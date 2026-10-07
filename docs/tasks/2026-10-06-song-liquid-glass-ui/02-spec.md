# 02 规格：前端整体改版「宋式清雅 × 液态玻璃（影青釉）」

- 规格版本：v1（2026-10-06）
- 基线：`main` @ `586d86a`；工作分支 `feat/song-liquid-glass-ui`（独立工作树）
- 执行者：Codex（实现）；Claude（规格、验证、复核）；用户（拍板）
- 任务级别：L3（UI 大改）。设计方向与本规格的取舍已由用户拍板，执行中不设中途确认。

---

## 1. 产品目标

Chloe（Fiona 前端）整体换成「宋朝清雅 + 液态玻璃」的视觉语言，取代现在的「磨砂玻璃仪器」深色 HUD 风格：

- 昼主题「汝窑天青」、夜主题「建盏黑釉」，默认跟随系统，可手动切换并记住；
- 一套字：思源宋体（Noto Serif SC，已自托管）；
- 桌面导航是竖排书签；一屏只盖一方朱印（只给分身身份）；
- 玻璃是一层瓷釉：口沿出筋/酱口、积釉、酥油光、顶边细高光、边缘透镜折射；玻璃后面是一幅极淡的绢本烟雨山水，内容可以从玻璃下面流过——透明感一眼可读；
- 「素瓷」：减少透明度时的不透明退路，可由系统设置或应用内开关触发；
- 世界页的 3D 星系换成静态星图（淳祐天文图式）。

使用场景不变：和自己的分身对话（文字、语音、生图修图）、编辑分身、广场交流、看世界热点与照片、设置。**本次只换视觉与必要的布局结构，不改任何功能、接口、数据流。**

## 2. 设计来源（权威参考，实现以此为准）

全部在本任务目录 `design/` 下：

| 文件 | 内容 |
|---|---|
| `design/source/Chat.dc.html` | **全站材质标准**。文件开头的 HTML 注释写全了玻璃配方（层次、数值、Safari 退路、素瓷、减弱动态）。`/*THEMES*/ … /*END*/` 之间是四套令牌（`day`、`night`、`daySolid`、`nightSolid`，51 个键）。 |
| `design/source/ChatMobile.dc.html` | 手机对话页（390×844）：页头釉片、底部一整片釉（输入 + 导航）、生图模型选择、安全区。 |
| `design/source/Main.dc.html` | 登录页。 |
| `design/source/Agent.dc.html` | 分身页（编辑表单 + 名片预览 + 私有记忆）。 |
| `design/source/Exchange.dc.html` | 广场页（单人体验标签）。 |
| `design/source/World.dc.html` | 世界页（星图 + 七类热点 + 我的兴趣 + 发布照片）。 |
| `design/source/Settings.dc.html` | 设置页（含「外观」三档与「素瓷」开关）。 |
| `design/source/Tokens.dc.html` | 规范页：色、字、件、材质的总表。 |
| `design/source/ChatNight.dc.html`、`ChatMobileNight.dc.html` | 仅是以 night 导入上面两个文件的壳。 |
| `design/shots/*.jpg` | 上述画板的渲染截图（昼、夜、素瓷、1920 宽屏），用来对照观感。 |

读设计源文件的方法：
- 它们是一种画板格式（`.dc.html`）。所有样式写在行内 `style` 上，颜色写成 `var(--键)`，根元素上用 `--键:{{t.键}}` 从 THEMES 取值。把 `{{t.键}}` 理解为「该主题下这个键的值」即可。
- `{{toggleChar}}`/`{{toggleLabel}}` 是昼夜切换按钮的「昼/夜」字与无障碍名。
- 画板为了格式限制把高光、边缘等写成了额外的 `aria-hidden` 层；真实实现可以用伪元素或封装组件，**观感与数值要一致**。
- 画板里的示例文案（对话内容、热点标题、用户名 lin_qing 等）是占位，真实页面用真实数据；但画板里的**界面文案**（按钮、标签、说明）以现有代码为准，除非本规格明确要求改。

代码现状地图：`01-frontend-map.md`（6 个只读调研代理产出，行号以 586d86a 为准）。每个区域都写了位置、结构、必须保留的行为、状态和改造风险。**动一个区域前先读它在地图里的条目。**

## 3. 已拍板的决定

1. 方向：按设计稿的「影青釉」液态玻璃落地。
2. 外观默认**跟随系统**（系统浅色→昼·天青，系统深色→夜·建盏）。用户可在设置里选「跟随系统 / 昼 / 夜」，导航上的圆形「昼/夜」按钮切换为显式的昼或夜。选择持久化。
3. 字体：思源宋体可变字重 300–600，按 Google Fonts 的 unicode-range 切片自托管（**已放好，见 §4.3，不要改动这些文件**）。
4. 世界页 3D 星系换成静态星图；匹配页的 Earth3D 背景换成烟雨山水背景。**不删除** `SolarSystem3D.tsx`、`Earth3D.tsx`、`public/textures/*`，**不改** `package.json`/`package-lock.json`（three 系依赖之后单独处理）——只是不再 import。
5. 「素瓷」不透明退路三种触发：系统 `prefers-reduced-transparency: reduce`、系统 `prefers-contrast: more`、应用内开关（设置页「外观」一节）。
6. 不改后端，不改任何接口与数据形状。

## 4. 技术约束

### 4.1 范围
- 只改 `frontend/` 下的源码与样式（`app/`、`components/`、`lib/`、`proxy.ts`）。允许新增组件文件。
- **不许**：改 `package.json`/`package-lock.json`；删除任何文件；改后端；改 `next.config.ts`（CSP 已允许 `font-src 'self'`、内联 SVG 与内联脚本，不需要改）；动 `components/ui/*`（零引用的死代码，改了也无法在界面验证）；提交 git commit。
- `frontend/AGENTS.md` 要求：写 Next.js 代码前先读 `node_modules/next/dist/docs/` 里相关的文档（Next 16 与旧版本有差异）。

### 4.2 必须原样保留（违反即不合格）
- **接口与数据**：POST /chat 请求体、SSE 事件结构、GET /image-models、/asr、TTS 票据与流、GET /strawberry 及其 60s 轮询、/match/pending 轮询、广场 4s/3s 轮询、帖子与热点接口。账号隔离机制（`useAccountIdentity` 的 owner key 重挂载、`useAccountRequest` 的 isCurrent 校验、`assertAccountAgent`）。
- **id 与 data 钩子**：`data-chat-panel`、`data-chat-composer`、`data-chat-scroll-area/-viewport/-content`、`#agent-drawer`、`#exchange-drawer`、`#plaza-drawer`、`#settings-drawer`、`#conversation-picker-dialog`、`data-agent-exchange-workspace`、`data-official-agent`、`data-exchange-id`、`data-exchange-detail`、`data-exchange-message`、`data-exchange-artifact`。
- **无障碍与焦点契约**：Sidebar 触发按钮的 `aria-controls`（`focusVisibleDrawerTrigger` 靠 `button[aria-controls=…]` + `getClientRects` 找可见触发器，桌面与手机两套按钮里隐藏的那套必须是 `display:none`）；两个 section 抽屉的 `aria-hidden` + `inert` + `tabIndex=-1` + Esc；手机对话目录的 `role=dialog aria-modal` 焦点陷阱；所有现有 `aria-label`（含「朗读」「免提」「按住说话」「语音转文字」「发送消息/生成图片/修改图片」等）。
- **语音与朗读的用户手势**：朗读、免提、「点此播放」「帮我读」的点击处理必须在同一个用户手势里同步调用 `primeTtsAudio`/`play`，不能包进会延后 click 的容器或异步逻辑。按住说话的 `setPointerCapture`/`pointerup` 必须在新的按钮内部结构下仍正确释放。
- **测高与输入**：footer 上的 `composerRef`（测 `--composer-height`）、`textareaRef` 与两个 composition 事件、`focusChatInput` 读取的 `aria-hidden`/`inert` 字符串值。
- **滚动跟随**：`ChatScrollArea` 的「在底部才跟随」逻辑与 ResizeObserver；背景画不得画进滚动视口内部，不得给滚动内容加 transform。
- **文案**（后端或文档引用，或属于 AI 身份披露与隐私承诺，一字不改）：「以此图修改」「加入参考」「已选为图N」「AI 分身」「由用户创建的人工智能分身」「官方 AI」「平台官方 AI · 无真人用户」「交流总结 · AI 生成」、交流免责说明（含「不代表真人即时发言」）、广场开始表单的流程与隐私说明（含「不读取性格设定」「每个账号每天…」）、公开名片开关说明、「名片始终标明…」、记忆清空确认文案、所有空态/加载/错误文案。
- **手机端不变量**（来自 2026-09-23 手机适配规格）：390×844 与 360×740 下 /、/login、/agents、/agents/me、/agents/[id]、/settings（含 embed）、/profile（含 embed）、/history 无横向滚动；可点目标 ≥ 40×40；textarea/input 字号 ≥ 16px；底部导航始终可见可点；抽屉底边停在底部导航上沿；输入区下沿不低于底部导航上沿；标签不出现逐字竖排（**桌面竖排书签导航是有意的竖排，不受此条限制**）。
- **断点规则**：会被 iframe 内嵌的页面（/plaza、/match、/settings、/profile、/community）只用自定义 `mobile:` 变体（尊重 `html[data-shell=desktop]`），不得写 `max-md:`；其余页面沿用 `max-md:/md:`。
- **CI 门槛**：`npm run lint` 0 错误且警告数 ≤ 25（基线 25；CI 上限 38）；`npx tsc --noEmit` 通过；`npm run build` 通过。

### 4.3 已放好的资源（不要改动）
- `frontend/public/fonts/noto-serif-sc/noto-serif-sc-000.woff2 … -100.woff2`（101 个切片，可变字重 300–600）与 `OFL.txt`（SIL OFL 1.1 许可）。
- `frontend/app/fonts/noto-serif-sc.css`：101 条 `@font-face`（`font-family: 'Noto Serif SC'`、`font-weight: 300 600`、`unicode-range`、`url('/fonts/noto-serif-sc/…')`）。
- 你需要做的：在全局样式里引入它；把 `fonts` 加进 `proxy.ts` matcher 的排除列表（否则生产环境未登录时 /login 请求字体会被 302 到 /login）。
- 字体栈：`'Noto Serif SC', 'Songti SC', 'STSong', serif`，全站一套（包括原来用 `--font-mono-stack` 的读数、时间、余额——改为同一字体 + `font-variant-numeric: tabular-nums`）。

### 4.4 性能与兼容
- 玻璃基层用 `backdrop-filter: blur() saturate() brightness()`（同时写 `-webkit-backdrop-filter`），走令牌 `--bd`/`--bd-strong`；素瓷时令牌为 `none`。
- 边缘透镜 `backdrop-filter: url(#…)` 只有 Chromium 支持：放在**独立的兄弟层**上，Safari/Firefox 丢弃后不得有任何副作用；只给框架玻璃（导航釉片、页头、输入釉片、手机底部釉片、抽屉外壳、世界页两侧热点釉片），**不给**消息、浮签、卡片、装裱。
- 不得嵌套 backdrop-filter（内层只能透到最近的带 backdrop 的祖先）。浮签、工具卡、装裱框、生成图卡、广场卡片等「清釉瓷片」只着色 + 口沿，不做 backdrop-filter。
- 关闭状态（推到屏外）的抽屉不得保留 backdrop 层（用 `visibility:hidden` 或只在打开时渲染玻璃层）。
- 减弱动态（`prefers-reduced-motion: reduce`）：远山语音线停在待命形；页头与输入釉片的透镜层关闭；其余动画沿用现有全局规则。
- 不新增 rAF 常驻循环之外的循环；星图静止不转。

## 5. 令牌与主题系统

### 5.1 令牌
- 以 `design/source/Chat.dc.html` 的 THEMES 为准，把 51 个键落成 CSS 自定义属性：`:root`（昼）、`.dark`（夜）、`[data-solid]`（昼素瓷）、`.dark[data-solid]`（夜素瓷）。键名直接用作变量名（`--paper`、`--hi`、`--slip`、`--ink`、`--ink2`、`--ink3`、`--rule`、`--rule2`、`--seal`、`--glyph`、`--btn`、`--btnink`、`--weave`、`--chart`、`--chartf`、`--river`、`--sky`、`--water`、`--m1`…`--m4`、`--mist`、`--ripple`、`--glass`、`--glass2`、`--thin`、`--thin2`、`--chip`、`--tile`、`--mount`、`--pool`、`--sheen`、`--rim`、`--lip`、`--lipdk`、`--carve`、`--etch`、`--spec`、`--bloom`、`--drop`、`--fur`、`--blur`、`--blur-strong`、`--sat`、`--bri`、`--bd`、`--bd-strong`、`--lens`、`--art`；THEMES 里的 `blurS`、`bdS` 对应 `--blur-strong`、`--bd-strong`）。
- 新增 `--scrim`（抽屉/弹层遮罩：昼 `rgba(31,41,38,.18)`，夜 `rgba(0,0,0,.45)`），替换所有 `bg-black/20`、`backdrop:bg-black/75` 等写死的遮罩色。
- **旧令牌改为新令牌的别名**，让暂未逐一改写的工具类也落到新配色上：`--background:var(--paper)`、`--foreground:var(--ink)`、`--card:var(--hi)`、`--popover:var(--hi)`、`--primary:var(--btn)`、`--primary-foreground:var(--btnink)`、`--secondary:var(--slip)`、`--muted:var(--slip)`、`--muted-foreground:var(--ink2)`、`--accent:var(--slip)`、`--accent-foreground:var(--ink)`、`--destructive:var(--seal)`、`--border:var(--rule)`、`--input:var(--rule2)`、`--ring:var(--ink)`、`--amber-ink:var(--ink)`、`--dim:var(--ink3)`、`--rec:var(--seal)`、`--rec-soft:` 朱色 12% 透明、`--glass-border:var(--rule)`、`--fill:` 墨色 3%（夜为月白 4%）、sidebar 系同理。删掉 `--grain`、`--spot-a/b/c` 及 body 三光斑背景。新写的代码直接用新令牌。
- 删除旧的琥珀色值 `#F2A63A`/`#9E6209`/`#0E1219` 等深色 HUD 值。

### 5.2 主题与素瓷
- 存储：`localStorage['chloe-appearance']` ∈ `system | day | night`（缺省 `system`），`localStorage['chloe-solid']` ∈ `0 | 1`（缺省 0）。
- **首帧脚本**（放在 `layout.tsx` 现有 data-shell 脚本旁，内联、同步执行，绘制前完成）：读两个键 + `matchMedia('(prefers-color-scheme: dark)')`，决定 `<html>` 是否带 `dark` 类；`chloe-solid=1` 或 `prefers-reduced-transparency: reduce` 或 `prefers-contrast: more` 时设 `data-solid`；同步设置 `<meta name="theme-color">`（昼 `#E8EEEA`、夜 `#161412`）与 `document.documentElement.style.colorScheme`（light/dark）。`layout.tsx` 不再写死 `className="dark"`。
- 跟随系统时监听 `prefers-color-scheme` 变化；监听 `storage` 事件，使 iframe 抽屉（/plaza、/match、/settings、/profile 的 `?embed=1`）、新标签页（/history）与主页面保持一致。
- `lib/useTheme.ts` 改为暴露 `{ appearance, setAppearance, dark, solid, setSolid }`（可保留 `toggleTheme`，语义改为在昼/夜之间切换为显式值）；服务端快照与首帧不一致造成的图标闪变要避免（例如挂载后再渲染昼/夜字，或 `suppressHydrationWarning`）。
- `viewport.themeColor` 改为按 `prefers-color-scheme` 的数组（昼 `#E8EEEA`、夜 `#161412`），首帧脚本再按实际外观覆盖；`appleWebApp.statusBarStyle` 用 `default`；`manifest.ts` 的 `theme_color`/`background_color` 用昼 `#E8EEEA`。
- 声明 `color-scheme`，让原生控件（date、checkbox、number、滚动条）跟随主题。
- 滚动条样式里 `.dark` 选择器按新主题机制同步。

## 6. 共享视觉组件（新增，名称固定，便于验收）

| 组件（`frontend/components/`） | 职责 | 设计来源 |
|---|---|---|
| `Glaze.tsx` | 釉片容器：渲染 `aria-hidden` 附属层（透镜层、釉层、釉色底、釉光/积釉/口沿、顶边高光 + 辉光、夜间兔毫可选），子内容在其上。变体至少：`panel`（左侧/抽屉大釉片）、`strip`（页头细条，透镜用 bar 参数，不用「上白下青」纵向渐变）、`slab`（输入釉片，用 `--glass2`/`--bd-strong`）。参数决定是否带透镜层。所有附属层 `border-radius: inherit`。 | Chat.dc 开头配方注释 + 左釉片/页头/输入釉片标记 |
| `LensDefs.tsx` | 每个文档一份的 `<svg width=0 height=0>` 透镜滤镜定义（`yqd-lens` 3/7/32、`yqd-lens-bar` 3/6/20、手机 `yqm-lens` 3/7/32），挂在根布局 body 里，iframe 文档各自也有。 | Chat.dc、ChatMobile.dc 的 `<filter id="yq…-lens…">` |
| `InkLandscape.tsx` | 玻璃后面的绢本烟雨山水（静态 SVG + 渐变底 + 绢纹），`position:fixed`、`aria-hidden`、`pointer-events:none`、`opacity: var(--art)`。变体：`chat`（桌面主山钉在左侧、始终压在左釉片之后，汀洲随对话栏越过输入釉片上沿；1920 宽不滑进阅读栏）、`chat-mobile`（随安全区移位）、`page`（分身/广场/设置等页）、`login`（右下一角平远）。 | Chat.dc / ChatMobile.dc / Agent.dc / Exchange.dc / Settings.dc / Main.dc 各自的背景 SVG |
| `StarChart.tsx` | 世界页星图（外规双圈、内规、赤道、黄道、二十八宿按古度不等分的径线与宿名、天河带、星官连线与散星；夜间像石刻拓本）。静止。 | World.dc |
| `Seal.tsx` | 朱印：`brand`（双圆环，白文）与 `agent`（分身头像符号）。带「印泥磨损」位移滤镜与轻微旋转。`agent` 印内显示 `avatar_emoji` 的第一个字形；为空或为默认 `✨` 时画 ✦ 四角星路径。**一屏只出现一方**：登录页用 `brand`；对话页头、名片预览用 `agent`；导航品牌标用墨色双圆环（不用 Seal）。 | Main.dc、Chat.dc 页头、Agent.dc 名片 |
| `Signal.tsx`（改写，保留文件名与 `mode` 接口） | 远山语音状态线：两道山脊（远 `--rule2`、近 `--ink2`），`idle` 静止；`speaking` 山势起伏；`listening` 近山轻颤并用 `--seal`。保留 viewBox 横向拉伸不变粗（`vector-effect: non-scaling-stroke`）、`aria-hidden`、减弱动态静止分支；两个调用点（主页页头、登录页）都要验。 | Chat.dc 页头 + Tokens.dc「远山：语音状态线」三态 |

全局样式里的 `.glass`、`.glass-card`、`.echo`、`.signal`（旧形态）、`.state-dot`、`hud-*` 等旧装饰类：改为新语言或删除定义；`.btn/.chip/.tag` 按设计稿的按钮与标签重绘（主按钮墨底、次按钮细线框、文字按钮、危险用朱字；`.chip` 仍兼作可点与只读两用，保留现有覆盖类的手机 40px 触控）。`.bubble-user` = 天青浮签（清釉不模糊）；`.bubble-ai` = 纸上正文（16.5px、行距 1.95）。`.readout` 改为宋体 + 等宽数字。

## 7. 复刻对照表

「复刻」指结构与观感与画板一致（数值以设计源文件为准），不是换类名。每行的「保留」以 §4.2 为底线。

| 路由 / 组件 | 对应画板 | 必须复刻的结构 |
|---|---|---|
| 全局 `layout.tsx`、`globals.css` | Chat.dc 配方、Tokens.dc | §5 令牌与主题；字体；`LensDefs` 挂载；body 背景改为 `--paper` + 绢纹（不再是光斑）；去掉旧 HUD 装饰。 |
| `Sidebar.tsx` 桌面 | Chat.dc 左釉片左段 | 竖排书签导航：墨色双圆环品牌标；五项竖排文字（`writing-mode: vertical-rl`、15px、字距 .32em），当前项左侧 1.5px 墨线、字重 500；底部圆形「昼/夜」切换按钮（`aria-label` 按状态）；余额「200 / 草莓」两行（无 emoji，<30 时用朱色）。导航宽度改为 CSS 变量 `--nav-w`（按设计稿实际宽度），**替换 page.tsx 等处所有写死的 56px / left-14 / calc(100vw - 56px)**。独立页（Link 分支）与主页（回调分支）两种都要复刻；独立页时导航自身就是一条窄釉片（`Glaze panel`）。 |
| `Sidebar.tsx` 手机底栏 | ChatMobile.dc 底栏 | 纯文字五项（14px、字距 .2em），当前项上方 16×1.5px 墨线；高度改为 CSS 变量 `--tabbar-h`（+ safe-area），**替换所有写死的 `calc(56px+env(safe-area-inset-bottom))`**。非对话页时底栏自身是一片底部釉片。 |
| `app/page.tsx` 桌面骨架 | Chat.dc | 左侧一方悬浮釉片合并「竖排书签 + 对话目录」（视觉上一片，离屏边约 18px 悬浮，圆角按设计）；页头悬浮釉条；输入釉片悬浮；**消息层铺满对话区、可滚到页头与输入釉片之下**（滚动视口在玻璃之下，用内边距让出初始位置），消息层加 `mask-image` 渐隐：渐隐在页头下沿之后 8px 内走完（桌面 36→84px）；消息列居中（最大宽度按设计稿）。 |
| `app/page.tsx` 手机骨架 | ChatMobile.dc | 页头釉片（含远山线、补安全区）；底部输入釉片与导航底栏在视觉上是一整片釉（无缝、无双口沿）；消息层渐隐 54→102px（+safe-area）；生图模式下的模型选择为一行分段（「模型」标签 + 两个选项，选中项墨色细框）。 |
| 页头 | Chat.dc 页头 | `Seal agent` + 名字 18px/500 + 「AI 分身｜仅你可见」（中间细竖线，不用中点）；中间远山线（`Signal`）；右侧状态字「待命/正在听/正在说」+「朗读」「免提」细线框按钮；手机上余额两行。 |
| 消息 `ChatBubble.tsx` | Chat.dc 消息区 | 分身：上方 13px 淡墨名字（字距 .1em）+ 纸上正文，无气泡；用户：右对齐天青浮签（清釉、圆角按设计）；元信息行（时间、朗读、复制等）12px 淡墨文字按钮；日期分隔「十月六日」式居中带两侧细线。工具卡（天气/网页/生成状态等）= 清釉瓷片。`app/history/page.tsx:335-351` 手抄的同一套气泡要同步改。 |
| `GeneratedImage.tsx` | Chat.dc 装裱框 | 装裱：图外一圈纸面边（清釉着色 + 口沿，不模糊），下方「标题 / 模型名」一行；大图预览 dialog 的遮罩用 `--scrim`。三处复用（聊天、输入区 compact、历史页）都要成立。 |
| 输入区 | Chat.dc / ChatMobile.dc 输入釉片 | 文本框 16px；工具行：「上传参考图｜生成图片」文字按钮（中间细竖线）、修改图片/比例/模型等模式行沿用现有交互、语音图标按钮、「按住说话」、墨底「发送」（生图时为「生成」等现有文案）；**提示行「Enter 发送，Shift + Enter 换行 / 每条消息消耗 10 颗草莓」收进釉片底部**，上方 1px 刻线。现有「修改图片」「生成图片」只读 chip-on 仍是 span，不要做成像可点的样子。 |
| 对话目录 `ConversationPicker.tsx` | Chat.dc 左釉片右段 | 标题「对话」18px/500 字距 .18em；「历史」「新建」文字按钮；列表项标题 15px + 右侧时间 12px；当前项为清釉选中片（同心圆角）；底部「对话仅你可见 / 完整历史」。手机对话框外观同此。 |
| 当前对话记录抽屉、四个右侧抽屉、遮罩 | Chat.dc 材质 | 抽屉外壳 = `Glaze panel` 悬浮（离屏边留缝）；遮罩用 `--scrim`；去掉写死的 `rgba(0,0,0,0.28)` 阴影，改用 `--drop`。 |
| `MyAgentWorkspace.tsx`（/agents/me 与分身抽屉） | Agent.dc | 页头（回到对话、「分身」30px/500 字距 .24em、说明）；表单：头像符号框（墨线 ✦ 或用户符号）、名称下划线输入、简介/性格文本框（清釉瓷片输入框）、公开开关行；右栏名片预览（`AgentIdentityCard`）+ 说明 + 私有记忆。 |
| `AgentIdentityCard.tsx` | Agent.dc 名片 | 宋版书双边版框（外 1.5px 淡墨框 + 5px 间距 + 内 1px 细框），右上 `Seal agent`（微旋），「AI 分身」细线框标签，名字 46px/300，简介，底部细线 +「由用户创建的人工智能分身」。**删除 `.echo` 描边偏移字**（含 login 与父级 `[&_.echo]` 选择器）。 |
| `AgentExchangeWorkspace.tsx`（/agents 与广场抽屉） | Exchange.dc | 页头 +「刷新」；标签栏（当前项墨色下划线）；流程说明「分身写完整初稿 —— 官方搭档审稿 —— 按意见修订」（无序号）；官方搭档 = **一整片釉**内用竖向刻线分三栏（不是三张卡）；其余标签页（体验记录/发现分身/邀请/交流详情/作品）沿用同一语言：列表用刻线、卡片用清釉瓷片。记录表在 390/360 宽两行堆叠不变。 |
| `app/plaza/page.tsx`（世界，含 iframe 内嵌） | World.dc | `StarChart` 取代 `SolarSystem3D`（不再 import）；左右两列热点各为一整片釉（标题 + 刷新 + 1–4 排名 + 获取时间），星图外圈从釉片边缘下穿过；底部「我的兴趣」釉条；FAB 改为墨底「发布照片」按钮（保留上传流程）；帖子卡与点赞沿用新语言（去掉黑色写死遮罩与粉色发光，改令牌）。手机端按 `mobile:` 变体纵排。 |
| `app/match/page.tsx` | Chat.dc 材质 | 背景 `InkLandscape page` 取代 `Earth3D`（不再 import）；最近聊天列表、匹配卡、对话区用新语言（`.bubble-*` 已全局改）。styled-jsx 里绑 `.glass-card` 的初始透明度规则要随类名同步。 |
| `app/settings/page.tsx`（含 iframe 内嵌） | Settings.dc | 页头「设置」+「账号、外观与数据。」；内容在一整片釉上，分节（左 160px 节名 + 右内容），节间刻线；「外观」节：「跟随系统｜昼 天青｜夜 建盏」三档分段 + 一句说明 +「素瓷（减少透明度）」开关行与一句平实说明；数据管理（朱字危险操作）；关于。 |
| `app/profile/page.tsx` | Settings.dc 语言 | 同设置页语言。 |
| `app/login/page.tsx` | Main.dc | 左上 `Seal brand` 56px（微旋）；「Chloe」76px/300；「每个人自己的分身。」20px 字距 .16em；邀请码表单在一方釉片上（下划线输入、墨底「进入」、说明）；`InkLandscape login`（右下平远远山，尾脊从釉片后经过）；开发测试入口保留且 `NODE_ENV` 守卫原样；手机号/验证码两步沿用现有状态机与文案（同一语言）。 |
| `app/history/page.tsx` | Chat.dc 语言 | 顶栏与左侧日期导航用釉条/釉片；消息与主页一致；新标签页也跟随主题（§5.2）。 |
| `app/agents/[id]/page.tsx`、`app/community/page.tsx` | Agent.dc 语言 | 名片页用 `AgentIdentityCard`；社群页仅换令牌与语言。 |

## 8. 不允许的做法

- 只换颜色/类名、保留旧结构（例：消息仍不能滚到玻璃下；导航仍是图标 + 小字；名片仍是 echo 描边字）。
- 在消息、浮签、卡片、装裱、广场卡片上加 backdrop-filter；嵌套 backdrop。
- 页面上出现两方以上朱印；把导航品牌标做成红色。
- 廉价渐变色块、发光、emoji 装饰（🍓、默认 ✨ 头像改由 Seal 画 ✦）、祥云/窗棂/毛笔字等宋风俗套纹样。
- 中点分隔（「A · B」）作为新写的界面文案分隔（保留既有必须原样的文案，如「平台官方 AI · 无真人用户」）。
- 改写 §4.2 的任何保留项；删文件；改依赖；改后端；改 `next.config.ts`；提交 commit。
- 用 `max-md:` 写会被 iframe 内嵌的页面。

## 9. Codex 执行任务清单（按顺序）

1. 读 `01-frontend-map.md`、`design/source/Chat.dc.html`（先读开头配方注释与 THEMES）、`Tokens.dc.html`、Next 16 相关文档。
2. §5 令牌、主题首帧脚本、`useTheme`、`color-scheme`、themeColor/manifest；字体引入；`proxy.ts` matcher 加 `fonts`。
3. §6 共享组件：`Glaze`、`LensDefs`、`InkLandscape`、`StarChart`、`Seal`、改写 `Signal`；重绘 `.btn/.chip/.tag/.bubble-*/.readout`。
4. `Sidebar` 桌面竖排书签 + 手机文字底栏；引入 `--nav-w`、`--tabbar-h` 并替换全部写死尺寸。
5. 对话主页（桌面 + 手机），含消息层结构调整与渐隐、输入釉片、页头、对话目录、抽屉与遮罩。
6. 消息与卡片组件（ChatBubble、GeneratedImage、工具卡、历史页手抄气泡）。
7. 分身（MyAgentWorkspace、AgentIdentityCard、AgentMemoryPanel、/agents/[id]）。
8. 广场（AgentExchangeWorkspace 全部标签与详情）。
9. 世界（plaza + StarChart）与匹配（match）。
10. 设置（含外观三档 + 素瓷）、profile、login、history、community。
11. 文档：在 `README.md` 前端相关段落补一句——字体为自托管思源宋体（`public/fonts/noto-serif-sc`，OFL）、外观可选跟随系统/昼/夜与素瓷；`frontend/AGENTS.md`、`CLAUDE.md` 不需要改。
12. 自检：§10 全部命令；能跑浏览器的话，按 `design/shots/` 对照截图自查（可选）。

可以用多个子代理并行（按文件不重叠分工，同一文件交同一子代理）；派子代理时不要传 model 和 reasoning_effort 参数。

**何时停下来问**：只有遇到「做哪个实现会影响产品行为或违反 §4.2」的分歧才停下并写进总结；只影响「怎么验证」或实现细节的，自己定并说明。任何情况下不要回滚已完成的工作。

## 10. 验收标准（全部可执行，Claude 会逐条复跑）

在 `frontend/` 下执行：

1. `npx tsc --noEmit` → 退出码 0。
2. `npm run lint` → 0 errors，warnings ≤ 25。
3. `npm run build` → 成功。
4. 结构判据（`grep -rF -- '<模式>' app components lib | wc -l`）：
   - 必须为 0：`#F2A63A`、`#9E6209`、`#0E1219`、`SolarSystem3D`（app/ 下的 import 与使用）、`Earth3D`（app/ 下）、`className="dark`（layout）、`bg-black/`、`rgba(0,0,0,0.28)`、`🍓`、`font-mono`、`echo`（作为类名或选择器，含 `.echo`、`[&_.echo]`、`className="echo`）、`--grain`、`--spot-`、`fonts.googleapis`、`glass-card`（旧类名全部换成新语言后为 0）。
   - 必须 ≥ 1：`<Glaze`（至少出现在 page.tsx、Sidebar.tsx、settings、plaza）、`<InkLandscape`、`<StarChart`（plaza）、`<Seal`（login、AgentIdentityCard、page.tsx 页头）、`<LensDefs`（layout）、`noto-serif-sc.css` 的引入、`chloe-appearance`、`chloe-solid`、`prefers-reduced-transparency`、`prefers-contrast`、`--nav-w`、`--tabbar-h`、`mask-image`（page.tsx 消息层）。
   - `proxy.ts` 的 matcher 排除列表包含 `fonts`。
5. 保留项计数（同上 grep，基线为 586d86a）：
   - 恰好等于基线：`data-chat-panel` 1、`data-chat-composer` 1、`data-chat-scroll-area` 1、`data-chat-scroll-viewport` 1、`data-chat-scroll-content` 1、`plaza-drawer` 2、`settings-drawer` 2、`conversation-picker-dialog` 2、`data-agent-exchange-workspace` 1、`data-official-agent` 1、`data-exchange-id` 1、`data-exchange-detail` 1、`data-exchange-message` 1、`data-exchange-artifact` 1。
   - 不少于基线：`agent-drawer` 4、`exchange-drawer` 4、`aria-controls` 4、`aria-label=` 50、`aria-modal` 1、`inert` 2、`composerRef` 3、`textareaRef` 4、`primeTtsAudio` 10；文案「以此图修改」2、「加入参考」2、「已选为图」2、「AI 分身」11、「由用户创建的人工智能分身」1、「官方 AI」6、「无真人用户」2、「AI 生成」3、「不代表真人即时发言」1、「名片始终标明」1、「每个账号每天」1、「不读取性格设定」1、「仅你可见」4、「每条消息消耗」3。
6. 字体资源未被改动：`shasum -a 256 public/fonts/noto-serif-sc/* app/fonts/noto-serif-sc.css` 与派单时记录的清单一致（Claude 持有清单）。
7. 除 `README.md` 外不改其他文档；`git diff --stat main` 中不出现 `package.json`、`package-lock.json`、`next.config.ts`、`components/ui/`、`backend/`，也没有被删除的文件。
8. 视觉（Claude 在隔离环境实机截图验收，Codex 无需自证）：昼/夜/素瓷 × 桌面 1440×900 / 1920×1080 / 手机 390×844、360×740，对照 `design/shots/`；正文对比度 ≥ 4.5:1，次要文字 ≥ 3:1；昼夜切换、跟随系统、素瓷开关、iframe 抽屉同步、刷新后保持均正确；首帧无主题闪烁。

## 11. 交付：变更总结（Codex 完成后输出）

必须包含：1. 修改/新增了哪些文件；2. 实现了哪些功能；3. 与 §9 任务清单、§7 对照表逐行的对应关系；4. §10 第 1–7 条的实际运行结果（命令与输出摘要）；5. 未完成或需要人工确认的地方（含你主动偏离设计稿的地方与理由）。
