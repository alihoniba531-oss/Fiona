# 写库取消保护 · 调查记录

2026-11-15，基线 main `19e4bd1`。运行环境：Python 3.14.6、SQLite 3.53.3、aiosqlite 0.22.1、anyio 4.14.2、starlette 1.3.1、fastapi 0.136.1、uvicorn 0.47.0。

本文件回答三件事：这个问题到底在什么条件下出现；后端里哪些写事务会碰上；怎么修、修多大。所有结论都有同目录 `verify/` 下的脚本和输出可以复跑；凡是推断而不是实测的地方都单独标明。

背景见 `docs/tasks/2026-11-14-agent-group/verify/lock-root-cause.md`：讨论群第一期查实，写事务被取消后，已经关闭的连接可能继续占着写锁，收尾代码等满 5 秒后报 `database is locked`。

## 1. 结论

1. 问题在讨论群之外真实存在。在 main 的代码上，书斋、分身交流、自带 Claude 的聊天三条路径都能确定性复现：取消落在某条查询上之后，紧跟着的收尾写库报 `database is locked`（第 5 节）。
2. 触发条件比原记录写的更具体，也多出一种情形（第 2 节）。原记录说的「查询已执行、结果未取走」只是其中一种；另一种是「多行查询只取一行、游标没关」，窗口宽得多，好在全库目前没有这种写法。
3. 「客户端断开会取消请求」只对流式接口成立。普通接口在客户端断开后照常跑完，不会被取消（第 3 节，实测）。所以 `database.py`、`novel/service.py` 里绝大多数写事务不在取消路径上；真正暴露的是后台任务和聊天流里用 `task.cancel()` 取消的子任务。
4. 写锁挂多久，取决于那个取消异常活多久。只要被取消的任务对象还被人拿着（局部变量、任务登记表都算），锁就一直在（第 2.3 节）。书斋的 `cancel_novel` 正是拿着任务对象去退款的，所以一旦撞上就必然失败，不需要等垃圾回收。
5. 修法有两层，任何一层单独都够用（第 7 节）。推荐做法是在「打开连接」这一层统一加一条规则：有异常离开连接作用域时，先回滚再关闭。它不改变任何既有行为，改动是纯机械替换。原型已在 main 的副本上验证：复现归零（第 7.3 节）。
6. `NovelBilling._drain` 有一个独立的小问题：调用方已被取消、里面又抛了普通异常时，取消会丢（第 6 节，实测）。讨论群是在调用处补的，书斋这边没有补。

## 2. 机制

以下各条都来自 `verify/mechanism_probe.py` 与 `verify/mechanism_probe2.py`。这两个脚本不依赖项目代码：它们对 9 种事务写法，把取消依次落在事务里的每一次 aiosqlite 调用上，记录取消之后新连接能不能立刻拿到写锁。输出在 `verify/mechanism_probe.out.txt`、`verify/mechanism_probe2.out.txt`。

### 2.1 什么情况下连接关了、写锁还在

连接关闭的那一刻，同时满足两条：

- 连接上有一个没提交也没回滚的写事务。显式的 `BEGIN IMMEDIATE` 算，没写 `BEGIN`、由第一条写语句隐式开启的也算。
- 还有一个活着的游标，握着一条没取完的取行语句。`SELECT` 算，带 `RETURNING` 的写语句也算；语句必须至少返回了一行。

这时 `close()` 不生效，连接变成「僵尸」，写事务不回滚、写锁不放，直到那个游标被销毁。

反过来，下面这些情况不会残留写锁（都实测过）：

| 情况 | 结果 |
|---|---|
| 事务里只有写语句（不带 `RETURNING`） | 不残留 |
| 查询用的是 `execute_fetchall`（在工作线程里取完，不留游标） | 不残留 |
| 连接上没有写事务，只查询 | 不挡别人写入 |
| 查询一行都没返回 | 不残留（在真实代码的复现里观察到：同一条查询，表里没有对应行时不残留，有行时残留） |
| 关闭之前已经回滚过 | 不残留，即使那个游标还活着 |

### 2.2 取消怎样留下这样一个游标

**情形一：结果已交回、任务还没被唤醒。** aiosqlite 把语句交给工作线程执行，结果经 `call_soon_threadsafe` 交回事件循环并写进一个 Future，等待它的任务要到下一轮事件循环才被唤醒。如果 `task.cancel()` 恰好在这一轮里到达，任务醒来收到的是 `CancelledError`，而那个 Future 里已经装着原生游标，没人关它，取消异常的调用栈又一直引用着它。

- 窗口只有一轮事件循环，所以罕见；机器越忙，一轮里排队的回调越多，越容易撞上。
- 写成 `async with db.execute(...) as cursor` 也没用：游标还没交到 `async with` 手里。
- 取消如果在语句还没出结果时到达，Future 会被取消，之后出来的结果被丢弃，不残留。

**情形二：多行查询只取一行，游标没关。** 写成 `cursor = await db.execute("SELECT ...")` 再 `fetchone()`，而查询结果不止一行，这个游标就一直握着语句。之后事务里任何一处被取消，都会残留写锁。窗口是事务剩余的全部时间。

全库清点（第 4 节）：非测试代码里 `cursor = await db.execute(取行语句)` 这种写法共 9 处，全部在书斋和讨论群的计费模块里，查询条件都是主键或聚合，只可能返回一行，而且都跑在受保护的任务里。所以情形二目前没有实例，但没有任何东西阻止以后有人写出来。

### 2.3 写锁挂多久

锁一直挂到那个游标被销毁，也就是引用它的取消异常被销毁。实测（`mechanism_probe2.py` B 部分）：

| 时刻 | 新连接能否拿到写锁 |
|---|---|
| 任务自己的 `finally` / `except` 里（取消异常还在向外传播） | 拿不到 |
| `await gather(task, return_exceptions=True)` 之后，任务对象仍被局部变量引用 | 拿不到 |
| 任务对象只被一个列表引用（相当于任务登记表） | 拿不到 |
| 任务对象已经没人引用 | 拿得到，不需要垃圾回收 |

原因是被取消的任务把取消异常存在自己身上，`gather(return_exceptions=True)` 返回的是它新建的一个异常，不会把任务身上那个取走。

这解释了为什么收尾代码最容易中招：它们恰好在「取消异常还活着」的时候去写库。讨论群当时出问题的 `cancel_group`、书斋的 `cancel_novel`，都是 `task.cancel()` → `gather` → 紧接着退款，全程拿着任务对象。

### 2.4 经 anyio 投递的取消会避开情形一

anyio 的取消域在投递取消时会检查任务正在等的 Future：如果它已经有结果，这一轮就不取消，下一轮再试（`anyio/_backends/_asyncio.py` 的 `_deliver_cancellation`）。实测（`mechanism_probe2.py` A 部分）：经 anyio 取消时，情形一的 8 种写法全部不残留写锁；情形二仍然残留。

这一点决定了哪些路径真的暴露，见下一节。它是 anyio 4.14.2 的实现细节，不是它对外承诺的行为。

### 2.5 两种修法分别验证

同一批写法、同一批取消点（`mechanism_probe2.py` C、D 部分）：

| 修法 | 原生取消（结果已交回） | 原生取消（语句还在排队） | anyio 取消 |
|---|---|---|---|
| 连接层回滚：有异常离开连接作用域时先回滚再关闭 | 0 处残留 | 0 处残留 | 0 处残留 |
| 受保护任务：整个事务放进独立任务，屏蔽取消，跑完再交还 | 0 处残留，取消都送达 | 未单测 | 未单测 |

不加任何保护时，同一批取消点里有 10 处残留写锁（`mechanism_probe.out.txt` 末行）。

## 3. 谁会取消

### 3.1 客户端断开

`verify/disconnect_probe.py` 按 `main.py` 的中间件结构（一个纯 ASGI 中间件、CORS、三层 `@app.middleware("http")`）搭了一个最小应用，用项目同版本的框架起在本机端口上，请求发出 0.3 秒后直接关掉套接字：

```
plain:   started -> finished      普通 JSON 接口：照常跑完，不取消
stream:  started -> CANCELLED     流式接口，已吐出第一段：取消
stream0: started -> CANCELLED     流式接口，第一段还没吐出：取消
```

流式接口的取消来自 Starlette 的 `StreamingResponse`（uvicorn 报的 ASGI 规格是 2.3，走的是「监听断开 + 取消任务组」那条分支），也就是经 anyio 投递。

后端里返回流式响应的只有三处：`routers/chat.py` 两处（聊天）、`routers/voice.py` 一处（语音合成，不写库）。

### 3.2 代码里主动取消

非测试代码里的 `.cancel()` 共 19 处（`grep -rn "\.cancel()"`，不含 `scripts/`），按用途分：

| 取消的是什么 | 位置 | 取消的方式 | 被取消的任务写不写库 |
|---|---|---|---|
| 书斋写作任务 | `novel/runner.py` `cancel_novel` | `task.cancel()` | 写，密集 |
| 讨论群任务 | `discuss/runner.py` `cancel_group` | `task.cancel()` | 写，已有保护 |
| 分身交流任务 | `services/exchange_service.py` `cancel_exchange` | `task.cancel()` | 写 |
| 分身交流里的模型调用 | `services/exchange_service.py` `_generate_while_authorized` | `task.cancel()` | 只读轮询 |
| 工作室调度器的作业 | `studio/scheduler.py` `StudioScheduler.close` | `task.cancel()`，只在关停时 | 写 |
| 全部应用级后台任务 | `utils/background_tasks.py` `shutdown_background_tasks` | `task.cancel()`，只在关停时 | 见第 5 节 |
| 书斋并行讨论里的兄弟调用 | `novel/deliberation.py` `_gather_phase` | `task.cancel()` | 计费在受保护任务里；步骤写入走 `DbStepStore.transaction` |
| 聊天流里带心跳等待的子任务 | `services/chat_service.py` 两处、`services/claude_agent.py` `_wait_task` | `task.cancel()`，在流被 anyio 取消时触发 | 其中 `_ensure_active_conversation` 写 |
| 危机分级任务 | `routers/chat.py` | `task.cancel()` | 不写库 |
| 定时器、域名解析 | `utils/safe_http.py`、`byok/client.py`、`byok/url_safety.py` | — | 与数据库无关 |

### 3.3 超时

`asyncio.wait_for` 共 18 处。逐个看过被包住的协程：模型或外部接口调用、放到线程里的同步函数、子进程、健康检查的只读查询、分身交流的只读轮询。没有一处包住写事务。

### 3.4 小结

| 取消来源 | 怎么投递 | 情形一（一轮事件循环的窗口） | 情形二（游标没关） |
|---|---|---|---|
| 普通接口 + 客户端断开 | 不取消 | 不会发生 | 不会发生 |
| 流式接口 + 客户端断开，流里直接 `await` 的写库 | anyio | 被 anyio 避开 | 会，但全库没有这种写法 |
| 流式接口里另开的子任务，被 `task.cancel()` | 原生 | 会 | 会 |
| 后台任务被 `task.cancel()`（暂停、删除、停止、关停） | 原生 | 会 | 会 |

## 4. 清点：全站写事务

`verify/txn_inventory.py` 用语法树扫描 `backend/` 下全部非测试代码，对每个函数按源码顺序列出它在连接上做的事，并把「把连接传给别的函数」的调用就地展开。完整结果在 `verify/inventory.19e4bd1.txt`（每个写事务一行：语句序列、每条语句处在哪种回滚保护里、风险标记）。

总数：

- 直接调用 `aiosqlite.connect(` 的地方 148 处，分布在 21 个文件里（`grep` 计数）；另有 3 个模块级封装：`novel.store_db.get_db`、`discuss.store.get_db`、`studio.store.connection`。
- 自己打开连接的函数 319 个，其中写事务 202 个。
- 同步的 `sqlite3.connect` 6 处（`intent_router.py`、`mode_switcher.py`、`migrate.py`、`analyze.py`、`studio/store.py` 一处、一个脚本）。它们在线程里一口气跑完，不存在「语句跑完、协程没醒」这个窗口，不在本问题范围内。

按「出异常时有没有回滚」分：

| 类别 | 模块（写事务数） | 被取消时 |
|---|---|---|
| 已有「任何异常都回滚」 | `song/jobs.py`（5）；`studio/*` 里用 `connection(transaction=True)` 的函数（53）；`discuss/store.py` 的 `run_write` | 不残留 |
| 整个事务在受保护任务里 | `novel/billing.py`（3）、`discuss/billing.py`（6）、讨论群经 `run_write` 的全部写入 | 不残留 |
| 主体有回滚，但开头的令牌核对在回滚范围之外 | `novel/store_db.py` 的 `DbStepStore.transaction()`（`DbStepStore` 自己 5 个方法经它写库，`novel/runner.py` 里 9 处、`novel/service.py` 里 1 处直接用它） | 取消落在令牌核对那条查询上时残留 |
| 只有 `except Exception` 的回滚，接不住取消 | 几个迁移函数（只在启动时跑） | 残留 |
| 没有回滚，写事务里有查询 | `database.py`（28，含只在启动时跑的 `init_db`）、`novel/service.py`（16）、`agent_store.py`（8）、`exchange_store.py`（7）、`novel/runner.py`（6，多数就是上一行的令牌核对）、`song/store.py`（3）、`byok/store.py`（2）、`studio/sources.py`（1：`_save_snapshot`，用的是不带事务标志的 `connection()` 再手写 `BEGIN IMMEDIATE`）、`trace.py`（1）、`manage_strawberries.py`（1，命令行脚本） | 残留 |
| 没有回滚，但写事务里没有查询 | 53 个：21 个只有写语句（如 `update_profile`、`mark_upload_cleanup_done`），32 个的查询都在写事务开始之前或提交之后 | 不残留 |

扫描给 91 个写事务打了风险标记。去掉 12 个实际有保护的（计费 9 个在受保护任务里，另 3 个是下面说的误报），剩 79 个：上表「没有回滚，写事务里有查询」的 73 个，加 `novel/store_db.py` 的 6 个。它们的典型写法是：

```python
async with aiosqlite.connect(DB_PATH, timeout=SQLITE_BUSY_TIMEOUT) as db:
    await db.execute("BEGIN IMMEDIATE")
    if not await _users_exist(db, user_a, user_b):   # 查询
        await db.rollback()
        return False
    await db.execute("INSERT ...")
    await db.commit()
```

扫描的局限：语句文本在运行时才拼出来的地方按「可能是查询」处理；同名函数靠名字解析，个别地方会连错（已知误报：`studio/store.py` 的 `cas_job`、`studio/kb_trial.py` 的 `_final_attempt`、`discuss/service.py` 的 `start.operation`，三处实际都有保护或只读）。这张表用来定范围和排优先级，不作为验收依据；验收靠第 5 节那种在真实代码上的取消点扫描。

## 5. 哪些写事务真的在取消路径上

`verify/callgraph.py` 从各个取消入口出发沿调用关系找能走到的写事务，结果在 `verify/callgraph.19e4bd1.txt`。下面是结合第 3 节之后的分档；每一档里的函数我都对着源码看过调用链。

### 第一档：后台任务被原生取消，取消后立刻有收尾写库

和讨论群出事时的结构相同。

**书斋写作任务。**

- 被取消的：`novel/runner.py` 的 `_run`。它的写库几乎都经 `DbStepStore.transaction()`，开头那条令牌核对查询在回滚范围之外（`novel/store_db.py`）；另有 `_start_novel_locked` 等几处直接写。
- 谁取消：`cancel_novel`。调用它的有暂停、删除、改稿、重做、升级结构、注销账号、应用关停。
- 取消之后：`cancel_novel` 拿着任务对象，立刻 `NovelBilling.refund_reserved()` 再清令牌；任务自己的 `finally` 也做同样的两件事。
- 撞上时的后果：这次操作卡 5 秒后报错（接口 500），预扣没退、令牌没清；期间全站其他写入被挡。
- 复现：是，见下表第 1 行。

**分身交流任务。**

- 被取消的：`services/exchange_service.py` 的 `run_exchange`，写库在 `exchange_store.py` 的 `load_running_exchange`、`reserve_model_call`、`finish_model_call`，都没有回滚。
- 谁取消：`cancel_exchange`（用户停止、隐藏分身、关停）。
- 取消之后：`run_exchange` 在 `except CancelledError` 里跑 `_settle_cancelled_exchange` → `stop_and_discard_reserved_calls`。
- 撞上时的后果：结算失败，预留的调用没有释放。
- 复现：是，见下表第 2 行。

### 第二档：聊天流里被原生取消的子任务

**自带 Claude 的聊天。** `services/claude_agent.py` 的 `_stream_claude_agent` 把 `_ensure_active_conversation`（→ `agent_store.resolve_chat_conversation`，`BEGIN IMMEDIATE` 之后有多条查询）放进子任务，用 `_wait_task` 边等边发心跳；流被取消时 `_wait_task` 的 `finally` 对它调 `task.cancel()`。随后 `run_chat` 的收尾在屏蔽取消的状态下执行 `refund_strawberries` 和 `log_event`。

- 撞上时的后果：这一条回复预扣的草莓退不回去（代码会记 `refund_failed`），埋点丢失，全站写入被挡约 10 秒。
- 复现：函数级，是，见下表第 3 行。没有在完整的聊天请求上复现。

讨论群里分身读库的那条路径（`discuss/avatar.py`）上一单已经包进受保护任务。

### 第三档：只在应用关停时被原生取消

- 聊天后处理任务（`chat-postprocess`）：`extract_and_update` → `agent_store.get_memory_snapshot`、`update_memory`、`database.update_profile`、`update_time_tag_prefs`；`detect_matches_and_save` → `save_match`、`save_pending_match`、`upsert_user_state`。
- 工作室调度器和它派出的作业：`database.save_studio_notice`、`agent_store.resolve_chat_conversation`、`database.save_message`（写提醒消息），`studio/store.py` 的作业状态写入（已有回滚保护）。
- 写歌轮询器（已有回滚保护）、上传清理（只有写语句）。

撞上时的后果：关停流程里排在后面的收尾写库各卡 5 秒后失败。进程反正要退出，影响小。

### 第四档：聊天流里直接等待的写库

`run_chat` 里直接 `await` 的 `save_message`、`refund_strawberries`、`resolve_chat_conversation`、`log_event` 等。取消经 anyio 投递，情形一被避开；情形二的写法全库没有。所以现在不暴露，但这靠的是 anyio 的实现细节和「恰好没人这么写」。

### 第五档：普通接口

`database.py` 的大部分函数、`novel/service.py` 的 16 个、`agent_store.py` 的其余函数、`byok/store.py`、工作室的接口函数。客户端断开不会取消它们。它们是受害的一方：别处留下僵尸写锁时，它们的写入等 5 秒后报错。

### 在真实代码上的复现

`verify/real_code_repro.py` 在 main 的代码上（临时库，不碰真实数据）对下面每个写函数做取消点扫描：取消落在「结果已交回、任务未唤醒」，像真实代码那样用 `gather(return_exceptions=True)` 等任务结束，然后在任务对象仍被引用的状态下执行真实的收尾写库。忙等待调成 0.3 秒只为跑得快，真实配置是 5 秒。输出在 `verify/real_code_repro.19e4bd1.out.txt`。

| # | 被取消的写函数 | 取消之后执行的收尾写库 | 取消点 | 收尾报 `database is locked` |
|---|---|---|---|---|
| 1 | `DbStepStore.append_usage`（书斋记步骤用量） | `NovelBilling.refund_reserved` | 7 | 1（令牌核对那条查询） |
| 2 | `exchange_store.reserve_model_call` | `stop_and_discard_reserved_calls` | 10 | 1 |
| 3 | `agent_store.resolve_chat_conversation` | `database.refund_strawberries` | 22 | 4 |
| 4 | `agent_store.get_memory_snapshot` | `database.refund_strawberries` | 12 | 3 |
| 5 | `database.save_message` | `database.refund_strawberries` | 15 | 3 |
| 6 | `trace.log_event` | `database.refund_strawberries` | 7 | 1 |
| | 合计 | | 73 | 13 |

失败的 13 处全部是返回了至少一行的查询；写语句、提交、关闭、没有返回行的查询上都不失败，和第 2 节的机制一致。

第 1、2 行是函数级的复现，没有走完整的暂停接口和停止接口；但 `cancel_novel` 和 `run_exchange` 在取消之后做的正是表里第三列那一步。

### 发生的可能性

没有线上数据，下面是推断。情形一要求取消落在特定查询之后的那一轮事件循环里。讨论群的测试里约 340 次出现一次，是因为测试在任务刚启动、正密集写库时就取消它。真实使用中，书斋和分身交流的任务大部分时间在等模型返回，单次暂停撞上的概率远低于这个数；最容易撞上的是「刚点开始就点暂停」「刚建好就删除」和重启恢复这类任务正在连续写库的时刻。概率低，但后果是全站写入卡住加上一次计费或状态不一致，而且出现时很难从现象反推原因。

## 6. `NovelBilling._drain` 会丢取消

`novel/billing.py` 的 `_drain` 负责「等受保护的操作跑完，再把取消交还调用方」。实测当前代码：

```
调用方被取消 + 内层抛普通异常: 收到 ValueError（取消丢失，task.cancelled()=False）
调用方被取消 + 内层成功:       收到 CancelledError（取消送达）
```

也就是调用方已经被取消、里面的操作又抛了普通异常时，调用方只看到那个普通异常。讨论群第二轮复核的 M5 就是它：外层有 `except Exception` 把异常当成可以跳过的失败，于是暂停被无视。讨论群的补法是在调用处检查 `asyncio.current_task().cancelling()`。

书斋这边没有补。`_drain` 的调用点在 `novel/billing.py`（3 处）和 `novel/llm_router.py`（2 处）。`novel/runner.py` 的 `_run` 对 `CancelledError` 是原样上抛，对其他异常是把书写成失败或暂停。按代码推断（没有实测）：写作任务被取消的同时，受保护的计费操作报了普通异常（最可能的就是锁库超时），任务不会按取消收场，而是把书的状态写成 `step_failed` 或 `failed`。

这两个问题会互相放大：僵尸写锁造成的正是「被取消」加「锁库超时」同时出现。

## 7. 修法

### 7.1 两层防护

**连接层回滚。** 在打开连接的地方加一条规则：有异常（包括取消）离开连接作用域时，先回滚，再关闭。

- 不改变既有行为：带着没提交的事务关连接，本来就等于回滚；这条规则只是让回滚在僵尸状态下也立即发生。无异常离开时什么都不多做。
- 改动是机械的：把 `aiosqlite.connect(` 换成一个同样用法的封装。148 处调用点，文本替换即可，参数原样不动。三个模块级封装内部也调 `aiosqlite.connect`，一并覆盖，书斋的令牌核对随之进入回滚范围，`DbStepStore` 不用动。
- 对情形一、情形二、原生取消、anyio 取消都有效（第 2.5 节）。
- 它不处理的：取消落在提交上时，数据已提交而调用方收到的是取消。这是现状，本来就如此。

**受保护任务。** 整个事务放进独立任务，屏蔽取消，跑完再把取消交还。讨论群的 `run_write` 和计费的 `_drain` 就是这样。

- 更强：事务一定跑完，不会被打断在中间。
- 代价：要把写法从「`async with` 里一条条写」改成「把事务包成一个函数交出去」，是结构性改动；而且改变了行为（调用方被取消，事务照样提交）。

### 7.2 取舍

| 方案 | 改动 | 覆盖 | 风险 |
|---|---|---|---|
| 甲：连接层回滚，全站替换；`_drain` 修丢取消；加静态守卫 | 1 个新文件，21 个文件里共 148 处文本替换，`_drain` 一处 | 全部写事务，含以后新写的（守卫拦住直接开连接的写法） | 低：不改语句、不改事务边界、不改既有行为 |
| 乙：只修第一、二档 | 约 5 个文件、十来个函数，各加一段回滚 | 当前已知暴露的路径 | 低，但第三到五档原样留着，以后新增的后台任务或新写法会再次中招，没有东西拦 |
| 丙：全站改成受保护任务 | 79 个写事务逐个改写法 | 全部 | 高：结构性改动大，行为有变化，每个函数都要重新验证 |

推荐甲。乙省不了多少事（要逐个函数加回滚，反而比文本替换更容易漏），丙的收益在锁的问题上和甲相同。已经在受保护任务里的（计费、讨论群）保持不动。

### 7.3 原型验证

在 main `19e4bd1` 的副本里按方案甲做了原型：新增封装，148 处调用点文本替换（21 个文件），`_drain` 改成不丢取消。原型只用于验证可行，不是交付的实现。

- `verify/real_code_repro.py`：同样 73 个取消点，收尾写库失败从 13 处变成 0 处（`verify/real_code_repro.prototype.out.txt`）。把原型里回滚那一步去掉再跑，回到 13 处。
- 全量测试：8552 条全部通过，0 失败，0 跳过，既有测试没有改动。
- `_drain` 改过之后：调用方被取消、内层抛 `ValueError` 时，调用方收到 `CancelledError`，`__cause__` 是那个 `ValueError`。

顺带记录：当天三次全量（基线一次、原型两次）里有两次是 8551 通过、1 失败，失败的都是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]`。它不碰数据库，单独跑 5 次、所在文件单独跑 3 次都通过，和本任务无关。

## 8. 附件

| 文件 | 内容 |
|---|---|
| `verify/mechanism_probe.py`、`.out.txt` | 9 种事务写法 × 每个取消点 × 两种落点，不加保护时哪里残留写锁 |
| `verify/mechanism_probe2.py`、`.out.txt` | anyio 取消、任务对象被引用时锁挂多久、两种修法的验证 |
| `verify/disconnect_probe.py`、`.out.txt` | 客户端断开时普通接口和流式接口是否被取消 |
| `verify/txn_inventory.py`、`inventory.19e4bd1.txt` | 全站写事务清单 |
| `verify/callgraph.py`、`callgraph.19e4bd1.txt` | 取消入口能走到哪些写事务 |
| `verify/real_code_repro.py`、两份 `.out.txt` | 在真实代码上的复现，修前与原型 |

复跑方法见各脚本文件头。`mechanism_probe*.py` 与 `disconnect_probe.py` 用后端的虚拟环境直接运行；`real_code_repro.py` 要在某个代码副本的 `backend/` 目录下运行。
