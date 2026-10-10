# 返修单 R1（回应 04-review.md）

日期：2026-10-09。本单与 `02-spec.md` 同等效力，冲突处以本单为准。

**约束**沿用规格第 3 节，唯一例外是 R1-2：允许修改 `backend/services/chat_service.py`，但**只能改 `_stream_byok_reply` 内部的等待逻辑**，加一个模块常量。其余部分，以及 `routers/chat.py` 等受保护文件，仍然一行不改。

**做法**：每项先写会失败的测试或验收脚本，确认它变红，再改代码。不安装包，不发真实网络请求。小范围收尾，直接自己做，不必派子代理。

## R1-1 思考强度单选组切换后丢失键盘焦点（A1，必须修复）

**涉及位置**：`frontend/app/page.tsx` 底栏的思考强度组，以及 `frontend/components/ChatModelSection.tsx` 设置页的思考强度组。

**问题**：请求进行中（busy）、聊天加载中（loading）或服务端不可用时，按钮用了原生 `disabled`。焦点所在的按钮一被禁用，焦点就掉到 `<body>`。

**改法**：
- 上述三种状态下改用 `aria-disabled="true"`，不再用原生 `disabled`。
- 点击和键盘处理函数里已有的 busy / loading / available 守卫保留，禁用期间点击或按键不发请求。
- 样式加上 `aria-disabled:opacity-50` 与 `aria-disabled:cursor-default`。
- roving tabIndex 保持不变：选中项 `tabIndex=0`，其余 `-1`。
- 请求结束后，如果焦点原本在组内，焦点应停在当前选中项上。

**验收**：由主控在沙箱外用浏览器执行，你写好 Playwright 脚本放在仓库外的临时目录。
- 聚焦「低」，**不重新聚焦**，连按两次 ArrowRight（每次等请求完成）：服务端为 `high`，且 `document.activeElement` 是 `aria-checked="true"` 的「高」。
- 鼠标点击「中」之后，焦点仍在组内。

## R1-2 BYOK 等待期间发送 SSE 心跳（A2）

**涉及位置**：`backend/services/chat_service.py` 的 `_stream_byok_reply`。

**改法**：
- 建流时的 `_byok_call(open_reply_stream...)`，以及逐块 `_byok_call(next, ...)` 的等待，都改为「放进任务里等，超时就发心跳」，写法参照同文件生图的 `_IMAGE_HEARTBEAT_SECONDS`：
  - 新增模块常量 `_BYOK_HEARTBEAT_SECONDS = 10`；
  - 每满一个间隔还没拿到结果，就 `yield ": thinking\n\n"`。这是一条 SSE 注释，不是 `data:` 事件，前端会忽略。
- **取消语义必须与现在完全一致**。客户端断开或生成器被关闭时，要取消这个任务并等它结束，让 `_byok_call` 里现有的取消路径照常执行：先 abort，再等 worker，最后关闭、释放槽位。
- 不能出现以下情况：
  - 遗留未等待的任务；
  - 「exception in shielded future」这类 ERROR 日志；
  - 重复 abort；
  - 槽位泄漏。
- 心跳不改变任何 `data:` 事件的内容和顺序，也不影响计费、退款、`reply_model` 标注和错误映射。

**新测试**（`backend/tests/test_byok_effort.py`，或新建 `test_byok_heartbeat.py`）：
1. monkeypatch 心跳间隔为 0.05 秒，让桩流在首块前延迟 0.2 秒：输出里至少有 2 条 `: thinking`，之后的 `data:` 事件与不延迟时逐字相同。
2. 心跳期间客户端取消：`control.abort` 被调用、worker 结束、`_BYOK_ACTIVE` 回到 0、caplog 中没有 asyncio ERROR。
3. 不延迟时一条心跳都不发。

**文档**：在 DEPLOYMENT 与 ARCHITECTURE 中补一句：BYOK 等待上游期间每 10 秒发送 SSE 注释心跳，防止 Next 开发代理（30 秒空闲超时）或其他中间层切断长时间思考。

## R1-3 选中态更醒目，桌面底栏不换行（M1、M2）

**选中态**：底栏与设置页的思考强度组，选中项使用与「启用我的聊天模型」开关一致的强调色：背景 `var(--btn)`、文字 `var(--btnink)`。未选中项悬停时只允许轻微变化，不得与选中态相同。日、夜两种主题都要清楚。

**不换行**：视口宽度 ≥1280 时，底栏保持一行：
- 左侧：「Enter 发送，Shift + Enter 换行」；
- 右侧依次为：「聊天：…（不扣草莓）」、思考 低 / 中 / 高、改用平台。

放不下时，只允许把「聊天：…」这段用省略号截断，用 `title` 显示全文。其他文案不改。手机宽度允许换行，但不得横向溢出。

**验收**：由主控截图核对：
- 1440×900 下底栏为单行；
- 选中「高」且鼠标悬停在「中」时，只有「高」呈选中样式；
- 390×844 夜间模式下不溢出。

## 验收

- 重跑规格第 5 节全部检查，有两处调整：
  - 第 5.1 条白名单在原有基础上追加 `backend/services/chat_service.py`；
  - 第 5.2 条命令中去掉 `backend/services/chat_service.py`。另需 `git diff backend/services/chat_service.py` 只涉及 `_stream_byok_reply` 与新常量。
- 全量 pytest 通过数 ≥ 2920 + 本轮新增数。
- 更新 `03-report.md`，新增「R1 返修」一节。
