# 小说工坊 P0 第 3 轮独立复核（第 2 轮返修 R2-1~R2-4）

复核日期：2026-10-15。复核对象：工作树 `.worktrees/fiona-novel-p0`，所有新增文件为未跟踪文件，直接读文件核验。依据：`05-fix-r2.md`（R2-1~R2-4）；`03-report.md` 第 2 轮一节仅作参考。范围严格限定在本轮返修，不重审前两轮已通过的内容。全程未运行真实提供方、未读取或打印密钥、未联网、未用浏览器；证据目录 `aborted-run1/` 只读；`expA`/`expB` 两个真跑目录未读未写、未动任何进程；仓库内只写了本文件。临时文件都在 scratchpad 的 `review3-*` 下。

## 结论：通过

- R2-1~R2-4 四条全部落实，每条都有代码行号 + 步骤文件里的真实消息为证。
- 关键证据：用 `aborted-run1/expB/arm-panel/ch001/05-review-reviewer-r2.json` 的 `raw_response` 和该步骤自己 payload 里的 `body`（去空白 2382 字）离线回放 `validate_review`：**新代码 `passed=True，保留 0 条，丢弃 1 条，drop_reason=字段不完整或类型错误`，不抛错；用返修前快照代码做正控，同一输入抛 `ValidationError`（6 条缺字段/类型错误）**。顶层结构错误（`[]`、`{}`、`{"issues": "x"}` 等 12 种）仍抛错。
- 测试纪律：既有 13 个测试文件中只改了 2 个，共 3 处，每处只在写手 payload 期望键集合里新增 `length_range`，其余逐字节相同。
- 6 个变异（R2-1/R2-2×2/R2-3×2/R2-4）全部让对应测试变红；`tests/test_novel_*.py` 709 通过 = 518 + 191（4+72+70+45，与报告一致）；三个 dry-run 退出 0；`git status --porcelain` 无 `M`。
- 没有发现会让真跑白花钱的新问题；有一条「审校被整体丢弃时不可见」的可优化项，不阻断。

## 复核方法

- 与返修前快照 `scratchpad/snap-r2/` 逐文件 `diff`：`novel/` 改了 agent_pool.py、llm_router.py、schemas.py、writing.py、README.md，新增 prompt_rules.py；测试改了 test_novel_r1_workflow.py、test_novel_r1_pilot_report.py，新增 4 个 r2 测试文件。
- `PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider tests/test_novel_*.py` → `709 passed in 2.55s`（日志 `scratchpad/review3-out/tests.log`）。
- 三个 dry-run 复跑到 `scratchpad/review3-{A,B,C}`，退出码均 0（`review3-out/dry{A,B,C}.log`）。
- 离线回放脚本 `scratchpad/review3-replay.py`，分别以当前代码和快照代码运行（`review3-out/replay-new.log` / `replay-old.log`）。
- 默认 dry-run 的 fake 不会触发复审和长度重写，所以另写 `scratchpad/review3-scripted.py` 用脚本化 fake 走完整 `run_experiment`（B 配置、1 章、1500 字）：第一稿故意超长、第一次审校故意返回带英文双引号的坏 JSON、首轮审校返回 1 条阻断、复审返回空，从而拿到含 `length_instruction`、修正消息、`previous_blocking_issues` 的**真实步骤文件**（`review3-scripted/arm-panel/ch001/`，日志 `review3-out/scripted.log`）。
- 扫描三个 dry-run 全部 185 个步骤文件的 system 消息（`review3-out/prompt-scan.log`）：JSON 角色 175 个都恰好含 1 次引号规则且倒数第二行是它、最后一行是防注入句；写手 19 个都不含引号规则；没有任何步骤出现修正轮。
- 变异测试：把 `novel/` 和测试复制到 `scratchpad/review3-mut/`，先跑正控（709 通过），再按变异各复制一份、断言目标字符串恰好出现一次后改坏，跑全部 novel 测试（`review3-out/mut-M*.log`）。

## R2-1~R2-4 逐条核验

| 条款 | 判定 | 证据 |
|---|---|---|
| **R2-1** JSON 字符串禁英文双引号，常量复用，修正消息追加 | 已落实 | 常量 `novel/prompt_rules.py:4`，原文与返修单一字不差。六份 schema 末尾拼接：`agent_pool.py:26`（setup）、`:39`（proposal/critique 共用 PROPOSAL_SCHEMA）、`:54`（decision）、`:69`（review）、`:80`（archive）、`:84`（corrupter）。修正消息：`llm_router.py:339-341` `_append_repair` 在 `output=="json"` 时把规则追加到 `修正要求` 末尾，三条修正路径（截断 `:303`、解析/校验 `:331`）都走它；写手 markdown 不追加。**真实消息**：脚本化运行 `05-review-reviewer-r0.json`（attempts=2，角色序列 system/user/assistant/user）最后一条 user 消息为 `{"校验错误": ["JSON 解析失败，请返回一个合法的 JSON 对象"], "修正要求": "请根据上述错误重新输出完整结果，保持原输出格式。\nJSON 字符串值内部不得出现英文双引号 "；需要引用原文、人物台词或圣经内容时，一律使用中文直角引号「」。"}`。dry-run B `05-review-reviewer-r0.json` system 消息末两行为引号规则 + 防注入句（prompt-scan.log 原文）。测试 `test_novel_r2_prompts.py:36-56`、`:105-131`、`:135-157`。 |
| **R2-2** 残缺 issue 只丢弃，顶层结构错误仍失败，只用于审校 | 已落实 | `schemas.py:348-383`：顶层 `c.obj(...,("issues",))` + `c.array(issues)` 后立即 `c.finish(data)`（`:356`）→ 顶层非对象、缺 issues、issues 非列表仍抛 `ValidationError`；每条 issue 用独立 `issue_check=_Check()`（`:361`），缺字段/类型/枚举错误时取原始条目深拷贝、写 `drop_reason="字段不完整或类型错误"` 进 `dropped_issues`（`:367-371`），不抛错；非对象条目包成 `{"issue": 原值}`；`passed` 只看保留条目（`:383`）。其他 validator（`:229/:246/:270/:345/:431/:473`）仍是整体 `c.finish`，未扩散。**离线回放**（上文）：aborted-run1 真实 raw_response → 新代码不抛错、该 issue 被丢弃、该轮 passed；快照代码抛错（正控）。测试 `test_novel_r2_schemas.py` 70 条含真跑形状 `:81-91` 与顶层失败 `:69-78`；端到端 `test_novel_r2_integration.py:52-62`（attempts=1、无修正轮、manifest completed）。 |
| **R2-3** 收紧阻断标准；复审带 `previous_blocking_issues`，首轮与实验 C 不带 | 已落实 | 提示词 `agent_pool.py:62-69`：三类可阻断、同义/中阿数字/详略不算、knows 只认「明确写出不可能知道的事」、拿不准 false、每轮最多 3 条按严重度排序、复审先逐条判断上一轮问题。dry-run B 审校步骤文件的 system 消息末 11 行与之逐字一致（prompt-scan.log）。流程 `writing.py:100-104`：仅 `revision >= 1` 时 `review_payload["previous_blocking_issues"] = deepcopy(blocking_issues)`，其中 `blocking_issues` 是上一轮**保留下来**的阻断条目（`:108`，丢弃的不在内）。实验 C `pilot.py:204` 审校 payload 固定 `review_round: 0`、无该字段。**真实消息**：脚本化运行 `05-review-reviewer-r0.json` 键 = `beat_sheet, bible, body, chapter, review_round, task`；`05-review-reviewer-r1.json` 键多出 `previous_blocking_issues`，值 `[{"blocking": true, "category": "continuity", "evidence": "乙乙乙乙乙乙乙", "fix": "修", "problem": "阻断示例"}]`；chapter_record `review_rounds=2, revision_rounds=1, flags=[]`。dry-run A/B 全部 19 个 r0 审校步骤无该字段；dry-run C 的 4 个审校步骤（`control/reviewer-0{1,2}/{original,contaminated}.json`）键集合均为六键、无该字段。测试 `test_novel_r2_writing.py:159-240`、`test_novel_r2_integration.py:65-90`、`:121-136`、`test_novel_r2_prompts.py:80-100`。 |
| **R2-4** 写手拿到具体字数范围；长度重写提示带实测字数 | 已落实 | `writing.py:58-59` `length_range={"min": (3W+4)//5, "max": 8W//5, "target": W}`（整数 ceil/floor，无浮点）；payload 键 `:90`；接受判定与最终标记共用同一区间（`:96`、`:119`）。系统提示 `agent_pool.py:14` 模板，`get_agent` `:155-158` 代入同一公式。长度重写 `:79-86`：`上一稿 {compact_length(body)} 字，{超出|不足}范围 {min}–{max} 字；请重写完整正文，目标 {W} 字，宁可略短，不要超过上限。`。**数值核对**：dry-run B（W=1500）写手 payload `length_range={'min': 900, 'max': 2400, 'target': 1500}`，system 消息「正文（不计空白）目标 1500 字，必须在 900–2400 字之间；宁可略短，不要超过上限。」；dry-run A（W=2000）`{'min': 1200, 'max': 3200, 'target': 2000}`，system「目标 2000 字，必须在 1200–3200 字之间」（steps.log）。**实测字数**：脚本化运行第一稿 2500 个「甲」+ 标题行，`04-write-writer-r0-a1.json` 的 `length_instruction` = `上一稿 2509 字，超出范围 900–2400 字；请重写完整正文，目标 1500 字，宁可略短，不要超过上限。`，与 `compact_length(previous_draft)=2509` 一致。测试 `test_novel_r2_writing.py:81-150`、`test_novel_r2_prompts.py:59-77`（含 1500→900/2400、2000→1200/3200）、`test_novel_r2_integration.py:93-118`。 |

## 测试纪律核对

- 快照 13 个既有测试文件 vs 当前：11 个逐字节相同；`test_novel_r1_workflow.py` 改 2 处（`:94-95`、`:112-113`）、`test_novel_r1_pilot_report.py` 改 1 处（`:56-57`），三处 diff 都只是在写手 payload 期望键集合末尾加 `"length_range"`，输入与其他断言未动。
- `test_writer_receives_scoped_complete_context_without_full_bible`（`test_novel_workflow.py`）本来就没有精确键集合断言，未改动，符合「其他断言不变」。
- 审校 payload 的既有精确键集合（r1_workflow `:114`）仍是六键：因默认 dry-run 从不进入复审，这条测试只看得到 r0，与 R2-3 不冲突；复审键集合由新测试覆盖。
- 新增 191 条（r2_prompts 72、r2_schemas 70、r2_writing 45、r2_integration 4），全部离线：monkeypatch 封死两家 SDK 构造与 socket connect，或直接 `_single_real_call` 抛错。

## 变异验证

| 变异 | 改法 | 结果 |
|---|---|---|
| M1（R2-2） | `schemas.py` 残缺 issue 改回 `raise ValidationError(issue_check.errors)` | 56 条变红（r2_schemas 全部丢弃类用例 + r2_integration 真跑形状） |
| M2（R2-2） | 删掉顶层 `c.finish(data)` | 13 条变红（`test_review_invalid_top_structure_still_fails` 12 参数 + 既有 `test_invalid_root_raises_validation_error[validate_review]`） |
| M3（R2-3） | `writing.py` `revision >= 1` → `>= 0`（首轮也带） | 5 条变红（r2_writing 2、r2_integration 1、既有 r1 审校键集合 2） |
| M4（R2-3） | `pilot.py` 实验 C 审校 payload 加 `previous_blocking_issues: []` | 2 条变红（`test_experiment_c_stays_single_pass_without_previous_blockers` + 既有 r1 C 用例） |
| M5（R2-4） | `length_range.min` 由 ceil 改 floor | 21 条变红（非 5 倍数的 W 全部命中） |
| M6（R2-1） | `_append_repair` 不再追加引号规则 | 21 条变红（7 任务 × schema/truncation 修正） |

每个变异前都断言目标字符串在副本中恰好出现一次；正控 709 通过。

## 阻断问题

无。

## 真跑风险核对（只列真实的）

- 本轮改动对单次调用的 token 影响只有 system 提示多约 50~400 字，可忽略；重试次数上限没变（JSON/截断修正仍只 1 次，长度重写 1 次，审校修订 2 轮）。
- R2-2 把「残缺 issue」从「整步失败 → 修正重试 → step_failed 退出」改成「静默丢弃、该轮通过」，这是返修单要求的口径，确实消除了 aborted-run1 那种白花钱的退出；代价是若某个审校模型**每条**都残缺，B 的审校臂会无声地退化成「零阻断、零修订」，实验结论会被污染但不会多花钱。见可优化项。
- 引号规则只是提示，qwen 是否遵守要靠真跑验证；但即使不遵守，现在的后果也只是该条 issue 被丢弃，不会再 step_failed。

## 可优化项（不阻断）

1. **审校整体被丢弃不可见**：`report.py` 没有任何 `dropped_issues` 的统计（grep 0 命中），作者在报告里看不到「一轮审校 N 条里 M 条因格式被丢」。建议在章节记录或过程报告里加一列「因格式丢弃 / 因证据丢弃」的条数，或当某轮保留 0 条、丢弃 ≥1 条时给章节打一个 `review_degraded` 之类的标记，让真跑结束后能一眼判断审校臂是否失效。
2. 「每轮最多 3 条阻断问题」只在提示里，没有代码截断；若模型给 5 条阻断，写手会一次收到 5 条。按返修单口径属于提示词范畴，记录即可，不要求本轮改。
3. 复审 `previous_blocking_issues` 深拷贝的是保留条目，包含模型可能附带的额外字段（如本轮测试里的 `details`），会原样回传给模型；无害，但若想省 token 可只回传 `category/problem/evidence/fix` 四键。
