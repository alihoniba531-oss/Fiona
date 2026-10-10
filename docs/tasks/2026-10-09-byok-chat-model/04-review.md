# 独立复核记录（Fable，五维审查 + 每条问题双视角反驳核实）

输入：本目录 `02-spec.md`、`05-fix-r0.md`、完整改动补丁（含新文件全文）、主控真实端到端结果与 14 张截图（白天 1440×900、夜间 390×844）。复核员为全新上下文、只读；每条问题由「复现」「规格」两个视角各派一名核实员尝试推翻。工作流 `wf_4bfad80f-b74`，47 个代理。

## 结论

五个维度共 21 条。**必须修复 5 条**：S0（中文域名自定义地址保存后永远连不上）、B0（零余额 + 残留待补参数时自带模型聊天被卡死）、C0（测试连接向 Claude 等发空 system）、S1（自定义上游无响应字节上限，可被打爆内存）、C2（`ANTHROPIC_CUSTOM_HEADERS` 未列入违规环境变量）。另有 C1（预设厂商看门狗打断不了阻塞读，实际时限 = 总时长 + 60 秒）虽两票均判可优化，但会使规格允许的 240 秒配置撞上 Nginx 300 秒，一并在 R1 修。其余低成本改进一并修，3 条不处理。

## 各维度规格条目核验

- **security**：21 条，通过 18、部分通过 1、不通过 2；未全过：6.3.3 重定向不跟随（follow_redirects=False）；6.3.3 PinnedTransport 对 IDNA（Unicode）主机名的可用性：规格 6.9#4 把 Unic；（规格外）自定义上游响应体字节上限
- **billing-crisis**：14 条，通过 12、部分通过 2；未全过：余额不足 + 启用 BYOK 时只允许自带模型聊天（方案 C′），生图 / stream_pending 清理前 / 工；BYOK 轮次服务端可控结束路径枚举：成功、上游各类错误、超时、客户端断开、并发上限、每日上限、零余额、会话被删
- **client**：17 条，通过 14、部分通过 3；未全过：6.4.5 总时长 FIONA_BYOK_TOTAL_SECONDS（10–240，默认 120）从建流开始计时，超时关；取消（客户端断开）时上游连接关闭、槽位释放；6.6.5 测试连接最小请求：OpenAI 兼容 max_tokens=16、Claude max_tokens=102
- **frontend**：22 条，通过 20、部分通过 2；未全过：设置页与常驻抽屉 iframe 之间的跨 iframe 同步（storage 事件 + revision）；429 / 503 / 网络错误的中文提示
- **scope-tests-docs**：20 条，通过 19、部分通过 1；未全过：6.9 关键防线变异测试：零余额守卫、危机走平台、退款、不回退平台、SSRF 内网拒绝、DNS 重绑定、AAD 绑定、K

## 逐条结论

| 编号 | 问题 | 位置 | 原级别 | 核实（复现 / 规格） | 最终级别 | 处理 |
|---|---|---|---|---|---|---|
| S0 | PinnedTransport 用 httpx 解码后的 Unicode 主机名与 punycode 比较，合法 IDNA 自定义地址保存成功后永远「连不上该服务」 | `backend/byok/url_safety.py:230` | 必须修复 | CONFIRMED·必须修复 / CONFIRMED·必须修复 | 必须修复 | R1-1 |
| S1 | 自定义上游响应无字节上限：恶意公网上游可在总时限内把后端内存打爆（50 MiB 无换行 SSE → 214 MiB 峰值） | `backend/byok/url_safety.py:114` | 可优化 | CONFIRMED·必须修复 / CONFIRMED·可优化 | 必须修复 | R1-4 |
| S2 | client.py 构造 httpx.Client 的 follow_redirects=False / trust_env=False 没有测试锁定（变异 M20/M21 幸存） | `backend/byok/client.py:232` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-10 |
| S3 | 第三方库 INFO/DEBUG 日志会带出用户自定义 URL 与模型名，当前仅靠根 logger 默认 WARNING 压住 | `backend/byok/client.py:234` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | 不处理：生产根日志为 WARNING，改全局第三方日志级别会影响平台路径 |
| B0 | 零余额 BYOK 用户被残留的 pending 卡死：任何消息都返回「草莓不足」，自带模型一次不被调用 | `backend/services/chat_service.py:1443` | 必须修复 | CONFIRMED·必须修复 / CONFIRMED·必须修复 | 必须修复 | R1-2 |
| B1 | BYOK 回复落库失败（会话中途被删）被误归因为「你的模型调用失败：调用失败」 | `backend/services/chat_service.py:303` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-7 |
| B2 | 从未配置 BYOK 的用户在配置表瞬时读取失败时也收到「你的模型调用失败…本条没有改用平台模型」 | `backend/services/chat_service.py:221` | 可优化 | CONFIRMED·可优化 / REFUTED·无需处理 | 可优化 | 不处理：两票分歧，一票推翻 |
| C0 | 测试连接向 Claude 发送 system=""、向 DeepSeek/Kimi/智谱/自定义发送空内容的 system 消息 | `backend/byok/client.py:70` | 必须修复 | PLAUSIBLE·必须修复 / PLAUSIBLE·必须修复 | 必须修复 | R1-3 |
| C1 | 预设厂商与 Claude 的 120 秒看门狗不能打断阻塞的 socket 读，实际总时限为 TOTAL_SECONDS+60s（设 240 时等于 Nginx 300s） | `backend/byok/client.py:111` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化（实际影响上限） | R1-6 |
| C2 | ANTHROPIC_CUSTOM_HEADERS 不在 FORBIDDEN_ENV，会被 anthropic SDK 注入到用户的 Claude 请求头 | `backend/byok/crypto.py:16` | 可优化 | CONFIRMED·可优化 / CONFIRMED·必须修复 | 必须修复 | R1-5 |
| C3 | 账号名替换是无边界子串替换：常见词用户名会把系统提示中的普通词汇打成「（账号已隐藏）」，2 字符用户名则原样外发 | `backend/byok/client.py:53` | 可优化 | CONFIRMED·无需处理 / REFUTED·无需处理 | 无需处理 | 不处理 |
| C4 | 几类上游失败归入「调用失败」而非更贴切的类别：流中 error 事件（含 insufficient_quota）、流中连接中断、Anthropic 529 过载 | `backend/byok/errors.py:73` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-8 |
| F0 | 常驻设置抽屉 iframe 不监听版本号，底栏「改用平台/改用我的模型」后抽屉内开关与状态陈旧 | `frontend/components/ChatModelSection.tsx:243` | 必须修复 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-9 |
| F1 | 网络错误直接显示浏览器英文文案「Failed to fetch」（设置分区三处 + 底栏） | `frontend/components/ChatModelSection.tsx:14` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-9 |
| F2 | PUT/PATCH/DELETE 命中 10/分钟限流时只显示泛化「操作失败，请重试」，没有「稍后再试」语义 | `frontend/lib/chatModel.ts:87` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-9 |
| F3 | 删除配置后立即显示「有未保存的修改。」 | `frontend/components/ChatModelSection.tsx:40` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-9 |
| D0 | 变异存活：stream_generated_image 顶部的零余额守卫没有任何直接测试 | `backend/services/chat_service.py:788` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-10 |
| D1 | 变异存活：路由层 has_enabled_config 读取出错「按草莓不足原样返回」的分支无测试 | `backend/routers/chat.py:177` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-10 |
| D2 | DEPLOYMENT.md 对长期备份中 BYOK 密文的处置只给结论没给步骤，与「备份中最多保留 14 天」承诺存在张力 | `docs/DEPLOYMENT.md:409` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-11 |
| D3 | DEPLOYMENT.md 环境变量表「FIONA_DAILY_BYOK_TESTS … 失败也计次数」表述过宽 | `docs/DEPLOYMENT.md:135` | 可优化 | CONFIRMED·可优化 / CONFIRMED·可优化 | 可优化 | R1-11 |
| D4 | 鉴权失败时 /chat-model 路径改返 403 而非全站的 401，前端的会话失效跳转对该接口不再生效 | `backend/main.py:257` | 可优化 | CONFIRMED·可优化 / REFUTED·无需处理 | 可优化 | 不处理：规格明文「新接口不得返回 401」，一票推翻 |

## 复核员覆盖说明

- **security**：实际执行：(1) 通读规格 02-spec.md、修订 05-fix-r0.md、e2e-results.md，逐行审阅 backend/byok/{url_safety,crypto,store,client,errors,providers}.py、routers/chat_model.py，以及 database.py/main.py/rate_limit.py/routers/chat.py/services/chat_service.py 的 diff 与五个 test_byok_*.py 的全部内容。(2) 在 rsync 副本（排除 .venv/uploads/db/.env）上用 backend/.venv 的 Python 3.14.6 跑 5 个 byok 测试文件基线：247 passed。(3) 变异测试 30 项（mutate.py，结果 mutation_results.json）：24 项被现有测试杀死（is_global、只看首个 DNS 应答、NAT64、不固定 IP、不重解析、AAD 常量、不按 key_id 选钥、忽略 FORBIDDEN_ENV、_open 不检查可用性、错误文案拼 str(exc)、校验失败回显 body、公开字段含密文、删号不删配置、保存不查用户、失败回退平台、high 轮走 BYOK、未预扣不复查、禁用配置仍解密、放行 
- **billing-crisis**：实际做了什么：① 通读规格 02-spec、修订 05-fix-r0、e2e 结果，以及补丁中 database.py / main.py / rate_limit.py / routers/chat.py / services/chat_service.py 的 diff 与工作区全文；通读 backend/byok/{client,errors,store,providers}.py 与 tests/test_byok_chat.py、test_byok_client.py。② 把 backend/ rsync 到复核目录（排除 .venv/uploads/*.db*/.env*），用仓库 .venv 的 python、临时 FIONA_DB_PATH/FIONA_UPLOADS_DIR、现生成的 FIONA_BYOK_SECRET 与 JWT_SECRET、DASHSCOPE_API_KEY=placeholder、PYTHON_DOTENV_DISABLED=1、空 FIONA_ENV_FILE，并 unset ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN/OPENAI_BASE_URL 等；全部上游用桩，断网夹具在每个测试里断言未触网。③ 在副本跑 test_byok_chat.py + test_byok_client.py（106 项
- **client**：实际做了：(1) 通读规格 02-spec 第 2/3/4/6.4/6.5.3/6.6.5/6.9 节与修订 05-fix-r0，对照 backend/byok/client.py、providers.py、errors.py、crypto.py（环境变量部分）、url_safety.py（abort 部分）与 services/chat_service.py 的 BYOK 消费段逐条核验；(2) 在 .venv 中 inspect anthropic 1.12.1 的 messages.stream / beta.messages.stream 签名、BetaFallbacksParam、anthropic_beta_param 字面量、MessageStream/MessageStreamManager 方法、_client.py 的环境变量读取、_streaming.py 错误事件处理，以及 openai 2.37.0 的环境变量读取；(3) 把 backend 复制到 临时目录/client/backend（排除 .venv/uploads/db/.env），用隔离环境（临时 DB/uploads、随机 JWT_SECRET 与 FIONA_BYOK_SECRET、DASHSCOPE_API_KEY=placeholder、PYTHON_D
- **frontend**：实际做了：(1) 逐行审阅 frontend/components/ChatModelSection.tsx、lib/chatModel.ts、lib/useAccountIdentity.ts，以及 page.tsx / settings/page.tsx / ChatBubble.tsx / Sidebar.tsx 相对 a70e7d7 的 diff，并对照后端 routers/chat_model.py、byok/errors.py、rate_limit.py、main.py 的 429/403/no-store 行为核对前端解析。(2) 搭隔离栈：rsync 后端副本到 review/frontend/backend，用 launch_backend.py 以 .venv python 启动 8097（DEV_MODE=1、临时库/上传目录、现生成 JWT_SECRET 与 FIONA_BYOK_SECRET、空 env 文件、unset ANTHROPIC_*/OPENAI_*），并把 openai.OpenAI / anthropic.Anthropic 替换为本地桩（按 Key 前缀返回正常流/401/429/404/超时/连接失败/空回复/慢流），DNS 解析桩成公网 IP，socket.getaddrinfo 与 create_connection 对非回环一律 
- **scope-tests-docs**：实际执行：（a）机械核验全部在仓库只读完成——git status 白名单对照（含 05-fix-r0 追加项）、7.2 受保护文件 git diff --exit-code（exit 0）、7.3 两条 grep（无输出）、7.4 requirements 两行（diff 仅 +2）、backend/tests 76 个既有文件逐个对比 a70e7d7（零差异、无删除）、pip check 通过、全量 pytest 在 rsync 副本（排除 .venv/uploads/*.db*/.env*，环境变量按规则 3 设置并 unset ANTHROPIC_BASE_URL 等）运行三次：前两次各 1 失败均因副本缺 deploy/ 与 docs/ 引用文件，补齐后 2675 passed（=2428+247），沙箱外无端口失败；新增用例 collect-only 计 247，五个文件均有规格要求的断网夹具。（b）变异测试在另一独立副本 mut/backend 上跑 30 个变异 + 额外 1 个（脚本 mutate.py、日志 mutate.log，每次改坏后自动还原并核对），覆盖零余额守卫四处、危机走平台、退款、不回退平台两种、SSRF（DNS 应答/NAT64/字面 IP）、DNS 重绑定两种、AAD、Key 不进响应三处与日志、安全规则恰好一次两种、账号名隐藏、每日上限、Cl
