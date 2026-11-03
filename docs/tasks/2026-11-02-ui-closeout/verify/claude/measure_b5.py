"""第五批（UI 复核收尾）真实浏览器实测：同一脚本量 HEAD 与候选，输出 JSON 并按期望打 PASS/FAIL。

用法（在 scratchpad 下跑，不要在含 pyproject 的目录跑 uv）：
  uv run --no-project --with playwright==1.63.0 python measure_b5.py \
      --base http://127.0.0.1:3097 --db <隔离库路径> --out <目录> --tag head|cand

只用隔离实例的测试账号；不发聊天请求。--tag 决定期望值：head 是正控（旧行为必须被量到），cand 是本批判据。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3

from playwright.sync_api import sync_playwright

SEEN_KEY = "fiona_cost_hint_seen:"


def login(page, base: str, user: str) -> None:
    page.goto(base + "/login", wait_until="networkidle")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(base + "/", timeout=30000)
    page.wait_for_selector(".chat-composer", timeout=30000)


def settle(page, ms: int = 1500) -> None:
    page.wait_for_load_state("load")
    page.wait_for_selector(".chat-composer textarea", timeout=30000)
    page.wait_for_timeout(ms)


COMPOSER_JS = r"""() => {
  const comp = document.querySelector('.chat-composer'); const r = comp.getBoundingClientRect();
  const vis = el => { const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && (el.checkVisibility ? el.checkVisibility() : true); };
  const spans = [...comp.querySelectorAll('span')];
  const find = re => spans.find(s => re.test(s.textContent) && vis(s));
  const fee = find(/每条消息消耗|每条 10 颗草莓/);
  const left = find(/还剩/);
  const hint = find(/Enter 发送/);
  const row = [...comp.querySelectorAll('div')].find(d => typeof d.className === 'string' && d.className.includes('border-t') && d.className.includes('pt-2'));
  return { h: Math.round(r.height * 100) / 100,
    feeText: fee ? fee.textContent.replace(/\s+/g, ' ').trim() : null, feeColor: fee ? getComputedStyle(fee).color : null,
    leftText: left ? left.textContent.replace(/\s+/g, ' ').trim() : null,
    hintVisible: !!hint, rowVisible: row ? vis(row) : null, rowH: row ? Math.round(row.getBoundingClientRect().height * 100) / 100 : null,
    toggle: [...comp.querySelectorAll('button')].some(b => /改用/.test(b.textContent)),
    radiogroup: !!comp.querySelector('[role=radiogroup]') };
}"""

BACKDROP_JS = r"""(classes) => { const out = {};
  for (const cls of classes) {
    const d = document.createElement('dialog'); d.className = cls; d.textContent = 'x'; document.body.appendChild(d); d.showModal();
    out[cls] = getComputedStyle(d, '::backdrop').backgroundColor; d.close(); d.remove(); }
  return out; }"""

ACTIVE_JS = r"""() => { const a = document.activeElement; if (!a) return null;
  return { tag: a.tagName, type: a.getAttribute('type'), label: a.getAttribute('aria-label'), chip: a.getAttribute('data-chip'),
    opacity: getComputedStyle(a).opacity, tabindex: a.getAttribute('tabindex') }; }"""


def set_balance(db: str, user: str, balance: int) -> None:
    con = sqlite3.connect(db)
    con.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (balance, user))
    con.commit(); con.close()


def composer_states(p, base: str, db: str, report: dict) -> None:
    browser = p.chromium.launch()
    for label, viewport, is_mobile in (("m390", (390, 844), True), ("d1440", (1440, 900), False)):
        for theme in ("day", "night") if label == "m390" else ("day",):
            ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, is_mobile=is_mobile, has_touch=is_mobile,
                                      device_scale_factor=1, color_scheme="light")
            page = ctx.new_page()
            # A：平台模型。先登录，再控制「首次」标记。
            login(page, base, "tester")
            page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
            page.evaluate("(k) => localStorage.removeItem(k)", SEEN_KEY + "tester")
            page.goto(base + "/", wait_until="load"); settle(page)
            report["runs"].append({"tag": f"A-first-{theme}-{label}", **page.evaluate(COMPOSER_JS),
                                   "seenAfter": page.evaluate("(k) => localStorage.getItem(k)", SEEN_KEY + "tester")})
            page.goto(base + "/", wait_until="load"); settle(page)
            report["runs"].append({"tag": f"A-seen-{theme}-{label}", **page.evaluate(COMPOSER_JS)})
            ctx.close()
            # A-low：余额 20。
            ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, is_mobile=is_mobile, has_touch=is_mobile,
                                      device_scale_factor=1, color_scheme="light")
            page = ctx.new_page()
            login(page, base, "testerlow")
            set_balance(db, "testerlow", 20)
            page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
            page.evaluate("(k) => localStorage.setItem(k, '1')", SEEN_KEY + "testerlow")
            page.goto(base + "/", wait_until="load"); settle(page, 2500)
            report["runs"].append({"tag": f"A-low-{theme}-{label}", **page.evaluate(COMPOSER_JS)})
            ctx.close()
        # B / C：自带模型。
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, is_mobile=is_mobile, has_touch=is_mobile,
                                  device_scale_factor=1, color_scheme="light")
        page = ctx.new_page()
        login(page, base, "tester2")
        page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", "day")
        page.evaluate("(k) => localStorage.setItem(k, '1')", SEEN_KEY + "tester2")
        put = page.request.put(base + "/api/chat-model", data={"provider": "anthropic", "model": "claude-haiku-5-5", "api_key": "sk-ant-api03-" + "A" * 60})
        report.setdefault("byokSetup", []).append({"viewport": label, "put": put.status, "body": put.text()[:200]})
        if put.ok:
            enable = page.request.patch(base + "/api/chat-model", data={"enabled": True})
            report["byokSetup"].append({"viewport": label, "patch_enable": enable.status})
            page.goto(base + "/", wait_until="load"); settle(page)
            report["runs"].append({"tag": f"C-day-{label}", **page.evaluate(COMPOSER_JS)})
            page.request.patch(base + "/api/chat-model", data={"enabled": False})
            page.goto(base + "/", wait_until="load"); settle(page)
            report["runs"].append({"tag": f"B-day-{label}", **page.evaluate(COMPOSER_JS)})
        ctx.close()
    browser.close()


def history_keyboard(p, base: str, report: dict) -> None:
    browser = p.chromium.launch()
    for label, viewport, is_mobile in (("d1440", (1440, 900), False), ("m390", (390, 844), True)):
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, is_mobile=is_mobile, has_touch=is_mobile,
                                  device_scale_factor=1, color_scheme="light")
        page = ctx.new_page()
        login(page, base, "tester")
        page.goto(base + "/history", wait_until="load")
        page.wait_for_selector('input[type="date"]', timeout=30000)
        page.wait_for_timeout(1000)
        page.evaluate("() => { window.__sp = 0; HTMLInputElement.prototype.showPicker = function () { window.__sp++; }; }")
        out: dict = {"tag": f"history-{label}"}
        # Tab 一圈，记录焦点序列。
        page.evaluate("() => { document.body.focus(); if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur(); }")
        seq = []
        for _ in range(60):
            page.keyboard.press("Tab")
            seq.append(page.evaluate(ACTIVE_JS))
        out["dateInputFocused"] = any(s and s["tag"] == "INPUT" and s["type"] == "date" for s in seq)
        out["chipButtons"] = [s["label"] for s in seq if s and s["tag"] == "BUTTON" and s["label"] and ("开始日期" in s["label"] or "结束日期" in s["label"])]
        out["dateInputs"] = page.evaluate("""() => [...document.querySelectorAll('input[type=date]')].map(i => ({
            label: i.getAttribute('aria-label'), hidden: i.getAttribute('aria-hidden'), tabindex: i.getAttribute('tabindex'), chip: i.getAttribute('data-chip'),
            opacity: getComputedStyle(i).opacity }))""")
        # 键盘：Enter / Space 打开选择器。
        btn = page.locator('button[aria-label^="从（开始日期）"]')
        if btn.count():
            btn.first.focus()
            page.evaluate("() => { window.__sp = 0; }")
            page.keyboard.press("Enter")
            out["spAfterEnter"] = page.evaluate("() => window.__sp")
            page.keyboard.press("Space")
            out["spAfterSpace"] = page.evaluate("() => window.__sp")
            out["focusRingOnLabel"] = page.evaluate("""() => { const b = document.querySelector('button[aria-label^="从（开始日期）"]');
                const l = b.closest('label'); const cs = getComputedStyle(l); return { outlineStyle: cs.outlineStyle, outlineWidth: cs.outlineWidth, outlineColor: cs.outlineColor,
                matches: l.matches(':has(:focus-visible)') }; }""")
            # 退回：showPicker 抛错 → 原生框显出来并得到焦点；失焦后藏回去。
            page.evaluate("() => { HTMLInputElement.prototype.showPicker = function () { throw new TypeError('no'); }; }")
            btn.first.focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(200)
            out["fallbackActive"] = page.evaluate(ACTIVE_JS)
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            page.wait_for_timeout(200)
            out["fallbackAfterBlur"] = page.evaluate("""() => { const i = document.querySelector('input[data-chip="from"]'); return i ? getComputedStyle(i).opacity : null; }""")
            page.evaluate("() => { HTMLInputElement.prototype.showPicker = function () { window.__sp++; }; }")
            # 选定日期后按钮的可访问名称带中文日期。
            page.fill('input[data-chip="from"]', "2026-11-02")
            page.wait_for_timeout(300)
            out["labelAfterPick"] = page.evaluate("""() => document.querySelector('button[aria-label^="从（开始日期）"]').getAttribute('aria-label')""")
        # 指针：点 chip 仍由原生框接到 click（手机用 tap）。
        page.evaluate("() => { window.__sp = 0; }")
        chip = page.locator('label:has(input[type="date"])').first
        if is_mobile:
            chip.tap()
        else:
            chip.click()
        page.wait_for_timeout(200)
        out["pointerActive"] = page.evaluate(ACTIVE_JS)
        out["spAfterPointer"] = page.evaluate("() => window.__sp")
        report["runs"].append(out)
        ctx.close()
    browser.close()


def backdrops(p, base: str, report: dict) -> None:
    classes = ["scrim-dialog", "image-preview-dialog", "confirm-dialog", "m-auto backdrop:bg-[color:var(--scrim)]"]
    browser = p.chromium.launch()
    for theme in ("day", "night"):
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page = ctx.new_page()
        login(page, base, "tester")
        page.evaluate("(t) => localStorage.setItem('chloe-appearance', t)", theme)
        page.goto(base + "/", wait_until="load"); settle(page)
        out = {"tag": f"backdrop-{theme}", "dark": page.evaluate("() => document.documentElement.classList.contains('dark')")}
        out["resolved"] = page.evaluate(BACKDROP_JS, classes)
        # 让 --scrim 无法解析，模拟取不到 :root 变量的旧版 Safari：var() 只能退回兜底色。
        page.add_style_tag(content=":root, .dark { --scrim: initial; }")
        page.wait_for_timeout(100)
        out["unresolvable"] = page.evaluate(BACKDROP_JS, classes)
        report["runs"].append(out)
        ctx.close()
    browser.close()


def judge(report: dict, tag: str) -> list[tuple[str, bool, str]]:
    runs = {r["tag"]: r for r in report["runs"]}
    res: list[tuple[str, bool, str]] = []

    def chk(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    cand = tag == "cand"
    for vp in ("m390", "d1440"):
        for theme in (("day", "night") if vp == "m390" else ("day",)):
            first = runs.get(f"A-first-{theme}-{vp}", {}); seen = runs.get(f"A-seen-{theme}-{vp}", {}); low = runs.get(f"A-low-{theme}-{vp}", {})
            # 没有自带模型配置的账号走 `chatMode && config ?` 的 else 分支：文字是「每条消息消耗 10 颗草莓」，
            # 「平台模型 · 每条 10 颗草莓」只在有配置但没启用（B 态）时出现。
            if cand:
                chk(f"{vp}/{theme} 首次显示费用文字", first.get("feeText") == "每条消息消耗 10 颗草莓", str(first.get("feeText")))
                chk(f"{vp}/{theme} 首次后已记标记", first.get("seenAfter") == "1", str(first.get("seenAfter")))
                chk(f"{vp}/{theme} 再次打开不显示费用", seen.get("feeText") is None, str(seen.get("feeText")))
                chk(f"{vp}/{theme} 低余额显示并带余额", low.get("feeText") == "每条消息消耗 10 颗草莓，还剩 20 颗", str(low.get("feeText")))
                chk(f"{vp}/{theme} 低余额朱色", low.get("feeColor") in ("rgb(168, 50, 42)", "rgb(229, 111, 93)"), str(low.get("feeColor")))
                chk(f"{vp}/{theme} 首次是墨色不是朱色", first.get("feeColor") not in ("rgb(168, 50, 42)", "rgb(229, 111, 93)"), str(first.get("feeColor")))
                if vp == "m390":
                    chk(f"{vp}/{theme} 非首次整行隐藏", seen.get("rowVisible") is False, f"rowVisible={seen.get('rowVisible')} h={seen.get('h')}")
                    chk(f"{vp}/{theme} 非首次空闲高度 100–115", seen.get("h") is not None and 100 <= seen["h"] <= 115, str(seen.get("h")))
                    chk(f"{vp}/{theme} 首次空闲高度 ≈133", first.get("h") is not None and 131 <= first["h"] <= 135, str(first.get("h")))
                else:
                    chk(f"{vp} 桌面仍显示 Enter 提示", seen.get("hintVisible") is True and seen.get("rowVisible") is True, str(seen.get("hintVisible")))
            else:
                chk(f"{vp}/{theme} HEAD 常显费用", first.get("feeText") == "每条消息消耗 10 颗草莓" and seen.get("feeText") == "每条消息消耗 10 颗草莓", f"{first.get('feeText')} / {seen.get('feeText')}")
                chk(f"{vp}/{theme} HEAD 低余额不带余额数", low.get("feeText") == "每条消息消耗 10 颗草莓" and not low.get("leftText"), str(low.get("feeText")))
                if vp == "m390":
                    chk(f"{vp}/{theme} HEAD 空闲高度 ≈133", seen.get("h") is not None and 131 <= seen["h"] <= 135, str(seen.get("h")))
        c = runs.get(f"C-day-{vp}", {}); b = runs.get(f"B-day-{vp}", {})
        chk(f"{vp} C 态有思考档与改用平台", c.get("radiogroup") is True and c.get("toggle") is True, str(c))
        chk(f"{vp} B 态有改用我的模型", b.get("toggle") is True, str(b))
        if vp == "m390":
            chk(f"{vp} B/C 高度 ≈157", all(x.get("h") is not None and 155 <= x["h"] <= 159 for x in (b, c)), f"B={b.get('h')} C={c.get('h')}")
    for vp in ("d1440", "m390"):
        h = runs.get(f"history-{vp}", {})
        if cand:
            chk(f"history/{vp} 原生框不在 Tab 序列", h.get("dateInputFocused") is False, str(h.get("dateInputFocused")))
            # 60 次 Tab 会在页面里绕好几圈，所以按去重后的顺序判：只有这两个按钮，且「从」在「到」前面。
            uniq = list(dict.fromkeys(h.get("chipButtons", [])))
            chk(f"history/{vp} Tab 落在两个 chip 按钮", len(uniq) == 2 and uniq[0].startswith("从（开始日期）：") and uniq[1].startswith("到（结束日期）："), str(uniq))
            chk(f"history/{vp} 原生框 aria-hidden 且 tabindex -1", all(i.get("hidden") == "true" and i.get("tabindex") == "-1" for i in h.get("dateInputs", [])) and len(h.get("dateInputs", [])) == 2, str(h.get("dateInputs")))
            chk(f"history/{vp} Enter 调一次 showPicker", h.get("spAfterEnter") == 1, str(h.get("spAfterEnter")))
            chk(f"history/{vp} Space 再调一次", h.get("spAfterSpace") == 2, str(h.get("spAfterSpace")))
            chk(f"history/{vp} 键盘聚焦时 chip 有墨线框", (h.get("focusRingOnLabel") or {}).get("matches") is True and (h.get("focusRingOnLabel") or {}).get("outlineStyle") not in (None, "none"), str(h.get("focusRingOnLabel")))
            fa = h.get("fallbackActive") or {}
            chk(f"history/{vp} 退回时原生框可见且有焦点", fa.get("tag") == "INPUT" and fa.get("chip") == "from" and fa.get("opacity") == "1", str(fa))
            chk(f"history/{vp} 退回失焦后藏回", h.get("fallbackAfterBlur") == "0", str(h.get("fallbackAfterBlur")))
            chk(f"history/{vp} 选日期后可访问名称带中文日期", (h.get("labelAfterPick") or "").startswith("从（开始日期）：2026年11月2日"), str(h.get("labelAfterPick")))
        else:
            chk(f"history/{vp} HEAD 原生框在 Tab 序列（正控）", h.get("dateInputFocused") is True, str(h.get("dateInputFocused")))
            chk(f"history/{vp} HEAD 没有 chip 按钮（正控）", not h.get("chipButtons"), str(h.get("chipButtons")))
        pa = h.get("pointerActive") or {}
        chk(f"history/{vp} 指针点 chip 由原生框接到", pa.get("tag") == "INPUT" and pa.get("type") == "date" and h.get("spAfterPointer", 0) >= 1, f"{pa} sp={h.get('spAfterPointer')}")
    for theme, fallback in (("day", "rgba(31, 41, 38, 0.18)"), ("night", "rgba(0, 0, 0, 0.45)")):
        r = runs.get(f"backdrop-{theme}", {})
        chk(f"backdrop/{theme} 主题生效", r.get("dark") is (theme == "night"), str(r.get("dark")))
        res_ = r.get("resolved", {}); unres = r.get("unresolvable", {})
        if cand:
            chk(f"backdrop/{theme} scrim-dialog 正常解析", res_.get("scrim-dialog") == fallback, str(res_.get("scrim-dialog")))
            chk(f"backdrop/{theme} scrim-dialog 变量失效仍是兜底色", unres.get("scrim-dialog") == fallback, str(unres.get("scrim-dialog")))
            # 候选里这个任意值类已不再被编译，合成的 dialog 只剩 Chromium 自带的 ::backdrop 默认色 rgba(0,0,0,.1)——不是遮罩色即可。
            chk(f"backdrop/{theme} 旧的任意值类已不存在（只剩浏览器默认遮罩）", unres.get("m-auto backdrop:bg-[color:var(--scrim)]") == "rgba(0, 0, 0, 0.1)" and res_.get("m-auto backdrop:bg-[color:var(--scrim)]") == "rgba(0, 0, 0, 0.1)", str(res_.get("m-auto backdrop:bg-[color:var(--scrim)]")))
        else:
            chk(f"backdrop/{theme} HEAD 任意值类正常解析（正控）", res_.get("m-auto backdrop:bg-[color:var(--scrim)]") == fallback, str(res_.get("m-auto backdrop:bg-[color:var(--scrim)]")))
            chk(f"backdrop/{theme} HEAD 任意值类变量失效即透明（正控）", unres.get("m-auto backdrop:bg-[color:var(--scrim)]") == "rgba(0, 0, 0, 0)", str(unres.get("m-auto backdrop:bg-[color:var(--scrim)]")))
            chk(f"backdrop/{theme} HEAD confirm-dialog 有兜底", unres.get("confirm-dialog") == fallback, str(unres.get("confirm-dialog")))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--db", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--tag", choices=["head", "cand"], required=True)
    ap.add_argument("--judge-only", action="store_true", help="只按已有的 measure-<tag>.json 重新打分")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    json_path = os.path.join(a.out, f"measure-{a.tag}.json")
    if a.judge_only:
        with open(json_path, encoding="utf-8") as fh:
            report = json.load(fh)
    else:
        report = {"base": a.base, "tag": a.tag, "runs": []}
        with sync_playwright() as p:
            composer_states(p, a.base, a.db, report)
            history_keyboard(p, a.base, report)
            backdrops(p, a.base, report)
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    res = judge(report, a.tag)
    fails = 0
    lines = []
    for name, ok, detail in res:
        fails += 0 if ok else 1
        lines.append(f"{'PASS' if ok else 'FAIL'} {name}  {detail}")
    lines.append(f"== FAIL {fails} / {len(res)}")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(a.out, f"judge-{a.tag}.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
