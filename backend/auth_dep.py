# -*- coding: utf-8 -*-
"""
FastAPI 鉴权依赖。

所有用户数据端点 Depends(get_current_user)，从 Authorization: Bearer <jwt>
解出 username，失败抛 401。

DEV_MODE=1 时支持 X-Dev-User 头跳过 JWT —— 和前端 proxy.ts 在
NODE_ENV=development 时跳过路由门禁对称，本地起服务不用每次过 OTP。
"""
import os
from fastapi import Header, HTTPException, WebSocket
from auth import decode_token


def _dev_mode() -> bool:
    return os.getenv("DEV_MODE", "0") == "1"


def _decode_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return decode_token(authorization[7:])


def get_current_user(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
) -> str:
    """必选鉴权 —— 失败抛 401。"""
    u = _decode_bearer(authorization)
    if u:
        return u
    if _dev_mode() and x_dev_user:
        v = x_dev_user.strip()
        if v:
            return v
    raise HTTPException(status_code=401, detail="未鉴权或鉴权失败")


def get_optional_user(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
) -> str | None:
    """可选鉴权 —— 没鉴权时返回 None，不抛错。
    用于 plaza/feed 这类匿名也能用、有身份则个性化的端点。"""
    u = _decode_bearer(authorization)
    if u:
        return u
    if _dev_mode() and x_dev_user:
        v = x_dev_user.strip()
        if v:
            return v
    return None


async def ws_authenticate(websocket: WebSocket) -> str | None:
    """WebSocket 鉴权：浏览器不能给 WS 加 Authorization 头，只能从 query 拿。
    成功返回 username；失败返回 None（调用方负责 close）。"""
    params = websocket.query_params
    token = params.get("token")
    if token:
        u = decode_token(token)
        if u:
            return u
    if _dev_mode():
        dev_user = params.get("dev_user")
        if dev_user and dev_user.strip():
            return dev_user.strip()
    return None
