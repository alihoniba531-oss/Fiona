# 返修单 R2：多智能体讨论群第一期

依据仍是 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1）。R1 交回后的门禁：新测试 146 通过、0 跳过；全量 8498 通过、0 跳过；变异 68 条杀死 66 条，P1–P3 对应的 5 条全部杀死。本轮只处理下面三件事。

## 一、规矩

1. 只允许改：`backend/tests/test_discuss_*.py`、新报告 `docs/tasks/2026-11-14-agent-group/impl/report-r2.md`。第三节如果查明原因在 `backend/discuss/runner.py`，可以改这个文件；除此之外的实现文件不动。
2. 已有用例的断言不许放宽或删除。其余规矩同前两轮。
3. 本轮改动小，可以不拆分，由你直接完成；要拆分的话仍按文件不重叠。

## 二、两条仍然存活的变异

上一轮它们被记成「杀死」，但那两次不是断言失败，而是下面第三节说的偶发报错，属于假阳性。现在的测试里没有任何用例断言这两个行为。

| 编号 | 变异（见 `verify/mut_discuss.py`） | 要补的用例 |
|---|---|---|
| T18 | S8：去掉「预算已经用完」的检查 | 群 `paused` 且 `budget_strawberries <= spent_strawberries` 时，`resume` 返回 `409`、文案「预算已经用完，请先调高预算」、状态不变；带上足够的 `add_budget` 后成功。`continue` 走同一条检查（`awaiting_user` 且预算已用完时 `409`），也要有用例 |
| T19 | S9：去掉「先暂停再结束」的检查 | 群在 `planning` 或 `running` 时 `close` 返回 `409`、文案「先暂停再结束」、状态不变；暂停之后再 `close` 成功并变成 `closed` |

自检：补完后运行

```
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> S8 S9
```

两条都要「杀死」，并且输出里的摘要必须是有用例 `failed`，不能是 `error`。

## 三、一个偶发的报错

规格作者跑变异时，在约 200 次「按文件顺序、带 `-x` 跑全部 `tests/test_discuss_*.py`」里遇到 3 次这样的结果：

```
6 passed, 45 warnings, 1 error in 17.8s
```

三次的耗时都在 17.8–17.9 秒（正常跑完整个文件只要 4 秒），都发生在 `tests/test_discuss_api.py` 的前 6 个用例通过之后，也就是第 7 个用例 `test_second_group_while_one_active_is_409` 的准备或收尾阶段，或第 6 个用例的收尾阶段。它是 `error` 不是 `failed`，说明异常出在夹具的准备或收尾里。出现时机器上同时有别的任务在跑；干净环境下连跑 86 次没有复现，报错原文没有抓到。

请读代码排查并消除它。线索：

- 这个用例用 `asyncio.run(discuss_store.update_group(USER, group["id"], status="running"))` 直接把群改成 `running`，之后没有还原，也没有对应的后台任务；用例结束时 `client` 夹具会走应用的关停流程（`shutdown_discuss_tasks()` 等）。
- `discuss.runner.TASKS` 是模块级字典，跨用例存活；`cancel_group` 在任务属于另一个事件循环时走 `run_coroutine_threadsafe`。上一个用例留下的、属于已关闭事件循环的任务如果还挂在 `TASKS` 里，关停流程可能卡住或抛错。
- 17.8 秒很像某个等待超时之后才报错。

要求：

1. 找出确切原因（指出是哪一行在等、等的是什么），写进报告。
2. 如果原因在测试（用例之间互相留下了状态、没有等后台任务收尾就结束等），修测试：每个用例结束前把自己起的后台任务停干净，不靠 `sleep` 碰运气。
3. 如果原因在 `backend/discuss/runner.py` 的取消或关停逻辑（例如对已关闭事件循环上的任务处理不当），修实现，并补一个能稳定复现该问题的用例（修之前失败、修之后通过）。
4. 如果读完代码仍然无法确定原因，不要乱改；在报告里写清你排除了哪些可能、还剩哪些怀疑。

## 四、验收

从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`：

1. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py` 全部通过、0 跳过；连跑 10 次都如此，贴出 10 次的结尾行。
2. 全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`：通过数 = 8352 + 新测试总数，0 失败、0 跳过。
3. 第二节的变异自检两条都靠 `failed` 杀死。
4. `git status --porcelain --untracked-files=all` 与 R1 交付相比，只多出或变动本单第一节第 1 条允许的文件。

报告写进 `docs/tasks/2026-11-14-agent-group/impl/report-r2.md`，不写本机绝对路径：T18、T19 对应的测试函数名；第三节的排查结论与改动；验收四条的命令与输出摘要；未完成或需要人工确认的地方。
