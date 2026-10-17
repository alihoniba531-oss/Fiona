# WO3d 补丁 P2（豆包语音 2.0 + 表演指示）独立复核

- 范围：快照 22742428 到 ffd141b8 的差异；工作区与后一快照一致（已核对）。
- 结论：**通过**。必须修复 0 项，可优化 10 项。

## 已实测

- 全部 `-k studio` 测试通过（无 skip）；`tsc --noEmit --incremental false` 与 eslint 对 VoicePanel.tsx、studio-casting.ts 均为 0 error。
- 在 `$TMPDIR` 用 MockTransport 写了约 60 个适配器用例，未联网。
  - 成功流、各 HTTP 状态码、响应体 code、中途断流、总超时、缺 Key 全部一次 POST（缺 Key 为 0 次）。
  - 4xx（400/401/403/408/429/499）为 rejected。
  - 5xx、3xx、传输错误、超时、无 20000000、成功码无音频、坏 JSON、坏 base64 均为 uncertain。
  - HTTP 200 且响应体 code 为 45xxxxxx 为 rejected。
  - 持续滴流超过总超时时，0.60 秒内中止，落 `doubao_timeout`。
- 请求体：`additions` 是 JSON 字符串。
  - `context_texts` 与 `post_process.pitch` 字段名与规格 §2 一致。
  - pitch 为 0 且指示为空时不写 `additions`；只有其一时只写对应字段。
  - rate 0.5/1/2/0.3/3/1.234 分别得到 -50/0/100/-50/100/23。
- Key：响应体或消息里回显 Key 一律替换为「[已隐藏]」；缺 Key 的 503 在入库与派发之前返回（API 与集成测试均断言付费调用数为 0）。
- 旧数据：`spec_json.voice` 与旧试听没有 direction/baseline 时，后端原样透传，GET 不报错；前端用 `?.` 读取，不崩。
- 文档：4 个文档中的三个环境变量名、默认值（`seed-tts-2.0`、3.0）和 Key 获取方式与代码一致。

## 必须修复

无。

## 可优化（均不阻塞）

1. `providers/tts_doubao.py:55-61,126-127,149-150`：uncertain 的错误信息用上游原文，上游无说明时变成「上游未提供错误说明」，而不是 cosy/edge/seedream 统一的 `UNCERTAIN_MESSAGE`（「可能已扣费，请勿直接重试」）。`or UNCERTAIN_MESSAGE` 的兜底永远不会触发，因为 `safe_message` 不会返回空串。前端只在图片任务上补了「可能已扣费」标签。
2. `providers/tts_doubao.py:124-127,147`：`error_code` 直接拼接上游 `code` 字符串，既不脱敏也不限长。实测非数字 code 带 Key 与 3000 字符的 code 都会原样落库（真实上游不太可能）。建议只接受纯数字 code，其余写 `upstream_error`。
3. `providers/tts_doubao.py:174,212-215,237` 与 `casting_jobs.py:497`：发送前的参数错误被归为 uncertain，会占着预留并提示「可能已扣费」，实际 POST 为 0 次。实测 rate 非数字或 NaN 得到 `doubao_error`（uncertain，posts=0），`ValueError` 经 `_classify` 得到 `media_error`（uncertain）。API 层已校验，仅脏数据可达。建议改为 rejected。
4. `providers/tts_doubao.py:194-199`：已收到音频块之后才出现 45xxxxxx，也按规格记 rejected 并释放预留。规格如此，可考虑已有音频时保守记 uncertain。
5. `studio-casting.ts:139-142` 与 `VoicePanel.tsx:217`：试听费用标签不看所选引擎，也不乘方案数。
   - 中文项目一律按豆包价，包括选了 CosyVoice 或 edge-tts 时。
   - 英文项目一律显示「免费」，包括手选豆包时（后端会预留）。
   - 多个方案不累加。
6. `VoicePanel.tsx:132-133`：`mutate` 内部吞掉错误，所以 `setPendingBaseline(null)` 总会执行，approve 失败（如 422/409）时基调输入与弹层一起丢失。另外 `casting.py:1081` 把空串当作未传，用户无法把基调清空，只会回落到指示。
7. `VoicePanel.tsx:228`：已定档那条的「选定这条」被禁用，所以已定档声线的基调只能通过先改选别条再选回来才能修改。非豆包试听（指示为空）也会弹出基调框，对 WO4 没有意义。
8. `studio-casting.ts:109-110`（既有缺口，P2 放大）：界面只显示 image 与 brain 任务，tts 任务的 rejected/uncertain 没有任何提示，uncertain 的 tts 也没有释放入口。豆包成为默认引擎后，Key 无效（401/403）这类首次配置错误会静默失败。
9. `studio-casting.ts:32`：`CastingVoiceSpec.direction/baseline` 声明为必有的 `string | null`，旧数据运行时实际是 undefined。当前因 `?.` 不崩，但类型应写成可选。
10. `docs/ARCHITECTURE.md:441`：写的是「豆包/CosyVoice/edge-tts 共用默认 2 的 TTS 配额」，实际 `casting_jobs.py:219-224` 按 `media_provider` 各建一个信号量，三个引擎各自上限为 2。

## 备注

- `VoiceVariantBody.direction` 的 `max_length=200` 在去空白之前生效，首尾带空白的 201 字会被 422，而去空白后只有 200 字（`routers/studio.py:276`）。影响极小，未单列。
- 本次复核只读，未改动任何代码或测试；探测脚本在 scratchpad 目录。
