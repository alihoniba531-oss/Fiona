# -*- coding: utf-8 -*-
# 全局限流器（slowapi）。
# 单独成模块是为了避开循环 import：routers/* 在 main.py 里 include 之前就被 import，
# 若把 limiter 定义在 main.py，各 router 反过来 import main 会成环。
# 这里只放纯粹的 limiter 实例，main 和各 router 都从这里 import。
import math
import time
from collections.abc import Callable

from limits import parse
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_ip(request) -> str:
    """取真实客户端 IP 做限流 key。
    服务在 nginx 反代后面，request.client.host 恒为 127.0.0.1。
    取信顺序（关键：不能取客户端可伪造的值，否则限流形同虚设）：
      1. X-Real-IP —— nginx 用 $remote_addr 设的真实对端 IP，客户端伪造不了。
      2. X-Forwarded-For 的【最后一跳】—— nginx 用 $proxy_add_x_forwarded_for
         会把客户端自带的 XFF 留在最前、把真实来源【追加在末尾】，所以取最后一个；
         取第一跳会被「每次发随机 XFF」绕过。
      3. 都没有（如本地直连）再退 TCP 对端。
    依赖 nginx 配置里有 `proxy_set_header X-Real-IP $remote_addr;`
    或 `X-Forwarded-For $proxy_add_x_forwarded_for;`（二选一即可）。"""
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)


def check_and_hit(
    checks: list[tuple[str, tuple[str, ...], int]],
    on_reject: Callable[[tuple[str, ...], int], None] | None = None,
) -> int | None:
    """Check every quota before charging any of them; return seconds to retry."""
    if not limiter.enabled:
        return None

    parsed = [(parse(limit), identifiers, cost) for limit, identifiers, cost in checks]
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
