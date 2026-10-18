# WO3e 阶段二 A 块报告：知识库核心

- 日期：2026-10-18
- 范围：`02-spec.md` §3、§5、§6、§7、§12，以及 §10 的 A 行
- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`

## 1. 交付文件

新建：

- `backend/studio/director_kb/__init__.py`
- `backend/studio/director_kb/schema.py`
- `backend/studio/director_kb/loader.py`
- `backend/studio/director_kb/retrieval.py`
- `backend/studio/director_kb/lint.py`
- `backend/studio/director_kb/stats.py`
- `backend/scripts/studio_import_exemplars.py`
- `backend/tests/test_studio_kb_core.py`
- `backend/tests/test_studio_kb_migration.py`

修改：

- `backend/studio/store.py`：`studio_exemplars`、`studio_stats` 两张表；
  `studio_projects.review_provider`（DDL + `migrate_schema`）；审核模型读写函数；
  两张新表的读写接口。
- `backend/database.py`：删号事务删除 `studio_exemplars` / `studio_stats`。

两张样卡与其余卡片均未改动；卡片由 D1–D4 写入，A 只读。

## 2. 实现说明

### 2.1 卡片契约 `schema.py`

- 共同字段：`id/type/title/summary/tags/sources/version`；`summary ≤ 80` 字、
  `sources` 至少一条、`license` 只接受 `own/MIT/MIT-0/Apache-2.0/CC-BY-4.0/vendor-doc`。
- id：kebab-case，前缀必须与 `type` 对应；加载时再校验文件名（去 `.yaml`）等于 `id`。
- `scene`：`scene_type` 必须在 §4 的 19 类内；`id` 必须为 `scene-<scene_type>`；
  `beats` 3–6 个；`pacing` 必须恰好 `fast/mid/slow` 三档且每档
  `shots_per_min`、`shot_seconds` 都是两个正数、下限不大于上限；
  `coverage/camera/sound/ai_risks` 非空；`example ≤ 600` 字。
- `position`：只有 `opening-hook`（`position: opening`）与 `cliffhanger`
  （`position: ending`）可带；内容卡带 `position` 会报错，位置卡缺 `position`
  或值不符也会报错。因此 19 张场景卡里最多且恰好只有这两张位置卡。
- `grammar`：`definition/narrative_use/safe_prompt/avoid/related`，`entries` 可选，
  每个 entry 恰好 `name/definition/safe_prompt`。
- `model`：`model/style/facts/portrait_gate/copyright/motion_risks/prompt_syntax/
  max_characters/lint_rules`；每条 fact 必须注明「实测」或「官方」；
  `lint_rules` 的 `when` 与 `pattern` 二选一，`level` 只允许 `warn/info`，
  正则必须能编译。
- `negative`：`wrong/right/why/evidence`，可选 `applies_to` 与 `lint_pattern`；
  `applies_to.scene_type` 必须是合法场景类型。
- 全库引用：`grammar.related`、`scene.related_grammar/related_negative` 必须存在且类型
  正确；重复 id、重复 `scene_type`、文件与 id 不符都由 loader 明确报错。

### 2.2 加载器 `loader.py`

- 只读仓库内 `backend/studio/director_kb/cards/<type>/*.yaml`，没有从环境变量或仓库外
  取路径的入口；未知子目录里的 YAML 也会报错。
- YAML 使用拒绝重复键的 `SafeLoader` 子类，避免重复字段被静默覆盖。
- 对 B/C 提供的入口（B 已按这些名字接入并通过）：
  `load_library()`、`load_cards()`、`load_cards_of_type()`、`get_card()`、
  `all_cards()`、`scene_card()`、`list_cards(type=None, q=None)`、
  `missing_required_ids()`；`CardLibrary` 带 `by_type`、`by_scene_type` 索引。
- `build_library()` 供测试与 lint 复用同一套卡片/引用校验。

### 2.3 取材料 `retrieval.py`

- 严格按 §5：`SceneTags` TypedDict 与
  `select_materials(tags, video_model, *, owner=None, budget_chars=8000)`。
- template 按 `scene_type`；position 按 `opening/ending` 映射到两张位置卡；
  grammar 先取两张卡的 `related_grammar`，再取 tags/sensitive 命中的卡，去重按 id
  排序后最多 5 张；model 先在同一视频模型家族里找 style 完全相同，再找 `any`；
  negatives 先取 `related_negative`，再取 `applies_to` 命中的卡，去重最多 3 条；
  exemplars 只在传 `owner` 时查库，同 scene_type、`kind='good'`、未归档，
  `created_at DESC, id DESC` 取最多 3 条。
- `scene_type` 传 `opening-hook`/`cliffhanger` 时抛
  `fastapi.HTTPException(422, …)`（项目现有惯例），B 的接口层会原样转成 422。
- 结果确定：所有列表排序、SQL 排序与 JSON 序列化都固定；测试里同一输入调用两次
  返回的 dict 与 `text` 逐字相同。
- 卡片文本统一渲染成「【卡片 id】标题：要点」；`card_ids` 与最终注入内容一致。
- 预算裁剪按「exemplars → negatives → grammar 尾部」执行，template/position/model
  不删。若预算小到连三张基础卡的全文都放不下，则把三张基础卡改成
  「【id】标题：summary」摘要行并（极端情况下）截断到 `budget_chars`，保证
  `chars == len(text) <= budget_chars` 的硬约束。
- 只传 `owner` 时用只读 `sqlite3` 连接查案例库，因此该同步函数可以在异步路由里
  直接调用，不触发 `asyncio.run()` 的嵌套事件循环错误。

### 2.4 知识库检查 `lint.py`

`lint_shots(shots, *, video_model, tags)` 返回
`[{shot_no, rule_id, level, message}]`，`level` 只取 `warn/info`，按镜头顺序输出，
同一镜头同一 `rule_id` 去重。

6 条内置规则：

1. `bare-camera-term`：Dolly/Crane/Aerial/Truck/Pedestal/Orbit 裸写且同一镜头文本里
   没有对应中文白话。
2. `looking-at-camera`：朝向/看向/直视/面朝镜头及 `looks at camera` 等英文写法。
3. `too-many-actions`：按「，然后」「，接着」「、并」「；」近似计数，超过 3 个。
4. `sensitive-nonfixed-camera`：镜头自身带 `sensitive`，或 tags 含
   structure/material/face_closeup/giant_offscreen，而 camera 不含「固定」。
5. `seedance-portrait-gate`：Seedance + photoreal + 中景/近景/特写 + 露脸。
6. `short-generation`：`duration_s < 4`，`level=info`。

数据驱动：按 `video_model + realism` 选模型卡并执行其 `lint_rules`
（`when` 支持 realism/shot_size_in/face_visible/scene_type_in/position_in/sensitive_any；
`pattern` 用正则搜索）；所有 negative 卡的 `lint_pattern` 在 `applies_to` 匹配时并入，
默认 `warn`。真实卡片上的 `seedance-camera-fixed` 与
`negative-grimy-realism` 已各有测试用例。

### 2.5 统计 `stats.py`

- `accumulate(owner, shots_by_scene_type)` 为异步函数：每次调用代表一集，按传入的
  场景类型分组更新 `episodes(+1)`、`shots`、加权 `avg_shot_s`、`shot_size_json`、
  `camera_json`、`updated_at`；同一事务内完成读改写。
- `read_stats(owner)`（别名 `get_stats`）：累计集数 = 各行 `episodes` 的最大值；
  `< 5` 时精确返回 `{"ready": false, "episodes": n}`，`>= 5` 时返回
  `{"ready": true, "episodes": n, "scene_types": [...]}`，每行含
  `scene_type/episodes/shots/avg_shot_s/shot_size/camera/updated_at`。
- 缺失景别/机位统计为「未标注」；来源镜头数组为空时该场景类型跳过。
- 本期只做函数和读接口，未接 WO7 终检。

### 2.6 `store.py` 与迁移

- `studio_exemplars`、`studio_stats` 的列、`kind` CHECK 与主键严格按 §7；
  两张表加入 `STUDIO_TABLES_DDL`，案例索引
  `idx_studio_exemplars_owner_scene` 也在 DDL（只引用新表，不引用迁移列）。
- `studio_projects` DDL 与 `migrate_schema` 都补
  `review_provider TEXT NOT NULL DEFAULT 'qwen'`；旧库迁移后旧项目为 `qwen`。
- `get_review_provider(pid, owner) -> str`：未归档项目不存在时 404；
  `set_review_provider(pid, owner, value) -> None`：非法值 422，项目不存在 404。
- 供 B 使用的读写接口：`list_exemplars/get_exemplar/create_exemplar/update_exemplar`、
  `list_stats`，以及同步只读的 `good_exemplars_for_retrieval`。
- 连续两次 `init_db` 正常；d11b60d 与 4b45346 两种旧库形态都补出两表与列，
  旧行原样保留。

### 2.7 删号与导入脚本

- `delete_account_data` 在同一事务里按 owner 删除 `studio_exemplars`、`studio_stats`，
  并在测试里验证行确实清空。
- `scripts/studio_import_exemplars.py` 支持
  `--owner --manifest --source [--scene-type]`，清单接受 JSON/YAML，顶层数组或
  `items/exemplars/shots/records/data/examples/entries/rows` 之一；每条记录可带单镜
  `shot`/`shot_json` 或 `shots` 数组（展开为多条好例）。写入 `kind='good'`、
  `source='import:<source>'`，owner 必须已存在。测试用合成夹具，仓库没有作者原始清单。

## 3. 卡片状态

结束时卡片目录共 **58** 张，§3.6 的 id 全部存在，`missing_required_ids()` 为空：

- grammar 13 / scene 19（17 内容 + 2 位置）/ model 5 / negative 21。

两张样卡只读未改。A 的卡片测试与 B/C 的集成测试均已在当前卡片上通过。

## 4. 契约偏差与实现决定

1. **模型名写法**：§3.4 写 `wan-3.0`、`seedance-2.5`、`seedream-5.0`，D3 已落盘卡片
   使用连字符 `wan-3`、`seedance-2-5`、`seedream-5`。为了不把 D3 的卡片判错，
   `MODEL_NAMES` 同时接受点号与连字符两种写法（仍只限这三组模型）；检索按
   `wan-` / `seedance-` 前缀识别家族。这是唯一放宽的枚举，其余字段按 §3 严格校验。
2. **标签允许点号**：模型标签 `seedance-2.5` 需要点号，`TAG_RE` 允许小写字母、
   数字与 `-_.`；仍不接受大写或空格。
3. **小预算**：规格同时要求「注入文本不超过 budget_chars」与「三张基础卡永远保留」。
   默认 8000 不会冲突；极小预算下先压成三张卡的摘要行，最后才截断，
   优先保证硬字数上限与卡片 id 仍可引用。
4. **3d 视频模型**：现有 5 张模型卡只有 photoreal/anime/any，没有 3D 视频卡。
   `realism=3d` + `wan/seedance` 时按 §5 返回 `model=None`（返回值允许 None），
   不回退到出图模型 Seedream。
5. **统计集数**：`studio_stats` 没有 owner 级的独立集数列，`read_stats` 用各行
   `episodes` 最大值作为累计集数；每次 `accumulate` 至少命中一个场景类型，
   因此该最大值等于调用次数。
6. **案例查询同步化**：`select_materials` 是同步签名，owner 查询改用只读 sqlite3，
   避免在 FastAPI 异步事件循环里调用 `asyncio.run`。

## 5. 测试原始数字

以下均为在本机 `backend/` 目录、使用指定 venv 跑出的原始结果。

环境说明：当前会话 shell 的 `NO_PROXY` 值含 `[::1]`，httpx 会把它当 URL 解析并抛
`InvalidURL: Invalid port: ':1]'`；这是既有问题，连带既有
`tests/test_studio_casting_migration.py` 也会在 setup 阶段失败。为了让结果反映代码本身，
下列命令都在清掉代理变量（`env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY -u no_proxy`）
的干净环境执行；没有修改 conftest 或增加环境特判。

| 命令 | 结果 |
|---|---|
| `python -m pytest -q tests/test_studio_kb_core.py tests/test_studio_kb_migration.py` | **39 passed, 0 failed, 0 skipped**（3.37s） |
| `python -m pytest -q tests/test_studio_casting_migration.py tests/test_studio_integration.py` | **52 passed, 0 failed, 0 skipped**（1.94s，32 条 slowapi DeprecationWarning） |
| `python -m pytest -q tests/ -k studio` | **1757 passed, 0 failed, 0 skipped, 5550 deselected**（75.69s） |
| `python -m pytest -q tests/test_studio_kb_api.py tests/test_studio_cross_review.py`（B 块集成） | **17 passed, 0 failed, 0 skipped** |
| `python -m pytest -q tests/test_account_deletion.py tests/test_beta_admin_scripts.py tests/test_studio_casting_migration.py tests/test_studio_integration.py` | **81 passed, 0 failed, 0 skipped**（20.01s） |

A 的两个新测试文件覆盖：全部 58 张卡片过 schema、id 唯一、引用存在、场景覆盖与
位置卡数量；`select_materials` 确定性、8000 字预算、极小预算、template/position/model
保留、`position=opening`、位置卡类型 422、模型风格匹配、owner 案例取 3 条；
lint 6 条内置规则各一例、model/negative 数据驱动各一例、返回结构；
stats 5 集阈值与分布累计；导入脚本合成清单；d11b60d/4b45346 旧库迁移、
review_provider 默认值与非法值、连续两次迁移、删号清理。

## 6. 已知限制

- loader 每次调用重新读 58 个 YAML（无进程内缓存）；卡片量小，当前耗时在测试里可忽略。
- 导入脚本的 v2.1 清单字段是尽力兼容的假设（见 §2.7）；拿作者真实清单首次运行时
  如需新增字段映射，只改脚本、不改 schema。
- 本期未接 WO4 的逐集拆镜；`accumulate` 的实际调用时机由 WO7 决定。
