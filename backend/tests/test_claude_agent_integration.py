"""Real offline SDK SSE through routing, tools, accounting and single persistence."""
import asyncio
import json
import socket
import base64
from io import BytesIO
from copy import deepcopy
from types import SimpleNamespace as NS

import httpx2
import pytest
from PIL import Image
from test_claude_agent_client import sse
from test_claude_agent_routing import context

@pytest.fixture(scope="module", autouse=True)
def block_network():
    patch = pytest.MonkeyPatch()
    def blocked(*args, **kwargs):
        raise AssertionError("Offline integration forbids TCP and DNS")
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        patch.setattr(socket, name, blocked)
    original, original_ex = socket.socket.connect, socket.socket.connect_ex
    patch.setattr(socket.socket, "connect", lambda s, a: blocked() if s.family in (socket.AF_INET, socket.AF_INET6) else original(s, a))
    patch.setattr(socket.socket, "connect_ex", lambda s, a: blocked() if s.family in (socket.AF_INET, socket.AF_INET6) else original_ex(s, a))
    yield
    patch.undo()

@pytest.fixture
def lifecycle(monkeypatch, tmp_path):
    from byok import client as sdk_client
    import services.chat_service as chat
    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "1")
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(sdk_client, "ensure_available", lambda: None)
    monkeypatch.setattr(chat, "_BYOK_USERS", set())
    results, requests, saves, refunds, traces, summaries, caps = [], [], [], [], [], [], []
    original = sdk_client.anthropic.Anthropic
    def handler(request):
        requests.append(json.loads(request.content))
        reply = results.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=reply)
    def constructor(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
        return original(**kwargs)
    async def save(ctx, state, image_path=None):
        saves.append((state.full_response, image_path))
        state.response_saved = True
    async def refund(*args):
        refunds.append(args)
    async def log(*args, **kwargs):
        traces.append(deepcopy(kwargs["payload"]))
    async def summary(*args):
        summaries.append(args)
    async def noop(*args, **kwargs):
        pass
    monkeypatch.setattr(sdk_client.anthropic, "Anthropic", constructor)
    monkeypatch.setattr(chat, "_save_response", save)
    monkeypatch.setattr(chat, "refund_strawberries", refund)
    monkeypatch.setattr(chat, "log_event", log)
    monkeypatch.setattr(chat, "set_message_image_summary", summary)
    monkeypatch.setattr(chat, "_normal_followups", noop)
    monkeypatch.setattr(chat, "_ensure_active_conversation", noop)
    monkeypatch.setattr(chat, "clear_pending", lambda *args: None)
    monkeypatch.setattr(chat, "get_pending", lambda *args: None)
    monkeypatch.setattr(chat, "set_pending", lambda *args, **kwargs: pytest.fail("agent must not write pending"))
    monkeypatch.setattr(chat, "detect_mode", lambda *args: "friend")
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda name, user, hit: caps.append((name, hit)) or None)
    def forbidden(*args, **kwargs):
        pytest.fail("Agent must bypass platform intent and vision")
    for name in ("recognize_intent_with_fallback", "explicit_image_intent", "image_planner_prescreen"):
        monkeypatch.setattr(chat, name, forbidden)
    monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", forbidden)
    return NS(chat=chat, results=results, requests=requests, saves=saves, refunds=refunds,
        traces=traces, summaries=summaries, caps=caps, patch=monkeypatch, tmp=tmp_path)

def tool(name, identity, **kwargs):
    return {"type": "tool_use", "id": identity, "name": name, "input": kwargs}

def collect(h, ctx):
    async def run():
        return [json.loads(event[6:]) for event in [e async for e in h.chat.run_chat(ctx, reserved=True, crisis=False)] if event.startswith("data: ")]
    return asyncio.run(run())

@pytest.mark.parametrize("fail_after_image", [False, True])
def test_real_sdk_weather_image_feedback_and_settlement(lifecycle, fail_after_image):
    h = lifecycle
    ctx = context(message="北京天气，画一只猫", user_content="北京天气，画一只猫",
        messages=[{"role": "user", "content": "北京天气，画一只猫"}])
    card = {"type": "card", "subtype": "weather", "source": "北京", "error": False, "stale": False,
        "weather": {"location": "北京", "forecast": [{"date": "2026-10-10", "dayWeather": "晴", "low": 12, "high": 24, "dayWind": "北风"}]}}
    def execute(name, params):
        assert h.chat._BYOK_ACTIVE == 0 and ctx.user in h.chat._BYOK_USERS
        assert name == "weather" and params == {"city": "北京"}
        return card
    h.patch.setattr(h.chat, "execute_intent", execute)
    image_path = h.tmp / "cat.png"
    image_path.write_bytes(b"offline")
    async def generate(*args, **kwargs):
        assert h.chat._BYOK_ACTIVE == 0 and ctx.user in h.chat._BYOK_USERS
        return {"image_path": str(image_path), "model": "seedream-5.0-flash"}
    h.patch.setattr(h.chat, "generate_image", generate)
    h.patch.setattr(h.chat, "image_model_available", lambda model: True)
    h.results.extend([
        sse([{"type": "text", "text": "先查天气。"}, tool("get_weather", "weather-1", city="北京")], "tool_use"),
        sse([{"type": "text", "text": "再画猫。"}, tool("generate_image", "image-1", prompt="一只猫", aspect_ratio="1:1")], "tool_use"),
        httpx2.ReadTimeout("offline timeout") if fail_after_image else sse([{"type": "text", "text": "都完成了。"}]),
    ])
    events = collect(h, ctx)
    assert len(h.requests) == 3, (events, h.traces)
    assert h.caps == [("byok_chat", True), ("weather", True)]
    assert sum("reply_model" in event for event in events) == 1
    assert [e["card"] for e in events if "card" in e] == [card]
    assert all(e["append"] is True for e in events if "card" in e)
    assert sum("generated_image" in e for e in events) == 1
    assert len(h.saves) == 1 and h.saves[0][1] == str(image_path)
    text = h.saves[0][0]
    expected = "先查天气。［卡片：" + h.chat._summarize_card_for_history(card) + "］\n\n再画猫。\n\n图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：一只猫"
    assert text == expected + ("" if fail_after_image else "\n\n都完成了。")
    assert h.refunds == [] and image_path.exists()
    assert h.requests[1]["messages"][-1]["content"][0]["tool_use_id"] == "weather-1"
    assert "图片已生成并展示给主人" in h.requests[2]["messages"][-1]["content"][0]["content"]
    assert h.traces[0]["agent_tools"] == ["get_weather", "generate_image"]
    assert h.traces[0]["agent_rounds"] == 3
    assert events[-1].get("error") if fail_after_image else events[-1] == {"done": True}
    assert h.chat._BYOK_USERS == set() and h.chat._BYOK_ACTIVE == 0

def test_real_sdk_vision_and_web_sources_are_free(lifecycle):
    h = lifecycle
    h.patch.setattr(h.chat, "detect_mode", lambda *args: pytest.fail("image must skip detect_mode"))
    image = BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    image_base64 = base64.b64encode(image.getvalue()).decode("ascii")
    ctx = context(message="", user_content="[发了一张图片]", has_image=True,
        image_base64="data:image/png;base64," + image_base64, uploaded_image_path="input.png",
        messages=[{"role": "user", "content": "[发了一张图片]"}])
    h.results.append(sse([
        {"type": "server_tool_use", "id": "search-1", "name": "web_search", "input": {"query": "private-query"}},
        {"type": "web_search_tool_result", "tool_use_id": "search-1", "content": [
            {"type": "web_search_result", "url": "https://example.com/article", "title": "来源", "encrypted_content": "opaque", "page_age": None}]},
        {"type": "text", "text": "图片里有猫，正文 https://example.com/body 。"},
    ], server_usage={"web_search_requests": 1, "web_fetch_requests": 0}))
    events = collect(h, ctx)
    assert h.requests, (events, h.traces)
    assert [b["type"] for b in h.requests[0]["messages"][-1]["content"]] == ["text", "image", "text"]
    assert h.requests[0]["messages"][-1]["content"][1]["source"]["data"] == image_base64
    sources = [e["card"] for e in events if "card" in e]
    assert len(sources) == 1 and sources[0]["subtype"] == "web_sources"
    assert sources[0]["sources"] == [{"title": "来源", "url": "https://example.com/article", "site_name": "example.com"}]
    assert len(h.refunds) == 1 and len(h.saves) == 1 and len(h.summaries) == 1
    assert h.traces[0]["web_search_requests"] == 1 and h.traces[0]["web_fetch_requests"] == 0
    assert "private-query" not in json.dumps(h.traces)
