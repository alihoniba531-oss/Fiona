# -*- coding: utf-8 -*-
import asyncio

from utils.request_limits import RequestBodyLimitMiddleware


def _scope(headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }


def test_rejects_oversized_content_length_before_calling_app():
    called = False
    sent = []

    async def app(scope, receive, send):
        nonlocal called
        called = True

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(app, max_bytes=4)
    asyncio.run(
        middleware(
            _scope([(b"content-length", b"5")]),
            receive,
            send,
        )
    )

    assert called is False
    assert sent[0]["status"] == 413


def test_counts_chunked_body_when_content_length_is_missing():
    chunks = [
        {"type": "http.request", "body": b"123", "more_body": True},
        {"type": "http.request", "body": b"45", "more_body": False},
    ]
    sent = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(app, max_bytes=4)
    asyncio.run(middleware(_scope(), receive, send))

    assert sent[0]["status"] == 413
