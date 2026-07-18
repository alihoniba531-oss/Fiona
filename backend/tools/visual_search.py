# -*- coding: utf-8 -*-
"""
GUI 视觉搜索: Playwright headless Chromium + 通义千问 VL。
不用爬虫,用真浏览器+视觉理解,完美绕过反爬。

执行流程:
1. 启 headless Chromium
2. 访问百度搜索 URL
3. 等 JS 渲染完成
4. 截图
5. base64 编码送给 qwen-vl-max
6. VL 提炼成 3-5 条要点
7. 返回卡片 dict

注意:由于 main.py 的 generate() 在 asyncio event loop 里,
sync_playwright 不能直接在 loop 里用——所以用线程隔离。
"""
import base64
import json
import os
import queue
import re
import threading
from openai import OpenAI


_vl_client_cache = None
def _get_vl_client():
    global _vl_client_cache
    if _vl_client_cache is None:
        _vl_client_cache = OpenAI(
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _vl_client_cache


def _capture_screenshot_blocking(search_url: str, ready_selector: str = "", timeout_ms: int = 15000) -> bytes:
    """同步用 Playwright 截图——必须在独立线程跑。
    ready_selector: 等这个 CSS 选择器出现就截图(比 networkidle 稳得多;SPA 经常 networkidle 永不到)
    """
    from playwright.sync_api import sync_playwright
    print(f"[Playwright] 启动 headless Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--mute-audio",
                "--disable-blink-features=AutomationControlled",  # 反 webdriver 检测
            ],
        )
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 1800},
                locale="zh-CN",
                extra_http_headers={
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            page = context.new_page()
            print(f"[Playwright] 访问: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
            # ready_selector 出现 = 搜到了真的结果页;不出现 = 八成是反爬/验证页,
            # 这种情况下截图给 VL 也是浪费,直接抛错让上层 fallback 到下个搜索源
            if ready_selector:
                try:
                    page.wait_for_selector(ready_selector, timeout=5000)
                except Exception:
                    raise RuntimeError(f"ready_selector {ready_selector!r} 未出现 (可能反爬/验证页)")
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
            page.wait_for_timeout(500)  # 给字体/图片最后渲染一点时间
            print(f"[Playwright] 截图...")
            return page.screenshot(full_page=False)
        finally:
            browser.close()
            print(f"[Playwright] 浏览器已关闭")


def _capture_in_thread(search_url: str, ready_selector: str = "", timeout_sec: int = 60) -> bytes:
    """把 Playwright sync 调用隔离到子线程,避免 asyncio event loop 冲突"""
    result_q = queue.Queue()
    err_q = queue.Queue()

    def _worker():
        # main.py 设了 WindowsSelectorEventLoopPolicy(Uvicorn 需要),
        # 但 Playwright 需要 ProactorEventLoop 启 Chromium 子进程。
        # 在这个线程里临时切回去。
        import sys as _sys, asyncio as _asyncio
        if _sys.platform == "win32":
            _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())
        try:
            img = _capture_screenshot_blocking(search_url, ready_selector=ready_selector)
            result_q.put(img)
        except Exception as e:
            import traceback
            traceback.print_exc()
            err_q.put(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        raise TimeoutError(f"Playwright 截图超过 {timeout_sec}s")
    try:
        err = err_q.get_nowait()
        raise err
    except queue.Empty:
        pass
    try:
        return result_q.get_nowait()
    except queue.Empty:
        raise RuntimeError("截图线程既没返回结果也没抛错")


def _vl_extract_points(image_bytes: bytes, query: str) -> list:
    """调通义千问 VL,看图提炼 3-5 条要点"""
    client = _get_vl_client()
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        f"用户在搜索:『{query}』。这是搜索结果的截图。\n"
        f"请你看图,直接告诉用户答案。\n"
        f"\n"
        f"⚠️ 核心要求:\n"
        f"1. 如果截图里有天气卡片/知识面板/即时答案——直接读里面的数据(温度/日期/天气)\n"
        f"2. 如果搜索结果摘要里包含了具体数据(温度数字/时间/地点)——提取出来告诉用户\n"
        f"3. **不要**列出网站名和网址——用户不关心哪个网站,只关心答案\n"
        f"4. 如果搜天气,给温度、降水、日期、建议\n"
        f"5. 如果搜新闻,给事件要点\n"
        f"6. 如果真的一丁点有用信息都找不到,才说\"没搜到\"\n"
        f"\n"
        f"输出 JSON: {{\"points\": [\"要点1\", \"要点2\", ...]}}\n"
        f"只输出 JSON,不要其他文字。"
    )
    resp = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        max_tokens=500,
        temperature=0.3,
    )
    content = (resp.choices[0].message.content or "").strip()
    # 容错: VL 偶尔在 JSON 前后加杂字
    m = re.search(r'\{[\s\S]*\}', content)
    if m:
        content = m.group(0)
    try:
        data = json.loads(content)
        points = [str(p).strip() for p in data.get("points", []) if p]
        return points[:5] if points else []
    except Exception:
        # 不是 JSON 就按行切
        lines = [l.strip("•- ").strip() for l in content.split("\n") if l.strip()]
        lines = [l for l in lines if l and not l.startswith(("{", "}", '"points"'))]
        return lines[:5]


def _search_weather_direct(query: str) -> dict | None:
    """天气直通车——用 wttr.in 直接拿数据,不绕搜索引擎"""
    import requests as _requests
    from urllib.parse import quote as _quote
    city = query.replace("天气", "").replace("明天", "").replace("今天", "").replace("预报", "").strip()
    if not city or len(city) < 1:
        city = "Ningbo"
    try:
        r = _requests.get(f"https://wttr.in/{_quote(city)}?format=j1", timeout=8)
        r.raise_for_status()
        data = r.json()
        cur = data.get("current_condition", [{}])[0]
        weather_list = data.get("weather", [])
        if not cur:
            return None

        wd = cur.get("weatherDesc", [{}])[0].get("value", "?")
        icon = cur.get("weatherIconUrl", [{}])[0].get("value", "") if cur.get("weatherIconUrl") else ""

        # 未来几天预报
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        forecast = []
        for w in weather_list[:7]:
            date_str = w.get("date", "")
            hi = w.get("maxtempC", "?")
            lo = w.get("mintempC", "?")
            # 取正午时段描述
            midday = (w.get("hourly", []) or [])
            desc = "?"
            icon_f = ""
            if len(midday) > 4:
                desc = (midday[4].get("weatherDesc", [{}])[0].get("value", "?") if midday[4].get("weatherDesc") else "?")
                icon_f = (midday[4].get("weatherIconUrl", [{}])[0].get("value", "") if midday[4].get("weatherIconUrl") else "")
            # 星期几
            from datetime import datetime as _dt
            try:
                d = _dt.strptime(date_str, "%Y-%m-%d")
                day_label = weekday_names[d.weekday()] if d.weekday() < 7 else date_str
            except Exception:
                day_label = date_str
            forecast.append({"day": day_label, "date": date_str, "high": hi, "low": lo, "condition": desc, "icon": icon_f})

        return {
            "type": "card",
            "subtype": "weather",
            "source": city,
            "url": f"https://wttr.in/{_quote(city)}",
            "weather": {
                "location": city,
                "currentTemp": cur.get("temp_C", "?"),
                "feelsLike": cur.get("FeelsLikeC", "?"),
                "condition": wd,
                "conditionIcon": icon,
                "humidity": cur.get("humidity", "?"),
                "windSpeed": cur.get("windspeedKmph", "?"),
                "visibility": cur.get("visibility", "?"),
                "forecast": forecast,
            },
            "points": [],  # 不用 points，前端直接读 weather
        }
    except Exception:
        pass
    return None


def visual_search(query: str) -> dict:
    """主入口:GUI 视觉搜索,返回卡片 dict"""
    if not query or not query.strip():
        return {"type": "card", "source": "搜索", "points": ["没说要搜啥"], "error": True}
    query = query.strip()

    # 天气直通车: wttr.in，不走搜索引擎
    if "天气" in query:
        card = _search_weather_direct(query)
        if card:
            return card
        # wttr.in 失败就诚实告知
        return {"type": "card", "source": f"搜索:{query[:20]}", "points": ["天气查询暂时失败,稍后重试"], "error": True}

    from urllib.parse import quote
    # 多源 fallback：百度优先(国内 IP 友好) → Bing(国际)→ DuckDuckGo HTML(无 JS,最稳)
    sources = [
        {
            "name":  "百度",
            "url":   f"https://www.baidu.com/s?wd={quote(query)}",
            "ready": "#content_left",  # 百度搜索结果区
        },
        {
            "name":  "Bing",
            "url":   f"https://www.bing.com/search?q={quote(query)}&setlang=zh-Hans&cc=cn&setmkt=zh-CN",
            "ready": "#b_results",
        },
        {
            "name":  "DuckDuckGo",
            "url":   f"https://html.duckduckgo.com/html?q={quote(query)}",
            "ready": ".results",
        },
    ]

    screenshot = None
    used_source = ""
    errors: list[str] = []
    for src in sources:
        try:
            print(f"[visual_search] 尝试 {src['name']}: {src['url']}")
            screenshot = _capture_in_thread(src["url"], ready_selector=src["ready"], timeout_sec=20)
            if screenshot:
                print(f"[visual_search] {src['name']} 成功, {len(screenshot)} bytes")
                used_source = src["name"]
                break
        except Exception as e:
            errors.append(f"{src['name']}:{type(e).__name__}")
            print(f"[visual_search] {src['name']} 失败: {type(e).__name__}: {e}")
            continue

    if not screenshot:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": [
                "三个搜索源都没拉到结果:",
                "  " + " / ".join(errors[:3]),
                "可能原因:服务器网络问题、所有搜索源都反爬、或 Playwright 启动失败",
            ],
            "error": True,
        }
    search_url = next((s["url"] for s in sources if s["name"] == used_source), sources[0]["url"])

    try:
        points = _vl_extract_points(screenshot, query)
    except Exception as e:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": [f"VL 提炼失败:{type(e).__name__}", f"{str(e)[:120]}"],
            "error": True,
        }

    if not points:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": ["VL 没看出有用信息(可能页面是反爬挑战页)"],
            "error": True,
        }

    return {
        "type": "card",
        "source": f"搜索:{query[:20]}",
        "url": search_url,
        "points": points,
    }
