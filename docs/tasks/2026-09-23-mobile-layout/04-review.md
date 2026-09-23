# 复核报告：手机宽度可用（响应式布局）

日期：2026-09-23　基线：`main` @ `54a9b57`　复核对象：`git diff -- frontend`（19 个文件，+403/−201）
复核方式：三个独立视角（桌面零变化 + M1 / 窄屏体验与可访问性 / 功能回归与逻辑）各自通读规格与 diff、核对机械验证截图、用无头 Chromium 交互复查；复核总结人对每条 must_fix 亲自复现（脚本与产物：`scratchpad/reviewB/final/verify_final.py`、`verify_final.json`、`plaza_modal_*.png`）。

## 结论：不通过

两条必须修复项（R1 独立 `/plaza` 发布弹窗被底栏遮住、R2 桌面「朗读」按钮新增原生提示）。两条修复都很小、只碰各自一处，不影响已通过的其它判据。

## 验收标准逐条核验

| # | 标准 | 结果 | 证据 |
| --- | --- | --- | --- |
| 5.1 | `npx tsc --noEmit` 退出码 0 | pass | 总结人在 `frontend/` 重跑：`TSC_EXIT=0`（`reviewB/final/tsc.log`）；视角一同样得到 0 |
| 5.2 | `npm run lint` 0 error，warning ≤ 28 | pass | 总结人重跑：`✖ 28 problems (0 errors, 28 warnings)`，退出码 0（`reviewB/final/lint.log`），等于基线上限 |
| 5.3 | `npm run build` 成功 | pass（附注） | 为不干扰正在运行的 dev 服务（占用 `.next`），总结人把 `app/components/lib/public/配置` 复制到 scratchpad 并软链 `node_modules` 后构建：Turbopack 拒绝跨文件系统根的软链（`Symlink [project]/node_modules is invalid`，环境限制，与代码无关），`npx next build --webpack` 退出码 0、14/14 静态页面生成（`reviewB/final/build_webpack.log`）。机械验证在 M1 前已记录默认 Turbopack 构建成功（`05-fix-mechanical.md`）；M1 只加了 `@custom-variant` 与内联脚本。**合并前请在真实 `frontend/` 下再跑一次默认 `npm run build` 作为最终门禁** |
| 5.4a | 390×844 / 360×740 下 T3 全部路由 `scrollWidth <= innerWidth`，标签/导航单行 | pass | `vis/shots/m_r1/results.json`：全部 `390_route/*`、`360_route/*`（含 `?embed=1`）`sw == iw`、`wrapped: []`；视角二复查 `/agents` tablist 单行（`scrollbar-width: none`）、`/history` 筛选 4 列不溢出、`/plaza` 7 张热点卡宽 358/328 无重叠 |
| 5.4b | 390×844 首页：气泡 ≥ 240px；输入区下沿 ≤ 标签栏上沿；开列表→选会话→自动关闭且消息切换；底栏四入口开抽屉且底栏仍可见 | pass | `results.json`：`390_home_msg` 内容列 358、`composerBottom 788 == navTop 788`；`390_picker_after_select.open=false`、`390_picker_after_new=false`；`390_drawer_*` 四抽屉 `w=390, left=0, bottom=788, navVisible=true`；视角二实测 AI 气泡 322px、用户气泡 240px（后者靠 `min-w` 硬凑，见 O1） |
| 5.4c | 1440×900 与 1024×768 下首页、四抽屉、`/agents/me`、`/agents`、`/plaza` 与改动前视觉一致 | pass（视觉）/ 见 R2（非视觉） | `vis/shots/diff/` 逐像素差异只剩会话时间戳、热点文字与 3D 太阳系动画（总结人复看 `diff/1024_drawer_世界.png`：仅散点星空与卡片角上的时间读数）；独立 `/plaza` 桌面未单独截图，但其改动全部是 `mobile:` 变体（`@media (width < 48rem)` 门控），≥768px 惰性，按代码判定一致。非像素层面：`page.tsx:1671` 给「朗读」按钮新增 `title="朗读"`，桌面悬停出现改动前不存在的原生提示（R2） |
| 5.5 | `git status` 中每个路径在白名单内 | pass | `git status --porcelain --untracked-files=all -- frontend`：全部在 `frontend/app/**`、`frontend/components/**`；唯一例外 `frontend/AGENTS.md` 是 `next dev` 自动改写（内容自述），规格已声明由 Claude 还原（O14） |
| M1 | 内嵌页按父窗口断点渲染；跨 768 切换不刷新；首帧不闪；覆盖全部 `embed=1` 入口与全局 `@media` 规则 | pass | `layout.tsx:29-46` head 内同步脚本，SSR HTML 中位于 `</head>` 前，MutationObserver 证实 `data-shell` 设置时 `document.body === null`（首帧前）；`globals.css:6-13` `mobile` 变体 + `:415-431` 两段全局规则均带 `:root:not([data-shell=desktop])` 门控；全库 `embed=1` 只有 `page.tsx:1919/1952` 两个 iframe（plaza/match/settings/profile），五个可嵌入页与 Earth3D/SolarSystem3D 中 grep 不到 `max-md`；1280/1024/900/800 世界抽屉 iframe `shell=desktop`、热点列 `absolute`、卡片 220px（`vis/shots/800_world.png`、`reviewB/1024_world.png`）；父窗口 1440→700→1024 拉伸，iframe 内 `data-shell` 在 desktop/null 间切换且未重载；767/768 边界正确；`diff/1024_drawer_世界.png`、`diff/1024_drawer_设置.png` 仅动态内容 |

规格 T1–T4 的逐项核验（三视角合并，均 pass，仅列证据要点）：

- **T1** 底栏 `<nav aria-label="主导航">` fixed、z-70、56px + 安全区、`glass` + 顶部 1px `--glass-border`、五个 78×56/72×56 等分按钮、激活规则与桌面 `Sidebar.tsx:83-146` 逐条一致、`aria-controls` 指向的四个 id 均存在（`plaza-drawer`/`settings-drawer` 为新增）；底栏无 Logo/余额/主题；余额移到头部（`page.tsx:1685-1693`，阈值与 `Sidebar.tsx:150-163` 一致），轮询仍只在 `Sidebar` 一处并通过稳定的 `setStrawberryBalance` 回传（fetch 打桩：挂载 2 次为 StrictMode 双挂载，重渲染不再请求）；主题切换在会话覆盖层底栏（桌面 `display:none`）；所有独立页底部留白到位（`/agents/me`、`/plaza` 滚到底最后元素 bottom == navTop）；根容器 `h-dvh`。
- **T2** 覆盖层 `min(85vw,320px)`、顶 0、底 == navTop、`role=dialog aria-modal aria-label`、焦点移入/陷阱/Escape/遮罩/选中/新建关闭后焦点回到触发按钮（全部实测 true）、删除按钮 40×40 常显；两行头部 56+24、分身名截断、状态只留点、朗读/免提图标态；滚动区 `padding-top 80 == headerBottom`，首条消息 top 96；消息区 px 16、图片 `max-w-full`；输入区 px 12、`footer.bottom == navTop`、textarea 16px、六个按钮高 40、Enter 提示隐藏草莓行保留、`--composer-height` 变量持续更新（`padding-bottom 257 = composerHeight + 56`）；「当前对话记录」滑层 left 0、宽 320/306、底 == navTop；四抽屉 100vw、左起、底 == navTop，开抽屉时五个底栏中心点 `elementFromPoint` 全命中。
- **T3** 见 5.4a；体验记录两行布局（`AgentExchangeWorkspace.tsx:95-118`）因隔离库无交流记录只做代码核对（桌面单元格 `max-md:hidden`，窄屏行含搭档/状态/次数/时间并带 sr-only 标签，整行仍是 `<button onClick={setSelected}>`）。
- **T4** `meta[name=viewport]` = `width=device-width, initial-scale=1, viewport-fit=cover`，`themeColor` 保留；`globals.css:415-420` 输入类 `font-size: max(16px, 1em)`，`/login`、`/history`、`/agents/me`、首页 textarea 实测 16px；reduced-motion 上下文中对话框 `animation-name: none`、遮罩/抽屉 `transition-duration 1e-05s`、Signal 退化为直线（`globals.css:460-468` 全局规则覆盖 `tw-animate-css`）。

## 必须修复项

### R1 独立 `/plaza` 的「发布到世界」弹窗被底部标签栏遮住，小屏手机上「发布」按钮点不到（点到会切走页面）

- **问题**：`frontend/app/plaza/page.tsx:585` 弹窗外层 `fixed inset-0 z-50` 在整个视口居中，`:586` 内层只扣了 `mobile:max-h-[calc(100dvh-2rem)]`，没有扣底部标签栏（56px + 安全区，`Sidebar.tsx:182` `z-[70]`）。弹窗 z-50 低于底栏 z-70，所以底栏盖在弹窗上，且遮罩没有盖住底栏。被遮住的是弹窗盒子自身的底边，内层 `overflow-y-auto` 滚到底也露不出来。
- **证据**（总结人亲自复现，`reviewB/final/verify_final.json`，均为独立打开 `/plaza`、点 FAB 注入图片后测量，弹窗已滚到底）：
  - 360×740（规格尺寸）：弹窗 bottom 707.5 > navTop 684（被遮 23.5px）；「发布」按钮 650.5–690.5，下沿被遮 6.5px，按钮下缘 2px 处 `elementFromPoint` 命中底栏（`bottomHitIsNav: true`）。截图 `reviewB/final/plaza_modal_360x740.png`：按钮下半截被底栏切掉，弹窗底边不可见。
  - 375×667（iPhone SE/8）：弹窗 bottom 651 > navTop 611（被遮 40px）；「发布」按钮 594–634，被遮 23px，**中心点 `elementFromPoint` 命中的是底栏的「广场」链接**（`centerHitTag: "A|广场"`）。截图 `reviewB/x_375x667_plaza_modal.png`：整个「发布」按钮不可见。
  - 360×640（常见安卓）：同 375×667，按钮中心命中「广场」链接。
  - 390×844：不受影响（弹窗 774.5 < 788）。嵌入模式（世界抽屉 iframe）不受影响（`embed_modal.pubBottom 706.5 < 743`）。
  - 视角二（`reviewB/extra.json`）与视角三（`reviewB/shots/results.json B_modal`）各自独立测得同样数值。
- **失败场景**：用户在手机上直接打开 `/plaza`（或 PWA 从独立页进入），点右下角 `+` 选好图片，在 375×667 / 360×640 的手机上找不到「发布」按钮；凭直觉去点弹窗最底部时，实际点中的是底栏「广场」，页面跳走、已选图片丢失，发帖流程无法完成。在规格要求的 360×740 上按钮下沿被切、弹窗底边不可见。违反规格 T1.5「确保最后一屏内容与浮动按钮不被遮挡」与 T3「主要按钮可点」的意图。
- **修复要求**：非嵌入窄屏下让弹窗层停在标签栏上沿，内层最大高度同样扣掉标签栏；嵌入模式保持现值；桌面（`mobile:` 变体惰性）零变化。修完在 360×740、375×667、360×640 复测：弹窗 bottom ≤ navTop，「发布」按钮中心与下缘 −2px 的 `elementFromPoint` 均命中按钮本身。

### R2 「朗读」按钮新增 `title="朗读"`，桌面悬停出现改动前不存在的原生提示

- **问题**：`frontend/app/page.tsx:1671` `onClick={() => setVoiceOn(!voiceOn)} aria-label="朗读" title="朗读"`。基线（`git show HEAD:frontend/app/page.tsx:1605`）该按钮只有 `className` 与 `onClick`，没有 `title`。`title` 不带断点条件，桌面同样生效。规格 T2.2 说的是「保留 `aria-label`/`title`」，即保留原有的，并没有要求给没有 `title` 的按钮新增。
- **证据**：总结人在 1024×768 与 1440×900 实测 `button[aria-label="朗读"]` 可见、文本「朗读」、`title="朗读"`（`reviewB/final/verify_final.json desktop_*`）；视角一、二各自在 1280/1024/900/800 得到同样结果。对照：免提按钮基线本就有 `title`，不受影响。像素比对抓不到 hover 态，所以机械验证未发现。
- **失败场景**：≥768px 桌面用户把鼠标停在头部「朗读」chip 上约 1 秒，弹出新的系统 tooltip「朗读」。这是规格第 2 节「≥ 768px 时…交互不得有任何变化」之外的桌面行为，且桌面端已由产品负责人验收。
- **修复要求**：删除 `title="朗读"`，只保留 `aria-label="朗读"`（窄屏图标态的可访问名称由 `aria-label` 提供即可）。一处一词，不影响其它判据。

## 可优化项

（三视角合并去重；不作为通过条件，由用户决定是否纳入本轮或后续任务。）

- **O1 用户气泡窄屏被强制 `min-width` 240px，短消息变成大空框**。`components/ChatBubble.tsx:215` `max-md:min-w-[min(240px,calc(100vw-32px))]`。实测发「好」：气泡 240px 宽、文字挂在最左（`reviewB/390x844_short_msg.png`、`reviewB/shots/A4_short.png`）。这是为机械满足「气泡 ≥ 240px」，而规格 T2.3 要的是「随屏幕自适应」。建议去掉 `max-md:min-w-*`，只保留 `max-md:max-w-full`；验收改为用 ≥30 字的消息测量或测内容列宽（已是 358）。
- **O2 会话覆盖层打开时视口跨到 ≥768，状态残留并吞掉一次 Escape**。`page.tsx:259-284` 焦点陷阱 effect 只依赖 `conversationPickerOpen`；覆盖层用 `md:hidden` 隐藏而非关闭。实测 744→1024：dialog 仍在 DOM（`display:none`）、触发按钮 `aria-expanded` 仍 true、document keydown 监听仍在（Escape 被 `preventDefault`）；回到 744 时列表未经操作重新出现。建议在同一 effect 里监听 `matchMedia('(min-width: 768px)')` 的 change，命中时 `setConversationPickerOpen(false)` 并置 `restoreConversationFocusRef=false`。
- **O3 `Sidebar` 与 `ConversationPicker` 各自维护 `dark` 状态，跨断点后失步**。`Sidebar.tsx:46` `useState(true)` 从不读 class，`ConversationPicker.tsx:40` 每次挂载读取 class。实测桌面切浅色→缩到 390 在覆盖层切回深色→放回 1440：`html.dark=true` 而 Sidebar 标题仍「切换深色」。建议 Sidebar 改为同样的惰性读取，或把主题抽成共享 hook。
- **O4 JS 断点 `(max-width: 767px)` 与 CSS 断点 `width < 48rem` 在非整数视口宽度下不一致**。`page.tsx:234`。浏览器缩放到 110%/125% 时 `innerWidth` 可能是 767.27：CSS 按窄屏渲染，JS 判为桌面，底栏切抽屉时「当前对话记录」滑层不会被收起。建议改为 `window.matchMedia("(width < 768px)")`。
- **O5 `layout.tsx` 内联脚本两处健壮性**。（a）`:41` 挂在父窗口 MediaQueryList 上的 `change` 监听没有 `pagehide` 清理，iframe 换 `src`（热点↔匹配、设置↔账户）时旧文档的监听器和闭包留在父窗口（视角一用 WeakRef + GC 做对照未能归因证实，按代码推断）；建议补 `window.addEventListener("pagehide", () => parentBreakpoint.removeEventListener("change", syncShell), { once: true })`。（b）`:31-45` `syncShell()` 之后 `addEventListener` 若在老 Safari（`MediaQueryList` 只有 `addListener`）抛错，`catch` 会 `removeAttribute("data-shell")` 把刚设的桌面标记删掉，768–1208px 桌面窗口的抽屉 iframe 会按手机布局渲染；建议把 `addEventListener` 单独 try/catch 并回退 `addListener`，或 catch 里不要删属性。
- **O6 `Sidebar` 轮询 effect 依赖 `[onBalanceChange]`**（`Sidebar.tsx:74`）。当前传入的是稳定的 `setStrawberryBalance`，实测不重订阅；但日后任何调用方传内联箭头函数就会每次渲染清定时器并立即再拉一次 `/strawberry`。建议回调放进 `useRef` 后依赖恢复为 `[]`。
- **O7 桌面读屏名称的非视觉变化**。`page.tsx:1791` 附图按钮新增固定 `aria-label="附图"`，桌面读屏听到的名称从随状态变化的 `title`（「发送看图聊天附件」等）变为「附图」，原 `title` 退化为描述；另有若干桌面也渲染的元素新增了 `aria-label`（免提/语音转文字/按住说话与可见文本相同，无名称变化）。功能无影响；若要严格零变化可不加 `aria-label`，否则在报告里注明即可。
- **O8 对话列表触发按钮的 `aria-controls` 在关闭态指向不存在的 id**。`page.tsx:1654` 常驻 `aria-controls="conversation-picker-dialog"`，而 `:1642` 的 dialog 只在打开时挂载（实测关闭态 `getElementById` 为 null）。axe 会标记；建议 `aria-controls={conversationPickerOpen ? "conversation-picker-dialog" : undefined}`。
- **O9 触控目标口径不一致**。四个抽屉头部关闭 X 在窄屏仍 24×24（`page.tsx:1853/1884/1908-1913/1941-1946` `h-6 w-6` 无 `max-md` 变体），朗读/免提 chip 36×36（`:1670/1676`）。规格只对输入区明确要求 40×40，不违规；建议关闭按钮加 `max-md:h-10 max-md:w-10`。
- **O10 从会话覆盖层打开「当前对话记录」后，焦点回到被遮罩盖住的触发按钮**。`page.tsx:1554` onHistory 先关覆盖层再开 showHistory，清理逻辑（`:1532-1535`）按 `restoreConversationFocusRef=true` 把焦点还给「对话列表」按钮，而它此时在 z-40 遮罩之下（实测 `activeLabel="对话列表"`）。建议 onHistory 先置 `restoreConversationFocusRef.current=false`，打开后把焦点移到面板关闭按钮，并给面板加 Escape 关闭。
- **O11 广场分类标签在 360px 下第五个 tab「发出的邀请」完全出屏且无可滚动提示**。`AgentExchangeWorkspace.tsx:60`；实测 tablist clientW 328 / scrollW 422（`vis/shots/m_r1/360_route_agents.png` 只见四个）。规格「横向滚动」已按字面实现，但可发现性差；建议右侧加渐隐遮罩或窄屏 `max-md:px-2` 让五个刚好放下。
- **O12 独立 `/plaza` 滚到底时 FAB 盖住最后一张热点卡右下角**。`plaza/page.tsx:569-571` FAB fixed，`:361` main 只留了标签栏高度没有为 FAB 预留；实测 390 滚到底 FAB 668–724 与「文化」卡（bottom≈723）重叠（`reviewB/390x844_plaza_bottom.png`）。建议非嵌入窄屏 main 再加约 80px 底部留白。
- **O13 history 窄屏隐藏导出按钮上的「(N条)」计数**（`history/page.tsx:182`）。数字仍在「筛选结果」摘要里，属次要取舍，仅记录。
- **O14 `frontend/AGENTS.md` 出现在 diff 中**（`next dev` 自动改写，内容自述）。实现方无需处理；合并前 `git checkout -- frontend/AGENTS.md`（由 Claude/用户执行，本次复核只读未动）。

## 给 Codex 的二次修改指令

约束不变：仍按 `02-spec.md` 第 2 节白名单与禁止事项执行；只改下面点名的位置；不要启动服务、不做截图；不得 `git commit/checkout/stash/reset`；任何情况下不回滚已完成的工作。完成后在 `frontend/` 下跑 `npx tsc --noEmit`、`npm run lint`（0 error、warning ≤ 28）、`npm run build`（沙箱里 Turbopack 若仍受限，用 `--webpack` 并在报告说明），并把本轮说明追加到 `03-report.md` 末尾「复核返修 R1/R2」小节。

### R1 独立 `/plaza` 发布弹窗停在底部标签栏上沿

文件：`frontend/app/plaza/page.tsx`（`cn` 已导入，`embedded` 在同一个 `PlazaContent` 组件作用域内，`:359` 处定义）。

把 `:585-586` 这两行：

```tsx
<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
  <div className="glass w-full max-w-sm overflow-hidden rounded-[10px] border mobile:max-h-[calc(100dvh-2rem)] mobile:overflow-y-auto" style={{ borderColor: "var(--glass-border)" }}>
```

改为：

```tsx
<div className={cn("fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4", !embedded && "mobile:bottom-[calc(56px+env(safe-area-inset-bottom))]")}>
  <div
    className={cn(
      "glass w-full max-w-sm overflow-hidden rounded-[10px] border mobile:overflow-y-auto",
      embedded ? "mobile:max-h-[calc(100dvh-2rem)]" : "mobile:max-h-[calc(100dvh-2rem-56px-env(safe-area-inset-bottom))]",
    )}
    style={{ borderColor: "var(--glass-border)" }}
  >
```

要点：只用 `mobile:` 变体（该页可被 iframe 内嵌，保持 M1 的 `data-shell` 门控）；嵌入模式保持现值；桌面不受影响（`mobile:` 在 ≥768px 惰性）。若 Tailwind 生成顺序导致 `mobile:bottom-[…]` 没有压过 `inset-0`，在该类后加 `!`（本文件 `:409-411` 热点展开层已用同样写法）。不要改 z-index 层级方案以外的任何东西；不要动 FAB、展开层、兴趣条。

自检（在报告里写清）：说明弹窗外层在非嵌入窄屏下 `bottom` 为 `calc(56px + env(safe-area-inset-bottom))`、内层 `max-height` 扣掉了同一高度；Claude 会在 360×740、375×667、360×640 复测「弹窗 bottom ≤ navTop、『发布』按钮中心与下缘 −2px 的 `elementFromPoint` 均命中按钮本身」，并复测 1440/1024 世界抽屉与 390/360 `/plaza?embed=1` 不变。

### R2 删除「朗读」按钮的 `title`

文件：`frontend/app/page.tsx:1671`。把

```tsx
onClick={() => setVoiceOn(!voiceOn)} aria-label="朗读" title="朗读">
```

改为

```tsx
onClick={() => setVoiceOn(!voiceOn)} aria-label="朗读">
```

只删这一个属性；免提按钮的 `title` 是基线原有的，不要动。自检：`git show HEAD:frontend/app/page.tsx | grep -n '朗读'` 与当前文件对照，确认头部「朗读」按钮与基线相比只多了 `aria-label`、窄屏类名和把文字包进 `<span className="max-md:hidden">`。

### 可顺手做（不作为通过条件；做了要在报告里写明）

- O1：`frontend/components/ChatBubble.tsx:215` 去掉 `max-md:min-w-[min(240px,calc(100vw-32px))]`，保留 `max-md:max-w-full`。这样短消息不再撑成 240px 空框；长消息仍满宽。桌面无影响。
- O2 / O3 / O5(b)：见「可优化项」的具体建议，均为一处小改；若做，不要顺带重构其它逻辑。

其余可优化项留待用户决定，本轮不要主动扩展。
