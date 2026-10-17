# -*- coding: utf-8 -*-
"""Seedream 定妆出图适配器：只用 MockTransport，绝不访问真实接口。"""
import asyncio
import base64
import io
import json

import httpx
from PIL import Image
import pytest

from studio.providers import image_seedream
from studio.providers.image_seedream import (
    DEFAULT_MODEL, GENERATION_URL, SeedreamResult, generate_sheet,
)
from studio.providers.media_errors import MediaCallError


SHEET_SIZE = "2560x1440"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def ark_key(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "offline-ark-key")
    monkeypatch.delenv("SEEDREAM_IMAGE_MODEL", raising=False)
    return "offline-ark-key"


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "#405060").save(buffer, format="PNG")
    return buffer.getvalue()


def _success_payload(png: bytes, *, usage: dict | None = None) -> dict:
    return {
        "model": DEFAULT_MODEL,
        "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
        "usage": usage if usage is not None else {"generated_images": 1, "total_tokens": 8100},
    }


def _post_body(request: httpx.Request) -> dict:
    return json.loads(request.content.decode("utf-8"))


async def _expect_error(status: str, code: str | None, coro_kwargs: dict, transport) -> MediaCallError:
    with pytest.raises(MediaCallError) as caught:
        await generate_sheet(**coro_kwargs, transport=transport)
    assert caught.value.status == status
    if code is not None:
        assert caught.value.code == code
    return caught.value


def _calls(handler):
    """把一个 MockTransport handler 包装成可计数的 handler。"""
    requests: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return wrapped, requests


# --------------------------------------------------------------------------- #
# 请求契约：单次 POST、URL、鉴权、请求体字段
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
async def test_single_post_and_request_body(ark_key):
    png = _png(2560, 1440)
    def handler(request):
        return httpx.Response(200, json=_success_payload(png))

    wrapped, requests = _calls(handler)
    result = await generate_sheet(
        "三视图定妆：正面、侧面、背面", size=SHEET_SIZE, reference_images=[],
        transport=httpx.MockTransport(wrapped),
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == GENERATION_URL
    assert request.headers["Authorization"] == f"Bearer {ark_key}"
    assert request.headers["Content-Type"] == "application/json"
    body = _post_body(request)
    assert set(body) == {"model", "prompt", "size", "response_format", "output_format", "watermark"}
    assert body["model"] == DEFAULT_MODEL
    assert body["prompt"] == "三视图定妆：正面、侧面、背面"
    assert body["size"] == SHEET_SIZE
    assert body["response_format"] == "b64_json"
    assert body["output_format"] == "png"
    assert body["watermark"] is False
    assert "image" not in body

    assert isinstance(result, SeedreamResult)
    assert result.png == png
    assert (result.width, result.height) == (2560, 1440)
    assert result.model == DEFAULT_MODEL
    assert result.usage == {"generated_images": 1, "total_tokens": 8100}


@pytest.mark.anyio
async def test_reference_images_single_is_string_multiple_is_list(ark_key):
    png = _png(2560, 1440)
    seen: list[dict] = []
    def handler(request):
        seen.append(_post_body(request))
        return httpx.Response(200, json=_success_payload(png))

    transport = httpx.MockTransport(handler)
    first, second = b"\x89PNG-one", b"\x89PNG-two"

    await generate_sheet("单张参考", size=SHEET_SIZE, reference_images=[first], transport=transport)
    await generate_sheet("两张参考", size=SHEET_SIZE, reference_images=[first, second], transport=transport)

    assert seen[0]["image"] == "data:image/png;base64," + base64.b64encode(first).decode("ascii")
    assert seen[1]["image"] == [
        "data:image/png;base64," + base64.b64encode(first).decode("ascii"),
        "data:image/png;base64," + base64.b64encode(second).decode("ascii"),
    ]
    assert seen[1]["size"] == SHEET_SIZE


@pytest.mark.anyio
async def test_model_resolution_parameter_then_env_then_default(ark_key, monkeypatch):
    png = _png(2560, 1440)
    seen: list[str] = []
    def handler(request):
        seen.append(_post_body(request)["model"])
        return httpx.Response(200, json=_success_payload(png))

    transport = httpx.MockTransport(handler)
    env_result = await generate_sheet("环境变量模型", size=SHEET_SIZE, reference_images=[], transport=transport)
    assert seen[-1] == DEFAULT_MODEL
    assert env_result.model == DEFAULT_MODEL

    monkeypatch.setenv("SEEDREAM_IMAGE_MODEL", "doubao-seedream-5-0-pro-260915")
    env_result = await generate_sheet("环境变量模型", size=SHEET_SIZE, reference_images=[], transport=transport)
    assert seen[-1] == "doubao-seedream-5-0-pro-260915"
    assert env_result.model == "doubao-seedream-5-0-pro-260915"

    explicit = await generate_sheet("显式模型", size=SHEET_SIZE, reference_images=[], model="doubao-seedream-5-0-flash-260915", transport=transport)
    assert seen[-1] == "doubao-seedream-5-0-flash-260915"
    assert explicit.model == "doubao-seedream-5-0-flash-260915"


# --------------------------------------------------------------------------- #
# uncertain：超时、断连、5xx、坏 JSON、尺寸不符、重定向
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["timeout", "connect", "reset"])
async def test_transport_failures_are_uncertain(ark_key, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("上游超时", request=request)
        if failure == "connect":
            raise httpx.ConnectError("连不上", request=request)
        raise ConnectionResetError("连接被重置")

    wrapped, requests = _calls(handler)
    error = await _expect_error(
        "uncertain", "transport_error",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1
    assert ark_key not in error.message


@pytest.mark.anyio
@pytest.mark.parametrize("status", [500, 502, 503])
async def test_5xx_is_uncertain(ark_key, status):
    def handler(request):
        return httpx.Response(status, json={"error": {"code": "ServerBusy", "message": "暂时不可用"}})

    wrapped, requests = _calls(handler)
    await _expect_error(
        "uncertain", "http_5xx",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [b"{", b"not json", b'[1, 2, 3]'])
async def test_2xx_bad_json_is_uncertain(ark_key, payload):
    def handler(request):
        return httpx.Response(200, content=payload)

    wrapped, requests = _calls(handler)
    await _expect_error(
        "uncertain", "invalid_response",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [
    {"data": []},
    {"data": [{}]},
    {"data": [{"b64_json": ""}]},
    {"data": [{"b64_json": "%%%not-base64%%%"}]},
    {"output": {"task_status": "succeeded"}},
])
async def test_2xx_missing_or_invalid_png_is_uncertain(ark_key, payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    wrapped, requests = _calls(handler)
    await _expect_error(
        "uncertain", "invalid_response",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1


@pytest.mark.anyio
async def test_returned_size_mismatch_is_uncertain(ark_key):
    png = _png(1280, 720)
    def handler(request):
        return httpx.Response(200, json=_success_payload(png))

    wrapped, requests = _calls(handler)
    await _expect_error(
        "uncertain", "size_mismatch",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("status", [301, 302, 307])
async def test_redirect_is_not_followed_and_is_uncertain(ark_key, status):
    def handler(request):
        return httpx.Response(status, headers={"Location": "https://evil.example.test/sheet.png"})

    wrapped, requests = _calls(handler)
    error = await _expect_error(
        "uncertain", f"http_{status}",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    # 未被跟随：只发出一次请求，且拿到的是原始重定向响应。
    assert len(requests) == 1
    assert error.code == f"http_{status}"
    assert "evil.example.test" not in error.message


@pytest.mark.anyio
async def test_total_timeout_is_uncertain_and_sends_single_post(ark_key, monkeypatch):
    """整体超时（含上传参考图 / 读满响应）按 uncertain 处理，且绝不重发 POST。"""
    monkeypatch.setattr(image_seedream, "TOTAL_TIMEOUT_S", 0.05)

    async def handler(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json=_success_payload(b"\x89PNG-rust"))

    wrapped, requests = _calls(handler)
    error = await _expect_error(
        "uncertain", "timeout",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": [b"\x89PNG-ref"]},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1
    assert ark_key not in error.message


# --------------------------------------------------------------------------- #
# rejected：明确 4xx / 429
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_client_errors_are_rejected(ark_key, status):
    def handler(request):
        return httpx.Response(status, json={"error": {"code": "InvalidParameter", "message": "参数不合法"}})

    wrapped, requests = _calls(handler)
    await _expect_error(
        "rejected", f"http_{status}",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1


@pytest.mark.anyio
async def test_429_is_rejected(ark_key):
    def handler(request):
        return httpx.Response(429, json={"error": {"code": "RateLimitExceeded", "message": "请求过于频繁"}})

    wrapped, requests = _calls(handler)
    await _expect_error(
        "rejected", "http_429",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert len(requests) == 1


@pytest.mark.anyio
async def test_4xx_message_hides_key_and_request_body(ark_key):
    def handler(request):
        return httpx.Response(
            400,
            json={"error": {"code": "InvalidParameter", "message": f"bad key {ark_key} and data:image/png;base64,AAAA"}},
        )

    error = await _expect_error(
        "rejected", "http_400",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(_calls(handler)[0]),
    )
    assert ark_key not in error.message
    assert "data:image/png;base64" not in error.message


# --------------------------------------------------------------------------- #
# failed：内容审核
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
@pytest.mark.parametrize("code", [
    "SensitiveContentDetected", "RiskDetection", "PolicyViolation",
    "PrivacyInformation", "Deepfake", "ContentModeration",
])
async def test_moderation_codes_are_failed(ark_key, code):
    def handler(request):
        return httpx.Response(400, json={"error": {"code": code, "message": "请求可能包含敏感信息"}})

    wrapped, requests = _calls(handler)
    error = await _expect_error(
        "failed", None,
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(wrapped),
    )
    assert error.code.lower() == code.lower()
    assert "审核" in error.message
    assert len(requests) == 1


@pytest.mark.anyio
async def test_moderation_code_in_2xx_body_is_failed(ark_key):
    def handler(request):
        return httpx.Response(200, json={"model": DEFAULT_MODEL, "error": {"code": "SensitiveContentDetected"}})

    await _expect_error(
        "failed", "SensitiveContentDetected",
        {"prompt": "定妆", "size": SHEET_SIZE, "reference_images": []},
        httpx.MockTransport(_calls(handler)[0]),
    )


# --------------------------------------------------------------------------- #
# 本地前置校验：缺 Key / 非法尺寸 / 非法参考图 —— 都不发请求
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
async def test_missing_api_key_does_not_send_request(monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("SEEDREAM_IMAGE_MODEL", raising=False)
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise AssertionError("缺少 ARK_API_KEY 时不应发请求")

    with pytest.raises(MediaCallError) as caught:
        await generate_sheet(
            "定妆", size=SHEET_SIZE, reference_images=[],
            transport=httpx.MockTransport(handler),
        )
    assert caught.value.status == "failed"
    assert caught.value.code == "missing_configuration"
    assert calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("size", [
    "2560*1440", "2560x", "0x1000", "900x900", "2560x1440x2", "5120x2880", "1x100000",
])
async def test_invalid_size_is_failed_without_request(ark_key, size):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise AssertionError("非法尺寸不应发请求")

    with pytest.raises(MediaCallError) as caught:
        await generate_sheet(
            "定妆", size=size, reference_images=[],
            transport=httpx.MockTransport(handler),
        )
    assert caught.value.status == "failed"
    assert caught.value.code == "invalid_size"
    assert calls == []


@pytest.mark.anyio
async def test_invalid_reference_image_is_failed_without_request(ark_key):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise AssertionError("非法参考图不应发请求")

    with pytest.raises(MediaCallError) as caught:
        await generate_sheet(
            "定妆", size=SHEET_SIZE, reference_images=["not-bytes"],
            transport=httpx.MockTransport(handler),
        )
    assert caught.value.status == "failed"
    assert caught.value.code == "invalid_reference_image"
    assert calls == []


@pytest.mark.anyio
async def test_empty_prompt_is_failed_without_request(ark_key):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise AssertionError("空提示词不应发请求")

    with pytest.raises(MediaCallError) as caught:
        await generate_sheet(
            "   ", size=SHEET_SIZE, reference_images=[],
            transport=httpx.MockTransport(handler),
        )
    assert caught.value.status == "failed"
    assert caught.value.code == "invalid_prompt"
    assert calls == []
