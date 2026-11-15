# 写库取消保护 · 实施报告

规格：`docs/tasks/2026-11-15-write-txn-cancel-guard/02-spec.md` v1.0
基线：`19e4bd1`；分支：`fix/write-txn-cancel-guard`。
本报告不写本机绝对路径；命令均从仓库根或 `backend/` 执行。

## 拆分与派发记录

两批工作流，批内并行、批间串行；没有返修轮（第一批、第二批均一次通过，主代理复跑与验收也没有触发返修派单）。所有 agent 都按文件归属拆开，同一文件只归一个 agent。

| 轮次 | agent | 负责的文件 | 结果 |
|---|---|---|---|
| 第一批 | guard | `backend/utils/db_txn.py` | 完成。`connect` 八条行为、`drain` 五行 + `__cause__`；自测 11 项、anyio 二次取消、原生二次取消、GeneratorExit、参数透传与对象同一性全部通过；另跑 2 个既有测试文件 84 passed。 |
| 第一批 | replace | 规格第 6 节「修改」里的 21 个后端文件（含 `backend/novel/billing.py` 的 `_drain`） | 完成。148 处替换、21 行导入、`_drain` 改为委托；`check_mechanical.py 19e4bd1` 末行 `problems=0`，21 个文件语法编译通过。 |
| 第一批 | sweep | `backend/tests/cancel_sweep.py` | 完成。602 行扫描辅助；delivered/queued、原生/anyio、prepare、逐点记录、写锁检查、零点和还原保护均已自测。 |
| 第一批 | docs | `docs/ARCHITECTURE.md`、`CLAUDE.md` | 完成。ARCHITECTURE 新增 6 行小节，CLAUDE 工作约定新增 1 条；只改这两个文件。 |
| 第二批 | guard-tests | `backend/tests/test_db_txn_guard.py` | 完成。31 条用例，`31 passed`（复跑 4 次一致），对照组测出 7 个 LOCKED 点。 |
| 第二批 | paths-main | `backend/tests/test_write_cancel_paths.py` | 完成。3 条收尾写库用例 + 10 个参数，`13 passed`。 |
| 第二批 | paths-core | `backend/tests/test_write_cancel_paths_core.py` | 完成。17 个参数，`17 passed`。 |
| 第二批 | paths-misc | `backend/tests/test_write_cancel_paths_misc.py` | 完成。3 个参数，`3 passed`；`studio.sources._save_snapshot` 也真实造数完成，未省略。 |
| 第二批 | static | `backend/tests/test_db_txn_static.py` | 完成。5 条用例，`5 passed`；扫 191 个文件、148 处 `db_txn.connect(`。 |

主代理只做拆分、派发、汇总、改动范围检查、验收与报告；未亲自改实现或测试文件（报告除外）。

## 1. 修改了哪些文件

### 1.1 与规格第 6 节逐条对照

**新增（8 个，含本报告）：**

- `backend/utils/db_txn.py`
- `backend/tests/cancel_sweep.py`
- `backend/tests/test_db_txn_guard.py`
- `backend/tests/test_write_cancel_paths.py`
- `backend/tests/test_write_cancel_paths_core.py`
- `backend/tests/test_write_cancel_paths_misc.py`
- `backend/tests/test_db_txn_static.py`
- `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`

**修改（23 个 = 21 个后端文件 + 2 个文档）：**

- `backend/agent_store.py`
- `backend/byok/store.py`
- `backend/conversation_matcher.py`
- `backend/database.py`
- `backend/discuss/billing.py`
- `backend/discuss/store.py`
- `backend/exchange_store.py`
- `backend/main.py`
- `backend/manage_strawberries.py`
- `backend/novel/billing.py`
- `backend/novel/drafts.py`
- `backend/novel/feedback.py`
- `backend/novel/store_db.py`
- `backend/routers/me.py`
- `backend/routers/plaza.py`
- `backend/scripts/fix_matches.py`
- `backend/song/jobs.py`
- `backend/song/media.py`
- `backend/song/store.py`
- `backend/studio/store.py`
- `backend/trace.py`
- `docs/ARCHITECTURE.md`
- `CLAUDE.md`

没有修改 `backend/tests/conftest.py`、`backend/tests/_fakes.py`、任何既有测试、`docs/tasks/2026-11-15-write-txn-cancel-guard/` 下除 `impl/report.md` 以外的任何文件。没有执行 `git commit` / `git stash` / `git checkout` / `git reset` / `git restore`。

### 1.2 `git status --porcelain --untracked-files=all` 原文

```
 M CLAUDE.md
 M backend/agent_store.py
 M backend/byok/store.py
 M backend/conversation_matcher.py
 M backend/database.py
 M backend/discuss/billing.py
 M backend/discuss/store.py
 M backend/exchange_store.py
 M backend/main.py
 M backend/manage_strawberries.py
 M backend/novel/billing.py
 M backend/novel/drafts.py
 M backend/novel/feedback.py
 M backend/novel/store_db.py
 M backend/routers/me.py
 M backend/routers/plaza.py
 M backend/scripts/fix_matches.py
 M backend/song/jobs.py
 M backend/song/media.py
 M backend/song/store.py
 M backend/studio/store.py
 M backend/trace.py
 M docs/ARCHITECTURE.md
?? backend/tests/cancel_sweep.py
?? backend/tests/test_db_txn_guard.py
?? backend/tests/test_db_txn_static.py
?? backend/tests/test_write_cancel_paths.py
?? backend/tests/test_write_cancel_paths_core.py
?? backend/tests/test_write_cancel_paths_misc.py
?? backend/utils/db_txn.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/01-investigation.md
?? docs/tasks/2026-11-15-write-txn-cancel-guard/02-spec.md
?? docs/tasks/2026-11-15-write-txn-cancel-guard/03-dispatch.md
?? docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/callgraph.19e4bd1.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/callgraph.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/disconnect_probe.out.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/disconnect_probe.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/inventory.19e4bd1.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/mechanism_probe.out.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/mechanism_probe.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/mechanism_probe2.out.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/mechanism_probe2.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.19e4bd1.out.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.prototype.out.txt
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/verify/txn_inventory.py
```

说明：`docs/tasks/2026-11-15-write-txn-cancel-guard/` 下的 `01-investigation.md`、`02-spec.md`、`03-dispatch.md`、`verify/*` 是任务开始前就已存在的输入文件（开工时第一次 `git status` 已列出）；本次只读了它们，没有改动。实现造成的变更严格限于规格第 6 节的 23 个修改文件、7 个新增代码/测试文件和本报告。

范围自查（脚本按第 6 节白名单逐行比对）输出：

```
MODIFIED_ALLOWED 23
NEW_ALLOWED 8
PREEXISTING_OR_OUT_OF_SCOPE 17
SCOPE_OK
```

17 条全部是上述任务输入文件。

## 2. 实现了哪些功能

### 2.1 `backend/utils/db_txn.py`

- `connect(*args, **kwargs)`：`@contextlib.asynccontextmanager`，内部 `async with aiosqlite.connect(*args, **kwargs) as db`。参数原样透传，调用时经 `aiosqlite` 模块属性取 `connect`（既有测试替换该属性仍生效）；交出的 `db` 就是连接对象本身。
- 有异常离开（`except BaseException`，含 `CancelledError`、`GeneratorExit`）时先 `await db.rollback()`，再让外层 `aiosqlite.connect` 的 `__aexit__` 执行原来的关闭，原异常裸 `raise` 继续向外。
- 回滚自身抛 `Exception` 子类时用 `contextlib.suppress(Exception)` 吞掉；回滚等待时再次被取消，关闭仍会被送进 aiosqlite 工作队列并执行。
- 无异常退出时不额外 commit/rollback，只关闭；不支持 `db = await db_txn.connect(...)`。
- `drain(operation)`：把 operation 放进独立任务，循环 `asyncio.shield`；正常返回时返回同一个值，普通异常原样抛出，内层自取消抛 `CancelledError`；调用方被取消时等内层结束后再抛 `CancelledError`，若内层抛普通异常则把它设为 `__cause__`。任何返回/抛出前内层任务都已结束。

### 2.2 全站替换与 `_drain`

- 21 个非测试后端文件里的 148 处 `aiosqlite.connect(` 机械替换为 `db_txn.connect(`；每个文件在第一处 `import aiosqlite` 的下一行、以相同缩进插入一行 `from utils import db_txn`。原有 `import aiosqlite` 全部保留，其它字节未动。
- 三个函数内 import 的文件（`manage_strawberries.py`、`routers/me.py`、`routers/plaza.py`）导入放在同一个函数里；`main.py` 只按模块级第一处 import 插入，函数内第二处保留。
- `novel/billing.py` 的 `NovelBilling._drain` 保留 `@staticmethod`、名字、签名和文档字符串，函数体改为 `return await db_txn.drain(operation)`。
- 没有新增依赖，没有改任何 SQL 文本、事务边界或函数签名/返回值。

### 2.3 测试辅助与新增测试

- `backend/tests/cancel_sweep.py`：取消点扫描器。支持 `mode="delivered"|"queued"`、`cancel="task"|"anyio"`、每点前 `prepare`、逐点 `check`；记录 `k`、`label`、`cancelled`、`check_result`、`check_completed`；零点抛 `NoCancelPointsFound`；anyio 检查在 `CancelScope(shield=True)` 中运行；`try/finally` 还原 `aiosqlite.core.Connection._execute` 与 `set_result`；提供 `write_lock_is_free(db_path, busy_timeout=0.2)`。
- `test_db_txn_guard.py`：9 种事务写法 × delivered/queued 原生取消、× delivered anyio 取消；裸连接对照组；6 条 `connect` 行为；`drain` 五行 + 连续取消三次。
- `test_write_cancel_paths.py`：三条「取消后紧接真实收尾写库」用例；`exchange_store` 4 个与 `novel` 6 个参数。
- `test_write_cancel_paths_core.py`：`agent_store` 7 个、`database` 9 个、`trace` 1 个参数。
- `test_write_cancel_paths_misc.py`：`byok.store`、`song.store`、`studio.sources` 3 个参数；`_save_snapshot` 也完成。
- `test_db_txn_static.py`：AST 扫描 191 个非测试 `.py`，禁止 `aiosqlite.connect` / `from aiosqlite import connect`，要求每处 `db_txn.connect(` 都是 `async with` 上下文表达式，并做文件数/调用数防空转。

### 2.4 文档

- `docs/ARCHITECTURE.md` 在 `## FastAPI 后端` 下新增 `### 数据库连接与取消保护`（6 行）。
- `CLAUDE.md` 的 `## 工作约定` 新增一条。

## 3. 与规格第 5 节任务清单逐项对应

| 规格第 5 节 | 状态 | 对应实现/证据 |
|---|---|---|
| 1. 新增 `backend/utils/db_txn.py`（3.1） | 完成 | `connect` + `drain`；`test_db_txn_guard.py` 31 passed |
| 2. 全站替换（3.2） | 完成 | 148/148，21 文件；A1/A2 通过 |
| 3. `NovelBilling._drain` 改为委托（3.3） | 完成 | `backend/novel/billing.py`，`_drain` 函数体 `return await db_txn.drain(operation)` |
| 4. 新增 `backend/tests/cancel_sweep.py`（4.1） | 完成 | 602 行；第二批五个测试文件都使用它 |
| 5. 新增 `test_db_txn_guard.py`（4.2） | 完成 | 31 条，全部通过 |
| 6. 新增三个路径测试文件（4.3） | 完成 | 13 + 17 + 3 = 33 条，全部通过 |
| 7. 新增 `test_db_txn_static.py`（4.4） | 完成 | 5 条，全部通过 |
| 8. 文档（3.4） | 完成 | 两处文档 diff 纯新增 |
| 9. 实施报告 | 完成 | 本文件 |

### 3.1 规格 4.2 每条要求 → 测试函数名

| 4.2 要求 | 测试函数 |
|---|---|
| 9 种事务写法，delivered + queued，原生取消；逐点断言写锁空闲、任务以取消结束、数据为初始值或完整执行后的值 | `test_db_txn_connect_cancel_points_leave_no_lock[f1_begin_select_fetchone_update]` … `[f9_select_fetchone_update]`（9 个参数，每个参数内部跑 delivered 与 queued） |
| 9 种写法再用 `anyio.CancelScope` 取消扫 delivered | `test_db_txn_connect_anyio_cancel_points_leave_no_lock[f1_begin_select_fetchone_update]` … `[f9_select_fetchone_update]` |
| 裸 `aiosqlite.connect` 对照组，至少一个取消点写锁不空闲 | `test_bare_aiosqlite_control_group_can_hold_write_lock` |
| 作用域内抛普通异常：写入回滚、连接关闭、向外是原异常 | `test_connect_rolls_back_and_closes_on_plain_exception` |
| 作用域内无异常：与裸连接相同（已提交留下、未提交丢弃） | `test_connect_without_exception_matches_bare_connection` |
| 回滚自己抛 `sqlite3.OperationalError`：原异常仍抛出、连接关闭 | `test_connect_swallows_rollback_error_and_keeps_original_exception` |
| 回滚等待时再次被取消（anyio）：连接关闭、工作线程退出、写锁空闲 | `test_connect_closes_when_rollback_is_cancelled_again` |
| 参数透传：位置参数 `(path,)`、关键字 `{"uri": True, "timeout": 1.0}` | `test_connect_passes_arguments_through_unchanged` |
| `async with` 交出的对象就是 `aiosqlite.connect(...)` 返回的连接对象 | `test_connect_yields_the_connection_object_from_aiosqlite` |
| `drain` 表格第一行（未取消、正常返回） | `test_drain_returns_inner_result_when_not_cancelled` |
| `drain` 表格第二行（未取消、抛异常） | `test_drain_propagates_inner_exception_when_not_cancelled` |
| `drain` 表格第三行（内层任务自取消） | `test_drain_raises_cancelled_error_when_inner_task_cancels_itself` |
| `drain` 表格第四行（调用方取消、等内层结束后抛取消） | `test_drain_waits_for_inner_then_raises_when_caller_cancelled` |
| `drain` 表格第五行（调用方取消、内层普通异常 → `CancelledError.__cause__`） | `test_drain_waits_for_inner_error_then_raises_cancelled_with_cause` |
| 连续取消三次，内层只执行一遍 | `test_drain_three_consecutive_cancels_run_inner_once` |

### 3.2 规格 4.3 每个函数 → 文件、参数名、取消点数、行返回查询点

计数口径：取消点数 = `cancel_sweep` 为该参数扫到的记录数；「行返回查询点」= 取消落在「启动了一条在 prepare 数据下确实返回至少 1 行的 SELECT / UPDATE ... RETURNING」的 `execute` 调用上的点数。紧随其后的 `fetchone`/`fetchall` 单独算取消点并计入总数，不重复算作「查询」。所有参数都至少有一个行返回查询点（A5 的变异自查也证明每个参数都会变红）。

| 函数 | 文件与参数 | 取消点数 | 行返回查询点 |
|---|---|---:|---:|
| `exchange_store.load_running_exchange` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.load_running_exchange]` | 15 | 3 |
| `exchange_store.reserve_model_call` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.reserve_model_call]` | 14 | 3 |
| `exchange_store.finish_model_call` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.finish_model_call]` | 19 | 4 |
| `exchange_store.stop_and_discard_reserved_calls` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.stop_and_discard_reserved_calls]` | 12 | 2 |
| `novel.DbStepStore.append_usage` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.append_usage]` | 7 | 1 |
| `novel.DbStepStore.write_step` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.write_step]` | 7 | 1 |
| `novel.DbStepStore.commit_setup` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_setup]` | 8 | 1 |
| `novel.DbStepStore.save_plan` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.save_plan]` | 8 | 1 |
| `novel.DbStepStore.commit_chapter` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_chapter]` | 12 | 2 |
| `novel.runner._pause` | `test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.runner._pause]` | 10 | 2 |
| `agent_store.get_my_agent` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_my_agent]` | 9 | 2 |
| `agent_store.update_my_agent` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.update_my_agent]` | 13 | 3 |
| `agent_store.get_memory_snapshot` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_memory_snapshot]` | 12 | 3 |
| `agent_store.resolve_chat_conversation` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.resolve_chat_conversation]` | 12 | 3 |
| `agent_store.list_conversations` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.list_conversations]` | 15 | 4 |
| `agent_store.create_conversation` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.create_conversation]` | 13 | 3 |
| `agent_store.delete_conversation` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.delete_conversation]` | 17 | 2 |
| `database.save_message` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_message]` | 14 | 3 |
| `database.reserve_strawberries` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.reserve_strawberries]` | 7 | 1 |
| `database.refund_strawberries` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.refund_strawberries]` | 5 | 1 |
| `database.get_strawberry_balance`（开每日补草莓） | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.get_strawberry_balance]` | 7 | 1 |
| `database.save_match` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_match]` | 10 | 1 |
| `database.save_pending_match` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_pending_match]` | 10 | 1 |
| `database.upsert_user_state` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.upsert_user_state]` | 7 | 1 |
| `database.save_studio_notice` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_studio_notice]` | 59 | 11 |
| `database.update_time_tag_prefs` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.update_time_tag_prefs]` | 7 | 1 |
| `trace.log_event` | `test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[trace.log_event]` | 7 | 1 |
| `byok.store.save_config` | `test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[byok.store.save_config]` | 15 | 1 |
| `song.store.save_lyrics` | `test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[song.store.save_lyrics]` | 14 | 3 |
| `studio.sources._save_snapshot` | `test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[studio.sources._save_snapshot]` | 9 | 1 |
| **合计** |  | **374** | **67** |

补充：`paths-main` 的 `test_novel_cancel_then_cancel_novel_succeeds` 另扫描 `append_usage`、`write_step`、`_pause`，点数分别 7、7、10；`test_exchange_cancel_then_settlement_succeeds` 另扫描 `load_running_exchange`、`reserve_model_call`、`finish_model_call`，点数 15、14、19；`test_chat_conversation_check_cancel_then_refund_succeeds` 对 `resolve_chat_conversation` 的三种起始状态分别扫描 23、12、9 点。三条用例的每个取消点都在任务对象仍被引用时执行了真实收尾写库并通过。

## 4. 测试结果

### A1 没有直接打开连接的调用了

从仓库根执行：

```bash
grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | grep -v "^backend/utils/db_txn.py:" | wc -l
```

输出：

```text
0
```

同类命令（先确认扫描非空）：

```bash
grep -rn "db_txn\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | wc -l
```

输出：

```text
148
```

第一条命令整体退出码 0（`wc` 成功；上游第一个 `grep` 只命中被过滤的 `backend/utils/db_txn.py`，没有其它命中）；第二条退出码 0。

### A2 替换是纯机械的

从仓库根执行：

```bash
backend/.venv/bin/python docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py 19e4bd1
```

输出：

```text
CHECK_MECHANICAL files=21 replaced=148 base_sites=148 problems=0
```

退出码：0。

### A3 改动范围

`git status --porcelain` 原文：

```text
 M CLAUDE.md
 M backend/agent_store.py
 M backend/byok/store.py
 M backend/conversation_matcher.py
 M backend/database.py
 M backend/discuss/billing.py
 M backend/discuss/store.py
 M backend/exchange_store.py
 M backend/main.py
 M backend/manage_strawberries.py
 M backend/novel/billing.py
 M backend/novel/drafts.py
 M backend/novel/feedback.py
 M backend/novel/store_db.py
 M backend/routers/me.py
 M backend/routers/plaza.py
 M backend/scripts/fix_matches.py
 M backend/song/jobs.py
 M backend/song/media.py
 M backend/song/store.py
 M backend/studio/store.py
 M backend/trace.py
 M docs/ARCHITECTURE.md
?? backend/tests/cancel_sweep.py
?? backend/tests/test_db_txn_guard.py
?? backend/tests/test_db_txn_static.py
?? backend/tests/test_write_cancel_paths.py
?? backend/tests/test_write_cancel_paths_core.py
?? backend/tests/test_write_cancel_paths_misc.py
?? backend/utils/db_txn.py
?? docs/tasks/2026-11-15-write-txn-cancel-guard/
```

退出码：0。实现的 23 个修改路径和 8 个新增路径全部在第 6 节清单内；折叠的 `docs/tasks/.../` 是任务输入（见 1.2）。用 `--untracked-files=all` 展开后的原文见 1.2，范围自查末行 `SCOPE_OK`。

### A4 测试

第一条（五个新测试文件，从 `backend/`）：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
```

输出末两行：

```text
.....................................................................    [100%]
69 passed in 42.32s
```

退出码：0。0 跳过。

每个新测试文件的收集数（`--collect-only -q`，从 `backend/`）：

| 文件 | 收集数 |
|---|---:|
| `tests/test_db_txn_guard.py` | 31 |
| `tests/test_write_cancel_paths.py` | 13 |
| `tests/test_write_cancel_paths_core.py` | 17 |
| `tests/test_write_cancel_paths_misc.py` | 3 |
| `tests/test_db_txn_static.py` | 5 |
| 合计 | 69 |

全量收集（`--collect-only -q`）：`8621 tests collected in 7.92s`，退出码 0。即基线 8552 + 新增 69。

第二条（全量，从 `backend/`）：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider
```

输出末尾：

```text
=========================== short test summary info ============================
FAILED tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]
1 failed, 8620 passed, 47 warnings in 554.82s (0:09:14)
```

退出码：1。

失败的是规格「不做」里列出的既有偶发用例，未改动它。按规格单独复跑一次：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider "tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]"
```

输出：

```text
.                                                                        [100%]
1 passed in 0.05s
```

退出码：0。两次结果都记录在此；该用例不碰数据库，是既有时间时序问题。

### A5 新测试有区分力（按派单只做表格第一行自查）

1. 把 `backend/utils/db_txn.py` 复制到系统临时目录留底，记录修改前 SHA-256：
   `64af7490024afa2be22258185bcc75d6d295e1973f994a1d868e31555131472c`。
2. 只把退出时「有异常就回滚」的那一步临时去掉（保留关闭路径），从 `backend/` 跑三个路径测试文件：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider --tb=no tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py
```

输出末尾的失败清单（完整）：

```text
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF                                        [100%]
=========================== short test summary info ============================
FAILED tests/test_write_cancel_paths.py::test_novel_cancel_then_cancel_novel_succeeds
FAILED tests/test_write_cancel_paths.py::test_exchange_cancel_then_settlement_succeeds
FAILED tests/test_write_cancel_paths.py::test_chat_conversation_check_cancel_then_refund_succeeds
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.load_running_exchange]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.reserve_model_call]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.finish_model_call]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.stop_and_discard_reserved_calls]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.append_usage]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.write_step]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_setup]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.save_plan]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_chapter]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.runner._pause]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_my_agent]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.update_my_agent]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_memory_snapshot]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.resolve_chat_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.list_conversations]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.create_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.delete_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_message]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.reserve_strawberries]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.refund_strawberries]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.get_strawberry_balance]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_match]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_pending_match]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.upsert_user_state]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_studio_notice]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.update_time_tag_prefs]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[trace.log_event]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[byok.store.save_config]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[song.store.save_lyrics]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[studio.sources._save_snapshot]
33 failed in 35.24s
```

退出码：1。

**去掉回滚后没有变红的参数：无**。30 个参数化参数全部变红，三条收尾写库用例也全部变红。

3. 用留底文件覆盖回去，SHA-256 与修改前一致，然后重跑三个文件：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py
```

输出末两行：

```text
.................................                                        [100%]
33 passed in 21.49s
```

退出码：0。恢复后的 `backend/utils/db_txn.py` SHA-256 为 `64af7490024afa2be22258185bcc75d6d295e1973f994a1d868e31555131472c`，与留底一致。

其余变异行（回滚后再次取消不关闭、回滚异常不吞、`drain` 两行、静态扫描）由规格作者在门禁里做；执行方未改测试去迁就。

### A6 真实代码复现归零

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.py
```

输出末行：

```text
REAL_CODE_REPRO cancel_points=73 follow_up_failed=0
```

退出码：0。取消点数仍为 73。

### A7 新测试不依赖本机环境

- 五个新测试文件没有读 git 历史、没有 `subprocess`/`git` 调用、没有读仓库之外的文件、没有引用 `frontend/node_modules`。
- `test_db_txn_static.py` 扫描的根是从 `Path(__file__)` 推出的仓库内 `backend/`；`test_write_cancel_paths_misc.py` 只使用 conftest/用例设置的临时 `FIONA_STUDIO_DIR`，并在用例内创建自己的文件。
- 临时脚本和临时库都在系统临时目录，未留在仓库。
- 浅克隆副本（不带 `node_modules`）的实跑按规格由规格作者执行。

### A8 文档

`docs/ARCHITECTURE.md` 新增小节原文（6 行）：

```markdown
### 数据库连接与取消保护

- 后端打开数据库连接一律用 `utils.db_txn.connect`（`backend/utils/db_txn.py`），不要直接调 `aiosqlite.connect`。
- `utils.db_txn.connect` 在有异常离开 `async with` 时先回滚再关闭。被取消的写事务如果只关闭不回滚，未取完的游标会让连接继续占着写锁，紧随其后的收尾写库就会报 `database is locked`。
- 需要「调用方被取消也要跑完」的操作用 `utils.db_txn.drain` 包住，它会等操作结束再把取消交还调用方。
```

`CLAUDE.md`「## 工作约定」新增一条原文：

```markdown
- 后端代码不直接调 `aiosqlite.connect`，一律用 `utils.db_txn.connect`，有测试拦截。
```

## 5. 没做完的、与规格不一致的、需要人确认的地方

没有未完成的功能项；没有需要人确认的阻塞项。

需要说明的几点：

1. **A3 的 `git status` 包含任务输入文件。** `docs/tasks/2026-11-15-write-txn-cancel-guard/` 下的 `01-investigation.md`、`02-spec.md`、`03-dispatch.md`、`verify/*` 在开工前就是未跟踪文件，不是本次实现改动；实现改动本身严格在规格第 6 节清单内（范围自查 `SCOPE_OK`）。
2. **anyio 取消模式下任务不会以 `CancelledError` 结束。** 规格 4.1 已说明 anyio 的取消由 `CancelScope` 捕获、检查函数要放 shield 里；4.2 的「任务以 CancelledError 结束」在 anyio 这一组按 `point.cancelled`（即 `scope.cancelled_caught`）判定，其余断言不变；原生取消组仍严格要求任务以 `CancelledError` 结束。
3. **全量测试里的 1 个失败是规格「不做」列出的既有偶发用例。** `test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]` 在全量运行中失败、单独复跑通过；未改动该用例，两次结果都记在 A4。
4. **A5 只做了派单要求的第一行自查。** 其余变异行由规格作者在门禁执行；执行方没有通过放宽断言来规避失败。
5. 初始 `git status` 里那 17 个任务输入文件在本次工作中只被读取，没有被修改；没有执行任何 Git 写操作。

## 返修 R1

### R1 派出的 agent

| 步骤 | agent | 负责文件 | 结果 |
|---|---|---|---|
| 第一步 | sweep-fix | `backend/tests/cancel_sweep.py` | 完成 F1/F2/F3 扫描器修复；两个探针通过；四个测试文件 64 passed；未改测试与源码。 |
| 第二步 | guard-tests-fix | `backend/tests/test_db_txn_guard.py` | 完成 F3 有界等待与两条新用例；33 passed；变异自查 5 秒内失败；未改其它文件。 |

本轮没有返修轮（第二步在第一步完成后进行）。

### R1 改了哪些文件

- `backend/tests/cancel_sweep.py`：
  - F1：新增 `tracking` 计数；原生取消被吞时记录 `cancelled=False`、运行检查并继续扫下一个点；anyio 取消被吞时按「注入后是否还有目标任务的 aiosqlite 调用」判断是否为最后一次，非最后一次记录 `cancelled=False` 并继续。
  - F2：anyio 的检查函数移入宿主任务 `finally`，在被测协程抛出取消之后、`CancelScope` 退出之前，用 `anyio.CancelScope(shield=True)` 运行；`CancelPointContext.task` 为宿主任务；检查函数自己开的连接不计入目标协程调用数。
  - F3：新增 `ScanTimeout`、`_OPERATION_TIMEOUT_SECONDS = 60.0`、`_CANCEL_GRACE_SECONDS = 5.0`；`prepare()`、任务等待、检查函数、`write_lock_is_free` 都有上限。
  - 对外签名和 `CancelPoint` / `CancelPointContext` 字段保持不变。
- `backend/tests/test_db_txn_guard.py`：
  - 新增 `_WAIT_TIMEOUT_SECONDS = 5.0` 与 `_wait_event_or_fail`、`_wait_task_or_fail`、`_gather_or_fail`、`_bounded_or_fail`；`test_connect_closes_when_rollback_is_cancelled_again`、三条 drain 用例的所有事件等待/任务等待/gather 都有上限，超时转 `pytest.fail`。
  - 新增 `test_sweep_reports_swallowed_cancellation`、`test_bare_aiosqlite_anyio_control_group_can_hold_write_lock`。
  - 原有 `test_db_txn_connect_anyio_cancel_points_leave_no_lock` 的断言未改。
- `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`：仅在本节追加。

没有改 `backend/utils/db_txn.py`、三个 `test_write_cancel_paths*.py`、`test_db_txn_static.py`、21 个替换文件或既有测试。`cancel_sweep.py` 的对外用法未变，因此三个路径测试文件不需要改。R1 开始前/结束后的 SHA-256：

```text
cancel_sweep.py               700f538ce0b65765377942b45ce5887bbcaaa862a12673f5bec3a8cf81adc0a4 -> c40d898c84c55be4d40a42717d57226b6640cfdfbdebe1fa1061cddf9f7d24dd
test_db_txn_guard.py          46b58fb7da50d2973f7edb9ba1d81f97b5fa6e27911cd4dc32c4e4fd82e129f9 -> b9d481e7a3e3c5d77ab9ffb30d09d271f185c9c49d09e5a55026948e4ba696e4
test_write_cancel_paths.py    0d8ad5b87f061cb517628367766e47d926f7b0e6238e8c14321dddbe6508129b（未变）
test_write_cancel_paths_core.py feda434ad8baa93fdcd5bc5d726f348e9c9b0034812511a4871d990ee0966d69（未变）
test_write_cancel_paths_misc.py 3536b55d3c76f4fb4029b8da208e2d1ed64e5a7fd27a81477d8fc75bb63fe9b6（未变）
db_txn.py                     64af7490024afa2be22258185bcc75d6d295e1973f994a1d868e31555131472c（未变）
```

### R1 验收 1：两个探针

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/sweep_truncation_probe.py
```

输出：

```text
SWEEP_TRUNCATION records: [(1, 'execute BEGIN IMMEDIATE', True), (2, 'execute UPDATE t SET v = v + 1 WHERE id=1', False), (3, 'execute UPDATE t SET v = v + 1 WHERE id=1', True), (4, 'commit', True), (5, 'close', True)]
SWEEP_TRUNCATION all_cancelled_true: False | 被测协程一共有 5 次 aiosqlite 调用（含关闭），扫到 5 个
```

退出码：0。5 条记录，第 2 条 `cancelled=False`。

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/sweep_anyio_probe.py
```

输出：

```text
SWEEP_ANYIO 取消点: [(1, 'execute BEGIN IMMEDIATE'), (2, 'execute SELECT id, v FROM t '), (3, 'fetchone'), (4, 'execute UPDATE t SET v = v +'), (5, 'commit'), (6, 'close'), (7, 'execute BEGIN IMMEDIATE'), (8, 'rollback')]
SWEEP_ANYIO 辅助模块的检查（任务结束之后）写锁空闲: [True, False, False, True, True, True, True, True]
SWEEP_ANYIO 被测协程自己的 finally 里（屏蔽取消）写锁空闲: [True, False, False, True, True, True, True, True]
```

退出码：0。两行一致。

说明：这个探针现在有 8 条记录，而不是原来的 6 条。多出的第 7、8 条来自探针自己的 `victim` 在 `finally` 里调用 `write_lock_is_free`（一个 `BEGIN IMMEDIATE`、一个 `rollback`）。F1 要求「注入后继续数目标任务后面还有没有 aiosqlite 调用」，这些调用确实属于被测任务，所以被计入取消点；扫描器自身的 `check` 调用已用 `tracking=False` 排除。两条需要比较的写锁结果仍然逐项一致。这里如实记录；如果门禁额外要求该探针固定为 6 条，需要规格作者明确「探针自身 finally 里的检查调用是否算被测协程的取消点」。

### R1 验收 2：五个新测试文件

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
```

输出末两行：

```text
.......................................................................  [100%]
71 passed in 32.19s
```

退出码：0。0 跳过。

每个文件的收集数（`--collect-only -q`）：

```text
tests/test_db_txn_guard.py :: 33 tests collected
tests/test_write_cancel_paths.py :: 13 tests collected
tests/test_write_cancel_paths_core.py :: 17 tests collected
tests/test_write_cancel_paths_misc.py :: 3 tests collected
tests/test_db_txn_static.py :: 5 tests collected
```

合计 71 条（原 69 + R1 新增 2 条）。

### R1 验收 3：去掉回滚的自查（覆盖五个文件）

1. 把 `backend/utils/db_txn.py` 复制到系统临时目录留底，记录 SHA-256：
   `64af7490024afa2be22258185bcc75d6d295e1973f994a1d868e31555131472c`。
2. 只把退出时「有异常就回滚」的那一步临时去掉（把 `await db.rollback()` 换成 `pass`，保留关闭），从 `backend/` 用 180 秒硬上限跑五个文件：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=no tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
```

实测整个命令 53 秒结束，没有卡住；退出码 1。输出末尾：

```text
FFF.F.F....F...........FF........FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF.....  [100%]
=========================== short test summary info ============================
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f1_begin_select_fetchone_update]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f2_begin_async_with_select_update]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f3_begin_multi_select_open_cursor]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f5_update_select_commit]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f7_begin_update_returning]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_anyio_cancel_points_leave_no_lock[f3_begin_multi_select_open_cursor]
FAILED tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception
FAILED tests/test_db_txn_guard.py::test_connect_closes_when_rollback_is_cancelled_again
FAILED tests/test_write_cancel_paths.py::test_novel_cancel_then_cancel_novel_succeeds
FAILED tests/test_write_cancel_paths.py::test_exchange_cancel_then_settlement_succeeds
FAILED tests/test_write_cancel_paths.py::test_chat_conversation_check_cancel_then_refund_succeeds
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.load_running_exchange]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.reserve_model_call]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.finish_model_call]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.stop_and_discard_reserved_calls]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.append_usage]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.write_step]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_setup]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.save_plan]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_chapter]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.runner._pause]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_my_agent]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.update_my_agent]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_memory_snapshot]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.resolve_chat_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.list_conversations]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.create_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.delete_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_message]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.reserve_strawberries]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.refund_strawberries]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.get_strawberry_balance]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_match]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_pending_match]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.upsert_user_state]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_studio_notice]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.update_time_tag_prefs]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[trace.log_event]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[byok.store.save_config]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[song.store.save_lyrics]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[studio.sources._save_snapshot]
41 failed, 30 passed in 52.09s
```

其中：

- 要求的 `test_db_txn_connect_anyio_cancel_points_leave_no_lock[f3_begin_multi_select_open_cursor]` 确实失败。
- 三个 `test_write_cancel_paths*.py` 的 33 条（13 + 17 + 3）全部失败。
- 命令整体 53 秒结束，没有触发 180 秒硬上限。

3. 用留底文件覆盖回去，SHA-256 与修改前一致：
   `64af7490024afa2be22258185bcc75d6d295e1973f994a1d868e31555131472c`。
4. 恢复后重跑五个文件：

```text
71 passed in 32.19s
```

退出码 0。

### R1 验收 4：A1、A2、A6

A1：

```bash
grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | grep -v "^backend/utils/db_txn.py:" | wc -l
```

输出 `0`；`db_txn.connect(` 计数输出 `148`；两条命令退出码 0。与上一轮一致。

A2：

```bash
backend/.venv/bin/python docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py 19e4bd1
```

输出：

```text
CHECK_MECHANICAL files=21 replaced=148 base_sites=148 problems=0
```

退出码 0。

A6：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.py
```

输出末行：

```text
REAL_CODE_REPRO cancel_points=73 follow_up_failed=0
```

退出码 0。与上一轮一致。

### R1 验收 5：全量

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider
```

输出末尾：

```text
=========================== short test summary info ============================
FAILED tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]
1 failed, 8622 passed, 47 warnings in 572.29s (0:09:32)
```

退出码 1。只有规格「不做」列出的既有偶发用例失败，未改动它。按规格单独复跑：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider "tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]"
```

输出：

```text
.                                                                        [100%]
1 passed in 0.06s
```

退出码 0。全量收集数：`8623 tests collected`（基线 8552 + 新测试 71）。

### R1 未完成/需要确认

- 没有未完成项。
- `sweep_anyio_probe.py` 现在 8 条记录（6 条业务调用 + 探针自身 finally 的 2 次检查调用），两条写锁结果仍逐项一致；如果门禁要求固定 6 条，需要规格作者明确探针自身 finally 调用是否计入取消点（见验收 1 的说明）。
- R1 只改了 `cancel_sweep.py`、`test_db_txn_guard.py`，并在本报告追加本节；`db_txn.py` 与三个路径测试文件的 SHA-256 未变。没有执行 Git 写操作。

## 复核返修 R1

### 本轮派出的 agent

| agent | 负责文件 | 结果 |
|---|---|---|
| paths-main | `backend/tests/test_write_cancel_paths.py` | A：收尾写库异常/超时改为错误文字，三条用例整轮收集后统一断言；13 passed。 |
| guard | `backend/utils/db_txn.py`、`backend/tests/test_db_txn_guard.py` | A3/A4、D、E：异常接住转断言、`_wait_task_or_fail` 断言结局、普通异常写锁对照、`ensure_future` 与 Task/Future 用例；38 passed。 |
| static | `backend/tests/test_db_txn_static.py` | C：别名、`aiosqlite.core`、`getattr`、`Connection(...)` 扫描与临时源文件证明用例；7 passed。 |
| docs | `docs/ARCHITECTURE.md` | B：新小节原样挪到 `## FastAPI 后端` 末尾；diff 只有 6 行新增、0 删除。 |

四个 agent 并行，文件互不重叠；没有返修轮。

### 本轮改了哪些文件

- `backend/tests/test_write_cancel_paths.py`：新增 `_run_follow_up`，三个 follow-up 检查返回 `{"error", "value"}`；三条收尾用例收集全部不合格点后用一条断言报出，信息含函数名、k、label、错误文字或实际值。
- `backend/tests/test_db_txn_guard.py`：
  - 普通异常与回滚异常两条用例改为自己接住 `BaseException` 并断言是同一个原异常对象；失败信息带实际异常。
  - `_wait_task_or_fail` 改为断言任务正常结束且无异常，不再返回 `task.result()`。
  - 新增 `test_plain_exception_rollback_releases_lock_before_close`：多行游标 + UPDATE + 普通异常，持有异常对象时写锁空闲；裸连接对照写锁不空闲。
  - 新增四条 drain 用例覆盖已在运行的 Task 与 Future 的「正常返回」「调用方取消后等内层结束再抛取消」。
  - 其余等待/读表入口硬化，非断言异常转成带上下文的 `pytest.fail`。
- `backend/utils/db_txn.py`：`drain` 中 `asyncio.create_task(operation)` 改为 `asyncio.ensure_future(operation)`；除这一行外无改动。最终 SHA-256 `6ec8ae41a0222b408f3c5e9251501f0c88e0ac8adb357c1f8be88b5711c88459`（E 之前是 `64af7490...472c`，本轮按要求改为 `ensure_future` 后哈希必然变化）。
- `backend/tests/test_db_txn_static.py`：新增 aiosqlite 绑定名收集、`.connect`/`.core.connect` 属性引用、危险 import、`getattr(..., "connect")`、`Connection(...)` 构造检查；新增证明用例，在 `tmp_path` 临时源文件上逐行验证每种写法都被报出。
- `docs/ARCHITECTURE.md`：`### 数据库连接与取消保护` 整节原样移到 `## FastAPI 后端` 末尾、`## 主创与审稿协作` 之前。
- `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`：仅追加本节。

未改 `cancel_sweep.py`、`test_write_cancel_paths_core.py`、`test_write_cancel_paths_misc.py`、21 个替换文件、`CLAUDE.md`；未执行 Git 写操作。

### 验收 1：五个新测试文件

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
```

输出末两行：

```text
......                                                                   [100%]
78 passed in 36.45s
```

退出码 0，0 跳过。各文件收集数：

```text
tests/test_db_txn_guard.py :: 38 tests collected
tests/test_write_cancel_paths.py :: 13 tests collected
tests/test_write_cancel_paths_core.py :: 17 tests collected
tests/test_write_cancel_paths_misc.py :: 3 tests collected
tests/test_db_txn_static.py :: 7 tests collected
```

合计 78 条（原 71 + 本轮新增 7 条：guard 5 条、static 2 条）。

### 验收 2：变异一（去掉回滚，五个文件，`--tb=line -rf`）

先留底，记录 `backend/utils/db_txn.py` 的 SHA-256 `6ec8ae41a0222b408f3c5e9251501f0c88e0ac8adb357c1f8be88b5711c88459`；把 `await db.rollback()` 换成 `pass`，从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=line -rf tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
```

实测整个命令 65 秒结束，没有卡住；退出码 1，`42 failed, 36 passed in 64.76s`。

三条收尾用例均以 `AssertionError` 失败，失败信息里同时有取消点和 `database is locked`（下面路径已去掉本机前缀）：

```text
tests/test_write_cancel_paths.py:474: AssertionError: novel 取消后的收尾写库有不合格取消点：
  DbStepStore.append_usage 的取消点 k=2，调用标签 execute SELECT 1 FROM novels n JOIN users u ON u.username=n.username：收尾写库失败：OperationalError: database is locked
tests/test_write_cancel_paths.py:520: AssertionError: exchange 取消后的收尾写库有不合格取消点：
  exchange_store.load_running_exchange 的取消点 k=2，调用标签 execute SELECT * FROM agent_exchanges WHERE id = ? AND status = 'run：收尾写库失败：OperationalError: database is locked
tests/test_write_cancel_paths.py:554: AssertionError: chat 取消后的收尾退款有不合格取消点：
  agent_store.resolve_chat_conversation(state=default-missing) 的取消点 k=2，调用标签 execute SELECT COUNT(*) FROM users WHERE username IN (?)：收尾写库失败：OperationalError: database is locked
```

一次断言分别汇总了 novel 3 个、exchange 10 个、chat 9 个不合格点，证明后续取消点和后续函数都继续扫描了。

三个路径文件共 33 条（13 + 17 + 3）全部失败。失败摘要共 42 条 `FAILED`，其中 `FAILED tests/test_write_cancel_paths*` 恰好 33 条；摘要条目中带 `- sqlite3.OperationalError` 或 `- TimeoutError` 后缀的为 0 条（`SUMMARY_TYPED=0`）。原始摘要块：

```text
=========================== short test summary info ============================
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f1_begin_select_fetchone_update]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f2_begin_async_with_select_update]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f3_begin_multi_select_open_cursor]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f5_update_select_commit]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_cancel_points_leave_no_lock[f7_begin_update_returning]
FAILED tests/test_db_txn_guard.py::test_db_txn_connect_anyio_cancel_points_leave_no_lock[f3_begin_multi_select_open_cursor]
FAILED tests/test_db_txn_guard.py::test_plain_exception_rollback_releases_lock_before_close
FAILED tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception
FAILED tests/test_db_txn_guard.py::test_connect_closes_when_rollback_is_cancelled_again
FAILED tests/test_write_cancel_paths.py::test_novel_cancel_then_cancel_novel_succeeds
FAILED tests/test_write_cancel_paths.py::test_exchange_cancel_then_settlement_succeeds
FAILED tests/test_write_cancel_paths.py::test_chat_conversation_check_cancel_then_refund_succeeds
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.load_running_exchange]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.reserve_model_call]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.finish_model_call]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[exchange_store.stop_and_discard_reserved_calls]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.append_usage]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.write_step]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_setup]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.save_plan]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.DbStepStore.commit_chapter]
FAILED tests/test_write_cancel_paths.py::test_cancelled_write_leaves_no_lock[novel.runner._pause]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_my_agent]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.update_my_agent]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.get_memory_snapshot]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.resolve_chat_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.list_conversations]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.create_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[agent_store.delete_conversation]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_message]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.reserve_strawberries]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.refund_strawberries]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.get_strawberry_balance]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_match]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_pending_match]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.upsert_user_state]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.save_studio_notice]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[database.update_time_tag_prefs]
FAILED tests/test_write_cancel_paths_core.py::test_cancelled_write_leaves_no_lock[trace.log_event]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[byok.store.save_config]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[song.store.save_lyrics]
FAILED tests/test_write_cancel_paths_misc.py::test_cancelled_write_leaves_no_lock[studio.sources._save_snapshot]
42 failed, 36 passed in 64.76s (0:01:04)
```

补充说明：guard 的「回滚等待时再次被取消」用例在超时路径的 traceback 里会显示一条被链式引用的 `E TimeoutError` 原因，但该用例的 `path:line` 失败条目是 `Failed: db_txn.connect 没有调用 rollback...`，不是以 `TimeoutError` 开头的失败条目；三条收尾用例的 `path:line` 条目均为 `AssertionError`。

用留底覆盖后，`backend/utils/db_txn.py` 的 SHA-256 与留底一致：`6ec8ae41a0222b408f3c5e9251501f0c88e0ac8adb357c1f8be88b5711c88459`。

### 验收 3：变异二（回滚异常不吞）

先留底，把 `contextlib.suppress(Exception)` 换成 `contextlib.suppress()`，从 `backend/` 跑：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider --tb=line -rf tests/test_db_txn_guard.py
```

输出末尾：

```text
tests/test_db_txn_guard.py:657: AssertionError: 向外抛的应是原异常对象，实际是 OperationalError: OperationalError('rollback failed')
FAILED tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception
1 failed, 37 passed in 4.26s
```

退出码 1；要求的那条用例以 `AssertionError` 失败。留底覆盖后哈希仍为 `6ec8ae41a0222b408f3c5e9251501f0c88e0ac8adb357c1f8be88b5711c88459`。

### 验收 4：变异三（只在 CancelledError 时回滚）

先留底，把 `connect` 的异常分支改成 `if isinstance(error, asyncio.CancelledError):` 才回滚，再跑：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider --tb=line -rf tests/test_db_txn_guard.py
```

输出末尾：

```text
tests/test_db_txn_guard.py:567: AssertionError: db_txn.connect 在普通异常后、异常对象仍被引用时写锁不空闲
FAILED tests/test_db_txn_guard.py::test_plain_exception_rollback_releases_lock_before_close
...
3 failed, 35 passed in 9.00s
```

退出码 1；新增的 D 用例以断言失败（写锁不空闲）报出。留底覆盖后哈希仍为 `6ec8ae41a0222b408f3c5e9251501f0c88e0ac8adb357c1f8be88b5711c88459`。

### 验收 5：静态守卫新用例与手工探针

目标文件：

```text
7 passed in 0.98s
```

退出码 0。随后在 `backend/` 临时放一个只含以下内容的 `.py` 文件：

```python
import aiosqlite as aio


aio.connect("manual.db")
```

跑 `tests/test_db_txn_static.py`，退出码 1，输出关键行（已去掉本机前缀）：

```text
E       AssertionError: 除 backend/utils/db_txn.py 外，后端代码只能通过 utils.db_txn.connect(...) 打开连接；不得使用 aiosqlite 导入别名、aiosqlite.core、getattr(..., "connect")、间接引用 connect，也不得直接构造 Connection(...)。共 1 处违规：
E           [connect-attribute] backend/_tmp_r2_alias_probe.py:4:1  aio.connect("manual.db")
FAILED tests/test_db_txn_static.py::test_no_aiosqlite_aliases_or_indirect_connection_openings
```

删除临时文件后重跑：

```text
7 passed in 0.98s
```

退出码 0；`git status` 中没有该探针文件残留。扫描计数仍为 191 个文件、148 处 `db_txn.connect(`。

### 验收 6：A1、A2、A6

A1：

```bash
grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | grep -v "^backend/utils/db_txn.py:" | wc -l
```

输出 `0`；`db_txn.connect(` 计数输出 `148`；两条命令退出码 0。

A2：

```bash
backend/.venv/bin/python docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py 19e4bd1
```

输出：

```text
CHECK_MECHANICAL files=21 replaced=148 base_sites=148 problems=0
```

退出码 0。

A6：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.py
```

输出末行：

```text
REAL_CODE_REPRO cancel_points=73 follow_up_failed=0
```

退出码 0。

### 验收 7：ARCHITECTURE 文档位置

```bash
git diff --numstat 19e4bd1 -- docs/ARCHITECTURE.md
```

输出：

```text
6       0       docs/ARCHITECTURE.md
```

退出码 0；`git diff -U0` 中删除行数为 0。`grep -n -E "^#{1,4} " docs/ARCHITECTURE.md` 在 `## FastAPI 后端` 到 `## 主创与审稿协作` 之间：

```text
156:## FastAPI 后端
243:### 数据库连接与取消保护
249:## 主创与审稿协作
```

新小节标题到下一个标题之间为 6 行，不超过 15 行；`## FastAPI 后端` 后面恢复为原有导语。

### 验收 8：全量

从 `backend/` 执行：

```bash
NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local .venv/bin/python -m pytest -q -p no:cacheprovider
```

输出末行：

```text
8630 passed, 47 warnings in 566.26s (0:09:26)
```

退出码 0，0 失败，0 跳过；全量收集数 `8630 tests collected`（基线 8552 + 新测试 78）。本轮全量没有触发那条既有偶发用例，因此不需要复跑。

### 未完成/需要人确认

- 没有未完成项。
- `backend/utils/db_txn.py` 的最终哈希是 E 之后的 `6ec8ae41...c88459`；上一轮的 `64af7490...472c` 是 E 之前的值。本轮所有变异都用最终版本留底并恢复到 `6ec8ae41...c88459`，没有回退 E。
- 变异一里 guard 的「回滚等待时再次被取消」用例会显示链式 `TimeoutError` 原因（见验收 2 的说明）；三条收尾用例的失败条目和 42 条失败摘要均不是以 `sqlite3.OperationalError` / `TimeoutError` 开头的类型条目。如果门禁要求整段 traceback 里也不能出现 `E TimeoutError`，需要再调整该用例的超时断言写法。
- `test_write_cancel_paths_core.py`、`test_write_cancel_paths_misc.py` 本轮未改；它们在变异一里仍以 `AssertionError` 失败（已计入 33 条）。
