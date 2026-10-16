# WO3a 复核记录（第 1 轮）

- 执行模型：GPT-6.1-Sol（ultra）。复核：全新上下文的 Fable。
- 机械验证（主控在沙箱外执行）：
  - 后端全量：6073 passed，1 failed。失败的是 `test_studio_api.py:103`：它对 caps 做了精确的字典断言，与本期新增的字段冲突，属已知问题，本轮一并更新。
  - 前端：lint 0 个错误（另有 25 条警告，与基线相同）；tsc 通过；build 通过。

## 结论：不通过（3 项必须修复）

核验成立的部分：
- 付费请求只发一次：三家 SDK 都设了 `max_retries=0`；故障分类正确；预留额度的保留与释放正确。
- 修正请求最多一次，单独记账。
- 重启恢复时不会重发。
- 价目表与规格一致，按上海时间统计的月上限和日上限在 `DEV_MODE` 下照样生效；trial 接口任一检查失败就返回 409，一个 job 都不建。
- 不做降级；DeepSeek 看图时明确交给 qwen-vl-max，并在结果里注明。
- Claude 请求体正确：模型取自 BYOK 配置，用 json_schema 加 effort，没有 thinking，没有预填充，带 fallbacks 和 cache_control。
- schema 转换只删除 schema 位置上的约束，业务字段名原样保留。
- 原文按不可信数据处理，日志里不出现原文、提示词和输出，接口不返回任何 Key。
- brain 任务与 i2v 任务隔离（凡是处理 i2v 的地方都按 `kind='i2v'` 过滤）。
- WO2 的 9 项打磨每项都有测试。
- 前端：先报价，再弹对话框确认，确认后才发请求；「改用」按钮只发 PATCH。

## 必须修复
A. **输出被 max_tokens 截断时，仍然会付费请求一次修正，而且注定再失败**（`brain_jobs.py:305-329`）。
B. **Claude 非流式请求的超时是 120 秒**（`brain.py:278-281`），短于 SDK 对长输出的预期耗时（12000 token 约 337 秒）。服务端完成并全额计费时，客户端已经超时，结果被记成 uncertain。
C. **2xx 响应带 `stop_reason=refusal` 或 content 为空时，被记成了 uncertain**（`brain.py:293-294`）。这种响应是完整的，费用可以确定，应当按 failed 记账，并按实际用量结算。

## 可优化（本轮一并修）
- 缓存写入应按基础输入价的 1.25 倍结算（`pricing.py:339-341`）。
- 服务端 fallback 之后，应按 `reply.model` 定价。
- 修正请求的报价上限过于保守（`brain_jobs.py:62-66`）。
- `to_claude_schema` 遇到不支持的形态时，应当显式报错，而不是静默改写或在运行时抛 TypeError。
- `provider_options` 只是判断可用性，不应每次都解密 Key。

## 留待后续 WO
- `run_brain` 在没有绑定 job 时，每次都会新建一个「导演模型」项目（`brain_jobs.py:268`）。WO3c / WO4 改为传入 project_id。
- 需要真实 Key 才能核实的两项：qwen-vl-max 能否调通，以及三家的实际价格。
