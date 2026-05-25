# desktop/ — 菲欧娜桌面客户端

Tauri 2 桌面壳 + 嵌入式 SSH 隧道。**双击 .exe 自动连云、自动加载、关窗自动清理**，
不用每次手动开终端转发端口。

## 部署形态

```
       Windows (你的电脑)                          云服务器
┌──────────────────────────────────┐      ┌──────────────────────┐
│ Tauri .exe                       │      │                      │
│  ├─ 子进程: ssh -N -L 3000:..    │◀────▶│  next dev :3000      │
│  └─ WebView2                     │ SSH  │   └─ /api → :8000    │
│      └─ http://localhost:3000    │ 隧道 │      ↓               │
│                                  │      │  python run.py :8000 │
└──────────────────────────────────┘      └──────────────────────┘
```

启动顺序（Tauri 进程内部）：
1. 读 `fiona.config.json` 拿云 IP / 用户 / 端口
2. spawn `ssh -N -L <forwards> user@host` 子进程
3. 轮询 `localhost:<前端端口>` 通了再开窗（最长等 15 秒）
4. WebView2 加载 `http://localhost:3000`
5. 关窗时 kill 子进程

## 第一次使用（Windows）

1. **git pull** 把这个 `desktop/` 目录拉下来
2. **配 SSH 免密**（如果还没配过）：
   ```powershell
   ssh-keygen -t ed25519                   # 没密钥才需要，全部回车
   type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<云IP> 'cat >> ~/.ssh/authorized_keys'
   ```
   做完之后 `ssh root@<云IP>` 应该直接进，不再问密码。
3. 在 `desktop/` 右键 `setup.ps1` → 用 PowerShell 运行：
   - 装 Rust + tauri-cli + npm 依赖（10-15 分钟）
   - 交互式问云端 IP/用户/端口
   - 测试 SSH 免密
4. 重开 PowerShell（让 PATH 生效）
5. 双击 `dev.ps1` 或运行 `.\dev.ps1` — 弹出菲欧娜窗口

## 之后每次

只需保证 **云端 backend + next dev 在跑**，然后双击 `dev.ps1`。
不用手开终端、不用手起隧道，关窗就自动清理。

## 想做桌面快捷方式

右键桌面 → 新建快捷方式 → 目标：
```
powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\path\to\desktop\dev.ps1"
```
图标用 `src-tauri\icons\icon.png`。

## 文件说明

- `package.json` — 装 `@tauri-apps/cli` 提供 `tauri` 命令
- `fiona.config.example.json` — 示例配置（实际配置 `fiona.config.json` 已 gitignore）
- `src-tauri/Cargo.toml` — Rust 依赖（Tauri 2 + serde + serde_json）
- `src-tauri/tauri.conf.json` — 主配置，**`build.devUrl` 决定加载哪个 URL**
- `src-tauri/src/main.rs` + `lib.rs` — 入口 + SSH 隧道嵌入逻辑
- `src-tauri/capabilities/default.json` — 权限
- `src-tauri/icons/icon.png` — 从 `frontend/public/icons/icon-512.png` 复制
- `setup.ps1` — 一键装环境 + 写云端配置
- `dev.ps1` — 启动 dev 窗口
- `build.ps1` — release 打包（待 next output: export 准备好）

## 后续要做的事（不阻塞当前 dev）

- 接 `tauri-plugin-store` 把 token 从 localStorage 迁到 OS keychain
- 接 `tauri-plugin-notification` 接桌面通知
- 想 prod build .exe 分发：`frontend/next.config.ts` 加 `output: "export"` +
  fetch 走 `NEXT_PUBLIC_API_BASE` + 后端 CORS 放行 `tauri://localhost`
- 用 `cargo tauri icon path/to/1024.png` 生成全套图标
