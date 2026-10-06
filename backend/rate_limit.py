# -*- coding: utf-8 -*-
# 全局限流器（slowapi）。
# 单独成模块是为了避开循环 import：routers/* 在 main.py 里 include 之前就被 import，
# 若把 limiter 定义在 main.py，各 router 反过来 import main 会成环。
# main 和各 router 共用 limiter 与每日上限助手。
import ipaddress
import math
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi.responses import JSONResponse
from limits import RateLimitItem, RateLimitItemPerDay, parse
from slowapi import Limiter
from slowapi.util import get_remote_address

import database


def _client_ip(request) -> str:
    """只有受信任代理对端提供的代理头可用于限流。

    uvicorn 通常已按 X-Forwarded-For 改写 client.host，此时直接用该地址。
    对端仍属于 FIONA_TRUSTED_PROXIES 时，依次取 X-Real-IP、XFF 最后一跳。
    每个反代入口必须覆盖 X-Real-IP，并向 X-Forwarded-For 追加真实来源。
    无效 IP（如 TestClient 的 testclient）不受信，保留原值作为键。
    """
    peer = get_remote_address(request)
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    trusted = False
    for raw in os.getenv("FIONA_TRUSTED_PROXIES", "127.0.0.1,::1").split(","):
        try:
            network = ipaddress.ip_network(raw.strip(), strict=False)
        except ValueError:
            continue
        if isinstance(network, ipaddress.IPv6Network) and network.network_address.ipv4_mapped:
            network = ipaddress.ip_network(
                (network.network_address.ipv4_mapped, network.prefixlen - 96), strict=False,
            )
        if address.version == network.version and address in network:
            trusted = True
            break
    if not trusted:
        return peer
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return peer


limiter = Limiter(key_func=_client_ip)

_DAILY_SETTINGS = {
    "official_exchange": ("FIONA_DAILY_OFFICIAL_EXCHANGES", 3),
    "hot_expand": ("FIONA_DAILY_HOT_EXPANDS", 30),
    "card_detail": ("FIONA_DAILY_CARD_DETAILS", 30),
    "asr": ("FIONA_DAILY_ASR", 300),
}
_INVALID_DAILY_WARNED: set[str] = set()


def daily_caps_enabled() -> bool:
    return limiter.enabled and os.getenv("DEV_MODE", "0") != "1"


def daily_cap(kind: str) -> int:
    name, default = _DAILY_SETTINGS[kind]
    raw = os.getenv(name, str(default))
    try:
        if not re.fullmatch(r"[0-9]+", raw):
            raise ValueError("not a positive integer")
        amount = int(raw)
        if amount > 0:
            return amount
    except ValueError:
        pass
    if name not in _INVALID_DAILY_WARNED:
        print(f"[daily] {name} 无效，使用默认值 {default}")
        _INVALID_DAILY_WARNED.add(name)
    return default


def daily_cap_response(kind: str, amount: int | None = None) -> JSONResponse:
    messages = {
        "hot_expand": "今天的热点展开次数已用完，明天再来吧。",
        "card_detail": "今天的详情查看次数已用完，明天再来吧。",
        "asr": "今天的语音识别次数已用完，明天再来吧，可以先打字。",
    }
    now = datetime.now(timezone(timedelta(hours=8)))
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    retry_after = max(1, math.ceil((midnight - now).total_seconds()))
    if kind == "official_exchange":
        amount = daily_cap(kind) if amount is None else amount
        message = f"今天的官方体验次数已用完（每天 {amount} 次），明天再来吧。"
    else:
        message = messages[kind]
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={"detail": message, "error": message, "retry_after": retry_after},
    )


class _DailyLimitItem(RateLimitItemPerDay):
    def key_for(self, *identifiers) -> str:
        # The day's accumulated count must survive a live configuration change.
        return RateLimitItemPerDay(1, namespace=self.namespace).key_for(*identifiers)


def check_daily_cap(kind: str, user: str) -> JSONResponse | None:
    if not daily_caps_enabled():
        return None
    amount = daily_cap(kind)
    item = _DailyLimitItem(amount)
    identifiers = ("daily", kind, user, database._today_shanghai())
    if check_and_hit([(item, identifiers, 1)]) is not None:
        return daily_cap_response(kind, amount)
    return None


def check_and_hit(
    checks: list[tuple[str | RateLimitItem, tuple[str, ...], int]],
    on_reject: Callable[[tuple[str, ...], int], None] | None = None,
) -> int | None:
    """Check every quota before charging any of them; return seconds to retry."""
    if not limiter.enabled:
        return None

    parsed = [
        (parse(limit) if isinstance(limit, str) else limit, identifiers, cost)
        for limit, identifiers, cost in checks
    ]
    failed = [
        (item, identifiers)
        for item, identifiers, cost in parsed
        if not limiter.limiter.test(item, *identifiers, cost=cost)
    ]
    if failed:
        reset_time = max(
            limiter.limiter.get_window_stats(item, *identifiers).reset_time
            for item, identifiers in failed
        )
        retry_after = max(1, math.ceil(reset_time - time.time()))
        if on_reject is not None:
            on_reject(failed[0][1], retry_after)
        return retry_after

    for item, identifiers, cost in parsed:
        limiter.limiter.hit(item, *identifiers, cost=cost)
    return None
