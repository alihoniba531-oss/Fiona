# 复核 R2（第 2 轮）：第 1 轮必须项复验与 F4–F7 回归检查

- 复核对象：分支 `novel-structure-v2` 工作树（基线 `85888d5`，未提交）；规格 `02-spec.md`（含 §7、§8）；第 1 轮复核 `04-review-a.md`、`04-review-b.md`；返修单 `05-fix-r1.md`；实施方自报 `03-report.md`「第 1 轮返修」只作线索。
- 复核方式：全部离线、占位密钥、fake 路由。复跑第 1 轮探针 probe1 / probe2 / probe3 / probe5（严格版）/ probe8；对现版新写 F1/F2 边界、F3/F5/F6、F7.2 升级与延长三组探针；在 scratchpad 副本上做 25 条「回退修复」变异验证新增测试。源码起止哈希一致（复核期间无人改动，见文末）。探针与日志在会话 scratchpad `v2-review/r2/`，仓库内本文件是唯一写入。
- 本轮只核验第 1 轮必须项（A1/A2/A3=B1）是否修好、F4–F7 是否引入回归；新的主观发现一律列为「可优化」。
- 日期：2026-10-16。

## 结论：**通过**

- 第 1 轮三项必须修复（A1 截断降级、A2 新问题判定与归一化、A3/B1 升级后重归档套 v2 预算）全部确认修好：probe3 Case A/B/C 由 `blocking=False passed=True` 变为 `blocking=True passed=False`；probe8 由 `paused/step_failed` 变为 `awaiting_review`、归档 1 次无修复轮。
- F4–F7 未引入 v1 回归：probe1 13 组、严格版 probe5（含原始 `config_json` 字符串）、probe2 P0 pilot 与 85888d5 逐字节一致（仅 P1 审校 system 提示词按 T5 追加，P0 的 `cost.md`/`blind/key.json` 为运行噪声）。
- 基线既有测试 diff 为空；本期测试相对第 1 轮快照的改动只在返修单授权范围内且均为收紧；新增测试能在回退修复的变异上失败（见 §7）。
- 没有「仍需修复」项。可优化项中第 1 条（跨段证据）是客观的边界缺口，建议随第二期一并处理。

## 1–7 核验表

### 1. F1 降级判定用未截断全集、payload 才截断；分段退化

| 检查点 | 结果 | 证据 |
|---|---|---|
| 全集与截断分开 | 符合 | `writing.py:284` `passages = changed_passages(previous_review_body, body, limit=None)`；`writing.py:286` payload 用 `_passages_payload(passages)` 截约 3000 字；`writing.py:290-291` 兜底校验收到的是未截断 `passages`。`writing.py:44-57` 截断只发生在 `_passages_payload`，截断说明 `（改动段落超过上限，已截断）` 只进 payload，不进 `writing.py:65` 的 `changed_evidence`。 |
| 分段退化 | 符合 | `writing.py:19-24`：按空行切段；若 ≤2 段且正文行数 ≥6，改为按单换行切段。探针 E8：6 行→5 段、7 行→6 段，边界与返修单一致。 |
| 「改动全集内」的真问题不被放过 | 符合（有一条边界，见可优化 1） | 复跑 probe3：`CASE B … payload_passages_chars=3000 full_changed_chars=4400 evidence_in_full_changed=True blocking=True outside_changes=None passed=False`；`CASE C … passages=2 chars=290 blocking=True outside_changes=None passed=False`。探针 E7（三个场景块、块内单换行）：场景 1 内新硬伤保持阻断。 |
| 收敛目的仍成立 | 符合 | `writing.py:87-89`：非旧问题且不在任何改动段 → `blocking=False, outside_changes=True`。探针 E7 场景 2（未改动）的新问题 `(False, True)`；新增测试 `test_single_newline_manuscript_scopes_changes_to_individual_lines` 同时断言段内阻断、段外降级。 |
| 变异 | 杀死 | R1（兜底改用截断 payload）→ `test_changed_payload_is_truncated_but_clipped_evidence_still_blocks` 失败；R2（去掉退化）→ 单换行用例失败。 |

### 2. F2 统一 compact()；重叠判定是否过宽/过窄；previous_issue_index

| 检查点 | 结果 | 证据 |
|---|---|---|
| 统一归一化 | 符合 | `writing.py:64-67, 86`：旧 evidence、改动段、正文、段落、新 evidence 全部 `schemas.compact()`，与 `validate_review`（`schemas.py:583`）同口径。新增测试 `test_quote_normalization_keeps_new_blocker_inside_changed_passage`（弯引号正文、直引号引用）通过；变异 R4（退回只去空白）被它杀死。 |
| 旧问题认定四条规则 | 符合返修单 | `writing.py:70-71` 索引；`:75` 互为子串；`:77-80` `compact(body).find()` 区间相交；`:81` 同段落。探针 E10（区间相交、互不为子串）保留阻断；复跑 probe3 `CASE A … blocking=True passed=False rounds=3 flags=['review_unresolved']`。 |
| 是否过宽（把改动段外的真新问题当旧问题保留阻断） | **会，但范围有界，且是返修单明示的规则**（可优化 2） | 探针 E1：未改动段落内与旧问题同段的另一个新问题 → `blocking=True`（R2 字面要求降级）；E3：新 evidence 是旧 evidence 的子串、实际出自另一未改动段 → 保留阻断。最坏情形 E2：正文 <6 行且只有 1–2 段（整章一个大段）时 `_paragraphs` 返回 2 段，同段规则覆盖整章，R2「无改动→新问题一律降级」对该章完全失效。实际写手正文通常多段，概率低。 |
| 是否过窄（把旧问题当新问题放行） | 有一种已知局限（可优化 3） | 探针 E4：旧问题未修复、复审改从另一段落引用同一问题且不填索引 → 判新并降级、`passed=True`。填 `previous_issue_index=1` 即保留阻断（E4b）。 |
| `previous_issue_index` 越界/伪造 | 类型与范围校验正确；伪造可绕过（可优化 4） | `writing.py:71` `type(index) is int and 1 <= index <= len(previous_issues)`；探针 E5：`0 / 2 / -1 / '1' / 1.0 / True / None` 全部不认（走重叠判定后降级）；有效索引伪造在真新问题上 → 保留阻断（返修单规定「带了就按索引归类」）。字段经 `validate_review` 的 `deepcopy(item)` 保留，提示词 `agent_pool.py:182-183` 已说明。 |
| 变异 | 杀死 | R3（退回精确相等）、R5（忽略索引）、R6（越界也认）分别被 respan 参数化用例、索引用例杀死。R24/R25（单独去掉同段 / 区间相交规则）见 §7。 |

### 3. F3 升级后重归档 v1 旧章跳过 v2 预算；v2 章仍生效

| 检查点 | 结果 | 证据 |
|---|---|---|
| 跳过条件 | 符合 | `schemas.py:659-668` `_archive_v2`：先做 `milestones_done ⊆ milestones_advanced`（662-663）与 `payoff_delivered` 布尔检查（664-665），`decision` 无 `genre_payoff` 键即 `return`（668），伏笔预算与「实际≤计划」只对 v2 细纲执行（669-690）。 |
| `_rearchive` 同规则 | 符合 | `runner.py:527` `v2_chapter = structure=="v2" and "genre_payoff" in decision`；只有 v2 章才带 `genre_payoff/milestones_advanced` 进 payload（529-532）并用 v2 档案员卡片（533-535）；`bible.py:115` 同条件才写 `structure_history`。复跑 probe8：`v2 re-archive of the v1 chapter after upgrade: status awaiting_review pause_reason None archive attempts 1 repair errors [] last_error None`。新增测试 `test_upgraded_v1_latest_rearchive_matches_unupgraded_canonical_bytes` 断言升级/未升级两本书 bible 原始字节相等、3 条伏笔保留。 |
| v2 章能否绕过预算 | 不能 | `schemas.py:522-523` v2 细纲缺 `genre_payoff` 键 → `decision.genre_payoff：缺少字段`（探针 F3-1）；`genre_payoff=null` 经 `c.finish` 后键仍保留（F3-2 `keeps key: True`），归档照常套预算（F3-3 `v2 decision payoff=None: rejected -> 本章新埋 3 条，超过每章上限 2 条`；测试 `test_v2_chapter_archive_keeps_budget_checks_when_payoff_is_null`、`test_native_v2_rearchive_still_rejects_three_planted_foreshadows`）。`validate_archive(..., decision=None)` 会跳过预算（F3-3），但 v2 路径的三个调用方 `writing.py:319-321`、`runner.py:539-541`、`bible.py:82` 都传了 decision，没有传 None 的入口。 |
| v1 旧章无害检查保留 | 符合 | 探针 F3-4：旧章归档 3 条伏笔通过；自带 `payoff_delivered='yes'` 被拒 `必须是布尔值`；新增测试里 `milestones_done=["M9"]` 对旧章仍被拒。 |
| 变异 | 杀死 | R7（去掉早退）→ core 用例失败；R8（旧章也用 v2 卡片/payload）→ runner 字节相等用例失败。 |

### 4. F4 爽点写进正文并由档案员核实；口径

| 检查点 | 结果 | 证据 |
|---|---|---|
| 写手上下文 | 符合 | `writing.py:225-227` v2 时 `context.genre_payoff / milestones_advanced`；提示词 `agent_pool.py:314-318`「在指定 beat_index 节拍里写出可见的兑现场面」。 |
| 审校按 beat_sheet 阻断 | 符合（提示词层） | `writing.py:274-275` payload 带 `genre_payoff`；`agent_pool.py:320-324`「兑现场面完全缺失按整条节拍缺失处理，报告 beat_sheet 类 blocking=true」。测试 `test_v2_planned_payoff_missing_from_manuscript_is_reviewed_as_missing_beat` 三轮均阻断。 |
| 档案员 `payoff_delivered` 只在有 genre_payoff 时必填 | 符合 | `schemas.py:664-665`：`genre_payoff is not None` 或自带该字段时要求严格 bool；`test_planned_payoff_cannot_omit_archive_confirmation` 同时断言 payoff 为 null 时可省略。提示词 `agent_pool.py:325-329`。 |
| `payoff_history`/硬校验 1 以 delivered 为准、旧数据回退计划 | 符合 | `bible.py:121-122` 记录；`context.py:176-181` 取 `archive.payoff_delivered`，为 False 时把该章 `genre_payoff` 置 None，`prior_payoff`（`context.py:193-195`）随之不计；无字段则保留细纲计划（`test_history_without_confirmation_falls_back_to_legacy_planned_payoff`）。 |
| 重写/redo/改稿/重归档后口径 | 符合 | 三条历史入口都带 archive：正常推演 `runner.py:311-323`（`archive_json`）、redo `runner.py:481-487`、`approve_plan` `service.py:424-430`。v2 最新章重归档从归档前版本重算（`runner.py:502-507`），`apply_archive` 用新确认值重新追加 `structure_history`，章节行 `archive_json` 同步更新（`runner.py:592`），下一章读到的是重归档后的确认。runner 级反例 `test_runner_payoff_window_uses_archivist_confirmation`：第 2 章计划爽点、正文未写、档案员报 false → 第 3 章 `payoff_history[-1].genre_payoff is None`、红灯「本章必须安排类型爽点」、首次细纲 null 被打回。优先级：history 的 archive 覆盖 `structure_history`；只有 ending-only 行时不抹掉已存确认（`test_history_archive_false_takes_priority_over_plan_and_persisted_true`）。 |
| 档案员谎报 true | 风险存在（可优化 5） | 代码无法核验正文语义；提示词 `agent_pool.py:328-329` 已写「不得为了通过节奏规则谎报」。 |
| 变异 | 杀死 | R9（false 不清计划）、R10（永不必填）、R11（写手不带 genre_payoff）、R23（审校不带 genre_payoff）。 |

### 5. F5 / F6 / F7

| 项 | 结果 | 证据 |
|---|---|---|
| F5 逾期里程碑持续红灯与硬要求 | 符合 | `schemas.py:541-545` `due_chapter <= chapter` 且 open 且不在 `milestones_advanced` → 失败并带「已逾期 N 章」；`context.py:211-215` 红灯。测试 `test_open_overdue_milestone_remains_flagged_and_mandatory[(4,1),(5,2),(9,6),(10,7)]`；done/missed 后解除（`test_closed_milestone_no_longer_adds_overdue_pressure`）。 |
| F5 与卷末 missed 的衔接 | 符合 | 探针 F5-2：第 10 章不列 M1 被拒 `已逾期 7 章`；第 10 章归档后 `['missed','missed']`（`bible.py:124-131`）；第 11 章新卷红灯 `第 1 卷里程碑 M1 未完成（到期第 3 章）`，不再硬要求。 |
| F5 与其他硬规则组合是否死局 | 无死局 | 探针 F5：同一章同时触发 6 条红灯（核心线 6 章未推进、必须爽点、M1 逾期 4 章、open 22>20、卷预算 4/4 用尽、钩子限制），违规细纲返回 5 条带数值错误；`genre_payoff` 非空 + `advances_threads=[T1]` + `milestones_advanced=[M1]` + `plant=[]` 一次通过。四条规则互相独立，均可同时满足。 |
| F6 章末钩子红灯 | 符合（仅提示） | `context.py:227-228`：open>20 或本卷已埋 ≥ 预算时加红灯；主编 v2 提示词 `agent_pool.py:311-312`；无代码校验。参数化测试 5 组；变异 R14 被杀。 |
| F7.1 顾问 critique_plan 提示词 | 符合 | `agent_pool.py:332-336` v2 critique_plan 明示检查 `genre_payoff/milestones_advanced` 及爽点保护；v1 卡片不含（测试 `test_v2_execution_and_advisor_cards_require_visible_confirmed_payoffs`；本轮另比对 v1/P1 全部非审校卡片与 85888d5 逐字节相同）。 |
| F7.2 零碎卷合并 | 符合 | `service.py:590-592` 与 `runner.py:417-421` 同规则。探针（`probe_f7.log`，max=25）：done 7→[8,10]、8→[9,20]、9→[10,20]、10→[11,20]、17→[18,20]、18→[19,25]、19→[20,25]、20→[21,25]；max=12 done 9→[10,12]；max=10 done 8→[9,10]；max=20 done 19→[20,20]（截于 max，一章卷不可避免，见可优化 7）。后续卷均按整十边界顺延。 |
| F7.2 末卷延长 | 符合 | `service.py:709-726`：末卷终点等于旧 `max_chapters` 时延长末卷、按 ceil 补齐 `payoff_plan`、写 `volume_extend:n` 版本、同步 `_volume_gate.end_chapter`；`runner.py:514-523` 重归档时用延长后的范围重算里程碑结果。探针：25+2 → `[21,27]` payoff 3、12+3 → `[11,15]` payoff 2、10+1 → `[1,11]` payoff 4，卷会议次数不变、无新卷。 |
| F7.3 v1 不写 `volume_gate`/`structure` | 符合 | `service.py:213-216`。严格版 probe5：`config_json_raw BYTE_EQ`，sha256 `c91cf3f6…`，键 `adaptation,agents,automation,batch_size,budget_strawberries,critique_rounds,drama_adaptation,enable_arc_summaries,enable_context_compression,experiment,panel_mode,seed_idea,target`。API 测试断言 v1 `config_json` 与期望字符串逐字节相等。 |
| F7.4 升级中 pause 409 | 符合 | `service.py:28` `_upgrading`，`:331-338` 在 `editing_novel` 锁内登记/注销，`:651-653` pause 返回 409「正在升级结构，请稍后再试」。测试 `test_upgrade_blocks_resume_while_contract_is_in_flight[awaiting_review|paused]` 断言 409 文案、租约与状态不变、结束后 `_upgrading` 清空；失败路径 `finally` 注销（`test_…refund…` 断言）。 |
| F7.5 补测试 | 符合 | 爽点窗口精确边界 `test_payoff_window_excludes_exactly_one_chapter_before_window[2..5]`（变异 R21 被杀）；只走 runner 的 `awaiting_volume` 恢复 `test_runner_alone_restores_pending_volume_gate_without_repeating_steps`（变异 R22 被杀）。 |

### 6. v1 零回归与契约

| 检查点 | 结果 | 证据 |
|---|---|---|
| 引擎级 v1 | 通过 | 复跑 probe1：solo/critique/merge × 缺键/`v1` × drama 开/关 12 组十章 + 1 组无审校，`PROBE1 PASS`；每组仅 P1 审校 system 有差异（10 处），且基线原句为前缀。 |
| runner/service 级 v1（含 `config_json`） | 通过 | 严格版 `probe5_strict.py`（去掉第 1 轮手工 pop `structure` 的动作、新增原始 `config_json` 字符串）：`log/versions/chapters/steps/notes/config/config_json_raw/compass/final/export` 全部 BYTE_EQ；52 个步骤键一致；仅 7 次 P1 审校 system 差异，其余消息无差异；`STRICT_PROBE5 PASS`。 |
| P0 离线 pilot | 通过 | 复跑 probe2：expA/A2/B（small 与完整）、expC 全部 step 文件、章节、圣经、报告一致；仅 `cost.md`（耗时列）与 `blind/key.json`（`SystemRandom` 盲评顺序）不同，与第 1 轮相同，为运行噪声。 |
| 五个只读服务签名、`novel_chapters` 列、圣经已有键 | 通过 | `test_protected_service_signatures_and_chapter_columns_are_unchanged` 通过；`store_db.py`、`billing.py`、`llm_router.py`、`run_store.py`、`pilot.py` 不在 `git diff HEAD --stat` 改动列表中；v1 书 bible JSON 在 probe1/probe5 中逐字节一致，v2 只新增 `dynamic.volumes/structure_history`。 |
| 角色卡 | 通过 | 本轮用 `novel_base`（85888d5）与现版逐一比对 editor/writer/archivist/六位顾问在 `None/decision/plan/finalize/write/archive/critique_plan/proposal/setup/arc_summary` 下的 v1 卡片：全部相同；P0 审校卡片不含 8 条/`previous_issue_index`/`changed_passages`。 |
| 既有测试 | 通过 | `tests/test_novel_*.py` 1613 passed（基线 1383 + 本期 230）；后端全量（去掉沙箱禁止回环端口的 `test_exchange_isolation.py`、`test_safe_http_deadline.py` 两文件）：**5467 passed, 15 deselected, 0 failed**（167 s），与实施方自报的「1 failed / 5 errors 全部在这两个文件」口径一致。 |

### 7. 测试改动范围与变异

| 检查点 | 结果 | 证据 |
|---|---|---|
| 基线既有测试 | diff 为空 | `git diff HEAD --exit-code -- backend/tests` → 空。 |
| 本期测试相对第 1 轮快照（`snap-before-fix/`） | 只限授权项且为收紧 | review：唯一改写的既有断言是 F1.3 点名的截断用例（改名为 `…but_clipped_evidence_still_blocks`，由 `outside_changes is True` 改为 `blocking is True` 且无 `outside_changes`，另加 `review_unresolved`），其余为新增 8 组用例。core：5 个既有 v2 归档用例按 F4.4 补 `payoff_delivered=True` 输入；`structure_history` 整条相等断言新增 `payoff_delivered` 键（收紧）；新增 11 组。api：F7.3 点名的四处 `structure/volume_gate` 断言改为缺键并补整串 `config_json` 相等（收紧）；升级并发用例参数化并加 pause 409 断言（收紧）；新增 3 组。runner：25 章用例追加档案员确认断言（收紧）；新增 6 组。compat 未改。无断言被删除或放宽。 |
| 新增测试在工作树通过 | 230 passed（8.0 s） | `tests/test_novel_v2_*.py`。 |
| 新增测试能否发现回退 | 【待填：变异汇总】 | 25 条变异（`r2/mutate.py`、`r2/mutate.log`）：逐条回退 F1（R1–R2）、F2（R3–R6、R24–R25）、F3（R7–R8）、F4（R9–R11、R23）、F5（R12–R13）、F6（R14）、F7.1（R15）、F7.2（R16–R18）、F7.3（R19）、F7.4（R20）、B-A1（R21）、A-可优化 1（R22）。存活分析见下。 |

【待填：变异存活分析】

## 仍需修复

无。第 1 轮三项必须修复均已确认修好；本轮未发现 F4–F7 引入的 v1 回归或既有测试回归。

## 可优化（按影响排序；均为本轮新发现或返修单未覆盖的边界，不阻断）

1. **跨段证据会被当作改动段外的新问题降级**（探针 E6，`writing.py:87`）。真正的新硬伤如果 evidence 横跨两个相邻的改动段落（例如引用上一段末句 + 下一段首句说明矛盾），`validate_review` 用 `compact(body)` 能接受它，但兜底判定逐段检查 `evidence in passage`，两段都不包含 → `blocking=False, outside_changes=True`，章节以 `passed=True` 通过。这是改动全集内真问题被放过的一个口子（第 1 轮代码同样存在，非本轮回归，概率低：审校提示词要求逐字摘录，通常是单句）。建议：把相邻改动段拼成 `compact("".join(...))` 后再做包含判定，或在 `compact(body)` 中标出改动区间、按区间相交判定。补一条跨段用例。
2. **同段落规则在「整章一两段」的正文上吞掉全部降级**（探针 E1/E2）。`_paragraphs` 只在 ≥6 行时退化为按行；正文 <6 行且 ≤2 段（例如写手整章不换行）时同段规则覆盖整章，R2「无改动→新问题一律降级」失效。建议：同段规则限定在段落 compact 长度 ≤ 某阈值（如 400 字），或在 `_paragraphs` 只切出 ≤2 段时不启用同段规则。
3. **旧问题换段引用且不填索引会被当新问题放行**（探针 E4）。这是基于 evidence 匹配的固有局限，`previous_issue_index` 是逃生口；建议在 P1 审校提示词里把「复报旧问题必须填 previous_issue_index」从「可选」改为「必须」。
4. **有效 `previous_issue_index` 可被伪造**（探针 E5）：真新问题标 index=1 即保留阻断。可在索引命中时再要求与该旧问题满足任一重叠规则，不满足则记 `index_mismatch` 并走重叠判定。
5. **档案员谎报 `payoff_delivered=true`**：代码无法核验正文语义，节奏规则可被档案员一句 true 绕过；可在对比实验中抽样人工核对 `structure_history.payoff_delivered` 与正文。
6. **`_volume_upgrade.end_chapter` 是死数据，runner 侧合并逻辑无测试**：`service.py:595` 写入的 `end_chapter` 在 `runner.py:418-421` 被无条件重算；变异 R17（去掉 runner 侧 `<3` 合并）230 全绿存活，而 API 用例只断言 config 标记。建议 runner 直接使用标记的 `end_chapter`（二者只留一处），并补一条「done=9 升级后首个发布卷为 [10,20]」的 runner 级断言（本轮探针已实测正确）。
7. **书末一章卷**：`max=20、done=19` 升级 → `[20,20]`（合并到下一边界后截于 max），仍需 2–5 条里程碑与三步付费卷会议；规格无更好选择，建议报告里明示，或在此情形跳过卷会议直接沿用「无卷」。
8. **末卷延长不复开 `missed` 里程碑**：`reject_end` 延长末卷时保留原里程碑状态（API 用例也如此断言），卷末已标 `missed` 的里程碑不会因延长重新 open；而若延长后重归档末章，`runner.py:514-523` 又会按新范围把它们算回 open。两条路径口径不一致，建议统一（延长时把 `missed` 改回 `open`，或重归档时也不复开）。
9. **`cancel_novel` 跨事件循环取消**（`runner.py:143-155`）：返修单未点名、报告称为修组合回归所加；同循环路径语义不变（多了 `done()` 守卫），跨循环路径依赖拥有任务的循环仍在运行，循环已关闭时 `run_coroutine_threadsafe` 会抛 `RuntimeError`。本轮 probe5 的 v1 暂停/取消流程逐字节一致，新增 `test_foreground_cancel_drains_worker_owned_by_another_event_loop` 覆盖；建议在报告中单独列为「范围外改动」。
10. **删除接口不受升级锁保护**：`service.delete`（768-778）只调用 `cancel_novel`，不检查 `_check_not_editing`/`_upgrading`；升级进行中删书会让升级在 `owned` 处失败并走 `finally` 退款，账目无误，但与 pause 的 409 处理不一致。
11. **删除造成的悬空引用**（探针 E9）：只删段落时改动集为空 → payload 省略 `changed_passages`、新问题全部降级，删掉人物出场段后的「老周给钥匙」类矛盾会被放行。这是 R2 裁定的行为，记录以便第二期评估是否把「被删段落的前后相邻段」计入改动集。
12. **`_passages_payload` 截段会把单个段落截半**（`writing.py:54`），模型看到的最后一段是半句；与第 1 轮一致，只影响模型上下文不影响判定。

## 探针与日志索引（scratchpad `v2-review/r2/`）

| 文件 | 内容 |
|---|---|
| `src-hash-start.txt` / `src-hash-end.txt` | 复核起止源码与测试文件 sha256（一致） |
| `probe3.log` | 复跑第 1 轮 probe3：Case A/B/C 全部 `blocking=True passed=False` |
| `probe8.log` | 复跑第 1 轮 probe8：升级后重归档 `awaiting_review`，归档 1 次、无修复轮 |
| `probe1.log` | 复跑第 1 轮 probe1：13 组 `PROBE1 PASS` |
| `probe2.log` | 复跑第 1 轮 probe2：仅 `cost.md` / `blind/key.json` 不同 |
| `probe5_strict.py`, `p5s_base.json`, `p5s_new.json`, `probe5_compare.py`, `probe5_compare.log` | 严格版 runner/service 级 v1 快照与比对（含原始 `config_json`） |
| `probe_f12_edges.py`, `probe_f12.log` | F1/F2 边界 E1–E10 |
| `probe_f3_f5.py`, `probe_f3f5.log` | F3 绕过尝试、F5 死局与卷末衔接、F6 红灯 |
| `probe_f7_upgrade_extend.py`, `probe_f7.log` | F7.2 升级合并 12 组边界、末卷延长 3 组（表中 `done=0` 一行为探针参数误差：batch_size=1 时实际 done=1，`[2,10]` 正确） |
| `mutate.py`, `mutate.log`, `mut/backend/` | 25 条回退变异与结果 |
| `v2-tests.log`, `novel-tests.log`, `fullsuite.log` | 新增测试 230 / 小说工坊 1613 / 后端全量 |

## 复跑方式

```bash
cd backend
DASHSCOPE_API_KEY=placeholder DEEPSEEK_API_KEY=placeholder ARK_API_KEY=placeholder OPENAI_API_KEY=placeholder PYTHON_DOTENV_DISABLED=1 \
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_v2_*.py
# 探针：同一环境变量下运行 scratchpad/v2-review/r2/*.py（probe5_strict.py 需分别以 base / new 两个进程运行后用 probe5_compare.py 比对）
```
