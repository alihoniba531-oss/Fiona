# 朗读换票限流修复报告

基线：8c7f0cf。实现遵守 02-spec.md 第 0 节：未修改已有测试、依赖清单、backend/main.py、frontend/AGENTS.md 或其他白名单外的工作树文件；未调用真实网络，未启动浏览器或 next dev，未读 .env 文件或手动操作数据库文件，未写 git 状态。

## 变更文件与功能

| 文件 | 变更 |
|---|---|
| backend/rate_limit.py | 新增固定窗口多闸先检查、全通过再计数的 check_and_hit；限流总开关关闭时直接放行。 |
| backend/routers/voice.py | 换票改为用户/IP × 次数/字数四闸；拒绝时给出 429、Retry-After、同值 JSON 字段与不含隐私的日志；拒绝发生在签票和 WebKit 预热之前。 |
| backend/tests/test_tts_ticket_rate_limit.py | 新增 14 个独立测试用例，覆盖 T3.1–T3.10 和通用多闸不多记。 |
| frontend/lib/ttsTicket.ts | 新增共享退避、Retry-After 解析、可中止等待和同一句无限次 429 重试。 |
| frontend/app/page.tsx | 将换票接入新模块；当前句等待时显示倒计时与“不听了”；停止标记阻止该回复后续入队和免提回录，保留共享退避。 |
| docs/ARCHITECTURE.md | 仅修改 routers/voice.py 一行，写入四个数值和 429 的 Retry-After。 |
| docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md | 本报告。 |

## 规格逐项对应

| 条目 | 实现与验证 |
|---|---|
| 3.1 / T1 | check_and_hit 使用 limits.parse；先对所有闸 test，失败时不计数，取所有失败闸最大 reset_time 向上取整、至少 1 秒；全部通过才逐闸 hit；函数内无 await；enabled=False 直接放行。可选同步拒绝回调记录原判定的首个失败闸。 |
| 3.2 / T2 | 请求时读取 120/2000（用户）及 240/6000（IP）四个常量；使用带命名空间的键、各自的 1 次或截到 300 字成本。鉴权/422 在处理函数前结束，strip 后空文本 400 先于计数。429 头和 body 共用同一整数；拒绝不签票、不预热。TTL、票据使用次数、缓存和其他 TTS 路由未改。 |
| T3 | 新建 14 个测试用例，以下逐条对应 T3.1–T3.10；每个测试前后重置限流器并清空票据表。 |
| 3.3 / T4 | retryAfterMs 优先读整数秒或 HTTP 日期头，其次读有限非负数 body，缺省 5 秒并夹到 1–60 秒；requestTtsTicket 共享 backoff，逐个 await 后核查取消/旧会话，429 等待后重试原句，其他失败返回 null；可中止定时器；曾等待的句子结束时仅调用一次 onWaitEnd。 |
| 3.4 / T5 | 当前句和预取句共用 backoff；waitingUntil 只在当前句对应的 React 状态中呈现。预取句变当前句立即显示余时；等待提示在 composer 顶部，按指定类名与无障碍属性实现。“不听了”清队列且只标记当前会话；该会话后续句不入队、不触发免提。无 429 路径、切句、预取节奏和 stream 票据 URL 保持原样。 |
| 3.5 / T6 | 架构文档的 voice 行新增四闸限额和 Retry-After 说明。 |
| T7 | 本报告列出文件、功能、任务对应、前端状态表、5.1 实际自检输出和未决事项。 |

### T3 后端新增测试对应

每个新增测试（含参数化用例）前后，autouse fixture 都调用 limiter.reset() 并在票据锁下清空 voice._tts_tickets；需要实际触发限流的测试显式设置 limiter.enabled=True。

| 子项 | 新测试中的断言 |
|---|---|
| T3.1 | 用户次数改为 3/minute；同 IP 的 A 前 3 张 200、第 4 张 429，B 仍 200。 |
| T3.2 | Retry-After 是 1–60 的整数，body 两字段精确匹配；拒绝不增加票据数、不预热，日志不含用户/IP/文本。 |
| T3.3 | 用户字数改为 700/minute；300+300 放行、第三张 300 被拒，余量仍 100，随后 100 放行。 |
| T3.4 | 一张实际 2000 字文本获票，表中保存 2000 字，字数闸只扣 300。 |
| T3.5 | IP 次数改为 5/minute；同 IP 5 个用户放行，第 6 个被拒，换 IP 放行。 |
| T3.6 | 用户次数满后被拒；get_window_stats 证实 IP 次数与字数余量都不变。 |
| T3.7 | 401、strip 后空文本 400、空字符串 422、超长 422 四种用例均断言用户/IP 两类次数和字数闸不计数。 |
| T3.8 | enabled=False 下超过调低的用户/IP 次数闸仍连续放行，计数不变。 |
| T3.9 | 用 rate_model.py 的碎句 69 段接顶格长回复 37 段，同一窗口按默认限额共 106 张全部 200。 |
| T3.10 | limits.parse 后断言两道默认字数闸额度均不少于 300。 |
| 补充 | 通用 check_and_hit 首闸拒绝后，后续闸余量不变。 |

## 前端状态转换

| 当前句 | 预取句 | 触发及转换 | 提示 |
|---|---|---|---|
| 换票中 | 尚无或换票中 | 新句入队，当前句与最多一句预取句各自开始换票。 | 不显示。 |
| 限流等待 | 任意 | 当前句收到 429，写入共享 backoff，等待 Retry-After 后重试同一句；重复 429 继续等。 | 显示当前句剩余秒数及“不听了”。 |
| 正在出声 | 限流等待 | 预取句收到 429，记录该句 waitingUntil；当前句继续播。 | 不显示。 |
| 已结束 | 限流等待 → 当前句限流等待 | 当前句 ended，等待中的预取句成为当前句，立即按 waitingUntil 显示余时。 | 显示。 |
| 限流等待 → 重试中 | 任意 | 定时器到期，重新检查共享 backoff；仍受限则继续等待，否则重发同一句。 | 直到拿票或放弃都显示；倒计时下限 1 秒。 |
| 换票中或重试中 → 拿到票 | 任意 | 返回非空 ticket；onWaitEnd 清等待，给 audio 设置 /tts/stream?ticket=… 并 load、play。 | 不显示。 |
| 换票中或重试中 → 放弃此句 | 任意 | 非 429 失败、无效 ticket 或 audio error，沿用原队列跳过该句。 | 当前句等待状态清空。 |
| 任意 → 取消本回复 | 任意 | 点“不听了”或发送新消息时中止请求/定时器并清队列；仅“不听了”标记当前会话，阻止流式后续句和免提。共享 backoff 保留供新回复使用。 | 清空。 |

## 第 5.1 节自检

后端命令在工作树 backend/ 执行。前端原样命令在 /private/tmp/tts-ratelimit-qa.WFxDG5/frontend 隔离副本中执行：复制前端文件时排除了 .env*、*.db、.next 和构建缓存，node_modules 也在临时目录中完整复制，避免验收命令生成的 tsbuildinfo/.next 触碰白名单外工作树文件。仓库根命令在工作树根目录执行。

### 后端（最终代码）

解释器为 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python；两条命令均设置 PYTHONDONTWRITEBYTECODE=1，且禁用 pytest 缓存。命令写成解释器绝对路径，等价于规格里的 PY 变量。

1. `PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py`。退出码：0。实际输出：

```text
..............                                                           [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
14 passed, 11 warnings in 1.14s
```

2. `PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider`。退出码：0。实际输出：

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 28%]
........................................................................ [ 33%]
........................................................................ [ 37%]
........................................................................ [ 42%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 56%]
........................................................................ [ 61%]
........................................................................ [ 66%]
........................................................................ [ 70%]
........................................................................ [ 75%]
........................................................................ [ 80%]
........................................................................ [ 85%]
........................................................................ [ 89%]
........................................................................ [ 94%]
........................................................................ [ 99%]
............                                                             [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1524 passed, 11 warnings in 54.39s
```

14 个新增用例达到至少 10 个的要求；全量 1524 = 基线 1510 + 新增 14。

### 前端（隔离副本）

1. `npx tsc --noEmit`。退出码：0。实际输出：空。

2. `npx eslint`。退出码：0。实际输出：

```text

/private/tmp/tts-ratelimit-qa.WFxDG5/frontend/app/page.tsx
    86:10   warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   177:7    warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   335:10   warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   380:9    warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   381:9    warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   382:9    warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   392:10   warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   393:10   warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   394:10   warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   395:10   warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   398:10   warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   404:10   warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   405:10   warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   659:20   warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   663:16   warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   734:18   warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   905:81   warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   911:108  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   979:9    warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   999:9    warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1007:9    warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1028:9    warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1064:9    warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1160:9    warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1504) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1603:9    warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1643:9    warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  1865:25   warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/tmp/tts-ratelimit-qa.WFxDG5/frontend/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 28 problems (0 errors, 28 warnings)

```

汇总为 0 errors、28 warnings，与基线 28 相同。

3. `npm run build`。最终重跑退出码：0。实际输出：

```text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.3 (Turbopack)
✓ Running next.config.ts took 938ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:40059) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 2.0s
  Running TypeScript ...
  Finished TypeScript in 2.2s ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) 
  Generating static pages using 16 workers (6/14) 
  Generating static pages using 16 workers (10/14) 
✓ Generating static pages using 16 workers (14/14) in 325ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ƒ /agents/[id]
├ ○ /agents/me
├ ○ /community
├ ○ /history
├ ○ /login
├ ○ /manifest.webmanifest
├ ○ /match
├ ○ /plaza
├ ○ /profile
└ ○ /settings


ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand

```

首次在同一隔离副本执行时，node_modules 是指向工作树的符号链接，Turbopack 拒绝跨根目录链接；该次退出码 1，实际错误行为：

```text
Error [TurbopackInternalError]: Symlink [project]/node_modules is invalid, it points out of the filesystem root
```

将 node_modules 完整复制到隔离副本后，以上原样命令通过。

### 仓库根目录

1. `git status --porcelain`。退出码：0。实际输出：

```text
 M backend/rate_limit.py
 M backend/routers/voice.py
 M docs/ARCHITECTURE.md
 M frontend/app/page.tsx
?? backend/tests/test_tts_ticket_rate_limit.py
?? docs/tasks/2026-09-29-tts-ticket-ratelimit/
?? frontend/lib/ttsTicket.ts
```

其中任务目录原有的 02-spec.md 和 rate_model.py 未改，本报告是新增文件；用 `git status --porcelain -uall` 核对了目录内文件，均在任务目录内。

2. `git diff --stat -- backend/main.py frontend/AGENTS.md`。退出码：0。实际输出：空。

3. `grep -n 'limiter.limit("20/minute")' backend/routers/voice.py`。退出码：1。实际输出：空（grep 无匹配时按约定退出 1）。

4. `grep -rn "tts/ticket" frontend/app frontend/lib`。退出码：0。实际输出：

```text
frontend/lib/ttsTicket.ts:76:      const response = await apiFetch(`${API_BASE}/tts/ticket`, {
```

附加检查 `git diff --check` 退出码 0，输出为空。

## 未完成与人工确认

- 浏览器实测 S1–S8 按规格由 Claude 主会话完成；本 worktree 没有启动浏览器，因此尚未确认真实浏览器中的提示、顺序、390 宽布局或基线逐像素对比。
- 实现范围内没有未决问题。临时副本第一次构建因 node_modules 跨目录符号链接被 Turbopack 拒绝；复制依赖到临时副本后，原样 npm run build 通过。这是隔离验证布置问题，已在上方记录两次实际输出。

## 第 1 轮返修

- 改动：仅在 backend/routers/voice.py 的 log_rejection 中给 print 增加 flush=True，使 stdout 指向文件或管道时也立即写出限流日志。
- 测试目录：backend/。
- 命令：`PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py`
- 退出码：0。
- 实际输出：

```text
..............                                                           [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
14 passed, 11 warnings in 0.81s
```

## v2 重接

### 修改范围与 v2.2 对应

本轮只修改 frontend/app/page.tsx，并在本报告末尾追加本节；其余暂存文件未改，没有执行 git 写操作。

| v2.2 | 对应实现 |
|---|---|
| 1 | page.tsx:19 引入 requestTtsTicket / TtsBackoff；388–389 增加等待状态；415 增加页面共享退避 ref；426–430 的 effect 仅在提示可见时每秒更新，清理 interval。 |
| 2 | page.tsx:79 给 PreparedTtsAudio 增加 waitingUntil；849 初始化为 null。 |
| 3 | page.tsx:856–883 的 prepared.ready 调用 requestTtsTicket，传入截断文本、signal、共享退避及基于 canUse 的迟到保护；onWait / onWaitEnd 维护句级字段并仅同步当前句。拿票后的 canUse → src → canUse → load 顺序保留。 |
| 4 | page.tsx:900、962–963、1037 分别在当前句结束、选定新当前句、清空队列时同步或清除提示。预取句等待时只记录字段。 |
| 5 | page.tsx:2024–2030 把限速提示放进现有常驻 status 容器，并紧跟自动播放被拒提示；使用指定样式、倒计时、aria-hidden 数字与固定 sr-only 文案，未新增 role=status。 |
| 6 | page.tsx:2029 的「不听了」直接调用现有 stopTtsByUser；没有新增停止函数、标记或守卫，原有入队、免提和清队列逻辑保持。 |
| 7 | 除上述接入点外，双元素池、手势解锁、被拒提示与重播、句级监听、迟到写入保护、关朗读与免提行为均未改。 |

### v2.3 验收命令与实际输出

后端目录执行：

~~~text
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
~~~

退出码 0。实际输出的结果与警告部分：

~~~text
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1524 passed, 11 warnings in 50.52s
~~~

pytest 进度输出为 4% 至 100% 的点阵；最终结果为 1524 passed。

仓库根目录执行前端隔离副本准备：

~~~text
T=$(mktemp -d)/fe && rsync -a --exclude node_modules --exclude .next frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules"
~~~

退出码 0；rsync 和 cp 标准输出为空。为后续命令记录的副本路径是 /var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.6v9aqxJMOb/fe（执行包装器输出：T=/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.6v9aqxJMOb/fe）。

在该副本中执行 npx tsc --noEmit：退出码 0，实际输出为空。

在该副本中执行 npx eslint：退出码 0。实际输出的诊断行如下（省略终端用于列对齐的空格）：

~~~text
/private/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.6v9aqxJMOb/fe/app/page.tsx
126:10 warning 'MiniCloudCard' is defined but never used @typescript-eslint/no-unused-vars
217:7 warning 'DEMO_MESSAGES' is assigned a value but never used @typescript-eslint/no-unused-vars
375:10 warning 'allUsers' is assigned a value but never used @typescript-eslint/no-unused-vars
421:9 warning 'nlsWsRef' is assigned a value but never used @typescript-eslint/no-unused-vars
422:9 warning 'mediaRecorderRef' is assigned a value but never used @typescript-eslint/no-unused-vars
423:9 warning 'audioCtxRef' is assigned a value but never used @typescript-eslint/no-unused-vars
433:10 warning 'peerRooms' is assigned a value but never used @typescript-eslint/no-unused-vars
434:10 warning 'activePeer' is assigned a value but never used @typescript-eslint/no-unused-vars
435:10 warning 'pendingMatches' is assigned a value but never used @typescript-eslint/no-unused-vars
436:10 warning 'cardPositions' is assigned a value but never used @typescript-eslint/no-unused-vars
439:10 warning 'peerConnected' is assigned a value but never used @typescript-eslint/no-unused-vars
445:10 warning 'myGender' is assigned a value but never used @typescript-eslint/no-unused-vars
446:10 warning 'matchPref' is assigned a value but never used @typescript-eslint/no-unused-vars
700:20 warning '_' is defined but never used @typescript-eslint/no-unused-vars
704:16 warning '_' is defined but never used @typescript-eslint/no-unused-vars
775:18 warning '_' is defined but never used @typescript-eslint/no-unused-vars
1149:9 warning 'saveUserSettings' is assigned a value but never used @typescript-eslint/no-unused-vars
1169:9 warning 'handleCardExpire' is assigned a value but never used @typescript-eslint/no-unused-vars
1177:9 warning 'handleAcceptCard' is assigned a value but never used @typescript-eslint/no-unused-vars
1198:9 warning 'handleSkipCard' is assigned a value but never used @typescript-eslint/no-unused-vars
1235:9 warning 'handleClearChat' is assigned a value but never used @typescript-eslint/no-unused-vars
1331:9 warning The 'handleSend' function makes the dependencies of useEffect Hook (at line 1675) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook react-hooks/exhaustive-deps
1774:9 warning 'openPeerChat' is assigned a value but never used @typescript-eslint/no-unused-vars
1814:9 warning 'handlePeerKeyDown' is assigned a value but never used @typescript-eslint/no-unused-vars
2057:25 warning Using <img> could result in slower LCP and higher bandwidth. Consider using <Image /> from next/image or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element @next/next/no-img-element
/private/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.6v9aqxJMOb/fe/app/plaza/page.tsx
610:21 warning Using <img> could result in slower LCP and higher bandwidth. Consider using <Image /> from next/image or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element @next/next/no-img-element
✖ 26 problems (0 errors, 26 warnings)
~~~

在该副本中执行 npm run build：退出码 0。实际输出：

~~~text
> frontend@0.1.0 build
> next build
▲ Next.js 16.3.3 (Turbopack)
✓ Running next.config.ts took 717ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"
  Creating an optimized production build ...
(node:83734) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 1897ms
  Running TypeScript ...
  Finished TypeScript in 2.2s ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) ...
  Generating static pages using 16 workers (6/14) ...
  Generating static pages using 16 workers (10/14) ...
✓ Generating static pages using 16 workers (14/14) in 292ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ƒ /agents/[id]
├ ○ /agents/me
├ ○ /community
├ ○ /history
├ ○ /login
├ ○ /manifest.webmanifest
├ ○ /match
├ ○ /plaza
├ ○ /profile
└ ○ /settings

ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
~~~

仓库根目录只读检查：

| 命令 | 退出码 | 实际输出 |
|---|---:|---|
| git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend frontend/lib docs/ARCHITECTURE.md | 0 | 空 |
| grep -rn "tts/ticket" frontend/app frontend/lib | 0 | frontend/lib/ttsTicket.ts:76:      const response = await apiFetch(`${API_BASE}/tts/ticket`, { |
| grep -n "stopTtsForReply" frontend/app/page.tsx | 1 | 空（无匹配） |
| grep -c 'role="status"' frontend/app/page.tsx | 0 | 7；只读对照 61fc01f 也是 7 |

git status --porcelain --untracked-files=all 的最终结果在本节末尾单列，确保包含报告自身本次追加后的状态。

### 未完成或人工确认

浏览器实测 S1–S9 与朗读自动播放修复的 A0 / A / B / C / D / F 按 v2.4 由 Claude 主会话完成；本轮按第 0 节没有启动浏览器。实现范围内无未决问题。

### 最终 git 状态

在仓库根目录执行 git status --porcelain --untracked-files=all：退出码 0。实际输出：

~~~text
M  backend/rate_limit.py
M  backend/routers/voice.py
A  backend/tests/test_tts_ticket_rate_limit.py
M  docs/ARCHITECTURE.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/02-spec.md
AM docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/03-verification.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/04-review.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/chromium-1280-notice-footer.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/chromium-390-notice-page.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/webkit-1280-notice-footer.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/webkit-390-notice-page.png
 M frontend/app/page.tsx
A  frontend/lib/ttsTicket.ts
~~~


## v3 返修

本轮以暂存区为基线，只执行 v3.2 的 F1、F2、F3。除 F2 的受控临时错误实现验证外，仅改动 v3.1 四个白名单文件；临时源码已逐字节还原，没有执行 git 写操作。下列输出仅剔除行尾空白，原始日志保留在 `/private/tmp/tts-v3-evidence/` 和 `/private/tmp/tts-v3-f2-*.log`。

### 文件位置与 F1 / F2 / F3 对应

| 项目 | 文件与位置 | 实现与证据 |
|---|---|---|
| F1 | `frontend/app/page.tsx:80`、90–92、854、880、953–958、983 | 增加并初始化 `ticketAt`，拿票且通过迟到保护、设置 `src` 时记录 `Date.now()`；定义 45 秒阈值及后端 60 秒 TTL/正常单句约 40 秒的注释。取出预取句时，超龄则依次 `releaseTtsAudio`、`unshift(prepared.text)`、置空局部变量，进入既有 `mkTtsAudio` 分支重换；补充回调依赖。原有池归属、迟到保护、自动播放被拒提示与停止逻辑未改。 |
| F2a | `backend/tests/test_tts_ticket_rate_limit.py:203`、229 | 新增用户字数第二闸拒绝与 IP 字数最后闸拒绝两个场景，比较拒绝前后的四道闸余量。两条在临时逐项 `test`/立即 `hit` 的错误实现下均失败，恢复后通过。 |
| F2b | 同文件 255–294（测试函数 264） | 参数化新增 3 个用例：失败重置偏移 `(2.0, 9.0)` 得 9；`(1.25, 2.01)` 向上取整得 3；`(-10.0, -0.25)` 得下限 1。额外通过项的重置偏移为 999，验证它不参与失败项最大值计算；拒绝时没有 `hit`。 |
| F3 | `02-spec.md:79`，§1.3 末尾 | 只追加一段「2026-09-30 勘误」：字数是换票口径；每票最多使用 4 次且无缓存可能再次合成；固定窗口跨界短时约 2 倍额度；`/tts/ws` 不受约束；实际合成绝对上限更高，相对基线收紧的比例仍成立。 |
| 报告 | `03-report.md:457` 起 | 只在末尾追加本「v3 返修」节，记录变异、恢复、验收实际输出、范围审计与待人工实测项。 |

新增测试数为 5（F2a 两条，F2b 三个参数化实例），文件总数 `14 + 5 = 19`，后端全量 `1524 + 5 = 1529`。原测试 8252 字节仍是完整前缀，原报告全文仍是完整前缀，规格删除本次新增勘误段后与起点逐字节相同。

### F2 错误实现验证与恢复

验证采用单个外部脚本的 `try/finally`：先保存 `backend/rate_limit.py` 原始字节；把「全部 test 完再 hit」临时改为下面的错误循环，并移除原来最后的统一 hit 循环；仅运行两个新 F2a；无论测试退出码如何，`finally` 都用保存的原始字节还原源码。

~~~python
failed = []
for item, identifiers, cost in parsed:
    if limiter.limiter.test(item, *identifiers, cost=cost):
        limiter.limiter.hit(item, *identifiers, cost=cost)
    else:
        failed.append((item, identifiers))
~~~

余量元组依次是「用户次数、用户字数、IP 次数、IP 字数」。错误实现下，用户字数第二闸拒绝后的实际值为 `(118, 0, 238, 5400)`，应为 `(119, 0, 239, 5700)`；IP 字数最后闸拒绝后的实际值为 `(118, 1400, 238, 0)`，应为 `(119, 1700, 239, 0)`。两个断言都失败，证明新增测试会发现先计数再遇到拒绝的问题。

#### 变异前：新测试文件

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

退出码：0。实际输出：

~~~text
...................                                                      [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 11 warnings in 1.16s
~~~

#### 错误实现：只运行两个 F2a

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py -k 'user_char_gate_rejection or last_ip_char_gate_rejection'
~~~

退出码：1。实际输出：

~~~text
FF                                                                       [100%]
=================================== FAILURES ===================================
___ test_user_char_gate_rejection_preserves_earlier_user_and_both_ip_quotas ____

client = <starlette.testclient.TestClient object at 0x10d590c20>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10baf6b10>

    def test_user_char_gate_rejection_preserves_earlier_user_and_both_ip_quotas(client, monkeypatch):
        monkeypatch.setattr(limiter, "enabled", True)
        monkeypatch.setattr(voice, "TTS_TICKET_USER_CHARS", "300/minute")
        assert _ticket(client, "字" * 300).status_code == 200
        before = (
            _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
            _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
            _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
            _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
        )
        assert before == (
            parse(voice.TTS_TICKET_USER_REQUESTS).amount - 1,
            0,
            parse(voice.TTS_TICKET_IP_REQUESTS).amount - 1,
            parse(voice.TTS_TICKET_IP_CHARS).amount - 300,
        )

        assert _ticket(client, "字" * 300).status_code == 429
>       assert (
            _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
            _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
            _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
            _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
        ) == before
E       assert (118, 0, 238, 5400) == (119, 0, 239, 5700)
E
E         At index 0 diff: 118 != 119
E         Use -v to get more diff

tests/test_tts_ticket_rate_limit.py:221: AssertionError
----------------------------- Captured stdout call -----------------------------
[TTS限流] scope=user kind=chars retry_after=60
__ test_last_ip_char_gate_rejection_preserves_both_user_and_earlier_ip_quotas __

client = <starlette.testclient.TestClient object at 0x10d04e350>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d5c02b0>

    def test_last_ip_char_gate_rejection_preserves_both_user_and_earlier_ip_quotas(client, monkeypatch):
        monkeypatch.setattr(limiter, "enabled", True)
        monkeypatch.setattr(voice, "TTS_TICKET_IP_CHARS", "300/minute")
        assert _ticket(client, "字" * 300).status_code == 200
        before = (
            _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
            _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
            _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
            _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
        )
        assert before == (
            parse(voice.TTS_TICKET_USER_REQUESTS).amount - 1,
            parse(voice.TTS_TICKET_USER_CHARS).amount - 300,
            parse(voice.TTS_TICKET_IP_REQUESTS).amount - 1,
            0,
        )

        assert _ticket(client, "字" * 300).status_code == 429
>       assert (
            _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
            _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
            _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
            _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
        ) == before
E       assert (118, 1400, 238, 0) == (119, 1700, 239, 0)
E
E         At index 0 diff: 118 != 119
E         Use -v to get more diff

tests/test_tts_ticket_rate_limit.py:247: AssertionError
----------------------------- Captured stdout call -----------------------------
[TTS限流] scope=ip kind=chars retry_after=60
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_char_gate_rejection_preserves_earlier_user_and_both_ip_quotas
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_rate_limit.py::test_user_char_gate_rejection_preserves_earlier_user_and_both_ip_quotas
FAILED tests/test_tts_ticket_rate_limit.py::test_last_ip_char_gate_rejection_preserves_both_user_and_earlier_ip_quotas
2 failed, 17 deselected, 11 warnings in 0.55s
~~~

恢复记录（两条 diff 均无输出，退出码均为 0）：

~~~text
original_sha256=be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7
mutated_sha256=c312b19760b941105e601e9e751eb1752a3ce3e9f3d5d04890bae589823ad59e
restored_sha256=be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7
restored_bytes_equal=True
$ git diff -- backend/rate_limit.py
EXIT_CODE=0
$ git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend/rate_limit.py
EXIT_CODE=0
~~~

#### 恢复后：新测试文件

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

退出码：0。实际输出：

~~~text
...................                                                      [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 11 warnings in 0.87s
~~~

### v3.3 验收命令与实际输出

后端沿用已有测试夹具，`PYTHON_DOTENV_DISABLED=1`，网络入口使用既有桩；测试库由夹具在系统临时目录创建并清理，没有手工读取环境文件或仓库数据库。测试命令均使用主仓库虚拟环境解释器，关闭 bytecode 与 pytest 缓存。

前端全部在仓库外副本 `/private/tmp/tts-v3-fe.UQjkvm/fe` 执行。准备副本时额外排除 `.env*` 和 `*.db`，以 `cp -Rc` 克隆 `node_modules`，没有软链；设置 `npm_config_offline=true` 与 `NEXT_TELEMETRY_DISABLED=1`，不下载依赖。源码副本与最终 `page.tsx` 逐字节一致。git 检查设置 `GIT_OPTIONAL_LOCKS=0`。

#### 副本准备

执行目录：`仓库根目录`。

~~~text
T=$(mktemp -d /private/tmp/tts-v3-fe.XXXXXX)/fe && rsync -a --exclude node_modules --exclude .next --exclude ".env*" --exclude "*.db" frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules" && printf "%s\n" "$T" > /private/tmp/tts-v3-front-copy.path
~~~

退出码：0。标准输出与标准错误均为空。

#### 1. 新测试文件

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

退出码：0。实际输出：

~~~text
...................                                                      [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 11 warnings in 0.87s
~~~

#### 2. 后端全量

执行目录：`backend/`。

~~~text
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python; PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
~~~

退出码：0。实际输出（仅去掉行尾空白）：

~~~text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 28%]
........................................................................ [ 32%]
........................................................................ [ 37%]
........................................................................ [ 42%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 56%]
........................................................................ [ 61%]
........................................................................ [ 65%]
........................................................................ [ 70%]
........................................................................ [ 75%]
........................................................................ [ 80%]
........................................................................ [ 84%]
........................................................................ [ 89%]
........................................................................ [ 94%]
........................................................................ [ 98%]
.................                                                        [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1529 passed, 11 warnings in 47.61s
~~~

#### 3. npx tsc --noEmit

执行目录：`/private/tmp/tts-v3-fe.UQjkvm/fe`。

~~~text
npx tsc --noEmit
~~~

退出码：0。标准输出与标准错误均为空。

#### 4. npx eslint

执行目录：`/private/tmp/tts-v3-fe.UQjkvm/fe`。

~~~text
npx eslint
~~~

退出码：0。实际输出（仅去掉行尾空白）：

~~~text

/private/tmp/tts-v3-fe.UQjkvm/fe/app/page.tsx
   131:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   222:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   380:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   426:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   427:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   428:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   438:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   439:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   440:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   441:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   444:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   450:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   451:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   705:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   709:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   780:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1161:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1181:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1189:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1210:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1247:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1343:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1687) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1786:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1826:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2069:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/tmp/tts-v3-fe.UQjkvm/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)
~~~

#### 5. npm run build

执行目录：`/private/tmp/tts-v3-fe.UQjkvm/fe`。

~~~text
npm run build
~~~

退出码：0。实际输出（仅去掉行尾空白）：

~~~text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.3 (Turbopack)
✓ Running next.config.ts took 757ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:41397) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 1847ms
  Running TypeScript ...
  Finished TypeScript in 1771ms ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14)
  Generating static pages using 16 workers (6/14)
  Generating static pages using 16 workers (10/14)
✓ Generating static pages using 16 workers (14/14) in 267ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ƒ /agents/[id]
├ ○ /agents/me
├ ○ /community
├ ○ /history
├ ○ /login
├ ○ /manifest.webmanifest
├ ○ /match
├ ○ /plaza
├ ○ /profile
└ ○ /settings


ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
~~~

#### 6. git status --porcelain --untracked-files=all

执行目录：`仓库根目录`。

~~~text
git status --porcelain --untracked-files=all
~~~

退出码：0。实际输出（仅去掉行尾空白）：

~~~text
M  backend/rate_limit.py
M  backend/routers/voice.py
AM backend/tests/test_tts_ticket_rate_limit.py
M  docs/ARCHITECTURE.md
AM docs/tasks/2026-09-29-tts-ticket-ratelimit/02-spec.md
AM docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/03-verification.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/04-review-v2.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/04-review.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/chromium-1280-notice-footer.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/chromium-390-notice-page.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/webkit-1280-notice-footer.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/webkit-390-notice-page.png
MM frontend/app/page.tsx
A  frontend/lib/ttsTicket.ts
~~~

#### 7. 与 v1 的受保护文件差异

执行目录：`仓库根目录`。

~~~text
git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend/rate_limit.py backend/routers/voice.py frontend/lib docs/ARCHITECTURE.md
~~~

退出码：0。标准输出与标准错误均为空。

### 范围审计与未完成或需要人工确认

`git status` 中的第一列来自本轮起点的暂存区。第二列新增的修改只有 v3.1 四个文件，暂存区完整二进制 diff 的 SHA-256 与起点一致。`backend/rate_limit.py` 的临时错误实现已按保存字节还原，后端源码、`frontend/lib/ttsTicket.ts` 和 `docs/ARCHITECTURE.md` 与 v1 的只读 diff 为空。

范围审计实际输出：

~~~text
{
  "index_sha256": "e030334125078b034f16c4c5e7b7ed14dfb31dfdc96a2fea0d6797e4a18778f6",
  "index_unchanged": true,
  "existing_test_prefix_unchanged": true,
  "existing_report_prefix_unchanged": true,
  "spec_only_appended_correction": true,
  "worktree_changed_files": [
    "backend/tests/test_tts_ticket_rate_limit.py",
    "docs/tasks/2026-09-29-tts-ticket-ratelimit/02-spec.md",
    "docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md",
    "frontend/app/page.tsx"
  ],
  "frontend_copy_identical": true,
  "exact_v3_whitelist": true
}
~~~

#### 补充格式检查

执行目录：`仓库根目录`。

~~~text
git diff --check
~~~

退出码：0。标准输出与标准错误均为空。

实现与 v3.3 命令验收均已完成，无待确认的实现问题。依第 0 节没有启动浏览器。v3.4 的 S10（Chromium/WebKit 均 5 句按序、0 次 error、等待提示）、S1–S9、朗读自动播放 A0/A/B/C/D/F，以及无提示输入区与 `61fc01f` 的截图逐字节对比，仍由 Claude 主会话实测确认。


## v3 复核返修

本轮按用户确认执行 M1 与可优化项 4、5、6、2、7；用户本轮指令优先于 `04-review-v3.md` 文末仅修 M1 的范围。本轮起点是此前 v3 工作区及当前暂存区，未执行任何 git 写操作。后端实现保持不变，临时变异在每次自检后逐字节恢复；本报告此前全文保留，只在末尾追加本节。下列终端输出仅剔除行尾空白，原始日志在 `/private/tmp/tts-v3-review-evidence/`。

### 六项修改与文件位置

| 用户条目 | 文件与位置 | 修改 |
|---|---|---|
| 1 / M1 | `backend/tests/test_tts_ticket_rate_limit.py:261`、266 | F2b 参数表末尾追加 `((9.0, 2.0), 9)`，id 为 `larger-reset-first`，覆盖较大 reset 在第一个失败项的顺序。原三组参数、原三项 ids 和全部已有断言均未改。 |
| 2 / 可优化 4 | 同文件 262、266 | 同表再追加 `((-10.0, -2.5), 1)`，id 为 `past-reset-minimum-one-2`。最新失败偏移为 -2.5 秒，ceil 得 -2，错误的 `ceil(x) or 1` 会返回 -2；取绝对值也会得到 2 或 3，而正确值为 1。 |
| 3 / 可优化 5 | 同文件 302–320 | 新增 `test_rejection_callback_reports_first_failed_gate_once`。真实耗满前两个闸并验证二者确实不通过，传入 `on_reject`，断言回调记录恰为首个失败项 identifiers 与本次返回的 retry_after 一条。 |
| 4 / 可优化 6 | 同文件 289、293–295、323–336 | F2b 的 `test`、`get_window_stats`、`hit` 补丁作用于 `type(limiter.limiter)`，函数签名带 self；所有原断言文本保留。另新增 cleanup 测试，在独立 monkeypatch context 中直接执行 F2b 的原正数参数，撤销后断言 `"test" not in vars(strategy)`，并检查三个方法都无实例残留、类函数身份恢复。 |
| 5 / 可优化 2 | `frontend/app/page.tsx:90–92` | 只修订常量上方注释：后端 60 秒过期；正常票龄不超过上一句播放时长，一般不触发；普通单段约 250 字/39 秒，「帮我读」可至 300 字/47 秒；越界只多换一张票与一个小空档，不丢句。45_000 常量和所有逻辑未改。 |
| 6 / 可优化 7 | `02-spec.md:79` | 只在 §1.3 的「2026-09-30 勘误」段补充 WebKit 换票时预热合成不计入使用次数，另算一次合成。其他正文不动。 |

本轮新增 **4 个测试实例**：两行参数 + 一个回调测试 + 一个撤销检查测试。因此文件为 `19 + 4 = 23`，后端全量为 `1529 + 4 = 1533`。文件在 F2b 参数表以前的原内容逐字节不变，全部已有断言的 AST 与原始文本均一致。

### 三种变异自检与恢复

三种变异分别只替换 `backend/rate_limit.py` 中一段表达式；每次运行整个测试文件，不使用 `-k` 排除其他测试。变异脚本保存原始字节，在 `try/finally` 中恢复。每次实际结果都为一个目标失败、另外 22 个通过，证明目标用例能区分错误实现且原用例继续通过。

| 变异 | 唯一失败目标 | 断言结果 | 实际输出末行 | pytest 退出码 |
|---|---|---|---|---:|
| ① `max(reset_times)` 改为 `list(reset_times)[-1]`，保持两项 stats 查询 | F2b `[larger-reset-first]` | `assert 2 == 9` | `1 failed, 22 passed, 11 warnings in 1.03s` | 1 |
| ② `max(1, ceil(x))` 改为 `ceil(x) or 1` | F2b `[past-reset-minimum-one-2]` | `assert -2 == 1` | `1 failed, 22 passed, 11 warnings in 1.06s` | 1 |
| ③ `on_reject(failed[0][1], retry_after)` 改用 `failed[-1][1]` | 新回调测试 | 收到 second，期望 first；retry_after 都为 60 | `1 failed, 22 passed, 11 warnings in 0.92s` | 1 |

#### ① 取最后一个失败项的 reset

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

pytest 退出码：1。实际输出：

~~~text
...................F...                                                  [100%]
=================================== FAILURES ===================================
_ test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one[larger-reset-first] _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x109ee97f0>
reset_offsets = (9.0, 2.0), expected = 9

    @pytest.mark.parametrize(
        ("reset_offsets", "expected"),
        [
            ((2.0, 9.0), 9),
            ((1.25, 2.01), 3),
            ((-10.0, -0.25), 1),
            ((9.0, 2.0), 9),
            ((-10.0, -2.5), 1),
        ],
        ids=(
            "latest-failed-reset", "fractional-seconds-ceil", "past-reset-minimum-one",
            "larger-reset-first", "past-reset-minimum-one-2",
        ),
    )
    def test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one(monkeypatch, reset_offsets, expected):
        from types import SimpleNamespace
        import rate_limit

        monkeypatch.setattr(limiter, "enabled", True)
        now = 1_000.0
        monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: now))
        checks = [
            ("1/minute", ("tts-retry", "first"), 1),
            ("2/minute", ("tts-retry", "second"), 1),
            ("3/minute", ("tts-retry", "passing"), 1),
        ]
        resets = {
            checks[0][1]: now + reset_offsets[0],
            checks[1][1]: now + reset_offsets[1],
            checks[2][1]: now + 999.0,
        }
        queried = []
        hits = []

        def fake_window_stats(self, _item, *identifiers):
            queried.append(identifiers)
            return SimpleNamespace(reset_time=resets[identifiers], remaining=0)

        monkeypatch.setattr(type(limiter.limiter), "test", lambda self, _item, *identifiers, cost: identifiers == checks[2][1])
        monkeypatch.setattr(type(limiter.limiter), "get_window_stats", fake_window_stats)
        monkeypatch.setattr(type(limiter.limiter), "hit", lambda self, _item, *identifiers, cost: hits.append(identifiers))

>       assert check_and_hit(checks) == expected
E       AssertionError: assert 2 == 9
E        +  where 2 = check_and_hit([('1/minute', ('tts-retry', 'first'), 1), ('2/minute', ('tts-retry', 'second'), 1), ('3/minute', ('tts-retry', 'passing'), 1)])

tests/test_tts_ticket_rate_limit.py:297: AssertionError
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_rate_limit.py::test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one[larger-reset-first]
1 failed, 22 passed, 11 warnings in 1.03s
~~~

该次变异恢复记录（git diff 输出为空、退出码 0）：

~~~text
{
  "original_sha256": "be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7",
  "restored_sha256": "be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7",
  "restored_bytes_equal": true,
  "only_expected_failure": true,
  "restored_diff": {
    "command": "git diff -- backend/rate_limit.py",
    "exit_code": 0,
    "output": ""
  }
}
~~~

#### ② ceil(x) or 1

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

pytest 退出码：1。实际输出：

~~~text
....................F..                                                  [100%]
=================================== FAILURES ===================================
_ test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one[past-reset-minimum-one-2] _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ba70550>
reset_offsets = (-10.0, -2.5), expected = 1

    @pytest.mark.parametrize(
        ("reset_offsets", "expected"),
        [
            ((2.0, 9.0), 9),
            ((1.25, 2.01), 3),
            ((-10.0, -0.25), 1),
            ((9.0, 2.0), 9),
            ((-10.0, -2.5), 1),
        ],
        ids=(
            "latest-failed-reset", "fractional-seconds-ceil", "past-reset-minimum-one",
            "larger-reset-first", "past-reset-minimum-one-2",
        ),
    )
    def test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one(monkeypatch, reset_offsets, expected):
        from types import SimpleNamespace
        import rate_limit

        monkeypatch.setattr(limiter, "enabled", True)
        now = 1_000.0
        monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: now))
        checks = [
            ("1/minute", ("tts-retry", "first"), 1),
            ("2/minute", ("tts-retry", "second"), 1),
            ("3/minute", ("tts-retry", "passing"), 1),
        ]
        resets = {
            checks[0][1]: now + reset_offsets[0],
            checks[1][1]: now + reset_offsets[1],
            checks[2][1]: now + 999.0,
        }
        queried = []
        hits = []

        def fake_window_stats(self, _item, *identifiers):
            queried.append(identifiers)
            return SimpleNamespace(reset_time=resets[identifiers], remaining=0)

        monkeypatch.setattr(type(limiter.limiter), "test", lambda self, _item, *identifiers, cost: identifiers == checks[2][1])
        monkeypatch.setattr(type(limiter.limiter), "get_window_stats", fake_window_stats)
        monkeypatch.setattr(type(limiter.limiter), "hit", lambda self, _item, *identifiers, cost: hits.append(identifiers))

>       assert check_and_hit(checks) == expected
E       AssertionError: assert -2 == 1
E        +  where -2 = check_and_hit([('1/minute', ('tts-retry', 'first'), 1), ('2/minute', ('tts-retry', 'second'), 1), ('3/minute', ('tts-retry', 'passing'), 1)])

tests/test_tts_ticket_rate_limit.py:297: AssertionError
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_rate_limit.py::test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one[past-reset-minimum-one-2]
1 failed, 22 passed, 11 warnings in 1.06s
~~~

该次变异恢复记录（git diff 输出为空、退出码 0）：

~~~text
{
  "original_sha256": "be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7",
  "restored_sha256": "be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7",
  "restored_bytes_equal": true,
  "only_expected_failure": true,
  "restored_diff": {
    "command": "git diff -- backend/rate_limit.py",
    "exit_code": 0,
    "output": ""
  }
}
~~~

#### ③ 回调取 failed[-1]

执行目录：`backend/`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

pytest 退出码：1。实际输出：

~~~text
.....................F.                                                  [100%]
=================================== FAILURES ===================================
____________ test_rejection_callback_reports_first_failed_gate_once ____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x109ec62d0>

    def test_rejection_callback_reports_first_failed_gate_once(monkeypatch):
        monkeypatch.setattr(limiter, "enabled", True)
        checks = [
            ("1/minute", ("tts-reject-callback", "first"), 1),
            ("1/minute", ("tts-reject-callback", "second"), 1),
        ]
        assert check_and_hit(checks) is None
        assert all(
            not limiter.limiter.test(parse(limit), *identifiers, cost=cost)
            for limit, identifiers, cost in checks
        )
        rejected = []

        retry_after = check_and_hit(
            checks, on_reject=lambda identifiers, seconds: rejected.append((identifiers, seconds))
        )

        assert isinstance(retry_after, int) and 1 <= retry_after <= 60
>       assert rejected == [(checks[0][1], retry_after)]
E       AssertionError: assert [(('tts-rejec...second'), 60)] == [(('tts-rejec...'first'), 60)]
E
E         At index 0 diff: (('tts-reject-callback', 'second'), 60) != (('tts-reject-callback', 'first'), 60)
E         Use -v to get more diff

tests/test_tts_ticket_rate_limit.py:320: AssertionError
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_rate_limit.py::test_rejection_callback_reports_first_failed_gate_once
1 failed, 22 passed, 11 warnings in 0.92s
~~~

该次变异恢复记录（git diff 输出为空、退出码 0）：

~~~text
{
  "original_sha256": "be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7",
  "restored_sha256": "be021e0950a085b3d21218f3c19e824526a5d4ceca06f102eecabdefe3995ea7",
  "restored_bytes_equal": true,
  "only_expected_failure": true,
  "restored_diff": {
    "command": "git diff -- backend/rate_limit.py",
    "exit_code": 0,
    "output": ""
  }
}
~~~

### 恢复后的自检命令与实际输出

使用主仓库虚拟环境解释器，`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`。后端沿用已有隔离夹具，禁用真实 dotenv 配置及真实网络入口，测试库只由既有夹具在系统临时目录创建和清理。

前端在仓库外副本 `/private/tmp/tts-v3-review-fe.OlvS1M/fe` 执行；复制时排除 `.env*` 和 `*.db`，通过 `cp -Rc` 克隆 node_modules；`npm_config_offline=true`、`NEXT_TELEMETRY_DISABLED=1`。副本 page.tsx 与本轮最终源码逐字节一致。

#### 前端副本准备

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit`。

~~~text
T=$(mktemp -d /private/tmp/tts-v3-review-fe.XXXXXX)/fe && rsync -a --exclude node_modules --exclude .next --exclude ".env*" --exclude "*.db" frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules" && printf "%s\n" "$T" > /private/tmp/tts-v3-review-front-copy.path
~~~

退出码：0。实际输出为空（stdout/stderr 均为空）。

#### 新测试文件：23 passed

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit/backend`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_ticket_rate_limit.py
~~~

退出码：0。实际输出：

~~~text
.......................                                                  [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_rate_limit.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_rate_limit.py::test_user_request_quota_is_independent_for_users_sharing_an_ip
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
23 passed, 11 warnings in 0.90s
~~~

#### 后端全量：1533 passed

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit/backend`。

~~~text
PYTHONDONTWRITEBYTECODE=1 /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider
~~~

退出码：0。实际输出：

~~~text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 28%]
........................................................................ [ 32%]
........................................................................ [ 37%]
........................................................................ [ 42%]
........................................................................ [ 46%]
........................................................................ [ 51%]
........................................................................ [ 56%]
........................................................................ [ 61%]
........................................................................ [ 65%]
........................................................................ [ 70%]
........................................................................ [ 75%]
........................................................................ [ 79%]
........................................................................ [ 84%]
........................................................................ [ 89%]
........................................................................ [ 93%]
........................................................................ [ 98%]
.....................                                                    [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1533 passed, 11 warnings in 47.80s
~~~

#### npx tsc --noEmit

执行目录：`/private/tmp/tts-v3-review-fe.OlvS1M/fe`。

~~~text
npx tsc --noEmit
~~~

退出码：0。实际输出为空（stdout/stderr 均为空）。

#### npx eslint

执行目录：`/private/tmp/tts-v3-review-fe.OlvS1M/fe`。

~~~text
npx eslint
~~~

退出码：0。实际输出：

~~~text

/private/tmp/tts-v3-review-fe.OlvS1M/fe/app/page.tsx
   132:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   223:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   381:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   427:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   428:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   429:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   439:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   440:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   441:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   442:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   445:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   451:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   452:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   706:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   710:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   781:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1162:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1182:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1190:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1211:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1248:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1344:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1688) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1787:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1827:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2070:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/tmp/tts-v3-review-fe.OlvS1M/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)
~~~

#### 恢复后源码 diff

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit`。

~~~text
git diff -- backend/rate_limit.py
~~~

退出码：0。实际输出为空（stdout/stderr 均为空）。

#### 受保护文件与 v1 的 diff

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit`。

~~~text
git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend/rate_limit.py backend/routers/voice.py frontend/lib docs/ARCHITECTURE.md
~~~

退出码：0。实际输出为空（stdout/stderr 均为空）。

#### 最终 git status

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit`。

~~~text
git status --porcelain --untracked-files=all
~~~

退出码：0。实际输出：

~~~text
M  backend/rate_limit.py
M  backend/routers/voice.py
AM backend/tests/test_tts_ticket_rate_limit.py
M  docs/ARCHITECTURE.md
AM docs/tasks/2026-09-29-tts-ticket-ratelimit/02-spec.md
AM docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/03-verification.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/04-review-v2.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/04-review-v3.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/04-review.md
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/chromium-1280-notice-footer.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/chromium-390-notice-page.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/webkit-1280-notice-footer.png
A  docs/tasks/2026-09-29-tts-ticket-ratelimit/shots/webkit-390-notice-page.png
MM frontend/app/page.tsx
A  frontend/lib/ttsTicket.ts
~~~

#### 补充格式检查

执行目录：`/Users/yangjing/Desktop/ai-workspace/Fiona/.claude/worktrees/tts-ratelimit`。

~~~text
git diff --check
~~~

退出码：0。实际输出为空（stdout/stderr 均为空）。

### 范围审计与未完成事项

本轮起点暂存区指纹保持不变，只修改四个白名单文件的授权位置；原报告完整前缀保留。实际范围审计输出：

~~~text
{
  "index_sha256": "16433ec898da2e9523a8276f5ee47d97641cc71931be9a1332f0ab4ae01a8b0d",
  "pre_f2b_tests_unchanged": true,
  "all_existing_assertions_unchanged": true,
  "original_three_parameter_rows_unchanged": true,
  "original_three_ids_unchanged": true,
  "exact_two_parameter_rows_added": true,
  "exact_two_ids_added": true,
  "frontend_only_comment_changed": true,
  "spec_only_authorized_correction_changed": true,
  "report_original_prefix_unchanged": true,
  "rate_limit_source_restored": true,
  "worktree_changed_files": [
    "backend/tests/test_tts_ticket_rate_limit.py",
    "docs/tasks/2026-09-29-tts-ticket-ratelimit/02-spec.md",
    "docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md",
    "frontend/app/page.tsx"
  ],
  "frontend_copy_identical": true,
  "index_unchanged": true,
  "exact_whitelist": true,
  "all_existing_assertion_text_unchanged": true
}
~~~

本轮六项修改、三种变异自检和要求的恢复后检查均完成，没有待确认的实现事项。未启动浏览器。此前 v3 浏览器复核结果已记录于 `04-review-v3.md`，本轮不改变前端运行逻辑。
