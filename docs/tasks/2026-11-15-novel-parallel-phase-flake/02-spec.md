# 02 · 规格 v1.1 — 并行阶段「失败后取消并等完兄弟调用」三条用例：把「让出一次事件循环」换成「等三个调用都到达模型」

- 日期 2026-11-15 · 基线提交 `acd04b6`（main）· 状态：**作者已确认（2026-11-15，原话「同意，两条都改」），可以实施**。
- 分级：改动量是 L1（只动两个测试文件、各一处、共 15 行增 4 行删，不碰实现、不碰数据模型）。它要改既有测试，所以先写成规格经作者确认。
- 复现与归因见同目录 `01-repro.md`；验证脚本与原始输出在 `verify/`。
- 工作目录：本仓库的一个 git worktree，分支 `fix/novel-parallel-phase-flake`。后端在 `backend/`，虚拟环境 `backend/.venv` 已就绪。
- 关于基线：调查与全部测量是在 `19e4bd1` 上做的；确认后分支已快进到 `acd04b6`（中间是两个讨论群提交 `ac815c3`、`acd04b6`）。本规格涉及的三个文件（两个测试文件和 `backend/novel/deliberation.py`）在这两个提交之间没有变化，行号、补丁、两个文件的通过数都不变；全量条数从 8552 变为 8562（`acd04b6` 上 `--collect-only` 实测）。`verify/out/` 里的输出都是 `19e4bd1` 上的。

- **v1.1 · 落地范围收窄（2026-11-15，实施之后追加）**：执行者在 `acd04b6` 上按本规格把两条都改完并通过门禁之后，main 前进到了 `1d6d759`。那个提交已经改掉了第一条（`test_novel_workflow.py`），代码与本规格的补丁逐行相同，只有注释措辞不同。所以落地时第一条采用 main 上已有的版本，本任务带来的改动只剩 `test_novel_r5_deliberation.py` 一处（`verify/proposed-change-r5.patch`，+6 −1），分支已快进到 `1d6d759`。下文 §0–§5 保持派单时的原样，供对照；落地后的验收结果见 `04-gate.md`。§0 第 3 条随之了结：主检出里那处未提交改动已由 `1d6d759` 提交。

**给执行者：你要做的事在 §4（硬规矩与任务清单）和 §5（验收）。先读完全文再动手。**

## 0. 作者的决定

| # | 要定的事 | 决定 | 说明 |
|---|---|---|---|
| 1 | 是否破例修改既有测试 | **同意** | 根因在用例对时序的假设，实现没有错（`01-repro.md` §5）。改的只是「失败的那个角色什么时候失败」，两条用例里的九条断言语句一个字不动。 |
| 2 | 范围 | **两条都改**（`test_novel_workflow.py` 的那条含两个参数，加 `test_novel_r5_deliberation.py` 里写法相同的那条） | 第二条用同一个路由替身、同一句 `await asyncio.sleep(0)`，同样的停顿注入下同样必败（`verify/out/02-matrix-repo-before-fix.txt`）。 |
| 3 | 主检出里那份未提交改动怎么处理 | **未定，不影响本规格的实施** | 2026-11-15 03:27，主检出的 `backend/tests/test_novel_workflow.py` 出现了一处未提交改动（同一条用例、同一思路）。它不是本任务做的，本任务不动它。它与本规格的补丁改的是同一段，合入 main 之前要先由作者决定丢弃还是保留。执行者不要去看、也不要去动主检出。 |

## 1. 目标

1. 这三条用例不再依赖「三个 1 毫秒定时器在事件循环的同一轮到期」。全量里不论回收器、调度器在哪里停顿，结果都一样。
2. 它们仍然证明原来要证明的事：并行阶段里一个调用失败后，`deliberate` 返回之前，另外两个已经在模型里的调用被取消、并且已经收尾。把 `_gather_phase` 改坏，它们仍然变红。
3. 不改实现。`backend/novel/` 下一个字节都不动。

## 2. 现状事实（已核实；行号在 `19e4bd1` 与 `acd04b6` 上相同）

- `backend/tests/test_novel_workflow.py`
  - 19–38 行 `LocalRouter`：`call()` 先 `self.active += 1`，然后 **`await asyncio.sleep(0.001)`（33 行）**，再 `await self.fake(request)`。也就是每个调用要先等一个 1 毫秒定时器，才到达假模型。
  - 181–221 行 `test_failed_parallel_phase_cancels_and_drains_siblings_before_return`（参数 `proposal` / `critique`）。假模型脚本 `delayed_failure` 在到达时 `started.add(role)`；`plot_architect` 在 **195 行 `await asyncio.sleep(0)`** 之后 `raise StepFailed()`；另两个角色 `await asyncio.sleep(10)`，被取消时 `cancelled.add(role)`。
  - 213–219 行五条断言语句：`started` 是三个角色、`cancelled` 是另外两个、`running == set() and router.active == 0`、让出一次后请求数不变、没有 `decision` 请求。
- `backend/tests/test_novel_r5_deliberation.py`
  - 16 行 `from test_novel_workflow import LocalRouter`（同一个替身）。
  - 205–237 行 `test_all_advisor_calls_are_cancelled_and_drained_if_one_fails`：结构相同，阶段是 `critique_plan`，**216 行 `await asyncio.sleep(0)`**；232–235 行四条断言语句。
- `backend/novel/deliberation.py` 32–42 行 `_gather_phase`：为每个协程建任务，`await asyncio.gather(*tasks)`；出任何异常时取消未完成的任务、`await asyncio.gather(*tasks, return_exceptions=True)` 等它们收尾，再抛出。调用点 128、162、184、260 行。
- 全库搜索同型写法（`asyncio.sleep(0)` 后立即失败、再断言兄弟都已开始）：只有上面两处会先过一个定时器。`backend/tests/test_discuss_engine.py` 1538–1546 行写法相似，但三个任务到 `started.add` 之前没有定时器，同一轮内必然都已开始，不受影响，不在本规格范围内。
- 机制与证据（详见 `01-repro.md`）：
  - 三个调用的 1 毫秒定时器先后相差约 30 微秒（共约 60 微秒）排入。只要这段间隙里出现一次约 0.2 毫秒以上的停顿，第一个定时器就会单独先到期；`plot_architect` 到达模型、让出一次、抛错的整个过程不到 0.1 毫秒，早于后面的定时器到期。于是兄弟调用还在路由替身里就被取消，从未到达模型，`started` 缺人，用例在 213 行（第二条用例是 232 行）失败。
  - 失败断言原文：`AssertionError: assert {'character_a...ot_architect'} == {'character_a...ist_designer'}`，`Extra items in the right set: 'twist_designer'`（停顿在第三个调用前）；停顿在第二个调用前时左边只剩 `{'plot_architect'}`。
  - 此时实现照常取消并等完了兄弟调用（`router.active == 0`、没有残留任务）。错的是用例的假设，不是实现。
- 基线数字（本工作树、`backend/.venv` 实测）：
  - 全量条数：`acd04b6` 上 `.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider` 报 `8562 tests collected`。（`19e4bd1` 上全量实跑是 `8552 passed, 47 warnings in 563.30s`，0 失败、0 跳过；`acd04b6` 上的全量没有在改动前单独实跑。）
  - `tests/test_novel_workflow.py` 单跑 `55 passed`；`tests/test_novel_r5_deliberation.py` 单跑 `20 passed`；两个一起 `75 passed`（`acd04b6` 上复测相同）。
  - 对照矩阵 `verify/run_matrix.py repo`：`VERDICT: NOT_SOUND (17 runs differ ...)`，退出码 1（`verify/out/02-matrix-repo-before-fix.txt`）。

## 3. 方案（已确认）

假模型脚本自己数到达的角色。三个都到了，置一个 `asyncio.Event`；要失败的那个角色等这个事件，而不是让出一次。等待带 5 秒超时，只为防止将来的回归把全量挂住。

改动内容以 `verify/proposed-change.patch` 为准（相对仓库根，`git apply --check` 在 `19e4bd1` 和 `acd04b6` 上都通过）：

```diff
--- a/backend/tests/test_novel_workflow.py
+++ b/backend/tests/test_novel_workflow.py
@@ -181,6 +181,7 @@
 @pytest.mark.parametrize("phase", ["proposal", "critique"])
 def test_failed_parallel_phase_cancels_and_drains_siblings_before_return(workshop, phase):
     started, cancelled, running = set(), set(), set()
+    all_started = asyncio.Event()
 
     async def delayed_failure(request, _index):
         if FakeLLM.payload(request)["task"] != phase:
@@ -188,11 +189,16 @@
         role = request["role"]
         started.add(role)
         running.add(role)
+        if len(started) == 3:
+            all_started.set()
         try:
             if role == "plot_architect":
-                # Let all three requests start, then fail without waiting for
-                # the siblings' deliberately slow local model responses.
-                await asyncio.sleep(0)
+                # Fail once all three requests have reached the model, without
+                # waiting for the siblings' deliberately slow responses. Yielding
+                # to the loop once is not enough: the router's 1 ms timers need
+                # not fire in the same iteration. The timeout only keeps a
+                # regression from hanging the suite.
+                await asyncio.wait_for(all_started.wait(), timeout=5)
                 raise StepFailed()
             await asyncio.sleep(10)
         except asyncio.CancelledError:
--- a/backend/tests/test_novel_r5_deliberation.py
+++ b/backend/tests/test_novel_r5_deliberation.py
@@ -204,6 +204,7 @@
 
 def test_all_advisor_calls_are_cancelled_and_drained_if_one_fails(workshop):
     started, cancelled, running = set(), set(), set()
+    all_started = asyncio.Event()
 
     async def broken_advisor(request, _index):
         if FakeLLM.payload(request)["task"] != "critique_plan":
@@ -211,9 +212,13 @@
         role = request["role"]
         started.add(role)
         running.add(role)
+        if len(started) == 3:
+            all_started.set()
         try:
             if role == "plot_architect":
-                await asyncio.sleep(0)
+                # Fail once all three advisors have reached the model; one yield
+                # does not guarantee that (see test_novel_workflow).
+                await asyncio.wait_for(all_started.wait(), timeout=5)
                 raise StepFailed()
             await asyncio.sleep(10)
         except asyncio.CancelledError:
```

这份补丁已经在一次性副本里验证过（不在本工作树，本工作树的测试文件未动）：两个文件 `75 passed`；对照矩阵 `VERDICT: SOUND`；补丁没有增删任何含 `assert` 的行（`verify/out/04-matrix-repo-patched-copy.txt`）。

没有选的做法，以及原因：

| 做法 | 不选的原因 |
|---|---|
| 改 `_gather_phase` 或它的调用方 | 实现没有错。兄弟调用无论停在路由里还是模型里，都被取消并等完（`01-repro.md` §5）。 |
| 去掉或改短 `LocalRouter` 里的 1 毫秒 | 这个替身被两个文件共 75 条用例共用，并发上限那两条靠它让调用重叠。动它等于改 75 条用例的时序。 |
| 多让出几次，或把 `sleep(0)` 换成一段固定时长 | 还是在赌时序，只是把会失败的停顿从 0.2 毫秒抬高到另一个数。 |
| 标成不稳定用例、失败自动重跑 | 掩盖问题，而且真回归时也会被重跑冲掉。 |

## 4. 给执行者的硬规矩与任务清单

1. **白名单**（只允许改动 / 新增这些文件）：
   - `backend/tests/test_novel_workflow.py`（修改，仅 §3 补丁的两段）
   - `backend/tests/test_novel_r5_deliberation.py`（修改，仅 §3 补丁的两段）
   - `docs/tasks/2026-11-15-novel-parallel-phase-flake/03-impl.md`（新增，变更总结）
2. **除 §3 补丁列出的行以外，既有测试一字不许改**：两个文件里任何断言、夹具、`LocalRouter`、其他用例都不动；不新增测试。`backend/novel/` 不动。`verify/` 下的文件不动。
3. 不改 `frontend/`，不改 `.env*`，不加依赖。**不要 commit**，不要 `git checkout` / `git stash` / 改分支；改动留在工作区。
4. **用工作流（workflow 工具）并行**：在脚本里用 `parallel()` 同时运行 2 个 agent，按文件不重叠拆分——agent A 只改 `backend/tests/test_novel_workflow.py`，agent B 只改 `backend/tests/test_novel_r5_deliberation.py`。每个 agent 的任务说明必须自包含（把 §3 里对应文件的那段补丁原文贴给它），并写明**不得调用 subagent / subagent_fork / workflow**。agent 不带 schema，直接返回文本。主代理只做拆分、派发、汇总、白名单检查、跑 §5、写 `03-impl.md`；报告开头列拆分表，如实列出全部派出过的代理；agent 失败先读它的结果再决定，不许盲目重派。
5. **何时停下来问**：只有「规格自相矛盾」或「按规格无法实现」才停下并说明。只影响「怎么实现 / 怎么验证」的事自己定，并在 `03-impl.md` 写明理由。你实测到的事实优先于本规格的断言，不符就停下来说明。任何情况下不回滚已完成的工作。
6. `03-impl.md` 必须含五项：修改了哪些文件 / 实现了什么 / 与本节任务清单逐项对应 / §5 每条验收的实际输出 / 未完成或需人工确认的地方。最终回复里把 `03-impl.md` 的内容原样贴出。

任务清单：

- 4.1 `backend/tests/test_novel_workflow.py`：按 §3 补丁的前两段修改 `test_failed_parallel_phase_cancels_and_drains_siblings_before_return`。
- 4.2 `backend/tests/test_novel_r5_deliberation.py`：按 §3 补丁的后两段修改 `test_all_advisor_calls_are_cancelled_and_drained_if_one_fails`。
- 4.3 跑 §5 全部验收，写 `03-impl.md`。

## 5. 验收（全部从仓库根或 `backend/` 执行，命令里写明）

- **5-A 改动集合**（仓库根）：`git status --porcelain | grep -v 'docs/tasks/2026-11-15-novel-parallel-phase-flake/'` 的输出恰好是下面两行（顺序不限），多一行少一行都不过：
  ```
   M backend/tests/test_novel_r5_deliberation.py
   M backend/tests/test_novel_workflow.py
  ```
  任务目录内只允许新增 `03-impl.md`；其余文件与派单时逐字节相同，由门禁用派单前记下的哈希清单比对。
- **5-B 改动形状**（仓库根）：
  - `git diff --numstat -- backend/tests` 输出恰好两行：`6	1	backend/tests/test_novel_r5_deliberation.py` 和 `9	3	backend/tests/test_novel_workflow.py`。
  - `git apply -R --check docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/proposed-change.patch` 退出码 0（工作区里的改动能被这份补丁原样撤销，即与补丁一致）。
  - 断言未动：`git diff -U0 -- backend/tests | grep -cE '^[-+][^-+].*assert '` 输出 `0`（没有匹配时 grep 的退出码是 1，属正常，只看输出）。前置校验：`git diff -U0 -- backend/tests | grep -c '^@@'` 输出 `6`（证明这条命令真的扫到了六段改动）。
- **5-C 两个文件**（`backend/`）：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_workflow.py tests/test_novel_r5_deliberation.py` → `75 passed`，0 失败、0 跳过。
- **5-D 对照矩阵**（`backend/`）：`.venv/bin/python ../docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/run_matrix.py repo` → 最后一行 `VERDICT: SOUND`，退出码 0。含义：不停顿、在任一兄弟调用前停顿 0.2 / 2 / 20 毫秒，三条用例每次都是 `3 passed`；把 `_gather_phase` 换成四种坏实现（取消但不等、普通 gather、逐个执行、等但不取消），三条用例每次都是 `3 failed`。基线上同一命令是 `VERDICT: NOT_SOUND`、退出码 1。脚本对每次运行都校验「恰好执行了三条用例」，否则报 `BROKEN`、退出码 2，不会把没跑到当成通过。
- **5-E 全量**（`backend/`）：`.venv/bin/python -m pytest -q -p no:cacheprovider` → `8562 passed`，0 失败、0 跳过（条数与改动前相同：没有新增或删除用例）。全量约 10 分钟。执行者注意：如果在你的沙箱里有用例因为沙箱限制而失败或被跳过，把完整的失败 / 跳过清单如实写进 `03-impl.md`，不要为此改动任何文件；这一条以 Claude 在沙箱外重跑的结果为准。

门禁由 Claude 在执行者沙箱外重跑 5-A 至 5-E，另加一项执行者不必做的正控：

- **门禁附加 · 让解释器自己的回收落进间隙**（`backend/`）：`.venv/bin/python ../docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/gc_sweep.py --whole-file --generation keep --start 1716 --stop 1762 --step 1 --expect-sound` → 最后一行形如 `runs: 46, failed: 0; collection inside the gap: N, of which failed: 0`，其中 N ≥ 10，退出码 0。这条命令不注入停顿，只逐个挪动回收器计数，让解释器自己的回收落在 critique 阶段三个调用先后发出的间隙里。退出码 2 表示回收没有落进间隙（区间随机器和版本会移动），这时正控不算数，要换区间重扫，不能当成通过。基线上同一做法在回收落进间隙时失败 17/45（机器忙）和 1/14（机器闲），见 `verify/out/06-gc-sweep-single-process.txt`；打了补丁的副本是 0/30 和 0/14。

## 6. 不在本规格范围内

- `_gather_phase` 在「等兄弟收尾期间自己又被取消」时的行为，没有检查，与本问题无关。
- Linux / CI 上的时序没有实测。机制与平台无关（任何事件循环上，间隙里出现足够长的停顿都会触发），改后的写法不依赖时序，所以不需要按平台区分。
- 主检出里那份未提交改动的去留（§0 第 3 条）。
