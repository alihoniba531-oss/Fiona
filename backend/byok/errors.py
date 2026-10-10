"""Public BYOK failures are fixed messages, never provider response bodies."""
from __future__ import annotations

import anthropic
import httpx
import httpx2
import openai


class ConfigurationError(ValueError):
    pass


class ConfigNotFoundError(ConfigurationError):
    def __init__(self):
        super().__init__("尚未配置自带模型")


class UserDeletedError(ConfigurationError):
    def __init__(self):
        super().__init__("账号不存在")


class NeedsReentryError(Exception):
    pass


class ByokUnavailableError(Exception):
    pass


class ByokTimeoutError(TimeoutError):
    pass


class EmptyReplyError(Exception):
    pass


class RefusalError(Exception):
    pass


_ERROR_TEXT = {
    "authentication": "Key 无效或没有权限", "not_found": "模型名或地址不存在",
    "quota": "额度不足或请求过于频繁", "bad_request": "请求参数不被接受",
    "timeout": "响应超时", "connection": "连不上该服务",
    "refusal": "模型拒绝回答这条消息", "empty": "模型没有返回内容",
    "needs_reentry": "配置需要重新填写 Key", "unavailable": "服务器暂未开启自带模型",
    "other": "调用失败", "busy": "服务繁忙，请稍后再试",
}


def error_category(exc: BaseException) -> str:
    # Name checks also support the two SDKs without mixing their HTTP clients.
    if isinstance(exc, NeedsReentryError):
        return "needs_reentry"
    if isinstance(exc, ByokUnavailableError):
        return "unavailable"
    if isinstance(exc, RefusalError):
        return "refusal"
    if isinstance(exc, EmptyReplyError):
        return "empty"
    if isinstance(exc, ConfigurationError):
        return "bad_request"
    name = type(exc).__name__
    if isinstance(exc, TimeoutError) or name in {"APITimeoutError", "TimeoutException", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout"}:
        return "timeout"
    status = getattr(exc, "status_code", None)
    if isinstance(exc, anthropic.APIError):
        body = exc.body
        kind = body.get("type") if isinstance(body, dict) else None
        nested = body.get("error") if isinstance(body, dict) else None
        if status == 529 or name == "OverloadedError" or kind == "overloaded_error" or (isinstance(nested, dict) and nested.get("type") == "overloaded_error"):
            return "busy"
    if name in {"AuthenticationError", "PermissionDeniedError"} or status in {401, 403}:
        return "authentication"
    if name == "NotFoundError" or status == 404:
        return "not_found"
    if name == "RateLimitError" or status in {402, 429} or (isinstance(exc, openai.APIError) and isinstance(exc.code, str) and exc.code in {"insufficient_quota", "rate_limit_exceeded", "billing_not_active"}):
        return "quota"
    if name == "BadRequestError" or status == 400:
        return "bad_request"
    if isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError, httpx2.NetworkError, httpx2.RemoteProtocolError)) or name in {"APIConnectionError", "UnsafeUrlError", "ConnectError", "NetworkError"}:
        return "connection"
    return "other"


def error_message(exc: BaseException) -> str:
    return f"你的模型调用失败：{_ERROR_TEXT[error_category(exc)]}。本条没有改用平台模型。"
