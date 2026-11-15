# 返修单 R1 实施报告：多智能体讨论群第一期

依据 `docs/tasks/2026-11-14-agent-group/02-spec.md`（v1.1）与返修单 `05-fix-r1.md`。首轮交付仍在工作区，本轮只改 `backend/discuss/engine.py`、四个 `test_discuss_*.py`，并新增本报告；没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`。

## 拆分表

| 轮次 | agent | 负责文件 | 结果 |
|---|---|---|---|
| R1 | engine | `backend/discuss/engine.py`、`backend/tests/test_discuss_engine.py` | ok：P1–P3 + T2、T4–T8，新增 12 个用例 |
| R1 | billing-tests | `backend/tests/test_discuss_billing.py` | ok：T3、T9、T12，新增 6 个用例 |
| R1 | api-tests | `backend/tests/test_discuss_api.py` | ok：T1、T14–T16，新增 4 个用例 |
| R1 | runner-tests | `backend/tests/test_discuss_runner.py` | ok：T10、T11、T13、T17，新增 4 个用例 |

四个 agent 并行、文件不重叠；任务说明都写明不得调用 subagent/subagent_fork/workflow、不得改别人负责的文件、不得运行 `mut_discuss.py`。变异自检由主代理统一执行。没有 agent 失败。

## P1–P3 改了什么

### P1 同一成员的多条任务合并

`engine.py` 新增私有 `_merge_assignments(assignments)`：按 `role` 保持首次出现顺序；同一成员的非空 `task` 用中文分号「；」连接成一条；空 task 不参与连接；输出每位成员一项。

- 第 1 轮初始化、裁决 `decision == "research"`、返工 `rNN/60-rework-host` 三个来源都走这个 helper。
- 合并后每位成员每轮只 `investigate` 一次；`tasks_by_role` / `queries_by_role` / `results_by_role` 改为按唯一 role 直接赋值，不再用 `setdefault` 丢掉后面的任务，也不再重复合并查询与搜索结果。
- 测试：`test_p1_rework_merges_tasks_for_same_member`（返工来源）、`test_p1_research_decision_merges_tasks_for_same_member`（裁决来源）。两条都断言下一轮该成员只有一个 `r02/10-queries-market` 调用、载荷 `assignment` 是「补查小团队样本；补查定价区间」、搜索步骤键是 `r02/11-search-market-1/2` 且没有重复。

### P2 重放不倒退轮次

`run_rounds` 读群时记录 `current_round = int(group["round"] or 0)`；循环里只在 `r > current_round` 时调用 `await store.update_group(round=r)`，成功后才更新内存值。重放第 1、2 轮时不再把库里已经到第 3 轮的群写回 1、2。

测试：`test_p2_replay_never_rewinds_round`。把群置为 `running`、`round=2`、有令牌，包一层记录 `store.update_group` 收到的 `round`，执行 `engine.run_rounds`；断言记录里没有 1，所有值 ≥2，最终库里的 round 是 3。

### P3 返工要求截断 300

`rework = [str(item)[:160] ...]` 改为 `[:300]`。验收校验器本身已按 4.7 把每条要求截到 300，因此 250 字完整保留、400 字落成 300 字。

测试：`test_p3_rework_requirements_keep_300_chars`。让验收返回 250 字与 400 字两条要求，断言 `r01/60-rework-host` 载荷里第一条完整 250 字、第二条恰好 300 字。

## T1–T17 对应测试函数

| 编号 | 变异 | 测试函数 |
|---|---|---|
| T1 | E3 完成后按意见返工 | `test_discuss_api.py::test_done_continue_with_note_reworks_and_adds_second_version` |
| T2 | E7 驳回的质疑不再下发 | `test_discuss_engine.py::test_t2_rejected_objection_not_in_next_note`、`::test_t2_rejected_objection_targeting_next_member_not_sent` |
| T3 | E10 分身余额/预算异常照常上抛 | `test_discuss_billing.py::test_avatar_brief_billing_error_pauses_group[insufficient]`、`[budget]` |
| T4 | E11 返工轮 `previous_draft` 是上一版全文 | `test_discuss_engine.py::test_t4_previous_draft_is_previous_version_full_text` |
| T5 | E14 第二轮 `your_previous_points` 是第一轮要点 | `test_discuss_engine.py::test_t5_previous_points_reach_second_round_note` |
| T6 | E17 `objections_to_address` 只含本人与 overall | `test_discuss_engine.py::test_t6_objections_only_target_member_and_overall` |
| T7 | E18 撰稿/验收的 `sources` 只含被要点引用的 | `test_discuss_engine.py::test_t7_sources_only_include_cited` |
| T8 | E24 有分身时 `owner_view` 到验收与返工 | `test_discuss_engine.py::test_t8_avatar_owner_view_reaches_accept_and_rework`、`::test_t8_no_avatar_owner_view_is_null` |
| T9 | B5 搜索固定扣费受预算约束 | `test_discuss_billing.py::test_search_fixed_fee_respects_budget_without_reserving`、`::test_search_budget_pause_via_runner` |
| T10 | N1 已有令牌不再起第二个任务 | `test_discuss_runner.py::test_start_group_with_existing_token_does_not_start_second_task` |
| T11 | N2 有 users 表、没有 discuss_groups 表时恢复直接返回 | `test_discuss_runner.py::test_recover_returns_with_users_but_no_discuss_groups_table` |
| T12 | N6 取消时退还全部预扣 | `test_discuss_billing.py::test_cancel_after_model_reservation_refunds_precharge`、`::test_cancel_after_search_reservation_refunds_all_precharges` |
| T13 | N7 自带模型不可用映射 paused/byok_unavailable | `test_discuss_runner.py::test_byok_unavailable_pauses_with_fixed_error` |
| T14 | S6 done 无未读插话时 continue 409 | `test_discuss_api.py::test_done_continue_without_note_is_409_then_note_allows_rework` |
| T15 | S10 没有成果时 accept 409 | `test_discuss_api.py::test_accept_without_any_output_is_409` |
| T16 | S11 开工版本不符 409 且仍 awaiting_start | `test_discuss_api.py::test_start_with_stale_revision_is_409_and_keeps_awaiting_start` |
| T17 | T1 旧令牌写库不生效 | `test_discuss_runner.py::test_stale_token_store_cannot_write_message_status_or_output` |

新增用例共 26 个：engine 12、billing 6、api 4、runner 4。讨论群测试总数从 120 增加到 146。

## 验收四条

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

输出摘要：`146 passed, 45 warnings in 10.20s`。退出码 `0`，0 跳过。

各文件收集数：`test_discuss_api.py` 22、`test_discuss_billing.py` 18、`test_discuss_docs.py` 19、`test_discuss_engine.py` 43、`test_discuss_runner.py` 7、`test_discuss_schemas.py` 33、`test_discuss_structure.py` 4，合计 146。

### 2. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

输出摘要：`8498 passed, 47 warnings in 394.96s (0:06:34)`。退出码 `0`，0 失败、0 跳过。基线 8352 + 本轮 146 = 8498；全量收集数也是 8498。

### 3. 改动范围

`git status --porcelain --untracked-files=all` 与首轮交付相比：

- 没有删除首轮的任何路径。
- 首轮交付的 39 条路径原样保留（9 条已修改 + 19 条新增 + 10 条派单任务文档 + 首轮报告）。
- 新增 6 条 R1 材料（`05-fix-r1.md`、`verify/mut_discuss.py`、`verify/walk_discuss.py`、`verify/walk-r0/` 三个文件），它们在本次返修开始前就由规格作者放好，不是本次产生的，本次只读。
- 新增 1 条本报告 `docs/tasks/2026-11-14-agent-group/impl/report-r1.md`。
- 本轮内容变动只在 `backend/discuss/engine.py` 和四个测试文件（`test_discuss_engine.py`、`test_discuss_billing.py`、`test_discuss_api.py`、`test_discuss_runner.py`）；`service.py`、`store.py`、`billing.py`、`runner.py`、`research.py`、`avatar.py`、`config.py`、`roles.py`、`schemas.py`、`routers/discuss.py`、`main.py`、`database.py`、文档与其余三个测试文件均未改。
- 9 条已跟踪文件的 `git diff --stat` 与首轮一致：`80 insertions(+), 6 deletions(-)`；`CLAUDE.md` 仍是 68,431 字节。

最终状态共 46 条：首轮 39 条 + R1 材料 6 条 + 本报告 1 条。没有 `__pycache__`、数据库、上传文件等被列出。

### 4. 变异自检

命令：

```text
backend/.venv/bin/python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <系统临时目录下的新目录> <系统临时目录下的结果文件.json> E3 E7 E10 E11 E14 E17 E18 E24 B5 N1 N2 N6 N7 S6 S10 S11 T1
```

脚本原始输出：

```text
正控（未改动）：exit=0 146 passed, 45 warnings in 12.77s
E3   杀死  作者要求返工被忽略  [1 failed, 18 passed, 45 warnings in 3.43s]
E7   杀死  被驳回的质疑仍留给调研成员  [1 failed, 95 passed, 45 warnings in 8.94s]
E10  杀死  分身步骤吞掉余额与预算异常  [1 failed, 34 passed, 45 warnings in 4.70s]
E11  杀死  撰稿人拿不到上一版  [1 failed, 96 passed, 45 warnings in 9.04s]
E14  杀死  调研成员看不到自己之前的要点  [1 failed, 97 passed, 45 warnings in 9.33s]
E17  杀死  针对本人的质疑不下发  [1 failed, 94 passed, 45 warnings in 8.75s]
E18  杀死  撰稿人拿到全量来源  [1 failed, 99 passed, 45 warnings in 9.44s]
E24  杀死  验收人拿不到分身的意见  [1 failed, 100 passed, 45 warnings in 9.61s]
B5   杀死  搜索不查预算  [1 failed, 36 passed, 45 warnings in 4.84s]
N1   杀死  已有令牌仍然再起一个任务  [1 failed, 105 passed, 45 warnings in 10.08s]
N2   杀死  恢复时不先查表是否存在  [1 failed, 106 passed, 45 warnings in 10.12s]
N6   杀死  取消任务时不退还预扣  [1 failed, 39 passed, 45 warnings in 5.00s]
N7   杀死  自带模型不可用没有暂停原因  [1 failed, 107 passed, 45 warnings in 10.23s]
S6   杀死  完成后没有插话也能返工  [1 failed, 19 passed, 45 warnings in 3.81s]
S10  杀死  没有成果也能接受  [1 failed, 20 passed, 45 warnings in 3.86s]
S11  杀死  开工不查版本  [1 failed, 21 passed, 45 warnings in 3.91s]
T1   杀死  后台写库不核对令牌  [1 failed, 108 passed, 45 warnings in 10.25s]
收尾正控（全部还原后）：exit=0 146 passed, 45 warnings in 10.45s
合计 17，杀死 17，存活 []，锚点缺失 []
```

结果 JSON 汇总：`{"total": 17, "killed": 17, "survived": [], "anchor_missing": [], "restored_ok": true}`。克隆目录与结果文件用完后已删除，工作区未被脚本改动。

## 未完成或需要人工确认的地方

1. **T2 的场景设计**：只按返修单描述的「O2 target=tech 被 reject、下一轮只派 market」并不能杀死 E7，因为即使变异保留被驳回的质疑，针对 tech 的质疑也会被 note 的 `target in (member, overall)` 正常过滤掉。因此除原场景外，另加了 `test_t2_rejected_objection_targeting_next_member_not_sent`：让被 reject 的质疑 target 正是下一轮继续调研的 market，正常实现不下发、E7 变异下会进入 `objections_to_address`。两条用例都在，E7 已被杀死。
2. **T12 的取消路径**：只让「模型调用进行到一半时取消」不能区分 N6。`LLMRouter` 的 `_attempt` finally 会在取消时自己 `refund` 本次模型预扣，runner 的 `refund_reserved` 只是幂等的第二层；因此另加了搜索固定预扣取消用例 `test_cancel_after_search_reservation_refunds_all_precharges`：4 个搜索预扣只能靠 runner 的 refund_reserved 退回，N6 变异下余额与群 reserved 都会不对。两个用例都保留，N6 已被杀死。
3. **变异脚本运行方式**：脚本用 macOS 的 `cp -cR` 克隆到系统临时目录，本次沙箱允许；正控和收尾正控都通过，说明克隆与还原正常。没有修改 `verify/mut_discuss.py`。
4. **新增 R1 材料**：`05-fix-r1.md`、`verify/mut_discuss.py`、`verify/walk_discuss.py`、`verify/walk-r0/` 在返修开始前已经是未跟踪文件，本次只读；它们不在本单允许改的范围内，也没有改。
5. **已有断言**：四个测试文件只新增用例、辅助函数与 import，没有删除或放宽首轮断言；既有非讨论群测试未改，全量通过。
