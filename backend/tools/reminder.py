# -*- coding: utf-8 -*-
import threading
import subprocess


def set_reminder(text: str, minutes: int) -> str:
    minutes = max(1, int(minutes))

    def notify():
        # Windows toast 通知（PowerShell）
        safe_text = text.replace("'", "''")
        try:
            subprocess.Popen([
                "powershell", "-Command",
                f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                f"[System.Windows.Forms.MessageBox]::Show('{safe_text}', '菲欧娜提醒你', "
                f"[System.Windows.Forms.MessageBoxButtons]::OK, "
                f"[System.Windows.Forms.MessageBoxIcon]::Information)"
            ])
        except Exception:
            pass

    t = threading.Timer(minutes * 60, notify)
    t.daemon = True
    t.start()

    if minutes >= 60:
        h = minutes // 60
        m = minutes % 60
        time_str = f"{h}小时" + (f"{m}分钟" if m else "")
    else:
        time_str = f"{minutes}分钟"

    return f"好，{time_str}后提醒你{text}"
