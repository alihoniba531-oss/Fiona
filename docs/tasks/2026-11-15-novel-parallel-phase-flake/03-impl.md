# 03 · 实施记录 — 并行阶段「失败后取消并等完兄弟调用」三条用例

- 日期：2026-11-15
- 工作树：本仓库的一个 git worktree（本机绝对路径已由门禁删去，仓库是公开的）
- 分支：`fix/novel-parallel-phase-flake`，基线 `acd04b6`（`git log -1` 实测）
- 状态：实施与 5-A 至 5-E 已完成（5-E 的原始命令被沙箱 `NO_PROXY` 挡住，干净环境下实测 `8562 passed`，详见 §4 5-E）

## 拆分表（本次派出过的全部代理）

| 代理 | 派发方式 | 负责文件 | 状态 | 返回摘要 |
|---|---|---|---|---|
| agent A | `workflow` 脚本内 `parallel()` | `backend/tests/test_novel_workflow.py`（仅此文件） | 完成 | 自报 `9	3	backend/tests/test_novel_workflow.py`；只改指定两段；未动断言/夹具/其他文件 |
| agent B | `workflow` 脚本内 `parallel()` | `backend/tests/test_novel_r5_deliberation.py`（仅此文件） | 完成 | 自报 `6	1	backend/tests/test_novel_r5_deliberation.py`；只改指定两段；未动断言/夹具/其他文件 |

两个代理的提示词均为自包含：贴出了各自文件的补丁原文、`+9 -3` / `+6 -1` 的期望数字，并明确禁止调用 `subagent` / `subagent_fork` / `workflow`、禁止 git 写命令、禁止跑测试。两个代理都不带 schema，直接返回文本。主代理未派出其他代理；没有代理失败，未发生重派。

## 1. 修改了哪些文件

| 文件 | 改动 | 说明 |
|---|---|---|
| `backend/tests/test_novel_workflow.py` | `+9 −3` | 任务 4.1，仅 §3 补丁该文件的两段 |
| `backend/tests/test_novel_r5_deliberation.py` | `+6 −1` | 任务 4.2，仅 §3 补丁该文件的两段 |
| `docs/tasks/2026-11-15-novel-parallel-phase-flake/03-impl.md` | 新增 | 本文件，任务 4.3 |

未改动：`backend/novel/`、`frontend/`、`.env*`、`verify/` 下任何文件、两个测试文件里的断言/夹具/`LocalRouter`/其他用例。未新增或删除测试，未加依赖，未 commit，未执行 `git checkout` / `git stash` / 改分支。

## 2. 实现了什么

两条用例的假模型脚本现在自己统计到达模型的角色：

- 新增 `all_started = asyncio.Event()`；每个角色在执行 `started.add(role)` / `running.add(role)` 后，如果 `len(started) == 3` 就 `all_started.set()`。
- 要失败的角色（`plot_architect`）把原来的 `await asyncio.sleep(0)` 换成 `await asyncio.wait_for(all_started.wait(), timeout=5)`，确认三个调用都已到达模型后才 `raise StepFailed()`；另外两个角色仍然 `await asyncio.sleep(10)`，等待被取消。
- 5 秒超时只是防止将来的回归把全量挂住，不改变正常路径的语义。
- 用例的九条断言语句（第二条用例为四条）一个字未动：`started` 必须是三个角色、`cancelled` 必须是另外两个、`running == set() and router.active == 0`、失败后请求数不再增加、没有 `decision` / `finalize` 请求。因此两条用例仍然证明「一个调用失败后、`deliberate` 返回之前，另外两个已到达模型的调用被取消并收尾」；把 `_gather_phase` 改坏仍会变红（5-D 的四种坏实现均为 `3 failed`）。
- `backend/novel/deliberation.py` 一个字节未动。

## 3. 与任务清单逐项对应

- **4.1**：`backend/tests/test_novel_workflow.py` 的 `test_failed_parallel_phase_cancels_and_drains_siblings_before_return`（参数 `proposal` / `critique`）已按 §3 补丁的前两段修改，由 agent A 完成，主代理复核 diff 与 `git apply -R --check` 均一致。
- **4.2**：`backend/tests/test_novel_r5_deliberation.py` 的 `test_all_advisor_calls_are_cancelled_and_drained_if_one_fails` 已按 §3 补丁的后两段修改，由 agent B 完成，同样复核一致。
- **4.3**：§5 的 5-A 至 5-E 已全部执行（5-E 结果见 §4），本文件即变更总结。
- **硬规矩 1（白名单）**：改动集合恰好是上表三个文件；任务目录其余文件与派单前哈希清单逐字节相同（派单前 17 个文件，编辑后比对无差异）。
- **硬规矩 2（不动既有测试其他部分）**：`git diff -U0 -- backend/tests | grep -c '^@@'` 为 `6`（六段改动都被扫到），含 `assert` 的增删行计数为 `0`；没有新增测试。
- **硬规矩 3（不 commit / 不碰 `.env` / 不加依赖）**：改动全部留在工作区；`git status --porcelain` 只有两个 `M` 与任务目录的 `??`；`backend/novel/`、`frontend/`、`.env*` 无改动。
- **硬规矩 4（用工作流并行）**：用 `workflow` 脚本里的 `parallel()` 同时运行 agent A / agent B，按文件不重叠拆分；两个 agent 都只返回文本、不带 schema；主代理只做拆分、派发、汇总、白名单检查、跑 §5、写本文件。
- **硬规矩 5（何时停下来问）**：实施中未遇到规格自相矛盾或无法实现的情况，未停下。
- **硬规矩 6（本文件五项）**：修改文件 / 实现内容 / 任务清单对应 / §5 实际输出 / 未完成或需人工确认，均在本文中。

## 4. §5 每条验收的实际输出

### 5-A 改动集合（仓库根）

命令：

```bash
git status --porcelain | grep -v 'docs/tasks/2026-11-15-novel-parallel-phase-flake/'
```

实际输出（恰好两行，顺序与下面一致）：

```text
 M backend/tests/test_novel_r5_deliberation.py
 M backend/tests/test_novel_workflow.py
```

完整 `git status --porcelain` 为上述两行加 `?? docs/tasks/2026-11-15-novel-parallel-phase-flake/`。任务目录内除新增本文件外，其余 17 个文件与派单前记录的 SHA-256 清单逐字节相同（`diff` 无输出）。

### 5-B 改动形状（仓库根）

`git diff --numstat -- backend/tests` 实际输出（恰好两行）：

```text
6	1	backend/tests/test_novel_r5_deliberation.py
9	3	backend/tests/test_novel_workflow.py
```

`git apply -R --check docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/proposed-change.patch`：退出码 `0`（工作区改动能被该补丁原样撤销，即与补丁一致）。

`git diff -U0 -- backend/tests | grep -c '^@@'`：输出 `6`。

`git diff -U0 -- backend/tests | grep -cE '^[-+][^-+].*assert '`：输出 `0`（grep 退出码 1，无匹配，属规格说明的正常情况）。

### 5-C 两个文件（`backend/`）

命令：

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_workflow.py tests/test_novel_r5_deliberation.py
```

实际输出：

```text
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 0.31s
```

0 失败、0 跳过。

### 5-D 对照矩阵（`backend/`）

命令：

```bash
.venv/bin/python ../docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/run_matrix.py repo
```

实际输出（退出码 `0`）：

```text
form: repo
  no pause                                 | 3 passed | 3 passed | 3 passed
  pause 0.2 ms before twist_designer       | 3 passed | 3 passed | 3 passed | 3 passed | 3 passed
  pause 2 ms before twist_designer         | 3 passed | 3 passed | 3 passed
  pause 20 ms before twist_designer        | 3 passed | 3 passed | 3 passed
  pause 2 ms before character_advocate     | 3 passed | 3 passed | 3 passed
  pause 20 ms before character_advocate    | 3 passed | 3 passed | 3 passed
  pause 2 ms before plot_architect         | 3 passed | 3 passed | 3 passed
  broken: cancels but does not wait        | 3 failed
  broken: plain gather                     | 3 failed
  broken: runs the calls one by one        | 3 failed
  broken: waits but does not cancel        | 3 failed
VERDICT: SOUND
```

### 5-E 全量（`backend/`）

规格原文命令：

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
```

**在本沙箱里这条命令没有跑到任何用例，卡在收集阶段**，实际输出末尾：

```text
!!!!!!!!!!!!!!!!!!! Interrupted: 20 errors during collection !!!!!!!!!!!!!!!!!!!
4 warnings, 20 errors in 8.07s
EXIT_CODE=2
```

20 个收集错误模块（每一条都是同一个 `httpx.InvalidURL: Invalid port: ':1]'`）：

```text
tests/test_byok_client.py
tests/test_byok_effort.py
tests/test_byok_image_tool.py
tests/test_byok_pending_image_access.py
tests/test_chat_branches.py
tests/test_claude_agent_client.py
tests/test_claude_agent_integration.py
tests/test_claude_agent_r1_client.py
tests/test_claude_agent_r1_integration.py
tests/test_event_loop_slots.py
tests/test_exchange_poll_connection.py
tests/test_exchange_workflow_store.py
tests/test_image_intent_precision.py
tests/test_image_planner.py
tests/test_novel_chat.py
tests/test_novel_chat_create.py
tests/test_novel_chat_feedback.py
tests/test_song_agent_tools.py
tests/test_weather_daily_cap.py
tests/test_weather_intent.py
```

根因（与本次改动无关）：本沙箱环境注入 `NO_PROXY=localhost,127.0.0.1,::1,.local,[::1]`。`httpx` 0.28 在 `llm.py` 构造 `OpenAI` 客户端时，把带方括号的 `[::1]` 当作 URL 解析，抛 `httpx.InvalidURL: Invalid port: ':1]'`，堆栈为 `llm.py` → `openai.OpenAI` → `httpx.Client`。错误发生在测试模块 import 阶段、早于任何夹具；`backend/tests/test_studio_cross_review.py` 里已有注释记录本机这个 `[::1]` 问题。按规格「不要为此改动任何文件」，没有修改任何测试、源码或环境文件。

为取得可用的全量证据，只对本次 pytest 进程覆盖这两个环境变量（不改文件、不改仓库）。先验证收集条数：

```bash
NO_PROXY='localhost,127.0.0.1,::1,.local' no_proxy='localhost,127.0.0.1,::1,.local' \
  .venv/bin/python -m pytest --collect-only -q -p no:cacheprovider
```

实际输出末尾：

```text
8562 tests collected in 9.10s
```

与改动前 `acd04b6` 的 8562 一致（没有新增或删除用例）。同一覆盖下跑全量：

```bash
NO_PROXY='localhost,127.0.0.1,::1,.local' no_proxy='localhost,127.0.0.1,::1,.local' \
  .venv/bin/python -m pytest -q -p no:cacheprovider
```

实际输出（退出码 `0`，0 失败、0 跳过）：

```text
8562 passed, 47 warnings in 457.19s (0:07:37)
EXIT_CODE=0
```

按规格，5-E 最终以 Claude 在沙箱外重跑的结果为准；上面记录的是本沙箱的原始复现与绕过环境变量后的实测。干净环境下条数、失败数、跳过数与规格要求一致（`8562 passed`，`47 warnings` 与基线相同）。

## 5. 未完成或需人工确认的地方

- **5-E 的原始命令被沙箱环境挡住**：`NO_PROXY` 里的 `[::1]` 让 httpx 在 20 个测试模块 import `llm` 时抛 `InvalidURL`，收集阶段即中断，未跑到任何用例。已按规格如实记录完整清单，没有为此刻意修改任何文件；绕过方式是仅对 pytest 进程覆盖 `NO_PROXY` / `no_proxy`，收集数 8562 与基线一致，覆盖后全量实测 `8562 passed, 47 warnings`（0 失败、0 跳过，退出码 0）。按规格，这一条最终以 Claude 在沙箱外重跑的结果为准。
- **门禁附加正控未由执行者运行**：按规格 §5 最后一段，`gc_sweep.py --whole-file ... --expect-sound` 由 Claude 在执行者沙箱外重跑，执行者不必执行；本次未运行该命令，也未改动 `verify/`。
- **主检出里那份未提交改动**：按 §0 第 3 条，本任务没有查看、没有改动主检出；它与本补丁改同一段，合入 main 前需作者决定丢弃还是保留。
- 未 commit（按硬规矩 3），改动留在工作区，供门禁复核。
