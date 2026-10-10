"""Claude agent request contracts exercised with the installed SDK, offline."""
from copy import deepcopy
import json
import socket

import httpx2
import pytest

from byok import client
from persona import BASE_SAFETY_RULES


TOOL_INSTRUCTIONS = "【工具使用】你可以调用工具帮主人做事：get_weather 查天气（城市必须是主人亲口说过的，没说就先问）；plan_travel 做旅行规划；plan_route 查两地路线；get_hot_topics 看热榜；generate_image 生成图片（每轮最多一张，描述不得含账号名、真实姓名或私人细节）；web_search 和 web_fetch 联网搜索、阅读网页（需要最新信息或主人给了链接时使用）。只有实际收到工具结果后才能说已经查到或已经画好，不得编造工具结果；工具失败就如实告诉主人。可以连续使用多个工具，再综合作答。当前消息开头的「当前北京时间」可直接使用。"
TOOLS = [{"name": "get_weather", "description": "查天气", "input_schema": {
    "type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"],
}}]
MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]


@pytest.fixture(scope="module", autouse=True)
def offline_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Claude agent tests cannot connect or resolve DNS")

    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        patch.setattr(socket, name, forbidden)
    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(client, "ensure_available", lambda: None)

    class Timer:
        def __init__(self, seconds, callback):
            self.seconds = seconds
            self.daemon = False

        def start(self):
            pass

        def cancel(self):
            pass

    monkeypatch.setattr(client, "Timer", Timer)
    monkeypatch.setenv("FIONA_BYOK_TOTAL_SECONDS", "120")


def config(model="claude-opus-5-5", effort="low"):
    return {"provider": "anthropic", "model": model, "effort": effort, "api_key": "offline-key"}


def messages():
    return [
        {"role": "system", "content": "账号 alice\n\n" + BASE_SAFETY_RULES.strip()},
        {"role": "assistant", "content": "丢弃开头"},
        {"role": "user", "content": "历史一"},
        {"role": "user", "content": "历史二［图中：小猫］"},
        {"role": "assistant", "content": "历史回答"},
        {"role": "user", "content": [
            {"type": "text", "text": "（当前北京时间：2026年10月10日 周六 14:00）"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "b2ZmbGluZQ=="}},
            {"type": "text", "text": "北京的天气呢"},
        ]},
    ]


def sse(blocks=None, stop="end_turn", *, server_usage=None):
    blocks = [{"type": "text", "text": "好"}] if blocks is None else blocks
    usage = {"input_tokens": 12, "output_tokens": 0, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 4}
    if server_usage is not None:
        usage["server_tool_use"] = server_usage
    events = [("message_start", {"type": "message_start", "message": {
        "id": "msg_offline", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [], "stop_reason": None, "stop_sequence": None, "usage": usage,
    }})]
    for index, original in enumerate(blocks):
        block = deepcopy(original)
        delta = None
        if block["type"] == "text":
            delta = {"type": "text_delta", "text": block["text"]}
            block["text"] = ""
        elif block["type"] in {"tool_use", "server_tool_use"}:
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"], ensure_ascii=False)}
            block["input"] = {}
        events.append(("content_block_start", {"type": "content_block_start", "index": index, "content_block": block}))
        if delta is not None:
            events.append(("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}))
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    events.extend([
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 7}}),
        ("message_stop", {"type": "message_stop"}),
    ])
    return "".join(f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n" for name, payload in events).encode()


def install_sdk(monkeypatch, response=None):
    original = client.anthropic.Anthropic
    calls, requests, clients = [], [], []

    def handler(request):
        requests.append((json.loads(request.content), dict(request.headers)))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=response or sse())

    def constructor(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
        sdk = original(**kwargs)
        clients.append(sdk)
        for endpoint in (sdk.messages, sdk.beta.messages):
            original_stream = endpoint.stream

            def stream(*, _original=original_stream, **params):
                calls.append(deepcopy(params))
                return _original(**params)

            monkeypatch.setattr(endpoint, "stream", stream)
        return sdk

    monkeypatch.setattr(client.anthropic, "Anthropic", constructor)
    return calls, requests, clients


def consume_agent(monkeypatch, *, settings=None, history=None, response=None, deadline=90):
    calls, requests, clients = install_sdk(monkeypatch, response)
    stream = client.open_agent_stream(settings or config(), history or messages(), username="alice", tools=TOOLS, deadline_seconds=deadline)
    chunks = list(stream)
    return stream, calls, requests, clients, chunks


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_agent_request_has_stable_prefix_cache_tools_and_existing_effort(monkeypatch, model, effort):
    history, schemas = messages(), deepcopy(TOOLS)
    stream, calls, requests, clients, chunks = consume_agent(monkeypatch, settings=config(model, effort), history=history)
    body = calls[0]
    system = body["system"][0]
    assert system["type"] == "text" and system["cache_control"] == {"type": "ephemeral"}
    assert system["text"].count(BASE_SAFETY_RULES.strip()) == 1
    assert system["text"].endswith(BASE_SAFETY_RULES.strip())
    assert system["text"].index(TOOL_INSTRUCTIONS) < system["text"].index(BASE_SAFETY_RULES.strip())
    assert system["text"].count(TOOL_INSTRUCTIONS) == 1
    assert "alice" not in system["text"]
    assert "（账号已隐藏）" in system["text"]
    assert body["messages"][0] == {"role": "user", "content": "历史一\n\n历史二［图中：小猫］"}
    current = body["messages"][-1]["content"]
    assert [block["type"] for block in current] == ["text", "image", "text"]
    assert current[0]["text"] == "（当前北京时间：2026年10月10日 周六 14:00）"
    assert current[1]["source"] == history[-1]["content"][1]["source"]
    assert current[-1] == {"type": "text", "text": "北京的天气呢", "cache_control": {"type": "ephemeral"}}
    assert "cache_control" not in history[-1]["content"][-1]
    assert TOOLS == schemas
    assert body["tools"][0] == TOOLS[0]
    assert all("eager_input_streaming" not in tool for tool in body["tools"])
    versions = ("20250305", "20250910")
    assert body["tools"][1:] == [
        {"type": "web_search_" + versions[0], "name": "web_search", "max_uses": 5},
        {"type": "web_fetch_" + versions[1], "name": "web_fetch", "max_uses": 3},
    ]
    assert client.CLAUDE_SERVER_TOOLS[model] == body["tools"][1:]
    assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert body["max_tokens"] == {"low": 4096, "medium": 8192, "high": 16384}[effort]
    assert body["output_config"] == {"effort": effort}
    assert not {"thinking", "temperature", "top_p", "top_k"} & body.keys()
    assert (body.get("fallbacks") == "default") == (model != "claude-haiku-5-5")
    assert (body.get("betas") == ["server-side-fallback-2026-07-01"]) == (model != "claude-haiku-5-5")
    assert requests[0][0]["tools"] == body["tools"]
    assert stream.final_message.stop_reason == "end_turn"
    assert all(sdk.is_closed() for sdk in clients)


def test_agent_tool_results_and_pause_assistant_blocks_are_preserved(monkeypatch):
    history = messages() + [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "tool_1", "name": "get_weather", "input": {"city": "北京"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tool_1", "content": "北京晴"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "我继续读网页"}]},
    ]
    _, calls, _, _, _ = consume_agent(monkeypatch, history=history)
    sent = calls[0]["messages"]
    assert sent[-2] == history[-2]
    assert sent[-3] == history[-3]
    assert sent[-1] == {"role": "assistant", "content": [{"type": "text", "text": "我继续读网页", "cache_control": {"type": "ephemeral"}}]}


def test_agent_deduplicates_safety_and_instructions_and_reorders_final_system(monkeypatch):
    history = messages()
    history.insert(1, {"role": "system", "content": "补充\n\n" + TOOL_INSTRUCTIONS + "\n\n" + BASE_SAFETY_RULES.strip()})
    history.append({"role": "system", "content": "最后规则"})
    _, calls, _, _, _ = consume_agent(monkeypatch, history=history)
    prompt = calls[0]["system"][0]["text"]
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1
    assert prompt.count(TOOL_INSTRUCTIONS) == 1
    assert prompt.endswith(BASE_SAFETY_RULES.strip())
    assert prompt.index("最后规则") < prompt.index(TOOL_INSTRUCTIONS)


@pytest.mark.parametrize("effort, deadline, expected", [("low", 90, 90), ("low", 200, 120), ("high", 200, 180), ("bogus", 200, 120)])
def test_agent_request_deadline_is_bounded_by_remaining_and_existing_limits(monkeypatch, effort, deadline, expected):
    stream, _, _, _, _ = consume_agent(monkeypatch, settings=config(effort=effort), deadline=deadline)
    assert stream.resources.timer.seconds == expected
    assert client.agent_request_seconds(config(effort=effort)) == (180 if effort == "high" else 120)


@pytest.mark.parametrize("model", MODELS)
def test_legacy_request_kwargs_remain_exact_without_agent_entrypoint(monkeypatch, model):
    calls, _, _ = install_sdk(monkeypatch)
    history = [{"role": "system", "content": "账号 alice"}, {"role": "user", "content": "文字"}]
    list(client.open_reply_stream(config(model), history, mirror=False, username="alice"))
    expected = {"model": model, "messages": [{"role": "user", "content": "文字"}], "max_tokens": 4096,
                "output_config": {"effort": "low"}, "system": "账号 （账号已隐藏）"}
    if model != "claude-haiku-5-5":
        expected.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    assert calls == [expected]


def test_legacy_convert_messages_keeps_old_string_only_behavior():
    system, prepared = client.convert_messages("anthropic", messages() + [{"role": "assistant", "content": "尾部"}], "alice")
    assert system == "账号 （账号已隐藏）\n\n" + BASE_SAFETY_RULES.strip()
    assert prepared == [{"role": "user", "content": "历史一\n\n历史二［图中：小猫］"}]


@pytest.mark.parametrize("stop", ["end_turn", "stop_sequence", "tool_use", "pause_turn", "refusal", "max_tokens"])
def test_real_sdk_agent_stop_reasons_and_final_message(monkeypatch, stop):
    blocks = [{"type": "text", "text": "先说一句"}]
    if stop == "tool_use":
        blocks.append({"type": "tool_use", "id": "tool_weather", "name": "get_weather", "input": {"city": "北京"}})
    stream, _, _, _, chunks = consume_agent(monkeypatch, response=sse(blocks, stop))
    assert stream.stop_reason == stop
    assert stream.refused is (stop == "refusal")
    assert stream.final_message.stop_reason == stop
    assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks) == "先说一句"
    assert any(chunk.choices[0].finish_reason == "length" for chunk in chunks) is (stop == "max_tokens")
    if stop == "tool_use":
        call = stream.final_message.content[-1]
        assert call.id == "tool_weather" and call.input == {"city": "北京"}


def test_real_sdk_preserves_search_and_fetch_results_and_server_usage(monkeypatch):
    blocks = [
        {"type": "server_tool_use", "id": "server_search", "name": "web_search", "input": {"query": "离线测试"}},
        {"type": "web_search_tool_result", "tool_use_id": "server_search", "content": [{
            "type": "web_search_result", "title": "来源", "url": "https://example.com/search", "encrypted_content": "opaque",
        }]},
        {"type": "server_tool_use", "id": "server_fetch", "name": "web_fetch", "input": {"url": "https://example.com/fetch"}},
        {"type": "web_fetch_tool_result", "tool_use_id": "server_fetch", "content": {
            "type": "web_fetch_result", "url": "https://example.com/fetch", "retrieved_at": "2026-10-10T00:00:00Z",
            "content": {"type": "document", "title": "网页标题", "source": {"type": "text", "media_type": "text/plain", "data": "网页内容"}},
        }},
        {"type": "text", "text": "找到了"},
    ]
    usage = {"web_search_requests": 2, "web_fetch_requests": 1}
    stream, _, _, _, _ = consume_agent(monkeypatch, response=sse(blocks, server_usage=usage))
    final = stream.final_message
    assert final.content[0].type == "server_tool_use"
    assert final.content[1].content[0].url == "https://example.com/search"
    assert final.content[3].type == "web_fetch_tool_result"
    assert final.content[3].content.type == "web_fetch_result"
    assert final.content[3].content.content.title == "网页标题"
    assert final.usage.server_tool_use.web_search_requests == 2
    assert final.usage.server_tool_use.web_fetch_requests == 1
    assert final.usage.cache_read_input_tokens == 3
    assert final.usage.cache_creation_input_tokens == 4


def test_real_sdk_beta_fallback_boundary_remains_in_final_message(monkeypatch):
    blocks = [
        {"type": "tool_use", "id": "ignored", "name": "get_weather", "input": {"city": "忽略"}},
        {"type": "fallback", "from": {"model": "claude-opus-5-5"}, "to": {"model": "claude-sonnet-5-5"}, "trigger": {"type": "refusal"}},
        {"type": "tool_use", "id": "selected", "name": "get_weather", "input": {"city": "北京"}},
    ]
    stream, _, _, _, _ = consume_agent(monkeypatch, response=sse(blocks, "tool_use"))
    assert [block.type for block in stream.final_message.content] == ["tool_use", "fallback", "tool_use"]
    assert stream.final_message.content[-1].id == "selected"


def test_agent_character_cap_retains_existing_truncation_and_closes_sdk(monkeypatch):
    stream, _, _, clients, chunks = consume_agent(monkeypatch, response=sse([{"type": "text", "text": "字" * 4100}]))
    assert stream.stop_reason == "max_tokens"
    assert stream.text_length == 4000
    assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks) == "字" * 4000
    assert chunks[-1].choices[0].finish_reason == "length"
    assert all(sdk.is_closed() for sdk in clients)
