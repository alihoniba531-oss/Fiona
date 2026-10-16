"""BYOK preset validation and shared SDK requests, with memory-only transports."""

import asyncio
import json
import os
import socket

import anthropic
import httpx
import httpx2
import openai
import pytest

from novel.byok_bridge import ByokBridge, ByokUnavailable, validate_config
from novel.deliberation import messages_for
from novel.llm_router import LLMRouter
from novel.run_store import ConfigurationError, RunStore


@pytest.fixture(autouse=True)
def no_network_or_environment_credentials(monkeypatch):
    monkeypatch.setattr(os, "environ", {})

    def blocked(*args, **kwargs):
        raise AssertionError("all P1 BYOK provider calls must use MockTransport")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.mark.parametrize("provider", ["custom", "moonshot", "zhipu", "ark"])
def test_unsupported_presets_are_rejected(provider):
    with pytest.raises(ConfigurationError, match="仅支持"):
        validate_config({"enabled": True, "provider": provider, "model": "anything"})


@pytest.mark.parametrize("provider", ["anthropic", "dashscope", "deepseek"])
def test_unknown_preset_models_are_rejected_before_any_call(provider):
    with pytest.raises(ConfigurationError, match="该模型暂不支持用于小说工坊"):
        validate_config({"enabled": True, "provider": provider, "model": "unknown-model"})


def test_public_description_does_not_decrypt_or_retain_key(monkeypatch):
    async def public(username):
        return {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "status": "ok"}

    async def forbidden(username):
        raise AssertionError("catalog must not decrypt a key")

    monkeypatch.setattr("novel.byok_bridge.byok_store.get_public_config", public)
    monkeypatch.setattr("novel.byok_bridge.byok_store.get_internal_config", forbidden)
    bridge = ByokBridge("offline-user")
    assert asyncio.run(bridge.describe()) == {
        "provider": "anthropic", "model": "claude-sonnet-5-5", "model_spec": "byok:self"}
    assert vars(bridge) == {"username": "offline-user"}


@pytest.mark.parametrize('failure,message',[
    ('needs_reentry','请重新填写自带模型 Key'),
    ('unavailable','服务器暂未开启自带模型，请稍后重试'),
])
def test_internal_byok_store_failures_become_fixed_recoverable_messages(monkeypatch,failure,message):
    from byok.errors import ByokUnavailableError, NeedsReentryError
    async def internal(username):
        cls=NeedsReentryError if failure=='needs_reentry' else ByokUnavailableError
        raise cls('PRIVATE-KEY-OR-PROVIDER-DETAIL')
    monkeypatch.setattr('novel.byok_bridge.byok_store.get_internal_config',internal)
    with pytest.raises(ByokUnavailable) as caught:
        asyncio.run(ByokBridge('offline-user').resolve())
    assert str(caught.value)==message
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize("provider,model", [
    ("anthropic", "claude-sonnet-5-5"), ("anthropic", "claude-haiku-5-5"),
    ("anthropic", "claude-opus-5-5"), ("dashscope", "qwen3.8-max"),
    ("deepseek", "deepseek-flash"),
])
def test_byok_reuses_nonstreaming_provider_seam_and_releases_key(
    tmp_path, monkeypatch, provider, model,
):
    sentinel = "NOVEL_BYOK_MEMORY_ONLY_SENTINEL"
    bodies, clients = [], []

    async def internal(username):
        return {"enabled": True, "status": "ok", "provider": provider, "model": model,
                "base_url": "https://must-never-be-used.invalid", "api_key": sentinel}

    monkeypatch.setattr("novel.byok_bridge.byok_store.get_internal_config", internal)
    _, messages = messages_for("editor", {
        "task": "decision", "brief": {"locked": {"world_rules": ["现实证据"]},
                                       "compass": {"theme": "选择"}, "chapter": 1},
    }, split_context=True)
    if provider == "anthropic":
        original = anthropic.AsyncAnthropic

        def handler(request):
            bodies.append(json.loads(request.content))
            assert request.headers["x-api-key"] == sentinel
            return httpx2.Response(200, json={
                "id": "msg_offline", "type": "message", "role": "assistant", "model": model,
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 20, "output_tokens": 5, "cache_read_input_tokens": 12}})

        def factory(**kwargs):
            assert kwargs["base_url"] == "https://api.anthropic.com"
            client = original(**kwargs, http_client=anthropic.DefaultAsyncHttpxClient(
                transport=httpx2.MockTransport(handler)))
            clients.append(client)
            return client

        monkeypatch.setattr(anthropic, "AsyncAnthropic", factory)
    else:
        original = openai.AsyncOpenAI

        def handler(request):
            bodies.append(json.loads(request.content))
            assert request.headers["authorization"] == "Bearer " + sentinel
            assert "must-never-be-used" not in str(request.url)
            return httpx.Response(200, json={
                "id": "chatcmpl_offline", "object": "chat.completion", "created": 1, "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"ok":true}'},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "prompt_cache_hit_tokens": 12}})

        def factory(**kwargs):
            client = original(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            clients.append(client)
            return client

        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

    bridge = ByokBridge("offline-user")
    store = RunStore(tmp_path, {})
    router = LLMRouter(store, byok_bridge=bridge)
    result = asyncio.run(router.call(step_key="steps/byok.json", role="editor", model="byok:self",
                                     messages=messages, max_tokens=100))
    assert result == {"ok": True}
    assert len(bodies) == 1
    assert router._clients == {}
    assert all(client.is_closed() for client in clients)
    assert vars(bridge) == {"username": "offline-user"}
    assert store.usage[0]["cached_tokens"] == 12
    assert sentinel not in json.dumps(store.read_json("steps/byok.json"))
    if provider == "anthropic":
        assert bodies[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
        first_user = bodies[0]["messages"][0]
        assert first_user["content"][0]["cache_control"] == {"type": "ephemeral"}
        # The mutable chapter payload must remain beyond the cached prefix.
        assert bodies[0]["messages"][1]["content"] == messages[2]["content"]
        expected = {"claude-sonnet-5-5": {"type": "between_tools"},
                    "claude-haiku-5-5": {"type": "disabled"}, "claude-opus-5-5": None}[model]
        assert bodies[0].get("thinking") == expected
    elif provider == "dashscope":
        assert bodies[0]["enable_thinking"] is False
    else:
        assert bodies[0]["thinking"] == {"type": "disabled"}
    assert "stream" not in bodies[0] or bodies[0]["stream"] is False
