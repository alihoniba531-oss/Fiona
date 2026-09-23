"""Crisis routing and final safety instructions at user-facing model boundaries."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from _fakes import FakeStream
from persona import BASE_SAFETY_RULES, build_system_prompt
from safety import CRISIS_GUIDANCE, CRISIS_RESOURCE_NOTE, detect_crisis


@pytest.mark.parametrize("message", [
    "我只能去死了", "我不想活了", "活着没意思，想自杀", "想结束自己的生命",
    "我想割腕", "想从楼上跳下去", "攒了一瓶安眠药", "我想死",
    "I want to kill myself", "thinking about suicide", "I want to end my life",
    "我想伤害自己", "我在自残", "我想自残", "我只能自残了", "我又割了自己",
    "我要跳河", "我打算今晚了结自己", "我想把自己杀了", "i want to die",
    "i don't want to live anymore", "i want to hurt myself", "i'm going to cut myself",
])
def test_crisis_detector_recognizes_required_phrases(message):
    assert detect_crisis(message)


@pytest.mark.parametrize("message", [
    "笑死我了", "累死了今天", "饿死了", "热死了", "吓死我了", "气死我了",
    "电脑死机了", "代码死循环了", "这个方案必须今天定", "我只能周末去", "死磕这个问题",
    "我想死你了", "宝贝我想死你了", "我要死了，笑死", "累得我要死", "笑得我要死了",
    "困得我要死", "气得我想死", "我快要死了好困", "别让我去死记硬背",
    "我不想活得太累", "suicide squad 好看吗", "跳楼价甩卖", "跳楼机好刺激",
])
def test_crisis_detector_rejects_required_everyday_phrases(message):
    assert not detect_crisis(message)


def test_crisis_detector_normalizes_case_and_whitespace():
    assert detect_crisis("  I  WANT TO  KILL MYSELF  ")
    assert detect_crisis("我 不 想 活 了")
    assert detect_crisis("i dont want to live anymore")
    assert detect_crisis("im going to cut myself")


@pytest.mark.parametrize("message_count", [0, 31, 101])
def test_persona_growth_stages_end_with_one_safety_block(message_count):
    prompt = build_system_prompt("tester", message_count=message_count)
    assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1


def test_custom_persona_ends_with_one_safety_block():
    prompt = build_system_prompt("tester", agent={"display_name": "小草莓"})
    assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1


@pytest.mark.parametrize("kind,summary,turn_count,workflow", [
    ("peer", False, 0, False),
    ("peer", False, 1, False),
    ("peer", True, 2, False),
    ("official", False, 0, False),
    ("official", False, 1, False),
    ("official", True, 2, False),
    ("official", False, 0, True),  # writer draft
    ("official", False, 1, True),  # independent review
    ("official", False, 2, True),  # writer revision
])
def test_exchange_every_system_path_ends_with_safety(kind, summary, turn_count, workflow):
    from exchange_workflow import WORKFLOW_VERSION
    from services.exchange_service import build_exchange_messages

    context = {
        "kind": kind,
        "topic": "一起完成文字方案",
        "turn_count": turn_count,
        "max_turns": 3,
        "initiator": {"id": "person:1", "display_name": "主创"},
        "recipient": {"id": "official:creative-partner" if kind == "official" else "person:2", "display_name": "搭档"},
        "messages": [{"display_name": "主创", "content": "先讨论目标", "stage": "draft"}],
    }
    if workflow:
        context["workflow_version"] = WORKFLOW_VERSION
        context["artifact"] = "# 方案\n\n目标明确。"
    messages = build_exchange_messages(context, summary=summary)
    systems = [entry["content"] for entry in messages if entry["role"] == "system"]
    assert systems
    for prompt in systems:
        assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
        assert prompt.count(BASE_SAFETY_RULES.strip()) == 1


def test_exchange_provider_payment_error_directs_user_to_platform_admin():
    from services.exchange_service import _safe_error

    message = _safe_error(SimpleNamespace(status_code=402))
    assert "请联系平台管理员恢复模型服务" in message
    assert "充值" not in message


@pytest.fixture(autouse=True)
def _isolate_chat_rate_limit(monkeypatch):
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _conversation(client, dev_headers):
    response = client.post("/conversations", json={}, headers=dev_headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["conversation"]["id"]


def _model_spy(monkeypatch, *, fail=False):
    import services.chat_service as chat

    calls = []

    def create(use_qwen, messages, **kwargs):
        calls.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        if fail:
            raise RuntimeError("synthetic provider error")
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", create)
    return calls


def _production_headers(monkeypatch, user):
    from auth import create_token

    monkeypatch.setenv("DEV_MODE", "0")
    return {"Authorization": f"Bearer {create_token(user)}"}


def _balance(user):
    import database

    return asyncio.run(database.get_strawberry_balance(user))


def test_crisis_chat_final_guidance_resource_persistence_and_no_charge(
    client, dev_headers, monkeypatch,
):
    import database

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = _model_spy(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我只能去死了",
    }))
    assert len(calls) == 1
    prompt = calls[0][0]["content"]
    assert prompt.rstrip().endswith(CRISIS_GUIDANCE.strip())
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1
    assert "【⚠️ 即时引导" not in prompt
    assert "【当前状态：陪着】" not in prompt
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert events[-1] == {"done": True}
    assert _balance(user) == before
    history = asyncio.run(database.get_messages(user, conversation_id=conversation))
    assert CRISIS_RESOURCE_NOTE in history[-1]["content"]


def test_crisis_chat_provider_error_still_sends_resources_before_error(
    client, dev_headers, monkeypatch,
):
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = _model_spy(monkeypatch, fail=True)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我不想活了",
    }))
    assert len(calls) == 1
    resource_index = next(i for i, event in enumerate(events) if CRISIS_RESOURCE_NOTE in event.get("text", ""))
    error_index = next(i for i, event in enumerate(events) if event.get("error"))
    assert resource_index < error_index
    assert _balance(user) == before


def test_crisis_chat_bypasses_existing_mirror_mode(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending
    from mode_switcher import MIRROR_PROMPT_APPENDIX, get_user_mode, set_user_mode

    conversation = _conversation(client, dev_headers)
    key = (dev_headers["X-Dev-User"], conversation)
    pending = {"intent": "route", "params": {"destination": "机场"}, "missing": ["origin"]}
    set_pending(key, pending)
    set_user_mode(key, "mirror", "existing mirror state")
    calls = _model_spy(monkeypatch)
    mode_calls = []

    def detect(*args, **kwargs):
        mode_calls.append(True)
        return "mirror"

    monkeypatch.setattr(chat, "detect_mode", detect)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "我想死",
    }))
    assert len(calls) == 1
    assert mode_calls == []
    assert MIRROR_PROMPT_APPENDIX.strip() not in calls[0][0]["content"]
    assert calls[0][0]["content"].rstrip().endswith(CRISIS_GUIDANCE.strip())
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert get_pending(key) == pending
    assert get_user_mode(key)["mode"] == "mirror"


def test_zero_balance_crisis_returns_resources_without_model(
    client, dev_headers, monkeypatch,
):
    import database

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE users SET strawberry_balance = 0 WHERE username = ?", (user,))
    calls = _model_spy(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我不想活了",
    }))
    assert calls == []
    assert events == [{"text": CRISIS_RESOURCE_NOTE}, {"done": True}]
    assert _balance(user) == 0
    history = asyncio.run(database.get_messages(user, conversation_id=conversation))
    assert history == []


_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)


def test_crisis_with_image_uses_vision_branch_and_keeps_final_guidance(
    client, dev_headers, monkeypatch,
):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    text_calls = _model_spy(monkeypatch)
    image_calls = []

    def create(**kwargs):
        image_calls.append(json.loads(json.dumps(kwargs["messages"], ensure_ascii=False)))
        return FakeStream()

    monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "我想死",
        "image_base64": f"data:image/png;base64,{_TINY_PNG}",
    }))
    assert text_calls == []
    assert len(image_calls) == 1
    assert image_calls[0][0]["content"].rstrip().endswith(CRISIS_GUIDANCE.strip())
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)


@pytest.mark.parametrize("branch,message", [
    ("normal", "今天聊聊计划"),
    ("mirror", "今天想安静聊聊"),
    ("hard_word", "我只能周末去"),
    ("image", "这是什么"),
    ("tts", "播报一下"),
    ("tts_mirror", "播报一下"),
    ("tts_image", "播报一下"),
])
def test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block(
    client, dev_headers, monkeypatch, branch, message,
):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    monkeypatch.setattr(chat, "detect_mode", lambda *args, **kwargs: "mirror" if branch in ("mirror", "tts_mirror") else "friend")
    calls = _model_spy(monkeypatch)
    if branch in ("image", "tts_image"):
        def create(**kwargs):
            calls.append(json.loads(json.dumps(kwargs["messages"], ensure_ascii=False)))
            return FakeStream()
        monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        ))
    payload = {"conversation_id": conversation, "message": message}
    if branch in ("image", "tts_image"):
        payload["image_base64"] = f"data:image/png;base64,{_TINY_PNG}"
    events = _events(client.post("/chat", headers=dev_headers, json=payload))
    assert events[-1] == {"done": True}
    assert len(calls) == 1
    prompt = calls[0][0]["content"]
    system_prompts = [entry["content"] for entry in calls[0] if entry["role"] == "system"]
    assert "\n".join(system_prompts).count(BASE_SAFETY_RULES.strip()) == 1
    assert system_prompts[-1].rstrip().endswith(BASE_SAFETY_RULES.strip())
    if branch in ("tts", "tts_mirror", "tts_image"):
        assert "直接开口说话" in system_prompts[-1]
        assert calls[0][-1]["role"] == "system"
        assert calls[0][-2]["role"] == "user"
    else:
        assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
        assert prompt.count(BASE_SAFETY_RULES.strip()) == 1
    if branch == "hard_word":
        assert "【⚠️ 即时引导" in prompt
