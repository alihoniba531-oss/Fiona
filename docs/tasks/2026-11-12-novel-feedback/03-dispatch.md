# 派单：修改意见卡（规格 v1.3）

你在 Fiona 仓库的专用 worktree 里工作（当前目录就是仓库根，分支 `feat/novel-feedback`，基线 `7a17f64`）。任务的唯一依据是同目录的 `docs/tasks/2026-11-12-novel-feedback/02-spec.md`（v1.3）。先完整读一遍规格，再动手；规格里没写的不要自行扩展。

## 一、硬性规矩

1. **只改规格 §4.1 白名单里的文件**；既有测试只许改 §4.5 授权的那一个文件的两处。改动集合按 §5 第 6 条逐条核对。
2. 不要 `git commit` / `git stash` / `git checkout` / `git reset`；不要改 `docs/tasks/2026-11-12-novel-feedback/` 下的 `01-brief.md`、`02-spec.md`、`03-dispatch.md`。
3. `backend/.venv` 与 `frontend/node_modules` 已经就绪：**不要**安装或升级任何依赖（不要 `npm install` / `npm ci` / `pip install` / `uv`），不新增依赖。Python 一律用 `backend/.venv/bin/python -m pytest ...`。
4. 不读 `.env` / `.env.local`，不打印任何密钥；测试必须离线（仓库的 conftest 已阻断真实网络）。
5. 改前端代码前先读 `frontend/AGENTS.md`，以及 `frontend/node_modules/next/dist/docs/` 里与你要改的写法相关的 Next.js 16 文档。界面文字不加粗（规格 §4.3 T6 第 2 条）。
6. `frontend/app/page.tsx` 以 UTF-8 BOM 开头，必须按字节读写，改完 `head -c 3 frontend/app/page.tsx | xxd -p` 仍为 `efbbbf`。
7. 何时停下来问：见规格 §6。只有「规格与源码事实矛盾」才停下来，在报告里写清矛盾点与证据；只影响怎么实现 / 怎么验证的问题自行决定并写明理由；你实测到的事实优先于规格的断言；任何情况下不回滚已完成的工作。
8. 本机 `NO_PROXY` 含 `[::1]` 时，跑测试的命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

## 二、并行方式（必须照做）

**用工作流（workflow 工具）并行**：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分，拆得越细越好。规矩：

- 同一个文件（及它对应的测试）只归一个 agent；不同 agent 不得改同一个文件。
- 每个 agent 的任务说明必须**自包含**：写明它负责的文件、规格里对应的章节号（让它自己去读 `02-spec.md` 的那些节）、它不得碰的文件，以及「不得调用 subagent / subagent_fork / workflow」。agent 看不到你的对话。
- agent 一律不许再派生子代理。
- agent 失败时先读它的结果再决定，不许盲目重派。
- 主代理（你）只做：拆分、派发、汇总、白名单检查、跑验收（§5）、写报告；需要返修时，按文件归属再开一轮工作流派给对应的 agent。

建议的拆分（可以更细，但不能出现文件重叠）：

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| db | `backend/database.py`、`backend/agent_store.py` | §4.2 T1 |
| novel | `backend/novel/feedback.py`（新）、`backend/novel/service.py`、`backend/routers/novel.py` | §4.2 T2、T3 |
| chat | `backend/studio/sources.py`、`backend/services/claude_agent.py`、`backend/services/chat_service.py` | §4.2 T4 |
| card | `frontend/lib/novelFeedback.ts`（新）、`frontend/components/NovelFeedbackCard.tsx`（新） | §4.3 T5、T6 |
| wiring | `frontend/components/ChatBubble.tsx`、`frontend/lib/useConversations.ts`、`frontend/app/page.tsx` | §4.3 T7 |
| desk | 三份 desk 文件、`backend/tests/test_desk_polish_frontend.py`（新） | §8 |
| docs | 六份文档（`CLAUDE.md`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example`） | §4.4 |
| test-backend | `backend/tests/test_novel_chat_feedback.py`（新）、`backend/tests/test_studio_sources_readonly_integration.py`（只许两处） | §4.5 后端 |
| test-frontend | `backend/tests/test_novel_chat_feedback_frontend.py`（新） | §4.5 前端 |

各 agent 之间的接口以规格为准（函数名、签名、返回的键、文案逐字），不要自己发明。第一轮全部完成后，由你跑一遍全部验收；有失败就按文件归属开第二轮工作流修，直到 §5 全部满足。

## 三、验收与报告

- 逐条执行规格 §5 第 1–9 条（含第 5 条「无 node_modules 副本」的 rsync 命令与 `SKIPPED [n]` 计数），**贴出原始输出与退出码**；取退出码时不要接管道。
- 报告写进 `docs/tasks/2026-11-12-novel-feedback/impl/report.md`（各 agent 的过程记录可放在同目录其他 `.md`）。报告开头先列**拆分表**：如实列出全部派出过的 agent（含返修轮），每个 agent 负责的文件与结果。然后写五项：
  1. 修改了哪些文件（与 §4.1 白名单逐条对照，附 `git status --porcelain --untracked-files=all` 原文）；
  2. 实现了哪些功能；
  3. 与规格任务清单的逐项对应（T1–T7、§4.4、§4.5 每条、§8）；
  4. 测试结果（§5 每条的命令、原始输出摘要、退出码）；
  5. 未完成或需人工确认的地方（包括你按 §6 自行决定的事项与理由、与规格不符的实测事实、白名单外发现但没改的同类陈述）。
