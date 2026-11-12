# 案头第一期 · 第四轮独立复核报告

- 复核对象：基线 `9adf34c` 上叠加的待审改动，R5 之后的工作区。
- 范围：只核验第三轮报告 `10-review-r3.md` 第 5.1 节的那 1 条必须修复（规格 v1.5 第 14.1 节），不重审前三轮已通过的部分。
- 依据：规格 `02-spec.md` 第 14 节，`.cache/review/` 下的材料，以及本轮在工作区里实际运行的结果。实施方报告和验收方门禁记录只当线索，文中结论都由下面的命令输出支撑。
- 复核方没有调用 subagent / subagent_fork / workflow。

## 1. 结论

**通过。**

- 第三轮必须修复 5.1 已修好：
  - 夹具改动逐条符合规格 14.1 的四条要求。
  - 当前代码下这条用例通过，操作前方案确实未锁定（`beforeActive == "done"`），409 之后变成 `running`。
  - G9 让这条用例变红（同一变异在 R4 版测试上仍是全过，说明区别正来自这次夹具修正）。
  - G2 仍让这条用例变红，G3 仍让真冲突用例变红。
- R5 只改了 `backend/tests/test_desk_dock_races_frontend.py` 的 5 行：
  - 其余 16 个改动文件与 R4 结束时逐字节相同；
  - 实施方没有新增或删除文件；
  - 新测试仍为 100 条，全量仍为 8011 条。
- 这处改动没有带出新问题：
  - `locked` 只在两个锁定场景里被置真，其他场景的驱动行为与 R4 完全一致；
  - 12 条容器用例连跑三遍、四路并发各一遍，都是 `12 passed`。
- 新测试 `100 passed`，全量 `8011 passed`，0 失败、0 跳过。
- 必须修复：无。

## 2. 上一轮必须修复 5.1 的核验

### 2.1 夹具改动与规格 14.1 四条要求逐条对照

R5 对该测试文件的全部改动（`.cache/review/r4-to-r5.diff` 中该文件一节，复核方已用它反推出 R4 版并核对哈希，见 3.1）：

```text
327c327
< let locked = LOCK;
---
> let locked = false;
410a411
>   const beforeActive = view.plan.active_breakdown_status;
425a427
>     beforeActive,
521a524
>     assert edit["beforeActive"] == "done"
530a534
>     assert approve["beforeActive"] == "done"
```

| 14.1 要求 | 现状（行号为 R5 文件） | 结论 |
|---|---|---|
| 1. `let locked = LOCK;` → `let locked = false;`；`locked = true; operationConflict = true;` 与 `let operationConflict = LOCK \|\| CONFLICT;` 不动 | 第 327 行已改；第 328 行 `let operationConflict = LOCK \|\| CONFLICT;`、第 412 行 `locked = true; operationConflict = true;` 都与 R4 相同（diff 里没有这两行） | 符合 |
| 2. 在把 `locked` 置真**之前**记下 `view.plan.active_breakdown_status`，放进最后输出的 JSON，字段名 `beforeActive` | 第 411 行 `const beforeActive = view.plan.active_breakdown_status;` 位于第 412 行置真之前；第 427 行加进 `console.log(JSON.stringify({...}))` | 符合 |
| 3. 修改、批准两个场景都断言 `beforeActive == "done"`，保留原有断言 | 第 524、534 行新增；`onConfirm`、`notice is None`、`planRevision == 5`（修改）、`activeStatus == "running"` 全部保留（diff 只有新增行） | 符合 |
| 4. 「载入未阻塞方案后」这句日志保持原文，并与实际一致 | 第 413 行原文未动；下面 2.2 的探针输出显示此时方案确实是 `done`，与日志相符 | 符合 |

两个 node 驱动在 R4、R5 之间的差别（把两版文件里的驱动字符串逐行比较）：

```text
--- r4 NODE_FOCUS_DRIVER
+++ r5 NODE_FOCUS_DRIVER
@@ -71 +71 @@
-let locked = LOCK;
+let locked = false;
@@ -154,0 +155 @@
+  const beforeActive = view.plan.active_breakdown_status;
@@ -169,0 +171 @@
+    beforeActive,
NODE_DRIVER identical: True
```

### 2.2 当前代码：用例通过，操作前确实未锁定

```text
$ cd backend && .venv/bin/python -m pytest -q tests/test_desk_dock_races_frontend.py -rsf
12 passed in 34.89s
```

用探针 `.cache/r5rev/probe.py` 直接运行两版驱动。探针只给 R4 驱动补上与 R5 相同的 `beforeActive` 记录，测试文件本身不动：

```text
== r4 lockedit    {..."notice":null,"busy":false,"planRevision":5,"activeStatus":"running","beforeActive":"running"}
== r5 lockedit    {..."notice":null,"busy":false,"planRevision":5,"activeStatus":"running","beforeActive":"done"}
== r4 lockapprove {..."notice":null,"busy":false,"planRevision":5,"activeStatus":"running","beforeActive":"running"}
== r5 lockapprove {..."notice":null,"busy":false,"planRevision":5,"activeStatus":"running","beforeActive":"done"}
```

- R4 夹具：方案在操作前就是 `running`，与操作后相同，所以用例证明不了刷新。这正是上一轮指出的问题。
- R5 夹具：操作前 `done`，操作后 `running`。
- 两个场景的 `onConfirm` 都是 `{"rejected":true,"status":409,"message":<后端原因>}`。

R5 驱动 `lockedit` 的时间线（探针额外打印 `log`）：

```text
0.25s GET 分集方案 完成
0.56s 载入未阻塞方案后，在工作室发起重新拆解；回到案头执行 edit
0.62s GET 分集方案 完成        ← 非冲突 409 之后容器重新取方案
```

在 0.86s 读取结果，距刷新回包还有约 240ms 余量。另外两点说明结果确实来自 409 之后的那次重新取数：

- 方案初始未锁定，容器每 5 秒一次的「锁定轮询」在操作前不会启动。
- 方案变锁定后，轮询最早也要到约 5.6s 才会触发，早于这个时间点场景已经结束。

### 2.3 变异必须让用例变红

三个变异都按规格 14.1 的写法做在 `frontend/components/desk/DeskDock.tsx` 上。每次做完都按原字节写回，并校验 sha256 为 `925361b1…3a43ec34`。

| 变异 | 测试文件 | 结果 | 失败点 |
|---|---|---|---|
| G9 | R4 版（反推还原的副本） | `12 passed` | ——（问题本身，说明旧夹具没有证明力） |
| G9 | R5 版，跑全部 100 条新测试 | `1 failed, 99 passed` | `test_non_conflict_409_keeps_reason_and_refreshes_locked_plan`：`assert 'done' == 'running'`（第 525 行，修改场景） |
| G2（两处 `isRevisionConflict(...)` → `true`） | R5 版，100 条 | `1 failed, 99 passed` | 同一条用例：`{'scenario': 'lockedit', 'onConfirm': {'rejected': False}, 'notice': '分集方案已在别处改动，已为你刷新，请再试一次。', ...}`（第 517 行） |
| G3（两处 → `false`） | R5 版，100 条 | `1 failed, 99 passed` | `test_real_version_conflict_sets_notice_and_resolves`：`assert result["onConfirm"] == {"rejected": False}`，实际 `{'rejected': True, 'status': 409, ...}` |

G9 只在修改场景的断言处报错，批准场景的断言没有执行到。为了确认批准场景的新断言也有证明力，复核方另外做了两个单点变异：

| 变异 | 改法 | 结果 |
|---|---|---|
| G9A | 只把 `approvePlan` 里 `const refreshed = await refreshPlanAfterConflict(targetProjectId);` 换成 `const refreshed = null as StudioEpisodePlan \| null;` | `1 failed, 11 passed`，失败在第 535 行 `approve["activeStatus"]`：`'done' == 'running'` |
| G9E | 只把 `operatePlan` 里的同一句换成同样写法 | `2 failed, 10 passed`：非冲突用例在第 525 行失败（`'done' == 'running'`），真冲突用例也失败（不刷新就无法识别版本变化） |

G9 下的探针输出：

```text
== r4 lockedit    {..."activeStatus":"running","beforeActive":"running"}
== r5 lockedit    {..."activeStatus":"done","beforeActive":"done"}
== r4 lockapprove {..."activeStatus":"running","beforeActive":"running"}
== r5 lockapprove {..."activeStatus":"done","beforeActive":"done"}
```

可以看到，在 G9 这种「只在版本真变了才替换方案」的错误实现下，R5 夹具里的方案停留在 `done`，用例变红；R4 夹具看不出这个区别。

**结论**：5.1 已修好，这条容器用例现在能区分「刷新并替换了方案」和「没有替换」。

## 3. R5 改动范围核验

### 3.1 哈希核对

```text
$ shasum -a 256 -c .cache/review/r4-files.sha256
CLAUDE.md: OK
PLAN.md: OK
README.md: OK
backend/tests/test_desk_contract_frontend.py: OK
backend/tests/test_desk_dock_races_frontend.py: FAILED
backend/tests/test_desk_logic_frontend.py: OK
backend/tests/test_desk_views_frontend.py: OK
backend/tests/test_ui_closeout_dialog_scrim.py: OK
docs/ARCHITECTURE.md: OK
frontend/app/page.tsx: OK
frontend/components/desk/DeskChaptersView.tsx: OK
frontend/components/desk/DeskDialogs.tsx: OK
frontend/components/desk/DeskDock.tsx: OK
frontend/components/desk/DeskEpisodesView.tsx: OK
frontend/components/desk/DeskFrame.tsx: OK
frontend/components/desk/DeskIdeaView.tsx: OK
frontend/lib/desk.ts: OK
shasum: WARNING: 1 computed checksum did NOT match
```

16 行 OK，只有预期中的测试文件不一致。全部变异实验结束后又核对了一遍，结果相同。

确认 diff 就是该文件的全部改动：

- 把 `r4-to-r5.diff` 中该文件一节反向应用到当前文件的副本，得到的 R4 版 sha256 为 `d77f303d…30776`，与 `r4-files.sha256` 记录的值完全一致。
- 因此 R5 对这个文件的改动就是 2.1 列出的 5 行：1 行修改、4 行新增。
- 当前文件的 sha256 为 `fa1422a0…d75eef`。

其他核对：

- `git diff` 与 `.cache/review/diff.patch` 逐字节相同（`cmp` 无输出）。
- `git diff main -- frontend/app/page.tsx | shasum -a 256` 为 `825086b0…187d4b`，与上一轮相同。
- 任务目录里 R5 的变化：`02-spec.md` 升到 v1.5，新增 `11-fix-r5.md`，这两处是规格作者改的；`impl/主代理.md` 只在末尾追加了「## R5」，diff hunk 为 `@@ -992,3 +992,227 @@`，只有新增行。

### 3.2 文件增删

- `git status --porcelain --untracked-files=all`（排除 `.cache/`）共 36 条：6 个已跟踪文件被修改，30 个未跟踪文件。
- 未跟踪文件清单与 `.cache/review/untracked.txt` 完全一致：用 `core.quotepath=false` 比较，`diff` 无输出。
- 与实施方 R4 记录里的清单相比，只多了 `10-review-r3.md` 和 `11-fix-r5.md`，分别由第三轮复核方和规格作者新增。
- `r4-to-r5.diff` 用 `diff -ruN` 生成，覆盖整棵树（排除缓存与依赖目录）。其中只有 `11-fix-r5.md` 是新文件，没有删除项。
- 结论：实施方没有新增或删除文件。（以上清点是在写本报告之前做的；本报告 `12-review-r4.md` 由复核方新增，不计入。）

### 3.3 测试条数

- `pytest --collect-only -q tests/test_desk_*.py`：`100 tests collected`。
- 竞态文件里的测试函数，R4 与 R5 两版都是同样的 11 个，展开后共 12 条（其中跳过检查参数化为 2 条）。反推出的 R4 版副本实测 `12 passed`。
- `NODE_DRIVER`（第一个驱动）两版逐字相同。
- 全量 `8011 passed`，与 R4 相同。

## 4. 测试结果

```text
$ cd backend && .venv/bin/python -m pytest -q tests/test_desk_*.py -rsf
100 passed in 42.29s
```

本机环境变量 `NO_PROXY` 含 `[::1]`。上面这条按原样运行即可通过；加上 `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1` 前缀再跑一遍，结果也是 `100 passed in 42.20s`。

```text
$ cd backend && NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 .venv/bin/python -m pytest -q
8011 passed, 35 warnings in 337.67s (0:05:37)
exit=0
```

0 failed、0 skipped。35 条 warnings 都是第三方库的 DeprecationWarning（slowapi、pypinyin）。全量是在任何变异之前跑完的。源码没有变化，按任务说明没有重跑 `tsc`、lint、build。

同一驱动里其他场景的检查（任务第 3 项）：

- `locked` 在 R5 驱动里只出现在四处：第 327 行初值；`planNow` 里两处读取（`active_breakdown_status`、`rebreakdown_pending`）；第 412 行置真，它只在 `lockScenario` 里执行。
- 对 `conflict`、`xclose-*`、`locatecancel` 这些场景，`LOCK` 恒为 `false`，所以 R4 的 `let locked = LOCK;` 与 R5 的 `let locked = false;` 完全等价。
- 两版驱动对这五个场景的实际输出逐字相同：

```text
== r4/r5 conflict        {"onConfirm":{"rejected":false},"notice":"分集方案已在别处改动，已为你刷新，请再试一次。","planRevision":6,"activeStatus":"done"}
== r4/r5 xclose-restore  {"focusAfterOpen":"body","focusAfterClose":"头部「案头」开关"}
== r4/r5 xclose-auto     {"focusAfterOpen":"输入框","focusAfterClose":"头部「案头」开关"}
== r4/r5 xclose-hand     {"focusAfterOpen":"案头面板 #desk-panel","focusAfterClose":"头部「案头」开关"}
== r4/r5 locatecancel    {"stage":"episodes","book":"甲"}
```

稳定性：

```text
## run 1  12 passed in 34.89s
## run 2  12 passed in 34.87s
## run 3  12 passed in 34.88s
```

另外让四路 pytest 同时跑同一个文件，作为负载下的抽查：四路都是 `12 passed in 35.05s`。

## 5. 必须修复

无。

## 6. 可优化

1. **实施方报告的一处行号偏差**（文档，不影响代码与测试）：`impl/主代理.md` 的「## R5」写的是「第 412 行『载入未阻塞方案后』日志保持原文」，但插入 `beforeActive` 之后，这句日志在第 413 行（第 412 行是 `locked = true; operationConflict = true;`）。其余行号（327、411、427、524、534）都对。不需要为此单独返修。

规格 13.7、14.2 留给作者裁定的各点，以及前几轮已列过的可优化项，这里不再重复。

## 7. 变异实验记录

**做法**：

- 脚本 `.cache/r5rev/mutate.py` 逐个应用变异：
  - 应用前校验 `DeskDock.tsx` 的起始哈希为 `925361b1…3a43ec34`；
  - 每处替换都检查匹配次数（G9 第一处 1 次、第二处 2 次；G2/G3 各 2 次；G9A/G9E 在 2 处里只换指定的一处）；
  - 跑 pytest 或探针；
  - 在 `finally` 里按原字节写回，并校验 sha256。
- 所有实验都在全量测试跑完之后串行进行。
- 实验结束后：
  - `shasum -a 256 -c .cache/review/r4-files.sha256` 仍是 16 OK、1 个预期不一致；
  - `DeskDock.tsx` 为 `925361b1…3a43ec34`；
  - `git status`（排除 `.cache/`）与实验前一致；
  - 运行中生成的 `backend/.pytest_cache/` 已删除，忽略列表恢复为只有 `backend/.venv/` 与 `frontend/node_modules/`。

| 编号 | 位置与改法 | 变异后 sha256（前 8 位） | 测试范围 | 结果 | 结论 |
|---|---|---|---|---|---|
| — | 不变异，跑反推的 R4 版测试 | — | 12 | `12 passed` | 副本可用 |
| G9 | `refreshPlanAfterConflict` 删掉 `setPlan(next); setPlanLoading(false); setPlanError(null);`，只留 `return next;`；`operatePlan`、`approvePlan` 冲突分支在 `setPlanNotice(PLAN_CONFLICT_TEXT);` 前加 `if (refreshed) setPlan(refreshed);` | `0e2c6454` | R4 版 12 条 | `12 passed` | 旧夹具没有证明力（复现 5.1） |
| G9 | 同上 | `0e2c6454` | R5 全部 100 条 | `1 failed, 99 passed`（非冲突用例，第 525 行） | **5.1 已修好** |
| G9A | 只让 `approvePlan` 的 409 分支不刷新 | `68f8d644` | R5 竞态 12 条 | `1 failed`（非冲突用例，第 535 行批准断言） | 批准场景断言独立有效 |
| G9E | 只让 `operatePlan` 的 409 分支不刷新 | `eb83a897` | R5 竞态 12 条 | `2 failed`（非冲突用例第 525 行；真冲突用例） | 修改场景断言独立有效 |
| G2 | 两处 `isRevisionConflict(currentPlan.plan_revision, refreshed)` → `true` | `62280326` | R5 全部 100 条 | `1 failed, 99 passed`（非冲突用例） | 有证明力 |
| G3 | 两处 → `false` | `b000ea80` | R5 全部 100 条 | `1 failed, 99 passed`（真冲突用例） | 有证明力 |

**探针**：`.cache/r5rev/probe.py`。

- 它从 R4 副本和当前测试文件里分别取出 `NODE_FOCUS_DRIVER`，直接用 node 运行。只读源码，不访问网络，不写文件。
- 对 R4 驱动只在内存里补上 `beforeActive` 记录；加 `--log` 时多打印一行时间线。
- 跑过的组合：
  - 当前代码与 G9 下的 `lockedit` / `lockapprove`，结果见 2.2、2.3；
  - 当前代码下的 `conflict`、`xclose-restore`、`xclose-auto`、`xclose-hand`、`locatecancel`，结果见第 4 节。

## 8. 给实施方的修改指令

无。
