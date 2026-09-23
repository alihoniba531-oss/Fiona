# 返修单 第 1 轮（手机布局）

来源：`04-review.md`（独立复核，结论：不通过）。原规格 `02-spec.md` 的白名单、禁止事项与「何时停下来问」判据不变；`05-fix-mechanical.md` 的 M1（内嵌页按父窗口断点渲染、可内嵌页面只用 `mobile:` 变体）必须保持。

## 必须修复

- **R1** 独立 `/plaza` 的发布弹窗在非嵌入窄屏下停在底部标签栏上沿：按 `04-review.md`「给 Codex 的二次修改指令 · R1」执行（只用 `mobile:` 变体；嵌入模式保持现值）。
- **R2** 删除「朗读」按钮新增的 `title`：按 `04-review.md`「给 Codex 的二次修改指令 · R2」执行。

## 同轮顺带处理（来自 04-review.md 可优化项）

- **O1**（规格验收写法造成的问题，由规格作者更正）：`02-spec.md` 第 5 节「消息气泡宽度 ≥ 240px」的本意是「消息区不再被挤窄、长消息不逐字竖排」，**不是**给短消息强加最小宽度。去掉 `ChatBubble.tsx` 中窄屏的最小宽度（如 `max-md:min-w-*`），只保留不超出内容区的最大宽度约束。验收改为：390×844 下内容列宽 ≥ 340px，且 30 字以上的用户消息气泡宽度 ≥ 240px。
- **O2** 会话覆盖层打开时视口跨到 ≥ 768px：自动关闭覆盖层并清理状态（`aria-expanded`、键盘监听），回到窄屏时不应自动重新出现。
- **O3** 主题状态：`Sidebar` 与 `ConversationPicker` 共用同一份主题状态（例如读取 `document.documentElement` 的 `dark` class 并订阅变化的共享 hook），跨断点后两处按钮文案/图标保持一致。
- **O4** `page.tsx` 中 JS 断点判断与 CSS 断点一致：改为 `matchMedia("(width < 768px)")`（或等价写法，保证非整数视口宽度下与 CSS `width < 48rem` 一致）。
- **O5** `app/layout.tsx` 内联脚本：`addEventListener` 不可用时回退 `addListener`；`catch` 分支不得移除已设置的 `data-shell="desktop"`；页面卸载（`pagehide`）时移除父窗口媒体查询监听。
- **O6** `Sidebar` 的余额轮询 effect 依赖恢复为 `[]`，`onBalanceChange` 通过 `useRef` 读取最新值。
- **O7** 附图按钮不要新增固定 `aria-label="附图"`（桌面读屏名称应保持改动前由 `title` 提供的状态化名称）。其余新增 `aria-label` 的按钮若在改动前有可见文字或 `title` 作为名称，同样核对：桌面端可访问名称不得变化。
- **O8** 头部「对话列表」按钮的 `aria-controls` 只在覆盖层实际挂载时设置。
- **O9** 四个抽屉头部的关闭按钮在窄屏触控区域不小于 40×40px（`max-md:`，桌面不变）。
- **O10** 从会话覆盖层打开「当前对话记录」时，焦点进入记录面板（如其关闭按钮），面板支持 Escape 关闭，关闭后焦点回到合理位置。
- **O11** 广场分类标签在 360px 下横向超出时给出可滚动提示（例如右侧渐隐遮罩，只用现有令牌），桌面不变。
- **O12** 独立 `/plaza` 在窄屏滚到底时，浮动 `+` 按钮不遮住最后一张卡片（给内容区增加足够的底部留白，只用 `mobile:` 变体）。

不处理：O13（仅记录）、O14（Claude 负责还原 `frontend/AGENTS.md`）。

## 交付

完成后在 `frontend/` 下跑 `npx tsc --noEmit`、`npm run lint`（0 error、warning ≤ 28）、`npm run build`（沙箱里 Turbopack 受限时用 `--webpack` 并说明），把本轮说明追加到 `03-report.md` 末尾「复核返修第 1 轮」小节，逐条对应 R1、R2、O1–O12。不要启动服务、不做截图。
