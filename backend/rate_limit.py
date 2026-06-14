# -*- coding: utf-8 -*-
# 全局限流器（slowapi）。
# 单独成模块是为了避开循环 import：routers/* 在 main.py 里 include 之前就被 import，
# 若把 limiter 定义在 main.py，各 router 反过来 import main 会成环。
# 这里只放纯粹的 limiter 实例，main 和各 router 都从这里 import。
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
