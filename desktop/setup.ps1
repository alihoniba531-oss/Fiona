# 桌面 app 环境一键安装 — 首次跑一次即可
# 装 Rust + tauri-cli + npm 依赖 + 生成 fiona.config.json
# 预计 10-15 分钟
#
# 用法：在 desktop/ 目录下右键 → 用 PowerShell 运行

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ── 1. Rust ─────────────────────────────────────────────────────
Write-Host "==> 检查 Rust 工具链"
if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Write-Host "    Rust 未装。下载 rustup-init.exe..."
    $rustupInit = Join-Path $env:TEMP "rustup-init.exe"
    Invoke-WebRequest -Uri "https://win.rustup.rs/x86_64" -OutFile $rustupInit -UseBasicParsing
    Write-Host "    静默安装 stable toolchain（约 300MB，5-10 分钟）..."
    & $rustupInit -y --default-toolchain stable --profile minimal
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    $env:Path = "$cargoBin;$env:Path"
} else {
    Write-Host "    Rust 已装：$(rustc --version)"
}

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "[!] cargo 还是没找到。请关掉这个 PowerShell 重开一个，再跑 setup.ps1。"
    exit 1
}

# ── 2. tauri-cli ────────────────────────────────────────────────
Write-Host ""
Write-Host "==> 检查 tauri-cli"
$tauriInstalled = cargo install --list 2>$null | Select-String "tauri-cli"
if (-not $tauriInstalled) {
    Write-Host "    安装 tauri-cli v2（编译约 5-10 分钟）..."
    cargo install tauri-cli --version "^2.0"
} else {
    Write-Host "    tauri-cli 已装"
}

# ── 3. Node ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "==> 检查 Node / npm"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[!] 没找到 npm。请先装 Node.js 20+（https://nodejs.org）。"
    exit 1
}
Write-Host "    node $(node --version) / npm $(npm --version)"

Write-Host ""
Write-Host "==> 安装 npm 依赖"
npm install

# ── 4. WebView2 ─────────────────────────────────────────────────
Write-Host ""
Write-Host "==> 检查 WebView2 Runtime"
$wv2 = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
if ($wv2 -and $wv2.pv) {
    Write-Host "    WebView2 Runtime 已装：$($wv2.pv)"
} else {
    Write-Host "    [!] 没检测到 WebView2 Runtime。Win11 / Win10 1809+ 通常自带。"
    Write-Host "        若 tauri dev 报 webview 相关错，到这里装："
    Write-Host "        https://developer.microsoft.com/microsoft-edge/webview2/"
}

# ── 5. OpenSSH ──────────────────────────────────────────────────
Write-Host ""
Write-Host "==> 检查 OpenSSH 客户端"
$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if (-not $ssh) {
    Write-Host "    [!] 系统没找到 ssh.exe。请在【可选功能】里添加 OpenSSH Client："
    Write-Host "        设置 → 系统 → 可选功能 → 添加可选功能 → 搜 OpenSSH 客户端"
    exit 1
}
Write-Host "    ssh.exe OK：$($ssh.Source)"

# ── 6. 云端配置 fiona.config.json ───────────────────────────────
Write-Host ""
$cfgPath = Join-Path $PSScriptRoot "fiona.config.json"
if (Test-Path $cfgPath) {
    Write-Host "==> fiona.config.json 已存在，跳过配置（要重新生成请先删掉它）"
} else {
    Write-Host "==> 生成 fiona.config.json — 填云端连接信息"
    $host_ = Read-Host "    云端 IP 或域名（必填）"
    $user  = Read-Host "    SSH 用户名（默认 root）"
    if (-not $user) { $user = "root" }
    $port  = Read-Host "    SSH 端口（默认 22）"
    if (-not $port) { $port = "22" }
    $fePort = Read-Host "    前端端口（默认 3000）"
    if (-not $fePort) { $fePort = "3000" }

    $cfg = [ordered]@{
        host     = $host_
        user     = $user
        port     = [int]$port
        forwards = @("${fePort}:127.0.0.1:${fePort}")
    }
    $cfg | ConvertTo-Json -Depth 4 | Set-Content -Path $cfgPath -Encoding UTF8
    Write-Host "    已写入 $cfgPath"
}

# ── 7. 测试 SSH 免密 ────────────────────────────────────────────
Write-Host ""
Write-Host "==> 测试 SSH 免密登录（BatchMode）"
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$testArgs = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=5",
    "-o", "StrictHostKeyChecking=accept-new",
    "-p", "$($cfg.port)",
    "$($cfg.user)@$($cfg.host)",
    "echo OK"
)
$result = & ssh @testArgs 2>&1
if ($LASTEXITCODE -eq 0 -and $result -match "OK") {
    Write-Host "    [OK] 免密登录成功"
} else {
    Write-Host "    [!] 免密登录失败 — 桌面 app 启动时无法自动建隧道。"
    Write-Host "    解决：在 Windows PowerShell 跑下面这两行配公钥（一次性）："
    Write-Host ""
    Write-Host "      ssh-keygen -t ed25519       # 没生成过密钥才需要，全部回车默认即可"
    Write-Host "      type `$env:USERPROFILE\.ssh\id_ed25519.pub | ssh $($cfg.user)@$($cfg.host) -p $($cfg.port) 'cat >> ~/.ssh/authorized_keys'"
    Write-Host ""
    Write-Host "    配完后再 ssh $($cfg.user)@$($cfg.host) -p $($cfg.port) 应当直接进，不再问密码。"
}

Write-Host ""
Write-Host "[OK] setup 完成。运行 .\dev.ps1 启动Chloe。"
