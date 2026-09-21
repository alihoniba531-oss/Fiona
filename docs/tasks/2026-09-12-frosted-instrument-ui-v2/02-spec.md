# 规格 v2：Fiona 前端视觉重设计落地——磨砂玻璃仪器 + 一条信号线（按原型逐页复刻）

任务日期：2026-09-12。任务级别：L3（UI 大改，纯视觉层，不改任何后端、接口、路由、数据与交互语义）。

**为什么有 v2**：v1 的实现被作者否决——它把旧界面「换了一层皮」：令牌换了、类名换了，但广场、世界、历史等页面的结构、层次、控件形态还是旧的（大图标搭档卡、眉标、箭头按钮、旧热点卡、实心橙块）。**本次要求：以原型为结构与像素的双重真源，逐页复刻，而不是替换类名。** 代码已还原到 v1 开工前的基线，从零做。

你是独立执行进程，看不到任何对话上下文。**本文件没写的，就是禁止你自由发挥的。** 拿不准时按第 9 节判据处理。

## 0. 阅读顺序与真源

1. 通读本文件。
2. 打开 `docs/design/chloe-ui-proposal.html`（已拍板的设计原型，单文件 HTML，约 700 行）。它是**结构真源**也是**数值真源**：每个 `data-screen` 的 DOM 层级、类名语义、文案层级、字号、间距、圆角、玻璃参数、信号线算法、分身名排法，全部照搬。本文件引用它时写「原型 §xxx」，指其 `<style>` 里的注释分节或 `data-screen` 的 section。
3. 读 `frontend/AGENTS.md`、`frontend/CLAUDE.md`，以及 `frontend/node_modules/next/dist/docs/` 里与你要碰的 API 相关的文档（Next.js 16 与你训练数据里的不同）。
4. 再读第 2 节白名单里的文件，每个文件先找到它在 §2.4 对照表里对应的原型 section，再动手。

## 1. 产品目标

Chloe（项目 Fiona）是「每个人自己的 AI 分身」产品。现有界面是暖琥珀 HUD 风：液态玻璃折射、四角尖括号、扫描线、3D 能量球、三栏悬浮卡、英文伪仪表标签（VOICE PORT / DATA STREAM / SYS·CLOCK）。作者要求改成**「科技感 + 简洁」**，方向已定为**「磨砂玻璃仪器，一条信号线」**：

- 蓝灰墨底、琥珀唯一强调色（延续品牌色，但只做哑光指示灯，不发光）。
- 外壳与卡片是**磨砂玻璃**：统一模糊 + 半透明 + 细颗粒；**不折射、不发光、没有湿润高光**。
- 中文标签；数字、时间、回合数、模型名用等宽读数。**没有眉标**（标题上方的小字标签），**没有全大写追踪英文**，**按钮文字里没有箭头**。
- 唯一动效：对话头部的**信号线**（待命 / 正在听 / 正在说 三态）。3D 球、轨道粒子、频谱条、心电图、扫描线、星空全部退场。
- 对话页三栏收成两栏；工具卡片回到消息里。
- 侧栏 8 项收成 5 项：对话 / 分身 / 广场 / 世界 / 设置。
- **层次靠 1px 线和两级表面，不靠色块**：不再有 `bg-primary/5`、`bg-primary/10`、`border-primary/25` 这类琥珀色洗底的容器；卡片一律 `glass-card`，分区靠 `border-t`。

## 2. 硬约束

### 2.1 白名单（只准改这些；改动范围之外的任何文件一律不动）

**修改：**
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/page.tsx`
- `frontend/app/login/page.tsx`
- `frontend/app/agents/[id]/page.tsx`
- `frontend/app/plaza/page.tsx`
- `frontend/app/match/page.tsx`
- `frontend/app/profile/page.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/app/community/page.tsx`
- `frontend/app/history/page.tsx`
- `frontend/components/Sidebar.tsx`
- `frontend/components/ChatBubble.tsx`
- `frontend/components/ConversationPicker.tsx`
- `frontend/components/AgentIdentityCard.tsx`
- `frontend/components/AgentMemoryPanel.tsx`
- `frontend/components/MyAgentWorkspace.tsx`
- `frontend/components/AgentExchangeWorkspace.tsx`
- `frontend/components/GeneratedImage.tsx`
- `frontend/components/NewsCardContent.tsx`

**新增：**
- `frontend/components/Signal.tsx`

**删除（只删这 5 个，删前确认全库无其他引用）：**
- `frontend/components/TopBar.tsx`
- `frontend/components/AmbientHUD.tsx`
- `frontend/components/HudOrb.tsx`
- `frontend/components/HudOrb3D.tsx`
- `frontend/components/StarField.tsx`

**明确不动：** `backend/**`、`desktop/**`、`frontend/lib/**`、`frontend/components/ui/**`、`frontend/app/shadcn-tailwind.css`、`frontend/components/ChatScrollArea.tsx`、`frontend/components/SolarSystem3D.tsx`、`frontend/components/Earth3D.tsx`、`frontend/components/PwaRegister.tsx`、`frontend/app/manifest.ts`、`frontend/next.config.ts`、`frontend/package.json`、`frontend/package-lock.json`、`frontend/proxy.ts`、所有 `docs/**`（除本任务目录的 `03-report.md`）、`README.md`、`PLAN.md`、`CLAUDE.md`。

### 2.2 行为红线

- **不改任何交互语义**：所有 state、handler、effect、API 调用、路由、`aria-*`、`inert`、`tabIndex`、键盘处理、`embed=1` 嵌入模式、账号切换清理逻辑、轮询、下载、`data-*` 测试锚点原样保留。你做的是把 JSX 搬进新布局、重排层级、换控件形态，不是改行为。
- 不引入任何依赖，不运行 `npm install`，不用 `next/font/google`（沙箱无网络）。字体全部走系统栈（见 §3.1）。
- 不新增 `!important`（现有滚动条块里的保留不动）。
- `.dark` 切换机制保留：`layout.tsx` 的 `<html className="dark h-full">` 与 `Sidebar` 的 `document.documentElement.classList.toggle("dark")` 不动；`@custom-variant dark` 不动。
- 不改 `frontend/next.config.ts` 的 CSP；因此不得引入外链字体、外链脚本。
- 完成任何一个里程碑后**不得回滚**它去迁就后面的困难；卡住就按第 9 节处理。

### 2.3 分工建议（可用多 subagent 并行，按文件不重叠切分）

- A：`globals.css` + `layout.tsx` + `login/page.tsx` + `Signal.tsx`
- B：`page.tsx`（M2 的抽屉与侧栏接线 + M3 的对话页，同一文件只能一个人改）
- C：`Sidebar.tsx` + 删除 `TopBar.tsx` + `ChatBubble.tsx` + `ConversationPicker.tsx` + `GeneratedImage.tsx` + `NewsCardContent.tsx`
- D：`AgentIdentityCard.tsx` + `AgentMemoryPanel.tsx` + `MyAgentWorkspace.tsx` + `AgentExchangeWorkspace.tsx` + `agents/[id]/page.tsx`
- E：`plaza` / `match` / `profile` / `settings` / `community` / `history` 六个页面

所有人依赖的**类名与令牌在 §3 已全部定死**，不必等 A 写完再开工。

### 2.4 复刻对照表（每个文件动手前先看这一行）

| 应用位置 | 原型 section | 必须复刻的结构（不是建议，是判据） |
|---|---|---|
| `login/page.tsx` | `[data-screen="login"]` | 双圆标 → `.echo` 字标 Chloe → 一句话「每个人自己的分身。」→ 待命信号线 → `.login-panel` 玻璃面板里放表单与说明。 |
| `page.tsx` 对话区 | `[data-screen="chat"]` | `.convs` 对话列表（头部：标题「对话」+ 时钟 + 加号；条目：标题 / 时间读数 / 悬停删除；页脚：「对话仅你可见」+「完整历史」）、`.talk-head`（glyph + 名字 + 副标 ｜ 信号线 ｜ 状态点 + 状态词 + 「朗读」「免提」chip）、`.transcript`（分身：琥珀方块 + 名字标签 + 无气泡正文，最宽 640；我方：浅层块右对齐，最宽 520；时间读数）、`.composer`（玻璃条 → `--fill` 内框 → 上行 chips「图片」「生成图片」等 → 右侧麦克风 / 按住说话 / 发送 → 底部提示行）。头部与输入区浮在滚动内容之上。 |
| `MyAgentWorkspace.tsx`、`agents/me`、分身抽屉 | `[data-screen="agent"]` | 粘性玻璃 `.page-head`（标题 + 一句话）；`.agent-grid` 两栏 `minmax(0,1fr) 340px`：左表单（`.field-row` 头像符号 96px + 名称；简介；性格；`.switch-row` 公开名片；保存按钮 + 「有未保存的修改」）；右栏 `.idcard`（tag「AI 分身」+ 读数「名片预览」；`.echo` 名字 40px；简介；页脚 glyph + 「由用户创建的人工智能分身」）→ `.note` 盾牌提示 → `.memory`（标题 + 读数；条目 13px 灰、`border-b`；页脚「查看全部」+ 红色「清空记忆」）。 |
| `AgentExchangeWorkspace.tsx`、`/agents`、广场抽屉 | `[data-screen="plaza"]` | 粘性玻璃 `.page-head`（标题「广场」+ 一句话 + 右侧「刷新」quiet 按钮）；`.tabs` 下划线标签（应用保留 5 个：单人体验 / 体验记录 / 发现分身 / 收到的邀请 / 发出的邀请；待处理数量用 `.count` 琥珀读数，不再拼「· N 待处理」）；「单人体验」= `.partners` 三张**紧凑** `.partner` 卡（标题 + tag「官方 AI」 ｜ 一句简介 ｜ 模型名读数；**不放大 emoji 图标、不放示例话题、不放按钮**，点整张卡选中 = 琥珀描边）+ 选中后**同页下方**出现 `.start-form` 两栏（话题 textarea + 计数读数 ｜ 回复次数 `.field` + 「开始讨论」主按钮 + 一段说明）；「体验记录 / 收到 / 发出」= `.records-head` + `.records` 表格式行（话题 ｜ 搭档 ｜ 状态 tag ｜ 次数读数 ｜ 时间读数）；详情 = `.detail`（返回 quiet 按钮 → `.detail-head`：标题 + `.meta`（双方名字 + 模型读数 + 「第 N 次 / M」读数）+ 右侧状态 tag → `.stages` 三段阶段条（从 `messages[].stage` 推导：出现过 draft/review/revision 的为 done，勾号）→ `.work` 当前作品块（头行「当前作品」+ 字数读数 + 状态 tag；正文；底部三个下载 `btn`）→ `.turns` 编号发言（序号读数 ｜ 名字 + 阶段 tag ｜ 正文）→ 停止按钮）；「发现分身」= `.people` 网格 `.person` 卡（glyph + 名字 ｜ 简介 ｜ 「邀请交流」btn）；邀请 = `.invite` 行（glyph ｜ 正文两行 ｜ 拒绝 / 接受）。 |
| `page.tsx` 右侧抽屉 | 无对应 | `.glass` 面板，头部：标题 + 右侧 chips（世界：热点与帖子 / 匹配；设置：设置 / 账户）+ 关闭；内容用上面的组件或 iframe。 |
| `plaza/page.tsx`（世界） | 无对应，套组件语言 | 保留 SolarSystem3D、ticker、发帖流程与所有数据逻辑。热点卡 → `glass-card`，卡头「今日热点」等中文 13px 500 + 刷新 quiet 按钮，序号用 `readout`，条目 12px；去掉 `hud-card-float`、发光、`HOT TOPIC` 英文、`textShadow`、彩色 `accent` 描边（统一 `--glass-border`）。话题抽屉 → `glass`。发帖 FAB → 圆形 `btn-primary`。帖子卡 `plaza-card` → `glass-card`。 |
| `match/page.tsx` | 无对应，套组件语言 | Earth3D 保留。匹配卡、房间面板 → `glass-card`；按钮 → `btn` / `btn-primary` / `chip`；`hud-label` → 中文 12px 灰。 |
| `profile` / `settings` / `community` / `agents/[id]` | 无对应，套组件语言 | 粘性玻璃 `.page-head`；分区 → `glass-card p-5`；按钮 → btn 家族；红色动作 → `btn-danger`；数字 → `readout`；`rounded-2xl` 一个不留。 |
| `history/page.tsx` | 无对应，套组件语言 | 顶栏 → `glass`（去掉「C」圆头像，左侧「历史记录」+ 用户名/条数读数，中间搜索 `.field` 风格，右侧「导出」btn）；左筛选栏 → `glass`：快捷筛选四项用 `chip` / `chip-on`（**不用 `bg-primary` 实心块**），区间输入用 `.field` 样式，日期跳转行选中用 `chip-on`；右侧按日分组卡 → `glass-card`（头行日期 + 条数读数）；消息 → 分身 `bubble-ai` + 方块名字标签，我方 `bubble-user`，去掉圆头像，时间 `readout`；「uppercase tracking-wider」小标题全部改为 12px 灰中文。 |

### 2.5 不允许的做法（v1 就是这样被否决的）

- 只替换类名而保留旧结构（例如搭档卡仍是大图标 + 长简介 + 示例话题 + 箭头按钮）。
- 保留任何 `rounded-2xl` / `rounded-3xl` / `bg-primary/5` / `bg-primary/10` / `border-primary/25` / `border-dashed` 之类旧装饰（判据见 §8 J）。
- 标题上方的眉标（如 `AI 分身交流 · 内测` 胶囊）；全大写追踪英文（`uppercase tracking-wider`）；按钮或链接文字里的 `→`、`↔`（改成中文「与」或去掉）。
- 用 `progress` 原生进度条表示回合（用 `.readout` 「第 N 次 / M」）。
- 用 `<select>` 做对话切换或回合数（回合数用 `.field` 数字输入；真人邀请的 2–6 也用数字输入，`min=2 max=6`）。

## 3. M1 令牌与全局样式（`globals.css`）

### 3.1 令牌：整段替换现有 `:root { … }` 与 `.dark { … }`

保留文件开头的三行 `@import`、`@custom-variant dark`、整个 `@theme inline { … }` 块（只改其中两行：`--font-sans: var(--font-sans);` 与 `--font-mono: var(--font-geist-mono);` 改成 `--font-sans: var(--font-sans-stack);` 与 `--font-mono: var(--font-mono-stack);`；`--font-heading` 同 `--font-sans`）。然后把 `:root` 与 `.dark` 两个块**整段换成下面这两段**：

```css
/* 浅色 */
:root {
  --font-sans-stack: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
  --font-mono-stack: ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;

  --background: #F3F5F8;
  --foreground: #141A22;
  --card: #FFFFFF;
  --card-foreground: #141A22;
  --popover: #FFFFFF;
  --popover-foreground: #141A22;
  --primary: #F2A63A;
  --primary-foreground: #2A1A05;
  --secondary: #EEF1F5;
  --secondary-foreground: #141A22;
  --muted: #EEF1F5;
  --muted-foreground: #64707E;
  --accent: rgba(242, 166, 58, 0.18);
  --accent-foreground: #9E6209;
  --destructive: #E04553;
  --border: #DDE3EA;
  --input: #EEF1F5;
  --ring: #9E6209;
  --radius: 0.625rem;
  --sidebar: rgba(255, 255, 255, 0.8);
  --sidebar-foreground: #141A22;
  --sidebar-primary: #F2A63A;
  --sidebar-primary-foreground: #2A1A05;
  --sidebar-accent: rgba(242, 166, 58, 0.18);
  --sidebar-accent-foreground: #9E6209;
  --sidebar-border: #DDE3EA;
  --sidebar-ring: #9E6209;

  /* 强调色的文字版（浅色底上 #F2A63A 对比不够，文字与图标用它） */
  --amber-ink: #9E6209;
  --dim: #8B96A3;
  --rec: #E04553;
  --rec-soft: rgba(224, 69, 83, 0.12);

  /* 磨砂玻璃 */
  --glass: rgba(255, 255, 255, 0.58);
  --glass-strong: rgba(255, 255, 255, 0.8);
  --glass-border: rgba(20, 26, 34, 0.09);
  --glass-hi: rgba(255, 255, 255, 0.85);
  --fill: rgba(20, 26, 34, 0.03);
  --grain: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .05 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
  --shadow: 0 1px 2px rgba(20, 26, 34, 0.06);

  /* 底场光斑 */
  --spot-a: rgba(242, 166, 58, 0.22);
  --spot-b: rgba(90, 140, 225, 0.16);
  --spot-c: rgba(255, 255, 255, 0.6);

  /* 气泡 */
  --bubble-user: rgba(20, 26, 34, 0.03);
  --bubble-user-text: #141A22;
  --bubble-ai: transparent;
  --bubble-ai-text: #141A22;
}

/* 深色（主主题） */
.dark {
  --background: #0E1219;
  --foreground: #E7ECF1;
  --card: #151B24;
  --card-foreground: #E7ECF1;
  --popover: #1B222D;
  --popover-foreground: #E7ECF1;
  --primary: #F2A63A;
  --primary-foreground: #2A1A05;
  --secondary: #1B222D;
  --secondary-foreground: #E7ECF1;
  --muted: #151B24;
  --muted-foreground: #7E8896;
  --accent: rgba(242, 166, 58, 0.14);
  --accent-foreground: #F2A63A;
  --destructive: #FF5A66;
  --border: #232B36;
  --input: #1B222D;
  --ring: #F2A63A;
  --sidebar: rgba(21, 27, 36, 0.76);
  --sidebar-foreground: #E7ECF1;
  --sidebar-primary: #F2A63A;
  --sidebar-primary-foreground: #2A1A05;
  --sidebar-accent: rgba(242, 166, 58, 0.14);
  --sidebar-accent-foreground: #F2A63A;
  --sidebar-border: #232B36;
  --sidebar-ring: #F2A63A;

  --amber-ink: #F2A63A;
  --dim: #586270;
  --rec: #FF5A66;
  --rec-soft: rgba(255, 90, 102, 0.14);

  --glass: rgba(21, 27, 36, 0.6);
  --glass-strong: rgba(21, 27, 36, 0.76);
  --glass-border: rgba(231, 236, 241, 0.09);
  --glass-hi: rgba(255, 255, 255, 0.05);
  --fill: rgba(255, 255, 255, 0.04);
  --grain: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .07 0'/></filter><rect width='100%25' height='100%25' filter='url(#n)'/></svg>");
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.25);

  --spot-a: rgba(242, 166, 58, 0.14);
  --spot-b: rgba(70, 118, 205, 0.18);
  --spot-c: rgba(242, 166, 58, 0.05);

  --bubble-user: rgba(255, 255, 255, 0.04);
  --bubble-user-text: #E7ECF1;
  --bubble-ai: transparent;
  --bubble-ai-text: #E7ECF1;
}
```

注意深色 `--grain` 里 `url(#n)` 与浅色 `url(%23n)` 都可用；两处统一写 `%23` 更稳。

### 3.2 `@layer base` 的 body

改成：

```css
@layer base {
  * { @apply border-border outline-ring/50; }
  body {
    @apply text-foreground;
    font-family: var(--font-sans-stack);
    -webkit-font-smoothing: antialiased;
    background:
      radial-gradient(1100px 700px at 10% -15%, var(--spot-a), transparent 60%),
      radial-gradient(900px 800px at 105% 105%, var(--spot-b), transparent 60%),
      radial-gradient(700px 500px at 55% 45%, var(--spot-c), transparent 65%),
      var(--background);
    background-attachment: fixed;
  }
}
```

### 3.3 删除这些块（整块删，含它们的 `@keyframes`）

- `.dark body::after`（扫描线）与 `@keyframes hud-scan`
- `.bubble-user, .bubble-ai { … clip-path … }`、`.bubble-user {…}`、`.bubble-ai {…}`、`.dark .bubble-ai {…}`、`.bubble-ai::before {…}`（用 §3.4 的新气泡替换）
- `.hud-panel …`、`.hud-panel::before/::after …`、`.hud-corners …`
- `.hud-card-float …`、`.hud-card-float::before …`
- `.dark .liquid-glass …`、`.dark .liquid-glass:active`、`.dark .liquid-glass::before`、`.dark .liquid-glass::after`
- `.hud-pill …`、`.hud-pill:hover`、`.hud-pill-active`
- `.plaza-card …`、`.plaza-card:hover`（用 §3.4 的 `.glass-card` 替换；`.hud-like-burst` / `.hud-like-pop` 两个点赞动画**保留**）
- `.shutter-handle …`、`.shutter-handle:hover`、`.shutter-handle-grip`、`.shutter-handle .chev`
- `.hud-label`、`.hud-pulse` 与 `@keyframes hud-pulse`
- `.hud-btn`、`.hud-btn:hover`、`.hud-btn-active`
- `.hud-avatar-ring`、`.hud-avatar-ring::before`、`@keyframes hud-rotate`
- `.hud-orb-outer/mid/pulse/core`、`@keyframes hud-orb-pulse`、`.hud-orb-recording …`
- `.hud-orb-v2*` 全部、`@keyframes hud-blob-morph`、`@keyframes hud-orb-glow-pulse`、`@keyframes hud-orbit`
- `.hud-ekg path` 与 `@keyframes hud-ekg`
- `.typing-cursor::after`：删掉 `text-shadow`，`color` 改为 `var(--amber-ink)`（`--hud-cyan` 已不存在，留着会让光标失色）
- `.dark .cloud-card { animation-duration … }` 删掉
- 末尾 `@media (prefers-reduced-motion: reduce)` 块把 `.dark *` 三个选择器改成 `*, *::before, *::after`（不再只对深色生效）

**保留不动：** `.glass`（下面会重写它）、`.msg-in-left/right` 与两个 slideIn keyframes、`.wave-bar` 与 `@keyframes wave`、整段滚动条样式、`@keyframes ticker-scroll` 与 `.ticker-track`、`@keyframes topic-drawer-open` 与 `.topic-drawer-in`、`@keyframes blink`、`.hud-like-*`。

### 3.4 新增 / 重写这些工具类（追加在 `@layer base` 之后）

**全部放进 `@layer components { … }`**（包括 `.glass`、`.glass-card`、`.bubble-user`、`.bubble-ai`），这样 JSX 里的 Tailwind 工具类才能覆盖它们（例如 `readout text-[11px]`、`glass-card border-[color:var(--amber-ink)]` 表示选中态）。`@supports` 与 `@media (prefers-reduced-transparency)` 两个块放在 layer 外面。

```css
/* ── 磨砂玻璃：外壳（导航栏、列表、对话头部、输入区、页面标题、抽屉） ── */
.glass {
  background-color: var(--glass-strong);
  background-image: var(--grain);
  -webkit-backdrop-filter: blur(22px) saturate(1.5);
  backdrop-filter: blur(22px) saturate(1.5);
  box-shadow: inset 0 1px 0 var(--glass-hi), var(--shadow);
}
/* ── 磨砂玻璃：卡片（工具卡、生成图、名片、搭档卡、作品块） ── */
.glass-card {
  background-color: var(--glass);
  background-image: var(--grain);
  -webkit-backdrop-filter: blur(14px) saturate(1.5);
  backdrop-filter: blur(14px) saturate(1.5);
  border: 1px solid var(--glass-border);
  border-radius: 10px;
  box-shadow: inset 0 1px 0 var(--glass-hi), var(--shadow);
}
@supports not (backdrop-filter: blur(1px)) {
  .glass, .glass-card { background-color: var(--card); background-image: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .glass, .glass-card { -webkit-backdrop-filter: none; backdrop-filter: none; background-color: var(--card); background-image: none; }
}

/* ── 读数：只给数字、时间、回合数、模型名、ID；永远不给中文标签 ── */
.readout {
  font-family: var(--font-mono-stack);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--muted-foreground);
}
.readout b { font-weight: 400; color: var(--foreground); }

/* ── 分身排法：实心字 + 琥珀描边偏移副本，只给名片与登录页的名字 ── */
.echo {
  position: relative;
  display: inline-block;
  isolation: isolate;
  font-weight: 500;
  letter-spacing: -0.01em;
  line-height: 1.1;
}
.echo::after {
  content: attr(data-text);
  position: absolute;
  left: 0.14em;
  top: 0.12em;
  z-index: -1;
  color: transparent;
  -webkit-text-stroke: 1px var(--amber-ink);
  opacity: 0.6;
  pointer-events: none;
  white-space: nowrap;
}

/* ── 信号线 ── */
.signal { display: block; width: 100%; height: 40px; overflow: visible; }
.signal path { fill: none; stroke: var(--amber-ink); stroke-width: 1.5; vector-effect: non-scaling-stroke; opacity: 0.9; }
.signal circle { fill: var(--amber-ink); }

/* ── 状态点 ── */
.state-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--dim); display: inline-block; }
.state-dot-listening { background: var(--rec); }
.state-dot-speaking { background: var(--primary); }

/* ── 按钮 / 芯片 / 标签（给还没用 components/ui 的地方） ── */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  height: 34px; padding: 0 14px; border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--border) 60%, var(--muted-foreground));
  background: var(--card); color: var(--foreground); font-size: 13px; white-space: nowrap;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.btn:hover { border-color: var(--muted-foreground); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-primary { background: var(--primary); border-color: var(--primary); color: var(--primary-foreground); font-weight: 500; }
.btn-primary:hover { filter: brightness(1.06); border-color: var(--primary); }
.btn-quiet { background: none; border-color: transparent; color: var(--muted-foreground); }
.btn-quiet:hover { color: var(--foreground); background: var(--secondary); border-color: transparent; }
.btn-danger { background: none; border-color: transparent; color: var(--rec); }
.btn-danger:hover { background: var(--rec-soft); border-color: transparent; }
.chip {
  display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 10px;
  border-radius: 6px; border: 1px solid var(--border); color: var(--muted-foreground); font-size: 12px;
}
.chip:hover { color: var(--foreground); }
.chip-on { color: var(--amber-ink); border-color: var(--amber-ink); background: var(--accent); }
.tag {
  display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 4px;
  font-size: 11px; border: 1px solid var(--border); color: var(--muted-foreground);
}
.tag-amber { border-color: transparent; background: var(--accent); color: var(--amber-ink); }
.tag-rec { border-color: transparent; background: var(--rec-soft); color: var(--rec); }

/* ── 消息块：分身无气泡，我方浅层块 ── */
.bubble-user {
  background: var(--bubble-user); color: var(--bubble-user-text);
  border: 1px solid var(--glass-border); border-radius: 10px;
  padding: 9px 14px; line-height: 1.6; box-shadow: var(--shadow);
}
.bubble-ai {
  background: var(--bubble-ai); color: var(--bubble-ai-text);
  padding: 0; line-height: 1.75;
}
```

### 3.5 类名映射表（其他所有文件按这张表替换；找不到对应的就删元素）

| 旧类 | 新写法 |
|---|---|
| `liquid-glass` | `glass` |
| `hud-card-float` | 元素随三栏一起删；若在别处残留则 `glass-card` |
| `hud-panel hud-corners` | 删（对话头部按 §5 重写） |
| `hud-btn` | `btn` |
| `hud-btn-active` | `btn-primary` |
| `hud-pill` / `hud-pill-active` | `chip` / `chip chip-on` |
| `hud-label` 上的英文伪仪表文本（VOICE PORT、DATA STREAM、SYS · CLOCK、SR · 16000Hz、CODEC · OPUS、CH.A1 · 16K、NEW、AUDIO ON/OFF、HANDS·FREE、HOLD · TALK、TRANSMIT、READY、LISTENING、EXPAND、COLLAPSE） | 元素连文本一起删，或按 §5 换成中文 |
| `hud-label` 上的时间戳 / 数字 | `readout` |
| `hud-label` 上的中文标签（抽屉标题「分身」「我的世界」等） | `text-xs font-medium text-muted-foreground` |
| `hud-pulse` | `state-dot` |
| `hud-avatar-ring` | 删外环，头像用 `glyph` 样式：`w-8 h-8 rounded-[6px] bg-secondary grid place-items-center` |
| `hud-ekg`、`shutter-handle*`、`hud-orb-*` | 元素删 |
| `plaza-card` | `glass-card` |
| 所有 `style={HUD_BUTTON_CLIP_8_STYLE}` / `HUD_BUTTON_CLIP_10_STYLE` / `clipPath: "polygon(…)"` | 删 |
| 所有 `textShadow: "0 0 … "` 与 `boxShadow` 里带 `inset 0 1px 0 rgba(255,255,255,0.62)` 之类的液态高光 | 删 |

## 4. M2 外壳

### 4.1 `layout.tsx`

- 删除整个 `<svg width="0" height="0" …><filter id="lg-refract">…</filter></svg>`。
- `viewport.themeColor` 改为 `#0E1219`。其余不动。

### 4.2 `Sidebar.tsx`：收成 5 项，接管草莓余额

- `navItems` 改为 5 项：`{ href: "/", icon: MessageCircle, label: "对话" }`、`{ href: "/agents/me", icon: Bot, label: "分身" }`、`{ href: "/agents", icon: Orbit, label: "广场" }`、`{ href: "/plaza", icon: Globe, label: "世界" }`、`{ href: "/settings", icon: Settings, label: "设置" }`（`Globe` 从 lucide-react 引入；`Sparkles`、`User`、`UsersRound`、`LayoutGrid` 不再需要就删 import）。
- props 删除 `onMatchClick/matchActive`、`onCommunityClick/communityActive`、`onProfileClick/profileActive`；其余 props 名称不变（`onHistoryClick` 保留，但历史按钮按 §5.3 挪到对话列表头部，Sidebar 里**不再渲染**历史按钮；prop 可以保留不用或删掉，二选一，保持 tsc 干净）。
- 宽度 `w-16` 改 `w-14`，按钮 `w-12 h-12` 改 `w-12 h-12` 不变，标签 `text-[9px]` 改 `text-[10px]`。类名 `glass … bg-sidebar` 保留（`glass` 已重写为磨砂玻璃）。
- active 态：去掉 `bg-accent`，只用 `text-[color:var(--amber-ink)]`；非 active 用 `text-muted-foreground hover:text-foreground hover:bg-secondary`。
- Logo：把 `bg-primary` 方块换成 24px 的「双圆」SVG（两个 r=5.5 的圆，圆心 (9,12) 与 (15,12)，stroke 1.5，`color: var(--amber-ink)`，fill none）。
- 底部新增草莓余额：把 `TopBar.tsx` 里 `balance` 的 state、两个 `useEffect`（时钟的那个不要，只要余额的）与事件监听**原样搬过来**，渲染为：
  ```tsx
  <div className="flex flex-col items-center gap-0.5 text-[11px] text-muted-foreground" title="草莓余额，每条消息消耗 10 颗">
    <span aria-hidden="true">🍓</span>
    <b className="readout" style={{ color: "var(--foreground)" }}>{balance === null ? "…" : balance}</b>
  </div>
  ```
  余额低于 30 用 `color: var(--rec)`，低于 100 用 `color: var(--amber-ink)`（沿用 TopBar 的阈值）。
- 主题切换按钮保留在最底部。

### 4.3 删除 `TopBar.tsx`，并从 9 处移除 `<TopBar />` 与其 import

文件：`app/page.tsx`、`app/settings/page.tsx`、`app/match/page.tsx`、`app/agents/[id]/page.tsx`、`app/plaza/page.tsx`、`app/profile/page.tsx`、`app/community/page.tsx`、`components/MyAgentWorkspace.tsx`、`components/AgentExchangeWorkspace.tsx`。删完 `grep -rn "TopBar" frontend/app frontend/components` 必须为 0 行。

### 4.4 `page.tsx` 的抽屉与侧栏接线（B 负责）

- `DrawerName` 改为 `"agent" | "exchange" | "plaza" | "settings" | null`；删除 `matchOpen`、`communityOpen`、`profileOpen` 三个派生量与对应 Sidebar props 传递。
- 新增 `const [worldTab, setWorldTab] = useState<"plaza" | "match">("plaza");` 与 `const [settingsTab, setSettingsTab] = useState<"settings" | "profile">("settings");`
- 「我的世界」抽屉：标题改「世界」，头部右侧放两个 `chip`：「热点与帖子」（`worldTab === "plaza"` 时 `chip-on`）与「匹配」；iframe `src` 改为 `worldTab === "plaza" ? "/plaza?embed=1" : "/match?embed=1"`。删除原来独立的「匹配」抽屉整个 `<div>`。
- `["community","profile","settings"]` 那段 map：改成只渲染「设置」一个抽屉，标题「设置」，头部右侧两个 `chip`：「设置」与「账户」；iframe `src` 为 `settingsTab === "settings" ? "/settings?embed=1" : "/profile?embed=1"`。社群抽屉删除（`app/community/page.tsx` 文件保留，只是侧栏不再有入口）。
- 所有抽屉宽度表达式里的 `64px`（旧侧栏宽）改为 `56px`：`min(960px, calc(100vw - 64px))` → `min(960px, calc(100vw - 56px))`，`calc((100vw - 64px) * 2 / 3)` → `calc((100vw - 56px) * 2 / 3)`；改完 `grep -c "100vw - 64px" app/page.tsx` 必须为 0（改前 5）。
- 所有抽屉 `className` 里 `liquid-glass` → `glass`；`style` 里的 `boxShadow` 改成打开时 `"-12px 0 32px rgba(0,0,0,0.28)"`、关闭时 `"none"`；`borderLeft` 统一 `"1px solid var(--glass-border)"`。
- 抽屉头部 `style={DRAWER_HEADER_STYLE}` 改为 `className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}`；标题 `hud-label` → `text-xs font-medium text-muted-foreground`；删除 `DRAWER_HEADER_STYLE`、`DRAWER_LABEL_STYLE` 常量。
- 历史抽屉（`showHistory`）底部那颗「查看完整历史记录」按钮删除（列表页脚的「完整历史」已承担），其余保留。
- 历史抽屉（`showHistory`）：`liquid-glass` → `glass`，`style={HISTORY_DRAWER_STYLE}` 改为 `style={{ borderRight: "1px solid var(--glass-border)", boxShadow: "8px 0 32px rgba(0,0,0,0.28)" }}`，`left-16` 改 `left-14`；删除 `HISTORY_DRAWER_STYLE` 常量。背板 `left-16` 也改 `left-14`。
- 「抽屉外部点击关闭」背板 `left-16` → `left-14`。

## 5. M3 对话页（`page.tsx` 主体 + `Signal.tsx` + `ConversationPicker.tsx` + `ChatBubble.tsx`）

### 5.1 `Signal.tsx`（新建）

```tsx
"use client";
import { useEffect, useRef } from "react";
export type SignalMode = "idle" | "listening" | "speaking";
export default function Signal({ mode, className }: { mode: SignalMode; className?: string }) { … }
```

行为（照原型 §「信号线」的 JS 算法翻译成 React，不许简化成 CSS 动画）：
- 渲染 `<svg className={cn("signal", className)} viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden="true"><path d="M0 20 L1000 20" /><circle cx="-10" cy="20" r="3" /></svg>`。
- `useEffect` 里用 `requestAnimationFrame` 循环；每帧：`target = mode==="idle"?0 : mode==="listening"?0.5 : 0.9`；`level += (target-level)*min(1, dt*6)`；`t += dt`；用 140 个点生成路径：`x = i/139*1000`，`env = sin(π·i/139)`，`w = 8·sin(x·0.045 + t·9 + phase) + 5·sin(x·0.012 − t·5.5) + 3·sin(x·0.09 + t·14)`，`y = 20 + env·level·w`；`d = "M x0 y0 L x1 y1 …"`（保留 1 位小数）。
- 待命且 `level < 0.02` 时亮点沿线跑：`cx = ((t·140 + phase·100) mod 1300) − 150`，越界时 `opacity=0`；其他模式 `opacity=0`。
- `phase` 用 `useRef(Math.random()*20)`。`mode` 用 ref 读，避免每次切换重建循环。
- `matchMedia("(prefers-reduced-motion: reduce)")` 为真时不跑循环，路径固定平线、亮点隐藏。卸载时 `cancelAnimationFrame`。

### 5.2 `ConversationPicker.tsx`：从下拉改成列表（props 不变）

组件名、导出、props 签名**完全不变**，内部渲染改为：

```
<aside class="glass flex h-full w-[260px] shrink-0 flex-col border-r" style={{borderColor:"var(--glass-border)"}} aria-label="对话列表">
  <div class="flex h-16 shrink-0 items-center justify-between border-b pl-5 pr-3" style={{borderColor:"var(--glass-border)"}}>
    <h2 class="text-sm font-medium">对话</h2>
    <div class="flex items-center gap-1">
      {onHistory && <button class="btn btn-quiet w-[34px] px-0" title="当前对话记录" aria-label="当前对话记录"><Clock size={16}/></button>}
      <button class="btn btn-quiet w-[34px] px-0" title="新对话" aria-label="新对话" disabled={disabled || !canCreate}><Plus size={16}/></button>
    </div>
  </div>
  <ul class="flex-1 overflow-y-auto p-2" role="listbox" aria-label="对话">
    {conversations.map(c => (
      <li role="option" aria-selected={c.id===selectedId}
          class="group flex cursor-pointer items-baseline gap-2 rounded-[6px] px-3 py-2 text-[13px] text-muted-foreground hover:bg-secondary hover:text-foreground aria-selected:bg-secondary aria-selected:text-foreground">
        <button type="button" class="min-w-0 flex-1 truncate text-left" onClick=… disabled={disabled}>{c.title || "新对话"}</button>
        <span class="readout text-[11px]">{formatRelative(c.updated_at)}</span>
        <button type="button" aria-label="删除对话" class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-[color:var(--rec)]" onClick=…><Trash2 size={13}/></button>
      </li>))}
  </ul>
  <div class="flex items-center justify-between border-t px-5 py-3 text-xs text-muted-foreground" style={{borderColor:"var(--glass-border)"}}>
    <span>对话仅你可见</span>
    <button type="button" onClick={onFullHistory}>完整历史</button>
  </div>
</aside>
```

- 新增两个可选 props：`onHistory?: () => void`（打开 `showHistory` 抽屉）与 `onFullHistory?: () => void`（`window.open("/history?user=…")`，把原历史抽屉底部那段逻辑搬过来）。
- `formatRelative(iso)`：后端 `updated_at` 是 `"YYYY-MM-DD HH:MM:SS"` 的 **UTC、无时区标记**，必须先规范化：`const date = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(" ", "T") + "Z");`（与 `app/history/page.tsx` 的 `parseUtcTimestamp` 一致）。然后：同一天显示 `HH:mm`；昨天显示「昨天」；7 天内显示星期（周一…周日）；否则 `MM/DD`。写在组件文件内，不改 `lib/`。
- 三种状态保留原文案：`locked` 时列表下方一行「分身回复或语音进行中，结束后可以切换对话。」；空列表「还没有对话。点「新对话」，开始和自己的分身交流。」；`error` 时红字 + 「重试加载」按钮（`btn btn-quiet`）。`loading` 时列表区一行「正在加载对话…」。

### 5.3 `page.tsx` 对话主体：三栏改两栏

**目标结构**（`<Sidebar …/>` 之后、抽屉之前）：

```
<div class="flex flex-1 min-w-0 min-h-0">
  <ConversationPicker … onHistory={() => setShowHistory(v => !v)} onFullHistory={…} />
  <div class="relative flex-1 min-w-0">                       ← 对话区，position relative
    <header class="glass absolute inset-x-0 top-0 z-[2] grid h-16 grid-cols-[auto_minmax(120px,1fr)_auto] items-center gap-6 border-b px-6" style={{borderColor:"var(--glass-border)"}}>
      <div class="flex items-center gap-3">
        <span class="grid h-8 w-8 place-items-center rounded-[6px] bg-secondary text-base" aria-hidden>{agent?.avatar_emoji || "✨"}</span>
        <div><div class="text-sm font-medium">{agent?.display_name || "我的分身"}</div>
             <div class="flex gap-2 text-xs text-muted-foreground"><span>AI 分身</span><span>仅你可见</span></div></div>
      </div>
      <Signal mode={signalMode} />
      <div class="flex items-center gap-2">
        <span class="flex items-center gap-2 text-xs text-muted-foreground"><span class={cn("state-dot", …)}/>{状态词}</span>
        <button class={cn("chip", voiceOn && "chip-on")} onClick={…}>{voiceOn ? <Volume2 size={13}/> : <VolumeX size={13}/>}朗读</button>
        <button class={cn("chip", handsFree && "chip-on")} …>免提</button>
      </div>
    </header>
    <ChatScrollArea …>  ← 需要占满：给 ChatScrollArea 外层加 class "absolute inset-0 pt-16 pb-[172px]"（若 ChatScrollArea 自身是 flex 容器且不接受 className，就用一个 <div class="absolute inset-0 flex flex-col pt-16 pb-[172px]"> 包住它；ChatScrollArea.tsx 不动）
    <footer class="glass absolute inset-x-0 bottom-0 z-[2] border-t px-8 pb-4 pt-3" style={{borderColor:"var(--glass-border)"}}>
      <div class="mx-auto max-w-[760px]">  ← 现有 data-chat-composer 那一整段 JSX 原样搬进来，只改样式：
        - 外层 bg-secondary rounded-2xl → "rounded-[10px] border px-3.5 py-2.5" style={{background:"var(--fill)", borderColor:"var(--glass-border)"}}
        - 参考图/生成图片那行小按钮：rounded-full border … → "chip"；激活态加 chip-on
        - 发送按钮：w-7 h-7 rounded-full → "grid h-8 w-8 place-items-center rounded-[6px] bg-primary text-primary-foreground disabled:bg-secondary disabled:text-[color:var(--dim)]"
        - 在麦克风按钮旁**新增**按住说话按钮（把左栏那个 onPointerDown/onPointerUp 的按钮连 handler 原样搬来，disabled 条件原样），显示 <Mic/> + 「按住说话」，recording 时 "text-[color:var(--rec)] bg-[color:var(--rec-soft)]"
        - 底部提示行：左「Enter 发送，Shift + Enter 换行」右「每条消息消耗 <b class="readout">10</b> 颗草莓」；voiceText 非空时在提示行上方显示一行 text-xs（原样文本）
      </div>
    </footer>
  </div>
</div>
```

- `signalMode`：`recording || inlineRecording ? "listening" : isLoading ? "speaking" : "idle"`。状态词：待命 / 正在听 / 正在说；状态点类：`state-dot-listening` / `state-dot-speaking`。
- 「新建聊天」按钮：从头部删除（列表头部已有 `+`）。
- 头部 `HUD_PRIMARY_TITLE_STYLE`、`CHAT_AVATAR_STYLE`、`CHAT_HEADER_STYLE`、`HUD_PLUS_STYLE`、`HUD_ACTIVE_LABEL_STYLE`、`VOICE_TEXT_STYLE`、`CHAT_SLOT_STYLE`、`DATA_STREAM_HEADER_STYLE`、`HUD_PULSE_DOT_STYLE`、`HALF_OPACITY_STYLE`、`CARD_*_STYLE`、`CARD_MODAL_*_STYLE`、`HUD_BUTTON_CLIP_*_STYLE` 这些常量：随使用处一起删，删完不得残留未使用常量。

**删除（整段 JSX + 对应 state/handler/import，删干净）：**
- `<StarField />` 与 import。
- 左栏「VOICE PORT」整个 `<div className="liquid-glass w-1/4 …">`（能量球 `<HudOrb>`、`recordingBars` 波形、`hud-ekg`、底部元数据）。`recordingBars` 的 `useMemo` 一并删。`HudOrb` import 删。**但** `recording`、`voiceText`、`asrSessionRef` 与所有语音 effect 保留（按住说话按钮搬到输入区后仍在用）。
- 中栏卷帘门：`chatCollapsed` state、`shutter-handle` 那段、`data-chat-panel` 外层的 `transform/transition` 样式；`ChatScrollArea` 与 composer 直接放进新结构。
- 右栏「DATA STREAM」整个 `<div className="liquid-glass w-1/4 hud-card-float …">`，以及 `activeCards`/`setActiveCards`（含第 924、1078、1397 行附近三处调用）、`hoveredCard`、`enlargedCard` 与其 `useEffect`、`handleDismissCard`、`cardDialogRef`、末尾整个「卡片放大层」`{enlargedCard && (…)}`、`getWeatherTheme`/`weatherCN` 若只被这些地方使用则一并删；`<AmbientHUD>` 与 import 删；`NewsCardContent` 若在 page.tsx 只被放大层使用，则 page.tsx 里删 import（组件文件保留，别处仍可能用）。
- `ConversationPicker` 原来放在头部下方的调用位置删除（它现在是左栏）。

**保留：** `MiniCloudCard`（`liquid-glass` → `glass-card`，去掉 `bg-card/90 backdrop-blur-md border border-border/60 rounded-2xl shadow-xl`）、匹配弹窗逻辑、免提/朗读/TTS/ASR 全部逻辑、参考图与生成图逻辑、`handleNewChat`、`handleDeleteConversation`、`handleSelectConversation`、账号切换清理。

### 5.4 `ChatBubble.tsx`

- 头像：删除渐变 `style`，改 `className="grid h-7 w-7 shrink-0 place-items-center rounded-[6px] bg-secondary text-sm"`。
- 分身消息：在气泡上方加一行说话者标签（仅 `!isUser`）：`<div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="inline-block h-1.5 w-1.5" style={{background:"var(--amber-ink)"}}/>{agentName}</div>`；文字气泡类 `bubble-ai` 保留（CSS 已改成无底）。`max-w-prose` 改 `max-w-[640px]`。
- 我方消息：`bubble-user` 保留，外层 `max-w` 520px。
- 天气卡：删除 `style={{ background: "linear-gradient(135deg, #1a1a2e …)", color: "#e0e0e0" }}` 与所有 `text-white/xx`，改成 `glass-card w-[320px] max-w-full overflow-hidden`，内部结构照原型 `.tool.weather`：头行「天气 | 城市」（`text-xs`，下边框 `var(--glass-border)`）；主行温度 `readout` 32px（`style={{fontSize:32, color:"var(--foreground)"}}`）+ 天气文字 + 「体感 xx° 湿度 xx%」（数字 `readout`）；预报改成三列网格（最多取前 3 天），每列「周几」+ `readout` 的 `low° high°`。
- 网页卡：`rounded-2xl border border-border/60 bg-card/80 shadow-sm` → `glass-card`；`Globe` 颜色用 `var(--amber-ink)`。
- 生成状态行 `bubble-ai …` → `text-sm text-muted-foreground`。
- 「帮我读」按钮：`hud-btn` + `clipPath` + `hud-label` → `btn btn-quiet h-7 px-2.5 text-xs`；「不用」同样 `btn btn-quiet h-7 px-2.5 text-xs`。
- 「重新生成」按钮：`rounded-full … text-primary hover:bg-primary/10` → `btn h-7 px-2.5 text-xs`。
- Meta 行时间 `hud-label text-[9px] opacity-70` → `readout text-[11px]`。
- 用户上传图 `rounded-2xl` → `rounded-[10px]`。

### 5.5 `GeneratedImage.tsx` / `NewsCardContent.tsx`

只做类名替换：`rounded-2xl`/`rounded-xl` → `rounded-[10px]`；描边用 `border` + `style={{borderColor:"var(--glass-border)"}}`；按钮 `hud-btn`/胶囊按钮 → `btn btn-quiet h-7 px-2.5 text-xs`；`hud-label` → `readout`。不改逻辑。

## 6. M4 分身、广场与其余页面

### 6.1 `AgentIdentityCard.tsx`

```
<section class="glass-card flex flex-col gap-[18px] p-[22px] pb-[18px]" aria-label=…>
  <div class="flex items-center justify-between"><span class="tag tag-amber">AI 分身</span><span class="readout">{preview ? "名片预览" : "分身名片"}</span></div>
  <div class="py-1 text-[40px]"><span class="echo" data-text={name}>{name}</span></div>   ← name = agent.display_name || "我的分身"；超过 12 字时不用 echo，改 text-[28px] font-medium break-words
  <p class="text-[13px] leading-[1.7] whitespace-pre-wrap break-words">{agent.bio || "这个分身还没有填写介绍。"}</p>
  <div class="flex items-center gap-2.5 border-t pt-3.5 text-xs text-muted-foreground" style={{borderColor:"var(--glass-border)"}}>
    <span class="grid h-8 w-8 place-items-center rounded-[6px] bg-secondary text-base" aria-hidden>{agent.avatar_emoji || "✨"}</span>
    <span>由用户创建的人工智能分身</span>
  </div>
  {preview && <p class="text-xs text-muted-foreground">…原文案…</p>}
</section>
```

### 6.2 `MyAgentWorkspace.tsx`（对照原型 `[data-screen="agent"]`）

- 删 `<TopBar />`。
- 头部：`<header className="glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7" style={{borderColor:"var(--glass-border)"}}><div className="flex max-w-[976px] items-end justify-between gap-4"><div><h1 className="text-xl font-medium tracking-[-0.01em]">分身</h1><p className="mt-1 text-[13px] text-muted-foreground">设置身份、介绍和交流方式。名片默认仅自己可见。</p></div></div></header>`；非嵌入模式的「回到对话」链接放在 h1 上方一行，12px 灰。
- 内容容器 `mx-auto max-w-[1040px] px-8 py-6`；网格 `grid gap-10 lg:grid-cols-[minmax(0,1fr)_340px] items-start`。
- 表单：`fieldClass` 改为 `w-full rounded-[6px] border border-[color:var(--border)] bg-card px-3 py-[9px] text-sm outline-none focus:border-[color:var(--amber-ink)] disabled:opacity-50`；标签 `text-xs font-medium` 行内右侧 `em` 用 `font-normal text-muted-foreground`；计数用 `readout`（数字进 `<b>`）。
- 头像符号 + 名称一行：`grid grid-cols-[96px_minmax(0,1fr)] gap-4`，头像输入框 `text-center text-xl`。
- 公开名片：`label` 容器 `glass-card flex items-start justify-between gap-4 p-4 cursor-pointer`；左侧 `b` 14px 500 + `p` 12px 灰 1.6；右侧 checkbox 保留（`mt-0.5 h-4 w-4 accent-[color:var(--primary)]`）。
- 保存：`btn btn-primary`；旁边「有未保存的修改」12px 灰。
- 右栏：`AgentIdentityCard` → `.note`（`flex gap-2.5 text-xs text-muted-foreground leading-[1.6]`，ShieldCheck 用 `var(--amber-ink)`）→ `AgentMemoryPanel`。

### 6.3 `AgentMemoryPanel.tsx`（对照原型 `.memory`）

- 容器 `border-t pt-[18px] flex flex-col gap-3`（边框 `var(--glass-border)`），不再是卡片。
- 头行：`h3` 14px 500「私有记忆」；右侧 `readout`：有 revision 字段则「修订 <b>N</b>」，没有则「仅自己可见」。
- 说明文字 12px 灰；条目列表 `li` 13px 灰、`py-1.5 border-b`；空态一句话。
- 按钮：「查看全部 / 刷新」→ `btn btn-quiet`；「清空记忆与个人画像」→ `btn btn-danger`；二次确认文案与 handler 原样。

### 6.4 `AgentExchangeWorkspace.tsx`（对照原型 `[data-screen="plaza"]`，这是 v1 偏差最大的文件）

**外壳**
- 删 `<TopBar />`。删除 `buttonClass` / `primaryButtonClass` 两个字符串常量，改用 `btn` / `btn btn-primary` / `btn btn-quiet` / `btn btn-danger`。`fieldClass` 同 §6.2。
- 头部同 §6.2 的粘性玻璃 `header`：h1「广场」，一句话「让分身和官方搭档讨论一个话题，一个账号就能开始。也可以邀请其他用户的公开分身。」，右侧「刷新」`btn btn-quiet`（RefreshCw 图标）。**删除**眉标 `AI 分身交流 · 内测` 整个元素。
- 「我的分身 · Chloe」那块 `bg-primary/5` 提示区**删除**；把「管理我的分身」链接移到 `.page-head` 一句话的末尾（`text-[color:var(--amber-ink)] underline underline-offset-4`）；关于公开名片的提示文案移到「发现分身」标签页顶部一行 12px 灰。
- 标签：`<nav role="tablist" className="mb-6 flex gap-1 border-b" style={{borderColor:"var(--border)"}}>`，每个 `<button role="tab" aria-selected className="-mb-px flex h-9 items-center gap-1.5 border-b-2 px-3 text-[13px] …">`，选中 `border-[color:var(--amber-ink)] text-foreground`，未选中 `border-transparent text-muted-foreground hover:text-foreground`；「收到的邀请」后面待处理数量用 `<span className="readout text-[11px]" style={{color:"var(--amber-ink)"}}>{pendingCount}</span>`（为 0 不显示）。

**单人体验（tab=official）**
- 一句说明 12px 灰（原文案缩到一行：「以下均为平台官方 AI，无真人用户。分身先写完整初稿，官方搭档审稿，再按意见修订；审稿通过提前结束，可随时停止。」）。
- `.partners`：`grid grid-cols-1 gap-3 md:grid-cols-3 mb-6`，每张 `<button type="button" role="radio" aria-checked className="glass-card flex flex-col gap-2.5 p-4 text-left" data-official-agent={card.id}>`：
  - 顶行 `flex items-center justify-between`：`h3` 14px 500 `{card.display_name}` + `<span className="tag">官方 AI</span>`
  - `p` 12px 灰 1.6 `{card.bio}`（`line-clamp-3`）
  - `<span className="readout">{modelLabel}</span>`
  - 选中态：`border-[color:var(--amber-ink)]`。点击 = `setTarget(card)`。
  - **不渲染** emoji 大图标、示例话题、「选择 xx」按钮。
- 选中搭档后，`ExchangeStartForm` **不再替换整页**，而是渲染在 `.partners` 下方（`target` 存在且 `official` 时）。表单改为 `grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px] items-start`：
  - 左：`.field` 话题 textarea（`min-h-[150px] resize-y`，保留 `maxLength/required/autoFocus`）+ `small`：`<b class="readout">{topic.length}</b> / <b class="readout">{topicLimit}</b>，人物、背景、风格和时长都可以写进来`；示例话题按钮 → `btn btn-quiet h-7 px-2.5 text-xs`「使用示例话题」（有才显示）。
  - 右：`.field` 回复次数 `input type=number`（`readout` 字体）+ `small`「双方合计，2–99。审稿通过会提前结束。」→ `btn btn-primary w-full h-10`「开始讨论」→ `p` 12px 灰：「流程是主创初稿、官方审稿、主创修订。只用分身的名字、简介和这次话题，不读取性格设定、私聊或私有记忆。记录仅你可见，内测期间不扣草莓。」
  - 「返回」quiet 按钮放在表单左上。提交逻辑、校验、错误提示原样。
- 真人邀请（`target.kind !== "official"`）沿用同一表单布局：话题 300 字，回复次数 `input type=number min=2 max=6`（替换 `<select>`），按钮「发送邀请」。

**记录列表（experiences / received / sent）**
- 顶部一句 12px 灰说明保留原文案。
- `.records-head`：`grid grid-cols-[minmax(0,1fr)_150px_120px_60px_60px] gap-4 px-2 pb-2 text-[11px]` 颜色 `var(--dim)`：话题 ｜ 搭档 ｜ 状态 ｜ 次数（右对齐）｜ 时间（右对齐）。
- 每行 `<button type="button" className="grid w-full grid-cols-[minmax(0,1fr)_150px_120px_60px_60px] items-center gap-4 border-b px-2 py-3 text-left text-[13px] hover:bg-card" data-exchange-id>`：话题 `truncate` ｜ 搭档名 12px 灰 ｜ `StatusBadge`（改为 `tag`：进行中/待处理 `tag-amber`，失败 `tag-rec`，其余 `tag`）｜ `readout` 次数 ｜ `readout` 日期（`formatDate` 改成只显示 `MM/DD`，今天显示 `HH:mm`）。
- 空态 / 加载态：一行 13px 灰文字，不要虚线框（`EmptyState` 改为 `p.text-[13px].text-muted-foreground.py-6`）。

**详情（`ExchangeConversation`）**
- 外层 `flex flex-col gap-6`。
- 返回：`btn btn-quiet` 左对齐（ArrowLeft + 「体验记录 / 收到的邀请 / 发出的邀请」）。
- `.detail-head`：左 `h2` 18px 500 `{exchange.topic 前 40 字}`（完整话题用 `ExchangeTopic` 渲染在 `.work` 之上，超长折叠逻辑保留）；`.meta` 行 `flex gap-3.5 text-xs text-muted-foreground items-center`：`{mine.display_name} <span class="readout">{mine.model_label||mine.model}</span>` ｜ `{other.display_name} <span class="readout">{…model}</span>` ｜ `<span class="readout">第 <b>{turn_count}</b> 次 / {max_turns}</span>`；右侧 `StatusBadge`（tag）。**删除** `<progress>` 与「已用 N 次 · 上限 M 次」文字。
- `.stages`（仅 `workflow` 为真时）：`<div className="inline-flex overflow-hidden rounded-[6px] border" style={{borderColor:"var(--glass-border)"}}>` 内三个 `<span className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs">`：主创初稿 / 官方审稿 / 主创修订；`detail.messages.some(m => m.stage === key)` 为真 → `text-foreground` + `<Check size={14}/>`（勾用 `var(--amber-ink)`），否则 `text-muted-foreground`；相邻 `border-l`。
- 待处理（pending）说明与「接受并开始交流 / 拒绝邀请 / 取消这次邀请」按钮保留，按钮改 btn 家族。
- `.work`（`ExchangeArtifact`）：`glass-card` 容器；头行 `flex items-center justify-between border-b px-4 py-3`：`b`「当前作品」+ 右侧 `<span class="readout"><b>{字数}</b> 字</span>` + `StatusBadge` 风格的 tag（`approved` → `tag tag-amber`「审稿通过，待你验收」；`needs_revision` → `tag`「待修订」；否则 `tag`「草稿」）；`completionLabel` 文案作为一行 12px 灰放头行下；正文区保留 `max-h-[36rem] overflow-y-auto` 的稿件（`p-4 text-[13px] leading-[1.8]`）；底部 `flex gap-1.5 border-t p-3`：三个下载按钮 `btn`（Download 图标 + 「作品 Markdown / README.md / 完整讨论」），即把 `ExchangeDocuments` 的三个按钮**搬进** `.work` 底部（下载逻辑、状态、错误提示原样；`ExchangeDocuments` 的两段说明文字缩成一行 12px 灰放按钮上方）。非 workflow 的交流：`ExchangeDocuments` 单独作为一个 `glass-card`，同样只保留一行说明 + 按钮。
- `.turns`：`flex flex-col gap-[18px]`；每条 `grid grid-cols-[28px_minmax(0,1fr)] gap-3`：左 `readout` 序号；右：`div.turn-who`（12px 灰：名字 + `tag` 阶段标签（有 stage 才显示）+ 「你的 AI 分身 / 平台官方 AI / 对方 AI 分身」）+ `div.turn-body`（13px 1.75）。**删除**每条消息的 `rounded-2xl border bg-primary/5` 卡片壳。
- 运行中的粘性操作条：改为 `glass sticky top-0 z-[2] -mx-8 px-8 py-2 flex items-center justify-between text-xs text-muted-foreground`，右侧「查看最新回复」`btn btn-quiet` + 「停止交流」`btn`。结束后底部一行：`btn` 禁用「停止交流」+ 12px 灰「已结束，记录仅你可见」。
- 总结区 `exchange.summary`：`glass-card p-4`，`h3` 14px 500，正文 13px 1.75。

**发现分身（gallery）**
- 顶部一行 12px 灰：「邀请需要双方都已公开名片。交流只使用公开名片和这次话题。」+（未公开时）「管理我的分身」链接。
- `.people`：`grid gap-3 md:grid-cols-3`；`.person`：`glass-card flex flex-col gap-2.5 p-4`：顶行 glyph（`grid h-8 w-8 place-items-center rounded-[6px] bg-secondary`）+ `h3` 14px 500；`p` 12px 灰 1.6 简介；`btn`「邀请交流」（disabled 条件原样）。

**收到的邀请行（received 里 pending 的记录）**
- 仍走 `.records` 列表；点开详情后接受/拒绝。不额外做 `.invite` 行（原型的 `.invite` 只是示意）。

**其余**
- `Participant` 组件：`flex items-center gap-2.5`：glyph 32px + `p` 14px 500 名字 + `p` 12px 灰 label + `readout` 模型名。不再有 `rounded-xl border-primary/20 bg-primary/10` 大方块。
- `ErrorNotice` → `glass-card p-3 text-[13px]` 红字 + 「重新加载」`btn btn-quiet h-7`。
- 所有 `rounded-2xl`、`rounded-xl`、`bg-primary/5`、`bg-primary/10`、`border-primary/25`、`border-dashed` 归零。

### 6.5 `agents/[id]/page.tsx`

粘性玻璃 `page-head`（标题「分身名片」）+ 内容区 `max-w-[560px]` 放 `AgentIdentityCard`；错误区 `glass-card p-6` + `btn btn-quiet`「重新加载」。

### 6.6 `plaza/page.tsx`（世界）、`match/page.tsx`、`profile`、`settings`、`community`

- 全部删 `<TopBar />`。
- 按 §2.4 对照表逐项改；按 §3.5 表替换旧类；`SolarSystem3D`、`Earth3D`、`cloud-card`、`ticker-track`、`hud-like-*`、`topic-drawer-in` 保留。
- `plaza` 热点卡：容器 `glass-card w-[220px] px-3 py-2 pointer-events-auto`（`style` 只保留定位，删 `borderColor: accent`）；卡头 `flex items-center gap-1.5`：图标 12px 用 `var(--amber-ink)`、标题 `text-[13px] font-medium`、刷新 quiet 按钮；条目 `li` 12px：序号 `readout` + 标题；页脚「获取于 HH:mm」`readout`。话题抽屉容器 `glass` + 头行标题 13px 500，删 `HOT TOPIC`。
- `settings` / `profile`：每个分区 `glass-card p-5`，分区标题 14px 500 + 图标 `var(--amber-ink)`；身份切换 chips 用 `chip` / `chip-on`；危险动作 `btn btn-danger`；删除账号输入框 `.field` 样式。
- `community`：占位页保留文案，容器 `glass-card p-8` 居中一句话。

### 6.7 `history/page.tsx`

按 §2.4 对照表那一行逐项做。补充判据：`grep -c "bg-primary text-primary-foreground" app/history/page.tsx` 改后为 0（改前 3）；`grep -c "uppercase tracking-wider" app/history/page.tsx` 改后为 0；`grep -c "bubble-user" app/history/page.tsx` ≥ 1。搜索高亮 `mark` 改为 `bg-[color:var(--accent)] text-foreground rounded-[3px] px-0.5`。

## 7. M5 登录页（`login/page.tsx`）

保留三步（invite / phone / otp）、所有 handler、错误提示与 `NODE_ENV !== "production"` 的开发测试入口。结构改为：

```
<div class="flex min-h-screen items-center justify-center px-6">
  <div class="flex w-[360px] flex-col gap-8">
    <div class="flex flex-col gap-3">
      <双圆 SVG 28px, color var(--amber-ink)>
      <div class="echo text-[44px]" data-text="Chloe">Chloe</div>
      <p class="text-[15px] text-muted-foreground">每个人自己的分身。</p>
      <Signal mode="idle" className="mt-2" />
    </div>
    <div class="glass rounded-[10px] border p-[22px]" style={{borderColor:"var(--glass-border)"}}>
      …三步表单原样，输入框类：w-full rounded-[6px] border bg-card px-3 py-[9px] text-sm outline-none focus:border-[color:var(--amber-ink)]，邀请码/验证码保持 font-mono tracking；主按钮 btn btn-primary w-full h-10；次按钮 btn btn-quiet…
      <p class="text-xs leading-relaxed text-muted-foreground">内测阶段凭邀请码进入。登录即同意用户协议，新用户赠送 <b class="readout">200</b> 颗草莓。</p>
    </div>
    …开发测试入口原样（样式换 btn btn-quiet）…
  </div>
</div>
```

删掉 🍓 大 emoji 与「你的私人 AI 助理」。`placeholder` 不得继承字距：给邀请码输入框加 `placeholder:tracking-normal placeholder:font-sans`。

## 8. 验收标准（全部命令在 `frontend/` 目录执行；先跑对照再跑判定）

每条「对照」是为了证明命令真的扫到了东西；对照不符说明你的扫描面错了，先修命令再判定。

```bash
# A. 门禁
npm run lint            # 期望：0 errors；warnings ≤ 35（基线 35；不得新增）
npx tsc --noEmit        # 期望：无输出，退出码 0
npm run build           # 期望：Compiled successfully，退出码 0（只在最后跑一次；若沙箱内 Turbopack 报端口/EPERM，改跑 npx next build --webpack 并在报告注明）

# B. 旧类彻底清除（对照：改前 grep -rE "hud-|liquid-glass" app components --include='*.tsx' | wc -l 为 80）
grep -rnE "hud-[a-z0-9-]+|liquid-glass|lg-refract|hud-card-float|shutter-handle|plaza-card" app components --include='*.tsx' | grep -v "hud-like" | wc -l   # 期望 0
grep -nE "hud-(panel|corners|card-float|pill|label|pulse|btn|avatar-ring|orb|ekg|cyan)|liquid-glass|shutter-handle|hud-scan|body::after" app/globals.css | wc -l   # 期望 0

# C. 组件退场（对照：改前 grep -rlE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l 为 15）
grep -rnE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l   # 期望 0
ls components/TopBar.tsx components/AmbientHUD.tsx components/HudOrb.tsx components/HudOrb3D.tsx components/StarField.tsx 2>&1 | grep -c "No such file"   # 期望 5
test -f components/Signal.tsx && echo ok   # 期望 ok

# D. 英文伪仪表标签与眉标清除（对照：改前 D1 为 5，D2 为 7，D3 为 1）
grep -rnE "VOICE PORT|DATA STREAM|SYS · CLOCK|SR · 16000|CODEC · OPUS|HOLD · TALK|AUDIO ON|AUDIO OFF|HANDS·FREE|TRANSMIT|LISTENING|EXPAND|COLLAPSE|HOT TOPIC" app components --include='*.tsx' | wc -l   # 期望 0
grep -rn "uppercase tracking-wider" app components --include='*.tsx' | wc -l   # 期望 0
grep -c "AI 分身交流 · 内测" components/AgentExchangeWorkspace.tsx   # 期望 0

# E. 侧栏 5 项（对照：改前 grep -c 'label: "' components/Sidebar.tsx 为 8）
grep -c 'label: "' components/Sidebar.tsx   # 期望 5
grep -nE '"对话"|"分身"|"广场"|"世界"|"设置"' components/Sidebar.tsx | wc -l   # 期望 5

# F. 三栏退场、下拉退场、信号线（对照：改前 grep -c "w-1/4" app/page.tsx 为 2，grep -c "<select" components/ConversationPicker.tsx 为 1，grep -c "100vw - 64px" app/page.tsx 为 5）
grep -c "w-1/4" app/page.tsx   # 期望 0
grep -c "<select" components/ConversationPicker.tsx   # 期望 0
grep -c "<select" components/AgentExchangeWorkspace.tsx   # 期望 0
grep -c 'role="listbox"' components/ConversationPicker.tsx   # 期望 1
grep -c "<Signal" app/page.tsx   # 期望 1
grep -c "<Signal" app/login/page.tsx   # 期望 1
grep -c "100vw - 64px" app/page.tsx   # 期望 0
grep -c 'replace(" ", "T")' components/ConversationPicker.tsx   # 期望 ≥ 1

# G. 令牌换血（对照：改前 grep -c "#12100a" app/globals.css 为 1）
grep -c "#12100a" app/globals.css   # 期望 0
grep -cE "^\s*--background: #0E1219;" app/globals.css   # 期望 1
grep -cE "^\s*\.glass-card \{" app/globals.css   # 期望 1
grep -cE "^\s*\.echo::after \{" app/globals.css   # 期望 1
grep -c "lg-refract" app/layout.tsx   # 期望 0
grep -c "@layer components" app/globals.css   # 期望 ≥ 1

# H. 交互逻辑保留（对照：这些名字改前各出现 ≥1 次；删了就是删错了）
for s in handleNewChat handleDeleteConversation handleSelectConversation toggleInlineVoice setRecording handsFree voiceOn asrSessionRef handleSelectReferenceImage moveReferenceImage handlePickReferenceImages MiniCloudCard showHistory onPointerDown; do printf "%s %s\n" "$s" "$(grep -c "$s" app/page.tsx)"; done   # 期望每行数字 ≥ 1
for s in assertAccountAgent ExchangeDocuments ExchangeTopic act\( load\( download\( isDraftReviewExchange isArtifactApproved completionLabel stageLabel data-exchange-id data-exchange-detail data-official-agent data-exchange-artifact; do printf "%s %s\n" "$s" "$(grep -c "$s" components/AgentExchangeWorkspace.tsx)"; done   # 期望每行 ≥ 1

# J. 结构复刻（对照：改前 J1 为 37，J2 为 22，J3 为 15，J4 为 2）
grep -rn "rounded-2xl\|rounded-3xl" app components --include='*.tsx' | wc -l   # 期望 0
grep -rnE "bg-primary/(5|10)|border-primary/(20|25|30)|border-dashed" app components --include='*.tsx' | wc -l   # 期望 0
grep -rn "→" app components --include='*.tsx' | wc -l   # 期望 0
grep -rn "↔" app components --include='*.tsx' | wc -l   # 期望 0
grep -c 'role="tablist"' components/AgentExchangeWorkspace.tsx   # 期望 1
grep -c 'role="radio"' components/AgentExchangeWorkspace.tsx   # 期望 ≥ 1
grep -c "glass-card" components/AgentExchangeWorkspace.tsx   # 期望 ≥ 4
grep -c "主创初稿" components/AgentExchangeWorkspace.tsx   # 期望 ≥ 2
grep -c "<progress" components/AgentExchangeWorkspace.tsx   # 期望 0
grep -c "glass-card" app/plaza/page.tsx   # 期望 ≥ 1
grep -c "bg-primary text-primary-foreground" app/history/page.tsx   # 期望 0
grep -c "bubble-user" app/history/page.tsx   # 期望 ≥ 1
grep -c "sticky top-0" components/MyAgentWorkspace.tsx   # 期望 ≥ 1
grep -c "sticky top-0" components/AgentExchangeWorkspace.tsx   # 期望 ≥ 1

# I. 范围（在仓库根目录跑）
git status --porcelain -- backend desktop docs README.md PLAN.md CLAUDE.md frontend/lib frontend/components/ui frontend/next.config.ts frontend/package.json frontend/package-lock.json | grep -vE "^\?\? docs/(design|tasks)/" | wc -l   # 期望 0（仓库本来就有大量未提交改动，本条只看你不该碰的路径；以你开工前的 git status 快照为准）
```

UI 验收由派单方用隔离环境截图完成，你不需要起服务器；**不要**运行 `next dev` / `next start`。

## 9. 什么时候停下来问，什么时候自己定

- **停下来（在报告里写明，不要瞎猜）**：某条要求必须改白名单外的文件才能实现；某条要求与「不改交互语义」冲突；`ChatScrollArea` 无法在不改它的前提下占满新布局。
- **自己定**：只影响样式细节的取舍（间距差几像素、某个图标用哪个 lucide 图标、某个中文标签措辞）按原型就近选；找不到原型对应就用最朴素的 Tailwind 令牌类。
- **绝不**：回滚已完成的里程碑；用 `git checkout`/`git stash` 动仓库里你没改过的文件；运行 `npm install`；改 `backend/`。

## 10. 完成报告（写到 `docs/tasks/2026-09-12-frosted-instrument-ui-v2/03-report.md`）

1. 修改 / 新增 / 删除了哪些文件（逐个列）。
2. 与本规格 §2.4 对照表每一行、§3–§7 每一小节的逐项对应：做了 / 跳过（原因）。
3. §8 每条命令的实际输出（贴原文，不要转述）。
4. 未完成或需要人工确认的地方。
5. 用了几个 subagent、怎么分的工。
