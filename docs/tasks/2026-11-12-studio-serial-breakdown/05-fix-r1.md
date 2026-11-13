# 返修单 R1：短片工作室「边写边拆」

你上一轮（r0）的实现已经交回，派单方在沙箱外复跑门禁全过，独立复核认为**实现代码没有违反规格之处**。本轮返修以补测试为主，另有五处小的产品改动。依据是同目录 `02-spec.md` 新增的 **§4.8 R1 返修**（规格已升到 v1.2，只新增这一节）；复核原文在 `04-review.md`，可作参考，但以 §4.8 为准。先完整读 §4.8，再动手。

## 一、硬性规矩

1. **只改 §4.8 列出的 R1 白名单文件**。其他文件（含所有既有测试、r0 已改过的其他文件）一字不动；派单方会把 R1 白名单外的文件与 r0 交回时逐字节比对。
2. 不要 `git commit` / `git stash` / `git checkout` / `git reset`；不要改 `docs/tasks/2026-11-12-studio-serial-breakdown/` 下的 `01-brief.md`、`02-spec.md`、`03-dispatch.md`、`04-review.md`、`05-fix-r1.md`。
3. 不安装、不升级依赖；Python 用 `backend/.venv/bin/python -m pytest ...`；跑测试前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。
4. 不读 `.env` / `.env.local`，不打印密钥；测试离线。
5. 改前端前先读 `frontend/AGENTS.md`；界面文字不加粗。
6. 新测试不得为了通过而放宽 r0 已有的断言；r0 新测试里的断言只能改严或改正（例如 R1-T1 换输入），每处改动在报告里写明理由。
7. 每条 R1-T 都要做「自检」：按 §4.8 括号里的方法临时改坏实现、确认用例变红、再还原。自检用的临时改动不得留在最终结果里（交回前用 `git diff` 确认实现文件只有 R1-P1–P7 的改动）。
8. 何时停下来问：只有「规格与源码事实矛盾」才停下来，在报告里写清证据；其余自行决定并写明理由；任何情况下不回滚已完成的工作。

## 二、并行方式（必须照做）

**用工作流（workflow 工具）并行**：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分。每个 agent 的任务说明必须自包含（写明负责的文件、§4.8 里对应的条目、不得碰的文件，以及「不得调用 subagent / subagent_fork / workflow」）；agent 一律不许再派生；失败先读结果再决定，不许盲目重派。主代理只做拆分、派发、汇总、白名单检查、跑验收、写报告。

建议拆分：

| agent | 负责的文件 | §4.8 条目 |
|---|---|---|
| backend | `backend/studio/sources.py`、`backend/studio/breakdown.py`、`backend/studio/breakdown_plan.py` | R1-P1–P4 |
| frontend | `frontend/components/studio/BreakdownPanel.tsx`、`frontend/components/studio/EpisodePlan.tsx` | R1-P5、R1-P6 |
| docs | `CLAUDE.md`、`docs/ARCHITECTURE.md`、`docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md` | R1-P7、R1-D1 |

第一轮完成后，第二轮并行：

| agent | 负责的文件 | §4.8 条目 |
|---|---|---|
| test-continue | `backend/tests/test_studio_serial_continue.py` | R1-T1–T10 |
| test-frontend | `backend/tests/test_studio_serial_frontend.py` | R1-T11 |

（R1-T8–T10 若放进 `test_studio_serial_sources.py` 更顺手，可以改归 test-continue 以外的一个 agent，但同一文件只归一个 agent。）

## 三、验收与报告

- 逐条执行规格 §5 第 1–7 条，贴原始输出与退出码（取退出码不接管道）。后端全量约 7 分钟，一次跑完。无 `node_modules` 副本的做法同 `03-dispatch.md`。
- 报告写进 `impl/report-r1.md`，内容按 §4.8「R1 报告」；`impl/report.md` 只补 R1-D1 的文档改动位置表。
