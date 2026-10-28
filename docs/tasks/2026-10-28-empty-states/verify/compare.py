"""比对 HEAD 与候选实测：改动项要求 HEAD 失败、候选通过；回归项要求两边都通过。"""
import json, re, sys
H = json.load(open(sys.argv[1], encoding="utf-8")); C = json.load(open(sys.argv[2], encoding="utf-8"))
# 可选第 3、4 个参数：measure.py v2 只重跑隐私部分的结果（HEAD、候选），覆盖 v1 的 privacy 段
if len(sys.argv) >= 5:
    H["privacy"] = json.load(open(sys.argv[3], encoding="utf-8"))["privacy"]
    C["privacy"] = json.load(open(sys.argv[4], encoding="utf-8"))["privacy"]
rows = []
def check(kind, name, fn):
    def safe(d):
        try: return bool(fn(d))
        except Exception: return False
    h, c = safe(H), safe(C)
    ok = c and ((not h) if kind == "改" else h)
    rows.append((ok, kind, name, h, c))
VPS, THEMES = ("d1440", "m390"), ("day", "night")
for path in ("/novels/new", "/novels", "/studio"):
    check("改", f"SSR 原始 HTML {path}：确认中、无请登录", lambda d, p=path: d["identity"][f"ssr html {p}"]["pending"] and not d["identity"][f"ssr html {p}"]["login"])
    check("改", f"脚本晚到 3 秒 {path}：1s/2.5s 显示确认中", lambda d, p=path: all(s["pending"] and not s["login"] for s in d["identity"][f"late js {p}"][:2]))
check("改", "profile 慢 4s：1s/2.5s 确认中，8s 出现向导", lambda d: all(s["pending"] and not s["login"] for s in d["identity"]["profile slow 4s"]["timeline"][:2]) and d["identity"]["profile slow 4s"]["timeline"][2]["wizard"])
check("回归", "profile 500：8s 显示原登录文案（已知局限）", lambda d: d["identity"]["profile 500"]["timeline"][2]["login"])
for vp in VPS:
    check("改", f"{vp} 工作室抽屉 h1 宽高 ≤1px", lambda d, v=vp: d["shelves"][f"{v} studio drawer"]["h1"]["w"] <= 1 and d["shelves"][f"{v} studio drawer"]["h1"]["h"] <= 1)
    check("回归", f"{vp} 工作室抽屉「新建项目」是 button 且贴右（间距 ≤1）", lambda d, v=vp: d["shelves"][f"{v} studio drawer"]["newProject"]["tag"] == "BUTTON" and d["shelves"][f"{v} studio drawer"]["newProject"]["visible"] and abs(d["shelves"][f"{v} studio drawer"]["newProject"]["rightGap"]) <= 1)
    check("回归", f"{vp} 独立页 /studio h1 可见", lambda d, v=vp: d["shelves"][f"{v} standalone /studio"]["h1"]["w"] > 100)
    for where in ("novel drawer", "standalone /novels"):
        check("改", f"{vp} {where} 0 本书：可见「新建一本」恰 1 个且不在页眉", lambda d, v=vp, w=where: d["shelves"][f"{v} {w}"]["newBookVisible"] == 1 and d["shelves"][f"{v} {w}"]["newBookInHeader"] == 0)
for th in THEMES:
    for vp in VPS:
        k = f"{th}-{vp}"
        check("改", f"{k} 开场：3 个可点、页头下输入釉片上、视口内、无粗体无中点、无横向滚动", lambda d, k=k: (lambda L: L["group"] and L["enabled"] == 3 and L["belowHeader"] and L["aboveComposer"] and L["inViewport"] and not L["hasDot"] and L["noHScroll"] and not L["inStatus"] and L["minHeight"] >= 40)(d["openers"][k]["layout"]) and d["openers"][k]["bold"] == [])
for vp in VPS:
    k = f"day-{vp}"
    check("回归", f"{k} 计数器正控：打字回车数到 1 次 /api/chat", lambda d, k=k: d["openers"][k]["counterControl"] == 1)
    check("改", f"{k} 点「聊聊今天」：0 次非 GET，输入框为「聊聊今天」并聚焦", lambda d, k=k: d["openers"][k]["聊聊今天"]["nonGetDuring"] == 0 and d["openers"][k]["聊聊今天"]["value"] == "聊聊今天" and d["openers"][k]["聊聊今天"]["focused"])
    check("改", f"{k} 点「帮我画一张…」：0 次非 GET，进入生成图片模式", lambda d, k=k: d["openers"][k]["帮我画一张…"]["nonGetDuring"] == 0 and d["openers"][k]["帮我画一张…"]["imageMode"])
    check("改", f"{k} 点「看看我拍的这张图」：0 次非 GET，触发选文件", lambda d, k=k: d["openers"][k]["看看我拍的这张图"]["nonGetDuring"] == 0 and d["openers"][k]["看看我拍的这张图"]["fileChooser"])
    check("改", f"{k} 在「聊聊今天」上按住 Enter：0 次非 GET，且输入框恰为「聊聊今天」（不留空行）", lambda d, k=k: d["openers"][k]["holdEnter"]["nonGetDuring"] == 0 and d["openers"][k]["holdEnter"]["value"] == "聊聊今天")
for th in THEMES:
    for vp in VPS:
        k = f"{th}-{vp}"
        check("改", f"{k} 匹配页：右侧有「匹配是什么」与入口，无禁用词，写明不会建立真人聊天，左栏 ≥12px，无横向滚动", lambda d, k=k: (lambda m: m["rightText"] > 0 and "匹配是什么" in m["h2"] and m["link"] and m["link"]["href"] == "/agents/me" and m["link"]["target"] == "_top" and not m["forbidden"] and m["noHumanChat"] and m["leftSize"] >= 12 and m["noHScroll"])(d["match"][k]["match"]))
        check("改", f"{k} 设置抽屉「账户」页：「旧社交画像」0 次、新名 ≥1", lambda d, k=k: d["match"][k]["profile"]["old"] == 0 and d["match"][k]["profile"]["new"] >= 1)
        check("改", f"{k} 隐私：details 收起；第一段可见且在开关与保存之上、在 details 外；其余 7 段不渲染", lambda d, k=k: (lambda c: c["details"] and not c["details"]["open"] and c["rendered"][0] and not any(c["rendered"][1:]) and c["firstAboveSave"] and c["firstAboveToggle"] and c["firstOutsideDetails"])(d["privacy"][k]["closed"]))
        check("回归", f"{k} 隐私：展开后 8 段与 HEAD 逐字相同", lambda d, k=k: (d["privacy"][k].get("opened") or d["privacy"][k]["closed"])["texts"] == H["privacy"][k]["closed"]["texts"] and all((d["privacy"][k].get("opened") or d["privacy"][k]["closed"])["rendered"]))
        check("改", f"{k} 隐私：summary 高 ≥40、区块无粗体", lambda d, k=k: d["privacy"][k]["closed"]["details"]["summaryH"] >= 40 and d["privacy"][k]["bold"] == [])
check("改", "d1440 隐私：滚到「聊天模型」顶部时，下一节「本机监控」在首屏内", lambda d: d["privacy"]["day-d1440"]["nextSectionOnScreen"]["nextTop"] < d["privacy"]["day-d1440"]["nextSectionOnScreen"]["innerHeight"])
VIS = re.compile(r"^(自定义区间|从|到|不限|\d{4}年\d{1,2}月\d{1,2}日|清除筛选)(\|(自定义区间|从|到|不限|\d{4}年\d{1,2}月\d{1,2}日|清除筛选))*$")
for vp in VPS:
    check("改", f"zh-CN {vp} 日期：输入框透明但可找到、可见文字只含中文日期面、chip ≥40px", lambda d, v=vp: (lambda i: len(i["inputs"]) == 2 and all(x["opacity"] <= 0.01 for x in i["inputs"]) and VIS.match(i["visibleText"]) and len(i["chips"]) == 2 and all(ch["h"] >= 40 for ch in i["chips"]) and i["noHScroll"])(d["history"][f"zh-CN-{v}"]["initial"]))
    check("改", f"{vp} 日期：en-US 与 zh-CN 可见文字相同", lambda d, v=vp: d["history"][f"en-US-{v}"]["initial"]["visibleText"] == d["history"][f"zh-CN-{v}"]["initial"]["visibleText"] and d["history"][f"zh-CN-{v}"]["initial"]["chips"])
    check("改", f"{vp} 日期：点 chip 与回车都调用 showPicker", lambda d, v=vp: d["history"][f"zh-CN-{v}"]["pickAfterClick"] >= 1 and d["history"][f"zh-CN-{v}"].get("pickAfterEnter", 0) >= 2)
    check("改", f"{vp} 日期：填入 2026-10-27 显示「2026年10月27日」", lambda d, v=vp: "2026年10月27日" in d["history"][f"zh-CN-{v}"]["afterFill"]["visibleText"])
    check("改", f"{vp} 日期：只设「到」时「全部」不高亮", lambda d, v=vp: d["history"][f"zh-CN-{v}"]["onlyTo"]["allOn"] is False)
check("改", "m390 按住语音键：上方可见「松开发送」气泡（不拦点击、读屏隐藏、在视口内）", lambda d: any(x["data"] and x["visible"] and x["aboveButton"] and x["inViewport"] and x["pointerEvents"] == "none" and x["ariaHidden"] == "true" and x["text"] == "松开发送" for x in d["voice"]["m390"]["holding"]["hits"]))
check("回归", "m390 松开后气泡消失", lambda d: not any(x["data"] for x in d["voice"]["m390"]["released"]["hits"]))
check("回归", "d1440 按住时按钮短字可见、手机气泡不显示", lambda d: any(x["visible"] and not x["data"] for x in d["voice"]["d1440"]["holding"]["hits"]) and not any(x["data"] and x["visible"] for x in d["voice"]["d1440"]["holding"]["hits"]))
bad = [r for r in rows if not r[0]]
for ok, kind, name, h, c in rows:
    print(f"| {'通过' if ok else '失败'} | {kind} | {name} | {'过' if h else '败'} | {'过' if c else '败'} |")
print(f"== {len(rows)} 项，FAIL {len(bad)}")
