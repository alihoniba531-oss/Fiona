# Fiona / Chloe 开发上下文

个人 AI 分身交流与 Skill 平台，当前第一阶段支持独立分身和持久私有会话，用于作者自用和受控小范围内测。分身互聊与 Skill 交易尚未实现。完整说明见 `README.md`，实际数据流见 `docs/ARCHITECTURE.md`，当前风险和路线图见 `PLAN.md`。

## 当前架构

- `backend/`：FastAPI + SQLite `fiona.db`，入口 `main.py`，通过 `run.py` 监听 `127.0.0.1:8000`。
- `frontend/`：Next.js 16.2.6 App Router + React 19，开发端口 3000。
- `desktop/`：Tauri 2 Windows 壳；有配置时建 SSH 隧道，无配置时加载 `https://madchloechat.online`（线上服务已于 2026-09-25 下线，该地址当前不可用）。
- 模型：DashScope/Qwen；主力 `qwen3.8-omni-flash`，轻量 `qwen3.8-flash`，图片 `qwen-vl-max`，搜索、旅行规划、热点展开和卡片详情 `qwen-plus`，语音使用 Qwen ASR 和 DashScope TTS。这四项走 DashScope 原生接口并强制联网搜索，固定 30 秒 socket 超时、不重试，不受兼容客户端的 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 控制；卡片详情路由外层另有 45 秒总超时。热点分类使用 `qwen3.8-flash`，请求固定 8 秒超时、不重试。生图和修图默认 Qwen Image 3.0，可选火山方舟 Seedream 5.0 Flash；两者均扣 10 颗草莓，后者将描述和参考图发送给字节跳动火山引擎。
- 天气：独立 `weather` 意图，使用阿里云百炼托管的高德地图 MCP（Amap Maps）；需在百炼控制台开通，复用 `DASHSCOPE_API_KEY`，目前限时免费，结束后按量计费，单价以控制台为准。每次只向该服务发送用户明确说出的城市名，不发送聊天历史、私有记忆或用户位置，不做 IP 定位、不默认城市。
- 数据：SQLite、`backend/uploads/`、`backend/.env` 都是本机/单机状态，不进入 Git。

## 核心模块

- 聊天主流程：`backend/routers/chat.py`、`backend/services/chat_service.py`
- 每用户聊天模型：`backend/byok/` 加密配置、SSRF 防护、OpenAI/Anthropic 流适配；`backend/routers/chat_model.py` 提供登录后配置与连接测试。仅普通/镜子回复接管，不影响 high、辅助模型、工具、生图、TTS、画像提取或分身交流/官方搭档。
- 分身与会话：`backend/agent_store.py`、`backend/routers/agents.py`、`backend/routers/conversations.py`；消息必须绑定已验证的会话 ID。
- 私有记忆：分身独立 JSON 和修订号；新会话不得写入旧社会画像或触发旧自动匹配。名片只使用显式公开字段。
- Persona/成长状态：`backend/persona.py`、`backend/avatar_state.py`、`backend/state_probe.py`
- 画像与匹配：`backend/extractor.py`、`backend/conversation_matcher.py`、`backend/matcher.py`
- API：`backend/routers/` 下的 auth/chat/hot/match/me/peer/plaza/voice
- 工具：`backend/tools/`；意图识别出口对白名单 `web_search`、`hot_topics`、`route`、`travel_plan`、`get_datetime`、`fetch_card`、`generate_image`、`weather` 及参数和缺失字段做格式规范化，白名单只在 `recognize_intent` 内部生效。天气城市规范化共用纯函数 `backend/utils/city_name.py`。
- 前端 API 基址：`frontend/lib/config.ts`
- 前端鉴权：`frontend/lib/auth.ts`、`frontend/proxy.ts`
- 桌面启动与权限：`desktop/src-tauri/src/lib.rs`、`desktop/src-tauri/capabilities/default.json`

## 本地命令

后端从 `backend/` 运行：

```bash
python run.py
python -m pytest -q
```

测试必须优先使用 `python -m pytest`，直接调用某些环境中的 `pytest` 可能无法导入后端顶层模块。

前端从 `frontend/` 运行：

```bash
npm ci
npm run dev
npm run lint
npx tsc --noEmit
npm run build
```

修改前端代码前必须阅读 `frontend/AGENTS.md` 和本地 `frontend/node_modules/next/dist/docs/` 中对应的 Next.js 16 文档。

## 鉴权和配置

- `backend/.env.example` 是后端配置模板。
- 生产必须 `DEV_MODE=0`，设置真实 `DASHSCOPE_API_KEY` 和强 `JWT_SECRET`。
- 内测登录使用邀请码，`backend/seed_invites.py` 原子分配不会与现有用户、邀请码绑定名或已退役用户名冲突的 `testerNN` 用户名；删号后的编号不回收。
- `backend/manage_invites.py` 查看、撤销和轮换邀请码；这些操作会使绑定账号的旧会话失效。`backend/manage_strawberries.py` 可查看、补充或设置草莓。三个脚本在导入数据库前加载服务环境文件，生产执行时明确传 `--env-file /etc/fiona/fiona.env`，并核对输出的数据库绝对路径；只有首次建库才传 `--init-db`。
- 生产私聊实际交付的平台模型回复、图片或成功工具结算 10 颗草莓，并发预扣原子化；BYOK 聊天回复不扣草莓并退还预扣，余额不足但已启用 BYOK 时只允许自带模型聊天，工具/看图/生图仍返回草莓不足。`STRAWBERRY_DAILY_REFILL` 默认关闭，可按 Asia/Shanghai 自然日补到下限。`DEV_MODE=1` 跳过预扣，零余额守卫为空操作。
- 官方体验不扣草莓。七项每日上限为官方体验 3、热点展开 30、卡片详情 30、ASR 300、天气 30、自带模型聊天 200、测试连接 20；后两项分别由 `FIONA_DAILY_BYOK_CHATS`（`byok_chat`）、`FIONA_DAILY_BYOK_TESTS`（`byok_test`）配置。配置均调用时读取，只接受正整数，非法值回落默认并只告警一次；开发模式或关闭限流器时跳过。官方创建用数据库事务计数，热点展开、卡片详情、ASR、天气分别沿用 `FIONA_DAILY_HOT_EXPANDS`、`FIONA_DAILY_CARD_DETAILS`、`FIONA_DAILY_ASR`、`FIONA_DAILY_WEATHER`；其余六项使用单进程内存计数，重启清零、北京零点换日，上游失败不退还次数。BYOK 聊天先检查并发，再计每日次数；超限在流内报错、退款，测试连接超限仍用 HTTP 200 返回 `ok:false`。 天气缺参追问只检查额度，取消和本地校验失败不计数；天气超限返回聊天错误事件、不写 pending、不扣草莓，成功天气卡才按普通工具结算。
- `FIONA_AMAP_ENABLED` 默认 `1`，只有字面 `0` 关闭；`FIONA_AMAP_TIMEOUT_SECONDS` 为天气 MCP 请求总预算，默认 `8` 秒，合法范围 `1–30`，非有限值、空串、非数字和越界值回落 `8`；均在调用时读取。固定 MCP 端点不能由环境变量覆盖。
- BYOK 隐私：启用后，每条聊天回复会把分身设定、用户的私有长期记忆、本会话最近 60 条消息（含平台看图生成的图片描述）与本条消息发送给用户选择的厂商；系统提示中的账号名替换为「（账号已隐藏）」。危机复核、意图识别、模式判定、看图、全部工具、生图、朗读仍由平台处理并读取对话内容，画像提取也仍由平台执行，并会读到用户模型的回复；明确危机轮仍由平台回复。用户模型失败不改用平台模型。Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天，无服务端密钥无法解密。长期归档副本须先清除 Key 密文，步骤见部署手册。Claude 的接口不对中国大陆提供服务，大陆服务器通常无法连接该预设。
- BYOK 运行边界：自定义上游响应上限 4 MiB。custom 强制请求头 Accept-Encoding: identity，拒绝非空且非 identity 的 Content-Encoding，避免解压绕过 4 MiB 上限；错误仍归「连不上该服务」。响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时。中断线程只标记状态并 shutdown socket，阻塞调用返回后由属主 worker 关闭流、客户端和连接池。测试连接的平台限流为 10 次/分钟，命中时仍以 HTTP 200 返回 ok:false 和「操作太频繁，请稍后再试」。Claude 过载显示固定「服务繁忙，请稍后再试」。零余额且已启用 BYOK、未预扣时，generate_image / weather 以外的 pending：「算了/取消/不用了/不要了/不查了/没事了」免费取消并清 pending；以「先聊/聊点/换个话题/先不」开头清 pending、由用户模型回复；其他补参消息仍报草莓不足、pending 保留。天气 pending 的「换个话题」类句子同样清 pending、由用户模型回复；余额充足用户与平台路由保持不变。付费执行在清 pending 前检查余额。
- Claude 思考强度可选低 / 中 / 高，默认低；聊天底栏和设置页切换立即保存到服务端账号。低、中、高的 `max_tokens` 普通/镜子分别为 4096/2048、8192/4096、16384/8192；低与中总时限为 `FIONA_BYOK_TOTAL_SECONDS`（默认 120 秒），高为 `min(240, FIONA_BYOK_TOTAL_SECONDS×1.5)`（默认 180 秒），必须小于 Nginx 的 300 秒。调高会先思考再回答，用户自己的额度消耗随档位上升；其他厂商不受影响。正文仍限普通 4000 字、镜子 600 字，测试连接固定低档/1024 tokens/原总时限。`user_model_configs` 新增 `effort TEXT NOT NULL DEFAULT 'low'`，老库启动时自动补列，已有行默认低，不新增迁移版本号，`/health` 不变；保存模型、Key 或切换厂商保留档位，只在 Claude 下生效。
- BYOK 密钥：服务端 `FIONA_BYOK_SECRET` 为 url-safe base64 编码的 32 字节，单独保管，不进入数据库/媒体备份；丢失时用户重新填写自己的 Key 即可。`FIONA_BYOK_SECRET_PREVIOUS` 为逗号分隔的旧密钥，仅用于解密，用户下次保存使用当前密钥重新加密。缺失或非法密钥、十一项污染客户端的环境变量会使 BYOK 不可用（含 `ANTHROPIC_CUSTOM_HEADERS`，完整清单见部署手册），DEV_MODE 也没有固定回退值。预设厂商（含 Claude）遵循服务器的 HTTP(S)_PROXY / NO_PROXY 出站代理设置；自定义地址不使用环境代理。 `FIONA_BYOK_MAX_STREAMS` 默认 8（1–64），每用户一条流；`FIONA_BYOK_TOTAL_SECONDS` 默认 120（10–240）秒，调用时读取，非法回退默认并只告警一次。生成命令：`python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`。
- 浏览器 JWT 只在 `HttpOnly` Cookie 中；新账号的会话版本使用随机正整数，既有账号版本保持原值，HTTP/WebSocket 每次鉴权都核对数据库会话版本，不能恢复 query token 或 JavaScript 可读存储。
- `DEV_MODE=1` 且请求 socket 对端为回环地址才开放测试登录和 `X-Dev-User` 等开发通道；前端 `npm run dev` 默认只监听 `127.0.0.1`，`npm run dev:lan` 才显式对局域网开放。
- 单域名环境不设置 `NEXT_PUBLIC_API_BASE`；前端相对 `/api` 由 Next rewrite 或生产 Nginx 转发。

## 生产拓扑

- Nginx 443：`/` → Next.js 3000，`/api/` → FastAPI 8000 并移除前缀，`/uploads/` → FastAPI。
- systemd：`fiona` 启动后端，`fiona-web` 启动 `next start`。
- 原线上服务器（域名 `madchloechat.online`）已于 2026-09-25 关闭，当前没有在线部署；下线记录见 `docs/DEPLOYMENT.md`。重新部署时以部署手册为准，不要假定任何服务器仍在运行。
- 所有生产命令、备份和回滚步骤以 `docs/DEPLOYMENT.md` 为准；SQLite 启用 WAL 后须用 `sqlite3 .backup` 或在线备份 API 获取一致快照，不能只复制主数据库文件。仓库文档不能证明外部服务器的即时状态。
- `deploy/fiona-backup.sh` 必须以数据库属主运行，备份目录为服务账号所有且 `0700`，备份文件 `0600`；timer 每天北京时间 04:00 执行，默认保留 14 天。`backend/migrate.py` 默认在库及 WAL/SHM 临时副本上仅执行初始化迁移，`--db` 优先于配置，明确 `--in-place` 才写指定库；恢复演练不得启动唯一备份。
- `/health` 无需登录，支持 GET/HEAD，3 秒总超时，只读检查现有数据库及其可写权限、五道迁移和上传目录，不探测外部服务、不泄露路径；原 `/` 仍只检查进程。启动从未成功时退出 3，上传清理单轮异常后继续。外部拨测用 GET，systemd 失败通知与供应商消费告警按部署手册配置，消费告警由作者手工完成。
- 按 IP 限流只在 ASGI 对端属于调用时读取的 `FIONA_TRUSTED_PROXIES` 时信任代理头；所有 Nginx 入口必须覆盖 X-Real-IP 并追加 XFF，uvicorn 可能已按 XFF 改写对端。开发回环鉴权函数保持只看 ASGI 对端。

## 当前重要边界

- 这是 SQLite 单机内测架构，不要宣称已经支持 PostgreSQL 或无限并发。
- 远程 Tauri capability、Windows `open_url` 和 CSP 已完成代码整改；桌面公开发布仍需 Windows/Rust 复核、签名和发布验证。
- 热点与网页卡片的服务端抓取已经统一经过公网 HTTP(S) 校验、DNS/IP 固定、逐跳重定向检查和响应大小限制。
- 搜索与旅行卡片来源只取自原生 `output.search_info.search_results`，经公网 HTTP(S) 格式校验后下发，模型生成的 URL 不进入卡片；此校验不访问来源站点。前端最多显示 5 条可点击来源，统一用 `openExternal` 打开；模型正文（要点、旅行标题与非 JSON 回退行）在卡片组装前依次清理引用角标与 HTTP(S)、www.、Markdown 链接，朗读和历史摘要使用清理后的正文。非字符串要点只允许非 bool 的 int/float 转成文字，其余对象丢弃。搜索无可核实来源时错误且不计费，旅行建议允许没有来源。卡片及来源不落库，刷新或切换会话后只剩文字摘要。
- 问句式天气请求走 `weather`，没明确城市就追问“哪个城市？”，取消或非城市回复不会调用高德；普通 `web_search` 不按“天气”关键词分流。天气卡最多四天的中文日夜预报，无实时温度、体感或湿度；卡片不落库。天气调用失败日志仅记录工具名、错误类型和耗时，城市名、用户原话、响应体不得进入日志、trace payload 或异常文案。
- Layer 2 双边卡片、双方偏好验证、手动匹配输出约束和跨用户画像最小化已完成；候选原始消息不得进入匹配模型。
- 完整账户删除会在删除 users 前同事务删除 `user_model_configs` 配置（含 `effort`）与加密 Key，清理其他数据库关联记录、关闭真人连接，并通过持久化队列重试无引用上传文件；关键后台写入必须继续防止删号后重建数据。
- 总请求体、Chat/图片、ASR、TTS、帖子和分页已有应用层边界；模型并发、真实 usage 与持久化成本控制仍未完成。
- 聊天和广场图片在线程中纠正方向、按原格式逐帧重建去元数据，仅保留 ICC；MPO 只存主帧，动图有限帧和总像素，并发重编码最多 2，广场在线程派发前排队，聊天等待槽位超时返回 503。广场视频依赖 ffmpeg 无损 remux，清 metadata、章节、数据和字幕轨，失败拒绝上传。上传目录内临时文件原子落盘，权限 0600；广场失败或取消、聊天同步处理失败及等待线程期间取消会清理，线程完成后的消息写库取消窗口仍保留。启动清扫超过 1 小时的上传临时文件，点文件不提供静态访问且不进入媒体备份。旧文件清理脚本默认 dry-run，跳过已清理图片，apply 有失败返回非零并保留原权限。语音合成仅保留 HTTP/流式接口，真人 Peer WebSocket 保留。
- 模型预算是进程内估算，不等同于供应商真实账单；草莓预扣、退款及每日补给已实现原子化，真实 usage 与持久化成本控制仍待完成。
- 私聊危机采用规则加模型复核：规则 `high` 直接进入支持流程；其他非空文字消息由 `qwen3.8-flash` 复核，只看当前消息；超过 2000 字时取首尾各 1000 字，中间用「……」连接。取较高档位，不能降档。复核与预扣、上下文装配并行，默认 2 秒超时，失败按规则结果走；只记录档位、异常类型和耗时，不记录原文。信息或求助语境只看规则。私聊未命中危机信号的轮次，所有 system 消息合计恰好包含一次基础安全规则，放在最后一条 system 消息末尾；请求朗读时，平台模型与 BYOK dashscope 预设将朗读强约束作为当前 user 消息后的独立 system 消息；其他 BYOK 厂商合并 system，Claude 使用顶层 system，基础安全规则仍恰好一次且在末尾。明确危机轮跳过普通模式、工具与待补参数，固定附上求助资源；余额足够时照常预扣并按交付结算，余额不足时免费返回资源且不调用回复模型。可能相关的轮次保留模式判定、镜子、看图、普通回复和计费；除信息或求助语境外，跳过自然语言生图候选、意图识别、工具及待补参数，保留 pending。信息或求助语境、界面显式生图或修图、缺少修图参考的固定引导保持原路由；唯一例外是已有天气 pending 时，到达工具路由的 `possible` 信息或求助语句清除该 pending，按新消息路由，不能当作城市名发给高德。文字、工具、图片以及服务端能控制的错误路径均恰好送达一次资源；余额不足时先送资源再报错；进入路由前的 422 校验和 429 限流是例外。图片模式的明确危机轮按文字回复显示。繁体危机文字只在规则分类时归一，模型复核、存库和显示保留原文。繁体『計畫』与『計劃』判级一致。分身交流每条 system 消息也带基础安全规则。测试在收集阶段强制使用会话临时数据库与上传目录。
- 前端主页面和常驻抽屉 iframe 有已知性能与维护债务。
- Persona、成人内容、AI 身份披露、年龄与危机处理政策必须在扩大内测前统一。

## 工作约定

- 优先修复可复现问题，避免无关重构。
- 不提交 `.env`、数据库、上传文件、备份或 `fiona.config.json`。
- 代码改变模型、路由、端口、环境变量、数据位置或部署方式时，同步更新 README、架构/部署文档和 PLAN。
- 只有作者明确要求时才提交 Git commit。
