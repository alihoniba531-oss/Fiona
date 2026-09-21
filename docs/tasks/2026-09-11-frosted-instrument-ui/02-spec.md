# 规格：Fiona 前端视觉重设计落地——磨砂玻璃仪器 + 一条信号线

任务日期：2026-09-11。任务级别：L3（UI 大改，纯视觉层，不改任何后端、接口、路由、数据与交互语义）。

你是独立执行进程，看不到任何对话上下文。**本文件没写的，就是禁止你自由发挥的。** 拿不准时按第 9 节判据处理。

## 0. 阅读顺序与真源

1. 通读本文件。
2. 打开 `docs/design/chloe-ui-proposal.html`（已拍板的设计原型，单文件 HTML）。它的 `<style>` 里的**每个数值都是真源**：令牌、字号、间距、圆角、玻璃参数、信号线算法、分身名排法。本文件引用它时写「原型 §xxx」。可以在浏览器里打开看效果：`open docs/design/chloe-ui-proposal.html`。
3. 读 `frontend/AGENTS.md`、`frontend/CLAUDE.md`，以及 `frontend/node_modules/next/dist/docs/` 里与你要碰的 API 相关的文档（Next.js 16 与你训练数据里的不同）。
4. 再读第 2 节白名单里的文件。

## 1. 产品目标

Chloe（项目 Fiona）是「每个人自己的 AI 分身」产品。现有界面是暖琥珀 HUD 风：液态玻璃折射、四角尖括号、扫描线、3D 能量球、三栏悬浮卡、英文伪仪表标签（VOICE PORT / DATA STREAM / SYS·CLOCK）。作者要求改成**「科技感 + 简洁」**，方向已定为**「磨砂玻璃仪器，一条信号线」**：

- 蓝灰墨底、琥珀唯一强调色（延续品牌色，但只做哑光指示灯，不发光）。
- 外壳与卡片是**磨砂玻璃**：统一模糊 + 半透明 + 细颗粒；**不折射、不发光、没有湿润高光**（这是与旧 `.liquid-glass` 的分界线）。
- 中文标签；数字、时间、回合数、模型名用等宽读数。
- 唯一动效：对话头部的**信号线**（待命 / 正在听 / 正在说 三态）。3D 球、轨道粒子、频谱条、心电图、扫描线、星空全部退场。
- 对话页三栏收成两栏：左侧对话列表 + 对话；工具卡片回到消息里（消息本身已带 `cardData` 内联渲染，右侧「DATA STREAM」栏是重复层）。
- 侧栏 8 项收成 5 项：对话 / 分身 / 广场 / 世界 / 设置。

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
- `frontend/components/GeneratedImage.tsx`（仅圆角/描边/按钮类名）
- `frontend/components/NewsCardContent.tsx`（仅类名）

**新增：**
- `frontend/components/Signal.tsx`

**删除（只删这 5 个，删前确认全库无其他引用）：**
- `frontend/components/TopBar.tsx`
- `frontend/components/AmbientHUD.tsx`
- `frontend/components/HudOrb.tsx`
- `frontend/components/HudOrb3D.tsx`
- `frontend/components/StarField.tsx`

**明确不动：** `backend/**`、`desktop/**`、`frontend/lib/**`、`frontend/components/ui/**`、`frontend/app/shadcn-tailwind.css`、`frontend/components/ChatScrollArea.tsx`、`frontend/components/SolarSystem3D.tsx`、`frontend/components/Earth3D.tsx`、`frontend/components/PwaRegister.tsx`、`frontend/app/manifest.ts`、`frontend/next.config.ts`、`frontend/package.json`、`frontend/package-lock.json`、`frontend/proxy.ts`、所有 `docs/**`、`README.md`、`PLAN.md`、`CLAUDE.md`。

### 2.2 行为红线

- **不改任何交互语义**：所有 state、handler、effect、API 调用、路由、`aria-*`、`inert`、`tabIndex`、键盘处理、`embed=1` 嵌入模式、账号切换清理逻辑原样保留。你做的是把 JSX 搬进新布局、换类名、删装饰元素。
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

所有人依赖的**类名与令牌在 §3 已全部定死**，不必等 A 写完再开工；A 写 CSS，其他人照 §3 的类名用。

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
- `.typing-cursor::after` 里的 `text-shadow` 一行删掉（其余保留）
- `.dark .cloud-card { animation-duration … }` 删掉
- 末尾 `@media (prefers-reduced-motion: reduce)` 块把 `.dark *` 三个选择器改成 `*, *::before, *::after`（不再只对深色生效）

**保留不动：** `.glass`（下面会重写它）、`.msg-in-left/right` 与两个 slideIn keyframes、`.wave-bar` 与 `@keyframes wave`、整段滚动条样式、`@keyframes ticker-scroll` 与 `.ticker-track`、`@keyframes topic-drawer-open` 与 `.topic-drawer-in`、`@keyframes blink`、`.hud-like-*`。

### 3.4 新增 / 重写这些工具类（追加在 `@layer base` 之后）

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
- 所有抽屉 `className` 里 `liquid-glass` → `glass`；`style` 里的 `boxShadow` 改成打开时 `"-12px 0 32px rgba(0,0,0,0.28)"`、关闭时 `"none"`；`borderLeft` 统一 `"1px solid var(--glass-border)"`。
- 抽屉头部 `style={DRAWER_HEADER_STYLE}` 改为 `className="flex shrink-0 items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--glass-border)" }}`；标题 `hud-label` → `text-xs font-medium text-muted-foreground`；删除 `DRAWER_HEADER_STYLE`、`DRAWER_LABEL_STYLE` 常量。
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
- `formatRelative(iso)`：同一天显示 `HH:mm`；昨天显示「昨天」；7 天内显示星期（周一…周日）；否则 `MM/DD`。写在组件文件内，不改 `lib/`。
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
  <div class="py-1 text-[40px]"><span class="echo" data-text={name}>{name}</span></div>   ← name = agent.display_name || "我的分身"
  <p class="text-[13px] leading-[1.7] whitespace-pre-wrap break-words">{agent.bio || "这个分身还没有填写介绍。"}</p>
  <div class="flex items-center gap-2.5 border-t pt-3.5 text-xs text-muted-foreground" style={{borderColor:"var(--glass-border)"}}>
    <span class="grid h-8 w-8 place-items-center rounded-[6px] bg-secondary text-base" aria-hidden>{agent.avatar_emoji || "✨"}</span>
    <span>由用户创建的人工智能分身</span>
  </div>
  {preview && <p class="text-xs text-muted-foreground">…原文案…</p>}
</section>
```

`.echo` 的名字超过 12 个字时不用 `echo`（直接 `text-[28px] font-medium break-words`），避免 `white-space: nowrap` 的副本溢出。

### 6.2 `MyAgentWorkspace.tsx`、`AgentExchangeWorkspace.tsx`、`agents/[id]/page.tsx`、`AgentMemoryPanel.tsx`

- 删 `<TopBar />`（§4.3）。
- 页面头部 `<header className="glass border-b border-border px-6 py-5">` → `<header className="glass sticky top-0 z-[2] border-b px-8 pb-[18px] pt-7" style={{borderColor:"var(--glass-border)"}}>`，内部包一层 `<div className="max-w-[976px] flex items-end justify-between gap-4">`；标题 `text-lg font-semibold` → `text-xl font-medium tracking-[-0.01em]`。
- `fieldClass`：`rounded-xl border border-border bg-secondary px-3 py-2.5 text-sm …` → `rounded-[6px] border bg-card px-3 py-[9px] text-sm outline-none focus:border-[color:var(--amber-ink)] disabled:opacity-50` 并加 `style` 无法进 class 常量的话，用 Tailwind 任意值 `border-[color:var(--border)]`。
- `buttonClass` → `btn`；`primaryButtonClass` → `btn btn-primary`；所有 `hud-btn` → `btn`；`rounded-xl bg-primary … text-primary-foreground` 的保存按钮 → `btn btn-primary`；红色文字动作（清空记忆、删除、停止）→ `btn btn-danger`。
- 公开名片开关那块 `rounded-xl border border-border bg-card p-4` → `glass-card p-4`（checkbox 本身不动）。
- 广场官方搭档卡与公开分身卡：容器 → `glass-card p-4 flex flex-col gap-2.5`；选中态 `border-[color:var(--amber-ink)]`；卡内模型名（如 `DeepSeek V4 Pro`）用 `readout`。
- 广场标签页（official/experiences/gallery/received/sent）：改成下划线式：容器 `flex gap-1 border-b` + 每个按钮 `h-9 px-3 text-[13px] text-muted-foreground border-b-2 border-transparent -mb-px`，选中 `text-foreground border-[color:var(--amber-ink)]`；待处理计数用 `readout text-[11px]` 且颜色 `var(--amber-ink)`。
- 交流详情：回合数改成读数 `第 <b>N</b> 次 / M`（`readout`）；若详情数据里有当前阶段字段（`draft` / `review` / `revision`，见文件内 `stageLabel` 那段），渲染三段式阶段条：`<div class="inline-flex overflow-hidden rounded-[6px] border" style={{borderColor:"var(--glass-border)"}}>` 内三个 `<span class="flex items-center gap-1.5 px-3.5 py-1.5 text-xs">`，已完成的加 `<Check size={14}/>` 且文字 `text-foreground`，未完成 `text-muted-foreground`，相邻用 `border-l`。**没有该字段就跳过这一项并在报告里说明。**
- 「当前作品」块 → `glass-card`，头行「当前作品 | <b>字数</b> 字」，底部下载三按钮 `btn`。
- `AgentMemoryPanel.tsx`：标题行右侧修订号用 `readout`（「修订 <b>N</b>」）；条目 `text-[13px] text-muted-foreground py-1.5 border-b` 边框色 `var(--glass-border)`；按钮映射同上。

### 6.3 `plaza` / `match` / `profile` / `settings` / `community` / `history`

- 删 `<TopBar />`。
- 按 §3.5 表替换 `hud-*`、`liquid-glass`、`plaza-card`；`plaza` 的 `SolarSystem3D`、`match` 的 `Earth3D` **保留**；`cloud-card` 保留。
- 页面头部与卡片容器改 `glass` / `glass-card`；按钮映射同上。不改结构。

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
npm run lint            # 期望：0 errors；warnings ≤ 35（基线 35；你删掉死代码只会更少，不得新增）
npx tsc --noEmit        # 期望：无输出，退出码 0
npm run build           # 期望：Compiled successfully，退出码 0（只在最后跑一次）

# B. 旧类彻底清除（对照：改前 grep -rE "hud-|liquid-glass" app components --include='*.tsx' | wc -l 为 80）
grep -rnE "hud-[a-z0-9-]+|liquid-glass|lg-refract|hud-card-float|shutter-handle|plaza-card" app components --include='*.tsx' | grep -v "hud-like" | wc -l   # 期望 0
grep -nE "hud-(panel|corners|card-float|pill|label|pulse|btn|avatar-ring|orb|ekg)|liquid-glass|shutter-handle|hud-scan|body::after" app/globals.css | wc -l   # 期望 0

# C. 组件退场（对照：改前 grep -rlE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l 为 15）
grep -rnE "StarField|HudOrb|AmbientHUD|TopBar" app components | wc -l   # 期望 0
ls components/TopBar.tsx components/AmbientHUD.tsx components/HudOrb.tsx components/HudOrb3D.tsx components/StarField.tsx 2>&1 | grep -c "No such file"   # 期望 5
test -f components/Signal.tsx && echo ok   # 期望 ok

# D. 英文伪仪表标签清除（对照：改前 grep -rnE "VOICE PORT|DATA STREAM|SYS · CLOCK|HOLD · TALK|AUDIO ON" app components | wc -l 为 5）
grep -rnE "VOICE PORT|DATA STREAM|SYS · CLOCK|SR · 16000|CODEC · OPUS|HOLD · TALK|AUDIO ON|AUDIO OFF|HANDS·FREE|TRANSMIT|LISTENING|EXPAND|COLLAPSE" app components --include='*.tsx' | wc -l   # 期望 0

# E. 侧栏 5 项（对照：改前 grep -c "label: \"" components/Sidebar.tsx 为 8）
grep -c 'label: "' components/Sidebar.tsx   # 期望 5
grep -nE '"对话"|"分身"|"广场"|"世界"|"设置"' components/Sidebar.tsx | wc -l   # 期望 5

# F. 三栏退场、下拉退场（对照：改前 grep -c "w-1/4" app/page.tsx 为 2，grep -c "<select" components/ConversationPicker.tsx 为 1）
grep -c "w-1/4" app/page.tsx   # 期望 0
grep -c "<select" components/ConversationPicker.tsx   # 期望 0
grep -c "role=\"listbox\"" components/ConversationPicker.tsx   # 期望 1
grep -c "<Signal" app/page.tsx   # 期望 1
grep -c "<Signal" app/login/page.tsx   # 期望 1

# G. 令牌换血（对照：改前 grep -c "#12100a" app/globals.css 为 1）
grep -c "#12100a" app/globals.css   # 期望 0
grep -cE "^\s*--background: #0E1219;" app/globals.css   # 期望 1
grep -cE "^\.glass-card \{" app/globals.css   # 期望 1
grep -cE "^\.echo::after \{" app/globals.css   # 期望 1
grep -c "lg-refract" app/layout.tsx   # 期望 0

# H. 交互逻辑保留（对照：这些名字改前各出现 ≥1 次；删了就是删错了）
for s in handleNewChat handleDeleteConversation handleSelectConversation toggleInlineVoice setRecording handsFree voiceOn asrSessionRef handleSelectReferenceImage moveReferenceImage handlePickReferenceImages MiniCloudCard showHistory; do printf "%s %s\n" "$s" "$(grep -c "$s" app/page.tsx)"; done   # 期望每行数字 ≥ 1
grep -c "onPointerDown" app/page.tsx   # 期望 ≥ 1（按住说话搬到了输入区）

# I. 范围（在仓库根目录跑）
git status --porcelain -- backend desktop docs README.md PLAN.md CLAUDE.md frontend/lib frontend/components/ui frontend/next.config.ts frontend/package.json frontend/package-lock.json | grep -vE "^\?\? docs/(design|tasks)/" | wc -l   # 期望 0（注意：仓库本来就有大量未提交改动，本条只看你不该碰的路径有没有出现在你之后的 diff 里；以你开工前的 git status 快照为准）
```

UI 验收由派单方用隔离环境截图完成，你不需要起服务器；**不要**运行 `next dev` / `next start`。

## 9. 什么时候停下来问，什么时候自己定

- **停下来（在报告里写明，不要瞎猜）**：某条要求必须改白名单外的文件才能实现；某条要求与「不改交互语义」冲突；`ChatScrollArea` 无法在不改它的前提下占满新布局；交流详情没有阶段字段（这条只是跳过 + 说明，不算阻塞）。
- **自己定**：只影响样式细节的取舍（间距差几像素、某个图标用哪个 lucide 图标、某个中文标签措辞）按原型就近选；找不到原型对应就用最朴素的 Tailwind 令牌类。
- **绝不**：回滚已完成的里程碑；用 `git checkout`/`git stash` 动仓库里你没改过的文件；运行 `npm install`；改 `backend/`。

## 10. 完成报告（写到 `docs/tasks/2026-09-11-frosted-instrument-ui/03-report.md`）

1. 修改 / 新增 / 删除了哪些文件（逐个列）。
2. 与本规格 §3–§7 每一小节的逐项对应：做了 / 跳过（原因）。
3. §8 每条命令的实际输出（贴原文，不要转述）。
4. 未完成或需要人工确认的地方。
5. 用了几个 subagent、怎么分的工。
