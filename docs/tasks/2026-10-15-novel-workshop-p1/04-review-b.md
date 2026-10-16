# 小说工坊 P1 独立复核 B（规格符合度 / 越权与开关 / 隐私与密钥 / 删号删书 / 安全底线 / 兼容 / 文档）

复核日期：2026-10-15。复核对象：工作树 `.worktrees/fiona-novel-p0`，基线 `820fff1`，以 `git diff 820fff1` 与 `git status --porcelain` 中的未跟踪新增文件为准。计费、状态机、恢复、上下文压缩由复核员 A 负责，本文不重复。

全部核验离线完成：未运行真实提供方、未读取 `.env` 或密钥、未联网、未改动仓库内任何文件（本文件除外）。探针脚本与比对产物放在 scratchpad `review-p1b/`，不进仓库。

## 结论

**通过**（附 2 项低风险「必须修复」项，均不涉及安全、隐私、计费或越权，不阻断合入；建议在 P2 前或随 P2 一起返修）。

- 范围、接口、角色/模型限制、D2 拍板、开关与白名单、越权 404、密钥与日志隔离、删号/删书清理与条件写入、安全底线、本机监控零改动、P0 步骤键不变、既有测试零改动、文档同步：全部核验通过，证据见下。
- 必须修复项：① BYOK 运行期失效时书直接进入 `failed/step_failed`，既不可恢复也不附原因；② 建书/估算时 BYOK 不被支持的具体原因（厂商不支持 / 型号未知）被折叠成同一句「请先启用支持的自带模型」，规格要求的「该模型暂不支持用于小说工坊」从未到达用户。

## 一、逐项核验

### 1. 规格符合度

**§1 修改范围。** `git diff 820fff1 --numstat` 的被改文件：`CLAUDE.md`、`PLAN.md`、`README.md`、`backend/.env.example`、`backend/database.py`、`backend/main.py`、`backend/rate_limit.py`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`，以及 `backend/novel/` 下 `agent_pool.py`、`context.py`、`deliberation.py`、`fake_llm.py`、`llm_router.py`、`run_store.py`、`writing.py`。未跟踪新增：`novel/{billing,byok_bridge,runner,safety,service,store_db}.py`、`routers/novel.py`、`tests/test_novel_p1_*.py`（7 份）、`docs/tasks/2026-10-15-novel-workshop-p1/`。`git status --porcelain --untracked-files=all` 过滤后无任何范围外文件。全部在 §1 白名单内。`novel/` 内各改动均对应 §4（存储协议、计费钩子、byok、安全、solo、上下文压缩/卷摘要）。

**§7 接口表。** `routers/novel.py` 逐条对照：

| 规格 | 实现 | 结论 |
|---|---|---|
| 前缀 `/novels`，全部 `Depends(get_current_user)` | `workshop_user = Depends(get_current_user)` 再查开关与白名单，每个路由都挂它 | ✓ |
| `GET /catalog` 不返回系统提示 | 只取 `name/category/required/description`；探针逐行比对所有 `AGENTS` 系统提示（≥12 字的行）均不在响应中 | ✓ |
| `POST /estimate` 输入同建书 | 复用 `CreateNovel` | ✓ |
| `POST ""` 201 + 摘要 | `status_code=201`，返回 `detail()` | ✓ |
| 列表只返回本人 | `WHERE username=?`；探针两用户各只见自己的书 | ✓ |
| 详情 / 章节 / 各写接口 | `owned()` 先查 `id AND username`，不存在 → 404「小说不存在」；状态不符 → 409 中文 | ✓ |
| 输入上限 | `seed_idea≤2000`、`agents` 3–9 项、`batch_size` 1–10、章数 1–200、每章字 1000–4000、预算 1–1e7、留言 ≤500、改稿 ≤30000、细纲 JSON ≤30000、立项修改 JSON ≤60000、`extend_chapters` 1–10、章号路径 1–300；全部 `extra='forbid'` | ✓ |
| 写接口 `20/minute` | estimate、create、setup/approve、plan/approve、plan/redo、continue、pause、resume、PATCH、notes、PUT chapters、end/confirm、end/reject、DELETE 共 14 个全部带 `@limiter.limit('20/minute')` | ✓ |
| 导出附件 | `Content-Disposition: attachment; filename*=UTF-8''小说-<uuid>.md`；文件名只含 uuid，无标题注入面 | ✓ |
| 删书：取消 → 退款 → 同事务删五表 | `delete()`：`owned` → `cancel_novel`（取消 + `refund_reserved`）→ `BEGIN IMMEDIATE` 删四张关联表与 `novels` → commit | ✓ |
| 每写完一章计 `check_daily_cap("novel_chapter")` | `_advance` 写完后 `check_daily_cap`，开章前 `check_chat_daily_cap(hit=False)` 预判，达上限转 `paused/daily_cap` 不报错 | ✓ |

**§8 必选角色与模型。** `validate_selection`：缺 editor/writer/archivist → 422；editor/archivist/reviewer 只允许 `dashscope:qwen3.8-max`、`ark:doubao-seed-2-1-pro-260915`、`byok:self`；writer 只允许 `deepseek:deepseek-flash`、`dashscope:qwen3.8-max`、`byok:self`；顾问 0–5 个，多于 5 → 422；0 顾问自动转 solo。`byok_bridge.SUPPORTED_PROVIDERS = {anthropic, dashscope, deepseek}`，`custom/moonshot/zhipu/ark` 拒绝；型号须在 `KNOWN_MODELS`（anthropic 三型号与 byok 的 `CLAUDE_MODELS` 一致）。✓

**§13 D2。** `PLATFORM_MODELS` 为千问/DeepSeek/豆包三种，无 Claude；`anthropic:*` 直接作为平台模型建书 → 422（既有测试覆盖）。catalog `notice` 文案与 D2 原文一致。✓（文案对所有用户无条件显示，见可优化 1）。

### 2. 越权与开关

探针 `probe_api.py::test_gate_literal_values_and_unauthenticated`：`FIONA_NOVEL` 取 `' 1'`、`'1 '`、`'01'`、`'yes'`、`'True'`、`'1\n'` 时 `GET /novels` 与 `/novels/catalog` 均 404；既有测试覆盖 `'0'`、`'true'`。白名单：`FIONA_NOVEL_USERS=''` → 403（既有测试），不在名单的用户对任何路径（含 catalog、他人书的 15 类操作）→ 403（探针）。

探针 `test_cross_user_all_endpoints_and_export_isolation`：两个白名单用户各建一本并写完，B 对 A 的书执行 GET 详情/章节/导出、setup/approve、plan/approve、plan/redo、continue、pause、resume、PATCH、notes、PUT chapters、end/confirm、end/reject、DELETE 共 15 类，全部 404 且 detail 为「小说不存在」；A 查不存在的 id 同样 404（无法区分「别人的」与「不存在」）；期间 fake 调用数不变、A 的书状态不变。导出互相隔离。

未登录请求：开关开或关都返回 401（见可优化 2）。

### 3. 隐私与密钥

- **Key 不落库/不进日志/不进返回。** 既有测试 `test_byok_key_and_story_are_absent_from_db_logs_and_responses` 用哨兵 Key 跑完一章，五张表、stdout/stderr/caplog、详情/章节/catalog 响应中都没有哨兵；`test_byok_reuses_nonstreaming_provider_seam_and_releases_key` 用 MockTransport 证明请求头带 Key、调用后 `router._clients == {}`、临时客户端已关闭、bridge 不留任何字段、步骤产物无哨兵。代码层面：`byok_bridge.resolve()` 只在调用期间返回 dict，`llm_router._single_real_call` finally 里 `client.close()` + `resolved.clear()`；`describe()` 只走 `get_public_config`，不解密（既有测试断言 `get_internal_config` 不被调用）。
- **日志不含思路/正文/提示词。** 新增代码中全部 logger/print：`billing.py:72`（固定文案，不回显覆盖值）、`runner.py:149/188`（只有 novel_id、状态、异常类型名）、`llm_router.py:325`（novel_id、章号、角色、模型、token、耗时、状态）；`utils/background_tasks._task_finished` 只打印异常类型名；`_exception_metadata` 只记类型名与 HTTP 状态码。`_run` 吞掉所有异常后只记类型名。
- **novel_steps 不存完整提示词。** `DbStepStore.write_step` 只写 `request_digest = sha256(messages)`，`messages` 不入库；`billing.reserve` 同样只写 digest。既有 store 测试用 `PROMPT_SENTINEL` 证明。
- **导出只含本人书。** `export()` 经 `owned()`；探针证明。
- **估算只读本人步骤。** `estimate` 的 SQL 带 `username=?`。

### 4. 删号与删书

- `database.delete_account_data`：函数开头先 `await cancel_user_tasks(username)`（取消任务 + `refund_reserved`），随后在同一 `BEGIN`…`commit` 事务内、`DELETE FROM users` 之前，按 `novel_id IN (SELECT id FROM novels WHERE username=?)` 删四张关联表再删 `novels`。✓（diff 第 795–903 行）
- **删号后后台任务不重建数据。** 既有 `test_obsolete_workers_cannot_write_any_artifacts` 覆盖 token 失效 / 用户删除 / 书删除三种情况下 `write_step/append_usage/commit_setup` 均返回 False 且无行写入。我另写了两条更贴近真实竞态的探针：
  - `test_raw_account_deletion_mid_run_does_not_recreate_rows`：fake 在 `write` 步骤阻塞，期间绕过 `cancel_user_tasks`、直接用 SQL 删掉五张表的行与 `users` 行，再放行 worker 跑完；结果五张表中该用户的行数全为 0、`users` 未被重建、`runner.TASKS` 为空。证明保护来自 `DbStepStore.transaction()` 在 `BEGIN IMMEDIATE` 内 JOIN users + run_token 的条件判断，而不依赖取消时序。
  - `test_billing_reserve_after_account_gone`（`DEV_MODE=0`）：用户已删 → `reserve()` 抛 `RunNoLongerActive`，`novel_steps` 与 `users` 均 0 行；书已删但用户在 → 抛 `RunNoLongerActive` 且 `reserve_strawberries` 已扣的草莓被退回（余额 500 不变）。
- 删书：既有 API 测试在删除后逐表 `COUNT(*)=0`。

### 5. 安全底线

`novel/safety.py::NOVEL_SAFETY_RULES` 五点逐条对应 §4.4：未成年人性内容/性暗示、露骨性描写、真实个人捏造丑闻、犯罪/武器/毒品/自伤不给可操作步骤配方方法、仇恨/极端主义。探针 `probe_safety.py` 枚举 11 个角色 × 14 种 task 共 154 个 `get_agent` 系统提示：每个恰好包含一次安全块，位置在主体之后、`INJECTION_GUARD` 之前，且提示仍以 `INJECTION_GUARD` 结尾；`_card` 对 `JSON_STRING_QUOTE_RULE` 做了剥离再追加，保持原有「引号规则 → 防注入句」的结尾契约。✓

### 6. 兼容

- **本机监控零改动。** `git diff 820fff1 -- database.py main.py rate_limit.py CLAUDE.md PLAN.md README.md .env.example ARCHITECTURE.md DEPLOYMENT.md | grep '^-[^-]'` 输出为空：九个受保护文件只有新增行，无删除、无移动；numstat 为 `13/0、6/0、2/0、8/0、6/0、8/0、12/0、12/0、10/0`。
- **/health 不变。** `main.py` 只增 6 行（导入、恢复、关闭、挂路由），不触及 `/health`；既有 store 测试断言 `schema_migrations` 无 novel 版本；API 测试断言 `/health` 200。
- **P0 离线脚本不变（独立验证，不依赖实施方的冻结常量）。** 我用 `git archive 820fff1 backend/novel` 抽出基线包到 scratchpad，分别用基线代码与当前代码对四份配置 `expA/A2/B/C` 跑 `run_experiment(dry_run=True)`，比较排序后的步骤键、`chapter.md` 的 sha256、以及输出目录的完整文件清单：`A 71/10/132`、`A2 61/10/122`、`B 109/9/161`、`C 5/0/17` 全部 SAME；再把基线结果与 `tests/test_novel_p1_p0.py::BASELINE` 比对，四组 steps/bodies 均 True，证明冻结常量确实来自改动前代码。唯一变化是输入字符数（提示词多了安全规则），属规格允许。
- **既有测试零改动。** numstat 中没有任何 `tests/` 文件；新增 7 个测试文件均未跟踪。全量 `python -m pytest -q`：`4855 passed, 3 skipped`（基线 4760 + 新增 95，跳过数与基线一致；本机沙箱无回环端口限制，报告中提到的 6 项在我这里全部通过）。
- **新测试不读仓库外文件、不依赖 git。** grep 七份测试：文件读取只有 `novel/pilot_configs/exp*.json`（仓库内）与 `tmp_path`；无 subprocess/git/expanduser；byok 测试把 `os.environ` 置空并封掉 socket。`httpx2` 是 anthropic SDK 的既有传递依赖，既有 `test_byok_*.py` 已在用，不算新增依赖。

### 7. 文档同步

README / ARCHITECTURE / DEPLOYMENT / PLAN / `.env.example` / CLAUDE.md 六处均写明：`/novels` 路由清单、`FIONA_NOVEL`（仅字面 1）、`FIONA_NOVEL_USERS`（空名单无人可用）、`FIONA_NOVEL_MAX_RUNNING=3`、`FIONA_DAILY_NOVEL_CHAPTERS=30`、`FIONA_NOVEL_PRICE_JSON`（整表覆盖、非法回落并告警一次）、五张表与无新迁移版本、数据发往阿里云百炼 / DeepSeek / 火山方舟 / 自带厂商（含 Anthropic）、平台无 Claude、Key 与提示词不落库不进日志。逐句与代码核对未发现不一致：价目默认值 1.80/5.40、0.33/1.30、0.90/4.50 与 `DEFAULT_PRICES` 一致且与 D1 折算相符；「必须完整包含三个规格」与 `get_prices` 的集合相等校验一致；「章节额度按北京时间换日、手动恢复」与 `daily_cap` 流程一致；「重启先退还 reserved 标 interrupted」与 `refund_reserved` 一致。`.env.example` 示例 JSON 可被 `get_prices` 原样接受。

## 二、必须修复项（低风险，不阻断合入）

### M1. BYOK 运行期失效 → 书变 `failed`，不可恢复也不附原因

- **位置**：`backend/novel/runner.py::_run` 的 `except Exception` 分支；`backend/novel/llm_router.py::_single_real_call`（`byok_bridge.resolve()` 抛 `ConfigurationError`）。
- **问题**：用户在书运行期间停用自带模型、换成不支持的厂商/型号或 Key 失效时，`resolve()` 抛 `ConfigurationError`，经 `call()` 的 `except ConfigurationError: raise` 直达 `_run` 的兜底分支，书被置为 `status='failed', pause_reason='step_failed'`。探针 `probe_api2.py::test_byok_config_disabled_mid_run_surface` 实测结果为 `failed step_failed`。`transition('resume')` 只接受 `paused`，于是用户只能删书重来（可导出但不能续写）。规格 §5 定义 `failed` 为「不可恢复的错误（附原因）」，而这是典型可恢复情形，且没有附任何原因。
- **影响**：BYOK 用户的书因一次配置变动被永久卡死；用户看不到原因。
- **修法**：在 `_run` 中单独捕获 `ConfigurationError`（它是 `ValueError` 子类，消息为固定中文、不含密钥），转 `paused`，原因沿用枚举内的 `step_failed`（或与作者确认新增 `byok_unavailable`），并把异常消息写入 `config_json` 的一个固定字段（如 `_last_error`）由 `detail()` 返回；用户重新启用自带模型后 `resume` 可续跑（步骤缓存保证不重跑）。同时建议 `_run` 兜底分支也把类型名写入 `_last_error`，让 `failed` 真正「附原因」。

### M2. BYOK 不被支持的具体原因未到达用户

- **位置**：`backend/novel/byok_bridge.py::ByokBridge.describe`（吞掉 `ConfigurationError` 返回 None）；`backend/novel/service.py::validate_selection`（`except ValueError` 分支因此成为死代码，最终统一 `fail('请先启用支持的自带模型', 422)`）。
- **问题**：规格 §4.3 要求型号未知时「报『该模型暂不支持用于小说工坊』」，§10.2 要求 byok 厂商不被支持时附中文原因。实测（探针 `test_byok_unknown_model_message`）：dashscope 未知型号与 moonshot 厂商都返回同一句「请先启用支持的自带模型」。用户明明已启用，会误以为配置没保存。
- **影响**：误导性文案；规格指定的文案从未出现在接口返回里。
- **修法**：让 `describe()` 返回 `{"error": str(exc)}` 或改为 `describe()` 抛出、由 `catalog` 捕获为 `byok: {"error": ...}`、`validate_selection` 直接把 `ConfigurationError` 消息作为 422 detail；三条既有消息（「请先启用可用的自带模型」「小说工坊仅支持自带 Anthropic、千问或 DeepSeek」「该模型暂不支持用于小说工坊」）都是固定文案，不含任何用户数据。

## 三、可优化项

1. **catalog 的 D2 提示无条件显示。** 规格要求「为没有启用自带 Claude 的用户写明」；现在已启用自带 Claude 的用户也看到「主编可选千问或豆包……」。可按 `byok and byok['provider']=='anthropic'` 切换文案。
2. **开关关闭时未登录请求返回 401 而非 404。** `workshop_user` 先跑 `get_current_user`。把开关检查放在鉴权之前（或在 `workshop_user` 内先读环境变量再 `await get_current_user`），可让功能关闭时对外完全不可见。
3. **同一用户第二本书 409 没有专门测试。** 规格 §10.8 要求；代码行为正确（探针 `test_same_user_second_book_409` 实测 409「每个用户同时只能运行一本小说」，`awaiting_setup` 后可建第二本），建议补一条测试冻结。
4. **删号 SQL 可加保险。** `DELETE FROM novel_* WHERE novel_id IN (SELECT id FROM novels WHERE username=?)` 对「有 username 但 novels 行已丢失」的孤儿行不生效；四张表都有 `username` 列，可改为 `WHERE novel_id IN (...) OR username = ?`。
5. **冗余索引。** `idx_novels_novel_id ON novels(id)` 与主键重复，可删。
6. **导出细节。** 文件名只用 uuid，可考虑 `小说-<title>-<uuid>.md`（经 `quote`）；正文里 `stale` 章节未标注，建议在导出 Markdown 中以注释或标题后缀标出，避免用户把过期章节当定稿。
7. **failed/paused 原因可见性。** 即便不做 M1，也建议 `detail()` 返回一个 `last_error`（固定文案或类型名），前端 P2 需要它。

## 四、给实施方的修改指令

1. `novel/runner.py::_run`：新增 `except ConfigurationError as error:` 分支（放在 `except Exception` 之前），调用 `_pause(store, "step_failed")`（若作者同意新增枚举则用 `byok_unavailable`），并在 `_pause` 中把 `str(error)` 写入 `config_json["_last_error"]`；`except Exception` 分支同样写入 `type(error).__name__`。`service.detail()` 把 `config.pop("_last_error", None)` 作为顶层 `last_error` 返回。补一条测试：运行中停用 BYOK → `paused`，重新启用后 `resume` 续跑且 fake 调用数证明已完成步骤未重跑。
2. `novel/byok_bridge.py::describe`：改为返回 `validate_config` 结果或 `{"error": 消息}`；`service.catalog` 原样放入 `byok`；`service.validate_selection` 在 `byok:self` 被选且 `describe()` 带 `error` 时以该消息 `fail(..., 422)`。更新既有 `test_unsupported_byok_create_is_rejected` 断言四种情况各自的文案（型号未知 → 「该模型暂不支持用于小说工坊」，厂商不支持 → 「小说工坊仅支持自带 Anthropic、千问或 DeepSeek」）。
3. 可选：按「可优化」1–5 顺手处理；每项改动后重跑 `tests/test_novel_p1_*.py` 与全量，并保证 `git diff 820fff1 -- database.py main.py rate_limit.py docs/*.md README.md PLAN.md CLAUDE.md backend/.env.example | grep '^-[^-]'` 仍为空。

## 五、核验命令摘录

```bash
# 范围与受保护文件
git diff 820fff1 --numstat
git diff 820fff1 -- backend/database.py backend/main.py backend/rate_limit.py CLAUDE.md PLAN.md README.md backend/.env.example docs/ARCHITECTURE.md docs/DEPLOYMENT.md | grep '^-[^-]'   # 空
git status --porcelain --untracked-files=all

# 测试（固定解释器，backend/ 下）
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_novel_p1_*.py   # 95 passed
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider                            # 4855 passed, 3 skipped

# P0 独立比对（scratchpad）
git archive 820fff1 backend/novel | tar -x -C $SP/baseline
(cd $SP/baseline/backend && PYTHONPATH=. $PY $SP/p0_compare.py $SP/p0_baseline.json)
(cd backend && PYTHONPATH=. $PY $SP/p0_compare.py $SP/p0_current.json)   # steps/bodies/files 全部 SAME，且与测试 BASELINE 一致

# 探针（scratchpad，conftest 作为插件加载）
PYTHONPATH=tests:. $PY -m pytest -q -p no:cacheprovider -p conftest -s $SP/probe_api.py    # 6 passed
PYTHONPATH=tests:. $PY -m pytest -q -p no:cacheprovider -p conftest -s $SP/probe_api2.py   # 2 passed
PYTHONPATH=. $PY $SP/probe_safety.py                                                        # 154 prompts, violations: []
```
