# 第二轮复核：手机宽度可用（响应式布局）

日期：2026-09-23　基线：`main` @ `54a9b57`　复核对象：`git diff -- frontend`（19 个文件，+498/−216）+ 未跟踪 `frontend/lib/useTheme.ts`
复核范围（按第二轮规则）：只核验 `04-review.md` 的必须修复项 R1、R2 是否真正修好、修复是否引入回归（重点：桌面 ≥ 768px 零变化、`05-fix-mechanical.md` M1 内嵌门控）；顺带抽查 O1–O12 有无造成桌面变化。新发现一律只列 optional。
复核方式：独立通读 diff → 检查 dev 服务实际生成的 CSS（`/_next/static/chunks/app_globals_*.css`）→ 用无头 Chromium（`uv run --with playwright`，隔离环境 3001/8001）亲自复现 R1 四个手机尺寸 + 嵌入模式、R2 两个桌面尺寸、M1 三个桌面尺寸的 iframe、独立 `/plaza` 桌面计算样式、桌面主题切换/Escape 回焦，并按 `vis/vis_desktop.py` 同一配方重新截取桌面 18 张图与改动前 `vis/shots/base/` 逐像素比对。脚本与产物：`scratchpad/reviewB2/verify_r2.py`、`verify_r2.json`、`shots/*.png`、`shots/desk/`、`shots/diff/`。

## 结论：通过

R1、R2 均已真正修好；桌面（1440×900、1024×768、800×900）渲染与交互未发现任何变化；M1 门控在 R1 修改后依然成立。`npx tsc --noEmit` 退出码 0；`npm run lint` 0 error / 28 warning（等于基线上限）。

附注（非通过条件）：`npm run build` 本轮未重跑——真实 `frontend/.next` 正被隔离 dev 服务占用，跑生产构建会打断它；第一轮复核已在副本目录用 `--webpack` 构建通过，实现方本轮自述同样。**合并前仍请在真实 `frontend/` 下跑一次默认 `npm run build` 作为最终门禁**（与第一轮报告的要求相同）。

## R1、R2 逐条核验（证据）

### R1 独立 `/plaza` 发布弹窗停在底部标签栏上沿 —— 已修好

代码（`frontend/app/plaza/page.tsx:585-592`）：外层 `cn("fixed inset-0 z-50 …", !embedded && "mobile:bottom-[calc(56px+env(safe-area-inset-bottom))]!")`；内层 `embedded ? "mobile:max-h-[calc(100dvh-2rem)]" : "mobile:max-h-[calc(100dvh-2rem-56px-env(safe-area-inset-bottom))]"`，并保留 `mobile:overflow-y-auto`。与返修单要求逐字一致，只用 `mobile:` 变体，嵌入分支保持第一轮取值。

生成 CSS 核对（`reviewB2/app.css`）：
- `.mobile\:bottom-\[calc\(56px\+env\(safe-area-inset-bottom\)\)\]\!:where(:root:not([data-shell="desktop"]) *) { bottom: calc(56px + env(safe-area-inset-bottom)) !important; }`，位于 `@media not (min-width: 48rem)` 内，`!important` 压过 `inset-0`；
- `.mobile\:max-h-\[calc\(100dvh-2rem-56px-env\(safe-area-inset-bottom\)\)\]:where(:root:not([data-shell="desktop"]) *)` 同样受 M1 `data-shell` 门控。

浏览器复现（独立打开 `/plaza`，对 `input[type=file][accept="image/*,video/*"]` 注入 `tiny.png` 打开弹窗，弹窗内层滚到底后测量；`verify_r2.json` 的 `A_plaza_modal_*`，截图 `reviewB2/shots/A_plaza_modal_*.png`）：

| 视口 | navTop | 外层 computed `bottom` / rect bottom | 内层 bottom / `max-height` | 「发布」按钮 | 中心命中 | 下缘 −2px 命中 |
| --- | --- | --- | --- | --- | --- | --- |
| 360×740（规格尺寸） | 684 | 56px / 684 | 668 / 652px（=740−32−56） | 611–651 | 按钮本身 | 按钮本身 |
| 375×667（第一轮失败尺寸） | 611 | 56px / 611 | 595 / 579px | 538–578 | 按钮本身 | 按钮本身 |
| 360×640（第一轮失败尺寸） | 584 | 56px / 584 | 568 / 552px | 511–551 | 按钮本身 | 按钮本身 |
| 390×844 | 788 | 56px / 788 | 747 / 756px（不需滚动，居中） | 690–730 | 按钮本身 | 按钮本身 |

四个尺寸弹窗 bottom ≤ navTop，第一轮「中心点命中底栏『广场』链接」的现象消失。与 Claude 机械验证 `vis/shots/fix/claude_measurements.json`（360×740 btnBottom 667 / modalBottom 668 等）一致，本轮为独立复现。

嵌入模式不变（`B_embed_modal_*`，390×844 首页点底栏「世界」→ iframe `/plaza?embed=1` 内注入图片）：iframe 底边 788 = 父窗口 navTop；iframe 内外层 `bottom` 仍为 `0px`（嵌入分支未加底边偏移），内层 `max-height` 699px = 731−32 即第一轮的 `calc(100dvh-2rem)`；「发布」中心与下缘均命中按钮。360×740 同（627 高 iframe，max-height 595px）。截图 `reviewB2/shots/B_embed_modal_*.png`。

### R2 删除「朗读」按钮的 `title` —— 已修好

代码：`git show HEAD:frontend/app/page.tsx` 第 1605 行 vs 当前 `page.tsx:1714-1715`——头部「朗读」按钮现为 `className={cn("chip max-md:…", voiceOn && "chip-on")} onClick aria-label="朗读"`，文字包进 `<span className="max-md:hidden">`，**无 `title`**。全文件 `title=` 属性清单与基线对照：仅新增一处 `title="草莓余额，每条消息消耗 10 颗"`，挂在 `hidden … max-md:inline-flex` 的 🍓 余额 span 上（桌面 `display: none`，实测 `balanceSpanDisplay: "none"`）；免提按钮基线自带的 `title` 原样保留。

浏览器复现（1024×768、1440×900 首页，`verify_r2.json` 的 `E_desktop_home_*`）：`button[aria-label="朗读"]` 属性集合 = `[aria-label, class, type]`，`hasAttribute('title') = false`，可见文字「朗读」，尺寸 64×28；鼠标悬停 1.2s 后再读 `title` 仍为 null。头部所有带 `title` 的元素只剩「免提：分身说完自动开麦…」（基线原有）与隐藏的余额 span；输入区带 `title` 的四个按钮（上传参考图 / 生成图片 / 发送看图聊天附件 / 语音转文字）与基线完全相同。

## 桌面零变化与 M1 门控复核

### 桌面逐像素（独立重截，`reviewB2/shots/desk/` vs 改动前 `vis/shots/base/`，阈值同 `vis/diff.py`）

| 截图 | 1440×900 | 1024×768 | 差异内容（看 `reviewB2/shots/diff/`） |
| --- | --- | --- | --- |
| 首页 | 0.578% | 0.952% | 会话列表时间戳 + 聊天区多出的两条测试消息「嗯」/ 30 字长消息（Claude 04:37 的 `vis_fix.py` 发送，晚于 02:46 基线截图），气泡外无任何布局边缘变化 |
| 分身抽屉 | 0.096% | 0 | 仅会话时间戳（bbox 76,83–274,132 即会话列表） |
| 广场抽屉 | 0.096% | 0 | 同上 |
| 世界抽屉 | 3.27% | 3.83% | 热点卡内文字更新、时间读数、3D 星空与行星动画；卡片边框/位置不在差异中，双列绝对定位保持 |
| 设置抽屉 | 0.096% | 0.159% | 仅会话时间戳 |
| `/agents/me` | 0 | 0 | — |
| `/agents` | 0 | 0 | —（O11 的箭头提示 `hidden … max-md:flex`，桌面不出现；tablist 外新增的 `div.relative.mb-6` 包裹未改变像素） |
| `/settings` | 0 | 0 | —（`h-screen`→`h-dvh` 规格允许，桌面等价） |
| `/history` | 1.62% | 2.10% | 同首页：新增的两条测试消息与计数，无结构位移 |

### 独立 `/plaza` 桌面（规格 5.4c 点名但基线集缺失，改用计算样式判定；`D_plaza_standalone_*`，截图 `reviewB2/shots/D_plaza_standalone_*`）

1024×768 与 1440×900：`html[data-shell]` 为空；根容器 `padding-bottom: 0px`；`main` `padding-bottom: 0px`、`overflow-y: hidden`（O12 的 `mobile:pb-20` 未生效）；两列热点容器 `position: absolute`、卡片 220px；FAB `position: absolute; bottom: 56px; right: 24px`；底栏 `display: none`、左侧 56px 侧栏可见。打开发布弹窗：外层 `bottom: 0px`（R1 的 `mobile:bottom-…!` 未生效）、内层 `max-height: none`、`overflow-y: hidden`——即 R1/O12 的全部新增类在桌面惰性，与基线 `fixed inset-0` 居中弹窗一致（截图 `D_plaza_standalone_1440x900_modal.png`）。

### M1 内嵌门控（`C_desktop_iframe_*`）

- 1024×768（iframe 644px 宽）、800×900（iframe 495px 宽）、1440×900：世界抽屉 iframe 内 `data-shell="desktop"`，热点两列 `absolute`、卡片 220px、`main` 无底部留白、FAB 绝对定位；在 iframe 内打开发布弹窗：外层 `bottom: 0px`、内层 `max-height: none`——R1 新增的两条 `mobile:` 规则被 `:root:not([data-shell="desktop"])` 正确挡住。设置抽屉 iframe 同样 `data-shell="desktop"`、`.max-w-lg` 左内边距 32px（桌面 `px-8`）。
- `frontend/app/layout.tsx:28-47` 内联脚本：`syncShell()` 先于监听注册；`addEventListener` 不可用时回退 `addListener`；`pagehide` 移除监听；外层 `catch` 只留注释、不再 `removeAttribute`（O5 三点均落实，且未改变桌面首帧逻辑）。
- 可内嵌五页（plaza/match/settings/profile/community）及 `Earth3D`/`SolarSystem3D` 中 grep 不到 `max-md`；`globals.css:415-431` 两段全局 `@media (width < 48rem)` 规则仍带 `:root:not([data-shell="desktop"])`；全库 `embed=1` 仍只有 `page.tsx:1962/1995` 两个 iframe。

### O1–O12 顺带抽查（有无桌面变化）

- O3 `useTheme`（`useSyncExternalStore` + MutationObserver，服务端快照 `true` 与 `<html class="dark">` 一致）：1024/1440 实测初始 `dark=true`、按钮 `title="切换浅色"`，点一次 → `html.dark=false`、`title="切换深色"`，再点复原——与基线行为相同；会话列表底部主题栏桌面 `display: none`。
- O6 余额轮询：登录后 5s 内 `/strawberry` 请求 2 次（StrictMode 双挂载），无重复订阅。
- O7 附图按钮：`aria-label` 为 null、`title="发送看图聊天附件"`，桌面读屏名称恢复基线；免提/语音转文字/按住说话的 `aria-label` 与可见文字或原 `title` 同串，名称不变。
- O8/O2/O10：桌面「对话列表」按钮 `display: none`；分身抽屉按 Escape 后焦点回到侧栏 `aria-controls="agent-drawer"` 的按钮（`focusVisibleDrawerTrigger` 在桌面选中的是 aside 按钮，因底栏按钮 `getClientRects().length === 0`）；桌面从会话列表打开「当前对话记录」：面板 left 56 / 宽 256 / 底到视口底（基线 `left-14 w-64`），焦点不被强制移入面板，Escape 不关闭（基线无此行为）——O10 的新行为只在 `matchMedia("(width < 768px)")` 命中时触发。
- O9 四个抽屉关闭按钮只加 `max-md:h-10 max-md:w-10`；O11 提示条 `hidden … max-md:flex`；O12 `mobile:pb-20` 受门控；O1 只删了 `max-md:min-w-*`。均为窄屏变体。
- 滚动区 `pt-16` / `pb-[var(--composer-height)]`：桌面实测 `padding-top: 64px`、`padding-bottom: 146px`，footer 底边 = 视口底。

### 静态门禁

- `npx tsc --noEmit` → `TSC_EXIT=0`。
- `npm run lint` → `✖ 28 problems (0 errors, 28 warnings)`，与基线上限相同。
- `git status --porcelain --untracked-files=all -- frontend`：全部在 `frontend/app/**`、`frontend/components/**`、`frontend/lib/**`；`frontend/AGENTS.md` 仍是 `next dev` 自动改写（内容自述），合并前由 Claude/用户 `git checkout -- frontend/AGENTS.md`（本轮只读未动）。

## 新发现（仅 optional）

- **N1 小屏弹窗滚到底后头部（含关闭 X）滚出视野**。360×740 / 375×667 / 360×640 独立 `/plaza` 弹窗内层可滚动，滚到「发布」时「发布到世界」标题与关闭按钮已在可视区外（`headerVisible: false`），需滚回顶部才能关闭。这是第一轮 `mobile:overflow-y-auto` 设计固有的，R1 只是缩小了最大高度，不是新引入；若要改善，可给弹窗头部加 `mobile:sticky mobile:top-0` 或把「发布」行固定在底部。桌面无影响。
- **N2 「当前对话记录」面板关闭按钮新增 `aria-label="关闭当前对话记录"`**（`page.tsx:1636`，O10 顺带加入）。桌面该按钮基线为无名称的图标按钮，现在读屏会念出名称；属可访问性改进，无视觉与交互变化。若坚持严格零变化可改成只在窄屏生效（如用 `<span className="sr-only md:hidden">`），否则在报告中注明即可。
- **N3 默认 Turbopack 构建仍未在真实目录验证**（见结论附注），合并前跑一次。
