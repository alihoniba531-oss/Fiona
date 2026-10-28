"""第三批返修 R1 回归实测：页眉不跳动、按住 Enter 不留空行、日期面不静默写「不限」、矮屏匹配页按钮可见、日期框可按可见标签找到。

用法：uv run --with playwright==1.63.0 python probe_r1.py <输出.json> [head=URL] [cand=URL]
每项给出 HEAD 与候选的判定；HEAD 没有该界面的项记为「无」。
"""
import asyncio, json, sys
from playwright.async_api import async_playwright

BASES = dict(a.split("=", 1) for a in sys.argv[2:]) or {"head": "http://127.0.0.1:3097", "cand": "http://127.0.0.1:3098"}

async def login(page, base):
    await page.goto(base + "/login", wait_until="load")
    await page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    await page.get_by_placeholder("测试用户名（默认 tester）").fill("tester")
    await page.get_by_role("button", name="以测试身份进入").click()
    await page.wait_for_url(base + "/", timeout=60000)
    await page.wait_for_selector(".chat-composer textarea", timeout=60000)

def delayed(ms, match):
    async def handler(route, request):
        if request.method == "GET" and match(request.url):
            await asyncio.sleep(ms / 1000)
        await route.continue_()
    return handler

TOP_JS = """(sel) => { const el = [...document.querySelectorAll(sel.tag)].find(e => e.textContent.trim().startsWith(sel.text)); return el ? Math.round(el.getBoundingClientRect().top) : null; }"""

async def header_jump(b, base, vp):
    w, h, mobile = vp
    out = {}
    ctx = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile)
    page = await ctx.new_page(); await login(page, base)
    path_is_list = lambda u: u.split("?")[0].rstrip("/").endswith("/api/novels")
    await ctx.route("**/api/novels**", delayed(1500, path_is_list))
    await page.goto(base + "/novels?embed=1", wait_until="load")
    desc = {"tag": "p", "text": "留一个故事思路"}
    seq = []
    for t in (300, 900, 3500):
        await page.wait_for_timeout(t - (seq[-1][0] if seq else 0))
        seq.append((t, await page.evaluate(TOP_JS, desc)))
    refresh = page.get_by_role("button", name="刷新")
    await refresh.click(); await page.wait_for_timeout(300)
    seq.append(("refresh+300", await page.evaluate(TOP_JS, desc)))
    await page.wait_for_timeout(2500)
    seq.append(("refresh+2800", await page.evaluate(TOP_JS, desc)))
    out["novel-embed descTop"] = seq
    await ctx.unroute("**/api/novels**")
    await ctx.route("**/api/studio/access**", delayed(1500, lambda u: True))
    await page.goto(base + "/studio?embed=1", wait_until="load")
    link = {"tag": "a", "text": "在新页面打开"}
    s2 = []
    for t in (300, 900, 3500):
        await page.wait_for_timeout(t - (s2[-1][0] if s2 else 0))
        s2.append((t, await page.evaluate(TOP_JS, link)))
    out["studio-embed openLinkTop"] = s2
    await ctx.close()
    return out

async def hold_enter_after_typing(b, base):
    """打字后按住 Enter：第一次按下发送，之后连续按下带 repeat（与 measure.py 的 holdEnter 同一手法）。"""
    ctx = await b.new_context(viewport={"width": 1440, "height": 900})
    calls = []
    async def chat(route, request):
        if request.method == "POST": calls.append(1)
        await route.fulfill(status=200, content_type="text/event-stream", body='data: {"done": true}\n\n')
    await ctx.route("**/api/chat", chat)
    page = await ctx.new_page(); await login(page, base)
    await page.wait_for_timeout(1500)
    ta = page.locator(".chat-composer textarea").first
    await ta.click(); await page.keyboard.type("你好")
    await page.keyboard.down("Enter"); await page.wait_for_timeout(300)
    for _ in range(4):
        await page.keyboard.down("Enter"); await page.wait_for_timeout(200)
    await page.keyboard.up("Enter"); await page.wait_for_timeout(1500)
    val = await ta.input_value()
    await ctx.close()
    return {"chatPosts": len(calls), "valueAfter": val}

async def history_keyboard(b, base, locale):
    ctx = await b.new_context(viewport={"width": 1440, "height": 900}, locale=locale)
    page = await ctx.new_page(); await login(page, base)
    await page.goto(base + "/history", wait_until="load"); await page.wait_for_timeout(2500)
    await page.get_by_role("button", name="本月").focus()
    stops = []
    for _ in range(8):
        await page.keyboard.press("Tab"); await page.wait_for_timeout(80)
        stops.append(await page.evaluate("() => { const a = document.activeElement; return a ? (a.getAttribute('aria-label') || a.textContent.trim().slice(0, 12) || a.tagName) : null; }"))
    await page.get_by_label("开始日期").focus()
    await page.keyboard.type("20261027"); await page.wait_for_timeout(400)
    typed = await page.evaluate("""() => { const i = document.querySelector('input[aria-label*="开始日期"]'); const lab = i ? i.closest('label') : null;
      const face = lab ? [...lab.querySelectorAll('span')].map(s => s.textContent.trim()).filter(Boolean) : null;
      return { value: i ? i.value : null, opacity: i ? getComputedStyle(i).opacity : null, face }; }""")
    typed["labelFrom"] = await page.get_by_label("从").count()
    typed["labelTo"] = await page.get_by_label("到").count()
    await ctx.close()
    return {"tabStops": stops, "typed": typed}

async def match_short(b, base):
    ctx = await b.new_context(viewport={"width": 820, "height": 360})
    page = await ctx.new_page(); await login(page, base)
    await page.wait_for_timeout(1000)
    await page.evaluate("""() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const c = [...document.querySelectorAll('button[aria-controls="plaza-drawer"]'), ...[...document.querySelectorAll('button')].filter(x => x.textContent.trim() === '世界')];
      (c.find(vis) || c[0]).click(); }"""); await page.wait_for_timeout(2500)
    await page.locator("#plaza-drawer button.chip", has_text="匹配").first.click(); await page.wait_for_timeout(2500)
    fr = page.frame_locator("#plaza-drawer iframe")
    res = await fr.locator("body").evaluate("""() => { const s = document.querySelector('section[data-match-empty]'); if (!s) return { section: false };
      s.scrollTop = s.scrollHeight; const p = s.parentElement.getBoundingClientRect(); const a = [...s.querySelectorAll('a')].find(x => x.textContent.includes('查看公开名片设置'));
      const r = a ? a.getBoundingClientRect() : null; const sr = s.getBoundingClientRect();
      return { section: true, parentBottom: Math.round(p.bottom), sectionBottom: Math.round(sr.bottom), ctaBottom: r ? Math.round(r.bottom) : null,
               scrollable: s.scrollHeight > s.clientHeight, ctaFullyVisible: r ? (r.bottom <= Math.min(p.bottom, sr.bottom) + 0.5) : null }; }""")
    await ctx.close()
    return res


def judge(res):
    rows = []
    def row(name, fn, side):
        try: v = fn(res, side)
        except KeyError: v = None
        rows.append((name, side, v))
    for side in BASES:
        for vp in ("d1440", "m390"):
            row(f"{vp} 书斋抽屉说明文字位置不随加载/刷新变化", lambda r, s, vp=vp: len({t for _, t in r[f"{s} {vp} header"]["novel-embed descTop"]}) == 1, side)
            row(f"{vp} 工作室抽屉「在新页面打开」位置不随权限到达变化", lambda r, s, vp=vp: len({t for _, t in r[f"{s} {vp} header"]["studio-embed openLinkTop"]}) == 1, side)
        row("打字后按住 Enter：只发 1 次，输入框为空", lambda r, s: r[f"{s} holdEnterAfterTyping"]["chatPosts"] == 1 and r[f"{s} holdEnterAfterTyping"]["valueAfter"] == "", side)
        for loc in ("zh-CN", "en-US"):
            def face_ok(r, s, loc=loc):
                t = r[f"{s} history {loc}"]["typed"]
                if not t.get("face"): return None
                return not (t["value"] and "不限" in t["face"])
            row(f"{loc} 日期框键入后有值时，日期面不显示「不限」", face_ok, side)
            def label_ok(r, s, loc=loc):
                t = r[f"{s} history {loc}"]["typed"]
                if not t.get("face"): return None
                return t["labelFrom"] == 1 and t["labelTo"] == 1
            row(f"{loc} 可按可见标签「从」「到」找到日期框", label_ok, side)
        def match_ok(r, s):
            m = r[f"{s} match 820x360"]
            return None if not m.get("section") else bool(m["ctaFullyVisible"])
        row("820×360 匹配页滚到底后「查看公开名片设置」完整可见", match_ok, side)
    return rows

async def main(out_path):
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for side, base in BASES.items():
            for name, vp in (("d1440", (1440, 900, False)), ("m390", (390, 844, True))):
                res[f"{side} {name} header"] = await header_jump(b, base, vp)
            res[f"{side} holdEnterAfterTyping"] = await hold_enter_after_typing(b, base)
            for loc in ("zh-CN", "en-US"):
                res[f"{side} history {loc}"] = await history_keyboard(b, base, loc)
            res[f"{side} match 820x360"] = await match_short(b, base)
        await b.close()
    rows = judge(res)
    json.dump({"raw": res, "judged": rows}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for name, side, v in rows:
        print(f"{side}\t{'无' if v is None else ('过' if v else '败')}\t{name}")

asyncio.run(main(sys.argv[1]))
