# Fiona 生产部署手册

本文把仓库当前采用的“单机、单域名、Nginx + systemd”拓扑写成可执行的基线。当前约定的线上域名是 `madchloechat.online`，代码目录是 `/root/Fiona`。

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
    backend/fiona.db
    backend/uploads/
    backend/.env
```

该拓扑目前只支持单个后端实例。SQLite 和进程内预算计数器不适合直接横向扩容。

## 前置条件

- Linux 云服务器
- Git
- Python 及 `venv`
- Node.js 20+ 和 npm
- Nginx
- systemd
- 域名 DNS 已指向服务器
- Certbot 或等价 TLS 证书管理工具
- 有效的 DashScope API Key

建议只对公网开放 22、80 和 443，端口 3000、8000 仅监听或仅允许本机访问。

## 首次安装

以下命令假设仓库位于 `/root/Fiona`。若使用专用部署用户，请同步替换目录和 systemd 权限。

```bash
cd /root
git clone <Fiona 仓库地址> Fiona
cd /root/Fiona/backend
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

编辑 `/root/Fiona/backend/.env`：

```dotenv
DASHSCOPE_API_KEY=<真实 DashScope Key>
JWT_SECRET=<足够长的随机字符串>
DEV_MODE=0
```

可以使用下面的命令在服务器上生成 JWT Secret：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

不要把命令输出粘到聊天、工单或版本库中。

安装并构建前端：

```bash
cd /root/Fiona/frontend
npm ci
npm run build
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

[Service]
Type=simple
WorkingDirectory=/root/Fiona/backend
EnvironmentFile=/root/Fiona/backend/.env
ExecStart=/root/Fiona/backend/.venv/bin/python /root/Fiona/backend/run.py
Restart=on-failure
RestartSec=3
TimeoutStopSec=30

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

[Service]
Type=simple
WorkingDirectory=/root/Fiona/frontend
Environment=NODE_ENV=production
ExecStart=/usr/bin/npm run start -- -H 127.0.0.1 -p 3000
Restart=on-failure
RestartSec=3
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

加载并启动：

```bash
systemctl daemon-reload
systemctl enable --now fiona fiona-web
systemctl status fiona fiona-web
```

如果未来改用专用服务用户，需要确保该用户可读代码和 `.env`，并可写 `backend/fiona.db`、数据库所在目录和 `backend/uploads/`。

## Nginx

下面是与当前路由约定匹配的站点基线。`/api/` 的 `proxy_pass` 末尾斜杠用于移除 `/api` 前缀，因为 FastAPI 实际端点是 `/chat`、`/match` 等，而不是 `/api/chat`。

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

启用站点后先检查配置：

```bash
nginx -t
systemctl reload nginx
```

再用 Certbot 或现有证书流程启用 443 和 HTTP → HTTPS 跳转。证书配置由部署环境生成，不应把私钥提交到仓库。

## 首次验证

先验证本机进程：

```bash
curl --fail http://127.0.0.1:8000/
curl --fail http://127.0.0.1:3000/
```

再验证公网：

```bash
curl --fail https://madchloechat.online/
curl --fail https://madchloechat.online/api/
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

账户删除是破坏性操作，只能用专门创建的一次性测试账号验证。确认该账号的消息、匹配、真人消息、广场帖子和媒体文件都已删除，并检查后端日志没有文件清理失败。

`/api/` 返回 FastAPI 根健康响应，但这只是进程级检查，不代表数据库、DashScope、搜索源和 WebSocket 全部健康。

## 日常发布

每次发布前先记录当前提交并备份状态：

```bash
cd /root/Fiona
git rev-parse HEAD
mkdir -p /root/fiona-backups
sqlite3 backend/fiona.db ".backup '/root/fiona-backups/fiona-$(date +%Y%m%d-%H%M%S).db'"
tar -C backend -czf "/root/fiona-backups/uploads-$(date +%Y%m%d-%H%M%S).tar.gz" uploads
```

然后更新、验证和重启：

```bash
cd /root/Fiona
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

数据库兼容 DDL 会在后端启动时执行。本轮会增加 `users.session_version`、邀请码撤销/用量字段、`posts.owner_username` 和 `upload_cleanup_queue`。后端启动还会回填可识别的旧帖子 owner，并重试队列中的文件清理。由于当前没有版本化迁移和自动回滚，任何涉及 `database.py` 的发布都必须先同时备份数据库与上传目录。

## 邀请码与会话运维

在后端目录运行本机管理命令：

```bash
cd /root/Fiona/backend
.venv/bin/python manage_invites.py list
.venv/bin/python manage_invites.py revoke ABCD2345
.venv/bin/python manage_invites.py rotate ABCD2345
```

撤销和轮换会使绑定账号当前所有 JWT 失效，操作前应确认目标用户名；轮换命令会打印新码，应只通过受控渠道发给对应测试者。邀请码仍可重复用于登录，因此不应公开写入日志、工单或群聊。

## 日志与故障排查

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
4. `backend/.env` 是否缺少 Key，且文件权限是否正确。
5. `backend/fiona.db` 和 `backend/uploads/` 是否可写。
6. SSE 是否被代理缓冲，WebSocket Upgrade 头是否保留。
7. DashScope 或外部热点源是否发生超时/额度问题。

## 回滚与恢复

代码回滚应使用发布前记录的提交或正式发布标签，重新安装依赖、重新构建前端，再重启两个服务。不要只恢复 `.next` 目录。

如果新版本已经改变 SQLite schema，应优先恢复发布前数据库备份，再启动旧代码；同时恢复匹配时间点的 `uploads` 备份，避免消息记录和文件不一致。

恢复前先停后端：

```bash
systemctl stop fiona
```

确认备份文件和目标路径后再执行恢复，并在恢复完成后重新启动、检查日志和跑完整冒烟测试。生产数据库恢复属于破坏性操作，不应在没有确认备份的情况下临时尝试。

## 发布前安全检查

- `DEV_MODE=0`，`JWT_SECRET` 不是开发默认值。
- HTTPS 正常，登录响应的 `fiona_token` Cookie 带 `Secure`、`HttpOnly` 和 `SameSite=Lax`；HTTP/WebSocket URL 中没有 Token。
- `.env`、数据库、上传目录和备份不可被 Nginx 静态暴露。
- `/api/docs` 是否需要在公网关闭或额外保护。
- Nginx 请求体、连接、速率和超时限制符合当前容量。
- 桌面端发布前已完成 Tauri capability、URL opener 和 CSP 整改。
- 已处理 [PLAN.md](../PLAN.md) 中所有标为“发布阻断”的项目。
- 已用一次性测试账号验证完整账户删除和失败文件清理重试。
- 已确认成人内容、未成年人和危机干预政策与代码一致。
