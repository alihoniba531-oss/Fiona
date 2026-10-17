# 豆包语音：情绪与表现力控制调研（2026-10-17）

来源仅限火山引擎官方文档 `volcengine.com/docs/6561/*`。页面为前端渲染，内容经文档站内容接口（`/api/doc/getDocDetail`）读取。未调用付费接口，未使用密钥。
- [A] 单向流式 HTTP（现行，2026-09-29）https://www.volcengine.com/docs/6561/2528925
- [B] HTTP Chunked/SSE V3（历史，2026-05-25）https://www.volcengine.com/docs/6561/1598757
- [C] 音色列表 https://www.volcengine.com/docs/6561/1257544 ；[D] 语音指令与标签 https://www.volcengine.com/docs/6561/1871062
- [E] 复刻2.0最佳实践 https://www.volcengine.com/docs/6561/2298705 ；[F] SSML https://www.volcengine.com/docs/6561/1330194
- [G] 音频生成 https://www.volcengine.com/docs/6561/2550782 ；[H] 模型列表 https://www.volcengine.com/docs/6561/2499930 ；[I] 计费 https://www.volcengine.com/docs/6561/1359370

## 1. TTS 2.0（seed-tts-2.0）情绪与表现力
**结论：2.0 的情绪控制靠自然语言指令 `context_texts`，不靠 `emotion`。**
- 指令字段 `req_params.additions.context_texts`：字符串数组，取值为一句自然语言，官方示例 `["你可以用特别特别痛心的语气说话吗?"]`。仅 2.0 音色支持，该文本不计费。[A][B]
  - 官方可调维度：语速、情绪/语气、音量、音感（例 `"嗯，你的语气再欢乐一点"`、`"你能用骄傲的语气来说话吗？"`）。[B]
  - 只有数组第一个值有效。[B] 单条建议只写一句话。
  - 官方指令示例库：`用颤抖沙哑、带着崩溃与绝望的哭腔，夹杂着质问与心碎的语气说`、`用asmr的语气`、`用吵架的语气`。控制台里写作 `[#指令]`，API 里是否要加 `[#]` 未查到，待实测。[D]
  - 「引用上文」：把上一句对白传入，模型承接语境情绪。文档只在复刻2.0最佳实践里说明可用 `context_texts` 传上文 query。[E] TTS2.0 是否同样适用待实测。
- **关键坑**：`additions` 的类型是 string，必须传 JSON 序列化后的字符串，不能传对象。[A]
- `speech_rate` / `loudness_rate`：在 `req_params.audio_params` 下，int，范围 [-50,100]，默认 0，100=2.0倍，-50=0.5倍。[A]
- 音高：`req_params.additions.post_process.pitch`，int，范围 [-12,12]，默认 0。[A]
- 句尾静音：`additions.silence_duration`，0~30000ms，仅作用于全文末尾，不是每句。[A][B]
- `section_id`（`additions` 下，string）：用同一 ID 串联多次合成，保持跨请求语义。仅 2.0 音色，轮数和超时有限制。[A][B] 对连续台词的情绪连贯可能有用，待实测。
- **`emotion` / `emotion_scale`**：只在历史文档 [B] 的 `audio_params` 下出现（`emotion_scale` 范围 1~5，默认 4）。该文档称仅部分音色支持。取值表只列在 1.0 多情感音色（`*_emo_v2_mars_bigtts`，如 happy/sad/angry/fear/excited 等）。[C]
  - 现行文档 [A] 已删除这两个字段，2.0 音色表无情感列。**`*_uranus_bigtts` 是否支持：未查到，视为不支持，待实测（可能被忽略）。**
- 哪些 2.0 音色支持指令：音色表首张 2.0 表中 93 个 `*_uranus_bigtts` 均标注「指令遵循」，`zh_female_sophie_uranus_bigtts`（魅力苏菲 2.0）已标注。[C]
  - 外语 2.0 音色另分 QA（指令遵循）与 Context（上下文遵循，仅单向流）两种模式。[C]
- SSML：现行文档称 2.0 中英文音色支持 `req_params.ssml`，需 `disable_markdown_filter=false`；历史文档称 2.0 暂不支持，**两份文档矛盾，待实测**。[A][B]
  - 通用 SSML 标签只有 speak / phoneme / say-as / sub / break(time) / soundEvent，其中 soundEvent 不适用 2.0。没有情感或韵律标签，只有 `<break>` 能帮到停顿。[F]
- 语音标签 `<cot text=急促难耐>…</cot>`（`additions.use_tag_parser=true`）：仅出现在历史文档 [B]，且仅限复刻2.0「表现力增强版」，单句建议少于 64 字。现行文档未列，不建议依赖。
- 最小请求体（语音指令）：
```json
{"user":{"uid":"u1"},"req_params":{"text":"你怎么现在才来……我等了你一整晚。","speaker":"zh_female_sophie_uranus_bigtts","audio_params":{"format":"mp3","sample_rate":24000,"speech_rate":-10},"additions":"{\"context_texts\":[\"用压低声音、带着委屈和一点哽咽的语气说\"],\"post_process\":{\"pitch\":-1}}"}}
```
- Header 不变：`X-Api-Key` 加 `X-Api-Resource-Id: seed-tts-2.0`。[A]

## 2. 音频生成 1.0（Seed-Audio，seed-audio-1.0）
- 端点：`POST https://openspeech.bytedance.com/api/v3/tts/create`，非流式 HTTP，官方样例超时 300s。[G]
- 请求头：只列了 `X-Api-Key`、`X-Api-Request-Id`。**文档没有 `X-Api-Resource-Id`，样例也不带，未查到其取值。** 模型由请求体 `model` 选择。[G]
- 请求体：`model`；`text_prompt`（≤3000 字符，既是提示词也是待合成文本）；`references[]`；`audio_config`；`watermark`。[G]
  - `references[]` 元素：`speaker`（TTS2.0 音色或复刻音色）、`audio_data`、`audio_url`，三者互斥；`image_data`、`image_url`（图片不能和音频或 speaker 混用）。
  - 参考音频最多 3 条，每条 ≤30s、≤10MB，在提示词里用 `@音频1` 引用。
  - `audio_config`：format（默认 wav）、sample_rate、`speech_rate` / `loudness_rate`（[-50,100]）、`pitch_rate`（[-12,12]）、enable_subtitle。
- **能否指定说话人并描述表演：能。** 用 `references[0].speaker` 指定音色，用 `text_prompt` 自然语言描述。官方样例提示词包含 BGM、环境音、音效，以及「男子1（中青年男性，台湾口音，嗓音低沉，浑厚）用严肃语气说道：“……”」这类角色、口音、语气描述。[G]
  - 另支持用提示词控制总时长和说话时间段。[G]
  - 指定 speaker 后，提示词里的表演描述是否照样生效：文档未明说，**待实测**。
- 限制：单次最长 120s；[H] 建议单次人声文本 ≤400 字符，过长会被加快语速；SSML 不支持。
  - 语种：[G] 列 18 种，[H] 写中英文并「可演绎方言口音但不支持纯方言」，两处不一致，中文场景无影响。
- 响应：`audio`（base64）、`duration`、`original_duration`、`url`（2 小时有效）、`subtitle`。[G]
- **计费**：按模型生成的原始时长 `original_duration` 计费，倍速不影响。后付费 1 元/分钟，预付费资源包折算 0.9~1 元/分钟。默认 5 并发。[I]
- 文档另提到「Seed Audio 1.5」营销计划（https://www.volcengine.com/docs/6561/2697433），API 文档未查到，暂不考虑。

## 3. 声音复刻 2.0（seed-icl-2.0）
- 流程：注册 `POST /api/v3/tts/voice_clone`，查状态 `POST /api/v3/tts/get_voice`（status=2 或 4 可用，2.0 的 model_type=5）。V1 旧音色用 `/api/v3/tts/upgrade_voice` 升级。[J] https://www.volcengine.com/docs/6561/2534906 ；https://www.volcengine.com/docs/6561/2535742 ；https://www.volcengine.com/docs/6561/2535751
- 合成：同 TTS 的单向流式接口，`X-Api-Resource-Id: seed-icl-2.0`，`speaker` 填复刻音色 ID。[A]
- 样本要求：wav/mp3/ogg/m4a/aac/pcm（pcm 仅 24k 单声道），≤10MB；推荐 14~30s 的 wav，单人、低噪、单轨。可选传参考文本 `text`，与音频差异过大会失败（45001109 WERError）。[J][E]
  - 情绪要求：整段情绪尽量一致、不要大起伏，语气语速贴合场景；中英混用的话样本最好两种都覆盖。[E]
- **风格和情绪能否复刻：只能部分复刻。** 官方称 2.0「不完全贴合 prompt 情感，更侧重语义」。要既保留音色又要情感，建议再加 `context_texts`（例 `["用最悲伤的语气演绎下面这句话："]`）。[E]
  - `additions.tone_fidelity=true`（还原模式）会尽量还原样本的音色和说话风格（情感、韵律、口音），仅限同语种，不支持双向流。[A]
  - 情感平稳的样本合成更稳；情感丰富的样本，同一文本多次合成情感会有变化。[E]
- `req_params.model`（`seed-tts-2.0-standard` / `-expressive`）：历史文档称 expressive 才支持指令和 cot；现行文档称指定 model 后不支持 `context_texts`，**两处矛盾，待实测**。[A][B]
- 成本：3 元/万字符，另有音色槽位费 138 元/音色（后付费音色首次合成时收取）。[I]

## 4. 建议（按「人味」收益排序，均待实测验证）
1. 先试 TTS 2.0 + `additions.context_texts`：成本最低（3 元/万字符，指令不计费），音色不变，逐句写情绪指令。
2. 再试 Seed-Audio `text_prompt` + `references[0].speaker`：可把角色、语气、环境音写进同一段提示词，但按 1 元/分钟计费，且指定音色后表演描述是否生效未知。
3. 辅助手段：`audio_params.speech_rate`（可小幅为负）、`additions.post_process.pitch`、文本里用省略号或 SSML `<break>` 制造停顿；复刻路线用 `tone_fidelity`。
