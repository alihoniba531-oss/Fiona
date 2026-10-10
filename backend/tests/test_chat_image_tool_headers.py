"""Chat SSE headers remain streaming through the Next proxy, entirely offline."""

import asyncio
import json
import socket
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("R2 header tests forbid real network connections")
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("R2 header tests forbid real network connections")
        return original_connect_ex(sock, address)

    def guarded_dns(*args, **kwargs):
        raise AssertionError("R2 header tests forbid real DNS requests")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_dns)


def _events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _assert_stream_headers(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.parametrize("reserved", [False, True])
def test_chat_reply_stream_headers_prevent_proxy_compression(
    client, dev_headers, monkeypatch, reserved,
):
    import database
    import routers.chat as router
    from auth import create_token
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(router, "assess_crisis", lambda message: None)

    async def classify(message):
        return None

    requests = []

    async def build_context(req, user, **kwargs):
        requests.append((req.message, user))
        return SimpleNamespace(user=user)

    reply_calls = []

    async def reply(ctx, **kwargs):
        reply_calls.append(kwargs)
        if kwargs.get("tracker") is not None:
            kwargs["tracker"].started = True
        yield 'data: {"text": "普通回复"}\n\n'
        yield 'data: {"done": true}\n\n'

    monkeypatch.setattr(router.crisis_model, "classify", classify)
    monkeypatch.setattr(router, "build_context", build_context)
    monkeypatch.setattr(router, "run_chat", reply)
    headers = dev_headers
    user = dev_headers["X-Dev-User"]
    if reserved:
        assert client.get("/profile", headers=dev_headers).status_code == 200
        version = asyncio.run(database.get_session_version(user))
        headers = {"Authorization": "Bearer " + create_token(user, version)}
        monkeypatch.setenv("DEV_MODE", "0")

        async def reserve(*args):
            return 10

        monkeypatch.setattr(router, "reserve_strawberries", reserve)

    response = client.post("/chat", headers=headers, json={"message": "普通测试消息"})
    assert requests == [("普通测试消息", user)]
    assert len(reply_calls) == 1
    assert reply_calls[0].get("reserved", False) is reserved
    assert _events(response) == [{"text": "普通回复"}, {"done": True}]
    _assert_stream_headers(response)


def test_chat_text_stream_error_headers_prevent_proxy_compression(
    client, dev_headers, monkeypatch,
):
    import routers.chat as router
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(router, "assess_crisis", lambda message: "possible")

    async def classify(message):
        return None

    def unexpected_reply(*args, **kwargs):
        raise AssertionError("Invalid crisis request must use _text_stream before reply")

    monkeypatch.setattr(router.crisis_model, "classify", classify)
    monkeypatch.setattr(router, "run_chat", unexpected_reply)
    response = client.post("/chat", headers=dev_headers, json={"message": ""})
    assert _events(response) == [
        {"text": router.CRISIS_RESOURCE_NOTE},
        {"error": "message 和图片不能同时为空"},
    ]
    _assert_stream_headers(response)
