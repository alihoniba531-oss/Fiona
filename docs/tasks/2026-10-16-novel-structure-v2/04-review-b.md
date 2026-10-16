# 独立复核 B：v2 推演逻辑能否纠正「修仙写成悬疑」（T2、T3、T4、提示词、纠偏力、测试质量）

日期：2026-10-16。复核对象：分支 `novel-structure-v2`，基线 `85888d5`，未提交工作树。复核员未参与规格与实现，只依据落盘材料与离线探针判断。

审查快照：`v2.diff`（3165 行）与工作树 `git diff HEAD` 逐行一致；源码 25 个文件起止 SHA256 一致（审查期间无人改动）。所有探针离线、fake 路由、占位密钥；仓库源码零修改，本文件是唯一写入。

## 结论：**不通过（1 项必须修复）**

v2 的三层机制——类型承诺（T2）、卷会议（T3）、章级硬校验（T4）——按规格实现到位，硬校验在离线探针里确实能拦下并迫使「只推悬疑、不给爽点、狂埋伏笔」的主编回到轨道（见 §5）。但有一个会让**升级到 v2 的旧书（含《凡骨登天》）改稿后卡死并丢伏笔记录**的功能错误，必须先修。另有一条核心规则的测试缺口（变异存活）建议随本单补齐。

## 必须修复

### B1. 升级到 v2 后改最新章，旧章重归档被 v2 伏笔预算卡死（功能错误 + 数据风险）

- **现象**：v1 书写了 N 章后调用 `upgrade-structure`，再对最新章 `PUT /chapters/{N}` 改稿 → 触发重归档 → `validate_archive(..., config=v2, decision=v1 的旧 decision)` → `_archive_v2` 对这章套用 v2 伏笔预算（每章 ≤2、未回收 >20 时新埋 ≤ 回收、实际 ≤ 细纲计划）→ 校验失败两次 → 书 `paused / step_failed`。
- **证据**：
  - `backend/novel/schemas.py:652-680`：`validate_archive` 只看 `config.structure == "v2"` 就进 `_archive_v2`，不看这章的 decision 是否是 v2 产物；`_archive_v2` 无条件调用 `_foreshadowing_budget`。
  - `backend/novel/runner.py:494-504`：`_rearchive` 把升级后的 `config`（已是 v2）和旧章 `meeting["decision"]` 一起传给 `validate_archive`。
  - 离线复现（探针 `test_zz_probe_runner.py::test_probe_upgrade_then_edit_latest_v1_chapter_with_three_plants`，fake 路由）：v1 书第 1 章细纲埋 3 条伏笔并归档成功（v1 无上限）→ 升级 → 改第 1 章正文 → 重归档结果 `status=paused, pause_reason=step_failed`，修复轮报错 `archive.foreshadowing_planted：本章新埋 3 条，超过每章上限 2 条`。
- **后果**：
  - 《凡骨登天》20 章埋 40 条、open 36 条。升级后只要改最新章正文，重归档必撞「未回收 36 条 > 20，本章新埋不得多于回收」；真实模型在修复轮最可能的做法是**少报伏笔**以通过校验 → 圣经伏笔账本静默丢条目；fake 这样的「如实」档案员则直接卡死，`resume` 后同样失败（同一校验），用户只能放弃改稿。
  - 与 T6.3「升级不改动已写章节和既有圣经内容」的精神相悖：旧章的事实被新规则逼着改写。
- **修法**（任选其一，均只改 `schemas.py`/`runner.py`）：
  1. `_archive_v2` 只对 v2 产生的 decision 执行预算与「实际 ≤ 计划」检查：`if decision and "genre_payoff" in decision:` 再调 `_foreshadowing_budget`；`milestones_done` 子集检查保留。
  2. 或在 `_rearchive` 中，当该章 `meeting["decision"]` 没有 `genre_payoff` 键（v1 产物）时，用 `{**config, "structure": "v1"}` 调 `validate_archive`/`apply_archive`（注意 `structure_history` 追加仍需 v2 配置，二选一要配套）。
  - 并补测试：v1 书埋 3 条 → 升级 → 改最新章 → 重归档成功且伏笔条数不变。

## 可优化（含「仍可能漂移」的设计漏洞）

按影响排序；A 类建议随本单补，B 类留第二期或对比实验后再定。

### A1. 爽点窗口边界无测试覆盖（变异存活）
- 把 `context.py:188` 的窗口 `range(max(1, chapter - period + 1), chapter)` 改宽一章为 `range(max(1, chapter - period), chapter)`，**176 条新测试全绿**（变异 A）。现有用例只在 `chapter == period` 处测边界，那里 `max(1, ·)` 把两种写法钳成同一个窗口；`test_brief_full_history_windows_red_flags_and_isolation` 的爽点在第 2 章、看第 13 章，两种窗口都要求爽点。
- 代码本身正确（探针 `test_probe_payoff_window_boundary_at_later_chapter`：第 13 章看 [11,12]，爽点恰在第 10 章 → 要求；在第 11 章 → 不要求）。
- 建议补一条：`chapter ≥ 2×period`，爽点恰在 `chapter − period` 章 → 必须 `payoff_required`；在 `chapter − period + 1` 章 → 不要求。
- 其余 13 个针对规则的变异（去掉爽点规则、核心主线窗口 3→4、到期里程碑、卷关卡先行、missed 流转、爽点保护提示词、redo 步骤键后缀、非核心红灯 6→7、归档超计划、卷关卡不停、卷预算 ±1、爽点只在整倍章要求、open 上限 20→21）全部被杀死。`service.transition` 里恢复 `awaiting_volume` 的分支被去掉后也存活，但那是等价变异——`runner._ensure_volume:383-389` 会重新推导关卡，行为不变，不算缺口。

### A2. 到期里程碑过了 due 章仍 open 就再无压力，直到卷末才判 missed
- `context.py:200-202` 与 `schemas.py:541-543` 只在 `due_chapter == chapter` 时给红灯/硬要求；主编在到期章把它列进 `milestones_advanced`、档案员没标 `done`，之后几章既无红灯也无校验（探针 `test_probe_overdue_open_milestone_has_no_red_flag_after_due_chapter`：第 4 章到期有红灯，第 5–7 章红灯为空、校验放行）。
- 规格原文如此，但「推进 ≠ 完成」让里程碑容易被敷衍一次就过。建议：`due_chapter <= chapter and status == open` 持续红灯「里程碑 M1 已逾期 k 章」，并在 `due+2` 章起硬要求再次 advanced。

### A3. 爽点与核心主线只是主编自报的标签，写手、审校、档案员都不核验
- `build_writer_context`（`context.py:223-258`）只带 `beat_sheet`，**没有 `genre_payoff`**；写手不知道哪一拍是爽点、该写出什么爽感。
- `REVIEW_SCHEMA` / `P1_REVIEW_RULES`（`agent_pool.py:107-179`）零次提及爽点或 `genre_payoff`；审校不会因爽点没落地而阻断。
- 归档 payload 带了 `genre_payoff`（`writing.py:280`）但档案员提示词没说要核对；`structure_history` 记录的是**细纲声明**（`bible.py:117-120`），不是正文事实。
- 结果：§4.3「每 3 章内有爽点」「核心主线无 3 章空缺」统计的是计划，不是成书。建议：写手上下文加 `genre_payoff` 并在提示词标出「第 k 拍是类型爽点」；审校把「爽点节拍缺失」归入 `beat_sheet` 阻断；档案员返回 `genre_payoff_delivered: bool`，`structure_history` 以归档结果为准，未兑现时下一章红灯。

### A4. 伏笔预算只管 `foreshadowing_plant`，章末钩子里的新谜团不计数
- v1 的根因之一是「每章章末新留一个谜团」。v2 的 `new_mystery_budget` 与 open 上限只统计 `foreshadowing_plant`（`schemas.py:544-558`）。探针 `test_probe_mystery_budget_evaded_via_ending_hook`：open 24 条、本章 `foreshadowing_plant=[]`、`ending_hook` 写「匿名信揭示宗主另有身份——又一个新谜团」→ 校验通过。
- 代码判不了语义，但可以：要求 v2 细纲对 `ending_hook` 标注 `hook_kind: payoff_tease | mystery | cliffhanger`，`mystery` 类计入卷预算；读者代表提示词明确「章末钩子优先悬挂成长线的下一步，而不是新谜团」。

### A5. 硬性下限等于《凡骨登天》的失败基线
- D4「每 3 章至少推进 1 次」在 20 章里的最低值是 7 次——v1 那本书 T1 恰好推进了 7 次。学习型主编探针（§5）在 10 章里只在第 3、6、9 章推核心线与爽点，其余 7 章全推悬疑线，完全合规。硬校验保证的是**分布均匀**（不再「第 8 章以后停滞」），不是**数量**。
- 这是作者已拍板的 D3/D4，不算缺陷；但对比实验若只看「核心主线推进次数」，v2 可能不比 v1 多。建议对比指标改看「最长空缺」「爽点间距方差」，或第二期把核心线要求提到「每 3 章 2 次」或与 `threads_focus` 挂钩。

### A6. 卷规划里的 `payoff_plan`、`threads_focus` 在章级从不校验
- 卷会议花钱排了「第 3 章当众打脸」，章级 `_decision_v2` 只认里程碑；`payoff_plan.chapter_hint` 过了没兑现不提醒，`threads_focus` 外的线推进也不提醒。建议至少进红灯：「卷规划安排第 3 章爽点『当众打脸』，尚未兑现」。

### A7. `progression_ladder`、`drift_warnings` 只进简报，代码不用
- 修仙文的「境界」是最直观的成长刻度，但没有任何地方记录主角当前处于哪一阶、多少章没升阶。建议档案员归档时返回 `progression_stage`，`thread_staleness` 之外再给「境界停滞 k 章」红灯。

### B1. 升级时已写 9 章会产生一章卷 `[10,10]`
- `service.py:572-574` 按规格 `ceil(9/10)+1 = 2`、范围到下一个整十章 → 卷 2 只有第 10 章（探针 `test_probe_upgrade_with_nine_chapters_done_makes_one_chapter_volume` 实测 `[(2,[10,10]), (3,[11,12])]`），仍要 2–5 条里程碑、三步付费会议。规格原文如此；建议 `done % 10 >= 7` 时直接并入下一卷。

### B2. 卷会议没有节奏顾问/读者代表时仍跑付费定稿步
- `deliberation.py:259-267`：两位顾问都未入选时 `02-*` 为空，`03-volume-finalize-editor` 仍对自己的初案「定稿」一次。可在 `roles` 为空时直接用初案。

### B3. `plan/approve` 对 v2 校验失败只回「细纲不符合裁决要求」
- `service.py:417` 不带具体规则；`volume/approve`（`service.py:480`）却带了 `str(error)`。第二期界面上作者改细纲被拒时不知道踩了哪条硬规则，建议对齐。

### B4. 顾问 critique_plan 提示词仍说「只根据 beat_sheet、rationale、ending_status 提意见」
- `agent_pool.py:105`；v2 的 `plan_input` 已多出 `genre_payoff`/`milestones_advanced`（`deliberation.py:125-127`），提示词没同步，顾问可能忽略它们。

### B5. `thread_staleness` 的数值含义易被误读
- 值 = 当前章 − 上次推进章，3 表示「空缺 2 章」。红灯文案做了换算，但 `thread_staleness` 原值也进简报，节奏顾问被要求「引用 thread_staleness」，可能把 3 说成 3 章。建议字段改名 `chapters_since_advance` 并减 1，或在简报里加一句说明。

### B6. 立项提示词不保证 `main_threads` 里有成长线
- `GENRE_CONTRACT_SCHEMA` 要求「思路含变强时 core_thread 指向成长线」，但 `SETUP_SCHEMA` 没要求此时主线清单必须包含成长线；主编若把成长写进「宗门」线描述里，core_thread 只能指向一条混合线。建议补一句「此时 main_threads 必须单列一条成长线」。

### B7. 归档阶段预算失败只能靠档案员「少报」通过
- 即使修了 B1（必须修复），v2 新章在归档阶段也可能撞预算（如细纲计划回收 F001、正文没回收、档案员如实报 resolved=[]、planted=1 → 失败）。档案员提示词没提预算，修复轮会逼它删条目。建议归档阶段只对「实际 > 计划」硬拦，预算差异记 flag 不拦，或在档案员 v2 提示词里写明规则。

## 逐条核验表

### 1. T2 类型承诺

| 检查点 | 结果 | 证据 |
|---|---|---|
| `validate_setup` 对 v2 额外要求 `genre_contract` 七字段 | 符合 | `schemas.py:311-315`、`198-213`；v1 不要求（`test_setup_contract_is_v2_only_and_uses_code_owned_ids`） |
| 每条校验规则：非空、core_thread 存在、payoffs 3–8 非空、period 1–5 整数（拒 bool/float）、ladder 3–12、warnings 0–5 | 符合 | 15 组参数化反例 `test_genre_contract_rejects_each_invalid_rule`；`drift_warnings` 每条还须非空（比规格略严，合理） |
| core_thread 必须是存在主线；立项用代码顺序 ID | 符合 | `schemas.py:204-208, 313-315`；模型自造 ID 被忽略（测试第 92–96 行） |
| 存进 `compass_json` | 符合 | `bible.py:26-27` |
| 立项确认可改字段、不能改成不存在主线 | 符合 | `service.py:360-363, 368-376`：整体替换后走 `validate_setup`；允许改到另一条**存在**的主线（规格只禁「不存在」）；v1 书传 `genre_contract` 一律 422（`test_v1_setup_rejects_contract_edits`） |
| 立项提示词要求按作者思路提炼、「变强/最强」→ 成长线 | 符合 | `agent_pool.py:146-154, 291-292`；但见 B6 |

### 2. T3 卷会议

| 检查点 | 结果 | 证据 |
|---|---|---|
| 触发章与范围 `[10k+1, min(10k+10, max)]` | 符合 | `runner.py:409`；25 章实测 `[1,10],[11,20],[21,25]`（`test_25_chapter_paid_fake_acceptance`） |
| 只触发一次：断点续跑 | 符合 | 三步固定 step_key，`router.call` 命中 `status=ok` 缓存不再调模型（`llm_router.py:393-395`）；`test_volume_recovery_reuses_completed_paid_steps` 在 finalize 中途暂停再恢复，前两步各 1 次、finalize 2 次、`volume:1` 版本仅 1 个、账目守恒 |
| 只触发一次：重启 | 符合 | `recover_interrupted_novels` → `_advance` → 同上缓存路径 |
| 只触发一次：redo 不重开、重归档不丢下卷 | 符合 | 章级 `plan/redo` 不碰卷（`runner.py:439-478`）；`_rearchive` 保留 `start > chapter` 的已付费卷规划（`runner.py:533-543`，`test_volume_gate_precedes_batch_and_rearchive_preserves_next_plan`） |
| 卷 redo 另计费、步骤键 `-redoN` 持久计数 | 符合 | `deliberation.py:239, 253`；`service.py:503-506`；变异 H 被杀 |
| 三步步骤键 | 符合 | `arm-{arm}/vol{n:02d}/01-volume-plan-editor.json` 等，`deliberation.py:240-253` |
| 顾问未入选跳过 | 符合 | `deliberation.py:259`；但见 B2 |
| 卷规划校验：2–5 里程碑且 ≥1 核心、due 在卷内、payoff ≥ ceil(n/period)、只引 open 伏笔、预算 0–6 | 符合 | `schemas.py:224-275`；19 组反例 + 末卷 5 章 ceil 用例；额外校验 volume/chapters 回显、thread 存在、ID 唯一、payoff 类型在 core_payoffs 内 |
| 写入 `dynamic.volumes` + 新版本 `source=volume:n`，里程碑带 status | 符合 | `bible.py:58-76`（安装时统一置 open）；`runner.py:426-428` |
| `volume_gate=false` 自动批准 | 符合 | `runner.py:423-425` `approved: not waiting`；三种自动化方式用例 |
| `volume_gate=true` 且非全自动 → `awaiting_volume`，三接口与流转 | 符合 | approve（可带修改、验证、里程碑重置 open、user_edit 版本）、redo、GET volumes；暂停/恢复不重复开会（`test_volume_gate_precedes_chapter_and_pause_resume_does_not_repeat`）；切全自动自动批准（`runner.py:390-398`） |
| 卷关卡先于批量关卡 | 符合 | `runner.py:354-367` 第 10 章批量关卡改为 `_volume_batch_pending` 标记、先开卷会议/卷关卡，再发批量关卡（`runner.py:315-328`）；变异 E/K 被杀 |
| 卷关卡先于每章关卡 | 符合 | 第 1 章 `_ensure_volume` 在 `deliberate` 之前（`runner.py:311-314`） |
| 最后一卷不足 10 章、max 非 10 倍数 | 符合 | 见上；`payoff_plan` 下限用 ceil |
| 升级后首卷 | 符合规格（见 B1 一章卷） | `service.py:572-574`、`runner.py:403-407` |

### 3. T4 硬校验

| 检查点 | 结果 | 证据 |
|---|---|---|
| 爽点节奏：最近 period−1 章无爽点则本章必填；窗口不随卷重置；书头 `chapter < period` 不要求 | 符合 | `context.py:187-189`；参数化 period 1–5；探针确认第 13 章看 [11,12] |
| 核心主线：实现为「前两章均未推进则本章必推」 | 比 T4.3.2 字面（连续 3 章）严一档，与 D4/§4.3「无连续 3 章空缺」一致 | `schemas.py:536-537`、`context.py:181-183`；报告 §6 已说明 |
| 里程碑到期 | 符合 | `schemas.py:541-543`；但见 A2 |
| 伏笔预算三条 | 符合 | `schemas.py:552-558`；归档阶段再校验实际值与「实际 ≤ 计划」（`657-680`） |
| 报错含具体数值 | 符合 | 探针第 3 章三条错误：`最近 2 章爽点数为 0…每 3 章至少 1 个`、`核心主线已连续 2 章未推进…`、`本卷此前新埋 4 条，本章 2 条，合计 6 条，超过卷预算 4 条` |
| 重写/redo/改稿后计数 | 符合 | `_redo` 重新读库取 history（`runner.py:459-466`）；`approve_plan` 构造 history（`service.py:406-415`）；重归档从归档前版本重算 `structure_history`（`bible.py:115-120`） |
| 死局 | 决策阶段无死局：四条规则两两独立，`plant=[]`、带核心线、填爽点、列到期里程碑可同时满足；探针学习型主编 10 章全部通过 | 归档阶段见 B1（必须修复）与 B7 |
| `decision_invalid` 耗尽后可恢复 | 符合 | `_pause('decision_invalid')` → `resume` → `_activate` → 失败步 `status≠ok` 重新调用（`llm_router.py:393-395`）；卷会议同理 |
| 档案员 `milestones_done ⊆ 本章 milestones_advanced` | 符合 | `schemas.py:659-661`；5 组类型反例 |
| 卷末 open → missed → 下一卷红灯 | 符合 | `bible.py:121-128`、`context.py:203-207`；探针 M1 卷末 `missed` |

### 4. 简报与提示词

| 检查点 | 结果 | 证据 |
|---|---|---|
| 新字段只对 v2 生效 | 符合 | `context.py:143-144`；v1 简报无 `red_flags`（`test_brief_full_history_windows_red_flags_and_isolation` 末行） |
| 数值：payoff_history 2×period 章、staleness = 章距、open 数与上限 20、卷内已埋数 | 符合 | `context.py:175-213`；`test_brief_full_history_windows_red_flags_and_isolation` 断言 `{"T1":12,"T2":1}`、`range(7,13)`、22/20 |
| 简报在裁剪前用全历史 | 符合 | `v2_structure_context` 用未裁剪 `bible`；`trim_bible` 只裁视图（`test_context_trims_archived_records_after_computing_complete_staleness`） |
| 读者代表锚定类型读者、节奏顾问三项检查、所有顾问爽点保护、主编替代爽点 | 措辞符合规格原文 | `agent_pool.py:168-171, 311-318, 302-307`；v1/P0 卡片逐字节不变（`test_v1_and_p0_cards_remain_exactly_unchanged`） |
| 是否仍可被「合理性」意见绕过 | 部分可以 | 保护规则只禁「太快/太巧/太爽」否定 `genre_payoff`，顾问仍可用「与已发生事实冲突」反对（这是允许的），也可以对整章走向而非 `genre_payoff` 提 major 意见间接删爽点；主编「替代爽点」是提示词层约束 |
| 代码兜底是否生效 | 生效但只在到期章 | 顽固主编探针：第 1、2 章删光爽点放行，第 3 章 `01-plan-editor` 两次失败 → `decision_invalid`；非到期章无兜底（规格如此，见 A5） |

### 5. 能否真正纠偏（离线脚本，fake 路由）

探针文件：`scratchpad/v2-review/b/mut/backend/tests/test_zz_probe_force.py`（对工作树的逐字节副本运行）。

- **顽固主编**（每章 `genre_payoff=null`、只推 T2、埋 2 条）：第 1、2 章放行；第 3 章 `arm-panel/ch003/01-plan-editor.json` 首次失败，修复轮错误三条带数值，第二次仍不改 → `StepFailed(decision_invalid)`，书会 `paused`。**拦得住**。
- **学习型主编**（读修复轮错误后照改）：10 章全部通过；爽点在第 3、6、9 章，核心线在第 3、6、9 章，第 4 章被迫列 M1，第 1–2 章埋满 4 条后每章被迫 0 新埋，open 峰值 5；M1 从未被档案员标 done → 卷末 `missed`。**迫使改正成立**，但只达到下限（见 A5）。
- **伏笔持续增加**：卷预算 4 在第 2 章用尽，之后每章都靠修复轮把 `foreshadowing_plant` 清空；open > 20 规则在 `test_open_foreshadowing_budget_only_applies_above_twenty` 与归档用例中验证。
- **仍会漂移的口子**：A3（标签不核验）、A4（钩子谜团不计数）、A2（逾期里程碑无压力）、A6（卷规划不落章）、A7（境界不记录）。这些都不违反规格，但决定了对比实验能否真正体现差别。

### 6. 测试质量

| 检查点 | 结果 |
|---|---|
| 176 条新测试离线通过；既有 53 个 `test_novel_*.py` 文件 1383 条通过；`git diff HEAD -- backend/tests` 为空 | 复跑确认 |
| 基线哈希真实性 | 用 `git archive 85888d5 backend/novel` 提取原版引擎，置于 `sys.path[0]`（确认包内无 `PAYOFF_PROTECTION_RULE`），独立重算 solo/critique/merge × {缺键, v1} 六组 steps/keys/payloads/output 摘要，与 `test_novel_v2_compat.py::BASELINE` 全部一致 |
| 变异分析 | 15 个变异：13 个被杀；**A（爽点窗口放宽一章）存活 → 真实缺口**（A1）；O（服务层恢复 awaiting_volume）存活但为等价变异 |
| 空集恒真 | 未发现：25 章用例先断言 `chapters_done == 25`，滑窗循环 `range(23)` 对空列表会失败；`not any(...)` 类断言都伴随正向断言（版本号、状态） |
| §4.3 统计是否由测试断言 | 是：卷会议 3 次（finalize 调用章号 `[1,11,21]`）、23 个三章滑窗均有爽点与 T1、逐章 ≤2 / open>20 时 planted ≤ resolved / 卷累计 ≤ 预算、`reserved=0`、全部步骤 `settled`、`spent == Σcharged == 余额减少`；在 `DEV_MODE=0` 下走真实预扣/结算，仅把供应商调用换成 fake |
| 注意 | 25 章用例的 fake 主编天然合规（每 3 章自动给爽点、永远推 T1），它证明的是「合规书不会被误拦、账目守恒」，不是「校验会纠正」；纠正力由 core 反例与 `test_v2_invalid_decision_is_repaired_with_concrete_budget_error` 覆盖，深度不如本次探针 |

## 复跑方式

```bash
cd backend
DASHSCOPE_API_KEY=placeholder DEEPSEEK_API_KEY=placeholder ARK_API_KEY=placeholder OPENAI_API_KEY=placeholder PYTHON_DOTENV_DISABLED=1 \
  /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_v2_*.py
```

探针与变异脚本在会话 scratchpad `v2-review/b/`（`probe_baseline.py`、`mutate.py`、`mut/backend/tests/test_zz_probe_*.py`），不进仓库。
