# -*- coding: utf-8 -*-
"""探索微信 UI 控件树。"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import uiautomation as auto


def find_weixin_window():
    root = auto.GetRootControl()
    for w in root.GetChildren():
        try:
            name = w.Name or ""
            cls = w.ClassName or ""
            if "微信" in name or "WeChat" in name or "Weixin" in name or "Weixin" in cls:
                return w
        except Exception:
            pass
    return None


def walk_buttons(node, depth=0, max_depth=15):
    if depth > max_depth:
        return
    try:
        for child in node.GetChildren():
            try:
                ctype = child.ControlTypeName
                name = (child.Name or "").strip()
                cls = (child.ClassName or "").strip()
                aid = (child.AutomationId or "").strip()
                if ctype == "ButtonControl":
                    rect = child.BoundingRectangle
                    print(f"{'  '*depth}[BTN] name=[{name}] cls={cls} aid={aid} pos=({rect.left},{rect.top})~({rect.right},{rect.bottom})")
                walk_buttons(child, depth + 1, max_depth)
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    print("Looking for WeChat window...")
    win = find_weixin_window()
    if not win:
        print("[ERROR] WeChat window not found")
        sys.exit(1)
    print(f"[OK] Found: Name={win.Name}, ClassName={win.ClassName}")
    print(f"Window rect: {win.BoundingRectangle}")
    print("\n========== ALL BUTTONS ==========")
    walk_buttons(win)
    print("\n========== DONE ==========")
