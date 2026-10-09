"""Weather account caps and local validation with every network path blocked."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import sqlite3
from threading import Event
import urllib.request

import pytest
import requests

import database
import intent_router
import rate_limit
from rate_limit import limiter
from safety import CRISIS_RESOURCE_NOTE
from tools import amap_mcp
from utils import safe_http


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(safe_http, "_open_pinned", blocked)
    yield
    assert not attempted, "network"


@pytest.fixture(autouse=True)
def reset_daily_counters():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def production_caps(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("FIONA_DAILY_WEATHER", "2")
    monkeypatch.setattr(limiter, "enabled", True)


@pytest.mark.parametrize("invalid", ["0", "-1", "1.5", "abc", "", " 2 "])
def test_weather_daily_environment_falls_back_and_warns_once(monkeypatch, capsys, invalid):
    monkeypatch.setenv("FIONA_DAILY_WEATHER", invalid)
    monkeypatch.setattr(rate_limit, "_INVALID_DAILY_WARNED", set())
    assert rate_limit.daily_cap("weather") == 30
    assert rate_limit.daily_cap("weather") == 30
    assert capsys.readouterr().out.count("FIONA_DAILY_WEATHER") == 1


def test_weather_default_cap_and_public_message(monkeypatch):
    monkeypatch.delenv("FIONA_DAILY_WEATHER", raising=False)
    assert rate_limit.daily_cap("weather") == 30
    message = "今天查天气的次数已用完，明天再试"
    assert rate_limit.daily_cap_message("weather") == message
    response = rate_limit.daily_cap_response("weather")
    assert response.status_code == 429
    assert json.loads(response.body)["error"] == message
    assert 1 <= int(response.headers["Retry-After"]) <= 86400


def test_chat_cap_check_does_not_count_and_shares_existing_daily_keys(production_caps):
    for _ in range(3):
        assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=False) is None
    assert rate_limit.check_daily_cap("weather", "user-a") is None
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=False) == rate_limit.daily_cap_message("weather")
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) == rate_limit.daily_cap_message("weather")
    assert rate_limit.check_chat_daily_cap("weather", "user-b", hit=True) is None


def test_weather_live_cap_change_and_beijing_day_reset(production_caps, monkeypatch):
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
    monkeypatch.setenv("FIONA_DAILY_WEATHER", "1")
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=False)
    monkeypatch.setenv("FIONA_DAILY_WEATHER", "2")
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True)
    tomorrow = (date.fromisoformat(database._today_shanghai()) + timedelta(days=1)).isoformat()
    monkeypatch.setattr(database, "_today_shanghai", lambda: tomorrow)
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None


@pytest.mark.parametrize("disabled_by", ["dev", "limiter"])
def test_weather_disabled_caps_do_not_count(production_caps, monkeypatch, disabled_by):
    if disabled_by == "dev":
        monkeypatch.setenv("DEV_MODE", "1")
    else:
        monkeypatch.setattr(limiter, "enabled", False)
    for _ in range(3):
        assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(limiter, "enabled", True)
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True)


def test_chat_daily_cap_runs_with_saturated_default_thread_pool(production_caps):
    entered, release = Event(), Event()

    def block_pool():
        entered.set()
        release.wait(5)

    async def run():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        blocked = loop.run_in_executor(None, block_pool)
        try:
            while not entered.is_set():
                await asyncio.sleep(0)
            assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
            assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True) is None
            assert rate_limit.check_chat_daily_cap("weather", "user-a", hit=True)
        finally:
            release.set()
            await blocked

    asyncio.run(run())


@pytest.fixture
def weather_chat(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from auth import create_token

    monkeypatch.setattr(limiter, "enabled", False)
    user = dev_headers["X-Dev-User"]
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE users SET strawberry_balance = 100 WHERE username = ?", (user,))
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    monkeypatch.setenv("FIONA_DAILY_WEATHER", "2")
    monkeypatch.setattr(limiter, "enabled", True)
    version = asyncio.run(database.get_session_version(user))
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}
    calls = []

    def provider(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "data": {"city": "杭州市", "forecasts": [
            {"date": "2026-10-09", "dayweather": "晴", "nightweather": "晴", "daytemp": "26", "nighttemp": "17"},
        ]}}

    monkeypatch.setattr(amap_mcp, "call_tool", provider)
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {"intent": "weather", "params": {"city": "杭州"}, "missing": []})

    def send(message="杭州天气"):
        response = client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation})
        assert response.status_code == 200, response.text
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    return user, (user, conversation), send, calls


def _balance(user):
    return asyncio.run(database.get_strawberry_balance(user))


def test_third_weather_query_is_error_without_charge_or_pending(weather_chat):
    user, key, send, calls = weather_chat
    assert any(event.get("card") for event in send())
    assert any(event.get("card") for event in send())
    assert _balance(user) == 80
    assert send() == [{"error": rate_limit.daily_cap_message("weather")}]
    assert _balance(user) == 80
    assert intent_router.get_pending(key) is None
    assert len(calls) == 2


def test_missing_city_questions_do_not_count_and_exhausted_cap_does_not_write_pending(weather_chat, monkeypatch):
    import services.chat_service as chat

    user, key, send, calls = weather_chat
    missing = {"intent": "weather", "params": {}, "missing": ["city"]}
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: missing)
    for _ in range(3):
        events = send("明天会下雨吗")
        assert {"text": "哪个城市？"} in events
        intent_router.clear_pending(key)
    assert calls == []
    assert _balance(user) == 100
    assert rate_limit.check_chat_daily_cap("weather", user, hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", user, hit=True) is None
    assert send("明天会下雨吗") == [{"error": rate_limit.daily_cap_message("weather")}]
    assert intent_router.get_pending(key) is None
    assert _balance(user) == 100


def test_upstream_failure_counts_weather_quota_but_refunds_strawberries(weather_chat, monkeypatch):
    user, key, send, calls = weather_chat

    def fail(name, arguments):
        calls.append((name, arguments))
        return {"ok": False, "error": "timeout"}

    monkeypatch.setattr(amap_mcp, "call_tool", fail)
    for _ in range(2):
        events = send()
        card = next(event["card"] for event in events if event.get("card"))
        assert card["error"] is True
        assert card["points"] == ["天气服务响应超时，稍后再试"]
    assert send() == [{"error": rate_limit.daily_cap_message("weather")}]
    assert _balance(user) == 100
    assert intent_router.get_pending(key) is None
    assert len(calls) == 2


def test_pending_completed_after_exhaustion_clears_without_charge(weather_chat):
    user, key, send, calls = weather_chat
    assert rate_limit.check_chat_daily_cap("weather", user, hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", user, hit=True) is None
    intent_router.set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
    assert send("宁波吧") == [{"error": rate_limit.daily_cap_message("weather")}]
    assert intent_router.get_pending(key) is None
    assert _balance(user) == 100
    assert calls == []


@pytest.fixture
def isolated_stream(monkeypatch):
    import services.chat_service as chat

    pending = {}

    async def saved(ctx, state, *a, **k):
        state.response_saved = True

    monkeypatch.setattr(chat, "_save_response", saved)
    monkeypatch.setattr(chat, "set_pending", lambda key, value: pending.update(value))
    monkeypatch.setattr(chat, "clear_pending", lambda key: pending.clear())
    ctx = chat.ChatContext(user="weather-stream-user", message="杭州", has_image=False, image_base64=None,
        user_content="杭州", history=[], message_count=0, system_prompt="", messages=[])

    def consume(stream):
        async def collect():
            return [json.loads(event[6:]) async for event in stream]
        return asyncio.run(collect())

    return chat, ctx, pending, consume


@pytest.mark.parametrize("branch", ["direct", "pending"])
def test_empty_city_local_failure_does_not_count(production_caps, isolated_stream, branch):
    chat, ctx, pending, consume = isolated_stream
    ctx.message = "Hangzhou"
    state = chat.ChatState(trace={})
    if branch == "direct":
        stream = chat.stream_intent(ctx, state, {"intent": "weather", "params": {"city": ""}, "missing": []})
    else:
        stream = chat.stream_pending(ctx, state, {"intent": "weather", "params": {}, "missing": ["city"]})
    events = consume(stream)
    assert next(event["card"] for event in events if event.get("card"))["points"] == ["没说是哪个城市"]
    assert state.billable is False
    assert pending == {}
    assert rate_limit.check_chat_daily_cap("weather", ctx.user, hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", ctx.user, hit=True) is None
    assert rate_limit.check_chat_daily_cap("weather", ctx.user, hit=True)


@pytest.mark.parametrize("branch", ["direct_complete", "direct_missing", "pending_complete", "pending_missing"])
def test_each_weather_cap_rejection_sends_crisis_resource_once(production_caps, isolated_stream, branch):
    chat, ctx, pending, consume = isolated_stream
    for _ in range(2):
        assert rate_limit.check_chat_daily_cap("weather", ctx.user, hit=True) is None
    state = chat.ChatState(trace={}, crisis_level="possible")
    if branch.startswith("direct"):
        missing = [] if branch.endswith("complete") else ["city"]
        stream = chat.stream_intent(ctx, state, {"intent": "weather", "params": {"city": "杭州"}, "missing": missing})
    else:
        pending.update({"old": True})
        missing = ["city"] if branch.endswith("complete") else ["city", "city"]
        stream = chat.stream_pending(ctx, state, {"intent": "weather", "params": {}, "missing": missing})
    events = consume(stream)
    assert sum(event.get("text", "").count(CRISIS_RESOURCE_NOTE) for event in events) == 1
    assert events[-1] == {"error": rate_limit.daily_cap_message("weather")}
    assert state.trace["error"] == "DailyCapExceeded"
    assert state.billable is False
    assert pending == {}


def test_weather_cap_rejection_does_not_wait_on_default_pool(production_caps, isolated_stream, monkeypatch):
    chat, ctx, pending, consume = isolated_stream
    for _ in range(2):
        assert rate_limit.check_chat_daily_cap("weather", ctx.user, hit=True) is None

    async def forbidden(*a, **k):
        raise AssertionError("daily check must be synchronous")

    monkeypatch.setattr(asyncio, "to_thread", forbidden)
    state = chat.ChatState(trace={})
    events = consume(chat.stream_intent(ctx, state, {"intent": "weather", "params": {"city": "杭州"}, "missing": []}))
    assert events == [{"error": rate_limit.daily_cap_message("weather")}]
    assert pending == {}


@pytest.mark.parametrize("branch", ["direct", "pending"])
def test_weather_failure_sends_card_before_crisis_resource(production_caps, isolated_stream, monkeypatch, branch):
    chat, ctx, pending, consume = isolated_stream
    card = {"type": "card", "source": "天气", "points": ["天气服务响应超时，稍后再试"], "error": True}
    monkeypatch.setattr(chat, "execute_intent", lambda intent, params: card)
    saved = []

    async def save(ctx, state, *a, **k):
        saved.append(state.full_response)
        state.response_saved = True

    monkeypatch.setattr(chat, "_save_response", save)
    state = chat.ChatState(trace={}, crisis_level="possible")
    if branch == "direct":
        stream = chat.stream_intent(ctx, state, {"intent": "weather", "params": {"city": "杭州"}, "missing": []})
    else:
        stream = chat.stream_pending(ctx, state, {"intent": "weather", "params": {}, "missing": ["city"]})
    events = consume(stream)
    assert events[0] == {"card": card}
    assert CRISIS_RESOURCE_NOTE in events[1]["text"]
    assert sum(event.get("text", "").count(CRISIS_RESOURCE_NOTE) for event in events) == 1
    assert state.full_response == "[天气]\n• 天气服务响应超时，稍后再试\n\n" + CRISIS_RESOURCE_NOTE
    assert saved == [state.full_response]
    assert state.billable is False


def test_pending_city_completions_consume_weather_daily_cap(weather_chat, client, monkeypatch):
    import services.chat_service as chat
    from auth import create_token

    user, first_key, _, calls = weather_chat
    version = asyncio.run(database.get_session_version(user))
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}
    conversations = [first_key[1]]
    for _ in range(2):
        response = client.post("/conversations", headers=headers, json={})
        assert response.status_code == 201, response.text
        conversations.append(response.json()["conversation"]["id"])
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
        "intent": "weather", "params": {}, "missing": ["city"],
    })

    def send(conversation, message):
        response = client.post("/chat", headers=headers, json={
            "message": message, "conversation_id": conversation,
        })
        assert response.status_code == 200, response.text
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    # Establish all three follow-ups before completions exhaust the account cap;
    # otherwise the third question is rejected by the non-consuming check.
    for conversation in conversations:
        assert {"text": "哪个城市？"} in send(conversation, "明天会下雨吗")
        assert intent_router.get_pending((user, conversation)) == {
            "intent": "weather", "params": {}, "missing": ["city"],
        }
    assert calls == []
    assert _balance(user) == 100
    for conversation in conversations[:2]:
        events = send(conversation, "宁波吧")
        card = next(event["card"] for event in events if event.get("card"))
        assert card["subtype"] == "weather"
        assert card["error"] is False
        assert intent_router.get_pending((user, conversation)) is None
    assert calls == [("maps_weather", {"city": "宁波"})] * 2
    assert _balance(user) == 80
    assert send(conversations[2], "宁波吧") == [{"error": rate_limit.daily_cap_message("weather")}]
    assert calls == [("maps_weather", {"city": "宁波"})] * 2
    assert intent_router.get_pending((user, conversations[2])) is None
    assert _balance(user) == 80
