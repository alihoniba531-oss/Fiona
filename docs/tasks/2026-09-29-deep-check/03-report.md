# 2026-09-29 深度检查修复报告

基线为 `656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f`。本次只在基线之上修改；未运行 `add/commit/stash/checkout/reset/restore/clean/switch` 等写 Git 状态的命令，未回滚既有未提交改动。未新增依赖或数据库 schema。

## 文件清单

按 `git diff --stat 12b6bf0 27e6806` 统计，deep-check 提交相对 09-25 加固提交改动 **69 个文件**，其中 **45 个修改、24 个新增**：

- 后端实现与配置：`backend/.env.example`、`backend/admin_env.py`、`backend/auth_dep.py`、`backend/database.py`、`backend/exchange_models.py`、`backend/exchange_store.py`、`backend/intent_router.py`、`backend/main.py`、`backend/persona.py`、`backend/routers/agent_exchanges.py`、`backend/routers/auth.py`、`backend/routers/cards.py`、`backend/routers/chat.py`、`backend/routers/hot.py`、`backend/routers/me.py`、`backend/routers/voice.py`、`backend/safety.py`、`backend/services/chat_service.py`、`backend/services/exchange_service.py`、`backend/tools/card_detail.py`、`backend/tools/system_tools.py`、`backend/tools/topic_expand.py`、`backend/tools/travel_plan.py`、`backend/tools/web_search.py`、`backend/utils/media.py`、`backend/utils/safe_http.py`。
- 既有测试与夹具：`backend/tests/conftest.py`、`backend/tests/test_auth_sessions.py`、`backend/tests/test_beta_admin_scripts.py`、`backend/tests/test_card_detail.py`、`backend/tests/test_chat_image_generation.py`、`backend/tests/test_exchange_models.py`、`backend/tests/test_exchange_workflow.py`。
- 前端：`frontend/app/page.tsx`、`frontend/app/plaza/page.tsx`、`frontend/app/settings/page.tsx`、`frontend/lib/auth.ts`、`frontend/lib/useAccountIdentity.ts`、`frontend/next.config.ts`、`frontend/package.json`（仅 `scripts`）。
- 文档：`README.md`、`docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`CLAUDE.md`、`PLAN.md`。

新建的 **24 个文件**：`backend/utils/beijing_time.py`、`backend/utils/dotenv_config.py`、`backend/utils/slow_pool.py`、`backend/utils/traditional_chinese.py`；`backend/tests/test_beijing_time.py`、`test_crisis_resource_paths.py`、`test_dev_loopback.py`、`test_early_env_loading.py`、`test_exchange_isolation.py`、`test_image_intent_precision.py`、`test_plaza_media_brands.py`、`test_safe_http_deadline.py`、`test_traditional_crisis.py`、`test_tts_private_tickets.py`（以上测试均在 `backend/tests/`）；`docs/tasks/2026-09-29-deep-check/00-findings.md`、`02-spec.md`、`03-report.md`、`04-review.md`、`04-review-round2.md`、`04-review-round3.md`、`05-fix-round1.md`、`05-fix-round2.md`、`05-fix-round3.md`、`05-fix-round4.md`（上述文档均在该 deep-check 目录）。原先未跟踪的 09-25 任务文件、`test_beta_session_revival.py` 和 `test_event_loop_slots.py` 不在上述提交差异中。

## T1–T10 对应关系

| 任务 | 实现与设计选择 | 新增测试函数 |
|---|---|---|
| T1 | `explicit_image_intent` 以祈使前缀、绘画动词、量词及图片对象作正向判定；询价、时长、难度、方法、评价及文字产物请求交给模型意图识别。`run_chat` 的抢先接线保留。 | `test_image_request_is_only_a_candidate`（20 例，含 README 示例）、`test_image_discussion_with_null_model_never_generates`（35 例）、`test_comment_reaches_model_intent_classifier_without_image_generation`、`test_model_confirmed_candidate_generates_once_and_charges`。 |
| T2 | `request_public_url` 用单个 monotonic 截止时间覆盖 DNS、连接、响应头、正文和重定向；DNS 放在最多 4 工作线程的独立解析池，连接/滴流头由绝对计时器关闭 socket，正文逐块读取并按剩余时间设置读超时。超时抛 `PublicUrlTimeoutError`，调用方仍按普通抓取失败处理。 | `test_drip_response_obeys_total_wall_clock_deadline`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_slow_resolution_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`。 |
| T3 | 交流上游改用 `AsyncOpenAI`；停止或撤销取消在途 Task，取消后的调用按 discarded 处理，未结束的调用继续占用同用户额度，防止开始→停止循环穿透上限。聊天工具、热点和卡片移入有界慢调用池。默认池 `FIONA_DEFAULT_POOL_WORKERS=32`，给小 CPU 主机的聊天槽位与流读取留余量；慢池 `FIONA_SLOW_POOL_WORKERS=16`，最多再排队 16 个等待执行的任务，隔离外部慢调用。两者可通过环境变量调节。 | `test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`、`test_stop_disconnects_async_upstream_and_releases_user_slot`、`test_rapid_start_stop_never_exceeds_one_inflight_call_per_owner`、`test_revoking_public_agent_cancels_inflight_provider_call`。 |
| T4 | 内置繁简表仅归一危机分类的局部文本；原文继续入库、送模型、显示。映射含规格列出的常见繁体/异体。 | `test_traditional_explicit_risk_is_high`、`test_traditional_related_talk_is_possible`、`test_traditional_everyday_talk_is_not_crisis`、`test_crisis_rule_character_variants_normalize_back_to_rule_characters`（检查 `safety.py` 的 **296** 个规则汉字：有映射 **114** 字、无异体白名单 **182** 字）、`test_specified_traditional_variants_are_mapped`、`test_crisis_normalization_keeps_original_message_available`、`test_traditional_crisis_chat_persists_and_sends_original`。 |
| T5 | 路由内校验前先判级；high 和 possible 在文字、上游错误/空回复、余额不足、会话不存在、预检异常、图片成功/失败、工具、待补和镜子模式的服务端收尾中恰好送达一次资源。high 首事件仍为 `crisis=true`；possible 零余额时先发资源文本再发余额错误且不调用模型、不扣费。失败保留退款语义。 | `test_crisis_normal_reply_provider_error_and_empty_refund`、`test_crisis_zero_balance_never_calls_model`、`test_crisis_precheck_failures_refund_and_stream_resources`、`test_crisis_request_validation_still_streams_resources`、`test_crisis_vision_reply_paths`、`test_possible_crisis_image_generation_and_edit_paths`、`test_high_image_modes_use_support_reply_while_possible_uses_generation`、`test_crisis_tool_pending_and_mirror_paths`（high/possible 各 3 路）、`test_crisis_run_chat_failure_refunds_and_streams_resources`、`test_crisis_classification_used_by_test_corpus`。 |
| T6 | 私聊朗读改为鉴权 `POST /tts/ticket` 传请求体，再以只含随机 ticket 的 GET 流式播放；票据绑定用户、一次性、60 秒有效，进程内保存。前端保留 `<audio>` 流播和下一句预取；丢失/过期会跳过该句。换票限额 20/min，播放不再另扣限额，与原每句流接口 20/min 持平。旧 `text` 查询参数拒绝。 | `test_tts_ticket_requires_login`、`test_tts_ticket_range_probe_then_playback_and_bound_to_user`、`test_tts_ticket_expires_and_legacy_text_query_is_rejected`、`test_tts_synthesize_shares_ticket_use_limit_with_stream`。 |
| T7 | `/auth/logout` 仅 2xx 才清本地身份并跳转；失败留页提示重试。缺本地用户名时以 Cookie 向 `/profile` 做一次回填，401 按既有登录失效处理；主页、设置与广场不再以“默认用户”执行账号操作，主页抽屉待回填后挂载。 | 前端没有测试框架，按规格未新增测试依赖；手工步骤见下节。 |
| T8 | `npm run dev` 绑定 `127.0.0.1`，`dev:lan` 显式开放；`allowedDevOrigins` 默认仅本机，额外来源由 `FIONA_ALLOWED_DEV_ORIGINS` 配置。DEV 鉴权、测试登录/OTP、`/users`、WebSocket `dev_user`、开发文档及媒体旁路按 ASGI `client.host` 判断回环，不信任代理头；生产 JWT 行为保持。 | `test_dev_http_shortcuts_reject_remote_peer_even_with_proxy_headers`、`test_dev_websocket_user_query_rejects_remote_peer`、`test_production_authentication_still_accepts_valid_cookie_from_remote`。 |
| T9 | 服务在导入数据库等模块前按 `FIONA_ENV_FILE` 或默认 `backend/.env` 加载 dotenv，显式环境变量优先；管理脚本使用同一默认与 DB 路径规则。广场 ISO BMFF 只接受已知视频 brand，HEIC/AVIF 给中文转码提示，未知 brand 拒绝。发布失败显示后端 `detail`，保留弹窗文案与标签。面向用户的五个工具及 Persona 使用 `Asia/Shanghai`，内部计时不动。 | `test_selected_dotenv_is_loaded_before_database_and_uploads_import`；`test_image_bmff_brands_are_not_videos`、`test_known_video_bmff_brands_are_accepted`、`test_quicktime_brand_is_mov_and_unknown_brand_is_rejected`、`test_image_compatible_brand_overrides_video_major_brand`、`test_plaza_rejects_image_bmff_with_conversion_hint`；`test_user_facing_dates_use_beijing_when_process_is_new_york`。发布弹窗按规格用手工步骤验证。 |
| T10 | 部署前置条件补 ffmpeg、`sqlite3` CLI、SQLite ≥3.35 的安装/自检；备份命令先设 `umask 077`，产物权限按 600 创建。README、架构、CLAUDE、PLAN 与环境变量模板同步本任务行为；部署继续明确单后端进程。 | 文档与配置差异检查见下节。 |

文件数与清单核对命令：`git diff --stat 12b6bf0 27e6806`、`git diff --name-status 12b6bf0 27e6806`。规则字覆盖数及主表测试名用以下脚本核对，输出为 `296 114 182`，T1–T10 引用的不存在测试名为 `[]`：

```bash
python3 - <<'PY'
import ast
import re
from pathlib import Path

root = Path('.')
rules = {c for n in ast.walk(ast.parse((root / 'backend/safety.py').read_text()))
         if isinstance(n, ast.Constant) and isinstance(n.value, str)
         for c in n.value if '\u4e00' <= c <= '\u9fff'}
tree = ast.parse((root / 'backend/tests/test_traditional_crisis.py').read_text())
def assigned(name):
    return next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
mapped = ast.literal_eval(assigned('RULE_CHARACTER_VARIANTS'))
whitelist = set(ast.literal_eval(assigned('NO_VARIANT_RULE_CHARACTERS').args[0]))
print(len(rules), len(rules & mapped.keys()), len(rules & whitelist))

tests = {n.name for p in (root / 'backend/tests').glob('test_*.py')
         for n in ast.walk(ast.parse(p.read_text()))
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')}
report = (root / 'docs/tasks/2026-09-29-deep-check/03-report.md').read_text()
rows = [line for line in report.splitlines() if re.match(r'^\| T(?:[1-9]|10) \|', line)]
print([(row.split('|')[1].strip(), name) for row in rows
       for name in re.findall(r'`(test_[^`]+)`', row) if name not in tests])
PY
```

## 验收实测

以下命令均在 Fiona 仓库根目录执行或明确进入子目录；未使用真实 Key、真实数据库/上传目录或固定服务端口。

| 验收命令 | 真实结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` | **1373 passed，0 failed，0 error，12 warnings，34.58s**，退出码 0；基线为 1169 passed。 |
| `cd backend && for f in tests/test_*.py; do .venv/bin/python -m pytest -q -p no:cacheprovider "$f" || echo FAIL "$f"; done` | **55 个文件逐一通过，合计 1373 passed，0 FAIL**；日志保存于 `/private/tmp/fiona-per-file-2026-09-29.log`。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .` | 无输出，退出码 0。 |
| `cd frontend && npx tsc --noEmit` | 无错误，退出码 0。 |
| `cd frontend && npm run lint -- --max-warnings=38` | **0 errors，28 warnings**，退出码 0。 |
| `cd frontend && npm run build` | 编译成功、**14/14** 静态页生成，退出码 0。 |
| `git diff --check` | 无输出，退出码 0。 |

测试前后 `ls backend/uploads | sort | shasum` 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`shasum backend/*.db` 均为 `fiona.db 403a086c4ec0cf28493fc9fa37b2b6eee528b261`、`local-avatar.db e6c4397d06f78f8182d3a93b5f597ed63cb4e564`，真实数据未变。

`git diff --name-only 12b6bf0 27e6806` 的 69 个文件（45 个修改、24 个新增）列于上文。`git diff 656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f -- backend/requirements.txt backend/requirements-dev.txt frontend/package-lock.json desktop frontend/AGENTS.md` 无输出；`frontend/package.json` 差异仅在 `scripts`。未运行 `next dev`。

私聊 URL 扫描实用命令：`rg -n 'tts/stream\?\$\{|text=\$\{|params\.set\("text"|text: text' frontend backend -g '!frontend/node_modules/**' -g '!frontend/.next/**' -g '!backend/.venv/**'`。输出为空，`rg` 退出码 1（无匹配）。

T3 基线失败另作了两种只读验证：将基线提交的 `backend` 用 `git archive` 导出到 `/private/tmp`，在临时副本上用同样的 **4 默认线程、8 个挂起 5 秒的交流、8 个滴流 fetch_card、1 条普通聊天** 场景运行兼容测试；普通聊天完成耗时 **35.888s**，`<1.5s` 断言失败（1 failed，36.77s）。当前代码的验收测试通过；该测试用 TestClient 缓冲完整 SSE，因此其“整轮完成 <1.5s”断言同时覆盖“首事件 <1.5s、整轮 <3s”。另外，当前验收测试的 `FIONA_T3_LEGACY_REPRO=1` 分支将两类调用换回基线的 `asyncio.to_thread`，同一断言测得 **29.767s** 并按预期失败。基线副本和复现脚本都在临时目录，未写入仓库或 Git 状态。

## 手工确认与边界

- T7 待浏览器手工验证：登录后只清 `localStorage.fiona_user` 而保留 Cookie，刷新主页/设置，确认一次 `/profile` 回填真实用户名，回填前删号按钮禁用；阻断或使 `/auth/logout` 返回非 2xx，确认仍在设置页、身份未清且显示重试提示；恢复接口后重试，确认 2xx 才进入 `/login?reason=logout`。再直达 `/profile`、`/match`、`/history` 检查回填与刷新行为。
- **白名单边界**：`frontend/app/profile/page.tsx`、`match/page.tsx`、`history/page.tsx` 不在允许修改范围，内部仍用“默认用户”作初始渲染。允许文件中的主页延迟 iframe 挂载、身份回填后直达页刷新已缓解；直达页首帧短暂占位及极早交互仍不能在本文件边界内彻底排除。要完全满足“所有直达页任何时刻都不用默认身份”，需将这三页加入后续任务白名单并改为统一身份 hook。
- T9.3 待浏览器手工验证：广场选择超限文件触发 413、选择 HEIC/AVIF 触发 400，确认弹窗显示后端 `detail`，文案与标签保留；正常发布后弹窗关闭。
- FastAPI 在进入聊天路由前产生的 422（如超过 8000 字）以及客户端主动断开不属于 T5 的服务端可控结束路径。一次性 TTS 票据、交流任务映射和预算状态按部署文档的**单后端进程**假设工作；进程重启会使未使用票据失效，前端跳过该句。
- DNS 的 OS `getaddrinfo` 本身无法便携取消；4 线程专池使抓取调用按总时限释放调用线程，底层解析线程可能等到 OS 返回。默认池 32、慢池 16 是小主机聊天余量与外部并发间的起点，真实内测负载仍需监测。未用真实上游 Key、真实浏览器或线上部署验证外部服务效果。

## 返修第 1 轮

本节记录 `05-fix-round1.md` 的 R1–R3；上文 T6 的“一次性票据”描述以本节的“60 秒内最多 4 次”修正为准。原规格、基线和白名单约束继续有效；未运行任何写 Git 状态的命令，未改前端、依赖或数据库 schema。

### 文件与逐项对应

| 返修项 | 本轮修改的文件 | 实现与测试 |
|---|---|---|
| R1 | `backend/intent_router.py`、`backend/tests/test_image_intent_precision.py` | 删除按价格、时长等话题列举的 `_IMAGE_META_QUERY`。对无请求前缀的句子按疑问词、疑问语气、评价和感叹标记保守判断；带请求前缀保留礼貌问句的明确请求。扩充条、座、朵等量词和油画、水彩、素描等画种。原语料全部保留，追加返修单的 5 条正例、8 条反例及 4 条句式护栏。现有对应参数化测试为 `test_image_request_is_only_a_candidate`、`test_image_discussion_with_null_model_never_generates`；该轮文件共 **57 passed**。 |
| R2 | `backend/routers/voice.py`、`backend/tests/test_tts_private_tickets.py`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` | 同一用户可在票据签发后 **60 秒内最多使用 4 次**，`/tts/stream` 与 `/tts/synthesize` 共用计数；跨用户、过期、超限为 404。计数和签发由锁保护。对 `Range: bytes=0-1` 探测仍返回 **200 全量流**，随后同 URL 正式 GET 可再次成功；返修单明确允许服务器忽略 Range，保持流式响应，避免为组装 206 而缓存整段音频。朗读原文仍只经 POST 请求体传输，票据 URL 不含原文；20/min 换票限额未收紧。`test_tts_ticket_requires_login`、`test_tts_ticket_range_probe_then_playback_and_bound_to_user`、`test_tts_ticket_expires_and_legacy_text_query_is_rejected`、`test_tts_ticket_expires_after_range_probe`、`test_tts_synthesize_shares_ticket_use_limit_with_stream` 共 **5 passed**。部署与架构文档改为“短时、限次票据”。 |
| R3 | `backend/services/exchange_service.py`、`backend/exchange_models.py`、`backend/tests/test_exchange_models.py`、`backend/tests/test_exchange_workflow.py` | 交流上游无条件调用异步 `get_async_main_client` / `get_async_deepseek_client` 并 `await ...create()`；删除基于 getter/client 身份识别测试替身的分支、同步 DeepSeek getter 和 `run_slow` 同步回退。直接测试 SDK 边界的假客户端改为异步。`test_generate_routes_to_the_selected_sdk_and_records_public_provider_metadata`、`test_async_deepseek_client_uses_only_server_key_and_fixed_official_endpoint`、`test_deepseek_failure_is_not_retried_or_sent_to_main`、`test_provider_boundary_keeps_long_document_and_reports_truncation`，以及 `test_exchange_isolation.py` 等 8 个交流相关测试文件合并运行，**226 passed**。 |

### 本轮验收实测

| 命令或检查 | 真实结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` | **1391 passed，0 failed，0 error，12 warnings，34.72s**，退出码 0；返修前为 1373 passed。 |
| `cd backend && for f in tests/test_*.py; do .venv/bin/python -m pytest -q -p no:cacheprovider "$f" || echo FAIL "$f"; done` | **55/55 个文件通过，合计 1391 passed，0 FAIL/FAILED/ERROR**；日志 `/private/tmp/fiona-per-file-fix-round1-2026-09-29.log`。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .` | 无输出，退出码 0。 |
| R1 定向：`tests/test_image_intent_precision.py tests/test_chat_image_generation.py tests/test_chat_image_editing.py` | **122 passed，12 warnings**；其中 R1 测试文件 57 passed。 |
| R2 定向：`tests/test_tts_private_tickets.py` | **5 passed，12 warnings**。 |
| R3 交流相关 8 个测试文件合并运行 | **226 passed，0 failed，12 warnings**。 |
| `git diff --check`；原规格禁止变动的 requirements、lock、`frontend/AGENTS.md`、`desktop` 与基线差异检查 | 两者均无输出，退出码 0。`exchange_service.py`、`exchange_models.py` 中搜索旧同步 getter、生产身份判断和 `run_slow` 无匹配。 |

前后 `ls backend/uploads | sort | shasum` 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`shasum backend/*.db` 均为 `fiona.db 403a086c4ec0cf28493fc9fa37b2b6eee528b261`、`local-avatar.db e6c4397d06f78f8182d3a93b5f597ed63cb4e564`。本轮没有前端文件改动，按返修单未重跑前端门禁。

### 未完成与人工确认

- 需在 Safari macOS、iOS Safari 和 iOS 主屏 PWA 真机确认 `Range` 探测后复用同一 URL 能正常出声；TestClient 已覆盖两次请求和次数上限，不能代替浏览器媒体栈。票据仍为单进程内存状态，进程重启使未用次数失效。
- 规格作者未公开 R1 的 10 条盲测原句，无法直接执行该私有语料；已按句式规则修复并通过公开及新增护栏，仍需规格作者复验盲测。
- 上文列出的 T7 身份/退出与 T9.3 广场发布浏览器手工确认仍待完成；本轮未使用真实上游 Key 或线上部署验证交流连接。

## 返修第 2 轮

本节对应 `05-fix-round2.md` 的 M1–M5、O1–O7，并以本节修正上文已过时的 R1「正则直接决定生图」、R2「Range 返回流式 200」及 T2「DNS 专池 4 线程」描述。沿用原规格第 0 节基线：没有回滚已有未提交改动，没有执行写 Git 状态的命令，没有下载浏览器或依赖；测试只使用隔离数据、已有虚拟环境与本机缓存。

### 本轮修改文件与逐项对应

| 项目 | 修改文件 | 实现与验证 |
|---|---|---|
| M1 | `backend/intent_router.py`、`backend/services/chat_service.py`、`backend/tests/test_image_intent_precision.py`、`backend/tests/test_chat_image_generation.py` | 正则仅提名自然语言生图候选；`run_chat` 在待补参数和镜子模式前调用已有意图模型确认，确认 `generate_image` 才生图，并复用本轮结果。模型未给 `prompt`（包括标记缺参）时使用原文；返回其他意图、空意图或抛异常时不生图。含返修单 7 句的端到端回归及镜子、计费、单次识别验证。两测试文件 **100 passed**；九个聊天/图片文件 **292 passed**。 |
| M2 | `backend/routers/voice.py`、`backend/tests/test_tts_private_tickets.py`、`frontend/app/page.tsx` | 带 Range 的票据先合成有限长度 mp3，同票据在锁下共享并缓存，返回准确的 206、`Content-Range`、`Content-Length`、`Accept-Ranges`；非法/越界返回 416。无 Range 首次请求仍以 200 流播；票据到期后缓存不可读取，后续签发会清理过期条目，单票据 8 MiB、总缓存 64 MiB 上限。覆盖 0–1 探测、0– 全长复用、并发复用、无 Range 和上限，共 **14 passed**。三句队列的真实浏览器验证见下方阻碍。`backend/tts.py` 未改。 |
| M3 | `backend/services/exchange_service.py`、`backend/exchange_store.py`、`backend/tests/test_exchange_isolation.py` | 重复停止时不再次 `task.cancel()`；取消收尾创建独立任务并用 `asyncio.shield` 等到结算完成。存储层按交流 ID 和运行 token 在一笔事务中将所有 reserved 调用记为 discarded、估算用量、清空在途指针与预留量，即使预留已提交但调用 ID 尚未返回也可结清。双停止、peer 双方停止、预留返回前停止各循环 **30 轮，0 泄漏**；交流相关 8 文件 **230 passed**。`backend/routers/agent_exchanges.py` 未改。 |
| M4 | `docs/DEPLOYMENT.md` | 日常备份与回滚前快照都在子 shell 内设置 `umask 077`，不改变外层 shell；文档说明后续更新仍用默认 umask。临时目录模拟 `sqlite3 .backup`、`tar` 和后续新文件：权限依次为 **0600、0600、0644**，外层 umask **022**。 |
| M5 | `backend/utils/traditional_chinese.py`、`backend/tests/test_traditional_crisis.py` | 补齐 讓/傘/繩/遠、葯/喫/瞭、纔/弔/妳/牠，并在逐字转换后做小范围词级 `計畫`→`计划`。测试用 AST 扫描 `safety.py` 全部字符串字面量，使用测试内独立的简繁/异体清单；对返修句及简体对应句比较判级。该文件 **92 passed**，联同 `test_beta_safety.py` **351 passed**。`backend/safety.py` 未改。 |
| O1 | `backend/main.py`、`backend/admin_env.py`、新增 `backend/utils/dotenv_config.py`、`backend/tests/test_early_env_loading.py` | 服务与管理脚本共用 dotenv 选择规则：命令行优先、其后 `FIONA_ENV_FILE`、最后默认 `backend/.env`；展开 `~`，显式文件缺失/不可读时中文报错，默认文件缺失时跳过。子进程覆盖路径与缺失行为；联同既有管理脚本测试 **33 passed**。 |
| O2 | `frontend/app/settings/page.tsx` | `/auth/logout` 返回 401 时清除本地身份并跳到 `/login?reason=logout`；其他非 2xx 和网络失败仍保留身份、留在设置页提示重试。TypeScript、lint 和 build 均通过；浏览器交互待人工确认。 |
| O3 | `frontend/app/page.tsx` | 朗读换票 POST 使用 `AbortController`，停止朗读时中止当前与预取句子的请求，并以会话序号拦住迟到响应，避免旧句再设置 stream URL。前端门禁通过；真实浏览器交互同 M2。 |
| O4 | `backend/utils/safe_http.py`、`backend/tests/test_safe_http_deadline.py` | DNS 独立解析池由 4 扩至 **32** 工作线程；请求仍按总时限放弃等待。模拟 4 个解析挂起时，第 5 个正常请求在时限内完成；该文件 **5 passed**。 |
| O5 | `backend/tests/test_exchange_isolation.py` | 测试实际 `execute_intent` 接线，在默认池被占满时验证普通聊天仍可完成。正控设置 `FIONA_T3_LEGACY_TOOL_REPRO=1` 将该路径临时改回默认池，同一测试**按预期 1 failed**：聊天耗时 **3.027s**，超过 `<1.5s` 断言；正常实现通过。 |
| O6 | `backend/tests/test_beijing_time.py` | 固定 UTC `2026-09-28 20:45`（纽约周一 16:45、北京周二 04:45），同时核对用户工具与 Persona 的日期、星期、小时及特别日期；**1 passed**。 |
| O7 | `docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`README.md`、`CLAUDE.md`、`PLAN.md` | 架构说明 possible 危机生图失败先发资源再发错误、路由前 422/429 例外、候选句模型确认及其延迟/成本、TTS Range 行为；部署自检改 `python3`；README 说明 `FIONA_ALLOWED_DEV_ORIGINS` 填主机名（可带端口），不是完整 origin。 |

本轮连同此报告共修改/新增 **26 个文件**，其中 `backend/utils/dotenv_config.py` 为新增实现文件。前端改动只落在 `app/page.tsx` 与 `app/settings/page.tsx`；其他可选实现文件（`backend/tts.py`、`backend/routers/agent_exchanges.py`、`backend/safety.py`）无需改动。

### 验收实测

| 命令或检查 | 真实结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` | **1450 passed，0 failed，0 error，12 warnings，41.42s**，退出码 0；返修第 1 轮为 1391 passed。 |
| `cd backend && for test_file in tests/test_*.py; do .venv/bin/python -m pytest -q -p no:cacheprovider "$test_file"; done` | **55/55 个文件通过，合计 1450 passed，0 FAIL/ERROR**，日志 `/private/tmp/fiona-per-file-fix-round2-2026-09-29.log`。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .` | 无输出，退出码 0。 |
| 仓库外副本 `/private/tmp/fiona-m2-browser-GJPCLA/frontend` 执行 `./node_modules/.bin/tsc --noEmit`、`npm run lint -- --max-warnings=38`、`npm run build` | 均退出码 0；TypeScript 无错误，lint **0 errors、28 warnings**，Next 编译成功且生成 **14/14** 静态页。副本的 `app/page.tsx`、`app/settings/page.tsx`、`next.config.ts` 与仓库文件逐一 `cmp` 一致；没有安装或下载依赖。 |
| `git diff --check`；与基线比较 requirements、lock、`frontend/AGENTS.md`、`desktop` | 均无输出，退出码 0。私聊 TTS 原文 URL 模式扫描无匹配。 |
| 真实数据哈希 | `ls backend/uploads \| sort \| shasum` 仍为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`backend/fiona.db` 为 `403a086c4ec0cf28493fc9fa37b2b6eee528b261`，`backend/local-avatar.db` 为 `e6c4397d06f78f8182d3a93b5f597ed63cb4e564`；与本轮开始及前轮相同。 |

按返修单尝试用本机已有 Playwright 浏览器执行 `node /private/tmp/fiona-m2-browser-GJPCLA/queue-test.js chromium` 与同命令的 `webkit` 版本，两者均**退出码 1，未进入页面、未观察到任何 `ended` 事件**：Chromium 启动时 macOS 沙箱拒绝 `MachPortRendezvousServer`，报 `Permission denied (1100)`；WebKit 缓存的 `pw_run.sh` 启动即 `Abort trap: 6`（内部退出码 134）。测试脚本在启动浏览器阶段即退出，三句场景未执行；这些是浏览器启动失败，不是三句队列通过或失败的播放结果。票据 Range 行为已有后端真实 HTTP 测试覆盖；浏览器播放结论仍待可启动 Playwright 的环境复验。没有下载替代浏览器或绕过沙箱。

### 未完成与人工确认

- **M2 验收缺口**：在允许启动本机 Playwright WebKit/Chromium 的环境，用本地 mp3 桩连续播放三句，核对每句按序触发 `ended`、免提续录；再在 macOS/iOS Safari 与主屏 PWA 做真机听音确认。本环境的浏览器启动限制使上述结果无法取得。
- **O2/O3 与既有 T7/T9.3 手工路径**：在浏览器确认退出接口 401 清身份、其他错误保留身份，朗读中止不会发旧句 stream，以及身份回填、广场发布错误文案。前端静态门禁不能替代这些交互验证。
- M1 复核员未提供完整私有 49 句语料；返修单公开的 7 句已在模型返回 `null` 的端到端测试中覆盖，仍可由复核员用私有语料复验。真实 DashScope、真实 TTS 上游及线上部署未在隔离测试中调用。

## 返修第 3 轮

本节对应 `05-fix-round3.md` 的 V1–V4，并修正上节 M1「画面描述可用模型参数」与 M2「所有 Range 均返回 206」的描述。原规格和前两轮返修的基线、隔离及文件白名单约束继续有效。本轮没有回滚已有未提交改动，没有执行写 Git 状态的命令，没有真实模型调用，也没有下载任何内容。

### 修改文件与 V1–V4 对应

本轮共修改 **7 个文件**：`backend/intent_router.py`、`backend/services/chat_service.py`、`backend/routers/voice.py`、`backend/tests/test_image_intent_precision.py`、`backend/tests/test_tts_private_tickets.py`、`docs/ARCHITECTURE.md`、本报告。未改前端、依赖、数据库 schema 或其他实现文件。

| 返修项 | 实现与测试 |
|---|---|
| V1 讨论不生图兜底 | `recognize_intent_with_fallback` 恢复模型返回 `generate_image` 时的 `image_generation_discussion` 检查，因此候选确认与普通意图路径共用兜底；同时补齐「你会画画吗」的能力咨询识别。新增 4 个打桩端到端用例，模型即使误报生图，能力咨询、教程、否定句也不调用生图。 |
| V2 完整原话 | 候选确认与普通意图路径实际送入生图的描述均使用 `ctx.message.strip()`；分类器短 `prompt` 不覆盖原话。比例先从原文的横版、竖版、正方形等表达推断，原文没写时才使用合法模型比例；显式图片按钮仍优先使用用户选择。新增 3 个截短 `prompt` 场景和 2 个 chat/图片按钮比例优先级端到端场景。 |
| V3 意图提示词 | `INTENT_PROMPT` 增加谈论生图价格、扣费、耗时、难度、已生成结果、回忆、愿望、第三人称叙述与口语反问应返回 `null` 的规则和自行编写的例句；明确当前祈使请求仍返回 `generate_image`。补静态提示词覆盖测试；按约束未调用真实意图模型，因此不声称私有语料实测效果。 |
| V4 开放区间首音 | 未缓存票据首次收到 `Range: bytes=0-` 时，沿用 `synthesize_stream` 流式返回 **200**；闭区间如 `bytes=0-1`、`bytes=0-N` 继续完整合成、缓存并返回 **206**；已有缓存的票据对任何 Range（含 `0-`）读缓存返回 206。依据是 `0-` 没有指定终点，不需先知道总长度，Chromium/WebView2 可直接接收流式 200；闭区间及缓存响应能给出有限 `Content-Range` 和 `Content-Length`。测试覆盖首次 `0-` 流播、闭区间探测后只合成一次、已缓存 `0-` 返回 206、无 Range 保持流播。 |

`docs/ARCHITECTURE.md` 同步记录了上述生图兜底、完整原话、比例优先级及两类 Range 响应规则，并注明模型分类仍可能误判。

### 验收实测

| 命令或检查 | 真实结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` | **1461 passed，0 failed，0 error，12 warnings，40.36s**，退出码 0；第 2 轮为 1450 passed。 |
| `cd backend && for test_file in tests/test_*.py; do .venv/bin/python -m pytest -q -p no:cacheprovider "$test_file"; done` | **55/55 个文件通过，合计 1461 passed，0 FAIL/ERROR**；日志 `/private/tmp/fiona-per-file-fix-round3-2026-09-29.log`。 |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_image_intent_precision.py tests/test_chat_image_generation.py` | **110 passed，12 warnings**；模型全部打桩，无真实调用。 |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_private_tickets.py tests/test_tts_ws_limits.py` | **17 passed，12 warnings**；其中票据测试 15 passed。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .` | 无输出，退出码 0。 |
| `git diff --check`；与基线比较 requirements、lock、`frontend/AGENTS.md`、`desktop` | 均无输出，退出码 0。前端关键文件与第 2 轮仓库外副本逐一 `cmp` 一致；本轮未重跑前端门禁。 |

本轮测试前后 `ls backend/uploads | sort | shasum` 均为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`shasum backend/*.db` 均为 `fiona.db 403a086c4ec0cf28493fc9fa37b2b6eee528b261`、`local-avatar.db e6c4397d06f78f8182d3a93b5f597ed63cb4e564`。真实数据未变。

### 未完成与人工确认

- V3 提示词对规格作者未公开语料及真实意图模型的效果，需要规格作者按返修单负责的方式复测；本轮只证明兜底代码、打桩路由及提示词文本，未做真实模型调用。
- V4 的 Chromium/WebView2 首音延迟改善需要在可启动浏览器及真实媒体栈的环境测量；本轮后端测试证明响应分支与合成次数，没有把它冒充为延迟实测。返修单前言记载规格作者在第 2 轮代码上用真实后端和生产构建让 WebKit、Chromium 三句队列各运行 2 次并按序触发 `ended`；该结果来自规格作者，不是本轮修改后的本机浏览器测试。此前报告中的本机 Playwright 启动限制仍存在。
- 既有设置页身份/退出、广场发布等浏览器手工确认以及真实 TTS 上游效果，均不在本轮隔离后端测试中验证。

## 返修第 4 轮

本节对应 `05-fix-round4.md` 的 N1–N3、P1–P3。继续遵守原规格及前三轮返修的文件边界和第 0 节基线规则：保留工作区已有未提交改动，没有回滚或执行写 Git 状态的命令，没有真实模型调用，也没有下载任何内容。本轮没有修改前端、依赖、数据库 schema 或真实数据。

### 修改文件与逐项对应

本轮连同此报告共修改 **12 个文件**：实现文件 `backend/services/chat_service.py`、`backend/utils/traditional_chinese.py`、`backend/routers/voice.py`、`backend/services/exchange_service.py`；测试文件 `backend/tests/test_chat_image_generation.py`、`backend/tests/test_image_intent_precision.py`、`backend/tests/test_traditional_crisis.py`、`backend/tests/test_tts_private_tickets.py`、`backend/tests/test_exchange_isolation.py`；文档 `README.md`、`docs/ARCHITECTURE.md`、本报告。`backend/intent_router.py` 和 `backend/exchange_store.py` 的现有接口足够完成本轮修复，未修改。

| 项目 | 实现与证据 |
|---|---|
| N1：空画面候选请求 | `chat_service.py` 在意图模型确认 `generate_image` 后，只要正则候选或模型的 `missing` 含 `prompt`，便保留缺参信号，先追问并设置待补参数。模型猜出的短 `prompt` 不能填补用户原话缺少的画面主体。四句指定空画面话语 × 模型是否标缺参共 **8** 个端到端用例，均验证首次不生图、不扣费，随后补画面正常生图并只对成功轮次扣 10 颗草莓；另测有主体但模型标缺参。恢复被第 2 轮改掉的基线原句，细目见下表。图像意图两文件 **119 passed**。 |
| N2：删除词级替换 | `traditional_chinese.py` 删除 `_WORD_REPLACEMENTS`，危机分类仅逐字归一。六句指定简繁回归的级别依次为 `None`、`None`、`possible`、`possible`、`None`、`possible`，与基线 `656b7cf` 的对应简体结果一致。「計畫下週跳樓」现在为 `possible`：去除跨词替换后不再命中含「计划」的 high 规则，但仍命中「跳楼」的 possible 规则，按 T5 继续收到资源。 |
| N3：规则字精确覆盖 | 测试独立写死「规则字→常见繁体/异体」和「无异体规则字」两份清单，扫描 `safety.py` 所有字符串字面量的汉字，断言并集**恰好**相等，缺字和多字均点名。现有规则共 **296** 字：有映射 **114** 字，无异体白名单 **182** 字。补齐 `薬、譲、縄、気、軽、対、実、絶、眞` 九个字形的逐字映射和验证。繁体文件 **107 passed**；与安全及危机资源测试合并 **422 passed**。正控见验收表。 |
| P1：TTS 缓存驱逐 | 总量超限时只清掉旧票据的 `cached_audio` 和已完成构建引用，保留票据及剩余使用次数；WebKit 探测后缓存即使被另一票据淘汰，正式 Range 请求仍可再次合成，返回 **206** 而非 404。票据与 WebSocket 限制两文件 **17 passed**。 |
| P2：交流停止结算异常 | 取消收尾对非取消异常最多重试 **3** 次并记录日志；全失败时不向 `/stop` 传播异常，保留持久预留供下次启动的 `recover_interrupted_exchanges` 结清。注入 `database is locked` 覆盖前两次失败后成功、三次全失败后恢复两个场景，验证 `/stop` 均为 **200**、恢复后预留清零且再次恢复幂等。交流相关八文件 **232 passed**。 |
| P3：文档 | `README.md` 明确 `FIONA_ALLOWED_DEV_ORIGINS` 只填主机名/IP，可用 `*.example.local`，不带协议和端口；危机资源保证排除进入 `/chat` 前的 **422** 校验和 **429** 限流。`docs/ARCHITECTURE.md` 说明模型否决的候选句复用本轮识别结果，不比普通消息多一次调用；只有确认生图的候选句需在生图前等待意图模型，并同步说明空画面追问。 |

### 基线已有测试改动审计

以只读的 `git show 656b7cfbd5de9e2f47664cfc0d1272ff8a45f16f:backend/tests/test_chat_image_generation.py` 和 `git ls-files` 核对：本轮修改过的基线已有测试仅下表 **2 处输入恢复**。两条测试的断言与基线一致，没有为通过测试而降低断言。

| 文件与当前行号（基线行号） | 本轮改动 | 规格依据 |
|---|---|---|
| `backend/tests/test_chat_image_generation.py:107`（基线 :89） | `test_image_prompt_question_then_description_generates_only_description` 首轮输入从第 2 轮替换的「帮我创作」恢复为基线「帮我生成图片」；仍断言先追问、不生图，补充描述才生图。 | 返修单 N1 第 2 条，明确要求恢复被改掉的基线原文及断言。 |
| `backend/tests/test_chat_image_generation.py:171`（基线 :100） | `test_pending_image_request_can_be_cancelled_or_left` 建立待补状态的输入同样恢复为「帮我生成图片」；原有取消/离开断言未变。 | 同上。 |

同文件 :42 的「帮我生成图片」位于第 2 轮新增的模型桩 fixture，**不是基线已有测试**，本轮一并恢复以匹配上述原句。其余本轮修改的四个测试文件均不在 `656b7cf` 的跟踪文件中；没有修改其他基线测试输入或断言。`test_traditional_crisis.py` 是基线后新增文件，其中「計畫下週跳樓」的期望由 `high` 改为 N2 允许的 `possible`，四条「計畫」逐字结果与 N2 的删除词级替换同步更新，N3 的弱覆盖断言改为精确集合断言。

### 验收实测

| 命令或检查 | 真实结果 |
|---|---|
| `cd backend && PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -p no:cacheprovider` | **1487 passed，0 failed，0 error，12 warnings，40.99s**，退出码 0；上轮为 1461 passed。 |
| 对 `backend/tests/test_*.py` 的 **55** 个文件逐个执行 `.venv/bin/python -m pytest -q -p no:cacheprovider <文件>`，并设置 `PYTHON_DOTENV_DISABLED=1` | **55/55 文件通过，合计 1487 passed，0 个失败文件**，日志 `/private/tmp/fiona-per-file-fix-round4-2026-09-29.log`。 |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_image_intent_precision.py tests/test_chat_image_generation.py` | **119 passed，12 warnings**；意图模型和生图均为测试桩。 |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_traditional_crisis.py` | **107 passed**；联同 `test_beta_safety.py`、`test_crisis_resource_paths.py` 为 **422 passed，12 warnings**。 |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tts_private_tickets.py tests/test_tts_ws_limits.py` | **17 passed，12 warnings**。 |
| 交流相关八个测试文件合并运行 | **232 passed，0 failed，12 warnings**；其中结算异常注入用例两个参数场景均通过。 |
| N3 仓库外临时副本正控 | 将 `safety.py` 和覆盖测试复制到 `/private/tmp/fiona-n3-positive-s22sxmmd`，在副本加入 `_INJECTED_REVIEW_RULE = re.compile(r"想离开这个世界")`，用临时目录优先的 `PYTHONPATH` 单跑 `test_traditional_crisis.py::test_crisis_rule_character_variants_normalize_back_to_rule_characters`：**按预期 1 failed**，报 `unlisted rule chars: 世开界离`。仅修改临时副本，仓库规则未注入。 |
| `cd backend && .venv/bin/python -m compileall -q -x '\.venv' .`；`git diff --check`；与基线比较 requirements、lock、`frontend/AGENTS.md`、`desktop` | 均退出码 **0**、无输出；禁止改动文件与基线无差异。 |
| 真实数据哈希 | `ls backend/uploads \| sort \| shasum` 为 `ccf9c1525240498c5b94e47a220a87a64f587eac`；`backend/fiona.db` 为 `403a086c4ec0cf28493fc9fa37b2b6eee528b261`，`backend/local-avatar.db` 为 `e6c4397d06f78f8182d3a93b5f597ed63cb4e564`；与本轮开始相同。 |

### 未完成与人工确认

- N1–N3、P1–P3 的返修实现和本轮规定的本地验收均已完成。按约束没有调用真实意图/生图模型；V3 提示词在规格作者私有语料上的效果仍需其复核。
- P1 的真实 WebKit/iOS Safari 媒体栈在「探测后缓存被淘汰」场景中的播放行为需具备浏览器环境的人工确认；本轮后端测试仅证明票据不失效且正式 Range 请求可返回 206。前轮记录的浏览器启动限制仍在，本轮没有尝试下载或替换浏览器。
- 原报告列出的设置页退出、广场发布等浏览器手工路径以及真实 TTS 上游效果仍待确认；本轮没有修改前端。
