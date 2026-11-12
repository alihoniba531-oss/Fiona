# 案头第一期 · 第二轮独立复核报告

复核对象：基线 `9adf34c` 之上、R3 之后的工作区。依据是规格 v1.3（`02-spec.md`，重点第 11、12 节）和 `.cache/review/r1-to-r3.diff`。实施方报告（`impl/主代理.md` 的 R2、R3 两节）和验收方记录（`gate-notes.md`）只当线索。下面的结论都来自复核方自己跑的命令、读的代码和做的实验。

本轮只核验四件事：上一轮 2 条必须修复、第 11 节、第 12 节，以及 R2/R3 有没有引入新错误。复核方没有启动浏览器或 dev server。

为了能对比 R1，复核方用 `patch -R` 把 `r1-to-r3.diff` 的前端部分反向应用到副本上，在 `.cache/r2-scratch/r1/` 还原出 R1 时的案头文件。复核过程中的脚本、日志和变异记录都放在 `.cache/r2-scratch/`。

## 1. 结论

**不通过。** 上一轮的 2 条必须修复都已修好，第 7 节 10 条验收全部符合。但复核发现 3 条新的必须修复，前两条是 R2 引入的回归：

1. **分集对话框可能锁死、关不掉**（`DeskEpisodesView.tsx` 与 DeskDock 的 11.2 分支）。
   - 场景：作者在工作室发起重新拆解后，回到案头去保存单集修改、合并或批准，后端返回「拆解尚未完成…」类的 409。
   - 结果：对话框显示了真实原因，但「取消」、Esc、「保存」全部失效。模态对话框把页面其余部分都变成不可操作，作者被困住。这个状态至少持续到拆解跑完；拆解如果以 `partial` 结束，只能刷新整页。
2. **点「收起案头」X 关闭后焦点掉到 body**（`DeskDock.tsx`）。
   - 场景：案头是自动打开或刷新后恢复打开的。
   - 违反规格 4.2「收起后把焦点还给头部那个按钮」。R1 在这条路径上是对的，R2 为了满足 11.3 引入了这个回归。
3. **11.9、12.3 要求「绑到元素上」的几条断言没有绑定元素**（`test_desk_views_frontend.py`）。
   - 涉及：竖排 tablist 的 `aria-orientation`、章节和分集展开按钮的 `aria-label`、Tab 停靠点是否在当前阶段。
   - 对应的 4 个变异（R5A、R5B、R5C、R4C）全部 `90 passed`。

第 11 节其余小节和第 12 节的实现都符合规格。账号隔离、付费入口、锁定字面量没有变化。

## 2. 上一轮必须修复 2 条的核验

### 2.1 必须修复 1：读请求作用域共用导致加载卡死，已修好

**复现方法与上一轮相同。** 用 `05-review.md` 附录的 `desk-race.js`（原样）分别驱动 R1 快照和当前代码。另做一个留言变体：只把调用换成 `onAddNote`，并给 `addNovelNote` 的桩加 120ms 延迟。

| 对象 | `write` 场景最后一行 | `episodes` 场景最后一行 | 留言变体 |
|---|---|---|---|
| R1 快照 | `{"loading":true,"book":null,"error":null}`（「GET 详情 乙 被取消」） | `{"candidateLoading":true,"hasPlan":true}` | `{"loading":true,"book":null,…}` |
| 当前代码 | `{"loading":false,"book":"乙","error":null}` | `{"candidateLoading":false,"hasPlan":true}` | `{"loading":false,"book":"乙",…}` |

**附录脚本要补一行才能跑当前代码。** R2 的焦点规则用了 `instanceof HTMLElement`，Node 里没有这个全局，附录脚本原样运行会抛 `ReferenceError: HTMLElement is not defined`。复核方只补了一行 `global.HTMLElement = class HTMLElement {};`（实施方的竞态用例也是这么做的）。补完的脚本在 R1 快照上照样复现两处卡死，说明这一行不影响检出能力。

**当前代码 `episodes` 场景的日志**：5.96s 点「刷新」后，6.13s 轮询的「GET 分集方案」照常完成，候选请求在 6.76s 完成，没有被取消。

**修复落在代码上的位置**（`DeskDock.tsx`）：

- `loadBookDetail` 在 `beginDetailRead()` 之前先判所选书和 `openRef`（第 271 行）。
- 写后检查补了所选书判断：`runNovelAction` 第 461 行、`addNote` 第 505 行。
- 候选和导出各有独立作用域：第 183、394 行和第 187、516 行。

**11.1 第 3 条的排查**：

- `bookLoading`：同作用域里只有 `loadBookDetail`。不同书的刷新已被开头的判断挡住；同一本书的任何一次刷新都会在 `finally` 里清掉它。
- `candidateLoading`：独占候选作用域。
- `planLoading`：轮询的 `loadPlan` 和冲突刷新 `refreshPlanAfterConflict` 的 `finally` 都会清掉它。
- 关闭案头时被取消的请求会留下为真的加载标志，但重开后 `loadBooks → selectBook → resetEpisodes` 会重置。没有找到新的卡死路径。

**变异**：R1A（两道所选书判断一起拆掉）、R1B（候选改回分集作用域）分别让 `test_write_then_switch_book_clears_loading_and_selects_new_book` 和 `test_refresh_during_plan_poll_clears_candidate_loading` 变红。

### 2.2 必须修复 2：「已批准」朱色用例没有绑定标签，已修好

用例改用 `tag_span_classes`（第 232 行）定位文字为「已批准」或「待批准」的 `tag`：

- `assert_approved_tag_has_seal`（第 249–255 行）断言两个朱色类在标签自己的 class 里，并且整页各只出现 1 次；
- `assert_pending_tag_has_no_seal`（第 257–263 行）断言「待批准」不带朱色，整页也没有朱色类；
- 自检样本把朱色放在 `<p>` 上，检查器会报错。

变异结果：

| 编号 | 变异 | 结果 |
|---|---|---|
| M2B | 「已批准」标签改成纯 `tag`，两个朱色类挪到汇总行 `<p>`（仅已批准时） | 1 failed（`test_episodes_approved_tag_has_seal_classes_and_pending_does_not`） |
| M2C | 只去掉「已批准」的朱色 | 1 failed（同上） |
| M2D | 标签保留朱色，汇总行再多加一处 | 1 failed（同上） |
| M2E | 「待批准」也上朱色 | 1 failed（同上） |

## 3. 规格第 11、12 节逐小节核验

| 小节 | 是否符合 | 证据 |
|---|---|---|
| 11.1 加载标志 | 符合 | 见 2.1。8 个 `useAccountRequest`：书目、详情、候选、分集方案、对话框、定位、导出 7 个读作用域，加 1 个写作用域（第 181–188 行）。 |
| 11.2 409 分类 | 实现符合，但引入必须修复 1 | 新增 `isRevisionConflict` 的逻辑用例覆盖了版本变、版本没变、`null`、`undefined`。`operatePlan`/`approvePlan` 遇到 409 先刷新并替换方案；只有版本真的变了才设提示并正常返回，否则原样抛出 `ApiError`（第 626–634、658–666 行）。探针证实：非冲突 409 时提示为 `null`、对话框收到真实原因。但刷新回来的方案必然被锁，对话框随之关不掉，见 5.1。另外，变异 R3A（所有 409 都当冲突）不会让任何用例变红：容器层的分类没有自动化覆盖，见可优化 5。 |
| 11.3 自动打开不抢焦点 | 实现符合，但引入必须修复 2 | 新增 `deskAutoOpens` 的逻辑用例覆盖 767/768/1439/1440。`page.tsx` 用 `deskAutoOpens(window.innerWidth)`，旧写法已删除，契约用例覆盖。打开时只有焦点在开关上才移到面板（第 904–906 行）。探针：自动打开后焦点仍在输入框，恢复打开后焦点仍在 body，亲手打开后焦点在面板。但收起时还不还焦点仍取决于面板是否获得过焦点，自动打开和恢复打开之后点 X 会丢焦点，见 5.2。 |
| 11.4 关闭后不发请求 | 符合 | `open` 变假时调用 `cancelReadScopes()`（第 705–722 行）。所有链式读请求的发起前和回包后都判 `openRef`。`resize` 只在打开时监听（第 208–217 行）。`test_close_stops_new_get_requests` 通过。探针 `locate-cancel`：定位请求在途时收起，日志是「GET 工作室来源 被取消」，之后没有新的 GET。 |
| 11.5 定位的两个副作用 | 符合 | 同书换项目时清 `planNotice`（第 790 行）；换书时由 `resetEpisodes` 清。细纲或正文对话框开着时忽略定位、不关对话框；请求在途期间对话框才打开的情况也会判断（第 727–733、754、774 行）。探针 `locate-dialog`：`planDialogStillOpen:true`，「工作室来源」请求数为 0，阶段仍是章回。 |
| 11.6 细纲对话框 | 符合 | `planAct` 抛 `new Error(novelErrorMessage(cause))`（第 488 行）。`DeskDialog` 增加了 `busy`，busy 时按 Esc 只 `preventDefault`（`DeskDialogs.tsx` 第 44–47 行）。成功后先关闭对话框再 `focusDeskPanel()`（第 485–486 行）。注意：busy 时 Esc 不关、成功后焦点落面板这两点都没有用例，变异 R6A 全过，见可优化 5。 |
| 11.7 无障碍 | 实现符合，测试见必须修复 3 | 竖排 `tablist` 带 `aria-orientation="vertical"`，横排不带。方向键见 12.1。章节和分集的展开按钮带 `第 n 章　章名`、`第 n 集　标题` 的 `aria-label`。没有章节时 `EmptyState` 不在 `role="list"` 里。 |
| 11.8 文案与健壮性 | 符合 | 没有 reason 时只显示「这本书还没有短片项目。」。还没有详情时书名留空，有详情但书名为空才显示「未命名」。`DeskDock` 里只有 `deskStorage()` 一处访问 `window.localStorage`，并包了 try/catch。 |
| 11.9 测试 | 部分不符合 | 朱色绑定、竞态文件（write、episodes、close 三个场景，带缺依赖自检）、两个新函数的用例、page 契约、`<aside>` 背景、半屏完整高度、横排标签的 `disabled`/`title`、`editsBlocked` 时两个按钮禁用、`role="alert"` 绑定提示文字，都符合。**最后一条里的 `aria-orientation` 和展开按钮 `aria-label` 没有绑定元素**，见 5.3。 |
| 11.10 文档 | 符合 | `CLAUDE.md` 和 `ARCHITECTURE.md` 写的是实际的暂停条件、7 个读作用域加 1 个写作用域。仓库里剩下的「页面隐藏或操作中暂停」都是工作室原有段落。实施记录的三处旧说法都已标注被 R1/R2 取代。四份文档和实施记录里没有本机绝对路径、账号名或密钥。 |
| 12.1 竖排方向键 | 符合 | `deskStageByKey` 只在可用阶段间移动，到头循环；竖排认上下、横排认左右，Home/End，其他按键和置灰的当前阶段都返回 `null`。`DeskFrame` 两组标签都用它处理按键，返回非空时 `preventDefault`、切阶段，并按 `data-stage` 把焦点移到目标按钮。当前阶段 `tabIndex=0`，其余 `-1`。已不再引用 `useRovingTabs`，`lib/useRovingTabs.ts` 没有改动。 |
| 12.2 一张卡片只定位一次 | 符合 | 新增 `handledFocusNonceRef`，effect 一开头就判（第 726 行）。规格列的六种「走完」都会写入：第 730、738、755/775、763、769/800、780、803 行。请求被取消时不写入，重开后重新定位：探针 `locate-cancel` 重开后到了分集页。仍保留同一 nonce 在途时的防重入（第 735 行）。 |
| 12.3 测试 | 部分不符合 | 逻辑用例覆盖了规格列出的全部情形。契约用例检查 `deskStageByKey(`、不再出现 `useRovingTabs`、两组 `data-stage`。竞态用例的 locate 场景在修复前是红的：变异 R2A 复现了 R2 的行为，该用例变红。**视图用例只数了 `tabindex="0"` 的个数，没有确认它在当前阶段上**，变异 R4C 全过，见 5.3。 |

## 4. 验收标准逐条核验（第 7 节）

| # | 命令 | 实际输出 | 是否符合 |
|---|---|---|---|
| 1 | `cd backend && NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 .venv/bin/python -m pytest -q -p no:cacheprovider`（本机 `NO_PROXY` 含 `[::1]`，按说明覆盖） | `8001 passed, 35 warnings in 330.51s (0:05:30)`，退出 0，没有 failed 或 skipped；8001 = 7911 + 90 | 符合 |
| 2 | `.venv/bin/python -m pytest -q tests/test_desk_*.py -rsf` | `90 passed in 33.43s`，没有 skip 或 fail 摘要；按文件：契约 42、竞态 6、逻辑 14、视图 28 | 符合 |
| 3 | `cd frontend && npx tsc --noEmit` | 无输出，`TSC_EXIT:0` | 符合 |
| 4 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`，退出 0；`npx eslint components/desk lib/desk.ts` 无输出 | 符合 |
| 5 | `cd frontend && npm run build` | 路由表正常（含 `/novels`、`/studio/[id]`、`/studio/kb`），`BUILD_EXIT:0`；构建后 `git status` 与构建前一致 | 符合 |
| 6 | `git status --porcelain --untracked-files=all`（排除 `.cache/`） | 修改：`CLAUDE.md`、`PLAN.md`、`README.md`、`docs/ARCHITECTURE.md`、`frontend/app/page.tsx`、`backend/tests/test_ui_closeout_dialog_scrim.py`。新增：四个 `backend/tests/test_desk_*.py`、六个 `frontend/components/desk/*.tsx`、`frontend/lib/desk.ts`、`impl/主代理.md`，以及作者的 `01`–`07` 与 `design/` | 符合 |
| 7 | `git diff --stat main -- backend ':!backend/tests'`；`git diff --numstat main -- backend/tests` | 前者为空；后者只有 `1	1	backend/tests/test_ui_closeout_dialog_scrim.py`，即 `expected_count=13` 改成 `expected_count=14` | 符合 |
| 8 | `git diff main -- frontend/package.json frontend/package-lock.json` | 空 | 符合 |
| 9 | 七条字面量逐条 `grep -cF`；`head -c 3 frontend/app/page.tsx \| xxd -p` | 依次为 `1 2 1 1 1 2 1`；BOM 为 `efbbbf` | 符合 |
| 10 | `grep -rc 'createElement("dialog"' frontend/components/desk/`（另查单引号写法）；`grep -c '<dialog' frontend/components/desk/DeskDialogs.tsx` | 六个文件两种写法都是 0；`<dialog` 为 1 | 符合 |

返修单的附加检查：

- `deskAutoOpens(window.innerWidth)` 出现 1 次；
- `DeskFrame.tsx` 里 `useRovingTabs` 为 0 次，`deskStageByKey(` 为 1 次；
- `git diff main` 对 `lib/useRovingTabs.ts`、`lib/useAccountIdentity.ts`、`components/novel`、`components/studio`、`lib/novels.ts`、`lib/studio*.ts`、`globals.css` 都为空；
- `git diff main -- frontend/app/page.tsx | shasum -a 256` 是 `825086b0…187d4b`，与实施方 R3 报告的值一致；
- `r1-to-r3.diff` 里 `page.tsx` 只有 11.3 那一处判断加 import 行。

## 5. 必须修复

### 5.1 非冲突 409 之后，分集对话框锁死，关不掉

**文件与行**

- `frontend/components/desk/DeskEpisodesView.tsx`：
  - 第 248–256 行，修改对话框的 `busy={busy || editsBlocked}` 在第 252 行；
  - 第 262 行，合并确认的 `busy={busy || editsBlocked}`；
  - 第 279 行，批准确认的 `busy={busy || approvalBlocked}`。
- `frontend/components/desk/DeskDock.tsx`：第 626–634、658–666 行（11.2 的非冲突分支）；第 430–449 行的 `refreshPlanAfterConflict`，第 439 行用刷新结果替换方案。
- 既有组件 `components/studio/BreakdownDialog.tsx`：
  - 第 16 行 `blocked = busy || saving`；
  - 第 24 行 `blocked` 时 `onCancel` 执行 `preventDefault`；
  - 第 29 行「取消」带 `disabled={blocked}`。

**现象**

1. 作者停在案头分集页，方案未被阻塞。案头不轮询未阻塞的方案，切回页面时也只刷新书的详情。
2. 作者在工作室抽屉或另一个标签页里发起重新拆解。这时后端的 `plan_revision` 不变，活动拆解变成 `running`。
3. 回到案头，展开某一集，点「修改」填好内容后保存（或「与下一集合并」，或「批准分集方案」）。
4. 后端返回 409「拆解尚未完成，完成后才能修改分集方案」（批准则是「拆解尚未全部完成，不能批准分集方案」）。
5. 按 11.2，容器刷新方案。版本号没变，于是原样抛出错误，对话框显示这句原因。这一步符合规格。
6. 但刷新回来的方案 `active_breakdown_status === "running"`，`editsBlocked` 和 `approvalBlocked` 都变成真，传给对话框的 `busy` 跟着变成真：
   - `BreakdownDialog` 进入 `blocked`：「取消」禁用、「保存」禁用、`fieldset` 禁用，Esc 被 `preventDefault`；
   - `EpisodeEditDialog` 的 `key={plan.plan_revision}` 没变，不会重新挂载，锁定状态一直保持；
   - `showModal()` 让页面其余部分不可操作；案头自己的 Esc 收起在有 `dialog[open]` 时也不生效（`canCloseNovelDrawer`）。

**为什么是问题**

- 这个锁是必然出现的，不是偶发。后端 `breakdown_plan.py`：
  - 第 325–328、345–348 行：版本号一致且活动拆解是 `running` 或 `partial` 时才返回这类 409；
  - 第 81–87 行的 `_activity`：GET 返回的 `active_breakdown_status` 和 `rebreakdown_pending` 取自同一个 `active['status']`。
  
  所以只要出现这类 409，刷新回来的方案就一定被锁。
- 解锁要等 `editsBlocked` 变假：新拆解发布后 `plan_revision` 加 1，对话框重新挂载才能关掉（作者填的内容会被重置）。一次拆解要跑几分钟甚至更久，作者这段时间被困在模态框里。如果拆解以 `partial` 结束，会一直锁着，只能刷新整页，作者填的内容也丢了。
- 这正是 11.2 想修好的场景（第一轮可优化 1 描述的流程）。R1 把所有 409 都当冲突处理，会关掉对话框，不会锁；R2 让对话框留着显示原因，但没有处理刷新后方案被锁的情况。这是「状态卡死」类的错误行为，由 R2 引入。
- 验收走查没发现的原因：走查只把 ops 接口换成返回 409，GET 仍返回未阻塞的方案，所以没触发这个锁。

**证明**（附录 A 探针在真实 `DeskDock.tsx` 上运行，附录 B 用真实 React 做服务端渲染，渲染的是真实的对话框组件）

- `node desk-r2-probe.js lock409edit`：

  ```text
  0.66s 载入后：plan_revision=5 editsBlocked=false approvalBlocked=false（案头不轮询未阻塞的方案）
  0.72s POST episodes/ops expected_revision=5 → 409 拆解尚未完成，完成后才能修改分集方案
  0.78s GET 分集方案 完成
  {"onConfirm":{"rejected":true,"status":409,"message":"拆解尚未完成，完成后才能修改分集方案"},"notice":null,"busy":false,"plan_revision":5,"editsBlocked":true,"approvalBlocked":true,"dialogBusyProp":true}
  ```

  `lock409approve` 的结果相同，消息是「拆解尚未全部完成，不能批准分集方案」。
- `node ssr-dialog-lock.js`：渲染真实的 `EpisodeEditDialog`、`BreakdownDialog`：

  ```text
  EpisodeEditDialog busy=false {"cancel":"<button … >取消</button>", …}
  EpisodeEditDialog busy=true  {"cancel":"<button … disabled=\"\">取消</button>","confirm":"<button type=\"submit\" … disabled=\"\">保存</button>","fieldset":"<fieldset disabled=\"\" …>"}
  BreakdownDialog(批准) busy=true {"cancel":"<button … disabled=\"\">取消</button>", "confirm":"… disabled=\"\">确认批准</button>", …}
  ```

**真实界面复现**：临时库里准备一个拆解已完成的项目，停在案头分集页。在工作室抽屉里对它发起重新拆解，关掉工作室抽屉，回案头修改第 1 集并保存。看到错误提示后，点「取消」、按 Esc 都没有反应。

**建议改法**

- 合并、批准两个确认框：改成 `busy={busy}`，再加 `disabled={editsBlocked}` / `disabled={approvalBlocked}`。`BreakdownDialog` 的 `disabled` 只禁用确认按钮，不影响「取消」和 Esc。
- 修改对话框：`EpisodeEditDialog` 没有透传 `disabled`，所以改成 `busy={busy}`；`onSave` 在 `editsBlocked` 时直接 `Promise.reject(new Error("拆解还没全部完成，暂时不能修改或批准，去工作室看进度。"))`，不发请求。这与工作室 `EpisodePlan` 的 `operate` 做法一致，文案取规格 4.4 的「拆解未完成」。
- 打开这三个对话框的按钮仍按 `editsBlocked` / `approvalBlocked` 禁用，不变。
- 底线要求：非冲突 409 之后，对话框始终能用「取消」和 Esc 关闭，作者填的内容保留，并显示后端原因。

### 5.2 自动打开或恢复打开之后，点「收起案头」X，焦点掉到 body

**文件与行**：`frontend/components/desk/DeskDock.tsx`

- 第 895–913 行：收起时只有 `panelFocusedRef` 为真才把焦点还给开关（第 897 行）。R2 新增的「焦点在开关上才移焦点」（第 904–906 行）使自动打开和恢复打开之后 `panelFocusedRef` 一直是 false。
- 第 1015 行：`onClose={() => onOpenChange(false)}`。
- 对照：Esc 收起路径（第 921–922 行）会显式调用 `focusVisibleDeskToggle`。

**现象**：案头由流式卡片自动打开，或刷新页面后恢复打开。作者用 Tab 进入面板，在「收起案头」X 上按回车或点击。面板卸载后焦点落到 body，没有回到头部「案头」开关。

**为什么是问题**

- 规格 4.2（v1.2）的末句是「收起后把焦点还给头部那个 `aria-controls="desk-panel"` 的按钮」，没有附加条件。X 是面板里最主要的收起方式；键盘用户关掉案头后，下一次 Tab 会从页面开头重新开始。
- R1 在这条路径上是对的：R1 打开时总会把焦点移到面板（这是 11.3 要修的问题），收起时就会还焦点。R2 修 11.3 时没有同步收起这一侧，造成回归。

**证明**（附录 A 探针，用一个只够焦点规则使用的假 DOM 驱动真实 `DeskDock.tsx`；面板卸载时，焦点若在面板内就落到 body，与浏览器行为一致）

| 场景 | 当前代码 | R1 快照 |
|---|---|---|
| `xclose-restore`（刷新后恢复打开） | `{"focusAfterOpen":"body","focusAfterClose":"body"}` | `{"focusAfterOpen":"案头面板 #desk-panel","focusAfterClose":"头部「案头」开关"}` |
| `xclose-auto`（卡片自动打开） | `{"focusAfterOpen":"输入框","focusAfterClose":"body"}` | `{"focusAfterOpen":"案头面板 #desk-panel","focusAfterClose":"头部「案头」开关"}` |
| `xclose-hand`（亲手打开，对照） | `{"focusAfterOpen":"案头面板 #desk-panel","focusAfterClose":"头部「案头」开关"}` | — |

当前代码打开时的焦点行为正确（11.3），收起这一侧丢了焦点。

**建议改法**：让 X 的回调与 Esc 路径一致：

```tsx
const closeFromPanel = useCallback(() => {
  onOpenChange(false);
  window.requestAnimationFrame(focusVisibleDeskToggle);
}, [onOpenChange]);
// <DeskFrame … onClose={closeFromPanel} …>
```

头部开关本身收起时焦点已经在开关上，不受影响。11.3 的打开规则保持不变。

### 5.3 11.9、12.3 要求「绑到元素上」的断言没有绑定元素

**文件与行**：`backend/tests/test_desk_views_frontend.py`

- 第 695、700、713 行：`'aria-orientation="vertical"' in dock`、`… in drawer`、`… not in sheet`，查的都是整页 HTML。
- 第 720–722 行：`'aria-label="第 1 章　测试章名"' in html`；第 743–745 行：`'aria-label="第 1 集　第 1 集 测试标题"' in html`，同样查整页。
- 第 757–765 行：`test_stage_tabs_expose_exactly_one_tab_stop_in_both_orientations` 只数了一个 `tabindex="0"` 和四个 `tabindex="-1"`，没有确认 `tabindex="0"` 就在当前阶段的标签上。用例只用默认阶段「章回」渲染。

**为什么是问题**

- 规格 11.9「把断言绑到元素上」明确列出：「竖排 `tablist` 带 `aria-orientation="vertical"`，横排不带；展开按钮的 `aria-label` 含章号 / 集号」。
- 12.3 要求「当前阶段的标签 `tabindex="0"` 恰好一个」。
- T8 总则：「每条断言都要能区分对错实现」。
- 现在把属性挪到别的元素上，用例照样全过。这与第一轮必须修复 2 是同一类问题：断言匹配到了别处的同名文字。

**证明**（每次只改一处或一组，跑全部 90 条，跑完按原字节还原）

| 编号 | 变异 | 结果 |
|---|---|---|
| R5A | `aria-orientation` 从竖排 `<nav role="tablist">` 挪到外层容器 `<div>` | `90 passed` |
| R5B | 章节展开按钮的 `aria-label` 挪到整行 `role="listitem"` 上（按钮的可读名称又只剩章名） | `90 passed` |
| R5C | 分集展开按钮的 `aria-label` 挪到整行 `role="listitem"` 上 | `90 passed` |
| R4C | `const selected = index === stageIndex` 改成 `index === 0`（两组标签的选中态和 Tab 停靠点都钉在「立意」，不跟随当前阶段） | `90 passed` |
| R4A（对照） | 只把 `tabIndex` 表达式改成 `index === 0 ? 0 : -1` | 视图用例 `28 passed`；全量 90 条里只有契约用例的源码字面量检查变红。说明视图断言本身没有区分能力。 |

**建议改法**

- 从渲染结果里取出 `role="tablist"` 的那个开标签：dock 和 drawer 渲染时断言它自己带 `aria-orientation="vertical"`，并且整页只出现 1 次；sheet 渲染时断言它不带，整页也没有。
- 取出带 `aria-expanded` 的展开按钮开标签，断言 `aria-label="第 1 章　测试章名"`（分集同理）在这个按钮上。
- Tab 停靠点：用一个非默认阶段（例如 `"episodes"`）分别渲染竖排和横排，断言唯一的 `tabindex="0"` 按钮同时带 `aria-selected="true"` 和 `data-stage="episodes"`，其余四个是 `tabindex="-1"`。
- 每条各配一条自检：属性挪到别的元素上，检查器必须报错。
- 改完用 R5A、R5B、R5C、R4C 各验一次，都必须变红。

## 6. 可优化

规格 11.11 留给作者裁定的两点（抽屉盖住发送按钮、手机半屏只露一行）本轮不再列出。

1. **定位只保护了细纲和正文对话框。** 分集的「修改」「合并」「批准」对话框开着时来一张项目卡，会把对话框连同作者填的内容一起卸掉：
   - 同书同项目：`setPlan(null)` 后显示 LoadingState，方案取回后修改框按原值重新弹出，作者改的字丢失；
   - 同书换项目：视图的 `key` 变了，整个重挂；
   - 换书：`book` 变成 `null`。
   
   规格 11.5 只写了两种对话框，是否扩展由作者裁定。如果扩展，可以让 `DeskEpisodesView` 用回调告诉容器有对话框开着，并把这个状态并入 `dialogOpenRef` 的判断。
2. **细纲对话框的「关闭」按钮在 busy 时仍能点**（`DeskDialogs.tsx` 第 72 行）。批准或重做进行中关掉对话框，之后如果失败，错误没有地方显示：`PlanEditor` 已经卸载，`gateError` 也不会被设置。建议 busy 时禁用「关闭」，或者在对话框已关闭时把失败信息写进 `gateError`。
3. **关闭期间改了窗口宽度，重开的第一帧沿用旧的呈现方式。** `resize` 只在打开时监听，`mode` 不会重置，重开后要等下一帧 rAF 才更正。例如关闭时从 ≥1440 缩到 <768，重开会先在文档流里渲染一帧并排面板。建议打开时同步算一次 `deskMode(window.innerWidth)`。
4. **定位已生效但项目还没选上时收起，会丢掉卡片指定的项目。** 定位到另一本书时，`handledFocusNonceRef` 在 `selectBook` 之后立即写入；如果在详情和候选取回之前收起，关闭时会清掉 `chatProjectRef`。重开后书和阶段是对的，但项目选的是最新的那个，不是卡片指定的那个（书有多个项目时才会碰到）。
5. **测试覆盖**（规格没有强制要求，以下变异都不变红）：
   - R2B：12.2 第三条「请求被取消不算走完」没有用例，把 nonce 提前在请求发出时就写入也全过；
   - R3A：容器层的 409 分类没有用例，所有 409 都当冲突也全过；
   - R6A：细纲对话框 busy 时按 Esc 照样关闭，全过；
   - R6B：自动打开也抢焦点（回到 R1 行为），全过；
   - R7A：Home 只在横排生效，全过（逻辑用例只测了横排的 Home 和竖排的 End）；
   - 竞态用例的写操作场景只走了 `onAction`，留言路径的所选书判断没有被单独证明；
   - `test_episode_no_project_without_reason_has_no_invented_suffix` 只断言旧的后半句不在，没有断言文案完整等于「这本书还没有短片项目。」。
   
   建议：在竞态文件里加带假 DOM 的焦点场景（可以参照附录 A），以及「定位请求被取消后重开」「非冲突 409」两个容器场景。

## 7. 变异实验记录

**做法**

- 用 `.cache/r2-scratch/mutate.py` 逐个应用变异：每次只改一处或一组，跑指定用例，在 `finally` 里按原字节写回，并逐个校验 sha256。
- 全部实验结束后，对 12 个相关文件运行 `shasum -a 256 -c`，结果全部 OK；`git status` 与实验前一致。
- 全量测试在任何变异之前跑完；构建在全部变异还原、sha256 校验通过之后才跑。

| 编号 | 位置 | 变异 | 结果 | 结论 |
|---|---|---|---|---|
| M2B | `DeskEpisodesView.tsx` | 朱色从「已批准」标签挪到汇总行 | 1 failed | 上一轮必须修复 2 已有证明力 |
| M2C | 同上 | 去掉「已批准」朱色 | 1 failed | 有证明力 |
| M2D | 同上 | 汇总行多加一处朱色 | 1 failed | 有证明力 |
| M2E | 同上 | 「待批准」也上朱色 | 1 failed | 有证明力 |
| R1A | `DeskDock.tsx` | `loadBookDetail` 开头和写后检查的所选书判断一起拆掉 | 1 failed（write 场景） | 有证明力 |
| R1B | 同上 | 候选改回 `beginEpisodeRead` | 1 failed（episodes 场景） | 有证明力 |
| R2A | 同上 | 去掉 `handledFocusNonceRef` 的开头判断（约等于 R2 行为） | 1 failed（locate 场景） | 12.3「修复前为红」成立 |
| R2B | 同上 | 请求一发出就记为已处理 | 90 passed | 12.2 第三条没有用例（可优化 5） |
| R3A | 同上 | 两处 `isRevisionConflict(…)` 换成 `true` | 90 passed | 容器层 409 分类没有用例（可优化 5） |
| R4A | `DeskFrame.tsx` | `tabIndex` 停靠点钉在第一个可用阶段 | 视图 28 passed；全量 1 failed（契约字面量） | 只有源码字面量兜底 |
| R4C | 同上 | `selected` 不再跟随 `stage` | 90 passed | 见必须修复 3 |
| R5A | 同上 | `aria-orientation` 挪到外层容器 | 90 passed | 见必须修复 3 |
| R5B | `DeskChaptersView.tsx` | 展开按钮的 `aria-label` 挪到整行 | 90 passed | 见必须修复 3 |
| R5C | `DeskEpisodesView.tsx` | 展开按钮的 `aria-label` 挪到整行 | 90 passed | 见必须修复 3 |
| R6A | `DeskDialogs.tsx` | busy 时 Esc 照样关闭 | 90 passed | 没有用例（可优化 5） |
| R6B | `DeskDock.tsx` | 去掉「焦点在开关上才移焦点」 | 90 passed | 焦点规则没有用例（可优化 5） |
| R7A | `lib/desk.ts` | Home 只在横排生效 | 逻辑 14 passed | 没有用例（可优化 5） |

**行为实验**（都只读源码，不访问网络）

- 竞态复现：附录脚本加补的一行 `HTMLElement`，在 R1 快照和当前代码上各跑一遍，结果见 2.1。
- 附录 A 探针 `desk-r2-probe.js`：
  - `lock409edit`、`lock409approve`：结果见 5.1；
  - `xclose-restore`、`xclose-auto`、`xclose-hand`：结果见 5.2，前两个另在 R1 快照上对照；
  - `locate-cancel`：定位请求在途时收起再打开，最终 `{"stage":"episodes","book":"甲"}`，说明会重新定位，符合 12.2；
  - `locate-dialog`：细纲对话框开着时来卡片，`{"planDialogStillOpen":true,"sourcesRequests":0,"stage":"chapters"}`，符合 11.5。
- 附录 B `ssr-dialog-lock.js`：结果见 5.1。

## 8. 给实施方的修改指令

> **背景**：案头第一期 R3 之后，第 7 节 10 条验收全部符合，上一轮 2 条必须修复都已修好。第二轮独立复核又发现 3 条必须修复，前两条是 R2 引入的回归。这一轮只做下面三件事，不要顺手重构。
>
> **硬规矩**（照旧）：
> - 只许改 `frontend/components/desk/DeskEpisodesView.tsx`、`frontend/components/desk/DeskDock.tsx`、`backend/tests/test_desk_*.py` 和 `docs/tasks/2026-11-10-desk-board/impl/主代理.md`；四份文档只在描述与新行为不符时才改。
> - `frontend/app/page.tsx`、`lib/useRovingTabs.ts`、`lib/useAccountIdentity.ts`、`components/novel/**`、`components/studio/**` 都不许改；`backend/` 下只许动 `tests/test_desk_*.py`。
> - 不装依赖；不提交、不 stash、不切分支；任务目录下 `01`–`08` 开头的文件和 `design/` 不要改。
> - 不要调用 subagent / subagent_fork / workflow。
>
> **一、非冲突 409 之后分集对话框锁死（`DeskEpisodesView.tsx` 第 248–290 行）**
>
> 现状：
> - 三个对话框的 `busy` 分别是 `busy || editsBlocked`（修改、合并）和 `busy || approvalBlocked`（批准）。
> - 作者在工作室发起重新拆解后，案头保存会得到「拆解尚未完成…」类的 409。容器按规格 11.2 刷新方案后原样抛错，但刷新回来的方案一定被锁（后端用同一个活动拆解状态决定 409 和 `active_breakdown_status`）。
> - 于是 `BreakdownDialog` 的「取消」和「保存」被禁用、Esc 被拦住，模态框关不掉，直到拆解跑完；以 `partial` 结束时会一直锁着。
>
> 要求：非冲突 409 之后，对话框必须仍能用「取消」和 Esc 关闭，作者填的内容保留，并显示后端原因。推荐做法：
> 1. 合并、批准两个 `BreakdownDialog` 改成 `busy={busy}`，并分别加 `disabled={editsBlocked}` / `disabled={approvalBlocked}`（`disabled` 只禁用确认按钮）。
> 2. `EpisodeEditDialog` 改成 `busy={busy}`；`onSave` 在 `editsBlocked` 为真时直接返回 `Promise.reject(new Error("拆解还没全部完成，暂时不能修改或批准，去工作室看进度。"))`，不发请求，与工作室 `EpisodePlan` 的 `operate` 做法一致。
> 3. 打开这三个对话框的按钮仍按 `editsBlocked` / `approvalBlocked` 禁用，不变。
>
> 测试：
> - 在 `test_desk_dock_races_frontend.py` 加一个场景：先载入未阻塞的方案（`plan_revision` 为 5），之后桩把 GET 改成同版本、`active_breakdown_status: "running"`、`rebreakdown_pending: true`，ops 和 approve 返回 409 `ApiError`。从视图桩的 props 调用 `onOperate` / `onApprove`，断言它们以 409 的 `ApiError` 拒绝、`notice` 为 `null`、方案已替换为被锁的版本。
> - 再加一条能证明对话框不会被锁的断言：可以是 `DeskEpisodesView.tsx` 的契约检查，确认三个对话框的 `busy` 表达式里不含 `editsBlocked` / `approvalBlocked`，并配违规样本自检；也可以用其他等价方式。
> - 验证：把 `busy` 临时改回 `busy || editsBlocked`，用例必须变红，然后按原字节还原。
> - 可以参照复核报告附录 A 的 `lock409edit` 场景。
>
> **二、自动打开或恢复打开之后点 X，焦点掉到 body（`DeskDock.tsx` 第 1015 行）**
>
> 现状：收起时只有 `panelFocusedRef` 为真才还焦点；R2 之后，自动打开和恢复打开都不会让它变真。
>
> 要求：给 `DeskFrame` 的 `onClose` 换成和 Esc 路径一样的回调：先 `onOpenChange(false)`，再 `window.requestAnimationFrame(focusVisibleDeskToggle)`。打开时的焦点规则（11.3）保持不变。
>
> 测试：在竞态文件里加带假 DOM 的焦点场景（参照附录 A 的 `xclose-*`）：
> - 恢复打开 → 焦点移进面板里的 X → 调用 `onClose`，断言焦点最终在头部开关上；
> - 卡片自动打开（打开时焦点在输入框）同样走一遍；
> - 亲手打开作对照；
> - 再断言自动打开和恢复打开那一刻焦点没有被移到面板。
>
> 验证：把 `onClose` 临时改回 `() => onOpenChange(false)`，前两个场景必须变红，然后按原字节还原。
>
> **三、11.9 / 12.3 的断言绑到元素上（`test_desk_views_frontend.py` 第 691–765 行）**
>
> 1. 取出 `role="tablist"` 的开标签：dock 与 drawer 渲染时断言它自己带 `aria-orientation="vertical"`，并且整页只出现 1 次；sheet 渲染时断言它不带，整页也没有。
> 2. 取出带 `aria-expanded` 的展开按钮开标签，断言 `aria-label="第 1 章　测试章名"` 在这个按钮上；分集同理（`第 1 集　…`）。
> 3. Tab 停靠点：用 `stage: "episodes"` 分别渲染竖排和横排，断言唯一的 `tabindex="0"` 按钮同时带 `aria-selected="true"` 和 `data-stage="episodes"`，其余四个是 `tabindex="-1"`。
> 4. 每条各配一条自检：属性在别的元素上时检查器必须报错。
> 5. 验证：下面 4 个变异各自必须让对应用例变红，跑完按原字节还原：
>    - `DeskFrame.tsx` 里把 `aria-orientation="vertical"` 从 `<nav>` 挪到外层容器；
>    - `DeskChaptersView.tsx` 里把展开按钮的 `aria-label` 挪到 `role="listitem"` 的行上；
>    - `DeskEpisodesView.tsx` 里做同样的挪动；
>    - `DeskFrame.tsx` 两处 `const selected = index === stageIndex` 改成 `index === 0`。
>
> **四、验收**：重跑规格第 7 节 10 条命令。全量要求 0 failed、0 skipped，通过数等于 7911 加新增用例总数；本机 `NO_PROXY` 含 `[::1]` 时，命令前加 `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1`。另外确认 `git diff main -- frontend/app/page.tsx | shasum -a 256` 仍是 `825086b000d3d31b0f167e1f2ecc8bb048257715f4d7712a17fc501ee1187d4b`。
>
> **五、报告**：在 `impl/主代理.md` 末尾追加「## R4」，写明：改了哪些文件；三条各自怎么改的；每条的修复前后输出；每个变异的结果；第 7 节命令的实际输出。

## 附录 A：探针 `desk-r2-probe.js`

在 `frontend/` 目录下运行：`node <路径>/desk-r2-probe.js <场景>`。它和 `05-review.md` 附录一样，用迷你 hooks 运行时驱动真实的 `DeskDock.tsx`、`useAccountIdentity.ts`、`desk.ts`；视图组件和后端都用桩，另加一个只够焦点规则使用的假 DOM。只读源码，不访问网络，也不写任何文件。

```js
// 第二轮复核用的探针：迷你 hooks 运行时（同 05-review 附录）驱动真实 DeskDock.tsx。
// 在 frontend/ 下运行：node <本文件> <场景>
//   lock409edit     分集方案在案头里没刷新、工作室已开始重新拆解：保存单集修改得到「拆解尚未完成」409
//   lock409approve  同上，批准得到「拆解尚未全部完成」409
//   xclose-restore  刷新后恢复打开（焦点不在开关）→ 作者 Tab 进面板 → 点「收起案头」X
//   xclose-auto     流式卡片自动打开（焦点在输入框）→ 作者 Tab 进面板 → 点 X
//   xclose-hand     亲手点开关打开 → 点 X（对照）
//   locate-cancel   定位请求在途时收起、再打开（12.2：应重新定位）
//   locate-dialog   细纲对话框开着时来一张项目卡（11.5：应忽略、不关对话框）
// 只读源码，不访问网络，不写文件。
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const FRONTEND = process.cwd();
const SCENARIO = process.argv[2] || 'lock409edit';

let slots = [], cursor = 0, pendingEffects = [], scheduled = false, Component = null, props = null, lastTree = null;
let afterRender = () => {};
function schedule() { if (!scheduled) { scheduled = true; setTimeout(flush, 0); } }
function flush() {
  scheduled = false; cursor = 0; pendingEffects = [];
  lastTree = Component(props);
  afterRender(lastTree);
  for (const run of pendingEffects) run();
}
const React = {
  useState(init) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = { v: typeof init === 'function' ? init() : init };
    const slot = slots[i];
    return [slot.v, next => { const v = typeof next === 'function' ? next(slot.v) : next; if (!Object.is(v, slot.v)) { slot.v = v; schedule(); } }];
  },
  useRef(init) { const i = cursor++; if (!(i in slots)) slots[i] = { current: init }; return slots[i]; },
  useCallback(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.fn; slots[i] = { fn, deps }; return fn; },
  useMemo(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.v; const v = fn(); slots[i] = { v, deps }; return v; },
  useEffect(fn, deps) {
    const i = cursor++; const prev = slots[i];
    if (prev && deps && prev.deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return;
    if (!prev) slots[i] = { deps: null, cleanup: null };
    pendingEffects.push(() => { const p = slots[i]; if (p.cleanup) p.cleanup(); const c = fn(); slots[i] = { deps, cleanup: typeof c === 'function' ? c : null }; });
  },
  useId() { cursor++; return 'id'; },
  useSyncExternalStore(_s, get) { cursor++; return get(); },
};
const jsx = (type, p, key) => ({ type, props: p || {}, key });

const log = [];
const t0 = Date.now();
const stamp = () => ((Date.now() - t0) / 1000).toFixed(2) + 's';
const delay = (ms, value, signal, label, fail) => new Promise((resolve, reject) => {
  let settled = false;
  const t = setTimeout(() => {
    settled = true;
    if (fail) { log.push(`${stamp()} ${label} → ${fail.status} ${fail.message}`); reject(fail); return; }
    log.push(`${stamp()} ${label} 完成`); resolve(typeof value === 'function' ? value() : value);
  }, ms);
  if (signal) signal.addEventListener('abort', () => { if (settled) return; settled = true; clearTimeout(t); log.push(`${stamp()} ${label} 被取消`); reject(Object.assign(new Error('aborted'), { name: 'AbortError' })); });
});

// ---------- 假 DOM（只够 DeskDock 的焦点规则用） ----------
class HTMLElement {
  constructor(name, parent) { this.name = name; this.parent = parent || null; this.isConnected = true; }
  focus() { if (this.isConnected) { document.activeElement = this; log.push(`${stamp()} 焦点 → ${this.name}`); } }
  matches(selector) { return selector === 'button[aria-controls="desk-panel"]' && this.name === '头部「案头」开关'; }
  getClientRects() { return this.isConnected ? [{}] : []; }
  contains(other) { for (let node = other; node; node = node.parent) if (node === this) return true; return false; }
}
global.HTMLElement = HTMLElement;
const body = new HTMLElement('body');
const toggle = new HTMLElement('头部「案头」开关');
const textarea = new HTMLElement('输入框');
const panel = new HTMLElement('案头面板 #desk-panel');
const closeButton = new HTMLElement('面板里的「收起案头」X', panel);
global.document = {
  activeElement: body, hidden: false, body,
  addEventListener() {}, removeEventListener() {},
  querySelector: () => null,
  querySelectorAll: selector => selector === 'button[aria-controls="desk-panel"]' ? [toggle] : [],
};

// ---------- 后端桩 ----------
const A = '11111111-1111-1111-1111-111111111111';
class ApiError extends Error { constructor(m, s) { super(m); this.status = s; } }
const book = { id: A, title: '甲', status: 'completed', chapters_done: 3, words_done: 9000, updated_at: '2026-11-10', chapters: [], config: { batch_size: 3, adaptation: { max_scenes_per_chapter: 6 } }, pending_notes: 0, bible: null, compass: null };
let rebreakdownStarted = false; // 作者在工作室里开始了重新拆解（不改 plan_revision）
const planNow = () => ({
  episodes: [{ id: 'e1', no: 1, title: '一', warnings: [] }, { id: 'e2', no: 2, title: '二', warnings: [] }],
  units: [], unassigned: [], plan_revision: 5, plan_approved_revision: null, g0_approved: false, total_seconds: 400,
  status: 'done',
  active_breakdown_status: rebreakdownStarted ? 'running' : 'done',
  rebreakdown_pending: rebreakdownStarted,
});
const STUBS = {
  react: React, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
  '@/lib/auth': { getUsername: () => 'fixture-user', ensureAccountIdentity: async () => {} },
  '@/lib/agents': { ApiError },
  '@/lib/novels': {
    listNovels: signal => delay(30, [book], signal, 'GET 书目'),
    getNovel: (id, signal) => delay(30, book, signal, 'GET 详情'),
    novelApi: { action: async () => ({}) }, getNovelChapter: async () => ({}), getNovelDraft: async () => ({}),
    addNovelNote: async () => ({}), exportNovel: async () => null, novelErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio': {
    listStudioNovelSources: signal => delay(SCENARIO === 'locate-cancel' ? 800 : 60, { enabled: true, books: [{ id: A, eligible: true, projects: [{ id: 'p1', title: '甲短片', snapshot_no: 1, created_at: '2026-11-10' }] }] }, signal, 'GET 工作室来源'),
    studioErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio-breakdown': {
    getStudioEpisodes: (id, signal) => delay(60, planNow, signal, 'GET 分集方案'),
    // 与后端 breakdown_plan.py 一致：版本号一致、活动拆解 running → 409
    operateStudioEpisodes: (id, op, signal) => delay(60, null, signal, `POST episodes/ops expected_revision=${op.expected_revision}`,
      rebreakdownStarted ? new ApiError('拆解尚未完成，完成后才能修改分集方案', 409) : null),
    approveStudioEpisodes: (id, rev, signal) => delay(60, null, signal, `POST episodes/approve expected_revision=${rev}`,
      rebreakdownStarted ? new ApiError('拆解尚未全部完成，不能批准分集方案', 409) : null),
  },
  '@/components/novel/NovelShell': { canCloseNovelDrawer: () => false },
  './DeskChaptersView': { __esModule: true, default: function DeskChaptersView() {} },
  './DeskDialogs': { DeskPlanDialog() {}, DeskReaderDialog() {} },
  './DeskEpisodesView': { __esModule: true, default: function DeskEpisodesView() {} },
  './DeskFrame': { __esModule: true, default: function DeskFrame() {} },
  './DeskIdeaView': { __esModule: true, default: function DeskIdeaView() {} },
};
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const out = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', 'module', out)(mod.exports, spec => {
    if (spec in STUBS) return STUBS[spec];
    if (spec.startsWith('@/')) { const base = path.join(FRONTEND, spec.slice(2)); return load(fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx'); }
    throw new Error('unexpected import ' + spec);
  }, mod);
  return mod.exports;
}
function find(tree, name) {
  if (!tree || typeof tree !== 'object') return null;
  if (Array.isArray(tree)) { for (const t of tree) { const f = find(t, name); if (f) return f; } return null; }
  if (tree.type && tree.type.name === name) return tree;
  return find(tree.props && tree.props.children, name);
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const { episodeLocks } = load(path.join(FRONTEND, 'lib/desk.ts'));

const stage = SCENARIO.startsWith('lock') ? 'episodes' : 'chapters';
const B = '22222222-2222-2222-2222-222222222222';
const store = new Map([['fiona.desk.v1:fixture-user', JSON.stringify({ open: true, novelId: A, stage })]]);
global.window = { localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }, requestAnimationFrame: cb => setTimeout(cb, 0), cancelAnimationFrame: t => clearTimeout(t), addEventListener() {}, removeEventListener() {}, innerWidth: 1280, setTimeout, clearTimeout };

// 面板挂载/卸载：DeskFrame 渲染出来时把 panelRef 接到假面板上；DeskDock 返回 null 时面板从 DOM 移除，
// 焦点若在面板里就掉到 body（浏览器对被移除的焦点元素就是这么处理的）。
afterRender = tree => {
  const frame = find(tree, 'DeskFrame');
  if (frame) { frame.props.panelRef.current = panel; panel.isConnected = true; closeButton.isConnected = true; }
  else if (panel.isConnected) {
    panel.isConnected = false; closeButton.isConnected = false;
    if (panel.contains(document.activeElement)) { document.activeElement = body; log.push(`${stamp()} 面板卸载，焦点掉到 body`); }
  }
};

const { default: DeskDock } = load(path.join(FRONTEND, 'components/desk/DeskDock.tsx'));
const baseProps = {
  owner: 'fixture-user', open: false, studioAllowed: true, composerHeight: 96, focus: null,
  onAsk() {}, onOpenNovel() {}, onOpenNovelShelf() {}, onOpenStudio() {}, onOpenSettings() {},
  onOpenChange(next) { props = { ...props, open: next }; schedule(); }, // 模拟 page.tsx 的 setDeskOpenPersisted
};

async function lockScenario(kind) {
  props = { ...baseProps, open: true };
  Component = DeskDock(props).type;
  flush();
  await sleep(600);
  let view = find(lastTree, 'DeskEpisodesView').props;
  log.push(`${stamp()} 载入后：plan_revision=${view.plan.plan_revision} editsBlocked=${episodeLocks(view.plan).editsBlocked} approvalBlocked=${episodeLocks(view.plan).approvalBlocked}（案头不轮询未阻塞的方案）`);
  rebreakdownStarted = true;
  log.push(`${stamp()} 作者在工作室发起重新拆解（后端 plan_revision 仍为 5）；回到案头，打开「${kind === 'edit' ? '修改' : '批准分集方案'}」对话框并确认`);
  let outcome;
  try {
    if (kind === 'edit') await view.onOperate({ op: 'edit', no: 1, fields: { title: '作者刚改的标题', change: '', hook: '', notes: '', target_min: null, target_max: null } });
    else await view.onApprove();
    outcome = { rejected: false };
  } catch (error) {
    outcome = { rejected: true, status: error.status, message: error.message };
  }
  await sleep(300);
  view = find(lastTree, 'DeskEpisodesView').props;
  const locks = episodeLocks(view.plan);
  const dialogBusy = kind === 'edit' ? view.busy || locks.editsBlocked : view.busy || locks.approvalBlocked;
  console.log(log.join('\n'));
  console.log(JSON.stringify({
    scenario: SCENARIO,
    onConfirm: outcome,
    notice: view.notice,
    busy: view.busy,
    plan_revision: view.plan.plan_revision,
    editsBlocked: locks.editsBlocked,
    approvalBlocked: locks.approvalBlocked,
    dialogBusyProp: dialogBusy,
    note: 'DeskEpisodesView 把 busy={busy || editsBlocked}（修改/合并）或 busy={busy || approvalBlocked}（批准）传给对话框；EpisodeEditDialog key={plan.plan_revision} 未变，不会重新挂载',
  }));
  process.exit(0);
}

async function xcloseScenario(how) {
  if (how === 'restore') {
    // 刷新页面后 page.tsx 从记忆里恢复 open=true；此时焦点在 body
    document.activeElement = body;
    props = { ...baseProps, open: true };
    Component = DeskDock(props).type;
    flush();
  } else {
    props = { ...baseProps, open: false };
    Component = DeskDock(props).type;
    flush();
    await sleep(50);
    if (how === 'auto') {
      document.activeElement = textarea;
      log.push(`${stamp()} 流式卡片到达，自动打开（焦点在输入框）`);
    } else {
      document.activeElement = toggle;
      log.push(`${stamp()} 作者点头部开关打开（焦点在开关上）`);
    }
    props = { ...props, open: true };
    flush();
  }
  await sleep(300);
  const afterOpen = document.activeElement.name;
  log.push(`${stamp()} 打开后焦点在：${afterOpen}`);
  closeButton.focus();
  log.push(`${stamp()} 作者按 Tab 进入面板，在「收起案头」X 上按回车`);
  find(lastTree, 'DeskFrame').props.onClose();
  await sleep(300);
  console.log(log.join('\n'));
  console.log(JSON.stringify({ scenario: SCENARIO, focusAfterOpen: afterOpen, focusAfterClose: document.activeElement.name }));
  process.exit(0);
}

async function locateCancelScenario() {
  // 12.2 第三条：定位请求还没回来就收起 → 不算走完 → 再打开时重新定位
  props = { ...baseProps, open: true, focus: { subject: { kind: 'project', projectId: 'p1' }, nonce: 7 } };
  Component = DeskDock(props).type;
  store.set('fiona.desk.v1:fixture-user', JSON.stringify({ open: true, novelId: A, stage: 'chapters' }));
  flush();
  await sleep(200);
  log.push(`${stamp()} 定位请求在途时收起案头`);
  props = { ...props, open: false }; flush();
  await sleep(300);
  log.push(`${stamp()} 再打开`);
  props = { ...props, open: true }; flush();
  await sleep(1500);
  const frame = find(lastTree, 'DeskFrame').props;
  console.log(log.join('\n'));
  console.log(JSON.stringify({ scenario: SCENARIO, stage: frame.stage, book: frame.book && frame.book.title }));
  process.exit(0);
}

async function locateDialogScenario() {
  // 11.5 第二条：细纲对话框开着时来一张卡片 → 忽略、不关对话框、不发「工作室来源」
  props = { ...baseProps, open: true };
  Component = DeskDock(props).type;
  flush();
  await sleep(300);
  find(lastTree, 'DeskChaptersView').props.onOpenPlan();
  await sleep(100);
  const before = log.filter(line => line.includes('工作室来源')).length;
  props = { ...props, focus: { subject: { kind: 'project', projectId: 'p1' }, nonce: 9 } }; flush();
  await sleep(500);
  const planOpen = !!find(lastTree, 'DeskPlanDialog');
  const after = log.filter(line => line.includes('工作室来源')).length;
  console.log(log.join('\n'));
  console.log(JSON.stringify({ scenario: SCENARIO, planDialogStillOpen: planOpen, sourcesRequests: after - before, stage: find(lastTree, 'DeskFrame').props.stage }));
  process.exit(0);
}

(async () => {
  if (SCENARIO === 'lock409edit') return lockScenario('edit');
  if (SCENARIO === 'lock409approve') return lockScenario('approve');
  if (SCENARIO === 'xclose-restore') return xcloseScenario('restore');
  if (SCENARIO === 'xclose-auto') return xcloseScenario('auto');
  if (SCENARIO === 'xclose-hand') return xcloseScenario('hand');
  if (SCENARIO === 'locate-cancel') return locateCancelScenario();
  if (SCENARIO === 'locate-dialog') return locateDialogScenario();
  throw new Error('unknown scenario ' + SCENARIO);
})();
```

## 附录 B：服务端渲染真实对话框 `ssr-dialog-lock.js`

在 `frontend/` 目录下运行：`node <路径>/ssr-dialog-lock.js`。用真实的 React 和 `react-dom/server` 渲染真实的 `EpisodeEditDialog`、`BreakdownDialog`，比较 `busy` 为假和为真时「取消」「保存」「确认批准」按钮与 `fieldset` 是否带 `disabled`。只读源码，不访问网络。

```js
// 用真实 React SSR 渲染真实的 EpisodeEditDialog / BreakdownDialog，看 busy 为真时「取消」能否点。
// 在 frontend/ 下运行：node <本文件>。只读源码，不访问网络。
const fs = require('fs');
const path = require('path');
const require2 = require('module').createRequire(path.join(process.cwd(), 'package.json'));
const ts = require2('typescript');
const React = require2('react');
const { renderToStaticMarkup } = require2('react-dom/server');
const FRONTEND = process.cwd();
const Icon = () => null;
const iconModule = new Proxy({}, { get: (_t, key) => key === '__esModule' ? false : Icon });
class ApiError extends Error { constructor(m, s) { super(m); this.status = s; } }
const STUBS = {
  'lucide-react': iconModule,
  'next/link': ({ href, children }) => React.createElement('a', { href }, children),
  '@/lib/agents': { ApiError, apiJson() { throw new Error('offline'); } },
  '@/lib/auth': { apiFetch() { throw new Error('offline'); } },
  '@/lib/config': { API_BASE: '/api' },
  '@/lib/studio': { studioErrorMessage: e => String((e && e.message) || e) },
};
const cache = new Map();
function resolveFile(spec, fromDir) {
  const base = spec.startsWith('@/') ? path.join(FRONTEND, spec.slice(2)) : path.resolve(fromDir, spec);
  for (const c of [base + '.tsx', base + '.ts', base + '.js']) if (fs.existsSync(c)) return c;
  throw new Error('not found ' + spec);
}
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const out = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', 'module', out)(mod.exports, spec => {
    if (spec === 'react') return React;
    if (spec === 'react/jsx-runtime') return require2('react/jsx-runtime');
    if (spec in STUBS) return STUBS[spec];
    return load(resolveFile(spec, path.dirname(file)));
  }, mod);
  return mod.exports;
}
const { EpisodeEditDialog } = load(path.join(FRONTEND, 'components/studio/EpisodePlan.tsx'));
const BreakdownDialog = load(path.join(FRONTEND, 'components/studio/BreakdownDialog.tsx')).default;
const episode = { id: 'e1', no: 1, title: '一', change: '', hook: '', notes: '', target_min: null, target_max: null, warnings: [] };
const pick = (html) => ({
  cancel: (html.match(/<button[^>]*>取消<\/button>/) || [''])[0],
  confirm: (html.match(/<button[^>]*type="submit"[^>]*>[^<]*<\/button>/) || [''])[0],
  fieldset: (html.match(/<fieldset[^>]*>/) || [''])[0],
});
for (const busy of [false, true]) {
  const html = renderToStaticMarkup(React.createElement(EpisodeEditDialog, { episode, busy, onSave: async () => {}, onClose() {} }));
  console.log(`EpisodeEditDialog busy=${busy}`, JSON.stringify(pick(html)));
}
const approve = renderToStaticMarkup(React.createElement(BreakdownDialog, { title: '批准分集方案', confirmLabel: '确认批准', busy: true, onConfirm: async () => {}, onClose() {} }, React.createElement('p', null, '即将批准')));
console.log('BreakdownDialog(批准) busy=true', JSON.stringify(pick(approve)));
```
