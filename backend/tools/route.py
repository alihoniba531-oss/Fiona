# -*- coding: utf-8 -*-
"""
驾车路线工具。
Nominatim 地址解析 + OSRM 公开路由服务，全免费、无 key。

注意：
- Nominatim 公开实例有 ~1 req/sec 软限制；本工具一次问答最多 2 次调用，没超
- OSRM demo server 同样有限速，正经上生产建议自建
- 中国境内 OSM 数据：主要城市路网 OK，乡镇覆盖有缺
- 目前只支持驾车（OSRM demo 只开了 driving profile）
"""
import requests
from urllib.parse import quote


_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OSRM = "https://router.project-osrm.org/route/v1/driving"
_UA = "fiona-assistant/0.1 (chat-app)"


def _geocode(addr: str):
    """addr → (lon, lat, display_name) or None"""
    try:
        r = requests.get(
            _NOMINATIM,
            params={"q": addr, "format": "json", "limit": 1, "accept-language": "zh-CN"},
            headers={"User-Agent": _UA},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    if not data:
        return None
    return float(data[0]["lon"]), float(data[0]["lat"]), data[0].get("display_name") or addr


def _fmt_duration(sec: float) -> str:
    m = int(round(sec / 60))
    if m < 60:
        return f"{m} 分钟"
    h, mr = divmod(m, 60)
    return f"{h} 小时 {mr} 分钟" if mr else f"{h} 小时"


def _short_name(s: str) -> str:
    # Nominatim display_name 形如 "海淀区, 北京市, 中国"，取前 2 段
    parts = [p.strip() for p in (s or "").split(",")]
    return " · ".join(parts[:2]) if len(parts) >= 2 else (s or "")


def _err(msg: str) -> dict:
    return {"type": "card", "source": "路线", "points": [f"❌ {msg}"], "error": True}


def route(origin: str, destination: str) -> dict:
    origin = (origin or "").strip()
    destination = (destination or "").strip()
    if not origin:
        return _err("起点没说清")
    if not destination:
        return _err("终点没说清")

    o = _geocode(origin)
    if not o:
        return _err(f"找不到起点位置：{origin[:30]}")
    d = _geocode(destination)
    if not d:
        return _err(f"找不到终点位置：{destination[:30]}")

    olon, olat, oname = o
    dlon, dlat, dname = d

    try:
        rr = requests.get(
            f"{_OSRM}/{olon},{olat};{dlon},{dlat}",
            params={"overview": "false", "steps": "true"},
            timeout=15,
        )
        rr.raise_for_status()
        rd = rr.json()
    except Exception as e:
        return _err(f"路线服务异常：{type(e).__name__}")

    if rd.get("code") != "Ok":
        return _err(f"OSRM 拒绝：{rd.get('code')}")

    routes = rd.get("routes") or []
    if not routes:
        return _err("没找到可行路线")

    r0 = routes[0]
    dist_km = r0.get("distance", 0) / 1000
    dur_str = _fmt_duration(r0.get("duration", 0))

    # 提取主路名（去重保序）
    roads: list[str] = []
    for leg in r0.get("legs") or []:
        for step in leg.get("steps") or []:
            n = (step.get("name") or "").strip()
            if n and n not in roads:
                roads.append(n)

    points = [f"🚗 {dist_km:.1f} km · 预计 {dur_str}"]
    if roads:
        shown = roads[:6]
        via = " → ".join(shown)
        if len(roads) > 6:
            via += f"  …(还有 {len(roads) - 6} 段)"
        points.append(f"途经：{via}")
    points.append(f"起：{_short_name(oname)}")
    points.append(f"终：{_short_name(dname)}")

    return {
        "type": "card",
        "source": f"路线 · {origin} → {destination}"[:40],
        "url": f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route={olat}%2C{olon}%3B{dlat}%2C{dlon}",
        "points": points,
    }
