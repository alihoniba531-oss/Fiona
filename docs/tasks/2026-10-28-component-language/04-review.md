# 04 独立复核：组件语言统一（UI 复核第二批）

- 复核方：独立复核（与实现方、规格作者无对话上下文），仅以本工作树落盘文件为依据。
- 基线：`main` @ `6410890`；候选 = 工作树 `git diff HEAD` + 未跟踪新文件 `frontend/components/ConfirmDialog.tsx`、`frontend/lib/ttsChunks.ts`、`backend/tests/test_component_language.py`（含 R1 返修后状态）。
- 依据：`02-spec.md` v1（权威）、`05-fix-r1.md`、`verify/gate.sh`、`verify/measure.py`、`verify/gate-record.md`、`verify/results/*`。`03-report.md` 只作线索，全部结论自行复验。

## 1. 结论

**通过**：§6 第 1–7 条复核方自跑全绿、§3.2/§5 保留项逐字节核验无违反、6 个变异全部被新测试捕获、实测证据与门禁记录自洽且 HEAD 正控四项确败；仅有若干不阻塞合并的可优化项（见第 6 节）。

## 2. 验收标准逐条核验（§6 第 1–8 条）

### §6-1 `cd frontend && npx tsc --noEmit`

- 实际值：exit 0，无输出（复核方自跑，`npm_config_cache=/tmp/fiona-npm-cache`）。
- 期望：0。
- 判定：通过。
- 证据：后台作业输出 `== tsc == tsc-exit=0`；`gate.sh` 行 `PASS tsc exit 0`。

### §6-2 `npm run lint`

- 实际值：exit 0；`✖ 25 problems (0 errors, 25 warnings)`。
- 期望：0 errors，warnings ≤ 25（HEAD 基线 25）。
- 判定：通过。
- 证据：作业输出尾行；`gate.sh` `PASS lint errors 0`、`PASS lint warnings 25<=25`。

### §6-3 `npm run build`

- 实际值：exit 0（`rm -rf .next` 后全量构建，18/18 静态页）。
- 期望：0。
- 判定：通过。
- 证据：作业输出 `build-exit=0`；`gate.sh` `PASS build exit 0`。

### §6-4 后端验收集合

- 实际值：
  - 复核方自跑（含 `test_novel_p2_r1.py`）：`536 passed in 46.19s`，无 skipped 行（0 skipped）。
  - `gate.sh` 内子集（不含 r1）：`522 passed`、`0 skipped`；新测试单跑 `23 passed`。
- 期望：全通过；总数 ≥ 499 + 8；既有 499 条一条不少；`test_novel_p2_frontend.py::test_workbench_polls_only_running_books_and_pauses_on_visibility` 仍绿。
- 判定：通过（522 − 23 新 = 499 既有，一条不少；536 = 522 + `test_novel_p2_r1.py` 14 条）。
- 证据：`gate.sh` `PASS pytest subset passed 522>=507`、`PASS pytest skipped 0`、`PASS new test count 23>=8`、`PASS novel confirm( test still green 1`。

### §6-5 结构判据

| 判据 | 实际值 | 期望（HEAD 基线） | 判定 |
|---|---|---|---|
| 原生 `confirm/alert(` 扫描（app/components/lib 的 ts/tsx） | 0（扫描 135 个文件） | 0（12） | 通过 |
| `useConfirm()`：settings/page/LocalWatch/AgentMemory/ChatModel/NovelWorkbench | 各 1 | ≥1 | 通过 |
| `useNotice()`：settings、page | 各 1 | ≥1 | 通过 |
| `<ConfirmProvider>` in layout.tsx | 1 | 1 | 通过 |
| `font-semibold` in page.tsx | 0 | 0（3） | 通过 |
| `setMuted\|setHovered\|onMouseEnter\|VolumeX\|Trash2` in ChatBubble | 0 | 0（≥5） | 通过 |
| `setVoiceOn` in page.tsx | 5（:619 声明、:1601 帮我读、:2531/2535/2550 全局开关） | 与 HEAD 相同（HEAD 实测 5） | 通过 |
| `aria-label=` 总数 | 118 | ≥118（HEAD 118） | 通过 |
| `平台官方 AI · 无真人用户` in AgentExchangeWorkspace | 1 | 1 | 通过 |
| 12 段正文各恰好 1 次 + 新增「删除这条消息？」1 次 | 各 1 | 1 | 通过 |
| 中点 8 处新文案到位、旧写法清零 | 全 PASS | — | 通过 |

- 证据：`gate.sh` 输出 54 项全 PASS（FAIL=0，exit 0）；HEAD 基线由复核方自测：`git show HEAD:frontend/app/page.tsx | grep -cE '(^|[^.A-Za-z_])(window\.)?(confirm|alert)\((`|")'` = 4（page 4 处，全仓 12 处与规格 §2.3 表一致）、HEAD `setVoiceOn` = 5、HEAD `font-semibold` = 3、HEAD `aria-label=` = 118。

### §6-6 改动集合

- 实际值：`git status --porcelain` 仅 12 个白名单修改 + `backend/tests/test_component_language.py`、`frontend/components/ConfirmDialog.tsx`、`frontend/lib/ttsChunks.ts`、`docs/tasks/2026-10-28-component-language/`（本任务目录，预期）；`git diff --stat` 不含 `package.json`、`package-lock.json`、`next.config.ts`、`backend/`（新测试为 untracked）、`components/ui/`、`components/studio/`、`SongProjectCard.tsx`。
- 期望：与 §3.1 白名单一致。
- 判定：通过。
- 证据：`gate.sh` `PASS changes outside whitelist none`、`PASS no forbidden files in diff 0`；复核方另核 `git status --porcelain -- frontend/components/studio frontend/components/novel frontend/lib` 仅 `M novel/NovelWorkbench.tsx`（白名单）与 `?? lib/ttsChunks.ts`（新增白名单）。

### §6-7 ChatCard 未动

- 实际值：`diff <(git show HEAD:...ChatBubble.tsx | awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p') <(awk ... 当前)` 输出空（156 行块逐字相同）。
- 期望：空。
- 判定：通过。
- 证据：`gate.sh` `PASS ChatCard block diff vs HEAD 0`、`PASS ChatCard block extracted (lines) 156>=100`。

### §6-8 真实浏览器（复核方无浏览器，只审证据链）

- 实际值（`verify/results/cand-measure.json`，4 轮 = 昼/夜 × 1440/390）：
  - 消息行：`speak=4/4、copy=10/10、del=10/10` 可见、`svgInMetaRows=0`；m390 `minHeight=40`（d1440 为 28，规格只要求手机 ≥40）。
  - 朗读：点击后 `stopButtons=1`、`ticketRequests=1`；点停止后 `stopAfterStop=0`；全局开关 `voicePressed` 前后均 `false`。
  - 复制：`copiedLabels=1`，剪贴板 `hasStars/hasHeading/hasDashItem` 全 False、len=214。
  - 删除：`.confirm-dialog[open]` 且 `role=alertdialog`、正文「删除这条消息？此操作不可恢复。」、焦点「取消」；Esc 后 `openAfterEsc=0`、消息数 10→10、`deleteReqsAfterEsc=0`；确认路径（--full）10→9、`deleteReqsAfterConfirm=1`。
  - 原生弹窗：`nativeDialogs=[]`（4 轮均 0）；三处流程（删除对话→取消、上传非图片→知道了、设置页清空→取消）均出瓷片框（`deleteConversationDialog=1`、`uploadNotice=只能上传图片知道了`、`settingsClearDialog=1`）。
  - 入场动画：`animatedOnLoad=0`；发送后 `animatedAfterSend={total:11, animatedIdx:[9,10]}`（仅末尾两条）。
  - 焦点：Tab 30 步 `stops=30、badCount=0`。
  - 粗体：7 路由 + 历史抽屉 `boldTotal=0`。
  - 截图：`cand-d1440-day-confirm.png`（1440×900）、`cand-m390-night-confirm.png`（390×844）；复核方目视：瓷片底、朱字「删除」、无粗体、遮罩压暗，消息行文字按钮不悬停可见。
- HEAD 正控（`head-measure.json` day-d1440）：原生弹窗 3 次（三条原文被 `page.on("dialog")` 捕获，证明监听有效）、`animatedOnLoad=9`、焦点 `badCount=20/stops=28`（outline `auto`）、`boldTotal=4`（历史抽屉）——四项必须失败的判据在 HEAD 上确实失败。
- 期望：候选全过、HEAD 四项失败；`gate-record.md` 表格与 JSON 一致。
- 判定：通过（附两条证据链备注，见第 6 节可优化项 E1/E2：落盘 JSON 缺「打开确认框时粗体扫描」数据键、`labelAfterClick` 为定位器重解析假象）。
- 证据：`measure.py:98`（dialog 监听）、`:105-145`（消息行/朗读/复制/删除）、`:159-171`（动画/焦点）、`:180-189`（粗体）、`:135`（截图）；JSON 与 `gate-record.md` 表格逐项数值一致（3/9/20/28/4 与 0/0/0/30/0、4/10/10/40px、1 停止 1 换票、已复制无 Markdown 残留、Esc 0 DELETE 确认后 1 DELETE）。
- 判据「真的量到」的逐条结论：消息行可见性用 `opacity>0.5`+尺寸判定且鼠标停在 (1,1)，可识破悬停显隐（`measure.py:35`）；朗读以 `stopButtons`/换票请求计数为准；复制读真实剪贴板（`:126`）；删除计数前后消息数并计 DELETE 请求；焦点逐步读 computed style（`:53-59,170`）；粗体扫「自带文字且可见且 ≥600」元素（`:20-32`）。唯一未落盘的是「打开确认框时的粗体扫描」（见 E1），由静态分析补足：确认框 markup 仅 `text-base`/`text-[15px]`/`btn*` 类，`globals.css:348-356` 的 `.btn/.btn-primary/.btn-quiet/.btn-danger` 均不设 font-weight，`h2` 标题被 Tailwind preflight（`globals.css:1` `@import "tailwindcss"`）重置为 inherit，且本批 12 处均不传 title。

## 3. §3.2 / §5 逐条核验

### 3.1 被测试锁住的 ChatBubble 内容 / ChatCard / 天气函数 / 文字气泡条件 / 帮我读

- `ChatCard` + `weatherDayLabel/weatherCondition/weatherTemperature` 156 行块与 HEAD 逐字相同（§6-7）。
- `{/* 文字气泡` 之后第一个条件表达式 HEAD:350 与当前:384 逐字相同：`{(message.content || (message.isTyping && !message.generationStatus)) && message.content !== "[发了一张图片]" && (`。
- 「帮我读 / 不用」块（HEAD:374–390 区域）与当前逐字相同（`diff` 空）；`handleConfirmTts`（page.tsx:1595–1611）与 HEAD 逐字相同，`primeTtsAudio()` 仍在同一点击处理里同步调用。
- 既有测试全绿（536 passed）间接锁定 `MessageText` 导入、`isUser ? message.content : <MessageText`、`formatBeijingTime(` 等。
- 判定：通过。

### 3.2 `primeTtsAudio()` 用户手势链与单条朗读不 `setVoiceOn`

- `handleSpeakMessage`（page.tsx:1619–1632）函数体全同步、无 `await`/`setTimeout`/`.then(`：顺序为 `stopHandsFreeRecording({discard:true})` → `clearTtsQueue()` → `primeTtsAudio()`（第 3 条语句，先于一切异步）→ `ttsStoppedSessionRef.current=null` → `ttsSessionRef.current+=1` → `if(!chatAbortRef.current) streamDoneRef.current=true` → `splitTtsChunks(stripMessageMarkdown(text)).map(normalizeForTTS).filter(Boolean)` → 空则 return → push → `setSpeakingMessageId(id)` → `playNextInQueue()`，与规格 T3-6 逐条一致。
- 调用链同步：ChatBubble.tsx:431 `onClick={() => speaking ? onStopSpeak?.() : onSpeak(message.id, message.content)}` 直接调用，无中间异步。
- 函数体内无 `setVoiceOn`；全文件 `setVoiceOn` 计数 5 与 HEAD 相同（:1601 属「帮我读」`handleConfirmTts`，行为不变）。
- `clearTtsQueue` 末尾 `setSpeakingMessageId(null)`（page.tsx:1408）；`playNextInQueue` 队列空分支内、return 前 `setSpeakingMessageId(null)`（page.tsx:1309）。
- 判定：通过。证据：`awk '/const handleSpeakMessage/,/\}, \[/'` 输出；变异 M1/M2 证明测试能捕获违反。

### 3.3 12 段确认 / 提示正文逐字未改

- 复核方脚本从 HEAD 提取 12 个原生弹窗字面量（含反引号模板与 `${...}` 变量），在当前文件按 `body: <字面量>` 逐字节匹配：**12/12 命中**（settings 3、page 4、LocalWatch 2、AgentMemory 1、ChatModel 1、NovelWorkbench 1）。
- 判定：通过。

### 3.4 `await confirm(...)` 之后的「新鲜值复查」逐文件结论

- `app/settings/page.tsx`（#1 :58–66、#2 :120–129、#3 :143–145）：复查 `getUsername() !== username`；`getUsername()`（lib/auth.ts:68–70）调用时读 localStorage → **新鲜**，覆盖切号风险；#3 在 `await notice(...)` 后、`clearAuth()` 前同样复查，切号时不清新账号认证、不跳转，语义正确。**结论：新鲜，合格。**
- `app/page.tsx` #4 `handleClearChat`（:1633–1636）：原代码无任何前置守卫，「同一组守卫」为空集，无复查属照抄空集；动作仅本地 `setMessages([])`。**结论：可接受。**
- `app/page.tsx` #5 `handleDeleteConversation`（:1798–1804）：复查 `conversationLocked || conversationLoading`。两者是渲染期派生 state（:1638 `conversationLocked = isLoading || recording || inlineRecording || handsFree`；`conversationLoading` 来自 useConversations 的 state），执行中的闭包冻结于点击当次渲染 → 复查恒等于首检结果，**语义上是旧 state 复查 = 没查**；下游 `deleteConversation`（lib/useConversations.ts:184–185）也只有 `operationPending` ref 与闭包内 `enabled`，无新鲜账号读取。真实兜底是后端所有权校验（backend/routers/conversations.py:60–62 `get_current_user` + `agent_store.delete_conversation(user, id)`），跨账号删除不可能成功，最坏为跨标签切号后一次被拒请求与本地 UI 扰动。**结论：陈旧复查，语义无效；因后端所有权兜底且场景极端，列为可优化项（O1），不阻塞。**
- `app/page.tsx` #6/#7 `handlePickImage`（:2236–2247）：`await notice(...)` 后立即 return，无后续动作，无需复查。**结论：合格。**
- `app/page.tsx`（T3 新增）`handleDeleteMessage`（:1585–1591）：规格 T3-6 给定代码即无复查；动作 = 函数式 `setMessages` 过滤 + `DELETE /message/{dbId}`（后端按登录用户校验所有权）。**结论：与规格给定代码一致；同 O1 类弱项，不阻塞。**
- `components/LocalWatchSection.tsx` #8/#9（:169–191）：复查 `disabled` 为闭包旧值，**但**紧随的 `operate()`（:152–155）首行 `beginRequest()`（lib/useAccountIdentity.ts:44–45）在调用时经 `isCurrentOwner()` → `getUsername()` 读存储 → **新鲜**，切号即返回 null 中止；动作后还有 `request.isCurrent()`。**结论：复查本身陈旧，但同一同步块内有新鲜守卫，合格。**
- `components/AgentMemoryPanel.tsx` #10（:61–72）：复查含 `isCurrentOwner()`（调用时读存储，新鲜）+ 随后 `beginRequest()` 新鲜。**结论：新鲜，合格。**
- `components/ChatModelSection.tsx` #11（:230–240）：复查 `disabled || !config` 为闭包旧值，但随后 `beginRequest()` 新鲜。**结论：同 LocalWatch，合格。**
- `components/novel/NovelWorkbench.tsx` #12（:243–252）：复查 `isCurrentOwner()` 新鲜；`mutate()` 内部再查 `isCurrentOwner()` + `beginMutation()` 新鲜。**结论：新鲜，合格。**

### 3.5 其余 §3.2 保留项

- `aria-label` 总数 118（≥118）；diff 删除行中 `data-` / `-drawer` 命中 0 → 钩子与抽屉 id 未动。
- AI 身份披露：`平台官方 AI · 无真人用户` 仍恰好 1 次（AgentExchangeWorkspace.tsx:216 行内逐字保留）。
- 「界面文字不加粗」：diff 新增行无 `font-semibold/font-bold/fontWeight/font-weight/<strong>`；唯一新增 `<b>` 为 `<b className="readout font-normal">`（AgentExchangeWorkspace.tsx:227，规格 T5 要求）；确认框 markup 无加粗类（见 §6-8 静态补足）。
- 「新写文案不用中点」：新增行唯一含「·」者为保留行「平台官方 AI · 无真人用户」（规格明令一字不改），非新写文案。
- 断点：`/plaza`、`/settings`、`/profile` 三页 `max-md:` 计数当前 0 = HEAD 0（无新出现）；`page.tsx`、`ChatBubble.tsx` 沿用 `max-md:`（如 ChatBubble.tsx:427 `max-md:min-h-10`）。
- 布局/间距：消息行按钮类名 `btn btn-quiet h-7 px-1.5 text-xs` 与规格 T3-3 一致；用户消息元信息行去掉 `flex-row-reverse` 使行内顺序为「时间 复制 删除」，与规格 §1 文案顺序及截图实测一致，属消息行 redesign 本身；按钮间无中点/竖线，父容器 `gap-3`（ChatBubble.tsx:427）。
- 判定：通过。

### 3.6 §5 不允许的做法

- `primeTtsAudio()` 未被挪到 await/setTimeout/then 后（见 3.2）；单条朗读无 `setVoiceOn`（见 3.2）。
- 无 `window.confirm =` 之类全局替换（全仓扫描 0 原生弹窗且 12 段正文各自仍在，见 §6-5）。
- `ChatCard`、三天气函数、文字气泡条件、「帮我读/不用」未改（见 3.1）。
- 删除按钮不依赖悬停：ChatBubble.tsx:448 `{onDelete && !message.isTyping && (`，无 `group-hover:opacity`/`hovered` 残留（`setHovered|onMouseEnter` 计数 0）。
- 消息行按钮间无中点/竖线；新文案无「·」（见 3.5）。
- 既有测试零改动：`git status` 中 `backend/tests/` 仅新增 untracked 的 `test_component_language.py`；白名单外零改动（§6-6）。
- 判定：通过。

### 3.7 R1 返修单符合性

- `ConfirmDialog.tsx` 无 `createContext/useContext/readContext/ConfirmContext`；模块级 `let host`（:38）、`confirmImpl/noticeImpl`（:40–68）在 host 空时 `Promise.reject(new Error("ConfirmProvider missing"))`；`useConfirm/useNotice`（:70–76）只返回模块函数、函数体无 `use[A-Z]...(` 调用；`ConfirmProvider` 以 `useEffect` 注册/清理 host（:103–108，卸载仅当 `host === enqueue` 才置 null），返回 `<>{children}{dialog}</>`（:183–188）。
- 新增两条测试在位（test_component_language.py:311–327、:374–384），含不挂 Provider 的 node 行为用例。
- 复核方自跑 R1-3 全集：tsc 0 / lint 0 错 25 警 / build 0 / pytest（含 r1）536 passed 0 skipped。
- 判定：通过。

### 3.8 ConfirmDialog 实现审（任务书第 4 点）

- **模块级 host 与重挂载/严格模式**：`enqueue` 为 `useCallback([pump])`、`pump` 为 `useCallback([])` → 身份稳定，host 注册 effect 只跑一次；严格模式双挂载按「cleanup→create」顺序执行且同一实例回调身份不变 → 清理后重新注册同一 enqueue，host 正确；Provider 被替换时 React 先跑旧树 cleanup 再跑新树 effect，旧 cleanup 的 `host === enqueue` 守卫防止误清新 host（:105–107）。多文档（iframe）各自模块实例、各自 host，符合 R1-1 第 5 条。
- **多调用排队**：`enqueue` 入 `queueRef` 后 `pump`；`pump` 在 `activeRef` 非空时直接返回（FIFO 保留）；`settle` 末尾 `pump()` 取下一条；同一时刻仅一个 dialog（:90–101、:121）。
- **焦点归还**：打开前在 effect 内捕获 `document.activeElement`（仅当 `openerRef` 为 null，:128–130）；`settle` 先 `resolve` 再 `opener.focus()`（仅当仍 `isConnected`，:118–120）后 `pump()`；队列下一条重新捕获刚归还的焦点元素，行为合理。默认焦点：确认类取消钮、提示类唯一钮（:133）。
- **三条路径恰好 resolve 一次**：`settle` 首行取 `activeRef.current` 并立即置 null（:111–113），二次调用直接 return；Esc 走 `onCancel` + `preventDefault` + `settle(false)`（:146–149）；遮罩走 `onClick` 且 `target === currentTarget`（:150–152）；按钮走 `settle(true/false/undefined)`（:161–175）。notice 的 resolve 忽略入参 → `Promise<void>` 正常落定。浏览器实测 Esc 路径 0 DELETE、确认路径 1 DELETE 与之吻合。
- **`showModal()` 已 open 时抛错**：effect 有 `if (!dialog.open)` 守卫（:127）；`settle` 在切换 active 前同步 `dialog.close()`（:115），批渲染看到的就是已关闭的 dialog → 不会二次 `showModal()`；effect cleanup 的 `if (dialog.open) dialog.close()` 为幂等兜底（:134–136）。
- 残留弱项（不阻塞）：Provider 若在 dialog 打开/排队期间卸载（仅开发期 HMR 场景），在途 Promise 永不落定；渲染期（effect 前）调用 `useConfirm()` 会 reject——现有调用点全在事件处理内，无影响。

### 3.9 splitTtsChunks 审（任务书第 5 点）

- 复核方自写 16 组用例经 typescript 转译后在 node 执行：空串/全空白/纯换行 → `[]`；「第一句。第二句！」→ 1 段；600 字无标点 → `[250,250,100]` 且去空白拼回等于原文；`版本 4.5 发布。下一句` 与 `会议在 2026.10.28 召开。完` 不在数字间句点切；连续标点「真的吗？！…是的」成组不丢字；换行切分不丢字；自定义 `max=5` 硬切生效且每段 ≤5；400 字 200 句贪心拼为 `[250,150]`；段均 `trim` 且空段丢弃。
- 不丢字性质：所有用例「去空白拼回 == 去空白原文」成立（实现仅在 trim/硬切处丢空白字符）。
- 每段 ≤ max：贪心拼接与硬切均以 `limit` 为界（ttsChunks.ts:44–52、59–63）。
- 边界：硬切按 UTF-16 code unit，含 emoji 且单句超 max 时可能切断代理对（实测 `'a'+'😀'×200, max=250` 首段以孤立高代理结尾）；HEAD 流式路径 `flushSentences` 的 `slice` 同类问题，属既有行为、非回归 → 可优化项 O4。
- 与 HEAD 规则的差异：全角 `．` 视为句点、全角数字视为数字（ttsChunks.ts:2、5），比 HEAD `isRealBoundary`（page.tsx HEAD:1896–1899 仅 ASCII `\d`、且 `．` 不在切分集）略宽；实现方报告 §6.3 已披露，规格测试输入行为不变 → 接受，记录在 O5。
- 不依赖 React/window：文件零 import（ttsChunks.ts:1–2 仅常量）。
- 判定：通过。

### 3.10 新测试审（任务书第 6 点）

- 离线/不依赖 git/不读仓库外：仅 `Path(__file__).parents[2]` 下读文件 + 本地 `node` 子进程（probe 用 `require.resolve(..., {paths:[frontend]})`），无网络、无 git 命令、无仓库外路径（test_component_language.py:15–19、181–202、330–351）。
- 依赖探测写法与 `test_claude_agent_frontend.py:136–155` 同构（node probe + `pytest.skip`）。
- 断言区分力：6 个变异全部变红（见第 4 节）；行为级断言含 node 实跑 `splitTtsChunks` 与不挂 Provider 的 reject 用例。
- 已知形态：部分断言为源码形态（`slice_between(..., "}, [")` 锚点、`if (host === enqueue) host = null;` 字面串），等价改写可绕过；作为本任务回归锁足够，且与行为断言互补 → 记录在 O6。
- 判定：通过。

## 4. 变异实验记录

方法：改前 `cp -p` 按字节备份到 /tmp/b2-mut/，python 精确串替换（锚点出现次数断言为 1），跑 `backend/.venv/bin/python -m pytest -q tests/test_component_language.py -p no:cacheprovider`，改完拷回并比对 sha256；未使用 `git checkout`。中途一次脚本崩溃（子进程路径笔误）导致 page.tsx 短暂处于 M1 变异态，已即时从备份还原并复验总哈希（见第 8 节）。

| # | 变异 | 目标文件 | 新测试结果 | 还原校验 |
|---|---|---|---|---|
| M1 | `primeTtsAudio()` 挪进 `setTimeout(...,0)` | frontend/app/page.tsx | RED：`1 failed, 22 passed`，失败 `test_single_message_speak_chain` | sha256 一致 |
| M2 | 单条朗读加 `setVoiceOn(true)` | frontend/app/page.tsx | RED：`test_single_message_speak_chain` | sha256 一致 |
| M3 | ChatModelSection 的 `await confirm({...})` 换回原生 `confirm(` | frontend/components/ChatModelSection.tsx | RED：`test_source_tree_has_no_native_confirm_or_alert_dialogs` | sha256 一致 |
| M4 | `splitTtsChunks` 删除末段 flush（丢最后一段） | frontend/lib/ttsChunks.ts | RED：`test_split_tts_chunks_behavior` | sha256 一致 |
| M5 | 去掉 `!message.id.startsWith("db-")` 动画条件 | frontend/components/ChatBubble.tsx | RED：`test_chat_bubble_message_row_contract` | sha256 一致 |
| M6 | 删掉 host 卸载清理守卫（`if (host === enqueue)`） | frontend/components/ConfirmDialog.tsx | RED：`test_confirm_dialog_uses_module_level_queue_without_context` | sha256 一致 |

6/6 变红，且每个变异只红对应的 1 条（其余 22 条仍绿），说明断言定位准确、无连带假阳。

## 5. 必须修复项

无。

## 6. 可优化项（不阻塞合并）

- **O1（新鲜值复查）**：`app/page.tsx` `handleDeleteConversation`（:1798–1804）await 后复查的 `conversationLocked || conversationLoading` 是闭包旧 state，语义上等于没查；`handleDeleteMessage`（:1585）无任何复查。当前由后端会话/消息所有权兜底，无跨账号破坏面。建议后续给对话删除引入新鲜守卫（如点击时捕获 `getUsername()` 与恢复时比对，或把 locked/loading 镜像到 ref），与 settings/AgentMemory/Novel 的做法对齐。
- **O2（播放失败残留）**：`playNextInQueue` 的 `prepared = mkTtsAudio(next)` 失败分支（page.tsx:1316–1317）直接 return，不换票失败时 `speakingMessageId` 不复位，按钮停留「停止」直至用户点停止（`stopTtsByUser → clearTtsQueue` 复位）或他处触发队列空分支；可自愈但建议在该分支一并 `setSpeakingMessageId(null)`。
- **O3（代理对硬切）**：`splitTtsChunks` 硬切按 code unit，emoji 消息单句超 250 时可能产出孤立代理对（HEAD 流式 slice 同类，非回归）；建议按码点边界切（如 `Array.from` 或检查 `slice` 边界 charCode）。
- **O4（measure.py 证据补录）**：落盘 `cand-measure.json` 的 day-d1440 运行缺 `boldWithDialog` 键（而 `delete.countAfterConfirm` 存在，证明 --full 块执行过），HEAD JSON 又多出 `"speak": null` 键——两者都说明落盘 JSON 由与当前 `verify/measure.py` 不完全同字节的版本产出。规格 §6-8「含打开的确认框」的粗体判据因此没有落盘数据；本次以静态分析补足（确认框无加粗类、preflight 重置 h2、`.btn` 无 weight）。建议用当前 measure.py 重跑 `--full` 补齐该键，并在脚本里固化键集合。
- **O5（measure.py 定位器假象）**：`measure.py:111` 的 `labelAfterClick` 在点击后用 `has_text="朗读"` 定位器重解析，读到的是「另一条仍为朗读的按钮」，落盘值 `'朗读'` 有误导性；真正有效的信号是 `stopButtons=1`。建议改为点击前取 element handle 再读文本。
- **O6（测试形态断言）**：`test_component_language.py` 若干断言依赖源码字面形态（锚点串、`}, [` 切片），等价重构会误红/漏红；可逐步替换为 AST 或行为断言。
- **O7（全角句点偏差）**：`splitTtsChunks` 将全角 `．`/全角数字纳入句点规则，宽于 HEAD 流式规则；已披露且无害，建议在函数注释中注明与 `flushSentences` 的差异，避免后续误以为两者逐字同规则。

## 7. 给执行者的二次修改指令

无（本次复核通过，不需要二次修改）。

## 8. 哈希核对

- 开始：`(git diff HEAD; cat frontend/components/ConfirmDialog.tsx frontend/lib/ttsChunks.ts backend/tests/test_component_language.py) | shasum -a 256` → `3eeeee7c2c58d0000a6265b6fc0e1365b531fdd7a1e42c31d53e68ab50c9767a`（前 16 位 `3eeeee7c2c58d000`，与任务书预期一致）。
- 结束：同命令 → `3eeeee7c2c58d0000a6265b6fc0e1365b531fdd7a1e42c31d53e68ab50c9767a`，一致。
- `git status --porcelain` 结束态相对开始态：默认输出 16 行逐行相同（未跟踪的 `docs/tasks/2026-10-28-component-language/` 目录被折叠为一行）；以 `--untracked-files=all` 展开核对，结束态仅比输入集合多出 `docs/tasks/2026-10-28-component-language/04-review.md`（本文件），12 个 ` M` 跟踪修改与 3 个候选新文件均与开始态一致；变异实验全部按字节还原（各文件 sha256 与备份一致）。
