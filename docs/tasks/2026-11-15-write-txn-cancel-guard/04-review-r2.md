# 写库取消保护 · 独立复核第 2 轮（复核返修 R1 之后）

本轮只核两件事：第 1 轮的两条必须修复项（F1、F2），以及本轮新增或改动的代码。范围以 `.cache/review/round1-fix.diff` 为准。依据仍是 `02-spec.md` v1.0；返修单 `06-fix-review-r1.md` 只用来确认本轮允许改哪些文件、应当做成什么样。实现方报告和规格作者的门禁结论，都只当线索。

所有命令都在新副本里跑，测试命令前加 `env -u ANTHROPIC_BASE_URL` 和 `-o faulthandler_timeout=60`，外面再套一层 `timeout`。贴出的输出里已删掉本机路径。

---

## 1. 结论

**通过。** 没有必须修复项。

- **F1 已修好。** 第 1 轮那 4 条用例在对应变异下现在都以 `AssertionError` 变红，失败信息里列出了被扫的函数、取消点 k、调用标签和原因。三条收尾用例会扫完全部取消点，再用一条断言一起报出。
- **F2 已修好。** 小节挪到了 `## FastAPI 后端` 的末尾。与基线相比只有 6 行新增、0 行删除，文字与上一轮逐字相同。
- **本轮新代码**：
  - `drain` 改用 `ensure_future`。对协程参数，行为与原来完全相同；现在也接受 Task 和 Future。
  - 静态守卫补齐了别名和间接写法，第 1 轮的 5 种绕过写法现在全部能拦住，仓库现状下没有误报。
  - 新补的用例都有区分力：本轮 30 个变异里，29 个被断言失败抓到；没被抓到的一个落在可优化项 1 说的那个缺口上。
  - 没有发现新的恒真断言、空转、挂死或时序依赖。
- **不该动的文件都没动。** 第 1 轮我复核过的 31 个文件里，`cancel_sweep.py`、另外两个路径测试文件、21 个替换文件、`CLAUDE.md` 共 25 个，哈希与第 1 轮逐个一致。另外 6 个文件，把 `round1-fix.diff` 反向打上之后，逐字节还原成第 1 轮的版本。也就是说，这份差异就是本轮的全部改动。

另有 4 条可优化项，都不影响通过，见第 6 节。

规格作者本轮门禁陈述的核对：

| 陈述 | 我的结果 |
|---|---|
| 只有返修单允许的 6 个文件有变化 | 属实（见上面最后一条） |
| 五个新测试文件 78 条全过 | 属实。各文件收集数是 guard 38、paths 13、core 17、misc 3、static 7 |
| A5 七行变异都以断言失败变红，没有非断言失败 | 属实。我本轮跑的 30 个变异里，没有一条用例是以非断言异常变红的 |
| `check_mechanical.py` 仍是 problems=0 | 属实 |
| `real_code_repro.py` 仍是 73 个取消点、0 处失败 | 属实 |

---

## 2. F1 的核验

### 2.1 按第 1 轮第 3 节的复现方法重做

从 `backend/` 运行。做之前把 `utils/db_txn.py` 留了底，做完用留底覆盖回去；复原后的哈希是 `6ec8ae41…c88459`，与实现方报告里本轮的最终值一致。

**回滚异常不吞**（`suppress(Exception)` 换成 `suppress()`），跑 `--tb=line -rf tests/test_db_txn_guard.py -k rollback_error`，退出码 1：

```text
E   AssertionError: 向外抛的应是原异常对象，实际是 OperationalError: OperationalError('rollback failed')
    assert OperationalError('rollback failed') is RuntimeError('original failure')
backend/tests/test_db_txn_guard.py:657: AssertionError: 向外抛的应是原异常对象，实际是 OperationalError: OperationalError('rollback failed')
FAILED tests/test_db_txn_guard.py::test_connect_swallows_rollback_error_and_keeps_original_exception
1 failed, 37 deselected in 0.05s
```

**去掉回滚**（`await db.rollback()` 换成 `pass`），跑 `--tb=line -rf tests/test_write_cancel_paths.py -k succeeds`，退出码 1。下面是节选：

```text
E   AssertionError: novel 取消后的收尾写库有不合格取消点：
      DbStepStore.append_usage 的取消点 k=2，调用标签 execute SELECT 1 FROM novels n JOIN users u ON u.username=n.username：收尾写库失败：OperationalError: database is locked
      DbStepStore.write_step 的取消点 k=2，……：收尾写库失败：OperationalError: database is locked
      novel.runner._pause 的取消点 k=2，……：收尾写库失败：OperationalError: database is locked
backend/tests/test_write_cancel_paths.py:474: AssertionError: novel 取消后的收尾写库有不合格取消点：
E   AssertionError: exchange 取消后的收尾写库有不合格取消点：
      exchange_store.load_running_exchange 的取消点 k=2，……（共 10 个点，k=2/5/8 ×3 个函数，外加 finish_model_call 的 k=11）
backend/tests/test_write_cancel_paths.py:520: AssertionError: exchange 取消后的收尾写库有不合格取消点：
E   AssertionError: chat 取消后的收尾退款有不合格取消点：
      agent_store.resolve_chat_conversation(state=default-missing) 的取消点 k=2，……（三种起始状态共 9 个点）
backend/tests/test_write_cancel_paths.py:554: AssertionError: chat 取消后的收尾退款有不合格取消点：
FAILED tests/test_write_cancel_paths.py::test_novel_cancel_then_cancel_novel_succeeds
FAILED tests/test_write_cancel_paths.py::test_exchange_cancel_then_settlement_succeeds
FAILED tests/test_write_cancel_paths.py::test_chat_conversation_check_cancel_then_refund_succeeds
3 failed, 10 deselected in 13.82s
```

从 `--junitxml` 解析出的不合格点：novel 3 个，exchange 10 个，chat 9 个。原因全部是 `收尾写库失败：OperationalError: database is locked`。

### 2.2 三条收尾用例会扫完全部取消点

在 `tests/` 下临时放了一个探针，把三个检查函数各包一层计数，在实现正确和去掉回滚两种状态下各跑一遍。跑完探针已删掉，`git status` 与开始时一致。

| 用例 | 实现正确时调用检查的次数 | 去掉回滚后调用检查的次数 | 去掉回滚后的结局 |
|---|---|---|---|
| novel | 24（= 7 + 7 + 10） | 24 | AssertionError，三个函数都有不合格点 |
| exchange | 48（= 15 + 14 + 19） | 48 | AssertionError，三个函数都有不合格点 |
| chat | 44（= 23 + 12 + 9） | 44 | AssertionError，三种起始状态都有不合格点 |

两种状态下检查函数被调用的次数相同，说明收尾写库失败之后扫描没有中断，后面的取消点和后面的函数都照常扫过了。每个点的期望值也没变：`run_token` 为空、`reserved` 调用数为 0、余额多 1。

### 2.3 返修单 A 的第 3、4 点和「通用要求」

- `test_connect_rolls_back_and_closes_on_plain_exception` 也改成了自己接住异常、断言是同一个对象。
- `_wait_task_or_fail` 改成断言任务的结局。第 1 轮的 M21（回滚放进后台、不等它完成）下，「再次被取消」那条现在报的是 `Failed: …任务以 RuntimeError: original failure 结束，预期正常结束`，不再是 RuntimeError 从用例里漏出来。
- 新增的 `_run_or_fail` / `_anyio_run_or_fail` / `_bounded_or_fail` 把意外的非断言异常转成带上下文的 `pytest.fail`；`AssertionError` 和 `pytest.fail` 自身的 `Failed` 都原样透出，不会被吞掉。
- 我把第 1 轮的 21 个变异全部重跑了一遍，加上本轮新增的 9 个、共 30 个（编号与第 1 轮一致，所以有缺号），见第 7 节。没有任何一条用例以非断言异常变红。

---

## 3. F2 的核验

```text
$ git diff 19e4bd1 --numstat -- docs/ARCHITECTURE.md
6       0       docs/ARCHITECTURE.md
$ grep -n -E "^#{1,4} " docs/ARCHITECTURE.md   # 节选
156:## FastAPI 后端
243:### 数据库连接与取消保护
249:## 主创与审稿协作
```

- 第 156 行 `## FastAPI 后端` 后面紧跟的，又是原来的「后端入口是 `backend/main.py`……」导语。
- 新小节从第 243 行开始，到下一个标题（第 249 行）之间是 5 行，没有超过 15 行。
- `round1-fix.diff` 里这一处删了 6 行、加了 6 行，两边的非空行逐字相同，所以文字一个字都没改。

---

## 4. 本轮新代码的审查

### 4.1 `backend/utils/db_txn.py`：`create_task` → `ensure_future`

- 本文件只改了这一行，`connect` 没有动。
- **对协程参数**：`ensure_future(coro)` 在运行中的事件循环里就是 `loop.create_task(coro)`，与原来的 `asyncio.create_task(coro)` 等价。所以第 1 轮关于 `_drain` 对各调用点影响的结论不受影响；现有调用点传的全是协程。实测 A6 仍是 `REAL_CODE_REPRO cancel_points=73 follow_up_failed=0`，退出码 0。全量结果见 4.5。
- **对 Task / Future**：`ensure_future` 原样返回对象本身。`shield` 保护的就是它；调用方被取消时，等它结束后再抛 `CancelledError`；它被别人取消时，走表格第 3 行。返回之前内层都已结束这一条仍然成立。
- 文档字符串里还写着「放进独立任务」，传进来的是 Task 或 Future 时这个说法不准确，见可优化项 4。

**配套用例。** 返修单要求两条，实际补了四条：Task 和 Future 各两行（没被取消、正常返回；等待期间被取消、内层正常返回）。

- 把实现改回 `create_task`（变异 E1）：
  - 「没被取消」的两条以 `Failed: …意外抛出 TypeError: a coroutine was expected…` 变红。
  - 「被取消」的两条以断言变红：`实际结局: []`，因为 drain 在调用方被取消之前就已经抛了 TypeError。
- 把 `drain` 改成不等内层结束（M5），或者改成吞掉调用方的取消（M14），后两条都以断言变红：`[('cancelled', False)]`、`[('returned', True)]`。
- 时序：两条「被取消」用例在取消之后做了一次 `await asyncio.sleep(0)`，然后断言内层还没结束。内层停在一个只有测试自己会触发的事件上，所以这条断言不依赖调度快慢；就算取消晚一轮才送到，`drain` 的循环也照样能处理。15 次重复运行全部通过。

### 4.2 `backend/tests/test_db_txn_static.py`：新扫描规则

**规则对照返修单 C，逐条都实现了：**

- 收集绑定名：`import aiosqlite [as X]`；`import aiosqlite.core`（绑定的是 `aiosqlite`）；`import aiosqlite.core as Y`；`from aiosqlite import core [as Z]`。
- 这些名字上的 `.connect` / `.core.connect`，不管有没有被调用，都算违规。
- `from aiosqlite[.core] import connect / Connection / *` 算违规。
- `getattr(<绑定名或 aiosqlite.core>, "connect")` 算违规。
- `<绑定名>.Connection(...)`、`<绑定名>.core.Connection(...)` 算违规；只引用不调用的不算。
- 原来的两条规则和防空转下限保留。

**仓库现状下的表现：**

- 非测试代码里只有 `import aiosqlite` 这一种导入形式（23 行），新规则报出 0 处。现在的 7 条用例全过，扫描 191 个文件、148 处 `db_txn.connect(`。
- 我在 `backend/` 下临时放了一个文件，写上第 1 轮那 5 种绕过写法。守卫逐行报出了 5 处，类别分别是 `unsafe-import`、`connect-attribute`、`core-connect-attribute`、`getattr-connect`、`connect-attribute`（partial），都带文件和行号。删掉之后重跑，7 条全过，`git status` 没有残留。

**误报和漏报**，在副本之外的临时目录里用同一套扫描函数实测：

- 合法写法都不报：`sqlite3.connect(...)`、`client.connect()`、`aiosqlite.Row`、`db: aiosqlite.Connection` 类型标注、`isinstance(db, aiosqlite.Connection)`、`hasattr(aiosqlite, "connect")`、`from aiosqlite import Row`。
- 会报的一处合法写法：`if TYPE_CHECKING: from aiosqlite import Connection` 会被当成违规。返修单就是这样规定的，所以不算缺陷，见可优化项 2。
- 漏报：
  - `import aiosqlite.cursor`（或 `aiosqlite.core` 以外的任何子模块）也会绑定 `aiosqlite` 这个名字，但扫描器没有记录。所以只有这种导入的文件里，`functools.partial(aiosqlite.connect, ...)` 拦不住。直接调用 `aiosqlite.connect(...)` 仍被原规则拦住。见可优化项 1。
  - `importlib.import_module("aiosqlite").connect`、`__import__`、`vars(aiosqlite)["connect"]` 这类刻意规避的写法拦不住，在预期之内。

**证明用例 `test_scanner_catches_alias_and_indirect_forms`：**

- 它在 `tmp_path` 里写一个 30 行的临时源文件，用与 backend 门禁相同的 `_scan_paths` 去扫，再与预期**精确比对**：漏报和误报都会让它失败，所以它也在证明那几条不该报的写法（各种导入本身、只引用类型、动态 getattr）确实不报。
- 变异下的表现：
  - 去掉 `.connect` 属性规则（S1）、忽略 `as` 别名（S2）、去掉 getattr 规则（S3）、不再识别 `aiosqlite.core` 的 from 导入（S5）、扫描结果清空（S7），都让它以断言失败变红，失败信息里有漏报的行。
  - 把 `from aiosqlite import core` 也当成违规（S4），它报出两条误报，也变红。
  - 不再检查名字是否绑定到 aiosqlite（S8），它没有变红。这一项是 backend 门禁 `test_no_aiosqlite_aliases_or_indirect_connection_openings` 抓到的：`db_txn.connect(` 等大量合法写法都被误报。
  - **只有一个变异没被抓到：** 把「构造连接」规则放宽成「任何对象的 `.Connection(...)` 都算」（S6），7 条用例全过。证明文件里没有「无关对象上的 `.Connection(...)`」这种反例，仓库里也没有这样的调用。见可优化项 1。

### 4.3 `backend/tests/test_db_txn_guard.py`：新补的用例

**`test_plain_exception_rollback_releases_lock_before_close`（返修单 D）。** 作用域里 `BEGIN IMMEDIATE`、开多行查询只取一行、`UPDATE`，然后抛普通异常。

- 测试一直持有这个异常对象：它是测试函数里的局部变量 `original`，traceback 里的游标也就一直活着。在这个状态下，断言封装连接的写锁空闲、数据没变、连接已关；同样的写法换成裸连接，断言写锁不空闲。两个连接用的是不同的库文件，互不干扰。
- 变异下的表现：
  - 只在 `CancelledError` 时回滚（M11）：它以 `AssertionError: db_txn.connect 在普通异常后、异常对象仍被引用时写锁不空闲` 变红。
  - 写锁检查恒返回真（M16）：它的裸连接对照组以断言变红。这说明它不会在检查函数坏掉的情况下空转。
  - 去掉回滚（M1）、先关闭后回滚（M12）、回滚放进后台（M21）：它也都以断言变红。
- 裸连接那一侧的僵尸，在用例结束后要等 gc 才会释放，原因是异常的 traceback 和测试函数的栈帧之间有引用环。占的只是这条用例自己 `tmp_path` 里的库文件，对其他用例没有影响。15 次重复运行全部通过。

**其他改动：**

- 原来所有 `asyncio.run` / `anyio.run` 都换成了 `_run_or_fail` / `_anyio_run_or_fail`，`pytest.raises` 换成了「接住异常再断言是同一个对象」。
- 这些辅助函数只把 `Exception` 和 `CancelledError` 转成 `pytest.fail`，`AssertionError` 原样透出，`NoCancelPointsFound` 和 `CheckNotCompleted` 都是 `AssertionError` 的子类，也透出。所以不会把扫描器的断言类结论吞掉。

### 4.4 `backend/tests/test_write_cancel_paths.py`

- `_run_follow_up` 保留了 2 秒上限，接住 `Exception`（含 TimeoutError），把异常转成一段文字；返回的是字符串，不持有异常对象，也就不会让 traceback 里的游标继续活着。
- `_follow_up_failures` 对每个点核对：以取消结束、检查函数跑完、结果形状正确、没有错误、值等于期望。三条用例在全部扫描结束后用一条断言汇总报出，失败信息格式符合返修单。
- 读库的辅助函数（`_chat_balance` 等）仍在 `try` 之外。但库是 WAL 模式（`database.py` 第 159 行），读不会被残留的写锁挡住，实测也没有出过问题，不另列。

### 4.5 有没有新的恒真断言、空转、挂死或时序依赖

- **恒真**：有几条在前面已有等待保证的情况下必然成立，比如 `assert inner.done()`、`assert future.done()`。它们无害，每条用例里真正承重的断言（`outcomes == [("cancelled", True)]`、`result is value`、写锁、数据）都有对应的变异能打红，所以不算空转。
- **挂死**：新代码里每一处等待都有上限（事件和任务 5 秒，收尾写库 2 秒）。30 个变异里最慢的一条 66 秒，没有一条卡住。
- **时序**：没有依赖墙钟时间的断言。新 guard 用例重复跑 15 次全部通过。
- **本机环境依赖（A7）**：本轮测试有新增，所以复跑了一次。做法同第 1 轮：一份不带 `.git`、`node_modules`、`.venv` 的副本，`git rev-parse` 报 `not a git repository`。五个新文件 `78 passed in 34.61s`，退出码 0。证明用例的临时文件写在 `tmp_path` 里，不依赖仓库之外的路径。
- **A1 / A2**：复跑结果分别是 0 / 148，以及 `CHECK_MECHANICAL files=21 replaced=148 base_sites=148 problems=0`，退出码 0，与上一轮相同。
- **全量**：本轮有一处运行时代码改动，所以跑了一遍全量，从 `backend/` 运行：

  ```text
  $ .venv/bin/python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=120 -rfEs
  8630 passed, 47 warnings in 567.85s (0:09:27)
  full_exit=0
  ```

  8630 = 8552 + 78，0 失败，0 跳过。警告数与第 1 轮相同。那条已知的偶发用例这次没有失败。

---

## 5. 必须修复项

无。

---

## 6. 可优化项（不影响通过，由作者决定）

1. **静态守卫还剩两个小缺口。**
   - `import aiosqlite.<core 以外的子模块>`（比如 `import aiosqlite.cursor`）也绑定了 `aiosqlite` 这个名字，但 `_collect_aiosqlite_bindings` 没有记录，所以只有这种导入的文件里，`partial(aiosqlite.connect, ...)` 拦不住。改法：凡是 `alias.name` 以 `aiosqlite.` 开头、又没写 `as` 的，都按 `aiosqlite` 记录绑定。
   - 证明用例里缺少「无关对象上的 `.connect` / `.Connection(...)`」反例。比如 `sqlite3.connect('x')`、`client.connect()`、`other.Connection()`，加进 `_PROOF_CASES`、期望为空即可。这样 S6、S8 这类放宽规则的变异，在证明用例里就能直接抓到。
2. **`from aiosqlite import Connection` 只做类型标注时也会被拦**，与 `aiosqlite.Connection` 只做标注不拦的口径不一致。这是返修单 C 明确规定的，这次不必改。以后如果有人要写 `if TYPE_CHECKING: from aiosqlite import Connection`，可以改成只拦「导入的 `Connection` 名字被调用」。
3. **`_run_or_fail` 一类辅助函数用了 `pytrace=False`。** 失败时只剩一行异常类型和消息，看不到 traceback，排查起来要多一步。可以保留调用栈，或者把原异常的 traceback 摘要拼进失败信息。
4. **`drain` 的文档字符串**（模块头第 6 行、函数里第 37 行）还写着「放进独立任务」，传进来的是 Task 或 Future 时不准确。可以改成「包成任务（已是 Task 或 Future 则直接使用）」。

---

## 7. 我做过的变异及结果

方法与第 1 轮相同：

1. 改之前留底。
2. 用文本替换改坏，锚点恰好命中一次。
3. 跑对应的测试，用 `--junitxml` 逐条记下失败类型。
4. 用留底覆盖回去，核对哈希。

每条命令 300 秒上限，最慢 66 秒。30 个变异全部复原，哈希一致。所有变异做完后，6 个改动文件反向打上 `round1-fix.diff`，又逐字节还原成第 1 轮的版本。

「断言」包括 `AssertionError` 和用例主动调用的 `pytest.fail`。本轮**没有任何一条非断言失败**。

| ID | 改坏什么 | 范围 | 结果 |
|---|---|---|---|
| M1 | 去掉回滚（A5 第 1 行） | 五个文件 | 42 条失败、36 条通过。30 个参数和三条收尾用例全部因断言变红；D 用例、回滚异常、再次取消也变红 |
| M2 | 回滚被再次取消时不关闭（A5 第 2 行） | guard | 「再次被取消」因断言变红。参数透传那条报 `Failed: …TypeError`，是我改写成 `await` 引入的副作用 |
| M3 | 回滚异常不吞（A5 第 3 行） | guard | **现在因断言变红**（上一轮是非断言） |
| M4 | `drain` 改回旧行为（A5 第 4 行） | guard | 第五行因断言变红 |
| M5 | `drain` 不等内层结束（A5 第 5 行） | guard | 5 条因断言变红，含两条新的 Task / Future 用例 |
| M6 | 一处改回 `aiosqlite.connect(`（A5 第 6 行） | static | 原规则和新规则两条都因断言变红 |
| M7 | 一处改成 `db = await` 形式（A5 第 7 行） | static | 因断言变红 |
| M8 | 原生取消模式：先释放任务引用、再做检查 | guard | 原生对照组变红 |
| M9 | 记录里 `cancelled` 恒为真 | guard + core | 吞取消那条用例变红 |
| M10 | anyio 模式：检查挪到取消域退出之后 | guard | anyio 对照组变红 |
| M11 | 只在 `CancelledError` 时回滚 | guard | **D 用例因断言变红**，另有 2 条变红 |
| M12 | 先关闭、后回滚 | 五个文件 | 40 条失败。30 个参数、三条收尾用例、D 用例全部因断言变红 |
| M13 | `drain` 抛出时不带 `from exc` | guard | `__cause__` 断言变红 |
| M14 | 内层成功时 `drain` 吞掉调用方的取消 | guard | 4 条因断言变红，含两条新的 Task / Future 用例 |
| M15 | 内层自己被取消时 `drain` 返回 None | guard | 第三行变红 |
| M16 | 写锁检查恒返回真 | guard | 两个对照组和 D 用例的对照组都变红 |
| M17 | 排队落点不投递取消 | guard | 9 种写法都变红 |
| M18 | 遇到被吞掉的取消就停止扫描 | guard | 吞取消那条用例变红 |
| M21 | 回滚放进后台、不等它完成 | 五个文件 | 41 条失败，全部是断言或 `pytest.fail`；「再次取消」那条现在是 `pytest.fail`，不再是 RuntimeError 漏出 |
| M22 | `trace.py` 漏替换 | core 两个参数 | `trace.log_event` 因断言变红 |
| M23 | `exchange_store.py` 全部漏替换 | paths | 4 个 exchange 参数和 exchange 收尾用例**全部因断言变红**（上一轮收尾用例是非断言） |
| E1 | `drain` 改回 `create_task` | guard | 4 条新用例变红：两条 `pytest.fail`（TypeError），两条断言 |
| S1 | 去掉 `.connect` 属性规则 | static | 证明用例变红（有漏报） |
| S2 | 忽略 `import ... as` 的别名 | static | 证明用例变红 |
| S3 | 去掉 getattr 规则 | static | 证明用例变红 |
| S4 | `from aiosqlite import core` 也当违规 | static | 证明用例变红（有误报） |
| S5 | 不再识别 `from aiosqlite.core import` | static | 证明用例变红 |
| S6 | 任何对象的 `.Connection(...)` 都算构造连接 | static | **没被抓到**（可优化项 1） |
| S7 | 扫描结果清空 | static | 证明用例变红 |
| S8 | 不检查名字是否绑定到 aiosqlite | static | backend 门禁变红（`db_txn.connect` 等合法写法被误报）；证明用例没有变红（可优化项 1） |
| 手工 | `backend/` 下临时放第 1 轮那 5 种绕过写法 | static | 5 处全部报出，带文件和行号；文件删除后 7 条全过 |

---

## 8. 给实现方的修改指令

本轮没有必须修复项，不需要返修。第 6 节的可优化项如果作者决定要做，范围都只在 `backend/tests/test_db_txn_static.py`、`backend/tests/test_db_txn_guard.py`，以及 `backend/utils/db_txn.py` 的文档字符串。
