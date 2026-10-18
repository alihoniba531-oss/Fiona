# WO3e 导演知识库

- **工作目录**：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`，基线提交 `4b45346`
- **Python**：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- **总计划**：`~/.claude/plans/fiona-shimmering-goose.md`，见其中「导演知识库」一节
- **作者规则**：同目录 `00-house-rules.md`，优先级最高

## 1. 目标

拆镜时，导演模型要先判断这一场属于什么类型，再从**本地知识库**取对应的模板、语法卡、模型能力卡、案例和反例来拆，并注明依据，不再全凭临场发挥。

本期交付五样东西：
1. 知识库数据。
2. 加载与校验、按标签取材料、知识库检查。
3. 案例库与节奏统计两张表。
4. 知识库页面。
5. 一个「试拆」功能，用来验收：同一场戏分别带知识库、不带知识库各拆一次，结果并排交给作者评。

正式把知识库接进逐集拆镜是 WO4 的事，本期不做。

**运行时不访问任何外部资源。** 卡片是仓库里的 YAML 文件，案例和统计存在 Fiona 自己的 SQLite 里。

## 2. 分三个阶段

| 阶段 | 内容 | 执行 | 闸门 |
|---|---|---|---|
| **一 样卡** | 起草两张样卡（对话、打斗）并定稿场景类型清单 | V4.1 Flash 一个任务，主控先审 | **交作者过目，确认后才进阶段二** |
| **二 实现** | 代码 3 块、内容 4 块，共 7 路并发 | dsh 引擎上的 DeepSeek V4.1 Flash（max），一张派单，用工作流并行 | 主控机械验证（含变异测试），dsh 上的 Opus 5.5（xhigh）独立复核，返修最多 3 轮 |
| **三 验收** | 3 场（对话、打斗、悬疑揭示）× 带 / 不带知识库各拆一次，并排交作者评 | 真实导演调用，先报价 | 作者评分 |

## 3. 卡片数据（契约；名字一字不改）

**存放位置**：`backend/studio/director_kb/cards/<type>/<id>.yaml`
- 每个文件只放一张卡。
- 文件名等于 `id`，用 kebab-case 英文。
- `type` 取值：`grammar`（语法）、`scene`（场景模板）、`model`（模型能力）、`negative`（反例）。

### 3.1 共同字段

```yaml
id: scene-dialogue            # 全库唯一；前缀与 type 对应：grammar- / scene- / model- / negative-
type: scene
title: 对话（两人静态）
summary: 一句话说明用途（≤80 字）
tags: [dialogue, two-person]  # 自由标签，小写英文，只用连字符（kebab-case，R1 起 schema 强制）；SceneTags.sensitive 里的下划线值在匹配前统一换成连字符
sources:                      # 至少一条；只提炼规则、用自己的话写
  - {name: 作者实测, license: own}
  - {name: seedance-shot-design, license: MIT-0, ref: references/scenarios.md}
version: 1
```

`license` 只允许以下取值：`own`、`MIT`、`MIT-0`、`Apache-2.0`、`CC-BY-4.0`、`vendor-doc`。`vendor-doc` 表示厂商官方文档，只提炼要点。

### 3.2 语法卡 `grammar`（13 张，id 见 §3.6：景别、角度、运镜各类、焦段与景深、转场、轴线与视线、连续性）

```yaml
definition: 定义
narrative_use: 叙事作用
safe_prompt: 提示词里的安全写法（术语 + 白话），例如「推轨（镜头沿地面平稳靠近）」
avoid: [裸写 Dolly, …]        # 不要这样写
entries:                       # 可选：同一类下的子条目（如 9 级景别）
  - {name: 中景, definition: …, safe_prompt: …}
related: [grammar-…]
```

### 3.3 场景模板 `scene`（19 张，清单见 §4）

```yaml
scene_type: dialogue           # 与 §4 清单一致，全库唯一
signals: [剧本里出现什么就算这一类, …]
beats: [节拍1, 节拍2, …]       # 3–6 个
coverage: [推荐镜头顺序, …]    # 覆盖拍法，每步写景别 + 机位 + 目的
pacing:                        # 三档节奏
  fast: {shots_per_min: [18, 24], shot_seconds: [1.5, 3.0]}
  mid:  {shots_per_min: [12, 18], shot_seconds: [3.0, 5.0]}
  slow: {shots_per_min: [6, 12],  shot_seconds: [5.0, 9.0]}
camera: [运镜建议，带敏感镜头约束]
sound: [声音设计要点]
ai_risks:                      # AI 生成风险与降级方案
  - {risk: …, fallback: …}
example: 一段自写的示例拆法（6–10 镜，原创内容，≤600 字）
related_grammar: [grammar-…]
related_negative: [negative-…]
position: opening | ending     # 只有两张「位置卡」带这个字段：opening-hook 为 opening，cliffhanger 为 ending；内容卡不带
```

- **内容卡与位置卡**（作者 2026-10-18 确认）：
  - 内容卡：17 张，按内容分类。
  - 位置卡：2 张，即开场钩子、结尾悬念。位置卡叠加在内容卡之上使用，例如「开场就是一场打斗」= fight 模板 + opening-hook 位置卡。
  - 位置卡的字段与内容卡相同，另加 `position`。
  - 位置卡的 beats、coverage、camera 只写「在这个位置要额外做什么」，不重复内容卡的拍法。
- **样卡**：`scene-dialogue.yaml` 和 `scene-fight.yaml` 已经过作者确认，是其余场景卡的写法样板。其余卡的字段、详略、示例格式、数字写法都照它们来。

### 3.4 模型能力卡 `model`（5 张，id 见 §3.6：万相 3.0 写实 / 动漫、Seedance 2.5 写实 / 动漫、Seedream 5.0 出图）

```yaml
model: wan-3.0 | seedance-2.5 | seedream-5.0
style: photoreal | anime | 3d | any
facts: [时长档位 / 分辨率 / 帧率 / 原生音频 …，每条注明 实测 或 官方]
portrait_gate: 什么镜头会被拒、怎么绕（无则写「无」）
copyright: 版权拦截表现与对策
motion_risks: [运镜导致编造的风险]
prompt_syntax: [时间戳等写法要点]
max_characters: 2
lint_rules:                    # 供知识库检查使用的数据驱动规则
  - {id: seedance-portrait, when: {realism: photoreal, shot_size_in: [中景, 近景, 特写], face_visible: true}, level: warn, message: …}
  - {id: …, pattern: "(?i)\\bdolly\\b", level: warn, message: …}
```

### 3.5 反例卡 `negative`（至少 21 张，id 见 §3.6）

```yaml
wrong: 错误写法（提示词片段或做法）
right: 正确写法
why: 原因
evidence: 出处（如 P01 第 3 次返工 / 作者实测 2026-10-17）
applies_to: {scene_type: [...], model: [...]}   # 可选
lint_pattern: 可选，正则；有就并入知识库检查
```

### 3.6 卡片 id 总表（全库引用只能用这里的 id；各块只写自己名下的卡，但所有 id 都必须存在）

**grammar（13 张，D3）**

| id | 内容 |
|---|---|
| `grammar-shot-size` | 景别，用 `entries` 列 9 级 |
| `grammar-camera-angle` | 角度：平视、俯、仰、荷兰角、顶拍 |
| `grammar-camera-movement` | 运镜总表，用 `entries` 列推、拉、摇、移、跟、升降、环绕、手持 |
| `grammar-lens-focal` | 焦段与景深 |
| `grammar-transition` | 转场 |
| `grammar-axis-eyeline` | 轴线与视线 |
| `grammar-continuity` | 动作、道具、服装、光线的连续性 |
| `grammar-over-shoulder` | 过肩 |
| `grammar-shot-reverse-shot` | 正反打 |
| `grammar-insert-closeup` | 插入特写 |
| `grammar-action-match` | 动作匹配剪辑 |
| `grammar-establishing-shot` | 定场镜 |
| `grammar-backlight-silhouette` | 逆光与剪影 |

**model（5 张，D3）**

| id | 对应 |
|---|---|
| `model-wan-3-photoreal` | 万相 3.0 写实 |
| `model-wan-3-anime` | 万相 3.0 动漫 |
| `model-seedance-2-5-photoreal` | Seedance 2.5 写实 |
| `model-seedance-2-5-anime` | Seedance 2.5 动漫 |
| `model-seedream-5` | Seedream 5.0 出图，`style: any` |

**negative（21 张，D4；可以再加，但这 21 个必须有）**

| id | 内容 |
|---|---|
| `negative-looking-at-camera` | 人物看镜头 |
| `negative-bare-camera-term` | 英文运镜术语裸写 |
| `negative-voiceover-mouth-moves` | 画外音时人物跟着动嘴 |
| `negative-photoreal-face-seedance` | 写实正脸撞 Seedance 肖像闸 |
| `negative-fight-sub-four-second-generation` | 打斗为短镜单独生成不足 4 秒 |
| `negative-nonfixed-structure-material` | 结构、材质镜头用了运动机位 |
| `negative-orbit-invents-detail` | P01：环绕运镜让丝杠穿进滚柱 |
| `negative-push-tilt-reveals-face` | P01：推近后上摇露出 AI 正脸 |
| `negative-move-down-material-drift` | P01：下移镜头让金属屑变成木刨花 |
| `negative-giant-offscreen-camera-move` | 只露局部的巨物，被跟拍或拉远编了出来 |
| `negative-ip-lookalike` | 形象近似知名 IP，被版权拦截 |
| `negative-grimy-realism` | 写实被写成脏乱 |
| `negative-transient-look-in-sheet` | 定妆图画了临时状态 |
| `negative-too-many-actions` | 单镜动作超过 3 个 |
| `negative-crowded-frame` | 同框超过 2 人 |
| `negative-no-establishing-shot` | 新场段开头没有定场镜 |
| `negative-unwritten-detail-seedream` | Seedream 没写到的细节就不会画 |
| `negative-focal-without-purpose` | 焦段没有叙事理由却写了 |
| `negative-axis-jump` | 越轴 |
| `negative-prop-continuity-break` | 道具归属前后断开 |
| `negative-unverified-model-syntax` | 把没核实过的模型写法（如时间戳格式）写成定论 |

**scene（19 张，D1 / D2）**：id 一律为 `scene-<scene_type>`，scene_type 见 §4。

## 4. 场景类型清单（作者 2026-10-18 确认：19 类，其中 17 类内容卡、2 类位置卡）

定义、识别信号和相邻区分见同目录 `01-scene-list.md`。

**内容卡（17）**

| scene_type | 中文名 | scene_type | 中文名 |
|---|---|---|---|
| dialogue | 对话（两人静态） | establishing | 环境建立 / 定场 |
| confrontation | 争执对峙 | twist | 反转 |
| fight | 打斗 | intimacy | 告白 / 亲密 |
| chase | 追逐 | phone-call | 电话 / 远程对话 |
| reveal | 悬疑揭示 | process-closeup | 工艺操作 / 动作特写（P01 类） |
| monologue | 情感独白 / 内心戏 | explainer | 讲解科普（竖屏） |
| flashback | 回忆闪回 | scare | 惊吓 / 恐怖 |
| ensemble | 群戏 | investigation | 调查 / 搜索（新增） |
| montage | 过场蒙太奇 | | |

**位置卡（2，叠加在内容卡上）**

| scene_type | 中文名 | position |
|---|---|---|
| opening-hook | 开场钩子 | opening |
| cliffhanger | 结尾悬念 | ending |

## 5. 标签与取材料（`backend/studio/director_kb/retrieval.py`）

```python
class SceneTags(TypedDict):
    scene_type: str            # §4 的 17 类内容卡之一；传位置卡的类型返回 422
    position: Literal["opening", "body", "ending"]   # 缺省为 body
    pace: Literal["fast", "mid", "slow"]
    emotion: str               # 自由文本，≤20 字
    cast_count: int            # 1–6
    realism: Literal["photoreal", "anime", "3d"]
    setting: Literal["interior", "exterior", "mixed"]
    sensitive: list[str]       # 子集：face_closeup / structure / material / giant_offscreen / ip_risk

def select_materials(tags: SceneTags, video_model: Literal["wan", "seedance"], *,
                     owner: str | None = None, budget_chars: int = 8000) -> dict
```

**返回值**：

```
{"template": card|None,
 "position": card|None,
 "grammar": [card…],
 "model": card|None,
 "exemplars": [≤3],
 "negatives": [≤3],
 "card_ids": [...],
 "text": "拼好的注入文本",
 "chars": n}
```

**选取规则**（结果必须确定，同样输入永远得到同样输出）：

| 材料 | 规则 |
|---|---|
| template | 按 `scene_type` 取 1 张内容卡 |
| position | `position` 为 opening 时取 `scene-opening-hook`，为 ending 时取 `scene-cliffhanger`，为 body 时为 None |
| grammar | 按优先级 template 的 `related_grammar` → position 的 `related_grammar` → `tags` 与 sensitive 命中的卡，依次去重，截取前 5 张，再按 id 排序输出（R1 澄清：先按优先级截取，再排序） |
| model | 按 `video_model` 加 realism 匹配：先找 style 完全相同的，没有就取 `any` |
| negatives | 依次取 template、position 的 `related_negative`，再取 `applies_to` 命中的卡；去重，最多 3 张 |
| exemplars | 只在传了 owner 时查库：同 scene_type 的好例，按时间倒序，最多 3 条 |

- 注入文本的总长不超过 `budget_chars`。超出时，按「exemplars → negatives → grammar 尾部」的顺序裁剪；template、position 和 model 永远保留。
- 卡片文本统一渲染成「【卡片 id】标题：要点」，方便导演在输出里引用 id。

## 6. 知识库检查（`backend/studio/director_kb/lint.py`）

```python
def lint_shots(shots: list[dict], *, video_model: str, tags: SceneTags) -> list[dict]
```

返回 `[{shot_no, rule_id, level: "warn"|"info", message}]`。

**内置规则**：
1. 英文运镜术语裸写：Dolly / Crane / Aerial / Truck / Pedestal / Orbit，且同一提示词里没有对应的中文白话。
2. 「朝向镜头 / 看向镜头 / 直视镜头 / 面朝镜头 / looks at camera」。
3. 单镜动作超过 3 个：按动作分隔符（「，然后」「，接着」「、并」「；」）近似计数。
4. 该镜带有 sensitive 标记，或 tags.sensitive 含 structure / material / face_closeup / giant_offscreen，却用了非固定机位（camera 不含「固定」）。
5. `video_model == "seedance"` 且 realism 为 photoreal 且景别属于中景、近景、特写且露脸：提示肖像闸，建议改用万相或剪影俯拍。
6. 生成时长小于 4 秒：info。

**数据驱动规则**：model 卡的 `lint_rules`，加上 negative 卡的 `lint_pattern`。

## 7. 案例库与统计（只新增表，`store.py` + 迁移）

```sql
studio_exemplars(id TEXT PK, owner TEXT, project_id TEXT NULL, source TEXT,      -- 'studio' | 'import:P01' 等
  scene_type TEXT, kind TEXT CHECK(kind IN ('good','bad')), reason TEXT,
  shot_json TEXT, keyframe_asset_id TEXT NULL, video_model TEXT, qc_json TEXT, cost_cny TEXT,
  tags_json TEXT, created_at TEXT, archived INTEGER DEFAULT 0)
studio_stats(owner TEXT, scene_type TEXT, episodes INTEGER, shots INTEGER,
  avg_shot_s REAL, shot_size_json TEXT, camera_json TEXT, updated_at TEXT, PRIMARY KEY(owner, scene_type))
```

- 删号时，这两张表与其他 studio 表在同一事务里删除。
- 迁移照 WO3d 的写法：引用新列的索引放进 `_ADDED_COLUMN_INDEXES`。
- `director_kb/stats.py` 提供 `accumulate(owner, shots_by_scene_type)`，WO7 终检通过时会调用它。本期只提供函数和读接口。
- `backend/scripts/studio_import_exemplars.py --owner <u> --manifest <path> --source P01 [--scene-type …]`：从 v2.1 清单导入好例。
  - 本机只在验收时手动跑。
  - 测试用合成夹具。
  - 公开仓库里不放任何作者的原始清单。

## 8. 接口（`backend/routers/studio.py`，全部只开放给作者）

| 方法与路径 | 说明 |
|---|---|
| `GET /studio/kb/cards?type=&q=` | 卡片列表：id、type、title、summary、tags |
| `GET /studio/kb/cards/{id}` | 完整卡片 |
| `GET /studio/kb/exemplars?scene_type=&kind=` | 列表 |
| `PATCH /studio/kb/exemplars/{id}` | 改 kind、reason，或归档 |
| `GET /studio/kb/stats` | 统计；累计不足 5 集时返回 `{"ready": false, "episodes": n}` |
| `POST /studio/projects/{pid}/kb/trial/quote` | 请求体 `{scene_text ≤3000, tags: SceneTags, target_seconds 10–120, video_model, modes: ["with_kb","without_kb"]}`，返回 CastingQuote 同形报价（kind=`kb_trial`）。用项目当前的导演模型，按 brain 任务口径预留 |
| `POST /studio/projects/{pid}/kb/trial/start` | `{quote_id}`。只能确认一次，15 分钟过期，受日上限、单次上限约束 |
| `GET /studio/projects/{pid}/kb/trials/{trial_id}` | 两种模式各自的 shots、template_id、deviations、card_ids、lint 结果、注入的字数，以及 `review`（见 §8.1） |
| `GET /studio/projects/{pid}/review-provider` | `{"review_provider": "claude"\|"qwen"\|"deepseek"\|"off", "brain_provider": …, "same_as_director": bool}` |
| `PATCH /studio/projects/{pid}/review-provider` | 请求体 `{"review_provider": "claude"\|"qwen"\|"deepseek"\|"off"}`，其他值 422 |

### 8.1 交叉审核 `cross_review`（作者 2026-10-18 确认，完整说明见同目录 `03-cross-review.md`，两处冲突时以本节为准）

- 在 `brain_tasks.TASKS` 里登记 `cross_review`，提示词放在 `prompts/cross_review.md`；输入、四个审核方面、输出 schema 按 `03-cross-review.md` §2。
- 项目字段 `studio_projects.review_provider`：取值 `claude` / `qwen` / `deepseek` / `off`，默认 `qwen`（模型即 brain 现有的 qwen3.8-max）。
- 试拆：两种模式的 `shot_plan` 各自成功后，若 `review_provider != off`，各发 1 次 `cross_review`。输入：`source_text = scene_text`，`adaptation_scale = "适度"`，`shots` 为该模式的分镜。审核调用用 `run_brain(..., provider=review_provider)`。
- 报价：审核调用按审核模型的 brain 单价一并计入试拆报价，并按 brain 任务口径预留；`off` 时不计。
- 审核失败（含 `uncertain`）只记在 `review` 里，不影响试拆本身的状态与结果；审核调用同样单发，传输错误不重试。
- 试拆结果里的 `review`：`{"with_kb": R, "without_kb": R}`，`R = {"provider", "model", "status", "verdict", "summary", "issues"}`；没发审核时为 `null`。
- 审核结论只作提示，不自动退回或淘汰（总计划第 8 条）。

### 导演任务 `shot_plan`

- 在 `brain_tasks.TASKS` 里登记，提示词放在 `prompts/shot_plan.md`。
- **输入**：scene_text、tags、target_seconds、video_model，以及可选的 `kb_text`。
- **输出 schema**：

```
{"template_id": str|null, "deviations": str,
 "shots": [{"no", "beat", "shot_size", "angle", "camera", "action", "first_frame_prompt", "video_prompt",
            "dialogue", "sound_intent", "duration_s", "sensitive": [], "basis": [card_id…]}]}
```

- **提示词要求**：
  - 带知识库时：每镜注明依据的卡片 id；偏离模板时，要在 deviations 里写理由。
  - 不带知识库时：`basis` 允许为空。
  - 素材按不可信数据处理，沿用 brain 现有的措辞。
  - 遵守作者规则里的通用条款：不直视镜头、每镜动作不超过 3 个、敏感镜头用固定机位，这几条两种模式都写进提示词。目的是让对比只体现「知识库」本身的差异，而不是基础规则的差异。

## 9. 知识库页面（`frontend/app/studio/kb/page.tsx`）

- **入口**：工作室首页和项目页的页头各加一个「导演知识库」链接。
- **七个页签**：语法、场景模板、模型能力、反例、案例库、节奏统计、试拆对比。
  - **卡片页签**：左边是列表（可按标签筛选、搜索），右边是详情，字段按卡片类型渲染。
  - **案例库**：列表、标好例 / 反例、改原因、归档。
  - **节奏统计**：累计不足 5 集时，显示空态文案「累计满 5 集后显示你的节奏统计」。
  - **试拆对比**：
    1. 选项目、粘贴一场戏、填标签（场景类型下拉，其余为表单）。
    2. 报价框复用 `CastingQuoteDialog` 的样式。
    3. 结果左右两栏并排展示：「带知识库 / 不带知识库」。每栏是镜头表，列出景别、机位、动作、时长、依据；lint 警告用标签显示；顶部写模板 id 和注入字数。
    4. 每栏镜头表下方显示该模式的审核结论：verdict、summary、issues 列表；`must` 用现有的警示色标出，不用粗体。
- **审核模型下拉**：新建 `frontend/components/studio/kb/ReviewProviderPicker.tsx`，在 `StudioWorkbench.tsx` 页头紧挨 `BrainProviderPicker` 放一个（只加这一处引用）。
  - 选项：Claude、千问 3.8 Max、DeepSeek、关闭。
  - 与导演模型相同时，旁边提示「同一模型自审，效果有限」。
  - 写明「审核会把原文发给所选厂商」。
- 沿用现有组件和类名，四态（空 / 加载 / 错误 / 成功）都要有，390px 宽度下不能横向滚动。
- **界面文字不加粗**（跨任务规则）：标题、名称、强调都不用 `font-semibold` / `font-bold` / `font-weight ≥ 600`，层次只靠字号与灰度。验收时遍历新文件，不得出现这些写法。
- 不改 `globals.css`，不加依赖。

## 10. 分块（阶段二，7 路并发；每块只改自己名下的文件）

| 块 | 只许改的文件 | 测试 |
|---|---|---|
| **A 知识库核心** | 新建 `backend/studio/director_kb/{__init__,schema,loader,retrieval,lint,stats}.py`；`backend/studio/store.py`（两张表 + `studio_projects.review_provider` 列 + 迁移 + `get_review_provider(pid, owner) -> str`、`set_review_provider(pid, owner, value) -> None` 两个函数）；`backend/database.py`（删号）；新建 `backend/scripts/studio_import_exemplars.py` | 新建 `backend/tests/test_studio_kb_core.py`（含「全部卡片过 schema、id 唯一、引用存在」）、`test_studio_kb_migration.py` |
| **B 接口、试拆与交叉审核** | `backend/routers/studio.py`；`backend/studio/brain_tasks.py`；新建 `backend/studio/kb_trial.py`、`backend/studio/cross_review.py`；新建 `backend/studio/prompts/shot_plan.md`、`backend/studio/prompts/cross_review.md` | 新建 `backend/tests/test_studio_kb_api.py`、`backend/tests/test_studio_cross_review.py` |
| **C 前端** | 新建 `frontend/app/studio/kb/page.tsx`、`frontend/components/studio/kb/*.tsx`、`frontend/lib/studio-kb.ts`；在 `frontend/app/studio/page.tsx` 页头加一个链接；在 `frontend/components/studio/StudioWorkbench.tsx` 页头加一个链接和一个 `ReviewProviderPicker`（只加这两处） | 新建 `backend/tests/test_studio_kb_frontend.py` |
| **D1 内容·场景模板 上** | `cards/scene/` 下新写 8 张：confrontation、chase、reveal、monologue、flashback、ensemble、montage、investigation（dialogue、fight 两张样卡已定稿，**不得改动**）；在 `01-scene-list.md` 末尾补 investigation 的定义、识别信号、相邻区分（只追加这一节） | 自查脚本：用 A 的 schema；若 A 还没写好，先用 §3 写一个临时校验，**不入库** |
| **D2 内容·场景模板 下 + 试拆样本** | `cards/scene/` 下 9 张：establishing、twist、intimacy、phone-call、process-closeup、explainer、scare 共 7 张内容卡，加 opening-hook、cliffhanger 两张位置卡（带 `position`，见 §3.3）；新建 `docs/tasks/2026-10-18-studio-wo3e-director-kb/trial-scenes.md`：3 场原创戏（对话、打斗、悬疑揭示），每场 300–600 字，附建议标签 | 同上 |
| **D3 内容·语法 + 模型** | `cards/grammar/*.yaml` 13 张、`cards/model/*.yaml` 5 张，id 按 §3.6。模型卡的写法（如 Seedance 2.5 与 2.0 的时间戳格式）只写来源里查得到的；查不到的写「待作者实测核实」，不得自编 | 同上 |
| **D4 内容·反例 + 出处 + 文档** | `cards/negative/*.yaml`：§3.6 的 21 张必须有，可再加；`THIRD_PARTY_NOTICES.md`（补 ai-visual-director MIT、prop-asset Apache-2.0、CameraBench CC BY 4.0、seedance-shot-design MIT-0）；`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md` 的短片工作室段 | 同上 |

**依赖关系**：B 和 C 依赖 A 的函数签名（§5–§7）；A 的测试依赖 D 的卡片。每块都按契约编码，跑集成测试前先确认依赖已经落盘，没落盘就先做别的。

## 11. 内容来源与授权

**可读的本地来源**（只提炼规则、用自己的话写，**不得复制成段原文**，示例一律原创）：
- `~/.claude/skills/ai-visual-director/knowledge/*.md`（MIT）
- `~/.claude/skills/seedance-shot-design/references/*.md`（MIT-0）：重点读 `scenarios.md`、`cinematography.md`、`failure-diagnosis.md`、`seedance-specs.md`、`official-examples.md`
- `~/.claude/skills/prop-asset/references/NEGATIVE-CASE-BOOK.md`（Apache-2.0）
- `~/Desktop/视频生成/.claude/skills/shortfilm-pipeline/references/*.md`（作者自己的规范，license 记为 own）
- 同目录 `00-house-rules.md`（作者规则，优先级最高）

**规则**：
- 冲突按作者规则里的优先级处理。
- 不读、不用 ShotDeck、FilmGrab 这类商业剧照库，不用 CineTechBench、DataDoP。
- 不写真实影片的台词或画面描述。
- 每张卡都必须有 `sources`。
- 复核阶段会做原文重合检查：连续 20 字以上与来源相同就判为不合格。

## 12. 验收（阶段二完成的标准）

1. `cd backend && <py> -m pytest -q tests/ -k studio` 全部通过。前端 `npx tsc --noEmit` 与 `npm run lint` 0 error。
2. 全部卡片通过 schema 校验，id 唯一，引用都存在。场景卡 19 张，覆盖 §4，其中恰有 2 张带 `position`；§3.6 列出的 id 全部存在。两张样卡与派单前逐字节相同。
3. `select_materials` 结果确定，同样的输入两次结果逐字相同；注入总字数不超过 8000；template、position 和 model 卡永远保留；`position=opening` 时取到 `scene-opening-hook`；scene_type 传位置卡类型时报 422。
4. lint 能拦下 §6 的 6 类内置问题，外加 model / negative 卡的数据驱动规则（各有用例）。
5. 试拆：报价只能确认一次，过期、超上限返回 409；两种模式各发 1 次导演调用；结果里带知识库的那份每镜都有 `basis`；用 MockTransport 或假 brain 测，不联网。
6. 迁移：旧库（d11b60d / 4b45346 的形态）跑 `init_db` 能补出两张表和 `review_provider` 列（旧项目取默认 `qwen`）；连续跑两次也正常。
6a. 交叉审核：导演为 deepseek、审核为 qwen 时，审核请求发往 DashScope 且 model 为 qwen3.8-max；`off` 时不发审核请求、报价不含审核费；审核失败时试拆结果仍完整；`PATCH review-provider` 非法值 422；全部用 MockTransport 或假 brain，不联网。
7. 页面七个页签四态齐全，390px 不横向滚动。
8. 每块写一份报告 `03-report-<块>.md`。

**禁止**：联网；读取 `.env`；读取或打印 Key；提交；隐藏或移动 `frontend/node_modules`；修改本块以外的文件。

## 13. 执行约定

- **既有测试一字不许改**：不得修改既有测试的输入、断言与夹具；新测试只放进 §10 列出的新文件。
- **测试不读仓库外文件、不依赖 git 历史**：卡片测试只读仓库里的 `cards/`；不读 `~/.claude/skills`、`~/Desktop` 下的任何东西。原文重合检查由主控在门禁里做，不进仓库测试。
- **何时停下来问**：只有影响「实现什么」的问题（规格自相矛盾、无法实现）才停下来，在报告里写明；只影响「怎么实现 / 怎么验证」的，自行决定并写明理由。你实测到的事实优先于规格里的断言，不符时停下来说明。任何情况下都不回滚已完成的工作。
- **跨块契约**：B、C 依赖 A 的函数签名（§5–§7、§10 A 行的两个函数）；scene 卡引用的 grammar / negative id 只能取自 §3.6。跑集成测试前先确认依赖文件已经落盘。
