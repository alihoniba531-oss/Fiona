"""TTS lifetime and pending-ticket caps stay consistent at request time."""

from dataclasses import replace
import threading
import time

import pytest

from routers import voice


SAFARI_UA = "AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15"


@pytest.fixture(autouse=True)
def isolated_tts_state(monkeypatch):
    import tts

    voice.limiter.reset()
    monkeypatch.setattr(voice.limiter, "enabled", False)
    monkeypatch.setattr(tts, "synthesize", lambda *_: (b"fake-mp3", "audio/mpeg"))

    async def fake_stream(*_):
        yield b"fake-mp3"

    monkeypatch.setattr(tts, "synthesize_stream", fake_stream)
    with voice._tts_tickets_lock:
        voice._tts_tickets.clear()
    yield
    with voice._tts_tickets_lock:
        for entry in voice._tts_tickets.values():
            voice._cancel_tts_prewarm(entry)
        voice._tts_tickets.clear()
    voice.limiter.reset()


def issue_ticket(client, user="ttl-user-a", text="朗读测试", **headers):
    response = client.post(
        "/tts/ticket", headers={"X-Dev-User": user, **headers}, json={"text": text},
    )
    assert response.status_code == 200
    return response.json()


def play_ticket(client, ticket, user="ttl-user-a", endpoint="/tts/stream"):
    return client.get(endpoint, headers={"X-Dev-User": user}, params={"ticket": ticket})


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_default_ttl_matches_response_and_ticket_expiry(client):
    assert voice.TTS_TICKET_TTL_SECONDS == 150
    assert voice.TTS_MAX_PENDING_TICKETS_PER_USER == 64
    issued = issue_ticket(client)
    assert issued["expires_in"] == 150
    remaining = voice._tts_tickets[issued["ticket"]].expires_at - time.monotonic()
    assert 149 <= remaining <= 150


def test_ttl_is_read_on_each_request(client, monkeypatch):
    assert issue_ticket(client)["expires_in"] == 150
    monkeypatch.setattr(voice, "TTS_TICKET_TTL_SECONDS", 5)
    issued = issue_ticket(client)
    assert issued["expires_in"] == 5
    remaining = voice._tts_tickets[issued["ticket"]].expires_at - time.monotonic()
    assert 4 <= remaining <= 5


@pytest.mark.parametrize("endpoint", ["/tts/stream", "/tts/synthesize"])
def test_ticket_works_until_expiry_then_returns_404(client, endpoint):
    ticket = issue_ticket(client)["ticket"]
    valid = play_ticket(client, ticket, endpoint=endpoint)
    assert valid.status_code == 200
    assert valid.content == b"fake-mp3"
    with voice._tts_tickets_lock:
        voice._tts_tickets[ticket] = replace(
            voice._tts_tickets[ticket], expires_at=time.monotonic() - 1,
        )
    assert play_ticket(client, ticket, endpoint=endpoint).status_code == 404
    assert ticket not in voice._tts_tickets


def test_user_cap_evicts_only_own_oldest_tickets(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 3)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 5)
    other_tickets = [issue_ticket(client, user="ttl-user-b")["ticket"] for _ in range(2)]
    own_tickets = [issue_ticket(client)["ticket"] for _ in range(5)]

    assert list(voice._tts_tickets) == other_tickets + own_tickets[2:]
    for ticket in own_tickets[:2]:
        assert play_ticket(client, ticket).status_code == 404
    for ticket in own_tickets[2:]:
        assert play_ticket(client, ticket).status_code == 200
    for ticket in other_tickets:
        assert play_ticket(client, ticket, user="ttl-user-b").status_code == 200


def test_user_cap_cancels_evicted_webkit_prewarm(client, monkeypatch):
    import tts

    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 3)
    release = threading.Event()
    started = [threading.Event() for _ in range(5)]
    finished = [threading.Event() for _ in range(5)]

    def fake_synthesize(text, *_):
        index = int(text)
        started[index].set()
        try:
            assert release.wait(5)
            return b"fake-mp3", "audio/mpeg"
        finally:
            finished[index].set()

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    other = issue_ticket(client, user="ttl-user-b")["ticket"]
    own_tickets = []
    builds = []
    tasks = []
    try:
        for index in range(5):
            ticket = issue_ticket(client, text=str(index), **{"User-Agent": SAFARI_UA})["ticket"]
            own_tickets.append(ticket)
            assert started[index].wait(2)
            with voice._tts_tickets_lock:
                build = voice._tts_tickets[ticket].audio_build
                assert build is not None
                task = build.prewarm_task
                assert task is not None
                builds.append(build)
                tasks.append(task)

        assert list(voice._tts_tickets) == [other] + own_tickets[2:]
        for build, task in zip(builds[:2], tasks[:2]):
            wait_until(task.done)
            assert task.cancelled()
            assert build.done.is_set()
            assert build.audio is None
        assert all(not task.done() for task in tasks[2:])
        for ticket in own_tickets[:2]:
            assert play_ticket(client, ticket).status_code == 404
    finally:
        release.set()
        for event in finished[:len(own_tickets)]:
            assert event.wait(2)

    for ticket in own_tickets[2:]:
        wait_until(lambda: voice._tts_tickets[ticket].cached_audio == b"fake-mp3")
        assert play_ticket(client, ticket).status_code == 200
    assert play_ticket(client, other, user="ttl-user-b").status_code == 200


def test_global_cap_keeps_original_fifo_across_users(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 3)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 20)
    users = ["ttl-user-a", "ttl-user-b", "ttl-user-c", "ttl-user-a", "ttl-user-b"]
    tickets = [issue_ticket(client, user=user)["ticket"] for user in users]

    assert list(voice._tts_tickets) == tickets[2:]
    for user, ticket in zip(users[:2], tickets[:2]):
        assert play_ticket(client, ticket, user=user).status_code == 404
    for user, ticket in zip(users[2:], tickets[2:]):
        assert play_ticket(client, ticket, user=user).status_code == 200


def test_user_cap_is_read_on_each_request_and_shrinks_existing_backlog(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 10)
    tickets = [issue_ticket(client)["ticket"] for _ in range(5)]
    assert list(voice._tts_tickets) == tickets

    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 3)
    replacement = issue_ticket(client)["ticket"]
    assert list(voice._tts_tickets) == tickets[-2:] + [replacement]
    for ticket in tickets[:-2]:
        assert play_ticket(client, ticket).status_code == 404
    for ticket in tickets[-2:] + [replacement]:
        assert play_ticket(client, ticket).status_code == 200


def test_expired_cleanup_precedes_user_and_global_eviction(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 3)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 4)
    other = issue_ticket(client, user="ttl-user-b")["ticket"]
    expired = issue_ticket(client)["ticket"]
    live = [issue_ticket(client)["ticket"] for _ in range(2)]
    with voice._tts_tickets_lock:
        voice._tts_tickets[expired] = replace(voice._tts_tickets[expired], expires_at=0)

    replacement = issue_ticket(client)["ticket"]
    assert list(voice._tts_tickets) == [other] + live + [replacement]
    assert play_ticket(client, expired).status_code == 404
    assert play_ticket(client, other, user="ttl-user-b").status_code == 200
    for ticket in live + [replacement]:
        assert play_ticket(client, ticket).status_code == 200


def test_expired_newest_ticket_is_cleaned_before_user_cap_evicts_oldest(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 2)
    a1 = issue_ticket(client, text="a1")["ticket"]
    a2 = issue_ticket(client, text="a2")["ticket"]
    with voice._tts_tickets_lock:
        voice._tts_tickets[a2] = replace(voice._tts_tickets[a2], expires_at=0)

    a3 = issue_ticket(client, text="a3")["ticket"]
    assert list(voice._tts_tickets) == [a1, a3]
    assert play_ticket(client, a1).status_code == 200
    assert play_ticket(client, a3).status_code == 200


def test_expired_newest_ticket_is_cleaned_before_global_cap_evicts_oldest(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 3)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 20)
    b1 = issue_ticket(client, user="ttl-user-b", text="b1")["ticket"]
    a1 = issue_ticket(client, text="a1")["ticket"]
    c1 = issue_ticket(client, user="ttl-user-c", text="c1")["ticket"]
    with voice._tts_tickets_lock:
        voice._tts_tickets[c1] = replace(voice._tts_tickets[c1], expires_at=0)

    a2 = issue_ticket(client, text="a2")["ticket"]
    assert list(voice._tts_tickets) == [b1, a1, a2]
    assert play_ticket(client, b1, user="ttl-user-b").status_code == 200
    assert play_ticket(client, a1).status_code == 200
    assert play_ticket(client, a2).status_code == 200


def test_global_cap_evicts_oldest_other_user_ticket_without_caller_preference(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 3)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 20)
    a1 = issue_ticket(client, text="a1")["ticket"]
    b1 = issue_ticket(client, user="ttl-user-b", text="b1")["ticket"]
    b2 = issue_ticket(client, user="ttl-user-b", text="b2")["ticket"]
    b3 = issue_ticket(client, user="ttl-user-b", text="b3")["ticket"]

    assert list(voice._tts_tickets) == [b1, b2, b3]
    assert play_ticket(client, a1).status_code == 404
    for ticket in [b1, b2, b3]:
        assert play_ticket(client, ticket, user="ttl-user-b").status_code == 200


def test_global_cap_evicts_oldest_caller_ticket_without_other_user_preference(client, monkeypatch):
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS", 3)
    monkeypatch.setattr(voice, "TTS_MAX_PENDING_TICKETS_PER_USER", 20)
    a1 = issue_ticket(client, text="a1")["ticket"]
    b1 = issue_ticket(client, user="ttl-user-b", text="b1")["ticket"]
    b2 = issue_ticket(client, user="ttl-user-b", text="b2")["ticket"]
    a2 = issue_ticket(client, text="a2")["ticket"]

    assert list(voice._tts_tickets) == [b1, b2, a2]
    assert play_ticket(client, a1).status_code == 404
    for ticket in [b1, b2]:
        assert play_ticket(client, ticket, user="ttl-user-b").status_code == 200
    assert play_ticket(client, a2).status_code == 200
