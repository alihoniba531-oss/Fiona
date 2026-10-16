"""Ark routing regressions: actual OpenAI SDK serialization, in memory only."""

import asyncio
import json
import os
import socket
from functools import wraps

import httpx
import openai
import pytest

from novel.llm_router import (
    ARK_MODELS, MODEL_ALLOWLISTS, POLLUTING_VARIABLES, PROVIDERS, ConfigurationError,
    LLMRouter, StepFailed, parse_model, validate_environment, validate_model_settings,
)
from novel.run_store import RunStore


RECOMMENDED = "doubao-seed-2-1-pro-260915"
PREVIOUS = "doubao-seed-2-1-pro-260628"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def run_async(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapped


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    # Replace the environment mapping; do not inspect or copy host credentials.
    monkeypatch.setattr(os, "environ", {"ARK_API_KEY": "offline-ark-placeholder"})

    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def options(model=RECOMMENDED, **overrides):
    values = {
        "step_key": "steps/ark.json", "role": "editor", "model": f"ark:{model}",
        "messages": [{"role": "system", "content": "只输出 JSON。"},
                     {"role": "user", "content": json.dumps({"task": "setup"})}],
        "max_tokens": 4242,
    }
    values.update(overrides)
    return values


def response(model, reason="stop", raw='{"ok":true}'):
    return {
        "id": "chatcmpl_ark_offline", "object": "chat.completion", "created": 1,
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": raw},
                     "finish_reason": reason}],
        "usage": {"prompt_tokens": 19, "completion_tokens": 7, "total_tokens": 26,
                  "prompt_tokens_details": {"cached_tokens": 5}},
    }


def mocked_sdk(monkeypatch, handler):
    """Capture router construction while preserving real SDK serialization."""
    original = openai.AsyncOpenAI
    parameters, clients = [], []

    def factory(**kwargs):
        parameters.append(dict(kwargs))
        client = original(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    return parameters, clients


def test_ark_provider_definition_and_exact_allowlist():
    assert PROVIDERS["ark"] == (BASE_URL, "ARK_API_KEY")
    assert ARK_MODELS == frozenset({RECOMMENDED, PREVIOUS})
    assert POLLUTING_VARIABLES == (
        "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_CUSTOM_HEADERS", "OPENAI_BASE_URL",
    )


def test_model_allowlists_are_only_for_ark():
    assert MODEL_ALLOWLISTS == {"ark": frozenset({RECOMMENDED, PREVIOUS})}
    assert ARK_MODELS is MODEL_ALLOWLISTS["ark"]


@pytest.mark.parametrize("model", [RECOMMENDED, PREVIOUS])
def test_ark_parse_accepts_both_allowed_models(model):
    assert parse_model(f"ark:{model}") == ("ark", model)


@pytest.mark.parametrize("model", ["unknown-model", "doubao-seed-2-1-pro", RECOMMENDED + " "])
@pytest.mark.parametrize("dry_run", [False, True])
def test_ark_unknown_model_is_configuration_error_even_in_dry_run(model, dry_run):
    with pytest.raises(ConfigurationError) as failure:
        validate_model_settings([f"ark:{model}"], dry_run=dry_run)
    assert failure.value.exit_code == 2
    assert str(failure.value) == "火山方舟型号未在白名单内"


def test_unknown_provider_error_mentions_ark():
    with pytest.raises(ConfigurationError) as failure:
        parse_model("volc:xxx")
    assert failure.value.exit_code == 2
    assert "ark" in str(failure.value)


@run_async
@pytest.mark.parametrize("model", [RECOMMENDED, PREVIOUS])
@pytest.mark.parametrize("output", ["json", "markdown"])
@pytest.mark.parametrize("finish,expected", [
    ("stop", "stop"), ("length", "max_tokens"), ("content_filter", "refusal"),
])
async def test_ark_sdk_serializes_request_and_normalizes_usage_and_finish_reason(
    tmp_path, monkeypatch, model, output, finish, expected,
):
    requests = []
    text = '{"ok":true}' if output == "json" else "# 正文\n本地测试。"

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response(model, finish, text))

    parameters, clients = mocked_sdk(monkeypatch, handler)
    router = LLMRouter(RunStore(tmp_path, {}))
    try:
        raw, usage, reason = await router._single_real_call({**options(model), "output": output})
    finally:
        for client in clients:
            await client.close()
    assert parameters == [{
        "base_url": BASE_URL, "api_key": "offline-ark-placeholder",
        "timeout": 300, "max_retries": 0,
    }]
    assert len(requests) == 1
    assert str(requests[0].url) == BASE_URL + "/chat/completions"
    assert requests[0].method == "POST"
    body = json.loads(requests[0].content)
    assert body["model"] == model
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 4242
    assert body["messages"] == options(model)["messages"]
    assert "enable_thinking" not in body
    assert "frequency_penalty" not in body
    assert "presence_penalty" not in body
    if output == "json":
        assert body["response_format"] == {"type": "json_object"}
    else:
        assert "response_format" not in body
    assert raw == text and reason == expected
    assert usage == {"input_tokens": 19, "output_tokens": 7, "cached_tokens": 5}


@run_async
@pytest.mark.parametrize("finish", ["length", "content_filter"])
async def test_ark_sdk_reads_finish_reason_when_content_is_empty(tmp_path, monkeypatch, finish):
    _, clients = mocked_sdk(
        monkeypatch, lambda request: httpx.Response(200, json=response(RECOMMENDED, finish, None)),
    )
    try:
        raw, _, reason = await LLMRouter(RunStore(tmp_path, {}))._single_real_call({
            **options(), "output": "json",
        })
    finally:
        for client in clients:
            await client.close()
    assert raw == ""
    assert reason == {"length": "max_tokens", "content_filter": "refusal"}[finish]


@run_async
@pytest.mark.parametrize("finishes,status,calls", [
    (["length", "stop"], "ok", 2),
    (["length", "length"], "step_failed", 2),
    (["content_filter"], "step_failed", 1),
])
async def test_ark_finish_reason_drives_shared_repair_and_persistence(
    tmp_path, monkeypatch, finishes, status, calls,
):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=response(RECOMMENDED, finishes[len(bodies) - 1]))

    parameters, clients = mocked_sdk(monkeypatch, handler)
    store = RunStore(tmp_path, {})
    try:
        if status == "ok":
            assert await LLMRouter(store).call(**options()) == {"ok": True}
        else:
            with pytest.raises(StepFailed):
                await LLMRouter(store).call(**options())
    finally:
        for client in clients:
            await client.close()
    assert len(bodies) == calls
    assert len(parameters) == 1
    step = store.read_json("steps/ark.json")
    assert step["status"] == status and step["attempts"] == calls
    expected = [{"length": "max_tokens", "content_filter": "refusal"}.get(value, value)
                for value in finishes]
    assert [row["stop_reason"] for row in store.read_usage()] == expected
    assert all(row["cached_tokens"] == 5 for row in store.read_usage())
    assert step["usage"] == {"input_tokens": 19 * calls, "output_tokens": 7 * calls,
                             "cached_tokens": 5 * calls}
    if calls == 2:
        assert [message["role"] for message in bodies[1]["messages"]] == [
            "system", "user", "assistant", "user",
        ]
        assert bodies[1]["messages"][-2]["content"] == '{"ok":true}'
        assert "截断" in bodies[1]["messages"][-1]["content"]
    else:
        assert step["errors"] == ["refusal"]


@run_async
async def test_ark_missing_key_is_rejected_before_sdk_construction(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", {})

    def forbidden(**kwargs):
        raise AssertionError("SDK must not be constructed without ARK_API_KEY")

    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    with pytest.raises(ConfigurationError) as failure:
        await LLMRouter(RunStore(tmp_path, {}))._single_real_call({**options(), "output": "json"})
    assert str(failure.value) == "缺少环境变量：ARK_API_KEY"
    assert failure.value.exit_code == 2


def test_ark_guard_does_not_inspect_unrelated_provider_keys():
    reads = []

    class Tracked(dict):
        def get(self, key, default=None):
            reads.append(key)
            if key.endswith("API_KEY") and key != "ARK_API_KEY":
                raise AssertionError("unrelated provider key inspected")
            return super().get(key, default)

    validate_environment(f"ark:{RECOMMENDED}", environ=Tracked(ARK_API_KEY="offline-only"))
    assert reads == [*POLLUTING_VARIABLES, "ARK_API_KEY"]


@pytest.mark.parametrize("pollution", POLLUTING_VARIABLES)
def test_ark_obeys_unchanged_pollution_guard_without_leaking_values(pollution):
    with pytest.raises(ConfigurationError) as failure:
        validate_environment(f"ark:{RECOMMENDED}", environ={
            "ARK_API_KEY": "offline-key-sentinel", pollution: "offline-pollution-sentinel",
        })
    assert str(failure.value) == "请先 unset 这些变量：" + pollution
    assert "sentinel" not in str(failure.value)


def test_ark_dry_run_never_inspects_environment():
    class Unreadable(dict):
        def get(self, *args, **kwargs):
            raise AssertionError("dry-run inspected environment")

    validate_environment(f"ark:{RECOMMENDED}", dry_run=True, environ=Unreadable())


@run_async
@pytest.mark.parametrize("dry_run", [False, True])
async def test_ark_unknown_model_never_enters_call_or_sdk(tmp_path, monkeypatch, dry_run):
    def forbidden(*args, **kwargs):
        raise AssertionError("unknown Ark model entered a call")

    router = LLMRouter(RunStore(tmp_path, {}, dry_run=dry_run), dry_run=dry_run)
    monkeypatch.setattr(router, "_single_real_call", forbidden)
    monkeypatch.setattr(router, "fake", forbidden)
    with pytest.raises(ConfigurationError) as failure:
        await router.call(**options("unknown-model"))
    assert str(failure.value) == "火山方舟型号未在白名单内"
    assert failure.value.exit_code == 2
    assert router.store.read_usage() == []
