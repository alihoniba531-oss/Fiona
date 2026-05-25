# 启动桌面 dev 窗口 — 加载 http://localhost:3000（SSH 转发的云端 next dev）
#
# 前置：另一个终端开着 SSH 端口转发 + 云端 next dev 在跑：
#   ssh -L 3000:127.0.0.1:3000 root@<云IP>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 让 cargo 在 PATH 里（如果用户没重启过 shell）
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path $cargoBin) {
    $env:Path = "$cargoBin;$env:Path"
}

Write-Host "==> 检查 localhost:3000 是否能连"
$test = Test-NetConnection -ComputerName "localhost" -Port 3000 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $test) {
    Write-Host ""
    Write-Host "[!] localhost:3000 连不上。可能原因："
    Write-Host "    a) SSH 端口转发没建立 → 另开终端：ssh -L 3000:127.0.0.1:3000 root@<云IP>"
    Write-Host "    b) 云端 next dev 没在跑 → 上云端 SSH 进 frontend/ 目录跑 npm run dev"
    Write-Host ""
    $ans = Read-Host "仍然要继续启动 Tauri 吗？(y/N)"
    if ($ans -ne "y") { exit 1 }
}

Write-Host ""
Write-Host "==> 启动 tauri dev（首次编译 5-10 分钟，后续秒开）"
npm run dev
