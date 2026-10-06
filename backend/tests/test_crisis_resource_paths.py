"""A crisis resource reaches the client once on every server-controlled chat exit."""

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from _fakes import FakeStream
from safety import CRISIS_RESOURCE_NOTE, assess_crisis


HIGH = "我想死"
POSSIBLE = "活着没意思"
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)
IMAGE = f"data:image/png;base64,{PNG}"
REFERENCE = "/uploads/reference_" + "a" * 32 + ".png"


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from rate_limit import limiter
    import services.chat_service as chat

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _assert_resource_once(events, level, *, error=False):
    assert sum(event.get("text", "").count(CRISIS_RESOURCE_NOTE) for event in events) == 1
    assert [event for event in events if event.get("crisis") is True] == (
        [{"crisis": True}] if level == "high" else []
    )
    if level == "high":
        assert events[0] == {"crisis": True}
    if error:
        resource_index = next(i for i, event in enumerate(events) if CRISIS_RESOURCE_NOTE in event.get("text", ""))
        error_index = next(i for i, event in enumerate(events) if "error" in event)
        assert resource_index < error_index


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


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("outcome", ["text", "provider_error", "empty"])
def test_crisis_normal_reply_provider_error_and_empty_refund(
    client, dev_headers, monkeypatch, message, level, outcome,
):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    if outcome == "provider_error":
        def fail(*args, **kwargs):
            raise RuntimeError("fake provider failure")
        monkeypatch.setattr(chat, "_create_stream_with_fallback", fail)
    elif outcome == "empty":
        monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **k: (FakeStream([]), False))
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))
    _assert_resource_once(events, level, error=outcome == "provider_error")
    assert _balance(user) == before - (10 if outcome == "text" else 0)
    if outcome == "provider_error":
        assert events[-1].get("error")
    else:
        assert events[-1] == {"done": True}


@pytest.mark.parametrize("message,level", [
    (HIGH, "high"), (POSSIBLE, "possible"), ("晚安，永别了", "possible"),
])
def test_crisis_zero_balance_never_calls_model(client, dev_headers, monkeypatch, message, level):
    import database
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE users SET strawberry_balance = 0 WHERE username = ?", (user,))
    calls = []
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **k: calls.append(1))
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))
    _assert_resource_once(events, level, error=level == "possible")
    assert calls == []
    assert _balance(user) == 0
    assert asyncio.run(database.get_messages(user, conversation_id=conversation)) == []
    if level == "high":
        assert events[-1] == {"done": True}
    else:
        assert "草莓不足" in events[-1]["error"] or "草莓用完" in events[-1]["error"]


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("failure", ["not_found", "http_error", "runtime_error", "reservation_error"])
def test_crisis_precheck_failures_refund_and_stream_resources(
    client, dev_headers, monkeypatch, message, level, failure,
):
    import routers.chat as router
    from agent_store import ResourceNotFound
    from fastapi import HTTPException

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)

    async def fail(*args, **kwargs):
        if failure == "not_found":
            raise ResourceNotFound()
        if failure == "http_error":
            raise HTTPException(status_code=409, detail="会话已失效")
        raise RuntimeError("fake precheck failure")

    monkeypatch.setattr(router, "reserve_strawberries" if failure == "reservation_error" else "build_context", fail)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))
    _assert_resource_once(events, level, error=True)
    assert _balance(user) == before
    assert events[-1]["error"]


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("invalid", [
    {"mode": "image_edit"},
    {"mode": "image_edit", "reference_image_path": REFERENCE, "image_base64": IMAGE},
    {"mode": "chat", "reference_image_path": REFERENCE},
    {"mode": "image", "image_base64": IMAGE},
    {"reference_image_path": REFERENCE, "reference_image_paths": [REFERENCE]},
    {"reference_image_paths": [REFERENCE, REFERENCE]},
])
def test_crisis_request_validation_still_streams_resources(
    client, dev_headers, monkeypatch, message, level, invalid,
):
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message, **invalid,
    }))
    _assert_resource_once(events, level, error=True)
    assert _balance(user) == before


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("outcome", ["text", "provider_error", "empty"])
def test_crisis_vision_reply_paths(client, dev_headers, monkeypatch, message, level, outcome):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)

    def create(**kwargs):
        if outcome == "provider_error":
            raise RuntimeError("fake visual provider failure")
        return FakeStream([] if outcome == "empty" else None)

    monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message, "image_base64": IMAGE,
    }))
    _assert_resource_once(events, level, error=outcome == "provider_error")
    assert _balance(user) == before - (10 if outcome == "text" else 0)


@pytest.mark.parametrize("mode", ["image", "image_edit"])
@pytest.mark.parametrize("outcome", ["success", "provider_error", "busy"])
def test_possible_crisis_image_generation_and_edit_paths(
    client, dev_headers, monkeypatch, mode, outcome,
):
    import services.chat_service as chat
    from utils import media

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = []
    image_path = Path(media.UPLOADS_DIR) / ("generated_" + "b" * 32 + ".png")

    async def generate(*args):
        calls.append(args)
        if outcome == "provider_error":
            raise chat.ImageGenerationError("fake image failure")
        image_path.write_bytes(b"isolated-test-image")
        return {"image_path": "/uploads/" + image_path.name, "model": "fake-image-model"}

    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat, "edit_image", generate)
    if outcome == "busy":
        chat._IMAGE_GENERATION_USERS.add(user)
    headers = _production_headers(monkeypatch, user)
    payload = {"conversation_id": conversation, "message": POSSIBLE, "mode": mode}
    if mode == "image_edit":
        payload["reference_images"] = [{"image_base64": IMAGE}]

    events = _events(client.post("/chat", headers=headers, json=payload))
    _assert_resource_once(events, "possible", error=outcome != "success")
    assert _balance(user) == before - (10 if outcome == "success" else 0)
    if outcome == "success":
        assert len(calls) == 1
        assert any("generated_image" in event for event in events)
        assert events[-1] == {"done": True}
    else:
        assert calls == [] if outcome == "busy" else len(calls) == 1
        assert events[-1].get("error")


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("mode", ["image", "image_edit"])
def test_high_image_modes_use_support_reply_while_possible_uses_generation(
    client, dev_headers, monkeypatch, message, level, mode,
):
    import services.chat_service as chat
    from utils import media

    conversation = _conversation(client, dev_headers)
    calls = []

    async def generate(*args):
        calls.append(args)
        path = Path(media.UPLOADS_DIR) / ("generated_" + "c" * 32 + ".png")
        path.write_bytes(b"isolated-test-image")
        return {"image_path": "/uploads/" + path.name, "model": "fake-image-model"}

    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat, "edit_image", generate)
    payload = {"conversation_id": conversation, "message": message, "mode": mode}
    if mode == "image_edit":
        payload["reference_images"] = [{"image_base64": IMAGE}]
    events = _events(client.post("/chat", headers=dev_headers, json=payload))
    _assert_resource_once(events, level)
    assert len(calls) == (0 if level == "high" else 1)
    if level == "high":
        assert not any("generated_image" in event for event in events)


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("path", ["tool", "pending", "mirror"])
def test_crisis_tool_pending_and_mirror_paths(client, dev_headers, monkeypatch, message, level, path):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending

    user = dev_headers["X-Dev-User"]
    conversation = _conversation(client, dev_headers)
    before = _balance(user)
    mode_calls, model_calls, intent_calls, tool_calls, fill_calls = [], [], [], [], []

    def detect(*args, **kwargs):
        mode_calls.append(1)
        return "mirror" if path == "mirror" else "friend"

    def model(*args, **kwargs):
        model_calls.append(kwargs["max_tokens"])
        return FakeStream(), False

    def recognize(*args, **kwargs):
        intent_calls.append(1)
        return {"intent": "get_datetime", "params": {}, "missing": []}

    def execute(*args):
        tool_calls.append(args)
        return "现在是下午三点"

    def fill(pending, current_message):
        fill_calls.append(current_message)
        return pending

    monkeypatch.setattr(chat, "detect_mode", detect)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", model)
    monkeypatch.setattr(chat, "recognize_intent", recognize)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "fill_param", fill)
    if path == "pending":
        set_pending((user, conversation), {"intent": "route", "params": {}, "missing": ["origin"]})
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))
    _assert_resource_once(events, level)
    assert events[-1] == {"done": True}
    assert _balance(user) == before - 10
    if level == "high":
        assert mode_calls == intent_calls == tool_calls == fill_calls == []
        assert model_calls == [700]
        if path == "pending":
            assert get_pending((user, conversation))["intent"] == "route"
    elif path == "tool":
        assert mode_calls == [1]
        assert intent_calls == tool_calls == fill_calls == []
        assert model_calls == [700]
    elif path == "pending":
        assert mode_calls == [1]
        assert intent_calls == tool_calls == fill_calls == []
        assert model_calls == [700]
        assert get_pending((user, conversation)) == {"intent": "route", "params": {}, "missing": ["origin"]}
    else:
        assert mode_calls == [1]
        assert model_calls == [80]
        assert intent_calls == tool_calls == fill_calls == []


@pytest.mark.parametrize("message,level", [(HIGH, "high"), (POSSIBLE, "possible")])
@pytest.mark.parametrize("failure", ["deleted_conversation", "unexpected_error"])
def test_crisis_run_chat_failure_refunds_and_streams_resources(
    client, dev_headers, monkeypatch, message, level, failure,
):
    import services.chat_service as chat
    from agent_store import ResourceNotFound

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    if failure == "deleted_conversation":
        async def missing(*args):
            raise ResourceNotFound()
        monkeypatch.setattr(chat, "_ensure_active_conversation", missing)
    else:
        def fail(*args, **kwargs):
            raise RuntimeError("fake routing failure")
        monkeypatch.setattr(chat, "_final_system_prompt" if level == "high" else "detect_mode", fail)
    headers = _production_headers(monkeypatch, user)

    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))
    _assert_resource_once(events, level, error=True)
    assert _balance(user) == before


def test_crisis_classification_used_by_test_corpus():
    assert assess_crisis(HIGH) == "high"
    assert assess_crisis(POSSIBLE) == "possible"
