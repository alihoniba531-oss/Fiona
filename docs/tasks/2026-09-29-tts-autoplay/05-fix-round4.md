# 返修单 第 4 轮（收尾）：免提偶发停住、「不听了」后开免提、生成中「帮我读」、麦克风被拒

- **基线**：`main` HEAD `b38beca`，`frontend/app/page.tsx` 的 sha1 前缀为 `88de85ce`。下文行号都指这个版本。
- **依据**：
  - 用户 2026-10-02 拍板「做一轮收尾的小返修」，范围是本单 F4–F7；
  - `04-review-round3.md` 第 4 节 O1、O3、O4、O6；
  - `04-review-round4.md` 的 N1。
- 已有行为一律保持，包括：
  - 第 1–3 轮的全部修复；
  - `19e5804` 的换票限流与 429 退避；
  - `063a999` 的票据 TTL 150 秒，以及「点此播放」按剩余有效期决定是否重换票。

## 0. 硬规则（违反任一条即返工）

- **不得修改任何已有测试的输入或断言。**
- 不引入依赖，不改 `package.json` 和 lockfile。
- 不做真实网络调用，不下载。
- 不运行 `next dev`，不启动浏览器。
- 不写 git 状态，不读 `.env*`。
- 同一个文件不要让多个 subagent 并行改；派生子代理时不要传 model 或 effort 参数。
- **凡偏离本单原文的地方，都必须写进报告的「未决问题」**，不能只写在正文里。
- 只有影响「实现什么」的事才停下来；只影响「怎么验证」的事自己定。不回滚已完成的工作。
- **白名单**：`frontend/app/page.tsx`；本目录 `03-report.md`（只在末尾追加）。其他文件一律不动，后端一行不改。

## 1. 改动

### F4：丢弃正在录的免提收音时，立即释放占用标记（O1 / N1）

- **现状**：`stopHandsFreeRecording`（802–811）在录音分支里只调用 `recorder.stop()`，要等异步的 `onstop`（约 50–110ms）才把 `handsFreeRecRef` 复位。
- **问题**：在这段窗口里，任何开麦请求都会被 721 行拒掉，而且之后没有人重试，免提就停住了。已实测的两种触发：
  - 打字发送后，`/chat` 立即失败；
  - 点「帮我读」后，卡片换票立即失败。
- **改法**：在录音分支里，`stop()` 之后，如果 `discard` 为 true，就按对象身份立即复位：
  ```ts
  if (discard && handsFreeRecRef.current === rec) handsFreeRecRef.current = null;
  ```
- **要求**：
  - `onstop` 第一行原有的身份比较复位保留不动。它只会复位自己的那一次，不会误清后来新开的那次。
  - 被丢弃的录音在 `onstop` 里仍然不送 ASR。
  - 任何时刻，处于 `recording` 状态的 MediaRecorder 仍然最多一个。`stop()` 会同步把旧录音机置为 inactive，旧轨道仍在 `onstop` 里释放。

### F5：朗读已开时点「免提」，不清除「已停止」标记（O3）

- **改法**：「免提」按钮打开分支（约 2033–2040，当前在 2037 行无条件置 null）改为只在朗读本来是关着时才清除：
  ```ts
  if (!voiceOn) ttsStoppedSessionRef.current = null;
  ```
  其余不变：`primeTtsAudio()`、`setVoiceOn(true)` 照旧。口径与「帮我读」的 1273–1276 行一致。
- **期望**：
  - 朗读开着、对某条回复点了「不听了」之后再开免提：这条回复后面到达的句子仍然不读；流结束后免提照常开麦。
  - 朗读关着时点「免提」：仍然视为重新开朗读（维持 D4）。

### F6：回复还在生成时点「帮我读」，不提前开麦（O4）

- **改法**：`handleConfirmTts` 的 1278 行 `streamDoneRef.current = true;` 改为：
  ```ts
  if (!chatAbortRef.current) streamDoneRef.current = true;
  ```
  也就是说，只有当前没有在途的 `/chat` 请求时，才把流标为已结束。
- **期望**：
  - 新回复还在流式输出时点「帮我读」：卡片读完后不开麦。
  - 等这条回复的 `/chat` 结束（`finally` 置 `streamDoneRef=true` 并调用 `playNextInQueue`），或卡片读完时流已经结束，才开麦，**恰好 1 次**。
  - 没有在途请求时，行为与现在相同。
- **原因**：现在卡片一读完就开麦，用户这时说的话会被 `handleSend` 里 `chatAbortRef` 的早退判断悄悄丢掉（第 3 次复核 CSTREAMHF 实测）。

### F7：麦克风用不了时给出提示；免提失败时自动关闭免提并释放麦克风（含 O6）

- **适用范围**：只针对两个由用户触发的入口。
  - **免提**：`startHandsFreeRecording` 的 `catch`（796–799）。
  - **输入框旁的麦克风按钮**：内联录音的 `catch`（715，现在是 `catch (_) {}`）。
  - 「按住说话」（`startNlsAsr`）已经会显示「麦克风未授权」，**不改**。
  - 页面加载时的预申请（584–586）保持静默，**不改**。
- **提示文字**：
  - 错误名为 `NotAllowedError` 或 `SecurityError`：「没有麦克风权限，请在浏览器里允许使用麦克风」；
  - 其他任何错误（`NotFoundError`、`NotReadableError`、`mediaDevices` 不存在导致的 `TypeError`、`MediaRecorder` 不支持该格式等）：「麦克风用不了」；
  - 如果因此关闭了免提，句末加「，免提已关闭」。
- **免提失败时**：
  - 调用 `setHandsFree(false)`；
  - **释放已经拿到的资源**（O6）：如果 `getUserMedia` 已经返回了 stream，就停掉它的所有轨道；如果 `AudioContext` 已创建，就 `close()`。
  - 为此可以把 `stream` 和 `audioCtx` 的声明提到 `try` 之外。
  - `handsFreeRecRef` 的复位规则不变（按身份比较）。
- **控制台输出**：
  - `NotAllowedError`、`SecurityError`、`NotFoundError` 属于预期内的环境问题，改用 `console.warn`，避免开发模式下 Next.js 把它弹成红色错误框；
  - 其他错误保留 `console.error`。
- **内联录音失败时**：只显示提示（不涉及免提）；轨道释放逻辑照现有代码，如果 `getUserMedia` 已成功但后续步骤抛错，也要停掉轨道。
- **提示的界面**：
  - 新增一个 React 状态，例如 `micNotice: string | null`。
  - 渲染在输入区常驻的 `<div role="status" aria-live="polite">`（2075）里，排在两条朗读提示之后。
  - 写法与「浏览器拦下了自动朗读」那一行一致：
    - 外层 `mb-2 flex min-w-0 items-center gap-1 text-xs`；
    - 文字 `min-w-0 flex-1 text-muted-foreground`；
    - 右侧一个「知道了」按钮，`<button type="button">`，类名 `btn btn-quiet h-7 shrink-0 px-2.5 text-xs max-md:h-9`，点了就清除提示。
  - 不新增颜色，不改 `globals.css`；提示不显示时，输入区像素不变。
  - 以下情况也会清除提示：
    - 再次点「免提」打开；
    - 这两个入口之后有一次 `getUserMedia` 成功。
  - 不自动抢焦点。

## 2. 报告

在 `03-report.md` 末尾追加「第 4 轮返修」：
- 逐条写出 F4–F7 的行号与前后代码；
- 列出 `micNotice` 的所有设置和清除点；
- 说明 F7 中 `stream` 和 `audioCtx` 在每条失败路径上都被释放；
- 在仓库外前端克隆里用 `npm ci --offline` 装依赖，重跑 02-spec 第 5.1 节全部命令，贴原样输出与退出码（lint 警告数不得超过 26）；
- `git status --porcelain` 只有白名单文件；
- 未决问题（含任何偏离本单原文之处）。

## 3. 验收（Claude 主会话实测；所有新场景先在 `b38beca` 上确认失败）

| 场景 | 判据 |
|---|---|
| FASTFAIL（F4） | 免提录音中打字发送，`/chat` 立即返回 error：修改前 3/3 次免提停住；修改后 3/3 次读完/出错后重新开麦，录音机并发 ≤1 |
| STOPHF（F5） | 朗读开、慢速流、第一句被拒、点「不听了」，然后点「免提」：之后 0 张新票、0 次出声；流结束后开麦 1 次。修改前后续句子会被读出 |
| CSTREAMHF（F6） | 新回复流式中点「帮我读」：第一次开麦时刻不早于该回复的 EOF，且只开 1 次。修改前卡片读完就开麦 |
| MICDENY-HF（F7） | `getUserMedia` 被拒（`NotAllowedError`）：免提读完后提示「没有麦克风权限…，免提已关闭」，免提芯片熄灭，控制台无 error 级的 `[handsfree]` 日志；点「知道了」后提示消失 |
| MICDENY-INLINE（F7） | 输入框旁麦克风按钮在被拒时出现「没有麦克风权限…」提示 |
| MICNOTFOUND（F7） | `NotFoundError`：提示「麦克风用不了」 |
| RECTHROW（F7 / O6） | `getUserMedia` 成功但 `MediaRecorder` 构造抛错：提示「麦克风用不了，免提已关闭」，所有麦克风轨道都已停止（活轨道 0） |
| 回归 | 第 3 轮验收矩阵全部重跑（`batch_r3.sh`：TYPED-SPEAK、MAIN、CHFCTRL/CHFDISC、GUMP、PLAYHF、DBL2、CHFTONE、CSTREAM*、竞态 11 项、V1–V11、A–H、截图逐字节相同） |
