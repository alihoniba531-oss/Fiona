# WO3a 复核记录（第 2 轮，只核 R1-A～R1-H）

- 返修模型：GPT-6.1-Sol（ultra）。
- 机械验证（主控在沙箱外执行）：
  - 后端全量：**6166 passed，0 failed，0 skipped**。
  - 前端：lint 0 个错误（另有 25 条警告，与基线相同）；tsc 通过；build 通过。
- 复核（Fable）：`tests/test_studio_*.py` 加上 `tests/test_byok*.py`，1535 passed。复核另用真实 Provider 类配合假 SDK 做了独立探针，覆盖截断、拒答、超时三种情况。

## 结论：通过

| 项 | 结论 | 证据 |
|---|---|---|
| R1-A 截断不修正 | 通过 | `brain_jobs.py:308-312`；三家各只发 1 次请求，按实际 usage 结算 |
| R1-B Claude 超时公式 | 通过 | `brain.py:181-183`：max_tokens 为 1 时 300 秒，12000 时 398 秒，128000 时 600 秒；千问 / DeepSeek ≥120 秒；`max_retries=0` |
| R1-C 拒答、空内容、内容过滤记为 failed 并按实际结算 | 通过 | `brain.py:327-347,415-417`、`brain_jobs.py:284-290`；没有 usage 的损坏响应仍记 uncertain |
| R1-D 缓存写入按 1.25 倍计价，按 reply.model 定价 | 通过 | `pricing.py:230`、`brain_jobs.py:293-295`；fallback 到价目表外的模型时，按预留金额结算并给出警告 |
| R1-E 修正报价上限 | 通过 | `pricing.py:203-207`：输入 token 上限 = 输入字符数 × 1.5 + 上次的 max_tokens + 2048 |
| R1-F schema 不支持的形态显式报错 | 通过 | `brain_schema.py:24-112` |
| R1-G 判断可用性时不解密 Key | 通过 | `get_public_status` 只读密文结构；`_public` / `get_public_config` 的行为与 91eb53d 逐字一致 |
| R1-H 只更新工作室自己的测试 | 通过 | 只改了 `test_studio_api.py` 的 caps 断言 |

## 新发现
无。

## 留待后续
- 真实 Key 评测：三家实际价格、`qwen-vl-max` 能否调通。等作者批准费用后，用 `scripts/studio_brain_eval.py` 执行。
- `run_brain` 不绑定项目时会新建项目的问题，到 WO3c / WO4 改为传入 project_id。
