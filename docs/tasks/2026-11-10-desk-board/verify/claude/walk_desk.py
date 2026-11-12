"""案头第一期 · 真实界面走查（隔离环境：3061 前端 + 8061 后端 + 临时库，先跑 seed_desk.py）。

用法：uv run --no-project --with playwright==1.63.0 python walk_desk.py --base http://127.0.0.1:3061 --out <截图目录>
只做免费操作：留言、改一集、合并、批准分集方案。**不点任何批准细纲 / 重做 / 继续写作的按钮。**
"""
import argparse
import json
import os
import re

from playwright.sync_api import sync_playwright

A = "11111111-1111-4111-8111-111111111111"
P_NEW = "desk-proj-new"
P_OLD = "desk-proj-old"
results = []
console_errors = []
# 面板底色的 alpha：rgb(...) 记 1，rgba(..., a) 取 a，transparent 记 0
ALPHA = """(() => { const c = getComputedStyle(document.querySelector('#desk-panel')).backgroundColor;
  const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return 0; const parts = m[1].split(/[,\\/ ]+/).filter(Boolean);
  return parts.length >= 4 ? parseFloat(parts[3]) : 1; })()"""


def chk(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:300]))
    print(f"{'PASS' if ok else 'FAIL'} {name}  {str(detail)[:220]}")


def login(page, base, user):
    page.goto(base + "/login", wait_until="domcontentloaded")
    page.get_by_role("button", name="开发测试入口（跳过登录）").click()
    page.get_by_placeholder("测试用户名（默认 tester）").fill(user)
    page.get_by_role("button", name="以测试身份进入").click()
    page.wait_for_url(re.compile(r"/(\?.*)?$"), timeout=30000)
    page.wait_for_timeout(2500)
    page.add_style_tag(content="nextjs-portal{display:none!important}")


def toggle(page):
    return page.locator('button[aria-controls="desk-panel"]:visible')


def open_desk(page):
    if toggle(page).get_attribute("aria-pressed") != "true":
        toggle(page).click()
    page.locator("#desk-panel").wait_for(timeout=20000)
    page.wait_for_timeout(1800)


def close_desk(page):
    if toggle(page).get_attribute("aria-pressed") == "true":
        toggle(page).click()
    page.wait_for_timeout(500)


def box(page, selector):
    return page.locator(selector).first.bounding_box()


def tab(page, name):
    return page.get_by_role("tab", name=name, exact=True).locator("visible=true").first


def shot(page, out, name):
    page.screenshot(path=os.path.join(out, name))


def pick_book(page, title):
    page.locator('select[aria-label="作品"]').select_option(label=title)
    page.wait_for_timeout(1800)


def sse(events):
    return "".join("data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))
        desk_gets = []
        page.on("request", lambda r: desk_gets.append(r.url) if r.method == "GET" and r.frame == page.main_frame and re.search(r"/api/(novels($|[/?])|studio/sources/|studio/projects/[^/]+/episodes)", r.url) else None)
        login(page, a.base, "tester")
        page.wait_for_timeout(1500)
        chk("案头没打开过时，主页面不发任何案头请求", desk_gets == [], desk_gets[:3])

        # ---------- 1440：并排 ----------
        chat = "[data-chat-panel]"
        w_closed = box(page, chat)["width"]
        chk("关闭时不渲染案头面板", page.locator("#desk-panel").count() == 0)
        chk("头部开关初始 aria-pressed=false", toggle(page).get_attribute("aria-pressed") == "false", toggle(page).count())
        open_desk(page)
        chk("打开后开关 aria-pressed=true", toggle(page).get_attribute("aria-pressed") == "true")
        chk("亲手点开：焦点移到案头面板", page.evaluate("document.activeElement && document.activeElement.id") == "desk-panel", page.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)"))
        pb, cb = box(page, "#desk-panel"), box(page, chat)
        chk("1440 并排：聊天列变窄 488±2", abs((w_closed - cb["width"]) - 488) <= 2, (w_closed, cb["width"]))
        chk("1440 并排：面板在聊天列右侧、不重叠", cb["x"] + cb["width"] <= pb["x"] + 1, (cb["x"] + cb["width"], pb["x"]))
        chk("面板宽 448±1", abs(pb["width"] - 448) <= 1, pb["width"])
        chk("并排时上下各留 12px", abs(pb["y"] - 12) <= 1 and abs((pb["y"] + pb["height"]) - 888) <= 1, (pb["y"], pb["height"]))
        pos = page.evaluate("getComputedStyle(document.querySelector('#desk-panel').parentElement).position")
        chk("并排方式在文档流里（非 fixed）", pos != "fixed", pos)
        chk("聊天输入框仍可见可用", page.locator("textarea").first.is_visible())
        tabs = page.get_by_role("tablist", name="创作阶段").get_by_role("tab")
        chk("五个阶段标签", tabs.count() == 5 and tabs.all_inner_texts() == ["立意", "章回", "分集", "分镜", "成片"], tabs.all_inner_texts())
        chk("分镜、成片置灰且提示「后续开放」", all(tab(page, n).is_disabled() and tab(page, n).get_attribute("title") == "后续开放" for n in ("分镜", "成片")))
        chk("阶段文字竖排", page.evaluate("getComputedStyle(document.querySelector('[role=tablist][aria-label=\"创作阶段\"] [role=tab]')).writingMode") == "vertical-rl")
        chk("竖排 tablist 带 aria-orientation=vertical", page.get_by_role("tablist", name="创作阶段").get_attribute("aria-orientation") == "vertical")
        # 真实键盘路径：只有已选中的标签在 Tab 顺序里（其余 tabindex=-1），方向键移动焦点并同时切换阶段
        tabidx = [t.get_attribute("tabindex") for t in tabs.all()]
        chk("只有当前阶段的标签在 Tab 顺序里", tabidx == ["-1", "0", "-1", "-1", "-1"], tabidx)
        tab(page, "章回").focus()
        seq = []
        for key in ("ArrowDown", "ArrowDown", "ArrowUp", "Home", "End", "ArrowRight"):
            page.keyboard.press(key)
            page.wait_for_timeout(250)
            seq.append((page.evaluate("document.activeElement && document.activeElement.textContent"), tab(page, page.evaluate("document.activeElement && document.activeElement.textContent")).get_attribute("aria-selected")))
        want = [("分集", "true"), ("立意", "true"), ("分集", "true"), ("立意", "true"), ("分集", "true"), ("分集", "true")]
        chk("方向键在可用阶段间移动并循环、焦点与选中同步、置灰项跳过、竖排不认左右键（章回 ↓分集 ↓立意 ↑分集 Home立意 End分集 →不动）", seq == want, seq)
        tab(page, "章回").click()
        page.wait_for_timeout(400)
        selected = [t.inner_text() for t in tabs.all() if t.get_attribute("aria-selected") == "true"]
        chk("默认选中「章回」且只选中一个", selected == ["章回"], selected)

        # 章回页：《春山》
        pick_book(page, "春山")
        panel = page.locator("#desk-panel")
        chk("书名与副标题", panel.get_by_role("heading", name="《春山》").count() == 1 and "等你确认细纲" in panel.inner_text() and "已写 2 章" in panel.inner_text(), panel.inner_text()[:80])
        chk("关卡提示与「查看并批准细纲」", panel.get_by_text("章细纲已定稿").count() == 1 and panel.get_by_role("button", name="查看并批准细纲").count() == 1)
        rows = panel.locator('[role=list][aria-label="章回"] [role=listitem]')
        chk("三行章节", rows.count() == 3, rows.count())
        tags = rows.locator(".tag").all_inner_texts()
        chk("三种状态标签", tags == ["待复核", "定稿", "细纲等你确认"], tags)
        colors = page.evaluate("""() => { const seal = getComputedStyle(document.documentElement).getPropertyValue('--seal').trim();
            const probe = document.createElement('span'); probe.style.color = seal; document.body.appendChild(probe);
            const sealRgb = getComputedStyle(probe).color; probe.remove();
            return [...document.querySelectorAll('#desk-panel [role=listitem] .tag')].map(el => getComputedStyle(el).color === sealRgb); }""")
        chk("只有「定稿」是朱色", colors == [False, True, False], colors)
        chk("第 1、2 章有摘要，第 3 章「待定章名」", "听见北岸今夜封渡" in rows.nth(0).inner_text() and "待定章名" in rows.nth(2).inner_text(), rows.nth(2).inner_text()[:60])
        weights = page.evaluate("[...document.querySelectorAll('#desk-panel *')].filter(el => parseInt(getComputedStyle(el).fontWeight) > 400).map(el => el.tagName + ':' + (el.textContent || '').slice(0, 12))")
        chk("案头里没有任何加粗文字（章回页）", weights == [], weights[:6])
        shot(page, a.out, "01-dock-1440-chapters.png")

        # 留言（免费）
        chk("留言计数 2 / 5", panel.get_by_text("待处理留言 2 / 5").count() == 1)
        note = panel.get_by_label("给编辑部留一句话")
        note.fill("  走查留言：结尾再收一点。  ")
        panel.get_by_role("button", name="留言", exact=True).click()
        page.wait_for_timeout(1800)
        chk("留言成功提示与计数 3 / 5", panel.get_by_text("已留言。").count() == 1 and panel.get_by_text("待处理留言 3 / 5").count() == 1, panel.inner_text()[-120:])
        chk("留言后输入框清空", note.input_value() == "", note.input_value())

        # 展开行：读正文、问分身
        rows.nth(2).get_by_role("button", name="待定章名").click()
        chk("未写完的章没有「读正文」", rows.nth(2).get_by_role("button", name="读正文").count() == 0 and rows.nth(2).get_by_role("button", name="问分身").count() == 1)
        chk("章节行按钮的名字带章号", rows.nth(1).locator("button[aria-expanded]").get_attribute("aria-label") == "第 2 章　北岸脚步", rows.nth(1).locator("button[aria-expanded]").get_attribute("aria-label"))
        rows.nth(1).get_by_role("button", name="北岸脚步").click()
        chk("同一时刻只展开一行", panel.get_by_role("button", name="问分身").count() == 1)
        rows.nth(1).get_by_role("button", name="读正文").click()
        page.wait_for_timeout(1500)
        dialog = page.locator("dialog[open]")
        chk("读正文对话框：标题与正文", dialog.count() == 1 and dialog.get_by_role("heading", name="第 2 章　北岸脚步").count() == 1 and "清晨，雾。" in dialog.inner_text(), dialog.inner_text()[:60] if dialog.count() else "无对话框")
        chk("对话框带 scrim-dialog", "scrim-dialog" in (dialog.get_attribute("class") or ""), dialog.get_attribute("class"))
        chk("对话框是模态（:modal）", page.evaluate("document.querySelector('dialog[open]').matches(':modal')"))
        shot(page, a.out, "02-dock-1440-reader-dialog.png")
        dialog.get_by_role("button", name="关闭").click()
        page.wait_for_timeout(600)
        chk("关闭后焦点回到「读正文」", page.evaluate("document.activeElement && document.activeElement.textContent") == "读正文", page.evaluate("document.activeElement && document.activeElement.textContent"))
        rows.nth(1).get_by_role("button", name="问分身").click()
        page.wait_for_timeout(400)
        chk("问分身：输入框得到引子", page.locator("textarea").first.input_value() == "关于《春山》第 2 章：", page.locator("textarea").first.input_value())
        page.locator("textarea").first.fill("")

        # 细纲对话框（只看，不批准）
        panel.get_by_role("button", name="查看并批准细纲").click()
        page.wait_for_timeout(1800)
        dialog = page.locator("dialog[open]")
        editor = dialog.locator('section[aria-label="细纲编辑器"]')
        chk("细纲对话框里是书斋的细纲编辑器", editor.count() == 1 and "船家的价" in (editor.locator("textarea").first.input_value() if editor.count() else ""), dialog.inner_text()[:80] if dialog.count() else "无对话框")
        chk("沿用原按钮与扣费提示", all(dialog.get_by_role("button", name=n).count() == 1 for n in ("批准（原样）", "改完批准", "附一句话重新定稿")) and dialog.get_by_text("重新定稿会再次扣除草莓。").count() == 1)
        shot(page, a.out, "03-dock-1440-plan-dialog.png")
        dialog.get_by_role("button", name="关闭").click()
        page.wait_for_timeout(600)
        chk("细纲对话框已关闭、书的状态没变", page.locator("dialog[open]").count() == 0 and "等你确认细纲" in panel.inner_text())

        # 立意页
        tab(page, "立意").click()
        page.wait_for_timeout(500)
        chk("立意页内容", all(t in panel.inner_text() for t in ("一句话故事", "少年在封渡前夜独自过江", "主题", "核心冲突", "主角", "想要：过江", "主线", "过江：封渡之前找到一条船")), panel.inner_text()[:120])
        shot(page, a.out, "04-dock-1440-idea.png")
        panel.get_by_role("button", name="在书斋打开").last.click()
        page.wait_for_timeout(1200)
        chk("「在书斋打开」打开书斋抽屉并定位到这本书", page.locator("#novel-drawer").get_attribute("aria-hidden") == "false" and page.locator('#novel-drawer iframe').get_attribute("src") == f"/novels/{A}?embed=1", page.locator('#novel-drawer iframe').get_attribute("src"))
        page.locator('#novel-drawer button[aria-label="收起书斋"]').click()
        page.wait_for_timeout(600)

        # 并排方式下 Esc 不收起
        panel.focus()
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        chk("并排方式下 Esc 不收起案头", page.locator("#desk-panel").count() == 1)

        # 分集页：《归舟》
        pick_book(page, "归舟")
        tab(page, "章回").click()
        page.wait_for_timeout(600)
        chk("完结的书：有「导出」、没有「做成片」、没有留言框", panel.get_by_role("button", name="导出").count() == 1 and panel.get_by_role("button", name="做成片").count() == 0 and panel.get_by_label("给编辑部留一句话").count() == 0)
        tab(page, "分集").click()
        page.wait_for_timeout(2500)
        text = panel.inner_text()
        chk("方案汇总与状态", "方案第 1 版　共 3 集" in text and "待批准" in text, text[:160])
        chk("未纳入原文的提示", "还有 1 段原文没有纳入分集，在工作室处理。" in text)
        project = panel.locator('select[aria-label="短片项目"]')
        chk("两个项目可切换，默认选新的那个", project.count() == 1 and project.locator("option").count() == 2 and project.input_value() == P_NEW, project.input_value() if project.count() else "无下拉")
        eps = panel.locator('[role=list][aria-label="分集"] [role=listitem]')
        chk("三行分集，含变化、钩子与时长", eps.count() == 3 and "变化：少年得知北岸今夜封渡。" in eps.nth(0).inner_text() and "钩子：船家只肯再走一趟。" in eps.nth(0).inner_text() and "1 分 15 秒" in eps.nth(0).inner_text(), eps.nth(0).inner_text()[:90])
        chk("有警告的集带「有提示」", eps.nth(0).locator(".tag", has_text="有提示").count() == 1)
        shot(page, a.out, "05-dock-1440-episodes.png")

        # 修改一集（免费）
        eps.nth(0).get_by_role("button", name="雾里渡口").click()
        eps.nth(0).get_by_role("button", name="修改").click()
        page.wait_for_timeout(600)
        dialog = page.locator("dialog[open]")
        chk("单集修改框是工作室原对话框", dialog.get_by_role("heading", name="修改第 1 集").count() == 1, dialog.inner_text()[:40] if dialog.count() else "无对话框")
        dialog.get_by_label("标题").fill("雾锁渡口")
        dialog.get_by_role("button", name="保存").click()
        page.wait_for_timeout(1800)
        text = panel.inner_text()
        chk("保存后标题更新、方案变第 2 版", page.locator("dialog[open]").count() == 0 and "雾锁渡口" in eps.nth(0).inner_text() and "方案第 2 版" in text, text[:120])

        # 不是版本冲突的 409：对话框留着、显示后端给的原因、填的内容还在、不出现冲突提示
        eps.nth(2).get_by_role("button", name="一个人过江").click()
        eps.nth(2).get_by_role("button", name="修改").click()
        page.wait_for_timeout(600)
        page.route("**/episodes/ops", lambda route: route.fulfill(status=409, headers={"Content-Type": "application/json"}, body=json.dumps({"detail": "拆解尚未完成，完成后才能修改分集方案"}, ensure_ascii=False)))

        def locked_plan(route):
            if route.request.method != "GET":
                return route.fallback()
            response = route.fetch()
            data = response.json()
            data["active_breakdown_status"] = "running"
            data["status"] = "running"
            route.fulfill(response=response, json=data)

        plan_url = re.compile(r"/api/studio/projects/" + P_NEW + r"/episodes$")
        page.route(plan_url, locked_plan)
        dialog = page.locator("dialog[open]")
        dialog.get_by_label("标题").fill("先别丢我填的字")
        dialog.get_by_role("button", name="保存").click()
        page.wait_for_timeout(2200)
        dialog = page.locator("dialog[open]")
        kept = dialog.count() == 1 and dialog.get_by_label("标题").input_value() == "先别丢我填的字"
        chk("其他 409：对话框仍开着且填的内容还在", kept, dialog.get_by_label("标题").input_value() if dialog.count() else "对话框没了")
        chk("其他 409：对话框里显示后端给的原因", dialog.count() == 1 and "拆解尚未完成，完成后才能修改分集方案" in dialog.inner_text(), dialog.inner_text()[-90:] if dialog.count() else "")
        chk("其他 409：不出现「在别处改动」的冲突提示", panel.locator('[role=alert]', has_text="分集方案已在别处改动").count() == 0)
        chk("其他 409：方案已刷新成锁定状态（案头显示拆解未完成）", "拆解还没全部完成，暂时不能修改或批准，去工作室看进度。" in panel.inner_text(), panel.inner_text()[60:160])
        cancel = page.locator("dialog[open]").get_by_role("button", name="取消")
        chk("其他 409 且方案被锁：对话框的「取消」仍然可用", cancel.count() == 1 and cancel.is_enabled())
        shot(page, a.out, "06a-dock-1440-locked-409.png")
        # 13.1：方案已锁定时再点「保存」，不再发请求，对话框里显示本地的锁定原因
        ops_posts = []
        count_ops = lambda r: ops_posts.append(r.url) if r.method == "POST" and r.url.endswith("/episodes/ops") else None
        page.on("request", count_ops)
        page.locator("dialog[open]").get_by_role("button", name="保存").click()
        page.wait_for_timeout(1500)
        page.remove_listener("request", count_ops)
        dialog = page.locator("dialog[open]")
        chk("方案被锁时再点保存：不再发修改请求", ops_posts == [], ops_posts[:2])
        chk("方案被锁时再点保存：对话框显示锁定原因、填的字还在", dialog.count() == 1 and "拆解还没全部完成，暂时不能修改或批准，去工作室看进度。" in dialog.inner_text() and dialog.get_by_label("标题").input_value() == "先别丢我填的字", dialog.inner_text()[-80:] if dialog.count() else "对话框没了")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        chk("其他 409 且方案被锁：按 Esc 能关掉对话框", page.locator("dialog[open]").count() == 0, page.locator("dialog[open]").count())
        page.unroute("**/episodes/ops")
        page.unroute(plan_url)
        if page.locator("dialog[open]").count():
            # 对话框真的锁死了：只能像用户一样刷新整页，才能继续后面的检查
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            page.add_style_tag(content="nextjs-portal{display:none!important}")
            desk_gets.clear()
        panel.get_by_role("button", name="刷新").click()
        page.wait_for_timeout(2500)
        chk("解除锁定并刷新后，案头恢复可改", "拆解还没全部完成" not in panel.inner_text() and "方案第 2 版" in panel.inner_text(), panel.inner_text()[60:160])
        if eps.nth(2).locator("button[aria-expanded]").get_attribute("aria-expanded") == "true":
            eps.nth(2).locator("button[aria-expanded]").click()

        # 版本冲突：先在别处改一次，再保存
        eps.nth(1).get_by_role("button", name="船家的价").click()
        eps.nth(1).get_by_role("button", name="修改").click()
        page.wait_for_timeout(600)
        outside = page.evaluate("""async (pid) => { const r = await fetch(`/api/studio/projects/${pid}/episodes/ops`, { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-Dev-User': localStorage.getItem('fiona_username') || 'tester' },
            body: JSON.stringify({ expected_revision: 2, op: 'edit', no: 3, fields: { title: '外部改动' } }) }); return r.status; }""", P_NEW)
        chk("（准备）在别处改动成功", outside == 200, outside)
        dialog = page.locator("dialog[open]")
        dialog.get_by_label("标题").fill("这次会冲突")
        dialog.get_by_role("button", name="保存").click()
        page.wait_for_timeout(2200)
        still_open = page.locator("dialog[open]").count()
        alert = panel.locator('[role=alert]', has_text="分集方案已在别处改动，已为你刷新，请再试一次。")
        chk("版本冲突：对话框关闭，案头里出现冲突提示", still_open == 0 and alert.count() == 1, (still_open, alert.count()))
        shot(page, a.out, "06-dock-1440-conflict.png")
        if page.locator("dialog[open]").count():
            page.locator("dialog[open]").get_by_role("button", name="取消").click()
            page.wait_for_timeout(600)
        text = panel.inner_text()
        chk("冲突后列表已刷新到第 3 版、看到别处的改动、没写入冲突的那次", "方案第 3 版" in text and "外部改动" in text and "这次会冲突" not in text, text[:160])

        # 合并（免费）
        chk("最后一集不能合并", (eps.nth(2).get_by_role("button", name="外部改动").click() or True) and eps.nth(2).get_by_role("button", name="与下一集合并").is_disabled())
        eps.nth(0).get_by_role("button", name="雾锁渡口").click()
        eps.nth(0).get_by_role("button", name="与下一集合并").click()
        page.wait_for_timeout(500)
        dialog = page.locator("dialog[open]")
        chk("合并确认文案", "把第 1 集和第 2 集合成一集，标题、变化、钩子会拼在一起。" in dialog.inner_text(), dialog.inner_text()[:80])
        dialog.get_by_role("button", name="确认合并").click()
        page.wait_for_timeout(1800)
        chk("合并后剩两集、方案变第 4 版", eps.count() == 2 and "方案第 4 版　共 2 集" in panel.inner_text(), panel.inner_text()[:120])

        # 问分身、去工作室
        head = eps.nth(0).locator("button[aria-expanded]")
        if head.get_attribute("aria-expanded") != "true":
            head.click()
        eps.nth(0).get_by_role("button", name="问分身").click()
        page.wait_for_timeout(400)
        chk("问分身（分集）：输入框得到引子", page.locator("textarea").first.input_value() == "关于《归舟》第 1 集：", page.locator("textarea").first.input_value())
        page.locator("textarea").first.fill("已有的字")
        eps.nth(0).get_by_role("button", name="问分身").click()
        page.wait_for_timeout(400)
        chk("输入框已有内容时把引子放在前面", page.locator("textarea").first.input_value() == "关于《归舟》第 1 集：已有的字", page.locator("textarea").first.input_value())
        page.locator("textarea").first.fill("")

        # 批准（免费）
        approve = panel.get_by_role("button", name="批准分集方案")
        chk("批准按钮可用", approve.is_enabled())
        approve.click()
        page.wait_for_timeout(500)
        dialog = page.locator("dialog[open]")
        chk("批准确认文案", "即将批准方案第 4 版。批准后再改会生成新版本、需要重新批准。" in dialog.inner_text(), dialog.inner_text()[:80])
        dialog.get_by_role("button", name="确认批准").click()
        page.wait_for_timeout(1800)
        chk("批准后标签「已批准」、按钮禁用", "已批准" in panel.inner_text() and panel.get_by_role("button", name="批准分集方案").is_disabled(), panel.inner_text()[:100])
        shot(page, a.out, "07-dock-1440-episodes-approved.png")

        panel.get_by_role("button", name="在工作室打开").first.click()
        page.wait_for_timeout(3000)
        urls = [f.url for f in page.frames]
        chk("「在工作室打开」打开工作室抽屉并跳到这个项目", page.locator("#studio-drawer").get_attribute("aria-hidden") == "false" and any(f"/studio/{P_NEW}" in u for u in urls), urls)
        chk("工作室 iframe 的 src 属性字面量没变", page.locator('#studio-drawer iframe').get_attribute("src") == "/studio?embed=1", page.locator('#studio-drawer iframe').get_attribute("src"))
        page.locator('#studio-drawer button[aria-label="收起工作室"]').click()
        page.wait_for_timeout(600)

        # 没有分集方案的项目
        project.select_option(value="desk-proj-old")
        page.wait_for_timeout(1800)
        chk("没有分集方案的项目：只有空提示与去工作室，没有汇总与批准栏", "还没有分集方案，拆解在工作室里做。" in panel.inner_text() and "方案第" not in panel.inner_text() and panel.get_by_role("button", name="批准分集方案").count() == 0, panel.inner_text()[-140:])
        shot(page, a.out, "08-dock-1440-episodes-empty-project.png")
        project.select_option(value=P_NEW)
        page.wait_for_timeout(1500)

        # 记忆：刷新后恢复
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.add_style_tag(content="nextjs-portal{display:none!important}")
        chk("刷新后案头自动恢复打开、仍是《归舟》的分集页", page.locator("#desk-panel").count() == 1 and page.locator("#desk-panel").get_by_role("heading", name="《归舟》").count() == 1 and tab(page, "分集").get_attribute("aria-selected") == "true")
        chk("恢复打开不把焦点移进面板", page.evaluate("document.activeElement && document.activeElement.id") != "desk-panel", page.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)"))

        # 夜色
        # 夜色：点侧栏自己的昼夜按钮（直接改 class 会被页面的主题同步脚本改回去）
        page.locator("button:has(span.theme-day)").first.evaluate("el => el.click()")
        page.wait_for_timeout(1000)
        dark_bg = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()")
        chk("夜色已切换（--paper 变深）", dark_bg.lower() == "#161412", dark_bg)
        seal_dark = page.evaluate("""() => { const el = [...document.querySelectorAll('#desk-panel .tag')].find(e => e.textContent === '已批准'); return el ? getComputedStyle(el).color : null; }""")
        chk("夜色下「已批准」用夜朱", seal_dark == "rgb(229, 111, 93)", seal_dark)
        shot(page, a.out, "09-dock-1440-night.png")
        page.locator("button:has(span.theme-day)").first.evaluate("el => el.click()")
        page.wait_for_timeout(800)
        chk("切回日色", page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()").lower() == "#e8eeea")

        # 关闭后不再发任何案头请求
        close_desk(page)
        page.wait_for_timeout(800)
        desk_gets.clear()
        page.wait_for_timeout(7000)
        chk("案头关闭后 7 秒内主页面不再发案头请求", desk_gets == [], desk_gets[:3])

        # 流里出卡自动打开并定位
        page.route("**/api/chat", lambda route: route.fulfill(status=200, headers={"Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache"},
                   body=sse([{"card": {"type": "card", "subtype": "studio_project", "source": "短片工作室", "points": ["《归舟》", "已建项目，尚未花费"], "url": f"/studio/{P_NEW}", "error": False}, "append": True}, {"done": True}])))
        page.locator("textarea").first.fill("把《归舟》做成片")
        page.keyboard.press("Enter")
        page.wait_for_timeout(4500)
        opened = page.locator("#desk-panel").count() == 1
        chk("流里出现工作室卡：案头自动打开", opened)
        chk("自动打开不抢走输入框的焦点", page.evaluate("document.activeElement && document.activeElement.tagName") == "TEXTAREA", page.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)"))
        chk("自动定位到《归舟》的分集页", opened and page.locator("#desk-panel").get_by_role("heading", name="《归舟》").count() == 1 and tab(page, "分集").get_attribute("aria-selected") == "true")
        shot(page, a.out, "10-dock-1440-auto-open.png")
        page.unroute("**/api/chat")
        # 自动打开之后，从面板里的「收起案头」收起：焦点应当回到头部开关
        page.locator('#desk-panel button[aria-label="收起案头"]').click()
        page.wait_for_timeout(700)
        chk("自动打开后从面板里收起：案头关闭且焦点回到头部开关", page.locator("#desk-panel").count() == 0 and page.evaluate("document.activeElement && document.activeElement.getAttribute('aria-controls')") == "desk-panel", page.evaluate("document.activeElement && (document.activeElement.getAttribute('aria-controls') || document.activeElement.tagName)"))
        open_desk(page)
        page.wait_for_timeout(1200)
        # 一张卡片只定位一次：之后手动换书、关掉再开，应当还是手动选的那本
        pick_book(page, "春山")
        close_desk(page)
        page.wait_for_timeout(600)
        open_desk(page)
        page.wait_for_timeout(1500)
        chk("定位过的卡片不会在重开案头时再次生效（仍是手动选的《春山》）", page.locator("#desk-panel").get_by_role("heading", name="《春山》").count() == 1, page.locator("#desk-panel").inner_text()[:40])

        # 13.4：分集的修改对话框开着时来一张项目卡（指向同一本书的另一个项目），不能把对话框和填的字冲掉
        pick_book(page, "归舟")
        tab(page, "分集").click()
        page.wait_for_timeout(2200)
        panel = page.locator("#desk-panel")
        eps = panel.locator('[role=list][aria-label="分集"] [role=listitem]')
        project = panel.locator('select[aria-label="短片项目"]')
        chk("（准备）案头在《归舟》新项目的分集页", project.input_value() == P_NEW and eps.count() >= 1, (project.input_value(), eps.count()))
        held = []
        page.route("**/api/chat", lambda route: held.append(route))
        page.locator("textarea").first.fill("再看看旧项目")
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        head = eps.nth(0).locator("button[aria-expanded]")
        if head.get_attribute("aria-expanded") != "true":
            head.click()
        eps.nth(0).get_by_role("button", name="修改").click()
        page.wait_for_timeout(600)
        dialog = page.locator("dialog[open]")
        dialog.get_by_label("标题").fill("对话框开着别冲掉")
        chk("（准备）回复还在路上、修改对话框已打开", len(held) == 1 and dialog.count() == 1, (len(held), dialog.count()))
        if held:
            held[0].fulfill(status=200, headers={"Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache"},
                            body=sse([{"card": {"type": "card", "subtype": "studio_project", "source": "短片工作室", "points": ["《归舟》", "旧项目"], "url": f"/studio/{P_OLD}", "error": False}, "append": True}, {"done": True}]))
        page.wait_for_timeout(3500)
        dialog = page.locator("dialog[open]")
        kept = dialog.count() == 1 and dialog.get_by_label("标题").input_value() == "对话框开着别冲掉"
        chk("分集对话框开着时来项目卡：对话框还在、填的字还在", kept, dialog.get_by_label("标题").input_value() if dialog.count() else "对话框没了")
        chk("分集对话框开着时来项目卡：案头没被换到卡片指的项目", project.input_value() == P_NEW, project.input_value())
        shot(page, a.out, "10a-dock-1440-card-while-dialog.png")
        page.unroute("**/api/chat")
        if page.locator("dialog[open]").count():
            page.locator("dialog[open]").get_by_role("button", name="取消").click()
            page.wait_for_timeout(600)
        chk("取消后对话框关闭，仍在新项目", page.locator("dialog[open]").count() == 0 and project.input_value() == P_NEW, project.input_value())
        if project.input_value() != P_NEW:
            project.select_option(P_NEW)
            page.wait_for_timeout(1500)

        # ---------- 1280：右侧抽屉 ----------
        close_desk(page)
        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(800)
        w_closed = box(page, chat)["width"]
        open_desk(page)
        pos = page.evaluate("getComputedStyle(document.querySelector('#desk-panel').parentElement).position")
        pb, cb = box(page, "#desk-panel"), box(page, chat)
        chk("1280 抽屉：fixed 定位", pos == "fixed", pos)
        chk("1280 抽屉：聊天列宽度不变", abs(cb["width"] - w_closed) <= 1, (w_closed, cb["width"]))
        chk("1280 抽屉：面板 448、书耳右缘离视口右缘 12px", abs((pb["x"] + pb["width"] + 28 + 12) - 1280) <= 2 and abs(pb["width"] - 448) <= 1, pb)
        chk("1280 抽屉：面板不透明（底色 alpha=1）", page.evaluate(ALPHA) == 1, page.evaluate("getComputedStyle(document.querySelector('#desk-panel')).backgroundColor"))
        z = page.evaluate("[getComputedStyle(document.querySelector('#desk-panel').parentElement).zIndex, getComputedStyle(document.querySelector('#novel-drawer')).zIndex]")
        chk("抽屉层级低于大抽屉", int(z[0]) < int(z[1]), z)
        shot(page, a.out, "11-drawer-1280.png")
        page.locator("#desk-panel").focus()
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)
        chk("1280 抽屉：Esc 收起且焦点回到开关", page.locator("#desk-panel").count() == 0 and page.evaluate("document.activeElement && document.activeElement.getAttribute('aria-controls')") == "desk-panel")
        for width in (1263, 1423):
            page.set_viewport_size({"width": width, "height": 800})
            page.wait_for_timeout(500)
            chk(f"{width} 宽（扣掉 17px 滚动条）无横向溢出", page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        ctx.close()

        # ---------- 390：手机半屏 ----------
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="light", is_mobile=True, has_touch=True, device_scale_factor=2)
        page = ctx.new_page()
        page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))
        login(page, a.base, "tester")
        chk("390：开关可见且不小于 40×40", toggle(page).count() == 1 and box(page, 'button[aria-controls="desk-panel"]:visible')["width"] >= 40 and box(page, 'button[aria-controls="desk-panel"]:visible')["height"] >= 40, box(page, 'button[aria-controls="desk-panel"]:visible'))
        page.route("**/api/chat", lambda route: route.fulfill(status=200, headers={"Content-Type": "text/event-stream; charset=utf-8"},
                   body=sse([{"card": {"type": "card", "subtype": "studio_project", "source": "短片工作室", "points": ["《归舟》"], "url": f"/studio/{P_NEW}", "error": False}, "append": True}, {"done": True}])))
        page.locator("textarea").first.fill("把《归舟》做成片")
        page.locator("textarea").first.press("Enter")
        page.wait_for_timeout(4000)
        chk("390：流里出卡不自动打开", page.locator("#desk-panel").count() == 0)
        page.unroute("**/api/chat")
        open_desk(page)
        page.wait_for_timeout(1500)
        panel = page.locator("#desk-panel")
        chk("390：之后手动打开时已定位到《归舟》的分集页", panel.get_by_role("heading", name="《归舟》").count() == 1 and tab(page, "分集").get_attribute("aria-selected") == "true", panel.inner_text()[:60])
        pos = page.evaluate("getComputedStyle(document.querySelector('#desk-panel').parentElement).position")
        pb = box(page, "#desk-panel")
        comp = page.locator("textarea").first.bounding_box()
        chk("390 半屏：fixed、通栏", pos == "fixed" and abs(pb["x"]) <= 1 and abs(pb["width"] - 390) <= 1, (pos, pb))
        chk("390 半屏：底边在输入框上方", pb["y"] + pb["height"] <= comp["y"] + 1, (pb["y"] + pb["height"], comp["y"]))
        chk("390 半屏：高度约 45dvh", abs(pb["height"] - 844 * 0.45) <= 4, pb["height"])
        chk("390 半屏：上方至少露出 120px 聊天区", pb["y"] - 94 >= 120, pb["y"] - 94)
        chk("390 半屏：面板不透明（底色 alpha=1）", page.evaluate(ALPHA) == 1, page.evaluate("getComputedStyle(document.querySelector('#desk-panel')).backgroundColor"))
        chk("390：阶段标签横排", page.evaluate("getComputedStyle(document.querySelector('[role=tablist][aria-label=\"创作阶段\"] [role=tab]')).writingMode") == "horizontal-tb")
        chk("390：无横向溢出", page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        small = page.evaluate("[...document.querySelectorAll('#desk-panel button, #desk-panel select, #desk-panel input')].filter(el => el.getClientRects().length && (el.getBoundingClientRect().height < 40)).map(el => (el.textContent || el.getAttribute('aria-label') || el.tagName).slice(0, 10) + ':' + Math.round(el.getBoundingClientRect().height))")
        chk("390：案头里的可点控件高度都不小于 40", small == [], small[:8])
        shot(page, a.out, "12-sheet-390-half.png")
        panel.get_by_role("button", name="展开").click()
        page.wait_for_timeout(700)
        pb2 = box(page, "#desk-panel")
        chk("390：点「展开」后顶到头部下沿、明显变高、按钮变「收起一半」", pb2["height"] > pb["height"] + 100 and panel.get_by_role("button", name="收起一半").count() == 1 and abs(pb2["y"] - 94) <= 2, pb2)
        shot(page, a.out, "13-sheet-390-expanded.png")
        tab(page, "章回").click()
        page.wait_for_timeout(800)
        shot(page, a.out, "14-sheet-390-chapters.png")
        ctx.close()

        # ---------- 空态与无权限 ----------
        for user, expect, name, button in (("empty_user", "案头空着。对分身说想写什么，或者到书斋新建一本。", "15-empty-user.png", "去书斋"), ("outsider", "你的账号暂未开通小说工坊", "16-no-access.png", None)):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            login(page, a.base, user)
            open_desk(page)
            text = page.locator("#desk-panel").inner_text()
            chk(f"{user}：{expect[:12]}…", expect in text, text[:100])
            shot(page, a.out, name)
            if button:
                page.locator("#desk-panel").get_by_role("button", name=button).click()
                page.wait_for_timeout(800)
                chk("空态「去书斋」打开书斋抽屉", page.locator("#novel-drawer").get_attribute("aria-hidden") == "false")
            ctx.close()
        browser.close()

    noise = [e for e in console_errors if not re.search(r"favicon|Failed to load resource|microphone|Permissions|ERR_ABORTED|/api/chat", e)]
    chk("走查过程中没有页面脚本错误", not [e for e in noise if e.startswith("PAGEERROR")], [e for e in noise if e.startswith("PAGEERROR")][:3])
    print("console.error（已去噪）：", noise[:6])
    failed = [r for r in results if not r[1]]
    print(f"== FAIL {len(failed)} / {len(results)}")
    with open(os.path.join(a.out, "walk.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
