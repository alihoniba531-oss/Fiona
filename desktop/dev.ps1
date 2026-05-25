# 启动菲欧娜桌面 dev — 双击即用
#
# Tauri 进程会读 fiona.config.json，自动建 SSH 隧道、等端口通、加载 webview。
# 关窗时自动 kill 隧道。
#
# 前置（一次性）：跑过 .\setup.ps1 + SSH 免密配过 + 云端 next dev 在跑。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 让 cargo 在 PATH（用户没重开 shell 也能用）
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path $cargoBin) {
    $env:Path = "$cargoBin;$env:Path"
}

if (-not (Test-Path "fiona.config.json")) {
    Write-Host "[!] fiona.config.json 不存在。先跑 .\setup.ps1 生成。"
    exit 1
}

Write-Host "==> 启动 tauri dev（首次编译 5-10 分钟，后续秒开）"
npm run dev
