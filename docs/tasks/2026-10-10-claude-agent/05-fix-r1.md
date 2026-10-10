# 返修 R1：验收与独立复核后的修改

日期：2026-10-10。本返修单与 `02-spec.md` 同等效力；两者冲突时，以本返修单为准。下面各项都必须完成，其余实现保持现状，不回滚已完成的工作。复核原文见同目录的 `04-review.md`。

## R1-1 计费在落库成功后才成立（必须）

**现状**：智能体模式下，工具卡交付（`claude_agent.py` 约 523 行）或生图成功（`chat_service._stream_image_execution` 约 1061 行）时就设置了 `state.billable = True`，这时还没有落库。会话被删（`_save_response` 抛错）或客户端中途断开时，用户仍被扣 10 颗、不退款；生图的情况下，图片还会被 finally 删掉。旧路由的顺序是先 `_save_text_reply` 再设 billable（`chat_service.py` 1313→1315）。

**改法**：
- 智能体循环里，计费项先记在局部变量中。只有 `save_delivered()` 成功、`state.response_saved` 为真之后，才执行 `state.billable = True`。
- 智能体模式下（`agent_result is not None`），`_stream_image_execution` 不再设置 `state.billable`。
- 会话被删时（`ResourceNotFound` 或落库抛出的同类错误），沿用旧路由的平台处理和文案，不显示「你的模型调用失败」。

**测试**：
- 卡片交付后落库失败：退款，不显示「你的模型调用失败」。
- 卡片交付后客户端断开：退款。
- 生图成功后落库失败：退款，附件被清理。

## R1-2 智能体轮里生图失败不能让前端报错（必须）

**现状**：后端先发出 `status: "generating_image"`，Seedream 失败后，`claude_agent.py` 约 458–462 行吞掉了 error，并把失败结果回灌给 Claude；Claude 正常作答并发送 `done`。前端 `page.tsx` 约 1944 行判定「开始生图但没收到图」就抛错，整轮被标为出错，朗读队列被清空；「正在生成」状态卡在 Claude 作答期间一直挂着。

**改法**：
1. **后端**：智能体轮里工具生图失败时，转发一个状态复位事件 `{"status": "image_failed", "source": "tool"}`，不转发 error。
2. **前端**：
   - 收到 `status === "image_failed"` 时：清掉该消息的 `generationStatus`，并把本轮的「生图进行中」标记复位，使收尾检查不再要求必须收到图。
   - 收到 `done` 时：若本轮的生图来自工具，也不再因为缺图抛错。
   - 面板生图与旧路由的行为逐字不变。
   - `ChatStreamEvent.status` 的类型补上 `"image_failed"`。

**测试**（新测试文件，沿用现有前端逻辑测试的做法）：
- 事件序列 reply_model → text → status(generating_image, tool) → status(image_failed) → text → done：不抛错，生成状态被清除，文字完整。
- 面板生图失败时仍显示重试按钮，行为不变。

## R1-3 回灌内容块不得丢掉「必须有、可为空」的字段（必须）

**现状**：`_block_dict` 使用 `model_dump(..., exclude_none=True)`。结果引用里的 `title: null`、`document_title: null` 等「必须存在、值可为空」的键会被删掉，回灌请求可能被 API 以 400 拒绝。

**改法**：
- 改用 anthropic 1.12.1 SDK 自己回灌消息时使用的序列化方式。去 SDK 源码里找它在 tool runner 或 `messages` 参数构造中实际调用的函数；如果找不到，就用 `model_dump(mode="json", by_alias=True, exclude_unset=True)`。
- 在 `03-report.md` 写明采用了哪个函数，以及它在 SDK 源码中的位置。

**测试**：用真实 SDK 类型构造一个带 `title=None` 引用的 text 块和一个 web_search_tool_result 块，回灌后这些键仍然存在。

## R1-4 天气城市规则不误拒（必须）

**现状**：主人说「北京」、Claude 传「北京市」时被拒绝；而且只拿规范化后的结果比较，比原文更窄。

**改法**：
- 对 Claude 传入的城市，生成以下几种候选写法：
  - 原样；
  - 规范化结果；
  - 去掉末尾一个行政后缀（「市」「省」「区」「县」「州」「盟」「自治州」「特别行政区」）后剩余 2 个字及以上的写法。
- 对本轮及最近 3 条 user 原文，取原文和对原文的规范化结果两种文本。
- 任一候选写法以子串形式出现在任一原文文本中即放行。候选写法必须至少 2 个字，单字一律不放行。
- 放行后，实际查询使用主人原文中匹配到的那个写法，再经 `normalize_city` 处理。隐私边界不变：记忆、system、图片摘要都不参与比较。

**测试**：
- 主人说「北京」、Claude 传「北京市」：放行。
- 主人说「那曲市天气」、Claude 传「那曲」：放行。
- Claude 传单字：拒绝。
- 城市只出现在记忆或 system 中：拒绝。

## R1-5 去掉客户端工具的 `eager_input_streaming`（必须，修订 02-spec 3.1）

**原因**：本单工具参数都很短，这个选项带来的收益可以忽略；而开启后，工具参数 JSON 不合法会让 SDK 在流中抛错，整轮直接以「调用失败」结束。

**改法**：
- 删除全部客户端工具定义中的 `"eager_input_streaming": true`，包括 `CLAUDE_CLIENT_TOOLS` 和 `open_agent_stream` 里添加该字段的代码。
- 同步更新相关测试和文档。

## R1-6 发给 Claude 的图片控制在接口上限内（必须）

**现状**：本地上传上限是原图 5MB，转成 base64 后约 6.7MB；Anthropic 单张图片有大小和像素上限，图片过大时可能被拒。

**改法**：组装图片块时，用已有依赖 Pillow 检查图片：
- 长边超过 2000 像素，或原始字节超过 3.5MB：等比缩放到长边不超过 2000 像素。
  - 有透明通道的 PNG 保留 PNG，否则转为 JPEG，质量 85。
  - 处理后仍超过 3.5MB 时，逐步降低尺寸，直到不超过为止。
- 图片处理放在线程里执行，不阻塞事件循环。
- 只影响发给 Claude 的副本，上传落盘的文件不变。

**测试**：
- 大图被缩放，且 base64 长度在上限内。
- 小图原样发送。
- media_type 与实际编码一致。

## R1-7 3 条前端渲染测试在 CI 会失败（必须）

**现状**：`backend/tests/test_claude_agent_frontend.py` 的 `render_card`（约 137–163 行）需要 `require('typescript')`、`react`、`react-dom/server`，依赖 `frontend/node_modules`。CI 的 backend 任务不安装前端依赖，因此以下用例会失败：
- `test_web_sources_card_renders_only_valid_sources_with_fixed_title`（2 组参数）；
- `test_shared_renderer_keeps_weather_and_generic_cards`。

作者方已在浅克隆中复现：没有 node_modules 时这 3 条失败。

**改法**：
- 先用 `node -e "require.resolve('typescript', {paths:[<frontend 目录>]})"` 等方式检测这三个包。任一个解析不到，就 `pytest.skip` 并写明原因。
- 另补几条不依赖这些包的源码断言，保证 CI 里仍然覆盖 web_sources 分支：固定标题「联网搜索」、只显示来源、`append` 分支不改动 `cardData`。

**验收**：
- 在 `git clone --depth 1` 的仓库副本中（没有 node_modules；新文件需复制进去），本任务新测试全部通过或跳过，不得有失败。
- 在完整工作区中，这 3 条照常执行并通过。

## R1-8 小修（必须）

1. **规格第 6 节第 9 点的覆盖缺口**：在 runtime 与 integration 两组测试中，把 `set_pending` 打桩为一旦调用就直接失败，以此证明智能体路径不写 pending。
2. **工具失败不写 `trace["error"]`**：改为累加计数 `trace["agent_tool_errors"]`。这样一轮里只是某个工具失败时，不会跳过画像提取等后续任务。
3. **平台侧失败的文案**：在调用 Claude 之前出错（例如模式判定、读取或清理 pending、确认会话存在），不显示「你的模型调用失败」，改用平台现有的通用错误文案和处理方式。
4. **只有来源卡时**：什么都没交付就出错时，不补发来源卡，也不落库。
5. **多步之间的文字**：新一次 Claude 请求开始输出文字、且之前已经输出过文字或卡片时，先输出一个 `"\n\n"`，并同样写入落库正文。
6. **槽位繁忙的文案**：等待全局槽超时时，使用旧路由已有的「自带模型通道繁忙，请稍后再试」文案（以代码里现有的常量或字符串为准）。
7. **`byok_chat` 计数时机**：移到第一次成功拿到全局槽之后，确保只计一次。
8. **预算耗尽与生图同时发生**：恰好在生图完成时预算耗尽，图片要么落库，要么被删除，不得留下孤立文件。

## 验收

与 `02-spec.md` 第 7 节相同，另加 R1-7 的浅克隆验收。

- 受保护文件零 diff。
- 任务前既有测试零改动，`conftest.py` 仍然只多那一行。
- 默认全量通过。
- 开关开启的全量测试中，失败项逐条列出原因。
- `pip check`、`tsc`、`eslint` 均为 0 errors。

结果追加到 `03-report.md` 末尾的新节「R1」。原始 traceback 不要整段粘贴进报告，只写每条失败的一行原因和数量，完整输出另存到同目录的 `acceptance/` 文件中。
