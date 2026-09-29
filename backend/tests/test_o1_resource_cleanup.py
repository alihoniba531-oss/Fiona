"""A failed stale-conversation cleanup must not hide crisis SSE events."""

import asyncio
import json
import sqlite3

import pytest

from safety import CRISIS_RESOURCE_NOTE


@pytest.mark.parametrize("message,level", [
    ("活着没意思", "possible"),
    ("我想死", "high"),
])
def test_deleted_conversation_cleanup_failure_keeps_crisis_resource_and_error(
    monkeypatch, message, level,
):
    import mode_switcher
    import services.chat_service as chat

    clear_pending_calls = []
    clear_mode_calls = []
    traces = []

    async def missing_conversation(_ctx):
        raise chat.ResourceNotFound()

    async def record_trace(_user, _event, *, payload, success):
        traces.append((payload.copy(), success))

    def locked_pending(state_key):
        clear_pending_calls.append(state_key)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(chat, "_ensure_active_conversation", missing_conversation)
    monkeypatch.setattr(chat, "get_pending", lambda _state_key: None)
    monkeypatch.setattr(chat, "detect_mode", lambda *_args: "friend")
    monkeypatch.setattr(chat, "clear_pending", locked_pending)
    monkeypatch.setattr(mode_switcher, "clear_user_mode", clear_mode_calls.append)
    monkeypatch.setattr(chat, "log_event", record_trace)

    ctx = chat.ChatContext(
        user="isolated-user",
        message=message,
        has_image=False,
        image_base64=None,
        user_content=message,
        history=[],
        message_count=1,
        system_prompt="system",
        messages=[{"role": "user", "content": message}],
        conversation_id="deleted-conversation",
    )

    async def collect():
        return [json.loads(event[6:]) async for event in chat.run_chat(ctx)]

    events = asyncio.run(collect())
    resource_events = [
        (index, event) for index, event in enumerate(events)
        if CRISIS_RESOURCE_NOTE in event.get("text", "")
    ]
    assert len(resource_events) == 1
    assert events[resource_events[0][0] + 1] == {"error": "会话已删除或不可用"}
    assert events[-1] == {"error": "会话已删除或不可用"}
    assert events == ([{"crisis": True}] if level == "high" else []) + [
        resource_events[0][1], {"error": "会话已删除或不可用"},
    ]
    assert clear_pending_calls == ([] if level == "high" else [ctx.state_key])
    assert clear_mode_calls == ([] if level == "high" else [ctx.state_key])
    assert traces[0][0]["error"] == "ResourceNotFound"
    assert traces[0][1] is False


def test_deleted_conversation_error_disconnect_still_cleans_pending_and_mode(monkeypatch):
    import mode_switcher
    import services.chat_service as chat

    cleanup = []

    async def missing_conversation(_ctx):
        raise chat.ResourceNotFound()

    async def record_trace(_user, _event, *, payload, success):
        cleanup.append(("trace", payload["error"], success))

    monkeypatch.setattr(chat, "_ensure_active_conversation", missing_conversation)
    monkeypatch.setattr(chat, "get_pending", lambda _state_key: None)
    monkeypatch.setattr(chat, "detect_mode", lambda *_args: "friend")
    monkeypatch.setattr(chat, "clear_pending", lambda key: cleanup.append(("pending", key)))
    monkeypatch.setattr(mode_switcher, "clear_user_mode", lambda key: cleanup.append(("mode", key)))
    monkeypatch.setattr(chat, "log_event", record_trace)

    ctx = chat.ChatContext(
        user="isolated-user",
        message="活着没意思",
        has_image=False,
        image_base64=None,
        user_content="活着没意思",
        history=[],
        message_count=1,
        system_prompt="system",
        messages=[{"role": "user", "content": "活着没意思"}],
        conversation_id="deleted-conversation",
    )

    async def close_after_error():
        stream = chat.run_chat(ctx, crisis="possible")
        events = []
        async for event in stream:
            events.append(json.loads(event[6:]))
            if "error" in events[-1]:
                break
        assert cleanup == []
        await stream.aclose()
        return events

    events = asyncio.run(close_after_error())
    assert len(events) == 2
    assert CRISIS_RESOURCE_NOTE in events[0]["text"]
    assert events[1] == {"error": "会话已删除或不可用"}
    assert cleanup == [
        ("pending", ctx.state_key),
        ("mode", ctx.state_key),
        ("trace", "ResourceNotFound", False),
    ]
