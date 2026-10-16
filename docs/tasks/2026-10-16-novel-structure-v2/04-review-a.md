# 复核 A：兼容性、外部契约与审校收敛（T1、T5、T6、契约保护、计费与断点续跑、测试质量）

- 复核对象：分支 `novel-structure-v2` 工作树（基线 `85888d5`），未提交改动；规格 `02-spec.md`（含 §7 R1、§8 R2）；完整 diff 与 `03-report.md` 只作线索。
- 复核方式：全部离线、占位密钥；把 `85888d5` 的 `backend/novel` 用 `git archive` 取到 scratchpad 并以 `novel_base` 包名载入，与现版在同一 fake 路由下逐字节对比；对现版做定向探针；在 scratchpad 的 backend 副本上做 19 条变异验证新增测试。探针脚本与日志在 `scratchpad/v2-review/a/`（probe1–probe9、mutate.py/mutate.log），仓库内未改任何文件。
- 日期：2026-10-16。

## 结论：**不通过**（3 项必须修复，均集中在 T5 审校收敛与 T6 升级后的归档边界；T1/契约/计费/断点续跑全部核验通过）

v1 零回归、P0 pilot 逐字节不变、五个只读服务接口与 `novel_chapters` 列、圣经既有键、卷会议计费与续跑、T6 升级的状态与卷号计算都经独立构造的对比与探针确认无误。不通过的原因是 T5 的代码兜底有三处会把**真正的连贯性错误**或**未修复的旧阻断问题**放行，以及 T6 升级后编辑旧章会触发归档失败；这几处都能用最小探针稳定复现。

## 必须修复项

### A1. 复审降级拿「截断后的 changed_passages」判定，改动量超过约 3000 字后，改动段落内新引入的硬伤被判为 `outside_changes` 放行

- **现象**：写手修订时改动段落合计超过 3000 字（`chapter_words=2000` 的书、写手按提示「返回修正后的完整新稿」时很常见），审校在**改动段落内**发现的新连贯性错误（例如死人复活），只要其所在段落落在 3000 字截断之后，就被降为 `blocking=false`、标 `outside_changes=true`，章节以 `passed=True`、`flags=[]` 通过。基线 85888d5 会保持阻断并进入下一轮修订，这是相对基线的回归。
- **证据**：
  - `backend/novel/writing.py:250-258`：`passages = changed_passages(previous_review_body, body)` 返回的是已截断列表（`writing.py:36-47`，`paragraph[:remaining]` 还会把段落截半），随后同一个 `passages` 既发给审校又传给 `_validate_focused_review(... passages=passages)` 做兜底判定。
  - 探针 `probe3_t5_review.py` Case B：旧稿 12 段、新稿 12 段全部改写（合计 4400 字），r1 审校在最后一段引用 `林澈在第十二段里死而复生地站了起来。` → 输出 `payload_passages_chars=3000 full_changed_chars=4400 evidence_in_full_changed=True blocking=False outside_changes=True passed=True flags=[]`。
  - 实施方的测试 `backend/tests/test_novel_v2_review.py:191-208` 把这个行为固定成了期望（断言被截掉区域内的证据 `outside_changes is True`），与规格 T5.2 的兜底定义「evidence **不在任何改动段落内**的新问题一律降级」相反——规格里的 3000 字上限只约束 payload，不约束兜底判定范围。
  - 同源放大：`changed_passages` 只按空行切段（`writing.py:26`）。写手若用单换行分段（Markdown 里允许），整章就是一个「段落」：任何一处小改都让整章成为改动段，再被截到 3000 字，3000 字以后的新问题全部降级（Case C：`passages=2 chars=3000 blocking=False outside_changes=True passed=True`），同时前 3000 字内的新问题又永远不会被降级，收敛目的也落空。
- **后果**：T5 的目标是「不在没改的地方挑新问题」，现在变成「改得越多越不检查」。写手大改之后恰恰是最容易新引入矛盾的时候，这些矛盾会被静默放行写进定稿，且没有 `review_unresolved` 标记供作者察觉。
- **修法**：
  1. 兜底判定用**未截断**的改动段落集合（`changed_passages(..., limit=None)` 或拆成「计算全集」与「截断成 payload」两步），只对发给模型的 payload 截断；截断说明不参与匹配。
  2. 段落切分退化处理：按 `\n` 行切分（或空行切分后若只得到 1–2 段再退化为按行），避免单换行正文把整章当成一个段落。
  3. 相应修改 `test_novel_v2_review.py:191` 的断言为「截断区域内的证据仍保持阻断、不带 `outside_changes`」，并补一条「单换行正文」的用例。

### A2. 「新问题」只按 evidence 去空白后**精确相等**判定，且归一化与 `validate_review` 的 `compact()` 不一致——未修复的旧阻断会因引用跨度/引号写法不同被当成新问题降级放行

- **现象**：
  - (a) 上一轮阻断问题未修复、正文未改，审校复审时**同一句话换了引用跨度**（少引几个字、多引一个标点）→ 不等于 `previous_blocking_issues` 的 evidence，又不在改动段落里 → 降级为非阻断，`passed=True`、`flags=[]`，一处写手没改的锁定设定冲突就这样通过了。基线会保持阻断、三轮后打 `review_unresolved`。
  - (b) 正文用弯引号 `“ ”`，模型引用时写成直引号 `" "`（或反之）：`validate_review` 用 `compact()` 去掉引号后能匹配正文、保留该问题（`schemas.py:23-26`），但 `_validate_focused_review` 只去空白（`writing.py:54-57`），`evidence in passage` 失败 → 改动段落内**真正的新硬伤**也被降级。
- **证据**：
  - `backend/novel/writing.py:54-58`：`old_evidence = {re.sub(r"\s+", "", ...)}`；`if evidence not in old_evidence and not any(evidence in passage ...)` → 降级。
  - 探针 `probe3_t5_review.py` Case A：r0 evidence `林澈仍然站在旧控制台旁，手里拿着那份白色文件夹。`，正文未改，r1 用 `仍然站在旧控制台旁` 复报同一问题 → `blocking=False outside_changes=True passed=True rounds=2 flags=[]`。
  - 探针 probe9（Case D）：改动段落 `林澈说：“原件早就不在保险柜里了，三天前就被人取走。”`，审校以直引号引用同一句 → `validate_review` 保留（`kept=True`），`_validate_focused_review` 判为 `blocking=False outside_changes=True passed=True`。
- **后果**：规格 T5.2(a) 要求「逐条判断 previous_blocking_issues 是否已解决」，未解决的必须仍为阻断。现在模型只要换个引用写法，未修复的旧问题就被代码兜底清掉，审校的「收敛」变成「清零」。(b) 是明确的实现 bug（两处归一化口径不同）。(a) 规格原文「与 previous_blocking_issues **不重合**的问题，判定依据是 evidence 不同」——实现取了最严的「精确相等」读法；按「不重合」的字面意思，与旧 evidence 有重叠即应视为同一问题。
- **修法**：
  1. 两处匹配统一用 `schemas.compact()`（与 `validate_review` 同口径）。
  2. 「旧问题」判定改为重叠判定：新 evidence 与任一旧 evidence 互为子串，或二者在正文中的位置区间相交（可用 `body_compact.find()` 定位），或落在同一段落；满足任一即视为旧问题复报，保持模型给出的 `blocking`。
  3. 可选加固：在 P1 审校 schema 里加可选字段 `previous_issue_index`（复审时指明对应上一轮第几条），有该字段时直接按索引归类；无字段再走重叠判定。
  4. 补测试：旧问题换跨度复报仍阻断；直/弯引号差异不影响改动段内新问题的阻断。

### A3. T6 升级后，对升级前写好的 v1 章节「编辑最新章 → 重新归档」会套用 v2 伏笔预算与「不得超过细纲计划」校验，合法旧章改稿后归档失败、书进入 `paused/step_failed`

- **现象**：v1 书第 2 章归档时档案员记录了 3 条实际新埋伏笔（v1 允许；重新归档也通过）。升级到 v2 后作者编辑第 2 章正文（最新章）→ 重新归档被 `validate_archive(..., config=v2, decision=v1决策)` 以 `本章新埋 3 条，超过每章上限 2 条` 和 `实际新埋 3 条，不得超过细纲计划 0 条` 拒绝，修复重试仍失败 → `StepFailed` → 书 `paused`、`pause_reason=step_failed`。
- **证据**：
  - `backend/novel/runner.py:494-503`（`_rearchive`）：只要 `config.structure == 'v2'` 就传 `config`/`decision` 进 `validate_archive`；`backend/novel/schemas.py:652-680`（`_archive_v2`）对任何章节套用每章 ≤2、>20 净增、卷预算及 `len(planted) > len(planned)` 四条规则，不区分该章的细纲是否在 v2 下产生（v1 细纲没有 `genre_payoff`/`milestones_advanced`，也从未受过伏笔预算约束）。
  - 探针 `probe8_rearchive_after_upgrade.py` 输出：`v1 re-archive after edit: status awaiting_review` → 升级后 `status paused pause_reason step_failed archive attempts 2 repair errors [['archive.foreshadowing_planted：本章新埋 3 条，超过每章上限 2 条', 'archive.foreshadowing_planted：实际新埋 3 条，不得超过细纲计划 0 条']]`。
- **后果**：规格 T6.3「升级只修改三处，不改动已写章节和既有圣经内容」；升级确实没改章节，但使一个升级前合法、升级后作者常做的操作（审阅时改最新章文字）失败并把书挂起。真实模型的档案员本就会记录细纲外实际出现的伏笔（归档 schema 要求「只记录最终正文实际发生的事」），用 v2 规则逼它少记录，等于让归档撒谎或失败。
- **修法**：`_archive_v2` 只对 v2 细纲生效：`decision` 中没有 `genre_payoff` 键（或该章 < 升级后首卷 `start_chapter`，即 `config["_volume_gate"]`/首个 volume 的起点）时跳过伏笔预算与「不得超过细纲计划」校验，仅保留 `milestones_done ⊆ milestones_advanced` 这类无害检查；`_rearchive` 同理。补测试：v1 旧章升级后重新归档结果与升级前逐字节一致。

## 可优化项（不阻断）

1. **冗余的卷关卡恢复分支**：`runner.py:384`（`_ensure_volume` 里「已有未批准卷规划则停 awaiting_volume」）与 `service.py:658`（`resume` 直接回到 awaiting_volume）互为备份——变异测试中两者**各自单独去掉都 176 全绿**（mutate.log M4、M19），现有用例无法区分。要么保留一处，要么补一条只走 runner 分支的用例（例如 `volume_gate` 开着、`_volume_gate.approved=False`、状态被置为 `running` 后启动）。
2. **`volume_gate=False` 写进每本新书（含 v1）的 `config_json`**（`service.py:210`）。行为无影响，`detail().config` 多一个键；probe5 显示这是 v1 书落库数据与基线唯一的差异。可改为只在 `structure=='v2'` 时写入，让 v1 书的 `config_json` 也与基线一致。
3. **`reject_end` 延长篇幅后的卷划分**：非升级路径下 25 章书延到 27 章，会新开第 4 卷 `[26,27]`（`runner.py:409` 以「无覆盖当前章的卷」为触发），而不是延长第 3 卷。规格没写这种情形；建议在报告里明示，或把末卷 `chapters[1] == 旧 max_chapters` 时改为延长末卷。
4. **升级进行中可被 `pause` 打断**：`transition('pause')` 不检查 `_check_not_editing`，会 `cancel_novel` → 退还预扣并清 `run_token`，正在跑的 `upgrade_structure` 随后以「小说状态已变化」失败（已确认不会重复扣费，主编那一步未落库不计费）。建议 `pause` 也调用 `_check_not_editing`，或在升级中禁用 pause。
5. **§4.3 25 章验收的证明力**：`test_25_chapter_paid_fake_acceptance` 的 fake 主编每章都推进核心主线、按节奏自动给爽点（`fake_llm.py:244-249`），因此「每 3 章至少 1 个爽点 / 核心主线无三章空缺 / 预算未突破」是 fake 的构造结果，证明的是管线与账目（这部分确实可信：预扣/结算/余额三方一致、190 步无重复），不是硬校验的拦截力。拦截力由 `test_novel_v2_core.py` 的正反例与 `test_v2_invalid_decision_is_repaired_with_concrete_budget_error` 覆盖，报告里宜把两者分开说。
6. **P1 审校卡片同时含「每轮最多 3 条」与「首轮最多 8 条」**：按 T5.4 保留原句、追加说明，可接受；追加段开头「对前文的轮次数量与复审范围作补充约定」已说明优先级。若后续冻结测试允许，建议在第二期收敛成一句。
7. **P0 pilot 的 `cost.md`/`blind/key.json` 差异**：对比两版 pilot 输出时只有这两个文件不同，分别是「平均耗时 ms」列和 `SystemRandom().shuffle` 的盲评钥匙，均为运行时噪声，不是回归；写在这里以免后人误判。

## 1–6 逐条核验表

| # | 核验点 | 方法 | 结果 |
|---|---|---|---|
| 1 | **v1 零回归** | probe1：`novel_base`（85888d5）与现版各自用自己的 `LLMRouter(dry_run)+RunStore+FakeLLM` 跑 `deliberate+write_chapter` 10 章（含第 10 章卷摘要），solo/critique/merge × 缺 `structure` 键/显式 `v1` × `drama_adaptation` 开/关 × 有/无审校，共 13 组、最多 121 步/组；比较**全部 messages（system+user）**、步骤键、会议/正文/审校/归档输出及圣经版本号 | **通过**。13 组逐字节一致；唯一差异是 P1 审校 system 提示词（每组 10 处），且基线原句完整保留在前缀（T5.4）。 |
| 1 | P0 离线 pilot | probe2：两版 `run_experiment` 跑 expA/A2/B（small 与完整各一次）与 expC（以同一 A 结果为 source），对输出目录逐文件比较（含每步 messages/raw/result） | **通过**。所有 step 文件、章节、圣经、报告一致；仅 `cost.md` 的耗时列与 `blind/key.json` 的随机盲评顺序不同（运行噪声）。 |
| 1 | runner/service 级 v1 流程 | probe5：两版各在独立进程、独立临时库里跑同一本 v1 书（建书→立项→批次关卡→暂停/改自动化→每章关卡 redo/approve→改最新章重归档→改旧章 stale→拒绝完结延长→确认），比对状态流、全部圣经版本 JSON、章节行、步骤键、留言、导出 | **通过**。状态/版本号/章节/圣经/步骤键/导出全部一致；fake 调用（按步骤键排序，排除 P1 审校 system）一致；仅 `config_json` 多 `volume_gate:false`（见可优化 2）。 |
| 1 | 实施方 BASELINE 哈希真伪 | probe4：用 `novel_base` 重跑 `test_novel_v2_compat.engine_snapshot` 逻辑 | **通过**。solo/critique/merge 三组哈希与测试内 `BASELINE` 完全相同，证明快照确来自 85888d5，测试非恒真。 |
| 2 | **外部契约** | 直接比对两版源码与签名：`list_books/detail/bible/chapter/owned`（另含 `find_books/chapters_range/notes`）签名与函数源码；`store_db.py`、`billing.py`、`llm_router.py`、`run_store.py`、`pilot.py`、`report.py` 与基线 diff | **通过**。八个函数签名相同，`summary/detail/bible/chapter/_chapter_result/list_books/find_books/chapters_range/export/edit_chapter` 源码逐字相同；上述六个模块与基线完全一致；`novel_chapters` DDL 相同（sha256 `45d349c7…`）。圣经既有键：probe1/probe5 中 v1 书的 bible JSON 逐字节一致，v2 只新增 `dynamic.volumes/structure_history`。`completed/done/stale` 逻辑所在函数未改动；新状态 `awaiting_volume` 只出现在 `update_character`、`transition('pause')`、`resume` 分支及新接口的 `owned()` 白名单中，`pending_gate` 规则（`startswith('awaiting_')`）自然覆盖。 |
| 3 | **T5 审校收敛** | 阅读 `writing.py:19-62,246-260`、`agent_pool.py:173-180,319-320`；probe3 Case A/B/C、probe9 Case D；既有冻结测试 `test_novel_p21_writing.py`、`test_novel_r2_prompts.py` 随 1559 项 novel 测试全绿 | **不通过**（A1、A2）。首轮 >3 条阻断可保留、上限 8 写入提示词 ✓；复审 `changed_passages` 增/改/删/截断计算与 R2 零改动省略字段并降级 ✓；旧问题（evidence 精确相同）不受改动范围限制 ✓；细纲措辞不阻断、R2 句子、冻结原句均在 P1 卡片且 P0 卡片不变 ✓。但：截断后的集合被用于兜底判定（A1）、精确相等+归一化口径不一致（A2）会放行真正的新硬伤与未修复旧阻断。 |
| 4 | **T6 升级接口** | 阅读 `service.py:515-590`；probe7 对 `chapters_done ∈ {0(paused),9,10,15,20}` 的 25 章 v1 书逐一升级并跑完；probe8 升级后改最新章 | **部分通过**。允许状态仅 `awaiting_review/paused`、复用 `_check_not_editing` 与 `editing_novel` 互斥 ✓；只改 `compass.genre_contract` 与 `config.structure/volume_gate=False/_volume_upgrade`，圣经版本与章节行逐字节不变 ✓；卷号/范围与规格公式一致：0→(1,[1,10])、9→(2,[10,10])、10→(2,[11,20])、15→(3,[16,20])、20→(3,[21,25])，后续卷顺延 ✓；失败/取消退款、断点同输入复用均由实施方测试覆盖并通过。**不通过点**：升级后对旧 v1 章重新归档套用 v2 预算导致 `step_failed`（A3）。 |
| 5 | **计费与断点续跑** | probe6：`DEV_MODE=0`、真实 `NovelBilling`、仅把供应商响应换成本地 fake；分别在 `01-volume-plan`、`02-volume-critique`、`03-volume-finalize` 三步中途暂停再恢复（含 `volume_gate=true` 情形），以及连做两次 `volume/redo` | **通过**。每种中断下仅被打断的那一步重调 1 次，其余卷步骤各 1 次；`volume:1` 版本恰 1 个；`spent == Σ步骤实扣 == 余额减少`，`reserved == 0`，全部步骤 `settled`、步骤键唯一。redo 两次产生 `-redo1/-redo2` 八个独立键、各调 1 次、三个 `volume:1` 版本，账目守恒。runner 对状态机的改动只新增 `awaiting_volume` 与 `_volume_batch_pending` 标记，`_pause` 原因集合、`commit_chapter`、`save_plan` 未动；`llm_router.py`/`billing.py` 与基线相同。 |
| 6 | **测试质量** | 176 项新增测试在工作树通过；全部 `test_novel_*.py` 1559 项通过；既有测试 `git diff HEAD -- backend/tests` 为空；grep 新测试无 `/tmp`、`/Users`、`subprocess`、`git`、`node_modules`、`open(`；在 scratchpad 副本上做 19 条变异 | **基本通过，有两点保留**。19 条变异杀死 17 条（审校不降级、忽略 replace、P0 也聚焦复审、升级开卷关卡、默认 v2、P1 规则不追加、批关卡压过卷关卡、核心主线窗口 3→4、卷末不标 missed、redo 复用步骤键、升级允许 awaiting_end、爽点永不必需、R2 总发字段、卷规划不落版本、批准不重置里程碑、milestones_done 不受限、structure_history 不裁剪）。存活 2 条是互为备份的分支（可优化 1）。保留点：`test_changed_payload_is_truncated_and_reports_outside_clipped_area` 把 A1 的错误行为固定成期望；§4.3 验收用例由 fake 构造满足指标（可优化 5）。 |

## 其他核对

- 新增测试文件只依赖仓库内夹具（`test_novel_schemas` 的 `setup_data/decision_data/archive_data`），`conftest` 在收集期强制临时库；`BASELINE` 哈希已独立验真。
- 文档改动（`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`）与实现一致；`03-report.md` 中「P1 reviewer system 提示词仅按 T5 有意追加，user payload 比对没有忽略字段」属实。
- 规格 §6「卷关卡先于章关卡」：`_volume_batch_pending` 在第 10 章先发下一卷/卷关卡再发批关卡，并可断点恢复、切全自动时清除（变异 M8 被 `test_volume_gate_precedes_batch_and_rearchive_preserves_next_plan` 与 `test_switching_full_auto_clears_pending_batch_after_volume_gate` 杀死）。
- 全量后端测试：`python -m pytest -q --deselect tests/test_exchange_isolation.py --deselect tests/test_safe_http_deadline.py` → **5413 passed, 15 deselected**（169 s）。去掉的两个文件是实施方报告中因沙箱禁止绑定回环端口而失败的 6 项所在文件，与本单改动无关；其余全部通过，说明文档类测试与非小说模块无连带回归。

## 探针与日志索引（scratchpad/v2-review/a/）

| 文件 | 内容 |
|---|---|
| `probe1_v1_engine_compare.py` | v1 引擎级两版逐字节比对（13 组） |
| `probe2_p0_pilot_compare.py`, `probe2.log` | P0 pilot A/A2/B/C 两版目录比对 |
| `probe3_t5_review.py` | T5 Case A/B/C 假阴性复现 |
| probe9（内联脚本，输出见本文 A2） | T5 Case D 引号归一化不一致 |
| `probe4_compat_baseline_hash.py` | 验证 `test_novel_v2_compat.BASELINE` 来自 85888d5 |
| `probe5_runner_v1_snapshot.py`, `p5_base.json`, `p5_new.json` | runner/service 级 v1 流程两版快照 |
| `probe6_volume_billing_resume.py` | 卷会议三步中断续跑与 redo 计费 |
| `probe7_upgrade_edges.py` | T6 升级卷号/范围五种 `chapters_done` |
| `probe8_rearchive_after_upgrade.py` | A3 复现 |
| `mutate.py`, `mutate.log` | 19 条变异与结果 |
| `basepkg/novel_base/` | `git archive 85888d5 backend/novel` 的改名副本 |
