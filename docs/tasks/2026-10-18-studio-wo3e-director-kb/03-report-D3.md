# D3 报告：内容·语法 + 模型

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 基线：`4b45346`
- 范围：`02-spec.md` §3.2、§3.4、§3.6、§11；写法以 `scene-dialogue.yaml`、`scene-fight.yaml` 两张定稿样卡为样板。

## 1. 修改了哪些文件

**新建语法卡（13 张，`backend/studio/director_kb/cards/grammar/`）**

- `grammar-shot-size.yaml`
- `grammar-camera-angle.yaml`
- `grammar-camera-movement.yaml`
- `grammar-lens-focal.yaml`
- `grammar-transition.yaml`
- `grammar-axis-eyeline.yaml`
- `grammar-continuity.yaml`
- `grammar-over-shoulder.yaml`
- `grammar-shot-reverse-shot.yaml`
- `grammar-insert-closeup.yaml`
- `grammar-action-match.yaml`
- `grammar-establishing-shot.yaml`
- `grammar-backlight-silhouette.yaml`

**新建模型卡（5 张，`backend/studio/director_kb/cards/model/`）**

- `model-wan-3-photoreal.yaml`
- `model-wan-3-anime.yaml`
- `model-seedance-2-5-photoreal.yaml`
- `model-seedance-2-5-anime.yaml`
- `model-seedream-5.yaml`

**新建报告**

- `docs/tasks/2026-10-18-studio-wo3e-director-kb/03-report-D3.md`

**未改动**

- 两张定稿样卡未动，sha256 与派单前一致：
  - dialogue：`d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d`
  - fight：`72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129`
- 白名单外的代码、测试、前端与数据文件均未改、未新建；完整 pytest 按要求未跑。

## 2. 实现了哪些功能

### 2.1 语法卡

13 张卡都带 §3.2 的字段：

- `definition`：定义这个语法单位在画面里到底控制什么。
- `narrative_use`：写叙事作用、使用条件与常见误用。
- `safe_prompt`：统一写成「中文术语（白话轨迹 / 范围 / 速度 / 起止）」，例如「推轨（镜头沿地面平稳向前靠近，从中景到中近景，约 3 秒）」。
- `avoid`：每张 4–6 条，覆盖裸写英文术语、无方向或无起止的运动、敏感镜用运动机位、把景别与机位揉成 1 个词、只写「保持上一镜一致」等。
- `related`：只引用 §3.6 的 grammar id，共 13 个 id 内部互引；没有引用 scene / model / negative。

`grammar-shot-size` 用 `entries` 列 9 级景别：大远景、远景、全景、中远景、中景、中近景、近景、特写、大特写。`grammar-camera-movement` 用 `entries` 列 8 类运镜：推、拉、摇、移、跟、升降、环绕、手持。`grammar-camera-angle` 也用 `entries` 列平视、俯拍、仰拍、荷兰角、顶拍 5 项，方便检索与渲染时逐项取用。

内容与作者规则的对应：

- 结构、材质、人脸敏感镜一律固定机位；环绕和组合运镜只放在非敏感镜头里作为可选项。
- 人物视线落在对手、物件或出口，不写「朝向镜头 / 看向镜头」；口型镜只要求脸大致可见。
- 写实人物走 Seedance 的中景、近景、特写，提示过肖像闸风险，并给出逆光剪影、约 65° 俯拍加头发遮脸、远景、背影等规避路径。
- 生成时长不足 4 秒的镜头先按至少 4 秒生成再裁切，这一条写进了模型卡事实与 Seedance 提示词约束。
- 焦段有叙事理由才写，不把毫米数当品质词。

### 2.2 模型卡

5 张卡都带 §3.4 的字段：

- `model`：`wan-3.0`、`seedance-2.5`、`seedream-5.0`。
- `style`：`photoreal`、`anime`、`any`。
- `facts`：每条结尾注明「实测」或「官方」；价格类写成「官方参考价，待作者核实」或「实测参考价」。
- `portrait_gate`：Seedance 写实卡写清拒单条件、是否计费和 5 条绕法；Seedance 动漫卡、万相卡、Seedream 卡写「无」，同时说明平台内容审核仍可能拦截，不把「无」当豁免。
- `copyright`：Seedance 两卡写作者实测的「生成完才拦、不计费、白等约 6 分钟」，以及对知名 IP 的美术差异化与 1/8 画高小剪影兜底；万相与 Seedream 的来源没有拦截时点，明确写「待作者实测核实」。
- `motion_risks`：把 P01 的 4 次实测事故（环绕补结构、推近后上摇露正脸、下移材质漂移、跟拍/拉远编出画外巨物）写进万相与 Seedance 卡，并补多主体串位、长提示词忽略运镜等风险。
- `prompt_syntax`：写时间戳、素材令牌、音频括号、首帧模式参数、固定机位写法等可执行要点。
- `max_characters`：5 张卡统一为 `2`，对应作者「同框不超过 2 人」的规则；官方多主体参考稳定性数字写在 `facts` 里，避免把知识库策略误当成厂商上限。
- `lint_rules`：每张 4–5 条，`when` 只用 `realism`、`shot_size_in`、`face_visible`，其余用 `pattern`；`level` 只取 `warn` / `info`，正则全部可被 Python `re` 编译。

模型事实的来源边界：

- 万相：2–30 秒或 -1 自动、480P/720P/1080P 大写枚举、480P 竖屏 480×852 / 30fps、首帧原图 20MB / 240–8000 / 宽高比 8、`audio` 默认 true、`prompt_extend` 默认 true、在途上限 3 条、无 `negative_prompt` / `return_last_frame` / `camera_fixed`。
- Seedance 2.5：标准 4–30 秒、超长 30–180 秒、延长规则、官方手册 480p/720p 与 MCP 实测 1080p、24fps、图片 30 张 / 视频 10 段 / 音频 10 段、无 12 文件混合上限、参考稳定性 1–8 / 1–5、MCP 2000 字符、首帧模式 `camera_fixed` 返回 HTTP 400。
- Seedream 5.0：pro / flash 两档、prompt 1500 字符、参考图 1–10 张、显式尺寸总像素 921,600–4,624,220 与宽高比 1/16–16、2864×1611 与 1611×2864、`background` 透明只限图生图、`output_format` png / jpeg、出图依赖提示词。
- **Seedance 2.0 的时间戳**：`prompt_syntax` 明确写「2.0 与 2.5 写法相反（作者规则）；2.0 的具体格式在 §11 来源中查不到，待作者实测核实，不能按 2.5 的区间格式反推」。2.5 自身只记录来源能查到的有序区间写法：`[00.0-05.0s]`、`0-5秒`、`0:30-0:45`，以及官方示例的帧锚点。
- 没有把厂商手册没写的 1080p 说成「官方支持」：卡片把「官方手册 480p/720p」与「MCP 通道实测 1080p」分成两条事实。

### 2.3 标签与数据驱动检查

- `tags` 同时保留连字符与下划线两种敏感词写法（如 `face-closeup` / `face_closeup`、`giant-offscreen` / `giant_offscreen`），既方便页面筛选，也能命中 `SceneTags.sensitive` 的合法值。
- `lint_rules` 覆盖：Seedance 写实肖像闸、`camera_fixed` 误发、Seedance 2.0 时间戳未核实、提示词超长、同框超 2 人；万相 `prompt_extend:true`、负向提示词、`camera_fixed`、2–3 秒短生成、写实近景/特写；Seedream 运镜词、空泛画质词、纯文生图透明背景、提示词超长、群像。
- 用 A 块实际 `lint.py` 做过冒烟：`seedance-portrait-photoreal`、`seedance-camera-fixed`、`seedance-crowd`、`wan-prompt-extend`、`seedream-motion-words`、`seedream-empty-quality` 均能在合成镜头上触发，`level` 只有 `warn` / `info`。

## 3. 与 §10、§12 的逐项对应

| 要求 | 本次实现 |
|---|---|
| §10 D3：grammar 13 张、model 5 张 | 18 张全部落盘，文件名 = id，id 与 §3.6 一字不差 |
| §3.2 grammar 字段 | `definition` / `narrative_use` / `safe_prompt` / `avoid` / `related` 齐全；shot-size 9 级、camera-movement 8 类、camera-angle 5 项用 `entries` 分条 |
| §3.4 model 字段 | `model` / `style` / `facts` / `portrait_gate` / `copyright` / `motion_risks` / `prompt_syntax` / `max_characters` / `lint_rules` 齐全；无 `example` |
| §3.1 共同字段与授权 | 每张卡 `sources` 至少 1 条；license 只用 `own` / `MIT` / `MIT-0` / `Apache-2.0`；无 BOM、无 tab，UTF-8 YAML |
| §3.6 引用 | `related` 只引用 13 个 grammar id；没有引用块外 id，也没有引用不存在的卡 |
| §11 来源 | 只读 00-house-rules、ai-visual-director `knowledge/*.md`、seedance-shot-design `references/*.md`、prop-asset `NEGATIVE-CASE-BOOK.md`、shortfilm-pipeline `references/*.md`；没有使用商业剧照库，没有复制成段原文 |
| §12.2 全库 | A 块 `loader.load_library()` 加载 58 张卡成功：grammar 13、scene 19、model 5、negative 21；`missing_required_ids` 为 0 |
| §12.4 数据驱动规则 | 模型卡 `lint_rules` 的 `when` 与 `pattern` 都能被 A 块 `lint_shots` 执行；`when` 字段都在 A 的 `_LINT_WHEN_FIELDS` 内 |
| 数字写法 | 卡片正文中的数量、时长、角度用阿拉伯数字（2 人、3 个动作、4 秒、65°、15°、1/8 等）；「同一」「一致」「一律」等固定词保留 |

## 4. 测试结果

按 §10 D3 的自查要求，在 `$TMPDIR` 写了两个临时脚本，均不入库：

- schema / 格式检查：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/validate_d3.py`
- 原文重合检查：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/overlap_d3.py`

运行命令：

```bash
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python <脚本路径>
```

结果：

```text
本块卡片：13 grammar + 5 model = 18
schema 通过：18
schema 失败：0
原文重合：18 张卡，56 个来源文件，连续 20 字，hits = 0
```

- **schema 检查**：18/18 通过，0 失败；覆盖共同字段、类型字段、id 前缀与文件名、summary ≤80 字、tags 格式、license 枚举、grammar 的 `avoid` / `entries` / `related`、model 的 `facts` 出处标记 / `max_characters` / `lint_rules` 结构 / `when` 键名 / 正则可编译、UTF-8 无 BOM、无 tab。
- **A 块实际 schema 复核**：`loader.load_cards_of_type("grammar")` 13 张、`load_cards_of_type("model")` 5 张全部通过；A 块 `load_library()` 全库 58 张加载成功，`missing_required_ids` 为 0，`validate_references` 通过。
- **原文重合检查**：18 张卡的全部正文与 §11 列出的 56 个来源文件逐一比对；`sources` 列表整体排除，路径字符串不参与比对。原始文本（折叠空白）与去空白/标点两种模式都查连续 20 字，合计 0 命中。
- **格式检查**：18 张卡均为 UTF-8、无 BOM、无 tab，`yaml.safe_load` 与 A 块 `_UniqueKeyLoader` 均能读取；没有重复键。
- **A 块测试子集（非完整 pytest）**：
  - `tests/test_studio_kb_core.py -k "all_cards_validate or model_card_data_driven or select_materials_is_deterministic or lint_result_shape"`：4 passed，0 failed。
  - `tests/test_studio_kb_core.py -k "default_budget_stays_within_8000 or position_and_model_selection"`：18 passed，0 failed。
  - 共 22 passed，覆盖 58 张全库卡片、模型卡数据驱动规则、检索确定性与 17 类场景预算。
- **lint 冒烟**：用合成镜头分别验证 Seedance 写实肖像闸、`camera_fixed`、同框、万相 `prompt_extend`、Seedream 运镜与空泛画质词规则；命中 id 与 level 符合预期。
- **未跑完整 pytest**：按要求没有运行 `pytest tests/ -k studio`，也没有跑前端 tsc / lint。

## 5. 未完成或需要人工确认的地方

- **Seedance 2.0 时间戳格式**：§11 来源没有给出 2.0 的具体写法，卡片只能写「与 2.5 相反，待作者实测核实」，没有把 2.5 的区间格式反推给 2.0。需要作者用真实 2.0 通道跑 1 条对照。
- **万相版权拦截时点**：§11 来源只记录了 Seedance 的「生成完才拦、约 6 分钟」，万相卡按「待作者实测核实」处理。需要作者在真实万相任务中确认是否有同类拦截及等待时长。
- **价格与通道事实**：万相 0.3 / 0.6 / 1.2 元/秒、Seedance 720p 约 2–2.6 元/秒与 1080p 约 3.4 元/秒、Seedream pro 0.6 / flash 0.12 元/张均来自作者流水线文档的参考价，已标注「官方参考价 / 实测参考价，待作者核实」，不是实时账单。
- **`max_characters: 2`**：这是知识库按作者「同框不超过 2 人」规则设的策略值，不是厂商上限；Seedance 官方多主体参考的稳定性数字（图像 1–8 个较稳）已写在 `facts`，两者不冲突。
- **Seedream 的 lint 规则**：A 块 `lint_shots` 当前按 `video_model` 取 `wan` / `seedance` 家族，Seedream 卡不会被常规视频分镜检查触发；其规则已用 `video_model="seedream"` 直接调用 `lint_shots` 冒烟通过，留给后续出图提示词检查或试拆扩展使用。
- **未做真实生成验证**：肖像闸、版权拦截、提示词字符上限、1080p 可用性与裁切效果仍需作者在真实调用中确认；本期只做本地静态卡片与 A 块加载 / 检索 / lint 的离线验证。
