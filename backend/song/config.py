"""写歌智能体配置。

所有配置都在**调用时**读取环境变量；非法值回落到默认值，并且每个变量
最多告警一次。告警只打印变量名，绝不打印变量值（尤其是火山密钥）。
"""

from __future__ import annotations

import os
from pathlib import Path
import re


# 相对路径以 backend 目录为基准。
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SONG_DIR = BACKEND_DIR / "song_data"

DEFAULT_SONG_STRAWBERRIES = 30
DEFAULT_DAILY_SONGS = 10
DEFAULT_SONG_MAX_INFLIGHT = 2
DEFAULT_AIGC_PRODUCER = "Fiona"

_DIGITS = re.compile(r"[0-9]+")
_INVALID_SETTINGS_WARNED: set[str] = set()


def _warn(name: str) -> None:
    if name not in _INVALID_SETTINGS_WARNED:
        print(f"[song] code=config_invalid name={name}")
        _INVALID_SETTINGS_WARNED.add(name)


def _value(name: str) -> str | None:
    """返回非空字符串；未设置或空字符串都视为未设置。"""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    return raw


def _flag(name: str, *, default: bool) -> bool:
    raw = _value(name)
    if raw is None:
        return default
    if raw == "1":
        return True
    if raw == "0":
        return False
    _warn(name)
    return default


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _value(name)
    if raw is None:
        return default
    if _DIGITS.fullmatch(raw):
        try:
            value = int(raw)
        except ValueError:  # 超长数字串（Python 整数转换上限）
            value = None
        if value is not None and minimum <= value <= maximum:
            return value
    _warn(name)
    return default


def song_agent_enabled() -> bool:
    """FIONA_SONG_AGENT 默认关闭；只有字面 1 开启。"""
    return _flag("FIONA_SONG_AGENT", default=False)


def song_users() -> tuple[str, ...]:
    """FIONA_SONG_USERS：逗号分隔的精确用户名，空表示没人可用。"""
    raw = _value("FIONA_SONG_USERS")
    if raw is None:
        return ()
    return tuple(
        dict.fromkeys(part.strip() for part in raw.split(",") if part.strip())
    )


def song_enabled_for(user: str | None) -> bool:
    """开关打开且用户名精确命中白名单时开放。"""
    if not isinstance(user, str) or not user:
        return False
    return song_agent_enabled() and user in song_users()


def song_price_strawberries() -> int:
    return _bounded_int(
        "FIONA_SONG_STRAWBERRIES", DEFAULT_SONG_STRAWBERRIES, 1, 500
    )


def song_daily_limit() -> int:
    return _bounded_int("FIONA_DAILY_SONGS", DEFAULT_DAILY_SONGS, 1, 100)


def song_max_inflight() -> int:
    return _bounded_int(
        "FIONA_SONG_MAX_INFLIGHT", DEFAULT_SONG_MAX_INFLIGHT, 1, 5
    )


def song_dir() -> Path:
    """音频根目录，返回 resolve 后的绝对路径；绝不创建目录。"""
    raw = _value("FIONA_SONG_DIR")
    if raw is None:
        return DEFAULT_SONG_DIR.resolve()
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        _warn("FIONA_SONG_DIR")
        return DEFAULT_SONG_DIR.resolve()


def song_explicit_watermark() -> bool:
    """FIONA_SONG_EXPLICIT_WATERMARK 默认开启；只有字面 0 关闭。"""
    return _flag("FIONA_SONG_EXPLICIT_WATERMARK", default=True)


def aigc_producer() -> str:
    """隐式标识里的服务提供者名称：1–40 个可见字符。"""
    raw = _value("FIONA_AIGC_PRODUCER")
    if raw is None:
        return DEFAULT_AIGC_PRODUCER
    if (
        1 <= len(raw) <= 40
        and raw.strip()
        and all(char.isprintable() for char in raw)
    ):
        return raw
    _warn("FIONA_AIGC_PRODUCER")
    return DEFAULT_AIGC_PRODUCER


def volc_credentials() -> tuple[str, str]:
    """火山子账号 AK/SK；缺失时返回空字符串，绝不记录值。"""
    access_key = _value("VOLC_MUSIC_ACCESS_KEY") or ""
    secret_key = _value("VOLC_MUSIC_SECRET_KEY") or ""
    return access_key, secret_key


def song_configured() -> bool:
    """AK/SK 均非空才可生成。"""
    access_key, secret_key = volc_credentials()
    return bool(access_key and secret_key)
