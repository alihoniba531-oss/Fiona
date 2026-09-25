# Fiona 当前架构

本文描述仓库在 2026-09-23 的实际代码结构。它是实现说明，不替代 [PLAN.md](../PLAN.md) 中的路线图和发布决策。

## 系统边界

```text
Browser / Tauri WebView
        │
        │ same-origin HTTP, SSE and WebSocket
        ▼
      Nginx
        ├── /              → Next.js :3000
        ├── /api/*         → FastAPI :8000（移除 /api 前缀）
        └── /uploads/*     → FastAPI :8000/uploads/*
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
                  SQLite       DashScope      外部网页/热点源
                fiona.db       Qwen 系列      搜索与卡片抓取
```

开发环境仍使用相同的相对 `/api` 地址，但由 `frontend/next.config.ts` 直接 rewrite 到本机 FastAPI。

## Web 前端

前端位于 `frontend/`，使用 Next.js 16 App Router 和 React 19。

| 路由 | 当前职责 |
|---|---|
| `/` | 自己的分身私有会话、图片、语音、工具卡片和抽屉容器 |
| `/agents/me` | 分身设置、名片预览、私有记忆查看与清空 |
| `/agents` | 公开分身广场、收发邀请、双分身交流记录与总结 |
| `/agents/[id]` | 登录后查看自己的或他人已公开的分身名片 |
| `/login` | 邀请码登录 |
| `/match` | 待接受匹配和匹配响应 |
| `/plaza` | 热点、发帖、媒体、点赞和兴趣信息 |
| `/community` | 社群兴趣展示 |
| `/profile` | 旧社交画像；新私有记忆在分身页管理 |
| `/history` | 对话历史、删除和导出 |
| `/settings` | 用户偏好和产品设置 |

重要共享模块：

- `frontend/lib/config.ts`：HTTP/WebSocket API 基址的唯一来源。
- `frontend/lib/auth.ts`：本地展示身份、Cookie 请求和统一 401 会话失效处理；不读取 JWT。
- `frontend/proxy.ts`：页面级 Cookie 门禁。
- `frontend/components/`：聊天、导航、HUD 和 3D 场景。
- `frontend/lib/useConversations.ts`：会话请求、当前选择持久化、历史加载与迟到响应隔离；选择器位于 `components/ConversationPicker.tsx`。

主页面目前会保留多个抽屉 iframe 的挂载状态。这是当前行为，不是推荐的长期架构；拆分和懒加载计划记录在 [PLAN.md](../PLAN.md)。

## FastAPI 后端

后端入口是 `backend/main.py`，启动包装是 `backend/run.py`。业务路由按领域拆分：

| 模块 | 主要端点/职责 |
|---|---|
| `routers/auth.py` | 邀请码、开发登录、预留 OTP |
| `routers/chat.py` | `/chat` SSE 对话入口 |
| `routers/voice.py` | ASR、TTS、TTS WebSocket |
| `routers/hot.py` | 热点源、分类和详情展开 |
| `routers/match.py` | 匹配生成、待接受卡片和响应 |
| `routers/peer.py` | 真人房间、历史和 WebSocket |
| `routers/plaza.py` | 广场、媒体、点赞和兴趣偏好 |
| `routers/me.py` | 设置、画像、历史、用量和草莓余额 |
| `routers/agents.py` | 自己的分身、公开名片列表/详情、私有记忆 |
| `routers/conversations.py` | 本人会话列表、新建、消息与删除 |
| `routers/agent_exchanges.py` | 分身交流邀请、列表/详情、接受、拒绝与停止 |

聊天主流程位于 `backend/services/chat_service.py`：

1. 验证用户与请求参数；生产环境对普通聊天原子预扣 10 颗草莓，余额不足时返回 SSE 错误。
2. 将可选 `conversation_id` 解析为本人会话；旧客户端省略时使用默认私有会话，非法归属返回 404。
3. 保存用户消息和可接受的图片，读取该会话近期消息、独立分身私有记忆、人格和按会话隔离的模式。
4. 根据图片、对话模式和意图选择模型或工具。
5. 通过 SSE 返回模型输出。
6. 将回复写回固定会话 ID，并在后台更新分身私有记忆；没有实际交付的预扣会退还。新私有会话不再触发旧 Layer 1/Layer 2 匹配或广场标签传播。

所有实际聊天都携带解析后的会话 ID。模式识别、意图识别完成后及工具执行前复核会话存活；会话删除后迟到回复不能重建记录或触发新的扣费。已经启动的外部工具无法通过删除会话撤回。

草莓以单条条件更新原子预扣，模型回复保存、图片实际生成并保存或真实工具成功执行才结算；失败、缺参追问、占位工具、未知意图、异常和未交付就断开的流会退款。`DEV_MODE=1` 跳过预扣与结算。`STRAWBERRY_DAILY_REFILL` 默认 `0`（关闭）；开启后，用户在 Asia/Shanghai 自然日首次经登录、`/strawberry` 或预扣时，余额只提升到设定下限，同日不重复补给，日期保存在 `users.strawberry_refill_date`。管理员的 `manage_strawberries.py list` 只读原始余额和日期，不触发补给。

私聊检测到自伤或自杀表达时，本轮绕开镜子模式、工具及待补参数，使用普通或看图回复；危机指导放在 system prompt 最后，服务端固定追加求助资源且本轮不计费。生产环境余额不足时直接返回资源文案、不调用模型；`DEV_MODE=1` 跳过余额拦截。非危机轮的所有 system 消息合计只放一份基础安全规则，位于最后一条 system 消息末尾；朗读强约束仍作为当前 user 消息后的独立 system 消息。

图片生成通过同一个 `POST /chat` 接入：`mode=image` 显式请求，`aspect_ratio` 可选 `1:1/16:9/9:16`；明确自然语言绘图请求也会触发。该分支优先于陪聊模式和旧工具补参，缺画面描述时追问，能力咨询与取消不触发生成。`tools/image_generation.py` 只向固定 DashScope native 多模态接口发送本轮画面描述，不发送私有记忆；每账号同时最多一张，单次 150 秒且不自动重试。SSE 先发 `status=generating_image`，等待期间发送注释心跳，成功落库后才发 `generated_image`、`text`、`done`；失败只发错误，不保存成功消息、不扣草莓。生成文件沿用 `messages.image_path`，限定为经过验证的本地 PNG，供应商临时链接不交给浏览器。新 `generated_*` 文件在开发和生产均验证消息归属，使用 `private, no-store`；删除与断开时清理未保存附件，落库期间保护事务结果确认。

参考图编辑使用 `mode=image_edit`、有序的 `reference_images` 数组（1–3 项）和非空修改指令。每项只允许 `image_path` 或 `image_base64` 之一，可以混合已保存图片与本地上传图。路径只接受 `/uploads/generated_<32位hex>.png` 或 `/uploads/reference_<32位hex>.png`，且已有路径必须由当前用户、当前会话的消息引用。旧 `reference_image_paths` 数组和 `reference_image_path` 单图继续兼容，三种引用格式不能同时提交；不接受同时携带普通看图聊天的 `image_base64`，普通聊天或文生图模式不可携带引用字段。

上传图片由 `utils/reference_images.py` 在线程中校验 PNG/JPEG/WebP 实际内容（原图 ≤5MB、≤4000万像素、比例 ≤4:1），纠正 EXIF 方向、去除元数据，再等比例规范为 PNG（至少 512² 像素、最多400万像素、长边 ≤2048、≤10MB）。只有本轮生成的新路径能通过服务内部参数随用户消息首次登记，客户端不能指定新图所有权。全部已有引用的归属核验和保存用户消息共用写事务；准备文件与事务在取消保护内完成，失败清理新图、提交成功保留。`messages.reference_image_paths` 存有序 JSON，`image_path` 保留首张以兼容旧客户端，历史接口解码为数组。新版请求在生图前先发 `type=reference_images` SSE 事件确认已保存路径，前端据此更新预览和失败重试，避免重复上传。前端代理和后端请求体上限均为25MB，可容纳三张5MB原图的Base64请求。所有 `generated_`、`reference_` 文件在开发与生产环境均验证消息归属；媒体权限和删除清理同时检查单图列与完整引用数组，防止删除原始消息后误删仍作为图2/图3使用的图片。

`edit_image` 逐张校验本地路径、PNG 内容及 10MB 大小上限，按顺序将 1–3 张图的 Base64 数据和本轮指令传入模型；不传聊天历史或记忆。图号对应数组顺序，默认沿用图1的尺寸，`aspect_ratio` 可覆盖。SSE 为 `status=editing_image`，成功事件含 `reference_image_paths` 及兼容字段 `reference_image_path`（首张），每次仍返回一张新图。页面通过“以此图修改”“加入参考”显式选图，支持移除和调整图序；提交或切换会话后清空当前引用，失败重试保留整组图、顺序和会话身份。

分身之间的交流由 `exchange_store.py` 与 `services/exchange_service.py` 独立处理，不经过私聊工具路由或记忆提取。双方公开名片并由受邀者接受后，数据库原子生成运行令牌，后台任务依次生成双方合计 2–6 条回复及一次总结。每次调用前预留预算、核验授权和剩余轮次；返回后复核同一令牌、当前状态及发言序号，阻止并发重复执行或撤销后的迟到保存。真人和官方体验的每一种交流 system 消息（包括总结、主创、审稿与修订）末尾均附基础安全规则。

真人分身间的模型输入只有白名单公开名片（名称、简介、头像符号）、主题和本次交流记录；每次输入最多 16,000 UTF-8 字节，回复最多 256 output tokens，总结最多 128。整个交流预留与实际用量不能超过 80,000 tokens，最多 7 次模型调用，禁用重试、回退与工具。缺失实际用量时使用保守估算；停止不保证撤回已到供应商的请求，但会禁止新轮次和在途回复发布。每账号最多 3 个待处理/运行交流、同时最多运行 1 个，同一对分身最多一个活动邀请。

新增交流表由 `20260905_agent_exchanges_v1` 事务迁移建立。启动时将遗留运行任务置为停止并结算未决预留，不重放模型请求；此恢复仅支持当前单进程部署。关闭名片在同一事务停止相关活动交流；删除账号连同双方共享的交流、回复与调用记录一起删除。

单人官方体验通过 `official_agents.py` 提供固定的“创意搭档”“脚本编辑”和“短视频创意搭档”目录，不创建用户或 `agents` 行。`GET /agent-exchanges/official-agents` 返回官方卡片；`POST /agent-exchanges/official` 校验固定目录 ID 与请求者分身后直接进入运行状态，复用有限轮数、预算预留、停止和总结流程。官方角色在提示词中明确为平台 AI，没有第二位真人主人。

`official:short-video-creator` 的创作流程与总结格式来自服务端 `get_official_exchange_instruction`：围绕钩子、冲突、反转逐步完善剧本，最后按时码输出分镜、画面、台词和音效。只有 official 类型与固定角色 ID 同时匹配才加入可信系统提示，不根据用户可编辑的名称或简介选择流程；这段指令不出现在公开目录。所有官方角色共用可配置的官方模型槽，新增角色无需新增用户、迁移数据或填写密钥。

官方话题上限由 `OFFICIAL_TOPIC_MAX_LENGTH=10_000` 控制，API 和前端同时校验，入库后完整送入双方及总结的 JSON 上下文，不再截取前 300 字。长历史仍按每条节选压缩以满足 128,000 字节预算，话题本身完整保留。真人邀请主题继续限制为 300 字。前端提供大输入框与计数器，详情中的长话题可展开并在有限高度内滚动。

`GET /agent-exchanges/{id}/export?document=readme|discussion|artifact` 通过同一交流权限检查读取一致快照，由 `exchange_exports.py` 输出 UTF-8 Markdown 附件。README 包含原始需求、参与分身和已有总结，discussion 额外包含全部逐轮回复；运行中或缺少总结时明确标为草稿。导出不调用模型、不写数据库或服务端文件，兼容既有记录。响应禁止缓存，文件名过滤为安全字符；用户话题和逐条回复使用动态长度代码围栏保留全文，总结保留 Markdown 并转义 HTML。前端下载使用独立可取消请求及账号校验，下载后释放 Blob URL。

`20260905_official_agent_exchanges_v2` 事务重建交流主表，保留原有 ID、记录和索引，增加 `kind`（旧数据默认 `peer`），让官方体验的 `recipient_username` 为 NULL。数据库约束保证 peer 有接收账号、official 没有接收账号。官方体验只授权发起者，额度按发起者计算，不对共享官方角色设置用户额度；创建和读取都不要求自己的名片公开，也不改变公开状态。仅把本人基础名片快照与当前讨论送入模型，体验不会被其他使用同一官方角色的账号读取。

## 主创与审稿协作

V4 事务迁移为交流增加 `workflow_version/artifact/artifact_status/completion_reason`，为消息增加 `stage/review_json`。旧记录字段默认空，保留旧流程与下载结果；新官方交流采用 `draft_review_v1`。个人分身通过 main 槽提交完整初稿与修订稿，官方模型通过 official 槽独立审稿。新流程的最多 99 次为调用上限，批准后原子保留已经审过的正文并完成，不额外调用摘要模型改写成品。

`exchange_workflow.py` 下发固定阶段、原始需求、最新完整稿和最近审稿意见；旧版本只提供节选，全部原文仍保存在记录中。原始需求、最新完整稿及最近审稿不作静默截断，核心输入超过 128,000 UTF-8 字节时明确停止并保留稿件。主创输出上限 8,192 tokens，审稿 4,096；存储边界为 48,000 字符，取消新流程的 1,200 字截断；总体保守预算仍为 14,000,000 tokens。

审稿使用结构化检查，涵盖交付物、用户约束、一致性、可用性、外部事实与执行声明五类。批准须五类检查齐全、每项满足、证据能通过真实行号或原文定位于当前稿、没有未解决问题；分行摘录和 Markdown 空白差异不会丢掉批评意见。不足的引用转为待核实，保留具体问题。对可明确解析的分镜镜数、时间要求，另从实际表行核对数量、连续性和总时长，不直接相信稿件自称的数字；非精确约束交由审稿处理。该机制仍属 AI 审稿，界面明确“待用户验收”，不等同于真实媒体生成或人工质量保证。

主创只换版本号/修订日志而正文相同，或连续三次相同问题没有解决时，停止重复修订；达到上限或供应商异常结束时保留待修订稿。所有发布仍在原令牌、授权、序号与预算事务内完成，停止/删号/重启后的迟到批准不能落库。列表仅返回 `has_artifact`，省略完整作品以降低轮询负载；详情与导出通过相同账号权限读取完整正文。

新流程的 README 包含完整作品、原始需求和审核状态，`artifact` 仅导出当前作品及其状态，`discussion` 保存全部版本和审稿。作品尚未生成时 `artifact` 返回 404；旧记录不会被伪装成已审稿的新作品。

## 模型和工具

官方单人体验旧版流程默认 99 次回复，支持 2–99 次，最后加一次总结；`20260905_official_exchange_limits_v3` 事务迁移放宽 official 的轮次约束，peer 仍限制为 6 次，并给调用账本增加 `provider/model`。历史调用留空，不推断旧模型；新官方名片保存创建时的模型信息。每次官方体验输入最多 128,000 UTF-8 字节，回复最多 512 output tokens，总结最多 1,024，整个体验最多 100 次调用和 14,000,000 tokens 保守预算。上下文保留所有轮次；超长记录才按每条节选压缩，包含最新回复和最后结论，不再截取开头六条。

`exchange_models.py` 独立选择官方模型：`OFFICIAL_EXCHANGE_PROVIDER` 默认 dashscope，可设为 deepseek；`OFFICIAL_EXCHANGE_MODEL` 指定模型，DeepSeek 默认 deepseek-v4-pro。`DEEPSEEK_API_KEY` 仅在服务端读取，客户端只连接固定的 https://api.deepseek.com。自己的分身发言继续使用 DashScope 主模型，官方搭档发言及总结使用官方模型槽。DeepSeek 通过 `thinking.type=disabled` 关闭默认思考模式，避免短回复预算被推理消耗；不使用 DashScope 特有的 enable_thinking 参数。生成禁用重试和跨供应商回退，逐次记录实际供应商、模型及用量。

当前模型配置以 `backend/llm.py` 和各适配器源码为准：

- `deepseek-v4-pro`：本地已配置的官方搭档发言及单人体验总结；由 `exchange_models.py` 独立配置。
- `qwen3.8-omni-flash`：主力对话、匹配和复杂判断。
- `qwen3.8-flash`：轻量对话槽位，失败时回退主力模型。
- `qwen-vl-max`：用户图片和视觉搜索结果理解。
- `qwen-image-3.0`：聊天文生图及参考图编辑，默认每次一张；`QWEN_IMAGE_MODEL` 可调整。
- `qwen-plus`：联网搜索、热点分类/展开和旅行规划。
- `qwen3-asr-flash`：语音识别。
- DashScope TTS：语音合成。

工具分派位于 `backend/services/chat_service.py:execute_intent`，意图识别位于 `backend/intent_router.py`；`backend/tools/route.py` 仅实现驾车路线。当前内置函数还不是可发布、安装或交易的 Skill。系统/微信辅助模块中的部分功能是占位实现，不能视为可用的服务端 Skill。

## 鉴权与公开端点

HTTP 默认经过 `backend/main.py` 的鉴权中间件，身份来源优先级为：

1. `Authorization: Bearer <jwt>`
2. `fiona_token` Cookie
3. `DEV_MODE=1` 时的 `X-Dev-User`/`dev_user`

当前公开范围包括根健康响应、认证入口、`/hot/*` 中的只读榜单，以及 Plaza 的标签、Feed 和社群兴趣三个只读端点。`/hot/expand` 会触发联网模型调用，中间件和路由依赖都要求登录。API 文档（`/docs`、`/redoc`、`/openapi.json`）只在 `DEV_MODE=1` 时开放，生产环境返回 404。WebSocket 不经过 HTTP 中间件，由具体端点单独认证。

生产 JWT 使用 HS256，默认有效期 30 天，浏览器端只存于 `HttpOnly`、`SameSite=Lax` Cookie。JWT 带账号会话版本，每次 HTTP 请求和 WebSocket 握手都会与数据库核对；退出登录、撤销或轮换邀请码会使旧会话立即失效。邀请码仍绑定用户名并允许重复登录，但兑换会原子记录用量。`backend/seed_invites.py` 在单个写事务中按用户表和邀请码表的最大 `testerNN` 编号分配新用户名，避免删号后与存量账号撞名；`backend/manage_invites.py` 可查看、撤销和轮换。管理脚本先加载服务环境配置，并拒绝在未明确 `--init-db` 时创建不存在的数据库。

## 数据与文件

当前持久化完全位于单机。开发环境的默认路径为：

- SQLite：`backend/fiona.db`
- 媒体：`backend/uploads/`
- 环境变量：`backend/.env`
- 桌面开发连接：`desktop/fiona.config.json`

生产部署通过 `FIONA_DB_PATH` 和 `FIONA_UPLOADS_DIR` 将前两项放到
`/var/lib/fiona/fiona.db` 和 `/var/lib/fiona/uploads/`；API Key/JWT Secret 位于
权限为 `0600` 的 `/etc/fiona/fiona.env`，不写入只读代码目录。

SQLite 表由 `backend/database.py:init_db()` 在启动时创建。历史字段仍使用旧的容错式 `ALTER TABLE`，其中包括新增可空列 `users.strawberry_refill_date`；新增分身与会话由 `backend/agent_store.py:migrate_avatar_schema()` 执行版本化事务迁移，版本记入 `schema_migrations`。当前没有通用迁移框架或 PostgreSQL 实现。

`agents` 对每个 owner 设置唯一约束，保存可编辑身份，以及不经名片 API 输出的 `private_memory_json/memory_revision`。初次创建时复制本人旧画像作为私有基线，之后与 `users.profile_json` 分开；旧社会画像仍用于原有显式匹配流程。公开名片只经字段白名单返回，不返回用户名、人格设定或私有记忆。

`conversations` 为本人私有会话，包含分身 ID、名称和默认会话标识；`messages` 新增 `conversation_id/agent_id`，迁移在同一事务中回填旧消息。默认会话删除后可创建新的默认会话，但旧 ID 永不复用。读取、写入和删除都在数据库操作中复核账号及会话归属。新会话首条消息可自动命名，显式设置的标题保持不变。

画像提取使用会话内消息和私有记忆修订号，通过条件写入避免清空记忆、删除会话或账号后的迟到回填。清空记忆同时清理私有副本与旧社会画像，保留原始聊天记录；未来交流可以形成新的记忆。待补全工具参数和模式以 `(username, conversation_id)` 在进程内隔离，重启后仍会重置。

主要数据域包括：用户和画像、消息、匹配、待接受卡片、真人消息、帖子/点赞、标签与时间偏好、用户成长状态、事件、OTP、邀请码和上传清理队列。

`fiona.db` 与 `uploads/` 必须作为一个隐私数据集合共同备份和清理。删除单条消息、清空历史或删除账户时，数据库会在同一事务中找出不再被消息/帖子引用的媒体并写入 `upload_cleanup_queue`；文件会立即清理，失败项在后端启动时和运行期间周期重试。新帖子在库内保存 owner；能通过当前 HMAC 或旧 MD5 匿名标识识别的历史帖子会自动回填，无法识别的旧行仍需人工处置。

## 匹配和真人连接

保留的旧匹配实现包含以下两条路径；M1 私有聊天不会启动它们，现有显式匹配与真人接受流程继续保留。这些代码不代表分身之间自动交流已经实现。

- Layer 1：从近期消息和显式需求中寻找更即时的连接。
- Layer 2：基于持续画像寻找候选。

候选会经过模型评估，再写入待接受卡片和匹配记录。同一用户对的近期匹配与同层待接受卡片在数据库事务中去重；不存在的匹配不能通过响应接口被隐式创建。双方都接受后才能读取/写入真人房间；Peer WebSocket 会逐条复核会话和双方最新同意状态，并限制消息大小与发送速率。

Layer 2 会为双方创建待接受卡片；Layer 1、Layer 2 和手动匹配都会验证双方连接偏好。手动匹配还会把模型输出限制在候选集合内，并校验类型、理由和标签。跨用户模型输入只包含长度受限的兴趣、价值观、技能、阶段和城市，不读取候选的原始近期消息，并排除需求、困扰、纪念日和职业等字段。当前仍是应用层最小化，不等同于数据库租户隔离或独立隐私审计。

## 桌面客户端

`desktop/` 是 Tauri 2 壳，不内置完整 Web 前端：

- 找到 `fiona.config.json`：建立 SSH 本地端口转发，加载 `http://localhost:<port>`。
- 没有配置文件：加载 `https://madchloechat.online`。线上服务已于 2026-09-25 下线，这个模式目前打不开任何页面。

本地隧道页面只拥有诊断、后端探测和日志相关 capability；远程页面只拥有两个受 Rust 层 HTTP(S) 校验保护的外链命令。Windows 外链不经过 `cmd.exe`，Tauri 启动页和远程 Next.js 页面均已配置 CSP。公开分发前仍需完成 [PLAN.md](../PLAN.md) 中的 Windows/Rust 构建复核、签名和发布验证。

## 运行和扩展限制

- SQLite 每次操作创建连接，尚未配置完整的并发和正式迁移策略。
- 模型预算计数是单进程内存状态，不是供应商账单或集群级配额；草莓预扣、退款和每日补给已原子化，真实 usage 与持久化成本控制仍待完成。
- 消息/账户删除已有引用检查和持久化文件清理周期重试；全目录孤儿扫描与保留期限尚未完成。
- ASGI 层限制总请求体为 25 MB，Chat/图片、ASR、TTS、帖子和分页还有更严格的领域边界；图片会验证真实格式、完整性和像素量。模型客户端已有明确超时和有限重试；并发边界、公共热点缓存和持久化成本上限仍需继续治理。
- 模型生成的热点/卡片 URL 通过只允许公网 HTTP(S) 的客户端访问，每次 DNS 和重定向都会重新校验并限制响应体与超时。
- 前端主页面承担职责过多，多个隐藏 iframe 会继续运行轮询或 3D 场景。
- 仓库已增加后端与 Web 质量门禁工作流；Windows 桌面工作流会运行 Rust 单测再打包。新工作流仍需在 GitHub 首次运行中确认 runner 环境。

当上述实现发生变化时，应在同一个变更中更新本文、根 README 和 PLAN 的状态。
