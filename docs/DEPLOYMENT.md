# Fiona 生产部署手册

本文把仓库当前采用的“单机、单域名、Nginx + systemd”拓扑写成可执行的基线。当前约定的线上域名是 `madchloechat.online`，只读代码目录是 `/opt/fiona`，运行状态位于 `/var/lib/fiona`。

> **2026-09-25：线上服务已下线。** 原 `madchloechat.online` 服务器已关闭，当前没有任何在线部署，详见文末[下线记录](#下线记录)。本文其余内容保留为重新部署时的参考基线。

> 仓库无法证明外部服务器此刻的真实配置。首次使用或接手服务器时，必须先核对 Nginx、systemd、证书、数据库和上传目录，再按本文操作。

## 目标拓扑

```text
Internet :443
    │
    ▼
  Nginx
    ├── /           → Next.js 127.0.0.1:3000
    ├── /api/*      → FastAPI 127.0.0.1:8000/*
    └── /uploads/*  → FastAPI 127.0.0.1:8000/uploads/*

systemd:
    fiona.service      → backend/.venv/bin/python run.py
    fiona-web.service  → npm run start

state:
    /var/lib/fiona/fiona.db
    /var/lib/fiona/uploads/
    /etc/fiona/fiona.env
```

该拓扑目前只支持单个后端实例。SQLite、进程内预算计数器和短时、限次 TTS 票据不适合直接横向扩容。

## 2026-09-05 分身与会话迁移

新版后端首次启动会自动执行 `20260905_private_agents_v1` 事务迁移：创建分身与会话表、为既有账号建立私有分身和默认会话、复制旧画像作为私有记忆基线，并回填旧消息归属。旧社会画像保留，新会话提取的记忆之后独立保存。

分身互聊版本还会执行 `20260905_agent_exchanges_v1`，创建交流、回复及调用记录三张独立表。此迁移不改已有分身公开状态或私聊数据。继续使用单后端进程；启动时将上次中断的交流置为停止、保守结算未决用量，不自动恢复生成。多 worker/多实例需要独立的任务租约与恢复机制，当前不要直接增加 worker 数。

官方单人体验继续执行 `20260905_official_agent_exchanges_v2`，在事务中重建交流主表以支持无用户账号的官方参与者。迁移逐字段校验旧记录和子表引用，并恢复索引；失败时回滚，可修复数据后重试。请先停止写入并备份数据库。迁移不会增加虚构用户，也不会公开已有分身。

99 次官方体验还会执行 `20260905_official_exchange_limits_v3`，保留已有交流和索引/触发器，并给调用表增加供应商、模型字段；既有回复次数与内容不会被改写。配置 `OFFICIAL_EXCHANGE_PROVIDER=deepseek`、`OFFICIAL_EXCHANGE_MODEL=deepseek-v4-pro` 和服务端 `DEEPSEEK_API_KEY` 可切换官方搭档及总结的模型，自己的分身仍使用 Qwen。密钥放在忽略版本控制的后端环境配置中，不使用 NEXT_PUBLIC 变量；修改后重启单后端进程。

第 5 道 `20260905_official_exchange_workflow_v4` 为交流增加工作流、作品与完成原因字段，为回复增加阶段与审稿 JSON 字段；既有记录保留原流程，新官方体验使用主创、审稿、修订流程。五道迁移都应出现在 `schema_migrations` 中。

更新前停止旧后端写入，按本文备份数据库与媒体，再启动新版。迁移版本和回填在一个事务中提交；发现无有效 owner 的旧消息或其他迁移错误时会回滚并阻止启动，应检查数据归属后重试，不要手动写入迁移成功标记。

兼容范围是旧客户端的 HTTP 接口，不包括旧后端与新版同时写同一数据库。若回退到迁移前的服务版本，应按下文恢复流程使用匹配的数据库/媒体备份，并先保全迁移后产生的数据；不要让旧服务继续写入新库后再直接切回新版。

本次只在临时数据库验证迁移和回滚，尚未操作线上数据。

浏览器隔离联调可设置前端服务端变量 `FIONA_BACKEND_ORIGIN=http://127.0.0.1:8001`，将 `/api` 代理到临时后端；默认仍为 `http://localhost:8000`。该变量参与 Next 配置，正式构建前应清除测试值。测试浏览器使用 `localhost`，与现有 `127.0.0.1` 预览隔离 Cookie。

多参考图编辑升级会在启动时为 `messages` 增加可空的 `reference_image_paths` 列，已有单图消息保持原样；新消息按顺序存入参考图数组，并保留首张 `image_path` 兼容字段。更新前停止旧后端并备份数据库与媒体。升级后应同时使用新版媒体权限与清理逻辑，以保护数组中的第二、第三张参考图；不要单独回退后端的附件清理代码。

外部参考图上传与生成图共用上述引用字段，无新增表。上传源图规范为私有 `reference_*.png`，媒体权限不可只保护 `generated_*`。前后端请求体上限25MB；若使用额外反向代理，也应允许至少25MB请求体，才能提交三张各5MB的Base64参考图。

## 前置条件

- Linux 云服务器
- Git
- Python 及 `venv`
- Node.js 20+ 和 npm
- ffmpeg（浏览器录制的 WebM/Opus 语音需要转码；广场视频去元数据也依赖它，建议 ≥ 6，旧版 remux 可能丢旋转信息）
- `sqlite3` 命令行（数据库在线备份依赖 `.backup`）
- Python 链接的 SQLite ≥ 3.35（数据写入使用 `RETURNING`）
- Nginx
- systemd
- 域名 DNS 已指向服务器
- Certbot 或等价 TLS 证书管理工具
- 有效的 DashScope API Key

上传图片和视频以 `0600` 落盘，只能经后端鉴权后的 `/uploads/` 访问；不要配置 Nginx 直接读取上传目录。GIF 相同的连续帧可能合并，总播放时长不变。3GP 中的 AMR 音频未验证能否 remux 到 MP4，可能处理失败；失败时需先转成兼容的 MP4 再上传。

Debian/Ubuntu 可用 `sudo apt-get update && sudo apt-get install -y ffmpeg sqlite3` 安装前两项；用 `ffmpeg -version`、`sqlite3 --version` 和 `python3 -c "import sqlite3; print(sqlite3.sqlite_version)"` 自检。最后一条应输出 3.35.0 或更新版本。

建议只对公网开放 22、80 和 443，端口 3000、8000 仅监听或仅允许本机访问。

## 首次安装

先创建无登录 shell 的专用服务账号和状态目录。不要让 Web 或 API 进程以 root 运行：

```bash
useradd --system --home /var/lib/fiona --shell /usr/sbin/nologin fiona
install -d -o root -g root -m 0755 /opt/fiona
install -d -o fiona -g fiona -m 0700 /var/lib/fiona /var/lib/fiona/uploads
install -d -o root -g root -m 0755 /etc/fiona
install -d -o fiona -g fiona -m 0700 /var/backups/fiona

git clone <Fiona 仓库地址> /opt/fiona
cd /opt/fiona/backend
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pip_audit -r requirements.txt --progress-spinner off
install -o root -g root -m 0600 .env.example /etc/fiona/fiona.env
```

编辑 `/etc/fiona/fiona.env`：

```dotenv
DASHSCOPE_API_KEY=<真实 DashScope Key>
DASHSCOPE_TIMEOUT_SECONDS=60
DASHSCOPE_MAX_RETRIES=1
JWT_SECRET=<足够长的随机字符串>
DEV_MODE=0
FIONA_DB_PATH=/var/lib/fiona/fiona.db
FIONA_UPLOADS_DIR=/var/lib/fiona/uploads
STRAWBERRY_DAILY_REFILL=0
```

OpenAI 兼容模型客户端默认 60 秒超时、最多重试 1 次，可通过 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 调整（模板允许 5–300 秒、0–3 次）。搜索、旅行规划、热点展开和卡片详情均使用 DashScope 原生 `qwen-plus` 接口、强制开启联网搜索，固定 30 秒 socket 超时、不重试，不受这两个环境变量控制；调大兼容客户端超时不会延长这四项调用。卡片详情路由外层另有 45 秒总超时。热点分类使用 `qwen3.8-flash`，请求固定 8 秒超时、不重试。

搜索与旅行卡片的来源只取自原生响应 `output.search_info.search_results`，经公网 HTTP(S) 格式校验后下发，模型生成的 URL 不进入卡片；模型正文中的引用角标与 HTTP(S)、www.、Markdown 链接也会清理。前端在要点下方显示可点击标题和站点，通过安全外链入口打开；校验不探测来源站点可达性。卡片及来源不落库，刷新或切换会话后只保留清理后的文字摘要。部署后抽查应覆盖搜索无真实来源时的错误与退款、旅行无来源时的正常交付，以及浏览器和 Tauri 的来源点击行为。

天气使用阿里云百炼托管的高德地图 MCP（Amap Maps）：须在百炼控制台开通，复用 `DASHSCOPE_API_KEY`，目前限时免费，结束后按量计费，单价以控制台为准。客户端只调用固定的百炼 Amap Maps 端点，不能用环境变量改端点；独立 `weather` 意图识别下雨、冷热、带伞或穿衣问句，没有明确城市就追问“哪个城市？”，取消或非城市回复不发起天气查询。意图识别出口对白名单 `web_search`、`hot_topics`、`route`、`travel_plan`、`get_datetime`、`fetch_card`、`generate_image`、`weather` 及参数、缺失字段统一做格式规范化。包含“天气”的普通搜索仍走原生联网搜索。

| 环境变量 | 用途 |
|---|---|
| `DASHSCOPE_API_KEY` | DashScope 模型密钥，天气也使用此 Key；需先在百炼控制台开通 Amap Maps |
| `QWEN_IMAGE_MODEL` | 默认生图和修图模型，默认 `qwen-image-3.0`，使用 `DASHSCOPE_API_KEY` |
| `ARK_API_KEY` | 可选 Seedream 生图和修图的火山方舟密钥，仅服务端读取；须先在方舟控制台开通 Seedream 5.0 Flash |
| `SEEDREAM_IMAGE_MODEL` | Seedream 真实模型名，默认 `doubao-seedream-5-0-flash-260915`，调用时读取 |
| `FIONA_CRISIS_MODEL_ENABLED` | 危机模型复核默认开启，仅 `0` 关闭；规则高危不复核，模型只能升档 |
| `FIONA_CRISIS_MODEL_TIMEOUT_SECONDS` | 独立危机客户端超时，默认 `2.0` 秒，合法范围 `0.5–10`，无效值回落默认；不重试，失败按规则结果走 |
| `FIONA_DB_PATH` | 服务和管理脚本使用的 SQLite 数据库路径 |
| `FIONA_UPLOADS_DIR` | 上传文件目录 |
| `FIONA_TRUSTED_PROXIES` | 按 IP 限流信任的代理 IP/CIDR，逗号分隔，默认 `127.0.0.1,::1`；每次调用读取 |
| `FIONA_DAILY_OFFICIAL_EXCHANGES` | 每账号每个北京时间自然日创建官方体验次数，默认 `3` |
| `FIONA_DAILY_HOT_EXPANDS` | 每账号每天热点展开次数，默认 `30` |
| `FIONA_DAILY_CARD_DETAILS` | 每账号每天卡片详情次数，默认 `30` |
| `FIONA_DAILY_ASR` | 每账号每天语音识别次数，默认 `300` |
| `FIONA_BYOK_SECRET` | url-safe base64 编码的32字节 AES-256-GCM服务端密钥；缺失/非法整体不可用，DEV_MODE无固定回退；单独保管，不进备份 |
| `FIONA_BYOK_SECRET_PREVIOUS` | 逗号分隔的旧密钥，仅用于解密；用户下次保存使用当前密钥重新加密 |
| `FIONA_DAILY_BYOK_CHATS` | 每账号每日 BYOK 聊天默认200次（byok_chat），正整数，非法回退并只告警一次，调用时读取 |
| `FIONA_DAILY_BYOK_TESTS` | 每账号每日测试连接默认20次（byok_test），同上；本地校验失败不计次，上游连接测试计次 |
| `FIONA_BYOK_MAX_STREAMS` | 全进程 BYOK 流及专用线程池上限默认8（1–64），每用户一条；调用时读取，非法回退并只告警一次 |
| `FIONA_BYOK_TOTAL_SECONDS` | 建流起的低/中档及非 Claude 总预算默认120秒（10–240）；Claude 高档为 min(240, FIONA_BYOK_TOTAL_SECONDS×1.5)，默认180秒，均须小于 Nginx 的 300 秒；调用时读取，非法回退并只告警一次；实际中断边界见下文 |
| `FIONA_DAILY_WEATHER` | 每账号每个北京时间自然日天气查询次数，默认 `30`；正整数，非法值回落默认并只告警一次，调用时读取 |
| `FIONA_AMAP_ENABLED` | 高德地图 MCP 天气默认开启（`1`），只有字面 `0` 关闭；关闭时返回“天气服务暂未开启”，不发请求，调用时读取 |
| `FIONA_AMAP_TIMEOUT_SECONDS` | 天气 MCP 请求总预算，默认 `8` 秒，合法范围 `1–30` 的有限浮点数；空串、非数字、`nan`、`inf` 和越界值回落 `8`，调用时读取 |
| `FIONA_BACKUP_DIR` | 定时备份目录，默认 `/var/backups/fiona`，属主为 `fiona:fiona`、权限 `0700` |
| `FIONA_BACKUP_RETENTION_DAYS` | 定时备份保留天数，默认 `14`，正整数 |
| `FIONA_DEFAULT_POOL_WORKERS` | 默认线程池大小，默认 `32`，留给聊天槽位和流读取 |
| `FIONA_SLOW_POOL_WORKERS` | 慢工具、热点及卡片专用线程池大小，默认 `16` |
| `STRAWBERRY_DAILY_REFILL` | 每位用户每天（Asia/Shanghai）首次经登录、`GET /strawberry` 或聊天预扣时补到至少该数量；`0` 关闭，建议值由运维决定 |

服务器到 DashScope 的网络延迟决定危机复核超时回落的比例。上线后用下面两条命令统计同一日志时间窗口的失败次数 `failed` 和成功判级次数 `level`：

```bash
journalctl -u fiona | grep -c '\[crisis-model\] failed'
journalctl -u fiona | grep -c '\[crisis-model\] level='
```

回落比例为 `failed / (failed + level)`；`failed` 包括超时、调用出错和解析失败，规则高危直通等未调用模型的轮次不计入分母。分母为 0 时无可统计结果；回落比例超过 10% 时，考虑把 `FIONA_CRISIS_MODEL_TIMEOUT_SECONDS` 调到 `3` 秒，再观察延迟与回落比例。

图片模式默认 Qwen Image 3.0，也可选择 Seedream 5.0 Flash；登录后的 `/image-models` 只检查密钥是否配置，不探测模型权限。未开通时返回安全错误，不自动切换供应商。隐私数据流：Qwen 生图和修图将本轮描述及参考图发送给阿里云 DashScope；Seedream 将相同数据发送给字节跳动火山引擎，不发送聊天历史或私有记忆。两个图片模型每次都扣 10 颗草莓，失败照常退款。

天气隐私数据流：每次只把用户本轮或最近对话里明确说出的城市名发送给阿里云百炼托管的高德地图服务，不发送聊天历史、私有记忆或用户位置，不做 IP 定位，不使用画像城市或默认城市。失败日志只含工具名、错误类型和耗时，不记录城市名、用户原话或上游响应；上游失败只向用户显示固定中文文案。天气卡最多展示四天中文日夜预报，不提供实时温度、体感温度或湿度；卡片结构不落库，仅保留文字摘要。部署后抽查应覆盖真实高德响应、失败卡退款、缺城市追问与取消。

平台模型正常回复每条 10 颗草莓，预扣后只对已保存的平台模型回复、图片或成功真实工具结算；BYOK 普通/镜子回复不扣草莓并退还预扣，失败、追问及桌面占位工具也退还。余额 0 或不足10颗且启用BYOK时，仅自带模型聊天可继续；工具、看图、自然语言生图及显式图片模式保持草莓不足，守卫不消耗天气额度、不清pending。明确危机仍由平台回复，有余额按交付计费，余额不足时不调用回复模型、不落库、免费送资源；possible的BYOK聊天免费，失败先资源再错误。`DEV_MODE=1` 不预扣，零余额守卫为空操作。每日补给不降低较高余额，同日一次。

七个每日上限（官方体验3、热点展开30、卡片详情30、ASR300、天气30、BYOK聊天200、测试连接20）只在限流器开启且 DEV_MODE 不等于1时生效，正整数非法回退默认并只告警一次，均调用时读取；次数不额外扣草莓，原IP每分钟限流保留。官方创建用数据库事务计数，其他六项使用进程内存计数，重启清零、北京零点换日，上游失败不退还。天气追问只检查额度、本地失败和取消不计数，超限流内报错退款、不写pending；BYOK聊天并发检查后计数，超限流内报错退款，测试连接失败和每日超限均HTTP200返回ok:false，不保存草稿。官方体验、热点展开、卡片详情和ASR四类HTTP超限仍429、Retry-After及同文案detail/error/retry_after，ASR超限关闭免提。

BYOK 只接管普通/镜子聊天回复。意图、模式、危机复核、看图、工具、生图、朗读、画像提取、分身交流/官方创作搭档始终使用平台；用户模型失败不改用平台。自定义地址须公网HTTPS/443、全部DNS结果公网，连接固定IP且保留主机名SNI，不跟随重定向；代理假IP198.18.0.0/15会被拒，不提供放行开关。自定义上游每连接累计读取全部 HTTP 字节（TLS 之上），上限 4 MiB，超限立即中断并报「你的模型调用失败：连不上该服务。本条没有改用平台模型。」；预设厂商不受此字节上限影响。custom 强制请求头 Accept-Encoding: identity，拒绝非空且非 identity 的 Content-Encoding，避免解压绕过 4 MiB 上限；错误仍归「连不上该服务」。响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时。中断线程只标记状态并 shutdown socket，阻塞调用返回后由属主 worker 关闭流、客户端和连接池。测试连接的平台限流为 10 次/分钟，命中时仍以 HTTP 200 返回 ok:false 和「操作太频繁，请稍后再试」。错误固定映射新增「服务繁忙，请稍后再试」，仍不包含上游正文。以下客户端污染环境变量任一非空都会使 BYOK 整体不可用：`OPENAI_ORG_ID`、`OPENAI_PROJECT_ID`、`OPENAI_CUSTOM_HEADERS`、`OPENAI_BASE_URL`、`ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_PROFILE`、`ANTHROPIC_FEDERATION_RULE_ID`、`ANTHROPIC_IDENTITY_TOKEN`、`ANTHROPIC_IDENTITY_TOKEN_FILE`、`ANTHROPIC_CUSTOM_HEADERS`。共十一项。预设厂商（含 Claude）遵循服务器的 HTTP(S)_PROXY / NO_PROXY 出站代理设置；自定义地址不使用环境代理。`ALL_PROXY` 同样按预设 SDK 默认规则生效。

BYOK 等待上游建流或正文块期间，每 10 秒发送 SSE 注释心跳（`: thinking`），防止 Next 开发代理的 30 秒空闲超时或其他中间层切断长时间思考；取消时仍先中断上游、等待 worker 结束，再关闭并释放槽位。

Claude 思考强度可选低 / 中 / 高，默认低；聊天底栏和设置页切换立即保存到服务端账号。低、中、高的 `max_tokens` 普通/镜子分别为 4096/2048、8192/4096、16384/8192；低与中总时限为 `FIONA_BYOK_TOTAL_SECONDS`（默认 120 秒），高为 `min(240, FIONA_BYOK_TOTAL_SECONDS×1.5)`（默认 180 秒），必须小于 Nginx 的 300 秒。调高会先思考再回答，用户自己的额度消耗随档位上升；其他厂商不受影响。正文仍限普通 4000 字、镜子 600 字，测试连接固定低档/1024 tokens/原总时限。`user_model_configs` 新增 `effort TEXT NOT NULL DEFAULT 'low'`，老库启动时自动补列，已有行默认低，不新增迁移版本号，`/health` 不变；保存模型、Key 或切换厂商保留档位，只在 Claude 下生效。

零余额且已启用 BYOK、未预扣时，generate_image / weather 以外的 pending：「算了/取消/不用了/不要了/不查了/没事了」免费取消并清 pending；以「先聊/聊点/换个话题/先不」开头清 pending、由用户模型回复；其他补参消息仍报草莓不足、pending 保留。天气 pending 的「换个话题」类句子同样清 pending、由用户模型回复；余额充足用户与平台路由保持不变。

BYOK 隐私数据流：启用后，每条聊天回复会把分身设定、用户的私有长期记忆、本会话最近 60 条消息（含平台看图生成的图片描述）与本条消息发送给用户选择的厂商；系统提示中的账号名替换为「（账号已隐藏）」。危机复核、意图识别、模式判定、看图、全部工具、生图、朗读仍由平台处理并读取对话内容，画像提取仍由平台执行并会读到用户模型的回复；明确危机轮仍由平台回复。用户模型失败不改用平台模型。Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天，无服务端密钥无法解密。长期归档副本须先清除 Key 密文，步骤见部署手册。Claude 的接口不对中国大陆提供服务，大陆服务器通常无法连接该预设。

服务端密钥独立保管，不随数据库/媒体打包或提交；删除配置/删号后的加密Key在数据库备份中最多保留14天，无密钥无法解密。丢失密钥只需用户重新填Key；轮换期间用FIONA_BYOK_SECRET_PREVIOUS解旧密文，保存时用当前密钥重加密。生成命令：

```bash
python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

不要把命令输出写入仓库、聊天或工单。Claude使用官方Anthropic SDK，接口不对中国大陆提供服务；部署在大陆时需先在沙箱外核查可用性。

危机路由仅有一处天气例外：已存在天气 pending 时，到达工具路由的 `possible` 信息或求助语句清除该 pending，继续按新消息路由，不当作城市名发送给高德。高危与 `possible` 非信息语境的保护保持现状，后者保留 pending；天气失败和超限等聊天错误收尾仍先按需恰好送达一次求助资源。

可以使用下面的命令在服务器上生成 JWT Secret：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

不要把命令输出粘到聊天、工单或版本库中。

安装并构建前端：

```bash
cd /opt/fiona/frontend
npm ci
npm audit
npm run build
install -d -o fiona -g fiona -m 0700 /opt/fiona/frontend/.next/cache
```

单域名部署不应设置 `NEXT_PUBLIC_API_BASE`，让浏览器继续使用相对 `/api`。只有前端和 API 确实位于不同域名时，才在构建前设置该变量，并同时重新审计 CORS、Cookie 和 WebSocket。

## systemd

### 后端服务

创建 `/etc/systemd/system/fiona.service`：

```ini
[Unit]
Description=Fiona FastAPI backend
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=fiona
Group=fiona
WorkingDirectory=/opt/fiona/backend
EnvironmentFile=/etc/fiona/fiona.env
ExecStart=/opt/fiona/backend/.venv/bin/python /opt/fiona/backend/run.py
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ReadWritePaths=/var/lib/fiona

[Install]
WantedBy=multi-user.target
```

### 前端服务

先用 `command -v npm` 确认 npm 的绝对路径。下面示例假设为 `/usr/bin/npm`。

创建 `/etc/systemd/system/fiona-web.service`：

```ini
[Unit]
Description=Fiona Next.js frontend
After=network-online.target fiona.service
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=fiona
Group=fiona
WorkingDirectory=/opt/fiona/frontend
Environment=NODE_ENV=production
ExecStart=/usr/bin/npm run start -- -H 127.0.0.1 -p 3000
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ReadWritePaths=/opt/fiona/frontend/.next/cache

[Install]
WantedBy=multi-user.target
```

加载并启动：

```bash
systemctl daemon-reload
systemctl enable --now fiona fiona-web
systemctl status fiona fiona-web
```

代码和虚拟环境保持 root 只写；`fiona` 账号只需要读取代码，并写入 `/var/lib/fiona` 与前端缓存。API Key 文件不应由 `fiona` 写入，也不应对其他普通账号可读。

## Nginx

下面是与当前路由约定匹配的站点基线。`/api/` 的 `proxy_pass` 末尾斜杠用于移除 `/api` 前缀，因为 FastAPI 实际端点是 `/chat`、`/match` 等，而不是 `/api/chat`。

每个反代入口都必须覆盖 `proxy_set_header X-Real-IP $remote_addr`，并用 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` 追加真实对端。后端按 IP 限流只在 `request.client.host` 属于 `FIONA_TRUSTED_PROXIES` 时采信这些头；IPv4 映射的 IPv6 地址按 IPv4 比较。uvicorn 默认可能已按受信 XFF 改写 `client.host`，后端通常直接使用这个真实 IP。已知局限：若某入口只设 X-Real-IP、不追加 XFF，客户端自带的 XFF 仍可能被 uvicorn 采信，因此必须逐入口检查两个头。开发鉴权仍只看 ASGI 对端，不能用代理头开启。

```nginx
server {
    listen 80;
    server_name madchloechat.online;

    client_max_body_size 25m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /fonts/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }
}
```

`/fonts/noto-serif-sc/` 下的自托管字体切片文件固定不变，部署层以一年 `immutable` 缓存提供；`proxy_hide_header` 避免 Next.js 的 `public, max-age=0` 与该策略并存。更换字体时必须使用新的目录名，并同步更新字体 CSS 中的 URL，不能覆盖相同 URL 下已缓存的文件。首次部署后可用 `curl -I https://madchloechat.online/fonts/noto-serif-sc/noto-serif-sc-000.woff2` 核对唯一的 `Cache-Control` 值。

启用站点后先检查配置：

```bash
nginx -t
systemctl reload nginx
```

再用 Certbot 或现有证书流程启用 443 和 HTTP → HTTPS 跳转。证书配置由部署环境生成，不应把私钥提交到仓库。

## 首次验证

先验证本机进程：

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:3000/
```

再验证公网：

```bash
curl --fail https://madchloechat.online/
curl --fail https://madchloechat.online/api/health
```

然后用浏览器完成以下冒烟测试：

1. 邀请码登录。
2. 退出登录后，确认旧会话不能继续访问个人 API，再重新登录。
3. 普通流式聊天。
4. 图片消息和 `/uploads/` 访问。
5. ASR 与 TTS。
6. Plaza 页面和媒体上传。
7. 匹配卡片、双方接受和真人 WebSocket。
8. 桌面用户模式加载公网网站。
9. 设置页测试/保存/启停/删除BYOK：GET响应private,no-store且无密文/完整Key，非法Key不回显、厂商失败不返回401；Claude推荐白名单与大陆说明正确；设置页和聊天底栏的低/中/高档立即保存、跨 iframe 同步且不覆盖草稿，方向键可切换，忙碌时禁用，手机无横向溢出。
10. 普通/镜子BYOK回复气泡有标记、余额不变，切平台恢复10颗计费；失效Key、空回复、超时均不改用平台；possible先一次资源再错误、high仍平台。
11. 余额0和5的BYOK用户可聊天，工具/自然语言生图/看图被守卫且不消耗天气额度、不清pending；显式image模式保持草莓不足。
12. 抽查byok_chat默认200与byok_test默认20额度、每用户一条、全进程8条、低/中默认120秒与高默认180秒总时限；高档预算不得超过240秒且小于 Nginx 的300秒；检查非法配置回退不打印值，trace不含Key/URL/用户模型名/原文。
13. 核查服务端密钥单独保管且不进备份；轮换可解旧配置、丢失Key提示重填，删号后迟到保存不重建配置。

账户删除是破坏性操作，只能用专门创建的一次性测试账号验证。确认该账号的消息、匹配、真人消息、广场帖子、媒体文件及 user_model_configs 自带模型配置与加密Key都已删除，并检查后端日志没有文件清理失败。

`/health` 无需登录，接受 GET 和 HEAD：只读检查现有数据库及其可写权限、五道迁移和上传目录可写性，整个检查最多等待 3 秒；成功返回 `{"status":"ok"}`，失败返回 503 和检查项名称，不泄露路径、异常正文、版本或提交。它不会探测外部模型服务。原来的 `/`（公网 `/api/`）仍只是进程级检查；后端从未成功启动时 `run.py` 以退出码 3 结束，使 systemd 能按失败重启。上传清理某轮异常只记录类型，下一轮继续，关停取消照常传播。

## 日常发布

每次发布前先停止后端写入、记录当前提交并备份状态。以下命令由运维账号控制服务，以数据库属主 `fiona` 执行备份，避免 SQLite CLI 在线生成 root 属主的 `-wal`/`-shm`：

```bash
cd /opt/fiona
systemctl stop fiona
git rev-parse HEAD
sudo -u fiona env FIONA_DB_PATH=/var/lib/fiona/fiona.db \
    FIONA_UPLOADS_DIR=/var/lib/fiona/uploads FIONA_BACKUP_DIR=/var/backups/fiona \
    /opt/fiona/deploy/fiona-backup.sh
```

备份脚本内的 `umask 077` 不影响更新用 shell。后端初始化时会开启 SQLite WAL 模式。发布、日常运行和手工导出时都必须用脚本内的 `sqlite3 .backup`（或 SQLite 在线备份 API）生成一致快照，不能只复制 `fiona.db` 主文件：未检查点的已提交数据可能仍在 `fiona.db-wal`。数据库和上传目录使用同一时间戳配套保管；在线媒体 tar 与数据库快照并非跨文件系统事务，要求严格同一时点时应先停止写入再备份。不要把 `fiona.db-wal`、`fiona.db-shm` 当成可独立恢复的备份。

发布前备份也受默认 14 天保留期约束，到期会自动清理。BYOK 密文在日常数据库备份中最多保留 14 天，`FIONA_BYOK_SECRET` 及 `PREVIOUS` 须单独保管、不放入数据库或媒体备份。需要超出 14 天长期归档时，先从一致快照制作归档副本，并在另存前仅对**副本**执行：

```bash
sqlite3 <副本路径> "DELETE FROM user_model_configs; VACUUM;"
```

这会删除所有用户模型配置行并清理密文残留，确保归档副本里没有任何用户 Key 密文；不要对运行中的数据库或日常恢复备份执行。归档数据库副本和对应媒体包应一起另存到不受日常保留策略管理的目录或异地存储；脚本不清理备份目录的子目录。

然后更新、验证和重启：

```bash
cd /opt/fiona
git pull --ff-only

cd backend
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check

cd ../frontend
npm ci
npx tsc --noEmit
npm run build

systemctl restart fiona fiona-web
systemctl status fiona fiona-web
```

当前 `npm run lint` 已恢复为绿色，但仍有非阻断警告。发布者必须人工查看 Lint 输出，不能把生产构建成功等同于所有维护债务已经清零。

数据库兼容 DDL 会在后端启动时执行。既有迁移增加了 `users.session_version`、邀请码撤销/用量字段、`posts.owner_username`、`upload_cleanup_queue` 和可空列 `users.strawberry_refill_date`；兼容建表包括 `retired_usernames(username TEXT PRIMARY KEY, retired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)` 和 `user_model_configs`（加密用户Key、模型配置、启用位与 `effort TEXT NOT NULL DEFAULT 'low'`）表；后者直接在 init_db 执行DDL，紧接着用容错 ALTER TABLE 补 `effort`，老库启动时自动补列、已有行取 low，不增加迁移版本号，health与五道迁移不变，并启用持久的 WAL 模式与统一的 SQLite busy timeout。新账号初始 `session_version` 为随机正整数，旧账号版本保持原值，不强制重新登录；删号事务记录退役用户名，之后的 `testerNN` 发码跳过它。后端启动还会回填可识别的旧帖子 owner，并重试队列中的文件清理。由于当前没有通用迁移和自动回滚，任何涉及 `database.py` 的发布都必须先同时备份数据库与上传目录。

## 邀请码、会话与草莓运维

在后端目录运行本机管理命令。明确传入服务使用的环境文件；脚本会在导入数据库模块前读取它，并向 stderr 显示配置文件路径与解析后的数据库绝对路径。命令行 `--env-file` 优先于 `FIONA_ENV_FILE`；两者都未指定时默认 `backend/.env`，与服务进程一致。生产示例应显式传 `--env-file /etc/fiona/fiona.env`。进程中已设置的环境变量仍优先。运行账号必须能读取配置文件并写入实际数据库。当前示例的环境文件为 `root:root 0600`，因此用有读取权限的运维账号执行管理脚本时，应先停止 `fiona` 服务；命令结束后按下方步骤修正数据库、`-wal`、`-shm` 属主，再启动服务，避免运维账号创建的伴生文件阻止服务账号写入。若需不停服在线执行，应先提供服务账号可读的受控配置及可写的备份目的地，并以服务账号运行数据库命令。

三个脚本进入初始化路径时会执行与服务启动相同的兼容 DDL（只加列、建表或索引），并可能启用 WAL、执行旧帖 owner 回填及版本化迁移；对已有数据库运行发码、邀请码管理或草莓 `grant/set`，即使未传 `--init-db` 也会进入此路径。请先用 `.backup` 备份数据库、同时备份媒体，再运行这些命令。`manage_strawberries.py list` 默认跳过初始化与迁移，以只读连接查看库内原始余额和最近补给日期，不触发每日补给；显式传 `--init-db` 时则会初始化数据库。`grant`、`set` 先应用当日补给再修改余额。

```bash
cd /opt/fiona/backend
.venv/bin/python seed_invites.py 10 --env-file /etc/fiona/fiona.env
.venv/bin/python manage_invites.py list --env-file /etc/fiona/fiona.env
.venv/bin/python manage_invites.py revoke ABCD2345 --env-file /etc/fiona/fiona.env
.venv/bin/python manage_invites.py rotate ABCD2345 --env-file /etc/fiona/fiona.env
.venv/bin/python manage_strawberries.py list --env-file /etc/fiona/fiona.env
.venv/bin/python manage_strawberries.py grant tester01 50 --env-file /etc/fiona/fiona.env
.venv/bin/python manage_strawberries.py set tester01 200 --env-file /etc/fiona/fiona.env
```

以上为独立操作示例，并非要依次执行所有命令。使用运维账号执行任一数据库操作后，在重新启动服务前检查并修正属主：

```bash
for db_file in /var/lib/fiona/fiona.db /var/lib/fiona/fiona.db-wal /var/lib/fiona/fiona.db-shm; do
    if [ -e "$db_file" ]; then chown fiona:fiona "$db_file"; fi
done
systemctl start fiona
```

数据库文件不存在时，管理脚本以退出码 2 拒绝操作，不会创建空库；仅首次初始化新库时使用 `--init-db`。`seed_invites.py` 每次只输出本次新建的码及其用户名，用户名编号取已存在用户、邀请码绑定名和退役用户名的最大 `testerNN` 编号之后，删号不会回收编号。`grant` 增加 1–100000 颗，`set` 将余额设为 0–100000；不存在的用户名返回退出码 1。

撤销和轮换会使绑定账号当前所有 JWT 失效，操作前应确认目标用户名；发码和轮换命令会打印新码，应只通过受控渠道发给对应测试者。邀请码仍可重复用于登录，因此不应公开写入日志、工单或群聊。

## 日志与故障排查

### 本地分身预览

当前本地分身数据已从临时测试目录保存到 `backend/local-avatar.db`，上传文件在 `backend/uploads/local-avatar/`。这些数据及 `backend/.env.local` 均被 Git 忽略。保留原有登录签名与账号，因此切回真实模型无需重设分身。

在 `backend` 目录执行 `.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --env-file .env.local`。此入口使用真实模型，没有固定回复；`backend/.env` 提供模型凭据，显式启动环境优先。该本地环境保留开发鉴权，仅绑定回环地址，不用于线上部署。

模型返回 `Arrearage` 时，检查 API Key 所属阿里云账号的欠费状态；恢复服务后可直接重试，无需重新设置分身。模型调用失败会显示错误，不保存虚构的分身回复。

### 服务日志

```bash
journalctl -u fiona -n 200 --no-pager
journalctl -u fiona-web -n 200 --no-pager
journalctl -u fiona -f
journalctl -u fiona-web -f
```

常见检查顺序：

1. `systemctl status` 是否显示进程存活。
2. 本机 8000 和 3000 是否可访问。
3. `nginx -t` 和 Nginx error log。
4. `/etc/fiona/fiona.env` 是否缺少 Key，且权限是否为 `0600`。
5. `/var/lib/fiona/fiona.db` 和 `/var/lib/fiona/uploads/` 是否只允许服务账号写入。
6. SSE 是否被代理缓冲，WebSocket Upgrade 头是否保留。
7. DashScope 或外部热点源是否发生超时/额度问题。

## 定时备份

仓库 `deploy/fiona-backup.sh` 使用 SQLite `.backup` 在线生成一致数据库快照，转为独立的非 WAL 文件并要求 `PRAGMA integrity_check` 为 `ok`，再打包上传目录，排除点开头的文件。两份备份共用 UTC 时间戳和进程号，媒体 tar 固定带 `uploads/` 前缀；脚本全程 `umask 077`，成品权限 `0600`。失败时非零退出并清理临时文件和未完成配对；GNU tar 因打包期间文件变化返回 1 时会明确告警，并保留已验证的数据库快照及已生成的媒体包，此媒体包可能不完整，需重新备份。默认仅清理备份目录第一层中本脚本命名的、达到 14 个完整 24 小时的旧备份，不递归删除子目录。

备份必须以数据库属主账号 `fiona` 运行；脚本拒绝不同属主账号，避免在线库旁生成 root 属主的 `-wal`、`-shm`。备份目录设为 `fiona:fiona 0700`，不能由 Nginx 暴露。安装脚本和两个 unit：

```bash
install -d -o fiona -g fiona -m 0700 /var/backups/fiona
install -o root -g root -m 0755 /opt/fiona/deploy/fiona-backup.sh /usr/local/sbin/fiona-backup
install -o root -g root -m 0644 /opt/fiona/deploy/fiona-backup.service /etc/systemd/system/fiona-backup.service
install -o root -g root -m 0644 /opt/fiona/deploy/fiona-backup.timer /etc/systemd/system/fiona-backup.timer
```

仓库 service 默认直接调用 `/opt/fiona/deploy/fiona-backup.sh`。若使用上面安装到 `/usr/local/sbin` 的副本，可用 drop-in 指向它：

```bash
install -d -o root -g root -m 0755 /etc/systemd/system/fiona-backup.service.d
cat > /etc/systemd/system/fiona-backup.service.d/exec.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/local/sbin/fiona-backup
EOF
systemctl daemon-reload
systemctl enable --now fiona-backup.timer
systemctl start fiona-backup.service
systemctl list-timers fiona-backup.timer
journalctl -u fiona-backup -n 100 --no-pager
```

timer 每天北京时间 04:00 执行，`Persistent=true` 补跑错过的任务。systemd 读取 `/etc/fiona/fiona.env` 后以 `fiona` 执行；数据库、上传与备份目录分别由 `FIONA_DB_PATH`、`FIONA_UPLOADS_DIR`、`FIONA_BACKUP_DIR` 覆盖，`FIONA_BACKUP_RETENTION_DAYS` 覆盖保留天数。若改到默认目录以外，还须用 service drop-in 扩充 `ReadWritePaths`，确保目录属主和权限匹配。

每次备份成功后，用受控运维账号通过 SSH 加密传输（`scp` 或 `rsync`）把同时间戳的数据库和媒体包一起拷到服务器以外；目的端目录和文件分别保持 `0700`、`0600`，另设异地保留策略并定期取回演练。不要把模型密钥、JWT Secret 或真实备份地址写进仓库。

## 旧备份恢复演练

全程只操作副本，不启动任何服务。绝不能拿唯一一份备份直接启动后端：启动不仅迁移，还会把进行中的交流改为停止、结算未决调用，并按清理队列删上传文件。以下先把两个同时间戳备份复制到演练目录；将时间戳替换成真实备份名：

```bash
backup_db=/var/backups/fiona/fiona-db-YYYYMMDDTHHMMSSZ-PID.sqlite3
backup_media=/var/backups/fiona/fiona-uploads-YYYYMMDDTHHMMSSZ-PID.tar.gz
rehearsal=/var/lib/fiona/restore-rehearsal
install -d -o fiona -g fiona -m 0700 "$rehearsal" "$rehearsal/uploads"
install -o fiona -g fiona -m 0600 "$backup_db" "$rehearsal/fiona.db"
install -o fiona -g fiona -m 0600 "$backup_media" "$rehearsal/uploads.tar.gz"
sudo -u fiona sqlite3 -readonly "$rehearsal/fiona.db" 'PRAGMA integrity_check;'
sudo -u fiona sqlite3 -readonly "$rehearsal/fiona.db" '.schema'
cd /opt/fiona/backend
.venv/bin/python migrate.py --env-file /etc/fiona/fiona.env --db "$rehearsal/fiona.db"
```

`.schema` 只输出结构，`migrate.py` 默认再复制演练库及存在的 `-wal`、`-shm` 到临时目录，仅调用 `database.init_db()`，打印迁移前后版本、列和行数，退出后删除临时副本；缺库退出 2，不创建新库。若备份是旧式原始三文件，先在离线、稳定的副本中保全主库和两个伴生文件，再演练，不能在仍持续写入的库上用逐文件复制取代一致性备份。

提示「没有归属用户的消息」时，在演练副本中先只统计：

```bash
sudo -u fiona sqlite3 -readonly "$rehearsal/fiona.db" \
    'SELECT COUNT(*) FROM messages m WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.username=m.username);'
```

此类旧消息会使第①道迁移失败。由作者在受控环境核对归属，不能自动新建虚构用户、猜测归属或写入迁移成功标记。确有可恢复用户时，先从可信同时间点数据恢复其用户记录；无法确定归属时，在另一份受保护副本中留存待核对数据。只有作者确认可删除孤立消息后，才可在当前演练副本执行下面的删除并重新演练；它不会影响保留的原始备份：

```bash
sudo -u fiona sqlite3 "$rehearsal/fiona.db" \
    'DELETE FROM messages WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.username=messages.username);'
.venv/bin/python migrate.py --env-file /etc/fiona/fiona.env --db "$rehearsal/fiona.db"
```

演练成功后，才把迁移应用到演练库本身，恢复和清理演练媒体：

```bash
.venv/bin/python migrate.py --env-file /etc/fiona/fiona.env --db "$rehearsal/fiona.db" --in-place
chown -R fiona:fiona "$rehearsal"
tar -tzf "$rehearsal/uploads.tar.gz"
sudo -u fiona tar -xzf "$rehearsal/uploads.tar.gz" -C "$rehearsal/uploads" --strip-components=1
FIONA_UPLOADS_DIR="$rehearsal/uploads" .venv/bin/python scripts/strip_upload_metadata.py --env-file /etc/fiona/fiona.env --dry-run
FIONA_UPLOADS_DIR="$rehearsal/uploads" .venv/bin/python scripts/strip_upload_metadata.py --env-file /etc/fiona/fiona.env --apply
chown -R fiona:fiona "$rehearsal"
sudo -u fiona sqlite3 -readonly "$rehearsal/fiona.db" 'SELECT version FROM schema_migrations ORDER BY version;'
sudo -u fiona sqlite3 -readonly "$rehearsal/fiona.db" 'PRAGMA integrity_check;'
```

归档先盘点并确认只含可信的 `uploads/` 树，`--strip-components=1` 把这个前缀移除，落到与 `FIONA_UPLOADS_DIR` 对齐的演练目录。清理脚本仅处理旧广场文件和聊天图片，默认只读；显式 `--apply` 才原子改写，跳过生成图、参考图、点文件、符号链接和已经没有待清理元数据的图片，保留原权限位。单文件失败会跳过并计数，`--apply` 有失败时整批非零退出，必须同时核对退出码和失败数后再决定实际恢复步骤。不要把演练目录直接替换生产目录。

恢复前还须了解：旧广场匿名 ID 由 `JWT_SECRET` 派生。更换 Secret 后，旧 HMAC 匿名 ID 和依赖它的归属回填会失效；已有 owner 字段仍可用于归属，旧 MD5 别名只在实际匹配到时提供兼容。应先在受控副本中用匹配的旧 Secret 核对回填结果，再决定换密钥方案；旧 Secret 不进入备份包或仓库。

## 监控与告警

从服务器以外的拨测服务，或另一台机器上的 cron，定时用 **GET** 访问 `https://<域名>/api/health`，以便同时核对响应体。用 HTTP 非 2xx、连接失败或超时触发通知；例如 cron 每分钟执行 `curl --request GET --fail --silent --show-error --max-time 10 https://<域名>/api/health` 并把失败交给该机器已有的邮件/通知机制。应用不接入第三方监控服务，也不在 `/health` 中调用 DashScope、DeepSeek。

```bash
journalctl -u fiona -u fiona-web -u fiona-backup -n 200 --no-pager
systemctl --failed
```

可在 `fiona.service`、`fiona-web.service` 和 `fiona-backup.service` 的 `[Unit]` drop-in 中设置 `OnFailure=fiona-alert@%n.service`，由作者配置对应的通知 oneshot unit；凭据放在受控环境文件，不写进仓库。后端启动失败退出 3、备份步骤失败非零退出，便于 systemd 记录 failed 并触发通知。发布前由作者手动在 **DashScope、DeepSeek 和火山引擎控制台设置消费告警**，并确认通知接收人和阈值。

systemd < 254 时，服务自动重启期间不会进入 failed 状态。仅设 `RestartSec=3` 可能一直重启，无法触发 `OnFailure`。在自动重启的后端和前端 unit 的 `[Unit]` 中配置 `StartLimitIntervalSec=300`、`StartLimitBurst=5`，限制 300 秒内最多启动 5 次，后续重试被拒绝后进入 failed；用 `systemctl daemon-reload` 应用配置，再在目标机验证启动失败通知。外部 GET 拨测仍须独立启用。

## 回滚与恢复

代码回滚应使用发布前记录的提交或正式发布标签，重新安装依赖、重新构建前端，再重启两个服务。不要只恢复 `.next` 目录。

如果新版本已经改变 SQLite schema，应优先把备份恢复到 `/var/lib/fiona/fiona.db`，再启动旧代码；同时恢复匹配时间点的 `/var/lib/fiona/uploads/` 备份，避免消息记录和文件不一致。

恢复前先停后端：

```bash
systemctl stop fiona
```

确认没有其他进程仍在使用旧库，检查 `/var/lib/fiona/` 下是否残留 `fiona.db-wal`、`fiona.db-shm`。若要保全旧库中尚未检查点的数据，**先对旧库**执行 `PRAGMA wal_checkpoint(TRUNCATE)`，必要时再用 `.backup` 另存旧库；若确定只需要恢复到既有快照时间点，可跳过旧库检查点。两种情况都要在覆盖主文件前删除旧 `-wal` 和 `-shm`。SQLite 否则可能把旧 WAL 帧回放到恢复后的主文件，带回备份时间点之后的数据或造成损坏。

若要保全旧库未检查点的数据，先运行以下检查点命令：

```bash
ls -l /var/lib/fiona/fiona.db /var/lib/fiona/fiona.db-wal /var/lib/fiona/fiona.db-shm 2>/dev/null || true
sudo -u fiona sqlite3 /var/lib/fiona/fiona.db "PRAGMA wal_checkpoint(TRUNCATE)"
```

如需留存回滚前状态，在覆盖旧库之前另存一份权限为 0600 的快照；备份命令在子 shell 内设 umask，不影响恢复后的操作：

```bash
( umask 077; sudo -u fiona sqlite3 /var/lib/fiona/fiona.db ".backup '/var/backups/fiona/pre-rollback-$(date +%Y%m%d-%H%M%S).db'" )
```

核对要恢复的快照文件和目标路径后执行以下步骤；把示例快照名换成实际已验证的 `.backup` 文件。`PRAGMA integrity_check` 必须输出 `ok`，并确认数据库及新生成的伴生文件属主为 `fiona:fiona`，才可启动旧代码：

```bash
rm -f /var/lib/fiona/fiona.db-wal /var/lib/fiona/fiona.db-shm
install -o fiona -g fiona -m 0600 /var/backups/fiona/fiona-db-YYYYMMDDTHHMMSSZ-PID.sqlite3 /var/lib/fiona/fiona.db
sudo -u fiona sqlite3 /var/lib/fiona/fiona.db "PRAGMA integrity_check"
ls -l /var/lib/fiona/fiona.db /var/lib/fiona/fiona.db-wal /var/lib/fiona/fiona.db-shm 2>/dev/null || true
```

继续保持停服。核对同一时间戳媒体包只含可信的 `uploads/` 树后，先把当前上传目录另存，再恢复媒体。以下 `saved_uploads` 必须使用一个尚不存在的目录名：

```bash
backup_media=/var/backups/fiona/fiona-uploads-YYYYMMDDTHHMMSSZ-PID.tar.gz
saved_uploads=/var/lib/fiona/uploads-pre-restore-YYYYMMDDTHHMMSSZ
tar -tzf "$backup_media"
mv /var/lib/fiona/uploads "$saved_uploads"
install -d -o fiona -g fiona -m 0700 /var/lib/fiona/uploads
sudo -u fiona tar -xzf "$backup_media" -C /var/lib/fiona/uploads --strip-components=1
cd /opt/fiona/backend
install -o fiona -g fiona -m 0600 /dev/null /var/lib/fiona/restore-media.env
sudo -u fiona env FIONA_UPLOADS_DIR=/var/lib/fiona/uploads \
    .venv/bin/python scripts/strip_upload_metadata.py --env-file /var/lib/fiona/restore-media.env --dry-run
sudo -u fiona env FIONA_UPLOADS_DIR=/var/lib/fiona/uploads \
    .venv/bin/python scripts/strip_upload_metadata.py --env-file /var/lib/fiona/restore-media.env --apply
```

清理必须以服务账号对**生产**上传目录执行，并在启动服务前完成。此脚本仅需显式指定的上传目录，用临时的空环境文件避免服务账号读取仅 root 可读的密钥配置。核对 dry-run 盘点、apply 退出码以及失败数为 0；有失败就保持停服并处理。成功后删除 `/var/lib/fiona/restore-media.env`。旧上传权限会被保留，核对权限后以服务账号执行 `find /var/lib/fiona/uploads -type f -exec chmod 0600 {} +`，使恢复文件仅由后端提供静态访问。随后再启动服务、检查日志并跑完整冒烟测试。生产数据库恢复属于破坏性操作，不应在没有确认备份的情况下临时尝试。

## 发布前安全检查

- `DEV_MODE=0`，`JWT_SECRET` 不是开发默认值。
- HTTPS 正常，登录响应的 `fiona_token` Cookie 带 `Secure`、`HttpOnly` 和 `SameSite=Lax`；HTTP/WebSocket URL 中没有 Token。
- `/etc/fiona/fiona.env`、`/var/lib/fiona` 和备份目录不可被 Nginx 静态暴露。
- 未登录访问 `/api/docs`、`/api/openapi.json` 返回 404（`DEV_MODE=0` 时后端关闭 API 文档），`/api/hot/expand` 返回 401（后端始终要求登录）；无需 Nginx 额外配置。
- Nginx 请求体、连接、速率和超时限制符合当前容量。
- 已检查所有反代入口覆盖 X-Real-IP 并追加 X-Forwarded-For，`FIONA_TRUSTED_PROXIES` 只包含真实代理。
- 已演练旧备份迁移和媒体恢复，启用定时备份与异地保存，确认外部 `/api/health` 拨测与 systemd 失败通知。
- 作者已在 DashScope、DeepSeek 和火山引擎控制台手动设置消费告警，确认阈值和接收人。
- 桌面端发布前已完成 Tauri capability、URL opener 和 CSP 整改。
- 已处理 [PLAN.md](../PLAN.md) 中所有标为“发布阻断”的项目。
- 已用一次性测试账号验证完整账户删除和失败文件清理重试。
- 已确认成人内容、未成年人和危机干预政策与代码一致。

## 下线记录

**2026-09-25**：作者确认原线上服务器已关闭。下线方案为“先备份，再删除服务、数据与密钥”，包括以下步骤：

1. 停止服务后，备份 SQLite、上传目录和历史备份，并拷贝到服务器以外保存。备份存放位置不记录在仓库中；备份不包含 `/etc/fiona/fiona.env`。
2. 删除 `fiona`、`fiona-web` 两个 systemd 服务、Nginx 站点、TLS 证书、代码目录、`/var/lib/fiona`、`/etc/fiona`、`/var/backups/fiona` 以及 `fiona` 服务账号。

截至 2026-10-04，记录更新如下；作者确认项仍在仓库之外处理：

- 域名 `madchloechat.online`：2026-10-04 公共 DNS 已查不到解析记录。
- **待作者确认**：通知测试者卸载已安装的 Windows 桌面端。用户模式仍加载 `https://madchloechat.online`，远程 capability 仍对该域名开放两个外链命令（见 `desktop/src-tauri/capabilities/remote-links.json`）；若放弃此域名，重新发布时需同时更换默认地址和 capability 白名单。
- **待作者确认**：在 DashScope、DeepSeek 后台删除本项目使用的旧 API Key。

重新上线时，按本文“首次安装”一节重新部署，并用新的 `JWT_SECRET` 和新的模型密钥。
