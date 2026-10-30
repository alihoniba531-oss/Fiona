"""第四批真实浏览器实测：同一脚本量 HEAD 与候选，输出 JSON，由 compare_b4.py 比对。

用法：uv run --no-project --with playwright python measure_b4.py --base http://127.0.0.1:3097 --out <目录> [--exe <chrome-headless-shell>]
只用隔离实例的测试账号 tester；不发聊天请求。
"""
import argparse, asyncio, json, os

from playwright.async_api import async_playwright

VIEWPORTS = {"d1440": (1440, 900, False), "m390": (390, 844, True)}
STATES = [
    ("home", "/", None),
    ("agent", "/", ("agent-drawer", "分身")),
    ("exchange", "/", ("exchange-drawer", "广场")),
    ("plaza", "/", ("plaza-drawer", "世界")),
    ("settings", "/", ("settings-drawer", "设置")),
    ("settings-del", "/", ("settings-drawer", "设置")),
    ("novel", "/", ("novel-drawer", "书斋")),
    ("studio", "/", ("studio-drawer", "工作室")),
    ("history", "/history", None),
    ("match", "/match", None),
    ("profile", "/profile", None),
    ("novels-new", "/novels/new", None),
    ("studio-kb", "/studio/kb", None),
]
THEMES = {"day": ("day", "0"), "night": ("night", "0"), "day-solid": ("day", "1"), "night-solid": ("night", "1")}

COLLECT_JS = r"""() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (!(r.width > 1 && r.height > 1) || cs.visibility === 'hidden' || cs.display === 'none') return null;
    if (el.checkVisibility && !el.checkVisibility({opacityProperty: true, visibilityProperty: true})) return null;
    return [r, cs]; };
  const texts = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg') || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'IFRAME'].includes(el.tagName)) continue;
    let own = ''; for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent;
    own = own.replace(/\s+/g, ' ').trim();
    const ctl = ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) && !['checkbox', 'radio', 'range', 'hidden', 'file'].includes(el.type);
    const ctlText = ctl ? ((el.value || '').trim() || (el.getAttribute('placeholder') || '').trim()) : '';
    if (!own && !ctlText) continue;
    const v = vis(el); if (!v) continue; const [r, cs] = v;
    const fs = parseFloat(cs.fontSize); const lh = cs.lineHeight === 'normal' ? fs * 1.2 : parseFloat(cs.lineHeight);
    const ov = ['hidden', 'clip'].includes(cs.overflowX) || ['hidden', 'clip'].includes(cs.overflowY);
    let lines = 0;
    if (own) { const tops = new Set(); for (const n of el.childNodes) { if (n.nodeType !== 3 || !n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n); for (const cr of rg.getClientRects()) if (cr.width > 0.5) tops.add(Math.round(cr.top)); }
      lines = tops.size; }
    texts.push({ tag: el.tagName, text: (own || ctlText).slice(0, 40), len: (own || ctlText).length, lines, x: r.x, y: r.y, w: r.width, h: r.height,
      fs, lh, color: cs.color, ws: cs.whiteSpace, ctl,
      clipped: ov && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) });
  }
  const taps = [];
  for (const el of document.querySelectorAll('button, a[href], input:not([type=hidden]), textarea, select, [role=button], [role=tab], summary')) {
    const v = vis(el); if (!v) continue; const [r] = v;
    taps.push({ tag: el.tagName, text: ((el.innerText || '').trim() || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '').replace(/\s+/g, ' ').slice(0, 30),
      x: r.x, y: r.y, w: r.width, h: r.height });
  }
  const land = [];
  for (const sel of ['.chat-header', '.chat-composer', '[aria-label="主导航"]', '.bookmark-nav', '[id$="-drawer"]', '.drawer-panel', 'dialog[open]']) {
    document.querySelectorAll(sel).forEach((el, i) => { const v = vis(el); if (!v) return; const [r] = v; land.push({ sel, i, x: r.x, y: r.y, w: r.width, h: r.height }); });
  }
  const se = document.scrollingElement;
  return { texts, taps, land, overflowX: se ? se.scrollWidth - se.clientWidth : 0, path: location.pathname + location.search };
}"""

BACKDROP_JS = r"""() => { const out = {};
  for (const cls of ['image-preview-dialog', 'confirm-dialog']) {
    const d = document.createElement('dialog'); d.className = cls; d.textContent = 'x'; document.body.appendChild(d); d.showModal();
    out[cls] = getComputedStyle(d, '::backdrop').backgroundColor; d.close(); d.remove(); }
  return out; }"""


async def login_state(b, base, path):
    ctx = await b.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await page.goto(base + "/login", wait_until="load")
    await page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    await page.get_by_placeholder("测试用户名（默认 tester）").fill("tester")
    await page.get_by_role("button", name="以测试身份进入").click()
    await page.wait_for_url(base + "/", timeout=90000)
    await page.wait_for_selector(".chat-composer textarea", timeout=90000)
    await ctx.storage_state(path=path)
    await ctx.close()


async def hide_portal(page):
    for fr in page.frames:
        try: await fr.evaluate("() => document.querySelectorAll('nextjs-portal').forEach(e => e.style.display='none')")
        except Exception: pass


async def open_drawer(page, controls, label):
    ok = await page.evaluate("""([c, l]) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const cs = [...document.querySelectorAll(`button[aria-controls="${c}"]`), ...[...document.querySelectorAll('button')].filter(b => b.textContent.trim() === l)].filter(vis);
      if (!cs.length) return false; cs[0].click(); return true; }""", [controls, label])
    await page.wait_for_timeout(4500)
    return ok


INJECT = ""
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hot-fixtures")


async def hot_route(route):
    import hashlib
    url = route.request.url
    key = hashlib.sha256(url.split("/api", 1)[-1].encode()).hexdigest()[:16]
    path = os.path.join(FIXTURES, key + ".json")
    if os.path.exists(path):
        rec = json.load(open(path, encoding="utf-8"))
    else:
        resp = await route.fetch()
        rec = {"url": url.split("/api", 1)[-1], "status": resp.status, "ctype": resp.headers.get("content-type", "application/json"), "body": await resp.text()}
        os.makedirs(FIXTURES, exist_ok=True)
        json.dump(rec, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    await route.fulfill(status=rec["status"], content_type=rec["ctype"], body=rec["body"])


async def measure_state(b, base, state_path, vp_name, theme, st, out_dir, sem, shots):
    name, route, drawer = st
    w, h, mobile = VIEWPORTS[vp_name]
    appearance, solid = THEMES[theme]
    async with sem:
        ctx = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1, storage_state=state_path)
        await ctx.add_init_script(f"try {{ localStorage.setItem('chloe-appearance', '{appearance}'); localStorage.setItem('chloe-solid', '{solid}'); }} catch (e) {{}}")
        await ctx.route("**/api/hot/**", hot_route)
        if INJECT:
            await ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = " + json.dumps(INJECT) + "; document.head.appendChild(s); });")
        page = await ctx.new_page()
        rec = {"state": name, "vp": vp_name, "theme": theme, "ok": True}
        try:
            await page.goto(base + route, wait_until="load", timeout=90000)
            await page.wait_for_timeout(4000)
            if drawer:
                rec["drawer_opened"] = await open_drawer(page, *drawer)
                if not rec["drawer_opened"]:
                    rec["ok"] = False
            if name == "settings-del":
                for fr in page.frames:
                    try:
                        el = fr.get_by_text("永久删除账号", exact=True).first
                        if await el.count():
                            await el.scroll_into_view_if_needed(timeout=3000); break
                    except Exception:
                        pass
                await page.wait_for_timeout(600)
            await hide_portal(page); await page.wait_for_timeout(400)
            frames = []
            for fr in page.frames:
                off = (0.0, 0.0)
                if fr != page.main_frame:
                    try:
                        fe = await fr.frame_element()
                        visible = await fe.evaluate("el => !!el.checkVisibility && el.checkVisibility({opacityProperty: true, visibilityProperty: true}) && el.getBoundingClientRect().width > 1")
                        bb = await fe.bounding_box()
                        if not visible or not bb: continue
                        off = (bb["x"], bb["y"])
                    except Exception:
                        continue
                try:
                    data = await fr.evaluate(COLLECT_JS)
                except Exception as e:
                    continue
                for k in ("texts", "taps", "land"):
                    for it in data[k]:
                        it["x"] += off[0]; it["y"] += off[1]
                data["main"] = fr == page.main_frame
                frames.append(data)
            rec["frames"] = frames
            rec["backdrop"] = await page.evaluate(BACKDROP_JS)
            if shots:
                await page.screenshot(path=os.path.join(out_dir, f"{name}-{vp_name}-{theme}.png"))
        except Exception as e:
            rec["ok"] = False; rec["error"] = repr(e)[:300]
        await ctx.close()
        print("done", name, vp_name, theme, "ok" if rec["ok"] else rec.get("error", "drawer"), flush=True)
        return rec


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--exe")
    ap.add_argument("--themes", default="day,night,day-solid,night-solid"); ap.add_argument("--shots", action="store_true")
    ap.add_argument("--states", default="")
    ap.add_argument("--inject-css", default="", help="仅用于验证本工具：往每个框架注入一段 CSS，人为制造回归")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=a.exe) if a.exe else await p.chromium.launch()
        state_path = os.path.join(a.out, "_state.json")
        await login_state(b, a.base, state_path)
        sem = asyncio.Semaphore(4)
        global INJECT
        INJECT = a.inject_css
        jobs = [measure_state(b, a.base, state_path, vp, th, st, a.out, sem, a.shots)
                for th in a.themes.split(",") for vp in VIEWPORTS for st in STATES if not a.states or st[0] in a.states.split(",")]
        recs = await asyncio.gather(*jobs)
        await b.close()
    out = os.path.join(a.out, "measure.json")
    if a.states and os.path.exists(out):  # 只补测部分状态时并入已有结果
        old = [r for r in json.load(open(out, encoding="utf-8")) if r["state"] not in a.states.split(",")]
        recs = old + list(recs)
    json.dump(recs, open(out, "w"), ensure_ascii=False)
    print("states", len(recs), "failed", sum(1 for r in recs if not r["ok"]))


asyncio.run(main())
