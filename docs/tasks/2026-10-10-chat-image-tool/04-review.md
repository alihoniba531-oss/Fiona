# 独立复核（R1 实现）

日期：2026-10-10。两份只读复核（Opus 5.5），基线 7ac7b57，对象为 R1 完成后的工作区改动。必须修复项已全部转入 [05-fix-r2.md](05-fix-r2.md)。探针脚本保存在作者方临时目录，未进入仓库。

---

### 后端路由与执行核心复核（WO6 聊天生图 R1）

- 复核对象：`仓库根目录/` 工作区未提交改动（基线 `7ac7b57`）
- 范围：`backend/services/chat_service.py`（`_image_tool_enabled`、`_image_tool_mode`、`run_chat` 的 image_tool_on 分支、`_run_chat_with_image_tool`、`_stream_image_execution`、`_stream_byok_reply` 的 image_tool 部分）、`backend/services/image_tool.py`（判断器）
- 规格优先级：02-spec < 05-fix-r0 < 05-fix-r1
- 取证方式：只读阅读 + AST 逐函数对比基线 + 在 scratchpad 写离线探针（`probe/test_probe_backend.py`，未放进仓库，socket 硬拦截）。新增 4 个测试文件 `275 passed`。

---

### 必须修复

以下两条都是**规格条文写窄了**（实现照 R1 字面做，没有违反条文），但都会让用户看到错误行为并扣错草莓。需要作者裁定后改规格，再改代码。

### M1. 判断器模式下，多轮补画面的回答被丢弃，还按普通文字扣 10 颗

**位置**
- `backend/services/chat_service.py:1674-1675`：只有本轮原话命中预筛，才调用判断器。
- `backend/services/chat_service.py:1541-1547`：遗留的 `generate_image` pending 不是取消短语时，直接清除。
- 旧路由建 pending 的位置：`chat_service.py:1336-1337`（`stream_intent` → `set_pending` + 「想生成什么画面？」）。

**触发 → 结果**

两条触发路径，结局相同。

路径 A（已用探针 `test_planner_error_then_answer_is_dropped` 复现）：
1. 第 1 轮，用户说「帮我画一张图」。命中预筛，调用判断器。判断器返回「不可用」，原因可能是：
   - 超时（8 秒；本机经代理时 p90 已有 5–6 秒）；
   - 或者对这种没有主体的请求返回 `{"draw": true, "prompt": ""}`。按 R1 §2.3 / 4.10，空 prompt 算「不可用」，`image_tool.py:53-55` 抛 `ValueError` → `error`。
2. 于是退回旧路由（`chat_service.py:1677-1682`）。`explicit_image_intent` 判出 `missing=["prompt"]`，`stream_intent` 写入 `generate_image` pending，并回复「想生成什么画面？可以告诉我主体、场景和风格。」
3. 第 2 轮，用户回答「一只橘猫在窗台上晒太阳」。这句话不含任何预筛词，所以不调用判断器，走 `_run_chat_with_image_tool`：
   - pending 在 `:1547` 被清除；
   - 进入 `stream_normal`，平台回复成功后 `billable=True`，扣 10 颗；
   - 没有生成任何图片。

   探针结果：`planner calls == ['帮我画一张图']`（第 2 轮没有调用判断器），`gen == []`，`pending is None`，`refunds == []`。回复模型看得到上一轮「想生成什么画面？」，很容易回一句「好的，这就给你画」。这正是 R1 想消灭的「假装画好」。

路径 B：
1. 判断器对「帮我画一张图」判为「不画」，或回复模型自己追问「想画什么呀？」。这一步没有 pending。
2. 用户回答主体（不含预筛词），判断器不会被调用。结果同上：没有图，文字回复扣 10 颗。

**规格依据**
- R1 §2.4：预筛只看本轮原话。
- R1 §3.2：遗留 pending 除取消外一律清除。
- R1 §3.1：判断器不可用时，旧路由原样执行，会新建 pending。

三条叠加就产生这个缺口。02-spec §1 的目标是「理解指代、多轮生图」；4.3 / 4.7 要求「只有实际收到结果才说已生成」。原生模式没有这个问题：用户模型能看到完整对话，下一轮可以直接调用工具。

**建议改法（需作者改 R1 §2.4）**

判断器模式下，下面任一条件成立时，也调用判断器：
- 存在 `generate_image` pending；
- 上一条 assistant 消息命中预筛，例如含「使用的描述」行、「想生成什么画面」或「画」。

判断器能看到最近 6 条，会把「想生成什么画面？」和回答连起来，判为要画。这样改，每轮最多多一次判断器调用，只发生在上一轮与生图相关时。

### M2. 判断器「要画」只清除生图 pending，搜索/路线/旅行/卡片 pending 残留，下一句话被当参数执行并扣费（相对基线回归）

**位置**
- `backend/services/chat_service.py:1684-1686`：只在 `pending.intent == "generate_image"` 时 `clear_pending`。
- 对照基线：确认生图时，`stream_intent` 在 `:1351` 无条件 `clear_pending`。原生候选路径 `:1530` 也是无条件清除。

**触发 → 结果**（已用探针 `test_planner_draw_keeps_stale_search_pending_and_next_turn_is_hijacked` 复现；对照探针 `test_legacy_confirmed_image_clears_search_pending` 证明开关关闭时会清除）
1. 用户说「帮我搜一下」，系统追问「搜啥？」，写入 `web_search` pending（TTL 10 分钟）。
2. 用户改口「画一只猫」。判断器判为要画，出图并扣 10 颗。`web_search` pending **原样保留**（探针：`pending after draw: {'intent': 'web_search', ...}`）。
3. 用户接着说「哇好可爱」。走 `_run_chat_with_image_tool`，`:1579-1582` 的 `stream_pending` 调用 `fill_param` 把这句话当作 query，执行 `web_search("哇好可爱")`。返回搜索卡片，按工具计费又扣 10 颗（探针：`executed == [('web_search', {'query': '哇好可爱'})]`，没有退款）。

`route`、`travel_plan`、`fetch_card` 的 pending 同理。天气 pending 有 `normalize_city` 兜底，不受影响。

**规格依据**
- R1 §3 第 1 条「要画」写的是「如有 `generate_image` pending，清除」，字面上只清这一种。
- 02-spec §1 第 4 条：「只换谁来决定画什么，计费……照旧」。
- 基线行为是「确认生图就清除全部 pending」（`stream_intent`）。

现状等于新增了一条错误计费路径。

**建议改法**

「要画」分支改为无条件 `await asyncio.to_thread(clear_pending, ctx.state_key)`，与基线 `stream_intent` 和原生候选路径一致。如果作者希望保留天气 pending，至少要清除天气以外的所有 pending。这一处需要作者确认后同步修订 R1 §3 第 1 条。

---

### 可优化

1. **判断器「要画」没有任何规则兜底**（`chat_service.py:1683-1699`）
   - 基线有两道兜底：`recognize_intent_with_fallback` 会用 `image_generation_discussion` 否决「别…/怎么…/生图模型价格/写提示词」类句子；pending 状态下还有取消正则。
   - 判断器模式下，「不画了」「别画了」也命中预筛（含「画」）。万一判断器误判，就直接扣 10 颗出图。
   - 建议：取消正则在判断器之前先查（有 `generate_image` pending 时），这样还能省掉 1–5 秒；`image_generation_discussion(message)` 为真时把 draw 降为 no。R1 的评测是 33/33，风险低，算防御性加固。

2. **本轮原话只保留开头 600 字**（`image_tool.py:33`）
   - 用户贴一段超过 600 字的英文提示词，末尾写「用 Seedream 画出来」时，判断器看不到末尾的指令，大概率判为不画，于是走文字回复并扣 10 颗。
   - 规格只写了「截断到 600 字」，没规定取头还是取尾。
   - 建议：本轮原话改为首尾各 300 字，中间用「……」连接，与危机复核的做法一致。历史消息维持现状。

3. **超时后线程仍在跑**（`image_tool.py:36, 63-66`）
   - `wait_for` 8 秒到点后，`to_thread` 里的 SDK 请求继续占用默认线程池的一个 worker（`main.py` 默认 32 个），直到 httpx 的分阶段超时结束（connect / read 各 8 秒）。结果被丢弃，没有共享状态，**不会影响后续轮次的正确性**，只是占用容量。
   - 建议：SDK 超时用 `httpx.Timeout(总剩余时间, connect=3)`；或者像 `crisis_model` 那样改用 `AsyncOpenAI`，让取消真正生效。

4. **判断器的描述没有做账号名后置过滤**
   - 平台人设系统提示里有账号名，平台回复可能带出账号名，进入历史后再被判断器读到。描述会发给火山引擎并落库，目前只靠提示词约束。
   - 建议：`ctx.user` 出现在 prompt 里时，替换掉或判为不可用。

5. **非法调用通知在没有前导文字时，落库正文以 `\n\n` 开头**（`chat_service.py:274-275`）
   - 只影响显示（刷新后气泡顶部多出空行）。
   - 建议：没有前导文字时去掉开头换行。规格原文写的是「前导（如有）加 `\n\n（…）`」，两种读法都说得通。

6. **判断器「要画」路径里 `trace.image_source` 写三遍**
   - `chat_service.py:1688-1699` 每个事件后，以及 finally 里，都把 `image_source` 覆盖回 `planner`。结果正确但写法绕。
   - 建议：给 `_stream_image_execution` 加一个 `image_source` 参数，直接传入。

---

### 已核实无问题的要点

- **开关与模式**
  - `_image_tool_enabled` 每次调用读取环境变量，只有字面 `0` 关闭，非法值只告警一次。条件包括 chat 模式、无本轮图片、`crisis_level is None`、非 `byok_unreserved`、`byok_error is None`，已删除白名单。
  - `_image_tool_mode` 只对 anthropic 和 deepseek 精确的 `deepseek-v4-pro` / `deepseek-flash` 返回 native。
  - `_stream_byok_reply` 内部再按 `not mirror and crisis_level is None and mode == native` 防守一次，直接调用这个函数也不会给判断器模式的厂商下发工具。
- **平台 `stream_normal`**
  - 用 AST 抽出函数逐字比对，与 `7ac7b57` **完全相同**（700 tokens，请求中没有 `tools`）。
  - `stream_mirror`、`stream_intent`、`stream_pending`、`_normal_followups`、`recognize_intent_with_fallback` 同样与基线逐字相同。
- **判断器不可用 → 旧路由**
  - `run_chat` 自「# 正则只提名候选。」起到 `except` 之前，与基线逐行无 diff。
  - 判断器分支没有副作用：不读写 pending，不调用 `detect_mode`。只是多了 `image_planner*` 三个 trace 字段（类型名和耗时）。
- **危机**
  - high 在判断器之前就返回；possible（含信息语境）使 `_image_tool_enabled` 为假，判断器和工具都不会进入，走基线路由。R0 关于 pending 的规则由基线代码原样承担。
- **「要画」计费**
  - 路由层整轮只预扣一次 10 颗。执行核心落库成功后才设 `billable=True`；失败、忙锁冲突、两个模型都未配置、断开，都在 `run_chat` 的 finally 里退款。
  - BYOK 用户在「要画」路径不进入 `_byok_slot`，不计 `byok_chat`，不发 `reply_model`。
  - 余额不足的 BYOK 用户（`byok_unreserved`）被开关排除，走旧守卫。
- **并发与清理**
  - `_IMAGE_GENERATION_USERS` 忙锁对两种模式都生效。
  - 断开时由 `aclosing` 链关闭执行核心，在 finally 里删除未落库图片并释放忙锁。既有测试覆盖了判断器「要画」时断开的情形。
- **trace / 日志**
  - 探针确认：判断器「要画」整轮 trace 中不出现原话和描述。
  - `plan_image` 的日志只记 `exception_type` 和 `elapsed_ms`。
  - `trace.model` 在判断器模式下为 None，`analyze.py` 会显示为 `(none)`，不会出错。
- **`plan_image` 输入**
  - 只保留 user / assistant 消息，取最近 5 条加本轮，共 6 条；按时间顺序，前缀为「主人：」「你：」，每条最多 600 字，最后一条是本轮原话。探针确认 6 行。
  - `ctx.history` 在用户消息落库之前读取，不含本轮。
- **`plan_image` 解析与客户端**
  - `draw` 必须严格为 bool；`prompt` 去掉首尾空白后为空或超过 1500 字时判为不可用；`model` / `aspect_ratio` 不在枚举内的值被丢弃；拒绝 NaN 常量。
  - history 的 content 不是 str 时抛 TypeError，判为不可用并退回旧路由。DB 的 `content` 列是 `TEXT NOT NULL`，实际不会发生。
  - `CancelledError` 不会被吞掉。
  - `QWEN_CLIENT.with_options`：openai 2.37.0 的 `copy()` 复用同一个 `SyncHttpxClientWrapper`，原客户端仍持有引用，派生对象被回收也不会关闭共享连接，可以安全共享。
- **原生模式（BYOK）**
  - 只在流结束、`_byok_slot` 退出后才读取 `tool_call`，再在 BYOK 的 try 外执行生图，生图异常不会被归为「你的模型调用失败」。
  - 只调工具、没有文字时不抛 `EmptyReplyError`，并补发一次 `reply_model`。
  - refusal、截断或坏 JSON 时走统一的非法调用通知，落库并退款。
  - 镜子模式不下发工具；候选句确认后先按 friend 模式设置 `sys_prompt_final`，再进入带工具的回复。
- **执行核心**
  - 模型选择优先级为：参数 → Seedream → 发请求前降级并说明；请求发出后失败不换厂商重试。
  - 比例：参数优先，其次描述原文，最后 1:1。
  - 前导文字不会被覆盖，落库只写一行。
  - 事件顺序与 `speak:false` 符合 4.3 第 5 条。
  - 错误文案按类别映射；面板路径的文案和 trace 都不变。

---

### 复核：byok/client.py + 前端 + 文档 + 新测试 + 任务目录（基线 7ac7b57，工作区未提交改动）

复核方式：只读阅读 diff 与相关源码；离线跑了 `tests/test_byok_image_tool.py tests/test_image_planner.py tests/test_chat_image_tool_frontend.py`（106 passed）；另在 scratchpad 写了一个离线探针 `probe_valueerror.py`，用真实 anthropic 1.12.1 SDK + httpx2 MockTransport 复现 F1。没有改仓库文件，没有联网。

### 必须修复

### F1. Claude 原生模式下，`except ValueError` 会把与工具无关的上游协议错误吞成「工具参数不合法」
- **位置**：`backend/byok/client.py:292-301`（`ReplyStream._consume` 的 `except ValueError` 分支），下游是 `backend/services/chat_service.py:387`、`:417`、`:272-280`（`_stream_invalid_image_tool`）。
- **触发 → 结果**：
  - 条件：原生模式下发了工具（即 BYOK Claude 的每一轮 friend 回复，不只是生图句）。上游 SSE 中途出现一条坏 JSON 的 data 行（SDK 中 `sse.json()` 抛 `json.JSONDecodeError`），或出现非法 UTF-8（`raw_line.decode` 抛 `UnicodeDecodeError`）。两者都是 `ValueError` 的子类，消息里根本没有 tool_use 块。
  - 实际结果：异常被吞掉，`tool_call=None`、`tool_call_invalid=True`。`_stream_byok_reply` 随后走 `_stream_invalid_image_tool`：把已经流出的半截文字加上「（这次没能生成图片，请再描述一次想画的画面。）」**落库**，再发 `done`。用户根本没要求画图，却看到「没能生成图片」，半截回复也被永久保存。
  - 基线和工具关闭时：异常照常抛出，归类为「你的模型调用失败」，不落库。
  - 离线探针实测（真实 SDK）：工具开启时得到 `('no-exception', '今天聊点别的，', None, True)`；工具关闭时得到 `('raised', 'JSONDecodeError', '今天聊点别的，')`。
- **规格依据**：02-spec 4.5 只要求把「**工具参数 JSON 解析失败**导致 SDK 抛出的 `ValueError`」按参数不合法处理。其他错误应保持原有分类（3.2/3.3：新参数不得改变现有行为）。
- **建议改法**：只认 SDK 包装的那一种异常。可以判 `type(exc) is ValueError and str(exc).startswith("Unable to parse tool parameter JSON")`（anthropic `lib/streaming/_messages.py:489`、`_beta_messages.py:519` 的固定前缀）；或者额外检查 `resources.stream.current_message_snapshot.content` 的最后一块确为 `tool_use`。`JSONDecodeError`、`UnicodeDecodeError` 及其他 `ValueError` 一律原样 `raise`，走原有分类。
  - 补一条负例测试：工具开启、SSE 坏 JSON、没有 tool_use 块时，必须抛出异常，而不是返回 invalid。现有 `test_claude_sdk_value_error_without_tool_preserves_existing_error` 只覆盖了工具关闭的情况。

### F2. 设置页隐私说明对判断器模式用户写错了：说「由你的模型决定何时生图」，也没有披露把最近 6 条对话发给 DashScope
- **位置**：`frontend/components/ChatModelSection.tsx:361-362`（静态文案，不区分厂商与型号）。新测试 `backend/tests/test_chat_image_tool_frontend.py:122-128` 把这句话钉死了。
- **触发 → 结果**：用户在设置页选 Kimi、智谱、自定义地址、通义（BYOK dashscope 任意型号），或选 DeepSeek 但型号不是 `deepseek-v4-pro`/`deepseek-flash`。页面写的是「启用后，由你的模型决定何时生图、撰写画面描述」。按 R1 的实现（`chat_service._image_tool_mode` 返回 `planner`），这些用户实际上：
  - 由平台判断器 `qwen3.8-flash` 决定画不画、撰写描述；
  - 判断器读取最近 6 条对话（每条最多 600 字），发送给阿里云 DashScope。

  页面对 6 家里的 5 家写的是错误的数据流，也和 README / CLAUDE.md / DEPLOYMENT 的 BYOK 隐私段（已写明「其他 BYOK 使用平台判断器读取最近 6 条对话」）互相矛盾。
- **规格依据**：05-fix-r1 第 1 节规定了两种模式的分工；4.9 要求隐私说明写明判断器读取最近 6 条对话并发给 DashScope。
  - 注意：R1 第 4 节写了「4.8 前端：不变」，实现照抄了 02-spec 4.8.5 的原句，字面上不算违规。但那句话是在「白名单模型全部原生」的前提下写的，R1 之后它与事实不符。这属于规格缺口，需要主控拍板文案；作为对外隐私披露，不应保留错误表述。
- **建议改法**：按当前选择的 `provider.id` 和 `model` 分两段渲染：
  - 原生（`anthropic`，或 `deepseek` 且型号精确为两个之一）：保留现句。
  - 其他：「启用后，是否生图及画面描述由平台生图判断器（qwen3.8-flash）决定：预筛命中时，会把最近 6 条对话（每条最多 600 字）发送给阿里云 DashScope；生图仍由平台执行并扣草莓……」
  - 同步改 `test_chat_image_tool_frontend.py` 的断言（新测试文件，允许改）。

### F3. `docs/ARCHITECTURE.md` 第 91 行仍是 R1 之前的描述，并且整段删掉了旧路由的实现说明
- **位置**：`docs/ARCHITECTURE.md:91`。
- **触发 → 结果**：
  1. 该段写「工具开启时，候选确认走带工具的 friend 回复；……工具关闭或不符合下发条件时原自然语言候选 / 意图 / pending 路径保持不变」。按 R1 实现，判断器模式（平台两槽，以及 Kimi/智谱/custom/dashscope 等）**跳过**候选块，不走带工具的回复；「判为不画」时也不是原路径。这与下文第 93-105 行的两模式说明互相矛盾。
  2. 基线第 91 行原有一整段旧路由说明被删除，没有替代内容，全文已搜不到：
     - `mode=image` 与比例；
     - 候选经意图模型确认、增加的延迟；
     - 讨论句兜底；
     - 画面主体为空时先追问、不扣费；
     - 描述用 `ctx.message.strip()`；
     - `GET /image-models` 的鉴权与返回字段；
     - SSE 顺序（status → 心跳 → generated_image → text → done）；
     - possible 轮先送资源再报错。

     旧路由在开关关闭、判断器不可用、possible 信息语境下仍在用，面板路径也依赖这些说明。
- **规格依据**：05-fix-r1 4.9 要求「改写为两种模式」；02-spec 4.9 要求同步更新相关位置，而不是删除仍有效的实现说明；CLAUDE.md 工作约定要求代码改变时同步更新架构文档。
- **建议改法**：
  - 恢复基线第 91 行的旧路由说明，并注明它适用于「开关关闭 / 判断器不可用 / 面板」；
  - 把新增那句改成「原生模式候选确认后走带工具的 friend 回复；判断器模式先由判断器裁决，判为不画时跳过候选块，意图识别的 generate_image 视为无意图」。

### 可优化

1. **弱断言与空集断言**（不一定会漏掉回归，但给不出证据）：
   - `backend/tests/test_chat_image_tool.py:739-740`：`len(calls) <= 1`、`done <= 1`。`outcome='success'`（平台）时没有断言真的生成了图、落库正文含「图片已生成。」。如果判断器路径坏掉、退回文字回复，`saves==1`、`refunds==[]` 依然成立，用例照样通过。
   - `test_chat_image_tool.py:618`：`all('tools' not in request ...)` 没有先断言 `requests` 非空，路由没走到模型时空集会让它恒真。
   - `test_chat_image_tool.py:371-382`：直接调用已恢复为基线的 `stream_normal`（里面已经没有任何工具代码），所以 `not calls` 恒真。危机资源条数用 `<= 1`，0 条也能通过。
   - `test_chat_image_tool.py:880`：`done <= 1`。
2. **请求体「与基线一致」的新测试是自比较**：`test_byok_image_tool.py:230`、`:253` 比较的是新代码的「不传 tools」和「tools=None」两种调用，两者走同一条分支，等于自己跟自己比。真正的基线字节保证仍靠既有的 `test_byok_effort.py`。可以改成与 `git show 7ac7b57` 的请求体比对，或删掉「bytes unchanged」这个措辞。
3. **可能偶发误报**：`test_image_planner.py:141` 的 `assert content not in caplog.text` 在参数 `content="3"` 时，只要日志里的 `elapsed_ms` 含数字 3（例如 3、13、30 毫秒，CI 负载高时可能出现）就会失败。可改为断言日志不含 JSON 原文的特征串，或对这个参数跳过该断言。
4. **模块耦合**：`byok/client.py:17-22` 现在 import `services.image_tool`，后者在模块级 `from llm import QWEN_CLIENT`。结果是 BYOK 适配层（含测试连接路由）的导入会顺带初始化平台 DashScope 客户端。可以把纯工具定义和累积器（不依赖 llm）拆出来，判断器单独放一个模块。目前没有循环导入，也没有功能问题。

### 已核实无问题的要点

**A. `byok/client.py`**
- 不带工具时，`_open` 的 kwargs 构造与基线完全相同。`tools` 只有在 `== "generate_image" and not mirror` 时才加入。`ReplyStream(image_tool=False)` 的行为等价于基线：`except ValueError` 分支在非工具时先判 `timed_out` 再原样 `raise`，与基线 `except Exception` 的处理一致。`test_connection` 不受影响。
- Claude：`tools=[anthropic 格式]` 与 `tool_choice={"type":"auto","disable_parallel_tool_use":True}` 同 `betas`/`fallbacks`/`output_config` 并存。工具调用只从 `get_final_message()` 取，要求 `stop_reason=="tool_use"`；`refusal`/`max_tokens`/`length`/`content_filter` 判为 invalid；只取最后一个 fallback 块之后、第一个 `generate_image`。`get_final_message` 返回后会再检查一次 `timed_out`/`closed`，中断时不会暴露工具调用。
- OpenAI 兼容：按 index 分组；id、name 取第一个非空值，只拼接 arguments；只有 `finish=="tool_calls"` 才算调用；`json.loads` 严格解析（NaN 一类常量也拒绝）。截断（超过 4000 字）时算 invalid。`extra_body`（关闭思考）保留。坏 JSON 的 SSE 在 OpenAI 路径照常抛出，没有被吞。
- 中断语义：没有新增跨线程的 close。中断线程仍只做 shutdown；`finally: resources.close()` 仍由属主线程执行。`ValueError` 分支里 closed/timed_out 时改抛 `ReplyInterruptedError`/`ByokTimeoutError`，都带 `from None`，SDK 异常消息里的 JSON（即描述）不会进入日志或分类。
- 只有原生模式会把 `tools` 传进 `_open`（`chat_service._stream_byok_reply` 由 `_image_tool_mode=="native"` 把关）；dashscope、moonshot、zhipu、custom 及 deepseek 其他型号都不传。

**B. 前端**
- `speak:false` 的 text 会拼进正文，但不进 `ttsBuf`，不触发 `flushSentences`；收尾 flush 的也只是 `ttsBuf`。没有其他朗读入口会读取正文（`pendingTtsText` 只用于卡片）。
- 只要本轮收到过 `status.source==="tool"`，失败时就不附 `imageGenerationRetry`。工具路径在发出 status 之前就失败的情况（两模型都未配置、忙锁）下 `generatingImage` 仍为 false，同样不显示重试。面板路径不变。
- `ChatBubble` 的新条件：有 content 就显示；只有在 `isTyping && !generationStatus` 时才显示打字占位。面板模式生成期间 content 为空，仍然隐藏，表现不变。
- `ChatStreamEvent` 已补 `speak?`、`source?`。

**C. 文档**
- 两种模式的适用范围、判断器参数（qwen3.8-flash、最近 6 条、每条最多 600 字、预筛、8 秒总超时、非流式 JSON、600 tokens、在线程中执行、不重试）、不可用时退回旧路由、要画时不调用回复模型、不计 `byok_chat`、trace 只记 `image_planner*` 与 `image_source=planner`、计费、时限口径，都与代码一致。
- `.env.example` 中 `SEEDREAM_IMAGE_MODEL` 的默认值与 `tools/image_generation.py:98` 一致，`ARK_API_KEY` 留空。
- 六个文档的新增内容里没有本机绝对路径或密钥。

**D. 新测试**
- 判断器单测（`test_image_planner.py`）用 `with_options` 打桩但执行真实的 `_plan_image_once`，对请求参数、6 条与 600 字截断、各类非法返回、超时、线程执行、日志不泄露内容都有实质断言。
- `test_stream_normal_is_restored_to_baseline` 用 `git show 7ac7b57` 做真实比对。
- R1 路由测试只打桩 `plan_image` 与外部调用，路由本身是真实代码；`'你好'` 这类预筛未命中的情况在 `test_disallowed_byok_route_keeps_old_request` 中由真实预筛覆盖（判断器桩返回 draw，若误命中会生图，断言 `not calls` 能抓到）。
- HTTP 级测试使用真实隔离的 SQLite 余额。

**E. 任务目录**
- `image_planner_stub.py` 与 `acceptance/`、`03-report.md` 里没有本机绝对路径、用户名、邮箱、JWT 或真实 Key。traceback 里的路径已脱敏为 `<python-stdlib>/` 或相对的 `.venv/...`。
- 唯一出现的 `sk-fiona-ci-smoke-test-not-real` 是已提交的 conftest 里本来就有的 CI 占位值。

---

# 第 2 轮复核（R2 返修）

日期：2026-10-10。只核验 05-fix-r2.md 的 R2-1 至 R2-9，新发现降级为可优化。

## 第 2 轮独立复核：WO6 聊天生图 R2 返修（R2-1 至 R2-9）

- 对象：`Fiona/` 工作区未提交改动，基线 `7ac7b57`；返修单 `docs/tasks/2026-10-10-chat-image-tool/05-fix-r2.md`
- 方式：只读阅读与 diff；离线跑本任务 7 个测试文件；在 `scratchpad/wo6/review/r2/` 写离线探针（conftest 在导入期硬拦截 AF_INET/AF_INET6 的 connect/connect_ex、getaddrinfo、create_connection，首条用例先证明拦截生效）；在 scratchpad 的源码副本里做「回退 R2 改动」的正控变异。仓库文件、git 状态都没有改动（复核前后 `git status --short` 都是 24 项）。
- 本轮规则：只核验 R2 条文，新发现一律放在「可优化」。

## 结论（通过 / 不通过）

**通过。** R2-1 至 R2-9 都按条文完成，没有必须修复项。

- 本任务 7 个测试文件：`358 passed`。
- 探针：`21 passed`。
- 正控变异：14 个，全部被对应测试抓到。其中 1 个首次变异写得不完整，曾存活，补全后被抓到，见 R2-8。

上一轮 M1、M2 两个场景已按本轮代码复跑，缺陷不再出现。

## 逐项核验（R2-1 … R2-9）

### R2-1 判断器调用时机：通过

**实现位置**

- 常量：`backend/services/chat_service.py:80-81`。
  - `IMAGE_PENDING_CANCEL_PATTERN` 与基线 `stream_pending` / 旧路由里的字面正则逐字相同。
  - `IMAGE_PLANNER_FOLLOWUP_PATTERN` 为 `"使用的描述|想生成什么画面|画|提示词|prompt"`，与条文逐字相同。
- 判断器分支：`chat_service.py:1675-1689`。
  - 先读 pending。
  - `image_pending_cancelled` 为真时，`planned` 保持 None，交给 `_run_chat_with_image_tool`。该函数在 `:1544-1549` 用同一常量走 `stream_pending` 取消。
  - 否则下面三条任一成立就调用判断器：
    - 预筛或 `explicit_image_intent`；
    - 存在 `generate_image` pending；
    - `ctx.history` 里最后一条 assistant 匹配 `IMAGE_PLANNER_FOLLOWUP_PATTERN`（`re.IGNORECASE`）。
- 旧路由 `run_chat` 的「# 正则只提名候选」段仍保留原字面正则，没有被改动，符合「旧路由原样」。
- 判断器提示词与预筛正则跟 05-fix-r1.md 原文逐字一致（AST 取值后比对：两者都为 True）。

**测试**（`backend/tests/test_chat_image_tool.py`）

| 测试 | 覆盖场景 |
| --- | --- |
| `test_r2_image_pending_answer_calls_planner_without_current_prescreen[draw/no]`（:965） | 有 pending、本轮未命中预筛时调用判断器：判画则出图并清 pending；判不画则清 pending 并走普通回复 |
| `test_r2_pending_cancel_does_not_call_planner`（:997，7 种取消短语） | 取消短语不调用判断器，返回「好，已取消。」 |
| `test_r2_last_assistant_image_followup_calls_planner`（:1022） | 上一条 assistant 含「使用的描述 / 想生成什么画面 / 画 / 提示词」或大写 PROMPT 时调用判断器 |
| `test_r2_unrelated_last_assistant_does_not_call_planner`（:1043） | 上一条 assistant 与生图无关时不调用；含「较早一条 assistant 有描述行、最后一条无关」和「最后是 user 消息含『提示词』」两种情况 |
| `test_r2_cancel_and_followup_patterns_are_exact_and_shared`（:1110） | 两个常量逐字正确，且两处共用 |

**M1 复跑探针**（`r2/test_probe_r2.py`）

`test_M1_rerun_planner_called_on_answer_and_draws[with_ask/empty]`：第 1 轮判断器返回 TimeoutError，旧路由建立 `generate_image` pending，并追问「想生成什么画面？」。第 2 轮用户答「一只橘猫在窗台上晒太阳」，结果：

```
planner calls: ['帮我画一张图', '一只橘猫在窗台上晒太阳']
gen: [('一只橘猫在窗台上晒太阳', '1:1', {'model_id': 'seedream-5.0-flash'})]
pending: None   refund: []   normal calls: 0
```

- 上一轮探针里第 2 轮判断器未被调用；现在被调用了。
- history 为空时，单靠 pending 也能触发。

**两个补充分支**

- `test_M1_rerun_planner_unavailable_again_legacy_pending_generates`：第 2 轮判断器仍不可用时，旧路由用 pending 补参并原样生图：`gen=[('一只橘猫在窗台上晒太阳','1:1',{})]`，pending 清空，不退款。
- `test_M1_rerun_planner_says_no_clears_pending_normal_reply`：判为不画时清 pending、走普通回复，`trace.intent` 为 None。

**取消短语探针**

`test_cancel_with_pending_skips_planner_even_when_last_assistant_matches`：存在 pending，且上一条 assistant 含「想生成什么画面」时，「不画了」不调用判断器。输出 `[{'text':'好，已取消。'},{'done':True}]`，退款 10 颗，与原取消逻辑一致。

**正控**

在副本里分别删掉 pending 条件、上一条回复条件、取消守卫，对应测试全部失败（KILLED）。

### R2-2 「要画」时无条件 clear_pending：通过

**实现**

`chat_service.py:1697-1698`：`elif planned and planned["status"] == "draw":` 之后第一句就是 `await asyncio.to_thread(clear_pending, ctx.state_key)`，然后执行生图。已没有 `pending.intent == "generate_image"` 这个条件。

**测试**

`test_r2_planner_draw_clears_search_pending_before_next_turn`（:1056）：
- 先留一个 `web_search` pending；
- 出图后断言 pending 已清空；
- 下一句「哇好可爱」不进入 `stream_pending`（`searches == []`）。

**M2 复跑探针**

`test_M2_rerun_draw_clears_search_pending_next_turn_not_searched[empty/with_saved_image]`：

```
pending after draw: None
turn2 events: [{'text': '好的，这就给你画一只橘猫～'}, {'done': True}]
executed: []
```

- 上一轮复现的结果是 `executed == [('web_search', {'query': '哇好可爱'})]`，现在不再执行搜索。
- 第 2 轮 history 带上「图片已生成…使用的描述」时，判断器会被调用一次，判为不画，随后普通回复。

另有 `test_M2_draw_clears_every_pending_kind[route/travel_plan/fetch_card/weather]`：四种 pending 在「要画」后都被清除。

**正控**

把清除改回「仅 generate_image 时清」，上述测试失败（KILLED）。

### R2-3 只把 SDK 工具参数 JSON 失败当作非法调用：通过

**实现**

`backend/byok/client.py:291-305`：
- `except ValueError` 先判 `timed_out`（抛 ByokTimeoutError），再判 `closed`（抛 ReplyInterruptedError），两者都带 `from None`。
- 只有同时满足以下条件，才置 `tool_call_invalid=True`：
  - `self.image_tool and self.anthropic_stream`；
  - `type(exc) is ValueError`；
  - `str(exc).startswith("Unable to parse tool parameter JSON")`。
- 其他情况一律原样 `raise`。
- 已核对：本地 anthropic 1.12.1 的 `lib/streaming/_messages.py:490` 与 `_beta_messages.py:520` 都使用这个前缀，异常消息尾部带 `JSON: {...}`。实现中没有任何地方记录该消息。

**测试**（`backend/tests/test_byok_image_tool.py`）

| 测试 | 内容 |
| --- | --- |
| `test_actual_claude_sdk_bad_sse_without_tool_use_raises_in_tool_mode[JSONDecodeError/UnicodeDecodeError]`（:269） | 真实 SDK 加 httpx2 MockTransport，工具开启：抛出异常，`tool_call_invalid is False`，请求确实带了 tools，客户端已关闭 |
| `test_claude_tool_mode_preserves_unrelated_value_error_identity`（:256） | 带前缀的 `JSONDecodeError` 子类也原样抛出，且为同一对象 |
| `test_claude_sdk_tool_parameter_json_value_error_is_invalid_without_leak`（:233） | 正例：结果为 invalid，日志不含 JSON 原文和标记串 |

**探针**

- 复跑 `probe_valueerror.py` 场景（`test_R23_rerun_probe_valueerror_bad_sse_json`）：工具开启和关闭都得到 `('raised','JSONDecodeError','今天聊点别的，')`。上一轮工具开启时得到的是 `('no-exception', …, None, True)`。
- 新增真实 SDK 正例（`test_R23_real_sdk_bad_tool_json_is_invalid_and_not_logged`）：上游发出 tool_use 块，`input_json_delta` 是非法 JSON。结果为 `('no-exception','我来画。',None,True)`；`caplog` 和 stdout 都不含标记串。

**正控**

- 去掉 `type(exc) is ValueError`：子类用例失败（KILLED）。
- 去掉整个前缀判断，回到 R1 行为：真实 SDK 坏 SSE 用例失败（KILLED）。

**关于 closed 检查提前：判定为可优化，不是必须修复**

现象：`closed` 检查被提到工具判断之前。工具关闭时，「closed 状态下抛出的 ValueError」由原样抛出变为 ReplyInterruptedError。

- **与基线确有差异**：探针 `test_R23_closed_valueerror_tool_off_current_vs_baseline` 用 `git show 7ac7b57` 加载基线 client。两种流（anthropic、OpenAI）下，当前抛 `ReplyInterruptedError`，基线抛 `ValueError`。
- **用户可见文案完全相同**：`byok/errors.py` 的 `error_category` 对两者都返回 `"other"`，`error_message` 都是「你的模型调用失败：调用失败。本条没有改用平台模型。」（探针实测）。`_stream_byok_reply` 的 `except Exception`（`chat_service.py:409-416`）只用 category 和 message 生成 SSE，测试连接路由（`routers/chat_model.py:134-136`）同样只用 `error_message`。
- **实际只在取消路径出现**：不超时而 `closed=True`，只有两种来源：
  - `_byok_call` 收到 CancelledError 后调用 `control.abort()`（`chat_service.py:214-217`）；
  - 生成器收尾时的 finally（`:349-351`、`:380-381`）。

  这两种情况下，外层抛出的都是 CancelledError 或 GeneratorExit，worker 的异常只被取回、不再上抛。探针 `test_R23_cancel_path_hides_worker_exception_type` 实测外层得到 CancelledError。所以用户收不到任何错误事件，`trace["error"]` 也不会写入。唯一的理论差别是 trace 里的异常类名，而这在现有调用路径上无法触发。
- **符合条文**：R2-3 原文写的是「其他异常一律走原有分类：先按 timed_out / closed 判断，否则原样抛出」，实现照此执行。而且 SDK 在 socket 被 shutdown 后读流，可能抛 `ValueError("I/O operation on closed file")`，把它归为中断在语义上更准确。

结论：对用户没有影响，列入可优化第 1 条。

### R2-4 SSE 响应头加 no-transform：通过

**实现**

`backend/routers/chat.py:26` 定义：

```python
CHAT_STREAM_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
```

三处使用：
- `:66` `_text_stream`；
- `:225` `_ReservedChatResponse`；
- `:228` 普通 `StreamingResponse`。

该文件相对基线的 diff 只有这些行，原局部 `headers` 变量已删除。`frontend/next.config.ts` 不在改动列表中，其他文件没有改动响应头。

**文档**

`docs/DEPLOYMENT.md:50` 的 `FIONA_BACKEND_ORIGIN` 段已补上条文那句，逐字一致。

**测试是否真的走到这些路径**（`backend/tests/test_chat_image_tool_headers.py`）

- `test_chat_reply_stream_headers_prevent_proxy_compression[False/True]`（:46）：用现有 `client` 夹具，回复流打桩。`reserved=True` 时断言 `reply_calls[0]["reserved"] is True`，只有 `_ReservedChatResponse` 分支会这样调用 `run_chat`。
- `test_chat_text_stream_error_headers_prevent_proxy_compression`（:99）：possible 加空消息，经 `_crisis_error_stream` 进入 `_text_stream`。

**正控**（`r2/mutate.py`、`r2/mutate3.py`）分别回退以下四处，每次都只有对应用例失败：
- 常量；
- `_text_stream` 的 headers；
- Reserved 那一处；
- 普通那一处。

三条路径各自都被独立覆盖。

### R2-5 设置页隐私文案：通过

- 脚本从返修单代码块取出原文，在 `frontend/components/ChatModelSection.tsx:362` 中以 `<p>{原文}</p>` 的形式命中 1 次，逐字一致。这是静态段落，没有按厂商分支渲染。
- 与 R1 快照对比：只替换了 R1 那一段，其他段落未动。
- `test_chat_image_tool_frontend.py:146`：断言 7 个短语，外加整段 `<p>` 原文。

### R2-6 本轮原话截断：通过

**实现**

`backend/services/image_tool.py:33`：

```python
current = message if len(message) <= 1500 else message[:1000] + "……" + message[-500:]
```

历史消息仍是 `row["content"][:600]`。与 R1 快照的 diff 只有这两行。

**测试**（`test_image_planner.py`）

- `:110` 覆盖 600 / 601 / 1499 / 1500，全文保留；
- `:119` 覆盖 1501 / 2400，精确等于前 1000 + `……` + 后 500，末尾「用 Seedream 画出来」保留；
- `:95` 历史 800 字截到 600，本轮 900 字完整保留。

正控：改回 `message[:600]`，两条用例都失败（KILLED）。

**文档**

六份文件都已改为「历史每条最多 600 字，本轮原话最多 1500 字（超长时保留首尾）」，没有残留旧表述（grep `最多 600` 并排除新表述和「镜子 600」后为零命中）：
- `CLAUDE.md:20,78`
- `PLAN.md:13,182`
- `README.md:129,155`
- `docs/ARCHITECTURE.md:99,167`
- `docs/DEPLOYMENT.md:163,191`
- `backend/.env.example:26`

R2-1 新增的调用时机（「上一条回复与生图相关 / 存在待补充的生图请求 / 取消短语不调用判断器」）已写进上述 6 处「何时调用判断器」的段落，由 `test_r2_docs_describe_planner_followup_triggers` 断言。

### R2-7 恢复 ARCHITECTURE 旧路由说明：通过

- 脚本用 `git show 7ac7b57:docs/ARCHITECTURE.md` 取出以「图片生成通过同一个 `POST /chat` 接入：」开头的原段落（1327 字符）。
- 当前文档 `docs/ARCHITECTURE.md:91` 存在一个独立段落，内容正好是「适用于开关关闭、判断器不可用、possible 轮与面板路径。」加上该原段落，逐字一致。
- 条文列出的 8 个要点逐一检索全部命中：
  - `mode=image`
  - 增加的延迟
  - 讨论句兜底
  - 先追问、不扣费
  - `ctx.message.strip()`
  - `GET /image-models`
  - SSE 顺序
  - possible 轮先送资源再报错
- R1 旧句「工具开启时，候选确认走带工具的 friend 回复」已删除；新句在 `:93`，与条文逐字一致。
- `test_r2_architecture_restores_complete_legacy_image_route` 也用 git 基线逐字比对。

### R2-8 小修：通过

1. **非法调用通知**：`chat_service.py:276` 为 `("\n\n" if state.full_response else "") + "（这次没能…）"`，SSE 和落库用的是同一个 `text`。
   - 测试：`test_r2_invalid_image_notice_only_separates_existing_lead[""/"我来画。"]`（:1086），以及改写后的 `test_byok_invalid_refusal_has_only_standard_notice`。
   - 探针 `test_R28_invalid_notice_no_leading_newlines_when_no_lead`：SSE 和落库都不以换行开头。
   - 正控：改回无条件加 `\n\n`，测试失败（KILLED）。
2. **`image_source` 参数化**：
   - `_stream_image_execution` 新增关键字参数 `image_source: str = "tool"`（`:921`），两次 `trace.update` 都使用它（`:928`、`:939`）。
   - 判断器路径传 `image_source="planner"`（`:1702`）；原生路径（`:423-426`）不传，取默认值 `tool`。
   - 探针用 AST 检查 `run_chat`：字符串常量 `"image_source"` 出现 0 次，关键字参数 `image_source=` 只有 1 处。逐事件和 finally 里的回写都已删除。
   - 测试：`test_r2_execution_records_planner_source_before_first_event`（:1097）在第一个事件之前就断言 `image_source == "planner"`。
   - 正控：首次只把第一处 `trace.update` 改成 `"tool"`，第二处仍写入参数值，因此用例存活。这是变异写得不完整，不是测试缺陷。两处都改为 `"tool"` 后，`test_r2_execution_records…`、`test_r2_image_pending…[draw]`、`test_r1_planner_draw_precedes_existing_mirror_mode` 三条全部失败（KILLED）。

### R2-9 加强新增测试：通过

1. **`test_reserved_turn_settlement_and_single_image`**（:712）：
   - `success` 分支断言 `len(calls) == 1`、`generated_image` 恰好 1 个、落库正文同时含「图片已生成。」和「使用的描述」、`done == 1`、`not refunds`（reserved=True，即 10 颗已结算）。
   - 其他分支用精确值 `int(...)`。
   - 全部 7 个新测试文件 grep `<= 1` 零命中。
   - 原约 880 行处（现 `:895-898`）改为 error 时无 done、否则 `== 1`；该 HTTP 用例还核对了真实 SQLite 余额 20→10。
2. **`test_switch_off_route_keeps_requests_unchanged`**：`:625` 先 `assert requests`，再做 `all(...)`。
3. **`test_platform_disabled_request_identical_and_crisis_ignores_unsolicited_tools`**（:374）：
   - 改为 `chat.run_chat(ctx, crisis=...)`，参数化 `("0",False)`、`("1","possible")`、`("1","high")`；
   - 危机资源条数用 `== int(crisis is not False)`，SSE 与落库都做了精确断言。
4. **请求体与基线比对**（`test_byok_image_tool.py`）：
   - 新的 `baseline_client` 夹具（:43）用 `git show 7ac7b57:backend/byok/client.py` 执行出基线模块，`ReplyStream` 和 `_open` 都是基线代码。
   - `:309`（anthropic / dashscope）比较「默认、tools=None、基线」三份请求体，要求 `len == 3` 且两两相等。
   - `:335`（dashscope / deepseek）经 httpx MockTransport 比较 SDK 实际发出的三份 HTTP body 字节。
   - anthropic 这一条比的是传给 SDK 的 kwargs，不是 HTTP 字节；测试名已不再写 "bytes"，表述如实。
5. **`test_invalid_planner_result_is_unavailable_without_content_leak`**（:152）：
   - 改用 `PRIVATE_PLANNER_CASE_R2_` 加 sha256 的特征串，与数字不冲突；
   - 同时精确断言 planner 日志只有 1 条，`msg` 和 `args` 恰为 `(exception_type, elapsed_ms)`，比原断言更强。
   - 本任务测试中已不存在 `content not in caplog.text`。
6. **R2-1 至 R2-8 的补测**：见上文各节，共 14 个正控变异全部被抓到，证明这些测试不是恒真。

另外，与 R1 快照逐文件 diff，被删除的行只有上面那些弱断言和条文要求替换的旧断言，没有删除或放宽其他断言。

- `test_r1_no_draw_routes_without_tools_or_image_candidate` 的「你好」用例改为期望判断器被调用 1 次。原因是该用例自带 `generate_image` pending，这是 R2-1 规定的新行为。
- 「无 pending、无线索时不调用判断器」改由 `test_r2_unrelated_last_assistant_does_not_call_planner` 覆盖。

## 必须修复（仅限 R2 条文未完成或改错的）

无。

## 可优化（含新发现）

1. **R2-3 的 closed 检查在工具关闭时与基线不一致（本轮要求评估的点）**
   - 现状：`byok/client.py:294-296` 在工具关闭时也把「closed 时的 ValueError」改抛为 ReplyInterruptedError，基线是原样抛 ValueError。
   - 已证明的影响范围：用户可见文案相同（都是 `other`）；当前代码里，不超时而 closed 只出现在取消或收尾路径，外层只会抛 CancelledError，用户收不到错误事件，trace 也不写。所以没有用户可见影响。
   - 为什么不是必须修复：符合 R2-3 条文「先按 timed_out / closed 判断」。
   - 另有一点不一致：同为工具关闭，其他异常类型（例如 `httpx.ReadError`）走 `except Exception`，不做 closed 转换。
   - 建议二选一：
     - 把 closed 转换限定在 `self.image_tool` 为真时，使工具关闭时与基线逐字节等价；
     - 或在 03-report 的 R2 节注明这是有意偏离基线，并补一条工具关闭时的用例把行为钉住。
2. **R2-1 缺少「pending 存在 + 判断器不可用 → 旧路由补参生图」的仓库内回归用例**
   - 本轮探针 `test_M1_rerun_planner_unavailable_again_legacy_pending_generates` 已证实行为正确：旧路由用 pending 补参生图，不退款。
   - 但新测试 `test_r2_image_pending_answer…` 只参数化了 draw 和 no 两种。建议补上 error 分支，把 M1 路径 A 的完整两轮钉住。
3. **开关开启的全量里，R2-1 让 4 条旧用例新增失败**
   - 03-report 5.4b 的第 26、31-33 项。原因是存在生图 pending 时现在会调用判断器，验收插件固定判为不画。
   - 这是条文要求的行为变化，报告逐条写了原因，不算缺陷。作者方在沙箱外复验时应确认这几条确实属于「允许的旧预期失败」。
4. **`IMAGE_PLANNER_FOLLOWUP_PATTERN` 含单字「画」，会多触发判断器**
   - 上一条回复含「动画」「漫画」「画面」等字样时，下一轮无论说什么都会多一次 1–5 秒的判断器调用。
   - 这是条文规定的常量，只影响延迟和成本，不影响正确性。上线后可以从 trace 里 `image_planner` 的分布观察误触发率，再决定是否收窄。

## 证据文件

- 探针：`scratchpad/wo6/review/r2/test_probe_r2.py`（运行结果 21 passed），`r2/conftest.py`（硬拦截 socket 与 DNS）。
- 正控变异：
  - `r2/mutate.py`：未变异副本 `32 passed`，11 个变异中 10 个 KILLED，1 个因变异不完整而存活；
  - `r2/mutate2.py`：`image_source` 两处都变异后 KILLED；
  - `r2/mutate3.py`：Reserved 与普通两条路径分别 KILLED。
  - 变异只在 `r2/mut/pristine/` 源码副本里进行，每次运行后复原，仓库未被改动。
- R1 新文件快照（用于 R1→R2 diff）：`r2/r1snap/`。
