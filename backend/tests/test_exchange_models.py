"""Model selection and SDK calls use fake clients, never provider network I/O."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from test_agent_exchanges import exchange_model, pair, _invite, _act  # noqa: F401
from test_official_agent_exchanges import owner, official_cards, _start, _wait  # noqa: F401


class FakeClient:
    def __init__(self):
        self.options = []
        self.calls = []
        self.failure = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="  模型回复  "), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=17, completion_tokens=9),
        )


def test_default_official_configuration_uses_dashscope_without_changing_main(monkeypatch):
    import exchange_models

    monkeypatch.delenv("OFFICIAL_EXCHANGE_PROVIDER", raising=False)
    monkeypatch.delenv("OFFICIAL_EXCHANGE_MODEL", raising=False)
    main = exchange_models.get_exchange_model("main")
    official = exchange_models.get_exchange_model("official")
    assert main.provider == official.provider == "dashscope"
    assert main.model == official.model == exchange_models.MAIN_MODEL
    assert official.extra_body == exchange_models.MAIN_EXTRA_BODY
    monkeypatch.setenv("OFFICIAL_EXCHANGE_PROVIDER", "deepseek")
    assert exchange_models.get_exchange_model("main") == main
    assert exchange_models.get_exchange_model("official").model == "deepseek-v4-pro"


@pytest.mark.parametrize("slot,official_provider,override", [
    ("main", "deepseek", "custom-official-model"),
    ("official", "dashscope", ""),
    ("official", "deepseek", ""),
    ("official", "deepseek", "custom-official-model"),
])
def test_generate_routes_to_the_selected_sdk_and_records_public_provider_metadata(
    monkeypatch, slot, official_provider, override,
):
    import exchange_models
    import services.exchange_service as service

    monkeypatch.setenv("OFFICIAL_EXCHANGE_PROVIDER", official_provider)
    monkeypatch.setenv("OFFICIAL_EXCHANGE_MODEL", override)
    main_client, deepseek_client = FakeClient(), FakeClient()
    monkeypatch.setattr(service, "client", main_client)
    monkeypatch.setattr(service, "get_deepseek_client", lambda: deepseek_client)
    messages = [{"role": "user", "content": "本次交流内容"}]
    result = asyncio.run(service.generate_exchange_reply(messages, max_tokens=512, provider=slot))
    config = exchange_models.get_exchange_model(slot)
    chosen = deepseek_client if config.provider == "deepseek" else main_client
    unused = main_client if chosen is deepseek_client else deepseek_client
    assert len(chosen.calls) == 1 and unused.calls == []
    assert chosen.options == [{"timeout": service.MODEL_TIMEOUT_SECONDS, "max_retries": 0}]
    call = chosen.calls[0]
    assert call["model"] == config.model
    assert call["messages"] == messages and call["max_tokens"] == 512
    assert call["stream"] is False
    assert "tools" not in call and "api_key" not in call
    if config.provider == "deepseek":
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}
        assert "enable_thinking" not in call["extra_body"]
    else:
        assert call["extra_body"] == exchange_models.MAIN_EXTRA_BODY
    assert result == {"content": "模型回复", "input_tokens": 17, "output_tokens": 9,
                      "provider": config.provider, "model": config.model, "finish_reason": "stop"}
    assert set(config.public_metadata()) == {"provider", "model", "model_label"}


def test_missing_deepseek_credentials_do_not_fall_back_to_main(monkeypatch):
    import exchange_models
    import services.exchange_service as service

    exchange_models.get_deepseek_client.cache_clear()
    monkeypatch.setenv("OFFICIAL_EXCHANGE_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    main_client = FakeClient()
    monkeypatch.setattr(service, "client", main_client)
    monkeypatch.setattr(service, "get_deepseek_client", exchange_models.get_deepseek_client)
    try:
        with pytest.raises(ValueError, match="not configured"):
            asyncio.run(service.generate_exchange_reply([], max_tokens=512, provider="official"))
        assert main_client.calls == []
    finally:
        exchange_models.get_deepseek_client.cache_clear()


def test_deepseek_client_uses_only_server_key_and_fixed_official_endpoint(monkeypatch):
    import exchange_models

    calls = []
    marker = object()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "  TEST_ONLY_DEEPSEEK_KEY  ")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://untrusted.invalid")
    monkeypatch.setattr(exchange_models, "OpenAI", lambda **kwargs: calls.append(kwargs) or marker)
    exchange_models.get_deepseek_client.cache_clear()
    try:
        assert exchange_models.get_deepseek_client() is marker
        assert exchange_models.get_deepseek_client() is marker
        assert calls == [{"api_key": "TEST_ONLY_DEEPSEEK_KEY", "base_url": "https://api.deepseek.com", "timeout": 45.0, "max_retries": 0}]
    finally:
        exchange_models.get_deepseek_client.cache_clear()


def test_deepseek_failure_is_not_retried_or_sent_to_main(monkeypatch):
    import services.exchange_service as service

    monkeypatch.setenv("OFFICIAL_EXCHANGE_PROVIDER", "deepseek")
    main_client, deepseek_client = FakeClient(), FakeClient()
    deepseek_client.failure = RuntimeError("fake provider failure")
    monkeypatch.setattr(service, "client", main_client)
    monkeypatch.setattr(service, "get_deepseek_client", lambda: deepseek_client)
    with pytest.raises(RuntimeError, match="fake provider failure"):
        asyncio.run(service.generate_exchange_reply([], max_tokens=512, provider="official"))
    assert len(deepseek_client.calls) == 1 and main_client.calls == []


@pytest.mark.parametrize("kind", ["peer", "official"])
def test_successful_call_ledger_preserves_provider_and_model_per_speaker(
    client, owner, official_cards, pair, exchange_model, kind,
):
    import database
    from exchange_models import get_exchange_model

    if kind == "official":
        exchange_id = _start(client, owner, official_cards[0], max_turns=3)["exchange"]["id"]
        participant = owner
        slots = ["main", "official", "main", "official"]
    else:
        exchange_id = _invite(client, pair)["id"]
        assert _act(client, pair[1], exchange_id, "accept").status_code == 200
        participant = pair[0]
        slots = ["main", "main", "main"]
    final = _wait(client, participant, exchange_id)
    assert final["exchange"]["status"] == "completed"
    assert [call["provider"] for call in exchange_model.calls] == slots
    with sqlite3.connect(database.DB_PATH) as db:
        rows = db.execute("SELECT ordinal, kind, provider, model, status FROM agent_exchange_calls WHERE exchange_id=? ORDER BY ordinal", (exchange_id,)).fetchall()
    assert rows == [
        (index + 1, "summary" if index == len(slots) - 1 else "turn",
         get_exchange_model(slot).provider, get_exchange_model(slot).model, "succeeded")
        for index, slot in enumerate(slots)
    ]


@pytest.mark.parametrize("unit", ["长内容", "🧠🎥✨", '\x00"\\\n'], ids=["cjk", "emoji", "escaped-controls"])
def test_large_official_summary_keeps_full_ten_thousand_character_topic_and_every_turn(unit):
    import services.exchange_service as service

    end_marker = "TOPIC_FINAL_REQUIREMENT"
    topic = (unit * 10000)[:10000 - len(end_marker)] + end_marker
    assert len(topic) == 10000
    context = {
        "kind": "official", "topic": topic, "turn_count": 99, "max_turns": 99,
        "initiator": {"id": "test-own-agent", "display_name": "自己的分身"},
        "recipient": {"id": "official:creative-partner", "display_name": "官方搭档"},
        "messages": [{"display_name": f"发言者{number % 2}", "content": f"ROUND_{number:02d}最终结论 " + unit * 1200} for number in range(99)],
    }
    messages = service.build_exchange_messages(context, summary=True)
    assert len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) <= service.OFFICIAL_MAX_INPUT_BYTES
    payload = json.loads(messages[-1]["content"])
    assert payload["topic"] == topic and payload["topic"].endswith(end_marker)
    assert payload["history_excerpted"] is True
    assert len(payload["dialogue"]) == 99
    assert payload["dialogue"][-1]["content"].startswith("ROUND_98最终结论")
    assert all(turn["content"].startswith(f"ROUND_{number:02d}") for number, turn in enumerate(payload["dialogue"]))
    assert payload["progress"] == {"completed_replies": 99, "total_replies": 99}
