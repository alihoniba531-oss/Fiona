"""视频供应商的单次付费传输与只读状态查询。"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from typing import Any

import httpx


UNCERTAIN_MESSAGE = "可能已扣费，请勿直接重试，去控制台核对"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _reject_json_constant(value: str):
    raise ValueError("invalid_json_constant")


class ProviderError(Exception):
    def __init__(self, status: str, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Submission:
    task_id: str
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PollResult:
    status: str
    usage: dict[str, Any] = field(default_factory=dict)
    result_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def safe_message(value: Any) -> str:
    """保留上游说明，但密钥和内联图片不能进入持久化错误文本。"""
    result = str(value or "上游未提供错误说明")
    for name in ("ARK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID"):
        secret = os.getenv(name, "").strip()
        if secret:
            result = result.replace(secret, "[已隐藏]")
    result = re.sub(r"data:[^,\s]*,[A-Za-z0-9+/=_-]+", "[图片已隐藏]", result, flags=re.I)
    return result[:2000]


def error_details(data: Any, fallback: str) -> tuple[str, str]:
    if not isinstance(data, dict):
        return fallback, safe_message(data)
    detail = data.get("error") or data.get("output") or data
    if not isinstance(detail, dict):
        return fallback, safe_message(detail)
    code = detail.get("code") or detail.get("error_code") or data.get("code") or fallback
    message = detail.get("message") or detail.get("error_message") or data.get("message")
    return safe_message(code), safe_message(message)


def response_usage(data: dict) -> dict:
    usage = data.get("usage")
    if usage is None and isinstance(data.get("output"), dict):
        usage = data["output"].get("usage")
    return usage if isinstance(usage, dict) else {}


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ProviderError("failed", "missing_configuration", f"未设置 {name}，没有提交生成请求")
    return value


class VideoProvider:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def _json(self, method: str, url: str, headers: dict, body: dict | None = None) -> dict:
        paid = method == "POST"
        # stream 的完整读取发生在状态判定之前；4xx 响应读到一半仍然是不确定。
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(120 if paid else 30, connect=10, write=30, pool=10),
                trust_env=False,
                follow_redirects=False,
            ) as client:
                async with client.stream(method, url, headers=headers, json=body) as response:
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ValueError("response_too_large")
                        chunks.extend(chunk)
                    declared = response.headers.get("content-length")
                    if declared is not None and not response.headers.get("content-encoding"):
                        if int(declared) != len(chunks):
                            raise ValueError("incomplete_response")
                    try:
                        data = json.loads(chunks, parse_constant=_reject_json_constant)
                    except (ValueError, UnicodeError):
                        data = bytes(chunks).decode("utf-8", errors="replace")
                    status = response.status_code
                    if paid and 400 <= status < 500:
                        code, message = error_details(data, f"HTTP_{status}")
                        raise ProviderError("rejected", code, message)
                    if not 200 <= status < 300:
                        code, _ = error_details(data, f"HTTP_{status}")
                        raise ProviderError(
                            "uncertain" if paid else "poll_error", code,
                            UNCERTAIN_MESSAGE if paid else f"任务状态查询返回 HTTP {status}，稍后重查",
                        )
                    if not isinstance(data, dict):
                        raise ProviderError(
                            "uncertain" if paid else "poll_error", "invalid_json",
                            UNCERTAIN_MESSAGE if paid else "任务状态响应不是有效 JSON 对象，稍后重查",
                        )
                    return data
        except ProviderError:
            raise
        except Exception:
            # 不重试 POST，也不复制传输异常正文（可能含请求内容和密钥）。
            raise ProviderError(
                "uncertain" if paid else "poll_error", "transport_error",
                UNCERTAIN_MESSAGE if paid else "任务状态查询中断，稍后重查",
            ) from None

    async def submit(self, params: dict, image_path) -> Submission:
        raise NotImplementedError

    async def poll(self, task_id: str) -> PollResult:
        raise NotImplementedError
