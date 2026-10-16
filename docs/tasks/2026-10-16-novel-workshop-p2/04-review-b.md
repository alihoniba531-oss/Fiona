# 小说工坊 P2 前端 独立复核 B（界面规范 / 交互完整性 / 嵌入与窄屏）

- 复核对象：工作树 `.worktrees/fiona-novel-p0`（分支 novel-workshop-p0，基线 8c58057，未提交改动）
- 依据：`docs/tasks/2026-10-16-novel-workshop-p2/02-spec.md`、完整 diff `p2.diff`、仓库源码。实施方报告仅作线索。
- 方法：只读源码与静态推算（未跑 build / dev / 浏览器）。所有尺寸结论为按 CSS 推算，截图由验收方另行完成。
- 路径省略前缀 `frontend/`。

## 1. 结论：不通过（1 条必须修复，范围很小；其余通过）

唯一的必须修复项是工作台三栏网格在「主页抽屉 + 平板宽度宿主」下会产生横向滚动（iPad 768–838px 宿主宽度），以及 1024–1150px 宿主宽度下正文列被挤到 124–200px。手机 360/390、桌面 1440 按推算均无横滚。修掉这一处 grid 后，本路复核可改为通过。

## 2. 必须修复项

### M1. 工作台三栏在嵌入抽屉的平板宽度下横向溢出，正文列在中等宽度下被挤扁

- 现象：三栏网格写死了左右两栏的最小宽度 150px / 240px 加两个 20px 间距（最小合计 430px），只在 `mobile:`（宿主 <768px）时退化为单列。宿主在 768–838px（iPad 竖屏 768/810/820/834 全部命中）时，抽屉宽度 = `(100vw − var(--rail-w) − 12px) × 2/3` ≈ 448–495px，减去 `main` 的 `px-8`（64px）后可用 383–430px，小于 430px → iframe 内出现横向滚动条；宿主 1024–1150px 时正文列只剩约 124–200px（每行 7–12 个汉字）。
- 证据：
  - `components/novel/NovelWorkbench.tsx:208` — `grid-cols-[minmax(150px,.65fr)_minmax(0,2fr)_minmax(240px,1fr)] items-start gap-5 mobile:block`
  - `components/novel/NovelWorkbench.tsx:184` — `main` 的 `px-8`（嵌入模式同样生效）
  - `app/page.tsx:2736` — 抽屉宽度 `calc((100vw - var(--rail-w) - 12px) * 2 / 3)`
  - `app/layout.tsx:72–75` — 宿主 ≥768px 时 iframe 置 `data-shell=desktop`，`mobile:` 变体不再生效（`app/globals.css:8–14`）
  - 推算：宿主 768px → 抽屉 448px → 可用 383px < 430px，溢出 47px；宿主 1024px → 可用 554px，fr 分配后正文列 = 554 − 40 − 150 − 240 = 124px。
- 用户可见后果：iPad 上打开主页「书斋」抽屉进入任意一本书，页面左右可拖、右栏被切掉一截；笔记本小窗/1024 宽度时正文一行只有十来个字，无法阅读。规格 §2「三个页面都必须能在 iframe 中正常工作」与 §3「不能出现横向滚动」的意图没有满足。
- 修法建议（任选其一，都不需要新令牌）：
  1. 用 Tailwind 4 自带的容器查询：在 `:208` 的网格外层加 `@container`，网格默认 `grid-cols-1`（或两栏：目录 + 正文，右栏下沉），到 `@4xl:`（≥56rem≈896px 容器宽）才启用三栏；
  2. 或改用 iframe 自身视口断点：默认单列/两栏，`lg:`（iframe ≥1024px）才三栏。iframe 的视口就是抽屉宽度，所以 `lg:` 在抽屉里天然按抽屉宽度切换；
  3. 同时把左右栏最小值改软一点（如 `minmax(0,.65fr)` / `minmax(0,1fr)` 并给栏内 `min-w-0`），避免任何宽度下出现硬下限。
  改完请验收方补一张宿主 768×1024 与 1024×768 的抽屉截图。

## 3. 可优化项（不阻断）

按影响从大到小排序。

1. **书架 N+1 轮询，且未按 §8 停下来问**：`list` 接口不含 `config.target.max_chapters`，实施方改为对每本书再拉一次详情，并在任何一本书运行时每 3 秒重复整个过程；任一本详情失败整张书架变错误态（`components/novel/NovelShelf.tsx:31–34`）。规格 §8 明确「后端返回的字段不够实现某项展示」应停下来报告，实施方在报告 §3 自述为「实现决定」。建议作者拍板：是否允许给 P1 `summary()`（`backend/novel/service.py:160`）加 `max_chapters` 字段。工作台同理：首次打开按已完成章数逐章拉 `chapters/{n}` 只为取 `edited_by_user`（`NovelWorkbench.tsx:70–76`），60 章书首屏 60 个请求。
2. **抽屉在 768–1150px 的紧凑布局**：见 M1 第 2 点，修 M1 时一并处理。
3. **独立页工作台的侧栏随页面拉长**：`NovelWorkbench.tsx:181–183` 根容器用 `min-h-screen flex-col` 让整页滚动，而 `Sidebar` 非共享模式外层是 `Glaze … flex shrink-0`（`components/Sidebar.tsx:126`），在 flex 行里会被拉伸到整页高度；长书时昼/夜切换与草莓读数（`mt-auto`）被推到页面最底部。书架与向导用的是设置页同款 `h-dvh overflow-hidden` + `main overflow-y-auto`（`NovelShelf.tsx:54–56`、`NovelWizard.tsx:139–141`、对照 `app/settings/page.tsx:143–147`）。建议工作台改成同一骨架。
4. **抽屉外壳与「设置」抽屉的两处细节差异**：关闭按钮固定 `h-10 w-10`（`app/page.tsx:2745`），设置抽屉桌面是 `w-6 h-6`、手机才 `max-md:h-10`（`:2707`），桌面端头部高 16px；面板被程序化聚焦（`:477–479`）却没有像分身抽屉那样加 `outline-none`（对照 `:2610`），键盘打开时整个抽屉可能出现一圈焦点轮廓。
5. **错误提示重复**：`mutate` 失败时既在工作台顶部 `setError`（`NovelWorkbench.tsx:150`）又把异常抛回子组件，子组件再各自 `ErrorNotice`（`SetupEditor.tsx:61`、`PlanEditor.tsx:14`、`ChapterReader.tsx:30`、`NotesPanel.tsx:19`），同一条错误会在页面上出现两次。建议 `mutate` 只在没有子组件接管时写顶部错误，或子组件只做字段级提示。
6. **404 文案映射过宽 / 过窄**：书架与向导把任何 404 都译成「小说工坊尚未开放」（`lib/novels.ts:150`），书架逐本拉详情时若某本刚被删除（后端返回「小说不存在」404）会误报「尚未开放」；工作台直连 `/novels/{id}` 且开关关闭时，后端 404 detail 是英文 `Not Found`（`backend/routers/novel.py:14`），前端落到「请求未完成，请稍后重试。」（`lib/novels.ts:153`），没有出现规格文案。建议按 detail 文本区分（`Not Found` → 尚未开放；含中文 → 原样）。
7. **目录标记用 Unicode 符号**：`!` `↔` `↗` `⚑` `✎` `◷`（`components/novel/ChapterList.tsx:6–13`），`⚑`/`◷` 在 Windows 常见字体里可能缺字或被当成 emoji 渲染，虽然旁边有文字标签不影响理解，但与全站 lucide 图标风格不一致。lucide 已是依赖，可换 `Flag`/`Clock` 等。
8. **新引入的 ES2022/2023 运行时 API**：`Array.prototype.findLast`、`.at(-1)`、`structuredClone`（`NovelWorkbench.tsx:157,179,85`、`SetupEditor.tsx:19–20`、`PlanEditor.tsx:9`），仓库其他前端代码此前未使用；需要 Safari ≥15.4 / Chrome ≥98。目标用户若有旧 iOS，需确认。
9. **a11y 小项**：右栏三个标签页的 `aria-controls` 指向 `novel-detail-{tab}`，但只渲染当前面板，其余两个 id 不存在（`NovelWorkbench.tsx:221–222`）；手机三标签对应的 `aside/section` 没有 `role="tabpanel"`（`:209–220`）；目录按钮用 `aria-current="page"` 表示「当前章」（`ChapterList.tsx:24`），用 `aria-pressed` 或 `aria-current="true"` 更贴切；「前往登录」内联链接不足 40px（`NovelShelf.tsx:64`、`NovelWorkbench.tsx:187`），属登录态异常路径。
10. **嵌入模式手机底部多留白**：工作台在嵌入模式也加了 `mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+16px)]`（`NovelWorkbench.tsx:184`），而抽屉本身已止于底栏之上（`app/page.tsx:2734`），底部多出约 76px 空白；书架/向导嵌入时没加（`NovelShelf.tsx:56`）。统一即可。
11. **`awaiting_review` 的章节区间是前端估算**：`start = max(1, end − batch_size + 1)`（`components/novel/GateBanner.tsx:21–22`），中途改过每批章数或首批不满时会显示错区间。后端若能给出本批起止章更稳。
12. **保存改稿后章节被拉取两次**：`mutate` 内 `load(true)` 已令 `revision+1`，`onSave` 回调里又 `setRevision`（`NovelWorkbench.tsx:214–216`）。
13. **`.btn` 的 `white-space:nowrap`** 在 296px 内容宽下所有按钮文字（最长「附一句话重新定稿」约 140px）均放得下，但横幅里多按钮同行靠 `flex-wrap` 换行，视觉上没问题，仅提醒不要再加更长按钮文案。

## 4. 逐条核验表

| # | 核验项 | 结论 | 证据 |
|---|---|---|---|
| 1a | 只用已有令牌与类，无新增颜色值 | 通过 | 在 `app/novels`、`components/novel`、`lib/novels.ts` 全文检索 `#hex`/`rgb(`/`rgba(`/`hsl(`/`oklch(`、Tailwind 调色板类（`text-red-*`、`bg-amber-*` 等 25 个色名）均 0 命中；用到的 CSS 变量只有 `--ink`(28) `--ink2`(60) `--carve`(21) `--paper`(1) `--scrim`(1) `--tabbar-h`(4)，全部在 `globals.css` 四套主题中定义（`:53–270`、`:273–298`） |
| 1b | 无新增字体 | 通过 | 检索 `font-family`/`font-serif`/`font-mono`/`@font-face`/`fontFamily` 0 命中；正文继承 `body` 的 `--font-sans-stack`（思源宋体，`globals.css:280,311`） |
| 1c | 朱印不用于书的状态 | 通过 | 检索 `seal`/`tag-rec`/`rec-soft` 0 命中；状态一律 `.tag`（`NovelShelf.tsx:66`、`NovelWorkbench.tsx:191`）。唯一带 `--seal` 的是规格允许的 `.btn-danger`（删除按钮，`NovelWorkbench.tsx:201`） |
| 1d | 数字用 `.readout` | 通过 | 书架进度/草莓/时间（`NovelShelf.tsx:68–69`）、页头读数（`NovelWorkbench.tsx:193–194`）、横幅章号与字数（`GateBanner.tsx:23,26,28`）、目录章号与「正在写第 n 章」（`ChapterList.tsx:26,30`）、字数计数（`ChapterReader.tsx:40`、`NovelWizard.tsx:152`、`NotesPanel.tsx:25`）、估算与余额（`NovelWizard.tsx:163`）。例外：留言卡「已下发到第 n 章」在 `.tag` 内（`NotesPanel.tsx:30`），可忽略 |
| 1e | 正文行距 ≥1.9、桌面列宽 ≤ 约 38 汉字 | 通过 | `ChapterReader.tsx:33` `max-w-[38em]`（16px 字号 = 608px ≈ 38 字）；`:42` `whitespace-pre-wrap break-words text-base leading-[1.95]`；改稿 textarea `:39` `leading-[1.95]`；页头梗概 `leading-[1.9]`（`NovelWorkbench.tsx:192`） |
| 1f | 昼/夜/素瓷下无写死颜色 | 通过 | 同 1a；对话框底色 `bg-[color:var(--paper)]`、遮罩 `backdrop:bg-[color:var(--scrim)]`（`NovelSettingsDialog.tsx:31`）；进度条轨/填充 `var(--carve)`/`var(--ink2)`（`NovelWorkbench.tsx:194`）；`Glaze` 嵌入时 `backdrop={false}`，素瓷下 `.glaze-tint` 为不透明 `--glass`（`globals.css:213,268`） |
| 2a | 可点区域 ≥40px | 通过 | 44 处 `min-h-10`/`h-10`；所有 `<button>`、`<summary>`（改编参数 `NovelWizard.tsx:154`、审校摘要 `ChapterReader.tsx:43`、圣经分块 `BiblePanel.tsx:9`、更多 `NovelWorkbench.tsx:201`）、标签页按钮（`:207,221`）、目录按钮（`ChapterList.tsx:25`）、复选/单选外层 `label min-h-10`（`NovelModelFields.tsx:25`、`NovelWizard.tsx:157,161`）均 ≥40px；`globals.css:376` 另有手机 `button{min-height:40px}` 兜底。`.chip`（32px）仅用于向导步骤条的非交互序号（`NovelWizard.tsx:145`）。未达标仅「前往登录」内联链接（见可优化 9） |
| 2b | 输入框字号 ≥16px | 通过 | `novelFieldClass` `text-[16px]`（`NovelModelFields.tsx:5`，向导全部输入/下拉复用）；`SetupEditor.tsx:8`、`PlanEditor.tsx:7`、`NovelSettingsDialog.tsx:8` `text-[16px]`；`GateBanner.tsx:27` 两个 input `text-[16px]`；`ChapterReader.tsx:39`、`NotesPanel.tsx:24` `text-base`；`globals.css:455–459` 手机壳再强制 `max(16px,1em)` |
| 2c | 底部留 `var(--tabbar-h)` + 安全区 | 通过 | `NovelShelf.tsx:56`、`NovelWizard.tsx:141`、`NovelWorkbench.tsx:184` 非嵌入时 `mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]`（工作台另加 24px）；嵌入时由宿主抽屉 `max-md:bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))]!` 止于底栏（`app/page.tsx:2734`） |
| 2d | 360/390 无横滚、无长不换行文本 | 通过（手机）/ **不通过（平板宿主，见 M1）** | 书架 `grid-cols-2 mobile:grid-cols-1`、卡片 `min-w-0`、书名 `break-words`（`NovelShelf.tsx:64–66`）；向导三格数字 `mobile:grid-cols-1`（`NovelWizard.tsx:153`），汇总 `break-words`（`:164`），下拉 `w-full min-w-0`；页头标题块 `min-w-0 flex-1 basis-72`（288px ≤ 360−32−32=296）+ 按钮 `flex-wrap`（`NovelWorkbench.tsx:190–196`），进度条 `max-w-[320px]`；三栏 `mobile:block`（`:208`）；三标签「推演·圣经·留言」13px×7 字≈91px < 单格≈109px（`:207`）；横幅输入 `w-24` + `min-w-0 flex-1 basis-48`（`GateBanner.tsx:27`）；对话框 `w-[min(720px,calc(100vw-32px))]`（`NovelSettingsDialog.tsx:31`）；推演/圣经/留言容器 `break-words`（`DeliberationTimeline.tsx:41`、`BiblePanel.tsx:18`、`NotesPanel.tsx:31`）；模型名/ID 只出现在 `<select>` 选项与 `break-words` 的 li 内（`NovelWizard.tsx:164`） |
| 3 | 手机底栏 6 项 360px 可容纳、未改其他项样式 | 通过 | `components/Sidebar.tsx:109–111`：每项 `min-w-0 flex-1 … whitespace-nowrap text-sm tracking-[.2em]`，360/6 = 60px；「书斋」2×14px + 2×2.8px 字距 ≈ 33.6px，余量 26px（320px 宽也仅需 53px 格）；高度 `h-[var(--tabbar-h)]`=60px ≥40。diff（`p2.diff:215–256`）对 Sidebar 只做了 navItems 追加与 `/novels` 映射，`classes`/`content` 未动。桌面书签同样 `min-h-16 w-10 … vertical-rl`（`:95`） |
| 4a | 书架空态/加载/错误/404/403 文案 | 通过 | 「开始你的第一本书」「只给一个思路，几位智能体替你推演整本书。」+「新建一本」（`NovelShelf.tsx:64`）；加载 `LoadingState`、错误 `ErrorNotice`（同行）；404→「小说工坊尚未开放」、403→「你的账号暂未开通小说工坊」（`lib/novels.ts:150–151`，书架 `:34` 与向导 `NovelWizard.tsx:70` 均传 `access=true`）；后端 403 detail 为「小说工坊暂未对该账号开放」但被前端映射覆盖为规格文案 |
| 4b | 「待你处理」提示 | 通过 | `awaiting_*` 与 `paused` 显示（`NovelShelf.tsx:67`） |
| 4c | 向导步骤条、返回保留、字段就近错误 | 通过 | 步骤条 `ol aria-label="建书步骤" aria-current="step"`（`NovelWizard.tsx:145`）；全部表单值在父组件 state，`上一步` 只改 `step`（`:166`）；`fieldError` 带 `role="alert"` 与 `aria-describedby`（`:137–138`）；逐步校验 `validate(at)`（`:93–117`）；后端 422/409 顶部 `ErrorNotice`（`:147`） |
| 4d | 工作台三栏与手机三标签「目录 / 正文 / 推演·圣经·留言」 | 通过 | `NovelWorkbench.tsx:207`（`hidden mobile:flex`）与 `:209–223`（`mobile:hidden` 切换） |
| 4e | 右栏三标签 推演/圣经/留言 | 通过 | `:221–222` |
| 4f | 目录 6 种标记 + 悬浮说明 | 通过 | `ChapterList.tsx:6–13` 六种 flag，`title`+`aria-label`+可见文字（`:27`）；`stale` 由章节 `status` 推出（`:22`），`edited_by_user` 由详情补读（`:23`、`NovelWorkbench.tsx:78–81`）；后端还会产生 `review_degraded`，被 `flagLabels[flag]` 过滤不显示，符合规格六种 |
| 4g | 「正在写第 n 章…」 | 通过 | `ChapterList.tsx:30`；章号来自 `planning/writing` 状态或 `chapters_done+1`（`NovelWorkbench.tsx:179`，后端章节状态见 `backend/novel/store_db.py:274`、`runner.py:311`） |
| 4h | 改稿 30000 上限、保存后 message | 通过 | `maxLength={30000}` + 守卫（`ChapterReader.tsx:27,39`）；`onSave` 返回后端 `message` 并以 `role="status"` 显示（`:29,37`；`NovelWorkbench.tsx:211–218`）；后端 `Manuscript max_length=30000`（`backend/novel/service.py:77`） |
| 4i | 审校摘要「保留 x 条意见 · 丢弃 y 条」可展开 | 通过 | `ChapterReader.tsx:43–44`，展开列出 `blocking===true` 的 problem/evidence；与后端 `review_summary` 口径一致（`service.py:246`） |
| 4j | 推演时间线 6 段顺序、solo 只显示裁决 | 通过 | `DeliberationTimeline.tsx:43–73` 顺序：初案→顾问意见（重/轻、针对、问题、改法、值得保留）→替代走向（采纳/部分采纳/不采纳，兼容旧格式 `:51–62`）→主编逐条回应（O 序号排序 `:63`）→定稿改动（原→新、节拍增删 `:67–68`）→留言回应；solo 判定 `:37–38`，solo 后端会议无 `mode/plan/critiques/proposals`（`backend/novel/deliberation.py:211–212`）→ 只渲染「主编裁决」+ 理由（`:42`）。严重度取值 `major/minor` 与后端一致（`agent_pool.py:99–100`） |
| 4k | 圣经各块默认折叠、罗盘展开 | 通过 | `BiblePanel.tsx:19` `open`，其余 `BibleSection` 默认 `open=false`（`:8–9,20–25`） |
| 4l | 留言 500 字、5 条待处理上限说明 | 通过 | `NotesPanel.tsx:24` `maxLength={500}`；`pending>=5` 禁用并提示「已有 5 条待下发留言，等主编处理后再留一句。」（`:14–16,25–26`）；待下发/已下发到第 n 章/采纳 (`:30–32`) |
| 4m | 删除二次确认、「更多」菜单 | 通过 | `confirm()`（`NovelWorkbench.tsx:171`）；`<details>`「更多」内 `btn-danger`（`:201`） |
| 4n | `<dialog>` 打开/关闭/Esc/焦点 | 通过 | `showModal()` 挂载、卸载 `close()`（`NovelSettingsDialog.tsx:17`）；`onCancel` 忙碌时阻止、否则关闭（`:31`）；`aria-labelledby`（`:31–32`）；原生 `showModal` 自动聚焦首个可聚焦元素并在关闭时还焦；iframe 内 Esc 关抽屉的监听在有 `dialog[open]` 时让路（`NovelShell.tsx:10`） |
| 4o | 关卡横幅 §5.4 全部状态与操作、loading 防重 | 通过 | `GateBanner.tsx:16–44` 逐状态；按钮 `disabled={busy}` 且文案变「正在处理…」（`:17`）；页头暂停/继续/调整/导出/删除 `disabled={!!busy}`（`NovelWorkbench.tsx:197–201`）；`mutating` 互斥（`:135–136`）；`setup_running` 行「主编正在生成罗盘和设定…」（`:205`）；重定稿「会再次扣除草莓」（`PlanEditor.tsx:37`）；byok_unavailable「去设置启用」嵌入时 postMessage、独立页 `router.push("/settings")`（`NovelWorkbench.tsx:206`） |
| 5a | 按钮 `type`、aria-label、label 关联 | 通过 | 检索 `<button` 无 `type=` 的 0 命中；宿主关闭按钮 `aria-label="收起书斋"`（`app/page.tsx:2746`）；向导 `htmlFor`（`NovelWizard.tsx:138,152`）、留言 `htmlFor`（`NotesPanel.tsx:23`）、改稿 `htmlFor`（`ChapterReader.tsx:38`），其余为包裹式 `<label>`；下拉框配 `sr-only` 文字（`NovelModelFields.tsx:29`）；iframe 有 `title`（`app/page.tsx:2748`） |
| 5b | 正文去掉首行「# 第n章 标题」 | 通过 | `ChapterReader.tsx:9–11` 正则剥离首行并单独显示标题（`:34`） |
| 5c | 不引入 Markdown 库/组件库 | 通过 | 新文件 import 只有 `react`、`next/*`、`lucide-react`（既有依赖）与仓库内模块；`package.json`/lockfile 不在 diff 中 |
| 5d | 无 `dangerouslySetInnerHTML` 渲染模型文本 | 通过 | 新代码 0 命中；模型 JSON 一律经 `ContentValue` 以文本/列表渲染（`NovelContent.tsx:26–34`）；`InkLandscape` 的 innerHTML 为既有静态插画 |
| 6a | 抽屉照抄「设置」结构与 `drawerStyle`、不卸载 iframe、`novel-drawer`、高亮一致 | 通过（有两处细节差异，见可优化 4） | `app/page.tsx:2721–2750`：同宽度公式、`lens={false} backdrop={false}`、`drawerStyle(novelOpen)`、`willChange`、同 class 串；iframe 常驻不随开关卸载（`:2748`，源码测试 `test_novel_p2_frontend.py:42` 亦断言）；`id="novel-drawer"`；Sidebar 高亮 `drawerActive`/`anyDrawer` 加入 `novelActive`（`Sidebar.tsx:88–89`） |
| 6b | 未改变已有 5 项与其他抽屉行为 | 通过 | diff `p2.diff:123–210` 对 page.tsx 只有新增类型值、新增状态/监听、Sidebar 两个新 prop、新增一段 Glaze；其他四个抽屉未触碰；`anyDrawerOpen` 背板逻辑沿用 `drawer !== null`（`app/page.tsx:495`） |
| 6c | postMessage 安全 | 通过 | 宿主同时校验 `event.origin === location.origin` 与 `event.source === iframe.contentWindow`，只认两个固定 `type`（`app/page.tsx:480–494`）；iframe 侧 `targetOrigin` 为自身 origin（`NovelShell.tsx:11`、`NovelWorkbench.tsx:206`）；`target="_blank"` 均带 `rel="noopener noreferrer"` |
| 7a | `useSearchParams` 包 Suspense | 通过 | 三个页面均在 `<Suspense>` 内读取（`app/novels/page.tsx:8`、`new/page.tsx:8`、`[id]/page.tsx:8–15`），符合本地 Next 文档 `use-search-params.md:181` 的生产构建要求 |
| 7b | 动态路由参数取法 | 通过 | 客户端组件用 `useParams<{id:string}>()`（`[id]/page.tsx:9`），文档 `dynamic-routes.md:86` 允许，无需处理 Promise `params` |
| 7c | effect 依赖与清理 | 通过 | 轮询 `setTimeout` 链 + `visibilitychange` + 清理（`NovelWorkbench.tsx:92–109`、`NovelShelf.tsx:40–52`）；`useAccountRequest` 在账号切换/卸载时 abort（`lib/useAccountIdentity.ts:36–41`）；对话框卸载 `close()`；Escape 监听卸载移除（`NovelShell.tsx:14`）；estimate 防抖清理（`NovelWizard.tsx:91`）。书架在 `running` 翻转时会多发一次立即刷新（`:46,52`），无害 |
| 7d | key 使用 | 通过 | 列表 key 用章号/id，有回退（`ChapterList.tsx:24`、`DeliberationTimeline.tsx:47,61,65,72`）；按账号/书/章重挂载 `key={owner}`、`${owner}:${id}`、`${id}:${selectedChapter}`、`bible.version`、`${chapter}:${updated_at}`（`NovelShelf.tsx:18`、`NovelWorkbench.tsx:30,209–211`）；`PlanEditor` 场景用索引 key（`:27`）属按位编辑可接受 |
| 7e | 受控组件 | 通过 | 所有 input/textarea/select/radio/checkbox 均 `value|checked` + `onChange`；禁用的未选角色下拉 `value` 回退首项（`NovelModelFields.tsx:29`）只做展示 |
| 7f | 运行时错误风险 | 通过 | 后端字段形状逐一核对：`config.target/adaptation/batch_size/panel_mode/agents/automation` 来自 `CreateNovel.model_dump()`（`service.py:54–62`）；`chapters[].chapter/title/status/words/flags`（`:205`）；`notes[].adopted/response`（`:233–234`）；`catalog.agents/models/allowed_models/byok/notice`（`:164`）；细纲 `scenes[].location/summary` 经 schema 保证非空字符串（`schemas.py:372–375`），`PlanEditor.tsx:17` 的 `.trim()` 不会落空。`findLast/.at/structuredClone` 为仓库新引入（见可优化 8） |

## 5. 对实施方自报的核对

- 报告称「360px 底栏源码计算可容纳，未擅改原五项样式」——核实为真（第 3 项）。
- 报告称「正文 max-w-[38em]、行距 1.95；输入 16px；可点 ≥40px」——核实为真。
- 报告称「无新颜色值、字体或全局样式；状态不用朱印」——核实为真。
- 报告称「现有 ErrorNotice/EmptyState/LoadingState 未导出故在 novel 目录复刻」——核实为真（`AgentExchangeWorkspace.tsx:475–485` 为模块内函数），复刻版把错误色从 `text-destructive` 改成 `--ink`（`NovelStates.tsx:5`），不违反规格。
- 报告未提及的问题：M1（平板宿主横滚）、可优化 3（独立页侧栏拉伸）、可优化 5（错误双显）。
- 报告把 N+1 请求写成「实现决定」，但规格 §8 要求遇后端字段不足应停下来问，此处属于流程偏差，交作者定夺。
