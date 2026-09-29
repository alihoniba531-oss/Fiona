# 2026-09-29 复核可优化项修复规格（6 条）

来源：`docs/tasks/2026-09-29-deep-check/04-review-round3.md`。那是 Fable 第 3 次独立复核，结论为「通过」，同时列出了 6 条可优化项。本规格自包含，以本文为准。

## 0. 基线与硬规则

- 仓库：`/Users/yangjing/Desktop/ai-workspace/Fiona`。基线是 `HEAD = 27e6806`，工作区干净。衡量本任务的改动用 `git diff 27e6806` 加上新增的未跟踪文件。
- 不得运行任何写 git 状态的命令（add/commit/stash/checkout/reset/restore/clean/switch）。
- **不得修改基线已有测试的输入或断言来让测试通过。** 只有本规格明确改变了某个行为时，才允许修改；报告里要逐条列出：文件、行号、改动内容、依据本规格哪一条。
- 不引入任何新依赖（requirements、package.json 的依赖、各 lock 文件都不得变化），不做数据库 schema 变更。
- 测试隔离：
  - 不得读写真实的 `backend/*.db`、`backend/uploads/`、`backend/.env`、`backend/.env.local`；
  - 不做真实模型或 TTS 调用；
  - 不下载任何东西；
  - 不运行 `next dev`；
  - 不打印任何 KEY、SECRET、TOKEN 的值。
- 需要端口的测试只用 127.0.0.1 上的临时端口（端口号填 0 由系统分配），不得占用 3000、3001、8000、8001、8010。
- 请按下文「分工建议」的文件边界拆成多个 subagent 并行实施；同一文件的改动交给同一个 subagent。

### 文件白名单

- **后端**：`backend/services/chat_service.py`、`backend/services/exchange_service.py`、`backend/exchange_store.py`、`backend/routers/voice.py`
- **前端**：`frontend/app/history/page.tsx`、`frontend/app/profile/page.tsx`、`frontend/app/match/page.tsx`、`frontend/lib/auth.ts`、`frontend/lib/useAccountIdentity.ts`
- **测试**：`backend/tests/` 下新建或修改的测试
- **文档**：
  - `docs/ARCHITECTURE.md`（只改与本任务行为变化直接相关的句子）
  - `docs/tasks/2026-09-29-deep-check/03-report.md`（只改 O5、O6 所说的过时内容）
  - 本目录新建的 `03-report.md`

## 1. 任务

### O1 会话不存在时，危机资源必须先于可能失败的清理发出

**现状**：`backend/services/chat_service.py` 中 `run_chat` 的 `except ResourceNotFound:` 分支，先对非 high 级执行 `clear_pending` 和 `clear_user_mode`（两者都是 SQLite 写操作，可能因 database is locked 等原因抛异常），之后才发资源和错误事件。清理一旦抛异常，possible 级用户既收不到资源，也收不到 `error` 事件。

**要求**：
- 先发资源（仍然只对 high 和 possible，且整轮只发一次），再发 `{"error": "会话已删除或不可用"}`。
- 清理放在最后，用 `try/except` 保护：失败时只记日志（不打印消息内容），不影响已经发出的事件。
- 补测试：possible 级消息遇到 ResourceNotFound，并且打桩让 `clear_pending` 抛异常时，SSE 仍然依次包含资源文本和 error；high 级同样测一遍。

### O2 交流在途的撤销轮询不得每 0.25 秒新建一次数据库连接

**现状**：`_generate_while_authorized` 每 0.25 秒调用一次 `exchange_store.is_exchange_running`，而这个函数每次都新开一个 `aiosqlite` 连接（每次都新建一个 OS 线程）。一次 45 秒的调用大约要连 180 次，120 秒的工作流调用大约 480 次。

**要求**：
- 同一次在途调用只用一个数据库连接，整个轮询期间复用。例如在 `exchange_store` 提供一个异步上下文管理器，返回可以反复查询的检查器。
- 撤销后取消上游的时延保持不变：不超过 0.5 秒。
- 连接在调用结束、取消、异常时都必须关闭。
- 补测试：让上游挂起 3 秒，统计期间 `aiosqlite.connect` 的调用次数，应当 ≤ 2；撤销后上游在 0.5 秒内被取消；异常路径下连接会关闭。
- 原有的交流测试（包括 `test_exchange_isolation.py` 中的重复停止、peer 双方停止、在途计数）必须全部通过，而且不得修改它们的输入和断言。

### O3 Safari/iOS 朗读首句首音延迟

**现状**：WebKit 播放每句朗读时，先发 `Range: bytes=0-1` 试探，这一步要等整句**非流式**合成完才返回首字节。Chromium 走的是流式 200，首字节约 0.6 秒。WebKit 必须拿到有限长度才会触发 `ended`，这一点不能退回。

**要求**：
- **在换票时预热合成。** 如果 `POST /tts/ticket` 请求的 User-Agent 属于 WebKit 引擎，就立即在后台启动这张票据的非流式合成：结果写进票据缓存，复用现有的 `audio_build` 机制。之后的 Range 请求直接等待或读取这次合成，不得重复合成。
- **判定 WebKit 引擎**：UA 含 `AppleWebKit`，并且**不含** `Chrome/`、`Chromium/`、`Edg/`。
  - 因此 iOS 上的 Chrome（CriOS）和 Firefox（FxiOS）也算 WebKit，会预热；
  - 桌面 Chrome 和 WebView2 不预热，保持流式 200 路径和首音速度不变。
- 预热失败时，后续请求按现有逻辑重新合成一次，或者返回现有的错误。不得让票据卡死。
- 预热任务必须受现有的缓存总量上限和 TTL 约束。票据过期或被淘汰时，任务结果要被丢弃，不得泄漏内存。
- **补测试**：
  - Safari UA 换票后，合成桩被调用 1 次；随后 `bytes=0-1` 和 `bytes=0-N` 都返回 206，合成总次数仍为 1；
  - Chrome、Edge（WebView2）UA 换票后不预热，`bytes=0-` 仍然是流式 200；
  - iOS Chrome（CriOS）UA 会预热；
  - 预热合成抛异常后，下一次 Range 请求能正常处理。
- 在 `docs/ARCHITECTURE.md` 的朗读部分补一句预热说明。

### O4 身份回填前，/history、/profile、/match 不得显示或使用「默认用户」

**现状**：
- `frontend/app/history/page.tsx:43` 用 `params.get("user") || localStorage… || "默认用户"` 计算用户名，不订阅身份变化。Cookie 有效但 localStorage 为空时，首屏显示「默认用户 · 0 条」，导出文件名可能变成 `Chloe_默认用户_日期.txt`。
- `profile/page.tsx:56` 和 `match/page.tsx:151` 的初值也是「默认用户」。
- `frontend/lib/auth.ts` 里专门为这三页写了一段「回填后整页 reload」的兜底：`DIRECT_IDENTITY_ROUTES`、`reloadDirectIdentityRoute`、`IDENTITY_RELOAD_KEY`。

**要求**：
- 三个页面都改用 `useAccountIdentity()`（它会触发 `ensureAccountIdentity`），身份变化时重新取数。
- 身份拿到之前显示加载态，不渲染、不导出、不请求任何以「默认用户」为身份的内容。
- `history` 页的 `?user=` 参数：
  - 只在它与当前身份一致时使用；
  - 不一致时，以当前身份为准，并去掉 URL 里的这个参数。
- 以上完成后，删掉 `auth.ts` 中只为这三页存在的整页 reload 兜底，以及相关的 sessionStorage 键。其他页面和抽屉的行为不得变化。
- 生产构建里，这三页不得出现「默认用户」字样。
  - 验证命令：在 `frontend/` 下执行 `rg -n "默认用户" app/history app/profile app/match lib`，应无匹配，或只剩注释。
  - 其他页面如果还有这个字样，保持原样，并在报告里列出来。
- 前端没有测试框架，**不要新增测试依赖**。在报告里写清手工验证步骤；规格作者会用无头 Playwright 实测。

### O5 修正 deep-check 报告主表的覆盖性数字

在 `docs/tasks/2026-09-29-deep-check/03-report.md` 主表的 T4 行里，覆盖性描述仍然是第 1 轮的「210 个规则汉字中可反查的 74 字/77 变体」。

要求：按当前实现更正为最新数字。数字用脚本实际统计得出：safety.py 全部规则汉字、有映射的字数、白名单字数。

### O6 修正 deep-check 报告主表过时的测试名和文件数

同一份报告顶部的 T1–T10 对应表和文件清单，引用了已经不存在的测试函数名（例如 `test_explicit_image_requests`、`test_tts_ticket_single_use_and_bound_to_user` 等），文件数也仍写 42。

要求：
- 用脚本收集 `backend/tests/test_*.py` 中所有 `def test_` 的名字，逐一核对主表里引用的每个测试名。不存在的，换成当前实际对应的测试名。
- 文件清单与文件数按 deep-check 任务实际改动的文件统计：`git diff --stat 12b6bf0 27e6806`（`12b6bf0` 是 09-25 加固提交，`27e6806` 是 deep-check 提交）。
- 在报告里写明你用于核对的命令。
- 只改过时的事实，不重写其他内容。

## 2. 分工建议

- **A**：`chat_service.py` 及其测试（O1）
- **B**：`exchange_service.py`、`exchange_store.py` 及其测试（O2）
- **C**：`routers/voice.py` 及其测试，以及 `ARCHITECTURE.md` 的朗读说明（O3）
- **D**：`history`、`profile`、`match` 三个页面，以及 `lib/auth.ts`、`lib/useAccountIdentity.ts`（O4）
- **E**：两份报告（O5、O6，以及本目录 03-report）

## 3. 验收标准

1. `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` 全部通过，数量 > 1487，0 failed、0 error。
2. 逐个测试文件单独运行 pytest，全部通过；`compileall` 退出码为 0。
3. 在仓库外的前端克隆里执行 `npx tsc --noEmit`、`npm run lint -- --max-warnings=38`、`npm run build`，全部通过。**不要在仓库里直接 build**。
4. 真实数据哈希前后一致：`ls backend/uploads | sort | shasum`、`shasum backend/*.db`。`frontend/AGENTS.md` 没有变化。
5. `git diff --stat 27e6806` 列出的文件，加上新增的未跟踪文件，全部在白名单内。`git diff 27e6806 -- backend/tests` 中，基线已有测试的改动都能在报告里找到对应依据。
6. O1–O4 中列出的新增测试都存在并且通过。报告里逐条写出测试函数名。

## 4. 交付

在本目录写 `03-report.md`，内容包括：修改的文件、O1–O6 与实现的逐项对应、验收命令的真实输出（含测试数量）、基线测试改动清单（没有就写「无」）、未完成或需要人工确认的地方。最后输出同样内容的变更总结。
