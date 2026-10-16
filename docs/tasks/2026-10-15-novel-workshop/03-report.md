# 小说工坊 P0 实施报告

日期：2026-10-15。工作树：`fiona-novel-p0`。所有命令均在 `backend/` 执行，解释器为 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。

## 交付结论

已实现规格要求的可复用 asyncio 原型、三个实验、离线 fake、断点续跑、预算与记账、作者报告和盲读文件。新增测试 **223 项全部通过**，超过要求的 40 项。A、B、C 三个 dry-run 均退出 0；A 两组各 5 章，B 第 9 章完结，C 两个审校模型均抓到 3/3 条、原稿误报均为 0。

全量仓库测试有六个既有用例受当前沙箱限制：绑定 `127.0.0.1` 端口时返回 `PermissionError: Operation not permitted`，表现为 1 failed、5 errors。已在不加载小说测试的独立命令中复现同样六项。没有改动这些测试或其夹具；§9.2 的“全量通过／与验收方基线比较”需在允许本地端口的环境另行确认。具体最终输出见下文。

没有读取真实密钥、访问网络、执行真实提供方或提交 git commit。真实路由只做代码实现和本地桩验证；哨兵密钥是测试自建字符串。没有新增依赖，没有改动任何任务开始时已存在的文件。

## 新增文件

共新增 23 个文件，全部位于白名单内：

```text
backend/novel/__init__.py
backend/novel/agent_pool.py
backend/novel/schemas.py
backend/novel/llm_router.py
backend/novel/fake_llm.py
backend/novel/bible.py
backend/novel/context.py
backend/novel/deliberation.py
backend/novel/writing.py
backend/novel/run_store.py
backend/novel/pilot.py
backend/novel/report.py
backend/novel/README.md
backend/novel/pilot_configs/expA.json
backend/novel/pilot_configs/expB.json
backend/novel/pilot_configs/expC.json
backend/tests/test_novel_schemas.py
backend/tests/test_novel_state.py
backend/tests/test_novel_router.py
backend/tests/test_novel_store.py
backend/tests/test_novel_workflow.py
backend/tests/test_novel_pilot.py
docs/tasks/2026-10-15-novel-workshop/03-report.md
```

任务开始时 `docs/tasks/2026-10-15-novel-workshop/02-spec.md` 已存在但未跟踪，因此也会出现在 `git status`；它不计入本次新增文件，未作修改。

按文件不重叠分工：A 负责 schemas/bible/context 及两份测试；B 负责 router/fake/store 及两份测试；C 负责角色池、配置、推演和写作及其测试；主代理负责包入口、pilot/report、README、端到端测试和本报告。同文件的后续修复均由原负责代理完成。

## 实现功能与规格 §1–§9 对应

| 规格 | 对应实现及验证 |
| --- | --- |
| §1 修改范围 | 仅新增上述 23 个白名单文件；没有扩展白名单，没有改动现有业务文件、依赖、README、测试或夹具。`git diff --exit-code` 无输出、退出 0。 |
| §2 技术约束 | Python 3.14.6；仅标准库及已安装 SDK；asyncio、提案和互评各使用 Semaphore(3)。四类路由在 `llm_router.py`；真实客户端延迟创建，显式 endpoint/api_key、timeout=300、max_retries=0；按规格关闭 thinking，JSON 调用传 response_format。环境检查仅涉及实际使用提供方，dry-run 在访问环境前直接返回。统一网络重试与中文 schema 修正各一次；失败记步骤。stdout 仅进度、估算和错误。 |
| §3 数据结构 | `schemas.py` 对 setup、提案、互评、裁决、审校、归档和矛盾插入逐字段验证；严格区分 bool/int，拒绝不存在 ID、重复评分／回应、非法完结和不合法新增人物。JSON 支持围栏与外部文字，拒绝重复字段、非有限数字及非对象顶层。`bible.py` 由代码分配 C/T/F ID，纯增量生成新版本。审校证据校验、丢弃记录和通过结论由代码计算。 |
| §4 每章流程 | `context.py` 纯函数计算 mode/stage，closing 保持及 final 强制结束；简报含全部摘要、伏笔、人物状态、最近5条timeline和本章留言。写手包含规定字段与上一章末1500字。`deliberation.py` 固定提案→互评→裁决，按配置顺序分配 P/O ID、计算五维及总均分，只发送他人提案。失败时取消并排空同阶段任务。`writing.py` 校验首行，长度重写一次；最多两轮审校修订；归档生成新圣经；记录全部规定标记。留言按章分配 N ID，主编逐条回应。 |
| §5 智能体池 | `agent_pool.py` 包含全部11张中文角色卡、完整职责及JSON结构，末尾均为规格防注入句。setup 8000、裁决4000；writer 上限按字数计算，必要时向上取整。提示词含重复桥段扣分、主线推进、收尾约束和写作细则。主编收到中文作者名。必选角色及畸形配置有退出2的校验。 |
| §6 实验与CLI | 三份配置按规格保留 seed、模型字符串、目标、组别和留言；`python -m novel.pilot run/report` 实现所有选项及0/2/3/4退出码。A一次setup共享、两组独立演化、SystemRandom分配盲读甲乙且续跑保留映射。B按逐章裁决至归档后完结，记录全部指标。C读取A panel第4章最终稿、章前圣经和细纲，校验3个唯一锚点及三类真实事实引文，按原稿偏移插入；审校不接收插入答案，8字公共连续子串判定抓到。 |
| §7 目录／续跑／记账 | `run_store.py` 临时文件+fsync+replace 原子写入步骤、manifest和产物；成功步骤直接读缓存，不重复调用或计费；配置哈希含dry-run，不含预算。调用前锁定预留预算，包含在途调用；超限不调用。每次尝试一行usage，保存失败审计、缓存token、耗时和尝试索引。`report.py` 生成过程报告、两类成本表、外部价格金额、估算表和盲读文件。额外 `bible_before.json` 和 `chapter_record.json` 支持C及报告重建。 |
| §8 离线测试 | 六份新测试共223项，覆盖所列20类用例：三个完整dry-run、9章完结、提前end修正/失败、final修正/失败、major伏笔守卫、模式阶段表、互评隔离/重复/漏评/非法分数、回应完整性、审校丢弃/非阻断/两轮上限、归档ID/版本、长度/标题、JSON修正、故障续跑、哈希、零预算与放宽、C锚点/匹配/指标、环境守卫、三个SDK构造全禁、哨兵密钥不落盘、必选角色缺失。另测并发预留和并行失败清理。 |
| §9 验收 | 新模块测试通过；三份dry-run通过且打印估算；环境守卫退出2；git无M/无已跟踪改动；打印点人工检查完成。全量测试执行完成，但六个旧用例被本地端口权限阻断，尚不能宣称全量通过。未获得验收方派活前基线，不能代替验收方作基线比较。 |

### 实验产物

| 实验 | 输出目录 | 结果 |
| --- | --- | --- |
| A | `/tmp/novel-p0-final-A` | solo/panel 各5章；`blind/版本甲.md`、`版本乙.md`、`key.json`、`阅读说明.md`，以及report/cost/estimate均存在。 |
| B | `/tmp/novel-p0-final-B` | 完结章号9，在[8,12]内；8个continue后end；第4章留言N1已采纳回应；归档后无open major伏笔。 |
| C | `/tmp/novel-p0-final-C` | dashscope:qwen3.8-max和anthropic:claude-sonnet-5-5均抓到3/3；原稿阻断误报数均0；这些标签对应dry-run中的本地fake调用。 |

第1次A探索运行保留在 `/tmp/novel-p0-A`；最终验证使用新的 `final-*` 目录，避免复用早期缓存。没有删除既有产物。

### 续跑与记账的解释

中断续跑测试逐字节比较最终正文、圣经、章节记录、标记、罗盘、盲读文件及 `report.md`；盲读随机映射在此对照测试中固定。失败尝试仍保留在usage审计中，耗时和尝试记录反映实际执行，因此不会把它们伪造成与无故障执行相同。正常再次运行已完成目录时，fake调用数和usage条数保持不变。

## 测试命令与输出末尾

以下 `$PY` 固定为：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
```

为避免生成缓存，全部Python命令使用 `PYTHONDONTWRITEBYTECODE=1`；pytest显式禁用cacheprovider。全量及旧测试复现额外设置 `PYTHON_DOTENV_DISABLED=1`，并将三个提供方key、OPENAI_API_KEY及JWT_SECRET覆盖为测试占位字符串，未读取实际环境值或 `.env`。

### 新增测试

```bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
```

```text
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.......                                                                  [100%]
223 passed in 2.19s
```

日志：`/tmp/novel-p0-verified-tests.log`。所有新增测试只使用fake或真实单次调用的本地桩；端到端测试将OpenAI和Anthropic客户端构造函数改成抛异常，并禁止IPv4/IPv6连接。密钥哨兵测试将单次真实调用方法替换为本地fake，不构造任何SDK客户端。

### 全量测试

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
```

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 3695 passed, 9 skipped, 14 warnings, 5 errors in 83.80s (0:01:23)
```

退出码1。日志：`/tmp/novel-p0-full-verified-tests.log`。失败与错误均为已有测试的loopback bind权限问题，详见独立复现；14条warning均为已有slowapi代码的Python3.14弃用提示。本次没有调整或跳过任何既有测试。

### 旧测试独立复现

同上测试环境前缀，运行：

```bash
"$PY" -m pytest -q -p no:cacheprovider \
  tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot \
  tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive \
  tests/test_safe_http_deadline.py
```

```text
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 1 passed, 14 warnings, 5 errors in 1.38s
```

日志：`/tmp/novel-p0-existing-failures.log`。同步HTTPServer及asyncio server均在bind本地端口时被沙箱拒绝，未到小说代码或外部请求。

### 三个dry-run与report命令

```bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-final-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-final-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-final-C --source-run /tmp/novel-p0-final-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot report --out /tmp/novel-p0-final-B
```

四条命令退出码均0。三个run的输出末尾即下节原文估算表；report成功时无标准输出。完整run日志：`/tmp/novel-p0-A.log`、`/tmp/novel-p0-B.log`、`/tmp/novel-p0-C.log`。

### 环境守卫

```bash
ANTHROPIC_BASE_URL=http://x PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-guard
```

```text
配置或环境错误：请先 unset 这些变量：ANTHROPIC_BASE_URL
```

退出码2，在检查密钥或创建客户端之前停止。

### 文件范围与stdout检查

```bash
git diff --exit-code
git status --porcelain --untracked-files=all
rg -n 'print\(' novel/
```

`git diff` 无输出、退出0；status仅有上述新增文件和原已存在未跟踪的02-spec.md，无M状态。打印只在 `llm_router.py` 的进度行和 `pilot.py` 的估算／错误位置；没有打印提示词、正文、模型输出或密钥。没有commit。

## 三个dry-run的估算表原文

下列内容逐字复制自各最终输出目录的 `estimate.md`，与对应命令标准输出末尾一致。模型标签按原配置保留，usage另有provider=fake标记。估算是按dry-run实际调用轨迹计算的上界，不声称涵盖真实模型额外产生的章节或修订。

### 实验 A

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| A | archivist | 10 | 53182 | 30000 |
| A | character_advocate | 10 | 43143 | 20000 |
| A | editor | 11 | 63733 | 48000 |
| A | plot_architect | 10 | 43123 | 20000 |
| A | reviewer | 10 | 70237 | 30000 |
| A | twist_designer | 10 | 43153 | 20000 |
| A | writer | 10 | 43270 | 50000 |
```

### 实验 B

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| B | archivist | 9 | 46503 | 27000 |
| B | character_advocate | 18 | 87355 | 36000 |
| B | editor | 10 | 73153 | 44000 |
| B | pacing_advisor | 18 | 87337 | 36000 |
| B | plot_architect | 18 | 87319 | 36000 |
| B | reviewer | 9 | 62511 | 27000 |
| B | twist_designer | 18 | 87373 | 36000 |
| B | writer | 9 | 42153 | 36000 |
```

### 实验 C

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| C | corrupter | 1 | 3688 | 2000 |
| C | reviewer | 4 | 15362 | 12000 |
```

## 未完成或需要人工确认

1. §9.2全量验收尚受本地端口权限阻断；需在允许loopback bind的环境执行同一全量命令，并与验收方掌握的派活前基线比较。本报告不把受阻用例算作通过。
2. 按明确要求，真实提供方从未运行。因此默认模型型号的实际可用性、真实返回格式、实测token与金额，需要后续另行授权验证；模型规格未联网查询、未擅自改写。没有内置价格。
3. 多智能体是否优于主编、真实模型能否合理收束、真实审校能力以及可拍摄性仍需作者评估。fake证明流程和守卫可执行，不能代替创作质量结论。
4. C的代码验证唯一锚点、真实引文及三类覆盖；自然语言插入与引文是否构成语义上的矛盾，仍需真实运行后人工抽查。
5. 同一输出目录支持单进程asyncio内的并发调用及续跑；不支持两个进程同时写同一目录，README已说明。

实现范围内没有遗留代码TODO；没有要求增加接口、数据库或前端。

## 第 1 轮返修

依据：`05-fix-r1.md`，并参考 `04-review.md`。独立复核指出的 Claude thinking 未关闭、输入重复与实验A信息不对称、C引文硬校验过严等问题成立。本节替代前文相应实现描述；保留前文作为首轮交付记录。

### 本轮状态与红线

功能修复已落实，最终小说测试 **423 passed**（原223项 + 本轮新增200项）。三份新目录的dry-run均退出0。真实SDK仅通过内存MockTransport构造与序列化请求；没有联网、读取实际密钥或运行真实提供方，没有新增依赖，没有commit。

**一项测试文本变更仍待确认**：R1-3指定的旧测试原输入只有一条user，而返修单要求新增的断言是 `system,user,assistant,user`，同时明确“只能新增这一条断言，原有断言保留”，并禁止改输入。没有擅自给旧测试补system，也没有在路由里补造system来迁就测试。实际assistant回放已经实现，新增独立回归用真实的system+user输入验证了完整四角色序列。已向用户询问是否允许仅为此旧测试补初始system消息；未收到确认前保留其输入和原有断言。写手标题通过独立规范化入口解决，不需要修改旧标题测试。

### 修改与新增文件

修改16个本任务文件，新增4个测试文件；未修改其他既有文件。

```text
修改 backend/novel/agent_pool.py
修改 backend/novel/bible.py
修改 backend/novel/context.py
修改 backend/novel/deliberation.py
修改 backend/novel/fake_llm.py
修改 backend/novel/llm_router.py
修改 backend/novel/pilot.py
修改 backend/novel/report.py
修改 backend/novel/run_store.py
修改 backend/novel/schemas.py
修改 backend/novel/writing.py
修改 backend/novel/README.md
修改 backend/tests/test_novel_router.py
修改 backend/tests/test_novel_schemas.py
修改 backend/tests/test_novel_workflow.py
追加 docs/tasks/2026-10-15-novel-workshop/03-report.md
新增 backend/tests/test_novel_r1_router.py
新增 backend/tests/test_novel_r1_schemas.py
新增 backend/tests/test_novel_r1_workflow.py
新增 backend/tests/test_novel_r1_pilot_report.py
```

按文件分成路由、schema/圣经、工作流/提示词三组并行；主代理负责context审校包、pilot、report、README及集成测试。同一文件始终由同一负责者串行修复。

已与 `/tmp/novel-p0-r1-before` 保存的返修前快照逐文件核对。三个旧测试文件的改动仅为：

- `test_role_token_limits_do_not_mutate_registry`：setup/decision期望改为12000/6000，其他期望保留。
- `test_insertions_quote_real_bible_facts_and_cover_three_categories`：原输入全部保留，改为验证“不合格引文不抛错且记录citation_check”。
- `test_decision_end_guards_and_fields[early_end]`：仅补 `foreshadowing_resolve=["F001"]`。
- `test_novel_router_parallel_budget_reservations_are_atomic`：仅在第二次调用外包 `asyncio.wait_for(..., 5)`。

`test_novel_pilot.py`、`test_novel_state.py`、`test_novel_store.py` 完全未动；原有标题测试未动；本轮其余测试全部放入新文件。

### 返修条目、落实方式与对应测试

| 条目 | 落实方式 | 对应测试（参数化展开计数） |
| --- | --- | --- |
| R1-1 | `CLAUDE_THINKING`映射：Sonnet→between_tools，Haiku→disabled，Opus不传；不传output_config。未知Claude在读取环境前退出2，Opus启动仅提示一次。使用anthropic 1.12.1 + DefaultAsyncHttpxClient + httpx2.MockTransport捕获真实SDK请求体。 | `test_claude_sdk_request_disables_thinking_by_model`、`test_unknown_claude_never_constructs_client`、`test_opus_startup_notice_is_one_line_for_all_roles`、集成 `test_r1_unknown_claude_configuration_rejected_before_environment`。 |
| R1-2 | 单次调用、fake三元组、usage和步骤文件均携带stop_reason；OpenAI length/content_filter归一。max_tokens与schema错误共用一次修正，提示压缩完整输出；refusal一次即step_failed，errors严格为[refusal]。 | `test_anthropic_sdk_reads_stop_reason_even_with_empty_content`、`test_openai_sdk_normalizes_finish_reason`、`test_truncation_repairs_once_and_records_reason`、`test_truncation_and_json_errors_share_one_repair`、`test_refusal_never_retries_and_errors_are_enum_only`。 |
| R1-3 | 修正前回放原始assistant响应；空输出回放指定占位文本。真实system+user输入产生system,user,assistant,user。指定旧测试的文本调整因上述限制冲突待确认，其原输入/断言未改。 | 新增 `test_repair_replays_assistant_before_correction` 覆盖非空与空输出；旧JSON修正测试仍通过。 |
| R1-4 | 推演仅task/chapter/mode/brief及阶段字段；写手精确10键，去decision与外层beat_sheet；审校精确6键，归档精确5键。fake从brief.locked/dynamic读状态。A两组各第1–5章落盘步骤的user键集合完全一致，均无decision。 | `test_deliberation_payload_has_one_brief_and_only_phase_fields`、`test_a_five_chapter_writer_step_keys_match_across_arms`、`test_execution_payloads_have_only_the_required_keys`、`test_fake_reads_custom_ids_and_open_major_facts_from_brief`，以及两个r1_pilot_report输入对称性测试。 |
| R1-5 | 只对数量3及唯一、互异锚点做语义硬校验；字段类型继续验证。citation_check以归一后至少8字公共连续子串记录三类命中，剔除name/age/personality；无命中、空引文或同类命中均不拒绝。每条记录写control/insertions.json，并在report列核对表。 | `test_citation_records_eight_character_partial_matches_by_category`、`test_citation_excludes_nonfact_character_fields`、`test_citation_records_all_categories_without_requiring_three_category_coverage`、`test_insertions_require_three_distinct_anchors_even_if_each_occurs_once`、集成 `test_r1_c_bad_citations_are_persisted_and_reported_without_stopping`。 |
| R1-6 | 所有validator先生成规范化副本：整数age转串、可选null文本转空串、非closing的left缺失/null归0；knows允许字符串列表并逐条追加。生产写作走normalize_manuscript去围栏、首个非空行规范/补标题，只有空或非文本失败；保留低层严格helper给已有调用与旧测试，不在生产入口拒绝标题偏差。 | `test_integer_character_age_is_normalized_on_a_copy`、`test_optional_null_strings_are_normalized_without_mutating_source`、`test_nonclosing_missing_or_null_chapter_count_becomes_zero`、`test_archive_knows_appends_individual_strings_and_preserves_inputs`、`test_every_validator_returns_an_independent_normalized_copy`；写手 `test_manuscript_normalizes_fences_headings_and_missing_headings`、`test_writer_pipeline_uses_normalization_before_validation`。 |
| R1-7 | 罗盘原样保存seed_idea；主编setup/decision两张提示，两组同一decision提示，含五维、used_beats、新发现；提案具体性、六角色各四行清单、写手四点、审校顺序/圣经引文、档案员格式均加强，仅改提示不加语义硬校验。为同时满足审校精确keys与原始罗盘可见，审校使用临时bible包携带唯一compass，持久化圣经不改；C采用相同包。 | `test_build_setup_preserves_original_seed_idea`、`test_editor_setup_and_decision_cards_are_separate_and_identical_across_arms`、`test_deliberation_role_checklists_and_proposal_specificity`、`test_execution_role_prompts_cover_requested_checks`、`test_r1_review_envelope_preserves_canonical_bible_and_compass`。 |
| R1-8 | setup12000、decision6000、推演2500、审校/归档4000；写手保持max(4000,ceil(words×2.5))。 | 许可更新的旧token测试；新增 `test_round_one_token_limits_preserve_registry`；所有角色guard测试仍通过。 |
| O1 | 两家SDK APIConnectionError及子类、httpx/httpx2的ConnectError和RemoteProtocolError均等待5秒重试一次。 | `test_connection_failures_wait_five_seconds_and_retry_once` 覆盖8类/子类。 |
| O3 | 失败errors只保存异常类名与HTTP码；拒答例外仍仅refusal。manifest增加failed_step；异常携带step_key，stdout和report展示失败步骤；续跑修好后清空。 | `test_sdk_failure_persists_only_exception_class_http_status_and_step`、`test_successful_resume_clears_previous_failed_step`、`test_r1_failed_step_is_visible_in_manifest_stdout_and_report`。 |
| O5 | 第二个并发预算调用加5秒wait_for，预算守卫回归时会失败而非挂起。 | 原 `test_novel_router_parallel_budget_reservations_are_atomic`，原断言保留。 |
| O6 | early_end先回收F001，隔离n<m守卫。 | 原 `test_decision_end_guards_and_fields[early_end]`，仅补指定输入。 |
| O7 | compact同时移除指定全半角引号、空白，并将……/…/...归一；审校证据、C抓到匹配和citation_check都使用相同函数。 | `test_compact_normalizes_quotes_whitespace_and_ellipsis`、`test_review_uses_identical_normalization_for_body_and_evidence`、`test_r1_estimate_caveat_and_shared_evidence_normalization`。 |
| O8 | 仅循环固定的版本甲/版本乙文件名；key只读映射值，额外标签不会成为路径；映射值也只允许solo/panel。 | `test_r1_blind_file_names_are_fixed_even_with_extra_key_labels`、`test_r1_blind_mapping_values_cannot_escape_known_arms`。 |
| O9 | 估算口径新增Claude中文约1–1.35 token/字、anthropic输入上界可能偏低的原文提醒。 | `test_r1_estimate_caveat_and_shared_evidence_normalization`；三个最终estimate.md及stdout核对。 |

本轮新增用例分布：r1_router 34项、r1_schemas 108项、r1_workflow 45项、r1_pilot_report 13项，共200项。未在本单范围的O4、O10不扩展实现。

### 测试与命令输出

所有命令均在backend执行，解释器固定，且禁用Python字节码和pytest缓存。全量命令禁用dotenv并主动覆盖提供方密钥/JWT为占位字符串，未读取或打印真实值。

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
```

```text
........................................................................ [ 85%]
...............................................................          [100%]
423 passed in 2.54s
```

退出0，日志 `/tmp/novel-p0-r1-verified-tests.log`。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
```

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 3895 passed, 9 skipped, 14 warnings, 5 errors in 83.04s (0:01:23)
```

退出1，最终日志 `/tmp/novel-p0-r1-full-final-tests.log`。完整命令包含全部423项小说测试；仍只有首轮已复现的六项既有loopback bind权限问题，未出现新增失败。不是全量通过，需在可绑定本地端口的环境复验。

另按04-review对两个既有端口受限文件的范围作补充诊断，使用同样占位环境，未修改或删除任何测试：

```bash
"$PY" -m pytest -q -p no:cacheprovider \
  --ignore=tests/test_exchange_isolation.py \
  --ignore=tests/test_safe_http_deadline.py
```

```text
3886 passed, 9 skipped, 14 warnings in 80.09s (0:01:20)
```

退出0，日志 `/tmp/novel-p0-r1-filtered-tests.log`。此命令是受限环境诊断，不替代上面的完整全量命令。本机跳过数与04复核环境不同，保留实际输出，不把跳过项计作通过。

```bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-r1-verified-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-r1-verified-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-r1-verified-C --source-run /tmp/novel-p0-r1-verified-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot report --out /tmp/novel-p0-r1-verified-C
```

四条退出0。A两组各5章，B第9章end且留言已回应，C两个模型标签的fake均3/3、误报0。C三条citation_check分别命中锁定外形、当前状态、时间线；另有集成测试明确验证不合格引文不停止实验。三个run的stdout末尾就是下一节估算表，完整日志为 `/tmp/novel-p0-r1-verified-{A,B,C}.log`。

```bash
ANTHROPIC_BASE_URL=http://x PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-r1-guard
```

```text
配置或环境错误：请先 unset 这些变量：ANTHROPIC_BASE_URL
```

退出2。`rg -n 'between_tools' novel/llm_router.py` 有型号表结果；`git diff --exit-code`无输出、退出0；status没有M。所有变化仍是尚未提交的新任务文件。工作目录中原有的02/04/05及期间外部出现的06文档未编辑，06未读取。

### 更新后的三个估算表原文

以下逐字复制最终estimate.md；旧目录和初轮估算保留，不复用旧步骤缓存。

#### R1 实验 A

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| A | archivist | 10 | 42702 | 40000 |
| A | character_advocate | 10 | 31861 | 25000 |
| A | editor | 11 | 42399 | 72000 |
| A | plot_architect | 10 | 31941 | 25000 |
| A | reviewer | 10 | 44182 | 40000 |
| A | twist_designer | 10 | 31981 | 25000 |
| A | writer | 10 | 35772 | 50000 |
```

#### R1 实验 B

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| B | archivist | 9 | 35823 | 36000 |
| B | character_advocate | 18 | 63427 | 45000 |
| B | editor | 10 | 52022 | 66000 |
| B | pacing_advisor | 18 | 64633 | 45000 |
| B | plot_architect | 18 | 63571 | 45000 |
| B | reviewer | 9 | 37146 | 36000 |
| B | twist_designer | 18 | 63643 | 45000 |
| B | writer | 9 | 34115 | 36000 |
```

#### R1 实验 C

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| C | corrupter | 1 | 3689 | 2000 |
| C | reviewer | 4 | 18250 | 16000 |
```

### 待人工确认

1. R1-3指定旧测试能否最小补上初始system消息，随后只新增返修单要求的四角色断言。未经确认保留旧输入；功能和独立新回归已完成。
2. 在允许loopback bind的环境复跑完整全量并对照验收方3484条既有测试基线。本机旧六项端口权限问题不作通过处理。
3. 本轮MockTransport只验证实际SDK的请求/响应处理，不代表官方在线服务接受参数；真实提供方与质量盲评仍未运行，后续须另行授权。
4. C的citation_check是引文匹配记录，不是语义矛盾证明；作者仍需抽查。多模型组合及panel必须选提案这两项实验混杂因素仍存在，未擅改实验设计。

## 接入火山方舟

依据：`06-add-ark-provider.md`。用户已确认第1轮返修通过验收方机械验证；本次仅处理方舟增补，不改动前轮测试的输入或断言。

### 交付结果与修改文件

已加入 `ark` 提供方，支持豆包 Doubao-Seed-2.1-pro 的两个指定型号，可分配给任意智能体或实验C比较审校。默认三份实验配置原样保留。新增95项离线测试，小说测试总计 **518 passed**。三份默认dry-run均退出0，含Ark推演角色的测试内部A配置也完整生成两组各5章。

修改5个本任务文件、新增3个测试文件：

```text
修改 backend/novel/llm_router.py
修改 backend/novel/agent_pool.py
修改 backend/novel/pilot.py
修改 backend/novel/README.md
追加 docs/tasks/2026-10-15-novel-workshop/03-report.md
新增 backend/tests/test_novel_ark_router.py
新增 backend/tests/test_novel_ark_validation.py
新增 backend/tests/test_novel_ark_security.py
```

分工互不重叠：路由及MockTransport测试、配置校验及其测试、安全集成测试三个子代理并行；主代理负责README、最终验证和本报告。所有命令均在backend，使用指定 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`；没有联网、读取真实密钥、运行真实提供方、增加依赖或提交commit。

### 逐条任务落实与对应测试

| 任务 | 实现 | 对应验证 |
| --- | --- | --- |
| 1 新增ark路由 | PROVIDERS添加方舟URL与ARK_API_KEY；走OpenAI兼容分支，thinking=disabled，JSON有response_format、Markdown无该字段，显式max_tokens，timeout=300、max_retries=0，不传frequency/presence penalty。finish_reason及usage复用统一逻辑。 | `test_ark_sdk_serializes_request_and_normalizes_usage_and_finish_reason`：两型号×JSON/Markdown×stop/length/content_filter，捕获实际URL/请求体/客户端构造参数；max_tokens=4242，高于默认4k。`test_ark_finish_reason_drives_shared_repair_and_persistence`验证截断修正、拒答单次及持久化。 |
| 2 全部规格校验 | 全库搜索定位小说协议三处parse_model、agent_pool._validate_model、pilot._model_spec，全部加入ark并更新中文文案；配置校验复用parse_model白名单。其它命中为BYOK/官方交流等既有独立业务，未修改。 | `test_each_agent_can_select_either_ark_model`覆盖两个型号×全部11个角色；`test_reviewers_to_compare_accepts_either_ark_model`；`test_strict_model_syntax_reports_ark_as_an_allowed_provider`。 |
| 3 环境守卫 | 仅用到ark时检查ARK_API_KEY；缺少时只输出变量名；污染变量清单完全不变。dry-run不读取环境。 | `test_ark_guard_does_not_inspect_unrelated_provider_keys`、`test_ark_missing_key_is_rejected_before_sdk_construction`、`test_missing_ark_key_reports_only_variable_name_before_creating_run`；四污染变量参数化和UnreadableEnvironment完整dry-run。 |
| 4 型号白名单 | MODEL_ALLOWLISTS仅含ark，准确列出260915/260628；ARK_MODELS共享同一不可变集合。未知ark在配置/路由入口即报“火山方舟型号未在白名单内”，退出2，dry-run同样验证；其它提供方不新增型号限制。 | `test_model_allowlists_are_only_for_ark`、`test_ark_unknown_model_is_configuration_error_even_in_dry_run`、`test_invalid_provider_or_ark_model_cli_exits_two_before_environment`、`test_other_providers_do_not_gain_model_whitelists`。 |
| 5 估算表 | 现有报表按usage数据汇总，不固定提供方列表，Ark角色自然计入调用数、输入字符上界、角色max_tokens输出上界及成本模型行。估算口径未改变；没有内置方舟价格。 | `test_ark_internal_config_full_a_dry_run_and_accounting`逐字段核对Ark usage与estimate/cost汇总，验证无价格时无金额、外部提供价格时按给定价格计算。 |
| 6 README | 提供方清单加ark，写明ARK_API_KEY、推荐260915、往期260628、URL、关闭思考、max_tokens、白名单、任意角色/比较审校分配及价格外供。 | 文档逐项人工核对；默认配置不变的快照比对。 |
| 7 离线测试 | 新增三文件，共95项：37项路由、50项校验、8项安全集成。SDK调用只交给httpx.MockTransport；集成禁构造客户端与网络，环境整体替换成本地假映射。哨兵小实验只把单次调用替换为本地fake三元组，递归扫描输出和stdout/stderr；内部配置不新增pilot_configs。 | `test_ark_key_sentinel_never_reaches_stdout_or_output_tree`、`test_ark_internal_config_full_a_dry_run_and_accounting`、`test_ark_budget_blocks_all_calls_before_generation`，以及上述MockTransport/校验测试。 |
| 8 默认配置不改 | expA/B/C不改变模型、角色、目标、留言或任何原始字节；是否使用豆包仍由作者决定。 | 与 `/tmp/novel-p0-ark-before/novel/pilot_configs/` 逐文件字节比对，三份默认配置重新dry-run完成。 |

### 命令与输出末尾

所有测试使用 `PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`，避免产生字节码和pytest缓存。全量额外禁用dotenv，并主动用占位值覆盖四个提供方密钥、OPENAI_API_KEY和JWT_SECRET；没有检查真实环境值。MockTransport测试自行替换环境映射、禁止socket连接，只使用测试假key。

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
```

```text
........................................................................ [ 97%]
..............                                                           [100%]
518 passed in 2.36s
```

退出0；日志 `/tmp/novel-p0-ark-tests.log`。原423项测试文件逐字节保持不变，新增95项。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
ARK_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
```

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 3990 passed, 9 skipped, 14 warnings, 5 errors in 83.43s (0:01:23)
```

退出1；日志 `/tmp/novel-p0-ark-full-tests.log`。失败/错误标识与前一轮完全相同，均为已有loopback bind权限限制。通过数从3895增加95至3990，正好对应本轮新增95项；无新增失败，完整全量也未排除任何旧测试。受限项仍需在允许本地端口的环境复验。

```bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-ark-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-ark-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-ark-C --source-run /tmp/novel-p0-ark-A --dry-run
```

三条命令退出码均0：A两组各5章；B第9章归档后完结；C两个模型的fake均抓到3/3、原稿误报0。日志分别为 `/tmp/novel-p0-ark-{A,B,C}.log`。输出末尾仍为估算表，最后一行如下：

```text
A: | A | writer | 10 | 35772 | 50000 |
B: | B | writer | 9 | 34115 | 36000 |
C: | C | reviewer | 4 | 18250 | 16000 |
```

独立含Ark测试配置定义在 `test_novel_ark_security.py` 内：仅将A的plot_architect改为推荐Ark型号，运行后两组各5章，Ark对应10次提案/互评调用，所有实际调用提供方均为fake。没有新增配置文件。

```bash
grep -rn '"ark"' novel/
git diff --exit-code
git status --porcelain --untracked-files=all
```

grep可见PROVIDERS条目、MODEL_ALLOWLISTS白名单、ARK_MODELS共享引用和parse_model校验。git diff无输出、退出0；status无M。接入前快照 `/tmp/novel-p0-ark-before` 对比确认：所有已有test_novel文件、三份默认配置不变；本报告仅追加，前文原字节保留；没有修改任何其它既有业务文件。

### 待人工确认

1. 真实方舟服务的开通权限、连通性与在线参数接受情况尚未运行；本次只验证实际SDK的本地请求序列化与响应处理，后续真实调用须另行授权。
2. 是否把豆包分配给正式实验的任一角色，由作者另行决定；本单没有改默认配置。
3. 价格没有内置。真实计费及外部价格文件由作者提供，缓存定价策略不在本单扩展范围内。
4. 本地端口受限的既有全量用例需在允许loopback bind的环境复验；不将受阻项声明为通过。

## 第 2 轮返修（真跑问题）

依据：`05-fix-r2.md`。仅对作者首次真跑暴露的JSON引用、残缺审校、阻断误报和长度提示问题返修；本轮没有继续或重启任何真实运行。

### 证据与结果

只读查看了 `aborted-run1/expB/arm-panel/ch001/05-review-reviewer-r2.json` 及对应末稿。原步骤状态step_failed、尝试2次；最终响应仍能解析为JSON，但单条issue仅有category与problem，缺少evidence/fix/blocking，旧校验使整个步骤失败。

修复后，对该原始响应与原末稿直接执行纯函数离线回放，结果为：

```text
真实失败响应只读回放：passed=True，保留0条，丢弃1条，原因=字段不完整或类型错误。
```

这是schema及流程的回归结果，不代表真实模型的误报率或长度表现已重新测量。证据目录的内容哈希在返修前保存于 `/tmp/novel-p0-r2-before/evidence-sha256.json`，最终已比对全部原文件，文件列表与全部内容哈希一致；没有向证据目录写入文件。

最终小说测试 **709 passed**，即原518项加本轮191项，未减少既有用例。三个新目录的默认dry-run全部退出0。SDK与模型调用仍全部离线；没有联网、读取真实密钥、运行真实提供方、增加依赖或提交commit。

### 修改文件

修改8个本任务文件，新增5个文件：

```text
修改 backend/novel/agent_pool.py
修改 backend/novel/llm_router.py
修改 backend/novel/schemas.py
修改 backend/novel/writing.py
修改 backend/novel/README.md
修改 backend/tests/test_novel_r1_workflow.py
修改 backend/tests/test_novel_r1_pilot_report.py
追加 docs/tasks/2026-10-15-novel-workshop/03-report.md
新增 backend/novel/prompt_rules.py
新增 backend/tests/test_novel_r2_prompts.py
新增 backend/tests/test_novel_r2_schemas.py
新增 backend/tests/test_novel_r2_writing.py
新增 backend/tests/test_novel_r2_integration.py
```

三个子代理分别负责提示词/路由、审校schema、写作流程；主代理负责真实证据只读回放、端到端测试、README、全量验证和报告。同文件修改由同一负责者完成。

### 逐条落实与对应测试

| 条目 | 实现 | 对应测试 |
| --- | --- | --- |
| R2-1 JSON引用约束 | `prompt_rules.JSON_STRING_QUOTE_RULE`为唯一共享常量，原文禁止JSON字符串值内部使用英文双引号，改用「」。setup、提案/互评、裁决、审校、档案员、corrupter的schema末尾均复用；系统防注入句仍是最后一句。JSON的解析、字段和截断修正均追加同句；Markdown写手及其修正不加JSON限制。没有通过替换原始响应来伪造合法JSON。 | `test_quote_rule_is_the_requested_shared_instruction`、`test_json_schema_ends_with_shared_quote_rule`、`test_every_json_task_has_quote_rule_before_final_injection_guard`、`test_json_repair_replays_output_and_reuses_quote_instruction`、`test_markdown_repair_keeps_quoted_prose_free_of_json_restriction`。 |
| R2-2 单条残缺问题丢弃 | 只修改validate_review：顶层非对象、issues缺失/非列表仍抛ValidationError；每条issue独立检查，字段不完整、类型或枚举非法、非对象均放dropped_issues，固定原因“字段不完整或类型错误”。对象保留原字段副本，非对象包装为issue字段；其他角色仍严格校验。原有证据过滤、style/adaptation非阻断、合法可选空值归一保留。passed仅由保留的阻断问题计算。 | `test_review_missing_issue_field_is_dropped_without_mutating_source`、`test_review_wrong_issue_field_type_is_dropped`、`test_review_nonobject_issue_has_explicit_diagnostic_wrapper`、`test_review_invalid_top_structure_still_fails`、`test_review_real_run_shaped_incomplete_issue_parses_and_passes`、`test_review_mixed_issues_compute_passed_from_retained_items`；端到端 `test_live_failure_shape_is_dropped_without_a_review_retry`。 |
| R2-3 阻断与复审范围 | 提示仅允许明显前后矛盾、直接锁定设定冲突、漏核心节拍/指定伏笔三类阻断；排除同义、中文/阿拉伯数字、详略差异；knows只有明确不可能知情才算，拿不准false，每轮最多3条且按严重程度排序。writing仅在review_round>=1加入上一轮保留阻断问题的深拷贝，提示优先逐条核对修复；新问题须为上述严重情况。C仍是独立单轮，不传该字段。语义判断留给提示，没有额外添加代码语义硬校验。 | `test_review_prompt_contains_narrow_blocking_and_rereview_rules`、`test_review_revisions_receive_only_previous_retained_blocking_issues`、`test_resolved_review_stops_revisions_and_archives`、`test_nonblocking_or_unverifiable_issues_do_not_start_a_revision`；端到端 `test_revisit_uses_only_verified_previous_blockers_and_can_finish`、`test_experiment_c_stays_single_pass_without_previous_blockers`。 |
| R2-4 具体字数范围 | 每次写手payload加length_range，min=(3W+4)//5、max=8W//5、target=W，避免浮点边界。get_agent的写手提示代入相同具体数字，例如1500字→900–2400字，强调宁短勿超。长度重写提示包含上一稿去空白实测X、超出/不足及具体区间；长度接受与最终标记共用整数边界。原长度一次重写和审校两次修订上限不变。 | `test_writer_gets_concrete_integer_range_without_json_rule`、`test_each_writer_payload_has_exact_integer_length_range`、`test_inclusive_integer_boundaries_control_rewrite_and_final_flag`、`test_second_out_of_range_draft_is_flagged_and_still_archived`；端到端 `test_length_retry_persists_actual_count_and_concrete_integer_range`。 |

新增测试分布：r2_prompts 72项、r2_schemas 70项、r2_writing 45项、r2_integration 4项，共191项。所有新回归只用fake、纯函数或本地测试桩，客户端构造和网络入口被禁用。

### 既有测试与只读边界核对

仅按R2-4方向调整两份R1测试中的三个“写手payload期望键集合”：每处只新增 `length_range`，其他输入和断言原样保留。具体为 `test_novel_r1_workflow.py` 两处、`test_novel_r1_pilot_report.py` 一处。原 `test_writer_receives_scoped_complete_context_without_full_bible` 不含精确键集合，原全部断言均保留，范围数值由新增参数化用例验证。

其余既有小说测试、三份默认配置均与 `/tmp/novel-p0-r2-before` 快照逐字节核对。本报告只追加，前文原字节保留；没有改动任务单、复核报告、既有业务文件或证据产物。

### 测试命令与输出末尾

所有命令在backend执行，使用固定解释器，禁用字节码和pytest缓存。全量禁用dotenv并主动用本地占位值覆盖提供方key、OPENAI_API_KEY和JWT_SECRET；未查看实际环境值。

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
```

```text
........................................................................ [ 91%]
.............................................................            [100%]
709 passed in 3.09s
```

退出0，日志 `/tmp/novel-p0-r2-tests.log`。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
ARK_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
```

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 4181 passed, 9 skipped, 14 warnings, 5 errors in 83.28s (0:01:23)
```

退出1，日志 `/tmp/novel-p0-r2-full-tests.log`。失败/错误标识与豆包接入验收时完全相同，均为已有loopback bind权限限制；通过数由3990增加191至4181，正好对应新增191项，无新增失败。完整全量没有排除任何测试，不将受限项计为通过。

```bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-r2-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-r2-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-r2-C --source-run /tmp/novel-p0-r2-A --dry-run
```

三条命令均退出0，A两组各5章，B第9章完成归档后end，C两个模型标签对应的fake均抓到3/3、误报0。日志 `/tmp/novel-p0-r2-{A,B,C}.log`；其stdout末尾为下面更新的估算表。没有复用或改写aborted-run1的步骤、配置、usage或manifest。

### 三个dry-run估算表原文

#### R2 实验 A

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| A | archivist | 10 | 43252 | 40000 |
| A | character_advocate | 10 | 32411 | 25000 |
| A | editor | 11 | 43004 | 72000 |
| A | plot_architect | 10 | 32491 | 25000 |
| A | reviewer | 10 | 48962 | 40000 |
| A | twist_designer | 10 | 32531 | 25000 |
| A | writer | 10 | 36512 | 50000 |
```

#### R2 实验 B

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| B | archivist | 9 | 36318 | 36000 |
| B | character_advocate | 18 | 64417 | 45000 |
| B | editor | 10 | 52572 | 66000 |
| B | pacing_advisor | 18 | 65623 | 45000 |
| B | plot_architect | 18 | 64561 | 45000 |
| B | reviewer | 9 | 41448 | 36000 |
| B | twist_designer | 18 | 64633 | 45000 |
| B | writer | 9 | 34763 | 36000 |
```

#### R2 实验 C

```text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| C | corrupter | 1 | 3744 | 2000 |
| C | reviewer | 4 | 20162 | 16000 |
```

### 待人工确认

1. 提示词能否在真实模型上减少英文引号错误、审校误报和长度重写，需要作者另行授权真跑验证；本轮未联网重跑，不能据fake结果声明质量已经改善。
2. 残缺issue丢弃后的“通过”表示没有可核实的保留阻断问题，并非证明正文无矛盾；完整诊断仍在步骤文件中供抽查。
3. 旧全量端口权限受限项需在允许loopback bind的环境复验。本轮不修改或跳过它们来制造全量通过。
4. 证据目录保留原状，未覆盖旧产物；是否继续旧实验或从新目录开始真实验证，交由作者决定，本轮不自动续跑。

## 第 3 轮返修

### 实现与验收状态

按 05-fix-r3.md 的 R3-1 完成裁决回收清单规范化与报告展示。指定第12章 raw_response 的纯函数离线回放已通过：原清单 F005/F006/F008/F011 返回为 F005/F006/F008，并生成 F011「已回收」警告；ending_status 保持 end。没有对真实实验目录执行续跑。

本轮新增26项回归均通过，三个默认 dry-run 均退出0。目前不能宣称全部验收通过：一项既有测试要求不存在的 F999 必须报错，与本单“剔除并记录警告”的新要求直接冲突。返修单的唯一测试修改例外仅适用于“已回收 ID 必须失败”，不涵盖这个不存在 ID 用例，因此保持旧测试原样，并已请求作者确认是否允许最小调整。完整小说测试如实保留该失败，不跳过、不标为预期失败，也不通过额外业务错误绕过断言。

### 修改文件

修改三个文件（报告只追加），新增三个测试文件：

~~~text
修改 backend/novel/schemas.py
修改 backend/novel/report.py
追加 docs/tasks/2026-10-15-novel-workshop/03-report.md
新增 backend/tests/test_novel_r3_schemas.py
新增 backend/tests/test_novel_r3_report.py
新增 backend/tests/test_novel_r3_integration.py
~~~

三个子代理分别负责 schemas 及测试、report 及测试、离线回放与续跑集成测试；主代理负责独立真实响应回放、默认 dry-run、完整回归、边界核对与本报告。文件分工无重叠。

### 逐条落实与对应测试

| R3-1要求 | 落实方式 | 对应新增测试 |
| --- | --- | --- |
| 已回收、不存在的ID剔除，open保留 | 只在 validate_decision 的规范化副本内按当前圣经状态筛选；保留有效ID原顺序，不改原模型响应或圣经。 | test_prunes_resolved_and_unknown_preserves_open_and_inputs；test_valid_open_resolutions_keep_order_and_have_no_model_warnings。 |
| 代码生成 warnings | 返回顶层列表，逐项含 field、id、reason；原因严格为「已回收」或「不存在」。覆盖模型提供的同名字段，不把模型警告当作校验事实。 | 上述两项覆盖双警告、输入纯函数性和伪造 warnings 覆盖。 |
| 完结守卫不削弱 | 用筛选后的 resolved 清单检查每个仍 open 的 major；未回收且没有明确 leave_open 理由仍失败。 | test_end_still_rejects_open_major_after_pruning 正控；test_end_accepts_explicit_open_major_handling_after_pruning。 |
| 重复ID仍失败 | 筛除之前检查重复，覆盖open、resolved、不存在三种状态；列表和元素类型校验保留。 | test_duplicate_resolution_ids_remain_errors_for_every_status（3项）；test_malformed_resolution_fields_remain_typed_errors（9项）。 |
| unresolved_major_handling不放宽 | ID仍必须引用open伏笔；枚举、非空理由和去重检查保留，档案员校验未改。 | test_unresolved_major_handling_still_rejects_resolved_and_unknown（2项）；test_unresolved_major_handling_keeps_reason_enum_and_duplicate_guards（3项）。 |
| 每章报告展示警告 | 每章推演摘要增加字段/ID/原因表格；旧章节记录缺少warnings或空列表时保持兼容。 | test_report_lists_each_normalization_warning_in_its_chapter；test_report_without_warnings_preserves_legacy_summary（2项）。 |
| 真响应离线回放 | 只读指定证据的messages和raw_response，还原final模式上下文后校验通过，且原输入与证据字节不变。本机实际执行，未skip；证据缺失的其他环境仅跳过此真实证据用例。 | test_real_final_decision_replays_without_modifying_evidence。 |
| 失败步骤续跑与后续传递 | 在pytest临时目录用FakeLLM制造最终裁决重复ID失败，再用合法响应续跑；成功步骤字节不变，新增调用仅decision/write/review/archive各一次。writer、reviewer、archivist只收到过滤后的清单，warnings进入步骤文件、chapter_record和report，最终major清空。 | test_failed_final_decision_resumes_with_pruned_ids_and_persisted_warnings。 |

新增测试分布：schemas 21项、report 3项、integration 2项。集成回归把环境替换为空字典，并阻止真实SDK客户端及互联网socket连接；所有流水线使用FakeLLM。

### 既有测试例外与只读边界

本轮没有修改任何既有测试输入或断言，返修单允许的“已回收ID必须失败”例外实际使用数为0。待确认的唯一冲突逐条记录如下：

1. tests/test_novel_schemas.py::test_decision_end_guards_and_fields[unknown_resolution]，原输入为 continue 模式、foreshadowing_resolve=[F999]，旧断言为抛出ValidationError；新规格要求返回空清单和F999「不存在」警告。拟调整方向仅为保留原输入，将这一参数分支的期望改为剔除与警告；其他参数分支及断言全部保留。尚未获准，因此未执行该调整。

已与 /tmp/novel-p0-r3-before 核对，全部17份既有小说测试、三份默认配置与其他原模块均未改变。报告原有字节前缀保留。指定证据SHA256为 3f61098300282b73e76d52e46f232e6d5e3e51a9713802aa15e3cee733fb5cbe；修复前后该文件内容哈希相同，整个ch012目录的文件列表、大小、mtime均相同。只读检查没有改写其中任何文件。

### 测试命令与输出末尾

所有命令均在本工作树的 backend/ 下执行，解释器固定为：

~~~bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
~~~

完整小说回归（无排除项，退出1，日志 /tmp/novel-p0-r3-tests.log）：

~~~bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
~~~

~~~text
E       Failed: DID NOT RAISE ValidationError

tests/test_novel_schemas.py:183: Failed
=========================== short test summary info ============================
FAILED tests/test_novel_schemas.py::test_decision_end_guards_and_fields[unknown_resolution]
1 failed, 734 passed in 2.78s
~~~

原709项加新增26项，共735项，未减少旧用例。新增26项全部通过，唯一失败为上节列明的旧断言冲突。

全量回归主动禁用dotenv，用合成占位值覆盖各提供方密钥变量和JWT_SECRET，没有查看真实环境值；退出1，日志 /tmp/novel-p0-r3-full-tests.log：

~~~bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
ARK_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
~~~

~~~text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
FAILED tests/test_novel_schemas.py::test_decision_end_guards_and_fields[unknown_resolution]
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
2 failed, 4206 passed, 9 skipped, 14 warnings, 5 errors in 81.16s (0:01:21)
~~~

除unknown_resolution外，失败/错误的六个标识与R2全量结果相同，均可在日志定位到socket绑定127.0.0.1时报PermissionError: [Errno 1] Operation not permitted。通过数为上一轮4181+本轮新增26-冲突旧用例1=4206。因此“全量没有新增失败”和“小说测试全部通过”目前尚未满足；没有将它们记成通过，也没有跳过失败项。

指定证据的独立离线回放只调用parse_json与validate_decision，不构造路由器或SDK。除新增集成测试外，主代理另做一次纯函数回放，日志 /tmp/novel-p0-r3-replay.log 末尾：

~~~text
raw_response offline validation: PASS
chapter: 12 mode: final ending_status: end
foreshadowing_resolve: ["F005", "F006", "F008"]
warnings: [{"field": "beat_sheet.foreshadowing_resolve", "id": "F011", "reason": "已回收"}]
input unchanged: True
~~~

三个默认配置在全新的/tmp目录进行dry-run，逐条退出0；C仅依赖本次fake实验A的输出：

~~~bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-r3-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-r3-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-r3-C --source-run /tmp/novel-p0-r3-A --dry-run
~~~

A日志 /tmp/novel-p0-r3-A.log 末尾：

~~~text
| A | reviewer | 10 | 48962 | 40000 |
| A | twist_designer | 10 | 32531 | 25000 |
| A | writer | 10 | 36512 | 50000 |
~~~

B日志 /tmp/novel-p0-r3-B.log 末尾：

~~~text
| B | plot_architect | 18 | 64561 | 45000 |
| B | reviewer | 9 | 41448 | 36000 |
| B | twist_designer | 18 | 64633 | 45000 |
| B | writer | 9 | 34763 | 36000 |
~~~

C日志 /tmp/novel-p0-r3-C.log 末尾：

~~~text
| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| C | corrupter | 1 | 3744 | 2000 |
| C | reviewer | 4 | 20162 | 16000 |
~~~

三个manifest均为completed、dry_run=true。A两组各5章；B第9章end，完结后open major为空；C两个fake审校标签均抓到3/3、误报0。该结果只证明离线流程，不代表真实模型续跑已经执行或完成。

git diff --name-only无输出，git status --porcelain全部条目仍为??，没有M状态。未联网、未读真实密钥、未运行真实提供方、未改既有业务文件、未提交commit。

### 待人工确认

1. 请明确是否允许调整上述唯一unknown_resolution旧用例的断言。返修单当前文字只允许“已回收ID”例外，这项“ID不存在”的冲突不在其中；本轮已完成实现及全部其余验证，保持该测试原样等待答复。
2. 原有六项loopback bind受限测试需在允许绑定本机端口的环境复验，本轮不修改这些测试。
3. 真实实验B原目录保持原状；作者可按原配置自行续跑以验证真实最终裁决及写作归档。离线回放证明这次给定raw_response可通过，但实际续跑会重新请求失败裁决，响应内容及最终正文仍需作者检查。

### 验收方补充授权后的收尾

验收方确认上述冲突是返修单未写周全，并明确授权修改不存在F999的旧参数分支。现已逐条落实这项唯一既有测试例外：

1. 修改 backend/tests/test_novel_schemas.py::test_decision_end_guards_and_fields[unknown_resolution] 的期望，保留原continue模式、F999输入及其他参数完全不变。该分支现调用校验器并断言返回foreshadowing_resolve为空，warnings精确等于 field=beat_sheet.foreshadowing_resolve、id=F999、reason=不存在 的一条记录，然后返回；其余分支原有raises断言保留。

与 /tmp/novel-p0-flash-before 比较，旧测试文件仅新增这7行授权期望，没有改输入，也没有改其他断言。此前“待确认”第1项已解除。定向验证退出0：

~~~bash
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_schemas.py
~~~

~~~text
79 passed in 0.04s
~~~

本次作者进一步禁止访问整个 /Users/yangjing/Desktop/ai-workspace/outputs/。因此后续回归命令明确deselect仅有的真实外部证据回放用例 test_real_final_decision_replays_without_modifying_evidence，不读取其文件、目录或元数据；其余R3纯函数和Fake续跑测试照常执行。没有修改或弱化该证据用例，本次也不重复声明已做真实证据回放。

## 默认 DeepSeek 改为 flash

### 修改文件

按07-deepseek-flash.md完成默认型号切换。修改三个配置、README，新增一份测试，并把上文授权旧断言改动记录在第3轮返修内：

~~~text
修改 backend/novel/pilot_configs/expA.json
修改 backend/novel/pilot_configs/expB.json
修改 backend/novel/pilot_configs/expC.json
修改 backend/novel/README.md
新增 backend/tests/test_novel_deepseek_flash.py
授权修改 backend/tests/test_novel_schemas.py（仅unknown_resolution期望）
追加 docs/tasks/2026-10-15-novel-workshop/03-report.md
~~~

三个子代理分别负责授权测试分支、三份配置与README、新增离线测试；主代理负责全库搜索、差异审查、小说与全量回归、三个默认dry-run和本报告。分工按文件不重叠。

### 逐条落实与对应测试

| 任务 | 实现 | 对应测试或核对 |
| --- | --- | --- |
| 先全库搜索并更新默认型号 | 修改前从backend用rg检索整个仓库的deepseek-v4-pro，明确排除outputs目录和.env文件。novel下仅三配置的writer与character_advocate共6处命中，全部改为deepseek:deepseek-flash；三份配置其余字节不变。 | test_default_configs_use_deepseek_flash[A/B/C]（3项），同时检查原始配置文本没有旧型号、两角色均为flash。 |
| README/提示/示例同步 | 原README、提示和其他novel源码没有旧型号需替换；README新增按作者要求切换的原因，说明旧型号可自选、价格仍外部提供，并将Ark段“默认配置保持原样”澄清为“默认配置未采用豆包”。仓库其余业务模块、业务README与历史02-spec中的旧型号属于其他功能或历史记录，按白名单保持不动。 | 配置字节比较、全库搜索结果人工核对；不改02-spec.md。README中的旧型号是明确的兼容说明，不是默认值。 |
| DeepSeek不设白名单 | 路由实现不需要修改；MODEL_ALLOWLISTS仍仅含Ark。flash、旧deepseek-v4-pro和自定义DeepSeek型号均继续被parse_model与validate_model_settings接受。 | test_deepseek_models_remain_selectable_without_allowlist（3项）。 |
| MockTransport验证请求 | 原DeepSeek路由已经传thinking disabled及JSON response_format，保留实现。新增测试使用真实OpenAI SDK序列化，但所有HTTP均由httpx.MockTransport在内存响应；JSON、Markdown各测一项，核验URL、型号、max_tokens、消息、思考关闭、JSON格式及用量。 | test_deepseek_flash_sdk_disables_thinking_and_sets_json_format_only_for_json[json/markdown]（2项）；Markdown不携带response_format。 |

新增8项测试的自动fixture整替换os.environ，只放合成占位key，不读取或复制主机环境；同时阻断socket连接。未硬编码价格，未修改llm_router.py，未新增依赖。未访问outputs下任何目录、文件或元数据，未联网、未运行真实提供方、未提交commit。

### 测试命令与输出末尾

所有命令在本工作树backend/执行，固定解释器，禁用字节码和pytest缓存：

~~~bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_deepseek_flash.py
~~~

~~~text
8 passed in 0.64s
~~~

小说回归只排除作者本轮明确禁止访问的外部证据回放一项，未改测试文件，也没有排除其他失败项。退出0，日志 /tmp/novel-p0-flash-tests.log：

~~~bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py \
  --deselect=tests/test_novel_r3_integration.py::test_real_final_decision_replays_without_modifying_evidence
~~~

~~~text
........................................................................ [ 97%]
......................                                                   [100%]
742 passed, 1 deselected in 2.63s
~~~

本轮共743项小说用例（原735+新增8），实际执行742项全部通过；外部证据一项未执行，不计通过。已授权的unknown_resolution及其余原参数分支全部执行并通过，R3的Fake原目录续跑集成也通过。

三个默认配置在经检查不存在的新/tmp目录运行，三条命令分别退出0；C只读取本次/tmp实验A产物：

~~~bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-flash-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-flash-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-flash-C --source-run /tmp/novel-p0-flash-A --dry-run
~~~

A日志 /tmp/novel-p0-flash-A.log 末尾：

~~~text
| A | reviewer | 10 | 48962 | 40000 |
| A | twist_designer | 10 | 32531 | 25000 |
| A | writer | 10 | 36512 | 50000 |
~~~

B日志 /tmp/novel-p0-flash-B.log 末尾：

~~~text
| B | reviewer | 9 | 41448 | 36000 |
| B | twist_designer | 18 | 64633 | 45000 |
| B | writer | 9 | 34763 | 36000 |
~~~

C日志 /tmp/novel-p0-flash-C.log 末尾：

~~~text
| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| C | corrupter | 1 | 3744 | 2000 |
| C | reviewer | 4 | 20162 | 16000 |
~~~

三份manifest均为completed、dry_run=true，保存的writer与character_advocate均为deepseek:deepseek-flash。A两组各5章；B第9章end，open major为空；C两个fake审校标签均抓到3/3、误报0。

旧默认值搜索命令及结果：

~~~bash
rg -n --fixed-strings 'deepseek-v4-pro' novel/pilot_configs
~~~

无输出，rg退出1表示没有匹配，满足三份默认配置无旧型号的要求。

全量回归同样仅deselect禁止访问的外部证据一项；禁用dotenv并以合成占位值覆盖提供方key和JWT_SECRET，不查看原环境值。退出1，日志 /tmp/novel-p0-flash-full-tests.log：

~~~bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
ARK_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider \
  --deselect=tests/test_novel_r3_integration.py::test_real_final_decision_replays_without_modifying_evidence
~~~

~~~text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 4214 passed, 9 skipped, 1 deselected, 14 warnings, 5 errors in 80.43s (0:01:20)
~~~

失败/错误标识与此前六个loopback bind受限项一致，均为PermissionError: [Errno 1] Operation not permitted，没有新增失败。旧unknown_resolution失败已消除。与R3全量相比，通过数4206+新增8+修正旧断言1-未执行外部证据1=4214。受限项未改、未跳过，也未记为通过。

### 文件与边界核对

与 /tmp/novel-p0-flash-before 逐字节比较：原文件仅变动上述三配置、README、获准旧测试和报告；三配置除6处型号替换外完全相同；旧测试除授权7行外完全相同，其他既有小说测试及全部其余novel模块保持原样。新增文件只有test_novel_deepseek_flash.py；报告原始字节前缀保留，R3授权收尾及flash节均为追加。历史02-spec、其他任务文档和既有业务文件未修改。

git diff --name-only无输出，git status --porcelain仍全部为??，没有M状态。所有本轮产物在/tmp，未读写outputs下任何目录或文件，亦未对其做哈希或元数据检查。没有联网、读取真实密钥、运行真实提供方或提交commit。

### 待人工确认或复验

1. 本轮没有尚待授权的代码或测试调整，R3唯一旧断言冲突已按验收方补充授权解决。flash真实请求的可接受性沿用任务单给定的最小探测事实；本轮仅验证内存请求序列化和fake流程，未验证真实生成质量、延迟或费用。
2. 六个旧loopback bind受限项仍需在允许绑定本机端口的环境复验；禁止访问outputs的真实证据回放一项本轮未执行，需在另行允许访问证据的环境执行，不计入本轮通过数。
3. 切换默认型号会改变配置哈希。如需继续既有运行，应使用该运行原配置；采用新flash默认配置应使用新输出目录。作者自行选择后续真实实验安排，本轮未读取或续跑既有产物。

测试可移植性修复：删除 test_novel_r3_integration.py 中依赖外部真跑文件状态的 test_real_final_decision_replays_without_modifying_evidence、EVIDENCE 常量及专用导入；审计全部21份 test_novel_*.py 后确认无仓库外固定文件读取，余下/tmp字面量仅为安全拒绝输入；末章已回收ID剔除、warnings和完结守卫由现有内存数据及tmp_path/FakeLLM测试充分覆盖，无需新增用例；完整小说回归不再deselect，742 passed in 2.82s；本轮仅改该测试文件与本行报告，novel代码未改，未访问外部证据、联网、读取真实密钥或提交commit。

## critique 模式

### 实现与验收状态

按08-critique-mode.md实现R5-1至R5-5，新增expA2及150项离线测试。四份默认配置dry-run均退出0；默认merge的A/B与改动前现场生成的基线比较，步骤键、完整会议内容与最终正文全部一致。新功能回归通过，但目前不能宣称全部验收通过：R5-2要求缺失/null blocking的问题保留，而两项旧R2断言要求丢弃，直接矛盾；本单同时禁止修改旧断言，已请求这两项的最小授权，尚未改动旧测试。

### 修改文件与分工

修改8个novel文件并追加本报告；新增expA2配置和4份测试：

~~~text
修改 backend/novel/agent_pool.py
修改 backend/novel/deliberation.py
修改 backend/novel/fake_llm.py
修改 backend/novel/pilot.py
修改 backend/novel/report.py
修改 backend/novel/schemas.py
修改 backend/novel/writing.py
修改 backend/novel/README.md
追加 docs/tasks/2026-10-15-novel-workshop/03-report.md
新增 backend/novel/pilot_configs/expA2.json
新增 backend/tests/test_novel_r5_cards_fake.py
新增 backend/tests/test_novel_r5_deliberation.py
新增 backend/tests/test_novel_r5_schema_writing.py
新增 backend/tests/test_novel_r5_pilot_report.py
~~~

三个子代理分别负责提示词/Fake/新配置、推演协议、schema/写作规范化，连同各自独占的新测试；主代理负责pilot配置检查、章节统计、report展示、端到端测试、README、基线比较与完整验证。同文件多处变更由同一负责者串行完成；另由子代理只读复核其未负责的实现，未发现额外功能漏项。

### R5-1至R5-5逐条落实与对应测试

| 条目 | 实现 | 对应新增测试 |
| --- | --- | --- |
| R5-1模式范围 | panel_mode缺省merge，允许merge/critique，非法值拒绝且不修改传入配置。critique只影响A/panel和B，solo始终保留旧decision协议；原merge代码块、步骤命名、meeting键及请求结构保留。 | test_invalid_panel_modes_are_rejected_without_mutating_config；test_direct_deliberation_rejects_invalid_panel_mode；test_solo_ignores_critique_panel_mode；test_absent_panel_mode_and_explicit_merge_have_identical_protocol；test_default_and_explicit_merge_preserve_step_keys_and_meeting_structure。 |
| R5-1固定协议 | 01-plan-editor先生成solo形态初案，沿用validate_decision且无意见ID；然后并行02-critique-plan-*，最多3个在途调用并在失败时取消、等待兄弟任务；最后03-finalize-editor沿用solo校验，完整回应O/A及本章N留言。后续writer/reviewer/archive接口不改。 | test_critique_runs_plan_then_parallel_advisors_then_finalize；test_plan_uses_solo_validation_before_any_advisor_runs；test_finalize_requires_exactly_one_response_to_every_objection_and_alternative（O/A漏答及重复正控）；test_advisor_concurrency_is_limited_to_three；test_all_advisor_calls_are_cancelled_and_drained_if_one_fails；test_experiment_b_uses_critique_protocol。 |
| R5-1意见校验与编号 | validate_critique_plan要求1–3条合法major/minor意见及非空target/problem/suggestion、keep；仅twist强制非空alternative，其他角色可缺失或为空。80–200字按本单校验列表仅作为提示指导。代码按配置顺序分配全部O再全部A，不受完成顺序影响；纯空白alternative不分配A。不打分、不计算均分。 | test_critique_plan_accepts_one_to_three_actionable_objections；test_critique_objection_requires_all_four_fields；test_critique_plan_objection_envelope_and_bounds；test_twist_critique_requires_nonempty_text_alternative；test_non_twist_critique_allows_omitted_or_empty_alternative；test_ids_follow_configuration_order_even_when_advisors_finish_in_reverse；test_whitespace_only_optional_alternative_does_not_get_an_a_id。 |
| R5-1卡片/Fake/报告 | plan与finalize独立卡片共享裁决结构和创作约束；finalize强调本章最好写法、只吸收有效意见、major改或说明理由、认真评估替代方向及采纳决定。critique_plan共享schema并保留全部既有顾问视角。Fake支持三个新task且旧task输出保持。meeting保存mode/brief/plan/critiques/objections/decision；报告展示初案、保留建议、严重度与改法、A全文、逐条回应和8个细纲字段的前后差异。 | test_plan_and_finalize_have_distinct_creative_responsibilities；test_critique_card_preserves_each_role_perspective_and_shared_contract；test_fake_new_editor_tasks_satisfy_final_solo_decision_schema；test_default_decision_fake_still_selects_a_proposal_and_responds_as_before；test_critique_report_displays_plan_severity_alternative_replies_and_changes。 |
| R5-2默认非阻断 | 单条只缺blocking或为null且其他字段/证据合法时，规范化副本置false并加blocking_defaulted=true；代码清除模型自带同名标记。其他字段缺失或错误、无效证据仍丢弃。任一轮全部issue丢弃且至少一条时加review_degraded，空issues或仍有保留问题不加。 | test_review_defaults_only_missing_or_null_blocking_to_nonblocking；test_missing_other_review_fields_still_drops_issue 正控；test_invalid_nonnull_blocking_is_not_defaulted；test_defaulted_review_still_requires_real_body_evidence；test_blocking_defaulted_marker_is_owned_by_validator；test_all_review_issues_dropped_marks_chapter_degraded；test_empty_or_partly_retained_review_does_not_mark_degraded；test_later_review_round_can_mark_chapter_degraded。 |
| R5-2章节统计 | chapter_record新增review_dropped_issues和review_blocking_defaulted，跨审校轮数累计；后者计保留问题中由代码默认的条数。报告每章显示两项数字，旧记录缺字段时兼容为0。 | test_review_diagnostics_are_saved_and_reported_for_each_arm（缺/null默认、全丢弃、合法空3项）；test_legacy_records_without_diagnostic_counts_still_generate_report。 |
| R5-3标题 | normalize_manuscript识别阿拉伯及常见中文数字，首行统一规范标题；紧接且只隔空行的同章同名标题仅删除一行，正文其他部分不改；异章标题原文保留并前插规范首行。 | test_chinese_and_arabic_chapter_heading_is_canonical；test_adjacent_duplicate_title_removes_only_that_one_line；test_wrong_chapter_heading_is_preserved_after_inserting_correct_heading；test_nonduplicate_or_nonadjacent_heading_is_preserved。 |
| R5-4主编准则 | REVELATION_RULE唯一常量保存任务单原句，decision、plan、finalize均逐字出现；不增加代码语义硬校验。 | test_each_editor_creation_task_contains_exact_revelation_rule；test_a2_all_editor_cards_have_the_exact_one_reveal_rule 直接检查solo decision及panel plan/finalize实际系统提示。 |
| R5-5新实验 | expA2原文seed、50–70章/2000字、适配限制、两组各5章、空留言、模型规格全部按单配置；A2仍为experiment=A，blind沿用随机甲乙映射且文件只含正文。 | test_exp_a2_config_has_exact_requested_story_models_and_arms；test_a2_five_chapters_use_plan_consultants_finalize_and_keep_solo；test_a2_writer_payload_keys_are_identical_for_both_arms。 |

新增测试分布：schema/writing 92项、cards/fake 22项、deliberation 20项、pilot/report 16项，共150项。新测试只读取仓库配置和各自tmp_path生成的数据，客户端与网络入口被测试桩阻止，环境使用空映射或合成占位值；没有固定外部文件依赖。

### merge兼容与边界核对

源码修改前先快照到/tmp/novel-p0-r5-before，并用旧代码在新的/tmp/novel-p0-r5-before-A、-B生成基线。修改后用相同三份原配置重跑A/B/C，A/B比较结果保存在/tmp/novel-p0-r5-merge-comparison.log：

~~~text
A: 71 step keys identical; 10 complete meeting values and chapter manuscripts identical
meeting keys: ['brief', 'decision', 'objections', 'proposals', 'reviews', 'scores']
B: 109 step keys identical; 9 complete meeting values and chapter manuscripts identical
meeting keys: ['brief', 'decision', 'objections', 'proposals', 'reviews', 'scores']
PASS: merge compatibility against pre-change runs, not only explicit/default mode comparison
~~~

除R5-4明确要求追加的主编提示、R5-2要求的章节审校诊断和报告展示外，默认merge的推演行为不变。旧merge会议未添加mode字段或任何其他键；critique会议使用独立结构。写手payload键集合两组完全相同，执行层没有混入初案或顾问意见。

全部21份既有小说测试与快照逐字节相同；旧expA/B/C配置也逐字节相同。未修改历史任务单、既有业务文件、路由器、预算、缓存或盲读映射逻辑。报告原有字节前缀保留。所有本轮运行产物在/tmp；没有访问outputs目录、外部真跑证据或Fiona主检出的文件数据（仅按要求使用其固定Python解释器）。

### 尚待授权的旧断言冲突

本轮实际修改的旧测试数为0。以下两项旧测试输入与R5-2新规则直接冲突，已请求只调整对应分支期望、保留输入和其他断言的授权，尚未执行：

1. tests/test_novel_r2_schemas.py::test_review_missing_issue_field_is_dropped_without_mutating_source[blocking]：原断言要求缺blocking的合法问题丢弃；新要求是保留blocking=false并标记blocking_defaulted=true。
2. tests/test_novel_r2_schemas.py::test_review_wrong_issue_field_type_is_dropped[blocking-None]：原断言要求blocking=null丢弃；新要求同样是默认false并保留。其他非null错误类型仍按原规则丢弃。

未为绕过旧断言而按模式、调用来源或测试环境分支，也未修改输入、跳过用例或添加xfail。这两项保留为实际失败，因此“小说测试全部通过”和“全量无新增失败”当前尚未满足。

### 测试命令与输出末尾

所有命令在本工作树backend/执行；解释器固定、禁用字节码及pytest缓存，不排除任何用例：

~~~bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
~~~

~~~text
=========================== short test summary info ============================
FAILED tests/test_novel_r2_schemas.py::test_review_missing_issue_field_is_dropped_without_mutating_source[blocking]
FAILED tests/test_novel_r2_schemas.py::test_review_wrong_issue_field_type_is_dropped[blocking-None]
2 failed, 890 passed in 3.58s
~~~

退出1，日志/tmp/novel-p0-r5-tests.log。原742项加新增150项，共892项，未减少任何旧用例；所有新增用例均通过，失败仅为上节两处旧断言冲突。端到端新文件单独运行结果为16 passed in 1.24s，日志/tmp/novel-p0-r5-pilot-report-tests.log。

全量回归禁用dotenv并用合成占位值覆盖提供方key及JWT_SECRET，没有查看原值：

~~~bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
ARK_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
~~~

~~~text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
FAILED tests/test_novel_r2_schemas.py::test_review_missing_issue_field_is_dropped_without_mutating_source[blocking]
FAILED tests/test_novel_r2_schemas.py::test_review_wrong_issue_field_type_is_dropped[blocking-None]
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
3 failed, 4362 passed, 9 skipped, 14 warnings, 5 errors in 85.20s (0:01:25)
~~~

退出1，日志/tmp/novel-p0-r5-full-tests.log。除了上述两项旧断言冲突，失败/错误的六个标识与此前loopback bind权限受限项相同，均为绑定127.0.0.1时报PermissionError: [Errno 1] Operation not permitted。通过数为上轮4214+新增150-原来通过的冲突用例2=4362；没有其他新增失败，受限项未改动或跳过。

### 四份配置dry-run

四条命令分别退出0，均为fake模式。A、B、A2分别在独立的新目录运行，C只读取本次A产物：

~~~bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-r5-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-r5-B --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-r5-C --source-run /tmp/novel-p0-r5-A --dry-run
PYTHONDONTWRITEBYTECODE=1 "$PY" -m novel.pilot run --config novel/pilot_configs/expA2.json --out /tmp/novel-p0-r5-A2 --dry-run
~~~

A日志/tmp/novel-p0-r5-A.log末尾：

~~~text
| A | reviewer | 10 | 48962 | 40000 |
| A | twist_designer | 10 | 32531 | 25000 |
| A | writer | 10 | 36512 | 50000 |
~~~

B日志/tmp/novel-p0-r5-B.log末尾：

~~~text
| B | reviewer | 9 | 41448 | 36000 |
| B | twist_designer | 18 | 64633 | 45000 |
| B | writer | 9 | 34763 | 36000 |
~~~

C日志/tmp/novel-p0-r5-C.log末尾：

~~~text
| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| C | corrupter | 1 | 3744 | 2000 |
| C | reviewer | 4 | 20162 | 16000 |
~~~

四份manifest均为completed且dry_run=true。A两组各5章；B第9章end、open major为空；C两个fake审校标签各抓到3/3、误报0；A2两组各试写5章，panel每章均有plan、3份critique-plan及finalize，solo保持decision，未产生panel提案或评分步骤。

### expA2 dry-run估算表原文

以下同时是/tmp/novel-p0-r5-A2.log的stdout末尾和/tmp/novel-p0-r5-A2/estimate.md全文。A2的experiment仍为A，所以表格实验列为A：

~~~text
真实运行 token 上界估算（按本次 dry-run 调用轨迹）

估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。

| 实验 | 角色 | 调用次数 | 输入 token 上界 | 输出 token 上界 |
| --- | --- | --- | --- | --- |
| A | archivist | 10 | 43252 | 40000 |
| A | character_advocate | 5 | 14933 | 12500 |
| A | editor | 16 | 63859 | 102000 |
| A | plot_architect | 5 | 14963 | 12500 |
| A | reviewer | 10 | 49032 | 40000 |
| A | twist_designer | 5 | 14983 | 12500 |
| A | writer | 10 | 36582 | 50000 |
~~~

这是本次fake调用轨迹的估算，共61次调用；不能据此断言真实调用次数、费用、创作质量或盲读结果。原A仍为71次调用；critique减少顾问调用次数，同时增加主编初案与定稿两阶段。

### 待人工确认

1. 需要明确是否允许仅调整上文两处旧R2断言期望，输入、其他字段及其余断言不变。本单R5-2的新行为已经实现，但“既有测试的输入和断言不得修改”的红线阻止同步更新这两处分支；在得到明确授权前不改它们，也不宣称验收全通过。
2. 六项旧端口绑定受限测试仍需在允许loopback bind的环境复验，本轮不修改它们。
3. A2真实故事质量、顾问意见是否改善solo及盲读结果，需要作者安排后续真实实验；本轮只完成离线实现与fake验证，未访问outputs、未运行真实提供方。审校默认非阻断和review_degraded属于诊断信息，作者可据报告抽查。
4. 全部新代码和测试都在白名单；git status --porcelain没有M状态，未提交commit。无其他待定实现选择，缓存、预算及原三份配置保持原样。

### 验收方补充授权后的收尾

验收方确认08任务单遗漏这两处旧断言例外，已明确授权只更新缺blocking和blocking=None分支的期望。现将「尚待授权的旧断言冲突」中的两项逐条收尾，先前待确认第1项已解除：

1. backend/tests/test_novel_r2_schemas.py::test_review_missing_issue_field_is_dropped_without_mutating_source[blocking]：原有删除blocking字段的输入不变，该分支现断言保留原问题、blocking=false、blocking_defaulted=true、dropped_issues为空、passed=true。其他缺字段分支原完整结果断言保留在else，所有分支仍公共执行data==before。
2. backend/tests/test_novel_r2_schemas.py::test_review_wrong_issue_field_type_is_dropped[blocking-None]：原有blocking=None输入不变，该分支现断言保留原问题、blocking=false、blocking_defaulted=true且无丢弃项。其他错误类型分支的issues为空及丢弃内容断言保留在else；passed=true及report==before仍对全部分支公共执行。

与/tmp/novel-p0-r5-authorized-before快照及AST逐项比较，参数化输入、调用前数据构造、其他分支原断言、源数据不变断言均保留。仅修改上述测试文件，并在本节追加本次收尾；其余24份既有小说测试及所有novel生产代码、配置、提示词和估算表不变。没有访问outputs、联网、读取真实密钥、运行真实提供方或提交commit。

定向验证在backend执行，退出0：

~~~bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_r2_schemas.py
~~~

~~~text
......................................................................   [100%]
70 passed in 0.03s
~~~

完整小说回归不排除或跳过任何用例，退出0，日志/tmp/novel-p0-r5-authorized-tests.log：

~~~bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
~~~

~~~text
........................................................................ [ 96%]
............................                                             [100%]
892 passed in 3.79s
~~~

全量回归同样不排除任何用例，禁用dotenv并用合成占位值覆盖提供方key和JWT_SECRET，不读取真实值；退出1，日志/tmp/novel-p0-r5-authorized-full-tests.log：

~~~bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
DASHSCOPE_API_KEY=novel-offline-placeholder \
DEEPSEEK_API_KEY=novel-offline-placeholder \
ANTHROPIC_API_KEY=novel-offline-placeholder \
ARK_API_KEY=novel-offline-placeholder \
OPENAI_API_KEY=novel-offline-placeholder \
JWT_SECRET=novel-offline-test-secret-0123456789 \
"$PY" -m pytest -q -p no:cacheprovider
~~~

~~~text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 4364 passed, 9 skipped, 14 warnings, 5 errors in 80.09s (0:01:20)
~~~

剩余六个失败/错误与此前原有loopback bind权限受限项完全一致，均为绑定127.0.0.1时的PermissionError: [Errno 1] Operation not permitted；没有新增失败。两项旧R2断言冲突均消除，完整小说892项全部通过，全量通过数由4362增加2至4364。没有待授权的测试调整；旧端口受限项仍需在允许绑定本机端口的环境复验，不将其计为通过。本轮没有生产代码变更，原四份dry-run和expA2估算表保持有效；报告此前内容保留，仅在critique模式内追加授权收尾，未提交commit，git状态无M。

真跑前两处小修（04-review-r5建议1/2）：schemas.py将alternative加入null→空串可选字段规范化，非反转顾问显式null通过、反转设计师null/空串仍失败；agent_pool.py仅将finalize的max_tokens提高至8000，plan及solo decision仍为6000；新增test_novel_r5_alternative_null.py和test_novel_r5_finalize_tokens.py各一条测试并通过，全部数据在内存构造且验证输入/注册表不被修改；验收方补充授权后，仅将test_novel_r5_cards_fake.py::test_new_editor_cards_use_solo_shape_and_isolated_registry的finalize分支max_tokens期望改为8000，plan分支原断言及其余输入、断言全部保留；完整小说回归最终为894 passed in 3.43s（/tmp/novel-p0-r5-tweaks-authorized-tests.log），无跳过或排除，原冲突已消除；其余旧测试原样，未访问outputs、联网、读取真实密钥、运行真实提供方或提交commit。
