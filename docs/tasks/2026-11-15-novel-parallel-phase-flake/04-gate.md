# 04 · 门禁记录

- 日期 2026-11-15。门禁全部由 Claude 在执行者沙箱之外亲自运行，不采信执行者自报的结果。
- 执行者：dsh 引擎，DeepSeek Flash，推理档 max，作业 `cx-20261115-043239-fc2809`，用时 646 秒。实施记录见 `03-impl.md`。
- 独立复核：没有做。作者 2026-11-15 的决定是按 L1 处理（原话「不用复核，按 L1 处理」）。
- 结论：**通过**。落地后的状态是分支 `fix/novel-parallel-phase-flake` 位于 `1d6d759`，工作区只有 `backend/tests/test_novel_r5_deliberation.py` 一处改动（+6 −1）和本任务目录。没有 commit，没有合入，没有推送。

## 落地范围为什么变成了一处

作者确认的是两条都改，执行者也在 `acd04b6` 上把两条都改了，第一轮门禁全部通过（下表）。门禁期间 main 前进到了 `1d6d759`：另一个提交在 04:40 改掉了第一条（`test_novel_workflow.py`），并已推送。它的代码与本任务的补丁逐行相同，去掉注释行后两个版本没有差异，只有注释措辞不同。

所以落地时第一条采用 main 上已有的版本，本任务工作区里对它的那处改动被撤掉（内容仍在 `verify/proposed-change.patch` 的前半段里）。分支快进到 `1d6d759`，只保留 main 还没有的 r5 那一处。两条用例最终都改了，其中一条来自 `1d6d759`，一条来自本任务。

r5 那条在 `1d6d759` 上仍然需要改：把 main 上未改的版本单独取出来，在兄弟调用前停顿 2 毫秒，它失败；工作区里改后的版本通过（下表最后一行）。

## 第一轮：基线 `acd04b6`，两条都改（执行者交付的状态）

| 验收 | 结果 |
|---|---|
| 5-A 改动集合 | 只有两个测试文件为 `M`；任务目录除新增 `03-impl.md` 外，17 个文件与派单前的 SHA-256 清单逐字节相同 |
| 5-B 改动形状 | `6 1 test_novel_r5_deliberation.py`、`9 3 test_novel_workflow.py`；`git apply -R --check verify/proposed-change.patch` 退出码 0；`-U0` 共 6 段；含 `assert` 的增删行 0 |
| 5-C 两个文件 | `75 passed`，0 失败、0 跳过 |
| 5-D 对照矩阵 | `VERDICT: SOUND`，退出码 0 |
| 门禁附加：回收落进间隙 | 两遍，每遍 `runs: 46, failed: 0; collection inside the gap: 14, of which failed: 0`，退出码 0（当时全量正在同一台机器上跑） |
| 5-E 全量 | `8562 passed, 47 warnings in 449.07s`，退出码 0，0 失败、0 跳过 |

## 第二轮：基线 `1d6d759`，只剩 r5 一处（落地的状态）

| 验收 | 结果 |
|---|---|
| 5-A 改动集合 | 只有 `backend/tests/test_novel_r5_deliberation.py` 为 `M` |
| 5-B 改动形状 | `6 1 test_novel_r5_deliberation.py`；`git apply -R --check verify/proposed-change-r5.patch` 退出码 0；`-U0` 共 3 段；含 `assert` 的增删行 0 |
| 5-C 两个文件 | `75 passed`，0 失败、0 跳过 |
| 5-D 对照矩阵（第一条用 main 上的版本，r5 用工作区的版本） | `VERDICT: SOUND`，退出码 0 |
| 门禁附加：回收落进间隙 | `runs: 46, failed: 0; collection inside the gap: 14, of which failed: 0`，退出码 0 |
| 5-E 全量 | `8562 passed, 47 warnings in 463.70s`，退出码 0，0 失败、0 跳过 |
| r5 这处改动是否仍有必要 | 兄弟调用前停顿 2 毫秒：main（`1d6d759`）上未改的 r5 用例 `1 failed`（停在第二个或第三个调用前都是）；工作区的 r5 用例 `1 passed` |

全量结果的判读方式：退出码直接取自 pytest 进程；另数了进度行（119 行），其中带失败 / 报错标记的 0 行，带跳过标记的 0 行。

## 执行者报告里需要知道的一点

执行者在自己的沙箱里直接跑全量时，20 个测试模块在收集阶段报错：沙箱注入的 `NO_PROXY` 里有带方括号的 `[::1]`，httpx 解析时抛 `InvalidURL`。这是执行者沙箱的环境问题，与本次改动无关；它没有为此改任何文件，覆盖这个环境变量后自测 `8562 passed`。门禁在沙箱外用规格原文的命令跑，没有遇到这个问题。

## 门禁期间对任务目录做的两处改动（都不是代码）

- `03-impl.md` 第 4 行原本写了工作树的本机绝对路径，已改为不含路径的说明。仓库是公开的。
- 新增 `verify/proposed-change-r5.patch`：原补丁里 r5 那个文件的部分，供第二轮的补丁一致性检查用。原补丁 `verify/proposed-change.patch` 保持不变。
