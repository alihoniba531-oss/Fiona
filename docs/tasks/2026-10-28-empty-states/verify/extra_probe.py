"""第三批补测：小说功能关闭时「小说工坊尚未开放」恰好 1 个；工作室抽屉 h1 读屏仍可读到。HEAD 与候选用同一脚本。"""
import asyncio, json, sys
from playwright.async_api import async_playwright

BASES = {"head": "http://127.0.0.1:3097", "cand": "http://127.0.0.1:3098"}
VIEWPORTS = {"d1440": (1440, 900, False), "m390": (390, 844, True)}
COUNT_JS = r"""(phrases) => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.5 && el.checkVisibility(); };
  const out = {};
  for (const ph of phrases) {
    const els = [...document.querySelectorAll('body *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.includes(ph)));
    out[ph] = { all: els.length, visible: els.filter(vis).length };
  }
  return out;
}"""
PHRASES = ["小说工坊尚未开放", "正在加载身份…", "请登录后"]

async def login(page, base):
    await page.goto(base + "/login", wait_until="load")
    await page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    await page.get_by_placeholder("测试用户名（默认 tester）").fill("tester")
    await page.get_by_role("button", name="以测试身份进入").click()
    await page.wait_for_url(base + "/", timeout=60000)
    await page.wait_for_selector(".chat-composer textarea", timeout=60000)

async def main(out_path):
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for side, base in BASES.items():
            for vp, (w, h, mobile) in VIEWPORTS.items():
                ctx = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile)
                page = await ctx.new_page(); await login(page, base)
                for path in ("/novels/new", "/novels", "/novels?embed=1"):
                    await page.goto(base + path, wait_until="load"); await page.wait_for_timeout(4000)
                    res[f"{side} {vp} novel-off {path}"] = await page.evaluate(COUNT_JS, PHRASES)
                await page.goto(base + "/studio?embed=1", wait_until="load"); await page.wait_for_timeout(4000)
                heading = page.get_by_role("heading", name="短片工作室", level=1)
                box = await heading.first.bounding_box() if await heading.count() else None
                aria = await page.locator("header").first.aria_snapshot() if await page.locator("header").count() else ""
                res[f"{side} {vp} studio-embed h1"] = {"roleCount": await heading.count(), "box": box,
                                                      "inAriaSnapshot": 'heading "短片工作室" [level=1]' in aria}
                await ctx.close()
        await b.close()
    json.dump(res, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res.items():
        print(k, json.dumps(v, ensure_ascii=False))

asyncio.run(main(sys.argv[1]))
