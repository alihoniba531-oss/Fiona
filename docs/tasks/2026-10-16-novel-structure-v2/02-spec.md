# 小说工坊推演结构 v2：类型承诺、卷规划、主线均衡与审校收敛

> - **任务等级**：L3，修改推演引擎和数据结构。规格经作者确认后才派给实施方。
> - **工作目录**：Fiona 仓库工作树 `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-novel-p0`，分支 `novel-structure-v2`，基于 main `85888d5`。下文路径均相对于仓库根目录。
> - **分期**：本单只做**第一期（后端引擎 + 对比实验所需能力）**。前端（立项卡里编辑类型承诺、卷规划关卡界面）放到第二期，等对比实验证明 v2 有效后再做。

## 0. 背景：为什么要改

作者用一个修仙思路写了 20 章（《凡骨登天》），原思路是：

> 现代都市玄幻修仙。普通家庭出身的主角加入宗门，资质一般被人看不起，靠机缘一路变成最强。

写出来的却是都市悬疑。推演记录给出的证据：

- **成长爽线推进得最少。** 20 章细纲里「修炼 / 灵力 / 突破」出现 0 次，「锁」单章最多出现 36 次。四条主线中，T1 成长爽线只推进过 7 次，第 8 章以后基本停滞；T3 悬疑、T4 家人线各推进 18 次。
- **顾问的意见在压制爽点。** critique 模式下，顾问的意见全是「太快 / 太巧 / 不合理」，主编几乎全部采纳，例如第 2、3 章否掉了主角施法，第 6 章删掉了打脸。主角始终不能变强。
- **没人把故事拉回主线。** 每章章末都新留一个谜团，读者代表总是追着上一章的悬念走。第 17–20 章，顾问已经连续指出「敲锁博弈在原地打转」，但没有任何角色把故事拉回主线。
- **伏笔越积越多。** 埋了 40 条，只回收 4 条。
- **审校收敛不了。** 20 章里有 16 章被标为「审校两轮未通过」。写手的修订平均保留了 87% 的原文，问题也都改了；但审校每轮最多只报 3 条阻断问题，复审时又在没改的地方挑出新问题。

**结构性根因**：

1. 所有角色只会做减法，没有角色守「类型承诺」。
2. 只有章级的会议，没有中间层的阶段规划，故事顺着悬念漂移。
3. 「每章至少推进一条主线」这条规则不要求均衡。
4. 伏笔只进不出。
5. 审校每轮限 3 条，复审又不限定范围。

## 1. 已定决策（作者在派单前可以改）

| 编号 | 决策 |
|---|---|
| D1 | 每卷 10 章。在第 1、11、21……章的推演之前，先开「卷会议」。 |
| D2 | 卷规划要经作者批准。自动化方式为每批或每章时，卷会议结束后停在新状态 `awaiting_volume`。全自动方式不停。（第一期只做后端接口，界面放到第二期。） |
| D3 | 类型爽点的节奏：默认每 3 章至少 1 个类型爽点。数值写在类型承诺里，作者在立项时可以改，范围 1–5。 |
| D4 | 核心主线（类型承诺里指定，修仙文通常是成长线）每 3 章至少推进 1 次，这是硬规则；其他主线连续 5 章没推进时，只给红灯提示。 |
| D5 | 伏笔预算：每章新埋不超过 2 条。未回收伏笔超过 20 条时，本章新埋的条数不得多于本章回收的条数。 |
| D6 | 新建的书默认使用 v2。已有的书（包括《凡骨登天》）保持 v1 不变，但提供一个「升级到 v2」的后端接口，见 T6。 |
| D7 | 审校收敛的改动（T5）对所有 P1 书生效，包括 v1 书。P0 离线 pilot 不变。 |
| D8 | 对比实验：用作者这本书的同一个思路，v1 和 v2 各写 10 章。只用平台模型，预算约 ¥50，上限 ¥70。开跑前另行报价，经作者同意后执行，不在本单的实施范围内。 |

## 2. 修改范围与不变量

**可以修改**：

- `backend/novel/` 下的 `schemas.py`、`context.py`、`deliberation.py`、`writing.py`、`agent_pool.py`、`runner.py`、`service.py`、`bible.py`；
- `fake_llm.py`：只为离线测试产出新字段时才改；
- `backend/routers/novel.py`：新增路由；
- 新增测试 `backend/tests/test_novel_v2_*.py`；
- 文档：`CLAUDE.md` 中小说工坊一节、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`，以及本目录下的 `03-report.md`。

**必须保持不变**：

- **短片工作室依赖的接口**：
  - `service.py` 中 `list_books`、`detail`、`bible`、`chapter`、`owned` 的签名，以及它们已有返回字段的含义（只许新增字段）；
  - `novel_chapters` 表的列；
  - 圣经里已有键的结构，包括 `locked.characters[].appearance`、`dynamic.chapter_summaries`、`arc_summaries`、`character_states`（只许新增键）；
  - `completed`、`done`、`stale` 的语义。
- **P0 离线 pilot**：A/B/C 实验的步骤键、payload、流程逐字节不变。
- **v1 书**：没有 `structure` 键的书，除 T5 之外的行为、payload 和步骤键都不变。
- **计费**：草莓计费的口径和原子性不变。
- **已有测试**：输入和断言一律不改。
- **依赖**：不改 `package.json` 和 lockfile；本期不改前端。

## 3. 任务清单

### T1 结构开关

1. `CreateNovel` 新增字段 `structure: Literal['v1','v2'] = 'v2'`，写入 `config_json`。
2. 旧书没有这个键，一律按 v1 处理。
3. 下文 T2–T4、T6 的所有新行为，只在 `config.get('structure') == 'v2'` 时生效。

### T2 类型承诺（genre_contract）

1. **立项输出新增字段**。v2 书立项时，`validate_setup` 额外要求 `genre_contract` 字段，结构如下：

   ```json
   {
     "genre": "修仙升级",
     "reader_promise": "一句话：这类读者追这本书是为了什么",
     "core_thread": "T1",
     "core_payoffs": ["修为突破", "越级取胜", "当众打脸", "获得机缘或宝物", "宗门比试排名"],
     "payoff_every_chapters": 3,
     "progression_ladder": ["凡人", "练气一层", "练气圆满", "筑基", "……"],
     "drift_warnings": ["连续多章只做悬疑推理而主角没有成长"]
   }
   ```

   校验规则：

   | 字段 | 要求 |
   |---|---|
   | `genre`、`reader_promise` | 非空 |
   | `core_thread` | 必须是 `main_threads` 里的某个 ID |
   | `core_payoffs` | 3–8 条，每条非空 |
   | `payoff_every_chapters` | 整数，1–5 |
   | `progression_ladder` | 3–12 条 |
   | `drift_warnings` | 0–5 条 |

   `genre_contract` 存进 `compass_json`。
2. **主编立项提示词**：明确要求主编从作者的思路里提炼类型承诺。思路里写了「一路变强、最强」之类的意思时，`core_thread` 必须指向成长线。
3. **立项确认**：`setup/approve` 允许作者修改 `genre_contract`。可修改的字段：`genre`、`reader_promise`、`core_payoffs`、`payoff_every_chapters`、`progression_ladder`、`drift_warnings`。`core_thread` 的 ID 不能改成不存在的主线。

### T3 卷会议与卷规划

1. **触发时机**：v2 书在第 `10k+1` 章（k≥0）开章级推演之前，先开卷会议。卷的范围是 `[10k+1, min(10k+10, max_chapters)]`。
2. **会议流程**（固定步骤，不自由对话）：
   1. 主编出卷规划初案；
   2. 节奏与完结顾问、读者代表各提意见，复用 critique 的意见结构；某一位未入选时就跳过他；
   3. 主编定稿。

   步骤键：

   ```
   arm-{arm}/vol{k+1:02d}/01-volume-plan-editor.json
   arm-{arm}/vol{k+1:02d}/02-volume-critique-{role}.json
   arm-{arm}/vol{k+1:02d}/03-volume-finalize-editor.json
   ```

   每一步都按现有规则计费。
3. **卷规划结构**：

   ```json
   {
     "volume": 1,
     "chapters": [1, 10],
     "goal": "本卷要完成的阶段目标",
     "milestones": [
       {"id": "M1", "thread": "T1", "description": "林砚舟正式开始修炼，并完成第一次突破", "due_chapter": 6}
     ],
     "payoff_plan": [
       {"chapter_hint": 3, "type": "当众打脸"}
     ],
     "threads_focus": ["T1", "T3"],
     "foreshadowing_to_resolve": ["F003"],
     "new_mystery_budget": 4
   }
   ```

   校验规则：

   - `milestones` 有 2–5 条，其中至少 1 条属于 `core_thread`；
   - 每条 `due_chapter` 都在本卷范围内；
   - `payoff_plan` 的条数不少于 `ceil(本卷章数 / payoff_every_chapters)`；
   - `foreshadowing_to_resolve` 只能引用 open 状态的伏笔；
   - `new_mystery_budget` 为 0–6。
4. **存储**：卷规划写进圣经 `dynamic.volumes[]`，这是新增的键。写入时新建一个圣经版本，`source='volume:{n}'`。每条里程碑带 `status`，取值为 `open`、`done` 或 `missed`。
5. **关卡**：自动化方式为每批或每章时，卷会议定稿后，书进入新状态 `awaiting_volume`。新增三个接口：

   | 接口 | 行为 |
   |---|---|
   | `POST /novels/{id}/volume/approve` | 请求体可以带修改后的卷规划，规则与 `plan/approve` 相同 |
   | `POST /novels/{id}/volume/redo` | 附一句话重新规划，会计费 |
   | `GET /novels/{id}/volumes` | 返回全部卷规划及里程碑状态 |

   全自动方式不停，直接继续。`awaiting_volume` 的计费、暂停和恢复规则与 `awaiting_plan` 相同。

### T4 章级推演：均衡、爽点与伏笔预算（只对 v2 书生效）

1. **简报新增内容**（`build_brief`）：
   - `genre_contract`；
   - 当前卷规划，以及各里程碑的状态和到期章；
   - `payoff_history`：最近 `payoff_every_chapters × 2` 章的爽点记录；
   - `thread_staleness`：每条主线距上次推进过了几章；
   - 未回收伏笔数和上限；
   - `red_flags`：中文短句列表。例如「核心主线 T1 已 3 章未推进，本章必须推进」「本章必须安排类型爽点」「里程碑 M1 到期」「未回收伏笔 22 条，已超上限，新埋不得多于回收」。
2. **细纲新增两个字段**（v2 的 `validate_decision`）：

   ```
   genre_payoff: {"type": core_payoffs 中的一项, "beat_index": 节拍序号} 或 null
   milestones_advanced: 本卷里程碑 ID 的列表，可以为空
   ```

3. **代码硬校验**：不合格时判 `decision_invalid`，主编按现有机制重试。报错要列出具体的规则和数值。
   1. **爽点节奏**：如果最近 `payoff_every_chapters − 1` 章都没有爽点，本章 `genre_payoff` 不得为 null。
   2. **核心主线**：如果核心主线已连续 3 章没出现在 `advances_threads` 里，本章必须包含核心主线。
   3. **里程碑到期**：`due_chapter` 等于本章、且状态仍是 open 的里程碑，必须出现在 `milestones_advanced` 中。
   4. **伏笔预算**：
      - `foreshadowing_plant` 不超过 2 条；
      - 未回收伏笔超过 20 条时，`len(foreshadowing_plant)` 不得多于 `len(foreshadowing_resolve)`；
      - 本卷新埋的总数不得超过 `new_mystery_budget`。
4. **里程碑状态**：章节定稿归档后，档案员的 `archive` 新增可选字段 `milestones_done: [ID]`，只能填本章 `milestones_advanced` 中真正完成的那些，代码据此把里程碑标为 `done`。卷末仍为 open 的里程碑标为 `missed`，写进下一卷简报的 `red_flags`。
5. **角色提示词**（`agent_pool.py`，v2 专用版本；v1 的提示词不动）：
   - **读者代表**：「你代表 genre_contract.genre 这一类型的读者。先检查本章是否兑现了 reader_promise 和类型爽点、主角的成长是否看得见；然后才看上一章留下的悬念。」
   - **节奏与完结顾问**：增加三项检查：卷里程碑进度、主线均衡（引用 `thread_staleness`）、伏笔预算。
   - **所有顾问的爽点保护规则**：「不得仅因『太快 / 太巧 / 太爽』否定 genre_payoff。只有在它与锁定设定或已发生的事实冲突时才能反对，并且要引用该事实；可以建议改成别的方式兑现，但不能建议删除。」
   - **主编定稿规则**：「采纳会删除 genre_payoff 的意见时，必须同时给出替代的爽点。」代码兜底：硬校验 1 仍然生效。

### T5 审校收敛（对所有 P1 书生效，P0 不变）

1. **首轮（r0）**：把审校提示词中的「每轮最多 3 条阻断问题」改为「首轮列出全部阻断问题，最多 8 条，按严重程度排序」。
2. **复审（r1、r2）**：
   - `writing.py` 计算本轮正文相对上一轮的改动段落：用 `difflib` 按段落比对，得到新增或修改的段落集合。
   - 审校 payload 新增 `changed_passages`：改动段落的原文，上限约 3000 字，超出时截断并注明。
   - 提示词要求审校做两件事：(a) 逐条判断 `previous_blocking_issues` 是否已解决；(b) 新发现的问题只有当 evidence 位于 `changed_passages` 中时，才可以判为阻断。
   - **代码兜底**：复审中，evidence 不在任何改动段落内的新问题一律降为 `blocking=false`，并在该问题上标注 `outside_changes=true`。「新问题」指与 `previous_blocking_issues` 不重合的问题，判定依据是 evidence 不同。
3. **细纲措辞不阻断**：`beat_sheet` 类问题只有在「整条节拍或整个场景缺失」时才能阻断；钩子措辞、节拍顺序的细节差异一律不阻断。这条写进提示词。
4. **兼容**：P0 pilot 的审校 payload 和提示词保持不变。如果改动影响冻结的期望（例如 `tests/test_novel_r2_prompts.py` 中冻结的子串），采用保留原句、在后面追加的方式；仍然冲突时，停下来报告。

### T6 已有书升级到 v2

1. 新增 `POST /novels/{id}/upgrade-structure`，只允许在 `awaiting_review`、`paused` 状态下调用，并复用 `_check_not_editing`。
2. **流程**：
   1. 调用主编一次，任务为 `genre_contract`，依据思路、罗盘、已写章节的摘要，生成类型承诺；
   2. 写入 `compass_json`，并把 `config.structure` 设为 `v2`；
   3. 下一章开始前开卷会议，卷号按 `ceil(chapters_done / 10) + 1`。如果当前章不在 10 的倍数边界上，本卷就是从下一章到下一个整十章，例如第 21–30 章。
3. 升级只修改上面这三处，**不改动已写章节和既有圣经内容**。

### T7 测试（`backend/tests/test_novel_v2_*.py`，离线，使用 fake 路由）

- **T1**：默认 v2；旧书没有该键时按 v1；v1 书的 payload 和步骤键与 `85888d5` 逐字节相同（拿真实 `deliberate` 和 `write_chapter` 在两版代码下的输出比对）。
- **T2**：`genre_contract` 校验的每条规则；`core_thread` 必须存在；立项确认时能修改。
- **T3**：
  - 卷会议在第 1、11、21 章触发，且只触发一次（断点续跑不重复）；
  - 步骤键和计费正确；
  - 卷规划的各条校验；
  - `awaiting_volume` 的三个接口和状态流转；
  - 全自动方式不停；
  - 圣经新版本的 `source='volume:n'`。
- **T4**：
  - 四条硬校验各自的正例和反例，报错文本里有具体数值；
  - `red_flags` 的生成；
  - 里程碑的 `done` 和 `missed` 流转；
  - 爽点保护提示词出现在 v2 卡片里，而 v1 卡片不变。
- **T5**：
  - 首轮可以有超过 3 条阻断问题；
  - 复审时改动段落外的新问题被降级，并带 `outside_changes`；
  - 上一轮的问题仍被检查；
  - `changed_passages` 的计算覆盖增、删、改和截断；
  - P0 pilot 的审校 payload 不变。
- **T6**：允许和不允许的状态；升级后下一章先开卷会议；已写章节和圣经已有内容逐字节不变。
- **契约保护**：五个函数的签名不变；`novel_chapters` 的列不变；圣经已有键的结构不变。

## 4. 验收（由验收方复跑）

1. `cd backend && python -m pytest -q` 全量通过，基线为 5252 passed，并且新增的测试都通过。在不含 `frontend/node_modules` 的仓库副本中，新增测试 0 failed。
2. 已有测试的 diff 为空；`git status` 的改动只在 §2 的范围内。
3. 用 fake 路由跑一本 v2 小书：25 章、每卷 10 章、全自动。检查以下几点：
   - 卷会议次数为 3；
   - 每 3 章内至少有 1 个爽点；
   - 核心主线没有连续 3 章空缺；
   - 伏笔预算从未被突破；
   - 账目守恒：`spent = 各步骤实扣之和`，`reserved = 0`。
4. 对比实验另起一单，见 §5。

## 5. 对比实验（本单不实施；第一期验收通过后，由验收方报价，作者同意后执行）

- **环境**：隔离的临时库，真实模型，复用 P1 冒烟测试的方式。
- **两本书**：同一个思路（作者原思路，一字不改），一本 v1、一本 v2，各写 10 章，全自动，只用平台模型：
  - 主编：千问 3.8 Max；
  - 写手、反转设计师：DeepSeek Flash；
  - 人物代言人：豆包；
  - 情节架构师、读者代表、节奏顾问、审校、档案员：千问。
- **机械指标**：
  - 核心主线推进次数；
  - 爽点次数和种类；
  - 里程碑完成率；
  - 未回收伏笔数；
  - 「审校两轮未通过」的章数；
  - 每章费用。
- **作者判断**：两本书的各章摘要并排盲读，再各附 2 章全文，由作者判断「哪本更像修仙升级文、哪本更好看」。
- **费用估算**：参照《凡骨登天》的实测数据，每章约 ¥2.3。两本共 20 章约 ¥46，加上立项和卷会议约 ¥4，**约 ¥50，上限 ¥70**。

## 6. 何时停下来问

- 有冻结的提示词或 payload 期望因 T5 或 T4 的修改而失败，且「保留原句、在后面追加」也解决不了。
- 需要修改 §2「必须保持不变」中的任何一项。
- 卷会议、`awaiting_volume` 与现有的批量关卡或每章关卡同时触发，规格中没有给出先后顺序时，默认卷关卡先于章关卡。如果实现上做不到这一点，停下来报告。
- 其他「怎么实现」类的问题，由实施方自行决定，并在报告中说明。

## 7. 修订 R1（验收方裁定，2026-10-16）

**背景**：实施方按 §6 停下，报告 D6「新书默认 v2」与既有建书测试冲突。验收方复查后认定，这是规格本身的问题，而不只是测试冲突：第一期不改前端，如果新书默认 v2，用户在界面上建的书会停在 `awaiting_volume`，而界面没有这个关卡，书就卡住了。裁定如下，既有测试仍然一律不改：

1. **默认值**：第一期 `CreateNovel.structure` 的默认值改为 `'v1'`。v2 只在请求中显式传 `structure: "v2"` 时生效，供对比实验和测试使用。D6「新书默认 v2」推迟到第二期，与界面一起生效，届时把默认值改为 `'v2'`。
2. **卷关卡**：新增配置键 `volume_gate`，默认 `false`。
   - 为 `false` 时，卷会议定稿后自动批准，不进入 `awaiting_volume`；卷规划照常写入圣经，并可以通过 `GET /novels/{id}/volumes` 查看。
   - 为 `true` 时，按 T3.5 的规则进入 `awaiting_volume`。
   - `CreateNovel` 暂不开放 `volume_gate`，只能由测试或后台直接写入 config。第二期界面就绪后再开放。
   - 三个卷接口照常实现，并用 `volume_gate=true` 的测试覆盖。
3. **T6 升级接口**：升级时写入 `structure='v2'`，**不**打开 `volume_gate`。因此在第一期，升级后的书不会卡在卷关卡上。
4. **§4.3 验收**：fake 路由的 25 章小书显式传 `structure='v2'`。另外补一条测试：不传 `structure` 时按 v1 处理，行为、步骤键和圣经版本号与 85888d5 完全一致。
5. **其余**：T1–T7 的其他内容不变。T5（审校收敛）仍然对所有 P1 书生效，与 structure 无关。如果 T5 与既有测试的断言冲突，按 T5.4 处理：保留原句、在后面追加，仍有冲突就停下报告。

## 8. 修订 R2（验收方裁定，2026-10-16）

**冲突**：`tests/test_novel_p21_writing.py:115` 冻结了「drama 关闭时审校 payload 逐字节不变」。用例里写手两轮的正文相同，此时即使只传 `changed_passages: []`，字节也会变。

**裁定**：采纳实施方的提议。
- 复审时，**正文没有任何改动**（改动段落为空集）的情况下，payload **省略** `changed_passages`，代码内部仍按空集执行 T5.2 的降级：本轮新发现的问题一律设为 `blocking=false`、`outside_changes=true`。
- 正文有改动时，照常传入 `changed_passages`。
- 审校提示词追加：「复审时如果 payload 中没有 changed_passages，表示本轮正文没有改动：只核对 previous_blocking_issues，新问题一律不阻断。」
- 新增测试覆盖三种情况：空改动（字段省略，同时降级生效）、有改动（字段存在）、截断。
- 既有测试一律不改。如果再出现其他冻结冲突，仍按 §6 停下报告。
