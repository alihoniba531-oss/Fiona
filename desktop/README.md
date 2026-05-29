# desktop/ — Chloe桌面客户端

Tauri 2 桌面壳 + 可选 SSH 隧道。**双击 .exe 自动加载；开发者模式自动连云，用户模式直连公网**。

## 两条获取路径，选一条

### A. 下载 GitHub Actions 构建的 .msi（推荐 — 不用装 Rust）

1. 仓库 → **Actions** 页面 → 选最新一次 **Build Windows Desktop** 成功的 run
2. 滚到底 **Artifacts** → 下载 `fiona-desktop-msi`（解压得到 `.msi`）
3. 双击 `.msi` 安装到 Windows
4. 直接打开 Chloe。默认不需要配置文件，会加载公网 `https://madchloechat.online`

如果要用开发者模式连自己的云端 dev 服务，再创建配置文件 `%APPDATA%\fiona\config.json`（在文件管理器地址栏输入 `%APPDATA%\fiona\` 回车进入该目录，没有就建一下），内容参考 [fiona.config.example.json](fiona.config.example.json)：
   ```json
   {
     "host": "<云IP>",
     "user": "root",
     "port": 22,
     "forwards": ["3000:127.0.0.1:3000"]
   }
   ```
开发者模式还需要配 SSH 免密（见下面【SSH 免密】小节）。

### B. 本机 setup + dev（开发者模式，能改代码热调）

适合要改 Rust / 调隧道逻辑的场景。

1. `git pull` 拿到这个 `desktop/` 目录
2. 在 `desktop/` 右键 `setup.ps1` → 用 PowerShell 运行：
   - 装 Rust + tauri-cli + npm 依赖（10-15 分钟）
   - 交互问云端 IP/用户/端口，写入 `desktop/fiona.config.json`
   - 测试 SSH 免密
3. 重开 PowerShell（让 PATH 生效）
4. `.\dev.ps1` 启动Chloe窗口

## SSH 免密（仅开发者模式需要）

Tauri 内部用 `BatchMode=yes` 起 ssh，**免密没配会失败**。在 Windows PowerShell 跑一次：

```powershell
ssh-keygen -t ed25519                    # 没生成过密钥才需要，三次回车默认即可
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<你的云IP> 'cat >> ~/.ssh/authorized_keys'
```

验证：`ssh root@<云IP>` 能直接进、不问密码，就 OK。

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

开发者模式启动顺序（检测到配置文件）：
1. 读配置（dev 用 `desktop/fiona.config.json`，prod 用 `%APPDATA%\fiona\config.json`）
2. spawn `ssh -N -L <forwards> user@host` 子进程
3. 轮询 `localhost:<前端端口>` 通了再开窗（最长等 15 秒）
4. WebView2 加载 `http://localhost:3000`
5. 关窗时 kill 子进程

用户模式启动顺序（无配置文件）：
1. 不启动 SSH
2. 静态加载页直接跳转到 `https://madchloechat.online`

## 文件说明

- `package.json` — 装 `@tauri-apps/cli`
- `fiona.config.example.json` — 配置模板（实际配置 `fiona.config.json` 已 gitignore）
- `dist/index.html` — prod build 的占位首页（有配置跳 `localhost:3000`，无配置跳公网）
- `src-tauri/Cargo.toml` — Rust 依赖
- `src-tauri/tauri.conf.json` — Tauri 主配置
- `src-tauri/src/main.rs` + `lib.rs` — 入口 + SSH 隧道嵌入逻辑
- `src-tauri/capabilities/default.json` — 权限
- `src-tauri/icons/icon.png` — 从 PWA 图标复制
- `setup.ps1` / `dev.ps1` / `build.ps1` — Windows 开发者脚本

## 后续要做的事（不阻塞当前）

- 接 `tauri-plugin-store` 把 token 从 localStorage 迁到 OS keychain
- 接 `tauri-plugin-notification` 接桌面通知
- 开发者模式首次启动可考虑弹原生表单填云端配置（替代手编 `%APPDATA%\fiona\config.json`）
- 用 `cargo tauri icon path/to/1024.png` 生成全套图标
