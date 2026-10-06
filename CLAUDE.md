# Fiona / Chloe 开发上下文

个人 AI 分身交流与 Skill 平台，当前第一阶段支持独立分身和持久私有会话，用于作者自用和受控小范围内测。分身互聊与 Skill 交易尚未实现。完整说明见 `README.md`，实际数据流见 `docs/ARCHITECTURE.md`，当前风险和路线图见 `PLAN.md`。

## 当前架构

- `backend/`：FastAPI + SQLite `fiona.db`，入口 `main.py`，通过 `run.py` 监听 `127.0.0.1:8000`。
- `frontend/`：Next.js 16.2.6 App Router + React 19，开发端口 3000。
- `desktop/`：Tauri 2 Windows 壳；有配置时建 SSH 隧道，无配置时加载 `https://madchloechat.online`（线上服务已于 2026-09-25 下线，该地址当前不可用）。
- 模型：DashScope/Qwen；主力 `qwen3.8-omni-flash`，轻量 `qwen3.8-flash`，图片 `qwen-vl-max`，搜索/热点 `qwen-plus`，语音使用 Qwen ASR 和 DashScope TTS。
- 数据：SQLite、`backend/uploads/`、`backend/.env` 都是本机/单机状态，不进入 Git。

## 核心模块

- 聊天主流程：`backend/routers/chat.py`、`backend/services/chat_service.py`
- 分身与会话：`backend/agent_store.py`、`backend/routers/agents.py`、`backend/routers/conversations.py`；消息必须绑定已验证的会话 ID。
- 私有记忆：分身独立 JSON 和修订号；新会话不得写入旧社会画像或触发旧自动匹配。名片只使用显式公开字段。
- Persona/成长状态：`backend/persona.py`、`backend/avatar_state.py`、`backend/state_probe.py`
- 画像与匹配：`backend/extractor.py`、`backend/conversation_matcher.py`、`backend/matcher.py`
- API：`backend/routers/` 下的 auth/chat/hot/match/me/peer/plaza/voice
- 工具：`backend/tools/`
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
- 生产私聊每次实际交付结算 10 颗草莓，并发预扣原子化；`STRAWBERRY_DAILY_REFILL` 默认关闭，可按 Asia/Shanghai 自然日补到下限。`DEV_MODE=1` 跳过预扣。
- 官方体验不扣草莓，生产限流开启时默认每账号每天北京时间自然日 3 次；热点展开、卡片详情、ASR 默认分别 30、30、300 次，四个 `FIONA_DAILY_*` 配置调用时读取。官方创建用数据库事务计数，其他三项用进程内存计数，重启清零；本地校验通过后计数，上游失败不退还，开发模式或限流器关闭时跳过。
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
- 热点来源和网页卡片已经统一经过公网 HTTP(S) 校验、DNS/IP 固定、逐跳重定向检查和响应大小限制。
- Layer 2 双边卡片、双方偏好验证、手动匹配输出约束和跨用户画像最小化已完成；候选原始消息不得进入匹配模型。
- 完整账户删除会清理数据库关联记录、关闭真人连接，并通过持久化队列重试无引用上传文件；关键后台写入必须继续防止删号后重建数据。
- 总请求体、Chat/图片、ASR、TTS、帖子和分页已有应用层边界；模型并发、真实 usage 与持久化成本控制仍未完成。
- 聊天和广场图片在线程中纠正方向、按原格式逐帧重建去元数据，仅保留 ICC；MPO 只存主帧，动图有限帧和总像素，并发重编码最多 2，广场在线程派发前排队，聊天等待槽位超时返回 503。广场视频依赖 ffmpeg 无损 remux，清 metadata、章节、数据和字幕轨，失败拒绝上传。上传目录内临时文件原子落盘，权限 0600；广场失败或取消、聊天同步处理失败及等待线程期间取消会清理，线程完成后的消息写库取消窗口仍保留。启动清扫超过 1 小时的上传临时文件，点文件不提供静态访问且不进入媒体备份。旧文件清理脚本默认 dry-run，跳过已清理图片，apply 有失败返回非零并保留原权限。语音合成仅保留 HTTP/流式接口，真人 Peer WebSocket 保留。
- 模型预算是进程内估算，不等同于供应商真实账单；草莓预扣、退款及每日补给已实现原子化，真实 usage 与持久化成本控制仍待完成。
- 私聊未命中危机信号的轮次，所有 system 消息合计恰好包含一次基础安全规则，放在最后一条 system 消息末尾；请求朗读时，朗读强约束仍作为当前 user 消息后的独立 system 消息。明确危机轮跳过普通模式、工具与待补参数，固定附上求助资源；余额足够时照常预扣并按交付结算，余额不足时免费返回资源且不调用模型。可能相关的轮次保留普通处理和计费，文字、工具、图片以及服务端能控制的错误路径均恰好送达一次资源；余额不足时先送资源再报错；进入路由前的 422 校验和 429 限流是例外。图片模式的明确危机轮按文字回复显示。繁体危机文字只在分类时归一，不改存库和显示原文。分身交流每条 system 消息也带基础安全规则。测试在收集阶段强制使用会话临时数据库与上传目录。
- 前端主页面和常驻抽屉 iframe 有已知性能与维护债务。
- Persona、成人内容、AI 身份披露、年龄与危机处理政策必须在扩大内测前统一。

## 工作约定

- 优先修复可复现问题，避免无关重构。
- 不提交 `.env`、数据库、上传文件、备份或 `fiona.config.json`。
- 代码改变模型、路由、端口、环境变量、数据位置或部署方式时，同步更新 README、架构/部署文档和 PLAN。
- 只有作者明确要求时才提交 Git commit。
