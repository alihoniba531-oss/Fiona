"""修改意见卡 · 真实界面走查（隔离环境：3063 前端 + 8063 后端 + 临时库，先跑 seed_feedback.py）。

用法：uv run --no-project --with playwright==1.63.0 python walk_feedback.py --base http://127.0.0.1:3063 --seed <seed.json> --out <截图目录>
免费操作：交留言、确认框取消、重新定稿（DEV_MODE 下不扣草莓；主编是 byok:self 且没配 Key，后台会立即暂停，不访问外网）。
"""
import argparse
import json
import os
import re

from playwright.sync_api import sync_playwright

results = []
console_errors = []
bad_responses = []


def chk(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:300]))
    print(f"{'PASS' if ok else 'FAIL'} {name}  {str(detail)[:220]}", flush=True)


def login(page, base, user="tester"):
    page.goto(base + "/login", wait_until="domcontentloaded")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(re.compile(r"/(\?.*)?$"), timeout=30000)
    page.wait_for_timeout(3000)
    page.add_style_tag(content="nextjs-portal{display:none!important}")


def card(page, marker):
    return page.locator(".ceramic-card").filter(has_text=marker).first


def text_of(locator):
    return re.sub(r"\s+", " ", locator.inner_text()).strip()


def sse(events):
    return "".join("data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events)


MAX_WEIGHT = """(el) => Math.max(...[el, ...el.querySelectorAll('*')].map(n => parseInt(getComputedStyle(n).fontWeight, 10) || 400))"""

FEE = {
    "own_model": "这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。",
    "free": "这次重新定稿不扣草莓。",
    "strawberries": "重新定稿会再调用一次编辑部，按实际用量扣草莓。",
}


def set_config(db_path, novel_id, **changes):
    """模拟作者在书斋里改了主编模型或确认方式：直接改隔离临时库里这本书的 config_json。"""
    import sqlite3
    con = sqlite3.connect(db_path, timeout=10)
    try:
        cfg = json.loads(con.execute("SELECT config_json FROM novels WHERE id=?", (novel_id,)).fetchone()[0])
        for key, value in changes.items():
            if key == "editor":
                cfg.setdefault("agents", {})["editor"] = value
            else:
                cfg[key] = value
        con.execute("UPDATE novels SET config_json=? WHERE id=?", (json.dumps(cfg, ensure_ascii=False), novel_id))
        con.commit()
    finally:
        con.close()


def dialog_open(page):
    d = page.get_by_role("alertdialog")
    return d.count() > 0 and d.first.is_visible()


def check_r1_recheck(page, a, seed, posts, gets):
    """R1（规格 v1.4）：点「带着这些要求重新定稿」先重新读取，按最新费用弹框；已经不能用就只更新卡片。"""
    book_a, fa_id = seed["books"]["A"], seed["FA"]
    fa = card(page, "以后要求甲")
    # 1) 作者在书斋把主编从「我的模型」换成平台模型，卡片不刷新，直接点旧卡
    set_config(a.db, book_a, editor="dashscope:qwen3.8-max")
    api_cost = page.evaluate(f"fetch('/api/novels/feedback/{fa_id}').then(r => r.json()).then(j => j.book.redo_cost)")
    chk("R1 准备：后端视图的费用已不是自带模型", api_cost in ("free", "strawberries"), api_cost)
    page.wait_for_timeout(300)
    before = len(gets)
    fa.get_by_role("button", name="带着这些要求重新定稿").click()
    opened = True
    try:
        page.get_by_role("alertdialog").wait_for(timeout=8000)
    except Exception:
        opened = False
    dt = text_of(page.get_by_role("alertdialog")) if opened else ""
    chk("R1 换主编后点击：先重新读取了一次", len(gets) - before == 1, len(gets) - before)
    chk("R1 确认框按最新费用说明", opened and FEE.get(api_cost, "?") in dt and FEE["own_model"] not in dt, dt[:200])
    tf = text_of(fa)
    chk("R1 卡片说明里的费用句也换成最新的", FEE.get(api_cost, "?") in tf and FEE["own_model"] not in tf, tf[:300])
    page.screenshot(path=os.path.join(a.out, "02a-1440-confirm-fresh-fee.png"))
    if opened:
        page.get_by_role("alertdialog").get_by_role("button", name="取消").click()
        page.wait_for_timeout(800)
    chk("R1 取消后不发重新定稿请求", not any(u.endswith("/redo") for u in posts), posts)
    set_config(a.db, book_a, editor="byok:self")
    # 2) 作者在书斋把确认方式改成每批确认：这一项已经不能用，点击后只更新卡片、不弹框
    set_config(a.db, book_a, automation="per_batch")
    page.wait_for_timeout(300)
    before = len(gets)
    fa.get_by_role("button", name="带着这些要求重新定稿").click()
    page.wait_for_timeout(2500)
    chk("R1 改确认方式后点击：先重新读取了一次", len(gets) - before == 1, len(gets) - before)
    shown = dialog_open(page)
    chk("R1 已经不能用时不弹确认框", not shown)
    t = text_of(fa)
    chk("R1 卡片按新状态显示（不是逐章确认）、按钮消失",
        "这本书现在不是逐章确认，重新定稿后会直接开始写正文、不会停下来等你确认；这一项请到书斋里处理。" in t
        and fa.get_by_role("button", name="带着这些要求重新定稿").count() == 0, t[:300])
    page.screenshot(path=os.path.join(a.out, "02b-1440-not-actionable.png"))
    if shown:
        page.get_by_role("alertdialog").get_by_role("button", name="取消").click()
        page.wait_for_timeout(800)
    chk("R1 已经不能用时不发重新定稿请求", not any(u.endswith("/redo") for u in posts), posts)
    set_config(a.db, book_a, automation="per_chapter")


def wait_cards(page, markers, timeout=30000):
    for marker in markers:
        page.locator(".ceramic-card").filter(has_text=marker).first.wait_for(timeout=timeout)


def check_static(page, label):
    a = card(page, "以后要求甲")
    t = text_of(a)
    chk(f"[{label}] FA 标题", "修改意见 · 《春山》" in t, t[:80])
    chk(f"[{label}] FA 细纲节：第 3 章细纲 + 自带模型费用句", "第 3 章细纲" in t and "这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。" in t, t[:400])
    chk(f"[{label}] FA 细纲节：看不到现在这一版 + 改完批准", "它看不到你现在看到的这一版" in t and "再点「改完批准」" in t)
    chk(f"[{label}] FA 两个按钮", a.get_by_role("button", name="带着这些要求重新定稿").count() == 1 and a.get_by_role("button", name="去书斋改细纲").count() == 1)
    chk(f"[{label}] FA 以后章节：待下发数 + 第 4 章 + 不能撤回",
        "这本书现在有 2 条待下发留言" in t and "第 3 章细纲已经出来了，这条要求要到第 4 章规划细纲时编辑部才会读到" in t and "交出后不能撤回。" in t, t[-400:])
    chk(f"[{label}] FA 已写章节两条 + 后果", "第 1 章 渡口：问题甲一" in t and "第 2 章 北岸脚步：问题甲二" in t and "永久标成「待复核」" in t)
    chk(f"[{label}] FA 底部提示（第一节可用）只有前半句", "要回到书架重新打开它" in t and "在旧页面上点「批准（原样）」" not in t)
    b = card(page, "以后要求乙")
    tb = text_of(b)
    chk(f"[{label}] FB 已被第 3 章细纲读到 + 采纳", "待下发" in tb and "编辑部已经在第 3 章细纲里读到这条要求；这一章写完后，这里会记为已下发。" in tb and "编辑部采纳：第三章里船家改说本地话。" in tb, tb)
    chk(f"[{label}] FB 不再有交给编辑部按钮、不推算第 4 章", b.get_by_role("button", name="交给编辑部").count() == 0 and "第 4 章" not in tb)
    c = card(page, "以后要求丙")
    tc = text_of(c)
    chk(f"[{label}] FC 最后一章", "第 5 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。" in tc and "第 6 章" not in tc, tc)
    d = card(page, "问题丁")
    td = text_of(d)
    chk(f"[{label}] FD 只有已写章节一节", "修改意见 · 《旧梦》" in td and "已写好的章节" in td and "以后的章节" not in td and not re.search(r"第 \d+ 章细纲", td), td[:200])
    e = card(page, "细纲要求戊")
    te = text_of(e)
    chk(f"[{label}] FE 已发起重新定稿、暂停未完成", "已发起重新定稿" in te and "重新定稿还没有完成：这本书暂停了，请到书斋查看原因；恢复写作后会接着重新定稿。" in te, te)
    chk(f"[{label}] FE 底部提示含旧页面后半句", "在旧页面上点「批准（原样）」会直接批准你还没看过的新细纲" in te)
    weights = [loc.evaluate(MAX_WEIGHT) for loc in (a, b, c, d, e)]
    chk(f"[{label}] 卡片内没有粗体（最大字重 ≤ 500）", max(weights) <= 500, weights)
    widths = [loc.bounding_box()["width"] for loc in (a, b, c, d, e)]
    chk(f"[{label}] 卡片宽度 ≤ 420", max(widths) <= 420.5, widths)
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    chk(f"[{label}] 页面没有横向溢出", overflow <= 0, overflow)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", required=True, help="隔离临时库（walk-env.sh 里的 FIONA_DB_PATH）")
    ap.add_argument("--r1-only", action="store_true", help="只跑静态检查与 R1 重读检查（正控用）")
    a = ap.parse_args()
    seed = json.load(open(a.seed, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        posts = []
        page.on("response", lambda r: bad_responses.append((r.status, r.url)) if r.status >= 400 else None)
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/novels/feedback/" in r.url else None)
        gets = []
        page.on("request", lambda r: gets.append(r.url) if r.method == "GET" and r.url.endswith("/novels/feedback/" + seed["FA"]) else None)
        login(page, a.base)
        wait_cards(page, ["以后要求甲", "以后要求乙", "以后要求丙", "问题丁", "细纲要求戊"])
        page.wait_for_timeout(1500)
        check_static(page, "1440")
        card(page, "以后要求甲").scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(a.out, "01-1440-fa.png"))

        check_r1_recheck(page, a, seed, posts, gets)
        if a.r1_only:
            ctx.close()
            browser.close()
            passed = sum(1 for _, ok, _ in results if ok)
            print(f"TOTAL {passed}/{len(results)} passed")
            json.dump(results, open(os.path.join(a.out, "walk.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return
        # 恢复后刷新，卡片回到可重新定稿
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.add_style_tag(content="nextjs-portal{display:none!important}")
        wait_cards(page, ["以后要求甲"])
        page.wait_for_timeout(1500)
        chk("R1 恢复后刷新：又能重新定稿、费用回到自带模型", card(page, "以后要求甲").get_by_role("button", name="带着这些要求重新定稿").count() == 1
            and FEE["own_model"] in text_of(card(page, "以后要求甲")))

        # 确认框：取消不发请求
        fa = card(page, "以后要求甲")
        fa.get_by_role("button", name="带着这些要求重新定稿").click()
        dialog = page.get_by_role("alertdialog")
        dialog.wait_for(timeout=10000)
        dt = text_of(dialog)
        chk("确认框标题与正文（自带模型）", "重新定稿第 3 章细纲" in dt and "这本书的主编用的是你自己的模型，重新定稿不扣草莓" in dt and "完成后新细纲仍会停下来等你确认。" in dt, dt)
        chk("确认框按钮名「重新定稿」", dialog.get_by_role("button", name="重新定稿", exact=True).count() == 1)
        chk("确认框询问期间卡片按钮文字不变", fa.get_by_role("button", name="带着这些要求重新定稿").count() == 1)
        page.screenshot(path=os.path.join(a.out, "02-1440-confirm.png"))
        dialog.get_by_role("button", name="取消").click()
        page.wait_for_timeout(1200)
        chk("取消后不发重新定稿请求", not any(u.endswith("/redo") for u in posts), posts)
        chk("取消后按钮恢复可用", fa.get_by_role("button", name="带着这些要求重新定稿").is_enabled())

        # 交给编辑部
        fa.get_by_role("button", name="交给编辑部").click()
        page.wait_for_timeout(2500)
        t = text_of(card(page, "以后要求甲"))
        chk("交出后：发了一次 /note", sum(u.endswith("/note") for u in posts) == 1, posts)
        chk("交出后：待下发 + 第 4 章规划细纲时读到", "待下发" in t and "第 4 章规划细纲时，编辑部会读到这条要求。" in t, t[-300:])
        chk("交出后：交给编辑部按钮消失", card(page, "以后要求甲").get_by_role("button", name="交给编辑部").count() == 0)

        # 重新定稿：确认后发起
        card(page, "以后要求甲").get_by_role("button", name="带着这些要求重新定稿").click()
        dialog = page.get_by_role("alertdialog")
        dialog.wait_for(timeout=10000)
        dialog.get_by_role("button", name="重新定稿", exact=True).click()
        page.wait_for_timeout(3000)
        t = text_of(card(page, "以后要求甲"))
        chk("发起后：发了一次 /redo", sum(u.endswith("/redo") for u in posts) == 1, posts)
        chk("发起后：已发起重新定稿", "已发起重新定稿" in t, t[:400])
        chk("发起后：底部提示含旧页面后半句", "在旧页面上点「批准（原样）」会直接批准你还没看过的新细纲" in t)
        page.screenshot(path=os.path.join(a.out, "03-1440-after-actions.png"))

        # 刷新后状态仍在（按 novel_feedback_id 重建）
        page.wait_for_timeout(4000)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.add_style_tag(content="nextjs-portal{display:none!important}")
        wait_cards(page, ["以后要求甲"])
        page.wait_for_timeout(1500)
        t = text_of(card(page, "以后要求甲"))
        states = ["编辑部正在带着这些要求重新定稿第 3 章细纲", "重新定稿还没有完成：这本书暂停了", "重新定稿没有完成：这本书处于失败状态", "已经带着这些要求重新定稿过第 3 章细纲。"]
        chk("刷新后：仍是已发起重新定稿，且说明是规格里的四种进展之一", "已发起重新定稿" in t and sum(s in t for s in states) == 1, [s for s in states if s in t] or t[:300])
        chk("刷新后：留言仍是待下发", "待下发" in t)
        card(page, "以后要求甲").scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(a.out, "04-1440-after-reload.png"))

        # 在书斋打开
        fd = card(page, "问题丁")
        fd.get_by_role("button", name="在书斋打开").click()
        page.wait_for_timeout(2500)
        srcs = page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.getAttribute('src'))")
        chk("在书斋打开：抽屉 iframe 指向这本书", any(s and f"/novels/{seed['books']['C']}?embed=1" in s for s in srcs), srcs)
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)

        # 流式注入：卡片经 SSE 到达
        page.route("**/api/chat", lambda route: route.fulfill(status=200, headers={"Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache"},
                   body=sse([{"card": {"type": "card", "subtype": "novel_feedback", "source": "书斋", "points": ["修改意见《春山》", "交给编辑部、重新定稿都要作者在卡片上点按钮"],
                                       "feedback_id": seed["FF"], "error": False}, "append": True}, {"done": True}])))
        page.locator("textarea").first.fill("把意见做成卡")
        page.keyboard.press("Enter")
        try:
            card(page, "以后要求己").wait_for(timeout=15000)
            ok = True
        except Exception:
            ok = False
        chk("流式到达的修改意见卡渲染出来", ok and "修改意见 · 《春山》" in text_of(card(page, "以后要求己")))
        page.unroute("**/api/chat")
        if ok:
            card(page, "以后要求己").scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(a.out, "05-1440-streamed.png"))

        # 1280
        page.set_viewport_size({"width": 1280, "height": 860})
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.add_style_tag(content="nextjs-portal{display:none!important}")
        wait_cards(page, ["以后要求乙"])
        page.wait_for_timeout(1500)
        b = card(page, "以后要求乙")
        chk("[1280] FB 正常显示", "编辑部已经在第 3 章细纲里读到这条要求" in text_of(b))
        chk("[1280] 页面没有横向溢出", page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
        b.scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(a.out, "06-1280-fb.png"))
        ctx.close()

        # 390 手机
        mctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        m = mctx.new_page()
        m.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        m.on("response", lambda r: bad_responses.append((r.status, r.url)) if r.status >= 400 else None)
        login(m, a.base)
        wait_cards(m, ["以后要求丙", "问题丁"])
        m.wait_for_timeout(1500)
        for marker in ("以后要求甲", "以后要求丙", "问题丁"):
            box = card(m, marker).bounding_box()
            chk(f"[390] 卡片「{marker}」不超出屏幕", box["x"] >= 0 and box["x"] + box["width"] <= 390.5, box)
        chk("[390] 页面没有横向溢出（scrollWidth ≤ clientWidth）", m.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
        card(m, "以后要求丙").scroll_into_view_if_needed()
        m.screenshot(path=os.path.join(a.out, "07-390-fc.png"))
        card(m, "以后要求甲").scroll_into_view_if_needed()
        m.screenshot(path=os.path.join(a.out, "08-390-fa.png"))
        mctx.close()
        browser.close()

    unrelated = [(s, u) for s, u in bad_responses if s == 429 and "/hot/" in u]
    related = [(s, u) for s, u in bad_responses if (s, u) not in unrelated]
    chk("没有失败的请求（首页热榜限流除外，已单独记录）", not related, {"related": related[:3], "unrelated_hot_429": len(unrelated)})
    relevant = [e for e in console_errors if "favicon" not in e and "Failed to load resource" not in e]
    chk("控制台没有脚本报错（资源加载失败由上一项按地址判断）", not relevant, relevant[:3])
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"TOTAL {passed}/{len(results)} passed")
    json.dump(results, open(os.path.join(a.out, "walk.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
