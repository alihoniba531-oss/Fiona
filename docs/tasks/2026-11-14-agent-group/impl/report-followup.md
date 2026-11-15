# 验收后小单：三条收紧报告

依据 `02-spec.md` v1.2 新增第 13、14 条与 `04-review-r3.md` 第 4、6 节。改动只在 `store.py`、`billing.py`、`service.py`、`runner.py` 和测试文件；没有改 `engine.py`、`avatar.py`、`roles.py`、`research.py`、`schemas.py`、`config.py`、`backend/novel/`、`agent_store.py`，没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`，没有访问真实模型/搜索。

## A. 退残留预扣并进状态事务

### 实现

- `store.refund_reserved_on_connection(db, username, group_id)`：在调用方已有的连接/事务里退该群全部 `billing_status='reserved'` 的预扣：
  - 汇总 reserved 金额并加回 `users.strawberry_balance`；
  - `discuss_groups.reserved_strawberries` 归零；
  - reserved 步骤标成 `status='interrupted'`、`billing_status='refunded'`。
- `DiscussBilling._refund_reserved_transaction` 改为在 `BEGIN IMMEDIATE` 里调用这个函数，不再复制三条 SQL；`refund_reserved` 的外部行为和金额返回值不变。
- `store.delete_group` 改为先调用同一函数，再删五张表的行；删群仍只退 reserved，settled/refunded 不重复退。
- `service.start`、`resume`、`continue_group`、`accept`、`close` 的退款都移进各自改状态的 `run_write` 事务，事务提交后不再单独调用 `refund_reserved()`。
- 已 `closed` 的群再次 `close`：走一个独立的受保护写事务，只调用退款函数，不改状态。

### 新用例

- `test_start_refund_failure_rolls_back_state_and_tasks`
  - 付费群停在 `awaiting_start`、留一条 reserved 步骤、余额已预扣；
  - monkeypatch `refund_reserved_on_connection` 抛错，调用 `start`；
  - 断言抛错、群仍在 `awaiting_start`、令牌不变、reserved 和余额不变、步骤仍 reserved、没有起后台任务。
- `test_accept_refund_failure_rolls_back_state`
  - 同样造数，调用 `accept`；断言状态仍 `paused`、reserved 和余额不变、步骤仍 reserved。
- `test_closed_group_close_refunds_once`
  - 群已经是 `closed` 且留有 reserved 预扣；第一次 `close` 退回并令余额等于 `10000 - spent`，第二次 `close` 余额不再变。

### 已有用例调整

没有调整任何已有用例；只追加了新用例。六条 `*_refunds_stale_reservation*` 用例（resume、delete、start、continue、accept、close）全部原样通过。`delete_group` 的退款被抽成共享函数后，`test_delete_refunds_stale_reservation_when_cancel_is_noop` 仍通过。

## B. 取消优先于同时发生的失败

### 实现

`runner._run` 保留 `CancelledError` 和 `RunNoLongerActive` 两个先行分支；其余所有异常进入统一的 `except Exception as error` 后，先检查：

```python
current = asyncio.current_task()
if current is not None and current.cancelling():
    raise asyncio.CancelledError() from error
```

只有没有待交付的取消时，才按原类型写 `insufficient_strawberries`、`budget`、`byok_unavailable`、`search_unavailable`、`step_failed` / `server_restart_failed` 或 `error`。`finally` 的 `_cleanup` 不变。

### 新用例

- `test_pause_during_protected_write_error_keeps_paused`
  - monkeypatch `DiscussStepStore.post_message`，第一次调用用 `shield` 模拟受保护写事务：取消先到，内层随后抛 `sqlite3.OperationalError`；
  - 阻塞期间调用 `service.pause`，放行后断言 `paused/user`，而不是 `failed/error`。
- `test_pause_during_avatar_insufficient_keeps_paused`
  - 开工后 view 的 `get_memory_snapshot` 阻塞后抛 `InsufficientStrawberries`，期间暂停；
  - 断言 `paused/user`，而不是 `paused/insufficient_strawberries`。

没有取消时原有异常仍写原停止原因：`insufficient_strawberries`、预算、BYOK、搜索、步骤失败等已有用例全部通过。

## C. 目录接口 notice 用例

`test_catalog_notice_ends_with_search_fee_sentence`：`GET /discuss/catalog` 返回的 `notice` 以「联网搜索按次另扣草莓，与成员用哪个模型无关。」结尾。`roles.PRIVACY_NOTICE` 和三份文档的 Y5 老用例继续保留。

## 自检表

在系统临时目录的克隆里改坏、运行、还原并删除；均为 `failed`，不是 `error`/超时。

| 项 | 改坏方式 | 由哪条用例发现 | 失败摘要 |
|---|---|---|---|
| A/start | 把 start 的退款从状态事务里删掉，改到 `run_write` 之后单独调用 | `test_start_refund_failure_rolls_back_state_and_tasks` | `1 failed in 2.30s`；断言 `('running', None) == ('awaiting_start', None)` |
| A/accept | 把 accept 的退款移出状态事务、放到提交之后 | `test_accept_refund_failure_rolls_back_state` | `1 failed in 0.87s` |
| A/closed | 去掉已 `closed` 群的退款分支 | `test_closed_group_close_refunds_once` | `1 failed in 0.87s` |
| B/Q5 | 去掉 `_run` 里的 `cancelling()` 判断 | `test_pause_during_protected_write_error_keeps_paused` | `1 failed in 1.10s`（与下条合计 2 failed） |
| B/Q2 | 同上 | `test_pause_during_avatar_insufficient_keeps_paused` | 同上，合计 `2 failed in 1.10s` |

A 的两条原子性用例在「退款留在事务内」时都通过；B 两条在判断存在时都通过。

## 验收

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

结果：`206 passed, 45 warnings in 15.67s`，退出码 0，0 跳过。

各文件收集数：api 39、billing 33、docs 20、engine 49、runner 28、schemas 33、structure 4，合计 206。

### 2. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8558 passed, 47 warnings in 420.22s (0:07:00)`，退出码 0，0 失败、0 跳过。基线 8352 + 206 = 8558；全量收集数 8558。

说明：第一次全量出现一次既有 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]` 的时序失败（`8557 passed, 1 failed`）；单跑通过，第二次全量 8558 全过。该测试不属于讨论群，未改。

### 3. 自检

见上表：A 三个改坏点、B 两个改坏点，全部由断言失败发现；没有 `error`/超时。

### 4. 改动范围

`git status --porcelain --untracked-files=all` 当前共 10 条：

- `backend/discuss/billing.py`
- `backend/discuss/runner.py`
- `backend/discuss/service.py`
- `backend/discuss/store.py`
- `backend/tests/test_discuss_api.py`
- `backend/tests/test_discuss_billing.py`
- `backend/tests/test_discuss_runner.py`
- `docs/tasks/2026-11-14-agent-group/02-spec.md`（规格作者新增第 13、14 条）
- `docs/tasks/2026-11-14-agent-group/11-followup-tighten.md`（本单派单）
- `docs/tasks/2026-11-14-agent-group/impl/report-followup.md`（本报告）

没有其他文件变动；`test_discuss_docs.py`、`test_discuss_engine.py`、`test_discuss_schemas.py`、`test_discuss_structure.py` 均未改。

## 未完成或需要人工确认

1. A 把退款并进状态事务后，`blocked` 分支等仍走 `run_write`；如果退款本身抛错，状态和预扣一起回滚，接口返回 500/原异常。没有加“失败后自动重试”逻辑。
2. B 的取消优先判断只放在 `_run` 的异常出口；`CancelledError` 和 `RunNoLongerActive` 仍先走原分支。没有改变 `_cleanup` 的退款失败日志行为。
3. 全量第一次的 `test_novel_workflow.py` 时序失败在本轮前后都存在；本轮未改该文件，第二次全量通过。若验收要求“全量一次通过”，需要单独处理该既有 flake，但不在本单允许范围。
4. 已有的六条 `*_refunds_stale_reservation*`（派单说五条，实际 grep 到六条，含 delete）全部通过；没有放宽或删除断言。
