# Fiona 当前架构

本文描述仓库在 2026-10-09 的实际代码结构。它是实现说明，不替代 [PLAN.md](../PLAN.md) 中的路线图和发布决策。

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

开发环境仍使用相同的相对 `/api` 地址，但由 `frontend/next.config.ts` 直接 rewrite 到本机 FastAPI。`npm run dev` 默认只监听回环地址，额外开发来源需显式设置 `FIONA_ALLOWED_DEV_ORIGINS`。

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
| `/settings` | 用户偏好、每用户自带聊天模型与产品设置 |

重要共享模块：

- `frontend/lib/chatModel.ts` 与 `components/ChatModelSection.tsx`：严格校验设置 API JSON，Key 只保留表单内存、从不回填；厂商配置不进入 localStorage，只有 `fiona_chat_model_rev` 版本号用于 iframe 同步。登录、设置抽屉关闭及 storage 事件重新取配置，SSE `reply_model` 仅在当前气泡标注、刷新后消失。
- `frontend/lib/config.ts`：HTTP/WebSocket API 基址的唯一来源。
- `frontend/lib/auth.ts`：本地展示身份、Cookie 请求和统一 401 会话失效处理；不读取 JWT。
- `frontend/proxy.ts`：页面级 Cookie 门禁。
- `frontend/components/`：聊天、导航、HUD 和 3D 场景。
- `frontend/lib/useConversations.ts`：会话请求、当前选择持久化、历史加载与迟到响应隔离；选择器位于 `components/ConversationPicker.tsx`。
- `frontend/components/ChatBubble.tsx`：通用卡片在要点下方显示最多 5 条来源，包含标题和站点；来源先经 `frontend/lib/open.ts:toSafeExternalUrl` 校验绝对、无凭据、长度受限的 HTTP(S) URL，再通过 `openExternal` 打开。搜索失败气泡显示错误说明。

工具卡片（含搜索和旅行来源、天气预报）只随本轮 SSE 交付，不保存卡片结构到数据库。搜索与旅行的历史仅保存去掉引用角标的文字摘要，刷新或切换会话后来源不保留；天气仅保存中文文字摘要，这是当前已知限制。天气卡最多四天，显示白天/夜间天况、最高最低温和风向风力；标签按北京时间显示今天、明天或星期，没有实时温度、体感温度或湿度。

主页面目前会保留多个抽屉 iframe 的挂载状态。这是当前行为，不是推荐的长期架构；拆分和懒加载计划记录在 [PLAN.md](../PLAN.md)。

## FastAPI 后端

后端入口是 `backend/main.py`，启动包装是 `backend/run.py`。业务路由按领域拆分：

| 模块 | 主要端点/职责 |
|---|---|
| `routers/auth.py` | 邀请码、开发登录、预留 OTP |
| `routers/chat.py` | `/chat` SSE 对话入口 |
| `routers/chat_model.py` | 登录后的 `/chat-model` 配置 GET/PUT/PATCH/DELETE 与 `/chat-model/test`，响应 private, no-store；修改和测试 10/minute |
| `routers/voice.py` | ASR、TTS HTTP/流式朗读；ASR 叠加按账号每日上限。朗读文本经鉴权 POST 换短时、限次票据，票据有效期为 150 秒；每个用户最多保留 64 张未过期票据，超出先淘汰自己最早的。换票限流有按用户的 120 次/分钟、2000 字/分钟和按 IP 的 240 次/分钟、6000 字/分钟四道闸，429 响应带 `Retry-After`。WebKit 在换票时后台预热非流式合成，后续 Range 请求等待或读取同一份音频。无 Range 请求返回流式 200；首次 `Range: bytes=0-` 且无缓存或预热任务时也流式返回 200，以保留 Chromium/WebView2 的首音速度。闭区间 Range 合成后缓存并返回有限长度的 206；已有缓存的票据对 Range 请求读缓存返回 206 |
| `routers/hot.py` | 热点源、分类和详情展开 |
| `routers/match.py` | 匹配生成、待接受卡片和响应 |
| `routers/peer.py` | 真人房间、历史和 WebSocket |
| `routers/plaza.py` | 广场、媒体、点赞和兴趣偏好 |
| `routers/me.py` | 设置、画像、历史、用量和草莓余额 |
| `routers/agents.py` | 自己的分身、公开名片列表/详情、私有记忆 |
| `routers/conversations.py` | 本人会话列表、新建、消息与删除 |
| `routers/agent_exchanges.py` | 分身交流邀请、列表/详情、接受、拒绝与停止 |

聊天主流程位于 `backend/services/chat_service.py`：

1. 先判规则危机档位，非 `high` 的非空文字消息立即启动异步模型复核；验证参数、预扣并装配上下文，首次需要档位时等待复核并取较高档位。有余额时原子预扣 10 颗草莓；不足且 `mode=chat`、启用 BYOK 时以显式“未预扣”标记继续，只允许用户模型聊天。余额不足的 `high` 轮直接返回危机标记、资源、done，不调用模型、不落库；其他没有 BYOK 的 `possible` 轮先资源再余额错误。
2. 将可选 `conversation_id` 解析为本人会话；旧客户端省略时使用默认私有会话，非法归属返回 404。
3. 保存用户消息和可接受的图片，读取该会话近期消息、独立分身私有记忆、人格和按会话隔离的模式。
4. 根据图片、对话模式和意图选择模型或工具。
5. 通过 SSE 返回模型输出。
6. 将回复写回固定会话 ID，并由平台在后台更新私有记忆（包括读取 BYOK 回复）；BYOK 聊天回复不计费、退还预扣，没有实际交付也退款。新私有会话不触发旧 Layer 1/Layer 2 匹配或广场标签传播。

所有实际聊天都携带解析后的会话 ID。模式识别、意图识别完成后及工具执行前复核会话存活；会话删除后迟到回复不能重建记录或触发新的扣费。已经启动的外部工具无法通过删除会话撤回。

草莓以单条条件更新原子预扣，仅平台模型回复保存、图片实际生成并保存或真实工具成功执行结算 10 颗；BYOK 普通/镜子回复不设置 billable、退还预扣，失败同样退款。零余额守卫在真正执行工具（天气每日检查之前）、补全参数后的执行分支清理 pending、生图忙锁和看图调用之前返回共享草莓不足文案，不调用这些服务、不消耗天气额度、不清 pending；缺参追问仍走已有免费追问路径；零余额 BYOK 的免费取消与转聊天出口按下文的明确规则清 pending；识别新工具但未预扣时保留原 pending。回复阶段若 BYOK 配置被删、关闭或需重填，也报草莓不足。`DEV_MODE=1` 跳过预扣与结算，显式未预扣标记为 false，守卫为空操作。`STRAWBERRY_DAILY_REFILL` 默认 `0`（关闭）；开启后，用户在 Asia/Shanghai 自然日首次经登录、`/strawberry` 或预扣时，余额只提升到设定下限，同日不重复，日期保存在 `users.strawberry_refill_date`。管理员 `manage_strawberries.py list` 只读原始余额和日期，不触发补给。

私聊危机采用规则加模型复核：规则 `high` 直接进入支持流程；其他非空文字消息由 `qwen3.8-flash` 复核，只看当前消息；超过 2000 字取首尾各 1000 字，中间用“……”连接。取较高档位，不能降档。复核与预扣、上下文装配并行，默认 2 秒超时，失败按规则结果走；只记录档位、异常类型和耗时，不记录原文。复核模块 `backend/crisis_model.py` 在首次有效调用时创建独立 `AsyncOpenAI` 客户端，使用轻量槽模型、关闭思考、JSON 输出、temperature=0、最多 32 tokens、无重试。请求结束时取消并回收未完成任务。`build_context` 通过可选 `crisis_resolver` 在提示词首次需要档位时等待最终结果，升档后省略硬词附录，高危时省略朗读尾部 system，保证危机指引与规则直接命中高危时一致。信息或求助语境仍仅由规则判断，模型从未命中升到 `possible` 按非信息语境处理。私聊危机识别分为 `high`、`possible` 与未命中，规则匹配前仅对分类文本做繁转简，原文继续用于模型复核、存储、回复模型输入和显示。繁体『計畫』与『計劃』判级一致。明确的第一人称危机（`high`）绕开镜子模式、工具及待补参数，不清除待补状态；危机指导放在 system prompt 最后，服务端固定追加求助资源并保存于回复。余额充足时像普通轮次一样预扣、交付结算、未交付退款；余额不足时不调用回复模型，直接返回资源文案。`DEV_MODE=1` 跳过计费。`mode=image` 或 `image_edit` 的明确危机也走文字支持并向前端发送危机标记，不调用生图或修图。`possible` 保留模式判定、镜子、看图、普通回复和计费；除命中 `safety.py` 信息或求助语境规则的轮次外，跳过自然语言生图候选、意图识别、工具及待补参数，保留 pending。信息或求助语境、显式 `mode=image` / `image_edit`、缺少修图参考的固定引导保持原路由；唯一例外是已有天气 pending 时，到达工具路由的 `possible` 信息或求助语句清除该 pending，按新消息路由，不能当作城市名发给高德。正常文字、工具结果、图片及服务端可控制的错误收尾均恰好送达一次求助资源，余额不足时先送资源再提示余额，不发危机标记。FastAPI 在进入 `/chat` 路由前返回的 422 请求校验错误和 429 限流属于例外，无法由该路由附资源。未命中危机信号的轮次，所有 system 消息合计只放一份基础安全规则，位于最后一条 system 消息末尾；朗读强约束在平台模型与 BYOK dashscope 预设中作为当前 user 消息后的独立 system 消息；其他 BYOK 厂商合并全部 system（Claude 使用顶层 system），安全规则仍恰好一次且在末尾。

图片生成通过同一个 `POST /chat` 接入：`mode=image` 显式请求，`aspect_ratio` 可选 `1:1/16:9/9:16`；自然语言绘图候选先由正则提名，再由现有意图模型确认，确认生图才执行且复用本轮识别结果。候选句若被模型否决，本轮识别结果会复用于后续路由，与普通消息相比不增加意图模型调用；只有确认生图的候选句，在生图开始前需要等待一次意图模型识别（最多 150 tokens），因此增加该次请求的延迟和调用成本。候选确认与普通意图路径都对模型返回的 `generate_image` 再做讨论句兜底，避免能力咨询、教程与否定句触发生图；意图提示词还要求把价格、扣费、耗时、难度、生成结果评价、回忆、愿望及口语反问等谈论生图本身的句子归为空意图。意图分类仍依赖模型，不能保证所有非命令句都零误判；模型返回其他意图、空意图或失败时继续普通流程。确认生图的分支优先于镜子模式和旧工具补参；正则判断画面主体为空或模型标记缺少 `prompt` 时先追问，不执行生图且不扣费；自然语言生图的画面描述始终使用用户本轮完整原话 `ctx.message.strip()`，分类器返回的短 `prompt` 不用于替换或截短原文。比例优先从原文推断，原文没有比例时可采用模型返回的合法比例。`image_model` 在 chat、image、image_edit 三种请求模式中均接受服务端白名单 id，经 `ChatContext` 透传到统一生图路径（含意图确认和待补参数）。由全局鉴权中间件和 `Depends(get_current_user)` 共同保护的 `GET /image-models` 仅返回默认 id、显示名和对应密钥是否配置；前端仅在用户点击时保存模型偏好，暂时不可用只回落界面选择，之后获取到可用列表时恢复偏好；重试沿用原描述、比例与参考图，并使用当前界面选中的模型。`tools/image_generation.py` 默认使用 Qwen Image 3.0 的固定 DashScope native 多模态接口，也可选 Seedream 5.0 Flash 的固定火山方舟图片接口；只发送本轮描述和修图参考图，不发送私有记忆。选择 Seedream 时这些数据发送给字节跳动火山引擎，选择 Qwen 时发送给阿里云 DashScope；两个模型每次均按现有 10 颗草莓结算，失败退款且不跨供应商回退；每账号同时最多一张，单次 150 秒且不自动重试。SSE 先发 `status=generating_image`，等待期间发送注释心跳，成功落库后才发 `generated_image`、`text`、`done`；普通失败发错误，`possible` 危机轮先发求助资源再发错误；失败不保存成功消息、不扣草莓。生成文件沿用 `messages.image_path`，限定为经过验证的本地 PNG，供应商临时链接不交给浏览器。新 `generated_*` 文件在开发和生产均验证消息归属，使用 `private, no-store`；删除与断开时清理未保存附件，落库期间保护事务结果确认。

参考图编辑使用 `mode=image_edit`、有序的 `reference_images` 数组（1–3 项）和非空修改指令。每项只允许 `image_path` 或 `image_base64` 之一，可以混合已保存图片与本地上传图。路径只接受 `/uploads/generated_<32位hex>.png` 或 `/uploads/reference_<32位hex>.png`，且已有路径必须由当前用户、当前会话的消息引用。旧 `reference_image_paths` 数组和 `reference_image_path` 单图继续兼容，三种引用格式不能同时提交；不接受同时携带普通看图聊天的 `image_base64`，普通聊天或文生图模式不可携带引用字段。

上传图片由 `utils/reference_images.py` 在线程中校验 PNG/JPEG/WebP 实际内容（原图 ≤5MB、≤4000万像素、比例 ≤4:1），纠正 EXIF 方向、去除元数据，再等比例规范为 PNG（至少 512² 像素、最多400万像素、长边 ≤2048、≤10MB）。只有本轮生成的新路径能通过服务内部参数随用户消息首次登记，客户端不能指定新图所有权。全部已有引用的归属核验和保存用户消息共用写事务；准备文件与事务在取消保护内完成，失败清理新图、提交成功保留。`messages.reference_image_paths` 存有序 JSON，`image_path` 保留首张以兼容旧客户端，历史接口解码为数组。新版请求在生图前先发 `type=reference_images` SSE 事件确认已保存路径，前端据此更新预览和失败重试，避免重复上传。前端代理和后端请求体上限均为25MB，可容纳三张5MB原图的Base64请求。所有 `generated_`、`reference_` 文件在开发与生产环境均验证消息归属；媒体权限和删除清理同时检查单图列与完整引用数组，防止删除原始消息后误删仍作为图2/图3使用的图片。

普通聊天附件和广场图片由 `utils/media.py` 纠正 EXIF 方向、逐帧新建图像后按 PNG/JPEG/WebP/GIF 原格式重编码，只显式保留 ICC，移除 GPS、EXIF/XMP/IPTC、PNG 文本与 GIF comment；JPEG/WebP 质量为 90，MPO 仅保存主帧为 JPEG，动画保留时长和循环但限制 300 帧及 2 亿总像素。不透明 GIF 保留帧间差分，相同连续帧可能合并且总时长不变；RGB/L PNG 的 tRNS 色键转换为 alpha 后保留。重编码通过工作线程执行，进程内有界信号量最多允许两次同时处理，广场在线程派发前排队，聊天等待槽位超过 10 秒返回 503；聊天发给模型的 data URI 使用清理后的字节。广场视频用 ffmpeg 无损 remux，仅保留首个非封面视频流及可选首音轨，清除 metadata、chapters、字幕及数据轨；缺工具、超时或处理失败拒绝上传。临时文件位于调用时读取的上传目录，以 `os.replace` 原子落盘，权限为 0600，只能经后端提供静态访问；广场失败或取消清理半成品，聊天同步处理失败及等待线程期间取消会清理，线程完成后的消息写库取消窗口仍保留。启动清扫超过 1 小时的 `.upload_*` 普通文件，点文件一律返回 404。旧文件可通过 `scripts/strip_upload_metadata.py` 先默认 dry-run、再明确 apply 原子清理，跳过已清理图片并保留权限，有失败时 apply 返回非零。

`edit_image` 逐张校验本地路径、PNG 内容及 10MB 大小上限，按顺序将 1–3 张图的 Base64 数据和本轮指令传入模型；不传聊天历史或记忆。图号对应数组顺序，生图与修图均可选上述两种模型；默认沿用图1的尺寸，`aspect_ratio` 可覆盖。Seedream 目标尺寸需满足 921600–2048² 总像素，宽高比在 [1/16,16] 内；已在范围内的尺寸保持原样，需要缩放时按目标面积均匀缩放，每边取附近 8 的倍数，比例误差 ≤1% 的候选中先选面积最接近目标的尺寸，仅无此类候选时才选比例误差最小的合法尺寸。Seedream 与 Qwen 共用 `_reference_image_bytes` / `_png_dimensions`，本地参考 PNG 和生成结果均使用项目 2048² 像素上限；同步读取最多 40MB 的 Base64 响应，解码后沿用现有 PNG、20MB 和 2048² 像素校验与原子落盘，显式关闭水印。方舟 HTTP 错误与单张图 `error` 统一映射安全文案；失败日志和 trace 仅记录供应商状态及清洗后的 code（只保留 `[A-Za-z0-9._-]`，最多 80 字），不记录 message、请求 ID、提示词或密钥。Qwen 请求、下载和域名白名单保持原样。SSE 为 `status=editing_image`，成功事件含 `reference_image_paths` 及兼容字段 `reference_image_path`（首张），每次仍返回一张新图。页面通过“以此图修改”“加入参考”显式选图，支持移除和调整图序；提交或切换会话后清空当前引用，失败重试保留整组图、顺序和会话身份。

分身之间的交流由 `exchange_store.py` 与 `services/exchange_service.py` 独立处理，不经过私聊工具路由或记忆提取。双方公开名片并由受邀者接受后，数据库原子生成运行令牌，后台任务依次生成双方合计 2–6 条回复及一次总结。每次调用前预留预算、核验授权和剩余轮次；返回后复核同一令牌、当前状态及发言序号，阻止并发重复执行或撤销后的迟到保存。真人和官方体验的每一种交流 system 消息（包括总结、主创、审稿与修订）末尾均附基础安全规则。

真人分身间的模型输入只有白名单公开名片（名称、简介、头像符号）、主题和本次交流记录；每次输入最多 16,000 UTF-8 字节，回复最多 256 output tokens，总结最多 128。整个交流预留与实际用量不能超过 80,000 tokens，最多 7 次模型调用，禁用重试、回退与工具。缺失实际用量时使用保守估算；停止会取消本进程中的在途上游请求，迟到回复也不得发布。每账号最多 3 个待处理/运行交流、同时最多运行 1 个在途交流调用，同一对分身最多一个活动邀请。

新增交流表由 `20260905_agent_exchanges_v1` 事务迁移建立。启动时将遗留运行任务置为停止并结算未决预留，不重放模型请求；此恢复仅支持当前单进程部署。关闭名片在同一事务停止相关活动交流；删除账号连同双方共享的交流、回复与调用记录一起删除。

单人官方体验通过 `official_agents.py` 提供固定的“创意搭档”“脚本编辑”和“短视频创意搭档”目录，不创建用户或 `agents` 行。`GET /agent-exchanges/official-agents` 返回官方卡片；`POST /agent-exchanges/official` 校验固定目录 ID 与请求者分身后直接进入运行状态，复用有限轮数、预算预留、停止和总结流程。官方角色在提示词中明确为平台 AI，没有第二位真人主人。

`official:short-video-creator` 的创作流程与总结格式来自服务端 `get_official_exchange_instruction`：围绕钩子、冲突、反转逐步完善剧本，最后按时码输出分镜、画面、台词和音效。只有 official 类型与固定角色 ID 同时匹配才加入可信系统提示，不根据用户可编辑的名称或简介选择流程；这段指令不出现在公开目录。所有官方角色共用可配置的官方模型槽，新增角色无需新增用户、迁移数据或填写密钥。

官方体验不扣草莓，开启限流且 `DEV_MODE` 不为 `1` 时，默认每账号每个北京时间自然日最多创建 3 次，`FIONA_DAILY_OFFICIAL_EXCHANGES` 在调用时读取。在创建的 `BEGIN IMMEDIATE` 事务内、INSERT 前，按账号与 UTC `created_at` 加 8 小时后的日期计数，包括停止和失败记录；不同账号独立，未知官方 ID 仍先返回 404。不新增表或迁移版本。

每日每账号上限共七项：官方体验 3、热点展开 30、卡片详情 30、ASR 300、天气 30、BYOK 聊天 200、测试连接 20。后三项分别使用 `FIONA_DAILY_WEATHER`、`FIONA_DAILY_BYOK_CHATS`（`byok_chat`）、`FIONA_DAILY_BYOK_TESTS`（`byok_test`），其余使用原变量；均调用时读取，只接受正整数，非法回退默认且只告警一次。日期由 `database._today_shanghai()` 获取，除官方创建数据库事务计数外六项使用限流器内存计数，重启清零、北京零点换键；上游失败不退次数。天气缺参追问只检查额度，取消、非城市回复和本地失败不计数；天气与 BYOK 聊天超限返回 SSE error、不结算草莓，需要危机资源时先送一次资源。BYOK 聊天并发检查后才计次数，测试连接超限仍返回 200、ok:false。测试连接的平台限流为 10 次/分钟，命中时仍以 HTTP 200 返回 ok:false 和「操作太频繁，请稍后再试」。官方体验、热点展开、卡片详情和 ASR 四类 HTTP 超限仍返回 429、Retry-After 及同文案的 detail/error/retry_after。按 IP 每分钟限流继续生效；开发模式或限流器关闭时跳过每日上限。

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

每用户 BYOK 由独立 `backend/byok/` 管理，只在普通/镜子回复且配置启用、非 high 时替换平台建流；平台路径仍通过 chat_service 全局 `_create_stream_with_fallback` 查找，BYOK 绝不调用它，分身交流/官方搭档不读取用户模型配置。预设通义、DeepSeek、Kimi、智谱、Claude；custom 只允许公网 HTTPS/443，格式与全部 DNS 应答校验，拒绝代理假 IP、multicast 和危险 NAT64，连接时重新解析固定 IP，TLS SNI/证书仍用原主机名，不跟随重定向，不信任环境代理。自写 httpx transport 只用 httpcore 公开 API；Claude 直接使用 Anthropic SDK（httpx2），两类 HTTP 对象不混用。custom 每连接限制读取 4 MiB 的 HTTP 字节（TLS 之上），超限 abort 并映射为 connection 类别「连不上该服务」；custom 强制请求头 Accept-Encoding: identity，拒绝非空且非 identity 的 Content-Encoding，避免解压绕过 4 MiB 上限；错误仍归「连不上该服务」。预设厂商不受此字节限制影响。错误分类新增「服务繁忙，请稍后再试」，用于 Claude 529/overloaded_error。

零余额且已启用 BYOK、未预扣时，generate_image / weather 以外的 pending：「算了/取消/不用了/不要了/不查了/没事了」免费取消并清 pending；以「先聊/聊点/换个话题/先不」开头清 pending、由用户模型回复；其他补参消息仍报草莓不足、pending 保留。天气 pending 的「换个话题」类句子同样清 pending、由用户模型回复；余额充足用户与平台路由保持不变。

启用后，每条聊天回复会把分身设定、用户的私有长期记忆、本会话最近 60 条消息（含平台看图生成的图片描述）与本条消息发送给用户选择的厂商；系统提示中的账号名替换为「（账号已隐藏）」。危机复核、意图识别、模式判定、看图、全部工具、生图、朗读仍由平台处理并读取对话内容，画像提取仍由平台执行并会读到用户模型的回复；明确危机轮仍由平台回复。用户模型失败不改用平台模型。Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天，无服务端密钥无法解密。长期归档副本须先清除 Key 密文，步骤见部署手册。Claude 的接口不对中国大陆提供服务，大陆服务器通常无法连接该预设。

客户端每次显式传 Key/地址/60 秒读超时/max_retries=0，新建后关闭；调用前检查服务端密钥与十一项污染环境变量（完整清单见部署手册，含 `ANTHROPIC_CUSTOM_HEADERS`），读取/解密出错不走平台。预设厂商（含 Claude）遵循服务器的 HTTP(S)_PROXY / NO_PROXY 出站代理设置；自定义地址不使用环境代理。普通/镜子正文限制 4000/600 字；`FIONA_BYOK_TOTAL_SECONDS` 默认 120（10–240）秒从建流计时。响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时。中断线程只标记状态并 shutdown socket，阻塞调用返回后由属主 worker 关闭流、客户端和连接池。`FIONA_BYOK_MAX_STREAMS` 默认 8（1–64），专用有界 `fiona-byok` 池建流与逐块读取，全进程容量和每用户一条流；这两项调用时读取，非法回退并只告警一次。Claude max_tokens 普通4096/镜子2048，effort=low，Opus/Sonnet使用官方内部拒答兜底；OpenAI兼容普通2048/镜子512，不传采样参数。空正文报错不保存assistant；Claude拒答有正文时加中止说明保存。日志/trace仅记异常类型、厂商id、错误类别、耗时，模型trace记byok。

当前平台模型配置以 `backend/llm.py` 和各适配器源码为准：

- `deepseek-v4-pro`：本地已配置的官方搭档发言及单人体验总结；由 `exchange_models.py` 独立配置。
- `qwen3.8-omni-flash`：主力对话、匹配和复杂判断。
- `qwen3.8-flash`：轻量对话槽位，失败时回退主力模型；热点分类使用此模型，请求固定 8 秒超时、不重试；也用于独立的危机复核，危机复核不回退、不重试。
- `qwen-vl-max`：用户图片理解。
- `qwen-image-3.0`：默认聊天文生图及参考图编辑模型，每次一张；`QWEN_IMAGE_MODEL` 可调整。
- `seedream-5.0-flash`：可选生图及参考图编辑模型，经火山方舟调用；`ARK_API_KEY` 仅服务端读取，`SEEDREAM_IMAGE_MODEL` 默认 `doubao-seedream-5-0-flash-260915`，需先开通。
- `qwen-plus`：搜索、旅行规划、热点展开和卡片详情，均使用 DashScope 原生接口并强制开启联网搜索。
- `qwen3-asr-flash`：语音识别。
- DashScope TTS：语音合成。

工具分派位于 `backend/services/chat_service.py:execute_intent`，意图识别位于 `backend/intent_router.py`；`backend/tools/route.py` 仅实现驾车路线。当前内置函数还不是可发布、安装或交易的 Skill。系统/微信辅助模块中的部分功能是占位实现，不能视为可用的服务端 Skill。

意图识别出口由 `normalize_intent_result` 统一规范化：白名单为 `web_search`、`hot_topics`、`route`、`travel_plan`、`get_datetime`、`fetch_card`、`generate_image`、`weather`，只保留对应参数与去重后的缺失字段，畸形或未知意图回落空意图；此白名单仅应用于 `recognize_intent` 内部，不改写 fallback、分派或 pending 层载荷。天气问句（下雨、冷热、带伞、穿衣）归入独立 `weather` 意图，城市只能取用户本轮或最近对话里明确说出的城市。`utils.city_name.normalize_city` 共用于识别、补参、聊天和天气工具；缺城市追问“哪个城市？”，取消时清除 pending，非城市回复清除 pending 后按新消息路由。

天气由 `backend/tools/weather.py` 调用 `backend/tools/amap_mcp.py`，通过固定端点的无状态 `tools/call` 调用 `maps_weather`，不做 initialize 握手、不引入 MCP SDK；支持 JSON 和按请求 id 匹配的 SSE 响应，最多读取 1,000,000 字节。数据来自阿里云百炼托管的高德地图 MCP（Amap Maps），需在百炼控制台开通，使用调用时读取的 `DASHSCOPE_API_KEY`；目前限时免费，结束后按量计费，单价以控制台为准。隐私数据流：每次只把用户明确说出的城市名发给阿里云百炼托管的高德地图服务，不发聊天历史、私有记忆或用户位置，不做 IP 定位、不默认城市。日志只记录工具名、错误类型和耗时，城市名、用户原话、响应体不得进入日志、trace payload 或异常文案；上游错误只映射固定中文失败卡，成功天气卡才结算草莓。

`FIONA_AMAP_ENABLED` 默认 `1`，只有字面 `0` 关闭，关闭时不发请求；`FIONA_AMAP_TIMEOUT_SECONDS` 默认总预算 `8` 秒，只接受 `1–30` 范围的有限浮点数，空串、非数字、非有限值或越界值回落 `8`。两个变量均在调用时读取，MCP 端点不得用环境变量覆盖。

搜索、旅行规划、热点展开和卡片详情都复用 `tools.topic_expand._request_search`：固定 30 秒 socket 超时、不重试，不受兼容客户端的 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 控制。卡片详情路由 `backend/routers/cards.py` 外层另有 45 秒总超时。

`backend/tools/native_search.py` 为搜索与旅行规划整理来源，只取自原生 `output.search_info.search_results`，将纯数字字符串编号转为整数后复用 `tools.card_detail._search_sources` 做公网 HTTP(S) 格式校验、去重与引用优先排序；只下发标题、URL、站点和有效编号，最多 5 条，不下发图标。此链接校验不访问来源站点，不承诺链接实时可达；服务端实际抓取仍需独立的 DNS/IP 与重定向校验。模型输出的 `sources` / `url` 不参与卡片来源和表头 URL；模型正文（要点、旅行标题和非 JSON 回退行）在组装前依次清理引用角标与 HTTP(S)、www.、Markdown 链接，非字符串要点只允许非 bool 的 int/float 转成文字，其余对象丢弃，朗读和历史摘要使用已清理的正文。

搜索没有可用真实来源时交付错误卡，不结算草莓；旅行规划允许 `sources: []` 和空 URL，仍按原有成功规则交付建议。含“天气”的 `web_search` 查询与其他搜索一样走原生联网搜索，天气预报由独立 `weather` 意图调用高德地图 MCP。

## 鉴权与公开端点

HTTP 默认经过 `backend/main.py` 的鉴权中间件，身份来源优先级为：

1. `Authorization: Bearer <jwt>`
2. `fiona_token` Cookie
3. `DEV_MODE=1` 时的 `X-Dev-User`/`dev_user`

当前公开范围包括根进程响应和 `/health`、认证入口、`/hot/*` 中的只读榜单，以及 Plaza 的标签、Feed 和社群兴趣三个只读端点。`/health` 接受 GET/HEAD，3 秒总超时，以只读方式检查现有数据库及其可写权限、五道迁移和上传目录可写性，不建库、不调用外部服务，正常为 200 `{"status":"ok"}`，失败为 503 且仅列 `database/schema/uploads` 检查项，不泄露路径或异常。`/hot/expand` 会触发联网模型调用，中间件和路由依赖都要求登录。API 文档（`/docs`、`/redoc`、`/openapi.json`）只在 `DEV_MODE=1` 时开放，生产环境返回 404。WebSocket 不经过 HTTP 中间件，由具体端点单独认证。

按 IP 限流只在 ASGI `client.host` 属于调用时读取的 `FIONA_TRUSTED_PROXIES`（默认回环，支持 IP/CIDR）时采信 X-Real-IP/XFF；uvicorn 可能已把 `client.host` 改写为真实客户端 IP。每个 Nginx 入口必须覆盖 X-Real-IP 并追加 XFF，避免只设一个头时由 uvicorn 采信客户端伪造的 XFF；开发鉴权的 `is_loopback_client` 保持只看 ASGI 对端。

生产 JWT 使用 HS256，默认有效期 30 天，浏览器端只存于 `HttpOnly`、`SameSite=Lax` Cookie。JWT 带账号会话版本，每次 HTTP 请求和 WebSocket 握手都会与数据库核对；新账号的初始版本是随机正整数，既有账号版本不变，退出登录、撤销或轮换邀请码会使旧会话立即失效。邀请码仍绑定用户名并允许重复登录，但兑换会原子记录用量。删号事务向 `retired_usernames` 写入用户名；`backend/seed_invites.py` 在单个写事务中按用户表、邀请码表和退役表的最大 `testerNN` 编号分配新用户名，编号永不回收。`backend/manage_invites.py` 可查看、撤销和轮换。管理脚本先加载服务环境配置，并拒绝在未明确 `--init-db` 时创建不存在的数据库。

## 数据与文件

当前持久化完全位于单机。开发环境的默认路径为：

- SQLite：`backend/fiona.db`
- 媒体：`backend/uploads/`
- 环境变量：`backend/.env`
- 桌面开发连接：`desktop/fiona.config.json`

生产部署通过 `FIONA_DB_PATH` 和 `FIONA_UPLOADS_DIR` 将前两项放到
`/var/lib/fiona/fiona.db` 和 `/var/lib/fiona/uploads/`；API Key/JWT Secret 位于
权限为 `0600` 的 `/etc/fiona/fiona.env`，不写入只读代码目录。

SQLite 表由 `backend/database.py:init_db()` 在启动时创建，初始化时启用持久的 WAL 模式，连接设置一致且不低于 5 秒的 busy timeout。历史字段仍使用旧的容错式 `ALTER TABLE`，其中包括可空列 `users.strawberry_refill_date`；兼容建表还包括 `retired_usernames`、`user_model_configs`；后者在 init_db 直接执行模块 DDL，不新增迁移版本，health 与五道迁移不变。新增分身与会话由 `backend/agent_store.py:migrate_avatar_schema()` 执行版本化事务迁移，版本记入 `schema_migrations`。当前没有通用迁移框架或 PostgreSQL 实现。

`agents` 对每个 owner 设置唯一约束，保存可编辑身份，以及不经名片 API 输出的 `private_memory_json/memory_revision`。初次创建时复制本人旧画像作为私有基线，之后与 `users.profile_json` 分开；旧社会画像仍用于原有显式匹配流程。公开名片只经字段白名单返回，不返回用户名、人格设定或私有记忆。

`conversations` 为本人私有会话，包含分身 ID、名称和默认会话标识；`messages` 新增 `conversation_id/agent_id`，迁移在同一事务中回填旧消息。默认会话删除后可创建新的默认会话，但旧 ID 永不复用。读取、写入和删除都在数据库操作中复核账号及会话归属。新会话首条消息可自动命名，显式设置的标题保持不变。

画像提取使用会话内消息和私有记忆修订号，通过条件写入避免清空记忆、删除会话或账号后的迟到回填。清空记忆同时清理私有副本与旧社会画像，保留原始聊天记录；未来交流可以形成新的记忆。待补全工具参数和模式以 `(username, conversation_id)` 隔离并保存在 SQLite 的 `chat_slot_state` 表，重启后在有效期内可恢复；异步请求路径把同步槽位读写交给工作线程，避免阻塞事件循环，连接不再重复建表。

`user_model_configs` 每用户名一行，保存厂商、custom 地址、模型、版本化 AES-256-GCM 密文、HMAC key_id、Key末四位、启用位与时间戳；AAD绑定用户名/厂商/地址，改变厂商或地址必须重填Key，模型可单独修改。写入 BEGIN IMMEDIATE 后检查用户存在，迟到保存不能复活删号配置；公开读取白名单字段、不返回密文或Key，解密失败标 needs_reentry，内部取Key不缓存。删号在删除 users 前同事务删除该表记录。`FIONA_BYOK_SECRET` 是 url-safe base64 的32字节服务端密钥，单独保管、不进数据库/媒体备份；`FIONA_BYOK_SECRET_PREVIOUS` 逗号分隔旧密钥仅解密，下一次保存用当前密钥重加密。密钥丢失只需用户重填Key，缺失/非法整体不可用，不在导入时raise，DEV_MODE无固定回退。生成命令：`python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`。

主要数据域包括：加密自带模型配置、用户和画像、消息、匹配、待接受卡片、真人消息、帖子/点赞、标签与时间偏好、用户成长状态、事件、OTP、邀请码、退役用户名、槽位状态和上传清理队列。

`fiona.db` 与 `uploads/` 必须作为一个隐私数据集合共同备份和清理。WAL 模式下在线数据库备份必须使用 SQLite `.backup` 或在线备份 API；只复制主数据库文件会漏掉未检查点的提交。`deploy/fiona-backup.sh` 以数据库属主运行并校验备份完整性，媒体与库用同一时间戳、权限 `0600`，默认保留 14 天；systemd timer 每天北京时间 04:00 执行并补跑。`backend/migrate.py` 默认在数据库及伴生文件的临时副本上只执行 `init_db`，不恢复交流或清理文件，明确 `--in-place` 才迁移指定库。删除单条消息、清空历史或删除账户时，数据库会在同一事务中找出不再被消息/帖子引用的媒体并写入 `upload_cleanup_queue`；文件会立即清理，失败项在后端启动时和运行期间周期重试，每轮异常只记类型并继续。新帖子在库内保存 owner；能通过当前 HMAC 或旧 MD5 匿名标识识别的历史帖子会自动回填，无法识别的旧行仍需人工处置。

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

- SQLite 每次操作创建连接；WAL、统一 busy timeout 和异步路径的槽位读写隔离已启用，正式迁移和更高并发能力仍待建设。
- 模型预算计数是单进程内存状态，不是供应商账单或集群级配额；草莓预扣、退款和每日补给已原子化，真实 usage 与持久化成本控制仍待完成。
- 消息/账户删除已有引用检查和持久化文件清理周期重试；全目录孤儿扫描与保留期限尚未完成。
- ASGI 层限制总请求体为 25 MB，Chat/图片、ASR、TTS、帖子和分页还有更严格的领域边界；上传图片验证真实格式、完整性和像素量并去元数据，广场视频由 ffmpeg remux 去元数据，处理失败拒绝保存。官方体验、热点展开、卡片详情、ASR、天气、BYOK 聊天和测试连接已叠加七项每日每账号上限，天气超限通过聊天错误事件退款；兼容模型客户端已有可配置超时和有限重试，搜索、旅行规划、热点展开和卡片详情的原生调用则固定 30 秒 socket 超时、无重试且不受兼容客户端超时/重试环境变量控制；热点分类使用 `qwen3.8-flash`，固定 8 秒超时、不重试。并发边界、公共热点缓存和持久化成本上限仍需继续治理。
- 热点与网页卡片的服务端抓取通过只允许公网 HTTP(S) 的客户端访问，每次 DNS 和重定向都会重新校验并限制响应体与超时；搜索与旅行卡片只展示原生搜索结果中经公网 HTTP(S) 格式校验的链接，模型生成的 URL 不进入这两类卡片。
- 前端主页面承担职责过多，多个隐藏 iframe 会继续运行轮询或 3D 场景。
- 仓库已增加后端与 Web 质量门禁工作流；Windows 桌面工作流会运行 Rust 单测再打包。新工作流仍需在 GitHub 首次运行中确认 runner 环境。

当上述实现发生变化时，应在同一个变更中更新本文、根 README 和 PLAN 的状态。
