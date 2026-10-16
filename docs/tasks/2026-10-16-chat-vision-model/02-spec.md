# 聊天看图模型改为可配置（默认 qwen3.8-omni-flash）

级别：L2 常规修复。工作分支 `fix-chat-vision`（独立 worktree）。

## 1. 产品目标 / 使用场景

Fiona 私聊里，用户发一张图片，后端走 `backend/services/chat_service.py` 的 `stream_image()`，把图片交给视觉模型，生成一两句看图回复。

现状：`stream_image()` 把模型名写死为 `qwen-vl-max`。2026-10-16 实测：DashScope 兼容接口 `GET https://dashscope.aliyuncs.com/compatible-mode/v1/models` 返回的作者账号可用模型（共 176 个）中已没有 `qwen-vl-max`；调用它返回 404「Model not exist」。因此聊天看图一直失败。

目标：

- 看图模型改为可配置，环境变量 `FIONA_CHAT_VISION_MODEL`。
- 默认值 `qwen3.8-omni-flash`（作者拍板；它也是当前主力聊天模型 `MAIN_MODEL`，支持图片输入）。
- `qwen3.8-omni-flash` 默认开思考模式，看图请求必须显式关闭思考（`enable_thinking=false`），否则 400 token 的回复额度可能被思考吃光、正文为空。
- 其他行为（提示词、历史条数、计费、图片摘要落库、危机资源、错误文案）一律不变。

## 2. 技术实现约束

- 沿用现有写法：模型常量放 `backend/llm.py`（文档约定「当前平台模型配置以 `backend/llm.py` 为准」）；环境变量解析函数放 `backend/services/chat_service.py`，照抄同文件 `_image_tool_enabled()` 的「每次调用现读 + 非法值只告警一次」模式（模块级 `_XXX_WARNED` 布尔量 + `logging.getLogger(__name__).warning(...)`）。
- 不引入任何新依赖；不做无关重构；不改格式。
- 测试全部离线：不得发起任何真实网络请求，不得读取 `backend/.env` 或任何密钥。
- **禁止修改的文件**（属于另一条开发线或历史记录）：
  - `backend/scripts/_studio_probe_brain.py`、`backend/scripts/studio_probe.py`
  - `backend/tests/test_studio_probe.py`、`backend/tests/fixtures/studio/**`
  - `backend/studio/**`、`backend/routers/studio.py`、`frontend/**`
  - `docs/tasks/**`（历史任务文档，含本规格所在目录，本规格文件你只读不改）
- 允许修改的文件只有：`backend/llm.py`、`backend/services/chat_service.py`、`backend/model_router.py`、`backend/tests/test_chat_branches.py`、新建 `backend/tests/test_chat_vision_model.py`、`backend/.env.example`、`CLAUDE.md`、`README.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`。
- 不要 `git commit`，不要切换分支，不要 stash。
- `frontend/node_modules` 是指向主检出依赖目录的符号链接（`frontend/.gitignore` 已忽略），供 `tests/test_studio_frontend_shell.py` 调 TypeScript 用；不要删除、不要在里面安装或写入任何东西。
- 基线（改动前，本 worktree）：全量 `6125 passed, 33 skipped, 0 failed`。

## 3. Codex 执行任务清单

可派子代理按文件不重叠分工（例如：一个改代码 + 测试，一个改文档）。

### T1 `backend/llm.py`：新增看图模型常量

在 `QWEN_EXTRA_BODY` 定义之后新增三个模块级常量（名字必须完全一致）：

```python
# 聊天看图（chat_service.stream_image）。2026-10-16 由 qwen-vl-max 切换：该模型已不在
# 账号可用模型列表，调用返回 404。默认值有意写成字面量、不引用 MAIN_MODEL——
# 主力模型将来若换成纯文本模型，看图不能跟着坏。可用 FIONA_CHAT_VISION_MODEL 覆盖。
CHAT_VISION_MODEL_ENV     = "FIONA_CHAT_VISION_MODEL"
CHAT_VISION_MODEL_DEFAULT = "qwen3.8-omni-flash"
# omni-flash 默认开思考，会吃掉看图回复的 400 token 额度；看图请求一律关掉。
CHAT_VISION_EXTRA_BODY    = {"enable_thinking": False}
```

### T2 `backend/services/chat_service.py`：解析函数

1. 从 `llm` 导入上述三个常量（照现有 `from llm import ...` 的写法；如果文件里 `QWEN_CLIENT` 是从别处导入的，保持不动）。
2. 在 `_IMAGE_TOOL_ENV_WARNED = False` 附近新增 `_CHAT_VISION_ENV_WARNED = False`。
3. 新增函数 `_chat_vision_model() -> str`，语义：
   - 每次调用现读 `os.getenv(CHAT_VISION_MODEL_ENV)`，不缓存。
   - 未设置，或 `strip()` 后为空串 → 返回 `CHAT_VISION_MODEL_DEFAULT`，不告警。
   - `strip()` 后完整匹配正则 `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`（用 `re.fullmatch`）→ 返回去空白后的值。
   - 其他情况（含空格、换行、斜杠、中文、超过 64 字符等）→ 返回 `CHAT_VISION_MODEL_DEFAULT`；若 `_CHAT_VISION_ENV_WARNED` 为假，则 `logging.getLogger(__name__).warning("FIONA_CHAT_VISION_MODEL 非法值，按默认 qwen3.8-omni-flash 处理")` 并置真。**告警文本不得包含非法值本身**；告警里的默认模型名用常量拼接，不要再写死字面量。

### T3 `backend/services/chat_service.py`：`stream_image()` 使用它

1. docstring 改为：`"""有图片：用看图模型（FIONA_CHAT_VISION_MODEL，默认 qwen3.8-omni-flash）看图，跳过意图识别。"""`（同样用不写死的措辞也可，但必须提到环境变量名）。
2. 在 `try:` 之前解析一次：`vision_model = _chat_vision_model()`。
3. `QWEN_CLIENT.chat.completions.create(...)` 的参数改为：`model=vision_model`，新增 `extra_body=dict(CHAT_VISION_EXTRA_BODY)`；`messages`、`max_tokens=400`、`temperature=0.9`、`stream=True` 保持不变。仍然使用 `QWEN_CLIENT`（测试会 monkeypatch 它）。
4. 异常日志改为 `print(f"[chat] vision model={vision_model} error type={type(e).__name__}", flush=True)`。模型名已经过正则校验，可以安全写进日志。
5. 函数里其他代码一行不动。

### T4 `backend/model_router.py`

第 134 行附近注释 `stream_image(qwen-vl-max 看图)` 改为 `stream_image(看图模型见 llm.CHAT_VISION_MODEL_DEFAULT)`，其他不动。

### T5 测试

1. `backend/tests/test_chat_branches.py::test_chat_image_branch`：
   - docstring 改为「带图片 → 走看图分支（直接用 QWEN_CLIENT，默认 qwen3.8-omni-flash）。」
   - 开头加 `monkeypatch.delenv("FIONA_CHAT_VISION_MODEL", raising=False)`。
   - 追加断言：`captured["model"] == "qwen3.8-omni-flash"`、`captured["extra_body"] == {"enable_thinking": False}`、`captured["stream"] is True`、`captured["max_tokens"] == 400`。
   - 原有断言保留。
2. 新建 `backend/tests/test_chat_vision_model.py`，沿用 `test_chat_branches.py` 的写法（`client`、`dev_headers` fixture，`_fakes.FakeStream`，monkeypatch `chat.QWEN_CLIENT`，那个 1x1 PNG 样本可以复制过来），至少覆盖：
   - a. 环境变量设为 `qwen3-vl-plus` → 请求里 `model == "qwen3-vl-plus"`，`extra_body == {"enable_thinking": False}`。
   - b. 设为 `"  qwen3-vl-plus  "` → 去空白后使用。
   - c. 设为 `""` 和 `"   "` → 用默认 `qwen3.8-omni-flash`，且不产生告警（用 `caplog` 断言）。
   - d. 非法值（至少 `"bad model"`、`"qwen\nx"`、`"../x"`、`"a" * 65`）→ 用默认；先 `monkeypatch.setattr(chat, "_CHAT_VISION_ENV_WARNED", False)`，连续解析两次只产生一条告警，且告警文本不包含非法值。可以直接调用 `chat._chat_vision_model()` 做单元测试。
   - e. 每次调用现读：同一测试内先后用两个不同的环境变量值各发一次 `/chat` 看图请求，两次 `create` 收到的 `model` 各自对应。
   - f. 上游异常：fake `create` 抛异常 → SSE 里有 `error` 事件；`capsys` 捕获的 stdout 含 `[chat] vision model=qwen3.8-omni-flash error type=`，且不含 `qwen-vl-max`。
   - g. 默认常量：`llm.CHAT_VISION_MODEL_DEFAULT == "qwen3.8-omni-flash"`、`llm.CHAT_VISION_MODEL_ENV == "FIONA_CHAT_VISION_MODEL"`。
   - 每个测试都要先清理或显式设置 `FIONA_CHAT_VISION_MODEL`，不依赖外部环境。

### T6 文档（措辞照抄或等义，保持各文件原有文风；只改下列位置）

1. `CLAUDE.md` 第 10 行：把「图片 `qwen-vl-max`」改为「看图 `qwen3.8-omni-flash`（`FIONA_CHAT_VISION_MODEL` 可改；原 `qwen-vl-max` 已不在账号可用模型列表）」。该行其余内容不动。
2. `docs/ARCHITECTURE.md`「当前平台模型配置」列表：
   - 删除 `- \`qwen-vl-max\`：用户图片理解。` 这一行。
   - 把 `- \`qwen3.8-omni-flash\`：主力对话、匹配和复杂判断。` 改为：`- \`qwen3.8-omni-flash\`：主力对话、匹配和复杂判断；也是用户图片理解（看图）的默认模型。看图模型由 \`FIONA_CHAT_VISION_MODEL\` 单独配置，每次调用时读取，空值用默认，非法值回落默认并只告警一次；看图请求固定关闭思考模式。`
3. `PLAN.md`「已实现 / 对话与模型」里 `- \`qwen-vl-max\` 图片理解。` 改为 `- 用户图片理解：默认 \`qwen3.8-omni-flash\`，可用 \`FIONA_CHAT_VISION_MODEL\` 改（2026-10-16 起；原 \`qwen-vl-max\` 已不在账号可用模型列表）。`
4. `README.md`：在「OpenAI 兼容模型客户端默认 60 秒超时……」这一段的末尾（「无效值回落到默认值。」之后）另起一行补一句：`用户发图时的看图模型默认 \`qwen3.8-omni-flash\`（与主力对话同一模型），可用 \`FIONA_CHAT_VISION_MODEL\` 改为账号已开通的其他视觉模型；每次调用时读取，空值用默认，非法值回落默认并只告警一次，请求固定关闭思考模式。` 不改 README 其他地方。
5. `docs/DEPLOYMENT.md` 环境变量表：在 `DASHSCOPE_API_KEY` 那一行之后插入一行：`| \`FIONA_CHAT_VISION_MODEL\` | 聊天看图模型，默认 \`qwen3.8-omni-flash\`，使用 \`DASHSCOPE_API_KEY\`；每次调用时读取，空值用默认，非法值回落默认并只告警一次；请求固定关闭思考模式 |`
6. `backend/.env.example`：
   - 第 13 行注释「主力大脑 qwen3.8-omni-flash + 轻量槽 ……」里，在「主力大脑 qwen3.8-omni-flash」后补「(也是默认看图模型)」。
   - 在 `DASHSCOPE_MAX_RETRIES=1` 之后、空行之前插入：
     ```
     # 聊天看图模型；留空用默认 qwen3.8-omni-flash。须是该 key 已开通、支持图片输入的模型。
     # 每次调用时读取；非法值回落默认并只告警一次；请求固定带 enable_thinking=false。
     FIONA_CHAT_VISION_MODEL=
     ```

## 4. 验收标准

在仓库根（worktree 根）执行，Python 用 `~/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`（下称 `$PY`）：

1. `grep -rn "qwen-vl-max" backend/services backend/llm.py backend/model_router.py CLAUDE.md README.md PLAN.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md backend/.env.example`
   期望：只剩 `backend/llm.py` 注释里的「由 qwen-vl-max 切换」、`CLAUDE.md` 和 `PLAN.md` 里「原 `qwen-vl-max` 已不在账号可用模型列表」这类历史说明，没有任何把它当作现役模型的调用或陈述。
2. `grep -n "FIONA_CHAT_VISION_MODEL" backend/llm.py backend/.env.example CLAUDE.md README.md PLAN.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md` → 每个文件至少一处。
3. `cd backend && $PY -m pytest -q -p no:cacheprovider tests/test_chat_branches.py tests/test_chat_vision_model.py` → 全部通过。
4. `cd backend && env -u DASHSCOPE_API_KEY $PY -m pytest -q -p no:cacheprovider` → 0 failed、0 errors（全量）。
5. `git status --porcelain` → 只出现第 2 节「允许修改的文件」以及本规格目录 `docs/tasks/2026-10-16-chat-vision-model/`。
6. `git diff backend/scripts backend/studio backend/tests/test_studio_probe.py backend/tests/fixtures frontend` → 空。

## 5. 完成后输出

变更总结，必须包含：1. 修改了哪些文件 2. 实现了哪些功能 3. 与本规格任务清单 T1–T6 的逐项对应 4. 测试结果（贴最后一行汇总）5. 未完成或需要人工确认的地方。
