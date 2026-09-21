# 独立复核：Fiona 前端视觉重设计（磨砂玻璃仪器 + 一条信号线）

复核日期：2026-09-11。复核输入只有三样：`02-spec.md`、`scratchpad/codex/run1.diff`（4478 行，`diff -ruN` 基线 vs 现状）、`scratchpad/shots/` 19 张 1280×800 截图 + `console-errors.json`。基线源码另从 `scratchpad/baseline/extract/Fiona/frontend` 取用，只用于对照计数。所有命令均由复核员在 `Fiona/frontend` 目录亲自执行（`npm run build` 按任务书不跑）。

## 1. 结论

**最终结论（第 2 轮复核后）：通过**——第 1 轮列出的 2 项必须修复（`--hud-cyan` 悬空引用、`formatRelative` 时区）与派单方追加的第 3 项（抽屉宽度 64px→56px）均已按 `05-fix-round1.md` 机械落实，`run2.diff` 相对 `run1.diff` 只多这三处改动，lint 0 errors / 33 warnings（与第 1 轮逐条相同）、tsc 无输出，返修后截图对话列表时间与消息时间一致。证据见文末「第 2 轮复核」。

第 1 轮结论（保留存档）：不通过——视觉与结构层面按规格落地、门禁全绿、行为红线无违反；但有两处必须返修：`globals.css` 的打字光标仍引用已删除的 `--hud-cyan`，以及新写的 `ConversationPicker.formatRelative` 把后端 UTC 时间当本地时间显示（截图里对话列表 12:41 vs 消息 08:41，差正好一个时区）。两处都是几行的机械修改。

## 2. §8 验收命令逐条

### A. 门禁

**`npm run lint`**（原始输出，去掉了各行末尾重复的规则名列宽空白）

```
> frontend@0.1.0 lint
> eslint

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/page.tsx
     5:56  warning  'WeatherData' is defined but never used                 @typescript-eslint/no-unused-vars
    13:10  warning  'ChevronUp' is defined but never used                   @typescript-eslint/no-unused-vars
    16:25  warning  'UserRound' is defined but never used                   @typescript-eslint/no-unused-vars
    16:36  warning  'Wifi' is defined but never used                        @typescript-eslint/no-unused-vars
    16:42  warning  'WifiOff' is defined but never used                     @typescript-eslint/no-unused-vars
    79:10  warning  'MiniCloudCard' is defined but never used               @typescript-eslint/no-unused-vars
   170:7   warning  'DEMO_MESSAGES' is assigned a value but never used      @typescript-eslint/no-unused-vars
   251:10  warning  'allUsers' is assigned a value but never used           @typescript-eslint/no-unused-vars
   289:9   warning  'nlsWsRef' is assigned a value but never used           @typescript-eslint/no-unused-vars
   290:9   warning  'mediaRecorderRef' is assigned a value but never used   @typescript-eslint/no-unused-vars
   291:9   warning  'audioCtxRef' is assigned a value but never used        @typescript-eslint/no-unused-vars
   295:10  warning  'peerRooms' is assigned a value but never used          @typescript-eslint/no-unused-vars
   296:10  warning  'activePeer' is assigned a value but never used         @typescript-eslint/no-unused-vars
   297:10  warning  'pendingMatches' is assigned a value but never used     @typescript-eslint/no-unused-vars
   298:10  warning  'cardPositions' is assigned a value but never used      @typescript-eslint/no-unused-vars
   301:10  warning  'peerConnected' is assigned a value but never used      @typescript-eslint/no-unused-vars
   307:10  warning  'myGender' is assigned a value but never used           @typescript-eslint/no-unused-vars
   308:10  warning  'matchPref' is assigned a value but never used          @typescript-eslint/no-unused-vars
   553:20  warning  '_' is defined but never used                           @typescript-eslint/no-unused-vars
   557:16  warning  '_' is defined but never used                           @typescript-eslint/no-unused-vars
   628:18  warning  '_' is defined but never used                           @typescript-eslint/no-unused-vars
   757:51  warning  '_' is defined but never used                           @typescript-eslint/no-unused-vars
   761:53  warning  '_' is defined but never used                           @typescript-eslint/no-unused-vars
   825:9   warning  'saveUserSettings' is assigned a value but never used   @typescript-eslint/no-unused-vars
   845:9   warning  'handleCardExpire' is assigned a value but never used   @typescript-eslint/no-unused-vars
   853:9   warning  'handleAcceptCard' is assigned a value but never used   @typescript-eslint/no-unused-vars
   874:9   warning  'handleSkipCard' is assigned a value but never used     @typescript-eslint/no-unused-vars
   910:9   warning  'handleClearChat' is assigned a value but never used    @typescript-eslint/no-unused-vars
  1006:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1344) change on every render. ...  react-hooks/exhaustive-deps
  1443:9   warning  'openPeerChat' is assigned a value but never used       @typescript-eslint/no-unused-vars
  1482:9   warning  'handlePeerKeyDown' is assigned a value but never used  @typescript-eslint/no-unused-vars
  1695:27  warning  Using `<img>` could result in slower LCP and higher bandwidth. ...  @next/next/no-img-element

/Users/yangjing/Desktop/ai-workspace/Fiona/frontend/app/plaza/page.tsx
  600:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. ...  @next/next/no-img-element

✖ 33 problems (0 errors, 33 warnings)

EXIT=0
```

判定：**通过**。0 errors，33 warnings ≤ 35（基线 `gates-baseline.log` 为 `✖ 35 problems (0 errors, 35 warnings)`）。附带核实：`MiniCloudCard`、`handleAcceptCard`、`handleSkipCard`、`handleCardExpire`、`handleClearChat`、`openPeerChat`、`handlePeerKeyDown`、`saveUserSettings` 在基线 `app/page.tsx` 里各只出现 1 次（仅定义），本来就是死代码，不是这次删出来的。

**`npx tsc --noEmit`**

```
（无输出）
EXIT=0
```

判定：**通过**。

**`npm run build`**：按任务书不跑，派单方已报 Turbopack 构建成功、14 条路由。不判定。

### B. 旧类彻底清除

```
$ grep -rnE "hud-[a-z0-9-]+|liquid-glass|lg-refract|hud-card-float|shutter-handle|plaza-card" app components --include='*.tsx' | grep -v "hud-like" | wc -l
       0
$ grep -nE "hud-(panel|corners|card-float|pill|label|pulse|btn|avatar-ring|orb|ekg)|liquid-glass|shutter-handle|hud-scan|body::after" app/globals.css | wc -l
       0
```

判定：**通过**（两条均 0）。但注意这条 grep 的扫描面不含 `hud-cyan`，见 §6 必须修复项 1。

### C. 组件退场

```
$ grep -rnE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l
       0
$ ls components/TopBar.tsx components/AmbientHUD.tsx components/HudOrb.tsx components/HudOrb3D.tsx components/StarField.tsx 2>&1 | grep -c "No such file"
5
$ test -f components/Signal.tsx && echo ok
ok
```

判定：**通过**。补充：全 `frontend/`（排除 node_modules/.next）只剩 `lib/auth.ts:19` 一处注释 `// 通知监听者（TopBar 等）身份变了`，在「明确不动」的 `lib/` 里，基线已有，不算残留。diff 中五个删除文件均为纯 `-` 行（AmbientHUD 128 / HudOrb 13 / HudOrb3D 211 / StarField 180 / TopBar 99 行，`+` 行均为 0）。

### D. 英文伪仪表标签清除

```
$ grep -rnE "VOICE PORT|DATA STREAM|SYS · CLOCK|SR · 16000|CODEC · OPUS|HOLD · TALK|AUDIO ON|AUDIO OFF|HANDS·FREE|TRANSMIT|LISTENING|EXPAND|COLLAPSE" app components --include='*.tsx' | wc -l
       0
```

判定：**通过**。

### E. 侧栏 5 项

```
$ grep -c 'label: "' components/Sidebar.tsx
5
$ grep -nE '"对话"|"分身"|"广场"|"世界"|"设置"' components/Sidebar.tsx | wc -l
       5
```

判定：**通过**。

### F. 三栏退场、下拉退场

```
$ grep -c "w-1/4" app/page.tsx
0
$ grep -c "<select" components/ConversationPicker.tsx
0
$ grep -c "role=\"listbox\"" components/ConversationPicker.tsx
1
$ grep -c "<Signal" app/page.tsx
1
$ grep -c "<Signal" app/login/page.tsx
1
```

判定：**通过**。

### G. 令牌换血

```
$ grep -c "#12100a" app/globals.css
0
$ grep -cE "^\s*--background: #0E1219;" app/globals.css
1
$ grep -cE "^\.glass-card \{" app/globals.css
1
$ grep -cE "^\.echo::after \{" app/globals.css
1
$ grep -c "lg-refract" app/layout.tsx
0
```

判定：**通过**。

### H. 交互逻辑保留

```
$ for s in handleNewChat handleDeleteConversation handleSelectConversation toggleInlineVoice setRecording handsFree voiceOn asrSessionRef handleSelectReferenceImage moveReferenceImage handlePickReferenceImages MiniCloudCard showHistory; do printf "%s %s\n" "$s" "$(grep -c "$s" app/page.tsx)"; done
handleNewChat 2
handleDeleteConversation 3
handleSelectConversation 2
toggleInlineVoice 2
setRecording 6
handsFree 14
voiceOn 8
asrSessionRef 11
handleSelectReferenceImage 2
moveReferenceImage 5
handlePickReferenceImages 2
MiniCloudCard 1
showHistory 3
$ grep -c "onPointerDown" app/page.tsx
1
```

判定：**通过**（每行 ≥ 1；`MiniCloudCard` 基线也是 1，见 A 的说明）。

### I. 范围（仓库根目录）

```
$ git status --porcelain -- backend desktop docs README.md PLAN.md CLAUDE.md frontend/lib frontend/components/ui frontend/next.config.ts frontend/package.json frontend/package-lock.json | grep -vE "^\?\? docs/(design|tasks)/" | wc -l
      72
```

原样跑是 72，因为仓库本来就有大量未提交改动（规格自己也说明了这一点，要求以开工前快照为准）。于是改用快照对照：

```
$ diff scratchpad/codex/git-status-before-run1.txt <(git status --porcelain)
27a28,29
>  M frontend/app/community/page.tsx
>  M frontend/app/globals.css
28a31,33
>  M frontend/app/layout.tsx
>  M frontend/app/login/page.tsx
>  M frontend/app/match/page.tsx
31a37,38
>  M frontend/app/settings/page.tsx
>  D frontend/components/AmbientHUD.tsx
32a40,41
>  D frontend/components/HudOrb.tsx
>  D frontend/components/HudOrb3D.tsx
33a43,44
>  D frontend/components/StarField.tsx
>  D frontend/components/TopBar.tsx
82a94
> ?? frontend/components/Signal.tsx
```

开工后新增的状态行全部在 §2.1 白名单内（其余白名单文件如 `page.tsx`、`Sidebar.tsx`、`agents/`、`components/*.tsx` 在快照里本来就是 M/??，所以不显示为新增行）。`frontend/next.config.ts` 的 M 在快照里已存在。`run1.diff` 的 26 个 `diff -ruN` 头全部落在白名单（20 修改 + 1 新增 + 5 删除）。

判定：**通过**。

## 3. 行为红线核对（§2.2）

| 红线 | 结论 | 证据 |
|---|---|---|
| 不改 state / handler / effect / API 调用 | 通过 | 基线 vs 现状 `app/page.tsx` 计数：`useCallback(` 21=21，`apiFetch(` 14=14，`fetch(` 2=2，`WebSocket(` 1=1，`inert` 2=2；`useEffect(` 18→17，减少的唯一一个是 `enlargedCard` 的焦点 effect（§5.3 明示可删）。删除的 state 只有 `activeCards / hoveredCard / enlargedCard / cardDialogRef / chatCollapsed / recordingBars`（全在 §5.3 允许清单）；删除的 handler 只有 `handleDismissCard`、`getWeatherTheme`（后者只被放大层/DATA STREAM 用）。`setActiveCards([])`、`setEnlargedCard(null)`、`setChatCollapsed(false)` 在账号切换清理、`resetConversationPresentation`、`handleSelectReferenceImage`、参考图读取里的调用随 state 一起删，其余清理语句原样。 |
| `aria-*` / `tabIndex` / 键盘处理 | 通过 | `page.tsx` aria 属性逐条 diff，只少了 `aria-label="卡片详情"`、`aria-label={\`放大${card.source}卡片\`}`、`aria-modal="true"` 三条，全属放大层 / DATA STREAM 卡；`tabIndex` 4→2、`onKeyDown` 5→3，减少的也都是这两块。`Sidebar.tsx` 的 `aria-expanded` / `aria-controls="agent-drawer|exchange-drawer"` 原样保留（`page.tsx` 关抽屉后 `querySelector('button[aria-controls=…]')` 回焦逻辑仍能找到目标）。 |
| `embed=1` 嵌入模式 | 通过 | `plaza / match / settings / profile / community` 六页只删 `{!embedded && <TopBar />}`，`{!embedded && <Sidebar />}` 与 `useSearchParams` 判定未动；抽屉 iframe 改为 `worldTab`/`settingsTab` 切换 src，仍带 `?embed=1`。 |
| 账号切换清理 | 通过 | diff 第 ~781 行处只删了 `setActiveCards([])`、`setEnlargedCard(null)` 两行，其余 `setHandsFree(false)`、`setRecording(false)`、`setInlineRecording(false)` 等原样。 |
| 语音 / 免提 / 朗读 / ASR / TTS | 通过 | `recording`、`voiceText`、`asrSessionRef`、`toggleInlineVoice`、`handleConfirmTts` 均在；按住说话按钮的 `onPointerDown/onPointerUp` 与 `disabled={conversationLoading \|\| !currentConversation \|\| isLoading}` 逐字符与左栏原按钮一致。 |
| 不引入依赖、不 `npm install`、不用 `next/font/google` | 通过 | `package.json`/`package-lock.json` 不在 diff 里；`layout.tsx` 无 `next/font`；`grep -rn geist app components` 为空；字体走 `--font-sans-stack` / `--font-mono-stack`。 |
| 不新增 `!important` | 通过 | `globals.css` 里 `!important` 计数 23 → 22（删掉的是 `.dark .cloud-card { animation-duration: 10s !important }`）。 |
| `.dark` 机制 | 通过 | `layout.tsx` 仍是 `<html lang="zh-CN" className="dark h-full">`；`Sidebar.toggleTheme` 的 `classList.toggle("dark")` 未动；`@custom-variant dark (&:is(.dark *))` 未动。 |
| 不改 CSP / 无外链 | 通过 | `next.config.ts` 不在 diff 里；新增 SVG 全部内联，`--grain` 为 data URI。 |
| 白名单外文件 | 通过 | 见 §2 I。`ChatScrollArea.tsx`、`SolarSystem3D.tsx`、`Earth3D.tsx`、`lib/**`、`components/ui/**` 均未出现在 diff。 |

一处需要说明但不算违反：`ConversationPicker` 每行的删除按钮没有 `disabled={disabled}`（基线的删除按钮有）。规格 §5.2 给的模板本身就没写 `disabled`，且 `page.tsx:953-955` 的 `handleDeleteConversation` 首行就 `if (conversationLocked || conversationLoading) return;`，所以 locked 期间点击无副作用，只是少了视觉禁用态。列入 §7。

## 4. §3–§7 逐项对照表

| 条款 | 状态 | 位置 / 说明 |
|---|---|---|
| §3.1 令牌整段替换（`:root` / `.dark`） | 做了 | `globals.css` 第 46–156 行，逐值与规格一致；深色 `--grain` 也写成 `%23`。 |
| §3.1 `@theme inline` 三行字体变量 | 做了 | `--font-sans/mono/heading` 均指向 `-stack` 变量。 |
| §3.2 `@layer base` body（三层光斑 + fixed） | 做了 | 第 158–170 行，与规格逐字一致。 |
| §3.3 删除扫描线、旧气泡、hud-panel/corners、card-float、liquid-glass、pill、plaza-card、shutter、label/pulse、btn、avatar-ring、orb、orb-v2、ekg、`.dark .cloud-card` | 做了 | diff 第 47–883 行全部为 `-`；§2 B 的 grep 为 0。`.hud-like-burst/pop` 保留。 |
| §3.3 `.typing-cursor::after` 只删 `text-shadow` | 做偏了 | 按字面做了（只删了 `text-shadow`），但剩下的 `color: var(--hud-cyan)` 引用的变量已随 `.dark` 块被删，现为悬空引用。**必须修复项 1**。 |
| §3.3 reduced-motion 选择器改 `*, *::before, *::after` | 做了 | 第 432–435 行。 |
| §3.3 保留 `.glass`、`.msg-in-*`、`.wave-bar`、滚动条、ticker、topic-drawer、blink、hud-like | 做了 | 现状文件第 282–425 行均在。 |
| §3.4 `.glass` / `.glass-card` + `@supports not` + `prefers-reduced-transparency` | 做了 | 第 172–196 行，与规格一致。 |
| §3.4 `.readout / .echo / .signal / .state-dot / .btn* / .chip* / .tag*` | 做了（有一处偏离） | 第 198–265 行。偏离：这组类被包进 `@layer components { … }`，规格给的是无层 CSS。这个偏离是合理的——Tailwind v4 里无层规则会压过 `utilities` 层，规格自己写的 `readout text-[11px]`、`btn h-7 px-2.5`、`btn btn-quiet w-[34px] px-0` 只有放进 `components` 层才能被工具类覆盖。`.glass / .glass-card / .bubble-*` 仍在层外。见 §7。 |
| §3.4 `.bubble-user / .bubble-ai` 新写法 | 做了 | 第 267–276 行。 |
| §3.5 类名映射表（liquid-glass→glass、hud-btn→btn、hud-pill→chip、plaza-card→glass-card、hud-label 文本删/中文化、hud-pulse→state-dot、avatar-ring 删、clipPath/textShadow 删） | 做了 | §2 B/D 的 grep 全 0；`grep -n "textShadow\|clipPath\|inset 0 1px 0 rgba(255,255,255,0.62)" app/**/*.tsx components/*.tsx` 为空。 |
| §4.1 `layout.tsx` 删 `lg-refract` SVG、themeColor `#0E1219` | 做了 | diff 第 940–983 行，只改这两处。 |
| §4.2 Sidebar 5 项 + Globe 图标 + 删多余 import | 做了 | `navItems` 5 项；import 精简为 `MessageCircle, Bot, Orbit, Globe, Settings, Moon, Sun`。 |
| §4.2 props 删 match/community/profile 三组；`onHistoryClick` 二选一 | 做了 | 类型里保留了 `onHistoryClick?`（未解构、未渲染），tsc 干净，符合「保留不用」。 |
| §4.2 `w-14`、`text-[10px]`、active 只用 amber 文字、非 active 悬停样式 | 做了 | 逐类名一致。 |
| §4.2 Logo 双圆 SVG（r=5.5，(9,12)/(15,12)，stroke 1.5，amber，fill none） | 做了 | `Sidebar.tsx` 第 87–90 行。 |
| §4.2 草莓余额搬入（只搬余额 effect，不搬时钟） | 做了 | `balance` state + `useEffect`（`fetchBalance`、60s 轮询、`storage` / `fiona-user-changed` 监听）与 `TopBar.tsx` 第 22–45 行逐字相同；阈值 <30 → `--rec`，<100 → `--amber-ink`；主题按钮仍在最底部。 |
| §4.3 删 TopBar 及 9 处引用 | 做了 | 9 个文件的 import 与 `<TopBar />` 均为 `-` 行；§2 C 为 0。 |
| §4.4 `DrawerName` 四值；删 matchOpen/communityOpen/profileOpen；新增 `worldTab` / `settingsTab` | 做了 | diff 第 ~225–240 行。 |
| §4.4 「世界」抽屉两 chip + iframe src 切换；删独立匹配抽屉 | 做了 | diff 第 ~1830–1860 行；截图 07/09 可见。 |
| §4.4 三抽屉 map 改成单个「设置」抽屉两 chip；社群页文件保留 | 做了 | diff 第 ~1862–1892 行；`community/page.tsx` 仍在。 |
| §4.4 抽屉 `glass`、boxShadow `-12px 0 32px rgba(0,0,0,0.28)`/`none`、borderLeft `var(--glass-border)`、头部类名、删 `DRAWER_*_STYLE` | 做了 | agent / exchange / world / settings 四个抽屉逐项一致。 |
| §4.4 历史抽屉 `glass` + 新 style + `left-14`；两处背板 `left-14` | 做了 | diff 第 ~1511–1515、1570、1897 行。 |
| §5.1 `Signal.tsx` 算法（140 点、包络、三重正弦、level 追踪、亮点轨迹、reduced-motion、mode 走 ref、卸载 cancel） | 做了 | 逐式对照一致；额外把 `dt` 钳到 ≤0.05s（防标签页切回时跳变），属安全增强。 |
| §5.2 `ConversationPicker` 改列表，props 签名不变 + 两个可选 prop | 做了 | 结构与规格模板一致；`aside/glass/listbox/option/aria-selected`、页脚「对话仅你可见 / 完整历史」都在。 |
| §5.2 `formatRelative` | 做偏了 | 分支逻辑（当天 HH:mm / 昨天 / 星期 / MM/DD）对，但用 `new Date(iso)` 直接解析后端 `updated_at`；后端该列是 SQLite `CURRENT_TIMESTAMP`（UTC、`YYYY-MM-DD HH:MM:SS`、无时区），V8 把这种串当本地时间，结果偏一个时区。同库 `history/page.tsx:32`、`plaza/page.tsx:29` 都是 `.replace(" ", "T") + "Z"` 再解析。**必须修复项 2**。 |
| §5.2 三种状态文案 + loading 行 | 做了 | 文案逐字一致。 |
| §5.3 两栏结构（Picker 左栏；对话区 relative；header 网格；Signal；状态点+状态词；朗读/免提 chip） | 做了 | diff 第 ~1577–1620 行；截图 02–04。 |
| §5.3 `ChatScrollArea` 用 `absolute inset-0 flex flex-col pt-16 pb-[172px]` 包住 | 做了 | 采用规格给的兜底写法，`ChatScrollArea.tsx` 未动。 |
| §5.3 footer 输入区：外层 `var(--fill)` 框、chip 小按钮、发送按钮新类、按住说话按钮搬入、提示行 | 做了 | 逐项一致；提示行左侧在规格文案后保留了原有的「· 改图可上传参考图或点“以此图修改”」后缀（原文本保留，不算偏离）。 |
| §5.3 `signalMode` 派生与状态词 | 做了 | `recording \|\| inlineRecording ? "listening" : isLoading ? "speaking" : "idle"`。 |
| §5.3 删「新建聊天」头部按钮；删所有 `*_STYLE` 常量 | 做了 | 常量块整段 `-`；lint 无「未使用常量」新告警。 |
| §5.3 删 StarField / 左栏 VOICE PORT / 卷帘门 / 右栏 DATA STREAM / 放大层 / AmbientHUD / NewsCardContent import | 做了 | 见 §3 表。`weatherCN` 仍被 `handleSend` 的天气口播文本使用，正确保留。 |
| §5.3 保留 `MiniCloudCard`（改 `glass-card`）等 | 做了 | `className="glass-card w-64 px-4 py-3"`。 |
| §5.4 ChatBubble 头像、说话者标签、`max-w-[640px]` / 520px、天气卡三列、网页卡 `glass-card` + amber Globe、状态行、帮我读/不用/重新生成按钮、meta 时间 `readout`、上传图圆角 | 做了 | diff 第 3154–3340 行逐项一致。天气卡去掉了原来的 `conditionIcon`/风速/能见度（规格结构里没有这些，属按规格收敛）。 |
| §5.5 GeneratedImage / NewsCardContent 只改类名 | 做了 | 圆角 `rounded-[10px]`、描边 `var(--glass-border)`、`hud-label→readout`；两文件里已无 `rounded-full/2xl/xl`、`hud-`。GeneratedImage 原本没有 hud-btn/胶囊按钮，无需替换。 |
| §6.1 AgentIdentityCard 新结构 + `echo`（>12 字回退 28px） | 做了 | 与规格模板逐行一致；截图 05/11/12。 |
| §6.2 页面头部 sticky glass + 内层 `max-w-[976px]`；标题 `text-xl font-medium tracking-[-0.01em]` | 做了 | `MyAgentWorkspace`、`AgentExchangeWorkspace` 两处。`agents/[id]/page.tsx` 本身没有页面头部，只做了 TopBar 删除与 `hud-btn→btn`、错误框→`glass-card`。 |
| §6.2 `fieldClass` / `buttonClass` / `primaryButtonClass` / 红色动作 `btn-danger` / 公开名片开关 `glass-card p-4` | 做了 | 两个工作区文件均改；AgentMemoryPanel 清空按钮 `btn btn-danger`。 |
| §6.2 广场搭档卡 / 公开分身卡 `glass-card p-4 flex flex-col gap-2.5`、选中态 amber 边、模型名 `readout` | 做了 | 新增 `targetId` 派生量做选中判断；`Participant` 里 `模型：<span className="readout">`。 |
| §6.2 标签页下划线式 + 待处理计数 `readout` amber | 做了 | 截图 06/13。 |
| §6.2 交流详情回合数 `第 <b>N</b> 次 / M`；阶段条 | 做了 | 详情里找到了 `message.stage`（draft/review/revision），按最后一条带 stage 的消息渲染三段式阶段条，仅 `workflow` 时显示。 |
| §6.2 「当前作品」`glass-card`、头行字数 `readout`、下载三按钮 `btn` | 做了 | 头行右侧原来的「AI 审稿通过 · 待你验收 / 草稿 · 待修订 / 草稿」状态文字被字数替换掉了（规格头行只写了字数）。见 §7。 |
| §6.2 AgentMemoryPanel 条目样式 | 做了 | `border-b py-1.5 text-[13px] text-muted-foreground`。 |
| §6.2 AgentMemoryPanel 标题行右侧「修订 N」`readout` | 没做（无字段） | `AgentMemoryPanel.tsx` 与 `lib/agents.ts` 里没有任何 revision 字段可用；按 §9 应「跳过 + 在报告里说明」。实施者报告需注明，本身不阻塞。 |
| §6.3 六页删 TopBar；`hud-*`/`liquid-glass`/`plaza-card` 替换；SolarSystem3D / Earth3D / cloud-card 保留 | 做了 | plaza：分类卡标题去英文前缀、发布弹窗中文化、`hud-pill→chip`、发布按钮 `btn btn-primary`、去发光 boxShadow；match：`cloud-card liquid-glass → cloud-card glass`，连内联 `<style>` 的选择器一起改；history/profile/settings：卡片 `glass-card`、按钮 `btn/btn-quiet/btn-danger`、`readout`。四页页面头部基线就是 `glass border-b …`，`.glass` 重写后自动变磨砂（截图 16–19）。 |
| §7 登录页结构、双圆 SVG、`echo` Chloe、Signal idle、`glass` 表单卡、输入框类、`btn btn-primary w-full h-10`、次按钮 `btn btn-quiet`、赠送文案 `readout`、开发入口保留、删 🍓 与「你的私人 AI 助理」、placeholder 字距复位 | 做了 | diff 第 983–1133 行逐项一致；三步 handler 与 `NODE_ENV` 判断未动；截图 01。 |

## 5. 截图核对（逐张一句话）

| 文件 | 结论 |
|---|---|
| 01-login-dark | 双圆标 + `echo` 描边偏移的 Chloe + 信号线 + 磨砂表单卡，无 🍓/英文伪标签/发光；通过。 |
| 02-chat-empty-dark | 两栏（对话列表 + 对话），头部信号线带跑动亮点、「待命」状态点、朗读/免提 chip，侧栏 5 项 + 🍓200，无星空/球/三栏/尖括号；通过。**但列表时间 12:36 与本机时间不符（见必须修复项 2）。** |
| 03-chat-new-dark | 新对话进入列表顶部并高亮；同上时区问题（12:41）。 |
| 04-chat-after-send-dark | 用户消息为浅层块，分身消息无气泡 + 「■ Chloe」说话者标签 + `readout` 时间 08:41；列表却显示 12:41，差 4 小时 = UTC 与 EDT 之差，坐实时区 bug。 |
| 05-drawer-agent-dark | 分身抽屉磨砂、名片 `tag-amber` + `echo` 名字 + 头像 glyph，私有记忆 `btn-danger`；通过。 |
| 06-drawer-plaza-dark | 分身广场下划线标签页、三张 `glass-card` 搭档卡、模型名等宽读数、`btn-primary`；通过。 |
| 07-drawer-world-dark | 「世界」抽屉头部两 chip（热点与帖子 高亮），plaza 嵌入保留太阳系 3D，分类卡中文标题 + `readout` 序号，玻璃透出星空；通过。 |
| 08-drawer-settings-dark | 「设置」抽屉两 chip（设置/账户），身份 chip、`btn`、`btn-danger`；通过。 |
| 09-drawer-world-match-dark | chip 切到「匹配」，iframe 变为 `/match?embed=1`，地球 3D 保留；通过。 |
| 10-chat-light | 浅色：`#F3F5F8` 底 + 光斑，文字 `#141A22` 清晰可读，选中对话有 `bg-secondary` 底，信号线为 `#9E6209`；通过。 |
| 11-drawer-agent-light | 浅色分身抽屉可读，`echo` 描边为深琥珀；通过。 |
| 12-page-agents-me | 独立页：sticky 磨砂头部 + `text-xl` 标题、名片、记忆面板；通过。 |
| 13-page-agents | 独立广场页同 06；通过。 |
| 14-page-plaza | 独立 plaza 页，太阳系 3D 保留，分类卡 `glass-card`；六张卡显示「请求较频繁，请稍后重试」对应 `console-errors.json` 的 429——是后端/上游热点接口限流（同一轮截图先在抽屉里加载过一次），前端 fetch 逻辑不在 diff 里，不是本次改动的回归。 |
| 15-page-match | 独立匹配页，地球 3D + 「最近聊天」中文标签；通过。 |
| 16-page-settings | 磨砂头部、三张 `glass-card`、chip/btn/btn-danger；通过。 |
| 17-page-profile | 磨砂头部、`glass-card`、底部 `btn`；通过。 |
| 18-page-history | 磨砂头部与左栏、日期分组 `glass-card`、`readout` 条数与时间；页内消息气泡仍是该页自有的琥珀实心样式（history 页气泡不在规格改动范围）；通过。 |
| 19-page-community | 磨砂头部、占位内容；通过。 |

整体：19 张里没有任何旧 HUD 痕迹（尖括号、扫描线、切角、发光、英文伪标签、3D 球、三栏）；玻璃都透出底场；浅色主题可读；信号线在登录页与对话页都在。

## 6. 必须修复项

1. **`frontend/app/globals.css` 第 312–317 行 `.typing-cursor::after`**：把 `color: var(--hud-cyan);` 改成 `color: var(--amber-ink);`。理由：`--hud-cyan` 已随 §3.1 的 `.dark` 整段替换被删，现在是悬空引用，光标退化成继承文字色，等于「打字光标的琥珀指示灯」丢了；规格 §3.3 的「其余保留」是在假定该变量还在的前提下写的。改完 `grep -rn "\-\-hud-" app components` 必须为 0。

2. **`frontend/components/ConversationPicker.tsx` 第 8–9 行 `formatRelative`**：把 `const date = new Date(iso);` 改成
   ```ts
   const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");
   ```
   理由：后端 `conversations.updated_at` 是 SQLite `CURRENT_TIMESTAMP`（`backend/agent_store.py:141`、`backend/database.py:475`），格式 `YYYY-MM-DD HH:MM:SS`、UTC、无时区标记；`new Date()` 直接解析会当本地时间，截图 02–04 里列表显示 12:36/12:41 而同一对话的消息时间是 08:41。同库 `app/history/page.tsx:32` 与 `app/plaza/page.tsx:29` 都是 `.replace(" ", "T") + "Z"` 的解法，照此对齐即可；带时区标记的 ISO 串（将来若后端改用）走原样解析。改完在隔离环境重截 02–04，列表时间必须与消息 meta 时间一致。

## 7. 可优化项（不阻塞，留给用户裁决）

1. `globals.css` 把 `.readout/.echo/.signal/.state-dot/.btn*/.chip*/.tag*` 包进 `@layer components`，规格给的是无层 CSS。这个偏离是对的（否则 `readout text-[11px]`、`btn h-7` 这类规格自己写的覆盖不生效），建议把规格 §3.4 同步改成 `@layer components`，避免下次有人「按规格」改回去。
2. `app/page.tsx` 四个抽屉的宽度仍按 64px 侧栏算（`min(960px, calc(100vw - 64px))`、`calc((100vw - 64px) * 2 / 3)`），侧栏已改 56px，抽屉右侧与侧栏之间多 8px 空隙。规格 §4.4 没要求改，可改成 56px。
3. `ConversationPicker` 每行删除按钮建议补 `disabled={disabled}`，与「切换」按钮和基线行为一致；当前靠 `page.tsx` 的 handler 守卫兜底，功能不受影响，只是 locked 期间按钮看起来可点。
4. `AgentExchangeWorkspace.ExchangeArtifact` 头行右侧原来的稿件状态（「AI 审稿通过 · 待你验收 / 草稿 · 待修订 / 草稿」）被字数读数替换后，`needs_revision` 状态在界面上不再有独立文字（approved 状态下方段落仍有说明）。规格 §6.2 头行只写了字数，若要保留状态可在字数左侧加 `tag`。
5. `page.tsx` 历史抽屉（`showHistory`）底部的「查看完整历史记录」按钮与新列表页脚的「完整历史」功能重复；规格说的是「搬过来」，可以删掉抽屉里那一份。
6. `AgentMemoryPanel` 的「修订 N」读数因数据里没有 revision 字段而未做，实施者的 03-report 应按 §9 注明；若后端将来暴露修订号再补。
7. 截图 14 的 429 与「请求较频繁」来自后端/上游热点接口限流，与本次改动无关，但隔离环境截图脚本若先开抽屉再开独立页会稳定触发，建议截图前给热点接口留冷却时间或只截一次。

## 第 2 轮复核

范围：只核验第 1 轮的必须修复项 1、2 与派单方追加的第 3 项。输入：`05-fix-round1.md`、`scratchpad/codex/run2.diff`（返修后累计 diff）、`scratchpad/shots2/r2-01-chat.png`、`r2-02-drawer-agent.png`。所有命令在 `Fiona/frontend` 目录亲自执行。

### 改动范围对照：`diff run1.diff run2.diff`

```
$ wc -l run1.diff run2.diff
    4478 run1.diff
    4484 run2.diff
$ diff run1.diff run2.diff
49c49
< +++ .../frontend/app/globals.css	2026-09-11 08:25:18
---
> +++ .../frontend/app/globals.css	2026-09-11 09:06:50
855c855,856
< @@ -661,7 +312,6 @@
---
> @@ -660,8 +311,7 @@
>  }
858c859
<    color: var(--hud-cyan);
---
> -  color: var(--hud-cyan);
859a861
> +  color: var(--amber-ink);
1209c1211
< +++ .../frontend/app/page.tsx	2026-09-11 08:28:46
---
> +++ .../frontend/app/page.tsx	2026-09-11 09:06:50
2122c2124
<            width: "min(960px, calc(100vw - 64px))",
---
> -          width: "min(960px, calc(100vw - 64px))",
2124a2127
> +          width: "min(960px, calc(100vw - 56px))",
2145c2148
<            width: "min(960px, calc(100vw - 64px))",
---
> -          width: "min(960px, calc(100vw - 64px))",
2147a2151
> +          width: "min(960px, calc(100vw - 56px))",
2172c2176
<            width: "calc((100vw - 64px) * 2 / 3)",
---
> -          width: "calc((100vw - 64px) * 2 / 3)",
2174a2179
> +          width: "calc((100vw - 56px) * 2 / 3)",
2222c2227
<            width: "calc((100vw - 64px) * 2 / 3)",
---
> -          width: "calc((100vw - 64px) * 2 / 3)",
2225a2231
> +          width: "calc((100vw - 56px) * 2 / 3)",
3342c3348
< +++ .../frontend/components/ConversationPicker.tsx	2026-09-11 08:25:09
---
> +++ .../frontend/components/ConversationPicker.tsx	2026-09-11 09:06:50
3353c3359
< +  const date = new Date(iso);
---
> +  const date = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");
```

除三个文件头的时间戳外，差异只落在 `globals.css` 一行、`page.tsx` 四行、`ConversationPicker.tsx` 一行——正是返修指令的三处，没有其他改动。

### 门禁（返修后）

```
$ npm run lint
…（33 条 warning，逐条与第 1 轮相同，仅行号无变化）
✖ 33 problems (0 errors, 33 warnings)
EXIT=0
$ npx tsc --noEmit
（无输出）
EXIT=0
```

`diff <(第 1 轮 lint 去行号) <(第 2 轮 lint 去行号)` 输出为空（IDENTICAL_MESSAGES），返修没有引入或消除任何告警。

### 逐条判定

**1. `globals.css` `.typing-cursor::after` 的 `--hud-cyan` → `--amber-ink`**

```
$ grep -c "hud-cyan" app/globals.css
0
$ grep -n "typing-cursor::after" -A3 app/globals.css | grep color
314-  color: var(--amber-ink);
$ grep -rn "\-\-hud-" app components | wc -l
       0
```

判定：**通过**。改前 1 → 改后 0；全 `app/`、`components/` 已无任何 `--hud-*` 引用。

**2. `ConversationPicker.formatRelative` 时区解析**

```
$ grep -c 'replace(" ", "T") + "Z"' components/ConversationPicker.tsx
1
$ grep -n "const date = new Date" components/ConversationPicker.tsx
9:  const date = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");
```

截图 `r2-01-chat.png`：对话列表两条分别显示 `08:41`、`08:36`，右侧用户消息 meta 显示 `08:41`；第 1 轮同一数据是 `12:41` / `12:36` vs `08:41`。列表时间与消息时间已一致，UTC 偏移消失。带时区标记的串走原样解析分支，与 `history/page.tsx` 的 `parseUtcTimestamp` 做法一致。

判定：**通过**。

**3. `page.tsx` 四个抽屉宽度 `100vw - 64px` → `100vw - 56px`**

```
$ grep -c "100vw - 64px" app/page.tsx
0
$ grep -c "100vw - 56px" app/page.tsx
4
$ grep -n "100vw - 56px" app/page.tsx
1762:          width: "min(960px, calc(100vw - 56px))",
1793:          width: "min(960px, calc(100vw - 56px))",
1814:          width: "calc((100vw - 56px) * 2 / 3)",
1849:          width: "calc((100vw - 56px) * 2 / 3)",
```

四处对应分身 / 分身广场（`min(960px, …)`）与世界 / 设置（`* 2 / 3`）四个抽屉，`min` 与 `2/3` 两种写法都改到了。截图 `r2-02-drawer-agent.png`：分身抽屉右贴边、左缘约 x=320（1280 宽下 `min(960px, 1224px)` = 960px，与第 1 轮的 960px 相同，所以本轮截图看不出差别；该修改只在视口 < 1016px 时才有可见效果），抽屉内容与第 1 轮一致，无回归。

判定：**通过**。

### 第 2 轮新发现

无需新增必须修复项。本轮没有发现新的问题，§7 可优化项保持第 1 轮清单不变（其中第 2 条「抽屉宽度 64px」已由本轮第 3 项解决，可视为关闭）。
