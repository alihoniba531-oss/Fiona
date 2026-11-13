# 短片工作室「边写边拆」R1 返修报告

- 依据：`docs/tasks/2026-11-12-studio-serial-breakdown/02-spec.md` §4.8 R1 返修（v1.2）
- r0 基线：HEAD `135253f` + r0 工作区改动；R1 前已将 r0 整树快照到 `/tmp/studio-serial-r0`
- 结论：§5 第 1–7 条全部通过；R1 白名单外文件与 r0 快照逐字节一致（仅 gitignored 的 `frontend/tsconfig.tsbuildinfo` 为构建产物，已恢复为 r0 内容）。

## 拆分表

| 轮次 | agent | 负责的文件 | 结果 |
|---|---|---|---|
| R1 第一轮 | backend | `backend/studio/sources.py`、`backend/studio/breakdown.py`、`backend/studio/breakdown_plan.py` | 完成 R1-P1–P4；定向 204 passed + casting 36 passed + r0 续拆 35 passed；P1/P2/P3 临时探针 3 passed 后删除 |
| R1 第一轮 | frontend | `frontend/components/studio/BreakdownPanel.tsx`、`frontend/components/studio/EpisodePlan.tsx` | 完成 R1-P5/P6；`tsc --noEmit` EXIT 0，改动文件 eslint 0；旧 serial 前端用例因“新增”标签期望未更新而 46 passed / 1 failed，属 R1-T11 预期同步项 |
| R1 第一轮 | docs | `CLAUDE.md`、`docs/ARCHITECTURE.md`、`docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md` | 完成 R1-P7/D1；`CLAUDE.md` 67,350 B（≤67,400）；report.md 新增 17 行「文档改动位置」表并注明 `ARCHITECTURE.md:505` 保留不改 |
| R1 第二轮 | test-continue | `backend/tests/test_studio_serial_continue.py` | 完成 R1-T1–T10；新收集 43（r0 35 + 8），43 passed；12 处自检全部变红后还原（T4/T10 各两处） |
| R1 第二轮 | test-frontend | `backend/tests/test_studio_serial_frontend.py` | 完成 R1-T11；新收集 22（r0 21 + 1），22 passed；3 处自检全部变红后还原 |

无返修轮。所有测试 agent 的自检临时改动均未留在最终结果；实现文件最终与 `/tmp/studio-serial-r0` 的差异只有 R1-P1–P6。

## 1. R1-P1–P7 逐条对应

### R1-P1 续拆进行中拒绝同步

- `backend/studio/sources.py` 新增 `_continuation_in_progress(db, project, owner)`：按 `studio_projects.breakdown_id` 查 `studio_breakdowns`（带 `owner`），仅当 `status in {'running','partial'}` 且 `import_json._continuations` 非空时返回 True；`import_json` 为空、非 dict 或解析失败返回 False，不抛 500。
- `_save_snapshot` 写事务内、原「导演模型任务进行中」检查之后加入检查，409「续拆进行中，完成后再同步」。
- `sync_source` 事务外、原同一检查之后加入同一检查与同一文案。
- 原有 job 检查顺序/文案未改；两处检查都保留，覆盖事务外快速拒绝和写事务内并发复核。
- 覆盖测试：R1-T8。

### R1-P2 快照读不出时拆解视图降级

- `breakdown.get_current` 读取当前快照 `sources._read_manifest` 时捕获 `HTTPException`、`OSError`、`ValueError`；失败时 `manifest=None`，`changed_covered=[]`、`continuable=False`、`continue_from/to=None`，`warnings` 末尾追加「当前快照无法读取，暂不能续拆，请到来源面板重新检查」。
- `stale_chapters` 仍从 `_chapter_basis` 计算；`continuations`、`continuing` 等字段照旧。`retry`、`cancel`、`continue_start` 返回 `get_current` 的路径不再 500。
- 覆盖测试：R1-T9。

### R1-P3 已续拆过的旧方案视图始终按已发布单元过滤

- `breakdown_plan.get_episodes`：过滤条件由 `_continuing(breakdown)` 改为 `breakdown['imported'].get('_continuations')` 非空；`continuing` 返回值仍按 `_continuing` 的 running/partial 语义。
- `breakdown_plan.export_markdown`：同样改为已发布拆解的 `_continuations` 非空时按 `_published_max_seq` 过滤 `units`。
- 续拆发布后 `_published_max_seq` 等于最大 seq，过滤不改变结果；续拆 partial 后整本重拆时旧方案视图/导出不再把本轮新单元算进「未纳入」。
- 覆盖测试：R1-T10（视图与导出两条自检）。

### R1-P4 `_insert_bible` 防御

- `_insert_bible` 插入新行后改为 `row_by_id[identifier] = await _one(db, 'SELECT * FROM studio_bible WHERE id=?', (identifier,))`，同一连接、同一事务读回完整行，不再使用 7 键精简 dict。
- 覆盖测试：R1-T3（自动 uuid5 条目 + 定妆 approved 的重名路径）。

### R1-P5 按钮层级

- `BreakdownPanel.tsx` 原有整本报价按钮（「重新报价拆解」/「报价」）className 改为 `breakdown?.continuable ? "btn btn-quiet min-h-10" : "btn btn-primary min-h-10"`；其它按钮、disabled、onClick、文案、位置不变。
- 覆盖测试：R1-T11 第 2 点。

### R1-P6 表格「新增」标签间距

- `EpisodePlan.tsx` 的 `addedTag` 接受第二个类名参数；表格视图调用 `addedTag(episode, "tag ml-2")`，卡片视图调用 `addedTag(episode, "tag")`；文案、`data-serial`、结构不变。
- 覆盖测试：R1-T11 第 3 点。

### R1-P7 `CLAUDE.md` 体积

- CLAUDE.md 原续拆段落 2,061 B 压缩为 490 B 的六项要点：适用范围与条件、两个接口、同一份拆解追加且总表/定妆/声线保留、发布后重新批准、进行中不能取消也不能同步、不支持次要来源。
- 细节保留在 `docs/ARCHITECTURE.md:507/509`；`ARCHITECTURE.md:507` 补了续拆进行中不能取消也不能同步的 409 细节。
- 为满足 67,400 B 上限，同时收紧了 CLAUDE.md 186/188/192/196 中已经存在于 ARCHITECTURE.md 的实现细节（不丢事实）。
- 最终 `wc -c CLAUDE.md` = **67,350**（基线 66,525，上限 67,400，余量 50 B）。

## 2. R1-T1–T11 逐条对应

### R1-T1 快照范围证明力（MF1）

- 改 `test_continuation_execution_reads_bound_snapshot_and_keeps_old_units`：新增 `prefixed_body()`，快照 2 的第 3 章改为「改过的开头。」+ `changed_body(3)`，改动落在旧批 range 以内；`changed_body` 本身未改。
- 保留并加强「`_source_inputs` 读回快照 1 原文（第 3 章）」「refresh 后旧单元 start/end/label 不变」；新增断言快照号 2、单元数增加。
- 自检：`_source_inputs` 改成 `snapshot_no = breakdown['snapshot_no']`；目标用例 1 failed（读到带「改过的开头。」的文本），还原后 1 passed。

### R1-T2 partial 不发布的真正守卫（MF2）

- 新增 `test_continuation_two_segment_partial_publishes_once_after_retry`：同步到第 16 章，只让第 16 章 `novel_complete` 失败，第一段分集批成功、第二段 blocked；断言 `plan_revision` 与集数不变、`appended_from is None`。
- 单批重跑后：revision 只加 1、新集齐全、`appended_from == 3`。
- 原单段 partial 用例保留，原覆盖未丢。
- 自检：`refresh` 续拆分支 `if status == 'done':` 改成 `if status in {'done','partial'}:`；目标用例 1 failed（partial 时 revision 已加 1，`2 == 1`），还原后 1 passed。

### R1-T3 冻结条目跳过退役（MF3）

- 改 `test_continuity_duplicate_active_names_warn_and_insert`：两条重名行之一为第 0 轮模型输出的自动 uuid5 条目，且其 `studio_items.status='approved'`；另一条作者 create_bible 手建；快照 2 书斋圣经登记同名 `ref_id='C2'`。
- 在 `continue_start` 后与 drain 后各断言：自动条目 `merged_into is None`、`casting.is_orphaned` 为假、定妆仍 approved；新行与「与总表里多个同类条目重名」warning 照常出现，活动行 3 条、无合并。
- 自检：`_insert_bible` 退役循环去掉 `old['id'] in frozen`；目标用例 1 failed（自动条目被合并、id 不在活动行集合），还原后 1 passed。

### R1-T4 续拆确认的计费/未结束批次守卫（MF4）

- 新增三条用例：
  - `test_continue_start_rejects_expired_quote`：过期后 409「报价已过期，请重新报价」，chunks/jobs/预留总额不变，报价仍 open；
  - `test_continue_start_rejects_exhausted_budget`：报价后 `FIONA_STUDIO_DAILY_CNY='0.0001'`，409 含「今日额度不足」，计数不变，报价仍 open；
  - `test_continue_start_rejects_unfinished_batches`：报价后插入 queued probe job，409「拆解还有未结束的批次」，计数不变，报价仍 open。
- `test_continue_start_appends_round_and_keeps_old_state` 增加 `studio_quotes.status == 'confirmed'`。
- 自检两遍：①`_confirmed_quote(...)` 换成 `payload = preview`，过期用例 `DID NOT RAISE HTTPException`；②未结束批次查询加 `AND 0`，probe 用例 `DID NOT RAISE HTTPException`；两次均还原后复跑 1 passed。

### R1-T5 别名并集

- 改 `test_continuity_keeps_author_created_character`：create_bible「船夫」带别名 `['老船夫']`，续拆后新批输出「船夫」；确认后与 drain 后都断言该行别名仍含「老船夫」、只有一条活动行、id 不变、不是孤儿。
- 自检：转向条目别名改成只取新条目别名；目标用例 1 failed（`assert '老船夫' in []`），还原后 1 passed。

### R1-T6 只改名

- 改 `test_continuity_keeps_author_renamed_character`：第 0 轮自动条目「阿禾」改名「禾生」，快照 2 的书斋圣经**不**登记这个人物，新批输出「禾生」；断言只有一条活动行、id 不变、`ref_id is None`、别名仍含「阿禾」、不是孤儿（bible 与 casting 两处）。
- 原「改名 + 书斋登记 C2」的输入按 R1-T6 改为只改名；`ref_id == 'C2'` 断言因输入变化删除，属规格指定的改正。
- 自检：活动行名字/别名匹配改为 `matched = False`；目标用例 1 failed（出现两条活动行，`2 == 1`），还原后 1 passed。

### R1-T7 跨新旧交界

- 新增 `test_continuation_appended_from_follows_moved_boundary`：续拆发布后、批准前用 `move_boundary(no=2, delta=1)` 把最后一个旧集终点挪进新单元；断言第 2 集终点进入新单元、`appended_from` 等于第一个 `unit_to >= _appended_from_unit` 的集号（==2）。
- 自检：`get_episodes` 的 `unit_to >= marker` 临时改成 `>`；目标用例 1 failed（`assert 3 == 2`），还原后 1 passed。

### R1-T8 P1 的 partial 无活动 job 路径

- 新增 `test_continuation_partial_without_active_jobs_blocks_sync`：让本轮最后一个分集批失败（第 16 章），partial 且组内无 queued/running job；`sync_source` 409「续拆进行中，完成后再同步」，快照号不变；done 后同步成功，快照号 +1。
- 自检：`_continuation_in_progress` 顶部临时 `return False`；目标用例 `DID NOT RAISE HTTPException`，还原后 1 passed。

### R1-T9 P2 的视图降级

- 新增 `test_current_view_degrades_when_manifest_unreadable`：改坏当前快照 `manifest_sha256`；`get_current` 正常返回、`continuable False`、warning 含「当前快照无法读取」；对同一拆解 `cancel` 正常返回 done，单元不变。
- 自检：`get_current` 的 manifest 读取 `except (HTTPException, OSError, ValueError)` 临时改为 `except ()`；目标用例 1 failed（`HTTPException: 500: 作品快照校验失败`），还原后 1 passed。

### R1-T10 P3 的旧方案视图/导出过滤

- 新增 `test_rebreakdown_published_view_excludes_unpublished_continuation_units`：续拆 partial（新单元已落库、未发布）后整本报 `quote/start`；已发布方案视图的 `unassigned/uncovered` 为空、units 只到 10；导出「未纳入」为「无」，不含「第 6 章第 1 场」。
- 自检两遍：①`get_episodes` 过滤条件退回 `_continuing(breakdown)`，视图含 11–16 单元；②导出过滤临时不生效，导出含「第 6 章第 1 场 – 第 8 章第 2 场」；两次均还原后 1 passed。

### R1-T11 前端

- 改 `test_panel_changed_covered_line_only_when_nonempty_even_when_not_continuable`：非 continuable 与 continuable 两种情况下「在拆解之后改过」整句都只出现一次，continuable 时短语也只出现一次。
- 新增 `test_panel_whole_book_quote_button_tier_follows_continuable`：continuable 真 → `btn btn-quiet min-h-10`；假 → `btn btn-primary min-h-10`；无 breakdown 的「报价」→ primary。
- 改 `test_episode_plan_added_tags_only_on_new_episodes_in_both_views`：表格标签精确为 `tag ml-2`（3 个，裸 tag 0 个）；卡片精确为 `tag`（3 个，`tag ml-2` 0 个）；单新增例表格/卡片各 1 个；无新增例两种标签都不出现；原数量和行位置断言保留。
- 自检 3 遍（P5 按钮 class、P6 表格 tag、重复句守卫），分别 1 failed 后还原，最终 22 passed；自检后实现文件 sha 与备份一致。

## 3. R1-D1 文档改动位置

- `docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md` 新增 `### 2.1 文档改动位置（R1-D1）`（约 125–149 行），17 行表，覆盖：
  - `CLAUDE.md:186`、`188`、`192`、`194`（R1-P7 压缩）、`196`；
  - `README.md:359`、`361`、`363`、`369`、`394`、`396`；
  - `docs/ARCHITECTURE.md:412`、`416`、`418`、`507`（新段落）、`509`；
  - `PLAN.md:525`（「2026-11-12：工作室续拆」新节）。
- 表中附注 `docs/ARCHITECTURE.md:505` 核对后保留不改：该处只写整本拆解的单批重跑与取消规则，没有错误陈述；续拆取消/同步例外写在紧随其后的 507。
- 行号按 R1-P7 编辑后的最终文件核对；README/PLAN 本轮未改，沿用当前行号。

## 4. 测试与验收结果

### 收集数

```
tests/test_studio_serial_sources.py: 23 tests collected in 0.72s
tests/test_studio_serial_continue.py: 43 tests collected in 0.80s
tests/test_studio_serial_frontend.py: 22 tests collected in 0.04s
全量: 8352 tests collected in 7.49s
```

8352 = 8264 + 88（23 + 43 + 22）。

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

告警仍只在既有 `frontend/app/page.tsx` 与 `frontend/app/plaza/page.tsx`；本次改动文件无告警。

### §5.3 `cd frontend && npm run build`

```
BUILD_EXIT:0
...
○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

### §5.4 后端全量

```
cd backend && [NO_PROXY 前缀] .venv/bin/python -m pytest -q -p no:cacheprovider -rs
```

```
8352 passed, 37 warnings in 406.67s (0:06:46)
EXIT:0
```

0 failed、0 skipped；passed 数 = 8264 + 88。

### §5.5 无 `frontend/node_modules` 副本

```
copydir=$(mktemp -d /tmp/studio-serial-copy.XXXXXX)
rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' <worktree>/ "$copydir"/
cd "$copydir/backend" && .venv/bin/python -m pytest -q -p no:cacheprovider -rsf \
  tests/test_studio_serial_sources.py tests/test_studio_serial_continue.py tests/test_studio_serial_frontend.py
```

```
..................................................................ssssss [ 81%]
ssssssssssssssss                                                         [100%]
SKIPPED [22] tests/test_studio_sources_frontend.py:21: frontend dependencies unavailable: typescript, react, react/jsx-runtime, react-dom/server
66 passed, 22 skipped, 35 warnings in 10.86s
EXIT:0
```

0 failed；`SKIPPED` 行求和 = 22，等于新前端文件里起 node 的 22 条用例；副本已删除。

### §5.6 改动集合

`git status --porcelain --untracked-files=all`（含本报告）：

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
?? docs/tasks/2026-11-12-studio-serial-breakdown/04-review.md
?? docs/tasks/2026-11-12-studio-serial-breakdown/05-fix-r1.md
?? docs/tasks/2026-11-12-studio-serial-breakdown/impl/report-r1.md
?? docs/tasks/2026-11-12-studio-serial-breakdown/impl/report.md
```

- R1 白名单改动：`CLAUDE.md`、`docs/ARCHITECTURE.md`、`backend/studio/sources.py`、`breakdown.py`、`breakdown_plan.py`、`frontend/components/studio/BreakdownPanel.tsx`、`EpisodePlan.tsx`、三个新测试文件、`impl/report.md`、新 `impl/report-r1.md`。
- `README.md`、`PLAN.md`、其它 r0 文件、既有测试均未被 R1 改动；`git status` 中的 `M` 是 r0 既有改动。
- 与 `/tmp/studio-serial-r0` 的 `diff -qr`（排除 `.git`、`.venv`、`node_modules`、`.next`、`__pycache__`）只显示上述 R1 白名单文件；`frontend/tsconfig.tsbuildinfo` 是 gitignored 构建产物，已恢复为 r0 内容。
- `docs/tasks/...` 下 01–05 是派单方预置文件，未修改。

### §5.7 AST 只读锁

```
..                                                                       [100%]
2 passed in 0.96s
EXIT:0
```

`studio/**` 没有新增 `novel.*` 导入，全文没有 §4.2 第 8 条禁止文字。

### 目标测试文件最终结果

```
tests/test_studio_serial_sources.py
tests/test_studio_serial_continue.py
tests/test_studio_serial_frontend.py
88 passed, 35 warnings in 12.72s
EXIT:0
```

## 5. 自检变红输出摘要

自检前把实现文件备份到 `/tmp/r1-selfcheck-*` 并记录 sha256；每次改一处，跑最窄目标用例，确认红后恢复并复跑绿。

| 条目 | 临时改坏点 | 目标用例 | 变红摘要 | 还原 |
|---|---|---|---|---|
| R1-T1 | `_source_inputs` 用 `breakdown['snapshot_no']` | `test_continuation_execution_reads_bound_snapshot_and_keeps_old_units` | 1 failed；读回文本含「改过的开头。」，与快照 1 原文不等 | sha/cmp 一致，1 passed |
| R1-T2 | `refresh` 续拆分支 `if status == 'done'` → `in {'done','partial'}` | `test_continuation_two_segment_partial_publishes_once_after_retry` | 1 failed；`assert 2 == 1`（partial 已加 revision） | sha/cmp 一致，1 passed |
| R1-T3 | 退役循环去掉 `old['id'] in frozen` | `test_continuity_duplicate_active_names_warn_and_insert` | 1 failed；自动条目 id 不在活动行集合（被合并） | sha/cmp 一致，1 passed |
| R1-T4a | `continue_start` 的 `_confirmed_quote(...)` → `payload = preview` | `test_continue_start_rejects_expired_quote` | 1 failed；`DID NOT RAISE HTTPException` | sha/cmp 一致，1 passed |
| R1-T4b | 确认时未结束批次查询加 `AND 0` | `test_continue_start_rejects_unfinished_batches` | 1 failed；`DID NOT RAISE HTTPException` | sha/cmp 一致，1 passed |
| R1-T5 | 转向条目别名只取新条目别名 | `test_continuity_keeps_author_created_character` | 1 failed；`assert '老船夫' in []` | sha/cmp 一致，1 passed |
| R1-T6 | 活动行名字/别名匹配改为 `matched = False` | `test_continuity_keeps_author_renamed_character` | 1 failed；`assert 2 == 1`（出现两条活动行） | sha/cmp 一致，1 passed |
| R1-T7 | `get_episodes` 的 `unit_to >= marker` → `>` | `test_continuation_appended_from_follows_moved_boundary` | 1 failed；`assert 3 == 2` | sha/cmp 一致，1 passed |
| R1-T8 | `_continuation_in_progress` 顶部 `return False` | `test_continuation_partial_without_active_jobs_blocks_sync` | 1 failed；`DID NOT RAISE HTTPException` | sha/cmp 一致，1 passed |
| R1-T9 | `get_current` manifest 读取 `except (...)` → `except ()` | `test_current_view_degrades_when_manifest_unreadable` | 1 failed；`HTTPException: 500: 作品快照校验失败` | sha/cmp 一致，1 passed |
| R1-T10a | `get_episodes` 过滤退回 `_continuing(breakdown)` | `test_rebreakdown_published_view_excludes_unpublished_continuation_units` | 1 failed；`unassigned/uncovered` 含 11–16 单元 | sha/cmp 一致，1 passed |
| R1-T10b | 导出过滤临时不生效 | 同上 | 1 failed；导出「未纳入」含「第 6 章第 1 场 – 第 8 章第 2 场」 | sha/cmp 一致，1 passed |
| R1-T11-P5 | 整本报价按钮 class 改回固定 `btn-primary` | `test_panel_whole_book_quote_button_tier_follows_continuable` | 1 failed；actual `btn-primary` vs expected `btn-quiet` | sha/cmp 一致，1 passed |
| R1-T11-P6 | 表格 `addedTag` 改回 `"tag"` | `test_episode_plan_added_tags_only_on_new_episodes_in_both_views` | 1 failed；`table added tags must be tag ml-2` / `0 !== 3` | sha/cmp 一致，1 passed |
| R1-T11-一次 | BreakdownPanel 去掉 `!breakdown.continuable &&` 守卫 | `test_panel_changed_covered_line_only_when_nonempty_even_when_not_continuable` | 1 failed；`2 !== 1` | sha/cmp 一致，1 passed |

最终 `sha256sum` / `cmp` 确认：
- `backend/studio/breakdown.py`、`breakdown_plan.py`、`sources.py` 与自检前备份一致；
- `frontend/components/studio/BreakdownPanel.tsx`、`EpisodePlan.tsx` 与自检前备份一致。

## 6. 未完成或需人工确认的地方

1. **`CLAUDE.md` 余量只有 50 B**：P7 压缩后 67,350 B（上限 67,400）。为同时满足字节上限，docs agent 收紧了 CLAUDE.md 186/188/192/196 中已存在于 ARCHITECTURE.md 的实现细节；六项续拆要点与其它事实均保留，但若作者希望 CLAUDE.md 保留更多原文，需要放宽 67,400 B 上限或再删其它内容。
2. **P1 检查顺序**：`sync_source` 和 `_save_snapshot` 都按规格把「续拆进行中」加在「导演模型任务进行中」之后。因此续拆 partial 且仍有 blocked 批的 queued job 时，同步先返回「导演模型任务进行中，完成后再同步」；只有组内没有 queued/running 等 job 时才命中新的「续拆进行中，完成后再同步」。R1-T8 按此覆盖无活动 job 的路径，符合 §4.8 P1 的位置要求。
3. **快照损坏时日志偏吵**：R1-P2 只让 `get_current` 降级；`sources._read_manifest` 仍按原逻辑记完整异常栈，5 秒轮询会重复记录。功能与测试不受影响，未在本批改日志。
4. **`frontend/tsconfig.tsbuildinfo`**：被 `.gitignore` 忽略的 tsc 构建产物，验收前已从 r0 快照恢复字节；R1 交付不包含该文件。
5. **无 §6 阻塞**：未发现规格与源码事实矛盾；没有修改 §4.6 未授权的既有测试；R1 白名单外没有留下改动。
