# -*- coding: utf-8 -*-
"""截取当前微信窗口截图，用于分析按钮位置"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
from PIL import ImageGrab
import uiautomation as auto


def find_weixin_window():
    root = auto.GetRootControl()
    for w in root.GetChildren():
        try:
            name = w.Name or ""
            cls = w.ClassName or ""
            if "微信" in name or "WeChat" in name or "Weixin" in cls:
                return w
        except Exception:
            pass
    return None


if __name__ == "__main__":
    win = find_weixin_window()
    if not win:
        print("[ERROR] WeChat not found")
        sys.exit(1)

    rect = win.BoundingRectangle
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))

    save_path = os.path.join(os.path.dirname(__file__), "weixin_screenshot.png")
    img.save(save_path)

    print(f"[OK] Saved to: {save_path}")
    print(f"Window rect: left={rect.left}, top={rect.top}, right={rect.right}, bottom={rect.bottom}")
    print(f"Window size: {rect.right - rect.left} x {rect.bottom - rect.top}")
