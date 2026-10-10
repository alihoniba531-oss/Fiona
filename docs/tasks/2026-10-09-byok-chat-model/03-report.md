# 每用户自带聊天模型（BYOK）实现报告

日期：2026-10-09。依据：`02-spec.md`、`05-fix-r0.md`、`05-fix-r1.md`、`05-fix-r1b.md`、`05-fix-r2.md` 与本轮优先的 `05-fix-r3.md`；代理策略继续遵循 R1b。

**R3-1至R3-5的实现与文档已完成。** 本轮新增9个后端用例，BYOK共390项；专项 **384 passed / 6 skipped**、退出0；全量 **1 failed, 2806 passed, 6 skipped, 14 warnings, 5 errors**、退出1。R3新增9项全通过；前端离线组件31项、文档2项通过；tsc退出0，ESLint **0 errors / 25 warnings**、退出0。六项既有端口权限失败、六项回环skip及Playwright浏览器验证仍须主控在沙箱外补验，未宣称全部验收绿色。R3逐项红绿与浏览器脚本说明见第7节，全部实际验收输出见第8节。

## 1. 新增与修改的文件

新增（含保留并完善上一轮四个 BYOK 模块）：

- `backend/byok/__init__.py`
- `backend/byok/errors.py`
- `backend/byok/crypto.py`
- `backend/byok/providers.py`
- `backend/byok/store.py`
- `backend/byok/url_safety.py`
- `backend/byok/client.py`
- `backend/routers/chat_model.py`
- `backend/tests/test_byok_store.py`
- `backend/tests/test_byok_url_safety.py`
- `backend/tests/test_byok_client.py`
- `backend/tests/test_byok_chat.py`
- `backend/tests/test_byok_api.py`
- `frontend/components/ChatModelSection.tsx`
- `frontend/lib/chatModel.ts`
- `docs/tasks/2026-10-09-byok-chat-model/03-report.md`（覆盖重写）

修改：

- 依赖与模板：`backend/requirements.txt`、`backend/.env.example`。
- 后端集成：`backend/database.py`、`backend/main.py`、`backend/rate_limit.py`、`backend/routers/chat.py`、`backend/services/chat_service.py`。
- 前端：`frontend/app/settings/page.tsx`、`frontend/app/page.tsx`、`frontend/components/ChatBubble.tsx`、`frontend/components/Sidebar.tsx`。
- 文档：`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`docs/CYBER_AVATAR_PLATFORM.md`；最后一份仅修改「实施状态」段的两处当前事实，历史评估快照未改。

R1 相对首轮新增改动范围：核心 `byok/client.py`、`crypto.py`、`errors.py`、`url_safety.py`；集成 `services/chat_service.py`；测试 `test_byok_client.py`、`test_byok_url_safety.py`、`test_byok_chat.py`（仅追加，含有限loopback fixture支持）；前端 `ChatModelSection.tsx`、`chatModel.ts`、`app/page.tsx`；根文档五份与 `.env.example`；本报告。R1 未新增仓库文件类别。`routers/chat.py` 两次变异已恢复首轮状态。

R2本轮实际修改：`backend/byok/client.py`、`backend/byok/url_safety.py`、`backend/services/chat_service.py`、`backend/main.py`；四个本任务新增测试文件 `test_byok_client.py`、`test_byok_url_safety.py`、`test_byok_chat.py`、`test_byok_api.py`；`frontend/components/ChatModelSection.tsx`、`frontend/app/page.tsx`；README、CLAUDE、PLAN、ARCHITECTURE、DEPLOYMENT、`.env.example`与本报告。`test_byok_store.py` 本轮未改。没有新增白名单外仓库文件。

R3本轮修改：`backend/byok/client.py`、`backend/services/chat_service.py`、`frontend/app/page.tsx`、`frontend/components/ChatModelSection.tsx`；只在 `test_byok_client.py`、`test_byok_chat.py` 追加新用例；README、CLAUDE、PLAN、ARCHITECTURE、DEPLOYMENT、`.env.example`和本报告。Playwright及离线组件/文档脚本仅放仓库外临时目录，没有新建白名单外仓库文件。

任务目录在本轮开始前已为未跟踪状态；`02-spec.md`、`05-fix-r0.md`、`05-fix-r1.md`、`05-fix-r1b.md`、`05-fix-r2.md`、`05-fix-r3.md`、`04-review.md`、`04-review-r1.md`、`04-review-r2.md` 为用户提供的文件，本轮未修改。没有改动本任务开始前已有的后端测试、规格第 3 节与第 7.2 条的受保护文件。

## 2. 实现的功能

- 每用户设置自己的普通/镜子聊天模型，支持通义、DeepSeek、Kimi、智谱、Claude、自定义 OpenAI 兼容地址；未配置或手动关闭时走原平台路径，用户模型失败绝不改用平台。
- 用户 Key 使用 AES-256-GCM 加密，AAD 绑定用户名/厂商/地址；支持当前与 PREVIOUS 密钥轮换，公开配置仅有白名单字段，损坏配置显示需重填。写入事务检查用户存在，删号同事务删除配置，迟到保存不复活账号。
- 自定义地址只允许公网 HTTPS/443；纯格式规范化、带超时的独立 DNS 池、全部应答公网校验，拒绝私网/保留地址、代理假 IP、multicast 与危险 NAT64；每次连接重新解析并固定公网 IP，原域名用于 TLS SNI/证书，不跟随重定向、不使用环境代理。自写 transport 只使用 httpx/httpcore 公开 API。
- Claude 使用官方 Anthropic SDK，独立于 OpenAI 的 httpx 客户端；三项型号白名单、effort=low，Opus/Sonnet 开启指定官方 beta 拒答兜底。各厂商按规格转换真实请求消息和参数，隐藏系统提示中的账号名，不传禁止的采样参数。
- 每请求新建并关闭客户端/流，不缓存明文 Key；专用有界 fiona-byok 池负责建流和逐块读取，每用户同时一条、进程默认八条，建流起总时限默认120秒，正文普通4000/镜子600字符上限；响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时。中断线程只标记和shutdown，阻塞调用返回后由worker关闭资源。
- BYOK 聊天回复不扣草莓，有余额的预扣收尾退还；零余额或余额5时启用 BYOK 仍可聊天。工具、看图、生图保持平台计费，未预扣路径在调用前守卫，被余额守卫阻止的付费执行不消耗天气额度、不清 pending；免费取消/缺参追问和转普通聊天正常清理旧状态。high 始终平台，零余额 high 免费资源且不落库；possible 资源与错误顺序保持。
- 登录后的设置 GET/PUT/PATCH/DELETE/test，响应 private,no-store；Pydantic仅类型检查，手动捕获校验错误返回固定400，避免422回显Key。厂商失败不产生401，新设置接口鉴权失败403；连接测试业务失败、每日/分钟限流均以200返回ok:false，不保存草稿；平台10次/分钟限流文案为「操作太频繁，请稍后再试」。
- 新增 byok_chat 默认200次/日、byok_test 默认20次/日；所有配置调用时读取，非法回退默认且只告警一次，不打印值。缺失/非法服务端密钥或十一项违规环境变量使BYOK不可用，开发模式没有固定密钥回退。
- 设置页完整厂商/模型/地址/Key表单、测试/保存/删除/启停、忙碌与状态提示、隐私说明；Key永不回填，保存/切厂商/卸载清空；设置区可按版本事件/可见性刷新服务端状态并保留草稿，设置区和底栏操作完成时取得错误归属，网络及429固定中文提示，初次加载可重试，删除恢复空态。厂商配置不写localStorage，仅版本号同步。输入区按模式显示与切换，登录/设置抽屉关闭/storage/可见性事件刷新配置，底栏初次加载失败可点击重试；后台刷新只清自身加载错误，保留操作失败提示；reply_model事件在气泡标注，刷新后不保留。
- 六份文档同步接管范围、隐私数据流、计费与零余额降级、七项每日上限、新表、环境变量与密钥生成/轮换/独立保管；部署抽查与删号验证清单更新。

## 3. 与规格 6.1–6.9 逐项对应

| 条款 | 实现与验证 |
|---|---|
| 6.1 依赖 | requirements追加精确版本anthropic==1.12.1与cryptography==50.0.0；两个grep各一行，pip check退出0。未安装任何包。 |
| 6.2 存储与加密 | crypto/store实现AAD、nonce、版本字节、HMAC key_id、轮换、白名单读取；init_db在retired_usernames附近直接DDL，无新迁移版本；删号在DELETE users前同事务删配置；专项测试覆盖重建/迟到保存/损坏密文与key_id。 |
| 6.3 地址与DNS固定 | url_safety实现纯函数、IDNA规范化、DNS独立池与超时、公开API transport、固定IP/SNI、无重定向/代理、IDNA ASCII 主机比较、4 MiB读取上限、强制Accept-Encoding: identity及解码前拒绝压缩响应、socket记录与shutdown；真实OpenAI客户端配MockBackend离线测试。safe_http未改。 |
| 6.4 客户端与流 | provider元数据/校验，open_reply_stream兼容chunk/close/stop_reason，预设与Claude实际请求参数、消息转换、账号隐藏、拒答/空回复/字符截断/总时限及错误映射；核心专项用例覆盖。 |
| 6.5 聊天接入 | 普通/镜子分流且BYOK不调用平台fallback、不累计token_budget、不设billable；显式零余额标记与四类守卫；专用线程池、用户互斥、每日额度、危机/空回复/模型标注；天气pending余额充足时保持平台基线，未预扣BYOK新增四类前缀转话题出口；其他pending的免费出口仍仅对未预扣BYOK生效；既有平台路径回归除六项端口权限失败外通过。 |
| 6.6 设置接口 | 五个登录接口及main注册，private,no-store，修改与测试10/min；保存/Key复用/启停/删除、availability、固定验证错误、测试最小请求/200/不保存；API专项覆盖非字符串/超长Key、不回显、403鉴权、每日与分钟额度。 |
| 6.7 前端 | 新组件/严格JSON库，设置区与删除确认、底栏切换/同步、气泡标记、计费tooltip与五句隐私说明。颜色用既有token，不用any，不在effect同步setState，Key/配置不进localStorage。tsc退出0、eslint0errors/25warnings。 |
| 6.8 文档 | 全库搜索后更新R0允许的六份文档，CYBER仅当前实施状态；同步范围、隐私、计费、环境变量/生成命令、七项上限、新表/删号、system合并差异、大陆说明、备份/独立保管/丢失重填。 |
| 6.9 测试 | 新增五个测试文件共390用例（首轮247，R1阶段98，R1b净增5，R2新增31，R3新增9）；每文件autouse断网夹具、阻断DNS/httpcore同步后端并teardown断言无网络尝试，Key用测试环境注入，涉及限流reset。本任务之前已有测试及保护文件diff为空。 |

规格6.9的19组覆盖对应：

| 编号 | 对应新增测试及覆盖 |
|---|---|
| 1–3 | test_byok_store：加解密/AAD/选钥与轮换/缺失或非法密钥不在导入时raise；删号、同名重建、迟到保存；公开白名单与坏密文/key_id。 |
| 4–5 | test_byok_url_safety：非法地址参数化与Unicode/大写/尾点；全部DNS应答含假IP、loopback、NAT64、multicast及IPv4映射时拒绝。 |
| 6 | 同文件真实OpenAI+httpcore.MockBackend记录connect_tcp与start_tls，断言公网IP/原主机SNI、重绑定拒绝、302不跟随、HTTPS_PROXY无影响、SDK超时分类、socket shutdown。 |
| 7 | test_byok_client：五家兼容厂商与Claude三型号的实际请求体，system结构/安全规则/首尾user/同角色合并/账号隐藏/禁止参数/预算/beta兜底。 |
| 8–9 | 同文件文字chunk/max_tokens/refusal/字符截断/总时限、流与客户端close及构造失败关闭；十一项违规环境变量阻止客户端构造。 |
| 10 | test_byok_chat：普通/镜子及余额0/5/10，确认专用fiona-byok线程、平台建流零调用、预扣退款；三个同用户并发第二/第三直接拒绝。 |
| 11–12 | 同文件未预扣weather/pending/自然语言生图/看图守卫，不执行桩、不计天气、不清pending、共享余额文案；显式image/image_edit原预检，有余额工具/图片/看图扣10。 |
| 13–14 | 同文件high有余额平台回复/零余额精确三个事件不落库；possible成功后一次资源，失败资源在error前且一次。 |
| 15 | 同文件401/404/429/超时/连接错误/需重填/不可用、真实配置坏密文/缺密钥/读取错误，无平台回退、退款、无Key/URL/模型名错误回显，trace标byok及安全provider。 |
| 16–17 | 同文件空回复、refusal有无正文、reply_model只在BYOK；关闭配置保持平台精确事件；每日上限及DEV放行，零余额配置被删/关/需重填不得走平台。 |
| 18 | 同文件启用BYOK后创建、接受并完成分身交流，断言用户客户端零调用。 |
| 19 | test_byok_api：no-store/白名单、不回显各类非法Key、改厂商/地址需Key、PATCH/DELETE/needs_reentry、无401、连接测试错误分类/HTTP200/每日额度/草稿不保存；额外覆盖分钟额度与鉴权403。 |

实现采用文件独占分工：核心子代理先确定对外签名，再并行启动后端集成与前端；根代理负责依赖/模板/六份文档/验收/报告，另有只读审查代理，未交叉编辑。派发时均未传model或reasoning_effort。

## 4. R1 返修

R1阶段采用原三个文件独占分组，根代理负责文档与验收；额外只读复核不编辑生产文件。没有传 `model` 或 `reasoning_effort` 参数。每项先新增回归并实际确认失败，再修生产代码；R1-10 对原本正确的防线先测绿色，再故意改坏、确认红色、恢复并重测。临时前端/文档测试放在仓库外，没有增加白名单外的文件。

| 返修项 | 最终实现 | 新测试与修复前失败摘要（红测试退出码均 1） |
|---|---|---|
| R1-1 | PinnedTransport 以 raw_host 的 ASCII 小写比较，scheme/443 检查不变。Unicode/punycode 均固定 8.8.8.8:443，SNI 使用 xn--fsqu00a.com。 | `test_r1_idna_actual_sdk_stream`：2 failed，httpx.ConnectError / OpenAI.APIConnectionError；修后2 passed。 |
| R1-2 | pending 守卫移到补全参数的付费执行之前；免费取消/追问、转聊天与手动镜子恢复清理。仅新工具意图进入 stream_intent 前的条件清理保留并注明6.9#11。天气恢复平台城市判断；R1擅加的关键词条件已按R2-3删除，4c消息按裁定改为「我今天心情不好」。城市纯函数不改。 | `test_r1_pending_api_free_actions_and_paid_guards`（24）、`test_r1_pending_missing_parameter_remains_free`（2）：13 failed/13 passed，pending未清或免费操作被拦；修后26 passed。补充 `test_r1_platform_weather_pending_keeps_legacy_city_handling`（2）先2 failed（平台基线误变普通text）再绿，最终28 passed。API涵盖0/10余额、真实接口造pending、新工具守卫和天气hit=False。 |
| R1-3 | 非DashScope省略空system；Claude顶层system只在非空时传；普通聊天仍一份末尾安全规则，DashScope原样。 | `test_r1_test_connection_omits_empty_system_openai`（4）、`test_r1_test_connection_omits_system_anthropic_real_sdk`：5 failed，实际请求含空system；修后5 passed，连同原真实请求/安全规则测试21 passed。 |
| R1-4 | custom每连接读HTTP字节累计4,194,304上限，超限backend.abort并抛httpcore.ReadError，经httpx/SDK固定映射connection。 | `test_r1_custom_response_bytes_are_bounded`（无换行SSE / 401无限错误体）：2 failed，实际送出6,291,529 > 4,194,304+65,536；修后2 passed，读取/发出均不超过上限+一个块。固定文案选择「你的模型调用失败：连不上该服务。本条没有改用平台模型。」。 |
| R1-5（按R1b更正） | 禁用清单十一项，保留ANTHROPIC_CUSTOM_HEADERS；移除八个代理名和大小写不敏感拦截。预设遵循服务器出站代理，custom继续忽略环境代理，审计决定见第5节。 | `test_r1_environment_audit_blocks_request_mutators` 的代理分支、`test_r1_mixed_case_proxy_environment_is_allowed` 与 `test_r1b_preset_sdk_reads_https_proxy_but_custom_does_not`：修正断言后先22 failed/2 passed（availability仍False），再24 passed。ANTHROPIC_CUSTOM_HEADERS分支仍禁止构造SDK。原R1过宽代理断言按R1b第3条调整，具体原→新见下文。 |
| R1-6 | public SDK stream.response.extensions[network_stream]取socket先shutdown(SHUT_RDWR)；custom取消也abort。R2-1将关闭移至阻塞调用返回后的owner线程。公开ReplyStreamControl在建流前可取消；_byok_call先abort再等worker，读异常回收后仍抛CancelledError，流关闭与槽位释放。 | 核心 `test_r1_abort_interrupts_public_response_socket_before_close`、`test_r1_custom_close_aborts_on_cancellation_not_just_timeout`、`test_r1_request_control_aborts_before_stream_construction_returns`：3 failed（首事件stream_close而非shutdown）。集成 `test_r1_cancel_interrupts_before_waiting_for_worker`：先2 failed（0.3秒内取消未完成），扩展建流/读取、worker读异常后4 passed。`test_r1_watchdog_public_socket_interrupts_blocking_read` 两SDK变异前后见下表；核心5 passed。`test_r1_watchdog_real_loopback` 两厂商实际尝试绑定127.0.0.1，2 skipped（沙箱EPERM/EACCES），没有宣称真实服务器验证通过。 |
| R1-7 | save与done移出BYOK异常域，落库失败由run_chat原异常处理，避免BYOK归因和该失败日志。 | `test_r1_reply_persistence_failure_uses_platform_error`（2）和 `test_r1_deleted_conversation_during_reply_is_platform_failure`（2）：各先2 failed，原返回「你的模型调用失败：调用失败…」而非平台文案；修后4 passed，真实首字后删会话无assistant落库、无BYOK失败日志、退还预扣。 |
| R1-8 | 两HTTP库网络基类/协议错误映射connection；OpenAI三种quota code映射quota且先检查str；Anthropic529/OverloadedError/流overloaded_error映射busy。 | `test_r1_direct_http_failure_classification`、`test_r1_openai_stream_quota_codes`、`test_r1_anthropic_overloaded_error`：先11 failed/2 passed，旧other分类错误；修后基本13项通过；另有 `test_r1_actual_openai_stream_error_quota`、`test_r1_actual_anthropic_stream_overloaded`、`test_r1_network_error_subclasses_keep_connection_category` 共6项，合跑19 passed。额外 `test_r1_malformed_openai_error_codes_do_not_crash` 测试的 malformed APIError dict/list code测试先2 failed（分类器TypeError）再2 passed；新增busy固定文案，无上游正文。 |
| R1-9 | storage版本/visible刷新使用独立read lane与mutation版本，作废旧读，dirty/busy保留厂商/模型/地址/Key而更新服务端config/available/开关；网络固定中文、加载重试、全429固定提示；删除复位首厂商默认型号/空地址/Key且无dirty。 | 临时真实TSX+useAccountRequest离线harness：首8项8 failed；追加初载失败刷新/迟到read/响应体网络失败后3 failed；再补400/503响应体TypeError，两项先failed。最终13 passed（输出见下）。tsc 0，eslint 0 errors/25 warnings。 |
| R1-10 | custom Client构造四参数防线、直接generated_image零余额入口、路由读配置失败而不建上下文/不写消息，均有独立测试和实际变异确认。 | `test_r1_custom_http_client_parameters_locked`、`test_r1_generated_image_direct_unreserved_guard`、`test_r1_route_config_read_failure_stops_before_context_or_user_message`。各变异内容、失败输出与恢复见下表。 |
| R1-11 | 五份文档隐私段补长期归档先清密文；DEPLOYMENT明确仅副本DELETE所有配置行并VACUUM、修正测试计次，同步十一环境变量、4MiB、所有厂商socket中断和busy文案；CYBER仍仅原R0许可段。 | 临时 `DocumentationR1.test_long_term_archive_removes_all_ciphertexts_from_copy`、`test_connection_test_daily_counter_boundary`、`test_runtime_safety_changes_documented`：3测试9个subtest/断言失败，缺归档步骤/计次措辞/运行限制；修后3测试全绿，退出0。 |

### R1-10 及额外中断变异的实际结果

| 变异 | 变红证据 | 恢复结果 |
|---|---|---|
| custom follow_redirects 改True | 1 failed，`assert True is False`，退出1 | 原值False恢复；参数测试1 passed，退出0 |
| custom trust_env 改True | 1 failed，`assert True is False`，退出1 | 原值False恢复；同上 |
| custom timeout 改30.0 | 1 failed，`assert 30.0 == 60.0`，退出1 | 60.0恢复；同上 |
| custom transport换MockTransport | 1 failed，`isinstance(..., PinnedTransport)`失败，退出1 | PinnedTransport恢复；同上 |
| 删除stream_generated_image直接零余额守卫 | 2 failed，首事件变generating_image而非草莓不足，退出1 | 守卫恢复，两个入口参数化测试通过 |
| has_enabled_config读取异常错误当enabled=True | 2 failed，错误进入BYOK并产生reply_model/用户消息，而非草莓不足，退出1 | 原错误处理恢复；与上一条合跑4 passed，退出0 |
| 额外：删除public socket shutdown中断 | 2 failed，阻塞读取0.30秒超过0.20秒阈值，退出1 | socket中断恢复；两个SDK阻塞桩通过，退出0 |

### R1阶段本任务新建测试的已有断言变更

**0处**：没有删除、改写或放宽首轮247项中已有的断言，故「原断言 → 新断言 → R1依据」为空。对比返修开始时五份测试快照确认这一点。客户端autouse fixture增加request参数，仅为新增两个R1-6真实测试精确允许127.0.0.1连接，其余测试断网拦截与teardown保留。R1阶段FORBIDDEN_ENV参数化曾增加9项，其中8个代理项按R1b撤销，保留新增ANTHROPIC_CUSTOM_HEADERS一项。所有本任务之前已有的backend/tests文件与受保护文件diff为空。

截至R1b结束，相对首轮新增后端收集用例103项（核心63，集成40），加首轮247共350；R1b相对R1阶段净增5项（代理/请求头跨两SDK增加9项、混合大小写跨SDK增加2项、真实默认传输增加2项，撤销8个动态禁用参数项：9+2+2−8=5）。前端13项及文档3项临时harness另计，不计入pytest数量。

### R1b 更正及允许修改的既有R1断言

R1b阶段由根代理直接完成，没有派新子代理。修改 `backend/byok/crypto.py`、`backend/tests/test_byok_client.py`、README、CLAUDE、PLAN、ARCHITECTURE、DEPLOYMENT、`.env.example` 与本报告；没有改变其他生产代码或新增仓库文件类别。custom原IP/SNI/HTTPS_PROXY防线测试保持原样。

| 位置 / 旧参数 | 原断言 | 新断言 | 依据 |
|---|---|---|---|
| `test_r1_environment_audit_blocks_request_mutators` 的HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY及四个小写参数 | `availability() == (False, "服务器暂未开启自带模型")` | `availability() == (True, None)` | R1b要求1、3撤销代理禁用 |
| 上述八个代理参数 | `with pytest.raises(ByokUnavailableError): open_reply_stream(...)` | 建流成功并消费「好」 | R1b要求2、3，预设SDK可正常构造 |
| 上述八个代理参数 | `assert not constructed` | `len(constructed) == 1`，客户端已关闭 | R1b要求3，验证构造器实际调用 |
| 原 `test_r1_mixed_case_proxy_environment_is_blocked` 的HtTpS_PrOxY/nO_pRoXy，现名 `_is_allowed` | `availability() == (False, "服务器暂未开启自带模型")` | `(True, None)`，并新增SDK构造/成功回复/关闭断言 | R1b要求1、3撤销大小写不敏感拦截 |

上述两处既有R1测试块覆盖十个旧代理参数；均扩展DeepSeek和Claude两SDK对照。ANTHROPIC_CUSTOM_HEADERS的三条禁用断言保持，不放宽其他既有断言；截至R1b阶段，首轮247项已有断言零修改；本轮R2-1允许的关闭时序修改见第6节。R1-6真实回环测试的有限fixture清除服务器代理，仅用于保证其只连接127.0.0.1；其他测试仍按SDK默认配置，外部网络拦截与teardown不变。

新增 `test_r1b_preset_sdk_reads_https_proxy_but_custom_does_not[deepseek/anthropic]`：只构造真实SDK/HTTP客户端，记录公开HTTPTransport构造参数，断言预设建立指定HTTPS代理传输且未传替代http_client；custom使用trust_env=False的PinnedTransport，不新增代理传输。流接口用内存桩，不发送请求。fixture继续硬拦截DNS和HTTP传输。

红测试实际为22 failed、2 passed，pytest退出1；修改crypto后24 passed，退出0。文档先六个文件subtest失败、退出1，再全部通过、退出0。代理从禁用清单移除的决策是R1b规格裁定，替换R1-5过宽表述；安装SDK源码审计证据仍有效。

### R1阶段前端离线行为用例实际输出

```text
PASS F0_storage_visible_preserve_dirty_key_and_update_server_state
PASS F0_consecutive_refresh_invalidates_old_read
PASS F0_busy_refresh_keeps_mutation_alive_and_draft_intact
PASS F0_refresh_after_initial_failure_and_clean_server_baseline
PASS F0_pending_refresh_cannot_overwrite_completed_save
PASS F1_initial_network_failure_is_chinese_and_retry_succeeds
PASS F1_all_settings_mutation_network_failures_are_chinese
PASS F1_footer_network_failure_is_chinese
PASS F1_response_body_network_failure_is_chinese
PASS F1_response_body_network_failure_is_chinese_400
PASS F1_response_body_network_failure_is_chinese_503
PASS F2_all_429_responses_use_fixed_message
PASS F3_delete_resets_empty_baseline_without_dirty
GREEN 13 tests, 0 failures; all requests offline
```

文档最终临时测试实际输出：

```text
test_connection_test_daily_counter_boundary (__main__.DocumentationR1.test_connection_test_daily_counter_boundary) ... ok
test_long_term_archive_removes_all_ciphertexts_from_copy (__main__.DocumentationR1.test_long_term_archive_removes_all_ciphertexts_from_copy) ... ok
test_runtime_safety_changes_documented (__main__.DocumentationR1.test_runtime_safety_changes_documented) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.001s

OK
```

## 5. R1-5 环境变量审计

审计对象为已安装的 anthropic 1.12.1、openai 2.37.0 的同步/异步构造器、`_base_client`，并追溯默认 HTTP 客户端、凭据链和代理发现。未安装包或访问网络。两个 `_base_client` 没有直接读取凭据环境变量；Anthropic 默认客户端自行调用 `get_environment_proxies`/`urllib.request.getproxies`，OpenAI 默认 httpx 的 `trust_env=True`。显式 Key、地址与 timeout 不会覆盖这些代理。

| 变量 | 加入 / 不加入 | 理由 |
|---|---|---|
| `OPENAI_ORG_ID` | 加入（保留） | 显式api_key不覆盖organization；自动注入OpenAI-Organization请求头。 |
| `OPENAI_PROJECT_ID` | 加入（保留） | 显式api_key不覆盖project；自动注入OpenAI-Project请求头。 |
| `OPENAI_CUSTOM_HEADERS` | 加入（保留） | 无条件合并default_headers，可改变认证等请求头。 |
| `OPENAI_BASE_URL` | 加入（保留） | 当前显式base_url会覆盖，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_BASE_URL` | 加入（保留） | 当前显式base_url会覆盖，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_AUTH_TOKEN` | 加入（保留） | 显式api_key阻止凭据环境发现，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_PROFILE` | 加入（保留） | 显式api_key阻止配置自动发现，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_FEDERATION_RULE_ID` | 加入（保留） | 显式api_key阻止联邦凭据自动发现，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_IDENTITY_TOKEN` | 加入（保留） | 显式api_key阻止联邦凭据自动发现，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_IDENTITY_TOKEN_FILE` | 加入（保留） | 显式api_key阻止联邦凭据自动发现，但02-spec第3节已要求禁止，保留该边界。 |
| `ANTHROPIC_CUSTOM_HEADERS` | 加入（R1新增） | anthropic/_client.py读取并无条件合并至default_headers；显式api_key/base_url/timeout不覆盖这些头。 |
| `HTTP_PROXY` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `HTTPS_PROXY` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `ALL_PROXY` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `NO_PROXY` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `http_proxy` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `https_proxy` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `all_proxy` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `no_proxy` | 不加入（R1b） | 运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP。 |
| `OPENAI_API_KEY` | 不加入 | 构造器明确传api_key；不读取用于认证的环境值。 |
| `OPENAI_ADMIN_KEY` | 不加入 | 构造器会读入，但聊天端点使用bearer_auth而非admin_api_key_auth；显式用户api_key优先，当前功能不调用管理端点。 |
| `OPENAI_WEBHOOK_SECRET` | 不加入 | 只用于webhook验签；当前功能不调用webhook。 |
| `ANTHROPIC_API_KEY` | 不加入 | 构造器明确传api_key；不会采用该值作为认证。仅凭据发现警告检查会读取其存在性。 |
| `ANTHROPIC_WEBHOOK_SIGNING_KEY` | 不加入 | 只用于webhook验签；当前功能不调用webhook。 |
| `ANTHROPIC_CONFIG_DIR` | 不加入 | 显式api_key使default_credentials分支不可达；可能触发静态凭据遮蔽配置的一次日志，不改变请求头/目标/凭据/代理。 |
| `ANTHROPIC_ORGANIZATION_ID` | 不加入 | 只用于联邦/配置凭据链；显式api_key使该链不可达。 |
| `ANTHROPIC_SERVICE_ACCOUNT_ID` | 不加入 | 只用于联邦/配置凭据链；显式api_key使该链不可达。 |
| `ANTHROPIC_WORKSPACE_ID` | 不加入 | 只用于联邦/配置凭据链；显式api_key使该链不可达，不自动注入工作区头。 |
| `ANTHROPIC_SCOPE` | 不加入 | 只用于OAuth/联邦凭据链；显式api_key使该链不可达。 |
| `APPDATA` | 不加入 | 仅Windows配置目录发现使用；显式api_key使配置加载链不可达。 |
| `OPENAI_LOG` | 不加入 | 仅SDK日志级别，R1第3节明确不处理S3，不改变四类请求设置。 |
| `ANTHROPIC_LOG` | 不加入 | 仅SDK日志级别，R1第3节明确不处理S3，不改变四类请求设置。 |
| `DEFER_PYDANTIC_BUILD` | 不加入 | 仅模型schema构造时机，不改变四类请求设置。 |
| `SSL_CERT_FILE` | 不加入 | 仅CA证书验证根配置，不改变请求目标/头/凭据/代理；custom trust_env=False且PinnedTransport不受其影响。 |
| `SSL_CERT_DIR` | 不加入 | 仅CA证书验证根配置，不改变请求目标/头/凭据/代理；custom trust_env=False且PinnedTransport不受其影响。 |
| `REQUEST_METHOD` | 不加入 | urllib的CGI代理防护规则，随预设SDK的服务器出站设置处理；custom已trust_env=False，不作为禁用项。 |

禁用清单为十一项，包含ANTHROPIC_CUSTOM_HEADERS；代理变量不加入，也没有大小写不敏感的代理拦截。预设厂商（含 Claude）遵循服务器的 HTTP(S)_PROXY / NO_PROXY 出站代理设置；自定义地址不使用环境代理。ALL_PROXY同样按预设SDK默认规则生效。原规格指定的认证/请求头变量继续保留禁用。文档、`.env.example` 与代码一致。

源码读取证据（同一个变量在同步/异步构造器重复读取，下面保留实际行号；这些是依赖包相对路径）：

- `openai/_client.py`：L174 api_key = os.environ.get("OPENAI_API_KEY")；L184 admin_api_key = os.environ.get("OPENAI_ADMIN_KEY")；L199 organization = os.environ.get("OPENAI_ORG_ID")；L203 project = os.environ.get("OPENAI_PROJECT_ID")；L207 webhook_secret = os.environ.get("OPENAI_WEBHOOK_SECRET")；L213 base_url = os.environ.get("OPENAI_BASE_URL")；L217 custom_headers_env = os.environ.get("OPENAI_CUSTOM_HEADERS")；L680 api_key = os.environ.get("OPENAI_API_KEY")；L690 admin_api_key = os.environ.get("OPENAI_ADMIN_KEY")；L705 organization = os.environ.get("OPENAI_ORG_ID")；L709 project = os.environ.get("OPENAI_PROJECT_ID")；L713 webhook_secret = os.environ.get("OPENAI_WEBHOOK_SECRET")；L719 base_url = os.environ.get("OPENAI_BASE_URL")；L723 custom_headers_env = os.environ.get("OPENAI_CUSTOM_HEADERS")
- `openai/_base_client.py`：没有直接 `os.environ` / `os.getenv` 读取。
- `openai/_utils/_logs.py`：L23 env = os.environ.get("OPENAI_LOG")
- `anthropic/_client.py`：L105 if api_key is not None and os.environ.get("ANTHROPIC_API_KEY"):；L107 if auth_token is not None and os.environ.get("ANTHROPIC_AUTH_TOKEN"):；L223 api_key = os.environ.get("ANTHROPIC_API_KEY") or None；L224 auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or None；L230 webhook_key = os.environ.get("ANTHROPIC_WEBHOOK_SIGNING_KEY")；L234 base_url = os.environ.get("ANTHROPIC_BASE_URL")；L243 custom_headers_env = os.environ.get("ANTHROPIC_CUSTOM_HEADERS")；L665 api_key = os.environ.get("ANTHROPIC_API_KEY") or None；L666 auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or None；L672 webhook_key = os.environ.get("ANTHROPIC_WEBHOOK_SIGNING_KEY")；L676 base_url = os.environ.get("ANTHROPIC_BASE_URL")；L685 custom_headers_env = os.environ.get("ANTHROPIC_CUSTOM_HEADERS")
- `anthropic/_base_client.py`：L116 from ._utils._httpx import get_environment_proxies；L953 proxy_map = {key: None if url is None else Proxy(url=url) for key, url in get_environment_proxies().items()}；L1651 proxy_map = {key: None if url is None else Proxy(url=url) for key, url in get_environment_proxies().items()}
- `anthropic/_utils/_httpx.py`：L32 def get_environment_proxies() -> Mapping[str, str | None]:；L40 proxy_info = getproxies()
- `anthropic/_utils/_logs.py`：L17 env = os.environ.get("ANTHROPIC_LOG")
- `anthropic/lib/credentials/_constants.py`：L78 env = os.environ.get(ENV_CONFIG_DIR)；L82 appdata = os.environ.get("APPDATA")；L105 env = os.environ.get(ENV_PROFILE)；L224 env = os.environ.get(ENV_IDENTITY_TOKEN_FILE)；L240 if os.environ.get(ENV_PROFILE) or os.environ.get(ENV_CONFIG_DIR):；L244 if os.environ.get(ENV_FEDERATION_RULE_ID) and os.environ.get(ENV_ORGANIZATION_ID):；L245 if os.environ.get(ENV_IDENTITY_TOKEN_FILE) or os.environ.get(ENV_IDENTITY_TOKEN):
- `anthropic/lib/credentials/_chain.py`：L33 federation_rule_id = os.environ.get(ENV_FEDERATION_RULE_ID)；L34 organization_id = os.environ.get(ENV_ORGANIZATION_ID)；L35 has_literal_token = ENV_IDENTITY_TOKEN in os.environ；L50 value = os.environ.get(ENV_IDENTITY_TOKEN)；L65 service_account_id=os.environ.get(ENV_SERVICE_ACCOUNT_ID),；L69 workspace_id=os.environ.get(ENV_WORKSPACE_ID) or None,；L70 scope=os.environ.get(ENV_SCOPE),；L108 if os.environ.get(ENV_API_KEY):；L112 auth_token = os.environ.get(ENV_AUTH_TOKEN)；L119 env_explicit = bool(os.environ.get(ENV_PROFILE) or os.environ.get(ENV_CONFIG_DIR))
- `anthropic/lib/credentials/_providers.py`：L97 v = os.environ.get(env_var)；L111 v = os.environ.get(ENV_IDENTITY_TOKEN_FILE)；L137 value = os.environ.get(self._env_var)
- `httpx/_client.py`：L49 from ._utils import URLPattern, get_environment_proxies；L201 trust_env: bool = True,；L246 for key, url in get_environment_proxies().items()；L648 trust_env: bool = True,；L722 trust_env: bool = True,；L745 trust_env: bool = True,；L1373 trust_env: bool = True,；L1436 trust_env: bool = True,；L1459 trust_env: bool = True,
- `httpx/_utils.py`：L30 def get_environment_proxies() -> dict[str, str | None]:；L33 # urllib.request.getproxies() falls back on System；L37 proxy_info = getproxies()
- `httpx/_config.py`：L26 trust_env: bool = True,；L34 if trust_env and os.environ.get("SSL_CERT_FILE"):  # pragma: nocover；L35 ctx = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])；L36 elif trust_env and os.environ.get("SSL_CERT_DIR"):  # pragma: nocover；L37 ctx = ssl.create_default_context(capath=os.environ["SSL_CERT_DIR"])
- `httpx2/_client.py`：L56 from ._utils import URLPattern, get_environment_proxies；L192 trust_env: bool = True,；L233 return {key: None if url is None else Proxy(url=url) for key, url in get_environment_proxies().items()}；L622 trust_env: bool = True,；L694 trust_env: bool = True,；L717 trust_env: bool = True,；L1470 trust_env: bool = True,；L1531 trust_env: bool = True,；L1554 trust_env: bool = True,
- `httpx2/_utils.py`：L30 def get_environment_proxies() -> dict[str, str | None]:；L33 # urllib.request.getproxies() falls back on System；L37 proxy_info = getproxies()
- `httpx2/_config.py`：L27 trust_env: bool = True,；L35 if trust_env and os.environ.get("SSL_CERT_FILE"):  # pragma: no cover；L36 ctx = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])；L37 elif trust_env and os.environ.get("SSL_CERT_DIR"):  # pragma: no cover；L38 ctx = ssl.create_default_context(capath=os.environ["SSL_CERT_DIR"])

另审阅模型初始化的 `DEFER_PYDANTIC_BUILD` 与 HTTP 客户端的 CA/代理读取；其加入决定见上表。`REQUEST_METHOD` 是 urllib 的 CGI 代理防护条件，按R1b允许的服务器出站配置处理，不加入禁用清单。

## 6. R2 返修

本节保留R2阶段证据；custom中断阶段的描述已依R3-5更正，当前新增行为与验收见第7–8节。

本轮三个子代理分别独占核心、后端集成、前端文件，根代理负责文档与验收；第四个子代理只读复核，没有交叉写同一文件。派发均未传 `model` 或 `reasoning_effort`。每项缺陷先对原生产代码跑新增回归并确认失败，再修改；补充原本正确行为的对照项保持原断言，未制造虚假的失败证据。没有触发第8节的功能冲突停止条件。

| 返修项 | 改了什么 | 新测试名、修复前失败摘要与最终结果 |
|---|---|---|
| R2-1 | `_Resources`独立维护closed/timed_out/disposed，控制器、ReplyStream.abort、timer与custom backend的中断线程仅标记并shutdown；不close socket/流/client/http_client/manager/连接池。owner在`_consume finally`、`_open except`或线程池中的stream.close完成幂等关闭。 | `test_r2_interrupt_defers_all_close_to_owner`（3）、`test_r2_custom_interrupt_only_shuts_down_until_owner_close`：修前4 failed，中断事件包含close；修后4 passed。`test_r2_cancelled_open_closes_returned_stream_on_worker_after_return`补充验证worker返回后才在池线程关闭。`test_r2_loopback_interrupt_race`（deepseek/anthropic × watchdog/cancel，4项，每项20次）SDK读超时3秒，watchdog每次<1.2秒、cancel每次<1秒，每组<15秒、合计<60秒；4项因bind EPERM显式skip，未声称完成80次实跑。 |
| R2-2 | 只对custom覆盖Accept-Encoding为identity；非空、非identity Content-Encoding在构造httpx.Response之前abort并抛映射后的ReadError。固定类别connection/「连不上该服务」。 | `test_r2_custom_forces_identity_request_encoding`（4）：修前头为gzip/deflate/br或GZIP，4 failed；修后通过。`test_r2_custom_rejects_encoding_before_gzip_bomb_decode`（5）：MockBackend提供对应64MiB明文的gzip，修前进入decoder trap而5 failed；修后decoder调用0、解码字节0、peak<16MiB。删除编码检查变异再次5 failed，退出1；恢复后全core224 passed/6 skipped，退出0。 |
| R2-3 | 删除上轮`conversational`关键词条件，精确恢复`state.crisis_level in {"high", "possible"} or not normalize_city(ctx.message)`。按规格裁定修正4c消息，未修改城市函数。 | `test_r2_paid_weather_pending_routing_matches_platform`：余额10、天气pending发「开心」，修前BYOK普通回复与平台天气工具路径不同，1 failed；修后事件序列、weather参数、余额、BYOK零调用均与未配置对照一致。既有weather_chat两项fixture改「我今天心情不好」，期望不变。 |
| R2-4 | 在pending参数补全执行分支、余额守卫之前，为未预扣且非generate_image/weather的用户添加精确取消/转聊天正则；免费出口清pending，其他消息仍草莓不足且保留pending。paid和平台逻辑不变。 | `test_r2_zero_balance_other_pending_free_exits`（4）：真接口在余额10造route/web_search pending再置0；修前route「算了」「换个话题」、web_search「算了」3 failed；修后取消落库且免费，换话题BYOK一次带reply_model，「从家出发」保留pending且工具0次。`test_r2_paid_other_pending_matches_platform`（6）验证paid对照保持一致；集成最终151 passed。 |
| R2-5 | Form refreshError ref标记加载错误；refresh成功仅清自身错误，save/test/toggle/remove开始复位标志。 | `R2_F0_test_error_survives_visible_refresh`、`R2_F0_test_error_survives_rev_refresh`及四个`R2_F0_*_starts_new_error_ownership`修前6 failed，操作失败提示被刷新清掉；修后全部通过。`R2_F0_refresh_success_clears_only_refresh_failure`原本通过，保留为对照。真实TSX+useAccountRequest离线组件harness共22 passed。 |
| R2-6 | 文档说明响应头前预设最多再等60秒，custom即时中断；初次等待用asyncio.wait再result，取消shield等待后显式future.exception()；平台测试分钟限流HTTP200、固定平台文案；Footer失败可点重试并在visible刷新。 | 文档`DocumentationR2.test_r2_header_boundary_and_owner_close_documented`、`test_r2_custom_identity_and_encoding_rejection_documented`、`test_r2_platform_test_minute_message_documented`：修前3测试/13 subtest失败，退出1；修后3 passed/退出0。`test_r2_cancelled_worker_exception_is_retrieved_without_shield_log`修前caplog含ERROR「exception in shielded future」，1 failed；`test_r2_connection_minute_cap_uses_platform_message`修前BYOK前缀文案，1 failed；修后均通过。`R2_F3_footer_initial_failure_has_working_retry`、`R2_F3_footer_visible_recovers_initial_failure`修前2 failed，修后通过。 |

R2-1响应头边界：响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时。中断线程不提前关闭fd；最终关闭发生在属主worker中。

主控沙箱外复跑发现回环测试的0.10秒看门狗可能在建流阶段提前到期，产品行为正确；本次仅调整 `test_r2_loopback_interrupt_race`：watchdog预算改为0.6秒，明确断言首个片段在看门狗到期前到达，阻塞读取返回阈值改为1.2秒（仍小于SDK的3秒读超时），cancel仍为1秒，每用例20次且整例小于15秒、四例合计小于60秒；生产代码和其他测试未改，沙箱内仅做静态验证，主控将于沙箱外连跑，本段保留该次测试预算调整的记录；第8节输出为R3修复后的最新实跑。

### 新增用例及实际红绿记录

R2后端净增31项：core17、integration14；基线350→381，没有删减收集项。前端新增9项、文档临时3项另计。核心新回归对原生产代码为`13 failed, 4 skipped, 186 deselected in 1.69s`（退出1），修后`13 passed, 4 skipped, 186 deselected in 1.44s`（退出0）。集成RED为`6 failed, 7 passed, 137 deselected, 14 warnings in 1.88s`（退出1），最终`151 passed, 14 warnings in 5.55s`（退出0）。集成补充的owner-close项本来就是正确安排，单独加强顺序验证，不虚称其修前失败。

前端RED为`9 tests, 8 failures`（退出1），加载错误恢复对照原本绿色；最终含旧13项为`22 tests, 0 failures`（退出0）。文档RED为`Ran 3 tests / FAILED (failures=13)`（退出1），GREEN为`Ran 3 tests / OK`（退出0）。gzip删除检查的实际变异输出摘要：

```text
FAILED test_r2_custom_rejects_encoding_before_gzip_bomb_decode[gzip]
FAILED test_r2_custom_rejects_encoding_before_gzip_bomb_decode[GZip]
FAILED test_r2_custom_rejects_encoding_before_gzip_bomb_decode[deflate]
FAILED test_r2_custom_rejects_encoding_before_gzip_bomb_decode[br]
FAILED test_r2_custom_rejects_encoding_before_gzip_bomb_decode[gzip, identity]
AssertionError: compressed BYOK body reached a decoder
5 failed, 72 deselected in 2.01s
```

变异退出码1，防线已立即恢复；后续第7节验收在恢复之后运行。64MiB压缩测试用decoder trap避免在变异时实际解压危险明文，绿色必须在decoder调用前拒绝，内存峰值断言仍有效。

### 允许修改的既有BYOK测试（原→新→依据）

| 位置 | 原断言/桩 | 新断言/桩 | 依据与保留的约束 |
|---|---|---|---|
| `test_watchdog_interrupts_blocking_stream_and_closes_client` | stream.close唤醒；`assert released.wait(0.5), "watchdog did not close blocking read"` | 公开socket.shutdown唤醒；同0.5秒wait，诊断改为did not shut down blocking read | R2-1中断不得close；最终started/client.closed/stream.closed断言保留。 |
| `test_watchdog_expires_during_stream_construction` | `assert closed.wait(0.5), "watchdog did not close construction"` | `assert expired.wait(0.5), "watchdog did not mark construction as expired"`并断言构造未返回时client未closed | R2-1与R2-6响应头前边界；owner返回/except后的client与stream关闭断言保留。 |
| `test_r1_abort_interrupts_public_response_socket_before_close` | `events[1][0] == "socket_close"`，`events[2:] == [stream_close,client_close]` | abort后仅shutdown；没有显式socket_close；owner.close后`events[1:] == [stream_close,client_close]` | R2-1禁止中断线程close；初始shutdown与最终流/client关闭仍严格验证。 |
| `test_r1_request_control_aborts_before_stream_construction_returns` | 构造中control.abort后`assert clients[0].closed` | `assert not clients[0].closed` | R2-1中断与关闭分离；_open except后原client.closed断言保留。 |
| `test_abort_records_and_shuts_down_socket_before_close` | `events[1][0] == "socket_close"` | 保存abort阶段快照，全部为shutdown且无socket_close | R2-1 custom backend.abort不得关闭；owner stream.close的最终断言保留。 |
| `test_r1_pending_api_free_actions_and_paid_guards` weather_chat fixture（余额0/10） | 「今天心情不好」 | 「我今天心情不好」；原所有断言不变 | R2-3明确修正表4c消息。 |
| `test_connection_minute_cap_returns_200_without_eleventh_call` JSON message | 「你的模型调用失败：额度不足或请求过于频繁。本条没有改用平台模型。」 | 「操作太频繁，请稍后再试」 | R2-6.3明确改平台限流文案；200、ok:false与第11次不调上游等原断言保留。 |

只有上述7处既有用例/fixture调整。`test_byok_store.py`与首轮其他断言未动；五份测试已对比本轮开始快照，全部差异为上述授权或新用例。断网夹具仅对精确R1/R2回环测试前缀放行127.0.0.1，其余测试继续阻止DNS/HTTP真实请求。

只读复核未发现阻断项，确认生产行为与断言修改符合R2。三个owner的红绿/变异日志和manifest均保存在仓库外临时目录；本报告包含必要证据，未增加白名单外文件。

## 7. R3 返修

本轮按要求由根代理直接完成，没有派子代理。先写新增失败回归并实际确认RED，再改生产代码；Playwright启动权限限制属于验证方式限制，按第8节继续工作并明确记录。没有发现影响产品实现的规格矛盾。

| 返修项 | 实现 | 新测试、修复前失败摘要与结果 |
|---|---|---|
| R3-1 | Footer增加refreshError ref：读取失败先取得错误归属；读取成功先setSettings，只清读取自己的错误。toggle开始及catch写错误前复位，避免操作失败被可见/跨文档刷新清掉。 | `R3_F0_footer_toggle_error_survives_visible_refresh`、`R3_F0_footer_toggle_error_survives_rev_refresh`、`R3_F0_footer_refresh_during_toggle_does_not_own_toggle_failure`：修前3 failed，成功GET清掉切换失败提示；修后通过。`R3_F0_footer_visible_clears_initial_load_error`修前已绿，是加载错误恢复对照。指定Playwright三场景脚本已准备，实跑启动被MachPort Permission denied拒绝，退出2、浏览器断言未执行，需主控补跑。 |
| R3-2 | 两个SDK分支在resources.start之后、发送函数之前检查resources.closed，按timed_out抛ByokTimeoutError或ReplyInterruptedError；原except统一由owner关闭，未给中断线程增加close。 | `test_r3_interrupt_before_sdk_send_makes_no_request`（cancel/watchdog × deepseek/anthropic，4项）：start原方法启动后立即abort或expire；修前4 failed，cancel触发不应调用的SDK send断言，watchdog发送记录非空；修后发送函数0次、正确异常、client最终关闭，4项通过。 |
| R3-3 | 天气pending的normalize_city判断前，仅byok_unreserved且以先聊/聊点/换个话题/先不开头时清pending并继续普通路由；有余额与平台保持原天气逻辑。 | `test_r3_zero_balance_weather_pending_topic_exit`（4个前缀）：修前4 failed，pending未清且返回草莓不足；修后pending清、BYOK1次带reply_model、工具/平台回复0次、余额0不变。`test_r3_paid_weather_topic_exit_matches_unconfigured_platform`修前即通过，余额10发换个话题时事件、工具参数、额度和余额与未配置对照一致；原R2“开心”对照断言未改。 |
| R3-4 | Form的save/test/toggle/remove四个catch，在有效owner写错误前复位refreshError；test业务失败result.ok=false分支同样复位。 | `R3_F1_PUT_operation_error_survives_busy_refresh_race`、`R3_F1_POST_operation_error_survives_busy_refresh_race`、`R3_F1_PATCH_operation_error_survives_busy_refresh_race`、`R3_F1_DELETE_operation_error_survives_busy_refresh_race`、`R3_F1_POST-result_operation_error_survives_busy_refresh_race`：操作未完成时先令GET失败，随后操作失败，再成功刷新；修前5 failed，操作自己的错误消失；修后5项通过。 |
| R3-5 | 六份文档/模板写清custom TLS建立后可立即中断、DNS约5秒和TCP/TLS连接约60秒上限；CLAUDE/ARCHITECTURE及README计费/DEPLOYMENT明确其他pending的免费取消、四前缀转聊、补参仍保留，以及天气pending的BYOK专属零余额出口。 | `DocumentationR3.test_r3_custom_dns_connect_tls_limits_documented`、`test_r3_zero_balance_free_exit_rules_documented`：修前2测试10个文件subtest失败，退出1；补查ARCHITECTURE旧“免费取消、缺参追问仍按平台逻辑”句又得到1失败/退出1，随后修正；最终2测试OK、退出0。不再用该笼统表述代替免费出口规则。 |

### 红绿实跑与已有断言

后端在`backend/`运行：

```bash
python -m pytest -q tests/test_byok_client.py tests/test_byok_chat.py -k test_r3
```

修前：`8 failed, 1 passed, 225 deselected, 14 warnings in 1.59s`，退出1；修后：`9 passed, 225 deselected, 14 warnings in 1.44s`，退出0。新增4个core用例、5个chat用例，381→390；未删收集项。平台有余额对照本来正确，不虚称RED。

前端临时离线组件harness加载实际TSX、真实chatModel库和useAccountRequest，覆盖真实回调、effects、独立读/写请求、延迟操作与刷新竞态，apiFetch被离线桩替换且任何真实fetch会抛错。R3新增9项，修前`RED 9 tests, 8 failures; all requests offline`、退出1，初载恢复对照本来绿色；修后含旧22项共`GREEN 31 tests, 0 failures; all requests offline`、退出0。文档新增2项临时回归，不计入pytest数量。

**本轮既有BYOK断言变更：0处。** 对本轮开始的五文件快照逐个比较AST，原模块语句/所有既有测试与断言完整保留，仅在client/chat测试文件末尾追加；另三文件字节不变。本任务之前已有75个测试/辅助Python文件的快照hash全不变；受保护文件git diff退出0。R2允许的七处历史调整仍见第6节，本轮没有再次修改它们；0.6秒回环预算也保持。

### Playwright步骤、脚本和实际限制

脚本位于任务目录之外的 `<临时目录>/fiona-byok-r3-frontend/playwright.cjs`，使用本机已有缓存Playwright 1.62.1和已缓存Chromium，没有安装包、启动应用或服务器。脚本从现有文件提取真实Footer，以已安装React/ReactDOM运行真实组件和useAccountRequest；同源测试页、GET/PATCH和第二文档全部由`context.route('**/*')`直接fulfill，其他请求abort，不调用route.continue，不访问厂商或任何真实服务。

预定三个浏览器场景：

1. GET返回有效配置，PATCH截获返回400/切换失败；点击改用平台后派发visibilitychange，确认新GET确实执行且原失败提示保留。
2. 同样令PATCH失败，在另一个同源文档写CHAT_MODEL_REV_KEY；确认原页收到原生storage事件并刷新GET，切换失败提示保留。
3. 初次GET截获返回加载失败；派发可见性事件后GET成功，配置恢复且仅加载错误消失。

实际命令为`node <临时目录>/fiona-byok-r3-frontend/playwright.cjs`，退出码**2**。浏览器在执行上述任何断言前启动失败，日志为：

```text
ENVIRONMENT BLOCKED: Playwright browser could not launch. No test reached the browser.
browserType.launch: Target page, context or browser has been closed
FATAL:base/apple/mach_port_rendezvous_mac.cc:159
Check failed: kr == KERN_SUCCESS. bootstrap_check_in ... Permission denied (1100)
process did exit: exitCode=null, signal=SIGTRAP
```

没有将环境失败作为功能RED，也没有声称Playwright三项通过；功能RED/GREEN证据来自上述离线实际组件回归。指定浏览器验证尚需主控沙箱外实跑，脚本保留可复用。

## 8. 第7节全部验收命令的实际输出与退出码

本轮全部重跑。后端用既有`.venv` Python及外置sitecustomize审计，阻止外部DNS/IPv4/IPv6，仅保留规格允许的127.0.0.1本地桩。每个BYOK测试文件断网fixture继续生效；前端npx设置npm_config_offline=true、npm_config_yes=false，只用既有工具。未安装包、运行build/dev、启动应用或发起真实外网请求。

以下每条第7节命令均保留完整实际输出和命令自身退出码，空输出标明；只替换工作区绝对路径、用户缓存与Python运行时路径，没有删堆栈或改测试结果。

| 验收项 | 退出码 | 实际结论 |
|---|---:|---|
| 7.1 git status | 0 | 只有规格/R0白名单路径 |
| 7.2 protected/test diff | 0 | 无输出，任务前tests/受保护文件不变 |
| 7.3 两个grep | 1 / 1 | 均无匹配，grep无匹配正常退出1 |
| 7.4 精确依赖grep | 0 / 0 | 各一行精确版本 |
| 7.5 pip check | 0 | No broken requirements found. |
| 7.5 full pytest | 1 | 2806 passed；1 failed/5 errors为六项既有端口权限失败；6回环skip |
| 7.6 tsc / eslint | 0 / 0 | tsc无输出；0 errors / 25 warnings |
| BYOK五文件 / R3专项 | 0 / 0 | 384 passed / 6 skipped；9 passed |
| BYOK收集 | 0 | 390 tests collected，R3新增9 |
| R2专项 / R1b代理专项 | 0 / 0 | 27 passed / 4 skipped；24 passed |
| R1b crypto代理grep | 1 | 无输出，11项禁用策略未改 |

R3字面passed门槛为2809+9=**2818**。当前实际2806 passed，另六项既有端口失败和六项回环skip：2806+6+6=2818。沙箱通过数增加9，没有新增失败或减少断言；**完整passed门槛仍待主控补跑12项后确认**，没有将failed/error/skip计为passed。

### 7.1

目录：`.`；命令：

```bash
git status --porcelain
```

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/.env.example
 M backend/database.py
 M backend/main.py
 M backend/rate_limit.py
 M backend/requirements.txt
 M backend/routers/chat.py
 M backend/services/chat_service.py
 M docs/ARCHITECTURE.md
 M docs/CYBER_AVATAR_PLATFORM.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/app/settings/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/components/Sidebar.tsx
?? backend/byok/
?? backend/routers/chat_model.py
?? backend/tests/test_byok_api.py
?? backend/tests/test_byok_chat.py
?? backend/tests/test_byok_client.py
?? backend/tests/test_byok_store.py
?? backend/tests/test_byok_url_safety.py
?? docs/tasks/2026-10-09-byok-chat-model/
?? frontend/components/ChatModelSection.tsx
?? frontend/lib/chatModel.ts
```

退出码：`0`。

### 7.2

目录：`.`；命令：

```bash
git diff --exit-code -- backend/llm.py backend/exchange_service.py backend/services/exchange_service.py backend/exchange_models.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/persona.py backend/tools backend/utils/safe_http.py backend/tests
```

```text
（无输出）
```

退出码：`0`。

### 7.3a

目录：`.`；命令：

```bash
grep -rn "alias_httpx\|lru_cache" backend/byok
```

```text
（无输出）
```

退出码：`1`。

### 7.3b

目录：`.`；命令：

```bash
grep -rn "str(e)\|str(exc)\|str(error)" backend/byok backend/routers/chat_model.py
```

```text
（无输出）
```

退出码：`1`。

### 7.4a

目录：`.`；命令：

```bash
grep -n "^anthropic==1.12.1$" backend/requirements.txt
```

```text
17:anthropic==1.12.1
```

退出码：`0`。

### 7.4b

目录：`.`；命令：

```bash
grep -n "^cryptography==50.0.0$" backend/requirements.txt
```

```text
18:cryptography==50.0.0
```

退出码：`0`。

### 7.5a

目录：`backend`；命令：

```bash
python -m pip check
```

```text
WARNING: The directory '<用户缓存目录>/pip' or its parent directory is not owned or is not writable by the current user. The cache has been disabled. Check the permissions and owner of that directory. If executing pip with sudo, you should use sudo's -H flag.
No broken requirements found.
```

退出码：`0`。

### 7.5b

目录：`backend`；命令：

```bash
python -m pytest -q
```

```text
........................................................................ [  2%]
........................................................................ [  5%]
........................................................................ [  7%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 17%]
........................................................................ [ 20%]
........................................................................ [ 22%]
........................................................................ [ 25%]
........................................................................ [ 28%]
...........................ss.................ssss...................... [ 30%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 53%]
........................................................................ [ 56%]
.......................................................EF............... [ 58%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 79%]
........................................................................ [ 81%]
...................EEE.E................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..........                                                               [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1100fec80>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python运行时>/socketserver.py:457: in __init__
    self.server_bind()
<Python运行时>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1133bfce0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python运行时>/socketserver.py:478: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x111ff23c0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python运行时>/socketserver.py:457: in __init__
    self.server_bind()
<Python运行时>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x114467240>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python运行时>/socketserver.py:478: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x111ff2eb0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python运行时>/socketserver.py:457: in __init__
    self.server_bind()
<Python运行时>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1143e6250>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python运行时>/socketserver.py:478: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x111fb0d00>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python运行时>/socketserver.py:457: in __init__
    self.server_bind()
<Python运行时>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1143e4c50>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python运行时>/socketserver.py:478: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1141726d0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python运行时>/socketserver.py:457: in __init__
    self.server_bind()
<Python运行时>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x11423da90>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python运行时>/socketserver.py:478: PermissionError
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x112801f20>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110b3d9b0>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python运行时>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python运行时>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python运行时>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x114039640>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted

<Python运行时>/asyncio/base_events.py:1637: PermissionError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 12 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2806 passed, 6 skipped, 14 warnings, 5 errors in 76.40s (0:01:16)
```

退出码：`1`。

### 7.6a

目录：`frontend`；命令：

```bash
npx tsc --noEmit
```

```text
（无输出）
```

退出码：`0`。

### 7.6b

目录：`frontend`；命令：

```bash
npx eslint .
```

```text

frontend/app/page.tsx
   146:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   237:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   483:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   536:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   537:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   538:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   548:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   549:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   550:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   551:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   554:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   560:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   561:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   865:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   959:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1383:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1403:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1411:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1432:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1474:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1570:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1911) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  2010:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  2050:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2320:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

退出码：`0`。

### R1b-1

目录：`.`；命令：

```bash
grep -n "PROXY\|proxy" backend/byok/crypto.py
```

```text
（无输出）
```

退出码：`1`。

### extra-byok

目录：`backend`；命令：

```bash
python -m pytest -q tests/test_byok_store.py tests/test_byok_url_safety.py tests/test_byok_client.py tests/test_byok_chat.py tests/test_byok_api.py
```

```text
........................................................................ [ 18%]
........................................................................ [ 36%]
...............................................................ss....... [ 55%]
..........ssss.......................................................... [ 73%]
........................................................................ [ 92%]
..............................                                           [100%]
=============================== warnings summary ===============================
tests/test_byok_chat.py: 14 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
384 passed, 6 skipped, 14 warnings in 7.06s
```

退出码：`0`。

### extra-r3

目录：`backend`；命令：

```bash
python -m pytest -q tests/test_byok_store.py tests/test_byok_url_safety.py tests/test_byok_client.py tests/test_byok_chat.py tests/test_byok_api.py -k test_r3
```

```text
.........                                                                [100%]
=============================== warnings summary ===============================
tests/test_byok_chat.py: 14 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
9 passed, 381 deselected, 14 warnings in 1.30s
```

退出码：`0`。

### extra-r2

目录：`backend`；命令：

```bash
python -m pytest -q tests/test_byok_store.py tests/test_byok_url_safety.py tests/test_byok_client.py tests/test_byok_chat.py tests/test_byok_api.py -k test_r2
```

```text
.............ssss..............                                          [100%]
=============================== warnings summary ===============================
tests/test_byok_chat.py: 14 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
27 passed, 4 skipped, 359 deselected, 14 warnings in 2.78s
```

退出码：`0`。

### extra-r1b

目录：`backend`；命令：

```bash
python -m pytest -q tests/test_byok_client.py -k 'environment_audit_blocks_request_mutators or mixed_case_proxy or r1b_preset_sdk'
```

```text
........................                                                 [100%]
24 passed, 106 deselected in 0.90s
```

退出码：`0`。

### 补充收集

目录：`backend`；命令：

```bash
python -m pytest --collect-only -q tests/test_byok_store.py tests/test_byok_url_safety.py tests/test_byok_client.py tests/test_byok_chat.py tests/test_byok_api.py
```

实际输出末行（其余为390个收集项名称）：

```text
390 tests collected in 0.72s
```

退出码：`0`。

### 前端离线组件最终输出

```text
PASS F0_storage_visible_preserve_dirty_key_and_update_server_state
PASS F0_consecutive_refresh_invalidates_old_read
PASS F0_busy_refresh_keeps_mutation_alive_and_draft_intact
PASS F0_refresh_after_initial_failure_and_clean_server_baseline
PASS F0_pending_refresh_cannot_overwrite_completed_save
PASS F1_initial_network_failure_is_chinese_and_retry_succeeds
PASS F1_all_settings_mutation_network_failures_are_chinese
PASS F1_footer_network_failure_is_chinese
PASS F1_response_body_network_failure_is_chinese
PASS F1_response_body_network_failure_is_chinese_400
PASS F1_response_body_network_failure_is_chinese_503
PASS F2_all_429_responses_use_fixed_message
PASS F3_delete_resets_empty_baseline_without_dirty
PASS R2_F0_test_error_survives_visible_refresh
PASS R2_F0_test_error_survives_rev_refresh
PASS R2_F0_refresh_success_clears_only_refresh_failure
PASS R2_F0_PUT_starts_new_error_ownership
PASS R2_F0_POST_starts_new_error_ownership
PASS R2_F0_PATCH_starts_new_error_ownership
PASS R2_F0_DELETE_starts_new_error_ownership
PASS R2_F3_footer_initial_failure_has_working_retry
PASS R2_F3_footer_visible_recovers_initial_failure
PASS R3_F0_footer_toggle_error_survives_visible_refresh
PASS R3_F0_footer_toggle_error_survives_rev_refresh
PASS R3_F0_footer_refresh_during_toggle_does_not_own_toggle_failure
PASS R3_F0_footer_visible_clears_initial_load_error
PASS R3_F1_PUT_operation_error_survives_busy_refresh_race
PASS R3_F1_POST_operation_error_survives_busy_refresh_race
PASS R3_F1_PATCH_operation_error_survives_busy_refresh_race
PASS R3_F1_DELETE_operation_error_survives_busy_refresh_race
PASS R3_F1_POST-result_operation_error_survives_busy_refresh_race
GREEN 31 tests, 0 failures; all requests offline
```

退出码：`0`。

### 文档离线回归最终输出

```text
..
----------------------------------------------------------------------
Ran 2 tests in 0.001s

OK
```

退出码：`0`。

## 9. 未完成或需要人工确认的地方

- R3五项实现和文档已完成，无影响实现的待裁定冲突；任务前测试及受保护文件未改，既有BYOK断言未变，没有安装任何包或发起外网请求。
- **指定Playwright三场景尚未执行**：缓存浏览器启动因MachPort Permission denied失败，退出2。临时拦截脚本已准备；离线实际组件31项全绿不代替浏览器验证，请主控在沙箱外执行该脚本。
- **完整pytest门槛待补验**：第8节的1 failed/5 errors均为既有127.0.0.1端口绑定PermissionError。6 skipped为原R1两个watchdog项与R2四个竞态项，后者已按主控裁定保留0.6秒建流预算、1.2秒阻塞读阈值、各20次及四例合计<60秒断言。此次没有把skip写为passed。第3轮复核记录提供的沙箱外中断实测结论来自主控，未算入本次本地验收数量。
- 构建、真实厂商调用和界面截图按原规格仍由主控沙箱外处理；本次没有运行应用或服务器。
- custom在TLS建立后可以立即中断；DNS约5秒、TCP/TLS建连约60秒上限属于既有行为，现已同步六份文档/模板。预设厂商在响应头前挂起仍最多再等60秒读超时。中断与owner关闭分离保持。
- R1b的11项环境变量禁用清单、预设服务器代理、custom固定IP且不信任环境代理、Key独立保管及长期归档清密文规则保持。reply_model气泡标记刷新后消失仍为原规格约定。

报告保留首轮/R1/R1b/R2有效阶段证据，新增R3逐项说明；验收输出均为R3最终实跑，验证限制明确保留。
