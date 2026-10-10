"""Offline agent lifecycle contracts; fixtures never use provider or git history."""
import asyncio
import base64
from copy import deepcopy
from io import BytesIO
import json
import logging
import socket
import threading
from types import SimpleNamespace as NS

import pytest
from PIL import Image


@pytest.fixture(scope="module", autouse=True)
def offline_module():
    """Hard-block TCP and DNS for the complete module, including fixture setup."""
    patch = pytest.MonkeyPatch()
    def blocked(*args, **kwargs):
        raise AssertionError("Claude agent runtime tests forbid connections and DNS")
    patch.setattr(socket.socket, "connect", blocked)
    patch.setattr(socket.socket, "connect_ex", blocked)
    patch.setattr(socket, "create_connection", blocked)
    patch.setattr(socket, "getaddrinfo", blocked)
    patch.setattr(socket, "gethostbyname", blocked)
    patch.setattr(socket, "gethostbyname_ex", blocked)
    yield
    patch.undo()


def message(stop="end_turn", *, content=None, text="", usage=None):
    return NS(stop_reason=stop, content=content or ([{"type": "text", "text": text}] if text else []),
              usage=usage or NS(input_tokens=10, output_tokens=5))


def call(name, arguments=None, identity="tool-1"):
    return {"type": "tool_use", "id": identity, "name": name, "input": arguments or {}}


class FakeStream:
    def __init__(self, final, text="", failure=None):
        self.final_message = final
        self.stop_reason = final.stop_reason
        self.refused = final.stop_reason == "refusal"
        self.failure = failure
        self.closed = False
        self._chunks = iter([NS(choices=[NS(delta=NS(content=text))])] if text else [])
    def __iter__(self):
        return self
    def __next__(self):
        if self.failure:
            raise self.failure
        return next(self._chunks)
    def close(self):
        self.closed = True


@pytest.fixture
def harness(monkeypatch):
    import services.claude_agent as agent
    import services.chat_service as chat
    ctx = chat.ChatContext("agent-user", "查北京天气并画猫", False, None, "查北京天气并画猫", [], 0,
                           "persona", [{"role": "user", "content": "查北京天气并画猫"}],
                           conversation_id="conversation",
                           byok_config={"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "fake"})
    state = chat.ChatState(trace={}, sys_prompt_final="persona")
    streams, requests, executions, caps, saves, followups, clears, summaries, deleted = [], [], [], [], [], [], [], [], []
    def open_stream(config, messages, **kwargs):
        assert ctx.user in chat._BYOK_USERS
        assert chat._BYOK_ACTIVE == 1
        requests.append((deepcopy(messages), kwargs.copy()))
        stream = streams.pop(0)
        if isinstance(stream, Exception):
            raise stream
        return stream
    def execute(name, params):
        assert chat._BYOK_ACTIVE == 0, "Client tools must release the global BYOK slot"
        assert ctx.user in chat._BYOK_USERS, "The user lock must span client tools"
        executions.append((name, params))
        return {"type": "card", "subtype": "weather" if name == "weather" else None,
                "source": "北京" if name == "weather" else name, "error": False, "stale": False,
                "points": ["晴天"], "weather": {"location": "北京", "forecast": [{"day": "10日", "dayWeather": "晴", "low": 12, "high": 24, "dayWind": "北风"}]}}
    async def save(ctx_, state_, image_path=None):
        saves.append((state_.full_response, image_path))
        state_.response_saved = True
    async def follow(*args):
        followups.append(args)
    async def summary(*args):
        summaries.append(args)
    async def active(*args):
        pass
    monkeypatch.setattr(agent, "open_agent_stream", open_stream)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda name, user, hit: caps.append((name, hit)) or None)
    monkeypatch.setattr(chat, "_save_response", save)
    monkeypatch.setattr(chat, "_normal_followups", follow)
    monkeypatch.setattr(chat, "_ensure_active_conversation", active)
    monkeypatch.setattr(chat, "set_message_image_summary", summary)
    monkeypatch.setattr(chat, "delete_uploaded_files", deleted.extend)
    monkeypatch.setattr(chat, "detect_mode", lambda *args: "friend")
    monkeypatch.setattr(chat, "get_pending", lambda *args: {"intent": "weather"})
    monkeypatch.setattr(chat, "clear_pending", lambda key: clears.append(key))
    monkeypatch.setattr(chat, "set_pending", lambda *args, **kwargs: pytest.fail("Claude agent must not write pending"))
    monkeypatch.setattr(chat, "_BYOK_USERS", set())
    return NS(agent=agent, chat=chat, ctx=ctx, state=state, streams=streams, requests=requests,
              executions=executions, caps=caps, saves=saves, followups=followups, clears=clears,
              summaries=summaries, deleted=deleted, monkeypatch=monkeypatch)


def run(h):
    async def collect():
        return [json.loads(event[6:]) if event.startswith("data: ") else event
                async for event in h.agent.stream_claude_agent(h.ctx, h.state)]
    return asyncio.run(collect())


def test_tool_definitions_are_only_allowed_tools(harness):
    tools = harness.agent.CLAUDE_CLIENT_TOOLS
    assert {tool["name"] for tool in tools} == {"get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image"}
    assert all("eager_input_streaming" not in tool for tool in tools)
    hot = next(tool for tool in tools if tool["name"] == "get_hot_topics")
    assert hot["input_schema"]["properties"]["source"]["enum"] == ["微博", "知乎", "抖音", "B站", "头条"]


def test_single_weather_round_persistence_daily_cap_and_privacy(harness, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    h = harness
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})]), "我查一下。"),
                      FakeStream(message(text="今天晴。"), "今天晴。")])
    events = run(h)
    assert h.executions == [("weather", {"city": "北京"})]
    cards = [event for event in events if isinstance(event, dict) and "card" in event]
    assert len(cards) == 1 and cards[0]["append"] is True
    assert h.saves == [("我查一下。［卡片：" + h.chat._summarize_card_for_history(cards[0]["card"]) + "］\n\n今天晴。", None)]
    assert h.state.billable and h.state.response_saved
    assert h.caps == [("byok_chat", True), ("weather", True)]
    assert h.state.trace["agent_rounds"] == 2
    assert h.state.trace["agent_tools"] == ["get_weather"]
    assert h.state.trace["agent_stop"] == "end_turn"
    assert h.state.trace["agent_usage"] == {"input_tokens": 20, "output_tokens": 10}
    assert "北京" not in json.dumps(h.state.trace, ensure_ascii=False) + caplog.text + capsys.readouterr().out
    assert h.clears == [h.ctx.state_key] and len(h.followups) == 1
    assert sum("reply_model" in event for event in events if isinstance(event, dict)) == 1
    assert not h.chat._BYOK_USERS and h.chat._BYOK_ACTIVE == 0
    feedback = h.requests[1][0][-1]
    assert feedback["role"] == "user" and feedback["content"][0]["type"] == "tool_result"
    assert "北风" in feedback["content"][0]["content"]


@pytest.mark.parametrize("current,history,allowed", [
    ("查上海天气", [], True),
    ("查天气", [{"role": "user", "content": "上海"}], True),
    ("查天气", [{"role": "user", "content": "上海"}] + [{"role": "user", "content": "别的"}] * 3, False),
    ("查天气", [{"role": "assistant", "content": "上海"}], False),
    ("查天气", [], False),
])
def test_weather_city_only_current_or_last_three_user_originals(harness, current, history, allowed):
    h = harness
    h.ctx.message = h.ctx.user_content = current
    h.ctx.history = history
    h.ctx.system_prompt = "记忆里的城市上海"
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "上海的天气"})])),
                      FakeStream(message(text="答复"), "答复")])
    run(h)
    assert bool(h.executions) is allowed
    if not allowed:
        assert h.requests[1][0][-1]["content"][0]["content"] == "主人没有说过这个城市，请先问主人想查哪个城市"


def test_image_input_skips_mode_detection_and_saves_120_character_summary(harness):
    h = harness
    h.ctx.has_image = True
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    h.ctx.image_base64 = "data:image/jpeg;base64," + encoded
    h.ctx.uploaded_image_path = "/uploads/input.jpg"
    h.monkeypatch.setattr(h.chat, "detect_mode", lambda *args: pytest.fail("Image turns must not detect mode"))
    h.streams.append(FakeStream(message(text="猫" * 150), "猫" * 150))
    run(h)
    blocks = h.requests[0][0][-1]["content"]
    assert blocks[0]["type"] == "text" and blocks[0]["text"].startswith("（当前北京时间：")
    assert blocks[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded}}
    assert blocks[2] == {"type": "text", "text": h.ctx.user_content}
    assert h.summaries == [(h.ctx.user, h.ctx.conversation_id, h.ctx.uploaded_image_path, "猫" * 120)]
    assert not h.state.billable


def test_mirror_uses_existing_branch_and_never_opens_agent(harness):
    h = harness
    h.monkeypatch.setattr(h.chat, "detect_mode", lambda *args: "mirror")
    async def mirror(*args):
        yield h.chat._sse({"text": "mirror"})
        yield h.chat._sse({"done": True})
    h.monkeypatch.setattr(h.chat, "stream_mirror", mirror)
    assert run(h) == [{"text": "mirror"}, {"done": True}]
    assert not h.requests and h.clears == [h.ctx.state_key]


def test_weather_then_image_then_answer_saves_once(harness):
    h = harness
    image_calls = []
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        assert h.chat._BYOK_ACTIVE == 0 and ctx.user in h.chat._BYOK_USERS
        image_calls.append((prompt, kwargs))
        agent_result.update(success=True, image_path="/uploads/cat.png", model="Seedream 5.0 Flash", aspect_ratio="1:1")
        state.full_response += "图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：猫"
        yield h.chat._sse({"generated_image": {"image_path": "/uploads/cat.png"}})
        yield h.chat._sse({"text": "图片已生成。"})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})]), "天气："),
                      FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"}, "image")]), "接着画。"),
                      FakeStream(message(text="完成。"), "完成。")])
    events = run(h)
    assert len(image_calls) == 1 and h.state.billable
    assert len(h.saves) == 1 and h.saves[0][1] == "/uploads/cat.png"
    assert h.saves[0][0].index("［卡片：") < h.saves[0][0].index("接着画。") < h.saves[0][0].index("图片已生成。") < h.saves[0][0].index("完成。")
    assert sum(event.get("done", False) for event in events if isinstance(event, dict)) == 1
    assert "图片已生成并展示给主人" in h.requests[2][0][-1]["content"][0]["content"]
    assert not h.deleted


def test_second_image_is_never_executed(harness):
    h = harness
    images = []
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        images.append(prompt)
        state.full_response += "图片已生成。"
        agent_result.update(success=True, image_path="/uploads/cat.png", model="model", aspect_ratio="1:1")
        yield h.chat._sse({"generated_image": {"image_path": "/uploads/cat.png"}})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.extend([FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])) for _ in range(2)])
    h.streams.append(FakeStream(message(text="完成"), "完成"))
    run(h)
    assert images == ["猫"]
    assert h.requests[2][0][-1]["content"][0]["content"] == "本轮已生成过一张图，请直接回答；如需更多请让主人再说一次"


def test_tool_cap_grants_exactly_one_final_answer_request(harness):
    h = harness
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_hot_topics", {"source": "微博"}, str(index))])) for index in range(7)])
    run(h)
    assert len(h.executions) == 4 and len(h.requests) == 6
    assert h.requests[5][0][-1]["content"][0]["content"] == "本轮工具调用次数已用完，请直接回答主人"
    assert h.state.trace["agent_stop"] == "tool_limit"
    assert h.caps.count(("byok_chat", True)) == 1


@pytest.mark.parametrize("count,expected", [(1, 2), (3, 3)])
def test_pause_turn_preserves_assistant_and_resumes_at_most_twice(harness, count, expected):
    h = harness
    h.streams.extend([FakeStream(message("pause_turn", content=[{"type": "text", "text": "继续"}]), "继续") for _ in range(count)])
    h.streams.append(FakeStream(message(text="结束"), "结束"))
    run(h)
    assert len(h.requests) == expected
    assert h.requests[1][0][-1] == {"role": "assistant", "content": [{"type": "text", "text": "继续"}]}
    assert h.state.trace["agent_stop"] == ("end_turn" if count == 1 else "pause_limit")


def test_fallback_ignores_old_client_calls_and_trims_assistant_feedback(harness):
    h = harness
    fresh = call("plan_route", {"origin": "甲", "destination": "乙"}, "new")
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"}), {"type": "fallback"}, fresh])),
                      FakeStream(message(text="路线"), "路线")])
    run(h)
    assert h.executions == [("route", {"origin": "甲", "destination": "乙"})]
    assert h.requests[1][0][-2] == {"role": "assistant", "content": [fresh]}


@pytest.mark.parametrize("first_success", [True, False])
def test_successful_card_billing_cannot_be_cleared_by_later_failure(harness, first_success):
    h = harness
    outcomes = iter([first_success, False])
    def tool(*args):
        return {"type": "card", "source": "test", "points": ["结果"], "error": not next(outcomes), "stale": False, "message": "失败"}
    h.monkeypatch.setattr(h.chat, "execute_intent", tool)
    h.streams.extend([FakeStream(message("tool_use", content=[call("plan_travel", {"query": "旅行"})])) for _ in range(2)])
    h.streams.append(FakeStream(message(text="答复"), "答复"))
    run(h)
    assert h.state.billable is first_success
    assert len(h.saves) == 1


def test_search_sources_only_from_verified_result_blocks_dedup_max_five(harness):
    h = harness
    results = [{"type": "web_search_result", "url": f"https://example.com/{index}", "title": "题" * 100} for index in range(7)]
    results.extend([results[0], {"url": "http://127.0.0.1/", "title": "private"}, {"url": "javascript:alert(1)", "title": "bad"}])
    final = message(content=[{"type": "web_search_tool_result", "content": results}],
                    usage=NS(input_tokens=3, output_tokens=2, cache_read_input_tokens=4, cache_creation_input_tokens=5,
                             server_tool_use=NS(web_search_requests=2, web_fetch_requests=1)))
    h.streams.append(FakeStream(final, "正文 https://untrusted.example/link"))
    events = run(h)
    cards = [event["card"] for event in events if isinstance(event, dict) and "card" in event]
    assert len(cards) == 1 and cards[0]["subtype"] == "web_sources"
    assert len(cards[0]["sources"]) == 5
    assert [source["url"] for source in cards[0]["sources"]] == [f"https://example.com/{index}" for index in range(5)]
    assert all(len(source["title"]) == 80 for source in cards[0]["sources"])
    assert h.state.trace["web_search_requests"] == 2 and h.state.trace["web_fetch_requests"] == 1
    assert h.state.trace["agent_usage"] == {"input_tokens": 3, "output_tokens": 2, "cache_read_input_tokens": 4, "cache_creation_input_tokens": 5}
    assert not h.state.billable


def test_web_fetch_result_actual_sdk_block_type(harness):
    h = harness
    h.streams.append(FakeStream(message(content=[{"type": "web_fetch_tool_result", "content": {"type": "web_fetch_result", "url": "https://example.com/page", "content": {"type": "document", "title": "网页标题"}}}]), "读过了"))
    events = run(h)
    source = next(event["card"]["sources"][0] for event in events if isinstance(event, dict) and "card" in event)
    assert source == {"title": "网页标题", "url": "https://example.com/page", "site_name": "example.com"}


@pytest.mark.parametrize("text,error", [("已输出", RuntimeError("secret-query")), ("", RuntimeError("secret-query"))])
def test_midturn_request_failure_saves_only_delivered_content(harness, text, error):
    h = harness
    h.streams.extend([FakeStream(message("pause_turn"), text), error])
    events = run(h)
    assert bool(h.saves) is bool(text)
    assert events[-1] == {"error": "你的模型调用失败：调用失败。本条没有改用平台模型。"}
    assert "secret-query" not in json.dumps(h.state.trace) + json.dumps(events)
    assert not h.state.billable and not h.followups


def test_budget_exhaustion_saves_text_and_reports_timeout(harness):
    h = harness
    clock = [0.0]
    h.monkeypatch.setattr(h.agent, "_now", lambda: clock[0])
    original = h.agent.open_agent_stream
    def open_stream(*args, **kwargs):
        result = original(*args, **kwargs)
        original_next = result.__next__
        class Expiring(FakeStream):
            def __next__(self):
                chunk = original_next()
                clock[0] = 241.0
                return chunk
        result.__class__ = Expiring
        return result
    h.monkeypatch.setattr(h.agent, "open_agent_stream", open_stream)
    h.streams.append(FakeStream(message(), "已有文字"))
    events = run(h)
    assert h.saves == [("已有文字", None)]
    assert events[-1]["error"] == "你的模型调用失败：响应超时。本条没有改用平台模型。"
    assert h.state.trace["agent_stop"] == "budget"


def test_busy_slot_after_card_saves_and_preserves_billing(harness):
    h = harness
    h.monkeypatch.setattr(h.agent, "_SLOT_WAIT_SECONDS", .01)
    original = h.chat.execute_intent
    def execute(*args):
        result = original(*args)
        h.monkeypatch.setattr(h.chat, "_byok_slot", busy)
        return result
    def busy(*args):
        raise h.chat._ByokBusyError("自带模型通道繁忙，请稍后再试")
    h.monkeypatch.setattr(h.chat, "execute_intent", execute)
    h.streams.append(FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})])))
    events = run(h)
    assert len(h.saves) == 1 and h.state.billable
    assert events[-1] == {"error": "自带模型通道繁忙，请稍后再试"}
    assert h.state.trace["agent_stop"] == "busy"


@pytest.mark.parametrize("stop,text,suffix,error", [
    ("max_tokens", "片段", "", False), ("refusal", "片段", "（Claude 中止了这条回复）", False),
    ("refusal", "", "", True), ("stop_sequence", "回答", "", False),
])
def test_final_stop_rules(harness, stop, text, suffix, error):
    h = harness
    h.streams.append(FakeStream(message(stop, text=text), text))
    events = run(h)
    assert h.state.trace["agent_stop"] == stop
    assert ("error" in events[-1]) is error
    if text:
        assert h.saves == [(text + suffix, None)]


def test_total_visible_text_cap_is_8000(harness):
    h = harness
    h.streams.extend([FakeStream(message("pause_turn"), "字" * 4000), FakeStream(message("pause_turn"), "字" * 4000), FakeStream(message(), "多" * 500)])
    events = run(h)
    assert len("".join(event.get("text", "") for event in events if isinstance(event, dict))) == 8000
    assert h.state.trace["agent_stop"] == "text_limit"
    assert len(h.requests) == 2


def test_pause_preserves_complete_fallback_content(harness):
    h = harness
    content = [{"type": "text", "text": "旧段"}, {"type": "fallback", "model": "other"}, {"type": "text", "text": "新段"}]
    h.streams.extend([FakeStream(message("pause_turn", content=content)), FakeStream(message(text="完成"), "完成")])
    run(h)
    assert h.requests[1][0][-1] == {"role": "assistant", "content": content}


def test_image_description_also_obeys_8000_visible_character_cap(harness):
    h = harness
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        state.full_response += "图片已生成。描述" * 10
        agent_result.update(success=True, image_path="/uploads/cat.png", model="model", aspect_ratio="1:1")
        yield h.chat._sse({"generated_image": {"image_path": "/uploads/cat.png"}})
        yield h.chat._sse({"text": "图片已生成。描述" * 10})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.extend([FakeStream(message("pause_turn"), "字" * 4000),
                      FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})]), "字" * 3995)])
    events = run(h)
    text = "".join(event.get("text", "") for event in events if isinstance(event, dict))
    assert len(text) == 8000
    assert h.saves == [(text, "/uploads/cat.png")]
    assert h.state.trace["agent_stop"] == "text_limit"


def test_image_completion_while_heartbeat_is_suspended_cleans_attachment(harness):
    h = harness
    async def scenario():
        ready = asyncio.Event()
        async def image(ctx, state, prompt, *, agent_result, **kwargs):
            await ready.wait()
            agent_result.update(success=True, image_path="/uploads/late.png", model="model", aspect_ratio="1:1")
            yield h.chat._sse({"generated_image": {"image_path": "/uploads/late.png"}})
        h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
        h.monkeypatch.setattr(h.chat, "_IMAGE_HEARTBEAT_SECONDS", .001)
        h.streams.append(FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])))
        stream = h.agent.stream_claude_agent(h.ctx, h.state)
        while await anext(stream) != ": generating-image\n\n":
            pass
        ready.set()
        await asyncio.sleep(.01)
        await stream.aclose()
    asyncio.run(scenario())
    assert h.deleted == ["/uploads/late.png"]
    assert not h.chat._BYOK_USERS and not h.saves


def test_error_card_points_are_the_failure_reason_given_to_claude(harness):
    h = harness
    h.monkeypatch.setattr(h.chat, "execute_intent", lambda *args: {"type": "card", "source": "天气", "points": ["天气连接失败，请稍后重试"], "error": True})
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})])), FakeStream(message(text="稍后再试"), "稍后再试")])
    run(h)
    assert h.requests[1][0][-1]["content"][0]["content"] == "天气连接失败，请稍后重试"
    assert not h.state.billable


def test_server_results_before_fallback_are_still_sources(harness):
    h = harness
    content = [{"type": "web_search_tool_result", "content": [{"type": "web_search_result", "title": "来源", "url": "https://example.com/page"}]},
               {"type": "fallback"}, {"type": "text", "text": "回答"}]
    h.streams.append(FakeStream(message(content=content), "回答"))
    events = run(h)
    assert next(event["card"]["sources"][0]["url"] for event in events if isinstance(event, dict) and "card" in event) == "https://example.com/page"


def test_user_lock_is_held_during_mode_detection(harness):
    h = harness
    def mode(*args):
        assert h.ctx.user in h.chat._BYOK_USERS
        assert h.chat._BYOK_ACTIVE == 0
        return "friend"
    h.monkeypatch.setattr(h.chat, "detect_mode", mode)
    h.streams.append(FakeStream(message(text="回答"), "回答"))
    run(h)
    assert h.saves == [("回答", None)]
    assert not h.chat._BYOK_USERS


def test_total_budget_already_runs_during_mode_detection(harness):
    h = harness
    clock = [0.0]
    h.monkeypatch.setattr(h.agent, "_now", lambda: clock[0])
    def mode(*args):
        clock[0] = 241.0
        return "friend"
    h.monkeypatch.setattr(h.chat, "detect_mode", mode)
    events = run(h)
    assert not h.requests and not h.saves
    assert events[-1]["error"] == "你的模型调用失败：响应超时。本条没有改用平台模型。"
    assert h.state.trace["agent_stop"] == "budget"


def test_final_answer_after_tool_cap_still_applies_refusal_rule(harness):
    h = harness
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_hot_topics", {"source": "微博"}, str(index))])) for index in range(5)])
    h.streams.append(FakeStream(message("refusal", text="片段"), "片段"))
    events = run(h)
    assert events[-2] == {"text": "（Claude 中止了这条回复）"}
    assert h.saves[0][0].endswith("片段（Claude 中止了这条回复）")
    assert h.state.trace["agent_stop"] == "refusal"


def test_budget_interrupts_pending_or_mode_or_conversation_wait(harness):
    h = harness
    async def scenario():
        for phase in ("pending", "mode", "conversation"):
            gate = threading.Event()
            entered = threading.Event()
            def blocking(*args):
                entered.set()
                gate.wait()
                return "friend"
            async def blocking_conversation(*args):
                entered.set()
                await asyncio.Event().wait()
            patch = pytest.MonkeyPatch()
            patch.setattr(h.agent, "agent_total_seconds", lambda: .02)
            patch.setattr(h.chat, "get_pending", blocking if phase == "pending" else lambda *args: None)
            patch.setattr(h.chat, "detect_mode", blocking if phase == "mode" else lambda *args: "friend")
            patch.setattr(h.chat, "_ensure_active_conversation", blocking_conversation if phase == "conversation" else lambda *args: asyncio.sleep(0))
            h.state = h.chat.ChatState(trace={})
            async def collect():
                return [json.loads(event[6:]) if event.startswith("data: ") else event
                        async for event in h.agent.stream_claude_agent(h.ctx, h.state)]
            try:
                events = await asyncio.wait_for(collect(), timeout=.2)
                assert entered.is_set()
                assert events[-1] == {"error": "你的模型调用失败：响应超时。本条没有改用平台模型。"}
                assert h.state.trace["agent_stop"] == "budget"
                assert h.state.trace["agent_rounds"] == 0 and h.state.trace["agent_tools"] == []
                assert h.state.trace["agent_usage"] == {}
                assert h.state.trace["web_search_requests"] == h.state.trace["web_fetch_requests"] == 0
                assert not h.chat._BYOK_USERS and not h.requests and not h.saves
            finally:
                gate.set()
                patch.undo()
    asyncio.run(scenario())


def test_mirror_persistence_error_still_propagates_to_platform_handler(harness):
    h = harness
    h.monkeypatch.setattr(h.chat, "detect_mode", lambda *args: "mirror")
    async def mirror(ctx, state):
        state.full_response = "已交付"
        yield h.chat._sse({"text": "已交付"})
        raise RuntimeError("conversation no longer available")
    h.monkeypatch.setattr(h.chat, "stream_mirror", mirror)
    with pytest.raises(RuntimeError, match="conversation no longer available"):
        run(h)
    assert h.state.trace == {"mode": "mirror"}
    assert not h.chat._BYOK_USERS and not h.requests


@pytest.mark.parametrize("phase", ["routing", "image"])
def test_deleted_conversation_keeps_platform_resource_not_found_handler(harness, phase):
    h = harness
    async def deleted(*args):
        raise h.chat.ResourceNotFound("deleted")
    if phase == "routing":
        h.monkeypatch.setattr(h.chat, "_ensure_active_conversation", deleted)
    else:
        async def image(*args, **kwargs):
            if False:
                yield ""
            raise h.chat.ResourceNotFound("deleted")
        h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
        h.streams.append(FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])))
    with pytest.raises(h.chat.ResourceNotFound):
        run(h)
    assert not h.chat._BYOK_USERS and not h.saves


@pytest.mark.parametrize("value,expected", [(None, 240), ("59", 240), ("60", 60), ("290", 290), ("291", 240), ("garbage", 240), ("NaN", 240)])
def test_total_seconds_range(harness, value, expected):
    if value is None:
        harness.monkeypatch.delenv("FIONA_CLAUDE_AGENT_TOTAL_SECONDS", raising=False)
    else:
        harness.monkeypatch.setenv("FIONA_CLAUDE_AGENT_TOTAL_SECONDS", value)
    assert harness.agent.agent_total_seconds() == expected
