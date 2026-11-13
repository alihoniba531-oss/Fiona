# 规格：短片工作室「边写边拆」——连载中的小说建项目与续拆

- 规格版本：v1.2（2026-11-13）。v1.1 于 2026-11-12 经作者确认；v1.2 新增 §4.8 R1、§4.9 R2、§4.10 R3 返修。三项产品决定已由作者在 2026-11-12 定下，见 §1。v1.0 经四路对抗审查后修订，修订内容见 §8。
- 任务级别：**L3**。涉及拆解数据的追加语义与计费流程。复核用 dsh 上的 Opus 5.5 `xhigh`。
- 基线：Fiona `main` = `135253f`。
  - 有 `frontend/node_modules` 时，后端全量 `8264 passed / 0 skipped`（`pytest --collect-only` 也是 8264 条）。
  - 前端：`tsc` 退出 0；`npm run lint` 为 `0 errors, 25 warnings`，告警全在 `app/page.tsx` 与 `app/plaza/page.tsx`；`npm run build` 退出 0。
  - 行号以 `135253f` 为准。

## 1. 产品目标与场景

作者边写小说边做短片。

1. 书写到第 5 章，就能在工作室为它建项目，先拆前 5 章、出分集方案、做定妆。
2. 写到第 12 章时，在工作室的来源面板「同步」一次，拆解页出现「续拆第 6–12 章」。
3. 作者看过报价、确认后，只为第 6–12 章付费。已经拆好的单元和总表、作者改过的分集、已经选定的定妆图和声线都保留。
4. 新章的分集追加在方案末尾，方案退回待批准，新增的集标「新增」。作者看一眼、重新批准一次即可。

作者 2026-11-12 的三项决定：

1. **待复核章节照收并标出**：快照和拆解照常收这些章，来源面板与拆解页标「待复核」。
2. **已拆过的章后来被改了，照常续拆、只提醒**：续拆只拆新增章，旧章的改动不进拆解；面板列出改过的章，作者需要时仍可整本重新拆解。只重拆受影响的段不在本期。
3. **续拆后整份分集方案重新批准一次**：沿用现有 G0 语义，发布即退回待批准。

## 2. 现状事实

### 2.1 来源与快照（`backend/studio/sources.py`）

- **资格判定** `_eligibility(book, canonical_bible, editing=False)`（`:61-75`）按顺序给出六种拒绝原因：
  1. 「作品尚未完结」：status ≠ completed
  2. 「作品缺少故事圣经」
  3. 「作品没有章节」
  4. 「作品有待复核章节，请先在小说工坊完成复核」
  5. 「作品有尚未完成的章节」
  6. 「作品正在修改，请稍后再试」

  调用方有三处：候选 `_candidate`（`:86`）、建快照 `take_novel_snapshot`（`:147`，建项目和同步都走它）、`source_status`（`:582`）。分身的做成片 `novel_chat.start_film` 先看候选的 `eligible`（`novel_chat.py:124-125`）。
- **读取范围** `_all_chapters`（`:126-134`）：
  - `maximum` 取「detail 里所有章号」与 `chapters_done` 中的较大值，然后按每次 50 章调用 `service.chapters_range`。
  - `chapters_range` 不过滤状态（`novel/service.py:306-312`）。逐章确认模式下，第 `chapters_done+1` 章是一条正文为空的进行中行。
  - `commit_chapter` 只接受 `chapters_done+1`，同一事务里写正文、`chapters_done` 和 `bible_version`（`novel/store_db.py:292-318`）。所以第 1..`chapters_done` 章没有空洞，状态只会是 done 或 stale，且都有正文；planning/awaiting_plan_approval/writing 行只出现在 `chapters_done+1`。
- **组装** `_assemble_novel_snapshot`（`:160-181`）：要求第 1 章到 `maximum` 每章都有非空正文，否则 409「第 N 章正文缺失或为空」。manifest 每章记录 index（小说里等于章号）、chapter、title、sha256、status、flags、updated_at、edited_by_user 和 outline。
- **签名** `_signature`（`:137-139`）= `(updated_at, bible_version, status, ((章号, 章status)…))`。
  - 计费的每次预留和结算都会更新 `novels.updated_at`（`novel/billing.py:225`、`:260`）。
  - 每提交一章，`bible_version` 加 1（`novel/store_db.py:296`）。
  - 后台写作期间 `runner.is_editing` 为 False，只在改稿、结构升级和暂停时为真。
- **重新归档窗口**：作者改**最新**一章时，`edit_chapter` 在事务里写 `config['_rearchive']=章号`、`status='running'` 后提交，随即退出 `editing_novel`（`novel/service.py:958-966`、`runner.py:50-57`）。真正的重新归档在后台做一次模型调用（`runner.py:287-290`），结束时才写新圣经、`bible_version+1`（`runner.py:590-598`）。这段时间 `is_editing` 为 False，`bible_version`、`chapters_done`、各章状态都不变，`service.detail` 返回的 config 里能看到 `_rearchive`（`service.py:256`、`:260` 只弹出 `_last_error`）。重新归档失败时书转 paused，`_rearchive` 仍留着。旧规则靠「作品尚未完结」挡住了这个窗口。
- **漂移** `_compare_drift`（`:587-597`）返回 `{state, changed, added, removed, bible_changed, book_status, eligible, reason}`。非小说来源的 drift 是 `{'state': 'not_applicable'}`（`:569`），原作不可访问时是 `{'state': 'unavailable'}`（`:580`），这两种都没有 `book_status`。
- **来源状态** `source_status`（`:561-584`）：`snapshot` 只带 `id/no/created_at/chapters/chars` 与 `flagged`（`:566-567`），没有 stale。
- **候选** `_candidate`（`:83-95`）：`projects` 只查 `id,title,snapshot_no,created_at`（`:88-90`），没有快照章数；`chapters_done` 是书当前的值。
- **同步** `sync_source`（`:600-612`）：
  - 只接受小说来源，要求 `expected_no` 等于当前快照号；项目里有 `queued/submitting/submitted/running` 的导演任务时返回 409「导演模型任务进行中，完成后再同步」（`:483-485`、`:606-608`）。
  - 新快照在 `_save_snapshot` 里落库；同一事务里把当前拆解标 `outdated=1`（`:491-492`），并把项目的 `snapshot_no` 加 1。
  - 不改分集方案版本，也不碰定妆。
- **分身做成片** `novel_chat.start_film`（`novel_chat.py:115-133`）：有未归档项目就复用 `projects[0]`，不同步；卡片第二行是「{书当前 chapters_done} 章 · {字数} 万字 · 快照第 {snapshot_no} 版」，第三行固定「已建项目，尚未花费」。

### 2.2 拆解（`backend/studio/breakdown.py`、`breakdown_material.py`、`breakdown_plan.py`）

- **报价**：`quote`（`breakdown.py:141-155`）每次都对整份当前快照出计划，用的是 `batch_plan(manifest, entries)`（`breakdown_material.py:85-158`）。切批规则：
  - 「段」=`(章号-1)//10`。
  - 每批最多 10 个片段、24000 字，同一章的不同片段不在一批，一批不跨段。
  - 每段一个 `episode_plan`，依赖段号不大于本段的全部补全批，再加上一段的 `episode_plan`。
  - 末段终点取 `min((seg+1)*10, len(entries))`。
  - `batch_plan` 内部用 1 起的本地批号 `no = len(chunks)+1`（`:87-91`），并直接拿它当下标：`chunks[number - 1]`（`:149`、`:154`）。
  - 传了 `target_episodes` 时，每个 `episode_plan` 改为依赖全部补全批（`breakdown.py:84-88`）。
- **确认** `start`（`:222-285`）在一个写事务里（`:224`），读快照的 `_locked_snapshot`（`:246`）也在这个事务块里：
  1. 旧拆解有 uncertain 批时返回 409；有 running/submitting 批时返回 409。
  2. 检查快照号。
  3. 新建拆解行（`settings_json` 含 `target_episodes`，`:257`），旧拆解记 `superseded_by`。
  4. 每批建一个 queued 任务并预留费用；有依赖的批标 blocked（job 仍是 queued）。
  5. 写入结构化单元和初始总表，把 `project.breakdown_id` 改指新拆解。
- **分集批的输入** `_dependency_input(breakdown, chunk, chunks, units)`（`:332-354`，同步函数，经 `asyncio.to_thread` 调用；调用方 `prepare_job` `:488`、`retry_quote` `:656`）：
  - `previous_episode` = no 更小、已成功的 `episode_plan` 批**模型原始输出**的最后一集（`:342-343`）。作者对分集的编辑只改 `studio_episodes`，不回写批的 output。
  - 拆解 settings 里有 `target_episodes` 时写 `suggested_episodes`（`:350-353`），读的是拆解行自己的 settings。
- **总表** `_insert_bible(db, breakdown, bible)`（`:355-438`）：
  - ID = `uuid5(拆解id, kind:(ref_id 或 name))`（`:361`）。ID 已存在就更新：`first_unit`、`aliases_json` 整体覆盖（作者改过的除外），role/description/excerpt/appearance 只补空值；不存在就插入。
  - 之后的退役循环：不在本次 desired 里的自动条目（uuid5 或在 `_generated_bible_ids` 里），若与某个 desired 条目同 kind 且 ref_id 相同、或规范化名字/别名相交，就写 `merged_into`（`:397-434`）。作者新建的 uuid4 行不参与。
  - 函数末尾把 `breakdown['imported']` 写回 `import_json`，含更新后的 `_generated_bible_ids/_bible_author_edits/_bible_merge_warnings`（`:435-438`）。
  - `merge_bible`（`breakdown_material.py:216-219`）先放入 imported 里的人物，再把批次输出的新人物按 ref_id 优先、名字相交合并进去，合并结果带上 ref_id。
- **孤儿** `casting.is_orphaned`（`casting.py:128-132`）：条目已归档、已有 `merged_into`、或 `breakdown_id` 不是已发布拆解时都是孤儿。定妆不会迁移到合并目标上。
- **单元物化** `_materialize`（`:288-329`）按批次 no 顺序重建全部单元，并重新编 seq；没成功的补全批回落到结构化单元。`_insert_units` 先整表删除再插入（`:181-187`）。旧批在 refresh 物化时优先用 job 的 `params.inputs`，只有它为空才回落 `_source_inputs`（`:557`）。
- **读原文** `_source_inputs`（`:446-468`）用的是 `breakdown['snapshot_no']`（`:450`）；`prepare_job` 在执行时才组装输入，并写进 job 的 `params.inputs`（`:471-495`）。
- **状态** `_status`（`:509-519`）：有 RETRYABLE 或 uncertain 状态的批就是 partial。
- **刷新** `refresh`（`:534-593`）：
  - 同步任务状态、按需物化（物化分支把 warning 写进 `_chunk_material_warnings`，`:561`）。
  - 依赖满足后把 blocked 改成 queued。
  - 状态为 done 或 partial、拆解未退役（`:584`）、且「全部成功分集批的模型输出拼接」的指纹变了时，调用 `publish_plan(db, bid, episodes)`（`:578-588`）。
- **发布** `publish_plan`（`breakdown_plan.py:219-241`）删光本拆解的集，用新 uuid 重新插入并重新编号；`project.breakdown_id == bid` 时 `plan_revision` 加 1、写版本行。
- **分集操作** `_operate`（`breakdown_plan.py:255-319`）：每次操作后重新编集号（`:316-317`），insert 按 `unit_from` 排序（`:313`），delete/merge/split 都会让后面的集号移动。拆解 done、方案未批准时允许操作（`:322-339`）。
- **分集视图** `_present_episodes`（`breakdown_plan.py:108-142`）：未被任何集覆盖的单元全部列进 `unassigned`；返回 `units`。导出 `export_markdown`（`:641`）同样列出「未纳入的单元」。
- **G0**：
  - `g0_approved` 的条件是 revision > 0、等于 approved，且至少一集（`breakdown_plan.py:135-138`）。
  - 拆解为 running 或 partial 时，分集操作与批准都返回 409（`:327-328`、`:347-351`）。
  - 定妆的付费入口靠 `_require_g0`（`casting.py:63-67`），在写事务之外检查。
- **取消** `cancel`（`breakdown.py:691-695`）只是包装 `_cancel_unexecuted`（`:203-214`）：取消 queued/blocked 批并释放预留；拆解状态不是 done 时改成 cancelled，即「退役」（`_retired`，`:217-219`）。`start` 也调 `_cancel_unexecuted`（`:251`）。
- **额度**：预留按确认日计入当天人民币日额度，Claude 按确认月计入当月美元额度（`spend.py:31-35`、`:99-101`）。
- **视图** `get_current`（`:596-636`）返回 `id/status/snapshot_no/provider/quote_id/outdated/settings/synopsis/chunks/units_count/unit_count/totals/total_cost/retry_needed/blocked_segments/warnings`。

### 2.3 前端与聊天

- **书斋工作台**：`const completed = book?.status === "completed"`（`NovelWorkbench.tsx:82`），工作室权限检查 effect 以它为条件，依赖数组 `[beginStudio, completed]`（`:83-92`）；`:294` 工具栏「做成片」、`:300` GateBanner 的 `onMakeFilm`、`:322` `NovelFilmDialog` 都要求完结。GateBanner 只在完结分支给「做成片」（`GateBanner.tsx:28`）。
- **做成片对话框** `NovelFilmDialog.tsx`：只导入 `ExistingSourceProjects, SourceAspectPicker, SourceFlags, sourceDialogClass`（`:9`），`:48` 只显示已有项目、flags 和不可选原因。`NovelSourceChoice` 只被 `CreateProjectDialog` 使用。
- **新建项目对话框**：空态文案「没有找到符合书名的作品。只有已完结并通过检查的作品可以导入。」（`CreateProjectDialog.tsx:69`）。
- **来源面板** `SourcePanel.tsx`：`studioDriftSummary` 在 `:9-16`；`:54` 只在 unchanged 时显示「原作与快照一致。」；`:56` 只在 `drift.state === "changed"` 时渲染摘要与同步按钮。
- **拆解面板** `BreakdownPanel.tsx`：
  - `:39` `canCancel` = 拆解没取消且有 queued/blocked/running 批；`:56` 据此显示「取消拆解」；`:61` 的确认框写「未执行的批次将取消并释放预留。…」。
  - `:46` 在 `outdated` 时显示「拆解基于快照第 k 版…」并给「重新拆解」。
  - `:54` 报价主按钮禁用条件：`busy || active || !valid || providers.find(item => item.id === project.brain_provider)?.available === false`。
- **报价对话框** `BreakdownQuoteDialog.tsx`：`!retry` 下有三条整本专用提示：`:17`「每集目标时长将保存为…」、`:18` affectsApproved、`:19` replacesPartial；`:20` 总是显示「共 N 批」。标题与确认按钮在 `:16`。
- **拆解页容器** `BreakdownStage.tsx`：`:83` 整本报价把 `{ value, settings, affectsApproved, replacesPartial }` 放进 quote 状态；`:100` 给 EpisodePlan 传 `partial = status 为 partial 或 running`；`:103` 确认时只有两支：`chosen.retry ? retryBreakdownChunk(...) : startStudioBreakdown(...)`。
- **分集方案** `EpisodePlan.tsx`：`:52` `regenerating = partial || …`；`:71` 在 regenerating 时显示「拆解尚未全部完成，补跑完成后分集方案会按新结果重新生成。…」；`:73` 表格视图（`data-testid="episode-table"`），`:74` 卡片视图（`data-testid="episode-cards"`），卡片标题是 `<h3 className="text-fs-15 break-words font-medium">`；`:66` 超时提示也有 `font-medium`。SSR 输出里两种视图同时存在。
- **请求函数** `frontend/lib/studio-breakdown.ts:54-69`；`formatEpisodeRanges` 在 `:91-99`。
- **分身**：
  - 工具描述「将已完结小说建立短片工作室项目与快照；免费。」（`backend/services/claude_agent.py:125`）
  - 平台意图「novel_to_film  把已完结小说建立短片工作室项目」（`backend/intent_router.py:148`）
- **与新规则冲突的其他陈述**（`git grep` 全部结果）：
  - `backend/services/claude_agent.py:845`（修改意见卡工具回给 Claude 的文字）：「…改较早的章会让后面已写的章永久待复核、不能做成片，故事圣经与章节摘要也不会重算。」
  - `frontend/components/NovelFeedbackCard.tsx:397`：「…改较早的章节会把它后面已写好的章永久标成「待复核」，有待复核章节的书不能做成片；…」
  - `README.md:369`（修改意见卡一段）同类陈述。
  - `backend/.env.example:231`：「# 作品来源：已完结小说工坊作品、…」

### 2.4 测试锁与可用夹具

- `backend/tests/test_studio_sources.py`（夹具书 `chapters_done=2`，两章都 done；`state['book']` 是 detail，`state['chapters']` 是 `chapters_range` 的返回）：
  - `:136-153` `test_eligibility_rejects_with_reason`：六个参数 `running/planning/stale/bible/editing/empty`。
  - `:157-179` `test_candidate_flags_projects_and_exact_title_search`：末尾把书改成 `title=None, status='setup_running'` 后断言不可选。
  - `:182-193` `test_consistent_snapshot_retries_once`：从第 2 次 detail 起改 `updated_at='new'`，断言 `details==4`、读了两轮、manifest 的 `updated_at=='new'`。
  - `:196-207` `test_continuous_change_rejected`：每次 detail 都改 `updated_at`，期望 409「作品正在修改，请稍后再试」、读了两轮。
  - `:232-258` 漂移用例，`:243` 精确比对整个 drift 字典。
  - `:261-275` `test_sync_rejects_ineligible_and_busy_brain`：前半把第 1 章设 stale、断言同步报「待复核」；后半断言「导演模型任务进行中，完成后再同步」。
  - `:493-504` AST 锁之一：`studio/**` 只能用 `novel.service` 的六个只读函数和 `runner.is_editing`；另外 `:504` 用不区分大小写的正则扫描 `studio/**` **全文（含注释和字符串）**，不得出现 `FROM|INTO|UPDATE|JOIN` 后紧跟 `novels` 或 `novel_`。
- `test_studio_sources_readonly_integration.py:177-211`：另一条 AST 锁。**本任务不得新增任何 `novel.*` 导入。**
- `backend/tests/test_studio_sources_frontend.py:118` `test_incomplete_workbench_never_requests_studio`。
- `backend/tests/test_novel_chat.py:116`：复用已有项目时逐字断言卡片 `points == ["《春山》", "3 章 · 1 万字 · 快照第 2 版", "已建项目，尚未花费"]`（桩里 `projects=[{"id":"existing","snapshot_no":2}]`）。
- `backend/tests/test_novel_chat_feedback.py:35-39` 的 `WRITTEN_SENTENCE` 与 `test_novel_chat_feedback_frontend.py:251-258` 的 `WRITTEN_DESCRIPTION` 逐字锁着 §2.3 那两句「不能做成片」。
- `test_novel_chat.py:129-130` 与 `test_studio_sources_frontend.py:45` 里的「作品尚未完结」只是桩数据，不依赖真实规则，保持不动。
- 可照抄的夹具：
  - 小说来源、两版快照与同步：`from test_studio_sources import workshop, novel_project, sql`（`test_studio_breakdown_plan_sources.py:8` 已这样用）。追加章节的方法：同时改 `state['chapters']`、`state['book']['chapters']`、`state['book']['chapters_done']`（必要时 `bible_version`），再调 `sources.sync_source`。
  - 带 `novel_complete` 输出的假导演模型：`test_studio_breakdown_integration.py:66-98` 的 `Adapter`（需要时补 `episode_plan` 分支）；`:104` 把 `brain_jobs._schedule` 换成往列表追加，再用 `brain_jobs._background(jid)` 逐个执行。
  - 额度环境变量：照 `test_studio_breakdown_pipeline.py:23-26` 设置。
  - 前端：`test_studio_breakdown_frontend.py` 的 `DRIVER`、`SETUP`（`:41`）、`STAGE_SETUP`（`:125`）与 `test_stage_quote_confirm_and_409_refresh`（`:130`）可用于 Breakdown 系列组件和 `BreakdownStage`；它的 DRIVER **没有** mock `next/navigation`，加载不了 `NovelWorkbench`。`NovelWorkbench` 用 `test_studio_sources_frontend.py:15` 的 `NOVEL_DRIVER` 加 `screen(...)`（照 `:111-119`）；`SourcePanel/SourceChoices/CreateProjectDialog/NovelFilmDialog` 用 `test_studio_sources_frontend.py` 的 `DRIVER` 与 `probe(script, driver)`（`:18`）。

## 3. 设计决策

1. **资格**：小说来源只要求三件事，按以下顺序判断：
   1. 有故事圣经，否则「作品缺少故事圣经」；
   2. `chapters_done ≥ 1`，否则「作品还没有写好的章节」；
   3. 不在修改中：`is_editing` 为假，且 detail 的 `config` 里没有 `_rearchive`；否则「作品正在修改，请稍后再试」。

   不再要求已完结、全部 done、没有待复核。**不得用书的 status 判断资格。**
2. **快照范围**：只收第 1 章到第 `chapters_done` 章。这些章的状态是 done 或 stale，都有正文；`chapters_done` 之后的行一律忽略。已完结的书 `chapters_done` 就是总章数，行为不变。
3. **签名**：改为 `(bible_version, chapters_done, config._rearchive, ((章号, 章status) for 章号 ≤ chapters_done))`，不再看 `updated_at` 和书的 status。读取期间提交了新章、改了圣经、旧章被标待复核或开始重新归档，仍然会重试。
4. **续拆 = 同一份拆解追加**：
   - 不新建拆解。
   - 新批次追加到当前拆解，no 接着编，每批在 `source_json` 里记 `snapshot_no` 与 `round`。
   - 总表沿用已有条目：续拆后新出现的条目，只要与本拆解已有的活动条目同类且 ref_id 相同或名字/别名相交，就并到已有条目上，不新建、不把旧条目标成合并（§4.3 T4 第 6 步）。所以已定的妆不会变孤儿。
   - 拆解的 `snapshot_no` 改为续拆所用的快照号，`outdated` 清零。
   - 每章的「拆解依据」（快照号、sha256、标题、状态）按章记录，旧章不随续拆覆盖，「改过的旧章」和「待复核」提醒据此计算。
5. **切段**：续拆从「已拆到的最后一章 +1」起，每 10 章一段，段号接在现有最大段号之后。段内切批规则不变。每段一个 `episode_plan`。
6. **续拆的批次不使用「大约几集」**：连载书不知道全书集数。续拆报价不收这个参数；即使这份拆解当初填过「大约几集」，续拆的分集批也不带建议集数。每集时长沿用这份拆解的 settings，续拆时不能改。
7. **衔接**：续拆每一轮的第一个分集批，拿已发布方案的最后一集（含作者编辑）当「上一段末集」，不拿旧批的模型原始输出。
8. **发布**：
   - 拆解从未续拆过：保持现状。
   - 续拆过：不再用模型原始输出重建整份方案。本轮全部成功（拆解 done）时，取当前已发布的集（含作者编辑，按 no 排序），在末尾接上本轮新分集批的输出，调用 `publish_plan`。版本号加 1，G0 随之失效，即「整份重新批准」。
   - 本轮有批失败（partial）时不发布，已发布方案保持不变，作者可以单批重跑。
9. **续拆进行中（running/partial）**：
   - 不提供取消：取消接口返回 409，前端不显示「取消拆解」。整本重新拆解的入口保留，规则不变；整本重拆会取消本轮未执行的批并释放预留。
   - 旧 G0 继续有效，旧的分集方案原样显示；新章的单元不算进「未纳入」，新章的人物已经出现在定妆页（G1 会回到未通过）。
   - 本轮失败且单批重跑也救不回时，只能整本重新拆解（会生成新总表，已定的妆要重新定）。本期不做「放弃本轮续拆」。
10. **「新增」标记**：按单元界定。续拆发布时记下本轮第一个新单元的 seq；方案视图返回 `appended_from` = 第一个 `unit_to` 不小于它的集号。各集按单元升序且不重叠，所以标「新增」的总是末尾连续的一段，作者改方案、再次续拆都不会标错。作者批准后清空。
11. **不做**：
    - 次要来源（上传文本、成稿）的续拆；
    - 只重拆改过的段；
    - 自动续拆（必须作者点、报价、确认）；
    - 续拆时改时长或集数；
    - 续拆中途取消、放弃本轮续拆；
    - 案头分集页显示「新增」。

## 4. 执行者任务清单

### 4.1 白名单（只许改 / 新增这些文件）

- 后端：
  - `backend/studio/sources.py`
  - `backend/studio/breakdown.py`
  - `backend/studio/breakdown_material.py`
  - `backend/studio/breakdown_plan.py`
  - `backend/studio/novel_chat.py`（只改 `start_film` 复用已有项目的分支，见 §4.5）
  - `backend/routers/studio.py`
  - `backend/services/claude_agent.py`（只改 `:125` 与 `:845` 两句）
  - `backend/intent_router.py`（只改 `:148` 一句）
  - `backend/.env.example`（只改 `:231` 一句）
- 前端：
  - `frontend/lib/studio.ts`
  - `frontend/lib/studio-breakdown.ts`
  - `frontend/components/studio/BreakdownPanel.tsx`
  - `frontend/components/studio/BreakdownStage.tsx`
  - `frontend/components/studio/BreakdownQuoteDialog.tsx`
  - `frontend/components/studio/EpisodePlan.tsx`
  - `frontend/components/studio/SourcePanel.tsx`
  - `frontend/components/studio/SourceChoices.tsx`
  - `frontend/components/studio/CreateProjectDialog.tsx`
  - `frontend/components/novel/NovelWorkbench.tsx`
  - `frontend/components/novel/NovelFilmDialog.tsx`
  - `frontend/components/NovelFeedbackCard.tsx`（只改 `:397` 那半句）
- 新测试：
  - `backend/tests/test_studio_serial_sources.py`
  - `backend/tests/test_studio_serial_continue.py`
  - `backend/tests/test_studio_serial_frontend.py`
- 授权改动的既有测试，只限 §4.6 第 1 条列出的部分。
- 文档：`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`。
- 报告：`docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md`。
- `docs/tasks/2026-11-12-studio-serial-breakdown/` 下派单方事先放好的文件（`01-brief.md`、`02-spec.md`、派单与返修单）不得修改或删除。

### 4.2 后端：来源与快照（T1，`sources.py`）

1. **`_eligibility`**：按 §3 第 1 条重写。`canonical_bible is None` 先判；`book.get('chapters_done') or 0` 小于 1 时判「作品还没有写好的章节」；最后，`editing` 为真或 `(book.get('config') or {}).get('_rearchive') is not None` 时判「作品正在修改，请稍后再试」。其余条件全部删除，不得出现按书 status 判断的分支。
2. **`_all_chapters(username, book)`**：
   - `maximum = book.get('chapters_done') or 0`。
   - 校验 `type(maximum) is int` 且 `0 ≤ maximum ≤ 300`，否则 409「作品章节范围无效」（不调用 `chapters_range`、不建项目）。
   - 只读第 1 到 `maximum` 章，返回 `(chapters, maximum)`。
   - 不再用 detail 里的章号求最大值。
3. **`_signature(book)`**：按 §3 第 3 条实现：`(book.get('bible_version'), book.get('chapters_done'), (book.get('config') or {}).get('_rearchive'), tuple((章号, 章status) for detail.chapters 里章号 ≤ chapters_done 的章))`。
4. **`_assemble_novel_snapshot`**：逻辑不变，范围随 `maximum` 变成 1..`chapters_done`。各章的 `status` 原样写进 manifest，包括 stale。
5. **`_compare_drift`**：
   - 当前章节只看 ≤ `book['chapters_done']` 的章（`_all_chapters` 已保证）。
   - 返回字典新增两个键：
     - `stale`：当前章号 ≤ `chapters_done`、状态为 stale 的章号，升序；
     - `chapters_done`：书的 `chapters_done`。
   - `state` 的判定不变。
6. **`source_status`**：`snapshot` 新增 `stale`：快照 manifest 里 `status == 'stale'` 的章号，升序；旧 manifest 没有这种章时为 `[]`。
7. **`_candidate`**：
   - 返回字典新增 `stale`，即 detail 里章号 ≤ `chapters_done`、状态为 stale 的章号，升序。
   - `projects` 查询改为 `LEFT JOIN studio_snapshots s ON s.project_id=p.id AND s.no=p.snapshot_no`，每项新增 `snapshot_chapters`（`s.chapters`，没有快照时为 None）。其余字段与排序不变。
8. 注释、docstring 和字符串里不得出现 `from|into|update|join` 后紧跟 `novels` 或 `novel_` 的文字（大小写不限），否则 AST 锁 `:504` 会失败。

### 4.3 后端：续拆（T2–T6）

**辅助函数**（`breakdown.py`，供下文使用）：

- `_covered_through(breakdown)`：`imported` 里有整数 `_covered_through` 就用它；否则取 `imported['_manifest']['chapters']` 的最大章号。
- `_chapter_basis(breakdown)`：`imported` 里有 `_chapter_basis` 就用它；否则由 `imported['_manifest']['chapters']` 生成 `{str(章号): {snapshot_no: breakdown.snapshot_no, sha256, title, status}}`。
- `_published_max_seq(breakdown, units)`：`imported` 里有整数 `_published_max_seq` 就用它；否则取 `units` 的最大 seq（没有单元时为 0）。
- `_continuing(breakdown)`：`imported` 里 `_continuations` 非空，且拆解状态为 running 或 partial。

**T2 切批**（`breakdown_material.py`）

`batch_plan` 增加三个关键字参数：`start_chapter=1`、`segment_base=0`、`no_base=0`。

- 用默认值调用时，输出必须与现在**逐字节相同**，既有测试照常通过。
- `start_chapter > 1` 时：
  - 只为 `entries` 里章号 ≥ `start_chapter` 的章切批。
  - 章的段号 = `segment_base + (章号 - start_chapter) // 10`。
  - 同段内切批规则不变：最多 10 个片段、24000 字，同章不同片段不同批，换段必须换批。
  - 第 s 段的 `episode_plan`：
    - `chapter_from = start_chapter + (s - segment_base) * 10`；
    - `chapter_to = min(chapter_from + 9, entries 里最大章号)`；
    - 依赖本次计划内段号 ≤ s 的全部补全批，加上本次计划内的上一个 `episode_plan`。
  - 标签格式与现有一致：「第 x–y 章 · 补全」「第 x–y 章 · 分集」，单章写「第 x 章 · …」，按现有写法。
- **批号偏移**：内部仍按 1 起的本地序号切批、建依赖、用 `chunks[number - 1]` 取下标；在函数返回前统一给每批的 `no`、`depends` 里的每个编号、`source.map_nos` 里的每个编号加上 `no_base`。中间步骤不得用偏移后的编号作下标。
- 次要来源（非小说）不支持这三个参数取非默认值：传了就抛 `ValueError`。

**T3 续拆报价**（`breakdown.py` 新增 `continue_quote(pid, owner)`；路由 `POST /studio/projects/{pid}/breakdown/continue/quote`，无请求体或空对象，门控与现有 quote 相同）

1. **找当前快照与拆解**：
   - 读项目的当前快照。没有快照、或不是小说来源：409「只有小说工坊来源可以续拆」。
   - 读 `project.breakdown_id` 对应的拆解。没有拆解：409「还没有拆解，请先拆解」。
2. **检查拆解状态**：
   - 已退役（`_retired`）：409「拆解已被替代或取消」。
   - 状态不是 done：409「拆解尚未全部完成，不能续拆」。
   - 本拆解组里有 job 的状态在 `uncertain/running/submitting/submitted/queued` 之中：409「拆解还有未结束的批次」。
3. **已覆盖到哪一章**：`covered = _covered_through(breakdown)`。
4. **检查有没有新章**：当前快照的最大章号 `last` 不大于 `covered` 时，409「没有新写好的章节可以续拆，请先在来源面板同步」。
5. **切批**：
   - 用 `_locked_snapshot(pid, owner, 当前快照号, indices=range(covered+1, last+1))` 读出新章。
   - 调 `batch_plan(manifest, entries, start_chapter=covered+1, segment_base=现有批 source.segment 的最大值+1, no_base=现有批 no 的最大值)`，只取 plan，丢弃它返回的 imported。
   - 不做 `target_episodes` 的依赖改写。
6. **报价单**：
   - 每批报价照 `_make_quote` 的做法。没有现成输入的 `episode_plan` 按 `estimate_units*400` 字估。时长取拆解 settings 里的 `episode_seconds_min/max`。
   - 导演模型用 `project.brain_provider`，经 `_option` 检查可用性。
   - 额度检查照 `quote` 的写法。
   - 写入报价，`kind='breakdown_continue'`，内容包括：`breakdown_id`、`snapshot_no`、`covered_through=covered`、`continue_from=covered+1`、`continue_to=last`、`provider`、`settings`（拆解 settings，`target_episodes` 为 None）、`plan`、`items`。
   - 返回 `_public_quote(...)`，再加上 `continue_from`、`continue_to` 两个字段。

**T4 续拆确认**（`breakdown.py` 新增 `continue_start(pid, owner, quote_id)`；路由 `POST /studio/projects/{pid}/breakdown/continue/start`，请求体 `{quote_id}`，与 `BreakdownStartBody` 相同）

快照文件可以在事务外或用独立连接读取（`start` 是在事务块里用 `_locked_snapshot` 读的，两种都可以）。项目行、拆解行、批、job 和旧 `imported` 必须在 `BEGIN IMMEDIATE` 之后用同一连接重新读取，并以这份为基准合并写回；全部校验都在这个写事务里完成。按顺序做：

1. **校验**（顺序固定，不得调换）：
   1. 报价存在，且 `kind == 'breakdown_continue'`，否则 409「报价用途不匹配」。
   2. `project.breakdown_id == 报价.breakdown_id`、拆解未退役、状态为 done，否则 409「拆解已更新，请重新报价」。
   3. 组里没有 `uncertain/running/submitting/submitted/queued` 的 job，否则 409「拆解还有未结束的批次」。
   4. `project.snapshot_no == 报价.snapshot_no`，否则 409「作品快照已更新，请重新报价」。
   5. `_covered_through(拆解) == 报价.covered_through`，否则 409「拆解已更新，请重新报价」。

   同一报价第二次确认时，第 2 步就会命中（拆解已是 running），返回「拆解已更新，请重新报价」。
2. **确认报价**：`_confirmed_quote(db, quote_id, pid, owner, 'breakdown_continue')`，复核额度、只确认一次、过期拒绝。
3. **更新拆解的 imported**（下文第 6、7 步操作的是同一个 dict）：
   - 读新快照的完整 manifest。
   - 续拆前先记下：`pre_max_seq` = 本拆解现有单元的最大 seq；`pre_bible_ids` = 本拆解 `studio_bible` 的全部 id。
   - 从旧 imported 出发：用 `structured_import(新 manifest)` 返回的所有不以 `_` 开头的键覆盖同名键；所有以 `_` 开头的键保留。
   - 再写入：
     - `_chapter_basis`：先取 `_chapter_basis(旧拆解)`（旧拆解没有这个键时由旧 `_manifest` 生成）；再为新 manifest 里章号 > `covered` 的章补记 `{snapshot_no: 报价.snapshot_no, sha256, title, status}`。已有的章一律不覆盖。
     - `_manifest = 新 manifest`；
     - `_covered_through = 报价.continue_to`；
     - `_published_max_seq`：不存在时设为 `pre_max_seq`；存在时不动；
     - `_frozen_bible_ids`：不存在时设为 `pre_bible_ids`（升序）；存在时取并集；
     - `_continuations` 列表追加一项 `{round, snapshot_no, from, to, quote_id, started_at, pre_max_seq}`，round 从 1 开始；
     - `_published_chunk_ids` 不存在时，设为当前所有 succeeded 的 `episode_plan` 批 id。这一步兼容本功能之前已发布的拆解。
   - **不改** `synopsis_json`，作者可能编辑过梗概；**不改** `settings_json`。
4. **给旧批记快照号**：没有 `source.snapshot_no` 的现有批，在 `source_json` 里补上 `snapshot_no = 旧拆解.snapshot_no`。
5. **新建批与 job**：按报价 plan 新建，做法照 `start`：
   - 预留费用；
   - `source` 带 `_item`、`snapshot_no=报价.snapshot_no`、`round`；
   - 依赖按报价 plan 里的 no 映射成新批 id；
   - 有依赖的标 blocked，否则 queued。
6. **单元与总表**：
   - 用现有批加新批调用 `_materialize`。现有 succeeded 批的 `inputs` 取各自 job 的 `params.inputs`，做法同 `refresh` 的物化分支；物化 warning 照 `refresh` 写进 `_chunk_material_warnings`。
   - 再 `_insert_units`，并把 `_materialize` 的总表交给 `_insert_bible`。
   - 必须满足：旧单元（seq ≤ `pre_max_seq`）的 `label/chapter/scene_index/start/end` 逐字段不变；新章的结构化单元接在后面。
   - **`_insert_bible` 的「沿用已有条目」规则**，只在 `breakdown['imported'].get('_continuations')` 非空时生效（未续拆过的拆解行为不变，既有 `test_studio_breakdown_*` 不受影响）；对 `continue_start` 和之后每一次 `refresh` 里的 `_insert_bible` 都生效：
     1. `key = kind + ':' + (ref_id or name)`，`derived = uuid5(拆解id, key)`；别名表 `alias = imported.setdefault('_bible_id_alias', {})`。
     2. 决定 identifier，按顺序：
        1. `alias[key]` 存在，且那一行仍属于本拆解、`archived=0`、`merged_into IS NULL`：用它。
        2. `derived` 这一行已存在于本拆解：用 `derived`。
        3. 否则在本拆解的活动行（`archived=0 AND merged_into IS NULL`，同 kind）里找匹配：两边都有 ref_id 时必须相等；否则行的规范化 `{name} ∪ aliases` 与条目的规范化 `{name} ∪ aliases` 相交即匹配（`normalize_name` 与现有退役循环一致）。作者新建的 uuid4 行、作者改过名的行（旧名已在 aliases 里）都参与匹配。
           - 恰好一行匹配：identifier = 那一行的 id，并写 `alias[key] = 该 id`；
           - 没有匹配：identifier = `derived`，照现在插入新行；
           - 多于一行：identifier = `derived`，照现在插入新行，并往 `_bible_merge_warnings` 追加「{name} 与总表里多个同类条目重名，请手动合并」。
     3. 先处理 identifier 等于 `derived` 的条目，再处理转向的条目（identifier ≠ `derived`）。转向条目对目标行只补空值：`ref_id` 为空时补上；`role/description/excerpt` 为空时补；`appearance` 照现有规则只在为空且非作者来源时补；`first_unit` 只在为 NULL 时补；`aliases_json` 取并集（目标行原有别名在前，再加新出现、且不等于目标行 name 的别名），`'aliases'` 在作者编辑里时不动；**不改 name**。多个条目转向同一行时依次照此合并。
     4. 退役循环：`_frozen_bible_ids` 里的行、`alias` 的值里的行一律跳过，不写 `merged_into`。
7. **更新拆解行**：`UPDATE studio_breakdowns SET snapshot_no=新快照号, outdated=0, status='running', import_json=…, updated_at=…`。`import_json` 写的就是第 3、6 步改过的那个 dict（`_insert_bible` 中途也会写回它）。**不改** `project.breakdown_id`、`plan_revision`、`plan_approved_revision`，不删任何集。
8. 提交后调度不依赖其他批的新 job。返回 `get_current(pid, owner)`。

**T5 读原文、分集输入、刷新、发布与取消**（`breakdown.py`）

1. **`_source_inputs`**：读原文用 `chunk['source'].get('snapshot_no') or breakdown['snapshot_no']`。
2. **`_dependency_input`** 增加可选参数 `published_last=None`。`round = chunk['source'].get('round') or 0`：
   - `round ≥ 1` 时一律不计算、不写 `suggested_episodes`，不管拆解 settings 里有没有 `target_episodes`。
   - `round ≥ 1`、且本轮（`source.round` 相同）没有 no 更小的 `episode_plan` 批时，`previous_episode = published_last`（可以是 None）；本轮后续的段照旧取本轮上一批的输出。
   - `round` 为 0 时行为完全不变。
   - `prepare_job` 与 `retry_quote` 在上一条成立时，读 `SELECT title,unit_from,unit_to,change,hook FROM studio_episodes WHERE breakdown_id=? ORDER BY no DESC LIMIT 1`，作为 `published_last` 传入；没有集时传 None。
3. **`refresh`**：
   - 发布段（`:578-588`）改为按 `imported.get('_continuations')` 分两条路，两条路都只在拆解未退役时发布：
     - **没有续拆过**：
       - 保持现状。
       - 每次真正调用 `publish_plan` 后，把 `imported['_published_chunk_ids']` 设为这次参与拼接的 succeeded `episode_plan` 批 id。
     - **续拆过**：
       - 不再走「拼接全部模型输出」那条路。
       - 当 `status == 'done'`，且存在不在 `_published_chunk_ids` 里的 succeeded `episode_plan` 批时：
         1. `existing`：从 `studio_episodes` 按 no 读出本拆解当前的全部集。每集取字段 `title, unit_from, unit_to, change, hook, target_min, target_max, notes`。
         2. `new`：上述批按 no 排序，依次拼接各自 `output['episodes']`。
         3. 调用 `publish_plan(db, bid, existing + new, reason='continued')`。
         4. 把这些批 id 追加进 `_published_chunk_ids`。
         5. 本轮第一个新单元 `first_new = _continuations[-1]['pre_max_seq'] + 1`：`_appended_from_unit` 为 null 或不存在时设为 `first_new`；已有值时取两者中较小的那个，不覆盖。
         6. `_published_max_seq` 设为当前单元的最大 seq。
       - `status == 'partial'` 时不发布。
4. **`cancel(bid, owner)`**：`imported` 里有 `_continuations`、且拆解状态是 running 或 partial 时，返回 409「续拆进行中不能取消，可以等它完成或单批重跑」，什么都不改。**这个守卫只放在 `cancel()` 里，不得放进 `_cancel_unexecuted`**：整本重新拆解（`start`）在续拆 running/partial 时仍要能取消本轮未执行的批并释放预留。

**T6 视图**

1. **`breakdown.get_current`** 的返回字典新增以下键：
   - `covered_through`：`_covered_through(breakdown)`。
   - `continuable`：同时满足以下条件才为真：
     - 当前快照是小说来源；
     - 拆解未退役、状态为 done；
     - 组里没有 `uncertain/running/submitting/submitted/queued` 的 job；
     - 当前快照（`studio_snapshots` 里 `project.snapshot_no` 那一行）的 `chapters` 大于 `covered_through`。
   - `continue_from` / `continue_to`：`continuable` 时分别为 `covered_through + 1` 与当前快照的 `chapters`，否则为 null。
   - `changed_covered`：不看快照号是否相等。取章号 ≤ `covered_through` 且满足以下任一条件的章，升序：
     - 当前快照 manifest 里这一章的 `title` 或 `sha256` 与 `_chapter_basis` 里记的不同；
     - 这一章已不在当前快照里。
   - `stale_chapters`：`_chapter_basis` 里 `status == 'stale'` 的章号，升序（这些章拆解时就是待复核）。
   - `continuations`：`_continuations` 每项的 `{round, from, to, snapshot_no}`，没有续拆过时为 `[]`。
   - `continuing`：`_continuing(breakdown)`。
2. **`breakdown_plan.get_episodes`** 返回字典新增：
   - `continuing`：已发布拆解的 `_continuing(...)`。
   - `appended_from`：方案 `g0_approved` 为真、或 `imported['_appended_from_unit']` 不是整数时为 null；否则为第一个 `unit_to ≥ _appended_from_unit` 的集的 no，没有这样的集时为 null。
   - `continuing` 为真时，交给 `_present_episodes` 的单元只取 `seq ≤ _published_max_seq(...)` 的那些，所以 `units` 与 `unassigned` 都不含本轮新章的单元。`export_markdown` 同样过滤。
3. **`breakdown_plan.approve`**：批准成功后，在同一事务里把已发布拆解 `import_json` 中的 `_appended_from_unit` 置为 null。

### 4.4 前端（T7）

所有新文案用普通字重，不加粗；不新增颜色或字号令牌；复用现有类名。**本任务新增的每个元素都带 `data-serial` 属性**（值为空串），供测试定位；这些元素自身和它们的祖先都不得带 `font-medium/font-semibold/font-bold` 类，也不得是 `<b>`/`<strong>`。

1. **`frontend/lib/studio-breakdown.ts`**：
   - `StudioBreakdown` 类型补 `covered_through: number; continuable: boolean; continue_from: number | null; continue_to: number | null; changed_covered: number[]; stale_chapters: number[]; continuations: { round: number; from: number; to: number; snapshot_no: number }[]; continuing: boolean`。
   - `StudioEpisodePlan` 补 `appended_from: number | null; continuing: boolean`。
   - `BreakdownQuote` 补可选 `continue_from?`、`continue_to?`。
   - 新增 `quoteStudioContinuation(id, signal?)` 与 `startStudioContinuation(id, quoteId, signal?)`，分别 POST `${project(id)}/breakdown/continue/quote`（请求体 `{}`）与 `…/continue/start`（请求体 `{quote_id}`）。
   - 新增 `formatChapterRanges(nos: number[]): string`：与 `formatEpisodeRanges` 同样合并连续号，输出「第 3–5、8 章」；单个写「第 3 章」；空数组返回空串。
2. **`frontend/lib/studio.ts`**：drift 类型补 `stale?: number[]; chapters_done?: number`；来源快照类型补 `stale?: number[]`；候选类型补 `stale?: number[]`，`projects` 每项补 `snapshot_chapters?: number | null`。
3. **`BreakdownPanel.tsx`**：
   - **续拆块**：`breakdown.continuable` 为真时，在现有 outdated 提示的位置**改为**显示续拆块（这种情况下 outdated 块不显示）。外层沿用 outdated 块的容器类。依次显示：
     1. `<p>已拆到第 {covered_through} 章；作品已同步到第 {continue_to} 章，可以续拆第 {continue_from}–{continue_to} 章。</p>`；只多一章时写「可以续拆第 {continue_from} 章。」。
     2. `<p>续拆只为新增章节付费，已拆的部分、你改过的分集和已定的妆都保留；续拆完成后分集方案要重新批准一次。</p>`
     3. 按钮：
        - 主按钮「续拆第 {from}–{to} 章」：`btn btn-primary min-h-10`，只多一章时写「续拆第 {from} 章」；`disabled={busy || active || providers.find(item => item.id === project.brain_provider)?.available === false}`，不受时长输入框是否合法影响；点击调用新的 `onContinue` 回调。
        - 次按钮「重新拆解」：沿用 outdated 块里原按钮的写法和回调，表示整本重拆。
   - **改过的旧章**：`changed_covered` 非空时，不管 `continuable`，都显示 `<p className="text-fs-13 text-[color:var(--ink2)]">{formatChapterRanges(changed_covered)}在拆解之后改过，续拆不会重拆它们；需要时可以整本重新拆解（会生成新的总表，已定的妆要重新定）。</p>`。续拆块显示时放在块内第 2 句之后；否则放在拆解状态行下方。
   - 在拆解状态行附近，另外满足条件时显示（都用 `text-fs-13 text-[color:var(--ink2)]`）：
     - `stale_chapters` 非空：「{formatChapterRanges(stale_chapters)}拆解时在书斋里标为待复核，拆解按快照里的原文进行。」
     - `continuations` 非空且状态为 done：「已续拆 {continuations.length} 次，拆到第 {covered_through} 章。」
     - `continuing` 为真：「正在续拆第 {最后一项 from}–{最后一项 to} 章。」（单章写「第 {from} 章」）
   - **取消**：`breakdown.continuing` 为真时，不渲染「取消拆解」按钮，原位置显示 `<p className="text-fs-13 text-[color:var(--ink2)]">续拆进行中不能取消，失败的批次可以单批重跑。</p>`。`continuing` 为假时取消按钮与确认框照旧。
   - **续拆 partial**：`continuing` 为真且状态为 partial 时，在「以下批次需要重跑」之后再显示：「续拆有批次未完成：完成前不能同步新章，也不能修改或批准分集方案。单批重跑读的是本轮的快照，在书斋里改原文对重跑无效；重跑仍失败时，只能整本重新拆解（会生成新的总表，已定的妆要重新定）。」
4. **`BreakdownStage.tsx`**：
   - 接上 `onContinue`：`direct(() => mutate(async signal => { const result = await quoteStudioContinuation(id, signal); if (!signal.aborted) setQuote({ value: result, continueRange: { from: result.continue_from!, to: result.continue_to! } }); }, "报价已就绪，请核对后确认。"))`。续拆的 quote 状态**只放** `value` 与 `continueRange`，不放 `settings/affectsApproved/replacesPartial`；范围取自报价响应，不取拆解视图。
   - `:103` 确认分支加第三支：`chosen.continueRange` 为真时调 `startStudioContinuation(id, chosen.value.id, signal)`，成功提示「续拆已开始。」，然后照整本报价刷新拆解与分集。
   - 给 `BreakdownQuoteDialog` 传 `continueRange={quote.continueRange}`。
   - 给 `EpisodePlan` 传 `continuing={!!breakdown.continuing}`。
   - 错误处理（409 显示后端原文并刷新）、忙碌态、账号请求作用域照现有整本报价的写法。
5. **`BreakdownQuoteDialog.tsx`**：新增可选 prop `continueRange?: { from: number; to: number }`。传入时：
   - 标题为「续拆报价」，确认按钮为「确认续拆」；
   - `:17`、`:18`、`:19` 三条的条件都改为 `!retry && !continueRange && …`，即使同时传了 `targetMin/targetMax` 也不显示；
   - 在 `:20` 之前加三句（各一个 `<p data-serial="">`）：
     - 「只拆第 {from}–{to} 章。」；只有一章时写「只拆第 {from} 章。」（批数由 `:20` 的「共 N 批」给出，这句不再重复）。
     - 「新增的集会追加到分集方案末尾，方案会退回待批准。」
     - 「确认后不能取消；有批次失败时可以单批重跑。」
   - 价格、倒计时、确认流程不变；不传 `continueRange` 时输出与现在完全相同。
6. **`EpisodePlan.tsx`**：
   - 新增可选 prop `continuing?: boolean`。为真时，`:71` 那句改为「续拆进行中，完成后新增的集会追加到方案末尾，已有的集保持不变；完成前暂不能修改或批准分集方案。」；为假时原句不变。
   - `appended_from` 非 null 时：
     - 方案汇总下加一行 `<p role="status" data-serial="">第 {appended_from}–{最后一集编号} 集是这次续拆新增的，看过后重新批准分集方案。</p>`；只新增一集时写「第 {n} 集是…」。
     - 每个编号不小于 `appended_from` 的集加 `<span className="tag" data-serial="">新增</span>`：卡片视图里放在 `<h3>` **外面**（把 h3 和标签包进一个 `<div className="flex min-w-0 items-center gap-2">`）；表格视图放在标题 `<td>` 里 `{episode.title}` 之后。
7. **`SourcePanel.tsx`**：
   - `studioDriftSummary`：`drift.stale` 非空时，在现有各部分之后追加「{formatChapterRanges(stale)}待复核」（只出现在 changed 时的摘要里）。
   - `source.kind === "novel"` 且 `source.snapshot?.stale` 非空时，不管 `drift.state` 是什么（含 unchanged、unavailable），在快照信息下方显示 `<p className="text-fs-13 text-[color:var(--ink2)]">快照中{formatChapterRanges(stale)}待复核。</p>`。
   - 连载提示：条件为 `source.kind === "novel" && typeof drift?.book_status === "string" && drift.book_status !== "completed"`，显示 `<p className="text-fs-13 text-[color:var(--ink2)]">作品还在写，同步只收已写好的章节。</p>`。非小说来源、drift 为 not_applicable/unavailable 或还没加载时都不显示。
8. **`SourceChoices.tsx`**：
   - 新增导出组件 `SerialSourceHints({ book }: { book: StudioNovelCandidate })`，按顺序渲染（都用 `text-fs-13`，普通字重）：
     - `book.stale` 非空：「{formatChapterRanges(stale)}待复核，会照常收进快照。」
     - `book.status !== "completed"` 且 `book.eligible`：「连载中，只收已写好的 {chapters_done} 章。」
     - 两条都不成立时返回 null。
   - `NovelSourceChoice` 在原因行下方渲染 `<SerialSourceHints book={book} />`。
   - `ExistingSourceProjects`：某项 `snapshot_chapters` 为整数、且小于候选的 `chapters_done` 时，在这一项后面加「快照到第 {snapshot_chapters} 章，到来源面板同步后可以续拆」。为此给 `ExistingSourceProjects` 增加可选 prop `chaptersDone?: number`，两处调用方都传 `book.chapters_done`；不传时输出与现在相同。
9. **`NovelFilmDialog.tsx`**：`:48` 在 `SourceFlags` 之后渲染 `<SerialSourceHints book={book} />`，`ExistingSourceProjects` 传 `chaptersDone={book.chapters_done}`；导入随之调整。其余不动。
10. **`CreateProjectDialog.tsx:69`**：空态整句替换为「没有找到符合书名的作品。只有有故事圣经、至少写好一章、且不在修改中的作品可以导入；连载中的书只收已写好的章节。」
11. **`NovelWorkbench.tsx`**：
    - 在 `:82` 之后、`:83` 的 effect 之前新增 `const filmReady = (book?.chapters_done ?? 0) >= 1;`。
    - `:83-92` 的工作室权限检查改为以 `filmReady` 为条件，依赖数组改为 `[beginStudio, filmReady]`（不得产生 `react-hooks/exhaustive-deps` 告警）。
    - `:294` 工具栏的「做成片」按钮和 `:322` 的 `NovelFilmDialog` 改用 `filmReady && studioAllowed`。
    - `:300` 传给 GateBanner 的 `onMakeFilm` 保持 `completed && studioAllowed` 不变。
    - `GateBanner.tsx` 不动。
12. **`NovelFeedbackCard.tsx:397`**：只把「，有待复核章节的书不能做成片；」改为「（短片工作室照收，会标出待复核）；」，这段其余文字不动。

### 4.5 聊天文案（T8）

1. `backend/services/claude_agent.py:125` 的描述改为「将小说建立短片工作室项目与快照，连载中的书只收已写好的章节；已有项目时直接打开，不会自动同步新章；免费。」
2. `backend/services/claude_agent.py:845`：只把「、不能做成片，」改为「（短片工作室照收，会标出待复核），」，这句其余文字不动。
3. `backend/intent_router.py:148` 改为「  novel_to_film  把小说建立短片工作室项目（连载中的书只收已写好的章节） params: book(书名)」。保持原有缩进和前后行不变。
4. `backend/studio/novel_chat.py` 的 `start_film`：新建项目的分支，卡片输出不变。复用已有项目（`projects[0]`）的分支，`points` 改为：
   1. 「《{title}》」；
   2. `snapshot_chapters` 为整数时「快照第 {snapshot_no} 版 · {snapshot_chapters} 章」，否则「快照第 {snapshot_no} 版」；
   3. 只在 `snapshot_chapters` 为整数且小于候选的 `chapters_done` 时：「作品已写到第 {chapters_done} 章；到工作室来源面板同步后可以续拆」；
   4. 「已有项目，打开即可继续」。
5. `backend/.env.example:231` 改为「# 作品来源：小说工坊作品（连载中的书只收已写好的章节）、txt/md/docx、粘贴文本、本人短视频创意搭档成稿。」

### 4.6 测试（T9）

1. **既有测试的授权改动**（只限下列内容；任何其他既有测试变红都必须停下来说明，不得修改；既有测试文件的收集数保持不变，不得拆分或合并参数化用例）：
   - `test_studio_sources.py::test_eligibility_rejects_with_reason`（`:136-153`）：保留六个参数 id 与签名，改函数体：
     - `running`、`planning`、`stale` 三个参数改为断言**可以**建项目：候选 `eligible` 为真，`POST /studio/projects/from-novel` 返回 201，项目已建。`planning` 的输入改为真实形状：在 `state['book']['chapters']` 和 `state['chapters']` 各追加第 3 章 `{'chapter': 3, 'title': '下一章', 'status': 'planning'}`（`state['chapters']` 那条再加 `'body': None`），`chapters_done` 保持 2；另断言 manifest 只有第 1–2 章、`state['range_calls'] == [(1, 2)]`。`stale` 参数另把 `state['chapters'][0]['status']` 也设为 stale（manifest 的章状态取自 `chapters_range` 的返回，真实情况下两边一致），并断言 manifest 第 1 章 `status == 'stale'`。
     - `bible`、`editing` 照旧断言 409、不建项目，期望子串分别为「故事圣经」「正在修改」。
     - `empty` 的输入改为 `state['book'].update(chapters_done=0, chapters=[])`，期望子串改为「还没有写好的章节」，断言 409、不建项目。
   - `test_candidate_flags_projects_and_exact_title_search`（`:177-179`）：最后一步改为 `state['book'].update(title=None, status='setup_running', chapters_done=0, chapters=[])`，并补断言 `untitled['reason'] == '作品还没有写好的章节'`。
   - `test_consistent_snapshot_retries_once`（`:182-193`）：扰动改为第 2 次 detail 起 `result['bible_version'] = state['book']['bible_version'] + 1`（不要用 `chapters_done` 加 1，夹具没有第 3 章正文，会报「第 3 章正文缺失或为空」）；保留 `details == 4` 与读了两轮；最后一行改为断言 `manifest['book']['bible_version'] == 4`。原意（只读到一次不一致就重试一次）保留，§4.6 第 2 条「只改 updated_at 一次成功」是替换它旧语义的新用例。
   - `test_continuous_change_rejected`（`:196-207`）：扰动改为每次 detail `result['bible_version'] = 100 + state['details']`；期望仍是 409「作品正在修改，请稍后再试」、读了两轮。
   - `test_sync_rejects_ineligible_and_busy_brain`（`:261-275`）：前半段的不合格输入改为 `state['bible'] = None`，期望子串「故事圣经」；然后恢复原 bible，后半段「导演模型任务进行中，完成后再同步」不动。
   - `:243` 的漂移精确字典：补上 `'stale': [], 'chapters_done': 3`。
   - `test_studio_sources_frontend.py:118` `test_incomplete_workbench_never_requests_studio`：改为「`chapters_done` 为 0 的书不请求工作室、不显示做成片」。原意图保留：没有可拆内容时不发请求。
   - `test_novel_chat.py:116`：复用分支的期望改为 `["《春山》", "快照第 2 版", "已有项目，打开即可继续"]`（桩里没有 `snapshot_chapters`），其余断言不动。
   - `test_novel_chat_feedback.py:35-39` 的 `WRITTEN_SENTENCE` 与 `test_novel_chat_feedback_frontend.py:251-258` 的 `WRITTEN_DESCRIPTION`：只随 §4.5 第 2 条、§4.4 第 12 条改那半句，其余字符与断言不动。
   - 既有测试如果只因为本规格新增的响应字段而失败（拆解视图、漂移、来源快照、候选及其 projects、分集方案），只允许在期望里**补上新字段的正确值**，不得删除或放宽其他断言。在报告里逐条列出改了哪些。
2. **新测试 `test_studio_serial_sources.py`**（用 `test_studio_sources` 的 `workshop` 夹具）：
   - 资格：
     - running、awaiting_plan、paused、failed、setup_running 状态且 `chapters_done ≥ 1` 的书都可以建项目。
     - 有 stale 章的书可以建项目，manifest 里该章 `status == 'stale'`（夹具里 detail 的章与 `state['chapters']` 两边都要设）。
     - 三种拒绝原因逐一核对。
     - detail 的 config 带 `_rearchive` 时：候选不可选、原因「作品正在修改，请稍后再试」，建项目与同步都 409，drift 的 `eligible` 为假。
     - `chapters_done` 为 301 或 `True` 时 409「作品章节范围无效」，不建项目，`range_calls` 为空。
   - 快照范围：逐章确认的书有第 `chapters_done+1` 章的进行中行（正文为 NULL）时，快照只收第 1 到 `chapters_done` 章，不报「正文缺失」，`state['range_calls'] == [(1, chapters_done)]`。
   - 签名（每条都断言 `state['details']` 的值）：
     - 两次 detail 之间只改 `updated_at`（模拟计费）时，快照一次成功（`details == 2`）。
     - 两次之间 `bible_version` 变化 → 重试（`details == 4`）。
     - 两次之间章号 ≤ `chapters_done` 的一章 done→stale → 重试。
     - 第二次 detail 才出现 `config._rearchive` → 重试后因资格不符 409「作品正在修改」。
     - 只改章号 > `chapters_done` 的行（planning→writing、改标题）→ 不重试（`details == 2`）。
   - 漂移：
     - 进行中的行不进入 `added`；
     - `stale` 与 `chapters_done` 正确；
     - 连载书同步后快照号加 1。
   - 来源状态：`snapshot.stale` 正确；旧快照没有 stale 章时为 `[]`。
   - 候选：`stale` 正确；`projects[0].snapshot_chapters` 等于快照章数。
   - 分身做成片（`novel_chat.start_film`，照 `test_novel_chat.py` 的门控桩）：连载书写到第 3 章、已有项目快照 2 章时，卡片四行与 §4.5 第 4 条逐字一致；快照章数等于 `chapters_done` 时没有第 3 行。
3. **新测试 `test_studio_serial_continue.py`**（夹具见 §2.4：`workshop/novel_project/sql` 建小说来源与同步，integration 的 `Adapter` 与 `_background` 驱动执行，pipeline 的额度环境变量）：
   - **切批**：
     - `batch_plan` 默认参数的输出，与改动前用同一输入算出的结果逐项相等。
     - `start_chapter=6、segment_base=1、no_base=N` 时：只含第 6 章及以后，段号与 no 正确；`depends` 与 `map_nos` 都落在 `N+1..N+len(plan)` 内，且依赖指向的批 task 正确；`episode_plan` 的章范围正确。
     - 次要来源传非默认参数时抛 `ValueError`。
   - **报价拒绝**：以下每种情况各一条，分别断言文案并确认没写报价：
     - 不是小说来源；
     - 没有拆解；
     - 拆解退役；
     - 拆解不是 done；
     - 有未结束的 job；
     - 没有新章。
   - **报价内容**：只含新章的批；`continue_from/continue_to` 正确；原拆解填过 `target_episodes` 时，报价的依赖与 settings 都不受它影响。
   - **确认**：
     - 报价用途、拆解已更新、快照已更新、`covered_through` 变化，各种情况都 409，且没有建批、没有扣预留。
     - 同一报价第二次确认：409「拆解已更新，请重新报价」，组内 job 数与预留总额不变。
     - 成功后：
       - `breakdown.snapshot_no` 为新快照号，`outdated == 0`，状态为 running；
       - 旧批都补上了 `source.snapshot_no`；
       - 新批的 `snapshot_no` 与 `round` 正确；
       - 旧单元逐字段不变；
       - `_chapter_basis` 里旧章的记录不变、新章已补记；
       - 旧总表条目的 id 不变，新角色得到新条目；
       - `project.breakdown_id`、`plan_revision`、`plan_approved_revision`、`settings_json` 不变。
   - **执行**：
     - 原文：快照 1 拆第 1–5 章，快照 2 改第 3 章正文并加到第 8 章；续拆成功后，把第 3 章所在旧补全批 job 的 `params_json` 改成 `{"inputs":{},"breakdown_chunk":<该批 id>}`，再 `await _source_inputs(拆解, 该旧批)`，断言正文等于快照 1 的第 3 章；让本轮一个新补全批成功、触发 refresh 后，旧单元的 `start/end/label` 不变。新批读到的是快照 2 的原文。
     - 建议集数：原拆解 `settings.target_episodes=20`，续拆后本轮 `episode_plan` 的 `job.params.inputs` 里没有 `suggested_episodes`；对同一批调 `retry_quote`，报价输入同样没有；原轮次 `episode_plan` 的输入不变。
     - 衔接：续拆前把已发布方案最后一集的 `title/hook` 改掉，本轮第一个 `episode_plan` 的 `params.inputs.previous_episode` 是改后的值；删掉最后一集时取新的末集；本轮第二个 `episode_plan` 仍取本轮上一批的输出。
   - **总表沿用已有条目**（每条都在续拆确认后、以及本轮新补全批成功触发 refresh 后各断言一次：同 kind 同名活动行只有一条、原条目不是孤儿、本拆解没有新的 `merged_into`）：
     - 续拆前补全批识别出无 ref_id 的新人物「阿禾」并已选定定妆；快照 2 的圣经把阿禾登记为 `ref_id='C2'`。续拆后原条目 id 不变、`ref_id == 'C2'`，`casting.is_orphaned` 为假。
     - 作者把「阿禾」改名为「禾生」后续拆，新批输出 `new_characters=[禾生]`。
     - 作者用 `create_bible` 新建「船夫」后续拆，新批输出 `new_characters=[船夫]`。
     - 两个已有活动行都与新条目重名时：插入新行，并出现「与总表里多个同类条目重名」的 warning。
   - **发布**：
     - 续拆完成（done）后：方案 = 原有集 + 新集；原有集里作者改过的标题和备注逐字保留；新集编号接在后面；`plan_revision` 加 1；`g0_approved` 为假；`appended_from` 等于原集数 + 1。
     - 发布后、批准前，分别删除一个旧集、在旧部分补建一集、合并两个旧集、拆分一个旧集：「新增」仍只落在含新单元的集上（`appended_from` 随之变化）。
     - 本轮有批失败（partial）时不发布，方案与版本号不变；单批重跑成功后发布。
     - 批准后 `appended_from` 为 null。
     - 第二次续拆（第一轮已批准）：第二轮只追加第二轮的集。
     - 第一轮发布后**未批准**就做第二轮：两轮新增的集都标「新增」。
   - **续拆进行中的视图**：确认后、发布前，`get_episodes` 的 `continuing` 为真、`g0_approved` 仍为真，`units` 与 `unassigned` 都不含新单元；导出 Markdown 的「未纳入的单元」也不含；`casting.state` 里能看到新人物条目。
   - **续拆 partial**：让本轮一批失败、下游批 blocked：`operate_episodes`、`approve`、`continue_quote`、`sync_source` 都返回 409，G0 仍为已批准。
   - **取消与整本重拆**：
     - 续拆 running 与 partial（含 `recover_studio_jobs` 把 running 转成 uncertain 之后的 partial）时调 `cancel` 都返回 409，什么都不改；从未续拆过的拆解，取消行为不变。
     - 续拆 partial 时用整本报价调 `start()`：成功；本轮所有 queued/blocked 的 job 变 cancelled，`spend.committed`（当天）与 `brain_month_used` 不再计入它们的预留；旧拆解的 `superseded_by` 等于新拆解 id。
   - **兼容**：没有 `_covered_through/_chapter_basis/_published_chunk_ids/_published_max_seq` 的旧拆解，能按 `_manifest` 算出已覆盖章与依据，并正确续拆一次。
   - **视图**：`continuable`、`continue_from/to`、`changed_covered`、`stale_chapters`、`continuations`、`continuing` 各有正例与反例。其中 `changed_covered`：快照 2 改第 3 章并续拆，续拆后（快照号已相等）仍含 3；再同步出快照 3（第 3 章不变）仍含 3；把第 3 章改回快照 1 的原文后不再含 3。`stale_chapters`：拆解时待复核、后来在书斋改好的章，续拆后仍在列表里。
4. **新测试 `test_studio_serial_frontend.py`**（驱动见 §2.4；缺 node 或缺依赖时 skip，文案沿用「frontend dependencies unavailable: …」）：
   - **请求函数**：`quoteStudioContinuation('p')` 发 POST `/api/studio/projects/p/breakdown/continue/quote`，body `{}`；`startStudioContinuation('p','q')` 发 POST `…/continue/start`，body `{quote_id:'q'}`。
   - **`BreakdownStage` 接线**（照 `STAGE_SETUP` 与 `test_stage_quote_confirm_and_409_refresh`）：
     - 调 `named(page,'BreakdownPanel').props.onContinue()` 后，`named(page,'BreakdownQuoteDialog').props.continueRange` 等于报价里的 from/to，`targetMin`、`affectsApproved`、`replacesPartial` 都是 undefined 或 false；
     - 调 onConfirm 后，`posts[1].url` 以 `/breakdown/continue/start` 结尾，body 为 `{quote_id}`；出现「续拆已开始。」；
     - `continue/quote` 返回 409 时显示后端原文；
     - 切换账号（`env.owner='other'`）后 onContinue 不发请求；
     - `breakdown.continuing` 为真时传给 EpisodePlan 的 `continuing` 为真。
   - `BreakdownPanel`：
     - `continuable` 时出现续拆块、主按钮文字和「重新拆解」，不出现 outdated 块；只多一章时的写法；
     - `changed_covered` 句只在非空时出现，`continuable` 为假时也出现；
     - stale 行、已续拆行（只在 done）、正在续拆行（只在 continuing）各自只在条件满足时出现；
     - `continuing` 且 running/partial 时不出现「取消拆解」、出现「续拆进行中不能取消」；`continuing` 为假且 running 时照常出现「取消拆解」；
     - 续拆 partial 的说明句只在 continuing 且 partial 时出现。
   - `BreakdownQuoteDialog`：continue 模式的标题、确认按钮与三句；同时传 `continueRange` 和 `targetMin/targetMax/affectsApproved/replacesPartial` 时三条整本提示都不出现；不传 `continueRange` 时输出与改动前逐字相同。
   - `EpisodePlan`：
     - `<span class="tag" data-serial="">新增</span>` 在 `episode-table` 与 `episode-cards` 两个区域里各出现「新增集数」次，只落在编号不小于 `appended_from` 的集上；
     - 提示句只在 `appended_from` 非 null 时出现；
     - `continuing` 为真时出现续拆句、不出现「按新结果重新生成」；为假且 partial 时仍是原句。
   - `SourcePanel`：
     - changed 摘要里的「待复核」；
     - `snapshot.stale` 非空时，unchanged 与 unavailable 两种状态下都出现「快照中…待复核。」，为空时不出现；
     - 连载提示只在 `kind:'novel'` 且 `book_status` 不是 completed 时出现；`{kind:'paste', drift:{state:'not_applicable'}}` 和 `{kind:'novel', drift:{state:'unavailable'}}` 都不出现。
   - `SourceChoices` / `NovelFilmDialog`：stale 行、连载行、「快照到第 M 章…」各有正反例；`NovelFilmDialog` 渲染连载候选时出现前两行。
   - `CreateProjectDialog`：新空态整句。
   - `NovelWorkbench`（`NOVEL_DRIVER` + `screen`）：
     - `chapters_done ≥ 1` 的连载书请求工作室权限并显示「做成片」；
     - `chapters_done == 0` 时不请求；
     - 完结书的 GateBanner 行为不变。
   - `formatChapterRanges` 的输出（空、单个、连续、混合）。
   - **字重**：用 Python `html.parser` 解析上述每个会渲染新增元素的场景（BreakdownPanel、BreakdownQuoteDialog、EpisodePlan、SourcePanel、SourceChoices、NovelFilmDialog）的 SSR 输出，维护开放标签栈（void 元素 `area/br/col/embed/hr/img/input/link/meta/source/track/wbr` 不入栈）。对每个带 `data-serial` 的元素断言：它自身和栈里所有祖先都没有 `font-medium/font-semibold/font-bold` 类，且都不是 `b/strong`。每个场景先断言 `data-serial` 元素数大于 0，证明真扫到了东西。
5. 所有新测试离线、不依赖 git 历史、不读仓库外文件；每个用例用独立的临时库或用户。

### 4.7 文档（T10）

只在白名单里的四份文档内，搜索「已完结才可建项目 / 待复核不能做成片 / 同步后只能整本重新拆解 / 做成片只对已完结的书」这几类事实的全部陈述，逐处改对，并在报告里列出改过的每一处。已知位置：

- `CLAUDE.md`：186、192、194
- `README.md`：359、363、369、396
- `docs/ARCHITECTURE.md`：412、416、418、505、507

另外补写两处：

- `CLAUDE.md` WO3c 段末，加一段续拆说明，写清：
  - 适用范围与条件；
  - 新增的两个接口；
  - 同一份拆解追加、总表沿用已有条目、定妆保留；
  - 发布后需要重新批准，「新增」按单元标记；
  - 续拆进行中的行为（不能取消、旧 G0 有效、partial 时的出路）；
  - 不支持次要来源。
- `PLAN.md`：新开「2026-11-12 工作室续拆」一节，写做了什么、§3 第 11 条列出的不做事项，以及 §7 的已知局限。

### 4.8 R1 返修（2026-11-13，依据 r0 门禁、变异测试、走查与 Opus 复核 `04-review.md`）

r0 的实现代码经复核没有违反本规格之处。以下返修以补测试为主，另有五处小的产品改动。**R1 白名单**：`backend/studio/sources.py`、`backend/studio/breakdown.py`、`backend/studio/breakdown_plan.py`、`frontend/components/studio/BreakdownPanel.tsx`、`frontend/components/studio/EpisodePlan.tsx`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、三个新测试文件、`impl/report.md`、新文件 `impl/report-r1.md`。其他文件（含所有既有测试）一字不动。

**产品改动**

- **R1-P1 续拆进行中拒绝同步**：`sync_source` 里现有两处「导演模型任务进行中」检查（`sources.py` 事务外一处、`_save_snapshot` 写事务内一处）之后，各加一条：项目当前拆解（`studio_projects.breakdown_id` 指向的那一行）的 `import_json` 里 `_continuations` 非空、且拆解状态为 running 或 partial 时，409「续拆进行中，完成后再同步」。原因：续拆 partial 而组里恰好没有 queued/running job 时（例如失败的是本轮最后一个分集批，或 partial 来自 uncertain），r0 仍能同步，与界面和 §7 的「完成前不能同步新章」不符。
- **R1-P2 快照读不出时拆解视图降级**：`get_current` 读当前快照 manifest 失败时（`HTTPException`、`OSError`、`ValueError`），不得让整个视图失败：`changed_covered=[]`、`continuable=False`、`continue_from/to=None`，并在 `warnings` 末尾追加「当前快照无法读取，暂不能续拆，请到来源面板重新检查」。`stale_chapters` 照常从 `_chapter_basis` 计算。`retry`、`cancel`、`continue_start` 返回 `get_current` 的路径随之不再 500。
- **R1-P3 已续拆过的旧方案视图始终按已发布单元过滤**：`get_episodes` 与 `export_markdown` 过滤单元的条件，由「`_continuing(已发布拆解)`」改为「已发布拆解的 `_continuations` 非空」。续拆 partial 后整本重拆时，旧方案视图不再把本轮新单元算进「未纳入」；续拆发布后 `_published_max_seq` 等于最大 seq，过滤不改变结果。
- **R1-P4 防御**：`_insert_bible` 插入新行后，放进 `row_by_id` 的必须是用同一连接重新 `SELECT *` 读回的完整行，不能是手拼的精简 dict。
- **R1-P5 按钮层级（作者 2026-11-13 定）**：`BreakdownPanel` 里原有的整本报价按钮（文字「重新报价拆解」/「报价」那个），在 `breakdown?.continuable` 为真时用 `btn btn-quiet min-h-10`，否则保持 `btn btn-primary min-h-10`。其余不变。
- **R1-P6 小修**：`EpisodePlan` 表格视图里的「新增」标签加左间距（`className="tag ml-2"`）；卡片视图不变。
- **R1-P7 `CLAUDE.md` 体积**：本任务在 `CLAUDE.md` 新增的续拆段落压缩到要点（适用条件、两个接口、同一份拆解追加且总表与定妆保留、发布后重新批准、进行中不能取消也不能同步、不支持次要来源），细节移到 `docs/ARCHITECTURE.md` 的续拆段落（已有则合并，不重复）。`CLAUDE.md` 文件总大小不超过 67,400 字节（基线 66,525）。其余文档事实不得因压缩而丢失或变错。

**测试（只改三个新测试文件；每条都要做「自检」：按括号里的方法临时改坏实现，用例必须变红，然后还原，把变红输出摘要写进报告）**

- **R1-T1（复核 MF1）**：`test_continuation_execution_reads_bound_snapshot_and_keeps_old_units` 里快照 2 对第 3 章的改动必须落在旧批 range 以内（例如在正文**开头**插入一句），保留「`_source_inputs` 读回快照 1 原文」与「refresh 后旧单元 start/end/label 不变」两条断言。`changed_body` 被其他用例共用时，另写一个函数，别改变其他用例的语义。（自检：`_source_inputs` 改成只用 `breakdown['snapshot_no']`。）
- **R1-T2（复核 MF2）**：新章跨两段（同步到第 16 章），只让第 16 章的 `novel_complete` 失败，使第一段分集批成功、拆解为 partial：断言 `plan_revision`、集数不变，`appended_from is None`；单批重跑成功后，revision 只加 1、新集齐全、`appended_from` 正确。（自检：续拆分支的 `if status == 'done':` 改成 `if status in {'done', 'partial'}:`。）
- **R1-T3（复核 MF3）**：多行重名用例里两条重名行之一改为第 0 轮模型输出的自动条目（uuid5），并把它的定妆条目设为 approved；快照 2 的书斋圣经登记同名 `ref_id='C2'`。在 `continue_start` 后与 drain 后各断言：该自动条目 `merged_into is None`、`casting.is_orphaned` 为假、定妆仍 approved；新行与「与总表里多个同类条目重名」warning 照常出现。（自检：退役循环去掉 `old['id'] in frozen`。）
- **R1-T4（复核 MF4）**：续拆确认补三条拒绝用例，每条断言 409 文案，且批数、job 数、预留总额不变：报价过期 →「报价已过期，请重新报价」；报价后把额度压到不够（照 `test_studio_breakdown_pipeline.py` 改额度环境变量）→ 额度不足的 409；报价后插入一条 queued probe job（可复用 `insert_queued_probe`）→「拆解还有未结束的批次」。成功用例里另断言 `studio_quotes.status == 'confirmed'`。（自检：`continue_start` 里的 `_confirmed_quote(...)` 换成 `payload = preview`；确认时的未结束批次查询改成查不到。）
- **R1-T5（别名并集）**：作者用 `create_bible` 手建「船夫」并带别名 `['老船夫']`，续拆后新批输出「船夫」：续拆确认后与 drain 后都断言该行别名仍含「老船夫」、只有一条活动行。（自检：转向条目的别名改成只取新条目的别名。）
- **R1-T6（只改名）**：作者把第 0 轮自动条目「阿禾」改名为「禾生」，快照 2 的书斋圣经**不**登记这个人物，新批输出「禾生」：只有一条活动行、id 不变、不是孤儿。
- **R1-T7（跨新旧交界）**：续拆发布后、批准前，用 `move_boundary` 把最后一个旧集的终点挪进新单元：断言 `appended_from` 等于第一个 `unit_to ≥ _appended_from_unit` 的集号（按 §4.3 T6 第 2 条的定义）。
- **R1-T8（P1）**：续拆 partial 且组里没有 queued/running job（让本轮最后一个分集批失败）时 `sync_source` 返回 409「续拆进行中，完成后再同步」、快照号不变；续拆完成（done）后同步照常。
- **R1-T9（P2）**：把当前快照的 `manifest_sha256` 改坏：`get_current` 返回正常、`continuable` 为假、warning 含「当前快照无法读取」；对同一拆解调 `cancel`（未续拆过的情形）也正常返回。
- **R1-T10（P3）**：续拆 partial 后用整本报价 `start()`：已发布方案视图与导出的「未纳入」都不含本轮新单元。
- **R1-T11（前端）**：`continuable` 为真且 `changed_covered` 非空时，「在拆解之后改过」那句在输出里只出现一次；`continuable` 为真时整本报价按钮是 `btn-quiet`、为假时是 `btn-primary`；表格视图「新增」标签带 `ml-2`。

**报告**

- **R1-D1（复核 MF5）**：`impl/report.md` 补「文档改动位置」表：每行写文件:行号、原陈述类别、改后要点，至少覆盖复核列出的 `CLAUDE.md` 186、188、192、194、196，`README.md` 359、361、363、369、394、396，`docs/ARCHITECTURE.md` 412、416、418、507、509，`PLAN.md` 新节；并注明 `ARCHITECTURE.md:505` 核对后保留不改及理由。R1-P7 之后行号有变的，按 R1 后的行号写。
- **R1 报告** `impl/report-r1.md`：拆分表；R1-P1–P7、R1-T1–T11、R1-D1 逐条对应改了什么；每条自检的变红输出摘要；三个新测试文件的新收集数；§5 第 1–7 条的结果；`git status --porcelain --untracked-files=all` 原文；未完成或需人工确认的地方。

**R1 验收**：§5 第 1–7 条全部重跑。后端全量 passed = 8264 + 三个新测试文件的新收集数，0 skipped；无 `node_modules` 副本的 SKIPPED 数 = 前端新文件里起 node 的用例数。改动集合只在 R1 白名单内；R1 白名单外的文件与 r0 交回时逐字节相同。

### 4.9 R2 返修（2026-11-13，依据第 2 轮复核 `07-review-r2.md`，只改文档）

R1 的代码与测试经第 2 轮复核全部通过。唯一必须修复项是 R1-P7 没有把细节迁到 `docs/ARCHITECTURE.md`。**R2 白名单**：`docs/ARCHITECTURE.md`、`CLAUDE.md`、新文件 `impl/report-r2.md`。其他文件一字不动。

- **R2-D1（复核 MF-R2-1）**：在 `docs/ARCHITECTURE.md` 的续拆段落（以「续拆走 `continue_quote`/`continue_start`」开头的那一段）末尾补上下列四条事实，与已有文字合并、不重复：
  1. 续拆的每集时长沿用原拆解且不能改，续拆报价不带时长与「大约几集」；
  2. 续拆进行中新章人物就会进入总表并出现在定妆页，G1 回到未通过；
  3. 本轮批次无论首次执行还是单批重跑，都按批 `source_json.snapshot_no` 读本轮绑定的快照，书斋里再改原文对重跑无效；
  4. 仍失败只能整本重新拆解，会生成新的总表，已定的妆要重新定。
- **R2-D2**：`docs/ARCHITECTURE.md` 里「（`continuing` 时只取 `seq ≤ _published_max_seq` 的单元）」改为「（已发布拆解的 `_continuations` 非空时只取 `seq ≤ _published_max_seq` 的单元）」，与 R1-P3 一致。
- **R2-D3**：`CLAUDE.md` 聊天读小说那一段里的「缺失拒绝」恢复主语，写成「`auth_method` 缺失拒绝」。`CLAUDE.md` 仍不超过 67,400 字节。
- **R2 报告** `impl/report-r2.md`：逐条写改了哪里（文件:行号）；`wc -c CLAUDE.md`；`git diff --stat` 原文（只应有 R2 白名单内的文件相对 R1 交回时变化）；`grep` 在 `docs/ARCHITECTURE.md` 里能找到「不能改」「G1 回到未通过」「绑定的快照」「已定的妆要重新定」的输出。
- **R2 验收**：只改文档，不要求重跑后端全量；派单方在合并前会再跑一次全量门禁。

### 4.10 R3 返修（2026-11-13，作者定「可优化项先记下不做」，只改 `PLAN.md`）

**R3 白名单**：`PLAN.md`、新文件 `impl/report-r3.md`。其他文件一字不动。

- **R3-D1**：在 `PLAN.md`「2026-11-12：工作室续拆」一节的「已知局限：」那一段末尾追加一句（与已有文字合并、不重复）：「另有三处行为已用临时探针核对、但还没有固定成自动测试：续拆进行中同步时写事务内的复查、这条拦截不误伤未续拆过的拆解、快照文件损坏时不显示续拆按钮；快照文件损坏时后端日志每次轮询都会记一次同样的错误；续拆的单章批次标签沿用原有写法「第 x–x 章」。」
- **R3 报告** `impl/report-r3.md`：改动位置（文件:行号）与 `git diff --stat` 原文（相对 R2 交回时只应有 `PLAN.md` 变化）。

## 5. 验收标准（执行者自跑；派单方在沙箱外复跑，以派单方的结果为准）

1. `cd frontend && npx tsc --noEmit` 退出 0。
2. `cd frontend && npm run lint`：0 errors，warnings ≤ 25；新增和改动的文件不产生 warning。
3. `cd frontend && npm run build` 退出 0。
4. `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider -rs`：0 failed、0 skipped，passed 数 = 8264 + 三个新测试文件的收集数（既有文件收集数不变）。
5. 去掉 `frontend/node_modules` 的副本里跑三个新测试文件：0 failed；SKIPPED 数等于前端新文件里起 node 的用例数。
6. `git status --porcelain --untracked-files=all` 的改动都在 §4.1 白名单内（`docs/tasks/2026-11-12-studio-serial-breakdown/` 下派单方事先放好的文件不计入，执行者也不得改动它们）。既有测试只有 §4.6 第 1 条授权的改动。
7. AST 只读锁两条用例全绿：`studio/**` 没有新增 `novel.*` 导入，全文也没有 §4.2 第 8 条禁止的文字。
8. 报告 `impl/report.md` 写：
   - 拆分表；
   - T1–T10 逐条对应改了什么；
   - 改过的既有测试及理由；
   - 三个新测试文件的收集数；
   - 文档改动位置；
   - 未完成或需人工确认的地方。

## 6. 何时停下来问

- 只有影响「实现什么」时才停下来，例如：本规格前后矛盾；照做会让 §2 列出的现有行为在本规格之外发生变化；有 §4.6 没授权的既有测试必须改。
- 「怎么实现、怎么测」自己决定，并在报告里写明理由。
- 你实测到的事实优先于规格里的断言，两者不符就停下来说明。
- 任何情况下不回滚已完成的工作。

## 7. 已知局限（写进文档，不在本批解决）

- 已拆过的章后来被改了，续拆不会重拆它们，已拆部分仍按旧版原文；要更新只能整本重新拆解，会生成新的总表，已定的妆要重新定。
- 续拆开始后不能取消。有批次失败时，可以单批重跑（可换模型），或整本重新拆解；在此之前不能同步新章，也不能修改或批准分集方案。单批重跑读的是本轮绑定的快照，在书斋里改原文对重跑无效。未执行批次的预留占用确认当天的日额度和当月的 Claude 额度。
- 次要来源（上传文本、成稿）不能续拆。
- 续拆进行中，旧 G0 继续有效；新章人物会立即出现在定妆页，G1 回到未通过。续拆发布后整份分集方案退回待批准，批准之前定妆的付费操作暂时锁住。
- 定妆的付费确认在写事务外检查 G0，后台续拆发布与作者点定妆可能恰好交错；这个窗口很小，本期不处理。
- 续拆的批次不使用「大约几集」，只按每集时长切。
- 待复核的章照常进入快照与拆解，内容可能与改过的前文不一致，由作者判断。
- 改最新一章后的重新归档进行中、或重新归档失败暂停时，不能建项目、同步或续拆；要在书斋恢复写作、完成归档。
- 案头的分集页不显示「新增」；建议在工作室里看过新增的集再批准。
- 分身「做成片」遇到已有项目时直接打开，不会自动同步新章；卡片会提示到来源面板同步。

## 8. 修订记录

**v1.0（2026-11-12）**：初稿。依据三路只读调查，规格作者亲自核对了 `chapters_range` 不过滤状态、`_materialize` 追加不改旧 seq、`publish_plan` 删光重插、每章提交 `bible_version` 加 1 这四条。三项产品决定已由作者确认。

**v1.1（2026-11-12）**：四路对抗审查（数据一致性、计费与事务、来源与测试、前端与可执行性，各配一个反驳者，8 个代理），送反驳的 36 条 must/should 里 35 条成立、1 条被推翻（「整本重拆后取消就不能再续拆」：属于现有规则，定妆也不会孤儿）。其中两路在副本里照 T1 字面实现并跑全量，都复现出 3 条未授权的既有测试会变红。规格作者亲自核对了总表退役与 `merged_into` 孤儿路径、重新归档窗口、两处「不能做成片」原文、分集 id 无外部引用、关键测试与组件行号。主要修订：

- 总表：续拆过的拆解在 `_insert_bible` 里沿用已有活动条目（别名表 + 冻结集合），修掉「书斋后来正式登记同名人物 → 旧条目被标合并 → 已定的妆变孤儿」，以及作者改名、手建条目后出现重复行（§3.4、T4 第 6 步）。
- 改过的旧章与待复核：改为按章记录拆解依据 `_chapter_basis`，续拆后提醒不再消失；改过的旧章不可续拆时也显示（§3.4、T4 第 3 步、T6）。
- 续拆分集批不再带原拆解的「大约几集」；每轮第一个分集批用已发布方案的末集衔接（§3.6、§3.7、T5 第 2 条）。
- 「新增」从集号改为按单元界定，作者改方案、第一轮未批准就做第二轮都不会标错（§3.10、T5、T6）。
- 续拆进行中：取消按钮隐藏并说明；分集页不再说「按新结果重新生成」；新单元不算「未纳入」；partial 时的出路写进界面与 §7；取消守卫只放 `cancel()`，整本重拆仍可释放预留（§3.9、T5 第 4 条、T7 第 3、4、6 条）。
- 来源：资格与签名补上重新归档窗口（`_rearchive`）；来源面板的待复核改读快照、不依赖漂移状态；连载提示的条件修正，不再误显示在上传/粘贴项目上（T1、T7 第 7 条）。
- 入口与文案：书斋「做成片」对话框加入白名单并共用连载提示；分身复用已有项目时卡片如实写快照章数并提示同步；修改意见卡两处「待复核不能做成片」与 `.env.example` 一并改对（§4.1、§4.4、§4.5）。
- 测试：授权 5 条既有测试并写死改法（含 3 条 v1.0 漏列的）；补签名、范围、回落读原文、建议集数、衔接、总表沿用、单元界定新增、续拆进行中、partial、整本重拆释放预留、前端接线等用例；字重断言改为按 `data-serial` 定位并检查祖先；指明各组件该用的测试驱动与夹具（§2.4、§4.6）。
- 可执行性：`batch_plan` 偏移只在返回前统一加；T4 写明在写事务内重读、校验顺序固定；验收第 6 条排除派单方放好的文件。
- 按作者决定之外的默认处理（规格作者定，作者可改）：partial 时不做「放弃本轮续拆」，只把出路写清楚；案头分集页不标「新增」，只写进已知局限；分身复用已有项目时只改卡片文字，不自动同步。
- 2026-11-12 作者确认 v1.1，并选定续拆 partial 时「只写清出路」，本期不做「放弃本轮续拆」。

**v1.2（2026-11-13）**：新增 §4.8 R1 返修。r0 门禁全过（全量 8343 passed / 0 skipped），HEAD 导出跑新测试无收集错误；派单方变异 73 项杀 67 项，隔离走查 39/39；Opus 5.5 xhigh 复核认为实现无违规，判不通过的原因是测试证明力（MF1–MF4）与报告（MF5）。派单方另有变异发现「转向条目别名并集」无用例。可优化项里采纳：续拆进行中拒绝同步（与 §7 一致）、快照读不出时降级、旧方案视图始终按已发布单元过滤、`_insert_bible` 防御、表格标签间距、`CLAUDE.md` 压缩；作者 2026-11-13 定：可续拆时下方整本报价按钮改浅色。不采纳：单章批标签保持基线写法「第 x–x 章」（T2「单章写第 x 章」与「默认输出逐字节不变」冲突，以后者为准）；`get_current` 的 manifest 缓存。
