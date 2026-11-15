# 多智能体讨论群：现状调查

调查日期 2026-11-14，基线 `859e2c5`。三路只读调查（Claude 子代理）加规格作者亲自核对。路径都相对仓库根；标「推断」的条目没有在代码里直接看到，写规格前须逐条裁决。

## 一、调研类工具与额度（第三路）

### 1. 联网搜索

- 平台侧只有一个底层通道：`backend/tools/topic_expand.py:23` 的 `_request_search(messages, api_key, *, max_tokens=900)`。DashScope 原生接口，模型 `qwen-plus`，`enable_search` 加 `forced_search / enable_source / enable_citation`，`temperature=0.3`，`urllib` 的 30 秒 socket 超时，不重试，响应超过 1,000,000 字节报错。（作者已核对 `topic_expand.py:20-49`。）
- 通用入口 `backend/tools/native_search.py:13` 的 `grounded_search(messages, *, max_tokens, max_sources=5) -> {"data","raw","sources","error"}`：同步函数；缺 Key 返回 `missing_key`；`finish_reason == "length"` 返回 `truncated`；正文里用正则取 JSON；来源只取 `output.search_info.search_results`，经 `card_detail._search_sources` 做格式校验、去重、被引用的排前，再截到 `max_sources`；异常只返回异常类名。（作者已核对全文。）
- `_search_sources`（`backend/tools/card_detail.py:44-86`）最多读前 50 条、最多返回 12 条，`validate_public_http_link` 只校验链接格式，不访问来源站点。
- `web_search(query)`、`travel_plan(query)`、`topic_expand(title)`、`card_detail(title, context)` 都是它的上层封装，卡片形态，不适合直接给智能体当原料。
- `web_search`、`travel_plan` 没有每日上限，只在聊天里出卡成功时按工具扣 10 颗草莓（`backend/services/chat_service.py:88-90,130-135`）。热点展开、卡片详情的每日上限加在路由层。
- 这些函数只依赖 `utils`，与 HTTP、SSE 无耦合，聊天里经 `utils/slow_pool.run_slow` 放进线程池（默认 16 线程，调用方取消后线程照样跑完）。

### 2. 读网页

- `backend/utils/safe_http.py:386` 的 `request_public_url(method, url, *, headers=None, timeout=5, max_bytes=1_000_000, follow_redirects=False, max_redirects=3)`：只允许 GET/HEAD、http/https 默认端口、URL ≤2048；拒绝带用户名密码的 URL；DNS 结果只要有一个不是公网地址就拒绝；校验后直连已校验的 IP（SNI 与证书仍用原主机名）；逐跳重定向重新校验；按解压后字节计数；另有绝对墙钟看门狗。
- `backend/tools/fetch_card.py:94` 的 `_extract_main_text(html, max_chars=5000)`：BeautifulSoup `html.parser`，删 script/style/nav/header/footer/aside/iframe 后依次取 article、main、body。
- `fetch_card.py` 在模块顶层 `import llm`，`llm` 导入时构造 DashScope 客户端。
- 正文抽取依赖只有 `beautifulsoup4`；没有 readability、lxml。不做 JS 渲染，不检查 Content-Type，不解析 PDF；解码只看响应头的 charset（推断：GBK 页面可能乱码）。

### 3. Claude 智能体循环

- `backend/services/claude_agent.py:382` 的 `stream_claude_agent(ctx, state)` 与聊天的 `ChatContext`、`ChatState`、SSE、pending、落库强耦合，后台任务不能直接复用。
- 下层 `backend/byok/client.py:431` 的 `open_agent_stream` 可单独调用，但写死了聊天工具说明、每次追加 web 工具（`web_search_20250305` 最多 5 次、`web_fetch_20250910` 最多 3 次）、单次 4000 字。
- 每用户一条流与全局并发槽在 `backend/services/chat_service.py:192-217` 的 `_byok_slot`；后台任务若占着每用户锁，会让该用户的聊天报「正在回复上一条」（推断）。

### 4. BYOK

- 厂商：dashscope、deepseek、moonshot、zhipu、custom（OpenAI 类）与 anthropic（`backend/byok/providers.py:9-19`）。
- `byok/` 里没有非流式入口。现成的非流式实现三处：小说 `backend/novel/llm_router.py:163-240`、工作室 `backend/studio/brain.py:282-363`、本机监控 `backend/services/local_watch.py:115-139`。
- 后台取 Key：`byok.store.get_internal_config(username)`（`backend/byok/store.py:110-125`）；小说再包一层 `ByokBridge.resolve()`（`backend/novel/byok_bridge.py:16-61`），只允许 anthropic、dashscope、deepseek 与已知型号。
- 小说与工作室走 BYOK 时都不经过 `_byok_slot`，小说用自己的 `FIONA_NOVEL_MAX_RUNNING` 信号量。

### 5. 平台模型（按代码实际用法）

| 模型 | 用途 | Key 变量 | 联网 | JSON 模式 |
|---|---|---|---|---|
| `qwen3.8-omni-flash` | 主聊天、意图、看图 | `DASHSCOPE_API_KEY` | 否 | 是 |
| `qwen3.8-flash` | 轻量、危机复核、判断器 | `DASHSCOPE_API_KEY` | 否 | 是 |
| `qwen-plus`（原生接口） | 搜索类工具 | `DASHSCOPE_API_KEY` | 强制 | 否，靠提示词加正则 |
| 小说 `dashscope:qwen3.8-max`、`deepseek:deepseek-flash`、`ark:doubao-seed-2-1-pro-260915` | 小说工坊 | `DASHSCOPE_API_KEY` / `DEEPSEEK_API_KEY` / `ARK_API_KEY` | 否 | json 输出时加 `json_object` |
| 工作室 `qwen3.8-max`、`deepseek-flash` / `deepseek-v4-pro` | 导演、拆解 | 同上 | 否 | 是 |

平台模型在代码里从不传 `tools=`；只有 BYOK 路径带工具。Claude 只能经 BYOK 使用。

### 6. 草莓与每日上限

- `backend/database.py:1774` `reserve_strawberries(username, amount)`（`BEGIN IMMEDIATE`、条件扣减）；`:1792` `refund_strawberries`。没有 settle 函数，聊天的结算就是不退款。
- 小说有按步骤的账本（`backend/novel/billing.py:187-297`）：每步预扣、结算、退款，各自 `BEGIN IMMEDIATE`，记在 `novel_steps`。
- `backend/rate_limit.py:63-74` 的 `_DAILY_SETTINGS` 实际有 10 项，进程内存计数；文档（CLAUDE.md、README、ARCHITECTURE）写的是「八项」，与代码不一致。官方体验、写歌、工作室用数据库计数。
- 新增一项每日上限：`_DAILY_SETTINGS` 加一项、`daily_cap_message` 加文案、调用处用 `check_daily_cap` 或 `check_chat_daily_cap`；要重启不清零就在数据库事务里计数。

### 7. 用户资料输入

- 聊天只能传图片（PNG/JPEG/GIF/WebP，≤5MB）；不能上传文档。
- 唯一的文档解析：`backend/studio/sources.py:198-249` 的 `normalize_text(raw, filename=None)`，支持 txt、md、docx（标准库解包），文件 ≤10MB、正文 ≤50 万字，出错抛 `HTTPException`。
- 没有 PDF、表格解析，依赖里也没有对应的库。

### 8. 成果导出

- 现有导出只有 Markdown：小说 `backend/novel/service.py:990-1006`、分身交流 `backend/exchange_exports.py:12-150`、工作室拆解 `backend/studio/breakdown_plan.py:645-693`。没有 PDF 或 Word 导出。

### 9. 安全

- 危机检查（`backend/safety.py` 规则加 `backend/crisis_model.py` 复核）只在 `/chat` 路径调用；小说、工作室、分身交流、写歌都不调用。
- 小说在每张智能体卡片的系统提示里加 `NOVEL_SAFETY_RULES` 与 `INJECTION_GUARD`（`backend/novel/agent_pool.py:14,197-206`）；分身交流在系统提示末尾加 `BASE_SAFETY_RULES`。
- 没有任何输出侧内容审核模型；只有 schema 校验，以及把厂商的 content_filter、refusal 映射成失败。
- 测试断网：`backend/tests/conftest.py:49-88` 的 socket 与 DNS 阻断只对文件名以 `test_studio_` 开头的测试生效（作者已核对 `:52`）；其他测试各自用 autouse fixture 打桩。CLAUDE.md 说「收集阶段阻断真实网络与 DNS」，与实际作用域不一致。
- 打桩样板：搜索直接 monkeypatch `native_search._request_search`（`backend/tests/test_search_real_sources.py:49-56`）；小说的单一注入点 `router_factory`（`backend/novel/runner.py:61-64`）。

### 10. 隐私披露惯例

新增会把用户内容发给第三方厂商的功能，现有样板在这几处写明「发给谁、发了什么、没发什么、日志和 Key 怎么处理」：CLAUDE.md 功能小节的「隐私」段、README、docs/ARCHITECTURE.md 的系统边界图与对应小节、PLAN.md 按日期的条目、docs/DEPLOYMENT.md 的环境变量表与厂商消费告警清单、前端界面里的提示文案（如 `frontend/components/ChatModelSection.tsx:345-378`）。

### 小结：只用平台模型时现在就有的调研能力与缺口

现成：带可核实来源的联网搜索（`grounded_search`）；读公网网页正文（`request_public_url` 加 `_extract_main_text`）；读 txt / md / docx；多家平台模型的 JSON 输出。

缺：PDF 与表格解析；JS 渲染与深度抓取；平台模型的原生工具调用（分工调度要用 JSON 协议自己编排）；搜索与读网页的每日上限和按调用计费；输出侧内容审核与后台路径的危机检查；PDF 或 Word 导出；带 usage 的统一非流式平台调用器（小说与工作室各有一套）。

## 二、多智能体运行底座（第一路）

### 1. 小说工坊的模型调用器 `backend/novel/llm_router.py`

- 入口 `LLMRouter(store, *, fake=None, dry_run=False, billing=None, byok_bridge=None)`；`await router.call(*, step_key, role, model, messages, max_tokens, validator=None, output="json", experiment=None, arm="", chapter=0, failure_status="step_failed")`（`:153`、`:386-401`）。
- 同一 `step_key` 已有成功记录就直接返回缓存，这是续跑不重复付费的关键（`:391-395`）。
- 模型规格写成 `厂商:型号`：`dashscope`、`deepseek`、`ark`、`anthropic`、`fake`、`byok:self`（`:18-40`、`:66-71`）。OpenAI 兼容厂商在 `output=="json"` 时传 `response_format={"type":"json_object"}`；思考一律关闭。
- 每次 SDK 请求 `timeout=300`、`max_retries=0`；网络类错误重试 1 次，校验失败或被截断回灌错误修正 1 次；计费类异常不重试（`:403-467`）。
- 不支持流式，不支持工具调用。
- 只有 store 上有 `novel_id` 属性、且 billing 声明 `atomic_step_settlement=True` 并支持 `settle(..., step_record=)` 时，才把「写步骤结果」与「扣费」放进同一事务（`:477-484`）。billing 抛的异常必须是 `novel.billing` 的 `InsufficientStrawberries`、`NovelBudgetExceeded`、`RunNoLongerActive` 或其子类，否则被当成普通错误重试（`:424-433`）。
- 假模型 `backend/novel/fake_llm.py:34-118` 的 `FakeLLM(script=...)`：脚本可以是函数、按 `step_key` / `task` / `role` 查的字典或列表；未知任务直接 raise。`dry_run=True` 或模型写成 `fake:xxx` 时启用。
- store 协议 `backend/novel/run_store.py:15-37` 的 `StepStore`。

### 2. 角色卡与推演会

- `backend/novel/agent_pool.py:197-206`：角色卡是 dict `{"id","name","category","required","system_prompt","max_tokens","output"}`，生成时自动拼安全规则、JSON 引号规则与 `INJECTION_GUARD`。角色卡没有默认模型，模型由配置 `agents: {角色: "厂商:型号"}` 提供。
- `backend/novel/deliberation.py:108-159`：主编初案 → 顾问并行挑错（每人 1–3 条意见，会内最多 3 个并发）→ 意见 ID 由代码按配置顺序分配 → 主编定稿，每条意见恰好回应一次。`_gather_phase`（`:32-42`）负责并行调用与失败时取消兄弟任务。
- 校验器统一抛 `novel.schemas.ValidationError(errors)`，路由器把中文错误回灌给模型修正。

### 3. 后台任务

- 每本书一个 asyncio Task：`create_background_task(_run(...), label=...)`，登记进进程内 `TASKS`（`backend/novel/runner.py:33-35,127-135`、`backend/utils/background_tasks.py:28-32`）。
- run_token：启动时在 `BEGIN IMMEDIATE` 里写入 uuid4 令牌；后台每次写库都要求令牌对且账号还在（`backend/novel/store_db.py:123-149`）；进入任何等待态都清空令牌。
- 重启恢复：lifespan 里调用 `recover_interrupted_novels`，先查 `sqlite_master`，没有表就返回（`runner.py:176-193`、`backend/main.py:137-138`）；恢复靠 step 缓存续跑。关机先退款再走通用关停（`main.py:159-161`）。
- 暂停：取消 Task、等它收尾、退还全部预扣、清令牌，再置 paused。
- 并发上限 `FIONA_NOVEL_MAX_RUNNING`：每个事件循环一个 `asyncio.Semaphore`，只在第一次创建时读值（`runner.py:82-92`）。每个用户同时只能跑一本书。

### 4. 计费

- `backend/novel/billing.py:18-24`：价目单位「草莓 / 千 token」，默认只有 3 个模型；`get_prices()` 要求覆盖 JSON 恰好包含这 3 个模型（`:47-74`）。`calculate_cost`：byok 与 fake 记 0，结果向上取整、最少 1 颗（`:77-86`）。
- 预扣：独立连接加 `BEGIN IMMEDIATE`；先查预算 80%，再带余额条件扣减，插入步骤行为 reserved（`:187-228`）。结算：实扣 = min(预扣, 真实用量费用)，差额退回（`:230-273`）。用量未知时按 0 结算，即免费（`:233-238,256`）。`is_free`：`DEV_MODE=1`、dry_run、`byok:self`、`fake:*`（`:150-153`）。
- 计费类的 SQL 直接写 `novels` 与 `novel_steps`，不能原样复用到新表。
- `backend/novel/byok_bridge.py:35-61`：`ByokBridge(username)`，`describe()` 只读公开配置，`resolve()` 每次调用时取明文 Key；只支持 anthropic、dashscope、deepseek 的已知型号；错误统一转成 `ByokUnavailable`。

### 5. 工作室底座

2 秒一次的 tick 调度器，人民币与美元账本，全工作室日额度，任务与提示词绑定 `studio_projects` 与 `brain_tasks.TASKS`，付费请求不重试、结果不明记 uncertain。不适合拿来按草莓计费的新模块。

### 6. 开关与白名单

`backend/routers/novel.py:12-18` 的 `workshop_user`：每个请求读环境变量，`FIONA_NOVEL` 必须是字面 `'1'` 否则 404；`FIONA_NOVEL_USERS` 逗号拆分、去空白后精确匹配，不在名单 403。

### 7. 结构锁测试（后端）

| 测试 | 锁的内容 |
|---|---|
| `backend/tests/test_studio_sources_readonly_integration.py:21-32` | 名为 `novels` 或 `novel_*` 的表恰好 7 张 |
| `backend/tests/test_studio_sources.py:510` | `backend/studio/` 下全部 `.py` 的 `novel.*` 导入白名单；文本里不得出现对 `novels` / `novel_` 表的 SQL |
| `backend/tests/test_studio_sources_readonly_integration.py:177` | 只扫 5 个文件（`services/claude_agent.py`、`intent_router.py`、`services/chat_service.py`、`routers/chat.py`、`studio/novel_chat.py`）的 `novel.*` 导入白名单 |
| `backend/tests/test_migrate_and_backup.py:91,110`、`test_agent_conversations.py:48-55`、`test_health_and_startup.py` | 迁移版本恰好 5 项；`/health` 的 `failed` 列表精确相等 |
| `backend/tests/test_song_jobs.py:1114,1181`、`test_health_and_startup.py:122` | 把 `init_db` 换成空操作但不替换新模块的恢复函数：新模块启动恢复必须先查 `sqlite_master` |
| `backend/tests/test_novel_chat.py:180-186` 等 | `CLAUDE_CLIENT_TOOLS` 恰好 5 个；开关关闭时工具列表必须 `is` 这个常量 |
| `backend/tests/test_novel_chat.py:165-175` | `INTENT_PROMPT` 精确相等 |
| `backend/tests/test_chat_image_tool.py:279`、`test_byok_image_tool.py:343` | `chat_service.stream_normal` 源码、`byok/client.py` 请求序列化与 git 基线相同 |
| `backend/tests/test_novel_p1_p0.py:13`、`test_novel_p1_billing.py:60` | 小说离线实验的 step_key 与正文哈希冻结；`get_prices()` 恰好 3 个模型 |
| `backend/tests/test_claude_agent_docs.py:32-47`、`test_local_watch_docs.py:30-41` | 六份文档保留指定短语，且不得出现本机绝对路径 |

没有找到的锁：`init_db` 建表数量、全量路由清单、`.env.example` 变量清单精确相等、`messages` 列集合、CLAUDE.md 字节上限、「所有带 owner 的表都被删号覆盖」的通用测试。

### 8. 删号清理

登记在 `backend/database.py:894-1042` 的 `delete_account_data`：先在事务外取消后台任务并退款（`:902-905`），再在一个 `BEGIN IMMEDIATE` 事务里逐表 DELETE。与消息挂钩的表还要同步登记清空历史（`database.py:517-538`）与删会话（`backend/agent_store.py:354-389`）。

### 调查方的复用建议

- 直接 import：`LLMRouter`、`parse_model`、`StepFailed`、`ByokBridge`、`FakeLLM`、`novel.schemas.ValidationError` / `parse_json`、`novel.billing` 的 `calculate_cost` 与三个异常类、`utils.background_tasks.create_background_task`。
- 照着写：runner（令牌、登记、取消、恢复、关机、信号量）、步骤存储、计费类、角色卡、准入依赖。
- 避坑：新模块不放 `backend/studio/`；新表不叫 `novel_*`；不新增迁移版本；不改小说的 `AGENTS`、`DEFAULT_PRICES` 与 llm_router / deliberation / fake_llm 的流程；不改 `CLAUDE_CLIENT_TOOLS` 常量；启动恢复容忍表不存在。

## 三、聊天、分身与前端入口（第二路）

### 1. 「分身交流」现状

- 固定两方、轮流发言、只产出文字、用户中途不能插话的后台任务，不是群聊。两种形态：真人分身互邀（peer）与官方搭档单人体验（official，`draft_review_v1`：主创初稿 → 官方审稿 → 主创修订，按轮次奇偶决定谁发言）。`backend/exchange_workflow.py:8,20-22,36`、`backend/exchange_store.py:432-501`。
- 明确不带工具（提示词写着没有浏览网页的能力），每次调用 `stream=False`、不重试。`backend/exchange_workflow.py:40-41`、`backend/services/exchange_service.py:124-150`。
- 三张表 `agent_exchanges`、`agent_exchange_messages`、`agent_exchange_calls`，结构写死两方（`initiator_*` / `recipient_*` 列，`pair_key` 进行中唯一）。`backend/exchange_store.py:61-119`。
- 后台运行用 `create_background_task`；每次调用前在库里预留 token、结束后结算；每 0.25 秒查一次是否被撤销；重启后把运行中的一律停掉、不重放。`backend/services/exchange_service.py:153-172,289-301`、`backend/exchange_store.py:408-429`。
- 用户只能 accept / reject / stop，没有插话接口。不扣草莓，官方体验每天 3 次。无功能开关，对所有用户开放。
- 工作室会读取已完成的 `short-video-creator` 成稿作素材来源（`backend/studio/sources.py:323-355`），所以不能改交流表。
- 可借鉴：run_token 授权、调用预留与结算、随时停止、重启恢复、迟到回复不回填、链式轮询、Markdown 导出。必须新做：多方参与者、用户插话、工具与调研。

### 2. 实时推送

- 整个仓库只有 `/chat` 用 SSE（`backend/services/chat_service.py:503-505`），与单请求生命周期和草莓预扣绑在一起。所有后台长任务（分身交流、书斋、工作室）都是写库加前端链式轮询。
- 卡片 subtype 现有 7 种：`web_sources`、`weather`、`travel_plan`、`song_project`、`novel_draft`、`novel_feedback`、`studio_project`。
- 前端解析只有一处：`frontend/app/page.tsx` 的 `handleSend`。

### 3. 消息与会话

- `messages` 的卡片外键列：`song_project_id`、`novel_draft_id`、`novel_feedback_id`（`backend/database.py:178-186`），由 `init_db` 幂等补列。
- `save_message(username, role, content, image_path=None, conversation_id=None, *, …, song_project_id=None, novel_draft_id=None, novel_feedback_id=None)`（`backend/database.py:549-562`）：三个卡片外键都要求本人本会话，否则存 NULL；`agent_id` 固定取会话的分身，无法为单条消息指定发言者。
- 一人一个分身（`agents.owner_username UNIQUE`，`backend/agent_store.py:119-130`）。
- 新增卡片外键要同时改：读消息的显式列清单（`backend/agent_store.py:338`）、前端按外键补卡片（`frontend/lib/useConversations.ts:16-18,60-67`）、删会话与清空历史的清理（`backend/agent_store.py:354-389`、`backend/database.py:517-538`）。

### 4. 前端一级入口

- 静态书签 6 个：对话、分身、广场、世界、设置、书斋（`frontend/components/Sidebar.tsx:15-22`），纯文字竖排。「工作室」在 `/studio/access` 返回 200 后动态追加（`:110-112`），并从手机底栏过滤（`:142`）。
- 陷阱：`Sidebar.tsx:114-118` 的回调三元链以 `onSettingsClick` 兜底，新 href 不补进这条链，点它会打开设置抽屉。
- `frontend/app/page.tsx`（文件以 UTF-8 BOM 开头）：`type DrawerName = "agent" | "exchange" | "plaza" | "settings" | "studio" | "novel" | null`（`:483`）；书斋是常驻 iframe `/novels?embed=1`，`openNovelAt` 做路径白名单（`:526-534`）；工作室 gate 通过后才挂 iframe（`:3056`）；iframe 经 postMessage 关抽屉并校验 origin 与 source（`:549-574`）；抽屉外壳统一为带 `drawer-panel` 类的 `Glaze`，共 6 个。
- `?embed=1` 约定：`data-shell="desktop"` 由 `frontend/app/layout.tsx:68-96` 设置；`mobile:` 变体见 `frontend/app/globals.css:8-14`；内嵌时不渲染 Sidebar，h1 加 sr-only，登录链接 `target="_top"`，内链保留 embed，Esc 经 postMessage 关闭。

### 5. 轮询与请求约定

- `frontend/lib/useAccountIdentity.ts`：`useAccountIdentity`、`useAccountRequest`（`beginRequest()` 返回 `{signal, isCurrent}`，切换账号自动取消）。
- 链式轮询样板：`frontend/components/novel/NovelWorkbench.tsx:119-136`（3 秒，页面隐藏暂停，`visibilitychange` 立即补一次；测试要求不用 `setInterval`）。
- 请求封装样板：`frontend/lib/novels.ts:101-152`、`frontend/lib/studio.ts:55-58`。

### 6. 组件复用

- `MessageText`（`frontend/components/MessageText.tsx:171-187`）是纯组件：段落、标题、列表、引用、代码块、分割线，行内只有 em 与 code；不支持表格与链接，不出粗体（`backend/tests/test_ui_polish_markdown.py:324-335` 锁定）。
- `ChatCard`（`frontend/components/ChatBubble.tsx:113-238`）已单独导出，来源列表最多 5 条，用 `openExternal` 打开。
- `ChatBubble` 无聊天上下文依赖，发言者名字按气泡传，但 title 写死「（AI 分身）」。
- `components/ui/` 没有 Dialog；对话框用原生 `<dialog className="… scrim-dialog">` 或 `ConfirmDialog.tsx` 的 `useConfirm` / `useNotice`；禁止原生 `confirm()` / `alert()`。

### 7. 视觉约定

- 字号只有 10 档 `text-fs-*`；禁止任意值字号与具名字号；颜色令牌四套主题块键集合必须相同（`backend/tests/test_design_system_gate.py`）。
- 前端源码目前没有任何 `font-semibold` / `font-bold`；没有覆盖全部源码的通用粗体禁令，各模块各自写了禁令测试。

### 8. 结构锁测试（新增书签、抽屉、对话框会碰到的）

| 测试 | 锁的内容 |
|---|---|
| `backend/tests/test_novel_p2_frontend.py:24-32` | 静态 navItems 标签恰为六个 |
| `backend/tests/test_studio_frontend_navigation.py:146-155` | 同一组六个标签（纯 Python 读源码，缺 node_modules 也照跑） |
| `backend/tests/test_studio_frontend_navigation.py:113-123` | 非共享挂载时手机底栏恰好 6 个 Link |
| `backend/tests/test_studio_frontend_navigation.py:73-85` | Sidebar 只能 import 已 mock 的模块与 6 个 React hook |
| `backend/tests/test_studio_frontend_navigation.py:158-171`、`test_novel_p2_frontend.py:35-46` | `page.tsx` 含 `"studio" \| "novel" \| null` 与 `"novel" \| null` 字面量 |
| `backend/tests/test_ui_polish_page_contracts.py:21,103-116` | `drawer-panel` 恰好出现 6 次；6 个抽屉 id 的先后顺序 |
| `backend/tests/test_ui_closeout_dialog_scrim.py:116-124,163-198` | app / components / lib 全部 `.tsx` 里 `<dialog` 恰好 14 个且都带 `scrim-dialog` |
| `backend/tests/test_desk_contract_frontend.py:284-359` | `page.tsx` 有 BOM；`<DeskDock` 恰好一处，位于 `data-chat-panel` 之后、`id="agent-drawer"` 之前 |
| `backend/tests/test_studio_wo3_polish_frontend.py:64-87` | `checkStudioAccess(request.signal)` 在 page 中恰好 1 次 |
| `backend/tests/test_novel_chat_create_frontend.py:339-345`、`test_novel_chat_feedback_frontend.py:419`、`test_song_frontend.py:59` | SSE 两段卡片代码各恰好拷贝一次 `draft_id` / `feedback_id` / `project_id` |
| `backend/tests/test_migrate_and_backup.py:91,110`、`test_health_and_startup.py:53-58` | `schema_migrations` 恰好 5 条 |
| `backend/tests/test_design_system_gate.py:530-556`、`test_component_language.py:77-92`、`test_ui_closeout_dialog_scrim.py:206-219` | 全部前端源码的字号、颜色规则；不得调用原生 confirm / alert；不得用 Tailwind `backdrop:` 工具类 |

### 9. 案头

案头只覆盖书斋的书和它的短片项目，没有登记机制；新模块不登记。

### 调查方的落点建议与作者决定的差异

调查方建议首期把入口挂进「广场」页签、不新增书签。作者已定「侧栏新增一个书签」，以作者决定为准；走工作室那条路（gate 通过后动态追加、补全回调映射）改动最小，但仍须改 `drawer-panel` 计数与抽屉顺序这两处锁测试。
