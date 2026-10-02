# 第 5 次复核：第 4 轮（收尾）返修（F4–F7）

- 复核日期：2026-10-02
- 复核方式：全新上下文，与实现方 Codex、返修单作者、前几次复核员都无关。
  - 2 个核验代理：一个看 F4/F5/F6 的逻辑和证据，一个看 F7（含 O6）。另有无头 Chromium/WebKit 补测：`scratchpad/rv5/mrstate.py`。
  - 1 个反驳代理做对抗实测：`scratchpad/rv6/r4x.py`、`../r4rev/r4.py`。它用 `fe-r3`（88de85ce，即 `b38beca`）在 3043 临时起了基线做正控，测完已停。
  - 最后由本汇总复核员亲自核对哈希、读代码、抽查原始结果、独立跑 lint，再做裁决。
- 被审对象：工作区里未提交的 `frontend/app/page.tsx`，sha1 `4c490b9677f1c73f75d470dc393a4d963d6565ef`。开工、两个核验代理和反驳代理各自核对，结果一致。
  - HEAD 为 `b38beca`；HEAD 版 page.tsx 的 sha1 前缀是 `88de85ce`，与返修单基线一致。
  - `git diff HEAD -- frontend/app/page.tsx` 与 `baselines/.../round4.diff` 逐字节相同（`cmp` 无输出）。
- 判定口径：
  - must_fix：偏离返修单；或引入「听不到 / 卡住 / 双路录音 / 用户说的话被丢掉 / 录进朗读声 / 麦克风灯常亮 / 提示错误或不消失」这类现实中会遇到的可感知回归。
  - 其余一律记为可优化项。
  - 已知原有问题（04-review-round3 的 O5、O7、O8，以及 04-review-round4 的 N2–N5）不重复列。O6 属于本轮 F7 的范围，单独判定。
- 下文行号都指当前工作区文件（4c490b96）。

## 结论：通过（无 must_fix）

- F4、F5、F6、F7（含 O6）都按返修单原文落地。
- 每一项都有「修改前失败、修改后通过」的实测对照。两个核验代理和反驳代理都没有测出现实中会遇到的可感知回归。反驳代理的结论是 `still_broken=false`。
- 有 1 条新发现由 F7 引入：在注入故障的条件下，能 3/3 复现「用户说的话被丢掉，提示还说麦克风用不了」，见 3 节 R5-1。
  - 它要求四件事同时成立：
    1. 第一次申请麦克风很慢；
    2. 慢的这次以暂时性的非权限错误失败；
    3. 用户恰好在这段等待里点了「帮我读」，而且卡片很快就读完或换票失败；
    4. 第二次申请成功。
  - 现实中最常见的慢申请是权限弹窗。弹窗期间两次申请共用同一个决定，结果必然一致，触发不了这个问题。
  - 因此本复核员判它为**可优化项**，与反驳代理的判断一致。修法只有一行，**建议列为下一单第一项**，是否随本单一起改由用户决定。裁决理由见 4 节。

## 1. 逐条核验

### F4：丢弃正在录的免提收音时，立即释放占用标记

| 要求 | 判定 | 依据 |
|---|---|---|
| 在录音分支里，`stop()` 之后，如果 `discard` 为 true，就按身份复位 | 符合 | 833–836：`if (rec.recorder.state === 'recording') { rec.recorder.stop(); if (discard && handsFreeRecRef.current === rec) handsFreeRecRef.current = null; }`，与返修单原文逐字一致。<br>只有两个调用方，都传 `discard: true`：1296 是「帮我读」，1467 是 `handleSend`。 |
| `onstop` 第一行的身份比较复位保留不动 | 符合 | 785 未改。旧录音的 `onstop` 晚到时，ref 已经是新开的 R2，身份比较为假，不会误清 R2。<br>`rv5/mrstate.py` 在 Chromium 和 WebKit 实测：R1 的 `onstop` 分别晚 3ms 和 9ms 到，这时 ref 已是 R2；之后 ref 仍是 R2。这个结果同时是正控：它证明了「旧 onstop 晚于新开的那次」这个时序确实会发生。 |
| 被丢弃的录音仍然不送 ASR | 符合 | 788：`rec.discard` 为 true 时直接 `return`。<br>786–787 只释放 R1 自己闭包里的 stream 和 audioCtx。734–735 的 `let` 每次调用各有一份，不会碰到 R2 的资源。 |
| 处于 `recording` 状态的录音机最多一个 | 符合 | `stop()` 会同步把 R1 置为 inactive，实测 stop 后立即读到 `inactive`。R2 要等 `getUserMedia` 返回后才在 806 行 `start()`。<br>反驳代理在 F4X、F4C 中按 recording 状态计数，最大值是 1。 |
| 修改前失败、修改后通过 | 符合 | 修改前：`pre-FASTFAIL.txt` 中 `reopened=false`，`recStart` 只有 `[6244]`，免提停住。<br>修改后：`post-new.jsonl` 第 6–9 行，FASTFAIL-1/2/3 和真实后端 404 都是 `reopened=true`。<br>反驳代理：<br>• F4X×2（打字发送、`/chat` 立即返回 error）、F4C（点「帮我读」、卡片换票立即 500）：新一路在丢弃后 1–2ms 就开始录，录到的人声被识别并以 `/chat` 发出。<br>• WebKit FASTFAIL：sse 0ms×2、net 0ms、offline 0ms，共 4/4 重新开麦且收到人声。上次复核同类场景是 8/8 卡住。 |

判定：**已修复**。O1 和 N1 的主要触发路径都已关闭。录音刚因静音自动停止、`onstop` 还没到的那一小段窗口仍未覆盖，见 R5-2。

### F5：朗读已开时点「免提」，不清除「已停止」标记

| 要求 | 判定 | 依据 |
|---|---|---|
| 打开分支改为 `if (!voiceOn) ttsStoppedSessionRef.current = null;`，其余照旧 | 符合 | 2062–2067：`setMicNotice(null); if (!voiceOn) ttsStoppedSessionRef.current = null; primeTtsAudio(); setVoiceOn(true);`<br>口径与「帮我读」的 1299–1302 一致。`onClick` 每次渲染都会重建，读到的 `voiceOn` 不会过期。 |
| 朗读开着、点过「不听了」后再开免提：后面的句子不读；流结束后开麦 1 次 | 符合 | 修改前：`pre-STOPHF.txt` 中 `tickets_after_hf` 有 3 句，`playing_after_hf=3`。<br>修改后：`post-new.jsonl` 第 1 行，`tickets_after_hf=[]`，`playing_after_hf=0`，`gum_after_hf` 只有 1 次，`maxConcurrent=1`。<br>「开麦在 EOF 之后」靠代码证明：后续句子在 1079（`ttsStoppedSessionRef` 守卫）被拦下；done 事件（1711）只置标记，不开麦；唯一的开麦入口是 finally（1745–1748）里的 `playNextInQueue` → 门槛 1012 → `startHandsFreeRecording`。这次运行没有记录 `t_hf` 和 EOF，见 R5-6。 |
| 朗读关着时点「免提」，仍视为重新开朗读（D4） | 符合 | 主会话 HFON（`post-matrix.jsonl`）：后面 3 句都读了，朗读芯片最后是亮的。<br>反驳代理 D4：关朗读后再点免提，三月、四月、五月三句全部播完；读完开麦 1 次。 |

判定：**已修复**。

### F6：回复还在生成时点「帮我读」，不提前开麦

| 要求 | 判定 | 依据 |
|---|---|---|
| 1304 改为 `if (!chatAbortRef.current) streamDoneRef.current = true;` | 符合 | 与原文逐字一致。`chatAbortRef` 是 ref，依赖数组不用改。 |
| 不会出现中间态 | 符合 | `handleSend` 在同一个同步段里先置 `chatAbortRef`（1433），再置 `streamDoneRef=false`（1471），第一个 `await` 在其后。finally 也是先置 `streamDoneRef=true`（1745），再置 `chatAbortRef=null`（1753）。<br>所以「帮我读」的点击处理函数不会看到「有在途请求，但 streamDone 已是 true 且未经 done 事件」这种中间态。 |
| 开麦恰好 1 次，且不会永远不开麦 | 符合 | 卡片读完和 finally 是两个开麦入口：前者经 `finishCurrentTts` → `playNext`，后者在 `!ttsPlayingRef.current` 时调用 `playNextInQueue`。两者互斥，再加上 730 的入口守卫，只会开 1 次。<br>只要 `chatAbortRef` 不为空，就一定有一个持有该位置的请求，它的 finally 必定会把 `streamDone` 置 true。卸载或切换账号时，1193 会清空 `chatAbortRef`。<br>done 与 EOF 之间的窗口是已知的 O7，不属于本轮问题。 |
| 修改前失败、修改后通过 | 符合 | 修改前：`pre-CSTREAMHF.txt` 中卡片 9796 读完，9799 就开麦，EOF 在 18497；识别了人声（`asr=[12686]`），但 `chat_posts` 里没有用户的话，被丢掉了。<br>修改后：两次独立运行，第一次免提开麦分别在 18585 和 18577，都在 EOF 之后 2ms；用户的话以 `/chat` 发出，`maxConcurrent=1`。<br>反驳代理补测 4 种时序：<br>• F6X（流式中点「帮我读」→ 卡片被拒 →「不听了」）：基线 3043 在 8812 开麦，比 EOF 18604 早约 10 秒，用户的话没发出；修改后在 EOF 18338 开麦 1 次，用户的话发出。<br>• F6E（流以断开结束，没有 done）：出错的同一毫秒开麦 1 次。<br>• F6L2（流在卡片播放中结束）：卡片读完后 1ms 开麦 1 次。<br>• F6L（点「帮我读」时没有在途请求）：行为与原来相同。 |

判定：**已修复**。

### F7（含 O6）：麦克风用不了时给出提示；免提失败时自动关闭免提并释放麦克风

| 要求 | 判定 | 依据 |
|---|---|---|
| 免提 catch：释放 stream 和 AudioContext（O6） | 符合 | `stream` 和 `audioCtx` 提到 try 外声明（734–735）。catch 中 809 停所有轨道，810 `audioCtx?.close()`。<br>逐条失败路径：<br>• `getUserMedia` 被拒，或 `mediaDevices` 不存在：stream 为 null，没有要释放的。<br>• 744 行 MediaRecorder 构造抛错、749–753 抛错、806 `start()` 抛错：都会停轨，已创建的 context 会被关闭。<br>实测 RECTHROW：修改前 `live_tracks=1`（麦克风灯常亮），修改后为 0。 |
| 免提 catch：关闭免提，并按身份复位 ref | 符合 | 811 按身份复位，812 `setHandsFree(false)`。MICDENY-HF、MICNOTFOUND、RECTHROW 修改后 `hands_chip_on=false`，修改前都是 true。 |
| 提示文字分类 | 符合 | 免提 813–816、内联 720–723：`NotAllowedError` 或 `SecurityError` 提示「没有麦克风权限，请在浏览器里允许使用麦克风」，其他错误提示「麦克风用不了」；免提入口再加「，免提已关闭」。<br>`(e as {name?:string}\|null)?.name` 对 null 和 TypeError 都安全。<br>实测的 deny、generic、hf_off 三种组合都符合预期。<br>反驳代理 DENY2：第二次失败（NotFoundError）时提示正确替换成「麦克风用不了，免提已关闭」，DOM 里只有 1 行。 |
| 控制台 warn 与 error 分流 | 符合 | 817–821：`NotAllowedError`、`SecurityError`、`NotFoundError` 用 warn，其他用 error。<br>实测 MICDENY-HF 和 MICNOTFOUND 只出 warning；RECTHROW（NotSupportedError）仍是 error，符合「其他保留 console.error」。<br>内联入口原来是 `catch (_) {}`，没有日志，本轮也没加，没有可「保留」的输出，不算偏离。 |
| 内联：失败时停轨并给提示 | 符合 | `stream` 提到 try 外（686），catch 719 停轨，720–723 设置提示。<br>反驳代理 INLINE：被拒时提示里不带「免提已关闭」；改为允许后，`getUserMedia` 成功即清除提示，录音、识别、发送都正常。<br>INLINEHF：免提开着时内联失败，只提示「麦克风用不了」，免提保持开。 |
| `micNotice` 的设置点和清除点 | 符合 | `grep` 结果：设置点 2 个（721、814）；清除点 4 个（内联 `getUserMedia` 成功 689、免提 `getUserMedia` 成功 738、点「免提」打开 2063、「知道了」2119）。与返修单列出的清除点一一对应，没有多也没有少。<br>「，免提已关闭」不会与亮着的免提芯片同时出现：唯一能把免提置为 true 的是 2061，同一个处理函数在 2063 就清掉了提示。<br>反驳代理 REALLOW：先被拒，看到提示、芯片熄灭；改为允许后再点免提，提示立刻消失；下一轮正常录音并发出人声。 |
| 「按住说话」和页面加载时的预申请不改 | 符合 | diff 中没有涉及 `startNlsAsr`（609–659）和预申请（582–588）的改动。 |
| 提示的界面 | 符合 | 2117–2120 位于常驻的 `<div role="status" aria-live="polite">`（2102）内，排在两条朗读提示（2103、2110）之后。<br>外层、文字、按钮的类名与 2103–2108「浏览器拦下了自动朗读」逐字一致；没有新增颜色，没有抢焦点；`git status` 中 globals.css 没有改动。 |
| 提示不显示时像素不变；390 宽不溢出 | 符合 | 提示不显示时，`shots-r4/r4-{chromium,webkit}-{390,1280}-footer.png` 与基线截图 sha1 4/4 相同。<br>反驳代理 390 宽实测：带「，免提已关闭」的长提示换成两行，`scrollWidth=390/390`，提示行 366×36，没有横向溢出。 |
| 截图里麦克风按钮底色偏深（主会话请复核的疑点） | 不是问题 | 是悬停样式，不是录音状态卡住。<br>• 像素：底色 (27,34,45)，即暗色 `--secondary`；图标 ≈ `--foreground`。这正是 globals.css 中 `.btn-quiet:hover` 的效果。<br>• 按钮区域没有红色像素；如果 `inlineRecording` 为 true，会显示 `--rec` 红字和红底。<br>• 截图脚本点完按钮后鼠标停在按钮上。<br>• 代码上，`setInlineRecording(true)` 只在 717，位于 `start()` 之后；被拒时在 688 就抛错，执行不到 717。<br>• 反驳代理 INLINE 实测：失败后按钮 class 里没有录音态。 |

判定：**F7 已实现，O6 已修复**。另有一条由 F7 引入的窄窗口问题，见 R5-1。

## 2. 门禁与范围

- **lint**：本复核员用 `eslint -f json` 跑工作区的 `app/page.tsx`，退出码 0；0 个错误、24 个警告：
  - 22 条 `no-unused-vars`；
  - 1 条 `exhaustive-deps`；
  - 1 条 `no-img-element`。
  
  第 4 次复核时同一文件是 25 个警告。少的那条正是被删掉的 `catch (_) {}` 里的 `_`。主会话报告整个项目共 25 个警告，满足 `--max-warnings=26`。用 json 格式，是为了先证明 lint 确实产出了结果。
- **tsc 与 next build**：采用主会话证据中的结果（退出码 0），本轮没有独立重跑，因为它们可能写入仓库里的产物。
- **`git status --porcelain`**：
  - 代码只改了 `frontend/app/page.tsx`。
  - `03-report.md` 只在末尾追加（唯一的 hunk 是 `@@ -1150,3 +1150,630 @@`）。
  - `02-spec.md` 只在附录末尾加了 5 行「2026-10-02 收尾拍板」，与 `05-fix-round4.md` 同时（03:29）由主会话写入，不属于实现方改动。
  - 后端没有改动。
- **构建新鲜度**：3021 是 fe-r4，进程 03:39:00 启动；BUILD_ID 时间是 03:38:56，晚于源码；构建产物里能找到「免提已关闭」。修改后的所有结果都在 03:42 之后产生，测的不是陈旧构建。

## 3. 可优化项（本轮不要求改）

| # | 内容 | 来源 | 建议 |
|---|---|---|---|
| **R5-1** | **被丢弃的那次申请晚到失败时，会关掉免提，并停掉正在录的新一路。**<br>**触发序列**：<br>1. 免提读完后发起 R1 的 `getUserMedia`；<br>2. 申请还没返回时，用户点「帮我读」（1296）。R1 没有录音机，走 829–831：置 `discard`，并立即清空 ref；<br>3. 卡片很快读完，或换票失败；<br>4. R2 申请成功，开始录音；<br>5. R1 这时才以非权限错误失败（例如 NotReadableError）；<br>6. R1 的 catch（808–816）不检查 `rec.discard`，执行了 `setHandsFree(false)`，提示「麦克风用不了，免提已关闭」；<br>7. R2 的 tick（780）看到免提已关，`stop()`；`onstop`（788）因为免提已关直接返回。<br>**后果**：用户正在说的话被丢掉；提示说麦克风用不了，其实它能用。<br>**证据**：反驳代理 STALE（注入「第 1 次申请延迟 1500ms 后抛 NotReadableError，第 2 次成功并带人声」）：<br>• 修改后 3/3（`rv6/post2.jsonl` 306，`post3.jsonl` 318、320）：`asr=[]`，`chat_user_speech=false`，`hands_on=false`，出现上述提示；<br>• 基线 3043 为 0/1（`pre3.jsonl` 316）：R2 正常录完，`asr=[8229]`，「用户说的话」在 8281 发出。<br>核验代理 2 从代码层面也指出了同一缺陷（catch 没有 stale 判断），另外还有一种轻的情形：用户自己关了免提后，弹窗被拒，提示仍带「，免提已关闭」。 | **本轮 F7 引入** | **列为下一单第一项。** 在 catch 中释放资源、按身份复位之后加一段：<br>`if (rec.discard \|\| selectionVersion !== getSelectionVersion()) { console.warn('[handsfree] stale mic error', e); return; }`<br>被丢弃或已切换账号的那次申请，不关免提、不写提示。如果真是权限问题，下一次开麦也会失败，并自行提示。这一行同时解决 R5-3 的第 (3) 点。<br>不判为 must_fix 的理由见 4 节。 |
| R5-2 | **F4 的立即复位只覆盖 `state==='recording'`。** 录音刚因静音自动停止（778）、`onstop` 还没到（3–110ms）时，录音机已是 inactive。如果这时被丢弃，不进入 833 分支，ref 不会立即清空。如果之后的开麦请求也落在这段窗口里（卡片换票立即失败，或 `/chat` 立即失败），730 会拒绝它，免提停住。 | **原有**（O1 剩下的一小段窗口；同一窗口里「刚说的话被丢弃」已登记为 O2） | 把复位挪到 if 块外：`if (rec.recorder.state === 'recording') rec.recorder.stop(); if (discard && handsFreeRecRef.current === rec) handsFreeRecRef.current = null;`。两种情况下录音机都已是 inactive，仍然最多一路在录。建议与 O2 一起处理。 |
| R5-3 | **`micNotice` 不跟随账号或会话复位。**<br>(1) 切换账号时，1173–1189 的复位 effect 清了其他提示，没有清 `micNotice`；<br>(2) `resetConversationPresentation` 也不清；<br>(3) 申请还在进行时切换账号，旧申请随后被拒，会给新账号弹出「…，免提已关闭」。 | 本轮新增状态带来的，不是回归。提示的内容是浏览器级别的事实，可以用「知道了」关掉。 | (1)、(2)：在两个复位函数里各补一行 `setMicNotice(null)`。(3)：随 R5-1 一起解决。 |
| R5-4 | 「按住说话」录音成功时不清提示，可能出现「提示还在，但已经在录音」。 | 返修单明确规定「按住说话」不改，属于规格范围内 | 日后如果允许改 `startNlsAsr`，在它的 `getUserMedia` 成功后也清除提示。 |
| R5-5 | **判据口径**：F4 之后，新一路的 `getUserMedia` 可能比旧录音的 `onstop` 先返回。这时旧轨道还会多亮约 100ms，返修单明确允许这一点。<br>harness 的 `rec.maxConcurrent` 按 stop 事件计数，所以 F4X、F4C 读出来是 2；按 recording 状态计数是 1。 | 证据口径问题，不是代码问题 | 「并发 ≤1」改按 recording 状态计数。「新申请早于旧轨道停止」这个顺序在 iOS 上是否有影响，并入 O8，一起做真机确认。 |
| R5-6 | **证据记录有缺口**：<br>• `pre-FASTFAIL` 只跑了 1 次，返修单要求修改前 3/3；<br>• `pre*.txt` 没有记录被测页面的 sha1 或 BUILD_ID，与 N3 同类；<br>• STOPHF 没有记录 `t_hf` 和 EOF。 | 证据问题 | 本轮已经补足：04-review-round4 的 N1 在同一份 88de85ce 代码上做过 3/3 复现；反驳代理在 3043（fe-r3 = 88de85ce）独立做了正控（F6X、STALE）；STOPHF 的时序由代码证明。<br>以后：harness 输出被测页面的 sha1 或 BUILD_ID；STOPHF 断言第一次开麦不早于 EOF；修改前的场景跑满规定次数。 |
| R5-7 | 有两条失败路径没有浏览器实测，只靠读代码确认：<br>• 免提 AudioContext 已创建后抛错的路径（750–753、806 → 810 `close()`）；<br>• 内联入口 `getUserMedia` 成功后抛错的路径（694、716 → 719 停轨）。 | 测试覆盖 | 在 MIC 钩子里加一种模式，让 `createMediaStreamSource` 或 `MediaRecorder.prototype.start` 抛错，同时统计 `AudioContext.close` 的调用次数；再加一个内联 recthrow 场景。 |

**原有问题状态**：
- O1/N1：已由 F4 修复，剩下的小窗口见 R5-2。
- O3：已由 F5 修复。
- O4：已由 F6 修复。
- O6：已由 F7 修复。
- O2、O5、O7、O8、O9、O10，以及 N2–N5：不变。

## 4. R5-1 的裁决说明（为什么不是 must_fix）

- R5-1 的后果属于 must_fix 清单里的「用户说的话被丢掉」和「提示错误」，并且由本轮引入，所以单独说明。
- 必须同时满足四个条件，缺一不可：
  1. R1 的 `getUserMedia` 等待时间长到用户来得及点击。实测里注入了 1500ms。已授权时，`getUserMedia` 通常一两百毫秒就返回，人手来不及点。
  2. 等待这么久的 R1，最后以**非权限的暂时性错误**失败。
  3. R2 的申请紧接着就成功了。
  4. 卡片在 R1 失败之前就读完或失败了。卡片正常要读几秒钟，R1 失败时卡片还在读，这时免提被关掉，R2 根本不会开，也就没有话可丢。
- 现实中，「申请慢」几乎只出现在权限弹窗上。弹窗期间，Chrome 让同源的几次申请共用同一个决定：两次都被拒，就是正确地关免提并提示；两次都被允许，R1 就走 739–742 的早退，不会进 catch。两次结果不一致的情形，只有在蓝牙耳机切换这类偶发硬件故障，又恰好叠上人手点击和 TTS 失败时才可能出现。
- 这与前几轮的口径一致：O2、O7 这类「人手点击落进一两百毫秒窗口」的问题判为可选；N1/FASTFAIL 能被断网稳定触发，才判为必修。
- 如果主会话希望从严，这一行修复风险很低（只是在 catch 里早退），也可以由主会话直接并入本单再提交。复核员不反对，也不要求。

## 5. 核验范围与可信度

- 本复核员核对的内容：
  - page.tsx 的 sha1、HEAD、diff 是否与 `round4.diff` 逐字节相同；
  - F4–F7 每一处改动的行号；
  - `micNotice` 的设置和清除点（grep 全量）；
  - `chatAbortRef` 和 `streamDoneRef` 的全部赋值点；
  - 抽查原始结果：`pre-*.txt`、`post-new.jsonl` 第 1–11 行、`rv6/post2|post3|pre3.jsonl` 中的 STALE 行，数值与两个代理的引述一致；
  - 独立跑了 lint，见 2 节。
- 浏览器实测全部来自主会话 harness 和三个代理的无头 Playwright 脚本。本复核员没有启动浏览器，也没有使用浏览器面板工具。
- 本复核员只写了本文件；没有修改仓库其他文件，没有写 git 状态，没有读 `.env*`。lint 不带 `--cache`，跑完后 `git status --porcelain` 与开工时相同。
