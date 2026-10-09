# Fiona / Chloe

Fiona 正在演进为个人 AI 分身交流与 Skill 交易平台，当前用于作者自用和小范围内测。已实现独立分身、持久私有会话、名片和私有记忆，以及经双方授权的分身互聊。Skill 安装和交易仍在后续计划中，见[平台方案](./docs/CYBER_AVATAR_PLATFORM.md)。

> 当前定位是小规模内测版本，不是已经完成安全加固的公开 SaaS。发布范围和已知阻断项见 [PLAN.md](./PLAN.md)。

## 当前能力

- 我的分身：名称、头像符号、简介、人格设置，以及登录用户可查看的公开名片。
- 私有会话：创建、切换、删除、刷新恢复；历史与工具补参按会话隔离，首条消息自动命名。
- 私有记忆：独立于旧社交画像保存，可查看和清空；新私有会话不自动触发跨用户匹配。
- 陪伴对话：流式回复、长期画像、成长阶段、人设与对话模式路由。
- 模型与工具：Qwen 主力/轻量模型、用户图片理解、联网搜索、热点展开、旅行规划和中文天气预报；搜索与旅行卡片可点击真实搜索来源，天气使用阿里云百炼托管的高德地图 MCP（Amap Maps）。
- 聊天生图：可选 Qwen Image 3.0（默认）或 Seedream 5.0 Flash，文字生成图片、参考图编辑、方形/横版/竖版、对话内预览与下载，生成图随会话保存。
- 语音：浏览器录音、Qwen ASR、TTS HTTP/流式朗读。
- 社交连接：两层候选匹配、待接受卡片、双方接受后的真人房间和历史消息。
- 广场：热点、发帖、图片/短视频上传、点赞、兴趣与时间偏好；社群页面仍为占位。
- 多端：Next.js Web/PWA，以及加载开发隧道或公网网站的 Tauri 2 Windows 客户端。

## 技术栈

| 层 | 当前实现 |
|---|---|
| Web | Next.js 16.3.3、React 19、Tailwind CSS 4、React Three Fiber |
| API | FastAPI、Uvicorn、Pydantic、SlowAPI |
| 模型 | DashScope / Qwen（主力、轻量、视觉、搜索、生图、ASR、TTS）；生图和修图可选火山方舟 Seedream 5.0 Flash；官方搭档可独立接入 DeepSeek V4 Pro |
| 天气 | 阿里云百炼托管的高德地图 MCP（Amap Maps），复用 `DASHSCOPE_API_KEY` |
| 数据 | SQLite + 本地媒体；开发默认位于 `backend/`，生产建议位于 `/var/lib/fiona/` |
| 桌面 | Tauri 2，Windows MSI/NSIS |
| 生产拓扑 | 单域名 Nginx，前端 `:3000`，后端 `127.0.0.1:8000` |

更完整的模块、数据流和信任边界见 [架构文档](./docs/ARCHITECTURE.md)。

## 目录

```text
Fiona/
├── backend/                 # FastAPI、SQLite、模型编排、匹配和工具
│   ├── routers/             # auth/chat/hot/match/me/peer/plaza/voice
│   ├── services/            # 聊天主流程
│   ├── tools/               # 搜索、天气、热点、旅行、系统工具等
│   └── tests/               # 后端回归测试
├── frontend/                # Next.js App Router Web/PWA
├── desktop/                 # Tauri 2 Windows 桌面壳
├── docs/                    # 当前架构和部署手册
├── PLAN.md                  # 当前状态、风险和路线图
└── start.ps1                # Windows 本地 Web 一键启动
```

## 本地启动

### 1. 后端

项目当前开发环境使用 Python 3.14；依赖以 `backend/requirements*.txt` 为准。

```bash
cd backend
python -m venv .venv
```

macOS/Linux 激活环境：

```bash
source .venv/bin/activate
```

Windows PowerShell 激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖并准备环境变量：

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

在 `backend/.env` 中至少配置：

```dotenv
DASHSCOPE_API_KEY=...
JWT_SECRET=...
DEV_MODE=1
```

OpenAI 兼容模型客户端默认 60 秒超时、最多重试 1 次，可用 `DASHSCOPE_TIMEOUT_SECONDS` 和
`DASHSCOPE_MAX_RETRIES` 在模板允许范围内调整。搜索、旅行规划、热点展开和卡片详情
均使用 DashScope 原生 `qwen-plus` 接口并强制联网搜索，固定 30 秒 socket 超时、不重试，
不受这两个环境变量控制；卡片详情路由外层另有 45 秒总超时。
热点分类使用 `qwen3.8-flash`，请求固定 8 秒超时、不重试。危机复核使用独立异步客户端、不重试，
`FIONA_CRISIS_MODEL_ENABLED` 默认开启，仅 `0` 关闭；`FIONA_CRISIS_MODEL_TIMEOUT_SECONDS`
默认 `2.0` 秒，合法范围 `0.5–10`，无效值回落到默认值。

天气需先在百炼控制台开通 Amap Maps，复用 `DASHSCOPE_API_KEY`；目前限时免费，结束后按量计费，单价以控制台为准。`FIONA_AMAP_ENABLED` 默认 `1`，只有字面 `0` 关闭；`FIONA_AMAP_TIMEOUT_SECONDS` 默认总预算 `8` 秒，合法范围 `1–30` 秒，空串、非数字、非有限值或越界值回落到 `8`。这些天气配置在调用时读取。

然后启动：

```bash
python run.py
```

API 默认监听 `http://127.0.0.1:8000`。数据库表会在应用启动时初始化。首次运行新版本会执行分身/会话版本迁移，为旧账号创建私有分身和默认会话，回填旧消息归属；更新已有部署前请按部署手册备份数据库与媒体。迁移失败会回滚该迁移并阻止启动。

### 2. 前端

前端字体为自托管思源宋体（`public/fonts/noto-serif-sc`，OFL）；外观可选跟随系统、昼、夜与素瓷。

Node.js 20+；锁文件已提交，优先使用 `npm ci`。

```bash
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:3000`。`npm run dev` 默认只监听本机；开发环境通过 Next rewrite 将 `/api/*` 转发到本机 FastAPI，不需要额外配置前端 API 地址。确需局域网真机调试时，显式运行 `npm run dev:lan`，并按需设置 `FIONA_ALLOWED_DEV_ORIGINS`（逗号分隔；只填主机名或 IP，可用 `*.example.local` 这类通配，不带协议和端口）允许额外来源；这个模式会把开发前端暴露给局域网设备，可能让能访问它的人触及调试接口和内测数据，只在可信网络临时使用。

登录后从侧栏“分身”打开设置面板，也可直接访问 `/agents/me`，再回到聊天页创建或切换会话。名片默认私有；公开后只展示名称、头像和简介等安全字段。清空记忆会同时清除分身私有记忆和旧个人画像，聊天记录保留。

搜索与旅行卡片在要点下方显示最多 5 条可点击来源（标题和站点），通过现有安全外链入口打开。来源只取自 DashScope 原生响应的 `output.search_info.search_results`，经公网 HTTP(S) 格式校验后附加，模型生成的 URL 不进入卡片；行程标题、要点与非 JSON 回退文本会清理引用角标及模型写入的 HTTP(S)、www. 和 Markdown 链接，朗读和聊天文字摘要使用清理后的正文。没有可核实来源的搜索返回错误且不计费；旅行建议允许没有来源。卡片及来源目前不落库，刷新或切换会话后只保留文字摘要，来源不会恢复。

“明天杭州会下雨吗”“杭州冷不冷”“要带伞吗”走独立的 `weather` 意图；没明确城市时追问“哪个城市？”，回复“算了”可取消，明显不是城市的回复按新消息处理。天气卡最多展示四天的中文白天/夜间天况、最高最低温和风向风力，成功交付才按普通工具扣草莓，失败、取消、缺参追问和超限均不扣草莓；天气卡结构目前不落库，只保存文字摘要。隐私数据流：每次只把用户本轮或最近对话里明确说出的城市名发送给阿里云百炼托管的高德地图服务，不发送聊天历史、私有记忆或用户位置，不做 IP 定位，不猜测或默认城市。包含“天气”的普通 `web_search` 查询仍走原生联网搜索。

意图识别出口对白名单 `web_search`、`hot_topics`、`route`、`travel_plan`、`get_datetime`、`fetch_card`、`generate_image`、`weather` 及各自参数、缺失字段做格式规范化，未知或畸形意图回落为空意图。

聊天输入区点击“生成图片”，选择 `1:1`、`16:9` 或 `9:16` 后填写画面描述；也可以直接发送“帮我生成一张薄雾古庙图片”。每次生成一张，可在气泡中放大和下载，刷新会话仍可查看。生图和修图都可选 Qwen Image 3.0（默认）或 Seedream 5.0 Flash；选择会保存在本机，切换账号或会话后保留，普通聊天里的自然语言生图也跟随该选择，失败重试使用当前界面选中的模型。Qwen 使用已有 `DASHSCOPE_API_KEY`，可通过 `QWEN_IMAGE_MODEL` 配置；Seedream 使用火山方舟 `ARK_API_KEY` 和 `SEEDREAM_IMAGE_MODEL`（默认 `doubao-seedream-5-0-flash-260915`），须先在方舟控制台开通模型。成功获取模型列表后，未配置密钥的模型按钮不可选，已选不可用项暂时回到默认模型，保留本机偏好，之后获取到该模型可用时恢复原选择；列表请求失败时两项均可选，由服务端报错。图片请求执行失败时不会自动更换供应商。选择 Qwen 时描述和参考图发送给阿里云 DashScope；选择 Seedream 时发送给字节跳动火山引擎。两个模型每次都扣 10 颗草莓，失败照常退款；单次生成和下载总超时 150 秒，不自动重试，失败可手动重试。生成图仅会话所属用户可访问，删除消息或会话时清理已无引用的文件。

需要调整已有图片时，点击该图的“以此图修改”，还可在其他图上点“加入参考”，或点击输入区“上传参考图”从电脑选择图片。本地图片和当前对话生成图可以混用，合计最多 3 张；本地支持 PNG、JPEG、WebP，每张不超过 5MB。输入区按选择顺序显示图1、图2、图3，可以移除或调整顺序，再输入例如“用图1的人物、图2的场景、图3的色调”。本地图片会纠正方向、移除元数据并适配模型尺寸，发送修改指令时才上传；比例超过 4:1 的图片需先裁剪。默认沿用处理后图1的尺寸；Seedream 在目标尺寸不足或超过限制时按比例缩放，缩放后的宽高取 8 的倍数；比例误差不超过 1% 的候选中优先选择最接近目标面积的尺寸。两个供应商读取本地参考 PNG 时都使用 2048² 像素上限。每次修改产生一张新图；全部参考图、顺序和修改要求都保存在对话里，新图也能继续作为参考。取消参考或切换会话会退出编辑，失败重试仍使用原先那组图与顺序。普通聊天的图片附件仍用于看图聊天。

侧栏“分身广场”或 `/agents` 可浏览其他公开分身。双方先公开名片，发起方填写主题与回复次数，对方在“收到的邀请”中接受后开始交流。双方合计最多 6 次回复，随后生成一次总结；任何一方可以立即停止。交流仅使用公开名片与当前交流内容，不读取人格设定、私聊或私有记忆。记录仅双方可见；关闭公开名片会停止待处理与进行中的交流。所有交流模型调用都带基础安全规则。内测阶段会消耗平台模型用量，不扣草莓，也不执行外部工具。

一个人也可在广场默认的“单人体验”中选择“创意搭档”“脚本编辑”或“短视频创意搭档”。它们是平台官方 AI，没有真人主人，也不占用用户账号。填写主题并点击“开始讨论”后，进入“主创初稿 → 官方审稿 → 主创修订”的作品协作。你的分身提交完整稿件，官方搭档核对原始要求并列出修订意见。默认双方合计最多 99 次，可填写 2–99 的整数；审稿通过即提前结束，直接保留通过审稿的完整版本，在“体验记录”查看。无需公开自己的名片或注册第二个账号；仅使用自己的分身名称、简介与本次讨论，不读取人格设定、私聊或私有记忆，记录仅本人可见。内测不扣草莓；生产限流开启时，每账号每天北京时间自然日默认可创建 3 次体验，由 `FIONA_DAILY_OFFICIAL_EXCHANGES` 配置，停止或失败也计入。关闭名片公开不会停止官方体验，可用“停止交流”结束。

连同官方体验，共有五项每日每账号上限。热点展开、卡片详情、语音识别和天气分别默认限 30、30、300、30 次，可由 `FIONA_DAILY_HOT_EXPANDS`、`FIONA_DAILY_CARD_DETAILS`、`FIONA_DAILY_ASR`、`FIONA_DAILY_WEATHER` 调整；五项配置均在调用时读取，只接受正整数，非法值回落默认并只告警一次，开发模式或关闭限流器时不生效。上述四项在本地校验通过、即将执行时计数，上游失败不退还，单进程内存计数会随服务重启清零，北京零点换日。天气缺参追问只检查额度，取消和本地校验失败不计数；天气超限在聊天中返回“今天查天气的次数已用完，明天再试”的错误事件，不写入待补状态、不扣草莓。其他四类 HTTP 接口超限仍返回 429 和 `Retry-After`；语音识别超限会关闭免提，可先打字。

“短视频创意搭档”专门从零发展短片创意：人物冲突、前三秒钩子、剧情反转，逐步细化成分镜、台词、音效和时长安排。结束时按讨论结果整理带时间段的剧本；遵循话题指定的时长，未指定时以 30–60 秒为起点。它负责剧本讨论，不直接生成视频。

单人体验的话题支持最多 10,000 字，可填写人物设定、剧情背景、风格与时长要求，后端完整保存并提供给每次写稿和审稿；最新完整作品和最近审稿意见也会完整保留在模型上下文中。长话题在详情中默认显示预览，可展开阅读、滚动或复制全文。与其他用户分身的邀请主题仍最多 300 字。

新创作的详情顶部展示“当前作品”，可下载作品 Markdown、`README.md`（完整稿件、原始需求和审核状态）以及完整讨论 Markdown（全部写稿、审稿和修订过程）。审稿通过标为“AI 审稿通过 · 待你验收”；达到次数上限、重复无进展、输出不完整或手动停止时保留草稿。历史讨论继续提供原有 README 与完整讨论导出，无需重新调用模型。下载权限与查看交流一致。

官方搭档支持独立模型：在后端 `.env` 配置 `OFFICIAL_EXCHANGE_PROVIDER=deepseek`、`OFFICIAL_EXCHANGE_MODEL=deepseek-v4-pro` 和 `DEEPSEEK_API_KEY` 后重启后端，官方审稿及历史流程的体验总结使用 DeepSeek V4 Pro，自己的分身继续使用 Qwen 主模型。未配置时官方搭档也使用 DashScope。模型名称显示在官方名片中，密钥仅留在后端；不会在供应商失败时暗中回退到另一个模型。DeepSeek 使用[官方接口](https://api-docs.deepseek.com/quick_start/)。

Windows 也可以在根目录运行 `start.ps1`，它会分别打开后端和前端进程。

## 登录与本地调试

- 内测登录使用邀请码：`POST /auth/redeem-invite`。
- 浏览器登录成功后使用服务端签发的 `HttpOnly` Cookie；退出登录会撤销该账号此前签发的会话。
- `backend/seed_invites.py` 用于创建绑定新 `testerNN` 用户名的邀请码，编号不会与现有账号、邀请码绑定名或已退役用户名重复，删号后不回收；新账号使用随机的初始会话版本，旧账号版本不变。`backend/manage_invites.py` 用于查看、撤销和轮换邀请码。
- 生产私聊先原子预扣 10 颗草莓，只对已保存的模型回复、已生成并保存的图片或成功的真实工具结算；失败、缺参追问和桌面占位工具会退还。`STRAWBERRY_DAILY_REFILL` 可配置每日补到至少指定余额（默认 `0` 为关闭），管理员可用 `backend/manage_strawberries.py` 手动补充。
- 私聊危机采用规则加模型复核：规则 `high` 直接进入支持流程；其他非空文字消息由 `qwen3.8-flash` 复核，只看当前消息；超过 2000 字时取首尾各 1000 字，中间用「……」连接。取较高档位，不能降档。复核与预扣、上下文装配并行，默认 2 秒超时，失败按规则结果走；只记录档位、异常类型和耗时，不记录原文。信息或求助语境只看规则，模型从未命中升到可能相关时跳过工具。明确的第一人称自伤或自杀危机进入支持流程，不执行工具或普通镜子话术；余额足够时按正常轮次预扣和结算，不足时无需付费即可收到资源文案且不调用回复模型。可能相关的表达保留模式判定、镜子、看图、普通回复与计费；除信息或求助语境外，跳过自然语言生图候选、意图识别、工具及待补参数，保留 pending。信息或求助语境、界面显式生图或修图、缺少修图参考的固定引导保持原路由；唯一例外是已有天气 pending 时，到达工具路由的 `possible` 信息或求助语句清除该 pending，按新消息路由，不能当作城市名发给高德。文字、工具、图片及失败路径都会附求助资源，余额不足时免费先送资源再提示余额。进入 `/chat` 路由之前发生的 422 请求校验和 429 限流不在资源送达保证范围内。模型不能消除规则已有的日常误判。繁体『計畫』与『計劃』判级一致。图片模式中的明确危机按文字回复显示。普通私聊和分身交流的模型提示词均带基础安全规则。
- `DEV_MODE=1` 时仅对回环地址开放 `/auth/test-login` 和 `X-Dev-User` 等调试通道；不要经不可信代理转发开发站点。
- 生产环境必须使用 `DEV_MODE=0` 和足够强的 `JWT_SECRET`。

生产管理示例（脚本会显示所加载的配置文件和数据库绝对路径；数据库不存在时须明确传 `--init-db` 才能首次创建）：

```bash
cd backend
python seed_invites.py 10 --env-file /etc/fiona/fiona.env
python manage_invites.py list --env-file /etc/fiona/fiona.env
python manage_invites.py revoke ABCD2345 --env-file /etc/fiona/fiona.env
python manage_invites.py rotate ABCD2345 --env-file /etc/fiona/fiona.env
python manage_strawberries.py list --env-file /etc/fiona/fiona.env
python manage_strawberries.py grant tester01 50 --env-file /etc/fiona/fiona.env
python manage_strawberries.py set tester01 200 --env-file /etc/fiona/fiona.env
```

设置页支持退出登录和完整账户删除。删除消息、清空历史或删号时都会清理不再被消息/帖子引用的上传文件；失败项进入持久化队列，并在启动时及运行期间周期重试。

不要提交 `backend/.env`、`backend/fiona.db`、`backend/uploads/` 或 `desktop/fiona.config.json`。

## 检查与构建

后端：

```bash
cd backend
python -m pytest -q
python -m compileall -q .
python -m pip check
python -m pip_audit -r requirements.txt --progress-spinner off
```

测试收集阶段会把数据库和上传目录固定到会话临时目录；单独运行任一后端测试文件也使用隔离路径。

请使用 `python -m pytest`；当前直接调用某些环境中的 `pytest` 命令可能无法找到后端顶层模块。

前端：

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
npm audit
```

当前 TypeScript、Lint 和生产构建都通过；Lint 仍有非阻断警告，合并前应以 [PLAN.md](./PLAN.md) 中的当前质量状态为准。
这些门禁已写入 `.github/workflows/quality.yml`，Windows 桌面工作流也会在打包前执行 Rust 单元测试。

桌面端构建和安装见 [desktop/README.md](./desktop/README.md)。

## 部署

> 原线上服务 `madchloechat.online` 已于 2026-09-25 下线，当前没有在线部署。下线记录见[生产部署手册](./docs/DEPLOYMENT.md#下线记录)。

重新部署时的目标形态是同一台服务器上的 Nginx + systemd：

- `/` → Next.js `127.0.0.1:3000`
- `/api/` → FastAPI `127.0.0.1:8000`，并移除 `/api` 前缀
- `/uploads/` → FastAPI `127.0.0.1:8000/uploads/`

完整的首次部署、Nginx、systemd、备份、更新与回滚步骤见 [生产部署手册](./docs/DEPLOYMENT.md)。仓库中的文档描述目标配置，不代表外部服务器一定已经保持相同状态；每次发布前仍需核对线上配置。

## 文档索引

- [当前路线图与发布阻断项](./PLAN.md)
- [系统架构](./docs/ARCHITECTURE.md)
- [生产部署](./docs/DEPLOYMENT.md)
- [前端开发](./frontend/README.md)
- [Windows 桌面客户端](./desktop/README.md)
- [编码代理快速上下文](./CLAUDE.md)

## 开源许可与安全报告

本项目原创代码采用 [MIT License](./LICENSE)。你可以使用、修改和分发代码，但需要保留许可证和版权声明。NASA、Solar System Scope 和 Three.js 的图片/纹理仍遵循各自条款，详见 [第三方素材声明](./THIRD_PARTY_NOTICES.md)。

请不要在公开 Issue 中披露未修复漏洞、API Key、个人数据或数据库内容。安全问题请按 [安全政策](./.github/SECURITY.md) 通过 GitHub Private Vulnerability Reporting 私密提交。
