"""WO3e X7：工作室 DeepSeek 导演模型可选 V4.1 Flash（全离线）。"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import json

import httpx
import openai
import pytest

import database
from byok import crypto
from studio import brain, config, kb_trial, pricing, store
from studio.brain_tasks import get_task


def run(coro):
    return asyncio.run(coro)


def _quote_tags():
    return {"scene_type": "dialogue", "position": "body", "pace": "mid", "emotion": "克制",
            "cast_count": 2, "realism": "photoreal", "setting": "interior", "sensitive": []}


async def _quote_items(quote_id):
    async with store.connection() as db:
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=?", (quote_id,))
    return row["items"]["items"]


def _expected_item_amount(model: str, input_chars: int, task: str) -> float:
    spec = get_task(task)
    first = pricing.estimate_brain(model, input_chars, spec.max_tokens)["amount"]
    repair = pricing.estimate_brain_repair(model, input_chars, spec.max_tokens)["amount"]
    return float(pricing.money(Decimal(str(first)) + Decimal(str(repair))))


def _make_quote_owner(client, monkeypatch, owner="x7-quote-owner"):
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", owner)
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_DEFAULT", "deepseek")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    monkeypatch.setattr(crypto, "availability", lambda: (False, "offline"))
    run(database.get_or_create_user(owner))
    project = run(store.create_project(owner, "X7 DeepSeek 报价", "16:9"))
    run(store.set_review_provider(project["id"], owner, "deepseek"))
    return owner, project


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
def test_configured_model_is_used_by_provider_and_options(monkeypatch, model):
    monkeypatch.setenv("FIONA_STUDIO_DEEPSEEK_MODEL", model)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    monkeypatch.setattr(crypto, "availability", lambda: (False, "offline"))

    assert config.get_settings().deepseek_model == model
    instance = brain.DeepSeekProvider(api_key="offline")
    assert instance.model == model

    options = run(brain.provider_options("x7-owner"))
    deepseek = next(option for option in options if option["id"] == "deepseek")
    assert deepseek["model"] == model


def test_default_deepseek_model_is_flash(monkeypatch):
    monkeypatch.delenv("FIONA_STUDIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    monkeypatch.setattr(crypto, "availability", lambda: (False, "offline"))

    assert config.get_settings().deepseek_model == "deepseek-flash"
    assert brain.DeepSeekProvider(api_key="offline").model == "deepseek-flash"
    options = run(brain.provider_options("x7-owner"))
    deepseek = next(option for option in options if option["id"] == "deepseek")
    assert deepseek["model"] == "deepseek-flash"


def test_invalid_deepseek_model_warns_and_falls_back(monkeypatch):
    warnings = []
    monkeypatch.setenv("FIONA_STUDIO_DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setattr(config, "_warn", lambda name: warnings.append(name))

    assert config.get_settings().deepseek_model == "deepseek-flash"
    assert warnings == ["FIONA_STUDIO_DEEPSEEK_MODEL"]


def test_flash_price_can_be_overridden(monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO_PRICE_DEEPSEEK_FLASH",
                       '{"input":1,"output":4,"cache_read":0.02}')
    price = pricing.brain_price("deepseek-flash")
    assert price["currency"] == "CNY"
    assert price["input"] == Decimal("1")
    assert price["output"] == Decimal("4")
    assert price["cache_read"] == Decimal("0.02")


def test_run_brain_deepseek_posts_default_flash_model(client, monkeypatch):
    owner = "x7-run-owner"
    monkeypatch.delenv("FIONA_STUDIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")
    monkeypatch.setattr(crypto, "availability", lambda: (False, "offline"))
    run(database.get_or_create_user(owner))

    requests = []
    review = {"verdict": "ok", "summary": "审核通过", "issues": []}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={
            "id": "chatcmpl-x7", "object": "chat.completion", "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(review, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        })

    transport = httpx.MockTransport(handler)
    real_openai = openai.OpenAI

    def client_factory(**kwargs):
        kwargs["http_client"] = httpx.Client(transport=transport, trust_env=False)
        return real_openai(**kwargs)

    monkeypatch.setattr(openai, "OpenAI", client_factory)
    result = run(brain.run_brain(
        "cross_review",
        {"source_text": "面包房夜班。", "adaptation_scale": "适度", "shots": []},
        provider="deepseek", username=owner,
    ))

    assert len(requests) == 1
    assert requests[0]["model"] == "deepseek-flash"
    assert result.model == "deepseek-flash"
    assert result.output == review


def test_quote_prices_director_and_review_with_configured_model(client, monkeypatch):
    owner, project = _make_quote_owner(client, monkeypatch)
    scene = "面包房夜班。叶岚把钥匙放在操作台，周默说今晚他来收店。"
    tags = _quote_tags()

    monkeypatch.setenv("FIONA_STUDIO_DEEPSEEK_MODEL", "deepseek-flash")
    flash_quote = run(kb_trial.quote(project["id"], owner, scene, tags, 15, "wan",
                                    ["with_kb", "without_kb"]))
    flash_items = run(_quote_items(flash_quote["id"]))

    monkeypatch.setenv("FIONA_STUDIO_DEEPSEEK_MODEL", "deepseek-v4-pro")
    pro_quote = run(kb_trial.quote(project["id"], owner, scene, tags, 15, "wan",
                                  ["with_kb", "without_kb"]))
    pro_items = run(_quote_items(pro_quote["id"]))

    for items, model in ((flash_items, "deepseek-flash"), (pro_items, "deepseek-v4-pro")):
        assert len(items) == 4
        assert all(item["model"] == model for item in items)
        assert all(item["currency"] == "CNY" for item in items)

    flash_director = next(item for item in flash_items if item["role"] == "shot_plan")
    pro_director = next(item for item in pro_items if item["role"] == "shot_plan")
    expected_flash = _expected_item_amount("deepseek-flash", flash_director["input_chars"], "shot_plan")
    expected_pro = _expected_item_amount("deepseek-v4-pro", pro_director["input_chars"], "shot_plan")
    assert flash_director["amount"] == pytest.approx(expected_flash)
    assert pro_director["amount"] == pytest.approx(expected_pro)
    assert flash_director["amount"] != pytest.approx(expected_pro)

    flash_line = next(line for line in flash_quote["items"] if line["name"] == "导演拆镜（带知识库）")
    assert flash_line["est"] == pytest.approx(flash_director["amount"])
    assert flash_quote["total"] == pytest.approx(sum(line["est"] for line in flash_quote["items"]))
    assert flash_quote["currency"] == "CNY"

    flash_review = next(item for item in flash_items if item["role"] == "cross_review")
    pro_review = next(item for item in pro_items if item["role"] == "cross_review")
    assert flash_review["model"] == "deepseek-flash"
    assert pro_review["model"] == "deepseek-v4-pro"
    assert flash_review["amount"] != pytest.approx(pro_review["amount"])
