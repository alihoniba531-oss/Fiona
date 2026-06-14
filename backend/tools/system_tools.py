# -*- coding: utf-8 -*-
from datetime import datetime


def open_url(site: str) -> str:
    # 后端只跑在无头服务器上，没有桌面浏览器可以替你外部打开网页
    return "用浏览器帮你打开网页这个，我在网页版里还做不到呢～你想看的话告诉我，我可以直接帮你搜来看看？"


def take_screenshot() -> str:
    # 服务器上没有屏幕可截，老老实实说做不到
    return "截图这个我现在还做不到哎，我这边是没有屏幕的那种～有别的我能帮上的吗？"


def get_datetime() -> str:
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]
    return f"{now.year}年{now.month}月{now.day}日 {weekday} {now.strftime('%H:%M')}"


def write_clipboard(content: str) -> str:
    # 服务器上没有剪贴板，复制粘贴这种本机操作做不了
    return "帮你复制到剪贴板这个我还做不到呢，我这边没办法碰你电脑的剪贴板～不过你直接选中我发的内容复制也很方便呀。"
