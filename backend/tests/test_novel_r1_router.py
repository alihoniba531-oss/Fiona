"""Round-one routing regressions: SDK requests use in-memory transports only."""

import asyncio
import json
import os
import socket
from functools import wraps

import anthropic
import httpx
import httpx2
import openai
import pytest

from novel.fake_llm import FakeLLM
from novel.llm_router import (
    ConfigurationError, LLMRouter, StepFailed, is_retryable, validate_model_settings,
)
from novel.run_store import RunStore


def run_async(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapped


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    # Replace the mapping instead of reading, copying or preserving real keys.
    monkeypatch.setattr(os, "environ", {
        "ANTHROPIC_API_KEY": "offline-placeholder",
        "DASHSCOPE_API_KEY": "offline-placeholder",
        "DEEPSEEK_API_KEY": "offline-placeholder",
    })

    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def options(**overrides):
    values = {
        "step_key": "steps/r1.json", "role": "editor", "model": "fake:offline", "max_tokens": 100,
        "messages": [{"role": "system", "content": "只输出 JSON。"},
                     {"role": "user", "content": json.dumps({"task": "setup"})}],
    }
    values.update(overrides)
    return values


def raw_request(model):
    return {**options(model=model), "output": "json"}


def anthropic_response(model, reason="end_turn", raw='{"ok":true}'):
    return {
        "id": "msg_offline", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": raw}] if raw else [],
        "stop_reason": reason, "stop_sequence": None,
        "usage": {"input_tokens": 14, "output_tokens": 6, "cache_read_input_tokens": 4},
    }


@run_async
@pytest.mark.parametrize("model,thinking", [
    ("claude-sonnet-5-5", {"type": "between_tools"}),
    ("claude-haiku-5-5", {"type": "disabled"}),
    ("claude-opus-5-5", None),
])
async def test_claude_sdk_request_disables_thinking_by_model(tmp_path, model, thinking):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=anthropic_response(model))

    client = anthropic.AsyncAnthropic(
        api_key="offline-placeholder", base_url="https://api.anthropic.com", timeout=300, max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    router = LLMRouter(RunStore(tmp_path, {}))
    router._clients["anthropic"] = client
    try:
        raw, usage, reason = await router._single_real_call(raw_request(f"anthropic:{model}"))
    finally:
        await client.close()
    assert json.loads(raw) == {"ok": True}
    assert usage == {"input_tokens": 14, "output_tokens": 6, "cached_tokens": 4}
    assert reason == "end_turn"
    assert len(bodies) == 1
    assert bodies[0].get("thinking") == thinking
    assert ("thinking" in bodies[0]) == (thinking is not None)
    assert "output_config" not in bodies[0]


def test_unknown_claude_is_configuration_error_and_dry_run_is_exempt():
    with pytest.raises(ConfigurationError, match="未知的 Claude 型号，无法确定如何关闭思考") as failure:
        validate_model_settings(["anthropic:unknown"])
    assert failure.value.exit_code == 2
    validate_model_settings(["anthropic:unused"], dry_run=True)
    validate_model_settings(["fake:offline", "deepseek:unknown"])


@run_async
async def test_unknown_claude_never_constructs_client(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("client construction must follow model validation")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    with pytest.raises(ConfigurationError, match="未知的 Claude 型号"):
        await LLMRouter(RunStore(tmp_path, {}))._single_real_call(raw_request("anthropic:unknown"))


def test_opus_startup_notice_is_one_line_for_all_roles(capsys):
    validate_model_settings({"editor": "anthropic:claude-opus-5-5", "reviewer": "anthropic:claude-opus-5-5"})
    assert capsys.readouterr().out.splitlines() == ["opus-5-5 无法关闭思考，输出 token 会显著增加"]


@run_async
@pytest.mark.parametrize("reason", ["max_tokens", "refusal"])
async def test_anthropic_sdk_reads_stop_reason_even_with_empty_content(tmp_path, reason):
    model = "claude-haiku-5-5"
    client = anthropic.AsyncAnthropic(
        api_key="offline-placeholder", base_url="https://api.anthropic.com", max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=anthropic_response(model, reason, "")))),
    )
    router = LLMRouter(RunStore(tmp_path, {}))
    router._clients["anthropic"] = client
    try:
        raw, _, actual = await router._single_real_call(raw_request(f"anthropic:{model}"))
    finally:
        await client.close()
    assert raw == "" and actual == reason


@run_async
@pytest.mark.parametrize("provider", ["dashscope", "deepseek"])
@pytest.mark.parametrize("finish,expected", [("length", "max_tokens"), ("content_filter", "refusal"), ("stop", "stop")])
async def test_openai_sdk_normalizes_finish_reason(tmp_path, provider, finish, expected):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "chatcmpl_offline", "object": "chat.completion", "created": 1, "model": "offline",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"},
                         "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        })

    client = openai.AsyncOpenAI(
        api_key="offline-placeholder", base_url="https://provider.invalid/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router = LLMRouter(RunStore(tmp_path, {}))
    router._clients[provider] = client
    try:
        raw, _, reason = await router._single_real_call(raw_request(f"{provider}:offline"))
    finally:
        await client.close()
    assert raw == "{}" and reason == expected
    assert bodies[0]["response_format"] == {"type": "json_object"}


@run_async
@pytest.mark.parametrize("first", ['{"cut":', '{"valid_but_truncated":true}'])
async def test_truncation_repairs_once_and_records_reason(tmp_path, first):
    fake = FakeLLM({"setup": [(first, {"input_tokens": 3, "output_tokens": 4}, "max_tokens"),
                              ('{"ok":true}', {"input_tokens": 5, "output_tokens": 6}, "end_turn")]})
    store = RunStore(tmp_path, {})
    assert await LLMRouter(store, fake=fake).call(**options()) == {"ok": True}
    assert fake.call_count == 2
    assert "截断" in fake.calls[1]["messages"][-1]["content"]
    assert fake.calls[1]["messages"][-2] == {"role": "assistant", "content": first}
    assert [row["stop_reason"] for row in store.read_usage()] == ["max_tokens", "end_turn"]
    assert [row["ok"] for row in store.read_usage()] == [False, True]
    assert store.read_json("steps/r1.json")["stop_reason"] == "end_turn"


@run_async
@pytest.mark.parametrize("reasons", [("max_tokens", None), (None, "max_tokens"), ("max_tokens", "max_tokens")])
async def test_truncation_and_json_errors_share_one_repair(tmp_path, reasons):
    fake = FakeLLM({"setup": [("bad", {}, reasons[0]), ("still bad", {}, reasons[1]), {"third": True}]})
    store = RunStore(tmp_path, {})
    with pytest.raises(StepFailed) as failure:
        await LLMRouter(store, fake=fake).call(**options())
    assert fake.call_count == 2
    assert failure.value.step_key == "steps/r1.json"
    assert store.read_json("steps/r1.json")["attempts"] == 2
    assert store.read_json("manifest.json")["failed_step"] == "steps/r1.json"


@run_async
@pytest.mark.parametrize("raw", ["", "PRIVATE_REFUSAL_TEXT"])
async def test_refusal_never_retries_and_errors_are_enum_only(tmp_path, raw):
    fake = FakeLLM({"setup": [(raw, {"input_tokens": 2, "output_tokens": 1}, "refusal"), {"unused": True}]})
    store = RunStore(tmp_path, {})
    with pytest.raises(StepFailed) as failure:
        await LLMRouter(store, fake=fake).call(**options(failure_status="decision_invalid"))
    assert fake.call_count == 1
    assert failure.value.status == "step_failed" and failure.value.step_key == "steps/r1.json"
    step = store.read_json("steps/r1.json")
    assert step["status"] == "step_failed" and step["errors"] == ["refusal"]
    assert step["stop_reason"] == "refusal"
    assert store.read_usage()[0]["stop_reason"] == "refusal"
    assert store.read_usage()[0]["ok"] is False
    assert store.read_json("manifest.json")["failed_step"] == "steps/r1.json"


@run_async
@pytest.mark.parametrize("raw,expected", [("not json", "not json"), ("", "（上一轮输出为空）")])
async def test_repair_replays_assistant_before_correction(tmp_path, raw, expected):
    fake = FakeLLM({"setup": [raw, {"fixed": True}]})
    assert await LLMRouter(RunStore(tmp_path, {}), fake=fake).call(**options()) == {"fixed": True}
    second = fake.calls[1]["messages"]
    assert [message["role"] for message in second] == ["system", "user", "assistant", "user"]
    assert second[-2]["content"] == expected


def connection_error(kind):
    request = httpx.Request("POST", "https://provider.invalid")
    request2 = httpx2.Request("POST", "https://provider.invalid")
    if kind == "openai":
        return openai.APIConnectionError(request=request)
    if kind == "openai_subclass":
        class Subclass(openai.APIConnectionError):
            pass
        return Subclass(request=request)
    if kind == "anthropic":
        return anthropic.APIConnectionError(request=request2)
    if kind == "anthropic_subclass":
        class Subclass(anthropic.APIConnectionError):
            pass
        return Subclass(request=request2)
    module, exception_name = kind.split(".")
    library = httpx if module == "httpx" else httpx2
    return getattr(library, exception_name)("PRIVATE_NETWORK_TEXT", request=request if module == "httpx" else request2)


@run_async
@pytest.mark.parametrize("kind", ["openai", "openai_subclass", "anthropic", "anthropic_subclass",
                                 "httpx.ConnectError", "httpx.RemoteProtocolError",
                                 "httpx2.ConnectError", "httpx2.RemoteProtocolError"])
async def test_connection_failures_wait_five_seconds_and_retry_once(tmp_path, monkeypatch, kind):
    failure = connection_error(kind)
    assert is_retryable(failure)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("novel.llm_router.asyncio.sleep", sleep)
    fake = FakeLLM({"setup": [failure, {"ok": True}]})
    assert await LLMRouter(RunStore(tmp_path, {}), fake=fake).call(**options()) == {"ok": True}
    assert sleeps == [5] and fake.call_count == 2


@run_async
@pytest.mark.parametrize("status,exception_name,calls", [(400, "BadRequestError", 1), (429, "RateLimitError", 2)])
async def test_sdk_failure_persists_only_exception_class_http_status_and_step(tmp_path, monkeypatch, status, exception_name, calls):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(status, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                    "message": "PRIVATE_PROVIDER_TEXT"}})

    async def sleep(seconds):
        assert seconds == 5

    monkeypatch.setattr("novel.llm_router.asyncio.sleep", sleep)
    client = anthropic.AsyncAnthropic(
        api_key="offline-placeholder", base_url="https://api.anthropic.com", max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    store = RunStore(tmp_path, {})
    router = LLMRouter(store)
    router._clients["anthropic"] = client
    try:
        with pytest.raises(StepFailed) as failure:
            await router.call(**options(model="anthropic:claude-haiku-5-5"))
    finally:
        await client.close()
    assert len(requests) == calls
    assert failure.value.step_key == "steps/r1.json"
    assert store.read_json("steps/r1.json")["errors"] == [exception_name, f"HTTP {status}"]
    assert store.read_json("manifest.json")["failed_step"] == "steps/r1.json"
    assert "PRIVATE_PROVIDER_TEXT" not in store._path("steps/r1.json").read_text()


@run_async
async def test_successful_resume_clears_previous_failed_step(tmp_path):
    store = RunStore(tmp_path, {})
    with pytest.raises(StepFailed):
        await LLMRouter(store, fake=FakeLLM({"setup": [RuntimeError("private")]})).call(**options())
    resumed = RunStore(tmp_path, {})
    assert await LLMRouter(resumed, fake=FakeLLM({"setup": [{"ok": True}]})).call(**options()) == {"ok": True}
    assert resumed.read_json("manifest.json")["failed_step"] is None
