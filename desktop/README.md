# Chloe Windows 桌面客户端

Tauri 2 桌面壳 + 可选 SSH 隧道。双击安装后的应用即可加载 Web 客户端：开发者模式连接云端开发服务，用户模式直接打开公网 `https://madchloechat.online`。

桌面包不内置完整的 Next.js 应用；`dist/index.html`、`dist/main.js` 和 `dist/style.css` 一起组成启动/跳转页，三个文件都必须入库。整个产品的架构和发布阻断项分别见 [架构文档](../docs/ARCHITECTURE.md) 和 [PLAN.md](../PLAN.md)。

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

1. 在仓库根目录执行 `git pull --ff-only`
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

这里的“开发者模式”和后端 `DEV_MODE` 不是同一个开关：前者由桌面配置文件是否存在决定，后者由 `backend/.env` 决定鉴权和测试入口。

## 构建与 CI

本地 release 构建：

```powershell
.\build.ps1
```

输出目录：

- `src-tauri\target\release\bundle\msi\`
- `src-tauri\target\release\bundle\nsis\`

GitHub Actions 的 `Build Windows Desktop` 工作流只在 `desktop/**` 或工作流文件变化时自动触发，也可以手动运行。它使用 Node 20、Rust stable 和 `npm ci`，先执行 Rust 单元测试再运行 `npm run build`，最后上传 MSI 与 NSIS artifact。

启动页的 `dist/index.html`、`dist/main.js` 和 `dist/style.css` 是手写静态文件，必须随代码入库，不能依赖本机文件生成。质量检查从仓库根目录运行 `node desktop/scripts/check-dist-assets.mjs`；Windows 工作流在 `desktop/` 下运行 `node scripts/check-dist-assets.mjs`。两者都会检查启动页引用的本地文件是否存在、是否被 Git 忽略，以及页面是否包含会被 CSP 拦截的内联脚本或样式。

当前目录已提交独立 `package-lock.json`；Rust 侧仍没有提交 `Cargo.lock`，因此构建还不是完全可复现的。公开发布前应补齐 Cargo 锁文件和安装包签名流程。

## 安全边界

用户模式加载的是远程网页，而 Tauri command 在本机执行。前端 JavaScript 的参数检查不能替代 Rust 命令边界的校验。

当前代码已经完成：

- 远程页面只保留 `open_url`/`open_url_in_app`，诊断、后端探测和日志目录命令只对本地隧道页面开放。
- Rust 层只接受长度受限、无凭据且带主机名的绝对 HTTP(S) URL。
- Windows 外链直接交给系统 URL 处理器，不再让 `cmd.exe` 解释输入。
- Tauri 启动页和远程 Next.js 页面均配置了 CSP；启动页脚本与样式已外置，不再依赖内联脚本、样式或事件处理器。

工作流已配置 Windows Cargo 编译与 Rust 单元测试，但本轮改动仍需推送后确认实际 CI 结果，并验证两种加载模式的 capability/CSP；安装包签名、`Cargo.lock` 和正式升级/回滚流程也尚未完成。因此桌面包目前仍只应在受控环境中测试。

## 文件说明

- `package.json` — 装 `@tauri-apps/cli`
- `fiona.config.example.json` — 配置模板（实际配置 `fiona.config.json` 已 gitignore）
- `dist/index.html` + `dist/main.js` + `dist/style.css` — prod build 的启动页（有配置跳 `localhost:3000`，无配置跳公网）
- `src-tauri/Cargo.toml` — Rust 依赖
- `src-tauri/tauri.conf.json` — Tauri 主配置
- `src-tauri/src/main.rs` + `lib.rs` — 入口 + SSH 隧道嵌入逻辑
- `src-tauri/capabilities/default.json` — 本地隧道页面权限
- `src-tauri/capabilities/remote-links.json` — 远程页面最小外链权限
- `src-tauri/icons/icon.png` — 从 PWA 图标复制
- `setup.ps1` / `dev.ps1` / `build.ps1` — Windows 开发者脚本

## 后续要做的事（不阻塞当前）

- 接 `tauri-plugin-store` 把 token 从 localStorage 迁到 OS keychain
- 接 `tauri-plugin-notification` 接桌面通知
- 开发者模式首次启动可考虑弹原生表单填云端配置（替代手编 `%APPDATA%\fiona\config.json`）
- 用 `cargo tauri icon path/to/1024.png` 生成全套图标
- 增加安装包签名、版本发布和自动/受控更新流程
