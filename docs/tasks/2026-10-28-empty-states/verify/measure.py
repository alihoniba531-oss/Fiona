"""空态与文案（第三批）真实浏览器实测：HEAD 与候选用同一脚本量，HEAD 是正控。

用法（在装有 Playwright 1.63.0 浏览器的目录里）：
  uv run --with playwright==1.63.0 python measure.py --base http://127.0.0.1:3098 --out <目录> [--parts identity,shelves,...]
只用隔离实例的测试账号 tester；/api/chat 与 /api/asr/recognize 一律在浏览器里拦截，不会打到真实厂商。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re

from playwright.async_api import async_playwright

VIEWPORTS = {"d1440": (1440, 900, False), "m390": (390, 844, True)}
THEMES = ("day", "night")

VIS_JS = """(el) => { if (!el) return false; const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.5; }"""

BOLD_IN_JS = r"""(root) => {
  const hits = [];
  if (!root) return null;
  for (const el of [root, ...root.querySelectorAll('*')]) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const w = parseInt(cs.fontWeight, 10);
    if (w >= 600) hits.push({ tag: el.tagName, w, text: el.textContent.trim().slice(0, 30) });
  }
  return hits;
}"""


async def login(page, base, user="tester"):
    await page.goto(base + "/login", wait_until="load")
    await page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    await page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    await page.get_by_role("button", name="以测试身份进入").click()
    await page.wait_for_url(base + "/", timeout=60000)
    await page.wait_for_selector(".chat-composer textarea", timeout=60000)


async def hide_portal(page):
    """隐藏 Next 开发角标，包括抽屉 iframe 里的（它会压住内容）。"""
    for frame in page.frames:
        try:
            await frame.evaluate("() => document.querySelectorAll('nextjs-portal').forEach(e => e.style.display = 'none')")
        except Exception:  # noqa: BLE001
            pass


async def guard_network(ctx):
    async def chat(route):
        await route.fulfill(status=200, content_type="text/event-stream", body='data: {"done": true}\n\n')
    async def asr(route):
        await route.fulfill(status=200, content_type="application/json", body='{"text": ""}')
    await ctx.route("**/api/chat", chat)
    await ctx.route("**/api/asr/recognize", asr)


async def open_home(b, base, vp, theme, **extra):
    w, h, mobile = VIEWPORTS[vp]
    ctx = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1, **extra)
    await guard_network(ctx)
    page = await ctx.new_page()
    await login(page, base)
    await page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
    await page.goto(base + "/", wait_until="load")
    await page.wait_for_selector(".chat-composer textarea")
    await page.wait_for_timeout(1500)
    await hide_portal(page)
    return ctx, page


async def open_drawer(page, controls, label):
    """点侧栏书签（桌面）或底栏（手机）；被隐藏时直接 click DOM。"""
    clicked = await page.evaluate("""([controls, label]) => {
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
      const cands = [...document.querySelectorAll(`button[aria-controls="${controls}"]`), ...[...document.querySelectorAll('button')].filter(b => b.textContent.trim() === label)];
      const target = cands.find(vis) || cands[0];
      if (!target) return false; target.click(); return true; }""", [controls, label])
    await page.wait_for_timeout(2500)
    await hide_portal(page)
    return clicked


# ---------- P3-20 身份 ----------
async def part_identity(b, base, out):
    res = {}
    ctx = await b.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await login(page, base)
    state = await ctx.storage_state()
    await ctx.close()
    # 服务端渲染的原始 HTML（带有效 Cookie）
    ctx = await b.new_context(storage_state=state)
    page = await ctx.new_page()
    for path in ("/novels/new", "/novels", "/studio"):
        html = await (await page.request.get(base + path)).text()
        res[f"ssr html {path}"] = {"pending": "正在加载身份…" in html, "login": "请登录后" in html}
    await ctx.close()

    # 前端脚本晚到 3 秒（慢网或慢手机）：按时间点取可见文字
    async def late_js(route):
        await asyncio.sleep(3)
        await route.continue_()
    for path in ("/novels/new", "/novels", "/studio"):
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, storage_state=state)
        await ctx.route("**/_next/static/chunks/**", late_js)
        page = await ctx.new_page()
        await page.goto(base + path, wait_until="commit")
        tl, waited = [], 0
        for t in (1000, 2500, 6000):
            await page.wait_for_timeout(t - waited); waited = t
            try:
                txt = await page.locator("body").inner_text()
            except Exception as exc:  # noqa: BLE001
                txt = f"<{type(exc).__name__}>"
            tl.append({"ms": t, "pending": "正在加载身份…" in txt, "login": "请登录后" in txt})
        res[f"late js {path}"] = tl
        await ctx.close()

    async def slow(route):
        await asyncio.sleep(4)
        await route.continue_()

    async def fail(route):
        await route.fulfill(status=500, content_type="application/json", body="{}")

    for name, handler in (("profile slow 4s", slow), ("profile 500", fail)):
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, storage_state=state)
        # 只在第一个文档开始时删掉本地用户名，之后由身份找回写回
        await ctx.add_init_script("if (!sessionStorage.getItem('b3-cleared')) { localStorage.removeItem('fiona_user'); sessionStorage.setItem('b3-cleared', '1'); }")
        hits = []

        def make_counted(inner):
            async def counted(route):
                hits.append(1)
                await inner(route)
            return counted
        await ctx.route(lambda u: u.split("?")[0].endswith("/api/profile"), make_counted(handler))
        page = await ctx.new_page()
        await page.goto(base + "/novels/new", wait_until="commit")
        tl, waited = [], 0
        for t in (1000, 2500, 8000):
            await page.wait_for_timeout(t - waited); waited = t
            try:
                txt = await page.locator("body").inner_text()
            except Exception as exc:  # noqa: BLE001
                txt = f"<{type(exc).__name__}>"
            tl.append({"ms": t, "pending": "正在加载身份…" in txt, "login": "请登录后新建小说" in txt, "wizard": "故事思路" in txt})
        res[name] = {"profileRequests": len(hits), "timeline": tl}
        await ctx.close()
    out["identity"] = res


# ---------- P2-8 书架 ----------
SHELF_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const h1 = [...document.querySelectorAll('h1')].find(e => e.textContent.trim() === '短片工作室' || e.textContent.trim() === '书斋');
  const r = h1 ? h1.getBoundingClientRect() : null;
  const btn = [...document.querySelectorAll('button')].find(e => e.textContent.includes('新建项目'));
  const news = [...document.querySelectorAll('a,button')].filter(e => e.textContent.includes('新建一本') && vis(e));
  return {
    h1: h1 ? { text: h1.textContent.trim(), w: Math.round(r.width), h: Math.round(r.height) } : null,
    newProject: btn ? { visible: vis(btn), rightGap: Math.round(btn.parentElement.getBoundingClientRect().right - btn.getBoundingClientRect().right), tag: btn.tagName } : null,
    newBookVisible: news.length, newBookInHeader: news.filter(e => e.closest('header')).length,
    pendingText: document.body.innerText.includes('正在加载身份…'), loginText: document.body.innerText.includes('请登录后'),
  };
}"""


async def part_shelves(b, base, out):
    res = {}
    for vp in VIEWPORTS:
        ctx, page = await open_home(b, base, vp, "day")
        await open_drawer(page, "studio-drawer", "工作室")
        res[f"{vp} studio drawer"] = await page.frame_locator("#studio-drawer iframe").locator("body").evaluate(f"(b) => ({SHELF_JS})()")
        await page.keyboard.press("Escape"); await page.wait_for_timeout(600)
        await open_drawer(page, "novel-drawer", "书斋")
        res[f"{vp} novel drawer"] = await page.frame_locator("#novel-drawer iframe").locator("body").evaluate(f"(b) => ({SHELF_JS})()")
        for path in ("/studio", "/novels"):
            await page.goto(base + path, wait_until="load"); await page.wait_for_timeout(2500); await hide_portal(page)
            res[f"{vp} standalone {path}"] = await page.evaluate(SHELF_JS)
        await ctx.close()
    out["shelves"] = res


# ---------- P2-10 新对话开场 ----------
OPENERS_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const group = document.querySelector('[data-chat-scroll-content] [role=group]');
  const btns = group ? [...group.querySelectorAll('button')] : [];
  const g = group ? group.getBoundingClientRect() : null;
  const header = document.querySelector('.chat-header'); const composer = document.querySelector('.chat-composer');
  return {
    group: !!group, labels: btns.map(b => b.textContent.trim()), enabled: btns.filter(b => !b.disabled && vis(b)).length,
    minHeight: btns.length ? Math.min(...btns.map(b => Math.round(b.getBoundingClientRect().height))) : null,
    inStatus: btns.some(b => !!b.closest('[role=status]')),
    belowHeader: g && header ? g.top >= header.getBoundingClientRect().bottom - 1 : null,
    aboveComposer: g && composer ? g.bottom <= composer.getBoundingClientRect().top + 1 : null,
    inViewport: g ? g.top >= 0 && g.bottom <= innerHeight : null,
    hasDot: group ? group.textContent.includes('·') : null,
    noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  };
}"""


async def part_openers(b, base, out):
    res = {}
    for vp in VIEWPORTS:
        for theme in THEMES:
            ctx, page = await open_home(b, base, vp, theme)
            nonget = []
            page.on("request", lambda r: nonget.append(f"{r.method} {r.url}") if r.method != "GET" and "/api/" in r.url else None)
            run = {"layout": await page.evaluate(OPENERS_JS)}
            run["bold"] = await page.evaluate(f"() => ({BOLD_IN_JS})(document.querySelector('[data-chat-openers]'))")
            if theme == "day":
                # 计数器正控：打字回车（/api/chat 已拦截），必须数到 1
                await page.fill(".chat-composer textarea", "计数器正控"); await page.keyboard.press("Enter")
                await page.wait_for_timeout(1500)
                run["counterControl"] = len([x for x in nonget if "/api/chat" in x])
                for label in ("聊聊今天", "帮我画一张…", "看看我拍的这张图"):
                    await page.goto(base + "/", wait_until="load"); await page.wait_for_selector(".chat-composer textarea"); await page.wait_for_timeout(1500); await hide_portal(page)
                    btn = page.locator("[data-chat-scroll-content] [role=group] button", has_text=label)
                    if not await btn.count():
                        run[label] = None; continue
                    before = len(nonget); chooser = False
                    if label == "看看我拍的这张图":
                        try:
                            async with page.expect_file_chooser(timeout=3000):
                                await btn.first.click()
                            chooser = True
                        except Exception:  # noqa: BLE001
                            chooser = False
                    else:
                        await btn.first.click()
                    await page.wait_for_timeout(3000)
                    eff = await page.evaluate("""() => { const ta = document.querySelector('.chat-composer textarea');
                      const chip = [...document.querySelectorAll('.chat-composer span.chip-on')].find(e => e.textContent.trim() === '生成图片');
                      return { value: ta ? ta.value : null, focused: document.activeElement === ta, placeholder: ta ? ta.placeholder : null, imageMode: !!chip,
                               bubbles: document.querySelectorAll('[data-chat-scroll-content] .bubble-user, [data-chat-scroll-content] .bubble-ai').length }; }""")
                    run[label] = {"nonGetDuring": len(nonget) - before, "fileChooser": chooser, **eff}
                # 在「聊聊今天」上按住 Enter：第一次按下激活按钮，之后连续按下带 repeat=true，落到输入框上
                await page.goto(base + "/", wait_until="load"); await page.wait_for_selector(".chat-composer textarea"); await page.wait_for_timeout(1500); await hide_portal(page)
                chip = page.locator("[data-chat-scroll-content] [role=group] button", has_text="聊聊今天")
                if await chip.count():
                    before = len(nonget)
                    await chip.first.focus(); await page.keyboard.down("Enter"); await page.wait_for_timeout(300)
                    for _ in range(4):
                        await page.keyboard.down("Enter"); await page.wait_for_timeout(200)
                    await page.keyboard.up("Enter"); await page.wait_for_timeout(1500)
                    run["holdEnter"] = {"nonGetDuring": len(nonget) - before,
                                        "value": await page.evaluate("() => (document.querySelector('.chat-composer textarea') || {}).value ?? null")}
            res[f"{theme}-{vp}"] = run
            await ctx.close()
    out["openers"] = res


# ---------- P2-10 匹配页与画像页 ----------
MATCH_JS = r"""() => {
  const aside = document.querySelector('aside'); const right = aside ? aside.nextElementSibling : null;
  const txt = right ? right.innerText.trim() : '';
  const link = right ? [...right.querySelectorAll('a')].find(a => a.textContent.includes('查看公开名片设置')) : null;
  const left = aside ? [...aside.querySelectorAll('p')].find(p => p.textContent.includes('会出现在这里')) : null;
  const ink2 = getComputedStyle(document.documentElement).getPropertyValue('--ink2').trim();
  return { rightText: txt.length, h2: right ? [...right.querySelectorAll('h2')].map(h => h.textContent.trim()) : [],
           link: link ? { href: link.getAttribute('href'), target: link.getAttribute('target') } : null,
           forbidden: /匿名|不知道你是谁|Skill|自动交流|左侧/.test(txt), mentionsAccept: txt.includes('认识下') && txt.includes('发送打招呼'),
           noHumanChat: txt.includes('不会建立真人聊天'),
           leftSize: left ? parseFloat(getComputedStyle(left).fontSize) : null, leftColor: left ? getComputedStyle(left).color : null, ink2,
           noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth };
}"""


async def part_match(b, base, out):
    res = {}
    for vp in VIEWPORTS:
        for theme in THEMES:
            ctx, page = await open_home(b, base, vp, theme)
            await open_drawer(page, "plaza-drawer", "世界")
            await page.locator("#plaza-drawer button.chip", has_text="匹配").first.click(); await page.wait_for_timeout(2500)
            run = {"match": await page.frame_locator("#plaza-drawer iframe").locator("body").evaluate(f"(b) => ({MATCH_JS})()")}
            await page.keyboard.press("Escape"); await page.wait_for_timeout(600)
            await open_drawer(page, "settings-drawer", "设置")
            await page.locator("#settings-drawer button.chip", has_text="账户").first.click(); await page.wait_for_timeout(2500)
            body = await page.frame_locator("#settings-drawer iframe").locator("body").inner_text()
            run["profile"] = {"old": body.count("旧社交画像"), "new": body.count("社交画像（旧版）")}
            res[f"{theme}-{vp}"] = run
            await ctx.close()
    ctx, page = await open_home(b, base, "d1440", "day")
    await page.goto(base + "/profile", wait_until="load"); await page.wait_for_timeout(2000)
    res["standalone profile h1"] = await page.evaluate("() => (document.querySelector('h1') || {}).textContent || null")
    await ctx.close()
    out["match"] = res


# ---------- P2-11 设置页隐私 ----------
PREFIXES = ["启用后，聊天回复会把", "危机复核、平台工具执行", "生图：", "选 Claude 时", "自带模型文字聊天", "Key 加密保存", "开启『聊天读小说』", "Claude 的接口不对中国大陆"]
PRIVACY_JS = r"""(prefixes) => {
  const sec = [...document.querySelectorAll('section')].find(s => (s.querySelector('h2') || {}).textContent?.trim() === '聊天模型');
  if (!sec) return { section: false };
  const ps = prefixes.map(pre => [...sec.querySelectorAll('p')].find(p => p.textContent.trim().startsWith(pre)) || null);
  const save = [...sec.querySelectorAll('button')].find(b => /保存/.test(b.textContent) && !/思考/.test(b.textContent));
  const details = sec.querySelector('details'); const summary = details ? details.querySelector('summary') : null;
  // Chromium 收起的 <details> 用 content-visibility:hidden，里面的段落仍有布局盒，只看盒子尺寸恒为真；
  // 是否真的显示给用户以 checkVisibility() 为准（不支持时抛错，不静默回落）。
  const boxed = p => !!p && p.getClientRects().length > 0 && p.getBoundingClientRect().height > 0;
  const rendered = p => boxed(p) && p.checkVisibility();
  return { section: true, found: ps.filter(Boolean).length, rendered: ps.map(rendered), boxed: ps.map(boxed), texts: ps.map(p => p ? p.textContent.trim() : null),
           details: details ? { open: details.open, summaryText: summary ? summary.textContent.trim() : null, summaryH: summary ? Math.round(summary.getBoundingClientRect().height) : null,
                                inFieldset: !!details.closest('fieldset'), opacity: getComputedStyle(details).opacity } : null,
           firstAboveSave: ps[0] && save ? ps[0].getBoundingClientRect().top < save.getBoundingClientRect().top : null,
           firstAboveToggle: (() => { const t = [...sec.querySelectorAll('span')].find(x => x.textContent.trim() === '启用我的聊天模型'); return ps[0] && t ? ps[0].getBoundingClientRect().top < t.getBoundingClientRect().top : null; })(),
           firstOutsideDetails: ps[0] ? !ps[0].closest('details') : null };
}"""


async def part_privacy(b, base, out):
    res = {}
    for vp in VIEWPORTS:
        for theme in THEMES:
            ctx, page = await open_home(b, base, vp, theme)
            await open_drawer(page, "settings-drawer", "设置")
            frame = page.frame_locator("#settings-drawer iframe")
            run = {"closed": await frame.locator("body").evaluate(f"(b) => ({PRIVACY_JS})({json.dumps(PREFIXES, ensure_ascii=False)})")}
            if vp == "d1440":
                run["nextSectionOnScreen"] = await frame.locator("body").evaluate("""() => {
                  const hs = [...document.querySelectorAll('h2')]; const a = hs.find(h => h.textContent.trim() === '聊天模型'); const n = hs.find(h => h.textContent.trim() === '本机监控');
                  if (!a || !n) return null; a.scrollIntoView({ block: 'start' }); return { nextTop: Math.round(n.getBoundingClientRect().top), innerHeight }; }""")
            summary = frame.locator("section details summary").first
            if await summary.count():
                await summary.focus(); await page.keyboard.press("Enter"); await page.wait_for_timeout(400)
                run["opened"] = await frame.locator("body").evaluate(f"(b) => ({PRIVACY_JS})({json.dumps(PREFIXES, ensure_ascii=False)})")
            run["bold"] = await frame.locator("body").evaluate(f"(b) => ({BOLD_IN_JS})([...document.querySelectorAll('section')].find(s => (s.querySelector('h2') || {{}}).textContent?.trim() === '聊天模型') || null)")
            res[f"{theme}-{vp}"] = run
            await ctx.close()
    out["privacy"] = res


# ---------- P3-19 历史页日期 ----------
DATES_JS = r"""() => {
  const title = [...document.querySelectorAll('p')].find(p => p.textContent.trim() === '自定义区间');
  const block = title ? title.parentElement : null;
  if (!block) return { block: false };
  const texts = [];
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) { const n = walker.currentNode; const el = n.parentElement; const t = n.textContent.trim(); if (!t || !el) continue;
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.5) texts.push(t); }
  const inputs = [...block.querySelectorAll('input[type=date]')].map(i => ({ label: i.getAttribute('aria-label'), opacity: parseFloat(getComputedStyle(i).opacity) }));
  const chips = [...block.querySelectorAll('label')].map(l => ({ h: Math.round(l.getBoundingClientRect().height), on: l.classList.contains('chip-on'), text: l.innerText.trim() }));
  const all = [...document.querySelectorAll('button')].find(bt => bt.textContent.trim() === '全部');
  return { block: true, visibleText: texts.join('|'), inputs, chips, allOn: all ? all.classList.contains('chip-on') : null,
           noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth };
}"""
PICKER_INIT = "(() => { const o = HTMLInputElement.prototype.showPicker; window.__pick = 0; HTMLInputElement.prototype.showPicker = function () { window.__pick++; try { return o && o.call(this); } catch (e) {} }; })();"


async def part_history(b, base, out):
    res = {}
    for loc in ("zh-CN", "en-US"):
        for vp in VIEWPORTS:
            w, h, mobile = VIEWPORTS[vp]
            ctx = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, locale=loc)
            await guard_network(ctx); await ctx.add_init_script(PICKER_INIT)
            page = await ctx.new_page(); await login(page, base)
            await page.goto(base + "/history", wait_until="load"); await page.wait_for_timeout(2500); await hide_portal(page)
            run = {"initial": await page.evaluate(DATES_JS)}
            if loc == "zh-CN":
                chip = page.locator("label", has_text="从")
                if await chip.count():
                    await chip.first.click(); await page.wait_for_timeout(300)
                    run["pickAfterClick"] = await page.evaluate("() => window.__pick")
                    await page.keyboard.press("Escape")
                    await page.get_by_label("开始日期").focus(); await page.keyboard.press("Enter"); await page.wait_for_timeout(300)
                    run["pickAfterEnter"] = await page.evaluate("() => window.__pick")
                    await page.keyboard.press("Escape")
                else:
                    await page.get_by_label("开始日期").click(); await page.wait_for_timeout(300)
                    run["pickAfterClick"] = await page.evaluate("() => window.__pick")
                await page.get_by_label("开始日期").fill("2026-10-27"); await page.wait_for_timeout(400)
                run["afterFill"] = await page.evaluate(DATES_JS)
                clear = page.locator("button", has_text="清除筛选")
                if await clear.count():
                    await clear.first.click(); await page.wait_for_timeout(300)
                await page.get_by_label("结束日期").fill("2026-10-27"); await page.wait_for_timeout(400)
                run["onlyTo"] = await page.evaluate(DATES_JS)
            res[f"{loc}-{vp}"] = run
            await ctx.close()
    out["history"] = res


# ---------- P3-21 语音 ----------
VOICE_JS = r"""() => {
  const btn = document.querySelector('.chat-composer button[aria-label^="语音"], .chat-composer button[aria-label^="正在录音"]');
  const br = btn ? btn.getBoundingClientRect() : null;
  const els = [...document.querySelectorAll('body *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim() === '松开发送' || n.nodeType === 3 && n.textContent.trim() === '再点一下发送'));
  return { label: btn ? btn.getAttribute('aria-label') : null,
    hits: els.map(e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
      return { text: e.textContent.trim(), visible: r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.5,
               inViewport: r.left >= 0 && r.right <= innerWidth && r.top >= 0, aboveButton: br ? r.bottom <= br.top + 1 : null,
               pointerEvents: cs.pointerEvents, ariaHidden: e.getAttribute('aria-hidden'), data: e.hasAttribute('data-voice-status') }; }) };
}"""


async def part_voice(b, base, out):
    res = {}
    for vp in VIEWPORTS:
        ctx, page = await open_home(b, base, vp, "day", permissions=["microphone"])
        btn = page.locator('.chat-composer button[aria-label^="语音"]').first
        box = await btn.bounding_box()
        run = {"idle": await page.evaluate(VOICE_JS)}
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await page.mouse.down(); await page.wait_for_timeout(700)
            run["holding"] = await page.evaluate(VOICE_JS)
            await page.mouse.up(); await page.wait_for_timeout(700)
            run["released"] = await page.evaluate(VOICE_JS)
        res[vp] = run
        await ctx.close()
    out["voice"] = res


# ---------- 截图 ----------
async def part_shots(b, base, out, shots_dir):
    os.makedirs(shots_dir, exist_ok=True)
    made = []
    for vp in VIEWPORTS:
        for theme in THEMES:
            ctx, page = await open_home(b, base, vp, theme)
            name = f"{theme}-{vp}"
            await hide_portal(page); await page.screenshot(path=os.path.join(shots_dir, f"{name}-openers.png")); made.append(f"{name}-openers.png")
            await open_drawer(page, "novel-drawer", "书斋"); await hide_portal(page); await page.screenshot(path=os.path.join(shots_dir, f"{name}-novel-drawer.png")); made.append(f"{name}-novel-drawer.png")
            await page.keyboard.press("Escape"); await page.wait_for_timeout(600)
            await open_drawer(page, "plaza-drawer", "世界")
            await page.locator("#plaza-drawer button.chip", has_text="匹配").first.click(); await page.wait_for_timeout(2500)
            await hide_portal(page); await page.screenshot(path=os.path.join(shots_dir, f"{name}-match.png")); made.append(f"{name}-match.png")
            await page.keyboard.press("Escape"); await page.wait_for_timeout(600)
            await open_drawer(page, "settings-drawer", "设置"); await page.wait_for_timeout(500)
            await page.frame_locator("#settings-drawer iframe").locator("body").evaluate("() => { const h = [...document.querySelectorAll('h2')].find(x => x.textContent.trim() === '聊天模型'); if (h) h.scrollIntoView({block: 'start'}); }")
            await page.wait_for_timeout(500); await hide_portal(page); await page.screenshot(path=os.path.join(shots_dir, f"{name}-privacy.png")); made.append(f"{name}-privacy.png")
            await page.goto(base + "/history", wait_until="load"); await page.wait_for_timeout(2500); await hide_portal(page)
            await hide_portal(page); await page.screenshot(path=os.path.join(shots_dir, f"{name}-history.png")); made.append(f"{name}-history.png")
            await ctx.close()
    out["shots"] = made


PARTS = {"identity": part_identity, "shelves": part_shelves, "openers": part_openers, "match": part_match,
         "privacy": part_privacy, "history": part_history, "voice": part_voice}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--parts", default=",".join(list(PARTS) + ["shots"]))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    out = {"base": a.base}
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        for name in a.parts.split(","):
            try:
                if name == "shots":
                    await part_shots(b, a.base, out, os.path.join(a.out, "shots"))
                else:
                    await PARTS[name](b, a.base, out)
            except Exception as exc:  # noqa: BLE001
                out[name] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
            print(f"[{name}] done", flush=True)
        await b.close()
    with open(os.path.join(a.out, "measure.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
