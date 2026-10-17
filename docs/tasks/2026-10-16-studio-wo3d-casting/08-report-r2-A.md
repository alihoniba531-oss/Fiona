# WO3d 返修 R2-A 报告：后端编排（派生合并、归档、孤儿、条目默认、单事务确认）

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 依据：`08-fix-r2-common.md`（公共口径）+ `08-fix-r2-A.md`（本块清单）；复核报告 `04-review.md` 的「必须修复 1/2/4/5」「可优化 a–m」「存疑 1」
- 性质：只改代码与测试。未提交、未推送、未联网、未读 `.env`、未动 `frontend/node_modules`、未改 R2-B / R2-C 的文件。
- 改动文件（8 个，全部在允许清单内）：
  - `backend/studio/casting.py`
  - `backend/studio/casting_jobs.py`
  - `backend/studio/store.py`
  - `backend/routers/studio.py`
  - `backend/tests/test_studio_casting_api.py`
  - `backend/tests/test_studio_casting_jobs.py`
  - `backend/tests/test_studio_casting_integration.py`
  - `backend/tests/test_studio_casting_migration.py`

## 0. 结果速览

| 项 | 文件:行 | 对应测试 |
|---|---|---|
| 必须修复 4 / 可优化 d 孤儿判定 | `casting.py:121-125` | `test_rebreakdown_orphans_old_items_and_blocks_paid_paths` |
| 必须修复 2 归档规则 | `casting.py:633-646` | `test_approve_archive_rules_and_g1` |
| 必须修复 1 / 5 派生合并 + 条目常驻默认 | `casting.py:436-469`、`471-533` | `test_sheets_merge_item_defaults_with_batch_input`、`test_sheets_quote_stores_only_explicit_references_and_caps_merged`、`test_sheets_start_creates_one_job_per_sheet_and_confirms_once`、`test_reference_plan_uses_approved_version_and_caps`、`test_reference_plan_dedupes_approved_listed_as_explicit_reference`、`test_derive_without_approved_version_is_rejected_without_paid_call`、`test_derived_reference_is_first_deduped_and_png` |
| 可优化 a 单事务确认报价 + 建任务 | `casting.py:535-568`、`casting_jobs.py:272-329` | `test_start_sheets_revalidates_and_keeps_quote_open`、`test_prepare_jobs_uses_caller_transaction_and_schedules_only_on_demand` |
| 可优化 b 执行前复核 + 预检转 rejected | `casting.py:516-533`、`casting_jobs.py:401-435` | `test_start_sheets_revalidates_and_keeps_quote_open`、`test_reference_unavailable_is_rejected_before_paid_call` |
| 可优化 c 试听 ffmpeg/ffprobe 预检 | `casting.py:40`、`698-717` | `test_cosyvoice_audition_requires_ffmpeg_tools` |
| 可优化 e skip / reopen 清空选定 | `casting.py:623-631` | `test_skip_and_reopen_clear_approved_version` |
| 可优化 f 自定义风格非空 | `casting.py:395-397` | `test_custom_style_requires_name_and_visual_style` |
| 可优化 g（后半）running 不悬挂 | `casting_jobs.py:358-398` | `test_execute_settles_when_job_read_fails_after_running` |
| 可优化 i / 存疑 1 参考图统一 PNG | `casting_jobs.py:171-183` | `test_reference_bytes_sync_always_outputs_png`、`test_derived_reference_is_first_deduped_and_png` |
| 可优化 j 资产部分唯一索引 | `store.py:238-248` | `test_item_version_unique_index_blocks_duplicates`、`test_fresh_database_initializes_twice`、`test_git_baseline_legacy_database_upgrades_and_keeps_rows` |
| 可优化 k 清理文件前查引用 | `casting_jobs.py:512-547` | `test_commit_failure_keeps_file_still_referenced_by_another_asset` |
| 可优化 m（前半）locked_features 600 | `casting.py:35,580`、`routers/studio.py:236` | `test_patch_locked_features_caps_at_600` |

## 1. 必须修复 4（+ 可优化 d）：孤儿判定加入 ``bible.breakdown_id``

- 改法：`casting.py:121-125` `is_orphaned(bible, breakdown_id)` 在原有「总表行缺失 / 已归档 / 已合并」之外，追加
  `return bool(breakdown_id) and bible.get("breakdown_id") != breakdown_id`。
- 调用侧：`_item_public` / `_load_items` / `_single_item` 都从 `studio_projects.breakdown_id`（或 `get_episodes()["breakdown_id"]`）取当前拆解并传入，
  于是孤儿条目 `orphaned=true` 且被 `_g1()`（`casting.py:173-179` 只统计非孤儿）排除；`quote_sheets` / `start_sheets` / `audition` 的复核与预检都走 `is_orphaned` → 409。
- 测试：`test_rebreakdown_orphans_old_items_and_blocks_paid_paths`（`test_studio_casting_api.py:709`）重新拆解后断言
  旧条目 `orphaned=true`、新条目 `false`、`g1.total=1`、旧条目报价 409、试听 409，且「报价后重拆解 → start 409 且报价保持 open、0 任务」。
- 反证：把 `is_orphaned` 末尾改回 `return False`，该用例 `1 failed`（旧总表条目不再是孤儿，`g1.total` 变 3）；改回即通过。

## 2. 必须修复 2：归档接口收紧

- 改法：`casting.py:633-646` `archive_asset` 增加两道门：
  - `if not asset.get("item_id") or asset.get("role") not in ("sheet", "audition")` → 409「只能归档条目下的定妆版本或试听」（挡掉上传图、i2v 首帧等非条目级素材）；
  - `if item is not None and asset_id in (item.get("approved_asset_id"), item.get("voice_asset_id"))` → 409「已选定（定档）的版本不能归档，请先换选定」（同时覆盖修复前漏掉的 `voice_asset_id`）。
- 测试：`test_approve_archive_rules_and_g1`（`test_studio_casting_api.py:780`）断言已选定版本归档 409、换选定后可归档；
  `test_skip_and_reopen_clear_approved_version`（`:742`）断言清空选定后该版本即可归档。
- 反证：同时去掉两道门后 `test_approve_archive_rules_and_g1` `1 failed`（已选定版本被 200 归档）；改回即通过。

## 3. 必须修复 1 / 5：派生合并 + 条目级常驻默认

产品口径（公共说明）：条目卡保存的 `extra_prompt` / `reference_asset_ids` 是**常驻默认**；批量栏输入只对本批生效并追加 / 合并去重；
报价里**只存显式参考图** + `derive_from_approved` 标志；执行期单点合并「已选定排第一 + 去重」；合并后 >4 张报价 422；无已选定却勾派生 409。

- 改法（`casting.py`）：
  - `436-437` 新增 `_dedupe(ids)`（`dict.fromkeys` 保序去重）。
  - `440-469` 新增 `_sheet_plan(db, item, bible, owner, pid, *, breakdown_id, extra_prompt, reference_asset_ids, derive_from_approved)`：
    孤儿 409 → 缺外形 409 → 批量参考 >4 张 422 → `explicit = _reference_assets(db, _dedupe(defaults + batch))`（常驻 + 本批合并去重，并校验归属本项目）→
    `derive` 且无 `approved_asset_id` → 409 → 张数校验按 `merged = _dedupe([approved, *explicit]) if derive else explicit` → `extra_prompt = " ".join(常驻, 本批)`。
    返回值里 `reference_asset_ids` 只放 `explicit`，另带 `derive_from_approved`。
  - `471-514` `quote_sheets` 用 `_require_g0` 取 `breakdown_id`，逐条走 `_sheet_plan`，报价落库的 `items_json` 因此只含显式参考图与派生标志。
  - `516-533` 新增 `_revalidate_sheet_item`：`start_sheets` 执行前按**当前库状态**再复核一次（孤儿 409 / 缺外形 409 / 参考图仍在 404 / 派生前提 409 / 合并 >4 张 422），返回执行期 `plan`。
  - 执行期合并去重在 `casting_jobs._reference_plan`（`casting_jobs.py:453-472`）：`derive` 时 `approved` 排第一并标 `derived=True`，随后追加显式参考且跳过已在列表里的 id，>4 → `too_many_references`，`notes` 与 id 同序。
  - 两处相反口径的断言已统一：`test_studio_casting_api.py` 的 `test_sheets_start_creates_one_job_per_sheet_and_confirms_once`（`:452`）与
    `test_studio_casting_jobs.py` 的 `test_reference_plan_uses_approved_version_and_caps`（`:343`）都按「报价只存显式、执行期合并」写。
- 测试：
  - `test_sheets_merge_item_defaults_with_batch_input`（`test_studio_casting_api.py:513`）：常驻默认不填批量栏也生效；批量栏补充追加在后、参考图与常驻合并去重；job `params` 与报价行一致。
  - `test_sheets_quote_stores_only_explicit_references_and_caps_merged`（`:545`）：显式 3 + 派生（合并 4）报价 200 且只存显式 3；显式 4 + 派生（合并 5）报价 422；无已选定勾派生 409；全程 0 出图请求、0 任务行。
  - `test_derived_reference_is_first_deduped_and_png`（`test_studio_casting_integration.py:971`）：跑通真实块 B / 块 C、只换传输恒——先出一版并批准，再报价 2 版「派生 + 显式里重复带上已选定」；断言 Seedream 请求体 `image` 恰好 2 张（已选定排第一、重复被去掉）、两个版本各自落库并记录 `[approved, reference]`、且 URIs 逐张是 PNG。
  - `test_reference_plan_uses_approved_version_and_caps`、`test_reference_plan_dedupes_approved_listed_as_explicit_reference`、`test_derive_without_approved_version_is_rejected_without_paid_call`（jobs 侧，见 §6）。
- 反证：把 `_sheet_plan` 回退成「参考图只用批量栏、不合并常驻、不带派生标志」，三条用例 `3 failed`（常驻默认丢失 / 报价没存派生 / 集成断言崩）；改回即通过。

## 4. 可优化 a：确认报价与建任务同一个 ``BEGIN IMMEDIATE``

- 改法：
  - `casting_jobs.py:272-312` 新增 `prepare_jobs(db, project, owner, *, kind, media_provider, quote_id, entries)`：把原来 `create_jobs` 的事务体抽出，**在调用方已开启的写事务里**做预留 + 建任务行，不新开事务、不排程。
  - `casting_jobs.py:314-318` 新增 `schedule_jobs(jobs)`：逐个 `_schedule(job["id"])`。
  - `casting_jobs.py:320-343` `create_jobs` 保持原签名与外部行为（空 `entries` 直接 `return []` 不开事务、未知 `kind` 先 `ValueError`），内部改成「开事务 → `prepare_jobs` → 出事务 → `schedule_jobs`」。
  - `casting.py:535-568` `start_sheets` 在**一个** `store.connection(transaction=True)` 里完成：项目校验 → 报价读取 / 用途 / 状态 / 过期 / 额度 → 逐条 `_revalidate_sheet_item` → `UPDATE quote status='confirmed'` → `prepare_jobs`；出事务后才 `schedule_jobs`，最后 `return await state(...)`。
- 测试：`test_prepare_jobs_uses_caller_transaction_and_schedules_only_on_demand`（`test_studio_casting_jobs.py:566`）验 `prepare_jobs` 不自行提交 / 不排程、`schedule_jobs` 才排程；`test_create_jobs_keeps_signature_and_skips_empty_entries`（`:595`）守旧行为。
  `test_start_sheets_revalidates_and_keeps_quote_open`（`test_studio_casting_api.py:578`）在事务**中途**注入失败（`prepare_jobs` 抛 409「今日额度不足」，即并发撞日上限的真实形态），断言报价仍 `open`、0 任务、随后同一张报价仍能确认。
- 反证：在 `start_sheets` 的 `UPDATE` 后插一句 `await db.commit()`（模拟「先提交 confirmed、再另开事务建任务」的旧结构），该用例 `1 failed`（报价被烧成 `confirmed`）；删除即通过。
- 说明：用例里另有「`FIONA_STUDIO_DAILY_CNY=0.1` → 409 且报价 open」的分支，它走的是 `check_quote_budget`（`UPDATE` 之前），因此它验证的是额度语义而**不能**区分单/多事务；真正钉住原子性的是上面那条注入失败的分支。

## 5. 可优化 b / c / f / m、g 后半、i

- **b 预检不落 uncertain + `start_sheets` 重校验**：
  - `casting_jobs.py:163-169` 新增 `_reference_errors()`（收敛 `HTTPException` / `UnidentifiedImageError` / `OSError` / `ValueError` / `SyntaxError` / 解压炸弹），
    `401-435` `_run_image` 里 `store.get_asset` 与 `_reference_bytes` 的异常一律转 `PreflightError("reference_unavailable"/"reference_unreadable")`，都在付费请求之前；
    `execute` 的 `_classify`（`:384-390`）把 `PreflightError` 判为 `rejected` 并释放预留。
  - `casting.py:516-533` `_revalidate_sheet_item` 让 `start_sheets` 在确认前重校验引用（归档 / 缺失的参考图直接 404/409，报价保持 open）。
  - 测试：`test_reference_unavailable_is_rejected_before_paid_call[archived|missing]`（`test_studio_casting_jobs.py:411`）、`test_start_sheets_revalidates_and_keeps_quote_open`。
  - 反证：把 `_revalidate_sheet_item` 的 `_reference_assets(...)` 换成不校验的 `list(...)`，后一条用例 `1 failed`（归档参考图不再被拦）；改回即通过。
- **c 试听 ffmpeg/ffprobe 预检**：`casting.py:40` 新增 `AUDIO_TOOLS = ("ffmpeg","ffprobe")`，`698-717` `audition` 先校验全部变体，若含 cosyvoice 则 `shutil.which` 逐个查，缺 → **503** 且不建任务、不发付费请求（`import shutil` 见 `:12`）。
  测试：`test_cosyvoice_audition_requires_ffmpeg_tools`（`test_studio_casting_api.py:907`）覆盖「纯 cosyvoice 503 / 混合批次 503 且 0 任务 / edge-tts 照常建任务 / 0 付费调用」。
  反证：去掉该预检块，该用例 `1 failed`；改回即通过。
- **f 自定义风格非空**：`casting.py:395-397` `put_style` 在 `_clean_fields` 后要求 `name` 与 `visual_style` 非空，否则 422（路由 `StyleFieldsBody` 各字段仍默认 `""`，空串会走到业务层）。
  测试：`test_custom_style_requires_name_and_visual_style`（`test_studio_casting_api.py:335`）覆盖空 / 仅空格 / 缺字段三种 API 入参与两条直连业务函数断言（不靠 Pydantic 兜）。反证：去掉该检查 → `1 failed`。
- **m 前半 locked_features ≤ 600**：业务层 `casting.py:35` `MAX_LOCKED_FEATURES = 600`（`:571-580` 超限 422），路由层 `routers/studio.py:236` `locked_features` 的 `max_length` 由 2000 收紧为 600 作纵深防御。
  测试：`test_patch_locked_features_caps_at_600`（`test_studio_casting_api.py:763`）断言 API 600 通过 / 601 → 422，并直连 `patch_item` 断言 422。
  反证：把 `MAX_LOCKED_FEATURES` 改回 2000 → `1 failed`；只回退路由字段（业务层仍 600）→ 仍通过，说明路由那一格是冗余防线，真正被钉住的是业务层上限。
- **g 后半 running 不悬挂**：`casting_jobs.py:358-398` `execute` 去掉 CAS 前的重复预读（CAS 自带 `queued` 条件），把置 running 之后的 `store.get_job` 及后续全部移进 `try`，
  `_fail(job_id, token, status, code, message)` 只按 `job_id` 定位（读不到行也能结算），`CancelledError` 仍 `asyncio.shield` 置 `uncertain`。
  测试：`test_execute_settles_when_job_read_fails_after_running`（`test_studio_casting_jobs.py:431`）。反证见 §6。
- **i / 存疑 1 参考图统一 PNG**：`casting_jobs.py:171-183` `_reference_bytes_sync` 无论输入 mode 都 `save(buffer, "PNG")`（带 alpha → RGBA，其余 → RGB，长边 >1536 等比缩放不变），与 `image_seedream._reference_uris` 恒标的 `data:image/png` 一致。
  测试：`test_reference_bytes_sync_always_outputs_png`（`test_studio_casting_jobs.py:458`）、集成用例的逐张 PNG 断言。反证见 §6。

## 6. 可优化 j / k、jobs 侧改动（子代理 Dirac / Nash 的产出与证据）

- **j 资产部分唯一索引**（Nash，`store.py:238-248`）：`_ADDED_COLUMN_INDEXES` 追加
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_studio_assets_item_version ON studio_assets(item_id,role,version_no) WHERE item_id IS NOT NULL`，随 `migrate_schema` 在补列之后建，沿用既有的「表不存在则跳过」守卫。
  测试：`test_item_version_unique_index_blocks_duplicates`（`test_studio_casting_migration.py:231`，非空 `item_id` 拒重复、`NULL` 行不参与约束），并在 `assert_upgraded` / `test_fresh_database_initializes_twice` 补索引存在断言（新旧库都建得出）。证据：改前 7 failed、改后 7 passed。
- **k 清理文件前查引用**（Dirac，`casting_jobs.py:512-547`）：`_commit_asset` 提交失败时先 `db.rollback()`，再用新只读连接跑 `_asset_path_referenced(rel_path)`，确认无引用才 `_discard_file`；查询异常按「仍有引用」保守处理。
  测试：`test_commit_failure_keeps_file_still_referenced_by_another_asset`。
- **g 后半 / i / b / 派生去重的 jobs 侧反证**（Dirac 把 `casting_jobs.py` 临时还原为改动前版本、只跑本文件）：`8 failed / 16 passed`，失败点分别为
  `paid["calls"]["references"]` 4 张 vs 3 张（未去重）、`'succeeded' == 'rejected'`（无选定 + derive 仍出图）、`'uncertain' == 'rejected'`（归档 / 缺失参考图落 uncertain）、
  `RuntimeError: db read failed` 逸出（任务停在 running）、PNG 签名断言 False（RGB 走 JPEG）、`discarded == [rel_path]`（误删仍被引用的文件）、`AttributeError: no attribute 'prepare_jobs'`；恢复后 `24 passed`。

## 7. 测试结果

命令与结果（本机，ffmpeg / ffprobe 可用）：

```
cd backend && <py> -m pytest -q tests/test_studio_casting_api.py tests/test_studio_casting_jobs.py \
  tests/test_studio_casting_integration.py tests/test_studio_casting_migration.py
# → 63 passed（基线 44 passed；本次 +19：api 8、jobs +9 例、integration 1、migration 1，另有 1 处参数化）
```

```
cd backend && <py> -m pytest -q tests/ -k studio
# → 1574 passed, 5550 deselected
```

新增 / 同步的用例：api `test_custom_style_requires_name_and_visual_style:335`、`test_sheets_merge_item_defaults_with_batch_input:513`、
`test_sheets_quote_stores_only_explicit_references_and_caps_merged:545`、`test_start_sheets_revalidates_and_keeps_quote_open:578`、
`test_rebreakdown_orphans_old_items_and_blocks_paid_paths:709`、`test_skip_and_reopen_clear_approved_version:742`、
`test_patch_locked_features_caps_at_600:763`、`test_cosyvoice_audition_requires_ffmpeg_tools:907`，并统一 `test_sheets_start_creates_one_job_per_sheet_and_confirms_once` 的口径；
jobs `test_reference_plan_dedupes_approved_listed_as_explicit_reference:367`、`test_derive_without_approved_version_is_rejected_without_paid_call:393`、
`test_reference_unavailable_is_rejected_before_paid_call:411`、`test_execute_settles_when_job_read_fails_after_running:431`、
`test_reference_bytes_sync_always_outputs_png:458`、`test_commit_failure_keeps_file_still_referenced_by_another_asset:474`、
`test_prepare_jobs_uses_caller_transaction_and_schedules_only_on_demand:566`、`test_create_jobs_keeps_signature_and_skips_empty_entries:595`；
integration `test_derived_reference_is_first_deduped_and_png:971`；migration `test_item_version_unique_index_blocks_duplicates:231`。

逐项「旧代码失败 / 新代码通过」的复现方式见第 1–6 节各条的「反证」（每项都做了临时回退 → 对应用例失败 → 恢复 → 通过；恢复后文件与备份逐字节一致）。

## 8. 未完成 / 存疑

- **可优化 l（试听条数上限）**：公共说明列入「不做」，本轮未做。
- **缩略图生成**：公共说明列入「不做」，留给 WO5；R2-C 只加懒加载。
- **可优化 g 前半（Seedream 总超时）**：属 R2-B（`providers/image_seedream.py`），本块未碰。
- **可优化 m 后半（`casting_prompts.py` 提示词 ≤1800）**：属 R2-B，本块只改了 PATCH 入口的 600 字上限。
- **路由层 `locked_features` 的 `max_length`**：属纵深防御，单独回退它不会让用例变红（业务层仍 600）——如需「每一格都被钉住」，可补一条只走 Pydantic 的 schema 断言。
- **可优化 j 的已知风险**：若某个旧库已存在重复的非空 `(item_id, role, version_no)` 行，新建唯一索引会失败，`init_db` 会中断。R2-A 未处理该场景（迁移测试只覆盖「旧库无该表列」与「重复插入被拒」两种形态）；如线上存在此类数据，需先人工去重。
- **必须修复 1 的报价口径**：`04-review.md` 给的是「二选一」，本块按公共说明选了「报价只存显式参考图 + `derive_from_approved`」，并让执行期单点合并去重；`test_studio_casting_api.py` 与 `test_studio_casting_jobs.py` 的历史相反断言已同时改到这个口径。
- 未做真实 Ark / CosyVoice 冒烟（不联网、无 Key）：参考图统一 PNG 与 `data:image/png` 标签的一致性已在单测与集成层（假传输）验证，真实上游是否校验格式仍待带 Key 冒烟确认（沿用 `04-review.md` 存疑 1 的处置）。
