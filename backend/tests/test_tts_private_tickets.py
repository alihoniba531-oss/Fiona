# -*- coding: utf-8 -*-
"""Private TTS text only travels in a POST body, never in playback URLs."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest


@pytest.fixture(autouse=True)
def clear_tts_tickets():
    from routers import voice
    voice._tts_tickets.clear()
    yield
    voice._tts_tickets.clear()


def test_tts_ticket_requires_login(client):
    response = client.post("/tts/ticket", json={"text": "私聊内容"})
    assert response.status_code == 401


def test_tts_ticket_range_probe_then_playback_and_bound_to_user(client, monkeypatch):
    import tts

    spoken = []

    def fake_synthesize(text, voice, speech_rate):
        spoken.append((text, voice, speech_rate))
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    owner = {"X-Dev-User": "tts_owner"}
    other = {"X-Dev-User": "tts_other"}
    issued = client.post("/tts/ticket", headers=owner, json={"text": "私聊内容"})
    assert issued.status_code == 200
    ticket = issued.json()["ticket"]
    assert issued.json()["expires_in"] <= 60
    assert "私聊内容" not in ticket

    denied = client.get("/tts/stream", headers=other, params={"ticket": ticket})
    assert denied.status_code == 404
    probe = client.get(
        "/tts/stream",
        headers={**owner, "Range": "bytes=0-1"},
        params={"ticket": ticket},
    )
    assert probe.status_code == 206
    assert probe.content == b"fa"
    assert probe.headers["content-range"] == "bytes 0-1/8"
    assert probe.headers["content-length"] == "2"
    assert probe.headers["accept-ranges"] == "bytes"
    assert "私聊内容" not in str(probe.request.url)
    played = client.get("/tts/stream", headers={**owner, "Range": "bytes=0-7"}, params={"ticket": ticket})
    assert played.status_code == 206
    assert played.content == b"fake-mp3"
    assert played.headers["content-range"] == "bytes 0-7/8"
    assert played.headers["content-length"] == "8"
    assert "私聊内容" not in str(played.request.url)
    assert spoken == [("私聊内容", "longxiaoxia_v2", 1.15)]
    assert client.get("/tts/stream", headers=other, params={"ticket": ticket}).status_code == 404
    for _ in range(2):
        assert client.get("/tts/stream", headers=owner, params={"ticket": ticket}).status_code == 200
    assert client.get("/tts/stream", headers=owner, params={"ticket": ticket}).status_code == 404
    assert len(spoken) == 1


def test_tts_ticket_expires_and_legacy_text_query_is_rejected(client, monkeypatch):
    from routers import voice
    import tts

    monkeypatch.setattr(tts, "synthesize", lambda *_: (b"fake-mp3", "audio/mpeg"))
    owner = {"X-Dev-User": "tts_owner"}
    issued = client.post("/tts/ticket", headers=owner, json={"text": "不会进网址"})
    assert issued.status_code == 200
    ticket = issued.json()["ticket"]
    assert client.get("/tts/stream", headers=owner, params={"text": "不会进网址"}).status_code == 422
    assert client.get("/tts/synthesize", headers=owner, params={"text": "不会进网址"}).status_code == 422
    assert client.get("/tts/stream", headers=owner, params={"ticket": ticket, "text": "不会进网址"}).status_code == 400
    assert client.get("/tts/synthesize", headers=owner, params={"ticket": ticket, "text": "不会进网址"}).status_code == 400

    entry = voice._tts_tickets[ticket]
    voice._tts_tickets[ticket] = replace(entry, expires_at=0)
    assert client.get("/tts/stream", headers=owner, params={"ticket": ticket}).status_code == 404
    assert ticket not in voice._tts_tickets


def test_tts_ticket_expires_after_range_probe(client, monkeypatch):
    from routers import voice
    import tts

    monkeypatch.setattr(tts, "synthesize", lambda *_: (b"fake-mp3", "audio/mpeg"))
    owner = {"X-Dev-User": "tts_owner"}
    ticket = client.post("/tts/ticket", headers=owner, json={"text": "短期朗读"}).json()["ticket"]
    probe = client.get("/tts/stream", headers={**owner, "Range": "bytes=0-1"}, params={"ticket": ticket})
    assert probe.status_code == 206
    entry = voice._tts_tickets[ticket]
    voice._tts_tickets[ticket] = replace(entry, expires_at=0)
    assert client.get("/tts/stream", headers=owner, params={"ticket": ticket}).status_code == 404
    assert ticket not in voice._tts_tickets


def test_tts_synthesize_shares_ticket_use_limit_with_stream(client, monkeypatch):
    import tts

    spoken = []
    def fake_synthesize(*_):
        spoken.append(1)
        return b"fake-mp3", "audio/mpeg"
    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    async def fake_stream(*_):
        yield b"fake-stream"

    monkeypatch.setattr(tts, "synthesize_stream", fake_stream)
    owner = {"X-Dev-User": "tts_owner"}
    ticket = client.post("/tts/ticket", headers=owner, json={"text": "合成内容"}).json()["ticket"]
    for _ in range(3):
        response = client.get("/tts/synthesize", headers=owner, params={"ticket": ticket})
        assert response.status_code == 200
        assert response.content == b"fake-mp3"
    streamed = client.get("/tts/stream", headers=owner, params={"ticket": ticket})
    assert streamed.status_code == 200
    assert streamed.content == b"fake-mp3"
    assert spoken == [1]
    assert client.get("/tts/synthesize", headers=owner, params={"ticket": ticket}).status_code == 404


@pytest.mark.parametrize("range_header", ["bytes=", "bytes=0-1,2-3", "items=0-1", "bytes=-0", "bytes=3-1", "bytes=100-"])
def test_tts_invalid_or_unsatisfiable_range_returns_416(client, monkeypatch, range_header):
    import tts

    monkeypatch.setattr(tts, "synthesize", lambda *_: (b"fake-mp3", "audio/mpeg"))
    owner = {"X-Dev-User": "tts_owner"}
    ticket = client.post("/tts/ticket", headers=owner, json={"text": "测试"}).json()["ticket"]
    response = client.get("/tts/stream", headers={**owner, "Range": range_header}, params={"ticket": ticket})
    assert response.status_code == 416
    assert response.headers["accept-ranges"] == "bytes"
    if range_header in {"bytes=3-1", "bytes=100-"}:
        assert response.headers["content-range"] == "bytes */8"


def test_tts_first_no_range_stays_streaming_and_then_reuses_cache(client, monkeypatch):
    import tts

    streamed = []
    async def fake_stream(*_):
        streamed.append(1)
        yield b"fake-"
        yield b"mp3"

    monkeypatch.setattr(tts, "synthesize_stream", fake_stream)
    monkeypatch.setattr(tts, "synthesize", lambda *_: pytest.fail("cached stream must avoid a second synthesis"))
    owner = {"X-Dev-User": "tts_owner"}
    ticket = client.post("/tts/ticket", headers=owner, json={"text": "测试"}).json()["ticket"]
    first = client.get("/tts/stream", headers=owner, params={"ticket": ticket})
    assert first.status_code == 200
    assert first.content == b"fake-mp3"
    assert "content-range" not in first.headers
    second = client.get("/tts/stream", headers={**owner, "Range": "bytes=0-"}, params={"ticket": ticket})
    assert second.status_code == 206
    assert second.content == b"fake-mp3"
    assert streamed == [1]


def test_tts_first_zero_open_range_streams_then_reuses_cache_as_206(client, monkeypatch):
    import tts

    streamed = []

    async def fake_stream(*_):
        streamed.append(1)
        yield b"fake-"
        yield b"mp3"

    monkeypatch.setattr(tts, "synthesize_stream", fake_stream)
    monkeypatch.setattr(tts, "synthesize", lambda *_: pytest.fail("zero-open playback must stream first"))
    owner = {"X-Dev-User": "tts_owner"}
    ticket = client.post("/tts/ticket", headers=owner, json={"text": "测试"}).json()["ticket"]
    first = client.get("/tts/stream", headers={**owner, "Range": "bytes=0-"}, params={"ticket": ticket})
    assert first.status_code == 200
    assert first.content == b"fake-mp3"
    assert "content-range" not in first.headers
    assert "content-length" not in first.headers

    cached = client.get("/tts/stream", headers={**owner, "Range": "bytes=0-"}, params={"ticket": ticket})
    assert cached.status_code == 206
    assert cached.content == b"fake-mp3"
    assert cached.headers["content-range"] == "bytes 0-7/8"
    assert cached.headers["content-length"] == "8"
    assert streamed == [1]


def test_tts_cache_budget_evicts_audio_but_preserves_ticket(client, monkeypatch):
    from routers import voice
    import tts

    monkeypatch.setattr(voice, "TTS_MAX_CACHED_AUDIO_BYTES", 10)
    synthesized = []

    def fake_synthesize(text, *_):
        synthesized.append(text)
        return b"12345678", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    owner = {"X-Dev-User": "tts_owner"}
    first = client.post("/tts/ticket", headers=owner, json={"text": "第一句"}).json()["ticket"]
    second = client.post("/tts/ticket", headers=owner, json={"text": "第二句"}).json()["ticket"]
    for ticket in (first, second):
        assert client.get("/tts/stream", headers={**owner, "Range": "bytes=0-1"}, params={"ticket": ticket}).status_code == 206
    assert first in voice._tts_tickets
    assert voice._tts_tickets[first].cached_audio is None
    assert voice._tts_tickets[first].audio_build is None
    assert voice._tts_tickets[first].uses == 1
    # A WebKit probe may lose its cache before the full playback request. The
    # ticket must still authorize that request, which can synthesize again.
    played = client.get("/tts/stream", headers={**owner, "Range": "bytes=0-7"}, params={"ticket": first})
    assert played.status_code == 206
    assert played.content == b"12345678"
    assert voice._tts_tickets[first].uses == 2
    assert synthesized == ["第一句", "第二句", "第一句"]
    assert sum(len(entry.cached_audio or b"") for entry in voice._tts_tickets.values()) <= 10


def test_overlapping_range_requests_share_one_synthesis(client, monkeypatch):
    import tts

    calls = []
    lock = threading.Lock()
    def fake_synthesize(*_):
        with lock:
            calls.append(1)
        time.sleep(0.04)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    owner = {"X-Dev-User": "tts_owner"}
    ticket = client.post("/tts/ticket", headers=owner, json={"text": "测试"}).json()["ticket"]
    def fetch(_):
        return client.get("/tts/stream", headers={**owner, "Range": "bytes=0-7"}, params={"ticket": ticket})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, range(4)))
    assert all(response.status_code == 206 and response.content == b"fake-mp3" for response in results)
    assert calls == [1]
