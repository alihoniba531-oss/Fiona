# -*- coding: utf-8 -*-
"""
FastAPI 鉴权依赖。

所有用户数据端点 Depends(get_current_user)，优先复用中间件验证后的身份；
非浏览器客户端也可使用 Authorization: Bearer <jwt>。失败抛 401。

DEV_MODE=1 时支持 X-Dev-User 头跳过 JWT —— 和前端 proxy.ts 在
NODE_ENV=development 时跳过路由门禁对称，本地起服务不用每次过 OTP。
"""
import os
from urllib.parse import unquote
from fastapi import Header, HTTPException, WebSocket, Request
from auth import decode_token_claims


def _dev_mode() -> bool:
    return os.getenv("DEV_MODE", "0") == "1"


async def authenticate_token(token: str | None) -> str | None:
    if not token:
        return None
    claims = decode_token_claims(token)
    if not claims:
        return None
    from database import is_session_valid
    if not await is_session_valid(claims["sub"], claims["sv"]):
        return None
    return claims["sub"]


async def _decode_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return await authenticate_token(authorization[7:])


def _decode_dev_user(raw: str | None) -> str | None:
    """X-Dev-User 头若含非 ASCII（如中文用户名），前端会 encodeURIComponent，后端 unquote 还原。"""
    if not raw:
        return None
    v = unquote(raw).strip()
    return v or None


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
) -> str:
    """必选鉴权 —— 失败抛 401。
    主入口是 main.py 的 require_auth 中间件：通过则把 user 写到 request.state.user，
    本函数直接读。中间件没设说明走了白名单，再从 header 兜底（少数 Depends 链路）。"""
    u = getattr(request.state, "user", None)
    if u:
        return u
    u = await _decode_bearer(authorization)
    if u:
        return u
    u = await authenticate_token(request.cookies.get("fiona_token"))
    if u:
        return u
    if _dev_mode():
        v = _decode_dev_user(x_dev_user)
        if v:
            return v
    raise HTTPException(status_code=401, detail="未鉴权或鉴权失败")


async def get_optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
) -> str | None:
    """可选鉴权 —— 没鉴权时返回 None，不抛错。
    用于 plaza/feed 这类匿名也能用、有身份则个性化的端点。"""
    u = getattr(request.state, "user", None)
    if u:
        return u
    u = await _decode_bearer(authorization)
    if u:
        return u
    # Plaza Feed 等匿名白名单会绕过全局中间件；若浏览器带着会话 Cookie，
    # 仍应识别身份以提供个性化结果。
    u = await authenticate_token(request.cookies.get("fiona_token"))
    if u:
        return u
    if _dev_mode():
        v = _decode_dev_user(x_dev_user)
        if v:
            return v
    return None


async def ws_authenticate(websocket: WebSocket) -> str | None:
    """WebSocket 鉴权使用同源握手自动携带的 HttpOnly Cookie。
    成功返回 username；失败返回 None（调用方负责 close）。"""
    params = websocket.query_params
    # 浏览器 WebSocket 握手会自动带同源 HttpOnly Cookie，不再需要把 JWT 放进 URL。
    token = websocket.cookies.get("fiona_token")
    u = await authenticate_token(token)
    if u:
        return u
    if _dev_mode():
        dev_user = params.get("dev_user")
        if dev_user and dev_user.strip():
            return dev_user.strip()
    return None
