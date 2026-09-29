# O1–O6 实施与验收报告

基线：`27e6806`。本轮未运行写 Git 状态的命令，未改依赖或数据库 schema；测试只使用临时数据与上游桩，未调用真实模型/TTS、下载内容或运行 `next dev`。规格文件 `02-spec.md` 在开始工作前已经是未跟踪文件，不计入本轮新增文件。

## 修改文件

| 项目 | 文件 |
|---|---|
| O1 | `backend/services/chat_service.py`；新增 `backend/tests/test_o1_resource_cleanup.py` |
| O2 | `backend/services/exchange_service.py`、`backend/exchange_store.py`；新增 `backend/tests/test_exchange_poll_connection.py` |
| O3 | `backend/routers/voice.py`、`docs/ARCHITECTURE.md`；新增 `backend/tests/test_tts_webkit_prewarm.py` |
| O4 | `frontend/app/history/page.tsx`、`frontend/app/profile/page.tsx`、`frontend/app/match/page.tsx`、`frontend/lib/auth.ts` |
| O5、O6 | `docs/tasks/2026-09-29-deep-check/03-report.md` |
| 本报告 | 新增 `docs/tasks/2026-09-29-review-optionals/03-report.md` |

`frontend/lib/useAccountIdentity.ts` 保持原样，三个页面现均使用该 hook。

## O1–O6 对应

| 项目 | 实现与证据 |
|---|---|
| O1 | `ResourceNotFound` 时先按 high/possible 级别发送一次危机资源，再发送固定 error；非 high 的两项 SQLite 清理在事件之后分别受 `try/except` 保护，失败日志仅含异常类型。新增 `test_deleted_conversation_cleanup_failure_keeps_crisis_resource_and_error`，参数化覆盖 possible、high **2 例**。 |
| O2 | `exchange_running_checker` 为一次在途调用复用一个 `aiosqlite` 连接，仍每 0.25 秒轮询；上下文退出时关闭连接。新增 `test_three_second_provider_call_reuses_one_poll_connection`、`test_revocation_cancels_upstream_within_half_second`、`test_provider_exception_closes_poll_connection`、`test_external_cancellation_closes_poll_connection`，共 **4 例**，覆盖三秒挂起期间一次连接、撤销后 0.5 秒内取消和异常/外部取消关连接。原有交流测试未改。 |
| O3 | WebKit UA（含 `AppleWebKit` 且不含 `Chrome/`、`Chromium/`、`Edg/`）换票即在后台做非流式合成，Range 探测与正式请求共享 `audio_build`，命中后返回有限长度 206；桌面 Chrome/Edge 的 `bytes=0-` 仍流式 200。失败允许下一次 Range 重试；预热截止于票据 TTL，过期或淘汰时取消任务、唤醒等待者并丢弃结果，保留缓存大小限制。朗读架构说明已更新。新增 `test_safari_ticket_prewarms_once_for_probe_and_playback`、`test_range_waits_for_pending_prewarm_and_gets_finite_length`、`test_desktop_chromium_tickets_do_not_prewarm_and_zero_open_range_streams`、`test_ios_alternate_browsers_use_webkit_prewarm`、`test_failed_prewarm_allows_next_range_to_retry`、`test_invalidated_prewarm_discards_its_result`、`test_prewarm_wait_is_capped_by_ticket_ttl`、`test_prewarmed_audio_obeys_total_cache_budget`，共 **11 例**。 |
| O4 | history、profile、match 用 `useAccountIdentity()` 等待 Cookie 身份回填，等待期间显示加载态；按身份 key 重挂载并重取各自数据。history 仅接受与当前身份一致的 `?user=`，不一致时使用当前身份并从 URL 移除该参数；导出前再次检查身份。删除 `auth.ts` 中三页专用的整页 reload 和 sessionStorage 键。`rg -n '默认用户' frontend/app/history frontend/app/profile frontend/app/match frontend/lib` 无匹配；`frontend/app` 的其他页面也无匹配。 |
| O5 | 按 `safety.py` 字符串常量和现有测试独立映射脚本实测：规则汉字 **296**，有映射 **114**，无异体白名单 **182**；已更正 deep-check 主表 T4 数字。 |
| O6 | 以 AST 收集 `backend/tests/test_*.py` 中 `def test_` 名称，主表 T1–T10 引用的缺失名称检查结果为 `[]`；已更正 T1/T6 及 R1 残留的过时测试名。`git diff --stat 12b6bf0 27e6806` 与 `git diff --name-status 12b6bf0 27e6806` 实测 deep-check 为 **69 个文件（45 修改、24 新增）**，已更正文件数与清单。核对命令和脚本写在 deep-check 报告中。 |

## 验收实测

| 命令或检查 | 真实结果 |
|---|---|
| `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` | **1504 passed，0 failed，0 error，12 warnings，44.29s**；退出码 0，满足 `>1487`。 |
| 对 `backend/tests/test_*.py` 逐文件执行 `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider <文件>` | **58/58 个文件通过，合计 1504 passed，0 个失败文件**；每个文件均由独立 pytest 进程运行。 |
| O1–O3 新文件定向：`tests/test_o1_resource_cleanup.py tests/test_exchange_poll_connection.py tests/test_tts_webkit_prewarm.py` | **17 passed**（分别 2、4、11），12 warnings，4.26s，退出码 0。 |
| `cd backend && PYTHONPYCACHEPREFIX=/private/tmp/fiona-review-pycache .venv/bin/python -m compileall -q services/chat_service.py services/exchange_service.py exchange_store.py routers/voice.py tests` | 无输出，退出码 0；字节码写到仓库外。 |
| 仓库外前端克隆：`npm_config_offline=true npx tsc --noEmit` | 无输出，退出码 0。 |
| 仓库外前端克隆：`npm run lint -- --max-warnings=38` | **0 errors，28 warnings**，退出码 0；警告均在未修改的 `app/page.tsx`、`app/plaza/page.tsx`。 |
| 仓库外前端克隆：`NEXT_TELEMETRY_DISABLED=1 npm_config_offline=true npm run build` | 编译、TypeScript 均成功，静态页 **14/14**，退出码 0。 |
| `rg -n '默认用户' frontend/app/history frontend/app/profile frontend/app/match frontend/lib` | 无匹配，`rg` 退出码 1；全 `frontend/app` 扫描也无匹配。 |
| `git diff --check` | 无输出，退出码 0。 |
| `git diff 27e6806 -- backend/tests` | 无输出：基线已有测试没有改动。 |

首次在临时前端克隆中以仓库 `node_modules` 软链接运行 build，Turbopack 因链接越出克隆根目录退出 1；将已有本地依赖完整复制到临时克隆后重跑，结果如上。没有下载依赖，也没有在仓库内 build。

真实数据哈希前后相同：`ls backend/uploads | sort | shasum` 为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`shasum backend/*.db` 为 `fiona.db 403a086c4ec0cf28493fc9fa37b2b6eee528b261`、`local-avatar.db 172d800a603128374bab9177d39b7f66be20be7e`。`frontend/AGENTS.md` 哈希保持 `b402af8a6533dfc73cc5af9164ae5e0c366af9cc`。`git diff --stat 27e6806` 的已跟踪文件与本轮新增的三个测试及本报告均在白名单内；依赖文件无差异。

## 基线已有测试改动清单

无。O1–O3 只新增测试文件，没有改动 `27e6806` 已有测试的输入或断言。

## 未完成或需要人工确认

实现与自动验收无未完成项。按规格仍需浏览器手工验证：保留有效 Cookie、清空 `localStorage.fiona_user` 后分别直达 `/history`、`/profile`、`/match`，确认回填前仅显示加载态，除用于身份回填的 `/profile` 请求外不发各页面的数据请求；回填后显示真实身份并取数。再以不一致的 `/history?user=另一用户&embed=1` 进入，确认 URL 仅移除 `user`、内容和导出文件名使用当前身份；身份切换后确认三页重取数据。真实 Safari/iOS 首音体感和实际 TTS 服务未测，本轮按硬规则只用合成桩。已开始的同步 TTS SDK 线程无法由 asyncio 强制中断；任务结束后迟到的合成结果不会进入票据缓存。

## 返修第 1 轮

依据 `05-fix-round1.md`，本轮仅修改 `backend/routers/voice.py`、`backend/services/chat_service.py`、`frontend/lib/auth.ts`、`frontend/app/history/page.tsx`，扩充本任务新增的 `backend/tests/test_tts_webkit_prewarm.py`、`backend/tests/test_o1_resource_cleanup.py`，并追加本节。`frontend/lib/useAccountIdentity.ts` 无需修改，所有使用该 hook 的页面通过共享 `getUsername()` 接收相同的身份变化。此前 O1–O6 的其他文件保持原有改动。未运行写 Git 状态的命令，未新增依赖或 schema；没有真实模型/TTS 调用、下载或运行 `next dev`。

| 项目 | 修复与新增测试 |
|---|---|
| R1 | `_TtsAudioBuild` 标记预热与按需合成。仅预热使用票据剩余 TTL 截断并在失效时丢弃结果；按需合成使用完整的 `dashscope_timeout_millis()/1000 + 1`，已准入请求跨过 TTL 或合成中票据被淘汰时，发起者及等待者仍能取得音频，失效票据不写缓存。新增 `test_on_demand_closed_range_returns_audio_after_ticket_ttl`、`test_on_demand_closed_range_returns_audio_after_ticket_eviction`、`test_on_demand_stream_waiter_returns_audio_after_ticket_ttl`。 |
| P1 | `ResourceNotFound` 仍按「危机资源 → error → 清理」发送；清理意图在发 error 前记录，两步清理在受 `anyio.CancelScope(shield=True)` 保护的 `finally` 中分别容错执行。新增 `test_deleted_conversation_error_disconnect_still_cleans_pending_and_mode`，在收到 error 后立即 `aclose()`，断言两步清理完成。 |
| P2 | `_TtsAudioBuild` 为各请求事件循环登记异步 Future 等待者；合成完成及预热票据失效时，使用各自 loop 的 `call_soon_threadsafe` 唤醒。探测不再占用默认线程池等待 `done.wait`。新增 `test_webkit_probe_wait_does_not_block_default_pool_thread`、`test_invalidated_prewarm_wakes_waiters_on_separate_event_loops`。 |
| P3 | `auth.ts` 记录已观察到的用户名，非空变为空时复位一次回填状态并排队一次 `ensureAccountIdentity()`；有效 Cookie 回填，401 走原登录失效跳转。版本号阻止旧在途响应覆盖新回填；本页主动 `clearAuth()` 不触发回填。主页、设置、广场和三个直达页继续共用原 hook，无前端测试依赖。 |
| P4 | history 头部在数据加载中显示「… 条」，加载结束后显示实际条数；`Suspense` fallback 加 `role="status"`。 |

### 本轮验收实测

| 命令或检查 | 真实结果 |
|---|---|
| `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` | **1510 passed，0 failed，0 error，12 warnings，44.64s**；退出码 0。 |
| `backend/tests/test_*.py` 逐文件用独立 pytest 进程执行 `-q -p no:cacheprovider` | **58/58 个文件通过，合计 1510 passed，0 个失败文件**。 |
| `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_o1_resource_cleanup.py tests/test_tts_webkit_prewarm.py tests/test_tts_private_tickets.py` | **34 passed，12 warnings，1.91s**；退出码 0。本轮扩充后 O1 测试文件 3 例、WebKit 测试文件 16 例，既有 TTS 文件 15 例。 |
| `cd backend && PYTHONPYCACHEPREFIX=/private/tmp/fiona-review-round1-pycache .venv/bin/python -m compileall -q services/chat_service.py services/exchange_service.py exchange_store.py routers/voice.py tests` | 无输出，退出码 0；字节码写到仓库外。 |
| 仓库外前端克隆 `/private/tmp/fiona-frontend-check.ZPzqr3`：`npm_config_offline=true npx tsc --noEmit` | 无输出，退出码 0。 |
| 同一克隆：`npm run lint -- --max-warnings=38` | **0 errors，28 warnings**，退出码 0；警告仍仅在未修改的 `app/page.tsx` 与 `app/plaza/page.tsx`。 |
| 同一克隆：`NEXT_TELEMETRY_DISABLED=1 npm_config_offline=true npm run build` | 编译和 TypeScript 通过，静态页 **14/14**，退出码 0。 |
| `git diff --check`；`git diff 27e6806 -- backend/tests`；`git diff 27e6806 -- backend/requirements.txt backend/requirements-dev.txt frontend/package.json frontend/package-lock.json frontend/AGENTS.md` | 均无输出，退出码 0；基线已有测试及依赖未改。 |
| `rg -n '默认用户' frontend/app/history frontend/app/profile frontend/app/match frontend/lib`；`rg -n 'asyncio.to_thread\(build.done.wait\)|done.wait' backend/routers/voice.py` | 均无匹配，`rg` 退出码 1。 |

验收前后 `ls backend/uploads | sort | shasum` 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`shasum backend/*.db` 均为 `fiona.db 403a086c4ec0cf28493fc9fa37b2b6eee528b261`、`local-avatar.db 172d800a603128374bab9177d39b7f66be20be7e`；`frontend/AGENTS.md` 为 `b402af8a6533dfc73cc5af9164ae5e0c366af9cc`，均未变化。本轮触及的实现、测试与报告文件均在返修单白名单内；相对 `27e6806` 的其余工作区改动承接前一轮 O1–O6。

### 基线已有测试改动清单

无。只扩充了本任务创建的两个测试文件，没有修改 `27e6806` 已有测试的输入或断言。

### 未完成或需要人工确认

实现与自动验收无未完成项。浏览器手工验证 P3：登录后在一个标签页打开 `/history`、`/settings` 或 `/plaza`，在另一标签页退出，确认前一页只发起一次 `/profile` 身份核验，收到 401 后跳到登录页；再保留有效 Cookie、只在另一标签页删除 `localStorage.fiona_user`，确认一次核验后用户名回填、页面重新取数；本页主动退出应保持原 `/login?reason=logout` 跳转且不额外回填。P4 可在历史请求未返回时检查头部为「… 条」，完成后变为实际数字，并用辅助技术检查加载态。实际 Safari/iOS 首音与真实 TTS 服务仍未测；已开始的同步 TTS SDK 线程无法由 asyncio 强制中断，失效票据的迟到结果不会写入缓存。
