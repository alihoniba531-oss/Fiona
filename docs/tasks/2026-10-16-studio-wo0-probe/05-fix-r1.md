# WO0 返修单 R1

仍然遵守 02-spec.md 的全部约束：不联网、不改业务代码、不提交、只改本任务的文件。逐条修复下面各项，每条都配上离线测试。

**R1-1 工作空间 ID 脱敏**
- 让 `Runtime.secrets` 也收集 `DASHSCOPE_WORKSPACE_ID`。先 strip，长度 ≥8 才参与替换；替换范围包括 URL 的 host 部分。
- 在 wan 的成功流程测试里断言：`ENV["DASHSCOPE_WORKSPACE_ID"]` 不出现在夹具、report.jsonl、report.md、stdout 和 stderr 里。
- seedance、seedream 等其他流程也补一条同样的断言，检查全部 6 个变量。

**R1-2 Claude 结构化输出 schema 兼容**
- 新增 `_api_schema(schema)`：先深拷贝，再递归删除 `minItems`（值为 0 或 1 时保留）、`maxItems`、`uniqueItems`、`minLength`、`maxLength`、`minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum`、`pattern`、`format`。被删的约束以「约束：key=value」的文字追加到同一层的 `description`。
- 只有发给 Claude 的 `output_config` 用 `_api_schema` 的结果；本地的 `validate_output` 继续用完整 schema 校验。
- 修改 `test_director_sdk_request_contract`：断言发出去的 schema 里不含上述关键字，并且 description 里含有「minItems=10」。

**R1-3 Claude 思考额度与截断**
- Claude 分支在 `output_config` 里加 `"effort": "low"`，写法参照 `backend/services/local_watch.py` 或 `backend/byok/` 中设置 effort 的方式。如果当前 SDK 版本不接受这个字段，就改用 SDK 支持的等价方式关闭或降低思考，并在总结里写明。
- 所有导演模型的调用，都把 `stop_reason` / `finish_reason` 记进 record。
- 遇到 `max_tokens` 或 `length` 截断时，状态记为 `succeeded_truncated`，并在报告里标明「已计费、输出被截断」。不自动再请求一次。

**R1-4 2xx 上的 SDK 异常判为 uncertain**
- 在 `paid_call` 里，异常带的 HTTP 状态如果是 2xx（如 APIResponseValidationError），判为 `uncertain`（退出码 4，附「可能已扣费」提示），不判 `rejected`。
- 补一条测试。

**R1-5 脱敏不误伤长英文**
- base64 判定改为：不含空白，并且 base64 字符集占比 ≥0.95；或者以 `data:` 开头。
- 补测试：一条 300 字、带空格的英文报错原样保留；真正的 base64 和 data URI 照旧替换。

**R1-6 夹具只在有上游响应时写**
- `quoted`、`plan`，以及没发出请求就失败的情况，只写 report，不写夹具。
- 删除已经存在的 `backend/tests/fixtures/studio/` 下所有烟测文件。如果目录变空，保留一个 `.gitkeep`。
- 补测试。

**R1-7 breakdown 的花费硬闸**
- map 阶段每完成一块，就把实际 usage 折算成金额累加。
- 累计金额超过本次 `--yes-spend` 时，停止派发剩余的块，也不执行 reduce，状态记为 `stopped_budget`，报告里写明已花费金额和未处理的块数。
- 补测试：模拟 usage 偏大，验证会提前停下，并且发出的请求数正确。

**R1-8 万相首帧预检**
- 发请求前检查首帧：PNG 有透明通道就拒绝，或先提示「请先去除透明」；边长在 240–8000 之间；文件 ≤20MB。不合格时直接退出码 2，不发请求。
- 补测试。

完成后：
- 在 `backend/` 下用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_probe.py` 跑通。
- 按 02-spec.md 第 8 节的五项格式输出变更总结，逐条对应 R1-1 到 R1-8。
