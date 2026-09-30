# 朗读票据有效期放宽到 150 秒，修复「点此播放」丢句 —— 规格（v1）

基线：`dc5336a`（main）。任务级别：L2。涉及后端常量与票据表、前端朗读队列两处接入；不动数据模型。
工作目录：本仓库根目录（基于 main 的 git worktree）。

## 0. 硬规则（违反任一条即返工）

- **不得修改任何已有测试的输入或断言，只有一处例外**：`backend/tests/test_tts_private_tickets.py` 里 `assert issued.json()["expires_in"] <= 60`（约第 39 行）。这一条写死的是旧有效期，本任务授权把它改为与新常量一致的断言，例如 `== voice.TTS_TICKET_TTL_SECONDS`。除这一行外，已有测试一个字都不改，也不删不跳过。新增测试放进新文件。
- 不引入依赖，不改 `requirements*.txt`、`package.json`、lockfile。
- 不做真实网络调用。不运行 `next dev`。不做 git 写操作（commit/stash/checkout/reset）。不读 `.env*`，不碰 `*.db`。
- 沙箱里起不了浏览器，浏览器实测由 Claude 主会话做。
- 什么时候停下来问：只有影响「实现什么」时才停，写进报告的「未决问题」；只影响「怎么验证」的事自己定。任何情况下不回滚已完成的工作。
- 可用两个 subagent 并行：后端一路，前端一路，按文件分工，同一文件只给一个 subagent。派子代理时不要传 model 和 reasoning_effort 参数。
- **白名单**：
  - `backend/routers/voice.py`
  - `backend/tests/test_tts_private_tickets.py`（只改上面那一行断言）
  - 新建 `backend/tests/test_tts_ticket_ttl.py`
  - `frontend/lib/ttsTicket.ts`
  - `frontend/app/page.tsx`
  - `docs/ARCHITECTURE.md`（只改 `routers/voice.py` 那一行）
  - 本目录 `03-report.md`
  - 除此之外一律不动。

## 1. 背景

### 1.1 现状

- 朗读每句先 `POST /tts/ticket` 换一张一次性票据，再用 `<audio src=/tts/stream?ticket=…>` 播放。
- 票据有效期是 `backend/routers/voice.py` 的 `TTS_TICKET_TTL_SECONDS = 60`。过期后 `/tts/stream`、`/tts/synthesize` 返回 404。换票响应里带 `expires_in`。
- 浏览器拦下自动播放（`NotAllowedError`）时，页面停在这一句，显示「浏览器拦下了自动朗读 / 点此播放 / 不听了」。
  - 用户点「点此播放」时，`resumeBlockedTts`（`frontend/app/page.tsx`，约 1072 行）对这一句**原来那张票**直接 `play()`，不重新换票。
- 前端另有一处超龄判断（v3 刚加）：预取句转为当前句时，如果票已签发超过 `TTS_PRELOAD_MAX_TICKET_AGE_MS = 45_000`，就放弃这张票、按原文重新换票（约 954 行）。

### 1.2 问题

用户在被拦提示出现后，隔了超过「60 秒减去这张票已过的时间」才点「点此播放」：

1. 票已过期。
2. Chromium 开始播放时会重新请求 `/tts/stream`（`Cache-Control: no-store`），拿到 404，触发 `error`。
3. `finishCurrentTts` 把这一句当成结束跳过，界面没有任何提示。

上一轮复核用无头 Chromium 实测复现过。

## 2. 目标

1. 后端票据有效期改为 **150 秒**：常量、`expires_in`、到期判断全部一致。
2. 「点此播放」无论用户隔多久才点，都从被拦的那一句读起，不丢句、不乱序：
   - 票还够用：照旧直接播放；
   - 不够用：在这次点击里放弃旧票、按原文重新换票再播。
3. 前端判断「票还够不够用」统一以后端返回的 `expires_in` 为准，不再写死秒数。预取句的超龄重换改用同一判据。
4. 有效期变长后，未过期票据在内存表里停留更久。补一道「每个用户最多保留 64 张未过期票据」的上限，防止少数账号挤掉其他用户正在播放的票据。
5. 其他行为保持不变：限流、429 等待、被拦提示的其余交互、预取节奏、隐私（原文只在 POST 体里）。

## 3. 设计要求

### 3.1 后端（`backend/routers/voice.py`）

- `TTS_TICKET_TTL_SECONDS = 150`。签发时 `expires_at = now + TTS_TICKET_TTL_SECONDS`，响应 `{"ticket": …, "expires_in": TTS_TICKET_TTL_SECONDS}`。两处都在**请求时**读模块常量，测试可以 monkeypatch。
- **每用户未过期票据上限**：
  - 新增常量 `TTS_MAX_PENDING_TICKETS_PER_USER = 64`，请求时读取。
  - 在签发处的同一把锁里，按以下顺序处理：
    1. 先做现有的过期清理；
    2. 如果**当前用户**名下未过期票据数已经 ≥ 上限，按签发先后淘汰**这个用户自己**最早的票据，直到数量 < 上限。被淘汰的票据同样要调用 `_cancel_tts_prewarm`；
    3. 再做现有的全局上限淘汰（`TTS_MAX_PENDING_TICKETS`，逻辑不变）；
    4. 最后写入新票据。
  - 这一步绝不能淘汰其他用户的票据。
- 在常量处加注释，写明两点：
  - 为什么要有每用户上限：有效期变长后，同一来源可持有的未过期票据增多，全局 FIFO 淘汰可能挤掉别人正在播放的票据。
  - 为什么正常使用不会淘汰到正在用的票据：前端同时只持有当前句和预取句两张，它们总是这个用户最新签发的。
- 其余逻辑一律不变：限流四道闸、使用次数、缓存、WebKit 预热、Range 处理。

### 3.2 前端 `frontend/lib/ttsTicket.ts`

- `requestTtsTicket` 的返回值改为 `Promise<{ ticket: string; expiresInMs: number } | null>`。
- `expiresInMs` 取响应里的 `expires_in`（秒）：必须是有限正数，换算成毫秒；缺失或无效时按 60 秒；结果夹在 [1 秒, 600 秒]。
- 其余流程（429 等待、共享退避、可中止、`onWait` / `onWaitEnd`）一字不改。

### 3.3 前端 `frontend/app/page.tsx`

1. **票据到期时刻**：
   - `PreparedTtsAudio` 的 `ticketAt` 改为 `ticketExpiresAt: number | null`，初始为 `null`。
   - 在 `mkTtsAudio` 里，拿到票、通过迟到结果保护、设置 `src` 的那一处，记为 `Date.now() + expiresInMs`。
   - 迟到保护顺序逐字保留：先检查 `canUse` 与票据，再设 `src`，再检查 `canUse`，最后 `load()`。
2. **统一判据**：
   - 删除 `TTS_PRELOAD_MAX_TICKET_AGE_MS`，新增模块级常量 `TTS_TICKET_MIN_REMAINING_MS = 15_000`；
   - 新增一个小函数，例如 `isTicketStale(prepared)`：`ticketExpiresAt !== null && ticketExpiresAt - Date.now() < TTS_TICKET_MIN_REMAINING_MS`；
   - 常量注释写明：以后端 `expires_in` 为准，剩余不足 15 秒视为不够用，留出开始播放和首个 Range 请求的余量。按 150 秒有效期，正常流程不会触发。
3. **预取句转为当前句**（`playNextInQueue`）：把原来的「票龄 > 45 秒」判断换成 `isTicketStale(prepared)`。放弃流程不变：`releaseTtsAudio` → 文本放回队头 → 走现有 `mkTtsAudio` 分支。
4. **「点此播放」**（`resumeBlockedTts`）：
   - 保持现有第一步：预取句占着未解锁元素时，放弃它并把文本放回队头。
   - 然后判断当前句 `isTicketStale(current)`：
     - **不够用**时，按下面顺序**同步**完成，不能有 `await`，保持在用户手势内：
       1. 把当前句从「当前」位置撤下：`ttsCurrentRef.current = null`，`ttsPlayingRef.current = false`；
       2. `ttsQueueRef.current.unshift(current.text)`。这一步必须在上一步预取句文本放回之后执行，保证当前句排在最前；
       3. `releaseTtsAudio(current)`，释放它占着的元素；
       4. `primeTtsAudio()`：此时释放出来的元素空闲且未解锁，会在这次手势里被解锁；
       5. `setTtsPlaybackBlocked(false)`；
       6. `playNextInQueue()`：按原文重新换票。换票期间如遇限流，照常等待并显示限速提示。新票拿到后在已解锁的元素上播放。
     - **够用**时，走现有路径：`primeTtsAudio()` → 直接 `playPreparedTts(current)` → 隐藏提示 → `tryPrefetch()`。一字不改。
   - 重新换票后如果仍被浏览器拒绝，照常再次显示被拦提示，不自动循环。
5. 其余不变：
   - 限速提示；
   - 「不听了」（`stopTtsByUser`）；
   - 关朗读；
   - 手势解锁的其他调用点；
   - 两元素池归属；
   - 句级监听清理；
   - 免提开麦时机。

### 3.4 文档

`docs/ARCHITECTURE.md` 里 `routers/voice.py` 那一行，补上两点：票据 150 秒有效；每个用户最多保留 64 张未过期票据，超出先淘汰自己最早的。
另外在全库搜索「票据有效期 60 秒」这一事实的其他现行陈述（`docs/tasks/` 下的历史任务文档除外）。如果找到，在报告里列出位置但**不要改**，因为它们不在白名单里；主会话会另行处理。

## 4. 任务清单

- **T1**：后端有效期 150 秒，每用户上限与淘汰（3.1）。
- **T2**：`test_tts_private_tickets.py` 那一行断言对齐新常量（第 0 节授权的唯一例外）。
- **T3**：新建 `backend/tests/test_tts_ticket_ttl.py`，至少覆盖：
  1. 默认 `TTS_TICKET_TTL_SECONDS == 150`；换票响应 `expires_in == 150`；票据的 `expires_at - time.monotonic()` 在 149–150 秒之间。
  2. 有效期在请求时读取：monkeypatch 成 5 后，新票 `expires_in == 5`。
  3. 票据在有效期内可用；把 `expires_at` 改到已过去后，`/tts/stream` 与 `/tts/synthesize` 返回 404。沿用现有测试直接改 `expires_at` 的做法，**不要**全局 monkeypatch `time.monotonic`，它会干扰事件循环。
  4. **每用户上限**：
     - 把上限调成 3，关掉限流；
     - 用户 A 连换 5 张：A 最早的 2 张被淘汰，用它们播放返回 404；最新 3 张可用；
     - 用户 B 事先换的票全部仍在、可用；
     - 被淘汰的票如果有预热任务，已被取消（可用 WebKit UA 加假合成验证）。
  5. **全局上限原逻辑不变**：把全局上限调小、每用户上限调大，多个用户换票超过全局上限时，按全局最早的顺序淘汰（与改动前相同）。
  6. 每用户上限在请求时读取（monkeypatch 生效）。
- **T4**：`ttsTicket.ts` 返回 `expiresInMs`（3.2）。
- **T5**：`page.tsx` 的到期时刻、统一判据、预取重换、「点此播放」重换（3.3）。
- **T6**：`ARCHITECTURE.md`（3.4）。
- **T7**：写 `03-report.md`，包括：
  - 改了哪些文件；
  - 与 3.1–3.4、T3 各条逐条对应；
  - 一张「点此播放」的状态转换表：够用 / 不够用两条路径，每一步的元素归属、队列内容、提示状态；
  - 5 节命令的实际输出与退出码；
  - 未决问题。

## 5. 验收

### 5.1 你来跑（报告里贴实际输出）

后端在 `backend/`：`PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。

| 命令 | 期望 |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_ttl.py` | 全部通过 |
| `PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider` | 全部通过；总数 = 1533 + 新增（基线 `dc5336a` 为 1533 passed） |

前端在仓库外副本里跑：

```bash
T=$(mktemp -d)/fe && rsync -a --exclude node_modules --exclude .next frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules"
```

| 命令 | 期望 |
|---|---|
| `npx tsc --noEmit` | 0 |
| `npx eslint` | 0 errors，warnings ≤ 26（基线 26） |
| `npm run build` | 0 |

仓库根目录：

| 命令 | 期望 |
|---|---|
| `git status --porcelain --untracked-files=all` | 只有白名单文件与本任务目录 |
| `git diff -- backend/tests/test_tts_private_tickets.py` | 只改了那一行断言 |
| `grep -n "TTS_PRELOAD_MAX_TICKET_AGE_MS\|ticketAt\b" frontend/app/page.tsx` | 0 行 |
| `grep -rn "tts/ticket" frontend/app frontend/lib` | 只在 `ttsTicket.ts` 里 1 处 |

### 5.2 Claude 在浏览器里实测（你不用跑）

环境：生产构建；后端 `DEV_MODE=0` + 临时库 + 假模型 + 假 TTS；无头 WebKit 与 Chromium。

为了缩短等待，一部分场景会把后端有效期临时调成 20 秒。前端按 `expires_in` 判断，自动跟着调整。

- **BL1（有效期 20 秒）**：第一次真实 `play()` 模拟为 `NotAllowedError` → 等 30 秒 → 点「点此播放」。
  - 5 句按序读完，0 次 `error`，被拦的那一句重新换过票。
  - 基线 `dc5336a` 在 Chromium 上应当丢这一句，用作正控。
- **BL2（默认 150 秒）**：同 BL1 但等 70 秒。票还够用，走直接播放路径，不重新换票。5 句按序读完。基线 `dc5336a` 上会丢。
- **BL3（默认 150 秒）**：同 BL1 但等 160 秒。重新换票，5 句按序读完。
- **S10'（有效期 20 秒）**：当前句限流等待，预取句先拿到票，等待超过 5 秒。预取句转为当前句时重换票，5 句按序读完，0 次 `error`。
- **回归**：
  - 本仓库已有的限流场景 S1–S9；
  - 朗读自动播放场景 A0 / A / B / C / D / F；
  - 无提示时，输入区截图与 `dc5336a` 逐字节相同。

---

## v1.1 更正（2026-09-30，机械验证发现，规格原文的漏洞）

**问题**：3.3 第 4 条「不够用」路径最后调用 `playNextInQueue()`，而它会**优先使用 `ttsPreloadRef.current` 里已预取的句子**。

- 预取句占着**已解锁**的元素时，不会被第一步放弃；
- 于是 `playNextInQueue` 先拿预取的第 2 句。它的票如果也不够用，会被放弃并把文本放回队头，插到第 1 句前面；够用的话就直接先播第 2 句。
- 实测（BL1，有效期 20 秒，等 30 秒）：两个引擎的结束顺序都是 [屋檐(2), 冬天(1), 街上, 早点, 阳光]，顺序颠倒。

**更正后的要求**（替换 3.3 第 4 条「不够用」路径的第 1–2 步，其余步骤不变）：

1. 把当前句从「当前」位置撤下：`ttsCurrentRef.current = null`，`ttsPlayingRef.current = false`。
2. 如果此时 `ttsPreloadRef.current` 仍有预取句（无论它的元素是否已解锁），也一并放弃：
   - 置空 `ttsPreloadRef`；
   - 把它的文本 `unshift` 回队头；
   - `releaseTtsAudio` 它。
3. 再 `ttsQueueRef.current.unshift(current.text)`，保证队列顺序是「被拦的当前句 → 原预取句 → 其余」。
4. 之后照原文继续：`releaseTtsAudio(current)` → `primeTtsAudio()` → `setTtsPlaybackBlocked(false)` → `playNextInQueue()`。

**验收补充**：BL1 / BL3 的结束顺序必须是 1→2→3→4→5，并且每句恰好出声一次。报告里写明你是如何确认顺序的（例如用状态表推演两种情形：预取句元素已解锁、未解锁）。

---

## v1.2 追加：复核可优化项——补强两条测试（2026-09-30，用户确认先补再合）

依据：`04-review.md`（Opus 5.5 多视角复核，结论通过）的可优化项 1、2。现有两条测试的场景是退化的，下面两类错误实现都能通过：

- 把「过期清理」与「每用户淘汰 / 全局淘汰」的先后写反；
- 全局淘汰改成优先淘汰调用者自己的票。

**实现一行都不改。**

### 白名单

- `backend/tests/test_tts_ticket_ttl.py`：只**追加**新测试，已有用例一字不改。
- 本目录 `03-report.md`：只在末尾追加「v1.2」一节。
- 除此之外一律不动。其余硬规则照旧。

### 要追加的测试（可以合并成参数化用例）

1. **每用户淘汰之前必须先做过期清理。**
   - 每用户上限设为 2，关掉限流。
   - 用户 A 依次签 a1、a2，把 a2 的 `expires_at` 改到过去，再签 a3。
   - 断言：表里 A 的票按顺序是 [a1, a3]，且 a1 仍可用。
   - 如果先淘汰、后清理，会得到 [a3]。
2. **全局淘汰之前必须先做过期清理。**
   - 全局上限设为 3，每用户上限设为 20。
   - 依次签 b1（用户 B）、a1（用户 A）、c1（用户 C），把 c1 设为过期，再由 A 签 a2。
   - 断言：表里按顺序是 [b1, a1, a2]，b1 没有被淘汰。
3. **全局淘汰只看全局最早，不偏向调用者自己的票。**
   - 全局上限设为 3，每用户上限设为 20。
   - 依次签 a1、b1、b2，再由 B 签 b3。
   - 断言：表里按顺序是 [b1, b2, b3]，被淘汰的是全局最早的 a1。
   - 如果优先淘汰调用者自己的票，会得到 [a1, b2, b3]。

### 自检（贴实际输出）

- 新文件全部通过；后端全量 = 1542 + 新增数。
- 变异自检：在**仓库外副本**里改 `voice.py`，**不要改仓库**。
  - 下面三种错误实现，都必须至少让一条新测试失败：
    - 每用户淘汰挪到过期清理之前；
    - 全局淘汰挪到过期清理之前；
    - 全局淘汰优先淘汰调用者自己的票。
  - 未变异的副本全部通过。

---

## v1.3 追加：再补一条跨用户公平测试（2026-09-30，用户确认补上再合）

依据：`04-review-v1.2.md` 的可优化项。「全局淘汰跳过调用者、优先淘汰别人的票」这种错误实现，现有 1545 条测试都拦不住，而这正是每用户上限要防的方向。

- **只在 `backend/tests/test_tts_ticket_ttl.py` 末尾追加一条测试**，已有用例与实现一字不改。本目录 `03-report.md` 只在末尾追加「v1.3」一节。
- **测试场景**：
  - 全局上限设为 3，每用户上限设为 20，关掉限流；
  - 依次签 a1（用户 A）、b1、b2（用户 B），再由 A 签 a2；
  - 断言表里按顺序是 [b1, b2, a2]；a1 播放返回 404；b1、b2、a2 返回 200。
- **自检**：
  - 在仓库外副本里把全局淘汰改成「优先淘汰非调用者最早的票」，新测试必须失败；未改动副本全部通过。
  - 后端全量应为 1546 passed。
