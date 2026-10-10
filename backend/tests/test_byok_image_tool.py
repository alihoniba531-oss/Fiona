"""Offline SDK contracts for the BYOK image tool and unchanged text streams."""
import json
import logging
import socket
import subprocess
from types import ModuleType, SimpleNamespace as NS

import httpx
import httpx2
import pytest

from byok import client as byok_client
from persona import BASE_SAFETY_RULES


@pytest.fixture(autouse=True)
def offline_image_tool(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setattr(byok_client, "ensure_available", lambda: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("real network request")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)

    class Timer:
        def __init__(self, seconds, callback):
            self.daemon = False

        def start(self):
            pass

        def cancel(self):
            pass

    monkeypatch.setattr(byok_client, "Timer", Timer)


def git_baseline(path, **kwargs):
    """Read a file at the task baseline; CI's shallow checkout lacks that commit."""
    try:
        return subprocess.check_output(
            ["git", "show", f"7ac7b57:{path}"], text=True, stderr=subprocess.DEVNULL, **kwargs,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("基线提交 7ac7b57 不在本地 git 历史中（如 CI 浅克隆），跳过基线比对")


@pytest.fixture
def baseline_client(monkeypatch):
    source = git_baseline("backend/byok/client.py")
    baseline = ModuleType("byok._image_tool_baseline")
    baseline.__package__ = "byok"
    exec(compile(source, "7ac7b57:backend/byok/client.py", "exec"), baseline.__dict__)
    monkeypatch.setattr(baseline, "ensure_available", lambda: None)
    monkeypatch.setattr(baseline, "Timer", byok_client.Timer)
    return baseline


def config(provider="anthropic", model="claude-opus-5-5", effort="low"):
    return {"provider": provider, "model": model, "api_key": "offline-key", "effort": effort}


MESSAGES = [{"role": "system", "content": "安全要求"}, {"role": "user", "content": "画一只猫"}]


def delta(*, text=None, calls=None, finish=None):
    value = NS(content=text)
    if calls is not None:
        value.tool_calls = calls
    return NS(choices=[NS(delta=value, finish_reason=finish)])


def call_part(index=0, *, identity=None, name=None, arguments=None):
    return NS(index=index, id=identity, function=NS(name=name, arguments=arguments))


def tool_block(prompt="一只猫", **arguments):
    return NS(type="tool_use", name="generate_image", input={"prompt": prompt, **arguments})


def install_sdk(monkeypatch, *, provider="anthropic", chunks=(), text=(), final=None, error=None):
    """Replace SDK constructors and stream managers before any request can occur."""
    captured = []
    closed = []

    class Stream:
        def __iter__(self):
            yield from chunks

        @property
        def text_stream(self):
            yield from text

        def get_final_message(self):
            if error is not None:
                raise error
            return final or NS(stop_reason="end_turn", content=[])

        def close(self):
            closed.append("stream")

    stream = Stream()

    class Manager:
        def __enter__(self):
            return stream

        def __exit__(self, *args):
            closed.append("manager")

    def request(**kwargs):
        captured.append(kwargs)
        return Manager() if provider == "anthropic" else stream

    def constructor(**kwargs):
        endpoint = NS(stream=request)
        return NS(messages=endpoint, beta=NS(messages=endpoint),
                  chat=NS(completions=NS(create=request)), close=lambda: closed.append("client"))

    if provider == "anthropic":
        monkeypatch.setattr(byok_client.anthropic, "Anthropic", constructor)
    else:
        monkeypatch.setattr(byok_client.openai, "OpenAI", constructor)
    return captured, closed


def open_and_consume(settings, **kwargs):
    stream = byok_client.open_reply_stream(settings, MESSAGES, mirror=False, username="", **kwargs)
    chunks = list(stream)
    return stream, "".join(chunk.choices[0].delta.content or "" for chunk in chunks), chunks


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"])
@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_claude_tool_request_preserves_effort_and_beta_fallback(monkeypatch, model, effort):
    captured, closed = install_sdk(monkeypatch, final=NS(stop_reason="tool_use", content=[tool_block()]))
    stream, text, chunks = open_and_consume(config(model=model, effort=effort), tools="generate_image")
    body = captured[0]
    assert body["tools"][0]["name"] == "generate_image"
    assert "input_schema" in body["tools"][0]
    assert "strict" not in body["tools"][0]
    assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert body["output_config"] == {"effort": effort}
    assert body["max_tokens"] == {"low": 4096, "medium": 8192, "high": 16384}[effort]
    assert (body.get("fallbacks") == "default") == (model != "claude-haiku-5-5")
    assert ("betas" in body) == (model != "claude-haiku-5-5")
    assert "eager_input_streaming" not in body
    assert stream.tool_call == {"name": "generate_image", "arguments": {"prompt": "一只猫"}}
    assert stream.tool_call_invalid is False
    assert text == "" and chunks == []
    assert "stream" in closed and "client" in closed and "manager" in closed


@pytest.mark.parametrize("provider,model,extra", [
    ("dashscope", "qwen3.8-omni-flash", {"enable_thinking": False}),
    ("deepseek", "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
])
def test_openai_tool_arguments_are_joined_without_repeating_id(monkeypatch, provider, model, extra):
    captured, closed = install_sdk(monkeypatch, provider=provider, chunks=[
        delta(text="我来画。", calls=[call_part(identity="same-id", name="generate_image", arguments='{"pro')]),
        delta(calls=[call_part(identity="same-id", name="generate_image", arguments='mpt":"一只猫"')]),
        delta(calls=[call_part(identity="same-id", arguments='}')], finish="tool_calls"),
    ])
    stream, text, chunks = open_and_consume(config(provider, model), tools="generate_image")
    body = captured[0]
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "generate_image"
    assert "strict" not in body["tools"][0]["function"]
    assert body["tool_choice"] == "auto" and "parallel_tool_calls" not in body
    assert body["extra_body"] == extra
    assert stream.tool_call == {"name": "generate_image", "arguments": {"prompt": "一只猫"}}
    assert stream.tool_call_invalid is False and text == "我来画。"
    assert all(not hasattr(chunk.choices[0].delta, "tool_calls") for chunk in chunks)
    assert "stream" in closed and "client" in closed


def test_openai_first_generate_image_call_only(monkeypatch):
    install_sdk(monkeypatch, provider="dashscope", chunks=[delta(calls=[
        call_part(0, identity="other", name="other", arguments='{}'),
        call_part(1, identity="first", name="generate_image", arguments='{"prompt":"第一只猫"}'),
        call_part(2, identity="second", name="generate_image", arguments='{"prompt":"第二只猫"}'),
    ], finish="tool_calls")])
    stream, _, _ = open_and_consume(config("dashscope", "qwen3.8-flash"), tools="generate_image")
    assert stream.tool_call["arguments"]["prompt"] == "第一只猫"


@pytest.mark.parametrize("finish", ["length", "max_tokens", "content_filter"])
def test_openai_truncated_or_filtered_tool_call_is_invalid(monkeypatch, finish):
    install_sdk(monkeypatch, provider="dashscope", chunks=[delta(calls=[
        call_part(identity="id", name="generate_image", arguments='{"prompt":"一只猫"}')
    ], finish=finish)])
    stream, _, _ = open_and_consume(config("dashscope", "qwen3.8-flash"), tools="generate_image")
    assert stream.tool_call is None and stream.tool_call_invalid is True


@pytest.mark.parametrize("arguments", ['{"prompt":', '["一只猫"]', 'null'])
def test_openai_invalid_json_or_nonobject_arguments_are_invalid(monkeypatch, arguments):
    install_sdk(monkeypatch, provider="dashscope", chunks=[delta(calls=[
        call_part(identity="id", name="generate_image", arguments=arguments)
    ], finish="tool_calls")])
    stream, _, _ = open_and_consume(config("dashscope", "qwen3.8-flash"), tools="generate_image")
    assert stream.tool_call is None and stream.tool_call_invalid is True


def test_openai_non_tool_finish_does_not_execute_complete_arguments(monkeypatch):
    install_sdk(monkeypatch, provider="dashscope", chunks=[delta(calls=[
        call_part(identity="id", name="generate_image", arguments='{"prompt":"一只猫"}')
    ], finish="stop")])
    stream, _, _ = open_and_consume(config("dashscope", "qwen3.8-flash"), tools="generate_image")
    assert stream.tool_call is None


@pytest.mark.parametrize("stop", ["refusal", "max_tokens", "length", "content_filter"])
def test_claude_refusal_or_truncated_tool_is_invalid(monkeypatch, stop):
    install_sdk(monkeypatch, final=NS(stop_reason=stop, content=[tool_block()]), text=["我来画。"])
    stream, text, _ = open_and_consume(config(), tools="generate_image")
    assert stream.tool_call is None and stream.tool_call_invalid is True
    assert text == "我来画。"


def test_claude_only_tool_after_last_fallback_is_used(monkeypatch):
    install_sdk(monkeypatch, final=NS(stop_reason="tool_use", content=[
        tool_block("第一次"), NS(type="fallback"), tool_block("第二次"),
        NS(type="fallback"), NS(type="thinking", thinking="内部思考"),
        tool_block("第三次"), tool_block("第四次"),
    ]))
    stream, _, _ = open_and_consume(config(), tools="generate_image")
    assert stream.tool_call == {"name": "generate_image", "arguments": {"prompt": "第三次"}}


def test_claude_discarded_fallback_tool_is_not_executed(monkeypatch):
    install_sdk(monkeypatch, final=NS(stop_reason="end_turn", content=[tool_block(), NS(type="fallback")]))
    stream, _, _ = open_and_consume(config(), tools="generate_image")
    assert stream.tool_call is None and stream.tool_call_invalid is False


def test_claude_sdk_tool_parameter_json_value_error_is_invalid_without_leak(monkeypatch, caplog):
    private_json = '{"prompt":"SDK_PRIVATE_TOOL_PROMPT_R2"}'
    install_sdk(monkeypatch, text=["我来画。"], error=ValueError(
        "Unable to parse tool parameter JSON: " + private_json,
    ))
    with caplog.at_level(logging.DEBUG):
        stream, text, _ = open_and_consume(config(), tools="generate_image")
    assert stream.tool_call is None and stream.tool_call_invalid is True and text == "我来画。"
    assert private_json not in caplog.text
    assert "SDK_PRIVATE_TOOL_PROMPT_R2" not in caplog.text


def test_claude_sdk_value_error_without_tool_preserves_existing_error(monkeypatch):
    install_sdk(monkeypatch, error=ValueError("existing failure"))
    with pytest.raises(ValueError, match="existing failure"):
        open_and_consume(config())


@pytest.mark.parametrize("error", [
    ValueError("unrelated SDK value failure"),
    json.JSONDecodeError("Unable to parse tool parameter JSON", "malformed SSE", 0),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid SSE encoding"),
])
def test_claude_tool_mode_preserves_unrelated_value_error_identity(monkeypatch, error):
    install_sdk(monkeypatch, text=["普通聊天的前半句"], error=error)
    stream = byok_client.open_reply_stream(config(), MESSAGES, mirror=False, username="", tools="generate_image")
    with pytest.raises(type(error)) as raised:
        list(stream)
    assert raised.value is error
    assert stream.tool_call is None and stream.tool_call_invalid is False


@pytest.mark.parametrize("malformed,exception_type", [
    (b"event: content_block_delta\ndata: {invalid SSE JSON}\n\n", json.JSONDecodeError),
    (b"event: content_block_delta\ndata: \xff\n\n", UnicodeDecodeError),
])
def test_actual_claude_sdk_bad_sse_without_tool_use_raises_in_tool_mode(monkeypatch, malformed, exception_type):
    model = "claude-haiku-5-5"
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_offline", "type": "message", "role": "assistant", "model": model,
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "今天聊点别的，"}}),
    ]
    response_bytes = "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode() + malformed
    captured, clients = [], []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=response_bytes)

    constructor = byok_client.anthropic.Anthropic

    def offline_constructor(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
        sdk = constructor(**kwargs)
        clients.append(sdk)
        return sdk

    monkeypatch.setattr(byok_client.anthropic, "Anthropic", offline_constructor)
    stream = byok_client.open_reply_stream(config(model=model), MESSAGES, mirror=False, username="", tools="generate_image")
    text = []
    with pytest.raises(exception_type):
        for chunk in stream:
            text.append(chunk.choices[0].delta.content or "")
    assert "".join(text) == "今天聊点别的，"
    assert stream.tool_call is None and stream.tool_call_invalid is False
    assert len(captured) == 1 and captured[0]["tools"][0]["name"] == "generate_image"
    assert clients[0].is_closed()


@pytest.mark.parametrize("provider,model", [("anthropic", "claude-opus-5-5"), ("dashscope", "qwen3.8-flash")])
def test_default_and_none_tool_match_baseline_request_and_ignore_fake_calls(monkeypatch, baseline_client, provider, model):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "0")
    captured, _ = install_sdk(monkeypatch, provider=provider, text=["好"],
        final=NS(stop_reason="tool_use", content=[tool_block()]),
        chunks=[delta(text="好", calls=[call_part(identity="id", name="generate_image", arguments='{"prompt":"猫"}')], finish="tool_calls")])
    default, text, _ = open_and_consume(config(provider, model))
    explicit, _, _ = open_and_consume(config(provider, model), tools=None)
    baseline = baseline_client.open_reply_stream(config(provider, model), MESSAGES, mirror=False, username="")
    assert "".join(chunk.choices[0].delta.content or "" for chunk in baseline) == "好"
    bodies = [json.dumps(body, ensure_ascii=False).encode() for body in captured]
    assert len(bodies) == 3 and bodies[0] == bodies[1] == bodies[2]
    assert "tools" not in captured[0] and "tool_choice" not in captured[0]
    assert default.tool_call is None and explicit.tool_call is None and text == "好"
    assert not default.tool_call_invalid and not explicit.tool_call_invalid


def test_reply_tool_result_properties_are_read_only(monkeypatch):
    install_sdk(monkeypatch, final=NS(stop_reason="tool_use", content=[tool_block()]))
    stream, _, _ = open_and_consume(config(), tools="generate_image")
    with pytest.raises(AttributeError):
        stream.tool_call = None
    with pytest.raises(AttributeError):
        stream.tool_call_invalid = False


@pytest.mark.parametrize("provider,model", [("dashscope", "qwen3.8-flash"), ("deepseek", "deepseek-v4-pro")])
def test_default_openai_serialized_request_bytes_match_git_baseline(monkeypatch, baseline_client, provider, model):
    constructor = byok_client.openai.OpenAI
    captured = []

    def handler(request):
        captured.append(request.content)
        payload = {"id": "offline", "object": "chat.completion.chunk", "created": 0, "model": model,
                   "choices": [{"index": 0, "delta": {"content": "好"}, "finish_reason": "stop"}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode())

    def offline_constructor(**kwargs):
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        return constructor(**kwargs)

    monkeypatch.setattr(byok_client.openai, "OpenAI", offline_constructor)
    open_and_consume(config(provider, model))
    open_and_consume(config(provider, model), tools=None)
    baseline = baseline_client.open_reply_stream(config(provider, model), MESSAGES, mirror=False, username="")
    assert "".join(chunk.choices[0].delta.content or "" for chunk in baseline) == "好"
    assert len(captured) == 3 and captured[0] == captured[1] == captured[2]
    assert b'"tools"' not in captured[0] and b'"tool_choice"' not in captured[0]


@pytest.mark.parametrize("provider,model", [("anthropic", "claude-opus-5-5"), ("dashscope", "qwen3.8-flash")])
def test_plain_text_truncation_with_tools_preserves_text_stop_semantics(monkeypatch, provider, model):
    install_sdk(monkeypatch, provider=provider, text=["好"], final=NS(stop_reason="max_tokens", content=[]),
                chunks=[delta(text="好", finish="length")])
    stream, text, chunks = open_and_consume(config(provider, model), tools="generate_image")
    assert text == "好" and stream.tool_call is None and stream.tool_call_invalid is False
    assert chunks[-1].choices[0].finish_reason == "length"


@pytest.mark.parametrize("interruption", ["timeout", "abort"])
@pytest.mark.parametrize("parse_error", [False, True])
def test_claude_interruption_during_final_message_never_exposes_tool(monkeypatch, interruption, parse_error):
    _, closed = install_sdk(monkeypatch, final=NS(stop_reason="tool_use", content=[tool_block()]))
    stream = byok_client.open_reply_stream(config(), MESSAGES, mirror=False, username="", tools="generate_image")

    def interrupted_final():
        if interruption == "timeout":
            stream.resources.expire()
        else:
            stream.abort()
        if parse_error:
            raise ValueError("SDK tool JSON parsing stopped")
        return NS(stop_reason="tool_use", content=[tool_block()])

    stream.resources.stream.get_final_message = interrupted_final
    expected = byok_client.ByokTimeoutError if interruption == "timeout" else byok_client.ReplyInterruptedError
    with pytest.raises(expected):
        list(stream)
    assert stream.tool_call is None and stream.tool_call_invalid is False
    assert closed.count("stream") == closed.count("client") == closed.count("manager") == 1


@pytest.mark.parametrize("provider,model", [
    ("anthropic", "claude-opus-5-5"),
    ("dashscope", "qwen3.8-flash"),
    ("deepseek", "deepseek-v4-pro"),
])
def test_actual_tool_request_keeps_safety_once_after_read_aloud_system(monkeypatch, provider, model):
    messages = [
        {"role": "system", "content": "人设规则，账号 alice"},
        {"role": "user", "content": "画一只猫"},
        {"role": "system", "content": "这轮回复需要适合朗读。\n" + BASE_SAFETY_RULES},
    ]
    captured, clients = [], []

    if provider == "anthropic":
        constructor = byok_client.anthropic.Anthropic
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_offline", "type": "message", "role": "assistant", "model": model,
                "content": [], "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 0}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": "好"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                               "usage": {"output_tokens": 1}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        response_bytes = "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode()
        http_module = httpx2
    else:
        constructor = byok_client.openai.OpenAI
        payload = {"id": "offline", "object": "chat.completion.chunk", "created": 0, "model": model,
                   "choices": [{"index": 0, "delta": {"content": "好"}, "finish_reason": "stop"}]}
        response_bytes = ("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode()
        http_module = httpx

    def handler(request):
        captured.append(json.loads(request.content))
        return http_module.Response(200, headers={"content-type": "text/event-stream"}, content=response_bytes)

    def offline_constructor(**kwargs):
        kwargs["http_client"] = http_module.Client(transport=http_module.MockTransport(handler), trust_env=False)
        sdk = constructor(**kwargs)
        clients.append(sdk)
        return sdk

    target = byok_client.anthropic if provider == "anthropic" else byok_client.openai
    monkeypatch.setattr(target, "Anthropic" if provider == "anthropic" else "OpenAI", offline_constructor)
    stream = byok_client.open_reply_stream(config(provider, model), messages, mirror=False, username="alice", tools="generate_image")
    assert "".join(chunk.choices[0].delta.content or "" for chunk in stream) == "好"
    body = captured[0]
    if provider == "anthropic":
        systems = [body["system"]]
        assert not any(message["role"] == "system" for message in body["messages"])
        assert body["tools"][0]["name"] == "generate_image"
        assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    else:
        systems = [message["content"] for message in body["messages"] if message["role"] == "system"]
        assert body["tools"][0]["function"]["name"] == "generate_image"
        assert body["tool_choice"] == "auto"
        assert len(systems) == (2 if provider == "dashscope" else 1)
        if provider == "dashscope":
            assert body["enable_thinking"] is False
        else:
            assert body["thinking"] == {"type": "disabled"}
    assert sum(system.count(BASE_SAFETY_RULES) for system in systems) == 1
    assert systems[-1].endswith(BASE_SAFETY_RULES)
    assert "alice" not in "\n".join(systems)
    assert messages[0]["content"] == "人设规则，账号 alice"
    assert clients[0].is_closed()
