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

该拓扑目前只支持单个后端实例。SQLite 和进程内预算计数器不适合直接横向扩容。

## 2026-09-05 分身与会话迁移

新版后端首次启动会自动执行 `20260905_private_agents_v1` 事务迁移：创建分身与会话表、为既有账号建立私有分身和默认会话、复制旧画像作为私有记忆基线，并回填旧消息归属。旧社会画像保留，新会话提取的记忆之后独立保存。

分身互聊版本还会执行 `20260905_agent_exchanges_v1`，创建交流、回复及调用记录三张独立表。此迁移不改已有分身公开状态或私聊数据。继续使用单后端进程；启动时将上次中断的交流置为停止、保守结算未决用量，不自动恢复生成。多 worker/多实例需要独立的任务租约与恢复机制，当前不要直接增加 worker 数。

官方单人体验继续执行 `20260905_official_agent_exchanges_v2`，在事务中重建交流主表以支持无用户账号的官方参与者。迁移逐字段校验旧记录和子表引用，并恢复索引；失败时回滚，可修复数据后重试。请先停止写入并备份数据库。迁移不会增加虚构用户，也不会公开已有分身。

99 次官方体验还会执行 `20260905_official_exchange_limits_v3`，保留已有交流和索引/触发器，并给调用表增加供应商、模型字段；既有回复次数与内容不会被改写。配置 `OFFICIAL_EXCHANGE_PROVIDER=deepseek`、`OFFICIAL_EXCHANGE_MODEL=deepseek-v4-pro` 和服务端 `DEEPSEEK_API_KEY` 可切换官方搭档及总结的模型，自己的分身仍使用 Qwen。密钥放在忽略版本控制的后端环境配置中，不使用 NEXT_PUBLIC 变量；修改后重启单后端进程。

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
- Nginx
- systemd
- 域名 DNS 已指向服务器
- Certbot 或等价 TLS 证书管理工具
- 有效的 DashScope API Key

建议只对公网开放 22、80 和 443，端口 3000、8000 仅监听或仅允许本机访问。

## 首次安装

先创建无登录 shell 的专用服务账号和状态目录。不要让 Web 或 API 进程以 root 运行：

```bash
useradd --system --home /var/lib/fiona --shell /usr/sbin/nologin fiona
install -d -o root -g root -m 0755 /opt/fiona
install -d -o fiona -g fiona -m 0700 /var/lib/fiona /var/lib/fiona/uploads
install -d -o root -g root -m 0755 /etc/fiona /var/backups/fiona

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

| 环境变量 | 用途 |
|---|---|
| `FIONA_DB_PATH` | 服务和管理脚本使用的 SQLite 数据库路径 |
| `FIONA_UPLOADS_DIR` | 上传文件目录 |
| `STRAWBERRY_DAILY_REFILL` | 每位用户每天（Asia/Shanghai）首次经登录、`GET /strawberry` 或聊天预扣时补到至少该数量；`0` 关闭，建议值由运维决定 |

草莓正常回复每条 10 颗，预扣后只对实际交付的模型回复、图片或成功真实工具结算；失败、追问及桌面占位工具会退还。`DEV_MODE=1` 不预扣。每日补给不会降低较高余额，同一自然日仅执行一次。

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
cd /opt/fiona
git rev-parse HEAD
sqlite3 /var/lib/fiona/fiona.db ".backup '/var/backups/fiona/fiona-$(date +%Y%m%d-%H%M%S).db'"
tar -C /var/lib/fiona -czf "/var/backups/fiona/uploads-$(date +%Y%m%d-%H%M%S).tar.gz" uploads
```

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

数据库兼容 DDL 会在后端启动时执行。既有迁移增加了 `users.session_version`、邀请码撤销/用量字段、`posts.owner_username` 和 `upload_cleanup_queue`；本次增加可空列 `users.strawberry_refill_date`。后端启动还会回填可识别的旧帖子 owner，并重试队列中的文件清理。由于当前没有通用迁移和自动回滚，任何涉及 `database.py` 的发布都必须先同时备份数据库与上传目录。

## 邀请码、会话与草莓运维

在后端目录运行本机管理命令。明确传入服务使用的环境文件；脚本会在导入数据库模块前读取它，并向 stderr 显示配置文件路径与解析后的数据库绝对路径。命令行 `--env-file` 优先于 `FIONA_ENV_FILE`；未指定时依次尝试可读的 `/etc/fiona/fiona.env`、`backend/.env`。进程中已设置的环境变量仍优先。运行账号必须能读取配置文件并写入实际数据库。

三个脚本进入初始化路径时会执行与服务启动相同的兼容 DDL（只加列/索引），并可能执行旧帖 owner 回填及版本化迁移；对已有数据库运行发码、邀请码管理或草莓 `grant/set`，即使未传 `--init-db` 也会进入此路径。请先备份数据库再运行这些命令。`manage_strawberries.py list` 默认跳过初始化与迁移，以只读连接查看库内原始余额和最近补给日期，不触发每日补给；显式传 `--init-db` 时则会初始化数据库。`grant`、`set` 先应用当日补给再修改余额。

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

数据库文件不存在时，管理脚本以退出码 2 拒绝操作，不会创建空库；仅首次初始化新库时使用 `--init-db`。`seed_invites.py` 每次只输出本次新建的码及其用户名，用户名编号取已存在用户和邀请码绑定名的最大 `testerNN` 编号之后，删号不会使新码撞上存量账号。`grant` 增加 1–100000 颗，`set` 将余额设为 0–100000；不存在的用户名返回退出码 1。

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

## 回滚与恢复

代码回滚应使用发布前记录的提交或正式发布标签，重新安装依赖、重新构建前端，再重启两个服务。不要只恢复 `.next` 目录。

如果新版本已经改变 SQLite schema，应优先把备份恢复到 `/var/lib/fiona/fiona.db`，再启动旧代码；同时恢复匹配时间点的 `/var/lib/fiona/uploads/` 备份，避免消息记录和文件不一致。

恢复前先停后端：

```bash
systemctl stop fiona
```

确认备份文件和目标路径后再执行恢复，并在恢复完成后重新启动、检查日志和跑完整冒烟测试。生产数据库恢复属于破坏性操作，不应在没有确认备份的情况下临时尝试。

## 发布前安全检查

- `DEV_MODE=0`，`JWT_SECRET` 不是开发默认值。
- HTTPS 正常，登录响应的 `fiona_token` Cookie 带 `Secure`、`HttpOnly` 和 `SameSite=Lax`；HTTP/WebSocket URL 中没有 Token。
- `/etc/fiona/fiona.env`、`/var/lib/fiona` 和备份目录不可被 Nginx 静态暴露。
- 未登录访问 `/api/docs`、`/api/openapi.json` 返回 404（`DEV_MODE=0` 时后端关闭 API 文档），`/api/hot/expand` 返回 401（后端始终要求登录）；无需 Nginx 额外配置。
- Nginx 请求体、连接、速率和超时限制符合当前容量。
- 桌面端发布前已完成 Tauri capability、URL opener 和 CSP 整改。
- 已处理 [PLAN.md](../PLAN.md) 中所有标为“发布阻断”的项目。
- 已用一次性测试账号验证完整账户删除和失败文件清理重试。
- 已确认成人内容、未成年人和危机干预政策与代码一致。

## 下线记录

**2026-09-25**：作者确认原线上服务器已关闭。下线方案为“先备份，再删除服务、数据与密钥”，包括以下步骤：

1. 停止服务后，备份 SQLite、上传目录和历史备份，并拷贝到服务器以外保存。备份存放位置不记录在仓库中；备份不包含 `/etc/fiona/fiona.env`。
2. 删除 `fiona`、`fiona-web` 两个 systemd 服务、Nginx 站点、TLS 证书、代码目录、`/var/lib/fiona`、`/etc/fiona`、`/var/backups/fiona` 以及 `fiona` 服务账号。

截至同日，仍有以下事项需要作者在仓库之外处理：

- 域名 `madchloechat.online` 的 DNS A 记录仍指向原服务器 IP。云主机释放后，这个 IP 可能被分配给其他用户，应删除或改掉这条解析。
- 已安装的 Windows 桌面端在用户模式下仍会加载 `https://madchloechat.online`，远程 capability 也仍对该域名开放两个外链命令（见 `desktop/src-tauri/capabilities/remote-links.json`）。域名到期前应通知测试者卸载桌面端；如果以后放弃这个域名，重新发布桌面端时需要同时更换默认地址和 capability 白名单。
- 在 DashScope、DeepSeek 后台删除本项目使用的 API Key。

重新上线时，按本文“首次安装”一节重新部署，并用新的 `JWT_SECRET` 和新的模型密钥。
