# 返修单 R3 实施报告：多智能体讨论群第一期

依据 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1）与返修单 R3。没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`。

## 拆分表

| 轮次 | 执行者 | 负责文件 | 内容 | 结果 |
|---|---|---|---|---|
| R3（串行） | 主代理 | `backend/discuss/store.py` | 新增取消安全的 `run_write(operation)` 与 `DiscussStepStore.transaction(operation)`，迁移 store 内全部写事务 | ok |
| R3（并行） | engine agent | `backend/discuss/engine.py` | 立项保存方案的事务迁移 | ok |
| R3（并行） | runner agent | `backend/discuss/runner.py` | 令牌、暂停、恢复失败、清令牌事务迁移；删除 N8 的多余兜底 | ok |
| R3（并行） | service agent | `backend/discuss/service.py` | 作者侧 8 个写事务迁移 | ok |
| R3 | 主代理 | `backend/tests/test_discuss_runner.py` | R3 取消保护用例、N8/N9 用例、加强关闭循环断言 | ok |
| R3 | 主代理 | `docs/tasks/2026-11-14-agent-group/impl/report-r3.md` | 本报告 | ok |

3 个实现 agent 由工作流 `parallel()` 并行执行，文件互不重叠；`store.py` 的新接口先由主代理串行定好。没有 agent 失败。`billing.py` 未改（R3 允许但不需要，它原本已用 `NovelBilling._drain`）。

## 保护是怎么做的

### 新接口

`backend/discuss/store.py`：

```python
async def run_write(operation):
    async def transaction():
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                result = await operation(db)
            except BaseException:
                await db.rollback()
                raise
            else:
                await db.commit()
                return result
    return await NovelBilling._drain(transaction())
```

- `operation(db)` 里只允许数据库读写，不得 await 模型、搜索或非数据库操作。
- `NovelBilling._drain` 把整个事务（含 commit/rollback 和连接关闭）放进受保护任务：调用方被取消时先不打断事务，等事务结束、连接关闭后才把 `CancelledError` 交还。
- 返回值和异常照旧；`run_write` 自己负责 rollback。

`DiscussStepStore.transaction(operation)`：

```python
async def guarded(db):
    if not await self.is_current(db):
        raise RunNoLongerActive()
    return await operation(db)
return await run_write(guarded)
```

它不再是 `async contextmanager`。所有调用点都改为传协程函数；守卫失败抛 `RunNoLongerActive`，语义与原来「yield None 后抛」等价。

### 覆盖的写入点

`store.py`：

- `run_write`（模块级受保护事务）
- `DiscussStepStore.transaction`（令牌守卫 + 受保护事务）
- `DiscussStepStore.write_step`
- `DiscussStepStore.append_usage`
- `DiscussStepStore.post_message`
- `DiscussStepStore.update_group`（实例方法）
- `DiscussStepStore.save_output`
- `DiscussStepStore.save_verdict`
- 模块级 `create_group`、`update_group`、`delete_group`
- 模块级 `post_user_note`
- 模块级 `claim_notes`
- 模块级 `register_source`、`register_sources`

`engine.py`：

- `run_planning` 保存 `plan_json` / `plan_revision` / `title` 的唯一直接事务

`runner.py`：

- `start_group` 的令牌声明事务
- `_pause` 写状态
- `recover_interrupted_groups` 失败时写 `paused/server_restart_failed`
- `cancel_group` 清令牌
- `_cleanup` 清令牌

`service.py`（作者侧接口，客户端断开也会被取消）：

- `create_group`
- `update_plan`
- `start`
- `pause`
- `resume`
- `continue_group`
- `accept`
- `close`

间接覆盖：

- `research.run_search` 的失败步骤通过 `store.write_step` 写；`register_findings` 通过 `register_sources` 登记，均在受保护事务里。
- `engine` 的消息、状态、成果、验收结果都走 `DiscussStepStore` 的受保护方法。
- 计费 `billing.py` 的六个事务本来就用 `NovelBilling._drain`，本次未改。

## 新用例与自检

### 取消保护用例

`backend/tests/test_discuss_runner.py`：

- `test_cancelled_store_transaction_finishes_and_releases_lock`：在 `store.transaction` 的提交点用可控等待点停住，取消任务；断言任务在事务收尾前不能结束，放行后 `CancelledError` 才出现、提交标记存在，且新连接以 0.2 秒忙等待执行 `BEGIN IMMEDIATE` 成功。
- `test_cancelled_store_transaction_twice_finishes_and_releases_lock`：同一任务连续取消两次，仍等事务提交后才结束，并检查写锁已释放。
- `test_cancelled_pause_write_finishes_and_releases_lock`：取消 `runner._pause` 的提交，放行后群仍是 `paused` / `budget`，写锁可立即拿到。
- `test_cancelled_cancel_group_token_clear_finishes_and_releases_lock`：取消 `cancel_group` 的清令牌提交，放行后 `run_token` 已清空，写锁可立即拿到。

四个用例都用 `_gate_next_commit` 把连接 `commit` 换成「先等一个事件再真正 commit」，只允许 await 数据库提交；不依赖多跑碰运气。

### 去掉保护的自检

在系统临时目录的克隆里把 `store.run_write` 换成不加 `_drain` 的朴素实现，运行上述四个用例：

```text
FFFF                                                                     [100%]
...
FAILED tests/test_discuss_runner.py::test_cancelled_store_transaction_finishes_and_releases_lock
FAILED tests/test_discuss_runner.py::test_cancelled_store_transaction_twice_finishes_and_releases_lock
FAILED tests/test_discuss_runner.py::test_cancelled_pause_write_finishes_and_releases_lock
FAILED tests/test_discuss_runner.py::test_cancelled_cancel_group_token_clear_finishes_and_releases_lock
4 failed, 9 deselected in 2.81s
```

失败点是「取消不应在事务收尾前生效」和「事务已取消但状态/令牌没提交」。之后在克隆里还原并删除临时目录，工作区未受影响。

### N8 / N9

- N8：保留 `if loop.is_closed() or not loop.is_running():`，删除后面 `except RuntimeError` 的重复兜底，只留一层。关闭循环的回归用例 `test_cancel_group_detaches_task_on_closed_loop_and_clears_token` 现在能直接区分：N8 下会走到 `run_coroutine_threadsafe` 并在关闭循环上抛 `RuntimeError`。
- N9：`finally` 里的 `TASKS.pop` / `_owners.pop` 保留；新增 `test_cancel_group_purges_done_task_from_registries` 断言已结束任务处理后不在两个登记表；关闭循环的既有用例也把「不在 TASKS/_owners」的断言移到清理之前，避免测试自己先 pop 掉掩盖 N9。

## 验收五条

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

结果：`154 passed, 45 warnings in 12.01s`，退出码 0，0 跳过。各文件收集数：api 24、billing 18、docs 19、engine 43、runner 13、schemas 33、structure 4。

### 2. 150 次稳定性

```text
.venv/bin/python -m pytest -q -x -p no:cacheprovider tests/test_discuss_api.py -k "admission or create_group_planning or patch_plan or second_group"
```

```text
TOTAL_RUNS=150 PASS=150 FAIL=0
```

150 次退出码全部为 0，没有失败。之前 17.4 秒的 `database is locked` 收尾错误没有出现。

### 3. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8506 passed, 47 warnings in 422.55s (0:07:02)`，退出码 0，0 失败、0 跳过。基线 8352 + 本轮 154 = 8506；全量收集数也是 8506。

说明：第一次全量跑出现一次既有 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]` 的时序失败（`8505 passed, 1 failed`），单跑该用例通过；第二次全量得到上面的 8506 全过。该测试不属于讨论群，未改动。

### 4. N8 / N9 / T1 / N6 变异

```text
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> N8 N9 T1 N6
```

```text
正控（未改动）：exit=0 154 passed, 45 warnings in 13.83s
N6   杀死  取消任务时不退还预扣  [1 failed, 41 passed, 45 warnings in 6.06s]
T1   杀死  后台写库不核对令牌  [1 failed, 110 passed, 45 warnings in 11.79s]
N8   杀死  任务所属事件循环已关闭时仍去调度  [1 failed, 111 passed, 45 warnings in 11.49s]
N9   杀死  处理过的任务不从登记表移除  [1 failed, 111 passed, 45 warnings in 11.02s]
收尾正控（全部还原后）：exit=0 154 passed, 45 warnings in 11.31s
非断言失败的「杀死」：[]
合计 4，杀死 4，存活 []，锚点缺失 []
```

四条都是 `1 failed`，不是 `error`。结果 JSON：`{"total": 4, "killed": 4, "survived": [], "anchor_missing": [], "restored_ok": true}`。克隆目录与结果文件已删除。

### 5. 改动范围

`git status --porcelain --untracked-files=all` 当前共 50 条。

- 与 R2 交付的 48 条相比，没有删除任何路径。
- 新增 2 条：规格作者在本次返修开始前放好的 `docs/tasks/2026-11-14-agent-group/07-fix-r3.md`，以及本报告 `docs/tasks/2026-11-14-agent-group/impl/report-r3.md`。
- 内容变动只在本单允许的 `backend/discuss/store.py`、`runner.py`、`engine.py`、`service.py` 和 `backend/tests/test_discuss_runner.py`；`research.py`、`billing.py` 未改。
- 其他实现文件、文档、其他测试文件未改；`backend/novel/` 一字未动。`CLAUDE.md` 仍是 68,431 字节；9 条已跟踪文件的 `git diff --stat` 与 R2 一致（80 insertions / 6 deletions）。

## 未完成或需要人工确认

1. 书斋 `backend/novel/` 里存在同类的「取消时 aiosqlite 已入队语句留下写锁」隐患，但 R3 明确不在本次范围；本次只修讨论群，报告此点供后续立项。
2. `start_group` 的令牌声明现在是受保护事务，但事务提交后、`create_background_task` 之前仍有极窄的取消窗口：可能留下已声明令牌而没有任务。R3 只要求写事务不留下写锁，这个窗口不会锁库；后续 `start_group` 会因已有令牌返回 None。若要求令牌与任务严格原子，需要额外的补偿清理，本次未做。
3. N8 的两种极端竞态（检查后、调度前循环刚好停止）现在会让 `RuntimeError` 上抛，因为按要求删掉了第二层兜底；正常关闭循环的回归用例已覆盖，N8 变异也已杀死。
4. 原始 17.8 秒 `database is locked` 的现场 traceback 是规格作者提供的；本轮通过 150 次稳定性与确定性取消用例验证不再出现锁泄漏，但没有再跑一次 200 次的外部压测。
