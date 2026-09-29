# 返修单 第 1 轮（对应 Fable 独立复核，见 04-review.md）

复核结论：O1、O2、O4、O5、O6 通过；O3 有 1 条必须修复项（回归），另有 4 条可优化项，本轮一并处理。

原规格 `02-spec.md` 的全部约束继续有效，包括第 0 节的硬规则：不得改动基线已有测试的输入或断言、不引入依赖、不做真实调用、不下载、不运行 `next dev`、不写 git 状态。

允许修改的文件：
- `backend/routers/voice.py`
- `backend/services/chat_service.py`
- `frontend/lib/auth.ts`
- `frontend/lib/useAccountIdentity.ts`
- `frontend/app/history/page.tsx`
- `backend/tests/` 下本任务新增的测试，以及为本轮新增的测试
- 本目录 `03-report.md`

## 必须修复

### R1 TTL 截断与丢弃结果被套到了按需合成路径（O3 引入的回归）

**现状**：
- `voice.py` 中，预热和按需合成共用 `_build_tts_audio`，且都用 `min(dashscope 超时 + 1, 票据剩余 TTL)` 作为超时，剩余时间 ≤ 0 时直接返回 None。
- `_complete_tts_audio` 在票据过期或被淘汰时，把已经合成好的音频丢弃（`audio = None`）。
- `_build_tts_audio` 返回的是 `build.audio`，所以发起合成的请求本身也拿不到结果。

**后果**：一张有效票据发出的闭区间 Range 请求，或者流式传输进行中的并发等待者，只要合成过程跨过了 TTL，就会从基线的 206 退化为 502。前端会为「下一句」预取票据，长句播放可能接近 60 秒，所以预取的票据到 TTL 末段才被使用并不少见。

**要求**：
- **只有预热任务**受 TTL 截断，也只有预热任务在过期或淘汰时丢弃结果。
- **按需合成**恢复基线语义：
  - 超时用 `dashscope_timeout_millis()/1000 + 1`；
  - 结果返回给发起者和所有等待者；
  - 票据过期或被淘汰时，只是不写入缓存。
- 回归测试（复核员已在 `27e6806` 上用同样的场景验证过，基线返回 206）：
  - 一张有效票据发出闭区间请求，合成耗时超过剩余 TTL，仍返回 206 并带音频；
  - 流式 200 传输进行中，第二个等待者跨过 TTL，仍拿到音频（206）。
- 已有的预热相关测试全部保持通过：过期、淘汰、TTL 上限、缓存总量。

## 同轮处理（可优化，都有复核证据）

### P1 会话不存在时的清理被客户端断开跳过（O1 顺序带来的轻度回归）

**现状**：清理挪到了 `yield error` 之后。前端收到 error 事件后会立即 `reader.cancel()`，这属于常规行为，于是 `clear_user_mode`（有时连同 `clear_pending`）被跳过，`chat_slot_state` 里留下以已删除会话为键的孤儿行。基线里清理总会执行。

**要求**：
- 保持「资源 → error → 清理」的顺序不变。
- 清理放在 `anyio.CancelScope(shield=True)` 内，或者在 `finally` 里受 shield 保护的阶段执行，保证客户端断开时清理也能完成。
- 补测试：消费者收到 error 事件后立即 `aclose()`，两步清理仍然都执行了。

### P2 WebKit 预热让每句朗读占用 2 个默认池线程

**现状**：预热之后，探测请求会用 `asyncio.to_thread(build.done.wait)` 阻塞等待，与合成线程同在 32 线程的默认池里。

**要求**：
- 等待改为不占线程的方式。例如：`_TtsAudioBuild` 持有一个在请求事件循环上创建的 `asyncio.Event` 或 `Future`，合成完成后用 `loop.call_soon_threadsafe` 置位；请求端 `await` 它。
- 注意：多个事件循环（测试中可能出现）和票据失效唤醒（`_cancel_tts_prewarm`）两种情况都要正确处理。
- 补测试：探测请求等待预热期间，默认池里不存在阻塞在 `done.wait` 上的线程（可以用 `sys._current_frames` 检查）；原有测试全部通过。

### P3 另一个标签页退出登录后，页面永久停在「加载中…」

**现状**：页面首次用 Cookie 回填身份后，`identityRecoveryAttempted` 就永久为 true。之后如果另一个标签页清除了 `fiona_user`（比如在那里退出登录），这边的页面会一直显示「加载中…」，既不再回填，也不跳转登录页。

**要求**：
- 在 `auth.ts` 或 `useAccountIdentity` 中，检测到用户名从非空变为空时，复位回填标志，并再执行一次 `ensureAccountIdentity()`：
  - Cookie 已失效：得到 401，走现有的 `redirectExpiredSession` 跳转登录页；
  - Cookie 仍然有效：重新回填身份。
- 同一个 hook 的所有使用者（主页、设置、广场、三个直达页）行为一致。
- 不得造成请求循环：每次「非空变为空」只触发一次回填。
- 在报告中写清手工验证步骤。

### P4 历史页数据到达前，头部显示假的「0 条」

`history/page.tsx` 的头部在 `loading` 为 true 时，条数显示为占位符（如「…」），加载结束后再显示实际条数。`Suspense` 的 fallback 加上 `role="status"`。

## 交付

- `backend/` 全量 pytest 与逐文件 pytest 通过，`compileall` 通过。
- 在仓库外的前端克隆里执行 `tsc`、`lint --max-warnings=38`、`build`，全部通过。
- 真实数据哈希不变，`frontend/AGENTS.md` 不变。
- 在 `03-report.md` 末尾追加「返修第 1 轮」，逐条对应 R1、P1–P4，列出新增的测试名，以及基线测试改动清单（没有就写「无」）。
