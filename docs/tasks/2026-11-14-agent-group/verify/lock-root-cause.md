# 偶发「database is locked」的根因记录

规格作者在第三轮返修的门禁里补查。`07-fix-r3.md` 第一节对机制的描述不准确，以本文件为准；修法的方向（写事务不受调用方取消打断）是对的。

## 现象

第二轮返修的代码上，`tests/test_discuss_api.py` 里 `test_patch_plan_changes_and_guards` 的收尾偶发报错：关停流程里 `cancel_group` → `refund_reserved` → `BEGIN IMMEDIATE` 报 `sqlite3.OperationalError: database is locked`，此前后台任务自己的收尾已经打出 `refund_failed` 与 `token_clear_failed`。三次写库各等满 5 秒，整轮多出约 15 秒。

出现频率很低：干净环境下连跑那 7 条用例，第 343 轮才出现一次；4 路并行时某一路第 17 轮出现。所以「连跑几百次没出错」本身不能证明修好了。

## 现场证据

在第二轮返修代码的副本里装诊断钩子，锁库的那一刻列出进程里的全部连接：

- 没有任何还开着的连接。3 个 aiosqlite 连接对象都已关闭，工作线程都已退出。
- 进程里还活着 2 个原生 `sqlite3.Connection` 对象，Python 层都已关闭。其中一个被一个原生游标引用着，游标是一个已完成的 Future 的结果，Future 又被 `aiosqlite/core.py` 里 `_execute` 的栈帧引用着；这条语句是写事务里核对令牌的那条查询（`... AND g.run_token=?`）。

## 机制

1. 后台任务在写事务里（`BEGIN IMMEDIATE` 之后）执行一条查询。语句已经在 aiosqlite 的工作线程里执行完，结果（一个原生游标）还没被协程取走，取消正好在这时到达。
2. 协程收到的是 `CancelledError`，那个游标没人包装、没人关闭，但被取消异常的调用栈一直引用着。
3. 之后连接照常 `close()`，但写锁没有释放（在 Python 3.14.6、SQLite 3.53.3 上实测）。原因应是 `sqlite3` 模块关闭连接用的是 `sqlite3_close_v2`：还有没收尾的语句时，连接只是变成「僵尸」，事务不回滚、写锁不释放，要等最后一条语句被销毁。这一句是对实测现象的解释，没有逐行核对解释器源码。
4. 任务的收尾代码（退还预扣、清令牌）正是在这个取消异常还在传播时运行的，调用栈活着，游标就活着，写锁就一直被占；之后异常对象陷在引用环里，要等垃圾回收，所以关停流程自己的那次写库也超时。

取消必须落在「语句已执行、结果未取走」这个很窄的窗口里，所以罕见；机器越忙窗口越宽。

## 确定性复现

`verify/zombie_probe.py` 让任务恰好停在上述位置再取消，并像 `runner._run` 那样在 `finally` 里立刻去拿写锁：

| 代码 | 结果 |
|---|---|
| 第二轮返修（写事务不受保护） | `lock_in_cleanup=locked (OperationalError: database is locked)`，探针失败 |
| 第三轮返修（写事务整体放进受保护任务） | `lock_in_cleanup=free`，探针通过 |

第三轮返修之所以对症，是因为它同时加了两层防护，任何一层单独都足以让写锁释放：

1. 令牌核对挪进了「出任何异常都先回滚」的范围。第二轮返修的代码里，令牌核对那条查询在这个范围之外，被取消时没有回滚。回滚之后，僵尸连接不再带着写事务。
2. 整个事务（含取走游标、提交、关闭连接）在一个不受调用方取消影响的任务里跑完，不会留下没人关的游标。

在第三轮返修的代码上逐层去掉防护的实测（用例 `test_cancel_with_unconsumed_cursor_leaves_no_write_lock_during_cleanup`）：

| 去掉什么 | 结果 |
|---|---|
| 只去掉受保护任务 | 通过（回滚兜底） |
| 只去掉回滚 | 通过（事务不被打断） |
| 两层都去掉 | 失败：`sqlite3.OperationalError: database is locked` |

## 收进正式测试

门禁后规格作者在 `backend/tests/test_discuss_runner.py` 末尾补了两条用例（执行方三轮返修已用完，按流程由规格作者接手）：

- `test_cancel_with_unconsumed_cursor_leaves_no_write_lock_during_cleanup`：上面这个探针的正式版。
- `test_stale_worker_pause_writes_nothing_and_returns_quietly`：过期任务写终态时什么都不写、也不抛异常。补它是因为变异「去掉 `_pause` 对过期任务的安静退出」此前存活。

`verify/cancel_probe.py` 是更早写的随机取消探针，在第二轮返修代码上 372 次中途取消没有一次留下写锁，它测不出这个问题，保留只作记录。

## 范围之外

同样的机制对任何「aiosqlite 写事务中途被取消」的代码都成立，不限于讨论群：书斋、聊天等模块的写事务没有这层保护。这是既有隐患，不在本任务范围内，交付时单独提出。
