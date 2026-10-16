# WO0 复核记录（第 1 轮）

- 复核方式：全新上下文的独立代理（Fable），输入只有 02-spec.md、改动的代码和参考实现。
- 机械验证（主控在沙箱外执行）：
  - 定向测试 160 passed。
  - 全量 5237 passed / 17 skipped / 0 failed。基线是 5094 passed，差值正好是新增的 160 个。17 个跳过都是因为 worktree 里没有前端 `node_modules`，属于环境原因。
  - 断网沙箱里跑 `plan`，退出码 0；不带 `--yes-spend` 的 `wan` 退出码 2，没有任何请求；输出中没有任何 Key 的值。

## 结论：不通过

付费安全合格：只发 1 次、不重试、`--yes-spend` 门槛、下载规则都已核实。有 2 项必须修复。

## 必须修复
1. **`DASHSCOPE_WORKSPACE_ID` 写进了夹具和 report.jsonl。** `Runtime.secrets` 只收集 `*_KEY` 变量（`_studio_probe_common.py:137`），而工作空间 ID 被拼进了请求 URL 的 host（`_studio_probe_media.py:88`），随后由 `post_json` 原样存进 `request.url`。
2. **Claude 结构化输出的 schema 里有 API 不支持的关键字。** `minItems`、`maxItems`、`minLength`、`minimum`、`exclusiveMinimum` 被直接塞进 `output_config.format.schema`（`_studio_probe_brain.py:54-64,412`），真实调用大概率返回 400。

## 可优化（主控决定本轮一并修，因为都会影响真实付费运行）
3. Claude 分支没有设 `effort`。思考 token 会占用 max_tokens 的额度，可能截断输出却照样扣费。另外应单独记录 `stop_reason`。
4. SDK 在 2xx 响应上抛出的异常（如 APIResponseValidationError）被判成 rejected。实际上请求已经计费，应改判为 uncertain。
5. `redact()` 会把长英文句子误判成 base64，把上游的英文报错吞掉。
6. `quoted` / `plan` 也写了夹具，应该只在拿到上游响应时才写。另外要删掉烟测留下的 2 个夹具文件。
7. breakdown 没有「累计实际花费超过报价上限就停」的硬闸。
8. 万相首帧没有预检：透明通道、边长 240–8000、大小 ≤20MB。

保持不变：完整 5xx 响应按规格 §5.1 标为 rejected。第 1 期起，正式任务表里一律改判 uncertain（按计划从严）。
