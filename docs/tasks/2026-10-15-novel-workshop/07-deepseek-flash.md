# 小说工坊 P0 增补：默认 DeepSeek 型号改为 deepseek-flash

> 作者要求（2026-10-15）：把 DeepSeek 的模型换成 `deepseek-flash`。
> 红线不变：只改 `backend/novel/**`、`backend/tests/test_novel_*.py`、`03-report.md`；不联网、不读密钥、不运行真实提供方、不提交 commit；既有测试的输入和断言不得修改。

## 已核实的事实

- `deepseek-flash` 是 DeepSeek 官方型号 ID，对应 DeepSeek-V4.1-Flash。
- 官方价格（美元/百万 token）：
  - 高峰期：输入（缓存未命中）0.30，输出 1.20
  - 非高峰：输入 0.15，输出 0.60
- 验收方在 2026-10-15 做过一次真实最小探测，以下组合都被接受，返回了合法 JSON：
  - `extra_body={"thinking":{"type":"disabled"}}`
  - `response_format={"type":"json_object"}`

## 任务

1. 三份默认实验配置 `backend/novel/pilot_configs/expA.json`、`expB.json`、`expC.json` 中，所有 `deepseek:deepseek-v4-pro` 一律改为 `deepseek:deepseek-flash`（目前用于写手和人物代言人）。**先全库搜索 `deepseek-v4-pro`**，`backend/novel/` 下的 README、提示文本和示例里如果出现，也要同步改掉，并写明改动原因；`docs/tasks/.../02-spec.md` 是历史规格，保留不动。
2. `deepseek` 提供方仍然**不设型号白名单**，`deepseek-v4-pro` 继续可选，只是不再作为默认值。
3. 新增一条测试：断言三份默认配置中没有出现 `deepseek-v4-pro`，并且写手是 `deepseek:deepseek-flash`。
4. 用 MockTransport 写一条离线测试：`deepseek:deepseek-flash` 的请求体中带有 `thinking={"type":"disabled"}`；输出 json 的角色还要带上 `response_format`。

## 验收

1. `tests/test_novel_*.py` 全部通过，全量测试没有新增失败。
2. 三个默认配置的 dry-run 都以退出码 0 结束。
3. `grep -rn "deepseek-v4-pro" backend/novel/pilot_configs` 没有任何输出。
4. `git status --porcelain` 中没有 `M` 状态的文件。
5. 在 03-report.md 末尾追加「默认 DeepSeek 改为 flash」一节。
