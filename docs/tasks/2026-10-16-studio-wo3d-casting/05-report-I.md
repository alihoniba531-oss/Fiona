# WO3d 集成任务 I 报告：接通块 A↔B↔C↔D，补集成测试

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`（分支 `short-film-studio`）
- Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 权威规格：`docs/tasks/2026-10-16-studio-wo3d-casting/02-spec.md`
- 主产物：新增 `backend/tests/test_studio_casting_integration.py`（11 个用例）
- 未提交、未推送。未碰 `CLAUDE.md` / `README.md` / `docs/ARCHITECTURE.md` / `backend/.env.example` / `frontend/node_modules`。

## 1. 发现的不一致与修正

四块自测时都用了假实现，接线后暴露出两处「同一份数据、不同接口返回形状不一致」的问题。两处都在后端，按 §8 改后端。

### 1.1 试听资产多暴露 `version_no` 和 `prompt`（违反 §8.3 `CastingAudition`）

- 位置：`backend/studio/casting.py:105-116`（`_asset_public`）。
- 原因：`_asset_public` 的两个分支共用了一个 `base` 字典，`base` 里含 `version_no`；`sheet` 分支再叠加 `prompt`。`audition` 分支最初复用了这个形状，于是单条目接口（`PATCH/approve/voice-approve` 返回的 `CastingItem.voice.auditions[*]`）里每个试听条目多带了 `version_no` 与 `prompt` 两个键。
- 规格：§8.3 `CastingAudition` 只列 `asset_id / spec / text / duration_s / measured_lufs / created_at / archived`，多键即形状不符。
- 改法：`audition` 分支改为单独构造字典，只输出规格列出的 7 个键（去掉 `version_no` 与 `prompt`）。
- 连带：`backend/tests/test_studio_casting_api.py:678-680` 里对该条目的精确断言同步收敛（去掉 `version_no` / `prompt`），与 §8.3 对齐。

### 1.2 单条目接口返回已归档的定妆版本（与 `GET /casting` 不一致）

- 位置：`backend/studio/casting.py:536-542`（`_single_item`）。
- 原因：`GET /projects/{pid}/casting` 走 `_item_public`，其中 sheets 已被 `and not asset.get("archived")` 过滤；而单条目接口 `_single_item` 直接把 `role='sheet'` 的所有行塞进 `versions`，未过滤 `archived`。结果：归档某张定妆图后，列表接口看不到它、单条目接口（`PATCH` / `approve` / `skip` / `voice/approve` 的返回）还能看到，同一 `CastingItem` 两处形状不一致。
- 改法：`_single_item` 的 sheets 过滤条件补 `and not asset.get("archived")`，与 `_item_public` 完全一致（`auditions` 保持原样，规格未要求按归档过滤）。

### 1.3 未发现其它跨块问题

- 块 B（Seedream / CosyVoice / edge-tts 适配器 + ffmpeg 处理）、块 C（定妆提示词与风格组装）、块 D（前端键名）与块 A（REST 编排 / 报价 / 预留 / 结算）在真实接线后没有出现新的形状或语义冲突。
- 前端**未做任何修改**：块 D 交付的 `frontend/lib/studio-casting.ts` 与各 `Casting*.tsx` 已与后端返回对齐（含 `StudioWorkbench.tsx` 把 `CastingStage` 挂到第 2 阶段），故本任务无需改前端。

## 2. 集成测试设计

文件：`backend/tests/test_studio_casting_integration.py`（约 1071 行，11 个用例）。

跑真实块 A / B / C 代码，只在**最底层**把传输换掉（绝不替换 `generate_sheet` / `synthesize_*` / `process_voice` 本身）：

- **Seedream**：`install_seedream()` 用 `_AsyncClientInjector` 代理 `image_seedream.httpx`，构造 `AsyncClient` 时补 `httpx.MockTransport`；返回真实 2560×1440 PNG（`_seedream_ok`），并记录每条请求用于**断言 POST 次数**与请求体。
- **CosyVoice**：`install_cosy()` 替换模块级 `tts_cosy._default_synthesizer_factory`，产出真实正弦 WAV 字节（`wave` 生成）。
- **edge-tts**：`install_edge()` 向 `sys.modules` 注入假 `edge_tts`（本机 venv 未装，测试不依赖它存在）。
- **ffmpeg**：`process_voice` 走真实 ffmpeg；模块在 `shutil.which("ffmpeg")` / `shutil.which("ffprobe")` 任一为空时 `pytest.skip(..., allow_module_level=True)`。
- **导演模型**：照块 A 假 brain 方式打桩 `brain.provider_options` 与 `_schedule`，再直接写 `result_json`。
- 夹具沿用 `tests/test_studio_casting_api.py` 的建库、JWT 准入与「G0 已批准项目」写法；未读 `.env`、未设真实 Key、付费调用全程离线。

§8.3 各对象逐字段键集合以常量断言（`STATE_KEYS` / `ITEM_KEYS` / `JOB_KEYS` / `AUDITION_KEYS` …），多键少键都判失败。

## 3. 新增测试清单

| # | 用例（行号） | 覆盖场景 |
|---|--------------|----------|
| 1 | `test_full_casting_flow_end_to_end`（:516） | 完整主流程：开工确认 → 风格报价/确认/落库/选定（含 realism）→ 2 条目各 2 版定妆图 → 资产落库（`item_id` / `version_no` 递增 / `role` / 实际 2560×1440 / 文件落在临时 `FIONA_STUDIO_DIR`）→ 批准 1 跳过 1 → G1 通过；逐字段校验 `CastingState` / `CastingItem` / `CastingJob`；断 4 次 POST、费用结算 |
| 2 | `test_seedream_timeout_is_uncertain_and_release_clears_reservation`（:664） | Seedream 超时/断连 → `uncertain`/`transport_error`，POST 恰好 1 次，预留保留；`POST /jobs/{jid}/release` 释放后预留归零、提交费用归零 |
| 3 | `test_seedream_4xx_is_rejected_without_retry`（:697） | 429/400 → `rejected`（`http_429` / `http_400`），不结算、不重试（各 POST 1 次），无资产落库 |
| 4 | `test_quotes_confirm_once_and_expire`（:726） | 同一报价确认两次第二次 409；过期报价确认被拒；风格报价同样覆盖 |
| 5 | `test_chinese_audition_processes_audio_and_settles_by_chars`（:759） | 中文试听 cosy + `robot:B` → 真 ffmpeg → 48000Hz 单声道 16bit WAV；`probe_audio` 与库里记录一致；按字数预留并结算 |
| 6 | `test_english_audition_is_free_and_outputs_48k_wav`（:817） | 英文 edge 路径免费（预留 0、结算 0、无费用记录）；输出 48k WAV |
| 7 | `test_voice_approve_writes_selected_spec`（:851） | `POST /casting/items/{id}/voice/approve` 后 `voice_asset_id` 与 `spec_json.voice` 一致 |
| 8 | `test_voice_catalog_matches_fx_presets_and_frontend_keys`（:888） | `GET /casting/voice-catalog` 的 `fx` 键与档位 == `audio.FX_PRESETS`；读 `frontend/lib/studio-casting.ts` 源码断言 `robot/beast/inner` 键名可命中 |
| 9 | `test_reference_image_is_downscaled_and_project_scoped`（:923） | 定妆报价带参考图 asset id（`POST /projects/{pid}/assets` 上传得到）时 Seedream 请求体确实带参考图，长边 ≤1536（1536×576）；他人 / 他项目 asset id 被拒 404 |
| 10 | `test_restart_recovery_marks_inflight_casting_jobs_uncertain`（:975） | 预置 `running` / `submitting` 的 image 与 tts 任务跑 `recovery.recover_studio_jobs()` → `uncertain`/`restart_during_submission`，付费调用 0 次 |
| 11 | `test_gates_and_ownership`（:1011） | G0 未批准时所有 casting 写接口 409、零 job / 零资产；非作者一律 404；响应头 `Cache-Control: private, no-store` |

## 4. 测试结果

运行目录 `backend/`，Python 为上述 venv：

- `python -m pytest -q tests/test_studio_casting_integration.py` → **11 passed**（约 3.6s）；加 `-p no:randomly` 亦全绿。
- `python -m pytest -q tests/ -k studio` → **1538 passed, 5550 deselected**（约 68s），0 failed。
- 前端（虽未改动，仍按规则验证块 D 交付能编译/通过 lint）：
  - `cd frontend && npx tsc --noEmit` → **0 error**。
  - `cd frontend && npm run lint`（eslint）→ **0 error, 25 warning**；warning 全部是既有的、与本任务无关的 `app/page.tsx`、`app/plaza/page.tsx`（未使用变量、`<img>` 提示），casting 相关文件 0 warning。

### 沙箱备注

- 全程未联网、未读 `.env`、未设真实 Key；付费调用均被 MockTransport / 假工厂接管。
- 本机（macOS，ffmpeg/ffprobe 在 `/opt/homebrew/bin/`）本次运行未出现任务说明里提到的沙箱禁绑本地端口导致的 `PermissionError: bind`；若在受限 CI 上出现，属环境限制，与本任务改动无关。
- 集成测试模块在缺少 ffmpeg / ffprobe 的环境会整体 `pytest.skip`，不会误报失败。

## 5. 改动文件一览

- 新增：`backend/tests/test_studio_casting_integration.py`（主产物）。
- 修正：`backend/studio/casting.py`（`_asset_public` 试听分支、`_single_item` sheets 过滤）。
- 连带：`backend/tests/test_studio_casting_api.py`（同步该条目的精确断言）。
- 报告：本文件。
