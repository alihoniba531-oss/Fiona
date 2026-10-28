"""P3-20 复现（已登录）：R1 脚本晚到 3 秒；R2 本地存储无用户名 + /api/profile 慢 4 秒；R3 本地存储无用户名 + /api/profile 返回 500。"""
import asyncio, json, sys
from playwright.async_api import async_playwright

base, out = sys.argv[1], sys.argv[2]
KEYS = ["请登录后新建小说", "请登录后查看你的书架", "前往登录", "正在加载", "思路与篇幅", "开始你的第一本书"]

async def login(page):
    await page.goto(base + "/login", wait_until="load")
    await page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    await page.get_by_placeholder("测试用户名（默认 tester）").fill("tester")
    await page.get_by_role("button", name="以测试身份进入").click()
    await page.wait_for_url(base + "/", timeout=60000)
    await page.wait_for_selector(".chat-composer textarea", timeout=60000)

async def sample(page, marks):
    tl, waited = [], 0
    for t in marks:
        await page.wait_for_timeout(t - waited); waited = t
        try:
            txt = await page.locator("body").inner_text()
        except Exception as exc:
            txt = f"<err {type(exc).__name__}>"
        tl.append({"ms": t, **{k: (k in txt) for k in KEYS}})
    return tl

async def scenario(b, name, path, setup):
    ctx = await b.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await login(page)
    profile_hits = []
    await setup(page, profile_hits)
    await page.goto(base + path, wait_until="commit")
    tl = await sample(page, (1000, 2500, 5000, 8000))
    await ctx.close()
    return {"scenario": name, "path": path, "profileRequests": len(profile_hits), "timeline": tl}

async def main():
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        # 正控：同一账号，正常网络
        async def none(page, hits): pass
        async def slow_js(page, hits):
            async def h(route):
                await asyncio.sleep(3); await route.continue_()
            await page.route("**/_next/static/chunks/**", h)
        async def no_user_slow_profile(page, hits):
            await page.evaluate("() => localStorage.removeItem('fiona_user')")
            async def h(route):
                hits.append(1); await asyncio.sleep(4); await route.continue_()
            await page.route(lambda u: u.split('?')[0].endswith('/api/profile'), h)
        async def no_user_profile_500(page, hits):
            await page.evaluate("() => localStorage.removeItem('fiona_user')")
            async def h(route):
                hits.append(1); await route.fulfill(status=500, body="{}", content_type="application/json")
            await page.route(lambda u: u.split('?')[0].endswith('/api/profile'), h)
        runs = []
        for path in ("/novels/new", "/novels"):
            runs.append(await scenario(b, "R0 正常", path, none))
            runs.append(await scenario(b, "R1 脚本晚到 3s", path, slow_js))
            runs.append(await scenario(b, "R2 无本地用户名 + profile 慢 4s", path, no_user_slow_profile))
            runs.append(await scenario(b, "R3 无本地用户名 + profile 500", path, no_user_profile_500))
        # 服务端渲染的原始 HTML（带有效 Cookie）
        ctx = await b.new_context(); page = await ctx.new_page(); await login(page)
        for path in ("/novels/new", "/novels"):
            html = await (await page.request.get(base + path)).text()
            res[f"ssrHtml {path}"] = {k: (k in html) for k in KEYS}
        await ctx.close(); await b.close()
        res["runs"] = runs
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res.items():
        if k != "runs": print(k, v)
    for r in res["runs"]:
        print(f"== {r['path']} | {r['scenario']} | profile requests={r['profileRequests']}")
        for s in r["timeline"]:
            on = [k for k in KEYS if s[k]]
            print(f"   {s['ms']:>5} ms: {on}")

asyncio.run(main())
