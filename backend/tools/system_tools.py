# -*- coding: utf-8 -*-
import webbrowser
import subprocess
from datetime import datetime


SITE_MAP = {
    "淘宝": "https://www.taobao.com",
    "京东": "https://www.jd.com",
    "jd": "https://www.jd.com",
    "抖音": "https://www.douyin.com",
    "微博": "https://www.weibo.com",
    "bilibili": "https://www.bilibili.com",
    "b站": "https://www.bilibili.com",
    "知乎": "https://www.zhihu.com",
    "百度": "https://www.baidu.com",
    "github": "https://github.com",
    "youtube": "https://www.youtube.com",
    "小红书": "https://www.xiaohongshu.com",
    "微信": "https://wx.qq.com",
    "qq邮箱": "https://mail.qq.com",
    "163邮箱": "https://mail.163.com",
    "google": "https://www.google.com",
}


def open_url(site: str) -> str:
    key = site.lower().strip()
    url = SITE_MAP.get(key)
    if not url:
        # 如果像域名就直接加 https，否则百度搜
        if "." in site and " " not in site:
            url = f"https://{site}" if not site.startswith("http") else site
        else:
            url = f"https://www.baidu.com/s?wd={site}"
    webbrowser.open(url)
    return f"打开了"


def take_screenshot() -> str:
    try:
        from PIL import ImageGrab
        import os
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(desktop, f"截图_{ts}.png")
        img = ImageGrab.grab()
        img.save(path)
        return f"截图保存到桌面了：截图_{ts}.png"
    except ImportError:
        # PIL 没装，用 PowerShell 截图
        try:
            import os
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(desktop, f"截图_{ts}.png")
            cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"$screen = [System.Windows.Forms.Screen]::PrimaryScreen; "
                f"$bmp = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height; "
                f"$g = [System.Drawing.Graphics]::FromImage($bmp); "
                f"$g.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size); "
                f"$bmp.Save('{path}'); $g.Dispose(); $bmp.Dispose()"
            )
            subprocess.run(["powershell", "-Command", cmd], timeout=10)
            return f"截图保存到桌面了：截图_{ts}.png"
        except Exception as e:
            return f"截图失败：{e}"
    except Exception as e:
        return f"截图失败：{e}"


def get_datetime() -> str:
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]
    return f"{now.year}年{now.month}月{now.day}日 {weekday} {now.strftime('%H:%M')}"


def write_clipboard(content: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(content)
        return "复制好了，直接粘贴就行"
    except ImportError:
        # 用 PowerShell 写剪贴板
        try:
            safe = content.replace("'", "''")
            subprocess.run(
                ["powershell", "-Command", f"Set-Clipboard -Value '{safe}'"],
                timeout=5
            )
            return "复制好了，直接粘贴就行"
        except Exception as e:
            return f"复制失败：{e}"
