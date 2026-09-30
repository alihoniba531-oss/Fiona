# 朗读自动播放修复 · 第 0 轮独立复核汇总

汇总复核员（全新上下文）对 4 个视角复核员的结果与 5 条反驳结论做合并、去重、对照规格逐条判定，并给出返修指令。

## 0. 复核前提

- 被审文件 `frontend/app/page.tsx` sha1 = `92d3f360b6d7d934f73978a2cdfe24a985cc5c00`，与派单一致；4 位视角复核员与 5 条反驳结论均独立核对为一致。
- `git diff --name-only 8c7f0cf -- frontend backend` 仅 `frontend/app/page.tsx`；`round0.diff`（437 行）与工作区内容吻合。
- 输入材料：`02-spec.md`、`03-report.md`、`round0.diff`、`evidence-round0.md`、`harness/runs/{base,new}/*.jsonl`、`harness/runs/new/B390-{1,2}.txt`、`harness/shots/*.png`、`harness/tts_check.py`；复核员的 scratchpad 实测（`rev/*.json`、`wk_probe/out5.json`）逐个打开核对数值，与其陈述一致。
- 基线事实：`git show 8c7f0cf:frontend/app/page.tsx | grep -n "new Audio"` 命中 669 行（`new AudioContext()`）与 733 行（`new Audio()`）；基线免提开麦门槛为 779–780 行 `if (streamDoneRef.current && handsFreeRef.current)`。
- 后端事实：`backend/services/chat_service.py` 905–909 行（直接执行）与 812–815 行（补参执行）都对 `travel_plan` 先 `yield _sse({"card": result})`、再 `yield _sse({"text": playback})`，两个独立 SSE 事件。
- 硬规则遵守：除本文件外未修改仓库任何文件、未写 git 状态、未读 `.env*`、未使用浏览器面板工具（本汇总未启动任何浏览器）。

## 1. 结论

**不通过。** 2 条必须修复项仍成立（合并自 4 位复核员的 6 条 must_fix 候选；反驳阶段 0 条被推翻、0 条被降级）。两条根因都在 `clearTtsQueue` 里：一处把「代码清队列」当成「用户停止」，一处把进行中的解锁尝试作废。修复量很小（各约 5–10 行），但当前版本会让旅行规划卡的口播整段静默、让免提在卡片回复后卡住，属于可感知回归，不能合入。

第 5.2 节实测 A/C/D/E/G/H 通过，B 与 F 部分通过；第 5.1 节机械门禁通过（附注一处靠改无关代码通过的文本检查）。5.2 的 8 个场景全部是纯文本回复，没有覆盖卡片回复、错误路径与免提组合，这正是两条必须修复项漏网的原因；返修后必须补测（见 5.5）。

## 2. 必须修复项（合并后）

### M1. `clearTtsQueue` 把「当前会话已停止」标记塞进了所有清队列路径——旅行规划卡口播整段静默、免提在卡片/错误/不听了/关朗读之后再也不开麦

合并自：视角 1 第 1 条、视角 3 第 1 条与第 2 条、视角 4 第 1 条（四条同一根因，反驳阶段 4 次尝试推翻均失败）。

**代码位置**

- `frontend/app/page.tsx:1007`：`clearTtsQueue` 首行无条件 `ttsStoppedSessionRef.current = ttsSessionRef.current`。
- `:995`：`enqueueSpeech` 新增守卫 `if (ttsStoppedSessionRef.current === sessionId) return;`。
- `:929`：免提开麦门槛新增第三项 `&& ttsStoppedSessionRef.current !== ttsSessionRef.current`。
- 触发点：`:1582`（`data.card` 分支）、`:1609`（`catch`）、`:1930`（关朗读）、`:1988`（不听了）。`:1352`（`handleSend`）紧跟 `:1353` 换号，不受影响。
- `ttsStoppedSessionRef` 全文仅 4 处（413 声明、929 读、995 读、1007 写），从不重置为 `null`，只能靠 `:1188`/`:1353` 的 `ttsSessionRef.current += 1` 失效。

**触发序列与后果**

| 序列 | 操作 | 链条 | 后果 | 基线 8c7f0cf |
|---|---|---|---|---|
| A 听不到 | 朗读开 → 发「帮我规划三天北京旅行」 | 后端 card 事件 → `:1582 clearTtsQueue()`（stopped = mySession）→ 紧接的 text 事件 → `:1526 flushSentences` → `:1390 enqueueSpeech(chunk, mySession)` → `:995` 直接 return；`finally :1631` 尾段同样被拦。`:1547` 对 travel_plan 把 tip 置空，`:1588 pendingTtsText` 为 undefined，气泡上没有「帮我读」按钮，没有任何替代出声途径 | 旅行规划回复一个字不出声、无提示——与本任务要消灭的「整段静默」是同一种用户感受 | 会整段朗读 playback |
| B 免提卡住（零额外操作） | 免提开 → 说「今天天气怎么样」 | ASR → `handleSend` → 天气/搜索卡片 → `:1582`（stopped = mySession）→ done → `finally :1632 playNextInQueue` → 队列空 → `:929` 第三项为假 → 不调 `startHandsFreeRecording` | 麦克风不再打开，「免提」芯片仍亮，界面无任何提示 | `:779` 会开麦 |
| C 错误路径 | 流式出错 | `:1609 clearTtsQueue` → finally → 同 B | 同 B | 会开麦 |
| D 关朗读（已实测） | 免提开 → 播放中点「朗读」关 | `:1930` → stopped = session → finally `:1632` → `:929` 为假 | `HFOFF-fixed-chromium.json`：`gum_calls=[131]`（只有挂载预热），`hands_chip_on_at_end=true` | `HFOFF-base-chromium.json`：`gum_calls=[132, 12955]`，读完后开麦 |
| E 不听了（已实测） | 免提开 → 提示出现 → 点「不听了」 | `:1988` → 流已结束时没有任何代码再调 `playNextInQueue` | `HFSTOP-fixed-chromium.json`：`prompt_appeared=true, t_stop=5668, gum_calls=[172]`，免提芯片仍亮 | 基线无此按钮 |

恢复路径比复核员描述的还窄：免提按钮本身（`:1942-1949`）只 `setHandsFree`/`primeTtsAudio`/`setVoiceOn`，不开麦，关了再开也不恢复；`startHandsFreeRecording` 全文只在 `:930` 一处被调用。用户只能点旧卡片的「帮我读」（session+1）或手动打字/按住说话才能重新启动循环。

**违反的规格条款**

- 2.1「本页之后的所有朗读…都能正常出声」；
- 3.3「免提模式：…续播读完后，照常进入免提录音」——只授权在被拒期间抑制开麦；
- 3.3「不听了：效果等同 `clearTtsQueue()`」——基线的 `clearTtsQueue()` 从不抑制免提，也从不影响后续入队；
- 3.4「其他逻辑不变」（`enqueueSpeech` 只允许 `voiceOn` 守卫；免提「读完→录音」分支属原有逻辑）；
- §0「影响『实现什么』的决定要写进未决问题」——报告 3.3 第 5 条承认「已停止的 TTS 会话不再入队，也不会在空队列时启动免提录音」，但把它当作已定行为，未列入未决问题。

**为什么实测没抓到**：`evidence-round0.md` 的 A–H 全是假模型 5 句纯文本，没有卡片、没有错误、没有免提组合。

**修复方向**（具体指令见 5.1）：把「标记会话已停止」从 `clearTtsQueue` 挪到只有两个用户显式停止入口（不听了、关朗读）调用的 `stopTtsByUser`；`:929` 恢复基线门槛；`:995` 守卫保留；用户停止时若确实打断了正在进行的朗读且流已结束、免提开着，补一次开麦（否则免提死锁）。

### M2. `clearTtsQueue` 把进行中的解锁尝试 `primeAttempt` 置空，随后的 `AbortError` 不再被记为「已解锁」——与规格 3.2 明文相反

合并自：视角 2 第 1 条（must_fix，反驳失败、维持）与视角 1 第 2 条（同一缺陷，视角 1 评为 optional）。按反驳结论与本任务 must_fix 定义（违反规格明文即算）维持 must_fix。

**代码位置**

- `:1018-1024`：`clearTtsQueue` 收尾循环 `if (slot.owner || !slot.primeAttempt) continue; slot.primeAttempt = null; pause(); removeAttribute("src"); load();`。
- `:793-804`：`finish()` 首句 `if (slot.primeAttempt !== attempt) return;`——置空后早退，`unlocked` 永远不会由这次尝试写 true（`unlocked = true` 全文只有 `:796` 与 `:907` 两处）。
- 对照：`mkTtsAudio :831-833` 接手元素时同样 pause/移源但**不**置空 `primeAttempt`，那条路径的 AbortError 会被正确记为已解锁——两条路径不一致，`:1020` 是唯一让标记失真的写入点。

**触发序列**（同一手势内先 prime 再 clear，中间无 `await`）

1. 朗读开、槽位仍标记未解锁时按 Enter 发送：document 捕获 keydown（`:1044-1048`）先 `primeTtsAudio()` → 冒泡到 `handleKeyDown :1645-1651` → `handleSend` 在 `:1352 clearTtsQueue()` 之前没有任何 await → 同一任务内 pause/移源 → `play()` 以 AbortError 拒绝 → `finish` 早退。主会话 harness 的 `send()` 正是 `fill + press Enter`，Enter 在 prime settle 之前到达。
2. 点「朗读」关闭：捕获 click 先 prime，`:1930 clearTtsQueue` 后到。
3. 点「不听了」：同理。

**证据**

- `harness/runs/new/results-v2.jsonl` WebKit B 行与 `B390-1.txt`、`B390-2.txt`：`tickets: 6, ended: 5, prime_plays: ["rej:AbortError","rej:AbortError","rej:AbortError"]`——「朗读」点击里的两次 prime 都被随后 Enter 的清队列打断；第三次是「点此播放」里 `resumeBlockedTts :1031` 因 `!preload.slot.unlocked` 放弃预取后重新 prime、又被 `tryPrefetch` 接手。多出的第 6 张票就是被放弃的预取句重新换票。对照旧钩子版本 `results.jsonl`（首句因钩子漏拦真实播放成功、`:907` 把槽位标为 unlocked）同流程 `tickets: 5`。
- 视角 2 独立探针 `wk_probe/out5.json`（Playwright 无头 WebKit 26.6，元素创建与手势外 play 都放在页面内 ≥7 秒后的定时器里）：元素 K 在真实 click 内 `src=静音WAV; play(); pause(); removeAttribute('src'); load()` → `rej:AbortError`，7.5 秒后（`userActivation.isActive=false`）换 HTTP 源 play → `ok` 并 ended；正控 H/N（从未碰手势）同条件 `rej:NotAllowedError`。即 WebKit 在 `play()` 同步阶段就已移除该元素的手势限制，被取消的尝试确实已解锁，规格 3.2 的判定规则是对的，代码让标记比真实状态保守。

**后果**

- (a) 已真解锁的元素在之后每一次 click/keydown/touchend 上仍会被设静音源并 `play()`——包括点「朗读」关闭的那一下（捕获监听在 `voiceOn` 翻转前执行）；在 iOS 上每次 play 都会激活 MediaPlayback 音频会话、打断正在听的音乐。这与 3.2「以后不再对它放静音」及 3.2 末段的意图直接冲突，不依赖任何低概率条件。
- (b) 进入被拒续播路径时无谓放弃已换好票的预取句并多换一张票；`/tts/ticket` 按 IP 限 20/分钟（`backend/routers/voice.py:270`），证据文件已记录超限会整段静默跳句。
- 不会造成「听不到」（元素本身已解锁），因此视角 1 评为 optional；但违反规格明文，且修复是零风险的单行删除，维持 must_fix。

**违反的规格条款**：3.2「其他情况：算作已解锁，以后不再对它放静音。包括…因为随后被换源或暂停而得到 `AbortError`」；3.1「`clearTtsQueue`…对池里的元素只做 pause + 移除 src + load()」。

**修复方向**：删除 `:1020` `slot.primeAttempt = null;` 一行，其余不动。删除后 pause/移源/load 保证 pending promise 必以 AbortError 拒绝（HTML 规范与探针 K 均证实）→ `finish` 通过身份校验 → `unlocked = true` → `primeAttempt = null` → 此时 `getAttribute("src")` 已为 null，`finish` 不再碰元素。若 `play()` 早已因 NotAllowedError 拒绝，promise 已 settle，后续 pause 不会改写它，仍判未解锁。期间新手势因 `:789` `primeAttempt` 非空而跳过，不会重复 prime；被 `mkTtsAudio` 接手时 owner 非空，`finish` 同样不碰元素。

## 3. 可优化项（合并去重）

| 编号 | 标题 | 来源 | 位置 | 本轮一并处理？ |
|---|---|---|---|---|
| O1 | 播放中关朗读→再开朗读，同一条回复剩余句子不再朗读（基线会继续读）。实测 `TOGGLE-fixed-chromium.json` `tickets_after_reenable=[]`，基线 `TOGGLE-base` 再开后 3 句入队、5 句 ended | 视角 4 第 2 条 | `:995` 守卫 + `:1933` 开朗读分支 | **建议**：改动一行，有对照实测，与 M1 同一处代码 |
| O2 | 为让 5.1 文本检查通过而改无关代码 `new AudioContext()` → `new window.AudioContext()`。规格的 `grep -n "new Audio"` 模式本身写宽了（基线也命中 669 行），实现方没在报告里指出模式缺陷而是改代码绕过 | 视角 3 第 3 条 | `:711` | **建议**：改回基线写法；把检查改为 `grep -nE 'new Audio\s*\('`（当前文件 0 行）。同类模式（改无关代码让检查过）本项目已有前科，不应留在 diff 里 |
| O3 | `role="status" aria-live="polite"` 容器随提示一起条件渲染，VoiceOver/NVDA 对「新插入且自带内容」的 live region 常不播报 | 视角 3 第 4 条 | `:1983` | **建议**：live region 常驻、内容条件渲染；外层 div 不带 class，隐藏时 0 高、无 margin；改完复跑 `shot_footer.py` 确认 H 仍逐字节相同 |
| O4 | 被拒提示显示期间点旧卡片的「帮我读」：会话号推进但不清队列，提示不消失，需再点一次「点此播放」，且被拒那句丢失 | 视角 1 第 4 条 + 视角 3 第 5 条 | `:1185-1196`、`:888`、`:1036-1038` | 不建议：改 `handleConfirmTts` 触及 3.4「不变」条款，场景窄；列入未决问题（附录 B） |
| O5 | 正在播放另一段时点「帮我读」，已预取就绪的下一句被整句跳过（基线会播）。`:888` 按规格 3.1 字面要求在 play 前核对会话号，与 3.4「会话号失效语义不变」冲突 | 视角 4 第 3 条 | `:888`、`:1188` | 不建议：规格自身两条冲突，需规格作者拍板；列入未决问题 |
| O6 | 预取句升为当前句前不挂 `error` 监听：预取期间网络错误事件丢失，升主后 `play()` 对 `MEDIA_ERR_NETWORK` 不拒绝而永久挂起，队列卡住无提示 | 视角 1 第 3 条 + 视角 3 第 6 条 | `:854-856`、`:892-898` | 不建议：基线同一缺口、低概率；另开任务。最小改法：`playPreparedTts` play 前 `if (prepared.audio.error) { finishCurrentTts(prepared); return; }` |
| O7 | 「点此播放」不换票、不重 load，票据 60 秒 TTL / 4 次 use（`voice.py:30-31`）；iOS 上 preload 封顶 metadata，用户 >60 秒才点则被拒句与预取句被 error 跳过 | 视角 2 第 2 条 | `:1036-1038`、`:897` | 不建议：iOS 语义本机无法实测，前端/后端方案二选一需规格作者决定；列入未决问题 |
| O8 | 静音解锁元素未 `muted`，iOS 上每次 prime 都会激活音频会话打断背景音乐；探针 L 证明 muted 解锁同样有效 | 视角 2 第 3 条 | `:792`、`:807`、`:831` | 不建议：iOS 未实测，M2 修复后 prime 次数已大幅减少；后续任务 |
| O9 | 关闭「朗读」那次点击仍可能在捕获阶段起一段 ≤40ms 静音（随后被 clearTtsQueue 暂停） | 视角 1 第 5 条 | `:1044-1048`、`:1929-1931` | 不建议：只在槽位仍标记未解锁时发生，M2 修好后概率趋零 |
| O10 | 证据中「手机 390 宽 1 次未出现提示」最可能是 `/tts/ticket` 20/分钟限流（当时并行跑 Chromium 批量），换票 429 → 每句 ready=false → 从未调用真实 play → 模拟拒绝钩子不触发 | 视角 4 第 4 条 | `:851`→`:945`；`voice.py:270` | 无代码改动。主会话在无并行、距上次换票 ≥60 秒条件下用 `tts_check.py webkit B --width 390` 复跑 3 次并保存完整输出 |
| O11（本汇总新增） | 5.2-F Chromium 停止延迟 562ms 超过规格「200ms 内」；四位复核员均未提及。`tts_check.py:205-206` 的 `t_off` 取在 Playwright `voice.click()` 之前，包含 Playwright 可操作性检查与鼠标事件派发开销；代码里 `clearTtsQueue` 在按钮 onClick 内同步 `pause()`，找不到能延迟的路径。WebKit 同口径 35ms | 本汇总 | `:1930` | 无代码改动。主会话复测：把 `t_off` 改为页面内 document 捕获阶段 click 监听里记录 `performance.now()`，或用 `page.evaluate(el => el.click())` 触发；若仍 >200ms 再查代码 |

## 4. 规格逐条判定

### 4.1 第 5.1 节（机械门禁）

| 检查 | 判定 | 证据 |
|---|---|---|
| `npx tsc --noEmit` 退出码 0 | 通过 | 报告表格；`evidence-round0.md`「机械门禁」主会话独立复跑退出码 0 |
| `npm run lint -- --max-warnings=28` | 通过 | 26 警告 0 错误（基线 28，少的是旧 `clearTtsQueue` 两处 `catch (_)`）；主会话复跑一致 |
| `npm run build` | 通过 | 退出码 0；主会话复跑一致。报告如实记录了 symlink node_modules 首次失败与改用实体副本 |
| `git status --porcelain` 只有白名单 | 通过 | `M frontend/app/page.tsx` + 本任务目录；本汇总复跑一致 |
| `grep -n "new Audio" page.tsx` 0 行 | 通过（附注） | 退出码 1；但基线本就命中 `new AudioContext()`，实现方靠改 `:711` 为 `window.AudioContext` 通过——见 O2 |
| `grep -rn 'new Audio\|createElement("audio")'` 只在池创建处 | 通过 | 仅 `:778`，注释「The only audio creation site」，`Array.from({length: 2})` |
| `shasum backend/*.db` 与开工前相同 | 通过 | `172d800a…`、`403a086c…`；主会话复核一致 |
| `git diff --stat -- frontend/AGENTS.md backend/` 为空 | 通过 | 本汇总复跑：`git diff --name-only 8c7f0cf` 仅 page.tsx |
| §0 白名单 / 不引依赖 / 不改测试 | 通过 | 未新建 `frontend/lib/ttsAudio.ts`；package.json/lockfile/globals.css 无 diff；静音 WAV 代码内生成（44 字节头 + 320 采样，字段经视角 2 字节级校验） |

### 4.2 第 5.2 节 A–H（主会话实测）

| 场景 | 判定 | 证据与备注 |
|---|---|---|
| A（WebKit）首字延迟 5 秒 | **通过** | 修复版 3/3：5/5 ended 按序、0 次 NotAllowedError、元素 2 个；基线 2/2 全部 `rej:NotAllowedError` ×5 |
| B（WebKit）首句模拟被拒→点此播放 | **部分** | 桌面 1280：提示 2–6ms 出现、被拒期间 0 句 ended、点击后 5/5 按序 ended、提示消失——判据本身通过。未通过的部分：① 票据 6 张而非 5 张（`results-v2.jsonl`、`B390-{1,2}.txt`），根因 M2；② 手机 390：3/4 通过，1 次 8 秒内未出现提示、完整输出未保存、原因未查明（O10 推断 429，需隔离复跑确认）。另 B 的「不丢句」在 O7 描述的 iOS >60 秒场景未验证 |
| C 提示出现时点「不听了」 | **通过** | WebKit 与 Chromium：之后 0 次 playing、提示消失、朗读开关仍开（`results.jsonl` C 行 `ended: 1` 是钩子旧版漏拦首句，证据文件「已排除的异常 2」已说明）。注意 C 判据未覆盖「免提 + 不听了」，该组合在 `HFSTOP-fixed-chromium.json` 实测为卡住（M1 序列 E） |
| D 两轮对话、中途打断 | **通过（附注）** | WebKit 2/2、Chromium 5/6：新回复 5 句按序 ended、任一时刻最多 1 个元素出声（`max_sounding=1`）、旧回复 0 次再出声、元素 2 个。Chromium 1 次失败归因 `/tts/ticket` 429（`runs/chromium-stall/` 交替 8 次基线 3/8、修复版 3/8，卡住时都没拿到票据） |
| E（Chromium）预取无空档 | **通过** | 句间空档 51–57ms（基线 50–55ms）；首音 690–810ms（基线 730–790ms），同一量级 |
| F 播放中关朗读 200ms 内停止 | **部分** | WebKit：35ms、之后 0 次 playing——通过（基线 1198ms、继续读 3 句）。Chromium：562ms，超过 200ms 判据；测量口径见 O11，需主会话换口径复测后才能判定 |
| G 元素总数 ≤2 | **通过** | 所有场景 `audio_elements=2`；视角 4 的 LONG/LONGB/TOGGLE/HF/HFOFF/HFSTOP 补测同样为 2；基线每句 1 个（5–9 个） |
| H 390/1280 截图 | **通过** | 提示隐藏时页脚截图与基线逐字节相同（WebKit/Chromium × 1280/390，`shots/{base,new}-*-footer.png`）；`webkit-B-390-page.png` 提示行单行放下、两按钮完整可见；`webkit-B-1280-prompt.png` 正常 |

**5.2 未覆盖但本轮复核发现有回归的场景**（返修后必须补测，判据见 5.5）：卡片回复（travel_plan 口播、天气/搜索卡）、流式错误路径、免提 + 卡片 / 关朗读 / 不听了、关朗读再开。

### 4.3 第 3 节设计要求（四位复核员通过项摘要，本汇总抽查代码位置无误）

- 3.1 元素池：唯一创建点 `:778`，恰好两个，`preload="auto"`，存 ref 不重建；owner 只在 `:840` 赋值、只在 `:820-821` 按身份释放；所有把 current/preload 置空的路径都同步释放或转移归属；`mkTtsAudio` 返回 null 只在两元素都有主人时发生，逐路径推演无「playing=false 且两元素都被占」的死状态。
- 3.1 监听：ended/error 只在票据 src 设好后于 `:892-898` 挂上，`AbortController` signal 成对清理；`releaseTtsAudio :817` 先 abort 再 pause/移源/load，load 引发的 emptied/abort 不会打到旧句回调；静音 ended 发生在挂监听之前。
- 3.1 迟到结果：`canUse() :841-842` 在 fetch 后、json 后、设 src 后各查一次（owner/cancelled/aborted/session）；play 前 `:888` 再查；play promise 回调按身份守卫（`:906`、`:910`）。
- 3.2 解锁函数同步、只处理空闲且未解锁且无进行中尝试的元素；NotAllowedError 之外一律记为已解锁（除 M2 缺陷）；收尾只在仍空闲且 src 仍为静音源时清理。四个显式手势（`:1933`、`:1946`、`:1186`、`:1036`）都在任何 await 之前调用；兜底监听在 document 捕获阶段、以 `voiceOn` 为门、卸载时移除。视角 2 探针 M 证实捕获阶段监听算手势，探针 I 证实手势内 `createElement` 即解锁（池的懒创建是双保险，不要挪到 useEffect）。
- 3.3 被拒行为、提示位置/内容/样式/无障碍、「点此播放」六步顺序、「不听了」不关开关、关朗读立即停止：逐条与代码对应（`:906-913`、`:1027-1041`、`:1983-1989`、`:1928-1931`）。按钮类名与 `ChatBubble.tsx:294` 一致，只用 Tailwind 工具类，无 focus() 调用。
- 3.4 票据请求体字段不变；`<audio>` 只用 `/tts/stream?ticket=`；预取保留；`normalizeForTTS` 与切句不在 diff 内；`enqueueSpeech` 的 `voiceOn` 守卫原样保留（但其后追加了 M1 的会话守卫）；`handleConfirmTts` 仍自动开朗读。
- 「双声」不可能：预取句在升主前从不 `play()`，`resumeBlockedTts` 只对当前句 play；实测 `max_sounding ≤ 1`。

## 5. 给 Codex 的返修指令（第 1 轮）

### 5.0 硬规则与白名单（重申规格第 0 节，违反任一条即返工）

- **不得修改任何已有测试的输入或断言。**
- 不引入依赖，不改 `package.json` 和 lockfile。
- 不做真实网络调用，不下载任何东西。
- 不运行 `next dev`（它会改写 `frontend/AGENTS.md`）。
- 不写 git 状态：不 commit、不 stash、不 checkout、不 reset。
- 不读 `.env*`。
- 沙箱里起不了浏览器，不要尝试启动浏览器；浏览器实测由 Claude 在主会话里做。
- 同一个文件不要让多个 subagent 并行改。
- 只有影响「实现什么」的事才停下来写进报告「未决问题」；只影响「怎么验证」的事自己定。任何情况下不回滚已完成的工作。
- **白名单**：`frontend/app/page.tsx`；可新建 `frontend/lib/ttsAudio.ts`（本轮不需要）；本目录的 `03-report.md`。除此之外一律不动，后端一行不改。
- 本轮返修只做下面 5.1–5.3 列出的改动，不做其他重构。以下行号均指当前工作区版本（sha1 `92d3f360…`）。

### 5.1 M1：把「用户停止」标记从通用 `clearTtsQueue` 里拿出来，免提门槛恢复基线

1. **`clearTtsQueue`（`:1006-1025`）**：删除第 1007 行 `ttsStoppedSessionRef.current = ttsSessionRef.current;`。`clearTtsQueue` 不再写任何会话标记，其余逻辑不动（第 1020 行另见 5.2）。
2. **新增 `stopTtsByUser`**，放在 `clearTtsQueue` 定义之后、`resumeBlockedTts` 之前（`startHandsFreeRecording` 定义在 `:698`，可直接引用）：
   ```ts
   // 用户显式停止（不听了 / 关朗读）：同一条流式回复的后续分句不再入队；
   // 若打断的是正在进行的朗读且流已结束、免提开着，补一次开麦，免提循环不能因此停住。
   const stopTtsByUser = useCallback(() => {
     const wasPlaying = ttsPlayingRef.current;
     ttsStoppedSessionRef.current = ttsSessionRef.current;
     clearTtsQueue();
     if (wasPlaying && streamDoneRef.current && handsFreeRef.current) startHandsFreeRecording();
   }, [clearTtsQueue, startHandsFreeRecording]);
   ```
   `wasPlaying` 条件不能省：免提麦已经在录音的空闲状态下点关朗读时不能再起第二个 MediaRecorder。流未结束时不在这里开麦，由 `finally :1632 → playNextInQueue → :929` 的基线门槛负责。
3. **只有两个入口改用它**：
   - `:1988`「不听了」按钮：`onClick={stopTtsByUser}`；
   - `:1930`「朗读」关闭分支：`stopTtsByUser(); setVoiceOn(false);`。
   - `:1090`（账号切换 cleanup）、`:1215`（`resetConversationPresentation`）、`:1352`（`handleSend`）、`:1582`（卡片分支）、`:1609`（catch）**保持调用 `clearTtsQueue()`**，不打标记。
4. **`:929` 免提门槛恢复基线写法**：`if (streamDoneRef.current && handsFreeRef.current) {`，删除 `&& ttsStoppedSessionRef.current !== ttsSessionRef.current`。
5. **`:995` 的 `enqueueSpeech` 守卫保留不动**（它仍负责「不听了 / 关朗读之后同一条流不再入队」）。
6. `ttsStoppedSessionRef` 的声明 `:413` 保留。

自检（改完在克隆里跑）：`grep -n "ttsStoppedSessionRef" frontend/app/page.tsx` 应恰好 4 处：声明、`enqueueSpeech` 读、`stopTtsByUser` 写、以及（若做 O1）开朗读分支置 null；`:929` 一行不再出现它。

### 5.2 M2：`clearTtsQueue` 不再作废进行中的解锁尝试

`:1017-1024` 改为（只删一行、改一条注释，其余保留）：

```ts
    // A click that clears the queue may have just primed an otherwise idle slot: stop the silent
    // audio but keep primeAttempt so finish() still classifies the resulting AbortError as unlocked (spec 3.2).
    for (const slot of ttsAudioPoolRef.current ? getTtsAudioPool() : []) {
      if (slot.owner || !slot.primeAttempt) continue;
      slot.audio.pause();
      slot.audio.removeAttribute("src");
      slot.audio.load();
    }
```

**不要改 `finish()`（`:793-804`）**：pause/移源/load 后 pending 的 `play()` promise 必以 AbortError 拒绝，`finish` 通过 `primeAttempt === attempt` 校验 → `unlocked = true` → `primeAttempt = null`；此时 `getAttribute("src")` 已为 null，`finish` 不会再碰元素。

### 5.3 建议本轮一并处理的可优化项（改动小、有对照实测、风险低）

- **O1**：`:1933` 开朗读分支改为 `ttsStoppedSessionRef.current = null; primeTtsAudio(); setVoiceOn(true);`，使关朗读再开后同一条流的后续句子重新可入队。`handleConfirmTts` 已 `ttsSessionRef.current += 1`，不需要再置 null。
- **O2**：`:711` 改回 `const audioCtx = new AudioContext();`。在 `03-report.md` 5.1 表格该行如实写：`grep -n "new Audio"` 命中 1 行且为 `:711` 的 `new AudioContext()`（Web Audio 上下文，不是媒体元素；基线同样命中），并注明建议规格作者把检查改为 `grep -nE 'new Audio\s*\('`（该模式当前文件 0 行）。
- **O3**：`:1983-1989` 改为 live region 常驻、内容条件渲染：
  ```tsx
  <div role="status" aria-live="polite">
    {ttsPlaybackBlocked && <div className="mb-2 flex min-w-0 items-center gap-1 text-xs">
      …原有 span 与两个按钮不变（「不听了」onClick 已按 5.1 改为 stopTtsByUser）…
    </div>}
  </div>
  ```
  外层 div 不带任何 class，提示隐藏时 0 高、无 margin，不改变像素。

其余 O4–O11 本轮不动；O4/O5/O7 由用户拍板（附录 B）。

### 5.4 报告要求（追加到 `03-report.md`，标题「第 1 轮返修」）

- 逐条列出本轮改动的行号与前后代码；
- 写明 `stopTtsByUser` 与 `clearTtsQueue` 的分工，以及「不听了 / 关朗读在免提下补开麦」这一产品决定（附录 B 第 1 条）已按本复核默认实现，仍待用户确认；
- 重跑第 5.1 节全部命令并贴原样输出与退出码（含 O2 后 grep 命中 1 行的说明）；
- 「未决问题」列出附录 B 的 1–4 条，不要自行决定。

### 5.5 验证判据（Claude 主会话实测；Codex 不跑浏览器）

除复跑 5.2 A–H 外，新增以下场景，全部须通过：

| 编号 | 场景 | 判据 |
|---|---|---|
| V1 travel_plan | 朗读开，发一条会返回 `travel_plan` 卡片的消息（假模型/假意图返回 card + text 两个事件） | text 事件的分句全部进入 `ttsQueueRef` 并按序 ended；`enqueueSpeech` 不在 `:995` 返回；基线同样场景对照 |
| V2 免提 + 卡片 | 免提开（Chromium `--use-fake-device-for-media-stream`，钩住 `getUserMedia`），问一个返回天气/搜索卡片的问题 | 流结束后 `getUserMedia` 被再次调用（`gum_calls` 出现第二个时间戳），与 `HFOFF-base` 同构 |
| V3 免提 + 关朗读 | 复跑视角 4 的 HFOFF 场景（脚本 `scratchpad/rev/tts_rev.py`） | `gum_calls` 有第二次调用；朗读芯片灭、免提芯片亮 |
| V4 免提 + 不听了 | 复跑 HFSTOP | 点「不听了」后 `getUserMedia` 被再次调用；不得出现两路并发 MediaRecorder（钩子计数 `MediaRecorder` 构造且 `state === "recording"` 的实例 ≤1） |
| V5 免提 + 错误路径 | 让 `/chat` 中途断流 | 流结束后开麦 |
| V6 不听了后不再入队 | 流仍在送句时点「不听了」 | 同一回复后续分句被 `:995` 丢弃、0 次 playing；下一条新消息照常朗读 |
| V7 M2 票据数 | 复跑 5.2-B（WebKit 1280 与 390） | `/tts/ticket` 恰为 5 张；`prime_plays` 里 AbortError 之后不再出现同一槽位的重复 prime |
| V8 O1 | 复跑 TOGGLE | 再开朗读后剩余句子入队并 ended（与 `TOGGLE-base` 同构） |
| V9 O3 | 复跑 `shot_footer.py` | 提示隐藏时页脚截图与基线逐字节相同 ×4；提示显示时 390 单行、按钮完整 |
| V10 F 复测 | 按 O11 换口径 | Chromium 停止延迟 ≤200ms |
| V11 B390 隔离复跑 | 按 O10 | 3/3 出现提示；若仍失败保存完整输出与 `_events/_tickets` |

## 附录 A. 被反驳项

无。5 条反驳结论全部 `refuted=false`、`downgrade_to_optional=false`。反驳过程中补充的事实已并入 M1/M2 正文：免提按钮本身不开麦（恢复路径更窄）；`:1609` 错误路径的 `clearTtsQueue` 之前已 `ttsBuf = ""` 且流已终止，「吞句」无实际后果、但「不开麦」成立；`stopTtsByUser` 补开麦需 `wasPlaying` 前置条件；`mkTtsAudio :831-833` 不置空 `primeAttempt` 说明 `:1020` 是唯一失真点。

## 附录 B. 未决问题（供用户拍板）

1. **「不听了」/「关朗读」在免提模式下是否应重新开麦？** 规格 3.3 未写。本复核默认：应开麦（否则免提芯片亮着却永远不录音，等同卡住），且只在确实打断了正在进行的朗读且流已结束时开一次。若用户希望「不听了 = 退出免提循环」，改为在 `stopTtsByUser` 里 `setHandsFree(false)` 而不是开麦。
2. **O4**：被拒提示显示期间点「帮我读」，是否应先放弃被拒的旧回复（`if (ttsPlaybackBlocked) clearTtsQueue();` 置于 `primeTtsAudio()` 之前）？涉及 3.4「`handleConfirmTts` 不变」。
3. **O5**：规格 3.1「play() 之前核对会话号」与 3.4「会话号失效语义不变」冲突——正在播放时点「帮我读」，已预取就绪的下一句是照播（基线）还是跳过（当前）？
4. **O7**：「点此播放」不换票 + 票据 60 秒 TTL 在 iOS 上的丢句风险，前端按 `ticketIssuedAt` 超 50 秒重新换票，还是后端放宽 TTL（超白名单）？
5. **O8**：是否把静音解锁改为 `muted=true`（减少 iOS 打断音乐面）？需 iOS 真机验证。

## 附录 C. 证据索引

- 规格 / 报告：`docs/tasks/2026-09-29-tts-autoplay/02-spec.md`、`03-report.md`
- diff 与哈希：`~/.claude/projects/-Users-yangjing-Desktop-ai-workspace/baselines/2026-09-29-tts-autoplay/{round0.diff,round0-page.sha,base-head.txt}`
- 主会话实测：同目录 `evidence-round0.md`；`harness/runs/new/{results.jsonl,results-v2.jsonl,B390-1.txt,B390-2.txt}`；`harness/runs/base/results.jsonl`；`harness/runs/chromium-stall/`；`harness/shots/`；F 计时口径 `harness/tts_check.py:201-211`
- 视角 4 补测（Chromium 假麦克风）：`/private/tmp/claude-501/-Users-yangjing-Desktop-ai-workspace/ce86f452-f08b-4591-81cf-b3418bbb4d36/scratchpad/rev/{HF,HFOFF,HFSTOP,TOGGLE,LONG,LONGB}-*.json`，脚本 `tts_rev.py`、`batch.sh`；未跑完：HFCARD、LONG2/LONG2B、CONFIRM、SWITCH、R429
- 视角 2 WebKit 探针：同 scratchpad `wk_probe/probe5.py`、`out5.json`（元素 H/I/J/K/L/M/N）
- 基线代码：`git -C Fiona show 8c7f0cf:frontend/app/page.tsx`（免提门槛 779–780、`new Audio` 669/733）
- 后端：`backend/services/chat_service.py:812-815, 905-909`；`backend/routers/voice.py:30-31, 270`
