"""聊天建书真实走查（规格 §5.8）：隔离环境 3099 前端 + 8098 后端 + 临时库。

用法：uv run --no-project --with playwright==1.63.0 python walk_ccn.py --base http://127.0.0.1:3099 --db <临时库> --draft <id> --title <标题> --seed <思路> --out <目录>
前置：seed_ccn.py 已造好草稿与卡片消息。步骤：登录 → 聊天出卡 → 去书斋建书 → 抽屉 + iframe 路径 → 向导预填 → 三步提交建书 → 库里草稿已消费 → 刷新卡片变已建书 → 打开 → iframe 路径。
"""
import argparse
import json
import os
import re
import sqlite3
import time

from playwright.sync_api import sync_playwright

UUID = r"[0-9a-f-]{36}"
results = []


def chk(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:300]))
    print(f"{'PASS' if ok else 'FAIL'} {name}  {str(detail)[:200]}")


def login(page, base, user="tester"):
    page.goto(base + "/login", wait_until="networkidle")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(re.compile(r"/(\?.*)?$"), timeout=30000)
    page.wait_for_timeout(1500)


def db_draft(db, draft_id):
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT novel_id FROM novel_drafts WHERE id=?", (draft_id,)).fetchone()
        novels = con.execute("SELECT COUNT(*) FROM novels WHERE username='tester'").fetchone()[0]
        return (row[0] if row else "MISSING"), novels
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--db", required=True); ap.add_argument("--draft", required=True)
    ap.add_argument("--title", required=True); ap.add_argument("--seed", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page = ctx.new_page()
        login(page, a.base)
        page.add_style_tag(content="nextjs-portal{display:none!important}")
        # 1. 聊天里的草稿卡
        card_title = page.get_by_text(f"书斋草稿 · 《{a.title}》")
        card_title.first.wait_for(timeout=20000)
        chk("聊天里有书斋草稿卡（标题）", card_title.count() >= 1, card_title.count())
        go = page.get_by_role("button", name="去书斋建书")
        chk("卡片有「去书斋建书」按钮", go.count() == 1, go.count())
        excerpt_ok = page.get_by_text(a.seed[:20]).count() >= 1
        chk("卡片显示思路前 80 字摘录", excerpt_ok)
        page.screenshot(path=os.path.join(a.out, "01-card.png"))
        # 2. 点按钮：抽屉打开 + iframe 路径
        drawer = page.locator("#novel-drawer")
        chk("点击前书斋抽屉是隐藏的", drawer.get_attribute("aria-hidden") == "true", drawer.get_attribute("aria-hidden"))
        go.click()
        page.wait_for_timeout(800)
        chk("点击后书斋抽屉打开", drawer.get_attribute("aria-hidden") == "false", drawer.get_attribute("aria-hidden"))
        frame_el = page.locator('#novel-drawer iframe[title="书斋工作区"]')
        src = frame_el.get_attribute("src")
        chk("iframe 路径为 /novels/new?embed=1&draft=<id>", src == f"/novels/new?embed=1&draft={a.draft}", src)
        # 3. 向导预填
        frame = page.frame_locator('#novel-drawer iframe[title="书斋工作区"]')
        seed_box = frame.locator("#novel-seed")
        seed_box.wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        chk("向导第一步已预填故事思路", seed_box.input_value() == a.seed, seed_box.input_value()[:60])
        vals = {}
        for label, want in (("最少章数", "40"), ("最多章数", "60"), ("每章字数", "2500")):
            try:
                v = frame.get_by_label(re.compile(label)).first.input_value(timeout=3000)
            except Exception as exc:
                v = f"ERR {type(exc).__name__}"
            vals[label] = v
            chk(f"向导预填 {label} = {want}", v == want, v)
        page.screenshot(path=os.path.join(a.out, "02-wizard-prefilled.png"))
        # 4. 三步提交建书（开发模式、占位 Key：建书会立刻发起 setup，模型调用失败后书会暂停，这里只看草稿消费与卡片状态）
        submit = frame.locator('form button[type="submit"]')
        for step in range(2):
            submit.click(); page.wait_for_timeout(1200)
        page.wait_for_timeout(2500)  # 等估算
        before_novel_id, before_count = db_draft(a.db, a.draft)
        chk("提交前草稿未消费", before_novel_id is None, before_novel_id)
        submit.click()
        deadline = time.time() + 30
        novel_id = None
        while time.time() < deadline:
            novel_id, count = db_draft(a.db, a.draft)
            if novel_id not in (None, "MISSING"):
                break
            page.wait_for_timeout(500)
        chk("建书后草稿 novel_id 已填（同一事务消费）", bool(novel_id) and novel_id != "MISSING", novel_id)
        chk("建书后 novels 多了 1 行", db_draft(a.db, a.draft)[1] == before_count + 1, db_draft(a.db, a.draft)[1])
        page.wait_for_timeout(1500)
        src_after = frame_el.get_attribute("src")
        wiz_url = None
        try:
            wiz_url = page.frames[-1].url
        except Exception:
            pass
        chk("向导建书后跳到工作台（iframe 内 URL 含 /novels/<id>）", bool(wiz_url) and re.search(rf"/novels/{UUID}", wiz_url or "") is not None, wiz_url)
        page.screenshot(path=os.path.join(a.out, "03-after-create.png"))
        # 5. 刷新：卡片变已建书，按钮「打开」
        page.reload(wait_until="domcontentloaded"); page.wait_for_timeout(3000)
        page.add_style_tag(content="nextjs-portal{display:none!important}")
        done_title = page.get_by_text(f"已建书《{a.title}》")
        done_title.first.wait_for(timeout=20000)
        chk("刷新后卡片仍在且变为已建书", done_title.count() >= 1, done_title.count())
        done_card = done_title.first.locator("xpath=ancestor::div[contains(@class, 'ceramic-card')][1]")
        open_btn = done_card.get_by_role("button", name="打开")
        chk("已建书卡片有「打开」按钮", open_btn.count() >= 1, open_btn.count())
        chk("刷新后不再显示「去书斋建书」", page.get_by_role("button", name="去书斋建书").count() == 0)
        open_btn.first.click(); page.wait_for_timeout(800)
        src2 = page.locator('#novel-drawer iframe[title="书斋工作区"]').get_attribute("src")
        chk("「打开」后 iframe 路径为 /novels/<id>?embed=1", src2 == f"/novels/{novel_id}?embed=1", src2)
        chk("抽屉再次打开", page.locator("#novel-drawer").get_attribute("aria-hidden") == "false")
        page.screenshot(path=os.path.join(a.out, "04-done-card.png"))
        # 6. 手机视口：卡片不溢出
        m = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mp = m.new_page(); login(mp, a.base); mp.add_style_tag(content="nextjs-portal{display:none!important}")
        mp.wait_for_timeout(2000)
        mp.get_by_text(f"已建书《{a.title}》").first.wait_for(timeout=20000)
        over = mp.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        chk("手机 390 宽无横向溢出", over <= 0, over)
        mp.screenshot(path=os.path.join(a.out, "05-mobile-card.png"))
        browser.close()
    fails = sum(1 for _, ok, _ in results if not ok)
    with open(os.path.join(a.out, "walk.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    print(f"== FAIL {fails} / {len(results)}")
    raise SystemExit(fails)


if __name__ == "__main__":
    main()
