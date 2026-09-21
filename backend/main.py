# -*- coding: utf-8 -*-
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import posixpath
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from database import get_pending_upload_cleanup, init_db, mark_upload_cleanup_done
from rate_limit import limiter
from routers import agent_exchanges, agents, auth, cards, chat, conversations, hot, match, me, peer, plaza, voice
from utils.media import UPLOADS_DIR
from utils.background_tasks import create_background_task, shutdown_background_tasks
from utils.request_limits import MAX_REQUEST_BODY_BYTES, RequestBodyLimitMiddleware

if os.getenv("DEV_MODE", "0") == "1":
    import selectors as _selectors
    for _selector_name in ("EpollSelector", "PollSelector", "SelectSelector", "KqueueSelector", "DevpollSelector"):
        _selector_cls = getattr(_selectors, _selector_name, None)
        if _selector_cls is None or getattr(_selector_cls, "_fiona_dev_select_clamped", False):
            continue
        _orig_select = _selector_cls.select
        def _select_with_dev_timeout(self, timeout=None, _orig_select=_orig_select):
            if timeout is None or timeout > 0.001:
                timeout = 0.001
            return _orig_select(self, timeout)
        _selector_cls.select = _select_with_dev_timeout
        _selector_cls._fiona_dev_select_clamped = True

_UPLOAD_CLEANUP_INTERVAL_SECONDS = 15 * 60


async def _run_upload_cleanup_once() -> None:
    """重试历史/删号过程中因文件系统错误而未完成的媒体清理。"""
    pending_uploads = await get_pending_upload_cleanup()
    if pending_uploads:
        from utils.media import delete_uploaded_files
        deleted, failed = delete_uploaded_files(pending_uploads)
        await mark_upload_cleanup_done(deleted)
        if failed:
            print(f"[cleanup] {len(failed)} upload file(s) still pending deletion")


async def _run_upload_cleanup_periodically() -> None:
    while True:
        await asyncio.sleep(_UPLOAD_CLEANUP_INTERVAL_SECONDS)
        await _run_upload_cleanup_once()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from exchange_store import recover_interrupted_exchanges
    await recover_interrupted_exchanges()
    await _run_upload_cleanup_once()
    create_background_task(
        _run_upload_cleanup_periodically(),
        label="upload-cleanup",
    )
    try:
        yield
    finally:
        await shutdown_background_tasks()

app = FastAPI(title="Chloe API", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)

# ── 限流（slowapi）────────────────────────────────────────────────
# 不设全局 default_limits，免误伤 /uploads、TTS 流等；只在具体端点上挂 @limiter.limit。
# key_func 走 rate_limit.py 里从 X-Forwarded-For 取真实 IP（nginx 反代后面）。
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

app.include_router(voice.router)
app.include_router(hot.router)
app.include_router(cards.router)
app.include_router(plaza.router)
app.include_router(auth.router)
app.include_router(peer.router)
app.include_router(chat.router)
app.include_router(match.router)
app.include_router(me.router)
app.include_router(agents.router)
app.include_router(conversations.router)
app.include_router(agent_exchanges.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局鉴权中间件 ────────────────────────────────────────────────
# 默认所有 HTTP 请求都要鉴权，白名单放过；鉴权来源按优先级：
#   1. Authorization: Bearer <jwt> 头        — 非浏览器客户端兼容入口
#   2. cookie fiona_token=<jwt>              — Web、媒体和 WebSocket 的主入口
#   3. X-Dev-User 头（仅 DEV_MODE=1）         — 本地切身份调试
# WebSocket 握手不走 HTTP middleware，各 ws 端点用 ws_authenticate 单独鉴权。
_AUTH_PUBLIC_PATHS = {
    "/",
    "/auth/send-otp",
    "/auth/verify-otp",
    "/auth/test-login",
    "/auth/redeem-invite",
    "/plaza/tags",
    "/plaza/feed",
    "/plaza/community-interests",
}
_AUTH_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/hot/")


async def _can_view_generated_image(username: str, image_path: str) -> bool:
    """Generated results and uploaded references inherit message ownership."""
    import aiosqlite
    import database

    async with aiosqlite.connect(database.DB_PATH) as db:
        return await database.message_references_image(db, image_path, username=username)


@app.middleware("http")
async def require_auth(request: Request, call_next):
    if request.method == "OPTIONS":  # CORS 预检
        return await call_next(request)
    path = request.url.path
    # Match StaticFiles' path normalization before the DEV uploads bypass.
    upload_path = posixpath.normpath("/" + path.lstrip("/"))
    private_chat_image = upload_path.startswith("/uploads/") and posixpath.basename(upload_path).startswith(("generated_", "reference_", ".generated_", ".reference_"))
    if path.startswith("/uploads/") and not private_chat_image and os.getenv("DEV_MODE", "0") == "1":
        return await call_next(request)
    if path in _AUTH_PUBLIC_PATHS or any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIXES):
        return await call_next(request)
    from auth_dep import authenticate_token
    user = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        user = await authenticate_token(auth_header[7:])
    if not user:
        cookie_token = request.cookies.get("fiona_token")
        if cookie_token:
            user = await authenticate_token(cookie_token)
    if not user and os.getenv("DEV_MODE", "0") == "1":
        from urllib.parse import unquote
        dev = request.headers.get("x-dev-user") or request.query_params.get("dev_user")
        if dev:
            user = unquote(dev).strip() or None
            if user:
                # 仅开发通道允许用 X-Dev-User 临时建测试账号。
                from database import get_or_create_user
                await get_or_create_user(user)
    if not user:
        response = JSONResponse({"detail": "未鉴权或鉴权失败"}, status_code=401)
        response.delete_cookie("fiona_token", path="/")
        return response
    # 把鉴权结果挂到 request.state，路由里 Depends(get_current_user) 直接读，避免重复解码。
    request.state.user = user
    if private_chat_image and not await _can_view_generated_image(user, upload_path):
        return JSONResponse({"detail": "图片不存在或无权访问"}, status_code=404, headers={"Cache-Control": "private, no-store"})
    response = await call_next(request)
    if private_chat_image:
        # Do not retain private files in browser/shared caches after deletion/logout.
        response.headers["Cache-Control"] = "private, no-store"
        if response.status_code == 200 and request.query_params.get("download") == "1":
            from urllib.parse import quote
            response.headers["Content-Disposition"] = (
                "attachment; filename*=UTF-8''" + quote(posixpath.basename(upload_path), safe="")
            )
    return response

@app.get("/")
async def root():
    return {"status": "ok", "name": "Chloe API"}
