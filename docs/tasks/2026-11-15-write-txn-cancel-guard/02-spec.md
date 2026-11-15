# 写库取消保护 · 规格

版本 v1.0（作者 2026-11-15 确认）。基线 main `19e4bd1`，工作分支 `fix/write-txn-cancel-guard`。

等级 L3：跨 21 个后端文件，涉及计费路径。

调查与证据见同目录 `01-investigation.md`；本规格自包含，执行方不需要读调查记录也能开工。

## 0. 作者已确认的三件事

2026-11-15 作者看过 v0.1 后回复「确认，派单」，下面三项都按推荐定了：

1. **范围**：在「打开连接」这一层统一加保护，全站 148 处调用点做纯文本替换。没有选的两个方案是只修书斋、分身交流、自带 Claude 的聊天这几处，以及全站改成受保护任务。理由见 `01-investigation.md` 第 7.2 节。
2. **顺手修 `NovelBilling._drain` 丢取消**：调用方已被取消、内层又抛普通异常时，改为把取消交还调用方。书斋和讨论群都用它。
3. **把「后端开数据库连接一律走新封装」写进 `CLAUDE.md` 和 `docs/ARCHITECTURE.md`**，并加一条测试拦住以后直接开连接的写法。

## 1. 目标

### 要解决的问题

写事务被取消后，已经关闭的连接可能继续占着数据库写锁，直到取消异常被销毁。紧跟在取消之后的收尾写库等满 5 秒后报 `database is locked`，期间全站其他写入也被挡。

用户会遇到的情形（都已在 main 的代码上复现，见第 2 节）：

- 作者暂停、删除或改稿一本正在写的书，偶发卡 5 秒后报错，预扣的草莓没退，这本书的运行令牌没清。
- 停止一场分身交流，结算失败，预留的模型调用没有释放。
- 自带 Claude 的用户在回复刚开始时关掉页面，这条回复预扣的草莓退不回去。

### 做完之后

- 任何写事务在任何位置被取消，都不残留写锁。
- 取消不会被吞掉。
- 既有行为不变：不改任何 SQL，不改事务边界，不改任何既有测试。

### 不做

- 不把现有的写事务改成「包成函数交给受保护任务」的写法。已经这样写的（书斋和讨论群的计费、讨论群的 `run_write`）保持原样。
- 不处理「取消落在提交上」：这时数据已提交、调用方收到的是取消。这是现状，本次不变。
- 不动同步的 `sqlite3.connect`（`intent_router.py`、`mode_switcher.py`、`migrate.py`、`analyze.py`、`studio/store.py` 一处、`scripts/` 下一处）。它们在线程里一口气跑完，没有这个问题。
- 不修 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]`。它在机器忙时偶发失败，不碰数据库，是既有的时序问题。

## 2. 现状事实

以下都是在 `19e4bd1` 上实测的，脚本和输出在 `verify/`。

**机制。** 连接关闭时如果同时有（a）没提交也没回滚的写事务，（b）一个活着的游标握着没取完的取行语句（`SELECT` 或带 `RETURNING` 的写语句，且至少返回了一行），关闭就不生效，写锁一直挂到那个游标被销毁。关闭之前只要回滚过，就不残留，即使游标还活着。

**取消怎样留下这种游标。** aiosqlite 在工作线程里执行语句，结果交回事件循环后，等待它的任务要到下一轮事件循环才醒。`task.cancel()` 恰好落在这一轮里，任务醒来拿到的是 `CancelledError`，装着游标的结果没人取、没人关，被取消异常的调用栈一直引用着。写成 `async with db.execute(...) as cursor` 也挡不住。

**锁挂多久。** 取消异常活多久就挂多久：任务自己的 `finally` 里；`await gather(task, return_exceptions=True)` 之后只要任务对象还被引用（局部变量、任务登记表）。

**谁会取消。** 普通接口在客户端断开后照常跑完，不取消。流式接口断开会取消，但那是经 anyio 投递的，anyio 会避开上面那个窗口。真正暴露的是用 `task.cancel()` 取消的后台任务和聊天流里的子任务。

**代码现状。**

- 非测试代码里 `aiosqlite.connect(` 共 148 处，分布在 21 个文件，全部写成 `async with aiosqlite.connect(...) as db:`，没有 `db = await aiosqlite.connect(...)` 的写法。
- 这 21 个文件都有一行顶格或缩进的 `import aiosqlite`。
- `novel/store_db.py` 的 `get_db`、`discuss/store.py` 的 `get_db`、`studio/store.py` 的 `connection` 三个封装内部也调 `aiosqlite.connect(`，已计入 148。
- `novel/billing.py` 的 `NovelBilling._drain`（静态方法）被 `novel/billing.py`、`novel/llm_router.py`、`discuss/` 下多处调用。实测：调用方被取消、内层抛 `ValueError` 时，调用方收到的是 `ValueError`，任务的 `cancelled()` 为假。
- 既有测试对连接的打桩方式（替换时必须保持它们可用）：
  - `tests/test_exchange_poll_connection.py`、`tests/test_health_and_startup.py`、`tests/test_studio_brain_eval.py` 替换 `aiosqlite.connect` 本身，其中两处是经 `exchange_store.aiosqlite`、`main.aiosqlite` 访问的，一处断言调用形状是 `connect(path, **kwargs)`、`kwargs` 里有 `uri` 和 `timeout`，一处断言返回的连接对象关闭后 `_connection is None`。
  - `tests/test_novel_p1_runner.py`、`tests/test_discuss_runner.py`、`tests/test_studio_breakdown_r1_pipeline.py` 替换的是模块级封装（`runner.get_db`、`discuss.store.get_db`、`studio.store.connection`）。
  - `tests/test_discuss_runner.py` 还替换 `aiosqlite.Connection._execute`，并在连接对象上改写 `_execute`、`commit`。

**在真实代码上的复现。** `verify/real_code_repro.py` 对 6 个写函数做取消点扫描（取消落在每一次 aiosqlite 调用的「结果已交回、任务未唤醒」），然后在任务对象仍被引用时执行真实代码里紧跟着的那一步收尾写库：

| 被取消的写函数 | 之后的收尾写库 | 取消点 | 收尾报 `database is locked` |
|---|---|---|---|
| `DbStepStore.append_usage` | `NovelBilling.refund_reserved` | 7 | 1 |
| `exchange_store.reserve_model_call` | `stop_and_discard_reserved_calls` | 10 | 1 |
| `agent_store.resolve_chat_conversation` | `database.refund_strawberries` | 22 | 4 |
| `agent_store.get_memory_snapshot` | `database.refund_strawberries` | 12 | 3 |
| `database.save_message` | `database.refund_strawberries` | 15 | 3 |
| `trace.log_event` | `database.refund_strawberries` | 7 | 1 |
| 合计 | | 73 | 13 |

**原型验证。** 在 `19e4bd1` 的副本里按本规格第 3 节做了原型（只用于验证可行，不是交付物）：

- `verify/real_code_repro.py`：同样 73 个取消点，失败 0 处。把原型里「回滚」那一步去掉再跑，回到 13 处失败。
- `verify/check_mechanical.py`：`files=21 replaced=148 base_sites=148 problems=0`；往其中一个文件末尾多加一行注释后，报出 1 个不合格项。
- 全量测试：8552 条全部通过，0 失败，0 跳过，既有测试一个字没改。
- `_drain`：调用方被取消、内层抛 `ValueError` 时，调用方收到 `CancelledError`，`__cause__` 是那个 `ValueError`。

**测试基线。** `19e4bd1` 上从 `backend/` 运行 `.venv/bin/python -m pytest -q -p no:cacheprovider`：共 8552 条，0 跳过。当天跑了三次全量（基线一次、原型两次），其中两次是 8551 通过、1 失败，失败的都是「不做」里列的那条偶发用例；它单独复跑 5 次、所在文件单独跑 3 次都通过。

## 3. 方案

### 3.1 新增 `backend/utils/db_txn.py`

提供两个东西。

**`connect(*args, **kwargs)`**：用法和 `aiosqlite.connect(...)` 的 `async with` 形式完全一样，多一条规则——有异常离开作用域时，先回滚，再关闭。

行为要求：

1. 参数原样透传：内部调用就是 `aiosqlite.connect(*args, **kwargs)`，不加、不改、不重排任何参数。
2. 调用 `aiosqlite.connect` 时必须在调用那一刻经 `aiosqlite` 模块的属性取到它（即写 `aiosqlite.connect(...)`，不要在模块加载时把它存进别的名字）。既有测试会替换这个属性。
3. `async with db_txn.connect(...) as db` 里拿到的 `db`，就是 `aiosqlite.connect(...)` 给出的那个连接对象本身，不包一层、不换类型。
4. 作用域内没有异常：退出时只做原来的关闭，不额外提交或回滚。
5. 作用域内有异常离开（包括 `asyncio.CancelledError`、`GeneratorExit`）：先 `await db.rollback()`，再做原来的关闭，原异常照常向外传播。
6. 回滚这一步自己抛出普通异常（`Exception` 的子类）：吞掉，仍然关闭，向外传播的仍是原异常。
7. 回滚这一步等待时任务再次被取消：仍然要执行关闭（关闭必须被送进 aiosqlite 的工作队列），不能因为这次取消而跳过。
8. 只支持 `async with` 形式。不需要支持 `db = await db_txn.connect(...)`。

**`drain(operation)`**：等一个受保护的操作跑完，再把调用方收到的取消交还。`operation` 是一个协程或可等待对象；`drain` 把它放进独立任务并屏蔽调用方的取消。

| 调用方 | 内层操作 | `drain` 的结果 |
|---|---|---|
| 没被取消 | 正常返回 | 返回同一个值 |
| 没被取消 | 抛异常 | 原样抛出同一个异常 |
| 没被取消 | 内层任务自己被取消 | 抛 `CancelledError` |
| 等待期间被取消一次或多次 | 正常返回 | 等内层跑完之后抛 `CancelledError`；内层已经做完的事（比如已提交）保留 |
| 等待期间被取消一次或多次 | 抛普通异常 | 等内层结束之后抛 `CancelledError`，它的 `__cause__` 是内层那个异常 |

最后一行是本次的修正；其余四行与现在的 `NovelBilling._drain` 相同。任何情况下，`drain` 返回或抛出之前内层任务都已经结束。

### 3.2 全站替换打开连接的调用

把非测试代码里所有 `aiosqlite.connect(` 换成 `db_txn.connect(`，括号里的参数一个字符都不动。每个被改的文件在它第一处 `import aiosqlite` 的下一行、用相同缩进加一行 `from utils import db_txn`。

- 调用点由搜索得出，不以本规格的数字为准：`grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests`。在 `19e4bd1` 上是 148 处、21 个文件；如果你搜到的不是这个数，照搜到的全部替换，并在实施报告里写明差异。
- 原有的 `import aiosqlite` 一律保留。文件里对 `aiosqlite.Row`、`aiosqlite.Connection` 等的其他引用不动。
- 有三个文件的 `import aiosqlite` 写在函数里面（`manage_strawberries.py`、`routers/me.py`、`routers/plaza.py`），新加的导入跟着放在同一个函数里。无论哪个文件，都要保证每一处 `db_txn.connect(` 执行时能取到 `db_txn` 这个名字。
- 除了「换调用名」和「加一行导入」，这些文件不得有任何其他改动，包括空白和注释。门禁会逐字节核对（第 7 节 A2）。
- `backend/utils/db_txn.py` 自己内部调 `aiosqlite.connect(`，不在替换范围内。

### 3.3 `NovelBilling._drain` 改为委托

`backend/novel/billing.py` 里 `_drain` 保留名字、保留 `@staticmethod`、保留签名，函数体改成 `return await db_txn.drain(operation)`，文档字符串可保留或缩短。这个文件除 3.2 的替换和这一处之外不得有其他改动。

### 3.4 文档

- `docs/ARCHITECTURE.md`：新增一小节（不超过 15 行），写明三点：后端打开数据库连接一律用 `utils.db_txn.connect`；它在有异常离开时先回滚再关闭，以及为什么（一两句话说清被取消的写事务会残留写锁）；需要「调用方被取消也要跑完」的操作用 `utils.db_txn.drain` 包住。
- `CLAUDE.md`：在「工作约定」一节加一条，一句话：后端代码不直接调 `aiosqlite.connect`，一律用 `utils.db_txn.connect`，有测试拦截。
- 全库搜索文档里是否还有别处写着「用 `aiosqlite.connect` 打开连接」之类的说法（`docs/tasks/` 下的历史任务记录不算），有就一并改成新说法。

### 3.5 技术约束

- 不新增任何依赖。
- 不改任何 SQL 文本、不改事务边界、不改任何函数的签名和返回值。
- 不重构、不顺手整理被改文件里的其他代码。
- 既有测试、`conftest.py`、`_fakes.py` 一个字都不许改。新测试只放进新文件。

## 4. 新增测试

### 4.1 测试辅助：`backend/tests/cancel_sweep.py`

提供「取消点扫描」，供下面两个测试文件使用。可以参照 `verify/mechanism_probe.py` 和 `verify/real_code_repro.py` 里的注入器来写（那两个文件不能被测试直接导入，要在 `tests/` 里重写）。

要求：

- 给定一个「造出被测协程」的函数，对 k = 1、2、3……逐个取消点运行：新建任务执行被测协程，把取消落在该任务的第 k 次 aiosqlite 调用上，用 `await asyncio.gather(task, return_exceptions=True)` 等它结束；然后**在任务对象仍被引用的状态下**调用调用方给的检查函数；直到某个 k 上取消没有触发（被测协程自然跑完）为止。
- 两种落点都要支持：
  - 「结果已交回」：该次调用的结果已经写进 Future、任务还没被唤醒时调用 `task.cancel()`。做法是替换 `aiosqlite.core.set_result`，在它把结果写进 Future 之后立刻取消。
  - 「还在排队」：该次调用刚入队、还没有结果时取消。
- 支持每个取消点之前先运行一个准备函数（用来把数据恢复成初始状态），准备函数里的数据库调用不计入取消点。
- 返回每个取消点的记录：序号、调用标签（方法名加 SQL 的开头一段）、任务是否以 `CancelledError` 结束、检查函数的结果。
- 对 `aiosqlite.core` 的替换必须在扫描结束后还原（用 `monkeypatch` 或 `try/finally`），不得影响其他用例。
- 一个取消点都没扫到时要报错，而不是返回空列表让断言空转。
- 支持用 `anyio.CancelScope` 取消（4.2 要用）。anyio 的取消会在任务每次等待时重新送达，所以这种模式下检查函数要放在 `anyio.CancelScope(shield=True)` 里运行；每个取消点都要记录检查函数是否真的跑完，没跑完算失败，不能当成通过。
- 另提供一个「写锁是否空闲」的检查：新开一条忙等待 0.2 秒的连接执行 `BEGIN IMMEDIATE`，成功则回滚并返回真。

### 4.2 `backend/tests/test_db_txn_guard.py`

对 `utils/db_txn.py` 本身的测试，用临时库和自建的小表，不依赖业务代码。

`connect`（以下 9 种事务写法各扫一遍，「结果已交回」「还在排队」两种落点，原生取消；另用 `anyio.CancelScope` 取消扫一遍「结果已交回」）：

1. `BEGIN IMMEDIATE`；`cursor = await db.execute(单行 SELECT)`；`fetchone`；`UPDATE`；`commit`
2. 同上，查询写成 `async with db.execute(...) as cursor`
3. `BEGIN IMMEDIATE`；`cursor = await db.execute(多行 SELECT)`；只 `fetchone`、不关游标；`UPDATE`；`commit`
4. `BEGIN IMMEDIATE`；两条 `UPDATE`；`commit`
5. 不写 `BEGIN`：`UPDATE`；`SELECT`；`commit`
6. 只有 `SELECT`
7. `BEGIN IMMEDIATE`；`UPDATE ... RETURNING`；`fetchone`；`commit`
8. `BEGIN IMMEDIATE`；`execute_fetchall(SELECT)`；`UPDATE`；`commit`
9. `SELECT`；`fetchone`；`UPDATE`；`commit`

每个取消点上断言：任务对象仍被引用时写锁空闲；任务以 `CancelledError` 结束；表里的数据要么和事务开始前一样、要么和事务完整执行后一样。

同一批写法再用裸的 `aiosqlite.connect` 跑一遍作对照，断言**至少有一个**取消点上写锁不空闲。这条对照证明扫描器真的能测出问题；没有它，上面那组断言可能在什么都没测到的情况下通过。

`connect` 的其余行为，各一条用例：

- 作用域内抛普通异常：已执行的写入被回滚，连接已关闭，向外抛的是原异常。
- 作用域内无异常：行为与裸的 `aiosqlite.connect` 相同（已提交的留下，没提交的丢弃）。
- 回滚自己抛普通异常（把连接的 `rollback` 换成会抛 `sqlite3.OperationalError` 的函数）：向外抛的仍是原异常，连接已关闭。
- 回滚等待时再次被取消（用 `anyio.CancelScope` 取消，它会在每次等待时重新送达）：连接最终被关闭（连接对象的 `_connection is None`，工作线程已退出），写锁空闲。
- 参数透传：替换 `aiosqlite.connect` 为记录参数的函数，`db_txn.connect(path, uri=True, timeout=1.0)` 记录到的是位置参数 `(path,)` 和关键字 `{"uri": True, "timeout": 1.0}`。
- `async with` 交出的对象就是 `aiosqlite.connect(...)` 返回的那个连接对象。

`drain`：3.1 表格的五行各一条用例。第四、五行要断言 `drain` 抛出时内层任务已经结束；第五行要断言 `__cause__` 是内层异常。再加一条：等待期间被连续取消三次，内层只执行一遍，最终抛 `CancelledError`。

### 4.3 真实路径上的用例（三个文件）

在真实业务函数上做取消点扫描（落点「结果已交回」，原生取消）。用例名必须用下面给的名字，门禁要按名字核对。

为了能并行写，这一节的用例分放三个文件，各文件自带需要的准备数据：

| 文件 | 内容 |
|---|---|
| `backend/tests/test_write_cancel_paths.py` | 下面三条「取消之后紧跟着真实的收尾写库」的用例；参数化用例里 `exchange_store` 与 `novel` 两行的函数 |
| `backend/tests/test_write_cancel_paths_core.py` | 参数化用例里 `agent_store`、`database`、`trace` 三行的函数 |
| `backend/tests/test_write_cancel_paths_misc.py` | 参数化用例里 `byok.store`、`song.store`、`studio.sources` 三行的函数 |

三条「取消之后紧跟着真实的收尾写库」的用例：

- `test_novel_cancel_then_cancel_novel_succeeds`：对 `DbStepStore.append_usage`、`DbStepStore.write_step`、`novel.runner._pause` 分别扫描。每个取消点之后，在任务对象仍被引用时执行 `await novel.runner.cancel_novel(novel_id, username)`，要求不抛异常、2 秒内返回、这本书的 `run_token` 已为空。
- `test_exchange_cancel_then_settlement_succeeds`：对 `exchange_store.load_running_exchange`、`reserve_model_call`、`finish_model_call` 分别扫描。每个取消点之后执行 `await exchange_store.stop_and_discard_reserved_calls(...)`，要求不抛异常、2 秒内返回，这场交流不再有 `status='reserved'` 的调用行。
- `test_chat_conversation_check_cancel_then_refund_succeeds`：对 `agent_store.resolve_chat_conversation` 扫描（默认会话还不存在、已存在、指定会话三种起始状态）。每个取消点之后执行 `await database.refund_strawberries(username, 1)`，要求不抛异常、2 秒内返回，余额比之前多 1。

一组参数化用例 `test_cancelled_write_leaves_no_lock[<函数名>]`（三个文件里都叫这个名字，参数各管各的），覆盖下面每个函数。每个取消点上断言：任务对象仍被引用时写锁空闲；任务以 `CancelledError` 结束。

| 模块 | 函数 |
|---|---|
| `agent_store` | `get_my_agent`、`update_my_agent`、`get_memory_snapshot`、`resolve_chat_conversation`、`list_conversations`、`create_conversation`、`delete_conversation` |
| `database` | `save_message`、`reserve_strawberries`、`refund_strawberries`、`get_strawberry_balance`（开着每日补草莓）、`save_match`、`save_pending_match`、`upsert_user_state`、`save_studio_notice`、`update_time_tag_prefs` |
| `trace` | `log_event` |
| `exchange_store` | `load_running_exchange`、`reserve_model_call`、`finish_model_call`、`stop_and_discard_reserved_calls` |
| `novel` | `DbStepStore.append_usage`、`write_step`、`commit_setup`、`save_plan`、`commit_chapter`；`runner._pause` |
| `byok.store` | `save_config` |
| `song.store` | `save_lyrics` |
| `studio.sources` | `_save_snapshot` |

对每个函数，准备的数据必须让它的写事务里**至少有一条查询返回了行**（否则这条用例测不出任何东西）。门禁会用第 7 节 A5 的做法核对这一点。

这三个文件里的用例把 `database.SQLITE_BUSY_TIMEOUT` 用 `monkeypatch` 调成 0.3 秒。业务函数都是在调用那一刻读这个值的；调小之后，一旦写锁残留，收尾写库 0.3 秒就报错，不用每个取消点干等 5 秒。

如果表里某个函数的准备数据确实造不出来（比如依赖过多的外部状态），停下来说明是哪个、卡在哪里，不要悄悄跳过或换成别的函数。唯一的例外是 `studio.sources._save_snapshot`：它的准备数据最重，可以参照 `tests/test_studio_sources.py` 的做法另写一份；实在做不出来就不做这一个，在实施报告里写明原因，不必停。

### 4.4 `backend/tests/test_db_txn_static.py`

用语法树扫描 `backend/` 下全部非测试 `.py` 文件（排除 `.venv`、`tests`、`__pycache__`、`uploads`）：

- 除 `backend/utils/db_txn.py` 外，不得出现对 `aiosqlite.connect` 的调用，也不得出现 `from aiosqlite import connect`。
- 每一处 `db_txn.connect(...)` 都必须是某个 `async with` 的上下文表达式。
- 防空转：断言扫到的文件数不少于 100，`db_txn.connect(` 的调用数不少于 140。

失败信息要列出文件和行号。

## 5. 执行方任务清单

1. 新增 `backend/utils/db_txn.py`（3.1）。
2. 全站替换（3.2）。
3. `NovelBilling._drain` 改为委托（3.3）。
4. 新增 `backend/tests/cancel_sweep.py`（4.1）。
5. 新增 `backend/tests/test_db_txn_guard.py`（4.2）。
6. 新增 `backend/tests/test_write_cancel_paths.py`、`test_write_cancel_paths_core.py`、`test_write_cancel_paths_misc.py`（4.3）。
7. 新增 `backend/tests/test_db_txn_static.py`（4.4）。
8. 文档（3.4）。
9. 写实施报告 `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`：修改了哪些文件、实现了什么、与本清单逐项对应、测试结果（命令与输出末行）、没做完或需要人确认的地方。

## 6. 允许改动的文件

新增：

- `backend/utils/db_txn.py`
- `backend/tests/cancel_sweep.py`
- `backend/tests/test_db_txn_guard.py`
- `backend/tests/test_write_cancel_paths.py`
- `backend/tests/test_write_cancel_paths_core.py`
- `backend/tests/test_write_cancel_paths_misc.py`
- `backend/tests/test_db_txn_static.py`
- `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`

修改（只限 3.2、3.3、3.4 写明的改动）：

- 含 `aiosqlite.connect(` 的非测试文件。`19e4bd1` 上是这 21 个：`backend/agent_store.py`、`backend/byok/store.py`、`backend/conversation_matcher.py`、`backend/database.py`、`backend/discuss/billing.py`、`backend/discuss/store.py`、`backend/exchange_store.py`、`backend/main.py`、`backend/manage_strawberries.py`、`backend/novel/billing.py`、`backend/novel/drafts.py`、`backend/novel/feedback.py`、`backend/novel/store_db.py`、`backend/routers/me.py`、`backend/routers/plaza.py`、`backend/scripts/fix_matches.py`、`backend/song/jobs.py`、`backend/song/media.py`、`backend/song/store.py`、`backend/studio/store.py`、`backend/trace.py`
- `docs/ARCHITECTURE.md`、`CLAUDE.md`

其他文件一律不动。`docs/tasks/2026-11-15-write-txn-cancel-guard/` 下已有的文件（`01-investigation.md`、`02-spec.md`、`03-dispatch.md`、`verify/`）不要改。

## 7. 验收标准

命令都从仓库根目录或 `backend/` 运行，下面逐条写明。

**A1 没有直接打开连接的调用了。**

```bash
grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | grep -v "^backend/utils/db_txn.py:" | wc -l
```

期望输出 `0`。先确认这条命令真的在扫：`grep -rn "db_txn\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | wc -l` 期望 `148`。

**A2 替换是纯机械的。** 从仓库根目录：

```bash
backend/.venv/bin/python docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py 19e4bd1
```

期望末行 `CHECK_MECHANICAL files=21 replaced=148 base_sites=148 problems=0`，退出码 0。这个脚本把每个被改文件里的 `from utils import db_txn` 去掉、把 `db_txn.connect(` 换回 `aiosqlite.connect(` 之后，与基线逐字节比较（`novel/billing.py` 的 `_drain` 函数体除外）。

**A3 改动范围。** `git status --porcelain` 列出的路径全部在第 6 节的清单里。

**A4 测试。** 从 `backend/`：

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
.venv/bin/python -m pytest -q -p no:cacheprovider
```

第一条：全部通过，0 跳过。第二条：通过数等于 8552 加新增用例数，0 失败，0 跳过。如果「不做」里列的那条偶发用例失败，单独复跑它；单独能过就在实施报告里记一笔，不要去改它。

**A5 新测试有区分力（门禁由规格作者执行，执行方也应自查）。** 逐项把实现改坏，对应的新用例必须因断言失败而变红：

| 改坏什么 | 必须变红的用例 |
|---|---|
| `db_txn.connect` 退出时不回滚 | `test_novel_cancel_then_cancel_novel_succeeds`、`test_exchange_cancel_then_settlement_succeeds`、`test_chat_conversation_check_cancel_then_refund_succeeds`，以及 `test_cancelled_write_leaves_no_lock` 的**每一个**参数 |
| 回滚之后遇到再次取消就不关闭连接 | 「回滚等待时再次被取消」那条 |
| 回滚抛出的普通异常不吞 | 「回滚自己抛普通异常」那条 |
| `drain` 在调用方被取消、内层抛普通异常时只抛内层异常（即改回现在的行为） | `drain` 表格第五行那条 |
| `drain` 不等内层结束就抛出取消 | `drain` 表格第四行那条 |
| 把任意一处 `db_txn.connect(` 改回 `aiosqlite.connect(` | `test_db_txn_static.py` |
| 把任意一处 `async with db_txn.connect(...) as db:` 改成 `db = await ...` 的形式 | `test_db_txn_static.py` |

第一行里「每一个参数都变红」就是 4.3 里「至少有一条查询返回了行」的核对方式。

**A6 真实代码复现归零。** 从 `backend/`：

```bash
.venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.py
```

期望末行 `REAL_CODE_REPRO cancel_points=73 follow_up_failed=0`，退出码 0。取消点数必须还是 73（证明它扫的还是同一批位置）。

**A7 新测试不依赖本机环境。** 新测试不得依赖 git 历史、仓库之外的文件或 `frontend/node_modules`。门禁会在一份不带 `node_modules` 的浅克隆副本里单独跑五个新测试文件，要求全部通过。

**A8 文档。** `docs/ARCHITECTURE.md` 有新增的小节，`CLAUDE.md`「工作约定」里有新增的一条，内容符合 3.4。

## 8. 什么时候停下来问

- 只有影响「实现什么」的问题才停：规格自相矛盾；按规格做不出来；某条既有测试在不改它的前提下无论如何过不了；4.3 表里某个函数的准备数据造不出来。
- 只影响「怎么实现、怎么验证」的问题自己定，在实施报告里写明理由。
- 你实测到的事实优先于本规格的说法。两者不符就停下来，写明你测到了什么。
- 任何情况下都不要回滚已经完成的工作。

## 9. 修订记录

- v0.1（2026-11-15）：初稿，待作者确认。
- v1.0（2026-11-15）：作者确认第 0 节三项。规格作者另做两处不涉及这三项的文字调整：4.3 的用例分放三个文件（用例名和覆盖范围不变，只为能并行写）；实施报告的位置改为 `impl/report.md`，与此前各任务一致。
