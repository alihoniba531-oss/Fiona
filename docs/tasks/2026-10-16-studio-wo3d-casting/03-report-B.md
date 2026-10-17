# WO3d 块 B 报告：付费适配与音频

> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
> 范围：§8.1 全部（Seedream 出图、CosyVoice / edge-tts 配音、声线特效与响度、音色目录、音频存储）
> 全部实现与测试离线：无任何真实付费调用、无真实网络、未提交 git。

## 1. 改了哪些文件

| 文件 | 动作 | 内容 |
|---|---|---|
| `backend/studio/providers/media_errors.py` | 新建 | `MediaCallError(status, code, message)`，`status ∈ {rejected, uncertain, failed}` |
| `backend/studio/providers/image_seedream.py` | 新建 | `SeedreamResult` + `generate_sheet`（单次 POST，不重试） |
| `backend/studio/providers/tts_cosy.py` | 新建 | `TtsResult` + `synthesize_cosy`（dashscope 延迟导入、全局 key 加锁） |
| `backend/studio/providers/tts_edge.py` | 新建 | `synthesize_edge`（edge_tts 延迟导入，WordBoundary → 秒） |
| `backend/studio/audio.py` | 新建 | `FX_PRESETS` / `parse_fx` / `ProcessedAudio` / `process_voice`（ffmpeg 异步 + 两遍 loudnorm） |
| `backend/studio/voices.py` | 新建 | `VOICE_CATALOG`（CosyVoice v2 九个 + edge-tts 七个） |
| `backend/studio/storage.py` | 只新增 | 追加 `MAX_AUDIO_BYTES` / `save_audio` / `probe_audio`；**旧函数零改动（67 行纯新增，0 删除）** |
| `backend/requirements.txt` | 只加一行 | `edge-tts==7.3.1` |
| `backend/tests/test_studio_media_seedream.py` | 新建 | 45 例 |
| `backend/tests/test_studio_media_tts.py` | 新建 | 17 例 |
| `backend/tests/test_studio_media_audio.py` | 新建 | 52 例（33 例特效/响度 + 19 例音频存储/probe） |

未触碰任何其他块的文件；`backend/tools/image_generation.py`、`backend/tts.py`、`backend/studio/store.py` 等一律没动。
两个滤镜源脚本 `/Users/yangjing/Desktop/视频生成/fx_robot.sh`、`fx_beast.sh` 只读。

## 2. 实现了什么（与 §8.1 逐字对齐）

接口名、参数名、参数默认值、返回字段已用 `inspect.signature` / `dataclasses.fields` 逐个核对，与 §8.1 完全一致：

- `MediaCallError(self, status, code, message)`，属性 `status / code / message`；未知 `status` 抛 `ValueError`。
- `SeedreamResult(png, width, height, model, usage)`；
  `generate_sheet(prompt, *, size, reference_images, model=None, transport=None)`。
- `TtsResult(audio, audio_format, sample_rate, chars, engine, voice, words)`；
  `synthesize_cosy(text, *, voice, rate, pitch, synthesizer_factory=None)`；
  `synthesize_edge(text, *, voice, rate, pitch, communicate_factory=None)`。
  `TtsResult` 定义在 `tts_cosy`，`tts_edge` 复用同一个 dataclass（`tts_cosy.TtsResult is tts_edge.TtsResult` 为真）。
- `FX_PRESETS`（robot A/B/Bd/C/D/E、beast A/B/C、inner A）、`parse_fx`、`ProcessedAudio(wav, sample_rate, samples, duration_s, measured_lufs, true_peak)`；
  `process_voice(raw, *, input_format, fx, target_lufs, true_peak=-1.5, timeout_s=60)`。
- `VOICE_CATALOG: list[dict]`（`engine / voice / label / lang / gender / note`）。
- `save_audio(project_id, data, *, ext=".wav") -> {"rel_path","sha256","bytes"}`；
  `probe_audio(path) -> {"duration_s","sample_rate","channels"}`。

### 2.1 Seedream（§8.1 + §11.2）
- 单次 POST `https://ark.cn-beijing.volces.com/api/v3/images/generations`，**绝不重试**。
- 请求体与 `backend/tools/image_generation.py` 的 ARK 分支逐字段一致：`model / prompt / size / response_format=b64_json / output_format=png / watermark=False`；参考图字段 `image`，data URI，**单张传字符串、多张传列表、无参考图不带该键**。
- 模型：`model` 参数 > `SEEDREAM_IMAGE_MODEL` > `doubao-seedream-5-0-flash-260915`；Key 读 `ARK_API_KEY`（缺失 → `failed/missing_configuration`，零请求）。
- `httpx.AsyncClient(transport=…, follow_redirects=False, trust_env=False, timeout=Timeout(150, connect=10, write=15, pool=10))`，`stream` 读取并限制 40MB。
- 错误分类：4xx（含 400/401/403/404/422）与 429 → `rejected`；超时 / 断连 / 3xx 未跟随 / 5xx / 2xx 坏 JSON / 缺或非法 `b64_json` / PNG 尺寸与请求不符 → `uncertain`；上游审核码（`sensitivecontentdetected` / `riskdetection` / `policyviolation` / `privacyinformation` / `deepfake` / `moderation`）→ `failed`。
- 错误文案经 `base.safe_message` 脱敏，不含 Key、data URI 或请求体。

### 2.2 CosyVoice（§8.1 + §11.2）
- `cosyvoice-v2` + `AudioFormat.WAV_48000HZ_MONO_16BIT`，返回 `audio_format="wav"`、`sample_rate=48000`、`words=None`（WO0 实测该 SDK 不返回逐字时间戳）。
- **模块顶层不 import dashscope**；`_synthesize_blocking` 在线程内延迟导入，`asyncio.to_thread` + `asyncio.wait_for(timeout=120)`。
- `dashscope.api_key` 是进程级共享状态且 SDK 在**构造**时读取，所以用模块级 `threading.Lock()` 包住「保存旧值 → 设置 → 构造并调用 → try/finally 恢复」；不残留被改写的全局 key（有专门测试断言恢复原值）。代价是合成串行，已在 docstring 说明。
- `rate`/`pitch`（0.5–2.0 浮点）映射到 SDK 的 `speech_rate`/`pitch_rate`（已核实 dashscope 1.25.18 只有这两个参数名）。
- 分类：审核码 → `failed`；明确 4xx/429 → `rejected`；未知异常 / 5xx / 空音频 / 超时 → `uncertain`（`timeout` / `empty_audio` / 上游码）。

### 2.3 edge-tts（§8.1 + §11.2）
- **模块内延迟导入** `edge_tts`（本机未安装，导入 `tts_edge` 仍然正常）；未安装 → `uncertain/edge_tts_unavailable`。
- `Communicate(text=, voice=, rate=, pitch=)`，`audio_format="mp3"`、`sample_rate=24000`；`words` 为 WordBoundary 列表 `[{offset_s, duration_s, text}]`，100 纳秒 ÷1e7 转秒。
- 超时 120 秒 → `uncertain`；明确 4xx → `rejected`；其余 SDK 报错 → `uncertain`。

### 2.4 音频处理（§10.2）
- 流程：解码 → `aresample=44100` → 套特效 → 第一遍 `loudnorm=I:TP:LRA=11:print_format=json`（解析 `measured_*`）→ 第二遍 `linear=true` + 实测值 + `,aresample=48000` → `-ac 1 -ar 48000 -c:a pcm_s16le` → 再跑一遍 loudnorm 回填 `measured_lufs`/`true_peak`。
- robot/inner 走 `-af`；beast（含 `asplit` 多路图）走 `-filter_complex "[0:a]aresample=44100,<chain>,loudnorm=…"`。
- 10 档滤镜**原样移植**：我用 stub `ffmpeg` 跑真脚本导出实参，再与原脚本展开逐字比对 —— `robot:A/B/Bd/C/D/E`、`beast:A/B/C` 全部 MATCH，`ALL VERBATIM: True`；同一条断言也固化在测试里。
- 全程 `asyncio.create_subprocess_exec`（无 `subprocess.run`、不阻塞事件循环），超时 `kill()` + `wait()`；`tempfile.TemporaryDirectory` 内先写临时文件，绝不原地读写。
- `shutil.which("ffmpeg")` 为空 → `RuntimeError("ffmpeg unavailable")`（消息逐字一致）。
- 失败（无音轨 / 损坏输入 / 非 0 退出 / JSON 解析失败 / 静音 / 输出格式异常 / 超时）统一抛 `AudioProcessError(RuntimeError)`。

### 2.5 音色目录（§10.3）与存储
- CosyVoice v2（zh）9 个、edge-tts（en 5 个 + zh 备选 2 个）共 16 条；拿不准的官方定位在 `note` 里写「官方定位待核实」。
- `save_audio`：内容寻址 `<pid>/audio/<sha256><ext>`，临时文件 + `os.replace` 原子替换，不留 `.part`；非法项目标识 / 扩展名 / 空数据抛 `ValueError`。
- `probe_audio`：`ffprobe -select_streams a:0`，只返回音频流信息；纯视频文件被判为无音频。

## 3. 约束核对（§2）

- 只新增 `edge-tts==7.3.1` 一行依赖；未改 `package.json` / lockfile / `globals.css`。
- 付费调用只发一次、不自动重试：Seedream 单次 POST；CosyVoice 单次 `call`；edge-tts 单次 `stream()`。
- 未联网：Seedream 测试用 `httpx.MockTransport`；CosyVoice / edge-tts 测试用注入的假工厂；`conftest.py` 的 socket 守卫全程未触发。
- 重 I/O 全部异步：`asyncio.to_thread`（SDK）+ `asyncio.create_subprocess_exec`（ffmpeg），ffmpeg 超时 kill，先写临时文件再改名。
- 未 import 探针（`rg '_studio_probe' backend/studio/` 无命中）；未 import `backend/tools/image_generation.py`、`backend/tts.py`。

## 4. 自测结果

- 指定命令：
  `cd backend && <Fiona venv>/bin/python -m pytest -q tests/test_studio_media_seedream.py tests/test_studio_media_tts.py tests/test_studio_media_audio.py`
  → **114 passed**（seedream 45 + tts 17 + audio 52）。
- 相关既有测试：`tests/test_studio_storage.py tests/test_studio_providers.py` → **87 passed**（storage 32 例含旧函数回归，全绿）。
- 工作室全量：`pytest -q tests/ -k studio` → **1454 passed**。
- 后端全量：`pytest -q` → **6992 passed, 1 failed, 5 errors**；失败/错误全部是
  `test_exchange_isolation.py` 与 `test_safe_http_deadline.py` 里
  `PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0)`——
  本沙箱不允许绑定本地端口，与块 B 无关（这些文件本次未被任何块改动）。

## 5. 未完成 / 需确认

1. **真实 SDK 路径未联网验证**（本期规定全离线）：真实 Seedream POST、真实 `dashscope` WebSocket 合成、真实 `edge_tts.Communicate` 都只验证了「注入工厂 + 错误分类」，未经真网。本机 venv 未安装 `edge-tts`，真实路径靠延迟导入 + requirements 留待主控安装后冒烟。
2. `studio/providers/__init__.py` 不在块 B 允许清单内，故没有导出新适配器。块 A 请直接：
   `from studio.providers.tts_cosy import TtsResult, synthesize_cosy`、`from studio.providers.tts_edge import synthesize_edge`、
   `from studio.providers.image_seedream import SeedreamResult, generate_sheet`、
   `from studio.providers.media_errors import MediaCallError`。
3. `ProcessedAudio.true_peak` 是**最终文件实测真峰值**（loudnorm `input_tp`），不是入参上限 `-1.5`；`meta_json` 若要记「上限」请用入参。
4. `process_voice` 的输出时长会因回声尾巴长于输入（2 秒正弦 → `beast:C`≈2.39 秒），块 A 不要假设时长等于输入。
5. 静音输入被显式判为 `AudioProcessError("输入音频为静音，无法进行响度标准化")`（规格外的防御：loudnorm 对静音返回 `-inf`）。
6. `probe_audio` 失败抛 `DownloadError`（`ffprobe_unavailable` / `invalid_output`，与既有 `probe_video` 同一约定），块 A 调用处请捕获它；`save_audio` 参数非法抛 `ValueError`。
7. `parse_fx` 对档位**大小写与空白宽容**（`"ROBOT:bd"` → `("robot","Bd")`）；`/voices/audition` 若要求严格字面匹配，用 `FX_PRESETS` 键精确比对即可，需要我改严格随时说。
8. Seedream 抛出的 `code` 采用 HTTP 派生（`http_400` / `http_429` / `http_5xx` / `http_3xx`），审核与本地校验用语义码；若块 A 想展示上游原始 code 可以再调整。
9. `audio._spawn` 是内部钩子（测试用它断言超时 kill），块 A 请勿重命名或删除。
10. `tts_cosy.SYNTHESIS_TIMEOUT_S` / `tts_edge.SYNTHESIS_TIMEOUT_S` 是模块常量（测试用它缩短超时）；CosyVoice 的 `rate/pitch` 在适配器内不做 0.5–2.0 范围校验，按规格由 REST / 块 A 校验。
