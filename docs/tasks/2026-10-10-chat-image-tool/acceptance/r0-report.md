# 主聊天模型调用生图工具：完成报告

日期：2026-10-10。基线：`7ac7b5763f053e6607d036e104cb1574e6ec1d71`。执行依据：[02-spec.md](../02-spec.md) 与 [05-fix-r0.md](../05-fix-r0.md)，冲突处按 R0 选项 1。

实现已完成，170 项新增测试全部通过，第 5 节验收命令全部实际执行。默认全量 3094 passed；开关开启全量 3062 passed，32 条旧生图行为断言按规格允许失败。两次全量还各有 1 failed、5 errors、6 skipped，均为沙箱端口/回环权限限制，不能记为通过，仍需作者方在沙箱外复验。TypeScript 和依赖检查通过；ESLint 为 0 errors / 25 warnings。

## 1. 新增与修改文件

多个 subagent 按文件不重叠并行，均继承主代理模型与推理档位，未传 `model` 或 `reasoning_effort`。执行核心组先给出函数签名，再启动其他组；所有 `chat_service.py` 工作只由聊天执行组完成，BYOK client 按约定结果接口协作。

| 负责方 | 修改 | 新增 |
| --- | --- | --- |
| 执行核心、平台/BYOK 流与路由组 | `backend/services/chat_service.py`、`backend/tools/image_generation.py` | `backend/services/image_tool.py`、`backend/tests/test_chat_image_tool.py`（99 例） |
| BYOK client 组 | `backend/byok/client.py` | `backend/tests/test_byok_image_tool.py`（41 例） |
| 前端组 | `frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/ChatModelSection.tsx` | `backend/tests/test_chat_image_tool_frontend.py`（17 例） |
| 主代理 | `backend/persona.py`、`backend/tests/conftest.py`、`backend/.env.example`、`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` | `backend/tests/test_chat_image_tool_docs.py`（13 例）；覆盖本报告；`acceptance/` 完整验收输出与结果 JSON |

`02-spec.md` 和 `05-fix-r0.md` 是作者提供的未跟踪任务输入，内容未改。受保护文件未改；其他所有既有测试输入和断言未改。conftest 恰好新增指定一行，persona 恰好替换一行。没有安装包、发起真实网络请求、运行 build/dev 或启动后端。

## 2. 实现的功能与接口

- 主回复模型根据完整对话撰写画面描述并调用 `generate_image`；一轮最多一图，执行后结束，不回灌续写。仅明确要新图时调用；历史引用、不能修旧图、隐私与点名模型规则写入中文工具描述。
- 每轮读取 `FIONA_CHAT_IMAGE_TOOL`，默认 1，仅字面 0 关闭，非法值按开启且仅告警一次。唯一判定入口覆盖聊天模式、无图片、无 high/possible、BYOK 预扣/配置守卫和模型白名单。平台两槽、Claude 三型号、规定 Qwen/DeepSeek 型号可用；Kimi、智谱、自定义等保留旧路由。
- 工具生图默认 Seedream，忽略面板 `image_model`；在请求前按 Key 可用性双向降级并说明。请求后失败不跨供应商重试。工具比例优先，再取描述原文比例，默认 1:1；面板和旧路由仍按既有选择。
- OpenAI 增量按 index 累积，id/name 不重复拼接，只拼 arguments；严格 JSON、合法结束原因、prompt 长度及可选枚举校验。Claude 仅取最后 fallback 之后的首个生图块，拒答/截断不执行。
- 成功只写一行 assistant：保留前导文字、完成文字、使用的描述、降级说明和图片；描述/降级事件 `speak: false`。工具 trace 保留回复模型、记录实际生图模型/来源/降级，不含描述。
- 图成功才结算 10 颗，每轮只预扣一次；图失败、非法参数、断开均退款。失败不落库前导文字，未落库附件清理。BYOK 文字仍免费，关流并释放 BYOK 槽位后才生图，生图不计入 BYOK 时限；先发模型标签。
- 生成期间保留可见前导文字，静音事件仍进正文，工具失败不显示面板重试按钮；聊天请求仍带原 `image_model`。文档、隐私、环境模板和时限口径同步。
- R0：全部 high/possible（含信息语境）不下发工具，假工具流不得经工具路径出图，危机资源恰好一次。非信息 possible 保留生图 pending；信息/求助 possible 沿用旧行为，测试比较开关 0/1 一致，可能清 pending 或经旧路由生成。

对外协作契约：

```python
openai_image_tool() -> dict
anthropic_image_tool() -> dict
OpenAIToolCallAccumulator.add(deltas) -> None
OpenAIToolCallAccumulator.result(finish_reason) -> tuple[dict | None, bool]
extract_anthropic_image_tool_call(message) -> tuple[dict | None, bool]
validate_image_tool_call(call) -> dict | None
image_model_available(model_id: str) -> bool

_stream_image_execution(ctx, state, prompt, *, aspect_ratio=None,
                       model_id=None, lead_text="", source=None)
stream_normal(ctx, state, *, image_tool=False)
_stream_byok_reply(ctx, state, *, mirror, image_tool=False)
open_reply_stream(..., tools=None)
ReplyStream.tool_call          # 只读快照：None 或 {name, arguments: dict}
ReplyStream.tool_call_invalid  # 只读 bool
```

原 `run_chat` 从 `# 正则只提名候选。` 到 `except ResourceNotFound` 前的路由片段与基线逐字节相同：7434 bytes，`identical=True`。开关真时新增 helper 早返回，假时原段执行；无工具请求不增加 kwargs，BYOK 既有请求体逐字节测试通过。

## 3. 与规格 4.1–4.10 的逐项对应

| 条款 | 实现与验证 | 状态 |
| --- | --- | --- |
| 4.1 工具定义 | `image_tool.py` 两 SDK 格式、中文正负例/历史/新图/隐私/调用前话术/模型规则、prompt maxLength 1500、枚举、不启 strict，不含安全规则正文 | 完成 |
| 4.2 解析校验 | 重复 id、arguments 分片、首个生图调用、严格 JSON；Claude fallback/stop；空/超长/截断/拒答不生图，前导加固定通知落库且退款，BYOK 先标签 | 完成 |
| 4.3 执行核心 | 原函数包装核心；默认 Seedream、双向 Key 降级、比例、单次请求、模型状态/10 秒心跳、单 done、单行落库、取消屏蔽与孤图清理、分类错误、仅成功计费、trace 不含 prompt | 完成 |
| 4.4 平台流 | 可选默认关闭参数；两平台槽 tools/auto、max_tokens 1200、无 parallel_tool_calls；工具前导不提前保存/计费，合法/非法/tool-only 分支，成功后原 followups 条件 | 完成 |
| 4.5 BYOK | 可选 tools；Claude auto/disable_parallel 与 effort/betas/fallback 共存，SDK ValueError 分类；Qwen/DeepSeek 保持关思考；只产文字且只读结果；释放槽位与时限后执行；daily 一次、tool-only 与退款 | 完成 |
| 4.6 路由 | 指定位置算一次开关；旧段字节不改；候选确认 friend 安全 system/绕镜子，旧 image pending 清除/取消，不新建；天气不变，生图意图/识别异常进主回复，镜子不下发；R0 危机旧行为对比 | 完成 |
| 4.7 persona | 仅一行替换为两个模型中性能力描述，保留“只有实际收到生成结果时才说图片已生成”；注释明确主回复根据对话写描述 | 完成 |
| 4.8 前端 | 前导可见、仅生成时空占位隐藏、speak/source 类型、静音正文、工具失败无重试，面板/请求选择保持，BYOK 隐私说明；17 例与 TS/ESLint | 完成 |
| 4.9 文档模板 | 五文档与 env 同步白名单/旧路由、默认/降级、每轮一图、描述行、计费/隐私/限制、实时开关、ARK/Seedream 参数、120/180+150 秒与 10 秒心跳/Nginx 间隔口径 | 完成 |
| 4.10 测试 | 170 新例：99 聊天/执行、41 BYOK、17 前端、13 文档；假流与离线 SDK，真实隔离 SQLite 计费、危机/R0、安全规则朗读末尾恰好一次、白名单/开关/零余额、取消/心跳/不跨厂商重试 | 完成；沙箱外项目见第 6 节 |

## 4. RED → GREEN 证据

实现修改先写会失败的测试并实际确认 RED。补充覆盖若已由既有实现满足，标记为验证，未人为破坏代码制造 RED。以下摘要来自实际执行；命令均在 backend，使用仓库已有 `.venv/bin/python`。

| 批次 | RED 实际摘要 / 退出码 | GREEN 实际摘要 / 退出码 |
| --- | --- | --- |
| `python -m pytest -q tests/test_chat_image_tool.py` 初始工具 helper | `7 failed in 0.29s` / 1，模块/API 不存在 | `7 passed in 0.26s` / 0 |
| 同文件执行核心 | `9 failed, 7 passed in 1.25s` / 1，执行核心不存在 | 加旧 `test_chat_image_generation.py`：`53 passed, 14 warnings in 2.53s` / 0 |
| `python -m pytest -q tests/test_chat_image_tool.py -k 'platform or byok'` 恢复集成 | `11 failed, 1 passed, 17 deselected in 0.92s` / 1，缺 image_tool 参数 | 同筛选加 `--tb=line`：`12 passed, 41 deselected in 0.81s` / 0 |
| 同文件 `-k 'unique_gate or gate_reads or tool_route' --tb=line` | `24 failed, 29 deselected in 0.82s` / 1，20 例入口缺失/4 例仍直接生图 | 完整文件 `53 passed in 0.84s` / 0 |
| 同文件 `-k 'invalid_refusal or unconfigured_tool_failure' --tb=line` | `3 failed, 53 deselected in 0.82s` / 1，拒答多旧提示/缺 Key 无 trace | `3 passed, 53 deselected in 0.82s` / 0 |
| `python -m pytest -q tests/test_byok_image_tool.py` 初始接口 | `33 failed, 1 passed in 1.04s` / 1，缺 tools 参数 | `34 passed in 0.82s` / 0 |
| 同文件 `-k interruption_during_final_message` | `3 failed, 1 passed, 34 deselected in 0.75s` / 1，final 超时/取消仍暴露工具或误分类 | `4 passed, 34 deselected in 0.69s` / 0 |
| `python -m pytest -q tests/test_chat_image_tool_frontend.py` | `6 failed, 11 passed in 0.58s` / 1，可见文字/静音/重试/类型/隐私 | `17 passed in 0.57s` / 0 |
| `python -m pytest -q tests/test_chat_image_tool_docs.py` 初批 | `8 failed in 0.15s` / 1，人设、文档、env、默认开关 | `8 passed in 0.14s` / 0 |
| 文档 R0 pending 口径 | `5 failed, 8 passed` / 1 | `13 passed` / 0 |
| 文档 BYOK/预扣口径和 env | `6 failed, 7 passed` / 1 | `13 passed` / 0 |
| 架构 trace.model 限定工具路径 | `1 failed, 12 passed` / 1 | `13 passed` / 0 |

补充验证：聊天完整文件最终 `99 passed, 14 warnings in 1.23s` / 0；BYOK 加三项实际 SDK MockTransport 安全 system 序列化后 `41 passed in 0.83s` / 0（三项无需代码变更）。聊天相关十个新旧文件回归 `666 passed, 14 warnings in 14.34s` / 0；BYOK client/effort/new，排除六个既有 loopback 项的分组回归 `267 passed, 6 deselected, 14 warnings in 2.15s` / 0。最终全量没有主动排除用例，六个 loopback 项由原测试自行跳过。

## 5. 第 5 节验收：实际命令、输出与退出码

全部验收在实现冻结后运行。根目录执行静态命令；pytest/pip 在 backend，tsc/eslint 在 frontend。使用已有虚拟环境；npx 设置 `NPM_CONFIG_OFFLINE=true`；pip 使用可写临时缓存目录，无安装操作。完整 stdout/stderr 保存在 [acceptance/](./)，每条命令及实际退出码见 [results.json](results.json) 与 [static-checks.txt](static-checks.txt)。日志仅将本机绝对路径替换为仓库相对路径或 `<python-stdlib>` / `<pytest-temp>`，其余输出不改。

### 5.1 文件范围

`git status --porcelain`，退出码 **0**，实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/byok/client.py
 M backend/persona.py
 M backend/services/chat_service.py
 M backend/tests/conftest.py
 M backend/tools/image_generation.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/components/ChatModelSection.tsx
?? backend/services/image_tool.py
?? backend/tests/test_byok_image_tool.py
?? backend/tests/test_chat_image_tool.py
?? backend/tests/test_chat_image_tool_docs.py
?? backend/tests/test_chat_image_tool_frontend.py
?? docs/tasks/2026-10-10-chat-image-tool/
```

全部属于允许范围。`acceptance/` 及本报告位于已列出的任务目录。

### 5.2 受保护文件和既有测试

```bash
git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/database.py backend/byok/crypto.py backend/byok/url_safety.py backend/byok/store.py backend/routers/chat_model.py backend/utils/safe_http.py
```

实际输出为空，退出码 **0**。

`git diff --stat -- backend/tools`，退出码 **0**，实际输出：

```text
 backend/tools/image_generation.py | 22 +++++++++++++++++-----
 1 file changed, 17 insertions(+), 5 deletions(-)
```

`git diff backend/tests/conftest.py`，退出码 **0**，实际输出：

```diff
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index 60a8b69..f025214 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -38,6 +38,7 @@ from _fakes import FakeStream
 os.environ.setdefault("JWT_SECRET", "fiona-ci-smoke-test-secret-0123456789")
 os.environ.setdefault("DASHSCOPE_API_KEY", "sk-fiona-ci-smoke-test-not-real")
 os.environ.setdefault("FIONA_CRISIS_MODEL_ENABLED", "0")
+os.environ.setdefault("FIONA_CHAT_IMAGE_TOOL", "0")
 
 
 @pytest.fixture
```

`git diff --exit-code -- 'backend/tests/*.py' ':!backend/tests/conftest.py'`，实际输出为空，退出码 **0**。所有任务前已存在的测试无改动。另将当前 conftest 去掉指定一行后与基线全文比较，完全相同。`git diff --check` 输出为空，退出码 **0**。

### 5.3 面板默认模型

`grep -n "DEFAULT_IMAGE_MODEL = " backend/tools/image_generation.py`，退出码 **0**，实际输出：

```text
71:DEFAULT_IMAGE_MODEL = "qwen-image-3.0"
```

### 5.4a 默认全量

```bash
python -m pytest -q
```

未传开关环境变量，由 conftest 默认关闭。实际摘要，退出码 **1**（[完整输出](5.4a-default.txt)）：

```text
1 failed, 3094 passed, 6 skipped, 14 warnings, 5 errors in 74.50s (0:01:14)
```

基线 2936 + 新增 170 = 3106。实际 3094 passed + 6 skipped + 1 failed + 5 errors = 3106，无其他默认功能失败。12 个非 passed 均因端口/回环权限；规格 5.4a 允许沙箱内忽略，须在沙箱外补验，不能把通过数写成 3106。

六个 FAILED/ERROR 与 5.4b 环境阻断相同，逐条见下表。六个 skip 是既有 `test_byok_client.py::test_r1_watchdog_real_loopback` 的两个 provider 参数，以及 `test_r2_loopback_interrupt_race` 的两个 provider × 两个 interruption 参数，原测试在本地 bind 被拒后自行 skip，需沙箱外复验。

### 5.4b 开关开启全量与每条失败原因

```bash
FIONA_CHAT_IMAGE_TOOL=1 python -m pytest -q
```

实际摘要，退出码 **1**（[完整输出与 traceback](5.4b-on.txt)）：

```text
33 failed, 3062 passed, 6 skipped, 14 warnings, 5 errors in 74.40s (0:01:14)
```

33 条 FAILED 中 32 条为本单有意改变的旧聊天生图预期，均在规格明确允许的四个文件内；第 17 条为沙箱 bind 阻断。另 5 条 ERROR 同样为 bind 权限限制，不是允许的行为差异，不记为通过，留待沙箱外确认；除这些环境项，未发现其他功能失败。开关开启结果不能表述为全量通过。以下中文参数仅将 pytest 节点中的 `\uXXXX` 还原，以便阅读；原节点名保留于完整输出。

| 序号 | FAILED 用例 | 逐条原因 |
| --- | --- | --- |
| 1 | `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image]` | 旧断言要求不调用 BYOK；实际交给带 tools="generate_image" 的 BYOK 回复。假回复只产文字，未调用生图；属于 4.5/4.6 的有意变化。 |
| 2 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]` | 旧断言要求 pending 补参直接 generate_image；4.6.2 改为清 pending 后交给主回复，假回复未调用工具，generated 为空。 |
| 3 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]` | 失败在种 pending 的准备步骤：旧断言要求“帮我画张图”新建 generate_image pending，实际为 None；4.6 禁止新建。尚未到后续零余额/weather 守卫，非其回归。 |
| 4 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]` | 失败在种 pending 的准备步骤：旧断言要求“帮我画张图”新建 generate_image pending，实际为 None；4.6 禁止新建。尚未到后续零余额/weather 守卫，非其回归。 |
| 5 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[帮我生成一张青灰薄雾古庙图片，横版16:9-16:9]` | 旧断言要求候选确认后把原句和比例直接发送生图；4.6.1 进入 friend 工具回复。假流只返回“测试”，image_stub 调用列表为空。 |
| 6 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[画一只趴在窗台的猫-1:1]` | 旧断言要求候选确认后把原句和比例直接发送生图；4.6.1 进入 friend 工具回复。假流只返回“测试”，image_stub 调用列表为空。 |
| 7 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[请帮我做一张咖啡店海报，竖版-9:16]` | 旧断言要求候选确认后把原句和比例直接发送生图；4.6.1 进入 friend 工具回复。假流只返回“测试”，image_stub 调用列表为空。 |
| 8 | `tests/test_chat_image_generation.py::test_image_prompt_question_then_description_generates_only_description` | 旧断言要求固定“想生成什么画面”追问与生图 pending；新路径由主回复处理，假回复为“测试”，不新建 pending。 |
| 9 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-帮我生成图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 10 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-帮我生成一张图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 11 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-画一张图]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 12 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-给我画一幅画]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 13 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-帮我生成图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 14 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-帮我生成一张图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 15 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-画一张图]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 16 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-给我画一幅画]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；实际首轮由主回复返回“测试”。候选确认后交给主模型，不新建生图 pending（4.6）。 |
| 17 | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` | 测试准备阶段 asyncio.start_server 在 bind(127.0.0.1, 0) 抛 PermissionError；未到上游断开断言。环境受限，需沙箱外复验。 |
| 18 | `tests/test_image_intent_precision.py::test_model_confirmed_candidate_generates_once_and_charges` | 旧断言要求意图确认后直接 generate("画一只猫", "16:9")；新路径交给主回复，假流不调用工具，调用列表为空。 |
| 19 | `tests/test_image_intent_precision.py::test_confirmed_candidate_without_model_prompt_uses_original_text[classified0]` | 旧断言要求分类器无 prompt 时使用原句直接生图；新路径由主回复撰写完整描述并调用工具，假流只有文字，调用列表为空。 |
| 20 | `tests/test_image_intent_precision.py::test_confirmed_candidate_without_model_prompt_uses_original_text[classified1]` | 旧断言要求分类器无 prompt 时使用原句直接生图；新路径由主回复撰写完整描述并调用工具，假流只有文字，调用列表为空。 |
| 21 | `tests/test_image_intent_precision.py::test_model_missing_prompt_overrides_populated_regex_candidate` | 旧断言要求分类器 missing prompt 触发固定追问和 pending；实际主回复为“测试”，新路径不新建生图 pending。 |
| 22 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[画一只在午夜灯塔边等船的黑猫，背景是潮汐与蓝色纸灯，横版16:9-9:16-16:9-True]` | 旧断言要求确认候选后使用原句而非分类器摘录直接生图并取原句比例；新路径由主回复整理描述，假流未调用工具。 |
| 23 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[午夜灯塔旁的黑猫与蓝色纸灯，请将海雾画出来-9:16-9:16-False]` | 旧断言要求非候选 generate_image 意图直接发送原句生图；4.6.3 将该意图视为无意图并进入带工具回复，假流未调用工具。 |
| 24 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[山顶风车与落日，请给我一幅正方形插画-9:16-1:1-False]` | 旧断言要求非候选 generate_image 意图直接发送原句生图；4.6.3 将该意图视为无意图并进入带工具回复，假流未调用工具。 |
| 25 | `tests/test_image_intent_precision.py::test_text_ratio_precedes_chat_field_but_image_button_keeps_selection[chat-16:9-1]` | 旧 chat 断言要求原句直接生成 16:9；主回复假流没有工具调用，调用列表为空。只有 chat 参数失败，显式面板 image 参数通过。 |
| 26 | `tests/test_image_intent_precision.py::test_rejected_candidate_cannot_fill_old_image_prompt` | 已正常回复且未生图；失败断言为 get_pending(key) is not None。4.6.2 要求非取消文本清除遗留生图 pending，实际为 None。 |
| 27 | `tests/test_image_intent_precision.py::test_confirmed_candidate_bypasses_active_mirror` | 镜子与 detect_mode 禁调用桩均未触发，已绕过镜子进入 friend 回复；失败的是旧直接生图断言，假主回复流未调用工具。 |
| 28 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-omitted]` | 旧断言要求 chat_intent 直接生成一图并跟随面板选择；新路径需要主回复工具调用且忽略面板选择，假流无工具，图片数为 0。显式 image/image_edit 参数通过。 |
| 29 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-default]` | 旧断言要求 chat_intent 直接生成一图并跟随面板选择；新路径需要主回复工具调用且忽略面板选择，假流无工具，图片数为 0。显式 image/image_edit 参数通过。 |
| 30 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-seedream]` | 旧断言要求 chat_intent 直接生成一图并跟随面板选择；新路径需要主回复工具调用且忽略面板选择，假流无工具，图片数为 0。显式 image/image_edit 参数通过。 |
| 31 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-omitted]` | 旧断言要求 pending 补参直接生成一图并跟随面板选择；新路径清 pending 后由主回复决定，假流没有工具，图片数为 0。显式 image/image_edit 参数通过。 |
| 32 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-default]` | 旧断言要求 pending 补参直接生成一图并跟随面板选择；新路径清 pending 后由主回复决定，假流没有工具，图片数为 0。显式 image/image_edit 参数通过。 |
| 33 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-seedream]` | 旧断言要求 pending 补参直接生成一图并跟随面板选择；新路径清 pending 后由主回复决定，假流没有工具，图片数为 0。显式 image/image_edit 参数通过。 |

5 条 ERROR 逐条如下（两次全量均相同）：

| ERROR 用例 | 逐条原因 |
| --- | --- |
| `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |

5.4b 的总数核对：3062 passed + 32 行为差异失败 + 1 权限失败 + 5 权限 errors + 6 skips = 3106。

### 5.4c 新测试全部通过

```bash
python -m pytest -q tests/test_chat_image_tool.py tests/test_byok_image_tool.py tests/test_chat_image_tool_docs.py tests/test_chat_image_tool_frontend.py
```

退出码 **0**，实际完整输出：

```text
........................................................................ [ 42%]
........................................................................ [ 84%]
..........................                                               [100%]
=============================== warnings summary ===============================
tests/test_chat_image_tool.py: 14 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
170 passed, 14 warnings in 2.31s
```

### 5.5 依赖检查

`python -m pip check`，退出码 **0**，实际完整输出：

```text
No broken requirements found.
```

### 5.6 前端

`npx tsc --noEmit`，实际输出为空，退出码 **0**。

`npx eslint .`，退出码 **0**，实际完整输出：

```text
frontend/app/page.tsx
   148:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   239:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   538:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   591:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   592:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   593:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   603:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   604:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   605:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   606:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   609:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   615:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   616:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   920:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1014:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1438:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1458:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1466:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1487:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1529:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1625:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1970) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  2069:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  2109:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2379:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

警告数与基线相同，25 warnings / 0 errors。

## 6. 未完成或需要人工确认

- 规格内实现和沙箱允许的验收命令均已完成，没有待解决的实现冲突，也没有未修复的新增测试失败。
- 作者方需在沙箱外重跑默认与开启开关全量，确认两次各 6 个权限失败/报错及 6 个自行 skip 的旧回环测试；本环境无法对这些项给出通过结论。5.4b 的 32 条旧行为差异失败逐条已说明，不修改其输入或断言。
- 真实模型评测、构建与浏览器走查按规格由作者方在沙箱外完成。本轮使用假流、本地 ASGI/隔离 SQLite 与离线 MockTransport；不据此声称真实厂商调用效果或浏览器体验已验收。

本轮曾因 3.2“旧路由字节不变”与原 4.10 第 8 条“所有 possible 保留 pending”的冲突暂停一次；已由 [05-fix-r0.md](../05-fix-r0.md) 裁定选项 1，按裁定从停止处继续并完成，未回滚原改动。
