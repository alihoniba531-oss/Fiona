# 菲欧娜 / Chloe

个人 AI 陪伴产品：用户跟"Chloe"聊天，附带匹配、广场等社交功能。作者自用 + 小范围内测。

## 架构
- **后端** `backend/`：FastAPI + SQLite（`fiona.db`），uvicorn 跑在 `127.0.0.1:8000`。
  入口 `main.py`，人设 `persona.py`，鉴权 `auth.py`（JWT，`DEV_MODE=1` 时放行 X-Dev-User）。
  成长阶段 `avatar_state.py`（空→镜像→完整分身，按消息总数 `count_messages` 路由）。
- **前端** `frontend/`：Next.js **16**（App Router），dev 端口 3000。
  ⚠️ 见 `frontend/AGENTS.md`：这是魔改版 Next，写前端代码前先读 `node_modules/next/dist/docs/`。
  后端地址统一走 `lib/config.ts`（`API_BASE`/`WS_BASE`，不设环境变量则相对 `/api`）。
- **桌面** `desktop/`：Tauri 2 壳。`src-tauri/src/lib.rs` 是启动逻辑，`dist/index.html` 是加载页。
  Windows 打包脚本 `desktop/build.ps1` → 出 `.msi`/`.exe`（Linux 打不了，必须 Windows）。

## 桌面壳两种模式（同一个 .msi 自适应）
- **开发者模式**：检测到 `fiona.config.json`（云 IP + SSH）→ 建 SSH 隧道 → 加载 `localhost:3000`。
- **用户模式**：无 config → 不建隧道 → 直接加载公网 `https://madchloechat.online`。给内测者发的就是不带 config 的用法。

## 部署拓扑（Plan B，单域名）
- 阿里云 ECS 新加坡，公网 IP `47.236.249.77`，域名 `madchloechat.online`（免备案）。
- Nginx（443，certbot 证书）：`location /api/ → 127.0.0.1:8000`（后端），`location / → 127.0.0.1:3000`（前端）。
- 两个 systemd 服务：`fiona`（uvicorn 8000）、`fiona-web`（`next start` 3000）。
- 前后端同源 → 无 CORS、相对 `/api` 直通、`/uploads` 靠同源 cookie。
- 代码在服务器 `/root/Fiona`（GitHub `Fiona.git`）；`backend/.env` 不入库，`DEV_MODE=0` + 强 `JWT_SECRET`。

## 登录
内测用**邀请码**（短信 `send_sms` 是 stub，未接真实服务商）。
`POST /auth/redeem-invite` 输码即登录；`backend/seed_invites.py` 种码（绑 tester01..N）。

## 约定
- 改动只修真 bug（作者自用阶段）；简单优先。
- 提交需作者明确要求；`.env`/`fiona.config.json` 永不入库。
