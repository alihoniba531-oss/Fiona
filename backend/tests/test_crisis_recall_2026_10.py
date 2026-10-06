"""Traditional plan spellings and possible-turn routing guardrails."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from _fakes import FakeStream
import safety


TRADITIONAL_PLAN_CASES = [
    ("計畫明天跳海", "high"),
    ("計畫吞藥", "high"),
    ("計畫下週跳河", "high"),
    ("計畫今晚跳江", "high"),
    ("計畫割腕", "high"),
    ("計畫上吊", "high"),
    ("計畫自殺", "high"),
    ("計畫下週跳樓", "high"),
    ("我計畫明天跳海", "high"),
    ("計畫下週去日本旅行", None),
    ("计划下周去海边玩", None),
]


@pytest.mark.parametrize("message,expected", TRADITIONAL_PLAN_CASES)
def test_traditional_plan_cases(message, expected):
    assert safety.assess_crisis(message) == expected


PLAN_AND_WORD_BOUNDARY_CASES = [
    ("计划明天跳河", "high"),
    ("计画明天跳河", "high"),
    ("计畫明天跳河", "high"),
    ("計劃明天跳河", "high"),
    ("計畫明天跳河", "high"),
    ("計画明天跳河", "high"),
    ("我在做设计画面，主角最后跳河", None),
    ("统计画面显示上吊人数", "possible"),
    ("我在做設計畫面，主角最後跳河", None),
    ("統計畫面顯示上吊人數", "possible"),
]


@pytest.mark.parametrize("message,expected", PLAN_AND_WORD_BOUNDARY_CASES)
def test_plan_spellings_and_design_word_boundaries(message, expected):
    assert safety.assess_crisis(message) == expected


INFORMATIONAL_CONTEXT_CASES = [
    ("帮我查下割腕的急救方法", True),
    ("請搜跳樓的心理研究", True),
    ("报道自杀预防研究", True),
    ("我朋友想死", False),
    ("查一下安眠药吃多少会有危险", False),
    ("帮我查下明天天气", False),
    ("帮我查下割腕的急救方法，我想死", False),
    ("帮我查下割腕的急救方法，画一张猫", True),
]


@pytest.mark.parametrize("message,expected", INFORMATIONAL_CONTEXT_CASES)
def test_informational_context_requires_existing_help_rule_and_possible(message, expected):
    assert safety.is_informational_crisis_context(message) is expected
    if expected:
        assert safety.assess_crisis(message) == "possible"


POSSIBLE = "活着没意思"
SEARCH_POSSIBLE = "查一下安眠药吃多少会有危险"
IMAGE_CANDIDATE_POSSIBLE = "画一张猫，活着没意思"
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)
IMAGE = f"data:image/png;base64,{PNG}"


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _conversation(client, headers):
    response = client.post("/conversations", json={}, headers=headers)
    assert response.status_code == 201
    return response.json()["conversation"]["id"]


def _balance(user):
    import database

    return asyncio.run(database.get_strawberry_balance(user))


def _production_headers(monkeypatch, user):
    import database
    from auth import create_token

    version = asyncio.run(database.get_session_version(user))
    monkeypatch.setenv("DEV_MODE", "0")
    return {"Authorization": f"Bearer {create_token(user, version)}"}


def _routing_spies(monkeypatch, *, mode="friend"):
    """Observe the real orchestration while replacing every model and tool."""
    import services.chat_service as chat

    calls = {name: [] for name in (
        "candidate", "fallback", "recognize", "fill", "execute", "generate", "clear",
        "detect", "model", "vision", "trace", "normal", "mirror", "image", "pending", "intent",
    )}

    def observe_sync(name, function):
        def observed(*args, **kwargs):
            calls[name].append(args)
            return function(*args, **kwargs)
        return observed

    def observe_stream(name, function):
        async def observed(*args, **kwargs):
            calls[name].append(args[0].message)
            async for event in function(*args, **kwargs):
                yield event
        return observed

    def detect(_client, _key, message, _history):
        calls["detect"].append(message)
        return mode

    def model(*args, **kwargs):
        calls["model"].append(kwargs["max_tokens"])
        return FakeStream(), False

    def vision(**kwargs):
        calls["vision"].append(kwargs["max_tokens"])
        return FakeStream()

    def recognize(_client, message, _history):
        calls["recognize"].append(message)
        return {"intent": "web_search", "params": {"query": message}, "missing": []}

    def execute(intent, params):
        calls["execute"].append((intent, params))
        return {"type": "card", "source": "搜索结果", "points": ["模拟工具结果"]}

    def fill(pending, message):
        calls["fill"].append(message)
        return {**pending, "params": {**pending["params"], "origin": message}, "missing": []}

    async def generate(*args, **kwargs):
        calls["generate"].append(args)
        raise AssertionError("possible conversational turns must not generate images")

    async def trace(*args, **kwargs):
        if len(args) > 1 and args[1] == "chat":
            calls["trace"].append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "explicit_image_intent", observe_sync("candidate", chat.explicit_image_intent))
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", observe_sync("fallback", chat.recognize_intent_with_fallback))
    monkeypatch.setattr(chat, "clear_pending", observe_sync("clear", chat.clear_pending))
    for name in ("normal", "mirror", "image", "pending", "intent"):
        attribute = f"stream_{name}"
        monkeypatch.setattr(chat, attribute, observe_stream(name, getattr(chat, attribute)))
    monkeypatch.setattr(chat, "detect_mode", detect)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", model)
    monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=vision)),
    ))
    monkeypatch.setattr(chat, "recognize_intent", recognize)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "fill_param", fill)
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat, "edit_image", generate)
    monkeypatch.setattr(chat, "log_event", trace)
    return calls


def _assert_possible_reply(events, calls):
    assert events[-2:] == [{"text": "\n\n" + safety.CRISIS_RESOURCE_NOTE}, {"done": True}]
    assert sum(event.get("text", "").count(safety.CRISIS_RESOURCE_NOTE) for event in events) == 1
    assert not any(event.get("crisis") or "error" in event or "generated_image" in event for event in events)
    assert len(calls["trace"]) == 1
    assert calls["trace"][0]["crisis"] == "possible"
    for name in ("candidate", "fallback", "recognize", "fill", "execute", "generate", "clear", "pending", "intent"):
        assert calls[name] == [], name


# R1, R2, R3, R4 plus image-candidate guardrails with both kinds of pending.
POSSIBLE_ROUTING_CASES = [
    pytest.param(POSSIBLE, "route", id="R1-route-pending"),
    pytest.param(POSSIBLE, None, id="R2-no-pending"),
    pytest.param(SEARCH_POSSIBLE, None, id="R3-search-prefix"),
    pytest.param(POSSIBLE, "generate_image", id="R4-image-pending"),
    pytest.param(IMAGE_CANDIDATE_POSSIBLE, "route", id="image-candidate-route-pending"),
    pytest.param(IMAGE_CANDIDATE_POSSIBLE, "generate_image", id="image-candidate-image-pending"),
]


@pytest.mark.parametrize("message,pending_intent", POSSIBLE_ROUTING_CASES)
def test_possible_turn_bypasses_candidates_pending_and_tools(
    client, dev_headers, monkeypatch, message, pending_intent,
):
    from intent_router import get_pending, set_pending

    assert safety.assess_crisis(message) == "possible"
    assert safety.is_informational_crisis_context(message) is False
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    key = (user, conversation)
    pending = None
    if pending_intent:
        pending = {"intent": pending_intent, "params": {}, "missing": [
            "prompt" if pending_intent == "generate_image" else "origin",
        ]}
        set_pending(key, pending)
    before = _balance(user)
    calls = _routing_spies(monkeypatch)
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))

    _assert_possible_reply(events, calls)
    assert calls["detect"] == [message]
    assert calls["normal"] == [message]
    assert calls["model"] == [700]
    assert calls["mirror"] == calls["image"] == calls["vision"] == []
    assert get_pending(key) == pending
    assert _balance(user) == before - 10


@pytest.mark.parametrize("path,pending_intent,trigger", [
    ("mirror", "route", "auto"),
    ("mirror", "generate_image", "auto"),
    ("mirror", "route", "manual"),
    ("mirror", "generate_image", "manual"),
    ("image", "generate_image", "auto"),
])
def test_possible_turn_preserves_mode_and_vision_paths(
    client, dev_headers, monkeypatch, path, pending_intent, trigger,
):
    from intent_router import get_pending, set_pending
    from mode_switcher import set_user_mode

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    key = (user, conversation)
    pending = {"intent": pending_intent, "params": {}, "missing": [
        "prompt" if pending_intent == "generate_image" else "origin",
    ]}
    set_pending(key, pending)
    if path == "mirror":
        set_user_mode(key, "mirror", trigger)
    before = _balance(user)
    calls = _routing_spies(monkeypatch, mode="mirror" if path == "mirror" else "friend")
    headers = _production_headers(monkeypatch, user)
    payload = {"conversation_id": conversation, "message": POSSIBLE}
    if path == "image":
        payload["image_base64"] = IMAGE

    events = _events(client.post("/chat", headers=headers, json=payload))

    _assert_possible_reply(events, calls)
    assert calls["detect"] == [POSSIBLE]
    assert calls[path] == [POSSIBLE]
    assert calls["normal"] == []
    assert calls["model"] == ([80] if path == "mirror" else [])
    assert calls["vision"] == ([400] if path == "image" else [])
    assert get_pending(key) == pending
    assert _balance(user) == before - 10


def test_none_turn_keeps_intent_and_tool_route_R6(client, dev_headers, monkeypatch):
    message = "帮我查下明天天气"
    assert safety.assess_crisis(message) is None
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = _routing_spies(monkeypatch)
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))

    assert calls["recognize"] == [message]
    assert len(calls["fallback"]) == 1
    assert calls["execute"] == [("web_search", {"query": message})]
    assert calls["intent"] == [message]
    assert calls["normal"] == calls["model"] == []
    assert any(event.get("card", {}).get("points") == ["模拟工具结果"] for event in events)
    assert not any(safety.CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert events[-1] == {"done": True}
    assert calls["trace"][0]["crisis"] is None
    assert _balance(user) == before - 10


def test_possible_image_edit_selection_keeps_fixed_guidance(client, dev_headers, monkeypatch):
    message = "把这张图片换成黑白，活着没意思"
    assert safety.assess_crisis(message) == "possible"
    conversation = _conversation(client, dev_headers)
    calls = _routing_spies(monkeypatch)

    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": message,
    }))

    assert events[0] == {"text": "请先点击要修改的图片上的「以此图修改」，再输入修改要求。我会参考你选中的那张图生成新版本，并保留原图。"}
    assert events[-2:] == [{"text": "\n\n" + safety.CRISIS_RESOURCE_NOTE}, {"done": True}]
    assert calls["candidate"] == calls["fallback"] == calls["recognize"] == []
    assert calls["execute"] == calls["generate"] == calls["model"] == []
    assert calls["trace"][0]["crisis"] == "possible"


# R5 and explicit image/image_edit modes retain the existing integration tests:
# test_beta_safety.py::test_possible_crisis_keeps_tool_routing_billing_resources_and_trace
# test_crisis_resource_paths.py::test_high_image_modes_use_support_reply_while_possible_uses_generation
