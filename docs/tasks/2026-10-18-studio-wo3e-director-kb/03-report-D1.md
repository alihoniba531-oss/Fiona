# 块 D1 报告：内容·场景模板 上

工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
基线：`4b45346`
范围：§3、§4、§11，并以 `scene-dialogue.yaml`、`scene-fight.yaml` 两张定稿样卡为写法样板。

## 1. 修改了哪些文件

新建 8 张场景内容卡（均在 `backend/studio/director_kb/cards/scene/`）：

- `scene-confrontation.yaml`：争执对峙
- `scene-chase.yaml`：追逐
- `scene-reveal.yaml`：悬疑揭示
- `scene-monologue.yaml`：情感独白 / 内心戏
- `scene-flashback.yaml`：回忆闪回
- `scene-ensemble.yaml`：群戏
- `scene-montage.yaml`：过场蒙太奇
- `scene-investigation.yaml`：调查 / 搜索

文档追加：

- `docs/tasks/2026-10-18-studio-wo3e-director-kb/01-scene-list.md`：只在文件末尾追加 `### 19. investigation 调查 / 搜索（新增）` 一节，含一句话定义、识别信号、与 `reveal` / `process-closeup` / `montage` / `twist` 的相邻区分。既有 18 节和「建议增删」一字未改，文件从 155 行变为 163 行。

本报告：

- `docs/tasks/2026-10-18-studio-wo3e-director-kb/03-report-D1.md`

两张样卡未改动，sha256 与派单给定值一致：

```text
dialogue d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d
fight    72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129
```

白名单外文件未改、未新建；完整 pytest 按要求未跑。

## 2. 实现了哪些功能

8 张卡全部按 §3.3 的 scene 字段和样卡详略写成，每张包含：

- `id`、`type`、`title`、`summary`（均 ≤80 字）、`tags`、`sources`、`version`、`scene_type`。
- `signals`：可判定的剧本识别信号。
- `beats`：5 个节拍（§3.3 要求 3–6 个）。
- `coverage`：6 步推荐覆盖，每步写清景别、机位和目的。
- `pacing`：`fast` / `mid` / `slow` 三档，含 `shots_per_min` 与 `shot_seconds`，并与镜长互相校验。
- `camera`、`sound`：按类型写轴线、机位、景别、声音层次和剪辑点。
- `ai_risks`：4–6 条 `risk` / `fallback`，覆盖肖像闸、结构材质漂移、视线翻面、动作过载、写实变脏、版权拦截等。
- `example`：7 镜原创示例（要求 6–10 镜），每镜含景别、机位、动作和裁切时长，全文 ≤600 字。
- `related_grammar`、`related_negative`：只引用 §3.6 定义的 id，且全部真实存在。
- 内容卡均不带 `position`。

与作者规则的对应：

- 每张卡都写明人物不看镜头，视线落在对手、证据、物件或路线上。
- 证据、手部、器械、齿轮、档案等结构 / 材质 / 人脸敏感镜一律固定机位。
- 运镜只写中文术语并加白话说明（如「轻推轨（镜头沿地面缓慢靠近）」「拉焦转移（焦点从前景移到证据）」），没有裸写英文运镜术语。
- 每张卡都写明每条生成至少 4 秒；短镜通过一条生成内预排动作点再裁切。
- 每张卡都写明写实人物保持干净、有精气神，瑕疵最多 1 项；雨夜、档案灰尘、修表油污只留在道具和环境。
- 每张卡都写明 Seedance 写实肖像闸的规避方式：侧后、过肩、逆光剪影、头发遮脸、约 65° 俯拍、远景或背影；需要清楚露脸时改走万相。
- 版权拦截按 00-house-rules 处理：`scene-reveal`、`scene-flashback`、`scene-ensemble` 写了 IP 近似风险，fallback 为先做美术差异化、不点名不复刻标志性服饰与道具组合、兜底压成不超过画高 1/8 的小剪影或改万相。
- 同一镜主体动作与摄影机动作合计不超过 3 个；群戏、追逐、调查都按 1 条主因果拆镜。
- 群戏按 `negative-crowded-frame` 的要求，每镜同框最多 2 人；用双人段、单人反应、空椅、画外人声和远景规模镜交代 3 人以上的场面，不把多人塞进 1 条生成。

`scene-investigation` 作为第 19 类、第 17 张内容卡落入 §4 清单，`01-scene-list.md` 的补充强调：

- 与 `reveal`：调查停在答案确认之前，揭示才交付答案并改变认知。
- 与 `process-closeup`：调查动作服务于判断和排除，工艺镜服务于完成 1 项操作。
- 与 `montage`：调查保留连续时空里的搜索、核对和停顿，蒙太奇用跳跃片段压缩过程。

## 3. 与 §10 和 §12 的逐项对应

- **§10 D1 行**：8 张指定 id 的卡已新建；`01-scene-list.md` 只追加 investigation 一节；两张样卡未动。
- **§12 第 2 条**：全库现有 58 张卡（grammar 13、scene 19、model 5、negative 21），scene 19 张覆盖 §4；恰有 2 张位置卡（`scene-opening-hook`、`scene-cliffhanger`）；`schema.missing_required_ids` 为 0，`unexpected_scene_ids` 为 0。
- **§3.1 / §3.3 字段**：8 张卡全部通过 `studio.director_kb.schema.validate_card`，字段、类型、id 前缀、summary 长度、tags 格式、license 白名单、beats 3–6、pacing 结构、example 长度均符合。
- **§3.6 引用**：8 张卡共引用 24 个唯一 id（12 个 grammar、12 个 negative），全部存在于已落盘的 13 张语法卡和 21 张反例卡中；`schema.validate_references` 在 53 张 scene + grammar + negative 卡上通过。引用没有块外 id。
- **§11 来源**：`sources` 只使用 00-house-rules、shortfilm-pipeline 02/05、ai-visual-director knowledge、seedance-shot-design references 这些 §11 允许的来源；license 只使用 own / MIT / MIT-0。示例全部为原创人物与场景，没有复用样卡或来源的成段原文。
- **§12 第 8 条**：本报告补齐五项。

## 4. 测试结果

按 §10 D1 的自查要求，在 `$TMPDIR` 写了两个临时脚本，均不入库：

- schema 检查：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/wo3e_d1_schema_check.py`
- 原文重合检查：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/wo3e_d1_overlap_check.py`

运行命令均为：

```bash
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python <脚本路径>
```

结果：

```text
全库：58 张卡，scene 19，缺 id 0
schema/card checks: 8/8 passed, 0 failed

overlap check: 8 cards, window=20, hits=0
```

- **schema 检查**：覆盖本块 8 张卡，8 passed / 0 failed / 0 skipped；同时用块 A 的 `load_library()` 复核全库 58 张卡成功。
- **原文重合检查**：覆盖本块 8 张卡正文，与 §11 列出的全部来源文件逐一比对连续 20 字相同，hits = 0；另外把两张定稿样卡作为对照，同样 hits = 0。`sources[].ref` 等元数据不参与比对。
- **格式检查**：8 张卡均为 UTF-8、无 BOM、无 tab，`yaml.safe_load` 与 `_UniqueKeyLoader` 均能读取；数字格式扫描未发现用中文数字表示数量、时长或角度。
- **未跑完整 pytest**：按派单要求没有运行 `pytest tests/ -k studio`；本块只需完成上述两项自查。

## 5. 未完成或需要人工确认的地方

- 无阻塞项。
- 示例与 `ai_risks` 是依据作者规则和 §11 来源写的规划，没有做真实视频生成验证；肖像闸、版权拦截和短镜裁切效果仍需作者在后续真实调用中确认。
- 按派单要求，`investigation` 一节追加在 `01-scene-list.md` 文件末尾（「建议增删」之后），因此它排在第 18 节之后、但不在「逐项定义」的连续编号段落内；既有行一字未改。若主控希望它紧接第 18 节，需要另行移动，但那会改动既有行，本块未做。
