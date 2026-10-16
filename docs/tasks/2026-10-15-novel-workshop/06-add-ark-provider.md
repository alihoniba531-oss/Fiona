# 小说工坊 P0 增补：接入火山方舟（豆包 Doubao-Seed-2.1-pro）

> 作者要求：把火山方舟的 **Doubao-Seed-2.1-pro** 加入平台的可选模型，客户可以把它分配给任意智能体。
> 本单是对 `02-spec.md` 和 `05-fix-r1.md` 的增量。红线不变：
> - 只改 `backend/novel/**`、`backend/tests/test_novel_*.py`、`03-report.md`，不改任何既有文件。
> - 不联网，不读密钥，不运行真实提供方，不提交 commit。
> - 不改既有测试的输入和断言；本单明确要求更新的除外。

## 已核实的事实（来源：火山方舟官方文档，2026-10-15 查阅）

- **接口**：与 OpenAI 兼容的 Chat Completions，`base_url = https://ark.cn-beijing.volces.com/api/v3`。
- **型号 ID**：
  - `doubao-seed-2-1-pro-260915`：推荐，上下文 1024k，最大输出 256k，**默认最大输出只有 4k**，所以必须显式传 `max_tokens`。
  - `doubao-seed-2-1-pro-260628`：往期版本，上下文 256k。
- **关闭深度思考**：请求体带 `"thinking": {"type": "disabled"}`，用 OpenAI SDK 时通过 `extra_body` 传入。两个型号都支持 `enabled` 和 `disabled`，默认值是 enabled。
- **结构化输出（beta）**：
  - 支持 `response_format={"type":"json_object"}`，要求输入里出现 json 字样（现有提示词已满足）。
  - 可以和关闭思考同时使用。
  - 不要同时传 `frequency_penalty` 或 `presence_penalty`。
- **用量字段**：OpenAI 兼容格式，即 `usage.prompt_tokens`、`usage.completion_tokens`，缓存命中在 `prompt_tokens_details.cached_tokens`。
- **价格**（在线推理，元/百万 token，只做参考，**代码里不得内置**）：输入 6.00，缓存命中 1.20，输出 30.00。
- **密钥环境变量**：`ARK_API_KEY`，Fiona 现有生图功能也用这个变量名。

## 任务

1. **新增提供方 `ark`**（llm_router.py）：
   - `PROVIDERS["ark"] = ("https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY")`。
   - 请求走 openai 兼容分支：
     - `extra_body={"thinking": {"type": "disabled"}}`。
     - json 输出时传 `response_format={"type":"json_object"}`。
     - 继续使用 `timeout=300`、`max_retries=0`，并显式传 `max_tokens`。
   - `finish_reason` 的处理与其他 openai 兼容提供方相同（见 05-fix-r1 R1-2）。
2. **模型规格校验**：所有校验「提供方:型号」的地方，都要把 `ark` 加入允许列表，范围包括 `llm_router.parse_model`、`agent_pool._validate_model`、`pilot._model_spec`，以及其他同类检查，**请全库搜索后逐处更新，不要只改上面列出的几处**。同时更新所有提示「提供方只能为 …」的中文报错文案。
3. **环境守卫**：用到 `ark` 时，检查 `ARK_API_KEY`；缺少这个变量时，只报变量名。污染变量清单不变。
4. **型号白名单**：只为 `ark` 提供方加一张白名单，内容为 `doubao-seed-2-1-pro-260915` 和 `doubao-seed-2-1-pro-260628`。白名单外的型号以退出码 2 拒绝，报错为「火山方舟型号未在白名单内」。原因是方舟的 thinking 参数按型号区分，未知型号不能确认能否关闭思考，这一点与 05-fix-r1 R1-1 对 Claude 未知型号的处理一致。
5. **dry-run 估算表**：`ark` 角色与其他提供方同样计入，口径不变。
6. **README**：在提供方清单里加入 `ark`，写明对应的密钥变量和推荐型号 ID。
7. **测试**（全部离线）：
   - 用 `httpx.MockTransport`（openai 2.37.0 基于 httpx）截获 `ark` 的真实请求体，断言：
     - URL 以 `https://ark.cn-beijing.volces.com/api/v3/chat/completions` 结尾。
     - `thinking == {"type":"disabled"}`。
     - json 角色带 `response_format`，写手（markdown）不带。
     - `max_tokens` 存在。
     - 不含 `frequency_penalty` 和 `presence_penalty`。
   - `ark:doubao-seed-2-1-pro-260915` 能通过配置校验；`ark:unknown-model` 以退出码 2 拒绝；`volc:xxx` 这类未知提供方以退出码 2 拒绝。
   - 缺少 `ARK_API_KEY` 时的报错只包含变量名。
   - 哨兵测试：把 `ARK_API_KEY` 设为哨兵字符串，跑一个用到 `ark` 的小实验（把单次调用函数替换成本地桩），输出目录和 stdout 中都不得出现哨兵字符串。
   - 新增一份**仅供测试用**的配置：把某个推演角色换成 `ark:doubao-seed-2-1-pro-260915`，在 dry-run 下以退出码 0 跑完。这份配置写在测试内部，不新增 pilot_configs 文件。
8. **三份默认实验配置（expA/B/C.json）本单不改**，是否让豆包参加真跑由作者另行决定。

## 验收

1. `$PY -m pytest -q -p no:cacheprovider tests/test_novel_*.py` 全部通过。
2. 全量测试不出现新增失败。
3. 三个 dry-run 都以退出码 0 结束。
4. `grep -rn '"ark"' backend/novel/` 能看到提供方表、白名单和校验三处。
5. `git status --porcelain` 中没有 `M` 状态的文件。
6. 在 03-report.md 末尾追加「接入火山方舟」一节。
