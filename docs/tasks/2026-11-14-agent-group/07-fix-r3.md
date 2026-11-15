# 返修单 R3：多智能体讨论群第一期

依据仍是 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1）。R2 交回后的门禁：新测试 149 通过、0 跳过；全量 8501 通过、0 跳过；T18、T19 对应的变异都靠断言失败被杀死。但 R2 对「偶发报错」的定位不对，问题还在。本轮只处理下面两件事。

## 一、偶发报错的真实原因（必须修）

规格作者不加负载连跑 `tests/test_discuss_api.py` 的前 7 个用例，第 24 次复现，报错原文如下（节选）：

```
ERROR at teardown of test_patch_plan_changes_and_guards
main.py: in lifespan
    await shutdown_discuss_tasks()
discuss/runner.py: in shutdown_discuss_tasks
    await cancel_group(group_id, username)
discuss/runner.py: in cancel_group
    await DiscussBilling(username, group_id).refund_reserved()
discuss/billing.py: in _refund_reserved_transaction
    await db.execute("BEGIN IMMEDIATE")
E   sqlite3.OperationalError: database is locked

WARNING discuss.runner group_id=… status=refund_failed type=OperationalError
WARNING discuss.runner group_id=… status=token_clear_failed type=OperationalError
6 passed, 17 deselected, 45 warnings, 1 error in 17.40s
```

`database.SQLITE_BUSY_TIMEOUT` 是 5 秒，三次写库各等满 5 秒后失败，合计约 15 秒，这就是之前每次都多出约 14 秒的来历。

原因：后台任务被取消时，可能正停在一次写事务中间。`aiosqlite` 的语句是交给它自己的工作线程执行的，协程被取消并不能撤回已经入队的语句：`BEGIN IMMEDIATE` 照样执行并拿到写锁，而协程这边已经抛出 `CancelledError`，后面的提交、回滚、关闭连接要么没执行、要么再次被取消打断。结果是一条没人管的连接一直占着写锁，之后整个库的写操作都要等到超时。

这不只是测试偶发失败：线上在不巧的时刻暂停、删除或关停，会让整个应用（聊天、扣费、其他功能）的写入在一段时间内全部失败。

`discuss/billing.py` 的每个事务都包了 `NovelBilling._drain(...)`（把整个事务连同关闭连接放进一个受保护的任务里跑完，再把取消交还给调用方），所以计费没有这个问题。但 `discuss/store.py` 里 `DiscussStepStore.transaction()` 以及其他后台写入都没有保护。

**要求**

1. 后台流程发起的每一次写事务，都必须在取消到来时照样跑完（提交或回滚，并关闭连接）之后，才把 `CancelledError` 交还给调用方。做法与 `NovelBilling._drain` 相同，直接复用它。覆盖范围至少包括：
   - `DiscussStepStore` 的 `transaction()` 以及基于它的写入：发消息、改群状态、存成果、存验收结论、登记来源、认领插话、`write_step`、`append_usage`；
   - `discuss/runner.py` 里的写入：写入与清空令牌、`_pause`、恢复失败时改状态、`cancel_group` 里清令牌；
   - `discuss/research.py` 与 `discuss/engine.py` 里直接或间接发起的写入。
   `transaction()` 现在是「把连接交给调用方」的上下文管理器，调用方在里面还会 `await`。可以改成「把要做的写操作作为一个协程函数传进去，由存储层在受保护的任务里整体执行」这种形式，也可以用别的办法，只要满足上面这句话。写操作内部不得再等待模型调用、搜索或任何非数据库的东西。
2. 作者侧接口（`discuss/service.py`）里的写事务也照此保护：请求被客户端断开时同样会被取消。
3. 行为不变：令牌守卫、去重、原子结算、返回值都照旧；已有用例的断言不改。

**必须有能稳定复现的用例**（修之前失败、修之后通过，不靠多跑几次碰运气）：

- 让一个后台任务停在一次写事务的中间（例如把连接的某个方法换成会等待一个事件的版本，或者在事务内部插入一个可控的等待点），此时取消这个任务，再放行。然后用一条新连接、把忙等待设成很短（例如 0.2 秒）执行 `BEGIN IMMEDIATE`，必须立刻成功，不得出现 `database is locked`。至少覆盖：发消息或改状态这类通过 `transaction()` 的写入一种，`runner` 里清令牌或 `_pause` 一种。
- 对同一个任务连续取消两次（模拟 `cancel_group` 之后关停流程又取消一次）的情形也要覆盖。
- 自检：把你加的保护去掉，新用例必须失败；贴出失败输出，再还原。

## 二、R2 那处改动的测试不够

R2 给 `cancel_group` 加了「任务所属事件循环已关闭或未运行时不去调度」的处理，这个加固可以保留，但它的回归用例没有测到它声称的行为。规格作者加了两条变异：

| 编号 | 变异 | 结果 |
|---|---|---|
| N8 | 把 `if loop.is_closed() or not loop.is_running():` 改成 `if False:` | 存活 |
| N9 | 去掉 `finally` 里把任务从 `TASKS` 与 `_owners` 移除的两行 | 存活 |

N8 存活是因为后面还有一层 `except RuntimeError` 兜着，两层只需要一层：留哪一层由你定，把多余的那层删掉，使剩下的那层有用例能区分。N9 需要一条断言：`cancel_group` 处理过的任务不再留在 `TASKS` 与 `_owners` 里，对「已结束的任务」和「事件循环已关闭的任务」都成立。

## 三、规矩

1. 只允许改：`backend/discuss/store.py`、`runner.py`、`engine.py`、`research.py`、`service.py`、`billing.py`（仅当需要把 `_drain` 的用法抽成共用辅助时）、`backend/tests/test_discuss_*.py`、新报告 `docs/tasks/2026-11-14-agent-group/impl/report-r3.md`。其他文件不动。
2. 不改 `backend/novel/` 下任何文件（书斋里同样的隐患不在本次范围内，报告里提一句即可）。
3. 已有用例的断言不许放宽或删除。其余规矩同前几轮。
4. 改动涉及多个实现文件时用工作流并行，按文件不重叠拆分；`store.py` 的新接口先定好再让其他文件的 agent 去用（先串行改 `store.py`，再并行改其余）。

## 四、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过。
2. 稳定性：下面这条命令连跑 150 次，150 次都必须退出码 0；贴出统计（通过次数、失败次数）。任何一次失败都要贴出报错原文并继续修。

   ```
   .venv/bin/python -m pytest -q -x -p no:cacheprovider tests/test_discuss_api.py -k "admission or create_group_planning or patch_plan or second_group"
   ```

3. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 新测试总数，0 失败、0 跳过。
4. 变异自检：`backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <结果文件.json> N8 N9 T1 N6`，四条都靠 `failed` 杀死（N8 若因为你删掉了它所在的那一层而找不到锚点，在报告里说明）。
5. `git status --porcelain --untracked-files=all` 与 R2 交付相比，只多出或变动本单第三节第 1 条允许的文件。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-r3.md`，不写本机绝对路径：保护是怎么做的、覆盖了哪些写入点（逐个列出函数名）、新用例的函数名与自检输出、验收五条的命令与输出摘要、未完成或需要人工确认的地方。
