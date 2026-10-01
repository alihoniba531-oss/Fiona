# 返修单 第 2 轮（依据用户 2026-10-01 拍板 + 第 2 次复核 04-review-round2.md）

- 基线：`main` HEAD `49b2f5a`，`frontend/app/page.tsx` 的 sha1 前缀为 `389ab742`。
- 第 1 轮返修已经提交为 `61fc01f`。之后的 `19e5804`（换票限流、429 退避）和 `063a999`（票据 TTL 150 秒、「点此播放」按剩余有效期决定是否重换票）也改过这个文件，**它们的行为全部保持不变**。
- 下文行号都指当前 HEAD。

## 0. 硬规则（沿用 02-spec.md 第 0 节，违反任一条即返工）

- **不得修改任何已有测试的输入或断言。**
- 不引入依赖，不改 `package.json` 和 lockfile。
- 不做真实网络调用，不下载。
- 不运行 `next dev`，不启动浏览器。
- 不写 git 状态，不读 `.env*`。
- 同一个文件不要让多个 subagent 并行改。
- 只有影响「实现什么」的事才停下来写进「未决问题」；只影响「怎么验证」的事自己定。不回滚已完成的工作。
- **白名单**：`frontend/app/page.tsx`；本目录 `03-report.md`（只在末尾追加）。其他文件一律不动，后端一行不改。

## 1. 用户拍板（2026-10-01）

| # | 问题 | 决定 |
|---|---|---|
| D1 | 免提下点「不听了」或「关朗读」后，是否重新开麦 | **维持现状**：重新开麦。`stopTtsByUser` 的补开麦逻辑不动 |
| D2 | 已经在朗读，或停在「浏览器拦下了自动朗读」提示时，点旧卡片的「帮我读」 | **先停掉旧的朗读，立刻读这张卡片**。这一条覆盖规格 3.4「`handleConfirmTts` 行为不变」，同时解决 04-review 的 O4 和 O5 |
| D3 | 免提偶发同时开出两路录音 | **现在修，用「已经在录音就不再开」的保护（稳妥改法）**。连同原本就有的问题一起修：免提录音中点「帮我读」，会多开一路，而且第一路会把朗读声录进去 |
| D4 | 点「免提」打开朗读，是否也算重新开朗读 | **是**，和「朗读」按钮一致 |
| —— | 静音解锁改成 `muted`（O8）、关朗读再开时补读同一条回复已到达的部分（R2-O4） | **本轮不做** |

## 2. 改动

### F1（D2）「帮我读」先打断旧朗读，再读卡片

`handleConfirmTts`（约 1249–1260 行）改为在点击处理函数的**同步部分**按以下顺序执行，中间不能有 `await`：

1. 如果免提录音正在进行（含正在申请麦克风），按 F2 的 `stopHandsFreeRecording({ discard: true })` 停掉，并**丢弃**这段录音，不送 ASR。
2. 调用 `clearTtsQueue()`：停止当前句和预取句，清空队列，隐藏被拒提示与限速提示，元素回到池里。
   - 用通用清理，**不要**用 `stopTtsByUser`：这里不是「用户不想听」，不要打停止标记，也不要触发补开麦。
3. 调用 `primeTtsAudio()`：在同一手势里解锁刚回到池里的元素。
4. 保留原有逻辑：
   - 朗读没开就打开（`setVoiceOn(true)`），并且和 D4 一样把 `ttsStoppedSessionRef.current` 置为 `null`；
   - `ttsSessionRef.current += 1`；
   - `streamDoneRef.current = true`；
   - 归一化文本后入队；
   - `playNextInQueue()`，此时 `ttsPlayingRef` 一定是 false，直接调用即可；
   - 清掉气泡上的 `pendingTtsText`。

**期望行为：**
- 点击后，旧回复（无论正在播放还是停在被拒提示）**不再出声**，卡片文字从头读到尾。
- 被拒提示立即消失。
- 正在流式输出的旧回复，后续分句因为会话号已变化不会入队。这是原有语义，不要改。
- 卡片读完后，如果免提开着，按原有门槛（966 行）开麦 **1 次**。

### F2（D3）免提录音幂等，并支持「停止并丢弃」

在 `startHandsFreeRecording`（约 719–791 行）上：

1. **新增一个 ref 记录免提录音状态**，例如：
   ```ts
   const handsFreeRecRef = useRef<{ recorder: MediaRecorder | null; discard: boolean } | null>(null);
   ```
   - `null` 表示空闲；
   - 非 `null` 表示「正在申请麦克风」或「正在录音」。
2. **入口检查**：`handsFreeRecRef.current` 非 `null` 就直接 `return`，**不得**再次调用 `getUserMedia`。否则先置为 `{ recorder: null, discard: false }`，再 `await getUserMedia`。
3. **在以下所有退出路径把它复位为 `null`**，每条路径都要复位，并且只能复位自己这一次创建的那个对象（用对象身份比较，避免误清后来的新一次）：
   - `getUserMedia` 之后的早退分支（会话已切换、免提已关）；
   - `catch`；
   - `mr.onstop` 的第一行；
   - 申请期间被 F2 第 4 点要求取消的情况。
4. **新增 `stopHandsFreeRecording({ discard })`**，同步执行：
   - 正在录音：置 `discard = true`，然后 `recorder.stop()`。`onstop` 看到 `discard` 时只释放资源，**不送 ASR、不调 `handleSend`**。
   - 还在申请麦克风（`recorder` 为 `null`）：置 `discard = true`。`getUserMedia` 返回后，看到 `discard` 就立刻停掉轨道、复位、`return`。
   - 空闲：什么也不做。
5. **不能改变的行为**：
   - 免提关闭时停止录音并丢弃（现有的 `tick` 加 `onstop` 逻辑）；
   - 静音 1.5 秒自动停并发送；
   - 30 秒上限；
   - 会话切换时丢弃。

这样一来，下面三种原本会开出两路录音的情况都会被拦住：
- 04-review-round2 的 R2-O1：服务端已发 done、还没到 EOF 时，点「关朗读」或「不听了」；
- 基线就有的 DRAINNAT：最后一句在 EOF 之前自然读完；
- 原本就有的 R2-O2：免提录音中点「帮我读」（已由 F1 第 1 步改为先停掉并丢弃）。

`stopTtsByUser`（1068–1073 行）和免提门槛（966 行）的代码**不改**。

### F3（D4）点「免提」打开时清除停止标记

「免提」按钮的 `onClick`（约 2007–2014 行）在 `next` 为 true 的分支里，在 `primeTtsAudio()` 之前加一行 `ttsStoppedSessionRef.current = null;`，与「朗读」按钮打开分支（1997 行）一致。

## 3. 报告

在 `03-report.md` 末尾追加「第 2 轮返修」，内容包括：
- 逐条写出 F1–F3 改动的行号与前后代码；
- 列出 `handsFreeRecRef` 所有的置位点和复位点，逐条说明为什么每条退出路径都覆盖到了；
- 在仓库外的前端克隆里重跑 02-spec 第 5.1 节全部命令，贴原样输出与退出码。注意：`frontend/package-lock.json` 已升到 next 16.3.8，而仓库里的 `node_modules` 还是旧版本，所以克隆里用 `npm ci --offline` 装依赖，不要复制仓库的 `node_modules`，也不要联网；
- 检查 `git status --porcelain` 只有白名单文件；
- 未决问题。

## 4. 验收（Claude 在主会话实测，Codex 不跑浏览器）

所有带免提的场景，都要求**同时在录音的 MediaRecorder ≤1**。

| 场景 | 脚本 | 判据 |
|---|---|---|
| CONFIRM-PLAY | 新写 | 朗读开，第二条回复播放中点旧卡片「帮我读」：点击后 50ms 以外旧回复 0 次 playing；卡片文字读完；同时出声 ≤1 |
| CONFIRM-BLOCKED | 新写 | 第一句模拟被拒，提示出现后点旧卡片「帮我读」：提示消失；被拒那句 0 次 playing；卡片文字读完（WebKit 与 Chromium） |
| CONFIRMHF / CONFIRMNAT | `m1_race.py` | 免提录音中点「帮我读」：那段录音被丢弃（点击后不发 `/asr/recognize`）；卡片读完后恰好开麦 1 次；最大并发录音 1 |
| DRAINOFF / DRAINSTOP / DRAINNAT / NODRAIN | `m1_race.py` | 最大并发录音 1；流结束后恰好开麦 1 次（DRAINNAT 是基线就有的问题，这次一并修好） |
| DOFF / DSTOP / DNAT / RECOFF / MIDSTOP | `m1c.py` | 同上 |
| HFON-AFTER-OFF（R2-O3） | 新写 | 流式中关朗读，再点「免提」打开：之后到达的分句会入队并读完 |
| V1–V11、A–H | `tts_v.py`、`tts_check.py`、`tts_rev.py` | 与 evidence-round1.md 的结论一致，不退化 |

## 附：第 3 次复核后的更正（2026-10-01）

- **F2.4 复位时机按实现为准**：申请麦克风期间被丢弃时，同步把 `handsFreeRecRef` 复位为 `null`；旧的 `getUserMedia` 返回后只负责停掉轨道。按原文「等返回后再复位」去做，会在「申请中点帮我读 → 卡片读完」时挡掉开麦，导致免提停住（第 3 次复核 GUMP 实测）。
  - 待 iPhone 真机确认的风险：两次 `getUserMedia` 同时在途时，iOS Safari 会不会把新开的轨道静音。
- **第 3 轮返修**：免提下改用打字（或其他方式）发送时，要停掉并丢弃正在进行的免提收音。修法见 `04-review-round3.md` 第 3 节。
