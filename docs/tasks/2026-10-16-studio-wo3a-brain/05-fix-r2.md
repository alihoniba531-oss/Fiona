# WO3a 返修单 R2（真实评测后的小修）

背景见 `06-eval.md`：作者账号下没有 `qwen-vl-max` 这个模型；用 `qwen3-vl-plus` 实测看图质检成功。

约束不变：不联网，不新增依赖，不提交，不改非工作室的测试，派子代理时不要传 model 和 reasoning_effort。

**R2-1 视觉模型可配置**
- 新增配置 `FIONA_STUDIO_VISION_MODEL`，默认 `qwen3-vl-plus`，每次调用时读取。
- 合法值为空，或匹配 `^[a-z0-9][a-z0-9.\-]{1,63}$`；非法值回落默认，并且只告警一次。
- `brain.py` 中所有写死的 `qwen-vl-max`（千问和 DeepSeek 的看图路由、`QwenProvider` 的模型白名单）都改为读取这个配置。
- `VISION_WARNING` 文案改为「看图由千问视觉（{实际模型}）完成」。
- `/studio/brain/providers` 里的 `vision_via` 显示实际模型。

**R2-2 价目表**
- `pricing.py` 新增 `qwen3-vl-plus`，单价暂按 ¥1 / ¥10（每百万 token），注释标「待核实」，允许用环境变量覆盖。
- `qwen-vl-max` 那一条保留，以兼容旧的 job 记录。
- 视觉模型不在价目表里时：拒绝调用，返回 409，提示需要配置单价。

**R2-3 评测脚本**
`scripts/studio_brain_eval.py` 的看图任务也读取 `FIONA_STUDIO_VISION_MODEL`；报告里注明实际使用的视觉模型。

**R2-4 文档**
- `CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`、`backend/.env.example` 里提到 `qwen-vl-max` 作为工作室视觉模型的地方全部更新，全库搜索后逐处修改。
- **不要改** Fiona 聊天看图的相关代码和文档（`services/chat_service.py` 等），那是单独的任务。

**R2-5 测试**
- 默认值为 `qwen3-vl-plus`；可以被覆盖；非法值回落默认。
- DeepSeek 看图时，实际请求体里的 model 是配置的视觉模型。
- 价目缺失时返回 409，并且发出 0 个请求。
- 原有的工作室测试中，凡是断言 `qwen-vl-max` 的，改为断言读取配置的结果。

完成后：
- 跑工作室测试和全量测试，**不带 deselect**；沙箱限制导致的失败如实列出。
- 前端如有改动，跑 lint 和 tsc。
- 在 `03-report.md` 里追加「R2」一节。
