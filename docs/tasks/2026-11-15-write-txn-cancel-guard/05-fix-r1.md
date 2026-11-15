# 返修单 R1（门禁打回）

依据仍是 `docs/tasks/2026-11-15-write-txn-cancel-guard/02-spec.md`（v1.0）与 `03-dispatch.md` 第一节的全部规矩。本单只补三处，都在测试辅助和测试里。

## 门禁结果

通过、不要再动的部分：

- `backend/utils/db_txn.py`、21 个文件的替换、`NovelBilling._drain`、两份文档。改动范围、机械替换核对、真实代码复现（73 个取消点、0 处失败）、不带 `node_modules` 的浅克隆副本都通过。
- 新测试 69 条全过；全量 8621 条，唯一失败的是规格「不做」里那条偶发用例，单独复跑通过。
- 规格 A5 表格的七行变异都被新测试以断言失败发现。

没通过的是下面三处。每处都附了能直接复跑的证据。

## F1 `cancel_sweep.py`：注入了取消、任务却没被取消时，被当成「自然跑完」

**现象。** `_run_asyncio_point` 和 `_run_anyio_point` 里，只要「这一次注入了取消但任务没有以取消收场」，就返回 `None`，整个扫描到此结束。于是：

- 被测协程在某个位置吞掉了取消，扫描不会报告，后面的取消点也都不扫了。
- 返回的记录里 `cancelled` 永远是真，所以各测试文件里 `assert point.cancelled` 这类断言测不出任何东西。规格第 1 节要的「取消不会被吞掉」实际上没有被检验。

**证据。** 从 `backend/` 运行：

```bash
.venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/sweep_truncation_probe.py
```

被测协程一共 5 次 aiosqlite 调用，在第 2 次上吞掉取消。现在的输出是只扫到 1 个取消点、`all_cancelled_true: True`。

**要改成的行为。**

- 原生取消（`cancel="task"`）：第 k 次调用上注入了取消、而任务没有以 `CancelledError` 结束 → 记一条 `cancelled=False` 的记录（检查函数照常运行），然后**继续**扫第 k+1 个取消点。原生取消下不存在「注入了却合理地没被取消」的情况。
- anyio 取消（`cancel="anyio"`）：注入之后取消域没有捕获到取消 → 只有当这一次是被测协程的**最后一次** aiosqlite 调用时才算正常（anyio 把取消推到下一次等待，后面没有等待了），这时照旧结束扫描；否则同样记一条 `cancelled=False` 并继续扫。判断「是不是最后一次」需要在注入之后继续数这个任务后面还有没有 aiosqlite 调用。
- 扫描只在「第 k 次调用根本没有发生」时结束。
- 被测协程吞掉取消之后可能继续跑完并提交数据，下一个取消点之前的 `prepare` 仍然先运行，这一点不变。

修完后上面那条探针应输出 5 条记录，其中第 2 条 `cancelled` 为假。

## F2 `cancel_sweep.py` 的 anyio 模式：检查函数跑得太晚，测不出残留写锁

**现象。** anyio 模式下，检查函数是在宿主任务结束之后才运行的。那时取消异常已经被取消域吞掉并销毁，僵尸连接已经放掉写锁。所以这一组「anyio 取消下不残留写锁」的断言永远通过：把 `db_txn.connect` 里回滚那一步去掉，`test_db_txn_connect_anyio_cancel_points_leave_no_lock` 的 9 个参数仍然全过。

真实代码里，被 anyio 取消的协程是在自己的 `finally` 里（屏蔽取消之后）做收尾写库的，那时取消异常还在向外传播。检查要放在那个位置才有意义。

**证据。** 从 `backend/` 运行：

```bash
.venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/sweep_anyio_probe.py
```

它用没有任何保护的裸 `aiosqlite.connect` 跑「多行查询只取一行、游标不关」的写法。现在的输出：

```
辅助模块的检查（任务结束之后）写锁空闲: [True, True, True, True, True, True]
被测协程自己的 finally 里（屏蔽取消）写锁空闲: [True, False, False, True, True, True]
```

第二行是真实情况，第一行是辅助模块看到的。

**要改成的行为。** anyio 模式下，检查函数改在宿主任务内部运行：被测协程抛出取消之后、取消域退出之前，在 `finally` 里用 `anyio.CancelScope(shield=True)` 包住运行。`CancelPointContext.task` 给宿主任务本身。「检查函数没跑完算失败」的规则不变。原生取消模式的检查位置不变（`gather` 之后、任务对象仍被引用）。

修完后上面那条探针的两行应当一致。

## F3 `test_connect_closes_when_rollback_is_cancelled_again` 会无限等待

**现象。** 这条用例等 `rollback_started.wait()` 时没有超时。实现一旦不调用回滚（比如回滚那一步被删掉或被换成别的），它不是失败，而是永远卡住，整个测试进程挂死。门禁里「去掉回滚」和「把回滚换成提交」两条变异都卡在 `tests/test_db_txn_guard.py` 第 390 行。

**要改成的行为。** 这条用例里所有等待都要有上限（几秒），等不到就以断言失败收场。同时把五个新测试文件和 `cancel_sweep.py` 通查一遍：等事件、等任务、等锁的地方都不许无限等。

## 要补的用例

都放在 `backend/tests/test_db_txn_guard.py`：

1. `test_sweep_reports_swallowed_cancellation`：被测协程 5 次 aiosqlite 调用，在第 2 次上吞掉取消（写法照 `verify/sweep_truncation_probe.py`）。断言：扫描返回 5 条记录；第 2 条 `cancelled` 为假；其余为真。
2. `test_bare_aiosqlite_anyio_control_group_can_hold_write_lock`：裸 `aiosqlite.connect` 加规格 4.2 的第 3 种写法，anyio 取消。断言：至少有一个取消点上写锁不空闲。它证明 anyio 这一组不是空转。
3. 原有的 `test_db_txn_connect_anyio_cancel_points_leave_no_lock` 保持断言不变；F2 修好后它才真正在检验东西。

三个 `test_write_cancel_paths*.py` 里的 `assert point.cancelled` 不用改，F1 修好后它们自然生效。除非 `cancel_sweep.py` 的对外用法不得不变，否则不要动这三个文件；`cancel_sweep.py` 的函数签名和记录字段尽量保持不变。

## 本轮允许改动的文件

- `backend/tests/cancel_sweep.py`
- `backend/tests/test_db_txn_guard.py`
- `docs/tasks/2026-11-15-write-txn-cancel-guard/impl/report.md`（在末尾追加一节「返修 R1」，不要改前面的内容）
- 只有在 `cancel_sweep.py` 的对外用法不得不变时，才可以改 `backend/tests/test_write_cancel_paths.py`、`test_write_cancel_paths_core.py`、`test_write_cancel_paths_misc.py`，并在报告里写明为什么。

其他文件一律不动，包括 `backend/utils/db_txn.py` 和 21 个替换过的文件。门禁会拿上一轮交回时的快照逐字节比对。

## 做法

这一轮只有两个文件，而且有先后：先改 `cancel_sweep.py`，再改 `test_db_txn_guard.py`。仍然用工作流派发：第一步一个 agent 负责 `cancel_sweep.py`，完成后第二步一个 agent 负责 `test_db_txn_guard.py`。agent 不得再派生子代理，任务说明要自包含（让它读本单的对应小节和 `verify/` 下的两个探针）。

## 本轮验收

从 `backend/` 运行，贴原始输出和退出码，取退出码时不要接管道。

1. 两个探针：`sweep_truncation_probe.py` 输出 5 条记录、第 2 条 `cancelled` 为假；`sweep_anyio_probe.py` 的两行一致。
2. 五个新测试文件全过、0 跳过；报出每个文件的收集数。
3. 「去掉回滚」的自查，这次要覆盖五个文件：先把 `backend/utils/db_txn.py` 复制到系统临时目录留底，去掉回滚那一步，跑五个新测试文件。要求：整个命令在 3 分钟内结束、没有卡住；`test_db_txn_connect_anyio_cancel_points_leave_no_lock[f3_begin_multi_select_open_cursor]` 失败；三个 `test_write_cancel_paths*.py` 的 33 条全部失败。然后用留底文件覆盖回去，核对哈希，重跑确认全过。
4. 规格 A1、A2、A6 重跑一遍，结果应与上一轮相同。
5. 全量跑一次。那条偶发用例如果失败，单独复跑并把两次结果都写上。

报告追加在 `impl/report.md` 末尾：本轮派出的 agent、改了哪些文件、上面五条的命令与输出、没做完或需要人确认的地方。
