# 返修单：独立复核第 1 轮

依据仍是 `docs/tasks/2026-11-15-write-txn-cancel-guard/02-spec.md`（v1.0）与 `03-dispatch.md` 第一节的全部规矩。独立复核报告在同目录 `04-review.md`，结论是不通过，必须修复 2 条（下面的 A、B）。规格作者核实过这两条，都属实。C 到 F 是复核列的可优化项里修法明确的几条，这一轮一并做掉。

实现的主体（`db_txn.connect`、21 个文件的替换、`_drain` 的委托、`cancel_sweep.py`）复核认定正确，不要动。本轮唯一一处运行时代码改动是 E。

## A（必须）收尾用例和「回滚异常不吞」用例，要以断言失败变红

**问题。** 把实现改坏之后，下面 4 条用例是被没接住的异常打红的，不是断言失败：

- `tests/test_write_cancel_paths.py` 的 `test_novel_cancel_then_cancel_novel_succeeds`、`test_exchange_cancel_then_settlement_succeeds`、`test_chat_conversation_check_cancel_then_refund_succeeds`：去掉回滚后，收尾写库的 `sqlite3.OperationalError: database is locked` 从检查函数里直接抛出，穿过扫描打断用例。除了不符合规格 A5「因断言失败而变红」，还有一个实际后果：第一个出问题的取消点就让整条用例中断，后面的取消点和后面要扫的函数都不再检查，失败信息里也看不出是哪个取消点出的事。
- `tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception`：回滚的异常一旦没被吞掉，`OperationalError` 从 `pytest.raises(RuntimeError)` 里漏出去。

**改法。**

1. `test_write_cancel_paths.py`：三个 `_check_*_follow_up` 不再让收尾写库的异常或超时抛出去。收尾写库放在 `try` 里（保留 2 秒上限），任何异常（包括超时）都记成一段文字，例如 `"OperationalError: database is locked"`；检查函数返回「错误文字或 `None`」加「原来的检查值」。有错误时不再去读检查值。
2. 三条用例在整轮扫描结束后，把**所有**不合格的取消点收集起来，用一条断言一起报出。每个不合格点写明：被扫的函数、k、调用标签、错误文字或与期望不符的值。原来的期望不变：`run_token` 为空、`reserved` 调用数为 0、余额多 1。
3. `test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception`：不用 `pytest.raises`，改成自己接住向外抛出的异常（`except BaseException`），再断言它就是原来那个异常对象，失败信息里带上实际接到的异常。其余断言不变。`test_connect_rolls_back_and_closes_on_plain_exception` 照同样的写法改。
4. `test_db_txn_guard.py::test_connect_closes_when_rollback_is_cancelled_again`：`_wait_task_or_fail` 现在返回 `task.result()`，被测任务以别的异常结束时用例会被那个异常打红。改成断言任务的结局（正常结束，没有异常），不合预期时用断言失败报出实际结局。

**通用要求。** 五个新测试文件里，凡是「实现改坏时会抛出非断言异常」的地方，都按上面的思路处理：把异常接住，转成带上下文的断言失败。

## B（必须）`docs/ARCHITECTURE.md` 的新小节放错了位置

**问题。** 「### 数据库连接与取消保护」现在紧跟在 `## FastAPI 后端` 这个标题下面、原有导语之前。按标题层级，原来的后端入口说明和模块表都成了这个小节的内容。

**改法。** 把这个小节（标题、三条要点、前后的空行）原样挪到 `## FastAPI 后端` 这一节的**末尾**，紧挨在 `## 主创与审稿协作` 之前。文字一个字都不改。「后端入口是 `backend/main.py`……」这段导语恢复成紧跟在 `## FastAPI 后端` 后面。

挪完后：`git diff 19e4bd1 -- docs/ARCHITECTURE.md` 应当只有新增行、没有删除行；`grep -n -E "^#{1,4} " docs/ARCHITECTURE.md` 里这个小节的标题到下一个标题之间不超过 15 行。

## C 静态守卫补上别名和间接写法

**问题。** 下面几种写法都能打开连接，而 `test_db_txn_static.py` 拦不住（复核实测 5 条全过）：`import aiosqlite as aio` 后调 `aio.connect`；`aiosqlite.core.connect`；`from aiosqlite.core import connect`；`getattr(aiosqlite, "connect")`；`functools.partial(aiosqlite.connect, ...)`。

**改法。** 在 `backend/tests/test_db_txn_static.py` 里扩充扫描（仍然只扫非测试代码，`backend/utils/db_txn.py` 仍然豁免）：

- 先收集每个文件里绑定到 `aiosqlite` 模块或 `aiosqlite.core` 模块的名字：`import aiosqlite`、`import aiosqlite as X`、`import aiosqlite.core`、`import aiosqlite.core as Y`、`from aiosqlite import core [as Z]`。
- 凡是这些名字上的 `.connect`、`.core.connect` 属性引用，**不管有没有被调用**，都算违规（这样 `partial(aiosqlite.connect, ...)` 和把它赋给别的名字也拦得住）。
- `from aiosqlite import ...` 与 `from aiosqlite.core import ...` 里导入 `connect`、`Connection` 或 `*` 的，算违规。
- 对这些名字调用 `getattr(X, "connect")`（第二个参数是字符串常量 `"connect"`）算违规。
- 直接构造连接对象 `X.Connection(...)`、`X.core.Connection(...)` 算违规。只引用 `aiosqlite.Connection` 而不调用（比如类型标注）不算。
- 原有的两条规则和「防空转」的计数不变。失败信息仍然列出文件和行号。

加一条用例证明这些规则真的在拦：在 `tmp_path` 里写一个临时源文件，里面放上面每一种写法各一处，用同一套扫描逻辑去扫它，断言每一种都被报出来。不要往 `backend/` 里放临时文件。

## D 「普通异常回滚」那条用例要能区分回滚和关闭

**问题。** `test_connect_rolls_back_and_closes_on_plain_exception` 现在的断言只靠「关闭连接」也能满足：把实现改成只在取消时回滚，它仍然通过。

**改法。** 在 `test_db_txn_guard.py` 里补一条用例（原用例保留）：作用域里 `BEGIN IMMEDIATE`，开一个多行查询、只取一行、不关游标，再写一条 `UPDATE`，然后抛普通异常；测试接住这个异常，**在还持有这个异常对象的时候**断言写锁空闲（用 `cancel_sweep.write_lock_is_free`），然后再断言数据没变、连接已关闭。对照：同样的写法换成裸 `aiosqlite.connect`，断言此时写锁不空闲（证明这条用例测得出区别）。

## E `drain` 要接受可等待对象，不只是协程

**问题。** 规格 3.1 写的是「`operation` 是一个协程或可等待对象」。现在的实现用 `asyncio.create_task(operation)`，传 Future 或 Task 会报 `TypeError: a coroutine was expected`。

**改法。** `backend/utils/db_txn.py` 里把 `asyncio.create_task(operation)` 换成 `asyncio.ensure_future(operation)`。这个文件本轮只许改这一处（文档字符串里如有相应措辞可以跟着改一句）。在 `test_db_txn_guard.py` 里补两条用例：传入一个已经在跑的 `asyncio.Task`、传入一个 `asyncio.Future`，`drain` 都按 3.1 表格的行为工作（各挑「没被取消、正常返回」和「等待期间被取消、内层正常返回」两行验证即可）。

## F 报告

`impl/report.md` 只在末尾追加一节「复核返修 R1」，不改前面的内容。

## 本轮允许改动的文件

- `backend/tests/test_write_cancel_paths.py`（A）
- `backend/tests/test_db_txn_guard.py`（A、D、E 的用例）
- `backend/utils/db_txn.py`（只有 E 那一处）
- `backend/tests/test_db_txn_static.py`（C）
- `docs/ARCHITECTURE.md`（B）
- `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`（F）

其他文件一律不动，包括 `cancel_sweep.py`、另外两个路径测试文件、21 个替换过的文件、`CLAUDE.md`。门禁会拿上一轮交回时的快照逐字节比对。

## 做法

用工作流并行，四个 agent，文件互不重叠，任务说明自包含（让它读本单对应的小节和 `04-review.md` 的相关段落），不得再派生子代理：

| agent | 负责的文件 | 本单小节 |
|---|---|---|
| paths-main | `backend/tests/test_write_cancel_paths.py` | A 的第 1、2 点 |
| guard | `backend/utils/db_txn.py`、`backend/tests/test_db_txn_guard.py` | A 的第 3、4 点，D，E |
| static | `backend/tests/test_db_txn_static.py` | C |
| docs | `docs/ARCHITECTURE.md` | B |

## 本轮验收

从 `backend/` 运行，贴原始输出和退出码，取退出码时不要接管道。做变异时先把 `backend/utils/db_txn.py` 复制到系统临时目录留底，做完用留底覆盖回去并核对哈希与留底一致。

1. 五个新测试文件全过、0 跳过；报出每个文件的收集数。
2. 变异一：把回滚那一步去掉，跑五个新测试文件，加 `--tb=line -rf`。要求：3 分钟内结束；三条收尾用例都以 `AssertionError` 失败，失败信息里看得到取消点和 `database is locked`；三个路径文件的 33 条全部失败；失败摘要里**没有**以 `sqlite3.OperationalError` 或 `TimeoutError` 开头的条目。
3. 变异二：把 `contextlib.suppress(Exception)` 换成 `contextlib.suppress()`，跑 `tests/test_db_txn_guard.py`，加 `--tb=line -rf`。要求 `test_connect_swallows_rollback_error_and_keeps_original_exception` 以 `AssertionError` 失败。
4. 变异三：把连接封装改成「只在 `asyncio.CancelledError` 时回滚」，跑 `tests/test_db_txn_guard.py`。要求 D 新补的那条用例以断言失败。
5. C 的新用例通过；另外手工验证一次：在 `backend/` 下临时放一个含 `import aiosqlite as aio` 与 `aio.connect(...)` 的 `.py` 文件，`tests/test_db_txn_static.py` 必须失败并报出该文件和行号；删掉临时文件后重跑通过，`git status` 里没有残留。
6. 规格 A1、A2、A6 重跑一遍，结果应与上一轮相同。
7. `git diff 19e4bd1 -- docs/ARCHITECTURE.md` 只有新增行；贴出 `grep -n -E "^#{1,4} " docs/ARCHITECTURE.md` 里 `## FastAPI 后端` 到 `## 主创与审稿协作` 之间的标题行。
8. 全量跑一次。规格「不做」里那条偶发用例如果失败，单独复跑并把两次结果都写上。

报告追加在 `impl/report.md` 末尾：本轮派出的 agent、改了哪些文件、上面八条的命令与输出、没做完或需要人确认的地方。
