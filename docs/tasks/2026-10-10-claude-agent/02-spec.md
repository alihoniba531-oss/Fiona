# 规格：自带 Claude 升级为「多步调度工具 + 直接看图 + 联网搜索」的智能体模式

日期：2026-10-10。基线：`main` 的 `b7a27cf`。等级 L3。作者已授权：规格写完直接实施，不需要再确认。

## 0. 背景与目标

用户在 Fiona 接入了自己的 Claude API Key（BYOK，`provider == "anthropic"`）。现状是：
- Claude 只负责文字回复，外加一个单轮的 `generate_image` 原生工具。生图结果不回灌给 Claude，生图后本轮就结束。
- 天气、旅行、路线、热榜、搜索、网页卡片这些工具，都由平台千问意图识别决定、由平台直接回卡片，Claude 不参与。
- 用户发图时由平台 `qwen-vl-max` 看图回复，Claude 完全收不到图片（`byok/client.py` 的 `convert_messages` 会丢掉非字符串内容）。

本单目标：用户自带 Claude 时，开启「Claude 智能体模式」：
1. **多步调度工具**：Claude 自己决定调用哪些平台工具。工具结果回灌给 Claude，它可以继续调用下一个工具或直接作答。一轮里可以用多个工具。
2. **直接看图**：用户本轮上传的图片作为图片块直接交给 Claude，不再经过平台视觉模型。
3. **联网搜索**：使用 Anthropic 服务器端的 `web_search` / `web_fetch` 工具，由 Claude 自己搜索、读网页。来源链接展示给用户。
4. **提示缓存**：多步调用会反复发送相同的前缀，在智能体模式下加 `cache_control`，降低用户 Key 的花费。

不在本单范围：
- DeepSeek 及其他厂商（保持现状，DeepSeek 的原生生图工具不变）；
- 平台模型；
- 视频；
- 一轮多张图；
- 改图（`edit_image` 仍只走面板）。

## 1. 开关与启用条件

- 环境变量 `FIONA_CLAUDE_AGENT`：
  - 默认 `1`；只有字面值 `0` 表示关闭；
  - 其他非法值按 `1` 处理，并只告警一次；
  - 每轮读取一次。

  写法与 `FIONA_CHAT_IMAGE_TOOL` 的 `_image_tool_enabled` 一致。
- `backend/tests/conftest.py` 只允许新增这一行，紧跟在 `FIONA_CHAT_IMAGE_TOOL` 那一行之后：
  ```python
  os.environ.setdefault("FIONA_CLAUDE_AGENT", "0")
  ```
  目的：任务前的既有测试默认仍走旧路由。
- **智能体模式启用条件**，必须同时满足：
  1. 开关开启；
  2. `ctx.request_mode == "chat"`；
  3. `state.crisis_level is None`。high 和 possible 两档一律不进入智能体模式，按现有路由处理；
  4. BYOK 已启用，`provider == "anthropic"`，且 `ctx.byok_error is None`；
  5. `not ctx.byok_unreserved`。零余额的 BYOK 用户不进入，现有的零余额 pending 免费取消等逻辑保持原样。

- 判定位置在 `run_chat` 中：
  - 在 high 危机分支、面板 `image` / `image_edit` 分支、「修图缺参考图」引导之后；
  - 在 `_image_tool_enabled` 那一段**之前**。

  条件成立时进入新的智能体路径并 `return`；不成立时，后续代码**逐字节**按现状执行。
- **智能体模式下 Anthropic 不再走 `_image_tool_mode == "native"` 的旧原生生图路径**，生图改为智能体工具之一。开关关闭时，旧原生路径保持原样。

## 2. 智能体路径的路由（新函数，建议放在新模块 `backend/services/claude_agent.py`，由 `chat_service.run_chat` 调用）

1. **清理 pending**：存在任何 pending 时，一律 `clear_pending`。智能体模式下，平台不读、不写 pending；需要追问时由 Claude 用自然语言追问。
2. **模式判定**：
   - 本轮有图（`ctx.has_image`）时，不调用 `detect_mode`，直接按 friend 模式；
   - 否则照常调用平台 `detect_mode`。结果为 `mirror` 时走现有 `stream_mirror`，不带工具，行为与现状完全一致，然后 `return`。
3. **friend 模式**：
   - 不调用平台意图识别 `recognize_intent_with_fallback`，不调用生图判断器，也不调用 `explicit_image_intent`。
   - 直接进入 Claude 智能体循环（第 3 节）。
4. **后续任务**：回复成功落库且没有 error 时，与现在的 BYOK 普通回复一样执行 `_normal_followups`。

## 3. Claude 智能体循环

### 3.1 请求构造（只在智能体模式下生效）

**不带新参数时，`byok/client.py` 现有请求体必须与现状逐字节一致**，既有测试会锁定这一点。智能体模式通过新的入口函数或新参数构造请求，不改动现有路径。

**system**
- 沿用 `state.sys_prompt_final`，经 `convert_messages` 处理：账号名脱敏，合并为顶层 system。
- 在**安全规则之前**插入第 3.4 节的「工具使用说明」。安全规则仍然只出现一次，并且位于最后一条 system 的末尾，与 `_final_system_prompt` 的约定一致。
- 顶层 system 以列表形式发送：`[{"type":"text","text":...,"cache_control":{"type":"ephemeral"}}]`。

**messages**
- 历史消息仍为字符串 content，即现有 `ctx.messages` 的文字形状，历史图片以「［图中：摘要］」文字出现。
- 本轮 user 消息改为内容块列表：
  - 第一个块：当前北京时间一行，格式 `（当前北京时间：2026年10月10日 周六 14:00）`。时间放在本轮消息而不是 system 里，避免每轮都让缓存失效。
  - 有图时：接着放 `{"type":"image","source":{"type":"base64","media_type":<mime>,"data":<base64>}}`。数据来自 `ctx.image_base64`（已经过平台去元数据、重编码的 data URI），解析出 mime 和数据。
  - 最后一个块：用户原文文字（`ctx.user_content`；纯图片时为「[发了一张图片]」）。
- 每次请求在 messages 最后一条的最后一个内容块上加 `{"cache_control":{"type":"ephemeral"}}`。多步时，最后一条是最新的 user 消息或 tool_result 消息。
- `convert_messages` 中「丢开头 assistant、合并同角色」等规则要继续适用于字符串历史；内容块列表要原样保留，不得被丢弃。

**tools**
- 客户端工具：见第 3.3 节。每个工具都设置 `"eager_input_streaming": true`。
- 服务器端工具：
  - `claude-opus-5-5`、`claude-sonnet-5-5`：
    - `{"type":"web_search_20260209","name":"web_search","max_uses":5}`
    - `{"type":"web_fetch_20260209","name":"web_fetch","max_uses":3}`
  - `claude-haiku-5-5`：
    - `{"type":"web_search_20250305","name":"web_search","max_uses":5}`
    - `{"type":"web_fetch_20250910","name":"web_fetch","max_uses":3}`
  - 版本映射写成模块级常量 `CLAUDE_SERVER_TOOLS`，方便作者方用真实 Key 实测后调整。

**其他参数**
- `tool_choice={"type":"auto","disable_parallel_tool_use":True}`：每一步最多调用一个客户端工具。
- 端点、betas、fallbacks、`output_config.effort` 与现有 Anthropic 路径一致：opus 和 sonnet 走 beta 端点并带 server-side-fallback；haiku 走普通端点。
- `max_tokens` 按现有普通回复的 effort 规则。
- 不传 thinking、temperature 等参数。

### 3.2 循环

- 每轮只有一次 Claude 请求序列，结构为「请求 → 流式输出文字 → `get_final_message()` → 处理」。
- `stop_reason` 的处理：
  - `end_turn` / `stop_sequence`：结束。
  - `tool_use`：
    - 只取最后一个 `fallback` 块之后的第一个客户端 `tool_use`；
    - 执行对应工具（第 3.3 节）；
    - 把本次 assistant content（裁掉最后一个 fallback 块之前的内容）原样追加为 assistant 消息，再追加 `{"role":"user","content":[{"type":"tool_result","tool_use_id":...,"content":<文字>}]}`，然后发起下一次请求。
  - `pause_turn`：把 assistant content 原样追加后继续请求，不添加任何新的 user 文字。每轮最多续 2 次，超过就按「结束」处理。
  - `max_tokens`：按现有截断规则结束。
  - `refusal`：按现有拒答规则结束。
- **上限**：
  - 每轮最多执行 4 次客户端工具。第 5 次 `tool_use` 不执行，返回 tool_result「本轮工具调用次数已用完，请直接回答主人」，再给 Claude 一次作答机会。
  - 每轮总时限 `FIONA_CLAUDE_AGENT_TOTAL_SECONDS`：默认 240，范围 60–290，非法值回落默认。每次 Claude 请求的总时限取「剩余预算」与现有 BYOK 总时限两者中较小的值。预算耗尽时以已产出内容收尾（第 3.6 节）。
  - 整轮可见文字累计上限 8000 字。单次请求仍沿用 4000 字上限。
- **并发槽**：
  - 每用户在整轮期间占用「每用户 1 条」的锁；
  - 全局槽（`FIONA_BYOK_MAX_STREAMS`）只在每次 Claude 请求期间占用，执行客户端工具时释放；
  - 重新获取全局槽时最多等 10 秒，仍拿不到就按第 3.6 节以已产出内容收尾，错误文案为「通道繁忙」；
  - 生图沿用 `_IMAGE_GENERATION_USERS` 锁，在 BYOK 全局槽之外执行。
- **心跳**：
  - 等待 Claude 时沿用 `: thinking`；
  - 执行客户端工具时每 10 秒发一次 `: tool`；
  - 生图沿用 `: generating-image`。
- **每日上限**：`byok_chat` 每个用户回合只计 1 次，不按请求次数计。

### 3.3 客户端工具（下发给 Claude）

所有工具都通过现有实现执行，复用 `run_slow` 线程池。
- 工具执行**不得**在日志或 trace 中写入参数（城市、查询、地点、描述）。
- tool_result 只给 Claude 文字，不含平台内部字段。

| 工具名 | 参数（JSON Schema） | 执行 | 给用户的输出 | tool_result 文字 |
|---|---|---|---|---|
| `get_weather` | `city`: string，必填 | 现有 `weather` 工具，含 `normalize_city` 和每日上限检查 | 天气卡（追加卡片事件，见第 4 节） | 城市、未来几天的日期、天气、温度、风，紧凑中文；失败时为失败原因 |
| `plan_travel` | `query`: string，必填，旅行需求的完整描述 | 现有 `travel_plan` | 旅行卡（追加） | 卡片要点和来源标题 |
| `plan_route` | `origin`、`destination`: string，均必填 | 现有 `route` | 路线卡（追加） | 卡片要点 |
| `get_hot_topics` | `source`: enum，取值为现有支持的 5 个源 | 现有 `hot_topics` | 热榜卡（追加） | 前 10 条标题 |
| `generate_image` | 沿用 `services/image_tool.py` 的 schema | 现有 `_stream_image_execution`（`source="tool"`，`lead_text` 为空），默认 Seedream，降级与错误文案不变 | 图片和描述行，与现状一致 | 成功：「图片已生成并展示给主人（模型：…，比例：…）」；失败：失败原因 |

**工具规则**
- **天气城市隐私**：`city` 经规范化后，必须出现在本轮用户原文或最近 3 条 user 消息原文中（规范化后做子串比较）；否则不执行，tool_result 返回「主人没有说过这个城市，请先问主人想查哪个城市」。这条规则不得用记忆、画像、位置来放宽。
- **每轮最多一张图**：本轮已成功生成过一张图后再调 `generate_image`，不执行，tool_result 返回「本轮已生成过一张图，请直接回答；如需更多请让主人再说一次」。
- 平台的 `web_search`、`fetch_card`、`get_datetime` **不下发**给 Claude：搜索和读网页由 Anthropic 服务器端工具完成，时间已放在本轮消息里。
- 桩工具（打开应用、微信等）不下发。

### 3.4 工具使用说明（插入 system，逐字使用）

```
【工具使用】你可以调用工具帮主人做事：get_weather 查天气（城市必须是主人亲口说过的，没说就先问）；plan_travel 做旅行规划；plan_route 查两地路线；get_hot_topics 看热榜；generate_image 生成图片（每轮最多一张，描述不得含账号名、真实姓名或私人细节）；web_search 和 web_fetch 联网搜索、阅读网页（需要最新信息或主人给了链接时使用）。只有实际收到工具结果后才能说已经查到或已经画好，不得编造工具结果；工具失败就如实告诉主人。可以连续使用多个工具，再综合作答。当前消息开头的「当前北京时间」可直接使用。
```

### 3.5 服务器端搜索结果展示

- 从 final message 的 `web_search_tool_result` 块中提取结果 URL 与标题。web_fetch 的结果块按 SDK 1.12.1 的实际类型名提取，需在 SDK 源码中核实。
- 只保留通过 `tools/card_detail.validate_public_http_link`（或现有等价的公网 URL 校验）的链接，去重后最多 5 条。
- 每轮结束前，如有来源，发一张追加卡片：`{type:"card", subtype:"web_sources", source:"联网搜索", points:[], sources:[{title≤80, url, site_name}], error:false}`。
- **不得**从 Claude 正文里抽取链接。
- trace 记录 `web_search_requests`、`web_fetch_requests` 两个次数，取自 `usage.server_tool_use` 的对应字段；SDK 没有该字段时记 0，不记查询词。

### 3.6 计费、落库与错误

**计费**
- 每轮仍只预扣一次 10 颗，不追加扣费。
- 本轮至少有一个计费项成功交付时，结算这 10 颗，否则全额退款。计费项包括：
  - 平台工具产出 `error` 为假、`stale` 为假的卡片；
  - 或者生图成功。
- 计费项用累加方式记录（例如 `state.billable = state.billable or ...`）。后续失败不得把已经成立的计费改回 False。
- 联网搜索和看图走用户自己的 Key，不扣草莓。纯文字回复与现状一致，免费。

**落库**
- 一轮只写一条 assistant 记录。正文按产出顺序拼接：
  - Claude 各段文字；
  - 每张卡片的摘要，格式为「［卡片：<现有 `_summarize_card_for_history` 的结果>］」；
  - 生图沿用现有的「图片已生成。」和「使用的描述（…）：…」行，`image_path` 用这一张图。
- 卡片本身不落库，与现状一致。
- 本轮有图片输入时，用 `set_message_image_summary` 写入摘要：取 Claude 本轮全部文字截到 120 字，与现有看图路径一致。

**错误**
- 中途出错（Claude 请求失败、超时、预算耗尽、槽位繁忙）时：
  - 已经交付过文字、卡片或图片：先落库已交付的内容，再发 error 事件；计费按已交付的计费项结算。
  - 还什么都没交付：与现有 BYOK 错误处理完全一致（不落库、退款、错误文案不变）。
- `reply_model` 标签每轮只发一次，在第一段文字或第一个工具事件之前发出。

**trace**
- 记录以下字段：
  - `agent: true`
  - `agent_rounds`（Claude 请求次数）
  - `agent_tools`（按顺序的工具名列表，**不含参数**）
  - `agent_stop`（结束原因）
  - `web_search_requests`、`web_fetch_requests`
  - `agent_usage`：累计的 `input_tokens`、`output_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`，取 SDK usage 中存在的字段
- trace 的 `model` 仍为 `"byok"`，`byok_provider` 照旧。

## 4. 前端

- SSE 新增追加卡片的语义：`{"card": {...}, "append": true}`。前端收到 `append === true` 的卡片时：
  - 把卡片追加进消息的新字段 `cards: CardData[]`；
  - **不覆盖**已流出的文字，不清空朗读队列，不改 `cardData`。
  - 没有 `append` 的卡片，处理逻辑逐字不变。
- `ChatBubble`：在文字气泡之后，按顺序渲染 `cards` 中的每张卡片，复用现有的天气卡、通用卡和来源渲染。`subtype:"web_sources"` 用通用卡渲染，标题为「联网搜索」，只显示来源列表。
- 智能体模式下文字可能先于卡片和图片出现。生成中的状态卡与文字同时显示的逻辑保持现状，R1 已支持。
- 设置页 `ChatModelSection.tsx`：在「生图：……」那一段之后新增一段，逐字使用：
  ```
  选 Claude 时，Claude 可以直接查看你本轮发送的图片，自行调用天气、旅行、路线、热榜和生图工具（工具由平台执行，天气只查询你亲口说过的城市，使用工具的回合按次扣草莓），并可使用 Anthropic 的联网搜索和网页读取（由 Anthropic 执行，按其价格计入你的 API 额度，搜索约每 1000 次 10 美元）。图片和工具结果会发送给 Anthropic。
  ```

## 5. 文档

README.md、CLAUDE.md、PLAN.md、docs/ARCHITECTURE.md、docs/DEPLOYMENT.md、backend/.env.example 需要同步说明：
- 智能体模式的启用条件、开关 `FIONA_CLAUDE_AGENT` 和 `FIONA_CLAUDE_AGENT_TOTAL_SECONDS`；
- 数据流：图片和工具结果发给 Anthropic；联网搜索由 Anthropic 执行并计入用户额度；
- 计费口径；
- 天气城市规则；
- 上限：4 次工具、240 秒、8000 字、每轮一张图；
- 已知局限：
  - 历史图片不再发送原图；
  - 镜子模式不带工具；
  - 危机轮不进入智能体模式；
  - 卡片不落库。

文档中不得出现本机绝对路径。

## 6. 约束

- **受保护文件，本单不得修改**：
  - `backend/llm.py`、`backend/intent_router.py`、`backend/mode_switcher.py`、`backend/crisis_model.py`、`backend/safety.py`、`backend/database.py`；
  - `backend/byok/crypto.py`、`backend/byok/url_safety.py`、`backend/byok/store.py`、`backend/routers/chat_model.py`、`backend/utils/safe_http.py`；
  - `backend/tools/` 下的全部文件。工具只能调用，不能修改。
- **测试纪律**：
  - 任务前已存在的测试文件一律不得修改。唯一例外是 `conftest.py` 新增上面那一行。
  - 新测试放在新文件里（建议前缀 `test_claude_agent_`）。
  - 新测试**不得依赖 git 历史**（不得 `git show <提交>`）。需要与旧行为比较时，就在测试里写死期望值。
  - 所有新测试必须离线：在模块级硬拦截 socket 连接与 DNS；Anthropic SDK 用 `httpx2.MockTransport` 喂入 SSE 夹具，覆盖以下情形：
    - tool_use；
    - server_tool_use + web_search_tool_result；
    - pause_turn；
    - fallback 块；
    - refusal；
    - max_tokens。
- **不新增依赖**；anthropic 1.12.1 和 httpx2 已安装。
- **不安装包、不发真实网络请求、不启动服务、不运行 build 或 dev**。
- 先写会失败的测试，再改代码。
- 使用多个 subagent 并行，按文件不重叠分工。派子代理时不要传 model 和 reasoning_effort 参数。

### 必须覆盖的测试点（新测试）

1. **开关与启用条件**：每个条件单独取反都不进入智能体模式；开关关闭时旧路由不变（抽查 2 条代表路径的事件序列）。
2. **请求构造**：
   - system 中「工具使用说明」位于安全规则之前，且安全规则恰好出现一次并在末尾；
   - system 带 cache_control，最后一条消息的最后一个块带 cache_control；
   - 时间块、图片块、文字块的顺序正确；
   - 三个型号对应的服务器端工具版本正确；
   - 不带新参数的旧路径请求体不变（写死期望 kwargs 做比较）。
3. **循环**：
   - 单工具、双工具串联（天气 + 生图）、工具次数上限、pause_turn 续传和续传上限；
   - fallback 块之前的 tool_use 被忽略；
   - 预算耗尽、槽位繁忙时的收尾；
   - 每轮只计 1 次 byok_chat。
4. **天气城市隐私规则**：
   - 正例：本轮说了城市、前 3 条 user 消息里说过城市；
   - 反例：只在记忆或 system 中出现，不执行；
   - 日志和 trace 中没有城市名。
5. **计费**：
   - 卡片成功 + 后续工具失败仍结算；
   - 只有失败工具时退款；
   - 纯文字和联网搜索不扣费；
   - 生图成功结算；
   - 第二次生图不执行。
6. **落库正文**：拼接格式、`image_path`、看图轮写入 image_summary。
7. **服务器端搜索**：来源卡只来自结果块、URL 校验、去重、最多 5 条；正文中的链接不进卡片；trace 记录次数。
8. **看图**：本轮有图时不调 `qwen-vl-max`；Claude 请求中带有 base64 图片块；不调用 `detect_mode`。
9. **pending**：进入智能体路径时清除；智能体路径不写 pending。
10. **危机**：high 和 possible 都不进入智能体模式。
11. **前端**：
    - `append` 卡片追加且不覆盖文字；
    - 非 `append` 卡片的行为不变；
    - 设置页新文案逐字出现。

    沿用 `test_chat_image_tool_frontend.py` 的做法：用 node 执行抽出的逻辑，或做源码断言。
12. **文档**：六个文件中包含智能体模式的关键说明。

### 停下来询问的条件

只有当规格中的要求互相矛盾，或者必须修改受保护文件或既有测试才能实现时，才停下来。在 `03-report.md` 写明冲突、可选方案及各自影响后停止，不回滚已完成的工作。只影响「怎么验证」的问题自行决定，不要停。

## 7. 验收（在仓库根目录与 backend 下执行，输出与退出码写入 `03-report.md`）

1. `git status --porcelain` 中只有规格允许范围内的文件。
2. 受保护文件零 diff：
   ```
   git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/database.py backend/byok/crypto.py backend/byok/url_safety.py backend/byok/store.py backend/routers/chat_model.py backend/utils/safe_http.py backend/tools
   ```
3. 既有测试零改动：`git diff --name-only -- backend/tests` 只列出 `backend/tests/conftest.py`，且 conftest 的 diff 恰好是新增的那一行。
4. 默认全量：`python -m pytest -q` 全部通过；沙箱内无法绑定回环端口的用例单独列出。
5. 开关开启全量：`FIONA_CLAUDE_AGENT=1 python -m pytest -q`。列出全部失败用例及逐条原因：
   - 只允许出现「智能体模式改变了 Anthropic BYOK 路径的旧预期」这一类失败；
   - 每条都要说明对应规格的哪一节。
6. 本任务新测试全部通过。
7. `python -m pip check` 通过。
8. 前端：`npx tsc --noEmit`、`npx eslint .` 均为 0 errors。
9. `03-report.md` 必须包含：
   - 修改了哪些文件；
   - 与第 1–5 节逐项的对应关系；
   - 以上各项的实际输出与退出码；
   - 未完成或需要人工确认之处，其中包括：服务器端工具版本、结果块类型名、`usage.server_tool_use` 字段名等需要作者方用真实 Key 核实的点。
