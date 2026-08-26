# Fiona Web

Fiona 的 Web/PWA 客户端，使用 Next.js 16.2.6、React 19、Tailwind CSS 4 和 React Three Fiber。它承载 Chloe 对话、语音、匹配、真人聊天、广场、社群、画像、历史和设置。

项目总览见 [根 README](../README.md)，后端与数据流见 [架构文档](../docs/ARCHITECTURE.md)。

## 开发约束

本项目使用的 Next.js 16 与旧版本存在 API、约定和文件结构差异。修改前端代码前，先阅读 [AGENTS.md](./AGENTS.md)，再查阅本地安装版本对应的 `node_modules/next/dist/docs/`，不要直接套用旧版 Next.js 示例。

## 页面

| 路由 | 功能 |
|---|---|
| `/` | 主聊天、语音、工具结果和功能抽屉 |
| `/login` | 邀请码登录 |
| `/match` | 匹配卡片和响应 |
| `/plaza` | 热点、广场内容和发帖 |
| `/community` | 社群兴趣 |
| `/profile` | 用户画像 |
| `/history` | 历史、导出和删除 |
| `/settings` | 用户偏好 |

这些页面中的 Plaza、Match、Community、Profile 和 Settings 目前也会以 iframe 方式挂载在主页面抽屉中。它们并不是独立的微前端，继续共享同源鉴权和 API。

## 本地运行

要求 Node.js 20+ 和 npm。

```bash
npm ci
npm run dev
```

打开 `http://localhost:3000`。同时需要在仓库的 `backend/` 目录启动 FastAPI：

```bash
python run.py
```

开发时不需要设置 API 环境变量：

- 浏览器请求相对 `/api`。
- `next.config.ts` 将 `/api/:path*` rewrite 到 `http://localhost:8000/:path*`。
- WebSocket 基址由当前页面协议和主机推导为 `/api`。

## API 配置

`lib/config.ts` 是 API 地址的唯一来源：

- 未设置 `NEXT_PUBLIC_API_BASE`：使用相对 `/api`，适用于本地开发和当前单域名生产部署。
- 设置绝对地址：HTTP 自动使用该地址，WebSocket 自动把 `http/https` 转为 `ws/wss`；构建时生成的 CSP 也会加入对应 HTTP(S)/WebSocket origin。

`NEXT_PUBLIC_*` 会在 `next build` 时内联。修改后必须重新构建，运行时再设置不会改变已经生成的前端包。

如果改成跨域 API，不能只设置这个变量；还必须同时检查后端 CORS、Cookie、上传媒体和 WebSocket 鉴权。

## 鉴权

`lib/auth.ts` 当前保存：

- `fiona_user`
- `fiona_balance`

JWT 只保存在后端签发的 `HttpOnly`、`SameSite=Lax` Cookie 中，前端 JavaScript 不读取 Token。`apiFetch` 使用 `credentials: include`；同源媒体和 WebSocket 握手由浏览器自动携带 Cookie，不再把 Token 放进 URL。生产登录使用邀请码；`DEV_MODE=1` 时可使用后端测试登录和 `X-Dev-User`。

`apiFetch` 会在后端返回 401 时清除本地展示状态并将顶层页面带回登录页。退出登录通过后端递增会话版本使旧 JWT 失效；设置页也提供需要精确输入用户名确认的完整账户删除。

## 常用命令

```bash
npm run dev
npm run lint
npx tsc --noEmit
npm run build
npm run start
```

- `npm run dev`：Turbopack 开发服务器。
- `npm run lint`：ESLint；当前无错误，仍有已记录的非阻断警告。
- `npx tsc --noEmit`：独立 TypeScript 检查。
- `npm run build`：生产构建。
- `npm run start -- -H 127.0.0.1 -p 3000`：启动已经构建的自托管生产服务。

最近一次审计中 TypeScript、生产构建和 Lint 都通过；Lint 仍报告非阻断警告，不能因为退出码为 0 就忽略这些维护债务。

## 生产部署

当前生产方式不是 Vercel，而是自托管 `next start`：

1. `npm ci`
2. `npm run build`
3. systemd 启动 `npm run start -- -H 127.0.0.1 -p 3000`
4. Nginx 将公网 `/` 转发到 3000
5. Nginx 将 `/api/` 和 `/uploads/` 转发到 FastAPI

完整配置见 [生产部署手册](../docs/DEPLOYMENT.md)。

## 当前结构注意事项

- `app/page.tsx` 目前同时负责聊天、ASR/TTS、匹配、Peer 房间、工具卡片和抽屉状态，修改时要检查跨功能回归。
- 主页面会一直保留五个抽屉 iframe；隐藏页面仍可能轮询、请求热点或运行 3D 场景。
- 麦克风、媒体播放和 WebSocket 都依赖浏览器权限与安全上下文。
- `public/sw.js` 当前主要用于清理旧 Service Worker/缓存，不提供完整离线能力；manifest 不等于离线 PWA。
- 3D 组件应继续尊重 reduced-motion，并避免在 Effect 中同步 setState。

计划中的拆分、懒加载、可访问性和测试工作统一记录在 [PLAN.md](../PLAN.md)。
