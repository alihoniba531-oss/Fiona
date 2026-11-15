# 复核返修第 1 轮 · 门禁补单报告

依据 `09-fix-review-r1b.md`。只补三条存活变异的用例，没有改实现文件。没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`，没有访问真实模型/搜索。

## 拆分表

本单改动小，按返修单允许由主代理直接完成，没有派子代理。

| 执行者 | 文件 | 内容 | 结果 |
|---|---|---|---|
| 主代理 | `backend/tests/test_discuss_runner.py` | 追加 V3 用例（作者补充段之后） | ok |
| 主代理 | `backend/tests/test_discuss_billing.py` | 追加 V7a、V7c 用例 | ok |
| 主代理 | `docs/tasks/2026-11-14-agent-group/impl/report-review-r1b.md` | 本报告 | ok |

`backend/tests/test_discuss_api.py` 本次未改；`backend/discuss/` 下实现文件一律未改。`test_discuss_runner.py` 末尾「R3 门禁后由规格作者补充」的两条用例及 `_hold_cursor_after_token_check` 原样保留，新用例追加在文件末尾。

## 三条用例

### V3：分身取私有记忆的取消保护

新用例：`test_cancelled_avatar_system_for_memory_snapshot_leaves_no_write_lock`

- 标记查询选的是 `get_memory_snapshot` 内部的：
  `SELECT private_memory_json, memory_revision FROM agents WHERE owner_username = ?`
- 理由：`get_my_agent` 用的是 `SELECT * FROM agents WHERE owner_username = ?` 和 `SELECT * FROM agents WHERE id = ?`，不包含这条列名组合；先 `await agent_store.get_my_agent(USER)` 建好行、让第一次 `get_my_agent` 正常返回，再给 `aiosqlite.Connection._execute` 装钩子，只在上面这条查询执行完、游标未取走时停住。这样取消点确定落在 `get_memory_snapshot`，而不是作者已补过的 `get_my_agent`。
- 取消 `avatar.system_for(USER, "brief")` 后，在 worker 的 `finally` 用 `aiosqlite.connect(timeout=0.2)` 执行 `BEGIN IMMEDIATE`，必须立刻成功。
- 去掉 `avatar.py` 中 `snapshot` 的 `NovelBilling._drain` 后，该用例失败；当前通过。

### V7a：开工前退残留预扣

新用例：`test_start_refunds_stale_reservation_before_launch`

- 付费模式（`DEV_MODE=0`）先跑完立项到 `awaiting_start`，用 `reserve_stale_step` 造一条 `billing_status='reserved'` 的步骤并把群置为 `awaiting_start`。
- 在 `runner.start_group` 外面包一层观察：`service.start` 调用到 `start_group` 时，群 `reserved_strawberries == 0`、余额已恢复、旧步骤 `interrupted/refunded`；之后正常跑完，最终余额减少量等于群 `spent`。
- 去掉 `service.start` 启动前的 `refund_reserved()` 后，该用例失败；当前通过。

### V7c：追加轮数前退残留预扣

新用例：`test_continue_refunds_stale_reservation_before_launch`

- 同样造 `awaiting_user` 的群和一条 reserved 步骤；观察 `continue_group` 调用到 `start_group` 时残留预扣已退、余额已恢复；正常跑完后余额减少量等于 `spent`。
- 去掉 `service.continue_group` 启动前的 `refund_reserved()` 后，该用例失败；当前通过。

## 验收

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

结果：`191 passed, 45 warnings in 14.19s`，退出码 0，0 跳过。

各文件收集数：api 36、billing 27、docs 19、engine 49、runner 23、schemas 33、structure 4，合计 191。

### 2. V1 V2 V3 V7a V7b V7c 变异自检

```text
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> V1 V2 V3 V7a V7b V7c
```

原始输出：

```text
正控（未改动）：exit=0 191 passed, 45 warnings in 16.86s
V1   杀死  分身取资料不受取消保护（系统提示）  [1 failed, 146 passed, 45 warnings in 13.72s]
V2   杀死  分身取名字不受取消保护  [1 failed, 147 passed, 45 warnings in 13.79s]
V3   杀死  分身取记忆不受取消保护  [1 failed, 153 passed, 45 warnings in 14.37s]
V7a  杀死  开工前不退残留预扣  [1 failed, 61 passed, 45 warnings in 7.00s]
V7b  杀死  继续前不退残留预扣  [1 failed, 58 passed, 45 warnings in 6.69s]
V7c  杀死  追加轮数前不退残留预扣  [1 failed, 62 passed, 45 warnings in 7.16s]
收尾正控（全部还原后）：exit=0 191 passed, 45 warnings in 14.38s
非断言失败的「杀死」：[]
合计 6，杀死 6，存活 []，锚点缺失 []
```

六条都是 `1 failed`，不是 `error`；结果 JSON 汇总为 `{"total": 6, "killed": 6, "survived": [], "anchor_missing": [], "restored_ok": true}`。克隆目录与结果文件已删除。

### 3. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8543 passed, 47 warnings in 399.74s (0:06:39)`，退出码 0，0 失败、0 跳过。基线 8352 + 191 = 8543；全量收集数 8543。

### 4. 改动范围

`git status --porcelain --untracked-files=all` 当前共 58 条。

- 与本次补单派出时相比，只多出本报告。
- 测试内容变动只在允许的 `backend/tests/test_discuss_runner.py`（V3）与 `backend/tests/test_discuss_billing.py`（V7a/V7c）。`backend/tests/test_discuss_api.py` 未改；实现文件、`verify/`、`backend/novel/`、`agent_store.py`、`conftest.py` 均未改。
- 规格作者在本单派出前提供的 `09-fix-review-r1b.md` 原样保留；首轮回合的任务材料与报告未改。
- `CLAUDE.md` 仍为 68,497 字节；已跟踪文件的 `git diff --stat` 未变。

## 未完成或需要人工确认

1. V3 用例只覆盖 `get_memory_snapshot` 的一条标记查询；`get_my_agent` 的取消路径由作者已补的两条分身用例覆盖，两者合起来覆盖 `build_avatar_system` 的两次调用。
2. V7a/V7c 用 `awaiting_start` / `awaiting_user` 构造残留状态；`done` 状态走 `continue` 的分支未单独造，但 `continue_group` 的启动前退款代码路径相同，且 V7c 的变异已杀死。
3. 没有真起服务、没有调用真实模型/搜索；六条变异与全量都在离线测试环境完成。
