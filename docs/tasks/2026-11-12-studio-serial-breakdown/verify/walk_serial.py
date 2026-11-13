"""工作室续拆 · 真实界面走查（隔离环境：3064 前端 + 8064 后端 + 临时库 + 本地假导演模型）。

用法：uv run --no-project --with playwright==1.63.0 python walk_serial.py --base http://127.0.0.1:3064 --extend-cmd "<造数 --extend 命令>" --out <截图目录>
全程免费：导演模型是 walk_server.py 里的本地假模型，DEV_MODE 下不扣草莓。
"""
import argparse
import json
import re
import subprocess

from playwright.sync_api import sync_playwright

BOOK = "55555555-5555-4555-8555-555555555555"
results, console_errors, bad_responses = [], [], []


def chk(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:300]))
    print(f"{'PASS' if ok else 'FAIL'} {name}  {str(detail)[:220]}", flush=True)


def login(page, base):
    page.goto(base + "/login", wait_until="domcontentloaded")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill("tester")
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(re.compile(r"/(\?.*)?$"), timeout=30000)
    page.wait_for_timeout(2000)


def hide_overlay(page):
    page.add_style_tag(content="nextjs-portal{display:none!important}")


def body_text(page):
    return page.locator("body").inner_text()


def wait_text(page, text, timeout=60000):
    try:
        page.get_by_text(text, exact=False).first.wait_for(timeout=timeout)
        return True
    except Exception:
        return False


def api(page, base, path, method="GET", data=None):
    if method == "GET":
        response = page.request.get(base + "/api" + path)
    else:
        response = page.request.post(base + "/api" + path, data=json.dumps(data or {}), headers={"Content-Type": "application/json"})
    return response.status, (response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text())


def open_breakdown(page):
    page.get_by_role("tab", name="①拆解").first.click()
    page.wait_for_timeout(1500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--extend-cmd", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    base, out = args.base, args.out
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("response", lambda r: bad_responses.append(f"{r.status} {r.url}") if r.status >= 500 else None)
        login(page, base)

        # A. 连载中的书在书斋里就能做成片
        page.goto(f"{base}/novels/{BOOK}", wait_until="domcontentloaded"); hide_overlay(page)
        film = page.get_by_role("button", name="做成片")
        chk("A1 连载书工作台出现「做成片」", wait_text(page, "做成片") and film.count() >= 1, film.count())
        film.first.click(); page.wait_for_timeout(1500)
        chk("A2 做成片对话框显示连载提示", wait_text(page, "连载中，只收已写好的 5 章。", 10000))
        page.screenshot(path=f"{out}/a2-film-dialog.png")
        page.get_by_role("button", name="创建项目").click()
        page.wait_for_url(re.compile(r"/studio/[^/?]+"), timeout=30000); hide_overlay(page)
        pid = re.search(r"/studio/([^/?]+)", page.url).group(1)
        chk("A3 建好项目并进入工作室", bool(pid), pid)
        chk("A4 来源面板显示连载提示", wait_text(page, "作品还在写，同步只收已写好的章节。", 20000))
        open_breakdown(page)
        page.get_by_role("button", name="报价").first.click()
        chk("A5 整本报价对话框", wait_text(page, "确认拆解报价", 20000))
        page.get_by_role("button", name="确认开始").click()
        chk("A6 首次拆解完成", wait_text(page, "拆解完成", 90000))
        status, plan = api(page, base, f"/studio/projects/{pid}/episodes")
        chk("A7 首次分集方案已发布", status == 200 and len(plan.get("episodes", [])) >= 2, (status, len(plan.get("episodes", []))))
        first_count = len(plan["episodes"])
        status, edited = api(page, base, f"/studio/projects/{pid}/episodes/ops", "POST",
                             {"op": "edit", "no": 1, "fields": {"title": "渡口（作者改）"}, "expected_revision": plan["plan_revision"]})
        chk("A8 作者改第 1 集标题", status == 200, status)
        page.reload(wait_until="domcontentloaded"); hide_overlay(page); open_breakdown(page)
        page.get_by_role("button", name="批准分集方案").click()
        page.get_by_role("button", name="确认批准").click()
        chk("A9 G0 已批准", wait_text(page, "G0 已批准", 20000))
        status, bible = api(page, base, f"/studio/projects/{pid}/bible")
        rows = bible if isinstance(bible, list) else bible.get("entries", bible.get("items", []))
        he = [row for row in rows if row.get("name") == "阿禾"]
        chk("A10 总表里有补全批识别出的阿禾（无 ref_id）", len(he) == 1 and not he[0].get("ref_id"), he)
        he_id = he[0]["id"] if he else None

        # B. 作者接着写到第 12 章，回来同步、续拆
        ran = subprocess.run(args.extend_cmd, shell=True, capture_output=True, text=True)
        chk("B0 造数：写到第 12 章", ran.returncode == 0, ran.stdout.strip()[-200:] or ran.stderr[-200:])
        page.reload(wait_until="domcontentloaded"); hide_overlay(page)
        chk("B1 来源面板提示改动与待复核", wait_text(page, "第 4 章待复核", 30000), body_text(page)[:0])
        page.get_by_role("button", name="同步").first.click(); page.wait_for_timeout(800)
        sync_buttons = page.get_by_role("button", name="同步")
        if sync_buttons.count() > 1:
            sync_buttons.last.click()
        chk("B2 同步后来源面板标出快照中的待复核章", wait_text(page, "快照中第 4 章待复核。", 30000))
        open_breakdown(page)
        chk("B3 续拆块", wait_text(page, "已拆到第 5 章；作品已同步到第 12 章，可以续拆第 6–12 章。", 30000))
        chk("B4 改过的旧章提醒", wait_text(page, "第 3 章在拆解之后改过", 5000))
        quote_btn = page.get_by_role("button", name="重新报价拆解")
        chk("B4b 可续拆时整本报价按钮为浅色", quote_btn.count() == 1 and "btn-quiet" in (quote_btn.first.get_attribute("class") or "")
            and "btn-primary" not in (quote_btn.first.get_attribute("class") or ""), quote_btn.first.get_attribute("class") if quote_btn.count() else None)
        chk("B4c 改过旧章句只出现一次", body_text(page).count("在拆解之后改过") == 1, body_text(page).count("在拆解之后改过"))
        page.screenshot(path=f"{out}/b4-continue-block.png", full_page=True)
        page.get_by_role("button", name="续拆第 6–12 章").click()
        chk("B5 续拆报价对话框", wait_text(page, "续拆报价", 20000))
        dialog = page.locator("dialog[open]").last
        text = dialog.inner_text()
        chk("B6 对话框三句齐全", all(s in text for s in ("只拆第 6–12 章。", "新增的集会追加到分集方案末尾，方案会退回待批准。", "确认后不能取消；有批次失败时可以单批重跑。")), text[:200])
        chk("B7 对话框没有整本专用提示", "每集目标时长将保存为" not in text and "上一次拆解未执行的批次" not in text, text[:200])
        page.screenshot(path=f"{out}/b7-continue-quote.png")
        page.get_by_role("button", name="确认续拆").click()
        chk("B8 续拆已开始", wait_text(page, "续拆已开始。", 20000))
        chk("B9 进行中：不能取消的说明", wait_text(page, "续拆进行中不能取消，失败的批次可以单批重跑。", 10000))
        chk("B10 进行中：没有「取消拆解」按钮", page.get_by_role("button", name="取消拆解").count() == 0)
        chk("B11 进行中：分集页说追加而非重新生成", wait_text(page, "续拆进行中，完成后新增的集会追加到方案末尾", 10000)
            and "按新结果重新生成" not in body_text(page))
        chk("B12 进行中：正在续拆行", wait_text(page, "正在续拆第 6–12 章。", 5000))
        chk("B13 进行中：旧 G0 仍有效", "G0 已批准" in body_text(page))
        status, mid = api(page, base, f"/studio/projects/{pid}/episodes")
        chk("B14 进行中：未纳入单元不含新章", status == 200 and all(item["unit_to"] <= max(e["unit_to"] for e in mid["episodes"]) for item in mid.get("unassigned", [])), mid.get("unassigned"))
        page.screenshot(path=f"{out}/b14-running.png", full_page=True)
        chk("B15 续拆完成", wait_text(page, "已续拆 1 次，拆到第 12 章。", 120000))
        page.wait_for_timeout(2500)
        status, plan2 = api(page, base, f"/studio/projects/{pid}/episodes")
        episodes = plan2.get("episodes", [])
        qb = page.get_by_role("button", name="重新报价拆解")
        chk("B15b 续拆完成后（不可续拆）整本报价按钮恢复主按钮", qb.count() == 1 and "btn-primary" in (qb.first.get_attribute("class") or ""), qb.first.get_attribute("class") if qb.count() else None)
        chk("B16 方案 = 原有集 + 新集，作者改的标题保留", len(episodes) > first_count and episodes[0]["title"] == "渡口（作者改）", [e["title"] for e in episodes])
        chk("B17 方案退回待批准，appended_from = 原集数+1", plan2.get("g0_approved") is False and plan2.get("appended_from") == first_count + 1, (plan2.get("g0_approved"), plan2.get("appended_from")))
        text = body_text(page)
        chk("B18 分集页提示新增的集", f"第 {first_count + 1}–{len(episodes)} 集是这次续拆新增的" in text or f"第 {first_count + 1} 集是这次续拆新增的" in text, "")
        tags = page.locator('[data-testid="episode-table"] span.tag', has_text="新增")
        chk("B19 表格里「新增」标签数 = 新集数", tags.count() == len(episodes) - first_count, (tags.count(), len(episodes) - first_count))
        page.screenshot(path=f"{out}/b19-plan-desktop.png", full_page=True)
        status, bible2 = api(page, base, f"/studio/projects/{pid}/bible")
        rows2 = bible2 if isinstance(bible2, list) else bible2.get("entries", bible2.get("items", []))
        he2 = [row for row in rows2 if row.get("name") == "阿禾"]
        chk("B20 阿禾仍是原条目，补上 ref_id=C2，只有一条", len(he2) == 1 and he2[0]["id"] == he_id and he2[0].get("ref_id") == "C2", he2)
        status, current = api(page, base, f"/studio/projects/{pid}/breakdown")
        chk("B21 视图字段", current.get("covered_through") == 12 and current.get("changed_covered") == [3] and current.get("continuable") is False
            and current.get("continuations") and current["continuations"][0]["from"] == 6, {k: current.get(k) for k in ("covered_through", "changed_covered", "stale_chapters", "continuable", "continuations")})

        # C. 手机宽度：卡片里「新增」标签在标题外面
        page.set_viewport_size({"width": 390, "height": 900}); page.wait_for_timeout(1200)
        inside = page.evaluate("() => [...document.querySelectorAll('[data-testid=\"episode-cards\"] h3 .tag')].length")
        outside = page.locator('[data-testid="episode-cards"] span.tag', has_text="新增").count()
        chk("C1 手机卡片：标签不在 h3 里", inside == 0 and outside == len(episodes) - first_count, (inside, outside))
        weights = page.evaluate("() => [...document.querySelectorAll('[data-serial]')].map(el => getComputedStyle(el).fontWeight)")
        chk("C2 新增元素字重都不超过 400", weights and all(int(w) <= 400 for w in weights), weights[:12])
        widths = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        chk("C3 手机无横向溢出", widths[0] <= widths[1], widths)
        page.locator('[data-testid="episode-cards"]').scroll_into_view_if_needed()
        page.screenshot(path=f"{out}/c3-plan-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000}); page.wait_for_timeout(800)

        # D. 重新批准后「新增」消失
        page.get_by_role("button", name="批准分集方案").click()
        page.get_by_role("button", name="确认批准").click()
        chk("D1 重新批准", wait_text(page, "G0 已批准", 20000))
        page.wait_for_timeout(1500)
        status, plan3 = api(page, base, f"/studio/projects/{pid}/episodes")
        chk("D2 批准后 appended_from 清空、标签消失", plan3.get("appended_from") is None and page.locator("span.tag", has_text="新增").count() == 0,
            (plan3.get("appended_from"), page.locator("span.tag", has_text="新增").count()))
        page.screenshot(path=f"{out}/d2-approved.png", full_page=True)

        chk("Z1 控制台无报错", not console_errors, console_errors[:5])
        chk("Z2 没有 5xx 响应", not bad_responses, bad_responses[:5])
        browser.close()
    failed = [r for r in results if not r[1]]
    print(f"TOTAL {len(results)} PASS {len(results) - len(failed)} FAIL {len(failed)}")
    json.dump(results, open(f"{out}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


main()
