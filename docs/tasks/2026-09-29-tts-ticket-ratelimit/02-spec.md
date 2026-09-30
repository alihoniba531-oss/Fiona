# 朗读换票被限流后整段后半截静默 —— 修复规格（v1）

基线：`8c7f0cf`（main）。任务级别：L2（后端限流键与限额 + 前端朗读队列的 429 处理，不动数据模型）。
工作目录：本仓库根目录（一个基于 main 的 git worktree）。

## 0. 硬规则（违反任一条即返工）

- **不得修改任何已有测试的输入或断言**，不得删除或跳过已有测试。新增测试放进新文件。
- 不引入依赖，不改 `requirements*.txt`、`package.json`、lockfile。
- 不做真实网络调用（不调 DashScope、不下载任何东西）。
- 不运行 `next dev`（它会改写 `frontend/AGENTS.md`）。
- 不写 git 状态：不 commit、不 stash、不 checkout、不 reset。
- 不读 `.env*`，不碰任何 `*.db` 文件。
- 沙箱里起不了浏览器。浏览器实测由 Claude 在主会话里做，你**不要**尝试启动浏览器。
- 什么时候停下来问：只有当某件事会影响「实现什么」时才停下来，写进报告的「未决问题」；只影响「怎么验证」的事自己定。任何情况下都不要回滚已经完成的工作。
- 可以用多个 subagent 并行，但**按文件分工，同一个文件只交给一个 subagent**。建议分两路：后端（`backend/**`）一路，前端（`frontend/**`）一路。
- **允许修改的文件（白名单）**：
  - `backend/rate_limit.py`
  - `backend/routers/voice.py`
  - 新建 `backend/tests/test_tts_ticket_rate_limit.py`
  - 新建 `frontend/lib/ttsTicket.ts`
  - `frontend/app/page.tsx`
  - `docs/ARCHITECTURE.md`：只改 `routers/voice.py` 那一行里关于换票限流的描述
  - 本目录的 `03-report.md`
  - 除此之外一律不动。尤其不动 `backend/main.py`（全局 429 处理器保持原样）和其他路由的限流。

## 1. 背景

### 1.1 现在怎么坏的

- `backend/routers/voice.py` 的 `POST /tts/ticket` 挂着 `@limiter.limit("20/minute")`。`backend/rate_limit.py` 的 key 是 `_client_ip`，所以是**按客户端 IP** 每分钟 20 次。
- 前端 `frontend/app/page.tsx` 的朗读队列（`mkTtsAudio` / `tryPrefetch` / `playNextInQueue`，约 730–815 行）每一句先换一张票。换票响应 `!response.ok` 时 `ready` 得到 `false`，`playNextInQueue` 把这一句当成「已结束」，立刻推进到下一句。
- 被限流后，后面每一句的换票都立刻 429、立刻被跳过。实测剩下的句子在约 150ms 内全部被跳完，整段回复后半截没有声音，界面上没有任何提示。
- slowapi 默认 `headers_enabled=False`，现在的 429 响应**没有** `Retry-After` 头，body 是 `{"error": "Rate limit exceeded: 20 per 1 minute"}`。
- 同一个 NAT 出口（家里、办公室）下的所有用户共用这 20 次。

### 1.2 真实使用下的换票速率（限额依据）

模型脚本：本目录 `rate_model.py`（纯标准库，可复跑）。

- **语速实测**：2026-09-29 用 `backend/tts.synthesize`（cosyvoice-v2、`longxiaoxia_v2`、`speech_rate=1.15`）真实合成 8 句，用 ffprobe 量时长。
  - 结果：时长 ≈ 0.156 秒/字 × 字数 + 0.10 秒，最短一段约 0.45 秒（「嗯。」「1.」）。
  - 所以连续播放最多约 **385 字/分钟**。
- **切句**：按 `flushSentences`。首句碰逗号也切（至少 4 字）；之后只在 `。！？\n.!?；;` 切。编号列表的 `1.` 会被单独切成一段。
- **换票节奏**：前端只预取 1 句。回复开头换 2 张，此后每开始播放一句才预取下一句，所以换票速率被音频时长卡住，最多约等于每分钟播放的句数。

| 场景 | 段数 | 音频时长 | 任意 60 秒内换票峰值 | 任意 60 秒内字数峰值 |
|---|---|---|---|---|
| 日常短回复（28 字） | 3 | 6 秒 | 3 | 28 |
| 走心长回复（306 字） | 15 | 51 秒 | 15 | 306 |
| 顶格长回复（约 950 字，`max_tokens=700` 的上限附近） | 37 | 154 秒 | 16 | 395 |
| 分身模式编号列表（30 项） | 58 | 78 秒 | 47 | 352 |
| 碎句连发（病态：「嗯。对。是啊！」×69） | 69 | 47 秒 | 69（平均折合 89/分钟） | 222 |

- 另外，每次在朗读中途发新消息，旧回复最多浪费 2 张票（当前句 + 预取句），通常各几十字。
- **结论**：
  - 现在的 20 次/分钟，一条 300 字的长回复就会用掉 15 张；再接一条就会超。
  - 正常使用每分钟最多几十张票，字数不超过约 400 字/分钟。
  - 真正花钱的是**字数**：每张票最多合成 300 字，DashScope 按字符计费。今天按 IP 20 次/分钟，单个来源最多能烧 20 × 300 = 6000 字/分钟。

### 1.3 新限额（本规格定死，不要改数值）

四道闸，**全部同时满足才放行**，固定窗口 60 秒：

| 计数键 | 按次数 | 按字数 |
|---|---|---|
| 登录用户（鉴权依赖返回的用户名） | 120 次/分钟 | 2000 字/分钟 |
| 客户端 IP（沿用 `_client_ip`） | 240 次/分钟 | 6000 字/分钟 |

- 「字数」= `min(len(去掉首尾空白的 text), 300)`，就是实际会送去合成的字数（`tts.synthesize` 截到 300）。
- 用户闸是主闸：
  - 按次数：病态碎句的 89/分钟也放得过。
  - 按字数：约为播放上限的 5 倍，覆盖预取和打断浪费。
  - 单个账号最多只能烧 2000 字/分钟，比今天单个来源的 6000 字/分钟收紧到三分之一。
- IP 闸是宽松兜底，防同一来源开多个账号刷：
  - 字数上限与今天单 IP 的最坏情况相同（6000 字/分钟），不比今天松。
  - 同一出口约 15 个用户同时满速朗读才会碰到。

**2026-09-30 勘误**：这里的字数额度按换票计，不是按实际合成计。一张票最多可用 4 次（`TTS_MAX_TICKET_USES`），没有缓存的票每用一次都可能重新合成一次；WebKit 换票时的预热合成不计入使用次数，另算一次合成。固定窗口从首次计数起算，跨窗口时短时间内最多可拿到约 2 倍额度；`/tts/ws` 不受这套限流约束，这是旧问题，另行处理。因此「单账号最多 2000 字/分钟」是换票口径，实际合成的绝对上限更高；「比原来收紧」的比例结论仍然成立，因为基线同样受这些因素影响。

## 2. 目标

1. 正常使用（上表所有场景，包括病态碎句）不会被限流。
2. 同一 NAT 下不同用户的计数互不影响（在 IP 兜底以内）。
3. 被限流时，服务端告诉前端要等多久（`Retry-After` 头 + body 字段）。
4. 前端遇到 429 **不再跳句**：
   - 这一句等到可以再换票时重试；
   - 等待期间，如果当前该出声的正是这一句，在输入区上方显示一行提示和倒计时，并给出「不听了」；
   - 等完后从这一句接着往下读，不丢句、不乱序。
5. 其他失败（非 429 的换票失败、音频 `error`）保持现在的行为，不在本任务范围内。

## 3. 设计要求

### 3.1 后端：`backend/rate_limit.py`

新增一个通用的「多闸一次判定」函数，建议名 `check_and_hit(checks)`：

- **输入**：若干项 `(limit_string, identifiers, cost)`。
  - `limit_string` 如 `"2000/minute"`，用 `limits.parse` 解析；
  - `identifiers` 是字符串元组；
  - `cost` 是正整数。
- **判定方式**：
  - 用 slowapi 实例底层的 `limits` 策略对象 `limiter.limiter`（现有实例，固定窗口、内存存储），**先对所有项 `test(item, *identifiers, cost=cost)`**。
  - 有任何一项不通过：**一项都不计数**，返回需要等待的整数秒。取值为所有不通过项的 `get_window_stats(...).reset_time - time.time()` 的最大值，向上取整，下限 1。
  - 全部通过：才逐项 `hit(..., cost=cost)`，返回 `None`。
  - 函数内部在 test 和 hit 之间不得 `await`，保证在事件循环里是原子的。
- **总开关**：`limiter.enabled` 为 `False` 时，直接返回 `None`，不计数。现有很多测试靠这个关掉限流。
- **不改动**：`_client_ip`、`limiter` 的构造参数都不改。

### 3.2 后端：`backend/routers/voice.py` 的 `POST /tts/ticket`

- 删除 `@limiter.limit("20/minute")`，改为在处理函数里调用 3.1 的函数。
- **四个限额写成模块级常量**，例如：
  - `TTS_TICKET_USER_REQUESTS = "120/minute"`
  - `TTS_TICKET_USER_CHARS = "2000/minute"`
  - `TTS_TICKET_IP_REQUESTS = "240/minute"`
  - `TTS_TICKET_IP_CHARS = "6000/minute"`
  - 以及 `TTS_TICKET_MAX_CHARS = 300`
  - 要求：必须在**请求时**读取这些常量，不能在导入时固化，这样测试和验收环境可以 monkeypatch 调低。
- **identifiers 带命名空间**，保证四项互不串：
  - 例如 `("tts_ticket", "user", user, "count")`、`("tts_ticket", "user", user, "chars")`；
  - `("tts_ticket", "ip", ip, "count")`、`("tts_ticket", "ip", ip, "chars")`；
  - `user` 用 `get_current_user` 依赖返回的值，`ip` 用 `rate_limit._client_ip(request)`。
  - 按次数的项 `cost=1`；按字数的项 `cost=min(len(text), TTS_TICKET_MAX_CHARS)`。
- **顺序**：
  1. 鉴权失败（401）和请求体校验失败（422），在进入处理函数之前就返回，不计数。现状如此，保持即可。
  2. 空文本的 400 判断放在限流判定**之前**，空文本不计数。
  3. 然后做限流判定。
  4. 通过后才签发票据。被拒时**不签发**：票据表不变，不启动 WebKit 预热。
- **被拒时的响应**：
  - 状态码 `429`；
  - 响应头 `Retry-After: <n>`，n 为 3.1 返回的整数秒；
  - JSON body `{"detail": "朗读请求太频繁，请稍后再试", "retry_after": <n>}`，这里的 `n` 与头里的值相同。
- **日志**：被拒时打印一行，格式如 `[TTS限流] scope=user|ip kind=count|chars retry_after=n`（取第一项不通过的）。**不得**打印用户名、IP 或朗读文本。
- **其他逻辑一律不变**：票据 TTL、使用次数、缓存、WebKit 预热、`/tts/stream` 与 `/tts/synthesize`。

### 3.3 前端：新建 `frontend/lib/ttsTicket.ts`

纯 TypeScript 模块，不依赖 React。

- **`TtsBackoff` 类型**：`{ until: number }`，单位是 `Date.now()` 毫秒。
  - 含义：在 `until` 之前，**任何一句**都不发换票请求。
  - 页面持有一个共享实例（`useRef`）。当前句、预取句、下一条回复的句子共用它。
- **`retryAfterMs(response, body)`**：
  - 先读 `Retry-After` 头：
    - 整数秒；
    - 或 HTTP 日期，换算成距现在的毫秒；
    - 解析不了就忽略。
  - 再读 body 的 `retry_after`：有限非负数字，单位秒。
    - 桌面静态包是跨域直连后端，读不到非 CORS 安全名单里的响应头，所以必须有这条回退。
  - 都没有时用 5 秒。
  - 结果夹在 [1 秒, 60 秒] 之间。
- **`requestTtsTicket(options)`**，返回 `Promise<string | null>`。
  - 参数：`text`（已截到 300 字）、`signal: AbortSignal`、`backoff: TtsBackoff`、`isStale: () => boolean`、`onWait(until: number)`、`onWaitEnd()`。
  - 流程：
    1. 如果 `backoff.until > Date.now()`：调用 `onWait(backoff.until)`，可中止地等到那个时刻。
    2. 用 `apiFetch` 发请求。URL 为 `${API_BASE}/tts/ticket`，方法、请求头和 body 与现在完全一致：`{ text, voice: "longxiaoxia_v2", speech_rate: 1.15 }`，带上 `signal`。
    3. 每个 `await` 之后都检查 `signal.aborted || isStale()`。成立就返回 `null`，并且不再发任何请求。
    4. 状态码是 `429`：
       - 尝试读 JSON body，读失败就当没有 body；
       - 用 `retryAfterMs` 算出等待时长，令 `backoff.until = max(backoff.until, Date.now() + 等待时长)`；
       - 回到第 1 步，重试同一句。
    5. 其他非 ok：返回 `null`，保持现有的「跳过这句」语义。
    6. ok：解析出 `ticket`，是非空字符串就返回它，否则返回 `null`。
  - **等待的边界**：
    - 等待必须可中止：`signal` 中止时立即结束等待，并清掉定时器。
    - 不设重试次数上限。每次最多等 60 秒；用户随时可以「不听了」或发新消息来结束等待。
  - **`onWait` / `onWaitEnd` 的调用**：
    - 每次开始等待时调用 `onWait(until)`；
    - 这一句结束等待状态时恰好调用一次 `onWaitEnd()`，包括：拿到票、非 429 失败、中止；
    - 从没等过的请求不调用 `onWaitEnd()`。

### 3.4 前端：`frontend/app/page.tsx`

- **`mkTtsAudio`**：
  - 把现有的换票部分（`apiFetch` 到 `audio.src = …/tts/stream?ticket=…` 之前）换成调用 `requestTtsTicket`。
  - 拿到票据后的逻辑不变：设 `src`，然后 `load()`。
  - `isStale` 即现有的 `session !== ttsSessionRef.current`。
- **`PreparedTtsAudio`** 增加一个可变字段，如 `waitingUntil: number | null`，记录这一句是否正在限流等待。
- **提示的显示条件**：只有**当前句**（`ttsCurrentRef.current`）处于等待时才显示。
  - 预取句在等、而当前句正在出声时，不显示。
  - 当前句放完、轮到正在等待的预取句时，立刻显示，倒计时接着剩余时间走。
  - 用一个 React 状态驱动，如 `ttsWaitUntil: number | null`。以下时机要同步它：
    - `onWait` / `onWaitEnd`：如果是当前句；
    - `playNextInQueue` 选定新的当前句时：按它的 `waitingUntil` 设置；
    - 当前句结束时：清空；
    - `clearTtsQueue()`：清空。
- **倒计时**：
  - 提示可见时，每秒刷新一次；
  - 秒数 = `max(1, ceil((until - now) / 1000))`；
  - 提示不可见时，不留定时器。
- **提示界面**：
  - **位置**：底部 `footer` 里 `[data-chat-composer]` 容器的顶部，紧挨着现有的 `referenceUploadError` 那一行之前，处在同一层级。
  - **内容**：一行。左边文字「朗读限速中，{n} 秒后接着读」，右边一个按钮「不听了」。
  - **样式**：沿用同一套写法：
    - 容器：`mb-2 flex min-w-0 items-center gap-1 text-xs`；
    - 文字：`min-w-0 flex-1 text-muted-foreground`；
    - 按钮：`btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9`。
    - 只用 Tailwind 工具类，不新增颜色、渐变、阴影、大圆角卡片，不改 `globals.css`。
    - 390 宽下放得下，按钮不能被挤出屏幕。
  - **无障碍**：
    - 容器加 `role="status"`、`aria-live="polite"`。
    - 为避免读屏器每秒播报一次，倒计时数字所在的元素加 `aria-hidden="true"`，另放一段只给读屏器的固定文字「朗读限速中，稍后自动接着读」（`sr-only`）。
    - 按钮是真正的 `<button type="button">`。
    - 不自动抢焦点。
- **「不听了」**：
  - 停止这次回复的朗读：`clearTtsQueue()`，并且把当前会话号记为「已停止」，例如 `ttsStoppedSessionRef.current = ttsSessionRef.current`。
  - 这个回复后面还在流式到达的句子不再入队：在 `enqueueSpeech` 里判断。
  - 这个回复不会触发免提录音：在 `playNextInQueue` 的「队列空了 → 开始免提录音」分支加判断。
  - 不关闭「朗读」开关。
  - 下一次发送、「帮我读」都会让会话号自增，自然解除「已停止」。
  - 只有「不听了」会设置「已停止」，**不要**把这个标记放进 `clearTtsQueue()`，否则会改变卡片回复、报错等其他调用 `clearTtsQueue()` 的路径在免提模式下的行为。
- **共享退避**：
  - 页面上的 `TtsBackoff` 在 `clearTtsQueue()` 和「不听了」之后**保留**。服务器仍在限流，新回复的第一句也要等。
  - 页面卸载或切换账号时不需要特别处理。
- **必须保持不变**：
  - 原文只在 `POST /tts/ticket` 请求体里，`<audio>` 只用 `/tts/stream?ticket=…`；
  - 预取一句的节奏；
  - `normalizeForTTS` 和切句；
  - `enqueueSpeech` 的 `voiceOn` 守卫（新增的「已停止」判断之外）；
  - 「朗读」「免提」按钮的现有行为；
  - 没有 429 时的一切播放行为和布局。

### 3.5 文档

`docs/ARCHITECTURE.md` 里 `routers/voice.py` 那一行，补一句换票限流的现状：按用户与按 IP、按次数与按字数四道闸（写明数值），429 带 `Retry-After`。

## 4. 任务清单

- **T1**：`rate_limit.py` 的多闸判定函数（3.1）。
- **T2**：`/tts/ticket` 改用四道闸，429 响应格式，日志（3.2）。
- **T3**：新建后端测试 `backend/tests/test_tts_ticket_rate_limit.py`，至少覆盖下列各条。每个测试前后都 `limiter.reset()`，并清空 `voice._tts_tickets`。需要触发限流的测试，要显式 `monkeypatch.setattr(limiter, "enabled", True)`。
  1. **按用户计数、不按 IP**：
     - 把用户次数限额调成 3/minute，IP 限额保持宽松；
     - 同一 IP（同一 `X-Real-IP`）下用户 A 连换 3 张都是 200，第 4 张是 429；
     - 同一 IP 下用户 B 仍然是 200。
  2. **429 响应格式**：
     - `Retry-After` 头是 1–60 的整数；
     - body 的 `retry_after` 与头一致；
     - body 的 `detail` 是规定文案；
     - 被拒时 `voice._tts_tickets` 条目数不变。
  3. **按字数**：
     - 用户字数限额调成 700/minute；
     - 300 字票两张通过（600）；
     - 第三张 300 字的被拒；
     - 被拒之后，一张 100 字的票仍能通过（700）。这证明被拒的那次没有计数。
  4. **字数按 300 封顶**：一张 2000 字的票按 300 计。
  5. **IP 兜底**：
     - IP 次数限额调成 5/minute；
     - 同一 `X-Real-IP` 下 5 个不同用户各换 1 张都通过，第 6 个用户被拒；
     - 换一个 `X-Real-IP` 的用户通过。
  6. **一次都不多记**：
     - 用户次数已满而被拒时，IP 的次数和字数计数都不增加；
     - 用 `limiter.limiter.get_window_stats` 读剩余量来断言。
  7. **不计数的情况**：401（未登录）、空文本 400、422（超长或空字符串）都不消耗用户与 IP 计数。
  8. **总开关**：`limiter.enabled=False` 时不限流。
  9. **默认限额下，真实使用序列全部放行**（这是「不误伤」的回归测试，用默认常量，不 monkeypatch 限额）：
     - 同一用户在一个窗口内依次换票：
       - 本目录 `rate_model.py` 中「碎句连发」的 69 段；
       - 加「顶格长回复」的 37 段。
       - 可以直接 import 该脚本的 `chunks()`，或把段文本写进测试。
     - 全部 200。
  10. **防误配**：四个默认常量解析后，两道字数闸的额度都 ≥ `TTS_TICKET_MAX_CHARS`。否则单张 300 字票永远过不去。
- **T4**：新建 `frontend/lib/ttsTicket.ts`（3.3）。
- **T5**：`page.tsx` 接入：等待状态、提示、倒计时、「不听了」（3.4）。
- **T6**：更新 `docs/ARCHITECTURE.md`（3.5）。
- **T7**：写 `03-report.md`，包括：
  - 改了哪些文件；
  - 与 3.1–3.5、T3 各条的逐条对应；
  - 一张前端状态表：当前句 / 预取句在「换票中 → 限流等待 → 重试 → 拿到票 / 放弃」之间的转换，每条写明触发条件，以及提示显示与否；
  - 第 5.1 节自检命令的原样输出摘要；
  - 未决问题。

## 5. 验收

### 5.1 你来跑（全部要在报告里贴结果）

后端（在 `backend/` 目录。worktree 里没有虚拟环境，用主仓库的解释器）：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

| 命令 | 期望 |
|---|---|
| 新测试文件 | 全部通过，且测试数 ≥ 10 |
| 全量 | 全部通过，总数 = 1510 + 新增数；基线 `8c7f0cf` 为 1510 passed |

前端（在 `frontend/` 目录，`node_modules` 已装好）：

| 命令 | 期望 |
|---|---|
| `npx tsc --noEmit` | 退出码 0 |
| `npx eslint` | 0 errors，warnings ≤ 28（基线 28），不得新增 |
| `npm run build` | 退出码 0 |

仓库根目录：

| 命令 | 期望 |
|---|---|
| `git status --porcelain` | 只出现白名单里的文件，以及本任务目录 |
| `git diff --stat -- backend/main.py frontend/AGENTS.md` | 空 |
| `grep -n 'limiter.limit("20/minute")' backend/routers/voice.py` | 0 行 |
| `grep -rn "tts/ticket" frontend/app frontend/lib` | 只在 `frontend/lib/ttsTicket.ts` 里出现 1 处 |

### 5.2 Claude 在浏览器里实测（供你实现时对照，你不用跑）

测试环境：

- 生产构建（`next build` + `next start`），后端 `DEV_MODE=0`，使用临时库；
- 假模型每条回复 5 句，假 TTS 每句约 1 秒；
- 无头 WebKit 和 Chromium；
- 换票请求可以被测试脚本拦截，并按需返回 429。

场景：

- **S1 预取句被限流**：第 2 张票首次返回 `429 Retry-After: 3`。
  - 第 1 句放完后，提示出现，倒计时从 2–3 秒走到 1；
  - 等待结束后提示消失，5 句按顺序全部 `ended`，没有跳句；
  - 等待期间，任何一句都不发换票请求。
- **S2 首句被限流**：第 1 张票首次返回 429，且只在 body 里带 `retry_after: 2`，没有响应头。
  - 约 2 秒后开始出声，5 句全部 `ended`。
- **S3 缺省等待**：429 既没有头也没有 body。按 5 秒等待后继续。
- **S4「不听了」**：在提示出现时点「不听了」。
  - 提示消失，之后这条回复 0 次换票、0 次出声；
  - 朗读开关仍然开着；
  - 等退避结束后再发一条消息，新回复正常读完。
- **S5 等待中发新消息**：旧回复的剩余句子不再出声，也不再换票；新回复在退避结束后按顺序读完。
- **S6 真实限流端到端**：不拦截请求，把后端用户次数限额调到 4/minute。
  - 一条 5 句的回复里，第 5 句收到真实的 429，经 Next 代理，同源；
  - 提示显示真实的倒计时（不超过 60 秒）；
  - 窗口重置后第 5 句读出，5 句全部 `ended`。
- **S7 正控**：S1 的拦截在基线 `8c7f0cf` 构建上跑，应当复现「跳句、无提示」。用它证明测试确实能测出这个问题。
- **S8 无 429 时不变**：普通消息 5/5 `ended`，句间空档与基线同量级。不出现提示时，输入区截图与基线逐像素相同（WebKit/Chromium × 1280/390）。

---

## v2 追加：在「朗读自动播放修复」之上重接前端（2026-09-30）

### v2.0 现状

- main 已前进到 `61fc01f`（朗读自动播放修复）。它重写了朗读队列：两元素池 `TtsAudioSlot`、`PreparedTtsAudio { text, slot, audio, session, ready, controller, listeners, cancelled }`、`releaseTtsAudio`、`finishCurrentTts`、`playPreparedTts`、`stopTtsByUser`、`resumeBlockedTts`，以及输入区顶部常驻的 `<div role="status" aria-live="polite">`（里面是「浏览器拦下了自动朗读」提示）。
- 本分支已对齐到 `61fc01f`，并**原样**恢复了 v1 提交（`refs/fiona-baselines/tts-ratelimit-v1`，即 `67a569e`）中除 `page.tsx` 外的全部文件：后端、后端测试、`frontend/lib/ttsTicket.ts`、`docs/ARCHITECTURE.md`、本任务文档。这些文件已在暂存区，**一律不动**。
- 本轮只做一件事：把 v1 在 `page.tsx` 里的接入，按新队列的结构重新接上。v1 的接入写法可用 `git show refs/fiona-baselines/tts-ratelimit-v1 -- frontend/app/page.tsx` 查看（只读 git 命令允许），但**不要**照搬 v1 里已被新队列取代的部分（见 v2.2 第 6 条）。

### v2.1 白名单

- `frontend/app/page.tsx`
- 本目录 `03-report.md`：在末尾追加「v2 重接」一节，不改前文。
- 除此之外一律不动；第 0 节其余硬规则照旧有效。

### v2.2 重接要求

1. **引入与状态**：
   - 引入 `requestTtsTicket` 与 `type TtsBackoff`；
   - 新增 `ttsBackoffRef = useRef<TtsBackoff>({ until: 0 })`；
   - 新增 `ttsWaitUntil` / `ttsWaitNow` 两个状态，以及「`ttsWaitUntil` 非 null 时每秒刷新 `ttsWaitNow`、为 null 时不留定时器」的 effect（与 v1 相同）。
2. **`PreparedTtsAudio`** 增加 `waitingUntil: number | null`，`mkTtsAudio` 创建对象时为 `null`。
3. **`mkTtsAudio`**：在 `prepared.ready` 里，把「`apiFetch(${API}/tts/ticket …)` → `response.ok` → `response.json()` → 取 `data.ticket`」这一段换成 `requestTtsTicket`：
   - `text: text.slice(0, 300)`；
   - `signal: controller.signal`；
   - `backoff: ttsBackoffRef.current`；
   - `isStale: () => !canUse()`；
   - `onWait(until)`：设 `prepared.waitingUntil = until`，仅当 `ttsCurrentRef.current === prepared` 时同步提示状态（先刷新 `ttsWaitNow` 再设 `ttsWaitUntil`）；
   - `onWaitEnd()`：设 `prepared.waitingUntil = null`，仅当它是当前句时清空提示状态。
   - 拿到票据之后的迟到结果保护**逐字保留**现有写法：`if (!canUse() || !ticket) return false;` → 设 `slot.audio.src` → `if (!canUse()) return false;` → `slot.audio.load()`。
4. **提示状态的同步点**：
   - `playNextInQueue` 在 `ttsCurrentRef.current = prepared;` 之后，按 `prepared.waitingUntil` 设置提示状态；
   - `finishCurrentTts` 清空；
   - `clearTtsQueue` 清空。
   - 其他函数（`releaseTtsAudio`、`playPreparedTts`、`resumeBlockedTts`、`primeTtsAudio`）不需要为此改动。
5. **限速提示界面**：
   - 放在现有常驻的 `<div role="status" aria-live="polite">` **里面**，紧跟在「浏览器拦下了自动朗读」那一块之后。
   - 不再给限速提示单独加 `role="status"` / `aria-live`；常驻容器已经负责播报。
   - 其余与 v1 完全相同：
     - 容器 `mb-2 flex min-w-0 items-center gap-1 text-xs`；
     - 文字 `min-w-0 flex-1 text-muted-foreground`；
     - 可见文字「朗读限速中，{n} 秒后接着读」，这个元素加 `aria-hidden="true"`；
     - 另放 `sr-only` 固定文字「朗读限速中，稍后自动接着读」；
     - 按钮「不听了」，类名 `btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9`；
     - 秒数 = `max(1, ceil((ttsWaitUntil - ttsWaitNow) / 1000))`。
6. **「不听了」**直接用现有的 `stopTtsByUser`。**不要**新增停止函数、停止标记或守卫；`enqueueSpeech`、`playNextInQueue` 的免提分支、`clearTtsQueue` 维持 `61fc01f` 的写法。v1 的 `stopTtsForReply` 及其两处守卫不要带过来。
7. **朗读自动播放修复的全部行为不得改变**：两元素池与归属、手势解锁、被拒提示与「点此播放」、关朗读立即停止、句级监听清理、迟到写入保护、免提开麦时机。除上面列出的接入点外，不改任何一行已有代码。

### v2.3 验收（你来跑，报告里贴结果）

后端（在 `backend/`）：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

| 命令 | 期望 |
|---|---|
| 全量 | `1524 passed`（后端与 v1 相同，这里只是确认） |

前端（在仓库外副本里构建，避免产物进仓库）：

```bash
T=$(mktemp -d)/fe && rsync -a --exclude node_modules --exclude .next frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules"
```

注意：Turbopack 不接受指向副本外的 node_modules 软链，必须用 `cp -Rc` 克隆。然后在 `$T` 里执行：

| 命令 | 期望 |
|---|---|
| `npx tsc --noEmit` | 退出码 0 |
| `npx eslint` | 0 errors，warnings ≤ 26（`61fc01f` 实测基线 26） |
| `npm run build` | 退出码 0 |

仓库根目录：

| 命令 | 期望 |
|---|---|
| `git status --porcelain --untracked-files=all` | 暂存区为 v2.0 所列文件；工作区只多出 `frontend/app/page.tsx` 与本目录 `03-report.md` 的修改 |
| `git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend frontend/lib docs/ARCHITECTURE.md` | 空 |
| `grep -rn "tts/ticket" frontend/app frontend/lib` | 只在 `frontend/lib/ttsTicket.ts` 里 1 处 |
| `grep -n "stopTtsForReply" frontend/app/page.tsx` | 0 行 |
| `grep -c 'role="status"' frontend/app/page.tsx` | 与 `61fc01f` 相同（不新增） |

### v2.4 Claude 在浏览器里实测（你不用跑）

- 本任务 S1–S8。
- 朗读自动播放修复的 A0 / A / B / C / D / F。
- **新增交互场景 S9**：第 2 张票先 429（`Retry-After: 3`）；等到之后，第 2 句的第一次真实 `play()` 被模拟为 `NotAllowedError`。
  - 限速提示消失，「浏览器拦下了自动朗读」出现；
  - 点「点此播放」后，5 句按顺序读完；
  - 任何时刻最多只有一个元素在出声。

---

## v3 追加：复核可选项返修（2026-09-30，用户确认先修再合）

依据：`04-review-v2.md`（Opus 多视角复核，结论通过）里的三条可选项。本轮在 v2 工作区之上继续改。v2 已改好的 `frontend/app/page.tsx` 与 `03-report.md` 未提交，是本轮的起点。

### v3.1 白名单

- `frontend/app/page.tsx`：只做 v3.2 的 F1。
- `backend/tests/test_tts_ticket_rate_limit.py`：只**追加**测试（F2），不改、不删已有测试。
- 本文件 §1.3：只追加一段勘误（F3），不改原文。
- 本目录 `03-report.md`：在末尾追加「v3 返修」一节。
- 除此之外一律不动（后端源码、`frontend/lib/ttsTicket.ts`、`docs/ARCHITECTURE.md` 都不动）；第 0 节其余硬规则照旧。

### v3.2 返修项

**F1：预取句的票据超龄后重新换票（修复限流下的静默丢句）**

- **现象**（Chromium 实测 2/2 复现）：
  1. 当前句在限流等待中（最长 60 秒），预取的下一句已经拿到票。
  2. 轮到这一句时，票已超过后端 60 秒有效期（`TTS_TICKET_TTL_SECONDS`）。
  3. Chromium 开始播放时会重新请求 `/tts/stream`（`Cache-Control: no-store`），拿到 404，触发 `error`。
  4. `finishCurrentTts` 把这一句当作结束直接跳过，界面没有任何提示。
- **要求**：
  - `PreparedTtsAudio` 增加 `ticketAt: number | null`，初始为 `null`。在 `mkTtsAudio` 里拿到票、通过迟到结果保护、设置 `src` 的同一处，记为 `Date.now()`。
  - 新增模块级常量 `TTS_PRELOAD_MAX_TICKET_AGE_MS = 45_000`，并加注释说明：后端票据 60 秒过期，留出开始播放的余量；正常情况下预取票的年龄不超过上一句的播放时长，单句最长约 40 秒，所以正常流程不会触发重换。
  - `playNextInQueue` 取出 `ttsPreloadRef.current` 作为新当前句时，如果它的 `ticketAt !== null` 且 `Date.now() - ticketAt > TTS_PRELOAD_MAX_TICKET_AGE_MS`，就放弃这个预取，按下面顺序处理：
    1. `releaseTtsAudio(那个预取)`；
    2. `ttsQueueRef.current.unshift(它的 text)`；
    3. 走现有「没有预取时从队头 `mkTtsAudio`」的分支重新换票。遇到限流照常等待，并显示限速提示。
  - 与 `resumeBlockedTts` 放回队头的写法保持一致；不新增别的放弃路径。
- **不改变的行为**：
  - 正常流程里预取句照常直接接上，句间无空档；
  - 两元素池归属；
  - 迟到保护；
  - 被拒提示；
  - 「不听了」。

**F2：补两条后端测试**

- **F2a**：后一道闸拒绝时，前面的闸一项都不计。
  - 例如把用户字数调成 300/minute，先换一张 300 字票，第二张 300 字票会被用户字数闸拒绝。断言用户次数余量仍是 `额度 - 1`，IP 次数、IP 字数余量也没有因第二张而减少。
  - 再构造一个由 IP 闸（排在最后）拒绝的情形，断言两道用户闸都没有计数。
  - 这两条都必须能让「按顺序逐项 test、通过就立刻 hit」的错误实现失败。在报告里写明你是怎么验证这一点的：临时改动后跑测试、确认失败，再还原；**不要把错误实现留在仓库里**。
- **F2b**：`retry_after` 取所有不通过项中最晚重置时间，向上取整，下限 1。
  - 至少覆盖三种情况：两项同时不通过、重置时间不同时取较大值；小数秒向上取整；已过去的重置时间给 1。
  - 可以 monkeypatch `limiter.limiter.get_window_stats` 或时间函数来控制重置时间。

**F3：§1.3 费用上限表述勘误**

在 §1.3 末尾追加一段，标明「2026-09-30 勘误」，写清：

- 这里的字数额度是按换票计的，不是按实际合成计。
- 一张票最多可用 4 次（`TTS_MAX_TICKET_USES`），没缓存的票每用一次都可能重新合成一次。
- 固定窗口从首次计数起算，跨窗口时短时间内最多可拿到约 2 倍额度。
- `/tts/ws` 不受这套限流约束（旧问题，另行处理）。
- 所以「单账号最多 2000 字/分钟」是换票口径，实际合成的绝对上限更高；「比原来收紧」的比例结论仍然成立，因为基线同样受这些因素影响。

### v3.3 验收（你来跑，报告里贴结果）

| 命令 | 期望 |
|---|---|
| 新测试文件 | 全部通过，数量 = 14 + 新增 |
| 后端全量 | 全部通过，数量 = 1524 + 新增 |
| `npx tsc --noEmit`（仓库外副本） | 0 |
| `npx eslint` | 0 errors，warnings ≤ 26 |
| `npm run build`（仓库外副本，用 `cp -Rc` 克隆 node_modules） | 0 |
| `git status --porcelain --untracked-files=all` | 相对暂存区只改了白名单文件 |
| `git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend/rate_limit.py backend/routers/voice.py frontend/lib docs/ARCHITECTURE.md` | 空 |

### v3.4 Claude 在浏览器里实测（你不用跑）

- **新增 S10**：拦截换票请求。第 1 句第 1 次返回 `429 Retry-After: 3`；第 2 次延迟 0.4 秒后返回 `429 Retry-After: 60`；其余放行。这样第 2 句作为预取句会先拿到票，然后等当前句约 60 秒。
  - v2 上 Chromium 实测丢第 2 句：结束顺序为 [1,3,4,5]，第 2 句触发 `error`。
  - 修后要求两个引擎都 5 句按序读完、0 次 `error`；等待期间显示限速提示。
- 回归：S1–S9、朗读自动播放 A0/A/B/C/D/F；无提示时输入区截图与 `61fc01f` 逐字节相同。
