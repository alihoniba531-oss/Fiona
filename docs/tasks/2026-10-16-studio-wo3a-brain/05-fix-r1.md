# WO3a 返修单 R1

约束不变：不联网，不新增依赖，不改令牌，不提交，派子代理时不要传 model 和 reasoning_effort。逐条修复，每条都要有离线测试。

**R1-A 截断时不再修正**
- 在 `_execute_brain` 里，回复的 `stop_reason` 属于 `{"max_tokens","length"}`（Claude 的 `max_tokens`、OpenAI 兼容接口的 `length`）时，**不进入修正**。
- 按实际 usage 结算，状态记为 `invalid_output`，`error_code="max_tokens"`。
- 中文提示：「输出超长被截断，请缩短素材或减少勾选的任务」。
- 补测试：三家各测一遍，断言只调用 1 次、结算金额等于实际 usage、错误码正确。

**R1-B Claude 超时**
- Claude 的超时按任务计算：`max(300, ceil(3600 * max_tokens / 128000) + 60)` 秒，上限 600 秒。千问和 DeepSeek 不变，仍然 ≥120 秒。
- 前端在任务运行期间显示「长任务可能需要数分钟」，状态说明里加上即可，不改视觉。
- 更新测试：Claude 断言超时不小于上述公式算出的值，并且 SDK 客户端仍然是 `max_retries=0`。

**R1-C 拒答和空内容按 failed 结算**
- Claude 回复 `stop_reason=="refusal"`，或者响应完整、带 usage、但没有 text 块时：抛出 `BrainProviderError("failed","refusal"或"empty_output",…)`，并附上 usage。
- `_execute_brain` 对带 usage 的这类错误，按 `brain_actual_cost` 结算，释放多余的预留，不记为 uncertain。
- 中文提示：
  - 拒答：「导演模型拒绝了这次请求（类别：{stop_details.category 中文}），可换一家或调整素材」。
  - 空内容：「导演模型没有返回内容」。
- 千问和 DeepSeek：遇到 `finish_reason=="content_filter"` 时按同样方式处理（failed，按 usage 结算）。
- 补测试。

**R1-D 结算精度**
- 缓存写入（`cache_creation_input_tokens`）按基础输入价的 1.25 倍结算。缓存读取继续按缓存价。
- 服务端 fallback 之后，按回复里的实际模型（`reply.model`）定价。如果这个模型不在价目表里，就按预留金额（最坏情况）结算，并记一条 warning「fallback 模型单价未配置，按预留计」。
- 补测试。

**R1-E 修正报价上限**
修正调用的输入上限 = 原始输入估算 + 上一次的 `max_tokens`（截断输出的上限）+ 修正提示词的固定开销；输出上限 = `max_tokens`。不要再用 `max_tokens * 8` 来估。这样报价上限会降下来，同时保证仍然不低于真实的最坏情况。补测试：断言报价上限的数值。

**R1-F schema 转换显式报错**
`to_claude_schema` 遇到以下情况时显式抛出 `UnsupportedSchema`，并说明是哪个位置：
- `additionalProperties` 是一个 schema（而不是布尔值）；
- `format` 的值不是字符串；
- 递归引用。

`brain_tasks.py` 里的现有任务 schema 都必须能通过转换。补测试。

**R1-G 可用性判断不解密 Key**
`provider_options` / `GET /studio/brain/providers` 只看 BYOK 的公开状态字段（`_public` 的 status 和 provider）来判断是否可用，不解密 Key。真正调用时再解密。补测试：用 monkeypatch 断言查询可用性时没有调用解密函数。

**R1-H 更新工作室自己的旧测试**
更新 `tests/test_studio_api.py:103` 对 caps 的精确断言，加入 `brain_monthly_usd` 和 `brain_month_used_usd`。这是 WO1 写的工作室测试，可以改；**非工作室的测试仍然一律不改**。

完成后：
- 跑工作室测试和全量测试，**不带 deselect**；沙箱限制导致的失败如实列出。
- 前端跑 lint、tsc、build。
- 把结果追加到 `03-report.md` 的「R1」一节，逐条对应 R1-A 到 R1-H。
