# 聊天生图（R1）：完成报告

日期：2026-10-10。基线：`7ac7b5763f053e6607d036e104cb1574e6ec1d71`。依据 [02-spec.md](02-spec.md)、[05-fix-r0.md](05-fix-r0.md)、[05-fix-r1.md](05-fix-r1.md)，冲突处以 R1 为准。

R1 实现已完成，第 5 节验收全部执行；311 项本任务新增测试全部通过。默认全量 3235 passed；开启开关并加载判断器桩插件的全量结果及全部失败原因见第 5 节。两次全量中的沙箱端口权限失败/报错和自行 skip 均不记为通过，需作者方在沙箱外复验。依赖与 TypeScript 通过；ESLint 为 0 errors / 25 warnings。

本轮测试离线纪律有一次偏差：初次 R1 路由 RED 的 5 条回退用例漏设平台回复流桩，触达 SDK 并报 APIConnectionError，不能证明未发生外部连接尝试。已补桩及连接硬拦截，不复发请求取证；详细说明见 R1 一节。本报告不宣称全程满足“不发起真实网络请求”的硬约束。

## 1. 新增与修改文件

多个 subagent 按文件不重叠并行，未传 `model` / `reasoning_effort`，均继承主控档位。先约定执行核心签名；R1 再约定判断器接口后并行。

| 负责方 | 修改 | 新增 |
| --- | --- | --- |
| 聊天执行与路由组 | `backend/services/chat_service.py`、`backend/tools/image_generation.py`；R1 更新本任务新增 `test_chat_image_tool.py` | `backend/tests/test_chat_image_tool.py`，当前 119 例 |
| 工具定义与判断器组 | 本任务新增 `backend/services/image_tool.py` | `backend/services/image_tool.py`、`backend/tests/test_image_planner.py`（48 例） |
| BYOK client / R1 协作组 | `backend/byok/client.py`（R1 保留此前 native 实现） | `backend/tests/test_byok_image_tool.py`（41 例）、`backend/tests/test_byok_planner_r1.py`（67 例）、任务目录 `image_planner_stub.py` |
| 前端组 | `frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/ChatModelSection.tsx`（R1 按修订单不变） | `backend/tests/test_chat_image_tool_frontend.py`（17 例） |
| 主控 | `backend/persona.py`、`backend/tests/conftest.py`（R1 不变）；`backend/.env.example`、`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`（R1 更新） | `backend/tests/test_chat_image_tool_docs.py`（当前 19 例）、覆盖本报告、`acceptance/r1-*` 验收输出/结果、`acceptance/r0-report.md` 历史快照 |

02/R0/R1 规格是作者提供的任务输入，内容未改。受保护文件与所有任务前既有测试输入/断言未改；conftest 恰好新增指定一行，persona 恰好替换一行。未安装包，未运行 build/dev，未启动后端；网络纪律偏差单列，不掩盖为合规。

## 2. 实现功能与接口

新生图流程仅在 chat、无本轮图片、无 high/possible、无 BYOK 配置错误、未触发零余额守卫且开关开启时使用。开关每轮读取，默认 1、只有字面 0 关闭，非法值开启并仅告警一次；已删除回复模型白名单条件。

原生工具模式仅限 BYOK Anthropic 三型号及 DeepSeek 精确 `deepseek-v4-pro` / `deepseek-flash`，保留完整对话工具决定生图。平台两槽及其余 BYOK 均为判断器模式，回复请求永远不带工具。判断器只在逐字预筛或显式候选命中时调用；未命中时不增加调用。

判断器 draw 直接共用执行核心、不调用回复模型/意图/detect_mode，无模型标签/前导文字，不计 `byok_chat`；no 跳候选后正常路由，不新建生图 pending；error 增加安全 trace 后原旧段执行。判断器可在镜子模式前识别生图；原生非候选镜子仍无工具。

两种模式默认 Seedream，忽略面板选择，在请求前检查 Key 并双向降级说明；请求后失败不换供应商重试。比例为参数优先、描述原文其次、1:1 默认。每轮最多一图、一个 done，不回灌续写；成功单行 assistant 保存完成文字、使用的描述、降级说明和图片，原生保留前导。描述/降级事件不朗读；图成功才结算 10 颗，失败/非法调用/断开退款，清理未落库图片。

BYOK 原生流先发标签、关流释放槽位后执行生图，不占 BYOK 生图时限；纯文字免费。R0 危机规则保持：所有 high/possible 不下发工具/判断器，资源恰好一次；非信息 possible 保留 pending，信息/求助 possible 与开关关闭的旧行为一致。

```python
IMAGE_PLANNER_PROMPT                     # R1 逐字提示词
IMAGE_PLANNER_PREFILTER_PATTERN          # R1 逐字正则字符串
IMAGE_PLANNER_PREFILTER                  # re.IGNORECASE
image_planner_prescreen(message, *, explicit=False) -> bool
await plan_image(history, message) -> dict
# {status: draw, prompt, [model], [aspect_ratio]}
# {status: no}
# {status: error, exception_type, elapsed_ms}

openai_image_tool() -> dict
anthropic_image_tool() -> dict
validate_image_tool_call(call) -> dict | None
image_model_available(model_id: str) -> bool
_stream_image_execution(ctx, state, prompt, *, aspect_ratio=None,
                       model_id=None, lead_text="", source=None)
stream_normal(ctx, state)                # 全文恢复基线，无工具参数
_stream_byok_reply(ctx, state, *, mirror, image_tool=False)
open_reply_stream(..., tools=None)
ReplyStream.tool_call / ReplyStream.tool_call_invalid  # 只读
```

原 `run_chat` 自 `# 正则只提名候选。` 至 `except ResourceNotFound` 前 7434 UTF-8 bytes 与基线完全相同；`stream_normal` 全文也与基线完全相同。无工具 BYOK 请求体字节兼容回归通过。

## 3. 与规格 4.1–4.10 逐项对应

| 条款 | 当前实现与验证 | 状态 |
| --- | --- | --- |
| 4.1 | 两 SDK 中文工具定义、schema/枚举/maxLength 1500、无 strict、安全/隐私/历史/新图限制保留；R1 新增逐字判断器常量 | 完成 |
| 4.2 | native 重复 id/arguments 分片、首工具、严格 JSON、Claude fallback/stop、非法调用通知落库/退款；planner 按 R1 draw/no/error 校验 | 完成 |
| 4.3 | 两模式共用核心；默认/降级/比例、心跳/事件/单行落库、计费/取消清理、分类错误、无跨厂商重试；planner 无前导/标签且最终 image_source=planner，model 空值 | 完成 |
| 4.4 | 由 R1 替换：删除平台工具参数、1200 tokens 和累积死代码，stream_normal 全文恢复基线/700 tokens；两槽永远无 tools，planner 决策先于回复 | 完成 |
| 4.5 | native 仅 Claude 与两个精确 DeepSeek，helper 直接调用也有模式防守；client 原生实现保留且默认请求不变；其他 BYOK planner 图不调用用户模型、不计 daily，文字免费 | 完成 |
| 4.6 | 唯一开关去白名单、native/planner 模式；planner draw/no/error 路由，error 旧段原样执行；pending/天气/镜子/其他意图与 R0 危机规则覆盖 | 完成 |
| 4.7 | persona 原一行中性模型描述保留，实际收到结果才能宣称完成的规则保留；两模式共用此人设约束 | 完成 |
| 4.8 | R1 不变：前导文字可见、speak=false 进正文不朗读、工具来源无面板重试、image_model 请求保留；17 项通过，TS/ESLint 通过 | 完成 |
| 4.9 | 五文档+env 改写两模式，qwen3.8-flash/6条600字/DashScope/1–5秒/8秒/error回退，更新镜子与Kimi等局限；默认/计费/隐私/时限保持 | 完成 |
| 4.10 | 当前311项本任务新测试：119+41+17+19+48+67；逐字常量、判断器输入与坏输出/超时、无工具平台/BYOK、无调用 draw、native、安全/危机、真实隔离 SQLite 计费、取消/trace覆盖 | 完成；环境补验见末节 |

## 4. R1

### 调整与验证

平台不再依赖回复模型自动调用工具。判断器复用 `llm.QWEN_CLIENT`，固定 `qwen3.8-flash`，非流式 JSON object、max_tokens=600、原关闭思考 extra_body、SDK timeout=8/max_retries=0，外层线程调用总 deadline 8 秒；不阻塞事件循环。派生 client 共享平台 transport，不关闭它以免关闭复用平台 client。

最近最多五条 user/assistant 历史加本轮原话，共六条；每条正文最多 600 字，按时间顺序加「主人：」「你：」前缀，历史描述行保留，不传系统人设/私有记忆。只有 draw 严格 bool true 且 trim 后有效 prompt 才画；无效可选枚举丢弃。按 R1 测试清单，draw=true 的空/超长 prompt 属 error；draw=false 为 no。异常日志/trace 仅类型与耗时，无对话/描述。

判断器模块与路由经另一 subagent 只读交叉审查，未发现遗漏。插件仅给任务前旧测试固定 no，本任务六个新测试文件仍验证真实实现的离线桩；插件禁止 DNS、AF_INET/AF_INET6 connect/connect_ex，保留 AF_UNIX/ASGI/MockTransport，按 `-p` 显式加载。插件本身有先 RED 后 GREEN 的验证。

### 先 RED 再修改的实际记录

命令均在 backend，使用已有 `.venv/bin/python`。没有为补充已满足的验证而人为破坏实现。

| 批次与命令 | RED 实际输出 / 退出码 | GREEN 实际输出 / 退出码 |
| --- | --- | --- |
| `python -m pytest -q tests/test_image_planner.py --tb=line` | `48 failed in 0.17s` / 1，接口与常量不存在 | `48 passed in 0.33s` / 0 |
| 聊天文件首组（gate/planner draw/平台基线恢复） | `8 failed, 13 passed, 78 deselected` / 1 | 后续完整文件 `119 passed, 14 warnings in 1.24s` / 0 |
| 聊天文件 R1 route 分组 | `20 failed` / 1，模式/helper缺失、no仍工具、error未回旧段、镜子先检测 | 完整文件如上 / 0；重复纯桩RED为0.84秒，见纪律偏差说明 |
| `python -m pytest -q tests/test_byok_planner_r1.py --tb=short` | `54 failed, 6 passed, 14 warnings in 1.95s` / 1（其中插件9项文件缺失） | 初版 `60 passed, 14 warnings in 1.12s` / 0 |
| 插件自测分组 | 插件相关9项包含在上行RED中 | `9 passed, 51 deselected in 0.78s` / 0 |
| BYOK helper 模式防线7配置 | `7 failed, 60 deselected in 0.80s` / 1，直接helper仍给非native工具 | 完整带插件 `67 passed, 14 warnings in 1.09s` / 0 |
| `python -m pytest -q tests/test_chat_image_tool_docs.py --tb=line` | `6 failed, 13 passed in 0.14s` / 1，六文档缺两模式/数据流说明 | `19 passed in 0.14s` / 0 |

判断器与既有 native 新测试联合回归：`89 passed in 0.93s` / 0。此前工具定义、执行核心、client、前端、人设/文档的 RED→GREEN 记录见 [R0 报告快照](acceptance/r0-report.md)，当前结果以本报告为准。

### 离线纪律偏差

首次 R1 路由 RED 中 5 条 error 回退测试漏设平台回复流桩，旧实现触达 SDK 并报 `APIConnectionError`。聊天层仅记录类型，没有底层 cause 链，无法证明未尝试 DNS/TCP 或未连接外部，不能以“未请求成功”充当“不发起真实网络请求”。没有为取证复发请求。随后在该新文件加入 socket connect/connect_ex 硬拦截，默认 planner/平台回复及 HTTP 用例明确离线桩；再跑 RED 的 20 项均在纯桩下失败，后续 GREEN 与最终验收使用隔离测试。已向用户说明，这次偏差保留在报告中；没有声称硬约束全程满足。

## 5. 第 5 节验收：实际输出与退出码

所有最终验收在代码冻结后执行。静态检查在根目录，pytest/pip 在 backend，tsc/eslint 在 frontend；使用现有虚拟环境，`NPM_CONFIG_OFFLINE=true`，pip 临时可写缓存，无安装操作。每条执行参数与退出码见 [r1-results.json](acceptance/r1-results.json)，静态输出见 [r1-static-checks.txt](acceptance/r1-static-checks.txt)。完整输出仅规范化本机路径为仓库相对路径、`<python-stdlib>` 或 `<pytest-temp>`，不改其余文本。旧 `acceptance/5.*` 是 R0 历史输出，R1 以 `r1-*` 为准。

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
?? backend/tests/test_byok_planner_r1.py
?? backend/tests/test_chat_image_tool.py
?? backend/tests/test_chat_image_tool_docs.py
?? backend/tests/test_chat_image_tool_frontend.py
?? backend/tests/test_image_planner.py
?? docs/tasks/2026-10-10-chat-image-tool/
```

均属于允许范围；插件、规格与报告/归档在任务目录内。

### 5.2 受保护文件与既有测试

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

`git diff --exit-code -- 'backend/tests/*.py' ':!backend/tests/conftest.py'`，实际输出为空，退出码 **0**。conftest 去掉指定新增行后与基线全文相同。`git diff --check` 输出为空，退出码 **0**。

### 5.3 面板默认常量

`grep -n "DEFAULT_IMAGE_MODEL = " backend/tools/image_generation.py`，退出码 **0**，实际输出：

```text
71:DEFAULT_IMAGE_MODEL = "qwen-image-3.0"
```

### 5.4a 默认全量

```bash
python -m pytest -q
```

由 conftest 默认关闭。退出码 **1**，实际摘要（[完整输出](acceptance/r1-5.4a-default.txt)）：

```text
1 failed, 3235 passed, 6 skipped, 14 warnings, 5 errors in 75.83s (0:01:15)
```

基线2936 + 新增311 = 3247。3235 passed + 1 failed + 5 errors + 6 skipped = 3247；12 个非passed均为端口/回环权限，按5.4a允许沙箱内忽略并由作者方补验，未把它们记为通过。失败/报错节点与下述5.4b环境项相同。六个skip来自既有 `test_byok_client.py::test_r1_watchdog_real_loopback` 的两个provider参数、`test_r2_loopback_interrupt_race` 的两个provider×两个interruption参数，原用例bind被拒后自行skip。

### 5.4b 开关开启，按 R1 加载插件

```bash
PYTHONPATH=../docs/tasks/2026-10-10-chat-image-tool FIONA_CHAT_IMAGE_TOOL=1 python -m pytest -q -p image_planner_stub
```

退出码 **1**，实际摘要（[完整输出与 traceback](acceptance/r1-5.4b-on.txt)）：

```text
33 failed, 3203 passed, 6 skipped, 14 warnings, 5 errors in 76.59s (0:01:16)
```

完整失败逐条如下。中文参数仅将pytest的 `\uXXXX` 还原，原始节点名保留于完整输出；每个参数化失败单列。旧生图行为差异与环境阻断分开解释，不把环境阻断称作允许的行为差异，也不宣称全量通过。

| 序号 | FAILED 用例 | 逐条原因 |
| --- | --- | --- |
| 1 | `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image]` | 该旧用例使用 Claude 原生模式；旧断言要求不调用 BYOK，实际交给带 generate_image 工具的 BYOK 回复。假回复仅文字、没有工具调用，故不生图。属于保留的原生模式行为变化。 |
| 2 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]` | 旧断言要求生图 pending 补参直接 generate_image；原生新路径清 pending 后交给主回复，假回复未调用工具，generated 为空。 |
| 3 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]` | 失败在制造 pending 的准备步骤：旧断言要求“帮我画张图”建立 generate_image pending，实际为 None。新路径不新建；尚未到后续零余额/weather 守卫，非其回归。 |
| 4 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]` | 失败在制造 pending 的准备步骤：旧断言要求“帮我画张图”建立 generate_image pending，实际为 None。新路径不新建；尚未到后续零余额/weather 守卫，非其回归。 |
| 5 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[帮我生成一张青灰薄雾古庙图片，横版16:9-16:9]` | 旧断言要求候选确认后用原句/比例直接生图；验收插件将平台判断器固定为不画，跳候选并进普通文字回复，image_stub 调用列表为空。 |
| 6 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[画一只趴在窗台的猫-1:1]` | 旧断言要求候选确认后用原句/比例直接生图；验收插件将平台判断器固定为不画，跳候选并进普通文字回复，image_stub 调用列表为空。 |
| 7 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[请帮我做一张咖啡店海报，竖版-9:16]` | 旧断言要求候选确认后用原句/比例直接生图；验收插件将平台判断器固定为不画，跳候选并进普通文字回复，image_stub 调用列表为空。 |
| 8 | `tests/test_chat_image_generation.py::test_image_prompt_question_then_description_generates_only_description` | 旧断言要求固定“想生成什么画面”追问与 pending；判断器固定不画后正常文字回复为“测试”，不新建生图 pending。 |
| 9 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-帮我生成图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 10 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-帮我生成一张图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 11 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-画一张图]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 12 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-给我画一幅画]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 13 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-帮我生成图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 14 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-帮我生成一张图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 15 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-画一张图]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 16 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-给我画一幅画]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 17 | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` | 测试准备阶段 asyncio.start_server 在 bind(127.0.0.1, 0) 抛 PermissionError；未到上游断开断言。环境受限，需沙箱外复验。 |
| 18 | `tests/test_image_intent_precision.py::test_model_confirmed_candidate_generates_once_and_charges` | 旧断言要求意图确认后直接 generate("画一只猫", "16:9")；判断器固定不画后跳候选，generate_image 意图视为无意图，调用列表为空。 |
| 19 | `tests/test_image_intent_precision.py::test_confirmed_candidate_without_model_prompt_uses_original_text[classified0]` | 旧断言要求分类器无 prompt 时仍使用原句直接生图；判断器固定不画后不走旧候选直接生成，调用列表为空。 |
| 20 | `tests/test_image_intent_precision.py::test_confirmed_candidate_without_model_prompt_uses_original_text[classified1]` | 旧断言要求分类器无 prompt 时仍使用原句直接生图；判断器固定不画后不走旧候选直接生成，调用列表为空。 |
| 21 | `tests/test_image_intent_precision.py::test_model_missing_prompt_overrides_populated_regex_candidate` | 旧断言要求分类器 missing prompt 触发固定追问和 pending；判断器固定不画后普通回复为“测试”，生图意图不建立 pending。 |
| 22 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[画一只在午夜灯塔边等船的黑猫，背景是潮汐与蓝色纸灯，横版16:9-9:16-16:9-True]` | 旧断言要求将本轮完整原文直接生图并按原文取比例；判断器固定不画后普通回复，旧 generate_image 意图被忽略，未发起生图。 |
| 23 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[午夜灯塔旁的黑猫与蓝色纸灯，请将海雾画出来-9:16-9:16-False]` | 旧断言要求将本轮完整原文直接生图并按原文取比例；判断器固定不画后普通回复，旧 generate_image 意图被忽略，未发起生图。 |
| 24 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[山顶风车与落日，请给我一幅正方形插画-9:16-1:1-False]` | 旧断言要求将本轮完整原文直接生图并按原文取比例；判断器固定不画后普通回复，旧 generate_image 意图被忽略，未发起生图。 |
| 25 | `tests/test_image_intent_precision.py::test_text_ratio_precedes_chat_field_but_image_button_keeps_selection[chat-16:9-1]` | 旧 chat 分支要求原句直接生成 16:9；判断器固定不画，未生图。只有 chat 参数失败，显式面板 image 参数通过。 |
| 26 | `tests/test_image_intent_precision.py::test_rejected_candidate_cannot_fill_old_image_prompt` | 已正常回复且未生图；旧断言要求生图 pending 仍存在，R1 继续路由要求非取消文本清除它，实际为 None。 |
| 27 | `tests/test_image_intent_precision.py::test_confirmed_candidate_bypasses_active_mirror` | 实际首个失败断言为 calls == ["画一只猫"]，calls 为空。判断器固定不画后跳过旧候选确认并继续 detect_mode；该旧禁用桩抛断言，路由在分类前中止。判断器判画时绕过镜子由新增用例验证。 |
| 28 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-omitted]` | 旧断言要求 chat_intent 直接生成一图且跟随面板选择；R1 判断器固定不画，generate_image 意图被忽略，图片数为 0；显式 image/image_edit 参数通过。 |
| 29 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-default]` | 旧断言要求 chat_intent 直接生成一图且跟随面板选择；R1 判断器固定不画，generate_image 意图被忽略，图片数为 0；显式 image/image_edit 参数通过。 |
| 30 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-seedream]` | 旧断言要求 chat_intent 直接生成一图且跟随面板选择；R1 判断器固定不画，generate_image 意图被忽略，图片数为 0；显式 image/image_edit 参数通过。 |
| 31 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-omitted]` | 旧断言要求 pending 补参直接生成一图且跟随面板选择；本句未命中预筛，不调用判断器，R1 清遗留生图 pending 后普通回复，图片数为 0；显式 image/image_edit 参数通过。 |
| 32 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-default]` | 旧断言要求 pending 补参直接生成一图且跟随面板选择；本句未命中预筛，不调用判断器，R1 清遗留生图 pending 后普通回复，图片数为 0；显式 image/image_edit 参数通过。 |
| 33 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-seedream]` | 旧断言要求 pending 补参直接生成一图且跟随面板选择；本句未命中预筛，不调用判断器，R1 清遗留生图 pending 后普通回复，图片数为 0；显式 image/image_edit 参数通过。 |

ERROR 逐条如下：

| ERROR 用例 | 逐条原因 |
| --- | --- |
| `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` | local_fetch_server 的 ThreadingHTTPServer → socket.bind(127.0.0.1, 0) 抛 PermissionError，fixture 准备失败；需沙箱外复验。 |

33 条FAILED中，32条为规格允许的旧聊天生图预期变化，均来自明确允许的四个文件；另1条FAILED与5条ERROR为端口bind权限阻断。除环境项外未发现其他功能失败。六个skip原因与默认全量相同，需沙箱外复验。

### 5.4c 本任务全部新测试

```bash
python -m pytest -q tests/test_chat_image_tool.py tests/test_byok_image_tool.py tests/test_chat_image_tool_docs.py tests/test_chat_image_tool_frontend.py tests/test_image_planner.py tests/test_byok_planner_r1.py
```

退出码 **0**，实际完整输出：

```text
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
.......................                                                  [100%]
=============================== warnings summary ===============================
tests/test_chat_image_tool.py: 14 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
311 passed, 14 warnings in 2.26s
```

### 5.5 依赖

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

警告数与基线相同：25 warnings / 0 errors。

## 6. 未完成或需要人工确认

- R1 规格内实现、离线测试及全部验收命令已完成，没有未修复的新测试失败或待裁定的实现冲突。测试离线纪律偏差如第4节所述，不能追溯补成全程合规。
- 作者方须在沙箱外重跑默认与开启开关全量，确认各6个权限失败/报错和6个自行skip的旧回环测试；本环境不能给出通过结论。开启开关的旧生图行为差异逐条已解释，未改旧测试输入/断言。
- 真实Key模型评测、构建与浏览器走查按规格由作者方在沙箱外完成；本轮不声称真实厂商效果或浏览器体验已验收，也未安装包、启动服务或运行build/dev。

本轮任务曾因3.2“旧路由字节不变”与原4.10第8条“所有possible保留pending”的冲突暂停一次，已由 [05-fix-r0.md](05-fix-r0.md) 裁定选项1；R1按 [05-fix-r1.md](05-fix-r1.md) 完成后续调整，未回滚作者允许保留的其他改动。


## R2

日期：2026-10-10。依据 [05-fix-r2.md](05-fix-r2.md) 与 [04-review.md](04-review.md)，R2-1 至 R2-9 全部完成。前三个子代理按文件独占并行，未传 model 或 reasoning_effort；主代理负责文档、验收与本节。两名子代理随后只读交叉复核，未发现遗漏。本节只追加，前面各节保持原有 38639 字节，SHA-256 为 `e16be6aaf65b22b52bbb138d2dd204c839c55c0726e0cafcb11cf6c2d9e9fc3a`；前文的旧截断说明与验收数字由本节更新。

### 修改与新增文件

| 类型 | R2 文件 | 用途 |
| --- | --- | --- |
| 后端代码修改 | `backend/services/chat_service.py` | 多轮判断器调用、清 pending、通知与 trace 来源 |
| 后端代码修改 | `backend/byok/client.py`、`backend/services/image_tool.py` | 精确 SDK 异常分类、本轮首尾截断 |
| 后端代码修改 | `backend/routers/chat.py` | 仅三条聊天 SSE 路径的响应头 |
| 前端修改 | `frontend/components/ChatModelSection.tsx` | R2 指定静态隐私段落 |
| 文档与配置修改 | `README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example` | 调用时机、截断、旧路由恢复与代理联调说明 |
| 本任务已有新测试修改 | `backend/tests/test_chat_image_tool.py`、`backend/tests/test_byok_planner_r1.py`、`backend/tests/test_byok_image_tool.py`、`backend/tests/test_image_planner.py`、`backend/tests/test_chat_image_tool_frontend.py`、`backend/tests/test_chat_image_tool_docs.py` | 回归覆盖与断言加强；每个文件独占修改 |
| 新测试新增 | `backend/tests/test_chat_image_tool_headers.py` | 普通、Reserved、_text_stream 响应头 |
| 验收插件修改 | `docs/tasks/2026-10-10-chat-image-tool/image_planner_stub.py` | 新 headers 测试加入任务测试名单；保留旧测试固定判不画与网络硬拦截 |
| 报告与证据新增 | 本报告末尾 R2、`acceptance/r2-*.txt`、`acceptance/r2-results.json` | 8 份 RED/GREEN、6 份验收输出、静态检查与命令退出码 |

R2 没有改 persona、image_generation、聊天气泡、主页面、next.config 或任何受保护文件。81 个任务前既有测试文件（不含 conftest）内容与基线相同，输入及断言未改；conftest 仍只保留原指定新增一行。

### R2-1 至 R2-9 逐项对应

| 项目 | 实现与验证 | 状态 |
| --- | --- | --- |
| R2-1 | 入口先读 pending；生图 pending 的取消短语直接走现有取消逻辑；本轮线索、生图 pending、history 最后一条 assistant 的生图线索任一成立即调用。取消原正则抽成常量两处共用，FOLLOWUP 常量逐字且忽略大小写。测试覆盖未命中预筛的补充 draw/no、7 种取消、描述/追问/提示词/大写 PROMPT、末尾 user 及无关 assistant；error 回原旧路由。 | 完成 |
| R2-2 | 判断器要画时无条件 clear_pending，再执行生图；测试先留 web_search pending、出图后确认清空，再发评价句确认不执行搜索。 | 完成 |
| R2-3 | 仅精确 ValueError 且指定固定前缀算非法工具参数；子类和其他 ValueError 先按 timed_out/closed，否则原样抛。真实 anthropic SDK + MockTransport 覆盖无 tool_use 的坏 SSE JSON 与非法 UTF-8；固定前缀正例 invalid 且不泄 JSON 日志。 | 完成 |
| R2-4 | 共享 `Cache-Control: no-cache, no-transform` 与 `X-Accel-Buffering: no`，仅应用于普通、Reserved 与 _text_stream。现有 client 夹具离线覆盖三条路径；DEPLOYMENT 联调段说明避免 Next 压缩缓冲。 | 完成 |
| R2-5 | 设置页逐字替换为返修单静态段落；七个短语及完整段落断言。 | 完成 |
| R2-6 | 历史每条最多 600 字，本轮原话最多 1500 字（超长时保留首尾）；超长严格按前 1000 + `……` + 后 500 实现。测试覆盖 600/601/1499/1500/1501/2400 边界。五份业务文档与 .env 同步，另本节记录更新；R1 判断器提示词与预筛正则一字未改。 | 完成 |
| R2-7 | 从 git show 7ac7b57 恢复完整旧路由原文，段首注明适用范围；原生与判断器模式句逐字改正，测试比较完整基线段落。 | 完成 |
| R2-8 | 空前导通知的 SSE/正文没有起始双换行；有前导保持原样。执行核心新增 `image_source="tool"`，planner 传 planner，删除入口逐事件与 finally 回写；首事件前及最终 trace 都验证。 | 完成 |
| R2-9 | success 恰一张图、正文包含完成和描述、ASGI /chat 用例验证 20→10 草莓；done 恰一次，requests 非空后才断言无 tools；关闭/危机测试走真实 run_chat 且资源精确一次。无 tools 请求加载 Git 基线客户端构造比较，OpenAI 额外比 SDK 实际请求字节；日志用唯一特征串并核对只含类型/耗时。各项回归测试均补齐。 | 完成 |

超长本轮按作者明确公式保留 1500 字原文，额外插入两字符 `……` 标记（构造后的片段共 1502 字），未改动公式或 R1 固定文本。此处是测试/说明细节，无待裁定实现冲突。

### 先 RED 再修改的实际记录

所有 R2 RED 在 socket.connect、connect_ex 与 DNS 硬拦截加入后运行；SDK 用 MockTransport，路由/HTTP 流、判断器、危机分类与外部执行均完整打桩。没有真实网络请求、安装包、build/dev、启动后端或真实 Key 评测。前文 R1 纪律偏差保留，不以 R2 的离线运行改写历史记录。

| 分组（backend 下执行） | RED 实际输出 / 退出码 | GREEN 实际输出 / 退出码 | 证据 |
| --- | --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/test_chat_image_tool.py tests/test_byok_planner_r1.py` | `14 failed, 197 passed, 14 warnings in 1.92s` / 1 | `211 passed, 14 warnings in 1.52s` / 0 | [RED](acceptance/r2-route-red.txt)、[GREEN](acceptance/r2-route-green.txt) |
| `.venv/bin/python -m pytest -q tests/test_byok_image_tool.py tests/test_image_planner.py` | `11 failed, 89 passed in 1.08s` / 1 | `100 passed in 1.00s` / 0 | [RED](acceptance/r2-sdk-red.txt)、[GREEN](acceptance/r2-sdk-green.txt) |
| `.venv/bin/python -m pytest -q tests/test_chat_image_tool_headers.py tests/test_chat_image_tool_frontend.py` | `4 failed, 16 passed, 14 warnings in 1.65s` / 1 | `20 passed, 14 warnings in 1.36s` / 0 | [RED](acceptance/r2-headers-red.txt)、[GREEN](acceptance/r2-headers-green.txt) |
| `.venv/bin/python -m pytest -q tests/test_chat_image_tool_docs.py` | `14 failed, 13 passed in 0.18s` / 1 | `27 passed in 0.17s` / 0 | [RED](acceptance/r2-docs-red.txt)、[GREEN](acceptance/r2-docs-green.txt) |

### 全部验收命令、实际输出与退出码

静态检查在仓库根目录，pytest/pip 在 backend，tsc/eslint 在 frontend，使用已存在的虚拟环境。`NPM_CONFIG_OFFLINE=true`、`PIP_NO_INDEX=1`，无安装操作。为两轮全量都提供连接硬拦截，默认轮额外用 `PYTEST_PLUGINS=image_planner_stub` 加载同一离线插件，FIONA_CHAT_IMAGE_TOOL 未设置，conftest 默认仍为 0；它的判不画桩不影响关闭开关的旧路由。开启轮按修订单显式 `-p image_planner_stub`；插件仅对任务前旧测试固定判不画，七份任务新测试保留自己的决策/SDK 桩。共用 `PYTHONPATH=../docs/tasks/2026-10-10-chat-image-tool`、`PYTEST_ADDOPTS=-ra`，后者仅显示所有非通过项与 skip 原因。两轮全量各执行一次。

完整命令、环境、耗时与退出码见 [r2-results.json](acceptance/r2-results.json)，原始输出只规范化本机路径，其他内容原样归档。

| 验收 | 命令 | 实际输出 | 退出码 | 证据 |
| --- | --- | --- | --- | --- |
| 5.4a-default | `python -m pytest -q` | `1 failed, 3282 passed, 6 skipped, 14 warnings, 5 errors in 74.95s (0:01:14)` | 1 | [完整输出](acceptance/r2-5.4a-default.txt) |
| 5.4b-on | `FIONA_CHAT_IMAGE_TOOL=1 python -m pytest -q -p image_planner_stub` | `33 failed, 3250 passed, 6 skipped, 14 warnings, 5 errors in 74.86s (0:01:14)` | 1 | [完整输出](acceptance/r2-5.4b-on.txt) |
| 5.4c-new | `python -m pytest -q tests/test_chat_image_tool.py tests/test_byok_image_tool.py tests/test_chat_image_tool_docs.py tests/test_chat_image_tool_frontend.py tests/test_image_planner.py tests/test_byok_planner_r1.py tests/test_chat_image_tool_headers.py` | `358 passed, 14 warnings in 2.44s` | 0 | [完整输出](acceptance/r2-5.4c-new.txt) |
| 5.5-pip-check | `python -m pip check` | `No broken requirements found.` | 0 | [完整输出](acceptance/r2-5.5-pip-check.txt) |
| 5.6-tsc | `npx tsc --noEmit` | `（无输出）` | 0 | [完整输出](acceptance/r2-5.6-tsc.txt) |
| 5.6-eslint | `npx eslint .` | `✖ 25 problems (0 errors, 25 warnings)` | 0 | [完整输出](acceptance/r2-5.6-eslint.txt) |

5.1 `git status --porcelain`（exit 0）：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/byok/client.py
 M backend/persona.py
 M backend/routers/chat.py
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
?? backend/tests/test_byok_planner_r1.py
?? backend/tests/test_chat_image_tool.py
?? backend/tests/test_chat_image_tool_docs.py
?? backend/tests/test_chat_image_tool_frontend.py
?? backend/tests/test_chat_image_tool_headers.py
?? backend/tests/test_image_planner.py
?? docs/tasks/2026-10-10-chat-image-tool/
```

5.2 受保护文件检查 `git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/database.py backend/byok/crypto.py backend/byok/url_safety.py backend/byok/store.py backend/routers/chat_model.py backend/utils/safe_http.py` 无输出、exit 0。

`git diff --stat -- backend/tools`（exit 0）：

```text
 backend/tools/image_generation.py | 22 +++++++++++++++++-----
 1 file changed, 17 insertions(+), 5 deletions(-)
```

`git diff -- backend/tests/conftest.py`（exit 0）：

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

`git diff --name-only -- backend/tests` 仅输出 `backend/tests/conftest.py`、exit 0；额外逐文件与 Git 基线比较确认其余 81 份既有 Python 测试零变化。`git diff --check` 无输出、exit 0。`routers/chat.py` 全文件对比仅包含 R2-4 常量及三处使用。六个基线聊天函数逐字一致，旧 run_chat 段仍 7434 UTF-8 字节一致，R1 两固定文本与 R2 前快照一致。完整证据见 [r2-static-checks.txt](acceptance/r2-static-checks.txt)。

5.3 `grep -n "DEFAULT_IMAGE_MODEL = " backend/tools/image_generation.py`（exit 0）：

```text
71:DEFAULT_IMAGE_MODEL = "qwen-image-3.0"
```

5.5 输出 `No broken requirements found.`，exit 0。5.6 tsc 无输出、exit 0；ESLint `✖ 25 problems (0 errors, 25 warnings)`，exit 0，warnings 未增加。

### 5.4a 默认全量的全部非通过项

`1 failed, 3282 passed, 6 skipped, 14 warnings, 5 errors in 74.95s (0:01:14)`，exit 1。2936 个任务前用例 + 358 个任务新用例 = 3294；3282 passed + 1 failed + 5 errors + 6 skipped = 3294。12 项均因沙箱回环端口绑定权限；没有新增测试失败。不得将环境阻断或 skip 记作通过，需作者方在沙箱外补验。

| 状态 | 用例 | 原因 |
| --- | --- | --- |
| FAILED | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` | asyncio.start_server 在 bind(127.0.0.1, 0) 抛 PermissionError；未到断开/槽位断言，需沙箱外复验。 |

其余 5 条 ERROR 与 6 条 SKIPPED 全部逐条列在下方，与开启轮相同。

### 5.4b 开关开启的失败清单与逐条原因

`33 failed, 3250 passed, 6 skipped, 14 warnings, 5 errors in 74.86s (0:01:14)`，exit 1。33 条 FAILED 中 32 条来自四个允许的旧聊天生图文件，编码了被规格改变的正则/意图/pending 直接生图预期；另 1 条 FAILED 与 5 条 ERROR、6 条 SKIPPED 属沙箱回环环境阻断。没有其他功能文件失败，358 项本任务新测试全部通过。

| 序号 | FAILED 用例 | 逐条原因 |
| --- | --- | --- |
| 1 | `tests/test_byok_chat.py::test_paid_branches_still_cost_ten[image]` | 该旧用例使用 Claude 原生模式；旧断言要求不调用 BYOK，实际交给带 generate_image 工具的 BYOK 回复。假回复仅文字、没有工具调用，故不生图。属于保留的原生模式行为变化。 |
| 2 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_fill-10]` | 旧断言要求生图 pending 补参直接 generate_image；原生新路径清 pending 后交给主回复，假回复未调用工具，generated 为空。 |
| 3 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-0]` | 失败在制造 pending 的准备步骤：旧断言要求“帮我画张图”建立 generate_image pending，实际为 None。新路径不新建；尚未到后续零余额/weather 守卫，非其回归。 |
| 4 | `tests/test_byok_chat.py::test_r1_pending_api_free_actions_and_paid_guards[image_new_tool-10]` | 失败在制造 pending 的准备步骤：旧断言要求“帮我画张图”建立 generate_image pending，实际为 None。新路径不新建；尚未到后续零余额/weather 守卫，非其回归。 |
| 5 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[帮我生成一张青灰薄雾古庙图片，横版16:9-16:9]` | 旧断言要求候选确认后用原句/比例直接生图；验收插件将平台判断器固定为不画，跳候选并进普通文字回复，image_stub 调用列表为空。 |
| 6 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[画一只趴在窗台的猫-1:1]` | 旧断言要求候选确认后用原句/比例直接生图；验收插件将平台判断器固定为不画，跳候选并进普通文字回复，image_stub 调用列表为空。 |
| 7 | `tests/test_chat_image_generation.py::test_natural_request_precedes_mirror_and_old_pending[请帮我做一张咖啡店海报，竖版-9:16]` | 旧断言要求候选确认后用原句/比例直接生图；验收插件将平台判断器固定为不画，跳候选并进普通文字回复，image_stub 调用列表为空。 |
| 8 | `tests/test_chat_image_generation.py::test_image_prompt_question_then_description_generates_only_description` | 旧断言要求固定“想生成什么画面”追问与 pending；判断器固定不画后正常文字回复为“测试”，不新建生图 pending。 |
| 9 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-帮我生成图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 10 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-帮我生成一张图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 11 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-画一张图]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 12 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing0-给我画一幅画]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 13 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-帮我生成图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 14 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-帮我生成一张图片]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 15 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-画一张图]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 16 | `tests/test_chat_image_generation.py::test_empty_scene_candidate_asks_without_charge_then_generates_from_followup[model_missing1-给我画一幅画]` | 旧断言要求固定追问、建立 pending、后续补参直接生图；平台判断器固定不画，首轮正常文字回复为“测试”，不新建 pending。 |
| 17 | `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot` | 测试准备阶段 asyncio.start_server 在 bind(127.0.0.1, 0) 抛 PermissionError；未到上游断开断言。环境受限，需沙箱外复验。 |
| 18 | `tests/test_image_intent_precision.py::test_model_confirmed_candidate_generates_once_and_charges` | 旧断言要求意图确认后直接 generate("画一只猫", "16:9")；判断器固定不画后跳候选，generate_image 意图视为无意图，调用列表为空。 |
| 19 | `tests/test_image_intent_precision.py::test_confirmed_candidate_without_model_prompt_uses_original_text[classified0]` | 旧断言要求分类器无 prompt 时仍使用原句直接生图；判断器固定不画后不走旧候选直接生成，调用列表为空。 |
| 20 | `tests/test_image_intent_precision.py::test_confirmed_candidate_without_model_prompt_uses_original_text[classified1]` | 旧断言要求分类器无 prompt 时仍使用原句直接生图；判断器固定不画后不走旧候选直接生成，调用列表为空。 |
| 21 | `tests/test_image_intent_precision.py::test_model_missing_prompt_overrides_populated_regex_candidate` | 旧断言要求分类器 missing prompt 触发固定追问和 pending；判断器固定不画后普通回复为“测试”，生图意图不建立 pending。 |
| 22 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[画一只在午夜灯塔边等船的黑猫，背景是潮汐与蓝色纸灯，横版16:9-9:16-16:9-True]` | 旧断言要求将本轮完整原文直接生图并按原文取比例；判断器固定不画后普通回复，旧 generate_image 意图被忽略，未发起生图。 |
| 23 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[午夜灯塔旁的黑猫与蓝色纸灯，请将海雾画出来-9:16-9:16-False]` | 旧断言要求将本轮完整原文直接生图并按原文取比例；判断器固定不画后普通回复，旧 generate_image 意图被忽略，未发起生图。 |
| 24 | `tests/test_image_intent_precision.py::test_natural_image_uses_complete_message_not_model_excerpt[山顶风车与落日，请给我一幅正方形插画-9:16-1:1-False]` | 旧断言要求将本轮完整原文直接生图并按原文取比例；判断器固定不画后普通回复，旧 generate_image 意图被忽略，未发起生图。 |
| 25 | `tests/test_image_intent_precision.py::test_text_ratio_precedes_chat_field_but_image_button_keeps_selection[chat-16:9-1]` | 旧 chat 分支要求原句直接生成 16:9；判断器固定不画，未生图。只有 chat 参数失败，显式面板 image 参数通过。 |
| 26 | `tests/test_image_intent_precision.py::test_rejected_candidate_cannot_fill_old_image_prompt` | 旧断言要求被否决候选后仍保留生图 pending；R2 因 pending 调用判断器，插件固定判不画，继续路由清生图 pending 并正常回复，实际 pending 为 None。 |
| 27 | `tests/test_image_intent_precision.py::test_confirmed_candidate_bypasses_active_mirror` | 实际首个失败断言为 calls == ["画一只猫"]，calls 为空。判断器固定不画后跳过旧候选确认并继续 detect_mode；该旧禁用桩抛断言，路由在分类前中止。判断器判画时绕过镜子由新增用例验证。 |
| 28 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-omitted]` | 旧断言要求 chat_intent 直接生成一图且跟随面板选择；判断器插件固定不画，generate_image 意图被忽略，图片数为 0；显式 image/image_edit 参数通过。 |
| 29 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-default]` | 旧断言要求 chat_intent 直接生成一图且跟随面板选择；判断器插件固定不画，generate_image 意图被忽略，图片数为 0；显式 image/image_edit 参数通过。 |
| 30 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_intent-seedream]` | 旧断言要求 chat_intent 直接生成一图且跟随面板选择；判断器插件固定不画，generate_image 意图被忽略，图片数为 0；显式 image/image_edit 参数通过。 |
| 31 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-omitted]` | 旧断言要求生图 pending 补参直接生成一图并跟随面板选择；R2 已因该 pending 调用判断器，验收插件固定判不画，随后清生图 pending 并普通回复，实际图片数为 0。显式 image/image_edit 参数通过。 |
| 32 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-default]` | 旧断言要求生图 pending 补参直接生成一图并跟随面板选择；R2 已因该 pending 调用判断器，验收插件固定判不画，随后清生图 pending 并普通回复，实际图片数为 0。显式 image/image_edit 参数通过。 |
| 33 | `tests/test_image_model_choice.py::test_selection_reaches_every_image_path_without_changing_default_arguments[chat_pending-seedream]` | 旧断言要求生图 pending 补参直接生成一图并跟随面板选择；R2 已因该 pending 调用判断器，验收插件固定判不画，随后清生图 pending 并普通回复，实际图片数为 0。显式 image/image_edit 参数通过。 |

两轮共同的 ERROR：

| ERROR 用例 | 逐条原因 |
| --- | --- |
| `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive` | 本地 HTTPServer fixture 在 bind(127.0.0.1, 0) 抛 PermissionError（Operation not permitted），未到测试断言；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline` | 本地 HTTPServer fixture 在 bind(127.0.0.1, 0) 抛 PermissionError（Operation not permitted），未到测试断言；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work` | 本地 HTTPServer fixture 在 bind(127.0.0.1, 0) 抛 PermissionError（Operation not permitted），未到测试断言；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline` | 本地 HTTPServer fixture 在 bind(127.0.0.1, 0) 抛 PermissionError（Operation not permitted），未到测试断言；需沙箱外复验。 |
| `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch` | 本地 HTTPServer fixture 在 bind(127.0.0.1, 0) 抛 PermissionError（Operation not permitted），未到测试断言；需沙箱外复验。 |

两轮共同的 SKIPPED（不是通过）：

| SKIPPED 用例 | 逐条原因 |
| --- | --- |
| `tests/test_byok_client.py::test_r1_watchdog_real_loopback[deepseek]` | 既有用例捕获回环 bind 权限拒绝，自行 skip（R1-6 loopback bind is denied by sandbox permissions）。 |
| `tests/test_byok_client.py::test_r1_watchdog_real_loopback[anthropic]` | 既有用例捕获回环 bind 权限拒绝，自行 skip（R1-6 loopback bind is denied by sandbox permissions）。 |
| `tests/test_byok_client.py::test_r2_loopback_interrupt_race[watchdog-deepseek]` | 既有用例捕获回环 bind 权限拒绝，自行 skip；20 次竞态循环需宿主机复验（R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun）。 |
| `tests/test_byok_client.py::test_r2_loopback_interrupt_race[watchdog-anthropic]` | 既有用例捕获回环 bind 权限拒绝，自行 skip；20 次竞态循环需宿主机复验（R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun）。 |
| `tests/test_byok_client.py::test_r2_loopback_interrupt_race[cancel-deepseek]` | 既有用例捕获回环 bind 权限拒绝，自行 skip；20 次竞态循环需宿主机复验（R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun）。 |
| `tests/test_byok_client.py::test_r2_loopback_interrupt_race[cancel-anthropic]` | 既有用例捕获回环 bind 权限拒绝，自行 skip；20 次竞态循环需宿主机复验（R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun）。 |

### 未完成或需要人工确认

R2-1 至 R2-9 无未完成实现、无新测试失败、无规格第 6 节待裁定冲突。默认与开启全量中的 12 项回环环境阻断需要作者方在沙箱外复验；开启轮另外 32 项旧预期失败属于修订单允许的行为变化，未改动旧测试来掩盖。作者方已完成的 R1 真实 Key/端到端/浏览器验收不由本轮重复；R2 no-transform 经真实 Next 代理的到达时序和设置页展示可在作者方下一次走查确认，本轮已验证后端响应头及静态原文。报告前面各节未改写。
