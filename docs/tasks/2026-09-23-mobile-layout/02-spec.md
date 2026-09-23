# 规格：手机宽度可用（响应式布局）

日期：2026-09-23　级别：L2（UI 结构在窄屏下调整，桌面零变化）　基线：`main` @ `54a9b57`

## 0. 背景（你看不到之前的对话，这里是全部上下文）

Fiona 前端是 Next.js 16 App Router + React 19 + Tailwind 4（`frontend/`）。2026-09 刚完成「磨砂玻璃仪器 + 一条信号线」视觉重设计，**桌面端已由产品负责人验收，不能改变**。但整套界面没有任何响应式断点：`app/page.tsx`、`components/ConversationPicker.tsx`、`components/Sidebar.tsx` 里 `sm:/md:/lg:` 为 0 处，`app/manifest.ts` 却声明了 `standalone` + `portrait-primary`。

在 390×844 的手机视口实测（无头 Chromium）：

- 首页：56px 左侧导航 + 固定 260px 会话列表（`ConversationPicker.tsx:40-41`）之后，聊天区只剩约 74px，消息一个字一行竖排，输入区被挤成窄条；
- 广场（`components/AgentExchangeWorkspace.tsx:60-62`）的分类标签「单人体验 / 体验记录 / 发现分身」逐字竖排；体验记录表格是固定列宽网格 `grid-cols-[minmax(0,1fr)_150px_120px_60px_60px]`（`:95,:98`）；
- 世界（`app/plaza/page.tsx`）热点卡片是固定 `w-[220px]`（`:159`）并用绝对定位放在左上/右上（`:373,:387`），窄屏下互相重叠；
- 页面内边距普遍是桌面尺寸 `px-8`；
- `app/layout.tsx:15-21` 的 viewport 禁止缩放（`maximumScale: 1, userScalable: false`）；根容器用 `h-screen`，手机浏览器地址栏伸缩时底部会被遮住。

本任务只让**窄屏（< 768px，即 Tailwind `md` 以下）**可用；**≥ 768px 的渲染结果必须与现在完全一致**。

## 1. 产品目标

手机或 PWA 打开 Fiona 时，核心旅程可以正常完成：登录 → 看会话列表并切换/新建 → 和分身聊天（打字、发图、语音）→ 打开分身/广场/世界/设置 → 返回对话。视觉语言沿用现有设计（磨砂玻璃、琥珀色强调、`readout` 数字、`chip`/`btn` 族、信号线），只是换成适合单手竖屏的排布。

## 2. 技术约束

- **桌面零变化**：≥ 768px 时布局、尺寸、颜色、交互不得有任何变化。实现方式：窄屏样式一律用 `max-md:` 变体，或新增只在窄屏出现的元素用 `md:hidden`，只在桌面出现的用 `max-md:hidden`；**不得修改现有桌面类名的取值**（例外：`h-screen` 可换为 `h-dvh`，桌面浏览器下两者等价）。
- 只用现有设计令牌与组件类（`glass`、`glass-card`、`--glass-border`、`--amber-ink`、`--rec`、`readout`、`chip`、`btn`、`btn-quiet` 等，见 `app/globals.css`）；不引入新颜色、渐变、新字体、新依赖；图标只用已安装的 `lucide-react`。
- 修改前先读 `frontend/AGENTS.md`，涉及 Next.js API（如 `viewport` 导出）时读 `frontend/node_modules/next/dist/docs/` 里的对应文档。
- **允许修改的范围（白名单）**：`frontend/app/**`、`frontend/components/**`、`frontend/lib/**`、`frontend/README.md`，以及本目录下的 `03-report.md`。
- **禁止修改**：`backend/**`、`desktop/**`、`.github/**`、根目录 `README.md`/`PLAN.md`/`CLAUDE.md`、`docs/**`（本目录报告除外）、`frontend/package*.json`、`frontend/next.config.ts`、`frontend/AGENTS.md`（若 `next dev/build` 自动改写了它，保持原状不要处理，Claude 会还原）。
- 不要启动前后端服务、不要做浏览器截图（后端正在被另一个任务修改）；浏览器验证由 Claude 做。你只需跑类型检查、Lint、构建。
- 不得 `git commit` / `push` / `stash` / `reset` / `checkout`。不做无关重构，不改业务逻辑与接口调用。

## 3. 任务清单

请使用多个 subagent 并行推进，按**文件不重叠**分工（建议：A = `app/page.tsx` + `components/ConversationPicker.tsx` + `components/Sidebar.tsx` + `components/ChatScrollArea.tsx` + `components/ChatBubble.tsx`；B = `components/AgentExchangeWorkspace.tsx` + `components/MyAgentWorkspace.tsx` + `app/agents/**`；C = `app/plaza/page.tsx` + `app/match/page.tsx`；D = `app/settings`、`app/profile`、`app/history`、`app/login`、`app/community`、`app/layout.tsx`、`app/globals.css`）。**同一文件的多处修改由同一个 subagent 串行完成。**

### T1 应用外壳：底部标签栏

1. `< md`：`Sidebar` 变为**底部标签栏**——固定在视口底部、全宽、高 56px + `env(safe-area-inset-bottom)`，`glass` 背景、顶部 1px `--glass-border` 分隔线；五个入口（对话/分身/广场/世界/设置）等分排列，图标 20 + 10px 文字，激活态规则与桌面完全相同（含抽屉激活逻辑、按钮/链接两种形态、`aria-expanded`/`aria-controls`）。用 `<nav aria-label="主导航">`。
2. 标签栏里**不放** Logo、草莓余额、主题切换。
3. 草莓余额在窄屏移到对话页头部右侧，显示为 `🍓` + `readout` 数字，颜色阈值与 `Sidebar.tsx:150-163` 一致。避免同一页面重复轮询 `/strawberry`（可抽成一个共享 hook）。
4. 主题切换在窄屏放到会话列表抽屉（T2）的底部栏里。
5. 所有渲染 `<Sidebar />` 的独立页面（`app/plaza/page.tsx` 非嵌入模式、`MyAgentWorkspace`、`AgentExchangeWorkspace` 非嵌入模式等，请全库搜索 `<Sidebar`）在窄屏同样出现底部标签栏，并给内容区留出底部空间，确保最后一屏内容与浮动按钮不被遮挡。
6. 根容器 `h-screen` 改为 `h-dvh`（桌面等价）。

### T2 对话页（`app/page.tsx`）

1. **会话列表**：`< md` 时不占据版面，改为从左侧滑出的覆盖层（宽 `min(85vw, 320px)`，顶到视口顶、底到标签栏上沿，`glass` 背景 + 半透明遮罩）。由头部新增的按钮打开（lucide `PanelLeft` 或 `Menu`，`aria-label="对话列表"`，`md:hidden`）。选中会话、新建会话、点遮罩、按 Escape 都会关闭；打开时焦点移入列表，关闭时焦点回到打开按钮；覆盖层 `role="dialog" aria-modal="true" aria-label="对话列表"`。窄屏下删除按钮常显（触屏没有 hover）。桌面保持现有 260px 列。
2. **头部**：`< md` 为两行——第一行 56px：`[对话列表按钮] [头像 + 分身名（单行截断）] … [状态点（不显示文字）] [朗读] [免提] [🍓 余额]`，朗读/免提在窄屏只显示图标（保留 `aria-label`/`title` 与 `chip-on` 状态）；第二行是 24px 高的**信号线**（`Signal` 组件全宽显示）。消息滚动区的顶部留白要与窄屏头部实际高度一致（可用测量或固定类，不能让首条消息被遮住）。
3. **消息区**：窄屏左右内边距 16px；消息宽度随屏幕自适应（用户消息与分身消息都不能再出现逐字竖排），图片与卡片不超出屏幕宽度。
4. **输入区**：窄屏左右内边距 12px；底部位于标签栏上沿之上（不被遮挡，包括 iOS 安全区）；隐藏「Enter 发送，Shift + Enter 换行」提示（保留草莓消耗那一行）；「按住说话」只显示图标并保留 `aria-label="按住说话"`；发送、附图、语音等可点目标在窄屏不小于 40×40px；textarea 在窄屏字号 16px（防止 iOS 聚焦自动放大）。现有 `composerHeight` 动态测量逻辑继续生效。
5. **「当前对话记录」滑出层**（`page.tsx` 中 `showHistory` 那块，目前 `left-14`）：窄屏从 `left-0` 起、宽 `min(85vw, 320px)`、底部在标签栏之上。
6. **四个抽屉**（分身 `agent-drawer`、广场 `exchange-drawer`、世界、设置；目前宽度 `min(960px, calc(100vw - 56px))` 或 `calc((100vw - 56px) * 2 / 3)`）：窄屏宽度 `100vw`、从左边缘起、底部停在标签栏上沿（标签栏始终可见可点，用来切换或回到对话）。桌面宽度不变。

### T3 内容页在 390px 与 360px 下可用

以下页面在 `390×844` 与 `360×740` 下都必须：无横向滚动（`document.documentElement.scrollWidth <= window.innerWidth`）、无逐字竖排的标签或标题、主要按钮可点：

`/`、`/login`、`/agents`、`/agents/me`、`/agents/[id]`、`/plaza`（含 `?embed=1`）、`/match`（含 `?embed=1`）、`/settings`（含 `?embed=1`）、`/profile`（含 `?embed=1`）、`/history`、`/community`。

具体至少包括（其余问题请逐页排查后一并修）：
1. `AgentExchangeWorkspace` 分类标签：单行不换行（`whitespace-nowrap`），放不下时横向滚动（隐藏滚动条）。体验记录/邀请列表的固定列宽网格在窄屏改为两行堆叠：第一行话题，第二行「搭档 · 状态 · 次数 · 时间」，窄屏隐藏表头行。窄屏页面内边距 `px-4`。
2. `MyAgentWorkspace` 与 `app/agents/**`：窄屏内边距 `px-4`，表单与预览卡单列。
3. `app/plaza/page.tsx`（世界）：热点卡片在窄屏改为正常文档流单列全宽（不再绝对定位、不再固定 220px），卡片之间不重叠；右下角 `+` 浮动按钮在窄屏位于标签栏之上；底部「我的兴趣」条不被标签栏遮住。
4. `settings`、`profile`、`history`、`match`、`login`、`community`：窄屏内边距与宽度自适应；`history`、`match` 的消息气泡最大宽度改为按屏幕比例。

### T4 视口与可访问性

1. `app/layout.tsx` 的 `viewport`：去掉 `maximumScale: 1` 与 `userScalable: false`（恢复缩放），增加 `viewportFit: "cover"`；`themeColor` 保持。
2. 所有文本输入框、textarea、select 在窄屏字号不小于 16px。
3. 继续尊重 `prefers-reduced-motion`：新增的滑出/遮罩动画在 reduced-motion 下无动画。

## 4. 何时停下来问（判据）

- **必须停**：某条要求只能通过改变桌面（≥ 768px）呈现才能实现，或两条要求互相矛盾且没有唯一合理解。停下时在报告中写清卡点与已完成部分。
- **不要停、自己定**：图标选择、具体间距、组件拆分方式、hook 命名、窄屏下次要元素的取舍（只要不删除功能）——按最合理的理解做，在报告中说明。
- **任何情况下都不回滚已完成的工作。**

## 5. 验收标准（Claude 会逐条独立执行）

在 `frontend/` 下：

1. `npx tsc --noEmit` → 退出码 0。
2. `npm run lint` → 0 error，warning 数不超过 28（当前基线）。
3. `npm run build` → 成功。
4. 浏览器（Claude 在隔离环境执行）：
   - 390×844 与 360×740 下，第 T3 节所列每个路由 `scrollWidth <= innerWidth`；分类标签、导航文字均为单行；
   - 390×844 首页：消息气泡宽度 ≥ 240px；输入区下沿 ≤ 标签栏上沿；打开会话列表 → 选择另一个会话 → 列表自动关闭且消息切换；点标签栏「分身/广场/世界/设置」能打开对应抽屉且标签栏仍可见；
   - 1440×900 与 1024×768 下，首页、四个抽屉、`/agents/me`、`/agents`、`/plaza` 截图与改动前**视觉一致**（除时间等动态内容外无差异）。
5. `git status --porcelain --untracked-files=all` 中的每个路径都在第 2 节白名单内（`frontend/AGENTS.md` 的自动改写除外）。

## 6. 交付

完成后把变更总结写入 `docs/tasks/2026-09-23-mobile-layout/03-report.md`，必须包含：
1. 修改/新增了哪些文件；
2. 实现了哪些功能；
3. 与本规格 T1–T4 的逐项对应；
4. 类型检查 / Lint（warning 数）/ 构建结果；
5. 未完成或需要人工确认的地方（尤其是你对窄屏取舍做的决定）。
