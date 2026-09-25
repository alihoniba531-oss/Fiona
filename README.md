# Fiona / Chloe

Fiona 正在演进为个人 AI 分身交流与 Skill 交易平台，当前用于作者自用和小范围内测。已实现独立分身、持久私有会话、名片和私有记忆，以及经双方授权的分身互聊。Skill 安装和交易仍在后续计划中，见[平台方案](./docs/CYBER_AVATAR_PLATFORM.md)。

> 当前定位是小规模内测版本，不是已经完成安全加固的公开 SaaS。发布范围和已知阻断项见 [PLAN.md](./PLAN.md)。

## 当前能力

- 我的分身：名称、头像符号、简介、人格设置，以及登录用户可查看的公开名片。
- 私有会话：创建、切换、删除、刷新恢复；历史与工具补参按会话隔离，首条消息自动命名。
- 私有记忆：独立于旧社交画像保存，可查看和清空；新私有会话不自动触发跨用户匹配。
- 陪伴对话：流式回复、长期画像、成长阶段、人设与对话模式路由。
- 模型与工具：Qwen 主力/轻量模型、视觉理解、联网搜索、热点展开、旅行规划等。
- 聊天生图：文字生成图片、引用已有生成图继续修改、方形/横版/竖版、对话内预览与下载，生成图随会话保存。
- 语音：浏览器录音、Qwen ASR、TTS HTTP/流式/WebSocket。
- 社交连接：两层候选匹配、待接受卡片、双方接受后的真人房间和历史消息。
- 广场：热点、发帖、图片/短视频上传、点赞、兴趣与时间偏好；社群页面仍为占位。
- 多端：Next.js Web/PWA，以及加载开发隧道或公网网站的 Tauri 2 Windows 客户端。

## 技术栈

| 层 | 当前实现 |
|---|---|
| Web | Next.js 16.3.3、React 19、Tailwind CSS 4、React Three Fiber |
| API | FastAPI、Uvicorn、Pydantic、SlowAPI |
| 模型 | DashScope / Qwen（主力、轻量、视觉、搜索、ASR、TTS）；官方搭档可独立接入 DeepSeek V4 Pro |
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
│   ├── tools/               # 搜索、热点、旅行、系统工具等
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

模型客户端默认 60 秒超时、最多重试 1 次，可用 `DASHSCOPE_TIMEOUT_SECONDS` 和
`DASHSCOPE_MAX_RETRIES` 在模板允许范围内调整。

然后启动：

```bash
python run.py
```

API 默认监听 `http://127.0.0.1:8000`。数据库表会在应用启动时初始化。首次运行新版本会执行分身/会话版本迁移，为旧账号创建私有分身和默认会话，回填旧消息归属；更新已有部署前请按部署手册备份数据库与媒体。迁移失败会回滚该迁移并阻止启动。

### 2. 前端

Node.js 20+；锁文件已提交，优先使用 `npm ci`。

```bash
cd frontend
npm ci
npm run dev
```

打开 `http://localhost:3000`。开发环境默认通过 Next rewrite 将 `/api/*` 转发到 `http://localhost:8000/*`，不需要额外配置前端 API 地址。

登录后从侧栏“分身”打开设置面板，也可直接访问 `/agents/me`，再回到聊天页创建或切换会话。名片默认私有；公开后只展示名称、头像和简介等安全字段。清空记忆会同时清除分身私有记忆和旧个人画像，聊天记录保留。

聊天输入区点击“生成图片”，选择 `1:1`、`16:9` 或 `9:16` 后填写画面描述；也可以直接发送“帮我生成一张薄雾古庙图片”。每次生成一张，可在气泡中放大和下载，刷新会话仍可查看。默认使用 `qwen-image-3.0` 和已有 `DASHSCOPE_API_KEY`，可通过 `QWEN_IMAGE_MODEL` 配置；单次生成和下载总超时 150 秒，不自动重试，失败可手动重试。生成图仅会话所属用户可访问，删除消息或会话时清理已无引用的文件。

需要调整已有图片时，点击该图的“以此图修改”，还可在其他图上点“加入参考”，或点击输入区“上传参考图”从电脑选择图片。本地图片和当前对话生成图可以混用，合计最多 3 张；本地支持 PNG、JPEG、WebP，每张不超过 5MB。输入区按选择顺序显示图1、图2、图3，可以移除或调整顺序，再输入例如“用图1的人物、图2的场景、图3的色调”。本地图片会纠正方向、移除元数据并适配模型尺寸，发送修改指令时才上传；比例超过 4:1 的图片需先裁剪。默认沿用处理后图1的尺寸，每次修改产生一张新图；全部参考图、顺序和修改要求都保存在对话里，新图也能继续作为参考。取消参考或切换会话会退出编辑，失败重试仍使用原先那组图与顺序。普通聊天的图片附件仍用于看图聊天。

侧栏“分身广场”或 `/agents` 可浏览其他公开分身。双方先公开名片，发起方填写主题与回复次数，对方在“收到的邀请”中接受后开始交流。双方合计最多 6 次回复，随后生成一次总结；任何一方可以立即停止。交流仅使用公开名片与当前交流内容，不读取人格设定、私聊或私有记忆。记录仅双方可见；关闭公开名片会停止待处理与进行中的交流。所有交流模型调用都带基础安全规则。内测阶段会消耗平台模型用量，不扣草莓，也不执行外部工具。

一个人也可在广场默认的“单人体验”中选择“创意搭档”“脚本编辑”或“短视频创意搭档”。它们是平台官方 AI，没有真人主人，也不占用用户账号。填写主题并点击“开始讨论”后，进入“主创初稿 → 官方审稿 → 主创修订”的作品协作。你的分身提交完整稿件，官方搭档核对原始要求并列出修订意见。默认双方合计最多 99 次，可填写 2–99 的整数；审稿通过即提前结束，直接保留通过审稿的完整版本，在“体验记录”查看。无需公开自己的名片或注册第二个账号；仅使用自己的分身名称、简介与本次讨论，不读取人格设定、私聊或私有记忆，记录仅本人可见。关闭名片公开不会停止官方体验，可用“停止交流”结束。

“短视频创意搭档”专门从零发展短片创意：人物冲突、前三秒钩子、剧情反转，逐步细化成分镜、台词、音效和时长安排。结束时按讨论结果整理带时间段的剧本；遵循话题指定的时长，未指定时以 30–60 秒为起点。它负责剧本讨论，不直接生成视频。

单人体验的话题支持最多 10,000 字，可填写人物设定、剧情背景、风格与时长要求，后端完整保存并提供给每次写稿和审稿；最新完整作品和最近审稿意见也会完整保留在模型上下文中。长话题在详情中默认显示预览，可展开阅读、滚动或复制全文。与其他用户分身的邀请主题仍最多 300 字。

新创作的详情顶部展示“当前作品”，可下载作品 Markdown、`README.md`（完整稿件、原始需求和审核状态）以及完整讨论 Markdown（全部写稿、审稿和修订过程）。审稿通过标为“AI 审稿通过 · 待你验收”；达到次数上限、重复无进展、输出不完整或手动停止时保留草稿。历史讨论继续提供原有 README 与完整讨论导出，无需重新调用模型。下载权限与查看交流一致。

官方搭档支持独立模型：在后端 `.env` 配置 `OFFICIAL_EXCHANGE_PROVIDER=deepseek`、`OFFICIAL_EXCHANGE_MODEL=deepseek-v4-pro` 和 `DEEPSEEK_API_KEY` 后重启后端，官方审稿及历史流程的体验总结使用 DeepSeek V4 Pro，自己的分身继续使用 Qwen 主模型。未配置时官方搭档也使用 DashScope。模型名称显示在官方名片中，密钥仅留在后端；不会在供应商失败时暗中回退到另一个模型。DeepSeek 使用[官方接口](https://api-docs.deepseek.com/quick_start/)。

Windows 也可以在根目录运行 `start.ps1`，它会分别打开后端和前端进程。

## 登录与本地调试

- 内测登录使用邀请码：`POST /auth/redeem-invite`。
- 浏览器登录成功后使用服务端签发的 `HttpOnly` Cookie；退出登录会撤销该账号此前签发的会话。
- `backend/seed_invites.py` 用于创建绑定新 `testerNN` 用户名的邀请码，编号不会与现有账号或邀请码绑定名重复；`backend/manage_invites.py` 用于查看、撤销和轮换邀请码。
- 生产私聊先原子预扣 10 颗草莓，只对已保存的模型回复、已生成并保存的图片或成功的真实工具结算；失败、缺参追问和桌面占位工具会退还。`STRAWBERRY_DAILY_REFILL` 可配置每日补到至少指定余额（默认 `0` 为关闭），管理员可用 `backend/manage_strawberries.py` 手动补充。
- 自伤或自杀表达优先进入危机支持流程，不执行工具或普通镜子话术；服务端固定附上求助资源，此轮不收费。普通私聊和分身交流的模型提示词均带基础安全规则。
- `DEV_MODE=1` 时开放 `/auth/test-login` 和 `X-Dev-User` 调试通道。
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
