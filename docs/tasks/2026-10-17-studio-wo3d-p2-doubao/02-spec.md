# WO3d 补丁 P2：豆包语音 2.0 + 每句表演指示

- **工作目录**：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`，分支 `short-film-studio`。工作区里还有补丁 P1 的未提交改动，不要动它们。
- **Python 解释器**：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`。
- **参考资料**：
  - `docs/tasks/2026-10-17-studio-wo3d-p1-look/research-doubao-emotion.md`：官方文档调研，字段名以它为准。
  - `docs/tasks/2026-10-16-studio-wo3d-casting/02-spec.md`：声线部分 §6 和 §8。

## 1. 产品目标

作者做了几轮试听对比，结论如下：
- CosyVoice v2 太死板。
- 豆包语音 2.0 不带指示时音色自然，但 AI 味仍然重。
- **豆包语音 2.0 带上一句自然语言表演指示后，明显有人味。**

本补丁要做的事：
- 把豆包语音 2.0 接成工作室的中文配音引擎，中文项目默认就用它。
- 每条试听方案都能写一句「表演指示」。
- 角色定档声线时，同时保存一句「角色基调」。WO4 逐句配音时，会把角色基调和每句的表演指示合并使用。

CosyVoice 和 edge-tts 保留，作为备选。

## 2. 已实测的接口事实（2026-10-17 用真实 Key 打通）

- **端点**：`POST https://openspeech.bytedance.com/api/v3/tts/unidirectional`
- **请求头**：
  - `X-Api-Key`：取环境变量 `VOLC_SPEECH_API_KEY`
  - `X-Api-Resource-Id`：取环境变量 `VOLC_SPEECH_RESOURCE_ID`，默认 `seed-tts-2.0`
  - `X-Api-Request-Id`：uuid4
  - `Content-Type: application/json`
- **请求体**：
  ```json
  {"user":{"uid":"fiona-studio"},
   "req_params":{"text":"…","speaker":"zh_female_sophie_uranus_bigtts",
     "audio_params":{"format":"mp3","sample_rate":24000,"speech_rate":0},
     "additions":"{\"context_texts\":[\"压低声音，不安里带着一点倔强，像在问自己\"],\"post_process\":{\"pitch\":0}}"}}
  ```
  - **注意 `additions` 必须是 JSON 序列化后的字符串**，不能直接传对象。
  - `context_texts` 只对 2.0 音色生效，这部分文本不计费。
  - `speech_rate` 的范围是 [-50, 100]。
  - `post_process.pitch` 是整数，范围 [-12, 12]。
- **响应**：逐行返回 JSON。每行的 `data` 是 base64 编码的音频块，拼起来就是完整音频。出现 `code == 20000000` 那一行表示成功结束。
- **错误码实测**：
  - HTTP 401，code 45000010：Key 无效。
  - HTTP 403，code 45000030：资源未授权。
  - code 45002001：没有可读文本。
  - Seed-Audio 曾返回 HTTP 500，code 55001309（内部错误）。

## 3. 共同契约（名字一字不改）

### 3.1 适配器 `backend/studio/providers/tts_doubao.py`（块 A 新建）

```python
DOUBAO_ENGINE = "doubao"
API_KEY_ENV = "VOLC_SPEECH_API_KEY"
RESOURCE_ENV = "VOLC_SPEECH_RESOURCE_ID"      # 默认 "seed-tts-2.0"
DOUBAO_AUDIO_FORMAT = "mp3"
DOUBAO_SAMPLE_RATE = 24000
DIRECTION_MAX_CHARS = 200
SYNTHESIS_TIMEOUT_S = 120.0

def doubao_configured() -> bool: ...          # Key 存在且非空

async def synthesize_doubao(text: str, *, voice: str, rate: float = 1.0, pitch: int = 0,
                            direction: str = "", transport=None) -> TtsResult: ...
```

**`TtsResult`**：复用 `providers/tts_cosy.py` 里的 `TtsResult`，字段这样填：
- `engine="doubao"`
- `audio_format="mp3"`
- `sample_rate=24000`
- `chars=len(text)`
- `words=[]`

**参数映射**：
- `rate`：取值 0.5–2.0，换算成 `speech_rate = round((rate - 1) * 100)`，再截到 [-50, 100]。
- `pitch`：取值是 -12 到 12 的整数，写进 `post_process.pitch`。值为 0 时不写这个字段。
- `direction`：去掉首尾空白后，非空才写成 `context_texts: [direction]`。超过 200 字时抛 `ValueError`。
- `additions`：没有任何内容时不传这个字段。

**调用约束**：
- 只发一次 POST，不重试。
- 使用 `httpx.AsyncClient(follow_redirects=False)`，`trust_env` 保持默认，因为本机走代理。
- 整个调用的总超时是 `SYNTHESIS_TIMEOUT_S`。
- 测试要能注入假传输：`transport` 参数为 None 时，调用模块级的 `_default_transport()`，它默认返回 None。测试 monkeypatch 这个函数，让它返回 `httpx.MockTransport`。

**错误分类**（只看结构化的状态码，**禁止**用正则去扫错误文本）：

| 情况 | 结果 |
|---|---|
| HTTP 4xx（含 401、403、429） | `rejected` |
| 响应体里的 code 以 45 开头（8 位数） | `rejected` |
| HTTP 5xx | `uncertain` |
| 传输错误、超时 | `uncertain` |
| 流结束了但没出现 20000000 | `uncertain` |
| 返回成功码但没有音频 | `uncertain` |
| 其余 code | `uncertain` |
| 缺 Key | 不发请求，直接 `rejected`，code 为 `doubao_key_missing` |

- 抛出的 `MediaCallError` 沿用 `providers/media_errors.py`，code 写成 `doubao_<数字>` 或语义码。
- 任何错误信息里都不能出现 Key。

### 3.2 音色目录 `backend/studio/voices.py`（块 A 改）

新增 11 条，`engine` 为 `"doubao"`，`lang` 为 `"zh"`。`label` 和 `note` 照下表写，`note` 用控制台上的官方描述：

| voice | label | gender | note |
|---|---|---|---|
| zh_female_vv_uranus_bigtts | Vivi 2.0 | female | 语调平稳、咬字柔和、自带治愈安抚力 |
| zh_female_xiaohe_uranus_bigtts | 小何 2.0 | female | 声线甜美有活力 |
| zh_female_wenroumama_uranus_bigtts | 温柔妈妈 2.0 | female | 语调舒缓、咬字温润 |
| zh_female_sophie_uranus_bigtts | 魅力苏菲 2.0 | female | 高冷御姐，外冷内柔（官方标注指令遵循） |
| zh_female_meilinvyou_uranus_bigtts | 魅力女友 2.0 | female | 成熟妩媚的御姐 |
| zh_male_wennuanahu_uranus_bigtts | 温暖阿虎 2.0 | male | 阳光温暖的少年音 |
| zh_male_jieshuoxiaoming_uranus_bigtts | 解说小明 2.0 | male | 明快、中气十足的解说男声 |
| zh_male_liufei_uranus_bigtts | 刘飞 2.0 | male | 逻辑清晰、理性稳重 |
| zh_male_shaonianzixin_uranus_bigtts | 少年梓辛 2.0 | male | 清爽少年感 |
| zh_male_taocheng_uranus_bigtts | 小天 2.0 | male | 清澈温润的男大学生 |
| zh_male_m191_uranus_bigtts | 云舟 2.0 | male | 磁性、成熟理性 |

### 3.3 后端接线（块 B）

**`routers/studio.py`**：
- `VoiceVariantBody.engine` 增加 `"doubao"`。
- `VoiceVariantBody` 新增 `direction: str | None = Field(default=None, max_length=200)`。

**`casting.py` 的试听校验**：
- 豆包方案：
  - `rate` 是 0.5–2.0 的数。
  - `pitch` 是 -12 到 12 的整数，传浮点但值是整数的也接受。
  - `voice` 必须在 doubao 目录里。
  - `fx` 照旧可选。
- 非豆包引擎传了非空的 `direction`，返回 422「该引擎不支持表演指示」。
- 含豆包方案时：如果 `doubao_configured()` 为假，返回 503「未配置 VOLC_SPEECH_API_KEY」；ffmpeg 预检也要覆盖豆包，因为 mp3 需要 ffmpeg 转码。这两项都必须在任何付费请求**之前**完成。
- 试听资产的 meta 和 `CastingAudition.spec` 里都要带上 `direction`。

**定档声线**：
- `POST /casting/items/{id}/voice/approve` 新增可选字段 `baseline: str ≤200`，即「角色基调」。没传时，默认取该试听的 `direction`。
- `spec_json.voice` 增加 `direction`（该条试听用的指示）和 `baseline`。
- `CastingVoiceSpec` 增加 `direction: string | null` 和 `baseline: string | null` 两个字段。

**`casting_jobs.py`**：
- 新增薄封装 `_synthesize_doubao(text, *, voice, rate, pitch, direction)`，里面延迟导入适配器。
- 试听执行时，`engine == "doubao"` 就调这个封装，之后走 `process_voice(raw, input_format="mp3", …)`。
- 错误分类沿用 `MediaCallError`。

**`pricing.py`**：
- 新增 `DEFAULT_DOUBAO_TTS_PRICE_CNY_PER_10K_CHARS = Decimal("3.0")`，标注「待核实」。
- 对应环境变量 `FIONA_STUDIO_PRICE_DOUBAO_TTS_CNY_PER_10K_CHARS`。
- 预留与结算的算法和 CosyVoice 相同：按字数计，最少 ¥0.01。指示文本不计费。

**`GET /casting`**：价格信息里同时返回 `doubao_cny_per_10k_chars`。可以搜 `cosyvoice_cny_per_10k_chars`，就在它旁边。

### 3.4 前端与文档（块 C）

**`frontend/lib/studio-casting.ts`**：
- `CastingVoiceEngine` 增加 `"doubao"`，`castingVoiceEngineLabel` 显示为「豆包语音 2.0」。
- `CastingAuditionVariant` 增加 `direction?: string`。
- `CastingVoiceSpec` 增加 `direction` 和 `baseline`。
- 价格读 `doubao_cny_per_10k_chars`。
- `castingVoiceSpecLabel` 在有指示时附上「指示：…」。

**`VoicePanel.tsx`**：
- 中文项目新建方案时，引擎默认选「豆包语音 2.0（推荐）」。下拉框里依次列出：豆包语音 2.0、CosyVoice、edge-tts。
- 选豆包时：
  - 音高改成 -12 到 12 的整数微调，默认 0。
  - 显示「表演指示」多行输入框，最多 200 字，带计数。占位文字为「例如：压低声音，不安里带着一点倔强，像在问自己」。
  - 下方加一行小字：「写清情绪、语气、场景，比只换音色更能去掉 AI 味」。
- 非豆包引擎：隐藏表演指示输入框。
- 试听列表：每条显示所用的表演指示。
- 「选定这条」：
  - 弹出一个小输入框填「角色基调」，默认值是这条试听的指示，可以修改。
  - 确认后，带上 `baseline` 调用 approve。
  - 已定档的声线要显示角色基调。
- 音色下拉：显示 label，以及 note 的前 12 个字。

**文档**：在 `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example` 的短片工作室段落里补充以下内容：
- 三个环境变量：`VOLC_SPEECH_API_KEY`、`VOLC_SPEECH_RESOURCE_ID`、`FIONA_STUDIO_PRICE_DOUBAO_TTS_CNY_PER_10K_CHARS`。
- Key 的获取方式：在火山引擎「豆包语音」控制台开通「语音合成 2.0」，然后到「API Key」页复制。
- 「表演指示」与「角色基调」两个概念。
- 中文默认引擎改为豆包。

## 4. 分块（三块并发，只改各自的文件）

| 块 | 只许改的文件 | 测试 |
|---|---|---|
| **A 适配器** | 新建 `backend/studio/providers/tts_doubao.py`；`backend/studio/voices.py` | 新建 `backend/tests/test_studio_media_tts_doubao.py` |
| **B 后端接线** | `backend/studio/casting.py`、`casting_jobs.py`、`pricing.py`、`backend/routers/studio.py` | `test_studio_casting_api.py`、`test_studio_casting_jobs.py`、`test_studio_casting_integration.py` |
| **C 前端与文档** | `frontend/lib/studio-casting.ts`、`frontend/components/studio/VoicePanel.tsx`、`StudioAssetAudio.tsx`（如需）、`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example` | `test_studio_casting_frontend.py`，以及会读 `.env.example` 的既有文档测试 |

块 B 依赖块 A 的 §3.1 契约，按契约直接 import 即可。跑集成测试前，先用 `grep -n "def synthesize_doubao" backend/studio/providers/tts_doubao.py` 确认块 A 已经落盘；还没落盘就先做其他部分。块 B 绝不能自己去写适配器。

## 5. 验收

**块 A**：用 `MockTransport` 覆盖以下情况：
- 多行分块的成功流。
- `additions` 是字符串，并且解析后包含 `context_texts` 和 `post_process.pitch`。
- `rate` 换算和截断。
- 4xx、401、403、429 → rejected。
- 5xx → uncertain。
- 传输错误、超时 → uncertain。
- 流里没有 20000000 → uncertain。
- 响应体 code 为 45002001 → rejected。
- 缺 Key 时不发任何请求。
- 每个用例都断言 POST 只发了 1 次。
- 断言错误信息里不含 Key。

**块 B**：
- 豆包试听走完整链路：用真实适配器加注入的 `MockTransport`，走真实 ffmpeg（没有 ffmpeg 时 skip），产出 48k 单声道 WAV。
- `direction` 写进了试听的 spec。
- 422 的情况：非豆包引擎传指示、指示超长、pitch 不是整数。
- 503 的情况：缺 Key、缺 ffmpeg，且付费调用次数为 0。
- approve 带 `baseline` 和不带 `baseline` 两种情况。
- 预留和结算金额正确。

**块 C**：
- 引擎默认值、表演指示输入框的显示与隐藏、字数计数、选定时填角色基调、试听列表显示指示。
- `npx tsc --noEmit` 和 `npm run lint` 都是 0 error。

**通用**：
- `cd backend && <py> -m pytest -q tests/ -k studio` 全部通过。
- 每块写一份报告 `docs/tasks/2026-10-17-studio-wo3d-p2-doubao/03-report-<块>.md`。

**禁止**：联网（测试一律用 MockTransport）；读取 `.env`；读取或打印任何 Key；提交代码；隐藏或移动 `frontend/node_modules`。
