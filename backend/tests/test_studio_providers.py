"""供应商契约只通过 MockTransport 验证，绝不调用真实接口。"""
import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from studio.providers import ProviderError, get_provider
from studio.providers.base import UNCERTAIN_MESSAGE


FIXTURES = Path(__file__).parent / "fixtures" / "studio"


@pytest.fixture
def provider_image(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-wan-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "offline-workspace")
    monkeypatch.setenv("ARK_API_KEY", "offline-ark-key")
    path = tmp_path / "frame.png"
    Image.new("RGB", (941, 1672), "#305070").save(path)
    return path


def _params(provider):
    return {"provider": provider, "model": "wan3.0-video" if provider == "wan" else "doubao-seedance-2-5-260628",
            "prompt": "相机缓慢推近", "resolution": "480P" if provider == "wan" else "480p",
            "duration": 5, "audio": True}


class BrokenResponse(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"error":'
        raise httpx.ReadError("响应正文包含私有内容")


@pytest.mark.parametrize("provider", ["wan", "seedance"])
@pytest.mark.parametrize("failure", ["timeout", "reset", "interrupted", "500", "502", "no_id", "bad_json", "nan_json", "list_json", "redirect", "incomplete_400"])
def test_paid_post_is_once_and_ambiguous_response_is_uncertain(provider, failure, provider_image):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        if failure == "timeout":
            raise httpx.ReadTimeout("私有提示词", request=request)
        if failure == "reset":
            raise ConnectionResetError("私有提示词")
        if failure == "interrupted":
            return httpx.Response(400, stream=BrokenResponse())
        if failure == "incomplete_400":
            return httpx.Response(400, content=b'{}', headers={"Content-Length": "20"})
        if failure in {"500", "502"}:
            return httpx.Response(int(failure), json={"code": "ServerBusy", "message": "暂时不可用"})
        if failure == "bad_json":
            return httpx.Response(200, content=b'{')
        if failure == "nan_json":
            return httpx.Response(200, content=b'{"id":"known-task","output":{"task_id":"known-task"},"value":NaN}')
        if failure == "list_json":
            return httpx.Response(200, json=[])
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "https://other.example/tasks"})
        return httpx.Response(200, json={"output": {}})

    async def scenario():
        instance = get_provider(provider, transport=httpx.MockTransport(handler))
        with pytest.raises(ProviderError) as exc:
            await instance.submit(_params(provider), provider_image)
        assert exc.value.status == "uncertain"
        assert UNCERTAIN_MESSAGE in exc.value.message
        assert "私有提示词" not in exc.value.message

    asyncio.run(scenario())
    assert len(calls) == 1


@pytest.mark.parametrize("provider", ["wan", "seedance"])
@pytest.mark.parametrize("status", [400, 401, 429])
def test_complete_4xx_retains_upstream_rejection(provider, status, provider_image):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": "InputImagePortraitDetected", "message": "首帧肖像校验未通过"}})

    async def scenario():
        with pytest.raises(ProviderError) as exc:
            await get_provider(provider, transport=httpx.MockTransport(handler)).submit(_params(provider), provider_image)
        assert exc.value.status == "rejected"
        assert exc.value.code == "InputImagePortraitDetected"
        assert exc.value.message == "首帧肖像校验未通过"

    asyncio.run(scenario())
    assert len(calls) == 1


@pytest.mark.parametrize("resolution,long_limit,short_limit", [("480p", 854, 480), ("720p", 1280, 720), ("1080p", 1920, 1080)])
@pytest.mark.parametrize("size", [(2400, 1500), (1500, 2400), (1800, 1800), (320, 240)])
def test_seedance_resizes_only_in_memory(resolution, long_limit, short_limit, size, provider_image):
    Image.new("RGB", size, "#305070").save(provider_image)
    before = provider_image.read_bytes()
    observed = []

    def handler(request):
        body = json.loads(request.content)
        assert "ratio" not in body and "camera_fixed" not in body
        assert body["model"] == "doubao-seedance-2-5-260628"
        assert body["generate_audio"] is True
        encoded = body["content"][1]["image_url"]["url"].split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            observed.append(image.size)
        return httpx.Response(200, json={"id": "cgt-offline-task"})

    params = {**_params("seedance"), "resolution": resolution}
    result = asyncio.run(get_provider("seedance", transport=httpx.MockTransport(handler)).submit(params, provider_image))
    assert result.task_id == "cgt-offline-task"
    width, height = observed[0]
    assert max(width, height) <= long_limit and min(width, height) <= short_limit
    assert max(width, height) <= max(size) and min(width, height) <= min(size)
    assert width / height == pytest.approx(size[0] / size[1], abs=0.005)
    assert provider_image.read_bytes() == before


def test_wan_uses_verified_probe_shape_and_unscaled_original(provider_image):
    fixture = json.loads((FIXTURES / "wan-20261016-131032.json").read_text())
    calls = []

    def handler(request):
        body = json.loads(request.content)
        assert request.headers["X-DashScope-Async"] == "enable"
        assert request.url.host == "offline-workspace.cn-beijing.maas.aliyuncs.com"
        assert body["parameters"] == fixture["request"]["body"]["parameters"]
        assert body["input"]["media"][0]["type"] == "first_frame"
        uri = body["input"]["media"][0]["url"]
        assert base64.b64decode(uri.split(",", 1)[1]) == provider_image.read_bytes()
        calls.append(request)
        return httpx.Response(200, json=fixture["submission_response"])

    result = asyncio.run(get_provider("wan", transport=httpx.MockTransport(handler)).submit(_params("wan"), provider_image))
    assert result.task_id == fixture["task_id"]
    assert len(calls) == 1


@pytest.mark.parametrize("provider,upstream,expected", [
    ("wan", "PENDING", "running"), ("wan", "RUNNING", "running"),
    ("wan", "SUCCEEDED", "succeeded"), ("wan", "FAILED", "failed"), ("wan", "UNKNOWN", "failed"),
    ("seedance", "queued", "running"), ("seedance", "running", "running"),
    ("seedance", "succeeded", "succeeded"), ("seedance", "failed", "failed"),
])
def test_status_mapping_only_uses_get(provider, upstream, expected, provider_image):
    calls = []
    usage = {"duration": 5, "SR": 480} if provider == "wan" else {"completion_tokens": 48324}
    payload = {"output": {"task_status": upstream, "video_url": "https://video.example/result.mp4"}, "usage": usage} if provider == "wan" else {
        "status": upstream, "content": {"video_url": "https://video.example/result.mp4"}, "usage": usage,
    }

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert "X-DashScope-Async" not in request.headers
        return httpx.Response(200, json=payload)

    result = asyncio.run(get_provider(provider, transport=httpx.MockTransport(handler)).poll("offline-task"))
    assert result.status == expected and result.usage == usage
    if expected == "succeeded":
        assert result.result_url == "https://video.example/result.mp4"
    assert len(calls) == 1


@pytest.mark.parametrize("code", ["OutputVideoSensitiveContentDetected", "InputImageSensitiveContentDetected", "CopyrightViolation"])
def test_seedance_content_filter_is_distinguished(code, provider_image):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "status": "failed", "error": {"code": code, "message": "内容校验未通过"},
    }))
    result = asyncio.run(get_provider("seedance", transport=transport).poll("offline-task"))
    assert result.status == "filtered" and result.error_code == code


def test_no_post_for_missing_credentials(provider_image, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(get_provider("seedance", transport=transport).submit(_params("seedance"), provider_image))
    assert exc.value.status == "failed" and calls == []


def test_rejection_message_hides_echoed_secret(provider_image):
    transport = httpx.MockTransport(lambda request: httpx.Response(400, json={
        "error": {"code": "BadRequest", "message": "offline-ark-key data:image/png;base64,AAAABBBB"},
    }))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(get_provider("seedance", transport=transport).submit(_params("seedance"), provider_image))
    assert "offline-ark-key" not in exc.value.message
    assert "AAAABBBB" not in exc.value.message
