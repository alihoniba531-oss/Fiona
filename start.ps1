# 菲欧娜一键启动脚本
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host ">>> 启动后端..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backend'; `$env:DEEPSEEK_API_KEY='REMOVED_API_KEY'; python run.py" -WindowStyle Normal

Write-Host ">>> 等待后端启动 (3秒)..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host ">>> 启动前端..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontend'; npm run dev" -WindowStyle Normal

Write-Host ">>> 等待前端编译 (5秒)..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host ">>> 打开浏览器..." -ForegroundColor Green
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "菲欧娜已启动！" -ForegroundColor Green
Write-Host "  前端: http://localhost:3000" -ForegroundColor White
Write-Host "  后端: http://localhost:8000" -ForegroundColor White
Write-Host ""
Write-Host "关闭两个 PowerShell 窗口即可停止服务。" -ForegroundColor Gray
