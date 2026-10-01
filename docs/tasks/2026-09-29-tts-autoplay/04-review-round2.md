# 朗读自动播放修复 · 第 2 次独立复核汇总

汇总复核员（全新上下文）合并 3 份核验结果和 2 份反驳结果，对第 1 次复核（`04-review.md`）列出的 M1、M2、O1、O2、O3 逐条给出最终判定。

## 0. 复核前提

- 被审对象：HEAD `49b2f5a`，`frontend/app/page.tsx` sha1 `389ab742b654c5e570215fdff1ab31f6d1e5ebd4`。开工前本汇总用 shasum 核对一致；3 位核验员和 2 位反驳员开工前、收尾时也都核对过，结果一致。
- 提交链：`61fc01f` 是第 0 轮和第 1 轮返修合并后的提交，之后依次是 `19e5804`（换票限流、429 退避）、`063a999`（票据 TTL 150 秒，「点此播放」按剩余有效期重换票）、`49b2f5a`（依赖升级）。
  - `git diff 61fc01f HEAD -- frontend/app/page.tsx` 共 74 增 11 删。涉及 `clearTtsQueue/stopTtsByUser/ttsStoppedSessionRef/primeAttempt/handsFreeRef/streamDoneRef` 的 +/- 行只有 1 行，是 19e5804 新增的限速提示按钮 `onClick={stopTtsByUser}`（`:2061`）。
- 构建不陈旧：反驳员 2 核对过 3021 端口进程 cwd 下的 page.tsx sha1，也是 389ab742。BUILD_ID 早于进程启动。打包产物里 `primeAttempt=null` 在 HEAD 只出现 1 次，第 0 轮产物（3023）出现 2 次。
- 本汇总自己做的核对：逐行读了 page.tsx 的 719–791、806–855、955–985、1031–1110、1249–1260、1363–1384、1640–1703、1990–2014、2046–2063 行；读了后端 `chat_service.py:940–1009, 1190–1220` 和 `routers/chat.py:76–94`；打开 `rev2-m1/*.json` 抽查了数值，与核验员的陈述一致。
- 硬规则遵守：除本文件外没有修改仓库任何文件，没有写 git 状态，没有读 `.env*`，没有使用浏览器面板工具。本汇总没有启动任何浏览器。

## 1. 结论

**通过。** M1、M2 都已修复，O1、O2、O3 都已按指令完成。没有发现由这些修改引入的、用户在现实中能感知到的「听不到 / 卡住 / 串句 / 双声 / 双路录音」回归。

有一处分歧需要说明。核验员 1 把「服务端已发 done、连接还没到 EOF 的窗口内点关朗读或不听了，会开出第二路录音」列为 must_fix。反驳员 1 用独立实测复现了同一现象，但判为 optional。本汇总裁定为 **可优化项 R2-O1（建议优先处理）**，理由有四条：

1. **根因在基线就有。** 同一窗口里，最后一句自然读完也会开两路录音，基线和 HEAD 都一样：
   - `DRAINNAT-base.json` 的 `gum_calls=[129,5977,8290]`，maxConcurrent=2；
   - 反驳员 1 的 `DNAT_BASE` 同样是 2 路。

   M1 返修只是多了一个「用户点击」的触发方式。这个触发方式来自第 1 次复核 5.1 指定的判据 `streamDoneRef.current`，实现方是逐字照抄的。
2. **现实中的窗口是毫秒级。** 窗口只等于服务端发出 done 之后的收尾时间：
   - `chat_service.py:986` 发 done，988–1009 行做 `token_budget.add`，每 5 条消息还有一次 `get_messages` 读库；抽取任务是后台任务，不等待；
   - `run_chat` 的 finally（`:1194–1220`）里有 `log_event` 写库；
   - `routers/chat.py:85–94` 关闭生成器。

   这些都没有模型调用。本机实测 done 到 EOF 只有 0.1–0.4ms（`measure-head2.json`、反驳员 1 的 MEASURE）。两位复核员都是把伪造流的 done→EOF 间隔人为拉长到 2–4 秒才复现的。
3. **即使撞上，用户也基本听不出来。** 两路录音会各自去请求 ASR。但 `handleSend` 在 `:1365` 检查 `chatAbortRef.current`，并在 `:1382` 同步赋值，两处之间没有 await，所以后到的那次发送会被丢掉，不会重复发消息。可感知的后果只有多一次 ASR 请求。
4. **复核规则。** 本轮规则只把「可感知回归」升级为 must_fix，其余新发现一律列为可优化。

因此本轮不需要给 Codex 返修。若用户决定把 R2-O1 升级为必须修复，可以直接用第 6 节的指令草案。

## 2. 逐条最终判定

| 编号 | 判定 | 关键证据（HEAD 行号） |
|---|---|---|
| M1 | **已修复** | 见 2.1 |
| M2 | **已修复** | 见 2.2 |
| O1 | **已修复** | 见 2.3 |
| O2 | **已修复** | 见 2.4 |
| O3 | **已修复** | 见 2.5 |

### 2.1 M1：「用户停止」标记从通用 `clearTtsQueue` 中移出

**代码核对**：第 1 次复核 5.1 的 6 点全部落实。

| 5.1 要点 | HEAD 现状 |
|---|---|
| 1. `clearTtsQueue` 不写会话标记 | `:1045–1064` 全函数不读、不写 `ttsStoppedSessionRef` |
| 2. 新增 `stopTtsByUser` | `:1068–1073`，与 5.1 给出的代码逐字一致。先取 `wasPlaying`，再打标记，再调 `clearTtsQueue()`，最后在 `wasPlaying && streamDoneRef && handsFreeRef` 时开麦。位置在 `clearTtsQueue` 之后、`resumeBlockedTts`（`:1075`）之前 |
| 3. 只有用户显式停止的入口用它 | 共 3 个入口：`:1994` 关朗读、`:2054` 被拒提示里的「不听了」、`:2061` 限速提示里的「不听了」。`:2061` 由 19e5804 新增，是该任务规格 v2.2-6 明文要求的。该提示只在 `ttsCurrentRef===prepared` 时渲染（`:873–876`、`:978–979`），所以点击时 `wasPlaying` 恒为 true，行为与 `:2054` 一致 |
| 3. 通用路径仍调 `clearTtsQueue` | `:1154` 账号切换、`:1279` 会话重置、`:1416` handleSend、`:1646` 卡片、`:1673` catch，都不打标记 |
| 4. 免提门槛恢复基线 | `:966` 为 `if (streamDoneRef.current && handsFreeRef.current) {`，与基线 `8c7f0cf:779` 逐字相同 |
| 5、6. 守卫和声明保留 | `ttsStoppedSessionRef` 全文恰好 4 处：`:428` 声明、`:1034` 守卫、`:1070` 写、`:1997` 置 null（O1） |

**第 1 次复核的 A–E 五个触发序列全部消除**。每一项都有第 0 轮版本的正向对照，主会话和两位复核员独立复测的结果一致：

| 序列 | HEAD | 第 0 轮（3023） | 基线（3022） |
|---|---|---|---|
| A 旅行规划口播（V1） | 换 1 张票、ended 1。反驳员 1 复测 Chromium 和 WebKit 都读完 | 0 张票，一声不出 | 1/1 |
| B 免提 + 卡片（V2） | `gum_after_mark=[5299]`，录音机 1 个；反驳员 1 复测为 `[151,5210]`，1 个 | 0 个 | 1 个 |
| C 免提 + 错误（V5） | 录音机 1 个（反驳员 1：`[156,5096]`） | 0 个 | 1 个 |
| D 免提 + 关朗读（V3） | `gum_after_mark=[12106]`，maxConcurrent=1 | 不开麦 | 开麦 |
| E 免提 + 不听了（V4） | `gum_after_mark=[9115]`，maxConcurrent=1 | 不开麦 | 无此按钮 |

**补充覆盖**（核验员 1、反驳员 1 补测）：

- **`stopTtsByUser` 补开麦分支**：流已结束、正在朗读时点关朗读，`nodrain-head.json` 的 `gum=[129,5779]`，maxConcurrent=1。主会话的 V3 是在流还在送句时点击的，走的是 finally 的门槛，没有覆盖这个分支。
- **免提麦正在录音时点关朗读**：HFRECOFF / RECOFF 都没有产生新的 getUserMedia，maxConcurrent=1。`wasPlaying` 前置条件有效。
- **流还在送句时点「不听了」**：
  - 免提版：HFMIDSTOP-head2 用页面内捕获阶段记录点击时刻，点击后 0 张票、0 次 playing，EOF 后恰好开麦 1 次；
  - 非免提版：STOPMID 在 Chromium 和 WebKit 上点击后都是 0 张票，下一条消息 5/5 读完。

**V4 判据的边界**：「同时录音的 MediaRecorder ≤1」在 V4 指定的场景里成立。但在 done→EOF 窗口内点击会开出 2 路（`drainstop-head.json` 的 `gum=[132,5297,8784]`，maxConcurrent=2）。本汇总把它裁定为可优化项，理由见第 1 节，详情见 R2-O1。

### 2.2 M2：`clearTtsQueue` 不再作废进行中的解锁尝试

**代码核对**：

- `:1056–1063` 收尾循环只保留 `if (slot.owner || !slot.primeAttempt) continue; pause(); removeAttribute("src"); load();`，注释已按 5.2 改写。
- 全文对 `primeAttempt` 的写入只剩两处：`:812`（赋值）和 `:819`（finish 内置 null）。`finish()`（`:814–825`）没有改动，规格本来就要求它不能改。
- `mkTtsAudio` 接手元素（`:852–854`）同样不置空 `primeAttempt`，两条路径现在一致。
- 推演：`clearTtsQueue` 打断解锁尝试后，`play()` 以 AbortError 拒绝 → 通过 `:815` 身份校验 → `:817` 写 `unlocked=true` → `:819` 置 null → 此时 src 已被移除，`:820` 条件为假，不会再碰元素。如果是 NotAllowedError，它在 `play()` 同步阶段就已拒绝，之后的 pause 改写不了结果，所以不会误判为已解锁。

**实测**：

- **V7**（`runs/head/results.jsonl`）：WebKit B 场景 1280 宽跑 2 次、390 宽跑 3 次，每次都是 5 张票，`prime_plays` 恰好是 `['rej:AbortError','rej:AbortError']`。
- **反驳员 2 的 14 次无头实测**（`scratchpad/m2rev/`），覆盖第 1 次复核 4.1 列出的三种触发方式（Enter 发送、点击发送按钮、关朗读那一下点击），每一项都在第 0 轮版本上做了正向对照：

| 场景 | HEAD | 第 0 轮 |
|---|---|---|
| BBUTTONF（WebKit 1280/390、Chromium） | 5 张票，prime 2 次，无重复文本 | 6 张票，prime 3 次，「屋檐下挂着细」重换了一次票 |
| BTOGGLEF（快速开→关→开 + Enter） | prime 2 次，第二次「开」没有再放静音 | prime 5 次，第二次「开」又放了 2 段静音 |
| TOGGLE3（读完后点击 5 次、按键 10 次，再关再开） | 全程只有最初的 2 次 prime | prime 4 次，有真实的静音 playing 事件 |

  BTOGGLEF 和 TOGGLE3 直接证明，第 1 次复核所说的后果 (a)「已解锁的元素在之后每次手势上仍被放静音」已经消失。
- 主会话证据表里 V7「第 0 轮」一列引用的是 09-29 的旧数据。反驳员 2 在 10-01 对 3023 重跑了（`B1280-r0.json`、`BBUTTONF-r0-*.json`），结果仍是 6 张票，这个缺口已经补上。
- 所有 HEAD 运行都是：元素 2 个，同时出声最多 1 个，读完后提示消失。没有发现由 M2 修改引入的回归。

**与 063a999 的衔接**：`resumeBlockedTts` 在 `:1079` 依赖 `unlocked` 标记，M2 修好后不再无谓放弃预取句。

063a999 的「票不够用」重换票路径（`:1084–1098`）在自己的复核里只用模拟拒绝验证过。核验员 3 用真实被拦的元素做了探针（`scratchpad/rev2_stale/out_stale2.json`，无头 WebKit 26.6）：

- 按这条路径的顺序处理后，8 秒和 20 秒后在手势外播放都是 ok；
- 正控 D（点击里没碰过）是 NotAllowedError，说明探针能抓到拦截。

iOS 真机没有验证。

### 2.3 O1：开朗读时把停止标记置 null

- **代码**：`:1997` 的 `ttsStoppedSessionRef.current = null;` 写在 `:1998 primeTtsAudio()`、`:1999 setVoiceOn(true)` 之前，与 5.3 一致。后续提交没有改动这几行。
- **V8**（`batch.jsonl` 第 15 行，HEAD）：
  - 再开后换了 2 张票（早点铺 9499、阳光 11285），依次读完，`max_sounding=1`，关闭期间 0 次开播；
  - 第 0 轮（第 13 行）再开后 0 张票。
- **对「比基线少读 1 句」的复核**：结论成立，但证据文件写的机制不对。
  - 从 SSE 事件节奏推算，「街上」约在 8160ms 到达，早于记录的 t_on=8398。t_on 在 Playwright click() 之前取，真实点击还要更晚。所以这句确实是在关闭期间到达的。
  - 丢掉它的不是 `:1032` 的「朗读关着不入队」守卫。原因是 `handleSend` 是普通函数，进行中的流在 `:1454` 调用的是发送那一刻闭包里的 `enqueueSpeech`，其中 `voiceOn` 固定为 true。真正拦下这句的是 `:1034` 的停止会话守卫。
  - 核验员 3 的 O1 条目沿用了证据文件的错误说法，这里一并更正。
  - 这条更正有实际意义：`:1034` 不能被当成「冗余守卫」删掉，否则关朗读后同一条流的后续句子会照常读出来，违反规格 3.3「立刻停止」。证据文字的更正见 R2-O5。

### 2.4 O2：`new AudioContext()` 改回基线写法

- `:732` 已改回 `const audioCtx = new AudioContext();`，与基线 `8c7f0cf:669` 一致。`git diff 8c7f0cf HEAD` 中 AudioContext 没有任何 +/- 改动。
- `grep -nE 'new Audio\s*\('` 无命中，退出码 1。
- `03-report.md`「第 1 轮返修」5.1 如实贴出了旧的宽泛 grep 命中 1 行，说明那一行是 Web Audio 上下文、不是媒体元素，并建议规格作者改用新模式。满足 5.3 的报告要求。

### 2.5 O3：live region 常驻

- `:2048` 的 `<div role="status" aria-live="polite">` 常驻、不带 class，被拒提示在 `:2049–2055` 条件渲染。
- 19e5804 新增的限速提示（`:2056–2062`）放在同一个 region 里：
  - 倒计时用 `aria-hidden`，读屏只读不变的 sr-only 文本，不会每秒重读；
  - 没有嵌套 live region；
  - 两个提示不会同时出现：等待状态在拿到票之前，被拒状态在拿到票之后。
- 父容器 `data-chat-composer`（`:2047`）不是 flex 或 grid，也没有 CSS 选中它，所以空 div 高 0。
- **V9**：核验员 2 独立核对了 sha1，4 张 `shots-head/head-*-footer.png` 与 `shots/base-*-footer.png` 逐一相同。`webkit-B-390-prompt.png` 中提示单行显示、两个按钮完整，sha1 与第 0 轮相同。

## 3. 第 1 次复核 5.5 验证判据汇总（HEAD）

| 编号 | 判定 | 说明 |
|---|---|---|
| V1 travel_plan | 通过 | 主会话 1/1；反驳员 1 在 Chromium 和 WebKit 上复测都通过 |
| V2 免提 + 卡片 | 通过 | 录音机 1 个 |
| V3 免提 + 关朗读 | 通过 | 主会话测的是流还在送句时点击；流已结束时点击由 `nodrain-head.json` 补测，maxConcurrent=1 |
| V4 免提 + 不听了 | 通过（附注） | 指定场景下 maxConcurrent=1；在 done→EOF 窗口内点击为 2 路，见 R2-O1 |
| V5 免提 + 错误 | 通过 | 录音机 1 个 |
| V6 不听了后不再入队 | 通过 | 点击后 0 张票、0 次 playing，下一条消息 5/5 |
| V7 M2 票据数 | 通过 | 5 次运行都是 5 张票；10-01 第 0 轮复跑仍是 6 张 |
| V8 O1 | 通过 | 再开后 2 句入队并读完；机制说明需更正（R2-O5） |
| V9 O3 | 通过 | 4 张截图逐字节与基线相同 |
| V10 F 复测 | 通过 | 换成页面内捕获阶段记录点击时刻后，Chromium 85ms、WebKit 2ms |
| V11 B390 隔离复跑 | 通过 | 3/3 次出现提示，5/5 读完 |

5.2 A–H 回归：主会话 HEAD 全部通过（见 `evidence-round1.md`）。

## 4. 可优化项（本轮新发现，全部留给用户裁决）

| 编号 | 标题 | 来源提交 | 位置 | 证据 | 建议 |
|---|---|---|---|---|---|
| **R2-O1（建议优先）** | 免提下，在服务端已发 done、连接还没到 EOF 的窗口内点「关朗读」或「不听了」，会开出第二路 MediaRecorder | `61fc01f`（M1 返修按 5.1 指定判据实现）；根因在基线 `8c7f0cf` 就已存在 | `:1072` 用 `streamDoneRef` 判断流已结束；`:1659` 收到 done 即置 true，之后 `:1662–1663` 继续读到 EOF；`:1692–1696` 的 finally 在 EOF 后调用 `playNextInQueue`，进而 `:966–967` 再开一次麦 | 2 路的情况：DRAINOFF（`gum=[132,5321,8713]`）、DRAINSTOP、DOFF2（录音机在 5967、6934 先后启动）。1 路的情况：基线做同样操作（`drainoff-base` `[134,10684]`）、在 EOF 之后点击（NODRAIN）。基线自然读完也是 2 路（DRAINNAT-base、DNAT_BASE）。现实窗口为毫秒级（理由见第 1 节） | **最小改法**：`:1072` 的 `streamDoneRef.current` 改为 `!chatAbortRef.current`，即只有 finally 已执行（`:1701` 已置 null）时才在这里补开麦；请求还在途时交给 finally。这样也顺带消掉了反驳员 1 指出的变体：流式中点旧卡片「帮我读」时，`:1253` 会把 `streamDoneRef` 置 true。**稳妥改法**：给 `startHandsFreeRecording` 加幂等 ref，正在申请或录音时直接 return，在 onstop、catch 和各个早退分支复位。这样连基线就有的 DRAINNAT 和 R2-O2 一起修掉。复测场景：DRAINOFF、DRAINSTOP、NODRAIN、DNAT，以及 batch.jsonl 的 HFSTOP、HFOFF，要求 maxConcurrent ≤1、每个场景各开麦 1 次 |
| R2-O2 | 免提麦正在录音时点旧卡片的「帮我读」，读完或关朗读后会开出第二路录音，而且第 1 路会录进朗读声 | 基线 `8c7f0cf`，不是本次回归 | `:719–791` 不幂等，`:1249–1260` | CONFIRMNAT、CONFIRMHF 在基线和 HEAD 上都是 maxConcurrent=2 | 与 R2-O1 的稳妥改法一起做；或者让 `handleConfirmTts` 在免提录音时先停掉录音。另开任务 |
| R2-O3 | 「免提」按钮打开朗读时没有清除停止标记，与「朗读」按钮（O1）不一致 | `61fc01f` | `:2006–2014`，对照 `:1996–1999` | 只做了代码推演：先关朗读打上标记，同一条回复还在流式输出时点开免提，朗读芯片亮了，但剩余分句被 `:1034` 丢弃 | 用户确认「开免提」是否等于「重新开朗读」。如果是，在 `:2010–2013` 加 `ttsStoppedSessionRef.current = null` |
| R2-O4 | 关朗读后再开，只会读「再开之后才到达」的句子；如果流已经结束，同一条回复剩下的部分再也不读 | `61fc01f`（规格 3.3「立刻停止」的直接结果） | `:1047–1055`、`:1996–1999` | TOGGLE HEAD：关闭时预取好的「屋檐」被释放，再开后没有补读。基线关朗读不停止，会读完 | 产品决定：维持现状（关闭等于放弃这条回复已到达的部分），还是暂存后接着读。后者触及规格 3.3 的边界，需要另开任务 |
| R2-O5 | `evidence-round1.md` 的 V3、V8 表述与代码路径不符 | 证据文件（不是代码） | V3、V8 两行 | V8 把丢句归因于 `:1032`，实际是 `:1034`。V3 HFOFF 没有覆盖 `:1072` 补开麦分支 | 更正文字。TOGGLE 改用页面内捕获阶段记录点击时刻；把 NODRAIN、DRAINOFF、DRAINSTOP 并入回归脚本 |
| R2-O6 | 限速提示里的「不听了」加免提的组合只做了代码推演，没有实测 | `19e5804` | `:2061` | 代码上 `wasPlaying` 恒为 true，不会双开（R2-O1 的窗口除外） | 下次跑 harness 时补一个 429 退避期间、免提开着点「不听了」的场景 |
| R2-O7 | 063a999「票不够用」重换票路径只在无头 WebKit 上用真实被拦元素验证过 | `063a999` | `:1084–1098` | `rev2_stale/out_stale2.json`：8 秒和 20 秒后在手势外播放都是 ok；正控是 NotAllowedError | 不改代码。以后在 iOS 真机验证 O8 时，顺带跑一次「被拦后等 140 秒以上再点『点此播放』」 |

## 5. 待用户拍板

| # | 问题 | 现状 | 选项 |
|---|---|---|---|
| 1 | 第 1 次复核附录 B 第 1 条：免提下「不听了 / 关朗读」后是否重新开麦 | 按第 1 次复核的默认实现：只在确实打断了正在进行的朗读、流已结束、免提开着时补开一次麦。现在覆盖 3 个入口（`:1994`、`:2054`，以及 19e5804 新增的 `:2061`），改 `stopTtsByUser` 一处会三处同时生效 | 维持；或者改成「不听了 = 退出免提」：在 `stopTtsByUser` 里 `setHandsFree(false)`，不再开麦 |
| 2 | 附录 B 第 2 条 / O4：被拒提示显示期间点「帮我读」 | 会话号推进但不清队列，提示不消失，被拒那句丢失 | 在 `handleConfirmTts` 的 `primeTtsAudio()` 之前加 `if (ttsPlaybackBlocked) clearTtsQueue();`（触及规格 3.4「不变」条款）；或者维持 |
| 3 | 附录 B 第 3 条 / O5：正在播放时点「帮我读」，已预取就绪的下一句是照播（基线）还是跳过（当前） | 当前按规格 3.1 在 play 前核对会话号，所以会跳过 | 规格 3.1 与 3.4 冲突，需要规格作者定 |
| 4 | 附录 B 第 5 条 / O8：静音解锁是否改为 `muted=true`，减少 iOS 打断背景音乐 | M2 修好后 prime 只在开朗读那一下发生，次数已大幅减少 | 需要 iOS 真机验证后再定 |
| 5 | 本轮新增：R2-O1 是否在本任务内修 | 已裁定为可优化项（建议优先） | 现在按第 6 节派单；或者与 R2-O2 合并另开「免提录音幂等」任务 |
| 6 | 本轮新增：R2-O3、R2-O4 的产品语义 | 见第 4 节 | —— |

**附录 B 第 4 条 O7 已由 `063a999` 处理**：票据 TTL 放宽到 150 秒，「点此播放」按剩余有效期决定是否重换票。该提交已经过独立复核；本轮核验员 3 又用真实被拦元素在无头 WebKit 上补测通过（R2-O7）。

## 6. 返修指令草案（仅在用户把 R2-O1 升级为必须修复时使用）

**硬规则与白名单**（重申规格第 0 节，违反任一条即返工）：

- 不得修改任何已有测试的输入或断言。
- 不引入依赖，不改 `package.json` 和 lockfile。
- 不做真实网络调用，不下载任何东西。
- 不运行 `next dev`。
- 不写 git 状态（不 commit、不 stash、不 checkout、不 reset）。
- 不读 `.env*`。
- 不启动浏览器。
- 同一个文件不要让多个 subagent 并行改。
- 只有影响「实现什么」的事才停下来写进「未决问题」。任何情况下不回滚已完成的工作。
- **白名单**：`frontend/app/page.tsx`，以及本目录新建的报告文件。后端一行不改。

**改动**（二选一，由用户指定）：

- **最小改法**：`:1072` 改为 `if (wasPlaying && !chatAbortRef.current && handsFreeRef.current) startHandsFreeRecording();`，其余不动。
- **稳妥改法**：
  1. 新增 `handsFreeRecordingRef`。
  2. `startHandsFreeRecording` 在入口检查：已为 true 就 return，否则置 true 再 `await getUserMedia`。
  3. 在以下位置复位为 false：`getUserMedia` 之后的早退分支（`:724–727`）、`mr.onstop` 首行、`catch`。
  4. `:1072` 保持不变。

**验证**（Claude 主会话实测）：

- 用 `rev2-m1/m1_race.py` 和 `rev2-m1-c/m1c.py` 复跑 DRAINOFF、DRAINSTOP、DOFF2、NODRAIN、DNAT，再加 `tts_v.py` 的 HFSTOP、HFOFF、HFCARD、HFERR。
- 要求每个场景录音机 maxConcurrent ≤1，且流结束后恰好开麦 1 次。
- 选稳妥改法时，还要加 CONFIRMNAT、CONFIRMHF。

## 附录 A. 证据索引

- 规格、第 1 次复核、实现报告：本目录 `02-spec.md`、`04-review.md`、`03-report.md`（「第 1 轮返修」一节）。
- 主会话证据：`~/.claude/projects/-Users-yangjing-Desktop-ai-workspace/baselines/2026-09-29-tts-autoplay/` 下的：
  - `evidence-round1.md`、`round1-vs-round0.diff`、`head-vs-base.diff`
  - `harness/runs/v/batch.jsonl`、`harness/runs/head/results.jsonl`、`harness/shots-head/`
- 复核员 scratchpad：`/private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/` 下的：
  - `rev2-m1/`：核验员 1。`m1_race.py`；DRAIN*、NODRAIN、HFMIDSTOP*、HFRECOFF*、CONFIRM*、measure-head2 的 JSON
  - `rev2-m1-c/`：反驳员 1。`m1c.py`；DOFF*、DSTOP*、DNAT*、MEASURE、RECOFF、MIDSTOP、V-* 的 JSON
  - `m2rev/`：反驳员 2。`m2probe.py`；B*、BBUTTONF*、BTOGGLEF*、TOGGLE3*、BSTORM、BLATE 的 JSON
  - `rev2_stale/`：核验员 3。`probe_stale2.py`、`out_stale2.json`
- 后端窗口依据：`backend/services/chat_service.py:986–1009, 1194–1220`；`backend/routers/chat.py:85–94, 178–186`。
