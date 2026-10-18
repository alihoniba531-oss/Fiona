# D4 报告：反例卡 + 出处 + 文档

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 基线：`4b45346`
- 范围：`02-spec.md` §10 的 D4 行；内容契约见 §3.5、§3.6，来源与授权见 §11。

## 1. 修改了哪些文件

**新建反例卡（21 张，均在 `backend/studio/director_kb/cards/negative/`）**

- `negative-looking-at-camera.yaml`
- `negative-bare-camera-term.yaml`
- `negative-voiceover-mouth-moves.yaml`
- `negative-photoreal-face-seedance.yaml`
- `negative-fight-sub-four-second-generation.yaml`
- `negative-nonfixed-structure-material.yaml`
- `negative-orbit-invents-detail.yaml`
- `negative-push-tilt-reveals-face.yaml`
- `negative-move-down-material-drift.yaml`
- `negative-giant-offscreen-camera-move.yaml`
- `negative-ip-lookalike.yaml`
- `negative-grimy-realism.yaml`
- `negative-transient-look-in-sheet.yaml`
- `negative-too-many-actions.yaml`
- `negative-crowded-frame.yaml`
- `negative-no-establishing-shot.yaml`
- `negative-unwritten-detail-seedream.yaml`
- `negative-focal-without-purpose.yaml`
- `negative-axis-jump.yaml`
- `negative-prop-continuity-break.yaml`
- `negative-unverified-model-syntax.yaml`

**修改既有文件**

- `THIRD_PARTY_NOTICES.md`：在 NASA 条目之后追加「Director knowledge base references」，补 ai-visual-director（MIT）、prop-asset（Apache-2.0）、CameraBench（CC BY 4.0）、seedance-shot-design（MIT-0）四项；既有条目未删除。
- `CLAUDE.md`：短片工作室标题改为 WO1–WO3e，末尾补 2 段 WO3e 说明。
- `README.md`：短片工作室标题改为 WO1–WO3e，末尾补 3 段 WO3e 说明。
- `docs/ARCHITECTURE.md`：在 WO3d 之后新增「### WO3e 导演知识库」小节。

**本轮返修（集成修正，2026-10-18）**

只改以下 5 张卡的必要行；其余 16 张 negative 卡、两张已确认样卡、来源文件、测试与白名单外文件均未动。

- `negative-bare-camera-term.yaml`：只改 `evidence`，把英文 Skill 名改为「Seedance 失败诊断」。
- `negative-crowded-frame.yaml`：只改 `evidence`，把英文 Skill 名改为「Seedance 失败诊断」。
- `negative-too-many-actions.yaml`：只改 `evidence`，把英文 Skill 名改为「Seedance 失败诊断」。
- `negative-voiceover-mouth-moves.yaml`：只改 `evidence`，把英文 Skill 名改为「Seedance 场景规范」。
- `negative-photoreal-face-seedance.yaml`：只改 `right`，改写肖像闸绕法；语义仍是「优先改走万相；非用 Seedance 不可时，用逆光剪影、高处俯拍、头发挡脸、远景或背影」。

5 张卡的 `sources` 全部原样保留（4 张 evidence 卡的具体来源名称与 ref 也都在），未删除任何来源。

**报告**

- `docs/tasks/2026-10-18-studio-wo3e-director-kb/03-report-D4.md`：本轮按返修要求在第 1、2、3、4、5 节追加修正记录。

**未改动**

- 两张样卡 `scene-dialogue.yaml`、`scene-fight.yaml` 未动；sha256 与派单前一致：
  - dialogue：`d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d`
  - fight：`72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129`
- 白名单外的代码、测试、前端与数据文件均未改。

## 2. 实现了哪些功能

- 21 个反例 id 全部按 §3.6 落盘，文件名等于 id，`type: negative`，并带 §3.1 的共同字段（`id/type/title/summary/tags/sources/version`）与 §3.5 的 `wrong/right/why/evidence`；可选 `applies_to` 的 `scene_type` 只使用 §4 的 17 类内容卡值，2 张 Seedance 相关卡另加 `model: [seedance-2.5]`；可选 `lint_pattern` 均为 Python `re` 可编译的正则。
- 出处逐卡写在 `evidence`：P01 第 1/2/3 次返工、P01 巨物实测、肖像闸、版权拦截、写实与定妆规则来自 `00-house-rules.md`；画外音口型、英文运镜术语、多动作、同框与道具连戏等来自 §11 列出的 seedance-shot-design、ai-visual-director、prop-asset、分集拆镜与声画时间轴规范。没有编造事故或作者未确认的实测。
- 7 张卡带数据驱动 `lint_pattern`：画外音跟嘴、写实脏乱、IP 造型照搬、定妆临时状态、Seedream 细节留给模型、道具只写「保持上一镜一致」、未核实模型语法。其余反例由 §6 的内置规则、动作计数、时长检查、敏感机位检查或模型卡规则覆盖；未给「看镜头」加重复正则，避免与内置规则 2 重复告警。
- `THIRD_PARTY_NOTICES.md` 四项授权按现有体例写成英文条目，许可证名称分别为 MIT、Apache-2.0、CC BY 4.0、MIT-0；CameraBench 注明只使用运镜标签、不转载数据集视频或标注。
- 三处文档补充了：本地 YAML 卡片、19 场景类型（17 内容卡 + 2 位置卡）、按标签取材料、知识库检查、`studio_exemplars` 与 `studio_stats` 2 张表、7 个页签、试拆对比、`review_provider` 默认 `qwen` 且可 `off`、只开放作者、运行时不访问外部资源，并明确正式接入逐集拆镜是 WO4。
- 本轮返修按主控 §13 失败输出处理 5 处原文重合：4 处 `evidence` 的英文 Skill 名会与来源文件里的自身引用形成 20 字重合，换成简短中文出处；`negative-photoreal-face-seedance` 的 `right` 行换一种句式描述肖像闸绕法，保留原意与「先验首帧」，不再与 `00-house-rules.md` 或两张样卡连续 20 字相同。
- 返修只动必要行，未改 `wrong/why/applies_to/lint_pattern`，未删除或改写 `sources`，未触碰两张样卡。

## 3. 与 §10、§12 的逐项对应

| 要求 | 本次实现 |
|---|---|
| §10 D4：21 张反例必须有 | 21 张全部存在，另无多余反例；`schema.missing_required_ids` 的 negative 部分为 0 |
| §10 D4：补 4 项授权 | `THIRD_PARTY_NOTICES.md` 四项齐全，既有条目保留 |
| §10 D4：更新 3 份文档的短片工作室段 | `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md` 均只做本期必要追加，未重写全文 |
| §3.5 字段 | 每张卡都有 `wrong/right/why/evidence`；`applies_to` 为合法子集；`lint_pattern` 可编译 |
| §3.6 id 总表 | 21 个 id 与文件名一一对应，kebab-case 英文 |
| §11 来源与授权 | `sources` 至少 2 条；只使用 §11 列出的本地来源与作者规则；未使用商业剧照库 |
| §11 连续 20 字重合 | 本轮修正后 21 张 negative 卡对 56 个来源文件按 raw / collapse / norm 三种口径均 0 命中；对两张已确认样卡也 0 命中 |
| §12.2 全库 id 与引用 | 全库 58 张卡加载成功，`missing_required_ids` 为 0，`validate_references` 通过；19 张场景卡、21 张反例卡 |
| §12.4 数据驱动规则 | 7 个反例 `lint_pattern` 均有用例命中；2 个安全写法不误报 |
| 不声称已接进逐集拆镜 | 3 份文档都写明「正式接入逐集拆镜在 WO4」或「留到 WO4」 |

## 4. 测试结果

第一轮没有运行完整 pytest；本轮按返修要求运行了 `tests/test_studio_kb_core.py`，结果见本节末尾。第一轮自查脚本放在 `$TMPDIR`，不入库：

- schema 检查：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/d4_schema_check.py`
  - 检查负例卡片数：21
  - schema 通过：21
  - schema 失败：0
  - 警告：0
  - 覆盖：共同字段、类型字段、id 前缀、文件名 = id、summary ≤80 字、tags 小写、license 枚举、`applies_to` 场景值、`lint_pattern` 可编译、21 个必需 id 齐全、场景卡对 negative id 的引用存在、UTF-8 无 BOM、无 tab。
- A 块 `schema.py` 落盘后复跑：
  - `schema.validate_card(..., filename=...)`：21/21 通过，0 失败。
  - `loader.load_library()`：58 张卡全部加载，`schema.missing_required_ids` 为 0，`schema.validate_references` 通过。
- 原文重合检查（第一轮，结论已作废，以本节末尾本轮复跑为准）：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/d4_overlap_check.py`
  - 比对来源文件：56 个（`00-house-rules.md` 1 个、ai-visual-director `knowledge/*.md` 32 个、seedance-shot-design `references/*.md` 16 个、prop-asset `NEGATIVE-CASE-BOOK.md` 1 个、shortfilm-pipeline `references/*.md` 6 个）。
  - 比对范围：21 张卡的全部文本字段；`sources` 列表整体排除，不计路径字符串。
  - 连续 20 字相同（纯中文模式）：0 命中。
  - 连续 20 字相同（去空白/标点、统一大小写模式）：0 命中。
  - 漏检原因：纯中文模式只取连续 CJK；去标点模式会把 `seedance-shot-design` 的连字符去掉（只剩 18 字），也会把肖像闸 `right` 行的空格与标点去掉，去掉后与 `00-house-rules.md` 的最长公共片段只有 18 字，两种口径都刚好达不到 20 字。主控 §13 用原文/折叠空白口径复跑时命中 5 处。
  - 第一轮合计 0 命中，但该结论不代表通过。
- `lint_shots` 冒烟（使用 A 块实际 `lint.py`）：
  - 7 个反例 `lint_pattern` 各有 1 个命中用例：画外音跟嘴、脏乱写实、IP 照搬、定妆临时状态、Seedream 细节外推、道具模糊连戏、未核实时间戳。
  - 2 个安全写法（「不看镜头」「画外音嘴唇闭合不张嘴」）0 误报。
  - 「看向镜头」只命中内置 `looking-at-camera`，不再重复命中反例卡。
- `select_materials` 冒烟（使用 A 块实际 `retrieval.py`）：对话场景分别用 wan 与 seedance 各调用 2 次，2 次结果逐字相同；各取到 3 条反例，注入文本均不超过 8000 字。
- 样卡 sha256 复核通过（见第 1 节）。

**本轮返修复跑（2026-10-18）**

- 主控 §13 修正前命中 5 处：
  - `negative-bare-camera-term.yaml` / `evidence`：英文 Skill 名。
  - `negative-crowded-frame.yaml` / `evidence`：英文 Skill 名。
  - `negative-too-many-actions.yaml` / `evidence`：英文 Skill 名。
  - `negative-voiceover-mouth-moves.yaml` / `evidence`：英文 Skill 名。
  - `negative-photoreal-face-seedance.yaml` / `right`：与 `00-house-rules.md` 的肖像闸绕法重合。
- schema 校验（A 块实际 `schema.py`）：21/21 通过，0 失败；21 张均可 `yaml.safe_load`，UTF-8 无 BOM、无 tab；本轮改动行数字均为阿拉伯数字。
- 原文重合复跑：`/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/d4_overlap_recheck.py`
  - 来源文件 56 个、negative 卡 21 张；排除 `sources`、`tags`、卡片引用 id；另与两张已确认样卡单独比对。
  - `raw`（原文）0 命中、`collapse`（折叠空白）0 命中、`norm`（NFKC + 去空白/标点 + casefold）0 命中。
  - 对两张已确认样卡 0 命中；合计 0 命中。
  - 补充口径（去空白但保留标点、只取连续 CJK）也为 0 命中；对两张样卡按五种口径复查仍为 0。
  - 阳性对照：用修正前的英文 Skill 名与肖像闸 `right` 行片段测试，`raw`/`collapse` 能稳定命中，确认脚本不是空跑。
- pytest：`cd backend && <py> -m pytest -q tests/test_studio_kb_core.py`
  - 32 passed、3 errors、0 failed、0 skipped。
  - 3 个 error 都在初始化测试库时由 `httpx` 解析环境变量 `NO_PROXY` 的 `[::1]` 触发 `Invalid port: ':1]'`，与卡片和 schema 无关，未改测试文件。
  - 把 `NO_PROXY`/`no_proxy` 清成 `localhost,127.0.0.1,::1,.local` 后复跑：35 passed、0 failed、0 skipped。
- 只改了 5 张卡的必要行；其余 16 张 negative 卡、两张样卡、来源文件、测试与白名单外文件未动（mtime 复核：只有这 5 张在返修时段更新）。

## 5. 未完成或需要人工确认

- 三处文档按 §8、§9 的契约描述；B/C 块如果最终调整了接口路径、页签数量或 `review_provider` 行为，需要以最终实现再校一次文档。
- `prop-asset` 本地副本没有上游仓库 URL，也没有独立 NOTICE 或版权人姓名；通知条目已如实写明这一点，作者可补上游地址。
- CameraBench 的署名信息取自同任务的历史 `SOURCES.md`（Hugging Face `syCen/CameraBench`、Lin et al.、NeurIPS 2025 Datasets and Benchmarks）；未联网复核论文作者全名。
- 21 张卡的 `evidence` 是对作者规则与来源的转写，P01 的「第 1/2/3 次返工」编号沿用 `00-house-rules.md` 的叙述顺序；如作者有更细的镜号或日期，可再补。
- 只有 7 张卡带 `lint_pattern`。动作数、生成时长、敏感机位、肖像闸等由内置规则或模型卡负责，符合 §6 的分工；如果后续希望反例卡也各自带规则，可再补，但需避免重复告警。
- 本轮只运行了 `tests/test_studio_kb_core.py`；完整 `pytest -q tests/ -k studio`、前端 tsc/lint 与真实导演调用仍未运行，属于主控门禁与阶段三验收。
- 本报告第一轮的「原文重合 0 命中」已作废，以第 4 节本轮复跑的 0 命中为准；主控需用修正后的 21 张卡复跑 §13 原文重合检查。本机 pytest 的 3 个 error 来自环境变量 `NO_PROXY` 的 `[::1]`，清掉后为 35 passed，建议主控在干净环境再确认一次。
