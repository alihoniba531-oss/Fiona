# -*- coding: utf-8 -*-
"""
热搜 / 热门话题工具。
使用 60s 公开 API 及维护者文档列出的社区备用实例（无需 key）。
微博 / 知乎 / 抖音 / B站 / 头条五源；缓存 5 分钟，失败保留最多 1 小时的旧榜。
返回卡片 dict，套用既有的 card 结构（前端不用改 UI）。
"""
import copy
import os
import threading
import time
from datetime import datetime, timezone

import requests

SOURCE_MAP = {
    # 用户口语 -> (60s API endpoint, 卡片显示名, 热度字段名/格式化方式)
    # hot_kind: "int" 用 hot_value 整数；"desc" 用 hot_value_desc 字符串；"none" 不显示热度
    "微博": ("weibo", "微博热搜",   "int"),
    "weibo": ("weibo", "微博热搜",  "int"),
    "知乎": ("zhihu", "知乎热榜",   "desc"),
    "zhihu": ("zhihu", "知乎热榜",  "desc"),
    "抖音": ("douyin", "抖音热搜",  "int"),
    "douyin": ("douyin", "抖音热搜","int"),
    "b站": ("bili", "B站热搜",      "none"),
    "B站": ("bili", "B站热搜",      "none"),
    "bili": ("bili", "B站热搜",     "none"),
    "bilibili": ("bili", "B站热搜", "none"),
    "哔哩哔哩": ("bili", "B站热搜",  "none"),
    "头条": ("toutiao", "头条热榜",    "int"),
    "今日头条": ("toutiao", "头条热榜","int"),
    "toutiao": ("toutiao", "头条热榜", "int"),
}

DEFAULT_SOURCE = "微博"
TOP_N = 8
# 聊天卡保持简短；分类需要更完整的榜单，避免后排娱乐等话题被提前丢弃。
CATEGORY_TOP_N = 50
API_BASE = "https://60s.viki.moe/v2"
# 维护者公开实例列表：https://docs.60s-api.viki.moe/7306811m0
API_FALLBACK_BASES = ("https://60s.mizhoubaobei.top/v2", "https://60s.crystelf.top/v2")
CACHE_TTL = 300
FAILURE_TTL = 30
MAX_STALE = 3600
_cache: dict[str, tuple[float, dict]] = {}
_failures: dict[str, tuple[float, str]] = {}
_locks = {value[0]: threading.Lock() for value in SOURCE_MAP.values()}


def _api_bases() -> tuple[str, ...]:
    configured = os.getenv("HOT_TOPICS_API_BASE", "").strip().rstrip("/")
    return (configured,) if configured else (API_BASE, *API_FALLBACK_BASES)


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

    # 广场并发请求单源榜和分类榜，同源只抓一次；不同源仍可并行。
    with _locks[endpoint]:
        now = time.monotonic()
        cached = _cache.get(endpoint)
        if cached and now - cached[0] < CACHE_TTL:
            return copy.deepcopy(cached[1])
        failed = _failures.get(endpoint)
        if failed and now - failed[0] < FAILURE_TTL:
            return _unavailable(endpoint, label, failed[1], now)

        reason = "暂时未获取到热榜"
        for base in _api_bases():
            try:
                r = requests.get(f"{base}/{endpoint}", timeout=8)
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, dict) or data.get("code") != 200:
                    raise ValueError("invalid response")
                items = data.get("data")
                if not isinstance(items, list):
                    raise ValueError("invalid list")
                items = [it for it in items if isinstance(it, dict)
                         and isinstance(it.get("title"), str) and it["title"].strip()]
                if not items:
                    raise ValueError("empty list")
                card = _success_card(label, hot_kind, items)
                _cache[endpoint] = (time.monotonic(), card)
                _failures.pop(endpoint, None)
                return copy.deepcopy(card)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                reason = f"热榜服务暂不可用（HTTP {status}）" if status else "热榜服务暂不可用"
            except requests.RequestException:
                reason = "热榜连接失败，请稍后重试"
            except (ValueError, TypeError):
                reason = "热榜返回的数据暂不可用"
        now = time.monotonic()
        _failures[endpoint] = (now, reason)
        return _unavailable(endpoint, label, reason, now)


def _success_card(label: str, hot_kind: str, items: list[dict]) -> dict:

    points = []
    for i, it in enumerate(items[:TOP_N], 1):
        title = (it.get("title") or "").strip()
        if not title:
            continue
        if hot_kind == "int":
            hot = _fmt_hot_int(it.get("hot_value"))
        elif hot_kind == "desc":
            hot = str(it.get("hot_value_desc") or "").strip()
        else:
            hot = ""
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
        "items": [{"title": it["title"].strip(), "url": it.get("link")} for it in items[:CATEGORY_TOP_N]],
        "error": False,
        "stale": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _unavailable(endpoint: str, label: str, msg: str, now: float) -> dict:
    cached = _cache.get(endpoint)
    if cached and now - cached[0] < MAX_STALE:
        card = copy.deepcopy(cached[1])
        card.update(stale=True, message="更新失败，显示上次成功获取的热榜")
        return card
    _cache.pop(endpoint, None)
    return _err_card(label, msg)


def _err_card(label: str, msg: str) -> dict:
    return {
        "type": "card",
        "source": label,
        "points": [],
        "items": [],
        "error": True,
        "message": msg,
        "stale": False,
        "updated_at": None,
    }
