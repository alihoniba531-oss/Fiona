"""R2 视觉配置、按调用读取、已报价快照与零请求价目闸。"""
import asyncio
from io import BytesIO
import json
from types import SimpleNamespace

from fastapi import HTTPException
from PIL import Image
import pytest

from studio import brain, config, pricing


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def image():
    output = BytesIO()
    Image.new("RGB", (20, 20)).save(output, "PNG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def vision_defaults(monkeypatch):
    monkeypatch.delenv("FIONA_STUDIO_VISION_MODEL", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-qwen-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")


def make_provider(provider, *, model=None, actual_model=None):
    requests, clients = [], []
    output = {key: {"passed": True, "notes": "可见结构正常。"}
              for key in ("structure", "materials", "physics", "realistic_frontal_face")}

    def create(**body):
        requests.append(body)
        return {"model": actual_model or body["model"],
                "choices": [{"message": {"content": json.dumps(output)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10}}

    def factory(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=lambda: None)

    if provider == "deepseek":
        instance = brain.DeepSeekProvider(api_key="offline-deepseek-key", client_factory=factory)
    else:
        instance = brain.QwenProvider(api_key="offline-qwen-key", model=model, client_factory=factory)
    return instance, requests, clients


def test_default_vision_model_and_empty_value_use_verified_model_without_warning(monkeypatch, capsys):
    assert config.get_settings().vision_model == "qwen3-vl-plus"
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "")
    assert config.get_settings().vision_model == "qwen3-vl-plus"
    assert "FIONA_STUDIO_VISION_MODEL" not in capsys.readouterr().out


@pytest.mark.parametrize("model", ["qwen3-vl-plus", "qwen-vl-max", "a1", "m" * 64, "a.b-c9"])
def test_valid_vision_ids_are_accepted_and_read_on_each_settings_call(monkeypatch, model):
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", model)
    assert config.get_settings().vision_model == model
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "another-vl")
    assert config.get_settings().vision_model == "another-vl"


@pytest.mark.parametrize("invalid", ["x", "UPPER-model", " model ", "bad/model", "bad_model", "bad:model", "m" * 65, "\n", "模型"])
def test_invalid_vision_ids_fall_back_and_warn_only_once(monkeypatch, capsys, invalid):
    config._INVALID_SETTINGS_WARNED.discard("FIONA_STUDIO_VISION_MODEL")
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", invalid)
    assert config.get_settings().vision_model == "qwen3-vl-plus"
    assert config.get_settings().vision_model == "qwen3-vl-plus"
    assert capsys.readouterr().out.count("FIONA_STUDIO_VISION_MODEL") == 1


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
@pytest.mark.parametrize("model", ["qwen3-vl-plus", "qwen-vl-max", "custom-vl"])
def test_both_platform_providers_route_images_to_configured_qwen_vision(monkeypatch, image, provider, model):
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", model)
    if model == "custom-vl":
        monkeypatch.setenv(pricing.brain_price_env(model), '{"input":1,"output":10}')
    instance, requests, clients = make_provider(provider)
    reply = run(instance.call("frame_qc", {"text": "检查结构。"}, images=image))
    assert len(requests) == 1 and requests[0]["model"] == model
    assert clients[0]["base_url"] == brain.QWEN_BASE_URL
    assert clients[0]["api_key"] == "offline-qwen-key"
    assert clients[0]["max_retries"] == 0
    assert reply.model == model and reply.warnings == [brain.VISION_WARNING.format(model=model)]
    assert brain.validate_reply("frame_qc", reply, {"text": "检查结构。"})[0]["structure"]["passed"] is True


def test_reused_provider_reads_configuration_on_each_call_including_constructor_snapshot(monkeypatch, image):
    first = config.get_settings().vision_model
    instance, requests, _ = make_provider("qwen", model=first)
    assert instance._vision_model_snapshot == first
    run(instance.call("frame_qc", "质检", images=image))
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "qwen-vl-max")
    run(instance.call("frame_qc", "质检", images=image))
    assert [request["model"] for request in requests] == [first, "qwen-vl-max"]


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
def test_pinned_quote_model_survives_configuration_change(monkeypatch, image, provider):
    quoted = config.get_settings().vision_model
    instance, requests, clients = make_provider(provider)
    instance.pin_vision_model(quoted)
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "qwen-vl-max")
    reply = run(instance.call("frame_qc", "质检", images=image))
    assert requests[0]["model"] == quoted and reply.model == quoted
    assert clients[0]["base_url"] == brain.QWEN_BASE_URL


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
def test_unknown_vision_price_blocks_direct_provider_call_before_sdk(monkeypatch, image, provider):
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "unpriced-vl")
    monkeypatch.delenv(pricing.brain_price_env("unpriced-vl"), raising=False)
    instance, requests, clients = make_provider(provider)
    with pytest.raises(HTTPException) as caught:
        run(instance.call("frame_qc", "质检", images=image))
    assert caught.value.status_code == 409
    assert pricing.brain_price_env("unpriced-vl") in caught.value.detail
    assert requests == [] and clients == []


async def available(username):
    return [{"id": "qwen", "label": "千问", "available": True, "model": "qwen3.8-max"},
            {"id": "deepseek", "label": "DeepSeek", "available": True, "model": "deepseek-v4-pro"}]


def test_get_provider_rejects_unpriced_vision_and_pins_priced_snapshot(monkeypatch, image):
    monkeypatch.setattr(brain, "provider_options", available)
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "unpriced-vl")
    monkeypatch.delenv(pricing.brain_price_env("unpriced-vl"), raising=False)
    with pytest.raises(HTTPException) as caught:
        run(brain.get_provider("deepseek", "owner", images=image))
    assert caught.value.status_code == 409
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "qwen3-vl-plus")
    instance = run(brain.get_provider("deepseek", "owner", images=image))
    assert instance.provider == "qwen" and instance.model == "qwen3-vl-plus"
    fake, requests, _ = make_provider("qwen")
    instance.client_factory = fake.client_factory
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "qwen-vl-max")
    run(instance.call("frame_qc", "质检", images=image))
    assert requests[0]["model"] == "qwen3-vl-plus"
    assert run(brain.get_provider("deepseek", "owner", images=image)).model == "qwen-vl-max"


def test_provider_options_reports_configured_vision_without_key_decryption(monkeypatch):
    from byok import crypto
    monkeypatch.setattr(crypto, "availability", lambda: (False, "未配置"))
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "custom-vl")
    options = run(brain.provider_options("owner"))
    assert all(option["vision_via"] == "custom-vl" for option in options if option["id"] != "claude")


def test_vision_warning_uses_actual_response_model(monkeypatch, image):
    instance, requests, _ = make_provider("qwen", actual_model="actual-fallback-vl")
    reply = run(instance.call("frame_qc", "质检", images=image))
    assert requests[0]["model"] == "qwen3-vl-plus" and reply.model == "actual-fallback-vl"
    assert reply.warnings == ["看图由千问视觉（actual-fallback-vl）完成"]
