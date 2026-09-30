# 复核报告（第 1 次）

复核者：Fable（全新上下文，只读 02-spec、diff、截图；未读 03-report / 03-verification）。浏览器实测只用无头 Playwright，未改仓库文件（复核前后 `git status --porcelain --untracked-files=all` 一致）。

## 结论：**通过**

无必须修复项。四道闸「全测通过才全计」、429 响应格式、Retry-After、不计数路径、前端不跳句/不乱序/共享退避/可中止/提示只对当前句/「不听了」语义，全部有代码与实测证据；无 429 时输入区截图与基线逐像素相同。

## 验收标准逐条核验（摘要）

- **§0 硬规则与白名单**：通过。只改 `rate_limit.py`、`routers/voice.py`、`ARCHITECTURE.md`（仅 voice.py 一行）、`page.tsx`，新建 `test_tts_ticket_rate_limit.py`、`ttsTicket.ts`；`backend/main.py`、`frontend/AGENTS.md` 无 diff；无依赖变更。
- **§3.1 `check_and_hit`**（`rate_limit.py:38-64`）：通过。先收集全部 `test` 失败项，拒绝分支只读 `get_window_stats` 不 `hit`；`max(1, ceil(reset - now))`；`enabled=False` 直接返回；`_client_ip`/`limiter` 未改。真实 429 实测 header `48` = body `48`，48.16s 后重试 200。
- **§3.2 `/tts/ticket`**：通过。删除 20/minute；四常量在请求时读取（monkeypatch 生效）；user 来自 `Depends(get_current_user)`，ip 来自 `_client_ip`，identifiers 带命名空间；cost 次数 1、字数 `min(len,300)`；401（中间件）/422/空文本 400 都不计数；被拒不签票不预热；429 头与 body 一致；日志不含用户名/IP/文本。
- **§3.3 `ttsTicket.ts`**：通过。用 `typescript.transpileModule` 在 Node 中加载并打桩 `apiFetch`，27 项单元检查全过：Retry-After 整数/HTTP 日期/无效回退 body/缺省 5s/夹 [1,60]s；先等退避再请求；请求体与原来一致；等待中 abort/stale → null 且 0 请求；连续两次 429 → 3 次请求拿到票，onWait 2 次、onWaitEnd 1 次；未等待不调 onWaitEnd；非 ok 与空票据返回 null。
- **§3.4 `page.tsx`**：通过。提示只在当前句等待时显示（实测第 1 句 ended 后 57ms 才出现）；倒计时 effect 只在非 null 时建 interval 并清理；位置、文案、样式类与规格一致；390 宽按钮右缘 378 < 390、高 36；`role=status aria-live=polite`、倒计时 `aria-hidden`、sr-only 固定文案、不抢焦点；「不听了」= `clearTtsQueue` + 已停止标记，`enqueueSpeech` 与免提分支均判断，`clearTtsQueue` 本身不设标记；共享退避在「不听了」后保留（X4：新回复首请求在旧退避结束后 226ms）；无 429 时 footer 截图 chromium/webkit × 1280/390 与基线逐像素相同（PIL `difference().getbbox() is None`）。
- **§4 T3 测试**：通过。11 个函数 / 14 个用例对应 T3.1–T3.10。变异体（不改仓库，插件替换 `voice.check_and_hit`）：`hit_before_test` → 2 failed；`partial_hit` → 1 failed；`skip_user` → 6 failed；`retry_zero` → 1 failed；`no_namespace` → 7 failed；无变异对照 14 passed。
- **§5.1 命令**：新测试 14 passed；全量 1524 passed（1510+14）；tsc 0；ESLint 0 errors / 28 warnings；白名单符合；`20/minute` 0 行；`tts/ticket` 仅 `ttsTicket.ts:76`。`npm run build` 未在仓库内跑（按指示），3031 为该代码的生产构建。
- **§5.2 浏览器**：S1–S5、S7、S8 通过；S6 用等价变体通过（默认限额下先在页面内打 116 张票，第 5 句吃到真实 429，经 Next 代理同源，提示 47→1，48.16s 后重试 200，5/5 按序）。追加 X1（两句同时 429）、X2（同一句连续两次 429，倒计时 `[1,2,1]` 重置）、X3（提示时序）、X4（「不听了」后立即发新消息）均通过。

## 必须修复项

无。

## 可优化项（不阻断验收）

1. **限流日志被块缓冲**：`voice.py:291` 的 `print` 未带 `flush=True`；stdout 是文件或管道时，真实 429 后数秒日志仍无 `[TTS限流]`。项目错误路径的 print 多带 `flush=True`；部署未设 `PYTHONUNBUFFERED`。建议 `print(..., flush=True)`。
2. **T3.9 依赖任务目录里的 `rate_model.py` 路径**（测试 `:165`）。任务目录日后移动会断，可把段文本固化进测试。
3. **提示在「等待已结束、重试请求在途」的约 100ms 里仍显示「1 秒后接着读」**，肉眼几乎不可察；要更干净需在等完后、发请求前清 `waitingUntil`（需同步改规格对 `onWaitEnd` 的定义）。
4. **live region 条件挂载**：部分读屏器对「和内容一起插入」的 live region 不播报首帧；可常驻一个空的 sr-only 状态容器。
5. **验收脚本两个辅助判据有假阳性**：`sentence_order_ok` 在两张票同毫秒时不稳；S5 的 `old_text_requests_after_send` 因两轮回复文本相同会误计。应以 `ended_texts` 与「发送后请求总数恰为 5」为准。
6. S1 倒计时在复核者那次只显示 `[1]`：假 TTS 首句实测约 1.3s，第 1 句结束时退避只剩约 0.8s，符合公式，不是实现问题。

## 给实现方的二次修改指令

无必须修复项，不需要二次修改。若采纳可优化项 1：在 `backend/routers/voice.py` 的 `log_rejection` 里把 `print(...)` 改为 `print(..., flush=True)`，其余不动；重跑 `tests/test_tts_ticket_rate_limit.py` 应仍 14 passed。
