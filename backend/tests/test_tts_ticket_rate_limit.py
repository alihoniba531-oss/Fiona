"""The four TTS ticket quotas share one all-or-nothing decision."""

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import random

from limits import parse
import pytest

from rate_limit import check_and_hit, limiter
from routers import voice


@pytest.fixture(autouse=True)
def reset_tts_quotas_and_tickets():
    limiter.reset()
    with voice._tts_tickets_lock:
        voice._tts_tickets.clear()
    yield
    with voice._tts_tickets_lock:
        voice._tts_tickets.clear()
    limiter.reset()


def _headers(user: str = "tts-user-a", ip: str = "198.51.100.10") -> dict[str, str]:
    return {"X-Dev-User": user, "X-Real-IP": ip}


def _ticket(client, text: str = "朗读测试", *, user: str = "tts-user-a", ip: str = "198.51.100.10", **headers):
    return client.post("/tts/ticket", headers={**_headers(user, ip), **headers}, json={"text": text})


def _remaining(limit: str, scope: str, owner: str, kind: str) -> int:
    return limiter.limiter.get_window_stats(
        parse(limit), "tts_ticket", scope, owner, kind
    ).remaining


def test_user_request_quota_is_independent_for_users_sharing_an_ip(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_REQUESTS", "3/minute")

    assert [_ticket(client).status_code for _ in range(3)] == [200] * 3
    assert _ticket(client).status_code == 429
    assert _ticket(client, user="tts-user-b").status_code == 200


def test_429_has_matching_retry_header_and_body_without_issuing_ticket_or_prewarm(
    client, monkeypatch, capsys,
):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_REQUESTS", "1/minute")
    assert _ticket(client).status_code == 200
    issued_count = len(voice._tts_tickets)
    prewarm_calls = []

    async def fake_prewarm(*_):
        prewarm_calls.append(1)

    monkeypatch.setattr(voice, "_build_tts_audio", fake_prewarm)
    denied = _ticket(
        client, "private denied text", ip="198.51.100.123", user="tts-user-a",
        **{"User-Agent": "AppleWebKit/605.1.15 Safari/605.1.15"},
    )
    assert denied.status_code == 429
    retry_after = int(denied.headers["Retry-After"])
    assert 1 <= retry_after <= 60
    assert denied.json() == {
        "detail": "朗读请求太频繁，请稍后再试",
        "retry_after": retry_after,
    }
    assert len(voice._tts_tickets) == issued_count
    assert prewarm_calls == []
    log = capsys.readouterr().out
    assert f"[TTS限流] scope=user kind=count retry_after={retry_after}" in log
    assert "tts-user-a" not in log
    assert "198.51.100.123" not in log
    assert "private denied text" not in log


def test_char_quota_does_not_charge_denied_request(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_CHARS", "700/minute")

    assert _ticket(client, "字" * 300).status_code == 200
    assert _ticket(client, "字" * 300).status_code == 200
    assert _ticket(client, "字" * 300).status_code == 429
    assert _remaining("700/minute", "user", "tts-user-a", "chars") == 100
    assert _ticket(client, "字" * 100).status_code == 200
    assert _remaining("700/minute", "user", "tts-user-a", "chars") == 0


def test_char_cost_is_capped_at_300_for_2000_character_ticket(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_CHARS", "300/minute")

    response = _ticket(client, "字" * 2000)
    assert response.status_code == 200
    assert len(voice._tts_tickets[response.json()["ticket"]].text) == 2000
    assert _remaining("300/minute", "user", "tts-user-a", "chars") == 0
    assert _ticket(client, "字").status_code == 429


def test_ip_request_quota_catches_many_accounts_but_other_ip_is_independent(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_IP_REQUESTS", "5/minute")

    for number in range(5):
        assert _ticket(client, user=f"tts-ip-user-{number}").status_code == 200
    assert _ticket(client, user="tts-ip-user-5").status_code == 429
    assert _ticket(client, user="tts-ip-user-5", ip="198.51.100.11").status_code == 200


def test_user_quota_rejection_does_not_charge_either_ip_quota(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_REQUESTS", "1/minute")
    assert _ticket(client, "first").status_code == 200
    ip_before = (
        _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
        _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
    )

    assert _ticket(client, "second sentence").status_code == 429
    assert ip_before == (
        _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
        _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
    )


@pytest.mark.parametrize(
    ("headers", "text", "expected"),
    [
        ({"X-Real-IP": "198.51.100.10"}, "valid", 401),
        (_headers(), "   ", 400),
        (_headers(), "", 422),
        (_headers(), "字" * 2001, 422),
    ],
)
def test_auth_and_validation_failures_charge_no_quota(client, monkeypatch, headers, text, expected):
    monkeypatch.setattr(limiter, "enabled", True)
    response = client.post("/tts/ticket", headers=headers, json={"text": text})
    assert response.status_code == expected
    for scope, owner, count_limit, char_limit in (
        ("user", "tts-user-a", voice.TTS_TICKET_USER_REQUESTS, voice.TTS_TICKET_USER_CHARS),
        ("ip", "198.51.100.10", voice.TTS_TICKET_IP_REQUESTS, voice.TTS_TICKET_IP_CHARS),
    ):
        assert _remaining(count_limit, scope, owner, "count") == parse(count_limit).amount
        assert _remaining(char_limit, scope, owner, "chars") == parse(char_limit).amount


def test_disabled_limiter_never_counts(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_REQUESTS", "1/minute")
    monkeypatch.setattr(voice, "TTS_TICKET_IP_REQUESTS", "1/minute")

    assert [_ticket(client).status_code for _ in range(3)] == [200] * 3
    assert _remaining("1/minute", "user", "tts-user-a", "count") == 1
    assert _remaining("1/minute", "ip", "198.51.100.10", "count") == 1


def test_default_quotas_admit_real_use_sequences_in_one_window(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    script = Path(__file__).resolve().parents[2] / "docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py"
    spec = importlib.util.spec_from_file_location("tts_rate_model_for_test", script)
    assert spec is not None and spec.loader is not None
    model = importlib.util.module_from_spec(spec)
    random_state = random.getstate()
    try:
        with redirect_stdout(io.StringIO()):
            spec.loader.exec_module(model)
        short_chunks = model.chunks(model.R["c 碎句连发"])
        long_chunks = model.chunks(model.R["e 顶格长回复(~900字)"])
    finally:
        random.setstate(random_state)
    assert (len(short_chunks), len(long_chunks)) == (69, 37)

    for chunk in short_chunks + long_chunks:
        assert _ticket(client, chunk).status_code == 200
    assert _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count") == 14


def test_default_char_quotas_can_admit_one_max_size_ticket():
    assert parse(voice.TTS_TICKET_USER_CHARS).amount >= voice.TTS_TICKET_MAX_CHARS
    assert parse(voice.TTS_TICKET_IP_CHARS).amount >= voice.TTS_TICKET_MAX_CHARS


def test_generic_check_does_not_charge_later_gate_when_first_fails(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    checks = [
        ("1/minute", ("tts-generic", "first"), 1),
        ("2/minute", ("tts-generic", "second"), 1),
    ]
    assert check_and_hit(checks) is None
    rejected = []
    retry_after = check_and_hit(checks, on_reject=lambda identifiers, seconds: rejected.append((identifiers, seconds)))
    assert 1 <= retry_after <= 60
    assert rejected == [(checks[0][1], retry_after)]
    assert limiter.limiter.get_window_stats(parse("2/minute"), "tts-generic", "second").remaining == 1


def test_user_char_gate_rejection_preserves_earlier_user_and_both_ip_quotas(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_USER_CHARS", "300/minute")
    assert _ticket(client, "字" * 300).status_code == 200
    before = (
        _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
        _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
        _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
        _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
    )
    assert before == (
        parse(voice.TTS_TICKET_USER_REQUESTS).amount - 1,
        0,
        parse(voice.TTS_TICKET_IP_REQUESTS).amount - 1,
        parse(voice.TTS_TICKET_IP_CHARS).amount - 300,
    )

    assert _ticket(client, "字" * 300).status_code == 429
    assert (
        _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
        _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
        _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
        _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
    ) == before


def test_last_ip_char_gate_rejection_preserves_both_user_and_earlier_ip_quotas(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr(voice, "TTS_TICKET_IP_CHARS", "300/minute")
    assert _ticket(client, "字" * 300).status_code == 200
    before = (
        _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
        _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
        _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
        _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
    )
    assert before == (
        parse(voice.TTS_TICKET_USER_REQUESTS).amount - 1,
        parse(voice.TTS_TICKET_USER_CHARS).amount - 300,
        parse(voice.TTS_TICKET_IP_REQUESTS).amount - 1,
        0,
    )

    assert _ticket(client, "字" * 300).status_code == 429
    assert (
        _remaining(voice.TTS_TICKET_USER_REQUESTS, "user", "tts-user-a", "count"),
        _remaining(voice.TTS_TICKET_USER_CHARS, "user", "tts-user-a", "chars"),
        _remaining(voice.TTS_TICKET_IP_REQUESTS, "ip", "198.51.100.10", "count"),
        _remaining(voice.TTS_TICKET_IP_CHARS, "ip", "198.51.100.10", "chars"),
    ) == before


@pytest.mark.parametrize(
    ("reset_offsets", "expected"),
    [
        ((2.0, 9.0), 9),
        ((1.25, 2.01), 3),
        ((-10.0, -0.25), 1),
        ((9.0, 2.0), 9),
        ((-10.0, -2.5), 1),
    ],
    ids=(
        "latest-failed-reset", "fractional-seconds-ceil", "past-reset-minimum-one",
        "larger-reset-first", "past-reset-minimum-one-2",
    ),
)
def test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one(monkeypatch, reset_offsets, expected):
    from types import SimpleNamespace
    import rate_limit

    monkeypatch.setattr(limiter, "enabled", True)
    now = 1_000.0
    monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: now))
    checks = [
        ("1/minute", ("tts-retry", "first"), 1),
        ("2/minute", ("tts-retry", "second"), 1),
        ("3/minute", ("tts-retry", "passing"), 1),
    ]
    resets = {
        checks[0][1]: now + reset_offsets[0],
        checks[1][1]: now + reset_offsets[1],
        checks[2][1]: now + 999.0,
    }
    queried = []
    hits = []

    def fake_window_stats(self, _item, *identifiers):
        queried.append(identifiers)
        return SimpleNamespace(reset_time=resets[identifiers], remaining=0)

    monkeypatch.setattr(type(limiter.limiter), "test", lambda self, _item, *identifiers, cost: identifiers == checks[2][1])
    monkeypatch.setattr(type(limiter.limiter), "get_window_stats", fake_window_stats)
    monkeypatch.setattr(type(limiter.limiter), "hit", lambda self, _item, *identifiers, cost: hits.append(identifiers))

    assert check_and_hit(checks) == expected
    assert queried == [checks[0][1], checks[1][1]]
    assert hits == []


def test_rejection_callback_reports_first_failed_gate_once(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    checks = [
        ("1/minute", ("tts-reject-callback", "first"), 1),
        ("1/minute", ("tts-reject-callback", "second"), 1),
    ]
    assert check_and_hit(checks) is None
    assert all(
        not limiter.limiter.test(parse(limit), *identifiers, cost=cost)
        for limit, identifiers, cost in checks
    )
    rejected = []

    retry_after = check_and_hit(
        checks, on_reject=lambda identifiers, seconds: rejected.append((identifiers, seconds))
    )

    assert isinstance(retry_after, int) and 1 <= retry_after <= 60
    assert rejected == [(checks[0][1], retry_after)]


def test_retry_after_class_patches_leave_no_instance_method_residue(monkeypatch):
    strategy = limiter.limiter
    strategy_class = type(strategy)
    method_names = ("test", "get_window_stats", "hit")
    original_methods = {name: getattr(strategy_class, name) for name in method_names}
    assert all(name not in vars(strategy) for name in method_names)

    with monkeypatch.context() as patch:
        test_retry_after_uses_latest_failed_reset_ceil_and_minimum_one(patch, (2.0, 9.0), 9)

    assert "test" not in vars(strategy)
    for name in method_names:
        assert name not in vars(strategy)
        assert getattr(strategy_class, name) is original_methods[name]
