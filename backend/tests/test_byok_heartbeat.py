"""Offline SSE heartbeats preserve delivery and BYOK cancellation ownership."""
import asyncio
import gc
import logging
import socket
import threading
import time
import urllib.request
from types import SimpleNamespace

import httpcore
import httpcore2
import httpx
import httpx2
import pytest
import requests


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    from utils import safe_http
    for target, name in (
        (urllib.request, "urlopen"), (requests, "get"), (safe_http, "_open_pinned"),
        (socket, "getaddrinfo"),
        (httpcore.SyncBackend, "connect_tcp"), (httpcore.SyncBackend, "connect_unix_socket"),
        (httpcore2.SyncBackend, "connect_tcp"), (httpcore2.SyncBackend, "connect_unix_socket"),
        (httpx.HTTPTransport, "handle_request"), (httpx.AsyncHTTPTransport, "handle_async_request"),
        (httpx2.HTTPTransport, "handle_request"), (httpx2.AsyncHTTPTransport, "handle_async_request"),
    ):
        monkeypatch.setattr(target, name, blocked)
    import services.chat_service as chat
    monkeypatch.setattr(chat, "_BYOK_HEARTBEAT_SECONDS", 0.05, raising=False)
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda *a, **k: None)
    monkeypatch.setenv("FIONA_BYOK_MAX_STREAMS", "8")
    assert chat._BYOK_ACTIVE == 0
    yield
    assert chat._BYOK_ACTIVE == 0 and not chat._BYOK_USERS
    chat.shutdown_byok_pool()
    assert not attempted, "network"


def _context(chat):
    return chat.ChatContext(
        "heartbeat_user", "你好", False, None, "你好", [], 0, "system",
        [{"role": "user", "content": "你好"}],
        byok_config={"provider": "anthropic", "model": "claude-opus-5-5",
                     "enabled": True, "api_key": "offline-key", "effort": "high"},
    )


class Reply:
    refused = False
    stop_reason = "end_turn"

    def __init__(self, before_first=None):
        self.before_first = before_first
        self.index = 0
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.index == 0 and self.before_first:
            self.before_first()
        if self.index == 2:
            raise StopIteration
        text = ("测试", "回复")[self.index]
        self.index += 1
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])

    def close(self):
        self.closed = True


def _save_stub(monkeypatch, chat):
    saved = []

    async def save(ctx, state):
        saved.append(state.full_response)
        state.response_saved = True

    monkeypatch.setattr(chat, "_save_response", save)
    return saved


@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("phase", ["opening", "reading"])
def test_delayed_byok_sends_heartbeats_without_changing_data(monkeypatch, mirror, phase):
    import services.chat_service as chat
    saved = _save_stub(monkeypatch, chat)

    async def collect(delay):
        reply = Reply((lambda: time.sleep(delay)) if phase == "reading" else None)

        def open_stream(*args, **kwargs):
            if phase == "opening":
                time.sleep(delay)
            return reply

        monkeypatch.setattr(chat, "open_reply_stream", open_stream)
        state = chat.ChatState(trace={}, sys_prompt_final="system")
        events = [event async for event in chat._stream_byok_reply(_context(chat), state, mirror=mirror)]
        assert reply.closed and state.response_saved and not state.billable
        return events, state

    async def scenario():
        fast, fast_state = await collect(0)
        slow, slow_state = await collect(0.2)
        assert sum(event == ": thinking\n\n" for event in slow) >= 2
        assert [event for event in slow if event.startswith("data: ")] == fast
        assert fast_state.full_response == slow_state.full_response == "测试回复"
        assert fast_state.trace == slow_state.trace

    asyncio.run(scenario())
    assert saved == ["测试回复", "测试回复"]


@pytest.mark.parametrize("mirror", [False, True])
def test_immediate_byok_sends_no_heartbeat(monkeypatch, mirror):
    import services.chat_service as chat
    _save_stub(monkeypatch, chat)
    reply = Reply()
    monkeypatch.setattr(chat, "open_reply_stream", lambda *args, **kwargs: reply)

    async def scenario():
        return [event async for event in chat._stream_byok_reply(
            _context(chat), chat.ChatState(trace={}), mirror=mirror)]

    events = asyncio.run(scenario())
    assert len(events) == 4 and all(event.startswith("data: ") for event in events)
    assert reply.closed


@pytest.mark.parametrize("phase", ["opening", "reading"])
@pytest.mark.parametrize("kind", ["cancel", "close"])
@pytest.mark.parametrize("worker_error", [False, True])
def test_cancel_during_heartbeat_joins_worker_without_leaks_or_errors(
    monkeypatch, caplog, phase, kind, worker_error,
):
    import services.chat_service as chat
    from byok.client import ReplyStreamControl
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    controls, replies = [], []
    saved = _save_stub(monkeypatch, chat)
    caplog.set_level(logging.ERROR, logger="asyncio")

    class Control(ReplyStreamControl):
        def __init__(self):
            super().__init__()
            self.abort_calls = 0
            controls.append(self)

        def abort(self):
            self.abort_calls += 1
            super().abort()
            release.set()

    def block():
        entered.set()
        try:
            assert release.wait(2), "cancel must interrupt the worker"
            if worker_error:
                raise httpx.ReadError("offline interrupted worker")
        finally:
            finished.set()

    def open_stream(*args, **kwargs):
        reply = Reply(block if phase == "reading" else None)
        replies.append(reply)
        if phase == "opening":
            try:
                block()
            except Exception:
                reply.close()
                raise
        return reply

    monkeypatch.setattr(chat, "ReplyStreamControl", Control)
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)

    async def scenario():
        prior_tasks = asyncio.all_tasks()
        stream = chat._stream_byok_reply(_context(chat), chat.ChatState(trace={}), mirror=False)
        owner = None
        try:
            if kind == "close":
                event = await asyncio.wait_for(stream.__anext__(), timeout=0.35)
                assert event == ": thinking\n\n"
                await asyncio.wait_for(stream.aclose(), timeout=0.35)
            else:
                heartbeat = asyncio.Event()

                async def consume():
                    async for event in stream:
                        if event == ": thinking\n\n":
                            heartbeat.set()

                owner = asyncio.create_task(consume())
                await asyncio.wait_for(heartbeat.wait(), timeout=0.35)
                owner.cancel()
                await asyncio.wait_for(asyncio.gather(owner, return_exceptions=True), timeout=0.35)
                assert owner.cancelled()
            assert entered.is_set() and finished.is_set()
            assert controls[0].aborted and controls[0].abort_calls == 1
            assert chat._BYOK_ACTIVE == 0 and not chat._BYOK_USERS
            gc.collect()
            await asyncio.sleep(0)
            assert not (asyncio.all_tasks() - prior_tasks), "pending BYOK tasks leaked"
        finally:
            release.set()
            if owner and not owner.done():
                owner.cancel()
                await asyncio.gather(owner, return_exceptions=True)
            await stream.aclose()

    asyncio.run(scenario())
    assert replies[0].closed and not saved
    assert not [record for record in caplog.records if record.name == "asyncio" and record.levelno >= logging.ERROR]


@pytest.mark.parametrize("worker_error", [False, True])
def test_close_after_open_finishes_while_paused_at_heartbeat(monkeypatch, caplog, worker_error):
    import services.chat_service as chat
    from byok.client import ReplyStreamControl
    release, finished = threading.Event(), threading.Event()
    controls = []
    reply = Reply()
    saved = _save_stub(monkeypatch, chat)
    caplog.set_level(logging.ERROR, logger="asyncio")

    class Control(ReplyStreamControl):
        def __init__(self):
            super().__init__()
            self.abort_calls = 0
            controls.append(self)

        def abort(self):
            self.abort_calls += 1
            super().abort()
            release.set()

    def open_stream(*args, **kwargs):
        try:
            assert release.wait(2)
            if worker_error:
                reply.close()
                raise httpx.ReadError("offline completed worker error")
            return reply
        finally:
            finished.set()

    monkeypatch.setattr(chat, "ReplyStreamControl", Control)
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)

    async def scenario():
        prior_tasks = asyncio.all_tasks()
        stream = chat._stream_byok_reply(_context(chat), chat.ChatState(trace={}), mirror=False)
        try:
            assert await asyncio.wait_for(stream.__anext__(), timeout=0.35) == ": thinking\n\n"
            release.set()
            assert await asyncio.to_thread(finished.wait, 1)
            await asyncio.sleep(0.01)
            await stream.aclose()
            assert reply.closed, "completed opening result was abandoned without closing"
            assert controls[0].abort_calls == (0 if worker_error else 1)
            gc.collect()
            await asyncio.sleep(0)
            assert not (asyncio.all_tasks() - prior_tasks)
        finally:
            release.set()
            await stream.aclose()

    asyncio.run(scenario())
    assert not saved
    assert not [record for record in caplog.records if record.name == "asyncio" and record.levelno >= logging.ERROR]
