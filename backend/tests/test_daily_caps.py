"""Production account quotas, local validation and live daily configuration."""
import asyncio
import base64
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier

import pytest

import database
import rate_limit
from rate_limit import limiter


SETTINGS = {
    "official_exchange": ("FIONA_DAILY_OFFICIAL_EXCHANGES", 3),
    "hot_expand": ("FIONA_DAILY_HOT_EXPANDS", 30),
    "card_detail": ("FIONA_DAILY_CARD_DETAILS", 30),
    "asr": ("FIONA_DAILY_ASR", 300),
}
MESSAGES = {
    "official_exchange": "今天的官方体验次数已用完（每天 2 次），明天再来吧。",
    "hot_expand": "今天的热点展开次数已用完，明天再来吧。",
    "card_detail": "今天的详情查看次数已用完，明天再来吧。",
    "asr": "今天的语音识别次数已用完，明天再来吧，可以先打字。",
}


@pytest.fixture(autouse=True)
def reset_daily_counters():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def quotas(client, monkeypatch):
    from auth import create_token
    from official_agents import list_official_agents
    from routers import agent_exchanges, cards, voice
    from tools import topic_expand

    monkeypatch.setattr(limiter, "enabled", False)
    users = ("daily-account-a", "daily-account-b")
    headers = {}
    for user in users:
        result = client.put("/agents/me", headers={"X-Dev-User": user}, json={
            "display_name": user, "bio": "每日体验测试", "is_public": False,
        })
        assert result.status_code == 200, result.text
        version = asyncio.run(database.get_session_version(user))
        headers[user] = {"Authorization": f"Bearer {create_token(user, version)}"}
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-daily-test-key")
    for name, _ in SETTINGS.values():
        monkeypatch.setenv(name, "2")
    monkeypatch.setattr(limiter, "enabled", True)
    calls = []

    def finish_official(exchange_id, _run_token):
        calls.append("official_exchange")
        # Finish the provider-free fixture so active-exchange limits do not mask
        # the daily quota; align SQLite timestamps with the patched test day.
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("""UPDATE agent_exchanges SET status = 'completed', run_token = NULL,
                created_at = ? WHERE id = ?""",
                (database._today_shanghai() + " 04:00:00", exchange_id))

    def expand(title):
        calls.append("hot_expand")
        return {"title": title, "summary": "离线热点"}

    def detail(title, context):
        calls.append("card_detail")
        return {"title": title, "summary": "离线详情"}

    def recognize(*args):
        calls.append("asr")
        return {"text": "离线语音"}

    monkeypatch.setattr(agent_exchanges, "start_exchange", finish_official)
    monkeypatch.setattr(topic_expand, "topic_expand", expand)
    monkeypatch.setattr(cards, "card_detail", detail)
    monkeypatch.setattr(voice, "asr_recognize", recognize)
    card_id = list_official_agents()[0]["id"]

    def request(kind, user=users[0], **overrides):
        auth_headers = headers[user]
        if kind == "official_exchange":
            return client.post("/agent-exchanges/official", headers=auth_headers, json={
                "official_agent_id": card_id, "topic": "讨论每日体验", **overrides,
            })
        if kind == "hot_expand":
            return client.get("/hot/expand", headers=auth_headers, params={"title": "离线话题", **overrides})
        if kind == "card_detail":
            return client.post("/cards/detail", headers=auth_headers, json={"title": "离线卡片", **overrides})
        return client.post("/asr/recognize", headers=auth_headers, json={
            "audio": base64.b64encode(b"\x01\x00\x02\x00").decode(),
            "format": "pcm", "sample_rate": 16000, **overrides,
        })

    return request, calls, users


def _assert_rejected(response, message):
    assert response.status_code == 429, response.text
    retry_after = int(response.headers["Retry-After"])
    assert 1 <= retry_after <= 86400
    assert response.json() == {"detail": message, "error": message, "retry_after": retry_after}


@pytest.mark.parametrize("kind", SETTINGS)
def test_daily_quota_is_per_account_and_resets_at_beijing_day(quotas, monkeypatch, kind):
    request, calls, users = quotas
    success = 201 if kind == "official_exchange" else 200
    today = database._today_shanghai()
    assert [request(kind).status_code for _ in range(2)] == [success, success]
    _assert_rejected(request(kind), MESSAGES[kind])
    assert calls.count(kind) == 2
    assert request(kind, users[1]).status_code == success
    monkeypatch.setattr(database, "_today_shanghai", lambda: (date.fromisoformat(today) + timedelta(days=1)).isoformat())
    assert [request(kind).status_code for _ in range(2)] == [success, success]
    _assert_rejected(request(kind), MESSAGES[kind])
    assert calls.count(kind) == 5


@pytest.mark.parametrize("kind", SETTINGS)
@pytest.mark.parametrize("disabled_by", ["dev", "limiter"])
def test_dev_mode_or_disabled_limiter_bypasses_daily_quota(quotas, monkeypatch, kind, disabled_by):
    request, calls, _ = quotas
    monkeypatch.setenv(SETTINGS[kind][0], "1")
    if disabled_by == "dev":
        monkeypatch.setenv("DEV_MODE", "1")
    else:
        monkeypatch.setattr(limiter, "enabled", False)
    success = 201 if kind == "official_exchange" else 200
    assert [request(kind).status_code for _ in range(3)] == [success] * 3
    assert calls.count(kind) == 3
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(limiter, "enabled", True)
    # Official creations remain in SQLite even while daily enforcement is off.
    expected = 429 if kind == "official_exchange" else success
    assert request(kind).status_code == expected


@pytest.mark.parametrize("kind", SETTINGS)
def test_live_cap_change_preserves_already_used_account_count(quotas, monkeypatch, kind):
    request, calls, _ = quotas
    success = 201 if kind == "official_exchange" else 200
    monkeypatch.setenv(SETTINGS[kind][0], "3")
    assert request(kind).status_code == success
    monkeypatch.setenv(SETTINGS[kind][0], "1")
    message = MESSAGES[kind].replace("每天 2 次", "每天 1 次")
    _assert_rejected(request(kind), message)
    assert calls.count(kind) == 1
    monkeypatch.setenv(SETTINGS[kind][0], "2")
    assert request(kind).status_code == success
    _assert_rejected(request(kind), MESSAGES[kind])


@pytest.mark.parametrize("kind", SETTINGS)
@pytest.mark.parametrize("invalid", ["0", "-1", "1.5", "abc", "", " 2 "])
def test_invalid_daily_environment_falls_back_and_warns_once(monkeypatch, capsys, kind, invalid):
    name, default = SETTINGS[kind]
    monkeypatch.setattr(rate_limit, "_INVALID_DAILY_WARNED", set())
    monkeypatch.setenv(name, invalid)
    assert rate_limit.daily_cap(kind) == default
    assert rate_limit.daily_cap(kind) == default
    assert capsys.readouterr().out.count(name) == 1
    monkeypatch.setenv(name, "1")
    assert rate_limit.daily_cap(kind) == 1


@pytest.mark.parametrize("kind", SETTINGS)
def test_missing_daily_environment_uses_spec_default(monkeypatch, kind):
    name, default = SETTINGS[kind]
    monkeypatch.delenv(name, raising=False)
    assert rate_limit.daily_cap(kind) == default


def test_daily_item_does_not_replace_limits_string_parser():
    from limits import RateLimitItemPerDay, parse

    first, second = parse("1/day"), parse("2/day")
    assert type(first) is type(second) is RateLimitItemPerDay
    assert first.key_for("existing", "quota") != second.key_for("existing", "quota")
    assert rate_limit._DailyLimitItem(1).key_for("daily", "quota") == rate_limit._DailyLimitItem(2).key_for("daily", "quota")


def test_empty_hot_title_and_missing_key_do_not_count(quotas, monkeypatch):
    request, calls, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_HOT_EXPANDS", "1")
    assert request("hot_expand", title="  ").json() == {"title": "", "error": "标题为空"}
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    assert request("hot_expand").json() == {"title": "离线话题", "error": "DASHSCOPE_API_KEY 未设置"}
    assert calls == []
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-daily-test-key")
    assert request("hot_expand").status_code == 200
    _assert_rejected(request("hot_expand"), MESSAGES["hot_expand"])


@pytest.mark.parametrize("invalid", [
    {"audio": ""}, {"audio": "!not-base64!"}, {"audio": "AAAA", "sample_rate": 7999},
])
def test_invalid_asr_requests_do_not_count(quotas, monkeypatch, invalid):
    request, calls, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_ASR", "1")
    assert request("asr", **invalid).status_code in (200, 422)
    assert calls == []
    assert request("asr").status_code == 200
    _assert_rejected(request("asr"), MESSAGES["asr"])


def test_asr_size_and_duration_failures_do_not_count(quotas, monkeypatch):
    from routers import voice

    request, calls, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_ASR", "1")
    with monkeypatch.context() as patch:
        patch.setattr(voice, "ASR_MAX_SOURCE_BYTES", 2)
        assert request("asr").status_code == 413
    with monkeypatch.context() as patch:
        patch.setattr(voice, "ASR_MAX_DURATION_SECONDS", 0)
        assert request("asr").status_code == 413
    assert calls == []
    assert request("asr").status_code == 200
    _assert_rejected(request("asr"), MESSAGES["asr"])


def test_ffmpeg_conversion_failure_does_not_count(quotas, monkeypatch):
    from routers import voice

    request, calls, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_ASR", "1")
    def fail_conversion(*args):
        raise RuntimeError("offline ffmpeg failure")
    monkeypatch.setattr(voice, "_ffmpeg_to_wav", fail_conversion)
    assert request("asr", format="opus").json()["error"] == "audio conversion failed"
    assert calls == []
    assert request("asr").status_code == 200
    _assert_rejected(request("asr"), MESSAGES["asr"])


def test_blank_card_title_does_not_count(quotas, monkeypatch):
    request, calls, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_CARD_DETAILS", "1")
    assert request("card_detail", title="  ").status_code == 422
    assert calls == []
    assert request("card_detail").status_code == 200
    _assert_rejected(request("card_detail"), MESSAGES["card_detail"])


@pytest.mark.parametrize("kind", ["card_detail", "asr"])
@pytest.mark.parametrize("missing_key", [None, ""])
def test_card_and_asr_missing_key_do_not_consume_daily_quota(quotas, monkeypatch, kind, missing_key):
    from tools.card_detail import detail_error

    request, calls, _ = quotas
    monkeypatch.setenv(SETTINGS[kind][0], "1")
    if missing_key is None:
        monkeypatch.delenv("DASHSCOPE_API_KEY")
    else:
        monkeypatch.setenv("DASHSCOPE_API_KEY", missing_key)
    expected = (detail_error("离线卡片", "详情搜索暂不可用，请稍后重试")
                if kind == "card_detail"
                else {"text": "", "error": "DASHSCOPE_API_KEY not set"})
    for _ in range(2):
        response = request(kind)
        assert response.status_code == 200
        assert response.json() == expected
    assert calls == []
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-daily-test-key")
    assert request(kind).status_code == 200
    assert calls == [kind]
    _assert_rejected(request(kind), MESSAGES[kind])


def test_asr_blank_key_is_checked_like_provider_before_daily_quota(quotas, monkeypatch):
    request, calls, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_ASR", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", " \t ")
    assert request("asr").json() == {"text": "", "error": "DASHSCOPE_API_KEY not set"}
    assert calls == []
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-daily-test-key")
    assert request("asr").status_code == 200
    _assert_rejected(request("asr"), MESSAGES["asr"])


@pytest.mark.parametrize("kind", ["hot_expand", "card_detail", "asr"])
def test_upstream_failure_still_consumes_daily_quota(quotas, monkeypatch, kind):
    from routers import cards, voice
    from tools import topic_expand

    request, _, _ = quotas
    monkeypatch.setenv(SETTINGS[kind][0], "1")
    if kind == "hot_expand":
        monkeypatch.setattr(topic_expand, "topic_expand", lambda *a: {"error": "offline provider failure"})
    elif kind == "card_detail":
        monkeypatch.setattr(cards, "card_detail", lambda *a: {"error": "offline provider failure"})
    else:
        monkeypatch.setattr(voice, "asr_recognize", lambda *a: {"text": "", "error": "offline provider failure"})
    assert request(kind).json()["error"] == "offline provider failure"
    _assert_rejected(request(kind), MESSAGES[kind])


def test_official_last_daily_slot_is_atomic_and_unknown_id_still_404(quotas, monkeypatch):
    from routers import agent_exchanges

    request, _, _ = quotas
    monkeypatch.setenv("FIONA_DAILY_OFFICIAL_EXCHANGES", "3")
    assert [request("official_exchange").status_code for _ in range(2)] == [201, 201]
    # Leave the winning creation running: the second request must report daily
    # exhaustion rather than the older active-exchange conflict.
    monkeypatch.setattr(agent_exchanges, "start_exchange", lambda *args: None)
    barrier = Barrier(2)
    def create(_):
        barrier.wait(timeout=5)
        return request("official_exchange")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, range(2)))
    assert sorted(response.status_code for response in responses) == [201, 429]
    rejected = next(response for response in responses if response.status_code == 429)
    _assert_rejected(rejected, MESSAGES["official_exchange"].replace("每天 2 次", "每天 3 次"))
    assert request("official_exchange", official_agent_id="missing-official").status_code == 404
    import exchange_store
    assert not issubclass(exchange_store.OfficialDailyCapExceeded, exchange_store.ExchangeConflict)


def test_stopped_and_failed_official_creations_still_count(quotas):
    request, _, users = quotas
    assert [request("official_exchange").status_code for _ in range(2)] == [201, 201]
    with sqlite3.connect(database.DB_PATH) as db:
        ids = [row[0] for row in db.execute(
            "SELECT id FROM agent_exchanges WHERE initiator_username = ? ORDER BY id", (users[0],),
        )]
        for exchange_id, status in zip(ids, ("stopped", "failed")):
            db.execute("UPDATE agent_exchanges SET status = ? WHERE id = ?", (status, exchange_id))
    _assert_rejected(request("official_exchange"), MESSAGES["official_exchange"])


def test_official_creation_uses_beijing_day_for_sqlite_utc_timestamp(quotas, monkeypatch):
    request, _, users = quotas
    monkeypatch.setenv("FIONA_DAILY_OFFICIAL_EXCHANGES", "1")
    assert request("official_exchange").status_code == 201
    previous = (date.fromisoformat(database._today_shanghai()) - timedelta(days=1)).isoformat()
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE agent_exchanges SET created_at = ? WHERE initiator_username = ?",
                   (previous + " 16:00:00", users[0]))
    _assert_rejected(request("official_exchange"), MESSAGES["official_exchange"].replace("每天 2 次", "每天 1 次"))
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE agent_exchanges SET created_at = ? WHERE initiator_username = ?",
                   (previous + " 15:59:59", users[0]))
    assert request("official_exchange").status_code == 201


@pytest.mark.parametrize("kind", SETTINGS)
def test_paid_daily_endpoints_do_not_charge_strawberries(quotas, kind):
    request, _, users = quotas
    before = asyncio.run(database.get_strawberry_balance(users[0]))
    assert request(kind).status_code == (201 if kind == "official_exchange" else 200)
    assert asyncio.run(database.get_strawberry_balance(users[0])) == before


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 10, 5, 23, 59, 59, 500000, tzinfo=timezone(timedelta(hours=8))), 1),
    (datetime(2026, 10, 5, 23, 59, 58, 500000, tzinfo=timezone(timedelta(hours=8))), 2),
    (datetime(2026, 10, 5, 0, 0, 0, tzinfo=timezone(timedelta(hours=8))), 86400),
])
def test_retry_after_is_ceiled_seconds_to_beijing_midnight(monkeypatch, now, expected):
    class Clock:
        @staticmethod
        def now(tz):
            return now
    monkeypatch.setattr(rate_limit, "datetime", Clock)
    response = rate_limit.daily_cap_response("asr")
    assert int(response.headers["Retry-After"]) == expected
