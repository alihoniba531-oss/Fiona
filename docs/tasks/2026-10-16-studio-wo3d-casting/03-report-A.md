# WO3d 块 A 报告：后端数据与编排

> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
> 范围：§3 数据、§4–§6 流程与路由、§3.5 价格、§3.4 恢复与调度、删号、`CastingState` 组装（§8.3 REST）
> 全部实现与测试离线：无任何真实付费调用、无真实网络、未提交 git；块 B / C 的函数全部延迟导入并 monkeypatch。

## 1. 改了哪些文件

只动了 §9 表中块 A 列出的文件，未触碰块 B / C / D 的任何文件。

| 文件 | 动作 | 内容 |
|---|---|---|
| `backend/studio/store.py` | 只新增 | `studio_projects` 补 4 列（`setup_json / setup_confirmed_at / style_json / style_group_id`）；`studio_assets` 补 3 列（`item_id / version_no / role`）；`studio_jobs` 补 2 列（`media_provider / item_id`）；新表 `studio_items` + 2 个索引；`migrate_schema` 同步补列；`CASTING_JOB_KINDS = ("image","tts")`；`cas_job` 对 image/tts 分派到 `casting_jobs.transition`（不走 i2v 的 `params["resolution"]` 计价）；`link_task` 对 image/tts 返回 409「没有上游任务号」 |
| `backend/studio/casting.py` | **新建** | `CastingState / CastingItem / CastingJob / CastingQuote` 组装、门禁、开工确认、风格报价/启动/选定、出图报价/启动、条目同步/patch/approve/skip/reopen、资产归档、声线试听/定档/音色目录 |
| `backend/studio/casting_jobs.py` | **新建** | image/tts 的建行+预留、状态转换与结算、后台执行、在途 Semaphore、块 B/C 薄封装（延迟导入）、落资产/回滚/清理、`price_for` |
| `backend/studio/pricing.py` | 只新增 | `seedream_price()`（默认 0.30）、`cosyvoice_price_per_10k_chars()`（默认 2.0/万字符）、`estimate_sheets()`、`estimate_speech()`；环境变量 `FIONA_STUDIO_PRICE_SEEDREAM_CNY` / `FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS`；非法值回落默认并告警一次 |
| `backend/studio/spend.py` | 只新增 | `check_quote_budget(db, amount)`：人民币报价的单次上限（409）+ 日上限 |
| `backend/studio/recovery.py` | 只新增分支 | 按 kind 分派：`image / tts` 的 `running / submitting` → `uncertain`（保留预留、`needs_recheck=1`、`next_poll_at=None`），`queued` 不动留给调度器；i2v 与 brain 原逻辑逐字未改 |
| `backend/studio/scheduler.py` | 改 1 行 | `tick()` 里在 `brain_jobs.dispatch_queued()` 之后调用 `casting_jobs.dispatch_queued()`（只排程，不发请求） |
| `backend/database.py` | 改 1 行 | 删号事务的表清单加入 `studio_items` |
| `backend/routers/studio.py` | 只新增 | §8.3 全部 15 条路由 + 请求模型（`extra="forbid"`）+ `_guarded` 错误映射 |
| `backend/tests/test_studio_casting_api.py` | 新建 | 12 例（REST/门禁/报价/归属） |
| `backend/tests/test_studio_casting_jobs.py` | 新建 | 15 例（建行/预留/派发/执行/结算/在途上限/价格） |
| `backend/tests/test_studio_casting_recovery.py` | 新建 | 5 例（恢复与调度补发、i2v/brain 不变） |

`git diff --stat`：`store.py +30`、`pricing.py +60`、`spend.py +9`、`recovery.py +10`、`scheduler.py ±1`、`database.py ±1`、`routers/studio.py +171`；新文件 `casting.py 670` 行、`casting_jobs.py 501` 行。

## 2. 实现了什么（与规格逐项对应）

### 2.1 §3 数据
- `studio_projects`：`setup_json / setup_confirmed_at / style_json / style_group_id`（DDL + `migrate_schema` 同时补）。
- 新表 `studio_items`：字段、CHECK、`UNIQUE(project_id,bible_id)`、外键与 §3.2 完全一致。
- `studio_assets`：`item_id / version_no / role`（`sheet` / `audition` / `reference`），废版沿用 `archived`；`_create_asset` 白名单同步放开这三列。
- `studio_jobs`：`media_provider / item_id`；新 kind `image` / `tts`，`provider` 留占位 `'wan'`，真实提供方看 `media_provider`。
- 删号：`database.delete_account_data` 一并删除 `studio_items`（顺序在 `studio_jobs` 之后、`studio_assets` 之前）。

### 2.2 §2 付费安全（重点）
- 付费只发一次、绝不自动重试；`execute` 内任何未归类异常都按 `uncertain` 保留预留（`_classify` 只认块 B 的 `MediaCallError` 与本地 `PreflightError`）。
- 分类：超时 / 断连 / 5xx / 2xx 解析失败 → `uncertain`（预留保留，`needs_recheck=1`，只能作者手动 `POST /jobs/{jid}/release`）；4xx / 429 → `rejected`（释放预留，0 结算）；审核拒绝 → `failed`（0 结算）。结算口径写在 `casting_jobs.transition`，**不经过** i2v 的 `params["resolution"]` 计价。
- 报价只确认一次：`start_*` 用 `WHERE status='open'` 的 CAS 更新，重复确认 409；15 分钟过期只约束确认。
- 单次上限 `FIONA_STUDIO_MAX_QUOTE_CNY` 与「已用 + 预留 + 本次」日上限都在写事务里校验（`spend.check_quote_budget` / `check_reservation`），超限 409 且不发任何请求。
- 重 I/O 一律 `asyncio.to_thread`：`_save_image`、`_save_audio`、`_inspect_image`、`_reference_bytes`（含 PIL 缩放长边 ≤1536）、`_discard_file`。

### 2.3 §3.4 恢复与调度（重点）
- `recovery.recover_studio_jobs()` 按 kind 分派：`image / tts` 的 `submitting / running` 转 `uncertain`（`needs_recheck=1`、`next_poll_at=None`、保留 `reserved_amount`）；`queued` 保持 `queued`，由 `StudioScheduler.tick()` → `casting_jobs.dispatch_queued()` 补发，恢复过程 0 次付费调用。
- i2v 与 brain 的恢复分支逐字未改（既有测试全过）。
- 在途独立于调度器：每个 `media_provider` 一个 `Semaphore`（seedream 3、cosyvoice 2、edge-tts 2；`FIONA_STUDIO_MAX_INFLIGHT_IMAGE / _TTS` 覆盖，合法 1–10，非法回落默认并告警一次）。
- `store.list_jobs` 仍只返回 i2v（按 §3.4 保持不变）；定妆任务经 `GET /casting` 的 `jobs` 字段返回（在途全部 + 最近 50 条已结束）。

### 2.4 §4 开工确认与风格
- `PUT /setup`：先校验 G0 已批准（`breakdown_plan.get_episodes` 的 `g0_approved`），再校验 resolution/video_model/language，写 `setup_json` + `setup_confirmed_at`；重新确认覆盖，不动已出的定妆。
- 风格提案：复用 WO3a `style_proposals` 导演任务与 schema，**绑定当前项目**（`style_group_id` 写回项目，不走「没绑定就新建项目」旧路径）；输入由块 C 的 `casting_prompts.style_inputs(...)` 组装（梗概、人物/场景/道具名与外形摘要、集数与总时长、开工确认语言）；先报价（15 分钟、确认一次），确认后 `start_trial` 执行。
- `GET /casting` 的 `style.proposals` 读该 group 的成功结果；`PUT /style` 支持 `proposal_index` 或 `custom`，`realism` 必填（`photoreal / anime / 3d`）。

### 2.5 §5 定妆出图
- `POST /sheets/quote`：条目 ≤30、合计 ≤60 张、每项版本 1–4、`extra_prompt ≤500`、参考图 ≤4；人物条目 `needs_author` 为真时 409 并点名；`derive_from_approved=true` 时把已选定版本作为第 1 张参考图并去重；报价 = 张数 × 单价，写 quote（只存条目 id / 版本数 / 参考图 asset id / 估价，不存图片字节）。
- `POST /sheets/start`：确认一次；为**每一张图**建一条 `kind='image'` 任务并预留，`create_jobs` 后逐条立即派发。
- 执行：块 C `build_sheet_prompt(...)` 组装 → 读参考图字节（线程、≤1536）→ 块 B `generate_sheet(prompt, size="2560x1440", reference_images=[...])` → 成功 `storage.save_image` 落盘、建资产（`role='sheet'`、`item_id`、`version_no` 同条目递增、`meta_json` 含提示词/参考图 id/尺寸/提供方/模型）→ 按单价结算；失败按 §2 分类。
- 条目操作：`PATCH`（locked_features / extra_prompt / reference_asset_ids）、`approve {asset_id}`（只接受本条目未归档的 sheet）、`skip` / `reopen`、`POST /assets/{aid}/archive`（已选定版本 409，需先换选定）。
- G1 = 所有非 orphaned 条目都 `approved/skipped` 且至少 1 个 `approved`。

### 2.6 §6 声线
- `POST /voices/audition`：只对 `kind='character'`；台词 1–120 字、变体 1–3 个；`voice` 必须在 `VOICE_CATALOG` 且引擎匹配，`fx` 必须是 `FX_PRESETS` 合法档位；CosyVoice `rate/pitch ∈ 0.5–2.0`，edge-tts `rate ∈ ±50%`、`pitch ∈ ±50Hz`（正则校验）。
- 不弹报价框，但每条按字符数预留（CosyVoice 按字数、最低 0.01 元；edge-tts 预留 0），受日上限约束，超限 409；每个变体一条 `kind='tts'` 任务并立即派发。
- 执行：块 B `synthesize_cosy` / `synthesize_edge` → 块 B `process_voice(raw, fx=..., target_lufs=-16 对白 / -18 旁白, true_peak=-1.5)` → `storage.save_audio` → 建资产（`kind='audio'`、`role='audition'`、`meta_json` 含 spec / 时长 / 实测 LUFS）→ 结算。
- `POST /items/{item_id}/voice/approve {asset_id}`：设 `voice_asset_id` 并把该试听 spec 写进 `spec_json.voice`。
- `GET /voice-catalog`：`{voices: VOICE_CATALOG, fx: {"robot":["A",...],...}}`（档位清单，不含滤镜字符串）。

### 2.7 §8.3 REST
15 条路由全部实现，路径、方法、请求体字段与返回结构逐字对齐；请求模型 `extra="forbid"`；错误一律 `HTTPException`（404 非本人/不存在、409 前置或上限或状态冲突且 `detail` 为中文、422 参数非法）。

### 2.8 跨块调用一律延迟导入（硬性要求 2）
块 B / C 的函数**只**通过 `casting_jobs.py` 的薄封装调用，函数体内 `import`：`_generate_sheet`、`_synthesize_cosy`、`_synthesize_edge`、`_process_voice`、`_build_sheet_prompt`、`_reference_note`、`fx_levels`、`valid_fx`、`lookup_voice`、`voice_catalog`、`style_inputs`、`_save_image`、`_save_audio`、`_inspect_image`、`_reference_bytes`、`_discard_file`。因此 `studio/providers/*`、`audio.py`、`voices.py`、`casting_prompts.py` 全部缺失时，块 A 的所有模块仍可导入；测试里 monkeypatch 这些封装即可。
`store.cas_job` 对 casting 的 `from .casting_jobs import transition` 也放在函数体内，避免循环导入。

## 3. §11.2「块 A 必测项」逐条对应

| 必测项 | 覆盖用例 |
|---|---|
| G0 未批准 / 未开工确认 / 未选风格 → 各接口 409 且 0 次付费 | `api::test_gates_require_g0_setup_and_style_without_paid_calls` |
| 出图报价 = 单价 × 张数；超单次/日上限 409、0 调用；报价确认两次 409；过期不能确认；`needs_author` 被拒 | `api::test_sheets_quote_prices_limits_and_needs_author`、`api::test_sheets_quote_respects_single_and_daily_caps`、`api::test_sheets_start_creates_one_job_per_sheet_and_confirms_once`、`api::test_style_quote_confirms_once_persists_and_expires` |
| 每张图一条任务并预留；成功落资产并结算；`rejected` 释放；`uncertain` 保留至手动释放；派发不重复 | `jobs::test_image_success_lands_versioned_asset_and_settles`、`test_image_versions_increment_for_same_item`、`test_image_failure_classification_and_reservation`、`test_uncertain_keeps_reservation_until_manual_release`、`test_execute_never_posts_twice_and_dispatch_is_idempotent`、`test_create_jobs_budget_and_entry_overrides` |
| 恢复：`running` 的 image/tts 变 `uncertain`，`queued` 补发，POST 次数 0；i2v 与 brain 不变 | `recovery::test_casting_inflight_becomes_uncertain_and_queued_is_redispatched`、`test_casting_uncertain_stays_uncertain_across_restart`、`test_casting_recovery_needs_no_job_table`、`test_i2v_submitting_recovery_unchanged`、`test_brain_submitting_recovery_unchanged`；既有 `tests/test_studio_*.py` 全过 |
| 条目同步（新增/归档/合并 → 补建或 orphaned）；approve 只接受本条目未归档版本；归档已选定 409；G1 判定 | `api::test_items_sync_orphan_and_patch`、`api::test_approve_archive_rules_and_g1` |
| 声线：音色与特效校验；CosyVoice 按字数预留与结算、edge-tts 为 0；定档写 spec | `api::test_voice_catalog_and_audition`、`api::test_voice_approve_writes_spec`、`jobs::test_tts_jobs_reserve_by_chars_and_settle`、`jobs::test_tts_preflight_rejects_missing_spec_and_unknown_engine` |
| 归属：他人项目/条目/资产/报价 404；删号清理新表；风格提案绑定当前项目 | `api::test_ownership_404_and_account_deletion`、`api::test_style_proposals_stay_bound_to_current_project_and_put_style` |

补充覆盖：参考图按已选定版派生与 4 张上限（`jobs::test_reference_plan_uses_approved_version_and_caps`）、落资产失败回滚 + 删文件（`jobs::test_commit_rolls_back_asset_when_creation_fails`）、preflight 失败不产生付费调用（`jobs::test_preflight_failures_release_without_paid_call`）、在途上限默认与环境变量校验（`jobs::test_inflight_limit_defaults_and_env_validation`）、价格默认与环境变量回落（`jobs::test_price_helpers_default_and_env`）。

## 4. 自测结果

```
cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q \
  tests/test_studio_casting_api.py tests/test_studio_casting_jobs.py tests/test_studio_casting_recovery.py
# 32 passed（api 12 + jobs 15 + recovery 5）

cd backend && ... -m pytest -q tests/test_studio_*.py
# 1510 passed，0 failed（含块 B / C 已完成的测试；无回归）
```

测试隔离：块 A 的三个测试文件各自建独立 SQLite（`monkeypatch database.DB_PATH`），把块 B / C 的所有函数替换成假实现（`_generate_sheet` / `_synthesize_*` / `_process_voice` / `_save_*` / `_inspect_image` / `_reference_bytes` / `_build_sheet_prompt` / `_reference_note` / `voice_catalog` / `style_inputs` / `fx_levels` / `valid_fx` / `lookup_voice`），并打桩 `casting_jobs._schedule`，断言 0 次付费调用。

## 5. 未完成 / 需确认

- **价格待核实**：Seedream 出图 `FIONA_STUDIO_PRICE_SEEDREAM_CNY` 默认 0.30 元/张、CosyVoice `FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS` 默认 2.0 元/万字符（已在代码注释标明「响应不含计费字段，按此价预留与结算」，待核实）。
- **真实付费冒烟**由主控在合并后单独报价执行，本期实现与测试全部离线。
- **跨块真接通**的集成测试由主控补写；本块只按 §8 的签名用假实现自测。
- `provider` 列仍是旧 CHECK（`wan / seedance`），casting 任务用占位 `'wan'`、真实提供方在 `media_provider`（与 §3.4 一致）。
- casting 任务是同步调用，不会进入 `submitted / downloaded`；`recovery` 第二段查询虽会取到 casting，但非 `submitting / running` 的 casting 任务直接 `continue`，状态不变。
- `_commit_image` 里 `_create_asset(..., **saved, kind=..., source=...)`：`saved` 只含 `rel_path / sha256 / bytes`，与显式 `kind / source` 无键冲突；已用测试断言落库字段正确。
- 需要块 D 注意：`GET /casting` 返回的 `jobs` 为近 50 条已结束任务的倒序，`CastingJob.created_at` 为 ISO 字符串。
