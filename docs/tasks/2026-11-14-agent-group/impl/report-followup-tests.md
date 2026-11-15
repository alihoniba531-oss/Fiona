# 门禁补单：四条用例报告

依据 `04-review-followup.md` 第 4 节第 1、2 条与第 5.3、5.4 节。只补测试，没有改任何实现文件；没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`，没有访问真实模型/搜索。

## 新用例

| 变异 | 用例 | 覆盖点 |
|---|---|---|
| V14b | `test_resume_refund_failure_rolls_back_state` | resume 的退款仍在状态事务里；退款函数抛错时接口报错，群字段、预扣、余额、步骤状态都与调用前相同，没有起后台任务 |
| V14c | `test_continue_refund_failure_rolls_back_state` | continue 同上，另比较 `max_rounds` |
| V14d | `test_close_refund_failure_rolls_back_state` | close 未结束分支同上，状态不会变成 `closed` |
| V17 | `test_unexpected_error_without_cancel_is_failed_error` | 没有取消时 `run_planning` 抛普通 `RuntimeError`，最终 `failed/error`、令牌为空 |

三条退款原子性用例都：

- 用付费模式造出「群已停下、留一条 `billing_status='reserved'` 的步骤、余额已预扣」；
- 在调用前读一次群、步骤和余额，作为 `before_*`；
- 把 `discuss.store.refund_reserved_on_connection` 换成抛 `RuntimeError` 的替身；
- 同时把 `runner.start_group` 换成记录调用的替身；
- 断言接口抛错、调用前后所有被点名字段逐一相等、步骤仍 `reserved`、余额不变、`start_group` 调用记录为空、`runner.TASKS` 里没有该群。

V17 用例在 `planning` 群上把 `engine.run_planning` 换成直接抛 `RuntimeError`，等后台任务结束后断言 `failed/error`、`run_token is None`；没有任何取消。

## 自检

执行：

```text
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> V14 V14b V14c V14d V14e V15 V17 X18 X19
```

原始输出：

```text
正控（未改动）：exit=0 210 passed, 45 warnings in 36.38s
X18  杀死  恢复时意外异常记成失败  [1 failed, 163 passed, 45 warnings in 21.40s]
X19  杀死  平时步骤失败记成失败状态  [1 failed, 164 passed, 45 warnings in 26.56s]
V14  杀死  开工时退残留预扣回到状态事务之外  [1 failed, 69 passed, 45 warnings in 12.79s]
V15  杀死  任务已被取消时仍按同时发生的失败写停止原因  [1 failed, 170 passed, 45 warnings in 22.76s]
V14b 杀死  继续时退残留预扣回到状态事务之外  [1 failed, 72 passed, 45 warnings in 11.82s]
V14c 杀死  追加轮数时退残留预扣回到状态事务之外  [1 failed, 73 passed, 45 warnings in 11.73s]
V14d 杀死  结束时退残留预扣回到状态事务之外  [1 failed, 74 passed, 45 warnings in 11.41s]
V14e 杀死  接受成果时退残留预扣回到状态事务之外  [1 failed, 70 passed, 45 warnings in 16.09s]
V17  杀死  平时意外异常不记成失败状态  [1 failed, 172 passed, 45 warnings in 33.09s]
收尾正控（全部还原后）：exit=0 210 passed, 45 warnings in 27.39s
非断言失败的「杀死」：[]
合计 9，杀死 9，存活 []，锚点缺失 []
```

结果 JSON 汇总：`{"total": 9, "killed": 9, "survived": [], "anchor_missing": [], "restored_ok": true}`。克隆与结果文件已删除。

四条新用例对应的变异：

- V14b：`test_resume_refund_failure_rolls_back_state`
- V14c：`test_continue_refund_failure_rolls_back_state`
- V14d：`test_close_refund_failure_rolls_back_state`
- V17：`test_unexpected_error_without_cancel_is_failed_error`

另外五条 V14/V14e/V15/X18/X19 由已有用例杀死，本轮复跑确认仍为 `1 failed`。

## 验收

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

结果：`210 passed, 45 warnings in 30.17s`，退出码 0，0 跳过。

各文件收集数：api 39、billing 36、docs 20、engine 49、runner 29、schemas 33、structure 4，合计 210。

### 2. 变异自检

见上节，9/9 杀死，全部 `1 failed`，没有 `error`/超时。

### 3. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8562 passed, 47 warnings in 522.17s (0:08:42)`，退出码 0，0 失败、0 跳过。基线 8352 + 210 = 8562；全量收集数 8562。

本次全量一次通过，没有出现 `test_novel_workflow.py` 的已知时序 flake，因此没有单独重跑记录。

### 4. 改动范围

`git status --porcelain --untracked-files=all` 当前共 14 条：

- 本单新增/修改：`backend/tests/test_discuss_billing.py`、`backend/tests/test_discuss_runner.py`、`docs/tasks/2026-11-14-agent-group/impl/report-followup-tests.md`。
- 本单派出前已经存在的返修改动与材料，本轮未触碰：`backend/discuss/{billing,runner,service,store}.py`、`backend/tests/test_discuss_api.py`、`docs/tasks/2026-11-14-agent-group/02-spec.md`、`verify/mut_discuss.py`、`04-review-followup.md`、`11-followup-tighten.md`、`12-followup-tests.md`、`impl/report-followup.md`。

相对本单派出时，变动的只有两个允许的测试文件和本报告；实现文件、`verify/`、`conftest.py`、规格与复核材料均未由本单修改。

## 未完成或需要人工确认

1. 工作区在本单派出前已带有上一小单的未提交实现/测试、规格修改和复核材料；本单按规矩没有回滚或提交它们，因此 `git status` 仍会显示这些历史脏文件。相对本单派出时的新增只有两个测试文件和本报告。
2. V17 用例只覆盖非恢复模式；恢复模式的 `server_restart_failed` 由已有 X18 用例覆盖，非取消的步骤失败由 X19 覆盖。
3. 三条退款原子性用例用同一个退款函数替身同时验证状态回滚和“未起任务”；没有单独测试 `start_group` 内部抛错的分支。
