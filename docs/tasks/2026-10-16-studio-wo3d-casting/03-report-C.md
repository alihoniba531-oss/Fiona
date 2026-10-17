# WO3d 块 C 执行报告：提示词与风格输入

## 自测结果

```
cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_casting_prompts.py
..........                                                               [100%]
10 passed in 0.25s
```

另跑了 4 个会读取 `backend/.env.example` 的既有文档测试，确认追加环境变量没有影响它们：

```
python -m pytest -q tests/test_claude_agent_docs.py tests/test_chat_image_tool_docs.py tests/test_local_watch_docs.py tests/test_local_watch_capture_docs_r3.py
64 passed in 0.32s   （含上面 10 个）
```

未联网、未新增依赖、未提交；全程只改自己块的文件。

## 改动的文件

| 文件 | 动作 | 内容 |
|---|---|---|
| `backend/studio/casting_prompts.py` | 新建 | §8.2 三个函数：`style_inputs` / `build_sheet_prompt` / `reference_note`，纯函数，不发请求、不读文件、不碰数据库 |
| `backend/tests/test_studio_casting_prompts.py` | 新建 | 10 个纯函数用例（版式、负向、锁定特征、原创声明、参考图说明、长度与裁剪优先级、摘要-only、语言与空输入、非法参数） |
| `backend/studio/prompts/style_proposals.md` | 末尾追加 | 追加「项目风格」段（原文一字未改，diff 为 +2 行） |
| `backend/.env.example` | 末尾追加 | WO3d 小节：4 个新环境变量、新依赖说明 |
| `CLAUDE.md` | 末尾追加 | WO3d 段落 4 段（流程、G1、声线、上限与单价/依赖） |
| `README.md` | 末尾追加 | WO3d 段落 4 段（面向作者的流程说明） |
| `docs/ARCHITECTURE.md` | 末尾追加 | 新增 `### WO3d 定妆（G1）与声线` 子节 4 段（模块、出图、声线、并发与价格） |

未碰：块 A 的 `store.py / casting.py / casting_jobs.py / pricing.py / spend.py / recovery.py / scheduler.py / routers/studio.py / database.py`，块 B 的 `providers/*`、`audio.py`、`voices.py`、`storage.py`、`requirements.txt`，块 D 的 `frontend/*`，以及任何既有测试。

## 实现了什么

### `backend/studio/casting_prompts.py`

函数签名与 §8.2 逐字一致（含仅关键字参数与默认值）：`style_inputs(*, synopsis, bible, episodes, language)`、`build_sheet_prompt(*, kind, name, appearance, description, locked_features, style, extra_prompt="", reference_notes=())`、`reference_note(kind, derived)`。

- `style_inputs`：只输出摘要。梗概按已知概括字段（`logline / synopsis / genre / tone / themes / theme / core_conflict / main_threads / arc_summaries`）取值并逐字段截断到 400 字；`bible` 按 `kind` 分到 `characters / locations / props`，人物取 `name / role / appearance（缺则 description）/ needs_author`，场景与道具取 `name / description`；**刻意不带 `excerpt`（原文逐字摘录）、`aliases_json`、`episodes_json` 等字段**，未知 kind 的条目直接丢弃；`episodes` 输出 `episode_count`、`total_seconds`（`est_seconds` 之和，容错 None/非数字）与每集 `{no, title, summary}`（摘要取 `change → hook → summary`，截断 200 字，最多 24 集）；`language` 映射为「中文 / 英文」。返回键固定为 `language / synopsis / characters / locations / props / episode_count / total_seconds / episodes`。
- `build_sheet_prompt`：按 §10.1 拼接 `定妆{人物|场景|道具}：{name}` → 版式（人物「三视图：正面、侧面、背面全身」；场景「同一地点的三个机位：全景、中景、细节」；道具「三视图：正面、侧面、背面，另加一处细节特写」＋「横向等距排开、视图之间留白、不加任何文字标签、纯白干净背景、边缘清晰便于抠像、16:9 横幅」）→ 外形／说明 → `必须保持（锁定特征）：…` → 写实度与负向（`photoreal` 加皮肤质感并「不要动漫、不要插画」；`anime`「不要照片质感、不要写实」；`3d`「不要照片、不要二维线稿」）→ 原创声明（人物「原创角色，原创设计，不模仿任何已知作品、品牌或真人」）→ 风格段（`visual_style / palette / lighting / camera`，逐项非空才拼）→ 参考图说明（`参考图说明（共 N 张，按上传顺序逐张取用）：` 后逐张编号）→ `补充要求：{extra_prompt}` **固定最后**。总长 ≤ `PROMPT_LIMIT = 1800`：先裁 `extra_prompt` 的尾部、再裁 `description` 的尾部，`locked_features` 与版式永不被裁。输入统一压缩为单行、不额外预截断（长度完全由 1800 上限与裁剪优先级决定）。
- `reference_note`：人物派生自已选定版本 → 「由已选定版本派生，只取身份、脸型、发型、体型，不取姿势与背景」；人物非派生 → 「只取身份、脸型、发型、体型，不取背景、文字与无关元素」；场景 → 「只取建筑结构、陈设、朝向，不取人物与文字标签」；道具 → 「只取结构、材质、颜色，不取场景与文字」；`derived=True` 的其他类型加前缀「由已选定版本派生，」。

### `backend/studio/prompts/style_proposals.md`

末尾追加一段「项目风格」：提案需贴合开工确认的语言与画幅，并直接服务定妆（人物三视图、场景三机位、道具三视图+细节特写、纯白背景无文字），要求 `visual_style / palette / lighting / camera` 具体到材质、色彩、光线来源与色温、景别与运镜，能逐项写进出图提示词。

### 文档与环境变量

- `backend/.env.example` 追加 WO3d 小节：`FIONA_STUDIO_MAX_INFLIGHT_IMAGE=3`、`FIONA_STUDIO_MAX_INFLIGHT_TTS=2`（1–10，非法值回落默认并只告警一次）、`FIONA_STUDIO_PRICE_SEEDREAM_CNY=0.30`（元/张，待核实；Seedream 响应不含计费字段，按此价预留与结算）、`FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS=2.0`（元/万字符，待核实；按字符数预留与结算，最低 0.01 元）、系统 `ffmpeg` 与 `edge-tts==7.3.1` 说明。
- `CLAUDE.md` / `README.md` / `docs/ARCHITECTURE.md` 用各自既有文风（散文段落，不用表格与列表；ARCHITECTURE 用 `### <期号>` 子节）补第 3d 期内容：开工确认 → 风格提案 → G1 定妆出图 → 声线试听定档、门禁 409 与零付费调用、Seedream 2560×1440 三视图纯白背景、中文 CosyVoice / 英文 edge-tts、三类特效 + 两遍响度标准化 + 48kHz 单声道 WAV、ffmpeg 缺失抛 `RuntimeError("ffmpeg unavailable")`、新环境变量与单价、唯一新依赖 `edge-tts==7.3.1`。更新前先全库检索：4 个文件原本零处 WO3d / 定妆 / 声线 / casting 文字（`.env.example` 里只有聊天生图工具的 `SEEDREAM_IMAGE_MODEL`，与定妆无关），故全部为新增，不存在覆盖或重复。

## 与规格逐项对应

| 规格 | 落点 | 状态 |
|---|---|---|
| §8.2 函数名与参数逐字一致 | `casting_prompts.py` 三个函数签名 | 完成 |
| §4 风格输入：梗概、人物/场景/道具名与外形摘要、集数与总时长、语言 | `style_inputs` | 完成 |
| §2「style_inputs 只放摘要、绝不放原文全文」 | 只取已知字段并截断；不带 `excerpt` | 完成（有测试断言哨兵长文与 `excerpt` 不出现） |
| §10.1 三类版式文字 | `_LAYOUTS` + `_FRAME` | 完成 |
| §10.1 三种写实度负向 | `_REALISM` | 完成 |
| §10.1 原创声明 | `_ORIGINAL` | 完成 |
| §10.1 锁定特征原样列为「必须保持」 | `必须保持（锁定特征）：` | 完成 |
| §10.1 `appearance` / `description` 作主体描述、`extra_prompt` 附最后 | 行序 | 完成 |
| §10.1 参考图说明逐张列出（`reference_note`） | `reference_notes` 编号行 | 完成 |
| §10.1 风格段拼入 | `_style_line` | 完成 |
| §10.1 总长 ≤1800，超长先裁 `extra_prompt`、再裁 `description`，保证锁定特征与版式完整 | `build_sheet_prompt` 裁剪循环 | 完成（有测试） |
| §9 只改块 C 文件 | 见改动表 | 完成 |
| 文档：第 3d 期内容 + 新环境变量 + 新依赖 + ffmpeg | 四个文档 | 完成 |
| §11.2 块 C 必测项（版式、负向、锁定特征、长度与裁剪、参考图说明、`style_inputs` 摘要-only） | `test_studio_casting_prompts.py` | 完成 |

## 未完成 / 需确认

1. **`style_inputs` 的返回结构是新增的隐式约定**。规格只给了签名、没给返回字段，块 A 需要在风格提案任务里消费它。我的实现见上（`language / synopsis / characters / locations / props / episode_count / total_seconds / episodes`，`synopsis` 的键是中文标签）。若块 A 期望别的键名或形状，请告知，我按需调整（只改我的文件）。
2. **`realism` / `kind` 非法值抛 `ValueError`**。两者都应由路由层先校验（`kind` 来自条目、`realism` 来自风格选择）；`style` 缺 `realism` 时按 `photoreal` 处理。若上游可能传入枚举外的写实度，需要改成回落而不是抛错，请确认。
3. **`extra_prompt` 在提示词层不做 500 字预截断**，只受 1800 总长裁剪；500 字上限由 `POST /sheets/quote` 的请求模型校验。规格未要求提示词层再截一次。
4. **WO3c 在 4 个文档里完全缺失**（标题仍为 `## 短片工作室 WO1–WO3b` / `（WO1–WO3b）`，且 WO3b 段落还写着「本期不做自动拆解、分集」）。我只追加、没有改标题，以免声称已覆盖 WO3c；是否补写 WO3c 或把标题改成 `WO1–WO3d`，请主控决定（都属于块 C 的文件范围）。
5. **两个单价均为「待核实」**（`FIONA_STUDIO_PRICE_SEEDREAM_CNY` 默认 0.30 元/张、`FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS` 默认 2.0 元/万字符），与规格一致；文档与 `.env.example` 都标注了这一点，合并后需用真实账单核实。
6. **文档描述的是目标行为**。写文档时块 A 的 `config.py` 还没有 `MAX_INFLIGHT_IMAGE/TTS` 与两个单价变量（并行执行中），这四个文档按规格写 WO3d 的既定行为，不随实现快照。
7. **未跑全量测试**：其他块正在同一工作区并行实现（`storage.py`、`requirements.txt`、`providers/*`、`frontend/*` 正在被改动），全量结果不稳定也不代表块 C；只跑了本块目标测试与 4 个读 `.env.example` 的文档测试。真实 Key 付费冒烟由主控合并后单独执行。
