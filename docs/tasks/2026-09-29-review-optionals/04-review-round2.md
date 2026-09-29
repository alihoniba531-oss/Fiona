# 独立复核 第 2 次（Fable，2026-09-29）

**结论：通过。** R1（必须修复）经复现确认修好（首轮快照 502、当前 206/200、基线 206/200）；P1–P4 无回归。

## backend：通过

**证据：** 【复核对象与快照】仓库只读；开工/收尾两次核对哈希一致（voice.py 2ba62102、chat_service.py 5f6915e5、test_tts_webkit_prewarm.py 2e321089、test_o1_resource_cleanup.py 3059b58b、auth.ts 4c9ea723、history/page.tsx 99aa5878），git status 与开工时相同。返修第 1 轮实际触碰的文件（与第 1 次复核快照 scratchpad/opt-review/backend、frontend 逐文件 diff）：backend/routers/voice.py、backend/services/chat_service.py、tests/test_tts_webkit_prewarm.py、tests/test_o1_resource_cleanup.py、frontend/lib/auth.ts、frontend/app/history/page.tsx，全部在 05-fix-round1 白名单内；依赖文件与基线已有测试 diff 均为 0 行。三份代码副本：new=当前工作区、base=git archive 27e6806、r1=第 1 次复核留存的首轮快照（voice.py e66a862c），均在 /private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/opt-review-r2/{new,base,r1}/backend。

【R1 必须修复项：已真正修好（含正控）】自写对抗测试 scratchpad/opt-review-r2/adv/test_r2_adv.py（不依赖 waiters 等新内部属性，可跨三版运行）：r1a 有效票据闭区间请求跨 TTL（TTL=0.4s，合成在过期后才返回）；r1b 按需超时=dashscope+1 而非剩余 TTL（DASHSCOPE_TIMEOUT_SECONDS=5、TTL=0.3s、合成真实耗时 0.8s）；r1c 流式 200 在途 + 第二个等待者跨 TTL；r1d /tts/synthesize 跨 TTL；r1e 合成期间票据被淘汰；r1f 两个闭区间重叠（创建者+等待者）跨 TTL。结果：new 15/15 通过（r1a–r1f 均 206/200 且带完整音频，过期票据出表）；base 上 r1a–r1f 状态码全部 206/200（仅「过期票据立即出表」两条断言不成立，属基线不清扫，非状态回归）；r1 上 r1a–r1f 全部 `assert 502 == 206`——证明测试真能抓到首轮回归。仓库自带的 3 条 R1 回归测试在 r1 快照上同样失败（2 条 502、1 条 AttributeError），在 new 上通过。代码核对：_build_tts_audio 只对 build.prewarm 取 min(超时, 剩余 TTL)；_complete_tts_audio 只在 build.prewarm 时置 audio=None，非预热在过期/淘汰时仅不写缓存并 finish(audio)；返回值 build.audio 经 finish 后即合成结果。

【P1–P4 回归检查】
P1（真实 uvicorn + main.app，端口 8111/8112，只打桩出网入口与 _ensure_active_conversation，裸 socket 读到 error 事件后 11ms 内断开）：new 日志顺序 yield:text(资源)→yield:error→clear_pending:start→clear_pending:end(0.6s 后)→clear_user_mode→log_event，断开后两步清理仍完成；r1 正控：clear_pending:start 后立刻 log_event，clear_user_mode 缺失（被取消）。
P2：探测请求等待在途合成时，fiona-chat 默认池忙线程 new=1（仅合成），base/r1=2（多一个阻塞在 done.wait）。
预热约束未回归（new-only）：pw_a 预热受 TTL 截断（TTL 0.3s、合成挂 2s → 任务 <1.5s 完结、audio=None、票据出表、合成线程晚归结果丢弃）；仓库测试 test_invalidated_prewarm_discards_its_result[expired/evicted]、test_prewarm_wait_is_capped_by_ticket_ttl 通过；pw_c/pw_d 缓存总量上限（超限不缓存但票据仍有效、多票据总量恒 ≤ 上限）。
跨事件循环 Future：xl_a 等待者被取消后从 waiters 移除且循环关闭后 finish 不抛；xl_b 两个独立 asyncio.run 循环的等待者被外线程 finish 各唤醒一次、二次 finish 不覆盖；xl_c 循环已关闭的等待者 finish 吞掉 RuntimeError；xl_d 票据在别处判失效时探测请求 0.0s 被唤醒返回 502（不挂死）、预热任务 cancelled、票据出表。
P3/P4（前端 cp -cR 到 scratchpad、删 .next 后生产 build 成功，next start 8112 → 后端 8111，无头 Chromium 1243）：/history /profile /match /settings 另一标签页退出登录（Cookie 失效+清 localStorage）→ 均 401 跳 /login?reason=expired，且仅 1 次 /api/profile；Cookie 仍有效只清 localStorage → 四页均重新回填并重取数据，/history 连续两次「非空→空」各恰好 1 次回填（profile=[1,1]、history 重取 [1,1]），/profile 页 2 次 /api/profile = 1 次回填 + 1 次页面自身数据（page.tsx:64），8 秒窗口稳定不增长，无循环。P4：MutationObserver 快照序列 '加载中… [role=status]' → 'r2_user · … 条 … 加载中…' → 'r2_user · 0 条 … 还没有聊天记录'，数据到达前不出现 0 条。
【验收命令】new 全量 pytest：1510 passed、0 failed（>1487）；三份新增测试文件重复 3 次均 23 passed；compileall 退出码 0。结束时已按 PID 结束 8111/8112 全部进程，端口空闲。日志在 scratchpad/opt-review-r2/logs/。

**回归：** 未发现阻断性回归。已排查并确认无回归的面：按需合成三种入口（闭区间 Range、流式等待者、/tts/synthesize）跨 TTL/淘汰均恢复基线 206/200；预热仍受 TTL 截断且过期/淘汰丢弃结果；缓存总量上限对预热与按需都生效；跨事件循环唤醒/取消/循环关闭三种路径无异常；ResourceNotFound 清理在客户端断开（CancelledError 路径，真实服务器）与 aclose（GeneratorExit 路径，仓库测试）下都完成且顺序为资源→error→清理；跨标签页回填不循环、401 跳登录、四个 hook 使用页行为一致。我的 e2e 脚本中两条标 FAIL 的行均为脚本自身取样时机问题（P4 的 loading 文本在 1.5s 延迟后才抓取；/profile 的 2 次 /api/profile 含页面自身数据请求），已用快照序列与请求时间线证实实际行为正确。

**可优化（未处理，留待用户决定）：**
- WebKit 预热在途时若已有探测请求附着等待，票据在此期间被淘汰（2048 上限）或预热被 TTL 截断（仅当 DashScope 合成耗时 > 剩余 TTL，默认 60s/60s 窗口极窄），等待者收到 502；基线会自行按需合成返回 206。这是 05 返修单「预热失效即丢弃结果」的直接后果，xl_d 已证不挂死，可考虑：失效时让已附着的等待者继续拿到合成结果、只不写缓存。
- voice.py:404 has_cached_or_pending_audio 扩展到 audio_build 后，Chromium 在另一闭区间合成在途期间发来的 `Range: bytes=0-` 会等待并返回 206 闭区间，而非基线的流式 200；两者都送完整音频、浏览器兼容，仅记录行为差异。
- test_prewarm_wait_is_capped_by_ticket_ttl 与 test_on_demand_stream_waiter_returns_audio_after_ticket_ttl 依赖 0.05–0.08s 级别的时间窗（本次 4 轮均稳定通过）；高负载 CI 下有偶发风险，可把过期判定改为显式 replace(expires_at=0) 后再断言。
- 前端 /profile 页身份回填与页面数据共用 /api/profile，跨标签页清身份后同一 URL 出现 2 次请求；虽不循环，若想在监控里区分可让身份回填改用更轻的端点或在页面层复用回填结果。

## frontend：通过

**证据：** 【范围】第 2 次独立复核（frontend）：P3（跨标签页身份回填/401 跳登录）、P4（history 加载占位 + Suspense role=status），以及机械核验（tsc / lint / build / 基线测试未改）。03-report.md 未采信；判断只基于 02-spec、04-review、05-fix-round1 与 `git diff 27e6806` + 新增未跟踪文件。仓库只读，全程未写 /Users/yangjing/Desktop/ai-workspace/Fiona（收尾 `git status --short` 仍为开工时的 14 条：10 个 M + 4 个 ??；`git diff 27e6806 --stat` 仍为 10 files, +302/−149）。

【代码核对（frontend/lib/auth.ts、useAccountIdentity.ts、app/history/page.tsx、profile、match）】
- P3 机制：auth.ts 新增 `observedUsername`；`getUsername()` 在「上次观察到非空、本次为空」时 `identityVersion += 1; identityRecoveryAttempted = false; identityRecovery = null`，随后 `queueIdentityRecovery()`（受 `identityRecoveryQueued / identityRecoveryAttempted / authRedirectStarted / pathname==='/login'` 四重闸门，微任务内只调一次 `ensureAccountIdentity()`）。`ensureAccountIdentity` 成功时写回 localStorage 并同步 `observedUsername`；401 走原有 `redirectExpiredSession()`（`clearAuth()` 先置 `identityRecoveryAttempted=true, observedUsername=""`，因此退出后不会再触发回填）。`setAuth`/`clearAuth` 均维护 `observedUsername`。删除了 DIRECT_IDENTITY_ROUTES / reloadDirectIdentityRoute / IDENTITY_RELOAD_KEY 及 apiFetch 内的 reload 兜底。useAccountIdentity.ts 与第 1 轮相同（未改动）。
- P4：history/page.tsx 头部 `{loading ? "…" : allMsgs.length}`；Suspense fallback 与身份占位 `<div role="status">加载中…</div>`。profile/match 的 Suspense fallback 也带 role=status。

【机械核验（仓库外克隆 /private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/opt-review-r2/fe-fable-r2/frontend，cp -cR 后删 .next 与 tsbuildinfo；5 个被测文件 shasum 与仓库逐一 SAME）】
- `npx tsc --noEmit` 退出码 0。
- `npm run lint -- --max-warnings=38`：28 problems（0 errors, 28 warnings）≤ 38，退出码 0。
- `FIONA_BACKEND_ORIGIN=http://127.0.0.1:8114 npm run build`：Next.js 16.3.3，✓ Compiled，✓ TypeScript，14 条路由生成，BUILD_EXIT=0（build.log）。
- `git diff 27e6806 --stat -- backend/tests` 输出为空：基线 57 个已跟踪测试文件零改动；新增 3 个未跟踪测试（test_exchange_poll_connection.py、test_o1_resource_cleanup.py、test_tts_webkit_prewarm.py）。改动文件与新增文件全部在 02-spec / 05-fix-round1 白名单内；package.json、lock、requirements 无变化；frontend/AGENTS.md 不在 diff 中。
- `rg -n "默认用户" app lib components`（frontend/）：无匹配。

【实机复现（生产构建 `next start -H 127.0.0.1 -p 8113`；隔离后端 uvicorn 8114：FIONA_DB_PATH/FIONA_UPLOADS_DIR 指向临时目录、DEV_MODE=1、JWT_SECRET 临时值、DASHSCOPE/DEEPSEEK_API_KEY=placeholder、PYTHON_DOTENV_DISABLED=1、HOT_TOPICS_API_BASE 指向 127.0.0.1:1 以阻断外网热榜；后端日志无任何公网热榜域名；无模型/TTS 调用；用 database.save_message 为 reviewer_r2 预置 2 条消息）。无头 Chromium chromium_headless_shell-1243，`uv run --offline --with playwright`，每个场景新建 context、两个标签页同一 context（Tab A 只做“另一标签页”操作，Tab B 为被测页）。脚本 fe-fable-r2/p3p4_test.py（141 项）与 extra_rapid.py（7 项），日志 run3.log；合计 148/148 通过。】
- P4：对 /api/history 加延迟 900ms，MutationObserver 记录头部快照序列 = ['reviewer_r2 · … 条', 'reviewer_r2 · 2 条']，从未出现「· 0 条」；role=status 快照 ['加载中…']；最终显示真实条数 2；无 pageerror。
- 正控（证明检测非空转）：阻断 /api/profile 且 localStorage 为空时，/history 停在 role=status「加载中…」、fiona_user 保持空、/api/profile 恰好 1 次不重试。
- 首载回填（O4 既有路径）：空 localStorage + 有效 Cookie → /api/profile 1 次 → 写回 fiona_user → 显示 reviewer_r2 · 2 条。
- P3 Cookie 有效、另一标签页清空 fiona_user（每页连做 2 次）：/history、/match、/settings、/plaza 每次恰好 1 次 /api/profile（200），fiona_user 回填，页面重新取数恢复，回填后 3s 静默窗口 0 次新请求，未跳登录；/profile 每次 2 次（1 次回填 + 页面自身数据请求同一端点），静默窗口 0；主页 `/` 每次 3 次，来源分别为 '/'、'/plaza?embed=1'、'/settings?embed=1'（顶层 + 两个抽屉 iframe 各一次，符合任务说明），静默窗口 0。
- P3 Cookie 失效：Tab A 在 /settings 点真实按钮「退出登录并撤销现有会话」（到达 /login?reason=logout），Tab B 的 /history 与主页 `/` 均跳到 /login?reason=expired，跳转前 /api/profile 分别 1 次 / 3 次且全部 401，到登录页后无新请求，fiona_user 为空；/profil

**回归：** 前端范围内未发现回归：三直达页、/settings、/plaza、主页（含两个抽屉 iframe）在「跨标签页清空→回填」「Cookie 失效→401 跳登录」「同页主动退出」三条路径上行为一致，回填每次转变只触发一次且无请求循环，Suspense/身份占位带 role=status，history 加载期头部不再显示假「0 条」。基线已有测试零改动，tsc/lint(28≤38)/build 全部通过。

**可优化（未处理，留待用户决定）：**
- 主页 `{username ? <iframe/> : 占位}`（app/page.tsx:2002、2039）在跨标签页清空→回填的短暂空窗期会卸载并重建两个抽屉 iframe：iframe 内部状态（滚动位置、未发帖草稿）丢失并各自重新拉数。属基线既有结构，非本次引入；如要平滑可在顶层对 iframe 保留 key 而只切换可见性。
- `getUsername()` 作为 useSyncExternalStore 的 getSnapshot 带副作用（改模块状态 observedUsername/identityVersion/identityRecoveryAttempted 并排微任务）。当前实测正确，但 React 可能在渲染期多次调用 getSnapshot，语义依赖“首次调用完成状态转换、后续调用幂等”的隐含约定；可考虑把「非空→空」检测挪到 subscribeAccount 的事件回调中，让 getSnapshot 变纯函数。
- /profile 页自身数据请求与身份回填复用同一 `/api/profile` 端点，一次回填计为 2 次请求；若日后加请求监控/限流，需区分两种来源（例如回填请求带专用查询参数或走 /me）。
- 账号切换语义（另一标签页 setAuth 为别的用户名）：页面头部显示 localStorage 里的新名字，但数据仍按 Cookie 身份拉取（实测出现 `other_person · … 条` 后显示 reviewer_r2 的记录）。基线既有，非本次引入；可在 useAccountRequest 里比对 /api/profile 返回的 username 与 owner。
- 主页 iframe 内退出：iframe 的 clearAuth 会向顶层与另一 iframe 发 storage 事件，二者各排一次回填，理论上 401→`/login?reason=expired` 可能与 iframe 的 `redirectTop('/login?reason=logout')` 竞态；本次 3 次实测均为 reason=logout，且基线亦有同一竞态。可在 clearAuth 后由顶层统一处理跳转。
- 复核流程：并行复核员共用 scratchpad 子目录名 `opt-review-r2/frontend`，导致本方首套环境（含 .next、临时 DB、日志）被覆盖并造成一轮假失败。建议规格为每位复核员显式分配互不相同的目录标签（如 `<角色>-<模型>-r2`）。
- 测试脚本可复用：fe-fable-r2/p3p4_test.py 覆盖 P3/P4 的 141 项断言（含正控），若前端日后引入测试框架可直接迁为 e2e 用例。

