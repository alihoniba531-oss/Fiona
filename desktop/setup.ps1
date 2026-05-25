# 桌面 app 环境一键安装 — 首次跑一次即可
# 装 Rust toolchain + tauri-cli + npm 依赖，预计 10-15 分钟
#
# 用法：在 desktop/ 目录下右键 → 用 PowerShell 运行

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> 检查 Rust 工具链"
if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Write-Host "    Rust 未装。下载 rustup-init.exe..."
    $rustupInit = Join-Path $env:TEMP "rustup-init.exe"
    Invoke-WebRequest -Uri "https://win.rustup.rs/x86_64" -OutFile $rustupInit -UseBasicParsing
    Write-Host "    静默安装 stable toolchain（约 300MB，5-10 分钟）..."
    & $rustupInit -y --default-toolchain stable --profile minimal
    # 让当前会话能用 cargo
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

Write-Host ""
Write-Host "==> 检查 tauri-cli"
$tauriInstalled = cargo install --list 2>$null | Select-String "tauri-cli"
if (-not $tauriInstalled) {
    Write-Host "    安装 tauri-cli v2（编译约 5-10 分钟）..."
    cargo install tauri-cli --version "^2.0"
} else {
    Write-Host "    tauri-cli 已装"
}

Write-Host ""
Write-Host "==> 检查 Node / npm"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[!] 没找到 npm。请先装 Node.js 20+（https://nodejs.org）。"
    exit 1
}
Write-Host "    node $(node --version) / npm $(npm --version)"

Write-Host ""
Write-Host "==> 安装 desktop/ 下的 npm 依赖"
npm install

Write-Host ""
Write-Host "==> 检查 WebView2 Runtime（Tauri 在 Windows 上加载 web 内容必备）"
$wv2 = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
if ($wv2 -and $wv2.pv) {
    Write-Host "    WebView2 Runtime 已装：$($wv2.pv)"
} else {
    Write-Host "    [!] 没检测到 WebView2 Runtime。Win11 / Win10 1809+ 通常自带；"
    Write-Host "        若 tauri dev 报 webview 相关错，去这里装："
    Write-Host "        https://developer.microsoft.com/microsoft-edge/webview2/"
}

Write-Host ""
Write-Host "[OK] 环境就绪。"
Write-Host ""
Write-Host "下一步："
Write-Host "  1. 先开一个 SSH 终端转发云端端口："
Write-Host "       ssh -L 3000:127.0.0.1:3000 root@<云IP>"
Write-Host "     再在云端确认 next dev + python run.py 都在跑。"
Write-Host "  2. 在 Windows 这边浏览器打开 http://localhost:3000 验证能进网页。"
Write-Host "  3. 回到 desktop/ 目录，运行 .\dev.ps1 启动桌面窗口。"
