# -*- coding: utf-8 -*-
"""
热搜 / 热门话题工具。
直连 60s.viki.moe 公开 API（无需 key），微博 / 知乎 / 抖音 三源。
返回卡片 dict，套用既有的 card 结构（前端不用改 UI）。
"""
import requests

SOURCE_MAP = {
    # 用户口语 -> (60s API endpoint, 卡片显示名, 热度字段名/格式化方式)
    "微博": ("weibo", "微博热搜",   "int"),
    "weibo": ("weibo", "微博热搜",  "int"),
    "知乎": ("zhihu", "知乎热榜",   "desc"),
    "zhihu": ("zhihu", "知乎热榜",  "desc"),
    "抖音": ("douyin", "抖音热搜",  "int"),
    "douyin": ("douyin", "抖音热搜","int"),
}

DEFAULT_SOURCE = "微博"
TOP_N = 8
API_BASE = "https://60s.viki.moe/v2"


def _fmt_hot_int(n) -> str:
    """整数热度 → 中文简写 (1.5万 / 1230万)"""
    try:
        n = int(n)
    except Exception:
        return ""
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n/10_000:.0f}万" if n >= 1_000_000 else f"{n/10_000:.1f}万"
    return str(n)


def hot_topics(source: str = "") -> dict:
    src_key = (source or DEFAULT_SOURCE).strip().lower()
    # 容错：用户可能输入 "微博热搜" / "微博的" 等
    matched = None
    for k, v in SOURCE_MAP.items():
        if k in src_key or src_key in k:
            matched = v
            break
    if not matched:
        matched = SOURCE_MAP[DEFAULT_SOURCE]
    endpoint, label, hot_kind = matched

    try:
        r = requests.get(f"{API_BASE}/{endpoint}", timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 200:
            return _err_card(label, f"接口返回 code={data.get('code')}")
        items = data.get("data") or []
    except Exception as e:
        return _err_card(label, f"{type(e).__name__}:{str(e)[:80]}")

    if not items:
        return _err_card(label, "没拉到数据")

    points = []
    for i, it in enumerate(items[:TOP_N], 1):
        title = (it.get("title") or "").strip()
        if not title:
            continue
        if hot_kind == "int":
            hot = _fmt_hot_int(it.get("hot_value"))
        else:
            hot = (it.get("hot_value_desc") or "").strip()
        line = f"{i}. {title}"
        if hot:
            line += f" · {hot}"
        points.append(line)

    # 取第一条的 link 作为卡片 url（用户想"看详情"可点击）
    first_link = next((it.get("link") for it in items if it.get("link")), None)

    return {
        "type": "card",
        "source": label,
        "url": first_link,
        "points": points,
    }


def _err_card(label: str, msg: str) -> dict:
    return {
        "type": "card",
        "source": label,
        "points": [f"获取失败：{msg}"],
        "error": True,
    }
