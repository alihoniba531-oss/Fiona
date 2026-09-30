# 复核报告（票据 150 秒任务，Opus 5.5 多视角）

- **结论：通过。** 三个视角都判 pass。对抗验证列表为空，没有 CONFIRMED 或 PLAUSIBLE 的必须修复项。各视角的 6 条发现都是 optional，其中 1 条只涉及验证方法，与代码无关。

## 各视角结论一览

| 视角 | 结论 | 核验条数 | 通过 | 未验证 | 发现 |
|---|---|---|---|---|---|
| frontend-resume | pass | 14 | 13 | 1（15 秒余量能否覆盖长句） | 1 条 optional |
| backend-ttl-cap | pass | 7 | 7 | 0 | 3 条 optional |
| spec-regression | pass | 19 | 18 | 1（T7：03-report.md 的内容） | 2 条 optional（其中 1 条只涉及验证方法） |

## 验收标准逐条核验

### 复核前提：被审代码与实测环境一致

- **复核期间代码没变，浏览器实测跑的就是被审代码：通过。**
  - frontend-resume：复核开始和收尾时，page.tsx、ttsTicket.ts、voice.py 的 sha 一致（389ab742…、e9c6c1ee…、969473f9…）。当前 diff 与 review.diff 比对结果为 SAME。
  - 3031（fe-ttl2）的源码与工作区 cmp 一致，`.next` 产物里有 `expiresInMs:Math.min(6e5,Math.max(1e3`。3032（fe-base4）的源码与 dc5336a 一致。8031 的 cwd 是本 worktree，没有 TTSV_ 覆盖，默认 150 秒。
  - spec-regression：`diff -rq` 显示 3031 与 worktree 的 frontend 相同。BUILD_ID 时间 10:26:17 晚于 page.tsx 的 10:21，8031 的启动时间 10:29 晚于 voice.py 的 10:06。新 bundle 里有 expires_in，基线 bundle 里没有。

### 第 0 节：白名单与已有测试

- **改动文件都在白名单内：通过。**
  - `git status --porcelain --untracked-files=all` 列出的是 voice.py、test_tts_private_tickets.py、ARCHITECTURE.md、page.tsx、ttsTicket.ts、新测试 test_tts_ticket_ttl.py，以及本任务目录下的 02-spec、03-report、03-verification。
  - `git diff dc5336a --stat -- '*.txt' '*.json' '*lock*'` 输出为空（spec-regression）。
- **已有测试只改了授权的那一行（T2）：通过。**
  - test_tts_private_tickets.py 第 39 行从 `<= 60` 改为 `== 150`，1 insertion、1 deletion。
  - 规格写的 `== voice.TTS_TICKET_TTL_SECONDS` 只是「例如」，改成字面量也符合要求。其他已有测试没有改动，也没有删除或跳过的测试（backend-ttl-cap、spec-regression）。

### 3.1 后端：有效期与每用户上限

- **TTL 为 150；expires_at 和 expires_in 都在请求时读取；三处到期判断的边界一致：通过。**
  - voice.py:32 定义 `TTS_TICKET_TTL_SECONDS = 150`。:311 和 :331 都在函数体内读取这个常量。
  - 三处判断分别是 :135 的 `monotonic() >= expires_at`、:316 的 `expires_at <= now`、:165 的 `expires_at > monotonic()`，边界一致。
  - backend-ttl-cap 的变异 M1/M2/M3/M4/M5/M5b 全部被杀死；spec-regression 的变异 M6/M11 也被 test_ttl_is_read_on_each_request 杀死。
  - 小问题：同一请求里常量读了两次（:311、:331），只在并发 monkeypatch 时才可能不一致，不影响结论。
- **每用户上限的顺序、范围、预热取消和锁范围符合规格：通过。**
  - voice.py:314-326 在同一个 `with _tts_tickets_lock` 里依次执行：过期清理 → 淘汰本用户最早的 len−cap+1 张，并逐张调用 `_cancel_tts_prewarm` → 原有全局淘汰（与 dc5336a 逐字相同）→ 写入。
  - dict 的插入顺序就是签发顺序：对已有键只做赋值，没有先 pop 再插入的写法。锁的嵌套顺序与原来一致，是 `_tts_tickets_lock` → `waiters_lock`。
  - :40-42 的注释写了规格要求的两点。
  - 变异：backend-ttl-cap 的 M6–M11、M14–M17，spec-regression 的 M1–M5、M8、M9 全部被杀死。全局淘汰不取消预热的变异（spec-regression 编号 M10）由已有的 `test_invalidated_prewarm_discards_its_result[evicted]` 杀死。
- **上限 64 对正常使用是安全的：通过。**
  - 单个标签页里 tryPrefetch 只在没有预取句时才换票，所以同时在用的票最多两张，而且总是本用户最新签发的两张。「帮我读」（page.tsx:1247）走的是同一个队列。
  - WebKit 的 Range 请求用的是正在播放的那张票，它总在最新两张之内。
  - 多标签页的边界情况见可优化项第 3 条。
- **有效期变长的副作用有定量评估：通过。**
  - 表项仍受 2048 的硬上限约束，最坏情况约 15.7MB（纯汉字约 7.9MB）。缓存音频仍是全局 64MB、单票 8MB。
  - 票据泄露窗口从 60 秒变为 150 秒。但票据绑定用户、最多用 4 次、用的是 token_urlsafe(32)，实际影响很小。
  - 把全局 2048 张挤满需要的账号数从至少 18 个升到 32 个（要造成跨用户淘汰需 ≥33 个），需要的 IP 数降到 4 个（突发时 3 个）。
  - 正在用的票的存活时间是 min(150, 2048/R)，不会比改动前短。

### 3.2 前端 ttsTicket.ts

- **返回 `{ticket, expiresInMs}`，只接受有限正数，否则按 60 秒，再夹在 [1s, 600s]；其余流程不改：通过。**
  - frontend-resume 用 transpileModule 编译后在 Node 里实测：
    - 缺失、0、-5、`"150"`、null、true、NaN、±Infinity 都得到 60000。
    - 150 得到 150000，20 得到 20000。
    - 0.2 和 1 夹到 1000；600、601、1e308 夹到 600000。
    - 缺 ticket、ticket 为空串、响应体是数组，都返回 null。
    - 先 429 再 200 时，onWait 和 onWaitEnd 都会触发。
  - spec-regression：diff 只改了返回类型和 :100-103，429、退避、中止相关代码没有变化。唯一的调用方是 page.tsx:866。

### 3.3 前端 page.tsx

- **mkTtsAudio 记录到期时刻的位置和迟到保护的顺序正确：通过。**
  - :883-887 的顺序是：检查 canUse 和 ticket → 设置 src → 记录到期时刻 → 再检查 canUse → load()。
  - :859 把到期时刻初始化为 null，isTicketStale 遇到 null 返回 false（:94-97），所以还在等票的预取句不会被误判为超龄。
- **统一用 isTicketStale 判断，旧常量已删净：通过。**
  - :958 改为 `if (prepared && isTicketStale(prepared))`，之后的放弃流程没有变化。
  - `grep TTS_PRELOAD_MAX_TICKET_AGE_MS\|ticketAt\b` 在 page.tsx 上 0 命中；同一条 grep 在 dc5336a 上命中 6 行，作为正控。`tts/ticket` 在前端只出现在 ttsTicket.ts:76 一处。
- **票还够用时，「点此播放」的处理与基线一字不差（3.3-4）：通过。**
  - :1100-1104 与 dc5336a 对照没有差异。
  - 实测场景 BL2（默认 150 秒，等 70 秒）：两个引擎点击后只为街上、早点、阳光三句换票，冬天和屋檐没有重换。5 句按序读完，0 次 error。
- **票不够用时的处理顺序符合 v1.1，而且全程同步、留在用户手势内：通过。**
  - :1084-1098 中间没有 await，deps 已补上 playNextInQueue。
  - 两个视角手推了三种情形（预取句已解锁、未解锁、没有预取句），最终队列都是 [被拦句, 原预取句, 其余]。
- **每句恰好出声一次，顺序正确，0 次 error：通过。**
  - frontend-resume 在 Chromium 和 WebKit 上都跑了三个场景，结束顺序都是 [冬天, 屋檐, 街上, 早点, 阳光]，每句 1 张票、1 次 playing、0 次 error：
    - BL1：expires_in 改成 20，等 30 秒，再让点击前的旧票返回 404。
    - BL3：真等 160 秒，让后端真正过期。
    - NOUNLOCK：预取句的元素没有解锁。
  - 正控：基线 3032 跑 BL3，冬天那句丢了，脚手架能识别出来。
  - spec-regression 另外独立实测了 Chromium（邀请码 237）和 WebKit（238）。对照组不改写 expires_in 时，被拦句沿用同一张票直接重播。
- **元素归属与释放正确：通过。** 所有场景都只有 2 个 audio 元素，同时出声的最多 1 个，两个元素交替出声。releaseTtsAudio 会先中止监听再清空 src（:835-846）。
- **被释放的元素在同一个手势里重新解锁：通过。** NOUNLOCK 场景下，静音 play() 调用时 `navigator.userActivation.isActive` 为 true。调用时机是 Chromium 点击后 465ms、WebKit 点击后 31ms。
- **重换票后仍被拒时，再次显示提示，不自动循环：通过。** REREJECT 场景在两个引擎上都是：提示先隐藏后再次出现，之后 9 秒内没有新的换票请求。再点一次后 5 句按序读完。
- **重换票遇到 429 时照常等待：通过。** INJ429=4 场景下两个引擎都显示倒计时并在结束后隐藏，然后 5 句按序读完，0 次 error。
- **限速等待中做其他操作没有残留：通过。**
  - STOP、OFF、NEW 三种操作后都没有新的换票和出声。
  - SEND 场景下旧句不再出声，新回复在共享退避结束后才换票，与既有 S5 的语义一致。
- **150 秒有效期下不会误触发重换：通过。**
  - 普通消息只换票 5 次。
  - S10 场景在默认 150 秒下屋檐没有重换；expires_in 改成 20 后屋檐只重换一次，也就是 S10'。
  - 对照组证明判断确实随 expires_in 生效。expires_in=5 时每句只重换一次，没有循环。
- **15 秒余量能否覆盖长句：未验证。**
  - 假 TTS 每句只有约 1 秒，测不了长句。
  - 可能的风险：票还剩 15–47 秒时走直接播放，如果 WebKit 在播放中途再发 Range 请求，就会拿到 404。
  - 实测时 WebKit 在加载阶段已经把整段取完，Chromium 是一次流式 200，所以风险较低。15 秒是规格给定的值，这也不是回归（frontend-resume）。

### 3.4 文档

- **ARCHITECTURE.md 那一行与代码一致：通过。** :61 写的是 150 秒、每用户 64 张、超出先淘汰自己最早的，与 voice.py:32/42/319-322 一致，这个文件的 diff 也只改了这一行。
- **其他文档没有「票据 60 秒」的说法：通过。** 排除 docs/tasks 后全库检索，只有 DEPLOYMENT.md:30 提到「短时、限次」，没有写秒数（spec-regression）。

### T3 新测试

- **规格要求的 1–6 条都有用例覆盖：通过。**
  - 共 9 个用例，逐条对应（spec-regression）。
  - 连跑 15 轮没有抖动（backend-ttl-cap）。
- **测试能否抓住错误实现：大部分通过，有强度缺口。**
  - backend-ttl-cap 的 17 个变异都被杀死，4 个存活：M12、M13、M20 与过期清理的顺序有关，M18 与全局淘汰的对象有关。
  - spec-regression 的 M7（每用户淘汰挪到过期清理之前）也存活。
  - 实现本身的顺序是正确的，缺口只在测试强度上，列入可优化项第 1、2 条。
  - 过程备注：backend-ttl-cap 的变异 M19（关掉到期判断）让已有测试真的去调用 DashScope，握手返回 401。这是复核方的变异引起的，不是实现的问题，请求没有成功。

### 5.1 验证命令

- **后端：通过。**
  - 新测试文件单独跑 9 passed。
  - 全量 `1542 passed, 11 warnings`，退出码 0。
  - spec-regression 用 git archive 导出基线实跑，全量是 1533 passed，1533 + 9 = 1542。
- **前端（在仓库外的副本里跑）：通过。**
  - `tsc --noEmit` 退出码 0。
  - eslint 0 errors、26 warnings，与基线持平，改动的行没有新增警告。
  - `npm run build` 退出码 0。
- **在仓库根目录跑 grep 和 status：通过。** 结果与前面的第 0 节、3.3 一致。

### 回归

- **S1、S8、S9（限流等待）两个引擎：通过。**
  - 状态码序列、倒计时、退避期间 0 请求都符合预期，5 句按序结束，同时出声最多 1 个。
  - WebKit 的 S9 第一次登录超时，重跑通过。
  - 脚手架的 ended_in_order 偶尔报 false，在基线上同样出现，原因是请求竞态。按文本看结束顺序始终是 1→5，不算回归。
- **A0、B、F（朗读自动播放）两个引擎：通过。**
  - 5 句按序播放，被拦提示 2ms 内出现，关掉朗读后没有残留声音。
  - Chromium 停止延迟 558ms，基线 538ms，同一量级。
- **没有提示时，输入区截图与基线逐像素相同：通过。**
  - 两个引擎 × 两种宽度共 4 组，sha256 两两相同，差异 bbox 为 None。
  - 正控能检出改动的 1 个像素。一开始 getbbox 只比了 alpha 通道，已发现并改正后重跑。

### 提交卫生

- **没有密钥、.env、数据库或构建产物：通过。**
  - 所有改动都是文本文件。
  - 密钥正则扫描和邀请码扫描都是 0 命中，两者的正控都能命中。
  - node_modules 和 tsbuildinfo 已被 .gitignore 忽略。

### T7

- **03-report.md 的内容：未验证。** 按任务要求没有读内容，只确认文件存在（46658 字节），并用计数扫描确认没有密钥和邀请码。

## 必须修复项

无。对抗验证列表为空，三个视角也没有提交任何必须修复级别的发现。

## 被驳回的候选

无。对抗验证列表为空，没有候选进入投票。

## 可优化项

按价值从高到低排列，都不阻塞本单。

1. **「过期清理先于淘汰」这条测试名不副实**（backend-ttl-cap 和 spec-regression 各自独立发现，两边报告的行号分别是 test_tts_ticket_ttl.py:187-201 和 :177-191）
   - 问题：用例里设成过期的那张票，恰好也是本用户最早的票，所以无论先做过期清理还是先淘汰，结果都一样。
   - 证据：M12、M13、M20、M7 在新测试文件上都存活，M13 跑全量仍是 1542 passed。
   - 建议：让过期的那张不是最早的。
     - 例（a）：每用户上限 2，a1 有效、a2 过期，再签 a3，断言表里是 [a1, a3]。
     - 例（b）：全局上限 3，依次签 b1、a1、c1 并把 c1 设为过期，再由 a 签一张，断言表里是 [b1, a1, a2]。
   - 两个视角都在副本上加了探针：原实现能通过，上述变异都会失败。
2. **「全局上限原逻辑不变」这条测试的场景是退化的**（backend-ttl-cap，test_tts_ticket_ttl.py:160-170）
   - 问题：签发顺序 [a, b, c, a, b] 是轮转的，每次全局淘汰时，全局最早的票恰好也是调用者自己最早的票。
   - 证据：M18（全局淘汰改成优先淘汰调用者自己的票）存活，全量仍是 1542 passed。
   - 建议：补一段不轮转的序列。全局上限 3、每用户上限 20，依次签 a1、b1、b2、b3，断言表里是 [b1, b2, b3]。
3. **同账号多标签页或多设备时，被拦句的票可能被每用户上限淘汰**（backend-ttl-cap，voice.py:40-42、:319-322；page.tsx:92、:929）
   - 问题：前端只根据 expires_in 判断票还够用，但这张票在后端可能已被其他标签页挤掉。点「点此播放」后 /tts/stream 返回 404，finishCurrentTts 会静默跳过这一句。
   - 触发门槛：135 秒内同账号签发 ≥63 张，约为另外 2 个标签页同时连续朗读。只有 60 秒内签满（约 4–5 个标签页同时读）时，新版才会比基线差。
   - 建议：在注释里写明「只持有两张」的前提只对单个会话成立；以后可以让前端对「还没出声就 error」的当前句按原文重新换票。
4. **会话号变化后，「点此播放」的两条路径对被拦句处理不一致**（frontend-resume，page.tsx:1084-1104、1249-1258）
   - 问题：handleConfirmTts 只把会话号加 1，不清队列。之后如果走「够用」路径，被拦句和预取句会被跳过（这是基线原有行为）；如果走「不够用」路径，这两句会在新会话里被重新读出。
   - 这只是代码推演，没有实测，也不是本次改动引入的回归。
   - 建议：两条路径统一处理；或者让 handleConfirmTts 在有被拦句时先 clearTtsQueue。
5. **验证方法提示：WebKit 上不要用 `route.fetch` 改写 /api/tts/ticket**（spec-regression）
   - 现象：页面跳到 `/?reason=expired`，这是与本次改动无关的假失败。
   - 做法：改用页面内的 fetch 包装（add_init_script），参考 scratchpad/rv_opus/bl_rewrite.py 的 JSREWRITE 分支。
6. **验证方法提示：丢句的正控请用 BL3，不要用 BL1**（frontend-resume）
   - 原因：基线在 Chromium 上空闲 30 秒后点击，不会重新请求 stream。所以规格 5.2 里「BL1 在基线上应该丢句」这个正控不一定每次都能复现；BL3 让后端真正过期，结果稳定。

## 给实现方的修改指令

无。