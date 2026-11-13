# 短片工作室「边写边拆」实施报告

- 规格：`docs/tasks/2026-11-12-studio-serial-breakdown/02-spec.md` v1.1（作者已确认）
- 基线：`135253f`
- 分支：`feat/studio-serial-breakdown`
- 工作树：专用 worktree（分支 `feat/studio-serial-breakdown`）
- 结论：§5 第 1–7 条全部通过；无主代理派发的返修轮。

## 拆分表

| 轮次 | agent | 负责的文件 | 结果 |
|---|---|---|---|
| 第一轮 | sources | `backend/studio/sources.py`；`backend/studio/novel_chat.py`（只改 `start_film` 复用分支）；`backend/services/claude_agent.py`（只改 `:125`、`:845`）；`backend/intent_router.py`（只改 `:148`）；`backend/.env.example`（只改 `:231`）；授权既有测试 `backend/tests/test_studio_sources.py`、`test_novel_chat.py`、`test_novel_chat_feedback.py`；新文件 `backend/tests/test_studio_serial_sources.py` | 完成。定向 4 文件 + 新文件 322 passed；新文件单独 23 passed，0 skipped；无 §6 阻塞 |
| 第一轮 | breakdown | `backend/studio/breakdown.py`、`breakdown_material.py`、`breakdown_plan.py`；`backend/routers/studio.py`（只加两个续拆路由） | 完成。定向拆解/定妆 353 passed，`test_studio_breakdown_plan_review.py` 另 4 passed；临时自检 3 passed 后已删除；无 §6 阻塞 |
| 第一轮 | studio-ui | `frontend/lib/studio.ts`、`frontend/lib/studio-breakdown.ts`、`frontend/components/studio/BreakdownPanel.tsx`、`BreakdownStage.tsx`、`BreakdownQuoteDialog.tsx`、`EpisodePlan.tsx`、`SourcePanel.tsx`、`SourceChoices.tsx`、`CreateProjectDialog.tsx` | 完成。`tsc --noEmit` EXIT 0；改动文件 eslint 0；`test_studio_breakdown_frontend.py` 26 passed，加 sources 前端 19 passed |
| 第一轮 | novel-ui | `frontend/components/novel/NovelWorkbench.tsx`、`NovelFilmDialog.tsx`；`frontend/components/NovelFeedbackCard.tsx`（只改 `:397` 半句）；授权既有测试 `backend/tests/test_studio_sources_frontend.py`（只改 `:118` 用例体）、`test_novel_chat_feedback_frontend.py`（只改 `WRITTEN_DESCRIPTION`） | 完成。`tsc --noEmit` EXIT 0；三个改动文件 eslint 0；两条前端测试 132 passed |
| 第一轮 | docs | `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md` | 完成。四份文档 11 条旧陈述 0 命中、所需新增 token 全部存在；`git diff --check` EXIT 0 |
| 第二轮 | test-continue | 新文件 `backend/tests/test_studio_serial_continue.py` | 完成。35 个用例全绿（`35 passed`）；未改实现；未发现实现问题；无 §6 阻塞 |
| 第二轮 | test-frontend | 新文件 `backend/tests/test_studio_serial_frontend.py` | 完成。21 个用例全绿（`21 passed`）；未改实现；未发现实现问题；无 §6 阻塞 |

无返修轮。第一轮各 agent 在自测中修正的是自己范围内的测试/实现细节；第二轮两个测试 agent 均未修改实现或既有测试。

## 1. 修改了哪些文件

### 1.1 `git status --porcelain --untracked-files=all` 原文

写报告后的最终状态：

```
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/intent_router.py
 M backend/routers/studio.py
 M backend/services/claude_agent.py
 M backend/studio/breakdown.py
 M backend/studio/breakdown_material.py
 M backend/studio/breakdown_plan.py
 M backend/studio/novel_chat.py
 M backend/studio/sources.py
 M backend/tests/test_novel_chat.py
 M backend/tests/test_novel_chat_feedback.py
 M backend/tests/test_novel_chat_feedback_frontend.py
 M backend/tests/test_studio_sources.py
 M backend/tests/test_studio_sources_frontend.py
 M docs/ARCHITECTURE.md
 M frontend/components/NovelFeedbackCard.tsx
 M frontend/components/novel/NovelFilmDialog.tsx
 M frontend/components/novel/NovelWorkbench.tsx
 M frontend/components/studio/BreakdownPanel.tsx
 M frontend/components/studio/BreakdownQuoteDialog.tsx
 M frontend/components/studio/BreakdownStage.tsx
 M frontend/components/studio/CreateProjectDialog.tsx
 M frontend/components/studio/EpisodePlan.tsx
 M frontend/components/studio/SourceChoices.tsx
 M frontend/components/studio/SourcePanel.tsx
 M frontend/lib/studio-breakdown.ts
 M frontend/lib/studio.ts
?? backend/tests/test_studio_serial_continue.py
?? backend/tests/test_studio_serial_frontend.py
?? backend/tests/test_studio_serial_sources.py
?? docs/tasks/2026-11-12-studio-serial-breakdown/01-brief.md
?? docs/tasks/2026-11-12-studio-serial-breakdown/02-spec.md
?? docs/tasks/2026-11-12-studio-serial-breakdown/03-dispatch.md
?? docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md
```

最后一行是本报告本身；`01/02/03` 是派单方预置文件。

`docs/tasks/2026-11-12-studio-serial-breakdown/` 下的 `01-brief.md`、`02-spec.md`、`03-dispatch.md` 是派单方事先放好的未跟踪文件，本次没有修改或删除。

### 1.2 与 §4.1 白名单逐条对照

| 文件 | 白名单依据 | 改动 |
|---|---|---|
| `backend/studio/sources.py` | §4.1；§4.2 | 资格、快照范围、签名、组装范围、漂移、来源状态、候选 |
| `backend/studio/novel_chat.py` | §4.1；§4.5 第 4 条 | 只改 `start_film` 复用已有项目分支的 `points` |
| `backend/services/claude_agent.py` | §4.1；§4.5 第 1、2 条 | 只改 `:125` 与 `:845` 两句 |
| `backend/intent_router.py` | §4.1；§4.5 第 3 条 | 只改 `:148` 一句 |
| `backend/.env.example` | §4.1；§4.5 第 5 条 | 只改 `:231` 一句 |
| `backend/studio/breakdown.py` | §4.1；§4.3 T3–T6 | 续拆辅助函数、报价、确认、读原文、分集输入、发布、取消守卫、视图 |
| `backend/studio/breakdown_material.py` | §4.1；§4.3 T2 | `batch_plan` 三个偏移参数 |
| `backend/studio/breakdown_plan.py` | §4.1；§4.3 T6 | `get_episodes` 新字段/单元过滤、导出过滤、批准清 `_appended_from_unit` |
| `backend/routers/studio.py` | §4.1；§4.3 T3/T4 | 只加两个续拆路由 |
| `frontend/lib/studio.ts` | §4.1；§4.4 第 2 条 | 类型补 `stale`/`chapters_done`/`snapshot_chapters` |
| `frontend/lib/studio-breakdown.ts` | §4.1；§4.4 第 1 条 | 类型、两个请求函数、`formatChapterRanges` |
| `frontend/components/studio/BreakdownPanel.tsx` | §4.1；§4.4 第 3 条 | 续拆块、旧章/待复核、取消隐藏、partial 说明 |
| `frontend/components/studio/BreakdownStage.tsx` | §4.1；§4.4 第 4 条 | onContinue 接线、continue 确认分支 |
| `frontend/components/studio/BreakdownQuoteDialog.tsx` | §4.1；§4.4 第 5 条 | continueRange 模式 |
| `frontend/components/studio/EpisodePlan.tsx` | §4.1；§4.4 第 6 条 | `continuing`、`appended_from`、「新增」tag |
| `frontend/components/studio/SourcePanel.tsx` | §4.1；§4.4 第 7 条 | 漂移/快照待复核、连载提示 |
| `frontend/components/studio/SourceChoices.tsx` | §4.1；§4.4 第 8 条 | `SerialSourceHints`、`chaptersDone`、快照落后提示 |
| `frontend/components/studio/CreateProjectDialog.tsx` | §4.1；§4.4 第 10 条 | 只改空态整句 |
| `frontend/components/novel/NovelWorkbench.tsx` | §4.1；§4.4 第 11 条 | `filmReady` 与按钮/对话框条件 |
| `frontend/components/novel/NovelFilmDialog.tsx` | §4.1；§4.4 第 9 条 | 渲染 `SerialSourceHints`、传 `chaptersDone` |
| `frontend/components/NovelFeedbackCard.tsx` | §4.1；§4.4 第 12 条 | 只改 `:397` 半句 |
| `backend/tests/test_studio_sources.py` | §4.6 第 1 条 | 只改授权的 6 处 |
| `backend/tests/test_studio_sources_frontend.py` | §4.6 第 1 条 | 只改 `:118` 用例体 |
| `backend/tests/test_novel_chat.py` | §4.6 第 1 条 | 只改 `:116` 复用分支期望 |
| `backend/tests/test_novel_chat_feedback.py` | §4.6 第 1 条 | 只改 `WRITTEN_SENTENCE` 对应半句 |
| `backend/tests/test_novel_chat_feedback_frontend.py` | §4.6 第 1 条 | 只改 `WRITTEN_DESCRIPTION` 对应半句 |
| `backend/tests/test_studio_serial_sources.py` | §4.1 新测试 | 新增 23 条 |
| `backend/tests/test_studio_serial_continue.py` | §4.1 新测试 | 新增 35 条 |
| `backend/tests/test_studio_serial_frontend.py` | §4.1 新测试 | 新增 21 条 |
| `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md` | §4.1、§4.7 | 文档更新 |
| `docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md` | §4.1 报告 | 本报告（写完后新增） |

白名单外没有留下任何改动。

## 2. 实现了哪些功能

- **小说来源资格与快照（T1）**：资格只看「故事圣经非空 → `chapters_done ≥ 1` → `is_editing` 为假且 `config._rearchive` 不存在」，不看书的 status、不要求完结/全部 done/无 stale。快照范围固定为第 1 到 `chapters_done` 章，`maximum` 必须是 0–300 的整数，否则 409「作品章节范围无效」且不读章节。签名改为 `bible_version`、`chapters_done`、`_rearchive` 和已写章状态。stale 章照收，manifest 保留 `status`。漂移新增 `stale`/`chapters_done`，来源快照新增 `stale`，候选新增 `stale` 与 `snapshot_chapters`。
- **续拆切批（T2）**：`batch_plan(..., start_chapter=1, segment_base=0, no_base=0)`；默认参数输出与基线逐字节一致；续拆只切新增章、段号接在现有最大段号后、批号接在现有最大批号后；依赖和 `map_nos` 只在返回前统一偏移；次要来源传非默认值抛 `ValueError`。
- **续拆报价（T3）**：新增 `continue_quote(pid, owner)` 和 `POST /studio/projects/{pid}/breakdown/continue/quote`，固定 409 文案，只按新章切批、按拆解 settings 的每集时长、不写 `target_episodes`，报价 `kind='breakdown_continue'`，返回 `continue_from`/`continue_to`。
- **续拆确认（T4）**：新增 `continue_start(pid, owner, quote_id)` 和 `POST …/breakdown/continue/start`。写事务内重读项目/拆解/批/job/旧 `imported`，固定顺序校验报价用途、拆解状态、未结束批次、快照号、`covered_through`；合并新 manifest 的非下划线键、保留 `_` 键；写 `_chapter_basis`/`_manifest`/`_covered_through`/`_published_max_seq`/`_frozen_bible_ids`/`_continuations`/`_published_chunk_ids`；旧批补 `source.snapshot_no`；新批带快照号与轮次；重新物化单元与总表；只更新拆解行，不改项目 `breakdown_id`/`plan_revision`/`plan_approved_revision`、不删集。
- **总表沿用（T4 第 6 步）**：续拆过的拆解在 `_insert_bible` 中按 alias 表、确定性 ID、活动行 `ref_id`/规范化名字/别名匹配；恰好一条并入、不新建、不把旧条目标合并；多条重名新建并写「与总表里多个同类条目重名，请手动合并」；冻结/alias 行不参与退役，已定妆不会变孤儿。
- **执行、衔接与发布（T5）**：`_source_inputs` 使用批自己的 `snapshot_no`；`_dependency_input` 在 round ≥ 1 时不写 `suggested_episodes`，第一个分集批用已发布方案末集衔接，后续段取本轮上一批输出；`prepare_job`/`retry_quote` 读已发布末集；`refresh` 对未续拆保持原发布逻辑并记 `_published_chunk_ids`，对续拆只在 done 且存在未发布成功分集批时把「已发布集 + 本轮新集」交给 `publish_plan(reason='continued')`，记 `_appended_from_unit`（取较小）和 `_published_max_seq`，partial 不发布；`cancel()` 只对续拆 running/partial 返回 409，不影响整本重拆取消未执行批。
- **视图（T6）**：拆解视图新增 `covered_through`/`continuable`/`continue_from`/`continue_to`/`changed_covered`/`stale_chapters`/`continuations`/`continuing`；分集视图新增 `continuing`/`appended_from`，续拆进行中只展示 `seq ≤ _published_max_seq` 的单元，导出 Markdown 同样过滤；批准后清空 `_appended_from_unit`。
- **前端（T7）**：续拆块/报价对话框/Stage 接线/分集「新增」与进行中提示/来源面板待复核与连载提示/`SerialSourceHints`/`ExistingSourceProjects.chaptersDone`/书斋 `filmReady`/修改意见卡半句；所有新增元素带 `data-serial=""`，自身和祖先无粗体类。
- **聊天文案（T8）**：Claude `start_film` 工具描述、Claude 修改意见卡回复、平台意图 `novel_to_film`、`.env.example` 注释、`start_film` 复用卡片四行规则。
- **测试（T9）**：新增三个测试文件共 79 条；按 §4.6 第 1 条只改授权既有测试。
- **文档（T10）**：四份文档的资格/快照/做成片/同步/续拆陈述改对；`CLAUDE.md` WO3c 段末续拆说明；`PLAN.md` 新增「2026-11-12：工作室续拆」一节（含不做事项与 §7 已知局限）。

### 2.1 文档改动位置（R1-D1）

按 R1-P7 编辑后的最终行号填写；`README.md`、`PLAN.md` 本轮未改，沿用当前行号。

| 文件:行号 | 原陈述类别 | 改后要点 |
|---|---|---|
| `CLAUDE.md:186` | 小说来源资格：已完结、圣经齐全、各章 done、无 stale 才可建项目 | 改为圣经非空、`chapters_done ≥ 1`、不在修改中即可，不要求完结/全部 done/无 stale，也不看书的 status；flags 只提示 |
| `CLAUDE.md:188` | 快照只做整本、同步后只能整本重拆 | 快照只收第 1 到 `chapters_done` 章、忽略其后进行中行、stale 章照收并保留 `status`；来源面板加待复核章检测（范围 0–300 与越界 409 的细节留在 `ARCHITECTURE.md:412`） |
| `CLAUDE.md:192` | 拆解视图与快照同步后的唯一出路 | 拆解视图加续拆视图；同步后只标 `outdated`、不自动作废 G0；续拆字段与 `appended_from` 明细移到 `ARCHITECTURE.md:507`、`509`，不在此重复 |
| `CLAUDE.md:194`（新段落，R1-P7 压缩） | 新增续拆说明（原 2,061 B） | 压缩为六项要点：适用条件、两个接口、同一份拆解追加且总表/定妆/声线保留、发布后重新批准、进行中不能取消也不能同步、次要来源不支持；压缩后段落 490 B，全文 67,350 B（≤67,400） |
| `CLAUDE.md:196` | 做成片只对已完结的书；复用项目行为 | 改为有故事圣经、至少一章、不在修改中即可，不要求完结；复用已有项目不自动同步，卡片写快照版本/章数，落后时提示同步后可续拆 |
| `README.md:359` | 小说工坊仅显示已完结、各章完成、无待复核/改稿的书 | 有故事圣经、至少写好一章、不在修改中即可，不要求完结；待复核照收并标记，连载只收已写好章；做成片入口放宽，完结横幅不变 |
| `README.md:361` | 快照内容与同步后的拆解出路 | 快照只收第 1 到 `chapters_done` 章、stale 照收并在清单保留状态；已拆部分保留，新章可在拆解页续拆 |
| `README.md:363` | 聊天做成片的条件与复用卡片 | 改为有故事圣经、至少一章、不在修改中，不要求完结；复用时不会自动同步，卡片写快照版本与章数，落后时提示同步后可以续拆 |
| `README.md:369` | 改较早的章会把后续章标「待复核」、不能做成片 | 改为「短片工作室照收，会标出待复核」 |
| `README.md:394` | 整本拆解报价与每集时长 | 补续拆另走续拆报价、不填「大约几集」、每集时长沿用原拆解 |
| `README.md:396` | 同步后只能整本重新拆解；续拆行为 | 补续拆按钮、只拆新增章并为新增章付费、保留旧单元/作者改过的分集/已定的妆；同一拆解追加、发布后重新批准并标「新增」、进行中不能取消/同步，partial 单批重跑或整本重拆 |
| `docs/ARCHITECTURE.md:412` | WO3b 只读边界与作品资格（completed/全 done/无 stale） | 改为圣经非空、`chapters_done ≥ 1`、不在修改中；快照读第 1..`chapters_done` 章（0–300，越界 409），签名与复查字段同步更新 |
| `docs/ARCHITECTURE.md:416` | 来源状态/同步后的拆解出路 | 漂移、快照、候选补 `stale` 与 `chapters_done`；快照只收已写章、stale 照收；同步只标 `outdated`，可续拆或整本重拆，不自动作废 G0 |
| `docs/ARCHITECTURE.md:418` | 聊天做成片条件与复用分支 | 改为至少一章、有故事圣经、不在修改中，不要求完结；复用项目不自动同步，卡片四行规则与快照版本/章数提示补全 |
| `docs/ARCHITECTURE.md:507`（新段落） | 无（新增续拆实现段） | 新增续拆报价/确认、追加同一拆解、总表沿用与冻结、发布/`appended_from`、旧单元过滤；R1-P7 后补「进行中不能取消也不能同步」的 409 细节 |
| `docs/ARCHITECTURE.md:509` | 拆解/分集视图与同步后出路 | 加续拆视图、`appended_from`/`continuing`、续拆块与 G0 行为、旧单元过滤、改过旧章/待复核章提示；保留「重新拆解」入口 |
| `PLAN.md:525`（新节） | 无（新增「2026-11-12：工作室续拆」） | 记录资格/快照放宽、续拆接口与追加/计费/总表/发布规则、前端文案、本期不做与已知局限 |

注：`docs/ARCHITECTURE.md:505` 核对后保留不改。复核确认该处只写整本拆解的单批重跑与取消规则，没有错误陈述；「续拆进行中不能取消」的例外写在紧随其后的 `:507`，故不重复改 505。

## 3. 与规格任务清单逐项对应

| 任务 | 状态 | 主要落点 |
|---|---|---|
| T1 来源与快照 | 完成 | `sources.py` 的 `_eligibility`、`_all_chapters`、`_signature`、`_assemble_novel_snapshot`、`_compare_drift`、`source_status`、`_candidate` |
| T2 切批 | 完成 | `breakdown_material.batch_plan` 三个关键字参数与返回前统一偏移 |
| T3 续拆报价 | 完成 | `breakdown.continue_quote` / `_continuation_quote_payload`；`routers/studio.py` 新路由 |
| T4 续拆确认 | 完成 | `breakdown.continue_start` / `_continued_import` / `_insert_bible` 沿用规则 |
| T5 读原文、分集输入、刷新、发布与取消 | 完成 | `_source_inputs`、`_dependency_input`、`_needs_published_last`、`_published_last`、`prepare_job`、`retry_quote`、`refresh`、`cancel` |
| T6 视图 | 完成 | `breakdown.get_current`；`breakdown_plan.get_episodes`/`approve`/`export_markdown` |
| T7 前端 | 完成 | 九个 studio 文件 + 三个 novel/反馈组件；`SerialSourceHints`、`chaptersDone` 按规格签名 |
| T8 聊天文案 | 完成 | `claude_agent.py:125,845`、`intent_router.py:148`、`.env.example:231`、`novel_chat.start_film` |
| T9 测试 | 完成 | 三个新文件 23+35+21；§4.6 授权既有测试 5 个文件 |
| T10 文档 | 完成 | `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md` |

### §4.6 第 1 条授权的既有测试改动

1. `backend/tests/test_studio_sources.py::test_eligibility_rejects_with_reason`：保留六个参数 id 与签名；`running`/`planning`/`stale` 改为可建项目，`planning` 追加真实形状第 3 章，`stale` 同时设 detail 与 `chapters_range` 两侧状态并断言 manifest `status='stale'`；`bible`/`editing` 仍 409；`empty` 改为 `chapters_done=0, chapters=[]`、期望「还没有写好的章节」。未拆分/合并参数化用例。
2. 同文件 `test_candidate_flags_projects_and_exact_title_search`：末尾改为 `title=None, status='setup_running', chapters_done=0, chapters=[]`，补 `reason == '作品还没有写好的章节'`。
3. 同文件 `test_consistent_snapshot_retries_once`：扰动改为第二次 detail 起 `bible_version = state['book']['bible_version'] + 1`；仍 `details == 4`、读两轮；断言 manifest `bible_version == 4`。
4. 同文件 `test_continuous_change_rejected`：扰动改为每次 detail `bible_version = 100 + state['details']`；仍 409「作品正在修改，请稍后再试」、读两轮。
5. 同文件 `test_sync_rejects_ineligible_and_busy_brain`：前半改用 `state['bible']=None`、期望「故事圣经」；后半不动。
6. 同文件 `:243` 漂移精确字典：补 `'stale': []`、`'chapters_done': 3`。
7. `backend/tests/test_studio_sources_frontend.py::test_incomplete_workbench_never_requests_studio`：改为 `chapters_done=0`、`chapters=[]` 的书不请求工作室、不显示做成片；保留原「没有可拆内容时不发请求」意图。
8. `backend/tests/test_novel_chat.py:116`：复用分支期望改为 `["《春山》", "快照第 2 版", "已有项目，打开即可继续"]`。
9. `backend/tests/test_novel_chat_feedback.py` 的 `WRITTEN_SENTENCE`：只随 §4.5 第 2 条改半句。
10. `backend/tests/test_novel_chat_feedback_frontend.py` 的 `WRITTEN_DESCRIPTION`：只随 §4.4 第 12 条改半句。

除以上文件外，没有改动任何既有测试；既有测试文件的收集数保持不变。

## 4. 测试结果（§5 第 1–8 条）

### §5.1 `cd frontend && npx tsc --noEmit`

```
（无输出）
TSC_EXIT:0
```

### §5.2 `cd frontend && npm run lint`

```
✖ 25 problems (0 errors, 25 warnings)
LINT_EXIT:0
```

告警仅来自 `frontend/app/page.tsx`（24 条）与 `frontend/app/plaza/page.tsx`（1 条），全部是基线已有告警；本次新增/改动的文件没有告警。studio-ui 与 novel-ui 另各自对被改动文件跑过 `npx eslint`，均 EXIT 0、无输出。

### §5.3 `cd frontend && npm run build`

```
BUILD_EXIT:0
...
○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

### §5.4 后端全量

命令：

```
cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local \
  .venv/bin/python -m pytest -q -p no:cacheprovider -rs
```

原始结果摘要：

```
8343 passed, 37 warnings in 378.59s (0:06:18)
EXIT:0
```

0 failed、0 skipped；8343 = 基线 8264 + 三个新测试文件 23 + 35 + 21 = 8343。

收集数（`--collect-only -q`）：

```
tests/test_studio_serial_sources.py: 23 tests collected in 0.70s
tests/test_studio_serial_continue.py: 35 tests collected in 0.74s
tests/test_studio_serial_frontend.py: 21 tests collected in 0.04s
全量: 8343 tests collected in 7.09s
```

### §5.5 去掉 `frontend/node_modules` 的副本

做法：

```
copydir=$(mktemp -d /tmp/studio-serial-copy.XXXXXX)
rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' <worktree>/ "$copydir"/
cd "$copydir/backend" && .venv/bin/python -m pytest -q -p no:cacheprovider -rsf \
  tests/test_studio_serial_sources.py tests/test_studio_serial_continue.py tests/test_studio_serial_frontend.py
```

原始结果摘要：

```
..........................................................ssssssssssssss [ 91%]
sssssss                                                                  [100%]
...
SKIPPED [21] tests/test_studio_sources_frontend.py:21: frontend dependencies unavailable: typescript, react, react/jsx-runtime, react-dom/server
58 passed, 21 skipped, 35 warnings in 10.12s
EXIT:0
```

0 failed；`SKIPPED` 每行 n 求和 = 21；与三个新测试文件里起 node 的 21 条（全部来自新的前端测试文件，经共享 `probe` 跳过）一致。副本已删除（`COPY_REMOVED:/tmp/studio-serial-copy.xS5pUy`）。

### §5.6 改动集合

见 §1.1。`git status --porcelain --untracked-files=all` 中除派单方预置的 `01-brief.md`、`02-spec.md`、`03-dispatch.md` 与本报告外，全部改动都在 §4.1 白名单内；既有测试只有 §4.6 第 1 条授权的 5 个文件、10 处改动。

### §5.7 AST 只读锁

命令：

```
cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_studio_sources.py::test_studio_sources_only_call_allowlisted_novel_functions \
  tests/test_studio_sources_readonly_integration.py::test_chat_novel_access_cannot_import_or_call_writer_functions
```

结果：

```
..                                                                       [100%]
2 passed in 0.92s
EXIT:0
```

`studio/**` 没有新增 `novel.*` 导入；全文没有 §4.2 第 8 条禁止的文字。

### 指定既有文件单独复跑

命令：

```
cd backend && NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_studio_sources.py tests/test_studio_sources_frontend.py \
  tests/test_studio_sources_readonly_integration.py tests/test_novel_chat.py \
  tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py \
  tests/test_studio_breakdown_*.py tests/test_studio_casting_*.py \
  tests/test_design_system_gate.py tests/test_desk_contract_frontend.py
```

结果：

```
837 passed, 35 warnings in 67.10s (0:01:07)
EXIT:0
```

### §5.8 报告

即本文件；包含拆分表、T1–T10 对应、授权既有测试及理由、三个新文件收集数、文档改动位置、未完成/需人工确认项。

## 5. 未完成或需人工确认的地方

1. **单章切批标签（规格示例 vs 源码事实，已按「现有写法」处理）**
   §4.3 T2 写「单章写『第 x 章 · …』」，但基线 `135253f` 的 `batch_plan` 无论单章与否都输出「第 x–y 章 · …」（例如 11 章输入得到「第 11–11 章 · 补全」）。本任务要求默认参数输出逐字节相同，测试也以基线行为为准；因此续拆单章批仍输出范围写法。没有既有/新测试按规格示例断言单章省略范围。若作者本意是要单章省略范围，这是基线未有的新需求，需要另行确认是否修改默认输出。

2. **续拆 partial 但本轮没有下游 blocked 批时的 `sync_source`**
   §7/界面文案要求「续拆有批次未完成时不能同步新章」，但 §4.3 T5 只要求把取消守卫放在 `cancel()`；现有 `sync_source` 的 409 来自「组内有 queued/submitting/submitted/running 导演任务」。当失败的恰好是最后一个分集批、没有下游 `blocked` 时，组内可能只剩 failed/uncertain 批，理论上 `sync_source` 不会命中现有 queued 检查。§4.6 第 3 条的 partial 用例按规格构造了「一批失败、下游 blocked」，因此现有检查能返回 409；新增测试也这样覆盖。没有额外在 `sources.sync_source` 增加新的续拆守卫，因为那超出 §4.2/T1 的明确清单；建议作者确认是否需要补一条「续拆 partial 禁止同步」的独立守卫。

3. **兼容旧/合成拆解的防御性回退**
   `_covered_through`/`_chapter_basis` 对没有 `_manifest` 的拆解返回 0/`{}`。这是为保持既有 `test_studio_breakdown_plan.py` 等用裸 `studio_breakdowns` 行构造的测试不红；规格只描述有 `_manifest` 的旧拆解，未禁止该回退。该回退不改变正常拆解行为。

4. **`test_incomplete_workbench_never_requests_studio` 同时清空 `chapters`**
   授权要求是「`chapters_done` 为 0 的书不请求工作室」；实现测试同时设 `chapters=[]`，让夹具书自洽。断言仍保留原意图（不请求 `/studio/`、不显示做成片、`onMakeFilm` undefined）。

5. **`get_current` 每次读取当前快照 manifest**
   为计算 `changed_covered`，拆解视图轮询时会多读一次当前快照 manifest；manifest 损坏时与 `source_status` 一样 500。现有全量测试通过，未做缓存；这是实现选择，已在此说明。

6. **续拆报价的「只收新章」与快照并发**
   `continue_quote` 先读当前快照行与 manifest，再在写报价前复核额度；确认时再次校验项目快照号与 `covered_through`。若报价后快照更新，确认返回「作品快照已更新，请重新报价」，不会按旧快照建批。

7. **白名单外发现的同类旧陈述（未改）**
   `docs/tasks/2026-11-12-novel-feedback/02-spec.md:426`、`docs/tasks/2026-11-12-novel-feedback/verify/results/walk-r1.txt` 仍保留「有待复核章节的书不能做成片」等历史任务记录。它们属于既有任务的规格/验收记录，不在 §4.1/§4.7 白名单，本次按「不改派单方预置/历史文件」处理。当前产品文档（README/CLAUDE/ARCHITECTURE/PLAN）中已无这类陈述。

8. **文档 agent 并行时序**
   docs agent 在 breakdown 的 `continue_quote`/`continue_start` 路由落地前写入文档，返回中已提示；主代理已在最终树中核对两个路由、视图字段、`cancel` 文案与文档一致，未发现需要返修的文档偏差。

9. **未改动派单方文件**
   `01-brief.md`、`02-spec.md`、`03-dispatch.md` 未被修改；工作树中仅以未跟踪文件出现，属于任务输入。

10. **无返修轮、无 §6 阻塞**
    第一轮与第二轮 agent 均未报告必须修改 §4.6 未授权既有测试或规格与源码事实矛盾导致无法继续；上述第 1 点为规格示例与基线行为的差异，按「默认输出逐字节相同」和「按现有写法」处理并记录。
