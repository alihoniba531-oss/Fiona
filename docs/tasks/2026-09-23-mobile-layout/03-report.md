# 手机宽度响应式布局实现报告

日期：2026-09-23

## 修改文件

本任务共修改 18 个前端文件，均在规格第 2 节白名单内；没有修改依赖、接口或业务逻辑。

| 分组 | 文件 | 主要改动 |
| --- | --- | --- |
| 对话与导航 | `frontend/app/page.tsx`、`frontend/components/Sidebar.tsx`、`frontend/components/ConversationPicker.tsx`、`frontend/components/ChatScrollArea.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/GeneratedImage.tsx` | 手机底栏、会话覆盖层、两行头部、消息和输入区、图片触控区、四个抽屉 |
| 分身与广场 | `frontend/components/AgentExchangeWorkspace.tsx`、`frontend/components/MyAgentWorkspace.tsx`、`frontend/app/agents/[id]/page.tsx` | 分类横滑、记录两行、分身表单与名片单列、底栏留白 |
| 世界与匹配 | `frontend/app/plaza/page.tsx`、`frontend/app/match/page.tsx` | 热点卡正常流、帖子单列、兴趣条和浮动按钮避让、匹配卡和聊天适配 |
| 其他页面与全局 | `frontend/app/settings/page.tsx`、`frontend/app/profile/page.tsx`、`frontend/app/history/page.tsx`、`frontend/app/login/page.tsx`、`frontend/app/community/page.tsx`、`frontend/app/layout.tsx`、`frontend/app/globals.css` | 页面宽度与内边距、历史筛选排布、视口缩放与安全区、手机输入字号 |

## 功能与规格对应

### T1 应用外壳

1. `Sidebar` 在 `<768px` 渲染固定、等宽五入口的 `glass` 底部 `<nav aria-label="主导航">`，高度为 `56px + env(safe-area-inset-bottom)`，顶部用 `--glass-border` 分隔。图标为 20px、文字为 10px，沿用桌面的激活规则和按钮／链接行为；抽屉按钮保留 `aria-expanded`、`aria-controls`。
2. 手机底栏不显示 Logo、草莓余额或主题切换。草莓余额移到对话头部，沿用原有 `<30`、`<100` 的颜色阈值；头部复用 `Sidebar` 的余额轮询结果，没有新增第二次轮询。
3. 主题切换移到手机会话列表覆盖层底栏。
4. 所有原本渲染 `Sidebar` 的独立页面及其内容滚动区，都为底栏和安全区留出空间；嵌入抽屉的页面由抽屉边界避让，不重复留白。
5. 首页根容器改为 `h-dvh`；其他全屏页面在窄屏使用动态视口高度。桌面 `h-screen` 的替换仅发生在规格允许的等价场景。

### T2 对话页

1. 手机会话列表改为左侧 `min(85vw, 320px)` 的 `glass` 覆盖层和半透明遮罩，顶部按钮打开。选择、新建、点遮罩和 Escape 都会关闭；打开时焦点移入列表，按关闭原因恢复焦点；覆盖层带 `role="dialog"`、`aria-modal="true"`、`aria-label="对话列表"`。删除按钮在触屏常显。
2. 手机头部为 56px 操作行和 24px `Signal` 行；分身名截断，状态只显示点，朗读与免提只显示图标且保留标签、标题及激活态。消息滚动区顶部按 80px 留白。
3. 消息区手机内边距 16px；用户消息至少占 240px 可用宽度，分身消息随内容区伸展，图片和卡片限制在内容宽度内。
4. 输入区手机左右内边距 12px，底边停在底栏上沿；保留动态 `composerHeight` 测量。隐藏 Enter 提示，保留草莓消耗提示；按住说话仅显示图标并保留 `aria-label`；发送、附图、语音、参考图和图片预览操作目标在手机为至少 40×40px；textarea 为 16px。
5. 「当前对话记录」滑层手机从左边缘打开，宽 `min(85vw, 320px)`，底边停在底栏上沿；底栏切换时收起。
6. 分身、广场、世界、设置四抽屉在手机从左边缘占满视口宽度，底边停在底栏上沿，关闭态退出手机键盘焦点流。保留原有桌面内联定位与宽度值。

### T3 内容页

1. `/agents` 的分类标签单行横滑并隐藏滚动条；体验记录和邀请记录在手机改为「话题」加「搭档 · 状态 · 次数 · 时间」两行，隐藏桌面表头；手机内边距改为 16px。
2. `/agents/me`、`/agents/[id]` 及分身管理内容在手机采用 16px 内边距、单列表单与预览，并约束长名称。
3. `/plaza`（含嵌入模式）的热点卡改为正常流、全宽单列，帖子也单列；兴趣条进入正常流，浮动发布按钮和话题展开层避开底栏。
4. `/match`（含嵌入模式）将最近聊天改为横向列表、匹配卡改为顺序流、气泡上限改为 `80vw`，并约束长标签；`/settings`、`/profile`、`/history`、`/login`、`/community` 改为适合 360px 与 390px 的宽度及内边距。历史页筛选区上下排布、日期横滑，消息气泡上限为 `85vw`。`/` 的消息、输入和抽屉按 T2 适配。

### T4 视口与可访问性

1. `viewport` 保留原 `themeColor`，移除 `maximumScale` 和 `userScalable: false`，增加 `viewportFit: "cover"`。
2. 全局 CSS 只在 `<768px` 对 `input`、`textarea`、`select` 设定最小 16px 字号；登录、对话和匹配的主要输入也有明确的手机字号类。
3. 新增覆盖层动画沿用现有动画类；现有 `prefers-reduced-motion: reduce` 全局规则会关闭动画并压缩过渡时长。

## 检查结果

在 `frontend/` 下执行：

| 命令 | 结果 |
| --- | --- |
| `npx tsc --noEmit` | 通过，退出码 0 |
| `npm run lint` | 通过，0 error、28 warning，等于规格基线及上限 |
| `npm run build` | 当前沙箱中未完成：Turbopack 在处理 `app/globals.css` 时尝试创建内部进程并绑定端口，收到 `Operation not permitted (os error 1)` |
| `npm run build -- --webpack` | 通过，退出码 0；编译、TypeScript、14/14 静态页面生成及构建追踪完成 |

Webpack 构建产物中已确认手机 `position: static/fixed !important` 和安全区底边类实际生成。没有启动前后端服务，也没有做浏览器截图。

## 未完成与人工确认

- 按任务约束未进行浏览器验证。需由 Claude 在 `390×844`、`360×740` 验证 T3 所列路由无横向滚动、消息与输入区位置、底栏及抽屉交互，并在 `1440×900`、`1024×768` 比对桌面截图。
- 标准 Turbopack 构建需在允许其内部进程绑定端口的环境重跑；此处的失败发生在沙箱权限层，Webpack 生产构建已通过。未改动 `package.json` 或 `next.config.ts`。
- 手机次要信息取舍：对话头部隐藏「AI 分身／仅你可见」副行和状态文字，历史日期改为横滑，匹配联系人改为横滑，世界热点与帖子改为先后纵向浏览；功能入口仍保留。
- 本任务开始前，另一并行任务已修改 `backend/**`、根目录及其他 `docs/**` 文件，且仍在继续；本任务没有触碰、回滚或格式化它们。因此仓库整体 `git status` 包含白名单外的并行改动，不能把该状态归因于本任务。

## 机械返修 M1

本轮修改了 `frontend/app/layout.tsx`、`frontend/app/globals.css`、`frontend/app/plaza/page.tsx`、`frontend/app/match/page.tsx`、`frontend/app/settings/page.tsx`、`frontend/app/profile/page.tsx`、`frontend/app/community/page.tsx`，均在规格第 2 节白名单内。

- 在布局的 `<head>` 中加入同步内联脚本：仅当页面以 `?embed=1` 内嵌时读取父窗口的 768px 媒体查询。父窗口宽度 ≥768px 时，首帧前给 iframe 的 `<html>` 标记 `data-shell="desktop"`；跨越断点时用媒体查询的 `change` 事件更新标记，无需重载 iframe。独立打开的页面仍按自身宽度布局。
- 定义带 `data-shell` 门控的 Tailwind `mobile:` 变体，将世界、匹配、设置、画像及同样支持嵌入的社区页新增窄屏样式改用该变体。世界页 640–767px 的帖子网格仍强制单列。全局手机输入最小 16px 字号和 `.mobile-scrollbar-none` 规则也加上相同门控。四个实际 iframe 入口为 `/plaza?embed=1`、`/match?embed=1`、`/settings?embed=1`、`/profile?embed=1`；其嵌入模式渲染的共享组件没有需要额外切换的窄屏规则。
- 构建产物检查：59 条生成的 `mobile:` 规则均带父窗口桌面标记门控；预渲染 HTML 中同步脚本位于 `<head>`，早于 `<body>`。`git diff --check` 通过。

在 `frontend/` 下验证：`npx tsc --noEmit` 通过；`npm run lint` 为 0 error、28 warning（等于规格上限）；默认 `npm run build` 因沙箱禁止 Turbopack 内部进程绑定端口而失败；`npm run build -- --webpack` 通过，14/14 静态页面生成完成，修正后的 CSS 优化无规则错误。

未启动服务、未截图。仍需由 Claude 在 800×900、1024×768 的世界与设置抽屉及 390×844、360×740 的手机页面做浏览器视觉确认，包括首次打开 iframe 和父窗口跨越 768px 时的切换。当前沙箱无法验证 Turbopack 构建；需在允许内部端口绑定的环境重跑。

## 复核返修第 1 轮

本轮修改 `frontend/app/page.tsx`、`frontend/app/plaza/page.tsx`、`frontend/app/layout.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/Sidebar.tsx`、`frontend/components/ConversationPicker.tsx`、`frontend/components/AgentExchangeWorkspace.tsx`，新增 `frontend/lib/useTheme.ts`。均属于规格第 2 节白名单；M1 的内嵌页 `mobile:` 门控与同步首帧标记继续保留。

| 项目 | 本轮处理 |
| --- | --- |
| R1 | 独立 `/plaza` 的窄屏发布弹窗外层底边设为 `calc(56px + env(safe-area-inset-bottom))`，用 `!important` 覆盖 `inset-0`；内层最大高度扣除相同的底栏高度及原有两侧 16px 间距。嵌入模式保留原最大高度和弹窗位置。构建产物确认这两条 `mobile:` CSS 均已生成且受 M1 标记门控。 |
| R2 | 删除桌面「朗读」按钮新增的 `title`，保留图标态可访问名称 `aria-label="朗读"`；原有免提 `title` 不变。 |
| O1 | 去掉用户短消息气泡的 240px 最小宽度，保留内容区内最大宽度限制。 |
| O2 | 会话覆盖层监听 768px 断点；跨到桌面立即关闭、清理键盘和媒体监听，不在回到手机宽度时自行重开；注册监听后也检查一次当前断点，避免错过切换。 |
| O3 | `Sidebar` 与 `ConversationPicker` 共用 `useTheme`，从 `<html>` 的 `dark` class 读取并订阅主题，跨断点后按钮图标与文案同步。 |
| O4 | 对话页 JS 窄屏判断统一使用 `matchMedia("(width < 768px)")`，与 CSS 的严格小于 768px 一致。 |
| O5 | M1 首帧脚本的父窗口媒体查询监听在缺少 `addEventListener` 时回退 `addListener`；`pagehide` 时移除监听；异常分支保留已正确设置的 `data-shell="desktop"`。 |
| O6 | `Sidebar` 余额轮询 effect 恢复空依赖，`onBalanceChange` 经 ref 读取最新回调，避免回调身份变化重启轮询。 |
| O7 | 附图按钮移除固定 `aria-label`，恢复由原有状态化 `title` 提供桌面读屏名称；其余核对过的按钮保持原名称。 |
| O8 | 头部「对话列表」按钮仅在覆盖层实际挂载时设置 `aria-controls`。 |
| O9 | 四个抽屉的关闭按钮在窄屏增加 40×40px 触控区域，桌面尺寸不变。 |
| O10 | 从会话覆盖层打开「当前对话记录」时，停止旧覆盖层回焦、改为聚焦记录面板关闭按钮；窄屏 Escape 可关闭，关闭后焦点回到头部列表按钮；切换导航时避免误回焦。 |
| O11 | 广场分类标签溢出且右侧仍有内容时显示使用现有令牌的箭头提示，横向滚到末端后隐藏；桌面不显示。 |
| O12 | 独立 `/plaza` 的窄屏滚动内容区增加 80px 底部留白，使最后一张卡片滚到底时避开固定发布按钮；嵌入模式与桌面不变。 |

在 `frontend/` 下验证：`npx tsc --noEmit` 通过；`npm run lint` 为 0 error、28 warning（未超过基线）；默认 `npm run build` 仍因沙箱禁止 Turbopack 内部进程绑定端口而失败；`npm run build -- --webpack` 通过，14/14 静态页面生成完成。`git diff --check` 通过。构建产物同时确认 R1 底边与最大高度类、O12 留白类均带 M1 的 `data-shell` 门控，内联同步脚本仍在 `<head>`、早于 `<body>`。

本轮未启动服务、未截图。R1 的 360×740、375×667、360×640 发布按钮命中测试，以及 R1/R2/O1–O12 的浏览器交互与桌面像素复核，仍由 Claude 按返修单执行；默认 Turbopack 构建需在允许内部端口绑定的环境重跑。O13、O14 按返修单未处理。其他任务的 `backend/**`、根目录和其他 `docs/**` 改动未触碰或回滚。
