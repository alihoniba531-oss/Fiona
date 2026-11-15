# 复核返修第 1 轮实施报告：多智能体讨论群第一期

依据 `docs/tasks/2026-11-14-agent-group/02-spec.md` v1.2、`04-review.md`、`verify/lock-root-cause.md`。没有 commit/stash/checkout/reset，没有装依赖，没有读 `.env`，没有访问真实模型/搜索。

## 拆分表

| 轮次 | 执行者 | 负责文件 | 内容 | 结果 |
|---|---|---|---|---|
| 实现并行 | avatar agent | `backend/discuss/avatar.py` | M1：三处 `agent_store` 调用套 `NovelBilling._drain` | ok |
| 实现并行 | service agent | `backend/discuss/service.py` | M1 detail 复用分身名、M2、F、G | partial（唯一失败为旧 T18 用例与 M2 新行为冲突，测试轮已修正 setup） |
| 实现并行 | engine agent | `backend/discuss/engine.py` | M3 身份行独占一行、H 的 `draft=""` | ok |
| 实现并行 | runner agent | `backend/discuss/runner.py` | E：认领令牌后取消补偿 | ok |
| 实现并行 | store agent | `backend/discuss/store.py` | F：删群事务退 reserved 预扣 | ok |
| 实现并行 | roles/docs agent | `backend/discuss/roles.py`、`README.md`、`docs/ARCHITECTURE.md`、`CLAUDE.md` | H 隐私说明追加一句并同步文档 | ok |
| 测试并行 | engine-tests agent | `backend/tests/test_discuss_engine.py` | M3 精确断言、X12/X15/X34/X35/X14/X37 | partial（X14 断言写成了「取消兄弟」，与当前 wait-all 实现不符，主代理按实现/复核原意修正测试） |
| 测试并行 | billing-tests agent | `backend/tests/test_discuss_billing.py` | M4 四条、F 两条、M2-paid | ok（主代理后续把付费 pause/delete 的快照改成稳定轮询，消除一次竞争性 flake） |
| 测试并行 | api-tests agent | `backend/tests/test_discuss_api.py` | M2-free、G、X22/X30/X31/X32/X33/X27/X28/X39/X44 | ok |
| 测试并行 | runner-tests agent | `backend/tests/test_discuss_runner.py` | A 两条、E、X17/X18/X19/X20；只追加在作者补充段之后 | ok |
| 集成 | 主代理 | 上述文件 + `impl/report-review-r1.md` | X14 测试修正、billing 稳定快照、全量验收、自检 | ok |

实现文件按一个文件一个 agent 并行；测试文件按一个文件一个 agent 并行。runner 测试文件末尾「R3 门禁后由规格作者补充」两段没有改动，新增用例全部在其后。

## A–I 逐条

### A. 分身路径取消保护（M1）

- `avatar.py`：`build_avatar_system` 的 `agent_store.get_my_agent`、`get_memory_snapshot`，以及 `display_name` 的 `get_my_agent` 全部改为 `await NovelBilling._drain(...)`。
- `service.py`：`detail` 一次请求最多 `await avatar.display_name` 一次；`_avatar_member` 新增可选 `name` 参数，detail 复用同一个 `avatar_name` 渲染成员与消息。
- 全库只找到 `avatar.py` 三处调用其他模块的写事务函数；`engine`/`service` 都是通过 `avatar` 间接调用，现已覆盖。
- 新用例：`test_cancelled_avatar_system_for_leaves_no_write_lock_during_cleanup`、`test_cancelled_avatar_display_name_leaves_no_write_lock_during_cleanup`。

### B. 继续不能跳过开工（M2）

- `service.resume` 的状态判据改为 `round == 0` 时回 `planning`，否则 `running`；不再用 `plan_revision`。
- 免费路径用例：`test_avatar_brief_pause_then_resume_waits_for_start`（暂停后 resume 停在 `awaiting_start`，没有 `r01/` 步骤/消息，brief 重试，之后作者 start 可跑完）。
- 付费路径用例：`test_paid_resume_after_brief_insufficient_funds_waits_for_start`（brief 余额不足暂停，加余额 resume 后停在 `awaiting_start`，余额减少量等于 spent）。
- 旧 `test_resume_and_continue_reject_exhausted_budget_until_added` 的 setup 补成 `round=1`，保留原有预算断言，不再与 M2 冲突。

### C. 身份设定独占一行（M3）

- `engine._system`：`prompt` +（有身份设定时）`"\n" + identity_line` + `RULES`，JSON 步骤再接 `JSON_RULE`；没有身份设定时与原来逐字相同。
- `test_host_identity_line_and_plan_edits` 与 `test_empty_persona_removes_identity_line` 的子串断言改成整段 system 精确比较，覆盖 decide 的 JSON 步骤和 draft 文本步骤，包含有/无身份设定两种公式。

### D. 付费路径用例（M4）

`test_discuss_billing.py` 新增：

- `test_pause_while_paid_call_blocked_refunds_reservation`
- `test_delete_while_paid_call_blocked_refunds_reservation`
- `test_paid_continue_reuses_ok_steps_and_charges_only_new_spend`
- `test_stale_token_cannot_reserve_or_reserve_fixed`

后两组对应用例覆盖 X1/X4；pause/delete 覆盖 X25/X26。付费 pause/delete 用 `stable_paid_snapshot` 等到预扣稳定且余额等式成立再断言，避免在预留/结算并发时读到中间值。

### E. 认领令牌后被取消

- `runner.start_group`：`run_write(claim_token)` 返回后若收到 `CancelledError`，先用受保护的 `run_write(clear_token)` 清掉「只等于自己刚认领值」的令牌，再 `raise`。
- 新用例：`test_cancelled_start_group_claim_clears_token_and_leaves_no_task`。

### F. 残留预扣

- `service.start`、`resume`、`continue_group`：在 `runner.start_group` 之前 `await billing.DiscussBilling(username, group_id).refund_reserved()`。
- `store.delete_group`：在同一受保护事务里先汇总 `billing_status='reserved'` 的 `strawberries_reserved`，退回 `users.strawberry_balance`，再删除五张表行；只退 reserved，不重复退 settled/refunded。
- 新用例：`test_resume_refunds_stale_reservation_before_replanning`、`test_delete_refunds_stale_reservation_when_cancel_is_noop`。后者把 `runner.cancel_group` 替换为空操作，专门证明删群事务自身会退款。

### G. 名字与重名

- `_parse_identities`：固定席位 name 允许空字符串，表示清除自定义名字；`_seat_name` 原有回退默认名逻辑不动。persona 空字符串清除不变；persona 超过 300 字仍 422。
- `_parse_members`：建群时 role 成员最终 name 与 custom 成员 name 一起查重，重复 422。
- 新用例：`test_patch_identity_clears_name_and_persona`、`test_create_group_rejects_duplicate_member_names`、`test_patch_identity_persona_over_300_is_422`。

### H. 两处小改

- `engine.run_rounds` 开头 `draft = ""`，删除 `latest_output` 初值查询；重放/续跑既有用例全部通过。
- `roles.PRIVACY_NOTICE` 末尾追加「联网搜索按次另扣草莓，与成员用哪个模型无关。」；同步 `README.md` 讨论群隐私段、`docs/ARCHITECTURE.md` 讨论群隐私段、`CLAUDE.md` 讨论群隐私段。CLAUDE.md 当前 68,497 字节（≤69,300）。

### I. 测试缺口

新增用例与变异自检见下表；另新增：

- `test_create_group_materials_crisis_is_400_without_row`（X22）
- `test_detail_after_only_returns_newer_messages`（X30）
- `test_start_rejects_when_other_group_is_running`、`test_resume_rejects_when_other_group_is_running`、`test_continue_rejects_when_other_group_is_running`（X31–X33）
- `test_group_list_is_capped_at_fifty`（X27）
- `test_patch_removing_member_clears_its_model`（X28）
- `test_patch_new_custom_member_skips_used_codes`（X39）
- `test_patch_identity_persona_over_300_is_422`（X44）
- `test_recovering_step_failure_pauses_with_server_restart_failed`（X17）
- `test_recovering_unexpected_error_pauses_with_server_restart_failed`（X18）
- `test_step_failure_without_recovery_pauses_with_step_failed`（X19）
- `test_max_running_limits_concurrent_planning`（X20）
- `test_x12_rework_payload_includes_verbatim_citation_issue`、`test_x15_avatar_brief_context_reaches_draft_writer`、`test_x34_collect_findings_truncates_fact_to_160`、`test_x35_note_payload_only_includes_member_sources`、`test_x14_gather_all_settles_siblings_before_raising`、`test_x37_avatar_effective_model_prefers_byok_and_configured`。

#### X14 的说明

复核正文说 X14 是「`_gather_all` 改回普通 `gather` 后存活，失败后兄弟任务还在跑」。当前实现是 `wait for every parallel step, then re-raise`，即等兄弟步骤收尾后才抛出，不是强制取消它们。新用例断言「抛出时两个兄弟都已 finally 收尾」；普通 `gather` 会在兄弟完成前抛出，因此会失败。实际行为与实现/复核正文一致；如果要求的是「取消兄弟」而不是「等兄弟收尾」，则需要另改实现，本轮未擅自改行为。

## 自检表

以下变异都在系统临时目录的克隆里执行，运行后还原并删除；失败均为 `failed`，不是 `error`/超时。表中「失败摘要」是 pytest 结尾行。

| 项 | 改坏方式 | 由哪条用例发现 | 失败摘要 |
|---|---|---|---|
| A | 去掉 avatar 三处 `_drain` | `test_cancelled_avatar_system_for...`、`test_cancelled_avatar_display_name...` | `2 failed in 1.42s` |
| A | 去掉 `get_memory_snapshot` 的 `_drain` | 同上（system_for 覆盖） | `1 failed in 0.72s`（该分支未被独立用例单独走到，由 system_for 主路径覆盖） |
| B | `round == 0` 改回 `plan_revision == 0` | `test_avatar_brief_pause_then_resume_waits_for_start`、`test_paid_resume_after_brief_insufficient_funds_waits_for_start` | `2 failed, 45 warnings in 24.36s` |
| C | 去掉身份行前的换行 | `test_host_identity_line_and_plan_edits`、`test_empty_persona_removes_identity_line` | `2 failed in 0.93s` |
| D/X1 | 原子结算不写步骤记录 | `test_paid_continue_reuses_ok_steps_and_charges_only_new_spend` | `1 failed in 0.88s` |
| D/X4 | 计费守卫不核对令牌 | `test_stale_token_cannot_reserve_or_reserve_fixed` | `1 failed in 0.80s` |
| D/X25 | 暂停不取消后台任务 | `test_pause_while_paid_call_blocked_refunds_reservation` | `1 failed in 2.37s`（最终版） |
| D/X26 | 删群不取消后台任务 | `test_delete_while_paid_call_blocked_refunds_reservation` | `1 failed in 0.86s`（最终版） |
| E | 去掉认领令牌后的补偿清理 | `test_cancelled_start_group_claim_clears_token_and_leaves_no_task` | `1 failed in 0.82s` |
| F | 去掉 start/resume/continue 的 `refund_reserved` | `test_resume_refunds_stale_reservation_before_replanning` | `1 failed in 0.82s` |
| F | 去掉 `delete_group` 的 reserved 退款 | `test_delete_refunds_stale_reservation_when_cancel_is_noop` | `1 failed in 0.79s` |
| G | 空 name 重新判 422 | `test_patch_identity_clears_name_and_persona` | `1 failed, 45 warnings in 1.16s` |
| G | 去掉建群成员重名检查 | `test_create_group_rejects_duplicate_member_names` | `1 failed, 45 warnings in 1.15s` |
| X12 | 返工载荷去掉引用问题 | `test_x12_rework_payload_includes_verbatim_citation_issue` | `1 failed in 0.94s` |
| X15 | 撰稿载荷 `owner_context` 置空 | `test_x15_avatar_brief_context_reaches_draft_writer` | `1 failed in 0.93s` |
| X34 | 事实不截 160 | `test_x34_collect_findings_truncates_fact_to_160` | `1 failed in 0.72s` |
| X35 | 笔记 sources 带全部来源 | `test_x35_note_payload_only_includes_member_sources` | `1 failed in 0.90s` |
| X14 | `_gather_all` 改普通 `gather` | `test_x14_gather_all_settles_siblings_before_raising` | `1 failed in 0.72s` |
| X17 | 恢复时 StepFailed 不记 server_restart_failed | `test_recovering_step_failure_pauses_with_server_restart_failed` | `1 failed in 0.78s` |
| X18 | 恢复时意外异常记 failed/error | `test_recovering_unexpected_error_pauses_with_server_restart_failed` | `1 failed in 0.78s` |
| X19 | 平时 StepFailed 记 error | `test_step_failure_without_recovery_pauses_with_step_failed` | `1 failed in 0.80s` |
| X20 | 全站并发不限 | `test_max_running_limits_concurrent_planning` | `1 failed in 0.77s` |
| X22 | 补充材料不做危机检查 | `test_create_group_materials_crisis_is_400_without_row` | `1 failed, 45 warnings in 1.15s` |
| X30 | 详情忽略 after | `test_detail_after_only_returns_newer_messages` | `1 failed, 45 warnings in 1.19s` |
| X31/X32/X33 | 三处「已有别的群在跑」检查全去掉 | `test_start_rejects...`、`test_resume_rejects...`、`test_continue_rejects...` | `3 failed, 45 warnings in 1.40s` |
| X27 | 群列表不限 50 | `test_group_list_is_capped_at_fifty` | `1 failed, 45 warnings in 1.13s` |
| X28 | 删成员不清模型 | `test_patch_removing_member_clears_its_model` | `1 failed, 45 warnings in 1.23s` |
| X37 | 分身默认模型不看 BYOK | `test_x37_avatar_effective_model_prefers_byok_and_configured` | `1 failed in 0.72s` |
| X39 | 自定义新成员不跳过已用代号 | `test_patch_new_custom_member_skips_used_codes` | `1 failed, 45 warnings in 1.20s` |
| X44 | 身份设定可超过 300 字 | `test_patch_identity_persona_over_300_is_422` | `1 failed, 45 warnings in 1.18s` |

X40 由 B 的免费/付费两条用例覆盖（同一 `round == 0` 变异，2 failed，见 B 行）。

## 验收

所有命令从 `backend/` 执行，命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

### 1. 讨论群测试连跑 5 次

```text
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_*.py
```

```text
RUN 1 exit=0 | 188 passed, 45 warnings in 14.48s
RUN 2 exit=0 | 188 passed, 45 warnings in 14.66s
RUN 3 exit=0 | 188 passed, 45 warnings in 14.23s
RUN 4 exit=0 | 188 passed, 45 warnings in 14.37s
RUN 5 exit=0 | 188 passed, 45 warnings in 14.39s
```

5 次都 188 passed、0 跳过、退出码 0。

### 2. 全量

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：`8540 passed, 47 warnings in 407.20s (0:06:47)`，退出码 0，0 失败、0 跳过。基线 8352 + 188 = 8540；全量收集数 8540。

各讨论群文件收集数：api 36、billing 25、docs 19、engine 49、runner 22、schemas 33、structure 4，合计 188。

### 3. 自检

见上面的自检表；A–G 和 D/I 全部由断言失败发现，未出现 `error` 或超时。

### 4. 改动范围

`git status --porcelain --untracked-files=all` 当前共 56 条。

- 与 R3 交付的 50 条相比，没有删除任何路径。
- 新增 6 条：规格作者在返修前提供的 `04-review.md`、`08-fix-review-r1.md`、`verify/lock-root-cause.md`、`verify/cancel_probe.py`、`verify/zombie_probe.py`，以及本报告。
- 内容变动在允许范围：`backend/discuss/avatar.py`、`engine.py`、`service.py`、`runner.py`、`store.py`、`roles.py`；四个 `backend/tests/test_discuss_*.py`；`README.md`、`docs/ARCHITECTURE.md`、`CLAUDE.md`（H 的一句话）。
- `backend/discuss/billing.py`、`backend/novel/`、`backend/agent_store.py`、`backend/tests/conftest.py`、`verify/` 未改。
- `CLAUDE.md` 68,497 字节；9 条已跟踪文件的 `git diff --stat` 与 R3 一致。

## 未完成或需要人工确认

1. **X14 的语义**：复核表格写「其余步骤先被取消并收尾」，复核正文写「失败后兄弟任务还在跑」。当前实现是等兄弟完成后再抛；测试按当前实现和复核正文写。若作者要求真正的取消兄弟，需要改 `_gather_all`，本轮没有擅自改变行为。
2. **A 的 `get_memory_snapshot` 分支**：它的 `_drain` 也已改，但复核建议的两条探针都停在 `get_my_agent` 的第一条 `FROM agents WHERE owner_username` 查询，未单独构造 memory snapshot 查询的取消点；system_for 主路径覆盖了同一保护机制。
3. **E 的补偿清理异常**：`release_claim` 内部若清理本身被二次取消，会记录 `claim_clear_cancelled` 并让原始取消继续；这是有意的优先级，未吞掉原始取消。
4. **F 的陈旧预扣**：`delete_group` 只退 `billing_status='reserved'` 的行，settled/refunded 不重复退；测试覆盖了 `cancel_group` 为空操作的场景。
5. **付费 pause/delete 的稳定快照**：测试用 `stable_paid_snapshot` 等到 `balance == 初始值 - spent - reserved` 连续两次成立，避免后台并发结算造成一次竞争性 flake；这是测试稳定性处理，不影响产品行为。
6. **`billing.py` 未改**：D 的四条用例证明现有计费实现已满足；`backend/novel/` 的同类取消隐患按复核范围保留，不属本轮。
