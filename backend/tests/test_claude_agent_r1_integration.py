"""R1 refunds, platform errors and attachment ownership with real offline SDK SSE."""
import asyncio

import pytest

from test_claude_agent_client import sse
from test_claude_agent_integration import block_network, lifecycle, collect, tool
from test_claude_agent_routing import context, parse, isolate


def weather(h):
    h.patch.setattr(h.chat, "execute_intent", lambda *args: {
        "type": "card", "subtype": "weather", "source": "北京", "error": False,
        "weather": {"location": "北京", "forecast": []},
    })
    h.results.extend([
        sse([tool("get_weather", "w", city="北京")], "tool_use"),
        sse([{"type": "text", "text": "天气已查好。"}]),
    ])
    return context(message="北京天气", user_content="北京天气",
                   messages=[{"role": "user", "content": "北京天气"}])


@pytest.mark.parametrize("missing", [False, True])
def test_card_save_failure_refunds_and_uses_platform_error(lifecycle, missing):
    h = lifecycle
    ctx = weather(h)
    async def failed_save(*args, **kwargs):
        if missing:
            raise h.chat.ResourceNotFound("conversation deleted")
        raise RuntimeError("conversation no longer available")
    h.patch.setattr(h.chat, "_save_response", failed_save)
    events = collect(h, ctx)
    assert any("card" in event for event in events)
    assert len(h.refunds) == 1
    assert events[-1] == {"error": "会话已删除或不可用" if missing else "服务暂时不可用，请稍后再试"}
    assert not h.saves


def test_client_disconnect_after_card_refunds_without_save(lifecycle):
    h = lifecycle
    ctx = weather(h)
    async def disconnect():
        stream = h.chat.run_chat(ctx, reserved=True, crisis=False)
        try:
            async for event in stream:
                if any("card" in item for item in parse([event])):
                    break
        finally:
            await stream.aclose()
    asyncio.run(disconnect())
    assert len(h.refunds) == 1 and not h.saves
    assert not h.chat._BYOK_USERS and h.chat._BYOK_ACTIVE == 0


def test_image_save_failure_refunds_and_deletes_attachment(lifecycle):
    h = lifecycle
    import utils.media as media
    h.patch.setattr(media, "UPLOADS_DIR", str(h.tmp))
    image = h.tmp / "generated_r1.png"
    image.write_bytes(b"offline generated attachment")
    async def generate(*args, **kwargs):
        return {"image_path": "/uploads/generated_r1.png", "model": "seedream-5.0-flash"}
    async def failed_save(*args, **kwargs):
        raise RuntimeError("conversation no longer available")
    h.patch.setattr(h.chat, "generate_image", generate)
    h.patch.setattr(h.chat, "image_model_available", lambda *args: True)
    h.patch.setattr(h.chat, "_save_response", failed_save)
    h.results.extend([
        sse([tool("generate_image", "img", prompt="一只猫")], "tool_use"),
        sse([{"type": "text", "text": "图已画好。"}]),
    ])
    events = collect(h, context())
    assert any("generated_image" in event for event in events)
    assert len(h.refunds) == 1 and not image.exists()
    assert events[-1] == {"error": "服务暂时不可用，请稍后再试"}


def test_agent_adapter_success_defers_billing(monkeypatch, tmp_path):
    chat, saves, _, _ = isolate(monkeypatch)
    image = tmp_path / "agent.png"
    image.write_bytes(b"generated")
    async def generate(*args, **kwargs):
        return {"image_path": str(image), "model": "seedream-5.0-flash"}
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat, "image_model_available", lambda *args: True)
    state = chat.ChatState(trace={})
    result = {}
    async def run():
        return [e async for e in chat._stream_image_execution(
            context(), state, "一只猫", source="tool", agent_result=result)]
    asyncio.run(run())
    assert result["success"] and image.exists()
    assert not state.billable and not state.response_saved and not saves


@pytest.mark.parametrize("step", ["get_pending", "clear_pending", "detect_mode", "_ensure_active_conversation"])
def test_pre_request_platform_failures_use_generic_error(lifecycle, step):
    h = lifecycle
    if step == "clear_pending":
        h.patch.setattr(h.chat, "get_pending", lambda *args: {"intent": "weather"})
    if step == "_ensure_active_conversation":
        async def failed(*args, **kwargs):
            raise RuntimeError("platform failure")
    else:
        def failed(*args, **kwargs):
            raise RuntimeError("platform failure")
    h.patch.setattr(h.chat, step, failed)
    events = collect(h, context())
    assert events == [{"error": "服务暂时不可用，请稍后再试"}]
    assert not h.requests and len(h.refunds) == 1


def test_failed_image_is_feedback_and_followups_still_run(lifecycle):
    h = lifecycle
    followups = []
    async def generate(*args, **kwargs):
        raise h.chat.ImageGenerationError("tool failed")
    async def followed(*args, **kwargs):
        followups.append(True)
    h.patch.setattr(h.chat, "generate_image", generate)
    h.patch.setattr(h.chat, "image_model_available", lambda *args: True)
    h.patch.setattr(h.chat, "_normal_followups", followed)
    h.results.extend([
        sse([{"type": "text", "text": "我来画。"}, tool("generate_image", "img", prompt="一只猫")], "tool_use"),
        sse([{"type": "text", "text": "这次没画成功，可以再试。"}]),
    ])
    events = collect(h, context())
    assert {"status": "image_failed", "source": "tool"} in events
    assert not any("error" in event for event in events) and events[-1] == {"done": True}
    assert h.saves == [("我来画。\n\n这次没画成功，可以再试。", None)]
    assert len(h.refunds) == 1 and followups == [True]
    assert h.traces[0]["agent_tool_errors"] == 1 and "error" not in h.traces[0]
