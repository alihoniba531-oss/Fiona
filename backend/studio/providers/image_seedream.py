# -*- coding: utf-8 -*-
"""Seedream 5.0 定妆出图：单次付费 POST，绝不自动重试。

请求体复刻 ``backend/tools/image_generation.py`` 的 ARK 分支（model / prompt /
size / response_format / output_format / watermark，参考图字段为 image），
错误按块 B 约定归类到 ``MediaCallError``：明确的 4xx（含 429）→ rejected；
超时、断连、重定向、5xx、2xx 解析失败、返回尺寸与请求不符 → uncertain；
上游内容审核拒绝 → failed。

``generate_sheet`` 除单次 POST 超时外还有整体超时 ``TOTAL_TIMEOUT_S``（含建连、
上传参考图、读满响应与解码），整体超时同样按 uncertain 处理。
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass
import json
import os
import re
import struct

import httpx

from .base import UNCERTAIN_MESSAGE, safe_message
from .media_errors import MediaCallError


GENERATION_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-flash-260915"
MODEL_ENV = "SEEDREAM_IMAGE_MODEL"
API_KEY_ENV = "ARK_API_KEY"

# POST 单次总超时，与 image_generation.py 的 _TIMEOUT_SECONDS 一致。
_TIMEOUT_SECONDS = 150
# generate_sheet 的整体超时（秒）：覆盖建连、上传参考图、读满响应与解码。
# 超时可能已经扣费，按 uncertain 处理，不重试。
TOTAL_TIMEOUT_S = 240.0
_MAX_RESPONSE_BYTES = 40 * 1024 * 1024
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MIN_PIXELS = 921600
_MAX_PIXELS = 2048 * 2048

_SIZE_PATTERN = re.compile(r"([1-9][0-9]*)[xX]([1-9][0-9]*)")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MODERATION_MARKERS = (
    "sensitivecontentdetected", "riskdetection", "policyviolation",
    "privacyinformation", "deepfake", "moderation",
)


@dataclass
class SeedreamResult:
    png: bytes
    width: int
    height: int
    model: str
    usage: dict


def _safe_code(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "", str(value or ""))[:80]


def _is_moderation(code: str) -> bool:
    lowered = code.lower()
    return any(marker in lowered for marker in _MODERATION_MARKERS)


def _moderation_error(code: str) -> MediaCallError:
    return MediaCallError(
        "failed", _safe_code(code) or "moderation_blocked",
        "描述或参考图未通过内容审核，请修改后再试。",
    )


def _upstream_error(data: object) -> tuple[str, str]:
    """取出上游错误码与说明；说明先脱敏（密钥、内联图片不得进入错误文本）。"""
    if not isinstance(data, dict):
        return "", safe_message(data)
    detail = data.get("error")
    if not isinstance(detail, dict):
        detail = data
    code = detail.get("code") or detail.get("error_code") or data.get("code")
    message = detail.get("message") or detail.get("error_message") or data.get("message")
    return str(code or ""), safe_message(message)


def _http_error(status: int, data: object) -> MediaCallError:
    """把非 2xx 响应归类；上游错误码命中内容审核时一律 failed。"""
    code, message = _upstream_error(data)
    if _is_moderation(code):
        return _moderation_error(code)
    if 400 <= status < 500:
        detail = f" 上游说明：{message}" if message else ""
        return MediaCallError("rejected", f"http_{status}", f"上游拒绝本次出图（HTTP {status}）。{detail}".strip())
    if status >= 500:
        return MediaCallError("uncertain", "http_5xx", UNCERTAIN_MESSAGE)
    # 3xx（重定向未被跟随）与其余异常状态都按「可能已扣费」处理。
    return MediaCallError("uncertain", f"http_{status}", UNCERTAIN_MESSAGE)


def _parse_size(size: object) -> tuple[int, int]:
    """校验 WxH 格式、比例（1/16..16）与像素范围，与 image_generation.py 一致。"""
    match = _SIZE_PATTERN.fullmatch(size) if isinstance(size, str) else None
    if match is None:
        raise MediaCallError("failed", "invalid_size", "定妆图尺寸须为 宽x高，例如 2560x1440。")
    width, height = int(match.group(1)), int(match.group(2))
    if not 1 / 16 <= width / height <= 16:
        raise MediaCallError("failed", "invalid_size", "定妆图比例超出 Seedream 支持范围（1:16 至 16:1）。")
    if not _MIN_PIXELS <= width * height <= _MAX_PIXELS:
        raise MediaCallError("failed", "invalid_size", "定妆图像素超出 Seedream 支持范围（92.16 万至 419.43 万）。")
    return width, height


def _reference_uris(reference_images: object) -> list[str]:
    if reference_images is None:
        return []
    if not isinstance(reference_images, (list, tuple)):
        raise MediaCallError("failed", "invalid_reference_image", "参考图无效，没有提交出图请求。")
    uris = []
    for item in reference_images:
        if not isinstance(item, (bytes, bytearray)) or not item:
            raise MediaCallError("failed", "invalid_reference_image", "参考图无效，没有提交出图请求。")
        uris.append("data:image/png;base64," + base64.b64encode(bytes(item)).decode("ascii"))
    return uris


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """只读 PNG 头拿真实宽高；不是 PNG 或头部不完整返回 None。"""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


async def _read_bounded(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) < 0 or int(declared) > _MAX_RESPONSE_BYTES:
                raise MediaCallError("uncertain", "response_too_large", UNCERTAIN_MESSAGE)
        except ValueError:
            raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE) from None
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
            raise MediaCallError("uncertain", "response_too_large", UNCERTAIN_MESSAGE)
        body.extend(chunk)
    return bytes(body)


def _decode_png(data: dict, width: int, height: int) -> bytes:
    images = data.get("data")
    first = images[0] if isinstance(images, list) and images and isinstance(images[0], dict) else {}
    encoded = first.get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        image_code, _ = _upstream_error(first)
        if _is_moderation(image_code):
            raise _moderation_error(image_code)
        raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE)
    try:
        png = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE) from None
    if not png or len(png) > _MAX_IMAGE_BYTES:
        raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE)
    actual = _png_dimensions(png)
    if actual is None:
        raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE)
    if actual != (width, height):
        raise MediaCallError("uncertain", "size_mismatch", UNCERTAIN_MESSAGE)
    return png


async def _generate_sheet(
    prompt: str, *, size: str, reference_images: list[bytes],
    model: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
) -> SeedreamResult:
    """单次 POST 的实现体；整体超时由 ``generate_sheet`` 用 ``asyncio.wait_for`` 施加。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise MediaCallError("failed", "invalid_prompt", "定妆提示词为空，没有提交出图请求。")
    width, height = _parse_size(size)
    resolved_model = (model.strip() if isinstance(model, str) else "") or os.getenv(MODEL_ENV, "").strip() or DEFAULT_MODEL
    api_key = os.getenv(API_KEY_ENV, "").strip()
    if not api_key:
        raise MediaCallError("failed", "missing_configuration", f"未设置 {API_KEY_ENV}，没有提交出图请求。")
    uris = _reference_uris(reference_images)
    body = {
        "model": resolved_model,
        "prompt": prompt,
        "size": f"{width}x{height}",
        "response_format": "b64_json",
        "output_format": "png",
        "watermark": False,
    }
    if uris:
        # 单张传字符串、多张传列表，与探针和 image_generation.py 的 image 字段一致。
        body["image"] = uris[0] if len(uris) == 1 else uris
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(_TIMEOUT_SECONDS, connect=10, write=15, pool=10)
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=timeout, trust_env=False, follow_redirects=False,
        ) as client:
            async with client.stream("POST", GENERATION_URL, headers=headers, json=body) as response:
                status = response.status_code
                raw = await _read_bounded(response)
    except MediaCallError:
        raise
    except Exception:
        # 不重试，也不复制可能含请求内容的传输异常正文。
        raise MediaCallError("uncertain", "transport_error", UNCERTAIN_MESSAGE) from None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        if 200 <= status < 300:
            raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE) from None
        raise _http_error(status, {}) from None
    if not isinstance(data, dict):
        if 200 <= status < 300:
            raise MediaCallError("uncertain", "invalid_response", UNCERTAIN_MESSAGE)
        raise _http_error(status, {})
    if not 200 <= status < 300:
        raise _http_error(status, data)
    # 少数实现把审核结论放在 2xx 正文里，同样按 failed 处理。
    top_code, _ = _upstream_error(data)
    if _is_moderation(top_code):
        raise _moderation_error(top_code)
    png = _decode_png(data, width, height)
    usage = data.get("usage")
    return SeedreamResult(
        png=png, width=width, height=height, model=resolved_model,
        usage=usage if isinstance(usage, dict) else {},
    )


async def generate_sheet(
    prompt: str, *, size: str, reference_images: list[bytes],
    model: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
) -> SeedreamResult:
    """生成一张定妆图；只发一次 POST，失败按 status 交由块 A 处置预留。

    整体超时 ``TOTAL_TIMEOUT_S``：超时视为 uncertain（可能已扣费），不重试。
    """
    try:
        return await asyncio.wait_for(
            _generate_sheet(prompt, size=size, reference_images=reference_images,
                            model=model, transport=transport),
            timeout=TOTAL_TIMEOUT_S,
        )
    except (TimeoutError, asyncio.TimeoutError):
        raise MediaCallError("uncertain", "timeout", UNCERTAIN_MESSAGE) from None
