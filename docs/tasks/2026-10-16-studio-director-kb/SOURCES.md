# 导演知识库 · 来源与许可

所有卡片都是**用自己的话提炼规则**：
- 不复制原文段落、示例视频或剧照。
- 你自己的规则、实测记录和成片属于你自有的内容，按原意转写。
- 来源冲突时按 `priority` 取舍，数字小的优先：1 你的规则与实测 → 2 厂商官方指南 → 3 第三方 Skill → 4 通用影视语法（已批准计划「规则冲突时的优先级」）。

**没有使用**：ShotDeck、FilmGrab 等商业剧照库；CC BY-NC 教材；中传教材；MovieNet、AVE 的数据本体；CineTechBench；DataDoP。

**需要写进 `THIRD_PARTY_NOTICES.md` 的四项**（实现时由 Codex 补）：
- ai-visual-director（MIT）
- prop-asset（Apache-2.0）
- CameraBench 运镜标签（CC BY 4.0）
- seedance-shot-design（MIT-0）

MIT-0 不要求署名，计划里已经决定一并列出。

## 来源登记表（机器读）

```yaml
sources:
  - id: src.user_02
    title: shortfilm-pipeline · 02-分集拆镜
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/Desktop/视频生成/.claude/skills/shortfilm-pipeline/references/02-分集拆镜.md
    usage: 规则原样遵循，用自己的话转写进卡片
    retrieved: 2026-10-16
  - id: src.user_05
    title: shortfilm-pipeline · 05-声画时间轴（SXX.json v2.1 合同）
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/Desktop/视频生成/.claude/skills/shortfilm-pipeline/references/05-声画时间轴.md
    usage: 字段与口型、声音规则原样遵循
    retrieved: 2026-10-16
  - id: src.plan
    title: Fiona 短片工作室计划（2026-10-16 批准）
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/plans/fiona-shimmering-goose.md
    usage: 默认分辨率、每集时长与镜头数、价格、知识库口径
    retrieved: 2026-10-16
  - id: src.p01_audit
    title: Preloq P01 清单（note_audit 与镜头记录），以及 P02 G2 草稿清单
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/Desktop/视频生成/Preloq短视频/清单/P01.json（另参考 P02.json、文案/P02_G2分镜表.md）
    usage: 三次返工的反例、万相实测的镜长与生成时长；P02 作为未生成的草稿示例
    retrieved: 2026-10-16
  - id: src.xiakexing_files
    title: 《侠客行》提示词脚本与剪辑表
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/Desktop/侠客行/tools/make_video_args.py、方案/视频提示词/*.json、剪辑/render_1080.py
    usage: 打斗模板的镜长、裁切入点、运镜与提示词结构
    retrieved: 2026-10-16
  - id: src.mcp_models
    title: 本机 seedance MCP 模型规格表（list_video_models，本地数据，不联网）
    kind: user
    priority: 1
    license: 用户自有工具
    url_or_path: mcp__seedance__list_video_models
    usage: 时长档、分辨率、画幅、能力缺口（不支持参考音频等）、参考价
    retrieved: 2026-10-16
  - id: src.mem_xiakexing
    title: memory · 《侠客行》沙漠打斗片
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/projects/-Users-yangjing-Desktop-----/memory/xiakexing-project.md
    usage: Seedance 肖像闸实测与绕法、1080p 计费
    retrieved: 2026-10-16
  - id: src.mem_copyright
    title: memory · Seedance 输出阶段版权拦截
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/projects/-Users-yangjing-Desktop-----/memory/seedance-copyright-output-filter.md
    usage: 版权拦截的触发条件、美术差异化与小剪影两种解法、720p 计费
    retrieved: 2026-10-16
  - id: src.mem_preloq
    title: memory · Preloq 机器人科普竖屏短片
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/projects/-Users-yangjing-Desktop-----/memory/preloq-shorts-project.md
    usage: 万相 3.0 生产经验、话术红线、竖屏合成参数
    retrieved: 2026-10-16
  - id: src.mem_lanhai
    title: memory · 《蓝海囚笼》通道选型
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/projects/-Users-yangjing-Desktop-----/memory/lanhai-project-channels.md
    usage: 写实人脸走万相、Seedance 动漫露脸可过、暗场误报教训
    retrieved: 2026-10-16
  - id: src.mem_robotdog
    title: memory · 机器狗抓小猪短片
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/projects/-Users-yangjing-Desktop-----/memory/robotdog-pig-project.md
    usage: 角色重制一律从现役定妆图派生
    retrieved: 2026-10-16
  - id: src.mem_guanyin
    title: memory · 《观音入梦》短片
    kind: user
    priority: 1
    license: 用户自有
    url_or_path: ~/.claude/projects/-Users-yangjing-Desktop-----/memory/guanyin-dream-project.md
    usage: 人物一律背影、侧影、剪影；宗教意象庄严
    retrieved: 2026-10-16
  - id: src.wan3_guide
    title: 阿里云百炼 · 万相 3.0 视频生成提示词指南（含短剧最佳实践）
    kind: official
    priority: 2
    license: 阿里云文档，版权归阿里云；只提炼规则
    url_or_path: https://help.aliyun.com/zh/model-studio/wan3-video-generation-prompt-guide
    usage: 只提炼规则，用自己的话写；不复制原文、示例提示词和示例视频
    retrieved: 2026-10-16
  - id: src.wan_t2v_guide
    title: 阿里云百炼 · 文生视频 / 图生视频提示词指南
    kind: official
    priority: 2
    license: 阿里云文档，版权归阿里云；只提炼规则
    url_or_path: https://help.aliyun.com/zh/model-studio/text-to-video-prompt
    usage: 只提炼规则（图生视频公式、景别与运镜词表），用自己的话写
    retrieved: 2026-10-16
  - id: src.sd25_guide
    title: 火山方舟 · Doubao Seedance 2.5 提示词指南
    kind: official
    priority: 2
    license: 火山引擎文档，版权归火山引擎；只提炼规则
    url_or_path: https://docs.volcengine.com/docs/82379/2607689（实际跳转到 docs.volcengine.com/docs/ark/seedance-2-5-prompt-guide）
    usage: 只提炼规则（整数秒时间戳、FAQ 里的失败与修法），用自己的话写
    retrieved: 2026-10-16
  - id: src.sd20_guide
    title: 火山方舟 · Doubao Seedance 2.0 系列提示词指南
    kind: official
    priority: 2
    license: 火山引擎文档，版权归火山引擎；只提炼规则
    url_or_path: https://docs.volcengine.com/docs/ark/seedance-2-0-prompt-guide
    usage: 只提炼规则（镜头序号代替时间戳、低缓动作、多视图与人数问题），用自己的话写
    retrieved: 2026-10-16
  - id: src.sds
    title: seedance-shot-design（Copyright 2025 woodfantasy）
    kind: third_party
    priority: 3
    license: MIT-0（MIT No Attribution）
    url_or_path: ~/.claude/skills/seedance-shot-design（references/scenarios.md、cinematography.md、failure-diagnosis.md）
    usage: 提炼短剧调度三要素、运镜安全写法、8 类失败诊断；与本工作室规则冲突处按本工作室规则改写（如微表情模板默认手持改为固定机位）
    retrieved: 2026-10-16
  - id: src.avd
    title: ai-visual-director（Copyright (c) 2026 AI Visual Director Contributors）
    kind: third_party
    priority: 3
    license: MIT
    url_or_path: ~/.claude/skills/ai-visual-director（knowledge/pacing-types.md、emotion-curves.md、directing-performance.md、editing-theory.md、transitions.md、camera.md）
    usage: 提炼节奏类型、调度与视线、匹配剪辑与转场的概念；数值按本工作室口径重定（不采用 0.5–1.5 秒/镜的快切）
    retrieved: 2026-10-16
  - id: src.prop_asset
    title: prop-asset · 反面案例与改写账本（NEGATIVE-CASE-BOOK.md）
    kind: third_party
    priority: 3
    license: Apache-2.0
    url_or_path: ~/.claude/skills/prop-asset/references/NEGATIVE-CASE-BOOK.md
    usage: 提炼「错误写法 → 正确写法」的思路和若干条目，例句全部重写
    retrieved: 2026-10-16
  - id: src.camerabench
    title: CameraBench 运镜标签体系（Lin et al., Towards Understanding Camera Motions in Any Video, NeurIPS 2025 Datasets and Benchmarks）
    kind: dataset
    priority: 4
    license: 数据集 CC BY 4.0（Hugging Face syCen/CameraBench）；论文本身在 arXiv 用的是非独占分发许可，未复制论文内容
    url_or_path: https://huggingface.co/datasets/syCen/CameraBench ；https://linzhiqiu.github.io/papers/camerabench/
    usage: 只取运镜标签名（dolly-in、truck-left、arc-CW、side-tracking 等），写进运镜卡的 camerabench 字段，注明出处
    retrieved: 2026-10-16
  - id: src.film_grammar
    title: 通用影视语法常识（景别阶梯、180° 轴线、正反打、J/L cut、匹配剪辑等）
    kind: general
    priority: 4
    license: 通用知识，自己写；没有复制 Wikipedia 或教材原文
    url_or_path: 无
    usage: 定义与叙事作用的通用部分
    retrieved: 2026-10-16
```

## 逐卡来源与许可

下表由各卡的 `sources` 字段生成；改了卡片之后重新生成，校验规则 V15 会核对两者是否一致。

「许可」一列只列第三方和数据集的许可；你的自有内容和厂商文档见上方登记表。

<!-- BEGIN 逐卡表（脚本生成，勿手改） -->
| 卡片 id | 标题 | 状态 | 来源 | 涉及的第三方许可 |
|---|---|---|---|---|
| `grammar.angle_dutch` | 荷兰角 | draft | `src.film_grammar`、`src.sds`、`src.avd` | MIT、MIT-0 |
| `grammar.angle_eye_level` | 平视 | draft | `src.film_grammar`、`src.sds`、`src.wan_t2v_guide` | MIT-0 |
| `grammar.angle_high` | 高角度俯拍 | draft | `src.film_grammar`、`src.sds`、`src.mem_xiakexing` | MIT-0 |
| `grammar.angle_low` | 低角度仰拍 | draft | `src.film_grammar`、`src.sds`、`src.avd` | MIT、MIT-0 |
| `grammar.angle_top_down` | 正上方顶视 | draft | `src.film_grammar`、`src.sds`、`src.xiakexing_files` | MIT-0 |
| `grammar.axis_180` | 180° 轴线 | draft | `src.film_grammar`、`src.avd`、`src.user_02` | MIT |
| `grammar.axis_eyeline` | 视线 | draft | `src.film_grammar`、`src.sds`、`src.avd` | MIT、MIT-0 |
| `grammar.axis_reset` | 越轴重建 | draft | `src.film_grammar`、`src.avd` | MIT |
| `grammar.axis_screen_direction` | 运动方向 | draft | `src.film_grammar`、`src.avd` | MIT |
| `grammar.cont_in_out_state` | 入出状态 | draft | `src.user_02`、`src.user_05`、`src.prop_asset` | Apache-2.0 |
| `grammar.cont_lighting` | 光向与光质 | draft | `src.user_02`、`src.sds` | MIT-0 |
| `grammar.cont_props_hands` | 道具与持手 | draft | `src.user_05`、`src.prop_asset` | Apache-2.0 |
| `grammar.cont_sound_state` | 声音状态 | draft | `src.user_02`、`src.user_05` | — |
| `grammar.cont_time_weather` | 时间与天气 | draft | `src.user_02`、`src.user_05` | — |
| `grammar.cont_wardrobe_damage` | 服装与伤痕累积 | draft | `src.film_grammar`、`src.wan3_guide` | — |
| `grammar.dof_deep` | 深焦 | draft | `src.film_grammar`、`src.sds`、`src.wan3_guide` | MIT-0 |
| `grammar.dof_shallow` | 浅景深 | draft | `src.film_grammar`、`src.sds` | MIT-0 |
| `grammar.focus_rack` | 移焦 | draft | `src.film_grammar`、`src.sds`、`src.sd25_guide` | MIT-0 |
| `grammar.lens_standard` | 标准焦段 | draft | `src.film_grammar`、`src.sds`、`src.user_02` | MIT-0 |
| `grammar.lens_tele` | 长焦 | draft | `src.film_grammar`、`src.sds`、`src.user_02` | MIT-0 |
| `grammar.lens_wide` | 广角 | draft | `src.film_grammar`、`src.sds`、`src.user_02`、`src.wan3_guide` | MIT-0 |
| `grammar.move_aerial` | 高空俯拍（无人机视角） | draft | `src.camerabench`、`src.sds`、`src.sd25_guide`、`src.xiakexing_files`、`src.mem_xiakexing`、`src.user_02` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_crane_arm` | 摇臂升降 | draft | `src.camerabench`、`src.sds`、`src.user_02` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_follow` | 跟拍 | draft | `src.camerabench`、`src.sds`、`src.xiakexing_files` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_handheld` | 手持 | draft | `src.camerabench`、`src.sds`、`src.wan3_guide`、`src.user_02` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_orbit` | 环绕 | draft | `src.camerabench`、`src.sds`、`src.wan3_guide`、`src.p01_audit`、`src.xiakexing_files`、`src.mem_xiakexing` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_pan` | 水平摇 | draft | `src.camerabench`、`src.sds`、`src.wan3_guide` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_pedestal` | 升降 | draft | `src.camerabench`、`src.sds`、`src.p01_audit`、`src.mem_preloq` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_pull_out` | 拉远 | draft | `src.camerabench`、`src.sds`、`src.p01_audit` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_push_in` | 推近 | draft | `src.camerabench`、`src.sds`、`src.prop_asset`、`src.p01_audit`、`src.user_02` | Apache-2.0、MIT-0、数据集 CC BY 4.0 |
| `grammar.move_shake_impact` | 撞击震动 | draft | `src.camerabench`、`src.wan3_guide`、`src.p01_audit`、`src.user_02` | 数据集 CC BY 4.0 |
| `grammar.move_static` | 固定机位 | draft | `src.user_02`、`src.p01_audit`、`src.mem_preloq`、`src.wan3_guide`、`src.camerabench`、`src.sds` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_tilt` | 上摇与下摇 | draft | `src.camerabench`、`src.sds`、`src.p01_audit` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_truck` | 横移 | draft | `src.camerabench`、`src.sds`、`src.p01_audit`、`src.xiakexing_files` | MIT-0、数据集 CC BY 4.0 |
| `grammar.move_zoom` | 变焦推拉 | draft | `src.camerabench`、`src.sds`、`src.wan3_guide`、`src.sd25_guide` | MIT-0、数据集 CC BY 4.0 |
| `grammar.pos_back` | 背面 | draft | `src.film_grammar`、`src.mem_copyright`、`src.mem_guanyin`、`src.mem_preloq` | — |
| `grammar.pos_over_shoulder` | 过肩 | draft | `src.film_grammar`、`src.sds`、`src.mem_copyright`、`src.user_05` | MIT-0 |
| `grammar.pos_pov` | 主观视角 | draft | `src.film_grammar`、`src.sds`、`src.avd` | MIT、MIT-0 |
| `grammar.pos_profile` | 侧面 | draft | `src.film_grammar`、`src.mem_xiakexing` | — |
| `grammar.size_close` | 近景 | draft | `src.film_grammar`、`src.sds`、`src.sd20_guide`、`src.mem_xiakexing`、`src.mem_lanhai` | MIT-0 |
| `grammar.size_closeup` | 特写 | draft | `src.film_grammar`、`src.sds`、`src.p01_audit`、`src.mem_preloq` | MIT-0 |
| `grammar.size_extreme_closeup` | 大特写 | draft | `src.film_grammar`、`src.sds`、`src.p01_audit`、`src.mem_preloq` | MIT-0 |
| `grammar.size_extreme_wide` | 大远景 | draft | `src.film_grammar`、`src.sds`、`src.wan_t2v_guide`、`src.mem_xiakexing`、`src.mem_copyright`、`src.prop_asset` | Apache-2.0、MIT-0 |
| `grammar.size_full` | 全景 | draft | `src.film_grammar`、`src.sds`、`src.wan_t2v_guide` | MIT-0 |
| `grammar.size_medium` | 中景 | draft | `src.film_grammar`、`src.sds`、`src.wan_t2v_guide`、`src.mem_xiakexing` | MIT-0 |
| `grammar.size_medium_close` | 中近景 | draft | `src.film_grammar`、`src.sds`、`src.user_02` | MIT-0 |
| `grammar.size_medium_wide` | 中全景 | draft | `src.film_grammar`、`src.sds`、`src.wan_t2v_guide` | MIT-0 |
| `grammar.size_wide` | 远景 | draft | `src.film_grammar`、`src.sds`、`src.wan_t2v_guide`、`src.mem_xiakexing`、`src.mem_copyright` | MIT-0 |
| `grammar.time_slow_motion` | 慢动作 | draft | `src.wan3_guide`、`src.avd`、`src.p01_audit`、`src.xiakexing_files` | MIT |
| `grammar.time_speed_ramp` | 变速 | draft | `src.avd`、`src.xiakexing_files`、`src.sd25_guide` | MIT |
| `grammar.trans_dissolve` | 叠化 | draft | `src.film_grammar`、`src.avd` | MIT |
| `grammar.trans_eyeline_match` | 视线匹配切 | draft | `src.film_grammar`、`src.avd` | MIT |
| `grammar.trans_fade_black` | 淡入淡出黑场 | draft | `src.film_grammar`、`src.avd`、`src.user_05` | MIT |
| `grammar.trans_hard_cut` | 硬切 | draft | `src.film_grammar`、`src.avd`、`src.wan3_guide`、`src.user_02` | MIT |
| `grammar.trans_j_l_cut` | 声音先行与延后 | draft | `src.film_grammar`、`src.user_02`、`src.user_05` | — |
| `grammar.trans_match_action` | 动作匹配切 | draft | `src.film_grammar`、`src.avd`、`src.user_02` | MIT |
| `grammar.trans_match_graphic` | 图形匹配切 | draft | `src.film_grammar`、`src.avd`、`src.sds` | MIT、MIT-0 |
| `grammar.trans_occlusion_wipe` | 遮挡转场 | draft | `src.film_grammar`、`src.avd`、`src.sd25_guide` | MIT |
| `grammar.trans_smash_cut` | 撞击切 | draft | `src.film_grammar`、`src.avd`、`src.sds` | MIT、MIT-0 |
| `scene.action_insert` | 动作特写 | draft | `src.user_02`、`src.user_05`、`src.p01_audit`、`src.mem_preloq`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.chase` | 追逐 | draft | `src.user_05`、`src.xiakexing_files`、`src.mem_xiakexing`、`src.wan3_guide`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.cliffhanger` | 结尾悬念 | draft | `src.user_02`、`src.p01_audit`、`src.mem_lanhai`、`src.mem_xiakexing`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.comedy` | 喜剧包袱 | draft | `src.mem_xiakexing`、`src.mem_lanhai`、`src.sds`、`src.avd`、`src.film_grammar` | MIT、MIT-0 |
| `scene.confrontation` | 争执对峙 | draft | `src.user_02`、`src.user_05`、`src.plan`、`src.mem_xiakexing`、`src.sd25_guide`、`src.sds`、`src.avd`、`src.film_grammar` | MIT、MIT-0 |
| `scene.dialogue` | 对话 | reviewed | `src.user_02`、`src.user_05`、`src.p01_audit`、`src.mem_preloq`、`src.mem_xiakexing`、`src.mem_lanhai`、`src.mem_robotdog`、`src.mcp_models`、`src.plan`、`src.wan3_guide`、`src.sd25_guide`、`src.sd20_guide`、`src.sds`、`src.avd`、`src.prop_asset`、`src.film_grammar` | Apache-2.0、MIT、MIT-0 |
| `scene.ensemble` | 群戏 | draft | `src.user_05`、`src.mem_xiakexing`、`src.sd20_guide`、`src.sd25_guide`、`src.wan3_guide`、`src.avd`、`src.film_grammar` | MIT |
| `scene.establishing` | 环境建立 | draft | `src.user_02`、`src.user_05`、`src.plan`、`src.wan3_guide`、`src.sd25_guide`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.explainer` | 旁白讲解 | draft | `src.user_02`、`src.user_05`、`src.plan`、`src.p01_audit`、`src.mem_preloq`、`src.film_grammar` | — |
| `scene.fight` | 打斗 | reviewed | `src.user_02`、`src.user_05`、`src.p01_audit`、`src.mem_xiakexing`、`src.mem_copyright`、`src.xiakexing_files`、`src.plan`、`src.wan3_guide`、`src.sd25_guide`、`src.sd20_guide`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.flashback` | 回忆闪回 | draft | `src.user_02`、`src.user_05`、`src.mem_robotdog`、`src.sd20_guide`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.intimate` | 温情亲密 | draft | `src.mem_xiakexing`、`src.wan3_guide`、`src.sds`、`src.film_grammar` | MIT-0 |
| `scene.monologue` | 情感独白 | draft | `src.user_05`、`src.mem_xiakexing`、`src.sd25_guide`、`src.sds`、`src.avd`、`src.film_grammar` | MIT、MIT-0 |
| `scene.montage` | 过场蒙太奇 | draft | `src.user_02`、`src.plan`、`src.xiakexing_files`、`src.wan3_guide`、`src.sd25_guide`、`src.avd`、`src.film_grammar` | MIT |
| `scene.opening_hook` | 开场钩子 | draft | `src.user_02`、`src.plan`、`src.mem_preloq`、`src.mem_copyright`、`src.p01_audit`、`src.film_grammar` | — |
| `scene.reveal` | 悬疑揭示 | draft | `src.user_02`、`src.user_05`、`src.p01_audit`、`src.mcp_models`、`src.avd`、`src.film_grammar` | MIT |
| `scene.spectacle` | 奇观异象 | draft | `src.mem_copyright`、`src.mem_guanyin`、`src.mem_lanhai`、`src.mcp_models`、`src.prop_asset`、`src.wan3_guide`、`src.sd20_guide`、`src.sds`、`src.film_grammar` | Apache-2.0、MIT-0 |
| `scene.tension` | 紧张蓄势 | draft | `src.mem_lanhai`、`src.sd25_guide`、`src.sds`、`src.avd`、`src.film_grammar` | MIT、MIT-0 |
| `scene.twist` | 反转 | draft | `src.user_02`、`src.mem_xiakexing`、`src.sds`、`src.film_grammar` | MIT-0 |
| `provider.seedance20_3d` | Seedance 2.0 · 3D | draft | `src.sd20_guide` | — |
| `provider.seedance20_anime` | Seedance 2.0 · 动漫 | draft | `src.sd20_guide` | — |
| `provider.seedance20_base` | Seedance 2.0 · 通用 | draft | `src.sd20_guide`、`src.user_02` | — |
| `provider.seedance20_realistic` | Seedance 2.0 · 写实 | draft | `src.sd20_guide`、`src.mem_xiakexing` | — |
| `provider.seedance25_3d` | Seedance 2.5 · 3D | draft | `src.sd20_guide`、`src.mem_xiakexing` | — |
| `provider.seedance25_anime` | Seedance 2.5 · 动漫 | draft | `src.mem_lanhai`、`src.mem_xiakexing`、`src.sd20_guide` | — |
| `provider.seedance25_base` | Seedance 2.5 · 通用 | draft | `src.sd25_guide`、`src.mcp_models`、`src.user_02`、`src.user_05`、`src.xiakexing_files`、`src.mem_xiakexing`、`src.mem_copyright`、`src.sds` | MIT-0 |
| `provider.seedance25_realistic` | Seedance 2.5 · 写实 | draft | `src.mem_xiakexing`、`src.mem_lanhai`、`src.mem_copyright` | — |
| `provider.wan30_3d` | 万相 3.0 · 3D | draft | `src.wan3_guide`、`src.wan_t2v_guide` | — |
| `provider.wan30_anime` | 万相 3.0 · 动漫 | draft | `src.wan3_guide`、`src.wan_t2v_guide` | — |
| `provider.wan30_base` | 万相 3.0 · 通用 | draft | `src.wan3_guide`、`src.wan_t2v_guide`、`src.mcp_models`、`src.plan`、`src.user_02`、`src.user_05`、`src.p01_audit`、`src.mem_preloq`、`src.mem_lanhai` | — |
| `provider.wan30_realistic` | 万相 3.0 · 写实 | draft | `src.mem_lanhai`、`src.p01_audit`、`src.mem_preloq`、`src.mem_robotdog`、`src.mem_xiakexing` | — |
| `neg.abstract_emotion` | 抽象情绪词 | draft | `src.user_02`、`src.sd20_guide`、`src.prop_asset`、`src.sds` | Apache-2.0、MIT-0 |
| `neg.bare_english_camera_term` | 裸写 Dolly、Crane、Aerial | draft | `src.user_02`、`src.sds` | MIT-0 |
| `neg.camera_move_rewrites_material` | 运镜改写了材质 | draft | `src.p01_audit`、`src.mem_preloq` | — |
| `neg.cinematic_buzzwords` | 空泛的质感形容词 | draft | `src.prop_asset` | Apache-2.0 |
| `neg.complex_body_contact` | 复杂的身体接触 | draft | `src.sds` | MIT-0 |
| `neg.dialogue_text_in_video_prompt` | 在 video_prompt 里写台词原文 | draft | `src.user_02`、`src.sd25_guide` | — |
| `neg.director_name_as_style` | 用导演名字代替手法 | draft | `src.prop_asset` | Apache-2.0 |
| `neg.emotion_glow_eyes` | 强情绪让眼睛发光 | draft | `src.sd25_guide` | — |
| `neg.frequency_timestamp` | 用时间戳数次数 | draft | `src.wan3_guide`、`src.sd25_guide` | — |
| `neg.ip_lookalike_design` | 造型近似知名 IP | draft | `src.mem_copyright`、`src.mem_preloq` | — |
| `neg.keep_consistent_vague` | 「保持上一镜一致」 | draft | `src.prop_asset`、`src.user_02` | Apache-2.0 |
| `neg.lens_filler` | 没有叙事意义的焦段填充 | draft | `src.user_02` | — |
| `neg.missing_no_text_line` | 漏了「无文字、字幕、水印」 | draft | `src.user_02`、`src.sd20_guide` | — |
| `neg.move_on_sensitive_shot` | 敏感镜头用了运镜 | draft | `src.p01_audit`、`src.mem_xiakexing`、`src.user_02` | — |
| `neg.multiview_reference` | Seedance 2.0 用多视图做人物参考 | draft | `src.sd20_guide`、`src.sd25_guide` | — |
| `neg.music_leaks_native_audio` | 原生音频混进了配乐 | draft | `src.sd25_guide`、`src.xiakexing_files` | — |
| `neg.orbit_structure_interpenetration` | 环绕让零件互相穿插 | draft | `src.p01_audit`、`src.mem_preloq` | — |
| `neg.push_tilt_reveals_face` | 推近接上摇，露出了脸 | draft | `src.p01_audit`、`src.mem_preloq` | — |
| `neg.realistic_face_on_seedance` | 写实露脸首帧交给 Seedance | draft | `src.mem_xiakexing`、`src.mem_lanhai` | — |
| `neg.repeat_static_appearance` | video_prompt 重复首帧外观 | draft | `src.user_02`、`src.wan_t2v_guide`、`src.xiakexing_files` | — |
| `neg.reveal_in_first_frame` | 揭示镜的首帧画出了秘密 | draft | `src.user_05`、`src.mcp_models` | — |
| `neg.short_gen_under_4s` | 生成时长不到 4 秒 | draft | `src.user_02`、`src.mcp_models` | — |
| `neg.stacked_camera_moves` | 一镜叠加多种运镜 | draft | `src.sd20_guide`、`src.sds`、`src.user_02` | MIT-0 |
| `neg.superpower_physics` | 超能力式的物理 | draft | `src.wan3_guide`、`src.sds` | MIT-0 |
| `neg.text_in_generated_frame` | 让模型生成精确文字 | draft | `src.user_02`、`src.sd25_guide`、`src.p01_audit`、`src.mem_preloq` | — |
| `neg.timestamp_seconds_on_seedance20` | 给 Seedance 2.0 写秒数时间戳 | draft | `src.sd20_guide`、`src.sd25_guide` | — |
| `neg.too_many_actions` | 一镜里动作太多 | draft | `src.user_02`、`src.sds` | MIT-0 |
| `neg.vague_camera_move` | 运镜没有方向和起止 | draft | `src.prop_asset`、`src.sds` | Apache-2.0、MIT-0 |
| `neg.voiceover_mouth_moves` | 画外音时角色在张嘴 | draft | `src.sds`、`src.user_05` | MIT-0 |
<!-- END 逐卡表 -->
