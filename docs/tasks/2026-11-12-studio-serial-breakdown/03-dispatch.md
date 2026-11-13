# 派单：短片工作室「边写边拆」（规格 v1.1）

你在 Fiona 仓库的专用 worktree 里工作（当前目录就是仓库根，分支 `feat/studio-serial-breakdown`，基线 `135253f`）。任务的唯一依据是同目录的 `docs/tasks/2026-11-12-studio-serial-breakdown/02-spec.md`（v1.1，作者已确认）。先完整读一遍规格，再动手；规格里没写的不要自行扩展。

## 一、硬性规矩

1. **只改规格 §4.1 白名单里的文件**；既有测试只许做 §4.6 第 1 条授权的改动。改动集合按 §5 第 6 条逐条核对。
2. 不要 `git commit` / `git stash` / `git checkout` / `git reset`；不要改 `docs/tasks/2026-11-12-studio-serial-breakdown/` 下的 `01-brief.md`、`02-spec.md`、`03-dispatch.md`。报告写在同目录的 `impl/` 下。
3. `backend/.venv` 与 `frontend/node_modules` 已经就绪：**不要**安装或升级任何依赖（不要 `npm install` / `npm ci` / `pip install` / `uv`），不新增依赖。Python 一律用 `backend/.venv/bin/python -m pytest ...`。
4. 不读 `.env` / `.env.local`，不打印任何密钥；测试必须离线（仓库的 conftest 已阻断真实网络）。
5. 改前端代码前先读 `frontend/AGENTS.md`，以及 `frontend/node_modules/next/dist/docs/` 里与你要改的写法相关的 Next.js 16 文档。界面文字不加粗（规格 §4.4 开头）。
6. 何时停下来问：见规格 §6。只有「规格与源码事实矛盾」或「必须改 §4.6 没授权的既有测试」才停下来，在报告里写清矛盾点与证据；只影响怎么实现 / 怎么验证的问题自行决定并写明理由；你实测到的事实优先于规格的断言；任何情况下不回滚已完成的工作。
7. 本机 `NO_PROXY` 含 `[::1]` 时，跑测试的命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。
8. `studio/**` 不得新增任何 `novel.*` 导入；注释和字符串里也不得出现规格 §4.2 第 8 条禁止的文字。

## 二、并行方式（必须照做）

**用工作流（workflow 工具）并行**：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好。规矩：

- 同一个文件（及它对应的测试）只归一个 agent；不同 agent 不得改同一个文件。
- 每个 agent 的任务说明必须**自包含**：写明它负责的文件、规格里对应的章节号（让它自己去读 `02-spec.md` 的那些节）、它不得碰的文件，以及「不得调用 subagent / subagent_fork / workflow」。agent 看不到你的对话。
- agent 一律不许再派生子代理。
- agent 失败时先读它的结果再决定，不许盲目重派。
- 主代理（你）只做：拆分、派发、汇总、白名单检查、跑验收（§5）、写报告；需要返修时，按文件归属再开一轮工作流派给对应的 agent。

建议分两轮（可以更细，但不能出现文件重叠）。

**第一轮（实现，并行）**

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| sources | `backend/studio/sources.py`、`backend/studio/novel_chat.py`、`backend/services/claude_agent.py`（只改 `:125`、`:845`）、`backend/intent_router.py`（只改 `:148`）、`backend/.env.example`（只改 `:231`）；授权改动的 `backend/tests/test_studio_sources.py`、`backend/tests/test_novel_chat.py`、`backend/tests/test_novel_chat_feedback.py`；新文件 `backend/tests/test_studio_serial_sources.py` | §2.1、§2.4、§3 第 1–3 条、§4.2、§4.5、§4.6 第 1 条（对应部分）与第 2 条 |
| breakdown | `backend/studio/breakdown.py`、`backend/studio/breakdown_material.py`、`backend/studio/breakdown_plan.py`、`backend/routers/studio.py` | §2.2、§3 第 4–10 条、§4.3 全部 |
| studio-ui | `frontend/lib/studio.ts`、`frontend/lib/studio-breakdown.ts`、`frontend/components/studio/` 下的 `BreakdownPanel.tsx`、`BreakdownStage.tsx`、`BreakdownQuoteDialog.tsx`、`EpisodePlan.tsx`、`SourcePanel.tsx`、`SourceChoices.tsx`、`CreateProjectDialog.tsx` | §2.3、§4.4 第 1–8、10 条 |
| novel-ui | `frontend/components/novel/NovelWorkbench.tsx`、`frontend/components/novel/NovelFilmDialog.tsx`、`frontend/components/NovelFeedbackCard.tsx`（只改 `:397` 那半句）；授权改动的 `backend/tests/test_studio_sources_frontend.py`（只改 `:118` 那条）、`backend/tests/test_novel_chat_feedback_frontend.py`（只改 `WRITTEN_DESCRIPTION`） | §4.4 第 9、11、12 条，§4.6 第 1 条（对应部分） |
| docs | `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md` | §4.7、§7 |

各 agent 之间的接口以规格为准（函数名、参数、返回的键、组件 prop、导出名 `SerialSourceHints`、文案逐字），不要自己发明。novel-ui 用到 studio-ui 新增的 `SerialSourceHints` 与 `ExistingSourceProjects` 的 `chaptersDone` prop，按规格 §4.4 第 8 条的签名写。

**第二轮（新测试，在第一轮完成后并行）**

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| test-continue | `backend/tests/test_studio_serial_continue.py`（新） | §2.4 夹具、§4.6 第 3 条 |
| test-frontend | `backend/tests/test_studio_serial_frontend.py`（新） | §2.4 驱动、§4.6 第 4 条 |

第二轮完成后，由你跑一遍全部验收；有失败就按文件归属开新一轮工作流修，直到 §5 全部满足。新测试发现实现有错时，修实现的 agent 是该实现文件的归属 agent，不许为了让测试通过去放宽新测试的断言。

## 三、验收与报告

- 逐条执行规格 §5 第 1–8 条，**贴出原始输出与退出码**；取退出码时不要接管道。
- §5 第 4 条的后端全量约需 7 分钟，请一次跑完，不要分片。另用 `--collect-only -q` 报出三个新文件各自的收集数，以及全量收集数。
- §5 第 5 条「无 node_modules 副本」的做法：

  ```
  rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' <worktree>/ <副本>/
  cd <副本>/backend && .venv/bin/python -m pytest -q -p no:cacheprovider -rsf tests/test_studio_serial_sources.py tests/test_studio_serial_continue.py tests/test_studio_serial_frontend.py
  ```

  副本放在系统临时目录，rsync 时保留 `backend/.venv`。要求 0 failed；按每行 `SKIPPED [n]` 的 n 求和，核对与起 node 的用例数一致，并逐行贴出 skip 原因。用完删除副本。
- 下列既有文件单独再跑一次并贴结果：`tests/test_studio_sources.py tests/test_studio_sources_frontend.py tests/test_studio_sources_readonly_integration.py tests/test_novel_chat.py tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py tests/test_studio_breakdown_*.py tests/test_studio_casting_*.py tests/test_design_system_gate.py tests/test_desk_contract_frontend.py`。
- 报告写进 `docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md`（各 agent 的过程记录可放在同目录其他 `.md`）。报告开头先列**拆分表**：如实列出全部派出过的 agent（含返修轮），每个 agent 负责的文件与结果。然后写五项：
  1. 修改了哪些文件（与 §4.1 白名单逐条对照，附 `git status --porcelain --untracked-files=all` 原文）；
  2. 实现了哪些功能；
  3. 与规格任务清单的逐项对应（T1–T10 每条，§4.6 每条授权改动）；
  4. 测试结果（§5 每条的命令、原始输出摘要、退出码）；
  5. 未完成或需人工确认的地方（包括你按 §6 自行决定的事项与理由、与规格不符的实测事实、白名单外发现但没改的同类陈述）。
