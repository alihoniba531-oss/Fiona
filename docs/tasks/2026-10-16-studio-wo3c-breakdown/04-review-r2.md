# WO3c 拆解与分集（G0）R1 返修复核

复核对象：worktree `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`，基线 `98c4ba8`，未提交改动。本轮只核验三件事：`04-review.md` 的必须修复项 M1–M7 是否落实；`05-fix-r1.md` 第二部分列出的 O1/O2/O3/O4/O5/O6/O7/O9/O11（以及 §4 第 8 条顺手项 O8/O10）是否按要求落实；返修有没有引入回归。新发现一律记为「可优化」。

取证方式：逐行读 R1 后的 `breakdown.py`、`breakdown_material.py`、`breakdown_plan.py`、`brain_jobs.py`、`store.py`、`recovery.py`、`sources.py`、`spend.py`、`routers/studio.py` 的 diff，3 个 `r1_*` 新测试与改动的旧测试，7 个前端文件；看 `screens/*-v2.*` 六张截图；本机复跑（先 `unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN OPENAI_BASE_URL`）：

| 命令 | 结果 |
|---|---|
| `pytest -q tests/test_studio_breakdown_*.py tests/test_studio_brain_frontend.py` | **209 passed / 0 failed**（15.5 s） |
| `pytest -q tests/test_studio_*.py`（全部 45 个工作室测试文件，含 WO0–WO3b 旧测试） | **1331 passed / 0 failed**（46.9 s） |

## 结论：通过

- M1–M7 全部落实，代码、测试、截图三方一致。
- 05-fix-r1 第二部分的 9 条可优化项全部按要求落实，每条都有新增测试覆盖。
- 未发现功能回归：既有工作室测试 1331 条全绿；`store._one/_many` 已恢复原写法；`_background`、`dispatch_queued`、`recovery` 的改动对非拆解任务是无感的（证据见 §3）。
- 主控提出的 (a)(b) 以及我新发现的 4 点，都属于观感/一致性问题，按本轮规则记为可优化（§4）；其中 (a) 是 R1 的 `w-20` 引起的布局退化，功能仍可横向滚动到达，建议下一轮优先处理。

## 1. 必须修复项 M1–M7 逐项核验

| 项 | 结论 | 代码证据 | 测试 / 截图 |
|---|---|---|---|
| **M1 更多菜单改为对话框** | ✅ | `EpisodePlan.tsx:15-38`：受控 `open` 状态 + 原生 `<dialog>`（`showModal` :21，`onCancel` 关闭 :25），标题「第 n 集 · 操作」:26，六个 `w-full` 按钮 :27-34，`perform` 先 `close()` 再执行 :23，关闭时 `focus({preventScroll:true})` :22 避免表格横滚；相邻性判定 `adjacent` :20 用于两种移边禁用 :31-32；操作列 `w-20` :73。表格与卡片共用同一 `menu()` :63。 | `test_more_native_dialog_closes_before_each_action_and_disables_invalid_boundaries`（frontend:154-159）：dialog 存在且带 `aria-labelledby`、七个按钮齐全、单场集与不相邻两集的禁用规则、关闭。截图 06-v2：居中对话框，六项竖排，右下「关闭」。 |
| **M2 部分完成提示指向真正要重跑的批** | ✅ | 后端 `breakdown.py:615-618`：`retry_needed`（status ∈ RETRYABLE∪{uncertain}，带 label/status）与 `blocked_segments`（episode_plan 且 blocked），`pending_segments` 已删。前端 `BreakdownPanel.tsx:41-42,57`：「以下批次需要重跑：…（被拒绝）；完成后「…分集」会自动继续。完成前不能批准分集方案。」uncertain 追加「需先核账释放」。 | 后端 `test_failure_blocks_manual_release_and_provider_retry`（pipeline:140-141）断言两个字段；前端 `test_partial_reports_retryable_batches_and_uncertain_release_before_blocked_segments`（frontend:179-183）与 `test_panel_ssr_unquoted_partial_outdated_and_running`（:57）断言新文案且不含旧文案。主控实测接口返回正确。 |
| **M3 梗概展示与导出可读化** | ✅ | 前端 `SynopsisPanel.tsx:21-25` `synopsisItemText`（主线「名称 —— 描述」，分段「第 a–b 章：摘要」，键名兼容 name/title、description/summary、from/to、start_chapter/end_chapter、from_chapter/to_chapter）；`:68-72` `SynopsisValue` 列表渲染；编辑态一行一项 `synopsisFieldDraft :26-31` / `parseSynopsisField :32-67`（保留原键与未知字段、错行 `throw` → 字段下 `role="alert"` :98）。后端 `breakdown_plan.py:16-27` 标签表；`_readable :576-593` 不再 `json.dumps`；`_prose :596-612`；`_render_export :618` `模型：千问`；`_inline :546-548` 与 `exchange_exports._inline` 字符集一致（不转义 `-`）。 | `test_prose_human_readable_structures_and_markdown_escaping`（r1_plan:23-37）断言含「旧灯 —— 找到灯」「第 1–2 章：离岸」「主题：归属、选择」且不含 `main_threads`/`"`/`{`/`[`、日期不出现 `\-`；`test_readable_synopsis_aliases_line_edit_parser_and_role_ranges`（frontend:161-165）覆盖解析器。截图 03-v2：主线两条「—— 」项、分段「第 1–10 章：…」。主控实测导出可读、模型名「千问」。 |
| **M4 定位中文、出场的集合并区间** | ✅ | 前端 `studio-breakdown.ts:90-99` `roleLabel` / `formatEpisodeRanges`，`BibleTable.tsx:38` 使用；后端 `breakdown_plan.py:551-567` `_role_label` / `_episode_ranges`，`_render_export :624-626` 使用。 | `test_role_labels`、`test_episode_ranges`（r1_plan:10-20，含乱序去重 `[6,1,5,3,2,1]→第 1–3、5–6 集`）、`test_export_uses_role_labels_and_compressed_episode_ranges`（:40-46，断言不含 `| main |`）。截图 04-v2：「主要人物 / 配角」「第 1–10 集」。 |
| **M5 进度条** | ✅ | `BreakdownPanel.tsx:43,56`：`role="progressbar"` + `aria-valuemin/max/now`，轨道 `--slip`、填充 `--ink2`，百分比宽度；原生 `<progress>` 已删；未改 `globals.css`。 | frontend:57 断言 `role="progressbar"`、`aria-valuenow="0"`。截图 01-v2：细灰轨 + 墨色填充。 |
| **M6 时长输入布局** | ✅（见 §4 (b)） | `BreakdownPanel.tsx:49`：三个 `w-28` 输入同一行 `flex-wrap items-end`，行尾 `readout` 分钟折算；`:50` 范围说明另起一行；`flex-1 basis-32`/`max-w-64` 已删。 | frontend:57 断言 `block w-28` 出现 3 次。截图 01-v2。 |
| **M7 重新拆解释放旧预留** | ✅ | `breakdown.py:215-245`：在确认报价之前检查旧 group **所有尝试**（含修正父任务）有无 `uncertain` → 409「…请先核账释放后再重新拆解」:223-226；有 running/submitting → 409 :227-230；通过后 `_cancel_unexecuted` :203-212 取消旧 `queued/blocked` 批对应的 queued job（`transition(queued→cancelled)` 归零预留）、chunk 置 cancelled、旧 breakdown 置 cancelled；旧 units/bible/episodes/plan_revisions 保留。整段在同一 `BEGIN IMMEDIATE` 事务内，任一校验失败整体回滚。前端 `BreakdownQuoteDialog.tsx:19` `replacesPartial` 提示「上一次拆解未执行的批次将取消并释放预留」，`BreakdownStage.tsx:83` 在旧拆解 partial 时传入。 | `test_restart_cancels_old_unexecuted_reservations_keeps_settled_cost_and_results`（r1_pipeline:94-115：旧 group 无 queued job、`reserved_amount` 全 0、`committed_cny == 新报价 + 旧实际费用`）；`test_restart_uncertain_rejected_before_any_mutation_and_quote_stays_open`（:118-135：409、报价仍 open、旧 jobs 行完全不变、`breakdown_id` 未切）；`test_restart_checks_uncertain_older_attempt_even_when_latest_is_released`（:196-212）。 |

## 2. 05-fix-r1 第二部分可优化项逐项核验

| 项 | 结论 | 代码证据 | 测试 |
|---|---|---|---|
| **O1 轮询写放大** | ✅ | `breakdown.py:508-517` `_dirty`：任一批 job 状态 ≠ chunk 状态、或 blocked 批依赖已全成功、或计算状态 ≠ 存储状态才算脏；`get_current :592-594` 先判脏再 `refresh`；`refresh :525-526` 不脏直接返回；`:534,539-547` 只有素材批（novel_complete/text_map）成功状态发生变化才重算 units/bible；chunk 行只在状态变化或 warning 变化时 UPDATE :552-554。 | `test_unchanged_get_is_zero_writes_and_preserves_timestamps`（r1_pipeline:16-40，done/cancelled 两种，用 `set_trace_callback` 断言零 DML、`updated_at` 不变）。 |
| **O2 收回越界改动** | ✅ | `git diff` 中 `store._one/_many` 已无改动（恢复 WO3b 写法）；仅 `store._get_job :293-304` 对四个拆解任务委托 `breakdown.decode_job_row`（线程中 `_row`）；拆解模块自带 `_one/_many/_job`（`breakdown.py:42-57`）在线程中解码大 JSON；`recovery.py:19-23` 恢复时只取 brain job 的小字段。 | `test_ordinary_store_queries_do_not_dispatch_worker_for_each_read`（r1_integration:59-71，monkeypatch `asyncio.to_thread` 为 fail）。 |
| **O3 报价不存全书正文** | ✅ | `_make_quote :99` `chunk.pop('inputs')`，payload 不再含 `manifest/imported`（:101-104）；`start :255,258` chunk `source` 只含 `_item`，job `inputs={}`；`_source_inputs :435-457` 执行时按 `breakdown.snapshot_no` 经 `_locked_snapshot :190-200` → `sources.read_snapshot_at :615-626`（按归属 + 快照号读归档快照，仍校验哈希）切片组装；`prepare_job :460-484` 在 `_background :231` 发请求前调用并写回 job `params_json`（CAS `status='queued'` 防并发）；`batch_plan` 记录 `ranges` :125-127 供切片。`start :237-238` 快照号不一致 409。 | `test_quote_and_source_are_text_free_and_execution_reads_locked_snapshot`（r1_pipeline:43-79：报价/chunk/job 均不含正文，执行时只读绑定快照第 1 版且在主线程外）；`test_quote_json_size_does_not_grow_with_source_body_length`（r1_integration:121-139，200 字与 10000 字报价 JSON 差 <512 B）；`test_start_rejects_snapshot_change_without_confirming_or_reserving`（:142-154）；`test_read_bound_snapshot_uses_its_own_revision_and_worker`、`test_bound_snapshot_reader_still_verifies_body_hash`（:17-56）。 |
| **O4 锚点未命中回退** | ✅ | `breakdown_material.py:11-34`：未命中记 `None`，自后向前回填为「下一个命中位置或块末」:24-29；首场命中才强制 0 :30-31；命中场保住正文。 | `test_missing_anchors_use_next_match_or_block_end`（r1_pipeline:138-147，首/中/尾/全缺四例）；旧测试 `test_missing_anchor_records_warning_without_guess_or_offset_regression`（material:123-130）已按新规则更新。 |
| **O5 warning 归属** | ✅ | `_materialize :307,317` 用 `warning_by_chunk` 按来源 chunk id 收集；`merge_bible` 的 `warn(message, cid)` :165-168 把摘录/合并 warning 记到来源批；`refresh :548-555` 写回对应 chunk；跨批冲突归 `__breakdown__` 并经 `get_current.warnings` :619-620 单列。 | `test_material_warnings_belong_to_the_source_batch`（r1_pipeline:170-193：第 2 块的锚点/摘录 warning 只出现在第 2 块）。 |
| **O6 未完成时只读** | ✅ | 后端 `operate_episodes :327-328` 与 `approve :347-348` 在活动拆解 running/partial 时 409；前端 `EpisodePlan.tsx:52-54` `regenerating/editsBlocked`，`:62` 操作入口直接拒绝，`:63` 菜单 busy，`:71` 提示「拆解尚未全部完成，补跑完成后分集方案会按新结果重新生成。完成前暂不能修改或批准分集方案。」，`:76-81` 建集/二级 dialog 同步禁用。 | `test_unfinished_breakdown_episode_operations_return_409`（r1_plan:61-70，六种 op × running/partial，revision 不变）；前端 `test_running_partial_and_rebreakdown_keep_old_g0_but_disable_editing`（frontend:167-171）。 |
| **O7 重新拆解期间保留旧方案** | ✅ | `breakdown_plan.py:58-78` `_published`：以最新 `studio_plan_revisions.plan_json.breakdown_id` 定位已发布方案，活动拆解 ≠ 已发布时沿用快照里的目标秒数，并把已发布拆解状态按发布原因呈现为 done/partial；`_activity :81-87` 附 `breakdown_id/active_breakdown_id/active_breakdown_status/rebreakdown_pending`；`get_episodes/operate/approve/export` 全部走 `_published`（:148,329,349,645）；`g0_approved` 要求有集 :138（杜绝「0 集已批准」）；`publish_plan :239-240` 只在 `project.breakdown_id == bid` 时 `_revision`（新方案发布 revision+1，自然退回待批准）。前端 `EpisodePlan.tsx:71` 「新的拆解进行中，完成后会替换此方案…」并禁用修改/批准；`:50` 目标秒数取 `plan.settings`。 | `test_rebreakdown_keeps_published_episodes_g0_and_target_defaults`、`test_first_unpublished_run_never_reports_approved_zero_episode_plan`、`test_new_publication_replaces_old_plan_once_and_clears_g0`、`test_cancelled_replacement_restores_old_plan_editing_and_default_revision`、`test_real_rebreakdown_confirmation_keeps_approved_plan_until_new_publication`（r1_plan:73-175，最后一条是真实跨模块流程：批准 → 草稿报价 → start → 旧方案/G0/目标保留 → 跑完发布 → revision 2 待批准）；前端 frontend:185-195。 |
| **O9 恢复不阻断启动** | ✅ | `breakdown.recover :683-694` 逐个 try/except，日志只记 id 与异常类型；`recovery.py:30-39` 对拆解任务的 running→uncertain 转换也隔离；`recover_studio_jobs` 末尾调用 :57-58。 | `test_recovery_skips_one_bad_breakdown_and_continues`（r1_pipeline:150-167，断言敏感文本不进日志）；`test_corrupted_running_breakdown_cannot_block_other_recovery`（r1_integration:91-118，损坏 `params_json`/`import_json` 两种，另一项目仍恢复为 uncertain）。 |
| **O11 报价时保存时长明示** | ✅ | 路由 `BreakdownQuoteBody` 新增可选 `episode_seconds_min/max`（routers diff），`breakdown.quote :141-149` 校验 60≤min≤max≤900 且只作草稿；`start :270-271` 确认时才写入项目。前端 `BreakdownStage.tsx:81-84` 报价不再预先 PATCH；`BreakdownQuoteDialog.tsx:17-18` 「每集目标时长将保存为 x–y 秒（确认开始时保存）」+ 影响已批准方案时的说明；单独「保存时长」影响已批准方案时先弹确认（`BreakdownStage.tsx:78-80,102`）。 | `test_quote_draft_seconds_does_not_change_project_until_confirmed`（r1_pipeline:215-227）；前端 `test_quote_does_not_patch_settings_and_confirmation_explains_old_plan_changes`（frontend:173-177）。 |
| **顺手项 O8 / O10** | ✅ | `patch_bible :471-474` 外形清空 → `appearance_source='none'`、人物 `needs_author=1`，并记入作者编辑标记防补跑回填；`spend.py:103-115` 三条 409 文案四位小数。 | `test_clearing_character_appearance_marks_missing_and_survives_refresh`（r1_plan:49-58）；`test_director_budget_messages_use_four_decimal_places`（r1_integration:74-88）。 |

## 3. 回归检查

| 检查点 | 结论 | 证据 |
|---|---|---|
| 既有工作室测试 | ✅ | `tests/test_studio_*.py` 45 个文件 1331 passed / 0 failed；`test_studio_brain_frontend.py` 随套件通过。 |
| `store._one/_many` 恢复 | ✅ | diff 无改动；O2 测试。 |
| `brain_jobs._background` 新增异常分支 | ✅ 无副作用 | `brain_jobs.py:225-242`：`HTTPException/Exception` 时 `cas_job(jid, 'queued' → 'rejected')`，只有 job 仍为 queued（即 `prepare_job` 在发请求前失败）才会生效；已进入 `run_brain` 的任务状态已不是 queued，CAS 静默返回 False，旧行为不变。非拆解任务走 `job['params']['inputs']` :231-232 原路径。 |
| `dispatch_queued` 只取 `j.id` | ✅ | `:217-222`，`_schedule` 只用 id。 |
| `recovery.recover_studio_jobs` 改为直接 SQL | ✅ | brain 任务只取 `id,kind,task,status,run_token`（代码仍只用这些键）；非 brain 任务 `_many(... kind!='brain')` 取整行（`studio_jobs.kind NOT NULL`，无 NULL 漏网）。`test_studio_scheduler.py`、`test_studio_brain_budget_api.py` 通过。 |
| 付费安全不退化 | ✅ | 旧断言仍在：确认一次/过期（pipeline:87-100）、全批预留 `sum(reserved)==total_max`（:87）、重启不发（:165,200）、取消释放（:170）、单次/日/月上限 0 次 POST（budget.py）。M7 新增路径在确认报价之前校验，失败时报价保持 open（r1_pipeline:131-133）。 |
| 原文不落入新表 | ✅ | O3 测试断言 `studio_quotes.items_json`、`studio_chunks.source_json` 均不含正文；执行时的素材只在对应 job 的 `params_json`（`WatchPrivateText`）。 |
| 前端缺依赖 skip 守卫 | ✅ | `test_studio_breakdown_frontend.py:17-37` `probe()` 与守卫自测未改；实现方报告隐藏 node_modules 时 173 passed / 36 skipped。 |
| 非工作室测试零改动 | ✅ | `git diff 98c4ba8 --stat -- backend/tests` 仍只有 `test_studio_brain_frontend.py`。 |

## 4. 新发现（全部记为可优化）

**(a) 分集表「操作」列在 1280 宽带侧栏时被挤出可视区**（主控发现，`screens/05-分集表-v2-操作列在1280宽被挤出.jpg`）
- 判定：**R1 引起的布局退化（轻度回归），非功能回归**。`min-w-[1180px]` 在首轮就有（`EpisodePlan.tsx:73`），容器 <1180 时表格始终溢出同样的像素数；首轮操作列按 `table-fixed` 均分约 110 px，溢出 60–80 px 时「更多」仍露出一截；R1 按我的指令把操作列固定为 `w-20`（80 px）后，同样的溢出量刚好把整列推出可视区，必须横向滚动才能点到。规格允许表格在容器内横滚，所以功能可达，但「最常用的操作列默认看不见」应优先处理。
- 修法（二选一，推荐第一种）：① 操作列 `th/td` 加 `sticky right-0 z-10 bg-[color:var(--paper)]`（或 `ceramic-card` 同色背景）让它始终贴右可见，表头同样 sticky；② 把 `min-w-[1180px]` 降到约 1000 px（操作列已只需 80 px，变化/钩子两列可再让出空间），并给「预估镜头数」「预估时长」「目标时长」三列设 `w-24`。

**(b) 「大约几集（可不填）」在 `w-28` 内折成两行，三组标签上沿不齐**（主控发现，`screens/01-拆解面板-v2-…jpg`）
- 判定：可优化（R1 新布局的文案宽度问题，输入框本身因 `items-end` 底部对齐，但标签高低不一）。
- 修法：标签改为「大约几集」并把「可不填」放进 `placeholder`；或该 label 用 `w-36`；三组 label 的 `<span>` 统一 `block min-h-5 whitespace-nowrap`。

**N1 拆解级 warnings 没有在界面展示**
- `get_current` 新增 `warnings`（`breakdown.py:619-620`，跨批合并冲突与无法归属的提示），但 `lib/studio-breakdown.ts` 的 `StudioBreakdown` 类型未声明，`BreakdownStage/BreakdownPanel` 也未渲染，作者看不到「某人物对应多个小说工坊 ID，未自动合并」这类提示。建议在批次列表上方加一个 `ceramic-card` 列出。

**N2 重新拆解期间，总表与梗概切到新拆解、分集仍显示旧方案**
- O7 只要求分集表与 G0 保留旧方案，已按要求实现；但 `list_bible`（`breakdown_plan.py:426-437`）与 `get_current.synopsis` 仍取活动拆解，所以 `start()` 之后页面上「分集方案」是旧的、「总表」变成新拆解的初始条目（文本来源为空）、「故事梗概」变成新拆解的导入梗概。属于视图一致性问题，不影响数据。建议 `rebreakdown_pending` 时总表/梗概同样读已发布拆解，或在这两块上方加同一句「新的拆解进行中」提示。

**N3 `start()` 把已完成（done）的旧拆解也标成 `cancelled`**
- `_cancel_unexecuted :210-212` 对任何非 cancelled 的旧拆解都写 `status='cancelled'`，`_published :73-76` 再按发布原因把它呈现回 done/partial。功能正确（测试覆盖），但 `studio_breakdowns.status` 原始值与事实不符，后续 WO3d 若直接读该列会误判。CHECK 约束限制了可用状态，若要区分需在 DDL 补一个 `superseded` 值（属新增，仍符合「只做新增」）；本期可先在 03-report 的取舍里写明。

**N4 修正批的输入复用首轮 `inputs`，与 O3 的「单次调用素材仅保存在对应 job」略有重叠**
- `_execute_brain` 修正时 `_insert_job(..., inputs, ...)` 再存一份完整素材到修正 job 的 `params_json`（`brain_jobs.py` 修正分支）。同一批最多两份，体量可控，仅记录。

## 5. 对 03-report「二次修改」一节的核对

- 6.2/6.3 的逐条对应与代码一致，未发现夸大；「关闭恢复焦点时使用 preventScroll」「uncertain 任意尝试始终要求核账释放」「首次空方案 G0=false」等细节都能在代码里找到。
- 6.4 的两种环境测试结果与我本机复跑一致（209 passed；隐藏依赖轮次由实现方自报，守卫逻辑未改，可信）。
- 6.5 取舍合理：failed 无 usage 的调用保留账本占用，与 WO3a 既有规则一致，不是 M7 的遗漏。
