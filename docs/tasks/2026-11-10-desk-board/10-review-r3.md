# 案头第一期 · 第三轮独立复核报告

复核对象：基线 `9adf34c` 之上、R4 之后的工作区。依据是规格 v1.4（`02-spec.md`，重点第 13 节）和 `.cache/review/r3-to-r4.diff`。实施方报告（`impl/主代理.md` 的「## R4」）和验收方记录（`gate-notes.md`）只当线索；下面的结论都来自复核方自己跑的命令、读的代码和做的实验。复核方没有启动浏览器或 dev server，没有访问网络。

本轮只核验三件事：第二轮必须修复 5.1–5.3、第 13 节 13.1–13.6、R4 有没有引入新错误；另外重跑第 7 节 10 条验收命令。

**R3 对照快照**：把 `r3-to-r4.diff` 里三个前端源码文件的部分用 `patch -R` 反向应用到副本上，在 `.cache/r3-scratch/r3/` 还原出 R3 时的 `DeskDock.tsx`、`DeskEpisodesView.tsx`、`DeskDialogs.tsx`。还原结果与第二轮报告引用的行号一致（`busy={busy || …}` 在第 252、262、279 行，`onClose={() => onOpenChange(false)}` 在第 1015 行）。

**行为探针**：第二轮附录 A、B 的探针原样取用，只给附录 A 加了一个 `DESK_DIR` 环境变量，用来切换加载 R3 快照的 `DeskDock.tsx`。另外新写了一个探针 `desk-r3-harness.js`（附录 A）。原来的探针只运行 `DeskDock` 一个组件，视图都是桩。新探针用一个最小的函数组件协调器，同时运行真实的 `DeskDock.tsx`、`DeskEpisodesView.tsx`、工作室的 `EpisodeEditDialog` / `BreakdownDialog`，以及 `useAccountIdentity.ts`、`desk.ts`。协调器给每个组件实例单独的 hook 槽位，子组件的 effect 先于父组件执行，卸载时执行 cleanup，元素的 key 变化时重新挂载。只有 DeskFrame（换成只渲染 children 的桩）、章回与细纲视图、NovelStates、Glaze 和后端是桩。这样就能按作者的真实操作走一遍：展开、点「修改」、填字、保存、遇到 409、点「取消」或按 Esc、收到卡片。全部脚本、日志和变异记录都在 `.cache/r3-scratch/`。

## 1. 结论

**不通过。** 有 1 条必须修复，只涉及测试文件。

第二轮的 3 条必须修复都已修好：

- 5.1、5.2 先在 R3 快照上复现，再在当前代码上证明修复有效；
- 5.3 的四个变异各自让对应用例变红。

其余核验：

- 第 13 节 13.1–13.5 的实现都符合规格；13.6 列出的测试都有，除下面这一条外都能区分对错实现。
- 第 7 节 10 条验收全部符合：全量 `8011 passed`，0 失败、0 跳过；新测试 100 条。
- R4 没有引入新的错误行为：
  - `onDialogOpenChange` 在打开、关闭，以及收起案头、切阶段、切项目导致的卸载时都会正确复位，不会让容器一直忽略定位；
  - 分集对话框从来不参与轮询暂停，所以也不会让轮询一直暂停；
  - `closeFromPanel` 收起后焦点落在头部开关上；
  - 收起时 `setMode(null)`，重开的第一帧什么都不渲染，然后按当前宽度渲染；
  - `initialDialog` 只出现在视图的初值里，`DeskDock` 和 `page.tsx` 都不传。

问题出在 13.6 明确要求的容器用例：「非冲突 409：……方案已刷新」没有证明力（见 5.1）。

- 原因：探针夹具 `let locked = LOCK;` 让方案在第一次载入时就已经是锁定的。409 之后断言的「第 5 版、running」和操作前完全一样，刷新与否都会通过。
- 证明：变异 G9 让非冲突 409 之后不替换方案，违反 11.2「取到就替换当前方案」，100 条新测试全部通过。
- 修法：改一行夹具，再加一条断言。

## 2. 上一轮必须修复 3 条的核验

### 2.1 必须修复 5.1：非冲突 409 后分集对话框锁死，已修好

**先复现（R3 快照）。**

- 附录 A 探针的 `lock409edit` / `lock409approve` 在 R3 快照和当前代码上输出相同：非冲突 409 之后方案被刷新成锁定状态，`editsBlocked: true, approvalBlocked: true`。这是 11.2 规定的容器行为，R4 没有改它，也不应改。
- 这个探针里的 `dialogBusyProp` 是探针自己按旧写法 `busy || editsBlocked` 算出来的，不读视图，所以判断不了 R4 有没有修好。修复与否要看视图把什么传给对话框。
- 附录 B 用真实对话框组件做服务端渲染：`busy=true` 时「取消」「保存」和 `fieldset` 都带 `disabled`。所以视图绝不能把锁定状态并进 `busy`。

**再证明修复有效（附录 A 新探针，真实的 DeskDock、DeskEpisodesView 和两个对话框组件）。**

操作序列：

1. 载入未锁定的第 5 版方案。
2. 展开第 1 集，点「修改」，在标题框里填「作者刚改的标题」。
3. 这时后端开始重新拆解，版本号不变。
4. 点「保存」，得到 409。
5. 再点一次「保存」。
6. 按 Esc。
7. 再来一张指向同书另一个项目 p1 的卡片。

合并、批准两条路径同理，只是没有填字和第 5 步。

| 时刻 | R3 快照 | 当前代码（R4） |
|---|---|---|
| 第一次确认（409）后：方案 | 第 5 版，`running` | 第 5 版，`running` |
| 同上：对话框里的提示 | 「拆解尚未完成，完成后才能修改分集方案」 | 同左（后端真实原因） |
| 同上：「取消」 | `disabled` | 可用 |
| 同上：标题框内容 | 「作者刚改的标题」 | 「作者刚改的标题」（保留） |
| 锁定态再点「保存」 | 按钮禁用，点不了 | 不发请求（新增 ops 请求 0 次），对话框显示「拆解还没全部完成，暂时不能修改或批准，去工作室看进度。」，填的字仍在 |
| 按 Esc | `prevented`，对话框仍在 | `closed`，对话框关闭 |
| 合并：409 后 | 「取消」`disabled`，Esc 被拦 | 「取消」可用，「确认合并」`disabled`，Esc 能关 |
| 批准：409 后 | 「取消」`disabled`，Esc 被拦 | 「取消」可用，「确认批准」`disabled`，Esc 能关 |
| 关掉对话框后来卡片 p1 | —（对话框关不掉） | 定位生效：项目切到 p1，「工作室来源」请求 +1。说明容器没有一直以为有对话框开着 |

**代码位置**（`frontend/components/desk/DeskEpisodesView.tsx`）：

- 第 268 行：修改对话框 `busy={busy}`；
- 第 269–274 行：`onSave` 在 `editsBlocked` 时 `Promise.reject(new Error("拆解还没全部完成，暂时不能修改或批准，去工作室看进度。"))`；
- 第 283–284 行：合并确认 `busy={busy}`、`disabled={editsBlocked}`；
- 第 301–302 行：批准确认 `busy={busy}`、`disabled={approvalBlocked}`；
- 第 210、218、253 行：打开这三个对话框的按钮仍按锁定状态禁用；
- `grep -c 'busy={busy || '` 为 0。

**测试**：`test_locked_plan_dialogs_keep_cancel_enabled` 的三个参数各自对应一个变异：

| 变异 | 结果 |
|---|---|
| E1（修改对话框的 `busy` 改回含锁定状态） | `[edit-None]` 变红 |
| E2（合并的 `busy` 改回含锁定状态） | `[merge-确认合并]` 变红 |
| E3（批准的 `busy` 改回含锁定状态） | `[approve-确认批准]` 变红 |
| E4（去掉合并的 `disabled`） | 合并用例变红 |
| E5（去掉批准的 `disabled`） | 批准用例变红 |

### 2.2 必须修复 5.2：从面板收起后焦点丢到 body，已修好

附录 A 探针（第二轮附录 A 原样，`DESK_DIR` 切换 R3 快照）：

| 场景 | R3 快照 | 当前代码 |
|---|---|---|
| `xclose-restore`（刷新后恢复打开） | `{"focusAfterOpen":"body","focusAfterClose":"body"}` | `{"focusAfterOpen":"body","focusAfterClose":"头部「案头」开关"}` |
| `xclose-auto`（卡片自动打开） | `{"focusAfterOpen":"输入框","focusAfterClose":"body"}` | `{"focusAfterOpen":"输入框","focusAfterClose":"头部「案头」开关"}` |
| `xclose-hand`（亲手打开，对照） | `{"focusAfterOpen":"案头面板 #desk-panel","focusAfterClose":"头部「案头」开关"}` | 同左 |

打开一侧的 11.3 规则没有被带坏：自动打开时焦点仍在输入框，恢复打开时仍在 body。新探针的 `reopen-hand` 场景依次做了这些操作：亲手打开、用头部开关收起、再亲手打开、再用开关收起、焦点在 body 时恢复打开、点 X 收起。焦点依次落在面板、开关、面板、开关、body、开关，正确。R3 在最后一步落到 body。

**代码位置**：

- `DeskDock.tsx` 第 252–255 行的 `closeFromPanel` 与规格 13.2 的代码逐字相同；
- 第 1028 行 `onClose={closeFromPanel}`；
- Esc 路径（第 927–938 行）未变。

**测试**：变异 F1（`onClose` 改回 `() => onOpenChange(false)`）让 `test_close_from_panel_restores_focus_after_auto_open` 与 `…_after_restore_open` 两条变红。

### 2.3 必须修复 5.3：四处断言绑到元素上，已修好

`backend/tests/test_desk_views_frontend.py` 第 203–233 行新增三个检查器：

- `assert_tablist_orientation`：取 `role="tablist"` 的开标签。竖排要求它自己带 `aria-orientation="vertical"`，且整页只出现 1 次；横排要求它不带，整页也没有。
- `assert_expand_label`：在带 `aria-expanded` 的按钮开标签里找 `aria-label`。
- `assert_unique_tab_stop`：用 `stage="episodes"` 渲染，唯一的 `tabindex="0"` 必须同时带 `data-stage="episodes"` 和 `aria-selected="true"`，其余四个是 `tabindex="-1"`。

三个检查器都配了自检：属性挪到外层容器或整行、`aria-selected` 改到别处时，检查器报错（第 746–759、770–775、801–806、825–829 行）。

复核方把上一轮四个变异各做了一次（跑全部 100 条，跑完按原字节还原）：

| 编号 | 变异 | 结果 |
|---|---|---|
| R5A | `DeskFrame.tsx`：`aria-orientation` 从竖排 `<nav role="tablist">` 挪到外层容器 `<div>` | 1 failed：`test_frame_uses_opaque_drawer_and_sheet_and_correct_width_and_height` |
| R5B | `DeskChaptersView.tsx`：展开按钮的 `aria-label` 挪到 `role="listitem"` 的整行 | 1 failed：`test_chapter_expand_button_has_accessible_label` |
| R5C | `DeskEpisodesView.tsx`：同上 | 1 failed：`test_episode_expand_button_has_accessible_label` |
| R4C | `DeskFrame.tsx` 两处 `const selected = index === stageIndex` 改成 `index === 0` | 1 failed：`test_stage_tabs_expose_exactly_one_tab_stop_in_both_orientations` |

## 3. 规格第 13 节逐小节核验

| 小节 | 是否符合 | 证据 |
|---|---|---|
| 13.1 非冲突 409 后对话框关得掉 | 符合 | 见 2.1。三个对话框都是 `busy={busy}`；合并、批准另加 `disabled`；修改在锁定时拒绝保存，文案与 4.4 逐字一致。打开对话框的按钮仍按锁定状态禁用。`initialDialog` 的类型与规格一致，只在三个 `useState` 初值里使用（第 67–75 行）；`grep` 确认 `DeskDock.tsx` 与 `page.tsx` 里没有 `initialDialog` / `initialExpanded`。底线行为（能取消、能按 Esc、保留内容、显示后端原因）由新探针证实。 |
| 13.2 面板收起还焦点 | 符合 | 见 2.2。 |
| 13.3 四处断言绑元素 | 符合 | 见 2.3。 |
| 13.4 定位避开分集三个对话框 | 实现符合（测试只有字面量契约，见可优化 1） | **视图**（`DeskEpisodesView.tsx`）：第 76 行 `dialogOpen = editing !== null \|\| merging !== null \|\| approving`；第 78–81 行用 effect 在变化时通知，卸载时若开着再补一次 `false`。**容器**（`DeskDock.tsx`）：第 171 行 `episodeDialogOpenRef`；第 177–184 行把它并入 `dialogOpenRef`；定位入口（第 739 行）与两处回包检查（第 766、786 行）都看 `dialogOpenRef.current`；第 984 行传入回调。**探针结果**：<br>① `focus-edit` / `focus-merge` / `focus-approve`：对话框开着来卡片 p1，「工作室来源」请求 0 次，对话框和填的字都在，项目仍是 p2；点「取消」后再来一张卡片，定位到 p1。R3 快照上同一操作，对话框被卸掉，项目被换成 p1。<br>② 卸载时复位：开着修改框时程序性收起案头、切到章回再切回、切到章回停住、切换项目（key 变化重挂），之后来的卡片都正常定位。<br>③ 轮询：分集对话框本来就不参与轮询暂停，两个轮询 effect 只看 `planDialog` / `readerDialog`，与规格一致，因此不存在「一直暂停轮询」的路径。<br>④ 回调依赖 `planDialog` / `readerDialog`，引用变化时视图 effect 先用旧回调补 `false`，再用新回调报当前值，最终状态正确。视图挂载期间这两个值不会变化。 |
| 13.5 两处小修 | 实现符合（测试只有字面量契约，见可优化 1） | **细纲「关闭」**：`DeskDialogs.tsx` 第 72 行 `disabled={busy}`。**清空呈现方式**：`DeskDock.tsx` 第 731 行 `setMode(null)`，位于收起 effect 的 rAF 里。**探针 `reopen-width`**：在 1500 宽打开，收起，宽度改成 500 再重开，逐帧记录 DeskFrame 的 `mode`。R4 是 `[null, "sheet", …]`，第一帧不渲染；R3 快照是 `["dock", "sheet", …]`，第一帧还是并排。亲手重开仍会把焦点移到面板（2.2 的 `reopen-hand`）。补充：收起后不到一帧又重开时，这个 rAF 会被 cleanup 取消，`mode` 不会被清空。人手做不到这么快，不影响结论。 |
| 13.6 测试补充 | **部分不符合** | 逐条：<br>• **视图·锁定对话框**：有，E1–E5 都能抓到。<br>• **容器·非冲突 409**：「被拒绝并带后端原因」「`planNotice` 为 null」有证明力，变异 G2「所有 409 都当冲突」会变红；**「方案已刷新」没有证明力**，变异 G9 全过，见必须修复 5.1。<br>• **容器·真冲突**：有，变异 G3「都不当冲突」变红。<br>• **容器·焦点**：自动打开后收起、恢复打开后收起、亲手打开后收起三条都有，F1、G4（自动打开也抢焦点）都会变红。<br>• **容器·定位请求被取消后重开会重新定位**：有，G1（请求一发出就记为已处理）变红。<br>• **逻辑**：竖排 Home、横排 End 都有，G5、G6 变红。<br>• **视图·无 reason 文案完整等于**：有，G7（自拟后半句）、G8（只多一个空格）都变红。 |

## 4. 验收标准逐条核验（第 7 节）

本副本里 `main` 指向 `9adf34c`。

| # | 命令 | 实际输出 | 是否符合 |
|---|---|---|---|
| 1 | `cd backend && NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 .venv/bin/python -m pytest -q -p no:cacheprovider`（本机 `NO_PROXY` 含 `[::1]`，按说明覆盖） | `8011 passed, 35 warnings in 341.77s (0:05:41)`，退出 0；日志里没有 failed 或 skipped。8011 = 7911 + 100。在任何变异之前跑完 | 符合 |
| 2 | `.venv/bin/python -m pytest -q tests/test_desk_*.py -rsf` | `100 passed in 42.20s`，没有 skip 或 fail 摘要。按文件：契约 43、竞态 12、逻辑 14、视图 31 | 符合 |
| 3 | `cd frontend && npx tsc --noEmit` | 无输出，`TSC_EXIT:0` | 符合 |
| 4 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`，`LINT_EXIT:0`；`npx eslint components/desk lib/desk.ts` 无输出 | 符合 |
| 5 | `cd frontend && npm run build` | 路由表正常（含 `/novels`、`/studio/[id]`、`/studio/kb`），`BUILD_EXIT:0`；构建后 `git status` 与构建前一致 | 符合 |
| 6 | `git status --porcelain --untracked-files=all`（排除 `.cache/`） | 修改：`CLAUDE.md`、`PLAN.md`、`README.md`、`docs/ARCHITECTURE.md`、`frontend/app/page.tsx`、`backend/tests/test_ui_closeout_dialog_scrim.py`。新增：四个 `backend/tests/test_desk_*.py`、六个 `frontend/components/desk/*.tsx`、`frontend/lib/desk.ts`、`impl/主代理.md`，以及作者的 `01`–`09` 与 `design/` | 符合 |
| 7 | `git diff --stat main -- backend ':!backend/tests'`；`git diff --numstat main -- backend/tests` | 前者为空；后者只有 `1	1	backend/tests/test_ui_closeout_dialog_scrim.py`，即 `expected_count=13` → `expected_count=14` | 符合 |
| 8 | `git diff main -- frontend/package.json frontend/package-lock.json` | 空 | 符合 |
| 9 | 七条字面量逐条 `grep -cF`；`head -c 3 frontend/app/page.tsx \| xxd -p` | 依次 `1 2 1 1 1 2 1`；`efbbbf` | 符合 |
| 10 | `grep -rc 'createElement("dialog"' frontend/components/desk/`（另查单引号写法）；`grep -c '<dialog' frontend/components/desk/DeskDialogs.tsx` | 六个文件两种写法都是 0；`<dialog` 为 1 | 符合 |

返修单的附加检查：

- `git diff main -- frontend/app/page.tsx | shasum -a 256` 为 `825086b0…187d4b`，与 R3 相同；
- `grep -c 'busy={busy || ' DeskEpisodesView.tsx` 为 0；
- `git diff main` 对以下路径都为空：`components/studio`、`components/novel`、`lib/useRovingTabs.ts`、`lib/useAccountIdentity.ts`、`lib/novels.ts`、`lib/studio.ts`、`lib/studio-breakdown.ts`、`app/globals.css`；
- `git diff main` 与 `.cache/review/diff.patch` 逐字节相同；
- `r3-to-r4.diff` 里的源码改动只有 `DeskEpisodesView.tsx`、`DeskDialogs.tsx`、`DeskDock.tsx` 三个文件，与任务说明一致。

## 5. 必须修复

### 5.1 13.6「非冲突 409 ……方案已刷新」的容器用例没有证明力

**文件与行**（`backend/tests/test_desk_dock_races_frontend.py`）：

- 探针 `NODE_FOCUS_DRIVER` 第 327 行 `let locked = LOCK;`（第 328 行 `let operationConflict = LOCK || CONFLICT;`）；
- 第 408–428 行的 `lockScenario`，第 412 行日志写着「载入未阻塞方案后」；
- 断言在第 513–531 行 `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan`。

**现象**：

- `lockedit` / `lockapprove` 场景里 `LOCK` 为真，所以案头第一次取到的方案就已经是锁定的（`active_breakdown_status: "running"`、`rebreakdown_pending: true`、第 5 版），与日志说的「未阻塞」相反。
- 409 之后断言的 `planRevision == 5`、`activeStatus == "running"` 与操作前完全相同。不管容器有没有刷新、有没有替换方案，这两条都会通过。

**为什么是问题**：

- 规格 13.6 明确要求这条容器用例证明三件事：「操作被拒绝并带后端原因、planNotice 为 null、方案已刷新」。
- 11.2 要求非冲突 409「先重新取分集方案（取到就替换当前方案）」，正是这一步让视图显示「拆解还没全部完成…」并锁住入口按钮。
- T8 总则要求「每条断言都要能区分对错实现」。现在第三件事的断言区分不了对错，属于「让测试失去证明力」。

**证明**：

1. 在探针里打印操作前的方案，两个场景都是 `{"planRevision":5,"activeStatus":"running","rebreakdown_pending":true}`，与操作后一样。
2. 变异 G9：`refreshPlanAfterConflict` 不再 `setPlan`，`operatePlan` / `approvePlan` 只在真冲突时替换方案。这是一种「只在版本变了才替换」的错误实现，违反 11.2。结果 `100 passed`。
3. G9 下用新探针跑 `edit409`（方案先是未锁定的）：
   - 409 之后方案仍是 `done`，视图不显示「拆解未完成」；
   - 作者再点「保存」会再发一次请求（ops 计数从 1 到 2），再收到一次 409。
   - 当前代码在这一步是 `running`，再点「保存」不发请求。
4. 把建议的改法做在副本 `.cache/r3-scratch/test_fixcheck_races.py` 上验证：
   - 当前代码 2 条全过；
   - G9 让非冲突用例变红；
   - G2 仍让非冲突用例变红，G3 仍让冲突用例变红。

**建议改法**（只改这一个测试文件）：

1. 第 327 行改成 `let locked = false;`。`lockScenario` 在发操作前已经会把 `locked` 置真，不用另改。
2. `lockScenario` 在置真之前记下 `view.plan.active_breakdown_status`，随结果一起输出（例如字段名 `beforeActive`）。
3. 用例里对修改、批准两个场景都断言 `beforeActive == "done"`，并保留 `activeStatus == "running"`。
4. 第 412 行的日志文字与实际一致。

## 6. 可优化

规格 13.7 留给作者裁定的几点和前两轮已列过的可优化项不再重复。

1. **13.4、13.5 和 13.1 的「锁定时不发请求」没有行为用例。** 13.6 没有要求，所以不列为必须修复。下面这些变异都是 `100 passed`，而新探针显示行为确实变了：

   | 变异 | 测试结果 | 探针看到的行为 |
   |---|---|---|
   | E6：`onSave` 里 `if (editsBlocked)` 改成 `if (false)` | 全过 | 锁定态再点「保存」会再发一次请求 |
   | F2：去掉 `\|\| value` | 全过 | 修改框开着来卡片时项目被换成 p1，对话框被卸掉 |
   | F4b：定位入口和两处回包检查都改回只看细纲/正文对话框 | 全过 | 同 F2 |
   | F3：去掉视图卸载时补发的 `false` | 全过 | 开着修改框切到章回后，再来的卡片一直被忽略 |
   | F5：把 `setMode(null)` 改成注释 | 全过 | 重开第一帧回到旧方式 |

   现有契约用例 `test_desk_episode_dialogs_join_focus_guard_and_plan_close_is_busy_disabled` 只查字面量。F5 保留了字面量、去掉了行为，照样通过。

   建议在竞态文件里补三类用例：
   - 视图桩调用 `onDialogOpenChange(true)` 后来卡片，断言不发「工作室来源」请求、项目不变；改为 `false` 后再来卡片，断言定位生效；
   - 收起后改窗口宽度再重开，记录 DeskFrame 每一帧的 `mode`；
   - 锁定方案下调用修改对话框的 `onSave`，断言 `onOperate` 没被调用。这需要能调用回调的运行时，服务端渲染做不到；可以参照附录 A。

2. **分集对话框的「开着」以组件状态为准，而不是以实际渲染出的对话框为准。**
   - 位置：`DeskEpisodesView.tsx` 第 76 行用 `editing` / `merging` / `approving` 计算 `dialogOpen`，而三个对话框只在「方案有分集」的分支里渲染（第 264–313 行）。
   - 现象：对话框开着时，如果方案变成 0 集，或视图进入候选/方案的加载、出错分支，对话框会消失，但 `dialogOpen` 仍为真。容器会一直忽略聊天卡片，直到视图卸载；分集恢复后，旧对话框还会重新弹出。
   - 复现：探针 `unmount-empty` 先得到一次非冲突 409，再让锁定轮询取回 0 集方案。之后来的卡片被忽略：「工作室来源」请求数不变，项目仍是 p2。
   - 触发条件很窄：重新拆解期间后端保留的是上一次发布的方案，模态框又挡住了「刷新」。
   - 「状态还在、对话框不渲染」在 R3 就有，R4 新增的后果是「忽略卡片」。
   - 建议：只在对话框确实渲染时才算开着，例如 `dialogOpen = !!plan && plan.episodes.length > 0 && (…)`；或者在离开方案分支时清掉这三个状态。

3. **`test_locked_plan_dialogs_keep_cancel_enabled[edit]` 只断言了「取消」可用。** 它没有确认渲染出来的是修改对话框（标题「修改第 1 集」）。`initialDialog` 的种类映射写错时，这一参数可能照样通过。可以顺手补一条标题断言。

## 7. 变异实验记录

**做法**：

- 用 `.cache/r3-scratch/mutate.py` 逐个应用变异：每次只改一处或一组，并校验匹配次数；然后跑全部 100 条新测试，或在探针模式下跑附录 A 的某个场景；最后在 `finally` 里按原字节写回，并逐个校验 sha256。
- 全量测试和构建都在任何变异之前跑完。
- 全部实验结束后，对 15 个相关文件运行 `shasum -a 256 -c`，结果全部 OK；`git status`（排除 `.cache/`）与实验前一致。

**测试变异**（每项跑 100 条新测试）：

| 编号 | 位置 | 变异 | 结果 | 结论 |
|---|---|---|---|---|
| R5A | `DeskFrame.tsx` | `aria-orientation` 挪到外层容器 | 1 failed（`test_frame_uses_opaque_drawer_…`） | 5.3 已修好 |
| R5B | `DeskChaptersView.tsx` | 展开按钮 `aria-label` 挪到整行 | 1 failed（`test_chapter_expand_button_…`） | 同上 |
| R5C | `DeskEpisodesView.tsx` | 展开按钮 `aria-label` 挪到整行 | 1 failed（`test_episode_expand_button_…`） | 同上 |
| R4C | `DeskFrame.tsx` | 两处 `selected` 钉在第一个标签 | 1 failed（`test_stage_tabs_expose_exactly_one_tab_stop_…`） | 同上 |
| E1 | `DeskEpisodesView.tsx` | 修改对话框 `busy={busy \|\| editsBlocked}` | 1 failed（`[edit-None]`） | 13.6 视图用例有证明力 |
| E2 | 同上 | 合并 `busy={busy \|\| editsBlocked}`（保留 `disabled`） | 1 failed（`[merge-确认合并]`） | 同上 |
| E3 | 同上 | 批准 `busy={busy \|\| approvalBlocked}`（保留 `disabled`） | 1 failed（`[approve-确认批准]`） | 同上 |
| E4 | 同上 | 去掉合并的 `disabled={editsBlocked}` | 1 failed（`[merge-确认合并]`） | 同上 |
| E5 | 同上 | 去掉批准的 `disabled={approvalBlocked}` | 1 failed（`[approve-确认批准]`） | 同上 |
| E6 | 同上 | `onSave` 的 `if (editsBlocked)` 改成 `if (false)` | 100 passed | 可优化 1 |
| F1 | `DeskDock.tsx` | `onClose` 改回 `() => onOpenChange(false)` | 2 failed（auto、restore） | 5.2 已修好 |
| F2 | 同上 | `handleEpisodeDialogOpenChange` 去掉 `\|\| value` | 100 passed | 可优化 1 |
| F3 | `DeskEpisodesView.tsx` | 去掉卸载时补发 `false` 的 cleanup | 100 passed | 可优化 1 |
| F4 | `DeskDock.tsx` | 定位入口改回 `planDialog \|\| readerDialog` | 100 passed | 可优化 1 |
| F4b | 同上 | 入口和两处回包检查都改回只看细纲/正文对话框 | 100 passed | 可优化 1 |
| F5 | 同上 | `setMode(null);` 改成注释 `/* setMode(null) */` | 100 passed | 契约只查字面量，可优化 1 |
| F6 | 同上 | 删掉 `setMode(null);` | 1 failed（契约字面量） | 只有字面量兜底 |
| F7 | `DeskDialogs.tsx` | 细纲「关闭」去掉 `disabled={busy}` | 1 failed（契约字面量） | 只有字面量兜底 |
| G1 | `DeskDock.tsx` | 定位请求一发出就记为已处理 | 1 failed（`test_locate_request_cancelled_by_close_retries_on_reopen`） | 13.6 有证明力 |
| G2 | 同上 | 两处 `isRevisionConflict(…)` 换成 `true` | 1 failed（`test_non_conflict_409_…`） | 有证明力 |
| G3 | 同上 | 两处换成 `false` | 1 failed（`test_real_version_conflict_…`） | 有证明力 |
| G4 | 同上 | 去掉「焦点在开关上才移焦点」 | 2 failed（auto、restore） | 有证明力 |
| G5 | `lib/desk.ts` | Home 只在横排生效 | 1 failed（逻辑用例） | 有证明力 |
| G6 | 同上 | End 只在竖排生效 | 1 failed（逻辑用例） | 有证明力 |
| G7 | `DeskEpisodesView.tsx` | 没有 reason 时自拟「暂时还不能建短片项目。」 | 1 failed（`test_episode_no_project_without_reason_…`） | 有证明力 |
| G8 | 同上 | 没有 reason 时只多一个空格 | 1 failed（同上） | 「完整等于」成立 |
| G9 | `DeskDock.tsx` | 非冲突 409 刷新后不替换方案（只在真冲突时替换） | **100 passed** | **必须修复 5.1** |
| G9′ | 同上，测试换成建议改法的副本 | 同 G9 | 1 failed（非冲突用例）；G2 → 非冲突用例红，G3 → 冲突用例红 | 建议改法有效 |

**行为实验**（只读源码，不访问网络）：

- 第二轮附录 A 探针，在 R3 快照和当前代码上各跑一遍：
  - `lock409edit` / `lock409approve`：两边相同，非冲突 409 之后方案被刷新为锁定状态（容器前提，本就不变）；
  - `xclose-restore` / `xclose-auto` / `xclose-hand`：结果见 2.2。
- 第二轮附录 B（`ssr-dialog-lock.js`）原样运行，结果与上一轮相同：`busy=true` 时「取消」「保存」和 `fieldset` 都带 `disabled`。
- 本轮附录 A 探针：
  - `edit409` / `merge409` / `approve409`，R3 与 R4 对照，结果见 2.1；
  - `focus-edit` / `focus-merge` / `focus-approve`：R4 忽略卡片、保留对话框；R3 快照卸掉对话框并换项目；
  - `unmount-close` / `unmount-stage` / `unmount-stage-stay` / `unmount-project`：卸载后的卡片都正常定位；
  - `unmount-empty`：见可优化 2；
  - `reopen-width`：R4 `[null, "sheet", …]`，R3 `["dock", "sheet", …]`；
  - `reopen-hand`：见 2.2；
  - 变异下的探针结果：G9、E6 → `edit409`；F2、F4b → `focus-edit`；F3 → `unmount-stage-stay`；F5 → `reopen-width`。结果见上文和可优化 1。

## 8. 给实施方的修改指令

> **背景**：案头第一期 R4 之后，第 7 节 10 条验收全部符合；第二轮的 3 条必须修复都已修好；第 13 节的实现符合规格，没有发现新的错误行为。第三轮独立复核只发现 1 条必须修复：规格 13.6 要求的「非冲突 409 后方案已刷新」这条断言没有证明力。这一轮只改一个测试文件，**不改任何源码**。
>
> **硬规矩**（照旧）：
> - 只许改 `backend/tests/test_desk_dock_races_frontend.py` 和 `docs/tasks/2026-11-10-desk-board/impl/主代理.md`；
> - 其余文件（含 `frontend/**`、其他测试、四份文档）都不动；
> - 不装依赖；不提交、不 stash、不切分支；任务目录下 `01`–`10` 开头的文件和 `design/` 不要改；
> - 不要调用 subagent / subagent_fork / workflow。
>
> **一、修正探针夹具，让「方案已刷新」可证伪**
>
> 现状：
> - 文件里第二个 node 驱动 `NODE_FOCUS_DRIVER` 第 327 行是 `let locked = LOCK;`，于是 `lockedit` / `lockapprove` 场景第一次取到的分集方案就已经是锁定的（`active_breakdown_status: "running"`、第 5 版）；
> - `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan`（约第 513–531 行）在 409 之后断言的「第 5 版、running」与操作前一模一样，容器不刷新或不替换方案也会通过；
> - 第 412 行日志写着「载入未阻塞方案后」，与事实不符。
>
> 要求：
> 1. 第 327 行改成 `let locked = false;`。`lockScenario` 在发起操作前已经执行 `locked = true; operationConflict = true;`，不用另改。
> 2. 在 `lockScenario` 里，`locked = true` 之前记下 `view.plan.active_breakdown_status`，放进最后输出的 JSON（字段名例如 `beforeActive`）。
> 3. 在 `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan` 里，对 `edit` 和 `approve` 两个结果都加 `assert result["beforeActive"] == "done"`，并保留 `activeStatus == "running"`（`edit` 另保留 `planRevision == 5`）。
> 4. 第 412 行日志改成与实际一致。
>
> 验证（每次跑完按原字节还原并校验 sha256）：
> - 当前代码下这条用例通过。
> - 变异 G9 必须让这条用例变红，改法分两处，都在 `frontend/components/desk/DeskDock.tsx`：
>   - `refreshPlanAfterConflict` 里删掉 `setPlan(next); setPlanLoading(false); setPlanError(null);` 三行，只留 `return next;`；
>   - `operatePlan` 和 `approvePlan` 的冲突分支里，在 `setPlanNotice(PLAN_CONFLICT_TEXT);` 之前加 `if (refreshed) setPlan(refreshed);`。
> - 下面两个变异的结果不变：两处 `isRevisionConflict(currentPlan.plan_revision, refreshed)` 换成 `true` 时，这条用例仍变红；换成 `false` 时，`test_real_version_conflict_sets_notice_and_resolves` 仍变红。
>
> **二、验收**：重跑规格第 7 节 10 条命令。全量要求 0 failed、0 skipped，通过数仍为 `8011`（不新增用例）；本机 `NO_PROXY` 含 `[::1]` 时，命令前加 `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1`。另外确认：
> - `git diff main -- frontend` 与 R4 结束时逐字节相同；
> - `git diff main -- frontend/app/page.tsx | shasum -a 256` 仍是 `825086b000d3d31b0f167e1f2ecc8bb048257715f4d7712a17fc501ee1187d4b`。
>
> **三、报告**：在 `impl/主代理.md` 末尾追加「## R5」，写明：
> - 改了哪一行；
> - 修改前后在当前代码与 G9 变异下的用例结果；
> - G2、G3 的结果；
> - 第 7 节命令的实际输出。
>
> 第 6 节的可优化项由规格作者裁定，不在本轮指令内。

## 附录 A：探针 `desk-r3-harness.js`

在 `frontend/` 目录下运行：`node <路径>/desk-r3-harness.js <场景>`；设置 `DESK_DIR=<目录>` 可以改为加载另一份 `components/desk/DeskDock.tsx` 与 `DeskEpisodesView.tsx`，用于和 R3 快照对照。

- 场景：`edit409`、`merge409`、`approve409`、`focus-edit`、`focus-merge`、`focus-approve`、`unmount-close`、`unmount-stage`、`unmount-stage-stay`、`unmount-project`、`unmount-empty`、`reopen-width`、`reopen-hand`。
- 只读源码，不访问网络，不写文件。
- 第二轮附录 A、B 的探针原样复用，本轮只给附录 A 的加载 `DeskDock.tsx` 那一行加了 `process.env.DESK_DIR ||`。

```js
// 第三轮复核用的行为探针：一个最小的函数组件协调器（每个组件实例各自的 hook 槽位、
// 子组件先于父组件执行 effect、卸载时执行 cleanup），驱动真实的
//   DeskDock.tsx + DeskEpisodesView.tsx + 工作室 EpisodeEditDialog / BreakdownDialog + useAccountIdentity.ts + desk.ts。
// 只有 DeskFrame（换成只渲染 children 的桩）、章回/细纲视图、NovelStates、Glaze 与后端是桩。
// 在 frontend/ 下运行：node <本文件> <场景>；DESK_DIR=<目录> 可改为加载另一份 components/desk/*（R3 快照对照）。
// 只读源码，不访问网络，不写文件。
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const FRONTEND = process.cwd();
const DESK_DIR = process.env.DESK_DIR ? path.resolve(process.env.DESK_DIR) : FRONTEND;
const SCENARIO = process.argv[2] || 'edit409';

// ---------------- 最小协调器 ----------------
const instances = new Map();
let currentInst = null, cursor = 0, seen = null, pending = [], scheduled = false;
let rootElement = null, lastTree = null;
let afterRender = () => {};
function schedule() { if (!scheduled) { scheduled = true; setTimeout(flush, 0); } }
function depsEqual(a, b) { return a && b && a.length === b.length && a.every((d, k) => Object.is(d, b[k])); }
function renderNode(node, p) {
  if (node == null || typeof node === 'boolean') return null;
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map((child, i) => renderNode(child, p + '/' + (child && child.key != null ? '$' + child.key : i)));
  const { type, props } = node;
  if (typeof type === 'function') {
    const id = p + '<' + (type.name || 'anon') + (node.key != null ? '#' + node.key : '') + '>';
    let inst = instances.get(id);
    if (!inst || inst.type !== type) { inst = { type, slots: [], id }; instances.set(id, inst); }
    seen.add(id);
    const prevInst = currentInst, prevCursor = cursor;
    currentInst = inst; cursor = 0; inst.pending = [];
    const out = type(props);
    currentInst = prevInst; cursor = prevCursor;
    const rendered = renderNode(out, id + '/0');
    pending.push(...inst.pending);
    return { type, props, rendered, inst };
  }
  const children = props && props.children;
  const renderedChildren = Array.isArray(children)
    ? children.map((child, i) => renderNode(child, p + '/' + (child && child.key != null ? '$' + child.key : i)))
    : renderNode(children, p + '/0');
  return { type, props: { ...props, children: renderedChildren } };
}
function flush() {
  scheduled = false; seen = new Set(); pending = [];
  lastTree = renderNode(rootElement, 'root');
  // 卸载：本轮没有出现的实例执行全部 effect cleanup
  const destroys = [];
  for (const [id, inst] of instances) {
    if (seen.has(id)) continue;
    instances.delete(id);
    for (const slot of inst.slots) if (slot && slot.effect && slot.cleanup) destroys.push(slot.cleanup);
  }
  afterRender(lastTree);
  for (const d of destroys) d();
  for (const e of pending) { const slot = e.inst.slots[e.i]; if (slot.cleanup) { const c = slot.cleanup; slot.cleanup = null; c(); } }
  for (const e of pending) { const slot = e.inst.slots[e.i]; const c = e.fn(); slot.cleanup = typeof c === 'function' ? c : null; slot.deps = e.deps; }
}
const React = {
  useState(init) {
    const inst = currentInst, i = cursor++;
    if (!(i in inst.slots)) inst.slots[i] = { v: typeof init === 'function' ? init() : init };
    const slot = inst.slots[i];
    return [slot.v, next => { const v = typeof next === 'function' ? next(slot.v) : next; if (!Object.is(v, slot.v)) { slot.v = v; schedule(); } }];
  },
  useRef(init) { const inst = currentInst, i = cursor++; if (!(i in inst.slots)) inst.slots[i] = { current: init }; return inst.slots[i]; },
  useCallback(fn, deps) { const inst = currentInst, i = cursor++; const prev = inst.slots[i]; if (prev && depsEqual(deps, prev.deps)) return prev.fn; inst.slots[i] = { fn, deps }; return fn; },
  useMemo(fn, deps) { const inst = currentInst, i = cursor++; const prev = inst.slots[i]; if (prev && depsEqual(deps, prev.deps)) return prev.v; const v = fn(); inst.slots[i] = { v, deps }; return v; },
  useEffect(fn, deps) {
    const inst = currentInst, i = cursor++;
    const prev = inst.slots[i];
    if (prev && deps && prev.deps && depsEqual(deps, prev.deps)) return;
    if (!prev) inst.slots[i] = { effect: true, deps: null, cleanup: null };
    inst.pending.push({ inst, i, fn, deps });
  },
  useLayoutEffect(fn, deps) { return React.useEffect(fn, deps); },
  useId() { const inst = currentInst; cursor++; return inst.id.length + ':' + cursor; },
  useSyncExternalStore(_s, get) { cursor++; return get(); },
};
const jsx = (type, p, key) => ({ type, props: p || {}, key: key === undefined ? null : key });

// ---------------- 日志与延迟桩 ----------------
const log = [];
const t0 = Date.now();
const stamp = () => ((Date.now() - t0) / 1000).toFixed(2) + 's';
const delay = (ms, value, signal, label, fail) => new Promise((resolve, reject) => {
  let settled = false;
  const t = setTimeout(() => {
    settled = true;
    const f = typeof fail === 'function' ? fail() : fail;
    if (f) { log.push(`${stamp()} ${label} → ${f.status} ${f.message}`); reject(f); return; }
    log.push(`${stamp()} ${label} 完成`); resolve(typeof value === 'function' ? value() : value);
  }, ms);
  if (signal) signal.addEventListener('abort', () => { if (settled) return; settled = true; clearTimeout(t); log.push(`${stamp()} ${label} 被取消`); reject(Object.assign(new Error('aborted'), { name: 'AbortError' })); });
});

// ---------------- 假 DOM（只够焦点规则） ----------------
class HTMLElement {
  constructor(name, parent) { this.name = name; this.parent = parent || null; this.isConnected = true; }
  focus() { if (this.isConnected) { document.activeElement = this; } }
  matches(selector) { return selector === 'button[aria-controls="desk-panel"]' && this.name === 'toggle'; }
  getClientRects() { return this.isConnected ? [{}] : []; }
  contains(other) { for (let node = other; node; node = node.parent) if (node === this) return true; return false; }
}
global.HTMLElement = HTMLElement;
const body = new HTMLElement('body');
const toggle = new HTMLElement('toggle');
const panel = new HTMLElement('panel');
let dialogOpenCount = 0;
global.document = {
  activeElement: body, hidden: false, body,
  addEventListener() {}, removeEventListener() {},
  querySelector: sel => (sel === 'dialog[open]' && dialogOpenCount > 0 ? {} : null),
  querySelectorAll: selector => selector === 'button[aria-controls="desk-panel"]' ? [toggle] : [],
  createElement: () => ({ remove() {}, click() {} }),
};

// ---------------- 后端桩 ----------------
const A = '11111111-1111-1111-1111-111111111111';
const B = '22222222-2222-2222-2222-222222222222';
class ApiError extends Error { constructor(m, s) { super(m); this.status = s; this.name = 'ApiError'; } }
const mkBook = (id, title) => ({ id, title, status: 'completed', chapters_done: 3, words_done: 9000, updated_at: id === A ? '2026-11-10' : '2026-11-09', chapters: [], config: { batch_size: 3, adaptation: { max_scenes_per_chapter: 6 } }, pending_notes: 0, bible: null, compass: null });
const books = { [A]: mkBook(A, '甲'), [B]: mkBook(B, '乙') };
const state = { locked: false, revision: 5, emptyEpisodes: false };
const counts = { ops: 0, approve: 0, sources: 0, episodesGet: 0 };
const planNow = projectId => ({
  episodes: state.emptyEpisodes ? [] : [
    { id: 'e1', no: 1, title: '一', change: '', hook: '', notes: '', target_min: null, target_max: null, est_seconds: 200, warnings: [] },
    { id: 'e2', no: 2, title: '二', change: '', hook: '', notes: '', target_min: null, target_max: null, est_seconds: 200, warnings: [] },
  ],
  units: [], unassigned: [], plan_revision: state.revision, plan_approved_revision: null, g0_approved: false, total_seconds: 400,
  status: 'done', active_breakdown_status: state.locked ? 'running' : 'done', rebreakdown_pending: state.locked,
  __project: projectId,
});
const projects = [
  { id: 'p1', title: '甲短片一', snapshot_no: 1, created_at: '2026-11-09' },
  { id: 'p2', title: '甲短片二', snapshot_no: 1, created_at: '2026-11-10' },
];
const lockFail = msg => () => (state.locked ? new ApiError(msg, 409) : null);
const STUBS = {
  react: React, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
  '@/lib/auth': { getUsername: () => 'fixture-user', ensureAccountIdentity: async () => {} },
  '@/lib/agents': { ApiError },
  '@/lib/novels': {
    listNovels: signal => delay(30, [books[A], books[B]], signal, 'GET 书目'),
    getNovel: (id, signal) => delay(30, books[id], signal, `GET 详情 ${books[id].title}`),
    novelApi: { action: async () => ({}) }, getNovelChapter: async () => ({}), getNovelDraft: async () => ({}),
    addNovelNote: async () => ({}), exportNovel: async () => null, novelErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio': {
    listStudioNovelSources: signal => { counts.sources += 1; return delay(40, { enabled: true, books: [{ id: A, eligible: true, projects }] }, signal, 'GET 工作室来源'); },
    studioErrorMessage: cause => (cause instanceof Error ? cause.message : '操作未完成，请稍后重试。'),
  },
  '@/lib/studio-breakdown': {
    getStudioEpisodes: (id, signal) => { counts.episodesGet += 1; return delay(40, () => planNow(id), signal, `GET 分集方案 ${id}`); },
    operateStudioEpisodes: (id, op, signal) => { counts.ops += 1; return delay(40, () => planNow(id), signal, `POST episodes/ops ${op.op} expected_revision=${op.expected_revision}`, lockFail('拆解尚未完成，完成后才能修改分集方案')); },
    approveStudioEpisodes: (id, rev, signal) => { counts.approve += 1; return delay(40, () => planNow(id), signal, `POST episodes/approve expected_revision=${rev}`, lockFail('拆解尚未全部完成，不能批准分集方案')); },
    formatEpisodeDuration: s => `${s} 秒`,
  },
  '@/components/novel/NovelShell': { canCloseNovelDrawer: () => false },
  '@/components/novel/NovelStates': {
    EmptyState: function EmptyState(p) { return jsx('div', { 'data-state': 'empty', children: p.children }); },
    LoadingState: function LoadingState(p) { return jsx('div', { 'data-state': 'loading', children: p.children }); },
    ErrorNotice: function ErrorNotice(p) { return jsx('div', { role: 'alert', 'data-state': 'error', children: p.message }); },
  },
  '@/components/Glaze': function Glaze(p) { return jsx('div', { children: p.children }); },
  './SourceChoices': { sourceDialogClass: '' },
  './DeskChaptersView': { __esModule: true, default: function DeskChaptersView() { return null; } },
  './DeskDialogs': { DeskPlanDialog: function DeskPlanDialog() { return null; }, DeskReaderDialog: function DeskReaderDialog() { return null; } },
  './DeskIdeaView': { __esModule: true, default: function DeskIdeaView() { return null; } },
  './DeskFrame': { __esModule: true, default: function DeskFrame(p) { return jsx('section', { 'data-frame': true, children: p.loading ? '正在取回作品…' : p.error ? p.error : p.children }); } },
};
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const out = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', 'module', out)(mod.exports, spec => {
    if (spec in STUBS) return STUBS[spec];
    let base;
    if (spec === './DeskEpisodesView') base = path.join(DESK_DIR, 'components/desk/DeskEpisodesView');
    else if (spec.startsWith('@/')) base = path.join(FRONTEND, spec.slice(2));
    else if (spec.startsWith('./')) base = path.resolve(path.dirname(file), spec);
    else throw new Error('unexpected import ' + spec);
    return load(fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx');
  }, mod);
  return mod.exports;
}

// ---------------- 树查询 ----------------
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(n => walk(n, visit)); return; }
  visit(node);
  if (typeof node.type === 'function') walk(node.rendered, visit);
  else walk(node.props && node.props.children, visit);
}
function textOf(node) {
  if (node == null) return '';
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (typeof node.type === 'function') return textOf(node.rendered);
  return textOf(node.props && node.props.children);
}
function findAll(pred) { const out = []; walk(lastTree, n => { if (pred(n)) out.push(n); }); return out; }
const comp = name => findAll(n => typeof n.type === 'function' && n.type.name === name);
const hostButtons = text => findAll(n => n.type === 'button' && textOf(n) === text);
const dialogs = () => findAll(n => n.type === 'dialog');
const sleep = ms => new Promise(r => setTimeout(r, ms));

const store = new Map([['fiona.desk.v1:fixture-user', JSON.stringify({ open: true, novelId: A, stage: 'episodes' })]]);
global.window = { localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }, requestAnimationFrame: cb => setTimeout(cb, 0), cancelAnimationFrame: t => clearTimeout(t), addEventListener() {}, removeEventListener() {}, innerWidth: 1280, setTimeout, clearTimeout };
global.URL = { createObjectURL: () => 'blob:x', revokeObjectURL() {} };

afterRender = tree => {
  let frame = null; walk(tree, n => { if (!frame && typeof n.type === 'function' && n.type.name === 'DeskFrame') frame = n; });
  if (frame && frame.props.panelRef) frame.props.panelRef.current = panel;
  dialogOpenCount = dialogs().length;
};

const { default: DeskDock } = load(path.join(DESK_DIR, 'components/desk/DeskDock.tsx'));
let props = {
  owner: 'fixture-user', open: true, studioAllowed: true, composerHeight: 96, focus: null,
  onAsk() {}, onOpenNovel() {}, onOpenNovelShelf() {}, onOpenStudio() {}, onOpenSettings() {},
  onOpenChange(next) { setProps({ open: next }); },
};
function setProps(patch) { props = { ...props, ...patch }; rootElement = jsx(DeskDock, props); schedule(); }

function viewSnapshot() {
  const view = comp('DeskEpisodesView')[0];
  const edit = comp('EpisodeEditDialog')[0];
  const bd = comp('BreakdownDialog');
  const cancel = hostButtons('取消')[0];
  const confirmBtn = findAll(n => n.type === 'button' && n.props.type === 'submit')[0];
  const titleInput = findAll(n => n.type === 'input' && n.props.required)[0];
  const alerts = findAll(n => n.props && n.props.role === 'alert').map(textOf);
  const select = findAll(n => n.type === 'select')[0];
  return {
    stageView: !!view,
    plan: view && view.props.plan ? { rev: view.props.plan.plan_revision, active: view.props.plan.active_breakdown_status, project: view.props.plan.__project } : null,
    projectSelect: select ? select.props.value : null,
    notice: view ? view.props.notice : null,
    dialogs: bd.map(d => d.props.title),
    editDialog: !!edit,
    cancelDisabled: cancel ? !!cancel.props.disabled : null,
    confirmDisabled: confirmBtn ? !!confirmBtn.props.disabled : null,
    titleValue: titleInput ? titleInput.props.value : null,
    alerts,
    counts: { ...counts },
  };
}
function pressEsc() {
  const d = dialogs()[0];
  if (!d) return 'no-dialog';
  let prevented = false;
  d.props.onCancel({ preventDefault() { prevented = true; } });
  return prevented ? 'prevented' : 'closed';
}
async function openEpisodeDialog(kind) {
  if (kind === 'approve') { hostButtons('批准分集方案')[0].props.onClick(); await sleep(30); return; }
  const expand = findAll(n => n.type === 'button' && n.props['aria-expanded'] !== undefined && /第 1 集/.test(n.props['aria-label'] || ''))[0];
  expand.props.onClick(); await sleep(30);
  hostButtons(kind === 'edit' ? '修改' : '与下一集合并')[0].props.onClick(); await sleep(30);
}
async function submit() {
  const form = findAll(n => n.type === 'form')[0];
  form.props.onSubmit({ preventDefault() {} });
  await sleep(400);
}

async function lockScenario(kind) {
  rootElement = jsx(DeskDock, props); flush();
  await sleep(600);
  const steps = [];
  steps.push(['载入后', viewSnapshot()]);
  await openEpisodeDialog(kind);
  if (kind === 'edit') {
    const input = findAll(n => n.type === 'input' && n.props.required)[0];
    input.props.onChange({ target: { value: '作者刚改的标题' } }); await sleep(30);
  }
  state.locked = true; // 作者在工作室发起了重新拆解，后端版本号不变
  steps.push(['打开对话框并填写后（后端已开始重新拆解）', viewSnapshot()]);
  await submit();
  steps.push(['第一次确认（409）后', viewSnapshot()]);
  if (kind === 'edit') {
    const before = counts.ops;
    await submit();
    steps.push([`锁定态再点「保存」（新增 ops 请求 ${counts.ops - before} 次）`, viewSnapshot()]);
  }
  const esc = pressEsc(); await sleep(60);
  steps.push([`按 Esc（${esc}）后`, viewSnapshot()]);
  // 关掉之后来一张同书另一个项目的卡片：定位必须生效（证明容器没有一直以为有对话框开着）
  state.locked = false;
  setProps({ focus: { subject: { kind: 'project', projectId: 'p1' }, nonce: 101 } });
  await sleep(500);
  steps.push(['关闭后来卡片（p1）', viewSnapshot()]);
  for (const [label, s] of steps) console.log(label.padEnd(12), JSON.stringify(s));
}

async function focusWhileDialog(kind) {
  rootElement = jsx(DeskDock, props); flush();
  await sleep(600);
  const steps = [['载入后', viewSnapshot()]];
  await openEpisodeDialog(kind);
  if (kind === 'edit') { const input = findAll(n => n.type === 'input' && n.props.required)[0]; input.props.onChange({ target: { value: '作者刚改的标题' } }); await sleep(30); }
  const before = counts.sources;
  setProps({ focus: { subject: { kind: 'project', projectId: 'p1' }, nonce: 201 } });
  await sleep(500);
  steps.push([`对话框开着来卡片 p1（工作室来源请求 ${counts.sources - before} 次）`, viewSnapshot()]);
  { const c = hostButtons('取消')[0]; if (c) c.props.onClick(); await sleep(60); }
  steps.push(['点「取消」关闭后', viewSnapshot()]);
  setProps({ focus: { subject: { kind: 'project', projectId: 'p1' }, nonce: 202 } });
  await sleep(500);
  steps.push(['再来一张卡片 p1', viewSnapshot()]);
  for (const [label, s] of steps) console.log(label, JSON.stringify(s));
}

async function unmountWhileDialog(how) {
  rootElement = jsx(DeskDock, props); flush();
  await sleep(600);
  await openEpisodeDialog('edit');
  const steps = [['打开修改框', viewSnapshot()]];
  if (how === 'close') {
    setProps({ open: false }); await sleep(100);
    steps.push(['程序性收起案头（视图卸载）', viewSnapshot()]);
    setProps({ open: true }); await sleep(600);
    steps.push(['重开', viewSnapshot()]);
  } else if (how === 'stage') {
    comp('DeskFrame')[0].props.onStageChange('chapters'); await sleep(100);
    steps.push(['切到章回（视图卸载）', viewSnapshot()]);
    comp('DeskFrame')[0].props.onStageChange('episodes'); await sleep(600);
    steps.push(['切回分集', viewSnapshot()]);
  } else if (how === 'stage-stay') {
    comp('DeskFrame')[0].props.onStageChange('chapters'); await sleep(100);
    steps.push(['切到章回（视图卸载），停在章回', { stage: comp('DeskFrame')[0].props.stage, ...viewSnapshot() }]);
  } else if (how === 'project') {
    // 视图里的项目下拉在模态框后面点不到；这里直接调用容器的 onSelectProject 以触发 key 变化卸载
    comp('DeskEpisodesView')[0].props.onSelectProject('p1'); await sleep(600);
    steps.push(['切换项目到 p1（key 变化，视图重挂）', viewSnapshot()]);
  } else if (how === 'empty') {
    // 锁定态下 5 秒轮询把方案换成 0 集：视图不再渲染对话框，但 editing 仍非空
    state.locked = true; await submit(); // 先拿到一次非冲突 409，方案变成锁定，开始 5 秒轮询
    state.emptyEpisodes = true;
    await sleep(5600);
    steps.push(['锁定轮询取回 0 集方案', viewSnapshot()]);
  }
  setProps({ focus: { subject: { kind: 'project', projectId: 'p1' }, nonce: 301 } });
  await sleep(600);
  steps.push(['之后来卡片 p1', { stage: comp('DeskFrame')[0].props.stage, ...viewSnapshot() }]);
  for (const [label, s] of steps) console.log(label, JSON.stringify(s));
}

const frameModes = [];
async function reopenWidth() {
  const prevAfter = afterRender;
  afterRender = tree => { prevAfter(tree); const f = comp('DeskFrame')[0]; frameModes.push(f ? f.props.mode : null); };
  window.innerWidth = 1500;
  rootElement = jsx(DeskDock, props); flush();
  await sleep(400);
  const marks = [['打开（1500 宽）', frameModes.slice()]];
  frameModes.length = 0;
  setProps({ open: false }); await sleep(100);
  marks.push(['收起', frameModes.slice()]);
  frameModes.length = 0;
  window.innerWidth = 500; // 关闭期间窗口变窄（不会收到 resize，因为只在打开时监听）
  setProps({ open: true }); await sleep(400);
  marks.push(['重开（500 宽），按渲染顺序的 DeskFrame mode', frameModes.slice()]);
  for (const [label, m] of marks) console.log(label, JSON.stringify(m));
}
async function reopenHand() {
  document.activeElement = body;
  setProps({ open: false }); rootElement = jsx(DeskDock, props); flush();
  await sleep(100);
  const out = [];
  for (const round of [1, 2]) {
    document.activeElement = toggle; setProps({ open: true }); await sleep(400);
    out.push([`第 ${round} 次亲手打开后焦点`, document.activeElement.name]);
    toggle.focus(); setProps({ open: false }); await sleep(200);
    out.push([`第 ${round} 次用头部开关收起后焦点`, document.activeElement.name]);
  }
  document.activeElement = body; setProps({ open: true }); await sleep(400);
  out.push(['焦点在 body 时恢复打开后焦点', document.activeElement.name]);
  comp('DeskFrame')[0].props.onClose(); await sleep(200);
  out.push(['面板里点 X 收起后焦点', document.activeElement.name]);
  console.log(JSON.stringify(out));
}

(async () => {
  try {
    if (SCENARIO === 'reopen-width') { await reopenWidth(); process.exit(0); }
    if (SCENARIO === 'reopen-hand') { await reopenHand(); process.exit(0); }
    if (SCENARIO === 'edit409') await lockScenario('edit');
    else if (SCENARIO === 'merge409') await lockScenario('merge');
    else if (SCENARIO === 'approve409') await lockScenario('approve');
    else if (SCENARIO.startsWith('focus-')) await focusWhileDialog(SCENARIO.slice(6));
    else if (SCENARIO.startsWith('unmount-')) await unmountWhileDialog(SCENARIO.slice(8));
    else throw new Error('unknown scenario ' + SCENARIO);
    if (process.env.SHOW_LOG) console.log(log.join('\n'));
    process.exit(0);
  } catch (error) {
    console.error(log.join('\n'));
    console.error(error && error.stack || error);
    process.exit(1);
  }
})();
```
