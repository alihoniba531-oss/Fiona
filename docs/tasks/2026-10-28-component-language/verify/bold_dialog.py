"""补测：打开删除确认框时的粗体扫描（规格 §6-8），附正控。只按 Esc 取消，不删除。

用法（复用同目录 measure.py 的登录与扫描函数）：
  uv run --with playwright==1.63.0 python bold_dialog.py <本 verify 目录> http://127.0.0.1:3098
"""
import json, sys
sys.path.insert(0, sys.argv[1])
import measure as M
from playwright.sync_api import sync_playwright

base = sys.argv[2]
res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for theme, label, w, h, mobile in (("day", "d1440", 1440, 900, False), ("night", "m390", 390, 844, True)):
        ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
        page = ctx.new_page()
        natives = []
        page.on("dialog", lambda d: (natives.append(d.message), d.dismiss()))
        M.login(page, base)
        page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
        page.goto(base + "/", wait_until="load"); page.wait_for_selector(".chat-composer textarea"); page.wait_for_timeout(1500); M.hide_portal(page)
        M.open_sample(page, mobile)
        dels = page.locator("[data-chat-scroll-content] button", has_text="删除")
        dels.last.scroll_into_view_if_needed(); dels.last.click(); page.wait_for_timeout(400)
        r = {"dialogOpen": page.locator(".confirm-dialog[open]").count(),
             "role": page.evaluate("() => document.querySelector('.confirm-dialog[open]')?.getAttribute('role') ?? null"),
             "boldWithDialog": page.evaluate(M.BOLD_JS)}
        # 正控：给框内正文临时加 700，扫描必须抓到它
        page.evaluate("() => { document.querySelector('.confirm-dialog[open] p').style.fontWeight = '700'; }")
        pc = page.evaluate(M.BOLD_JS)
        r["positiveControlHits"] = [x for x in pc if "删除这条消息" in (x.get("text") or "")]
        page.evaluate("() => { document.querySelector('.confirm-dialog[open] p').style.fontWeight = ''; }")
        page.keyboard.press("Escape"); page.wait_for_timeout(300)
        r["openAfterEsc"] = page.locator(".confirm-dialog[open]").count()
        r["natives"] = natives
        res[f"{theme}-{label}"] = r
        ctx.close()
    b.close()
print(json.dumps(res, ensure_ascii=False, indent=1))
