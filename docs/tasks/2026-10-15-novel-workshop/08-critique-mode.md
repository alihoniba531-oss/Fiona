# 小说工坊 P0 增补：「主编出方案、顾问挑错」推演模式（实验 A2）

> 背景：实验 A 的盲读结果是作者选了 solo 组，也就是主编独自构思的那一组，panel 组落败。对照推演记录，panel 落败有三个原因：
> - 主编每章都把 2–3 个提案合并，导致事件和道具堆砌；
> - 底牌揭示得太快；
> - 反转设计师的提案平均分只有 2.2–3.1，10 条全部落选，说明均分投票会淘汰大胆的方向。
>
> 作者决定换一种新的推演模式，换一个故事思路，再和 solo 组各写 5 章做盲读对比。
> 本单是对 `02-spec.md` 及已完成各返修单的增量。红线不变：
> - 只改 `backend/novel/**`、`backend/tests/test_novel_*.py`、`03-report.md`。
> - 不联网，不读密钥，不运行真实提供方，不提交 commit。
> - 既有测试的输入和断言不得修改。
> - 测试不得读取仓库以外的任何文件。
> - 不要读写 `/Users/yangjing/Desktop/ai-workspace/outputs/`。

## R5-1 新增推演模式 critique（主编出方案 → 顾问挑错 → 主编定稿）

配置新增字段 `panel_mode`，可取 `"merge" | "critique"`，默认值为 `"merge"`。**现有的 merge 流程、校验和测试一律保持不变**。`panel_mode` 只影响实验 A 的 panel 组和实验 B；solo 组始终是主编独自构思。

critique 模式下每章的固定流程如下：

1. **主编初案**（task=`plan`）
   - 输入：简报，与现有推演会相同。
   - 输出：与现有裁决**完全相同的 JSON 结构**，即 `validate_decision` 的 solo 形态。具体要求：`chosen_proposal_ids` 为空，`objection_responses` 为空，`user_note_responses` 必须回应本章的用户留言。
   - 校验沿用 `validate_decision(..., solo=True, objection_ids=[])`。
   - 步骤文件：`01-plan-editor.json`。
2. **顾问挑错**：除主编外的每个推演智能体并行执行 task=`critique_plan`。
   - 输入：简报，加上主编初案的 `beat_sheet`、`rationale`、`ending_status`。
   - 输出：
     ```json
     {"objections": [{"severity": "major|minor", "target": "针对初案的哪一部分（节拍/场景/伏笔/人物/结尾钩子等）", "problem": "具体问题", "suggestion": "具体改法"}],
      "keep": "初案里最值得保留的一点",
      "alternative": "（仅反转设计师必填）一个与初案方向不同、出人意料但合理的替代走向，80–200 字"}
     ```
   - 校验：
     - `objections` 1–3 条，各字段非空，`severity` 必须是枚举值之一；
     - `keep` 非空；
     - 角色为 `twist_designer` 时，`alternative` 必须非空；其他角色的 `alternative` 允许缺失或为空。
   - 步骤文件：`02-critique-plan-{role}.json`。
   - **不打分，不计算均分。**
3. **主编定稿**（task=`finalize`）
   - 输入：简报、主编初案、全部挑错意见（带作者角色名），以及代码分配的 ID：
     - 每条 objection 分配 `O1…On`，按配置顺序编号；
     - 每条非空的 alternative 分配 `A1…`。
   - 输出：与现有裁决结构相同。`chosen_proposal_ids` 为空；`objection_responses` 必须**恰好回应一次**全部 O* 和 A* 的 ID。对 A* 的回应要明确写出「采纳 / 部分采纳 / 不采纳」以及理由，这一点只在提示词里要求，不做硬校验。
   - 校验沿用 `validate_decision`，参数为 `solo=True`、`objection_ids = O* + A*`。
   - 步骤文件：`03-finalize-editor.json`。
   - 定稿之后的写手、审校、档案员流程完全不变。

**主编在 critique 模式下的提示词要点**（`plan` 和 `finalize` 两张卡片，按 task 返回）：

- `plan`：与现有 decision 卡片的创作准则相同，包括五个维度、`used_beats` 不重复、每章有一个新发现，再加上 R5-4。
- `finalize`：
  - 定稿的依据是「这一章最好的写法」，而不是「让每条意见都满意」。
  - 只吸收能让本章更好的意见，**不要为了照顾意见而把多个方向拼在一起**。
  - 对每条 major 意见，要么改，要么说明不改的理由。
  - 对反转设计师的替代走向必须认真评估：如果它明显更好，可以整体换成它。

**顾问提示词**（`critique_plan`，五个推演角色共用一个 schema，各自保留原有视角清单）：

- 只挑会让本章变差的真问题，不挑措辞。
- 每条意见都要给出可执行的改法。
- 不要另起一个完整方案；反转设计师的 `alternative` 是唯一例外。

**简报、推演会记录与报告**：

- `chapter_record.json` 的 `meeting` 记录 `mode`、`plan`、`critiques`、`objections`（含 A*）和 `decision`。
- `report.md` 的推演摘要按 critique 模式展示以下内容：初案要点、各条意见及其严重度、替代走向、主编对每条意见的回应、定稿相对初案的改动。改动可以是简单的字段差异，例如章名、节拍、钩子是否变化。

## R5-2 审校漏掉 `blocking` 字段时按非阻断保留，不再丢弃（schemas.py、report.py）

- `validate_review` 中，单条 issue **只缺 `blocking` 字段**（或该字段为 null）、其余字段都合法时，按 `blocking=false` 保留，并在该 issue 上标记 `blocking_defaulted: true`。缺少其他字段的 issue 仍然丢弃，保持 R2-2 的处理方式。
- 某一轮审校的**全部** issue 都被丢弃、且被丢弃的条数不少于 1 时，给本章加上标记 `review_degraded`。
- `report.md` 的每章摘要里列出两项数字：被丢弃的 issue 条数，以及 `blocking_defaulted` 的条数。
- 补测试：只缺 `blocking` 时保留为非阻断；全部丢弃时加上 `review_degraded` 标记；缺少其他字段时仍然丢弃（正控）。

## R5-3 写手标题识别中文数字，并去掉重复标题（writing.py）

- `normalize_manuscript` 识别章节首行时，章号同时接受阿拉伯数字和中文数字：「第二章」「第十二章」等价于 n=2 和 n=12。规范化后统一写成 `# 第{n}章 {title}`。
- 规范首行之后，如果紧接着（只隔空行）又出现一行章节标题，并且去掉「第X章」之后与规范标题相同，就删除这一行。只删这一行，不改正文其他任何内容。
- 补测试：
  - 「# 第二章 同源的跳板」被识别为第 2 章；
  - 「# 第2章 X」后面紧跟「# 第二章 X」时，只保留一个标题；
  - 章号不一致时（例如本章是第 3 章，正文首行却是「第二章」），按「首行不是本章标题」处理，在正文前插入规范首行，原有那行保留。

## R5-4 主编准则：每章最多一个关键揭示（agent_pool.py）

- 在主编的 decision、plan、finalize 三张卡片中都加入：「每章最多安排一个关键揭示（主线谜底或核心身份的实质推进）；其余新发现只能是线索层面的。」
- solo 组和 critique 组使用同一句话。
- 只改提示词，不加任何硬校验。

## R5-5 新实验配置 `pilot_configs/expA2.json`（新增文件）

- `"experiment": "A"`，`"panel_mode": "critique"`。
- `arms` 与 expA 相同：
  - `solo` 只有 `["editor"]`；
  - `panel` 为 `["plot_architect", "character_advocate", "twist_designer", "editor"]`。
- `chapters_per_arm` 为 5，`user_notes` 为 `{}`。
- `target` 为 50–70 章，每章 2000 字；`adaptation` 与 expA 相同。
- `agents`：
  - editor：`anthropic:claude-sonnet-5-5`
  - plot_architect：`dashscope:qwen3.8-max`
  - character_advocate：`ark:doubao-seed-2-1-pro-260915`
  - twist_designer：`anthropic:claude-haiku-5-5`
  - writer：`deepseek:deepseek-flash`
  - reviewer：`dashscope:qwen3.8-max`
  - archivist：`dashscope:qwen3.8-max`
- `seed_idea`（新思路，原文照抄）：「一个在殡仪馆做遗容化妆的年轻女人，某天推进来的遗体，是一张和她一模一样的脸——可她从小被告知自己是独生女。随后她发现，死者身上的旧伤疤，和她母亲多年来闭口不提的那场火灾，对得上。基调：家庭悬疑加情感，克制细腻，每章揭开一层家族秘密。」
- 盲读文件生成方式不变（仍按 solo / panel 两组随机分配甲乙）。

## 测试（全部离线）

1. critique 模式 dry-run 走完整个实验 A2：
   - panel 组每章依次产生 `01-plan-editor`、3 个 `02-critique-plan-*`、`03-finalize-editor` 步骤文件，**不产生** proposal 和打分步骤；
   - solo 组与原来一样。
2. 定稿时漏回应任意一条 O* 或 A*，判失败；重复回应，也判失败。
3. 反转设计师缺少 `alternative` 时校验失败；其他角色缺少 `alternative` 时校验通过。
4. 默认 `panel_mode`（merge）下，实验 A 和 B 的步骤文件名及推演会结构与改动前一致（用离线 dry-run 比较步骤键集合）。
5. 两组的写手 payload 键集合仍然完全相同。
6. 规则（R5-4 那句话）**逐字**出现在 solo 组 decision 和 critique 组 plan、finalize 的系统提示中。
7. R5-2、R5-3 中列出的各条测试。

## 验收

1. `tests/test_novel_*.py` 全部通过，全量测试没有新增失败。
2. 四份配置（expA、expB、expC、expA2）的 dry-run 都以退出码 0 结束，其中 expC 使用 `--source-run` 指向 expA 的 dry-run 结果。
3. 运行 `git status --porcelain`，没有 M 状态的文件。
4. expA2 的 dry-run 估算表贴进 03-report.md，放在「critique 模式」一节。
