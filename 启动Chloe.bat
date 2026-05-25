@echo off
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im node.exe >nul 2>&1
timeout /t 2 /nobreak >nul

powershell -WindowStyle Hidden -Command "Start-Process -FilePath 'd:\Program Files\数据抓取软件\.venv\Scripts\pythonw.exe' -ArgumentList 'run.py' -WorkingDirectory 'D:\Program Files\新建文件夹\backend' -WindowStyle Hidden -RedirectStandardError 'D:\Program Files\新建文件夹\backend\err.log'"

timeout /t 5 /nobreak >nul

powershell -WindowStyle Hidden -Command "Start-Process -FilePath 'cmd' -ArgumentList '/c npm run dev' -WorkingDirectory 'D:\Program Files\新建文件夹\frontend' -WindowStyle Minimized"

timeout /t 14 /nobreak >nul
start http://localhost:3000
