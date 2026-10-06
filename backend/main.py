# -*- coding: utf-8 -*-
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import posixpath
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from utils.dotenv_config import DotenvSelectionError, select_dotenv_path

# Read the selected dotenv before database, media, auth, or model modules bind
# configuration at import time. Process environment always wins.
_selected_dotenv = select_dotenv_path()
if _selected_dotenv is not None:
    try:
        load_dotenv(dotenv_path=_selected_dotenv, override=False)
    except OSError as error:
        raise DotenvSelectionError(f"配置文件不存在或不可读：{_selected_dotenv}") from error
# Legacy auth/llm imports also call load_dotenv at module scope. The selected
# file is already loaded; disable those redundant reads (including a different
# local .env when FIONA_ENV_FILE points at an isolated test or deployment file).
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from auth_dep import is_loopback_client
import aiosqlite
import database
from database import get_pending_upload_cleanup, init_db, mark_upload_cleanup_done
from rate_limit import limiter
from routers import agent_exchanges, agents, auth, cards, chat, conversations, hot, match, me, peer, plaza, voice
from utils import media
from utils.background_tasks import create_background_task, shutdown_background_tasks
from utils.request_limits import MAX_REQUEST_BODY_BYTES, RequestBodyLimitMiddleware
from utils.slow_pool import shutdown_slow_pool

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
_UPLOAD_TEMP_MAX_AGE_SECONDS = 60 * 60
_HEALTH_TIMEOUT_SECONDS = 3.0


def _default_pool_workers() -> int:
    try:
        workers = int(os.getenv("FIONA_DEFAULT_POOL_WORKERS", "32"))
    except ValueError:
        workers = 32
    return workers if 1 <= workers <= 256 else 32


async def _run_upload_cleanup_once() -> None:
    """重试历史/删号过程中因文件系统错误而未完成的媒体清理。"""
    pending_uploads = await get_pending_upload_cleanup()
    if pending_uploads:
        from utils.media import delete_uploaded_files
        deleted, failed = delete_uploaded_files(pending_uploads)
        await mark_upload_cleanup_done(deleted)
        if failed:
            print(f"[cleanup] {len(failed)} upload file(s) still pending deletion")


def _cleanup_stale_upload_temporaries() -> None:
    """删除强制退出留下的上传临时文件，不触碰正在处理的上传。"""
    cutoff = time.time() - _UPLOAD_TEMP_MAX_AGE_SECONDS
    try:
        with os.scandir(media.UPLOADS_DIR) as entries:
            for entry in entries:
                if not entry.name.startswith(".upload_"):
                    continue
                try:
                    if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < cutoff:
                        os.unlink(entry.path)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    print(f"[cleanup] upload temporary cleanup failed type={type(error).__name__}")
    except OSError as error:
        print(f"[cleanup] upload temporary cleanup failed type={type(error).__name__}")


async def _run_upload_cleanup_periodically() -> None:
    while True:
        await asyncio.sleep(_UPLOAD_CLEANUP_INTERVAL_SECONDS)
        try:
            await _run_upload_cleanup_once()
        except Exception as error:
            print(f"[cleanup] upload cleanup failed type={type(error).__name__}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=_default_pool_workers(), thread_name_prefix="fiona-chat")
    )
    await asyncio.to_thread(_cleanup_stale_upload_temporaries)
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
        shutdown_slow_pool()

app = FastAPI(title="Chloe API", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)

# ── 限流（slowapi）────────────────────────────────────────────────
# 不设全局 default_limits，免误伤 /uploads、TTS 流等；只在具体端点上挂 @limiter.limit。
# key_func 由 rate_limit.py 校验受信任代理；uvicorn 可能已改写 client.host。
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/uploads", StaticFiles(directory=media.UPLOADS_DIR), name="uploads")

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
    "/health",
    "/auth/send-otp",
    "/auth/verify-otp",
    "/auth/test-login",
    "/auth/redeem-invite",
    "/plaza/tags",
    "/plaza/feed",
    "/plaza/community-interests",
}
_AUTH_PUBLIC_PREFIXES = ("/hot/",)
# 热点展开会触发联网模型调用，不能匿名消耗额度；其余 /hot/* 只读榜单保持公开。
_AUTH_REQUIRED_PATHS = {"/hot/expand"}
# 交互式 API 文档只在 DEV_MODE=1 开放；生产环境一律 404，不对公网暴露接口清单。
_API_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")


async def _can_view_generated_image(username: str, image_path: str) -> bool:
    """Generated results and uploaded references inherit message ownership."""
    import aiosqlite
    import database

    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        return await database.message_references_image(db, image_path, username=username)


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    # Match StaticFiles' path normalization when identifying private/hidden uploads.
    upload_path = posixpath.normpath("/" + path.lstrip("/"))
    hidden_upload = upload_path.startswith("/uploads/") and any(
        part.startswith(".") for part in upload_path.split("/")[2:]
    )
    if request.method == "OPTIONS":  # CORS 预检
        return await call_next(request)
    private_chat_image = upload_path.startswith("/uploads/") and posixpath.basename(upload_path).startswith(("generated_", "reference_", ".generated_", ".reference_"))
    if (path.startswith("/uploads/") and not private_chat_image and not hidden_upload
            and os.getenv("DEV_MODE", "0") == "1" and is_loopback_client(request)):
        return await call_next(request)
    if path.startswith(_API_DOCS_PREFIXES):
        if os.getenv("DEV_MODE", "0") != "1":
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if not is_loopback_client(request):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return await call_next(request)
    if path in _AUTH_PUBLIC_PATHS or (
        path.startswith(_AUTH_PUBLIC_PREFIXES) and path.rstrip("/") not in _AUTH_REQUIRED_PATHS
    ):
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
    if not user and os.getenv("DEV_MODE", "0") == "1" and is_loopback_client(request):
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
    if hidden_upload:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
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


async def _check_health() -> list[str]:
    """检查本机持久化状态，只收集检查项名称。"""
    from agent_store import MIGRATION_VERSION
    from exchange_store import (
        MIGRATION_VERSION as EXCHANGE_MIGRATION_VERSION,
        OFFICIAL_MIGRATION_VERSION,
        EXTENDED_OFFICIAL_MIGRATION_VERSION,
        WORKFLOW_MIGRATION_VERSION,
    )

    expected_versions = {
        MIGRATION_VERSION,
        EXCHANGE_MIGRATION_VERSION,
        OFFICIAL_MIGRATION_VERSION,
        EXTENDED_OFFICIAL_MIGRATION_VERSION,
        WORKFLOW_MIGRATION_VERSION,
    }
    failed = []
    try:
        if not os.access(database.DB_PATH, os.W_OK):
            raise PermissionError("database is not writable")
        uri = Path(database.DB_PATH).resolve().as_uri() + "?mode=rw"
        async with aiosqlite.connect(uri, uri=True, timeout=1.0) as db:
            try:
                async with db.execute("SELECT version FROM schema_migrations") as cursor:
                    versions = {row[0] for row in await cursor.fetchall()}
                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
                ) as cursor:
                    users_exists = await cursor.fetchone() is not None
                if not expected_versions.issubset(versions) or not users_exists:
                    failed.append("schema")
            except Exception:
                failed.append("schema")
    except Exception:
        failed.append("database")
    if not os.path.isdir(media.UPLOADS_DIR) or not os.access(media.UPLOADS_DIR, os.W_OK):
        failed.append("uploads")
    return failed


@app.get("/health")
@app.head("/health")
async def health():
    """在总时限内检查本机持久化状态，只返回检查项名称。"""
    try:
        failed = await asyncio.wait_for(_check_health(), timeout=_HEALTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        failed = ["database"]
    if failed:
        return JSONResponse({"status": "error", "failed": failed}, status_code=503)
    return {"status": "ok"}
