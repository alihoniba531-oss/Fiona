# 规格修订 R2：验收与独立复核后的返修

日期：2026-10-10。本修订与 `02-spec.md`、`05-fix-r0.md`、`05-fix-r1.md` 同等效力，冲突处以本修订为准。

只做下列各项。其余实现保持现状，不回滚任何已完成的工作。R1 的判断器提示词 `IMAGE_PLANNER_PROMPT` 和预筛正则 `IMAGE_PLANNER_PREFILTER_PATTERN` 一字不改。

来源：
- 作者方在沙箱外的验收：默认全量通过；开关开启全量与 R1 报告一致；真实 Key 判断器评测、端到端出图、浏览器走查都已完成。
- 两份独立复核（见 `04-review.md`）。

## R2-1 判断器的调用时机要覆盖多轮补充（必须）

**现状**

只有本轮原话命中预筛时，才调用判断器。下面两种情况会让用户补充的画面被丢掉，平台还会按普通文字回复扣 10 颗：

1. 判断器不可用的那一轮按旧路由执行。旧路由追问「想生成什么画面？」并建立 `generate_image` pending。下一轮用户回答「一只橘猫在窗台上晒太阳」，这句不含预筛词，于是判断器没被调用，pending 被清除，转普通回复。复核用探针复现了这个过程。
2. 判断器判为不画，或回复模型自己追问「想画什么呀？」；或者上一轮刚写完提示词，用户回「就按这个来」。这些回答同样不含预筛词。

**改法**

判断器模式下，先检查是否存在 `generate_image` pending，以及本轮原话是否匹配现有的取消正则（`_run_chat_with_image_tool` 中生图 pending 用的那一条，抽成模块级常量后两处共用）：

- **存在 pending 且本轮是取消短语**：不调用判断器，直接交给 `_run_chat_with_image_tool`，按现有逻辑取消。
- **否则**，下面任一条件成立就调用判断器：
  - 本轮原话命中预筛，或命中 `explicit_image_intent`（现状）；
  - 存在 `generate_image` pending；
  - `ctx.history` 中最后一条 assistant 消息匹配新的模块级常量 `IMAGE_PLANNER_FOLLOWUP_PATTERN`（忽略大小写）：
    ```
    使用的描述|想生成什么画面|画|提示词|prompt
    ```

判断器的结果仍按 R1 第 3 节处理：要画、不画、不可用三种。判断器不可用时，旧路由原样执行；旧路由自己的 pending 补参逻辑会负责生成。

## R2-2 判断器「要画」时清除所有 pending（必须）

**现状**

`run_chat` 判断器「要画」分支只在 `pending.intent == "generate_image"` 时清除 pending。复核用探针复现了以下过程：

1. 用户说「帮我搜一下」，系统追问「搜啥？」，建立 `web_search` pending。
2. 用户改口「画一只猫」，出图后 `web_search` pending 仍在。
3. 用户说「哇好可爱」，被当作搜索词执行，又扣了 10 颗。

基线 `stream_intent` 确认生图时无条件 `clear_pending`，原生候选路径也是无条件清除。现状相对基线是回归。

**改法**

「要画」分支改为无条件执行 `await asyncio.to_thread(clear_pending, ctx.state_key)`，然后再执行生图。

## R2-3 Claude 原生模式只把「工具参数 JSON 解析失败」当作非法调用（必须）

**现状**

`backend/byok/client.py` 中 `ReplyStream._consume` 的 `except ValueError` 分支，在工具开启时会接住所有 `ValueError`。上游 SSE 中途出现坏 JSON（`json.JSONDecodeError`）或非法 UTF-8（`UnicodeDecodeError`）时，异常被吞掉，`tool_call_invalid=True`。原生模式下 Claude 的每一轮 friend 回复都带工具，所以与生图无关的普通聊天会被落库为「半截回复 +（这次没能生成图片……）」。工具关闭时，同样的错误会正常抛出，归类为「你的模型调用失败」。作者方用真实 anthropic 1.12.1 SDK 加 MockTransport 离线复现过。

**改法**

只有满足以下两条的异常，才按非法工具调用处理：

- `type(exc) is ValueError`（子类不算）；
- `str(exc).startswith("Unable to parse tool parameter JSON")`。这是 SDK `lib/streaming/_messages.py` 与 `_beta_messages.py` 中的固定前缀。

其他异常一律走原有分类：先按 timed_out / closed 判断，否则原样抛出。异常消息里带有工具参数 JSON，**不得写入日志、trace 或任何错误文案**。

**新增测试**

工具开启、SSE 中途出现坏 JSON、没有 tool_use 块时：必须抛出异常，不得返回 invalid。用真实 SDK 加 MockTransport，参照现有 `test_claude_sdk_value_error_without_tool_preserves_existing_error` 的做法。

再加一条正例：SDK 抛出带上述前缀的 `ValueError` 时，结果是 invalid，且日志里不出现 JSON 片段。

## R2-4 聊天 SSE 响应头加 `no-transform`（必须）

**现状**

`backend/routers/chat.py` 中 `/chat` 的流式响应头是 `{"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}`。前端经 Next 的 `/api` rewrite 代理访问后端时（本地 `next dev` 与 `next start` 都是如此），Next 内置的 compression 会对 `text/event-stream` 做 gzip 压缩。压缩缓冲让所有事件攒到流结束才一起到达浏览器。

作者方实测：
- 生图时，浏览器约 13 秒内都收不到「正在用 Seedream 5.0 Flash 生成图片…」状态，气泡一直是空的，图到达时所有事件一次性出现。
- 用最小 SSE 服务对照，`Cache-Control` 加上 `no-transform` 后，经同一代理，事件按 1 秒间隔实时到达，响应也不再带 `Content-Encoding: gzip`。

**改法**

1. `/chat` 的流式响应头改为 `{"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}`。`_ReservedChatResponse` 和普通 `StreamingResponse` 两条路径都用这组响应头，可抽成模块级常量。
2. 同文件 `_text_stream` 返回的 `StreamingResponse` 也带上这组响应头。
3. 不改其他文件的响应头，不改 `frontend/next.config.ts`。
4. 新增测试：
   - 用现有夹具发起一次 `/chat` 普通文字回复（回复流打桩），断言响应头 `Cache-Control` 含 `no-transform`、`X-Accel-Buffering` 为 `no`；
   - 再覆盖一条返回 `_text_stream` 的路径。
5. `docs/DEPLOYMENT.md` 中 `FIONA_BACKEND_ORIGIN` 联调那一段补一句：聊天流带 `Cache-Control: no-transform`，避免 Next 代理压缩缓冲导致流式事件延迟到达。

## R2-5 自带模型设置页的隐私说明要符合两种模式（必须）

**现状**

`frontend/components/ChatModelSection.tsx` 对所有厂商都写「启用后，由你的模型决定何时生图、撰写画面描述」。R1 之后，只有 Claude 和 DeepSeek（`deepseek-v4-pro`、`deepseek-flash`）是这样。通义、Kimi、智谱、自定义地址，以及 DeepSeek 的其他型号，都由平台判断器读取最近对话、发给阿里云 DashScope 来决定。现有文字对这些用户不实，也与 README 等文档矛盾。

**改法**

用下面这段替换现有那一段，逐字使用，作为一个静态段落，不按厂商分支渲染：

```
生图：选 Claude 或 DeepSeek（deepseek-v4-pro、deepseek-flash）时，由你的模型决定何时生图并撰写画面描述；选其他厂商时，在你的消息或上一条回复涉及画图时，平台的生图判断器（阿里云 DashScope 千问 qwen3.8-flash）会读取最近 6 条对话来决定是否生图、撰写画面描述。生图由平台执行并扣草莓，默认使用 Seedream 5.0 Flash，画面描述会发送给字节跳动火山引擎（点名千问时发送给阿里云），可能包含对话中出现过的内容。
```

**同步修改测试**

修改本任务新增的 `backend/tests/test_chat_image_tool_frontend.py::test_byok_settings_disclose_model_decision_platform_billing_and_seedream_privacy`，断言以下短语都出现：

- 「由你的模型决定何时生图」
- 「平台的生图判断器」
- 「最近 6 条对话」
- 「阿里云 DashScope」
- 「生图由平台执行并扣草莓」
- 「默认使用 Seedream 5.0 Flash」
- 「字节跳动火山引擎」

## R2-6 本轮原话的截断方式（必须）

**现状**

本轮原话只保留开头 600 字。用户贴一段长英文提示词、在末尾写「用 Seedream 画出来」时，判断器看不到这句指令。

**改法**

- 历史消息：每条最多 600 字，保持不变。
- 本轮原话：最多 1500 字。超过 1500 字时，取前 1000 字 + `……` + 后 500 字。

**同步修改**

- `test_image_planner.py` 中的相关断言；
- 六份文档和 `.env.example` 中「每条最多 600 字」的表述，改为「历史每条最多 600 字，本轮原话最多 1500 字（超长时保留首尾）」；
- R2-1 新增的调用时机（上一条回复与生图相关、存在待补充的生图请求）也写进文档里描述「何时调用判断器」的位置。

## R2-7 恢复 `docs/ARCHITECTURE.md` 中旧路由的实现说明（必须）

**现状**

`docs/ARCHITECTURE.md` 第 91 行附近，基线原有一整段旧路由说明被删除，且没有替代内容。被删的内容包括：

- `mode=image` 与比例；
- 候选经意图模型确认、增加的延迟；
- 讨论句兜底；
- 画面主体为空时先追问、不扣费；
- 描述用 `ctx.message.strip()`；
- `GET /image-models` 的鉴权与返回字段；
- SSE 顺序；
- possible 轮先送资源再报错。

同一行新增的「工具开启时，候选确认走带工具的 friend 回复」只对原生模式成立。

**改法**

1. 用 `git show 7ac7b57:docs/ARCHITECTURE.md` 取回原段落，原文恢复，并在段首注明适用于「开关关闭、判断器不可用、possible 轮与面板路径」。
2. 新增那句改为：「原生模式下，候选经确认后走带工具的 friend 回复；判断器模式下，先由判断器裁决，判为不画时跳过候选块，意图识别返回的 generate_image 视为无意图。」

## R2-8 小修（必须）

1. **非法调用通知**：没有前导文字时，落库正文和 SSE 文本都不以 `\n\n` 开头；有前导文字时保持现状。
2. **`image_source` 写入方式**：给 `_stream_image_execution` 增加关键字参数 `image_source`，默认 `"tool"`；判断器路径传 `"planner"`。删除 `run_chat` 中在每个事件后、以及在 finally 里反复写回 `image_source` 的代码。trace 的最终结果不变。

## R2-9 加强本任务新增测试（必须；只改本任务新增的测试文件）

1. **`test_chat_image_tool.py` 约 739–740 行**：`outcome='success'` 的平台判断器用例要断言：
   - 恰好生成一张图；
   - 落库正文含「图片已生成。」和「使用的描述」；
   - 扣费 10 颗。

   不得再用 `<= 1` 这类断言。约 880 行的 `done <= 1` 改为 `== 1`。
2. **约 618 行**：`all('tools' not in request ...)` 之前，先断言 `requests` 非空。
3. **约 371–382 行**：这条用例直接调用已恢复为基线的 `stream_normal`，`not calls` 恒真。改为走 `run_chat` 的真实路由。危机资源条数改为精确的期望值。
4. **`test_byok_image_tool.py` 约 230、253 行**：「请求体与基线字节一致」现在是新代码自己跟自己比。改为与 `git show 7ac7b57:backend/byok/client.py` 的请求构造结果比对（可参照 `test_stream_normal_is_restored_to_baseline` 的取基线方式）。做不到时，删除「bytes unchanged」措辞，改为如实描述测的是什么。
5. **`test_image_planner.py` 约 141 行**：`assert content not in caplog.text` 在参数 `content="3"` 时，可能因日志里的 `elapsed_ms` 含数字 3 而误报。改为断言日志不含该用例特有的、不会与数字冲突的特征串。
6. **为 R2-1 至 R2-8 各补测试**：
   - R2-1：存在 pending 且回答未命中预筛时，判断器被调用；判画则出图并清 pending；判不画则清 pending 并普通回复；取消短语不调用判断器并按现有逻辑取消；上一条 assistant 含「使用的描述」或「提示词」时，判断器被调用；上一条 assistant 与生图无关、本轮未命中预筛时，判断器不被调用。
   - R2-2：「要画」后，`web_search` pending 被清除，下一句不会执行搜索。
   - R2-3 到 R2-8：如各节所述。

## 验收

与 R1 相同：

- 受保护文件零 diff；
- 任务前既有测试零改动，`conftest.py` 仍只有那一行；
- `routers/chat.py` 不在受保护名单内，本单允许修改，但只改 R2-4 所述内容；
- 默认全量、开关开启并加载 `-p image_planner_stub` 的全量，各跑一次，列出全部非通过项及原因；
- 本任务新测试全部通过；
- `pip check` 通过；
- `npx tsc --noEmit`、`npx eslint .` 均为 0 errors。

结果追加到 `03-report.md` 的新节「R2」，不改写之前各节。

沙箱里无法绑定回环端口的测试照旧单列，由作者方在沙箱外复验。
