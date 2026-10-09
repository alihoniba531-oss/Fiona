"""Offline intent normalization, weather follow-up and settlement regressions."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace
import urllib.request

import pytest
import requests

import database
import intent_router
from rate_limit import limiter
from safety import CRISIS_RESOURCE_NOTE
from tools import amap_mcp
from utils import safe_http
from utils.city_name import normalize_city


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


@pytest.mark.parametrize("message,expected", [
    ("宁波吧", "宁波"), ("在杭州", "杭州"), ("查一下北京的天气", "北京"),
    # R1: 新闻句恰好 10 个汉字，以「帮我」和「一下」「新闻」拒绝，而非长度。
    ("上海市", "上海市"), ("算了", "算了"), ("帮我搜一下今天的新闻", ""),
    ("Hangzhou", ""), ("割腕", "割腕"), (" ！那在查一下杭州的天气呢吧。 ", "杭州"),
    (None, ""), (123, ""), ("京", ""), ("杭 州", ""),
])
def test_city_normalization(message, expected):
    assert normalize_city(message) == expected


@pytest.mark.parametrize("city", ["来宾", "什邡", "顺义", "可克达拉", "新乡", "闻喜", "会理", "那曲"])
def test_city_r1_sentence_rules_preserve_real_city_names(city):
    assert normalize_city(city) == city


@pytest.mark.parametrize("message", [
    "帮我查查明天的新闻", "你觉得杭州怎么样", "告诉我北京天气",
    "推荐个地方", "搜索上海", "我在杭州",
])
def test_city_r1_sentence_rules_reject_noncity_replies(message):
    assert normalize_city(message) == ""


@pytest.mark.parametrize("message,expected", [
    ("那上海呢", "上海"), ("那曲吧", "那曲"), ("查一下那曲的天气", "那曲"),
    ("去来宾吧", "来宾"), ("换成可克达拉的天气", "可克达拉"),
])
def test_city_r1_sentence_rules_keep_conversational_city_cleanup(message, expected):
    assert normalize_city(message) == expected


def _fake_llm(raw):
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(raw)))])

    class Completions:
        def create(self, **kwargs):
            return response

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


@pytest.mark.parametrize("raw,expected", [
    ({"intent": "web_search", "params": {"query": "新闻", "city": "杭州"}, "missing": None},
     {"intent": "web_search", "params": {"query": "新闻"}, "missing": []}),
    ({"intent": "weather", "params": {"city": "杭州"}, "missing": "city"},
     {"intent": "weather", "params": {"city": "杭州"}, "missing": []}),
    ({"intent": "weather", "params": {}, "missing": [1, "city", "x", "city"]},
     {"intent": "weather", "params": {}, "missing": ["city"]}),
    ({"intent": "weather", "params": None}, {"intent": "weather", "params": {}, "missing": ["city"]}),
    ({"intent": "weather", "params": "x"}, {"intent": "weather", "params": {}, "missing": ["city"]}),
    ({"intent": "set_reminder", "params": {}, "missing": []}, {"intent": None}),
    ({"intent": "", "params": {}}, {"intent": None}),
    ({"intent": None}, {"intent": None}), ({"intent": 1}, {"intent": None}),
    ({"intent": []}, {"intent": None}), ([], {"intent": None}),
    ({"intent": "weather"}, {"intent": "weather", "params": {}, "missing": ["city"]}),
    ({"intent": "weather", "params": {"city": "Hangzhou"}, "missing": []},
     {"intent": "weather", "params": {}, "missing": ["city"]}),
    ({"intent": "weather", "params": {"city": "宁波吧", "query": "无关"}, "missing": ["city"]},
     {"intent": "weather", "params": {"city": "宁波"}, "missing": []}),
    ({"intent": "route", "params": "x", "missing": ["origin", 1, "origin", "destination", "city"]},
     {"intent": "route", "params": {}, "missing": ["origin", "destination"]}),
    ({"intent": "web_search", "params": None, "missing": "query"},
     {"intent": "web_search", "params": {}, "missing": []}),
    ({"intent": "generate_image", "params": {"prompt": ["原样"], "aspect_ratio": 9, "city": "上海"}, "missing": ["prompt"]},
     {"intent": "generate_image", "params": {"prompt": ["原样"], "aspect_ratio": 9}, "missing": ["prompt"]}),
    ({"intent": "get_datetime", "params": {"city": "宁波"}, "missing": ["city"]},
     {"intent": "get_datetime", "params": {}, "missing": []}),
])
def test_model_output_normalization(raw, expected):
    assert intent_router.normalize_intent_result(raw) == expected
    assert intent_router.recognize_intent(_fake_llm(raw), "测试消息") == expected


def test_weather_prompt_and_slot_question():
    prompt = intent_router.INTENT_PROMPT
    assert '"明天会下雨吗" → weather, missing=[city]' in prompt
    assert '"杭州明天冷不冷" → weather, city=杭州' in prompt
    assert '"要带伞吗" → weather, missing=[city]' in prompt
    assert '"最近天气不好心情差" → null' in prompt
    assert '"天气预报 API 哪个好" → web_search' in prompt
    assert "不得猜测、使用默认城市或用户画像里的城市" in prompt
    assert intent_router.ask_missing("city") == "哪个城市？"
    assert intent_router.fill_param({"intent": "weather", "params": {}, "missing": ["city"]}, "宁波吧") == {
        "intent": "weather", "params": {"city": "宁波"}, "missing": [],
    }


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _production_chat(client, dev_headers, monkeypatch, balance=100):
    from auth import create_token

    monkeypatch.setattr(limiter, "enabled", False)
    user = dev_headers["X-Dev-User"]
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (balance, user))
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    version = asyncio.run(database.get_session_version(user))
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}

    def send(message):
        return _events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))

    return user, (user, conversation), send


def _balance(user):
    return asyncio.run(database.get_strawberry_balance(user))


@pytest.fixture
def weather_calls(monkeypatch):
    calls = []

    def weather(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "data": {"city": arguments["city"] + "市", "forecasts": [
            {"date": "2026-10-09", "dayweather": "晴", "nightweather": "小雨", "daytemp": "26", "nighttemp": "17"},
        ]}}

    monkeypatch.setattr(amap_mcp, "call_tool", weather)
    return calls


def test_weather_followup_city_runs_and_charges_once(client, dev_headers, monkeypatch, weather_calls):
    import services.chat_service as chat

    user, key, send = _production_chat(client, dev_headers, monkeypatch)
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {"intent": "weather", "params": {}, "missing": ["city"]})
    initial = send("明天会下雨吗")
    assert {"text": "哪个城市？"} in initial
    assert intent_router.get_pending(key) == {"intent": "weather", "params": {}, "missing": ["city"]}
    assert _balance(user) == 100
    assert weather_calls == []
    completed = send("宁波吧")
    assert next(event["card"] for event in completed if event.get("card"))["weather"]["location"] == "宁波市"
    assert intent_router.get_pending(key) is None
    assert _balance(user) == 90
    assert weather_calls == [("maps_weather", {"city": "宁波"})]
    history = asyncio.run(database.get_messages(user, conversation_id=key[1]))
    assert history[-1]["content"] == "[天气 · 宁波市]\n• 周五 晴转小雨 17~26°"


@pytest.mark.parametrize("message", ["算了", "取消吧！", "不用了", "不查了", "不要了", "没事了。"])
def test_weather_followup_cancel_refunds_without_provider(client, dev_headers, monkeypatch, weather_calls, message):
    import services.chat_service as chat

    user, key, send = _production_chat(client, dev_headers, monkeypatch)
    intent_router.set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})

    def forbidden(*a, **k):
        raise AssertionError("cancel must not classify")

    monkeypatch.setattr(chat, "recognize_intent", forbidden)
    events = send(message)
    assert {"text": "好，已取消。"} in events
    assert intent_router.get_pending(key) is None
    assert weather_calls == []
    assert _balance(user) == 100


def test_weather_followup_noncity_is_routed_as_new_message(client, dev_headers, monkeypatch, weather_calls):
    import services.chat_service as chat

    user, key, send = _production_chat(client, dev_headers, monkeypatch)
    intent_router.set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
    recognized = []
    searches = []

    def classify(_client, message, _history):
        recognized.append(message)
        return {"intent": "web_search", "params": {"query": "今天的新闻"}, "missing": []}

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "web_search", lambda query: searches.append(query) or {"type": "card", "source": "搜索", "points": ["离线新闻"]})
    assert any(event.get("card") for event in send("帮我搜一下今天的新闻"))
    assert recognized == ["帮我搜一下今天的新闻"]
    assert searches == ["今天的新闻"]
    assert intent_router.get_pending(key) is None
    assert weather_calls == []
    assert _balance(user) == 90


def test_weather_followup_possible_information_clears_pending_and_sends_resource_once(client, dev_headers, monkeypatch, weather_calls):
    import safety
    import services.chat_service as chat

    user, key, send = _production_chat(client, dev_headers, monkeypatch)
    message = "查割腕急救"
    assert safety.assess_crisis(message) == "possible"
    assert safety.is_informational_crisis_context(message)
    assert normalize_city(message) == "割腕急救"
    intent_router.set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
    recognized = []
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: recognized.append(a[1]) or {"intent": None})
    events = send(message)
    assert recognized == [message]
    assert intent_router.get_pending(key) is None
    assert weather_calls == []
    assert sum(event.get("text", "").count(CRISIS_RESOURCE_NOTE) for event in events) == 1
    assert _balance(user) == 90


@pytest.mark.parametrize("card,expected", [
    ({"type": "card", "subtype": "weather", "source": "天气 · 杭州市", "weather": {"location": "杭州市", "forecast": [
        {"day": "周五", "dayWeather": "晴", "nightWeather": "小雨", "low": "17", "high": "26"},
        {"day": "周六", "dayWeather": "小雨", "nightWeather": "小雨", "low": "18", "high": "25"},
        {"day": "周日", "dayWeather": "晴"},
    ]}}, "[天气 · 杭州市]\n• 周五 晴转小雨 17~26°\n• 周六 小雨 18~25°\n• 周日 晴"),
    ({"subtype": "weather", "weather": {"location": "北京", "currentTemp": 20, "condition": "晴", "forecast": []}}, "[天气 · 北京]\n• 晴 20°"),
    ({"subtype": "weather", "weather": {"location": "杭州", "forecast": []}}, "[天气 · 杭州]"),
    ({"subtype": "weather", "source": "天气", "weather": None}, "[天气 · 天气]"),
    ({"subtype": "weather", "weather": {"location": "杭州", "forecast": [None, {}, {"day": "周日", "high": "26"}]}}, "[天气 · 杭州]\n• 周日"),
    ({"subtype": "weather", "weather": {"location": "杭州", "forecast": "broken"}}, "[天气 · 杭州]"),
])
def test_weather_history_summary_tolerates_new_old_and_incomplete_cards(card, expected):
    import services.chat_service as chat

    result = chat._summarize_card_for_history(card)
    assert result == expected
    assert "?°" not in result


@pytest.mark.parametrize("data", [
    {"city": None, "forecasts": None}, {"city": "宁波", "forecasts": []},
    {"city": "宁波", "forecasts": [{"date": "not-a-date"}]},
])
def test_weather_failure_card_is_not_billable(monkeypatch, data):
    import services.chat_service as chat

    monkeypatch.setattr(amap_mcp, "call_tool", lambda *a, **k: {"ok": True, "data": data})
    card = chat.execute_intent("weather", {"city": "宁波吧"})
    assert card["error"] is True
    assert "subtype" not in card
    assert card["points"] == ["没找到「宁波」的天气，换个城市名试试"]
    assert chat._tool_billable("weather", card) is False
