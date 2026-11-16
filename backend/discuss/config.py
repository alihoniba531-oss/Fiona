"""讨论群配置。

全部配置都在调用时读取环境变量，不在导入时缓存；数值类配置非法时
回落到默认值，并且每个变量最多告警一次，告警文案不含取值。
"""

from __future__ import annotations

from datetime import datetime
import logging
import os
import re
from zoneinfo import ZoneInfo


_DIGITS = re.compile(r"[0-9]+")
_INVALID_SETTINGS_WARNED: set[str] = set()


def _warn(name: str) -> None:
    if name not in _INVALID_SETTINGS_WARNED:
        logging.warning("[discuss] 配置项无效，使用默认值：%s", name)
        _INVALID_SETTINGS_WARNED.add(name)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    if isinstance(raw, str) and _DIGITS.fullmatch(raw):
        try:
            value = int(raw)
        except ValueError:  # 超长数字串（Python 整数转换上限）
            value = None
        if value is not None and minimum <= value <= maximum:
            return value
    _warn(name)
    return default


def enabled() -> bool:
    """FIONA_DISCUSS 只有字面 "1" 为真。"""
    return os.getenv("FIONA_DISCUSS") == "1"


def allowed_users() -> set[str]:
    """FIONA_DISCUSS_USERS：逗号分隔的精确用户名。"""
    raw = os.getenv("FIONA_DISCUSS_USERS") or ""
    return {part.strip() for part in raw.split(",") if part.strip()}


def user_allowed(username: str) -> bool:
    return username in allowed_users()


def chat_enabled(username: str | None, crisis: bool = False) -> bool:
    """聊天看讨论群：非危机、账号在白名单、两个讨论群开关都开启。"""
    if crisis or not username:
        return False
    if os.getenv("FIONA_DISCUSS") != "1":
        return False
    if username not in allowed_users():
        return False
    return os.getenv("FIONA_DISCUSS_CHAT") == "1"


def chat_cards_enabled(username: str | None) -> bool:
    """任务卡与意见卡：在聊天看讨论群的基础上再加卡片开关。"""
    return os.getenv("FIONA_DISCUSS_CHAT_CARDS") == "1" and chat_enabled(username)


def max_running() -> int:
    """FIONA_DISCUSS_MAX_RUNNING：全站同时在跑的群数，默认 2。"""
    return _bounded_int("FIONA_DISCUSS_MAX_RUNNING", 2, 1, 10)


def daily_groups() -> int:
    """FIONA_DAILY_DISCUSS_GROUPS：每人每个上海自然日新建群数，默认 5。"""
    return _bounded_int("FIONA_DAILY_DISCUSS_GROUPS", 5, 1, 50)


def search_strawberries() -> int:
    """FIONA_DISCUSS_SEARCH_STRAWBERRIES：每次联网搜索的草莓数，默认 2。"""
    return _bounded_int("FIONA_DISCUSS_SEARCH_STRAWBERRIES", 2, 0, 50)


def today_beijing() -> str:
    """北京时间的当天，格式 YYYY-MM-DD。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
