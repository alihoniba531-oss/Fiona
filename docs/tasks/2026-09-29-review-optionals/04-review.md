# 独立复核（Fable，2026-09-29）

**结论：不通过**——1 条必须修复（O3 回归），4 条可优化；均经 Fable 对抗核实。返修见 05-fix-round1.md。

## backend

| 条目 | 结论 |
|---|---|
| O1：ResourceNotFound 时危机资源（high/possible，整轮一次）先于 error 事件发出，清理放最后 | 通过 |
| O1：清理失败只记日志且不打印消息内容 | 通过 |
| O2：同一次在途调用只用一个数据库连接 | 通过 |
| O2：撤销后 ≤0.5s 取消上游 | 通过 |
| O2：连接在结束/取消/异常路径都关闭，无线程残留 | 通过 |
| O2：长连接读能看到其他连接提交的 stop，且不持有事务阻塞写 | 通过 |
| O2：原有交流测试（含重复停止、peer 双方停止、在途计数）未改且通过 | 通过 |
| O3：WebKit 引擎判定（含 AppleWebKit 且不含 Chrome/、Chromium/、Edg/） | 通过 |
| O3：换票预热复用 audio_build，Range 请求等待或读取同一份，单次合成 | 通过 |
| O3：Chromium/WebView2 不预热，bytes=0- 仍流式 200 | 通过 |
| O3：预热失败/票据失效不卡死 | 通过 |
| O3：预热受缓存总量与 TTL 约束，过期/淘汰丢弃结果、无泄漏 | 通过 |
| O3：按需合成路径（非预热）行为不得回归 | 不通过 |
| 新增测试稳定（逐文件单独运行、重复 3 次） | 通过 |
| 验收 1/2：全量 pytest > 1487 且 0 failed；compileall 退出码 0 | 通过 |
| 验收 5：改动文件全部在白名单内，依赖与 schema 未变 | 通过 |
| docs/ARCHITECTURE.md 朗读部分补预热说明 | 通过 |
| 验收 4：真实数据哈希前后一致 | 无法验证 |

- **[必须修复｜核实 CONFIRMED]** O3 把「TTL 截断 + 结果丢弃」套到了按需合成路径，有效票据的闭区间/等待者请求在跨 TTL 时从 206 退化为 502（`backend/routers/voice.py:148`）
  - 规格只要求预热任务受 TTL 约束、过期/淘汰时丢弃预热结果。但实现把约束写进了所有合成共用的函数：
1) voice.py:148-150 `timeout = min(dashscope_timeout_millis() / 1000 + 1, entry.expires_at - time.monotonic())` / `if timeout <= 0: return None` —— 按需请求（Chromium 闭区间 Range、WebKit 预热失败后的重试、/tts/synthesize）在票据有效时到达，却只被允许等「剩余 TTL」这么久；票据发出 55s 后到达的请求只剩 5s 合成窗口。
2) voice.py:134-138 else 分支 `audio = None`：票据在合成期间自然过期（current.expires_at <= now）或被淘汰时，把已合成好的字节直接丢掉，随后 `build.audio = None`，并且
3) voice.py:161 `return build.audio` 取代了基线的 `return audio`，创建者本人也拿不到自己刚合成的音频。
基线 27e6806：_use_tts_ticket 通过即视为有权取音频，合成结果总是返回给创建者和等待者，只是过期不写缓存。前端 page.tsx:731-790 会为
  - 核实意见：引用全部核对无误：backend/routers/voice.py:148-150 `timeout = min(dashscope_timeout_millis() / 1000 + 1, entry.expires_at - time.monotonic())` / `if timeout <= 0: return None` 写在预热与按需共用的 `_build_tts_audio` 里；:134-138 else 分支 `audio = None`；:161 `return build.audio`。基线 27e6806 的 `_complete_tts_audio` 无条件 `build.audio = audio`、`_get_tts_audio` 返回局部 `audio`，过期只是不写缓存。

复现（审查者测试文件对两版 voice.py，我重跑）：scratchpad/op
- **[可优化｜核实 CONFIRMED]** O1 清理挪到 yield 之后，客户端在 error 事件后断开会跳过 clear_pending/clear_user_mode（`backend/services/chat_service.py:1187`）
  - `if not high_crisis:` 下的两步清理位于 `yield _sse({"error": …})` 之后且不在 finally 的 shield 作用域内。Starlette 在客户端断开时会向生成器抛 CancelledError/GeneratorExit，此时清理不会执行（基线因清理在 yield 之前所以总会执行）。影响仅限 chat_slot_state 里以 (user, 已删除会话 id) 为键的孤儿行，不影响用户可见行为，属于规格要求的顺序带来的边角。
  - 核实意见：机制在真实用户路径上成立，且比审查者预想的更常发生——但被跳过的只有 clear_user_mode，不是两者。frontend/app/page.tsx:1356-1358 收到 `error` 事件即 `await reader.cancel()`，所以「error 后断开」是前端的常规行为，不是人为构造。我在 8101 端口用真实 main.app + uvicorn 0.47（ASGI spec_version 2.3 → Starlette 1.3.1 走任务组 listen_for_disconnect；外加 `@app.middleware("http") require_auth` 这个 BaseHTTPMiddleware）复现：只打桩出网入口与 `_ensure_active_conversation`，clear_pending/clear_user_mode 包装成
- **[可优化｜核实 CONFIRMED]** WebKit 预热让每句朗读在默认线程池里占 2 个线程（合成 + 阻塞等待）（`backend/routers/voice.py:170`）
  - 预热后 WebKit 的探测请求总是走 `await asyncio.to_thread(build.done.wait)`（voice.py:170），与 `asyncio.to_thread(synthesize…)`（voice.py:152）同在 main.py 设定的 32 线程 `fiona-chat` 默认池；前端预取下一句，一名 WebKit 用户合成期间可占 4 个线程，8 名并发用户即可占满该池，而 detect_mode / recognize_intent / clear_pending 等聊天路径的 to_thread 也依赖它。基线只在探测与正式请求重叠时才出现等待线程。
  - 核实意见：引用核对无误：voice.py:170 `await asyncio.to_thread(build.done.wait)`、:152 `asyncio.to_thread(synthesize, …)`、main.py:59-64 与 :86-88 默认池 32 线程（FIONA_DEFAULT_POOL_WORKERS 可调）供全局 to_thread 共用。我用 sys._current_frames 在 TestClient 内实测（scratchpad/opt-review/adv/{new,base}/tests/test_adv_threads.py）：Safari UA 换票后发 `bytes=0-1` 探测、合成被闸住时，新实现池内忙线程 = 2（1 个在合成桩、1 个阻塞在该票据的 `build.done.wait`）；基线 = 1（探测本身是创建者，无等待线程），与审

## frontend

| 条目 | 结论 |
|---|---|
| O4-a 三页（/history /profile /match）改用 useAccountIdentity()，身份就位前只渲染加载态 | 通过 |
| O4-b 身份到位前不渲染/不请求/不导出以「默认用户」为身份的内容 | 通过 |
| O4-c 身份变化时重新取数（同页 fiona-user-changed 与跨标签页 storage 事件） | 通过 |
| O4-d history ?user= 与当前身份不一致时以当前身份为准并去掉参数，一致时保留 | 通过 |
| O4-e 删除 auth.ts 专用 reload 兜底后，其他页面与抽屉 iframe（?embed=1）行为不变 | 通过 |
| O4-f 生产构建里三页不得出现「默认用户」；其他页面若有需列出 | 通过 |
| O5 deep-check 报告主表 T4 覆盖性数字按当前实现更正 | 通过 |
| O6 deep-check 报告过时测试名与文件数更正，且只改过时事实 | 通过 |
| 验收 1：全量 pytest 全部通过，数量 > 1487，0 failed、0 error | 通过 |
| 验收 2：逐个测试文件单独运行全部通过；compileall 退出码 0 | 通过 |
| 验收 3：仓库外前端克隆 tsc / lint --max-warnings=38 / build 全部通过 | 通过 |
| 验收 4：真实数据哈希前后一致；frontend/AGENTS.md 无变化 | 部分通过 |
| 验收 5：改动文件全部在白名单内；基线已有测试未被改动 | 通过 |
| 验收 6：O1–O4 新增测试存在并通过，测试函数名逐条可对应 | 通过 |

- **[可优化｜核实 CONFIRMED]** 另一标签页清空身份或退出登录后，三页永久停在「加载中…」，既不再回填也不跳登录页（`frontend/lib/auth.ts:55`）
  - `if (!username && !identityRecoveryAttempted) { queueMicrotask(() => { void ensureAccountIdentity(); }); }`——页面首次用 Cookie 回填身份后 identityRecoveryAttempted 永久为 true。此后若 localStorage.fiona_user 被另一标签页移除（退出登录时 clearAuth 就会这样做），storage 事件让 useAccountIdentity() 变为 ""，HistoryContent/ProfileContent/MatchContent（history/page.tsx:379-381 等）转为渲染「加载中…」，但再没有任何代码触发回填或 401 跳转，用户只能手动刷新。基线三页不订阅身份变化，表现为继续显示旧数据；/settings、/plaza、主页用同一 hook 也有同样的「正在加载身份…」表现，因此属于共享 hook 的既有语义，不是本次引入的回归，也未违反规格「身份拿到之前显示加载态」的字面要求，但从「加载中」变成永久卡死对用户不友好。
  - 核实意见：复现成立，机制核对无误，但审查员对基线的描述只对 /history 准确，对 /profile、/match 低估了差异。

【代码核对】frontend/lib/auth.ts:27-28 `if (identityRecoveryAttempted || …) return Promise.resolve(""); identityRecoveryAttempted = true;`——回填只做一次，只有 setAuth（auth.ts:71）重置；getUsername() auth.ts:55 `if (!username && !identityRecoveryAttempted) { queueMicrotask(() => { void ensureAccountIdentity(); }); }` 被该标志挡住。history/page.tsx:379-381、profil
- **[可优化｜核实 CONFIRMED]** history 头部在数据到达前显示「用户名 · 0 条」，条数为假值（`frontend/app/history/page.tsx:153`）
  - `{username} · <span className="readout"><b>{allMsgs.length}</b> 条</span>`——allMsgs 初值为 []，/api/history 返回前头部先渲染 `reviewer_a · 0 条`（实测 MutationObserver 快照序列：'加载中…' → '历史记录 reviewer_a · 0 条 … 加载中…' → '历史记录 reviewer_a · 2 条 …'）。身份已是真实身份，符合规格，但「0 条」是数据未到的假数字；基线同样如此。
  - 核实意见：复现成立，属基线既有的展示瑕疵，不在规格范围内。

【代码核对】frontend/app/history/page.tsx:44-45 `const [allMsgs, setAllMsgs] = useState<Msg[]>([]); const [loading, setLoading] = useState(true);`，第 153 行头部无条件渲染 `{username} · <span className="readout"><b>{allMsgs.length}</b> 条</span>`，只有第 281 行主区域按 `loading ?` 显示「加载中…」。数据未到时头部必然是「用户名 · 0 条」。

【复现】脚本 /private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-459

