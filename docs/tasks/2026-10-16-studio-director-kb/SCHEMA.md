# 导演知识库卡片 SCHEMA（kb/v1）

本文件写给两类读者：
- 整理卡片的人：照着写就能通过校验。
- 实现加载器和知识库检查的人（Codex）：照着实现，就能把每条规则落成代码。

卡片是纯数据，运行时只读本地文件，不访问网络。

---

## 1. 目录与文件

```
cards/
  grammar/     镜头语法卡   kb.grammar/v1
  scenes/      场景模板卡   kb.scene/v1
  providers/   模型能力卡   kb.provider/v1
  negatives/   反例卡       kb.neg/v1
SCHEMA.md      本文件
SOURCES.md     来源登记表（机器读）+ 逐卡来源与许可表
```

- 一个 `.yaml` 文件只放一张卡：单文档，顶层是映射。
- 文件编码 UTF-8；缩进用空格；不使用 YAML 锚点和别名（`&` / `*`）。
- 部署路径：随仓库放在 `backend/studio/director_kb/cards/`。`SCHEMA.md` 和 `SOURCES.md` 放在 `director_kb/` 下。

## 2. id 命名

### 2.1 卡片 id

格式：`<层>.<短名>`

| 层 | 目录 | schema 值 |
|---|---|---|
| `grammar` | `cards/grammar/` | `kb.grammar/v1` |
| `scene` | `cards/scenes/` | `kb.scene/v1` |
| `provider` | `cards/providers/` | `kb.provider/v1` |
| `neg` | `cards/negatives/` | `kb.neg/v1` |

- 短名的正则：`^[a-z0-9]+(_[a-z0-9]+)*$`。
- **id 必须等于 `<层>.<文件名去掉 .yaml>`，文件也必须在该层的目录里。**例如 `cards/grammar/move_orbit.yaml` 的 id 只能是 `grammar.move_orbit`。
- id 全库唯一。卡片一经引用就不改名；要废弃时把 `status` 改成 `deprecated`，并用 `replaced_by_ref` 指向新卡。

语法卡短名按家族取固定前缀：

| 家族 `family` | 前缀 |
|---|---|
| `shot_size` | `size_` |
| `angle` | `angle_` |
| `position` | `pos_` |
| `movement` | `move_` |
| `lens` | `lens_`、`dof_`、`focus_` |
| `transition` | `trans_` |
| `axis` | `axis_` |
| `continuity` | `cont_` |
| `time` | `time_` |

模型能力卡短名：`<provider>_<style>`，例如 `seedance25_realistic`。其中 `provider ∈ {wan30, seedance25, seedance20}`，`style ∈ {base, realistic, anime, 3d}`。

### 2.2 卡内条目 id

卡内列表条目带 id，便于拆镜时精确引用。前缀固定，卡内唯一：

| 前缀 | 所在列表 | 例 |
|---|---|---|
| `B` | 场景卡 `beats` | `B1` |
| `C` | 场景卡 `coverage` | `C3` |
| `R` | 场景卡 `ai_risks` | `R2` |
| `G` | 场景卡 `example.gens` | `G1` |
| `E` | 场景卡 `example.shots` | `E4` |
| `D` / `N` | 场景卡 `example.cues`（对白 / 旁白） | `D01`、`N02` |
| `M` | 模型能力卡 `rules` | `M3` |

条目 id 的正则：`^[A-Z][0-9]+$`。

### 2.3 来源 id

格式：`src.<短名>`，短名规则同 2.1。所有来源 id 都必须登记在 `SOURCES.md` 的登记表里（第 9 节）。

## 3. 引用方式

- **引用字段靠键名识别**：键名为 `ref` 或以 `_ref` 结尾的，值是一个 id 字符串；键名为 `refs` 或以 `_refs` 结尾的，值是 id 列表。其余字段里出现的 id 字样都不算引用。
- 引用值的正则：`^(grammar|scene|provider|neg)\.[a-z0-9_]+(#[A-Z][0-9]+)?$`
- 带锚点（`scene.fight#R1`）时，`#` 后面的条目 id 必须在目标卡里存在。
- 来源用 `sources`（卡片级，列表）和 `src`（条目级，列表）两个键，值是 `src.*`。条目级的 `src` 必须是卡片级 `sources` 的子集。
- 常用的引用键：`see_refs`（相关卡）、`size_refs`、`angle_ref`、`camera_ref`、`default_refs`、`transition_refs`、`route_to_ref`、`neg_refs`、`provider_refs`、`coverage_ref`、`extends_ref`、`replaced_by_ref`。

按键名还有一条类型约束（V17）：

| 键 | 只能指向 |
|---|---|
| `size_refs` | `family: shot_size` 的语法卡 |
| `angle_ref` | `family: angle` 或 `position` |
| `camera_ref`、`camera.default_refs`、`camera.*[].ref` | `family: movement` |
| `transition_refs` | `family: transition` |
| `route_to_ref` | 场景卡，且不能是本卡 |
| `neg_refs` | 反例卡 |
| `provider_refs`、`extends_ref` | 模型能力卡 |
| `coverage_ref` | `scene.<本卡>#C<n>` |

## 4. 公共字段（四层都有）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema` | 字符串 | 是 | 与所在层一致，例如 `kb.scene/v1` |
| `id` | 字符串 | 是 | 见 2.1 |
| `title` | 字符串 | 是 | 中文名 |
| `version` | 整数 ≥ 1 | 是 | 内容每改一次加 1 |
| `status` | 枚举 | 是 | `draft` 草稿 / `reviewed` 用户已过目 / `approved` 生效 / `deprecated` 废弃 |
| `updated` | 日期 `YYYY-MM-DD` | 是 | 最后修改日 |
| `summary` | 字符串 | 是 | 不超过 300 字；精简注入时只注入它 |
| `sources` | `src.*` 列表 | 是 | 至少 1 项 |
| `aliases` | 字符串列表 | 否 | 同义词、英文术语，用于识别和知识库检查 |
| `notes` | 字符串 | 否 | 给维护者看，不注入 |

条目级可以出现的通用可选字段：`src`（来源）、`note`（补充说明）、`decision`（用户裁决记录，如「2026-10-16 用户确认」）。

**状态与加载**：第一版加载全部状态的卡（`deprecated` 除外），知识库页面标出状态。`draft` 卡照常参与拆镜，等用户逐张过目后改成 `reviewed` 或 `approved`。

## 5. 受控词表

| 词表 | 取值 |
|---|---|
| `pace` | `fast` / `medium` / `slow` |
| `emotion` | `calm` / `warm` / `joy` / `sad` / `tense` / `fear` / `anger` / `awe` / `comic` / `mystery` |
| `cast` | `none`（0 人）/ `solo`（1）/ `duo`（2）/ `small_group`（3–5）/ `crowd`（6 人以上） |
| `realism` | `realistic` / `anime` / `3d` |
| `setting` | `interior` / `exterior` / `mixed` |
| `providers` | `wan30` / `seedance25` / `seedance20` |
| `sensitivity` | `face`（可读人脸：近景及更紧，或露正脸、侧脸的人物）/ `structure`（机构、兵器形状、建筑结构必须保持）/ `material`（金属、液体、毛发等材质必须保持）/ `text_ui`（精确文字、数字、界面，只能后期做） |
| `severity` | `P0` 很可能失败，必须先有降级 / `P1` 有明显风险，要有降级方案 / `P2` 低风险 |
| `mouth` | `none` / `averted` / `masked` / `visible`（与 05-声画时间轴一致） |
| `lip_sync` | `none` / `offscreen` / `avoid` / `sync`（与 05 一致） |

`applies_to`：映射，可选键为 `providers`、`realism`、`sensitivity`，值取自上表。缺省的键表示不限；`applies_to: {}` 表示所有通道、所有画风都适用。

## 6. 各层字段

### 6.1 镜头语法卡 `kb.grammar/v1`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `family` | 枚举 | 是 | `shot_size` / `angle` / `position` / `movement` / `lens` / `transition` / `axis` / `continuity` / `time` |
| `definition` | 字符串 | 是 | 定义，用自己的话写 |
| `narrative_use` | 字符串列表 | 是 | 叙事作用，至少 1 条 |
| `prompt.write` | 字符串列表 | 是 | 提示词里的安全写法，至少 1 条。生僻术语一律写成「术语 + 白话」 |
| `prompt.avoid` | 字符串列表 | 是 | 不要这样写；可以为空列表 |
| `order` | 整数 1–9 | 仅 `shot_size` | 景别从远到近的序号 |
| `framing` | 字符串 | 仅 `shot_size` | 画面边界，例如「胸部以上」 |
| `mouth_readable` | `none` / `low` / `high` | 仅 `shot_size` | 嘴形可读程度，决定口型方案 |
| `sensitive_ok` | 布尔 | 仅 `movement` | 能否用在 `sensitivity` 非空的镜头。统一口径下只有 `move_static` 为 `true` |
| `camerabench` | 字符串列表 | `movement` 必填，其他可选 | 对应的 CameraBench 标签，例如 `dolly-in` |
| `provider_notes` | 列表 | 否 | 每项：`providers`、可选 `realism`、`note`、可选 `src` |
| `risks` | 列表 | 否 | 每项：`risk`、`mitigation`、可选 `neg_refs` |
| `see_refs` | id 列表 | 否 | 相关卡 |

### 6.2 场景模板卡 `kb.scene/v1`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `position_type` | `content` / `position` | 否，缺省 `content` | `position` 表示按在集里的位置判定（开场钩子、结尾悬念），可以和内容类型叠加 |
| `definition` | 字符串 | 是 | 一句定义 |
| `tags` | 映射 | 是 | 键 `pace`、`emotion`、`cast`、`realism`、`setting` 都要有，值是受控词列表，至少 1 项 |
| `signals.strong` | 字符串列表 | 是 | 强信号，至少 1 条 |
| `signals.weak` | 字符串列表 | 是 | 弱信号，可为空 |
| `signals.counter` | 列表 | 是 | 每项 `signal` + `route_to_ref`，可为空 |
| `directing` | 列表 | 是 | 每项 `rule`，可选 `see_refs`、`src`；至少 1 项 |
| `beats` | 列表 | 是 | 每项 `id`（B）、`name`、`purpose`、`share: [下限, 上限]`；至少 2 项 |
| `coverage` | 列表 | 是 | 每项 `id`（C）、`beat`、`shot`、`size_refs`、`camera_ref`、`purpose`；可选 `angle_ref`、`optional`、`transition_refs`、`see_refs`；至少 2 项 |
| `pacing.basis` | 字符串 | 是 | 数值依据 |
| `pacing.tiers.{fast,medium,slow}` | 映射 | 三档都必填 | `shot_len_s: [短, 长]`（成片剪辑长度，秒）、`shots_per_min: [少, 多]`、`gen_ratio: [低, 高]`（生成总秒数 ÷ 成片秒数）、`use_when` |
| `generation` | 映射 | 是 | `min_gen_s`（≥ 4）、`strategy`、`rules`（至少 1 条），可选 `routes`（每项 `id`、`name`、`how`，可选 `evidence`、`risk`、`decision`、`src`）、`src` |
| `camera` | 映射 | 是 | `default_refs`（至少 1 个）、`allowed`、`nonsensitive_only`、`avoid` |
| `sound.items` | 字符串列表 | 是 | 声音要点，至少 1 条；同级可选 `see_refs`、`src` |
| `ai_risks` | 列表 | 是 | 至少 1 项，字段见下 |
| `example` | 映射 | 是 | 字段见下 |
| `action_units` | 映射 | 否 | 动作单元计数口径：`rule`、`ok`、`not_ok` |
| `lip_sync` | 映射 | 否 | 口型档位：`default`、`ladder`、`rule` |

`generation.strategy` 的取值：
- `by_angle`：按机位生成长条，交叉裁切。
- `one_take_multi_cut`：一条连续动作裁成多镜。
- `per_shot`：一镜一条。
- `post_heavy`：大量后期镜。
- `mixed`：混合。

`camera` 的四个列表：
- `allowed`：每项 `ref` + `condition`，**只能放 `sensitive_ok: true` 的运镜**。
- `nonsensitive_only`：每项 `ref` + `condition`，只能用在 `sensitivity` 为空的镜头。
- `avoid`：每项 `what` + `reason`，可选 `neg_refs`。

`ai_risks[]` 的字段：
- 必填：`id`（R）、`risk`、`applies_to`、`symptom`、`mitigation`、`fallback`、`severity`。
- 可选：`provider_refs`、`neg_refs`、`see_refs`、`note`、`src`。

`example` 的字段：
- `title`、`setup`、`totals`：必填，字符串。
- `gens`：至少 1 项。每项必填 `id`（G）和 `duration_s`（整数 ≥ `min_gen_s`）；`video_prompt` 与 `action` 至少写一个；可选 `coverage_ref`、`angle`、`camera`、`note`。
- `shots`：至少 2 项。每项 `id`（E）、`beat`、`from`、`len_s`。
  - `from` 是本例的 G 条目 id，或字面量 `post_only`。
  - `from` 是 G 时必须有 `in_s`（在生成条里的入点）。
  - 可选字段：`speed`（播放速度系数，缺省 1；0.6 表示减速到 0.6 倍）、`cue_ids`、`mouth`、`note`。
- `cues`：可选。每项 `id`（D 或 N）、`role`、`text`、`delivery`、`lip_sync`。

### 6.3 模型能力卡 `kb.provider/v1`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `provider` | 枚举 | 是 | `wan30` / `seedance25` / `seedance20` |
| `style` | 枚举 | 是 | `base` / `realistic` / `anime` / `3d`；必须与短名一致 |
| `tested` | 枚举 | 是 | `tested` 有本人实测 / `partial` 部分实测 / `untested` 只有官方资料 |
| `extends_ref` | id | 画风卡必填 | 指向同一 provider 的 `_base` 卡 |
| `model_ids` | 字符串列表 | base 必填 | 接口里的模型 id；本机还没接入时写空列表 `[]` |
| `capabilities` | 映射 | base 必填 | `input_modes`、`duration_s: [最短, 最长]`、`resolutions`、`ratios`、`native_audio`（布尔）、`reference_audio`（布尔，是否支持参考音频输入）、`last_frame`（布尔）、`max_reference_images`（整数）、`unsupported`（列表）。官方资料没写、也没实测的值写 `null` |
| `pricing_note` | 字符串 | base 必填 | 参考价及日期；以控制台为准 |
| `prompt_syntax` | 映射 | base 必填 | `structure`；`timestamps`（`supported` 布尔、`format`、`note`）；`shot_labels`、`dialogue`、`negatives`；可选 `symbols` |
| `pipeline_overrides` | 列表 | base 必填 | 本工作室规则高于厂商能力的地方。每项 `rule` + `why`，可选 `src` |
| `limits` | 映射 | base 必填 | 可选键：`cast_stable_max`、`prompt_max_chars`、`reference_subjects_stable`、`concurrent_tasks`；未知写 `null` |
| `portrait_gate` | 映射 | 画风卡必填 | `status`（`tested` / `untested` / `none`）、`blocks`、`passes`、`workarounds`（都是列表） |
| `copyright` | 映射 | 画风卡必填 | 字段同 `portrait_gate` |
| `style_drift` | 字符串 | 画风卡必填 | 风格漂移风险与对策 |
| `rules` | 列表 | 是 | 每项 `id`（M）、`rule`、`why`，可选 `neg_refs`、`src`；至少 1 项 |

### 6.4 反例卡 `kb.neg/v1`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `category` | 枚举 | 是 | `camera` / `prompt` / `performance` / `audio` / `provider` / `continuity` / `physics` / `production` |
| `wrong` | 字符串 | 是 | 错误写法，可以是提示词片段 |
| `why` | 字符串 | 是 | 为什么错 |
| `right` | 字符串 | 是 | 正确写法 |
| `applies_to` | 映射 | 是 | 见第 5 节 |
| `evidence` | 列表 | 否 | 实测案例。每项 `case`、`detail`，可选 `src` |
| `level` | `warning` / `info` | 是 | 知识库检查报出时的级别；按计划一律并入 G2 报告，不阻塞 |
| `check` | 映射 | 否 | 机器检查规则，见第 8 节；没有的话，只作为注入材料 |
| `see_refs` | id 列表 | 否 | 相关卡 |

## 7. 校验规则（加载时全部执行，任何一条不过都拒绝加载并列出原因）

| 编号 | 规则 |
|---|---|
| V01 | 每个文件是单文档 YAML，顶层是映射，能被安全加载（不执行标签） |
| V02 | `schema` 与所在目录对应的层一致 |
| V03 | `id` 合乎 2.1；等于「层 + 文件名」；全库唯一 |
| V04 | 本层必填字段齐全、类型正确。未知的顶层字段报 warning，不拒绝 |
| V05 | 受控词表字段只取第 5 节里的值 |
| V06 | 所有引用字段的值合乎第 3 节正则；目标卡存在；带锚点时锚点在目标卡里存在 |
| V07 | `sources` 非空；所有 `src.*` 都在 SOURCES.md 登记表里；条目级 `src` ⊆ 卡片级 `sources` |
| V08 | 卡内条目 id 唯一，前缀与所在列表一致（2.2） |
| V09 | 场景卡 `beats`：每项 `0 ≤ 下限 ≤ 上限 ≤ 1`，且所有下限之和 ≤ 1 ≤ 所有上限之和 |
| V10 | 场景卡 `pacing`：`shot_len_s` 短 < 长，且短 ≥ 1.4；`shots_per_min` 与 `[60 ÷ 长, 60 ÷ 短]` 每端相差不超过 1；`gen_ratio` 低 > 0 且低 ≤ 高 |
| V11 | 场景卡：`coverage[].beat` 和 `example.shots[].beat` 指向本卡 `beats`；`shots[].from` 指向本例 `gens` 或等于 `post_only`；`in_s + len_s × speed ≤` 该生成条的 `duration_s`；`cue_ids` 指向本例 `cues` |
| V12 | 场景卡 `generation.min_gen_s ≥ 4`；`example.gens[].duration_s` 是整数，且 ≥ `min_gen_s` |
| V13 | 模型能力卡：每个 provider 恰好有 `base`、`realistic`、`anime`、`3d` 四张；画风卡的 `extends_ref` 指向同 provider 的 base；`provider` / `style` 与短名一致 |
| V14 | 反例卡的 `check.kind` 在第 8 节枚举里；其中的正则都能编译 |
| V15 | SOURCES.md 的逐卡来源表与各卡 `sources` 完全一致（表由卡片生成，改卡后重新生成） |
| V16 | `route_to_ref` 只指向场景卡，且不指向本卡 |
| V17 | 引用键的目标类型合乎第 3 节的表 |
| V18 | 场景卡 `camera.allowed[].ref` 指向的运镜卡必须 `sensitive_ok: true`；`sensitive_ok: false` 的运镜只能出现在 `nonsensitive_only` 里 |
| V19 | 语法卡的 `family` 与短名前缀一致（2.1 的表）；`shot_size` 卡的 `order` 1–9 各出现一次 |

## 8. 知识库检查（`neg.*.check`）

检查对象是拆镜清单里的每一个镜头，结果作为 warning 并入 G2 报告。

**依赖拆镜输出的新增字段**：导演模型在每镜的 `review.kb` 里填写（见第 10 节）：
- `sensitivity`：受控词列表，可为空。
- `action_units`：整数，按场景卡 `action_units` 的口径计数。
- `face_visible`：布尔，画面里有没有可读的人脸。

`check` 的通用结构：

```yaml
check:
  kind: <见下表>
  when: {providers: [...], realism: [...], sensitivity: [...], gen_audio: true|false}   # 可选，全部满足才检查
  # 以下是该 kind 的参数
```

| kind | 参数 | 命中条件 |
|---|---|---|
| `regex_forbid` | `fields`、`patterns`、可选 `ignore_case` | 指定字段里任一正则命中 |
| `regex_require` | `fields`、`patterns` | 指定字段里所有正则都没命中 |
| `sensitive_camera` | `static_patterns` | `review.kb.sensitivity` 非空，而 `review.framing.camera` 不匹配任何「固定」类正则 |
| `action_count` | `max` | `review.kb.action_units > max` |
| `provider_face` | `providers`、`realism` | 镜头所用通道在列表里，项目画风在列表里，且 `review.kb.face_visible` 为真 |
| `min_gen_duration` | `min` | `gen.enabled` 为真且 `gen.duration < min` |
| `cue_mouth` | `deliveries`、`require_patterns` | 被 `delivery` 属于 `deliveries` 的 cue 覆盖的镜头，`video_prompt` 里没有任何 `require_patterns` 命中 |

`fields` 可取 `video_prompt`、`prompt`（关键帧提示词）、`review.framing.camera`、`review.framing.lens`。

## 9. SOURCES.md 的机器读部分

SOURCES.md 里第一个 ` ```yaml ` 代码块就是登记表：

```yaml
sources:
  - id: src.wan3_guide
    title: …
    kind: official | user | third_party | dataset | general
    priority: 1 | 2 | 3 | 4      # 冲突时数字小的优先（计划「规则冲突时的优先级」）
    license: …
    url_or_path: …
    usage: …                     # 怎么用的：只提炼规则 / 只取概念 / 用户自有内容
    retrieved: YYYY-MM-DD
```

逐卡来源与许可表在登记表后面，用 Markdown 表格。表由卡片的 `sources` 生成，V15 校验两者一致。

## 10. 取材料约定（拆镜时按标签取卡，结果确定）

输入：每场的标签。
- `scene_type`：主类型，1 个。
- `secondary_type`：次类型，可选，最多 1 个（2026-10-16 用户确认）。
- `pace`、`emotion`、`cast`、`realism`、`setting`。
- 本场用到的 `providers`。

取卡顺序，每一步内部都按 id 字典序排列：

1. **固定前缀**（每集不变，适合开提示词缓存）：
   - 全部语法卡的精简版：`title`、`summary`、`prompt.write` 前 2 条、`sensitive_ok`。
   - 本项目所用通道的 `_base` 卡，以及项目画风对应的那张画风卡。
2. **场景模板**：主类型卡全文。
   - 选档：`pacing.tiers` 只保留与 `pace` 对应的一档。
   - 过滤：`ai_risks` 只保留 `applies_to` 与本场通道、画风匹配的条目。
3. **次类型**：只取它的 `ai_risks`（同样过滤）和 `camera.avoid`。
4. **反例卡**：以下两类的并集。
   - 第 2、3 步取到的内容里 `neg_refs` 指到的卡。
   - 固定前缀里模型能力卡的 `rules[].neg_refs`。
5. **案例**：`studio_exemplars` 里同 `scene_type` 的已批准镜头，最多 3 个，优先同 `realism`、同通道；再加同类反例最多 2 个。

注入上限建议：第 2 到 5 步合计不超过 8k token。超出时按「案例 → 反例 → 次类型」的顺序截断。场景模板本身不截断。

**拆镜输出怎么引用**：
- 每场写 `kb.template_ref: scene.<类型>`；偏离模板时写 `kb.deviation`，说明理由。
- 每镜在 `review.kb` 里写：
  - `basis_refs`：依据的卡片或条目，例如 `[scene.dialogue#C2, grammar.pos_over_shoulder]`。
  - 第 8 节要求的 `sensitivity`、`action_units`、`face_visible`。
