# 本机 release build — 输出 .msi 和 .exe 到 src-tauri/target/release/bundle/
#
# 如果你已经从 GitHub Actions 下载了 .msi，不需要本地 build。
# 这个脚本是给想本地 build 调试的开发者用的。
# 装好 setup.ps1 的环境后才能跑这个。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path $cargoBin) {
    $env:Path = "$cargoBin;$env:Path"
}

Write-Host "==> 开始 release build（首次 10-20 分钟）"
npm run build

$msiDir = Join-Path $PSScriptRoot "src-tauri\target\release\bundle\msi"
$nsisDir = Join-Path $PSScriptRoot "src-tauri\target\release\bundle\nsis"

Write-Host ""
Write-Host "[OK] build 完成。安装包位置："
if (Test-Path $msiDir) { Get-ChildItem $msiDir | ForEach-Object { Write-Host "  $($_.FullName)" } }
if (Test-Path $nsisDir) { Get-ChildItem $nsisDir | ForEach-Object { Write-Host "  $($_.FullName)" } }
