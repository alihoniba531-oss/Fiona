# 复核报告（v3 针对性复核，Opus）

- **结论：不通过。** 有 1 项 CONFIRMED 必须修复：F2b 的「取较大值」用例分不出「取最大值」和「取最后一个不通过项」。对抗验证 2 票都没能驳倒。修法只需在参数表里加一行，改的是本轮新增的测试，没有超出白名单。F1、F3、白名单这几部分全部通过。
- **说明：** 本轮 Fable 额度已用完，经用户同意改用 Opus 复核。

## F1 / F2 / F3 / 白名单逐条核验

### F1（前端：预取票超龄重换）

| 核验项 | 结果 | 证据 |
|---|---|---|
| 实测的不是旧构建 | 通过 | 3031 端口的进程 41761 的 cwd 是 `scratchpad/tts/fe-v3`。它的 page.tsx sha1 与工作区一致（c276a785…），ttsTicket.ts 也一致（f35d0791…）。BUILD_ID 时间 05:58:34，晚于源码的 05:49:43。产物 chunk `2j24njfx7xcgy.js` 里有 `n.ticketAt=Date.now()` 和 `Date.now()-e.ticketAt>45e3`。复核结束时 page.tsx 的 sha 没变，它的 diff 与 v3-incremental.diff 里 page.tsx 那一段逐字相同 |
| ticketAt 只在拿到票、设置 src 的那一处记录，迟到保护的顺序不变 | 通过 | :80 声明，:854 初始为 null，:879 设 src，:880 `prepared.ticketAt = Date.now()`。grep 确认只有这一处赋值。「canUse 与 ticket → src → canUse → load()」的顺序原样保留 |
| 模块级常量 `TTS_PRELOAD_MAX_TICKET_AGE_MS = 45_000`，注释符合规格 | 通过 | page.tsx:90-92。注释写明了后端 60 秒过期、给开始播放留余量、预取票龄不超过上一句的播放时长、单句最长约 40 秒，与 v3.2 原文一致 |
| 只在预取句转为当前句时判断超龄；放弃的顺序是 releaseTtsAudio → 文本放回队头 → 走现有 mkTtsAudio 分支 | 通过 | :951-958 在取出 ttsPreloadRef 并置空之后判断，然后依次 release、unshift、prepared=null，再进入 :959 原有的 `if (!prepared)`。tryPrefetch、resumeBlockedTts、finishCurrentTts 都没改。还在等票的预取句 ticketAt 为 null，不会被放弃：R10_new 里新回复的第 2 句在退避中等票，最后正常出声 |
| 放弃预取后，新换的票能拿到空闲的音频元素 | 通过 | R10 中，第 2 句的重换票在第 1 句 ended 之后发出：Chromium 隔 1ms，WebKit 隔 0ms，都立刻拿到 200 并出声。所有场景 audio_elements=2、max_sounding=1 |
| 放回的文本不重复、不乱序 | 通过 | R10 两个引擎、原版 S10 两个引擎，ended 顺序都是 冬天→屋檐→街上→早点→阳光，每句一次。「屋檐下」恰好换票 2 次，其余每句各 1 次。原版 S10 的 statuses 为 [429,200,429,200,200,200,200,200]，sentence_order_ok=true |
| S10 已修复（两个引擎） | 通过 | R10 Chromium：5/5 按序，0 次 error，旧票转为当前句时票龄 65.81s，已重换；限速提示 1.46s 出现、65.47s 消失。WebKit：5/5，0 次 error，票龄 65.21s。原版 S10 两个引擎都是 ended=5、ended_in_order=true、errors=[]（all_ok_ended=false 是统计口径的问题，见可优化项） |
| 负对照：关掉 F1 能复现丢句 | 通过 | 用 Playwright 路由把 `45e3` 改成 `45e9`，替换计数为 1，仓库没动。Chromium 上旧票在 67.36s 请求 /tts/stream，返回 404，67.51s 报 error，ended 里少了第 2 句。修复版里旧票放弃后再也没有被请求 |
| 不该重换时不会重换 | 通过 | R10_30：转为当前句时票龄 35.86s，只换票 1 次，5/5，0 次 error。S8 两个引擎都是 5 次 200，5/5，没有提示 |
| 重换票遇到限流照常等待并显示提示 | 通过 | R10_re429：Chromium 上提示 67.17s 出现、70.41s 消失，第 2 句 70.97s 出声，5/5。WebKit 上提示 65.92→68.93s，5/5 |
| 与被拒提示、「点此播放」的配合 | 通过 | R10_blk：被拒提示 67.85s 出现；68.68s 点击后，提示 69.37s 消失，第 2 句 69.44s 出声，之后按序，0 次 error。两种提示没有同时出现。WebKit autoplay B：5/5 |
| 「不听了」 | 通过 | R10_stop：7.23s 点击，提示 7.97s 消失；此后 72s 内 0 次换票、0 次出声，退避到期后也没有请求 |
| 新消息打断 | 通过 | R10_new：旧回复的票 0 次出声。新回复按共享退避等到 65.5s，5/5 按序，0 次 error |
| 关朗读和切换会话 | 通过 | autoplay F：playing_after_off=0。D：old_playing_after_interrupt=0，第二轮 5/5。切账号（:1134）、切会话（:1259）、发消息（:1396）都会先调 clearTtsQueue。「帮我读」（:1232）不清队列，这是原有行为，不构成回归 |
| 正常场景没有回归（S8 / A0） | 通过 | S8 两个引擎都是 5/5，没有提示。A0 Chromium：首音 863ms，句间空档 [62,67,64,66]ms，没有被拒。releaseTtsAudio 是依赖为空数组的稳定回调，加进 deps 不改变 playNextInQueue 的身份 |
| 45 秒阈值的依据 | 通过 | voice.py:32 定义 `TTS_TICKET_TTL_SECONDS=60`。MAX_CHUNK=250，按拟合公式 0.156×250+0.1 约 39.1s。开始播放时浏览器带 bytes=0- 重新请求，而放弃判断之后立刻 play，所以余量有 15s |
| 长句播放途中票龄超过 60 秒再发 Range 请求，是否会 404 | 未验证 | 假 TTS 每句约 1 秒，造不出这种情形。这属于 TTL 60 秒的原有设计，与 F1 无关 |
| tsc / eslint | 通过 | 在 sha 相同的 fe-v3 副本里跑：`npx tsc --noEmit` 退出码 0；eslint 0 errors、25 warnings，与 v2 记录一样多，没有新增 |

### F2（后端测试加强）

| 核验项 | 结果 | 证据 |
|---|---|---|
| F2a 第 1 条（用户字数闸拒绝）能让「逐项 test、通过就立刻 hit」的错误实现失败 | 通过 | 变异体 MUT=sequential：本文件 2 failed, 17 passed，挂的正是两条 F2a，断言为 `(118, 0, 239, 5700) == (119, 0, 239, 5700)`。全量 2 failed, 1527 passed，说明原有 14 条用例抓不到这个变异。对照组都是 19 passed |
| F2a 第 2 条（最后一道 IP 字数闸拒绝）能让逐项 hit 的错误实现失败 | 通过 | 断言为 `(118, 1400, 238, 0) == (119, 1700, 239, 0)`。drop_ipchars 变异体下两条 F2a 都失败 |
| F2a 断言数值正确 | 通过 | 按配置推算应为 (119, 0, 239, 5700) 和 (119, 1700, 239, 0)，测试文件 204-222 行、230-248 行与之一致 |
| **F2b 取所有不通过项里的最大 reset（取较大值）** | **不通过** | 三组 reset_offsets 分别是 (2.0, 9.0)、(1.25, 2.01)、(-10.0, -0.25)，较大值都在最后一项。last_failed 变异体下本文件 19 passed、全量 1529 passed，完全存活。详见必须修复项 |
| F2b 小数秒向上取整 | 通过 | (1.25, 2.01) 期望 3。int、round 变异体失败（2 == 3），floor+1 变异体失败（10 == 9），all_checks_max 变异体三组全失败。sum_ceil 与原实现数学上等价，不算漏洞 |
| F2b 已过去的重置时间给 1 | 通过 | (-10.0, -0.25) 期望 1，no_floor 变异体失败（0 == 1）。`ceil(x) or 1` 和取 abs 两种写法能存活，见可优化项 |
| F2b 的 monkeypatch 不影响其他测试 | 通过 | teardown 后 time_restored=True，bound_self_ok 和 func_ok 都是 True。打乱顺序（种子 1-8）并重复 3 次，每次 57 passed；把 F2b 挪到全量最前面跑，1529 passed |
| 后端全量 1529 passed，本文件 19 条（14 + 5） | 通过 | 两个视角都独立跑过：全量 1529 passed（45.19s / 44.54s），本文件 19 passed |

### F3（规格勘误）

| 核验项 | 结果 | 证据 |
|---|---|---|
| 字数额度按换票计；一张票最多用 4 次；票没缓存时，每用一次都可能重新合成 | 通过 | 字数只在 voice.py:283-296 的 /tts/ticket 扣；/tts/synthesize 和 /tts/stream 不限流。voice.py:38 定义 `TTS_MAX_TICKET_USES = 4`，:138 检查。缓存逻辑在 :158-181，没缓存时在 :145-155 重新合成 |
| 固定窗口从第一次计数开始算，跨窗口的短时间内约为 2 倍 | 通过 | limits 5.8.0 的 MemoryStorage.incr 在第一次计数时设置过期时间。实测 "10/2 seconds" 下 0.11 秒内拿到 19 个，约 1.9 倍。slowapi 默认策略就是固定窗口（extension.py:247） |
| /tts/ws 不受这套限流约束 | 通过 | voice.py:484-492 没挂 limiter。main.py:107 注明不设全局 default_limits。tts_ws.py 只有单连接上限 |
| 「比原来收紧」的比例结论仍然成立 | 通过 | 基线 61fc01f 同样有票据复用 ×4、`20/minute` 固定窗口、/tts/ws 和 WebKit 预热，所以倍数两边相同：单账号 2000 对基线单 IP 6000，是三分之一 |
| 勘误的位置和形式（§1.3 末尾，只追加，标明 2026-09-30） | 通过 | hunk 为 `@@ -78,0 +79,2 @@`，只新增 2 行，位于「## 2. 目标」之前，没有删除。五条陈述与 v3.2 F3 逐条对应 |

### 白名单

| 核验项 | 结果 | 证据 |
|---|---|---|
| diff 只落在 v3.1 白名单允许的位置 | 通过 | page.tsx +14/−2，全部是 F1。测试文件 `@@ -200,0 +201,94`，纯追加，前 200 行逐字节不变。02-spec `@@ -78,0 +79,2`，纯追加。03-report `@@ -454,0 +455,476`，按行数和字节前缀核对为纯追加，内容没读 |
| 禁改文件与 tts-ratelimit-v1 基线一致 | 通过 | `git diff refs/fiona-baselines/tts-ratelimit-v1 -- backend/rate_limit.py backend/routers/voice.py frontend/lib docs/ARCHITECTURE.md` 输出为空，也没有未跟踪文件。rate_limit.py 的 mtime 是 05:51:41，在 Codex 运行期间，但内容与暂存区相同，符合规格里「临时改错实现验证后还原」的做法 |
| 当前 diff 与快照一致 | 通过 | cur.diff 与 v3-incremental.diff 逐行一致 |
| 03-verification.md 和截图的改动 | 通过（不算实施方越界） | mtime 是 06:11:46，晚于 Codex 结束（05:56）和快照（06:01）。codex-v3b.log 最后一次 git status 里它们仍是 A（未改动），可以判断是主会话 v3.4 实测时产生的 |

## 必须修复项

### M1. F2b 的「取较大值」用例分不出「取最大值」和「取最后一个不通过项」（CONFIRMED，2/2 票成立）

- **位置：** `backend/tests/test_tts_ticket_rate_limit.py`，F2b 的 parametrize。复核视角记为 253-259 行，对抗验证实测参数表在 256-262 行，数据行在 258-260 行。
- **缺陷：** 三组数据的较大 reset 都放在第二个，也就是最后一个不通过项上。所以「循环覆盖 reset_time、取末项」的错误实现（last_failed / last_list / last_loop）在三组上都恰好得到 9 / 3 / 1。queried 断言只检查查询顺序，挡不住它。
- **票数与理由：**
  - **第 1 票：** 用自己写的插件 mut140plug 独立复现。正控有效：first_failed 和 min_failed 都被杀。last_failed 下本文件 19 passed，全量 1529 passed。又用真实 limiter 做了对照：用户闸 1/10s 在前、IP 闸 2/10s 在后，IP 窗口开得更早。正确实现的 retry_after 是 9，last_failed 给出 6，客户端会提早重试，再吃一次 429。真实的四道闸正是用户在前、IP 在后，所以线上可能出现这种情况。
  - **第 2 票：** 用另一个插件 mymut 独立复现，正控 first 被杀。last_list 和 last_loop 本文件都是 19 passed，last_list 全量 1529 passed。规格 02-spec.md:104 写的是「所有不通过项……的最大值」，:477-478 写的是「重置时间不同时取较大值」，都是与顺序无关的最大值。v2 复核的 E2 也特意测过两种顺序：10.2/50.2 返回 51，40.5/5.5 返回 41。
  - **两票共同的保留意见：** F2b 的条文没有像 F2a 那样明写「必须能让错误实现失败」。这只影响定级，推不翻缺口本身。F2 本来就是为了修 04-review-v2 里变异体存活的问题；M3（只取第一项）已经被杀，对称的「只取最后一项」却漏掉了。
- **实现本身没有错：** rate_limit.py:53-56 的 `max(...)` 是对的，问题只在测试不够强。
- **修法验证：** 两个视角都在副本里追加过 `((9.0, 2.0), 9)`。正确实现 4 passed；last_failed / last_list / last_loop 都只在新增的这一行失败（`assert 2 == 9`）；first 变异体照样被杀。

## 被驳回的候选

无。本轮只有 M1 进入对抗验证，2 票都判成立。

## 可优化项（已去重，本轮不强制）

1. **被拒提示下当前句等超过 60 秒再点「点此播放」，Chromium 仍会不提示地跳过这一句。** 在 BLK65 场景里，第 1 句的旧票返回 404，被跳过；预取的第 2 句被 F1 重换后正常出声。这是 resumeBlockedTts（page.tsx:1071-1085）原有的缺口，v3 没碰这段，不是回归，而且丢的句子已经从推断的 2 句减少到 1 句。根治办法是 v2 复核可选项 1 的方案 (c)：后端票据 TTL 放宽到约 150 秒。也可以在 resumeBlockedTts 里重换票，但要解决离开手势上下文的问题，需要单独设计。
2. **45 秒阈值的注释说得偏满。** 250 字一段约 39.1s，再加换票和首包延迟，余量只有约 4–5s。normalizeForTTS 在切句之后才执行，会让一段略超 250 字；「帮我读」截到 300 字约 46.9s。越界时只会多换一张票、多一个小空档（R10 里 WebKit 0.33s，Chromium 0.83s），不会丢句。注释可以改成「一般不会触发；越界时只多换一张票，不会丢句」。
3. **harness 的 S10 指标 all_ok_ended 在修复后按设计会是 false，容易被误读成失败。** 建议 S10 改看三点：5 句按序出声、errors 为空、「屋檐下」恰好换票 2 次；或者统计时排除「放弃后从未请求过 /tts/stream」的票。
4. **下限 1 的用例太弱。** `math.ceil(x) or 1` 和取 abs 两个变异体都能存活（19 passed）。可以追加 `((-10.0, -2.5), 1)`。
5. **拒绝日志取第一个不通过项这一点没有测试。** 把 `failed[0][1]` 改成 `failed[-1][1]` 仍然 19 passed。这个要求 v3 规格没有收进来。以后可以在 F2b 里传入 on_reject，并断言参数是 `checks[0][1]`。
6. **F2b 直接在 limiter.limiter 实例上 monkeypatch，恢复后实例上会留下 3 个绑定方法。** 功能上等价，现在的测试全绿。但如果以后有测试在 FixedWindowRateLimiter 类上打补丁，这些残留会把补丁挡掉。可以改为替换 `limiter._limiter`，或者对 `type(limiter.limiter)` 打补丁。
7. **F3 勘误没提 WebKit 预热那一次合成**（它不计入使用次数，所以单票最坏是 5 次合成）。勘误原文没给具体数字，不算错，比例结论也不受影响。可以补半句「WebKit 预热另算一次合成」。
8. **03-verification.md 和截图在工作区里相对暂存区有改动。** 它们不是实施方改的，暂存或提交前由主会话确认这些改动是有意的即可。

## 给实现方的修改指令

1. 在 `backend/tests/test_tts_ticket_rate_limit.py` 的 F2b 参数表（期望 id 为 latest-failed-reset 那组所在的 parametrize）里**追加一行** `((9.0, 2.0), 9)`，让较大的 reset 落在第一个不通过项上，并给它一个 id（例如 `larger-reset-first`）。
   - 已有的三行数据和所有断言一律不许改，只能追加。
   - 不要动 `backend/rate_limit.py`、`backend/routers/voice.py`、`frontend/` 及其他任何文件。实现本身是对的。
2. **自检：**
   - 按 19 + 1 推算，本文件应为 20 passed，后端全量应为 1530 passed。
   - 变异自检要证明新行真的起作用：把 `check_and_hit` 临时换成「取最后一个不通过项」的写法，新增这一行必须失败（`assert 2 == 9`），并且只有它失败。自检完必须还原，还原后 `git diff -- backend/rate_limit.py` 应为空。
3. 在 `docs/tasks/2026-09-29-tts-ticket-ratelimit/03-report.md` 末尾追加本次返修记录，写明新增的那一行、测试数量和变异自检结果。只追加，不改已有内容。
4. 其余可优化项本轮不做。