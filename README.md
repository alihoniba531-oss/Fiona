# Fiona / Chloe

Fiona 是一个面向作者自用和小范围内测的 AI 陪伴与社交连接产品。用户可以与 Chloe 对话，由系统持续形成用户画像，并在用户同意后推荐可能合适的人；产品同时包含联网工具、语音、热点广场、社群和双方同意后的真人聊天。

> 当前定位是小规模内测版本，不是已经完成安全加固的公开 SaaS。发布范围和已知阻断项见 [PLAN.md](./PLAN.md)。

## 当前能力

- 陪伴对话：流式回复、长期画像、成长阶段、人设与对话模式路由。
- 模型与工具：Qwen 主力/轻量模型、视觉理解、联网搜索、热点展开、旅行规划等。
- 语音：浏览器录音、Qwen ASR、TTS HTTP/流式/WebSocket。
- 社交连接：两层候选匹配、待接受卡片、双方接受后的真人房间和历史消息。
- 广场与社群：热点、发帖、图片/短视频上传、点赞、兴趣与时间偏好。
- 多端：Next.js Web/PWA，以及加载开发隧道或公网网站的 Tauri 2 Windows 客户端。

## 技术栈

| 层 | 当前实现 |
|---|---|
| Web | Next.js 16.2.6、React 19、Tailwind CSS 4、React Three Fiber |
| API | FastAPI、Uvicorn、Pydantic、SlowAPI |
| 模型 | DashScope / Qwen（主力、轻量、视觉、搜索、ASR、TTS） |
| 数据 | SQLite `backend/fiona.db`，上传文件位于 `backend/uploads/` |
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

然后启动：

```bash
python run.py
```

API 默认监听 `http://127.0.0.1:8000`。数据库表会在应用启动时初始化。

### 2. 前端

Node.js 20+；锁文件已提交，优先使用 `npm ci`。

```bash
cd frontend
npm ci
npm run dev
```

打开 `http://localhost:3000`。开发环境默认通过 Next rewrite 将 `/api/*` 转发到 `http://localhost:8000/*`，不需要额外配置前端 API 地址。

Windows 也可以在根目录运行 `start.ps1`，它会分别打开后端和前端进程。

## 登录与本地调试

- 内测登录使用邀请码：`POST /auth/redeem-invite`。
- 浏览器登录成功后使用服务端签发的 `HttpOnly` Cookie；退出登录会撤销该账号此前签发的会话。
- `backend/seed_invites.py` 用于创建绑定用户名的邀请码；`backend/manage_invites.py` 用于查看、撤销和轮换邀请码。
- `DEV_MODE=1` 时开放 `/auth/test-login` 和 `X-Dev-User` 调试通道。
- 生产环境必须使用 `DEV_MODE=0` 和足够强的 `JWT_SECRET`。

邀请码管理示例：

```bash
cd backend
python manage_invites.py list
python manage_invites.py revoke ABCD2345
python manage_invites.py rotate ABCD2345
```

设置页支持退出登录和完整账户删除。删号会清除账号关联数据库记录，并立即清理无引用上传文件；失败的文件清理会进入持久化队列，在后端下次启动时重试。

不要提交 `backend/.env`、`backend/fiona.db`、`backend/uploads/` 或 `desktop/fiona.config.json`。

## 检查与构建

后端：

```bash
cd backend
python -m pytest -q
python -m compileall -q .
python -m pip check
```

请使用 `python -m pytest`；当前直接调用某些环境中的 `pytest` 命令可能无法找到后端顶层模块。

前端：

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

当前 TypeScript、Lint 和生产构建都通过；Lint 仍有非阻断警告，合并前应以 [PLAN.md](./PLAN.md) 中的当前质量状态为准。

桌面端构建和安装见 [desktop/README.md](./desktop/README.md)。

## 部署

当前目标生产形态是同一台服务器上的 Nginx + systemd：

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
