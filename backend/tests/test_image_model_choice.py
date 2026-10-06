"""Offline image-model selection, provider contracts and billing regressions."""
import asyncio
import base64
import io
import json
from typing import Literal, get_args, get_origin
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from PIL import Image

from tools import image_generation as images


_QWEN = "qwen-image-3.0"
_SEEDREAM = "seedream-5.0-flash"
_ARK_MODEL = "doubao-seedream-5-0-flash-260915"
_ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
_ASYNC_CLIENT = httpx.AsyncClient
_UNAVAILABLE = "Seedream 生图暂不可用，请改选 Qwen Image 3.0。"
_BUSY = "图片生成服务繁忙，请稍后再试。"
_MODERATION = "描述或参考图未通过内容审核，请修改后再试。"
_FAILED = "图片生成失败，请稍后再试。"


def _png(size=(24, 16), color="blue"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def _result(png=None):
    return {"model": _ARK_MODEL, "created": 1, "data": [{
        "b64_json": base64.b64encode(_png() if png is None else png).decode("ascii"),
        "size": "24x16", "output_format": "png",
    }], "usage": {"generated_images": 1}}


def _transport(monkeypatch, handler):
    options = []

    def factory(**kwargs):
        options.append(kwargs)
        return _ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(images.httpx, "AsyncClient", factory)
    return options


def _reference(directory, size=(1024, 1024), color="green"):
    name = f"reference_{uuid4().hex}.png"
    (directory / name).write_bytes(_png(size, color))
    return f"/uploads/{name}"


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def _conversation(client, headers):
    response = client.post("/conversations", headers=headers, json={})
    assert response.status_code in {200, 201}, response.text
    return response.json()["conversation"]["id"]


def _production_user(client, dev_headers, monkeypatch, balance=10):
    """Use a real JWT and isolated balance, as beta billing tests do."""
    import database
    from auth import create_token

    user = dev_headers["X-Dev-User"]
    conversation = _conversation(client, dev_headers)

    async def set_balance():
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (balance, user))
            await db.commit()

    asyncio.run(set_balance())
    version = asyncio.run(database.get_session_version(user))
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    return user, conversation, {"Authorization": f"Bearer {create_token(user, version)}"}


@pytest.fixture(autouse=True)
def offline_image_test(monkeypatch):
    import services.chat_service as chat
    from rate_limit import limiter

    def forbidden_network(**kwargs):
        raise AssertionError("Image-model tests must install an offline transport")

    monkeypatch.setattr(images.httpx, "AsyncClient", forbidden_network)
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())


@pytest.fixture
def image_env(monkeypatch, tmp_path):
    from utils import media

    uploads = tmp_path / "model-images"
    uploads.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "unit-qwen-key")
    monkeypatch.setenv("ARK_API_KEY", "unit-ark-key")
    monkeypatch.delenv("QWEN_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("SEEDREAM_IMAGE_MODEL", raising=False)
    return uploads


@pytest.mark.parametrize("qwen_key,ark_key,available", [
    (None, None, [False, False]), ("", "", [False, False]),
    (" \t", " \n", [False, False]),
    ("qwen-secret", "", [True, False]), ("", "ark-secret", [False, True]),
    (" qwen-secret ", " ark-secret ", [True, True]),
])
def test_registry_public_metadata_and_configuration_availability(monkeypatch, qwen_key, ark_key, available):
    for name, value in (("DASHSCOPE_API_KEY", qwen_key), ("ARK_API_KEY", ark_key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert images.DEFAULT_IMAGE_MODEL == _QWEN
    assert images.get_image_models() == {
        "default": _QWEN, "models": [
            {"id": _QWEN, "label": "Qwen Image 3.0", "available": available[0]},
            {"id": _SEEDREAM, "label": "Seedream 5.0 Flash", "available": available[1]},
        ],
    }


def test_registry_reads_availability_on_every_call(monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    assert images.get_image_models()["models"][1]["available"] is False
    monkeypatch.setenv("ARK_API_KEY", "newly-configured")
    assert images.get_image_models()["models"][1]["available"] is True


@pytest.mark.parametrize("model_id,env_name,fetch_name,default", [
    (_QWEN, "QWEN_IMAGE_MODEL", "_fetch_generated_bytes", _QWEN),
    (_SEEDREAM, "SEEDREAM_IMAGE_MODEL", "_fetch_ark_png", _ARK_MODEL),
])
@pytest.mark.parametrize("editing", [False, True], ids=["generate", "edit"])
def test_real_model_environment_is_read_at_each_call(monkeypatch, image_env, model_id, env_name, fetch_name, default, editing):
    calls = []

    async def fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return _png()

    monkeypatch.setattr(images, fetch_name, fetch)
    reference = _reference(image_env)
    expected = [default, "custom-model-first", "custom-model-second", default]
    for override, actual in zip([None, expected[1], expected[2], " \t "], expected):
        if override is None:
            monkeypatch.delenv(env_name, raising=False)
        else:
            monkeypatch.setenv(env_name, override)
        if editing:
            result = asyncio.run(images.edit_image("加一点晨雾", reference, model_id=model_id))
        else:
            result = asyncio.run(images.generate_image("窗台上的猫", model_id=model_id))
        assert result["model"] == actual
        assert calls[-1][0][2] == actual
    assert len(calls) == 4


def test_image_models_requires_production_auth_and_does_not_expose_configuration(client, dev_headers, monkeypatch):
    _, _, headers = _production_user(client, dev_headers, monkeypatch)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "private-qwen-key")
    monkeypatch.setenv("ARK_API_KEY", "private-ark-key")
    monkeypatch.setenv("QWEN_IMAGE_MODEL", "private-qwen-model")
    monkeypatch.setenv("SEEDREAM_IMAGE_MODEL", "private-ark-model")
    assert client.get("/image-models").status_code == 401
    response = client.get("/image-models", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "default": _QWEN, "models": [
            {"id": _QWEN, "label": "Qwen Image 3.0", "available": True},
            {"id": _SEEDREAM, "label": "Seedream 5.0 Flash", "available": True},
        ],
    }
    for private in (_ARK_MODEL, "ARK_API_KEY", "DASHSCOPE_API_KEY", "private-qwen-key", "private-ark-key",
                    "private-qwen-model", "private-ark-model", "QWEN_IMAGE_MODEL", "SEEDREAM_IMAGE_MODEL"):
        assert private not in response.text


def test_chat_request_omitted_image_model_defaults_to_none():
    from routers.chat import ChatRequest

    assert ChatRequest(message="测试").image_model is None


def test_chat_request_image_model_literal_matches_registry():
    from routers.chat import ChatRequest

    annotation = ChatRequest.model_fields["image_model"].annotation
    literals = [item for item in get_args(annotation) if get_origin(item) is Literal]
    assert len(literals) == 1
    assert set(get_args(literals[0])) == set(images._IMAGE_MODELS)


def test_image_models_requires_auth_even_without_global_middleware(client, dev_headers, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.image_models import router

    _, _, headers = _production_user(client, dev_headers, monkeypatch)
    isolated = FastAPI()
    isolated.include_router(router)
    with TestClient(isolated) as isolated_client:
        assert isolated_client.get("/image-models").status_code == 401
        response = isolated_client.get("/image-models", headers=headers)
        assert response.status_code == 200
        assert response.json() == images.get_image_models()


@pytest.mark.parametrize("mode", ["chat", "image", "image_edit"])
def test_unknown_image_model_is_http_422(client, dev_headers, mode):
    response = client.post("/chat", headers=dev_headers, json={
        "message": "窗台上的猫", "mode": mode, "image_model": "unregistered-model",
    })
    assert response.status_code == 422
    assert any(error["loc"] == ["body", "image_model"] for error in response.json()["detail"])


@pytest.mark.parametrize("model_id", [None, _QWEN, _SEEDREAM], ids=["omitted", "default", "seedream"])
@pytest.mark.parametrize("path", ["image", "image_edit", "image_edit_multi", "chat_intent", "chat_pending"])
def test_selection_reaches_every_image_path_without_changing_default_arguments(
    client, dev_headers, monkeypatch, image_env, model_id, path,
):
    import database
    import services.chat_service as chat
    from intent_router import get_pending, set_pending

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    key = (user, conversation)
    calls = []
    traces = []
    prompt = "画一只窗台上的橘猫" if path == "chat_intent" else "窗台上睡觉的橘猫"
    mode = "image_edit" if path.startswith("image_edit") else ("image" if path == "image" else "chat")
    body = {"conversation_id": conversation, "message": prompt, "mode": mode}
    if model_id is not None:
        body["image_model"] = model_id

    async def record(*args, **kwargs):
        calls.append((args, kwargs))
        name = f"generated_{uuid4().hex}.png"
        (image_env / name).write_bytes(_png())
        return {"image_path": f"/uploads/{name}", "model": "actual-provider-model", "width": 24, "height": 16}

    async def log(*args, **kwargs):
        traces.append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "generate_image", record)
    monkeypatch.setattr(chat, "edit_image", record)
    monkeypatch.setattr(chat, "log_event", log)
    if path.startswith("image_edit"):
        references = [_reference(image_env, color=color) for color in (
            ["red", "green"] if path == "image_edit_multi" else ["red"]
        )]
        for reference in references:
            assert asyncio.run(database.save_message(user, "assistant", "参考图", reference, conversation_id=conversation))
        if path == "image_edit_multi":
            body["reference_image_paths"] = references
            expected_args = (prompt, references, None)
        else:
            body["reference_image_path"] = references[0]
            expected_args = (prompt, references[0], None)
    elif path == "image":
        body["aspect_ratio"] = "16:9"
        expected_args = (prompt, "16:9")
    else:
        expected_args = (prompt, "1:1")
        if path == "chat_intent":
            monkeypatch.setattr(chat, "recognize_intent", lambda *args, **kwargs: {
                "intent": "generate_image", "params": {"prompt": "分类器缩短内容"}, "missing": [],
            })
        else:
            set_pending(key, {"intent": "generate_image", "params": {}, "missing": ["prompt"]})

    output = _events(client.post("/chat", headers=dev_headers, json=body))
    assert output[-1] == {"done": True}
    assert sum("generated_image" in event for event in output) == 1
    expected_kwargs = {"model_id": _SEEDREAM} if model_id == _SEEDREAM else {}
    assert calls == [(expected_args, expected_kwargs)]
    assert traces[-1]["model"] == "actual-provider-model"
    assert traces[-1]["image_model"] == (model_id or _QWEN)
    assert prompt not in json.dumps(traces, ensure_ascii=False)
    if path == "chat_pending":
        assert get_pending(key) is None


@pytest.mark.parametrize("ratio,size", [("1:1", "1024x1024"), ("16:9", "1536x864"), ("9:16", "864x1536")])
def test_ark_generation_exact_contract_and_png_persistence(monkeypatch, image_env, ratio, size):
    requests = []
    png = _png()

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_result(png))

    options = _transport(monkeypatch, handler)
    result = asyncio.run(images.generate_image("  窗台上的猫  ", ratio, model_id=_SEEDREAM))
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == _ARK_URL
    assert request.headers["authorization"] == "Bearer unit-ark-key"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": _ARK_MODEL, "prompt": "窗台上的猫", "size": size,
        "response_format": "b64_json", "output_format": "png", "watermark": False,
    }
    assert options[0]["timeout"].read == 150
    assert options[0].get("follow_redirects", False) is False
    assert result["model"] == _ARK_MODEL
    assert (result["width"], result["height"]) == (24, 16)
    assert images._REFERENCE_IMAGE_PATH.fullmatch(result["image_path"])
    assert (image_env / result["image_path"].rsplit("/", 1)[-1]).read_bytes() == png
    assert len(list(image_env.iterdir())) == 1


@pytest.mark.parametrize("count", [1, 2, 3])
def test_ark_edit_reference_shape_and_order(monkeypatch, image_env, count):
    references = [_reference(image_env, color=color) for color in ["red", "green", "blue"][:count]]
    expected = ["data:image/png;base64," + base64.b64encode(
        (image_env / path.rsplit("/", 1)[-1]).read_bytes()).decode("ascii") for path in references]
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=_result())

    _transport(monkeypatch, handler)
    result = asyncio.run(images.edit_image("加一点晨雾", references[0] if count == 1 else references, model_id=_SEEDREAM))
    assert len(calls) == 1
    assert json.loads(calls[0].content) == {
        "model": _ARK_MODEL, "prompt": "加一点晨雾", "size": "1024x1024",
        "response_format": "b64_json", "output_format": "png", "watermark": False,
        "image": expected[0] if count == 1 else expected,
    }
    assert result["model"] == _ARK_MODEL
    assert len(list(image_env.iterdir())) == count + 1


@pytest.mark.parametrize("data", [
    None, {}, {"data": None}, {"data": []}, {"data": "wrong"},
    {"data": [None]}, {"data": [{}]}, {"data": [{"b64_json": None}]},
    {"data": [{"b64_json": ""}]}, {"data": [{"b64_json": "%%%not-base64%%%"}]},
    {"data": [{"b64_json": base64.b64encode(b"not-a-PNG").decode("ascii")}]},
])
def test_bad_ark_response_is_safe_and_leaves_no_file(monkeypatch, image_env, data):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=data)

    _transport(monkeypatch, handler)
    with pytest.raises(images.ImageGenerationError):
        asyncio.run(images.generate_image("窗台上的猫", model_id=_SEEDREAM))
    assert len(calls) == 1
    assert list(image_env.iterdir()) == []


@pytest.mark.parametrize("case", ["oversized-pixels", "oversized-bytes"])
def test_ark_image_limits_reject_before_persistence(monkeypatch, image_env, case):
    png = _png((3000, 1500)) if case == "oversized-pixels" else _png()
    if case == "oversized-bytes":
        monkeypatch.setattr(images, "_MAX_IMAGE_BYTES", len(png) - 1)

    _transport(monkeypatch, lambda request: httpx.Response(200, json=_result(png)))
    with pytest.raises(images.ImageGenerationError):
        asyncio.run(images.generate_image("窗台上的猫", model_id=_SEEDREAM))
    assert list(image_env.iterdir()) == []


def test_ark_uses_separate_40mb_bounded_response_without_changing_qwen_limit(monkeypatch, image_env):
    limits = []
    original = images._read_bounded
    data = _result()
    data["unused_padding"] = "x" * (1024 * 1024)

    async def bounded(response, limit):
        limits.append(limit)
        return await original(response, limit)

    monkeypatch.setattr(images, "_read_bounded", bounded)
    _transport(monkeypatch, lambda request: httpx.Response(200, json=data))
    asyncio.run(images.generate_image("窗台上的猫", model_id=_SEEDREAM))
    assert limits == [40 * 1024 * 1024]
    assert images._MAX_RESPONSE_BYTES == 1024 * 1024


def test_ark_declared_response_over_40mb_is_rejected(monkeypatch, image_env):
    _transport(monkeypatch, lambda request: httpx.Response(
        200, content=b"{}", headers={"content-length": str(40 * 1024 * 1024 + 1)},
    ))
    with pytest.raises(images.ImageGenerationError):
        asyncio.run(images.generate_image("窗台上的猫", model_id=_SEEDREAM))
    assert list(image_env.iterdir()) == []


def test_ark_streaming_response_limit_is_enforced_without_content_length(monkeypatch, image_env):
    class ChunkedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 32
            yield b"x" * 33

    monkeypatch.setattr(images, "_MAX_ARK_RESPONSE_BYTES", 64)
    _transport(monkeypatch, lambda request: httpx.Response(200, stream=ChunkedBody()))
    with pytest.raises(images.ImageGenerationError):
        asyncio.run(images.generate_image("窗台上的猫", model_id=_SEEDREAM))
    assert list(image_env.iterdir()) == []


@pytest.mark.parametrize("status,code,expected", [
    (400, "InputSensitiveContentDetected", _MODERATION), (400, "RiskDetection", _MODERATION),
    (400, "PolicyViolation", _MODERATION), (400, "PrivacyInformation", _MODERATION),
    (400, "DeepFake", _MODERATION), (429, "", _BUSY), (400, "RateLimitExceeded", _BUSY),
    (400, "QuotaExceeded", _BUSY), (401, "AuthenticationError", _UNAVAILABLE),
    (403, "Forbidden", _UNAVAILABLE), (404, "NotFound", _UNAVAILABLE),
    (400, "ModelNotOpen", _UNAVAILABLE), (400, "AccountOverdueError", _UNAVAILABLE),
    (400, "InvalidEndpointOrModel.NotFound", _UNAVAILABLE),
    (400, "InvalidParameter", _FAILED), (500, "InternalServiceError", _FAILED),
])
def test_every_ark_error_family_is_safe_and_does_not_retry(monkeypatch, image_env, capsys, status, code, expected):
    calls = []
    prompt = "独有的私密画面描述"

    async def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {
            "code": code, "message": "private-provider-message unit-ark-key",
            "type": "private-error-type", "request_id": "private-request-id",
        }})

    _transport(monkeypatch, handler)
    with pytest.raises(images.ImageGenerationError) as error:
        asyncio.run(images.generate_image(prompt, model_id=_SEEDREAM))
    assert str(error.value) == expected
    if code:
        assert code not in str(error.value)
    output = capsys.readouterr().out
    assert output == f"[image] provider=ark status={status} code={code}\n"
    assert error.value.provider_status == status
    assert error.value.provider_code == code
    for private in (prompt, "private-provider-message", "unit-ark-key", "private-request-id"):
        assert private not in str(error.value)
        assert private not in output
    assert len(calls) == 1
    assert list(image_env.iterdir()) == []


@pytest.mark.parametrize("code", [
    "OutputImageSensitiveContentDetected", "RiskDetection", "PolicyViolation", "PrivacyInformation", "DeepFake",
])
def test_ark_http_200_single_image_error_preserves_moderation_mapping(monkeypatch, image_env, capsys, code):
    _transport(monkeypatch, lambda request: httpx.Response(200, json={"data": [{"error": {
        "code": code, "message": "private-single-image-message", "request_id": "private-single-image-id",
    }}]}))
    with pytest.raises(images.ImageGenerationError) as error:
        asyncio.run(images.generate_image("私密单图失败描述", model_id=_SEEDREAM))
    assert str(error.value) == _MODERATION
    assert error.value.provider_status == 200
    assert error.value.provider_code == code
    assert capsys.readouterr().out == f"[image] provider=ark status=200 code={code}\n"
    assert list(image_env.iterdir()) == []


@pytest.mark.parametrize("source_size", [(959, 961), (1199, 767), (1001, 919), (1279, 720)])
def test_ark_small_irregular_sizes_stay_close_to_minimum_area(monkeypatch, image_env, source_size):
    reference = _reference(image_env, size=source_size)
    sizes = []

    def handler(request):
        sizes.append(json.loads(request.content)["size"])
        return httpx.Response(200, json=_result())

    _transport(monkeypatch, handler)
    asyncio.run(images.edit_image("保留比例", reference, model_id=_SEEDREAM))
    width, height = map(int, sizes[0].split("x"))
    assert width % 8 == height % 8 == 0
    assert 921600 <= width * height <= 921600 * 1.1
    assert width / height == pytest.approx(source_size[0] / source_size[1], rel=0.01)


@pytest.mark.parametrize("source_size", [(960, 960), (1536, 864), (1001, 921), (4000, 1000)])
def test_ark_sizes_already_in_range_remain_unchanged(source_size):
    assert images._ark_size(*source_size) == f"{source_size[0]}x{source_size[1]}"


@pytest.mark.parametrize("ratio", [(1, 1), (4, 3), (16, 9), (9, 16), (4, 1), (1, 16)])
def test_ark_output_area_is_nondecreasing_for_fixed_ratio_samples(ratio):
    areas = []
    for scale in range(64, 4097, 64):
        width, height = map(int, images._ark_size(ratio[0] * scale, ratio[1] * scale).split("x"))
        assert width % 8 == height % 8 == 0
        assert 921600 <= width * height <= 2048 * 2048
        assert width / height == pytest.approx(ratio[0] / ratio[1], rel=0.01)
        areas.append(width * height)
    assert areas == sorted(areas)


@pytest.mark.parametrize("source_size", [(512, 512), (4000, 1000), (3000, 1000), (2048, 2048), (1024, 1024)])
def test_ark_follow_first_reference_size_preserves_ratio_and_all_bounds(monkeypatch, image_env, source_size):
    reference = _reference(image_env, size=source_size)
    sizes = []

    async def handler(request):
        sizes.append(json.loads(request.content)["size"])
        return httpx.Response(200, json=_result())

    _transport(monkeypatch, handler)
    asyncio.run(images.edit_image("保留比例，加一点晨雾", reference, model_id=_SEEDREAM))
    assert len(sizes) == 1
    width, height = map(int, sizes[0].split("x"))
    assert width % 8 == height % 8 == 0
    assert width > 0 and height > 0
    assert 921600 <= width * height <= min(4624220, 2048 * 2048)
    assert 1 / 16 <= width / height <= 16
    assert width / height == pytest.approx(source_size[0] / source_size[1], rel=0.01)


@pytest.mark.parametrize("source_size", [(4000, 2000), (4000, 4000), (8000, 2000)])
def test_ark_size_scales_inputs_above_project_total_pixel_limit(source_size):
    width, height = map(int, images._ark_size(*source_size).split("x"))
    assert width % 8 == height % 8 == 0
    assert width > 0 and height > 0
    assert 2048 * 2048 * 0.9 <= width * height <= min(4624220, 2048 * 2048)
    assert width / height == pytest.approx(source_size[0] / source_size[1], rel=0.01)


@pytest.mark.parametrize("model_id", [_QWEN, _SEEDREAM])
def test_both_providers_reject_reference_above_project_pixel_limit(image_env, model_id):
    reference = _reference(image_env, size=(4000, 2000))
    with pytest.raises(images.ImageGenerationError, match="尺寸过大"):
        asyncio.run(images.edit_image("加一点晨雾", reference, model_id=model_id))
    assert len(list(image_env.iterdir())) == 1


@pytest.mark.parametrize("source_size", [(32, 1024), (1024, 32)])
def test_ark_reference_outside_aspect_ratio_bounds_rejected_without_request(monkeypatch, image_env, source_size):
    reference = _reference(image_env, size=source_size)
    with pytest.raises(images.ImageGenerationError):
        asyncio.run(images.edit_image("加一点晨雾", reference, model_id=_SEEDREAM))
    assert len(list(image_env.iterdir())) == 1


@pytest.mark.parametrize("editing", [False, True], ids=["generate", "edit"])
def test_unknown_provider_model_id_rejected_without_network(monkeypatch, image_env, editing):
    with pytest.raises(images.ImageGenerationError):
        if editing:
            asyncio.run(images.edit_image("加一点晨雾", "/uploads/reference_" + "a" * 32 + ".png", model_id="unknown"))
        else:
            asyncio.run(images.generate_image("窗台上的猫", model_id="unknown"))
    assert list(image_env.iterdir()) == []


@pytest.mark.parametrize("mode", ["image", "image_edit"])
def test_unavailable_seedream_refunds_real_production_reservation_and_traces_id(
    client, dev_headers, monkeypatch, image_env, mode,
):
    import database
    import services.chat_service as chat

    user, conversation, headers = _production_user(client, dev_headers, monkeypatch)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setattr(chat, "generate_image", images.generate_image)
    monkeypatch.setattr(chat, "edit_image", images.edit_image)
    prompt = "私密草莓退款验收画面"
    body = {"message": prompt, "conversation_id": conversation, "mode": mode, "image_model": _SEEDREAM}
    if mode == "image_edit":
        reference = _reference(image_env)
        assert asyncio.run(database.save_message(user, "assistant", "参考图", reference, conversation_id=conversation))
        body["reference_image_path"] = reference
    traces = []

    async def log(*args, **kwargs):
        traces.append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "log_event", log)
    output = _events(client.post("/chat", headers=headers, json=body))
    assert output[-1] == {"error": _UNAVAILABLE}
    assert not any("generated_image" in event for event in output)
    assert asyncio.run(database.get_strawberry_balance(user)) == 10
    assert traces[-1]["image_model"] == _SEEDREAM
    assert traces[-1]["error"] == "ImageGenerationError"
    assert traces[-1]["model"] is None
    assert prompt not in json.dumps(traces, ensure_ascii=False)
    rows = client.get(f"/conversations/{conversation}/messages", headers=headers).json()["messages"]
    assert rows[-1]["role"] == "user"
    assert not list(image_env.glob("generated_*.png"))


def test_seedream_success_debits_ten_real_production_strawberries(client, dev_headers, monkeypatch, image_env):
    import database
    import services.chat_service as chat

    user, conversation, headers = _production_user(client, dev_headers, monkeypatch)
    monkeypatch.setattr(chat, "generate_image", images.generate_image)
    _transport(monkeypatch, lambda request: httpx.Response(200, json=_result()))
    assert asyncio.run(database.get_strawberry_balance(user)) == 10
    output = _events(client.post("/chat", headers=headers, json={
        "message": "窗台上的猫", "conversation_id": conversation, "mode": "image", "image_model": _SEEDREAM,
    }))
    assert output[-1] == {"done": True}
    assert sum("generated_image" in event for event in output) == 1
    assert asyncio.run(database.get_strawberry_balance(user)) == 0


def test_ark_failure_logs_and_traces_only_sanitized_status_code_and_refunds(
    client, dev_headers, monkeypatch, image_env, capsys,
):
    import database
    import services.chat_service as chat

    user, conversation, headers = _production_user(client, dev_headers, monkeypatch)
    monkeypatch.setattr(chat, "generate_image", images.generate_image)
    prompt = "不能写入日志和trace的原始提示词"
    code = "ModelNotOpen.\n<秘密>/" + "x" * 100
    safe_code = ("ModelNotOpen." + "x" * 100)[:80]
    message = "private-ark-original-message unit-ark-key"
    traces = []

    async def log(*args, **kwargs):
        traces.append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "log_event", log)
    _transport(monkeypatch, lambda request: httpx.Response(404, json={"error": {
        "code": code, "message": message, "request_id": "private-ark-request-id",
    }}))
    output = _events(client.post("/chat", headers=headers, json={
        "message": prompt, "conversation_id": conversation, "mode": "image", "image_model": _SEEDREAM,
    }))
    assert output[-1] == {"error": _UNAVAILABLE}
    assert asyncio.run(database.get_strawberry_balance(user)) == 10
    assert traces[-1]["provider_status"] == 404
    assert traces[-1]["provider_code"] == safe_code
    logs = capsys.readouterr().out
    assert [line for line in logs.splitlines() if line.startswith("[image]")] == [
        f"[image] provider=ark status=404 code={safe_code}",
    ]
    trace_text = json.dumps(traces, ensure_ascii=False)
    for private in (prompt, code, message, "private-ark-request-id", "unit-ark-key", "秘密"):
        assert private not in logs
        assert private not in trace_text
    assert list(image_env.iterdir()) == []


@pytest.mark.parametrize("model_id", [None, _QWEN, _SEEDREAM])
def test_image_failure_trace_records_effective_id_without_prompt(monkeypatch, model_id):
    import services.chat_service as chat

    async def fail(*args, **kwargs):
        raise images.ImageGenerationError("安全失败说明")

    monkeypatch.setattr(chat, "generate_image", fail)
    prompt = "不可写入 trace 的私密提示词"
    ctx = chat.ChatContext("trace-test", prompt, False, None, prompt, [], 0, "", [], image_model=model_id)
    state = chat.ChatState(trace={})

    async def consume():
        return [event async for event in chat.stream_generated_image(ctx, state, prompt)]

    output = asyncio.run(consume())
    assert "安全失败说明" in output[-1]
    assert state.trace["image_model"] == (model_id or _QWEN)
    assert state.trace["error"] == "ImageGenerationError"
    assert prompt not in json.dumps(state.trace, ensure_ascii=False)


@pytest.mark.parametrize("model_id", [None, _QWEN, _SEEDREAM])
def test_busy_image_failure_trace_records_effective_id_without_prompt(model_id):
    import services.chat_service as chat

    prompt = "并发忙时也不可写入 trace 的提示词"
    ctx = chat.ChatContext("busy-model-test", prompt, False, None, prompt, [], 0, "", [], image_model=model_id)
    state = chat.ChatState(trace={})
    chat._IMAGE_GENERATION_USERS.add(ctx.user)

    async def consume():
        return [event async for event in chat.stream_generated_image(ctx, state, prompt)]

    output = asyncio.run(consume())
    assert "已有图片正在生成" in output[-1]
    assert state.trace["error"] == "ImageGenerationBusy"
    assert state.trace["image_model"] == (model_id or _QWEN)
    assert prompt not in json.dumps(state.trace, ensure_ascii=False)
