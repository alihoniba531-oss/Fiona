# 返修单 R2：案头第一期

R1 之后，机械门禁、变异测试、三个宽度的界面走查都通过了。随后的独立复核（报告在同目录 `05-review.md`，请完整读一遍，尤其第 3、4、6 节和附录脚本）结论是不通过：必须修复 2 条，另有若干可优化项，规格作者采纳了其中大部分。

规格已改成 v1.2：**先读 `docs/tasks/2026-11-10-desk-board/02-spec.md` 第 11 节（共 11 小节）**，它就是这一轮的完整要求；与前文不一致时以第 11 节为准。本单只做概括。

沿用全部硬规矩：只改白名单内的文件；`backend/` 下只许动 `tests/test_desk_*.py`（`test_ui_closeout_dialog_scrim.py` 保持 R1 的状态，不要再动）；不装依赖；不提交、不 stash、不切分支；任务目录下 `01`–`06` 开头的文件和 `design/` 不要改。`frontend/app/page.tsx` 本轮只许改规格 11.3 说的那一处判断和对应的 import 行。不许改 `lib/useRovingTabs.ts`、`lib/useAccountIdentity.ts` 以及任何既有组件。

## 要做的事（细节以规格第 11 节为准）

| 规格小节 | 内容 | 主要文件 |
|---|---|---|
| 11.1 | 两处加载卡死：写后刷新先判所选书；候选、导出各用独立读作用域；排查同类标志 | `DeskDock.tsx` |
| 11.2 | 409 只有版本真的变了才算冲突；新增 `isRevisionConflict` | `lib/desk.ts`、`DeskDock.tsx` |
| 11.3 | 自动打开与恢复打开不抢焦点；新增 `deskAutoOpens` 并在 `page.tsx` 用它 | `lib/desk.ts`、`DeskDock.tsx`、`page.tsx` |
| 11.4 | 关闭后不再发任何 GET；`resize` 只在打开时监听 | `DeskDock.tsx` |
| 11.5 | 定位时清 `planNotice`；对话框开着时忽略定位 | `DeskDock.tsx` |
| 11.6 | 细纲错误转中文；`DeskDialog` 在 busy 时 Esc 不关；成功后焦点落到面板 | `DeskDock.tsx`、`DeskDialogs.tsx` |
| 11.7 | `aria-orientation`、方向键跳过置灰阶段、展开按钮 `aria-label`、空列表语义 | `DeskFrame.tsx`、两个视图 |
| 11.8 | 两处文案、`localStorage` 访问包 try/catch | 视图、`DeskFrame.tsx`、`DeskDock.tsx` |
| 11.9 | 测试：朱色绑定标签；容器竞态用例；两个新函数；六处断言绑定元素 | `backend/tests/test_desk_*.py` |
| 11.10 | 文档与实施记录改对 | 四份文档、`impl/主代理.md` |

## 这一轮特别要注意的

1. **先复现再修。** 11.1 的两个场景，先把 `05-review.md` 附录的脚本改造成新测试 `backend/tests/test_desk_dock_races_frontend.py`，在**修复前**跑一次确认它是红的，再修，再确认变绿。报告里写出修复前后的输出。
2. **新测试都要能区分对错实现。** 11.9 列的每一条，改完后把对应实现改坏一次确认变红，再还原。特别是「已批准」朱色那条：把朱色从标签挪到汇总行，用例必须变红。
3. **不要顺手重构。** `DeskDock.tsx` 只按 11.1–11.6、11.8 改，不调整无关结构。
4. 这一轮文件之间依赖紧，**由你自己直接改，不要调用 subagent / subagent_fork / workflow**。

## 验收

逐条执行规格第 7 节的 10 条命令并给出实际输出（全量仍用 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local` 前缀）。另外：

- `git diff main -- backend/tests` 仍然只有 `test_ui_closeout_dialog_scrim.py` 那一行。
- `git diff main -- frontend/app/page.tsx` 相对 R1 只多改了 11.3 那一处判断与 import 行。
- `grep -c 'deskAutoOpens(window.innerWidth)' frontend/app/page.tsx` 输出 1。

## 报告

在 `impl/主代理.md` 末尾追加「## R2」，然后回复五项：改了哪些文件；规格 11.1–11.10 各自怎么改的；逐项对应；第 7 节每条命令与上面三条附加命令的实际输出；没做完或需要人工确认的地方。
