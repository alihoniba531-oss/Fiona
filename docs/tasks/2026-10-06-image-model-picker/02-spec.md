# 规格：生图模型选择 —— Qwen Image 3.0 / Seedream 5.0 Flash（2026-10-06）

- **基线**：`main` HEAD `065e00a`。
  - `backend/tests` 全量 **1938 passed**；
  - 前端 `npx tsc --noEmit` 通过；`npm run lint` 25 条警告、0 错误（CI 门禁 `--max-warnings=38`）。
  - 以上为 2026-10-06 实测。下文行号都指这个版本。
- **任务级别**：L2（新增界面控件，后端新增一个供应商，不改数据模型）。

## 1. 用户需求与拍板（2026-10-06）

用户原话：「帮我在这个对话框上面加上可选的模型：Qwen image 3.0，或者 seedream」。所指是输入区里生图那一行（「上传参考图 / 生成图片 / 1:1 16:9 9:16 / 返回聊天」）。

| # | 问题 | 决定 |
|---|---|---|
| D1 | Seedream 用哪一版 | **Seedream 5.0 flash**，火山方舟模型 ID `doubao-seedream-5-0-flash-260915`。方舟上不存在「Seedream 2.5」 |
| D2 | Qwen 用哪一档 | **标准版 `qwen-image-3.0`**，也就是现在的默认值 |
| D3 | 作用范围 | **生图和修图都能选**；记住用户上次的选择；普通聊天里自然语言触发的生图（「帮我画……」）也跟随这个选择 |
| D4 | 计费 | **两个模型都扣 10 颗**，与现在相同，计费逻辑一行不改 |

## 2. 关键事实（主会话调研与实测，实施方不需要也不得调用真实接口）

### 2.1 火山方舟图片生成接口

- **端点**：`POST https://ark.cn-beijing.volces.com/api/v3/images/generations`，同步返回。
- **请求头**：`Authorization: Bearer <ARK_API_KEY>`、`Content-Type: application/json`。
- **请求体**（本单固定使用以下字段）：

  ```json
  {"model": "doubao-seedream-5-0-flash-260915", "prompt": "...", "size": "1024x1024",
   "response_format": "b64_json", "output_format": "png", "watermark": false,
   "image": "data:image/png;base64,..."}
  ```

  - `size` 写成像素「宽x高」（小写 x），总像素必须在 **[921600, 4624220]** 之间。
  - `image` 只在修图时传：一张图传字符串，多张图传字符串数组，格式都是 `data:image/png;base64,...`。
  - `watermark` 必须显式传 `false`，否则会加「AI 生成」水印。
  - `output_format: "png"` 让结果直接是 PNG。
- **成功响应**：`{"model", "created", "data": [{"b64_json": "...", "size": "WxH", "output_format": "png"}], "usage": {...}}`。用了 `b64_json`，就不用下载结果 URL，也不用改结果域名白名单。
- **错误**：响应顶层是 `{"error": {"code", "message", "type"}}`。
  - 内容审核拦截：HTTP 400，code 中包含 `SensitiveContentDetected` 或 `RiskDetection`；
  - 401 `AuthenticationError`；
  - 403 `AccountOverdueError`（欠费）；
  - 404 `ModelNotOpen` 或 `InvalidEndpointOrModel.*`；
  - 429 `*RateLimitExceeded` 或 `QuotaExceeded`；
  - 400 `InvalidParameter`；
  - 500 `InternalServiceError`。
- **主会话实测**（2026-10-06）：用户账号目前返回 404 `ModelNotOpen`，需要用户在方舟控制台开通。开通后由主会话做真实验收；实施方一律打桩。
- **价格**：0.12 元/张。官方耗时约 10–20 秒，沿用现有 150 秒总超时。

### 2.2 现有 Qwen 路径

现有 Qwen 路径（`tools/image_generation.py`）保持原样。它的请求体、结果下载、域名白名单、PNG 校验与落盘都不改。

## 3. 硬规则（违反任一条即返工）

- **已有测试的输入和断言一律不得修改。**
  - 现有测试里大量生图和修图桩函数的签名是固定的：`(prompt, ratio)`、`*args`，或者 `(prompt, refs, aspect_ratio=None)`。所以**只有用户选了非默认模型时**，才允许向 `generate_image` / `edit_image` 传新增的关键字参数；默认模型的调用方式必须和现在逐字一致。
  - 如果某条已有测试和本规格冲突，不要改测试；调整实现，并写进报告的「未决问题」。
- 不引入依赖：Python 和 npm 都不行。用现有的 `httpx` 直接调用方舟，不装方舟 SDK。不改 `requirements.txt`、`package.json` 和 lockfile。
- 不做真实网络调用，不调用真实模型，不读 `.env*`，不启动服务，不运行浏览器。
- 不写 git 状态。
- 派生子代理时，不要传 model 或 reasoning_effort 参数；同一个文件只能由一个子代理改。
- **凡偏离本规格原文、或由你自行决定的行为，都写进报告的「未决问题」。**
- 只有影响「实现什么」的事才停下来；只影响「怎么验证」的事自己定。
- 公开仓库里不得出现本机绝对路径。
- 修改前端前，先读 `frontend/AGENTS.md` 和 `frontend/node_modules/next/dist/docs/` 里对应的文档。
- **白名单**：
  - 后端：`backend/tools/image_generation.py`、`backend/routers/chat.py`、`backend/services/chat_service.py`、`backend/main.py`（只在需要注册新路由时改）；
  - 前端：`frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`（只改重试类型）；
  - 新建：`backend/tests/test_image_model_choice.py`，以及按需新建的 `backend/routers/image_models.py`；
  - 文档：`README.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`PLAN.md`、`CLAUDE.md`（只改与本单相关的句子）；
  - 本目录 `03-report.md`。

## 4. 实现要求

### 4.1 模型登记（后端，服务端白名单）

在 `tools/image_generation.py` 里新增一份登记表。写法参考 `exchange_models.py:11-33`。前端只能传登记表里的 **id**，服务端再把 id 映射成供应商和真实模型名。

| id（前端传的值） | 显示名 | 供应商 | 真实模型名 | 需要的密钥 |
|---|---|---|---|---|
| `qwen-image-3.0`（默认） | `Qwen Image 3.0` | DashScope（现有路径） | 环境变量 `QWEN_IMAGE_MODEL`，默认 `qwen-image-3.0`（与现在一致） | `DASHSCOPE_API_KEY` |
| `seedream-5.0-flash` | `Seedream 5.0 Flash` | 火山方舟 | 环境变量 `SEEDREAM_IMAGE_MODEL`，默认 `doubao-seedream-5-0-flash-260915` | `ARK_API_KEY` |

- **环境变量**：在调用时读取，与现有 `QWEN_IMAGE_MODEL` 的写法一致。
- **可用性**：对应密钥非空即为可用，只判断「有没有配」，不发请求。
- **新增 `GET /image-models`**：
  - 需要登录，沿用全局鉴权中间件，不加进公开路径；
  - 返回 `{"default": "qwen-image-3.0", "models": [{"id", "label", "available"}]}`；
  - 不返回真实模型名、密钥变量名或任何配置值。
  - 路由可以放在新文件 `routers/image_models.py`，也可以放进现有路由文件，由你决定。

### 4.2 请求字段与透传

- **请求字段**：`routers/chat.py` 的 `ChatRequest` 新增 `image_model: Literal["qwen-image-3.0", "seedream-5.0-flash"] | None = None`，`mode` 为 chat、image、image_edit 时都接受。传不认识的值时由 Pydantic 返回 422（这是现有行为，不用额外处理）。
- **透传**：`ChatContext` 新增 `image_model: str | None = None`。
  - 必须带默认值，并且放在已有默认字段之后（有测试按位置构造 ChatContext）。
  - 由 `build_context` 从请求填入。
- **调用**：`stream_generated_image` 调用 `generate_image` / `edit_image` 时，`ctx.image_model` 为 `None` 或默认 id 的，按**现在的方式**调用，不多传任何参数；只有非默认 id 才多传关键字参数（例如 `model_id="seedream-5.0-flash"`）。
- **覆盖面**：自然语言生图（意图确认后的 `stream_intent`）和待补参数生图（`stream_pending`）都走 `stream_generated_image`。确认这两条路径也能拿到 `ctx.image_model`，并且同样遵守上一条。
- **选了不可用的模型时**：例如没有配置 `ARK_API_KEY` 却选了 Seedream，抛出 `ImageGenerationError("Seedream 生图暂不可用，请改选 Qwen Image 3.0。")`。不得悄悄改用别的模型；现有的失败退款机制照常退还草莓。
- **trace**：成功时记录真实模型名（现有行为）。失败分支（`chat_service.py:650-654` 一带）也写入本次选择的模型 id，例如 `state.trace["image_model"]`，方便排查是哪一个模型失败。不得记录提示词原文。

### 4.3 火山方舟供应商实现

- **新增异步函数**：在 `tools/image_generation.py` 里新增函数（例如 `_fetch_ark_png(prompt, size, model, api_key, *, reference_images=None)`），按第 2.1 节的字段直接 POST。
- **超时与重试**：沿用 `_TIMEOUT_SECONDS` 总超时，不自动重试。
- **响应读取**：
  - 用 `_read_bounded` 读，上限单独设 **40MB**（因为 b64 的 PNG 比 URL 大）；Qwen 路径的 1MB 上限不变。
  - 取 `data[0].b64_json` 做 base64 解码。
  - 解码后的字节必须通过现有 `_png_dimensions` 校验，并且不超过 `_MAX_IMAGE_BYTES`、`_MAX_IMAGE_PIXELS`，然后交给现有 `_persist_png` 落盘。
  - 文件命名、私有图判定、消息落库全部沿用现有逻辑。
- **尺寸**：
  - 生图：沿用 `_SIZES`。它的 1:1、16:9、9:16 三档都在方舟的像素范围内。
  - 修图「尺寸跟随图 1」时，如果图 1 的宽乘高小于 921600，或大于 `_MAX_IMAGE_PIXELS`，要**保持宽高比**缩放到范围内：宽和高各取 8 的倍数，并且不超出方舟上限 4624220 与本项目上限 2048×2048。
  - 不论生图还是修图，宽高比都要在 [1/16, 16] 之内（`_SIZES` 本来就满足）。
- **参考图**：沿用 `_reference_image_bytes` 读取已授权的本地 PNG，转成 `data:image/png;base64,...`；1 张传字符串，2–3 张传数组。
- **错误映射**：新增 `_ark_error(status, data)`，返回的 `ImageGenerationError` 文案与现有 `_provider_error` 风格一致：
  - code 中包含 `SensitiveContentDetected` / `RiskDetection` / `PolicyViolation` / `PrivacyInformation` / `DeepFake` → 「描述或参考图未通过内容审核，请修改后再试。」
  - 429、`RateLimit`、`QuotaExceeded` → 「图片生成服务繁忙，请稍后再试。」
  - 401、403、404，以及 `ModelNotOpen` / `AccountOverdue` / `InvalidEndpointOrModel` → 「Seedream 生图暂不可用，请改选 Qwen Image 3.0。」
  - 其他 → 「图片生成失败，请稍后再试。」
  - 文案里不得带供应商返回的原文、code 或请求 ID。
- **日志**：如需打印，只打印供应商名、HTTP 状态和 code，不打印提示词、参考图或密钥。

### 4.4 前端（`frontend/app/page.tsx`）

- **状态**：新增 `imageModel`，默认 `"qwen-image-3.0"`。
  - 用 `localStorage` 记住上次的选择，键名例如 `fiona_image_model`。读写都包在 try/catch 里。
  - 读出的值不在下面的列表里时，回落默认值。
  - 换账号、新建或切换会话时**不重置**这个选择，它是个人偏好。
- **获取模型列表**：
  - 页面加载后，用现有的 `apiFetch` 请求 `GET {API}/image-models`。
  - 请求失败时，用写死的两个选项作兜底，并且都视为可用（服务端会兜底报错）。
  - 某个模型 `available=false` 时，对应按钮 `disabled`，`title` 写「管理员尚未配置此模型」。如果当前选中的正好不可用，自动切回默认模型。
- **界面**：在生图分支（`page.tsx:2185-2193`，比例组之后、「返回聊天」之前）和修图分支（`:2180-2184`，「尺寸跟随图1」之后、「全部取消」之前）各加一个分段按钮组：
  - `role="group"`，`aria-label="图片模型"`；
  - 两个按钮的文字是 `Qwen 3.0` 和 `Seedream 5.0 Flash`，`title` 用完整显示名；
  - 写法照抄比例按钮：`cn("chip h-6 px-2 max-md:h-10", selected && "chip-on")`、`aria-pressed`、`disabled={isLoading || !available}`；
  - 两组之间可以用一个很淡的分隔，例如一个 `text-muted-foreground` 的「·」，或者 `gap-2`，由你决定，但不得引入新的颜色或类；
  - 手机宽度（<768）下这一行本来就会自动折行，保持 `max-md:h-10` 触控高度。
- **请求体**：`page.tsx:1532-1539` 的 body 里，**chat、image、image_edit 三种模式都带上** `image_model: imageModel`。chat 模式要带，是为了让自然语言生图跟随用户的选择。
- **重试**：`ChatBubble.tsx:84-90` 的 `ImageGenerationRetry` 加可选字段 `imageModel?: string`；`page.tsx` 失败时组装重试请求（:1739-1743 一带），把本次用的模型一起记下；重试时优先用记下的模型。
- **其他**：不改其他样式，不新增依赖，lint 警告数不得超过 25。

### 4.5 文档

- `README.md`、`docs/ARCHITECTURE.md`：生图可选两个模型；Seedream 走火山方舟，描述和参考图会发给字节跳动火山引擎；默认模型 Qwen；修图同样可选；草莓不变。
- `docs/DEPLOYMENT.md`：
  - 环境变量表加上 `ARK_API_KEY`、`SEEDREAM_IMAGE_MODEL`，注明 Seedream 需要先在方舟控制台开通；
  - 消费告警清单加上火山引擎；
  - 隐私说明加上第二个供应商。
- `PLAN.md`：新增一个 2026-10-06 小节。
- `CLAUDE.md`：模型行补一句生图模型。

## 5. 测试（新建 `backend/tests/test_image_model_choice.py`，全部打桩，不出网）

1. **登记表**：默认 id；两个模型的显示名；密钥为空时 `available=false`、非空时为 `true`；`SEEDREAM_IMAGE_MODEL` 和 `QWEN_IMAGE_MODEL` 在调用时生效。
2. **`GET /image-models`**：未登录返回 401；登录后结构正确；响应里不出现真实模型名、`ARK_API_KEY`、`DASHSCOPE_API_KEY` 字样。
3. **`ChatRequest`**：不认识的 `image_model` 返回 422；省略时为 `None`。
4. **透传与默认路径不变**：
   - 用一个记录调用参数的桩替换 `generate_image` / `edit_image`；
   - 默认 id 和 `None` 时，调用参数与现在**完全相同**（不带新增关键字）；
   - 选 Seedream 时，带上 `model_id`。
   - 三条路径都要覆盖：`mode=image`、`mode=image_edit`，以及 `mode=chat` 的自然语言生图（打桩意图模型返回 `generate_image`）。
5. **方舟请求**：用 `httpx.MockTransport`，或给 `httpx.AsyncClient` 打桩，断言：
   - URL、Bearer 头；
   - body 字段与第 2.1 节**完全一致**（`watermark` 为 `false`，`output_format` 为 `png`，`response_format` 为 `b64_json`）；
   - 生图时没有 `image` 字段；修图 1 张时 `image` 是字符串，2–3 张时是数组，并且顺序正确。
6. **方舟响应**：
   - 正常的 b64 PNG 能落盘，返回 `model` 为真实模型名，宽高正确；
   - b64 解出来不是 PNG、超过尺寸或体积上限、缺少 `data` 或 `b64_json`，都转成 `ImageGenerationError`，并且不留文件。
7. **错误映射**：每一类 code 和状态码各一例，断言文案；文案里不含原始 code 或 message。
8. **修图尺寸缩放**：图 1 为 512×512 时放大到 ≥921600 像素并保持宽高比；图 1 为 4000×1000 这类超大或超扁图时，缩小到上限内；宽高都是 8 的倍数。
9. **不可用模型**：没有 `ARK_API_KEY` 时选 Seedream，返回规定文案，不发请求，草莓退还（用生产态鉴权与余额，参照 `test_beta_billing.py::_prepare`）。
10. **trace**：失败时记录 `image_model` id，并且不含提示词。

## 6. 报告（新建 `03-report.md`）

- 逐条写出改动的文件和行号；
- 第 7 节验收命令的原样输出与退出码；
- `git status --porcelain --untracked-files=all`；
- 未决问题。

## 7. 验收（主会话独立重跑）

| # | 命令 | 期望 |
|---|---|---|
| A1 | `backend/` 下 `python -m pytest -q -p no:cacheprovider` | 全部通过；数量为 1938 加上新增用例数 |
| A2 | `git diff --stat -- backend/tests` | 已有测试文件 0 改动 |
| A3 | `frontend/` 下 `npx tsc --noEmit`、`npm run lint`、`npm run build` | tsc 与 build 退出码 0；lint 0 错误、警告不超过 25 |
| A4 | 主会话真实界面走查 | 生图和修图两行都显示模型按钮；选择会被记住；切换会话后保留；未配置的模型是灰的；请求体带 `image_model` |
| A5 | 主会话真实接口验收（用户开通 Seedream 后） | 文生图、单图修图、多图修图各一次，落盘为 PNG，无水印，耗时有记录 |
