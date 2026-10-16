"""Private account controls and scoped bearer-token endpoints for Mac watchers."""
from collections import deque
from datetime import datetime
import hashlib
import math
import os
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response

from auth_dep import get_current_user
import database
import rate_limit
from byok import store as byok_store
from services.local_watch import process_observation

_HEADERS = {"Cache-Control": "private, no-store"}
_windows = {}
_capture_states = {}
_recent_heartbeats = {}
_observation_rates = {}
_heartbeat_rates = {}
_authentication_failure_rates = {}


def count_device_request(rates, identifier, limit, message):
    """Count before body parsing, scoped to this database and client/device."""
    now = time.monotonic()
    for key in list(rates):
        if not rates[key] or now - rates[key][-1] >= 60:
            del rates[key]
    key = (str(database.DB_PATH), identifier)
    recent = rates.setdefault(key, deque())
    while recent and now - recent[0] >= 60:
        recent.popleft()
    if len(recent) >= limit:
        retry_after = max(1, math.ceil(60 - (now - recent[0])))
        raise HTTPException(429, message, headers={**_HEADERS, "Retry-After": str(retry_after)})
    recent.append(now)


def authentication_failed(request):
    client_ip = rate_limit._client_ip(request)
    count_device_request(_authentication_failure_rates, client_ip, 30, "设备鉴权失败过于频繁")
    raise HTTPException(401, "设备令牌无效", headers=_HEADERS)


def require_enabled():
    if os.getenv("FIONA_LOCAL_WATCH", "1") == "0":
        raise HTTPException(404, "Not Found", headers=_HEADERS)


router = APIRouter(prefix="/local-watch", tags=["local-watch"], dependencies=[Depends(require_enabled)])


def invalid(message="请求参数不正确"):
    raise HTTPException(422, message, headers=_HEADERS)


async def body(request, fields):
    try:
        value = await request.json()
    except Exception:
        invalid()
    if not isinstance(value, dict) or set(value) - fields:
        invalid()
    return value


def text(value, minimum, maximum):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        invalid()
    return value


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        invalid()
    return value


def capture_statuses(value):
    """Reject invalid containers, discard invalid entries; first valid rule wins."""
    if not isinstance(value, list) or len(value) > 20:
        invalid()
    result = {}
    for status in value:
        try:
            if not isinstance(status, dict) or set(status) != {"rule_id", "ok", "error", "since"}:
                invalid()
            rule_id = integer(status["rule_id"], 1, 2**63 - 1)
            if type(status["ok"]) is not bool:
                invalid()
            error = status["error"]
            if error is not None:
                text(error, 1, 200)
            if status["ok"] and error is not None:
                invalid()
            since = text(status["since"], 1, 80)
            instant = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                invalid()
        except (HTTPException, ValueError):
            continue
        if rule_id in result:
            continue
        result[rule_id] = {"ok": status["ok"], "error": error, "since": since}
    return result


def capture_message(status):
    if status["ok"]:
        return "监控中"
    error = status["error"]
    if error == "window_not_found":
        return "没有找到匹配的窗口（窗口可能已关闭或最小化）"
    domain = error.partition("/")[0] if error else ""
    # 真机上报的是带前缀的完整错误域，例如
    # com.apple.ScreenCaptureKit.SCStreamErrorDomain，只比较最后一段。
    short = domain.rpartition(".")[2]
    if short in {"SCStream", "SCStreamErrorDomain", "SCErrorDomain", "SCScreenshotErrorDomain"} or "ScreenCaptureKit" in domain:
        return "截图失败：屏幕可能已锁定或显示器已休眠，也可能缺少屏幕录制权限"
    return "截图失败，请查看监控程序日志"


def expire_capture_states(now):
    for key in list(_capture_states):
        if now - _capture_states[key][0] >= 300:
            del _capture_states[key]
    for key in list(_recent_heartbeats):
        if now - _recent_heartbeats[key] >= 300:
            del _recent_heartbeats[key]


def capture_display(status):
    """Keep capture error mapping separate from an initial neutral state."""
    if not status["ok"] and status["error"] is None:
        return {"ok": False, "neutral": True, "message": "等待首次截图", "since": status["since"]}
    return {"ok": status["ok"], "message": capture_message(status), "since": status["since"]}


async def rule_capture_states(username, rule_ids=()):
    """Only current active devices can supply state, scoped to this database."""
    expire_capture_states(time.monotonic())
    owner = (str(database.DB_PATH), username)
    cached = [(key, value) for key, value in _capture_states.items() if key[:2] == owner]
    recent = [key for key in _recent_heartbeats if key[:2] == owner]
    if not cached and not recent:
        return {}
    active = set()
    if await database.get_session_version(username) is not None:
        active = {device["id"] for device in await database.list_watch_devices(username) if not device["revoked"]}
    recent = [key for key in recent if key[2] in active]
    for key in list(_recent_heartbeats):
        if key[:2] == owner and key[2] not in active:
            del _recent_heartbeats[key]
    latest = {}
    for key, (received_at, statuses) in cached:
        if key[2] not in active:
            _capture_states.pop(key, None)
            continue
        for rule_id, status in statuses.items():
            if rule_id not in latest or received_at >= latest[rule_id][0]:
                latest[rule_id] = (received_at, status)
    result = {rule_id: capture_display(status) for rule_id, (_, status) in latest.items()}
    if recent:
        for rule_id in rule_ids:
            result.setdefault(rule_id, {"ok": False, "neutral": True, "message": "等待首次截图"})
    return result


async def validate_rule(value):
    result = dict(value)
    result["name"] = text(value.get("name"), 1, 30)
    result["app_match"] = text(value.get("app_match", ""), 0, 60)
    result["title_match"] = text(value.get("title_match", ""), 0, 60)
    if not result["name"].strip() or not (result["app_match"].strip() or result["title_match"].strip()):
        invalid()
    result["interval_seconds"] = integer(value.get("interval_seconds", 3), 2, 60)
    result["cooldown_seconds"] = integer(value.get("cooldown_seconds", 60), 10, 3600)
    result["enabled"] = value.get("enabled", True)
    if type(result["enabled"]) is not bool:
        invalid()
    result["conversation_id"] = value.get("conversation_id")
    if result["conversation_id"] is not None:
        text(result["conversation_id"], 0, 200)
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in {"keyword", "number", "ai"}:
        invalid()
    params = value.get("params")
    if not isinstance(params, dict):
        invalid()
    if kind == "keyword":
        if set(params) != {"keywords"} or not isinstance(params["keywords"], list) or not 1 <= len(params["keywords"]) <= 10:
            invalid()
        for keyword in params["keywords"]:
            if not text(keyword, 1, 20).strip(): invalid()
    elif kind == "number":
        if set(params) != {"label", "op", "threshold"}:
            invalid()
        if not text(params["label"], 1, 20).strip() or not isinstance(params["op"], str) or params["op"] not in {">", ">=", "<", "<="}:
            invalid()
        threshold = params["threshold"]
        if type(threshold) not in {int, float}:
            invalid()
        try:
            if not math.isfinite(threshold): invalid()
        except OverflowError:
            invalid()
    else:
        if set(params) - {"condition", "model"} or "condition" not in params:
            invalid()
        if not text(params["condition"], 2, 200).strip(): invalid()
        params = dict(params)
        params.setdefault("model", "platform")
        if not isinstance(params["model"], str) or params["model"] not in {"platform", "claude"}: invalid()
    result["params"] = params
    return result


_RULE_FIELDS = {"name", "app_match", "title_match", "kind", "params", "interval_seconds", "cooldown_seconds", "enabled", "conversation_id"}


async def validate_claude(user, rule):
    if rule["kind"] != "ai" or rule["params"].get("model") != "claude":
        return
    try:
        config = await byok_store.get_internal_config(user)
    except Exception:
        invalid("需要启用可用的 Anthropic 自带模型")
    if not config or not config.get("enabled") or config.get("provider") != "anthropic" or not config.get("api_key") or config.get("status") != "ok":
        invalid("需要启用可用的 Anthropic 自带模型")


async def current_device(request: Request, authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 256:
        authentication_failed(request)
    token = authorization[7:]
    device = await database.authenticate_watch_device_throttled(hashlib.sha256(token.encode()).hexdigest())
    if device is None:
        authentication_failed(request)
    return device


@router.post("/devices")
async def create_device(request: Request, user=Depends(get_current_user)):
    value = await body(request, {"name"})
    name = text(value.get("name", "Mac"), 0, 80)
    token = secrets.token_bytes(32).hex()
    try:
        device = await database.create_watch_device(user, hashlib.sha256(token.encode()).hexdigest(), name)
    except ValueError as exc:
        raise HTTPException(400, str(exc), headers=_HEADERS) from None
    return JSONResponse({**device, "token": token}, headers=_HEADERS)


@router.get("/devices")
async def list_devices(user=Depends(get_current_user)):
    return JSONResponse(await database.list_watch_devices(user), headers=_HEADERS)


@router.delete("/devices/{device_id}")
async def revoke_device(device_id: int = Path(ge=1, le=2**63 - 1), user=Depends(get_current_user)):
    if not await database.revoke_watch_device(user, device_id):
        raise HTTPException(404, "设备不存在", headers=_HEADERS)
    _capture_states.pop((str(database.DB_PATH), user, device_id), None)
    _recent_heartbeats.pop((str(database.DB_PATH), user, device_id), None)
    return Response(status_code=204, headers=_HEADERS)


@router.get("/rules")
async def list_rules(user=Depends(get_current_user)):
    rules = await database.list_watch_rules(user)
    captures = await rule_capture_states(user, (rule["id"] for rule in rules))
    return JSONResponse([{**rule, "capture": ({"ok": False, "neutral": True, "message": "已停用"} if not rule["enabled"]
                         else captures.get(rule["id"], {"ok": False, "message": "监控程序未在运行"}))}
                         for rule in rules], headers=_HEADERS)


@router.post("/rules")
async def create_rule(request: Request, user=Depends(get_current_user)):
    rule = await validate_rule(await body(request, _RULE_FIELDS))
    await validate_claude(user, rule)
    try:
        result = await database.create_watch_rule(user, rule)
    except ValueError as exc:
        raise HTTPException(400, str(exc), headers=_HEADERS) from None
    return JSONResponse(result, headers=_HEADERS)


@router.patch("/rules/{rule_id}")
async def patch_rule(request: Request, rule_id: int = Path(ge=1, le=2**63 - 1), user=Depends(get_current_user)):
    previous = await database.get_watch_rule(user, rule_id)
    if previous is None:
        raise HTTPException(404, "规则不存在", headers=_HEADERS)
    updates = await body(request, _RULE_FIELDS)
    if not updates: invalid()
    rule = await validate_rule({**{key: previous[key] for key in _RULE_FIELDS}, **updates})
    # Turning an unavailable Claude rule off must always remain possible.
    if rule["enabled"] or "params" in updates or "kind" in updates:
        await validate_claude(user, rule)
    result = await database.update_watch_rule(user, rule_id, rule)
    if result is None:
        raise HTTPException(404, "规则不存在", headers=_HEADERS)
    return JSONResponse(result, headers=_HEADERS)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int = Path(ge=1, le=2**63 - 1), user=Depends(get_current_user)):
    if not await database.delete_watch_rule(user, rule_id):
        raise HTTPException(404, "规则不存在", headers=_HEADERS)
    return Response(status_code=204, headers=_HEADERS)


@router.get("/windows")
async def list_windows(user=Depends(get_current_user)):
    value = _windows.get(user)
    if value is None or time.monotonic() - value[0] >= 300:
        _windows.pop(user, None)
        return JSONResponse([], headers=_HEADERS)
    return JSONResponse(value[1], headers=_HEADERS)


@router.get("/alerts")
async def list_alerts(after: int = Query(default=0, ge=0, le=2**63 - 1), user=Depends(get_current_user)):
    return JSONResponse(await database.list_watch_alerts_with_content(user, after), headers=_HEADERS)


@router.post("/heartbeat")
async def heartbeat(request: Request, device=Depends(current_device)):
    count_device_request(_heartbeat_rates, device["id"], 10, "设备心跳过于频繁")
    value = await body(request, {"windows", "capture_status"})
    windows = value.get("windows")
    if not isinstance(windows, list) or len(windows) > 200: invalid()
    sanitized = []
    for window in windows:
        if not isinstance(window, dict) or set(window) - {"window_id", "app_name", "bundle_id", "title"}: invalid()
        if "window_id" in window: integer(window["window_id"], 0, 2**32 - 1)
        sanitized.append({"app_name": text(window.get("app_name", ""), 0, 200), "bundle_id": text(window.get("bundle_id", ""), 0, 200), "title": text(window.get("title", ""), 0, 10000)[:80]})
    captures = capture_statuses(value["capture_status"]) if "capture_status" in value else {}
    rules = await database.list_watch_rules(device["username"], enabled_only=True)
    enabled_ids = {rule["id"] for rule in rules}
    captures = {rule_id: status for rule_id, status in captures.items() if rule_id in enabled_ids}
    now = time.monotonic()
    for username in list(_windows):
        if now - _windows[username][0] >= 300: del _windows[username]
    _windows[device["username"]] = (now, sanitized)
    expire_capture_states(now)
    key = (str(database.DB_PATH), device["username"], device["id"])
    _recent_heartbeats[key] = now
    # Replace only this device's snapshot. Reinsertion orders equal clock ticks.
    _capture_states.pop(key, None)
    if captures:
        _capture_states[key] = (now, captures)
    return JSONResponse({"rules": [{key: rule[key] for key in ("id", "app_match", "title_match", "interval_seconds")} for rule in rules]}, headers=_HEADERS)


@router.post("/observations")
async def observations(request: Request, device=Depends(current_device)):
    count_device_request(_observation_rates, device["id"], 60, "设备上报过于频繁")
    value = await body(request, {"rule_id", "new_lines", "captured_at"})
    rule_id = integer(value.get("rule_id"), 1, 2**63 - 1)
    lines = value.get("new_lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 50 or any(not isinstance(line, str) for line in lines): invalid()
    if sum(len(line) for line in lines) > 4000: invalid()
    try:
        instant = datetime.fromisoformat(text(value.get("captured_at"), 1, 80).replace("Z", "+00:00"))
        if instant.tzinfo is None: invalid()
    except ValueError:
        invalid()
    rule = await database.get_watch_rule(device["username"], rule_id)
    if rule is None or not rule["enabled"]:
        raise HTTPException(404, "规则不存在或未启用", headers=_HEADERS)
    now = time.monotonic()
    app_name = None
    cached = _windows.get(device["username"])
    if cached and now - cached[0] < 300:
        for window in cached[1]:
            if ((rule["app_match"].casefold() in window["app_name"].casefold()
                    or rule["app_match"].casefold() in window["bundle_id"].casefold())
                    and rule["title_match"].casefold() in window["title"].casefold()):
                app_name = window["app_name"] or None
                break
    return JSONResponse(await process_observation(device["username"], rule, lines, app_name=app_name), headers=_HEADERS)
