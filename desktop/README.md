# desktop/ — 菲欧娜桌面客户端

Tauri 2 桌面壳。Dev 阶段加载 SSH 转发的云端 `http://localhost:3000`，所有
API/WebSocket 通过 next 的 rewrite 自动落到云端 backend。Windows 用户拿到的
是一个独立窗口的 .exe，但内核还是云上的菲欧娜。

## 部署形态

```
        Windows (你的电脑)                       云服务器
┌────────────────────────────────┐      ┌─────────────────────┐
│  Tauri .exe                    │      │                     │
│   └─ WebView2                  │      │  next dev :3000     │
│       └─ http://localhost:3000 │◀────▶│   └─ /api → :8000   │
│                                │ SSH  │      ↓              │
│  (Rust/Cargo, Node, WebView2)  │ 转发 │  python run.py :8000│
└────────────────────────────────┘      └─────────────────────┘
```

## 第一次使用（Windows）

1. **git pull** 把这个 `desktop/` 目录拉下来
2. 右键 `setup.ps1` → 用 PowerShell 运行 — 装 Rust + tauri-cli + npm 依赖（10-15 分钟，一次性）
3. 装完会让你重开 PowerShell 一次（让 PATH 生效）
4. 开一个 SSH 终端做端口转发：
   ```
   ssh -L 3000:127.0.0.1:3000 root@<云IP>
   ```
5. 在云端 SSH 里启动 backend + frontend（同你平时的流程）
6. Windows 这边浏览器打开 `http://localhost:3000` 确认能用网页
7. 回 desktop/，运行 `.\dev.ps1` — 弹出桌面窗口

## 之后每次

- 开 SSH 转发 + 云端 backend/frontend 在跑
- desktop/ 下 `.\dev.ps1`

## 文件说明

- `package.json` — 装 `@tauri-apps/cli` 提供 `tauri` 命令
- `src-tauri/Cargo.toml` — Rust 端依赖（Tauri 2 + serde）
- `src-tauri/tauri.conf.json` — 主配置，**`build.devUrl` 决定加载哪个 URL**
- `src-tauri/src/main.rs` + `lib.rs` — 入口，目前是纯壳子无自定义逻辑
- `src-tauri/capabilities/default.json` — 权限（dev 只开 core:default 够用）
- `src-tauri/icons/icon.png` — 从 `frontend/public/icons/icon-512.png` 复制
- `setup.ps1` — 一键装环境
- `dev.ps1` — 启动 dev 窗口
- `build.ps1` — release 打包（暂时还不能用，见脚本里的说明）

## 后续要做的事（不阻塞 dev）

- 接 `tauri-plugin-store` 把 token 从 localStorage 迁到 OS keychain
- 接 `tauri-plugin-notification` 接桌面通知
- 想 prod build .exe 分发：`frontend/next.config.ts` 加 `output: "export"`，
  把 fetch 改成走 `NEXT_PUBLIC_API_BASE`，后端 CORS 放行 `tauri://localhost`
- 用 `cargo tauri icon path/to/1024.png` 生成全套图标（dev 单张 icon.png 就够）
