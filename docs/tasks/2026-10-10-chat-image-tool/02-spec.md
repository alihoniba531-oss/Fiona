# 主聊天模型调用生图工具（L3）

**基线**：`main` @ `7ac7b57`

| 检查 | 基线结果 |
|---|---|
| 后端 `python -m pytest -q`（沙箱外） | **2936 passed** |
| 前端 `npx eslint .` | **0 errors / 25 warnings** |
| 前端 `npx tsc --noEmit` | 0 |

**引用方式**：本文以**函数名与原文片段**为准；行号取自 `7ac7b57`，仅供参考。

**调研材料**：代码地图与审查意见已由作者方整理。本规格自包含，不需要阅读其他材料。

---

## 1. 产品目标与已拍板的决定

**要解决的问题**：用户在聊天里说「把你上面写的提示词画出来」「按你说的画，改成动漫风」「用 Seedream 画一张……」时，现有路由（正则候选 + 意图识别 + 追问 pending）只看当前这句话，不理解指代，于是把这句话原样当成画面描述去生图。

**做法**：把生图做成**主聊天模型可直接调用的工具**。主模型可以是平台模型，也可以是用户自带模型（BYOK）。由主模型根据完整对话自己写画面描述、自己选生图模型，平台执行生图。

作者已拍板：

1. **一轮到底**。主模型在一轮回复里可以先说一句话，再调用一次 `generate_image`。平台执行生图后，这一轮直接结束，**不把工具结果回灌给模型续写**。
   - 落库只写一行 assistant：前导文字 + `图片已生成。` + 描述行。
   - 每轮最多生成一张图。
2. **直接生成，不先确认**。图片下方附一行「使用的描述（模型名）：……」。这一行写进消息正文落库，下一轮对话里模型能看到它，刷新后也还在。
3. **工具路径的默认生图模型是 Seedream 5.0 Flash**。规则如下：
   - 用户在话里点名千问 / 通义 / Qwen 时，用 Qwen Image 3.0。
   - Seedream 未配置 `ARK_API_KEY` 时，改用 Qwen，并在回复里说明。
   - **生图面板（界面「生成图片」和「以此图修改」模式）完全不变**，仍按面板选择。
   - 旧路由（见第 3 节）仍跟随面板选择，不变。
4. **只换「谁来决定画什么」，计费、危机、隐私守卫照旧**：
   - 生图成功扣 10 颗草莓，和现在一样，一轮最多 10 颗。
   - 生图失败退款。
   - 危机轮不下发工具。
5. **天气、搜索、旅行、卡片、热点等其他工具不改**，仍走现有意图路由。

## 2. 已核实的外部事实（2026-10-10，作者方用真实 Key 实测或查阅官方文档）

- **平台与 DashScope 千问支持工具调用**
  - 测试方式：DashScope OpenAI 兼容模式，流式请求，`tools=[...]`、`tool_choice="auto"`、`extra_body={"enable_thinking": False}`。
  - 测试模型：`qwen3.8-omni-flash`、`qwen3.8-flash`、`qwen3.8-max`。三者都会返回 `delta.tool_calls` 增量，`finish_reason == "tool_calls"`。
  - 实测案例：一段英文提示词加一句「就用上面的提示词画出来，改成动漫风」，模型能把描述改写成动漫风格并调用工具，参数如 `{"prompt": "A cozy cat ... anime style", "model": "seedream-5.0-flash"}`。
  - 注意：omni 在「助手消息开头、没有用户消息」的畸形对话里会拒绝调用。真实对话不会出现这种结构，但工具描述里要写明「可以引用对话里之前出现的描述或提示词」。
- **DeepSeek 支持工具调用**（`deepseek-v4-pro` 加 `thinking: {type: disabled}`，流式）：行为与千问一致。
  - 官方文档写明：开启思考模式时，带 tools 的请求在之后每一轮都必须回传 `reasoning_content`，否则返回 400。所以**下发工具时必须保持关闭思考**，现有预设本来就是关闭的。
- **OpenAI 兼容流式增量的形状**
  - 字段：`delta.tool_calls[i]` 含 `index`、`id`、`function.name`、`function.arguments`。
  - 首包带 `id` 和 `name`，`arguments` 分片到达。
  - 百炼 omni 的后续包会**重复同一个 id**，所以**不要用** SDK 的 `ChatCompletionStreamState` 来累积（它会把 id 拼成两遍）。
  - 正确的累积方式：按 `index` 分组；`id` 和 `name` 取第一个非空值；只拼接 `arguments`；结束后用 `json.loads` 严格解析。
- **Claude（anthropic 1.12.1）**
  - `messages.stream` 和 `beta.messages.stream` 都接受 `tools` 和 `tool_choice`，可以和现有的 `betas` / `fallbacks="default"` 同时使用。
  - Opus 5.5 和 Sonnet 5.5 **对强制 `tool_choice`（`any` 或指定 `tool`）返回 400**。统一使用 `{"type": "auto", "disable_parallel_tool_use": True}`，含义是由模型自己决定，并且最多调用一次。
  - `text_stream` 只产出文字。工具调用块（`tool_use`，`input` 已解析成字典）在 `get_final_message()` 的 `content` 里，此时 `stop_reason == "tool_use"`。
  - 出现 `refusal` 或 `max_tokens` 时，`tool_use` 可能是半截，**不得执行**。
  - beta 流里如果出现 `type == "fallback"` 的内容块，**只执行最后一个 fallback 块之后**的 `tool_use`。
  - 不开 `eager_input_streaming`。
  - 因为本单不回灌，所以不需要回传 thinking 块。
  - Opus / Sonnet 在调用工具前的说明文字可能落在 thinking 块里、不可见，所以「只调工具、没有可见文字」是正常情况。
- **Kimi、智谱**：都要求回传 `reasoning_content`，或者需要额外参数（如 `tool_stream`）。本单**不对它们下发工具**。

## 3. 技术约束

### 3.1 统一开关：`image_tool_on`

在 `services/chat_service.py` 中新增一个纯函数（名字自定，例如 `_image_tool_enabled(ctx, state)`）。它是唯一的判定入口，**以下条件全部满足**时才为真：

- 环境开关 `FIONA_CHAT_IMAGE_TOOL` 打开。
  - 每次调用时读取；默认 `1`；只有字面值 `0` 表示关闭。
  - 其他非法值按 `1` 处理，并只告警一次。
- `ctx.request_mode == "chat"`
- 本轮没有图片：`not ctx.has_image`
- `state.crisis_level is None`。可能相关轮（possible，含信息/求助语境）和明确危机轮（high）一律不下发工具。
- `not ctx.byok_unreserved`，并且 `ctx.byok_error is None`（或项目里表示 BYOK 配置读取或解密失败的等价字段）。
- 本轮的回复模型在白名单内：
  - **平台回复**（主力槽和轻量槽）：开。
  - **BYOK `anthropic`**：开（三个型号都开）。
  - **BYOK `dashscope`**：模型名**精确等于** `qwen3.8-omni-flash`、`qwen3.8-max`、`qwen3.8-flash` 之一时开。
  - **BYOK `deepseek`**：模型名精确等于 `deepseek-v4-pro` 或 `deepseek-flash` 时开。
  - **BYOK `moonshot`、`zhipu`、`custom`**：一律不开。

### 3.2 开关为假时：字节级不变

开关为假时，`run_chat` 从「自然语言生图候选」到「意图识别」再到 `stream_normal` 的整段原代码**字节级原样执行**。同时：

- `_create_stream_with_fallback` 的调用参数中不得出现 `tools`、`tool_choice` 等任何新键。
- BYOK 请求体与现状**逐字节相同**（`test_byok_effort.py` 有逐字节断言）。

### 3.3 新参数一律可选、默认关闭

- `stream_normal`、`_stream_byok_reply`、`byok.client.open_reply_stream` / `_open`，以及生图执行核心的新参数，都必须可选且默认关闭。
- `ChatContext` 和 `ChatState` 的新字段只能**追加在末尾并带默认值**。测试里有按位置参数构造它们的写法。
- 读取增量时一律用 `getattr(delta, "tool_calls", None)`，因为测试里的假对象没有这个属性。

### 3.4 受保护文件（本单不得修改）

**后端：**
- `backend/llm.py`（它已经通过 `**kwargs` 透传 `tools`，不需要改）
- `backend/intent_router.py`
- `backend/mode_switcher.py`、`backend/crisis_model.py`、`backend/safety.py`
- `backend/database.py`、`backend/byok/crypto.py`、`backend/byok/url_safety.py`、`backend/byok/store.py`
- `backend/routers/chat_model.py`、`backend/utils/safe_http.py`
- `backend/tools/` 下**除 `image_generation.py` 之外**的所有文件

**测试：** 本单之前已存在的 `backend/tests/*.py`，**唯一例外**是 `backend/tests/conftest.py` 允许**新增一行**：

```python
os.environ.setdefault("FIONA_CHAT_IMAGE_TOOL", "0")
```

放在现有环境默认值附近，作用是让既有测试默认走旧路由。

### 3.5 不得修改的现有逻辑

- `INTENT_PROMPT`、`explicit_image_intent`、`image_generation_discussion`、`MISSING_QUESTIONS`
- `tools/image_generation.py` 中的 `DEFAULT_IMAGE_MODEL`，以及所有面向面板路径的错误文案常量
- `ChatRequest.image_model` 的 Literal
- 安全规则在 system 中的位置
- 面板路径：`mode=image` / `image_edit`
- 「缺少修图参考」的固定引导
- 天气 pending 逻辑

### 3.6 前端

- 前端没有单测框架，用 `npx tsc --noEmit` 和 `npx eslint .` 把关。
- 修改前先读 `frontend/AGENTS.md`。

### 3.7 其他

- 不引入新依赖。
- 文档里不得写本机绝对路径。

## 4. 任务清单

### 4.1 工具定义（新文件 `backend/services/image_tool.py`，或放在 `chat_service.py` 内，自定）

**工具名**：`generate_image`。工具描述用中文，**必须**写明以下几点：

- **什么时候调用**：只有当用户明确要求画图或生成图片时才调用（包括「把上面的提示词画出来」「按你说的画，改成××风」「再画一张××」）。
- **什么时候不调用**：只要提示词、讨论生图、评价图片、询问价格或用法时不调用。负例举 3–5 个，例如「帮我写一段生图提示词」「哪个生图模型好」「这张图好看吗」。
- **可以引用历史**：可以引用对话里之前出现的描述或提示词，把它整理成一段完整、具体的画面描述再调用。
- **只画新图**：这个工具只能生成新图，不能修改已有图片。用户要基于某张已有的图修改时，不调用工具，而是引导用户点那张图上的「以此图修改」。
- **隐私**：描述里不得写入账号名、真实姓名、私有记忆里的个人细节。
- **调用前的话术**：调用前最多说一句话，不得声称图片已经画好。
- **模型参数**：只有用户点名时才填 `model`。点名「Seedream / 豆包 / 即梦」填 `seedream-5.0-flash`；点名「千问 / 通义 / Qwen」填 `qwen-image-3.0`。

**参数 schema**（JSON Schema）：

| 参数 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `prompt` | string | 是 | `maxLength: 1500` | 完整画面描述 |
| `model` | string | 否 | `enum: ["seedream-5.0-flash", "qwen-image-3.0"]` | 只在用户点名时填 |
| `aspect_ratio` | string | 否 | `enum: ["1:1", "16:9", "9:16"]` | 画面比例 |

**两种请求格式**，需要提供生成函数：

- OpenAI 兼容格式：`{"type":"function","function":{"name","description","parameters"}}`
- Anthropic 格式：`{"name","description","input_schema"}`

两种格式都**不开 `strict`**。

**任何工具描述、状态文案里都不得出现 `BASE_SAFETY_RULES` 的内容。**

### 4.2 工具调用的解析与执行前校验（各厂商通用）

**平台流 / BYOK OpenAI 兼容流**：

- 按 `index` 累积 `tool_calls`。`id`、`name` 取第一个非空值，只拼接 `arguments`。
- 只有 `finish_reason == "tool_calls"` 时才视为一次工具调用。
- 用 `json.loads` 严格解析参数。

**Claude**：

- 从 `get_final_message()` 取 `tool_use`，要求 `stop_reason == "tool_use"`。
- 存在 fallback 块时，只取最后一个 fallback 块之后的 `tool_use`。
- 出现 `refusal` / `max_tokens`（或 `length`）、`content_filter` 时一律不执行。

**通用规则**：

- 只执行第一个名为 `generate_image` 的调用，其余调用忽略。
- 校验参数：
  - `prompt` 必须是去掉首尾空白后非空、长度不超过 1500 的字符串。
  - `model` / `aspect_ratio` 不在枚举内时视为未提供。
- **参数不合法**（JSON 无法解析、`prompt` 为空或超长、被截断、拒答）时：
  - 不生图，不计费（平台路径和 BYOK 路径都退款）。
  - 回复内容为「前导文字（如有）」加 `\n\n（这次没能生成图片，请再描述一次想画的画面。）`，落库，结束本轮。
  - BYOK 下仍要先发 `reply_model` 标签。

### 4.3 生图执行核心（重构 `stream_generated_image`，面板路径行为不变）

从 `stream_generated_image` 中抽出一个可复用的执行核心（名字自定）。**原函数改为调用该核心，面板路径的输出、文案、计费、trace 逐字节不变。**

**工具路径调用核心时的输入**：`prompt`、`model_id`、`aspect_ratio`、`lead_text`（前导文字）、`source="tool"`。

**工具路径与面板路径的差异**：

1. **模型选择**：
   - 优先级：工具参数 `model` → 工具默认 Seedream → Seedream 不可用时用 Qwen 并说明。
   - **工具路径忽略 `ctx.image_model`**。前端在聊天模式下会带上面板的旧选择，后端不得用它。
   - 新增常量 `TOOL_DEFAULT_IMAGE_MODEL = "seedream-5.0-flash"`，不得改 `DEFAULT_IMAGE_MODEL`。
   - 可用性：在 `tools/image_generation.py` 中抽出 `image_model_available(model_id)`，与 `public_metadata` 共用同一判断（对应 key 环境变量非空）。在发请求**之前**判断。
   - 选中的模型不可用、另一个可用时：改用另一个，并在描述行后追加一句说明，例如「（Seedream 5.0 Flash 暂未配置，这次用 Qwen Image 3.0 生成。）」。
   - 两个都不可用时：按 4.3 第 6 点的错误处理。
   - 请求发出后才失败的，**不换供应商重试**（沿用现有「不重试，避免二次计费」原则）。
2. **比例**：工具参数 `aspect_ratio` 优先；否则用描述原文里的比例词（复用现有 `image_aspect_ratio(prompt, fallback="1:1")`）；再否则用 `1:1`。
3. **状态事件**：`{"status": "generating_image", "message": "正在用 {模型显示名} 生成图片…", "source": "tool"}`。心跳沿用 `: generating-image`。
4. **落库**：
   - 只落一行 assistant。正文为：`lead_text`（去掉首尾空白后非空时，加 `\n\n`）+ `图片已生成。` + `\n\n使用的描述（{模型显示名}）：{prompt}` + 可能的降级说明，带 `image_path`。
   - **不得覆盖 `lead_text`**。现有代码里 `state.full_response = image_reply` 是覆盖写法。
   - 沿用现有「屏蔽取消的落库」和「finally 中清理未落库图片」。
5. **事件顺序（成功时）**：

   1. （BYOK 时）`reply_model`
   2. 前导 `text*`
   3. `status`
   4. 心跳
   5. `{"generated_image": …}`
   6. `{"text": "\n\n图片已生成。"}`（`lead_text` 为空时不带前面的换行）
   7. `{"text": "\n\n使用的描述（…）：…", "speak": false}`
   8. 降级说明（如有），同样带 `speak: false`
   9. `{"done": true}`

   整个过程只发一个 `done`，不发 `tool` 事件。
6. **失败**（`ImageGenerationError` 或忙锁冲突）：只发一个 `{"error": 工具口径文案}`，不落库，**退款**，前导文字不入库。工具口径文案如下：
   - **审核未通过**：「这次画面描述没通过内容审核，换个说法再让我画吧。」
   - **Seedream 发请求后返回不可用**（401/403/404/ModelNotOpen/AccountOverdue 一类）：「Seedream 暂时用不了（可能未开通或欠费），可以说『用千问画』改用 Qwen Image 3.0。」
   - **两个模型都未配置**：「图片生成服务尚未配置，请联系管理员。」
   - **其他**：沿用 `ImageGenerationError` 原文。

   实现方式：给 `ImageGenerationError` 增加一个类别属性（例如 `category`: `moderation` / `unavailable` / `busy` / `other`），由聊天层映射。**面板路径的文案逐字不变。**
7. **计费**：
   - 只有落库成功后才置 `state.billable = True`。
   - 平台路径和 BYOK 路径相同：图成功扣 10 颗；图失败、参数不合法都退款。
   - 一轮最多 10 颗。工具触发时不再预扣。
8. **零余额守卫**：不需要。`image_tool_on` 已排除 `byok_unreserved` 的情况；平台余额不足时，路由层已有处理，不会进入这里。
9. **trace**：
   - `trace.intent = trace.tool = "generate_image"`
   - `trace.image_source = "tool"`
   - `trace.image_model` = 实际生效的模型 id
   - `trace.image_fallback` = 是否降级（bool）
   - **工具路径不得用生图厂商的模型名覆盖 `trace.model`**，保持本轮回复模型（平台槽位或 `byok`），因为 `analyze.py` 依赖它。
   - 描述永远不进 trace，也不进日志。

### 4.4 平台回复路径（`stream_normal`）

- 新增可选参数，例如 `image_tool: bool = False`。为真时：
  - 给 `_create_stream_with_fallback` 传 `tools=[OpenAI 格式工具]` 和 `tool_choice="auto"`，**不传** `parallel_tool_calls`。
  - 把 `max_tokens` 从 700 提高到 1200。
  - 在块循环里同时累积 `tool_calls`。
- 循环结束后：
  - **得到一次合法调用**：
    - 不走现有的「正文非空 → `_save_text_reply` + 计费」分支；
    - 改为调用 4.3 的核心，`lead_text` 为已流出的文字；
    - 结束后照常执行 `_normal_followups`，触发条件与现有文字回复一致；
    - 返回。
  - **工具调用不合法**：按 4.2 处理。
  - **没有工具调用**：完全走现有逻辑。
- 「只调工具、没有文字」时，不得落到「空回复」分支。

### 4.5 BYOK 路径（`byok/client.py` + `_stream_byok_reply`）

**`open_reply_stream` / `_open`**：新增可选参数 `tools`（取值为 `None` 或 `"generate_image"` 这样的开关）。为空时请求体与现状逐字节相同。

**下发工具时**：

- **Claude**：
  - 在 kwargs 中加 `tools=[Anthropic 格式]`、`tool_choice={"type": "auto", "disable_parallel_tool_use": True}`；
  - 与现有的 `betas` / `fallbacks`、`output_config` 共存；
  - 文字仍走 `text_stream`；
  - 流结束后从 `get_final_message()` 按 4.2 提取工具调用；
  - 工具参数 JSON 解析失败导致 SDK 抛出的 `ValueError`，按「参数不合法」处理，不得冒出为未分类异常。
- **OpenAI 兼容（dashscope / deepseek）**：
  - 在 kwargs 中加 `tools=[OpenAI 格式]`、`tool_choice="auto"`；
  - 保持现有 `extra_body`（关闭思考）；
  - 在 `_consume` 中按 4.2 累积 `tool_calls`。

**`ReplyStream` 对外接口**：迭代契约不变，仍只产出文字块。新增一个只读结果属性（例如 `tool_call`），流结束后为 `None` 或 `{"name", "arguments": dict}`，并附带「是否因截断或拒答而作废」的信息。

**`_stream_byok_reply`**：

- **下发工具的条件**：参数 `image_tool` 为真，且 `mirror=False`。镜子模式一律不下发。
- **得到合法调用时**：
  - 若还没发过 `reply_model`，先发；
  - 在 `_byok_slot` **之外**执行生图，即关流、释放槽位之后，不要在生图期间占着 BYOK 并发槽；
  - 生图期间不计入 BYOK 的总时限（生图另有自己的 150 秒总时限）；
  - `byok_chat` 每日次数每轮只计一次（现状即如此）；
  - 生图本身的异常，不得被 BYOK 的 `except` 归类成「你的模型调用失败」。
- **「只调工具、没有文字」**：不得抛 `EmptyReplyError`。
- **计费**：BYOK 文字回复照旧免费，所以 BYOK 本轮的 10 颗**只在图成功时扣**。

### 4.6 路由（`run_chat`）

**计算位置**：在高危分支、面板模式分支、「缺少修图参考」的引导**之后**，自然语言生图候选**之前**，计算一次 `image_tool_on`。

**`image_tool_on` 为假时**：后续原样执行，不改任何字节。

**`image_tool_on` 为真时**：

1. **自然语言生图候选块**（正则候选 + 意图模型确认）**保留**。确认为生图时，改为以下步骤：
   - 清除 pending（现状在确认生图时也会清）；
   - **跳过 `detect_mode`**（保持「明确的生图请求可以绕过镜子模式」）；
   - **必须先按 friend 模式给 `state.sys_prompt_final` 赋值**，写法与 detect_mode 之后的现有赋值相同，`mode="friend"`；否则 system 为空，既没有人设也没有安全规则；
   - 进入带工具的回复：平台走 `stream_normal(…, image_tool=True)`，启用 BYOK 时走 `_stream_byok_reply(…, image_tool=True)`。
   - 候选被意图模型否决时，行为与现状相同。
2. **遗留的 `generate_image` pending**：
   - 取消类短语（现有的「算了 / 取消……」取消捷径）照旧取消；
   - 其他情况一律**清除该 pending**，然后继续往下路由；
   - 不再新建 `generate_image` pending。
   - 天气 pending 不变。
3. **意图识别**（现有 step 2）：
   - 识别结果为 `generate_image` 时**视为无意图**，进入带工具的普通回复；
   - 识别过程抛异常时也视为无意图；
   - 其他工具意图照旧走 `stream_intent`。
4. **普通回复**：
   - **friend 模式**带工具：平台走 `stream_normal(…, image_tool=True)`，BYOK 走 `_stream_byok_reply(…, image_tool=True)`。
   - **镜子模式**不带工具：镜子的 `max_tokens` 只有 80，装不下工具参数。

**保证**：同一句话只会被一条路径处理，生图只能由主模型的工具调用触发。

### 4.7 persona 与提示文字

- `backend/persona.py` 中「当前聊天支持通过千问图片模型按文字描述生成图片……」这一句，改为不绑定具体模型的说法。示例：「当前聊天可以按文字描述生成图片（可选 Seedream 5.0 Flash 或 Qwen Image 3.0）」。
- 「只有实际收到生成结果时才说图片已生成」保留。
- **只允许改这两三行**，同文件其他内容一行不改；如果有既有测试钉住原句，停下来报告。
- `chat_service.py` 中「只发送本次画面描述，不夹带人设、私有记忆」一类注释，改成与新口径一致。

### 4.8 前端（`frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/ChatModelSection.tsx`）

1. **生成期间不隐藏已经流出的文字**。`ChatBubble` 中「有 `generationStatus` 就不显示文字」的条件，改为：
   - 有 `content` 时照常显示；
   - 只有 `isTyping` 且正在生成时才隐藏打字占位。

   面板模式（生成期间 `content` 为空）的表现不变。
2. **`speak: false` 的 `text`**：拼进回复正文，**不进入朗读缓冲**。在 `ChatStreamEvent` 类型中补上 `speak?: boolean`、`source?: string`。
3. **工具路径失败不显示「重新生成」按钮**。收到 `status` 且 `source === "tool"` 后，如果本轮失败，不附 `imageGenerationRetry`。面板路径保持不变。
4. **不改**聊天模式下发送 `image_model` 的现有行为（后端工具路径会忽略它）。
5. **设置页「聊天模型」分区的隐私说明**：把「工具、生图仍由平台处理」一类的句子改成以下意思：
   - 启用后，由你的模型决定何时生图、撰写画面描述；
   - 生图仍由平台执行并扣草莓；
   - 默认使用 Seedream 5.0 Flash，描述会发送给字节跳动火山引擎。

### 4.9 文档与模板

**同步更新以下文件中描述「聊天里自然语言生图」「默认生图模型」「生图隐私」「BYOK 只接管聊天回复」的位置**：
- README.md
- CLAUDE.md
- PLAN.md
- `docs/ARCHITECTURE.md`
- `docs/DEPLOYMENT.md`
- `backend/.env.example`

**必须写明的内容**：

- **工具化生图机制**：哪些模型会下发工具，哪些退回旧路由。
- **默认模型规则**：默认 Seedream；未配置时用 Qwen 并说明；面板路径不变。
- **一轮到底**：每轮最多一张图。
- **「使用的描述」行**：会写进消息正文。
- **计费**：成功扣 10、失败退款，BYOK 文字仍免费。
- **隐私**：
  - 聊天里的生图默认把「回复模型根据对话撰写的描述」发送给字节跳动火山引擎；
  - 描述可能包含对话里出现过的内容；
  - 启用 BYOK 时，由用户自选的厂商决定何时生图、撰写描述。
- **新环境变量 `FIONA_CHAT_IMAGE_TOOL`**：默认 1，只有 0 关闭，调用时读取。
  - `.env.example` 要补上：`FIONA_CHAT_IMAGE_TOOL`、`ARK_API_KEY`（空值加注释）、`SEEDREAM_IMAGE_MODEL`（注释说明默认值）。
- **时限口径**：把「BYOK 总时限须小于 Nginx 300 秒」一类说法改为：
  - Nginx `proxy_read_timeout` 按两次读之间的间隔计算；
  - BYOK 等待和生图期间每 10 秒有一次心跳；
  - 最坏耗时为：BYOK 首轮（120 秒或高档 180 秒）加生图 150 秒。
- **已知局限**：
  - 镜子模式下非候选句不出图；
  - 非生图意图优先（例如「画一张明天北京天气的插画」会得到天气卡）；
  - Qwen 的 `prompt_extend` 会改写描述，所以显示的描述不等于最终渲染所用的描述；
  - 「改成动漫风」是重新生成新图，不保留原图构图；
  - 已配置 Key 但 Seedream 未开通时，每次都会失败，并提示「用千问画」；
  - Kimi、智谱、自定义地址暂不支持，仍走旧路由。

### 4.10 测试（新文件，例如 `backend/tests/test_chat_image_tool.py`、`test_byok_image_tool.py`）

新测试要显式 `monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")`，并按需显式 `setenv` / `delenv` `ARK_API_KEY`。

假流要覆盖两种形状：
- 带 `tool_calls` 增量的 OpenAI 块，包括 id 重复、`arguments` 分片；
- Claude 的 final message，包括 `tool_use`、fallback 块、`refusal`、`max_tokens`。

**至少覆盖以下场景**：

1. **平台成功路径**：
   - 只扣 10 颗、只扣一次；
   - 落库正文 = 前导 + `图片已生成。` + 描述行；
   - 事件顺序符合 4.3 第 5 点，描述行带 `speak: false`；
   - trace 字段符合 4.3 第 9 点，trace 里没有描述原文。
2. **模型选择**：
   - 有 ARK Key、未点名：Seedream，调用时 `model_id="seedream-5.0-flash"`；
   - 工具参数为 qwen：Qwen，调用形状为 `generate_image(prompt, ratio)`；
   - 无 ARK Key：Qwen，带降级说明；
   - 请求里带着面板的 `image_model="qwen-image-3.0"` 时，工具路径仍默认 Seedream。
3. **比例优先级**：工具参数 > 描述原文 > 1:1。
4. **失败与边界**：
   - 生图失败：退款、不落库、只有一个 error、文案为工具口径；
   - 忙锁冲突；
   - 中途断开：清理未落库图片、退款；
   - 多个工具调用：只生一张；
   - 截断 / 坏 JSON / 空 prompt / 超长：不生图、不计费、按 4.2 回复。
5. **BYOK**：
   - Claude 只调工具不出文字：不抛 EmptyReplyError，并且先发 `reply_model`；
   - 生图时 `_BYOK_USERS` 为空、`_BYOK_ACTIVE == 0`（在 generate 桩里断言）；
   - `byok_chat` 只计一次；
   - 图成功扣 10、图失败退款；
   - Claude 的 `stop_reason` 为 `refusal` 或 `max_tokens` 时不执行；
   - 有 fallback 块时只取最后一个 fallback 块之后的 `tool_use`；
   - 请求体里的 `tools` 和 `tool_choice` 形状正确。
6. **白名单**：
   - BYOK `custom` / `moonshot` / `zhipu` 不传 `tools`，并且走旧路由（给 `open_reply_stream` 打桩，断言 kwargs）；
   - dashscope 和 deepseek 的模型名不在名单内时，同样不传 `tools`。
7. **开关为 0**：平台和 BYOK 的请求参数里都没有 `tools`，行为与现状一致。
8. **危机**：
   - high、possible（含信息语境）轮都不传 `tools`；
   - 即使假流发出了工具调用，也不生图；
   - 危机资源恰好一次；
   - possible 轮保留 `generate_image` pending，并且不调用 `clear_pending`。
9. **路由**：
   - 候选句确认后，绕过镜子模式，走带工具的回复，且 `sys_prompt_final` 非空、以安全规则结尾；
   - 遗留 `generate_image` pending：「算了」取消；其他文本时清除 pending，再交给带工具的回复；
   - 意图识别返回 `generate_image` 时走带工具的回复；
   - 意图识别返回 `weather` 时仍走 `stream_intent`；
   - 意图识别抛异常时视为无意图。
10. **安全规则恰好一次**：带工具的平台请求和 BYOK 请求里，所有 system 内容合计只有一次 `BASE_SAFETY_RULES`，并且在最后一条 system（Claude 为顶层 system）的末尾。要覆盖朗读尾部 system 那条路径。
11. **零余额 BYOK**：`image_tool_on` 为假，走旧路由，守卫原样。

## 5. 验收标准（在仓库根目录执行）

1. `git status --porcelain` 只允许出现以下文件：
   - **修改**：
     - `backend/services/chat_service.py`
     - `backend/byok/client.py`
     - `backend/tools/image_generation.py`
     - `backend/persona.py`
     - `backend/tests/conftest.py`（仅新增那一行）
     - `backend/.env.example`
     - `frontend/app/page.tsx`
     - `frontend/components/ChatBubble.tsx`
     - `frontend/components/ChatModelSection.tsx`
     - README.md、CLAUDE.md、PLAN.md、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`
   - **新增**：
     - `backend/services/image_tool.py`（如采用）
     - 新测试文件
     - 本任务目录
2. 受保护文件零 diff：`git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/database.py backend/byok/crypto.py backend/byok/url_safety.py backend/byok/store.py backend/routers/chat_model.py backend/utils/safe_http.py` 的退出码为 0。另外：
   - `git diff --stat -- backend/tools` 只出现 `image_generation.py`；
   - `git diff backend/tests/conftest.py` 恰好只新增 1 行；
   - 其他既有测试文件零 diff。
3. `grep -n "DEFAULT_IMAGE_MODEL = " backend/tools/image_generation.py` 仍为 `"qwen-image-3.0"`。
4. 在 `backend/` 下运行三遍全量测试：
   - **a. 默认运行**（conftest 默认关闭开关）：`python -m pytest -q`，passed ≥ 2936 + 新增用例数。沙箱内因端口或回环权限导致的既有失败与 skip 可忽略，由主控在沙箱外重跑。
   - **b. 打开开关运行**：`FIONA_CHAT_IMAGE_TOOL=1 python -m pytest -q`。允许失败的**只能**是编码了「聊天中自然语言生图走正则候选 / 意图识别 / pending 并直接生图」这一被本单有意改变行为的既有用例，例如 `test_chat_image_generation.py`、`test_image_intent_precision.py`、`test_image_model_choice.py` 中 chat_intent / chat_pending 相关用例、`test_byok_chat.py` 中 image 相关参数化用例。报告里要逐条列出失败用例和原因；其他任何文件出现失败都不合格。
   - **c.** 新测试全部通过。
5. 在 `backend/` 下运行 `python -m pip check` 通过。
6. 在 `frontend/` 下：`npx tsc --noEmit` 退出码为 0；`npx eslint .` 为 0 errors，warnings ≤ 25。

不要运行 `npm run build` 或 `npm run dev`，不要启动后端，不要安装任何包，不要发起任何真实网络请求。真实模型评测、构建和浏览器走查由作者方在沙箱外完成。

## 6. 什么时候停下来问

- 只有当某项要求**无法实现，或与另一项要求矛盾**，并且影响「做出什么」时，才停下来，在报告里写明原因和证据。例如：
  - 必须修改受保护文件才能实现；
  - 必须修改既有测试的输入或断言；
  - 某厂商 SDK 的实际接口与第 2 节不符。

  停下来时不回滚已完成的工作。
- 只影响「怎么写测试 / 怎么验证」的细节，自行决定并说明。
- **规格示例与既有逻辑冲突时必须停下来问，不得自行发明规则。**
