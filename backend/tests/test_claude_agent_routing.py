"""Offline rollout, legacy route and deferred image delivery contracts."""
import asyncio
import json
import socket
import pytest
from _fakes import FakeStream

@pytest.fixture(scope="module", autouse=True)
def offline_module():
    patch = pytest.MonkeyPatch()
    def blocked(*args, **kwargs):
        raise AssertionError("Claude agent tests forbid network and DNS")
    original, original_ex = socket.socket.connect, socket.socket.connect_ex
    patch.setattr(socket.socket, "connect", lambda s, a: blocked() if s.family in (socket.AF_INET, socket.AF_INET6) else original(s, a))
    patch.setattr(socket.socket, "connect_ex", lambda s, a: blocked() if s.family in (socket.AF_INET, socket.AF_INET6) else original_ex(s, a))
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, blocked)
    yield
    patch.undo()

@pytest.fixture(autouse=True)
def rollout(monkeypatch):
    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "1")
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "0")
    monkeypatch.setenv("DEV_MODE", "0")

def context(**kwargs):
    import services.chat_service as chat
    values = dict(user="agent_offline", message="今天挺轻松", has_image=False, image_base64=None,
        user_content="今天挺轻松", history=[], message_count=1, system_prompt="人设",
        messages=[{"role": "user", "content": "今天挺轻松"}], conversation_id="test-conversation",
        byok_config={"enabled": True, "provider": "anthropic", "model": "claude-haiku-5-5", "api_key": "offline"})
    values.update(kwargs)
    return chat.ChatContext(**values)

def parse(events):
    return [json.loads(e[6:]) for e in events if e.startswith("data: ")]

@pytest.mark.parametrize("changes,crisis,enabled", [
    ({}, None, True), ({"request_mode": "image"}, None, False),
    ({"request_mode": "image_edit"}, None, False), ({}, "high", False), ({}, "possible", False),
    ({"byok_config": None}, None, False),
    ({"byok_config": {"enabled": False, "provider": "anthropic"}}, None, False),
    ({"byok_config": {"enabled": True, "provider": "deepseek"}}, None, False),
    ({"byok_error": ValueError("offline")}, None, False), ({"byok_unreserved": True}, None, False),
    ({"has_image": True}, None, True),
])
def test_each_enable_condition(changes, crisis, enabled):
    import services.chat_service as chat
    assert chat._claude_agent_enabled(context(**changes), chat.ChatState(trace={}, crisis_level=crisis)) is enabled

def test_switch_default_zero_and_warn_once(monkeypatch, caplog):
    import services.chat_service as chat
    state = chat.ChatState(trace={})
    monkeypatch.delenv("FIONA_CLAUDE_AGENT")
    assert chat._claude_agent_enabled(context(), state)
    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "0")
    assert not chat._claude_agent_enabled(context(), state)
    monkeypatch.setattr(chat, "_CLAUDE_AGENT_ENV_WARNED", False, raising=False)
    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "invalid")
    assert chat._claude_agent_enabled(context(), state)
    assert chat._claude_agent_enabled(context(), state)
    assert sum("FIONA_CLAUDE_AGENT" in r.message for r in caplog.records) == 1

def isolate(monkeypatch):
    import services.chat_service as chat
    saved, traces, refunded = [], [], []
    async def save(ctx, state, image_path=None):
        saved.append((state.full_response, image_path))
        state.response_saved = True
    async def log(*args, **kwargs):
        traces.append(kwargs["payload"].copy())
    async def refund(*args):
        refunded.append(args)
    async def noop(*args, **kwargs):
        pass
    monkeypatch.setattr(chat, "_save_response", save)
    monkeypatch.setattr(chat, "log_event", log)
    monkeypatch.setattr(chat, "refund_strawberries", refund)
    monkeypatch.setattr(chat, "_normal_followups", noop)
    monkeypatch.setattr(chat, "_ensure_active_conversation", noop)
    monkeypatch.setattr(chat, "clear_pending", lambda *args: None)
    monkeypatch.setattr(chat, "get_pending", lambda *args: None)
    monkeypatch.setattr(chat, "get_user_mode", lambda *args: {})
    monkeypatch.setattr(chat, "detect_mode", lambda *args: "friend")
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *args: {"intent": None, "params": {}, "missing": []})
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda *args, **kwargs: None)
    return chat, saved, traces, refunded

async def collect(iterator):
    return [event async for event in iterator]

def test_enabled_dispatch_precedes_image_tool(monkeypatch):
    chat, saved, traces, refunded = isolate(monkeypatch)
    called = []
    async def agent(ctx, state):
        called.append(ctx.has_image)
        yield chat._sse({"text": "智能体"})
    monkeypatch.setattr(chat, "stream_claude_agent", agent, raising=False)
    monkeypatch.setattr(chat, "_image_tool_enabled", lambda *args: pytest.fail("legacy image switch"))
    assert parse(asyncio.run(collect(chat.run_chat(context(), crisis=False)))) == [{"text": "智能体"}]
    assert called == [False]

@pytest.mark.parametrize("mode", ["friend", "mirror"])
def test_disabled_legacy_event_sequences(monkeypatch, mode):
    chat, saved, traces, refunded = isolate(monkeypatch)
    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "0")
    monkeypatch.setattr(chat, "detect_mode", lambda *args: mode)
    class Reply(FakeStream):
        refused = False
        stop_reason = "end_turn"
        def close(self):
            pass
    monkeypatch.setattr(chat, "open_reply_stream", lambda *args, **kwargs: Reply())
    actual = parse(asyncio.run(collect(chat.run_chat(context(), reserved=True, crisis=False))))
    assert actual == [{"reply_model": {"source": "byok", "label": "Claude · claude-haiku-5-5"}},
        {"text": "测试"}, {"text": "回复"}, {"done": True}]
    assert saved == [("测试回复", None)] and len(refunded) == 1 and "agent" not in traces[0]

def test_image_adapter_defers_save_and_preserves_prior_content(monkeypatch, tmp_path):
    chat, saved, traces, refunded = isolate(monkeypatch)
    monkeypatch.setattr(chat, "image_model_available", lambda model: True)
    image = tmp_path / "generated.png"
    image.write_bytes(b"offline")
    async def generate(*args, **kwargs):
        return {"image_path": str(image), "model": "seedream-5.0-flash"}
    monkeypatch.setattr(chat, "generate_image", generate)
    state = chat.ChatState(trace={}, full_response="先看天气。［卡片：晴］", billable=True)
    result = {}
    events = parse(asyncio.run(collect(chat._stream_image_execution(context(), state, "一只猫",
        source="tool", lead_text="", aspect_ratio="1:1", agent_result=result))))
    assert saved == [] and not state.response_saved and state.billable
    assert state.full_response == "先看天气。［卡片：晴］\n\n图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：一只猫"
    assert not any(event.get("done") for event in events)
    assert result["success"] and result["image_path"] == str(image)
    assert result["aspect_ratio"] == "1:1" and result["model"] == "seedream-5.0-flash"
    assert image.exists()

def test_image_adapter_failure_keeps_successful_billing(monkeypatch):
    chat, saved, traces, refunded = isolate(monkeypatch)
    monkeypatch.setattr(chat, "image_model_available", lambda model: True)
    async def generate(*args, **kwargs):
        raise chat.ImageGenerationError("失败")
    monkeypatch.setattr(chat, "generate_image", generate)
    state = chat.ChatState(trace={}, full_response="［卡片：晴］", billable=True)
    result = {}
    events = parse(asyncio.run(collect(chat._stream_image_execution(context(), state, "猫", source="tool", agent_result=result))))
    assert state.billable and state.full_response == "［卡片：晴］" and saved == []
    assert result["error"] == "失败" and not result.get("success") and events[-1] == {"error": "失败"}
