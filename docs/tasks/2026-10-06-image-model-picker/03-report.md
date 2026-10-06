# 实施报告：生图模型选择（2026-10-06）

基于 `main 065e00a`，实现默认 Qwen Image 3.0 与可选 Seedream 5.0 Flash。生图、修图、普通聊天确认后的自然语言生图及待补参数生图均遵循本次选择；计费与退款代码未修改。新增 88 个离线测试；全量共 2026 项。

## 1. 修改文件与行号

| 文件 | 行号 | 改动 |
|---|---|---|
| `backend/tools/image_generation.py` | 42、66、69、98、106、121、247、290、363、380、443、494 | 限制、模型登记与动态配置、公开元数据、方舟请求与错误、尺寸适配、安全参考图读取和生图/修图分流 |
| `backend/routers/image_models.py`（新增） | 1、10 | 登录后的模型列表；仅返回 default/id/label/available |
| `backend/main.py` | 40、150 | 导入并注册模型列表路由，未加入公开路径 |
| `backend/routers/chat.py` | 47 | `image_model` Literal 白名单，省略为 None |
| `backend/services/chat_service.py` | 38、365、565、593、610、627 | 上下文末尾新增默认字段，build_context 透传，保留默认调用形状，非默认追加 model_id，trace 记录模型 id |
| `frontend/app/page.tsx` | 70、408、504、525、534、1507、1610、1814、2258、2274 | 模型状态/存储、登录后列表与兜底、重试快照、三种模式请求体、修图及生图按钮组 |
| `frontend/components/ChatBubble.tsx` | 87 | 仅为 ImageGenerationRetry 增加可选 imageModel |
| `backend/tests/test_image_model_choice.py`（新增） | 1、122、149、173、200、210、270、300、328、343、355、403、429、449、457、465、483、519、541 | 88 个参数化离线用例；默认阻止意外 AsyncClient 出网 |
| `README.md` | 14、26、114、116 | 两模型选择、默认值、修图尺寸、偏好/重试、供应商数据流与原计费 |
| `docs/ARCHITECTURE.md` | 86、94、140、141 | 白名单、透传、方舟适配与响应边界、参考输入上限、隐私与计费 |
| `docs/DEPLOYMENT.md` | 113、114、115、140、538、606 | 环境变量表、方舟开通、第二供应商隐私说明、火山引擎消费告警 |
| `PLAN.md` | 7 | 新增 2026-10-06 生图模型选择小节 |
| `CLAUDE.md` | 10 | 模型行补充生图和修图选择及数据流 |
| `docs/tasks/2026-10-06-image-model-picker/03-report.md`（新增） | 1 | 本报告 |

`02-spec.md` 是任务提供的现存未跟踪输入，没有修改。没有改依赖、lockfile、数据库模型或已有测试。

## 2. 规格逐节对应

| 规格节 | 对应结果 |
|---|---|
| §1 D1–D4 | Seedream 5.0 Flash 对应 `doubao-seedream-5-0-flash-260915`；Qwen 标准版默认；生图/修图/自然语言均跟随选择且本机记住；两者仍扣 10 颗草莓 |
| §2.1 | 使用规定方舟同步接口和请求字段，PNG/Base64 返回；所有验收请求打桩，不调用真实接口 |
| §2.2 | Qwen 请求、下载、域名白名单、PNG 校验与落盘核心函数精确比对保持原样 |
| §3 | 仅白名单文件；已有测试输入/断言零改动；无依赖更新、真实接口调用或 git 写命令；前端修改前已读 AGENTS 和本地 Next use-client / client-side-data-fetching 文档；未运行浏览器 |
| §4.1 | 服务端不可变登记表；调用时读取密钥与模型环境变量；`GET /image-models` 沿用全局鉴权，生产态未登录 401，响应无真实模型名、密钥名称或配置值 |
| §4.2 | ChatRequest Literal 与末尾默认 ChatContext 字段；None/默认 id 原参数调用，Seedream 才传 model_id；image/image_edit/chat 意图确认/pending 全覆盖；不可用安全报错，生产余额验证退款；trace 无提示词 |
| §4.3 | 固定方舟 HTTPS、Bearer、指定 JSON、单次 POST、150 秒总超时、无重试；40MB 有界响应、严格 Base64 解码、既有 PNG/20MB/生成像素校验及原子落盘；一张字符串、多张有序数组；错误按指定类别映射 |
| §4.3 尺寸 | 文生图沿用 _SIZES；跟随图1时 512×512 → 960×960，4000×1000 → 2048×512，真实 4000×2000 → 2048×1024；缩放目标为 8 的倍数并满足像素/比例/每边上限 |
| §4.4 | 两个 role=group/aria-label=图片模型 分段组位于指定位置；原 chip 类和手机 h-10，aria-pressed/disabled/title 完整；try/catch 存储，非法值回默认；账号/会话不重置；列表失败两项可用；失败重试优先本次模型 |
| §4.5 | 五份指定文档全部同步；明确描述和参考图发送给字节跳动火山引擎，方舟需开通，默认 Qwen，计费不变 |
| §5 | 下表逐项覆盖，共 88 个新增测试，所有供应商请求使用 MockTransport，生产 JWT/余额测试使用隔离数据库 |
| §6 | 文件与行号、验收结果及原样输出尾部、git 状态、实现选择与未决事项均见本报告 |
| §7 | A1–A3 已运行；A4/A5 按任务范围留给主会话真实走查及接口验收 |

### §5 测试逐项对应

| 条目 | 证据：新增测试文件行号 |
|---|---|
| 1 登记/可用性/调用时环境变量 | 122、137、149：空白/缺失/非空密钥、两个标签、动态配置及空值回默认 |
| 2 GET 鉴权与信息边界 | 173：真实 JWT，匿名 401，结构与禁止泄露字段 |
| 3 请求白名单 | 193、200：省略为 None，三个模式未知值均 422 |
| 4 默认调用不变与透传 | 210：三模型值 × image/image_edit/chat_intent/chat_pending；严格比较 args/kwargs |
| 5 方舟请求 | 270、300：URL、Bearer、全部指定字段、文生图无 image、1/2/3 张参考图形状及顺序 |
| 6 响应与落盘 | 270、328、343、355、371、380：正常 PNG/真实模型名/尺寸，缺字段、坏 Base64/非 PNG、字节/像素/40MB 上限及无残留 |
| 7 错误映射 | 403：五类审核 code、限流/额度、401/403/404/未开通/欠费/模型错误、其他错误；文案无原 code/message/key/request_id |
| 8 修图尺寸 | 429、449、457、465：小图放大、大图缩小、真实超生成像素参考、8 倍数/比例/上限，Qwen 原拒绝行为 |
| 9 不可用/退款 | 483：未配 ARK 密钥，生图/修图不出网，规定提示，真实预扣后余额仍为 10 |
| 10 trace | 210、483、519、541：真实模型成功 trace、默认/None/Seedream 失败 id、并发忙 id，均无提示词 |

## 3. 验收命令、原样输出尾部与退出码

以下保留输出尾部原文；无输出的命令明确标注。完整诊断含本机路径的部分不进入公开仓库。

### A1 全量后端

在 `backend/` 执行 `python -m pytest -q -p no:cacheprovider`，退出码 **1**。

```text
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2020 passed, 11 warnings, 5 errors in 63.37s (0:01:03)
```

全部 6 个未通过项均是旧用例创建本地 HTTP/TCP 服务器时的 `PermissionError: [Errno 1] Operation not permitted`，未修改其输入或断言。新增 88 项全部通过；1938 + 88 = 2026，已通过 2020 项，剩余 6 项需要主会话在允许绑定端口的环境重跑。

辅助定向验证：在 `backend/` 执行 `python -m pytest -q -p no:cacheprovider tests/test_image_model_choice.py tests/test_image_generation.py tests/test_chat_image_generation.py tests/test_chat_image_editing.py tests/test_chat_multi_image_editing.py tests/test_image_intent_precision.py tests/test_reference_images.py tests/test_beta_billing.py`，退出码 **0**。

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
457 passed, 11 warnings in 9.68s
```

新增测试计数：`python -m pytest --collect-only -q -p no:cacheprovider tests/test_image_model_choice.py`，退出码 **0**。

```text
88 tests collected in 0.16s
```

### A2 已有测试无修改

在仓库根执行 `git diff --stat -- backend/tests`，**无输出**，退出码 **0**。唯一新增测试文件尚未跟踪，因此此命令为空；未修改任何已有测试文件。

### A3 前端

在 `frontend/` 执行 `npx tsc --noEmit`，**无输出**，退出码 **0**。

`npm run lint`，退出码 **0**：

```text
✖ 25 problems (0 errors, 25 warnings)

```

`npm run build`，退出码 **1**。原样尾部：

```text
> Build error occurred
Error [TurbopackInternalError]: [project]/app/globals.css [app-client] (css)

Caused by:
- creating new process
- binding to a port
- Operation not permitted (os error 1)

Debug info:
- Execution of get_all_written_entrypoints_with_issues_operation failed
- Execution of EntrypointsOperation::new failed
- Execution of all_entrypoints_write_to_disk_operation failed
- Execution of output_assets_operation failed
- Execution of <MiddlewareEndpoint as Endpoint>::output failed
- Execution of MiddlewareEndpoint::output_assets failed
- Execution of MiddlewareEndpoint::node_chunk failed
- Execution of *<NodeJsChunkingContext as ChunkingContext>::entry_chunk_group failed
- Execution of Project::server_chunking_context failed
- Execution of *get_server_chunking_context failed
- Execution of Project::module_ids failed
- Execution of whole_app_module_graph_operation failed
- Execution of *Project::get_all_additional_entries failed
- Execution of ModuleGraph::from_graphs failed
- Execution of ModuleGraph::from_graphs_inner failed
- Execution of SingleModuleGraph::new_with_entries failed
- [project]/app/globals.css [app-client] (css)
- Execution of primary_chunkable_referenced_modules failed
- Execution of <CssModule as Module>::references failed
- Execution of parse_css failed
- Execution of <PostCssTransformedAsset as Asset>::content failed
- Execution of PostCssTransformedAsset::process failed
- Execution of evaluate_webpack_loader failed
- creating new process
- binding to a port
- Operation not permitted (os error 1)
    at <unknown> (TurbopackInternalError: [project]/app/globals.css [app-client] (css)) {
  type: 'TurbopackInternalError',
  location: undefined
}
```

上述错误明确发生在 Turbopack CSS 处理器创建进程并绑定端口时，是沙箱限制，需要主会话重跑默认构建。

辅助 `npm run build -- --webpack`，退出码 **0**。原样尾部：

```text
└ ○ /settings


ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand

```

webpack 完成编译、TypeScript、全部 14 个静态页面及构建 trace。`git diff --check` **无输出**，退出码 **0**。

### A4/A5 人工验收

- A4 未运行浏览器；主会话需实际确认两处按钮、手机折行、持久化/切会话、灰色禁用和请求体。
- A5 未调用真实模型；需用户在方舟控制台开通后，由主会话各验收文生图、单图编辑、多图编辑，检查 PNG/无水印并记录耗时。

## 4. Git 状态

`git status --porcelain --untracked-files=all`，退出码 **0**；验证产生的文件已清理。输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/main.py
 M backend/routers/chat.py
 M backend/services/chat_service.py
 M backend/tools/image_generation.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
?? backend/routers/image_models.py
?? backend/tests/test_image_model_choice.py
?? docs/tasks/2026-10-06-image-model-picker/02-spec.md
?? docs/tasks/2026-10-06-image-model-picker/03-report.md
```

## 5. 未决问题与自主实现选择

未完成的是 A1 的 6 个端口受限旧用例、A3 的默认 Turbopack 构建、A4 真界面及 A5 真接口验收；实现项已完成，没有修改计费或为通过测试放宽 Qwen 行为。

以下均为规格未明确之处或实施时自行选择的行为，列出供主会话确认：

1. 把项目「2048×2048」解释为 Seedream 目标每边不超过 2048，同时总像素不超过现有上限。这使 4000×1000 按 §5.8 缩小；极端比例（虽在 1/16–16 范围内）无法同时满足 921600 像素下限时安全报错，不强行改变比例。
2. 缩放目标限定 8 的倍数；任意原比例未必可精确表示，优先选择最接近原比例的合法尺寸，再选择最接近均匀缩放目标的面积。已处于合法范围的原尺寸保持原值，不额外量化。
3. 为满足 §4.3 真实超生成像素参考图可缩小的要求，仅方舟参考输入沿用现有上传的 4000 万像素安全边界；文件授权/安全读取/10MB 限制保留。Qwen 仍使用原 PNG 像素校验，生成结果校验不放宽。
4. 模型登记采用 frozen dataclass；模型列表另设 `routers/image_models.py`，按全局鉴权保护。直接工具调用未知 id 返回安全 ImageGenerationError；HTTP 请求仍由 Literal 返回 422。工具入口也接受 None 作为默认。
5. 在图片尝试开始时统一写入 trace.image_model，而非仅在供应商失败 catch 写入；成功、并发忙及后续错误都可定位选中 id。None 映射为默认 id，成功 trace.model 仍为真实模型名。
6. 模型列表等待页面 hydrate 且有账号后请求；账号变化重新获取可用性，取消旧响应回写，但不主动重置偏好。列表缺少任一已知模型、字段类型不合规也按失败兜底，两项可用；未知条目忽略。已有可用性状态触发的默认回落按规格执行。
7. localStorage 初始化通过 microtask 和 loaded 标记避免默认值提前覆盖旧选择；存储不可用时仅内存保持选择。两按钮组沿用外层已有 gap-2，没有额外分隔符、颜色或样式。
8. 保留原重试触发方式：自然语言生图的并发忙错误发生在生成 status 之前，因此原流程不会展示生图重试按钮；供应商失败在 status 之后，已保存本次模型。未扩展与本单无关的忙错误界面。
9. 报告采用验收输出原样尾部，省略完整诊断中含本机绝对路径的内容，以遵守公开仓库路径限制；默认构建失败后使用规格允许的 webpack 辅助验证。PLAN 新小节置于文档前部便于查看。

10. 默认 Turbopack 构建自动在系统临时目录生成了 panic 日志；未读取其内容，按工作树范围约束未访问该目录清理。后续验证临时目录设在工作树内，工作树内的全部验证产物已清理。

## 第 1 轮返修

按 `05-fix-round1.md` 的 1–7 项完成。以下记录本轮最终行为，并取代第 0 轮报告中相应的尺寸、参考图上限、重试与偏好描述。新增测试文件现有 **114** 个离线用例，比第 0 轮净增 26 项；全量共 **2052** 项（1938 + 114）。已有跟踪测试文件仍为 0 改动，计费逻辑与默认模型调用方式未改。

### 本轮修改文件与返修单逐项对应

本轮修改 10 个文件：`backend/tools/image_generation.py`、`backend/services/chat_service.py`、`backend/routers/image_models.py`、`backend/tests/test_image_model_choice.py`、`frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`README.md`、`docs/ARCHITECTURE.md`、`PLAN.md`、本报告。其余工作区改动沿用第 0 轮，没有在本轮修改。

| 返修项 | 改法与最终行号 |
|---|---|
| 1 修图尺寸 | `backend/tools/image_generation.py:254`：均匀缩放到目标面积，组合附近的 8 倍数，先筛比例误差 ≤1% 的合法候选，再选最接近目标面积者；找不到时才以比例误差优先。面积范围内保持原样。测试 `backend/tests/test_image_model_choice.py:480` 覆盖四组不规则小图端到端面积 ≤下限×1.1；`:497` 覆盖原样保留，`:534` 覆盖缩小面积 ≥上限×0.9，`:502` 覆盖 6 个固定比例各 64 个递增面积样本。 |
| 2 参考图上限 | 删除方舟专用像素校验及 4000 万像素放宽；`backend/tools/image_generation.py:382`、`:411`、`:509` 统一使用原 `_reference_image_bytes` / `_png_dimensions` 和 2048² 总像素上限。测试 `backend/tests/test_image_model_choice.py:543` 同时验证两供应商拒绝超限参考图。`README.md:116`、`docs/ARCHITECTURE.md:94` 同步更正。 |
| 3 单张图错误 | `backend/tools/image_generation.py:341`、`:345`：HTTP 200 缺少 `b64_json` 时将首图对象交给 `_ark_error`，使 `data[0].error` 的审核 code 映射为审核文案。测试 `backend/tests/test_image_model_choice.py:466` 覆盖五类审核 code，并验证 status=200、安全日志与无文件残留。 |
| 4 安全诊断 | `backend/tools/image_generation.py:58` 为异常添加可选供应商属性；`:124` 清洗 code，仅保留 `[A-Za-z0-9._-]` 并截断到 80 字；`:359` 对已有 HTTP 响应的失败统一输出一行 `[image] provider=ark status=... code=...`。`backend/services/chat_service.py:663` 将安全属性写入 trace。测试 `backend/tests/test_image_model_choice.py:435` 覆盖各错误类别，`:620` 通过生产态 /chat + MockTransport 的 404 验证日志、trace、清洗截断、敏感原文缺席及退款。文档 `docs/ARCHITECTURE.md:94` 同步。 |
| 5 重试当前选择 | `frontend/app/page.tsx:1497` 使用当前 `imageModel`，重试描述、比例和有序参考图仍沿用记录；失败轮的模型可保留作记录。`frontend/components/ChatBubble.tsx:285` 的生成按钮 title 改为规定文案，修图 title 同样说明当前选择的模型。`README.md:114`、`docs/ARCHITECTURE.md:86` 同步。 |
| 6 保留用户偏好 | `frontend/app/page.tsx:407` 将保存偏好与按可用性派生的当前选择分开；`:508` 只读存储，`:525` 列表响应只更新可用性，自动回默认不写存储；`:2012` 是唯一存储写入点，位于用户点击处理内。之后获取到可用列表即恢复保存偏好，存储读取和列表响应的先后顺序均不覆盖偏好。`README.md:114`、`docs/ARCHITECTURE.md:86` 同步。 |
| 7 小整理 | `frontend/app/page.tsx:2006` 提取局部按钮片段，`:2265` / `:2275` 复用；`frontend/components/ChatBubble.tsx:83` 导出 `ImageModelId` 联合类型，`:88` 用于重试记录。`backend/routers/image_models.py:12` 增加 `Depends(get_current_user)`。测试 `backend/tests/test_image_model_choice.py:200` 验证 Literal 与登记表一致，`:209` 验证脱离全局中间件仍需登录，`:604` 证明成功路径确实扣 10 颗，`:235` 的 `image_edit_multi` 参数项严格断言有序多图透传及默认 kwargs 为空。`PLAN.md:140` 已移到危机模型复核小节之后。 |

第 5 项按本轮返修单明确修改 `02-spec.md` §4.4 原有“重试时优先用记下的模型”要求：失败提示让用户改选 Qwen，重试应尊重这个改选，因此使用当前界面选中的模型。原规格文件不改，变更依据记录在这里。

### A1–A3 验收、原样输出尾部与退出码

后端使用任务指定的现有虚拟环境解释器，以下以 `python` 代称，不将本机绝对路径写入仓库。设置 `PYTHONDONTWRITEBYTECODE=1`、`PYTHON_DOTENV_DISABLED=1`；`TMPDIR` 和 pytest `--basetemp` 均指向工作树内专用目录，运行后已清理。

**A1 全量后端**：在 `backend/` 执行 `python -m pytest -q -p no:cacheprovider`（另设工作树内 `--basetemp`）。退出码 **1**，原样尾部：

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2046 passed, 11 warnings, 5 errors in 63.64s (0:01:03)
```

六个未通过项均为已有端口用例：五处 `PermissionError: [Errno 1] Operation not permitted`，另一处明确是在绑定 `127.0.0.1` 时被拒绝。与第 0 轮相同，属于沙箱端口限制；114 项新增测试在全量中均通过。

辅助定向测试：`python -m pytest -q -p no:cacheprovider tests/test_image_model_choice.py`（同样隔离临时目录），退出码 **0**，原样尾部：

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
114 passed, 11 warnings in 1.89s
```

**A2 已有测试无修改**：`git diff --stat -- backend/tests`，**无输出**，退出码 **0**。仅第 0 轮新增且未跟踪的 `test_image_model_choice.py` 按返修单补充、调整测试；其他既有测试没有改动。

**A3 前端**：`npx --offline --no-install tsc --noEmit`，**无输出**，退出码 **0**；离线且禁止安装参数确保使用已有依赖。

`npm run lint`，退出码 **0**，原样尾部：

```text
✖ 25 problems (0 errors, 25 warnings)

```

`npm run build`，设置 `NEXT_TELEMETRY_DISABLED=1`、`CI=1`、工作树内 `TMPDIR`。退出码 **1**，原样尾部：

```text
> Build error occurred
Error [TurbopackInternalError]: [project]/app/globals.css [app-client] (css)

Caused by:
- creating new process
- binding to a port
- Operation not permitted (os error 1)

Debug info:
- Execution of get_all_written_entrypoints_with_issues_operation failed
- Execution of EntrypointsOperation::new failed
- Execution of all_entrypoints_write_to_disk_operation failed
- Execution of output_assets_operation failed
- Execution of <MiddlewareEndpoint as Endpoint>::output failed
- Execution of MiddlewareEndpoint::output_assets failed
- Execution of MiddlewareEndpoint::node_chunk failed
- Execution of *<NodeJsChunkingContext as ChunkingContext>::entry_chunk_group failed
- Execution of Project::server_chunking_context failed
- Execution of *get_server_chunking_context failed
- Execution of Project::module_ids failed
- Execution of whole_app_module_graph_operation failed
- Execution of *Project::get_all_additional_entries failed
- Execution of ModuleGraph::from_graphs failed
- Execution of ModuleGraph::from_graphs_inner failed
- Execution of SingleModuleGraph::new_with_entries failed
- [project]/app/globals.css [app-client] (css)
- Execution of primary_chunkable_referenced_modules failed
- Execution of <CssModule as Module>::references failed
- Execution of parse_css failed
- Execution of <PostCssTransformedAsset as Asset>::content failed
- Execution of PostCssTransformedAsset::process failed
- Execution of evaluate_webpack_loader failed
- creating new process
- binding to a port
- Operation not permitted (os error 1)
    at <unknown> (TurbopackInternalError: [project]/app/globals.css [app-client] (css)) {
  type: 'TurbopackInternalError',
  location: undefined
}
```

错误明确来自 Turbopack CSS 处理创建进程时绑定端口，被沙箱拒绝。辅助 `npm run build -- --webpack`，同样禁止遥测并将临时目录留在工作树，退出码 **0**，原样尾部：

```text
└ ○ /settings


ƒ Proxy (Middleware)

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand

```

webpack 完成编译、TypeScript、页面生成与构建 trace。`git diff --check` **无输出**，退出码 **0**。本轮生成的构建目录、panic 日志、测试数据库及临时文件均已清理，构建前已有的 `.next`、`next-env.d.ts` 和构建前的 `tsconfig.tsbuildinfo` 已恢复。前端修改前已读取本地 `frontend/AGENTS.md` 与 Next 的 `05-server-and-client-components.md`、`02-typescript.md`、`03-eslint.md` 文档。

### 最终 Git 状态

`git status --porcelain --untracked-files=all`，退出码 **0**；其中 `02-spec.md`、`04-review.md`、`05-fix-round1.md` 为任务输入，本轮未改。原样输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/main.py
 M backend/routers/chat.py
 M backend/services/chat_service.py
 M backend/tools/image_generation.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
?? backend/routers/image_models.py
?? backend/tests/test_image_model_choice.py
?? docs/tasks/2026-10-06-image-model-picker/02-spec.md
?? docs/tasks/2026-10-06-image-model-picker/03-report.md
?? docs/tasks/2026-10-06-image-model-picker/04-review.md
?? docs/tasks/2026-10-06-image-model-picker/05-fix-round1.md
```

### 未决问题与本轮实现解释

- 功能返修 1–7 已完成。待在允许绑定端口的环境重跑 A1 的 6 个旧用例与默认 Turbopack 构建；A4 浏览器走查和 A5 用户开通后的真实接口验收仍由主会话完成，本轮未启动服务、浏览器或调用真实接口。
- 按第 1 项明确的总面积要求，取消第 0 轮额外的“每边 ≤2048”解释，保留 `2048²` **总像素**上限与 [1/16,16] 比例约束。4000×1000 本已处于总像素范围内，因此保持原样；真实超过总像素上限的参考图按第 2 项在读取阶段拒绝，缩小分支以尺寸函数直接打桩测试覆盖。这取代第 0 轮未决问题 1–3 的相关解释。
- 单调验证采用 6 个固定比例各 64 个递增面积样本，未宣称任意比例、任意边界输入的全域单调；范围内必须原样保留，而范围外需要量化到 8 倍数，二者在边界附近可能产生细小面积跳变。
- 未增加可用性轮询。管理员恢复配置后，在页面加载或账号变化触发的下一次模型列表响应中恢复原偏好；存储读取失败则仅保持内存偏好。
- HTTP 响应后的失败记录实际 status 与清洗 code；未获取 HTTP 响应的连接错误或超时沿用原安全文案，没有伪造供应商状态码。
