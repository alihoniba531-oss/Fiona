# 打包 release .exe / .msi — 输出在 src-tauri/target/release/bundle/
#
# 注意：prod build 需要前端静态导出（frontend/out 目录）。
# 当前 next.config.ts 没开 output: "export"，所以这一步还跑不通 ——
# 等真正要分发安装包时再处理 export 兼容性。
# Dev 阶段用 .\dev.ps1 即可，无需 build。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path $cargoBin) {
    $env:Path = "$cargoBin;$env:Path"
}

$outDir = Join-Path $PSScriptRoot "..\frontend\out"
if (-not (Test-Path $outDir)) {
    Write-Host "[!] 找不到 frontend/out。Tauri prod build 需要前端静态导出产物。"
    Write-Host "    需要先在 frontend/next.config.ts 加 output: 'export'，"
    Write-Host "    然后 cd frontend && npm run build，产生 frontend/out。"
    Write-Host "    （app router 兼容性请先验过——dynamic routes / server actions 都不行）"
    exit 1
}

Write-Host "==> 开始 release build（10-20 分钟）"
npm run build
