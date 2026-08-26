# Fiona 当前架构

本文描述仓库在 2026-08-26 的实际代码结构。它是实现说明，不替代 [PLAN.md](../PLAN.md) 中的路线图和发布决策。

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

开发环境仍使用相同的相对 `/api` 地址，但由 `frontend/next.config.ts` 直接 rewrite 到本机 FastAPI。

## Web 前端

前端位于 `frontend/`，使用 Next.js 16 App Router 和 React 19。

| 路由 | 当前职责 |
|---|---|
| `/` | Chloe 主对话、图片、语音、工具卡片和抽屉容器 |
| `/login` | 邀请码登录 |
| `/match` | 待接受匹配和匹配响应 |
| `/plaza` | 热点、发帖、媒体、点赞和兴趣信息 |
| `/community` | 社群兴趣展示 |
| `/profile` | 用户画像 |
| `/history` | 对话历史、删除和导出 |
| `/settings` | 用户偏好和产品设置 |

重要共享模块：

- `frontend/lib/config.ts`：HTTP/WebSocket API 基址的唯一来源。
- `frontend/lib/auth.ts`：本地展示身份、Cookie 请求和统一 401 会话失效处理；不读取 JWT。
- `frontend/proxy.ts`：页面级 Cookie 门禁。
- `frontend/components/`：聊天、导航、HUD 和 3D 场景。

主页面目前会保留多个抽屉 iframe 的挂载状态。这是当前行为，不是推荐的长期架构；拆分和懒加载计划记录在 [PLAN.md](../PLAN.md)。

## FastAPI 后端

后端入口是 `backend/main.py`，启动包装是 `backend/run.py`。业务路由按领域拆分：

| 模块 | 主要端点/职责 |
|---|---|
| `routers/auth.py` | 邀请码、开发登录、预留 OTP |
| `routers/chat.py` | `/chat` SSE 对话入口 |
| `routers/voice.py` | ASR、TTS、TTS WebSocket |
| `routers/hot.py` | 热点源、分类和详情展开 |
| `routers/match.py` | 匹配生成、待接受卡片和响应 |
| `routers/peer.py` | 真人房间、历史和 WebSocket |
| `routers/plaza.py` | 广场、媒体、点赞和兴趣偏好 |
| `routers/me.py` | 设置、画像、历史、用量和草莓余额 |

聊天主流程位于 `backend/services/chat_service.py`：

1. 验证用户和草莓余额。
2. 保存用户消息和可接受的图片文件。
3. 读取近期消息、画像、成长状态和模式。
4. 根据图片、对话模式和意图选择模型或工具。
5. 通过 SSE 返回模型输出。
6. 保存回复，并在后台更新画像、状态和匹配信号。

## 模型和工具

当前模型配置以 `backend/llm.py` 和各适配器源码为准：

- `qwen3.8-max`：主力对话、匹配和复杂判断。
- `qwen3.7-flash`：轻量对话槽位，失败时回退主力模型。
- `qwen-vl-max`：用户图片和视觉搜索结果理解。
- `qwen-plus`：联网搜索、热点分类/展开和旅行规划。
- `qwen3-asr-flash`：语音识别。
- DashScope TTS：语音合成。

工具注册和路由主要位于 `backend/tools/route.py`。当前包含联网搜索、网页卡片、视觉搜索、热点、旅行、提醒、系统工具和微信相关辅助脚本。不同工具的可用性和安全边界并不完全相同，不能只依靠模型提示词作为访问控制。

## 鉴权与公开端点

HTTP 默认经过 `backend/main.py` 的鉴权中间件，身份来源优先级为：

1. `Authorization: Bearer <jwt>`
2. `fiona_token` Cookie
3. `DEV_MODE=1` 时的 `X-Dev-User`/`dev_user`

当前公开范围包括根健康响应、认证入口、API 文档、`/hot/*`，以及 Plaza 的标签、Feed 和社群兴趣三个只读端点。WebSocket 不经过 HTTP 中间件，由具体端点单独认证。

生产 JWT 使用 HS256，默认有效期 30 天，浏览器端只存于 `HttpOnly`、`SameSite=Lax` Cookie。JWT 带账号会话版本，每次 HTTP 请求和 WebSocket 握手都会与数据库核对；退出登录、撤销或轮换邀请码会使旧会话立即失效。邀请码仍绑定用户名并允许重复登录，但兑换会原子记录用量，且管理员可以用 `backend/manage_invites.py` 查看、撤销和轮换。

## 数据与文件

当前持久化完全位于单机。开发环境的默认路径为：

- SQLite：`backend/fiona.db`
- 媒体：`backend/uploads/`
- 环境变量：`backend/.env`
- 桌面开发连接：`desktop/fiona.config.json`

生产部署通过 `FIONA_DB_PATH` 和 `FIONA_UPLOADS_DIR` 将前两项放到
`/var/lib/fiona/fiona.db` 和 `/var/lib/fiona/uploads/`；API Key/JWT Secret 位于
权限为 `0600` 的 `/etc/fiona/fiona.env`，不写入只读代码目录。

SQLite 表由 `backend/database.py:init_db()` 在启动时创建，并通过容错式 `ALTER TABLE` 处理旧库字段。当前没有版本化迁移工具，也没有 PostgreSQL 实现。

主要数据域包括：用户和画像、消息、匹配、待接受卡片、真人消息、帖子/点赞、标签与时间偏好、用户成长状态、事件、OTP、邀请码和上传清理队列。

`fiona.db` 与 `uploads/` 必须作为一个隐私数据集合共同备份和清理。删除单条消息、清空历史或删除账户时，数据库会在同一事务中找出不再被消息/帖子引用的媒体并写入 `upload_cleanup_queue`；文件会立即清理，失败项在后端启动时和运行期间周期重试。新帖子在库内保存 owner；能通过当前 HMAC 或旧 MD5 匿名标识识别的历史帖子会自动回填，无法识别的旧行仍需人工处置。

## 匹配和真人连接

匹配包含两条主要路径：

- Layer 1：从近期消息和显式需求中寻找更即时的连接。
- Layer 2：基于持续画像寻找候选。

候选会经过模型评估，再写入待接受卡片和匹配记录。同一用户对的近期匹配与同层待接受卡片在数据库事务中去重；不存在的匹配不能通过响应接口被隐式创建。双方都接受后才能读取/写入真人房间；Peer WebSocket 会逐条复核会话和双方最新同意状态，并限制消息大小与发送速率。

Layer 2 会为双方创建待接受卡片；Layer 1、Layer 2 和手动匹配都会验证双方连接偏好。手动匹配还会把模型输出限制在候选集合内，并校验类型、理由和标签。跨用户模型输入只包含长度受限的兴趣、价值观、技能、阶段和城市，不读取候选的原始近期消息，并排除需求、困扰、纪念日和职业等字段。当前仍是应用层最小化，不等同于数据库租户隔离或独立隐私审计。

## 桌面客户端

`desktop/` 是 Tauri 2 壳，不内置完整 Web 前端：

- 找到 `fiona.config.json`：建立 SSH 本地端口转发，加载 `http://localhost:<port>`。
- 没有配置文件：加载 `https://madchloechat.online`。

本地隧道页面只拥有诊断、后端探测和日志相关 capability；远程页面只拥有两个受 Rust 层 HTTP(S) 校验保护的外链命令。Windows 外链不经过 `cmd.exe`，Tauri 启动页和远程 Next.js 页面均已配置 CSP。公开分发前仍需完成 [PLAN.md](../PLAN.md) 中的 Windows/Rust 构建复核、签名和发布验证。

## 运行和扩展限制

- SQLite 每次操作创建连接，尚未配置完整的并发和正式迁移策略。
- 模型预算计数是单进程内存状态，不是供应商账单或集群级配额；草莓扣费原子性与持久化成本控制按当前产品决定暂缓。
- 消息/账户删除已有引用检查和持久化文件清理周期重试；全目录孤儿扫描与保留期限尚未完成。
- ASGI 层限制总请求体为 25 MB，Chat/图片、ASR、TTS、帖子和分页还有更严格的领域边界；图片会验证真实格式、完整性和像素量。模型客户端已有明确超时和有限重试；并发边界、公共热点缓存和持久化成本上限仍需继续治理。
- 模型生成的热点/卡片 URL 通过只允许公网 HTTP(S) 的客户端访问，每次 DNS 和重定向都会重新校验并限制响应体与超时。
- 前端主页面承担职责过多，多个隐藏 iframe 会继续运行轮询或 3D 场景。
- 仓库已增加后端与 Web 质量门禁工作流；Windows 桌面工作流会运行 Rust 单测再打包。新工作流仍需在 GitHub 首次运行中确认 runner 环境。

当上述实现发生变化时，应在同一个变更中更新本文、根 README 和 PLAN 的状态。
