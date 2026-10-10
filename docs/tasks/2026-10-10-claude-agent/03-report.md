# Claude 智能体模式实施与验收报告

任务日期：2026-10-10。依据 `02-spec.md`，授权后直接实施。使用三个继承主代理模型与推理档位的子代理，按文件不重叠分工；主代理负责路由、生图执行适配、集成测试和验收。未修改受保护文件、任务前测试或依赖清单，`conftest.py` 仅新增指定一行。

## 1. 文件变更

| 文件 | 变更 |
| --- | --- |
| `backend/byok/client.py` | 独立智能体请求入口、缓存、多模态/工具结果消息、服务器工具版本映射、最终 SDK 消息 |
| `backend/services/claude_agent.py`（新增） | 多步工具循环、预算/并发/心跳、隐私约束、来源卡、累计计费/用量与一次落库 |
| `backend/services/chat_service.py` | 每轮开关与启用条件、指定位置路由、生图延迟落库适配，旧调用契约保留 |
| `backend/tests/conftest.py` | 仅新增 `os.environ.setdefault("FIONA_CLAUDE_AGENT", "0")` |
| `backend/tests/test_claude_agent_client.py`（新增） | 真实 SDK 的离线 SSE 及写死旧请求 kwargs 回归 |
| `backend/tests/test_claude_agent_runtime.py`（新增） | 工具循环、计费、落库、来源、隐私、预算、取消与锁 |
| `backend/tests/test_claude_agent_routing.py`（新增） | 每个启用条件、关闭开关后的两条事件序列、生图适配 |
| `backend/tests/test_claude_agent_integration.py`（新增） | 真实 SDK 经 run_chat 的天气→生图→作答/错误，及看图+搜索免费结算 |
| `backend/tests/test_claude_agent_frontend.py`（新增） | Node 执行 SSE 分支、React 静态渲染、旧分支写死 SHA256、设置文案 |
| `backend/tests/test_claude_agent_docs.py`（新增） | 六份文档关键说明、环境变量默认值与路径约束 |
| `frontend/app/page.tsx` | `append === true` 卡片追加到 `cards`，保留文字、旧卡与朗读队列 |
| `frontend/components/ChatBubble.tsx` | 共用天气/通用卡渲染；文字后按序渲染 `cards`；联网搜索仅显示来源 |
| `frontend/components/ChatModelSection.tsx` | 生图说明后追加规格逐字文案，并同步相关数据流/计费说明 |
| `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example` | 同步智能体条件、开关、数据流、计费、天气城市规则、全部上限与局限 |
| `docs/tasks/2026-10-10-claude-agent/03-report.md`（新增） | 本报告 |

`02-spec.md` 为任务开始前已有的未跟踪文件，没有修改。

## 2. 与规格逐项对应

| 规格 | 实现与验证 |
| --- | --- |
| §1 开关/条件/位置 | 默认开启、字面 0 关闭、非法值一次告警、每轮读取；chat/无 high 或 possible 危机/有效已启用 Anthropic/已预扣条件全部落实。入口在危机、面板和缺参考图引导后、旧生图开关前；未命中时继续旧路由。关闭开关的 friend/mirror 事件写死比对。 |
| §2 路由 | 清除既有 pending，智能体不写 pending；有图固定 friend 并跳过 detect_mode 和平台视觉模型；无图按现有 detect_mode；mirror 转交现有不带工具的流；成功保存且无 error 才运行普通 BYOK followups。 |
| §3.1 请求 | 独立 `open_agent_stream` 保留旧入口 kwargs；系统提示账号脱敏、工具说明在唯一末尾安全规则前；ephemeral system/末块缓存；北京时间→当前图→原文顺序；字符串历史与摘要保留；三个模型映射、eager_input_streaming、auto/禁止客户端并行、端点/beta/fallback/effort/token 规则落实，无额外 thinking/temperature。 |
| §3.2 循环 | 流文字后读取真实 SDK final；tool_use 只取最后 fallback 后首个客户端工具，回灌对应 assistant/tool_result；pause 原样续传最多 2 次；max_tokens/refusal 沿用旧语义；4 次工具后只给一次最终作答机会；入口开始总预算 240（60–290）秒、请求取较小预算、8000/4000 字；整轮用户锁、逐请求全局槽、工具释放槽、10 秒重获限制及各类心跳；byok_chat 仅计一次。 |
| §3.3 工具 | 仅五种客户端工具；复用现有 execute_intent/run_slow 和图片执行器；天气规范化、仅本轮或最近三条原始 user 内容授权，每日上限；仅回灌文字要点/失败原因/来源标题/热榜前十；本轮成功图后拒绝第二张；日志/trace 不记录参数。 |
| §3.4 工具说明 | 规格全文逐字使用，并位于安全规则之前；测试锁定文本与顺序。 |
| §3.5 搜索来源 | 仅读取最终 SDK 搜索/网页读取结果块，含 fallback 前已实际收到的来源；公网 HTTP(S) 校验、去重、标题 80 字、最多五条，追加 web_sources 卡；正文链接不提取；usage.server_tool_use 两个请求次数缺字段记 0。 |
| §3.6 结算/保存/错误/trace | 不追加预扣，平台成功非 stale 卡或成功图以 OR 累加结算，纯文字/看图/服务器搜索退款；一条 assistant 按产出顺序保存卡片摘要、图片说明及 image_path；图输入摘要取全部 Claude 文字前 120 字；中途错误先保存已交付内容再 error，空交付不保存；单次 reply_model；完整 agent/byok trace 与累计用量；取消清理未保存图片和释放槽/锁。 |
| §4 前端 | append 分支只追加 cards，不改 content/cardData 或清朗读；非 append 主体的写死 SHA256 回归通过；复用天气/通用/来源渲染，web_sources 固定标题且仅来源；设置页逐字文案正确。 |
| §5 文档 | 六文件均同步全部条件、两变量、图片/工具结果送 Anthropic、服务器搜索计入用户额度、结算规则、城市规则、4 次/240 秒/8000 字/一张图，以及历史图仅摘要、mirror 无工具、危机退出和卡片不落库。 |
| §6 约束 | 先取得新测试失败再改对应代码；新增六个测试模块采用模块级 socket/DNS 硬拦截；真实 Anthropic 1.12.1 + httpx2.MockTransport 覆盖 tool_use、server_tool_use/web_search_tool_result、pause_turn、fallback、refusal、max_tokens；新测试不依赖 git 历史；全程离线，无安装包、启动服务、build 或 dev。 |
| §7 验收 | 下节记录全部实际命令、输出与退出码，环境限制和开启开关后的旧预期差异逐项列出。 |

## 3. 测试先行记录

| 测试组 | 改代码前的实际结果 | 退出码 |
| --- | --- | --- |
| client | `24 failed, 4 passed in 1.03s`；缺少新入口，四项旧 kwargs 期望已通过 | 1 |
| runtime | `35 errors`；`ModuleNotFoundError: services.claude_agent` | 1 |
| routing/图片适配 | `15 failed, 2 passed in 1.00s`；缺少启用 helper、路由和 agent_result 参数 | 1 |
| frontend/docs | `12 failed, 21 passed in 0.83s`；追加卡、渲染、设置文案和文档缺失 | 1 |
| 集成 | `3 failed in 1.05s`；智能体路径尚未完成 | 1 |
| 交叉审查新增回归 | late 图片取消 1 failed；失败原因/fallback 来源 2 failed；整轮锁/预算 2 failed；路由挂起预算 1 failed；上限作答拒答 1 failed；镜子/资源异常透传 3 failed；修复前均退出 1 | 1 |

在核验夹具后，真实 SDK 集成测试另抓到图片前换行在文本裁剪重建时丢失：`2 failed, 1 passed in 1.08s`，退出 1；修改生图适配器的智能体 SSE 前缀后 `20 passed in 0.99s`，退出 0。

## 4. 最终验收实际输出与退出码

验收使用仓库已有 `backend/.venv`，把其 bin 加到 PATH 后执行规格的 `python` 命令。没有安装或更新依赖。测试进程及子进程额外加载临时 socket/DNS 拦截器；npx 设置离线模式并使用已安装本地工具。命令输出中的本机绝对路径已替换为仓库相对路径或占位符，以满足 §5 文档路径约束；其余输出保留。临时拦截器未加入仓库。

### 4.1 验收汇总

| 项目 | 实际结果 | 退出码 |
| --- | --- | --- |
| 允许文件范围 / 受保护文件零 diff / 既有测试唯一一行 | 均符合 | 0 |
| 默认完整 `python -m pytest -q` | `1 failed, 3411 passed, 6 skipped, 14 warnings, 5 errors in 101.94s (0:01:41)` | 1 |
| 开启完整 `FIONA_CLAUDE_AGENT=1 python -m pytest -q` | `56 failed, 3356 passed, 6 skipped, 14 warnings, 5 errors in 98.47s (0:01:38)` | 1 |
| 默认排除六个端口受限用例复验 | `3411 passed, 6 skipped, 6 deselected, 14 warnings in 101.66s (0:01:41)` | 0 |
| 开启排除六个端口受限用例复验 | `55 failed, 3356 passed, 6 skipped, 6 deselected, 14 warnings in 101.96s (0:01:41)` | 1 |
| 本任务新增测试 | `129 passed in 3.43s` | 0 |
| `python -m pip check` | `No broken requirements found.`（附缓存权限 warning） | 0 |
| `npx tsc --noEmit` | 无输出，0 errors | 0 |
| `npx eslint .` | `25 problems (0 errors, 25 warnings)` | 0 |
| `git diff --check` | 无输出 | 0 |

默认全量非零退出仅来自下列六个回环 bind EPERM；排除同一组用例后全部通过。开启全量中除同一组环境限制外，55 个失败逐条对应旧 Anthropic 路由预期，见 4.3；新测试全部通过，DeepSeek、平台和危机路径没有额外失败。原首次开启验收还发现两条 mirror 保存异常被改写的实际兼容问题，已先新增失败回归后修复；最终这两条既有用例通过，不列为允许差异。

### 4.2 回环端口环境限制

以下六项在默认、开启两次完整验收中均为 `PermissionError: [Errno 1] Operation not permitted`，发生在绑定 `127.0.0.1`、端口 0 时。不是智能体逻辑失败，也未修改测试。

- `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`
- `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`
- `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline`
- `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work`
- `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline`
- `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch`

另有六个 BYOK 回环 race/watchdog 参数例由其既有测试自行 skip，详见实际输出；两组总计 12 项需要可绑定回环的环境补跑。

<details>
<summary>python -m pytest -v -rs tests/test_byok_client.py -k loopback；退出码 0</summary>

````text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0 -- ./backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: ./backend
plugins: anyio-4.14.2
collecting ... collected 130 items / 124 deselected / 6 selected

tests/test_byok_client.py::test_r1_watchdog_real_loopback[deepseek] SKIPPED [ 16%]
tests/test_byok_client.py::test_r1_watchdog_real_loopback[anthropic] SKIPPED [ 33%]
tests/test_byok_client.py::test_r2_loopback_interrupt_race[watchdog-deepseek] SKIPPED [ 50%]
tests/test_byok_client.py::test_r2_loopback_interrupt_race[watchdog-anthropic] SKIPPED [ 66%]
tests/test_byok_client.py::test_r2_loopback_interrupt_race[cancel-deepseek] SKIPPED [ 83%]
tests/test_byok_client.py::test_r2_loopback_interrupt_race[cancel-anthropic] SKIPPED [100%]

=========================== short test summary info ============================
SKIPPED [2] tests/test_byok_client.py:652: R1-6 loopback bind is denied by sandbox permissions
SKIPPED [4] tests/test_byok_client.py:882: R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun
====================== 6 skipped, 124 deselected in 0.89s ======================
````

</details>

### 4.3 开关开启后的全部旧预期差异

共 55 项。旧夹具只桩 `chat.open_reply_stream`，没有桩新增 `open_agent_stream`。因此新的 friend 请求由硬离线守卫阻止（connection），或测试 BYOK 配置不可用（unavailable），而不会执行旧夹具提供的文字/异常/工具调用；这不是发出真实网络请求。涉及 pending 的 seed/补参、原生生图、平台看图和镜子判定变化分别由对应规格明确要求。新 SDK/运行时/集成测试另行覆盖新入口的成功和失败行为。

| 失败用例 | 实际原因 | 对应规格 |
| --- | --- | --- |
| `tests/test_byok_chat.py::test_reply_uses_dedicated_pool_and_refunds[10-friend]` | 余额 10 friend 满足智能体条件；新入口绕过只桩旧 open_reply_stream 的夹具，旧调用计数为 0。 | §1、§3.1 |
| `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[weather]` | 天气由 Claude 调度，不再按旧平台意图桩直接执行；新 Claude 请求被离线守卫拒绝。 | §2.3、§3.3 |
| `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image]` | 生图由 Claude 客户端工具调度，旧识别器/单轮回复桩未执行，新入口未打桩。 | §1、§2.3、§3.3 |
| `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[vision]` | 当前图片直接给 Claude；旧平台视觉桩不执行，直接看图免费；新 Claude 入口未被旧夹具打桩。 | §3.1、§3.6 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure0]` | 旧入口注入的 401 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure1]` | 旧入口注入的 404 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure2]` | 旧入口注入的 429 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure3]` | 旧入口注入的 超时 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure4]` | 新请求的离线连接错误文案与旧注入连接错误相同，但旧入口未调用，旧计数断言失败。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure5]` | 旧入口注入的 NeedsReentryError 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure6]` | 旧入口注入的 ByokUnavailableError 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_empty_and_refusal_semantics[True-True]` | 旧单轮流的部分文本/拒答桩未执行；新请求未被该桩接住，先发生离线连接错误。 | §3.1、§3.2 |
| `tests/test_byok_chat.py::test_daily_cap_and_dev_mode_bypass` | 第一次新入口请求未打桩，未到旧预期 done；每日次数仍每轮一次，由新测试验证。 | §3.1、§3.2 |
| `tests/test_byok_chat.py::test_disconnected_byok_stream_closes_and_releases_slot` | 直接构造的已启用 Anthropic ctx 改走新入口，首事件为离线连接错误，旧流的断开模拟没有开始。 | §1、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_topic-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_cancel-10]` | 智能体先清 pending，并由 Claude 回复，旧平台免费取消的固定事件序列不再用于此付费智能体轮。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]` | 智能体清 pending，不走旧平台补参；天气/生图改由 Claude 工具调度，旧桩未接住新请求。 | §2.1、§3.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_cancel-10]` | 智能体先清 pending，并由 Claude 回复，旧平台免费取消的固定事件序列不再用于此付费智能体轮。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_fill-10]` | 智能体清 pending，不走旧平台补参；天气/生图改由 Claude 工具调度，旧桩未接住新请求。 | §2.1、§3.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_chat-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]` | 失败发生在余额 10 的前置 seed：智能体不通过平台识别创建 pending；带 -0 的例子尚未降余额，零余额实际请求没有执行。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]` | 失败发生在余额 10 的前置 seed：智能体不通过平台识别创建 pending；带 -0 的例子尚未降余额，零余额实际请求没有执行。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_thanks-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_discussion-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_question-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_reply_persistence_failure_uses_platform_error[friend]` | friend 新入口未打桩，保存前先连接失败；旧保存失败注入未触发。镜子对应兼容问题已修复，最终不再失败。 | §3.1 |
| `tests/test_byok_chat.py::test_r1_deleted_conversation_during_reply_is_platform_failure[friend]` | friend 不创建旧 DeletedReply，因此旧删除模拟未执行。镜子对应兼容问题已修复，最终不再失败。 | §3.1 |
| `tests/test_byok_chat.py::test_r2_paid_weather_pending_routing_matches_platform` | 已配置 Claude 清 pending 并自行调度，与未配置的平台旧补参快照不同；新请求未被旧入口桩接住。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-算了]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-换个话题]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-从家出发]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[web_search-算了]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[算了-route]` | 余额 10 的 Anthropic seed 不再通过平台意图识别创建 pending，因此与平台旧补参快照不同。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[算了-web_search]` | 余额 10 的 Anthropic seed 不再通过平台意图识别创建 pending，因此与平台旧补参快照不同。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[换个话题-route]` | 余额 10 的 Anthropic seed 不再通过平台意图识别创建 pending，因此与平台旧补参快照不同。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[换个话题-web_search]` | 余额 10 的 Anthropic seed 不再通过平台意图识别创建 pending，因此与平台旧补参快照不同。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[从家出发-route]` | 余额 10 的 Anthropic seed 不再通过平台意图识别创建 pending，因此与平台旧补参快照不同。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[从家出发-web_search]` | 余额 10 的 Anthropic seed 不再通过平台意图识别创建 pending，因此与平台旧补参快照不同。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r3_paid_weather_topic_exit_matches_unconfigured_platform` | 已配置 Claude 清 pending 并自行调度，与未配置的平台旧补参快照不同；新请求未被旧入口桩接住。 | §2.1、§2.3 |
| `tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-opus-5-5]` | 旧测试只桩 open_reply_stream 并期待 native generate_image；新入口未被桩且测试 BYOK 环境不可用，replies 为空。 | §1、§2.3、§3.1 |
| `tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-sonnet-5-5]` | 旧测试只桩 open_reply_stream 并期待 native generate_image；新入口未被桩且测试 BYOK 环境不可用，replies 为空。 | §1、§2.3、§3.1 |
| `tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-haiku-5-5]` | 旧测试只桩 open_reply_stream 并期待 native generate_image；新入口未被桩且测试 BYOK 环境不可用，replies 为空。 | §1、§2.3、§3.1 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[candidate]` | detect_mode 桩返回 mirror；新路径按模式转交既有无工具镜子流，旧预期绕过模式判定并生图不再成立。 | §2.2、§2.3 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent]` | friend 不调用平台意图识别或旧 native 入口；旧生图桩未执行，新入口在测试中不可用。 | §1、§2.3 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent_error]` | friend 不调用平台意图识别或旧 native 入口；旧生图桩未执行，新入口在测试中不可用。 | §1、§2.3 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[pending]` | 进入后清除 pending，不按旧补参直接生图；新 Claude 入口未被旧桩接住，生图调用为 0。 | §2.1、§2.3 |
| `tests/test_chat_image_tool.py::test_switch_off_route_keeps_requests_unchanged[True]` | 此例仅关闭 FIONA_CHAT_IMAGE_TOOL；新 FIONA_CLAUDE_AGENT 仍开启且优先路由，旧请求捕获为空。 | §1 |
| `tests/test_chat_image_tool.py::test_byok_tools_safe_system_once_including_readaloud` | 旧断言读取 open_reply_stream 桩的 system；新请求在 open_agent_stream 构造，旧捕获为空；安全唯一末尾由新 SDK 测试另行验证。 | §3.1 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[success-True]` | 旧 native 成功图桩未执行；新 Claude 入口不可用，未交付计费项，因此退款而非旧成功结算。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[invalid-True]` | 旧 invalid-tool 桩未执行；错误发生于新 Claude 请求，无交付，故没有旧固定提示/落库/done。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[error-True]` | 未进入旧生图审核失败桩，实际为新 Claude 请求 unavailable，故 trace 含 byok_error。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[deleted-True]` | 旧生图后删除模拟未执行；新入口先不可用，旧生图调用计数为 0。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[image-True]` | 旧单轮回复/成功图桩未执行；新入口不可用且无交付，预扣被退款。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[invalid-True]` | 旧单轮文本/invalid-tool 桩未执行；新请求不可用且无交付，因此不产生旧预期的 assistant 记录。 | §2.3、§3.1、§3.6 |
| `tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[text-True]` | 旧单轮文本/invalid-tool 桩未执行；新请求不可用且无交付，因此不产生旧预期的 assistant 记录。 | §2.3、§3.1、§3.6 |

### 4.4 规格要求的实际输出

<details>
<summary>git status --porcelain（仓库根目录）；退出码 0</summary>

````text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/byok/client.py
 M backend/services/chat_service.py
 M backend/tests/conftest.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/components/ChatModelSection.tsx
?? backend/services/claude_agent.py
?? backend/tests/test_claude_agent_client.py
?? backend/tests/test_claude_agent_docs.py
?? backend/tests/test_claude_agent_frontend.py
?? backend/tests/test_claude_agent_integration.py
?? backend/tests/test_claude_agent_routing.py
?? backend/tests/test_claude_agent_runtime.py
?? docs/tasks/2026-10-10-claude-agent/
````

</details>

<details>
<summary>git status --porcelain --untracked-files=all（补充完整文件名）；退出码 0</summary>

````text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/byok/client.py
 M backend/services/chat_service.py
 M backend/tests/conftest.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/components/ChatModelSection.tsx
?? backend/services/claude_agent.py
?? backend/tests/test_claude_agent_client.py
?? backend/tests/test_claude_agent_docs.py
?? backend/tests/test_claude_agent_frontend.py
?? backend/tests/test_claude_agent_integration.py
?? backend/tests/test_claude_agent_routing.py
?? backend/tests/test_claude_agent_runtime.py
?? docs/tasks/2026-10-10-claude-agent/02-spec.md
?? docs/tasks/2026-10-10-claude-agent/03-report.md
````

</details>

受保护文件命令（根目录）：

```sh
git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/database.py backend/byok/crypto.py backend/byok/url_safety.py backend/byok/store.py backend/routers/chat_model.py backend/utils/safe_http.py backend/tools
```

退出码 0，实际输出：
````text
（无输出）
````

<details>
<summary>git diff --name-only -- backend/tests；退出码 0</summary>

````text
backend/tests/conftest.py
````

</details>

<details>
<summary>git diff -- backend/tests/conftest.py；退出码 0</summary>

````text
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index f025214..d2e39d2 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -39,6 +39,7 @@ os.environ.setdefault("JWT_SECRET", "fiona-ci-smoke-test-secret-0123456789")
 os.environ.setdefault("DASHSCOPE_API_KEY", "sk-fiona-ci-smoke-test-not-real")
 os.environ.setdefault("FIONA_CRISIS_MODEL_ENABLED", "0")
 os.environ.setdefault("FIONA_CHAT_IMAGE_TOOL", "0")
+os.environ.setdefault("FIONA_CLAUDE_AGENT", "0")
 
 
 @pytest.fixture
````

</details>

<details>
<summary>python -m pytest -q（backend）；退出码 1</summary>

````text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................................................ [ 18%]
........................................................................ [ 21%]
........................................................................ [ 23%]
...........................ss.................ssss...................... [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 50%]
........................................................................ [ 52%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 63%]
..............................EF........................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 84%]
................................................EEE.E................... [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.......................................                                  [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fbd39a0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x111ce3ac0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10faaa2e0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x112e9f8a0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10faab150>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x112917250>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10eddcc90>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x112917750>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ec19160>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1129297c0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x111ce3570>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10da74de0>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-install>:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<python-install>:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-install>:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x11282af00>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted

<python-install>:1637: PermissionError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  ./backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 3411 passed, 6 skipped, 14 warnings, 5 errors in 101.94s (0:01:41)
````

</details>

<details>
<summary>FIONA_CLAUDE_AGENT=1 python -m pytest -q（backend）；退出码 1</summary>

````text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................F...........FFF....FFFFFFF..FF.. [ 18%]
.........F.F.F.F.F.F.FFF.F.F.F......F.........F...FFFFFFFFFFF......F.... [ 21%]
........................................................................ [ 23%]
...........................ss.................ssss...................... [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
.................................................FFF.................... [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................FFFF.........F.. [ 42%]
..F...F.F.F.....F....F.F...F............................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 50%]
........................................................................ [ 52%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 63%]
..............................EF........................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 84%]
................................................EEE.E................... [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.......................................                                  [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x112bde9e0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x111225d00>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11126ac10>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1151e9e10>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110d42190>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1151c0b50>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1127351d0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1151c0550>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x112780de0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:457: in __init__
    self.server_bind()
<python-install>:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x115066b70>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<python-install>:478: PermissionError
=================================== FAILURES ===================================
____________ test_reply_uses_dedicated_pool_and_refunds[10-friend] _____________

client = <starlette.testclient.TestClient object at 0x112bc0f30>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c4b92b0>
mode = 'friend', amount = 10

    @pytest.mark.parametrize("mode", ["friend", "mirror"])
    @pytest.mark.parametrize("amount", [0, 5, 10])
    def test_reply_uses_dedicated_pool_and_refunds(client, dev_headers, monkeypatch, mode, amount):
        import services.chat_service as chat
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
        calls, platform, names, replies = stub_reply(monkeypatch)
        accounting = []
        monkeypatch.setattr(chat.token_budget, "add", lambda *a: accounting.append(1))
        result = events(client.post("/chat", headers=headers, json={"message": "今天挺轻松", "conversation_id": conversation}))
>       assert len(calls) == 1 and calls[0]["mirror"] is (mode == "mirror")
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_byok_chat.py:126: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
__________________ test_paid_branches_still_cost_ten[weather] __________________

client = <starlette.testclient.TestClient object at 0x113bc7240>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c6cc440>
branch = 'weather'

    @pytest.mark.parametrize("branch", ["weather", "image", "vision"])
    def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
        import services.chat_service as chat
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
        })
        monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
        async def generate(*a, **k):
            path = "/uploads/generated_" + "f" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
        payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
        if branch == "vision":
            payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = events(client.post("/chat", headers=headers, json=payload))
>       assert result[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:204: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
___________________ test_paid_branches_still_cost_ten[image] ___________________

client = <starlette.testclient.TestClient object at 0x113bc7460>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c4ec910>
branch = 'image'

    @pytest.mark.parametrize("branch", ["weather", "image", "vision"])
    def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
        import services.chat_service as chat
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
        })
        monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
        async def generate(*a, **k):
            path = "/uploads/generated_" + "f" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
        payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
        if branch == "vision":
            payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = events(client.post("/chat", headers=headers, json=payload))
>       assert result[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:204: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________________ test_paid_branches_still_cost_ten[vision] ___________________

client = <starlette.testclient.TestClient object at 0x113bc6030>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113bea970>
branch = 'vision'

    @pytest.mark.parametrize("branch", ["weather", "image", "vision"])
    def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
        import services.chat_service as chat
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
        })
        monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
        async def generate(*a, **k):
            path = "/uploads/generated_" + "f" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
        payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
        if branch == "vision":
            payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = events(client.post("/chat", headers=headers, json=payload))
>       assert result[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:204: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure0] ___________

client = <starlette.testclient.TestClient object at 0x113bc7ce0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113bea7b0>
capsys = <_pytest.capture.CaptureFixture object at 0x1130a05f0>
failure = ProviderFailure('sk-private-test-key https://private.example.net claude-opus-5-5')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：Key 无效或没有权限。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure1] ___________

client = <starlette.testclient.TestClient object at 0x112bc3bd0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113be9550>
capsys = <_pytest.capture.CaptureFixture object at 0x113bc69c0>
failure = ProviderFailure('sk-private-test-key https://private.example.net claude-opus-5-5')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：模型名或地址不存在。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure2] ___________

client = <starlette.testclient.TestClient object at 0x113bc7bd0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c6cdda0>
capsys = <_pytest.capture.CaptureFixture object at 0x113bc7790>
failure = ProviderFailure('sk-private-test-key https://private.example.net claude-opus-5-5')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：额度不足或请求过于频繁。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure3] ___________

client = <starlette.testclient.TestClient object at 0x113bc7130>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c36f930>
capsys = <_pytest.capture.CaptureFixture object at 0x113bd3650>
failure = TimeoutError()

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：响应超时。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure4] ___________

client = <starlette.testclient.TestClient object at 0x113bc6cf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x112bddb00>
capsys = <_pytest.capture.CaptureFixture object at 0x113bd1d50>
failure = APIConnectionError('Connection error.')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
        assert events(response) == [{"error": error_message(failure)}]
>       assert calls and not platform and balance(user) == 10
E       assert ([])

tests/test_byok_chat.py:249: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure5] ___________

client = <starlette.testclient.TestClient object at 0x113bc68b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113beb2a0>
capsys = <_pytest.capture.CaptureFixture object at 0x113bdb2f0>
failure = NeedsReentryError()

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：配置需要重新填写 Key。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure6] ___________

client = <starlette.testclient.TestClient object at 0x113c545a0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113bebe70>
capsys = <_pytest.capture.CaptureFixture object at 0x113bdba70>
failure = ByokUnavailableError()

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：服务器暂未开启自带模型。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
_________________ test_empty_and_refusal_semantics[True-True] __________________

client = <starlette.testclient.TestClient object at 0x113c54c00>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113be9cc0>
refused = True, partial = True

    @pytest.mark.parametrize("refused,partial", [(False, False), (True, False), (True, True)])
    def test_empty_and_refusal_semantics(client, dev_headers, monkeypatch, refused, partial):
        import database
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        stub_reply(monkeypatch, chunks=[("部分", None)] if partial else [], refused=refused)
        result = events(client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation}))
        messages = asyncio.run(database.get_messages(user, conversation_id=conversation))
        if partial:
>           assert result[-2:] == [{"text": "（Claude 中止了这条回复）"}, {"done": True}]
E           AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'text': '（C...'done': True}]
E             
E             At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'text': '（Claude 中止了这条回复）'}
E             Right contains one more item: {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:262: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
______________________ test_daily_cap_and_dev_mode_bypass ______________________

client = <starlette.testclient.TestClient object at 0x113c55480>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113c5f4d0>

    def test_daily_cap_and_dev_mode_bypass(client, dev_headers, monkeypatch):
        import services.chat_service as chat
        from rate_limit import limiter
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        monkeypatch.setenv("FIONA_DAILY_BYOK_CHATS", "1")
        monkeypatch.setattr(limiter, "enabled", True)
        calls, *_ = stub_reply(monkeypatch)
        payload = {"message": "正常聊天", "conversation_id": conversation}
>       assert events(client.post("/chat", headers=headers, json=payload))[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:278: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
____________ test_disconnected_byok_stream_closes_and_releases_slot ____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ff54980>

    def test_disconnected_byok_stream_closes_and_releases_slot(monkeypatch):
        import services.chat_service as chat
        from rate_limit import limiter
        monkeypatch.setattr(limiter, "enabled", False)
        monkeypatch.setenv("DEV_MODE", "0")
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "friend")
        monkeypatch.setattr(chat, "get_pending", lambda *a, **k: None)
        monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *a, **k: {"intent": None})
        traces = []
        async def log(*a, **k):
            traces.append(k)
        monkeypatch.setattr(chat, "log_event", log)
        replies = []
        def open_stream(*a, **k):
            reply = Reply()
            replies.append(reply)
            return reply
        monkeypatch.setattr(chat, "open_reply_stream", open_stream)
        config = {"provider": "anthropic", "model": "claude-opus-5-5", "enabled": True, "api_key": "test-key"}
        ctx = chat.ChatContext("disconnect_user", "聊天", False, None, "聊天", [], 0, "system", [], byok_config=config)
        async def scenario():
            stream = chat.run_chat(ctx, crisis=False)
            first = await anext(stream)
            assert "reply_model" in first
            assert ctx.user in chat._BYOK_USERS
            await stream.aclose()
>       asyncio.run(scenario())

tests/test_byok_chat.py:464: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:205: in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
<python-install>:128: in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-install>:719: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    async def scenario():
        stream = chat.run_chat(ctx, crisis=False)
        first = await anext(stream)
>       assert "reply_model" in first
E       assert 'reply_model' in 'data: {"error": "你的模型调用失败：连不上该服务。本条没有改用平台模型。"}\n\n'

tests/test_byok_chat.py:461: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=connection
_______ test_r1_pending_api_free_actions_and_paid_guards[image_topic-10] _______

client = <starlette.testclient.TestClient object at 0x113bc79b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113c5ca60>
amount = 10, case = 'image_topic'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[image_cancel-10] _______

client = <starlette.testclient.TestClient object at 0x113bc7df0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113decad0>
amount = 10, case = 'image_cancel'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
_______ test_r1_pending_api_free_actions_and_paid_guards[image_fill-10] ________

client = <starlette.testclient.TestClient object at 0x113c54f30>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbe660>
amount = 10, case = 'image_fill'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
_____ test_r1_pending_api_free_actions_and_paid_guards[weather_cancel-10] ______

client = <starlette.testclient.TestClient object at 0x113c55150>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbd940>
amount = 10, case = 'weather_cancel'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[weather_fill-10] _______

client = <starlette.testclient.TestClient object at 0x113c55bf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d89ef0>
amount = 10, case = 'weather_fill'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[weather_chat-10] _______

client = <starlette.testclient.TestClient object at 0x113bc7570>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d88f30>
amount = 10, case = 'weather_chat'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=7, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0] ______

client = <starlette.testclient.TestClient object at 0x113bc5260>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8bf50>
amount = 0, case = 'image_new_tool'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
>           assert seed[-1] == {"done": True} and get_pending(key) == pending
E           AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff)

tests/test_byok_chat.py:517: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_____ test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10] ______

client = <starlette.testclient.TestClient object at 0x113bc7790>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbde10>
amount = 10, case = 'image_new_tool'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
>           assert seed[-1] == {"done": True} and get_pending(key) == pending
E           AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff)

tests/test_byok_chat.py:517: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[image_thanks-10] _______

client = <starlette.testclient.TestClient object at 0x113c578a0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d89860>
amount = 10, case = 'image_thanks'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
____ test_r1_pending_api_free_actions_and_paid_guards[image_discussion-10] _____

client = <starlette.testclient.TestClient object at 0x113c56470>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8b8c0>
amount = 10, case = 'image_discussion'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_____ test_r1_pending_api_free_actions_and_paid_guards[image_question-10] ______

client = <starlette.testclient.TestClient object at 0x113c569c0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbd1d0>
amount = 10, case = 'image_question'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
________ test_r1_reply_persistence_failure_uses_platform_error[friend] _________

client = <starlette.testclient.TestClient object at 0x113bc6250>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113c5cfa0>
capsys = <_pytest.capture.CaptureFixture object at 0x113e44bb0>, mode = 'friend'

    @pytest.mark.parametrize("mode", ["friend", "mirror"])
    def test_r1_reply_persistence_failure_uses_platform_error(client, dev_headers, monkeypatch, capsys, mode):
        import services.chat_service as chat
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
        original = chat.save_message
        async def fail_assistant(username, role, *a, **k):
            if role == "assistant":
                return False
            return await original(username, role, *a, **k)
        monkeypatch.setattr(chat, "save_message", fail_assistant)
        result = events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation}))
>       assert result[-1] == {"error": "服务暂时不可用，请稍后再试"}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'error': '服务暂时不可用，请稍后再试'}
E         
E         Differing items:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '服务暂时不可用，请稍后再试'}
E         Use -v to get more diff

tests/test_byok_chat.py:591: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
____ test_r1_deleted_conversation_during_reply_is_platform_failure[friend] _____

client = <starlette.testclient.TestClient object at 0x113c548d0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1107262e0>
capsys = <_pytest.capture.CaptureFixture object at 0x113fa4ef0>, mode = 'friend'

    @pytest.mark.parametrize("mode", ["friend", "mirror"])
    def test_r1_deleted_conversation_during_reply_is_platform_failure(client, dev_headers, monkeypatch, capsys, mode):
        import database
        import services.chat_service as chat
        from agent_store import delete_conversation
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
        class DeletedReply(Reply):
            def __iter__(self):
                for chunk in super().__iter__():
                    yield chunk
                    # The first chunk has reached the consumer before deletion.
                    if not calls:
                        raise AssertionError("BYOK stream did not open")
                    asyncio.run(delete_conversation(user, conversation))
                    break
        def open_stream(*a, **k):
            calls.append(1)
            return DeletedReply()
        monkeypatch.setattr(chat, "open_reply_stream", open_stream)
        result = events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation}))
>       assert result[:2] == [{"reply_model": {"source": "byok", "label": "Claude · claude-opus-5-5"}}, {"text": "测试"}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'reply_mode...'text': '测试'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'reply_model': {'source': 'byok', 'label': 'Claude · claude-opus-5-5'}}
E         Right contains one more item: {'text': '测试'}
E         Use -v to get more diff

tests/test_byok_chat.py:733: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
____________ test_r2_paid_weather_pending_routing_matches_platform _____________

client = <starlette.testclient.TestClient object at 0x113c57460>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8a510>

    def test_r2_paid_weather_pending_routing_matches_platform(client, dev_headers, monkeypatch):
        """BYOK must not reinterpret a pending city's valid text as conversation."""
        import database
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending, set_pending
        snapshots = []
        for enabled in (False, True):
            monkeypatch.setenv("DEV_MODE", "1")
            user, conversation, headers = setup(client, dev_headers, monkeypatch)
            if not enabled:
                asyncio.run(delete_config(user))
            key = (user, conversation)
            set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
            calls, platform, *_ = stub_reply(monkeypatch)
            tools, caps = [], []
            card = {"type": "card", "subtype": "weather", "points": ["天气结果"]}
            def execute(intent, params):
                tools.append((intent, dict(params)))
                return card
            monkeypatch.setattr(chat, "execute_intent", execute)
            monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
            result = events(client.post("/chat", headers=headers, json={"message": "开心", "conversation_id": conversation}))
            snapshots.append((result, tools, caps, balance(user), bool(calls), bool(platform), get_pending(key)))
>           assert asyncio.run(database.get_messages(user, conversation_id=conversation))[-1]["role"] == "assistant"
E           AssertionError: assert 'user' == 'assistant'
E             
E             - assistant
E             + user

tests/test_byok_chat.py:791: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
______ test_r2_zero_balance_other_pending_free_exits[route-\u7b97\u4e86] _______

client = <starlette.testclient.TestClient object at 0x113c56ad0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbd010>
intent = 'route', message = '算了'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c56ad0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbd010>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_zero_balance_other_pending_free_exits[route-\u6362\u4e2a\u8bdd\u9898] _

client = <starlette.testclient.TestClient object at 0x113c54270>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8a5f0>
intent = 'route', message = '换个话题'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c54270>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8a5f0>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_zero_balance_other_pending_free_exits[route-\u4ece\u5bb6\u51fa\u53d1] _

client = <starlette.testclient.TestClient object at 0x113c56250>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbce50>
intent = 'route', message = '从家出发'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c56250>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbce50>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
____ test_r2_zero_balance_other_pending_free_exits[web_search-\u7b97\u4e86] ____

client = <starlette.testclient.TestClient object at 0x113c57df0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbef90>
intent = 'web_search', message = '算了'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c57df0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbef90>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
_______ test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-route] ________

client = <starlette.testclient.TestClient object at 0x113bc7350>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbeba0>
intent = 'route', message = '算了'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113bc7350>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbeba0>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[意图识别] chars=5, intent=route, missing=['origin']
[硬词检测] chars=2, detected_count=0
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_____ test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-web_search] _____

client = <starlette.testclient.TestClient object at 0x113c557b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1107262e0>
intent = 'web_search', message = '算了'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c557b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1107262e0>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=web_search, missing=['query']
[硬词检测] chars=2, detected_count=0
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-route] __

client = <starlette.testclient.TestClient object at 0x113c57bd0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d89550>
intent = 'route', message = '换个话题'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c57bd0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d89550>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[意图识别] chars=5, intent=route, missing=['origin']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-web_search] _

client = <starlette.testclient.TestClient object at 0x113c568b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8bf50>
intent = 'web_search', message = '换个话题'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c568b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d8bf50>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=web_search, missing=['query']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-route] __

client = <starlette.testclient.TestClient object at 0x113c54e20>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113e397f0>
intent = 'route', message = '从家出发'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113c54e20>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113e397f0>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[意图识别] chars=5, intent=route, missing=['origin']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-web_search] _

client = <starlette.testclient.TestClient object at 0x113d68d10>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113e38d70>
intent = 'web_search', message = '从家出发'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x113d68d10>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113e38d70>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=web_search, missing=['query']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
________ test_r3_paid_weather_topic_exit_matches_unconfigured_platform _________

client = <starlette.testclient.TestClient object at 0x113c56580>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113fbeba0>

    def test_r3_paid_weather_topic_exit_matches_unconfigured_platform(client, dev_headers, monkeypatch):
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending, set_pending
        snapshots = []
        for enabled in (False, True):
            monkeypatch.setenv("DEV_MODE", "1")
            user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=10)
            if not enabled:
                asyncio.run(delete_config(user))
            key = (user, conversation)
            set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
            calls, platform, *_ = stub_reply(monkeypatch)
            tools, caps = [], []
            card = {"type": "card", "subtype": "weather", "points": ["天气结果"]}
            def execute(intent, params):
                tools.append((intent, dict(params)))
                return card
            monkeypatch.setattr(chat, "execute_intent", execute)
            monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
            result = events(client.post("/chat", headers=headers, json={"message": "换个话题", "conversation_id": conversation}))
            snapshots.append((result, tools, caps, balance(user), bool(calls), bool(platform), get_pending(key)))
>       assert snapshots[0] == snapshots[1]
E       AssertionError: assert ([{'card': {'...e, False, ...) == ([{'error': '...e, False, ...)
E         
E         At index 0 diff: [{'card': {'type': 'card', 'subtype': 'weather', 'points': ['天气结果']}}, {'done': True}] != [{'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}]
E         Use -v to get more diff

tests/test_byok_chat.py:969: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
_ test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-opus-5-5] _

harness = namespace(chat=<module 'services.chat_service' from './backend/services/chat_...'unavailable', 'resp_chars': 0}], daily=[(('byok_chat', 'r1-byok-user'), {'hit': True})], replies=[], planner_calls=[])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1105f2350>
provider = 'anthropic', model = 'claude-opus-5-5'

    @pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
    def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
        h = harness
        configure(h, provider, model)
        def unexpected(*args, **kwargs):
            pytest.fail("native mode must not call planner")
        monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
        def open_reply(*args, **kwargs):
            h.replies.append((args, kwargs))
            return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
        monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
>       assert h.replies[0][1]["tools"] == "generate_image"
               ^^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_byok_planner_r1.py:235: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_ test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-sonnet-5-5] _

harness = namespace(chat=<module 'services.chat_service' from './backend/services/chat_...'unavailable', 'resp_chars': 0}], daily=[(('byok_chat', 'r1-byok-user'), {'hit': True})], replies=[], planner_calls=[])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1106c9710>
provider = 'anthropic', model = 'claude-sonnet-5-5'

    @pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
    def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
        h = harness
        configure(h, provider, model)
        def unexpected(*args, **kwargs):
            pytest.fail("native mode must not call planner")
        monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
        def open_reply(*args, **kwargs):
            h.replies.append((args, kwargs))
            return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
        monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
>       assert h.replies[0][1]["tools"] == "generate_image"
               ^^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_byok_planner_r1.py:235: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_ test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-haiku-5-5] _

harness = namespace(chat=<module 'services.chat_service' from './backend/services/chat_...'unavailable', 'resp_chars': 0}], daily=[(('byok_chat', 'r1-byok-user'), {'hit': True})], replies=[], planner_calls=[])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x113d38c90>
provider = 'anthropic', model = 'claude-haiku-5-5'

    @pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
    def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
        h = harness
        configure(h, provider, model)
        def unexpected(*args, **kwargs):
            pytest.fail("native mode must not call planner")
        monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
        def open_reply(*args, **kwargs):
            h.replies.append((args, kwargs))
            return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
        monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
>       assert h.replies[0][1]["tools"] == "generate_image"
               ^^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_byok_planner_r1.py:235: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
___________ test_native_tool_route_uses_reply_model_only[candidate] ____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110d569e0>
kind = 'candidate'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
_____________ test_native_tool_route_uses_reply_model_only[intent] _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x114bb95c0>
kind = 'intent'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
__________ test_native_tool_route_uses_reply_model_only[intent_error] __________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x114bb97f0>
kind = 'intent_error'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
____________ test_native_tool_route_uses_reply_model_only[pending] _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ff54980>
kind = 'pending'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_____________ test_switch_off_route_keeps_requests_unchanged[True] _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...', response_saved=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x112fb6430>
byok = True

    @pytest.mark.parametrize('byok', [False, True])
    def test_switch_off_route_keeps_requests_unchanged(chat_harness, monkeypatch, byok):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.message = ctx.user_content = '你好'
        monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', '0')
        requests = []
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            def opened(*a, **kwargs):
                requests.append(kwargs)
                return ByokFakeStream('免费文字', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
            monkeypatch.setattr(chat, 'open_reply_stream', opened)
        else:
            def opened(*a, **kwargs):
                requests.append(kwargs)
                return iter(tool_blocks()), False
            monkeypatch.setattr(chat, '_create_stream_with_fallback', opened)
        asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
>       assert requests
E       assert []

tests/test_chat_image_tool.py:630: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_____________ test_byok_tools_safe_system_once_including_readaloud _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...', response_saved=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ffd1a90>

    def test_byok_tools_safe_system_once_including_readaloud(chat_harness, monkeypatch):
        from persona import BASE_SAFETY_RULES
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        ctx.messages.append({'role': 'system', 'content': '朗读本次结果\n\n' + BASE_SAFETY_RULES.strip()})
        requests = []
        def opened(config, messages, **kwargs):
            requests.append(messages)
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
>       systems = [m['content'] for m in requests[0] if m['role'] == 'system']
                                         ^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_chat_image_tool.py:674: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_________ test_reserved_turn_settlement_and_single_image[success-True] _________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x112ba16a0>
byok = True, outcome = 'success'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
>       assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
E       AssertionError: assert [('tool-user', 10)] == []
E         
E         Left contains one more item: ('tool-user', 10)
E         Use -v to get more diff

tests/test_chat_image_tool.py:751: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_________ test_reserved_turn_settlement_and_single_image[invalid-True] _________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ffb33f0>
byok = True, outcome = 'invalid'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
        assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
        if outcome == 'success':
            assert len(calls) == 1
            assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
            assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
            assert sum('done' in event for event in result if isinstance(event, dict)) == 1
            assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
        else:
            assert len(calls) == int(outcome == 'deleted')
>           assert sum('done' in event for event in result if isinstance(event, dict)) == int(outcome == 'invalid')
E           AssertionError: assert 0 == 1
E            +  where 0 = sum(<generator object test_reserved_turn_settlement_and_single_image.<locals>.<genexpr> at 0x113bf0740>)
E            +  and   1 = int('invalid' == 'invalid'
E               
E                 invalid)

tests/test_chat_image_tool.py:760: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
__________ test_reserved_turn_settlement_and_single_image[error-True] __________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x114bbb700>
byok = True, outcome = 'error'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
        assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
        if outcome == 'success':
            assert len(calls) == 1
            assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
            assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
            assert sum('done' in event for event in result if isinstance(event, dict)) == 1
            assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
        else:
            assert len(calls) == int(outcome == 'deleted')
            assert sum('done' in event for event in result if isinstance(event, dict)) == int(outcome == 'invalid')
        assert sum('error' in event for event in result if isinstance(event, dict)) == (0 if outcome in ('success', 'invalid') else 1)
        assert not any('tool' in event for event in result if isinstance(event, dict))
        if outcome in ('success', 'invalid'): assert len(saves) == 1
        else: assert not saves
        if outcome == 'deleted': assert deleted == ['/uploads/generated_test.png']
>       if byok and outcome == 'error': assert 'byok_error' not in traces[0]
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 'byok_error' not in {'mode': 'friend', 'intent': None, 'model': 'byok', 'has_image': False, ...}

tests/test_chat_image_tool.py:766: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_________ test_reserved_turn_settlement_and_single_image[deleted-True] _________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110d404b0>
byok = True, outcome = 'deleted'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
        assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
        if outcome == 'success':
            assert len(calls) == 1
            assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
            assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
            assert sum('done' in event for event in result if isinstance(event, dict)) == 1
            assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
        else:
>           assert len(calls) == int(outcome == 'deleted')
E           AssertionError: assert 0 == 1
E            +  where 0 = len([])
E            +  and   1 = int('deleted' == 'deleted'
E               
E                 deleted)

tests/test_chat_image_tool.py:759: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
____ test_http_paid_turn_reserves_once_and_settles_real_balance[image-True] ____

client = <starlette.testclient.TestClient object at 0x1145d0af0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11063f5b0>
byok = True, outcome = 'image'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
    def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
        """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
        import sqlite3
        from pathlib import Path
        import database
        import routers.chat as router
        import services.chat_service as chat
        from auth import create_token
        from rate_limit import limiter
        from utils import media
        monkeypatch.setattr(limiter, 'enabled', False)
        monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
        monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
        username = dev_headers['X-Dev-User']
        conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
        version = asyncio.run(database.get_session_version(username))
        headers = {'Authorization': 'Bearer ' + create_token(username, version)}
        monkeypatch.setenv('DEV_MODE', '0')
        config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
        async def config_read(*a): return config
        monkeypatch.setattr(chat, 'get_internal_config', config_read)
        reservations, refunds, generated = [], [], []
        original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
        async def reserve(*a):
            reservations.append(a)
            return await original_reserve(*a)
        async def refund(*a):
            refunds.append(a)
            return await original_refund(*a)
        monkeypatch.setattr(router, 'reserve_strawberries', reserve)
        monkeypatch.setattr(chat, 'refund_strawberries', refund)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        async def planner(*args):
            if outcome == 'text':
                return {'status': 'no'}
            if outcome == 'invalid':
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            return {'status': 'draw', 'prompt': '猫'}
        monkeypatch.setattr(chat, 'plan_image', planner)
        if byok:
            call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
        else:
            chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
        async def image(prompt, ratio, **kwargs):
            generated.append((prompt, ratio, kwargs))
            if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
            Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
            return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
        monkeypatch.setattr(chat, 'generate_image', image)
        response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
        assert response.status_code == 200
        result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
        assert reservations == [(username, 10)]
>       assert refunds == ([] if billed else [(username, 10)])
E       AssertionError: assert [('smoke_tester', 10)] == []
E         
E         Left contains one more item: ('smoke_tester', 10)
E         Use -v to get more diff

tests/test_chat_image_tool.py:891: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=8, detected_count=0
[byok] reply failed category=unavailable
___ test_http_paid_turn_reserves_once_and_settles_real_balance[invalid-True] ___

client = <starlette.testclient.TestClient object at 0x1145d2470>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c4bb5b0>
byok = True, outcome = 'invalid'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
    def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
        """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
        import sqlite3
        from pathlib import Path
        import database
        import routers.chat as router
        import services.chat_service as chat
        from auth import create_token
        from rate_limit import limiter
        from utils import media
        monkeypatch.setattr(limiter, 'enabled', False)
        monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
        monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
        username = dev_headers['X-Dev-User']
        conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
        version = asyncio.run(database.get_session_version(username))
        headers = {'Authorization': 'Bearer ' + create_token(username, version)}
        monkeypatch.setenv('DEV_MODE', '0')
        config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
        async def config_read(*a): return config
        monkeypatch.setattr(chat, 'get_internal_config', config_read)
        reservations, refunds, generated = [], [], []
        original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
        async def reserve(*a):
            reservations.append(a)
            return await original_reserve(*a)
        async def refund(*a):
            refunds.append(a)
            return await original_refund(*a)
        monkeypatch.setattr(router, 'reserve_strawberries', reserve)
        monkeypatch.setattr(chat, 'refund_strawberries', refund)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        async def planner(*args):
            if outcome == 'text':
                return {'status': 'no'}
            if outcome == 'invalid':
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            return {'status': 'draw', 'prompt': '猫'}
        monkeypatch.setattr(chat, 'plan_image', planner)
        if byok:
            call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
        else:
            chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
        async def image(prompt, ratio, **kwargs):
            generated.append((prompt, ratio, kwargs))
            if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
            Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
            return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
        monkeypatch.setattr(chat, 'generate_image', image)
        response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
        assert response.status_code == 200
        result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
        assert reservations == [(username, 10)]
        assert refunds == ([] if billed else [(username, 10)])
        assert asyncio.run(database.get_strawberry_balance(username)) == (10 if billed else 20)
        history = client.get(f'/conversations/{conversation}/messages', headers=headers).json()['messages']
        assistants = [row for row in history if row['role'] == 'assistant']
>       assert len(assistants) == (0 if outcome == 'error' else 1)
E       assert 0 == 1
E        +  where 0 = len([])

tests/test_chat_image_tool.py:895: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=8, detected_count=0
[byok] reply failed category=unavailable
____ test_http_paid_turn_reserves_once_and_settles_real_balance[text-True] _____

client = <starlette.testclient.TestClient object at 0x113bc7df0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110d40590>
byok = True, outcome = 'text'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
    def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
        """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
        import sqlite3
        from pathlib import Path
        import database
        import routers.chat as router
        import services.chat_service as chat
        from auth import create_token
        from rate_limit import limiter
        from utils import media
        monkeypatch.setattr(limiter, 'enabled', False)
        monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
        monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
        username = dev_headers['X-Dev-User']
        conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
        version = asyncio.run(database.get_session_version(username))
        headers = {'Authorization': 'Bearer ' + create_token(username, version)}
        monkeypatch.setenv('DEV_MODE', '0')
        config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
        async def config_read(*a): return config
        monkeypatch.setattr(chat, 'get_internal_config', config_read)
        reservations, refunds, generated = [], [], []
        original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
        async def reserve(*a):
            reservations.append(a)
            return await original_reserve(*a)
        async def refund(*a):
            refunds.append(a)
            return await original_refund(*a)
        monkeypatch.setattr(router, 'reserve_strawberries', reserve)
        monkeypatch.setattr(chat, 'refund_strawberries', refund)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        async def planner(*args):
            if outcome == 'text':
                return {'status': 'no'}
            if outcome == 'invalid':
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            return {'status': 'draw', 'prompt': '猫'}
        monkeypatch.setattr(chat, 'plan_image', planner)
        if byok:
            call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
        else:
            chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
        async def image(prompt, ratio, **kwargs):
            generated.append((prompt, ratio, kwargs))
            if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
            Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
            return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
        monkeypatch.setattr(chat, 'generate_image', image)
        response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
        assert response.status_code == 200
        result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
        assert reservations == [(username, 10)]
        assert refunds == ([] if billed else [(username, 10)])
        assert asyncio.run(database.get_strawberry_balance(username)) == (10 if billed else 20)
        history = client.get(f'/conversations/{conversation}/messages', headers=headers).json()['messages']
        assistants = [row for row in history if row['role'] == 'assistant']
>       assert len(assistants) == (0 if outcome == 'error' else 1)
E       assert 0 == 1
E        +  where 0 = len([])

tests/test_chat_image_tool.py:895: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=8, detected_count=0
[byok] reply failed category=unavailable
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x113c567a0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ffd1b70>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-install>:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<python-install>:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-install>:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x114c67c10>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted

<python-install>:1637: PermissionError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  ./backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_byok_chat.py::test_reply_uses_dedicated_pool_and_refunds[10-friend]
FAILED tests/test_byok_chat.py::test_paid_branches_still_cost_ten[weather] - ...
FAILED tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image] - As...
FAILED tests/test_byok_chat.py::test_paid_branches_still_cost_ten[vision] - A...
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure0]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure1]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure2]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure3]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure4]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure5]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure6]
FAILED tests/test_byok_chat.py::test_empty_and_refusal_semantics[True-True]
FAILED tests/test_byok_chat.py::test_daily_cap_and_dev_mode_bypass - Assertio...
FAILED tests/test_byok_chat.py::test_disconnected_byok_stream_closes_and_releases_slot
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_topic-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_cancel-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_cancel-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_fill-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_chat-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_thanks-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_discussion-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_question-10]
FAILED tests/test_byok_chat.py::test_r1_reply_persistence_failure_uses_platform_error[friend]
FAILED tests/test_byok_chat.py::test_r1_deleted_conversation_during_reply_is_platform_failure[friend]
FAILED tests/test_byok_chat.py::test_r2_paid_weather_pending_routing_matches_platform
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-\u7b97\u4e86]
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-\u6362\u4e2a\u8bdd\u9898]
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-\u4ece\u5bb6\u51fa\u53d1]
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[web_search-\u7b97\u4e86]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-route]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-web_search]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-route]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-web_search]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-route]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-web_search]
FAILED tests/test_byok_chat.py::test_r3_paid_weather_topic_exit_matches_unconfigured_platform
FAILED tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-opus-5-5]
FAILED tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-sonnet-5-5]
FAILED tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-haiku-5-5]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[candidate]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent_error]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[pending]
FAILED tests/test_chat_image_tool.py::test_switch_off_route_keeps_requests_unchanged[True]
FAILED tests/test_chat_image_tool.py::test_byok_tools_safe_system_once_including_readaloud
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[success-True]
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[invalid-True]
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[error-True]
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[deleted-True]
FAILED tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[image-True]
FAILED tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[invalid-True]
FAILED tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[text-True]
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
56 failed, 3356 passed, 6 skipped, 14 warnings, 5 errors in 98.47s (0:01:38)
````

</details>

<details>
<summary>python -m pytest -q tests/test_claude_agent_*.py（backend）；退出码 0</summary>

````text
........................................................................ [ 55%]
.........................................................                [100%]
129 passed in 3.43s
````

</details>

补充复验仅使用测试选择参数，不改测试文件：

```sh
python -m pytest -q --deselect=tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot --deselect=tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive --deselect=tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline --deselect=tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work --deselect=tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline --deselect=tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
FIONA_CLAUDE_AGENT=1 python -m pytest -q --deselect=tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot --deselect=tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive --deselect=tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline --deselect=tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work --deselect=tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline --deselect=tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
```

<details>
<summary>pytest-default-no-loopback（对应上方补充命令，backend）；退出码 0</summary>

````text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................................................ [ 18%]
........................................................................ [ 21%]
........................................................................ [ 23%]
...........................ss.................ssss...................... [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 50%]
........................................................................ [ 52%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 99%]
.................................                                        [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  ./backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3411 passed, 6 skipped, 6 deselected, 14 warnings in 101.66s (0:01:41)
````

</details>

<details>
<summary>pytest-enabled-no-loopback（对应上方补充命令，backend）；退出码 1</summary>

````text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................F...........FFF....FFFFFFF..FF.. [ 18%]
.........F.F.F.F.F.F.FFF.F.F.F......F.........F...FFFFFFFFFFF......F.... [ 21%]
........................................................................ [ 23%]
...........................ss.................ssss...................... [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
.................................................FFF.................... [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 40%]
........................................................FFFF.........F.. [ 42%]
..F...F.F.F.....F....F.F...F............................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 50%]
........................................................................ [ 52%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 99%]
.................................                                        [100%]
=================================== FAILURES ===================================
____________ test_reply_uses_dedicated_pool_and_refunds[10-friend] _____________

client = <starlette.testclient.TestClient object at 0x10ea12f10>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x108266f20>
mode = 'friend', amount = 10

    @pytest.mark.parametrize("mode", ["friend", "mirror"])
    @pytest.mark.parametrize("amount", [0, 5, 10])
    def test_reply_uses_dedicated_pool_and_refunds(client, dev_headers, monkeypatch, mode, amount):
        import services.chat_service as chat
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
        calls, platform, names, replies = stub_reply(monkeypatch)
        accounting = []
        monkeypatch.setattr(chat.token_budget, "add", lambda *a: accounting.append(1))
        result = events(client.post("/chat", headers=headers, json={"message": "今天挺轻松", "conversation_id": conversation}))
>       assert len(calls) == 1 and calls[0]["mirror"] is (mode == "mirror")
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_byok_chat.py:126: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
__________________ test_paid_branches_still_cost_ten[weather] __________________

client = <starlette.testclient.TestClient object at 0x10fa0f240>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1081f1be0>
branch = 'weather'

    @pytest.mark.parametrize("branch", ["weather", "image", "vision"])
    def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
        import services.chat_service as chat
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
        })
        monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
        async def generate(*a, **k):
            path = "/uploads/generated_" + "f" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
        payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
        if branch == "vision":
            payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = events(client.post("/chat", headers=headers, json=payload))
>       assert result[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:204: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
___________________ test_paid_branches_still_cost_ten[image] ___________________

client = <starlette.testclient.TestClient object at 0x10fa0f460>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1081f2190>
branch = 'image'

    @pytest.mark.parametrize("branch", ["weather", "image", "vision"])
    def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
        import services.chat_service as chat
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
        })
        monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
        async def generate(*a, **k):
            path = "/uploads/generated_" + "f" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
        payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
        if branch == "vision":
            payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = events(client.post("/chat", headers=headers, json=payload))
>       assert result[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:204: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________________ test_paid_branches_still_cost_ten[vision] ___________________

client = <starlette.testclient.TestClient object at 0x10fa0e030>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x108350c20>
branch = 'vision'

    @pytest.mark.parametrize("branch", ["weather", "image", "vision"])
    def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
        import services.chat_service as chat
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
            "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
        })
        monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
        async def generate(*a, **k):
            path = "/uploads/generated_" + "f" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
        payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
        if branch == "vision":
            payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = events(client.post("/chat", headers=headers, json=payload))
>       assert result[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:204: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure0] ___________

client = <starlette.testclient.TestClient object at 0x10fa0fce0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2e3c0>
capsys = <_pytest.capture.CaptureFixture object at 0x10eee43b0>
failure = ProviderFailure('sk-private-test-key https://private.example.net claude-opus-5-5')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：Key 无效或没有权限。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure1] ___________

client = <starlette.testclient.TestClient object at 0x10ea12470>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2d390>
capsys = <_pytest.capture.CaptureFixture object at 0x10fa0e9c0>
failure = ProviderFailure('sk-private-test-key https://private.example.net claude-opus-5-5')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：模型名或地址不存在。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure2] ___________

client = <starlette.testclient.TestClient object at 0x10fa0fbd0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1081f3e70>
capsys = <_pytest.capture.CaptureFixture object at 0x10fa0f790>
failure = ProviderFailure('sk-private-test-key https://private.example.net claude-opus-5-5')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：额度不足或请求过于频繁。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure3] ___________

client = <starlette.testclient.TestClient object at 0x10fa0f130>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x108353a10>
capsys = <_pytest.capture.CaptureFixture object at 0x10fa20c50>
failure = TimeoutError()

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：响应超时。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure4] ___________

client = <starlette.testclient.TestClient object at 0x10fa0ecf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2f000>
capsys = <_pytest.capture.CaptureFixture object at 0x10fa22850>
failure = APIConnectionError('Connection error.')

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
        assert events(response) == [{"error": error_message(failure)}]
>       assert calls and not platform and balance(user) == 10
E       assert ([])

tests/test_byok_chat.py:249: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure5] ___________

client = <starlette.testclient.TestClient object at 0x10fa0e8b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2e900>
capsys = <_pytest.capture.CaptureFixture object at 0x10fa27e30>
failure = NeedsReentryError()

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：配置需要重新填写 Key。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
__________ test_error_mapping_no_fallback_refund_or_secret[failure6] ___________

client = <starlette.testclient.TestClient object at 0x10fa9d480>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2da90>
capsys = <_pytest.capture.CaptureFixture object at 0x10fa26d50>
failure = ByokUnavailableError()

    @pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
    def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
        response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
>       assert events(response) == [{"error": error_message(failure)}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'error': '你...本条没有改用平台模型。'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '你的模型调用失败：服务器暂未开启自带模型。本条没有改用平台模型。'}
E         Use -v to get more diff

tests/test_byok_chat.py:248: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
_________________ test_empty_and_refusal_semantics[True-True] __________________

client = <starlette.testclient.TestClient object at 0x10fa9dd00>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2c750>
refused = True, partial = True

    @pytest.mark.parametrize("refused,partial", [(False, False), (True, False), (True, True)])
    def test_empty_and_refusal_semantics(client, dev_headers, monkeypatch, refused, partial):
        import database
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        stub_reply(monkeypatch, chunks=[("部分", None)] if partial else [], refused=refused)
        result = events(client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation}))
        messages = asyncio.run(database.get_messages(user, conversation_id=conversation))
        if partial:
>           assert result[-2:] == [{"text": "（Claude 中止了这条回复）"}, {"done": True}]
E           AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'text': '（C...'done': True}]
E             
E             At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'text': '（Claude 中止了这条回复）'}
E             Right contains one more item: {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:262: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
______________________ test_daily_cap_and_dev_mode_bypass ______________________

client = <starlette.testclient.TestClient object at 0x10fa9ce20>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa95710>

    def test_daily_cap_and_dev_mode_bypass(client, dev_headers, monkeypatch):
        import services.chat_service as chat
        from rate_limit import limiter
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        monkeypatch.setenv("FIONA_DAILY_BYOK_CHATS", "1")
        monkeypatch.setattr(limiter, "enabled", True)
        calls, *_ = stub_reply(monkeypatch)
        payload = {"message": "正常聊天", "conversation_id": conversation}
>       assert events(client.post("/chat", headers=headers, json=payload))[-1] == {"done": True}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff

tests/test_byok_chat.py:278: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
____________ test_disconnected_byok_stream_closes_and_releases_slot ____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10bd9cad0>

    def test_disconnected_byok_stream_closes_and_releases_slot(monkeypatch):
        import services.chat_service as chat
        from rate_limit import limiter
        monkeypatch.setattr(limiter, "enabled", False)
        monkeypatch.setenv("DEV_MODE", "0")
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "friend")
        monkeypatch.setattr(chat, "get_pending", lambda *a, **k: None)
        monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *a, **k: {"intent": None})
        traces = []
        async def log(*a, **k):
            traces.append(k)
        monkeypatch.setattr(chat, "log_event", log)
        replies = []
        def open_stream(*a, **k):
            reply = Reply()
            replies.append(reply)
            return reply
        monkeypatch.setattr(chat, "open_reply_stream", open_stream)
        config = {"provider": "anthropic", "model": "claude-opus-5-5", "enabled": True, "api_key": "test-key"}
        ctx = chat.ChatContext("disconnect_user", "聊天", False, None, "聊天", [], 0, "system", [], byok_config=config)
        async def scenario():
            stream = chat.run_chat(ctx, crisis=False)
            first = await anext(stream)
            assert "reply_model" in first
            assert ctx.user in chat._BYOK_USERS
            await stream.aclose()
>       asyncio.run(scenario())

tests/test_byok_chat.py:464: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<python-install>:205: in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
<python-install>:128: in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-install>:719: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    async def scenario():
        stream = chat.run_chat(ctx, crisis=False)
        first = await anext(stream)
>       assert "reply_model" in first
E       assert 'reply_model' in 'data: {"error": "你的模型调用失败：连不上该服务。本条没有改用平台模型。"}\n\n'

tests/test_byok_chat.py:461: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=connection
_______ test_r1_pending_api_free_actions_and_paid_guards[image_topic-10] _______

client = <starlette.testclient.TestClient object at 0x10fa0e140>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa95010>
amount = 10, case = 'image_topic'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[image_cancel-10] _______

client = <starlette.testclient.TestClient object at 0x10fa0d260>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fca0b40>
amount = 10, case = 'image_cancel'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
_______ test_r1_pending_api_free_actions_and_paid_guards[image_fill-10] ________

client = <starlette.testclient.TestClient object at 0x10fa9d040>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfcfa0>
amount = 10, case = 'image_fill'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
_____ test_r1_pending_api_free_actions_and_paid_guards[weather_cancel-10] ______

client = <starlette.testclient.TestClient object at 0x10fa9d590>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfd550>
amount = 10, case = 'weather_cancel'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[weather_fill-10] _______

client = <starlette.testclient.TestClient object at 0x10fa9f020>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc456a0>
amount = 10, case = 'weather_fill'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[weather_chat-10] _______

client = <starlette.testclient.TestClient object at 0x10fa9c380>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc47070>
amount = 10, case = 'weather_chat'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=7, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0] ______

client = <starlette.testclient.TestClient object at 0x10fa9fce0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc47bd0>
amount = 0, case = 'image_new_tool'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
>           assert seed[-1] == {"done": True} and get_pending(key) == pending
E           AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff)

tests/test_byok_chat.py:517: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_____ test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10] ______

client = <starlette.testclient.TestClient object at 0x10fa9e140>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdff380>
amount = 10, case = 'image_new_tool'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
>           assert seed[-1] == {"done": True} and get_pending(key) == pending
E           AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff)

tests/test_byok_chat.py:517: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
______ test_r1_pending_api_free_actions_and_paid_guards[image_thanks-10] _______

client = <starlette.testclient.TestClient object at 0x10fa9f9b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc46f20>
amount = 10, case = 'image_thanks'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
____ test_r1_pending_api_free_actions_and_paid_guards[image_discussion-10] _____

client = <starlette.testclient.TestClient object at 0x10fa9e360>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc46660>
amount = 10, case = 'image_discussion'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_____ test_r1_pending_api_free_actions_and_paid_guards[image_question-10] ______

client = <starlette.testclient.TestClient object at 0x10fa9ebe0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdff1c0>
amount = 10, case = 'image_question'

    @pytest.mark.parametrize("amount", [0, 10])
    @pytest.mark.parametrize("case", [
        "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
        "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
        "image_question", "manual_mirror", "missing_edit_reference",
    ])
    def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
        import database
        import services.chat_service as chat
        from intent_router import get_pending, set_pending
        from pathlib import Path
        from utils import media
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
        key = (user, conversation)
        calls, platform, *_ = stub_reply(monkeypatch)
        caps, generated, tools = [], [], []
    
        def classify(_client, message, history):
            if message == "帮我画张图":
                return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
            if message == "查一下北京明天天气":
                return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
            return {"intent": None, "params": {}, "missing": []}
    
        def cap(kind, username, *, hit):
            caps.append((kind, hit))
            return None
    
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return {"type": "card", "subtype": "weather", "points": ["天气晴"]}
    
        async def image(*a, **k):
            generated.append(1)
            path = "/uploads/generated_" + "e" * 32 + ".png"
            Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
            return {"image_path": path, "model": "platform-image"}
    
        monkeypatch.setattr(chat, "recognize_intent", classify)
        monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "generate_image", image)
        weather_pending = case.startswith("weather_") or case == "manual_mirror"
        pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
        if case == "image_new_tool":
            # Manufacture the pending through the real paid route, then lower balance.
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
            seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
            assert seed[-1] == {"done": True} and get_pending(key) == pending
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
            caps.clear()
        else:
            set_pending(key, pending)
        messages = {
            "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
            "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
            "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
            "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
            "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
        }
        if case == "manual_mirror":
            monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
            monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
        result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
        paid = case in {"image_fill", "weather_fill", "image_new_tool"}
        if paid and amount == 0:
            assert result == [{"error": database.strawberry_insufficient_message()}]
            assert not generated and not tools and not calls and not platform
            assert all(kind != "weather" or hit is False for kind, hit in caps)
            assert get_pending(key) == pending
            assert balance(user) == amount
        else:
            assert get_pending(key) is None
>           assert result[-1] == {"done": True}
E           AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E             
E             Left contains 1 more item:
E             {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E             Right contains 1 more item:
E             {'done': True}
E             Use -v to get more diff

tests/test_byok_chat.py:543: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
________ test_r1_reply_persistence_failure_uses_platform_error[friend] _________

client = <starlette.testclient.TestClient object at 0x10fa0fdf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa95e10>
capsys = <_pytest.capture.CaptureFixture object at 0x10fc3cbb0>, mode = 'friend'

    @pytest.mark.parametrize("mode", ["friend", "mirror"])
    def test_r1_reply_persistence_failure_uses_platform_error(client, dev_headers, monkeypatch, capsys, mode):
        import services.chat_service as chat
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
        original = chat.save_message
        async def fail_assistant(username, role, *a, **k):
            if role == "assistant":
                return False
            return await original(username, role, *a, **k)
        monkeypatch.setattr(chat, "save_message", fail_assistant)
        result = events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation}))
>       assert result[-1] == {"error": "服务暂时不可用，请稍后再试"}
E       AssertionError: assert {'error': '你的...。本条没有改用平台模型。'} == {'error': '服务暂时不可用，请稍后再试'}
E         
E         Differing items:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'error': '服务暂时不可用，请稍后再试'}
E         Use -v to get more diff

tests/test_byok_chat.py:591: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
____ test_r1_deleted_conversation_during_reply_is_platform_failure[friend] _____

client = <starlette.testclient.TestClient object at 0x10fa9f680>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10bda6350>
capsys = <_pytest.capture.CaptureFixture object at 0x10fde8ef0>, mode = 'friend'

    @pytest.mark.parametrize("mode", ["friend", "mirror"])
    def test_r1_deleted_conversation_during_reply_is_platform_failure(client, dev_headers, monkeypatch, capsys, mode):
        import database
        import services.chat_service as chat
        from agent_store import delete_conversation
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        calls, platform, *_ = stub_reply(monkeypatch)
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
        class DeletedReply(Reply):
            def __iter__(self):
                for chunk in super().__iter__():
                    yield chunk
                    # The first chunk has reached the consumer before deletion.
                    if not calls:
                        raise AssertionError("BYOK stream did not open")
                    asyncio.run(delete_conversation(user, conversation))
                    break
        def open_stream(*a, **k):
            calls.append(1)
            return DeletedReply()
        monkeypatch.setattr(chat, "open_reply_stream", open_stream)
        result = events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation}))
>       assert result[:2] == [{"reply_model": {"source": "byok", "label": "Claude · claude-opus-5-5"}}, {"text": "测试"}]
E       AssertionError: assert [{'error': '你...本条没有改用平台模型。'}] == [{'reply_mode...'text': '测试'}]
E         
E         At index 0 diff: {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'} != {'reply_model': {'source': 'byok', 'label': 'Claude · claude-opus-5-5'}}
E         Right contains one more item: {'text': '测试'}
E         Use -v to get more diff

tests/test_byok_chat.py:733: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
____________ test_r2_paid_weather_pending_routing_matches_platform _____________

client = <starlette.testclient.TestClient object at 0x10fa9d9d0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc47150>

    def test_r2_paid_weather_pending_routing_matches_platform(client, dev_headers, monkeypatch):
        """BYOK must not reinterpret a pending city's valid text as conversation."""
        import database
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending, set_pending
        snapshots = []
        for enabled in (False, True):
            monkeypatch.setenv("DEV_MODE", "1")
            user, conversation, headers = setup(client, dev_headers, monkeypatch)
            if not enabled:
                asyncio.run(delete_config(user))
            key = (user, conversation)
            set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
            calls, platform, *_ = stub_reply(monkeypatch)
            tools, caps = [], []
            card = {"type": "card", "subtype": "weather", "points": ["天气结果"]}
            def execute(intent, params):
                tools.append((intent, dict(params)))
                return card
            monkeypatch.setattr(chat, "execute_intent", execute)
            monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
            result = events(client.post("/chat", headers=headers, json={"message": "开心", "conversation_id": conversation}))
            snapshots.append((result, tools, caps, balance(user), bool(calls), bool(platform), get_pending(key)))
>           assert asyncio.run(database.get_messages(user, conversation_id=conversation))[-1]["role"] == "assistant"
E           AssertionError: assert 'user' == 'assistant'
E             
E             - assistant
E             + user

tests/test_byok_chat.py:791: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=2, detected_count=0
[硬词检测] chars=2, detected_count=0
[byok] reply failed category=connection
______ test_r2_zero_balance_other_pending_free_exits[route-\u7b97\u4e86] _______

client = <starlette.testclient.TestClient object at 0x10fa9d7b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfcde0>
intent = 'route', message = '算了'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9d7b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfcde0>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_zero_balance_other_pending_free_exits[route-\u6362\u4e2a\u8bdd\u9898] _

client = <starlette.testclient.TestClient object at 0x10fa9fdf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfcc20>
intent = 'route', message = '换个话题'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9fdf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfcc20>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_zero_balance_other_pending_free_exits[route-\u4ece\u5bb6\u51fa\u53d1] _

client = <starlette.testclient.TestClient object at 0x10fa9d8c0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfe970>
intent = 'route', message = '从家出发'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9d8c0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfe970>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
____ test_r2_zero_balance_other_pending_free_exits[web_search-\u7b97\u4e86] ____

client = <starlette.testclient.TestClient object at 0x10fa9dbf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdff310>
intent = 'web_search', message = '算了'

    @pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
    def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
        import database
        import services.chat_service as chat
        from intent_router import get_pending
>       user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:821: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9dbf0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdff310>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
_______ test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-route] ________

client = <starlette.testclient.TestClient object at 0x10fa0ff00>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfd780>
intent = 'route', message = '算了'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa0ff00>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdfd780>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[意图识别] chars=5, intent=route, missing=['origin']
[硬词检测] chars=2, detected_count=0
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_____ test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-web_search] _____

client = <starlette.testclient.TestClient object at 0x10fa9c8d0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10bda58d0>
intent = 'web_search', message = '算了'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9c8d0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10bda58d0>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=web_search, missing=['query']
[硬词检测] chars=2, detected_count=0
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-route] __

client = <starlette.testclient.TestClient object at 0x10fa9cc00>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc45080>
intent = 'route', message = '换个话题'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9cc00>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc45080>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[意图识别] chars=5, intent=route, missing=['origin']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-web_search] _

client = <starlette.testclient.TestClient object at 0x10fa9f8a0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc449f0>
intent = 'web_search', message = '换个话题'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9f8a0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc449f0>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=web_search, missing=['query']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-route] __

client = <starlette.testclient.TestClient object at 0x10fa9dae0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fbd07c0>
intent = 'route', message = '从家出发'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fa9dae0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fbd07c0>
intent = 'route', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=5, detected_count=0
[意图识别] chars=5, intent=route, missing=['origin']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=5, detected_count=0
[byok] reply failed category=connection
_ test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-web_search] _

client = <starlette.testclient.TestClient object at 0x10fbc9ae0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fbd2430>
intent = 'web_search', message = '从家出发'

    @pytest.mark.parametrize("intent", ["route", "web_search"])
    @pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
    def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
        import services.chat_service as chat
        from intent_router import get_pending
        snapshots = []
        card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
        for byok in (False, True):
>           user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_byok_chat.py:850: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

client = <starlette.testclient.TestClient object at 0x10fbc9ae0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fbd2430>
intent = 'web_search', byok = True

    def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
        """Use /chat at balance 10 to create the pending before changing credit."""
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not byok:
            asyncio.run(delete_config(user))
        message = "怎么去机场" if intent == "route" else "帮我搜点信息"
        pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
        def classify(_client, text, history):
            return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
        monkeypatch.setattr(chat, "recognize_intent", classify)
        seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
>       assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
E       AssertionError: assert ({'error': '你的...。本条没有改用平台模型。'} == {'done': True}
E         
E         Left contains 1 more item:
E         {'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}
E         Right contains 1 more item:
E         {'done': True}
E         Use -v to get more diff)

tests/test_byok_chat.py:811: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=6, detected_count=0
[意图识别] chars=6, intent=web_search, missing=['query']
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=6, detected_count=0
[byok] reply failed category=connection
________ test_r3_paid_weather_topic_exit_matches_unconfigured_platform _________

client = <starlette.testclient.TestClient object at 0x10fa9c270>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fc442f0>

    def test_r3_paid_weather_topic_exit_matches_unconfigured_platform(client, dev_headers, monkeypatch):
        import services.chat_service as chat
        from byok.store import delete_config
        from intent_router import get_pending, set_pending
        snapshots = []
        for enabled in (False, True):
            monkeypatch.setenv("DEV_MODE", "1")
            user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=10)
            if not enabled:
                asyncio.run(delete_config(user))
            key = (user, conversation)
            set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
            calls, platform, *_ = stub_reply(monkeypatch)
            tools, caps = [], []
            card = {"type": "card", "subtype": "weather", "points": ["天气结果"]}
            def execute(intent, params):
                tools.append((intent, dict(params)))
                return card
            monkeypatch.setattr(chat, "execute_intent", execute)
            monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
            result = events(client.post("/chat", headers=headers, json={"message": "换个话题", "conversation_id": conversation}))
            snapshots.append((result, tools, caps, balance(user), bool(calls), bool(platform), get_pending(key)))
>       assert snapshots[0] == snapshots[1]
E       AssertionError: assert ([{'card': {'...e, False, ...) == ([{'error': '...e, False, ...)
E         
E         At index 0 diff: [{'card': {'type': 'card', 'subtype': 'weather', 'points': ['天气结果']}}, {'done': True}] != [{'error': '你的模型调用失败：连不上该服务。本条没有改用平台模型。'}]
E         Use -v to get more diff

tests/test_byok_chat.py:969: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=4, detected_count=0
[硬词检测] chars=4, detected_count=0
[byok] reply failed category=connection
_ test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-opus-5-5] _

harness = namespace(chat=<module 'services.chat_service' from './backend/services/chat_...'unavailable', 'resp_chars': 0}], daily=[(('byok_chat', 'r1-byok-user'), {'hit': True})], replies=[], planner_calls=[])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10c407e00>
provider = 'anthropic', model = 'claude-opus-5-5'

    @pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
    def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
        h = harness
        configure(h, provider, model)
        def unexpected(*args, **kwargs):
            pytest.fail("native mode must not call planner")
        monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
        def open_reply(*args, **kwargs):
            h.replies.append((args, kwargs))
            return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
        monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
>       assert h.replies[0][1]["tools"] == "generate_image"
               ^^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_byok_planner_r1.py:235: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_ test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-sonnet-5-5] _

harness = namespace(chat=<module 'services.chat_service' from './backend/services/chat_...'unavailable', 'resp_chars': 0}], daily=[(('byok_chat', 'r1-byok-user'), {'hit': True})], replies=[], planner_calls=[])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10be216a0>
provider = 'anthropic', model = 'claude-sonnet-5-5'

    @pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
    def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
        h = harness
        configure(h, provider, model)
        def unexpected(*args, **kwargs):
            pytest.fail("native mode must not call planner")
        monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
        def open_reply(*args, **kwargs):
            h.replies.append((args, kwargs))
            return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
        monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
>       assert h.replies[0][1]["tools"] == "generate_image"
               ^^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_byok_planner_r1.py:235: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_ test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-haiku-5-5] _

harness = namespace(chat=<module 'services.chat_service' from './backend/services/chat_...'unavailable', 'resp_chars': 0}], daily=[(('byok_chat', 'r1-byok-user'), {'hit': True})], replies=[], planner_calls=[])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10be20e50>
provider = 'anthropic', model = 'claude-haiku-5-5'

    @pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
    def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
        h = harness
        configure(h, provider, model)
        def unexpected(*args, **kwargs):
            pytest.fail("native mode must not call planner")
        monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
        def open_reply(*args, **kwargs):
            h.replies.append((args, kwargs))
            return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
        monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
>       assert h.replies[0][1]["tools"] == "generate_image"
               ^^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_byok_planner_r1.py:235: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
___________ test_native_tool_route_uses_reply_model_only[candidate] ____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10cb9ea50>
kind = 'candidate'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
_____________ test_native_tool_route_uses_reply_model_only[intent] _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110a05630>
kind = 'intent'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
__________ test_native_tool_route_uses_reply_model_only[intent_error] __________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110a05710>
kind = 'intent_error'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
____________ test_native_tool_route_uses_reply_model_only[pending] _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10be6b620>
kind = 'pending'

    @pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
    def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        requests, cleared, modes = [], [], []
        ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
        ctx.messages = [{'role': 'user', 'content': ctx.message}]
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
        def detect(*a):
            modes.append(a)
            return 'mirror' if kind == 'candidate' else 'friend'
        monkeypatch.setattr(chat, 'detect_mode', detect)
        def recognize(*a):
            if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
            return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
        monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
        monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
        if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
        def opened(config, messages, **kwargs):
            requests.append((messages, kwargs))
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
>       assert len(calls) == 1 and calls[0][0] == '猫'
E       assert (0 == 1)
E        +  where 0 = len([])

tests/test_chat_image_tool.py:553: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_____________ test_switch_off_route_keeps_requests_unchanged[True] _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...', response_saved=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ea47a10>
byok = True

    @pytest.mark.parametrize('byok', [False, True])
    def test_switch_off_route_keeps_requests_unchanged(chat_harness, monkeypatch, byok):
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.message = ctx.user_content = '你好'
        monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', '0')
        requests = []
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            def opened(*a, **kwargs):
                requests.append(kwargs)
                return ByokFakeStream('免费文字', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
            monkeypatch.setattr(chat, 'open_reply_stream', opened)
        else:
            def opened(*a, **kwargs):
                requests.append(kwargs)
                return iter(tool_blocks()), False
            monkeypatch.setattr(chat, '_create_stream_with_fallback', opened)
        asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
>       assert requests
E       assert []

tests/test_chat_image_tool.py:630: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_____________ test_byok_tools_safe_system_once_including_readaloud _____________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...', response_saved=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fa2e740>

    def test_byok_tools_safe_system_once_including_readaloud(chat_harness, monkeypatch):
        from persona import BASE_SAFETY_RULES
        chat, ctx, state, saves, calls, *_ = chat_harness
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        ctx.messages.append({'role': 'system', 'content': '朗读本次结果\n\n' + BASE_SAFETY_RULES.strip()})
        requests = []
        def opened(config, messages, **kwargs):
            requests.append(messages)
            return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
>       systems = [m['content'] for m in requests[0] if m['role'] == 'system']
                                         ^^^^^^^^^^^
E       IndexError: list index out of range

tests/test_chat_image_tool.py:674: IndexError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_________ test_reserved_turn_settlement_and_single_image[success-True] _________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e9e9a90>
byok = True, outcome = 'success'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
>       assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
E       AssertionError: assert [('tool-user', 10)] == []
E         
E         Left contains one more item: ('tool-user', 10)
E         Use -v to get more diff

tests/test_chat_image_tool.py:751: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_________ test_reserved_turn_settlement_and_single_image[invalid-True] _________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fbd1d30>
byok = True, outcome = 'invalid'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
        assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
        if outcome == 'success':
            assert len(calls) == 1
            assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
            assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
            assert sum('done' in event for event in result if isinstance(event, dict)) == 1
            assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
        else:
            assert len(calls) == int(outcome == 'deleted')
>           assert sum('done' in event for event in result if isinstance(event, dict)) == int(outcome == 'invalid')
E           AssertionError: assert 0 == 1
E            +  where 0 = sum(<generator object test_reserved_turn_settlement_and_single_image.<locals>.<genexpr> at 0x1103f5000>)
E            +  and   1 = int('invalid' == 'invalid'
E               
E                 invalid)

tests/test_chat_image_tool.py:760: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
__________ test_reserved_turn_settlement_and_single_image[error-True] __________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110a07bd0>
byok = True, outcome = 'error'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
        assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
        if outcome == 'success':
            assert len(calls) == 1
            assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
            assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
            assert sum('done' in event for event in result if isinstance(event, dict)) == 1
            assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
        else:
            assert len(calls) == int(outcome == 'deleted')
            assert sum('done' in event for event in result if isinstance(event, dict)) == int(outcome == 'invalid')
        assert sum('error' in event for event in result if isinstance(event, dict)) == (0 if outcome in ('success', 'invalid') else 1)
        assert not any('tool' in event for event in result if isinstance(event, dict))
        if outcome in ('success', 'invalid'): assert len(saves) == 1
        else: assert not saves
        if outcome == 'deleted': assert deleted == ['/uploads/generated_test.png']
>       if byok and outcome == 'error': assert 'byok_error' not in traces[0]
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 'byok_error' not in {'mode': 'friend', 'intent': None, 'model': 'byok', 'has_image': False, ...}

tests/test_chat_image_tool.py:766: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
_________ test_reserved_turn_settlement_and_single_image[deleted-True] _________

chat_harness = (<module 'services.chat_service' from './backend/services/chat_service.py'>, ...=False, billable=False, crisis=False, crisis_level=None, crisis_resource_sent=False), [], [], [('tool-user', 10)], ...)
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10cb8c280>
byok = True, outcome = 'deleted'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
    def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
        chat, ctx, state, saves, calls, refunds, traces = chat_harness
        if byok:
            ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
            monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
        else:
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
            if outcome == 'invalid':
                async def unavailable_planner(*args):
                    return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
                monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
        deleted = []
        monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
        if outcome == 'error':
            async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
            monkeypatch.setattr(chat, 'generate_image', fail)
        elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
        elif outcome == 'missing':
            monkeypatch.delenv('ARK_API_KEY')
            monkeypatch.delenv('DASHSCOPE_API_KEY')
        elif outcome == 'deleted':
            original = chat.generate_image
            async def generate(*a, **kw):
                generated = await original(*a, **kw)
                async def vanished(*a): raise chat.ResourceNotFound()
                monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
                return generated
            monkeypatch.setattr(chat, 'generate_image', generate)
        monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
        result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
        assert chat.STRAWBERRY_COST_PER_REPLY == 10
        # An unavailable planner falls back to the legacy route. A delivered
        # platform text reply still settles its ordinary reservation.
        assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
        if outcome == 'success':
            assert len(calls) == 1
            assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
            assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
            assert sum('done' in event for event in result if isinstance(event, dict)) == 1
            assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
        else:
>           assert len(calls) == int(outcome == 'deleted')
E           AssertionError: assert 0 == 1
E            +  where 0 = len([])
E            +  and   1 = int('deleted' == 'deleted'
E               
E                 deleted)

tests/test_chat_image_tool.py:759: AssertionError
----------------------------- Captured stdout call -----------------------------
[byok] reply failed category=unavailable
____ test_http_paid_turn_reserves_once_and_settles_real_balance[image-True] ____

client = <starlette.testclient.TestClient object at 0x1104186b0>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10cb8c600>
byok = True, outcome = 'image'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
    def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
        """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
        import sqlite3
        from pathlib import Path
        import database
        import routers.chat as router
        import services.chat_service as chat
        from auth import create_token
        from rate_limit import limiter
        from utils import media
        monkeypatch.setattr(limiter, 'enabled', False)
        monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
        monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
        username = dev_headers['X-Dev-User']
        conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
        version = asyncio.run(database.get_session_version(username))
        headers = {'Authorization': 'Bearer ' + create_token(username, version)}
        monkeypatch.setenv('DEV_MODE', '0')
        config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
        async def config_read(*a): return config
        monkeypatch.setattr(chat, 'get_internal_config', config_read)
        reservations, refunds, generated = [], [], []
        original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
        async def reserve(*a):
            reservations.append(a)
            return await original_reserve(*a)
        async def refund(*a):
            refunds.append(a)
            return await original_refund(*a)
        monkeypatch.setattr(router, 'reserve_strawberries', reserve)
        monkeypatch.setattr(chat, 'refund_strawberries', refund)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        async def planner(*args):
            if outcome == 'text':
                return {'status': 'no'}
            if outcome == 'invalid':
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            return {'status': 'draw', 'prompt': '猫'}
        monkeypatch.setattr(chat, 'plan_image', planner)
        if byok:
            call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
        else:
            chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
        async def image(prompt, ratio, **kwargs):
            generated.append((prompt, ratio, kwargs))
            if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
            Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
            return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
        monkeypatch.setattr(chat, 'generate_image', image)
        response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
        assert response.status_code == 200
        result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
        assert reservations == [(username, 10)]
>       assert refunds == ([] if billed else [(username, 10)])
E       AssertionError: assert [('smoke_tester', 10)] == []
E         
E         Left contains one more item: ('smoke_tester', 10)
E         Use -v to get more diff

tests/test_chat_image_tool.py:891: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=8, detected_count=0
[byok] reply failed category=unavailable
___ test_http_paid_turn_reserves_once_and_settles_real_balance[invalid-True] ___

client = <starlette.testclient.TestClient object at 0x11041a470>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fdffe70>
byok = True, outcome = 'invalid'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
    def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
        """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
        import sqlite3
        from pathlib import Path
        import database
        import routers.chat as router
        import services.chat_service as chat
        from auth import create_token
        from rate_limit import limiter
        from utils import media
        monkeypatch.setattr(limiter, 'enabled', False)
        monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
        monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
        username = dev_headers['X-Dev-User']
        conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
        version = asyncio.run(database.get_session_version(username))
        headers = {'Authorization': 'Bearer ' + create_token(username, version)}
        monkeypatch.setenv('DEV_MODE', '0')
        config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
        async def config_read(*a): return config
        monkeypatch.setattr(chat, 'get_internal_config', config_read)
        reservations, refunds, generated = [], [], []
        original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
        async def reserve(*a):
            reservations.append(a)
            return await original_reserve(*a)
        async def refund(*a):
            refunds.append(a)
            return await original_refund(*a)
        monkeypatch.setattr(router, 'reserve_strawberries', reserve)
        monkeypatch.setattr(chat, 'refund_strawberries', refund)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        async def planner(*args):
            if outcome == 'text':
                return {'status': 'no'}
            if outcome == 'invalid':
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            return {'status': 'draw', 'prompt': '猫'}
        monkeypatch.setattr(chat, 'plan_image', planner)
        if byok:
            call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
        else:
            chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
        async def image(prompt, ratio, **kwargs):
            generated.append((prompt, ratio, kwargs))
            if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
            Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
            return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
        monkeypatch.setattr(chat, 'generate_image', image)
        response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
        assert response.status_code == 200
        result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
        assert reservations == [(username, 10)]
        assert refunds == ([] if billed else [(username, 10)])
        assert asyncio.run(database.get_strawberry_balance(username)) == (10 if billed else 20)
        history = client.get(f'/conversations/{conversation}/messages', headers=headers).json()['messages']
        assistants = [row for row in history if row['role'] == 'assistant']
>       assert len(assistants) == (0 if outcome == 'error' else 1)
E       assert 0 == 1
E        +  where 0 = len([])

tests/test_chat_image_tool.py:895: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=8, detected_count=0
[byok] reply failed category=unavailable
____ test_http_paid_turn_reserves_once_and_settles_real_balance[text-True] _____

client = <starlette.testclient.TestClient object at 0x10fa9c050>
dev_headers = {'X-Dev-User': 'smoke_tester'}
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10cb8c600>
byok = True, outcome = 'text'

    @pytest.mark.parametrize('byok', [False, True])
    @pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
    def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
        """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
        import sqlite3
        from pathlib import Path
        import database
        import routers.chat as router
        import services.chat_service as chat
        from auth import create_token
        from rate_limit import limiter
        from utils import media
        monkeypatch.setattr(limiter, 'enabled', False)
        monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
        monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
        username = dev_headers['X-Dev-User']
        conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
        version = asyncio.run(database.get_session_version(username))
        headers = {'Authorization': 'Bearer ' + create_token(username, version)}
        monkeypatch.setenv('DEV_MODE', '0')
        config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
        async def config_read(*a): return config
        monkeypatch.setattr(chat, 'get_internal_config', config_read)
        reservations, refunds, generated = [], [], []
        original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
        async def reserve(*a):
            reservations.append(a)
            return await original_reserve(*a)
        async def refund(*a):
            refunds.append(a)
            return await original_refund(*a)
        monkeypatch.setattr(router, 'reserve_strawberries', reserve)
        monkeypatch.setattr(chat, 'refund_strawberries', refund)
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        async def planner(*args):
            if outcome == 'text':
                return {'status': 'no'}
            if outcome == 'invalid':
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            return {'status': 'draw', 'prompt': '猫'}
        monkeypatch.setattr(chat, 'plan_image', planner)
        if byok:
            call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
            monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
        else:
            chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
            monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
        async def image(prompt, ratio, **kwargs):
            generated.append((prompt, ratio, kwargs))
            if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
            Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
            return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
        monkeypatch.setattr(chat, 'generate_image', image)
        response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
        assert response.status_code == 200
        result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
        assert reservations == [(username, 10)]
        assert refunds == ([] if billed else [(username, 10)])
        assert asyncio.run(database.get_strawberry_balance(username)) == (10 if billed else 20)
        history = client.get(f'/conversations/{conversation}/messages', headers=headers).json()['messages']
        assistants = [row for row in history if row['role'] == 'assistant']
>       assert len(assistants) == (0 if outcome == 'error' else 1)
E       assert 0 == 1
E        +  where 0 = len([])

tests/test_chat_image_tool.py:895: AssertionError
----------------------------- Captured stdout call -----------------------------
[硬词检测] chars=8, detected_count=0
[byok] reply failed category=unavailable
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  ./backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_byok_chat.py::test_reply_uses_dedicated_pool_and_refunds[10-friend]
FAILED tests/test_byok_chat.py::test_paid_branches_still_cost_ten[weather] - ...
FAILED tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image] - As...
FAILED tests/test_byok_chat.py::test_paid_branches_still_cost_ten[vision] - A...
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure0]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure1]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure2]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure3]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure4]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure5]
FAILED tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure6]
FAILED tests/test_byok_chat.py::test_empty_and_refusal_semantics[True-True]
FAILED tests/test_byok_chat.py::test_daily_cap_and_dev_mode_bypass - Assertio...
FAILED tests/test_byok_chat.py::test_disconnected_byok_stream_closes_and_releases_slot
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_topic-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_cancel-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_cancel-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_fill-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_chat-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_thanks-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_discussion-10]
FAILED tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_question-10]
FAILED tests/test_byok_chat.py::test_r1_reply_persistence_failure_uses_platform_error[friend]
FAILED tests/test_byok_chat.py::test_r1_deleted_conversation_during_reply_is_platform_failure[friend]
FAILED tests/test_byok_chat.py::test_r2_paid_weather_pending_routing_matches_platform
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-\u7b97\u4e86]
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-\u6362\u4e2a\u8bdd\u9898]
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-\u4ece\u5bb6\u51fa\u53d1]
FAILED tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[web_search-\u7b97\u4e86]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-route]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u7b97\u4e86-web_search]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-route]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u6362\u4e2a\u8bdd\u9898-web_search]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-route]
FAILED tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[\u4ece\u5bb6\u51fa\u53d1-web_search]
FAILED tests/test_byok_chat.py::test_r3_paid_weather_topic_exit_matches_unconfigured_platform
FAILED tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-opus-5-5]
FAILED tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-sonnet-5-5]
FAILED tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-haiku-5-5]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[candidate]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent_error]
FAILED tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[pending]
FAILED tests/test_chat_image_tool.py::test_switch_off_route_keeps_requests_unchanged[True]
FAILED tests/test_chat_image_tool.py::test_byok_tools_safe_system_once_including_readaloud
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[success-True]
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[invalid-True]
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[error-True]
FAILED tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[deleted-True]
FAILED tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[image-True]
FAILED tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[invalid-True]
FAILED tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[text-True]
55 failed, 3356 passed, 6 skipped, 6 deselected, 14 warnings in 101.96s (0:01:41)
````

</details>

<details>
<summary>python -m pip check（backend）；退出码 0</summary>

````text
WARNING: The directory '<pip-cache>' or its parent directory is not owned or is not writable by the current user. The cache has been disabled. Check the permissions and owner of that directory. If executing pip with sudo, you should use sudo's -H flag.
No broken requirements found.
````

</details>

<details>
<summary>npx tsc --noEmit（frontend，npm 离线模式）；退出码 0</summary>

````text
（无输出）
````

</details>

<details>
<summary>npx eslint .（frontend，npm 离线模式）；退出码 0</summary>

````text

./frontend/app/page.tsx
   149:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   240:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   539:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   592:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   593:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   594:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   604:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   605:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   606:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   607:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   610:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   616:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   617:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   921:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1015:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1439:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1459:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1467:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1488:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1530:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1626:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1985) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  2084:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  2124:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2394:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

./frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
````

</details>

<details>
<summary>git diff --check（根目录）；退出码 0</summary>

````text
（无输出）
````

</details>



最终复核（报告写入后）：再次执行受保护文件 `git diff --exit-code` 与 `git diff --check`，均退出 0、无输出；按允许文件集合核对完整 porcelain，并用 diff 的新增/删除行严格核对 conftest 例外，退出 0，实际输出：

```text
final file scope and exact conftest exception: PASS
```

## 5. 未完成或需要人工确认

实现与离线验证完成；回环端口测试受沙箱绑定权限限制，需在允许回环绑定的环境补跑，未修改或规避其既有测试。

作者需要用真实 Key 核实（本任务遵守全程离线，未发真实请求）：

1. 三型号的 `CLAUDE_SERVER_TOOLS` 版本是否可用，尤其 opus/sonnet 的 `web_search_20260209` / `web_fetch_20260209` 与 haiku 的 `web_search_20250305` / `web_fetch_20250910`，以及实际模型账户的工具权限。
2. beta 端点的 `server-side-fallback-2026-07-01`、fallbacks、effort、eager_input_streaming、缓存断点与服务器工具同时使用时的真实响应。
3. SDK 1.12.1 源码和离线夹具已核实 `WebFetchToolResultBlock` / `BetaWebFetchToolResultBlock.type == "web_fetch_tool_result"`；内部 `content.type == "web_fetch_result"`，URL 为 `content.url`，标题为 `content.content.title`。仍应核对真实账户返回的形状及 fallback/pause 情况。
4. SDK 源码及 SSE 夹具已核实 `usage.server_tool_use.web_search_requests` / `web_fetch_requests`，以及四项 token/cache usage 字段；仍需核对实际调用的次数和缓存命中。
5. 设置页搜索约每千次 10 美元按规格逐字呈现；实际收费、缓存优惠及 API 额度以 Anthropic 账户为准。

没有遇到 §6 要求停下询问的冲突，也没有遗留需要修改受保护文件或既有测试的实现项。


## R1

日期：2026-10-10。依据 `05-fix-r1.md` 完成 R1-1 至 R1-8；返修单修订的规则以本节为准。三个子代理继承主代理模型和推理档位，按文件独占并行，主代理负责 `chat_service.py`、集成测试、浅克隆及全部验收。全过程离线，无安装包、启动服务或 build/dev；未触及受保护文件或任务前既有测试，conftest 的唯一新增行保持不变。

### R1 文件变更与功能

| 文件 | 本次返修内容 |
| --- | --- |
| `backend/services/claude_agent.py` | 落库后提交计费、平台异常透传、image_failed、官方 SDK 回灌序列化、城市变体、线程图片副本、工具错误计数、段间换行、槽位/每日计数、附件实际关联路径清理 |
| `backend/services/chat_service.py` | agent_result 模式生图成功时不提前置 billable；既有面板/旧路径保存后收费顺序保留 |
| `backend/byok/client.py` | 不添加 eager_input_streaming；发送前从工具副本剥离旧字段，不修改调用方工具列表 |
| `frontend/app/page.tsx` | image_failed 状态类型与复位；工具轮 done 缺图正常收尾，面板重试与旧 error/catch 行为回归保持 |
| `backend/tests/test_claude_agent_client.py`、`test_claude_agent_runtime.py`、`test_claude_agent_integration.py`、`test_claude_agent_frontend.py`、`test_claude_agent_docs.py` | 同步本任务原新增测试；runtime/integration set_pending 直接 fail；合法小图夹具；SSR 三包检测；更新段落、收费和文档断言 |
| `backend/tests/test_claude_agent_r1_client.py`、`test_claude_agent_r1_runtime.py`、`test_claude_agent_r1_integration.py`、`test_claude_agent_r1_frontend.py`（新增） | 全部返修回归，包括实际 wire JSON nullable 字段、退款/断开/失败保存、Pillow 大小与 MIME、工具失败 followups、裸源码/Node 事件序列、预算图片竞态 |
| `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example` | 同步落库后结算、失败退款、城市行政变体、图片副本上限、image_failed、工具错误和新的循环边界 |
| `docs/tasks/2026-10-10-claude-agent/03-report.md`、同目录 `acceptance/r1-*`（新增） | 追加本节；完整输出、实际命令元数据和退出码独立归档 |

本次返修没有改动 `02-spec.md`、`04-review.md`、`05-fix-r1.md`。整体任务的其他文件变更仍见原报告 §1；任务前测试唯一差异仍是 conftest 的指定一行。

### R1 逐项对应

| 返修项 | 实现与测试证据 | 原规格对应 |
| --- | --- | --- |
| R1-1 | 局部 billable_pending 累加，只在 response_saved 成功后提交；卡片后保存 RuntimeError/ResourceNotFound、断开、图片成功后保存失败都退款，附件清理；shield 保存期间取消且事务成功仍成立计费 | §3.6 |
| R1-2 | 精确发送 `{"status":"image_failed","source":"tool"}` 并把失败回灌 Claude；前端清状态/生成标志，工具 done 缺图通过；Node 完整事件序列保留正文/TTS，面板失败仍有重试 | §3.3、§4 |
| R1-3 | 采用 Anthropic 1.12.1 实际请求构造的 openapi_model_dump；真实 SDK 类型及实际二次请求 wire JSON 保留 title:null、document_title:null、page_age:null | §3.2 |
| R1-4 | 原样/规范化/去一个最长行政后缀候选，至少两字；比较当前及最近三条 user 的原文和规范化文本，查询匹配写法再 normalize；北京→北京市、那曲市天气→那曲及长行政后缀通过，单字和 system/记忆城市拒绝 | §3.3、§6.4 |
| R1-5 | 五个客户端工具定义和请求均不带 eager_input_streaming；三个型号真实 SDK 请求断言；文档/原任务测试同步 | 修订 §3.1 |
| R1-6 | Pillow 在 asyncio.to_thread 中处理发给 Claude 的副本：长边 2000、3,500,000 字节；透明 PNG 保留 PNG，其余 JPEG85，超大继续每步缩至 85%；小图 base64 原样，MIME 按实际编码；上传文件不改 | §3.1、§6.8 |
| R1-7 | SSR 先 require.resolve 检查 typescript/react/react-dom/server；缺包写明原因并 skip；固定标题/仅来源/append 不改 cardData 的源码断言继续运行；深度 1、无 node_modules 的副本新测试全部通过或跳过，完整工作区 SSR 3 条实际通过 | §4、§6.11 |
| R1-8 | 下表逐一覆盖全部八个小修 | §2、§3.2、§3.5、§3.6、§6 |

| R1-8 子项 | 实现与覆盖 |
| --- | --- |
| 1 不写 pending | runtime harness 与 integration lifecycle 的 set_pending 均直接 pytest.fail，覆盖正常、缺参、未授权城市、镜子等任务新测试 |
| 2 工具错误 | agent_tool_errors 累加；生图适配器临时 error 恢复原值，工具失败不置整轮 error；真实 SDK 集成验证普通 followups 继续 |
| 3 平台错误 | pending 读/清、mode、会话确认、首槽非 busy 异常及每日计数异常透传 run_chat，保留平台通用文案和清理 |
| 4 来源单独失败 | 无交付且续请求失败不追加来源卡、不保存；已交付内容仍按原规则保存 |
| 5 多步文字 | 后续请求首段正文前先发送两个换行并同样保存；换行纳入 8000 字上限，天气→图片→作答集成精确比对 |
| 6 槽位繁忙 | 保留「自带模型通道繁忙，请稍后再试」，忙时不计每日次数 |
| 7 byok_chat 时机 | 首次成功取得全局槽后计一次，测试断言计数时 _BYOK_ACTIVE==1，多步只计一次 |
| 8 图片预算竞态 | 使用实际 persisted_image_path 判断关联；预算与图片完成同时发生，图片落库或删除；先存部分文字且图片尚未交付时也删除该未关联附件 |

原规格 §1 的开关/条件/旧路径、§2 的 friend/mirror 与危机路由、§3.4 的工具说明均继续由本任务新测试验证；§5 六文档已同步返修；§6 的文件、离线、测试先行和分工约束及 §7 全部验收结果如下。

SDK 序列化源码位置：`backend/.venv/lib/python3.14/site-packages/anthropic/_utils/_json.py:53–57` 的 `openapi_model_dump`，以 `mode="json", by_alias=True, exclude_unset=True` 及 `__api_exclude__` 导出；实际请求构造 `anthropic/_utils/_prepare.py:124` 的 `prepare_request_data` BaseModel 分支调用它，JSON encoder 在 `_json.py:67` 也调用它。没有使用 exclude_none。

### R1 测试先行

| 改对应代码之前 | 实际输出摘要 | 退出码 | 完整记录 |
| --- | --- | --- | --- |
| client | `12 failed, 19 passed in 1.12s` | 1 | [完整输出](acceptance/r1-red-client.txt) / [退出码](acceptance/r1-red-client.exit) |
| runtime | `24 failed, 2 passed in 1.18s` | 1 | [完整输出](acceptance/r1-red-runtime.txt) / [退出码](acceptance/r1-red-runtime.exit) |
| 主代理集成/适配 | `10 failed in 1.40s` | 1 | [完整输出](acceptance/r1-red-integration.txt) / [退出码](acceptance/r1-red-integration.exit) |
| frontend/docs | `12 failed, 14 passed in 0.40s` | 1 | [完整输出](acceptance/r1-red-frontend-docs.txt) / [退出码](acceptance/r1-red-frontend-docs.exit) |
| 文字已存但图片未关联竞态 | `1 failed, 2 passed, 26 deselected in 1.00s` | 1 | [完整输出](acceptance/r1-red-image-handoff.txt) / [退出码](acceptance/r1-red-image-handoff.exit) |
| 调用 Claude 前的槽位/每日计数异常 | `2 failed, 29 deselected in 0.97s` | 1 | [完整输出](acceptance/r1-red-platform-admission.txt) / [退出码](acceptance/r1-red-platform-admission.exit) |

联跑最初还发现两条原任务新增集成断言需同步段间换行，以及测试图片绝对路径不符合 `/uploads/<basename>` 清理契约；已更新任务后新增夹具，使用临时 UPLOADS_DIR 与实际删除函数验证。任务前既有测试没有改动。

### R1 验收实际输出与退出码

backend 使用已有 .venv，把 bin 加入 PATH 后执行 python；测试及其 Python 子进程加载临时 socket/DNS 硬拦截器。npx 使用已安装工具并设置 NPM_CONFIG_OFFLINE=true。浅克隆通过本地 file 协议执行 git clone --depth 1；未跟踪/已改工作树文件复制到副本，复用源工作区 Python 环境，不复制 .venv 或 node_modules。完整日志仅将本机绝对路径替换为相对路径/占位符，未删减 traceback。

| 验收命令/项目 | 实际输出 | 退出码 | 完整记录 |
| --- | --- | --- | --- |
| `git status --porcelain` | `仅允许路径；详见完整输出` | 0 | [完整输出](acceptance/r1-status.txt) / [退出码](acceptance/r1-status.exit) |
| `git status --porcelain --untracked-files=all` | `完整文件列表，范围检查通过` | 0 | [完整输出](acceptance/r1-status-all.txt) / [退出码](acceptance/r1-status-all.exit) |
| `git diff --exit-code -- [§7 所列全部受保护路径]` | `（无输出）` | 0 | [完整输出](acceptance/r1-protected.txt) / [退出码](acceptance/r1-protected.exit) |
| `git diff --name-only -- backend/tests` | `backend/tests/conftest.py` | 0 | [完整输出](acceptance/r1-existing-tests.txt) / [退出码](acceptance/r1-existing-tests.exit) |
| `git diff -- backend/tests/conftest.py` | `仅新增指定 setdefault 行` | 0 | [完整输出](acceptance/r1-conftest.txt) / [退出码](acceptance/r1-conftest.exit) |
| `允许文件与 conftest 精确新增/删除检查` | `conftest.py: exactly 1 insertion, 0 deletions; specified setdefault line` | 0 | [完整输出](acceptance/r1-constraints.txt) / [退出码](acceptance/r1-constraints.exit) |
| `python -m pytest -q` | `1 failed, 3475 passed, 6 skipped, 14 warnings, 5 errors in 89.97s (0:01:29)` | 1 | [完整输出](acceptance/r1-pytest-default.txt) / [退出码](acceptance/r1-pytest-default.exit) |
| `FIONA_CLAUDE_AGENT=1 python -m pytest -q` | `56 failed, 3420 passed, 6 skipped, 14 warnings, 5 errors in 90.01s (0:01:30)` | 1 | [完整输出](acceptance/r1-pytest-enabled.txt) / [退出码](acceptance/r1-pytest-enabled.exit) |
| `python -m pytest -q --deselect=…（同一六项环境限制）` | `3475 passed, 6 skipped, 6 deselected, 14 warnings in 88.39s (0:01:28)` | 0 | [完整输出](acceptance/r1-pytest-default-no-loopback.txt) / [退出码](acceptance/r1-pytest-default-no-loopback.exit) |
| `FIONA_CLAUDE_AGENT=1 python -m pytest -q --deselect=…（同一六项）` | `55 failed, 3420 passed, 6 skipped, 6 deselected, 14 warnings in 88.41s (0:01:28)` | 1 | [完整输出](acceptance/r1-pytest-enabled-no-loopback.txt) / [退出码](acceptance/r1-pytest-enabled-no-loopback.exit) |
| `python -m pytest -q tests/test_claude_agent_*.py` | `193 passed in 3.45s` | 0 | [完整输出](acceptance/r1-pytest-new.txt) / [退出码](acceptance/r1-pytest-new.exit) |
| `git clone --depth 1（本地 file 协议）` | `HEAD commit count: 1；frontend/node_modules: absent` | 0 | [完整输出](acceptance/r1-shallow-clone.txt) / [退出码](acceptance/r1-shallow-clone.exit) |
| `浅克隆：python -m pytest -q -rs tests/test_claude_agent_*.py` | `190 passed, 3 skipped in 2.77s` | 0 | [完整输出](acceptance/r1-pytest-shallow.txt) / [退出码](acceptance/r1-pytest-shallow.exit) |
| `完整工作区：三条 SSR 渲染用例` | `3 passed, 24 deselected in 0.80s` | 0 | [完整输出](acceptance/r1-pytest-ssr.txt) / [退出码](acceptance/r1-pytest-ssr.exit) |
| `python -m pytest -v -rs tests/test_byok_client.py -k loopback` | `====================== 6 skipped, 124 deselected in 0.84s ======================` | 0 | [完整输出](acceptance/r1-loopback-skips.txt) / [退出码](acceptance/r1-loopback-skips.exit) |
| `python -m pip check` | `No broken requirements found.（缓存权限 warning）` | 0 | [完整输出](acceptance/r1-pip-check.txt) / [退出码](acceptance/r1-pip-check.exit) |
| `npx tsc --noEmit` | `（无输出）；0 errors` | 0 | [完整输出](acceptance/r1-tsc.txt) / [退出码](acceptance/r1-tsc.exit) |
| `npx eslint .` | `25 problems (0 errors, 25 warnings)` | 0 | [完整输出](acceptance/r1-eslint.txt) / [退出码](acceptance/r1-eslint.exit) |
| `git diff --check` | `（无输出）` | 0 | [完整输出](acceptance/r1-diff-check.txt) / [退出码](acceptance/r1-diff-check.exit) |

浅克隆只跳过三条 React SSR，实际原因是 typescript、react、react-dom/server 不可解析；裸源码来源卡、append 以及 Node 事件序列仍执行通过。完整工作区本任务新测试无跳过，三条 SSR 另单独执行通过。

受保护文件命令逐字为：

```sh
git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/database.py backend/byok/crypto.py backend/byok/url_safety.py backend/byok/store.py backend/routers/chat_model.py backend/utils/safe_http.py backend/tools
```

默认完整验收的非零退出仅来自以下六个沙箱回环 bind 限制；排除同一组后默认全部通过。开启完整验收另有 55 项旧 Anthropic 路由预期变化，逐条列在下表；开启排除六项环境限制后没有其他 error，新增测试、平台/DeepSeek 和危机路径无额外失败。

### R1 环境限制（每条一行）

| 用例 | 实际原因 |
| --- | --- |
| `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` | 绑定 127.0.0.1:0 时 PermissionError: [Errno 1] Operation not permitted；默认/开启都相同，测试未修改 |
| `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` | 绑定 127.0.0.1:0 时 PermissionError: [Errno 1] Operation not permitted；默认/开启都相同，测试未修改 |
| `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` | 绑定 127.0.0.1:0 时 PermissionError: [Errno 1] Operation not permitted；默认/开启都相同，测试未修改 |
| `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` | 绑定 127.0.0.1:0 时 PermissionError: [Errno 1] Operation not permitted；默认/开启都相同，测试未修改 |
| `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` | 绑定 127.0.0.1:0 时 PermissionError: [Errno 1] Operation not permitted；默认/开启都相同，测试未修改 |
| `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` | 绑定 127.0.0.1:0 时 PermissionError: [Errno 1] Operation not permitted；默认/开启都相同，测试未修改 |

另有六个既有 BYOK loopback 参数用例由既有代码自行 skip：watchdog（deepseek/anthropic）、interrupt race（watchdog/cancel × deepseek/anthropic）。完整退出码/skip 原因见上表 loopback 记录，共十二项回环限制需在可绑定端口的环境补验。

### R1 开启后的全部旧预期差异（55 项）

旧夹具桩住 open_reply_stream，但新智能体通过独立 open_agent_stream；离线守卫阻止真实 TCP/DNS。pending、工具/看图、模式和收费变化按规格发生。下列每项附实际原因及规格章节，属于授权允许的旧 Anthropic BYOK 预期差异。

| 失败用例 | 实际原因 | 规格依据 |
| --- | --- | --- |
| `tests/test_byok_chat.py::test_reply_uses_dedicated_pool_and_refunds[10-friend]` | 余额 10 friend 满足智能体条件；新入口绕过只桩旧 open_reply_stream 的夹具，旧调用计数为 0。 | §1、§3.1 |
| `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[weather]` | 天气由 Claude 调度，不再按旧平台意图桩直接执行；新 Claude 请求被离线守卫拒绝。 | §2.3、§3.3 |
| `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image]` | 生图由 Claude 客户端工具调度，旧识别器/单轮回复桩未执行，新入口未打桩。 | §1、§2.3、§3.3 |
| `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[vision]` | 当前图片直接给 Claude；旧平台视觉桩不执行，直接看图免费；新 Claude 入口未被旧夹具打桩。 | §3.1、§3.6 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure0]` | 旧入口注入的 401 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure1]` | 旧入口注入的 404 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure2]` | 旧入口注入的 429 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure3]` | 旧入口注入的 超时 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure4]` | 新请求的离线连接错误文案与旧注入连接错误相同，但旧入口未调用，旧计数断言失败。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure5]` | 旧入口注入的 NeedsReentryError 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_error_mapping_no_fallback_refund_or_secret[failure6]` | 旧入口注入的 ByokUnavailableError 未执行；新 agent 入口被离线守卫拒绝，实际为固定连接错误。 | §3.1 |
| `tests/test_byok_chat.py::test_empty_and_refusal_semantics[True-True]` | 旧单轮流的部分文本/拒答桩未执行；新请求未被该桩接住，先发生离线连接错误。 | §3.1、§3.2 |
| `tests/test_byok_chat.py::test_daily_cap_and_dev_mode_bypass` | 第一次新入口请求未打桩，未到旧预期 done；每日次数仍每轮一次，由新测试验证。 | §3.1、§3.2 |
| `tests/test_byok_chat.py::test_disconnected_byok_stream_closes_and_releases_slot` | 直接构造的已启用 Anthropic ctx 改走新入口，首事件为离线连接错误，旧流的断开模拟没有开始。 | §1、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_topic-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_cancel-10]` | 智能体先清 pending，并由 Claude 回复，旧平台免费取消的固定事件序列不再用于此付费智能体轮。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]` | 智能体清 pending，不走旧平台补参；天气/生图改由 Claude 工具调度，旧桩未接住新请求。 | §2.1、§3.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_cancel-10]` | 智能体先清 pending，并由 Claude 回复，旧平台免费取消的固定事件序列不再用于此付费智能体轮。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_fill-10]` | 智能体清 pending，不走旧平台补参；天气/生图改由 Claude 工具调度，旧桩未接住新请求。 | §2.1、§3.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[weather_chat-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]` | 失败发生在余额 10 的前置 seed：智能体不通过平台识别创建 pending；带 -0 的例子尚未降余额，零余额实际请求没有执行。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]` | 失败发生在余额 10 的前置 seed：智能体不通过平台识别创建 pending，旧 seed 断言失败，后续请求尚未执行。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_thanks-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_discussion-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_question-10]` | 进入时清 pending，friend 使用新 Claude 入口；旧文本/讨论/感谢回复桩未执行。 | §2.1、§2.3、§3.1 |
| `tests/test_byok_chat.py::test_r1_reply_persistence_failure_uses_platform_error[friend]` | friend 新入口未打桩，保存前先连接失败；旧保存失败注入未触发。镜子对应兼容问题已修复，最终不再失败。 | §3.1 |
| `tests/test_byok_chat.py::test_r1_deleted_conversation_during_reply_is_platform_failure[friend]` | friend 不创建旧 DeletedReply，因此旧删除模拟未执行。镜子对应兼容问题已修复，最终不再失败。 | §3.1 |
| `tests/test_byok_chat.py::test_r2_paid_weather_pending_routing_matches_platform` | 已配置 Claude 清 pending 并自行调度，与未配置的平台旧补参快照不同；新请求未被旧入口桩接住。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-算了]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-换个话题]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[route-从家出发]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_zero_balance_other_pending_free_exits[web_search-算了]` | 在余额 10 的 _r2_seed_other_pending 前置阶段失败（旧测试第 811 行）；尚未 UPDATE 到 0，零余额请求未执行。智能体不创建旧平台 pending。 | §1、§2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[算了-route]` | 余额 10 的 Anthropic 前置 seed（旧测试第 811 行）不再通过平台意图识别创建 pending，旧 seed 断言失败，尚未执行后续付费请求与快照比较。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[算了-web_search]` | 余额 10 的 Anthropic 前置 seed（旧测试第 811 行）不再通过平台意图识别创建 pending，旧 seed 断言失败，尚未执行后续付费请求与快照比较。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[换个话题-route]` | 余额 10 的 Anthropic 前置 seed（旧测试第 811 行）不再通过平台意图识别创建 pending，旧 seed 断言失败，尚未执行后续付费请求与快照比较。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[换个话题-web_search]` | 余额 10 的 Anthropic 前置 seed（旧测试第 811 行）不再通过平台意图识别创建 pending，旧 seed 断言失败，尚未执行后续付费请求与快照比较。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[从家出发-route]` | 余额 10 的 Anthropic 前置 seed（旧测试第 811 行）不再通过平台意图识别创建 pending，旧 seed 断言失败，尚未执行后续付费请求与快照比较。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r2_paid_other_pending_matches_platform[从家出发-web_search]` | 余额 10 的 Anthropic 前置 seed（旧测试第 811 行）不再通过平台意图识别创建 pending，旧 seed 断言失败，尚未执行后续付费请求与快照比较。 | §2.1、§2.3 |
| `tests/test_byok_chat.py::test_r3_paid_weather_topic_exit_matches_unconfigured_platform` | 已配置 Claude 清 pending 并自行调度，与未配置的平台旧补参快照不同；新请求未被旧入口桩接住。 | §2.1、§2.3 |
| `tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-opus-5-5]` | 旧测试只桩 open_reply_stream 并期待 native generate_image；新入口未被桩且测试 BYOK 环境不可用，replies 为空。 | §1、§2.3、§3.1 |
| `tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-sonnet-5-5]` | 旧测试只桩 open_reply_stream 并期待 native generate_image；新入口未被桩且测试 BYOK 环境不可用，replies 为空。 | §1、§2.3、§3.1 |
| `tests/test_byok_planner_r1.py::test_r1_native_still_calls_reply_tools_without_planner[anthropic-claude-haiku-5-5]` | 旧测试只桩 open_reply_stream 并期待 native generate_image；新入口未被桩且测试 BYOK 环境不可用，replies 为空。 | §1、§2.3、§3.1 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[candidate]` | detect_mode 桩返回 mirror；新路径按模式转交既有无工具镜子流，旧预期绕过模式判定并生图不再成立。 | §2.2、§2.3 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent]` | friend 不调用平台意图识别或旧 native 入口；旧生图桩未执行，新入口在测试中不可用。 | §1、§2.3 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[intent_error]` | friend 不调用平台意图识别或旧 native 入口；旧生图桩未执行，新入口在测试中不可用。 | §1、§2.3 |
| `tests/test_chat_image_tool.py::test_native_tool_route_uses_reply_model_only[pending]` | 进入后清除 pending，不按旧补参直接生图；新 Claude 入口未被旧桩接住，生图调用为 0。 | §2.1、§2.3 |
| `tests/test_chat_image_tool.py::test_switch_off_route_keeps_requests_unchanged[True]` | 此例仅关闭 FIONA_CHAT_IMAGE_TOOL；新 FIONA_CLAUDE_AGENT 仍开启且优先路由，旧请求捕获为空。 | §1 |
| `tests/test_chat_image_tool.py::test_byok_tools_safe_system_once_including_readaloud` | 旧断言读取 open_reply_stream 桩的 system；新请求在 open_agent_stream 构造，旧捕获为空；安全唯一末尾由新 SDK 测试另行验证。 | §3.1 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[success-True]` | 旧 native 成功图桩未执行；新 Claude 入口不可用，未交付计费项，因此退款而非旧成功结算。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[invalid-True]` | 旧 invalid-tool 桩未执行；错误发生于新 Claude 请求，无交付，故没有旧固定提示/落库/done。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[error-True]` | 未进入旧生图审核失败桩，实际为新 Claude 请求 unavailable，故 trace 含 byok_error。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_reserved_turn_settlement_and_single_image[deleted-True]` | 旧生图后删除模拟未执行；新入口先不可用，旧生图调用计数为 0。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[image-True]` | 旧单轮回复/成功图桩未执行；新入口不可用且无交付，预扣被退款。 | §1、§3.6 |
| `tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[invalid-True]` | 旧单轮文本/invalid-tool 桩未执行；新请求不可用且无交付，因此不产生旧预期的 assistant 记录。 | §2.3、§3.1、§3.6 |
| `tests/test_chat_image_tool.py::test_http_paid_turn_reserves_once_and_settles_real_balance[text-True]` | 旧单轮文本/invalid-tool 桩未执行；新请求不可用且无交付，因此不产生旧预期的 assistant 记录。 | §2.3、§3.1、§3.6 |

### R1 未完成或人工确认

R1-1 至 R1-8 实现及全部离线验收已完成，没有需修改受保护文件/既有测试的遗留项，也没有遇到 §6 的停下询问条件。沙箱内十二项回环相关用例需由作者在允许绑定端口的环境补验。

作者仍需用真实 Key 核实：三个型号的服务器工具版本及账户权限；beta 的 server-side-fallback-2026-07-01、fallbacks、effort、cache 与服务器工具组合；实际 web_search_tool_result/web_fetch_tool_result（内部 web_fetch_result）结构及 nullable 引用回灌；usage.server_tool_use.web_search_requests/web_fetch_requests 和 token/cache 用量；处理后的 PNG/JPEG 在真实接口中的接受情况、一次成功图的存储/扣费与失败工具后续作答。eager_input_streaming 已删除，无需验证其组合。规格设置页价格文案仍需以账户实际计费核对。

报告与日志写入后再次核对：95 个工作树文件均在允许范围（含作者任务资料与验收归档）；受保护文件零 diff、既有测试仅 conftest 指定一行、git diff --check 均退出 0。最终输出已更新到上述对应 acceptance 文件。

开启验收的 command.json 另记 FIONA_CLAUDE_AGENT=1；浅克隆的本地 file 协议、深度和副本路径占位符另存于 [命令元数据](acceptance/r1-shallow-clone.command.json)。
