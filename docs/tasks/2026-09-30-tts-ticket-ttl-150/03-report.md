# 朗读票据 TTL 150 秒 —— 实现与验收报告

基线：`dc5336a`。实施范围：第 0 节白名单；后端和前端各由一个子代理负责，没有给子代理传入 model 或 reasoning_effort，同一文件只归一个代理。架构文档与本报告由主代理负责。

代码按规格字面要求实现；第 2 节“不乱序”目标在“当前票不足且预取元素已经解锁”这一边界存在规格冲突，尚待用户确认。下文明确列出，不宣称已完成浏览器验收。

## 1. 文件与功能

| 文件 | 变更 |
|---|---|
| `backend/routers/voice.py` | TTL 150 秒；每用户最多 64 张未过期票据；同锁内先清过期，再淘汰该用户最早票，再执行既有全局 FIFO，最后写新票；取消被淘汰票的预热任务；补规定注释 |
| `backend/tests/test_tts_private_tickets.py` | 仅第 39 行授权断言由 `<= 60` 改为 `== 150` |
| `backend/tests/test_tts_ticket_ttl.py`（新建） | 9 个测试实例，覆盖 T3 全部子项和清理顺序 |
| `frontend/lib/ttsTicket.ts` | 返回票据及后端有效期毫秒数；验证有限正数，缺失/无效默认 60 秒，结果夹在 1–600 秒 |
| `frontend/app/page.tsx` | 保存票据到期时刻；统一判断剩余不足 15 秒；预取超龄重换；“点此播放”当前票不足时在手势内同步撤下、回队、释放、解锁、隐藏提示、重新换票 |
| `docs/ARCHITECTURE.md` | 仅 `routers/voice.py` 一行补充 TTL 与每用户上限 |
| 本任务 `03-report.md`（新建） | 规格对应、状态转换、真实验收输出和未决问题 |

任务开始时 `02-spec.md` 已由用户暂存为新增文件；本任务没有改动它。没有新增依赖、改配置/lockfile、读 `.env*`、触碰已有数据库、启动 `next dev`、做 Git 写操作或调用外部服务。后端测试由已有 conftest 禁用 dotenv，并使用测试临时数据库/上传目录与假模型、假 TTS；前端构建设置 npm 离线与禁用 Next 遥测。

## 2. T1–T7 逐项对应

| 任务 | 对应与状态 |
|---|---|
| T1 | `voice.py:32,42,311,314–331`：完成 150 秒及每用户同锁 FIFO 淘汰 |
| T2 | `test_tts_private_tickets.py:39`：仅授权行改为响应 `== 150` |
| T3 | 新测试 9 个实例全部通过；逐项见第 4 节 |
| T4 | `ttsTicket.ts:62,101–103`：返回 `{ ticket, expiresInMs }`，验证/默认/夹取完成 |
| T5 | `page.tsx:80,90–97,859,884–887,958–962,1075–1100`：完成 3.3 字面步骤；已解锁预取的乱序边界待确认，见第 8 节 |
| T6 | `ARCHITECTURE.md:61`：仅该行更新；全库旧事实检索见第 7 节 |
| T7 | 本报告：文件、3.1–3.4/T3 对应、状态表、命令完整输出/退出码、未决问题均已记录 |

## 3. 3.1–3.4 逐条对应

| 规格要求 | 实现或证据 |
|---|---|
| 3.1 TTL 常量 150，签发/响应请求时读取 | `voice.py:32,311,331`；默认与 monkeypatch 为 5 的测试通过 |
| 3.1 每用户上限默认 64、请求时读取 | `voice.py:42,319–322`；默认值与动态从 10 改为 3 的测试通过 |
| 3.1 锁内步骤 1：先清理过期 | 既有清理保留在 `314–318`；补充清理顺序测试通过 |
| 3.1 锁内步骤 2：只删当前用户最早票直到可签发 | 筛选 `existing.user == user`，沿 dict 插入顺序删足够数量，逐张调用 `_cancel_tts_prewarm`；A/B 隔离及预热取消测试通过 |
| 3.1 锁内步骤 3：全局 FIFO 不变 | 既有 `if len(...) >= TTS_MAX_PENDING_TICKETS` 和淘汰/取消代码逐字保留；多用户全局 FIFO 测试通过 |
| 3.1 锁内步骤 4：最后写新票 | 写入仍位于两级淘汰后；WebKit 预热流程保留 |
| 3.1 两点常量注释 | `voice.py:40–41` 解释有效期变长与全局 FIFO 排挤风险，以及当前/预取两张为用户最新签发票 |
| 3.1 其他后端逻辑不变 | diff 仅 TTL、注释/常量和用户淘汰四行；四道限流、次数、缓存、预热、Range 未改；全量 1542 passed |
| 3.2 返回类型 | `Promise<{ ticket: string; expiresInMs: number } \| null>` |
| 3.2 响应有效期验证 | 只接受 number、有限、>0；缺失、零、负数、非数字、非有限值默认 60 秒；毫秒结果夹在 `[1_000,600_000]` |
| 3.2 429/共享退避/中止/等待回调 | 成功响应解析之外的流程逐字保留，静态比对通过 |
| 3.3.1 字段/初始值 | `ticketAt` 替换为 `ticketExpiresAt: number \| null`，初始 null |
| 3.3.1 到期时刻/迟到保护 | 检查 `canUse` 与票 → 设置 src → `Date.now()+expiresInMs` → 再检查 `canUse` → load；原保护顺序保留 |
| 3.3.2 统一判据/注释 | 模块常量 `15_000`；`ticketExpiresAt !== null && ticketExpiresAt-Date.now()<15_000`；注释包含后端响应、开始播放/首 Range 余量、正常 150 秒流程不触发 |
| 3.3.3 预取转当前 | 改用 `isTicketStale`；释放 → 原文放回队头 → 原 mkTtsAudio 分支不变 |
| 3.3.4 共用第一步 | 仅预取元素未解锁时，原撤下/文本回队/释放步骤逐字保留 |
| 3.3.4 不足路径 1 | 同步撤下 current，并清 playing |
| 3.3.4 不足路径 2 | 在预取回队后 unshift 当前文本，正常路径队列成为 `[C,P,R…]` |
| 3.3.4 不足路径 3 | release 当前元素，取消旧请求/句级监听 |
| 3.3.4 不足路径 4 | primeTtsAudio，在本次手势内对空闲未解锁元素调用 play |
| 3.3.4 不足路径 5 | 隐藏被拦提示 |
| 3.3.4 不足路径 6 | playNextInQueue，沿用换票及 429 提示；整个不足分支没有 await；已解锁预取边界见第 8 节 |
| 3.3.4 够用路径 | 原 prime → 直接 playPreparedTts → 隐藏提示 → tryPrefetch，主体逐字保留 |
| 3.3.4 新票仍被拒绝 | 原 NotAllowedError 处理未改，再次显示被拦提示，没有自动循环 |
| 3.3.5 其他交互/生命周期 | 限速提示、不听了、关朗读、其余手势调用点、两元素池、句级监听清理、免提开麦代码均未改 |
| 3.4 文档 | 仅架构表 voice 行更新两项；未发现白名单外其他现行“票据有效期 60 秒”事实陈述 |

## 4. T3 各子项与测试

| 子项 | 测试（新文件内） | 检查内容 |
|---|---|---|
| T3.1 | `test_default_ttl_matches_response_and_ticket_expiry`（58 行） | 常量 150、响应 150、实际剩余 149–150 秒；另验证用户上限 64 |
| T3.2 | `test_ttl_is_read_on_each_request`（67 行） | 首张默认 150，patch 为 5 后响应 5、实际剩余 4–5 秒 |
| T3.3 有效时 | `test_ticket_works_until_expiry_then_returns_404`（77 行，双接口参数化） | 两接口有效时 200，返回假音频 |
| T3.3 过期时 | 同上 | 直接 replace expires_at 到过去，stream/synthesize 均 404；没有全局 patch time.monotonic |
| T3.4 设置/顺序 | `test_user_cap_evicts_only_own_oldest_tickets`（90 行） | 用户上限 3、限流关闭；全局上限 5 同时验证先用户后全局 |
| T3.4 A 旧两张 | 同上 | 连签 5 张，最早 2 张移除，播放 404 |
| T3.4 A 最新三张 | 同上 | 最新 3 张保留、播放 200 |
| T3.4 B 的票 | 同上 | B 事先签的 2 张完整保留，播放 200 |
| T3.4 预热取消 | `test_user_cap_cancels_evicted_webkit_prewarm`（105 行） | WebKit UA、阻塞假合成；最早两个 asyncio 任务 cancelled，build 被唤醒且无音频；最新三张与 B 可用 |
| T3.5 | `test_global_cap_keeps_original_fifo_across_users`（160 行） | 全局 3、用户 20；三用户交错签 5 张，全局最早 2 张 404、最新 3 张 200 |
| T3.6 | `test_user_cap_is_read_on_each_request_and_shrinks_existing_backlog`（173 行） | 用户上限 10→3，下一次请求立即淘汰足够数量，保留最新 3 张 |
| 补充 | `test_expired_cleanup_precedes_user_and_global_eviction`（187 行） | 过期先清理，不误删同用户或其他用户的活票 |

合计 9 个测试实例（8 个函数，其中过期函数参数化 2 个接口）；全量预期与实际均为 `1533+9=1542`。

## 5. “点此播放”状态转换表

记号：C＝被拦当前句，P＝预取句，R＝其余队列；S_C/S_P＝两句占用的池元素。下表先列规格通常路径：P 未解锁、被第一步释放；没有 P 时直接去掉 P。

| 路径/步骤 | 元素归属与当前/playing | 文本队列 | 提示状态 |
|---|---|---|---|
| 点击前（共用） | S_C→C，S_P→P；current=C，playing=true | [R…] | 被拦提示显示 |
| 第一阶段释放未解锁 P（共用） | S_P 空闲，S_C→C；current=C | [P,R…] | 保持被拦 |
| 够用：prime | 空闲未解锁 S_P 在手势内调用静音 play；S_C→C | [P,R…] | 保持被拦 |
| 够用：直接 playPreparedTts(C) | current=C，S_C 继续持有旧票 | [P,R…] | 保持直到下一同步步骤 |
| 够用：隐藏提示 | 归属不变 | [P,R…] | 被拦提示隐藏 |
| 够用：tryPrefetch | S_P→新 P，current=C | [R…] | 原限速逻辑；若 C 再被拒绝则重新被拦 |
| 不足 1：撤下当前 | current=null，playing=false；S_C 暂仍→C | [P,R…] | 保持被拦 |
| 不足 2：当前回队 | S_C 暂仍→C | [C,P,R…] | 保持被拦 |
| 不足 3：释放当前 | S_C/S_P 空闲，旧 C 请求与监听取消 | [C,P,R…] | 保持被拦 |
| 不足 4：prime | 空闲未解锁元素在该手势内调用静音 play，随后正常接管 | [C,P,R…] | 保持被拦 |
| 不足 5：隐藏提示 | 元素空闲或处于 prime | [C,P,R…] | 被拦提示隐藏 |
| 不足 6：playNextInQueue | mkTtsAudio(C) 占空闲元素；current=新 C，playing=true；原 tryPrefetch 准备新 P | [R…]（已有 P 时被正常预取取走） | 429 按既有流程显示等待；新票仍被拒绝则再次被拦，无自动循环 |

如果 P 已解锁，够用路径保留其元素，直接播放 C；无需重建 P。若 P 已解锁而 C 不足，严格字面流程的边界如下：

| 步骤 | 元素归属/当前 | 队列 | 提示 |
|---|---|---|---|
| 共用第一步不释放已解锁 P | S_C→C，S_P→P | [R…] | 被拦 |
| 不足 1–3 | current=null，S_C 空闲，S_P→P | [C,R…] | 被拦 |
| 不足 4–5 | prime 空闲 S_C，S_P 仍→P | [C,R…] | 隐藏 |
| 不足 6 | playNextInQueue 优先取 P，current=P；原 tryPrefetch 才从队列取 C | [R…] | 先播放 P、随后 C，违反第 2 节不乱序目标 |

## 6. 第 5.1 节实际命令、完整输出与退出码

后端 cwd：`backend/`；PY 指向规格指定虚拟环境。前端 cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.JmjFFM2ZjZ/fe`，所有检查在仓库外副本。下面输出为真实运行记录，空输出单独注明。构建日志中的换行/回车按文本展示。

### 6.1 新后端测试

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_ttl.py
```

退出码：0；最终稿由后端子代理执行。

```text
.........                                                                [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
9 passed, 11 warnings in 1.05s
```

### 6.2 后端全量

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

退出码：0。

```text
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
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 70%]
........................................................................ [ 74%]
........................................................................ [ 79%]
........................................................................ [ 84%]
........................................................................ [ 88%]
........................................................................ [ 93%]
........................................................................ [ 98%]
..............................                                           [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1542 passed, 11 warnings in 52.13s
```

### 6.3 前端仓库外副本准备

为遵守第 0 节“不读 .env*”，在规格复制命令增加 `--exclude '.env*'`；没有读取任何环境文件。实际执行：

```bash
T=$(mktemp -d)/fe && rsync -a --exclude node_modules --exclude .next --exclude '.env*' frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules" && printf '%s\n' "$T"
```

退出码：0。输出（最后 printf 为记录副本位置）：

```text
/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.JmjFFM2ZjZ/fe
```

### 6.4 TypeScript

```bash
npm_config_offline=true NEXT_TELEMETRY_DISABLED=1 npx tsc --noEmit
```

退出码：0；实际 stdout/stderr 均为空。

### 6.5 ESLint

```bash
npm_config_offline=true NEXT_TELEMETRY_DISABLED=1 npx eslint
```

退出码：0。

```text

/private/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.JmjFFM2ZjZ/fe/app/page.tsx
   136:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   227:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   385:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   431:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   432:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   433:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   443:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   444:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   445:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   446:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   449:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   455:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   456:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   710:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   714:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   785:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1175:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1195:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1203:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1224:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1261:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1357:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1701) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1800:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1840:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2083:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.JmjFFM2ZjZ/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)
```

0 errors，26 warnings，未超过基线 26。

### 6.6 生产构建

```bash
npm_config_offline=true NEXT_TELEMETRY_DISABLED=1 npm run build
```

退出码：0。

```text

> frontend@0.1.0 build
> next build

▲ Next.js 16.3.3 (Turbopack)
✓ Running next.config.ts took 707ms
- Experiments (use with caution):
  · proxyClientMaxBodySize: "25mb"

  Creating an optimized production build ...
(node:66863) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 1817ms
  Running TypeScript ...
  Finished TypeScript in 2.0s ...
  Collecting page data using 16 workers ...
  Generating static pages using 16 workers (0/14) ...
  Generating static pages using 16 workers (3/14) 
  Generating static pages using 16 workers (6/14) 
  Generating static pages using 16 workers (10/14) 
✓ Generating static pages using 16 workers (14/14) in 293ms
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

仓库根目录四条验收命令的最终记录追加在下节。

## 7. 全库旧事实搜索与补充核对

搜索覆盖非历史任务的现行代码/文档，包括隐藏目录；排除 `.git`、`.env*`、数据库、node_modules、构建产物和本报告。搜索“票据/ticket”与“60/六十/有效期/过期/TTL”的组合，未发现白名单外“票据有效期 60 秒”的现行事实陈述，所以没有需要主会话另改的位置。`ttsTicket.ts` 中的 60 秒是规格要求的无效/缺失响应兼容默认值，600 秒是夹取上界，都不是后端有效期陈述。

补充检查：`git diff --check` 无输出、退出 0；已有测试 diff 1 增 1 删，仅授权行；架构 diff 1 增 1 删，仅 voice 行。前端静态比对验证退避/429/中止代码、够用播放主体、共用预取释放步骤逐字保留，且不足分支无 await。

主代理另以字节比对核查原测试只替换授权断言、其他所有已有测试未改，并逐行核查架构文档仅 voice 行变化；白名单审计退出 0，实际输出：

```text
PASS: whitelist only; original private test differs by exactly the authorized assertion; all other existing tests unchanged; architecture differs by exactly the voice row
```

另外用 Node 从实际 page.tsx 提取 resumeBlockedTts/playNextInQueue 回调，注入内存 refs/假音频、假换票，不启动浏览器、不发网络、不写仓库测试。省略预取副作用以直接观察首播与队列，实际输出、退出码 0：

```text
current_stale=false, preload_unlocked=false: first=C, queue=[P,R]
current_stale=true, preload_unlocked=false: first=C, queue=[P,R]
current_stale=true, preload_unlocked=true: first=P, queue=[C,R]
```

前两条与预期一致；第三条证明第 8 节的规格边界存在。

## 8. 未完成与需人工确认

1. **实现边界待规格确认**：当前票不足 15 秒，且预取句元素已解锁时，3.3.4 的第一阶段只释放未解锁预取，因此仍保留 P；六步最后的 playNextInQueue 优先使用 P，导致 P 先于 C。代码严格保留规格步骤，没有擅自修改够用路径或扩大预取释放条件。已向用户发出澄清：是否允许在不足分支先释放已解锁 P、将 P 放回队头，再执行规定六步。尚未收到答复；该边界未修复，不能宣称“无论多久、不乱序”目标完全达成。
2. **浏览器实测未运行**：按第 0 节/5.2 交 Claude 主会话执行 WebKit/Chromium 的 BL1（20 秒/等 30 秒）、BL2（150 秒/等 70 秒）、BL3（等 160 秒）、S10′（20 秒/预取等待 >5 秒）、S1–S9、A0/A/B/C/D/F 及无提示输入区逐字节截图对照。建议额外覆盖“当前过期且 P 已解锁”边界；构建/静态核对不能替代真实手势解锁验证。
3. **无其他未完成项**：后端 T1–T3、前端 T4 及 T5 的字面实现、文档 T6、报告 T7 均已落实；无需安装依赖、无外部部署/发布操作。

## 9. 仓库根目录验收输出

### 9.1 变更范围

```bash
git status --porcelain --untracked-files=all
```

退出码：0。实际输出：

```text
 M backend/routers/voice.py
 M backend/tests/test_tts_private_tickets.py
 M docs/ARCHITECTURE.md
A  docs/tasks/2026-09-30-tts-ticket-ttl-150/02-spec.md
 M frontend/app/page.tsx
 M frontend/lib/ttsTicket.ts
?? backend/tests/test_tts_ticket_ttl.py
?? docs/tasks/2026-09-30-tts-ticket-ttl-150/03-report.md
```

### 9.2 既有测试唯一授权改动

```bash
git diff -- backend/tests/test_tts_private_tickets.py
```

退出码：0。实际输出：

```text
diff --git a/backend/tests/test_tts_private_tickets.py b/backend/tests/test_tts_private_tickets.py
index 30738f8..3115e3b 100644
--- a/backend/tests/test_tts_private_tickets.py
+++ b/backend/tests/test_tts_private_tickets.py
@@ -36,7 +36,7 @@ def test_tts_ticket_range_probe_then_playback_and_bound_to_user(client, monkeypa
     issued = client.post("/tts/ticket", headers=owner, json={"text": "私聊内容"})
     assert issued.status_code == 200
     ticket = issued.json()["ticket"]
-    assert issued.json()["expires_in"] <= 60
+    assert issued.json()["expires_in"] == 150
     assert "私聊内容" not in ticket
 
     denied = client.get("/tts/stream", headers=other, params={"ticket": ticket})
```

### 9.3 删除旧票龄字段与常量

```bash
grep -n "TTS_PRELOAD_MAX_TICKET_AGE_MS\|ticketAt\b" frontend/app/page.tsx
```

退出码：1。实际输出为空，匹配 0 行；grep 的无匹配退出码 1 是本项预期。

### 9.4 换票调用唯一入口

```bash
grep -rn "tts/ticket" frontend/app frontend/lib
```

退出码：0。实际输出：

```text
frontend/lib/ttsTicket.ts:76:      const response = await apiFetch(`${API_BASE}/tts/ticket`, {
```

第 9.1 节除白名单文件外，仅出现任务开始时已经暂存的本任务规格；没有本任务新改的白名单外文件。

## v1.1 更正

本节落实 `02-spec.md` 末尾的 v1.1；前文第 8 节第 1 项“规格边界待确认”已经解决，前文关于该边界的失败记录属于更正前的结果。本次只在 `frontend/app/page.tsx` 的不足分支新增 6 行，并在本报告末尾追加本节；其他代码、测试、规格和此前报告内容保持原样。沿用原前端子代理修改该唯一代码文件，没有传 model 或 reasoning_effort；没有 Git 写操作、网络调用、环境文件读取或依赖变动。

### 改动行与执行顺序

`frontend/app/page.tsx:1087–1092` 新增：

```ts
      const remainingPreload = ttsPreloadRef.current;
      if (remainingPreload) {
        ttsPreloadRef.current = null;
        ttsQueueRef.current.unshift(remainingPreload.text);
        releaseTtsAudio(remainingPreload);
      }
```

位置为撤下当前句/清除 playing（1085–1086 行）之后、当前文本回队（1093 行）之前。读取的是此时仍存在的 ref，不检查元素是否已解锁。随后原有 release 当前 → prime → 隐藏提示 → playNextInQueue（1094–1097 行）保留，没有 await。共用第一阶段仍只释放未解锁预取；票够用路径保持原样。

### 两种情形的队列与元素归属推演

记 C＝第 1 句（被拦的当前句），P＝第 2 句（原预取句），其余为第 3–5 句；S_C/S_P 为原两元素。新 C/P 表示重新换票后的 prepared，仍使用原两元素池。调用 prime 是本次手势内同步调用；解锁 Promise 仍由既有逻辑处理。

**预取句元素未解锁**：

| 步骤 | current / preload / playing | 元素归属 | 队列 | 提示 |
|---|---|---|---|---|
| 点击前 | C / P / true | S_C→C，S_P→P（未解锁） | [3,4,5] | 被拦 |
| 共用第一阶段 | C / null / true | S_C→C，S_P 空闲；P 请求/监听取消 | [2,3,4,5] | 被拦 |
| 不足分支撤下当前 | null / null / false | S_C 暂仍→C，S_P 空闲 | [2,3,4,5] | 被拦 |
| 新增处理仍存在的预取 | null / null / false | ref 已空，无重复释放或入队 | [2,3,4,5] | 被拦 |
| 当前文本回队 | null / null / false | S_C 暂仍→C，S_P 空闲 | [1,2,3,4,5] | 被拦 |
| release 当前 → prime → 隐藏提示 | null / null / false | 两元素空闲，旧 C 请求/监听取消；未解锁者在手势内 prime | [1,2,3,4,5] | 隐藏被拦提示 |
| playNextInQueue → 原 tryPrefetch | 新 C / 新 P / true | 空闲池元素分别归属新 C、新 P | [3,4,5] | 429 沿用等待提示；新票仍拒绝则再次被拦 |

**预取句元素已解锁**：

| 步骤 | current / preload / playing | 元素归属 | 队列 | 提示 |
|---|---|---|---|---|
| 点击前 | C / P / true | S_C→C，S_P→P（已解锁） | [3,4,5] | 被拦 |
| 共用第一阶段 | C / P / true | 不释放已解锁的 S_P，归属保持 | [3,4,5] | 被拦 |
| 不足分支撤下当前 | null / P / false | S_C 暂仍→C，S_P→P | [3,4,5] | 被拦 |
| 新增处理仍存在的预取 | null / null / false | S_P 空闲、保留已有解锁状态；P 请求/监听取消 | [2,3,4,5] | 被拦 |
| 当前文本回队 | null / null / false | S_C 暂仍→C，S_P 空闲 | [1,2,3,4,5] | 被拦 |
| release 当前 → prime → 隐藏提示 | null / null / false | 两元素空闲；空闲未解锁者在手势内 prime，S_P 无需重复解锁 | [1,2,3,4,5] | 隐藏被拦提示 |
| playNextInQueue → 原 tryPrefetch | 新 C / 新 P / true | 空闲池元素分别归属新 C、新 P | [3,4,5] | 原限速/被拦提示逻辑 |

两种情形进入 playNextInQueue 时 preload 都为 null，文本队列都为 [1,2,3,4,5]，因此该调用必从队头取第 1 句，随后原 tryPrefetch 才取第 2 句。未解锁 P 已由共用阶段回队，新增处理跳过；已解锁 P 在新增处理回队；两种情况 P 都只入队一次，旧 P/C 都各释放一次。

### 顺序自检与改动范围核对

用 Node 从更正后的实际源码提取 resumeBlockedTts、playNextInQueue、tryPrefetch、finishCurrentTts、releaseTtsAudio 和 isTicketStale 回调，提供两元素内存池、假 Audio/换票/prime；驱动 ready Promise 和逐句结束。没有启动浏览器或发起网络，也没有新增/修改仓库测试。

覆盖“预取元素已解锁/未解锁 × 预取票仍有效/已经过期”四种组合。断言释放当前前队列恰为 [1,2,3,4,5]、current/preload 均已撤下；旧两句请求已中止、各释放一次；模拟播放调用每句一次且顺序严格为 1→2→3→4→5；完成后队列空、元素池空闲。实际输出，退出码 0：

```text
PASS: preload_unlocked=false, preload_expired=false; order=[1,2,3,4,5]; calls_per_sentence=1; old_current/preload_released_once; final_pool_free
PASS: preload_unlocked=false, preload_expired=true; order=[1,2,3,4,5]; calls_per_sentence=1; old_current/preload_released_once; final_pool_free
PASS: preload_unlocked=true, preload_expired=false; order=[1,2,3,4,5]; calls_per_sentence=1; old_current/preload_released_once; final_pool_free
PASS: preload_unlocked=true, preload_expired=true; order=[1,2,3,4,5]; calls_per_sentence=1; old_current/preload_released_once; final_pool_free
```

与本次更正前快照逐字节比较，确认 page.tsx 恰为指定分支插入这 6 行；其他代码/测试/规格文件哈希相同，既有报告在追加前也相同。实际审计输出，退出码 0：

```text
PASS: page.tsx adds exactly 6 lines in stale resume branch; all other code/spec files byte-identical; report unchanged before append; whitelist audit passed
```

`git diff --check -- frontend/app/page.tsx`：无输出，退出码 0。

### 仓库外副本 tsc / eslint 的实际输出

副本准备（额外排除 .env*，遵守第 0 节）：

```bash
T=$(mktemp -d)/fe && rsync -a --exclude node_modules --exclude .next --exclude '.env*' frontend/ "$T/" && cp -Rc frontend/node_modules "$T/node_modules" && printf '%s\n' "$T"
```

退出码 0；输出：

```text
/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.c4vThPOqpE/fe
```

以下在该仓库外副本执行；npm 离线、Next 遥测禁用：

```bash
npm_config_offline=true NEXT_TELEMETRY_DISABLED=1 npx tsc --noEmit
```

退出码 0，stdout/stderr 均为空。

```bash
npm_config_offline=true NEXT_TELEMETRY_DISABLED=1 npx eslint
```

退出码 0；完整输出：

```text

/private/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.c4vThPOqpE/fe/app/page.tsx
   136:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   227:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   385:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   431:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   432:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   433:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   443:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   444:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   445:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   446:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   449:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   455:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   456:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   710:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   714:16  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   785:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1181:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1201:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1209:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1230:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1267:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1363:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1707) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1806:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1846:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2089:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/private/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.c4vThPOqpE/fe/app/plaza/page.tsx
  610:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 26 problems (0 errors, 26 warnings)
```

结果为 0 errors、26 warnings，符合 warnings ≤26。

### 尚需浏览器确认

v1.1 对实现的澄清已落实，无剩余实现问题。状态表与实际回调的模拟确认了顺序与调用次数；BL1/BL3 在两个真实引擎中的结束顺序 1→2→3→4→5、每句恰好出声一次，仍按第 0 节/5.2 由 Claude 主会话复测。本次没有运行浏览器或扩大其他代码改动范围。

## v1.2

已按规格末尾“v1.2 追加”完成补强。仅在 `backend/tests/test_tts_ticket_ttl.py` 末尾追加 3 条非退化测试，并在本报告末尾追加本节；没有新建仓库文件。已有用例与实现代码逐字节保持原样，尤其没有修改仓库 `backend/routers/voice.py`。由原后端子代理追加用例，原前端子代理只读审查场景，派任务未传 model 或 reasoning_effort；主代理运行全量、外部副本变异并追加报告。未做 Git 写操作、读取真实环境文件、触碰已有数据库或发起外部网络调用。

### 新增用例与实例数

| 新增用例 | 位置 | 非退化场景与断言 |
|---|---|---|
| `test_expired_newest_ticket_is_cleaned_before_user_cap_evicts_oldest` | `test_tts_ticket_ttl.py:204` | 用户上限 2；A 签 a1、a2，最新的 a2 过期，再签 a3；完整表为 [a1,a3]，两张均可播放。若先用户淘汰再清理，会误删有效 a1，只剩 [a3] |
| `test_expired_newest_ticket_is_cleaned_before_global_cap_evicts_oldest` | `test_tts_ticket_ttl.py:217` | 全局上限 3、用户 20；依次 B:b1、A:a1、C:c1，最新的 c1 过期，再 A:a2；完整表 [b1,a1,a2]，三张均可播放。若先全局淘汰再清理，会误删 b1，变成 [a1,a2] |
| `test_global_cap_evicts_oldest_other_user_ticket_without_caller_preference` | `test_tts_ticket_ttl.py:233` | 全局上限 3、用户 20；依次 A:a1、B:b1/b2，再 B:b3；完整表 [b1,b2,b3]，a1 播放 404，B 三张均可播放。若偏向调用者，会误删 b1，变成 [a1,b2,b3] |

三条独立函数，无参数化。沿用既有关闭限流、清空票表、假 TTS 的夹具；直接 replace expires_at=0，不 monkeypatch 全局时钟。测试文件实例数由 9 增至 **12**；全量由 1542 增至 **1545**，即 `1542+3=1533+12`。本次新建文件数为 0。

### 仓库外副本与变异说明

副本根目录：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.ZmoKTpcamR`；全部运行使用规格指定虚拟环境 Python。复制 backend 时排除 `.env*`、`*.db*`、`.venv`、`__pycache__`、`.pytest_cache`、`*.pyc` 与 uploads。未变异副本位于 control，其源码与仓库一致；三个变异均由 control 独立复制，只修改对应副本的 routers/voice.py，测试文件保持一致。为完整运行既有全量测试，还在副本根目录保留 `docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py` 的相对路径副本，满足既有测试的文件依赖。

- M1：锁内原有每用户淘汰块移到过期清理前，顺序为用户淘汰→过期清理→全局淘汰。
- M2：原有全局淘汰块移到过期清理前，顺序为全局淘汰→过期清理→用户淘汰。
- M3：原顺序不变，只将全局淘汰目标改为调用者自己的最早票；无其票时才退回全局最早。

M3 的错误选择代码仅存在于副本：

```python
oldest = next((key for key, existing in _tts_tickets.items() if existing.user == user), next(iter(_tts_tickets)))
evicted = _tts_tickets.pop(oldest)
```

副本建立/隔离核查实际输出，退出码 0：

```text
M1-user-before-expiry: only external routers/voice.py differs; test file identical
M2-global-before-expiry: only external routers/voice.py differs; test file identical
M3-caller-first-global: only external routers/voice.py differs; test file identical
control voice matches repository; sibling rate_model.py copied for full-suite fixture; repository voice.py unchanged
```

### 结果对照

| 运行位置 / 变异 | 实际 pytest 汇总 | 退出码 | 命中的新增用例 |
|---|---|---|---|
| 原仓库：测试文件 | 12 passed, 11 warnings in 0.80s | 0 | 三条全部通过 |
| 原仓库：全量 | 1545 passed, 11 warnings in 45.75s | 0 | 全部通过 |
| 未变异 control：测试文件 | 12 passed, 11 warnings in 0.79s | 0 | 三条全部通过 |
| 未变异 control：全量 | 1545 passed, 11 warnings in 45.56s | 0 | 全部通过 |
| M1-user-before-expiry：测试文件 | 1 failed, 11 passed, 11 warnings in 1.14s | 1（预期） | 用户清理顺序新例，第 212 行完整表断言失败 |
| M2-global-before-expiry：测试文件 | 3 failed, 9 passed, 11 warnings in 1.15s | 1（预期） | 全局清理顺序新例，第 227 行完整表断言失败；同时命中两条旧用例 |
| M3-caller-first-global：测试文件 | 1 failed, 11 passed, 11 warnings in 1.14s | 1（预期） | 无调用者偏向新例，第 241 行完整表断言失败 |

所有变异运行都执行了测试文件全部 12 个实例，没有删改、跳过任何用例。三种错误实现均至少导致一条新增用例失败；未变异对照的文件与全量均通过。以下附实际命令与完整输出；日志按文本展示，仅去除行尾空格。

所有运行均先设置：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
```

### 原仓库测试文件输出

cwd：仓库 backend/；由后端子代理在最终稿冻结前执行，退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_ttl.py
```

```text
............                                                             [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 11 warnings in 0.80s
```

### 原仓库全量输出

cwd：仓库 backend/；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 13%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 27%]
........................................................................ [ 32%]
........................................................................ [ 37%]
........................................................................ [ 41%]
........................................................................ [ 46%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 74%]
........................................................................ [ 79%]
........................................................................ [ 83%]
........................................................................ [ 88%]
........................................................................ [ 93%]
........................................................................ [ 97%]
.................................                                        [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1545 passed, 11 warnings in 45.75s
```

### 未变异副本测试文件输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.ZmoKTpcamR/control`；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_ttl.py
```

```text
............                                                             [100%]
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 11 warnings in 0.79s
```

### 未变异副本全量输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.ZmoKTpcamR/control`；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 13%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 27%]
........................................................................ [ 32%]
........................................................................ [ 37%]
........................................................................ [ 41%]
........................................................................ [ 46%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 74%]
........................................................................ [ 79%]
........................................................................ [ 83%]
........................................................................ [ 88%]
........................................................................ [ 93%]
........................................................................ [ 97%]
.................................                                        [100%]
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1545 passed, 11 warnings in 45.56s
```

### M1-user-before-expiry 输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.ZmoKTpcamR/M1-user-before-expiry`；退出码 1（变异被测试捕获，符合预期）。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider --tb=short tests/test_tts_ticket_ttl.py
```

```text
.........F..                                                             [100%]
=================================== FAILURES ===================================
_____ test_expired_newest_ticket_is_cleaned_before_user_cap_evicts_oldest ______
tests/test_tts_ticket_ttl.py:212: in test_expired_newest_ticket_is_cleaned_before_user_cap_evicts_oldest
    assert list(voice._tts_tickets) == [a1, a3]
E   AssertionError: assert ['3D_R9DQMPVt...qGBQmg6tMTd4'] == ['X4GKUTPQ2Ay...qGBQmg6tMTd4']
E
E     At index 0 diff: '3D_R9DQMPVtCVQmEDLNtLi93QiNslL5qGBQmg6tMTd4' != 'X4GKUTPQ2AyREirnYIc5bjBzGsNYJK84jfFDIZZECUU'
E     Right contains one more item: '3D_R9DQMPVtCVQmEDLNtLi93QiNslL5qGBQmg6tMTd4'
E     Use -v to get more diff
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_ttl.py::test_expired_newest_ticket_is_cleaned_before_user_cap_evicts_oldest
1 failed, 11 passed, 11 warnings in 1.14s
```

### M2-global-before-expiry 输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.ZmoKTpcamR/M2-global-before-expiry`；退出码 1（变异被测试捕获，符合预期）。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider --tb=short tests/test_tts_ticket_ttl.py
```

```text
....F...F.F.                                                             [100%]
=================================== FAILURES ===================================
_________________ test_user_cap_evicts_only_own_oldest_tickets _________________
tests/test_tts_ticket_ttl.py:96: in test_user_cap_evicts_only_own_oldest_tickets
    assert list(voice._tts_tickets) == other_tickets + own_tickets[2:]
E   AssertionError: assert ['jOslb69cDkx...ededZGRDPatI'] == ['HsXuhCGsvp0...ededZGRDPatI']
E
E     At index 0 diff: 'jOslb69cDkxT5aBfBos6Q6s6--ok2w8ZjmOFE-MlhP8' != 'HsXuhCGsvp0jQdCuZGeY40kAwcwuOx9_7px2GlR2UKk'
E     Right contains one more item: 'OA8oGwJu_V-Q9cQG4I80XFEmcOUIfmpededZGRDPatI'
E     Use -v to get more diff
____________ test_expired_cleanup_precedes_user_and_global_eviction ____________
tests/test_tts_ticket_ttl.py:197: in test_expired_cleanup_precedes_user_and_global_eviction
    assert list(voice._tts_tickets) == [other] + live + [replacement]
E   AssertionError: assert ['dqLLBoDMJWm...5owcpahlpAAw'] == ['oqaGefnVi6k...5owcpahlpAAw']
E
E     At index 0 diff: 'dqLLBoDMJWmSJB-aY7N39AvqwptTVoo5IhFa5J5-nAU' != 'oqaGefnVi6kG4mThrYHVcFE_394q9w2tnlqCF9kDTLE'
E     Right contains one more item: 'X4965ibFjKSFVP8HAw3THTJeec72s-f5owcpahlpAAw'
E     Use -v to get more diff
____ test_expired_newest_ticket_is_cleaned_before_global_cap_evicts_oldest _____
tests/test_tts_ticket_ttl.py:227: in test_expired_newest_ticket_is_cleaned_before_global_cap_evicts_oldest
    assert list(voice._tts_tickets) == [b1, a1, a2]
E   AssertionError: assert ['2iwNYS1Xz45...mRM3fFMMEugo'] == ['JpkXQ4JEQBr...mRM3fFMMEugo']
E
E     At index 0 diff: '2iwNYS1Xz45AyJojoBPj0tcNHGdTH86w9l6P78banJI' != 'JpkXQ4JEQBrv2Mon8BQTcUa_mWpF93PLzr6BhpPj_ok'
E     Right contains one more item: 'v_blhEcWfiMRRFMicX2kB6wX0qwuakrmRM3fFMMEugo'
E     Use -v to get more diff
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_ttl.py::test_user_cap_evicts_only_own_oldest_tickets
FAILED tests/test_tts_ticket_ttl.py::test_expired_cleanup_precedes_user_and_global_eviction
FAILED tests/test_tts_ticket_ttl.py::test_expired_newest_ticket_is_cleaned_before_global_cap_evicts_oldest
3 failed, 9 passed, 11 warnings in 1.15s
```

### M3-caller-first-global 输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.ZmoKTpcamR/M3-caller-first-global`；退出码 1（变异被测试捕获，符合预期）。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider --tb=short tests/test_tts_ticket_ttl.py
```

```text
...........F                                                             [100%]
=================================== FAILURES ===================================
__ test_global_cap_evicts_oldest_other_user_ticket_without_caller_preference ___
tests/test_tts_ticket_ttl.py:241: in test_global_cap_evicts_oldest_other_user_ticket_without_caller_preference
    assert list(voice._tts_tickets) == [b1, b2, b3]
E   AssertionError: assert ['yXn8iQpEa2i...8R_zDT2QYt5s'] == ['Ovfb9vn9UrW...8R_zDT2QYt5s']
E
E     At index 0 diff: 'yXn8iQpEa2isjUoHtH3LRHgWqIBheCL8bZku9hLkkjE' != 'Ovfb9vn9UrWPqc2wUN3xnHDzsg7_KKxrbn0FG1JXIdM'
E     Use -v to get more diff
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_ttl.py::test_global_cap_evicts_oldest_other_user_ticket_without_caller_preference
1 failed, 11 passed, 11 warnings in 1.14s
```

### 追加与不变性核查

保存本次开始前的逐字节快照与其他 343 个已跟踪文件哈希；核查测试文件原内容仍是完整前缀，追加内容恰为三条指定函数，没有其他顶层代码；其他已跟踪文件保持一致，包含仓库 voice.py、所有实现与其他测试。已有暂存的规格/验证/复核文档属于用户已有状态，没有修改。实际输出，退出码 0：

```text
PASS: exactly 3 test functions appended; existing tests byte-identical; 343 other tracked files unchanged including repository voice.py; no new repository files; report unchanged before append
```

`git diff --check` 无输出，退出码 0。本报告仅在末尾追加 v1.2，前文保留。没有未完成项或需要人工确认的实现问题；用户已确认此前复核通过，本次不重新运行浏览器验收。

## v1.3

只执行规格末尾 v1.3：在 `backend/tests/test_tts_ticket_ttl.py` 末尾追加一条跨用户公平测试，并在本报告末尾追加本节。已有用例与实现代码一字不改，没有新建仓库文件。原后端子代理唯一编辑测试文件，未传 model 或 reasoning_effort；主代理负责原仓库全量、外部副本变异/对照与报告。未做 Git 写操作，没有读取真实环境文件、触碰已有数据库或调用外部服务。

### 新增用例

`test_global_cap_evicts_oldest_caller_ticket_without_other_user_preference`，位于 `backend/tests/test_tts_ticket_ttl.py:247`。

- 全局上限设为 3，每用户上限为 20，沿用既有关闭限流、清空票表、假 TTS 夹具。
- 依次 A:a1、B:b1、B:b2，再由 A 签 a2。
- 第 255 行断言完整表顺序为 [b1,b2,a2]；a1 返回 404；b1、b2 以 B 播放为 200，a2 以 A 播放为 200。
- 全局最早票属于调用者 A；正确逻辑仍淘汰 a1，不能为了保留调用者票而淘汰 B 的 b1。错误实现会留下 [a1,b2,a2]，直接触发新增顺序断言。

新增 1 个独立实例，测试文件总数由 12 增至 **13**；后端全量由 1545 增至 **1546**，即 `1545+1=1533+13`。

### 仓库外变异与未变异对照

副本根目录：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.7HGTq5twbp`。control 为未变异 backend 副本；global-other-user-first 为从 control 独立复制的变异副本。复制时排除 `.env*`、`*.db*`、`.venv`、`__pycache__`、`.pytest_cache`、`*.pyc` 和 uploads；为了既有全量测试的文件依赖，副本根保留 `docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py` 的相对路径副本。全部运行使用规格指定的原虚拟环境 Python，不新增依赖。

变异仅在外部副本的 `routers/voice.py` 修改全局淘汰目标：优先选择 `existing.user != user` 的全局最早票，无此类票时才回退全局最早；过期清理、每用户淘汰、全局容量判断和取消预热步骤均不改。错误代码如下，仅在副本存在：

```python
oldest = next((key for key, existing in _tts_tickets.items() if existing.user != user), next(iter(_tts_tickets)))
evicted = _tts_tickets.pop(oldest)
```

副本设置与隔离核查实际输出，退出码 0：

```text
PASS: external mutant only changes global eviction to oldest non-caller ticket; all test files identical; control voice equals repository; repository voice.py unchanged
```

### 结果

| 运行 | 实际输出汇总 | 退出码 |
|---|---|---|
| 原仓库测试文件 | 13 passed, 11 warnings in 1.10s | 0 |
| 原仓库全量 | 1546 passed, 11 warnings in 50.70s | 0 |
| 未变异副本测试文件 | 13 passed, 11 warnings in 0.99s | 0 |
| 未变异副本全量 | 1546 passed, 11 warnings in 51.29s | 0 |
| 优先淘汰非调用者的变异副本：测试文件 | 1 failed, 12 passed, 11 warnings in 1.05s | 1（预期） |

唯一失败的是本次新增测试的第 255 行完整票表断言。变异副本运行了测试文件全部 13 个实例，原 12 个仍通过，证明新用例补到了原有测试缺口；未变异副本的测试文件与全量均通过。没有删除、跳过或更改任何已有用例。下面附实际命令与完整输出，按文本展示，仅去掉行尾空格。

所有命令使用：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
```

### 原仓库测试文件：完整输出

cwd：`仓库 backend/`；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_ttl.py
```

```text
.............                                                            [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
13 passed, 11 warnings in 1.10s
```

### 原仓库全量：完整输出

cwd：`仓库 backend/`；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 13%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 27%]
........................................................................ [ 32%]
........................................................................ [ 37%]
........................................................................ [ 41%]
........................................................................ [ 46%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 74%]
........................................................................ [ 79%]
........................................................................ [ 83%]
........................................................................ [ 88%]
........................................................................ [ 93%]
........................................................................ [ 97%]
..................................                                       [100%]
=============================== warnings summary ===============================
../../../../backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1546 passed, 11 warnings in 50.70s
```

### 未变异副本测试文件：完整输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.7HGTq5twbp/control`；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_tts_ticket_ttl.py
```

```text
.............                                                            [100%]
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
13 passed, 11 warnings in 0.99s
```

### 未变异副本全量：完整输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.7HGTq5twbp/control`；退出码 0。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider
```

```text
........................................................................ [  4%]
........................................................................ [  9%]
........................................................................ [ 13%]
........................................................................ [ 18%]
........................................................................ [ 23%]
........................................................................ [ 27%]
........................................................................ [ 32%]
........................................................................ [ 37%]
........................................................................ [ 41%]
........................................................................ [ 46%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 74%]
........................................................................ [ 79%]
........................................................................ [ 83%]
........................................................................ [ 88%]
........................................................................ [ 93%]
........................................................................ [ 97%]
..................................                                       [100%]
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1546 passed, 11 warnings in 51.29s
```

### 变异副本测试文件：完整输出

cwd：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/tmp.7HGTq5twbp/global-other-user-first`；退出码 1（变异被新测试捕获，符合预期）。

```bash
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider --tb=short tests/test_tts_ticket_ttl.py
```

```text
............F                                                            [100%]
=================================== FAILURES ===================================
__ test_global_cap_evicts_oldest_caller_ticket_without_other_user_preference ___
tests/test_tts_ticket_ttl.py:255: in test_global_cap_evicts_oldest_caller_ticket_without_other_user_preference
    assert list(voice._tts_tickets) == [b1, b2, a2]
E   AssertionError: assert ['QtbBnPW6aBZ...m5ghnczvXPvQ'] == ['LgiV3rMy3ee...m5ghnczvXPvQ']
E
E     At index 0 diff: 'QtbBnPW6aBZTPf1GikHbVjL9J25gwuCLq3H8l8AD8sU' != 'LgiV3rMy3eeKJZcovP8DLSd4Q2jy0vGZ0p0OWmf1gi4'
E     Use -v to get more diff
=============================== warnings summary ===============================
../../../../../../../../Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 1 warning
tests/test_tts_ticket_ttl.py: 9 warnings
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

tests/test_tts_ticket_ttl.py::test_default_ttl_matches_response_and_ticket_expiry
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_tts_ticket_ttl.py::test_global_cap_evicts_oldest_caller_ticket_without_other_user_preference
1 failed, 12 passed, 11 warnings in 1.05s
```

### 追加与不变性核查

与本次开始前快照比较，测试文件原内容完整保留，只新增一个指定函数；另外 344 个已跟踪文件哈希全部相同，包括仓库 voice.py、所有实现代码和其他测试。原报告追加前也完全一致，本次未新增仓库文件。实际审计输出，退出码 0：

```text
PASS: exactly 1 test appended; all prior test bytes preserved; 344 other tracked files unchanged including repository voice.py; no new repository files; report unchanged before append
```

本报告仅在末尾追加 v1.3，前文保留。`git diff --check` 无输出，退出码 0。所有 v1.3 项已完成，无未决问题，不运行浏览器或扩大实现改动范围。
