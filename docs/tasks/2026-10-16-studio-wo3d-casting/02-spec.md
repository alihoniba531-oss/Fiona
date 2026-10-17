# WO3d 短片工作室：开工确认、风格、定妆（G1）与声线

> 所属项目：Fiona「短片工作室」，12 期中的第 3d 期。WO0–WO3c 已合入 main（d11b60d）。
> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。
> **本期由多个执行者并行实现，每个执行者只负责一个「块」（见 §9）。只改自己块列出的文件；跨块只通过 §8 的接口约定交互；需要别的块的东西时，在自己的测试里用假实现（fake），不要去改别人的文件。**
> 必读：
> - 工作室现有代码：`backend/studio/{store,storage,pricing,spend,scheduler,recovery,brain,brain_jobs,brain_tasks,breakdown,breakdown_plan}.py`、`backend/routers/studio.py`、`frontend/components/studio/*`、`frontend/lib/studio.ts`、`frontend/lib/studio-breakdown.ts`。
> - WO0 实测：`docs/tasks/2026-10-16-studio-wo0-probe/06-probe-results.md`（Seedream、CosyVoice、edge-tts 三节），探针 `backend/scripts/_studio_probe_media.py`、`_studio_probe_speech.py`（只参考写法，业务代码不得 import 探针）。夹具：`backend/tests/fixtures/studio/seedream-*.json`、`cosyvoice-*.json`、`edge-tts-*.json`。
> - 前端改动前先读 `frontend/AGENTS.md` 与 `frontend/node_modules/next/dist/docs/` 里对应文档（Next.js 16）。

## 1. 产品目标

G0（分集方案）批准后，作者在「②定妆」页签里依次完成：

1. **开工确认**：确认这部片的视频分辨率（默认 480P）、默认视频模型（默认万相）、语言（中文 / 英文），画幅沿用项目设置。确认后才能进行后面三步。
2. **风格**：导演模型根据梗概、总表和分集方案给出 2–3 种风格方案，作者选一种，可以再微调文字，并选定写实度（写实 / 动漫 / 3D）。这一步先报价、确认后才调用。
3. **G1 定妆**：总表里的每个人物、场景、道具都要定妆（或标为「不需要定妆」）。
   - 作者勾选若干条目、设每项出几版（1–4），按批报价，确认一次后批量出图（Seedream 5.0，三视图，纯白背景）。
   - 每个条目的多个版本并排显示，作者选定一个版本并确认该条目；废版只归档，不删除。
   - 可以给条目上传参考图，或以已选定的版本为参考派生新版本。
   - 可以填写「锁定特征」（作者认可、以后不得改动的特征，包括作者选中的「缺陷」），出图提示词会带上。
   - 原文没有外形描述（「待作者补充」）的人物，必须先补写外形才能出图。
   - 所有条目都确认或跳过，即 **G1 通过**。
4. **声线**（只针对人物）：
   - 每个角色配置最多 3 个试听方案（引擎、音色、语速、音高、声线特效），用一句试听台词生成试听，作者选定一条，定档。
   - 中文用 CosyVoice（付费，金额很小，不弹报价框，但先预留额度并受上限约束）；英文用 edge-tts（免费）。
   - 声线特效：机器人 / 巨兽 / 内心独白，各有档位；特效之后做两遍响度标准化，输出 48kHz 单声道 WAV。

本期**不做**：看图质检（导演模型看图提示）、关键帧、视频、本集剧本。真实 Key 的付费冒烟由主控在合并后单独报价执行，本期实现与测试全部离线。

## 2. 约束（红线，所有块都适用）

- 不联网。所有测试用假实现（fake transport / fake SDK / monkeypatch）。不提交。派子代理时不要传 model 和 reasoning_effort。
- **唯一新增依赖**：`edge-tts==7.3.1`（只由块 B 写进 `backend/requirements.txt`）。其他一律不加。不改 `package.json`、lockfile、`globals.css`。
- 数据库只做新增：新表，或在 `store.py` 的 `STUDIO_TABLES_DDL` 与 `migrate_schema` 补列字典里同时补列（只有块 A 改 `store.py`）。删号时新表的行在 `database.py` 删号事务里一并删除。
- **付费调用只发一次**（沿用 WO1/WO3a 规则）：
  - 出图、配音都不得自动重试。超时、断连、5xx、2xx 但解析失败 → `uncertain`（保留预留，只能手动释放）；明确 4xx / 429 → `rejected`（释放预留）；内容审核拒绝 → `failed`（按 0 结算）。
  - HTTP 客户端 `follow_redirects=False`、`trust_env=False`，可注入 transport 供测试。
- **报价只能确认一次**，15 分钟过期只约束确认；确认后预留随任务保留到结束。人民币单次报价不得超过 `FIONA_STUDIO_MAX_QUOTE_CNY`，且「已用 + 预留 + 本次」不超过日上限；超限 409，不发任何请求。
- 所有重 I/O（读写图片音频、ffmpeg 子进程、解码）一律 `asyncio.to_thread` 或 `asyncio.create_subprocess_exec`，不得在事件循环里同步执行。ffmpeg 子进程设超时，超时 kill；先写临时文件再改名，绝不原地读写同一文件。
- 所有经由 node 驱动的新前端测试，在 `frontend/node_modules` 缺少所需包时 `pytest.skip`（参照 `backend/tests/test_studio_frontend_components.py` 的 `probe()`）。所有需要 ffmpeg 的测试，在 `shutil.which("ffmpeg")` 为空时 `pytest.skip`。
- 测试夹具不得出现第三方受版权保护的文字或图片，一律自写 / 程序生成（例如用 PIL 生成纯色 PNG、用 ffmpeg 生成正弦波）。
- 不改非工作室的测试；不改聊天相关代码（`backend/tools/image_generation.py`、`backend/tts.py`、`services/*` 都不要动）。

## 3. 数据（块 A 实现）

### 3.1 `studio_projects` 补列
| 列 | 说明 |
|---|---|
| `setup_json` TEXT NULL | `{"resolution":"480P"|"720P"|"1080P","video_model":"wan"|"seedance","language":"zh"|"en"}` |
| `setup_confirmed_at` TEXT NULL | 开工确认时间 |
| `style_json` TEXT NULL | 选定的风格：`{"name","visual_style","palette","camera","lighting","rationale","realism":"photoreal"|"anime"|"3d","source":"proposal"|"custom","proposal_index":int|null}` |
| `style_group_id` TEXT NULL | 最近一次风格提案导演任务的 group_id |

### 3.2 新表 `studio_items`（定妆条目，一个总表条目对应一行）
`id` TEXT PK、`project_id`、`owner`、`bible_id`（指向 `studio_bible.id`）、`kind`（`character / location / prop`）、`name`、`status`（`pending / approved / skipped`，CHECK）、`spec_json`（`{"locked_features":"", "extra_prompt":"", "reference_asset_ids":[], "voice": {voice spec} | null}`）、`approved_asset_id` NULL、`voice_asset_id` NULL、`created_at`、`updated_at`；`UNIQUE(project_id, bible_id)`。
- 条目按需同步：读取定妆数据时，为当前拆解总表里每个未归档、未被合并的条目补建 `studio_items` 行；总表条目已归档或被合并的，对应条目在返回里标 `orphaned: true`，不删除。
- `approved_asset_id` 必须是本条目、未归档的图片版本；`voice_asset_id` 必须是本条目、未归档的试听音频。

### 3.3 `studio_assets` 补列
`item_id` TEXT NULL、`version_no` INTEGER NULL（同条目同类资产内从 1 递增）、`role` TEXT NULL（`sheet` 定妆图 / `audition` 试听 / `reference` 参考图）。现有 `meta_json` 存提示词、参数、尺寸、音频时长与实测响度。废版用现有 `archived` 列。

### 3.4 `studio_jobs` 补列与新 kind
- 补列：`media_provider` TEXT NULL（`seedream / cosyvoice / edge-tts`）、`item_id` TEXT NULL。
- 新 kind：`image`（出图）、`tts`（试听配音）。`provider` 列仍需满足旧 CHECK，填占位 `'wan'`（与 WO3a 导演任务同一做法），真实提供方看 `media_provider`。
- **注意现有代码的坑**（块 A 负责处理）：
  - `store.cas_job` 用 `params["resolution"]` 结算 → 新 kind 不得走这条路径，自己写结算。
  - `recovery.py` 把所有 kind≠brain 的任务当视频恢复 → 必须改为按 kind 分派：`i2v` 原逻辑不变；`image / tts` 与导演任务相同：`running / submitting` 改 `uncertain`，`queued` 等调度补发，绝不重发。
  - `store.list_jobs` 只返回 i2v → 保持不变（定妆任务另有接口）。
  - 调度器只领 i2v → 新 kind 用独立的后台执行：每个 `media_provider` 一个 Semaphore（seedream 默认 3、cosyvoice 2、edge-tts 2，可用环境变量 `FIONA_STUDIO_MAX_INFLIGHT_IMAGE / _TTS` 覆盖，合法 1–10）。确认后立即派发；调度器 tick 补发遗留的 queued。

### 3.5 价格（块 A 写进 `pricing.py`）
- Seedream 出图：`FIONA_STUDIO_PRICE_SEEDREAM_CNY` 默认 `0.30`（元/张，**待核实**，注释写明「Seedream 响应不含计费字段，按此价预留与结算」）。
- CosyVoice：`FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS` 默认 `2.0`（元/万字符，待核实），按字符数预留与结算，最低 0.01 元。
- edge-tts：0 元。
- 非法值回落默认并告警一次。

## 4. 开工确认与风格（块 A 实现流程，块 C 提供输入组装）

- `PUT /setup`：校验 G0 已批准（`breakdown_plan` 里的 g0 判定），写 `setup_json` 与 `setup_confirmed_at`。重新确认会覆盖（不影响已出的定妆）。
- 风格提案：复用 WO3a 的 `style_proposals` 导演任务与 schema，**绑定当前项目**（不得走「没绑定就新建项目」的旧路径）。输入由块 C 的 `casting_prompts.style_inputs(...)` 组装：梗概、人物/场景/道具名与外形摘要、集数与总时长、开工确认里的语言。
  - 先报价（单项导演任务，复用 WO3c 的报价写法：`_write_quote` 风格的 quote，15 分钟有效，确认一次），确认后执行。
  - 结果在 `GET /casting` 里以 `style.proposals` 返回（读该 group 的成功结果）。
- `PUT /style`：作者选定提案（`proposal_index`）或自定义（字段同提案 + `realism`），写 `style_json`。`realism` 必填。

## 5. 定妆出图（块 A 编排，块 B 出图，块 C 提示词）

- 前置：G0 已批准、开工已确认、风格已选定。否则 409 并说明缺哪一步。
- `POST /sheets/quote`：`{"items":[{"item_id","versions":1-4,"extra_prompt"?:str≤500,"reference_asset_ids"?:[≤4],"derive_from_approved"?:bool}]}`，最多 30 个条目、合计 ≤ 60 张。
  - 人物条目 `needs_author` 仍为真（外形未补）时拒绝该条并说明。
  - `derive_from_approved=true` 时把该条目已选定的版本作为第 1 张参考图（只取身份、脸型、发型、体型 / 结构、材质），参考图总数 ≤ 4。
  - 报价 = 张数 × 单价；校验单次上限与日上限；写 quote（items 里只存条目 id、版本数、参考图 asset id 与估价，**不存图片字节**）。
- `POST /sheets/start {quote_id}`：确认一次；为每一张图建一条 `kind='image'` 任务并预留；立即派发。
- 执行（每张一个任务）：
  1. 组装提示词：块 C `build_sheet_prompt(...)`。
  2. 读参考图字节（长边缩到 ≤1536，PNG/JPEG），在线程里做。
  3. 调块 B `generate_sheet(prompt, size="2560x1440", reference_images=[...])`。**定妆图一律 2560×1440 横幅**（三视图横排），与项目画幅无关。
  4. 成功：`storage.save_image` 落盘，建 `studio_assets`（`role='sheet'`、`item_id`、`version_no` 递增、`meta_json` 含提示词与参考图 id），按单价结算。
  5. 失败按 §2 分类。
- 条目操作：`approve {asset_id}`（设 `approved_asset_id`、状态 `approved`）、`skip`、`reopen`（回到 `pending`）、改 `locked_features / extra_prompt / reference_asset_ids`、`POST /assets/{aid}/archive`（归档版本；已选定的版本不能归档，先换选定）。
- **G1 通过** = 所有非 orphaned 条目都是 `approved` 或 `skipped`，且至少有 1 个 `approved`。

## 6. 声线（块 A 编排，块 B 合成与处理）

- 前置：开工已确认。只对 `kind='character'` 的条目。
- `POST /voices/audition`：`{"item_id","text":1–120 字,"variants":[{"engine":"cosyvoice"|"edge-tts","voice","rate","pitch","fx":null|"robot:B"|...,"role":"dialogue"|"narration"}] (1–3 个)}`。
  - `voice` 必须在块 B 的 `VOICE_CATALOG` 里且引擎匹配；`fx` 必须是 `FX_PRESETS` 的合法档位。
  - CosyVoice：`rate`、`pitch` 为 0.5–2.0 的浮点；edge-tts：`rate` 形如 `+5%`/`-8%`（-50% 到 +50%），`pitch` 形如 `+0Hz`/`-3Hz`（-50Hz 到 +50Hz）。
  - 不弹报价框，但每条按字符数预留（edge-tts 预留 0），受日上限约束，超限 409。每个变体一条 `kind='tts'` 任务，立即派发。
- 执行：块 B `synthesize_cosy` / `synthesize_edge` → 块 B `process_voice(raw, fx=..., target_lufs=-16 对白 / -18 旁白, true_peak=-1.5)` → `storage.save_audio` → 建 `studio_assets`（`kind='audio'`、`role='audition'`、`meta_json` 含 spec、时长、实测 LUFS）→ 结算。
- `POST /items/{item_id}/voice/approve {asset_id}`：设 `voice_asset_id`，并把该试听的 spec 写进 `spec_json.voice`（定档）。
- `GET /voice-catalog`：返回块 B 的 `VOICE_CATALOG` 与 `FX_PRESETS` 的档位清单（不含滤镜字符串）。

## 7. 前端（块 D 实现）

「②定妆」页签（`StudioWorkbench.tsx` index 1）挂载新组件 `CastingStage`，自上而下：
1. **门禁提示**：G0 未批准时只显示「请先在①拆解批准分集方案」，不渲染其他部分。
2. **开工确认卡**：画幅（只读，显示项目设置）、视频分辨率（`.chip` 单选 480P / 720P / 1080P，默认 480P，旁注单价「万相 ¥0.3 / ¥0.6 / ¥1.2 每秒」）、默认视频模型（万相 / Seedance）、语言（中文 / 英文）、定妆图尺寸（只读：2560×1440）。按钮「确认开工设置」；已确认时显示摘要和「修改」。
3. **风格卡**：「生成风格提案」→ 报价对话框（金额、模型、过期倒计时）→ 确认 → 进行中状态（每 5 秒轮询，完成即停）→ 2–3 张提案卡，每张「选这个」。选定后显示可编辑的风格字段与写实度单选（写实 / 动漫 / 3D），「保存风格」。
4. **定妆区**：「人物 / 场景 / 道具」三个页签（`useRovingTabs`）。
   - 每个条目一张卡：名字、外形摘要（人物待补时醒目提示「先补外形」并给出就地编辑外形的入口，调用已有 `PATCH /studio/bible/{id}`）、状态 tag、锁定特征（可编辑）、版本缩略图网格（`StudioAssetImage`，点开大图对话框）。
   - 每个版本：选定、归档。条目操作：确认此条、标为不需要、重新打开。
   - 勾选多个条目后出现批量栏：每项版本数（1–4）、「以选定版为参考派生」、补充提示词、参考图上传（复用已有 `POST /projects/{pid}/assets` 上传图片，得到 asset id）→「报价出图」→ 报价对话框（逐项列出：条目 × 版本数 × 单价，合计，过期倒计时）→ 确认。
   - 进行中的出图任务以占位卡显示在对应条目的版本网格里；`uncertain` 显示「可能已扣费」与「释放」，`rejected` 显示原因。有在途任务时每 5 秒轮询。
   - 顶部 G1 进度条：「已确认 x / 共 y（跳过 z）」，通过时显示「G1 定妆通过」。
5. **声线区**（只列人物）：每个角色一张卡：
   - 试听台词（默认填该人物的第一句外形摘录或「我是{名字}。」）。
   - 最多 3 个方案行，每行：引擎、音色（下拉，来自 `/voice-catalog`）、语速、音高、特效（无 / 机器人 A–E 等）、角色类型（对白 / 旁白）。
   - 「生成试听」（中文显示「约 ¥0.0x」，英文显示「免费」）。
   - 试听列表：每条一个新组件 `StudioAssetAudio`（按 asset id 取 blob → objectURL → `<audio controls>`，类型须为 `audio/*`），显示方案摘要与实测响度，「选定这条」。
   - 已定档的显示「已定档」与方案摘要。
6. 所有异步区块都有加载、空、错误、成功状态；按钮忙碌时禁用。390px 宽度不出现横向页面滚动。宋式清雅 × 液态玻璃：沿用 `Glaze`、`ceramic-card`、`.btn`、`.chip`、`.tag`、`.readout`、原生 `<dialog>`（可复用 `BreakdownDialog.tsx` 外壳）。

## 8. 接口约定（各块必须严格遵守；名称、参数、返回字段不得自行更改）

### 8.1 块 B 提供（Python）
```python
# backend/studio/providers/media_errors.py
class MediaCallError(Exception):
    def __init__(self, status: str, code: str, message: str): ...   # status ∈ {"rejected","uncertain","failed"}
    status: str; code: str; message: str

# backend/studio/providers/image_seedream.py
@dataclass
class SeedreamResult:
    png: bytes; width: int; height: int; model: str; usage: dict
async def generate_sheet(prompt: str, *, size: str, reference_images: list[bytes],
                         model: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> SeedreamResult
# 单次 POST、follow_redirects=False、trust_env=False；Key 读 ARK_API_KEY，模型默认读 SEEDREAM_IMAGE_MODEL（同 Fiona 现有默认）；
# 参考图转 data URI，单张传字符串、多张传列表；校验返回 PNG 尺寸与 size 一致；错误抛 MediaCallError。

# backend/studio/providers/tts_cosy.py
@dataclass
class TtsResult:
    audio: bytes; audio_format: str; sample_rate: int; chars: int; engine: str; voice: str; words: list | None
async def synthesize_cosy(text: str, *, voice: str, rate: float, pitch: float, synthesizer_factory=None) -> TtsResult
# cosyvoice-v2、WAV_48000HZ_MONO_16BIT；在线程里调用 SDK；Key 用 DASHSCOPE_API_KEY，不得在无锁情况下改写全局 dashscope.api_key
# （SDK 若支持按调用传 key 就按调用传；否则用模块级锁包住「设置→调用→恢复」）；超时 120 秒 → uncertain。

# backend/studio/providers/tts_edge.py
async def synthesize_edge(text: str, *, voice: str, rate: str, pitch: str, communicate_factory=None) -> TtsResult
# edge-tts 7.3.1，audio_format="mp3"、sample_rate=24000，words 为 WordBoundary 列表 [{offset_s, duration_s, text}]。

# backend/studio/audio.py
FX_PRESETS: dict[str, dict[str, str]]   # {"robot": {"A":…, "B":…, "Bd":…, "C":…, "D":…, "E":…}, "beast": {"A":…,"B":…,"C":…}, "inner": {"A":…}}
def parse_fx(fx: str | None) -> tuple[str, str] | None   # "robot:B" → ("robot","B")；非法抛 ValueError
@dataclass
class ProcessedAudio:
    wav: bytes; sample_rate: int; samples: int; duration_s: float; measured_lufs: float; true_peak: float
async def process_voice(raw: bytes, *, input_format: str, fx: str | None, target_lufs: float,
                        true_peak: float = -1.5, timeout_s: float = 60) -> ProcessedAudio
# 流程：解码 → 重采样到 44100 → 特效（滤镜按 44100 调校，见 §10）→ 两遍 loudnorm（LRA=11，第二遍 linear=true 带实测值）
# → 重采样 48000 → pcm_s16le 单声道。ffmpeg 不存在时抛 RuntimeError("ffmpeg unavailable")。

# backend/studio/voices.py
VOICE_CATALOG: list[dict]   # [{"engine":"cosyvoice"|"edge-tts","voice":str,"label":str,"lang":"zh"|"en","gender":"male"|"female","note":str}]

# backend/studio/storage.py（新增函数，不改旧函数行为）
def save_audio(project_id: str, data: bytes, *, ext: str = ".wav") -> dict   # {"rel_path","sha256","bytes"}；路径 <pid>/audio/<sha256>.wav；原子写入
def probe_audio(path) -> dict   # {"duration_s","sample_rate","channels"}；ffprobe 只看音频流
```

### 8.2 块 C 提供（Python，`backend/studio/casting_prompts.py`）
```python
def style_inputs(*, synopsis: dict, bible: list[dict], episodes: list[dict], language: str) -> dict
def build_sheet_prompt(*, kind: str, name: str, appearance: str, description: str, locked_features: str,
                       style: dict, extra_prompt: str = "", reference_notes: list[str] = ()) -> str
def reference_note(kind: str, derived: bool) -> str   # 每张参考图「只取什么、不取什么」的说明
```

### 8.3 块 A 提供（REST，全部在 `/studio` 下，作者门禁，请求模型 `extra="forbid"`）
| 方法与路径 | 请求 | 返回 |
|---|---|---|
| `GET /projects/{pid}/casting` | — | `CastingState`（见下） |
| `PUT /projects/{pid}/casting/setup` | `{resolution, video_model, language}` | `CastingState` |
| `POST /projects/{pid}/casting/style/quote` | `{}` | `CastingQuote` |
| `POST /projects/{pid}/casting/style/start` | `{quote_id}` | `CastingState` |
| `PUT /projects/{pid}/casting/style` | `{proposal_index}` 或 `{custom:{name,visual_style,palette,camera,lighting,rationale}}`，外加 `realism` | `CastingState` |
| `PATCH /casting/items/{item_id}` | `{locked_features?, extra_prompt?, reference_asset_ids?}` | `CastingItem` |
| `POST /casting/items/{item_id}/approve` | `{asset_id}` | `CastingItem` |
| `POST /casting/items/{item_id}/skip` · `/reopen` | `{}` | `CastingItem` |
| `POST /casting/assets/{asset_id}/archive` | `{}` | `{ok:true}` |
| `POST /projects/{pid}/casting/sheets/quote` | 见 §5 | `CastingQuote` |
| `POST /projects/{pid}/casting/sheets/start` | `{quote_id}` | `CastingState` |
| `POST /projects/{pid}/casting/voices/audition` | 见 §6 | `CastingState` |
| `POST /casting/items/{item_id}/voice/approve` | `{asset_id}` | `CastingItem` |
| `GET /casting/voice-catalog` | — | `{voices: VOICE_CATALOG, fx: {"robot":["A","B",…],…}}` |
| 已有 `POST /jobs/{jid}/release` | — | 对 `image / tts` 的 uncertain 任务同样适用 |

```ts
type CastingState = {
  g0_approved: boolean;
  setup: { aspect: "16:9"|"9:16"; resolution: "480P"|"720P"|"1080P"; video_model: "wan"|"seedance"; language: "zh"|"en"; sheet_size: "2560x1440"; confirmed_at: string } | null;
  style: { chosen: StyleChoice | null; proposals: StyleProposal[]; proposal_job: CastingJob | null };
  items: CastingItem[];
  g1: { approved: boolean; total: number; done: number; skipped: number };
  jobs: CastingJob[];             // 本项目 image/tts/风格任务：在途全部 + 最近 50 条已结束
  prices: { seedream_cny: number; cosyvoice_cny_per_10k_chars: number };
};
type StyleProposal = { name: string; visual_style: string; palette: string; camera: string; lighting: string; rationale: string };
type StyleChoice = StyleProposal & { realism: "photoreal"|"anime"|"3d"; source: "proposal"|"custom"; proposal_index: number|null };
type CastingItem = {
  id: string; bible_id: string; kind: "character"|"location"|"prop"; name: string; role: string;
  appearance: string; description: string; needs_author: boolean; orphaned: boolean;
  status: "pending"|"approved"|"skipped"; locked_features: string; extra_prompt: string; reference_asset_ids: string[];
  approved_asset_id: string|null;
  versions: { asset_id: string; version_no: number; created_at: string; archived: boolean; prompt: string }[];
  voice: null | { spec: VoiceSpec|null; approved_asset_id: string|null;
                  auditions: { asset_id: string; spec: VoiceSpec; text: string; duration_s: number; measured_lufs: number; created_at: string; archived: boolean }[] };
};
type VoiceSpec = { engine: "cosyvoice"|"edge-tts"; voice: string; rate: number|string; pitch: number|string; fx: string|null; role: "dialogue"|"narration" };
type CastingJob = { id: string; kind: "image"|"tts"|"brain"; item_id: string|null; status: string; error_code: string|null;
                    error_message: string|null; reserved_amount: number; actual_amount: number|null; currency: "CNY"|"USD"; created_at: string };
type CastingQuote = { id: string; kind: "casting_style"|"casting_sheets"; items: { item_id: string|null; name: string; versions: number; unit: number; est: number }[];
                      total: number; currency: "CNY"|"USD"; expires_at: string };
```
错误一律 `HTTPException`：404（不存在或非本人）、409（前置未满足、上限、状态冲突，`detail` 为中文说明）、422（参数非法）。

## 9. 并发拆分（每块一个执行者，文件互不重叠）

| 块 | 负责 | 只允许改 / 新建的文件 | 测试文件（新建） |
|---|---|---|---|
| **A 后端数据与编排** | §3 数据、§4–§6 流程与路由、价格、恢复、调度、删号、`CastingState` 组装 | `backend/studio/store.py`、`backend/studio/casting.py`（新）、`backend/studio/casting_jobs.py`（新）、`backend/studio/pricing.py`、`backend/studio/spend.py`、`backend/studio/recovery.py`、`backend/studio/scheduler.py`、`backend/routers/studio.py`、`backend/database.py` | `backend/tests/test_studio_casting_api.py`、`test_studio_casting_jobs.py`、`test_studio_casting_recovery.py` |
| **B 付费适配与音频** | §8.1 全部 | `backend/studio/providers/media_errors.py`、`image_seedream.py`、`tts_cosy.py`、`tts_edge.py`（均新）、`backend/studio/audio.py`（新）、`backend/studio/voices.py`（新）、`backend/studio/storage.py`、`backend/requirements.txt` | `backend/tests/test_studio_media_seedream.py`、`test_studio_media_tts.py`、`test_studio_media_audio.py` |
| **C 提示词与风格输入** | §8.2；风格提案提示词补充；文档 | `backend/studio/casting_prompts.py`（新）、`backend/studio/prompts/style_proposals.md`（只追加「项目风格」段，不改原有内容）、`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example` | `backend/tests/test_studio_casting_prompts.py` |
| **D 前端** | §7 全部 | `frontend/components/studio/CastingStage.tsx`、`SetupCard.tsx`、`StyleCard.tsx`、`CastingItems.tsx`、`CastingItemCard.tsx`、`VoicePanel.tsx`、`StudioAssetAudio.tsx`、`CastingQuoteDialog.tsx`（均新）、`frontend/lib/studio-casting.ts`（新）、`frontend/components/studio/StudioWorkbench.tsx`（只改 index 1 的渲染为挂载 `CastingStage`） | `backend/tests/test_studio_casting_frontend.py` |

- 块 A 的测试里，对块 B / C 的函数一律 monkeypatch 成假实现（按 §8 的签名）；块 D 的测试用假的 `apiJson` 返回 §8.3 的形状。
- 跨块真正接通后的集成测试由主控补写与执行，各块不必等别人。
- 各块完成后在 `docs/tasks/2026-10-16-studio-wo3d-casting/03-report-<块字母>.md` 写报告：改了哪些文件、实现了什么、与本规格的逐项对应、自测结果、未完成或需确认的地方。

## 10. 实现细节（相关块必读）

### 10.1 定妆提示词要点（块 C）
- 版式：人物「三视图：正面、侧面、背面全身」，场景「同一地点的三个机位：全景、中景、细节」，道具「三视图：正面、侧面、背面，另加一处细节特写」；视图之间留白、不加任何文字标签、纯白干净背景、边缘清晰便于抠像；16:9 横幅。
- 写实度：`photoreal` 加真实皮肤质感描述、负向「不要动漫、不要插画」；`anime` 负向「不要照片质感、不要写实」；`3d` 负向「不要照片、不要二维线稿」。
- 写明「原创角色 / 原创设计，不模仿任何已知作品、品牌或真人」。
- `locked_features` 原样列为「必须保持」；`appearance`、`description` 作为主体描述；`extra_prompt` 附在最后；参考图说明逐张列出（`reference_note`：派生自已选定版本时「只取身份、脸型、发型、体型，不取姿势与背景」；场景「只取建筑结构、陈设、朝向」；道具「只取结构、材质、颜色」）。
- 风格段：`visual_style`、`palette`、`lighting`、`camera` 拼入。
- 总长度 ≤ 1800 字符（超出时按优先级裁掉 extra_prompt、description 的尾部，保证 locked_features 与版式完整）。

### 10.2 声线特效（块 B）
滤镜按 44100 Hz 调校，`process_voice` 先重采样到 44100 再套特效：
- `robot:B`：`afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=768:overlap=0.75,highpass=f=85,lowpass=f=6800,equalizer=f=2200:t=q:w=1.0:g=7,equalizer=f=3600:t=q:w=1.2:g=4,aecho=0.85:0.8:16:0.18`；A / Bd / C / D / E 档参照 `/Users/yangjing/Desktop/视频生成/fx_robot.sh` 第 18–23 行原样移植（只读该文件，不要修改它）。机器人音高由 `win_size` 决定（512→高、768→中、1024→低），各档保留原值。
- `beast:C`（用 filter_complex）：`asplit=3[a][b][c];[b]asetrate=44100*0.5,aresample=44100,atempo=2.0,volume=1.0[sub];[c]asetrate=44100*1.00695,aresample=44100,atempo=0.99310,volume=0.55[det];[a][sub][det]amix=inputs=3:weights=1 0.9 0.45:normalize=0,bass=g=8:f=100:w=0.7,lowpass=f=6000[mix];[mix]asplit=2[dry][wet];[wet]lowpass=f=1800,aecho=0.68:0.66:53|97|163|251|389:0.38|0.31|0.24|0.17|0.11,volume=1.0[rev];[dry][rev]amix=inputs=2:weights=1 0.8:normalize=0,equalizer=f=210:t=q:w=1.1:g=4,acompressor=threshold=-20dB:ratio=4:attack=10:release=200,volume=1.35`；A / B 档参照 `/Users/yangjing/Desktop/视频生成/fx_beast.sh` 第 29–30 行。
- `inner:A`：`lowpass=f=6800,aecho=0.85:0.3:60:0.18,equalizer=f=300:t=q:w=1.0:g=2,volume=1.05`。
- 响度：第一遍 `loudnorm=I={I}:TP={TP}:LRA=11:print_format=json`（解析 measured_*）；第二遍 `loudnorm=I={I}:TP={TP}:LRA=11:linear=true:measured_I=…:measured_TP=…:measured_LRA=…:measured_thresh=…:offset=…,aresample=48000`，输出 `-ac 1 -ar 48000 -c:a pcm_s16le`；最后用 `ebur128` 或再跑一遍 loudnorm 测量回填 `measured_lufs`。

### 10.3 音色目录（块 B 的 `VOICE_CATALOG` 初始内容）
- CosyVoice v2（zh）：`longxiaocheng_v2`、`longjielidou_v2`、`longze_v2`、`longyuan_v2`、`longfei_v2`、`longshu_v2`、`longlaotie_v2`、`longjing_v2`、`longxiaoxia_v2`（性别与备注按官方说明填写；拿不准就写「待核实」）。
- edge-tts（en）：`en-US-AndrewNeural`、`en-US-BrianNeural`、`en-US-ChristopherNeural`、`en-US-AriaNeural`、`en-US-JennyNeural`；（zh 备选）`zh-CN-YunyangNeural`、`zh-CN-XiaoxiaoNeural`。

## 11. 验收（主控集成后统一执行）

### 11.1 命令
- 后端全量两种环境（带 / 不带 `frontend/node_modules`）0 failed；前端 lint（0 error、警告不超过基线）、tsc、build 通过。

### 11.2 必测项（各块自测覆盖自己的部分；主控补集成测试）
- **块 A**：
  - G0 未批准、未开工确认、未选风格时，各接口 409 且 0 次付费调用。
  - 出图报价：单价 × 张数；超单次上限或日上限 409、0 次调用；同一报价确认两次 409；过期不能确认；`needs_author` 条目被拒。
  - 每张图一条任务并预留；成功落资产并结算；`rejected` 释放；`uncertain` 保留直至手动释放；派发不重复。
  - 恢复：`running` 的 image/tts 变 uncertain，`queued` 补发，POST 次数为 0；i2v 与 brain 的恢复行为不变（现有测试全过）。
  - 条目同步：总表新增 / 归档 / 合并后，条目补建或标 orphaned。approve 只接受本条目未归档的版本；归档已选定版本 409。G1 判定正确。
  - 声线：音色与特效校验；CosyVoice 按字数预留与结算，edge-tts 为 0；定档写 spec。
  - 归属：别人的项目、条目、资产、报价一律 404；删号清理新表；风格提案绑定当前项目。
- **块 B**：
  - Seedream：单次 POST；请求体字段与 Fiona 现有一致；参考图单张为字符串、多张为列表；超时 / 断连 / 5xx / 2xx 坏 JSON → uncertain；4xx / 429 → rejected；返回尺寸不符 → uncertain；不跟随重定向。
  - CosyVoice：参数传递正确；超时 → uncertain；SDK 报错分类；不留下被改写的全局 key。
  - edge-tts：WordBoundary 解析为秒；SDK 报错 → uncertain。
  - 音频：用 ffmpeg 生成的正弦波作输入，三类特效各至少一档能跑通；输出为 48000 Hz、单声道、s16；两遍 loudnorm 后实测响度在目标 ±1 LU 内；ffmpeg 超时会被 kill；没有 ffmpeg 时 skip。
  - `save_audio` 原子写、路径校验；`probe_audio` 只看音频流。
- **块 C**：三类条目的版式文字；三种写实度的负向；锁定特征必在；长度上限与裁剪优先级；参考图说明；`style_inputs` 不含原文全文、只含摘要。
- **块 D**：各区块的门禁、加载、空、错误、成功状态（SSR）；报价对话框逐项与合计；版本选定 / 归档、条目确认 / 跳过；待补外形的提示与入口；试听播放组件只接受 `audio/*`；`StudioAssetAudio` 释放 objectURL；全部带缺依赖 skip 守卫。
