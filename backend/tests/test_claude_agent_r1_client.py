"""R1 client regressions use the real Anthropic SDK and no network."""
from copy import deepcopy
import socket

import pytest

from byok import client
from test_claude_agent_client import MODELS, TOOLS, config, install_sdk, messages, sse


@pytest.fixture(scope="module", autouse=True)
def offline_module():
    patch = pytest.MonkeyPatch()

    def blocked(*args, **kwargs):
        raise AssertionError("Claude agent R1 tests forbid connections and DNS")

    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        patch.setattr(socket, name, blocked)
    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, blocked)
    yield
    patch.undo()


@pytest.mark.parametrize("model", MODELS)
def test_agent_never_sends_eager_input_streaming_even_with_stale_tool_schema(monkeypatch, model):
    monkeypatch.setattr(client, "ensure_available", lambda: None)
    calls, requests, clients = install_sdk(monkeypatch)
    schemas = deepcopy(TOOLS)
    schemas[0]["eager_input_streaming"] = True
    original = deepcopy(schemas)
    stream = client.open_agent_stream(config(model), messages(), username="alice", tools=schemas, deadline_seconds=90)
    list(stream)
    assert calls[0]["tools"][0] == TOOLS[0]
    assert all("eager_input_streaming" not in tool for tool in requests[0][0]["tools"])
    assert schemas == original
    assert all(sdk.is_closed() for sdk in clients)


def test_real_sdk_replay_wire_body_preserves_explicit_nullable_citations(monkeypatch):
    from services.claude_agent import _assistant_content

    monkeypatch.setattr(client, "ensure_available", lambda: None)
    response = sse([
        {"type": "server_tool_use", "id": "search", "name": "web_search", "input": {"query": "offline"}},
        {"type": "web_search_tool_result", "tool_use_id": "search", "content": [{
            "type": "web_search_result", "title": "来源", "url": "https://example.com/", "encrypted_content": "opaque", "page_age": None,
        }]},
        {"type": "text", "text": "引用", "citations": [
            {"type": "web_search_result_location", "cited_text": "事实", "encrypted_index": "index", "url": "https://example.com/", "title": None},
            {"type": "char_location", "cited_text": "文档", "document_index": 0, "document_title": None, "start_char_index": 0, "end_char_index": 2},
        ]},
        {"type": "tool_use", "id": "weather", "name": "get_weather", "input": {"city": "北京"}},
    ], "tool_use")
    _, requests, clients = install_sdk(monkeypatch, response)
    history = messages()
    first = client.open_agent_stream(config(), history, username="alice", tools=TOOLS, deadline_seconds=90)
    list(first)
    history.extend([
        {"role": "assistant", "content": _assistant_content(first.final_message)},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "weather", "content": "北京晴"}]},
    ])
    list(client.open_agent_stream(config(), history, username="alice", tools=TOOLS, deadline_seconds=90))
    replay = requests[1][0]["messages"][-2]["content"]
    assert "page_age" in replay[1]["content"][0] and replay[1]["content"][0]["page_age"] is None
    assert "title" in replay[2]["citations"][0] and replay[2]["citations"][0]["title"] is None
    assert "document_title" in replay[2]["citations"][1] and replay[2]["citations"][1]["document_title"] is None
    assert all(sdk.is_closed() for sdk in clients)
