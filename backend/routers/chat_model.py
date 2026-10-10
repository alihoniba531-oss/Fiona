"""Private per-account model settings; credentials never enter public schemas."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from auth_dep import get_current_user
from byok.crypto import availability
from byok.errors import (ByokUnavailableError, ConfigurationError, ConfigNotFoundError,
                         NeedsReentryError, error_message)
from byok.providers import public_provider_metadata, validate_effort
from byok.store import delete_config, get_public_config, prepare_config, save_config, update_options
from rate_limit import check_chat_daily_cap, limiter
from services.chat_service import run_byok_connection_test


router = APIRouter(prefix="/chat-model", tags=["chat-model"])
_HEADERS = {"Cache-Control": "private, no-store"}
_DRAFT_FIELDS = {"provider", "model", "base_url", "api_key"}


class ModelDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ModelSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool | None = None
    effort: str | None = None


def _response(body, status=200):
    return JSONResponse(body, status_code=status, headers=_HEADERS)


async def _body(request: Request, *, test=False, patch=False):
    # Parse outside Pydantic: its default validation payload echoes input Key.
    try:
        body = await request.json()
    except Exception:
        raise ConfigurationError("请求格式不正确") from None
    fields = {"enabled", "effort"} if patch else _DRAFT_FIELDS
    if not isinstance(body, dict) or set(body) - fields:
        raise ConfigurationError("请求格式不正确")
    if patch:
        if not body:
            raise ConfigurationError("请求格式不正确")
        if "effort" in body:
            validate_effort(body["effort"])
    try:
        parsed = (ModelSwitch if patch else ModelDraft).model_validate(body)
    except ValidationError:
        message = "Key 格式不正确" if "api_key" in body and not isinstance(body["api_key"], (str, type(None))) else "请求格式不正确"
        raise ConfigurationError(message) from None
    if patch and "enabled" in body and parsed.enabled is None:
        raise ConfigurationError("启用状态格式不正确")
    if not patch and not test and (parsed.provider is None or parsed.model is None):
        raise ConfigurationError("请填写厂商和模型名")
    return parsed.model_dump(exclude_unset=True)


def _error(exc):
    if isinstance(exc, ByokUnavailableError):
        return _response({"detail": "服务器暂未开启自带模型"}, 503)
    if isinstance(exc, ConfigNotFoundError):
        return _response({"detail": "尚未配置自带模型"}, 404)
    if isinstance(exc, ConfigurationError):
        # ConfigurationError is exclusively raised with fixed local messages.
        return _response({"detail": exc.args[0] if exc.args else "请求格式不正确"}, 400)
    if isinstance(exc, NeedsReentryError):
        return _response({"detail": "配置需要重新填写 Key"}, 400)
    return _response({"detail": "自带模型配置暂时不可用"}, 503)


@router.get("")
async def get_chat_model(user: str = Depends(get_current_user)):
    available, reason = availability()
    try:
        config = await get_public_config(user)
    except Exception as exc:
        return _error(exc)
    payload = {"available": available, "providers": public_provider_metadata(), "config": config}
    if not available:
        payload["unavailable_reason"] = reason or "服务器暂未开启自带模型"
    return _response(payload)


@router.put("")
@limiter.limit("10/minute")
async def put_chat_model(request: Request, user: str = Depends(get_current_user)):
    try:
        body = await _body(request)
        config = await save_config(user, **body)
        return _response({"config": config})
    except Exception as exc:
        return _error(exc)


@router.patch("")
@limiter.limit("10/minute")
async def patch_chat_model(request: Request, user: str = Depends(get_current_user)):
    try:
        body = await _body(request, patch=True)
        config = await update_options(user, **body)
        return _response({"config": config})
    except Exception as exc:
        return _error(exc)


@router.delete("")
@limiter.limit("10/minute")
async def delete_chat_model(request: Request, user: str = Depends(get_current_user)):
    try:
        await delete_config(user)
        return Response(status_code=204, headers=_HEADERS)
    except Exception as exc:
        return _error(exc)


@router.post("/test")
@limiter.limit("10/minute")
async def test_chat_model(request: Request, user: str = Depends(get_current_user)):
    try:
        body = await _body(request, test=True)
        config = await prepare_config(user, **body)
        message = check_chat_daily_cap("byok_test", user, hit=True)
        if message:
            return _response({"ok": False, "message": message})
        await run_byok_connection_test(config)
        return _response({"ok": True, "message": "连接成功"})
    except Exception as exc:
        # Test failures are always a successful HTTP response, without secrets.
        message = exc.args[0] if isinstance(exc, ConfigurationError) and exc.args else error_message(exc)
        return _response({"ok": False, "message": message})
