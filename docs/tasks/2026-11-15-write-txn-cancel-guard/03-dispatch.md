# 派单：写库取消保护（规格 v1.0）

你在 Fiona 仓库的专用 worktree 里工作（当前目录就是仓库根，分支 `fix/write-txn-cancel-guard`，基线 `19e4bd1`）。任务的唯一依据是 `docs/tasks/2026-11-15-write-txn-cancel-guard/02-spec.md`（v1.0，作者已确认）。先完整读一遍规格，再读本文件。规格没写的地方不要自由发挥。

## 一、硬性规矩

1. 只改规格第 6 节清单里的文件。既有测试、`backend/tests/conftest.py`、`backend/tests/_fakes.py` 一个字都不许改。
2. 不要 `git commit`、`git stash`、`git checkout`、`git reset`、`git restore`。不要改 `docs/tasks/2026-11-15-write-txn-cancel-guard/` 下除 `impl/` 以外的任何文件。报告写在 `impl/report.md`。
3. `backend/.venv` 已经就绪：不要安装或升级任何依赖（不要 `pip install`、`uv`、`npm install`），不新增依赖。Python 一律用 `backend/.venv/bin/python`，测试从 `backend/` 目录运行，例如 `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_db_txn_guard.py`。
4. 跑测试的命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。
5. 不读 `.env`、`.env.local`，不打印任何密钥。测试必须离线，不得调用真实模型。
6. 规格 3.2 的替换必须逐字节干净：除了把 `aiosqlite.connect(` 换成 `db_txn.connect(`、每个文件加一行 `from utils import db_txn`，被改的文件不得有任何其他变化（空白、换行符、文件末尾有没有换行、import 顺序、注释都不许动）。所以这一步**用一次性脚本做文本替换**，不要让模型逐个文件手改：
   - 用搜索找出全部含 `aiosqlite.connect(` 的非测试文件（规格 3.2 给了命令）。
   - 对每个文件：按原样读入（`open(path, encoding="utf-8", newline="")`），`text.replace("aiosqlite.connect(", "db_txn.connect(")`；找到第一行去掉首尾空白后等于 `import aiosqlite` 的行，在它下一行插入缩进相同的 `from utils import db_txn`；按原样写回（同样 `newline=""`）。
   - `backend/utils/db_txn.py` 不参与替换。脚本用完就删，不要留在仓库里。
   - 然后只对 `backend/novel/billing.py` 手改 `_drain` 的函数体（规格 3.3）。
7. 什么时候停下来问见规格第 8 节。你实测到的事实优先于规格的说法；任何情况下不回滚已完成的工作。
8. `backend/utils/db_txn.py` 的实现提示（行为以规格 3.1 为准）：退出时把「有异常就回滚」放在 `try` 里、把原来的关闭放在 `finally` 里，这样回滚这一步即使被再次取消，关闭也照常执行；回滚用 `contextlib.suppress(Exception)` 包住。`drain` 可以对照 `backend/novel/billing.py` 里现有的 `_drain`，只补上「调用方已被取消时，内层的普通异常要换成 `CancelledError` 并把它设为 `__cause__`」这一种情况。

## 二、并行方式（必须照做）

用工作流（workflow 工具）并行：在脚本里用 `parallel()` 同时运行多个 agent，按文件不重叠拆分。规矩：

- 同一个文件只归一个 agent，不同 agent 不得改同一个文件。
- 每个 agent 的任务说明必须自包含：写明它负责的文件、要读的规格章节号（让它自己去读 `02-spec.md` 的那些节）、本文件第一节里和它有关的规矩、它不得碰的文件，以及「不得调用 subagent、subagent_fork、workflow」。
- agent 一律不许再派生子代理。agent 失败时先读它的结果再决定，不许盲目重派。
- 主代理（你）只做：拆分、派发、汇总、改动范围检查、跑验收、写报告。需要返修时，按文件归属再开一轮工作流派给对应的 agent。

分两批，批内并行、批间串行。

**第一批**

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| guard | `backend/utils/db_txn.py` | 3.1、3.5；本文件第一节第 8 条 |
| replace | 规格第 6 节「修改」里的 21 个后端文件（含 `backend/novel/billing.py` 的 `_drain`） | 第 2 节「代码现状」、3.2、3.3、3.5；本文件第一节第 6 条 |
| sweep | `backend/tests/cancel_sweep.py` | 4.1；先读 `docs/tasks/2026-11-15-write-txn-cancel-guard/verify/` 下的 `mechanism_probe.py`、`mechanism_probe2.py`、`real_code_repro.py`，里面的注入器可以照着改写 |
| docs | `docs/ARCHITECTURE.md`、`CLAUDE.md` | 3.4 |

四个 agent 之间的接口：`utils.db_txn.connect` 与 `utils.db_txn.drain` 的名字和行为以规格 3.1 为准，replace 不用等 guard 写完。`cancel_sweep.py` 对外提供什么函数由 sweep 定，要在文件开头的文档字符串里写清用法，第二批的 agent 照着用。

第一批完成后，你先做一次冒烟再开第二批：

- 规格 A1 的两条 `grep`（期望 0 与 148）。
- 从 `backend/` 跑这几个既有测试文件，必须全过：`tests/test_health_and_startup.py tests/test_exchange_poll_connection.py tests/test_discuss_runner.py tests/test_novel_p1_runner.py tests/test_novel_p1_billing.py tests/test_studio_breakdown_r1_pipeline.py`。
- 规格 A6 的 `real_code_repro.py`（期望末行 `REAL_CODE_REPRO cancel_points=73 follow_up_failed=0`）。

**第二批**（任务说明里写明：先读 `backend/utils/db_txn.py` 和 `backend/tests/cancel_sweep.py`）

| agent | 负责的文件 | 规格章节 |
|---|---|---|
| guard-tests | `backend/tests/test_db_txn_guard.py` | 3.1、4.1、4.2 |
| paths-main | `backend/tests/test_write_cancel_paths.py` | 4.1、4.3（三条收尾用例；参数化里 `exchange_store`、`novel` 两行） |
| paths-core | `backend/tests/test_write_cancel_paths_core.py` | 4.1、4.3（参数化里 `agent_store`、`database`、`trace` 三行） |
| paths-misc | `backend/tests/test_write_cancel_paths_misc.py` | 4.1、4.3（参数化里 `byok.store`、`song.store`、`studio.sources` 三行） |
| static | `backend/tests/test_db_txn_static.py` | 4.4 |

对写测试的 agent 的要求（写进它们的任务说明）：

- 准备数据怎么造，去读被测函数的源码和既有的同模块测试（只读、可以照抄其中的造数代码到自己的新文件里，但不许改既有测试）。
- 造数据不要用 `INSERT OR IGNORE`：约束不满足时它会静默不插入，用例就在空数据上空转。插完要断言行确实在。
- 参数化用例的每个函数，都要保证它的写事务里至少有一条查询返回了行（规格 4.3）。自查办法：在用例里临时打印每个取消点的调用标签，确认扫到了 `SELECT` 并且那条查询有结果；确认后去掉打印。
- 发现实现或 `cancel_sweep.py` 有问题，不许放宽断言去迁就，也不许去改别人的文件；把问题写在结果里交回主代理，由主代理按文件归属派人修。
- 自己负责的测试文件写完要自己跑通，结果里贴命令和输出末行。

第二批完成后，由你跑第三节的验收；有失败就按文件归属开新一轮工作流修，直到全部满足。

## 三、验收与报告

逐条执行规格第 7 节，贴出原始输出与退出码；取退出码时不要接管道。

- A1、A3、A4、A6：照规格执行。A4 的后端全量约需 8 分钟，一次跑完，不要分片；另用 `--collect-only -q` 报出每个新测试文件的收集数和全量收集数。规格「不做」里列的那条偶发用例如果在全量里失败，单独复跑它一次，把两次结果都写进报告，不要改它。
- A2：从仓库根目录运行规格给的命令。这个脚本会调 `git status`、`git show`、`git diff`、`git ls-files`。如果沙箱里 git 报权限错误，在命令前加 `GIT_OPTIONAL_LOCKS=0` 再试；还不行就在报告里写明报错原文，这一条由规格作者在沙箱外补做。
- A5：只做表格第一行的自查。做法：先把 `backend/utils/db_txn.py` 复制到系统临时目录留底，再把它里面回滚的那一步临时去掉，从 `backend/` 跑三个 `tests/test_write_cancel_paths*.py`，把输出末尾的失败清单贴进报告；然后用留底的文件覆盖回去，重跑这三个文件确认全过。报告里要列出「去掉回滚后**没有**变红的参数」——应当一个都没有；如果有，说明那条用例的准备数据没让查询返回行，派回给对应的 agent 补数据。其余几行由规格作者在门禁里做。
- A7：新测试里不要读 git 历史、仓库之外的文件、`frontend/node_modules`。浅克隆副本的实跑由规格作者做。
- A8：贴出两份文档里新增的原文。

报告写进 `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`，不写本机绝对路径。开头先列拆分表：如实列出全部派出过的 agent（含返修轮）、各自负责的文件与结果。然后写五项：

1. 修改了哪些文件（与规格第 6 节逐条对照，附 `git status --porcelain --untracked-files=all` 原文；git 不可用时改用文件清单并说明）。
2. 实现了哪些功能。
3. 与规格第 5 节任务清单的逐项对应；另给两张对照表：规格 4.2 的每条要求 → 测试函数名；规格 4.3 表里的每个函数 → 所在文件与参数名、它的取消点数、其中落在返回了行的查询上的取消点数。
4. 测试结果（每条验收的命令、输出末行、退出码）。
5. 没做完的、与规格不一致的、需要人确认的地方。没有就写「无」。
