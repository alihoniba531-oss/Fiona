# 机械验证返修单（手机布局）

来源：Claude 机械验证（隔离环境 + 无头 Chromium，改动前后同一脚本截图逐像素比对）。本单不计入独立复核轮次。

## 通过的部分（不要改动）

- `npx tsc --noEmit` 退出码 0；`npm run lint` 0 error / 28 warning；默认 Turbopack `npm run build` 成功。
- 390×844、360×740 下规格 T3 所列全部路由（含 `?embed=1`）无横向滚动、无逐字竖排；首页内容列宽 358px；输入区下沿 = 底栏上沿；会话覆盖层新建/切换后自动关闭；四个抽屉宽 390、底边停在底栏上沿且底栏可点。
- 1440×900 下首页、四个抽屉、`/agents/me`、`/agents`、`/settings`、`/history` 与改动前逐像素一致（仅会话时间戳不同）；1024×768 下首页、分身/广场抽屉与各独立页面一致。

## 必须修复

### M1 桌面窄窗口下，内嵌抽屉里的页面误用了手机布局

- **现象**：1024×768 桌面视口，打开「世界」抽屉（iframe `/plaza?embed=1` 或 `/match?embed=1`）与「设置」抽屉（iframe `/settings?embed=1` 或 `/profile?embed=1`）。这两个抽屉宽度是 `calc((100vw - 56px) * 2 / 3)` ≈ 645px，iframe 自身视口 < 768px，于是内嵌页面里的 `max-md:` 等窄屏样式全部生效：世界抽屉的热点卡从「太阳系两侧双列、绝对定位」变成单列文档流；设置页的内边距与卡片宽度也变了。逐像素比对：世界抽屉 4.9% 像素变化、设置抽屉 2.8%。只要桌面窗口宽度 < 约 1208px（此时 iframe < 768px）都会出现。
- **违反**：规格第 2 节「≥ 768px 的渲染结果必须与现在完全一致」。
- **要求**：
  1. 内嵌页面（`?embed=1`）是否使用窄屏布局，由**顶层应用外壳**（父窗口）的宽度决定：父窗口 ≥ 768px 时，iframe 内一律按桌面布局渲染，不论 iframe 自身多宽；父窗口 < 768px（手机外壳）时保持你现在实现的窄屏布局。独立打开的页面（非嵌入）仍按自身视口判断。
  2. 父窗口跨越 768px 断点（桌面窗口拉窄/拉宽）时，iframe 内布局要随之切换（首选无需刷新；做不到时允许 iframe 重新加载）。首帧不应先闪一下错误布局再纠正（若无法完全避免，在报告中说明）。
  3. 覆盖所有可被 iframe 内嵌的页面及它们渲染的共享组件，以及 `app/globals.css` 中 `@media (width < 48rem)` 的全局规则（手机输入 16px、`.mobile-scrollbar-none`）。请全库搜索 `embed=1` 找到所有内嵌入口，不要只改上面点名的页面。
  4. 参考做法（非强制）：在 `globals.css` 用 Tailwind 4 `@custom-variant` 定义一个窄屏变体，例如 `@custom-variant mobile (@media (width < 48rem) { &:where(:root:not([data-shell=desktop]) *) });`，把可内嵌页面里的 `max-md:` 换成它，`md:hidden` 等同理处理；内嵌页面在 `window.parent !== window` 且父窗口 `matchMedia("(min-width: 768px)")` 命中时给 `<html>` 设 `data-shell="desktop"`，并监听父窗口的媒体查询变化。
- **验收**（Claude 会执行）：1024×768 下世界、设置两个抽屉与改动前截图逐像素一致（热点内容、时间戳等动态区域除外）；800×900 下 iframe 内 `<html>` 按桌面渲染（热点卡保持绝对定位双列）；390×844、360×740 下所有现有检查结果不变。

## 约束

仍按 `02-spec.md` 第 2 节白名单与禁止事项执行；不要启动服务、不做截图；完成后跑 `npx tsc --noEmit`、`npm run lint`（warning 不超过 28）、`npm run build`（沙箱里 Turbopack 若仍受限，可用 `--webpack` 验证并在报告说明）。把本轮说明追加到 `03-report.md` 末尾的「机械返修 M1」小节。
