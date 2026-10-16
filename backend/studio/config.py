"""工作室配置统一在调用时读取，非法配置只告警一次。"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re


DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "studio_data"
DEFAULT_VIDEO_HOSTS = (
    "*.oss-accelerate.aliyuncs.com",
    "*.oss-cn-beijing.aliyuncs.com",
    "*.tos-cn-beijing.volces.com",
)
_INVALID_SETTINGS_WARNED: set[str] = set()


def _warn(name: str) -> None:
    if name not in _INVALID_SETTINGS_WARNED:
        print(f"[studio] {name} 无效，使用默认值")
        _INVALID_SETTINGS_WARNED.add(name)


def _positive(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        if math.isfinite(value) and value > 0:
            return value
    except (ValueError, OverflowError):
        pass
    _warn(name)
    return default


def _inflight(name: str) -> int:
    raw = os.getenv(name, "3")
    if re.fullmatch(r"[0-9]+", raw):
        try:
            value = int(raw)
            if 1 <= value <= 10:
                return value
        except ValueError:
            pass
    _warn(name)
    return 3


def _directory() -> Path:
    raw = os.getenv("FIONA_STUDIO_DIR")
    if not raw:
        return DEFAULT_DIRECTORY
    try:
        if "\x00" in raw:
            raise ValueError("invalid path")
        return Path(raw).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        _warn("FIONA_STUDIO_DIR")
        return DEFAULT_DIRECTORY


def _video_hosts() -> tuple[str, ...]:
    raw = os.getenv("FIONA_STUDIO_VIDEO_HOSTS")
    if raw is None:
        return DEFAULT_VIDEO_HOSTS
    patterns = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    if patterns and all(re.fullmatch(r"[a-z0-9*](?:[a-z0-9.*-]*[a-z0-9*])?", part) for part in patterns):
        return patterns
    _warn("FIONA_STUDIO_VIDEO_HOSTS")
    return DEFAULT_VIDEO_HOSTS


@dataclass(frozen=True)
class Settings:
    enabled: bool
    owners: frozenset[str]
    require_jwt: bool
    directory: Path
    daily_cny: float
    max_quote_cny: float
    max_inflight_wan: int
    max_inflight_seedance: int
    video_hosts: tuple[str, ...]
    poll_timeout_min: float

    def inflight_limit(self, provider: str) -> int:
        if provider == "wan":
            return self.max_inflight_wan
        if provider == "seedance":
            return self.max_inflight_seedance
        raise ValueError("不支持的视频提供商")


def get_settings() -> Settings:
    return Settings(
        enabled=os.getenv("FIONA_STUDIO", "1") != "0",
        owners=frozenset(part.strip() for part in os.getenv("FIONA_STUDIO_OWNERS", "").split(",") if part.strip()),
        require_jwt=os.getenv("FIONA_STUDIO_REQUIRE_JWT", "1") != "0",
        directory=_directory(),
        daily_cny=_positive("FIONA_STUDIO_DAILY_CNY", 300),
        max_quote_cny=_positive("FIONA_STUDIO_MAX_QUOTE_CNY", 100),
        max_inflight_wan=_inflight("FIONA_STUDIO_MAX_INFLIGHT_WAN"),
        max_inflight_seedance=_inflight("FIONA_STUDIO_MAX_INFLIGHT_SEEDANCE"),
        video_hosts=_video_hosts(),
        poll_timeout_min=_positive("FIONA_STUDIO_POLL_TIMEOUT_MIN", 30),
    )
