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
- 内测登录使用邀请码，`backend/seed_invites.py` 原子分配不会与现有用户或邀请码绑定名冲突的 `testerNN` 用户名。
- `backend/manage_invites.py` 查看、撤销和轮换邀请码；这些操作会使绑定账号的旧会话失效。`backend/manage_strawberries.py` 可查看、补充或设置草莓。三个脚本在导入数据库前加载服务环境文件，生产执行时明确传 `--env-file /etc/fiona/fiona.env`，并核对输出的数据库绝对路径；只有首次建库才传 `--init-db`。
- 生产私聊每次实际交付结算 10 颗草莓，并发预扣原子化；`STRAWBERRY_DAILY_REFILL` 默认关闭，可按 Asia/Shanghai 自然日补到下限。`DEV_MODE=1` 跳过预扣。
- 浏览器 JWT 只在 `HttpOnly` Cookie 中；HTTP/WebSocket 每次鉴权都核对数据库会话版本，不能恢复 query token 或 JavaScript 可读存储。
- `DEV_MODE=1` 才开放测试登录和 `X-Dev-User`。
- 单域名环境不设置 `NEXT_PUBLIC_API_BASE`；前端相对 `/api` 由 Next rewrite 或生产 Nginx 转发。

## 生产拓扑

- Nginx 443：`/` → Next.js 3000，`/api/` → FastAPI 8000 并移除前缀，`/uploads/` → FastAPI。
- systemd：`fiona` 启动后端，`fiona-web` 启动 `next start`。
- 原线上服务器（域名 `madchloechat.online`）已于 2026-09-25 关闭，当前没有在线部署；下线记录见 `docs/DEPLOYMENT.md`。重新部署时以部署手册为准，不要假定任何服务器仍在运行。
- 所有生产命令、备份和回滚步骤以 `docs/DEPLOYMENT.md` 为准；仓库文档不能证明外部服务器的即时状态。

## 当前重要边界

- 这是 SQLite 单机内测架构，不要宣称已经支持 PostgreSQL 或无限并发。
- 远程 Tauri capability、Windows `open_url` 和 CSP 已完成代码整改；桌面公开发布仍需 Windows/Rust 复核、签名和发布验证。
- 热点来源和网页卡片已经统一经过公网 HTTP(S) 校验、DNS/IP 固定、逐跳重定向检查和响应大小限制。
- Layer 2 双边卡片、双方偏好验证、手动匹配输出约束和跨用户画像最小化已完成；候选原始消息不得进入匹配模型。
- 完整账户删除会清理数据库关联记录、关闭真人连接，并通过持久化队列重试无引用上传文件；关键后台写入必须继续防止删号后重建数据。
- 总请求体、Chat/图片、ASR、TTS、帖子和分页已有应用层边界；模型并发、真实 usage 与持久化成本控制仍未完成。
- 模型预算是进程内估算，不等同于供应商真实账单；草莓预扣、退款及每日补给已实现原子化，真实 usage 与持久化成本控制仍待完成。
- 私聊非危机轮的所有 system 消息合计恰好包含一次基础安全规则，放在最后一条 system 消息末尾；请求朗读时，朗读强约束仍作为当前 user 消息后的独立 system 消息。危机轮跳过普通模式与工具，固定附上求助资源且不计费。分身交流每条 system 消息也带基础安全规则。测试在收集阶段强制使用会话临时数据库与上传目录。
- 前端主页面和常驻抽屉 iframe 有已知性能与维护债务。
- Persona、成人内容、AI 身份披露、年龄与危机处理政策必须在扩大内测前统一。

## 工作约定

- 优先修复可复现问题，避免无关重构。
- 不提交 `.env`、数据库、上传文件、备份或 `fiona.config.json`。
- 代码改变模型、路由、端口、环境变量、数据位置或部署方式时，同步更新 README、架构/部署文档和 PLAN。
- 只有作者明确要求时才提交 Git commit。
