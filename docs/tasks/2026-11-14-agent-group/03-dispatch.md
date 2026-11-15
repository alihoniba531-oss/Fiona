# 派单：多智能体讨论群第一期（规格 v1.1）

你在 Fiona 仓库的专用 worktree 里工作（当前目录就是仓库根，分支 `feat/agent-group`，基线 `859e2c5`）。任务的唯一依据是 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1，作者已确认）。先完整读一遍规格和它引用的 `docs/tasks/2026-11-14-agent-group/verify/pilot.py`，再动手；规格里没写的不要自行扩展。

## 一、硬性规矩

1. 只改规格第 9 节白名单里的文件。既有测试的输入、断言与夹具一字不改，唯一例外是白名单写明的 `backend/tests/conftest.py` 第 52 行。
2. 不要 `git commit`、`git stash`、`git checkout`、`git reset`。不要改 `docs/tasks/2026-11-14-agent-group/` 下除 `impl/` 以外的任何文件（包括 `verify/pilot.py`）。报告写在 `impl/report.md`。
3. `backend/.venv` 已经就绪：不要安装或升级任何依赖（不要 `pip install`、`uv`、`npm install`），不新增依赖。Python 一律用 `backend/.venv/bin/python`，从 `backend/` 目录运行，例如 `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_api.py`。
4. 跑测试的命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。
5. 不读 `.env`、`.env.local`，不打印任何密钥；测试必须离线，不得调用真实模型或真实搜索。
6. 不修改 `backend/novel/`、`backend/studio/`、`backend/services/`、`backend/byok/`、`backend/tools/`、`backend/song/`、`frontend/` 下任何文件。需要它们的功能就 import（规格第 3 节第 5 条列了可以直接引用的名字）。
7. 何时停下来问见规格第 7 节。你实测到的事实优先于规格的断言；任何情况下不回滚已完成的工作。
8. 提示词按规格附录 A 办：从 `verify/pilot.py` 逐字搬，只做附录列出的改动。不要改写、润色、翻译或「优化」这些文字。

## 二、并行方式（必须照做）

用工作流（workflow 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分。规矩：

- 同一个文件只归一个 agent，不同 agent 不得改同一个文件。
- 每个 agent 的任务说明必须自包含：写明它负责的文件、要读的规格章节号（让它自己去读 `02-spec.md` 的那些节和 `verify/pilot.py`）、它不得碰的文件，以及「不得调用 subagent、subagent_fork、workflow」。agent 看不到你的对话。
- agent 一律不许再派生子代理。agent 失败时先读它的结果再决定，不许盲目重派。
- 主代理（你）只做：拆分、派发、汇总、白名单检查、跑验收、写报告。需要返修时，按文件归属再开一轮工作流派给对应的 agent。

分三批，批内并行、批间串行（后一批的 agent 要读前一批写好的文件，任务说明里写明让它先读哪些文件）：

**第一批**

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| base | `backend/discuss/__init__.py`、`backend/discuss/config.py`、`backend/discuss/roles.py`、`backend/discuss/schemas.py` | 第 2、3 节，4.2、4.4、4.7，附录 A |
| data | `backend/discuss/store.py`、`backend/discuss/billing.py` | 第 2、3 节，4.3、4.10、4.11 |
| wiring | `backend/database.py`（规格 4.3 与 4.14 写明的三处）、`backend/tests/conftest.py`（只改第 52 行） | 4.3、4.14、第 9 节 |

三个 agent 之间的接口以规格为准：表名与列名（4.3）、`DISCUSS_TABLES_DDL`、`DiscussStepStore` 的成员（4.10）、`DiscussBilling` 的方法（4.11）、校验器的名字与行为（4.7）。wiring 写的 `database.py` 会 import `discuss.store` 与 `discuss.runner`，这两个文件由别的 agent 写，import 放在函数内部（照该文件里书斋与写歌的写法）。

**第二批**（先读第一批写好的 `backend/discuss/*.py`）

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| research | `backend/discuss/research.py`、`backend/discuss/avatar.py` | 4.8、4.9，附录 A |
| engine | `backend/discuss/engine.py` | 4.4、4.6 全部、4.7、4.9 |
| runner | `backend/discuss/runner.py` | 4.5、4.12 |

engine 调用 research 的 `run_search`、`collect_findings` 与 avatar 的 `build_avatar_system`，签名以规格 4.8、4.9 为准。runner 调用 engine 的 `run_planning`、`run_rounds` 并捕获 `engine.SearchUnavailable`。engine 的入口函数怎么接收上下文由 engine 与 runner 两个 agent 按同一约定写：`async def run_planning(store, router)` 与 `async def run_rounds(store, router)`，其余需要的数据从 `store` 与数据库读。

**第三批**（先读前两批写好的全部文件）

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| api | `backend/discuss/service.py`、`backend/routers/discuss.py`、`backend/main.py`（规格 4.12 写明的四处） | 4.2、4.5、4.13 |
| tests-core | `backend/tests/test_discuss_schemas.py`、`backend/tests/test_discuss_billing.py`、`backend/tests/test_discuss_engine.py` | 第 6 节的场景 4–13、16、17、21–23 中不经 HTTP 的部分 |
| tests-api | `backend/tests/test_discuss_api.py`、`backend/tests/test_discuss_runner.py`、`backend/tests/test_discuss_structure.py` | 第 6 节的场景 1–3、14、15、18、19 以及经 HTTP 的端到端场景 |
| docs | `backend/.env.example`、`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/tests/test_discuss_docs.py` | 4.15、第 6 节场景 20 |

测试文件可以比上表多（都以 `test_discuss_` 开头），但第 6 节的 23 个场景每个都要有用例，并在报告里给出「场景编号 → 测试函数」的对照表。测试 agent 写测试时发现实现有错，不许放宽断言来迁就实现；把问题记下来，由你再开一轮工作流派给该实现文件的归属 agent 修。

第三批完成后，由你跑一遍规格第 8 节的验收；有失败就按文件归属开新一轮工作流修，直到全部满足。

## 三、验收与报告

- 逐条执行规格第 8 节第 1–10 条，贴出原始输出与退出码；取退出码时不要接管道。
- 第 2 条的后端全量约需 7 分钟，一次跑完，不要分片。另用 `--collect-only -q` 报出每个新测试文件的收集数和全量收集数。
- 第 3 条「基线对照」的做法：在系统临时目录建一个基线检出（`git worktree add --detach <临时目录> 859e2c5`），把新测试文件拷进去，用本 worktree 的 `backend/.venv/bin/python` 从它的 `backend/` 目录运行新测试，贴出结果，然后 `git worktree remove --force <临时目录>`。如果沙箱不允许 `git worktree add`，在报告里说明，这一条留给规格作者做。
- 第 9 条「无 `frontend/node_modules` 的副本」：本 worktree 的 `frontend/node_modules` 是存在的，所以要另建副本验证。用 `rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' ./ <副本>/` 建到系统临时目录（保留 `backend/.venv`），在副本的 `backend/` 里跑新测试，要求全部通过、0 跳过，用完删除副本。
- 第 10 条：不必真的起服务，用测试客户端在未设置 `FIONA_DISCUSS` 的环境下请求 `/discuss/access` 与 `/health` 即可（可以写成一个测试用例）。
- 报告写进 `docs/tasks/2026-11-14-agent-group/impl/report.md`，不写本机绝对路径。开头先列拆分表：如实列出全部派出过的 agent（含返修轮）、各自负责的文件与结果。然后写五项：
  1. 修改了哪些文件（与白名单逐条对照，附 `git status --porcelain --untracked-files=all` 原文）；
  2. 实现了哪些功能；
  3. 与任务清单及测试场景 1–23 的逐项对应；
  4. 测试结果（第 8 节每条的命令、输出摘要、退出码）；
  5. 未完成或需要人工确认的地方（包括你自行决定的事项与理由、与规格不符的实测事实）。
