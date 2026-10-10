"""SDK request-body and stream-lifecycle tests using offline transports/fakes."""
import base64
from copy import deepcopy
import json
import os
import socket
from threading import Event
from types import SimpleNamespace
import urllib.request

import httpcore
import httpcore2
import httpx
import httpx2
import openai
import pytest
import requests

from byok import client, crypto
from byok.errors import ByokTimeoutError, ByokUnavailableError, EmptyReplyError, RefusalError, error_category, error_message
from byok.providers import CLAUDE_MODELS, PROVIDERS
from persona import BASE_SAFETY_RULES
from utils import safe_http


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch, request):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    originals = {}
    for target, name in ((urllib.request, "urlopen"), (requests, "get"), (safe_http, "_open_pinned"), (socket, "getaddrinfo"), (httpcore.SyncBackend, "connect_tcp"), (httpcore.SyncBackend, "connect_unix_socket"), (httpx.HTTPTransport, "handle_request"), (httpx.AsyncHTTPTransport, "handle_async_request"), (httpx2.HTTPTransport, "handle_request"), (httpx2.AsyncHTTPTransport, "handle_async_request")):
        originals[(target, name)] = getattr(target, name)
        monkeypatch.setattr(target, name, blocked)
    originals[(httpcore2.SyncBackend, "connect_tcp")] = httpcore2.SyncBackend.connect_tcp
    monkeypatch.setattr(httpcore2.SyncBackend, "connect_tcp", blocked)
    monkeypatch.setattr(httpcore2.SyncBackend, "connect_unix_socket", blocked)
    if request.node.name.startswith(("test_r1_watchdog_real_loopback", "test_r2_loopback_interrupt_race")):
        # R1-6 explicitly permits only this loopback hanging-server test.
        # Server proxies are supported, but this test must connect locally.
        for name in list(os.environ):
            if name.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
                monkeypatch.delenv(name)
        def dns(host, *args, **kwargs):
            if host != "127.0.0.1":
                return blocked()
            return originals[(socket, "getaddrinfo")](host, *args, **kwargs)
        monkeypatch.setattr(socket, "getaddrinfo", dns)
        for module in (httpcore, httpcore2):
            original = originals[(module.SyncBackend, "connect_tcp")]

            def connect(self, host, port, *args, _original=original, **kwargs):
                if host != "127.0.0.1":
                    return blocked()
                return _original(self, host, port, *args, **kwargs)
            monkeypatch.setattr(module.SyncBackend, "connect_tcp", connect)
        for module in (httpx, httpx2):
            original = originals[(module.HTTPTransport, "handle_request")]

            def handle(self, request, _original=original):
                if request.url.host != "127.0.0.1":
                    return blocked()
                return _original(self, request)
            monkeypatch.setattr(module.HTTPTransport, "handle_request", handle)
    monkeypatch.setenv("FIONA_BYOK_SECRET", base64.urlsafe_b64encode(b"a" * 32).decode())
    for name in crypto.FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    yield
    assert not attempted, "network"


def _messages():
    return [
        {"role": "system", "content": "Account alice persona"},
        {"role": "assistant", "content": "old leading assistant"},
        {"role": "assistant", "content": "second leading assistant"},
        {"role": "user", "content": "first"}, {"role": "user", "content": "second"},
        {"role": "assistant", "content": "answer one"}, {"role": "assistant", "content": "answer two"},
        {"role": "user", "content": ""}, {"role": "user", "content": "   "}, {"role": "user", "content": "current"},
        {"role": "system", "content": "Read aloud for alice\n" + BASE_SAFETY_RULES},
    ]


def _config(provider, model=None):
    return {"provider": provider, "model": model or (CLAUDE_MODELS[0] if provider == "anthropic" else "unit-model"), "base_url": "https://api.example.net/v1" if provider == "custom" else None, "api_key": "sk-offline-1234", "enabled": True}


def _sse(text="好", finish="stop"):
    payload = {"id": "offline", "object": "chat.completion.chunk", "created": 0, "model": "unit", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}
    return ("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode()


def _real_openai_capture(monkeypatch, *, text="好", finish="stop"):
    real_constructor = openai.OpenAI
    calls, clients = [], []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(text, finish))

    def constructor(**kwargs):
        # Replace even a custom transport with a safe in-memory response.
        if "http_client" in kwargs:
            kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        sdk = real_constructor(**kwargs)
        clients.append((sdk, deepcopy({k: v for k, v in kwargs.items() if k != "http_client"})))
        return sdk
    monkeypatch.setattr(client.openai, "OpenAI", constructor)
    return calls, clients


def _assert_consolidated(messages):
    assert messages[0]["role"] == "user" and messages[-1]["role"] == "user"
    assert all(a["role"] != b["role"] for a, b in zip(messages, messages[1:]))
    assert all(message["content"] for message in messages)


@pytest.mark.parametrize("provider", ["dashscope", "deepseek", "moonshot", "zhipu", "custom"])
@pytest.mark.parametrize("mirror", [False, True])
def test_actual_openai_request_body_for_each_provider(monkeypatch, provider, mirror):
    calls, sdk_clients = _real_openai_capture(monkeypatch)
    messages = _messages()
    original = deepcopy(messages)
    stream = client.open_reply_stream(_config(provider), messages, mirror=mirror, username="alice")
    assert "".join(chunk.choices[0].delta.content or "" for chunk in stream) == "好"
    assert messages == original
    body = calls[0]
    assert body["max_tokens"] == (512 if mirror else 2048) and body["stream"] is True
    assert not {"temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty"} & body.keys()
    sent_systems = [m["content"] for m in body["messages"] if m["role"] == "system"]
    assert sum(system.count(BASE_SAFETY_RULES) for system in sent_systems) == 1
    assert sent_systems[-1].endswith(BASE_SAFETY_RULES)
    assert "alice" not in "\n".join(sent_systems)
    assert "（账号已隐藏）" in "\n".join(sent_systems)
    if provider == "dashscope":
        assert len(sent_systems) == 2 and body["messages"][-1]["role"] == "system"
        assert body["enable_thinking"] is False
    else:
        assert len(sent_systems) == 1
        _assert_consolidated(body["messages"][1:])
        if provider == "deepseek":
            assert body["thinking"] == {"type": "disabled"}
    sdk, kwargs = sdk_clients[0]
    assert kwargs["max_retries"] == 0 and kwargs["timeout"] == 60.0
    assert kwargs["api_key"] == "sk-offline-1234"
    assert kwargs["base_url"] == (_config(provider)["base_url"] if provider == "custom" else PROVIDERS[provider]["base_url"])
    assert sdk.is_closed()


class ClaudeStream:
    def __init__(self, texts, stop):
        self.text_stream = iter(texts)
        self.stop = stop
        self.closed = False

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="thinking")])

    def close(self):
        self.closed = True


class Manager:
    def __init__(self, stream):
        self.stream = stream
        self.exited = False

    def __enter__(self):
        return self.stream

    def __exit__(self, *args):
        self.exited = True
        self.stream.close()


def _anthropic_capture(monkeypatch, *, texts=("好",), stop="end_turn"):
    calls, clients, streams = [], [], []

    class Claude:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            self.messages = SimpleNamespace(stream=lambda **kw: self.start(False, kw))
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: self.start(True, kw)))
            clients.append(self)

        def start(self, beta, kwargs):
            calls.append((beta, kwargs))
            stream = ClaudeStream(texts, stop)
            streams.append(stream)
            return Manager(stream)

        def close(self):
            self.closed = True
    monkeypatch.setattr(client.anthropic, "Anthropic", Claude)
    return calls, clients, streams


@pytest.mark.parametrize("model", CLAUDE_MODELS)
@pytest.mark.parametrize("mirror", [False, True])
def test_anthropic_request_body_and_fallback_parameters(monkeypatch, model, mirror):
    calls, clients, streams = _anthropic_capture(monkeypatch)
    stream = client.open_reply_stream(_config("anthropic", model), _messages(), mirror=mirror, username="alice")
    assert [chunk.choices[0].delta.content for chunk in stream] == ["好"]
    beta, body = calls[0]
    assert body["model"] == model and body["max_tokens"] == (2048 if mirror else 4096)
    assert body["output_config"] == {"effort": "low"}
    assert not {"thinking", "temperature", "top_p", "top_k"} & body.keys()
    assert body["system"].endswith(BASE_SAFETY_RULES) and body["system"].count(BASE_SAFETY_RULES) == 1
    assert "alice" not in body["system"]
    assert not any(message["role"] == "system" for message in body["messages"])
    _assert_consolidated(body["messages"])
    if model != "claude-haiku-5-5":
        assert beta and body["fallbacks"] == "default"
        assert body["betas"] == ["server-side-fallback-2026-07-01"]
    else:
        assert not beta and "fallbacks" not in body and "betas" not in body
    assert clients[0].kwargs == {"api_key": "sk-offline-1234", "base_url": "https://api.anthropic.com", "timeout": 60.0, "max_retries": 0}
    assert clients[0].closed and streams[0].closed
    assert stream.stop_reason == "end_turn" and not stream.refused


@pytest.mark.parametrize("texts,stop", [((), "refusal"), (("partial",), "refusal"), ((), "max_tokens"), (("partial",), "max_tokens")])
def test_claude_final_semantics(monkeypatch, texts, stop):
    _anthropic_capture(monkeypatch, texts=texts, stop=stop)
    stream = client.open_reply_stream(_config("anthropic"), _messages(), mirror=False, username="alice")
    chunks = list(stream)
    assert "".join(c.choices[0].delta.content or "" for c in chunks) == "".join(texts)
    assert stream.stop_reason == stop and stream.refused == (stop == "refusal")
    if stop == "max_tokens":
        assert chunks[-1].choices[0].finish_reason == "length"


@pytest.mark.parametrize("mirror,limit", [(False, 4000), (True, 600)])
def test_character_limit_closes_both_resources(monkeypatch, mirror, limit):
    _, clients, streams = _anthropic_capture(monkeypatch, texts=("a" * (limit + 5), "must-not-be-read"))
    stream = client.open_reply_stream(_config("anthropic"), _messages(), mirror=mirror, username="alice")
    chunk = next(stream)
    assert len(chunk.choices[0].delta.content) == limit
    assert chunk.choices[0].finish_reason == "length"
    assert clients[0].closed and streams[0].closed
    assert list(stream) == []


def test_openai_length_and_explicit_close(monkeypatch):
    calls, clients = _real_openai_capture(monkeypatch, finish="length")
    stream = client.open_reply_stream(_config("deepseek"), _messages(), mirror=False, username="alice")
    chunk = next(stream)
    assert chunk.choices[0].finish_reason == "length"
    stream.close()
    assert clients[0][0].is_closed()
    assert len(calls) == 1


def test_watchdog_interrupts_blocking_stream_and_closes_client(monkeypatch):
    _, clients, streams = _anthropic_capture(monkeypatch)
    monkeypatch.setattr(client, "total_seconds", lambda: 0.02)
    started, released = Event(), Event()
    original_enter = Manager.__enter__

    def enter(manager):
        stream = original_enter(manager)
        stream.response = SimpleNamespace(extensions={"network_stream": SimpleNamespace(
            get_extra_info=lambda name: SimpleNamespace(shutdown=lambda how: released.set())
        )})

        def text_stream():
            started.set()
            assert released.wait(0.5), "watchdog did not shut down blocking read"
            raise OSError("provider private response must not leak")
            yield "unreachable"
        stream.text_stream = text_stream()
        return stream
    monkeypatch.setattr(Manager, "__enter__", enter)
    stream = client.open_reply_stream(_config("anthropic"), _messages(), mirror=False, username="alice")
    with pytest.raises(ByokTimeoutError):
        list(stream)
    assert started.is_set() and clients[0].closed and streams[0].closed


def test_connect_test_minimal_token_budgets_and_no_saved_state(monkeypatch):
    calls, clients = _real_openai_capture(monkeypatch)
    client.test_connection(_config("deepseek"))
    assert calls[0]["max_tokens"] == 16
    assert calls[0]["messages"][-1] == {"role": "user", "content": "只回复：好"}
    assert clients[0][0].is_closed()
    calls, clients, _ = _anthropic_capture(monkeypatch)
    client.test_connection(_config("anthropic"))
    assert calls[0][1]["max_tokens"] == 1024
    assert calls[0][1]["output_config"] == {"effort": "low"}
    assert calls[0][1]["messages"] == [{"role": "user", "content": "只回复：好"}]
    assert clients[0].closed


@pytest.mark.parametrize("stop,expected", [("refusal", RefusalError), ("end_turn", EmptyReplyError)])
def test_test_connection_reports_empty_and_refusal(monkeypatch, stop, expected):
    _anthropic_capture(monkeypatch, texts=(), stop=stop)
    with pytest.raises(expected):
        client.test_connection(_config("anthropic"))


@pytest.mark.parametrize("name", crypto.FORBIDDEN_ENV)
def test_polluted_environment_blocks_constructor(monkeypatch, name):
    monkeypatch.setenv(name, "must-not-appear-in-output")
    calls = []
    monkeypatch.setattr(client.openai, "OpenAI", lambda **kw: calls.append(kw))
    monkeypatch.setattr(client.anthropic, "Anthropic", lambda **kw: calls.append(kw))
    assert not crypto.availability()[0]
    for provider in ("deepseek", "anthropic"):
        with pytest.raises(ByokUnavailableError):
            client.open_reply_stream(_config(provider), _messages(), mirror=False, username="alice")
    assert not calls


@pytest.mark.parametrize("raw,expected", [("0", 8), ("65", 8), ("1", 1), ("64", 64), ("NaN", 8)])
def test_max_stream_settings_are_read_each_call(monkeypatch, raw, expected):
    monkeypatch.setenv("FIONA_BYOK_MAX_STREAMS", raw)
    assert client.max_streams() == expected


@pytest.mark.parametrize("status,category", [(401, "authentication"), (403, "authentication"), (404, "not_found"), (402, "quota"), (429, "quota"), (400, "bad_request"), (500, "other")])
def test_error_classification_never_repeats_provider_details(status, category):
    class ProviderError(Exception):
        status_code = status
    error = ProviderError("sk-private-key https://private.url private-model")
    assert error_category(error) == category
    message = error_message(error)
    assert "private" not in message and message.endswith("本条没有改用平台模型。")


def test_stream_construction_failure_closes_anthropic_client(monkeypatch):
    _, clients, _ = _anthropic_capture(monkeypatch)

    def fail(manager):
        raise OSError("private upstream failure")
    monkeypatch.setattr(Manager, "__enter__", fail)
    with pytest.raises(OSError):
        client.open_reply_stream(_config("anthropic"), _messages(), mirror=False, username="alice")
    assert clients[0].closed


def test_custom_constructor_failure_closes_http_client(monkeypatch):
    real_constructor = httpx.Client
    http_clients = []

    def http_constructor(**kwargs):
        instance = real_constructor(**kwargs)
        http_clients.append(instance)
        return instance

    def fail(**kwargs):
        raise OSError("constructor failed")
    monkeypatch.setattr(client.httpx, "Client", http_constructor)
    monkeypatch.setattr(client.openai, "OpenAI", fail)
    with pytest.raises(OSError):
        client.open_reply_stream(_config("custom"), _messages(), mirror=False, username="alice")
    assert http_clients[0].is_closed


@pytest.mark.parametrize("raw,expected", [("9", 120), ("241", 120), ("NaN", 120), ("inf", 120), ("10", 10), ("240", 240), ("", 120)])
def test_total_seconds_settings_are_read_each_call(monkeypatch, raw, expected):
    monkeypatch.setenv("FIONA_BYOK_TOTAL_SECONDS", raw)
    assert client.total_seconds() == expected


def test_watchdog_expires_during_stream_construction(monkeypatch):
    _, clients, streams = _anthropic_capture(monkeypatch)
    monkeypatch.setattr(client, "total_seconds", lambda: 0.02)
    expired = Event()
    original_expire = client._Resources.expire

    def expire(resources):
        original_expire(resources)
        expired.set()

    monkeypatch.setattr(client._Resources, "expire", expire)
    original_enter = Manager.__enter__

    def enter(manager):
        assert expired.wait(0.5), "watchdog did not mark construction as expired"
        assert not clients[0].closed
        return original_enter(manager)
    monkeypatch.setattr(Manager, "__enter__", enter)
    with pytest.raises(ByokTimeoutError):
        client.open_reply_stream(_config("anthropic"), _messages(), mirror=False, username="alice")
    assert clients[0].closed and streams[0].closed


def test_non_text_openai_events_are_not_emitted(monkeypatch):
    records = [SimpleNamespace(choices=[]), client._chunk(None), client._chunk("text")]
    closed = []

    class Stream:
        def __iter__(self):
            return iter(records)

        def close(self):
            closed.append("stream")
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: Stream())), close=lambda: closed.append("client"))
    monkeypatch.setattr(client.openai, "OpenAI", lambda **kwargs: fake)
    stream = client.open_reply_stream(_config("deepseek"), _messages(), mirror=False, username="alice")
    assert [chunk.choices[0].delta.content for chunk in stream] == ["text"]
    assert closed == ["stream", "client"]


def _claude_sse():
    events = [
        ("message_start", {"type": "message_start", "message": {"id": "msg_unit", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "好"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 1}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode()


@pytest.mark.parametrize("provider", ["deepseek", "moonshot", "zhipu", "custom"])
def test_r1_test_connection_omits_empty_system_openai(monkeypatch, provider):
    calls, _ = _real_openai_capture(monkeypatch)
    client.test_connection(_config(provider))
    assert calls[0]["messages"] == [{"role": "user", "content": "只回复：好"}]


def test_r1_test_connection_omits_system_anthropic_real_sdk(monkeypatch):
    import anthropic
    original = anthropic.Anthropic
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=_claude_sse())

    def constructor(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
        return original(**kwargs)
    monkeypatch.setattr(client.anthropic, "Anthropic", constructor)
    client.test_connection(_config("anthropic", "claude-haiku-5-5"))
    assert "system" not in bodies[0]
    assert bodies[0]["messages"] == [{"role": "user", "content": "只回复：好"}]


@pytest.mark.parametrize("name", ["ANTHROPIC_CUSTOM_HEADERS", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"])
@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
def test_r1_environment_audit_blocks_request_mutators(monkeypatch, name, provider):
    value = "untrusted-setting" if name == "ANTHROPIC_CUSTOM_HEADERS" else "example.invalid" if name.lower() == "no_proxy" else "http://proxy.example.invalid:8080"
    monkeypatch.setenv(name, value)
    if name == "ANTHROPIC_CUSTOM_HEADERS":
        constructed = []
        monkeypatch.setattr(client.openai, "OpenAI", lambda **kw: constructed.append(kw))
        monkeypatch.setattr(client.anthropic, "Anthropic", lambda **kw: constructed.append(kw))
        assert crypto.availability() == (False, "服务器暂未开启自带模型")
        with pytest.raises(ByokUnavailableError):
            client.open_reply_stream(_config(provider), _messages(), mirror=False, username="alice")
        assert not constructed
    else:
        assert crypto.availability() == (True, None)
        _assert_proxy_allows_sdk_constructor(monkeypatch, provider)


@pytest.mark.parametrize("module", [httpx, httpx2])
@pytest.mark.parametrize("kind", ["NetworkError", "ReadError", "WriteError", "RemoteProtocolError"])
def test_r1_direct_http_failure_classification(module, kind):
    error = getattr(module, kind)("private key URL and provider body")
    assert error_category(error) == "connection"
    assert error_message(error) == "你的模型调用失败：连不上该服务。本条没有改用平台模型。"


@pytest.mark.parametrize("code", ["insufficient_quota", "rate_limit_exceeded", "billing_not_active"])
def test_r1_openai_stream_quota_codes(code):
    error = openai.APIError("private details", httpx.Request("POST", "https://api.example.net"), body={"code": code, "message": "private"})
    assert error_category(error) == "quota"
    assert error_message(error) == "你的模型调用失败：额度不足或请求过于频繁。本条没有改用平台模型。"


@pytest.mark.parametrize("stream_error", [False, True])
def test_r1_anthropic_overloaded_error(stream_error):
    import anthropic
    if stream_error:
        error = anthropic.APIError("private", httpx2.Request("POST", "https://api.anthropic.com"), body={"type": "overloaded_error", "message": "private"})
    else:
        response = httpx2.Response(529, request=httpx2.Request("POST", "https://api.anthropic.com"))
        error = anthropic.OverloadedError("private", response=response, body={})
    assert error_category(error) == "busy"
    assert error_message(error) == "你的模型调用失败：服务繁忙，请稍后再试。本条没有改用平台模型。"


def test_r1_abort_interrupts_public_response_socket_before_close(monkeypatch):
    events = []

    class Sock:
        def shutdown(self, how):
            events.append(("shutdown", how))

        def close(self):
            events.append(("socket_close", None))
    socket_handle = Sock()
    stream = SimpleNamespace(response=SimpleNamespace(extensions={"network_stream": SimpleNamespace(get_extra_info=lambda info: socket_handle)}), close=lambda: events.append(("stream_close", None)))
    resources = client._Resources()
    resources.stream = stream
    resources.client = SimpleNamespace(close=lambda: events.append(("client_close", None)))
    reply = client.ReplyStream(resources, anthropic_stream=False, character_limit=4000)
    reply.abort()
    assert events == [("shutdown", socket.SHUT_RDWR)]
    reply.close()
    assert events[0] == ("shutdown", socket.SHUT_RDWR)
    assert [event[0] for event in events[1:]] == ["stream_close", "client_close"]
    assert not any(event[0] == "socket_close" for event in events)


def test_r1_custom_close_aborts_on_cancellation_not_just_timeout():
    events = []
    resources = client._Resources()
    resources.transport = SimpleNamespace(abort=lambda: events.append("abort"))
    resources.stream = SimpleNamespace(close=lambda: events.append("stream_close"))
    resources.client = SimpleNamespace(close=lambda: events.append("client_close"))
    resources.close()
    assert events == ["abort", "stream_close", "client_close"]


def test_r1_request_control_aborts_before_stream_construction_returns(monkeypatch):
    _, clients, _ = _anthropic_capture(monkeypatch)
    control = client.ReplyStreamControl()
    original_enter = Manager.__enter__

    def enter(manager):
        control.abort()
        assert not clients[0].closed
        return original_enter(manager)
    monkeypatch.setattr(Manager, "__enter__", enter)
    with pytest.raises(client.ReplyInterruptedError):
        client.open_reply_stream(_config("anthropic"), _messages(), mirror=False, username="alice", control=control)
    assert clients[0].closed


def test_r1_custom_http_client_parameters_locked(monkeypatch):
    calls = []
    real_http_client = httpx.Client

    def construct(**kwargs):
        calls.append(kwargs.copy())
        return real_http_client(**kwargs)

    class Stream:
        def __iter__(self):
            return iter([client._chunk("好")])

        def close(self):
            pass
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: Stream())), close=lambda: None)
    monkeypatch.setattr(client.httpx, "Client", construct)
    monkeypatch.setattr(client.openai, "OpenAI", lambda **kw: fake)
    reply = client.open_reply_stream(_config("custom"), _messages(), mirror=False, username="alice")
    list(reply)
    assert len(calls) == 1
    from byok.url_safety import PinnedTransport
    assert isinstance(calls[0]["transport"], PinnedTransport)
    assert calls[0]["follow_redirects"] is False
    assert calls[0]["trust_env"] is False
    assert calls[0]["timeout"] == 60.0


@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
def test_r1_watchdog_public_socket_interrupts_blocking_read(monkeypatch, provider):
    import time
    released = Event()
    closed = []
    monkeypatch.setattr(client, "total_seconds", lambda: 0.02)

    class Sock:
        def shutdown(self, how):
            assert how == socket.SHUT_RDWR
            released.set()

        def close(self):
            closed.append("socket")

    class Stream:
        response = SimpleNamespace(extensions={"network_stream": SimpleNamespace(get_extra_info=lambda name: Sock())})

        def texts(self):
            yield "partial"
            released.wait(0.3)
            raise OSError("blocking read interrupted")

        @property
        def text_stream(self):
            return self.texts()

        def __iter__(self):
            for text in self.texts():
                yield client._chunk(text)

        def close(self):
            # Closing a response alone deliberately does not release the read.
            closed.append("stream")
    stream = Stream()
    sdk = SimpleNamespace(close=lambda: closed.append("client"))
    if provider == "deepseek":
        sdk.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: stream))
        monkeypatch.setattr(client.openai, "OpenAI", lambda **kwargs: sdk)
    else:
        sdk.messages = SimpleNamespace(stream=lambda **kwargs: Manager(stream))
        monkeypatch.setattr(client.anthropic, "Anthropic", lambda **kwargs: sdk)
    model = "claude-haiku-5-5" if provider == "anthropic" else "unit"
    started = time.monotonic()
    reply = client.open_reply_stream(_config(provider, model), _messages(), mirror=False, username="alice")
    assert next(reply).choices[0].delta.content == "partial"
    with pytest.raises(ByokTimeoutError):
        list(reply)
    assert time.monotonic() - started < 0.2
    assert released.is_set() and "client" in closed and "stream" in closed


@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
def test_r1_watchdog_real_loopback(monkeypatch, provider):
    import errno
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import time

    release = Event()
    received = Event()
    # HTTPServer normally computes its name with reverse DNS after bind.
    monkeypatch.setattr(socket, "getfqdn", lambda *args: "localhost")
    fragment = _claude_sse().split(b"event: content_block_stop")[0] if provider == "anthropic" else _sse("partial", None).split(b"data: [DONE]")[0]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(f"{len(fragment):x}\r\n".encode() + fragment + b"\r\n")
            self.wfile.flush()
            received.set()
            release.wait(8)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except OSError as exc:
        if exc.errno in {errno.EPERM, errno.EACCES}:
            pytest.skip("R1-6 loopback bind is denied by sandbox permissions")
        raise
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setitem(PROVIDERS[provider], "base_url", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setattr(client, "total_seconds", lambda: 2.0)
    model = "claude-haiku-5-5" if provider == "anthropic" else "unit"
    started = time.monotonic()
    reply = None
    try:
        reply = client.open_reply_stream(_config(provider, model), [{"role": "user", "content": "test"}], mirror=False, username="alice")
        text = next(reply).choices[0].delta.content
        assert text == ("好" if provider == "anthropic" else "partial")
        assert received.wait(0.2)
        with pytest.raises(ByokTimeoutError):
            list(reply)
        assert time.monotonic() - started < 4.0
        assert reply.text_length == len(text)
    finally:
        if reply is not None:
            reply.close()
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("name", ["HtTpS_PrOxY", "nO_pRoXy"])
@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
def test_r1_mixed_case_proxy_environment_is_allowed(monkeypatch, name, provider):
    monkeypatch.setenv(name, "example.invalid" if name.lower() == "no_proxy" else "http://proxy.example.invalid:8080")
    assert crypto.availability() == (True, None)
    _assert_proxy_allows_sdk_constructor(monkeypatch, provider)


def _assert_proxy_allows_sdk_constructor(monkeypatch, provider):
    if provider == "anthropic":
        _, constructed, _ = _anthropic_capture(monkeypatch)
    else:
        _, constructed = _real_openai_capture(monkeypatch)
    reply = client.open_reply_stream(_config(provider), _messages(), mirror=False, username="alice")
    assert "".join(chunk.choices[0].delta.content or "" for chunk in reply) == "好"
    assert len(constructed) == 1
    assert constructed[0].closed if provider == "anthropic" else constructed[0][0].is_closed()


@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
def test_r1b_preset_sdk_reads_https_proxy_but_custom_does_not(monkeypatch, provider):
    # Construct the real SDK/default HTTP clients, without issuing a request.
    for name in list(os.environ):
        if name.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            monkeypatch.delenv(name)
    proxy_url = "http://proxy.example.invalid:8080"
    monkeypatch.setenv("HTTPS_PROXY", proxy_url)
    transport_proxies = []
    for module in (httpx, httpx2):
        original_init = module.HTTPTransport.__init__

        def record_transport(self, *args, _original=original_init, **kwargs):
            proxy = kwargs.get("proxy")
            if proxy is not None:
                transport_proxies.append(str(proxy.url) if hasattr(proxy, "url") else str(proxy))
            _original(self, *args, **kwargs)
        monkeypatch.setattr(module.HTTPTransport, "__init__", record_transport)

    constructors, sdk_clients = [], []
    original_openai = openai.OpenAI
    original_anthropic = client.anthropic.Anthropic

    def openai_constructor(**kwargs):
        constructors.append(("openai", kwargs.copy()))
        sdk = original_openai(**kwargs)
        monkeypatch.setattr(sdk.chat.completions, "create", lambda **kw: iter([client._chunk("好")]))
        sdk_clients.append(sdk)
        return sdk

    def anthropic_constructor(**kwargs):
        constructors.append(("anthropic", kwargs.copy()))
        sdk = original_anthropic(**kwargs)
        monkeypatch.setattr(sdk.messages, "stream", lambda **kw: Manager(ClaudeStream(("好",), "end_turn")))
        sdk_clients.append(sdk)
        return sdk

    monkeypatch.setattr(client.openai, "OpenAI", openai_constructor)
    monkeypatch.setattr(client.anthropic, "Anthropic", anthropic_constructor)
    assert crypto.availability() == (True, None)
    model = "claude-haiku-5-5" if provider == "anthropic" else None
    list(client.open_reply_stream(_config(provider, model), _messages(), mirror=False, username="alice"))
    assert proxy_url in transport_proxies
    assert "http_client" not in constructors[0][1]
    preset_proxy_count = len(transport_proxies)
    list(client.open_reply_stream(_config("custom"), _messages(), mirror=False, username="alice"))
    assert len(transport_proxies) == preset_proxy_count
    custom_http_client = constructors[-1][1]["http_client"]
    assert custom_http_client.trust_env is False
    assert all(sdk.is_closed() for sdk in sdk_clients)


@pytest.mark.parametrize("code", ["insufficient_quota", "rate_limit_exceeded", "billing_not_active"])
def test_r1_actual_openai_stream_error_quota(monkeypatch, code):
    original = openai.OpenAI
    body = ("data: " + json.dumps({"error": {"code": code, "message": "private-key-url-model"}}) + "\n\n").encode()

    def constructor(**kwargs):
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)), trust_env=False)
        return original(**kwargs)
    monkeypatch.setattr(client.openai, "OpenAI", constructor)
    reply = client.open_reply_stream(_config("deepseek"), _messages(), mirror=False, username="alice")
    with pytest.raises(openai.APIError) as caught:
        list(reply)
    assert error_category(caught.value) == "quota"
    assert "private" not in error_message(caught.value)


def test_r1_actual_anthropic_stream_overloaded(monkeypatch):
    import anthropic
    original = anthropic.Anthropic
    body = b'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"private-key-url-model"}}\n\n'

    def constructor(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(lambda request: httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)), trust_env=False)
        return original(**kwargs)
    monkeypatch.setattr(client.anthropic, "Anthropic", constructor)
    reply = client.open_reply_stream(_config("anthropic", "claude-haiku-5-5"), _messages(), mirror=False, username="alice")
    with pytest.raises(anthropic.APIError) as caught:
        list(reply)
    assert error_category(caught.value) == "busy"
    assert "private" not in error_message(caught.value)


@pytest.mark.parametrize("module", [httpx, httpx2])
def test_r1_network_error_subclasses_keep_connection_category(module):
    class VendorReadError(module.ReadError):
        pass
    assert error_category(VendorReadError("private")) == "connection"


@pytest.mark.parametrize("code", [{"unexpected": "private"}, ["insufficient_quota"]])
def test_r1_malformed_openai_error_codes_do_not_crash(code):
    error = openai.APIError("private-key-url-model", httpx.Request("POST", "https://api.example.net"), body={"code": code})
    assert error_category(error) == "other"
    assert error_message(error) == "你的模型调用失败：调用失败。本条没有改用平台模型。"


@pytest.mark.parametrize("interruption", ["watchdog", "control", "reply"])
def test_r2_interrupt_defers_all_close_to_owner(interruption):
    from threading import Thread, get_ident

    events = []
    interrupt_thread = get_ident()

    class Sock:
        def shutdown(self, how):
            events.append(("shutdown", get_ident()))
            assert how == socket.SHUT_RDWR

        def close(self):
            events.append(("socket_close", get_ident()))

    sock = Sock()
    resources = client._Resources()
    resources.stream = SimpleNamespace(
        response=SimpleNamespace(extensions={"network_stream": SimpleNamespace(get_extra_info=lambda name: sock)}),
        close=lambda: events.append(("stream_close", get_ident())),
    )
    resources.client = SimpleNamespace(close=lambda: events.append(("client_close", get_ident())))
    resources.http_client = SimpleNamespace(close=lambda: events.append(("http_client_close", get_ident())))
    resources.manager = SimpleNamespace(__exit__=lambda *args: events.append(("manager_exit", get_ident())))
    resources.transport = SimpleNamespace(abort=lambda: events.append(("transport_abort", get_ident())))
    control = client.ReplyStreamControl()
    control.bind(resources)
    reply = client.ReplyStream(resources, anthropic_stream=False, character_limit=4000)
    if interruption == "watchdog":
        resources.expire()
        assert resources.timed_out
    elif interruption == "control":
        control.abort()
        assert control.aborted
    else:
        reply.abort()
    assert resources.closed
    assert [name for name, _ in events] == ["shutdown", "transport_abort"]
    owner = Thread(target=reply.close)
    owner.start()
    owner.join(timeout=1)
    assert not owner.is_alive()
    closing = [(name, thread) for name, thread in events if name.endswith("close") or name == "manager_exit"]
    assert {name for name, _ in closing} == {"stream_close", "client_close", "http_client_close", "manager_exit"}
    assert all(thread != interrupt_thread for _, thread in closing)
    before = list(events)
    reply.close()
    assert events == before


@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
@pytest.mark.parametrize("interruption", ["watchdog", "cancel"])
def test_r2_loopback_interrupt_race(monkeypatch, provider, interruption):
    import errno
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import time

    # Each of the four cases owns one server and performs 20 interrupted reads.
    # Four cases at <15 seconds each enforce the required <=60 second group.
    release = Event()
    fragment = _claude_sse().split(b"event: content_block_stop")[0] if provider == "anthropic" else _sse("partial", None).split(b"data: [DONE]")[0]
    monkeypatch.setattr(socket, "getfqdn", lambda *args: "localhost")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(f"{len(fragment):x}\r\n".encode() + fragment + b"\r\n")
            self.wfile.flush()
            release.wait(15)

    started_group = time.monotonic()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except OSError as exc:
        if exc.errno in {errno.EPERM, errno.EACCES}:
            pytest.skip("R2-1 loopback bind is denied by sandbox permissions; 20-iteration race test requires host rerun")
        raise
    server.daemon_threads = True
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    monkeypatch.setitem(PROVIDERS[provider], "base_url", f"http://127.0.0.1:{server.server_port}/v1")
    # Leave enough time for the connection and first fragment before testing
    # the watchdog against the subsequent blocked read.
    monkeypatch.setattr(client, "total_seconds", lambda: 0.6 if interruption == "watchdog" else 10.0)
    read_limit = 1.2 if interruption == "watchdog" else 1.0
    constructor_module = client.anthropic if provider == "anthropic" else client.openai
    constructor_name = "Anthropic" if provider == "anthropic" else "OpenAI"
    real_constructor = getattr(constructor_module, constructor_name)

    def construct(**kwargs):
        kwargs["timeout"] = 3.0
        return real_constructor(**kwargs)

    monkeypatch.setattr(constructor_module, constructor_name, construct)
    try:
        for iteration in range(20):
            control = client.ReplyStreamControl()
            reply = client.open_reply_stream(_config(provider, "claude-haiku-5-5" if provider == "anthropic" else "unit"), [{"role": "user", "content": "test"}], mirror=False, username="alice", control=control)
            assert next(reply).choices[0].delta.content == ("好" if provider == "anthropic" else "partial")
            if interruption == "watchdog":
                assert not reply.resources.timed_out, "first fragment must arrive before the watchdog"
            result = []
            reading = Event()

            def consume():
                reading.set()
                try:
                    list(reply)
                except Exception as exc:
                    result.append(exc)
                finally:
                    reply.close()

            started = time.monotonic()
            worker = Thread(target=consume, daemon=True)
            worker.start()
            assert reading.wait(0.2)
            if interruption == "cancel":
                time.sleep(0.005)
                control.abort()
            worker.join(timeout=read_limit)
            assert not worker.is_alive(), f"{provider}/{interruption} iteration {iteration} waited for SDK read timeout"
            assert time.monotonic() - started < read_limit
            if interruption == "watchdog":
                assert len(result) == 1 and isinstance(result[0], ByokTimeoutError)
            assert reply.resources.closed
            assert reply.resources.client.is_closed()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1)
    assert time.monotonic() - started_group < 15.0


@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
@pytest.mark.parametrize("interruption", ["cancel", "watchdog"])
def test_r3_interrupt_before_sdk_send_makes_no_request(monkeypatch, provider, interruption):
    """An interruption at timer start must not reach either SDK send method."""
    constructed, sent = [], []
    control = client.ReplyStreamControl()

    class SDK:
        def __init__(self, **kwargs):
            self.closed = False
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.send))
            self.messages = SimpleNamespace(stream=self.send)
            constructed.append(self)

        def send(self, **kwargs):
            sent.append(kwargs)
            raise AssertionError("SDK send must not run after interruption")

        def close(self):
            self.closed = True

    monkeypatch.setattr(client.openai, "OpenAI", SDK)
    monkeypatch.setattr(client.anthropic, "Anthropic", SDK)
    original_start = client._Resources.start

    def start(resources):
        original_start(resources)
        if interruption == "cancel":
            control.abort()
        else:
            resources.expire()

    monkeypatch.setattr(client._Resources, "start", start)
    expected = client.ReplyInterruptedError if interruption == "cancel" else ByokTimeoutError
    model = "claude-haiku-5-5" if provider == "anthropic" else "unit"
    with pytest.raises(expected):
        client.open_reply_stream(_config(provider, model), _messages(), mirror=False, username="alice", control=control)
    assert sent == []
    assert len(constructed) == 1 and constructed[0].closed
