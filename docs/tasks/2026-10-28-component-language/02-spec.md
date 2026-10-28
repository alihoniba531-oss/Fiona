# 02 规格：组件语言统一（UI 复核第二批）

- 规格版本：v1（2026-10-28）
- 基线：`main` @ `6410890`；工作分支 `feat/component-language`（本工作树）
- 来源：`docs/tasks/2026-10-28-ui-review/01-audit.md` 的 P1-3、P2-9、P2-13、P2-14、P2-15、P3-17；用户已拍板：消息行改「朗读 / 复制 / 删除」文字按钮，原生弹窗一次全换。
- 级别：L2（组件与文案，不改接口、数据模型、依赖）。全程不设中途确认。
- 执行者：dsh（DeepSeek Flash，max）；Claude 做门禁与真实浏览器实测；独立复核另派。

---

## 1. 产品目标

六件事，都是「同一种东西在不同地方长得不一样 / 做得不对」：

1. **消息行**：每条分身消息下面那个小喇叭是死按钮（点了只换图标），删除只在鼠标悬停时出现（手机上点不到）。改成一行 12px 文字按钮：分身消息「时间　朗读　复制　删除」，自己的消息「时间　复制　删除」，不悬停也看得见。「朗读」只读这一条，读的时候字变「停止」。「删除」先确认。
2. **确认框**：12 处用的是浏览器自带的 `confirm()` / `alert()`，样式和影青釉完全脱节，桌面壳里也不可定制。换成一个共用的瓷片确认框。
3. **焦点**：只有 `.btn` / `.chip` 有墨线焦点框；书签导航、对话列表、消息行按钮、主题圆钮等用的是浏览器默认蓝框。统一成墨线。
4. **粗体**：违反「界面文字不加粗」的残留（对话页 3 处 `font-semibold`、广场 1 处裸 `<b>`）。
5. **中点**：主界面新写的文案还在用「A · B」分隔。本批只改主界面、且没有被既有测试或后端文案锁住的 8 处（清单见 T5）。
6. **入场动画**：消息滑入动画每条都有，切换对话时整列一起滑。只给这次会话里新出现的消息。

## 2. 现状事实（HEAD `6410890` 实测；行号以 HEAD 为准）

### 2.1 消息行（`frontend/components/ChatBubble.tsx`）

- `:4` 引入 `Volume2, VolumeX, Trash2, Globe, LoaderCircle, RotateCcw, ArrowUpRight`。`Volume2` 另用于 `:380`「帮我读」按钮；`Globe`、`ArrowUpRight` 用于 `ChatCard`；`VolumeX`、`Trash2` 只用于消息行。
- `:290` `const [muted, setMuted] = useState(false);`、`:291` `const [hovered, setHovered] = useState(false);`；`:318–319` 根元素的 `onMouseEnter/onMouseLeave` 只为 `hovered` 服务。
- `:316` 根元素 class 含 `msg-in-right`（用户）/ `msg-in-left`（分身），每条都滑入。`globals.css:397–408` 定义这两个动画；减弱动态由 `globals.css:580–588` 全局关掉。
- `:322–325`：分身名一行 `<div className="text-[13px] tracking-[0.1em] text-[color:var(--ink2)]" title={\`${agentName} · AI 分身\`}>{agentName}{message.replyModelLabel && <span title={message.replyModelLabel}> · 由你的模型回复</span>}</div>`。
- `:392–419` 元信息行：时间 `<span className="readout …">{timeStr}</span>`；分身消息一个图标按钮（`title={muted ? "播放语音" : "静音"}`，只切 `muted`，不接任何朗读逻辑）；`hovered && onDelete && !message.isTyping` 时一个垃圾桶图标（`title="删除这条消息"`），点击直接 `onDelete(message.id, message.dbId)`。
- 消息 id：历史消息由 `lib/useConversations.ts:57` 映射为 `` `db-${message.id}` ``；本机提醒 `lib/localWatch.ts:130` 也是 `db-` 前缀；本次会话里新发的用户消息 `app/page.tsx:1853` 为 `Date.now().toString()`。
- 既有测试锁住的 ChatBubble 内容（一律不得改动）：`test_ui_polish_markdown.py:358–361`（`import MessageText…` 与 `isUser ? message.content : <MessageText`）、`test_claude_agent_frontend.py:128–134` 与 `:158–175`（`ChatCard` 渲染、抽出 `function weatherDayLabel(` / `weatherCondition(` / `weatherTemperature(` / `ChatCard(` 四个函数块用 node 渲染，模拟了 `Globe`、`ArrowUpRight`）、`test_song_frontend.py:77–84`、`test_claude_agent_r1_frontend.py:162–167`、`test_chat_image_tool_frontend.py:90–98`（`{/* 文字气泡` 注释之后第一个 `{… && (<div` 的条件表达式）、`test_ui_polish_beijing_time.py`（`formatBeijingTime(`）。

### 2.2 朗读链路（`frontend/app/page.tsx`）

- 「帮我读」的处理 `handleConfirmTts`（`:1586–1602`）：`stopHandsFreeRecording({ discard: true })` → `clearTtsQueue()` → `primeTtsAudio()`（**必须在同一个用户手势里同步调用**，`:1164` 注释）→ 若朗读关着就 `setVoiceOn(true)` → `ttsSessionRef.current += 1` → `if (!chatAbortRef.current) streamDoneRef.current = true` → `normalizeForTTS(text.trim())` 整段推进 `ttsQueueRef` → `playNextInQueue()`。
- 单段上限：`mkTtsAudio`（`:1185`）只取 `text.slice(0, 300)` 换票；流式回复用 `flushSentences`（`:1888` 起）按句切、单段 ≤250 字。所以整条长消息直接推一段只会读前 300 字。
- `playNextInQueue`（`:1289–1324`）：队列空时（`:1302` `if (!next)`）返回；`clearTtsQueue`（`:1382–1401`）清空队列与当前播放；`stopTtsByUser`（`:1405–1410`）= 记停止会话 + `clearTtsQueue()`。`playNextInQueue` 不检查 `voiceOn`；`voiceOn` 只挡流式回复的自动入队（`enqueueSpeech` `:1369`）。
- `handleDeleteMessage`（`:1577–1582`）直接从列表删并 `DELETE /message/{dbId}`，没有确认。
- `isLoading`（`:450`）为真表示有回复在流式生成。
- `stripMessageMarkdown(text: string): string` 在 `lib/messageMarkdown.ts:362` 导出，目前没有调用方。

### 2.3 原生弹窗（12 处，`grep -rnE '(^|[^.A-Za-z_])(window\.)?(confirm|alert)\((\`|")' frontend/app frontend/components frontend/lib` 实测 12 行）

| # | 位置 | 现状 |
|---|---|---|
| 1 | `app/settings/page.tsx:57` | `confirm(\`确定清空「${username}」的所有聊天记录？此操作不可恢复。\`)` |
| 2 | `app/settings/page.tsx:113` | `confirm(\`将永久删除「${username}」的账号、聊天、画像、匹配、帖子、上传文件、自带模型配置与 Key。确定继续？\`)` |
| 3 | `app/settings/page.tsx:128` | `alert("账号数据已删除，但有媒体文件需要管理员继续清理。")`，之后立即 `clearAuth()` 与 `redirectTop(…)` |
| 4 | `app/page.tsx:1610` | `confirm("清空当前聊天界面？（历史记录仍保留）")` |
| 5 | `app/page.tsx:1776` | `confirm("删除这段对话及其中的消息？其他对话和分身设定会保留。此操作不可恢复。")` |
| 6 | `app/page.tsx:2216` | `alert("只能上传图片")` |
| 7 | `app/page.tsx:2220` | `alert("图片不能超过 5MB")` |
| 8 | `components/LocalWatchSection.tsx:265` | `confirm(\`吊销「${device.name \|\| "未命名设备"}」的令牌？监控程序将停止。\`)` |
| 9 | `components/LocalWatchSection.tsx:297` | `confirm(\`删除规则「${rule.name}」？\`)` |
| 10 | `components/AgentMemoryPanel.tsx:60` | `if (clearing \|\| loading \|\| !isCurrentOwner() \|\| !confirm("清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。")) return;` |
| 11 | `components/ChatModelSection.tsx:229` | `if (disabled \|\| !config \|\| !confirm("确定删除自带模型配置与 Key？之后聊天将使用平台模型。")) return;` |
| 12 | `components/novel/NovelWorkbench.tsx:242` | `confirm(\`确定删除「${book?.title \|\| "这本书"}」？章节、推演和留言都会删除，无法恢复。\`)` |

- 同名的本地函数 `confirm()`（`SongProjectCard.tsx:359`、`studio/BreakdownDialog.tsx:26`、`studio/BrainTrial.tsx:174`、`studio/QuoteDialog.tsx:55`）是组件自己的确认函数，不是原生弹窗，**不在本单范围**。
- 既有测试 `backend/tests/test_novel_p2_frontend.py:124` 断言 `"confirm(" in NovelWorkbench.tsx 源码`。所以新 API 的调用写法必须让源码里仍出现 `confirm(`（见 T2：`const confirm = useConfirm();` 后 `await confirm({…})`）。
- 根布局 `app/layout.tsx:97–101`：`<body className="h-full antialiased"><LensDefs />{children}<PwaRegister /></body>`。每个路由（含 iframe 抽屉里的 `/settings?embed=1`、`/plaza?embed=1` 等）都是独立文档，都经过这个根布局。
- 现有对话框样式先例：`globals.css:502–504` 的 `.image-preview-dialog`（`background:var(--hi)` + rim / lip / lipdk 内阴影 + `--drop` 外阴影；`::backdrop` 用写死的 `rgba(31,41,38,.18)`，`.dark` 下 `rgba(0,0,0,.45)`——`::backdrop` 不一定继承根变量，所以写死）。

### 2.4 焦点

- `globals.css:300` `@layer base { * { @apply border-border outline-ring/50; } }` 只设了轮廓颜色。
- `globals.css:356` `.btn:focus-visible,.chip:focus-visible { outline:1px solid var(--ink); outline-offset:3px; }`（components 层）。
- 其余可聚焦元素（`Sidebar.tsx` 书签导航与主题圆钮、`ConversationPicker.tsx` 列表项按钮、消息行按钮、`role="radio"` 的外观分段等）没有自定义焦点样式，用浏览器默认 `outline: auto`。
- `outline-none` 共 40 处，其中 10 处没有任何 `focus:` / `focus-visible:` 替代：`page.tsx:2477`（对话弹层容器，`tabIndex=-1`）、`:2650`（输入框 textarea）、`:2752/2781/2876/2907`（抽屉容器，`tabIndex=-1`）、`match/page.tsx:403`（真人聊天 textarea）、`history/page.tsx:160`（搜索框）、`login/page.tsx:190`（手机号输入）、`NewsCardContent.tsx:146`（`tabIndex=-1` 的标题）。

### 2.5 粗体

- `page.tsx:217` `font-semibold text-xs`（「神秘好友」）、`:2420` `text-xs font-semibold`（「当前对话记录」）、`:2440` `text-[11px] font-semibold`（历史抽屉日期）。
- `AgentExchangeWorkspace.tsx:222`：`<small className="font-normal …"><b className="readout">…</b> / <b className="readout">…</b>…`——`.readout` 只在后代选择器 `.readout b` 里设了 `font-weight:400`（`globals.css:341`），`<b className="readout">` 自身仍是 bolder。
- 其余 `<b>` 都在 `.readout` 内或带 `font-medium`（500，允许）。

### 2.6 中点（主界面）

本批只改下表 8 处（均已核对：既不被 `backend/tests` 锁住，也不是后端产出或 10-06 规格 §4.2 列明须原样保留的文案）：

| # | 位置 | 现在 | 改为 |
|---|---|---|---|
| 1 | `ChatBubble.tsx:322` title | `` `${agentName} · AI 分身` `` | `` `${agentName}（AI 分身）` `` |
| 2 | `ChatBubble.tsx:324` | `<span title=…> · 由你的模型回复</span>` | 细竖线分隔（见 T5）+「由你的模型回复」 |
| 3 | `app/settings/page.tsx:248` | `Chloe AI 助理 · 内测版` | `Chloe AI 助理（内测版）` |
| 4 | `app/plaza/page.tsx:212` | `{feed.loading ? "更新中 · " : ""}获取于 …` | `{feed.loading ? "更新中，" : ""}获取于 …` |
| 5 | `app/plaza/page.tsx:617` | `标签 · 最多 5` | `标签（最多 5 个）` |
| 6 | `app/profile/page.tsx:110` | `.join(" · ")` | `.join("、")` |
| 7 | `components/LocalWatchSection.tsx:288` | `{rule.name} <span …>· {typeLabels[rule.kind]} · {rule.enabled ? "已启用" : "已停用"}</span>` | `{rule.name} <span …>（{typeLabels[rule.kind]}，{rule.enabled ? "已启用" : "已停用"}）</span>` |
| 8 | `components/AgentExchangeWorkspace.tsx:215–216` | `"我的 AI 分身 · 发起方"`、`"对方 AI 分身 · 受邀方"` | `"我的 AI 分身（发起方）"`、`"对方 AI 分身（受邀方）"`；**同一行的 `"平台官方 AI · 无真人用户"` 一字不改**（AI 身份披露，10-06 规格 §4.2 保留项） |

明确**不改**（被测试或后端锁住，或属作者专用工具）：`page.tsx:402/403/406/410`（输入区模型标签，`test_ui_polish_page_contracts.py` 与 `test_mobile_chat_fix.py` 锁定）、`:2559/2568`（提醒 chip，`:2568` 被测试锁定，两条保持一致）、`:1644/1700`（系统通知标题）、`:1358` 与 `lib/useHotTopics.ts:41`（正则）、`SongProjectCard.tsx`（`test_song_frontend.py:43` 锁定「写歌 ·《」）、`AgentExchangeWorkspace.tsx:363/473`（与后端导出文案「AI 审稿通过 · 待用户验收」对应）、`components/studio/*`、`components/novel/*`、`lib/*`。

### 2.7 门禁基线（HEAD 实测，next 16.4.3）

- `cd frontend && npx tsc --noEmit` → 0；`npm run lint` → 0 errors，**25 warnings**。
- `cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py -p no:cacheprovider` → **499 passed**。
- 计数：原生弹窗 12；`page.tsx` 的 `font-semibold` 3；ChatBubble 的 `msg-in-` 1；`aria-label=`（`frontend/app` + `frontend/components` 的 tsx）118。

## 3. 技术约束

### 3.1 白名单

修改：
- `frontend/app/layout.tsx`
- `frontend/app/globals.css`
- `frontend/app/page.tsx`
- `frontend/components/ChatBubble.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/app/plaza/page.tsx`
- `frontend/app/profile/page.tsx`
- `frontend/components/LocalWatchSection.tsx`
- `frontend/components/AgentMemoryPanel.tsx`
- `frontend/components/ChatModelSection.tsx`
- `frontend/components/AgentExchangeWorkspace.tsx`
- `frontend/components/novel/NovelWorkbench.tsx`

新增：
- `frontend/components/ConfirmDialog.tsx`
- `frontend/lib/ttsChunks.ts`
- `backend/tests/test_component_language.py`
- `docs/tasks/2026-10-28-component-language/03-report.md`

其余一律不动：不改 `package.json` / lockfile / `next.config.ts`；不改既有测试的输入、断言与夹具；不改后端；不删文件；不提交 git。完成标准与验收命令的覆盖范围与本白名单一致（本规格所在目录本身已在工作树里，属预期）。

### 3.2 必须原样保留

- §2.1 列出的全部被测试锁住的 ChatBubble 内容；`ChatCard` 及其上方三个天气函数**一字不改**（测试会把它们抽出来用 node 渲染）。
- 10-06 规格 §4.2：所有 `aria-label`（总数不得少于 118）、`data-*` 钩子、`#…-drawer` id、`primeTtsAudio` 的用户手势链（朗读相关点击必须在同一个点击处理里同步调用 `primeTtsAudio()`，不能放进 `await` 之后或 `setTimeout` 里）、AI 身份披露文案。
- 12 处确认 / 提示的**正文一字不改**（就是 §2.3 表里引号内的文字，含模板变量）；只换承载方式。
- `page.tsx:402/403/406/410/2559/2568` 及 §2.6「不改」清单里的所有中点文案。
- 「帮我读 / 不用」两个按钮（`ChatBubble.tsx:374–390`）与 `handleConfirmTts` 的行为不变。
- 界面文字不加粗：不新增 `font-semibold` / `font-bold` / `fontWeight` / `font-weight ≥ 600` / 不带 `font-normal`、`font-medium` 且不在 `.readout` 内的 `<b>` / `<strong>`。
- 新写的界面文案不得用中点「·」分隔。
- 断点：会被 iframe 内嵌的页面（`/plaza`、`/settings`、`/profile`）只能用 `mobile:` 变体，不得写 `max-md:`；`page.tsx`、`ChatBubble.tsx` 沿用 `max-md:`。
- 桌面与手机现有布局不变（本单不动任何间距、尺寸，除了消息行新按钮本身）。

### 3.3 环境

- 沙箱 workspace-write，有网。跑 npm 前 `export npm_config_cache=/tmp/fiona-npm-cache`；`frontend/node_modules`（next 16.4.3）与 `backend/.venv` 已就位，不要重装。
- 沙箱里没有浏览器，§6 第 8 条由 Claude 用真实浏览器量；你负责把代码写对、把 §6 第 1–7 条跑绿，并在报告里写明每条视觉判据对应的代码依据。
- 修改前端前先读 `frontend/AGENTS.md` 与 `frontend/node_modules/next/dist/docs/` 里与 client component、`<dialog>` 无关的部分不必读；本单只用 React 客户端组件和原生 `<dialog>`。

## 4. 任务清单

### T1 共用确认框 `frontend/components/ConfirmDialog.tsx`（新文件，接口名固定）

```ts
"use client";
export interface ConfirmOptions {
  body: string;            // 正文（必填，就是原 confirm/alert 的文字）
  title?: string;          // 本单不用，留接口
  confirmLabel?: string;   // 默认「确定」
  cancelLabel?: string;    // 默认「取消」
  danger?: boolean;        // true 时确认按钮用 .btn-danger（朱字），否则 .btn-primary
}
export interface NoticeOptions { body: string; title?: string; okLabel?: string /* 默认「知道了」 */ }
export function ConfirmProvider({ children }: { children: React.ReactNode }): JSX.Element;
export function useConfirm(): (options: ConfirmOptions) => Promise<boolean>;
export function useNotice(): (options: NoticeOptions) => Promise<void>;
```

行为：
1. `ConfirmProvider` 内部维护一个 FIFO 队列，同一时刻只显示一个对话框；前一个关闭后再显示下一个。
2. 用原生 `<dialog>` + `showModal()`。确认类 `role="alertdialog"`，提示类用默认 `dialog` 角色；`aria-labelledby` 指向标题（有标题时），`aria-describedby` 指向正文。
3. 打开时：确认类默认聚焦「取消」按钮，提示类聚焦唯一按钮。关闭后把焦点还给打开前的 `document.activeElement`（若仍在文档里）。
4. Esc（`cancel` 事件）与点击遮罩（`event.target === dialog`）= 取消，`confirm` 解析为 `false`；`notice` 解析为 `undefined`。点确认按钮解析为 `true`。
5. `useConfirm()` / `useNotice()` 在 Provider 之外调用时抛出 `Error("ConfirmProvider missing")`。
6. 样式（类名固定 `confirm-dialog`，写进 `globals.css`，见 T6）：宽 `min(420px, calc(100vw - 32px))`，`m-auto`，圆角 12px，`p-0`；内部 `px-6 pt-6 pb-5`；标题 `text-base tracking-[.06em]`；正文 `whitespace-pre-wrap text-[15px] leading-[1.85] text-[color:var(--ink)]`（无标题时正文就是问句）；按钮行 `mt-6 flex justify-end gap-2`；取消用 `btn btn-quiet`，确认用 `btn btn-danger` 或 `btn btn-primary`，提示的按钮用 `btn btn-primary`。不加粗。
7. `app/layout.tsx`：`<body>` 里用 `<ConfirmProvider>` 包住 `{children}`（`<LensDefs />` 与 `<PwaRegister />` 位置不变）。

### T2 把 12 处原生弹窗换成共用确认框

每个文件在组件顶部取 `const confirm = useConfirm();`（需要提示的再取 `const notice = useNotice();`），调用写成 `if (!(await confirm({ body: <原文>, confirmLabel: <下表>, danger: <下表> }))) return;`，所在处理函数改为 `async`。**`await` 之后必须重新检查调用前的同一组守卫**（账号是否仍是当前账号、是否仍可操作等，按原条件照抄一遍），防止对话框开着时切换了账号。

| # | 位置 | confirmLabel | danger |
|---|---|---|---|
| 1 | settings 清空聊天记录 | 清空 | true |
| 2 | settings 永久删除账号 | 永久删除 | true |
| 3 | settings 删号后媒体未清理（`alert`） | `notice`，按钮「知道了」；`await` 之后再 `clearAuth()` 与 `redirectTop(…)` | — |
| 4 | page 清空当前聊天界面 | 清空 | false |
| 5 | page 删除对话 | 删除 | true |
| 6 | page 只能上传图片（`alert`） | `notice` | — |
| 7 | page 图片不能超过 5MB（`alert`） | `notice` | — |
| 8 | LocalWatch 吊销令牌 | 吊销 | true |
| 9 | LocalWatch 删除规则 | 删除 | true |
| 10 | AgentMemoryPanel 清空记忆 | 清空 | true |
| 11 | ChatModelSection 删除自带模型 | 删除 | true |
| 12 | NovelWorkbench 删除书 | 删除 | true |

### T3 消息行（`ChatBubble.tsx` + `page.tsx` + `lib/ttsChunks.ts`）

1. `frontend/lib/ttsChunks.ts`（新文件）导出纯函数 `export function splitTtsChunks(text: string, max = 250): string[]`：
   - 在 `。！？!?；;\n` 处切句；英文句点 `.` 两侧都是数字时不切（与 `page.tsx:1896–1899` 同规则）；
   - 把相邻句子贪心拼成不超过 `max` 字的段；单句超过 `max` 时在 `max` 处硬切；
   - 每段 `trim()`，丢掉空段；输入为空或全空白返回 `[]`；
   - 不依赖 React、不访问 `window`/`document`。
2. `ChatBubble` 新增可选 props（名称固定）：
   ```ts
   onSpeak?: (id: string, text: string) => void;
   onStopSpeak?: () => void;
   speaking?: boolean;        // 这一条正在被单条朗读
   speakDisabled?: boolean;   // 有回复在流式生成时为 true
   ```
3. 元信息行（`:392–419`）改为：时间（原样）+ 文字按钮。按钮统一 `className="btn btn-quiet h-7 px-1.5 text-xs"`（手机 40px 触控由 `globals.css:376` 全局规则保证，不另写）：
   - 「朗读」：仅分身消息、`onSpeak` 存在、`!message.isTyping`、`message.content` 非空且不是 `"[发了一张图片]"` 时显示；`speaking` 为真时文字为「停止」、点击调 `onStopSpeak()`；否则文字为「朗读」、点击调 `onSpeak(message.id, message.content)`；`speakDisabled` 为真时 `disabled`。
   - 「复制」：两种消息都显示（同样排除空内容与 `"[发了一张图片]"`、`isTyping`）。点击 `navigator.clipboard.writeText(isUser ? message.content : stripMessageMarkdown(message.content))`；成功后文字变「已复制」，失败（含 `navigator.clipboard` 不存在）变「复制失败」，1500ms 后恢复「复制」。计时器在卸载时清掉。
   - 「删除」：`onDelete && !message.isTyping` 时显示，**不再依赖悬停**；点击 `onDelete(message.id, message.dbId)`；悬停色用 `hover:text-[color:var(--seal)]`。
   - 删掉 `muted`、`hovered` 两个 state、根元素的 `onMouseEnter/onMouseLeave`、以及不再使用的 `VolumeX`、`Trash2` 引入（`Volume2` 仍被「帮我读」使用，保留）。
   - 按钮之间不用任何分隔符号（不用「·」也不用竖线），靠 `gap-3` 间距。
4. 入场动画：根元素的 `msg-in-right` / `msg-in-left` 只在 `!message.id.startsWith("db-")` 时加上。
5. 分身名一行：title 改为 `` `${agentName}（AI 分身）` ``；「由你的模型回复」前的 ` · ` 改为细竖线：外层 div 加 `flex items-center gap-2`，中间插入 `<span aria-hidden="true" className="h-3 border-l border-[var(--rule2)]" />`（与 `page.tsx:2493` 页头「AI 分身｜仅你可见」同一写法），后面 `<span title={message.replyModelLabel}>由你的模型回复</span>`。
6. `page.tsx`：
   - 新增 `const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);`。
   - 新增 `handleSpeakMessage = useCallback((id: string, text: string) => { … })`，顺序固定：`stopHandsFreeRecording({ discard: true })` → `clearTtsQueue()` → `primeTtsAudio()` → `ttsStoppedSessionRef.current = null` → `ttsSessionRef.current += 1` → `if (!chatAbortRef.current) streamDoneRef.current = true` → `const chunks = splitTtsChunks(stripMessageMarkdown(text)).map(normalizeForTTS).filter(Boolean)` → 若为空直接返回 → `ttsQueueRef.current.push(...chunks)` → `setSpeakingMessageId(id)` → `playNextInQueue()`。**不调用 `setVoiceOn`**（单条朗读不应打开之后回复的自动朗读）。
   - `clearTtsQueue` 函数体末尾加 `setSpeakingMessageId(null);`；`playNextInQueue` 在队列为空的分支（`:1302` `if (!next) {` 内、`return` 之前）加 `setSpeakingMessageId(null);`。
   - `handleDeleteMessage` 开头加确认：`if (!(await confirm({ body: "删除这条消息？此操作不可恢复。", confirmLabel: "删除", danger: true }))) return;`。
   - 渲染 `<ChatBubble>`（`:2576` 起）时追加 `onSpeak={handleSpeakMessage} onStopSpeak={stopTtsByUser} speaking={speakingMessageId === msg.id} speakDisabled={isLoading}`；其余 props 不变。
   - `page.tsx:217`、`:2420`、`:2440` 去掉 `font-semibold`（不换成别的字重类）。

### T4 焦点（`globals.css`）

在 `@layer base { … }`（`:299–308`）内、`* { … }` 之后追加：

```css
:where(a[href], button, summary, [role="button"], [role="tab"], [role="option"], [role="radio"], [role="switch"], [role="menuitem"], [tabindex]:not([tabindex="-1"])):focus-visible { outline:1px solid var(--ink); outline-offset:2px; }
```

放在 base 层是为了让组件里显式写的 `outline-none` / `focus-visible:…` 工具类和 `.btn/.chip` 的组件层规则仍然优先。§2.4 那 10 处 `outline-none` 本单不动（容器是 `tabIndex=-1` 的程序焦点；文本框靠光标，另议）。

### T5 粗体与中点

- 粗体：§2.5 的 3 处 `font-semibold` 去掉（T3-6 已含）；`AgentExchangeWorkspace.tsx:222` 两个 `<b className="readout">` 改为 `<b className="readout font-normal">`。
- 中点：按 §2.6 表格逐项替换（第 2 项见 T3-5），表外的一律不动。

### T6 确认框样式（`globals.css`）

在 `@layer components` 里 `.image-preview-dialog` 规则之后追加：

```css
.confirm-dialog { background:var(--hi); color:var(--ink); border:1px solid var(--carve); box-shadow:inset 0 0 0 1px var(--rim),inset 0 1px 0 var(--lip),inset 0 -1px 0 var(--lipdk),0 1px 2px var(--drop),0 26px 48px -34px var(--drop); }
.confirm-dialog::backdrop { background:rgba(31,41,38,.18); }
.dark .confirm-dialog::backdrop { background:rgba(0,0,0,.45); }
```

### T7 新测试 `backend/tests/test_component_language.py`

离线、不依赖 git 历史、不读仓库外文件。需要 node + typescript 的用例照 `test_claude_agent_frontend.py:136–155` 的 `require_rendering_dependencies` 写法探测，缺失时 `pytest.skip`。至少覆盖：

1. **原生弹窗清零**：对 `frontend/app`、`frontend/components`、`frontend/lib` 下所有 `.ts/.tsx`，正则 `(^|[^.A-Za-z_])(window\.)?(confirm|alert)\(\s*[\`"']` 零命中；且先断言扫描到的文件数 ≥ 100（防空集）。
2. **12 处都换上了**：§2.3 表里 12 段正文（取每段里不含模板变量的最长一截，如「的所有聊天记录？此操作不可恢复。」）各自仍在对应文件里恰好出现 1 次；对应文件含 `useConfirm()`（需要提示的含 `useNotice()`）；`NovelWorkbench.tsx` 仍含 `confirm(`。
3. **确认框组件契约**：`ConfirmDialog.tsx` 导出 `ConfirmProvider`、`useConfirm`、`useNotice`；含 `showModal(`、`role="alertdialog"` 或 `"alertdialog"`、`confirm-dialog`、`ConfirmProvider missing`；`layout.tsx` 含 `<ConfirmProvider>` 且 `<LensDefs />` 在其之前、`<PwaRegister />` 在其之后。
4. **消息行**：`ChatBubble.tsx` 不含 `setMuted`、`setHovered`、`onMouseEnter`、`VolumeX`、`Trash2`、`"播放语音"`、`"静音"`；含 `onSpeak?: (id: string, text: string) => void;`、`speaking?: boolean;`、`speakDisabled?: boolean;`、`"朗读"`、`"停止"`、`"复制"`、`"已复制"`、`"复制失败"`、`"删除"`、`stripMessageMarkdown(`、`navigator.clipboard`；`msg-in-` 只出现在一个以 `startsWith("db-")` 为条件的表达式里。
5. **朗读链路**：`page.tsx` 的 `handleSpeakMessage` 函数体（从 `const handleSpeakMessage` 到对应的 `}, [`）里 `primeTtsAudio()` 出现在任何 `await` / `setTimeout` / `.then(` 之前且函数体内没有 `await`；不含 `setVoiceOn`；含 `splitTtsChunks(`、`setSpeakingMessageId(id)`；`clearTtsQueue` 函数体含 `setSpeakingMessageId(null)`；`<ChatBubble` 那段 JSX 含 `speaking={speakingMessageId === msg.id}` 与 `speakDisabled={isLoading}`。
6. **`splitTtsChunks` 行为**（node + typescript 转译后执行，缺依赖则 skip）：空串与全空白 → `[]`；`"第一句。第二句！"` → 1 段；600 个「字」无标点 → 3 段且每段 ≤250；`"版本 4.5 发布。下一句"` 不在 `4.` 处切；把 30 句 20 字的句子拼起来，所有段 ≤250 且拼回去（去空白）等于原文去空白。
7. **焦点**：`globals.css` 的 `@layer base` 块（用括号配对取块）含 `:focus-visible` 且含 `outline:1px solid var(--ink)`。
8. **粗体与中点**：`page.tsx` 不含 `font-semibold`；`AgentExchangeWorkspace.tsx` 不含 `<b className="readout">`（无 `font-normal` 的写法）；§2.6 表 8 处的新文案各在对应文件出现，旧写法（`"更新中 · "`、`标签 · 最多 5`、`.join(" · ")`、`Chloe AI 助理 · 内测版`、`"我的 AI 分身 · 发起方"`、`"对方 AI 分身 · 受邀方"`、`· AI 分身\``、` · 由你的模型回复`）不再出现；`"平台官方 AI · 无真人用户"` 仍恰好出现 1 次。

### T8 报告 `03-report.md`

见 §7。

## 5. 不允许的做法

- 把 `primeTtsAudio()` 挪到 `await`、`setTimeout`、`then` 之后；单条朗读里调用 `setVoiceOn`。
- 用 `window.confirm = …` 之类的全局替换来「清零」原生弹窗；改动 12 段正文。
- 改 `ChatCard`、三个天气函数、`{/* 文字气泡` 之后的条件表达式、「帮我读 / 不用」按钮。
- 用 `opacity-0 group-hover:opacity-100` 之类的悬停显隐来实现删除按钮。
- 在消息行按钮之间放中点或竖线；新写任何带「·」的界面文案。
- 任何既有测试改动；任何白名单外文件改动；任何布局 / 间距改动（消息行按钮本身除外）。

## 6. 验收标准（Claude 逐条复跑，以 Claude 结果为准）

在仓库根执行（第 1–7 条你必须自己跑绿并写进报告）：

1. `cd frontend && npx tsc --noEmit` → 0。
2. `cd frontend && npm run lint` → 0 errors，warnings ≤ 25。
3. `cd frontend && npm run build` → 0。
4. `cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py tests/test_component_language.py -p no:cacheprovider` → 全部通过，总数 ≥ 499 + 8（既有 499 条一条不少；`test_novel_p2_frontend.py::test_workbench_polls_only_running_books_and_pauses_on_visibility` 必须仍绿）。
5. 结构判据（括号内为 HEAD 基线）：
   - `grep -rnE '(^|[^.A-Za-z_])(window\.)?(confirm|alert)\((\`|")' frontend/app frontend/components frontend/lib --include='*.tsx' --include='*.ts' | wc -l` = 0（12）。
   - `grep -c 'useConfirm()' frontend/app/settings/page.tsx frontend/app/page.tsx frontend/components/LocalWatchSection.tsx frontend/components/AgentMemoryPanel.tsx frontend/components/ChatModelSection.tsx frontend/components/novel/NovelWorkbench.tsx` 每个文件 ≥ 1；`grep -c 'useNotice()' frontend/app/settings/page.tsx frontend/app/page.tsx` 每个 ≥ 1。
   - `grep -c '<ConfirmProvider>' frontend/app/layout.tsx` = 1。
   - `grep -c 'font-semibold' frontend/app/page.tsx` = 0（3）。
   - `grep -cE 'setMuted|setHovered|onMouseEnter|VolumeX|Trash2' frontend/components/ChatBubble.tsx` = 0（≥5）。
   - `grep -c 'setVoiceOn' frontend/app/page.tsx` 与 HEAD 相同（单条朗读不新增调用）。
   - `grep -rho 'aria-label=' frontend/app frontend/components --include='*.tsx' | wc -l` ≥ 118。
   - `grep -c '平台官方 AI · 无真人用户' frontend/components/AgentExchangeWorkspace.tsx` = 1（1）。
6. 改动集合：`git status --porcelain` 只出现 §3.1 白名单路径与本规格目录；`git diff --stat` 不含 `package.json`、`package-lock.json`、`next.config.ts`、`backend/`（新测试除外）、`components/ui/`、`components/studio/`、`SongProjectCard.tsx`。
7. ChatCard 未动：`diff <(git show HEAD:frontend/components/ChatBubble.tsx | awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p') <(awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p' frontend/components/ChatBubble.tsx)` 输出为空。
8. 真实浏览器（Claude 在隔离实例量，昼夜、1440×900 与 390×844）：
   - 消息行：样例对话里每条分身消息下可见（不悬停）「朗读」「复制」「删除」，每条用户消息可见「复制」「删除」；元信息行里没有 `svg`；手机上三个按钮高度 ≥ 40。
   - 朗读：点「朗读」后同一按钮文字变「停止」、发出换票请求；点「停止」或播放结束后变回「朗读」；全局「朗读」开关的 `aria-pressed` 前后都为 `false`。
   - 复制：授予剪贴板权限，点分身那条 Markdown 消息的「复制」→ 文字变「已复制」，剪贴板内容不含 `**`、`## `、`- ` 开头的行。
   - 删除：点「删除」→ 出现 `.confirm-dialog[open]`，正文「删除这条消息？此操作不可恢复。」，焦点在「取消」；按 Esc → 对话框关闭、消息仍在、没有 DELETE 请求；再点「删除」→「删除」按钮 → 消息消失、发出 DELETE 请求。
   - 全程监听 `page.on("dialog")`，原生弹窗触发次数 = 0（含设置页「清空」→ 取消、删除对话 → 取消、上传非图片文件 → 出现提示框「只能上传图片」→ 知道了）。
   - 入场动画：加载样例对话后 DOM 里没有 `.msg-in-left` / `.msg-in-right`；发一条消息后只有新的那条带 `.msg-in-right`。
   - 焦点：1440 下在 `/` 用 Tab 走 30 步，每个获得焦点且不是 `input/textarea` 的元素 `outline-style` 不为 `none` 且 `outline-width ≥ 1px`（或有非 `none` 的 `box-shadow`）。
   - 粗体：`/`、`/settings`、`/agents`、`/agents/me`、`/plaza`、`/profile`、`/history`、`/novels` 各页（含打开的确认框）里，没有任何自带文字的元素 `font-weight ≥ 600`。
   - 截图：确认框昼 / 夜各一张，与影青釉一致（瓷片底、朱字危险操作、无粗体）。

## 7. 交付：变更总结（写进 `03-report.md`）

1. 修改 / 新增文件清单；2. 实现了什么；3. 与 T1–T8 逐项对应；4. §6 第 1–7 条实际结果（第 4 条写 passed 数，第 5 条逐条写实际值）；5. 未完成或需人工确认的地方、主动偏离及理由，以及 §6 第 8 条每项对应的代码依据。

## 8. 何时停下来问

只在影响「实现什么」时停：不改 §3.2 的保留项就做不到某项任务；某处原生弹窗的调用上下文无法在 `await` 后安全地重新检查守卫；你实测到的事实与本规格不符（实测优先，先停下来说明）。只影响「怎么实现 / 怎么验证」的自行决定并写进报告。任何情况下不回滚已完成的工作。

## 9. 执行方式

用工作流（`workflow` 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好：

- agent A：`ConfirmDialog.tsx`（新）+ `layout.tsx` + `globals.css`（T1、T4、T6）；
- agent B：`page.tsx` + `lib/ttsChunks.ts`（新）（T2 的 #4–7、T3-1、T3-6、T5 粗体）；
- agent C：`ChatBubble.tsx`（T3-2 至 T3-5）；
- agent D：`settings/page.tsx`、`LocalWatchSection.tsx`、`AgentMemoryPanel.tsx`、`ChatModelSection.tsx`、`novel/NovelWorkbench.tsx`（T2 的 #1–3、#8–12）；
- agent E：`plaza/page.tsx`、`profile/page.tsx`、`AgentExchangeWorkspace.tsx`（T5 其余）；
- agent F：`backend/tests/test_component_language.py`（T7）——等 A–E 完成后再跑一次确认全绿。

接口以本规格 T1、T3-1、T3-2 写死的名字为准（各 agent 互相看不到对方的代码）。每个 agent 的任务说明自包含，并写明不得调用 subagent / subagent_fork / workflow。主代理只做拆分、派发、汇总、白名单检查、门禁（§6 第 1–7 条）、报告；报告开头列拆分表，如实列出全部派出过的 agent。
