"""将高德中文四日预报转成聊天天气卡。"""
from datetime import date
import math
import re

from tools import amap_mcp
from utils.city_name import normalize_city


_ERROR_MESSAGES = {
    "disabled": "天气服务暂未开启",
    "missing_key": "天气服务暂不可用",
    "auth": "天气服务暂不可用",
    "not_enabled": "天气服务暂不可用",
    "quota": "天气服务今天的查询额度用完了，晚点再试",
    "timeout": "天气服务响应超时，稍后再试",
}


def _failure(reason: str) -> dict:
    return {"type": "card", "source": "天气", "points": [reason], "error": True}


def _text(value) -> str:
    return value[:20] if isinstance(value, str) else ""


def _temperature(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        return value[:20] if math.isfinite(float(value)) else ""
    except ValueError:
        return ""


def _wind(direction, power) -> str:
    direction, power = _text(direction), _text(power)
    return " ".join(part for part in (f"{direction}风" if direction else "",
                                       f"{power}级" if power else "") if part)[:20]


def weather(city: str) -> dict:
    city = normalize_city(city)
    if not city:
        return _failure("没说是哪个城市")
    result = amap_mcp.call_tool("maps_weather", {"city": city})
    if not result.get("ok"):
        return _failure(_ERROR_MESSAGES.get(result.get("error"), "天气服务暂时出错了，稍后再试"))

    def not_found() -> dict:
        return _failure(f"没找到「{city[:10]}」的天气，换个城市名试试")

    data = result.get("data")
    if not isinstance(data, dict):
        return not_found()
    forecasts = data.get("forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        return not_found()
    forecast = []
    for item in forecasts:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("date")
        if not isinstance(raw_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            continue
        try:
            day = "周" + "一二三四五六日"[date.fromisoformat(raw_date).weekday()]
        except ValueError:
            continue
        forecast.append({
            "date": raw_date, "day": day,
            "dayWeather": _text(item.get("dayweather")),
            "nightWeather": _text(item.get("nightweather")),
            "high": _temperature(item.get("daytemp")),
            "low": _temperature(item.get("nighttemp")),
            "dayWind": _wind(item.get("daywind"), item.get("daypower")),
            "nightWind": _wind(item.get("nightwind"), item.get("nightpower")),
        })
        if len(forecast) == 4:
            break
    if not forecast:
        return not_found()
    upstream_city = data.get("city")
    location = (_text(upstream_city.strip()) or city) if isinstance(upstream_city, str) else city
    return {
        "type": "card", "subtype": "weather", "source": f"天气 · {location}",
        "points": [], "error": False,
        "weather": {"location": location, "forecast": forecast},
    }
