# WO3d P2 · 块 B（后端接线）完成报告

- 日期：2026-10-17
- 范围：仅块 B 的 4 个实现文件与 3 个测试文件；未改块 A / 块 C 文件，未触碰 P1 的未提交改动。
- 依赖：块 A 的 `tts_doubao.py` 与 `voices.py` 已落盘后，才运行了集成测试；块 B 未自行实现适配器。

## 1. 改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/studio/casting.py` | 修改 | 引擎枚举、试听校验、Key/ffmpeg 预检、试听 spec 带 `direction`、定档 `baseline`、价格字段 |
| `backend/studio/casting_jobs.py` | 修改 | `_synthesize_doubao` 薄封装、`doubao_configured` 薄封装、tts 执行分支、豆包计价 |
| `backend/studio/pricing.py` | 修改 | 豆包单价常量/环境变量、`estimate_speech` 支持豆包 |
| `backend/routers/studio.py` | 修改 | `VoiceVariantBody` 增加豆包与 `direction`；定档 body 增加 `baseline` |
| `backend/tests/test_studio_casting_api.py` | 修改 | 豆包 422 / 503 / 价格 / 定档 baseline 用例 |
| `backend/tests/test_studio_casting_jobs.py` | 修改 | 豆包任务执行、错误结算、计价用例 |
| `backend/tests/test_studio_casting_integration.py` | 修改 | 真实适配器 + MockTransport + 真实 ffmpeg 的豆包端到端用例 |
| `docs/tasks/2026-10-17-studio-wo3d-p2-doubao/03-report-B.md` | 新建 | 本报告 |

## 2. §3.3 后端接线逐项对应

**`routers/studio.py`**
- `VoiceVariantBody.engine` 增加 `"doubao"`，Literal 为 `["doubao", "cosyvoice", "edge-tts"]`。
- `VoiceVariantBody` 新增 `direction: str | None = Field(default=None, max_length=200)`。
- 定档改用 `VoiceApproveBody(CastingApproveBody)`，新增 `baseline: str | None = Field(default=None, max_length=200)`；
  `POST /casting/items/{id}/voice/approve` 把 `baseline` 传给 `casting.approve_voice`。
- 额外：`pitch` 增加 `mode="before"` 校验，阻止 pydantic 把 JSON `true` 静默转成 `1.0`（否则整数校验会被绕过）。

**`casting.py` 试听校验**
- `ENGINES = ("doubao", "cosyvoice", "edge-tts")`；错误文案同步为三种引擎。
- 豆包：
  - `rate` 走 `_bounded_float(..., 0.5, 2.0, "语速")`。
  - `pitch` 走新增的 `_bounded_int(..., -12, 12, "音高")`；`3.0` 这类整数值浮点接受并存成 `3`，布尔与 `1.5` 拒绝。
  - `voice` 通过 `casting_jobs.lookup_voice("doubao", voice)` 校验，必须命中块 A 的豆包目录。
  - `fx`、`role` 沿用原校验。
- 非豆包引擎传非空 `direction` → 422「该引擎不支持表演指示」；`direction` 先 `strip()`，空白视为未传。
- 豆包指示超过 200 字 → 422（请求层由 pydantic `max_length` 先拦，业务层再兜底）。
- 含豆包方案时：
  1. `casting_jobs.doubao_configured()` 为假 → 503「未配置 VOLC_SPEECH_API_KEY」；
  2. 再检查 `AUDIO_TOOLS`（ffmpeg / ffprobe，豆包 mp3 必须转码）→ 缺工具 503。
  这两步都在 `create_jobs` 之前完成，不会留下任务行或任何付费请求。
- 校验后的 spec 固定带上 `direction`（无指示为 `None`）；该 spec 同时进入任务 `params`，执行后原样写入试听资产 `meta.spec` 与 `CastingAudition.spec`。

**定档声线**
- `approve_voice(item_id, owner, asset_id, *, baseline=None)`：
  - `baseline` 未传或只有空白时，默认取该条试听的 `direction`；
  - 传了则 `strip()`，超过 200 字 → 422；
  - `spec_json.voice = {**spec, "direction": ..., "baseline": ...}`，即 `CastingVoiceSpec` 同时具备两个新字段。
- 返回的 `voice.spec` 直接透出 `direction` 与 `baseline`。

**`casting_jobs.py`**
- 新增 `async _synthesize_doubao(text, *, voice, rate, pitch, direction)`，函数体内延迟导入
  `providers.tts_doubao.synthesize_doubao`。
- 新增 `doubao_configured()` 薄封装，供 `casting.audition` 延迟导入调用。
- `_run_tts` 在 `engine == "doubao"` 时调用 `_synthesize_doubao`，以 `pitch=int(...)`、
  `direction=spec.get("direction") or ""` 传参，之后统一走 `process_voice(raw, input_format="mp3", …)`。
- 异常分类不变：适配器抛出的 `MediaCallError` 经 `_classify` 落为 `rejected` / `uncertain`，
  预留按既有规则释放或保留。
- `price_for("doubao", chars=...)` 接入豆包计价。

**`pricing.py`**
- 新增 `DEFAULT_DOUBAO_TTS_PRICE_CNY_PER_10K_CHARS = Decimal("3.0")`，注释标注「待核实」。
- 新增 `PRICE_DOUBAO_ENV = "FIONA_STUDIO_PRICE_DOUBAO_TTS_CNY_PER_10K_CHARS"` 与
  `doubao_price_per_10k_chars()`，非法值告警一次并回落默认（沿用 `_price`）。
- `estimate_speech` 支持 `engine == "doubao"`，算法与 CosyVoice 相同：`单价 × 字数 / 10000`，
  最低 ¥0.01；指示文本不计入 `chars`（`chars` 仍为 `len(text.strip())`）。
- 新增 `MIN_SPEECH_PRICE_CNY`；保留旧名 `MIN_COSYVOICE_PRICE_CNY` 兼容既有调用。

**`GET /casting`**
- `prices` 同时返回 `doubao_cny_per_10k_chars`，位于 `cosyvoice_cny_per_10k_chars` 旁边。

## 3. §5 验收项逐项对应

| 验收项 | 覆盖测试 |
|---|---|
| 豆包完整链路：真实适配器 + MockTransport + 真实 ffmpeg，产出 48k 单声道 WAV | `test_doubao_audition_end_to_end`（`test_studio_casting_integration.py`） |
| `direction` 写进试听 spec（任务 spec、资产 meta、返回的 audition spec） | `test_doubao_audition_validation_and_spec`、`test_doubao_audition_end_to_end` |
| 422：非豆包引擎传指示 | `test_doubao_audition_validation_and_spec`（cosy / edge 各一次） |
| 422：指示超长 | `test_doubao_audition_validation_and_spec`（201 字） |
| 422：pitch 不是整数 | `test_doubao_audition_validation_and_spec`（`1.5`、`"0"`、`true`、`±13`） |
| 503：缺 Key，付费调用为 0 | `test_doubao_audition_requires_key_and_ffmpeg`、`test_doubao_audition_blocks_without_key_or_ffmpeg` |
| 503：缺 ffmpeg，付费调用为 0 | 同上（两条用例都断言无任务行、无 POST） |
| approve 带 baseline | `test_voice_approve_baseline_defaults_to_direction`、`test_doubao_voice_approve_writes_direction_and_baseline` |
| approve 不带 baseline（默认取 direction） | 同上 |
| 预留与结算金额正确 | `test_doubao_audition_validation_and_spec`、`test_doubao_tts_job_passes_direction_and_processes_mp3`、`test_price_helpers_default_and_env` |
| 错误分类沿用 `MediaCallError` | `test_doubao_preflight_error_releases_reservation` |

其他新增/更新：
- `test_studio_casting_jobs.py` 的 `paid` 夹具新增 `_synthesize_doubao` 打桩与调用记录，原 CosyVoice / edge 行为不变。
- 既有 spec 形状常量拆为 `AUDITION_SPEC_KEYS`（含 `direction`）与 `VOICE_SPEC_KEYS`（再加 `baseline`），
  既有 CosyVoice / edge 用例同步为 `direction: None`，定档断言同步为 `{**spec, "baseline": None}`。
- 音色目录集成测试改为三种引擎，并断言豆包目录 11 条、全部 `zh` 且以 `_uranus_bigtts` 结尾。

## 4. 测试结果

```text
cd backend
python -m pytest -q tests/test_studio_casting_api.py
36 passed, 32 warnings in 7.61s

python -m pytest -q tests/test_studio_casting_jobs.py
27 passed in 0.92s

python -m pytest -q tests/test_studio_casting_integration.py
16 passed, 32 warnings in 5.12s

python -m pytest -q tests/test_studio_casting_api.py tests/test_studio_casting_jobs.py \
  tests/test_studio_casting_integration.py -k doubao
7 passed, 72 deselected, 32 warnings in 2.76s
```

全量（块 B 完成时首跑；块 C 落盘后复跑结果一致）：

```text
cd backend
python -m pytest -q tests/ -k studio
1659 passed, 5550 deselected, 32 warnings in 82.21s (0:01:22)

# 块 C 落盘后复跑
1659 passed, 5550 deselected, 32 warnings in 73.08s (0:01:13)
```

集成测试使用本机真实 `ffmpeg` / `ffprobe`（`/opt/homebrew/bin`），未跳过；所有 HTTP 均走
`httpx.MockTransport`，未联网。

## 5. 未完成项 / 说明

- 块 B 范围内无未完成项。
- 未改块 A 的适配器、音色目录或其测试；未改块 C 的前端与文档。
- 未读取 `.env`、未读取或打印任何真实 Key；集成测试使用占位 Key `offline-volc-key`。
- 未提交代码；P1 的未提交改动保持原样。
- 前端 `npx tsc --noEmit` / `npm run lint` 属块 C 验收，本报告未运行。
