# 复核返修第 1 轮 · 门禁补单

`08-fix-review-r1.md` 交回后的门禁：改动范围合规；讨论群用例 188 passed、0 跳过；全量 8540 passed、0 失败、0 跳过；规格作者的三个探针（分身路径写锁、继续不跳过开工、写锁回归）在新代码上全部通过。变异脚本 `verify/mut_discuss.py` 共 110 条，107 条靠断言失败被发现，**3 条存活**。代码是对的，缺的是用例。本单只补这三条用例。

## 一、规矩

1. 只允许改 `backend/tests/test_discuss_runner.py`、`backend/tests/test_discuss_billing.py`、`backend/tests/test_discuss_api.py`（只追加，不改已有用例），和新报告 `docs/tasks/2026-11-14-agent-group/impl/report-review-r1b.md`。实现文件一律不动。
2. 其余规矩同 `08-fix-review-r1.md` 第一节。本单改动小，可以不拆分，由你直接完成。

## 二、三条存活的变异

| 编号 | 变异 | 为什么现有用例发现不了 | 要补的用例 |
|---|---|---|---|
| V3 | `avatar.build_avatar_system` 里取私有记忆的那一处去掉取消保护：`snapshot = await agent_store.get_memory_snapshot(username)` | 现有两条分身用例都停在 `FROM agents WHERE owner_username` 那条查询上，那是 `get_my_agent` 里的；`get_memory_snapshot` 自己的查询从没在「结果未取走时被取消」的条件下跑过 | 一条用例：让 `get_memory_snapshot` 内部的一条查询执行完、游标未取走时停住（选一条只出现在 `get_memory_snapshot` 里、不出现在 `get_my_agent` 里的查询作为标记；先确认 `get_my_agent` 那一步已经正常返回），取消正在执行 `avatar.system_for(USER, "brief")` 的任务，在它的 `finally` 里用忙等待 0.2 秒的新连接执行 `BEGIN IMMEDIATE`，必须立刻成功 |
| V7a | `service.start` 里去掉启动前的 `refund_reserved()` | 现有用例只覆盖了 `resume` | 付费模式（`DEV_MODE=0`）：造一个「群在 `awaiting_start`、留有一条 `billing_status='reserved'` 的步骤、余额已被预扣」的状态，调用 `start`：那条步骤变成已退、余额先恢复；之后正常跑完，最终余额减少量 = `spent` |
| V7c | `service.continue_group` 里去掉启动前的 `refund_reserved()` | 同上 | 付费模式：同样的残留状态放在 `awaiting_user`（或 `done` 且带一条未读插话）的群上，调用 `continue`：残留预扣被退回，最终余额减少量 = `spent` |

写法可以参照已有的 `test_resume_refunds_stale_reservation_before_replanning` 和两条 `test_cancelled_avatar_*` 用例。

## 三、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过。
2. 自检：从仓库根运行

   ```
   backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> V1 V2 V3 V7a V7b V7c
   ```

   六条都要「杀死」，摘要必须是有用例 `failed`，不能是 `error`。贴出输出。
3. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 讨论群用例总数，0 失败、0 跳过。
4. `git status --porcelain --untracked-files=all`：相对本单派出时只多出报告，变动只在第一节允许的三个测试文件里。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-review-r1b.md`，不写本机绝对路径：三条用例的函数名、V3 用例选了哪条查询作标记及理由、验收四条的命令与输出摘要。
