"""手机对话页修缮（2026-10-28）验收测量脚本。

用 Playwright 无头 Chromium 对一个正在运行的 Fiona 前端（dev 或 prod 均可）做同一套测量，
HEAD 与候选各跑一遍，输出 JSON 与 PNG 便于对比。只读；只用隔离实例的测试账号。

用法（在 scratchpad 等临时目录下跑，不要在含 pyproject 的目录跑 uv）：
  uv run --with playwright==<与缓存 Chromium 匹配的版本> --with pillow python measure.py \
      --base http://127.0.0.1:3097 --out <输出目录> [--user tester] [--byok-user tester2] [--themes day,night]

测量项（对应规格 §6 第 8、9 条）：
  - 状态 A/B/C 下 390×844 与 1440×900 空闲输入区高度、控件可见性、两行文字后的高度；
  - 真实点击文本框与「图片」菜单后 .chat-shell.scrollTop 与 .chat-header.top；
  - 消息区上滚 300px 后「回到最新」浮标的位置、是否在遮罩层内、与输入釉片的距离、不透明度；
  - 390 下对话列表弹层与设置抽屉的 glaze 层计算样式、底边两行像素中位差；
  - 390 与 360 下无横向滚动。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

from playwright.sync_api import sync_playwright
from PIL import Image

MEASURE_JS = r"""() => {
  const q = s => document.querySelector(s);
  const comp = q('.chat-composer').getBoundingClientRect();
  const hdr = q('.chat-header').getBoundingClientRect();
  const vis = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return { h: r.height, w: r.width, top: r.top, bottom: r.bottom, visibility: cs.visibility, opacity: cs.opacity,
      rects: el.getClientRects().length, fontSize: cs.fontSize,
      inside: r.top >= comp.top - 0.5 && r.bottom <= comp.bottom + 0.5, text: (el.textContent || '').trim().slice(0, 40) };
  };
  const actions = [...document.querySelectorAll('.chat-composer .composer-actions button')];
  const foot = [...document.querySelectorAll('.chat-composer span, .chat-composer button')]
    .map(e => e.textContent.trim()).filter(t => /每条消息|改用|思考|重试/.test(t));
  const fee = [...document.querySelectorAll('.chat-composer span')].find(s => s.textContent.includes('每条消息消耗'));
  const footerButtons = [...document.querySelectorAll('.chat-composer button')].filter(b => /改用|重试|低|中|高/.test(b.textContent.trim()));
  const tabbar = q('.mobile-tabbar');
  return {
    vw: innerWidth, vh: innerHeight,
    composer: { h: comp.height, top: comp.top, bottom: comp.bottom },
    headerTop: hdr.top, shellTop: q('.chat-shell').scrollTop, docTop: document.scrollingElement.scrollTop,
    varH: getComputedStyle(q('[data-chat-panel]')).getPropertyValue('--composer-height') || getComputedStyle(q('.chat-message-layer')).getPropertyValue('--composer-height'),
    foot,
    textarea: vis(q('.chat-composer textarea')),
    imageBtn: vis(q('.chat-composer button[aria-label^="图片"]')),
    voiceBtn: vis(actions[0]), sendBtn: vis(actions[actions.length - 1]),
    feeNote: vis(fee), footerButtons: footerButtons.map(vis),
    tabbarTop: tabbar ? tabbar.getBoundingClientRect().top : null,
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  };
}"""

PILL_JS = r"""() => {
  const pill = document.querySelector('.chat-latest');
  if (!pill) return { exists: false };
  const layer = document.querySelector('.chat-message-layer');
  const panel = document.querySelector('[data-chat-panel]').getBoundingClientRect();
  const comp = document.querySelector('.chat-composer').getBoundingClientRect();
  const r = pill.getBoundingClientRect(); const cs = getComputedStyle(pill);
  return { exists: true, inLayer: layer.contains(pill), centerDiff: (r.left + r.width / 2) - (panel.left + panel.width / 2),
    gapToComposer: comp.top - r.bottom, opacity: cs.opacity, top: r.top, bottom: r.bottom, h: r.height, left: r.left + r.width / 2,
    className: pill.className, text: pill.textContent.trim() };
}"""

GLAZE_JS = r"""(sel) => {
  const root = document.querySelector(sel);
  if (!root) return null;
  const pick = (el) => { if (!el) return null; const cs = getComputedStyle(el);
    return { display: cs.display, maskImage: cs.maskImage || cs.webkitMaskImage, background: cs.backgroundColor, backgroundImage: cs.backgroundImage, boxShadow: cs.boxShadow }; };
  const g = root.classList.contains('glaze') ? root : root.querySelector(':scope > .glaze');
  if (!g) return { error: 'no glaze' };
  const r = g.getBoundingClientRect();
  return { bottom: r.bottom, lens: pick(g.querySelector(':scope > .glaze-lens')), blur: pick(g.querySelector(':scope > .glaze-blur')),
    tint: pick(g.querySelector(':scope > .glaze-tint')), finish: pick(g.querySelector(':scope > .glaze-finish')),
    glass2: getComputedStyle(document.documentElement).getPropertyValue('--glass2').trim() };
}"""


def login(page, base: str, user: str) -> None:
    page.goto(base + "/login", wait_until="networkidle")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(base + "/", timeout=30000)
    page.wait_for_selector(".chat-composer", timeout=30000)


def settle(page, ms: int = 1500) -> None:
    # 对话页有常驻轮询，networkidle 永远等不到；按 load + 固定等待。
    page.wait_for_load_state("load")
    page.wait_for_selector(".chat-composer textarea", timeout=30000)
    page.wait_for_timeout(ms)


def hide_portal(page) -> None:
    page.evaluate("() => document.querySelectorAll('nextjs-portal').forEach(e => e.style.display = 'none')")


def row_profile(png_path: str, clip_top: int, x0: int = 200, x1: int = 380) -> dict:
    """每一行在 x0..x1（右侧、少文字）的平均 RGB；键为页面 y 坐标。"""
    img = Image.open(png_path).convert("RGB")
    prof = {}
    for y in range(img.height):
        seg = [img.getpixel((x, y)) for x in range(x0, min(x1, img.width))]
        prof[clip_top + y] = tuple(sum(c[i] for c in seg) // len(seg) for i in range(3))
    return prof


def lum(rgb) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def measure_chat(page, base: str, out: str, tag: str, mobile: bool) -> dict:
    page.goto(base + "/", wait_until="load")
    page.wait_for_selector(".chat-composer")
    settle(page)
    hide_portal(page)
    result: dict = {"tag": tag}
    result["idle"] = page.evaluate(MEASURE_JS)
    # T1：真实点击文本框、再打开图片菜单
    page.click(".chat-composer textarea")
    page.wait_for_timeout(400)
    result["afterFocus"] = page.evaluate(MEASURE_JS)
    page.click('.chat-composer button[aria-label^="图片"]')
    page.wait_for_timeout(400)
    result["afterMenu"] = page.evaluate(MEASURE_JS)
    result["shellScrollable"] = page.evaluate("() => { const s = document.querySelector('.chat-shell'); s.scrollTop = 40; const got = s.scrollTop; s.scrollTop = 0; return got; }")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    # 两行文字
    page.fill(".chat-composer textarea", "测试一下，这是一条较长的输入，看看输入区会怎么长高，再多写几个字让它换行。")
    page.wait_for_timeout(400)
    result["twoLines"] = page.evaluate(MEASURE_JS)
    page.fill(".chat-composer textarea", "")
    page.wait_for_timeout(300)
    # T2：上滚 300px 看浮标。账号当前对话可能是空的（新建的「新的交流」），先切到有消息的样例对话。
    scrollable = page.evaluate("() => { const vp = document.querySelector('[data-chat-scroll-viewport]'); return vp.scrollHeight - vp.clientHeight > 300; }")
    if not scrollable:
        if mobile:
            page.click('button[aria-label="对话列表"]')
            page.wait_for_timeout(500)
        candidates = page.locator("button:visible", has_text="与我的分身交流")
        if candidates.count():
            candidates.first.click()
            page.wait_for_timeout(1500)
            hide_portal(page)
        elif mobile:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
    result["pillScrollable"] = page.evaluate("() => { const vp = document.querySelector('[data-chat-scroll-viewport]'); return vp.scrollHeight - vp.clientHeight; }")
    for _ in range(2):  # 跟随逻辑要看到两次向上滚动才判定「用户离开底部」
        page.evaluate("() => { const vp = document.querySelector('[data-chat-scroll-viewport]'); vp.scrollTop = Math.max(0, vp.scrollTop - 150); }")
        page.wait_for_timeout(350)
    page.wait_for_timeout(400)
    result["pill"] = page.evaluate(PILL_JS)
    comp_top = result["idle"]["composer"]["top"]
    clip = {"x": 0, "y": max(0, int(comp_top) - 120), "width": int(result["idle"]["vw"]), "height": 130}
    pill_png = os.path.join(out, f"{tag}-pill.png")
    page.screenshot(path=pill_png, clip=clip)
    result["pillPng"] = pill_png
    if result["pill"].get("exists"):
        # 层级探针：浮标可见时打开「图片」菜单，浮标中心点命中的应是菜单项，而不是浮标
        pr = result["pill"]
        page.click('.chat-composer button[aria-label^="图片"]')
        page.wait_for_timeout(400)
        result["pillUnderMenu"] = page.evaluate("([cx, cy]) => { const el = document.elementFromPoint(cx, cy); const menu = el && el.closest('[role=menu], [role=menuitem]'); return { hit: el ? (el.className && el.className.toString().slice(0, 60)) : null, inMenu: !!menu, isPill: !!(el && el.closest('.chat-latest')), menuOpen: !!document.querySelector('[role=menu]') }; }", [pr["left"] if "left" in pr else 195, (pr["top"] + pr["bottom"]) / 2])
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.click(".chat-latest")
        page.wait_for_timeout(600)
        result["afterPillClick"] = page.evaluate("() => { const vp = document.querySelector('[data-chat-scroll-viewport]'); return { atBottom: vp.scrollHeight - vp.clientHeight - vp.scrollTop <= 2, pill: !!document.querySelector('.chat-latest') }; }")
    if mobile:
        # 对话列表弹层
        page.click('button[aria-label="对话列表"]')
        page.wait_for_timeout(700)
        result["modal"] = page.evaluate(GLAZE_JS, "#conversation-picker-dialog")
        modal_png = os.path.join(out, f"{tag}-modal-bottom.png")
        page.screenshot(path=modal_png, clip={"x": 0, "y": 700, "width": 390, "height": 90})
        result["modalPng"] = modal_png
        mprof = row_profile(modal_png, 700)
        result["modalRows"] = {str(k): v for k, v in mprof.items()}
        result["modalGradient_740_to_782"] = lum(mprof[740]) - lum(mprof[782])
        result["modalMaxStep_772_783"] = max(abs(lum(mprof[y]) - lum(mprof[y - 1])) for y in range(773, 784))
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        # 设置抽屉底边
        page.click('.mobile-tabbar button:has-text("设置")')
        page.wait_for_timeout(900)
        result["drawer"] = page.evaluate(GLAZE_JS, "#settings-drawer")
        clip_top = 760
        drawer_png = os.path.join(out, f"{tag}-drawer-bottom.png")
        page.screenshot(path=drawer_png, clip={"x": 0, "y": clip_top, "width": 390, "height": 30})
        result["drawerPng"] = drawer_png
        prof = row_profile(drawer_png, clip_top)
        result["drawerRows"] = {str(k): v for k, v in prof.items()}
        # 面板内部最后 12 行（772–783）相邻两行亮度跳变的最大值：有横线则大
        result["drawerMaxStep_772_783"] = max(abs(lum(prof[y]) - lum(prof[y - 1])) for y in range(773, 784))
        page.click('.mobile-tabbar button:has-text("对话")')
        page.wait_for_timeout(300)
    return result


def run(base: str, out: str, user: str, byok_user: str | None, themes: list[str], pw_version: str) -> dict:
    os.makedirs(out, exist_ok=True)
    report: dict = {"base": base, "playwright": pw_version, "runs": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in themes:
            for label, viewport, is_mobile in (("m390", (390, 844), True), ("d1440", (1440, 900), False), ("m360", (360, 740), True)):
                ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, is_mobile=is_mobile, has_touch=is_mobile,
                                          device_scale_factor=1, color_scheme="light")
                page = ctx.new_page()
                login(page, base, user)
                page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
                tag = f"A-{theme}-{label}"
                if label == "m360":
                    page.goto(base + "/", wait_until="load"); settle(page)
                    report["runs"].append({"tag": tag, "idle": page.evaluate(MEASURE_JS)})
                else:
                    report["runs"].append(measure_chat(page, base, out, tag, is_mobile))
                ctx.close()
        if byok_user:
            for label, viewport, is_mobile in (("m390", (390, 844), True), ("d1440", (1440, 900), False)):
                ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, is_mobile=is_mobile, has_touch=is_mobile,
                                          device_scale_factor=1, color_scheme="light")
                page = ctx.new_page()
                login(page, base, byok_user)
                page.evaluate("() => localStorage.setItem('chloe-appearance', 'day')")
                put = page.request.put(base + "/api/chat-model", data={"provider": "anthropic", "model": "claude-haiku-5-5", "api_key": "sk-ant-api03-" + "A" * 60})
                report.setdefault("byokSetup", []).append({"viewport": label, "put": put.status, "body": put.text()[:300]})
                if put.ok:
                    # PUT 不会把已存在记录的 enabled 改回 true（store.py:173 沿用旧值），显式 PATCH 才是真正的 C 态。
                    enable = page.request.patch(base + "/api/chat-model", data={"enabled": True})
                    report["byokSetup"].append({"viewport": label, "patch_enable": enable.status, "body": enable.text()[:200]})
                    page.goto(base + "/", wait_until="load"); settle(page)
                    c_state = page.evaluate("() => ({ radiogroup: !!document.querySelector('.chat-composer [role=radiogroup]'), toPlatform: [...document.querySelectorAll('.chat-composer button')].some(b => b.textContent.trim() === '改用平台') })")
                    report["byokSetup"].append({"viewport": label, "c_state_check": c_state})
                    report["runs"].append(measure_chat(page, base, out, f"C-day-{label}", is_mobile))
                    patch = page.request.patch(base + "/api/chat-model", data={"enabled": False})
                    report["byokSetup"].append({"viewport": label, "patch": patch.status})
                    report["runs"].append(measure_chat(page, base, out, f"B-day-{label}", is_mobile))
                ctx.close()
        browser.close()
    with open(os.path.join(out, "measure.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return report


def summary(report: dict) -> str:
    lines = []
    for r in report["runs"]:
        idle = r["idle"]
        line = f"{r['tag']:<14} composer={idle['composer']['h']:.0f} header={idle['headerTop']:.0f} shell={idle['shellTop']} foot={idle['foot']} hscroll={idle['hscroll']}"
        if "afterFocus" in r:
            line += f" | focus: header={r['afterFocus']['headerTop']:.0f} shell={r['afterFocus']['shellTop']} menu: header={r['afterMenu']['headerTop']:.0f} shell={r['afterMenu']['shellTop']}"
            line += f" | twoLines={r['twoLines']['composer']['h']:.0f}"
        if "pill" in r:
            pl = r["pill"]
            line += f" | pill(scrollable={r.get('pillScrollable')}): " + (f"inLayer={pl['inLayer']} gap={pl['gapToComposer']:.1f} center={pl['centerDiff']:.1f} op={pl['opacity']}" if pl.get("exists") else "none")
        if "pillUnderMenu" in r:
            pm = r["pillUnderMenu"]
            line += f" | pillUnderMenu: inMenu={pm['inMenu']} isPill={pm['isPill']} menuOpen={pm['menuOpen']}"
        if "shellScrollable" in r:
            line += f" | shellScrollTo40={r['shellScrollable']}"
        if "drawerMaxStep_772_783" in r:
            line += f" | drawerStep={r['drawerMaxStep_772_783']:.1f} modalGrad={r['modalGradient_740_to_782']:.1f} modalStep={r['modalMaxStep_772_783']:.1f}"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--user", default="tester")
    ap.add_argument("--byok-user", default=None)
    ap.add_argument("--themes", default="day,night")
    args = ap.parse_args()
    try:
        from playwright._repo_version import version as pw_version
    except Exception:  # pragma: no cover
        pw_version = "?"
    rep = run(args.base, args.out, args.user, args.byok_user, [t for t in args.themes.split(",") if t], pw_version)
    print(summary(rep))
