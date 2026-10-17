# WO3d P2 · 块 A（适配器）完成报告

- 日期：2026-10-17
- 范围：仅块 A；未改动块 B / 块 C 的文件，也未触碰 P1 的未提交改动。

## 1. 改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/studio/providers/tts_doubao.py` | 新建 | 豆包语音 2.0 单向流式 HTTP 适配器 |
| `backend/studio/voices.py` | 修改 | 新增 11 条豆包 2.0 中文音色 |
| `backend/tests/test_studio_media_tts_doubao.py` | 新建 | 39 个离线契约测试（MockTransport） |
| `docs/tasks/2026-10-17-studio-wo3d-p2-doubao/03-report-A.md` | 新建 | 本报告 |

## 2. §3.1 适配器契约逐项对应

**常量与入口（名字一字未改）**
- `DOUBAO_ENGINE = "doubao"`
- `API_KEY_ENV = "VOLC_SPEECH_API_KEY"`
- `RESOURCE_ENV = "VOLC_SPEECH_RESOURCE_ID"`，未设置或为空时默认 `seed-tts-2.0`
- `DOUBAO_AUDIO_FORMAT = "mp3"`、`DOUBAO_SAMPLE_RATE = 24000`
- `DIRECTION_MAX_CHARS = 200`、`SYNTHESIS_TIMEOUT_S = 120.0`
- `doubao_configured() -> bool`：Key 去空白后非空才为真
- `async synthesize_doubao(text, *, voice, rate=1.0, pitch=0, direction="", transport=None) -> TtsResult`

**`TtsResult`**
- 复用 `providers/tts_cosy.py::TtsResult`，填 `engine="doubao"`、`audio_format="mp3"`、
  `sample_rate=24000`、`chars=len(text)`、`words=[]`。

**请求与参数映射**
- 请求头：`X-Api-Key`、`X-Api-Resource-Id`、`X-Api-Request-Id`（uuid4）、`Content-Type: application/json`。
- 请求体：`{"user":{"uid":"fiona-studio"},"req_params":{...}}`，`speaker=voice`。
- `rate`：`speech_rate = round((rate - 1) * 100)`，再截到 `[-50, 100]`。
- `pitch`：整数（整数浮点也接受），写入 `additions.post_process.pitch`；为 0 时不写。
- `direction`：先 `strip()`；非空才写 `context_texts: [direction]`；超过 200 字抛 `ValueError`。
- `additions`：用 `json.dumps(..., ensure_ascii=False)` 序列化成字符串；无任何内容时不传该字段。

**调用约束**
- 只发一次 POST，不重试。
- `httpx.AsyncClient(transport=..., timeout=httpx.Timeout(SYNTHESIS_TIMEOUT_S), follow_redirects=False)`；
  未显式设置 `trust_env`，保持默认。
- 外层 `asyncio.wait_for(..., timeout=SYNTHESIS_TIMEOUT_S)` 作为整个调用的总超时。
- `transport is None` 时调用模块级 `_default_transport()`；该函数默认返回 `None`，测试 monkeypatch 注入 `httpx.MockTransport`。

**错误分类（只看结构化 HTTP 状态码与响应体 `code`，不扫错误文本）**
- HTTP 4xx（含 401/403/429）→ `rejected`
- 响应体 `code` 为 8 位且以 `45` 开头 → `rejected`（如 45002001）
- HTTP 5xx → `uncertain`
- 传输错误 → `uncertain`（`doubao_transport_error`）
- 超时（httpx 超时与总超时）→ `uncertain`（`doubao_timeout`）
- 流结束但未出现 20000000 → `uncertain`（`doubao_incomplete_stream`）
- 成功码但无音频 → `uncertain`（`doubao_empty_audio`）
- 其余 code → `uncertain`
- 缺 Key → 不发请求，`rejected`，code `doubao_key_missing`
- 错误 code 统一为 `doubao_<数字>`、`doubao_http_<状态码>` 或语义码；
  错误信息经 `safe_message` 处理后，再显式替换掉当前 `VOLC_SPEECH_API_KEY`。

## 3. §3.2 音色目录逐项对应

`VOICE_CATALOG` 新增 11 条，全部 `engine="doubao"`、`lang="zh"`，`label` / `note` 按规格表原样写入：

| voice | label | gender |
|---|---|---|
| `zh_female_vv_uranus_bigtts` | Vivi 2.0 | female |
| `zh_female_xiaohe_uranus_bigtts` | 小何 2.0 | female |
| `zh_female_wenroumama_uranus_bigtts` | 温柔妈妈 2.0 | female |
| `zh_female_sophie_uranus_bigtts` | 魅力苏菲 2.0 | female |
| `zh_female_meilinvyou_uranus_bigtts` | 魅力女友 2.0 | female |
| `zh_male_wennuanahu_uranus_bigtts` | 温暖阿虎 2.0 | male |
| `zh_male_jieshuoxiaoming_uranus_bigtts` | 解说小明 2.0 | male |
| `zh_male_liufei_uranus_bigtts` | 刘飞 2.0 | male |
| `zh_male_shaonianzixin_uranus_bigtts` | 少年梓辛 2.0 | male |
| `zh_male_taocheng_uranus_bigtts` | 小天 2.0 | male |
| `zh_male_m191_uranus_bigtts` | 云舟 2.0 | male |

`voices_for("doubao")` 返回 11 条，`lookup_voice("doubao", ...)` 可直接命中；原有 CosyVoice / edge-tts 条目未改动。

## 4. §5 验收项逐项对应

| 验收项 | 覆盖测试 |
|---|---|
| 多行分块的成功流 | `test_success_stream_collects_multiline_chunks` |
| `additions` 是字符串，含 `context_texts` 与 `post_process.pitch` | `test_additions_is_json_string_with_direction_and_pitch` |
| 无指示、pitch=0 时不传 `additions` | `test_additions_omitted_when_no_direction_and_zero_pitch`、`test_zero_pitch_is_omitted_but_direction_kept` |
| `rate` 换算和截断 | `test_rate_conversion_and_clamp[...]`（0.1–3.0 共 7 组） |
| 4xx / 401 / 403 / 429 → rejected | `test_http_4xx_is_rejected[...]`、`test_http_4xx_without_json_body_is_rejected` |
| 5xx → uncertain | `test_http_5xx_is_uncertain`、`test_http_5xx_without_json_body_is_uncertain` |
| 传输错误、超时 → uncertain | `test_transport_error_is_uncertain`、`test_httpx_timeout_is_uncertain`、`test_total_timeout_is_uncertain` |
| 流里没有 20000000 → uncertain | `test_stream_without_success_code_is_uncertain` |
| 响应体 code 45002001 → rejected | `test_body_code_45002001_is_rejected` |
| 其余 code → uncertain | `test_other_body_code_is_uncertain` |
| 成功码但无音频 → uncertain | `test_success_code_without_audio_is_uncertain` |
| 缺 Key 时不发任何请求 | `test_missing_key_never_sends_request`（断言 `calls == []`） |
| 每个用例断言 POST 只发 1 次 | 所有异步用例经 `assert_single_post(calls)` |
| 错误信息不含 Key | 所有错误用例断言；另有 `test_upstream_message_redacts_key` 验证上游回显 Key 会被替换 |
| 音色目录 | `test_voice_catalog_contains_doubao_entries` |

附加覆盖：指示超 200 字在发请求前抛 `ValueError`；恰好 200 字可用；非法 pitch 在发请求前抛 `ValueError`；
整数浮点 pitch 被接受；`doubao_configured()` 的真假边界；`_default_transport()` 默认返回 `None`。

## 5. 测试结果

```text
cd backend
python -m pytest -q tests/test_studio_media_tts_doubao.py
39 passed in 0.37s
```

块 B 的豆包相关用例（用于验证契约对接，非块 A 改动）：

```text
python -m pytest -q tests/test_studio_casting_api.py -k doubao \
  tests/test_studio_casting_jobs.py -k doubao \
  tests/test_studio_casting_integration.py -k doubao
7 passed, 72 deselected
```

全量验收（块 B / 块 C 落地后复跑）：

```text
python -m pytest -q tests/ -k studio
1659 passed, 5550 deselected, 32 warnings in 89.86s
```

块 A 自身的 39 个用例全部通过，块 B 的 7 个豆包用例全部通过，全量 studio 套件全绿，
说明 §3.1 契约与块 B / 块 C 的调用方式一致。

## 6. 未完成项 / 说明

- 块 A 范围内无未完成项。
- 未联网、未读取 `.env`、未使用真实 Key：所有 HTTP 走 `httpx.MockTransport`。
- 未提交代码；未改动块 B / 块 C 文件及 P1 的未提交改动。
