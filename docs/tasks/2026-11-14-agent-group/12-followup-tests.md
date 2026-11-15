# 小单门禁补单：补四条用例

`11-followup-tighten.md` 交回后的门禁与复核都通过了（复核报告 `docs/tasks/2026-11-14-agent-group/04-review-followup.md`，没有必须修复项）。代码是对的，缺的是用例：复核方把下面四处改坏之后，206 条讨论群用例照样全过。本单只补这四条用例。先读复核报告第 4 节第 1、2 条和第 5.3、5.4 节。

## 一、规矩

1. 只允许改 `backend/tests/test_discuss_billing.py`、`backend/tests/test_discuss_runner.py`（只追加，不改已有用例），和新报告 `docs/tasks/2026-11-14-agent-group/impl/report-followup-tests.md`。实现文件一律不动。
2. 不许动任务目录下的规格、复核、返修单与 `verify/`，不动 `conftest.py`。
3. 不装依赖，不读 `.env`，不 commit / stash / checkout / reset，不访问外网，不调用真实模型。
4. 本单改动小，由你直接完成，不拆分，不调用 subagent / subagent_fork / workflow。
5. 你实测到的事实优先于本单的说法。如果某条新用例在现在的实现上就失败，说明实现有问题：停下来在报告里写明现象，不要改实现，也不要把断言改松。任何情况不回滚已完成的工作。

## 二、四条要补的用例

| 变异编号 | 改坏方式 | 为什么现有用例发现不了 | 要补的用例 |
|---|---|---|---|
| V14b | `service.resume` 里把退残留预扣从状态事务里拿出来，改成事务提交之后再单独退 | 已有的 `test_resume_refunds_stale_reservation_before_replanning` 只看到「最终退了」，看不出退款和改状态是不是同一个事务 | 付费模式。造一个「群停在 `paused`（或 `failed`）、留有一条 `billing_status='reserved'` 的步骤、余额已被预扣」的状态；让 `discuss.store.refund_reserved_on_connection` 抛异常，调用 `resume`：接口报错；群的 `status`、`stop_reason`、`run_token`、`budget_strawberries`、`reserved_strawberries`、那条步骤的 `billing_status`、用户余额都与调用前相同；没有起后台任务 |
| V14c | `service.continue_group` 同上 | 同上（`test_continue_refunds_stale_reservation*` 只看最终结果） | 付费模式。同样的残留状态放在 `awaiting_user` 的群上，调用 `continue_group`（追加 1 轮）：接口报错；上面那些字段加上 `max_rounds` 都与调用前相同；没有起后台任务 |
| V14d | `service.close`（群还没 closed 的那个分支）同上 | 同上 | 付费模式。同样的残留状态放在一个已停下、还没 closed 的群上，调用 `close`：接口报错；群的 `status`（不是 `closed`）、`stop_reason`、`reserved_strawberries`、那条步骤的 `billing_status`、用户余额都与调用前相同 |
| V17 | `runner._run` 里，非恢复模式下的意外异常不再记成 `failed` / `error`（改成记 `paused` / `step_failed`） | 前几轮只测了恢复模式（记 `paused` / `server_restart_failed`）和步骤失败（记 `paused` / `step_failed`） | 没有任何取消的情况下，让 `engine.run_planning` 直接抛一个普通异常（例如 `RuntimeError`），等后台任务结束：群的最终状态是 `failed`、`stop_reason` 是 `error`、`run_token` 为空 |

写法参照：

- 前三条照 `tests/test_discuss_billing.py` 里的 `test_start_refund_failure_rolls_back_state_and_tasks` 和 `test_accept_refund_failure_rolls_back_state`。可以各写一条，也可以写成一条参数化用例；参数化的话每个接口必须是独立的参数，名字里能看出是哪个接口。
- 第四条放 `tests/test_discuss_runner.py`，可以参照 `test_pause_during_protected_write_error_keeps_paused` 的夹具用法。

「与调用前相同」必须真的比较调用前后两次读出来的值，不要只断言某个固定值。「没有起后台任务」要有正面证据（例如把 `runner.start_group` 换成记录调用的替身并断言没被调用，同时 `runner.TASKS` 里没有这个群）。

## 三、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过。
2. 自检：从仓库根运行

   ```
   backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> V14 V14b V14c V14d V14e V15 V17 X18 X19
   ```

   九条都要「杀死」，摘要必须是有用例 `failed`，不能是 `error` 或超时。贴出输出。
3. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 讨论群用例总数，0 失败、0 跳过。如果唯一的失败是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`（已知的旧用例，机器忙时偶发，与本单无关），单独重跑这一条并把两次的输出都贴出来，不要为它改任何文件。
4. `git status --porcelain --untracked-files=all`：相对本单派出时，只有第一节第 1 条允许的两个测试文件有新变动，另加你的新报告。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-followup-tests.md`，不写本机绝对路径：新用例的函数名、各自对应哪条变异、验收四条的命令与输出摘要、没做完或需要人工确认的地方。
