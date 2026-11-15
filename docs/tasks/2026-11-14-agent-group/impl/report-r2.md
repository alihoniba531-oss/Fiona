# 返修单 R2 实施报告：多智能体讨论群第一期

依据 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1）与返修单 R2。R2 改动小，按返修单允许由主代理直接完成，没有派子代理。没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`。

## 拆分表

| 轮次 | 执行者 | 负责文件 | 内容 | 结果 |
|---|---|---|---|---|
| R2 | 主代理 | `backend/tests/test_discuss_api.py` | T18（S8）、T19（S9） | ok |
| R2 | 主代理 | `backend/discuss/runner.py`、`backend/tests/test_discuss_runner.py` | 排查并修复偶发 teardown error，补稳定复现用例 | ok |
| R2 | 主代理 | `docs/tasks/2026-11-14-agent-group/impl/report-r2.md` | 本报告 | ok |

没有子代理，因此没有 agent 失败或返修。

## 第二节：T18、T19 的用例

### T18（S8，移除「预算已经用完」检查）

`test_discuss_api.py::test_resume_and_continue_reject_exhausted_budget_until_added`

- 建群到 `awaiting_start` 后，把群置为 `paused`、`budget_strawberries=500`、`spent_strawberries=500`；`resume` 空请求返回 409，`detail` 是「预算已经用完，请先调高预算」，随后详情仍是 `paused`，预算与已花数不变。
- 同一群 `resume` 带 `add_budget=100` 返回 200，预算变为 600，状态变为 `running`。
- 再把群置为 `awaiting_user`、预算 500、已花 500；`continue` 空请求返回 409、同一固定文案，状态仍是 `awaiting_user`；带 `add_budget=100` 后返回 200，预算变为 600。
- 用 `monkeypatch` 把 `runner.start_group` 替换为空操作，避免为这两个只验证检查分支的用例制造后台任务。

### T19（S9，移除「先暂停再结束」检查）

`test_discuss_api.py::test_close_rejects_planning_or_running_until_paused`

- 群先置 `planning`（带令牌、没有后台任务），`POST close` 返回 409，`detail` 是「先暂停再结束」，状态仍是 `planning`。
- 再置 `running`（同样没有后台任务），`POST close` 同样 409，状态仍是 `running`。
- `POST pause` 返回 200、状态 `paused`；再 `POST close` 返回 200、状态 `closed`。

## 第三节：偶发 error 的排查与修复

### 结论

根因在 `backend/discuss/runner.py` 的取消/关停逻辑，不是测试用例本身的清理问题。

旧实现 `cancel_group` 的分支：

```python
await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
    cancel_and_drain(), task.get_loop()))
```

它在等的是「把 `cancel_and_drain()` 调度到任务所属事件循环后返回的 future」。如果这个任务的循环已经关闭，`run_coroutine_threadsafe` 内部的 `loop.call_soon_threadsafe` 会立即抛 `RuntimeError: Event loop is closed`；如果循环只是停止、还没有关闭，future 永远不会完成，调用方就会一直等。`shutdown_discuss_tasks()` 在 lifespan 关停里调用 `cancel_group`，这个异常没有被捕获，于是 `TestClient` 的夹具收尾变成 `error`，不是用例断言 `failed`。

`TASKS` 里出现这种任务的原因：旧 `cancel_group` 处理完任务后没有从 `TASKS`/`_owners` 移除条目；`start_group` 注册的 done 回调依赖任务事件循环继续运行，循环一旦先关闭，回调不会再执行。任何一次没有在循环关闭前被 `shutdown_discuss_tasks` 排干的任务，都会留在模块级 `TASKS` 里，被下一个 `client` 用例的关停流程再次处理，从而触发上面这行。

### 证据

- 在约 200 次「按文件顺序、带 `-x` 跑全部 `tests/test_discuss_*.py`」的观察里，问题是低频的；本轮我用 4 个并行循环跑了 60 次 `tests/test_discuss_api.py`（有机器负载），没有复现原始 traceback。
- 用确定性方式复现同一失败点：在临时克隆里把 `cancel_group` 还原成旧实现，构造一个已经关闭事件循环的 pending 任务并放进 `TASKS`，运行新增回归用例，得到：

```text
discuss/runner.py:117: in cancel_group
    await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
...
RuntimeError: Event loop is closed
```

- 修复后同一个用例通过（8 passed）。
- 原始 17.8 秒没有抓到 traceback。能确定的是报错点在上述 `wrap_future`/`run_coroutine_threadsafe`，不是 15 秒等待本身；耗时应来自该用例准备/收尾与关停过程中前面的数据库、取消等操作累积，最后才在这个死循环调度上暴露。没有证据支持「某个固定 15 秒超时」的说法，因此没有按超时去改。

### 修复内容

`backend/discuss/runner.py` 的 `cancel_group`：

1. 需要跨事件循环取消时先检查 `task.get_loop().is_closed()` 和 `is_running()`；循环已关闭或已停止时只 `task.cancel()`，不把协程调度到死循环上，也不等待它的 future。
2. 对「检查时还在运行、调度时刚好停止」的竞态，捕获 `RuntimeError` 并改为 detach（`task.cancel()`），不把异常抛给 lifespan。
3. 处理完任务后在 `finally` 里把该条目从 `TASKS`/`_owners` 移除（仅当条目仍指向同一个 task），下一次关停不再重试死任务。done 回调仍保留，正常任务不受影响。
4. 同事件循环或另一仍运行的事件循环上的任务，仍按原来的 `cancel_and_drain` 语义等待收尾，没有放宽取消。

回归用例：`test_discuss_runner.py::test_cancel_group_detaches_task_on_closed_loop_and_clears_token`

- 建一个 running 群，写一个新令牌。
- 在一个新事件循环里创建 pending task 后关闭该循环，把 task 放进 `runner.TASKS`/`_owners`。
- `asyncio.wait_for(runner.shutdown_discuss_tasks(), timeout=2)` 必须正常返回；随后 `TASKS` 没有该群，库里的 `run_token` 已清空。
- 旧实现会在同一行抛 `RuntimeError: Event loop is closed`，用例失败；新实现通过。

## 验收四条

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试连跑 10 次

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

10 次结尾行：

```text
RUN 1 exit=0 | 149 passed, 45 warnings in 10.81s
RUN 2 exit=0 | 149 passed, 45 warnings in 11.21s
RUN 3 exit=0 | 149 passed, 45 warnings in 11.71s
RUN 4 exit=0 | 149 passed, 45 warnings in 11.12s
RUN 5 exit=0 | 149 passed, 45 warnings in 10.90s
RUN 6 exit=0 | 149 passed, 45 warnings in 10.86s
RUN 7 exit=0 | 149 passed, 45 warnings in 10.75s
RUN 8 exit=0 | 149 passed, 45 warnings in 10.78s
RUN 9 exit=0 | 149 passed, 45 warnings in 10.72s
RUN 10 exit=0 | 149 passed, 45 warnings in 11.12s
```

10 次都 149 passed、0 跳过、退出码 0。

### 2. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

输出摘要：`8501 passed, 47 warnings in 404.93s (0:06:44)`。退出码 `0`，0 失败、0 跳过。基线 8352 + 本轮 149 = 8501；全量收集数也是 8501。

各讨论群文件收集数：api 24、billing 18、docs 19、engine 43、runner 8、schemas 33、structure 4，合计 149。

### 3. S8/S9 变异自检

命令：

```text
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> S8 S9
```

原始输出：

```text
正控（未改动）：exit=0 149 passed, 45 warnings in 13.14s
S8   杀死  预算用完也能继续  [1 failed, 22 passed, 45 warnings in 4.26s]
S9   杀死  在跑时也能结束  [1 failed, 23 passed, 45 warnings in 4.31s]
收尾正控（全部还原后）：exit=0 149 passed, 45 warnings in 10.89s
非断言失败的「杀死」：[]
合计 2，杀死 2，存活 []，锚点缺失 []
```

两条都是 `1 failed`，不是 `error`；脚本自己列出「非断言失败的杀死」为空。结果 JSON 汇总为 `{"total": 2, "killed": 2, "survived": [], "anchor_missing": [], "restored_ok": true}`。克隆目录与结果文件用完后已删除。

### 4. 改动范围

`git status --porcelain --untracked-files=all` 当前共 48 条。

- 与 R1 交付的 46 条相比，没有删除任何路径。
- 新增 2 条：规格作者在本次返修开始前放好的 `docs/tasks/2026-11-14-agent-group/06-fix-r2.md`，以及本报告 `docs/tasks/2026-11-14-agent-group/impl/report-r2.md`。
- 内容变动只在本单允许的 `backend/discuss/runner.py`、`backend/tests/test_discuss_api.py`、`backend/tests/test_discuss_runner.py`。
- 其余实现文件、文档、其他测试文件未改；R1 的 6 条材料、R2 的返修单与首轮任务文档原样保留。
- `CLAUDE.md` 仍是 68,431 字节；9 条已跟踪文件的 `git diff --stat` 与 R1 一致（80 insertions / 6 deletions）。

## 未完成或需要人工确认

1. **原始 17.8 秒报错没有抓到 traceback**，也没有在 60 次负载压力中复现。已确定并修复的是 `cancel_group` 对已关闭/已停止事件循环任务的死循环调度：旧实现在确定性复现里抛 `RuntimeError: Event loop is closed`，修复后通过。若规格作者后续再次遇到，建议保留完整 pytest traceback 以确认是否同一行。
2. **T18/T19 只验证接口检查分支**：为了不制造后台任务，T18 把 `runner.start_group` 临时替换为空操作，T19 用数据库状态直接构造 planning/running。这与已有场景 15 的写法一致，不影响被变异改坏的检查分支的判别。
3. **回归用例使用已关闭事件循环的 pending task**：这是对真实泄漏路径的最小化复现；正常任务路径（同循环取消、另一运行中循环取消）的既有用例继续通过。
4. 没有真起服务、没有调用真实模型/搜索；S8/S9 变异正控与全量都在离线测试环境完成。
