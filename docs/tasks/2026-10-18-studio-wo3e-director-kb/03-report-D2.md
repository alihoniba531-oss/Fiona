# WO3e 块 D2 报告：场景模板下（7 张内容卡 + 2 张位置卡）与试拆样本

> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
> 范围：§3.3、§4、§11，以及本块派单的 9 张场景卡、`trial-scenes.md` 与本报告
> 全部离线完成：未联网、未读取 `.env`、未跑完整 pytest、未 `git commit`；白名单外文件一律未触碰。

## 1. 改了哪些文件

| 文件 | 动作 | 内容 |
|---|---|---|
| `backend/studio/director_kb/cards/scene/scene-establishing.yaml` | 新建 | 环境建立 / 定场 |
| `backend/studio/director_kb/cards/scene/scene-twist.yaml` | 新建 | 反转 |
| `backend/studio/director_kb/cards/scene/scene-intimacy.yaml` | 新建 | 告白 / 亲密 |
| `backend/studio/director_kb/cards/scene/scene-phone-call.yaml` | 新建 | 电话 / 远程对话 |
| `backend/studio/director_kb/cards/scene/scene-process-closeup.yaml` | 新建 | 工艺操作 / 动作特写（P01 类） |
| `backend/studio/director_kb/cards/scene/scene-explainer.yaml` | 新建 | 讲解科普（竖屏） |
| `backend/studio/director_kb/cards/scene/scene-scare.yaml` | 新建 | 惊吓 / 恐怖 |
| `backend/studio/director_kb/cards/scene/scene-opening-hook.yaml` | 新建 | 位置卡，`position: opening` |
| `backend/studio/director_kb/cards/scene/scene-cliffhanger.yaml` | 新建 | 位置卡，`position: ending` |
| `docs/tasks/2026-10-18-studio-wo3e-director-kb/trial-scenes.md` | 新建 | 对话、打斗、悬疑揭示 3 场原创试拆样本与建议标签 |
| `docs/tasks/2026-10-18-studio-wo3e-director-kb/03-report-D2.md` | 新建 | 本报告 |

未改动2 张样卡，也未改动 D1 / D3 / D4 / A / B / C 的文件。2 张样卡在本块开工前已存在，本块全程只读；当前 SHA-256 供主控与本块派单前的基线核对：

```text
d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d  scene-dialogue.yaml
72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129  scene-fight.yaml
```

## 2. 实现了什么

### 2.1 7 张内容卡

7 张卡都按 §3.3 的共同字段与场景字段写，字段顺序、详略和示例格式照2 张样卡：

- 每张卡 `summary` 在 36 字以内；`signals` 3–4 条；`beats` 5 条；`coverage` 5–6 步，每步都用「景别｜机位：目的」写清；`pacing` 三档齐全；`camera` 6–7 条；`sound` 4 条；`ai_risks` 4–5 条，每条都有 `risk` / `fallback`；`example` 7–8 镜，350–400 字。
- `scene_type` 与 §4 一致，`id` 为 `scene-<scene_type>`；7 张内容卡都没有 `position`。
- 场景语义按 `01-scene-list.md` 区分：定场没有独立冲突；反转必须重读旧事实；亲密靠距离与触碰；电话切开 2 个空间；工艺镜按步骤和物理约束推进；讲解以观众理解为回报；惊吓先给威胁、答案可以缺席。
- 作者规则落到卡里：人物视线落在对手、证据或器物上，不写看镜头；结构、材质、人脸、手部等敏感镜固定机位且机位与焦段不动；英文运镜术语只作中文白话的补充；每条生成至少 4 秒；写实人物干净、有精气神，瑕疵最多 1 项；写实露脸按 Seedance 肖像闸预先绕行；惊吓、开场、结尾卡写明版权拦截的美术差异化与剪影兜底。

### 2.2 2 张位置卡

- `scene-opening-hook`：`position: opening`；字段与内容卡相同，`beats` / `coverage` / `camera` 只写「在这个位置要额外做什么」——第 1 镜先给异常结果、前 3 个镜头抛出问题、第 2 镜才补空间、末尾切常态。开场若是打斗或追逐，卡里明确写「按内容卡的拍法执行」，不重复内容卡的分镜配方。
- `scene-cliffhanger`：`position: ending`；只写结果出现前的截断、未完成动作、最后 1 个威胁细节与切黑，不总结、不解释、不拉远；内容卡负责完成本场变化，位置卡只负责把后果留到下一段。
- 2 张位置卡的 `pacing` 三档、`sound`、`ai_risks`、`example` 都齐全；示例分别演示「先结果后空间」与「接触前切黑」。

### 2.3 试拆样本 `trial-scenes.md`

3 场均为原创，没有复制来源或样卡原文，也不写成卡片：

| 场 | 主类型 / 位置 | CJK 字数 | 非空白字符 | 建议标签 |
|---|---|---|---|---|
| 对话：借书卡 | dialogue / body | 347 | 437 | mid / 克制的试探 / 2 人 / photoreal / interior / face_closeup |
| 打斗：车库里的第 1 声 | fight / opening | 354 | 403 | fast / 急促的愤怒 / 2 人 / photoreal / interior / face_closeup,structure |
| 悬疑揭示：窗里的第 2 个人 | reveal / ending | 407 | 489 | slow / 恍然与不安 / 2 人 / photoreal / interior / face_closeup,material |

- 每场附 1 个 YAML 标签块，`scene_type`、`position`、`pace`、`emotion`、`cast_count`、`realism`、`setting`、`sensitive` 都取 §5 的合法值；`emotion` 均不超过 20 字。
- 每场另给建议 `target_seconds`（25 / 45 / 55，均在 10–120 内），供阶段三报价与拆镜直接使用。
- 打斗设为 `opening`、揭示设为 `ending`，是为了让阶段三同时跑到2 张位置卡；若作者希望 3 场都用 `body`，只改标签即可，正文不动。

### 2.4 来源与引用

- 每张卡 6–7 条 `sources`，只用 §11 列出的来源；授权取 `own` / `MIT` / `MIT-0`，没有 `vendor-doc` 断言，也没有引用商业剧照库。
- `related_grammar` / `related_negative` 只引用 §3.6 的 id；全库 58 张卡加载时引用校验通过。
- 卡片运行时不访问任何外部资源；本块的来源阅读只发生在起草阶段。

## 3. 约束核对

- 白名单：本块只新建 9 张场景卡、`trial-scenes.md` 与本报告，共 11 个文件；没有修改或新建白名单外文件。
- 样卡：`scene-dialogue.yaml`、`scene-fight.yaml` 全程只读，未写入；SHA-256 见 §1。
- 编码：11 个文件均为 UTF-8，无 BOM、无 tab；全部通过 `yaml.safe_load`（schema 脚本逐张读）。
- 字段：9 张卡 `summary` ≤ 80 字、`beats` 3–6、`coverage` 每步含景别 + 机位 + 目的、`pacing` 三档、`camera` 含「每条生成至少 4 秒」与固定机位约束、`ai_risks` 含 `risk` / `fallback`、`example` 6–10 镜且 ≤ 600 字。
- 位置：2 张位置卡恰好为 `opening` / `ending`；7 张内容卡没有 `position`。
- 数字：数量、时长、角度、镜数、人数一律用阿拉伯数字（如 2 人、3 个动作、4 秒、65°、45°）；脚本扫描未发现中文数字量词。
- 测试：按派单要求没有跑完整 pytest；没有联网、没有读取 `.env`、没有提交 git。

## 4. 自查结果

### 4.1 脚本

临时脚本放在 `$TMPDIR`，不入库：

```text
/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/d2_schema_check.py
/var/folders/8q/xrv13jp544l_3cc6cggv04r00000gn/T/d2_overlap_check.py
```

schema 脚本在 `backend/studio/director_kb/schema.py` 落盘后直接调用它的 `validate_card`，并额外检查：文件名与 id 一致、内容卡无 `position`、位置卡取值、`example` 镜数 6–10、`camera` 含 4 秒与固定约束、`coverage` 结构、引用 id 属于 §3.6、已落盘引用卡的 `type` 匹配。最后用 `studio.director_kb.loader.load_cards()` 加载全库，跑引用校验。

### 4.2 schema 结果

```text
检查卡片数: 9（内容卡 7，位置卡 2）
schema 通过: 9 / 失败: 0
总计: 0 个失败，0 个提醒
INFO  全库加载与引用校验通过，共 58 张
```

逐卡统计：

| 卡 | scene_type | position | summary 字 | beats | coverage | example 镜数 / 字数 | camera | ai_risks |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| `scene-establishing` | establishing | — | 36 | 5 | 5 | 7 / 353 | 6 | 4 |
| `scene-twist` | twist | — | 33 | 5 | 6 | 7 / 374 | 7 | 5 |
| `scene-intimacy` | intimacy | — | 33 | 5 | 5 | 7 / 379 | 6 | 5 |
| `scene-phone-call` | phone-call | — | 35 | 5 | 6 | 8 / 400 | 7 | 5 |
| `scene-process-closeup` | process-closeup | — | 32 | 5 | 6 | 7 / 376 | 7 | 5 |
| `scene-explainer` | explainer | — | 34 | 5 | 6 | 7 / 369 | 7 | 5 |
| `scene-scare` | scare | — | 35 | 5 | 6 | 7 / 386 | 6 | 5 |
| `scene-opening-hook` | opening-hook | opening | 35 | 5 | 4 | 7 / 365 | 6 | 5 |
| `scene-cliffhanger` | cliffhanger | ending | 36 | 5 | 4 | 7 / 364 | 6 | 5 |

### 4.3 原文重合结果

脚本逐一遍历 §11 的 56 个来源文件，对 9 张卡与 `trial-scenes.md` 做连续 20 字比对，`sources` 行里的路径字符串不计；同时给出 2 种口径：

- 叙述性字段（标题、摘要、信号、节拍、覆盖、运镜、声音、风险、示例），保留标点与去标点各查 1 遍；
- 整张卡原文（只去掉 `sources` 行，保留 id、标签、引用 id 与 Markdown），保留标点查 1 遍。

```text
§11 来源文件数: 56
[§11 来源][保留标点] 查 10 个文件，累计 13203 字
[§11 来源][去标点] 查 10 个文件，累计 11540 字
§11 来源叙述字段重合命中数: 0
§11 来源全字段（仅去 sources 行）保留标点重合命中数: 0（20228 字）
[样卡][保留标点] 查 10 个文件，累计 13203 字
[样卡][去标点] 查 10 个文件，累计 11540 字
样卡重合命中数: 0
```

要求的「连续 20 字与来源相同」命中数为 **0**；叙述字段与2 张样卡的命中数也是 **0**。

### 4.4 试拆样本结果

3 场正文都在 300–600 字区间（CJK 字数 347 / 354 / 407；非空白字符 437 / 403 / 489）；标签均通过 §5 合法值校验；没有引用或改写样卡、来源的成段原文。

### 4.5 测试

按要求没有跑完整 pytest。上述 2 个临时脚本是本次全部自动化检查；没有新增仓库内测试文件。

## 5. 未完成 / 需确认

- 本块无未完成项：7 张内容卡、2 张位置卡、3 场试拆样本、报告均已落盘。
- 供主控集成时核对：
  1. 自查时全库 58 张卡（13 语法 + 19 场景 + 5 模型 + 21 反例）已落盘并通过引用校验；若 D1 / D3 / D4 在本报告之后还有改动，建议重跑 `load_cards()`。
  2. 试拆样本的打斗使用 `position: opening`、揭示使用 `position: ending`，目的是同时覆盖2 张位置卡；若阶段三只想比内容卡，改成 `body` 即可。
  3. `scene-opening-hook` 的 `related_negative` 含 `negative-no-establishing-shot`，这是有意的：钩子把定场镜推迟到第 2 镜，不是取消定场；卡里已写清「环境放到第 2 镜补」。
  4. 位置卡的 `pacing` 是位置本身的节奏建议，叠加内容卡时可取两者中更合适的一档，不必机械相加。
