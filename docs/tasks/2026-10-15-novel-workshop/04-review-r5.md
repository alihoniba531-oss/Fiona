# 小说工坊 P0 第 5 轮独立复核（08 critique 推演模式 R5-1～R5-5）

复核对象：工作树 `.worktrees/fiona-novel-p0`，以 `scratchpad/snap-r5/`（改动前 `novel/` 与测试）为基线做 diff。全程离线：未运行真实提供方、未读密钥/.env、未联网、未用浏览器、未读写 `outputs/`、未改仓库内任何文件（仅写本文件）。所有命令在 `backend/` 下用 `Fiona/backend/.venv/bin/python`，带 `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`；dry-run 与变异验证产物都在 scratchpad 的 `review5-*` 目录。

## 结论：通过

五条需求按字面落实，默认 merge 流程逐字节不变，两组写手/审校/档案员输入完全对等，测试纪律符合授权范围。没有阻断问题。下面「真跑风险」里有两条**一行即可改**的建议，关系到真钱，建议真跑前顺手改掉，但不构成不通过。

## 改动面（diff 实测）

| 文件 | 变化 |
| --- | --- |
| `novel/agent_pool.py` | 新增 `REVELATION_RULE` 常量并插入 `DECISION_SCHEMA`；新增 `PLAN_SCHEMA`/`FINALIZE_SCHEMA`（由 `DECISION_SCHEMA` 做 6 处 `.replace()` 派生，我已逐一核实 6 个目标串在原文中各恰好出现 1 次，没有静默未命中）；新增 `CRITIQUE_PLAN_SCHEMA`；`get_agent` 按 task 返回 plan/finalize/critique_plan 卡片 |
| `novel/deliberation.py` | `deliberate` 新增 critique 分支（仅 `panel_mode=="critique"` 且有顾问且 arm 非 solo 且（B 或 A/panel）时走），merge 分支原样 |
| `novel/schemas.py` | 新增 `validate_critique_plan`；`validate_review` 单条 issue 缺 `blocking`/为 null 时置 false 并标 `blocking_defaulted` |
| `novel/writing.py` | `normalize_manuscript` 中文章号识别 + 紧邻重复标题删一行；审校全部丢弃时加 `review_degraded` |
| `novel/pilot.py` | 校验 `panel_mode`；`chapter_record` 新增 `review_dropped_issues`/`review_blocking_defaulted` |
| `novel/report.py` | 新增 `_critique_summary`；每章摘要加两项数字 |
| `novel/fake_llm.py` | 支持 plan/finalize/critique_plan 三个 task |
| `novel/README.md`、`pilot_configs/expA2.json`（新增） | 文档与新配置 |
| 既有测试 | 仅 `tests/test_novel_r2_schemas.py` 两处授权分支（见「测试纪律」） |
| 新增测试 | `test_novel_r5_{cards_fake,deliberation,pilot_report,schema_writing}.py` 共 150 项 |

`git status --porcelain` 无 `M`/`A`/`D` 条目。

## 公平性核验（solo 组 vs critique 组）

### 简报与载荷

- `build_brief(compass, bible, chapter, history, written_words, user_notes)` 两组走同一函数；`history` 只被 `chapter_mode` 读 `ending_status`。A2 dry-run 实测 ch1 solo `03-decision-editor` 与 panel `01-plan-editor` 的 `brief` 完全相等。
- solo decision 载荷键：`brief, chapter, mode, note_ids, objection_ids, objections, proposal_ids, proposals, scores, solo, task, user_notes`；panel plan 载荷键：同上去掉 `proposals`（值 `[]`）与 `scores`（值 `{}`）。两个被去掉的键在 solo 下都是空值，不构成信息差。
- 顾问载荷键：`brief, chapter, mode, plan, task`，`plan` 只含 `beat_sheet, rationale, ending_status`（`deliberation.py:95-96`），与需求一致。
- finalize 载荷键：`brief, chapter, critiques, mode, note_ids, objection_ids, objections, plan, proposal_ids, solo, task, user_notes`。

### 主编三张卡片逐行 diff（我用 `difflib` 对 `get_agent("editor", task=…)` 的实际系统提示做的）

decision → plan 只差 5 行：角色句（「负责本章裁决」→「负责独自构思本章初案」）、`task=` 名、JSON 示例的两个空数组、「综合评分但不要机械选择最高分，可以合并多个提案，rationale 说明具体取舍」→「根据简报独自构思本章初案，rationale 说明具体创作取舍」、两句机制说明（提案选择/回应范围）。

decision → finalize：同上的角色句/task 名/空数组，外加把「综合评分…」那一行替换成需求要求的 6 行（最好的写法、不要拼合多个方向、major 改或说明理由、认真评估替代走向可整体换、A* 写明采纳/部分采纳/不采纳及理由、rationale 说明相对初案的改动），以及回应范围加入 A*。

**三张卡片完全相同的部分**：五维度那一句、R5-4 那一句（各恰好 1 次）、「不重复 used_beats…每章必须有一个读者能说得出来的新发现」、细纲约束（主线/人物/场景/节拍数）、伏笔回收与 closing/end 规则、`JSON_STRING_QUOTE_RULE`、`INJECTION_GUARD`。`max_tokens` 三者均 6000。结论：critique 组的 plan 相对 solo decision 没有多任何创作约束；finalize 多出的 6 行全部是需求点名要求的。

solo decision 卡片仍保留两句对 solo 无意义的 merge 文字（「综合评分…可以合并多个提案」「推演会模式必须至少选择一个存在的提案」）——这是改动前就有的，且与已跑过的 expA solo 组一致，保留反而维持了可比性；见可优化项 4。

### 执行层（写手/审校/档案员）

- `write_chapter` 只读 `meeting["decision"]["beat_sheet"]`（`writing.py:89-90`），不碰 `plan`/`critiques`/`objections`；`pilot.py` 也只取 `meeting["decision"]`。
- A2 dry-run 实测：10 次写手调用（两组各 5 章）的载荷键集合（含 `context.*`、`beat_sheet.*`、`length_range.*` 两层展开）完全相同，系统提示 10 份逐字相同，没有 `plan/critiques/objections/scores/proposals/panel_mode/decision` 任何一键。
- 审校 10 次、档案员 10 次同样键集合相同、系统提示相同。
- 模型配置：两组共用同一个 `agents` 字典（主编 sonnet-5-5、写手 deepseek-flash、审校/档案员 qwen3.8-max），arms 只选推演角色。

### 结论

除「panel 主编多一次定稿、定稿时看到三位顾问意见」这一设计本身，没有任何通道让一组多拿信息或多一条约束。

## 逐条核验

### R5-1 critique 推演模式

- **流程与步骤文件名**：A2 dry-run 中 panel 每章依次 `01-plan-editor.json`、`02-critique-plan-{plot_architect,character_advocate,twist_designer}.json`、`03-finalize-editor.json`；无 proposal/打分步骤；solo 每章仍只有 `03-decision-editor.json`。`test_critique_runs_plan_then_parallel_advisors_then_finalize` 另断言调用顺序与 step_key 原文、并发上限 3。
- **初案**：`validate_decision(..., proposal_ids=[], objection_ids=[], solo=True)`（`deliberation.py:83-93`）；`test_plan_uses_solo_validation_before_any_advisor_runs` 三个变体（选了提案 / 回应了不存在的 O1 / 漏回应留言）都在顾问调用前失败。
- **顾问 schema 与校验**（`schemas.py:validate_critique_plan`）：`objections` 1–3 条（`c.array(min=1,max=3)`），四字段非空、`severity` 枚举 major/minor、`keep` 非空；`twist_designer` 的 `alternative` `minimum=1`，其他角色缺失或 `""` 通过。模型自带 `id` 会被代码分配的 `id` 覆盖。
- **ID 分配**：先按配置顺序把所有 objection 编 O1…On，再把非空（strip 后）alternative 编 A1…（`deliberation.py:106-117`）；`test_ids_follow_configuration_order_even_when_advisors_finish_in_reverse` 让完成顺序倒置仍得 `O1-O4, A1, A2`；纯空白 alternative 不编 A。
- **定稿**：`validate_decision(solo=True, objection_ids=O*+A*)`，`_responses` 要求 `len(seen)==len(allowed)` 且每个 ID 恰好出现 1 次且无外来 ID（`schemas.py:292-303`）；漏答/重复 O 或 A 四个参数组合都判失败。
- **不打分**：critique 分支没有 scores 计算，meeting 无 `scores` 键，报告无「均分」「选中提案」字样（测试断言）。
- **提示词**：finalize 卡片含「不要为了照顾意见而把多个方向拼在一起」「如果它明显更好，可以整体换成它」「对每条 major 意见，要么改，要么说明不改的理由」「这一章最好的写法，而不是让每条意见都满意」逐字；`critique_plan` 卡片含「只挑会让本章变差的真问题，不挑措辞」「每条意见都要给出可执行的改法」「不要另起一个完整方案；反转设计师的 alternative 是唯一例外」逐字，并通过 `split(PROPOSAL_SCHEMA)` 保留各角色原有四条视角清单（6 个顾问角色参数化测试）。
- **记录与报告**：`chapter_record.meeting` 键为 `mode, brief, plan, critiques, objections, decision`；`report.md` 展示初案要点（章名/目标/节拍/两个钩子/理由/ending_status）、每位顾问的 keep、每条 O*（作者、严重度、target/problem/suggestion、主编回应）、每条 A*（全文、主编回应）、8 字段「定稿相对初案的改动」表、定稿理由与说明。我在 A2 dry-run 的 report.md 中逐段核对过。
- **默认 merge 不变**：用快照代码与现版代码分别跑 expA/expB dry-run 后比对——A 71 个、B 109 个步骤键集合相同；**每个步骤的 result 相同**；全部 chapter_record 的 `meeting` 相同（键仍为 `brief, decision, objections, proposals, reviews, scores`）；chapter.md 逐字相同。唯一差异：`03-decision-editor.json` 的系统提示多了 R5-4 那一行（用户消息逐字相同），以及 record 多两个诊断键。expC 以本次 A 为 `--source-run` 退出 0。

### R5-2 审校缺 blocking 默认非阻断

- `schemas.py:396-400`：在规范化副本上先剥掉模型自带的 `blocking_defaulted`，`blocking` 缺失或 None → `False` + `blocking_defaulted=True`；其余字段仍走原来的结构检查（缺字段、`"false"`/`0`/`[]` 等非法值仍丢弃），证据逐字核对仍适用。
- `writing.py:144-145`：某轮 `issues` 为空且 `dropped_issues` 非空 → 加 `review_degraded`（只加一次）；合法空 issues 不加。`pilot.py:120-124` 跨轮累计两项数字；`report.py` 每章输出「被丢弃的 issue 条数：n；blocking_defaulted 条数：m」。
- 测试覆盖：缺/null 保留、其他字段缺失仍丢弃（正控）、非 null 非法值不默认、证据不符仍丢弃、标记归代码所有、全丢弃标降级、空/部分保留不降级、后轮可降级、端到端两组记录与报告。

### R5-3 中文章号与去重

- 正则 `第\s*([0-9零〇一二两三四五六七八九十百千]+)\s*章`，`_chapter_number` 处理纯数字串、纯汉字数字串（「一〇二」）与带十/百/千的写法（「十二」「二十一」「一百零二」），结果与 `chapter` 比较后才视为本章标题。
- 去重只看规范首行之后第一个非空行，且去掉章号后标题相等才 `del` 那一行；`test_adjacent_duplicate_title_removes_only_that_one_line` 证明正文行内空格、后面第二个同名标题都原样保留；章号不一致（本章 3、首行「第二章」）插入规范首行并保留原行；`validate_manuscript` 未动。

### R5-4 每章最多一个关键揭示

- `REVELATION_RULE` 与需求原句逐字相同；我的脚本实测 decision/plan/finalize 三张卡片各恰好出现 1 次；`test_a2_all_editor_cards_have_the_exact_one_reveal_rule` 直接检查 A2 dry-run 中 solo decision、panel plan、panel finalize 的实际系统提示。`grep 揭示` 在 schemas/deliberation/writing/pilot 均无命中，没有硬校验。

### R5-5 expA2.json

- `experiment=A`、`panel_mode=critique`、`arms` 与 `adaptation` 与 expA 相等（程序比对）、`chapters_per_arm=5`、`user_notes={}`、`target={50,70,2000}`、`critique_rounds=1`、七个 agents 与需求逐项一致（人物代言人 `ark:doubao-seed-2-1-pro-260915`）。`seed_idea` 用正则从 08 文档「」内抽出与配置比较：逐字相同。
- 03-report.md「critique 模式」节贴的估算表与我本次 dry-run 输出逐数字相同（editor 16 次 / 63859 / 102000 等），说明 fake 轨迹确定。

## 测试纪律

- `tests/test_novel_*.py`：**892 passed**（742 旧 + 150 新），退出 0。
- 既有测试改动：只有 `test_novel_r2_schemas.py` 两个 hunk，分别在 `test_review_missing_issue_field_is_dropped_without_mutating_source[blocking]` 与 `test_review_wrong_issue_field_type_is_dropped[blocking-None]` 分支上加 `if/else`：参数化输入未动，else 分支保留原断言原文，`data == before` / `report == before` / `passed is True` 对所有分支仍执行。与验收方授权范围一致。其余 20 份既有测试与快照逐字节相同。
- 新测试文件访问：只读 `novel/pilot_configs/*.json`（`Path(__file__).parents[1]`）与 pytest `tmp_path`；grep `/tmp|outputs|/Users|expanduser|home()|environ[` 零命中。`test_novel_r5_pilot_report.py` 的 autouse fixture 把 `os.environ` 换成 `{}`，并把 `openai.AsyncOpenAI`、`anthropic.AsyncAnthropic`、`socket.connect/connect_ex` 全部打成断言失败。
- **变异验证**（在 scratchpad `review5-mut/` 的隔离副本上做，每次先 `import novel.schemas` 打印 `__file__` 证明导入的是副本；基线 892 绿）：

| 变异 | 结果 |
| --- | --- |
| M1 `_responses` 去掉「数量相等且每个 ID 恰好一次」只保留「无外来 ID」（R5-1 回应校验） | 7 红：`test_finalize_requires_exactly_one_response_…` 四个参数（missing/duplicate × O/A）、plan 漏回应留言、既有 `test_missing_objection_or_user_note_response_rejected` 两项 |
| M2 `validate_critique_plan` 的 twist `minimum=1` 改成 0（R5-1 alternative 必填） | 2 红：`test_twist_critique_requires_nonempty_text_alternative[""]`、`[" \n "]`（None/[]/12 仍被「必须是字符串」拦住，符合预期） |
| M3 `del lines[next_line]` 改 `pass`（R5-3 去重） | 3 红：`test_adjacent_duplicate_title_removes_only_that_one_line` 三种分隔 |
| M4 额外：`objections.extend(alternatives)` 改 `pass`（A* 不进回应清单） | 5 红：ID 顺序、空白 alternative、finalize A 漏答/重复、A2 端到端 |

- 小瑕疵（不影响结论）：`test_non_twist_critique_allows_omitted_or_empty_alternative` 参数化的角色名 `reader_advocate`/`pacing_editor` 在 `AGENTS` 中不存在（真实名是 `reader_rep`/`pacing_advisor`），校验函数不查角色所以照样有效；它的 `None` 参数表示「省略键」，`"alternative": null` 这一形状没有被测到——正是下面风险 1。

## 阻断问题

无。

## 真跑风险与可优化项

1. **（建议真跑前改，一行）非反转顾问返回 `"alternative": null` 会校验失败。** `alternative` 不在 `_OPTIONAL_TEXT_FIELDS`，`_normalized_copy` 不会把 null 转成 `""`，于是 `c.text(None, minimum=0)` 报「必须是字符串」（我已实测 plot_architect/character_advocate 两角色：省略 OK、`""` OK、null FAIL）。提示词示例里 `"alternative":"替代走向"` 是字符串且说「允许缺失或为空」，模型多半输出 `""` 或省略，但 qwen/豆包给 null 并非不可能。代价：每次多一次修复重试（顾问调用，输出上限 2500），连续两次则该章 `step_failed` 退出 4（已成功步骤缓存，可续跑，不算白花钱但要人工介入）。修法：把 `"alternative"` 加进 `_OPTIONAL_TEXT_FIELDS`，或在 `validate_critique_plan` 里把 None 当 `""`。
2. **（建议真跑前改，一行）finalize 的 `max_tokens` 与 decision 同为 6000，但输出要多装最多 9 条 O* + 3 条 A* 的回应，且提示词要求每条 A* 和每条未采纳的 major 都写理由。** 估算：细纲+理由+说明约 2000–3500 token，12 条回应各 60–120 字再加 800–1900 token，总计 3000–5500，仍在 6000 内但余量比 decision（3 条回应）薄得多。截断后路由会追加一次「压缩重输」（再付一次主编调用），再截断就 `decision_invalid` 停工。`max_tokens` 只影响预算预留，不额外计费，把 finalize 卡片改成 8000 几乎零成本。另注：`CLAUDE_THINKING["claude-sonnet-5-5"] = {"type": "between_tools"}`，离线无法确认思考 token 是否计入 `max_tokens`，这一点与上一轮相同。
3. （可优化）finalize 载荷里每条意见出现两次：`critiques[*].objections`（无 ID）与 `objections`（有 ID）。fake 下两者 815 + 767 字符；真跑每章多 2–4k 字符输入 × 5 章，费用小。若要省，可把 `critiques` 精简成 `{author, author_name, keep}`。
4. （可优化）solo decision 卡片仍有两句对 solo 无效的 merge 文字，见「公平性核验」。本轮不改是对的（与 expA solo 组一致）；若将来重做 solo 基线可一并清理。
5. （可优化）`_critique_summary` 的改动表和既有 `_table` 一样不转义值里的 `|`，节拍里出现竖线会破坏 Markdown 表格；纯展示问题。
6. 预算：A2 估算输入 ≈ 23.7 万、输出上界 ≈ 27 万 token（Claude 输入再 ×1.35），远低于默认 `--max-total-tokens 3,000,000`，续跑语义（成功步骤缓存、失败步骤重试）在 critique 分支同样成立。
