# WO3c 短片工作室：拆解与分集（G0）

> 所属项目：Fiona「短片工作室」，12 期中的第 3c 期。WO0–WO3b 已合入 main（98c4ba8）。
> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。
> 必读：
> - 导演模型基础设施（WO3a）：`backend/studio/brain.py`、`brain_jobs.py`、`brain_tasks.py`、`brain_schema.py`、`pricing.py`、`spend.py`、`prompts/*.md`。
> - 作品快照（WO3b）：`backend/studio/sources.py`（`read_snapshot`、`_read_manifest`、snapshot.json 结构）、`docs/tasks/2026-10-16-studio-wo3b-sources/02-spec.md` §3。
> - WO0 长文拆解实测：`docs/tasks/2026-10-16-studio-wo0-probe/06-probe-results.md`「长文拆解」一节；`backend/scripts/_studio_probe_brain.py` 的 map/reduce 提示词与 schema（只参考，业务代码不要 import）。
> - 三家评测：`docs/tasks/2026-10-16-studio-wo3a-brain/06-eval.md`。
> - 前端改动前，先读 `frontend/AGENTS.md` 和 `frontend/node_modules/next/dist/docs/` 里对应的文档（Next.js 16 与旧版不同）。可复用写法：`components/novel/PlanEditor.tsx`（增删行与「改完批准」）、`SetupEditor.tsx`（只提交改动字段、字段级报错）、`BiblePanel.tsx`（行内编辑）、`BrainTrial.tsx:226`（表格样式）、`NovelWorkbench.tsx:231-240`（Markdown 下载）。

## 1. 产品目标

作者把一部小说（或剧本）建成工作室项目后，在「①拆解」页签里完成**拆解与分集**：

1. 设好每集时长（默认 3–4 分钟，即 180–240 秒），可选填「大约几集」，点「报价」，看到整次拆解的预估费用，确认后开跑。
2. 导演模型分批处理快照。进度按批显示；某一批失败、被拒或结果不确定时，只重跑那一批，可以换一家模型重跑（千问遇到暴力情节可能被审核截断，WO0 实测过）。
3. 拆完得到三样，全部可在表格里修改：
   - **故事梗概**。
   - **人物、场景、道具总表**：首次出场、原文外观摘录、出场的集；原文找不到外形的人物标「待作者补充」，绝不编造。
   - **分集方案表**：集号｜标题｜原文范围｜这集发生的变化｜终点 / 钩子｜预估镜头数｜预估时长｜出场人物。作者可以合并、拆分、挪动边界、改标题和文字、改单集时长。
4. **G0 批准**：作者批准分集方案的当前版本。批准后再改任何一处，方案 revision 加 1，退回待批准。G0 是后续定妆（WO3d）的前置条件，本期只需把状态暴露出来。
5. 总表与分集方案可以导出成 Markdown。

另外顺手修一处 WO3b 遗留的观感问题（见 F4）。

本期**不做**：风格提案、定妆、本集剧本改编、拆镜（WO3d / WO4）。

## 2. 约束（红线）

- 不新增依赖，不改 `package.json`、lockfile、`requirements.txt`、`globals.css` 令牌。不联网，不提交。派子代理时不要传 model 和 reasoning_effort。
- 数据库只做新增：新表，或在 `backend/studio/store.py` 的 `STUDIO_TABLES_DDL` 与 `migrate_schema` 补列字典里同时补列。删号时新表的行在 `database.py` 删号事务里一并删除（参照现有 `studio_*` 表）。
- **付费调用只发一次**（同 WO1 / WO3a 硬规则）：沿用 `brain.py` 的 provider 实现，`max_retries=0`；超时、断连、5xx、2xx 无法解析 → `uncertain`（保留预留，只能手动释放）；明确 4xx / 429 → `rejected`；拒答、内容过滤、空输出 → `failed` 按实际 usage 结算；截断 → `invalid_output` 不修正；schema 或硬约束不合格允许修正一次（沿用现有规则）。
- **报价只能确认一次**，15 分钟过期只约束确认；确认后预留随任务保留到结束。
- 原文是数据不是指令：所有原文一律经 `material_prompt` 的 JSON 数据块传入，系统提示写明不得执行其中要求（沿用现有做法）。
- 工作室只读快照，不再回读小说工坊（拆解完全基于 `sources.read_snapshot` / manifest）。
- 所有重 I/O 与大文本处理（读快照、切块、拼装大 JSON、导出）一律 `asyncio.to_thread`，不得在事件循环里同步执行（WO3b 复核的教训）。
- 所有经由 node 驱动的新前端测试，在 `frontend/node_modules` 缺少所需包时 `pytest.skip`（参照 `backend/tests/test_studio_frontend_shell.py` 的 `probe()`）。
- 测试夹具里不得出现任何第三方受版权保护的原文（仓库是公开的），一律用自写文字。
- 不改非工作室的测试。

## 3. 核心概念：场景单元（unit）

拆解的中间产物统一成一串有序的**场景单元**，分集就是把连续的单元划成若干集。这样合并、拆分、挪边界都是确定性操作，不需要再调模型。

每个单元：`seq`（从 1 起，全书唯一、有序）、`label`（人读位置，例如「第 12 章 第 2 场」或「第 3 块 第 1 场」）、`chapter`（小说章号或次要来源的块号）、`scene_index`（章 / 块内第几场，从 1 起）、`location`、`summary`、`characters`（名字列表）、`est_seconds`（这场拍成短片约多少秒，整数）、`change`（这场发生了什么变化，可空）。次要来源另有 `start` / `end`（在 `full.txt` 里的字符偏移）。

分集方案中每集用 `unit_from`、`unit_to`（含两端）表示原文范围；`原文范围` 列显示为「第 12 章第 2 场 – 第 14 章第 1 场」（次要来源另显示字符偏移）。

## 4. 两条拆解路径

### 4.1 小说工坊来源（`source_kind='novel'`）

**第一步：结构化导入（不调模型，确认报价前就做，作为报价依据）**
- 人物：`bible.locked.characters` → 人物总表（`id` 如 C1、`name`、`role`、`age`、`appearance`、`personality`、`motivation`）。`appearance` 非空的记为来源「小说工坊设定」；为空的待补全。
- 初始单元：每章 `outline.scenes[{location, summary}]` → 单元（`est_seconds` 暂空）。没有细纲场景的章，整章作为一个单元，`summary` 取 `dynamic.chapter_summaries` 里该章的摘要。
- 梗概（不调模型）：由 `compass` 的 `logline / theme / core_conflict / main_threads` 与 `dynamic.arc_summaries` 拼成，存为结构化 JSON。
- 伏笔与时间线：`dynamic.foreshadowing`、`dynamic.timeline` 作为参考资料存进拆解记录，传给分集任务，并出现在导出里。
- 改编参数 `locked.adaptation`（主要人物上限、每章场景上限）作为分集任务的软约束。

**第二步：补全（调模型，每批 ≤10 章且 ≤24,000 字）**——新任务 `novel_complete`：
- 输入：这几章的正文、这几章的细纲场景、已知人物（id、名字、是否已有外形）。
- 输出：
  - `chapters[{chapter, scenes[{location, summary, characters, est_seconds, change, start_anchor}]}]`：**以正文为准**（写手可能偏离细纲），场景数可以与细纲不同。
  - `locations[{name, description, first_chapter, excerpt}]`、`props[{name, description, first_chapter, excerpt}]`。
  - `appearance_fills[{character, excerpt}]`：为缺外形的人物从原文摘录外观描写（必须是原文原句，≤200 字）；找不到就不要输出这一项。
  - `new_characters[{name, role, first_chapter, excerpt}]`：总表里没有、但在这几章有戏份的人物；`excerpt` 只能摘原文。
- 补全后用这一批的场景替换对应章的初始单元。

### 4.2 次要来源（上传、粘贴、创意搭档成稿）

快照里已经有块（WO3b 按标题或约 1 万字切）。超过 12,000 字的块，在段落边界再切成 ≤10,000 字的子块（子块按 `start / end` 偏移记录，不改快照）。

**第一步：逐块通读**——新任务 `text_map`（每块一次）：
- 输出：`summary`、`scenes[{location, summary, characters, est_seconds, change, start_anchor}]`、`characters[{name, aliases, role, excerpt}]`（`excerpt` 为原文外观描写，找不到为空）、`locations[…]`、`props[…]`。

**第二步：梗概**——新任务 `synopsis`（一次，输入是各块的 `summary`）：输出 `logline, synopsis, genre, tone, themes`。

**场景定位**：模型给出每场的 `start_anchor`（该场开头的一句原文，8–30 字）。代码在块内按顺序做**精确子串查找**，找到就把该场 `start` 定为该位置，并把上一场的 `end` 设为这里；找不到时这场的 `start` 沿用上一场的 `end`，并记一条 warning。偏移必须单调不减，首场从块起点开始，末场到块终点结束。小说来源同样用 `start_anchor` 在章内定位，供 WO4 截取原文使用（失败同样只记 warning）。

### 4.3 分集（两条路径共用）——新任务 `episode_plan`

- 按段调用：小说每 10 章一段，次要来源每 5 块一段；每段的单元交给模型划集。
- 输入：
  - 这一段的单元列表（`seq, label, location, summary, characters, est_seconds, change`）。
  - 每集目标时长区间，以及按「大约几集」与本段时长折算的本段建议集数（作者没填就不给）。
  - 上一段最后一集的标题、变化、钩子（保证连续）。
  - 梗概要点，以及小说来源的伏笔与改编参数。
- 输出：`episodes[{unit_from, unit_to, title, change, hook}]`。
- **硬约束**（不合格触发一次修正）：每集 `unit_from ≤ unit_to`；各集按顺序排列、互不重叠；都落在本段单元范围内。
- **软约束**（只记 warning）：
  - 每集预估时长 = 所含单元 `est_seconds` 之和，落在目标区间的 ±15% 以外。
  - 本段有单元没被任何一集覆盖（显示为「未纳入」）。
- 提示词写明规则，提炼自流水线 `02-分集拆镜.md`：
  - 每集必须有自己的变化（谁得知了什么、谁做了什么决定、关系或权力格局怎么移动）。
  - 没有变化的段落并入邻集，不靠空镜或旁白硬撑成一集。
  - 一集可以跨章，一章也可以拆成几集。
  - 每集要有终点或钩子。
- 各段结果由代码按顺序拼接、全书统一编号；段与段之间不重叠。
- **预估镜头数** = `round(预估秒数 / 3.5)`（平均每镜 3–4 秒）；**预估时长**由代码计算，不信模型给的数字。

### 4.4 总表合并（不调模型）

- 各批的人物、场景、道具，按规范化名字（去空白、全半角统一、casefold）与别名做确定性合并。
- 保留最早的首次出场位置；外观摘录取第一条非空的；`aliases` 合并去重。
- 小说来源的人物以小说工坊 id 为准；补全里新出现的人物追加。
- 「出场的集」由代码根据分集方案与单元里的 `characters` 计算，分集方案改动后重新计算。
- 合并不了的同物异名，由作者在界面里手动合并。

## 5. 数据与状态

### 5.1 新表（字段可按需补充，下表为最少集合）

| 表 | 内容 |
|---|---|
| `studio_breakdowns` | `id, project_id, owner, snapshot_no, provider, status`（`draft / running / partial / done / cancelled`），`settings_json`（每集目标秒数区间、大约几集），`import_json`（结构化导入结果：梗概、伏笔、时间线、改编参数），`synopsis_json`，`quote_id`，`outdated`（0/1），`created_at, updated_at`。一个项目可以有多次拆解，当前用的是最新一次；旧的保留。 |
| `studio_chunks` | `id, breakdown_id, project_id, owner, no, task`（`novel_complete / text_map / synopsis / episode_plan`），`source_json`（章号范围或块号与偏移），`depends_on_json`（依赖哪些批），`status`（`blocked / queued / running / succeeded / failed / uncertain / rejected / invalid_output / released / cancelled`），`job_id`（最近一次尝试的 `studio_jobs.id`），`provider`，`result_json`，`warnings_json`。 |
| `studio_units` | `breakdown_id, seq, label, chapter, scene_index, location, summary, characters_json, est_seconds, change, start, end`，主键 `(breakdown_id, seq)`。 |
| `studio_bible` | `id, project_id, owner, breakdown_id, kind`（`character / location / prop`），`name, aliases_json, role, description, appearance`（作者可改），`appearance_source`（`workshop / excerpt / author / none`），`excerpt`（原文摘录，只读），`needs_author`（0/1），`first_unit`，`episodes_json`（计算值），`ref_id`（如小说工坊 C1），`merged_into`，`archived`，`updated_at`。 |
| `studio_episodes` | `id, project_id, owner, breakdown_id, no, title, unit_from, unit_to, change, hook, target_min, target_max`（单集覆盖，NULL 表示用项目默认），`notes, updated_at`。预估秒数与镜头数在读取时计算。 |
| `studio_plan_revisions` | `project_id, owner, revision, plan_json`（该版本分集方案的完整快照），`created_at, created_reason`。每次 revision 加 1 都写一行，用于追溯。 |

`studio_projects` 补列：`episode_seconds_min`（默认 180）、`episode_seconds_max`（默认 240）、`plan_revision`（默认 0）、`plan_approved_revision`（NULL）、`breakdown_id`（当前拆解）。**G0 已批准** ⇔ `plan_approved_revision IS NOT NULL AND plan_approved_revision = plan_revision AND plan_revision > 0`。

### 5.2 revision 规则
- 拆解跑完、分集方案首次生成：`plan_revision` 加 1（从 0 到 1），未批准。
- 作者对分集方案的任何修改（合并、拆分、挪边界、改标题、变化、钩子、备注、单集时长）：在同一事务里 `plan_revision` 加 1，写 `studio_plan_revisions`；如果原先已批准，状态自然变成待批准（因为 revision 不再相等）。
- 每个修改请求必须带 `expected_revision`，不一致返回 409「分集方案已更新，请刷新」（防并发与重复点击）。
- 总表的修改不影响 `plan_revision`。
- 重新拆解（新的 breakdown）完成后，用新结果替换分集方案，`plan_revision` 加 1，旧方案留在 `studio_plan_revisions`。

### 5.3 与快照同步的关系
- 拆解记录绑定开跑时的 `snapshot_no`。作者之后同步了快照（`snapshot_no` 变大）时，把当前拆解标为 `outdated=1`，界面提示「拆解基于快照第 k 版，作品已同步到第 m 版」，并提供「重新拆解」（新报价）。
- 不自动作废 G0，由作者决定是否重新拆解。
- WO3b 已禁止在导演任务进行中同步快照，拆解任务属于导演任务，自动受此保护（加测试确认）。

## 6. 报价、预留与执行

- **报价**（`POST /studio/projects/{pid}/breakdown/quote`）：
  - 做结构化导入、算出批次计划，对每一批按「输入字符 × 1.5 + max_tokens」估算上限（沿用 `pricing.py`）。
  - 分集批的输入在报价时还不知道，按上限估算：每个单元 400 字，单元数按小说细纲场景数或每块 6 场估算。
  - 合计后：
    - 千问 / DeepSeek（人民币）：不得超过 `FIONA_STUDIO_MAX_QUOTE_CNY`（单次报价上限，**导演任务目前没检查，本期补上**），且「已用 + 预留 + 本次」不超过日上限。
    - Claude（美元）：不得超过本月 Claude 剩余额度。
  - 超限返回 409 并说明差多少，不发任何请求。
  - 报价写入 `studio_quotes`，返回批数、各类任务数、金额区间、provider、过期时间。
- **确认**（`POST /studio/quotes/{qid}/confirm`，沿用现有确认接口，或新增 `/breakdown/start` 带 `quote_id`，二选一，但必须「同一报价只能确认一次」）：
  - 在一个事务里建 `studio_breakdowns`、全部 `studio_chunks`，以及能立即执行的批的 `studio_jobs`，并为**全部批**预留费用。
  - 有依赖的批（`episode_plan` 依赖其段内的通读或补全批，`synopsis` 依赖全部 `text_map`）状态为 `blocked`。
  - 必须带 `project_id`，不得走「没绑定项目就新建项目」的旧路径（`brain_jobs.py:261` 附近）。
- **执行**：
  - 沿用 brain 的执行与每家 3 路并发。
  - 依赖全部成功后，代码组装该批输入（在线程里），转为 `queued`，交给调度。
  - 千问 / DeepSeek 跑拆解类任务时，超时放宽到 300 秒（只对本期新任务生效，WO3a 原有任务不变）。
  - Claude 维持现有公式。
- **新任务的 max_tokens**：
  - `novel_complete`：8192。
  - `text_map`：4096。
  - `episode_plan`：4096。
  - `synopsis`：2048。
- **单批重跑**（`POST /studio/breakdowns/{bid}/chunks/{cid}/retry`，带 `provider`）：
  - 只允许 `failed / rejected / invalid_output / released` 状态的批。`uncertain` 必须先释放（沿用 `/jobs/{jid}/release`），释放后批状态变为 `released`。
  - 每次重跑先单独报价、确认（金额小，同样受上限约束）。
  - 成功后解除下游批的 `blocked`。
- **取消**：取消整次拆解时，`queued / blocked` 的批取消并释放预留；`running` 的不打断，结束后按实际结算。
- **重启恢复**：沿用现有恢复（`running → uncertain`，`queued` 等调度补发）；`blocked` 保持不变；恢复后检查依赖满足的 `blocked` 批并解除。
- **部分完成**：某段的分集批无法完成时，整次拆解为 `partial`，已完成段的分集照常展示；未完成的段显示为「待重跑」，不允许批准 G0。

## 7. 路由（全部在 `/studio` 下，沿用作者门禁；请求模型一律 `extra="forbid"`）

| 方法与路径 | 说明 |
|---|---|
| `PATCH /studio/projects/{pid}` | 在现有基础上允许改 `episode_seconds_min / max`（整数，60 ≤ min ≤ max ≤ 900） |
| `POST /studio/projects/{pid}/breakdown/quote` | `{target_episodes?: int 1–300}`；返回报价 |
| `POST /studio/projects/{pid}/breakdown/start` | `{quote_id}`；或复用 `/quotes/{qid}/confirm`（二选一，写进报告） |
| `GET /studio/projects/{pid}/breakdown` | 当前拆解：状态、各批（状态、provider、费用、warning）、梗概、单元数、`outdated`、总费用 |
| `POST /studio/breakdowns/{bid}/chunks/{cid}/retry/quote` 与 `/retry` | 单批重跑的报价与确认 |
| `POST /studio/breakdowns/{bid}/cancel` | 取消 |
| `GET /studio/projects/{pid}/bible` | 总表（可按 kind 过滤） |
| `PATCH /studio/bible/{id}` | 改 `name / aliases / role / description / appearance / needs_author`；改了 `appearance` 时 `appearance_source='author'`、`needs_author=0` |
| `POST /studio/bible/merge` | `{keep_id, merge_ids[]}`；同 kind 才能合并；被合并项标 `merged_into`，不删除 |
| `POST /studio/bible` / `DELETE /studio/bible/{id}` | 手动新增 / 归档（`archived=1`，不物理删除） |
| `GET /studio/projects/{pid}/episodes` | 分集方案：每集计算好的预估秒数、镜头数、原文范围文字、出场人物、warning；`plan_revision`、`plan_approved_revision`、`g0_approved`；未纳入的单元区间 |
| `POST /studio/projects/{pid}/episodes/ops` | `{expected_revision, op, ...}`，`op` 为：`edit`（`no`，字段）、`merge`（`no` 与下一集合并，文字字段用「；」拼接）、`split`（`no`，`at_unit`：从该单元起为新一集，新集标题为「原标题（下）」）、`move_boundary`（`no`，`delta: -1/+1`：本集与下一集的分界前后移动一个单元，任何一集不得因此变空）、`delete`（集变成未纳入）、`insert`（把一段未纳入的单元建成新集）。操作后统一重新编号、重算出场人物，并在同一事务里 revision 加 1 |
| `POST /studio/projects/{pid}/episodes/approve` | `{expected_revision}`；要求拆解不是 `partial`、至少 1 集；设 `plan_approved_revision = plan_revision` |
| `GET /studio/projects/{pid}/breakdown/export` | Markdown 下载 |

Markdown 导出：
- 标题与项目信息：作品、快照第几版、拆解所用模型、方案 revision 与批准状态。
- 梗概。
- 人物、场景、道具三张表。
- 分集方案表（7 列加出场人物）。
- 未纳入的单元。
- 伏笔与时间线（仅小说来源）。

格式要求：
- 文本做 Markdown 转义，参照 `exchange_exports.py` 的 `_inline`。
- 文件名用 `filename*=UTF-8''` 编码，参照 `routers/novel.py:161-163`。
- 响应头 `Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff`。

## 8. 前端（宋式清雅 × 液态玻璃，沿用 `Glaze` / `ceramic-card` / `.btn` / `.chip` / `.tag` / `.readout` / 原生 `<dialog>`）

### F1「①拆解」页签结构（`StudioWorkbench.tsx` 的 index 0）
自上而下：
1. 作品来源（WO3b 的 `SourcePanel`，不变）。
2. **拆解**面板（新）。
3. 拆完后的**梗概**、**总表**、**分集方案**（新）。
4. 原「剧本试读」（`BrainTrial`）收进默认折叠的 `<details>`，标题「试读与三家对比」，功能不变。

空白项目（没有作品来源）只显示「先关联作品才能拆解」，不显示拆解面板。

### F2 拆解面板
- **设置**：每集时长（两个数字框：最短与最长秒数，旁边显示折算的分钟），「大约几集（可不填）」，当前导演模型（只读，改模型沿用顶部已有选择器）。改时长调 `PATCH`。
- **报价**：点「报价」→ 原生 `<dialog>` 显示批数（补全 / 通读 / 分集 / 梗概各几批）、金额区间、模型、过期倒计时 →「确认开始」。超限时显示后端给的原因，按钮禁用。
- **进度**：总进度条 + 批次列表（可折叠，默认只展开有问题的批）。每批：位置（如「第 1–10 章 · 补全」）、状态、模型、费用、warning 数；`failed / rejected / invalid_output / released` 有「重跑」（可选模型，先报价再确认）；`uncertain` 有「释放」（说明「可能已扣费」）。有在途批时每 5 秒轮询，没有就停。
- **过期提示**：`outdated=1` 时显示提示条和「重新拆解」。
- **部分完成**：`partial` 时显示哪几段待重跑。

### F3 结果区
- **梗概**：小说来源显示一句话梗概、主题、核心冲突、主线、分段梗概；次要来源显示 logline、梗概、类型、基调、主题。
- **总表**：「人物 / 场景 / 道具」三个页签（`useRovingTabs`），表格列为名字（含别名）｜定位｜外形或描述｜原文摘录（可展开）｜首次出场｜出场的集。
  - 「待作者补充」用 `.tag` 醒目标出，并有筛选「只看待补充」。
  - 行内「修改」与「保存 / 取消」（参照 `BiblePanel.tsx`）。
  - 勾选两行以上可「合并」，弹确认框选保留哪一个。
  - 可新增、可归档。
- **分集方案表**：列为 集号｜标题｜原文范围｜这集发生的变化｜终点 / 钩子｜预估镜头数｜预估时长｜目标时长｜出场人物。
  - 预估时长超出目标区间 ±15% 时，该格标色并有文字提示，不能只靠颜色。
  - 每行操作收在一个「更多」菜单里：修改（标题、变化、钩子、备注、单集目标时长）、与下一集合并、拆分（选拆分点：列出该集的单元，点选从哪一场开始为新一集）、边界前移 / 后移一场、删除（变为未纳入）。
  - 未纳入的单元区间以灰色行显示，带「建成一集」。
  - 表头上方：方案第 n 版 · 待批准 / 已批准（第 k 版）、集数合计、总预估时长；「批准分集方案」（原生 `<dialog>` 确认，说明「批准后再改会生成新版本、需要重新批准」）、「导出 Markdown」。
  - 修改请求一律带 `expected_revision`；收到 409 时提示「分集方案已被更新」并刷新。
- **适配**：宽屏显示表格；窄屏（<640px 容器宽）改为每集一张卡片，不出现横向页面滚动；表格本身可以在自己的容器里横向滚动。
- **状态**：空状态、加载态、错误态、成功提示都要有。

### F4 WO3b 遗留：多项目「打开」按钮
`frontend/components/studio/SourceChoices.tsx` 的 `ExistingSourceProjects`：
- 每个项目名后显示建立日期（`YYYY-MM-DD HH:mm`，本地时区）。
- `primary` 模式下只有**最近建立**的那个项目的「打开」用 `btn-primary`，其余用 `btn-quiet`。
- 后端 `list_candidates` 返回的 `projects` 已含 `created_at`，没有就补上，按建立时间倒序。

## 9. 验收标准

### 9.1 命令
- `cd backend && python -m pytest -q`：0 failed、0 error，**不带 deselect**。沙箱里本机端口绑定导致的失败如实列出，主控会在沙箱外复跑。
- 临时把 `frontend/node_modules` 改名为 `node_modules.__hidden`，跑一遍全量：0 failed，所有 node 驱动的测试都是 skip。**跑完必须改回原名。**
- `cd frontend && npm run lint`（0 error，警告不多于基线 25）、`npx tsc --noEmit`、`npm run build` 全部通过。沙箱里 Turbopack 失败时，补跑 `npm run build -- --webpack` 并如实说明。

### 9.2 必测项（离线，用假 provider 与 monkeypatch，不联网）
- **批次计划**：
  - 小说按「≤10 章且 ≤24,000 字」分批。
  - 次要来源超过 12,000 字的块在段落边界再切。
  - 分集按 10 章 / 5 块分段。
  - 依赖关系正确。
  - 结构化导入不调模型，且导入的人物、单元、梗概与快照一致。
- **报价与上限**：
  - 人民币报价超过单次上限、超过日上限剩余，都返回 409，且 POST 次数为 0。
  - Claude 超本月剩余，同样 409、0 次请求。
  - 同一报价确认两次，第二次 409。
  - 报价过期后不能确认。
  - 确认后全部批都已预留。
- **执行与依赖**：
  - `blocked` 批在依赖成功后才组装输入并执行。
  - 某批失败时，下游保持 `blocked`。
  - 单批重跑（换 provider）成功后下游解除，且重跑前必须报价确认。
  - `uncertain` 必须先释放才能重跑。
  - 取消时释放未执行批的预留。
  - 重启恢复不重发任何请求（POST 次数断言），`blocked` 不变。
  - 拆解请求都绑定当前项目，不会新建项目。
- **新任务**：
  - 四个任务的 schema 与硬约束：`episode_plan` 的重叠、乱序、越界触发一次修正，修正仍不合格判 `invalid_output`。
  - 软约束（时长偏离、未纳入）只记 warning。
  - 千问 / DeepSeek 新任务超时 300 秒、原任务不变。
  - 截断不修正。
  - 原文以数据块传入。
- **场景定位**：`start_anchor` 精确命中时偏移正确且单调；未命中时沿用上一场终点并记 warning；首尾覆盖整块。
- **总表合并**：
  - 规范化名字与别名合并。
  - 首次出场取最早。
  - 小说人物 id 优先。
  - 缺外形且原文无摘录 → `needs_author=1`。
  - 绝不把模型的非原文描述写进 `excerpt`：校验 `excerpt` 必须是对应原文的子串，否则丢弃并记 warning。
- **分集计算**：预估秒数等于单元之和；镜头数为 `round(秒/3.5)`；出场人物由单元计算；各段拼接后编号连续。
- **分集操作**：
  - `edit / merge / split / move_boundary / delete / insert` 各自结果正确。
  - 不变量：各集按顺序、不重叠、非空，编号连续。
  - 每次操作 revision 加 1 并写 `studio_plan_revisions`。
  - `expected_revision` 不符 409。
  - 已批准后修改会变成待批准。
  - `partial` 时不能批准。
  - 批准后 `g0_approved` 为 true。
- **快照同步**：同步后当前拆解 `outdated=1`；拆解进行中不能同步（409）。
- **导出**：Markdown 内容与接口数据一致；Markdown 特殊字符被转义；响应头正确；中文文件名编码正确。
- **归属与准入**：别人的项目、拆解、批、总表条目，一律 404；非作者访问所有新路由 404。
- **删号**：新表的行随账号删除。
- **F4**：多个项目时，只有最近一个的「打开」是主按钮，并显示日期（SSR 测试）。
- **前端**：拆解面板（未报价、报价对话框、进行中、部分完成、过期）、总表（待补充标记、行内编辑、合并）、分集表（超时标记、操作菜单、409 刷新、批准对话框、窄屏卡片）的关键状态，有组件测试或 SSR 测试，全部带缺依赖 skip 守卫。

## 10. 完成后输出（写进 `docs/tasks/2026-10-16-studio-wo3c-breakdown/03-report.md`）
1. 修改了哪些文件（含新增）。
2. 实现了哪些功能。
3. 与本规格各节的逐项对应（§4–§8、F1–F4）。
4. 测试结果（两种环境的全量、前端三项）。
5. 未完成或需要人工确认的地方。设计上的取舍也写进来，例如确认接口选了哪种、分集段的大小。
