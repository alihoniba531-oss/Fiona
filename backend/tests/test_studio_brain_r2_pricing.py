"""R2: vision price admission and CNY bookkeeping without any network."""
import asyncio
from decimal import Decimal
import io
import json
from types import SimpleNamespace

from fastapi import HTTPException
from PIL import Image
import pytest

import database
from studio import brain, brain_jobs, pricing, store


OUTPUT = {name: {"passed": True, "notes": "结构可辨认。"}
          for name in ("structure", "materials", "physics", "realistic_frontal_face")}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def vision(monkeypatch, client):
    owner = "r2-vision-price-author"
    run(database.get_or_create_user(owner))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-dashscope-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    monkeypatch.delenv("FIONA_STUDIO_VISION_MODEL", raising=False)
    image = io.BytesIO()
    Image.new("RGB", (32, 32)).save(image, format="PNG")
    return owner, [image.getvalue()]


@pytest.fixture
def sdk(monkeypatch):
    import openai
    calls = []

    def construct(**settings):
        calls.append({"settings": settings})
        def create(**body):
            calls.append({"body": body})
            return SimpleNamespace(model=body["model"], usage={"prompt_tokens": 100, "completion_tokens": 50},
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(OUTPUT)), finish_reason="stop")])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=lambda: None)

    monkeypatch.setattr(openai, "OpenAI", construct)
    return calls


def test_new_and_legacy_vision_prices_and_environment_override(monkeypatch):
    monkeypatch.delenv("FIONA_STUDIO_PRICE_QWEN3_VL_PLUS", raising=False)
    assert pricing.brain_price("qwen3-vl-plus") == {
        "currency": "CNY", "input": Decimal("1"), "output": Decimal("10"), "cache_read": Decimal("1")}
    usage = {"input_tokens": 100, "output_tokens": 50}
    assert pricing.brain_actual_cost("qwen3-vl-plus", usage) == {"currency": "CNY", "amount": .0006}
    assert pricing.brain_actual_cost("qwen-vl-max", usage) == {"currency": "CNY", "amount": .00072}
    monkeypatch.setenv("FIONA_STUDIO_PRICE_QWEN3_VL_PLUS", '{"input":2,"output":12,"cache_read":0.5}')
    assert pricing.brain_actual_cost("qwen3-vl-plus", usage) == {"currency": "CNY", "amount": .0008}


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
def test_unpriced_vision_is_409_and_zero_sdk_requests_or_jobs(vision, sdk, monkeypatch, provider):
    owner, images = vision
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "vision-unpriced-r2")
    monkeypatch.delenv("FIONA_STUDIO_PRICE_VISION_UNPRICED_R2", raising=False)
    with pytest.raises(HTTPException) as failure:
        run(brain.run_brain("frame_qc", {"text": "检查结构。"}, provider=provider, username=owner, images=images))
    assert failure.value.status_code == 409
    assert "FIONA_STUDIO_PRICE_VISION_UNPRICED_R2" in str(failure.value.detail)
    assert sdk == []
    async def count():
        async with store.connection() as db:
            async with db.execute("SELECT COUNT(*) FROM studio_jobs WHERE owner=?", (owner,)) as cursor:
                return (await cursor.fetchone())[0]
    assert run(count()) == 0


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
def test_custom_vision_prices_are_cny_and_use_configured_request_model(vision, sdk, monkeypatch, provider):
    owner, images = vision
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "vision-priced-r2")
    monkeypatch.setenv("FIONA_STUDIO_PRICE_VISION_PRICED_R2", '{"input":1.5,"output":12}')
    result = run(brain.run_brain("frame_qc", {"text": "检查结构。"}, provider=provider, username=owner, images=images))
    body = next(call["body"] for call in sdk if "body" in call)
    assert body["model"] == result.model == "vision-priced-r2"
    assert next(call["settings"] for call in sdk if "settings" in call)["base_url"] == brain.QWEN_BASE_URL
    assert result.cost == {"currency": "CNY", "amount": .00075}
    assert result.warnings == ["看图由千问视觉（vision-priced-r2）完成"]
    async def read():
        async with store.connection() as db:
            return await store._one(db, "SELECT * FROM studio_jobs WHERE owner=?", (owner,))
    job = run(read())
    assert job["provider"] == provider and job["currency"] == "CNY" and job["actual_cny"] == .00075
    assert job["cost"] == result.cost and job["reserved_cny"] == 0


def test_quoted_model_is_pinned_for_call_and_next_call_reads_new_config(vision, sdk, monkeypatch):
    owner, images = vision
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "vision-first-r2")
    for model in ("FIRST", "SECOND"):
        monkeypatch.setenv(f"FIONA_STUDIO_PRICE_VISION_{model}_R2", '{"input":1,"output":10}')
    original = brain_jobs._quote_item
    def change_config_after_quote(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "vision-second-r2")
        return result
    monkeypatch.setattr(brain_jobs, "_quote_item", change_config_after_quote)
    first = run(brain.run_brain("frame_qc", {"text": "检查结构。"}, provider="deepseek", username=owner, images=images))
    second = run(brain.run_brain("frame_qc", {"text": "检查结构。"}, provider="deepseek", username=owner, images=images))
    assert [call["body"]["model"] for call in sdk if "body" in call] == ["vision-first-r2", "vision-second-r2"]
    assert first.model == "vision-first-r2" and second.model == "vision-second-r2"


def test_price_removed_after_quote_rejects_before_sdk_and_releases_reserve(vision, sdk, monkeypatch):
    owner, images = vision
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "vision-price-removed-r2")
    variable = "FIONA_STUDIO_PRICE_VISION_PRICE_REMOVED_R2"
    monkeypatch.setenv(variable, '{"input":1,"output":10}')
    original = brain_jobs._quote_item
    def remove_price_after_quote(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.delenv(variable)
        return result
    monkeypatch.setattr(brain_jobs, "_quote_item", remove_price_after_quote)
    with pytest.raises(HTTPException) as failure:
        run(brain.run_brain("frame_qc", {"text": "检查结构。"}, provider="deepseek", username=owner, images=images))
    assert failure.value.status_code == 409 and sdk == []
    async def read():
        async with store.connection() as db:
            return await store._one(db, "SELECT * FROM studio_jobs WHERE owner=?", (owner,))
    job = run(read())
    assert job["status"] == "rejected" and job["cost"]["amount"] == 0
    assert job["reserved_cny"] == 0 and float(job["reserved_amount"]) == 0
