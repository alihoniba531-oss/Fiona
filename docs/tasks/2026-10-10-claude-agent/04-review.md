# 独立复核（首轮实现）

日期：2026-10-10。两份只读复核（Opus 5.5），对象为 b7a27cf 之上的首轮工作区改动。必须修复项已转入 [05-fix-r1.md](05-fix-r1.md)。

## 后端复核：Claude 智能体模式（基线 b7a27cf，工作区未提交改动）

范围：`backend/services/claude_agent.py`（新）、`backend/byok/client.py`、`backend/services/chat_service.py` 的 diff。
方法：通读代码与规格 02-spec.md，核对 anthropic 1.12.1 源码（`types/beta/*`、`lib/streaming/_beta_messages.py`、`_utils/_json.py`），新测试 95 项全过；另在 `scratchpad/wo7/review/probe/` 写了离线探针（复用 `tests/test_claude_agent_runtime.py` 的 harness，socket/DNS 硬拦截），4 项探针全部复现下面的问题。未改仓库文件。

---

## 必须修复

### M1. 计费在落库之前就成立：会话被删或客户端断开时仍扣 10 颗，生成的图还会被删掉

- **位置**
  - `claude_agent.py:523`：卡片交付即 `state.billable = True`。
  - `chat_service.py:1061`：智能体模式（`agent_result is not None`）下，`_stream_image_execution` 仍在**没落库**时设置 `state.billable = True`。
  - `claude_agent.py:303-316, 542, 567-570`：落库失败只记 trace，计费不回退。
  - `claude_agent.py:573-577`：未落库的图会被删除。
- **触发与结果**
  1. **会话中途被删**：工具卡已交付，之后 `_save_response` 返回假值并抛 `RuntimeError`。结果是 `billable` 仍为 True，`run_chat` finally 不退款，用户被扣 10 颗。错误文案还显示成「你的模型调用失败：调用失败」。探针 `test_deleted_conversation_after_card_still_billable` 已复现。旧路径的 `_save_response` 文档写的是「删除后不重建也不扣费」，旧工具路径（`chat_service.py:1443-1445`）也是先落库、后设 billable。
  2. **客户端断开**：天气卡已发出，Claude 第二步还在写（可能长达数分钟）时用户关掉页面。结果：没有落库（`saves == []`），`billable=True`，扣 10 颗。探针 `test_disconnect_after_card_keeps_charge_without_persist` 已复现。
  3. **生图成功后断开或出现异常**：图片成功、`billable=True`，但随后被取消或落库失败。`finally` 会删掉这张图，扣费不退。用户付了钱，刷新后什么都没有。
- **规格依据**
  - 3.6「本轮至少有一个计费项成功交付时结算」，以及「已经交付过……先落库已交付的内容」：计费的前提是交付并落库，与旧路径「先存后结算」一致。
  - 3.6「还什么都没交付：……退款」。
- **建议改法**
  - 智能体内部用局部变量 `billable_pending` 累加计费项。只在 `save_delivered()` 成功、`state.response_saved` 为真之后，才执行 `state.billable = state.billable or billable_pending`。
  - `_stream_image_execution` 在 `agent_result is not None` 时不要设置 `state.billable`，改为在 `agent_result` 里返回 `success`，由智能体统一结算。
  - 会话删除导致落库失败时，错误文案沿用旧路径（「服务暂时不可用」或「会话已删除或不可用」），不要归到「你的模型调用失败」。

### M2. generate_image 工具失败后，前端必定报「图片生成未完成，请重试。」

- **位置**
  - `chat_service.py:1004`：发出 `{"status":"generating_image","source":"tool"}`。
  - `claude_agent.py:458-462`：吞掉随后的 `error` 事件（只写进 `result["error"]`，不转发）。
  - 前端 `frontend/app/page.tsx:1840-1845, 1944`。
- **触发**：Claude 调用 `generate_image`，Seedream 审核不过、未开通或超时（`ImageGenerationError`，在 status 事件之后抛出）。随后 Claude 如实说明「没画成」，后端正常发出 `done`。
- **结果**
  - 前端收到 status 后置 `generatingImage = true`，整轮没有收到 `generated_image`，收尾时 `throw new Error("图片生成未完成，请重试。")`。
  - 气泡被改成「…\n\n错误：图片生成未完成，请重试。」。
  - Claude 后续说明期间，「正在用 Seedream 生成图片…」状态一直挂着。
  - 库里落的是正常正文，所以刷新前后显示不一致。
  - 探针 `test_image_failure_after_status_sequence` 输出的事件序列为 `reply_model, text, status, text, done`，没有 `generated_image`。
- **规格依据**
  - 3.3「失败时为失败原因」交给 Claude，由 Claude 如实告知，整轮不是错误。
  - 3.6：错误事件只用于中途出错。
  - 4「生成中的状态卡与文字同时显示的逻辑保持现状」：这里的现状没有覆盖「工具失败但整轮继续」。
- **建议改法**：二选一。
  - 后端：智能体模式下生图失败时转发一个结束状态事件，例如 `{"status":"image_failed","source":"tool"}`；前端收到后把 `generatingImage` 置回 false 并清除 `generationStatus`。
  - 前端：收到 `source:"tool"` 的生图状态后，如果之后又收到 `done`，就不再按「未完成」报错，并清除状态。
  - 两种方式都要补测试。

### M3. 多步回灌用 `exclude_none=True`，会丢掉 API 要求必须存在的 null 字段，可能被 400

- **位置**：`claude_agent.py:62-67` `_block_dict`，`model_dump(mode="json", by_alias=True, exclude_none=True)`。
- **触发**：Claude 在第 1 步联网搜索并写出带引用的文字，然后调用客户端工具（或遇到 pause_turn），第 2 步回灌这段 assistant content。引用为 `web_search_result_location` 且 `title: null`；或 web_fetch 文档引用为 `char_location` 且 `document_title: null`。
- **结果**
  - 回灌后引用里的 `title` / `document_title` 键直接消失。
  - SDK 请求类型 `BetaCitationWebSearchResultLocationParam.title`、`BetaCitationCharLocationParam.document_title` 都标注为 `Required[Optional[str]]`：键必须存在，值可以是 null。
  - SDK 自己回灌模型对象时用的是 `openapi_model_dump`（`_utils/_json.py:53-57`：`exclude_unset=True, mode="json", by_alias=True, exclude=__api_exclude__`），会保留显式的 null。
  - 探针 `probe_dump.py` 对比结果：智能体输出 `{'cited_text','encrypted_index','type','url'}`，SDK 输出多了 `'title': None`。
  - 一旦服务端按 schema 校验，第 2 步请求就会 400：已流出的文字会落库，然后报「请求参数不被接受」。
- **规格依据**
  - 3.2「把本次 assistant content……原样追加」。
  - 复核要求「不得给 Anthropic 发出会被 400 拒绝的请求」。
- **建议改法**
  - `_block_dict` 改用 `anthropic._utils._json.openapi_model_dump(block)`；或者照它的写法 `block.model_dump(mode="json", by_alias=True, exclude_unset=True, exclude=getattr(block, "__api_exclude__", None))`，与 SDK 回灌行为一致。
  - `parsed_output` 的 Field 本身带 `exclude=True`，不受影响。
  - 加一条测试：带 `title=None` 引用的块回灌后，键仍然存在。
- 是否一定 400 需要真实 Key 确认，但改法零成本，而且与 SDK 官方回灌路径一致，建议直接改。

### M4. 天气城市规则误拒合理输入：「北京市」对「北京」，以及只比对规范化结果

- **位置**：`claude_agent.py:95-105` `_city_is_allowed`、`:493-498`。
- **触发与结果**
  1. 主人说「北京明天冷吗」，Claude 传 `city="北京市"`。`normalize_city("北京市")` 返回「北京市」（`_SUFFIXES` 里没有「市」），而「北京市」不是「北京…」的子串，于是不执行，tool_result 返回「主人没有说过这个城市，请先问主人想查哪个城市」。Claude 只能反问用户刚刚说过的城市。探针 `test_city_with_shi_suffix_rejected` 已复现。Claude 给城市补「市」很常见。
  2. 第 102 行 `normalized = normalize_city(raw) or raw`：只要原文能规范化出非空值，就**只**拿规范化结果比对，而规范化结果总是原文的子串，范围更窄。例如主人说「那曲市天气」，规范化后成了「曲市」（先剥后缀「天气」，再剥前缀「那」）；Claude 传「那曲」时比对不上，被误拒。
- **规格依据**：3.3「规范化后做子串比较」。规则本意是挡住记忆里的城市，而不是挡住主人亲口说的城市。复核清单第 4 点也点名了这个场景。
- **建议改法**
  - 对 Claude 传入的城市生成候选：规范化值本身，以及去掉行政后缀（市、省、区、县、自治州等）后长度仍 ≥2 的变体。
  - 对每条原文，同时与原文本身和规范化结果做子串比较。
  - 命中时，用**命中的那个候选**（即主人说过的写法）去查天气。这样仍然只发送主人亲口说过的文字，隐私边界不变。
  - 补充反例测试：只在记忆里出现的城市仍然拒绝。

---

## 需要真实 Key 核实的点

1. **图片大小和尺寸上限**（看图，`_agent_messages:82-86`）
   - 上传上限是原图 5MB，重编码后 base64 约 6.7MB。Anthropic 单图上限 5MB，报错时的计量对象可能是 base64 长度；单边最大 8000px。
   - 大于约 3.7MB 的 JPEG 或超大尺寸图，可能被 400，用户看到「请求参数不被接受」。
   - 建议实测 4.5MB 的 JPEG，以及 9000px 宽的 PNG。必要时在交给 Claude 前按长边和体积降采样，这一步只作用于发往 Anthropic 的副本。
2. **pause_turn 续传**（`claude_agent.py:404-410`，`client.py:426-430`）
   - 续传时最后一条是 assistant 消息。需确认 5.5 系列在禁用预填充的情况下，是否仍接受 pause_turn 原样续传。
   - 需确认 cache_control 加在这条 assistant 消息的最后一个块上时，块类型是否允许：`thinking`、`redacted_thinking`、`fallback` 都没有 cache_control 字段；空文本块、以空白结尾的文本也会被拒。
   - 若有问题，pause_turn 续传时把 cache_control 放到最后一个允许的块上，或者不加。
3. **fallback 裁剪**（`_assistant_content` 默认 `trim_fallback=True`）
   - SDK 文档（`beta_fallback_block_param.py`）要求「原样回灌，fallback 块留在原位」，并说明 thinking 跨越边界时省略该块会被拒。
   - 规格要求裁掉 fallback 块及其之前的内容。裁剪后不存在跨边界的 thinking，理论上可以，但需要用真实 fallback 加 thinking 的回合验证。
4. **服务器端工具**
   - `web_fetch_20260209` / `web_search_20260209` 在 beta 端点上是否还需要额外 beta 头（目前只带了 `server-side-fallback-2026-07-01`）。
   - 动态过滤是否要求声明 code execution 工具。回灌 `code_execution_tool_result` 等块时，当前 dump 能保留字段。
   - haiku 用的旧版本能否和 `eager_input_streaming` 共存。
5. **`eager_input_streaming` 下工具 JSON 非法**
   - SDK 会在流内抛 `ValueError("Unable to parse tool parameter JSON …")`（`_beta_messages.py:518-521`）。
   - 智能体路径（`client.py:314-324`）只对 `image_tool` 吞掉这个错误，`agent_stream` 下整轮报「调用失败」。
   - 需确认实际发生的频率。若较常见，建议在 agent_stream 下把它当作「本步工具参数无效」，回给 Claude 一条 tool_result，而不是让整轮失败。异常文本里含工具参数（城市），目前没有写入日志，需继续保持。
6. `usage.server_tool_use.web_search_requests` / `web_fetch_requests`：SDK 1.12.1 的 beta 和非 beta 版本都有这两个字段，需确认真实响应确实带有。

---

## 可优化

1. **每日次数先于全局槽计数**（`claude_agent.py:319-336`）
   - 全局槽等满 10 秒仍繁忙时，已经消耗了 1 次 `byok_chat`。CLAUDE.md 写的是「先检查并发，再计每日次数」。
   - 首次获取槽也会等 10 秒，文案是「通道繁忙」，旧文案是「自带模型通道繁忙，请稍后再试」。规格 3.6 要求「什么都没交付时错误文案不变」。
   - 建议：首次获取不等待并沿用旧文案，或者把计数挪到首次拿到槽之后。
2. **出错路径补发来源卡**（`claude_agent.py:560-566`）
   - 前面什么都没交付、只有搜索来源时，出错前补发一张来源卡，并把「［卡片：[联网搜索]］」落成一条 assistant 记录。下一轮 Claude 会看到这条空洞的历史。
   - 建议：仅当已有其他交付时才补发，或者来源卡不单独算作交付。
3. **工具失败让 trace 判为失败、后续任务被跳过**
   - 工具异常（`:519`）或生图失败（`chat_service.py:1076`）会写 `state.trace["error"]`。整轮正常落库时，`_normal_followups` 仍被跳过（`:544`，每 5 条一次的画像提取会漏掉），`log_event` 也记为 `success=False`。
   - 建议：工具级错误写进 `agent_tool_errors` 之类的字段，不占用 `error`。
4. **生图事件丢失后的孤儿文件**
   - 预算恰好在生图完成那一刻耗尽时，`generated_image` 事件可能没被消费，`agent_result.success` 却已为真。如果此前已有文字交付，`save_delivered` 会以 `image_path=None` 落库，`response_saved=True`，`finally` 不再删除这张图。
   - 结果：上传目录里留下孤儿文件，而且 `billable=True`（与 M1 同源）。
   - 建议：落库前用 `owned_image_result` 兜底 `image_path`，或者在未消费事件时删除。
5. **平台侧失败被说成用户模型失败**
   - 进入循环前的 `get_pending`、`detect_mode`、`_agent_messages` 等平台步骤失败时，外层统一显示「你的模型调用失败：调用失败」。
   - 旧路径同类失败显示「服务暂时不可用」。
6. **多步文字缺少分隔**
   - 各步的 Claude 文字直接相连，落库和 SSE 都没有分隔，例如「我查一下。［卡片：…］今天晴。」或「我来搜一下根据结果…」。
   - 建议：步与步之间补一个换行。
7. **生图心跳重复**：生图等待期间，执行核心和 `_wait_task` 各自发 `: generating-image`，最多每 10 秒两条。无害。
8. **tool_result 缺少 `is_error`**：失败时可以加 `"is_error": true`，帮助 Claude 判断。

---

## 已核实无问题的要点

1. **启用条件与位置**
   - `_claude_agent_enabled`（`chat_service.py:263-277`）每轮读取开关；只有字面 `0` 关闭；非法值告警一次。
   - 条件：`request_mode=="chat"`、`crisis_level is None`、enabled、`provider=="anthropic"`、`byok_error is None`、`not byok_unreserved`。
   - 位置在 high 危机、面板 image / image_edit、修图引导之后，在 `_image_tool_enabled` 之前（`:1714-1718`）。
   - 开关关闭时只多一次判断，后续代码不变。
2. **旧路径逐字节不变**
   - `convert_messages` 在 `preserve_blocks=False` 时，判定、合并、弹出逻辑与原来等价。
   - `_open` 未改；`ReplyStream` 只新增 `final_message` 赋值。
   - `_stream_image_execution` 在 `agent_result is None` 时：全文拼接、落库、`done`、finally 删除条件都与原来一致。
3. **SDK 回灌字段**
   - `by_alias=True` 正确输出 fallback 的 `from`。
   - thinking 的 `signature`、`web_search_result.encrypted_content`、`server_tool_use.input`、`caller` 均保留，空字符串不会被 `exclude_none` 丢掉。
   - `ParsedTextBlock.parsed_output` 由 Field 的 `exclude=True` 排除。
   - fallback 块可以回灌（`BetaFallbackBlockParam` 明确「Accepted in messages[].content」）；pause_turn 用 `trim_fallback=False` 原样回灌是合法的。
   - 例外见 M3：null 必填键。
4. **cache_control**
   - system 一个、最后一条消息的最后一个块一个，共 2 个断点，不超过 4 个。
   - `_prepare_agent_messages` 改的是 `convert_messages` 深拷贝出来的副本，不会污染循环里的 `messages`。
   - 首个请求的最后一个块是非空用户文字，工具步是 tool_result，都允许加 cache_control。
5. **system 顺序**：工具说明在安全规则之前；安全规则恰好一次，位于末尾；带朗读的 trailing system 时同样成立。
6. **锁与槽**
   - 每用户锁在外层 `stream_claude_agent` 中获取，`finally` 释放。
   - mirror 分支先释放、把标志置 False，再交给 `stream_mirror`，由它的 `_byok_slot(ctx.user)` 重新占用，不会重复释放别人的锁。
   - 全局槽 `__enter__` 失败时没有残留；拿到槽后到 `try` 之间没有挂起点；每步 `finally` 都执行 `__exit__`；关流在 shield 中进行。
   - 客户端工具和生图都在全局槽之外执行。`_wait_task` 取消时在 shield 中回收任务。
7. **上限**
   - 4 次工具后，第 5 次返回固定 tool_result，再给一次作答；仍然 tool_use 时以 `tool_limit` 结束。
   - 每轮一图（`image_success` 判断）。
   - 8000 字跨文字和生图描述累计截断；单次仍受 4000 字限制。
   - 预算默认 240，范围 60–290，非有限值回落默认；每次请求的时限取 `min(剩余, 现有时限)`。
   - pause_turn 最多续 2 次。
   - `byok_chat` 每轮计 1 次，mirror 分支由 `stream_mirror` 自己计数，没有重复。
8. **计费累加**：使用 `state.billable or _tool_billable(...)`，`error` 或 `stale` 的卡片不计费，后续失败不会把计费改回 False（落库前提的问题见 M1）。
9. **生图附件所有权**
   - 成功时执行核心不删，所有权交给智能体。
   - 智能体 `finally` 用 `owned_image_result` 兜底，未落库就删除。
   - 第二次生图有效时不执行；第一次失败后重试会替换 `owned_image_result`，不会泄漏。
10. **看图**
    - data URI 由 `_save_uploaded_image` 规范化为 `data:image/{png|jpeg|gif|webp};base64,…`，mime 解析正确。
    - `has_image` 为真时 `image_base64` 一定非空。
    - 块顺序为时间、图片、文字。
    - 本轮有图时不调用 `detect_mode` / VL。
    - `image_summary` 取 Claude 文字的前 120 字。
11. **来源卡**
    - 只取自 `web_search_tool_result.content[]`，以及 `web_fetch_tool_result.content`（type 为 `web_fetch_result`，标题取自 `content.title`），与 SDK 1.12.1 的类型一致。
    - URL 经 `utils.safe_http.validate_public_http_link` 校验（与 card_detail 使用的是同一个函数）。
    - 去重，最多 5 条，标题不超过 80 字，不从正文抽取链接。
12. **隐私**
    - trace 只记工具名、次数和 usage；日志只记类别或类型名。
    - 天气参数、SDK 的 JSON 解析异常文本都不会进入日志或 trace。
    - 工具模块（route、travel、hot、amap）没有打印参数。
    - 城市规则不读取记忆和 system，只读本轮原文和最近 3 条 user 原文；单字城市被 `normalize_city` 拒绝。子串命中是规格明确的口径。
13. **pending**：进入智能体路径时清除任何 pending；智能体路径不写 pending。

---

## WO7 Claude 智能体模式：前端 / 文档 / 新测试 / 报告 复核

基线 b7a27cf，工作区未提交改动。只读复核；本机 `backend/.venv/bin/python -m pytest -q tests/test_claude_agent_*.py` → `129 passed`。

## 必须修复

### M1. 新前端测试依赖 `frontend/node_modules`，CI backend 任务会挂 3 条
- 位置：`backend/tests/test_claude_agent_frontend.py:137-163`（`render_card`：`require('typescript')`、`require('react')`、`require('react-dom/server')`，`cwd=ROOT/"frontend"`，`check=True`）。
- 触发 → 结果：`.github/workflows/quality.yml` 的 backend 任务只装 Python 依赖，不跑 `npm ci`；`frontend/node_modules` 被 `frontend/.gitignore:4` 忽略，CI 检出里没有。ubuntu-latest 自带 node，所以 `node -e` 能起，但 `require('typescript')` 抛 MODULE_NOT_FOUND → `CalledProcessError`。本机在无 node_modules 的目录执行同一 require 已复现失败。CI 会挂的用例：
  - `test_web_sources_card_renders_only_valid_sources_with_fixed_title[points0]`
  - `test_web_sources_card_renders_only_valid_sources_with_fixed_title[points1]`
  - `test_shared_renderer_keeps_weather_and_generic_cards`
  
  `run_cards` 的 3 组用例只用裸 node，不 require 任何包，CI 能过；`test_non_append_processing_body_is_unchanged` 是写死的 SHA256，也能过。
- 规格依据：§6 新测试必须离线、不依赖本机才有的东西；§7 第 4 项要求全量通过；CI Quality 必须是绿的。报告 §4.1 说「本任务新增测试 129 passed」，这只在装了前端依赖的本机成立。
- 建议改法（二选一或组合）：
  1. `render_card` 开头加 `if not (ROOT/"frontend/node_modules/typescript").exists(): pytest.skip(...)`（同样检查 react、react-dom）。同时补一组不依赖包的源码断言，保证 CI 仍覆盖 web_sources 分支：web_sources 标题三元式、`cardData.subtype !== "web_sources" && <ul`、来源标题条件、`.slice(0, 5)`。写法参照 `test_chat_image_tool_frontend.py`。
  2. 把渲染测试挪到 frontend 任务（例如 vitest 或 node 脚本），backend 测试只保留源码断言。

### M2. 智能体轮生图失败后，前端仍追加「错误：图片生成未完成」，并清空朗读队列
- 位置：`frontend/app/page.tsx:1840-1843`（收到 `status:generating_image` 后置 `generatingImage = true`）、`frontend/app/page.tsx:1944`（流结束时 `generatingImage && !generatedImageReceived` 就 throw）。联动的后端位置：`backend/services/chat_service.py:1004` 在调用生图前先发 `status:"generating_image", source:"tool"`；`backend/services/claude_agent.py:460-462` 吞掉生图的 error 事件，status 事件照常转发。
- 触发：智能体轮里 Claude 调用 `generate_image`，状态事件已经发出，随后 Seedream 失败（审核不过、未开通或欠费、上游错误）。后端按规格把失败原因作为 tool_result 回灌，Claude 接着如实作答，最后发 `done`。
- 结果：前端没收到 `generated_image`，`generatingImage` 仍为 true，流结束时第 1944 行 throw。catch 分支把气泡改成「Claude 的回答 + \n\n错误：图片生成未完成，请重试。」，并执行 `clearTtsQueue()`、清空 `ttsBuf`，Claude 回答里还没念的部分被丢掉。另外，在 Claude 后续作答期间，「正在用 Seedream 5.0 Flash 生成图片…」转圈卡一直显示，直到 finally 才清除。一轮正常结束的对话被标成出错，和后端记录（已落库、没有 error 事件）不一致。
- 规格依据：§3.3「generate_image … 失败：失败原因」作为 tool_result 交给 Claude，不是整轮错误；§3.6 只有 Claude 请求失败、超时、预算耗尽、槽位繁忙才发 error；§4「生成中的状态卡与文字同时显示的逻辑保持现状」，前提是这一轮最终不报错。
- 建议改法：
  - 前端：第 1944 行改成 `if (generatingImage && !generatedImageReceived && !(imageGenerationFromTool && responseComplete)) throw ...`。基线里 tool 来源的生图失败一定先发 error 事件并在流内 throw，所以这个放宽只影响智能体轮。另外在收到后续 `text`、`append` 卡片或 `done` 时清除 `generationStatus`。
  - 或者后端：吞掉 error 时补发一个让前端复位的事件（例如 `{"status": "image_failed"}`），前端据此复位 `generatingImage` 和 `generationStatus`。
  - 补一条 node 驱动的事件序列测试：status(tool) → text → done，断言最终 content 里没有「错误：」，且 clears 计数不变。

### M3. 规格 §6 测试点 9「智能体路径不写 pending」没有任何断言
- 位置：`backend/tests/test_claude_agent_runtime.py`、`test_claude_agent_integration.py`、`test_claude_agent_routing.py`。三个文件都没有桩或断言 `set_pending`（全部新测试 grep 为零）。runtime 只断言了 `clear_pending` 被调用（`h.clears == [h.ctx.state_key]`）。
- 触发 → 结果：如果以后有人在智能体路径或它前面的 run_chat 段落里加回 `set_pending`（比如天气缺城市时），新测试仍全绿。目前代码里 `claude_agent.py` 确实没有调用 `set_pending`，所以这是覆盖缺口，不是行为错误。
- 规格依据：§2.1「平台不读、不写 pending」；§6 必须覆盖第 9 点「智能体路径不写 pending」。
- 建议改法：在 runtime 的 harness 和 integration 的 lifecycle 里都 `monkeypatch.setattr(chat, "set_pending", lambda *a, **k: pytest.fail("agent must not write pending"))`；再加一条用例：天气城市未授权、缺参、mirror 三种情形都不写 pending。

## 可优化

1. **web_sources 卡在没有合法来源时只剩空标题框**：`frontend/components/ChatBubble.tsx:137`。web_sources 的渲染条件不看 `safeSources.length`。后端已经用 `validate_public_http_link` 过滤，但前端 `toSafeExternalUrl` 的口径不一定完全一致（比如带凭据的 URL），两边口径一旦不同，就会出现只有「联网搜索」标题的空卡。建议条件改成 `(card.subtype === "web_sources" && safeSources.length > 0)`，需要把 safeSources 的计算提到条件前面。
2. **隐私日志断言对 INFO/DEBUG 级别不起作用**：`test_claude_agent_runtime.py` 的 `test_single_weather_round_persistence_daily_cap_and_privacy`。仓库没有配置 pytest `log_level`，`caplog` 只能收到 WARNING 及以上，城市名如果以 INFO 级别写进日志，这条断言会照样通过。当前实现用 `print`，capsys 能捕获。建议在用例开头加 `caplog.set_level(logging.DEBUG)`。另外这里 `execute_intent` 是桩，真实天气工具的日志没有走到；工具本身未改，可以接受。
3. **危机（测试点 10）只测了判定函数**：`test_claude_agent_routing.py::test_each_enable_condition` 直接调用 `_claude_agent_enabled`。没有 run_chat 层面的用例证明 `state.crisis_level` 在判定前已经赋值。建议加一条：run_chat 带 `crisis="possible"` 和 `"high"`，把 `stream_claude_agent` 桩成 `pytest.fail`。
4. **「只有失败工具时退款」只断言了 billable**：`test_successful_card_billing_cannot_be_cleared_by_later_failure[False]` 只检查 `state.billable is False`，没有经过 run_chat 断言 `refund_strawberries` 被调用 1 次。integration 只覆盖了「看图+搜索免费」这一种退款。建议补一条 integration 用例：失败卡片 → `len(refunds) == 1`。
5. **ChatCard 与基线等价只有短语级断言**：`test_shared_renderer_keeps_weather_and_generic_cards` 只检查片段包含关系。我已用基线 `b7a27cf` 的 ChatBubble 抽出旧的两个块，和新 ChatCard 做 `renderToStaticMarkup` 逐字比较，8 种卡形全部一致（通用、带来源含非法 URL、travel_plan 错误卡、空 points、三日天气、空 forecast 天气、hot_topics、长 url 无来源）。这份证据测试里没有固化。建议写死 1–2 张卡的期望 HTML（同样要处理 M1 的 CI 依赖问题）。
6. **03-report.md 有 7217 行**：主要是全量失败的原始 traceback，放进公开仓库太臃肿。敏感信息检查过，没有问题（见下）。建议把 §4.3、§4.4 的长输出折叠成摘要，原始输出不入库。

## 已核实无问题的要点

**A. 前端**
- `append === true` 分支（`page.tsx:1874-1886`）只往 `cards` 里追加，不碰 `reply`、`content`、`ttsBuf`、`clearTtsQueue`、`cardData`、`pendingTtsText`。`test_append_cards_preserve_text_legacy_card_and_speech_queue` 用 node 实际执行了这段分支。
- 非 append 分支的判断条件由 `if (data.card)` 改成 `data.append !== true`，主体从 `// 旅行规划卡：` 到 `if (data.done)` 和基线逐字一致。我用 `git show b7a27cf` 重算 SHA256 得到 `e0718e49…b0ce`，与测试写死的值相同。`append` 取值为 `false`、`"true"`、`1`、缺省时都走旧逻辑，有参数化测试覆盖。
- ChatBubble 抽出的 ChatCard：天气卡条件 `message.cardData?.subtype === "weather" && …` 等价于 `cardData && <ChatCard>` 加上 `card.subtype === "weather" && …`。通用卡在非 web_sources 时，条件、来源标题 `source || "网页"`、url 截断行、`<ul>` 要点、「来源」小标题都原样保留。Fragment 不产生 DOM，flex 的 `gap-2` 子元素结构不变。静态 markup 比对 8 种卡形全部一致（见可优化 5）。`memo(ChatBubble)` 是浅比较，message 对象换了引用就会重渲染，cards 更新能显示出来。
- 渲染顺序：图片 → 状态卡 → 文字气泡 → 旧 `cardData` → `cards`（按追加顺序，key 用 index，只增不删）。符合「在文字气泡之后按顺序渲染」。
- web_sources 卡：标题固定为「联网搜索」，不显示 points、url 截断行和「来源」小标题；来源经 `toSafeExternalUrl` 过滤，最多 5 条，用 `openExternal` 打开。
- 历史重载：`lib/useConversations.ts:54-67` 的 `toMessages` 不设置 `cards` 和 `cardData`，重载后都是 undefined，不渲染卡片，和「卡片不落库」一致。`refreshList` 只刷新会话列表，不会冲掉刚生成的 cards。出错时 catch 分支把 failure 展开合并进原消息，已追加的 cards 保留。
- 设置页新文案与规格 §4 代码块逐字一致（脚本比对 `<p>{spec文本}</p>` 在源码中为 True），位置在「生图：」段之后。另外改了两段已有文案（平台处理范围、看图计费），改后的内容符合实际行为；不改的话旧文案在智能体模式下会说错，属于必要同步。

**B. 文档**
- 六个文件都写了：启用条件（chat、crisis 为空且 high/possible 都排除、anthropic、无 byok_error、非 byok_unreserved）、开关语义（默认 1、只有字面 0 关闭、非法值只告警一次、每轮读取）、`FIONA_CLAUDE_AGENT_TOTAL_SECONDS` 240（60–290）、每次请求取剩余预算和 BYOK 时限中的较小值、4 次工具、8000/4000 字、每轮一张图、10 秒重新拿槽、每用户锁和全局槽的分工、心跳、数据流（图片和工具结果发给 Anthropic，搜索计入用户额度）、计费（10 颗只预扣一次，按累加口径结算，搜索和看图不扣）、天气城市规则、已知局限（历史图只发摘要、镜子不带工具、危机轮不进入、卡片不落库）。以上与实现常量一致：`_SLOT_WAIT_SECONDS=10.0`、8000、`tools_executed >= 4`、`": tool"` 心跳、`_city_is_allowed` 只读本轮原文和最近 3 条 user 原始行（`ctx.history` 是数据库原始行，不含「［图中］」摘要）。
- DEPLOYMENT 的环境变量表新增了两行；`.env.example` 新增 `FIONA_CLAUDE_AGENT=1`、`FIONA_CLAUDE_AGENT_TOTAL_SECONDS=240`，旧原生路径的说明改为「关闭智能体模式时」。
- 文档 diff 里没有本机绝对路径和密钥（grep `<本机路径>`、`/private/`、`/home/`、`sk-…`、`api_key=` 均为零命中）。

**C. 新测试**
- 都不依赖 git 历史（没有 subprocess 调 git），每个模块都在模块级拦截 socket 和 DNS。client 和 integration 用真实 anthropic SDK 加 `httpx2.MockTransport` 喂 SSE，覆盖 tool_use、server_tool_use + web_search_tool_result、web_fetch_tool_result、pause_turn、fallback、refusal、max_tokens。
- 打桩范围合理：runtime 桩掉 `open_agent_stream` 和 `execute_intent`，测循环本身；真实 client 由 client 测试覆盖，端到端由 integration 用真实 SDK 加真实 `_stream_image_execution`（只桩 `generate_image`）覆盖。没有发现恒真断言。`test_image_adapter_failure_keeps_successful_billing` 一开始就设 billable=True，测的是「失败不撤销已成立的计费」，用意正确。
- 规格 §6 测试点逐条对应：
  1. 开关与条件：`test_each_enable_condition`（11 组）、`test_switch_default_zero_and_warn_once`、`test_disabled_legacy_event_sequences[friend/mirror]` ✔
  2. 请求构造：`test_agent_request_has_stable_prefix_cache_tools_and_existing_effort`（3 个型号 × 3 档）、`test_agent_deduplicates_safety_and_instructions_and_reorders_final_system`、`test_legacy_request_kwargs_remain_exact_without_agent_entrypoint`（写死 kwargs）、`test_legacy_convert_messages_keeps_old_string_only_behavior` ✔
  3. 循环：`test_single_weather_round…`、`test_weather_then_image_then_answer_saves_once`、`test_tool_cap_grants_exactly_one_final_answer_request`、`test_pause_turn_preserves_assistant_and_resumes_at_most_twice`、`test_fallback_ignores_old_client_calls_and_trims_assistant_feedback`、`test_budget_exhaustion_saves_text_and_reports_timeout`、`test_busy_slot_after_card_saves_and_preserves_billing`，每轮只计一次 byok_chat 在 single 和 tool_cap 两条里断言 ✔
  4. 天气城市：`test_weather_city_only_current_or_last_three_user_originals`（正例 2 条、反例 3 条，含 system 里有城市名的情形），日志和 trace 断言见可优化 2 ✔（偏弱）
  5. 计费：`test_successful_card_billing_cannot_be_cleared_by_later_failure`、`test_real_sdk_weather_image_feedback_and_settlement`（生图成功结算、refunds 为空）、`test_real_sdk_vision_and_web_sources_are_free`、`test_second_image_is_never_executed`、`test_error_card_points_are_the_failure_reason_given_to_claude` ✔（失败工具退款只断言了 billable，见可优化 4）
  6. 落库：integration 的精确拼接、image_path，`test_image_input_skips_mode_detection_and_saves_120_character_summary` ✔
  7. 服务器端搜索：`test_search_sources_only_from_verified_result_blocks_dedup_max_five`（正文链接、127.0.0.1、javascript: 都被排除，去重，最多 5 条，标题 80 字，trace 计数）、`test_web_fetch_result_actual_sdk_block_type`、`test_server_results_before_fallback_are_still_sources` ✔
  8. 看图：integration 里把 `QWEN_CLIENT…create`、`detect_mode` 桩成 fail，并断言 base64 图片块和块的顺序 ✔
  9. pending：清除 ✔；**不写 ✘（M3）**
  10. 危机：只在判定函数层面测了 ✔（偏弱，见可优化 3）
  11. 前端：append、非 append、设置页文案 ✔；**其中 3 条在 CI 会挂（M1）**；与生图状态的交互没有覆盖（M2）
  12. 文档：`test_all_documents_explain_agent_conditions_data_billing_limits_and_caveats` × 6，加上 `.env.example` 默认值测试 ✔

**D. 任务目录**
- `docs/tasks/2026-10-10-claude-agent/02-spec.md`、`03-report.md` 里没有 `<本机路径>`、`/private/`、`/home/`、`/var/folders`、用户名、邮箱、手机号、JWT、真实 Key。命令输出里的路径已替换为 `./backend/.venv/...`、`.venv/lib/...` 这类相对形式。出现的 `sk-fiona-ci-smoke-test-not-real`、`sk-private-test-key` 是仓库里已有测试夹具的假值；`127.0.0.1` 只出现在回环测试的源码片段里。

---

# 第 2 轮复核（R1 返修）

日期：2026-10-10。只核验 05-fix-r1.md 的 R1-1 至 R1-8，新发现降级为可优化。

## 第 2 轮独立复核（R1 返修核验）

范围：仓库 `仓库根目录/`，基线 b7a27cf，改动未提交。只核对 `05-fix-r1.md` 中 R1-1 至 R1-8 是否按条文完成。全程只读：仓库零写入，没有 git 写操作，没有用浏览器，没有联网。

探针放在 `scratchpad/wo7/review/r2/`：
- `test_r2_probe.py`：25 条探针，硬拦截 socket 的 connect/connect_ex 和 create_connection/getaddrinfo/gethostbyname(_ex)。
- `clone/`：本地 `git clone --depth 1` 的副本，复制了全部已修改和未跟踪文件（不含 docs/tasks），没有 node_modules。

探针放进副本的 `backend/tests` 后运行，结果为 **25 passed**。

## 结论（通过）

R1-1 至 R1-8 全部通过。没有发现条文未完成或改错的项。

辅助验证：
- 完整工作区：`tests/test_claude_agent_*.py` 结果为 193 passed（开关为默认值和 `FIONA_CLAUDE_AGENT=1` 时都是 193 passed）；`tests/test_byok_*.py` 加 `tests/test_chat_image_tool*.py` 结果为 812 passed。
- 浅克隆副本（无 node_modules）：190 passed, 3 skipped。跳过原因是「Frontend SSR dependencies unavailable: typescript, react, react-dom/server」。
- 受保护文件 `git diff --exit-code` 退出码为 0；`backend/tests` 下已有测试只有 `conftest.py` 有差异。

## 逐项核验

### R1-1 计费在落库成功后才成立：通过

**实现**
- `claude_agent.py:350` 新增局部变量 `billable_pending`。卡片交付（:628）、生图成功（:555、:580）只累加这个局部变量。
- `save_delivered`（:357–381）只在 `finally` 中确认 `state.response_saved` 为真时，才执行 `state.billable = state.billable or billable_pending`（:370–372）。
- 落库期间被取消时，会先 `await save_task`，确认结果后再结算。
- `chat_service.py:1061、:1074`：`agent_result is not None` 时，不落库、不设置 `billable`、不发送 done。
- `chat_service.py:1103`：智能体成功拿到的图交给智能体处理，这里不删。

**会话被删或落库失败**
- `persistence_failed` 或 `ResourceNotFound` 会直接重新抛出（:652–653）。外层 `stream_claude_agent` 只拦截预算和繁忙两种错误，其余交给 `run_chat`：
  - ResourceNotFound 显示「会话已删除或不可用」（`chat_service.py:1900`）；
  - 其他错误显示「服务暂时不可用，请稍后再试」。
- 这与旧路径一致：`_save_response` 返回假时抛 `RuntimeError`，同样走通用文案。

**附件清理**：`finally`（:678–682）用 `owned_image_result` 兜底取得图片路径。只要该路径不等于实际落库的 `persisted_image_path`，就删除。

**复跑上轮 M1 探针**
- 上轮的 `probe/test_probe_agent.py` 断言的是缺陷行为，现在 3 条全部翻转为失败：
  - 断开后仍计费：`billable` 现为 False；
  - 会话删除后仍计费：现在抛 RuntimeError，`billable` 为 False；
  - 北京市被拒：现在放行。
- R2 探针输出：
  - `M1-disconnect saves [] billable False`
  - `M1-deleted billable False`，事件中没有「你的模型」
  - `img-disconnect refunds 1 saves [] exists False`：生图成功后，Claude 第 2 步期间断开，退款且附件已删除
  - `img-rnf last {'error': '会话已删除或不可用'} refunds 1 exists False`：生图成功后落库抛 ResourceNotFound
  - 正控：`ok ... saves [(…, '/uploads/r2_ok.png')] refunds [] exists True`，正常路径只扣一次，图保留
  - 正控：卡片交付后 Claude 第 2 步失败，显示「你的模型调用失败：连不上该服务…」，已交付内容落库、不退款。这是模型失败，文案正确。

**作者测试**
- `test_claude_agent_r1_integration.py::test_card_save_failure_refunds_and_uses_platform_error[False/True]`
- `::test_client_disconnect_after_card_refunds_without_save`
- `::test_image_save_failure_refunds_and_deletes_attachment`
- `test_claude_agent_r1_runtime.py:44/56/70/83/291`

### R1-2 智能体轮生图失败不让前端报错：通过

**后端**
- 适配器里的 error 只写入 `result["error"]`，不转发（:548–550）。
- 失败时发送 `{"status":"image_failed","source":"tool"}`，位置有两处：参数校验失败（:527）和执行失败（:586）。

**前端**
- `page.tsx:69` 类型增加了 `"image_failed"`。
- `:1847–1852` 收到后复位 `generatingImage`、`editingImage`，并清除 `generationStatus`。
- `:1950` 收尾检查增加条件 `!(imageGenerationFromTool && responseComplete)`。
- 面板生图的 source 不是 tool，所以不受影响。catch 段与基线逐字相同（sha256 测试 `test_existing_error_flow_remains_byte_for_byte_unchanged`）。
- 旧路由工具生图在 status 之后必定跟 `generated_image` 或 error（`chat_service.py:1003` 起），所以放宽这个条件不改变旧路由的实际行为。

**探针**：参数非法时事件序列为 `reply_model, text, status:image_failed, text:"\n\n", text, done`，没有 error。

**作者测试**（Node 实际执行 page.tsx 源码片段）
- `test_claude_agent_r1_frontend.py::test_tool_image_failure_resets_status_and_keeps_complete_reply_and_speech`：使用规定的事件序列，不抛错，状态被清除，正文和朗读都完整。
- `::test_panel_missing_image_still_errors_and_offers_retry`：面板生图缺图时仍报错，并保留重试按钮。

### R1-3 回灌保留「必须有、可为空」字段：通过

- `_block_dict`（:68–75）改用 `anthropic._utils._json.openapi_model_dump`，代码里已没有 `exclude_none`。
- 源码位置已核实（anthropic 1.12.1）：
  - `_utils/_json.py:53–57` 定义该函数，参数为 `exclude_unset=True, mode="json", by_alias=True, exclude=__api_exclude__`；
  - `_utils/_prepare.py:124` 在 BaseModel 分支调用它；
  - `_json.py:67` 的 encoder 也调用它。
- `03-report.md` R1 节写明了采用的函数和源码位置。
- 复跑上轮 `probe/probe_dump.py`：智能体输出与 SDK 输出逐项相同，`title: None`、document 的 `title: None`、`retrieved_at: None` 都还在。
- 作者测试 `test_claude_agent_r1_client.py::test_real_sdk_replay_wire_body_preserves_explicit_nullable_citations` 检查的是第二次请求实际发出的 JSON，`title`、`document_title`、`page_age` 的 null 都保留。

### R1-4 天气城市规则：通过

`_city_is_allowed`（:125–148）逐条核对：
- **候选写法**：包括原样（strip 后）、`normalize_city` 的结果，以及对两者各去掉末尾一个行政后缀的写法。
  - 后缀表在 :39，长后缀排在前面，所以「自治州」优先于「州」、「特别行政区」优先于「区」；每次只去掉一个（遇到就 `break`）。
  - 去后缀后剩余至少 2 个字才收入；候选本身也要求至少 2 个字。
- **比较范围**：本轮 `ctx.user_content`，加上 `ctx.history` 中最后 3 条 role 为 user 的记录。history 不含本轮（`chat_service.py:821` 注释），取的是原始 content，不带图片摘要。每条都取原文和 `normalize_city(原文)` 两种文本做子串比较。
- **查询写法**：用命中的候选写法（它就是原文的子串）再经 `normalize_city` 处理。
- **隐私**：不读取 `ctx.messages`、system 或记忆。

探针结果（12 组参数）：

| 主人原文 | Claude 传入 | 结果 |
|---|---|---|
| 北京明天冷吗 | 北京市 | 放行，按「北京」查 |
| 那曲市天气 | 那曲 | 放行 |
| 北京市天气 | 北京 | 放行 |
| 香港天气 | 香港特别行政区 | 放行，按「香港」查 |
| 延边天气 | 延边自治州 | 放行，按「延边」查 |
| 北京天气 | 京、市（单字） | 拒绝 |
| 天气怎么样 | 上海（城市只在 assistant 历史中） | 拒绝 |
| 那边呢（前一条 user：我在杭州） | 杭州市 | 放行 |
| 杭州在第 4 条之前 | 杭州 | 拒绝 |
| 杭州正好在第 3 条 | 杭州 | 放行 |

作者测试：`test_claude_agent_r1_runtime.py::test_weather_variants_match_only_user_originals`。

### R1-5 去掉 eager_input_streaming：通过

- `CLAUDE_CLIENT_TOOLS`（:48–54）和 `anthropic_image_tool()` 都不再带这个字段。
- `byok/client.py` 的 `open_agent_stream` 没有添加它的代码，反而在 deepcopy 后执行 `tool.pop("eager_input_streaming", None)`（:452–454）。调用方传入旧 schema 也会被去掉，调用方的列表不被修改。
- 测试检查的是实际发出的请求：`test_claude_agent_r1_client.py::test_agent_never_sends_eager_input_streaming_even_with_stale_tool_schema`。三个型号都向工具注入 `eager_input_streaming=True`，断言 SDK 实际请求的 tools 中没有这个字段。
- 对 README、CLAUDE、PLAN、ARCHITECTURE、DEPLOYMENT 执行 grep 都没有命中；docs 测试 `test_claude_agent_docs.py:63` 也有断言。

### R1-6 图片大小控制：通过

**实现**：`_claude_image_source`（:84–108）
- 阈值：`len(raw) > 3_500_000` 或长边 `> 2000` 时处理，否则原样返回原 base64，MIME 取 `Image.MIME[format]`。
- 编码：透明 PNG（有 A 通道或 `transparency`）保留 PNG，其余转为 JPEG，质量 85。
- 处理后仍超过上限时，每步缩到 85%，直到不超过为止。
- 线程：`_agent_messages:115` 通过 `asyncio.to_thread` 执行。
- 落盘文件：函数只读 `ctx.image_base64`，返回新的 dict，不改上传文件，也不改 ctx。

**探针**

| 输入 | 输出 |
|---|---|
| 2600×1300 RGB 噪声 PNG，10.1MB | JPEG 2000×1000，1.31MB，media_type 为 image/jpeg |
| 2400×2400 RGBA 噪声 PNG，23MB | PNG 886×886，2.84MB，media_type 为 image/png |
| 4000×1000 JPEG（只是尺寸超限） | JPEG 2000×500 |
| 1500×1500 PNG，6.76MB（只是字节超限） | JPEG 1500×1500，1.71MB |
| 50×40 PNG（小图） | data 与原文逐字相同，image/png |

所有输出解码后的格式都与 media_type 一致。

**作者测试**：`test_claude_agent_r1_runtime.py:156、:170`。

### R1-7 前端渲染测试在 CI 可跳过：通过

- `test_claude_agent_frontend.py:137–156` 的 `require_rendering_dependencies` 用 `node -e` 对 `typescript`、`react`、`react-dom/server` 执行 `require.resolve(paths:[frontend])`。任一个解析不到就 `pytest.skip`，并写明缺哪些包；没有 node 时同样 skip。
- 补充的源码断言（不依赖这些包）：
  - `test_claude_agent_r1_frontend.py::test_web_sources_branch_has_package_free_source_contracts`：固定标题「联网搜索」，只显示来源，不显示 points 和 url；
  - `::test_append_branch_never_assigns_legacy_card_text_or_speech_fields`：append 分支不写 `cardData`、`content`、`pendingTtsText`。
- 本轮在浅克隆中实测：190 passed, 3 skipped，原因正确。完整工作区 193 passed，0 skipped，说明这 3 条照常执行。
- CI backend 任务运行在 ubuntu-latest，自带 node，所以 R1 前端事件序列测试（Node 执行源码片段）不受影响。

### R1-8 小修：8 项全部通过

1. **不写 pending**：两组 harness 都打桩为一旦调用就失败。
   - runtime harness：`test_claude_agent_runtime.py`，harness 内 `set_pending` 调用 `pytest.fail`；
   - integration lifecycle：`test_claude_agent_integration.py:68`，同样做法。
   - 两组下的全部新测试都通过。
2. **工具失败不写 `trace["error"]`**：改为累加 `agent_tool_errors`，位置在 :526、:585、:605、:610、:626。
   - 生图适配器写入的 `trace["error"]` 在 finally 中恢复为原值（:572–576）。
   - `test_failed_image_is_feedback_and_followups_still_run` 断言 `agent_tool_errors==1`、`"error" not in trace`，且 followups 已执行。
3. **平台侧失败的文案**：get_pending、clear_pending、detect_mode、`_ensure_active_conversation`、`_agent_messages` 抛出的异常都交给 `run_chat`，显示「服务暂时不可用，请稍后再试」。
   - 全局槽的非繁忙异常和每日计数异常会设置 `platform_failure`，先落库已交付的内容，再抛出（:398–400、:405–410、:654–656）。
   - 测试：`test_pre_request_platform_failures_use_generic_error`（4 个参数），以及 `test_platform_admission_exceptions_before_claude_are_not_model_failures`。
4. **只有来源卡时**：出错路径只在 `delivered and sources and not sources_sent` 时补发来源卡（:668）；`save_delivered` 也只在 `delivered` 为真时落库。测试：`test_sources_are_not_delivered_if_error_happens_before_any_content`。
5. **多步之间的文字**：每次请求的第一段正文到来，且之前已有交付和正文时，先输出 `"\n\n"`（:443–451），同时写入 `full_response`，并计入 8000 字上限。生图适配器也有对应的 `agent_separator`。探针和集成测试的落库正文里都能看到 `"\n\n"`。
6. **槽位繁忙文案**：等待超过 10 秒仍繁忙时，抛出「自带模型通道繁忙，请稍后再试」（:396），与旧代码 `chat_service.py:187` 的文案逐字相同。
7. **`byok_chat` 计数时机**：放在拿到槽之后的 `if not daily_counted`（:405），只计一次。测试：`test_daily_chat_counter_runs_once_after_successful_slot_admission` 断言计数时 `_BYOK_ACTIVE==1`，且多步只计一次；繁忙时不计数（`test_busy_global_slot_keeps_old_message_and_does_not_count_daily_chat`）。
8. **预算耗尽与生图同时发生**：`finally` 用 `owned_image_result` 兜底取图片路径，只要不等于 `persisted_image_path` 就删除（:680–682）。测试：
   - `test_image_finishing_exactly_at_budget_never_leaves_an_orphan`
   - `test_unattached_owned_image_is_cleaned_even_when_partial_text_is_saved`

## 必须修复（仅限 R1 条文未完成或改错的）

无。

## 可优化（含新发现）

1. **R1-6 透明 PNG 的 base64 体积**：阈值按条文作用于原始字节（≤3.5MB）。探针中透明噪声 PNG 处理后为 2.84MB，base64 后约 3.79MB，仍低于 Anthropic 单图 5MB 的上限，符合条文。如果以后想按 base64 长度控制，可以把判定改为 `len(base64) ≤ 上限`。
2. **R1-2 收尾检查的条件**：新条件 `imageGenerationFromTool && responseComplete` 没有区分智能体轮和旧路由的工具生图。目前旧路由在 status 之后必定跟 `generated_image` 或 error，所以没有实际差异。如果以后旧路由出现「status 之后直接 done」的分支，这个条件也会放过它。
3. **R1-1 工具生图成功后的文案**：工具卡片交付后，Claude 第 2 步失败时显示「你的模型调用失败」，同时已交付的内容落库、不退款。这符合规格 3.6，列在这里只是作为正控记录，不需要改。
4. 上轮的探针 `probe/test_probe_agent.py` 断言的是缺陷行为，现在其中 3 条会失败，这是预期的结果。之后如需回归，请改用 `r2/test_r2_probe.py`。
