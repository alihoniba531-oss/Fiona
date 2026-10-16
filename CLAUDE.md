# Fiona / Chloe 开发上下文

个人 AI 分身交流与 Skill 平台，当前第一阶段支持独立分身和持久私有会话，用于作者自用和受控小范围内测。分身互聊与 Skill 交易尚未实现。完整说明见 `README.md`，实际数据流见 `docs/ARCHITECTURE.md`，当前风险和路线图见 `PLAN.md`。

## 当前架构

- `backend/`：FastAPI + SQLite `fiona.db`，入口 `main.py`，通过 `run.py` 监听 `127.0.0.1:8000`。
- `frontend/`：Next.js 16.2.6 App Router + React 19，开发端口 3000。
- `desktop/`：Tauri 2 Windows 壳；有配置时建 SSH 隧道，无配置时加载 `https://madchloechat.online`（线上服务已于 2026-09-25 下线，该地址当前不可用）。
- 模型：DashScope/Qwen；主力 `qwen3.8-omni-flash`，轻量 `qwen3.8-flash`，图片 `qwen-vl-max`，搜索、旅行规划、热点展开和卡片详情 `qwen-plus`，语音使用 Qwen ASR 和 DashScope TTS。这四项走 DashScope 原生接口并强制联网搜索，固定 30 秒 socket 超时、不重试，不受兼容客户端的 `DASHSCOPE_TIMEOUT_SECONDS` / `DASHSCOPE_MAX_RETRIES` 控制；卡片详情路由外层另有 45 秒总超时。热点分类使用 `qwen3.8-flash`，请求固定 8 秒超时、不重试。聊天生图工具默认火山方舟 Seedream 5.0 Flash；面板生图和修图默认 Qwen Image 3.0，也可选 Seedream；两者均扣 10 颗草莓，后者将描述和参考图发送给字节跳动火山引擎。
- 天气：独立 `weather` 意图，使用阿里云百炼托管的高德地图 MCP（Amap Maps）；需在百炼控制台开通，复用 `DASHSCOPE_API_KEY`，目前限时免费，结束后按量计费，单价以控制台为准。每次只向该服务发送用户明确说出的城市名，不发送聊天历史、私有记忆或用户位置，不做 IP 定位、不默认城市。
- 数据：SQLite、`backend/uploads/`、`backend/.env` 都是本机/单机状态，不进入 Git。

## Claude 智能体模式

Claude 智能体模式仅在 `FIONA_CLAUDE_AGENT` 开启、普通 `chat` 请求、危机级别为空、BYOK 已启用且 `provider == "anthropic"`、配置无错误且未触发 `byok_unreserved` 的余额守卫时进入。零余额用户保持原路由；high 和 possible 危机轮不进入智能体模式，生图/修图面板保持现状。`FIONA_CLAUDE_AGENT` 默认 `1`，每轮读取，只有字面 `0` 关闭，其他非法值按开启并只告警一次；关闭后 Claude 保留原生单轮生图路径。

Claude 自己决定天气、旅行、路线、热榜和生图工具，可以把工具结果回灌后继续调用或作答；不走平台意图识别或生图判断器。本轮有图时直接 friend，不调用平台模式判定或视觉模型；无图时仍判定模式，镜子模式不带工具。本轮图片和工具结果发送给 Anthropic；联网搜索和网页读取由 Anthropic 执行，按其价格计入用户额度。提示前缀使用 ephemeral 缓存，本轮北京时间随 user 消息发送。

计费每轮仅预扣一次 10 颗草莓，不追加扣费：至少交付一张 `error=false` 且 `stale=false` 的平台工具卡，或生图成功，先累加计费项，整轮落库成功后才结算；后续工具失败不撤销已成立的计费。未落库的计费项退款，包括会话被删、保存失败或客户端断开；未保存的生成图会清理。否则全额退款。纯文字、Anthropic 联网搜索和 Claude 直接看图使用用户自己的 Key，不扣草莓；每日 `byok_chat` 在拿到首个全局槽后才计数，每轮仅计一次。

天气只匹配本轮用户原文或最近 3 条 user 消息原文，同时比较原文及其规范化结果。Claude 提供的城市可使用原样、规范化结果和去掉一个末尾行政后缀（市、省、区、县、州、盟、自治州、特别行政区）的写法，候选至少 2 个字，单字拒绝；实际查询使用匹配到的主人原文写法，再经 normalize_city 处理。北京/北京市、那曲市天气/那曲均可匹配。没有匹配就先询问城市，记忆、system、图片摘要和位置都不参与，也不在日志或 trace 记录城市/工具参数。

上限为每轮 4 次客户端工具、默认 240 秒整轮预算、可见文字累计 8000 字（单次仍限 4000 字）、每轮一张图。`FIONA_CLAUDE_AGENT_TOTAL_SECONDS` 默认 `240`，合法范围 `60–290` 秒，非法值回落默认；每次请求时限取剩余预算与现有 BYOK 时限的较小值。整轮保持每用户锁，Claude 请求期间才占全局槽，工具执行释放全局槽并发送心跳；重新获取槽最多等 10 秒。

本轮图片只处理发给 Claude 的副本：小图原样发送；长边超过 2000 像素或原始字节超过 3.5MB 时，在后台线程等比缩放到长边不超过 2000 像素。有透明通道的 PNG 保留 PNG，其他图片转 JPEG、质量 85；处理后仍超过 3.5MB 则继续缩小尺寸，media_type 与实际编码一致，上传落盘文件不变。

工具生图失败通过 image_failed 状态清除生成提示，失败原因回灌 Claude 后继续正常作答；工具来源的 done 不因缺图报错，面板生图及其重试行为保持原样。多步两段文字之间加两个换行，同样保存到正文。工具异常累加到 agent_tool_errors，成功保存的整轮仍执行画像提取等后续任务；模式判定、pending 或会话确认等平台侧失败沿用平台文案。尚未交付任何文字、平台卡片或图片就请求失败时，不补发来源卡，也不落库。全局槽等待超时显示「自带模型通道繁忙，请稍后再试」；预算耗尽时，完成的图片必须落库或清理，不能留下孤立文件。

已知局限：历史图片不再发送原图，仅发送「［图中：摘要］」文字；镜子模式不带工具；危机轮不进入智能体模式；卡片不落库，刷新后仅保留正文摘要和生成图。进入智能体路径即清除 pending，不读写工具补参；本轮只保存一条 assistant，按文字、卡片摘要和生图描述的交付顺序拼接。服务器端工具版本、结果块类型和 `usage.server_tool_use` 字段仍需作者用真实 Key 核实。

## 聊天模型调用生图工具

以下判断器/原生单轮生图说明适用于智能体模式之外的路由；Claude 启用智能体模式时按上节的多步工具流程执行。

`FIONA_CHAT_IMAGE_TOOL` 默认 `1`，只有字面 `0` 关闭，每次调用时读取；其他非法值按开启处理并只告警一次。仅普通 chat、无本轮图片、非 high/possible 危机、未触发零余额守卫且 BYOK 配置正常时启用新生图流程，不再按回复模型白名单排除。关闭开关或判断器不可用时退回旧路由，仍跟随面板选择。危机轮不经新路径生图；possible 信息/求助语境的生图 pending 沿用旧路由，可能清除；非信息语境的 possible 轮保留生图 pending。

两种模式：**原生工具模式 native** 仅用于关闭智能体模式的 BYOK Claude 三个型号及 DeepSeek 精确型号 `deepseek-v4-pro` / `deepseek-flash`，由用户模型根据完整对话调用 `generate_image`。**判断器模式 planner** 用于平台主力/轻量槽、BYOK DashScope（所有型号）、Moonshot/Kimi、智谱、自定义地址及 DeepSeek 其他型号。Kimi、智谱、自定义地址改走判断器模式，回复模型不下发任何工具；平台 `stream_normal` 恢复原 700 token 文字回复。

判断器使用平台轻量模型 `qwen3.8-flash`：本轮预筛命中画图/图片/风格/提示词/模型名等线索或现有显式生图候选、上一条回复与生图相关，或存在待补充的生图请求时，这一轮会多一次约 1–5 秒的判断器调用。已有生图 pending 的取消短语不调用判断器，沿用原取消逻辑。判断器读取最近 6 条对话（含本轮原话，历史每条最多 600 字，本轮原话最多 1500 字（超长时保留首尾）），以「主人：」「你：」前缀按时间排列，发送给阿里云 DashScope；历史 assistant 的「使用的描述」行保留。不传人设或私有记忆。非流式 JSON、关闭思考、600 tokens、在线程执行、8 秒总超时，不重试；超时、异常、非 JSON、非法 draw 或要画时描述为空/超长均判为不可用。判断器不可用时退回旧路由；日志和 trace 不写对话或描述。

判断器判为要画时先清除所有 pending，再直接执行生图，不调用回复模型、意图识别或模式判定，也不消耗 `byok_chat` 次数、不发回复模型标签；判断器模式下镜子模式也能生图。判为不画或未满足判断器调用条件时跳过自然语言生图候选，不新建生图 pending，已有生图 pending 除取消外清除后继续；天气 pending、镜子与其他工具仍按原逻辑，意图识别的 `generate_image` 视为无意图。原生模式候选确认后绕过镜子进入带工具的 friend 回复，非候选镜子回复不下发工具。

两种模式每轮最多一张图，执行后直接结束，不把结果回灌给回复模型；完成文字及「使用的描述」行合在一条 assistant 正文落库，原生模式保留前导文字，判断器模式没有前导文字，刷新及下一轮仍可见。描述行不进入朗读缓冲。新路径忽略面板 `image_model`，默认 Seedream 5.0 Flash；点名千问/通义/Qwen 用 Qwen Image 3.0。选中模型未配置而另一个可用时，发请求前降级并说明；已发请求失败不跨供应商重试。面板生图/修图完全不变，默认 Qwen、按用户选择。成功扣 10 颗、失败退款，BYOK 文字仍免费，每轮不重复预扣。

隐私：判断器读取的最近对话发给阿里云 DashScope；原生模式由用户自选的 Claude 或上述 DeepSeek 型号决定何时生图、撰写描述。两种模式默认把根据对话撰写的描述发送给字节跳动火山引擎，描述可能包含对话里出现过的内容；描述不得含账号名、真实姓名、私有记忆里的个人细节。图片仍由平台执行并扣草莓；Qwen 描述发送给阿里云 DashScope，面板路径只发送本轮描述和所选参考图。

时限：Nginx `proxy_read_timeout` 按两次读之间的间隔计算，BYOK 等待和生图期间每 10 秒有一次心跳。原生模式最坏耗时为 BYOK 首轮（默认 120 秒或高档 180 秒）加生图 150 秒；生图在 BYOK 流关闭并释放并发槽后执行，不计入 BYOK 总时限。判断器模式先最多 8 秒判断，再执行最多 150 秒生图；判为不画才调用回复模型。

已知局限：原生模式下镜子非候选句不出图，其他工具意图仍优先；判断器模式由判断器先裁决，判为不画才进入天气、搜索等意图路由。Qwen 的 `prompt_extend` 会改写描述，显示描述不等于最终渲染所用描述；「改成动漫风」是重新生成新图，不保留原图构图，修改已有图应点「以此图修改」；已配置 Key 但 Seedream 未开通时，每次都会失败并提示「用千问画」。

## 核心模块

- 聊天主流程：`backend/routers/chat.py`、`backend/services/chat_service.py`；Claude 多步调度：`backend/services/claude_agent.py`
- 每用户聊天模型：`backend/byok/` 加密配置、SSRF 防护、OpenAI/Anthropic 流适配；`backend/routers/chat_model.py` 提供登录后配置与连接测试。普通/镜子回复接管；原生模式由关闭智能体模式的 Claude 与两个精确 DeepSeek 型号决定生图，其余使用平台判断器，平台执行图片；high、辅助模型、其他工具、TTS、画像提取及分身交流/官方搭档不变。
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
- 生产私聊实际交付的平台模型回复、图片或成功工具结算 10 颗草莓，并发预扣原子化；BYOK 纯文字回复不扣草莓并退还预扣，工具图成功时结算原预扣，余额不足但已启用 BYOK 时只允许自带模型聊天，工具/看图/生图仍返回草莓不足。`STRAWBERRY_DAILY_REFILL` 默认关闭，可按 Asia/Shanghai 自然日补到下限。`DEV_MODE=1` 跳过预扣，零余额守卫为空操作。
- 官方体验不扣草莓。聊天与工具的七项每日上限为官方体验 3、热点展开 30、卡片详情 30、ASR 300、天气 30、自带模型聊天 200、测试连接 20；后两项分别由 `FIONA_DAILY_BYOK_CHATS`（`byok_chat`）、`FIONA_DAILY_BYOK_TESTS`（`byok_test`）配置。配置均调用时读取，只接受正整数，非法值回落默认并只告警一次；开发模式或关闭限流器时跳过。官方创建用数据库事务计数，热点展开、卡片详情、ASR、天气分别沿用 `FIONA_DAILY_HOT_EXPANDS`、`FIONA_DAILY_CARD_DETAILS`、`FIONA_DAILY_ASR`、`FIONA_DAILY_WEATHER`；其余六项使用单进程内存计数，重启清零、北京零点换日，上游失败不退还次数。BYOK 聊天先检查并发，再计每日次数；超限在流内报错、退款，测试连接超限仍用 HTTP 200 返回 `ok:false`。 天气缺参追问只检查额度，取消和本地校验失败不计数；天气超限返回聊天错误事件、不写 pending、不扣草莓，成功天气卡才按普通工具结算。
- `FIONA_AMAP_ENABLED` 默认 `1`，只有字面 `0` 关闭；`FIONA_AMAP_TIMEOUT_SECONDS` 为天气 MCP 请求总预算，默认 `8` 秒，合法范围 `1–30`，非有限值、空串、非数字和越界值回落 `8`；均在调用时读取。固定 MCP 端点不能由环境变量覆盖。
- BYOK 隐私：启用后，每条聊天回复会把分身设定、用户的私有长期记忆、本会话最近 60 条消息（含平台看图生成的图片描述）与本条消息发送给用户选择的厂商；系统提示中的账号名替换为「（账号已隐藏）」。危机复核、工具执行、图片执行及朗读仍由平台处理并读取对话内容；智能体模式之外的意图识别、模式判定和看图也由平台处理；原生模式由关闭智能体模式的 Claude 或两个精确 DeepSeek 型号决定生图，其他 BYOK 使用平台判断器读取最近 6 条对话（历史每条最多 600 字，本轮原话最多 1500 字（超长时保留首尾）），画像提取也仍由平台执行，并会读到用户模型的回复；明确危机轮仍由平台回复。用户模型失败不改用平台模型。Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天，无服务端密钥无法解密。长期归档副本须先清除 Key 密文，步骤见部署手册。Claude 的接口不对中国大陆提供服务，大陆服务器通常无法连接该预设。
- BYOK 运行边界：自定义上游响应上限 4 MiB。custom 强制请求头 Accept-Encoding: identity，拒绝非空且非 identity 的 Content-Encoding，避免解压绕过 4 MiB 上限；错误仍归「连不上该服务」。响应头到达后，所有厂商在总时限或取消时立即中断；上游在返回响应头之前挂起时，预设厂商最多再等 60 秒读超时，custom 在 TLS 建立后立即中断；DNS 解析与 TCP/TLS 建连阶段分别最多等约 5 秒和 60 秒连接超时。中断线程只标记状态并 shutdown socket，阻塞调用返回后由属主 worker 关闭流、客户端和连接池。测试连接的平台限流为 10 次/分钟，命中时仍以 HTTP 200 返回 ok:false 和「操作太频繁，请稍后再试」。Claude 过载显示固定「服务繁忙，请稍后再试」。零余额且已启用 BYOK、未预扣时，generate_image / weather 以外的 pending：「算了/取消/不用了/不要了/不查了/没事了」免费取消并清 pending；以「先聊/聊点/换个话题/先不」开头清 pending、由用户模型回复；其他补参消息仍报草莓不足、pending 保留。天气 pending 的「换个话题」类句子同样清 pending、由用户模型回复；余额充足用户与平台路由保持不变。付费执行在清 pending 前检查余额。
- Claude 思考强度可选低 / 中 / 高，默认低；聊天底栏和设置页切换立即保存到服务端账号。低、中、高的 `max_tokens` 普通/镜子分别为 4096/2048、8192/4096、16384/8192；低与中总时限为 `FIONA_BYOK_TOTAL_SECONDS`（默认 120 秒），高为 `min(240, FIONA_BYOK_TOTAL_SECONDS×1.5)`（默认 180 秒），Nginx 的 300 秒是两次读之间的间隔，并非整轮总时限。调高会先思考再回答，用户自己的额度消耗随档位上升；其他厂商不受影响。单次请求正文仍限普通 4000 字、镜子 600 字，智能体整轮累计限 8000 字，测试连接固定低档/1024 tokens/原总时限。`user_model_configs` 新增 `effort TEXT NOT NULL DEFAULT 'low'`，老库启动时自动补列，已有行默认低，不新增迁移版本号，该 BYOK 变更不增加健康检查项；保存模型、Key 或切换厂商保留档位，只在 Claude 下生效。
- BYOK 密钥：服务端 `FIONA_BYOK_SECRET` 为 url-safe base64 编码的 32 字节，单独保管，不进入数据库/媒体备份；丢失时用户重新填写自己的 Key 即可。`FIONA_BYOK_SECRET_PREVIOUS` 为逗号分隔的旧密钥，仅用于解密，用户下次保存使用当前密钥重新加密。缺失或非法密钥、十一项污染客户端的环境变量会使 BYOK 不可用（含 `ANTHROPIC_CUSTOM_HEADERS`，完整清单见部署手册），DEV_MODE 也没有固定回退值。预设厂商（含 Claude）遵循服务器的 HTTP(S)_PROXY / NO_PROXY 出站代理设置；自定义地址不使用环境代理。 `FIONA_BYOK_MAX_STREAMS` 默认 8（1–64），每用户一条流；`FIONA_BYOK_TOTAL_SECONDS` 默认 120（10–240）秒，调用时读取，非法回退默认并只告警一次。生成命令：`python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`。
- 浏览器 JWT 只在 `HttpOnly` Cookie 中；新账号的会话版本使用随机正整数，既有账号版本保持原值，HTTP/WebSocket 每次鉴权都核对数据库会话版本，不能恢复 query token 或 JavaScript 可读存储。
- `DEV_MODE=1` 且请求 socket 对端为回环地址才开放测试登录和 `X-Dev-User` 等开发通道；工作室默认仍要求 JWT，只有 `FIONA_STUDIO_REQUIRE_JWT=0` 才允许开发身份；前端 `npm run dev` 默认只监听 `127.0.0.1`，`npm run dev:lan` 才显式对局域网开放。
- 单域名环境不设置 `NEXT_PUBLIC_API_BASE`；前端相对 `/api` 由 Next rewrite 或生产 Nginx 转发。

## 生产拓扑

- Nginx 443：`/` → Next.js 3000，`/api/` → FastAPI 8000 并移除前缀，`/uploads/` → FastAPI。
- systemd：`fiona` 启动后端，`fiona-web` 启动 `next start`。
- 原线上服务器（域名 `madchloechat.online`）已于 2026-09-25 关闭，当前没有在线部署；下线记录见 `docs/DEPLOYMENT.md`。重新部署时以部署手册为准，不要假定任何服务器仍在运行。
- 所有生产命令、备份和回滚步骤以 `docs/DEPLOYMENT.md` 为准；SQLite 启用 WAL 后须用 `sqlite3 .backup` 或在线备份 API 获取一致快照，不能只复制主数据库文件。仓库文档不能证明外部服务器的即时状态。
- `deploy/fiona-backup.sh` 必须以数据库属主运行，备份目录为服务账号所有且 `0700`，备份文件 `0600`；timer 每天北京时间 04:00 执行，默认保留 14 天。数据库、uploads 及存在时的 studio 目录各生成同时间戳备份，两个媒体包都排除隐藏文件与 `.part`。`backend/migrate.py` 默认在库及 WAL/SHM 临时副本上仅执行初始化迁移，`--db` 优先于配置，明确 `--in-place` 才写指定库；恢复演练不得启动唯一备份。
- `/health` 无需登录，支持 GET/HEAD，3 秒总超时，只读检查现有数据库及其可写权限、五道迁移和上传目录；`FIONA_STUDIO != "0"` 时另查工作室目录可写性（`studio_storage`），不探测外部服务、不泄露路径；原 `/` 仍只检查进程。启动从未成功时退出 3，上传清理单轮异常后继续。外部拨测用 GET，systemd 失败通知与供应商消费告警按部署手册配置，消费告警由作者手工完成。
- 按 IP 限流只在 ASGI 对端属于调用时读取的 `FIONA_TRUSTED_PROXIES` 时信任代理头；所有 Nginx 入口必须覆盖 X-Real-IP 并追加 XFF，uvicorn 可能已按 XFF 改写对端。开发回环鉴权函数保持只看 ASGI 对端。

## 当前重要边界

- 这是 SQLite 单机内测架构，不要宣称已经支持 PostgreSQL 或无限并发。工作室调度器在进程内运行，只支持单 worker。
- 远程 Tauri capability、Windows `open_url` 和 CSP 已完成代码整改；桌面公开发布仍需 Windows/Rust 复核、签名和发布验证。
- 热点与网页卡片的服务端抓取已经统一经过公网 HTTP(S) 校验、DNS/IP 固定、逐跳重定向检查和响应大小限制。
- 搜索与旅行卡片来源只取自原生 `output.search_info.search_results`，经公网 HTTP(S) 格式校验后下发，模型生成的 URL 不进入卡片；此校验不访问来源站点。前端最多显示 5 条可点击来源，统一用 `openExternal` 打开；模型正文（要点、旅行标题与非 JSON 回退行）在卡片组装前依次清理引用角标与 HTTP(S)、www.、Markdown 链接，朗读和历史摘要使用清理后的正文。非字符串要点只允许非 bool 的 int/float 转成文字，其余对象丢弃。搜索无可核实来源时错误且不计费，旅行建议允许没有来源。卡片及来源不落库，刷新或切换会话后只剩文字摘要。
- 问句式天气请求走 `weather`，没明确城市就追问“哪个城市？”，取消或非城市回复不会调用高德；普通 `web_search` 不按“天气”关键词分流。天气卡最多四天的中文日夜预报，无实时温度、体感或湿度；卡片不落库。天气调用失败日志仅记录工具名、错误类型和耗时，城市名、用户原话、响应体不得进入日志、trace payload 或异常文案。
- Layer 2 双边卡片、双方偏好验证、手动匹配输出约束和跨用户画像最小化已完成；候选原始消息不得进入匹配模型。
- 完整账户删除会在删除 users 前同事务删除 `user_model_configs` 配置（含 `effort`）与加密 Key，清理其他数据库关联记录、关闭真人连接，并通过持久化队列重试无引用上传文件和工作室项目目录；删号同事务删除四张 `studio_*` 表中的 owner 行并入队项目目录，目录清理拒绝工作室根外路径；关键后台写入必须继续防止删号后重建数据。
- 总请求体、Chat/图片、ASR、TTS、帖子和分页已有应用层边界；通用聊天的模型并发、真实 usage 与持久化成本控制仍未完成；工作室已独立持久化人民币预留、结算与每日上限。
- 聊天和广场图片在线程中纠正方向、按原格式逐帧重建去元数据，仅保留 ICC；MPO 只存主帧，动图有限帧和总像素，并发重编码最多 2，广场在线程派发前排队，聊天等待槽位超时返回 503。广场视频依赖 ffmpeg 无损 remux，清 metadata、章节、数据和字幕轨，失败拒绝上传。上传目录内临时文件原子落盘，权限 0600；广场失败或取消、聊天同步处理失败及等待线程期间取消会清理，线程完成后的消息写库取消窗口仍保留。启动清扫超过 1 小时的上传临时文件，点文件不提供静态访问且不进入媒体备份。旧文件清理脚本默认 dry-run，跳过已清理图片，apply 有失败返回非零并保留原权限。语音合成仅保留 HTTP/流式接口，真人 Peer WebSocket 保留。
- 聊天模型预算是进程内估算，不等同于供应商真实账单；草莓预扣、退款及每日补给已实现原子化。工作室额度独立存 SQLite，实际金额由厂商 usage 折算。
- 私聊危机采用规则加模型复核：规则 `high` 直接进入支持流程；其他非空文字消息由 `qwen3.8-flash` 复核，只看当前消息；超过 2000 字时取首尾各 1000 字，中间用「……」连接。取较高档位，不能降档。复核与预扣、上下文装配并行，默认 2 秒超时，失败按规则结果走；只记录档位、异常类型和耗时，不记录原文。信息或求助语境只看规则。私聊未命中危机信号的轮次，所有 system 消息合计恰好包含一次基础安全规则，放在最后一条 system 消息末尾；请求朗读时，平台模型与 BYOK dashscope 预设将朗读强约束作为当前 user 消息后的独立 system 消息；其他 BYOK 厂商合并 system，Claude 使用顶层 system，基础安全规则仍恰好一次且在末尾。明确危机轮跳过普通模式、工具与待补参数，固定附上求助资源；余额足够时照常预扣并按交付结算，余额不足时免费返回资源且不调用回复模型。可能相关的轮次保留模式判定、镜子、看图、普通回复和计费；除信息或求助语境外，跳过自然语言生图候选、意图识别、工具及待补参数，保留 pending。信息或求助语境、界面显式生图或修图、缺少修图参考的固定引导保持原路由；唯一例外是已有天气 pending 时，到达工具路由的 `possible` 信息或求助语句清除该 pending，按新消息路由，不能当作城市名发给高德。文字、工具、图片以及服务端能控制的错误路径均恰好送达一次资源；余额不足时先送资源再报错；进入路由前的 422 校验和 429 限流是例外。图片模式的明确危机轮按文字回复显示。繁体危机文字只在规则分类时归一，模型复核、存库和显示保留原文。繁体『計畫』与『計劃』判级一致。分身交流每条 system 消息也带基础安全规则。测试在收集阶段强制使用会话临时数据库、上传目录和工作室目录，并阻断真实网络与 DNS；厂商请求必须使用模拟传输。
- 前端主页面和常驻抽屉 iframe 有已知性能与维护债务。
- Persona、成人内容、AI 身份披露、年龄与危机处理政策必须在扩大内测前统一。

## 工作约定

- 优先修复可复现问题，避免无关重构。
- 不提交 `.env`、数据库、上传文件、备份或 `fiona.config.json`。
- 代码改变模型、路由、端口、环境变量、数据位置或部署方式时，同步更新 README、架构/部署文档和 PLAN。
- 只有作者明确要求时才提交 Git commit。

## 本机监控（2026-10-11）

`watcher-mac/` 是 macOS 14+ 的独立 Swift Package，不改 Windows `desktop/`。数据流：本机 OCR → 只上报新增行 → `routers/local_watch.py` / `services/local_watch.py` 判断 → 用 `database.save_message` 写进聊天，同时保存 `watch_alerts`。不进入现有聊天路由、画像提取、匹配、危机流程或计费；提醒不扣草莓。截图和整页文字留在 Mac 内存，新增文字不落日志、不写 trace，持久化的只有提醒摘要。关键词/数值不调用模型，AI 使用阿里云千问或已启用的 Anthropic BYOK，Claude 失败不回退。

`FIONA_LOCAL_WATCH=1` 默认开启，`0` 使全部监控接口返回 404；`FIONA_DAILY_WATCH_JUDGE=500` 是每账号每日 AI 判断上限，开发模式与通用限流关闭也不跳过。设备令牌只显示一次，数据库仅存 SHA-256 哈希；不要记录或提交令牌，文件须为 `600`，用 `umask 077` 写入，泄露后立即在设置页吊销。旧库启动以 `CREATE TABLE IF NOT EXISTS` 建三张监控表，删号同事务清理。

已知局限：只支持 macOS；窗口最小化后截不到；OCR 可能有错字；只能看到窗口当前显示的内容。Fiona 页面关闭时不会实时弹出，但提醒照样落库。浏览器通知默认不弹，需用户主动允许。实现和验收细节见 `docs/tasks/2026-10-11-local-watch/03-report.md` 与 `watcher-mac/README.md`。

屏幕锁定或显示器休眠时 macOS 不允许截取窗口，期间无法监控。如果需要离开电脑时也能监控，可以在 系统设置 → 锁定屏幕 中延长自动锁定时间，但要自行权衡安全。截图状态随心跳按规则上报，后端只在内存保留 5 分钟并映射中文提示；设置页逐条显示正常、截图失败、窗口未找到或监控程序未在运行。

## 小说工坊

P2 前端入口为第六个书签「书斋」；`frontend/app/novels/page.tsx` 是书架，`new/page.tsx` 为三步向导，`[id]/page.tsx` 为单本工作台，拆分组件在 `components/novel/`，请求与类型在 `lib/novels.ts`。主页 `novel-drawer` 常驻 iframe `/novels?embed=1`，内链保留 embed，三页均尊重 `data-shell` / `mobile:`。运行态可见时每 3 秒链式轮询，操作后立即刷新；账号身份与请求取消沿用 `useAccountIdentity` / `useAccountRequest`。完整圣经与留言使用新增只读 GET `/{id}/bible` 和 `/{id}/notes`，P1 详情仍裁剪。状态只用文字 tag/chip，不用朱印；不新增颜色、字体或依赖。

P1 后端入口 `backend/routers/novel.py`（`/novels`），业务层 `novel/service.py`，状态机 `novel/runner.py`，数据库适配 `novel/store_db.py`，计费 `novel/billing.py`，BYOK 适配 `novel/byok_bridge.py`。必须复用 P0 deliberate/write_chapter，离线 pilot 的步骤键与流程不得改变。

P2.1 建书可选 `drama_adaptation`（默认 false，建书后不可修改）；向导勾选时尝试加入短剧改编顾问并展开改编参数，顾问仍可手动取消。开启后审校 payload 才包含 `adaptation_blocking` 和 `adaptation_limits`，允许场景数/主要人物数超限阻断；style 永不阻断。审校冻结原句保留，紧接追加条件例外。`validate_archive(..., require_new_appearance=False)` 保持 P0/直接归档兼容，P1 写书和重新归档传 true，要求新人物外形去空白至少 20 字。

`PATCH /novels/{id}/characters/{character_id}` 仅允许在 awaiting_review、awaiting_plan、awaiting_end、paused、completed 时修改外形/性格/动机，写入新的 `user_edit` 圣经版本，不标记章节 stale。Markdown 导出保留所有有正文的章节，对 stale 章追加待复核提示和书首汇总；无 stale 时输出不变。进程内只读服务 `find_books(username, query)` 按本人书名包含匹配，`chapters_range(username, novel_id, start, end)` 按 1–300 章、单次最多 50 章读取，共用单章返回组装；两者不新增 HTTP 路由。

开关 `FIONA_NOVEL=1` 且用户名位于 `FIONA_NOVEL_USERS` 才开放；并发 FIONA_NOVEL_MAX_RUNNING 默认 3，每日 FIONA_DAILY_NOVEL_CHAPTERS 默认 30，完整价目覆盖 FIONA_NOVEL_PRICE_JSON。SQLite 五表 novels、novel_bible_versions、novel_chapters、novel_steps、novel_notes 由 init_db 幂等创建，无新迁移版本，删号前取消任务/退款，同事务删全部关联行。后台写库需 run_token 与 users 存在检查。

平台模型使用 DASHSCOPE_API_KEY、DEEPSEEK_API_KEY、ARK_API_KEY；Claude 只经 BYOK。思路、圣经、正文与留言会发给阿里云百炼、DeepSeek、火山方舟或用户自带厂商（包括 Anthropic）。Key 仅调用时从 byok.store 取用，不写小说库、日志或响应；步骤只存请求摘要，不存提示词。测试必须离线、不得读仓库外输入或依赖 git 历史；本机监控原有内容不得修改或移动。

## 短片工作室 WO1

`backend/studio/` 与 `routers/studio.py` 提供作者私用的首帧视频接口，暂无前端。全部 `/studio/*`（含文件）要求开关非字面 `0`、精确命中 `FIONA_STUDIO_OWNERS` 与 Bearer/Cookie JWT；不满足一律 404、`private, no-store`。中间件记录 `auth_method=jwt/dev`，其他路由鉴权保持原行为。

报价 15 分钟内只可确认一次，确认事务锁定价格、预留额度、建 queued 任务；日上限按确认时的上海自然日计算，全工作室共用，DEV_MODE 和通用限流开关不能跳过。付费 POST 最多一次；超时、断流、5xx、成功响应无任务编号均 uncertain 并保留预留，只允许人工核对、关联 task_id、只读复查或明确未扣费后释放。启动先恢复再调度，submitting 变 uncertain，其他在途恢复 GET，不能重新提交。

文件默认 `backend/studio_data/`，生产 `FIONA_STUDIO_DIR=/var/lib/fiona/studio`，因为 systemd `ProtectSystem=strict` 只允许写 `/var/lib/fiona`。文件不挂静态目录，按素材归属和真实路径校验后用 FileResponse 支持 Range。仅下载白名单 host，不跟重定向、不转发凭据，限 300MB；ffprobe 按时长校验。万相按原图提交，Seedance 只在提交内存中等比缩图。所有测试用模拟传输，业务不得 import WO0 探针。
