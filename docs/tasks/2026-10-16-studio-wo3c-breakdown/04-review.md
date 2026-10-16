# WO3c 拆解与分集（G0）独立复核

复核对象：worktree `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`，基线 `98c4ba8`，未提交改动（`git diff 98c4ba8` 13 个文件 + 28 个新文件）。只看落盘产物：规格 `02-spec.md`、全部 diff 与新文件、`03-report.md`（仅参考）、`screens/01–11`。

专项取证（本机复跑，先 `unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN OPENAI_BASE_URL`）：8 个新测试文件 + 改动的 `test_studio_brain_frontend.py` 共 **148 passed / 0 failed**（11.2 s）。另写了一个临时探针测试验证预留泄漏（见 M7），跑完已删除，仓库无残留。

## 结论：不通过（后端核心通过，界面与导出需二次修改后复核）

- **付费安全、依赖调度、原文真实性、分集/G0 不变量、数据归属与删号**：全部对上规格，证据见下表；没有发现会多扣费或重复发请求的路径。
- **不通过的原因**：主控列的 ①–⑥ 六个界面问题全部成立（代码与截图互证），其中 ①（更多菜单）和 ⑥（部分完成指错批）直接影响可用性；另发现一处实际风险 M7——重新拆解时旧 partial 拆解的未执行批与 uncertain 批的预留不释放、界面上也无法再释放，会占用当日人民币额度 / 当月 Claude 额度（已用探针复现）。
- 建议：按第 5 节指令二次修改，再复核一次界面（截图 06/07/10 对应场景）与 M7 的新增测试。

## 1. 验收标准逐条核验

### A. 付费安全

| 项 | 结论 | 证据 |
|---|---|---|
| 新任务沿用「只发一次」 | ✅ | `brain.py:433` `max_retries=0` 不变；拆解任务只是把超时改为 300 s（`brain.py:420-422`，`_once` 中 pop 后再调 SDK，`test_studio_breakdown_pipeline.py::test_new_task_timeout_is_300_and_sdk_retries_zero` 断言 `_studio_timeout` 不进 SDK）。修正最多一次：`brain_jobs.py` `for attempt in (1, 2)`；截断不修正 `brain_jobs.py:333-337`，测试 `test_truncated_new_task_is_never_repaired`。 |
| 报价只能确认一次 | ✅ | `breakdown.py:135-136` `status != 'open'` → 409；`:140-141` `UPDATE … WHERE status='open'`，全程在 `BEGIN IMMEDIATE`（`store.py:254-270`）内。旧确认接口被挡住：`store.py:483-484` 拒绝无 `params` 的 items（拆解报价是 dict payload）。测试 `test_quote_confirmation_preallocates_all_batches_once_and_expires`。 |
| 过期不能确认 | ✅ | `breakdown.py:137-138`；15 分钟 `:96`。同上测试。 |
| 确认时全部批预留 | ✅ | `start()` 对 plan 里**每一批**（含 blocked）都 `_new_chunk_job`（`:181`），`_new_chunk_job` 把 `first_max` 设为 `item['amount']`（首轮 + 一次修正，`brain_jobs.py:61`），`_insert_job` 按它写 `reserved_amount/reserved_cny`（`brain_jobs.py:120-121`）。测试断言 `sum(reserved_amount) == quote.total_max`。 |
| 单次上限 / 日上限 / Claude 月上限在发请求前检查，0 次 POST | ✅ | `spend.check_brain_budget` 新增单次上限 `spend.py:103-106`（`FIONA_STUDIO_MAX_QUOTE_CNY`，`config.py:106`），日上限 `:107-110`，月上限 `:111-115`，均带「还差」金额。报价路径 `breakdown.quote` `:124` 与确认路径 `_confirmed_quote` `:139` 都调用；`_option()` 只读 env/BYOK 状态不联网（`brain.py:478-503`）。测试 `test_studio_breakdown_budget.py` 三组参数化 + `test_existing_director_tasks_enforce_single_quote_cap`（旧导演任务也补上了），断言 provider 未创建、jobs/quotes/breakdowns 表为 0 行。 |
| 单批重跑必须先报价 | ✅ | `retry()` 要求 `breakdown_retry` 类型的已确认报价，且 `breakdown_id/chunk_id/previous_job_id` 全部匹配（`breakdown.py:485-490`）；`retry_quote` 再过一次 `check_brain_budget`（`:473`）。 |
| uncertain 必须先释放 | ✅ | `retry_quote` `:464-466` 只放行 `RETRYABLE`；`retry` `:489` 再查一次 job 状态。测试参数 `uncertain` 分支先 409 再 `release_job` 后才能报价。 |
| 取消释放未执行批 | ✅ | `cancel()` `:505-510` 对 `queued/blocked` 批走 `transition(queued→cancelled)`，`transition` 把 `reserved_amount/reserved_cny` 归零（`brain_jobs.py:194-200`）；running 不打断（`test_cancel_does_not_interrupt_already_running_success`）；取消后不再发修正（`brain_jobs.py:285-293`、`:366-369`，测试 `plan_review::test_cancelling_running_batch_settles_first_call_without_new_paid_repair`）。 |
| 重启恢复不重发、blocked 不变 | ✅ | `recovery.py:39-40` → `breakdown.recover()` 只 `refresh(dispatch=False)`（`breakdown.py:515-523`）；running→uncertain 沿用。`dispatch_queued` 左连 `studio_chunks`，只派 `c.status='queued'` 的 job（`brain_jobs.py:217-222`），所以 blocked 批那条已存在的 queued job 不会被补发。测试 `test_restart_running_becomes_uncertain_and_never_submits`、`test_dispatch_does_not_send_blocked_preallocated_jobs`。 |
| 拆解不会新建项目 | ✅ | 只有 `_BOUND_JOB` 为空才 `create_project`（`brain_jobs.py:262-271`）；`_background` 先 set（`:228`）。测试断言 `COUNT(studio_projects)==1`、`len(/studio/projects)==1`。 |
| 修正费用不越过预留 | ✅ | 绑定批的修正把 `item.amount` 改成已授权的 `repair_max`，首轮用量未知时把首轮 job 的 hold 降为 `first_max`（`brain_jobs.py:352-365`），再 `_insert_job` 预留 `repair_max`；总 hold 恒等于确认时金额（`test_unknown_first_usage_then_uncertain_repair_keeps_only_confirmed_reserve` 断言 `sum(reserved)==total_max`）。 |

### B. 依赖调度

| 项 | 结论 | 证据 |
|---|---|---|
| blocked 只在依赖全部成功后组装输入并执行 | ✅ | `refresh()` `breakdown.py:384-397`：`all(... == 'succeeded')` 才 `_dependency_input`（在 `to_thread`）→ 更新 `params_json` → `UPDATE … WHERE status='blocked'` → 才 `_schedule`。失败时下游保持 blocked（`test_failure_blocks_manual_release_and_provider_retry` 断言 `['blocked','blocked']`）。 |
| 不循环、不重复派发 | ✅ | `_schedule` 以 `active` 字典去重（`brain_jobs.py:210-215`）；`_execute_brain` 以 CAS `queued→running` 兜底。`integration::execute_all` 断言调度次数 ≤ 8。 |
| 并发与 lane 信号量 | ✅ | 沿用 `run_brain` 每家 `Semaphore(3)`（`brain_jobs.py:248`），拆解 job 也经 `_background→run_brain`。 |
| 依赖图正确 | ✅ | `batch_plan`：小说 ≤10 章且 ≤24,000 字、不跨 10 章段（`breakdown_material.py:102-104`）；次要来源 >12,000 字块按段落切 ≤10,000（`split_block :31-46`）；synopsis 依赖全部 text_map（`:134`）；每段 `episode_plan` 依赖本段及之前所有补全/通读批 + 上一段分集（`:138-144`，注释说明 seq 全局编号必须等前面都定）；填了「大约几集」的小说让所有分集批依赖全部补全批（`breakdown.py:60-64`）。测试 `material::test_novel_batches_obey_both_limits_and_ten_chapter_segments`、`test_text_subblocks_preserve_exact_paragraph_offsets_and_dependencies`。 |
| 部分完成不能批准 G0 | ✅ | `approve()` 要求 `status == 'done'`（`breakdown_plan.py:294-295`）；前端按钮禁用（`EpisodePlan.tsx:36,51`）。测试 `plan::test_partial_empty_and_cancelled_approval`。 |

### C. 原文安全与真实性

| 项 | 结论 | 证据 |
|---|---|---|
| 原文只经数据块传入 | ✅ | `material_prompt` 未改（`brain.py:104-121`），四个提示词都写明不执行素材指令（`prompts/*.md`）。测试 `test_duration_and_uncovered_are_only_warnings_and_schema_limits` 断言 material 原样进数据块。 |
| excerpt 必须是原文子串，否则丢弃并记 warning | ✅ | `merge_bible` `breakdown_material.py:168-170`（含 ≤200 字）；`appearance_fills` `:193-199`；指到批外章号时 `source=''` 自然失配。测试 `test_invented_or_wrong_chapter_excerpts_are_dropped_and_warned`。 |
| needs_author | ✅ | `:174`、`:244`；小说工坊有外形 → `workshop`，优先于摘录（`test_workshop_ids_stay_distinct_and_workshop_appearance_has_priority`）。 |
| start_anchor 定位 | ✅（语义见 O4） | `locate_scenes :11-28`：顺序精确 `find`，首场强制 0、末场到块末，单调不减；未命中记 warning 并沿用 `cursor`。测试两例。 |

### D. 分集与 G0

| 项 | 结论 | 证据 |
|---|---|---|
| 硬约束触发一次修正 | ✅ | `brain_tasks.py:98-106`（有序、非空、不重叠、段内）；修正后仍不合格 → `invalid_output`（`test_hard_constraints_get_exactly_one_paid_repair`：恰 2 次调用、第 2 次带 repair）。 |
| 软约束只记 warning | ✅ | `_episode_warnings :140-152`（±15%、未纳入）。 |
| 拼接编号连续；秒数/镜头数由代码算 | ✅ | `publish_plan` 按 chunk 顺序重编号（`breakdown_plan.py:177-183`）；`_present_episodes :66,72` `sum(est_seconds)`、`round(秒/3.5)`。 |
| 六种操作与不变量 | ✅ | `_operate :205-269`，`_validate :105-118`（有序、不重叠、非空、落在单元内、60≤min≤max≤900）。`plan::test_all_operations_revision_invariants_and_g0`、`test_invalid_operations_roll_back`、`test_boundary_cannot_empty_or_cross_gaps`。 |
| 每次操作 revision+1 并写 studio_plan_revisions | ✅ | `_revision :153-166`，同事务；测试断言 revisions 1..8。 |
| expected_revision 不符 409 | ✅ | `:275-276`、`:292-293`。 |
| 批准后再改退回待批准 | ✅ | `g0_approved = revision == approved`（`:90`）。 |
| 快照同步后 outdated=1；拆解进行中不能同步 | ✅ | `sources.py:483-484`；旧门禁覆盖 blocked 批（`plan_sources::test_breakdown_director_jobs_prevent_sync` 三种状态）。 |

### E. 数据

| 项 | 结论 | 证据 |
|---|---|---|
| 只增不改旧表 | ✅ | 6 张新表 + 索引 `store.py:90-142`；`studio_projects` 新列同时写进 DDL 与 `migrate_schema` additions（`:226-233`）。 |
| 删号清理新表 | ✅ | `database.py:915-918`（units 经 breakdown owner 子查询）。`plan::test_account_deletion_cleans_all_new_tables`。 |
| 归属检查 | ✅ | `_breakdown` 校验 owner + `_project`（`breakdown.py:36-41`、`breakdown_plan.py:26-31`）；chunk 只在该 breakdown 内查（`:458,480`）；`_bible_item` 带 owner（`breakdown_plan.py:373-379`）。`integration::test_all_new_endpoints_are_hidden_from_non_authors` 17 条路由 404；`plan::test_owned_resources_and_extra_fields`。 |
| 事件循环无同步重 I/O | ✅ | 读快照 `sources.read_snapshot` 本就 `to_thread`；`_make_quote`、`_materialize`、`_dependency_input`、`_insert_units` 行构造、`_present_episodes`、`_validate`、`_revision` 快照、导出 `render`、`validate_reply`、`system/material_prompt` 全部 `to_thread`。`plan::test_markdown_export_escaping_headers_and_worker` 断言导出在工作线程。副作用见 O2（`_one/_many` 全局线程化过度）。 |

### F. 前端

| 项 | 结论 | 证据 |
|---|---|---|
| F1 页签结构 | ✅ | `StudioWorkbench.tsx:142`：SourcePanel → `BreakdownStage` 或「先关联作品才能拆解」→ `<details>`「试读与三家对比」默认折叠。`test_studio_brain_frontend.py` 断言已更新。 |
| F2 拆解面板 | ✅（⑤⑥④ 见必修） | 设置/报价 dialog（批数、金额、模型、倒计时、过期禁用）/进度/批次（默认展开有问题的批 `open={problem}`）/重跑选模型先报价/uncertain 释放提示「可能已扣费」/5 s 轮询有在途才跑（`BreakdownStage.tsx:47-55`）/outdated 提示/partial 提示。`test_studio_breakdown_frontend.py` 覆盖。 |
| F3 结果区 | ✅（①②③ 见必修） | 梗概字段、总表三页签 `useRovingTabs`、待补充 `.tag` + 筛选、行内编辑、合并确认、新增/归档；分集九列、超时标色+文字、更多菜单、未纳入灰行+建成一集、版本/批准/导出、409 刷新（`BreakdownStage.tsx:68`）、`@[640px]` 卡片、表格自身 `overflow-x-auto`。 |
| F4 多项目「打开」 | ✅ | `SourceChoices.tsx:11-22`：按 `created_at` 倒序、只有第 0 个 `btn-primary`、`<time>` 本地 `YYYY-MM-DD HH:mm`；后端 `sources.py:82` 倒序。截图 11 符合。SSR 测试 `test_f4_ssr_only_newest_project_is_primary_with_local_date`。 |
| 缺依赖 skip | ✅ | `probe()` 先查 4 个包再查 node（`test_studio_breakdown_frontend.py:208-216`），`test_dependency_guard_skips_before_starting_node` 参数化验证不启动 node。 |
| 非工作室测试零改动 | ✅ | `git diff 98c4ba8 --stat -- backend/tests` 只有 `test_studio_brain_frontend.py`（工作室测试）。 |

### G. 界面观感（截图 + 代码互证）

| 编号 | 成立？ | 严重度 | 证据 |
|---|---|---|---|
| ① 更多菜单原地展开被裁切、不收起、表格横滚 | **成立** | 高 | `EpisodePlan.tsx:14-22` 用无 `open` 控制的 `<details>` 在操作列内联展开；表格容器 `overflow-x-auto` + `min-w-[1180px] table-fixed`（`:54`），操作列约 118 px，菜单文字被右缘裁切（screens/06）；点菜单按钮时浏览器把焦点元素滚入视口导致容器横向滚动，集号列消失（screens/07），且操作后 `<details>` 仍开着。 |
| ② 梗概按通用对象逐字段罗列；导出倒出 JSON 键名与转义；模型名英文 | **成立** | 中 | 前端 `SynopsisPanel.tsx:43` 用 `ContentValue` 通用渲染，`main_threads/arc_summaries` 的键按 `NovelContent.tsx:17-21` 映射成「姓名/描述/起始章节/结束章节」（screens/03）。后端 `_prose`（`breakdown_plan.py:494-504`）对 list/dict 直接 `json.dumps` 再 `_inline` 转义，实测输出 `- main\_threads：\[\{"name": …\}\]`、`- arc\_summaries：\[\{"from": 1, …\}\]`；`_render_export :510` 写 `模型：qwen`。 |
| ③ 定位显示 main/supporting；出场的集逐个列 | **成立** | 中 | `BibleTable.tsx:38` `entry.role || "—"` 与 `第 ${no} 集` 逐个 join（screens/04 林岚一行列到第 10 集）；导出 `_render_export :516,518` 同样原样输出 role 与 `'、'.join(episodes)`。 |
| ④ 进度条饱和亮绿 | **成立** | 低 | `BreakdownPanel.tsx:55` 原生 `<progress … accent-[color:var(--ink)]>`，截图 01/10 实际是浏览器默认绿色（`--ink` 是 `#1F2926`，说明 accent-color 未生效），与宋式配色冲突。 |
| ⑤ 两个秒数框各占半宽 | **成立** | 低 | `BreakdownPanel.tsx:47` 两个 `<label className="flex-1 basis-32">`，宽屏时各撑满一半（screens/01）。 |
| ⑥ 部分完成提示写「第 11–14 章 · 分集」待重跑 | **成立** | 中 | 前端 `BreakdownPanel.tsx:41,56` 把 `task==='episode_plan' && status!=='succeeded'` 的批当「待重跑」；后端 `get_current` `pending_segments` 同样只收分集批（`breakdown.py:451-452`）。实际被拒的是补全批（status `rejected`），分集批只是 `blocked`（screens/10）。 |

### §9.2 必测项对照（抽查）

- 批次计划 5 条：`material.py` 全部覆盖 ✅。
- 报价与上限 5 条：`budget.py`、`pipeline::test_quote_confirmation_*` ✅。
- 执行与依赖 7 条：`pipeline.py` ✅（含 provider 换 deepseek、POST 次数为 0、取消释放、恢复不发）。
- 新任务 5 条 ✅；场景定位 ✅；总表合并 5 条 ✅；分集计算 ✅；分集操作 7 条 ✅；快照同步 2 条 ✅；导出 4 条 ✅；归属 ✅；删号 ✅；F4 ✅；前端关键状态 ✅（SSR + hooks 驱动）。

## 2. 必须修复项

### M1（高）① 分集表「更多」菜单：裁切、不收起、表格横向滚走
- 复现：桌面宽度 <1200 px 打开 ①拆解 → 分集方案表 → 任一行「更多」。菜单在 118 px 宽的操作列里内联展开，右侧被 `overflow-x-auto` 容器裁掉（screens/06）；点「与下一集合并」后表格横向滚到最右、集号列不可见、菜单仍开着（screens/07）。
- 根因：`EpisodePlan.tsx:14-22` 非受控 `<details>` 内联渲染菜单；滚动容器会裁切任何绝对定位弹层，所以 `NovelWorkbench.tsx:285` 那种 `absolute right-0` 写法在这里也不行。
- 修法：把菜单改成原生 `<dialog>`（沿用 `BreakdownDialog` 的样式 `sourceDialogClass`，但不要确认/取消两按钮，只要一个「关闭」）：点「更多」打开「第 n 集 · 操作」对话框，列出修改 / 与下一集合并 / 拆分 / 边界前移一场 / 边界后移一场 / 删除六个 `.btn btn-quiet w-full` 按钮；点任一项先 `close()` 再执行（修改/拆分/删除接着打开各自的二级 dialog）。表格与卡片共用同一组件。顺带把「边界前移/后移」在两集不相邻（`next.unit_from !== episode.unit_to + 1`）时禁用，避免点了才收到 422。

### M2（中）⑥ 部分完成提示指错了批
- 复现：让补全批被拒（screens/10）：提示写「以下分段待重跑：第 11–14 章 · 分集」，但分集批是 `blocked`，可重跑的是「第 11–14 章 · 补全」。
- 修法：后端 `get_current`（`breakdown.py:448-452`）把 `pending_segments` 换成两个字段：`retry_needed`（status ∈ `failed/rejected/invalid_output/released/uncertain` 的批的 `label` + 状态）与 `blocked_segments`（`episode_plan` 且 `blocked` 的 `label`）；前端 `BreakdownPanel.tsx:41,56` 改为「以下批次需要重跑：第 11–14 章 · 补全（被拒绝）；完成后「第 11–14 章 · 分集」会自动继续。完成前不能批准分集方案。」`uncertain` 的批写「需先释放再重跑」。更新 `test_panel_ssr_unquoted_partial_outdated_and_running` 的断言文字。

### M3（中）② 梗概展示与 Markdown 导出可读性
- 复现：小说来源拆完看「故事梗概」：主线显示「描述 / 姓名」、分段梗概显示「结束章节 / 起始章节 / 摘要」（screens/03）；导出 Markdown「梗概」一节是 `- main\_threads：\[\{"name": …` 这样的原始 JSON；头部 `模型：qwen`。
- 修法：
  - 前端 `SynopsisPanel.tsx`：不再用 `ContentValue` 兜底。`main_threads` 渲染为列表项「名称 —— 描述」（键名兼容 `name/title`、`description/summary`）；`arc_summaries` 渲染为「第 a–b 章：摘要」（键名兼容 `from/to`、`start_chapter/end_chapter`、`from_chapter/to_chapter`）；`themes` 用顿号连接。编辑态把这两个结构化字段改为「一行一项」的文本框（主线：`名称｜描述`；分段：`a–b｜摘要`），保存时解析回原结构、保留未显示的键；解析失败才提示格式错误。保留现有「保留未知字段」语义（测试 `test_synopsis_structured_field_errors_and_preservation` 要相应调整）。
  - 后端 `breakdown_plan.py` `_prose`/`_render_export`：梗概键名映射为中文（logline 一句话梗概、theme 主题、core_conflict 核心冲突、main_threads 主线、arc_summaries 分段梗概、synopsis 梗概、genre 类型、tone 基调、themes 主题）；list/dict 不再 `json.dumps`，按上面的规则逐项输出为 `- ` 行；`foreshadowing`/`timeline` 同样逐项输出，dict 用「中文字段名：值」子项，不出现 JSON 键名与大括号。`模型：` 用 `{'qwen': '千问', 'deepseek': 'DeepSeek', 'claude': 'Claude'}` 映射，可附模型号。`_inline` 与 `exchange_exports._inline` 对齐（不要额外转义 `-`，否则日期变成 `2026\-10\-16`）。补导出测试：断言不含 `main\_threads`、`\[\{`、`模型：qwen`。

### M4（中）③ 总表「定位」英文、「出场的集」未合并区间
- 复现：screens/04 定位列 `main/supporting`，出场的集「第 1 集、第 2 集……第 10 集」；导出同样。
- 修法：`lib/studio-breakdown.ts` 新增 `roleLabel(role)`（main 主要人物、supporting 配角、major 重要、minor 次要，其他原样）与 `formatEpisodeRanges(nos)`（连续合并：`第 1–3、5–6、10 集`），`BibleTable.tsx:38` 使用；后端 `breakdown_plan.py` 加同样两个纯函数用于 `_render_export :516,518`，并补单测。

### M5（低）④ 进度条配色
- 修法：`BreakdownPanel.tsx:55` 不再用原生 `<progress>`，改为 `<div role="progressbar" aria-label="拆解总进度" aria-valuemin={0} aria-valuemax={chunks.length} aria-valuenow={complete} className="h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--slip)]"><div className="h-full rounded-full bg-[color:var(--ink2)] transition-[width]" style={{ width: `${pct}%` }} /></div>`，只用现有令牌，不改 `globals.css`。更新 SSR 测试里对「拆解总进度」的断言。

### M6（低）⑤ 每集时长输入框过宽
- 修法：`BreakdownPanel.tsx:47-50` 把最短/最长/大约几集三个输入排成一行：每个 `w-28`（或 `max-w-32`），标签在上，后面紧跟一个 `readout` 显示「约 3.0–4.0 分钟」；窄屏 `flex-wrap` 自然换行。去掉 `flex-1 basis-32`。

### M7（中）重新拆解时旧 partial 拆解的预留不释放，且界面上再也无法释放
- 现象：旧拆解处于 `partial`（有批失败或 uncertain），作者不重跑而是点「重新报价拆解」。`start()` 只拒绝 `running`（`breakdown.py:167-169`），直接新建 breakdown 并把 `project.breakdown_id` 切过去（`:191`）。旧拆解里 `blocked/queued` 批对应的 `studio_jobs` 仍是 `queued` 并持有 `reserved_amount`；`uncertain` 批的 hold 也仍在。界面只显示当前拆解，旧批的「取消」「释放」按钮消失。
- 取证（临时探针，已删）：paste 项目，text_map 批 `failed`/`uncertain` 两种情况下重新报价并 start 后，旧 group 的 jobs 为 `[('text_map','failed'/'uncertain', ¥0.272), ('synopsis','queued', ¥0.143), ('episode_plan','queued', ¥0.295)]` 仍占预留，`spend.today().committed_cny` 从 0.711 变为 1.422（= 旧 hold + 新报价全额）。人民币 hold 占到当日结束；Claude 的 uncertain hold 计入当月 `brain_month_used`，会一直占到月底。
- 修法：`breakdown.start()` 在同一事务里，对项目当前 breakdown（`project['breakdown_id']`，若存在且 ≠ 新建）：
  1. 若其任一批 job 状态为 `uncertain` → 409「上一次拆解还有结果不确定的批，请先核账释放后再重新拆解」；
  2. 否则对其 `queued/blocked` 批执行与 `cancel()` 相同的释放（`transition(queued→cancelled)` + chunk `cancelled`），并把旧 breakdown 标为 `cancelled`（`partial` 的旧结果仍保留在表中，符合「旧的保留」）。
  前端：`BreakdownPanel` 在 `partial` 且点「重新报价拆解」前的报价 dialog 里加一句「上一次拆解未执行的批次将取消并释放预留」。补测试：重新 start 后旧 group 不再有 `queued` job、`reserved_amount` 全为 0；有 uncertain 时 409。

## 3. 可优化项

- **O1 `get_current` 每次轮询都做全量重算与重写**（`breakdown.py:430` 每次 GET 调 `refresh`，`refresh` 里 `_insert_units` DELETE+INSERT 全部单元、`_insert_bible` 逐条 SELECT/UPDATE、改写 `import_json`）。5 s 一次、每个打开页面各一次，长篇写放大明显。建议：只在「某批 job 状态 ≠ chunk 状态」或 breakdown 为 `running/partial` 时执行物化；`done/cancelled` 且无差异时直接读表。
- **O2 `store._one/_many` 全局 `to_thread`**（`store.py:275-285`）：所有工作室查询（含调度器每 2 s 的 tick）每行都切线程，超出规格「重 I/O 与大文本」的范围，徒增开销。建议回退，只在拆解模块对大 JSON 列（`source_json/import_json/result_json`）做线程化解析（现有 `_decode` 已这么做）。
- **O3 报价 payload 把整部小说正文写进 `studio_quotes.items_json`**（`_make_quote` 的 `plan[].inputs` + `manifest`，`breakdown.py:76-79,97`），每点一次「报价」就多存一份全书；正文又在 `studio_chunks.source_json._inputs` 与 `studio_jobs.params_json` 各存一份。建议报价只存章号/块号与偏移，`start()` 时按 `snapshot_no` 重读快照组装输入（已有 snapshot_no 校验）。
- **O4 `locate_scenes` 未命中回退让「命中的上一场」变成空范围**：`[(0,5),(5,5),(5,15)]`——第 2 场锚点命中却被压成 0 长度，第 3 场（未命中）拿走了它的正文。建议未命中场的 `start` 取「下一个命中锚点的位置」（没有则块末），让命中的场保住自己的文字、未命中的场为空并带 warning，更利于 WO4 截取原文。
- **O5 物化 warning 全挂在第 1 批上**（`breakdown.py:412-415`），界面上看不出是哪一批的锚点没命中。建议把 `locate_scenes`/`merge_bible` 的 warning 按来源批写回对应 chunk，或在 breakdown 级别单列 `warnings`。
- **O6 `partial` 期间作者编辑分集会在补跑完成后被整体替换**（`refresh :408-411` 指纹变化即 `publish_plan`），旧版本虽留在 `studio_plan_revisions`，但界面无提示。建议 `partial/running` 时在分集表上方提示「拆解未全部完成，补跑完成后方案会按新结果重新生成」，或暂时禁用操作菜单。
- **O7 重新拆解一开始，旧方案立刻从界面消失，而「已批准（第 k 版）」仍显示**：`start()` 立即切 `breakdown_id`，`get_episodes` 读新拆解（0 集）但 `g0_approved` 仍按 revision 判定为真。建议 start 时把 `plan_approved_revision` 置 NULL 并写一条 revision（reason `restart`），或在 `_present_episodes` 里 0 集时 `g0_approved=false`。
- **O8 `patch_bible` 把 appearance 清空也会标成 `author`、`needs_author=0`**（`breakdown_plan.py:404-405`）。建议 appearance 为空串时 `appearance_source='none'`、人物 `needs_author=1`。
- **O9 `recover()` 不吞异常**（`breakdown.py:515-523`）：任一 breakdown 的 `refresh` 抛 `HTTPException`（例如项目被删/未来归档、`publish_plan._validate` 422）会让 `recover_studio_jobs` 抛出、进而阻断应用启动（`main.py:131`）。建议逐条 try/except 记日志。
- **O10 预算 409 文案 8 位小数**（`spend.py:105,110,115` `:.8f`）直接显示在 ErrorNotice 里，建议 4 位，与前端 `formatBreakdownMoney` 一致。
- **O11 `BreakdownPanel` 「保存时长」与「报价」两条路径都会 PATCH**，报价时静默改项目默认时长且可能触发 revision+1（`patch_project` 影响已有集时），建议报价 dialog 里提示「每集目标时长将保存为 x–y 秒」。
- **O12 报告 §4 与实际**：报告称两环境全量各 1 failed/5 errors 为沙箱端口问题，主控沙箱外复跑已 0 failed，可信；报告未提 M7 场景与 O1 的写放大，属遗漏。

## 4. 给实现方的二次修改指令（自包含，可直接交给 Codex）

> 工作区 `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`。不新增依赖、不改 `package.json`/lockfile/`requirements.txt`/`globals.css` 令牌、不联网、不提交。所有改动只在下列文件及对应测试里进行；非工作室测试零改动；新前端测试沿用 `backend/tests/test_studio_breakdown_frontend.py` 的 `probe()` 缺依赖 skip 守卫。完成后用仓库虚拟环境跑 `cd backend && python -m pytest -q tests/test_studio_breakdown_*.py tests/test_studio_brain_frontend.py`，再跑 `cd frontend && npm run lint && npx tsc --noEmit && npm run build`（沙箱 Turbopack 失败则补 `-- --webpack`），并在 `03-report.md` 末尾追加「二次修改」一节逐条说明。

1. **分集表操作菜单改为对话框**（`frontend/components/studio/EpisodePlan.tsx`）
   - 删除内联 `<details>` 的 `EpisodeMoreMenu`，改为按钮「更多」+ 原生 `<dialog>`（复用 `sourceDialogClass`，标题「第 n 集 · 操作」，`aria-labelledby`，Esc 可关，只有一个「关闭」按钮，不要确认按钮）。
   - 对话框内六个 `btn btn-quiet min-h-10 w-full text-left` 按钮：修改、与下一集合并、拆分、边界前移一场、边界后移一场、删除（变为未纳入）。点任一项先关闭本对话框再执行；修改/拆分/删除随后打开现有二级 dialog。
   - 禁用规则：无下一集 → 合并与两种移边禁用；本集只有一场 → 拆分与前移禁用；下一集只有一场 → 后移禁用；`next.unit_from !== episode.unit_to + 1`（中间有未纳入）→ 两种移边禁用。
   - 表格与卡片共用同一组件；操作列 `w-20`。操作完成后不得残留打开状态，也不得引起表格容器横向滚动。
   - 更新 `test_episode_operations_revision_split_points_and_approval_dialog` 与 `test_episode_ssr_timing_menus_approval_and_narrow_cards`：断言点「更多」后出现标题「第 1 集 · 操作」的 dialog、六个按钮文字、禁用规则（构造 `unit_from===unit_to` 与不相邻两集各一例）、点击后 dialog 关闭。

2. **部分完成提示指向真正要重跑的批**
   - 后端 `backend/studio/breakdown.py` `get_current`：去掉 `pending_segments`，改为 `retry_needed: [{label, status}]`（status ∈ failed/rejected/invalid_output/released/uncertain 的批）与 `blocked_segments: [label]`（`episode_plan` 且 `blocked`）。
   - 前端 `BreakdownPanel.tsx`：`partial` 时显示「以下批次需要重跑：第 11–14 章 · 补全（被拒绝）；完成后「第 11–14 章 · 分集」会自动继续。完成前不能批准分集方案。」uncertain 的批标注「需先核账释放」。`lib/studio-breakdown.ts` 类型同步。
   - 测试：`test_panel_ssr_unquoted_partial_outdated_and_running` 改断言为上述文字；后端 `test_failure_blocks_manual_release_and_provider_retry` 增加 `retry_needed[0]['label']` 为 text_map 批、`blocked_segments` 为分集批的断言。

3. **梗概展示与导出可读化**
   - 前端 `SynopsisPanel.tsx`：展示态不用 `ContentValue`。`main_threads` → `<ul>` 每项「名称 —— 描述」（键名兼容 `name/title` 与 `description/summary`，缺描述只显示名称）；`arc_summaries` → 每项「第 a–b 章：摘要」（兼容 `from/to`、`start_chapter/end_chapter`、`from_chapter/to_chapter`，缺章号只显示摘要）；`themes` 顿号连接。编辑态这两个字段改为「一行一项」textarea：主线每行 `名称｜描述`，分段每行 `a–b｜摘要`；保存时解析回原数组、保留每项原有的其他键（按顺序对应，多余行新建对象，缺行删除）；解析失败在字段下方 `role="alert"` 提示。`compass` 嵌套与未知顶层字段保留逻辑不变。更新 `test_synopsis_structured_field_errors_and_preservation`（用新格式造一处错行、一处正确保存，断言保存结果结构）。
   - 后端 `backend/studio/breakdown_plan.py`：
     - 新增 `_SYNOPSIS_LABELS = {'logline': '一句话梗概', 'theme': '主题', 'core_conflict': '核心冲突', 'main_threads': '主线', 'arc_summaries': '分段梗概', 'synopsis': '梗概', 'genre': '类型', 'tone': '基调', 'themes': '主题'}`，`_PROVIDER_LABELS = {'qwen': '千问', 'deepseek': 'DeepSeek', 'claude': 'Claude'}`。
     - 重写 `_prose`：dict 的键用中文标签（无映射时原样）；值为 list 时每项一行 `  - …`；项为 dict 时按「主线/分段」规则（同前端）渲染为一行，其他 dict 用「字段：值」以「；」连接；任何情况下不得输出 JSON 括号与引号。`foreshadowing`、`timeline` 也走它。
     - `_render_export` 头部改为 `模型：千问（qwen3.8-max 等模型号可选）`。
     - `_inline` 与 `exchange_exports._inline` 的转义字符集对齐（不转义 `-`）。
     - 测试 `test_markdown_export_escaping_headers_and_worker`：夹具的 synopsis 加入 `main_threads=[{'name': '归家', 'description': '找到灯'}]`、`arc_summaries=[{'from': 1, 'to': 2, 'summary': '离岸'}]`，断言导出含「主线」「归家 —— 找到灯」「第 1–2 章：离岸」「模型：千问」，且不含 `main\_threads`、`\[\{`、`"`。

4. **总表定位中文化、出场的集合并区间**
   - `frontend/lib/studio-breakdown.ts` 新增并导出 `roleLabel(role: string)`（main→主要人物、supporting→配角、major→重要、minor→次要，其余原样）与 `formatEpisodeRanges(nos: number[])`（排序去重后连续合并：`[1,2,3,5,6,10]` → `第 1–3、5–6、10 集`；空数组返回 `未纳入`）。`BibleTable.tsx` 的定位列与出场的集列使用它们。
   - 后端 `breakdown_plan.py` 新增同语义的 `_role_label` 与 `_episode_ranges`，用于 `_render_export` 三张总表。
   - 测试：前端 SSR 测试里 `entry.role='main'`、`episodes=[1,2,3,5]` 断言出现「主要人物」与「第 1–3、5 集」；后端为两个纯函数加参数化单测。

5. **进度条**（`BreakdownPanel.tsx`）：删除 `<progress>`，改为 `role="progressbar"` 的双层 `div`（轨道 `bg-[color:var(--slip)]`、填充 `bg-[color:var(--ink2)]`、`h-1.5 rounded-full`，宽度按 `complete/chunks.length` 百分比，`aria-valuemin/max/now` 与 `aria-label="拆解总进度"`）。SSR 测试断言 `role="progressbar"` 与 `aria-valuenow`。

6. **时长输入布局**（`BreakdownPanel.tsx`）：最短秒数、最长秒数、大约几集三个输入同一行，每个 `w-28`（去掉 `flex-1 basis-32` 与 `max-w-64`），标签在上；行尾 `readout` 显示「约 3.0–4.0 分钟」；容器 `flex flex-wrap items-end gap-3`，窄屏自动换行。现有「60–900 秒，最短不能大于最长」说明保留在下一行。

7. **重新拆解前释放旧拆解的预留**（`backend/studio/breakdown.py` `start()`，`BreakdownQuoteDialog.tsx`）
   - 在 `start()` 事务内、插入新 breakdown 之前：读 `project['breakdown_id']` 对应的旧 breakdown（存在且状态 ≠ `cancelled` 时）。若旧拆解任一批的 job 状态为 `uncertain` → `HTTPException(409, '上一次拆解还有结果不确定的批次，请先核账释放后再重新拆解')`，且不得改动任何数据（含不确认报价——把这个检查放在 `_confirmed_quote` 之前）。否则把旧拆解 `queued/blocked` 批对应的 `queued` job 用 `brain_jobs.transition(db, job, 'queued', {'status': 'cancelled'})` 取消、chunk 置 `cancelled`，旧 breakdown 状态置 `cancelled`（其 units/bible/episodes/plan_revisions 全部保留）。
   - 前端 `BreakdownQuoteDialog`（非重跑模式）在已有拆解且其状态为 `partial` 时多显示一行「上一次拆解未执行的批次将取消并释放预留」。
   - 测试（`test_studio_breakdown_pipeline.py`）：(a) text_map `failed` → partial → 再次 `quote`+`start`：断言旧 group 内没有 `queued` job、`reserved_amount` 全为 0、旧 breakdown 状态 `cancelled`、`spend.today().committed_cny` 等于新报价 `total_max` 加旧 failed 批应占金额；(b) text_map `uncertain` → 再次 `start` 得 409、报价仍为 `open`、项目 `breakdown_id` 未变。

8. **两处顺手项（低成本，建议一并做）**：`spend.py` 三条 409 文案改为 4 位小数；`patch_bible` 中 `appearance` 为空串时写 `appearance_source='none'`，人物 `needs_author=1`（补一条测试）。

9. 完成后在 `03-report.md` 追加「二次修改」小节：列出改动文件、每条对应上面的编号、两种环境测试结果与前端三项结果；重拍 screens/06、07、10 对应场景的截图放到 `screens/` 下（文件名加 `-v2`）。
