# 01 前端结构地图（改造前现状，HEAD 586d86a）

> 由 6 个只读调研代理并行通读产出，供实现方定位代码。行号以 586d86a 为准。

## chat-shell：Fiona/Chloe 前端对话主页 frontend/app/page.tsx（HEAD 586d86a，工作区干净，2474 行，sha1 574f1505db53b8d5cb728f4286122db90170d3bd），以及它直接耦合的 components/Sidebar.tsx、ConversationPicker.tsx、Signal.tsx、ChatScrollArea.tsx、lib/useTheme.ts、app/layout.tsx、app/globals.css
### 根骨架与分栏
- **位置**：page.tsx:2023-2025（根）、2100（中栏 flex 行）、2111（data-chat-panel）、2323-2326、2472-2474；背景 globals.css:168-178
- **结构**：div.flex.flex-col.h-dvh.overflow-hidden > div.flex.flex-1.min-h-0.relative(2025) > [Sidebar(2027-2038) | 历史抽屉+背板(2041-2098，absolute) | div.flex.flex-1.min-w-0.min-h-0(2100) > [ConversationPicker 桌面列(2101) | 手机对话框+背板(2103-2109) | div.relative.flex-1.min-w-0[data-chat-panel](2111) > header(absolute top) + 消息容器(absolute inset-0，用内边距让位) + footer(absolute bottom)]]。四个右侧抽屉和抽屉外背板挂在根 div 下、flex 行之外（2328-2470，全部 fixed）。桌面宽度分配：Sidebar 56px(w-14) + 对话目录 260px + 对话区 flex-1。手机(<768)：Sidebar 的 aside 隐藏，换成 fixed 底部 tab 栏；对话目录列隐藏。
- **样式**：根本身没有背景类；底色来自 body：三层 radial-gradient(--spot-a/-b/-c) + var(--background)，background-attachment: fixed。page.tsx 用 Tailwind 的 max-md: / md:hidden，不用自定义的 mobile: 变体，也不读 data-shell。
- **行为（必须保留）**：无（纯布局）。
- **状态**：—
- **手机端**：h-dvh；所有贴底偏移都手写成 calc(56px+env(safe-area-inset-bottom))，让出 tab 栏。
- **改造风险**：对话区是叠在 data-chat-panel 里的三个 absolute 层，消息容器靠 pt-16 / pb-[var(--composer-height)] 让出位置，消息不会滚到玻璃页头/输入区下面，所以玻璃背后只有 body 背景。复刻稿如果要内容从玻璃下面流过，就得改结构，换皮做不到。

### 主导航 Sidebar（组件耦合）
- **位置**：page.tsx:2026-2038 调用、305-322（closeMobilePanelsFromNavigation / toggleDrawer / closeDrawer / focusVisibleDrawerTrigger）；components/Sidebar.tsx:13-19 navItems、54-80 余额、84-180 桌面 aside、181-221 手机 nav
- **结构**：桌面：aside.glass.flex.min-h-0.w-14.flex-col.items-center.gap-1.border-r.bg-sidebar.py-3.max-md:hidden，从上到下是 Logo（双圆 SVG，amber-ink，86-91）→ nav 竖排五项（对话/分身/广场/世界/设置，各 h-12 w-12，图标 20 + 10px 文字）→ 底部草莓余额（🍓 + b.readout）→ 主题按钮（Sun/Moon，h-10 w-12）。手机：nav[aria-label=主导航].glass.fixed.inset-x-0.bottom-0.z-[70].h-[calc(56px+env(safe-area-inset-bottom))].border-t.md:hidden，五项 flex-1 h-14 等分。
- **样式**：.glass、bg-sidebar(--sidebar)、border-border/var(--glass-border)、激活态 text-[color:var(--amber-ink)]、非激活 text-muted-foreground hover:bg-secondary hover:text-foreground、rounded-[6px]、图标 strokeWidth 激活 2.2 / 否则 1.8。余额颜色写在 inline style：<30 用 var(--rec)，<100 用 var(--amber-ink)，否则 var(--foreground)。
- **行为（必须保留）**：主页把五个回调都传进去，所以五项都渲染成 button（不走路由）：对话=closeDrawer，其余=toggleDrawer('agent'|'exchange'|'plaza'|'settings')，抽屉互斥。active 先看抽屉状态，「对话」只在 pathname=/ 且没有抽屉打开时高亮。aria-expanded / aria-controls：桌面只有 agent-drawer、exchange-drawer 两项有（Sidebar 120-121），手机四项都有（202-206、216）。导航点击会关掉手机对话框，手机上还会关历史抽屉（305-310）。余额：挂载时 GET /strawberry，之后每 60s 轮询，并监听 storage 和 fiona-user-changed；通过 onBalanceChange 回传 page 的 setStrawberryBalance(2037)，再用 updateBalance 写 localStorage。
- **状态**：余额为 null 时显示「…」；激活态 / 非激活态。
- **手机端**：底部 tab 栏 z-[70]，始终可见可点，用来切换或关闭抽屉；桌面 aside 隐藏。
- **改造风险**：focusVisibleDrawerTrigger(319-322) 按 button[aria-controls="<id>"] 且 getClientRects 非空来找焦点归还目标；新导航去掉 aria-controls 或改成不可见元素，Esc 关抽屉后焦点就回不去。导航宽 56px 在 page.tsx 写死了 7 处：left-14（2043、2097、2466）和 calc(100vw - 56px)（2343、2374、2396、2433），竖排书签宽度一变要同步改。发消息后不刷新余额（只有 60s 轮询）。主题按钮没有 type 和 aria-label。

### 对话目录（桌面常驻列 / 手机对话框）
- **位置**：page.tsx:297、300-302（状态与 ref）、334-371（手机焦点陷阱）、1979-2002（conversationPickerProps）、2101（桌面列）、2103-2109（手机背板+对话框）、2117-2120（手机触发按钮）；components/ConversationPicker.tsx:41-107
- **结构**：ConversationPicker = aside.glass.flex.h-full.w-[260px].shrink-0.flex-col.border-r[aria-label=对话列表]。头部 h-16 border-b pl-5 pr-3：h2「对话」+ Clock「当前对话记录」+ Plus「新对话」（btn btn-quiet w-[34px]）。中间 ul[role=listbox].flex-1.overflow-y-auto.p-2，每项 li[role=option][aria-selected] 内含标题 button、span.readout 相对时间、Trash2 删除（hover 才显）。下方依次是锁定提示 / 空态 / 错误，底栏「对话仅你可见」+「完整历史」，最后是只在手机出现的主题按钮栏（md:hidden）。桌面：作为对话区左侧常驻列（className=max-md:hidden）。手机：页头 PanelLeft 按钮打开 div#conversation-picker-dialog[role=dialog][aria-modal=true][aria-label=对话列表][tabIndex=-1].fixed.left-0.top-0.bottom-[calc(56px+safe)].z-[62].w-[min(85vw,320px)].animate-in.slide-in-from-left.duration-300.md:hidden；背板 fixed inset-x-0 z-[61] bg-black/20 backdrop-blur-sm，点击关闭，aria-hidden。
- **样式**：.glass、borderColor var(--glass-border)、btn btn-quiet、.readout、aria-selected:bg-secondary、hover:bg-secondary、rounded-[6px]、text-[13px]、删除按钮 hover:text-[color:var(--rec)]、错误 text-[color:var(--rec)]；背板硬编码 bg-black/20。
- **行为（必须保留）**：onSelect / onCreate 先关对话框，再调 handleSelectConversation(1426-1430) / handleNewChat(1419-1424)；conversationLocked 或 conversationLoading 时直接返回；切换前 resetConversationPresentation(1400-1417) 清空 TTS、ASR、草稿、待发图、参考图、imageMode 和比例。onDelete：confirm「删除这段对话及其中的消息？…」后 deleteConversation(1432-1437)。onRetry：reloadConversations。onHistory：手机上对话框开着时，关对话框、打开历史抽屉、焦点移到历史关闭按钮；其他情况 toggle showHistory(1990-2000)。onFullHistory：window.open('/history?user=…', '_blank', 'noopener,noreferrer')。手机焦点陷阱：打开时聚焦第一个可用 button，Tab / Shift+Tab 循环，Esc 关闭；视口变到 ≥768 自动关闭且不还焦点；关闭时焦点还给 PanelLeft（restoreConversationFocusRef）。PanelLeft 按钮：aria-expanded，只在打开时设 aria-controls=conversation-picker-dialog。
- **状态**：加载：li[role=status]「正在加载对话…」。锁定：「分身回复或语音进行中，结束后可以切换对话。」。空：「还没有对话。点「新对话」，开始和自己的分身交流。」。错误：role=alert + 「重试加载」。新对话按钮在 loading、locked 或没有 agent 时禁用；标题和删除在 loading 或 locked 时禁用（disabled:opacity-40）。
- **手机端**：只能从页头 PanelLeft（btn btn-quiet h-10 w-10）打开；删除按钮常显，40×40；头部按钮 40×40；底部有「主题」按钮(h-10)。
- **改造风险**：桌面目录头部 h-16 的 border-b 和对话区页头 h-16 的底边线是对齐的，改页头高度两边要一起改。conversationLocked 包含 handsFree(1394)，免提开着时不能切换、新建或删除对话。listbox/option 里嵌 button 是现有结构。

### 当前对话记录抽屉（history）
- **位置**：page.tsx:2040-2098；焦点与 Esc：372-389；分组 groupByDate 251-266；collapsed 状态 289
- **结构**：showHistory 为真时渲染 div.glass.absolute.left-14.top-0.bottom-0.w-64.z-50.flex.flex-col.animate-in.slide-in-from-left.duration-300（inline：borderRight 1px var(--glass-border)，boxShadow 8px 0 32px rgba(0,0,0,0.28)）。头部 px-4 py-3 border-b：Clock +「当前对话记录」+「删除」按钮（Trash2，删当前对话）+ X 关闭（aria-label「关闭当前对话记录」，ref historyCloseButtonRef）。主体 flex-1 overflow-y-auto py-3 px-3：hasMoreMessages 提示 → 按日期倒序分组，每组一个折叠按钮（ChevronDown/Right + 日期 + 「n 条」）→ 展开时 div.ml-5.border-l.pl-3 里列条目（角色名「我」或分身名 / zh-CN 时间 / 内容 line-clamp-2）。背板(2096-2098)：absolute left-14 top-0 bottom-0 right-0 z-40 bg-black/20 backdrop-blur-sm，点击关闭。
- **样式**：.glass、border-border、hover:bg-secondary、rounded-xl、text-[11px]/[10px]/[9px]、text-muted-foreground/50、text-foreground/70、删除 hover:text-destructive disabled:opacity-40；硬编码 rgba 阴影和 bg-black/20。
- **行为（必须保留）**：按日期键切换 collapsed。删除按钮在没有当前对话、locked 或 loading 时禁用。只有从手机对话框进入时才聚焦关闭按钮，Esc 只在 <768 时生效，关闭后焦点还给 PanelLeft。
- **状态**：hasMoreMessages：「当前显示最近 500 条消息，完整记录可在历史页查看。」；messages 为空时列表为空，没有空态文案。
- **手机端**：max-md:left-0，bottom 停在 tab 栏上沿，宽 w-[min(85vw,320px)]；关闭按钮 40×40。
- **改造风险**：不是 dialog 角色，桌面上没有焦点管理；left-14、阴影色、背板色都是硬编码。

### 页头（分身头像/名字/Signal/状态/朗读/免提/草莓余额）
- **位置**：page.tsx:2112-2172；signalMode 1978；components/Signal.tsx:9-98；globals.css:233-241（.signal / .state-dot）、243-264（.chip）
- **结构**：header.glass.absolute.inset-x-0.top-0.z-[2].grid.h-16.grid-cols-[auto_minmax(120px,1fr)_auto].items-center.gap-6.border-b.px-6（borderColor var(--glass-border)），三列。① 左(2116-2126)：[手机才有的 PanelLeft 按钮] + 头像 span.grid.h-8.w-8.place-items-center.rounded-[6px].bg-secondary.text-base[aria-hidden]，内容是 agent.avatar_emoji 或「✨」+ 名字 div.text-sm.font-medium（agent.display_name 或「我的分身」）+ 副行 div.flex.gap-2.text-xs.text-muted-foreground「AI 分身」「仅你可见」（max-md:hidden）。② 中：<Signal mode={signalMode}/>，即 svg.signal，viewBox 0 0 1000 40，preserveAspectRatio=none，aria-hidden，里面一条 path（140 点）和一个 r=3 的 circle。③ 右(2128-2171)：span.state-dot（加 state-dot-listening / state-dot-speaking）+ 文案「正在听 / 正在说 / 待命」（max-md:hidden）；朗读 chip（Volume2 或 VolumeX 13px +「朗读」）；免提 chip（AudioLines 图标只在手机显示，「免提」文字只在桌面显示）；草莓余额 span.hidden.max-md:inline-flex（🍓 + b.readout）。
- **样式**：.glass；.signal：path stroke var(--amber-ink)，宽 1.5，non-scaling-stroke，opacity .9；circle fill amber-ink，高 40px。.state-dot 6px 圆：idle 用 var(--dim)，listening 用 var(--rec)，speaking 用 var(--primary)。.chip（28px 高）/.chip-on（amber-ink 边框和字色 + var(--accent) 底）；.readout（mono 12px tabular-nums）；bg-secondary；余额 inline color var(--rec)/var(--amber-ink)/var(--foreground)。
- **行为（必须保留）**：signalMode：recording 或 inlineRecording 时为 listening，否则 isLoading 时为 speaking，否则 idle(1978)。免提自动录音中、TTS 朗读播放中都不算 listening/speaking。Signal 用 rAF 常驻绘制：level 按 dt*6 缓动到 0 / 0.5 / 0.9，三条正弦叠加再乘 sin 包络；idle 且 level<0.02 时有个小圆点从左往右扫；每次挂载随机一个相位。prefers-reduced-motion 时只画直线、隐藏圆点、不启动 rAF。朗读按钮(2133-2145)：打开时置 ttsStoppedSessionRef=null，在点击里同步调 primeTtsAudio()，再 setVoiceOn(true)；关闭时 stopTtsByUser() + setVoiceOn(false)。aria-label="朗读"，没有 aria-pressed。免提按钮(2146-2164)：切换 handsFree；打开时清 micNotice、prime，并强制 voiceOn=true；conversationLoading 或没有当前对话时禁用；aria-label="免提"，title「免提：分身说完自动开麦，你停顿 1.5 秒后自动发」。
- **状态**：agent 未加载时回退到「✨」和「我的分身」；状态三态；朗读和免提开启时 chip-on；免提可禁用；余额为 null 显示「…」，<30 红，<100 琥珀。
- **手机端**：h-20，grid-cols-[minmax(0,1fr)_auto]，grid-rows-[56px_24px]，gap-0，px-3。第 1 行是左块 + 右块(col-start-2 row-start-1)；Signal 跨两列放第 2 行，h-6。名字 truncate；状态只剩圆点；朗读/免提变成 36×36 图标按钮(h-9 w-9 px-0 justify-center)；草莓余额只在手机页头显示，桌面放在 Sidebar。
- **改造风险**：Signal 的形态（一条线 + 圆点 + 颜色）全在 Signal.tsx 和 globals.css 的 .signal 里，换成「远山」时必须保留 mode 三态输入、reduced-motion 分支和 aria-hidden。消息容器的 pt-16 / max-md:pt-20(2173) 和页头高度 h-16 / h-20 绑死。朗读/免提的 onClick 必须在用户手势里同步调用 prime，不能包进异步逻辑或会延后 click 的容器。

### 消息列表与滚动
- **位置**：page.tsx:2173-2189；components/ChatScrollArea.tsx:20-143；ChatBubble 调用 2181-2186（ChatBubble.tsx 160-331 为气泡样式）
- **结构**：div.absolute.inset-0.flex.flex-col.pt-16.pb-[var(--composer-height)]（--composer-height 由 composerHeight state 写在 inline style）> ChatScrollArea：div.relative.flex.min-h-0.flex-1.flex-col[data-chat-scroll-area] > viewport div[role=region][aria-label=聊天消息][tabIndex=0][data-chat-scroll-viewport].min-h-0.flex-1.overflow-y-auto（overflowAnchor:none）> content div.space-y-4.px-6.py-4.max-md:px-4[data-chat-scroll-content] > page 自己的 div.flex.w-full.max-w-[760px].flex-col.gap-[22px] > [hasMoreMessages 提示 | 空态 | ChatBubble×n]。这层 760 容器没有 mx-auto，宽屏下消息列靠左，而输入区是 mx-auto 居中。「回到最新」按钮：absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border-border bg-background/95 shadow-sm（ArrowDown +「回到最新」）。
- **样式**：page 这一段只有 text-xs text-muted-foreground。气泡里用的是 .bubble-user / .bubble-ai / .typing-cursor / .msg-in-left / .msg-in-right / .glass-card（天气卡、网页卡）/ .readout / btn btn-quiet / amber-ink 小方点 / LoaderCircle animate-spin。
- **行为（必须保留）**：resetKey=`${username}:${currentConversation?.id ?? 'loading'}`，变化时 useLayoutEffect 滚到底。跟随底部：ResizeObserver 同时观察 content 和 viewport，用 rAF 直接设 scrollTop（不用 smooth）；wheel、touch、键盘（ArrowUp/PageUp/Home/Shift+Space）表现出向上意图时停止跟随；被动 clamp 不算向上。handleSend 一开始就 scrollToLatest(1528)。ChatBubble 的 props：key=`${username}-${convId}-${msg.id}`、agentName、agentAvatar、onDelete（isLoading 时传 undefined）、onConfirmTts / onDeclineTts（「帮我读 / 不用」，1366-1387）、onRetryImage → handleSend(prompt, request)、onEditImage → handleSelectReferenceImage、selectedReferenceImagePaths、imageRetryDisabled（locked、loading、无对话、有待发图、正在读图或读参考图）。
- **状态**：hasMoreMessages：「当前显示最近 500 条消息；更早记录可在历史页查看。」。空态 p[role=status] 四选一：「正在加载对话…」/「对话加载失败，请在上方重试。」/「和 {name} 开始新的交流。」/「点击上方“新对话”，开始和自己的分身交流。」。typing 占位消息 id="typing"，isTyping，可带 generationStatus。流式中是空的 assistant 气泡（generationStatus「正在生成图片… / 正在修改图片… / 正在上传参考图…」）。
- **手机端**：pt-20；底部 pb=calc(var(--composer-height)+56px+env(safe-area-inset-bottom))；content px-4。
- **改造风险**：消息列不居中是现状，复刻稿要居中得加 mx-auto（属于结构变化）。空态写的是「点击上方“新对话”」，手机上实际入口在页头 PanelLeft → 对话框，文案对不上。

### 输入区外壳与状态行（朗读被拦/限速/麦克风提示）
- **位置**：page.tsx:2190-2211；测高 480-488（composerRef / ResizeObserver）、423（初始 172）；倒计时 456-460；resumeBlockedTts 1192-1222；stopTtsByUser 1185-1190
- **结构**：footer.glass.absolute.inset-x-0.bottom-0.z-[2].border-t.px-8.pb-4.pt-3（ref composerRef，borderColor var(--glass-border)）> div[data-chat-composer].mx-auto.max-w-[760px] > div[role=status][aria-live=polite]，里面有三条可选行，每行 div.mb-2.flex.min-w-0.items-center.gap-1.text-xs。① ttsPlaybackBlocked：「浏览器拦下了自动朗读」+ 按钮「点此播放」(Volume2，btn btn-quiet h-7 px-2.5 text-xs) + 按钮「不听了」。② ttsWaitUntil!==null：span[aria-hidden]「朗读限速中，N 秒后接着读」+ span.sr-only「朗读限速中，稍后自动接着读」+「不听了」。③ micNotice：文本 +「知道了」。
- **样式**：.glass、btn btn-quiet、text-muted-foreground。
- **行为（必须保留）**：ResizeObserver 量 footer 实际高度，写进 composerHeight，再作为 --composer-height 给消息容器做底部内边距，所以 footer 里新增任何行都会自动推高消息区底边。「点此播放」必须在同一个点击里同步执行 primeTtsAudio + audio.play()，不能重新取票。倒计时每秒刷新。「不听了」= stopTtsByUser：清队列，并把本轮剩余分句标为不朗读；如果流已结束且免提开着，补一次开麦。
- **状态**：三行可以同时出现，也可以都不出现。
- **手机端**：max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]，max-md:px-3，max-md:pb-3；状态行按钮 max-md:h-9。
- **改造风险**：footer 就是测高源，把它外面再包一层，或从 absolute 改成文档流，都会破坏 --composer-height。

### 参考图托盘与上传错误
- **位置**：page.tsx:2212-2232；选择/排序/移除 1439-1483；本地读取 1876-1927；GeneratedImage.tsx:134-178
- **结构**：referenceUploadError 有值时：p[role=alert].mb-2.text-xs.text-destructive。hasReferenceImages 时：div.mb-2.rounded-[10px].bg-secondary/50.p-2 > div.flex.max-h-[144px].items-start.gap-2.overflow-auto.pb-1[aria-label=已选参考图，按编号顺序发送] > 每张 div.w-[120px].shrink-0：GeneratedImage variant="reference" referenceIndex={n} compact localPreview，下面一行操作 div.mt-1.flex.justify-between：前移（ArrowLeft，aria-label「将图N前移」）、后移（ArrowRight，「将图N后移」）、移除（X，ml-auto，「移除参考图N」）。托盘底部是提示 p.mt-1.text-[10px]，三种：已满 3 张 / 2 张 / 其他。
- **样式**：bg-secondary/50、rounded-[10px]、按钮 rounded p-1 hover:bg-secondary hover:text-foreground、移除 hover:bg-destructive/10 hover:text-destructive、disabled:opacity-30。GeneratedImage 里是 .glass-card、btn btn-quiet，以及原生 <dialog> 预览（.glass，backdrop:bg-black/75）。
- **行为（必须保留）**：最多 3 张。来源一：本地上传，只收 PNG/JPEG/WebP，每张 ≤5MB，readLocalReferenceImage 读取后去重。来源二：已生成图上的「以此图修改」（handleSelectReferenceImage），会校验这张图确实是当前会话 assistant 消息里的图。选择按 owner+conversationId 绑定，切换对话后不再显示。每次改动后 requestAnimationFrame(focusChatInput)（因为预览 dialog 可能刚关）。发送后清空，重试时不清。
- **状态**：按钮在 conversationLocked、conversationLoading 或 isReadingReferences 时禁用；第一张禁前移，最后一张禁后移。错误文案：「最多共3张参考图，当前还可添加N张，请重新选择。」「参考图仅支持 PNG、JPEG、WebP 格式。」「每张参考图需大于 0 字节且不超过 5MB。」「这些图片已加入参考，请选择其他图片。」以及读取异常的 message。
- **手机端**：操作按钮变成 40×40（max-md:grid h-10 w-10 p-0），行间距 gap-0、px-0。
- **改造风险**：托盘高度变化会触发 composerHeight 重算。GeneratedImage 的 reference 变体由别的组件负责，这里只决定排布。

### 输入框与待发送图片
- **位置**：page.tsx:2233-2250；handleKeyDown 1834-1840；handleInput 1842-1847；handlePickImage 1849-1874；textareaRef / focusChatInput 425-431
- **结构**：div.flex.flex-col.gap-2.rounded-[10px].border.px-3.5.py-2.5（inline background var(--fill)，borderColor var(--glass-border)），这一个框同时包着第一行（输入）和第二行（模式行 + 动作按钮，见下两段）。第一行 div.flex.items-end.gap-2：有 pendingImage 时先放 div.relative.inline-block.w-fit.pt-1，里面是 img（rounded-xl max-h-20 max-w-[120px] object-cover border-border，alt「待发送」）和右上角移除按钮（absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-background border，hover:bg-destructive hover:text-white，aria-label「移除待发送图片」）；然后是 textarea（rows=1，min-w-0 flex-1 resize-none bg-transparent text-sm py-1 leading-relaxed max-h-[80px] outline-none placeholder:text-muted-foreground）。
- **样式**：var(--fill)、var(--glass-border)、text-foreground、hover:text-white（白色硬编码）、border-border。
- **行为（必须保留）**：Enter 发送，Shift+Enter 换行；IME 组合期间不发送（onCompositionStart/End 写 isComposingRef）。输入时自动增高到 min(scrollHeight,120)px，但 class 里的 max-h-[80px] 实际把它封在 80px。手动发送后 style.height 重置为 auto（1536，语音/重试这类 textOverride 发送不清草稿）。placeholder 四种：有参考图「描述修改要求，可用图1、图2、图3指定各图用途…」/ 生图模式「描述想生成的画面、风格和细节…」/ 有待发图「说点什么…（可选）」/ 默认「说点什么…」。看图附件读成 dataURL，非图片或 >5MB 用 alert 提示。focusChatInput 只在分身/广场两个抽屉的 aria-hidden 不等于 "false" 时才聚焦。
- **状态**：textarea 在 conversationLoading 或没有当前对话时禁用。
- **手机端**：textarea max-md:text-base（16px，防 iOS 聚焦放大；globals.css:415-420 另有兜底）；移除按钮 40×40（max-md:-right-4）。
- **改造风险**：必须保留 textareaRef 和两个 composition 事件，新对话、工具事件、参考图选择、发送完成都会调 focusChatInput。

### 模式行：上传参考图 / 生成图片 / 修改图片 / 比例 / 生图模型
- **位置**：page.tsx:2251-2286；imageModelGroup 2006-2021；模型常量 70-81；偏好与可用性 407-411、508-523（读 localStorage）、525-550（GET /image-models）；请求体 1595-1603
- **结构**：div.flex.flex-wrap.items-center.justify-between.gap-2，左边 div.flex.flex-wrap.items-center.gap-2.text-[11px]：隐藏的 input[type=file][multiple][accept=image/png,image/jpeg,image/webp]；「上传参考图」chip（ImagePlus 12，有参考图时 chip-on）；读取中显示 span[role=status]「正在读取并检查参考图…」。后面三个分支互斥。A 有参考图：span.chip.chip-on「修改图片」(PencilLine) + span[role=status].text-[color:var(--amber-ink)]「参考图 n/3」+「尺寸跟随图1」+ imageModelGroup + 按钮「全部取消」(ml-auto，X 11)。B imageMode：span.chip.chip-on「生成图片」(Sparkles) + div[role=group][aria-label=图片比例]，里面三个 chip h-6 px-2（1:1 / 16:9 / 9:16，aria-pressed）+ imageModelGroup + 按钮「返回聊天」(ml-auto)。C 默认：「生成图片」chip 按钮（Sparkles）；有待发图时提示「先移除待发送图片，即可切换生成模式」；读图中显示 status「正在读取图片…」。imageModelGroup = div[role=group][aria-label=图片模型].flex.items-center.gap-1，按钮是 chip h-6 px-2 + aria-pressed，按钮文字用 shortLabel：「Qwen 3.0」「Seedream 5.0 Flash」；title 显示完整 label（Qwen Image 3.0 / Seedream 5.0 Flash），不可用时 title「管理员尚未配置此模型」。
- **样式**：.chip / .chip-on（默认 28px 高，这里被 h-6 改成 24px）、text-[color:var(--amber-ink)]、text-muted-foreground、hover:text-foreground、disabled:opacity-40。
- **行为（必须保留）**：模型列表：登录后 GET /image-models，按 FALLBACK 两项校验合并，失败就回退 FALLBACK。点选写 localStorage fiona_image_model（try/catch）。某模型不可用时，当前选择回落到默认，但保留用户偏好(409-411)。image_model 在 chat / image / image_edit 三种模式下都放进请求体。aspect_ratio 只在非 chat 模式提交：image 模式用所选比例，自然语言生图用 imageAspectRatioFromPrompt，修图不传（跟随图1）。选了参考图会 setImageMode(false)。
- **状态**：上传参考图禁用条件：locked、loading、无对话、有待发图、正在读图、正在读参考图、已满 3 张（title 三种）。比例和模型按钮在 isLoading 时禁用（模型还要求 available）。生成图片按钮禁用条件：有待发图、正在读图、正在读参考图、locked、loading、无对话（title 两种）。返回聊天在 isLoading 时禁用。全部取消在 locked、loading、isReadingReferences 时禁用。
- **手机端**：整行自动折行；所有 chip 和按钮 max-md:h-10（全部取消、返回聊天是 max-md:min-h-10）。
- **改造风险**：「修改图片」「生成图片」两个 chip-on 是 span，不可交互，但长得和按钮一样；改样式时不要把它们做成看起来能点，也不要改成 button。这一段是最近一单（2026-10-06 image-model-picker）的落点，规格写死了按钮写法照抄比例按钮、保留 max-md:h-10。

### 右侧动作按钮：看图附件 / 语音转文字 / 按住说话 / 发送
- **位置**：page.tsx:2287-2313；toggleInlineVoice 739-792；startNlsAsr / stopNlsAsr 671-734；recording 驱动 730-734；全局抬起兜底 652-665；handleSend 1485-1829
- **结构**：div.flex.items-center.gap-0.5.ml-auto.shrink-0，依次是：隐藏 input[type=file][accept=image/*]；看图附件 btn btn-quiet h-8 w-8 px-0（ImagePlus 14，只有 title，没有 aria-label）；语音转文字 btn btn-quiet h-8 w-8 px-0（Mic 14，aria-label「语音转文字」）；按住说话 btn btn-quiet h-8 px-2.5 text-xs（Mic 14 + span「按住说话」，aria-label「按住说话」）；发送 button.grid.h-8.w-8.place-items-center.rounded-[6px].bg-primary.text-primary-foreground.disabled:bg-secondary.disabled:text-[color:var(--dim)]（Send 14，aria-label 随模式变：「修改图片 / 生成图片 / 发送消息」，没有 type 属性）。
- **样式**：btn / btn-quiet；录音中两个麦克风按钮加 text-[color:var(--rec)] bg-[color:var(--rec-soft)]；发送键 bg-primary（琥珀 #F2A63A）/ text-primary-foreground，禁用时 bg-secondary + var(--dim)。
- **行为（必须保留）**：按住说话：onPointerDown 里 preventDefault、对 e.target 做 setPointerCapture、setRecording(true)；onPointerUp 里 release、asrSession+1、setRecording(false)；window 的 mouseup/touchend 兜底停止。recording 变 true 后启动 MediaRecorder(webm/opus)，停止后 POST /asr/recognize（base64），识别出的文字直接 handleSend，不放进输入框。没有键盘操作路径。语音转文字：点一下开始，再点一下停止，识别结果同样直接发送（739 行注释说放进输入框，但 779 行实际是 handleSendRef）；429 时写 micNotice；没有权限时提示「没有麦克风权限，请在浏览器里允许使用麦克风」或「麦克风用不了」。发送：handleSend 走 POST /chat，SSE 流式，mode 为 chat / image / image_edit；发送时停掉免提录音（丢弃）、清 TTS 队列、开新的 TTS session，回复按句切分入队朗读（首句碰逗号也切，单段最长 250 字）；结束后 refreshList()。
- **状态**：看图附件禁用：imageMode、有参考图、正在读图、正在读参考图、isLoading、loading、无对话（title 三种）。语音两个按钮禁用：loading、无对话、isLoading。发送禁用：isLoading、正在读图、正在读参考图、loading、无对话，或者既没文字也没待发图。录音态：红字 + 红底。
- **手机端**：全部 40×40（max-md:h-10 max-md:w-10）；按住说话只剩图标（文字 max-md:hidden，aria-label 保留）。
- **改造风险**：setPointerCapture 作用在 e.target 上，可能是里面的 svg 或 span；改按钮内部结构后要确认 pointerup 还能正确释放。发送键不属于 .btn 体系，是单独一串类。

### 识别提示与底部提示行
- **位置**：page.tsx:2316-2320；voiceText 来源 686-709
- **结构**：voiceText 有值时：p.mt-2.text-xs.text-muted-foreground。下面一行 div.mt-2.flex.items-center.justify-between.text-xs.text-muted-foreground：左边「Enter 发送，Shift + Enter 换行」（max-md:hidden），右边「每条消息消耗 <b.readout>10</b> 颗草莓」。
- **样式**：.readout（mono 等宽 12px）、text-muted-foreground。
- **行为（必须保留）**：voiceText 只来自「按住说话」：「识别中…」→ 识别成功后清空；失败显示后端 error、「未识别到语音」或「识别失败」，2 秒后清；没有权限显示「麦克风未授权」。这一行不在 aria-live 区里。
- **状态**：voiceText 有 / 无。
- **手机端**：只剩草莓消耗那一行。
- **改造风险**：「10」是写死的，和后端扣费常量没有联动。

### 右侧抽屉：分身 / 分身广场（section，直接挂组件）
- **位置**：page.tsx:2327-2386；打开时聚焦 323-330；focusChatInput 426-431；focusVisibleDrawerTrigger 319-322
- **结构**：两个 section：#agent-drawer（aria-label「分身管理」）和 #exchange-drawer（aria-label「分身广场」），都带 aria-hidden={!open}、inert={!open}、tabIndex=-1。class：glass fixed inset-y-0 right-0 z-[55] flex flex-col outline-none。inline：width min(960px, calc(100vw - 56px))；borderLeft 1px var(--glass-border)；打开时 boxShadow -12px 0 32px rgba(0,0,0,0.28)；transform translateX(0) 或 translateX(105%)；transition transform 360ms cubic-bezier(.22,.61,.36,1)。头部 div.flex.shrink-0.items-center.justify-between.border-b.px-4.py-2：标签 span.text-xs.font-medium.text-muted-foreground「分身」/「分身广场」+ 收起按钮（X 14，h-6 w-6 rounded，aria-label「收起分身面板」/「收起分身广场」）。主体只在打开时挂载：MyAgentWorkspace embedded onSaved={updateAgent}，或 AgentExchangeWorkspace embedded onOpenMyAgent={() => setDrawer('agent')}。
- **样式**：.glass、var(--glass-border)、hover:bg-secondary hover:text-foreground、硬编码 rgba 阴影。
- **行为（必须保留）**：打开时 section 自己获焦；在 section 内按 Esc → closeDrawer + 焦点回到可见的触发按钮。focusChatInput 读这两个 section 的 aria-hidden 字符串，不等于 "false" 才去聚焦输入框，这样抽屉开着时后台回复不会抢焦点。抽屉互斥。
- **状态**：关闭时桌面上仍在 DOM 里（屏外 105%，inert），子组件已卸载；手机上 max-md:hidden。
- **手机端**：max-md:left-0；max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]!；max-md:w-screen!；收起按钮 40×40。
- **改造风险**：aria-hidden 和 inert 不能丢；宽度里的 56px 是硬编码。这两个是同一文档里的组件（不是 iframe），会直接继承主页面的主题和令牌。

### 右侧抽屉：世界 / 设置（iframe 内嵌 embed=1）
- **位置**：page.tsx:2388-2423（世界 #plaza-drawer）、2425-2460（设置 #settings-drawer）；worldTab / settingsTab 295-296；app/layout.tsx:28-58（data-shell 内联脚本）；globals.css:6-13（mobile 自定义变体）；被嵌页面 embed 分支：app/plaza/page.tsx:362-414、573-592，app/match/page.tsx:303-308，app/settings/page.tsx:14、128-130，app/profile/page.tsx:86-91、161
- **结构**：div#plaza-drawer / div#settings-drawer，class：glass fixed z-[55] flex flex-col。inline：top/bottom/right 0；width calc((100vw - 56px) * 2 / 3)；borderLeft var(--glass-border)；打开时阴影 rgba(0,0,0,0.28)；translateX(0|105%)；360ms 同一条曲线；willChange transform。头部 div.flex.shrink-0.items-center.justify-between.border-b.px-4.py-2：标签「世界」/「设置」+ div.flex.gap-1，里面两个 tab chip（「热点与帖子」/「匹配」；「设置」/「账户」，当前项 chip-on）+ 收起按钮（X，w-6 h-6，没有 type、没有 aria-label，只有 title「收起」）。主体：有 username 时 iframe.flex-1.w-full.border-0，src 按 tab 取 /plaza?embed=1、/match?embed=1、/settings?embed=1 或 /profile?embed=1（没有 title 属性）；没有 username 时 div[role=status].flex-1.p-5.text-sm.text-muted-foreground「正在加载身份…」。
- **样式**：.glass、.chip / .chip-on、hover:bg-secondary、硬编码阴影。
- **行为（必须保留）**：按注释「不卸载 iframe，重开秒回原状态」，容器一直在 DOM 里。只要 username 就绪，iframe 就开始加载，即使抽屉关着（/plaza 里有 SolarSystem3D 的 WebGL，/match 里有 Earth3D）；切 tab 会改 src，导致重新加载。iframe 内的 layout 脚本：embed=1 且父窗口 ≥768px 时给 iframe 的 <html> 加 data-shell="desktop"，并监听父窗口断点变化，于是 mobile: 变体跟随父视口而不是 iframe 自己的窄宽度。被嵌页面在 embedded 时不渲染 Sidebar，也不加底部 56px 内边距。
- **状态**：两个 tab 状态；iframe 的加载和失败态由被嵌页面自己处理，外壳不管；没身份时显示「正在加载身份…」。
- **手机端**：max-md:left-0；bottom 停在 tab 栏上沿（!important）；max-md:w-screen!；关闭时 max-md:hidden（display:none，但 iframe 照样加载）；收起按钮 40×40。
- **改造风险**：这两个抽屉没有 aria-hidden/inert，也没有 Esc 处理，桌面上关着时屏外的 iframe 仍能被 Tab 进去；桌面 Sidebar 也没给它们设 aria-controls。iframe 是独立文档：① 主题——各自的 <html class="dark"> 由 layout 写死，主页面切主题传不进去；② 背景——iframe 的 body 自己画 radial-gradient + var(--background)，把抽屉 .glass 的半透明整个盖住，烟雨背景 SVG 也得在 iframe 里各画一份；③ 字体、令牌、SVG 滤镜 defs 都要在被嵌文档里各自存在（共享 layout/globals.css，所以会每个 iframe 各加载一份）。

### 抽屉外部点击背板
- **位置**：page.tsx:2462-2470
- **结构**：anyDrawerOpen 为真时渲染 div.fixed.left-14.top-0.right-0.bottom-0.z-50[aria-hidden]，透明，onClick=closeDrawer。
- **样式**：透明，没有颜色。
- **行为（必须保留）**：z-50 比抽屉的 z-[55] 低；left-14 让开桌面侧栏，侧栏可以直接切到别的抽屉。
- **状态**：—
- **手机端**：max-md:left-0；max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]，tab 栏仍然可点。
- **改造风险**：left-14 写死了导航宽度。

### 主题切换入口
- **位置**：components/Sidebar.tsx:46、171-178（桌面侧栏底部）；components/ConversationPicker.tsx:40、100-105（手机对话框底栏）；lib/useTheme.ts:1-20；app/layout.tsx:16、28；app/manifest.ts:11；globals.css:5、54-164
- **结构**：page.tsx 自己没有主题按钮。桌面：Sidebar 底部一个 Sun/Moon 图标按钮（h-10 w-12 rounded-[6px]，title「切换浅色 / 切换深色」）。手机：对话目录对话框底部 div.border-t.px-5.py-2.md:hidden 里的 btn btn-quiet h-10「主题」（有 aria-label）。
- **样式**：令牌两套：:root 是浅色，.dark 是深色主主题；@custom-variant dark (&:is(.dark *))；两套都包含 --glass、--glass-strong、--glass-border、--glass-hi、--fill、--grain、--shadow、--spot-a/b/c、--bubble-*、--amber-ink、--dim、--rec、--rec-soft，以及 shadcn 语义色。
- **行为（必须保留）**：toggleTheme 就是 document.documentElement.classList.toggle('dark')。useSyncExternalStore 用 MutationObserver 监听 html 的 class，服务端快照恒为 dark。layout 把 <html className="dark"> 写死，所以不持久化（刷新回到深色），也不同步到 iframe。viewport themeColor 写死 #0E1219，manifest theme_color 写死 #09090b。
- **状态**：dark 布尔值。
- **手机端**：入口藏在对话目录对话框底部，要先点页头 PanelLeft 才看得到。
- **改造风险**：昼/夜两套主题要做到持久化、首屏不闪（layout 已经有一段 head 内联脚本可以参照）、同步进 iframe、themeColor 跟着主题变，这些现在都没有。Sidebar 的主题按钮没有 type 和 aria-label。

### 危机 / 错误 / 余额不足 / 生成状态的呈现（没有独立横幅或弹层）
- **位置**：page.tsx:1607-1626（非 2xx 解析）、1662-1667（crisis 事件）、1693-1711（生成状态与图片）、1720-1723（data.error）、1724-1781（卡片）、1791-1814（失败写进气泡 + 重试）、1815-1828（finally）；后端 backend/routers/chat.py:67-70、161-177
- **结构**：page.tsx 里没有危机横幅、余额不足弹层或全局错误条，全部落在当前回复气泡里。错误：内容写成「错误：{msg}」，如果已有部分回复，就空一行接在后面。生图/修图失败：在这条气泡上挂 imageGenerationRetry，由 ChatBubble 渲染重试按钮。危机：SSE 的 {crisis:true} 只用来清 generationStatus 和 imageGenerationRetry，并把 generatingImage 置 false；求助资源当普通 text 流进同一条气泡。余额不足：后端返回 200 + SSE {error:「今天的草莓用完了，明天会自动补到 N 颗；急用请联系管理员补充 🍓」或「草莓不足，内测期间请联系管理员补充 🍓」}，前端走 data.error，显示成「错误：…」气泡。页面里其他提示：原生 alert「只能上传图片」「图片不能超过 5MB」(1854、1858)；原生 confirm 删除对话 / 清空(1434、1390)；micNotice 行；TTS 被拦 / 限速行；referenceUploadError（role=alert）；对话目录错误（role=alert）。
- **样式**：气泡里没有错误专用样式，ChatBubble 按普通 assistant 文本渲染；referenceUploadError 用 text-destructive；对话目录错误用 text-[color:var(--rec)]。
- **行为（必须保留）**：非 2xx 时先找 data: 行，没有就解析原文 JSON 的 error / detail；detail 是数组时给固定中文：修图「参考图参数校验失败。请确认图片为 PNG、JPEG 或 WebP，每张不超过5MB，最多3张。」，其他「请求参数校验失败，请检查内容后重新发送。」；不显示原始校验载荷（可能含图片）。流结束时：没收到图 →「图片生成未完成，请重试。」/「图片修改未完成，请重试。」；没收到 done →「连接已中断，请重新发送消息。」；生成图片地址非法 →「生成图片的地址无效，请重试。」；参考图回写非法 →「参考图保存结果无效，请重试。」。卡片回复会替换流式文本并清 TTS 队列，挂 pendingTtsText 等用户点「帮我读」。
- **状态**：见上。
- **手机端**：和桌面一样，都在气泡里。
- **改造风险**：如果复刻稿给危机提示或余额不足做了独立视觉，前端目前没有可以区分它们的数据钩子：只有流内的 crisis 布尔，余额不足只是一个 error 字符串。要加横幅就得加新状态，不是纯样式改动。

### 语音 / 朗读状态机（不渲染，但驱动页头和输入区显示）
- **位置**：page.tsx:399-455（state 与 ref）、643-650（挂载时预热麦克风）、794-908（免提录音 + 静音检测）、910-1238（TTS 双槽音频池、票据、预取、队列、解锁）、1240-1276（换账号/卸载清理）
- **结构**：没有 DOM，<audio> 用 document.createElement 创建，不挂进文档树。对外提供给 UI 的 state：voiceOn、handsFree、recording、inlineRecording、micNotice、voiceText、ttsPlaybackBlocked、ttsWaitUntil / ttsWaitNow、isLoading。
- **样式**：—
- **行为（必须保留）**：两个复用的音频槽；requestTtsTicket 取票据后播 /tts/stream?ticket=…，剩余不足 15 秒的票据重新取。首个用户手势里同步播一段静音 wav 来解锁；document 上用捕获阶段的 click / keydown / touchend 全局监听来补 prime(1224-1238)。免提：朗读完自动开麦，RMS 低于 0.015 持续 1.5s 停止，最长 30s，POST /asr/recognize 后自动发送；遇到 429 自动关免提并提示。挂载时 getUserMedia 预热麦克风权限。换账号或卸载时中止流、录音和 TTS。
- **状态**：见页头和输入区。
- **手机端**：同桌面。
- **改造风险**：朗读、免提、「点此播放」、「帮我读」的点击处理必须在同一个用户手势里同步调用 primeTtsAudio 或 play（WebKit/iOS 自动播放限制）。别把这些按钮包进会延后 click、要先等动画结束的容器或异步包装里。

### 未渲染代码与后台副作用
- **位置**：page.tsx:25-48（Peer 相关接口）、147-236（MiniCloudCard）、238-249（DEMO_MESSAGES）、462-477（peer 与用户菜单 state）、552-641（/users、/user/settings、/peer/rooms、/match/pending 轮询）、1278-1353、1389-1392（handleClearChat）、1929-1976（peer WebSocket）
- **结构**：这些都不在 JSX 里渲染；MiniCloudCard 定义了但从没被用到。
- **样式**：MiniCloudCard 用了 glass-card、tag tag-amber、var(--amber-ink)、bg-secondary、bg-primary，以及 1s / 1.2s 的 inline 过渡。
- **行为（必须保留）**：网络副作用仍在跑：挂载时拉 /users（生产环境 404 会被静默忽略）、/user/settings、/peer/rooms；登录后每 8 秒轮询 /match/pending，结果写进 pendingMatches（不显示）。
- **状态**：—
- **手机端**：—
- **改造风险**：如果判据是按类名全局 grep（比如「不得再出现 glass-card / tag-amber」），会命中这段死代码。规格要写明这段是保留还是删除；删除会改变网络行为。

### 跨区域要点
- 快照：Fiona 仓库 HEAD 586d86a，frontend 工作区干净；page.tsx 共 2474 行，sha1 574f1505db53b8d5cb728f4286122db90170d3bd。上面的行号都按这个版本。
- 断点：page.tsx 用 Tailwind 的 max-md: / md:hidden（<48rem=768px），JS 里的 matchMedia('(width < 768px)') 有 5 处（309、339、377、384、1991）。被嵌 iframe 页面用自定义 mobile: 变体（globals.css:7-13，在 :root:not([data-shell=desktop]) 下才生效），由 layout.tsx:30-58 的内联脚本按父窗口断点设置 data-shell。主页面不是 iframe，不会有 data-shell，所以在主页面里 mobile: 和 max-md: 等价。
- 导航宽 56px 写死 7 处：left-14 在 2043、2097、2466；calc(100vw - 56px) 在 2343、2374、2396、2433。手机 tab 栏高 calc(56px+env(safe-area-inset-bottom)) 在 page.tsx 有 11 处（2043、2097、2104、2106、2173、2190、2341、2372、2391、2428、2466），另外 Sidebar.tsx:183 一处，被嵌页面的 mobile:pb-[calc(56px+…)] 也有若干处。竖排书签导航如果改宽度或改 tab 栏高度，这些地方要一起改。
- z 层级：页头和输入区 z-[2]；「回到最新」z-20（ChatScrollArea 局部）；历史背板 z-40，历史抽屉 z-50；抽屉外背板 z-50；四个右侧抽屉 z-[55]；手机对话框背板 z-[61]，对话框 z-[62]；手机 tab 栏 z-[70]；GeneratedImage 的原生 modal dialog 在 top layer。
- page.tsx 里的 .glass 有 7 处（2043、2113、2190、2341、2372、2391、2428），glass-card 只在死代码 178 用了一处。桌面同屏常驻的 backdrop-filter 表面有：Sidebar aside、对话目录、页头、输入区，加上 4 个推到屏外的抽屉。body 是 background-attachment: fixed，Signal 有常驻 rAF，抽屉打开时世界/设置 iframe 还可能跑着 WebGL。叠加更重的 SVG 透镜滤镜时，这些都是性能风险点。
- 现有的不透明退路：globals.css:284-289。浏览器不支持 backdrop-filter，或用户开了 prefers-reduced-transparency 时，.glass / .glass-card 退成 var(--card) 实底、去掉 grain。「素瓷」可以挂在这里，但 page.tsx 里写在 inline style 上的边框和阴影（--glass-border、rgba(0,0,0,0.28)）管不到。
- 边缘透镜如果写成 backdrop-filter: url(#svg滤镜)，只有 Chromium 系支持；WebKit（含 iOS 主屏 PWA，layout 里设了 appleWebApp capable）和 Firefox 不支持，需要退路。
- page.tsx 里的硬编码颜色：rgba(0,0,0,0.28) 阴影 5 处（2044、2345、2376、2398、2435），bg-black/20 背板 2 处（2097、2104），hover:text-white 1 处（2238），🍓 和默认头像 ✨ 两个 emoji。其余颜色都走 var(--glass-border|fill|amber-ink|rec|rec-soft|dim|foreground)，或 shadcn 语义类（bg-secondary、bg-secondary/50、text-muted-foreground、text-foreground/70、bg-primary、text-primary-foreground、text-destructive、hover:bg-destructive/10、border-border、bg-background）。page.tsx 里没有 hud-*、echo、bubble-*、btn-primary、tag（死代码除外），这些只出现在其他组件或 globals.css。
- 字体：现在只有 --font-sans-stack（苹方 / 雅黑系统黑体）和 --font-mono-stack；.readout 用等宽字体显示余额、草莓 10、会话时间、天气数值。layout 没用 next/font，也没接 Google Fonts，项目里没有任何衬线或思源宋体资源。
- 动画清单：tw-animate-css 的 animate-in slide-in-from-left duration-300（2043 历史抽屉、2106 手机对话框）；四个抽屉 transform 360ms cubic-bezier(.22,.61,.36,1)；Signal 的 rAF；ChatBubble 的 msg-in-left/right 0.2s、typing-cursor 1.4s 闪烁、LoaderCircle animate-spin；ChatScrollArea 不用 smooth 滚动。globals.css:459-468 在 prefers-reduced-motion 下全局关掉 animation 和 transition，Signal 自己另有静态分支。
- 主题：只能通过切 html 的 .dark class，不持久化，服务端快照恒为 dark，layout 把 <html className="dark"> 写死，iframe 不跟着切，themeColor 写死。所以 page.tsx 的世界/设置抽屉（iframe）在浅色模式下仍然是深色。
- iframe 是独立文档：主题 class、body 背景、字体、令牌、SVG 滤镜 defs 都要在每个被嵌页面里各有一份。因为大家共用 layout.tsx 和 globals.css，放在这里的全局资源每个 iframe 都会各加载一次。iframe 的 body 不透明，会盖住抽屉外壳的玻璃效果。
- 必须保留的锚点：data-chat-panel、data-chat-composer、data-chat-scroll-area / -viewport / -content、#agent-drawer、#exchange-drawer、#plaza-drawer、#settings-drawer、#conversation-picker-dialog（Sidebar 的 aria-controls 和 focusVisibleDrawerTrigger 依赖它们，以往验收截图脚本也用它们）；两个 section 抽屉的 aria-hidden / inert 字符串值（focusChatInput 读它）；footer 上的 composerRef（测高）；textareaRef；所有 aria-label（「朗读」「免提」「按住说话」「语音转文字」「发送消息 / 生成图片 / 修改图片」「图片模型」「图片比例」等）。仓库里没有自动化 UI 测试引用这些选择器，只有 docs/tasks 文档提到。
- 既有不变量（来自 docs/tasks/2026-09-23-mobile-layout/02-spec.md）：手机可点目标 ≥40×40（页头朗读/免提现状是 36×36），textarea 16px，tab 栏始终可见可点，抽屉底边停在 tab 栏上沿，390×844 和 360×740 下无横向滚动，输入区下沿不低于 tab 栏上沿。
- 接口与数据形状不能因为改版而变：POST /chat 的请求体（1595-1603：conversation_id、message、image_base64、mode、image_model、aspect_ratio、reference_images），SSE 事件 ChatStreamEvent(50-62)，以及 GET /image-models、POST /asr/recognize、TTS 票据加 /tts/stream、GET /strawberry、/match/pending 轮询。

## cards：消息内与工作区组件（Fiona/frontend @586d86a）：ChatBubble、GeneratedImage、ChatScrollArea、NewsCardContent、AgentIdentityCard、AgentMemoryPanel、MyAgentWorkspace、AgentExchangeWorkspace、ConversationPicker、Signal，以及 app/page.tsx 抽屉、app/agents/**、app/community/page.tsx 怎样组合它们。路径都相对于 frontend。本次只读，没有改任何文件。
### ChatBubble·消息块（用户与分身）及元信息行
- **位置**：components/ChatBubble.tsx:1-343（打字机 useTypewriter 12-48；类型 Message/CardData/WeatherData/ImageGenerationRetry/ImageModelId 50-110；props 112-123；主体 125-341；导出 memo 343）。挂载点：app/page.tsx:2181-2186（messages.map，外层 2176 `flex w-full max-w-[760px] flex-col gap-[22px]`）
- **结构**：根节点 168-176：`group flex items-start gap-2`。用户消息：`ml-auto max-w-[520px] flex-row-reverse msg-in-right`；分身消息：`max-w-[640px] msg-in-left`。分身头像 178-182：28px 方块，内放 agentAvatar（emoji）。右侧是列 184：用户 items-end，分身在手机上 flex-1。分身说话人行 185-188：1.5px 琥珀方点 + agentName。生成图 191-193（只给分身，用 GeneratedImage）。用户参考图组 194-197（最多 3 张，用 GeneratedImage variant=reference，aria-label="本次修改的参考图片"）。用户普通上传图 198-206：<img>，点击 window.open。生成状态行 208-210。文字气泡 213-223：content 为 "[发了一张图片]" 时不渲染，有 generationStatus 时也不渲染。卡片 226-281（见工具卡区域）。重新生成 283-289。帮我读/不用 292-308。元信息行 311-337：时间、静音图标、悬停时显示的删除按钮。分隔线分支 158-166（isDivider，全库没有任何地方会设它，是死分支）。
- **样式**：气泡用 .bubble-user / .bubble-ai（globals.css:273-281；令牌 --bubble-user/--bubble-user-text/--bubble-ai/--bubble-ai-text 在 :root 108-111，.dark 160-163）。用户块：浅底 + 1px var(--glass-border) + 10px 圆角 + padding 9px 14px + line-height 1.6；分身无底，line-height 1.75。打字中加 .typing-cursor（globals.css:322-327，▌ 用 var(--amber-ink)，blink 1.4s）。入场 .msg-in-left/.msg-in-right（globals.css:330-341，0.2s 位移 12px）。头像 `rounded-[6px] bg-secondary text-sm`；说话人点 inline style background var(--amber-ink)（186）；时间 `.readout text-[11px]`（317）。删除按钮 `text-muted-foreground/50 hover:text-destructive`；用户上传图 `max-h-[260px] max-w-[260px] rounded-[10px]`。分隔线：`bg-border` + `text-muted-foreground/50`。本区没有任何 dark: 变体，换主题全靠令牌。
- **行为（必须保留）**：useTypewriter（12-48）用 RAF 按 45cps 推进；一次落后超过 60 字时加速；前缀对不上直接同步。只对分身消息生效（147），历史消息首帧不回放。stillTyping（148）决定光标。引用计算（127-142）：referenceUrls 只取 referenceImagePath 白名单内的，或 localReferenceImageUrls 里的 data URL。selectedReferenceIndex 和 referenceLimitReached（≥3）推出 editDisabled/editLabel/editDisabledReason（139-142）。按钮文案「以此图修改 / 加入参考 / 已选为图N」，后端 persona.py:51、intent_router.py:79、chat.py:140/146、chat_service.py:607/1096 和 README:116 都按原字引用，不能改字。onDelete(id, dbId) 只在 hovered 且不在打字时出现（328），isLoading 时父组件传 undefined（page.tsx:2182）。静音按钮（319-325）只切本地 muted 状态，不影响任何朗读，纯装饰。onEditImage 只在 imagePath 合法时传入（192）。Message 类型被 lib/useConversations.ts:4 和 app/page.tsx:5 引用，接口要保持不变。组件用 memo 包装，key 规则在 page.tsx:2182。
- **状态**：打字中：isTyping 或 stillTyping 时有光标；内容为空时显示 ""，非打字时显示 "…"（221）。生成中：generationStatus 行，role=status，LoaderCircle 旋转（208-210），这时隐藏文字气泡。失败可重试：imageGenerationRetry 存在时出现「重新生成 / 重新修改」按钮，disabled=imageRetryDisabled，title 随原因变化（283-289）。帮我读待确认：pendingTtsText（292-308）。删除只在悬停时出现，没有键盘或触屏入口。
- **手机端**：max-md：根节点 max-w-full，分身消息 w-full（172）；文字气泡 max-md:max-w-full / w-full（217）；用户图 max-md:max-w-full（203）；网页卡要点 max-md:min-w-0 break-words（276）。手机上没有 hover，删除按钮实际出不来。消息列在 ChatScrollArea 内容区里 max-md:px-4。
- **改造风险**：1) app/history/page.tsx:335-351 手抄了同一套气泡结构：说话人方点、写死的「Chloe」、bubble-user/bubble-ai、readout 时间。只改 ChatBubble 会让两处不一致。2) 气泡文案要原样保留，以及「AI 分身」头像 title（179：`${agentName} · AI 分身`）。3) .bubble-* 和 .typing-cursor 是全局类，history 页也在用。4) 消息列 page.tsx:2176 没有 mx-auto，宽屏下靠左；输入区 2191 用 mx-auto，是居中的。复刻时要明确对齐方式。5) 打字机推高内容依赖 ChatScrollArea 的 ResizeObserver 跟随，气泡加动画或改高度会影响自动跟随底部。

### ChatBubble·工具卡内联（天气卡/网页卡/生成状态/重新生成/帮我读）
- **位置**：components/ChatBubble.tsx:225-308；数据来源 app/page.tsx:1740-1780（卡片回复会替换流式文本，content=tip，并挂 pendingTtsText）、1693-1711（generating_image/editing_image 状态和 generated_image）、1803（imageGenerationRetry）
- **结构**：天气卡 226-251（cardData.subtype==="weather" 且有 weather）：根 `glass-card w-[320px] max-w-full overflow-hidden`。头行「天气 | 城市」带下边框。主行：32px 温度读数 + 天况文字 +「体感 xx° 湿度 xx%」。底部 3 列网格，取预报前 3 天，每列「周几 + low° high°」，列间左边框。conditionIcon/icon/windSpeed/visibility 都没渲染。网页卡 254-281（非 weather 且 points 非空）：`glass-card w-[340px] max-w-full`。头行 Globe 图标 + source（缺省「网页」）+ 去掉协议、截到 40 字的 url（不可点）；ul 要点列表用琥珀 • 符号。items/sources/error 字段在这里都没用（只有孤儿组件 NewsCardContent 用 items）。重新生成按钮 283-289。帮我读/不用 292-308，在气泡下方。
- **样式**：glass-card（globals.css:192-200：var(--glass) 底 + var(--grain) 噪点 + blur(14px) saturate(1.5) + 1px var(--glass-border) + 10px 圆角 + inset 高光 var(--glass-hi) + var(--shadow)）。分隔线用 inline style borderColor var(--glass-border)（230、241、243、261）。数字用 .readout：温度 inline fontSize 32 + color var(--foreground)。Globe 和 • 用 var(--amber-ink)。要点 `text-sm text-foreground/90 leading-relaxed`。按钮：重新生成 `btn h-7 self-start px-2.5 text-xs`（287）；帮我读和不用 `btn btn-quiet h-7 px-2.5 text-xs`（296、303）。btn 家族在 globals.css:244-258。
- **行为（必须保留）**：onRetryImage(message.imageGenerationRetry)：page.tsx:2183 调 handleSend(request.prompt, request)，用的是当前选中的模型；按钮 title 区分「重新修改」（有 referenceImages）和「重新生成」。onConfirmTts(id, text) / onDeclineTts(id)：page.tsx:1381/1386 会清掉 pendingTtsText。卡片出现时文字气泡同时显示 tip。
- **状态**：天气卡没有加载或错误态，cardData.error 不区分。网页卡 points 为空时整卡不渲染。重新生成按钮在 imageRetryDisabled 时禁用（锁定、加载中、有待发图、正在读参考图都算，page.tsx:2185）。
- **手机端**：两种卡都是 max-w-full；天气卡固定 320、网页卡固定 340，窄屏靠 max-w-full 收缩。网页卡要点 max-md:min-w-0 break-words（276）。按钮在手机上没有放大到 40px，仍是 h-7。
- **改造风险**：1) 卡片宽度是写死的 320/340，换成瓷釉玻璃后如果加边缘透镜 SVG 滤镜，overflow-hidden 会裁掉滤镜边缘。2) 天气卡温度写死 fontSize 32、color var(--foreground)，改字体（思源宋体）时数字读数仍走 --font-mono-stack（.readout）。3) 卡片里的 glass-card 叠在 ChatScrollArea 里（父级没有 glass），但页面头部和输入区是 .glass，滚动经过时会出现 backdrop 叠加。

### GeneratedImage·生成图片卡 / 参考图缩略 / 大图预览
- **位置**：components/GeneratedImage.tsx:1-182。用到它的地方：ChatBubble.tsx:191-196（生成图 + 用户消息参考图）；app/page.tsx:2216（输入区已选参考图，compact + localPreview）；app/history/page.tsx:343、345（历史页，没有 onEdit）
- **结构**：根 132-136：`glass-card max-w-full overflow-hidden rounded-[10px] border`；生成图宽 280，参考图宽 120；被选中时加 ring-1 + 琥珀边。媒体区 137-149：`relative flex items-center justify-center bg-secondary/40`。生成图 min-h-36 max-h-[360px]，有宽高时用 inline aspectRatio；参考图 min-h-18 max-h-24，compact 时 min-h-12 max-h-16。加载中提示 138；错误块 139-142；放大按钮包着 img 143-148，未加载完时为 `absolute inset-0 opacity-0`。底栏 150-154：左边标签「AI 生成」或「参考图 N」，右边放大（Maximize2）、下载（Download），参考图只显示图标。修图按钮 155-160：只有生成图且有 onEdit 时才有，整宽，顶部边框。预览弹窗 161-179：createPortal 到 body，原生 <dialog>，头部是标签 + 修图按钮 + 下载图片 + 关闭（autoFocus），下面是大图。
- **样式**：glass-card；弹窗用 `glass m-auto max-h-[94vh] max-w-[94vw] rounded-[10px] border p-0 shadow-2xl backdrop:bg-black/75`（164），backdrop 写死黑 75%。边框全部 inline var(--glass-border)；选中态 borderColor var(--amber-ink) + `ring-[color:var(--amber-ink)]`；修图按钮选中时 `font-medium text-[color:var(--amber-ink)]`，未选中禁用时 `disabled:opacity-40`。按钮都是 `btn btn-quiet h-7 px-2.5 text-xs`；修图按钮额外 `rounded-none border-x-0 border-b-0 border-t`。放大按钮焦点环 `focus-visible:outline-[color:var(--ring)]`。
- **行为（必须保留）**：IntersectionObserver 懒加载，rootMargin 240px（43-54）。可见后用 apiFetch 带鉴权取 blob，得到 objectURL，校验 image/* 类型，卸载时 abort 并 revoke（56-78）。localPreview 只接受 isLocalReferenceDataUrl 的 data URL（39-41）。retry 改 attempt 重拉（91-96）。download（98-115）：生产环境且同源时走原 URL 加 ?download=1，其余用 blob；文件名取路径末段，本地参考图按 MIME 定扩展名。弹窗（80-89）：showModal；关闭后把焦点还给原元素，但 selectForEdit 时不还（restoreFocusRef，122-129），让输入框拿到焦点。点 backdrop 关闭（163）；onCancel/onClose 同步状态。selectForEdit 先查 onEdit、editDisabled、loaded、previewError。按钮 aria-label 是「放大/下载 + AI 生成的图片 / 参考图 N」；弹窗 aria-label 是「…预览」；关闭按钮 aria-label="关闭图片预览"。
- **状态**：加载中：role=status，spinner +「正在加载图片…」或「加载中…」（138）。错误：role=alert，ImageOff + 文案 +「重新加载」（139-142），文案有「图片加载失败，请重试。」「图片格式无法显示，请重试。」「图片无法显示，请重新加载。」「本地参考图格式无效，请重新选择。」。禁用：未加载或出错时放大和下载禁用；修图按钮在 editDisabled、未加载或出错时禁用，title 给出原因。选中：editSelected 时 ring + 琥珀色 + 文案「已选为图N」。模型标注：目前没有。ChatBubble 不把 message.generatedImage.model 传进来，底栏固定写「AI 生成」。
- **手机端**：max-md：按钮 h-10、min-w-10，参考图按钮 px-0 只显示图标（142、152、153、157、171-173）。参考图底栏 max-md:flex-wrap justify-between，标签独占一行（150-151）。放大按钮 max-md:flex min-h-10（143）。弹窗 max-w-[94vw]，图片 max-w-[92vw] max-h-[80vh]（177）。
- **改造风险**：1) 模型标注没有数据：message.generatedImage.model 只在 SSE 实时生成时写入（page.tsx:1709），值是供应商真实模型串，例如 qwen-image-3.0、doubao-seedream-5-0-flash-260915，或环境变量覆盖值（backend/tools/image_generation.py:120、476、534），不是选择器 id。刷新后从历史加载（lib/useConversations.ts:54-66 toMessages；StoredMessage 10-17 没有 model/width/height 字段），宽高和模型都会丢。要做稳定的模型标注，需要后端存储，或者从 imageGenerationRetry.imageModel 加 page.tsx:79-80 FALLBACK_IMAGE_MODELS 的 label 映射，而且历史页和刷新后仍然会缺。2) 弹窗挂在 top-layer，用 .glass；backdrop 写死 black/75，昼天青主题下要改令牌化。3) 改成边缘透镜 SVG 滤镜时，overflow-hidden 加 rounded 会裁滤镜。backdrop-filter:url() 只有 Chromium 支持，要有退路。4) 同一个组件服务三处（聊天、输入区 compact、历史页），改尺寸会连带输入区参考图条（page.tsx:2213-2232，固定 w-[120px]、max-h-[144px]）。5)「以此图修改 / 加入参考」文案被后端引用，不能改。

### ChatScrollArea·聊天消息滚动视口
- **位置**：components/ChatScrollArea.tsx:1-144；挂载点 app/page.tsx:2173-2189（外层 `absolute inset-0 flex flex-col pt-16 pb-[var(--composer-height)]`，手机 `pt-20 pb-[calc(var(--composer-height)+56px+env(safe-area-inset-bottom))]`，resetKey=`${username}:${conversationId}`）
- **结构**：外层 116 `relative flex min-h-0 flex-1 flex-col` data-chat-scroll-area。视口 117-135：role=region aria-label="聊天消息" tabIndex=0，data-chat-scroll-viewport，overflow-y-auto，inline overflowAnchor none、scrollBehavior auto。内容 136 `space-y-4 px-6 py-4 max-md:px-4`，data-chat-scroll-content。「回到最新」浮钮 138-141：绝对定位在底部居中。
- **样式**：视口焦点环 `focus-visible:ring-1 ring-inset ring-primary/40`。浮钮 `rounded-full border border-border bg-background/95 px-3 py-1.5 text-xs text-muted-foreground shadow-sm hover:text-foreground focus-visible:outline-primary`。没有 glass；聊天背景透出 body 背景（globals.css:168-178 三个光斑 radial-gradient + var(--background)，background-attachment fixed）。
- **行为（必须保留）**：跟随状态机：followingRef / previousRef / upwardIntentRef（23-27）。每帧最多一次 scheduleFollow，直接设 scrollTop，不用 smooth（37-54，注释说明 smooth 跟不上打字机）。ResizeObserver 同时观察内容和视口（69-84）。onScroll 判断用户上滑和 resize 造成的回夹（96-113，BOTTOM_TOLERANCE=2）。wheel（ctrlKey 除外）、touch、键盘（ArrowUp/PageUp/Home/Shift+Space 以及对应向下键，输入框内不处理）都记录意图（122-134）。通过 imperative handle 暴露 scrollToLatest（62），page.tsx 发送时会调用。resetKey 变化时 layout effect 回到底部（64-67）。
- **状态**：不跟随且距底超过 2px 时显示「回到最新」（34、138）。本组件没有空、加载、错误态，空态文案由 page.tsx:2178-2180 在 children 里渲染。
- **手机端**：内容区 max-md:px-4；手机上下 padding 由父级 page.tsx:2173 算（头部 80px，底部是输入区高度 + 56px 标签栏 + 安全区）。
- **改造风险**：1) 别把背景、远山、烟雨 SVG 画进视口内部或给内容加 transform，否则会改变 scrollHeight，ResizeObserver 会触发误跟随。2) data-chat-scroll-* 属性没有消费者（全库搜索只有自身），可以保留。3) 给消息加入场动画或延迟布局，会和「在底部才跟随」的判定交互，要实测上滑后不被拉回。

### ConversationPicker·对话列表（桌面左栏 / 手机抽屉）
- **位置**：components/ConversationPicker.tsx:1-108；组合在 app/page.tsx：桌面 2101（className="max-md:hidden"），手机 2103-2109（fixed 遮罩 z-[61] + role=dialog aria-modal 容器 z-[62]，w-[min(85vw,320px)]，animate-in slide-in-from-left duration-300）；props 1979-2002；焦点陷阱和断点关闭 334-371
- **结构**：aside 42-45：`glass flex h-full w-[260px] shrink-0 flex-col border-r`，aria-label="对话列表"。头部 47-59：h-16，h2「对话」+ 当前对话记录（Clock，onHistory 有才出现）+ 新对话（Plus）。列表 61-87：ul role=listbox；每项 li role=option aria-selected，内含标题按钮（截断）+ 相对时间 .readout + 删除按钮（Trash2）。下面依次是锁定提示 89、空态 90、错误 91-94。页脚 96-99：「对话仅你可见」+「完整历史」。手机专属主题切换 100-105（md:hidden，Sun/Moon +「主题」）。
- **样式**：`.glass`（globals.css:183-189：var(--glass-strong) + 噪点 + blur(22px) saturate(1.5) + inset 高光）。分隔线 inline var(--glass-border)（44、47、96、100）。列表项 `rounded-[6px] px-3 py-2 text-[13px] text-muted-foreground hover:bg-secondary aria-selected:bg-secondary aria-selected:text-foreground`（69）。删除 `opacity-0 group-hover:opacity-100 hover:text-[color:var(--rec)] focus-visible:opacity-100`。错误 `text-[color:var(--rec)]`。按钮 `btn btn-quiet w-[34px] px-0`，重试 `btn btn-quiet h-7 px-2.5 text-xs`。时间 `.readout text-[11px]`。
- **行为（必须保留）**：formatRelative（7-20）：今天显示 HH:mm、昨天、周X、MM/DD，兼容没有时区的串。disabled=loading||locked（39），会禁用切换、删除、重试；新建还要求 canCreate（page 传 !!agent）。onHistory 在手机上会关掉列表再开历史抽屉，并处理焦点（page.tsx:1990-2000）。onFullHistory 新开 /history?user=。主题切换走 lib/useTheme.ts（只切换 html 的 .dark 类，不持久化；layout.tsx:28 初始写死 className="dark"）。page.tsx:358 的焦点陷阱只认 `button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])`，打开后聚焦第一个可用按钮（350），Esc 关闭，回到桌面断点自动关闭（339-348）。
- **状态**：加载：li role=status「正在加载对话…」。锁定：role=status「分身回复或语音进行中，结束后可以切换对话。」。空：「还没有对话。点「新对话」，开始和自己的分身交流。」。错误：role=alert + 重试。选中：aria-selected 的底色。
- **手机端**：max-md:w-full（放进 320px 抽屉）；头部按钮 max-md:h-10 w-10；删除按钮手机常显、40×40（79）；底部多一行主题切换（md:hidden）。手机抽屉 bottom 让出标签栏 calc(56px+safe-area)。
- **改造风险**：1) 如果改成「竖排书签导航」，桌面 260px 宽和 Sidebar w-14（56px）的偏移在 page.tsx 多处写死：历史抽屉 left-14（2043、2097），分身和广场抽屉 width min(960px, calc(100vw - 56px))（2343、2374），世界抽屉 calc((100vw - 56px) * 2 / 3)（2396）。2) listbox/option 里嵌了三个按钮，ARIA 不规范但现状如此；焦点陷阱依赖 button 元素，不能改成 div。3) 主题切换入口这里一处、Sidebar 一处，都只认 .dark 类。昼/夜两套主题如果改名或改选择器，useTheme 和 globals.css:5 的 dark 自定义变体都要同步。4) layout.tsx:16 的 themeColor #0E1219 写死了。

### Signal·语音状态线（待命/正在听/正在说）
- **位置**：components/Signal.tsx:1-98；样式 app/globals.css:234-236（.signal）、239-241（.state-dot）；挂载点 app/page.tsx:2127（头部中列，`max-md:col-span-2 max-md:row-start-2 max-md:h-6`），模式来自 1978（recording||inlineRecording→listening；isLoading→speaking；否则 idle）；登录页 app/login/page.tsx:146（mode=idle，className mt-2）
- **结构**：<svg class="signal" viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden>，内有一条 path 和一个 circle（r=3，idle 时沿线移动的光点）。旁边的状态点和文字在 page.tsx:2129-2132：.state-dot / state-dot-listening / state-dot-speaking +「正在听 / 正在说 / 待命」，手机上隐藏文字。头部 2113 是三列网格 `grid-cols-[auto_minmax(120px,1fr)_auto]`；手机两行 `grid-rows-[56px_24px]`，Signal 独占第二行。
- **样式**：.signal：width 100%，高 40px，overflow visible；path 无填充，stroke var(--amber-ink) 1.5px，non-scaling-stroke，opacity .9；circle fill var(--amber-ink)。.state-dot 6px 圆，idle var(--dim)，listening var(--rec)，speaking var(--primary)。
- **行为（必须保留）**：RAF 循环（76-84）一直在跑，idle 也跑。目标振幅：idle 0、listening 0.5、speaking 0.9，按 dt*6 缓动；140 个采样点，三个正弦叠加，乘 sin 包络，两端为 0（47-66）。idle 且振幅小于 0.02 时光点以 140 单位/秒横移，循环长度 1300（67-73）。随机相位每次挂载固定一次（20，带 eslint 注释）。prefers-reduced-motion 时只画直线、隐藏光点、不启动 RAF（33-40）。modeRef 让模式切换不重建循环。
- **状态**：三态 idle / listening / speaking；没有错误或禁用态。
- **手机端**：page 头部手机上 h-6（24px）占整行第二行；login 页用默认 40px。
- **改造风险**：1) 改成「远山」线形时，viewBox 1000×40、preserveAspectRatio none 和 non-scaling-stroke 决定了横向拉伸不变粗，新形状要保留这个约束，否则手机 24px 高时会变形。2) RAF 常驻：新增 SVG 滤镜（比如墨晕）会每帧重绘滤镜，代价较高。3) SignalMode 类型被 page.tsx 推导使用；login 页也在用，换样式要两处都验。4) globals.css:460-467 的全局 reduced-motion 只停 CSS 动画，这个 RAF 靠组件自己判断。

### NewsCardContent·新闻卡详情（孤儿组件）
- **位置**：components/NewsCardContent.tsx:1-177；全库没有任何 import（grep app/components/lib 只命中自身），ChatBubble 的网页卡没用它
- **结构**：根 113 `glass-card flex max-h-[88vh] flex-col overflow-hidden rounded-[10px] border`。头部 114-125：列表态是 h2 source +「点击任一条，查看详情与来源」；详情态是「返回新闻列表」按钮。主体 126-171（aria-busy=loading）：列表态 128-143，每条是带 01/02 读数序号的按钮，加「查看详情 >」；详情态 article 145-169，依次是 h2（tabIndex -1）、加载、错误、summary、详细内容、关键信息、背景、来源原文列表。页脚 172-174 是「查看卡片来源」。
- **样式**：glass-card；分隔线 var(--glass-border)；小标题和来源索引用 `text-[color:var(--amber-ink)]`；列表按钮 `rounded-[10px] border p-4 hover:bg-secondary focus-visible:outline-[color:var(--ring)]`；按钮 `btn btn-quiet h-7 px-2.5 text-xs`；序号 .readout。
- **行为（必须保留）**：POST ${API_BASE}/cards/detail，body {title, context}（82-85）；超时 50s（79）；按条缓存 5 分钟（71）；429 返回「查看较频繁，请稍后重试」；AbortController 防止竞态（63-66、89、93）。safeUrl 只放行 http/https 且不带凭据（19-26）；没有来源时报错（40）。焦点：进详情时聚焦 h2，返回时聚焦原来那条（57-61）。外链走 lib/open.ts 的 openExternal。
- **状态**：加载 role=status「正在查找来源并整理详情…」；错误 role=alert +「重新加载详情」；card.error 时列表项是纯文字；无内容时「无可展示内容」。
- **手机端**：只有 sm:px-8（≥640 才加大内边距），没有 max-md 规则。
- **改造风险**：当前没有入口，复刻对照表里应标为「不在任何页面出现」，或由规格方决定是否接回。依赖 CardData 类型（从 ChatBubble 导入，第 5 行）。

### AgentIdentityCard·分身名片（AI 分身标识）
- **位置**：components/AgentIdentityCard.tsx:1-24；使用处 MyAgentWorkspace.tsx:153（preview）、app/agents/[id]/page.tsx:45
- **结构**：section 6 `glass-card flex flex-col gap-[18px] p-[22px] pb-[18px]`，aria-label 为「分身名片预览」或「AI 分身名片」。顶行 7-10：`tag tag-amber`「AI 分身」+ 右侧读数「名片预览 / 分身名片」。名字 11-15：40px；12 字以内用 `<span class="echo" data-text={name}>`，超过时用 28px font-medium break-words。简介 16：13px，line-height 1.7，空时「这个分身还没有填写介绍。」。底行 17-20：带上边框，32px emoji 方块 +「由用户创建的人工智能分身」。预览说明 21（按 is_public 二选一文案）。
- **样式**：.echo（globals.css:212-231）：实心字，::after 用 attr(data-text) 偏移 0.14em/0.12em，1px var(--amber-ink) 描边，opacity .6，white-space nowrap，z-index -1，isolation isolate。.tag/.tag-amber（globals.css:265-269；--accent 底 + --amber-ink 字）。.readout。底行边框 var(--glass-border)。emoji 方块 `rounded-[6px] bg-secondary`。
- **行为（必须保留）**：纯展示，没有状态。display_name 为空时显示「我的分身」。
- **状态**：预览/正式两种模式（文案和 aria-label 不同）；简介空态文案。
- **手机端**：组件内部没有断点。父级用任意选择器兜住 echo 溢出：MyAgentWorkspace.tsx:152 和 app/agents/[id]/page.tsx:43 都有 `max-md:[&_.echo]:max-w-full max-md:[&_.echo]:overflow-hidden max-md:[&_.echo]:break-all`。
- **改造风险**：1) 改掉 .echo（比如换成朱印或竖排名）时，两个父级的 `[&_.echo]` 选择器和 login 页 app/login/page.tsx:144 的 `.echo text-[44px]` 要一起改。2)「AI 分身」标签和「由用户创建的人工智能分身」属于 AI 身份披露（CLAUDE.md 列为待统一政策），要原样保留。3) data-text 必须与可见文本一致，否则描边层错位。

### AgentMemoryPanel·私有记忆
- **位置**：components/AgentMemoryPanel.tsx:1-102；只在 MyAgentWorkspace.tsx:156 的右栏底部使用
- **结构**：section 82 `flex flex-col gap-3 border-t pt-[18px]`，aria-labelledby="private-memory-title"。它不是卡片。头行 83-86：h3「私有记忆」+ 读数（有 revision 时「修订 <b>N</b>」，没有时「仅自己可见」）。说明 87。主体 88-90：未登录 / 加载 / 条目 ul / 空态。错误 91（行内重试）、notice 92。footer 93-98：「刷新」btn-quiet +「清空记忆与个人画像」btn-danger。尾注 99。
- **样式**：上边框 var(--glass-border)；条目 li `border-b py-1.5 text-[13px] text-muted-foreground`；错误 `text-[color:var(--rec)]`；`.readout` 里的 `b` 为前景色（globals.css:209）；.btn-danger（globals.css:257-258，var(--rec) / var(--rec-soft)）。
- **行为（必须保留）**：GET ${API}/agents/me/memory（41）；DELETE 同一地址（68），先用原生 confirm() 二次确认，文案见 60。按账号 key 重挂载（21-24）；useAccountRequest 防止串号（33）。labels 映射 9-12，memoryText 递归拼接 14-19。
- **状态**：未登录 role=status「请登录后查看私有记忆。」；加载 role=status spinner；空「还没有私人画像…」；错误 role=alert + 重试（loading/clearing 时禁用）；清空中 spinner +「正在清空…」；成功 notice role=status；刷新和清空在 !owner、loading、clearing 时禁用。
- **手机端**：没有断点；footer flex-wrap justify-between。
- **改造风险**：confirm() 是浏览器原生弹窗，主题化不了；如果设计稿要自绘确认框，会改变交互（必须保留二次确认和「账号切换时中止」的语义，见 59-63）。

### MyAgentWorkspace·分身编辑（/agents/me 与分身抽屉）
- **位置**：components/MyAgentWorkspace.tsx:1-165；页面 app/agents/me/page.tsx:1-5（服务端组件直接渲染）；抽屉 app/page.tsx:2327-2357（section#agent-drawer 是 .glass fixed，右侧滑入，内置标题条「分身」+ 收起按钮，`{agentOpen && <MyAgentWorkspace embedded onSaved={updateAgent} />}`）
- **结构**：根 98：非 embedded 时 `h-screen max-md:h-dvh`，embedded 时 `h-full min-h-0`，都是 flex-col overflow-hidden。非 embedded 有 Sidebar（100）。main 101 overflow-y-auto；非 embedded 时手机底部让出 56px + 安全区。粘性头部 102-110：`glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7`，含「回到对话」链接（非 embedded）、h1「分身」、一句话说明。容器 111：`mx-auto max-w-[1040px] px-8 py-6`。状态分支 112-116。主网格 118：`grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_340px]`。左表单 119-151：fieldset 内依次是头像符号（96px）+ 名称（`grid-cols-[96px_minmax(0,1fr)]`）、名片简介 textarea（300 字）、性格与交流方式 textarea（2000 字，标「仅自己可见」）、公开名片开关（label 用 glass-card）；下面是 error、notice、保存按钮 +「有未保存的修改」。右栏 aside 152-157：AgentIdentityCard 预览 →「查看已保存的公开名片」链接（savedAgent.is_public 才有）→ ShieldCheck 说明 → AgentMemoryPanel。
- **样式**：fieldClass 13：`rounded-[6px] border border-[color:var(--border)] bg-card px-3 py-[9px] text-sm focus:border-[color:var(--amber-ink)] disabled:opacity-50`，AgentExchangeWorkspace.tsx:14 有一份完全相同的副本。头部 .glass + inline var(--glass-border)。计数 `.readout` 里加 `<b>`。开关 `accent-[color:var(--primary)]`。链接 `text-[color:var(--amber-ink)]`；ShieldCheck 图标 inline var(--amber-ink)。保存按钮 `btn btn-primary`，重载按钮 `btn btn-quiet`，加载失败块 glass-card。
- **行为（必须保留）**：GET ${API}/agents/me（41）；PUT 同一地址，body 为 display_name/bio/personality/avatar_emoji/is_public（74-81），名称必填（67），owner_username 校验防串号（43、83）。dirty 用 JSON 比较（95），保存按钮在 saving 或 !dirty 时禁用。onSaved 回调更新主页分身（page.tsx:2356 → updateAgent，影响头部名和气泡头像）。按账号 key 重挂载（20-24）。输入上限 maxLength：头像 16、名称 40、简介 300、性格 2000。
- **状态**：未登录（112，带「前往登录」）；加载 role=status；加载失败：glass-card + role=alert + 重新加载；保存中：fieldset 禁用 + spinner「正在保存…」；校验错误「给分身起一个名字再保存。」；成功 notice role=status。
- **手机端**：头部 max-md:px-4 pb-4 pt-4；容器 max-md:px-4 py-4；网格 max-md:gap-6；lg 以下（小于 1024）单列，所以 768-1023 也是单列。aside 用 [&_.echo] 兜溢出。抽屉在手机上是 max-md:left-0、w-screen、bottom 让出 56px 标签栏（page.tsx:2341）。
- **改造风险**：1) 抽屉不是 iframe：组件直接挂在主文档里，max-md 和 lg 按顶层视口算，这是对的。如果改成 iframe，就得换成 globals.css:7-13 的 mobile: 变体加 data-shell。2) embedded 时外层抽屉 .glass 里再套 sticky .glass 头部，两层 backdrop-filter 叠加，嵌入时还有两条标题（抽屉条「分身」和 h1「分身」）。3)「查看已保存的公开名片」是 next/link，在抽屉里点击会把整个主页面导航到 /agents/[id]，离开聊天。4) fieldClass 两份副本要同步改。5) 公开开关的说明文案涉及隐私承诺，要原样保留。

### AgentExchangeWorkspace·广场外壳（头部与五个标签）
- **位置**：components/AgentExchangeWorkspace.tsx:21-144；页面 app/agents/page.tsx:1-5；抽屉 app/page.tsx:2359-2386（section#exchange-drawer，.glass fixed，标题条「分身广场」，`<AgentExchangeWorkspace embedded onOpenMyAgent={() => setDrawer("agent")} />`）；数据 lib/useAgentExchanges.ts:11-127
- **结构**：根 62 data-agent-exchange-workspace，高度规则同 MyAgentWorkspace。main 65 aria-label="分身交流工作区"。粘性 glass 头部 66-75：「回到对话」（非 embedded）、h1「广场」、一句话 +「管理我的分身」（embedded 时是按钮，回调切到分身抽屉；独立页是指向 /agents/me 的 Link，37-39）；右侧「刷新」btn-quiet，加载中图标旋转（73）。容器 77 `mx-auto max-w-[1040px] px-8 py-6`。未登录（78）；目录错误（79）。标签栏 80-87：nav role=tablist aria-label="分身广场分类"，五个 button role=tab aria-selected，依次是单人体验 / 体验记录 / 发现分身 / 收到的邀请（带待处理数）/ 发出的邀请；手机右侧有渐隐的 ChevronRight 提示（86）。记录错误（88）。身份分支（90）：没有 agent 时显示 Loading 或 Empty；有 selected 时显示 ExchangeConversation；否则按 tab 渲染各标签页。
- **样式**：标签按钮 `-mb-px flex h-9 items-center gap-1.5 border-b-2 px-3 text-[13px]`，选中 `border-[color:var(--amber-ink)] text-foreground`，未选中 `border-transparent text-muted-foreground`；tablist 下边框 inline var(--border)；待处理数 `.readout text-[11px]` + color var(--amber-ink)；更多提示 `bg-card border-l`。
- **行为（必须保留）**：tab 状态没有持久化；切换 tab 会调 back()，清空 target 和 selected（83）。pendingCount 只统计非官方、recipient、pending（34）。records 按 tab 过滤（35）。标签溢出提示用 ResizeObserver 加 scroll 监听（43-59）。刷新会依次刷目录、记录、官方搭档（73）。useAgentExchanges：记录每 4s 轮询（102-113）；身份失效时清空私有状态（28-34）；onExchangeChanged 乐观插入后重新拉取（115-122）。按账号 key 重挂载（21-24）。
- **状态**：未登录 EmptyState + 登录链接；目录错误 ErrorNotice + 重新加载；记录错误「交流记录暂未更新：…」；身份确认中「正在确认你的分身身份…」；身份失败「暂时无法确认当前分身身份…」；刷新按钮在 loading 或 officialLoading 时禁用。
- **手机端**：tablist 在 max-md 下横向滚动、不换行、右侧留 pr-7，用 mobile-scrollbar-none 隐藏滚动条（globals.css:422-430，受 data-shell 约束）；头部 max-md:px-4 pt-4 pb-4；刷新按钮 max-md:shrink-0；main 非 embedded 时底部让出 56px + 安全区。
- **改造风险**：1) 和 MyAgentWorkspace 一样：抽屉不是 iframe，内外两层 glass；embedded 时标题重复（抽屉条「分身广场」和 h1「广场」）。2) mobile-scrollbar-none 在 :root:not([data-shell=desktop]) 下才生效，非 iframe 时 data-shell 不存在，等于纯视口判断。3) 标签文字被测试和上一版规格引用（docs/tasks/2026-09-12-frosted-instrument-ui-v2/02-spec.md §6.4），要保持五个标签的 key 和文案。

### 广场·单人体验标签页 + 开始表单（ExchangeStartForm）
- **位置**：AgentExchangeWorkspace.tsx:90-104（单人体验标签页）；ExchangeStartForm 146-211（单人体验和邀请共用）；Participant 439-442
- **结构**：说明一行 91。officialError 92。官方搭档网格 93-103：`mb-6 grid grid-cols-1 gap-3 md:grid-cols-3` role=radiogroup aria-label="选择官方搭档"；每张是 button role=radio aria-checked + data-official-agent，内容为 h3 名称 + `tag`「官方 AI」、bio（line-clamp-3）、模型读数。选中后表单出现在网格下方（104），不替换整页。表单 184-210：「返回单人体验」btn-quiet → 两张 Participant 卡（`grid gap-3 sm:grid-cols-2`，emoji 方块 + 名称 + 标签「你的 AI 分身 / 平台官方 AI · 无真人用户」+ 模型读数）→ form `grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_220px]`。左边话题 textarea（autoFocus、required、`min-h-[150px] resize-y`）+ 计数「n / 10,000」+「使用示例话题」（有 suggested_topic 才出现）；右边回复次数 number input（.readout 字体）+ 帮助文字 → `btn btn-primary h-10 w-full`「开始讨论」（Play 图标）→ 流程说明 → 错误。
- **样式**：搭档卡 glass-card，选中时 `border-[color:var(--amber-ink)]`（97）；`tag`；模型名 `.readout max-md:break-all`；fieldClass；计数 `b.readout`。
- **行为（必须保留）**：官方：POST ${API}/agent-exchanges/official，body {official_agent_id, topic, max_turns}。提交前先 assertAccountAgent 校验身份（166、469-472）；返回后校验 initiator、recipient、viewer_role、是否官方（173），不符抛 ExchangeIdentityError 并触发身份失效。限制：话题最多 10000 字，次数 2-99，默认 99（149-156）。成功后 onCreated：乐观插入、清 target、selected=新交流、tab 切到「体验记录」（104）。按钮禁用条件：busy 或校验不过（205）。textarea autoFocus。
- **状态**：加载「正在加载官方搭档…」；空「暂时没有可用的官方搭档，请稍后刷新。」；错误「官方搭档暂不可用：…」+ 重试；提交中整个 fieldset 禁用，按钮 spinner「正在开始…」；表单错误 ErrorNotice；每日次数限制由后端 429 文案经 errorMessage 显示。
- **手机端**：搭档卡 max-md 单列、min-w-0；Participant 小于 640 单列；表单小于 1024 单列；按钮整宽 h-10。
- **改造风险**：radiogroup 没有方向键漫游，只能 Tab 逐个切换，改造时不要退化成 div。流程说明（206）写明「不读取性格设定、私聊或私有记忆」「每个账号每天可体验的次数有限」，这是隐私和限额承诺，要原样保留。

### 广场·发现分身标签页（gallery）与邀请
- **位置**：AgentExchangeWorkspace.tsx:105-114；邀请表单复用 ExchangeStartForm 146-211（非官方分支）
- **结构**：说明一行 106（未公开时追加「管理我的分身」）。人员网格 107-113：`grid gap-3 md:grid-cols-3`；每张 section 是 `glass-card flex flex-col gap-2.5 p-4`，内有 32px emoji 方块 + h3 名称、bio（空时「这位分身还没有填写简介。」）、`btn self-start`「邀请交流」（Send 图标）。选中后表单出现在网格下方 `mt-6`（114）。邀请表单：Participant「我的 AI 分身 · 发起方 / 对方 AI 分身 · 受邀方」，话题最多 300 字，次数 2-6（默认 6），按钮「发送邀请」。
- **样式**：glass-card、btn、emoji 方块 `rounded-[6px] bg-secondary`，文字 12px muted，leading 1.6。
- **行为（必须保留）**：others 会排除自己（36）。邀请按钮在 !data.agent.is_public 时禁用（111）。POST ${API}/agent-exchanges，body {target_agent_id, topic, max_turns}（168-171）。成功后切到「发出的邀请」（114）。自己未公开时提交被拦（161、205）。
- **状态**：加载「正在寻找公开分身…」；空「最近公开的分身中暂无其他交流对象…」；禁用：自己未公开时邀请按钮禁用。
- **手机端**：max-md 单列网格；表单同上。
- **改造风险**：「邀请需要双方都已公开名片」这类规则说明要保留；卡片名称 break-words。

### 广场·记录列表（体验记录 / 收到的邀请 / 发出的邀请）
- **位置**：AgentExchangeWorkspace.tsx:115-137；StatusBadge 444-446；formatDate 460-467
- **结构**：说明一行 116（三种 tab 文案不同，都带「记录会自动更新」）。表头 118：`grid grid-cols-[minmax(0,1fr)_150px_120px_60px_60px] gap-4 px-2 pb-2 text-[11px]`，颜色 var(--dim)，max-md:hidden；列为话题 / 搭档 / 状态 / 次数 / 时间。每行 121-134 是一个 button，同样的五列网格，`border-b px-2 py-3 text-left text-[13px] hover:bg-card`，data-exchange-id。手机上换成两行：第一行话题，第二行是 127-133 的「搭档 · 状态 tag · 次数 · 时间」，带 sr-only 前缀「搭档：/状态：/次数：/时间：」。
- **样式**：StatusBadge：基础 `tag shrink-0`；failed 用 tag-rec；pending/running 用 tag-amber；running 时加 Loader2 旋转；draft_review 完成后显示「AI 审稿通过 · 待你验收 / 已结束 · 草稿」，其余用 exchangeStatusLabel（lib/agentExchanges.ts:66-69）。次数和时间 `.readout text-right`。表头颜色 var(--dim)。
- **行为（必须保留）**：点击行 setSelected(exchange) 进入详情（121），这时 tab 不变。formatDate：今天显示 HH:mm，否则 MM/DD，兼容 SQLite 不带时区的串。数据每 4s 轮询刷新。
- **状态**：加载「正在加载交流记录…」；三种空态文案（117）；记录错误条在 88。
- **手机端**：max-md:grid-cols-1 gap-1；隐藏表头和桌面列，显示 127-133 的手机行。
- **改造风险**：列宽固定 150/120/60/60，换宋体后中文更宽，可能截断搭档名（已有 truncate）。手机行的 sr-only 标签是无障碍补偿，要保留。

### 广场·交流过程视图（ExchangeConversation）
- **位置**：AgentExchangeWorkspace.tsx:213-342；stageLabel 344-346；ExchangeTopic 428-437
- **结构**：section 293 `flex flex-col gap-6` data-exchange-detail。返回按钮 294：文案为「体验记录 / 收到的邀请 / 发出的邀请」。标题区 295-305：h2 取话题前 40 字；meta 行包括我方名 + 模型读数、对方名 + 模型读数、读数「第 <b>n</b> 次 / max」；右侧 StatusBadge。阶段条 306-311（只在 workflow=draft_review_v1 时出现）：inline-flex 三段「主创初稿 / 官方审稿 / 主创修订」，已有对应 stage 的消息时加琥珀 Check、文字转前景色，相邻段之间 border-l。完整话题 ExchangeTopic 312：300 字以内直接显示；超过时 line-clamp-4，再加 details（glass-card），展开后是可滚动的 region。待处理说明 313。待处理按钮 314-317：受邀方有「接受并开始交流」btn-primary 和「拒绝邀请」btn-quiet，双方都有「取消这次邀请」btn。错误 318。运行中粘性条 319-322：`glass sticky top-0 z-[2] -mx-8 px-8 py-2`，内容为说明 +「查看最新回复」btn-quiet +「停止交流」btn。作品区 323（workflow 时）。免责说明 324。消息流 325-334：role=region aria-label="双分身交流消息"，aria-busy=running；每条 article 是 `grid grid-cols-[28px_minmax(0,1fr)] gap-3`，data-exchange-message，左边序号读数，右边一行名字 + 阶段 tag +「你的 AI 分身 / 平台官方 AI / 对方 AI 分身」，下面正文 13px、line-height 1.75、pre-wrap。消息空态 333。总结 335：glass-card p-4，标题为「创作说明」或「交流总结 · AI 生成」。非 workflow 时文档区单独一块（336）。结束态 337-340。
- **样式**：阶段条外框 `rounded-[6px] border`，颜色 var(--glass-border)；Check 用 var(--amber-ink)；粘性条 .glass；`tag` 阶段标签；`.readout` 序号和次数；ErrorNotice 是 `glass-card` + `text-destructive`。
- **行为（必须保留）**：详情轮询：GET ${API}/agent-exchanges/{id}，只在 pending/running 时每 3s 一次（249-259），mutating 期间不拉。操作：POST …/{id}/accept|reject|stop（261-281）；官方交流只允许 stop（263）；每次先 assertAccountAgent。归属校验 exchangeBelongsTo（240、272）。401/403/404 或身份错误时清空详情，置 unavailable，身份错误还会 onIdentityInvalid（225-232）。「查看最新回复」用 messagesRef.scrollIntoView({block:"end"})（321）。onChanged 同步列表。
- **状态**：不可访问（283）：ErrorNotice +「返回交流记录」。加载 LoadingState「正在读取交流详情…」。pending：说明 + 操作按钮（busy 时禁用，当前按钮显示 spinner）。running：粘性条 + 消息区 aria-busy；没有消息时「分身正在准备第一条回复…」。failed：ErrorNotice（用后端 error 或默认文案）。stopped / rejected：EmptyState 文案。结束后（非 running 且非 pending）：禁用的「停止交流」+「已结束，记录仅你可见」（340）。轮询或操作错误：「交流暂未更新：…」+ 重新加载（busy 时不给重试）。
- **手机端**：标题区 max-md:flex-col gap-2；名字和模型 max-md:break-all；阶段条 max-md:w-full，三段 flex-1 居中、px-1 不换行；粘性条 max-md:-mx-4 px-4 flex-col items-start gap-2。
- **改造风险**：1) 粘性条 -mx-8 和 max-md:-mx-4 与容器 px-8 和 max-md:px-4（77 行）耦合，改容器内边距必须同步。2) 粘性条和页面头部（66 行）都是 sticky top-0 z-[2]，在同一个滚动容器 main 里，滚动后会互相重叠（现状）。改头部高度或玻璃效果时要明确谁盖谁。3) 消息区没有 aria-live，只有 aria-busy；轮询追加消息时不会自动滚动。4) 免责文案（324）、「不代表真人即时发言」属于 AI 身份披露，要原样保留。

### 广场·当前作品与文档交付（ExchangeArtifact / ExchangeDocuments）
- **位置**：AgentExchangeWorkspace.tsx:352-365（作品）、367-426（文档）、348-350（completionLabel）
- **结构**：作品 section 356 是 glass-card，aria-label="当前作品"，data-exchange-artifact。头行 357-360：b「当前作品」+ 读数「n 字」+ tag（审稿通过时用 tag-amber「审稿通过，待你验收」，否则「待修订 / 草稿」）。下面依次是完成原因 361（12px muted）、稿件 362（role=region tabIndex=0，`max-h-[36rem] overflow-y-auto`，p-4，13px，line-height 1.8，select-text；没有稿件时显示占位文案）、children（嵌入的 ExchangeDocuments）。文档区 416-425：embedded 时 `border-t p-3`，否则单独一块 glass-card p-4；一行说明，然后按钮依次为「作品 Markdown」（只在 workflow 时出现）、「README.md」、「完整讨论」，都是 `btn max-w-full` + Download 图标；下面是下载中状态和错误。
- **样式**：glass-card；头行下边框 var(--glass-border)；tag/tag-amber；`.readout`；稿件焦点环 `focus-visible:ring-[color:var(--ring)]`；按钮 btn。
- **行为（必须保留）**：下载：GET ${API}/agent-exchanges/{id}/export?document=readme|discussion|artifact，cache no-store（384）。校验 Content-Type 必须是 text/markdown（390）；生成 blob 链接下载，文件名 README.md 或 {kind}-{id}.md，1s 后 revoke（393-404）。activeDownload 防止并发；401/403/404 时交给 onAccessError。是否为草稿快照用 isArtifactApproved 判断（373，lib/agentExchanges.ts:89-93）。
- **状态**：作品占位三种（362）：正在读取已保存稿件 / 主创正在准备初稿 / 尚未保存稿件。下载中 role=status「正在下载…」。按钮在未就绪、正在下载，或作品按钮在稿件为空时禁用。错误 ErrorNotice。
- **手机端**：没有专门断点，按钮 flex-wrap、max-w-full。
- **改造风险**：稿件区是可聚焦的 region，有键盘滚动语义，要保留 tabIndex 和 aria-label。

### app/agents/[id]·公开名片页 与 app/agents/page、me/page 组合
- **位置**：app/agents/[id]/page.tsx:1-56；app/agents/page.tsx:1-5；app/agents/me/page.tsx:1-5
- **结构**：[id]：根 32 `flex h-screen flex-col overflow-hidden max-md:h-dvh`，Sidebar + main（max-md 底部让出 56px + 安全区）。粘性 glass 头部 35-42：「我的分身」返回 /agents/me，h1「分身名片」。容器 43 `mx-auto max-w-[560px] space-y-5 px-8 py-6`，带 [&_.echo] 溢出兜底。三态 44-46。Suspense fallback 55。/agents 和 /agents/me 只是直接渲染非 embedded 的工作区组件。
- **样式**：同广场外壳：glass 头部、glass-card 错误块、错误文字 `text-[color:var(--rec)]`、`btn btn-quiet`。
- **行为（必须保留）**：GET ${API}/agents/{id}（26），按 owner:id key 重挂载（16），retry 计数器（21、46）；useParams 取 id。
- **状态**：未登录（带登录链接）；加载 role=status；错误 role=alert + 重新加载；成功渲染 AgentIdentityCard（不是预览模式）。
- **手机端**：max-md:px-4 py-4，头部 max-md:px-4 pb-4 pt-4，底部让出 Sidebar 标签栏。
- **改造风险**：三个独立页都自带 Sidebar（components/Sidebar.tsx：桌面 84 行 aside w-14 max-md:hidden；手机 183 行 fixed 底部标签栏 md:hidden h-[calc(56px+safe-area)]）。如果把导航改成竖排书签，这三个页面和主页的布局要一起改。

### app/community/page.tsx·社群占位页
- **位置**：app/community/page.tsx:1-40
- **结构**：根 11 `flex h-dvh flex-col overflow-hidden`，非 embed 时 `mobile:pb-[calc(56px+env(safe-area-inset-bottom))]`。embed=1 时不渲染 Sidebar（9、13）。粘性 glass 头部 15-22：h1「社群」+「发现志同道合的人」。正文 23-27：居中的 glass-card p-8「社群功能即将上线」。整页包在 Suspense 里（因为用了 useSearchParams）。
- **样式**：glass、glass-card、var(--glass-border)；用的是 iframe 感知的 mobile: 变体（globals.css:7-13），不是 max-md:。
- **行为（必须保留）**：只读 searchParams 的 embed，没有 API 调用。
- **状态**：只有占位态。
- **手机端**：mobile:px-4 pt-4；底部让出 56px。embed=1 且在 iframe 里时，layout.tsx:30-58 的脚本按父窗口断点设置 html[data-shell=desktop]，mobile: 变体随之失效。
- **改造风险**：没有任何入口：Sidebar navItems（components/Sidebar.tsx:13-19）里没有 /community，page.tsx 的 iframe 只指向 /plaza 和 /match（page.tsx:2419），全库也没有链接。它和 /agents 系列用的断点变体不一样（mobile: 对 max-md:）。

### 跨区域要点
- 令牌和类的单一来源是 app/globals.css：浅色令牌在 :root 55-112，深色在 .dark 115-164（--amber-ink/--dim/--rec/--rec-soft/--glass/--glass-strong/--glass-border/--glass-hi/--fill/--grain/--shadow/--spot-a/b/c/--bubble-*）。body 三光斑背景 168-178；.glass 183-189（blur 22px）；.glass-card 192-200（blur 14px，自带 1px 边框和 10px 圆角）；.readout 203-209（mono 12px，b 为前景色）；.echo 212-231；.signal 234-236；.state-dot 239-241；.btn/.btn-primary/.btn-quiet/.btn-danger 244-258；.chip/.chip-on 259-264；.tag/.tag-amber/.tag-rec 265-270；.bubble-user/.bubble-ai 273-281；.typing-cursor 317-327；.msg-in-left/right 329-341。不透明退路已经存在：@supports not (backdrop-filter) 在 284-286，prefers-reduced-transparency 在 287-289，都回到 var(--card)。「素瓷」退路可以在这两处扩展。
- 本次负责的所有文件里没有一个 dark: 变体，也没有 hud-* 类（hud-like-burst/pop 在 globals.css:291-315，只给 plaza 用）。主题切换完全靠令牌。主题源是 html 的 .dark 类：layout.tsx:28 写死 className="dark"；lib/useTheme.ts 只做 classList.toggle，不持久化；globals.css:5 是 `@custom-variant dark (&:is(.dark *))`；layout.tsx:16 的 themeColor 写死 #0E1219。改成昼天青/夜建盏两套时，这四处要一起定。
- Tailwind 任意值颜色出现在这些写法里：text-[color:var(--amber-ink)]、border-[color:var(--amber-ink)]、ring-[color:var(--amber-ink)]、focus:border-[color:var(--amber-ink)]、text-[color:var(--rec)]、hover:text-[color:var(--rec)]、border-[color:var(--border)]、accent-[color:var(--primary)]、focus-visible:outline-[color:var(--ring)]、focus-visible:ring-[color:var(--ring)]。另外 inline style 大量使用 borderColor var(--glass-border)、background/color var(--amber-ink)、color var(--dim)、borderColor var(--border)。写死的颜色和透明度有：GeneratedImage.tsx:164 backdrop:bg-black/75；page.tsx 遮罩 bg-black/20（2097、2104）；抽屉阴影 rgba(0,0,0,0.28)（2044、2345、2376）；ChatScrollArea.tsx:139 bg-background/95；ChatBubble 的 text-muted-foreground/50、text-foreground/90。只改令牌值会漏掉这些写死项。
- 断点有两套：抽屉内的 MyAgentWorkspace 和 AgentExchangeWorkspace（page.tsx:2356、2385）是直接挂载、不是 iframe，所以用 max-md:/md:/lg:，按顶层视口计算。community 用 iframe 感知的 mobile: 变体（globals.css:7-13），配合 layout.tsx:30-58 的 embed=1 脚本，按父窗口 768px 设置 html[data-shell=desktop]；mobile-scrollbar-none 和手机输入框 16px 字号（globals.css:415-431）也受 data-shell 约束。真正走 iframe 的只有世界抽屉的 /plaza?embed=1 和 /match?embed=1（page.tsx:2419）。
- 导航宽度耦合：桌面 Sidebar 是 56px（w-14），手机是底部 56px 标签栏加安全区。56px 写死在 page.tsx（history left-14 在 2043/2097；抽屉宽 calc(100vw - 56px) 在 2343/2374；世界抽屉 2396；手机 bottom calc(56px+env(safe-area-inset-bottom)) 在 2043/2097/2104/2106/2173/2190/2341/2372/2391）和各独立页的 main 底部 padding（MyAgentWorkspace.tsx:101、AgentExchangeWorkspace.tsx:65、agents/[id]/page.tsx:34、community/page.tsx:11）。改成竖排书签导航时这些数字都要改。
- 抽屉动画是 transform translateX(105%↔0)，360ms cubic-bezier(.22,.61,.36,1)（page.tsx:2346-2347、2377-2378）。手机对话列表用 animate-in slide-in-from-left duration-300（tw-animate-css）。globals.css:460-467 的全局 reduced-motion 把所有 CSS 动画和过渡清零；Signal 和 useTypewriter 的 RAF 不受它影响，Signal 自己判断 reduced-motion，打字机不判断。
- 玻璃叠加：抽屉 section 是 .glass，里面工作区的 sticky 头部又是 .glass，交流详情的运行条也是 .glass，ErrorNotice、作品、总结、搭档卡是 .glass-card，层层 backdrop-filter。若玻璃改为 backdrop-filter:url(#lens) 的 SVG 边缘透镜，只有 Chromium 支持，Safari/WebKit 和 Firefox 需要退路；而且 overflow-hidden 加圆角的卡片（GeneratedImage 根、天气卡、网页卡、NewsCardContent 根、作品 section）会裁掉滤镜溢出。
- 必须原样保留的文案（被后端或文档引用，或属于 AI 身份披露和隐私承诺）：「以此图修改」「加入参考」「已选为图N」（backend persona.py:51、intent_router.py:79、routers/chat.py:140/146、services/chat_service.py:607/1096、README.md:116）；「AI 分身」「由用户创建的人工智能分身」「官方 AI」「平台官方 AI · 无真人用户」「交流总结 · AI 生成」；交流免责说明（AgentExchangeWorkspace.tsx:324）；开始表单的流程和隐私说明（206）；公开开关说明（MyAgentWorkspace.tsx:139）；记忆清空的确认文案（AgentMemoryPanel.tsx:60）。
- 要保留的 data 属性和 ARIA 钩子：data-chat-scroll-area/viewport/content（ChatScrollArea.tsx:116-136）；data-chat-panel（page.tsx:2111）；data-chat-composer（2191）；data-agent-exchange-workspace（62）；data-official-agent（97）；data-exchange-id（121）；data-exchange-detail（293）；data-exchange-message（326）；data-exchange-artifact（356）。全库搜索目前没有 JS 消费者，只有上一版规格 docs/tasks/2026-09-12-frosted-instrument-ui-v2/02-spec.md 用它们做结构判据。ARIA 包括 role=tablist/tab、radiogroup/radio、listbox/option、region（聊天消息、双分身交流消息、完整作品稿件、完整讨论话题）、status、alert，以及 aria-busy、aria-selected、aria-checked、aria-modal。
- 共享类型和组件耦合：Message/CardData/ImageGenerationRetry/ImageModelId 从 ChatBubble 导出，被 app/page.tsx:5、lib/useConversations.ts:4、NewsCardContent.tsx:5 引用。GeneratedImage 被聊天、输入区（page.tsx:2216，compact）、历史页（app/history/page.tsx:343、345）三处复用。app/history/page.tsx:335-351 手抄了气泡和说话人行。fieldClass 在 MyAgentWorkspace.tsx:13 和 AgentExchangeWorkspace.tsx:14 各有一份。AgentIdentityCard 和 .echo 还被 login 页（app/login/page.tsx:144、146 也用 Signal）引用。
- 账号隔离和轮询不能动：所有工作区组件按 useAccountIdentity() 的 owner 做 key 重挂载，每次请求经 useAccountRequest 校验 isCurrent（lib/useAccountIdentity.ts:27-58）；广场记录 4s 轮询（lib/useAgentExchanges.ts:102-113）；详情 3s 轮询（AgentExchangeWorkspace.tsx:249-259）；写操作前 assertAccountAgent（469-472）。改结构时不能把这些组件的挂载点移到会跨账号复用的位置。
- 现有死代码和缺口（复刻对照表里应注明）：NewsCardContent 没有任何 import；ChatBubble 的 isDivider 分支没有任何地方会设；静音按钮只切本地图标；删除按钮只在 hover 时出现（手机和键盘不可达）；生成图卡目前不显示模型名，刷新后 generatedImage（宽、高、模型）全部丢失；/community 没有入口；消息列 page.tsx:2176 没有 mx-auto，靠左，而输入区 2191 是居中的。

## system：样式系统与外壳（Fiona/frontend @ 586d86a，工作区干净）：app/globals.css、app/shadcn-tailwind.css、app/layout.tsx、app/manifest.ts、components/Sidebar.tsx、components/ui/*、lib/useTheme.ts 与调用处、lib/utils.ts、lib/usePrefersReducedMotion.ts、components/Signal.tsx、components/PwaRegister.tsx、public/*、主页面抽屉外壳（app/page.tsx:2023-2474）、各页 embed=1 外层包装；附全局类、硬编码颜色、font-mono/readout 的全仓库统计（只统计 app/ components/ lib/ 下的 .ts/.tsx，计数只算字符串字面量里的出现）
### 颜色/字体令牌层（:root 浅色、.dark 深色）
- **位置**：app/globals.css:54-164（:root 55-112；.dark 115-164）
- **结构**：两套令牌。:root（浅色）56-57 字体栈：--font-sans-stack = -apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",system-ui；--font-mono-stack = ui-monospace,"SF Mono",Menlo…。59-85 是 shadcn 语义令牌（background #F3F5F8 / foreground #141A22 / card #FFF / primary #F2A63A / primary-foreground #2A1A05 / secondary=muted=input #EEF1F5 / muted-foreground #64707E / accent rgba(242,166,58,.18) / accent-foreground=ring=#9E6209 / destructive #E04553 / border #DDE3EA / radius .625rem / sidebar-* 系列）。88-91 自定义：--amber-ink #9E6209、--dim #8B96A3、--rec #E04553、--rec-soft。94-100 玻璃：--glass rgba(255,255,255,.58)、--glass-strong .8、--glass-border rgba(20,26,34,.09)、--glass-hi、--fill、--grain（内联 data-URI SVG feTurbulence 噪点，浅色版 alpha .05）、--shadow。103-105 底场光斑 --spot-a/b/c。108-111 --bubble-user/-text、--bubble-ai/-text。.dark 116-163 覆盖同名令牌（background #0E1219、card #151B24、popover/secondary/input #1B222D、border #232B36、primary 仍 #F2A63A、--amber-ink #F2A63A、--dim #586270、--rec #FF5A66、--glass rgba(21,27,36,.6)、--glass-strong .76、--glass-hi rgba(255,255,255,.05)、--grain 白噪点 alpha .07）。字体栈只在 :root 定义，.dark 不覆盖。
- **样式**：琥珀色 #F2A63A 在 globals.css 出现于 65,80,122,129,133,136,139,141,143 行，rgba(242,166,58,…) 在 71,82,103,128,138,156,158 行；#9E6209 在 72,76,83,85,88。TSX 端只消费这些变量：var(--amber-ink) 73 次、var(--glass-border) 68 次、var(--rec) 18、var(--ring) 5、var(--foreground) 4、var(--border) 4、var(--fill) 3、var(--rec-soft) 2、var(--dim) 2、var(--primary) 1、var(--accent) 1、var(--composer-height) 1（page.tsx:2173-2174 运行时注入）。--glass/--glass-strong/--glass-hi/--grain/--shadow/--spot-*/--bubble-* 只在 globals.css 内部用。Tailwind 语义类用量（ui/ 除外）：text-muted-foreground 179（+各透明度变体 12）、text-foreground 36（+透明度变体 19）、bg-secondary 28（+/40 /50 /60 共 4）、bg-card 14、text-destructive 7、border-border 6、text-primary-foreground 3、bg-primary 2、bg-border 2、bg-sidebar 1、bg-background 1、bg-background/95 1、bg-destructive 1、bg-destructive/10 1、ring-primary/40 1、outline-primary 1。任意值写法：text-[color:var(…)] 44、border-[color:…] 16、ring-[color:…] 4、bg-[color:…] 3、outline-[color:…] 2。
- **行为（必须保留）**：无运行时行为；主题切换靠 html 上的 .dark 类选择令牌（见主题区域）。--composer-height 由 page.tsx 用 ResizeObserver 类逻辑写入 inline style，令牌改名时这一个不能动。
- **状态**：禁用色：--dim 只用于发送按钮禁用文字（page.tsx:2311 disabled:text-[color:var(--dim)]）和 AgentExchangeWorkspace.tsx:118。错误色 --rec/--rec-soft、destructive 两套并存（--rec 用于草莓余额<30、录音中、删除按钮、错误文本；destructive 用于 text-destructive 7 处）。
- **手机端**：令牌无断点差异。
- **改造风险**：1) 设计改为昼天青/夜建盏两套主题时，--amber-ink 这个名字被 73 处 TSX 直接引用、--glass-border 被 68 处 inline style 引用，保留变量名只改值改动面最小，改名就得动 18 个文件。2) primary 和 amber-ink 在深色下同为 #F2A63A，浅色下分开（primary #F2A63A 作底、amber-ink #9E6209 作字）；文字对比度靠这个分工，新配色要保留“底色令牌/文字令牌”两个令牌。3) 没有声明 color-scheme（全仓 grep 无），深色下原生 date 输入（history/page.tsx:219,226）和 checkbox（MyAgentWorkspace.tsx:140）按浅色 UA 样式渲染。4) sidebar-* / popover / chart 类令牌只给 components/ui 和 bg-sidebar（Sidebar.tsx:84）用。

### Tailwind 主题映射与自定义变体（dark / mobile / shadcn 变体）
- **位置**：app/globals.css:1-52；app/shadcn-tailwind.css:1-98；components.json
- **结构**：globals.css:1-3 依次 @import tailwindcss、tw-animate-css、./shadcn-tailwind.css。:5 `@custom-variant dark (&:is(.dark *))`：只匹配 .dark 的后代，不含 html 自身。:7-13 `@custom-variant mobile`：`@media (width < 48rem)` 且 `&:where(:root:not([data-shell="desktop"]) *)`，即 iframe 里如果父窗口是桌面宽度就不触发。:15-52 `@theme inline` 把 --color-* 映射到令牌，--font-sans/--font-mono/--font-heading 映射到字体栈（font-heading 全仓未使用），--radius-sm..4xl 由 --radius 推导。shadcn-tailwind.css:5-29 accordion keyframes；31-89 data-open/closed/checked/unchecked/selected/disabled/active/horizontal/vertical 变体；91-98 @utility no-scrollbar。components.json style "base-nova"、baseColor neutral、css 指向 app/globals.css。
- **样式**：断点用法分两派：`mobile:` 共 146 次，只出现在可被 iframe 嵌入的页面（plaza 55、match 49、settings 22、profile 16、community 4）；`max-md:` 共 288 次，出现在不进 iframe 的地方（page.tsx 114、history 55、AgentExchangeWorkspace 43、GeneratedImage 24、MyAgentWorkspace 13、ChatBubble 10、ConversationPicker 10、agents/[id] 10、login 7、ChatScrollArea 1、Sidebar 1）。`md:` 只有 8 次（page.tsx 3、AgentExchangeWorkspace 2、ConversationPicker 1、Sidebar 1，加 ui 2）。plaza 和 NewsCardContent 里还有 `sm:`（plaza:404 sm:grid-cols-3，NewsCardContent:114,172 sm:px-8），它们按 iframe 自己的宽度响应。
- **行为（必须保留）**：`dark:` 变体只在 components/ui/*（未被使用）里出现；shadcn 的 data-* 变体和 no-scrollbar 工具类在 ui/ 之外零使用。
- **状态**：无。
- **手机端**：`mobile:` 与 `max-md:` 都在 768px 切换（48rem 假定根字号 16px），区别只在 iframe 内是否看 data-shell。
- **改造风险**：1) 新外壳里任何会在 iframe 抽屉（/plaza、/match、/settings、/profile ?embed=1）中渲染的样式必须用 `mobile:` 而不是 `max-md:`，否则桌面上 1024px 窗口的 iframe（宽约 645px）会误切到手机布局。2) dark 变体选择器是 `.dark *`，改成 data-theme 方案（如 [data-theme=night]）时要同步改这一行和 scrollbar 的 .dark 选择器（globals.css:395-413）。3) 删除 shadcn-tailwind.css 会让 components/ui 里的类失效，但这些组件当前没人引用（见 ui 区域）。

### 底场背景（body 光斑）
- **位置**：app/globals.css:166-179；app/layout.tsx:60
- **结构**：@layer base：`* { @apply border-border outline-ring/50 }`（167），给所有元素默认边框色和焦点描边色。body（168-178）：text-foreground、font-family var(--font-sans-stack)、三层 radial-gradient（--spot-a 左上 1100×700、--spot-b 右下 900×800、--spot-c 中部 700×500）叠在 var(--background) 上，`background-attachment: fixed`。layout.tsx:60 body className="h-full antialiased"，html className="dark h-full"。
- **样式**：--spot-a/b/c（globals.css:103-105 浅色，156-158 深色）。没有任何 SVG 背景插画或 fixed 背景层元素，背景全在 body 上。
- **行为（必须保留）**：无 JS。
- **状态**：无。
- **手机端**：同一套背景；iOS 上 background-attachment:fixed 实际按 scroll 处理。
- **改造风险**：1) 每个 iframe 抽屉是独立文档，自己的 body 也会画一份不透明背景（--background 实色），父页面背景透不进 iframe。“背后一幅烟雨平远 SVG”要在 iframe 页里也出现，否则抽屉内是纯色；fixed 背景在 iframe 里按 iframe 视口定位，和主窗口背景对不齐。2) .glass/.glass-card 的 backdrop-filter 只能模糊同一文档里的内容。

### .glass / .glass-card 磨砂玻璃及降级
- **位置**：app/globals.css:181-200（组件层），284-289（降级）
- **结构**：.glass（183-189）：background-color var(--glass-strong) + background-image var(--grain) + backdrop-filter blur(22px) saturate(1.5)（带 -webkit-）+ box-shadow inset 0 1px 0 var(--glass-hi), var(--shadow)。没有边框和圆角，边框靠各处 `border-*` 工具类加 inline borderColor var(--glass-border)。.glass-card（192-200）：var(--glass) + grain + blur(14px) saturate(1.5) + 1px solid var(--glass-border) + border-radius 10px + 同样的阴影。降级：`@supports not (backdrop-filter: blur(1px))` → 背景改为 var(--card)、去掉 grain（284-286）；`@media (prefers-reduced-transparency: reduce)` → 关掉 backdrop-filter，背景 var(--card)（287-289）。两段降级都没有放进 @layer。
- **样式**：.glass 25 处：Sidebar.tsx:84（桌面导航，还带 bg-sidebar 覆盖底色）、183（手机底栏）；ConversationPicker.tsx:43；page.tsx:2043（当前对话记录抽屉）、2113（聊天头部）、2190（输入区 footer）、2341/2372/2391/2428（分身、分身广场、世界、设置四个右抽屉）；页面标题栏 agents/[id]:35、community:15、settings:132、profile:93、MyAgentWorkspace:102、AgentExchangeWorkspace:66；history:148（头部）、189（侧栏）；login:149（登录卡，加 rounded-[10px] border）；match:398（输入区）；plaza:419（热点话题抽屉，+topic-drawer-in）、520（底部 ticker 条）、591（上传弹窗）；AgentExchangeWorkspace:319（运行中吸顶条）；GeneratedImage:164（原生 dialog 大图）。.glass-card 30 处：settings 143/175/217；match 60（叠加 cloud-card）、315、344；agents/[id]:46（错误卡）；page.tsx:178（匹配浮卡）；profile 33/108/126/153；plaza 59（帖子卡）、160（分类卡）；community:24；history:300；MyAgentWorkspace 113/138；AgentIdentityCard:6；ChatBubble 229/257（天气/新闻卡）；NewsCardContent:113；AgentExchangeWorkspace 97/108/335/356/416/432/449。
- **行为（必须保留）**：纯 CSS。
- **状态**：降级态 = 实色 var(--card) 卡片，这是现成的“素瓷”挂点，但目前只能被系统设置（不支持 backdrop-filter 或减少透明度）触发，没有用户开关。
- **手机端**：无断点差异；手机上抽屉依旧 .glass。
- **改造风险**：1) 层级：.glass/.glass-card 在 @layer components 里，会被任意 Tailwind 工具类覆盖。例如 Sidebar.tsx:84 的 bg-sidebar 实际覆盖了 --glass-strong 底色；login:149、plaza:419/591、GeneratedImage:134/164、NewsCardContent:113 另加了 rounded-[10px] border。而 284-289 的降级没有分层，优先级高于所有工具类。2) 嵌套 backdrop：右抽屉（.glass，有 backdrop-filter）里面还有 .glass 标题栏和 .glass-card，内层的模糊只能采样到抽屉自身内容（backdrop root）。“边缘透镜 SVG 滤镜”放在内层时同样受这个限制。3) backdrop-filter: url(#svg) 只有 Chromium 支持，Safari/WebKit 不支持，必须走现有的 @supports 降级路径。4) inline style 的 borderColor var(--glass-border) 共 68 处，分散在 18 个文件。5) 四个右抽屉的 inline boxShadow rgba(0,0,0,.28)（page.tsx:2044,2345,2376,2398,2435）写死在 JSX 里。

### .readout / .echo / .signal / .state-dot
- **位置**：app/globals.css:202-241；components/Signal.tsx:1-98
- **结构**：.readout（203-209）：mono 字体栈、tabular-nums、12px、muted-foreground，`.readout b` 用 foreground 400 字重。.echo（212-231）：相对定位 inline-block，::after 用 attr(data-text) 生成一份偏移 .14em/.12em 的副本，1px -webkit-text-stroke var(--amber-ink)，opacity .6，z-index -1（需要 isolation:isolate）。.signal（234-236）：svg 宽 100%、高 40px、path 描边 amber-ink 1.5（non-scaling-stroke）、circle 填 amber-ink。.state-dot（239-241）：6px 圆点，默认 --dim，-listening 用 --rec，-speaking 用 --primary。
- **样式**：.readout 共 47 处：Sidebar:158（草莓余额）；page.tsx:2167（手机头部草莓余额）、2319（“10”颗）；history 153,182,222,229（两个 date 输入框整体用 readout）,257,258,271,310,350；login:245；plaza 119（anon_id）,122（时间）,128（点赞数）,206,215,556（ticker 用户名 9px）；settings:195（用户名）；AgentExchangeWorkspace 83,100（模型名）,125,126,131,132,194×2,201（number 输入框）,299,300,301,327,359,441；AgentIdentityCard:9（作用在中文“名片预览/分身名片”上，违反 151-202 行注释“永远不给中文标签”）；AgentMemoryPanel:85；ChatBubble 235（天气温度 inline fontSize 32）,238×2,245,317（时间）；ConversationPicker:74（相对时间）；MyAgentWorkspace 127,132,136（字数计数）；NewsCardContent:136（序号 01..）。font-mono 工具类只有 2 处：login:161（邀请码输入 tracking-[0.2em]）、login:221（6 位验证码 tracking-[0.3em]），两处都用 placeholder:font-sans。没有 tabular-nums/font-serif/fontFamily 的其他用法。.echo 元素只有 2 处：login:144（“Chloe” 44px）、AgentIdentityCard:13（名字不超过 12 字时用 40px，超过则改用 28px 普通字）；另有后代选择器 `max-md:[&_.echo]:max-w-full/overflow-hidden/break-all` 在 agents/[id]:43、MyAgentWorkspace:152。.signal 只经 Signal.tsx:89 使用。.state-dot 2 处：page.tsx:2130（聊天头部，随 signalMode 切换 -listening/-speaking）、plaza:444（话题加载中，固定 -speaking）。
- **行为（必须保留）**：Signal.tsx：props mode: "idle"|"listening"|"speaking"；每次挂载用 Math.random 生成相位（19-20）；requestAnimationFrame 循环（76-84）把 140 点正弦叠加写进 path d，level 平滑趋近目标（idle 0 / listening .5 / speaking .9）；idle 且 level<.02 时一个小圆点自左向右扫过（67-73）。prefers-reduced-motion 时画静态直线并隐藏圆点（33-40）。svg aria-hidden、viewBox 0 0 1000 40、preserveAspectRatio none。调用方：page.tsx:2127（mode=signalMode，signalMode 定义于 page.tsx:1978：recording||inlineRecording→listening，isLoading→speaking，否则 idle）；login:146（mode="idle"）。page.tsx:2131 状态文字“正在听/正在说/待命”（手机隐藏）。
- **状态**：三态 idle/listening/speaking；减弱动态时为静态直线。
- **手机端**：page.tsx:2127 手机上 Signal 占头部第二行（max-md:col-span-2 row-start-2 h-6，头部 grid-rows-[56px_24px]，2113），桌面在头部中间列。
- **改造风险**：1) “远山语音状态线”替换 Signal 时，必须保留 mode 三态接口、两个调用点，以及减弱动态降级（注意 globals.css:460-468 只能停 CSS 动画，停不了 rAF，所以 Signal 自己判断了 matchMedia）。2) .readout 的字体来自 --font-mono-stack，换成宋体系统后，凡依赖等宽对齐的地方（AgentExchangeWorkspace:125-126 的表格列、history 日期）都会变。3) .echo 依赖 data-text 与正文一致，改名字渲染时两处都要同步。

### .btn* / .chip* / .tag* 控件类
- **位置**：app/globals.css:243-270
- **结构**：.btn（244-250）：inline-flex、高 34px、padding 0 14px、圆角 6px、1px 边框 color-mix(border 60%, muted-foreground)、背景 var(--card)、13px、hover 边框变 muted-foreground（251）、:disabled opacity .45 + not-allowed（252）。.btn-primary（253-254）：底 primary、字 primary-foreground、500 字重、hover brightness(1.06)。.btn-quiet（255-256）：无底无边、muted 字，hover 用 secondary 底。.btn-danger（257-258）：--rec 字，hover --rec-soft 底。.chip（259-263）：高 28px、padding 0 10px、圆角 6、border var(--border)、12px muted 字，hover 变 foreground。.chip-on（264）：amber-ink 字和边，accent 底。.tag（265-268）：高 20px、padding 0 7px、圆角 4、11px、边框 border；.tag-amber（269）：无边、accent 底、amber-ink 字；.tag-rec（270）：rec-soft 底、rec 字。
- **样式**：btn 73 次（行内出现）：agents/[id]:46；history 169,178,234,291；login 171,200,231,238,255,272；match 125,129,139,143,411；page.tsx 2118,2195,2198,2205,2209,2290,2295,2304；plaza 174,186,434,572,601,646；profile:161（作用在 <Link>）；settings 166,183,207；AgentExchangeWorkspace 73,111,185,196,205,283,294,315×2,316,321×2,340,419,420,421,449；AgentMemoryPanel 91,94,95；ChatBubble 287,296,303；ConversationPicker 51,55,93,101；GeneratedImage 142,152,153,157,171,172,173；MyAgentWorkspace 115,146；NewsCardContent 121,152,173。btn-primary 11：login 171,200,231；match 129,143,411；plaza 572,646；AgentExchangeWorkspace 205,315；MyAgentWorkspace 146。btn-quiet 48 次（上述 btn 行中的大部分）。btn-danger 3：settings 183,207；AgentMemoryPanel 95。chip 22：history 199,253,272,274；match 103,330；page.tsx 2017,2133,2148,2257,2262,2268,2271,2280,2407,2408,2444,2445；plaza 536,632；profile 45；settings 153。chip-on 16：history 201,254；match 331；page.tsx 2017,2133,2148,2257,2262,2268,2271,2407,2408,2444,2445；plaza 632；settings 153。非按钮元素上的 chip：match:103、page.tsx:2262/2268、profile:45、history:272/274（span）。tag 11：match 80；page.tsx 200；plaza 85,95,100,298；AgentExchangeWorkspace 98,329,359,445；AgentIdentityCard 8。tag-amber 6：match 80、page 200、plaza 85、AgentExchangeWorkspace 359,445、AgentIdentityCard 8。tag-rec 1：AgentExchangeWorkspace 445。plaza 95/100 的 tag 被 bg-black/60 + text-white/80|70 覆盖成深色胶囊。主页发送按钮不用 .btn，而是 page.tsx:2311 `bg-primary text-primary-foreground disabled:bg-secondary disabled:text-[color:var(--dim)]`。
- **行为（必须保留）**：纯样式；不少 chip 是开关按钮（aria-pressed 用在 page.tsx:2008 图片模型、2270 比例；朗读 2133、免提 2148 只用 chip-on 类表示状态，没有 aria-pressed）。抽屉内的 tab 切换（2407-2408、2444-2445）用 chip/chip-on，没有 role=tab。
- **状态**：只有 .btn 有 :disabled 样式。.chip 没有禁用样式，但这些 chip 按钮会被 disabled：page.tsx:2008-2017（isLoading 或模型不可用）、2148（免提）、2255-2257（上传参考图）、2270（比例）、2278-2280（生成图片），禁用时外观和可用时一样。.btn/.chip/.tag 都没有 :focus-visible 样式，焦点环只靠 globals.css:167 的 outline-ring/50 加浏览器默认 outline。
- **手机端**：多处在手机上用工具类把尺寸放大到 40px 触控区（max-md:h-10/w-10、mobile:min-h-10），比如 page.tsx 2017/2257/2271/2280/2290/2295/2304、ConversationPicker 51/55。
- **改造风险**：高度、内边距常被工具类覆盖（h-6/h-7/h-8/h-10、px-0/px-2/px-2.5），改基础尺寸时这些覆盖不受影响；手机 40px 触控区由覆盖类保证，不能删。

### .bubble-* / .typing-cursor / .msg-in-* 消息样式
- **位置**：app/globals.css:272-281, 317-341
- **结构**：.bubble-user（273-277）：底 --bubble-user、字 --bubble-user-text、1px --glass-border、圆角 10、padding 9px 14px、行高 1.6、阴影 --shadow。.bubble-ai（278-281）：透明、padding 0、行高 1.75（分身消息没有气泡）。.typing-cursor::after（322-327）：内容 "▌"，amber-ink，blink 1.4s。msg-in-left/right（330-341）：slideInLeft/Right，0.2s，位移 12px。
- **样式**：bubble-user 与 bubble-ai 各 3 处：ChatBubble.tsx:217（cn 中二选一，用户还加 max-w-[520px]，分身加 max-w-[640px]）、history/page.tsx:347、match/page.tsx:387。typing-cursor 1 处：ChatBubble:218（message.isTyping || stillTyping）。msg-in-left/right 1 处：ChatBubble:172（外层行容器）。
- **行为（必须保留）**：打字机光标随 isTyping 状态切换；入场动画只在挂载时播放。
- **状态**：流式输出中（typing-cursor）；生成中（ChatBubble 205-207 有 role=status 和 LoaderCircle 转圈）。
- **手机端**：ChatBubble 在 max-md 下改为 max-w-full / w-full（172, 217）。
- **改造风险**：globals.css:460-468 的全局 reduced-motion 会把 typing-cursor 的闪烁和 msg-in 动画全部关掉（animation:none !important）。

### 未分层的动画与杂项类（hud-*、ticker、topic-drawer、wave-bar、减弱动态）
- **位置**：app/globals.css:291-355, 433-468；app/match/page.tsx:423-449（styled-jsx global）
- **结构**：hud-like-burst（292-297）：scale 1→1.5→1，峰值时加粉色 drop-shadow rgba(255,80,120,.75)，0.45s。hud-like-pop（299-315）：绝对定位 top -4 right -8，颜色 #ff6680，10px 粗体，text-shadow rgba(255,102,128,.9)，0.75s 上飘淡出。wave（344-355）：.wave-bar + nth-child 延迟。ticker-track（434-445）：inline-flex nowrap，60s 平移 -50% 无限循环，hover 暂停。topic-drawer-in（448-457）：从 scaleY .05 展开，360ms。全局 `@media (prefers-reduced-motion: reduce)`（460-468）对 *, ::before, ::after 设 animation:none !important、transition-duration .01ms !important。match/page.tsx:423-449 另有一段 `<style jsx global>`：cloud-drift keyframes，以及 .cloud-card.glass-card、.cloud-stable、.cloud-out 的过渡（自带 reduced-motion 分支）。
- **样式**：hud-like-burst 1 处：plaza:127（Heart 图标）；hud-like-pop 1 处：plaza:129（“+1”）。全仓只有这两个 hud-* 类。ticker-track 1 处：plaza:553（数据双份拼接实现无缝滚动）。topic-drawer-in 1 处：plaza:419。wave-bar 0 处（死 CSS）。mobile-scrollbar-none 2 处：history:243、AgentExchangeWorkspace:81。no-scrollbar 工具类 0 处。tw-animate-css 只用在 page.tsx:2043 和 2106（animate-in slide-in-from-left duration-300）；animate-spin 20 处；duration-150 在 Sidebar 123/140/208；duration-500 在 plaza 64/74。JSX 内联过渡：page.tsx:190（匹配浮卡）、2347/2378/2400/2437（抽屉 transform 360ms cubic-bezier(.22,.61,.36,1)）；match:69 animationDelay。
- **行为（必须保留）**：点赞：burst 计数变化时重新挂载 pop（key=burst）。ticker hover 暂停。
- **状态**：减弱动态：全部 CSS 动画和过渡几乎归零（包括抽屉 inline transition，因为 !important 优先于 inline 非 important 声明）。
- **手机端**：无差异。
- **改造风险**：1) 这些规则都没有分层（不在 @layer 中），优先级高于 Tailwind 工具类；新增同类规则要注意。2) #ff6680 等粉色硬编码与令牌无关。3) match 页的 styled-jsx 全局样式会覆盖 .glass-card 的 opacity/transform，改玻璃类时要一起看。

### 滚动条与手机输入字号
- **位置**：app/globals.css:357-431
- **结构**：WebKit 滚动条（358-393）：宽高 6px、透明轨道、thumb rgba(0,0,0,.22)，hover .4，全部 !important；.dark 下 thumb 改为 rgba(255,255,255,.22/.4)（395-403）。Firefox（406-413）：scrollbar-width thin，scrollbar-color 黑/白 .22，!important。415-431：`@media (width<48rem)` 加 `:root:not([data-shell="desktop"])`，input/textarea/select 字号 max(16px,1em)（防 iOS 聚焦缩放）；.mobile-scrollbar-none 在手机上隐藏滚动条。
- **样式**：滚动条颜色是写死的黑/白 rgba，没有走令牌；主题选择器写死 .dark。
- **行为（必须保留）**：无。
- **状态**：无。
- **手机端**：16px 输入字号规则同样遵循 data-shell，iframe 在桌面父窗口里不放大字号。
- **改造风险**：改主题机制（例如 .dark 换成 data-theme）时，395-403 和 411-413 的 .dark 选择器要同步改；所有声明都带 !important，组件里无法局部覆盖。

### 根布局 app/layout.tsx（html 类、首帧 data-shell 脚本、metadata/viewport、字体）
- **位置**：app/layout.tsx:1-66
- **结构**：metadata（5-13）：title "Chloe"，description "我拥有世界 — 每个人自己的分身"，appleWebApp {capable, title, statusBarStyle "black-translucent"}。viewport（15-20）：themeColor "#0E1219"（单一值，等于深色 --background）、device-width、initialScale 1、viewportFit "cover"（各处 env(safe-area-inset-bottom) 依赖它）。html（28）：lang zh-CN，className "dark h-full"（服务端固定输出深色），suppressHydrationWarning。head 内联脚本（30-58）：只在 window.parent!==window 且 URL 有 ?embed=1 时运行；读父窗口 matchMedia("(min-width: 768px)")，匹配就在 documentElement 设 data-shell="desktop"，否则移除；监听 change（优先 addEventListener，退回 addListener），pagehide 时移除监听（once）；整体 try/catch，跨源或异常时保持上一次状态。body（60）："h-full antialiased"，挂 {children} 和 <PwaRegister/>。没有 next/font，没有任何 webfont，没有 <link> 字体。
- **样式**：字体完全来自 globals.css 的系统字体栈。
- **行为（必须保留）**：data-shell 是 iframe 抽屉在桌面上不切手机布局的唯一机制，被 globals.css:7-13（mobile 变体）和 415-431 消费。suppressHydrationWarning 让脚本在 hydration 之前改 html 属性不会报错。
- **状态**：非 iframe 页面永远没有 data-shell。
- **手机端**：父窗口小于 768px 时 iframe 内移除 data-shell，`mobile:` 正常生效。
- **改造风险**：1) CSP（next.config.ts:32-45）为 `font-src 'self' data:`、`style-src 'self' 'unsafe-inline'`，Google Fonts 的 CSS 和字体文件都会被拦；思源宋体只能走 next/font（构建期自托管到 /_next/static/media）或 next/font/local（文档：node_modules/next/dist/docs/01-app/01-getting-started/13-fonts.md）。next/font/google 构建时要联网下载。2) proxy.ts:39-41 matcher 只放行 api|_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|icons|textures|uploads；新增 public/fonts、public/svg 之类的目录会被鉴权代理拦截，生产环境下未登录的 /login 页请求这些资源会被 302 到 /login。3) script-src 允许 'unsafe-inline'（没有 nonce），因此可以再加一段首帧主题脚本，放在现有 data-shell 脚本旁边。4) 双主题时 themeColor 要改成数组或按主题动态生成（generate-viewport 文档第 95-119 行支持 media 数组）。

### PWA：manifest / icons / favicon / PwaRegister / sw.js
- **位置**：app/manifest.ts:1-32；public/icons/icon-192.png、icon-512.png；app/favicon.ico；components/PwaRegister.tsx:1-23；public/sw.js:1-28
- **结构**：manifest：name/short_name "Chloe"，start_url "/"，display standalone，background_color 与 theme_color 均为 "#09090b"（不是任何令牌，和 layout 的 #0E1219 也不一致），orientation portrait-primary，图标 192、512、512 maskable。图标内容是黄色渐变底上的卡通女孩头像，和应用内的双圆 logo（Sidebar.tsx:87-90、login:140-143）不一致。app/favicon.ico 为 25931 字节、16/32 两档，大小与 create-next-app 默认 favicon 相同。PwaRegister：开发环境卸载所有 SW；生产环境注册 /sw.js。sw.js 是自杀式 SW：install 时 skipWaiting，activate 时清空 caches、注销自己、让各客户端重新导航，没有 fetch 处理。
- **样式**：只有颜色常量。
- **行为（必须保留）**：生产首次加载会注册 SW 再自注销并刷新客户端（一次重导航）。
- **状态**：无。
- **手机端**：Apple 状态栏 black-translucent 配合 viewportFit cover，浅色主题下状态栏文字仍是白色。
- **改造风险**：1) 改主题色要同时改 manifest:10-11 与 layout:16。2) public 下未被引用的资源：file.svg、globe.svg、next.svg、vercel.svg、window.svg（Next 模板残留），textures/earth_clouds_2k.jpg、earth_day_2k.jpg、earth_night_2k.jpg、earth_normal.jpg。

### Sidebar 桌面竖栏（aside）
- **位置**：components/Sidebar.tsx:1-180（aside 84-180）
- **结构**：navItems（13-19）共 5 项：/ MessageCircle「对话」、/agents/me Bot「分身」、/agents Orbit「广场」、/plaza Globe「世界」、/settings Settings「设置」。aside（84）：`glass flex min-h-0 w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar py-3 max-md:hidden`，宽 56px。Logo（86-91）：32px 方块，amber-ink 色，24px SVG 双圆（cx 9/15，r 5.5，描边 1.5），title="Chloe"。nav（94-152）：纵向 flex-1 overflow-y-auto；每项 h-12 w-12 rounded-[6px]，图标 20px（激活描边 2.2，否则 1.8），下面一行 10px 文字。底部（154-179）：草莓余额，🍓（aria-hidden）+ `<b className="readout">`，title “草莓余额，每条消息消耗 10 颗”；主题切换按钮 h-10 w-12，深色时显示 Sun、浅色时显示 Moon，title 为“切换浅色/切换深色”。
- **样式**：激活：text-[color:var(--amber-ink)]（125,142）；未激活：text-muted-foreground hover:bg-secondary hover:text-foreground；transition-colors duration-150。余额颜色 inline（159-165）：<30 用 var(--rec)，<100 用 var(--amber-ink)，否则 var(--foreground)；null 时显示“…”。
- **行为（必须保留）**：激活判断（97-105）：drawerActive（agentActive/exchangeActive/plazaActive/settingsActive）或 chatActive（pathname==='/' 且没有抽屉打开）或 pathname===href（不是 /）。drawerCallback（107-113）：父组件传了回调就渲染 <button type=button>，不路由；否则渲染 <Link>。桌面按钮只给 /agents/me 和 /agents 设了 aria-expanded/aria-controls（120-121，对应 agent-drawer / exchange-drawer），/plaza 和 /settings 在桌面上没有（手机底栏有）。余额拉取（54-80）：apiFetch(`${API}/strawberry`)，挂载时拉一次、每 60s 拉一次、监听 window 的 storage 和自定义 fiona-user-changed 事件；成功后 setBalance、调 onBalanceChange、updateBalance 写 localStorage；没有用户名时置 null；错误静默。主题按钮 onClick=toggleTheme（173）。props 声明了 onHistoryClick（33），但没有解构使用。
- **状态**：余额 null→“…”；低余额两档变色。没有错误态。主题按钮没有 aria-label 和 type（只有 title）；激活项没有 aria-current；aside/nav 都没有 aria-label。
- **手机端**：max-md:hidden（用 max-md 而不是 mobile 变体，因为 iframe 内不渲染 Sidebar）。手机端草莓余额改由 page.tsx:2165-2170 的头部显示（只在主页），主题切换改在 ConversationPicker:100-105。
- **改造风险**：1) 改成“竖排书签导航”且宽度不再是 56px 时，以下写死的地方要一起改：Sidebar:84 w-14；page.tsx:2043、2097、2466 的 left-14（2463 是注释）；page.tsx:2343、2374 的抽屉宽 min(960px, calc(100vw - 56px))；2396、2433 的 calc((100vw - 56px) * 2 / 3)。2) page.tsx:319-322 的 focusVisibleDrawerTrigger 用 `button[aria-controls=id]` 加 getClientRects().length>0 找可见触发器；桌面 aside 和手机 nav 两份按钮同时在 DOM 里，隐藏的那份必须是 display:none，按钮也必须保留 aria-controls，否则 Esc 关闭抽屉后焦点回不到触发器。3) 使用 Sidebar 的页面：page.tsx:2027（传入全部抽屉回调和 onBalanceChange）、match:308、settings:130、plaza:367、profile:91、community:13（这几处都是 !embedded 时才渲染）、agents/[id]:33、MyAgentWorkspace:100、AgentExchangeWorkspace:64（!embedded）。history 和 login 不渲染 Sidebar。4) logo SVG 在 Sidebar:87-90 和 login:140-143 各写了一份。

### Sidebar 手机底栏（nav 主导航）
- **位置**：components/Sidebar.tsx:181-221
- **结构**：`<nav aria-label="主导航">`，className `glass fixed inset-x-0 bottom-0 z-[70] flex h-[calc(56px+env(safe-area-inset-bottom))] items-start border-t pb-[env(safe-area-inset-bottom)] md:hidden`，inline borderColor var(--glass-border)。5 项各 flex-1 h-14，竖排图标 20px + 10px 文字，whitespace-nowrap。
- **样式**：激活与未激活配色同桌面（208-212）。没有余额，也没有主题按钮。
- **行为（必须保留）**：激活与回调逻辑和桌面相同（187-201）；drawerId（202-206）给四个抽屉都设了 aria-expanded 和 aria-controls（agent-drawer / exchange-drawer / plaza-drawer / settings-drawer）。
- **状态**：同桌面。
- **手机端**：仅在 <768px 显示（md:hidden），z-[70] 压在所有抽屉（z-55）和对话列表弹层（z-61/62）之上。
- **改造风险**：底栏高度 56px+safe-area 被硬编码为各处的底部避让：page.tsx:2043、2097、2104、2106、2173、2190、2341、2372、2391、2428、2466；plaza:365、414、573、588、592；match:306；settings:128；profile:89；community:11；agents/[id]:34；MyAgentWorkspace:101；AgentExchangeWorkspace:65（共 25 处左右）。底栏高度一变，这些 calc 都要改。

### 主页面外壳：右侧四抽屉 + iframe embed=1 + 遮罩层
- **位置**：app/page.tsx:293-333（状态）、2023-2038（根与 Sidebar）、2041-2098（当前对话记录抽屉）、2101-2109（对话列表）、2328-2470（四抽屉与遮罩）
- **结构**：根 `flex flex-col h-dvh overflow-hidden`（2024）。抽屉状态 drawer: "agent"|"exchange"|"plaza"|"settings"|null，互斥（293-294）；worldTab plaza|match（295）；settingsTab settings|profile（296）。分身抽屉 section#agent-drawer（2328-2357）与分身广场 section#exchange-drawer（2359-2386）：`glass fixed inset-y-0 right-0 z-[55] flex flex-col`，宽 min(960px, calc(100vw-56px))，translateX(0/105%) 过渡 360ms，aria-hidden 与 inert 随开合切换，tabIndex -1，Esc 时 closeDrawer 再 focusVisibleDrawerTrigger；内容是组件（不是 iframe）：MyAgentWorkspace embedded（2356）、AgentExchangeWorkspace embedded（2385），只在打开时挂载。世界抽屉 div#plaza-drawer（2389-2423）与设置抽屉 div#settings-drawer（2426-2460）：宽 calc((100vw-56px)*2/3)，willChange transform，头部有 chip 页签（2407-2408：热点与帖子/匹配；2444-2445：设置/账户）和关闭按钮（只有 title，没有 aria-label），内容是 `<iframe src="/plaza?embed=1"|"/match?embed=1">`（2419）和 `/settings?embed=1`|`/profile?embed=1`（2456）；关闭后 iframe 不卸载（注释 2388）；username 为空时显示 role=status“正在加载身份…”。四个抽屉的标题栏都是 `border-b px-4 py-2` + text-xs 标题。遮罩（2464-2470）：任一抽屉打开时铺 `fixed left-14 top-0 right-0 bottom-0 z-50` 透明层，点击关闭。当前对话记录抽屉（2041-2093）：`glass absolute left-14 … w-64 z-50 animate-in slide-in-from-left duration-300`，inline borderRight + boxShadow；背板 2096-2098 用 bg-black/20 backdrop-blur-sm。对话列表：桌面 ConversationPicker（2101，max-md:hidden）；手机弹层（2103-2109）是 role=dialog aria-modal 的 z-[62] 层，背板 z-[61] bg-black/20 backdrop-blur-sm。
- **样式**：抽屉都用 .glass，inline borderLeft var(--glass-border)，boxShadow rgba(0,0,0,.28)；关闭按钮 hover:bg-secondary。
- **行为（必须保留）**：toggleDrawer / closeDrawer（311-318）同时关闭手机面板（closeMobilePanelsFromNavigation 305-310）。分身与分身广场抽屉打开时聚焦面板本身（327-330）。focusChatInput（426-431）通过读两个抽屉的 aria-hidden 决定是否把焦点还给输入框。对话列表弹层有 Tab 焦点陷阱、Esc 关闭、切到桌面断点自动关闭（334-371）；历史抽屉在手机上 Esc 关闭并还原焦点（372-389）。Sidebar 的 onChatClick=closeDrawer，四个抽屉回调都是 toggleDrawer。
- **状态**：关闭态：transform 105%、阴影 none，手机上还加 max-md:hidden；iframe 抽屉关闭后仍保留 iframe 状态。加载身份中显示文字。
- **手机端**：抽屉在手机上 max-md:left-0、max-md:w-screen!、max-md:bottom-[calc(56px+env(safe-area-inset-bottom))]!，即全宽并让出底栏；遮罩 max-md:left-0。iframe 内由 layout 脚本按父窗口断点设置或移除 data-shell。
- **改造风险**：1) iframe 是独立文档：父窗口切换主题不会传进 iframe（iframe 由服务端渲染为 class="dark"，没有 postMessage 或存储同步），现在浅色主题下打开世界/设置抽屉，里面仍是深色；双主题必须让 iframe 首帧就拿到同一主题（例如持久化到 localStorage 或 cookie，在首帧脚本里读取，并监听 storage 事件）。2) iframe 内有自己的 body 背景，抽屉 .glass 的毛玻璃对 iframe 区域无效。3) z 轴顺序：头部和输入区 z-[2] < 匹配浮卡 zIndex 20 < 历史背板 z-40 < 历史抽屉、遮罩 z-50 < 四抽屉 z-[55] < 对话列表 z-61/62 < 手机底栏 z-[70]；GeneratedImage 用原生 dialog（顶层）并 createPortal 到 body（GeneratedImage.tsx:164,178）。4) 抽屉 id 和 aria-controls 是 Sidebar 与 page.tsx 之间的契约，不能改名。

### 各页 embed=1 外层包装（独立页 / 抽屉内两种形态）
- **位置**：app/plaza/page.tsx:361-371；app/match/page.tsx:303-312；app/settings/page.tsx:14,128-140；app/profile/page.tsx:86-100,161；app/community/page.tsx:9-27；components/MyAgentWorkspace.tsx:16-26,98-105；components/AgentExchangeWorkspace.tsx:17-26,62-69,416；app/agents/[id]/page.tsx:32-47；app/history/page.tsx:144-189；app/login/page.tsx:136-149
- **结构**：iframe 页统一写法：`const embedded = searchParams.get("embed")==="1"`；外层 plaza/match 用 `flex h-screen flex-col overflow-hidden mobile:h-dvh`，settings/profile/community 用 `flex h-dvh flex-col overflow-hidden`；非 embedded 时加 `mobile:pb-[calc(56px+env(safe-area-inset-bottom))]`，并在 `flex flex-1 min-h-0` 行内渲染 <Sidebar/>。标题栏统一为 `glass sticky top-0 z-[2] shrink-0 border-b px-8 pb-[18px] pt-7 mobile:px-4 mobile:pt-4`，h1 用 `text-xl font-medium tracking-[-0.01em]`，副标题 13px muted（settings:132-139、profile:93-97、community:15-21；MyAgentWorkspace:102、AgentExchangeWorkspace:66、agents/[id]:35 是同一结构，只是用 max-md）。组件级 embedded（MyAgentWorkspace、AgentExchangeWorkspace）：外层高度在 embedded 时为 h-full min-h-0，否则 h-screen max-md:h-dvh；embedded 时不渲染 Sidebar 和“回到对话”链接；AgentExchangeWorkspace:416 的文档区在 embedded 时从 glass-card 改为 border-t。profile:161 的 Link 在 embedded 时用 target=_top 跳出 iframe；settings:61 和 lib/auth.ts:26 用 window.top 做顶层跳转。history（144-189）：没有 Sidebar，是 window.open 新窗口打开的独立页（page.tsx:2001），min-h-screen，有 glass 头部和 glass 侧栏。login（136-149）：居中 360px 列，包含双圆 logo、.echo“Chloe”、标语、Signal idle 和 .glass 卡。plaza 背景是 <SolarSystem3D/>（371），match 背景是 <Earth3D/>（312）。
- **样式**：见各行；community 只有一张“社群功能即将上线”的 glass-card。
- **行为（必须保留）**：embedded 只影响外壳（Sidebar、底部留白、高度、跳转 target），不影响数据请求。
- **状态**：match/plaza 用 Suspense 和“加载中…”作 fallback（match:457-466）；agents/[id] 有登录引导、加载、错误重试三态（44-46）。
- **手机端**：iframe 页用 `mobile:`，非 iframe 页用 `max-md:`（见 Tailwind 变体区域）。
- **改造风险**：1) 新外壳的标题栏、书签导航、朱印、背景 SVG 都要考虑“同一页面两种形态”：独立页带 Sidebar，嵌入时不带。2) history 永远是深色（新窗口，没有主题持久化）。3) community 页存在，但主页面没有入口（navItems 不含它，抽屉也不加载它）。

### 主题系统（useTheme 与两个调用处）
- **位置**：lib/useTheme.ts:1-20；components/Sidebar.tsx:9,46,171-178；components/ConversationPicker.tsx:5,40,100-105；app/layout.tsx:28
- **结构**：真相源是 document.documentElement 上的 .dark 类。getDark（6-8）：没有 document 时返回 true；subscribeTheme（10-14）用 MutationObserver 观察 html 的 class；useTheme（16-20）= useSyncExternalStore(subscribe, getDark, () => true) 加 toggleTheme = classList.toggle("dark")。调用处：Sidebar 桌面底部按钮（172-178，只有桌面可见）；ConversationPicker 底部（100-105，`md:hidden`，带“主题”文字，有 aria-label）。
- **样式**：按钮图标：深色时显示 Sun，浅色时显示 Moon。
- **行为（必须保留）**：默认：服务端固定输出 class="dark"（layout.tsx:28），首屏永远深色。切换：只改当前文档的 class；不持久化（全仓没有与主题相关的 localStorage/cookie）；不读 prefers-color-scheme（全仓 grep 为 0）；不同步到 iframe 和其他标签页；刷新、新窗口（history）、iframe 都会回到深色。Next 客户端路由切页时 html 不重新渲染，所以 class 能保留。
- **状态**：只有 dark/light 两态。
- **手机端**：手机上主题切换只出现在主页对话列表弹层底部（ConversationPicker 由 page.tsx:2107 渲染）；直接打开 /settings、/plaza 等独立页时，手机上没有主题按钮。
- **改造风险**：1) 昼天青/夜建盏若要“首帧无闪烁 + 持久化 + iframe 一致”，需要新增首帧脚本（CSP 允许内联脚本），并保证 useTheme 的服务端快照与首帧一致，否则会出现 hydration 后的图标闪变。html 已有 suppressHydrationWarning。2) MutationObserver 只监听 class 属性，改用 data-theme 时 attributeFilter 要同步改。3) 素瓷（不透明）退路目前没有用户开关，只靠 globals.css:284-289 的系统条件。

### components/ui/*（shadcn base-nova 组件）
- **位置**：components/ui/avatar.tsx(109)、badge.tsx(52)、button.tsx(58)、input.tsx(20)、scroll-area.tsx(55)、separator.tsx(25)、textarea.tsx(18)
- **结构**：基于 @base-ui/react 和 cva：Button（variant: default/outline/secondary/ghost/destructive/link；size: default h-8/xs/sm/lg/icon/icon-xs/icon-sm/icon-lg）、Badge（6 种 variant，rounded-4xl）、Avatar 系列、Input（h-8）、Textarea（field-sizing-content）、ScrollArea/ScrollBar、Separator。
- **样式**：使用 dark: 变体、data-horizontal/vertical 变体、ring-3、rounded-lg（--radius）等标准 shadcn 写法。
- **行为（必须保留）**：无业务行为。
- **状态**：组件自带 disabled、aria-invalid、focus-visible 样式。
- **手机端**：Input/Textarea 用 md:text-sm。
- **改造风险**：整个仓库没有任何文件 import components/ui/*（grep `components/ui/`、buttonVariants、<Button>、<Badge> 等都是 0），它们是死代码；实际界面全部用 globals.css 里的 .btn/.chip/.tag 和手写类。改造时改 ui/* 对界面没有影响；如果要启用它们，得先补上调用方。

### 世界页 3D 星系与匹配页背景（及 public/textures）
- **位置**：components/SolarSystem3D.tsx:1-254；components/Earth3D.tsx:1-20；lib/usePrefersReducedMotion.ts:1-23；public/textures/*（8.5MB）
- **结构**：SolarSystem3D：@react-three/fiber Canvas（camera [0,3.8,11] fov 44，dpr [1,1.5]，ACES 色调映射）+ drei Stars（8000 颗）+ postprocessing Bloom；8 颗行星贴图（23-30）、milkyway.jpg 天球（75）、sun.jpg（90）、saturn_ring.png（116）；外层 `absolute inset-0 pointer-events-none`，上面叠两层 z-10：琥珀扫描线 rgba(242,168,60,.012)，mix-blend screen（216-221）；暗角 radial rgba(0,0,15,.65)（224-229）。frameloop：页面可见时，减弱动态用 demand，否则 always；页面不可见时 never（VisibilityController 监听 visibilitychange）。调用：plaza:371。Earth3D：静态 div，背景 url(/textures/match_bg.jpg) + #000，调用 match:312。
- **样式**：硬编码颜色：SolarSystem3D 24-26 大气 #e8b47a/#4fc3f7/#e64a19、103 #ffe0a0（太阳点光），219 和 227 的 rgba；Earth3D:16 #000。
- **行为（必须保留）**：usePrefersReducedMotion 只被 SolarSystem3D:211 使用。
- **状态**：贴图加载期间 Suspense fallback 为 null（空白）。
- **手机端**：同一组件；plaza 在手机上改为纵向流式布局，背景仍铺满。
- **改造风险**：换成静态星图后：three、@react-three/fiber、drei、postprocessing、@types/three（package.json dependencies）和 usePrefersReducedMotion 都会失去调用方；simplex-noise 已经没有任何 import（现在就是未用依赖）。textures 里实际被引用的是 8 颗行星、milkyway、sun、saturn_ring、match_bg；earth_clouds_2k/day_2k/night_2k/earth_normal 无引用。proxy matcher 放行了 textures 目录（proxy.ts:40）。

### lib 下与 UI 相关的工具
- **位置**：lib/utils.ts:1-6；lib/usePrefersReducedMotion.ts；lib/useTheme.ts；lib/auth.ts:88-115；lib/config.ts
- **结构**：cn = twMerge(clsx(...))，被 Sidebar、page.tsx、plaza、match、ChatBubble、GeneratedImage、Signal、ui/* 使用。auth.ts：setAuth 派发 fiona-user-changed（97-99），updateBalance 写 localStorage（102-104），Sidebar 余额刷新依赖这两项。lib/open.ts 的 openExternal 处理 Tauri 外链（plaza:11、NewsCardContent:8），与样式无关。
- **样式**：无。
- **行为（必须保留）**：twMerge 会合并冲突的 Tailwind 类，但不认识 .glass/.btn 这些自定义类，不会去重它们。
- **状态**：无。
- **手机端**：无。
- **改造风险**：新增自定义工具类（@utility）时要注意 twMerge 可能误判冲突；用 @layer components 的普通类不受影响。

### 跨区域要点
- 深浅主题现状：默认深色，由 app/layout.tsx:28 的 <html className="dark h-full"> 写死；lib/useTheme.ts:18 只对当前文档执行 classList.toggle("dark")；不持久化（没有 localStorage/cookie），不读 prefers-color-scheme，不同步到 iframe（/plaza、/match、/settings、/profile 的 ?embed=1）、新窗口（/history）和其他标签页，刷新后回到深色。切换入口两处：Sidebar.tsx:172-178（只有桌面）、ConversationPicker.tsx:100-105（只有手机，且只在主页的对话列表弹层里）。themeColor 固定为 #0E1219（layout.tsx:16），manifest 固定为 #09090b（manifest.ts:10-11），两者不一致。
- CSS 优先级：.glass/.glass-card/.readout/.echo/.signal/.state-dot/.btn*/.chip*/.tag*/.bubble-* 在 @layer components（globals.css:181-282），会被任何 Tailwind 工具类覆盖；而 @supports 和减少透明度的降级（284-289）、hud-*、typing-cursor、msg-in-*、wave、ticker、topic-drawer、滚动条（带 !important）、手机输入字号、reduced-motion（!important）都没有分层，优先级高于工具类。match/page.tsx:423-449 另有一段 styled-jsx 全局样式会改 .cloud-card.glass-card。
- 全局类使用总数（只计字符串字面量）：glass 25、glass-card 30、btn 73、btn-primary 11、btn-quiet 48、btn-danger 3、chip 22、chip-on 16、tag 11、tag-amber 6、tag-rec 1、bubble-user 3、bubble-ai 3、readout 47、echo 2 个元素（另有 2 处 [&_.echo] 后代选择器）、signal 1（Signal.tsx:89）、state-dot 2、state-dot-listening 1、state-dot-speaking 2、hud-like-burst 1、hud-like-pop 1（全仓只有这两个 hud-*，都在 plaza:127/129）、ticker-track 1（plaza:553）、topic-drawer-in 1（plaza:419）、wave-bar 0（死 CSS）、typing-cursor 1、msg-in-left/right 各 1（ChatBubble:172）、mobile-scrollbar-none 2、no-scrollbar 0。具体文件:行见各区域。
- TSX 中的硬编码颜色：layout.tsx:16 #0E1219；manifest.ts:10-11 #09090b；Earth3D.tsx:16 #000；SolarSystem3D.tsx:24-26、103、219、227；page.tsx:2044、2345、2376、2398、2435 的 rgba(0,0,0,.28) 抽屉阴影；Tailwind 调色板类：page.tsx:2097、2104 bg-black/20，2238 hover:text-white；plaza 60 bg-black/40、80/95/100 bg-black/60、95 text-white/80、100 text-white/70、107 from-black/70、588 bg-black/70、607 bg-black/50；GeneratedImage:164 backdrop:bg-black/75。TSX 里没有直接写 #F2A63A，琥珀色都经过 var(--amber-ink)（73 处）或 primary。globals.css 的硬编码集中在令牌（59-163）、hud 粉色（294、308、312）、滚动条黑白 rgba（373-412）。
- 圆角写死：rounded-[6px] 31 处、rounded-[10px] 12 处、rounded-[3px] 1、rounded 9、rounded-full 5、rounded-xl 2、rounded-lg 1、rounded-none 1；另外 .glass-card 10px、.btn/.chip 6px、.tag 4px、.bubble-user 10px 都写在 CSS 里，没有走 --radius。
- 桌面导航宽 56px（Sidebar.tsx:84 w-14）被 page.tsx 2043/2097/2466 的 left-14 和 2343/2374/2396/2433 的抽屉宽度公式引用；手机底栏高度 56px+safe-area 被约 25 处 calc 引用（page.tsx 11 处、plaza 5 处，match/settings/profile/community/agents/[id]/MyAgentWorkspace/AgentExchangeWorkspace 各 1 处）。导航尺寸一改，就要同步这些位置。
- iframe 隔离：四个 iframe 抽屉是独立文档，各自有 body 背景、各自的 html.dark、各自的 backdrop 上下文；data-shell="desktop" 只由 layout.tsx:30-58 的首帧脚本按父窗口 768px 断点设置，iframe 内的样式必须用 `mobile:` 变体（globals.css:7-13）才会尊重它。双主题、背景 SVG、素瓷开关都要在 iframe 文档里各自生效。
- CSP（next.config.ts:32-45）：font-src 'self' data:、style-src 'self' 'unsafe-inline'、img-src 'self' blob: data:、script-src 'self' 'unsafe-inline'（开发环境加 unsafe-eval）。外链字体和 Google Fonts CSS 会被拦，思源宋体须通过 next/font 自托管；内联 SVG 和 data-URI SVG 不受影响。proxy.ts:39-41 matcher 没有放行新的 public 子目录，新增静态资源目录要加进排除列表，否则未登录时（例如 /login 页）请求会被重定向。
- 无障碍与焦点契约：抽屉 id（agent-drawer、exchange-drawer、plaza-drawer、settings-drawer）与 Sidebar 按钮的 aria-controls 配对，page.tsx:319-322 靠 getClientRects 找可见的那个触发器（桌面和手机两套按钮同时在 DOM 里，隐藏的那套必须是 display:none）；分身和分身广场两个抽屉用 aria-hidden + inert + tabIndex -1 + Esc；手机对话列表是 role=dialog aria-modal，有焦点陷阱；手机底栏 aria-label="主导航"。现有缺口：桌面导航没有 aria-label、没有 aria-current；主题按钮（Sidebar）没有 aria-label；世界和设置抽屉的关闭按钮只有 title；chip 页签没有 role=tab；.chip 没有禁用和 focus-visible 样式。
- 减弱动态：globals.css:460-468 全局去掉 CSS 动画和过渡（含抽屉 inline transition），Signal.tsx:33-40 与 SolarSystem3D 自己处理 rAF 和 WebGL；match 的 styled-jsx 也有 reduced-motion 分支。新的远山状态线、朱印动效如果用 rAF，必须自己判断 reduced-motion。
- 字体：目前没有任何 webfont；--font-sans-stack 是系统中文黑体栈，--font-mono-stack 供 .readout（47 处）使用；font-mono 工具类只在 login:161、221；font-heading 已映射但没有使用。
- 死代码与未用资源：components/ui/* 七个文件零引用；wave-bar、no-scrollbar、shadcn-tailwind.css 的 data-* 变体在 ui 之外零使用；simplex-noise 依赖零 import；public 下 file/globe/next/vercel/window.svg 与 textures 中 earth_clouds_2k/day_2k/night_2k/earth_normal 无引用；app/favicon.ico 大小与 create-next-app 默认图标相同；PWA 图标（卡通女孩）与应用内双圆 logo（Sidebar.tsx:87-90、login:140-143 两份重复）不一致。
- 前端没有任何自动化测试（Fiona 仓库内没有 *.spec/*.test/playwright 配置），也没有测试依赖 CSS 选择器；验证只能靠 lint、tsc、build 和实机走查。

## world：世界与匹配（Fiona/frontend @586d86a，工作树干净）：app/plaza/page.tsx(664)、components/SolarSystem3D.tsx(254)、app/match/page.tsx(468)、components/Earth3D.tsx(20)、lib/useHotTopics.ts(144)，以及宿主 app/page.tsx 世界抽屉、Sidebar、layout.tsx、globals.css 中被这两页用到的部分
### 世界页外壳（PlazaContent 根布局与 embed 判定）
- **位置**：app/plaza/page.tsx:224-235（状态）、361-369（embed 判定、根 div、main）、582-585（main 结束与隐藏 input）、658-664（PlazaPage Suspense fallback=null）
- **结构**：根 div `flex h-screen flex-col overflow-hidden mobile:h-dvh`（365；非 embed 时加 mobile:pb-[calc(56px+env(safe-area-inset-bottom))]）> div `flex flex-1 min-h-0 relative`（366）> [Sidebar（367，仅非 embed）, main `flex flex-col flex-1 min-w-0 relative overflow-hidden mobile:overflow-y-auto`（369；非 embed 时加 mobile:pb-20）]。桌面：main 是定位容器，除帖子流外全部 absolute 叠放：背景 inset-0（371）、左栏 top16/left16 z20（374-386）、右栏 top16/right16 z20（389-400）、帖子流 relative z10 flex-1 自滚动（403）、话题抽屉 z30（410-516）、底栏 bottom0 h44 z20（519-566）、FAB z30（569-581）；发布弹层 fixed z50 在根 div 末尾（587-653），隐藏 file input 在 main 外（585）。手机：main 纵向滚动，两栏和底栏 static! 进入文档流，顺序为 背景→左栏4卡→右栏3卡→帖子网格→底栏；FAB、话题抽屉、发布弹层改为 fixed。
- **样式**：根和 main 上没有 .glass。断点 mobile: 与 sm: 混用。定位全靠内联 style 写数值（377-379、392-394、416、522-525、575-577）。层级为背景(无z)/扫描线z10/帖子z10/两栏z20/底栏z20/抽屉z30/FAB z30/弹层z50；Sidebar 手机导航 z-[70]。
- **行为（必须保留）**：useSearchParams 读 embed=1（361-362）后：隐藏 Sidebar，去掉手机底部 padding，并切换 FAB、话题抽屉、发布弹层的手机 bottom 偏移。PlazaPage 必须保留 <Suspense>（useSearchParams 需要）。
- **状态**：Suspense fallback=null，首帧空白。页面级没有加载态，也没有错误态。
- **手机端**：mobile: 变体在 globals.css:7-13 定义，条件为 (width<48rem) 且 :root 不带 data-shell="desktop"。iframe 内由 layout.tsx:30-58 的内联脚本判断：父窗口 ≥768px 时打上 data-shell=desktop，因此桌面抽屉里的 iframe 只有约 475px 宽也走桌面绝对定位布局。sm:grid-cols-3（404）却是标准媒体查询，按 iframe 自身宽度判断，两套断点同时存在。单独访问 /plaza（非 embed）时，Sidebar 自己渲染手机底部导航（Sidebar.tsx:181-221，md:hidden，z-[70]），桌面侧栏为 Sidebar.tsx:84（max-md:hidden）。
- **改造风险**：如果把 mobile: 换成 md:/max-md:，iframe 抽屉会在桌面父窗口下变成手机布局。main 的 overflow 桌面是 hidden、手机是 auto，背景层和吸附元素要分两种情况处理。根高度桌面用 h-screen、手机用 h-dvh。

### SolarSystem3D 太阳系背景（要换成静态星图的对象）
- **位置**：app/plaza/page.tsx:6（import）、370-371（使用）；components/SolarSystem3D.tsx:1-254
- **结构**：外层 div `absolute inset-0 pointer-events-none`，可追加 className（214，不设 z-index），内含三层：① 扫描线叠层 z-10（215-222）：repeating-linear-gradient 180deg，3px 透明 + 1px rgba(242,168,60,0.012)，mixBlendMode screen；② 边缘暗角 z-10（223-229）：radial-gradient transparent 45% → rgba(0,0,15,0.65)；③ R3F <Canvas>（230-251）：camera [0,3.8,11] fov44，gl alpha/antialias/high-performance/ACESFilmic，dpr [1,1.5]。Canvas 内有：VisibilityController（33-71）、ambientLight 0.18、Scene（184-206，整组绕 y 轴自转 0.025rad/s）、drei <Stars> 8000 颗（242）、EffectComposer+Bloom（243-250，intensity1.4、threshold0.15）。Scene 内有：银河背景球（73-86，/textures/milkyway.jpg，r500，BackSide）；太阳（88-111，sun.jpg r0.52，带 pointLight #ffe0a0）；8 颗行星 PLANETS（22-31，含贴图/尺寸/轨道/速度/相位，Uranus tilt 1.7）各自公转加自转（PlanetMesh 130-182）；Venus/Earth/Mars 有大气光晕（additive，opacity0.12，颜色 #e8b47a/#4fc3f7/#e64a19）；土星环（114-128，saturn_ring.png）。
- **样式**：没有用任何全局类或令牌，颜色全部硬编码（扫描线琥珀、暗角深蓝黑、大气色、点光源色）。
- **行为（必须保留）**：frameloop：页面可见且未开减弱动态时为 "always"；减弱动态时为 "demand"（静帧）；document.hidden 时为 "never"，同时记下 clock.elapsedTime，恢复时回填并 invalidate（44-68、234）。usePrefersReducedMotion 来自 lib/usePrefersReducedMotion.ts:1-23，全仓库只有这里用。贴图用 useTexture 加 Suspense fallback null。
- **状态**：没有加载 UI：贴图到达前对应星体不显示，透出 body 背景。WebGL 不可用时没有退路，也没有 ErrorBoundary。没有错误态。
- **手机端**：桌面手机是同一个组件。手机下 main 是滚动容器，absolute inset-0 只覆盖 main 首屏高度，并随内容一起滚走；往下滚会露出 body 光斑背景（globals.css:166-179）。
- **改造风险**：不管深浅主题都是深色宇宙（银河球把 alpha 完全盖住）。.glass/.glass-card 的 backdrop-filter 现在模糊的就是这层动画。替换层要满足：absolute inset-0、pointer-events-none、层级低于 z-10 的内容。如果希望手机端背景不随滚动走，要改成 fixed 或 sticky，而 iframe 内的 fixed 是相对 iframe 视口。扫描线和暗角是 HUD 风格的一部分，会随组件一起删除。

### 左右热点分类栏 + CategoryCard
- **位置**：app/plaza/page.tsx:138-221（CategoryCard）、237-240（三个 feed）、373-386（左栏）、388-400（右栏）；lib/useHotTopics.ts:1-144
- **结构**：左栏 div（374-386）：absolute top16 left16 z20，flex-col gap10，maxHeight calc(100%-70px)，overflowY auto，依次放 今日热点(微博, Flame)、娱乐(Music2)、经济(BarChart2)、生活(Sparkles)。右栏（389-400）定位相同但靠 right16，放 潮流(抖音, TrendingUp)、科技(Cpu)、文化(BookOpen)。每张 CategoryCard 为 `.glass-card w-[220px] px-3 py-2 pointer-events-auto mobile:w-full`（159-161），自上而下：头部行（163-178）= 12px 图标(amber-ink) + 13px 标题 + 右侧刷新按钮 `.btn .btn-quiet ml-auto h-7 w-7 px-0` 包 RefreshCw；提示块（179-191）`role=status` 10px var(--rec)，附重试按钮 `.btn .btn-quiet ml-1.5 h-7 px-2.5 text-xs`；列表 ul.space-y-1（192-213），最多 4 条 li = `.readout` 序号 01-04 + truncate 标题；获取时间（214-218）`.readout text-[10px]`「获取于 HH:MM」，title 为完整本地时间。
- **样式**：.glass-card、.btn、.btn-quiet、.readout；图标用 var(--amber-ink)；提示文字 text-[color:var(--rec)]；条目 text-foreground/80，hover:text-foreground；li 内联 borderRadius:3。style 参数调用方恒传 {}（死参数）。
- **行为（必须保留）**：useHotTopics(source) 请求 GET /hot/{source}（138-140），useCategorizedHotTopics 请求 GET /hot/categorized/all（142-144）。5 张分类卡共用同一个 feed 对象，点其中任一张的刷新或重试，5 张会一起转圈。挂载后立即拉取，每 5 分钟自动刷新（7、124-133），请求超时 45s（8、78-81），新请求会 abort 旧请求（74）。失败时保留上次数据，超过 1 小时才清空（9、109-118）。429 显示「请求较频繁，请稍后重试」（88）。parseTopics 兼容 items[].title 和旧版 points（会去掉序号和热度后缀），取 5 条（33-44）。分类别名：历史/哲学→文化，时事→生活（57）。li 的 onClick 调 openTopic(title)，title 为「点开查看详情」。刷新按钮 aria-label=`刷新${title}`，loading 时 disabled，title 在「更新中」与「刷新热点」之间切换。
- **状态**：加载中且无数据：「拉取中…」，RefreshCw 加 animate-spin。有错误且无数据：显示 error 文本，列表显示「暂无可显示的热点」。无错误但为空：「暂时没有相关热点」。有错误但有旧数据：「更新失败，显示上次内容」。stale：「实时更新暂不可用，显示上次内容」。partial：「部分来源暂不可用」。重试按钮 loading 时显示「重试中…」并禁用；禁用样式走 .btn:disabled（opacity .45）。时间行在 loading 时加前缀「更新中 · 」。
- **手机端**：两栏加 `mobile:static! mobile:mx-4 mobile:mt-4(右栏 mt-3) mobile:shrink-0 mobile:gap-3 mobile:max-h-none! mobile:overflow-visible!`，卡片 mobile:w-full。7 张卡全部排在帖子流之前。
- **改造风险**：li 不是按钮，没有 tabIndex、role 或键盘处理，键盘用户打不开话题（现状）；如果改成 button，要保留 title 和 truncate。桌面下两栏 z20 浮在帖子网格（z10，max-w-2xl 居中）之上。在 iframe 抽屉宽度（(100vw-56px)*2/3，约 475-1000px）下一定会遮住帖子。数据保留 5 条，页面只显示 4 条。

### 帖子流网格
- **位置**：app/plaza/page.tsx:273-284（loadPosts）、402-407
- **结构**：div `relative z-10 flex-1 overflow-y-auto px-4 py-6 mobile:flex-none mobile:overflow-visible` > grid `grid-cols-2 sm:grid-cols-3 gap-3 max-w-2xl mx-auto mobile:grid-cols-1!` > PostCard×N。
- **样式**：容器没有用全局类，半透明效果完全来自卡片自身。
- **行为（必须保留）**：挂载时请求 GET /plaza/feed?limit=30，不带 sort/tag（后端默认 recommended，匿名时回退 latest，见 backend/routers/plaza.py:23-46）。发布成功后重新拉取。没有分页，也没有加载更多。
- **状态**：没有加载态、空态或错误态：catch 吞掉错误，posts 为空时网格什么都不显示。
- **手机端**：单列，跟随 main 滚动。
- **改造风险**：桌面底栏（absolute h44 z20）会盖住最后一行，因为 py-6 只留了 24px；右下角还被 FAB 盖住。sm: 按 iframe 自身宽度判断（≥640px 为 3 列）。如果新设计要加空态，属于新增行为。

### PostCard 帖子卡 + 点赞动画
- **位置**：app/plaza/page.tsx:39-136（timeAgo 29-37）；globals.css:291-315（hud-like-burst / hud-like-pop）
- **结构**：`.glass-card group overflow-hidden`（59）分两部分。媒体区 `relative aspect-square bg-black/40 overflow-hidden`（60-108）：视频为 video muted loop playsInline，mouseenter 播放、mouseleave 暂停并归零（61-68）；图片为 img alt=""（70-75）；两者都有 `transition-transform duration-500 group-hover:scale-[1.04]`。右上角角标列（78-90）：视频图标块 `rounded-[6px] border bg-black/60 p-1`（边框 var(--glass-border)，Video 10px amber）；likes≥5 时显示 `.tag .tag-amber gap-0.5` Flame+「热门」。左下角标签（92-105）最多显示 2 个 `.tag border bg-black/60 text-[9px] text-white/80`「#t」，超出部分显示「+N」(text-white/70)。底部渐变 `pointer-events-none h-16 bg-gradient-to-t from-black/70`（107）。信息区 `px-3 py-2.5`（110-133）：caption 为 12px、text-foreground/85、line-clamp-2（可选）；底行左侧是 h-6 w-6 rounded-[6px] bg-secondary 方块（显示 anon_id 首字母大写）加 `.readout text-[10px]` anon_id，右侧是 `.readout` timeAgo（刚刚/Nm/Nh/Nd，把 'YYYY-MM-DD HH:MM:SS' 当 UTC 解析）加点赞按钮（123-130：relative flex，Heart 13px，`.readout text-[11px]` 计数，burst>0 时追加 <span key={burst} class=hud-like-pop>+1</span>）。
- **样式**：全局类 .glass-card、.tag、.tag-amber、.readout、.hud-like-burst、.hud-like-pop。硬编码颜色 bg-black/40、bg-black/60、text-white/80、text-white/70、from-black/70。令牌 var(--glass-border)、var(--amber-ink)；已赞为 text-[color:var(--amber-ink)]，未赞为 text-muted-foreground 且 hover 变 amber。hud-like-burst：0.45s 放大到 1.5 并加 drop-shadow rgba(255,80,120,.75)。hud-like-pop：absolute top-4px right-8px，颜色 #ff6680，带 text-shadow，0.75s 上飘淡出。
- **行为（必须保留）**：handleLike（46-56）：已赞直接 return。否则乐观更新：liked=true、likes+1、burst+1（变 key 让动画重播），800ms 后 burst 归零。然后 POST /plaza/like/{id}，错误被吞掉，返回的 likes 不读。liked 只存在组件内存里，刷新页面就重置（后端按登录用户去重，见 backend/routers/plaza.py:105-118）。
- **状态**：已赞态：实心心形加 amber 色。没有禁用态，没有失败回滚，没有加载占位（图片直接加载）。
- **手机端**：单列满宽，作者 id 用 mobile:truncate。视频只靠 mouseenter 播放，又没有 controls 和 poster，触屏上放不了。
- **改造风险**：点赞按钮没有 aria-label 和 aria-pressed。「热门」按初始 post.likes 判断，点赞后不更新。全局 reduced-motion（globals.css:459-468）会关掉 burst/pop 和 hover 缩放过渡。hud-* 类改名时要同步改 globals.css。媒体区的黑色遮罩和标签底色是写死的暗色，换浅色主题时要换成令牌。

### 热点话题展开抽屉
- **位置**：app/plaza/page.tsx:241-268（ExpandedTopic 类型、expanded/expanding 状态、openTopic）、409-516（渲染）；globals.css:447-457（topic-drawer-in）；lib/open.ts:68-90（openExternal）
- **结构**：外层定位层 `absolute z-30 flex items-stretch justify-center pointer-events-none`，内联 top16 bottom56 left260 right260（411-417）。面板 `.glass .topic-drawer-in pointer-events-auto flex flex-col rounded-[10px] border`，width100%、maxWidth920、overflow hidden、边框 var(--glass-border)（418-425）。头部（427-438）：border-b px-5 py-3，Flame 14px(amber) + 标题 truncate 13px，关闭按钮 `.btn .btn-quiet h-7 w-7 px-0`（title=关闭，aria-label=关闭话题详情）。内容区（441-513）`flex-1 overflow-y-auto px-6 py-5 text-sm leading-relaxed space-y-4 mobile:px-4`，依次为：加载行（`.state-dot .state-dot-speaking` + 加载中…）、错误「拉取失败：{error}」var(--rec)、summary（15px，foreground/95）、「发生了什么」、「为什么上热搜」、「关键事实」（ul，每条前面一个 1.5×1.5 的 amber 方块）、「背景」（13px，/75）、「来源」（border-t pt-2）。来源有 url 时渲染 button，点击 openExternal(url)，样式 amber、opacity80、break-all；没有 url 时渲染 span，opacity40，后缀 9px「（链接失效）」，title=AI 整理时未能确认此来源原链接。
- **样式**：全局类 .glass、.btn、.btn-quiet、.state-dot、.state-dot-speaking（颜色 var(--primary)，静态无动画）、.topic-drawer-in。小节标题统一为 text-xs font-medium text-muted-foreground。
- **行为（必须保留）**：openTopic：先立即 setExpanded({title}) 显示标题占位，并置 expanding=true；然后请求 GET /hot/expand?title=…，拿到结果直接 res.json() 展开（不检查 res.ok）。后端日上限触发时返回 429 {detail,error,retry_after}，因为带 error 字段，会走错误显示；后端还限 20 次/分钟。网络异常时显示 error 文本。openExternal 只放行 http/https：Tauri 下用 open_url_in_app 开子窗口，浏览器下用 window.open noopener。关闭只能点 X（没有 Escape、点击外部不关、没有焦点管理、没有 role=dialog/aria-modal）。
- **状态**：加载、错误、各字段缺失时对应段落不渲染、来源有链接和无链接两种。入场动画 topic-drawer-open：360ms，scaleY 0.05→1.02→1。
- **手机端**：手机端为 `mobile:fixed! mobile:top-4! mobile:left-4! mobile:right-4!`；embed 时加 mobile:bottom-4!，否则 mobile:bottom-[calc(56px+env(safe-area-inset-bottom)+16px)]!，避开底部导航（412-415）。
- **改造风险**：连续点两个话题时没有 abort：后返回的结果会覆盖前一个，可能标题和内容对不上；expanding 还会被先返回的请求置成 false。桌面端 left/right 各写死 260px：iframe 宽度小于 520px（父窗口小于约 836px）时面板宽度为 0，看不见；父窗口 1024px 时只有约 125px 宽。

### 底部兴趣横栏（我的兴趣 + 社区兴趣 ticker）
- **位置**：app/plaza/page.tsx:270-271（状态）、286-301（time-prefs）、303-310（community-interests）、518-566（渲染）；globals.css:433-445（ticker）
- **结构**：外层 `.glass pointer-events-none z-20 flex items-center gap-3 border-t px-4`，内联 absolute bottom0 left0 right0、height44、边框色 var(--glass-border)（519-526），内部三块：① 左侧「我的兴趣」（528-545，pointer-events-auto）：Sparkles 12px(amber)、文字 text-xs font-medium muted，后面跟兴趣 chip `.chip h-6 px-2 text-[10px]`（内容为 #tag 的 span）；没有兴趣时显示「点赞后出现」(text-[10px] muted/50)。② 分隔线 h-5 w-px，背景 glass-border（548，mobile:hidden）。③ 右侧 ticker（551-565）`flex-1 overflow-hidden relative mobile:min-h-4`，内含 `.ticker-track gap-5 items-center`，把 communityItems 复制两份串起来；每项 inline-flex mr-5，内容为 `.readout text-[9px]` 匿名用户 + 11px tag（foreground/70）。
- **样式**：全局类 .glass、.chip、.readout、.ticker-track（inline-flex nowrap，ticker-scroll 60s linear infinite 向左 -50%，:hover 时暂停）。
- **行为（必须保留）**：两个请求都要求有 username：GET /plaza/time-prefs 取当前 time_slot 的偏好，没有就退回 global，按分数取前 5（289-300）；GET /plaza/community-interests 取 items[{tag,user}]（306-309）。两者只在 username 变化时拉一次，点赞后不会刷新兴趣。
- **状态**：兴趣为空：「点赞后出现」。社区为空：「暂无其他用户兴趣数据」(muted/40)。没有加载态或错误态（catch 吞掉）。
- **手机端**：`mobile:static! mobile:h-auto! mobile:min-w-0 mobile:flex-col mobile:items-stretch mobile:gap-2 mobile:py-2`；兴趣行 mobile:overflow-x-auto，chip 加 mobile:shrink-0 mobile:whitespace-nowrap；分隔线隐藏。
- **改造风险**：整条横栏是 pointer-events-none，ticker 区没有恢复 pointer-events，所以 .ticker-track:hover 暂停实际上永远不会触发。兴趣 chip 是 span 不是按钮，只做展示。开启 reduced-motion 时 ticker 静止，只显示第一段。gap-5 加 mr-5 等于间距算了两次。

### 发布 FAB + 上传流程 + 发布弹层
- **位置**：app/plaza/page.tsx:16（ALL_TAGS）、225-235（状态与 refs）、312-316（togglePostTag）、318-326（handleFileChange）、328-349（handleSubmit）、351-359（handleClose）、568-581（FAB）、585（隐藏 input）、587-653（弹层）
- **结构**：FAB（569-581）：`btn btn-primary pointer-events-auto z-30 h-14 w-14 rounded-full p-0`，内联 absolute bottom56 right24，图标 Plus 22px strokeWidth2.5 text-primary-foreground，只有 title「发布到我的世界」，没有 aria-label。隐藏 input（585）：type=file，accept="image/*,video/*"，className=hidden。弹层（588-652）：遮罩 `fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4`，内卡 `.glass w-full max-w-sm overflow-hidden rounded-[10px] border mobile:overflow-y-auto`。卡内依次为：头部（596-604）border-b px-4 py-3，Plus(amber) +「发布到世界」，关闭按钮 `.btn .btn-quiet h-7 w-7 px-0`（aria-label=关闭发布面板）；预览（606-612）aspect-square bg-black/50，视频带 controls，图片 alt=""，都是 object-cover；表单区 p-4 space-y-3（614-650），包括 textarea（rows2，placeholder「说点什么…（可选，100字以内）」，`rounded-[6px] border bg-card px-3 py-[9px] text-[13px] focus:border-[color:var(--amber-ink)] mobile:text-base`）、标签区（小标题「标签 · 最多 5」，下面 12 个 ALL_TAGS 按钮 `.chip`，选中时加 `.chip-on` 并带 Check 9px，文案「#tag」）、错误提示 p（role=alert，var(--rec)）、提交按钮 `.btn .btn-primary h-10 w-full`。
- **样式**：全局类 .btn、.btn-primary、.btn-quiet、.glass、.chip、.chip-on。硬编码颜色 bg-black/70（遮罩）、bg-black/50（预览底）。令牌 var(--glass-border)、var(--amber-ink)、var(--rec)、bg-card。
- **行为（必须保留）**：点 FAB 触发 fileRef.click()。input onChange 时：取第一个文件，清空错误，存进 selectedFile ref，按 MIME 判断 video 还是 image，用 URL.createObjectURL 生成预览（从不 revoke），然后 setShowModal(true)。caption 截断到 100 字（后端允许 1000）。标签最多选 5 个，超出时点击无效。ALL_TAGS 必须与 backend/routers/plaza.py:15 PLAZA_TAGS 一致，后端会过滤。handleSubmit：没有文件、正在上传或没有 username 时直接 return；否则组 FormData（caption、tags=JSON 字符串、file）POST /plaza/post。响应不 ok 时，优先用 body.detail 字符串，否则显示「发布失败（status），请重试」；后端可能返回 400 格式不支持或 HEIC 提示、413「文件太大」、409「账号已失效」。成功后调用 handleClose 再 loadPosts。handleClose 会重置预览、文案、标签和 ref，并清空 input.value，这样同一个文件可以再选一次。
- **状态**：提交按钮文案：上传中「正在发布…」，没有 username 时「正在获取账号信息…」，平时「发布」；前两种状态都禁用。错误用 role=alert 显示。没有上传进度。没有表单校验（文案和标签都可以为空）。
- **手机端**：FAB 为 `mobile:fixed! mobile:right-4!`，bottom 在 embed 时 mobile:bottom-16!，否则 mobile:bottom-[calc(56px+env(safe-area-inset-bottom)+64px)]!。弹层遮罩非 embed 时加 mobile:bottom-[calc(56px+env(safe-area-inset-bottom))]!，所以底部导航（z-70）仍然可见可点。内卡 max-h 在 embed 时为 calc(100dvh-2rem)，否则再减去 56px 和 safe-area，内容在卡内滚动。全局把手机端输入框字号设为至少 16px（globals.css:415-420），防止 iOS 自动缩放。
- **改造风险**：弹层没有 role=dialog/aria-modal，没有 Escape，点遮罩不关闭，也没有焦点陷阱（现状；保留还是增强需要在规格里写明）。iframe 里的 fixed 弹层只能盖住 iframe 自己的视口，盖不住宿主抽屉头部。FAB 依赖 .btn 的 inline-flex 居中，h-14 会覆盖 .btn 自带的 34px 高度。

### 匹配页外壳 + Earth3D 背景
- **位置**：app/match/page.tsx:6（import）、151-161（状态）、302-312（embed 判定、根、Earth3D）、421-422、454-468（MatchContent/MatchPage）；components/Earth3D.tsx:1-20
- **结构**：MatchPage 用 <Suspense>，fallback 是 `role=status flex h-dvh items-center justify-center text-sm text-muted-foreground`「加载中…」（464）。MatchContent 在 username 为空时显示同样的加载中（456-458），否则渲染 <MatchForAccount key={username}>。根 div `flex h-screen flex-col overflow-hidden mobile:h-dvh`（非 embed 时加手机底部 56px+safe-area 的 padding）> `flex flex-1 min-h-0` > [Sidebar（非 embed）, 容器 `flex flex-1 min-w-0 relative overflow-hidden mobile:min-h-0 mobile:flex-col`（309）]。容器里有三块：Earth3D（312）、左侧联系人卡、右侧区域。Earth3D 是 div `absolute inset-0 pointer-events-none`，内联背景图 url(/textures/match_bg.jpg)，cover、center、no-repeat，底色 #000。
- **样式**：Earth3D 只用内联样式，不用全局类。它早已不是 3D，组件注释（3-5 行）写明保留这个名字只是为了不改调用方。
- **行为（必须保留）**：MatchForAccount 以 username 为 key：切换账号时整体重新挂载。useAccountRequest(username).isCurrentOwner 用来守卫所有请求（lib/useAccountIdentity.ts:27-62）。
- **状态**：账号未就绪时显示「加载中…」(role=status)。
- **手机端**：容器改为纵向排列，左侧卡在上，右侧区域在下。
- **改造风险**：match_bg.jpg（117KB）只有 Earth3D 在用。这张背景与主题无关，永远是深色照片。Sidebar 的 navItems（Sidebar.tsx:13-19）没有匹配入口，/match 只能通过世界抽屉的「匹配」标签（iframe）或直接输入 URL 进入；独立访问 /match 时 Sidebar 没有任何项高亮。

### 匹配页·最近聊天列表
- **位置**：app/match/page.tsx:163-175（loadRooms）、314-341（渲染）
- **结构**：外层 `.glass-card relative z-10 m-4 mr-0 flex w-64 shrink-0 flex-col overflow-hidden`（315）。头部为 border-b px-4 py-3，文字「最近聊天」(text-xs muted)。列表 `flex-1 overflow-y-auto py-1`（319）：没有会话时显示空态（321-324，User 28px muted/40 +「接受匹配后会出现在这里」11px，容器 h-40）；有会话时每个房间是一个按钮 `.chip h-auto w-full justify-start px-4 py-3 text-left transition-colors hover:bg-secondary`，选中时加 `.chip-on`（326-338），按钮内为 h-9 w-9 rounded-[6px] bg-secondary 方块（显示 peer 首字，amber）+ 名字（text-sm truncate）。
- **样式**：全局类 .glass-card、.chip、.chip-on（.chip 自带的 28px 高度被 h-auto 覆盖）。令牌 var(--glass-border)、var(--amber-ink)。
- **行为（必须保留）**：GET /peer/rooms，取前 5 个，带 isCurrentOwner 守卫。接受匹配后会重新拉取。点击房间调用 openChat(room)。
- **状态**：有空态；选中态为 chip-on。没有加载态或错误态。
- **手机端**：外层改为 `mobile:m-3 mobile:mb-0 mobile:w-auto`。列表改为横向滚动 `mobile:flex mobile:flex-none mobile:overflow-x-auto mobile:overflow-y-hidden`，按钮改为 mobile:w-auto mobile:min-w-32 mobile:shrink-0。空态改为 mobile:h-16 mobile:w-full。
- **改造风险**：列表行直接用了 .chip，改 .chip 的全局样式会波及这里。selected 一旦设置就清不掉，代码里没有回到匹配卡视图的入口（现状）。

### 匹配卡飘动区 + CloudCard
- **位置**：app/match/page.tsx:19-28（PendingMatch）、30-149（CloudCard）、177-214（轮询）、216-249（移除/过期/接受/跳过）、343-363（区域渲染）、423-449（style jsx global）
- **结构**：右侧区域外层 `relative z-10 flex min-w-0 flex-1 flex-col mobile:min-h-0`（344），未选中会话时没有玻璃效果。未选中时渲染飘动区 `flex-1 relative overflow-hidden`（346），里面最多 3 张 CloudCard。CloudCard 外层（58-71）`cloud-card glass-card w-80 px-5 py-4`，按相位加 cloud-in/cloud-stable/cloud-out，内联 position absolute、left x%、top y%、animationDelay idx*0.15s。卡内结构：头像（74-76）h-10 w-10 rounded-[6px] bg-secondary，内放 Sparkles 16px(amber)；头部行（78-83）「神秘好友」(text-sm, foreground/70) + `.tag .tag-amber` 显示 match.type；来由（84-88）10px「因为你聊到了「topic」」；reason（89）text-sm foreground/85；对方招呼（91-99）为 rounded-[6px] border 块，背景 var(--fill)，带 MessageCircle 11px，文字 11px；tags（100-108）为 `.chip h-6 px-2 text-[10px]`。底部操作（135-146）：「算了」`.btn .btn-quiet h-7 px-2.5 text-xs`、「认识下」`.btn .btn-primary h-7 px-2.5 text-xs`。点「认识下」后展开招呼编辑（113-133）：textarea 限 50 字、rows2，样式同发布弹层；下方按钮「跳过」（quiet，只收起编辑区，不会跳过这个匹配）和「发送打招呼」（primary）。
- **样式**：全局类 .glass-card、.tag、.tag-amber、.chip、.btn、.btn-quiet、.btn-primary。style jsx global（423-449）定义：.cloud-card.glass-card 初始 opacity0、translateY(-24px) scale(.96)，transition 为 opacity 1.2s ease-out、transform 1.5s cubic-bezier(.16,1,.3,1)；.cloud-stable 为 opacity1 并播放 cloud-drift（10s ease-in-out 无限循环，上下 3px）；.cloud-out 为 opacity0、translateY(-32px) scale(.95)，过渡 2s/2.5s ease-in，并停掉动画；reduced-motion 时取消 drift。
- **行为（必须保留）**：轮询：挂载时立即请求 GET /match/pending，之后每 8 秒一次（177-214）。只追加新的 id（lastIds 去重），最多同时显示 3 张，多出的等下次轮询再补。每张卡的位置随机 x 5-55%、y 5-65%（198-204），没有位置时回退为 10+idx*8。卡片生命周期（50-55）：800ms 后进入 stable，25 秒后 out，27 秒后调用 onExpire。onExpire、点「算了」、点「发送打招呼」都会 POST /match/pending/{id}/seen；「发送打招呼」还会 POST /match/response {peer, response:"accept", greeting.trim()}，然后 loadRooms，最后移除卡片（221-249）。
- **状态**：没有匹配时什么都不渲染（347，没有空态文案）。卡片有 in/stable/out 三个相位，招呼编辑区有展开和收起两态。没有提交中或错误提示（catch 吞掉）。
- **手机端**：飘动区为 `mobile:flex mobile:min-h-0 mobile:flex-col mobile:gap-3 mobile:overflow-y-auto mobile:p-3`。卡片为 `mobile:static! mobile:w-full mobile:min-w-0 mobile:break-words`（内联的 left/top 因 static 失效）。tags chip 为 mobile:h-auto mobile:max-w-full mobile:break-all mobile:whitespace-normal。手机 textarea 字号为 text-base。
- **改造风险**：用户正在输入招呼时，25 秒过期计时照样在跑，卡片会中途淡出并被标记 seen（现状）。.cloud-card 的规则选择器绑死了 .glass-card，如果换类名，初始 opacity0 会失效。style jsx global 只在匹配页挂载时注入。首页 app/page.tsx 也每 8 秒轮询 /match/pending（601-640），但 MiniCloudCard（149）只定义没渲染，所以首页只轮询，不展示也不标记 seen。

### 匹配页·对话区
- **位置**：app/match/page.tsx:251-300（openChat、自动滚动、WS 清理、发送、键盘）、364-418（渲染）
- **结构**：选中会话后，右侧区域追加 `glass-card m-4 overflow-hidden mobile:m-3`（344）。内部三块：头部（367-372）border-b px-5 py-3，h-7 w-7 rounded-[6px] bg-secondary 首字(amber) + 名字 text-sm；消息列表（375-395）`flex-1 overflow-y-auto px-5 py-4 space-y-3`，自己发的消息右对齐、max-w-[520px]、`.bubble-user`，对方消息左对齐、max-w-[640px]，上方显示 sender（text-xs muted，前面一个 1.5px amber 方点），正文 `.bubble-ai`，列表末尾放 bottomRef；输入区（398-416）`.glass shrink-0 border-t px-4 py-3`，里面是 rounded-[10px] border 的框（背景 var(--fill)），框内 textarea（rows1、max-h-[100px]、透明底、placeholder「发消息…」）和发送按钮 `.btn .btn-primary mb-0.5 h-8 w-8 px-0`（Send 14px，没有 aria-label）。
- **样式**：全局类 .glass-card、.glass、.bubble-user、.bubble-ai、.btn、.btn-primary。令牌 var(--fill)、var(--glass-border)、var(--amber-ink)。
- **行为（必须保留）**：openChat：写入 selectedRoomIdRef，关闭旧的 WebSocket，setSelected，清空消息；GET /peer/history/{roomId}，只有返回的 room_id 一致才写入。随后新建 WebSocket `${WS_BASE}/ws/peer/${roomId}`，非生产环境追加 ?dev_user=。onmessage 有三重守卫（是当前账号、是当前房间、是当前 ws 实例），忽略 history 类型，只把 message 类型追加到列表。消息变化时 bottomRef 平滑滚动到底。卸载时关闭 WS（286-289）。Enter 发送，Shift+Enter 换行（298-300）。连接未 OPEN 时静默不发，发送后清空输入。
- **状态**：发送按钮在输入为空时禁用。没有连接中、断线或发送失败的提示；会话为空时列表空白，没有文案。
- **手机端**：消息为 mobile:max-w-[80vw] mobile:min-w-0，正文 mobile:break-words。头部为 mobile:px-4，输入区 mobile:px-3，发送按钮 mobile:h-10 mobile:w-10 mobile:shrink-0，textarea mobile:text-base。
- **改造风险**：.bubble-user 和 .bubble-ai 是全局类，主对话页也在用，改样式会一起变。WS 逻辑、ref 和守卫与 JSX 写在一起，重排结构时不能动这些。

### 世界抽屉宿主（首页 iframe）与导航入口
- **位置**：app/page.tsx:293-336（drawer/worldTab 状态）、2388-2423（#plaza-drawer）、约 2460-2468（外部点击背板）；components/Sidebar.tsx:13-19、84-180、181-221；app/layout.tsx:15-20、28-58
- **结构**：#plaza-drawer：`glass fixed z-[55] flex flex-col`，内联 top0 bottom0 right0、宽度 calc((100vw-56px)*2/3)、左边框 glass-border；打开时加 boxShadow -12px 0 32px rgba(0,0,0,.28) 和 translateX(0)，关闭时 translateX(105%)，transition 360ms cubic-bezier(.22,.61,.36,1)。手机端加 max-md:left-0、max-md:bottom-[calc(56px+safe)]!、max-md:w-screen!，关闭时 max-md:hidden。头部：「世界」+ 两个 `.chip` 标签「热点与帖子」/「匹配」（当前标签加 chip-on）+ 关闭按钮（title=收起，没有 aria-label）。主体：有 username 时渲染 `<iframe src={worldTab==="plaza"?"/plaza?embed=1":"/match?embed=1"} className="flex-1 w-full border-0">`，否则显示「正在加载身份…」(role=status)。外部点击背板为 fixed left-14 z-50，点击即关闭。
- **样式**：抽屉使用 .glass 和 .chip/.chip-on，头部边框用 var(--glass-border)。
- **行为（必须保留）**：iframe 不会随抽屉关闭而卸载（2388 注释）：只要首页有 username，就会加载 /plaza?embed=1，哪怕用户从没打开过世界。切换标签会改 src，整页重新加载。Sidebar「世界」项指向 /plaza；首页传了 onPlazaClick，所以渲染成按钮。手机导航给它设了 aria-controls=plaza-drawer 和 aria-expanded，桌面侧栏只给 agent/exchange 设了 aria-controls。layout.tsx 的内联脚本只对 embed=1 且身处 iframe 的页面生效，同步父窗口 ≥768px 断点到 data-shell。
- **状态**：身份未就绪时显示占位文字。
- **手机端**：抽屉占满宽度，底部让出导航栏。iframe 内的 mobile: 断点跟随父窗口。
- **改造风险**：layout.tsx:28 把 <html className="dark"> 写死了；useTheme（lib/useTheme.ts）只切换当前文档的 class，不持久化。父窗口切到浅色不会同步到 iframe，所以做昼/夜双主题必须给 iframe 传主题（例如 query 参数或 postMessage，加上持久化）。viewport.themeColor 写死为 #0E1219（layout.tsx:16）。抽屉隐藏后 iframe 里的 SolarSystem3D 仍在跑：它只认 document.hidden，抽屉移出屏幕不会触发；热点 feed 也在后台每 5 分钟刷新。抽屉内 iframe 的宽度决定了两栏遮挡和话题抽屉宽度为 0 的问题。

### 3D 组件引用面与去掉后的影响
- **位置**：components/SolarSystem3D.tsx（唯一引用方 app/plaza/page.tsx:6、371）；components/Earth3D.tsx（唯一引用方 app/match/page.tsx:6、312，另有 343 行注释）；package.json:14-17、26；public/textures/*；lib/usePrefersReducedMotion.ts
- **结构**：SolarSystem3D 是全仓库唯一 import three、@react-three/fiber、@react-three/drei、@react-three/postprocessing 的文件，@types/three 也只有它用。simplex-noise（package.json:24）全仓库无引用，本来就是死依赖。SolarSystem3D 用到 11 张贴图：mercury、venus、earth、mars、jupiter、saturn、uranus、neptune、milkyway(1.9MB)、sun、saturn_ring.png，合计约 7.9MB。earth_clouds_2k、earth_day_2k、earth_night_2k、earth_normal 四张已经没有任何引用。match_bg.jpg 只有 Earth3D 在用。
- **样式**：随 SolarSystem3D 一起消失的还有：扫描线（琥珀 rgba(242,168,60,.012)）、暗角 rgba(0,0,15,.65)，以及 Bloom 和星点。
- **行为（必须保留）**：删除 SolarSystem3D 后：usePrefersReducedMotion 变成孤儿（星图或远山动画可以复用它）；VisibilityController 那套暂停逻辑也随之消失。首页每次加载都会在后台 iframe 初始化一个 WebGL 上下文和全部贴图，删掉后这笔开销就没了；切换世界/匹配标签也不会再反复创建 WebGL 上下文。plaza 页里除第 6 和 371 行外，没有任何代码依赖这个组件（无 ref、无回调、无 props）。
- **状态**：删除后不影响热点、帖子、发帖、兴趣这些数据流。
- **手机端**：替换品在手机端要单独决定背景是跟随 main 滚动（现状）还是固定。
- **改造风险**：如果同时从 package.json 移除 three 系依赖，package-lock.json 会大幅改动，CI 的 npm audit --omit=dev 结果也会变。不移除的话，代码不再 import 它们，构建也不会打包进去。CI 的 lint 要求 --max-warnings=38（.github/workflows/quality.yml），删掉 SolarSystem3D 会同时删掉 3 处 eslint-disable 注释。新组件不得新增警告。Earth3D 改名或删除只需动 match/page.tsx:6、312 两处，还要清掉 343 行的注释。

### 跨区域要点
- 断点：mobile: 是自定义变体（globals.css:7-13），条件为 (width<48rem) 且 :root 不带 data-shell="desktop"。layout.tsx:30-58 只对 embed=1 的 iframe 按父窗口 ≥768px 设置 data-shell。两页同时还在用标准 sm:（plaza:404）。宿主抽屉和 Sidebar 用的是标准 md:/max-md:，它们不认 data-shell。规格里必须写明哪些断点跟父窗口、哪些跟 iframe 自身宽度。
- 主题：<html className="dark h-full"> 写死在 layout.tsx:28。:root（globals.css:55-112）是浅色，.dark（115-164）是深色主主题。useTheme（lib/useTheme.ts:16-19）只 toggle 当前文档 html 的 class，没有持久化，也不同步到 iframe。iframe 页隐藏了 Sidebar，自己没有切换主题的按钮。所以世界/匹配在抽屉里永远是深色，昼天青/夜建盏两套主题需要新增从父页到 iframe 的主题传递和持久化。themeColor #0E1219 也写死在 layout.tsx:16。
- 两页用到的全局类（globals.css 行号）：.glass 183-189（blur22 saturate1.5、背景 var(--glass-strong)、var(--grain) 噪点、inset 高光）；.glass-card 192-200（blur14、背景 var(--glass)、1px var(--glass-border)、圆角 10px）；.readout 203-209（等宽字体、tabular-nums、12px、muted）；.state-dot / .state-dot-speaking 239-241；.btn / .btn-primary / .btn-quiet 244-256；.chip / .chip-on 259-264；.tag / .tag-amber 265-269；.bubble-user / .bubble-ai 273-281。这两页没用到 .echo 和 .signal。这些类是全站共用的，改类定义等于全站换肤，plaza/match 自身只需改用法。
- 现成的玻璃退路：globals.css:284-289。一是 @supports not (backdrop-filter) 时 .glass/.glass-card 退成 var(--card) 实底；二是 prefers-reduced-transparency 时去掉 backdrop-filter。「素瓷」不透明退路可以挂在这两处，或者加一个类/属性开关。
- 全局 reduced-motion（globals.css:459-468）会把所有 animation 设为 none!important、transition 设为 0.01ms。受影响的有 ticker、topic-drawer-in、hud-like-burst/pop、animate-spin、cloud-drift，以及 CloudCard 的入场和离场过渡（卡片会瞬间出现、瞬间消失）。新做的远山语音线、朱印等动画也会被同一规则压掉。
- plaza/match 里需要换成令牌的硬编码颜色：plaza 60 bg-black/40、80/95/100 bg-black/60、95 text-white/80、100 text-white/70、107 from-black/70、588 bg-black/70、607 bg-black/50；globals.css:294 rgba(255,80,120,.75)、308 #ff6680、312 rgba(255,102,128,.9)；SolarSystem3D 219、227 及大气色；Earth3D 的 #000；首页抽屉阴影 rgba(0,0,0,.28)。其余颜色都已经走令牌：--amber-ink、--rec、--glass-border、--fill、--primary、--card、--secondary、--muted-foreground。
- CSP（next.config.ts）：font-src 'self' data:，style-src 'self' 'unsafe-inline'，img-src 'self' blob: data:。思源宋体不能直接引用 Google Fonts 的 CDN 样式表和字体文件，必须自托管，或用 next/font 在构建期下载后自托管。内联 SVG（星图、远山、烟雨、透镜滤镜）不受影响。
- 字体：body 用 var(--font-sans-stack)（globals.css:56，系统中文字体）；.readout 用 var(--font-mono-stack)；Tailwind 的 --font-heading 也指向 sans（globals.css:18-20）。目前没有任何 next/font 或 @font-face。
- body 背景（globals.css:166-179）是三层固定光斑渐变：var(--spot-a/b/c)，background-attachment fixed。世界页手机端滚动离开 3D 背景后，露出的就是这层；在 iframe 里它也会透过 .glass 显示出来。
- 两页的数据接口：GET /plaza/feed?limit=30、POST /plaza/like/{id}、GET /plaza/time-prefs、GET /plaza/community-interests、POST /plaza/post（multipart：caption/tags/file）、GET /hot/微博、GET /hot/抖音、GET /hot/categorized/all、GET /hot/expand?title=；GET /peer/rooms、GET /peer/history/{room}、WS /ws/peer/{room}、GET /match/pending、POST /match/pending/{id}/seen、POST /match/response。全部经 lib/auth.ts:125-147 的 apiFetch 发出：Cookie 鉴权，开发环境带 X-Dev-User 头，遇到 401 时让顶层窗口跳转登录页（iframe 内也一样）。
- 前端没有任何自动化测试（无 tests/e2e 目录）。CI（.github/workflows/quality.yml）只跑 lint --max-warnings=38、tsc --noEmit、next build、npm audit。复刻是否到位只能靠截图和结构判据来验收。
- 页面里的空态/加载/错误文案（要求一字不改时可照抄）：「拉取中…」「暂无可显示的热点」「暂时没有相关热点」「更新失败，显示上次内容」「实时更新暂不可用，显示上次内容」「部分来源暂不可用」「重试」「重试中…」「获取于 HH:MM」「加载中…」「拉取失败：」「（链接失效）」「点赞后出现」「暂无其他用户兴趣数据」「正在发布…」「正在获取账号信息…」「发布」「接受匹配后会出现在这里」「最近聊天」「神秘好友」「算了」「认识下」「跳过」「发送打招呼」「发消息…」。帖子流和匹配卡区为空时什么都不显示，没有空态文案。

## pages：Fiona 前端其余页面：/login（含开发测试入口）、/settings、/history、/profile、/agents/[id]、/agents（AgentExchangeWorkspace）、/agents/me（MyAgentWorkspace + AgentIdentityCard + AgentMemoryPanel）。HEAD 586d86a，只读调研。下文的相对路径都以 frontend 为根。哪些页面以 ?embed=1 放进抽屉 iframe：只有 /settings 和 /profile，见 app/page.tsx:2456 的设置抽屉，其中「设置」chip 对应 /settings，「账户」chip 对应 /profile。/agents 和 /agents/me 背后的两个组件在主页里是直接内嵌，传 embedded 这个 prop，不经过 iframe，也不带 embed 参数（app/page.tsx:2356、2385）。/login、/history、/agents/[id] 从不内嵌；其中 /history 由 window.open 在新标签页打开（app/page.tsx:2001）。
### 登录页 · 外壳与品牌区（Logo / echo 字标 / 标语 / 信号线）
- **位置**：frontend/app/login/page.tsx:136-147（整个组件 12-283；没有 Sidebar、Suspense、embed 分支）
- **结构**：根节点 div `flex min-h-screen items-center justify-center px-6` 让内容整体居中。里面是列容器 `flex w-[360px] flex-col gap-8`。列容器第一块是品牌块 `flex flex-col gap-3`，依次为：(1) 双圆 Logo SVG，28×28，两个 r=5.5 的圆，stroke 1.5，aria-hidden，图形与 components/Sidebar.tsx:86-90 相同；(2) `div.echo text-[44px] data-text="Chloe"` 字标；(3) 标语 p，15px，muted，内容「每个人自己的分身。」；(4) `<Signal mode="idle" className="mt-2"/>`。品牌块下面是表单玻璃卡（149），再下面是开发测试入口（249）。
- **样式**：Logo 用 text-[color:var(--amber-ink)]。.echo 定义在 globals.css:212-231：::after 用 attr(data-text) 画一个 amber-ink 1px 描边的偏移副本，opacity .6，white-space:nowrap。.signal 定义在 globals.css:234-236：高 40px，path 的 stroke 和 circle 的 fill 都是 amber-ink。标语用 text-muted-foreground。页面背景来自 body 的三层 radial-gradient（--spot-a/b/c）叠在 --background 上，并且 background-attachment:fixed（globals.css:168-178）。
- **行为（必须保留）**：Signal 组件在 components/Signal.tsx:9-98。它用 requestAnimationFrame 循环，每帧重写 path 的 d（140 个点）；idle 模式下有一个圆点从左扫到右。命中 prefers-reduced-motion 时画成直线并隐藏圆点。整个 SVG 是 aria-hidden，viewBox 0 0 1000 40，preserveAspectRatio=none。登录页只用 idle 模式。
- **状态**：无。
- **手机端**：窄屏（max-md）：根节点改为 min-h-dvh px-4 py-6 pb-[calc(24px+env(safe-area-inset-bottom))]；列容器改为 w-full min-w-0 gap-6。
- **改造风险**：Signal 还有一个消费者在主页头部（app/page.tsx:2127，mode=signalMode，窄屏 col-span-2 row-start-2 h-6），换成远山状态线时两处都要满足。.echo 还被 AgentIdentityCard.tsx:13 使用，它的 ::after 依赖 data-text 与可见文本一致。登录页不读 `?reason=` 参数：lib/auth.ts:28 会带 expired，settings/page.tsx:83/91/119 会带 logout 或 deleted，但页面目前不显示任何提示。layout.tsx:28 把 html 写死为 class="dark"，登录页又没有主题切换，所以登录页永远是夜间主题。

### 登录页 · 表单玻璃卡（invite / phone / otp 三步状态机）
- **位置**：frontend/app/login/page.tsx:10-21（状态）、49-134（三个 handler）、149-247（JSX）
- **结构**：外层 `div.glass rounded-[10px] border p-[22px]`（行内 style 设 borderColor 为 var(--glass-border)），内层 `flex flex-col gap-3.5`，按 step 渲染不同内容：
- step="invite"（151-175）：label「邀请码」包住 input（type text，autoFocus）；然后是错误 p；最后是主按钮「进入」，loading 时显示「进入中…」。
- step="phone"（176-204）：label「手机号」里是一个伪输入框 div（用 focus-within 改边框色），里面有 "+86" 前缀 span 和 input（type tel，inputMode numeric，autoFocus）；然后是错误 p；最后是按钮「获取验证码」，loading 时显示「发送中…」。
- step="otp"（205-242）：label 的头部一行左边是「验证码」、右边是手机号；input 为 type text、inputMode numeric、maxLength 6、autoFocus；然后是错误 p；主按钮「登录 / 注册」（loading 时「验证中…」）；次按钮 btn-quiet「换个手机号」。
三步的底部都有同一段说明 p（245）：「内测阶段凭邀请码进入。登录即同意用户协议，新用户赠送 <b.readout>200</b> 颗草莓。」
- **样式**：.glass 定义在 globals.css:183-189：背景 --glass-strong，叠 --grain 噪点，backdrop blur(22px) saturate(1.5)，并有 inset 高光阴影。
输入框公用类串：`w-full rounded-[6px] border bg-card px-3 py-[9px] text-sm outline-none placeholder:text-muted-foreground focus:border-[color:var(--amber-ink)] disabled:opacity-50`。邀请码输入框（161）另加 `font-mono tracking-[0.2em] placeholder:font-sans placeholder:tracking-normal`；验证码输入框（221）另加 `font-mono tracking-[0.3em]`；手机号容器（179）用 `focus-within:border-[color:var(--amber-ink)]`。
错误文字：`text-xs text-[color:var(--rec)]`（166、195、226）。
按钮：`btn btn-primary w-full h-10`（171、200、231）和 `btn btn-quiet w-full`（238）。
label：`flex flex-col gap-1.5 text-xs font-medium`。
- **行为（必须保留）**：handleRedeem（49-77）：先用 loading 防重入；邀请码 trim 后转大写，为空时提示「请输入邀请码」；然后 POST `${API}/auth/redeem-invite`，body 为 {code}，带 credentials include。响应不 ok 时显示 data.detail，没有则显示「邀请码无效」；ok 时调用 setAuth(data.username, data.balance ?? 200)，再 router.replace("/")；网络异常显示「网络错误，请重试」。邀请码输入框的 onChange 会自动转大写并去掉空白（159）。

handleSendOtp（79-105）：手机号要通过 /^1[3-9]\d{9}$/，否则提示「请输入正确的手机号」；POST /auth/send-otp，body {phone}；成功后 setStep("otp")。手机号 onChange 只保留数字并截到 11 位（187）。

handleVerify（107-134）：验证码长度不是 6 时提示「验证码是 6 位数字」；POST /auth/verify-otp，body {phone, code}；成功后 setAuth，再 replace("/")。验证码 onChange 只保留数字并截到 6 位（219）。

每个输入框按 Enter 都会触发对应的 handler。「换个手机号」会 setStep("phone")，并清空 code 和 err。

按钮禁用条件：invite 步在邀请码为空或 loading 时；phone 步在手机号不足 11 位或 loading 时；otp 步在验证码不足 6 位或 loading 时。
- **状态**：- 加载态：按钮文案改变，输入框 disabled（opacity .5）。
- 错误态：一行红字，没有 role=alert，也没有 aria-live。
- 禁用态：按 .btn:disabled 显示，opacity .45，cursor not-allowed（globals.css:252）。
- 没有成功态，成功后直接跳转。
- **手机端**：卡片随列容器 w-full，没有专门的断点。窄屏下 globals.css:415-420 把 input 字号强制设为 ≥16px（防止 iOS 聚焦时自动放大）。
- **改造风险**：现在的 UI 里 phone 和 otp 两步走不到：初始 step 是 "invite"，只有 otp 步里的「换个手机号」（237）会 setStep("phone")，而 invite 步没有任何入口进入 phone 步。所以如果设计稿画了手机号登录，要先拍板这段死代码是保留还是复刻。

输入框靠 label 包裹来关联（没有 htmlFor），改结构时不要把 label 和 input 拆开。错误文案来自后端 detail，长度不固定。「用户协议」只是文字，不是链接。三处 autoFocus 要保留，切换步骤后依靠它把焦点放进新输入框。

### 登录页 · 开发测试入口
- **位置**：frontend/app/login/page.tsx:20-21（showTest/testUser）、23-47（handleTestLogin）、249-279（JSX）
- **结构**：位置在表单卡下方、同一个列容器里，外层是 `div.pt-3 border-t border-border/30 space-y-2`。
- 未展开时：只有一个 `btn btn-quiet w-full`，文案「开发测试入口（跳过登录）」。
- 展开后：`space-y-2` 容器里有一个 input（type text，placeholder「测试用户名（默认 tester）」，初始值 "tester"）和一个 `btn btn-quiet w-full`「以测试身份进入」（loading 时「进入中…」）。
- **样式**：输入框用登录页公用类串（267），不带 font-mono。分隔线是 border-border/30。
- **行为（必须保留）**：渲染条件是 `process.env.NODE_ENV !== "production"`，构建时内联，生产包里整块消失。
点击后 POST `${API}/auth/test-login`，body {username: testUser.trim() || "tester"}，带 credentials include。响应不 ok 时显示 detail，没有则显示「测试登录失败（后端是否 DEV_MODE=1？）」；ok 时 setAuth 后 router.replace("/")；网络异常显示「网络错误」。输入框按 Enter 也会触发。
后端还要求 DEV_MODE=1 且请求来自回环地址（见 Fiona/CLAUDE.md 鉴权一节）。
- **状态**：loading 时按钮禁用并改文案。错误不显示在入口旁边，而是复用上方表单卡当前步骤里的 err 段落。
- **手机端**：无断点差异。
- **改造风险**：NODE_ENV 守卫必须原样保留，这是安全边界。错误提示显示在上方卡片里，改布局时要保证 err 仍然看得到。测试输入框不会 disabled，handleTestLogin 也没有 loading 防重入，所以 Enter 可以重复触发请求（现状）。settings/page.tsx:30-41 的「切换测试身份」走的是同一个端点。

### 设置页 · 外壳 / 页头 / embed 分支
- **位置**：frontend/app/settings/page.tsx:12-15（embedded 由 ?embed=1 判定）、127-139、234-240（Suspense fallback=null）
- **结构**：根节点 `div flex h-dvh flex-col overflow-hidden`，下一层 `flex flex-1 min-h-0`，里面依次是：
1. `{!embedded && <Sidebar/>}`；
2. 右列 `flex flex-col flex-1 min-w-0`：
   - header `glass sticky top-0 z-[2] shrink-0 border-b px-8 pb-[18px] pt-7`，行内 style borderColor 为 var(--glass-border)。header 里是 `flex max-w-[976px] items-end justify-between gap-4`：h1「设置」（text-xl font-medium tracking-[-0.01em]）加 p「账号与数据管理」（13px muted）；
   - 内容滚动区 `max-w-lg flex-1 space-y-3 overflow-y-auto px-8 py-6`：这个滚动容器本身限宽 512px 并靠左，滚动条出现在 512px 处，而不是窗口右缘。
- **样式**：.glass 页头。Sidebar 有两套：桌面竖条（components/Sidebar.tsx:84）`.glass w-14 border-r bg-sidebar max-md:hidden`；窄屏底部标签栏（181-221）`.glass fixed inset-x-0 bottom-0 z-[70] h-[calc(56px+env(safe-area-inset-bottom))] md:hidden`。
- **行为（必须保留）**：作为 iframe 被内嵌的方式：app/page.tsx:2456 写的是 `src={settingsTab==="settings" ? "/settings?embed=1" : "/profile?embed=1"}`。

设置抽屉在 2426-2460。顶栏 chips「设置/账户」用来切换 src，一切换 iframe 就整页重载。抽屉关闭时只做 translateX(105%)，不卸载 iframe。宽度为 calc((100vw - 56px) * 2 / 3)，动画 360ms cubic-bezier(.22,.61,.36,1)。

embed 时既不渲染 Sidebar，也不加底部 56px 留白。

layout.tsx:30-58 有一段内联脚本：只有在 embed=1 且确实处于 iframe 中时，才按父窗口是否满足 (min-width:768px) 给 html 设置或移除 data-shell="desktop"，并监听断点变化，pagehide 时解绑。
- **状态**：Suspense 的 fallback 是 null，首帧空白。
- **手机端**：这一页只用自定义的 `mobile:` 变体，定义在 globals.css:7-13，含义是视口 <48rem 且 :root 上没有 data-shell="desktop"。具体用法：
- 非 embed 时根节点加 `mobile:pb-[calc(56px+env(safe-area-inset-bottom))]`（128）；
- 页头加 `mobile:px-4 mobile:pt-4`（132）；
- 内容区加 `mobile:min-w-0 mobile:px-4 mobile:py-4`（141）。

iframe 放在桌面父窗口里时，自己的视口只有 (100vw-56px)*2/3；比如父窗口 1024 宽时约 645px，小于 768，但 data-shell 让它保持桌面排版。父窗口小于 768 时，抽屉变成全宽，同时去掉 data-shell，切到手机排版。
- **改造风险**：- 改断点必须继续用 `mobile:`，不能换成 `max-md:`，否则在桌面抽屉的 iframe 里会被误切成手机排版。
- 抽屉顶栏写着「设置」，页内 h1 也是「设置」，出现双标题。
- iframe 文档的 body 会画自己的不透明渐变背景（globals.css:172-177），抽屉的 .glass 透不过 iframe。如果要做「背后一幅烟雨平远 SVG」，iframe 里要么再画一份，要么把背景改成透明。
- iframe 文档的 html 同样写死了 dark。父窗口的 useTheme 只切换自己文档的 class（lib/useTheme.ts:18），而且不持久化，所以主题切换传不进 iframe。
- 设置抽屉这个 div 没有 role、aria-hidden、inert，也不响应 Escape（app/page.tsx:2426-2460）；分身抽屉（2328-2357）则都有。

### 设置页 · 当前身份卡（测试身份切换 / 退出登录）
- **位置**：frontend/app/settings/page.tsx:16、22-23、25-41、60-97、142-172
- **结构**：外层 `div.glass-card space-y-3 p-5`，自上而下：
1. 标题行：User 图标（14，amber）加「当前身份」，text-sm font-medium；
2. chips 行 `flex flex-wrap gap-2`：取 allUsers；allUsers 为空时取 [username]。每个用户渲染一个 `<button class="chip …">`，当前用户加 chip-on。没有身份时显示 span「正在加载身份…」；
3. 说明 p，11px，muted/60：「当前使用服务端 HttpOnly 会话；开发环境仍可切换测试身份。」；
4. 按钮 `btn w-full`：LogOut 图标加「退出登录并撤销现有会话」，进行中显示「正在退出…」；
5. logoutError：p role="alert"，text-xs，text-[color:var(--rec)]。
- **样式**：.glass-card 定义在 globals.css:192-200：背景 --glass，叠 grain，blur(14px)，1px glass-border 边框，圆角 10px，inset 高光。
.chip 和 .chip-on 定义在 259-264，chip-on 为 amber-ink 文字和边框、--accent 底色。
图标颜色写在行内 style，值为 var(--amber-ink)（145）。按钮用 .btn。
- **行为（必须保留）**：挂载时 GET `${API}/users`（25-28）；这个端点只在 DEV_MODE 下存在，生产返回 404，前端就用空列表。

switchUser（30-41）：点的是当前用户，或者 NODE_ENV=production，直接 return。否则 POST /auth/test-login {username}，成功后 setAuth，派发 fiona-user-changed 事件，所有订阅 useAccountIdentity 的组件会按新账号重新挂载。失败时静默。

logout（69-97）：先防重入，然后 apiFetch POST /auth/logout，并传 {redirectOnUnauthorized:false}。
- 返回 401：clearAuth，再 redirectTop("/login?reason=logout")；
- 其他非 ok：提示「退出失败，会话仍可能有效。请重试。」；
- ok：clearAuth，再 redirectTop；
- 网络异常：提示「网络错误，退出未完成。请重试。」。

redirectTop（60-67）用 window.top.location.replace 跳转，能跳出 iframe。退出没有二次确认。

username 来自 useAccountIdentity（lib/useAccountIdentity.ts:20-23），用 useSyncExternalStore 读 localStorage 里的 fiona_user。
- **状态**：- 身份加载中：显示「正在加载身份…」。
- 退出中：按钮 disabled，文案改变。
- 退出失败：role=alert 的红字。
- **手机端**：chips 加 `mobile:h-auto mobile:max-w-full mobile:break-all mobile:whitespace-normal`（153）；退出按钮加 `mobile:h-auto mobile:min-h-10 mobile:break-all mobile:whitespace-normal`（166），防止长用户名把版面撑破。
- **改造风险**：生产环境下 chips 只有当前用户一个，点了也没反应，但它仍然是 <button>。如果改成纯展示样式，要保留开发环境的切换功能。redirectTop 必须保持跳顶层窗口。

### 设置页 · 数据管理卡（清空聊天记录 / 永久删除账号）
- **位置**：frontend/app/settings/page.tsx:17-21、43-58、99-125、174-214
- **结构**：外层 `div.glass-card space-y-3 p-5`，自上而下：
1. 标题行：Trash2 图标（amber）加「数据管理」；
2. `btn btn-danger w-full`：Trash2 加「清空「{username}」的所有聊天记录」，没有身份时显示「正在加载身份…」；
3. cleared 为真时显示 p「已清空」，颜色 amber-ink（189）；
4. clearError：p role=alert（191）；
5. 删号子块 `space-y-2 border-t pt-3`（borderColor 为 glass-border），内含：
   - p「永久删除账号」，text-xs，--rec 颜色；
   - 11px 说明「输入当前用户名 <span.readout text-foreground>{username}</span> 确认。此操作不可恢复。」；
   - input：没有 label，也没有 aria-label，placeholder 为 username；
   - `btn btn-danger w-full`：Trash2 加「永久删除账号及全部数据」，进行中显示「正在删除…」；
   - deleteError：p，没有 role（212）。
- **样式**：.btn-danger 定义在 globals.css:257-258：透明底、--rec 文字，hover 时底色变 --rec-soft。
输入框用公用类串（202），但没有 disabled 样式。另外用到 .readout 和 --rec。
- **行为（必须保留）**：clearHistory（43-58）：
1. 没有 username 时直接返回；
2. window.confirm(`确定清空「${username}」的所有聊天记录？此操作不可恢复。`)；
3. apiFetch DELETE `${API}/history`；
4. 不 ok 显示「清空失败，请重试」；ok 时 setCleared(true)，3 秒后复位；网络异常显示「网络错误，请重试」。

deleteAccount（99-125）：
1. 必须输入框内容 === username，且当前不在删除中；
2. window.confirm(`将永久删除「${username}」的账号、聊天、画像、匹配、帖子和上传文件。确定继续？`)；
3. apiFetch DELETE `${API}/account`，body {confirmation}；
4. 不 ok 显示 detail，没有则显示「删除失败，请重试」；
5. ok 时，如果 !data.file_cleanup_complete，弹 window.alert(「账号数据已删除，但有媒体文件需要管理员继续清理。」)；
6. 然后 clearAuth，再 redirectTop("/login?reason=deleted")；
7. 网络异常显示「网络错误，请重试」。
- **状态**：清空：
- 没有加载态，按钮不会被禁用；
- 成功提示显示 3 秒；
- 错误为 role=alert。

删号：
- 用户名没输对、没有身份或正在删除时，按钮 disabled；
- 删除中改文案；
- 错误红字没有 role。
- **手机端**：两个危险按钮都加 `mobile:h-auto mobile:min-h-10 mobile:whitespace-normal`，183 行那个另加 break-all。readout 用户名加 `mobile:break-all`（195）。
- **改造风险**：两次 confirm 和一次 alert 都是浏览器原生弹框，而且运行在 iframe 文档里。如果改成自绘对话框，只能盖住抽屉 iframe 那块区域，还要自己做焦点陷阱和 Escape 关闭。

「输入用户名匹配」和 confirm 这两道闸都必须保留。

现状缺陷：deleteError 没有 role=alert，确认输入框没有可访问名称。

### 设置页 · 关于卡
- **位置**：frontend/app/settings/page.tsx:216-226
- **结构**：`div.glass-card space-y-2 p-5`：标题行是 Info 图标（amber）加「关于」，下面两行 11px 文字：「Chloe AI 助理 · 内测版」，以及「账号数据保存在部署服务器的 SQLite 与 uploads 目录」（第二行为 text-muted-foreground/50）。
- **样式**：.glass-card、text-muted-foreground、/50 透明度。
- **行为（必须保留）**：无。
- **状态**：无。
- **手机端**：无差异。
- **改造风险**：muted-foreground/50 在新的昼间浅色主题下对比度需要复核。

### 历史页 · 入口、身份守卫与外壳
- **位置**：frontend/app/history/page.tsx:366-396（HistoryContent/HistoryPage）、42-61（拉取数据）、144-145（根节点）；入口在 app/page.tsx:2001 和 components/ConversationPicker.tsx:98「完整历史」
- **结构**：这一页不在任何抽屉或 iframe 里。主页会话列表的「完整历史」调用 window.open(`/history?user=${encodeURIComponent(username)}`, "_blank", "noopener,noreferrer")，在新标签页打开。

页面本身没有 Sidebar、没有返回链接、没有主题切换。

HistoryContent 的逻辑：
- identity 为空时，全屏居中显示「加载中…」（role=status）；
- ?user 和当前身份不一致时，router.replace 把 user 参数去掉（scroll:false）；
- 正常情况渲染 HistoryForAccount，key=username。

HistoryForAccount 的根节点是 `flex min-h-screen flex-col text-foreground`。Suspense 的 fallback 也是「加载中…」（role=status）。
- **样式**：text-muted-foreground。根节点没有自己的背景，用的是 body 渐变。
- **行为（必须保留）**：数据请求：apiFetch GET `${API}/history`，带 AbortSignal，并由 useAccountRequest（lib/useAccountIdentity.ts:27-58）防止换号后串数据；取 d.messages，`.catch(()=>{})` 把错误吞掉。401 由 apiFetch 统一处理，让顶层页面跳到 /login?reason=expired。

消息结构 Msg：{id, role, content, image_path, reference_image_paths?, created_at}，其中 created_at 是 UTC 时间，格式 "YYYY-MM-DD HH:MM:SS"。

时间处理：parseUtcTimestamp（32-34）给时间补上 Z 再解析；toDateStr（25-30）按本地时区分日。
- **状态**：加载中显示「加载中…」。拉取失败和真的没有记录一样，都显示「还没有聊天记录」，没有单独的错误态。
- **手机端**：根节点加 max-md:min-h-dvh max-md:min-w-0。
- **改造风险**：页面没有导航，复刻「桌面竖排书签导航」时要先决定加不加。新标签页打开时主题永远是 dark：layout 写死了 dark，useTheme 又不持久化。整页是文档滚动，见下面消息区一节。

### 历史页 · 顶栏（标题与计数 / 搜索 / 导出）
- **位置**：frontend/app/history/page.tsx:147-184；导出逻辑 123-135
- **结构**：header `glass sticky top-0 z-20 flex items-center gap-3 border-b px-5 py-2.5`（borderColor 为 glass-border），从左到右三块：
1. 标题块 `shrink-0`：p「历史记录」（text-sm font-medium），下面一行 p「{username} · <span.readout><b>{总数，加载中为…}</b> 条</span>」；
2. 搜索框（伪输入框）`flex flex-1 items-center gap-2 rounded-[6px] border bg-card px-3 py-[9px] focus-within:border-[color:var(--amber-ink)]`，里面是 Search 图标（13）、input（placeholder「搜索消息内容…」；ref searchRef 没有被使用；没有 label），以及有内容时出现的清除按钮 `btn btn-quiet h-7 w-7 shrink-0 px-0`（X 图标 12，没有 aria-label）；
3. 导出按钮 `btn shrink-0`：Download 图标（12）加「导出」；有筛选时再加 `<span.readout>({n}条)</span>`。
- **样式**：.glass、var(--glass-border)、.readout b、.btn/.btn-quiet、bg-card、聚焦时 amber 边框。
- **行为（必须保留）**：搜索实时过滤（101-110），对 content 做大小写不敏感的 includes，没有防抖。

导出 handleExport（123-135）：
1. 先校验 isCurrentOwner；
2. 按当前 filtered 生成每行文本：`[本地时间，zh-CN，hour12:false] {username 或 Chloe}: content`；
3. 生成 text/plain;charset=utf-8 的 Blob，用临时 a 标签下载，文件名 `Chloe_${username}_${YYYY-MM-DD}.txt`；
4. click 后 revokeObjectURL。

0 条消息时导出按钮也能点，会导出一个空文件，没有禁用态。
- **状态**：loading 时计数显示「…」。导出按钮没有禁用态，也没有错误态。
- **手机端**：窄屏（max-md）：
- header 改为 flex-wrap gap-2 px-4；
- 标题块限宽 max-w-[60vw]，并 truncate；
- 搜索框 order-3 basis-full，换到第二行全宽；
- 导出按钮 ml-auto，(n条) 计数 max-md:hidden。
- **改造风险**：清除按钮和搜索输入框都没有可访问名称（现状）。这里 sticky 用的是 z-20，比其他页面常用的 z-[2] 高。

### 历史页 · 左侧日期导航（快捷筛选 / 自定义区间 / 按日跳转）
- **位置**：frontend/app/history/page.tsx:63-99（dateStats、applyQuick、selectDay）、137-142（quickLabels）、186-264
- **结构**：主体是一行 `flex flex-1 min-h-0`，左边是 aside `glass flex w-56 shrink-0 flex-col border-r`，分三段：

A 快捷筛选（191-209）：小标题加 4 个 chip 按钮「全部/今天/近7天/本月」。按钮类为 `chip h-auto w-full justify-start px-3 py-1.5 text-left`，纵向排列，gap-0.5。

B 自定义区间（212-240），上方有 border-t：
- 小标题：Calendar 图标（12，amber）加「自定义区间」；
- 两个 `<input type="date">`，类里带 readout，没有 label，中间夹一个 10px 的「至」；
- 有值时显示「清除筛选」按钮（btn btn-quiet h-7）。

C 按日期跳转（243-263），上方有 border-t，容器 `flex-1 overflow-y-auto`：小标题加「每天一个 chip 按钮」。按钮左侧是 readout 11px 的 MM-DD，右侧是 readout 10px 的条数，两端对齐（justify-between）；选中的那天加 chip-on。
- **样式**：.glass、.chip/.chip-on、.readout、Calendar 图标行内 amber、mobile-scrollbar-none（globals.css:422-430）、分隔线 var(--glass-border)。
- **行为（必须保留）**：applyQuick 的四种取值：
- today：今天到今天；
- week：今天往前 6 天到今天；
- month：本月 1 日到今天；
- all：清空日期区间。

selectDay(day)：把 quick 设为 "all"，并把起止日期都设为 day。手动改任一日期输入框，也会把 quick 设为 "all"。

快捷 chip 的高亮条件（200）是 `quick===key && dateFrom===(key==="all" ? "" : dateFrom)`。结果是：选了某一天或手填日期之后，「全部」不亮，其他快捷项也不亮。

按日 chip 在起止日期都等于这一天时高亮。dateStats 由全部消息算出，不受筛选影响，按日期降序。
- **状态**：没有消息时 C 段只剩小标题。没有加载态。
- **手机端**：窄屏（max-md）下各部分的变化：
- aside：变为 w-full，下边框代替右边框（border-b，border-r-0）；
- A 段：变为 4 列网格（grid grid-cols-4 gap-1），chip 内容居中、px-1；
- B 段：变为单列网格（grid grid-cols-1），日期输入框 px-1.5；
- C 段：容器改为 flex-none overflow-x-auto overflow-y-hidden，内层改为 flex-row，chip 为 w-auto shrink-0，横向滚动并隐藏滚动条。
- **改造风险**：根据代码推断（未实测）：根节点是 min-h-screen，不是固定高度，所以 main 和 aside 都会被内容撑高，实际滚动的是整个文档。aside 不是 sticky，会随页面一起滚走；C 段的 overflow-y-auto 在桌面上基本不起作用。如果改成固定高度布局，滚动容器就变了，会影响 sticky 顶栏和手机端 overflow-visible 的设定。

原生日期控件的配色由 color-scheme 决定，而现在没有设置 color-scheme。

### 历史页 · 消息区（筛选摘要 / 空态 / 按日折叠组 / 消息块 / 图片）
- **位置**：frontend/app/history/page.tsx:101-121（filtered、groups）、266-360、36-40（formatDisplayDate）
- **结构**：main `flex-1 overflow-y-auto px-6 py-5 space-y-3`，内容自上而下：

1. 筛选摘要行（269-279）：有筛选时出现，11px。内容为「筛选结果：<readout><b>n</b> 条」，加 chip h-6「含「query」」，加 chip h-6「from 至 to」（缺的一端显示「—」）。

2. 加载中：居中显示「加载中…」，pt-20，没有 role。

3. groups 为空：居中显示，pt-24。有筛选时文案为「没有符合条件的记录」，并附「清除所有筛选」按钮（btn-quiet h-7，会同时清空 query、日期和 quick）；没有筛选时文案为「还没有聊天记录」。

4. 每一天一组，外层 `div.glass-card overflow-hidden`：
   - 组头部按钮（301-311）：`w-full flex items-center gap-2 px-4 py-3 hover:bg-secondary/40 transition-all text-left`，内容是 ChevronDown 或 ChevronRight（13）、13px 日期（toLocaleDateString zh-CN，如「2026年10月6日」）、靠右的 readout「n 条」。
   - 展开后的消息列表（313-356）：`divide-y divide-[color:var(--glass-border)] border-t`。

每条消息的结构：
- 行容器 `flex px-4 py-3`，用户消息 justify-end，分身消息 justify-start；
- 里面一列 `flex flex-col gap-1.5`：用户为 max-w-[520px] items-end，分身为 max-w-[640px] items-start；
- 分身消息先有一行标签：一个 `inline-block h-1.5 w-1.5` 小方块（background amber-ink）加「Chloe」；
- 分身生成的图片用 `<GeneratedImage imageUrl={API+path}>`；
- 用户消息的参考图放在 flex-wrap justify-end 容器里（aria-label「本次修改的参考图片」），每张是 variant="reference" 并带 referenceIndex；
- 正文 div `break-words whitespace-pre-wrap text-sm`，用户加 bubble-user，分身加 bubble-ai；
- 最后是 readout 11px 的时间 HH:MM。
- **样式**：.glass-card。
.bubble-user（globals.css:273-277）：底色 --bubble-user，glass-border 边框，圆角 10，内边距 9px/14px，--shadow。
.bubble-ai（278-281）：透明，无内边距，line-height 1.75。
此外用到 .chip、.readout、hover:bg-secondary/40。
搜索高亮 `<mark class="bg-[color:var(--accent)] text-foreground rounded-[3px] px-0.5">`（330）。
- **行为（必须保留）**：折叠状态记在 collapsed[day]，默认全部展开；组头按钮没有 aria-expanded。

highlight（324-333）先转义正则元字符，再 split。代码注释写明这是为了防止 SyntaxError 导致整页白屏，必须保留。

GeneratedImage（components/GeneratedImage.tsx）自带加载、错误、重试、放大（<dialog>）和下载功能，key 里含 username。

generatedImagePath 和 storedReferenceImagePaths 来自 lib/generatedImages。
- **状态**：有加载态，有空态（分有筛选/无筛选两种文案），没有错误态。图片组件自己有「加载中」和「加载失败 + 重新加载」两种状态。
- **手机端**：main 加 max-md:min-w-0 overflow-visible px-4 py-4（文档滚动）。摘要行 flex-wrap，query chip 加 h-auto break-all whitespace-normal。消息列加 max-md:max-w-[85vw] min-w-0。
- **改造风险**：GeneratedImage 和主聊天页共用，它的 .glass-card 宽 280px（参考图 120px）。改 bubble-* 也会影响主聊天页，需要和主页规格保持一致。transition-all 在 reduced-motion 下会被全局规则压成 0.01ms。

### 旧社交画像页（设置抽屉「账户」标签）· 外壳与页头
- **位置**：frontend/app/profile/page.tsx:85-104、173-187
- **结构**：和设置页同构：
- 根节点 `flex h-dvh flex-col overflow-hidden`，非 embed 时加 mobile:pb-[calc(56px+env(safe-area-inset-bottom))]；
- `{!embedded && <Sidebar/>}`；
- header `glass sticky top-0 z-[2] shrink-0 border-b px-8 pb-[18px] pt-7`，里面是 `max-w-[976px] flex items-end justify-between gap-4`：左边是 h1「旧社交画像」加 p「此前用于社交匹配的画像；新会话记忆在“我的分身”中查看」；右边是「本人查看」（Shield 图标 13，amber，text-xs muted）。

ProfileContent：没有身份时，h-dvh 居中显示「加载中…」（role=status）。Suspense 的 fallback 也是这个。ProfileForAccount 用 key=username。
- **样式**：.glass 页头，Shield 图标行内 amber。
- **行为（必须保留）**：以 iframe 内嵌：app/page.tsx:2456 的 `/profile?embed=1`，对应设置抽屉的「账户」chip（2445）。独立路由 /profile 也存在，但 Sidebar 里没有入口，只能直接输入地址访问。
- **状态**：身份加载中。
- **手机端**：header 加 `mobile:px-4 mobile:pt-4`；内层加 `mobile:flex-col mobile:items-start mobile:gap-2`，「本人查看」换到标题下方。
- **改造风险**：抽屉 chip 叫「账户」，页内 h1 却是「旧社交画像」，现状就不一致。

embed 判断的 useSearchParams 写在 ProfileForAccount 里（85-86），排在其他 hook 之后；改结构时不要把它挪进条件分支。

其他 iframe 风险和设置页相同：body 背景不透明、主题不同步、断点必须用 mobile: 变体。

### 旧社交画像页 · 内容（头像卡 / 五类标签 / 隐私说明 / 去我的分身）
- **位置**：frontend/app/profile/page.tsx:13-54（Profile 类型与 Section/TagList/Empty 子组件）、56-83（拉取与空判断）、106-166
- **结构**：滚动区 `flex-1 space-y-3 overflow-y-auto px-8 py-6`，不限宽，内容自上而下：

1. 头像卡 `glass-card flex items-center gap-4 p-5`：左边是 `grid h-14 w-14 rounded-[6px] bg-secondary` 方块，显示 username 的第一个字（text-xl，amber）；右边是用户名（truncate），下面一行基本信息「city · occupation · stage」，都没有时显示「（暂未提取到基本信息）」。

2. 主体按状态三选一：
   - loading：Loader2 animate-spin 加「加载中…」，py-12；
   - isEmpty：`glass-card p-8 text-center`，标题「暂无旧社交画像」，下面两行说明（中间用 <br/> 断行）；
   - 其他情况：5 个 Section，每个是 `glass-card p-5`，h3 前带 amber 图标：兴趣（Heart）、价值观（Scale）、当前需求 / 想解决的问题（CircleHelp）、技能 / 可分享的经验（Wrench）、当前困境（TriangleAlert）。Section 内容是 TagList（只读的 `span.chip`），没有数据时是 Empty（11px italic muted/60「暂无记录」）。

3. 隐私说明卡 `glass-card flex items-start gap-2 p-5`：Shield 图标加一段说明。

4. 底部 `flex gap-2 pb-4`，里面一个 Link `btn flex-1`：ArrowUpRight 加「前往我的分身管理记忆」。
- **样式**：.glass-card 用在头像卡、空态、5 个 Section 和隐私说明上。.chip 在这里只作只读标签。另外用到 bg-secondary、italic、Loader2 spin。
- **行为（必须保留）**：GET `${API}/profile`（apiFetch，带 signal，并用 isCurrent 守卫），取 data.profile，没有则用 {}。请求出错时同样置为 {}，所以错误会显示成空态。

Link 的 href 是 "/agents/me"，target={embedded ? "_top" : undefined}：在 iframe 里点它，会让顶层页面跳到 /agents/me。
- **状态**：有三种情况：加载中（旋转图标）、整体为空、某个 Section 单独为空（「暂无记录」）。没有错误态。
- **手机端**：chip 加 `mobile:h-auto mobile:max-w-full mobile:break-all mobile:whitespace-normal`（45）。内容区加 `mobile:min-w-0 mobile:px-4 mobile:py-4`。按钮加 `mobile:h-auto mobile:min-h-10 mobile:whitespace-normal`。
- **改造风险**：target=_top 必须保留，否则 /agents/me 会被加载进抽屉的 iframe 里（还会带着 Sidebar）。

只读的 .chip 和可点的 .chip 是同一个类。如果给 .chip 加按压或 hover 动效，也会作用到这里。

username[0] 遇到 emoji 等代理对字符时会只取一半（现状）。

### 分身名片页 /agents/[id]
- **位置**：frontend/app/agents/[id]/page.tsx:1-56；名片组件 frontend/components/AgentIdentityCard.tsx
- **结构**：根节点 `flex h-screen flex-col overflow-hidden`（窄屏 max-md:h-dvh），下一层 `flex min-h-0 flex-1`，里面是 <Sidebar/> 和 main `min-w-0 flex-1 overflow-y-auto`（main 是滚动容器）。

main 里：
- header `glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7`：返回链接（ArrowLeft 13 加「我的分身」，指向 /agents/me，text-xs muted，hover 变 foreground），下面是 h1「分身名片」；
- 内容 `mx-auto max-w-[560px] space-y-5 px-8 py-6`。

内容按四种状态渲染：
- 没有 owner：p role=status「请登录后查看分身名片。」，加一个 Link「前往登录」（amber，下划线）；
- 还没返回：p role=status，Loader2 旋转加「正在加载名片…」；
- 成功：<AgentIdentityCard agent/>；
- 失败：`glass-card space-y-3 p-6`，里面是 p role=alert（text-[color:var(--rec)]）显示错误，加一个 `btn btn-quiet`「重新加载」。点它会清空 result，并把 retry 加 1。

Suspense 的 fallback 是 p「正在加载名片…」。
- **样式**：.glass 页头、.glass-card 错误卡、--rec。名片样式见下一区。
- **行为（必须保留）**：数据请求：GET `${API}/agents/${encodeURIComponent(id)}`，用 apiJson（lib/agents.ts:33-45）。apiJson 对 404 给出「内容不存在或暂未公开。」，对 422 和其他状态码也有固定文案。

用 key=`${owner}:${id}`，换账号时整块重新挂载；只有 result.id===id 时才显示结果，防止显示旧响应。

入口在 MyAgentWorkspace.tsx:154 的「查看已保存的公开名片」，只在 savedAgent.is_public 时出现。这一页从不以 iframe 或 embed 形式出现。
- **状态**：未登录、加载中、成功、错误加重试。
- **手机端**：窄屏（max-md）：
- header 改为 px-4 pb-4 pt-4；
- 内容区改为 px-4 py-4，并加 `max-md:[&_.echo]:max-w-full max-md:[&_.echo]:overflow-hidden max-md:[&_.echo]:break-all`，防止长名字的 echo 溢出；
- main 加 max-md:pb-[calc(56px+env(safe-area-inset-bottom))]，给底部标签栏让位。
- **改造风险**：这一页用的是 max-md:（按视口判断的断点），不受 data-shell 影响；这是对的，因为它不会被放进 iframe。

Sidebar 在这里走 Link 路由模式，没有抽屉回调。高亮按 pathname 精确匹配，所以在 /agents/[id] 上没有任何一项高亮。

### AgentIdentityCard（名片组件，多处共用）
- **位置**：frontend/components/AgentIdentityCard.tsx:1-24；使用方 app/agents/[id]/page.tsx:45 和 components/MyAgentWorkspace.tsx:153（preview 模式）
- **结构**：外层 section `glass-card flex flex-col gap-[18px] p-[22px] pb-[18px]`，aria-label 在 preview 时为「分身名片预览」，否则为「AI 分身名片」。内容自上而下：
1. 顶行，两端对齐：左边 `span.tag.tag-amber`「AI 分身」，右边 `span.readout`「名片预览」或「分身名片」；
2. 名字区 `py-1 text-[40px]`：名字不超过 12 个字时用 `span.echo data-text={name}`；超过 12 个字时改成普通字 `text-[28px] font-medium break-words`；
3. 简介 p，13px，leading-[1.7]，保留换行；没有简介时显示「这个分身还没有填写介绍。」；
4. 底栏 border-t pt-3.5（glass-border）：左边是 `grid h-8 w-8 rounded-[6px] bg-secondary` 的头像 emoji（默认 ✨，aria-hidden），右边是「由用户创建的人工智能分身」；
5. 只在 preview 时显示一行说明：公开时「保存后，其他已登录用户可查看这张名片。」，不公开时「保存后，这张名片将仅自己可见。」
- **样式**：.glass-card；.tag 和 .tag-amber（globals.css:265-269）；.readout；.echo。
这里的 .readout 用在中文标签上，和 globals.css:202 注释里「永远不给中文标签」的约定相悖（现状）。
- **行为（必须保留）**：纯展示组件。名字为空时显示「我的分身」。
- **状态**：简介为空时有专门文案；preview 模式按公开与否显示两种说明。
- **手机端**：组件本身没有断点。两个父容器用 `max-md:[&_.echo]:…` 约束 echo 的宽度。
- **改造风险**：「始终标明 AI 分身」是产品和合规要求：MyAgentWorkspace.tsx:155 的文案承诺「名片始终标明“AI 分身”」。所以 tag 和「由用户创建的人工智能分身」都不能删。

echo 的 ::after 是 nowrap 的；「不超过 12 个字才用 echo」这个阈值要么保留，要么同步调整。

### /agents/me → MyAgentWorkspace · 外壳 / 页头 / 加载与错误态 / 抽屉宿主
- **位置**：frontend/app/agents/me/page.tsx:1-5；frontend/components/MyAgentWorkspace.tsx:15-57、97-117；宿主 app/page.tsx:2327-2357
- **结构**：非嵌入（路由 /agents/me）时：根节点 `flex h-screen max-md:h-dvh flex-col overflow-hidden`，里面是 <Sidebar/> 和 main `min-w-0 flex-1 overflow-y-auto max-md:pb-[calc(56px+env(safe-area-inset-bottom))]`。

嵌入时：放在主页的分身抽屉里，不是 iframe，而是直接渲染组件 `<MyAgentWorkspace embedded onSaved={updateAgent}/>`。此时根节点为 `h-full min-h-0`，没有 Sidebar，也没有「回到对话」。

header `glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7`：非嵌入时有返回链接「回到对话」（ArrowLeft，指向 /）；然后是 h1「分身」和 p「设置身份、介绍和交流方式。名片默认仅自己可见。」。

内容区 `mx-auto max-w-[1040px] px-8 py-6`，按状态渲染：
- 没有 owner：role=status「请登录后管理自己的分身。」，加「前往登录」；
- loading：role=status，Loader2 加「正在加载你的分身…」；
- 没有 agent：`glass-card space-y-3 p-6`，里面是 p role=alert（text-destructive），显示 error，没有则显示「暂时无法加载分身。」，再加 btn-quiet「重新加载」；
- 正常：两栏网格，见下一区。
- **样式**：.glass 页头。.glass-card 错误卡。错误用 text-destructive，和其他页面用的 --rec 是不同的 token。
- **行为（必须保留）**：GET `${API}/agents/me`（apiJson），并校验 owner_username===owner，不一致时报「账号状态已变化，请重新登录后再管理分身。」。MyAgentWorkspace 用 key=owner，换号时重新挂载。

宿主抽屉 section#agent-drawer 的行为：
- aria-label「分身管理」，aria-hidden 和 inert 跟随开关，tabIndex -1；
- 按 Escape 关闭抽屉，并把焦点还给可见的触发按钮（focusVisibleDrawerTrigger，app/page.tsx:319-322）；
- 打开时把焦点移到面板上（326-330）；
- 抽屉顶栏写「分身」，有关闭按钮 X（aria-label「收起分身面板」）；
- 用 `{agentOpen && …}` 渲染，关闭即卸载，没保存的修改会丢失；
- 宽度 min(960px, calc(100vw - 56px))，滑入用 translateX，360ms cubic-bezier(.22,.61,.36,1)。
- **状态**：未登录、加载中、加载失败加重试、正常。
- **手机端**：header：max-md 下 px-4 pb-4 pt-4。内容区：max-md 下 px-4 py-4。抽屉：max-md 下 left-0、w-screen，底部停在标签栏上沿；关闭时 max-md:hidden。
- **改造风险**：嵌入时组件在主页 DOM 里（不是 iframe），所以 max-md: 按真实视口生效，主题也跟随主页。

嵌入时抽屉本身是 .glass，里面的 header 又是 .glass，形成两层 backdrop-filter 嵌套；换成透镜滤镜时要注意嵌套的 backdrop root。

抽屉标题「分身」和页内 h1「分身」重复。

### MyAgentWorkspace · 分身设定表单
- **位置**：frontend/components/MyAgentWorkspace.tsx:13（fieldClass）、59-95（updateAgent / save / dirty）、118-151
- **结构**：外层网格 `grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_340px]`：视口 ≥1024px 才分两栏，768-1023px 是单栏。

左栏是 form `flex flex-col gap-[22px]`，里面先是 fieldset（saving 时 disabled），包含四块：
1. `grid grid-cols-[96px_minmax(0,1fr)] gap-4`：
   - label「头像符号」加 input（aria-label「头像符号」，maxLength 16，text-center text-xl，placeholder ✨）；
   - label「分身名称」加 input（maxLength 40，required），下面提示「最多 <readout><b>40</b></readout> 字」。
2. label「名片简介」：textarea（rows 3，maxLength 300，resize-y），下面计数「<b>当前长度</b> / <b>300</b>，开启公开名片后可被他人查看」。
3. label，标题行两端对齐：左「性格与交流方式」，右 em「仅自己可见」；textarea rows 7，maxLength 2000；下面同样有 /2000 计数。
4. `label.glass-card flex cursor-pointer items-start justify-between gap-4 p-4`：粗体「公开分身名片」加一段长说明，右侧是 checkbox `h-4 w-4 accent-[color:var(--primary)]`。

fieldset 之外依次是：
- error：p role=alert，text-destructive；
- notice：p role=status，muted；
- 按钮行：submit `btn btn-primary`（图标 Save，保存中换成 Loader2；文案「保存分身」/「正在保存…」），dirty 时旁边显示「有未保存的修改」。
- **样式**：fieldClass 为 `w-full rounded-[6px] border border-[color:var(--border)] bg-card px-3 py-[9px] text-sm outline-none focus:border-[color:var(--amber-ink)] disabled:opacity-50`。计数用 .readout b。.glass-card 用在 label 元素上。checkbox 用 accent-[color:var(--primary)]。
- **行为（必须保留）**：updateAgent 合并传入的补丁，并清空 notice。

save 的流程：
1. preventDefault；
2. 前置条件：有 agent、不在保存中、isCurrentOwner、owner 一致；
3. display_name.trim() 为空时报「给分身起一个名字再保存。」；
4. PUT `${API}/agents/me`，body 为 {display_name, bio, personality（三者都 trim）, avatar_emoji（为空时用 ✨）, is_public}；
5. 校验返回的 owner；
6. 成功后 notice 显示「已保存。新的对话回复会使用这些分身设定。」，并调用 onSaved(agent)，主页据此更新头部的分身名和头像。

dirty 的判定是 JSON.stringify(agent) !== JSON.stringify(savedAgent)；不 dirty 时提交按钮禁用。

错误文案来自 apiJson，例如 422 时为「填写的信息不符合要求，请检查长度和内容。」
- **状态**：- 保存中：fieldset 整体 disabled，按钮显示旋转图标。
- 错误：role=alert。
- 成功：role=status。
- 未修改：提交按钮禁用。
- 有修改：显示 dirty 提示。
- **手机端**：窄屏（max-md）下网格 gap 改为 gap-6，form 加 min-w-0。头像和名称那两列在窄屏仍然是 96px + 1fr。
- **改造风险**：fieldset 一旦 disabled，会禁用里面所有控件。保存按钮现在在 fieldset 外面，改结构时保持这一点。

maxLength（16/40/300/2000）和后端限额一致，不要改。

公开开关的说明文案里有隐私承诺，语义不能删改。

### MyAgentWorkspace · 右栏（名片预览 / 公开名片链接 / 隐私说明 / 私有记忆面板）
- **位置**：frontend/components/MyAgentWorkspace.tsx:152-157；frontend/components/AgentMemoryPanel.tsx:1-102
- **结构**：aside `flex flex-col gap-5`，自上而下：
1. <AgentIdentityCard agent={agent} preview/>，实时跟着还没保存的表单变化；
2. savedAgent.is_public 时显示 Link，指向 `/agents/${id}`：ExternalLink 图标（13）加「查看已保存的公开名片」，text-xs，amber，hover 时下划线；
3. 说明行：ShieldCheck 图标（16，amber）加「名片始终标明“AI 分身”。公开名片不会公开你的用户名、性格设定、私人画像或聊天记录。」；
4. AgentMemoryPanel。

AgentMemoryPanel 是 section `flex flex-col gap-3 border-t pt-[18px]`，aria-labelledby="private-memory-title"，自上而下：
- 标题行：h3「私有记忆」，右边 readout；revision 为 null 时显示「仅自己可见」，否则显示「修订 <b>n</b>」；
- 说明 p；
- 内容区，按状态渲染：没有 owner 时「请登录后查看私有记忆。」；loading 时 Loader2 加「正在加载记忆…」；有条目时是 ul>li（每项 border-b，格式「标签：值」，标签由 8 项映射得到，比如 interests→兴趣，嵌套对象会递归拼接）；为空且没有错误时显示「还没有私人画像。…」；
- error：p role=alert（--rec），后面跟一个内联的「重试」（btn-quiet h-7）；
- notice：role=status；
- footer，两端对齐：左「刷新」（btn-quiet），右「清空记忆与个人画像」（btn-danger，图标 Trash2，清空中换成 Loader2）；
- 最底下一行 11px 说明。
- **样式**：.readout、--rec、.btn-quiet/.btn-danger、分隔线 glass-border、行内 amber 图标。
- **行为（必须保留）**：加载：GET `${API}/agents/me/memory`，返回 {profile, revision}。

清空：
1. window.confirm(「清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。」)；
2. 确认后重新 beginRequest，防止确认框开着的时候换了账号；
3. DELETE 同一个端点；
4. 成功后清空列表，并提示「分身记忆和已有个人画像已清空，聊天记录与分身设定已保留。」。

在没有 owner、加载中或清空中时，刷新和清空按钮都禁用。AgentMemoryPanel 自己也用 key=owner。
- **状态**：未登录、加载中、有数据、为空、错误加重试、清空中、清空成功。
- **手机端**：aside 在窄屏加 max-md:min-w-0，并加 `max-md:[&_.echo]:max-w-full overflow-hidden break-all`。
- **改造风险**：预览卡读的是没保存的 state，公开链接读的是已保存的 savedAgent，两者语义不同，不能合并。

清空用的是原生 confirm 弹框。这个组件嵌在主页抽屉里，不在 iframe 里。

### /agents → AgentExchangeWorkspace · 外壳 / 页头 / 分类标签栏 / 抽屉宿主
- **位置**：frontend/app/agents/page.tsx:1-5；frontend/components/AgentExchangeWorkspace.tsx:16-89；宿主 app/page.tsx:2359-2386；数据 lib/useAgentExchanges.ts:11-127
- **结构**：根节点 `flex h-screen max-md:h-dvh flex-col overflow-hidden`，嵌入时改为 h-full min-h-0，并带属性 data-agent-exchange-workspace。里面是 <Sidebar/>（只在非嵌入时）和 main（aria-label「分身交流工作区」，`min-w-0 flex-1 overflow-y-auto`，非嵌入时加 max-md:pb 56px + safe-area）。

header `glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7`：
- 左边：非嵌入时有「回到对话」链接；h1「广场」；p 说明，末尾带「管理我的分身」。有 onOpenMyAgent 时它是 button（点击切到分身抽屉），否则是 Link /agents/me；样式 amber underline underline-offset-4；
- 右边：有 owner 时显示「刷新」按钮（btn btn-quiet，RefreshCw 图标加载时 animate-spin，aria-label「刷新分身与交流记录」，加载时禁用）。

内容区 `mx-auto max-w-[1040px] px-8 py-6`，自上而下：
- 没有 owner：EmptyState 登录提示；
- data.error 不为空：ErrorNotice 加重试；
- 标签栏：外层 `div.relative mb-6`，里面 nav[role=tablist, aria-label「分身广场分类」] `flex gap-1 border-b`（borderColor 为 var(--border)），包含 5 个 button[role=tab, aria-selected]：「单人体验 / 体验记录 / 发现分身 / 收到的邀请 / 发出的邀请」。按钮类为 `-mb-px flex h-9 items-center gap-1.5 border-b-2 px-3 text-[13px]`；选中时 border-[color:var(--amber-ink)] text-foreground，未选中时边框透明、文字 muted。「收到的邀请」后面带一个 readout 待处理数（amber）；
- recordsError 不为空：ErrorNotice；
- data.agent 还没有：加载中显示「正在确认你的分身身份…」，否则 EmptyState「暂时无法确认当前分身身份，请刷新或重新登录。」；
- 有 selected：渲染 ExchangeConversation；
- 其他情况：按当前 tab 分支渲染。
- **样式**：.glass 页头；下划线式 tab；.readout；mobile-scrollbar-none。
- **行为（必须保留）**：切换 tab 时会调用 back()，清空 target 和 selected。

数据来源（useAgentExchanges）：
- 挂载时并行拉 /agents/me 和 /agents（目录），同时拉 /agent-exchanges/official-agents；
- 拿到 agent 后，每 4000ms 轮询一次 /agent-exchanges（refreshRecords）；
- 遇到 401/403，或返回的记录不属于本分身，就调用 invalidateIdentity 清空数据。

刷新按钮执行 refreshDirectory().then(refreshRecords)，同时执行 refreshOfficial。

tablist 没有 aria-controls 和 tabpanel，也不支持方向键切换（现状）。

宿主抽屉 section#exchange-drawer（aria-label「分身广场」）和分身抽屉一样有 aria-hidden、inert、Escape 关闭、打开时聚焦。用 `{exchangeOpen && …}` 渲染，关闭即卸载，轮询也随之停止。onOpenMyAgent 为 () => setDrawer("agent")。
- **状态**：未登录、目录错误、记录错误、身份确认中、身份失效。
- **手机端**：tab 栏在窄屏变为 overflow-x-auto pr-7 whitespace-nowrap，每个 tab shrink-0。ResizeObserver 和 scroll 监听（43-59）算出右边是否还有 tab（moreTabsRight），有则在右侧显示一个提示块：`absolute w-7 border-l bg-card`，里面是 ChevronRight（max-md:flex，aria-hidden）。header 在窄屏为 px-4 pt-4 pb-4，刷新按钮 shrink-0。
- **改造风险**：命名容易混：Sidebar 里「广场」对应 /agents，「世界」对应 /plaza，是两个不同页面。

这个组件嵌在主页 DOM 里，不是 iframe。

页头和详情里「交流中」的 sticky 条都是 sticky top-0 z-[2]，而且在同一个滚动容器里。推断会互相遮盖，未实测。

### AgentExchangeWorkspace · 「单人体验」与「发现分身」两个标签的内容
- **位置**：frontend/components/AgentExchangeWorkspace.tsx:90-114
- **结构**：「单人体验」（90-104），自上而下：
- 说明 p：都是官方 AI、没有真人，流程为初稿→审稿→修订；
- officialError 不为空时显示 ErrorNotice；
- 主体：officialLoading 时显示加载，0 个搭档时显示 EmptyState，否则显示搭档卡网格。网格为 `grid grid-cols-1 gap-3 md:grid-cols-3`，role=radiogroup，aria-label「选择官方搭档」。

每张搭档卡是 `<button role=radio aria-checked class="glass-card flex flex-col gap-2.5 p-4 text-left">`，带 data-official-agent={id}；选中时加 border-[color:var(--amber-ink)]。卡内依次是：
- 标题行：h3 display_name，右边 `span.tag`「官方 AI」；
- bio，line-clamp-3；
- model_label（没有则用 model），readout 样式。

选中一张卡后，下方渲染 ExchangeStartForm（官方模式）。创建成功后切到「体验记录」并打开详情。

「发现分身」（105-114），自上而下：
- 说明 p：双方都必须公开名片；自己没公开时末尾附「管理我的分身」；
- 主体：加载中显示加载；为空时显示 EmptyState（「最近公开的分身中暂无其他交流对象。…」）；否则显示卡片网格 `grid gap-3 md:grid-cols-3`。

每张卡是 `section.glass-card flex flex-col gap-2.5 p-4`，依次是：
- emoji 方块（h-8 w-8，bg-secondary）加 h3 名称；
- bio，空时显示「这位分身还没有填写简介。」；
- `btn self-start`：Send 图标加「邀请交流」；自己没公开时禁用。

选中后在下方 `mt-6` 渲染 ExchangeStartForm（对等模式）。成功后切到「发出的邀请」并打开详情。
- **样式**：.glass-card 用在 button 和 section 上；另外用到 .tag、.readout、.btn。
- **行为（必须保留）**：搭档卡虽然是 role=radio，但只支持 Tab 加点击，不支持方向键（现状）。others 列表会过滤掉自己的分身。
- **状态**：加载、空、错误，以及禁用态（自己没公开时「邀请交流」禁用）。
- **手机端**：md 以下卡片单列。官方卡在窄屏加 min-w-0，模型名加 break-all。
- **改造风险**：data-official-agent 属性可能被验证脚本用到，保留。

.glass-card 用在了 <button> 上；新玻璃如果加伪元素或滤镜，要保证按钮的焦点环还能正常显示。

### AgentExchangeWorkspace · 记录列表（体验记录 / 收到的邀请 / 发出的邀请）
- **位置**：frontend/components/AgentExchangeWorkspace.tsx:34-35、115-137、444-446（StatusBadge）、460-467（formatDate）
- **结构**：自上而下：
- 说明 p「展示最近 50 条交流记录中的…记录会自动更新。」；
- recordsLoading 时显示加载；
- 为空时显示 EmptyState，三个 tab 各一种文案；
- 有数据时显示列表。

列表表头行 `grid grid-cols-[minmax(0,1fr)_150px_120px_60px_60px] gap-4 px-2 pb-2 text-[11px]`，颜色 var(--dim)，五列为「话题 / 搭档 / 状态 / 次数（右对齐）/ 时间（右对齐）」。

每行是一个 `<button class="grid w-full …（同样的列宽） items-center gap-4 border-b px-2 py-3 text-left text-[13px] hover:bg-card" data-exchange-id>`，五列内容为：话题（truncate）、对方名称、StatusBadge、readout 次数、readout 时间（今天显示 HH:MM，其他日子显示 MM/DD）。
- **样式**：var(--dim)、.readout、hover:bg-card。

状态徽章 StatusBadge 用 .tag：
- failed 用 tag-rec；
- pending 和 running 用 tag-amber，running 前面再加 Loader2（11，旋转）。

徽章文案：
- 审稿流且已完成：审稿通过显示「AI 审稿通过 · 待你验收」，否则「已结束 · 草稿」；
- 其他情况按 exchangeStatusLabel：等待接受 / 交流中 / 已完成 / 已停止 / 已拒绝 / 交流失败。
- **行为（必须保留）**：点击一行会 setSelected，进入详情。

三个 tab 的过滤规则：
- 体验记录：官方交流；
- 收到的邀请：viewer_role 为 recipient；
- 发出的邀请：viewer_role 为 initiator。
- **状态**：加载、空（三个 tab 文案各不相同）。错误由上方的 recordsError 统一显示。
- **手机端**：窄屏（max-md）下：
- 表头隐藏；
- 行改为 grid-cols-1 gap-1，桌面那几列隐藏；
- 改用第二行 `hidden max-md:flex`，依次显示对方名称、StatusBadge、次数、时间，每项前面带 sr-only 前缀「搭档：/状态：/次数：/时间：」。
- **改造风险**：这个固定列宽表格在窄屏改成两行堆叠，是 2026-09-23 手机适配的验收项（docs/tasks/2026-09-23-mobile-layout/02-spec.md:62）。改版后在 390 和 360 宽度下也必须没有横向滚动。

### AgentExchangeWorkspace · 发起表单 ExchangeStartForm
- **位置**：frontend/components/AgentExchangeWorkspace.tsx:146-211、439-442（Participant）
- **结构**：外层 section `flex flex-col gap-4`，自上而下：

1. 返回按钮（btn-quiet，ArrowLeft）：官方模式为「返回单人体验」，对等模式为「返回分身列表」。

2. `grid gap-3 sm:grid-cols-2`，放两个 Participant。每个 Participant 是 emoji 方块，加名称，加角色标签，再加模型 readout。角色标签：官方模式为「你的 AI 分身」和「平台官方 AI · 无真人用户」；对等模式为「我的 AI 分身 · 发起方」和「对方 AI 分身 · 受邀方」。

3. form `grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_220px]`：
   - 左栏是一个 fieldset：
     - label「讨论话题」（官方）或「交流话题」（对等）；
     - textarea：autoFocus、required，maxLength 官方 10000、对等 300，min-h-[150px]，resize-y；
     - small 计数「<b.readout>n</b> / <b.readout>上限</b>，人物、背景…」；
     - 官方模式且有 suggested_topic 时，再加一个「使用示例话题」按钮（btn-quiet h-7）。
   - 右栏：
     - fieldset：label「回复次数」，input type=number（min 2，max 官方 99、对等 6，step 1，readout 样式，带 aria-describedby），下面 small 帮助文字「双方合计，2–N。…」；
     - 提交按钮 `btn btn-primary h-10 w-full`：官方模式图标 Play、文案「开始讨论」，进行中为「正在开始…」；对等模式图标 Send、文案「发送邀请」，进行中为「正在发送…」；进行中图标换成 Loader2；
     - 说明 p：隐私、扣费、每日限次；
     - error 时显示 ErrorNotice。
- **样式**：fieldClass（第 14 行，和 MyAgentWorkspace 里那份相同）、.readout、.btn-*。
- **行为（必须保留）**：校验规则：
- validTopic：trim 后非空，且长度不超过上限；
- validMaxTurns：整数，2 到上限之间；
- 次数默认值：官方 "99"，对等 "6"。

提交流程：
1. 先调 assertAccountAgent：GET /agents/me，比对 owner 和 id；
2. 官方模式 POST `/agent-exchanges/official`，body {official_agent_id, topic, max_turns}；对等模式 POST `/agent-exchanges`，body {target_agent_id, topic, max_turns}；
3. 校验返回结果的双方 id、viewer_role 和 kind，不符就抛 ExchangeIdentityError，然后调用 onIdentityInvalid。

busy 时两个 fieldset 和返回按钮都禁用。
- **状态**：提交中、校验不通过时禁用、错误。
- **手机端**：Participant 网格在 sm（640px）以下单列；表单在 lg（1024px）以下单列。
- **改造风险**：官方和对等两种模式的文案、上限都不同，要分别复刻。次数输入框用的是 readout 等宽字体。

### AgentExchangeWorkspace · 交流详情 ExchangeConversation
- **位置**：frontend/components/AgentExchangeWorkspace.tsx:213-346
- **结构**：交流不可访问时（283），只显示 ErrorNotice 和返回按钮。

正常时是 section `flex flex-col gap-6`，带 data-exchange-detail，内容自上而下：

1. 返回按钮（btn-quiet），文案按来源为「体验记录 / 收到的邀请 / 发出的邀请」。

2. 标题区，两端对齐：
   - 左：h2 显示话题前 40 字（超出加「…」）；下面一行元信息：我方名称加模型 readout、对方名称加模型 readout、readout「第 <b>n</b> 次 / max」；
   - 右：StatusBadge。

3. 审稿流才有的阶段条：`inline-flex rounded-[6px] border`（glass-border），aria-label「流程阶段」。三段「主创初稿 / 官方审稿 / 主创修订」之间用 border-l 分隔，已完成的段前加 Check 图标（amber）。

4. ExchangeTopic：话题不超过 300 字时直接是一个 p。超过 300 字时，先显示截断后的 line-clamp-4 文本，再加一个 `details.glass-card group p-3`：summary 为 amber 文字「展开/收起完整话题（n 字）」，展开内容是 role=region、tabIndex 0、max-h-80 的滚动区。

5. pending 时的一段说明。

6. loading 时显示 LoadingState；pending 时显示按钮组：
   - 受邀方额外有：btn-primary「接受并开始交流」、btn-quiet「拒绝邀请」；
   - 双方都有：btn「取消这次邀请」。

7. 出错时显示 ErrorNotice「交流暂未更新：…」，带重新加载。

8. running 时显示 sticky 条 `glass sticky top-0 z-[2] -mx-8 px-8 py-2`：左边「交流正在自动更新，停止后保留已有内容」；右边两个按钮：「查看最新回复」（scrollIntoView，block end）和「停止交流」（btn）。

9. 审稿流时显示 ExchangeArtifact，里面嵌着 ExchangeDocuments（embedded 模式）。

10. 隐私说明 p。

11. 消息区：div role=region，aria-label「双分身交流消息」，aria-busy 在 running 时为真。每条消息是 `article grid grid-cols-[28px_minmax(0,1fr)] gap-3`，带 data-exchange-message：左列 readout 序号；右列先是头行（名称、stage tag、「你的 AI 分身 / 平台官方 AI / 对方 AI 分身」），然后是正文（13px，leading-[1.75]，保留换行）。没有消息时显示 EmptyState，有三种文案。

12. 有 summary 时显示 `section.glass-card p-4`，h3 为「创作说明」（审稿流）或「交流总结 · AI 生成」。

13. 非审稿流时显示独立的 ExchangeDocuments（glass-card）。

14. 结束状态提示：failed 显示 ErrorNotice；stopped 显示 EmptyState；rejected 显示 EmptyState。

15. 已结束时最后显示一个禁用的「停止交流」btn，加「已结束，记录仅你可见」。
- **样式**：.glass（sticky 条）、.glass-card、.tag、.readout、.btn*、var(--glass-border)、Check 图标 amber。
- **行为（必须保留）**：轮询：每次 load 后，如果状态仍是活跃的（pending 或 running），3000ms 后再 GET /agent-exchanges/{id}。

act(accept | reject | stop)：先上 mutating 锁，再调 assertAccountAgent，然后 POST `/agent-exchanges/{id}/{action}`。官方交流只允许 stop。

遇到 401/403/404，或返回的身份不符，就清空内容，显示「这段交流已被删除或无法访问，旧内容已清除。」

拒绝、取消、停止都没有二次确认。
- **状态**：加载中、pending、running（徽章旋转、sticky 条、aria-busy）、completed、stopped、rejected、failed、不可访问，以及各个按钮的 busy 态。
- **手机端**：窄屏（max-md）：
- 标题区改为 flex-col gap-2，名称加 break-all；
- 阶段条改为 w-full，三段 flex-1 等分，px-1；
- sticky 条改为 -mx-4 px-4，并改为 flex-col items-start。
- **改造风险**：sticky 条的 -mx-8 是为了抵消父容器的 px-8（窄屏是 -mx-4 对应 px-4），改内边距时必须同步改它。

data-exchange-detail 和 data-exchange-message 属性要保留。

### AgentExchangeWorkspace · 作品与文档交付，以及通用小组件
- **位置**：frontend/components/AgentExchangeWorkspace.tsx:348-437、448-458
- **结构**：ExchangeArtifact（352-365）是 `section.glass-card`，aria-label「当前作品」，带 data-exchange-artifact，自上而下：
- 头行（border-b）：「当前作品」，右边是 readout「n 字」和一个 tag：已通过用 tag-amber「审稿通过，待你验收」，needs_revision 显示「待修订」，其他显示「草稿」；
- completion_reason 对应的说明；
- 稿件正文：div role=region，aria-label「完整作品稿件」，tabIndex 0，max-h-[36rem] overflow-y-auto，13px，leading-[1.8]，select-text，focus-visible 时显示 ring。没有稿件时显示三种占位文案之一；
- 最后是 children（文档区）。

ExchangeDocuments（367-426）：embedded 时外层为 `border-t p-3`，否则为 `glass-card p-4`；aria-label「文档交付物」。内容自上而下：
- 说明 p；
- 按钮组，按钮类为 `btn max-w-full`，图标 Download（下载中换成 Loader2）：审稿流时有「作品 Markdown」，另外都有「README.md」和「完整讨论」；
- 下载中显示 role=status 文案；
- 出错时显示 ErrorNotice。

通用小组件：
- ErrorNotice（448-450）：`glass-card role=alert p-3`，文字 text-destructive，可选「重新加载」按钮（btn-quiet h-7）；
- EmptyState：p，py-6，13px，muted；
- LoadingState：p role=status，Loader2（15，旋转）。
- **样式**：.glass-card、.tag/.tag-amber、.readout、text-destructive、focus-visible:ring-[color:var(--ring)]。
- **行为（必须保留）**：下载流程：
1. 上 activeDownload 锁，调 assertAccountAgent；
2. apiFetch GET `/agent-exchanges/{id}/export?document=readme|discussion|artifact`，cache 为 no-store；
3. 校验响应 Content-Type 以 text/markdown 开头；
4. 转成 Blob，用一个临时的隐藏 a 标签下载：先 append，再 click，然后 remove；
5. 文件名为 README.md 或 `${kind}-${id}.md`；
6. 1 秒后 revoke 掉 URL。

遇到 401/403/404 时交给 onAccessError 处理。
- **状态**：ready 之前所有下载按钮禁用；没有作品时「作品 Markdown」禁用；另有下载中和错误两种状态。
- **手机端**：按钮 flex-wrap，并设 max-w-full。
- **改造风险**：ErrorNotice 用 text-destructive，而设置页和名片页用 --rec。两者都是错误红，却是两套 token。

### 跨区域要点
- embed 矩阵：用 iframe 加 ?embed=1 内嵌的只有 /settings 和 /profile，都在设置抽屉里（app/page.tsx:2426-2460，chips「设置/账户」切换 src）；/plaza 和 /match 也是这样内嵌，但不在本范围。MyAgentWorkspace（app/page.tsx:2356）和 AgentExchangeWorkspace（2385）是组件内嵌，不经过 iframe，靠 embedded 这个 prop 区分。/login、/history（新标签页打开）、/agents/[id] 从不内嵌。/agents 和 /agents/me 两个路由页是非嵌入版本：Sidebar 在这里走 Link 跳转；在主页里则通过 Sidebar 的回调打开抽屉。
- 断点体系：md = 48rem = 768px。settings 和 profile 只用自定义的 `mobile:` 变体（globals.css:7-13）。这个变体会尊重 html[data-shell="desktop"]，该属性由 layout.tsx:30-58 的脚本按父窗口是否 ≥768px 来设置。其余页面用 Tailwind 的 max-md: / md: / lg:（1024）/ sm:（640）。globals.css:415-431 也尊重 data-shell：窄屏把 input、textarea、select 的字号设为 ≥16px，并定义 .mobile-scrollbar-none。改版时不能把 settings 和 profile 里的 mobile: 换成 max-md:。
- 主题现状：layout.tsx:28 把 `<html class="dark">` 写死了。dark 变体是 `@custom-variant dark (&:is(.dark *))`（globals.css:5）。浅色令牌在 :root（55-112），深色令牌在 .dark（115-164）。lib/useTheme.ts 只切换当前文档的 class，不持久化，也不读 prefers-color-scheme。切换入口只有 Sidebar 的桌面竖条（172-178）和 ConversationPicker。结果是：iframe 里的 settings/profile、新标签页里的 history、以及 login 永远是深色。viewport 的 themeColor 也固定为 #0E1219（layout.tsx:16）。本范围 9 个文件里没有任何硬编码的 hex/rgba，也没有 dark: 变体，颜色全部走 CSS 变量和语义类（bg-card、bg-secondary、text-muted-foreground、text-destructive、border-border），所以换一套令牌就能整体换色。
- 颜色令牌出现的行号（amber-ink / rec / destructive / dim / accent / primary / border / ring）：
- login：140、161、166、179、195、221、226、267；
- settings：145、171、177、189、191、193、202、212、219；
- history：159、214、222、229、330、339；
- profile：35、100、110、154；
- agents/[id]：44、46；
- MyAgentWorkspace：13、112、114、140、143、154、155；
- AgentMemoryPanel：91；
- AgentExchangeWorkspace：14、38、39、78、81、83、86、97、118、309、362、433、434、449。
lucide 图标统一用行内 style={{color:"var(--amber-ink)"}} 着色。
- 输入框样式没有共用组件：components/ui/input.tsx 存在，但这些页面都没用。同一套 `rounded-[6px] border bg-card px-3 py-[9px] … focus:border-[color:var(--amber-ink)]` 类串分散在这些位置：login 161、179、221、267；settings 202；history 159、222、229；MyAgentWorkspace 13 的 fieldClass；AgentExchangeWorkspace 14 的 fieldClass。换输入框风格时要逐处修改，漏一处就会残留旧样式。
- 错误红有两套 token：text-[color:var(--rec)] 用在 login、settings、agents/[id]、AgentMemoryPanel；text-destructive 用在 MyAgentWorkspace 114/143 和 AgentExchangeWorkspace 的 ErrorNotice（449）。两者当前值相同，但是不同的 token。
- 原生对话框：window.confirm 用在 settings 45（清空聊天）、settings 101（删号）、AgentMemoryPanel 60（清空记忆）；window.alert 用在 settings 116（媒体文件没清理完）。设置页这几处运行在 iframe 里。以下操作没有任何二次确认：退出登录、交流的拒绝/取消/停止。
- 玻璃层：.glass（globals.css:183-189）和 .glass-card（192-200）都是 backdrop-filter blur 加 saturate，再叠 --grain 噪点。降级规则已经有了：`@supports not (backdrop-filter)` 和 `prefers-reduced-transparency`（284-289），会退成 --card 实色，可以作为「素瓷」不透明退路的挂点。嵌套情况：抽屉是 .glass，里面组件的 header 又是 .glass；history 的顶栏 .glass 和 aside .glass 是并列的。iframe 文档的 body 有不透明的渐变背景（168-178）。如果用 backdrop-filter: url(#svg) 做透镜，只有 Chromium 支持，WebKit（iOS PWA、macOS Safari）不支持；Tauri 的 Windows 版用的是 WebView2，属于 Chromium。另外，带 filter / backdrop-filter / transform 的元素会成为 fixed 后代的包含块。
- .glass-card 不只用在 div 上：AgentExchangeWorkspace 97（官方搭档卡）用在 <button> 上，MyAgentWorkspace 138 用在 <label> 上，AgentExchangeWorkspace 432 用在 <details> 上，AgentIdentityCard 6 以及 AgentExchangeWorkspace 108、335、356 用在 <section> 上。history 的分组卡还带 overflow-hidden（300）。给 .glass-card 加伪元素、SVG 滤镜或 overflow 时，都要兼容这些元素。
- .chip 既用作可点按钮（settings 153、history 199 和 253、主页抽屉的 chips），也用作只读标签（profile 45、history 摘要 272 和 274），不加区分。.readout 在 AgentIdentityCard 9 和 AgentMemoryPanel 85 被用在中文标签上，和 globals.css:202 的注释约定冲突。
- 字体与 CSP：现在没有加载任何 webfont，用的是 globals.css:56-57 的系统字体栈，也没有用 next/font。next.config.ts 的 CSP 为 `font-src 'self' data:`、`style-src 'self' 'unsafe-inline'`、`img-src 'self' blob: data:`。所以思源宋体必须自托管，或者用 next/font 在构建时下载，不能直接连 Google Fonts CDN。SVG 用内联或 data: URI 都可以。login 161/221 显式用了 font-mono，.readout 用 --font-mono-stack。
- 动画：
- Signal 用 rAF 驱动（login 页）；
- Loader2 / RefreshCw 的 animate-spin 用在 profile 122、agents/[id] 44、MyAgentWorkspace 112 和 147、AgentMemoryPanel 88 和 96、AgentExchangeWorkspace 73、205、315、316、321、419-421、445、457；
- history 的折叠头有 transition-all；
- 抽屉滑入是 translateX，360ms cubic-bezier(.22,.61,.36,1)。
globals.css:460-467 在 reduced-motion 下全局禁掉动画；Signal 另外自己检查 matchMedia。
- 底部标签栏与竖条导航：非嵌入页给底部留出 56px + env(safe-area-inset-bottom)：settings 128 和 profile 89 用 mobile:pb；agents/[id] 34、MyAgentWorkspace 101、AgentExchangeWorkspace 65 用 max-md:pb，加在 main 上。层级：Sidebar 底栏 z-[70]，抽屉 z-[55]，抽屉背板 z-50。改「桌面竖排书签导航」要注意两点：Sidebar.tsx:84-180 的桌面竖条（w-14）被这些页面复用；主页抽屉的宽度和背板的 left-14 都硬编码了 56px，依赖 Sidebar 宽 56px（app/page.tsx:2343、2374、2396、2433、2466）。
- 账号隔离必须保留，机制分三部分：
1. useAccountIdentity 加 useAccountRequest（lib/useAccountIdentity.ts）；
2. 按 owner 或 username 做 key，换号时整块重新挂载：history 383、profile 178、agents/[id] 16、MyAgentWorkspace 23、AgentMemoryPanel 23、AgentExchangeWorkspace 23；
3. 所有请求回来时都用 isCurrent() 守卫。
401 由 lib/auth.ts:22-32 处理，让顶层页面跳到 /login?reason=expired，iframe 里也是跳顶层。settings、history、profile 因为用了 useSearchParams，外面包着 Suspense，这一点也要保留。
- data-* 钩子要保留：data-agent-exchange-workspace（62）、data-official-agent（97）、data-exchange-id（121）、data-exchange-detail（293）、data-exchange-message（326）、data-exchange-artifact（356）。frontend 目录下没有测试文件引用它们，但以往的验收或复核脚本可能用到。
- 前端没有自动化测试，验收靠 tsc、lint、build 加浏览器检查。已有的手机适配不变量见 docs/tasks/2026-09-23-mobile-layout/02-spec.md:57-65：在 390×844 和 360×740 下，/login、/agents、/agents/me、/agents/[id]、/settings（含 embed）、/profile（含 embed）、/history 都必须没有横向滚动，标签不出现逐字竖排，主要按钮可点。
- 页头模式与标题层级：
- 统一页头为 `glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7`，内层 `max-w-[976px] flex items-end justify-between gap-4`。使用处：settings 132-133、profile 93-94、agents/[id] 35-36、MyAgentWorkspace 102-103、AgentExchangeWorkspace 66-67；history 例外，用的是 px-5 py-2.5 z-20。
- 每页一个 h1：设置 / 旧社交画像 / 分身名片 / 分身 / 广场。login 和 history 没有 h1：login 的字标是 div.echo，history 的「历史记录」是 p。
- 抽屉顶栏标题和页内 h1 有重复：「分身」对「分身」、「设置」对「设置」；还有一处不一致：抽屉 chip 叫「账户」，页内 h1 是「旧社交画像」。
- Next 16 约束：frontend/AGENTS.md 要求改代码前先读 node_modules/next/dist/docs。拦截文件是 proxy.ts（不是 middleware）：/login 是公开路径；生产环境没有 fiona_token cookie 时重定向到 /login，有 cookie 时访问 /login 会被重定向到 /；dev 模式全部放行。

## gaps：完整性核对：Fiona/frontend @586d86a（工作区干净）。app/ 与 components/ 下共 36 个 .tsx/.ts/.css 文件（共 8155 行），逐个与 5 份地图对照过。每个文件都至少被提到一次，没有整文件漏掉。下面只补「被漏掉，或只被一笔带过」的弹层、状态、模式和耦合：原生 confirm/alert 弹框；登录页不读退出原因参数；路由级 404/错误/加载缺失，Suspense 回退不一致；components/ui 全部零引用；Sidebar 在独立页走 Link 模式；世界/设置两个 iframe 抽屉常驻挂载、主题不同步、无障碍有缺口；GeneratedImage 的顶层 <dialog>；世界页 iframe 内两个浮层。另外核对了 app/components 以外但直接卡住改造的三个文件：proxy.ts、next.config.ts 里的 CSP、lib/auth.ts。路径均相对 frontend。
### 原生 confirm()/alert() 系统弹框（全站没有自绘确认弹层）
- **位置**：app/page.tsx:1389-1392（handleClearChat，没有任何 JSX 调用它）、1432-1437（handleDeleteConversation，有两处入口：经 1988 onDelete 接到 components/ConversationPicker.tsx:73-82 行内垃圾桶；另一处是当前对话记录抽屉 page.tsx:2053 的「删除」）、1849-1860（handlePickImage：1854 alert("只能上传图片")、1858 alert("图片不能超过 5MB")）；app/settings/page.tsx:43-46（clearHistory confirm）、99-101（deleteAccount confirm）、115-117（alert 媒体文件待管理员清理）；components/AgentMemoryPanel.tsx:59-61（清空记忆 confirm）
- **结构**：8 个调用点全是 window.confirm/alert，渲染的是浏览器原生框，没有任何 DOM 结构。settings 的 3 处在 /settings?embed=1 的 iframe 文档里触发，从设置抽屉弹出。
- **样式**：不可主题化，不受 globals.css 令牌影响。全站也没有 color-scheme 声明（grep 零命中），原生框和控件按 UA 默认配色绘制。
- **行为（必须保留）**：confirm 同步阻塞主线程。守卫顺序必须保留：page.tsx:1433 先判 conversationLocked||conversationLoading 再 confirm，确认后直接 resetConversationPresentation()+deleteConversation(id)，确认后不再复查。AgentMemoryPanel:60 先判 clearing/loading/isCurrentOwner() 再 confirm，确认后才 beginRequest()（61 行注释说明确认框打开期间账号可能变化）。settings deleteAccount 先要求输入框 deleteConfirmation===username 才走到 confirm，形成双重确认；alert 之后 clearAuth()+redirectTop('/login?reason=deleted')。handlePickImage 的 alert 前已执行 e.target.value=""。
- **状态**：取消 confirm 就静默 return，没有任何反馈。普通附件（看图聊天）的类型和大小错误只有 alert，没有页内错误位。参考图走的是页内 referenceUploadError（page.tsx:2212 role=alert）。
- **手机端**：同样是系统原生框，iOS 独立 PWA 下是系统样式。
- **改造风险**：如果改成自绘异步确认层，同步语义会变：确认回调里要重新判 conversationLocked/currentConversation/owner；原生框打开时 TTS 队列、60s 余额轮询、peer 轮询都被阻塞，自绘层不会阻塞。settings 的确认层自绘后会被限制在 iframe 抽屉区域内，fixed inset-0 只盖住抽屉。删掉两处 alert 时，普通附件需要新的错误呈现位。

### 登录页不呈现退出原因（?reason=expired / logout / deleted），以及 proxy 门禁
- **位置**：lib/auth.ts:22-32（redirectExpiredSession → window.top.location.replace('/login?reason=expired')）；app/settings/page.tsx:60-66（redirectTop 用 window.top）、83 与 91（reason=logout）、119（reason=deleted）；app/login/page.tsx:1-21（只 import useRouter，不读 searchParams）、41（成功后 router.replace('/')）；proxy.ts:1-41
- **结构**：登录页没有横幅或提示位来接这个参数。过期、主动退出、注销账号、直接访问，四种进入方式看到的登录页完全一样（136-147 品牌区 + 149-247 表单卡）。
- **样式**：无专属样式，复用 .glass 表单卡。
- **行为（必须保留）**：proxy.ts 只在生产环境生效（SKIP_AUTH 判断 NODE_ENV==='development'）：没有 fiona_token cookie 时访问非 /login 路径会被 302 到 /login，且不带 reason；有 cookie 时访问 /login 会被 302 到 /。lib/auth.ts:26 和 settings:61 都跳 window.top，所以 iframe 抽屉里的 401 或退出会让整个外壳去登录页。
- **状态**：上面四种进入方式没有任何区分。开发测试入口（login 249-279）只在 development 渲染。
- **手机端**：同桌面，登录页用 max-md: 断点（7 处）。
- **改造风险**：如果设计稿给登录页加「已退出」「会话过期」提示，必须新增 useSearchParams。login/page.tsx 目前没有 Suspense 包裹，而 Next 16 预渲染时裸用 useSearchParams 会构建报错，需要像 settings/plaza 那样加 Suspense 外壳。登录页是生产环境下唯一未登录可见的页面，它的静态资源受 proxy matcher 限制（见 cross_cutting）。

### 路由级 404/错误/加载缺失，以及各页 Suspense 和无身份回退不一致
- **位置**：app/ 下不存在 not-found.tsx、error.tsx、global-error.tsx、loading.tsx、template.tsx（find 结果只有 36 个文件）。Suspense 回退：app/plaza/page.tsx:658-664 null；app/settings/page.tsx:234-240 null；app/community/page.tsx:34-40 null；app/agents/[id]/page.tsx:54-56 是 <p className="p-6 text-sm text-muted-foreground">正在加载名片…</p>；app/match/page.tsx:454-468、app/profile/page.tsx:173-187、app/history/page.tsx:366-396 是全屏「加载中…」。首页抽屉无身份时显示 app/page.tsx:2420-2422、2457-2459 的「正在加载身份…」
- **结构**：全屏加载态硬编码了 6 次，写法相同：<div role="status" className="flex h-dvh|min-h-screen items-center justify-center text-sm text-muted-foreground">加载中…</div>，match 457/464、profile 176/183、history 380/389 各两次（一次是 Suspense fallback，一次是 useAccountIdentity 为空时）。
- **样式**：只用 text-muted-foreground，背景是 body 光斑。
- **行为（必须保留）**：match、profile、history 在身份为空时会一直停在「加载中…」，直到 lib/auth.ts ensureAccountIdentity 恢复身份或 401 跳登录。history 还会在 ?user 与身份不符时 router.replace 去掉该参数（371-377）。
- **状态**：未知路由走 Next 内置 404：在 RootLayout 内渲染，html.dark 和 body 背景生效，但内容是 Next 内置内联样式。运行时异常走 Next 默认错误界面，没有品牌化。null 回退会让 iframe 抽屉首帧只剩外层 .glass 底。
- **手机端**：同桌面；h-dvh 与 min-h-screen 混用。
- **改造风险**：设计稿若有 404、错误或加载画面，需要新建 special files，现有页面里没有可复刻的对象。「加载中…」分散在 3 个页面共 6 处，统一换皮要逐处改。

### components/ui/*（shadcn base-nova）全部零引用
- **位置**：components/ui/avatar.tsx(109)、badge.tsx(52)、button.tsx(58)、input.tsx(20)、scroll-area.tsx(55)、separator.tsx(25)、textarea.tsx(18)；components.json（style base-nova）；app/globals.css:243 注释「给还没用 components/ui 的地方」
- **结构**：在 app、components、lib 里 grep 'components/ui' 或 'ui/<名字>'，没有任何 import，只命中 globals.css:243 的注释。@base-ui/react 和 class-variance-authority 只被这 7 个文件使用。
- **样式**：内部用 shadcn 令牌类，avatar.tsx:62 有 z-10。shadcn-tailwind.css 的令牌映射仍通过 globals.css:3 生效，被 .btn/.chip 等间接使用。
- **行为（必须保留）**：无（不渲染）。
- **状态**：无。
- **手机端**：无。
- **改造风险**：它们不出现在任何页面，复刻对照表里不应作为对象。如果实现方「顺手」改它们，无法在界面上验证。所有实际控件都是 globals.css:243-270 的 .btn/.chip/.tag 和各处 Tailwind 任意值。

### Sidebar 独立页（Link）模式与高亮规则
- **位置**：components/Sidebar.tsx:95-151（桌面：drawerCallback 为 undefined 时走 136-149 的 Link）、186-219（手机：219 Link）、54-80（每个实例各自拉余额）。无回调调用处共 8 个，其中 7 个带 !embedded 判断：app/settings/page.tsx:130、app/match/page.tsx:308、app/plaza/page.tsx:367、app/profile/page.tsx:91、app/community/page.tsx:13、components/MyAgentWorkspace.tsx:100、components/AgentExchangeWorkspace.tsx:64；app/agents/[id]/page.tsx:33 无 embed 分支，总是渲染。/history 与 /login 不渲染 Sidebar
- **结构**：高亮规则：active = drawerActive || chatActive || (href!=='/' && pathname===href)，独立页只按 pathname 精确匹配。/match、/profile、/community、/agents/[id] 没有对应 navItem，所以没有任何项高亮。桌面 Link 没有 aria-current。
- **样式**：与抽屉模式相同：h-12 w-12 rounded-[6px]，激活用 text-[color:var(--amber-ink)]，图标 strokeWidth 2.2/1.8；手机 h-14 flex-1。
- **行为（必须保留）**：每个独立页挂一个 Sidebar，就各自 GET /strawberry，60s 轮询，并监听 storage 和 fiona-user-changed。独立页不传 onBalanceChange。抽屉模式下 aria-expanded/aria-controls：桌面只给分身和广场（120-121），手机四项都给（202-206、216）。
- **状态**：余额为 null 显示「…」；<30 用 var(--rec)；<100 用 var(--amber-ink)；其余用 var(--foreground)（160-167）。
- **手机端**：手机底栏 fixed z-[70]。独立页自己留底部内边距，写法有两种：mobile:pb-[calc(56px+env(safe-area-inset-bottom))]（community:11 等 iframe 可嵌页），max-md:pb-[...]（agents/[id]:34）。手机底栏没有主题切换；手机上唯一的主题入口在 ConversationPicker.tsx:100-105，且只在首页，所以独立页在手机上切不了主题。
- **改造风险**：竖排书签导航要同时复刻按钮（抽屉回调）和 Link 两种分支，以及两套高亮来源。独立页没有可高亮项的情况要有定义。余额轮询随实例数增加。

### 世界/设置 iframe 抽屉：常驻挂载、主题隔离、无障碍缺口（与分身/广场两个 section 抽屉对比）
- **位置**：app/page.tsx:2386-2423（#plaza-drawer）、2425-2460（#settings-drawer）；对照 2327-2357 与 2359-2386（section 抽屉带 aria-hidden/inert/tabIndex/Esc）、323-330（只给 agent/exchange 打开时聚焦）；components/Sidebar.tsx:120-121；app/profile/page.tsx:161（Link target=_top）；lib/auth.ts:26
- **结构**：这两个抽屉是 div，不是 section。关闭时桌面只 translateX(105%)，仍在 DOM；手机 max-md:hidden。头部条 border-b px-4 py-2，标签切换用 .chip/.chip-on，收起按钮 w-6 h-6（手机 h-10 w-10）。主体是 <iframe className="flex-1 w-full border-0">，没有 title 属性。只要 username 非空，iframe 从首页挂载起就常驻（2387 注释「不卸载 iframe」）。worldTab/settingsTab 一变，src 就变，iframe 整页重载。
- **样式**：.glass；内联宽度 calc((100vw - 56px) * 2 / 3)；阴影 rgba(0,0,0,0.28) 写死；transition transform 360ms cubic-bezier(.22,.61,.36,1)，willChange transform。
- **行为（必须保留）**：没有 Esc；打开时不移焦点；关闭时没有 aria-hidden/inert，桌面上仍能 Tab 进 iframe 内部。桌面 Sidebar 的世界、设置按钮没有 aria-expanded/aria-controls，手机有。iframe 内 401 和退出都跳 window.top。profile「前往我的分身管理记忆」用 target=_top，整个外壳跳到独立页 /agents/me，而不是打开分身抽屉。
- **状态**：无身份时显示「正在加载身份…」（2421、2458）。iframe 内各页自己的加载、空、错误态见各页地图。
- **手机端**：max-md 下 left-0、w-screen，底部让出 56px+safe-area。iframe 内由 layout.tsx:28-58 的内联脚本按父窗口断点写 data-shell。
- **改造风险**：首页一加载，就在隐藏 iframe 里跑 /plaza?embed=1（SolarSystem3D WebGL、热点、帖子、兴趣请求）和 /settings?embed=1。iframe 是独立文档：主题 class、字体、SVG 滤镜 <defs>、背景画都要在 iframe 文档里各自生效，body 光斑会在抽屉内再画一层。改主题时如果只改外壳，抽屉内仍是旧样子。

### GeneratedImage 大图预览 <dialog>（全站唯一的 top-layer 弹层，补细节）
- **位置**：components/GeneratedImage.tsx:80-89（showModal/close 与焦点恢复）、117-129（openPreview/selectForEdit）、161-179（createPortal 到 document.body）；使用方 components/ChatBubble.tsx:191-196、app/page.tsx:2216（compact 参考图）、app/history/page.tsx:343、345
- **结构**：原生 <dialog>，经 showModal() 进入 top layer。头部条 flex flex-wrap justify-between gap-3 border-b px-4 py-3，左边是标题 text-sm，右边是「以此图修改」（仅生成图且有 onEdit 时）、「下载图片」、关闭（X 18）。下面是 <img className="max-h-[80vh] max-w-[92vw] object-contain">。
- **样式**：glass m-auto max-h-[94vh] max-w-[94vw] overflow-auto rounded-[10px] border p-0 text-foreground shadow-2xl backdrop:bg-black/75；style 写 borderColor var(--glass-border)；按钮是 btn btn-quiet h-7 px-2.5 text-xs（手机 h-10）；选中态 text-[color:var(--amber-ink)]。
- **行为（必须保留）**：Esc 触发 onCancel 关闭；点 dialog 自身（遮罩区）关闭（163 判 event.target===currentTarget）；关闭按钮 autoFocus；关闭后恢复打开前的焦点，但 selectForEdit 时 restoreFocusRef=false，焦点交给输入框，且先 dialogRef.close() 再 onEdit()。下载：生产环境同源时走 ?download=1 链接，否则用 blob 或 data URL。
- **状态**：未 loaded 或有 previewError 时不能打开（152 disabled）。参考图变体没有「以此图修改」。editDisabled 时 title=editDisabledReason。
- **手机端**：按钮 h-10 w-10 触控尺寸；弹层宽 94vw。
- **改造风险**：.glass 的 backdrop-filter 作用在 top-layer 元素上。::backdrop 写死黑色 75%，浅色主题下也是黑。它 portal 到 body，所以在 /history 新标签页里同样存在，那里永远是深色（见主题条目）。

### 世界页 iframe 内两个浮层（热点话题展开层、发布弹层）的定位与无障碍缺口
- **位置**：app/plaza/page.tsx:409-516（话题展开层，外层 absolute z-30 + 内联 top16/bottom56/left260/right260；内层 .glass topic-drawer-in，maxWidth 920）、431-436（关闭按钮）；587-653（发布弹层 fixed inset-0 z-50 bg-black/70；内层 .glass max-w-sm）、601（关闭）、630-646（提交）；动画 globals.css:447-457
- **结构**：两个都没有 role=dialog 或 aria-modal，没有 Esc、没有焦点陷阱，打开时也不移焦点。发布弹层的 fixed inset-0 在 iframe 文档内，只盖住世界抽屉，盖不住外层 Sidebar 和聊天区。
- **样式**：.glass、var(--glass-border)、Flame/Plus 图标用 var(--amber-ink)；遮罩 bg-black/70 写死。
- **行为（必须保留）**：话题层：关闭靠 setExpanded(null)。发布弹层：关闭靠 handleClose（351-359），提交 disabled={uploading||!username}，错误显示在 role=alert（642）。
- **状态**：submitError、uploading、未登录禁用。
- **手机端**：话题层 mobile:fixed! top/left/right-4!，非 embed 时底部让出 56px+safe-area+16px，embed 时 mobile:bottom-4!。发布弹层非 embed 时 mobile:bottom 让出底栏，max-h 按 embed 分两种（590-594）。
- **改造风险**：如果对照表要求弹层盖住全屏或有统一的「朱印」弹层外观，iframe 边界决定了它做不到覆盖外壳。无障碍属性目前为零，复刻时不能以「现状」为基线。

### 跨区域要点
- 主题在多文档之间不同步、不持久：layout.tsx:28 把 className="dark" 写死在 html 上；lib/useTheme.ts:18 只 toggle 当前 document 的 class，不写存储，不读 prefers-color-scheme，getServerSnapshot 恒为 true（:17），刷新就回深色。iframe 抽屉（/plaza、/match、/settings、/profile ?embed=1）和 window.open 打开的 /history 新标签（page.tsx:2001）都是独立文档，永远深色。单值配置也都只按深色写：viewport.themeColor '#0E1219'（layout:16）、appleWebApp.statusBarStyle 'black-translucent'（layout:11）、manifest background_color/theme_color '#09090b'（manifest.ts:10-11）。
- 全站没有 color-scheme 声明，原生控件按 UA 默认浅色绘制：history/page.tsx:217-229 两个 type=date（带 .readout bg-card）、MyAgentWorkspace.tsx:140 checkbox（accent-[color:var(--primary)]）、AgentExchangeWorkspace.tsx:201 type=number（fieldClass+readout），还有 confirm/alert 和 <dialog> 的 ::backdrop。
- 断点有两套，且按文件严格分开：可被 iframe 嵌入的页面只用 mobile:（globals.css:7-13，跟随父窗口 data-shell）：plaza 55、match 49、settings 22、profile 16、community 4，max-md 都是 0。其余只用 max-md:：page.tsx 114、history 55、AgentExchangeWorkspace 43、GeneratedImage 24、MyAgentWorkspace 13、agents/[id] 10、ChatBubble 10、ConversationPicker 10、login 7。桌面 iframe 抽屉宽 calc((100vw-56px)*2/3)，视口 1200 时约 763px，小于 768px。如果在 iframe 页面里写 max-md:，会在桌面抽屉里误触发手机布局。
- CSP（next.config.ts:31-44）：font-src 'self' data:、style-src 'self' 'unsafe-inline'、img-src 'self' blob: data:（外加 API origin）、connect-src 'self'，没有任何 https: 外链。外部字体 CDN、外链 CSS、外链图片都会被拦，思源宋体只能自托管或用构建期下载的 next/font。layout.tsx:30-58 的内联脚本依赖 script-src 'unsafe-inline'。frame-src 和 frame-ancestors 都是 'self'。
- proxy.ts:37-40 的 matcher 只放行 api|_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|icons|textures|uploads。生产环境未登录时，public/ 下新建目录（比如 /fonts、/art）里的静态资源请求会被 302 到 /login，登录页（唯一未登录可见页）就加载不到这些字体、背景画、朱印。
- z-index 阶梯（新增背景画、朱印、远山线层要插进来）：Sidebar 手机底栏 z-[70]（Sidebar.tsx:183）；手机对话目录背板 z-[61]、面板 z-[62]（page.tsx:2104/2106）；四个右侧抽屉 z-[55]；抽屉外部背板 z-50（2466）；当前对话记录抽屉 z-50 与它的背板 z-40（2043/2097，absolute，在 relative 行容器内）；页头和输入区 z-[2]（2113/2190）；ChatScrollArea 按钮 z-20（:139）；history 顶栏 z-20（:148）；各独立页 header z-[2]；SolarSystem3D 叠层 z-10（:217/225）。plaza 内部的 z-10/20/30/50 和 match 的 z-10 都在 iframe 文档内，不与外层比较。GeneratedImage dialog 在 top layer。
- 入场与过渡动画清单：tw-animate-css 的 animate-in slide-in-from-left duration-300 只用在 page.tsx:2043 和 2106；四个抽屉用内联 transform 360ms cubic-bezier(.22,.61,.36,1)；globals.css:460-468 的 prefers-reduced-motion 规则把全站 animation 置 none、transition 置 0.01ms，内联 transition 也会被压平。
- 路由可达性：/community 没有任何入口（全库没有 href 指向它，只能手输 URL）；/match 只能通过世界抽屉的「匹配」标签（iframe）进入，独立访问时 Sidebar 无高亮；/agents/[id] 只能从 MyAgentWorkspace.tsx:154 进入（is_public 才显示链接）；/history 只通过 window.open 新标签打开；NewsCardContent 和 page.tsx 的 MiniCloudCard 不被渲染。
- public/ 下的无引用资源：file.svg、globe.svg、next.svg、vercel.svg、window.svg（create-next-app 残留），以及 textures/earth_clouds_2k.jpg、earth_day_2k.jpg、earth_night_2k.jpg、earth_normal.jpg。被引用的纹理只有 SolarSystem3D 用的 milkyway/sun/各行星、Earth3D 用的 match_bg.jpg；package.json 里的 simplex-noise 在 app/components/lib 中无引用。
- 所有页面都是 'use client'，没有按路由设置 metadata，所以每个标签页标题都是 layout.tsx:6 的 'Chloe'，包括新开的 /history 标签页。
- public/sw.js 是自毁型 Service Worker（装上即清缓存、注销自己、刷新客户端）。PwaRegister.tsx 只在 production 注册，dev 下主动注销。新增的静态资源不受 SW 缓存影响，但也没有离线能力。
