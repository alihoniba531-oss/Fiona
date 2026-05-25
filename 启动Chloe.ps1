Get-Process -Name 'python','pythonw','node' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process -FilePath 'd:\Program Files\数据抓取软件\.venv\Scripts\pythonw.exe' -ArgumentList 'run.py' -WorkingDirectory 'D:\Program Files\新建文件夹\backend' -WindowStyle Hidden -RedirectStandardOutput 'D:\Program Files\新建文件夹\backend\backend.log' -RedirectStandardError 'D:\Program Files\新建文件夹\backend\backend_err.log'
Start-Sleep -Seconds 5
Start-Process -FilePath 'cmd' -ArgumentList '/c npm run dev' -WorkingDirectory 'D:\Program Files\新建文件夹\frontend' -WindowStyle Hidden
Start-Sleep -Seconds 14
Start-Process 'http://localhost:3000'
