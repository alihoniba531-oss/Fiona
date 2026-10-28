"""组件语言统一（2026-10-28）验收测量脚本：规格 §6 第 8 条。

HEAD 与候选各跑一遍；HEAD 上的「原生弹窗次数、入场动画、焦点、粗体」四项是正控（HEAD 必须失败）。
只用隔离实例的测试账号；会删除隔离库里样例对话的最后一条消息（仅 --full 时）。

用法（在 scratchpad 等临时目录下跑 uv，不要在含 pyproject 的目录跑）：
  uv run --with playwright==1.63.0 python measure.py --base http://127.0.0.1:3098 --out <目录> [--full]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

SAMPLE_CONVERSATION = "与我的分身交流"

BOLD_JS = r"""() => {
  const hits = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('nextjs-portal')) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const w = parseInt(cs.fontWeight, 10);
    if (w >= 600) hits.push({ tag: el.tagName, w, text: el.textContent.trim().slice(0, 30), cls: String(el.className).slice(0, 60) });
  }
  return hits;
}"""

META_JS = r"""() => {
  const vis = b => { const r = b.getBoundingClientRect(); const cs = getComputedStyle(b); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.5; };
  const btns = [...document.querySelectorAll('[data-chat-scroll-content] button')];
  const by = t => btns.filter(b => b.textContent.trim() === t);
  const speak = by('朗读'), copy = by('复制'), del = by('删除');
  const rows = new Set([...speak, ...copy, ...del].map(b => b.parentElement));
  return {
    ai: document.querySelectorAll('[data-chat-scroll-content] .bubble-ai').length,
    user: document.querySelectorAll('[data-chat-scroll-content] .bubble-user').length,
    speak: speak.length, speakVisible: speak.filter(vis).length,
    copy: copy.length, copyVisible: copy.filter(vis).length,
    del: del.length, delVisible: del.filter(vis).length,
    svgInMetaRows: [...rows].reduce((n, r) => n + r.querySelectorAll('svg').length, 0),
    minHeight: Math.min(...[...speak, ...copy, ...del].map(b => b.getBoundingClientRect().height), 999),
    animated: document.querySelectorAll('.msg-in-left, .msg-in-right').length,
    voicePressed: (document.querySelector('.chat-header button[aria-label="朗读"]') || {}).ariaPressed ?? null,
  };
}"""

FOCUS_JS = r"""() => {
  const el = document.activeElement; if (!el || el === document.body) return null;
  const cs = getComputedStyle(el);
  const ink = getComputedStyle(document.documentElement).getPropertyValue('--ink').trim();
  return { tag: el.tagName, text: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 20), type: el.getAttribute('type'),
    outlineStyle: cs.outlineStyle, outlineWidth: cs.outlineWidth, outlineColor: cs.outlineColor, boxShadow: cs.boxShadow, ink };
}"""


def login(page, base, user="tester"):
    page.goto(base + "/login", wait_until="load")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(base + "/", timeout=60000)
    page.wait_for_selector(".chat-composer textarea", timeout=60000)


def hide_portal(page):
    page.evaluate("() => document.querySelectorAll('nextjs-portal').forEach(e => e.style.display = 'none')")


def open_sample(page, mobile):
    if mobile:
        page.click('button[aria-label="对话列表"]'); page.wait_for_timeout(500)
    page.locator("button:visible", has_text=SAMPLE_CONVERSATION).first.click()
    page.wait_for_timeout(1800); hide_portal(page)
    page.mouse.move(1, 1)


def rgb(color):
    return color.replace(" ", "")


def run(base, out, full):
    os.makedirs(out, exist_ok=True)
    rep = {"base": base, "runs": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in ("day", "night"):
            for label, (w, h), mobile in (("d1440", (1440, 900), False), ("m390", (390, 844), True)):
                ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
                ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
                page = ctx.new_page()
                natives = []
                page.on("dialog", lambda d: (natives.append(d.message), d.dismiss()))
                ticket_reqs, delete_reqs = [], []
                page.on("request", lambda r: ticket_reqs.append(r.url) if "/tts/ticket" in r.url else (delete_reqs.append(r.url) if r.method == "DELETE" else None))
                login(page, base)
                page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
                page.goto(base + "/", wait_until="load"); page.wait_for_selector(".chat-composer textarea"); page.wait_for_timeout(1500); hide_portal(page)
                open_sample(page, mobile)
                r = {"tag": f"{theme}-{label}", "meta": page.evaluate(META_JS)}
                # 朗读
                speak = page.locator("[data-chat-scroll-content] button", has_text="朗读")
                if speak.count():
                    target = speak.nth(min(1, speak.count() - 1))
                    target.scroll_into_view_if_needed(); target.click(); page.wait_for_timeout(600)
                    r["speak"] = {"labelAfterClick": target.text_content().strip() if target.count() else None,
                                  "stopButtons": page.locator("[data-chat-scroll-content] button", has_text="停止").count(),
                                  "ticketRequests": len(ticket_reqs)}
                    stop = page.locator("[data-chat-scroll-content] button", has_text="停止")
                    if stop.count():
                        stop.first.click(); page.wait_for_timeout(500)
                    r["speak"]["stopAfterStop"] = page.locator("[data-chat-scroll-content] button", has_text="停止").count()
                    r["speak"]["voicePressedAfter"] = page.evaluate(META_JS)["voicePressed"]
                # 复制（Markdown 那条：含「本周读书计划」）
                md = page.locator("[data-chat-scroll-content] .bubble-ai", has_text="本周读书计划")
                if md.count():
                    row_copy = page.locator("[data-chat-scroll-content] div:has(> .bubble-ai:has-text('本周读书计划')) button", has_text="复制")
                    if row_copy.count():
                        row_copy.first.scroll_into_view_if_needed(); row_copy.first.click(); page.wait_for_timeout(300)
                        label_after = page.locator("[data-chat-scroll-content] button", has_text="已复制").count()
                        clip = page.evaluate("() => navigator.clipboard.readText()")
                        r["copy"] = {"copiedLabels": label_after, "hasStars": "**" in clip, "hasHeading": any(l.startswith("## ") for l in clip.splitlines()),
                                     "hasDashItem": any(l.startswith("- ") for l in clip.splitlines()), "len": len(clip), "head": clip[:40]}
                # 删除：先 Esc 取消
                dels = page.locator("[data-chat-scroll-content] button", has_text="删除")
                if dels.count():
                    before = page.evaluate("() => document.querySelectorAll('[data-chat-scroll-content] .bubble-ai, [data-chat-scroll-content] .bubble-user').length")
                    dels.last.scroll_into_view_if_needed(); dels.last.click(); page.wait_for_timeout(400)
                    r["delete"] = page.evaluate("() => { const d = document.querySelector('.confirm-dialog[open]'); return { open: !!d, text: d ? d.textContent.trim().slice(0, 60) : null, focus: document.activeElement ? document.activeElement.textContent.trim() : null, role: d ? d.getAttribute('role') : null }; }")
                    page.screenshot(path=os.path.join(out, f"{theme}-{label}-confirm.png"))
                    page.keyboard.press("Escape"); page.wait_for_timeout(300)
                    after = page.evaluate("() => document.querySelectorAll('[data-chat-scroll-content] .bubble-ai, [data-chat-scroll-content] .bubble-user').length")
                    r["delete"].update({"openAfterEsc": page.locator(".confirm-dialog[open]").count(), "countBefore": before, "countAfterEsc": after, "deleteReqsAfterEsc": len(delete_reqs)})
                    r["boldWithDialog"] = None
                    if full and theme == "day" and label == "d1440":
                        dels.last.click(); page.wait_for_timeout(300)
                        r["boldWithDialog"] = page.evaluate(BOLD_JS)
                        page.locator(".confirm-dialog[open] button", has_text="删除").click(); page.wait_for_timeout(800)
                        r["delete"]["countAfterConfirm"] = page.evaluate("() => document.querySelectorAll('[data-chat-scroll-content] .bubble-ai, [data-chat-scroll-content] .bubble-user').length")
                        r["delete"]["deleteReqsAfterConfirm"] = len(delete_reqs)
                # 原生弹窗流程（只在昼 1440 跑一遍）
                if theme == "day" and label == "d1440":
                    flows = {}
                    page.locator('button[aria-label="删除对话"]').first.click(force=True); page.wait_for_timeout(400)
                    flows["deleteConversationDialog"] = page.locator(".confirm-dialog[open]").count()
                    if flows["deleteConversationDialog"]:
                        page.locator(".confirm-dialog[open] button", has_text="取消").click(); page.wait_for_timeout(300)
                    page.set_input_files('input[type=file][accept="image/*"]', files=[{"name": "note.txt", "mimeType": "text/plain", "buffer": b"hello"}])
                    page.wait_for_timeout(400)
                    flows["uploadNotice"] = page.evaluate("() => { const d = document.querySelector('.confirm-dialog[open]'); return d ? d.textContent.trim().slice(0, 30) : null; }")
                    if flows["uploadNotice"]:
                        page.locator(".confirm-dialog[open] button", has_text="知道了").click(); page.wait_for_timeout(300)
                    # 入场动画：加载后为 0；发一条后只有末尾的带动画
                    flows["animatedOnLoad"] = page.evaluate(META_JS)["animated"]
                    page.fill(".chat-composer textarea", "测试动画"); page.keyboard.press("Enter"); page.wait_for_timeout(1500)
                    flows["animatedAfterSend"] = page.evaluate("() => { const all = [...document.querySelectorAll('[data-chat-scroll-content] .group')]; const anim = all.map((e, i) => [i, e.matches('.msg-in-left, .msg-in-right')]).filter(x => x[1]).map(x => x[0]); return { total: all.length, animatedIdx: anim }; }")
                    # 焦点：Tab 30 步
                    page.goto(base + "/", wait_until="load"); page.wait_for_selector(".chat-composer textarea"); page.wait_for_timeout(1200); hide_portal(page)
                    page.mouse.click(5, 5)
                    stops = []
                    for _ in range(30):
                        page.keyboard.press("Tab"); page.wait_for_timeout(60)
                        f = page.evaluate(FOCUS_JS)
                        if f: stops.append(f)
                    bad = [s for s in stops if s["tag"] not in ("INPUT", "TEXTAREA") and not (s["outlineStyle"] == "solid" and float(s["outlineWidth"].rstrip("px") or 0) >= 1) and s["boxShadow"] in ("none", "")]
                    flows["focus"] = {"stops": len(stops), "bad": bad[:8], "badCount": len(bad), "styles": sorted({(s["outlineStyle"], s["outlineWidth"]) for s in stops})}
                    # 设置页「清空」→ 取消
                    page.goto(base + "/settings", wait_until="load"); page.wait_for_timeout(1500); hide_portal(page)
                    page.locator("button", has_text="的所有聊天记录").first.click(); page.wait_for_timeout(400)
                    flows["settingsClearDialog"] = page.locator(".confirm-dialog[open]").count()
                    if flows["settingsClearDialog"]:
                        page.locator(".confirm-dialog[open] button", has_text="取消").click(); page.wait_for_timeout(300)
                    flows["nativeDialogs"] = list(natives)
                    # 粗体扫描（含历史抽屉）
                    bold = {}
                    for route in ("/settings", "/agents", "/agents/me", "/plaza", "/profile", "/history", "/novels"):
                        page.goto(base + route, wait_until="load"); page.wait_for_timeout(1800); hide_portal(page)
                        bold[route] = page.evaluate(BOLD_JS)
                    page.goto(base + "/", wait_until="load"); page.wait_for_selector(".chat-composer textarea"); page.wait_for_timeout(1200); hide_portal(page)
                    open_sample(page, False)
                    page.get_by_role("button", name="历史：当前对话记录").click(); page.wait_for_timeout(600)
                    bold["/ (history drawer open)"] = page.evaluate(BOLD_JS)
                    flows["bold"] = {k: v[:6] for k, v in bold.items()}
                    flows["boldTotal"] = sum(len(v) for v in bold.values())
                    r["flows"] = flows
                r["nativeDialogsThisRun"] = len(natives)
                rep["runs"].append(r)
                ctx.close()
        browser.close()
    with open(os.path.join(out, "measure.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True); ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    rep = run(a.base, a.out, a.full)
    for r in rep["runs"]:
        print(json.dumps({k: v for k, v in r.items() if k != "flows"}, ensure_ascii=False)[:900])
        if "flows" in r:
            fl = dict(r["flows"]); fl["bold"] = {k: len(v) for k, v in fl["bold"].items()}
            print("FLOWS", json.dumps(fl, ensure_ascii=False)[:1500])
