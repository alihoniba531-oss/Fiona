"""WebKit tickets prewarm once while other engines keep streaming playback."""

import asyncio
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import sys
import threading
import time

import pytest


SAFARI_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
CHROME_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0_0) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
EDGE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
IOS_CHROME_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 CriOS/126.0.0.0 Mobile/15E148 Safari/604.1"
IOS_FIREFOX_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 FxiOS/126.0 Mobile/15E148 Safari/605.1.15"
OWNER = {"X-Dev-User": "webkit_tts_owner"}


@pytest.fixture(autouse=True)
def clear_tickets():
    from routers import voice

    voice.limiter.reset()
    with voice._tts_tickets_lock:
        voice._tts_tickets.clear()
    yield
    with voice._tts_tickets_lock:
        voice._tts_tickets.clear()
    voice.limiter.reset()


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_safari_ticket_prewarms_once_for_probe_and_playback(client, monkeypatch):
    from routers import voice
    import tts

    calls = []

    def fake_synthesize(text, voice_name, rate):
        calls.append((text, voice_name, rate))
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    issued = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"})
    assert issued.status_code == 200
    ticket = issued.json()["ticket"]
    wait_until(lambda: voice._tts_tickets[ticket].cached_audio == b"fake-mp3")
    assert calls == [("首句", "longxiaoxia_v2", 1.15)]

    probe = client.get("/tts/stream", headers={**OWNER, "Range": "bytes=0-1"}, params={"ticket": ticket})
    played = client.get("/tts/stream", headers={**OWNER, "Range": "bytes=0-7"}, params={"ticket": ticket})
    assert probe.status_code == 206
    assert probe.content == b"fa"
    assert probe.headers["content-range"] == "bytes 0-1/8"
    assert played.status_code == 206
    assert played.content == b"fake-mp3"
    assert played.headers["content-range"] == "bytes 0-7/8"
    assert len(calls) == 1


def test_range_waits_for_pending_prewarm_and_gets_finite_length(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_synthesize(*_):
        calls.append(1)
        started.set()
        assert release.wait(2)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"}).json()["ticket"]
    try:
        assert started.wait(2)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.get,
                "/tts/stream",
                headers={**OWNER, "Range": "bytes=0-"},
                params={"ticket": ticket},
            )
            wait_until(lambda: voice._tts_tickets[ticket].uses == 1 and not pending.done())
            assert calls == [1]
            release.set()
            played = pending.result(timeout=2)
    finally:
        release.set()
    assert played.status_code == 206
    assert played.content == b"fake-mp3"
    assert played.headers["content-range"] == "bytes 0-7/8"
    assert calls == [1]


@pytest.mark.parametrize("user_agent", [CHROME_UA, EDGE_UA])
def test_desktop_chromium_tickets_do_not_prewarm_and_zero_open_range_streams(client, monkeypatch, user_agent):
    from routers import voice
    import tts

    def unexpected_synthesize(*_):
        pytest.fail("desktop Chromium must not start non-streaming synthesis")

    streamed = []

    async def fake_stream(*_):
        streamed.append(1)
        yield b"fake-mp3"

    monkeypatch.setattr(tts, "synthesize", unexpected_synthesize)
    monkeypatch.setattr(tts, "synthesize_stream", fake_stream)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": user_agent}, json={"text": "首句"}).json()["ticket"]
    assert voice._tts_tickets[ticket].audio_build is None
    first = client.get("/tts/stream", headers={**OWNER, "Range": "bytes=0-"}, params={"ticket": ticket})
    assert first.status_code == 200
    assert first.content == b"fake-mp3"
    assert "content-range" not in first.headers
    assert streamed == [1]


@pytest.mark.parametrize("user_agent", [IOS_CHROME_UA, IOS_FIREFOX_UA])
def test_ios_alternate_browsers_use_webkit_prewarm(client, monkeypatch, user_agent):
    from routers import voice
    import tts

    calls = []

    def fake_synthesize(*_):
        calls.append(1)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": user_agent}, json={"text": "首句"}).json()["ticket"]
    wait_until(lambda: voice._tts_tickets[ticket].cached_audio == b"fake-mp3")
    assert calls == [1]


def test_failed_prewarm_allows_next_range_to_retry(client, monkeypatch):
    from routers import voice
    import tts

    calls = []

    def fake_synthesize(*_):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("stub failure")
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"}).json()["ticket"]
    wait_until(lambda: len(calls) == 1 and voice._tts_tickets[ticket].audio_build is None)
    played = client.get("/tts/stream", headers={**OWNER, "Range": "bytes=0-7"}, params={"ticket": ticket})
    assert played.status_code == 206
    assert played.content == b"fake-mp3"
    assert calls == [1, 1]


@pytest.mark.parametrize("invalidated", ["expired", "evicted"])
def test_invalidated_prewarm_discards_its_result(client, monkeypatch, invalidated):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def fake_synthesize(*_):
        started.set()
        try:
            assert release.wait(2)
            return b"fake-mp3", "audio/mpeg"
        finally:
            finished.set()

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"}).json()["ticket"]
    try:
        assert started.wait(2)
        with voice._tts_tickets_lock:
            entry = voice._tts_tickets[ticket]
            build = entry.audio_build
            assert build is not None
            task = build.prewarm_task
            assert task is not None
            if invalidated == "expired":
                voice._tts_tickets[ticket] = replace(entry, expires_at=0)
        if invalidated == "expired":
            expired = client.get("/tts/stream", headers={**OWNER, "Range": "bytes=0-1"}, params={"ticket": ticket})
            assert expired.status_code == 404
        else:
            monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 1)
            replacement = client.post("/tts/ticket", headers={**OWNER, "User-Agent": CHROME_UA}, json={"text": "第二句"})
            assert replacement.status_code == 200
        wait_until(task.done)
        assert task.cancelled()
        assert build.done.is_set()
        assert build.audio is None
    finally:
        release.set()
    assert finished.wait(2)
    assert build.audio is None
    with voice._tts_tickets_lock:
        assert ticket not in voice._tts_tickets


def test_prewarm_wait_is_capped_by_ticket_ttl(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def fake_synthesize(*_):
        started.set()
        try:
            assert release.wait(2)
            return b"fake-mp3", "audio/mpeg"
        finally:
            finished.set()

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    monkeypatch.setattr(voice, "TTS_TICKET_TTL_SECONDS", 0.08)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"}).json()["ticket"]
    try:
        assert started.wait(2)
        with voice._tts_tickets_lock:
            build = voice._tts_tickets[ticket].audio_build
            assert build is not None
            task = build.prewarm_task
            assert task is not None
        wait_until(task.done)
        assert build.done.is_set()
        assert build.audio is None
        with voice._tts_tickets_lock:
            assert ticket not in voice._tts_tickets
    finally:
        release.set()
    assert finished.wait(2)
    assert build.audio is None


def test_prewarmed_audio_obeys_total_cache_budget(client, monkeypatch):
    from routers import voice
    import tts

    monkeypatch.setattr(voice, "TTS_MAX_CACHED_AUDIO_BYTES", 10)
    monkeypatch.setattr(tts, "synthesize", lambda *_: (b"12345678", "audio/mpeg"))
    first = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "第一句"}).json()["ticket"]
    wait_until(lambda: voice._tts_tickets[first].cached_audio == b"12345678")
    second = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "第二句"}).json()["ticket"]
    wait_until(lambda: voice._tts_tickets[second].cached_audio == b"12345678")
    assert voice._tts_tickets[first].cached_audio is None
    assert voice._tts_tickets[first].audio_build is None
    assert sum(len(item.cached_audio or b"") for item in voice._tts_tickets.values()) <= 10


def test_on_demand_closed_range_returns_audio_after_ticket_ttl(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()

    def fake_synthesize(*_):
        started.set()
        assert release.wait(2)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    monkeypatch.setattr(voice, "TTS_TICKET_TTL_SECONDS", 0.4)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": CHROME_UA}, json={"text": "长句"}).json()["ticket"]
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.get, "/tts/stream", headers={**OWNER, "Range": "bytes=0-7"}, params={"ticket": ticket},
            )
            assert started.wait(2)
            wait_until(lambda: time.monotonic() > voice._tts_tickets[ticket].expires_at)
            release.set()
            response = pending.result(timeout=2)
    finally:
        release.set()
    assert response.status_code == 206
    assert response.content == b"fake-mp3"
    assert ticket not in voice._tts_tickets


def test_on_demand_closed_range_returns_audio_after_ticket_eviction(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()

    def fake_synthesize(*_):
        started.set()
        assert release.wait(2)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 1)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": CHROME_UA}, json={"text": "长句"}).json()["ticket"]
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.get, "/tts/stream", headers={**OWNER, "Range": "bytes=0-7"}, params={"ticket": ticket},
            )
            assert started.wait(2)
            replacement = client.post(
                "/tts/ticket", headers={**OWNER, "User-Agent": CHROME_UA}, json={"text": "下一句"},
            )
            assert replacement.status_code == 200
            assert ticket not in voice._tts_tickets
            release.set()
            response = pending.result(timeout=2)
    finally:
        release.set()
    assert response.status_code == 206
    assert response.content == b"fake-mp3"


def test_on_demand_stream_waiter_returns_audio_after_ticket_ttl(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()

    async def fake_stream(*_):
        started.set()
        yield b"fake-"
        assert await asyncio.to_thread(release.wait, 2)
        yield b"mp3"

    monkeypatch.setattr(tts, "synthesize_stream", fake_stream)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": CHROME_UA}, json={"text": "长句"}).json()["ticket"]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            streaming = pool.submit(client.get, "/tts/stream", headers=OWNER, params={"ticket": ticket})
            assert started.wait(2)
            waiting = pool.submit(
                client.get, "/tts/stream", headers={**OWNER, "Range": "bytes=0-7"}, params={"ticket": ticket},
            )
            def waiter_registered():
                with voice._tts_tickets_lock:
                    entry = voice._tts_tickets[ticket]
                    build = entry.audio_build
                    return entry.uses == 2 and build is not None and bool(build.waiters)

            wait_until(waiter_registered)
            with voice._tts_tickets_lock:
                entry = voice._tts_tickets[ticket]
                voice._tts_tickets[ticket] = replace(entry, expires_at=time.monotonic() + 0.05)
            wait_until(lambda: time.monotonic() > voice._tts_tickets[ticket].expires_at)
            release.set()
            streamed = streaming.result(timeout=2)
            played = waiting.result(timeout=2)
    finally:
        release.set()
    assert streamed.status_code == 200
    assert streamed.content == b"fake-mp3"
    assert played.status_code == 206
    assert played.content == b"fake-mp3"
    assert ticket not in voice._tts_tickets


def test_webkit_probe_wait_does_not_block_default_pool_thread(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()

    def fake_synthesize(*_):
        started.set()
        assert release.wait(2)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"}).json()["ticket"]
    try:
        assert started.wait(2)
        build = voice._tts_tickets[ticket].audio_build
        assert build is not None
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.get, "/tts/stream", headers={**OWNER, "Range": "bytes=0-1"}, params={"ticket": ticket},
            )
            wait_until(lambda: bool(build.waiters) and not pending.done())
            names = {thread.ident: thread.name for thread in threading.enumerate()}
            blocked = []
            for ident, frame in sys._current_frames().items():
                if not names.get(ident, "").startswith("fiona-chat"):
                    continue
                while frame is not None:
                    if frame.f_code.co_name == "wait" and frame.f_locals.get("self") is build.done:
                        blocked.append(names[ident])
                    frame = frame.f_back
            assert blocked == []
            release.set()
            played = pending.result(timeout=2)
    finally:
        release.set()
    assert played.status_code == 206
    assert played.content == b"fa"


def test_invalidated_prewarm_wakes_waiters_on_separate_event_loops(client, monkeypatch):
    from routers import voice
    import tts

    started = threading.Event()
    release = threading.Event()

    def fake_synthesize(*_):
        started.set()
        assert release.wait(2)
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    ticket = client.post("/tts/ticket", headers={**OWNER, "User-Agent": SAFARI_UA}, json={"text": "首句"}).json()["ticket"]
    try:
        assert started.wait(2)
        with voice._tts_tickets_lock:
            entry = voice._tts_tickets[ticket]
            build = entry.audio_build
            assert build is not None
            task = build.prewarm_task
            assert task is not None
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(lambda: asyncio.run(build.wait()))
            second = pool.submit(lambda: asyncio.run(build.wait()))
            wait_until(lambda: len(build.waiters) == 2)
            with voice._tts_tickets_lock:
                voice._tts_tickets.pop(ticket)
                voice._cancel_tts_prewarm(entry)
            assert first.result(timeout=2) is None
            assert second.result(timeout=2) is None
        wait_until(task.done)
        assert task.cancelled()
        assert build.audio is None
    finally:
        release.set()
