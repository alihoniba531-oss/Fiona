# 返修单 R1：案头第一期

首轮交付的机械门禁全部通过（全量 7975 通过、0 跳过；改动都在白名单内）。下面七项来自验收方通读代码、变异测试和三个宽度的真实界面走查。规格已改成 v1.1：**先重读 `docs/tasks/2026-11-10-desk-board/02-spec.md` 的 2.6、4.2、T5、T6、T8、第 6 节、第 7 节和第 10 节**，本单与规格不一致时以规格为准。

沿用首轮的全部硬规矩：只改白名单内的文件；`backend/` 非测试文件不动；`page.tsx` 这一轮不需要改；不装依赖；不提交、不 stash、不切分支；任务目录下 `01-brief.md`、`02-spec.md`、`03-dispatch.md`、`04-fix-r1.md`、`design/` 不要改。

## 必须修复

### 1. 对话框不许躲开门禁扫描

- 现状：`frontend/components/desk/DeskDialogs.tsx` 用 `React.createElement("dialog", …)` 生成对话框，理由是既有测试写死了全仓 13 个 JSX `<dialog`。这让新对话框躲开了「每个 dialog 必须带 scrim-dialog」的扫描，不接受。
- 改法：`DeskDialog` 包装组件改回 JSX：`<dialog ref={ref} aria-labelledby={labelledBy} className={sourceDialogClass} onCancel={…}>{children}</dialog>`。`DeskDialogs.tsx` 里 `<dialog` 恰好出现一次。
- **授权改一处既有测试**：`backend/tests/test_ui_closeout_dialog_scrim.py` 第 117 行 `def assert_dialogs_have_scrim(sources, *, expected_count=13):` 里的 `13` 改成 `14`。这个文件的其他任何字符都不许动；别的既有测试一个字都不许动。
- 新契约测试：`DeskDialogs.tsx` 里 `<dialog` 恰好一次；`frontend/components/desk/` 下所有文件都不出现 `createElement("dialog"` 与 `createElement('dialog'`（带自检：给一段违规文本，扫描器能抓到）。

### 2. 抽屉与半屏方式下面板必须不透明

- 现状：768–1439 宽的抽屉和手机半屏盖在聊天上面，面板是半透明釉面，聊天气泡、时间、卡片、输入框的文字透上来和案头文字叠在一起，没法读。
- 改法：`DeskFrame.tsx` 里 `mode === "drawer"` 与 `mode === "sheet"` 时给 `<aside>` 加 `bg-[color:var(--paper)]`；`mode === "dock"` 不加。

### 3. 抽屉宽度 488 → 476

- 现状：抽屉方式外层容器 `w-[488px]`，内容只有 448 + 28 = 476，右侧多出 12px 空带，书耳离视口右缘 24px，和其他抽屉（12px）不齐。
- 改法：抽屉方式外层容器改成 `w-[476px]`。并排方式保持 `w-[488px] py-3 pr-3` 不变。

### 4. 手机半屏高度

- 现状：`height: "56dvh"`。在 390×844 的手机上，头部到输入区之间只有约 556px，半屏盖掉了其中 85%，聊天几乎看不到。
- 改法：半屏（未展开）高度改成 `min(45dvh, calc(100dvh - 94px - env(safe-area-inset-top) - var(--tabbar-h) - env(safe-area-inset-bottom) - ${composerHeight}px))`。展开后的写法不变。

### 5. 分集版本冲突的提示丢了

- 现状：修改某一集时如果方案已在别处改动（409），容器刷新方案并抛出带冲突文案的错误；但单集修改框以 `key={plan.plan_revision}` 挂载，方案一刷新它就被重新挂载，错误提示和作者刚填的内容一起消失，界面上没有任何反馈。（已用真实界面复现：先在别处改一次，再点保存，对话框回到原始内容、没有提示。）
- 改法：
  - `DeskDock.tsx`：新增状态 `planNotice: string | null`。`operatePlan` 与 `approvePlan` 遇到 409 时，刷新方案、`setPlanNotice("分集方案已在别处改动，已为你刷新，请再试一次。")`，然后**正常返回，不再抛错**。`planNotice` 在这些时刻清空：一次修改、合并或批准成功之后；切换项目；切换作品（`resetEpisodes`）；点「刷新」。409 之外的错误照旧抛出。
  - `DeskEpisodesView.tsx`：新增 prop `notice: string | null`；非空时在方案汇总行下面显示 `<p role="alert" className="…text-fs-13…">{notice}</p>`。

### 6. 没有分集的项目只显示空提示

- 现状：项目没有分集时（`plan.episodes.length === 0`），页面仍显示「方案第 0 版　共 0 集　约 0 分 0 秒」、「待批准」标签和禁用的批准栏。
- 改法：`plan.episodes.length === 0` 时只显示「还没有分集方案，拆解在工作室里做。」和文字按钮「在工作室打开」；不显示汇总行、状态标签、提示行与底部批准栏。

### 7. 三处测试盲区

把下面三处实现各改坏一次，现有 64 个新用例全部照样通过，说明没有用例盯着它们：

| 改坏的地方 | 应该变红却没变红 |
|---|---|
| `DeskChaptersView` 里「读正文」不再判断 `chapter.chapter <= book.chapters_done` | 无 |
| `DeskEpisodesView` 里「已批准」标签不再加朱色两类 | 无 |
| `DeskEpisodesView` 里「与下一集合并」不再对最后一集禁用 | 无 |

原因是这些按钮只在行展开后才渲染，而服务端渲染时行都是收起的。改法：

- `DeskChaptersView` 与 `DeskEpisodesView` 各加一个可选 prop `initialExpanded?: number | null`（默认 `null`），只作为展开状态 `useState` 的初值；`DeskDock` 不传。
- 按规格 T8 里标了「（v1.1）」的几条补用例（章回页两条、分集页四条、面板骨架一条、契约一条）。每条都要能区分对错实现：对上表三处各自再改坏一次，确认对应用例变红，再还原。

## 验收

逐条执行规格第 7 节的 10 条命令并给出实际输出。其中：

- 全量：0 failed、0 skipped，通过数 = `7911 + 新增用例总数`。你的环境里 `NO_PROXY` 含 `[::1]` 会让 httpx 在收集阶段报错，照首轮的办法设 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local` 再跑。
- `git diff main -- backend/tests` 只有 `test_ui_closeout_dialog_scrim.py` 里一行删、一行增。
- `grep -c '<dialog' frontend/components/desk/DeskDialogs.tsx` 输出 1；`grep -rc 'createElement("dialog"' frontend/components/desk/` 每个文件都是 0。

## 报告

在 `docs/tasks/2026-11-10-desk-board/impl/主代理.md` 末尾追加「## R1」一节，然后回复五项：改了哪些文件；七项各自怎么改的；与上面七项的逐项对应；第 7 节每条命令的实际输出；没做完或需要人工确认的地方。同时把文档里与本轮变化有关的描述改对（`CLAUDE.md` 等四份文档里若写了 56dvh、488 抽屉宽或冲突时对话框显示提示，要同步）。

这一轮改动小，文件之间有先后依赖，**不需要并行，由你自己直接改**；不要调用 subagent / subagent_fork / workflow。
