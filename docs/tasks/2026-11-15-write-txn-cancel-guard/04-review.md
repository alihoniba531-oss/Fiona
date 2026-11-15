# 写库取消保护 · 独立复核（R1 返修之后）

复核对象：基线 `19e4bd1` 加上未提交的待审改动。复核开始时按 `.cache/review/r1.sha256` 逐个核对了 31 个文件的哈希，全部一致；所有变异实验做完、逐个用留底覆盖回去之后又核对了一遍，仍然全部一致，`git status --porcelain --untracked-files=all` 与开始时逐行相同。

唯一依据：`02-spec.md` v1.0。实现方报告和规格作者的门禁结论只当线索，下面的结论都是我自己跑出来的。

所有命令都在副本里执行，测试命令前都加了 `env -u ANTHROPIC_BASE_URL` 和 `-o faulthandler_timeout=60`，外面再套一层 `timeout`。下文贴出的输出里，本机路径已删掉。

---

## 1. 结论

**不通过。** 有 2 条必须修复项，都在测试和文档里，运行时代码不用改：

| # | 位置 | 一句话 |
|---|---|---|
| F1 | `tests/test_write_cancel_paths.py` 的三条收尾用例；`tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception` | 套上 A5 第 1 行、第 3 行的变异后，这 4 条用例是被未捕获的 `sqlite3.OperationalError` 打红的，不是断言失败。A5 要求「因断言失败而变红」，所以这两行目前不达标。 |
| F2 | `docs/ARCHITECTURE.md` | 新小节插在「## FastAPI 后端」标题和原有导语之间。按 Markdown 的标题层级，原有导语和整张模块表（第 164–248 行，约 85 行）都归进了「### 数据库连接与取消保护」，与 3.4「一小节，不超过 15 行」不符。 |

审过、没发现问题的部分：

- **`backend/utils/db_txn.py`**：3.1 的 8 条行为和 `drain` 表格的 5 行全部满足。另外实测了 GeneratorExit、KeyboardInterrupt、连接没打开成功、作用域里自己先关了连接、嵌套使用、`asyncio.timeout` 这几种边界情况，结果都正确，见 2.9。
- **替换**：148 处替换和 21 个文件的导入逐行核对过，除了换调用名、加一行导入，没有别的改动；每一处 `db_txn` 在执行时都取得到。非测试代码里没有别的打开异步连接的写法。
- **`_drain` 语义变化**：逐个看了调用点和上层的 `except` 分支，没有找到会多退、少退、漏记或写错状态的路径，见 2.11。
- **既有行为**：全量测试只挂了规格「不做」里那条偶发用例，单独复跑通过。正常路径多出的开销不到 1%。

对规格作者门禁陈述的核对：

| 陈述 | 结果 |
|---|---|
| 改动的文件恰好等于第 6 节清单 | 属实 |
| `check_mechanical` 输出 `files=21 replaced=148 base_sites=148 problems=0` | 属实 |
| 五个新文件 71 条全过 | 属实 |
| 全量唯一失败是那条偶发用例 | 属实 |
| `real_code_repro` 输出 `cancel_points=73 follow_up_failed=0` | 属实 |
| A5 七行变异都被断言失败发现 | **不属实**：第 1 行里的三条收尾用例和第 3 行，变红的原因不是断言失败（F1） |

---

## 2. 规格第 7 节 A1–A8 逐条核验

### A1 没有直接打开连接的调用（通过）

从仓库根目录运行：

```text
$ grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | grep -v "^backend/utils/db_txn.py:" | wc -l
       0
$ grep -rn "db_txn\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests | wc -l
     148
```

正控：同一条命令去掉 `grep -v` 后输出 `1`，就是 `db_txn.py` 自己那一处；基线上 `git grep -n "aiosqlite\.connect(" 19e4bd1 -- 'backend/*.py' ':!backend/tests/*'` 输出 148 行、21 个文件。取退出码时不接管道：`grep -rn "aiosqlite\.connect(" backend --include='*.py' --exclude-dir=.venv --exclude-dir=tests --exclude=db_txn.py` 的退出码是 1，也就是没有命中。

### A2 替换是纯机械的（通过）

```text
$ backend/.venv/bin/python docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py 19e4bd1
CHECK_MECHANICAL files=21 replaced=148 base_sites=148 problems=0
A2_exit=0
```

`check_mechanical.py` 不核对导入加在哪一行，只要求这行恰好出现一次；它也不核对 `db_txn` 在调用点是否取得到。所以我另写了一个更严的核对，结果 `STRICT files=21 calls=148 problems=0`，退出码 0。它核对四件事：

- 用 difflib 逐行比对基线：每个改动块只能是「换调用名的同行替换」或「插入一行 `from utils import db_txn`」。
- 导入恰好加在第一处 `import aiosqlite` 的下一行，缩进相同。
- 用语法树核对每一处 `db_txn.connect(`：它所在的函数链或模块顶层，在这一行之前有 `from utils import db_txn`。
  - `main.py` 第 253 行函数里有局部 `import aiosqlite`，但 `db_txn` 是模块顶层导入的，取得到。
  - `manage_strawberries.py`、`routers/me.py`、`routers/plaza.py` 的导入都和调用在同一个函数里。
- 非测试代码里没有任何地方给 `db_txn` 这个名字赋值、拿它当参数名或重新定义它。

`novel/billing.py` 除了替换以外的改动，只有 `_drain` 函数体换成 `return await db_txn.drain(operation)`。名字、`@staticmethod`、签名和文档字符串都保留了。

### A3 改动范围（通过）

`git status --porcelain --untracked-files=all` 一共 53 行：

- 23 个修改：21 个后端文件，加 `CLAUDE.md`、`docs/ARCHITECTURE.md`。
- 7 个新增代码和测试文件，加 `impl/report.md`。
- 规格作者的任务材料：`01`/`02`/`03`/`05` 和 `verify/` 下的文件。
- 我的复核材料 `.cache/review/`。

逐行对照第 6 节，清单外的路径是 0 个，清单里的 23 个修改也一个不缺。

### A4 测试（通过，附一条说明）

五个新文件，从 `backend/` 运行：

```text
$ .venv/bin/python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=60 -rs tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
71 passed in 34.74s
A4_new_exit=0
```

0 跳过。各文件收集数：33、13、17、3、5。所有变异做完后又跑了一遍，结果是 `71 passed in 27.62s`。

全量：

```text
$ .venv/bin/python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=120 -rfEs
FAILED tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]
1 failed, 8622 passed, 47 warnings in 549.18s (0:09:09)
A4_full_exit=1
```

8622 + 1 = 8623 = 8552 + 71，0 跳过。失败的是规格「不做」里列的那条，断言是 `started == {三个角色}` 时只有 `plot_architect` 启动了。它不碰数据库，是调度时序问题。单独复跑 5 次都是 `1 passed in 0.05s`，所在文件单独跑是 `55 passed in 0.18s`。

再看实现会不会影响它：`_drain` 改成 `return await db_txn.drain(...)` 之后只多了一层直接 await 的协程帧，不多让出一次事件循环，调度顺序没有变。

### A5 新测试有区分力（不通过：第 1 行和第 3 行不达标，见 F1）

变异方法：

1. 改之前留底。
2. 用文本替换改坏，确认锚点恰好命中一次。
3. 跑对应的测试，用 `--junitxml` 逐条记下失败类型。
4. 用留底覆盖回去，核对哈希。

每条命令都有 300 秒上限，实际最长一条 51 秒，没有卡住。

| 规格 A5 的行 | 我的变异 | 必须变红的用例 | 结果 |
|---|---|---|---|
| 1 退出时不回滚 | `await db.rollback()` 换成 `pass` | 三条收尾用例 + `test_cancelled_write_leaves_no_lock` 的全部 30 个参数 | 30 个参数**全部因 AssertionError 变红**，例如 `trace.log_event 的取消点 k=2 [...] 在任务对象仍被引用时写锁没有释放`。**三条收尾用例变红的原因是 `sqlite3.OperationalError: database is locked` 从检查函数里直接抛出，不是断言失败**，见 F1。（同时还有 6 条 guard 用例因断言变红。） |
| 2 回滚后遇到再次取消就不关闭 | 改写成 `db = await aiosqlite.connect(...)`，回滚抛 `CancelledError` 时直接 `raise`、跳过 `close()` | 「回滚等待时再次被取消」 | 因断言变红：`assert <sqlite3.Connection ...> is None`。（参数透传那条也挂了，报 `TypeError: '_FakeConnection' object can't be awaited`。那是我的改写引入的副作用，与本行无关。） |
| 3 回滚抛出的普通异常不吞 | `suppress(Exception)` 换成 `suppress()` | 「回滚自己抛普通异常」 | **变红的原因是 `sqlite3.OperationalError: rollback failed` 从 `pytest.raises(RuntimeError)` 里漏出去，不是断言失败**，见 F1 |
| 4 `drain` 改回只抛内层异常 | 删掉 `if cancelled: raise CancelledError() from exc` | 表格第五行 | 因断言变红：`isinstance(ValueError('inner failure'), CancelledError)` 为假 |
| 5 `drain` 不等内层结束就抛取消 | 捕获到调用方的取消后立刻 `raise` | 表格第四行 | 因断言变红：`assert [False] == [True]`。另有第五行和「连续取消三次」也因断言变红 |
| 6 一处 `db_txn.connect(` 改回 `aiosqlite.connect(` | 改 `trace.py` 那一处 | `test_db_txn_static.py` | 因断言变红，失败信息里列出了 `backend/trace.py:24:20  async with ...` |
| 7 一处改成 `db = await ...` 形式 | 改 `scripts/fix_matches.py` | `test_db_txn_static.py` | 因断言变红，`test_db_txn_connect_calls_are_async_with_context_expressions` |

第一行里「每一个参数都变红」也就核对了 4.3 的「至少有一条查询返回了行」：30 个参数都在 k=1～6 的某个点上因写锁不空闲变红。

### A6 真实代码复现归零（通过）

```text
$ .venv/bin/python -B ../docs/tasks/2026-11-15-write-txn-cancel-guard/verify/real_code_repro.py
   取消点 7 个；之后执行 cancel_novel 的下一步 NovelBilling.refund_reserved：失败 0 个
   取消点 10 个；之后执行 取消后的结算 stop_and_discard_reserved_calls：失败 0 个
   取消点 22 个；之后执行 run_chat 收尾里的 refund_strawberries：失败 0 个
   取消点 12 个；之后执行 refund_strawberries：失败 0 个
   取消点 15 个；之后执行 refund_strawberries：失败 0 个
   取消点 7 个；之后执行 refund_strawberries：失败 0 个
REAL_CODE_REPRO cancel_points=73 follow_up_failed=0
A6_exit=0
```

取消点总数还是 73，与规格第 2 节的表逐行相同。

### A7 新测试不依赖本机环境（通过）

改动没有提交，浅克隆拿不到它们，所以我造了一份等价的副本：

- 内容：`git ls-files` 列出的已跟踪文件，加上未被忽略的未跟踪文件（排除 `.cache/`）。
- 不带：`.git`、`frontend/node_modules`、`backend/.venv`。
- 放在副本之外的临时目录里，没有进任何仓库目录。

在里面跑：

```text
$ git rev-parse --git-dir
fatal: not a git repository (or any of the parent directories): .git
$ GIT_CEILING_DIRECTORIES=<临时目录> <副本的 .venv>/bin/python -m pytest -q -p no:cacheprovider tests/test_db_txn_guard.py tests/test_write_cancel_paths.py tests/test_write_cancel_paths_core.py tests/test_write_cancel_paths_misc.py tests/test_db_txn_static.py
71 passed in 32.37s
A7_exit=0
```

### A8 文档（内容符合，位置不符合，见 F2）

- `CLAUDE.md`「工作约定」只加了一行：`后端代码不直接调 aiosqlite.connect，一律用 utils.db_txn.connect，有测试拦截。` 符合 3.4。
- `docs/ARCHITECTURE.md` 加了 6 行：标题、三条要点、两个空行。三点都写到了，「为什么」的一两句话也写清楚了。**问题在位置**，见 F2。
- 3.4 第三点：用 `git grep` 在 `docs/tasks/` 以外的所有已跟踪文件里搜 `aiosqlite`，只剩上面这两处新说法和 `requirements.txt` 里的版本号；搜「打开…连接」「connect(」之类的说法，也没有残留的旧写法。

### 2.9 其他审查：`db_txn.connect` 对照 3.1

| 3.1 的行为 | 核对方式 | 结果 |
|---|---|---|
| 1 参数原样透传 | 读代码；`test_connect_passes_arguments_through_unchanged` | 满足 |
| 2 调用那一刻经模块属性取 `aiosqlite.connect` | 读代码：在生成器体内写 `aiosqlite.connect(...)`，进入 `async with` 时才取；全量里替换 `exchange_store.aiosqlite.connect`、`main.aiosqlite.connect` 的既有用例都通过 | 满足 |
| 3 交出的就是连接对象本身 | `Connection.__aenter__` 返回 `self`；有专门用例 | 满足 |
| 4 无异常时只做原来的关闭 | 读代码：`try` 正常结束后由 `aiosqlite` 的 `__aexit__` 关闭 | 满足 |
| 5 有异常离开时先回滚再关闭 | 探针：异步生成器被 `aclose()`，作用域里抛 GeneratorExit，此时游标还活着，写锁空闲（裸连接对照组不空闲）；作用域里抛 KeyboardInterrupt，写入被回滚，连接已关，KeyboardInterrupt 照常传到 `asyncio.run` 之外 | 满足 |
| 6 回滚抛普通异常时吞掉 | 用例；探针：作用域里先 `await db.close()` 再抛 ValueError，回滚报「no active connection」被吞掉，向外仍是 ValueError | 满足 |
| 7 回滚被再次取消时仍关闭 | 读代码：`rollback()` 内部在第一次挂起之前就把回滚放进了工作队列；关闭写在外层 `async with` 的退出路径上，`close()` 又在第一次挂起之前把关闭放进队列，`finally` 里还会 `stop()`。用例里，被 anyio 再次取消后工作线程退出了 | 满足 |
| 8 只支持 `async with` | 静态守卫强制；`await db_txn.connect()` 在运行时会直接报 TypeError | 满足 |

其他边界情况，都是探针实测：

- 连接没打开成功（目录不存在）：原样抛 `OperationalError('unable to open database file')`，不会走到回滚。
- 嵌套使用：内层抛异常被外层接住，外层照常提交。两个连接都关了，写锁空闲。
- `asyncio.timeout(0.05)` 包住一个停在 `sleep` 上的写事务：外面收到 TimeoutError，写锁空闲，数据已回滚。
- 普通异常（不是取消）也会留下残留写锁：异常对象还被引用、多行游标没取完时，裸 `aiosqlite.connect` 的写锁不空闲。这时 traceback 和栈帧之间有引用环，要等 gc 才会释放。`db_txn.connect` 的写锁空闲。这说明「任何异常都先回滚」是有实际意义的，不只为取消。
- 性能：400 次开连接、写、关连接，取三轮里的最小值：
  - 正常路径：裸 370µs，封装 373µs。
  - 异常路径：裸 291µs，封装 321µs，多出来的是一次回滚的往返。

`drain` 对照 3.1 表格：五行由用例和变异 M4、M5、M13–M15 一起锁定，见第 5 节。「返回或抛出之前内层都已结束」在所有 `CancelledError` 和 `Exception` 路径上都成立。只有调用方自己收到 KeyboardInterrupt 或 GeneratorExit 这类非 `CancelledError` 的 BaseException 时会直接透出，asyncio 下这种情况不现实。

### 2.10 其他审查：替换是否完整，静态守卫能否绕过

- 在非测试代码里搜了几种打开连接的写法：`aiosqlite.Connection(`、`aiosqlite.core`、`from aiosqlite import`、`import aiosqlite as`、`getattr(aiosqlite`、不带括号引用 `aiosqlite.connect`。除 `db_txn.py` 外都没有命中。backend 之外的 `.py` 只有 `docs/tasks/` 下的探针用到 aiosqlite。没有 `autocommit=`，也没有 `isolation_level` 设置，所以 `rollback()` 不会变成空操作。
- 三个模块级封装都写成 `async with db_txn.connect(...) as db: ... yield db`，嵌套 `asynccontextmanager` 时异常能逐层传进去，已验证。`studio.store.connection` 自己也有一次回滚，和封装的回滚叠加没有副作用。
- **静态守卫能被绕过**，列为可优化项。我加了一个临时文件，里面五种写法都打开了连接：`import aiosqlite as aio` 后调 `aio.connect`、`aiosqlite.core.connect`、`from aiosqlite.core import connect`、`getattr(aiosqlite, "connect")(...)`、`functools.partial(aiosqlite.connect, ...)`。结果 `test_db_txn_static.py` 5 条全过，A1 的 grep 也输出 0。临时文件随后删掉，状态已复原。规格 4.4 只要求拦两种写法，所以这不是不合格。

### 2.11 其他审查：`_drain` 语义变化对调用方的影响

新行为是：调用方已被取消、内层抛普通异常时，收到的是 `CancelledError`，它的 `__cause__` 是内层那个异常。我逐个看了调用点：

- **`NovelBilling.reserve`、`DiscussBilling.reserve` / `reserve_fixed`**：`except CancelledError` 里会做一次补偿退款，现在多了一条路：内层失败时也会走到这次补偿。这时内层事务已经回滚，本次没有留下 `reserved` 行。`_finish_transaction` 只处理 `billing_status='reserved'` 的行，处理完立刻翻成 `refunded`。所以同一笔预留最多退一次，不会多退；按现有约定（预留时 `ON CONFLICT` 会覆盖同一个 `step_key`），这一步退 0。
- **补偿退款自己抛异常时**（比如 `RunNoLongerActive`），这个异常会顶掉 `CancelledError`。旧版在内层成功的那条路上本来就这样；内层失败的那条路上，旧版直接抛内层异常，结果一样。这不是回退，列为遗留。
- **`settle` / `refund` / `_finish` / `refund_reserved`**：
  - `llm_router._attempt` 的 `finally` 里是 `except BaseException: 退款; raise`，退款行为不变。
  - `_with_retries` 里 `_drain(_complete_response(...))` 不在 `try` 里，异常直接上抛；`_complete_response` 的补偿写在内层任务自己的 `finally` 里，也受保护。
  - `runner._run` 收到 `CancelledError` 时原样上抛，不再走 `_pause` 或「写成 failed」那些分支。旧版这时会把暂停或删除过程中的书写成 `step_failed`，也就是调查记录第 6 节说的那个问题。`finally` 里的 `refund_reserved` 和清令牌照常执行，`cancel_novel` 排空任务之后还会再退一次、再清一次。没有少退，也没有漏清令牌。
- **讨论群**：
  - `run_write`、`release_claim`、`claim_token` 的 `except CancelledError` 分支在新行为下仍然正确：领取失败时清令牌的条件匹配不到行，是空操作。
  - `_cleanup` 里的 `except Exception` 接不住 `CancelledError`。所以清理期间如果第二次被取消、退款又恰好失败，后面关客户端和清令牌这两步会被跳过。旧版在退款成功时本来就这样跳过；令牌和预留另外由 `cancel_group` 在排空任务之后处理，只有客户端关闭会留给 gc。
  - `avatar.py` 的三处读取：`CancelledError` 在 `_AVATAR_RAISE` 里，会原样上抛。`engine._avatar_try` 里检查 `cancelling()` 的补丁现在多余了，但无害。
- **步骤记录**：settle 带着 `step_record` 时，扣费和步骤记录在同一个事务里，要么都提交，要么都回滚，不会出现扣了费没记步骤。

结论：没有找到多退、少退、漏记或写错状态的路径。

### 2.12 其他审查：测试的证明力与稳定性

- **`cancel_sweep.py`**：
  - 两种落点：「结果已交回」只对被测任务当前正在等的 Future 生效（核对 `_fut_waiter`）；「还在排队」先投递取消再入队，等价于「刚入队就取消」。
  - 两种取消方式：anyio 的检查在宿主任务的 `finally` 里、`CancelScope(shield=True)` 内运行，也就是 F2 修好之后的样子。
  - 终止条件：只有「第 k 次调用没有发生」，或者「anyio 取消落在最后一次调用上」才结束。被吞掉的取消记成 `cancelled=False`，扫描继续往下走。
  - 契约，用探针核实过：一个取消点都没扫到时抛 `NoCancelPointsFound`；扫描正常结束、检查函数抛异常、扫描任务被取消，这三种情况下 `aiosqlite.core` 的两个属性都还原了；重入时抛 RuntimeError。
  - 两个 R1 探针复跑：`sweep_truncation_probe` 出 5 条记录，第 2 条 `cancelled` 为假；`sweep_anyio_probe` 的两行一致。
- **对照组真在测东西**：
  - 把检查挪到释放任务引用之后（M8），原生对照组因断言变红。
  - 把 anyio 的检查挪到取消域退出之后（M10），anyio 对照组因断言变红。
  - 让写锁检查恒返回真（M16），两个对照组都变红。
  - 让排队落点不投递取消（M17），9 种写法都报「任务没有以取消结束」。
  - 恢复 F1 的截断（M18）、让 `cancelled` 恒为真（M9），吞取消的那条用例都会变红。
- **与规格字面不同、但等价的一处**：4.1 说用 `gather(task, return_exceptions=True)` 等任务结束，实现用的是有上限的 `asyncio.wait`（F3 的要求）。两者都不会清掉任务上保存的 `_cancelled_exc`：gather 在 `return_exceptions` 模式下给被取消的子任务另造一个新的 `CancelledError`。所以「任务仍被引用时僵尸还在」这个条件是一样的，原生对照组能测出锁就是证据。
- **等待上限**：
  - 扫描器里的每次等待都有 60 秒上限，guard 用例 5 秒，收尾写库 2 秒，`_prepare_db` 最多重试 5 秒，sync 的 prepare 用 sqlite 默认的 5 秒忙等待。
  - 23 条变异里最慢的一条 51 秒，没有一条卡住。
- **时序**：检查结果取决于对象引用，不取决于时间。drain 用例里的 0.05～0.3 秒 sleep 有足够余量。本次没有观察到新用例偶发失败。
- **偏弱的地方**，都列为可优化项：
  - 「普通异常回滚」那条用例的数据断言，只靠关闭也能满足（M11 下它仍然通过）。M11 是靠回滚异常那条用例里的 `rollback_called` 抓到的。
  - `_wait_task_or_fail` 返回的是 `task.result()`，某些变异下会以非断言异常变红（M21）。

---

## 3. 必须修复项

### F1 A5 第 1 行的三条收尾用例和第 3 行的用例，变红的原因不是断言失败

**哪里错。**

- `tests/test_write_cancel_paths.py` 的 `_check_novel_follow_up`、`_check_exchange_follow_up`、`_check_chat_follow_up` 直接 `await asyncio.wait_for(收尾写库, timeout=2)`。收尾写库一报 `database is locked` 或者超时，异常就从检查函数里抛出，穿过 `sweep_cancel_points` 直接打断用例。
- `tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception` 用的是 `pytest.raises(RuntimeError)`。回滚异常一旦没被吞掉，向外的是 `OperationalError`，它不是 `RuntimeError`，于是直接漏出 `pytest.raises`。

规格 A5 要求这些用例「因断言失败而变红」；规格作者门禁里「七行都被断言失败发现」的说法也不成立。

**怎么复现。** 从 `backend/` 运行，跑完用留底复原：

```bash
cp utils/db_txn.py "${TMPDIR:-/tmp}/db_txn.py.bak"
.venv/bin/python -c "p='utils/db_txn.py'; s=open(p,encoding='utf-8').read(); open(p,'w',encoding='utf-8').write(s.replace('with contextlib.suppress(Exception):','with contextlib.suppress():',1))"
.venv/bin/python -m pytest -q -p no:cacheprovider --tb=line tests/test_db_txn_guard.py -k rollback_error
cp "${TMPDIR:-/tmp}/db_txn.py.bak" utils/db_txn.py
```

输出：`backend/tests/test_db_txn_guard.py:492: sqlite3.OperationalError: rollback failed`，然后是 `1 failed, 32 deselected`。

把替换换成 `'                await db.rollback()'` → `'                pass'`，再跑 `tests/test_write_cancel_paths.py -k succeeds`，输出三行 `.../aiosqlite/core.py:63: sqlite3.OperationalError: database is locked`，然后是 `3 failed, 10 deselected`。复原后 `db_txn.py` 的哈希是 `64af7490…472c`，与快照一致。

**后果。**

- 这几条用例确实会变红，缺陷本身能被发现，但不满足 A5 的判定口径：门禁只认断言失败。
- 三条收尾用例在第一个出问题的取消点就整个中断。之后的取消点、同一条用例里后面几个被扫的函数（比如 `write_step`、`_pause`）都不再检查，失败信息里也看不出是哪个取消点、哪一步收尾出的问题。
- 「2 秒内返回」超时时报的是 TimeoutError，同样不是断言失败。

**建议改法。** 见第 6 节的指令 1、2。

### F2 `docs/ARCHITECTURE.md` 的新小节把原有的后端概览吞了进去

**哪里错。** 新小节插在 `## FastAPI 后端`（第 156 行）的下一行。原来这一节没有 `###` 子标题，直接是「后端入口是 `backend/main.py`…」的导语，后面跟着模块表。现在：

```text
$ grep -n -E "^#{1,4} " docs/ARCHITECTURE.md   # 节选
156:## FastAPI 后端
158:### 数据库连接与取消保护
249:## 主创与审稿协作
```

按标题层级，「### 数据库连接与取消保护」这一节从第 158 行一直延伸到第 248 行。后端入口、模块表、官方体验的那些段落，在目录和渲染结构里都成了它的内容。

**后果。** 不符合 3.4「新增一小节（不超过 15 行）」；读文档的人会以为整张模块表属于「数据库连接」这一节。

**建议改法。** 见第 6 节的指令 3。

---

## 4. 可优化项（不影响通过，由作者决定）

1. **静态守卫补上别名和间接引用。** 2.10 那五种写法目前都能绕过守卫和 A1 的 grep。建议在 `_scan` 里：
   - 先收集绑定到 `aiosqlite` 模块的名字，包括 `import aiosqlite as X`，以及 `import aiosqlite.core` 绑定的 `aiosqlite`。
   - 凡是 `X.connect`、`X.core.connect` 形式的属性引用，不管有没有被调用，都拦。
   - `from aiosqlite[.core] import connect / Connection / *` 都拦。
   - `getattr(X, "connect")` 和 `X.Connection(`、`X.core.Connection(` 也拦。
2. **把「普通异常回滚」那条用例补强到能区分「回滚」和「只是关闭」。** 作用域里开一个多行游标、只取一行，然后抛普通异常；在测试里还持有那个异常对象的时候断言写锁空闲。2.9 的探针表明，裸连接在这种情况下会残留写锁，和业务里写事务中途抛 HTTPException 是同一回事。
3. **`drain` 只接受协程。** 传 Future 会报 `TypeError: a coroutine was expected`，而规格写的是「协程或可等待对象」。现有调用点全是协程，可以把文档字符串写成「协程」，也可以改用 `asyncio.ensure_future`。
4. **回滚失败目前被静默吞掉。** 回滚失败意味着可能还残留写锁，建议在吞掉之前记一条 `logger.warning`，只记异常类型。这不改变 3.1 第 6 条的行为。
5. **`test_connect_closes_when_rollback_is_cancelled_again` 的 `_wait_task_or_fail` 返回 `task.result()`。** 被测任务以别的异常结束时，用例会以那个异常变红，M21 下就是 `RuntimeError: original failure`。建议改成断言任务的结局。
6. **遗留，不在本次范围，供以后参考：**
   - `reserve` 补偿退款时如果自己抛异常，会顶掉 `CancelledError`（2.11）。
   - `discuss/engine.py::_avatar_try` 的 `cancelling()` 补丁已经多余。
   - anyio 取消域下，`drain` 的循环每轮都会被重新投递取消，相当于空转，旧版也一样。
7. **门禁脚本 `verify/check_mechanical.py` 不核对导入加在哪一行。** 本次我另外核对过，全部合格。如果以后复用这个脚本，可以把「紧跟第一处 `import aiosqlite`、缩进相同」也加进去。

---

## 5. 我做过的变异及结果

「因断言变红」包括 `AssertionError` 和用例主动调用的 `pytest.fail`；「非断言」指未捕获的业务异常从用例里漏出来。所有变异做完都复原了，哈希核对一致。

| ID | 改坏什么 | 跑的范围 | 结果 |
|---|---|---|---|
| M1 | 去掉回滚（A5 第 1 行） | 五个文件 | 41 条失败、30 条通过。30 个参数全部因断言变红；三条收尾用例**非断言**（`database is locked`） |
| M2 | 回滚被再次取消时不关闭（A5 第 2 行） | guard | 「再次被取消」因断言变红 |
| M3 | 回滚异常不吞（A5 第 3 行） | guard | **非断言**（`OperationalError: rollback failed`） |
| M4 | `drain` 改回旧行为（A5 第 4 行） | guard | 第五行用例因断言变红 |
| M5 | `drain` 不等内层结束（A5 第 5 行） | guard | 第四行、第五行、连续三次取消，3 条都因断言变红 |
| M6 | 一处改回 `aiosqlite.connect(`（A5 第 6 行） | static | 因断言变红，失败信息带行号 |
| M7 | 一处改成 `db = await` 形式（A5 第 7 行） | static | 因断言变红 |
| M8 | 原生取消模式：先释放任务引用、再做检查 | guard | 原生对照组因断言变红 |
| M9 | 记录里 `cancelled` 恒为真 | guard + core | 吞取消那条用例因断言变红 |
| M10 | anyio 模式：检查挪到取消域退出之后 | guard | anyio 对照组因断言变红 |
| M11 | 只在 `CancelledError` 时回滚 | guard | 2 条变红：回滚异常那条的 `rollback_called` 断言，再次取消那条主动 `pytest.fail`。普通异常那条仍然通过（可优化项 2） |
| M12 | 先关闭、后回滚 | 五个文件 | 39 条失败。30 个参数全部因断言变红；三条收尾用例**非断言** |
| M13 | `drain` 抛出时不带 `from exc` | guard | 第五行 `__cause__` 断言变红 |
| M14 | 内层成功时 `drain` 吞掉调用方的取消 | guard | 第四行和连续三次取消，都因断言变红 |
| M15 | 内层自己被取消时 `drain` 返回 None | guard | 第三行因断言变红 |
| M16 | 写锁检查恒返回真 | guard | 两个对照组都因断言变红 |
| M17 | 排队落点不投递取消 | guard | 9 种写法都因「任务没有以取消结束」断言变红 |
| M18 | 遇到被吞掉的取消就停止扫描（F1 回退） | guard | 吞取消那条用例因断言变红（`1 == 5`） |
| M21 | 回滚放进后台、不等它完成 | 五个文件 | 40 条失败。30 个参数全部因断言变红；三条收尾用例和「再次被取消」**非断言** |
| M22 | `trace.py` 漏替换 | core 两个参数 | `trace.log_event` 因断言变红，`save_message` 不受影响、仍然通过 |
| M23 | `exchange_store.py` 全部漏替换 | paths | 4 个 exchange 参数因断言变红；收尾用例**非断言**；novel 参数不受影响 |
| 绕过 | 临时文件里写五种别名和间接打开 | static + A1 | 全部没拦住（可优化项 1），文件已删 |

---

## 6. 给实现方的修改指令（可直接转发）

依据仍是 `02-spec.md` v1.0 和 `03-dispatch.md` 第一节的全部规矩。本轮只允许改三个文件：

- `backend/tests/test_write_cancel_paths.py`
- `backend/tests/test_db_txn_guard.py`
- `docs/ARCHITECTURE.md`

`impl/report.md` 只在末尾追加一节「返修 R2」。`backend/utils/db_txn.py`、`cancel_sweep.py`、另外两个路径测试文件、21 个替换过的文件、`CLAUDE.md` 一律不动，门禁会逐字节核对。

1. **`test_write_cancel_paths.py`：把收尾写库的失败变成断言失败。**
   - 加一个辅助函数：

     ```python
     async def _run_follow_up(awaitable):
         """执行收尾写库；任何异常或超时都记下来交给断言，不让它打断扫描。"""
         try:
             await asyncio.wait_for(awaitable, timeout=2)
         except Exception as error:  # 包括 TimeoutError 和 OperationalError
             return f"{type(error).__name__}: {error}"
         return None
     ```

   - 三个 `_check_*_follow_up` 都改成先调它，返回 `{"error": error, "value": ...}`。`value` 是原来的检查值，`error` 不为 None 时不再读值。
   - 三条用例对**每个**取消点断言 `error is None`，失败信息写出用例、被扫的函数、k、label 和 error；再断言值等于原来的期望（`run_token` 为空、`reserved` 调用数为 0、余额多 1）。
   - 检查函数不再抛异常，扫描就会走完全部取消点。最好把所有不合格的点收集起来，最后用一条断言一起报出。
2. **`test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception`：** 把 `pytest.raises(RuntimeError)` 换成：

   ```python
   caught = None
   try:
       asyncio.run(scenario())
   except BaseException as error:
       caught = error
   assert caught is original, f"向外抛的应是原异常，实际是 {caught!r}"
   ```

   其余断言不变。`test_connect_rolls_back_and_closes_on_plain_exception` 可以照同样的写法改，保持一致。
3. **`docs/ARCHITECTURE.md`：** 把「### 数据库连接与取消保护」这一节（标题、三条要点和前后的空行）原样挪到 `## FastAPI 后端` 这一节的末尾，紧挨在 `## 主创与审稿协作` 之前。文字一个字都不改；「后端入口是 `backend/main.py`…」这段导语恢复成紧跟在 `## FastAPI 后端` 后面。挪完用 `grep -n -E "^#{1,4} " docs/ARCHITECTURE.md` 确认：这个小节的标题到下一个标题之间不超过 15 行；与基线比，除了这 6 行之外没有别的差异（`git diff 19e4bd1 -- docs/ARCHITECTURE.md` 应当只有新增行）。
4. **自查**，从 `backend/` 运行，贴原始输出和退出码，取退出码时不接管道：
   1. 五个新测试文件全过、0 跳过。
   2. 把 `utils/db_txn.py` 复制到系统临时目录留底，做两次变异：
      - 把 `await db.rollback()` 换成 `pass`，跑 `tests/test_write_cancel_paths.py`，要求三条收尾用例都以 `AssertionError` 失败，失败信息里能看到取消点和 `database is locked`。
      - 把 `suppress(Exception)` 换成 `suppress()`，跑 `tests/test_db_txn_guard.py -k rollback_error`，要求以 `AssertionError` 失败。

      用 `--tb=line` 或 `--junitxml` 证明失败类型。每次做完都用留底覆盖回去，核对哈希是 `64af7490024afa2be22258185bcc75d6d295e1973f994a1d868e31555131472c`。
   3. A1、A2、A6 复跑一遍，结果应与本轮相同。
   4. 全量跑一次。那条偶发用例如果失败，单独复跑，两次结果都写进报告。
