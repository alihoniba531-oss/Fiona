# -*- coding: utf-8 -*-
"""Offline generation, provider boundary, cancellation and image ownership tests."""
import asyncio
import base64
import io
import json

import httpx
import pytest
from PIL import Image

from tools import image_generation


_RESULT_URL = "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/output/image.png?Expires=123&Signature=private-signature"


def _successful_result(url=_RESULT_URL):
    return {"output": {"choices": [{"message": {"content": [{"image": url}]}}]}}


def _png_bytes(size=(24, 16)):
    output = io.BytesIO()
    Image.new("RGB", size, "blue").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def generation_env(monkeypatch, tmp_path):
    from utils import media

    monkeypatch.setenv("DASHSCOPE_API_KEY", "unit-test-secret-key")
    monkeypatch.delenv("QWEN_IMAGE_MODEL", raising=False)
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    return tmp_path


def _mock_transport(monkeypatch, handler):
    original_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(image_generation.httpx, "AsyncClient", client_factory)


def test_generates_one_image_with_official_contract_and_saves_locally(monkeypatch, generation_env):
    requests = []
    png = _png_bytes()

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json=_successful_result())
        return httpx.Response(200, content=png, headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    result = asyncio.run(image_generation.generate_image("蓝色的小猫", "16:9"))

    assert result["model"] == "qwen-image-3.0"
    assert (result["width"], result["height"]) == (24, 16)
    assert result["image_path"].startswith("/uploads/generated_")
    saved = generation_env / result["image_path"].split("/")[-1]
    assert saved.read_bytes() == png
    assert len(requests) == 2
    assert str(requests[0].url) == image_generation._GENERATION_URL
    assert requests[0].headers["authorization"] == "Bearer unit-test-secret-key"
    assert "authorization" not in requests[1].headers
    assert json.loads(requests[0].content) == {
        "model": "qwen-image-3.0",
        "input": {"messages": [{"role": "user", "content": [{"text": "蓝色的小猫"}]}]},
        "parameters": {"size": "1536*864", "n": 1, "prompt_extend": True, "enable_thinking": False},
    }


def test_model_override(monkeypatch, generation_env):
    monkeypatch.setenv("QWEN_IMAGE_MODEL", "qwen-image-3.0-pro")

    async def handler(request):
        if request.method == "POST":
            assert json.loads(request.content)["model"] == "qwen-image-3.0-pro"
            return httpx.Response(200, json=_successful_result())
        return httpx.Response(200, content=_png_bytes(), headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    assert asyncio.run(image_generation.generate_image("小猫"))["model"] == "qwen-image-3.0-pro"


@pytest.mark.parametrize("model", ["qwen-image-3.0", "qwen-image-2.0"])
def test_native_protocol_contract_and_documented_shanghai_result(monkeypatch, generation_env, model):
    monkeypatch.setenv("QWEN_IMAGE_MODEL", model)
    requests = []

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            assert str(request.url) == image_generation._GENERATION_URL
            body = json.loads(request.content)
            assert body["model"] == model
            assert body["input"] == {"messages": [{"role": "user", "content": [{"text": "小猫"}]}]}
            assert body["parameters"]["size"] == "1024*1024"
            assert body["parameters"]["n"] == 1
            assert body["parameters"]["prompt_extend"] is True
            if model == "qwen-image-3.0":
                assert body["parameters"]["enable_thinking"] is False
            else:
                assert "enable_thinking" not in body["parameters"]
            return httpx.Response(200, json={"output": {"choices": [{"message": {"content": [{"image": "https://dashscope-result-sh.oss-cn-shanghai.aliyuncs.com/output.png"}]}}]}})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=_png_bytes(), headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    result = asyncio.run(image_generation.generate_image("小猫"))
    assert result["model"] == model
    assert len(requests) == 2


def test_documented_a717_acceleration_result_is_saved_without_sending_api_key(monkeypatch, generation_env):
    requests = []
    url = "https://dashscope-a717.oss-accelerate.aliyuncs.com/output.png?Expires=123&Signature=test"

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json=_successful_result(url))
        assert str(request.url) == url
        assert "authorization" not in request.headers
        return httpx.Response(200, content=_png_bytes(), headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    result = asyncio.run(image_generation.generate_image("小猫"))
    assert len(requests) == 2
    assert (generation_env / result["image_path"].split("/")[-1]).read_bytes() == _png_bytes()


def test_native_error_is_safe_without_fallback(monkeypatch, generation_env):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"code": "DataInspectionFailed", "message": "private provider detail"})

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="内容检查") as error:
        asyncio.run(image_generation.generate_image("小猫"))
    assert "private" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("data", [
    None,
    {},
    {"output": None},
    {"output": {"choices": []}},
    {"output": {"choices": [{"message": {"content": [{"text": "没有图片"}]}}]}},
    {"output": {"choices": [{"message": {"content": [{"image": _RESULT_URL}, {"image": _RESULT_URL}]}}]}},
])
def test_missing_or_multiple_images_are_rejected_without_retry(monkeypatch, generation_env, data):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=data)

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError):
        asyncio.run(image_generation.generate_image("小猫"))
    assert len(calls) == 1
    assert list(generation_env.iterdir()) == []


def test_failed_atomic_save_cleans_temporary_file(monkeypatch, generation_env):
    def failed_replace(*args):
        raise OSError("private filesystem details")

    monkeypatch.setattr(image_generation.os, "replace", failed_replace)
    with pytest.raises(image_generation.ImageGenerationError, match="无法保存") as error:
        image_generation._persist_png(_png_bytes())
    assert "private" not in str(error.value)
    assert list(generation_env.iterdir()) == []


@pytest.mark.parametrize(("status", "code", "expected"), [
    (429, "Throttling", "繁忙"),
    (403, "AccessDenied", "模型权限"),
    (401, "InvalidApiKey", "模型权限"),
    (404, "ModelNotFound", "模型权限"),
    (400, "DataInspectionFailed", "内容检查"),
    (500, "InternalError", "没有生成成功"),
    (200, "InvalidParameter", "没有生成成功"),
])
def test_provider_errors_are_safe_and_never_retry(monkeypatch, generation_env, status, code, expected):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": code, "message": "unit-test-secret-key provider private detail"}})

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match=expected) as error:
        asyncio.run(image_generation.generate_image("小猫"))
    assert "private" not in str(error.value)
    assert "unit-test" not in str(error.value)
    assert len(calls) == 1
    assert list(generation_env.iterdir()) == []


@pytest.mark.parametrize("url", [
    "http://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/image.png",
    "https://127.0.0.1/image.png",
    "https://[::1]/image.png",
    "https://169.254.169.254/latest/meta-data",
    "https://example.com/image.png",
    "https://attacker.oss-cn-shenzhen.aliyuncs.com/image.png",
    "https://attacker.oss-accelerate.aliyuncs.com/image.png",
    "https://dashscope-attacker.oss-accelerate.aliyuncs.com/image.png",
    "https://dashscope-a717.oss-accelerate.aliyuncs.com.evil.example/image.png",
    "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com.evil.example/image.png",
    "https://user:password@dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/image.png",
    "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com:8080/image.png",
    "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/image.png#fragment",
    "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com\\@example.com/image.png",
    "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/image\n.png",
    None,
])
def test_untrusted_result_urls_never_reach_download(monkeypatch, generation_env, url):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=_successful_result(url))

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="地址无效"):
        asyncio.run(image_generation.generate_image("小猫"))
    assert len(calls) == 1
    assert list(generation_env.iterdir()) == []


@pytest.mark.parametrize(("status", "headers", "body"), [
    (302, {"Location": "http://127.0.0.1/secret"}, b""),
    (200, {"Content-Type": "text/html"}, b"<html>private</html>"),
    (200, {"Content-Type": "image/png"}, b"\x89PNG\r\n\x1a\nnot an image"),
    (200, {"Content-Type": "image/png", "Content-Length": str(21 * 1024 * 1024)}, b"tiny"),
])
def test_invalid_downloads_and_redirects_leave_no_files(monkeypatch, generation_env, status, headers, body):
    calls = []

    async def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json=_successful_result())
        return httpx.Response(status, headers=headers, content=body)

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError):
        asyncio.run(image_generation.generate_image("小猫"))
    assert len(calls) == 2
    assert list(generation_env.iterdir()) == []


def test_download_checks_size_without_content_length(monkeypatch, generation_env):
    monkeypatch.setattr(image_generation, "_MAX_IMAGE_BYTES", 5)

    async def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json=_successful_result())
        response = httpx.Response(200, headers={"Content-Type": "image/png"}, content=b"more than five")
        del response.headers["content-length"]
        return response

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="文件过大"):
        asyncio.run(image_generation.generate_image("小猫"))
    assert list(generation_env.iterdir()) == []


def test_pixel_limit_checked_before_decoding(monkeypatch, generation_env):
    monkeypatch.setattr(image_generation, "_MAX_IMAGE_PIXELS", 1)
    with pytest.raises(image_generation.ImageGenerationError, match="尺寸过大"):
        image_generation._persist_png(_png_bytes())
    assert list(generation_env.iterdir()) == []


def test_cancelled_download_closes_stream_and_leaves_no_file(monkeypatch, generation_env):
    async def scenario():
        started = asyncio.Event()
        closed = asyncio.Event()

        class SlowImage(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"\x89PNG\r\n\x1a\n"
                started.set()
                await asyncio.Event().wait()

            async def aclose(self):
                closed.set()

        async def handler(request):
            if request.method == "POST":
                return httpx.Response(200, json=_successful_result())
            return httpx.Response(200, headers={"Content-Type": "image/png"}, stream=SlowImage())

        _mock_transport(monkeypatch, handler)
        task = asyncio.create_task(image_generation.generate_image("小猫"))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()

    asyncio.run(scenario())
    assert list(generation_env.iterdir()) == []


def test_total_timeout_is_safe_and_does_not_retry(monkeypatch, generation_env):
    monkeypatch.setattr(image_generation, "_TIMEOUT_SECONDS", 0.01)
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.Event().wait()

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="等待超时"):
        asyncio.run(image_generation.generate_image("小猫"))
    assert len(calls) == 1
    assert list(generation_env.iterdir()) == []


@pytest.mark.parametrize(("prompt", "ratio", "key", "expected"), [
    (" ", "1:1", "test-key", "描述"),
    ("小猫", "99:1", "test-key", "比例"),
    ("小猫", "1:1", "", "尚未配置"),
])
def test_invalid_configuration_or_input_never_calls_provider(monkeypatch, generation_env, prompt, ratio, key, expected):
    monkeypatch.setenv("DASHSCOPE_API_KEY", key)

    async def handler(request):
        pytest.fail("invalid input must not create a charged generation")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match=expected):
        asyncio.run(image_generation.generate_image(prompt, ratio))


def _reference_png(generation_env, data=None):
    filename = "generated_" + "d" * 32 + ".png"
    source = generation_env / filename
    source.write_bytes(_png_bytes((960, 1280)) if data is None else data)
    return f"/uploads/{filename}", source


def _reference_pngs(generation_env):
    selected = []
    for marker, size in [("a", (1280, 960)), ("b", (640, 960)), ("c", (1024, 1024))]:
        filename = "generated_" + marker * 32 + ".png"
        source = generation_env / filename
        source.write_bytes(_png_bytes(size))
        selected.append((f"/uploads/{filename}", source, size))
    return selected


def test_edit_mixes_uploaded_and_generated_references_in_selected_order(monkeypatch, generation_env):
    from utils.reference_images import prepare_reference_upload

    generated_path, generated_source = _reference_png(generation_env)
    uploaded = prepare_reference_upload(base64.b64encode(_png_bytes((800, 600))).decode("ascii"))
    uploaded_source = generation_env / uploaded["image_path"].split("/")[-1]
    selected = [uploaded["image_path"], generated_path]
    originals = [uploaded_source.read_bytes(), generated_source.read_bytes()]
    calls = []

    async def handler(request):
        calls.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["parameters"]["size"] == "800*600"
            assert body["parameters"]["prompt_extend"] is False
            expected = [{"image": "data:image/png;base64," + base64.b64encode(data).decode("ascii")} for data in originals]
            expected.append({"text": "将图1的主体放到图2的背景中"})
            assert body["input"]["messages"] == [{"role": "user", "content": expected}]
            return httpx.Response(200, json=_successful_result())
        assert "authorization" not in request.headers
        return httpx.Response(200, content=_png_bytes(), headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    result = asyncio.run(image_generation.edit_image("将图1的主体放到图2的背景中", selected))
    assert result["image_path"] not in selected
    assert uploaded_source.read_bytes() == originals[0]
    assert generated_source.read_bytes() == originals[1]
    assert len(calls) == 2


@pytest.mark.parametrize("failure", ["symlink", "corrupt", "too-large", "bad-path"])
def test_uploaded_reference_uses_same_strict_provider_boundary(monkeypatch, generation_env, failure):
    generated_path, generated_source = _reference_png(generation_env)
    reference_path = "/uploads/reference_" + "e" * 32 + ".png"
    reference_source = generation_env / reference_path.split("/")[-1]
    if failure == "symlink":
        reference_source.symlink_to(generated_source)
    elif failure == "corrupt":
        reference_source.write_bytes(b"private not png")
    elif failure == "too-large":
        with reference_source.open("wb") as source:
            source.truncate(image_generation._MAX_REFERENCE_IMAGE_BYTES + 1)
    else:
        reference_path = "/uploads/reference_../private.png"

    async def handler(request):
        pytest.fail("invalid uploaded reference must not reach provider")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError) as error:
        asyncio.run(image_generation.edit_image("融合两张参考", [generated_path, reference_path]))
    assert "private" not in str(error.value)
    assert generated_source.exists()


@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("aspect_ratio", [None, "9:16"])
def test_multi_reference_edit_preserves_selection_order_and_first_size(
    monkeypatch, generation_env, count, aspect_ratio
):
    available = _reference_pngs(generation_env)
    selected = [available[index] for index in (1, 2, 0)][:count]
    selected_paths = [path for path, _, _ in selected]
    originals = {source: source.read_bytes() for _, source, _ in available}
    prompt = "图1保留主体；参考图2的配色和图3的构图。完整保留文字『秋日新品』。"
    output = _png_bytes((640, 640))
    requests = []

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            first_width, first_height = selected[0][2]
            assert body["parameters"] == {
                "size": "864*1536" if aspect_ratio else f"{first_width}*{first_height}",
                "n": 1, "prompt_extend": False, "enable_thinking": False,
            }
            expected_content = [
                {"image": "data:image/png;base64," + base64.b64encode(originals[source]).decode("ascii")}
                for _, source, _ in selected
            ] + [{"text": prompt}]
            assert body["input"]["messages"] == [{"role": "user", "content": expected_content}]
            assert all(path.encode() not in request.content for path, _, _ in available)
            return httpx.Response(200, json=_successful_result())
        assert "authorization" not in request.headers
        return httpx.Response(200, content=output, headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    result = asyncio.run(image_generation.edit_image(prompt, selected_paths, aspect_ratio))
    assert result["image_path"] not in selected_paths
    assert result["model"] == "qwen-image-3.0"
    assert (result["width"], result["height"]) == (640, 640)
    assert selected_paths == [path for path, _, _ in selected]
    assert all(source.read_bytes() == contents for source, contents in originals.items())
    assert len(requests) == 2


@pytest.mark.parametrize("selection", [
    [],
    ["/uploads/generated_" + "a" * 32 + ".png"] * 2,
    ["/uploads/generated_" + marker * 32 + ".png" for marker in "abcd"],
    ["/uploads/generated_" + "a" * 32 + ".png", None],
    ["/uploads/generated_" + "a" * 32 + ".png", 123],
    ["/uploads/generated_" + "a" * 32 + ".png", []],
    ["/uploads/generated_" + "a" * 32 + ".png", ""],
    ["/uploads/generated_" + "a" * 32 + ".png", "/etc/passwd"],
    ("/uploads/generated_" + "a" * 32 + ".png",),
    {"image": "/uploads/generated_" + "a" * 32 + ".png"},
])
def test_multi_reference_invalid_selection_is_rejected_before_file_io_or_network(monkeypatch, generation_env, selection):
    def forbidden_open(*args, **kwargs):
        pytest.fail("invalid selection must not read any image")

    async def handler(request):
        pytest.fail("invalid selection must not reach provider")

    monkeypatch.setattr(image_generation.os, "open", forbidden_open)
    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError):
        asyncio.run(image_generation.edit_image("参考图1修改图2", selection))


@pytest.mark.parametrize("failure", ["missing", "corrupt", "oversized", "symlink", "pixels"])
def test_multi_reference_any_invalid_image_prevents_provider_call(monkeypatch, generation_env, failure):
    available = _reference_pngs(generation_env)
    second = available[1][1]
    if failure == "missing":
        second.unlink()
    elif failure == "corrupt":
        second.write_bytes(b"private corrupt bytes")
    elif failure == "oversized":
        with second.open("wb") as source:
            source.truncate(image_generation._MAX_REFERENCE_IMAGE_BYTES + 1)
    elif failure == "symlink":
        second.unlink()
        second.symlink_to(available[0][1])
    else:
        second.write_bytes(_png_bytes((2049, 2049)))
    untouched = {source: source.read_bytes() for _, source, _ in (available[0], available[2])}

    async def handler(request):
        pytest.fail("all references must validate before any provider request")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError) as error:
        asyncio.run(image_generation.edit_image("参考图1修改图2", [item[0] for item in available]))
    assert "private" not in str(error.value)
    assert all(source.read_bytes() == contents for source, contents in untouched.items())
    assert len(list(generation_env.iterdir())) == (2 if failure == "missing" else 3)


@pytest.mark.parametrize("failure", ["provider", "unsafe-url", "invalid-image", "redirect"])
def test_multi_reference_output_failures_keep_every_original_and_never_retry(monkeypatch, generation_env, failure):
    selected = _reference_pngs(generation_env)
    originals = {source: source.read_bytes() for _, source, _ in selected}
    calls = []

    async def handler(request):
        calls.append(request)
        if request.method == "POST":
            if failure == "provider":
                return httpx.Response(429, json={"code": "Throttling", "message": "private provider text"})
            url = "https://attacker.oss-accelerate.aliyuncs.com/image.png" if failure == "unsafe-url" else _RESULT_URL
            return httpx.Response(200, json=_successful_result(url))
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        return httpx.Response(200, content=b"private broken PNG", headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError) as error:
        asyncio.run(image_generation.edit_image("使用图1图2和图3的配色", [item[0] for item in selected]))
    assert "private" not in str(error.value)
    assert len(calls) == (1 if failure in {"provider", "unsafe-url"} else 2)
    assert all(source.read_bytes() == contents for source, contents in originals.items())
    assert len(list(generation_env.iterdir())) == 3


def test_cancelled_multi_reference_edit_preserves_all_originals(monkeypatch, generation_env):
    selected = _reference_pngs(generation_env)
    originals = {source: source.read_bytes() for _, source, _ in selected}

    async def scenario():
        started = asyncio.Event()

        async def handler(request):
            started.set()
            await asyncio.Event().wait()

        _mock_transport(monkeypatch, handler)
        task = asyncio.create_task(image_generation.edit_image("参考图1图2和图3", [item[0] for item in selected]))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert all(source.read_bytes() == contents for source, contents in originals.items())
    assert len(list(generation_env.iterdir())) == 3


@pytest.mark.parametrize(("aspect_ratio", "expected_size"), [(None, "960*1280"), ("16:9", "1536*864")])
def test_edit_sends_local_reference_as_base64_and_preserves_or_overrides_size(
    monkeypatch, generation_env, aspect_ratio, expected_size
):
    reference_path, source = _reference_png(generation_env)
    original = source.read_bytes()
    output = _png_bytes((640, 640))
    requests = []

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["model"] == "qwen-image-3.0"
            assert body["parameters"] == {
                "size": expected_size, "n": 1, "prompt_extend": False, "enable_thinking": False,
            }
            messages = body["input"]["messages"]
            assert len(messages) == 1 and messages[0]["role"] == "user"
            content = messages[0]["content"]
            assert len(content) == 2 and content[1] == {"text": "把背景改成暖黄色"}
            prefix, encoded = content[0]["image"].split(",", 1)
            assert prefix == "data:image/png;base64"
            assert base64.b64decode(encoded, validate=True) == original
            assert reference_path not in request.content.decode()
            return httpx.Response(200, json=_successful_result())
        assert "authorization" not in request.headers
        return httpx.Response(200, content=output, headers={"Content-Type": "image/png"})

    _mock_transport(monkeypatch, handler)
    result = asyncio.run(image_generation.edit_image(" 把背景改成暖黄色 ", reference_path, aspect_ratio))
    assert result["model"] == "qwen-image-3.0"
    assert (result["width"], result["height"]) == (640, 640)
    assert result["image_path"] != reference_path
    assert (generation_env / result["image_path"].split("/")[-1]).read_bytes() == output
    assert source.read_bytes() == original
    assert len(requests) == 2


@pytest.mark.parametrize("reference_path", [
    None,
    "",
    "/etc/passwd",
    "../generated_" + "d" * 32 + ".png",
    "/uploads/../generated_" + "d" * 32 + ".png",
    "/uploads/subdir/generated_" + "d" * 32 + ".png",
    "/uploads/" + "d" * 32 + ".png",
    "/uploads/generated_" + "d" * 32 + ".jpg",
    "/uploads/generated_" + "d" * 32 + ".png?download=1",
    "/uploads/generated_" + "d" * 32 + ".png\x00",
    "/uploads/%2e%2e/generated_" + "d" * 32 + ".png",
    "https://dashscope-a717.oss-accelerate.aliyuncs.com/image.png",
    "data:image/png;base64,AAAA",
])
def test_edit_rejects_invalid_reference_paths_before_file_read_or_network(monkeypatch, generation_env, reference_path):
    def forbidden_open(*args, **kwargs):
        pytest.fail("untrusted reference path must not reach file I/O")

    async def handler(request):
        pytest.fail("untrusted reference path must not reach provider")

    monkeypatch.setattr(image_generation.os, "open", forbidden_open)
    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片地址无效"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))


@pytest.mark.parametrize("outside", [False, True])
def test_edit_rejects_reference_symlinks_even_inside_uploads(monkeypatch, generation_env, outside):
    target = (generation_env.parent if outside else generation_env) / "reference-target.png"
    target.write_bytes(_png_bytes())
    reference_path = "/uploads/generated_" + "e" * 32 + ".png"
    source = generation_env / reference_path.split("/")[-1]
    source.symlink_to(target)

    async def handler(request):
        pytest.fail("reference symlink must not reach provider")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片地址无效"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))
    assert source.is_symlink()
    assert target.read_bytes() == _png_bytes()


def test_edit_rejects_oversized_reference_before_decode_or_network(monkeypatch, generation_env):
    reference_path, source = _reference_png(generation_env)
    with source.open("wb") as file:
        file.truncate(image_generation._MAX_REFERENCE_IMAGE_BYTES + 1)

    async def handler(request):
        pytest.fail("oversized reference must not reach provider")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="10MB"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))
    assert list(generation_env.iterdir()) == [source]


@pytest.mark.parametrize("malformed", [b"", b"\x89PNG\r\n\x1a\nnot a valid png", b"private file data"])
def test_edit_rejects_corrupt_or_nonimage_reference(monkeypatch, generation_env, malformed):
    reference_path, source = _reference_png(generation_env, malformed)

    async def handler(request):
        pytest.fail("corrupt reference must not reach provider")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片内容损坏") as error:
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))
    assert "private" not in str(error.value)
    assert source.read_bytes() == malformed
    assert list(generation_env.iterdir()) == [source]


def test_edit_rejects_non_png_and_oversized_pixel_count(monkeypatch, generation_env):
    async def handler(request):
        pytest.fail("invalid reference image must not reach provider")

    _mock_transport(monkeypatch, handler)
    jpeg = io.BytesIO()
    Image.new("RGB", (24, 16), "blue").save(jpeg, format="JPEG")
    reference_path, source = _reference_png(generation_env, jpeg.getvalue())
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片内容损坏"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))
    source.write_bytes(_png_bytes())
    monkeypatch.setattr(image_generation, "_MAX_IMAGE_PIXELS", 1)
    with pytest.raises(image_generation.ImageGenerationError, match="尺寸过大"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))


def test_edit_missing_reference_returns_safe_error(monkeypatch, generation_env):
    async def handler(request):
        pytest.fail("missing reference image must not reach provider")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片不存在") as error:
        asyncio.run(image_generation.edit_image("改成暖黄色", "/uploads/generated_" + "f" * 32 + ".png"))
    assert str(generation_env) not in str(error.value)


def test_edit_rejects_reference_directory_without_opening_provider(monkeypatch, generation_env):
    reference_path = "/uploads/generated_" + "f" * 32 + ".png"
    (generation_env / reference_path.split("/")[-1]).mkdir()

    async def handler(request):
        pytest.fail("directory reference must not reach provider")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片地址无效"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))


@pytest.mark.skipif(not hasattr(image_generation.os, "O_NOFOLLOW"), reason="platform does not support atomic no-follow open")
def test_edit_rejects_symlink_swapped_after_path_validation(monkeypatch, generation_env):
    reference_path, source = _reference_png(generation_env)
    target = generation_env.parent / "private-reference.png"
    target.write_bytes(_png_bytes())
    original_open = image_generation.os.open

    def swapping_open(file_path, flags, *args, **kwargs):
        assert file_path == str(source)
        source.unlink()
        source.symlink_to(target)
        return original_open(file_path, flags, *args, **kwargs)

    async def handler(request):
        pytest.fail("reference symlink swapped during open must not reach provider")

    monkeypatch.setattr(image_generation.os, "open", swapping_open)
    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError, match="参考图片不存在或无法读取"):
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))
    assert target.read_bytes() == _png_bytes()


@pytest.mark.parametrize("failure", ["provider", "unsafe-url", "invalid-image"])
def test_edit_provider_failures_keep_source_and_do_not_retry(monkeypatch, generation_env, failure):
    reference_path, source = _reference_png(generation_env)
    original = source.read_bytes()
    requests = []

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            if failure == "provider":
                return httpx.Response(429, json={"code": "Throttling", "message": "private provider detail"})
            return httpx.Response(200, json=_successful_result("http://127.0.0.1/private" if failure == "unsafe-url" else _RESULT_URL))
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=b"private damaged PNG")

    _mock_transport(monkeypatch, handler)
    with pytest.raises(image_generation.ImageGenerationError) as error:
        asyncio.run(image_generation.edit_image("改成暖黄色", reference_path))
    assert "private" not in str(error.value)
    assert len(requests) == (2 if failure == "invalid-image" else 1)
    assert source.read_bytes() == original
    assert list(generation_env.iterdir()) == [source]


def test_cancelled_edit_keeps_reference_and_creates_no_output(monkeypatch, generation_env):
    reference_path, source = _reference_png(generation_env)
    original = source.read_bytes()

    async def scenario():
        started = asyncio.Event()

        async def handler(request):
            started.set()
            await asyncio.Event().wait()

        _mock_transport(monkeypatch, handler)
        task = asyncio.create_task(image_generation.edit_image("改成暖黄色", reference_path))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert source.read_bytes() == original
    assert list(generation_env.iterdir()) == [source]


def _isolate_uploads(monkeypatch, tmp_path):
    import main
    from utils import media

    uploads = tmp_path / "private-generated"
    uploads.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(uploads))
    static = next(route.app for route in main.app.routes if getattr(route, "name", None) == "uploads")
    monkeypatch.setattr(static, "directory", str(uploads))
    monkeypatch.setattr(static, "all_directories", [str(uploads)])
    return uploads


@pytest.mark.parametrize("dev_mode", ["1", "0"])
def test_generated_images_require_owner_in_dev_and_production(client, monkeypatch, tmp_path, dev_mode):
    from auth import create_token
    import database

    uploads = _isolate_uploads(monkeypatch, tmp_path)
    filename = "generated_" + "a" * 32 + ".png"
    (uploads / filename).write_bytes(_png_bytes())
    url = f"/uploads/{filename}"

    async def seed():
        await database.get_or_create_user("image_owner")
        await database.get_or_create_user("image_other")

    asyncio.run(seed())
    owner_cookie = create_token("image_owner")
    assert asyncio.run(database.save_message("image_owner", "assistant", "你的图片", url)) is True
    other_cookie = create_token("image_other")
    client.cookies.clear()
    monkeypatch.setenv("DEV_MODE", dev_mode)

    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": f"Bearer {other_cookie}"}).status_code == 404
    owner = client.get(url, headers={"Cookie": f"fiona_token={owner_cookie}"})
    assert owner.status_code == 200
    assert owner.content == _png_bytes()
    assert owner.headers["cache-control"] == "private, no-store"
    assert client.head(url, headers={"Authorization": f"Bearer {owner_cookie}"}).status_code == 200
    download = client.get(url + "?download=1", headers={"Cookie": f"fiona_token={owner_cookie}"})
    assert download.content == owner.content
    assert download.headers["content-disposition"] == "attachment; filename*=UTF-8''" + filename
    assert client.get(url + "?download=1", headers={"Authorization": f"Bearer {other_cookie}"}).status_code == 404

    # A delayed/failed file removal still must revoke access once its message is deleted.
    asyncio.run(database.clear_message_history("image_owner"))
    assert (uploads / filename).exists()
    assert client.get(url, headers={"Authorization": f"Bearer {owner_cookie}"}).status_code == 404


def test_generated_image_delete_uses_existing_cleanup(client, dev_headers, monkeypatch, tmp_path):
    import aiosqlite
    import database

    uploads = _isolate_uploads(monkeypatch, tmp_path)
    filename = "generated_" + "b" * 32 + ".png"
    (uploads / filename).write_bytes(_png_bytes())
    url = f"/uploads/{filename}"

    async def seed():
        await database.get_or_create_user("smoke_tester")
        await database.save_message("smoke_tester", "assistant", "你的图片", url)
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute("SELECT id FROM messages WHERE image_path = ?", (url,)) as cursor:
                return (await cursor.fetchone())[0]

    message_id = asyncio.run(seed())
    assert client.get(url, headers=dev_headers).status_code == 200
    assert client.delete(f"/message/{message_id}", headers=dev_headers).status_code == 200
    assert not (uploads / filename).exists()
    assert client.get(url, headers=dev_headers).status_code == 404
    assert asyncio.run(database.get_pending_upload_cleanup()) == []


def test_existing_dev_upload_access_is_preserved(client, monkeypatch, tmp_path):
    uploads = _isolate_uploads(monkeypatch, tmp_path)
    (uploads / "existing.png").write_bytes(_png_bytes())
    assert client.get("/uploads/existing.png").status_code == 200


def test_generated_upload_normalization_cannot_bypass_owner(client, monkeypatch, tmp_path):
    uploads = _isolate_uploads(monkeypatch, tmp_path)
    filename = "generated_" + "c" * 32 + ".png"
    (uploads / filename).write_bytes(_png_bytes())
    assert client.get(f"/uploads/unused/%2e%2e/{filename}").status_code == 401
    assert client.get(f"/uploads//{filename}").status_code == 401
