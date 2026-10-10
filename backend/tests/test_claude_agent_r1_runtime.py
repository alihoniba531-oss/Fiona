"""R1 regression contracts: isolated tools, persistence, SDK replay and image limits."""
import asyncio
import base64
from io import BytesIO
import json
import random
import socket
import threading

from PIL import Image
import pytest

from test_claude_agent_runtime import FakeStream, call, harness, message, run


@pytest.fixture(scope="module", autouse=True)
def offline_module():
    patch = pytest.MonkeyPatch()
    def blocked(*args, **kwargs):
        raise AssertionError("R1 runtime forbids TCP connections and DNS")
    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, blocked)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, blocked)
    yield
    patch.undo()


def image_uri(size=(2, 2), mode="RGB", *, noise=False, format="PNG"):
    if noise:
        image = Image.frombytes(mode, size, random.Random(19).randbytes(size[0] * size[1] * len(mode)))
    else:
        image = Image.new(mode, size, "red")
    buffer = BytesIO()
    image.save(buffer, format=format)
    return "data:image/" + ("jpeg" if format == "JPEG" else format.lower()) + ";base64," + base64.b64encode(buffer.getvalue()).decode()


def queue_card(h):
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})])),
                      FakeStream(message(text="天气晴"), "天气晴")])


def test_card_billable_is_committed_only_after_successful_save(harness):
    h = harness
    async def save(ctx, state, image_path=None):
        assert not state.billable
        h.saves.append((state.full_response, image_path))
        state.response_saved = True
    h.monkeypatch.setattr(h.chat, "_save_response", save)
    queue_card(h)
    run(h)
    assert h.state.billable and len(h.saves) == 1


def test_card_persistence_failure_is_a_platform_error_and_never_billable(harness):
    h = harness
    attempts = []
    async def save(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("conversation no longer available")
    h.monkeypatch.setattr(h.chat, "_save_response", save)
    queue_card(h)
    with pytest.raises(RuntimeError, match="conversation no longer available"):
        run(h)
    assert not h.state.billable and not h.state.response_saved and len(attempts) == 1
    assert "byok_error" not in h.state.trace


def test_card_disconnect_before_persistence_never_commits_charge(harness):
    h = harness
    queue_card(h)
    async def scenario():
        stream = h.agent.stream_claude_agent(h.ctx, h.state)
        while '"card"' not in await anext(stream):
            pass
        await stream.aclose()
    asyncio.run(scenario())
    assert not h.state.billable and not h.state.response_saved and not h.saves
    assert not h.chat._BYOK_USERS


def test_successful_image_with_failed_save_is_refunded_and_cleaned(harness):
    h = harness
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        agent_result.update(success=True, image_path="/uploads/r1.png", model="model", aspect_ratio="1:1")
        yield h.chat._sse({"generated_image": {"image_path": "/uploads/r1.png"}})
        yield h.chat._sse({"text": "图片已生成。"})
    async def save(*args, **kwargs):
        raise RuntimeError("conversation no longer available")
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.monkeypatch.setattr(h.chat, "_save_response", save)
    h.streams.extend([FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])), FakeStream(message(text="完成"), "完成")])
    with pytest.raises(RuntimeError):
        run(h)
    assert not h.state.billable and h.deleted == ["/uploads/r1.png"]


def test_image_tool_failure_resets_status_and_keeps_followups(harness):
    h = harness
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        yield h.chat._sse({"status": "generating_image", "source": "tool"})
        state.trace["error"] = "ImageGenerationError"
        agent_result["error"] = "这次画面描述没通过内容审核，换个说法再让我画吧。"
        yield h.chat._sse({"error": agent_result["error"]})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.extend([FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})]), "我来画。"),
                      FakeStream(message(text="没画成，请换个描述。"), "没画成，请换个描述。")])
    events = run(h)
    assert {"status": "image_failed", "source": "tool"} in events
    assert not any("error" in event for event in events if isinstance(event, dict))
    assert h.state.trace["agent_tool_errors"] == 1 and "error" not in h.state.trace
    assert events[-1] == {"done": True} and len(h.followups) == 1
    assert not h.state.billable
    assert h.requests[1][0][-1]["content"][0]["content"] == "这次画面描述没通过内容审核，换个说法再让我画吧。"


def test_replayed_sdk_citation_nulls_and_search_result_fields_are_preserved(harness):
    from anthropic.types.beta import BetaTextBlock, BetaWebSearchToolResultBlock
    h = harness
    text = BetaTextBlock(type="text", text="引用", citations=[
        {"type": "web_search_result_location", "cited_text": "事实", "encrypted_index": "id", "url": "https://example.com/", "title": None},
        {"type": "char_location", "cited_text": "文本", "document_index": 0, "document_title": None, "start_char_index": 0, "end_char_index": 2},
    ])
    result = BetaWebSearchToolResultBlock(type="web_search_tool_result", tool_use_id="search",
        content=[{"type": "web_search_result", "url": "https://example.com/", "title": "网页", "encrypted_content": "opaque", "page_age": None}])
    h.streams.extend([FakeStream(message("tool_use", content=[text, result, call("plan_route", {"origin": "甲", "destination": "乙"})]), "引用"),
                      FakeStream(message(text="答复"), "答复")])
    run(h)
    replay = h.requests[1][0][-2]["content"]
    assert "title" in replay[0]["citations"][0] and replay[0]["citations"][0]["title"] is None
    assert "document_title" in replay[0]["citations"][1] and replay[0]["citations"][1]["document_title"] is None
    assert replay[1]["content"][0]["page_age"] is None
    assert replay[1]["content"][0]["encrypted_content"] == "opaque"


@pytest.mark.parametrize("utterance,city,expected", [
    ("北京明天冷吗", "北京市", "北京"), ("那曲市天气", "那曲", "那曲"),
    ("香港", "香港特别行政区", "香港"), ("延边", "延边自治州", "延边"),
    ("北京", "京", None), ("帮我查天气", "北京", None),
])
def test_weather_variants_match_only_user_originals(harness, utterance, city, expected):
    h = harness
    h.ctx.user_content = h.ctx.message = utterance
    h.ctx.system_prompt = "画像记忆里有北京"
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": city})])), FakeStream(message(text="答复"), "答复")])
    run(h)
    assert h.executions == ([] if expected is None else [("weather", {"city": expected})])


def test_client_definitions_do_not_enable_eager_input_streaming(harness):
    assert all("eager_input_streaming" not in tool for tool in harness.agent.CLAUDE_CLIENT_TOOLS)


@pytest.mark.parametrize("size,mode,noise,expected_format", [((4000, 10), "RGB", False, "JPEG"), ((1700, 700), "RGBA", True, "PNG")])
def test_oversized_image_copy_is_bounded_and_correctly_encoded(harness, size, mode, noise, expected_format):
    h = harness
    original = image_uri(size, mode, noise=noise)
    result = h.agent._claude_image_source(original)
    encoded = base64.b64decode(result["data"])
    with Image.open(BytesIO(encoded)) as image:
        assert max(image.size) <= 2000 and image.format == expected_format
        if expected_format == "PNG":
            assert "A" in image.getbands()
    assert len(encoded) <= 3_500_000 and len(result["data"]) <= 4 * ((3_500_000 + 2) // 3)
    assert result["media_type"] == "image/" + expected_format.lower()
    assert original != "data:" + result["media_type"] + ";base64," + result["data"]


def test_small_image_stays_byte_identical_and_image_work_runs_in_thread(harness):
    h = harness
    h.ctx.has_image = True
    h.ctx.image_base64 = original = image_uri()
    main_thread = threading.get_ident()
    seen = []
    helper = h.agent._claude_image_source
    def checked(data):
        seen.append(threading.get_ident())
        return helper(data)
    h.monkeypatch.setattr(h.agent, "_claude_image_source", checked)
    h.streams.append(FakeStream(message(text="猫"), "猫"))
    run(h)
    source = h.requests[0][0][-1]["content"][1]["source"]
    assert source == {"type": "base64", "media_type": "image/png", "data": original.split(",", 1)[1]}
    assert seen and all(ident != main_thread for ident in seen)
    assert h.ctx.image_base64 == original


@pytest.mark.parametrize("phase", ["pending", "clear", "mode", "conversation"])
def test_platform_preparation_errors_are_not_byok_failures(harness, phase):
    h = harness
    def broken(*args):
        raise RuntimeError("platform preparation failed")
    async def broken_async(*args):
        raise RuntimeError("platform preparation failed")
    target = {"pending": "get_pending", "clear": "clear_pending", "mode": "detect_mode", "conversation": "_ensure_active_conversation"}[phase]
    h.monkeypatch.setattr(h.chat, target, broken_async if phase == "conversation" else broken)
    with pytest.raises(RuntimeError, match="platform preparation failed"):
        run(h)
    assert not h.requests and "byok_error" not in h.state.trace


def test_tool_failures_accumulate_count_and_allow_normal_followups(harness):
    h = harness
    def broken(*args):
        raise RuntimeError("secret city argument")
    h.monkeypatch.setattr(h.chat, "execute_intent", broken)
    h.streams.extend([FakeStream(message("tool_use", content=[call("plan_route", {"origin": "甲", "destination": "乙"})])),
                      FakeStream(message(text="工具失败了"), "工具失败了")])
    events = run(h)
    assert h.state.trace["agent_tool_errors"] == 1 and "error" not in h.state.trace
    assert "secret" not in json.dumps(events) + json.dumps(h.state.trace)
    assert len(h.followups) == 1 and not h.state.billable


def test_sources_are_not_delivered_if_error_happens_before_any_content(harness):
    h = harness
    h.streams.extend([FakeStream(message("pause_turn", content=[{"type": "web_search_tool_result", "content": [{"type": "web_search_result", "title": "来源", "url": "https://example.com/"}]}])),
                      RuntimeError("upstream failure")])
    events = run(h)
    assert not h.saves and not any("card" in event for event in events if isinstance(event, dict))
    assert len(events) == 1 and "error" in events[0]


def test_new_round_separates_text_after_cards_in_events_and_persistence(harness):
    h = harness
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})]), "先查。"),
                      FakeStream(message(text="晴天。"), "晴天。")])
    events = run(h)
    assert {"text": "\n\n"} in events
    assert h.saves[0][0].endswith("］\n\n晴天。")


def test_busy_global_slot_keeps_old_message_and_does_not_count_daily_chat(harness):
    h = harness
    def busy(*args):
        raise h.chat._ByokBusyError("自带模型通道繁忙，请稍后再试")
    h.monkeypatch.setattr(h.chat, "_byok_slot", busy)
    h.monkeypatch.setattr(h.agent, "_SLOT_WAIT_SECONDS", .001)
    events = run(h)
    assert events[-1] == {"error": "自带模型通道繁忙，请稍后再试"}
    assert not h.caps and not h.requests


def test_daily_chat_counter_runs_once_after_successful_slot_admission(harness):
    h = harness
    def cap(name, username, hit):
        if name == "byok_chat":
            assert h.chat._BYOK_ACTIVE == 1
        h.caps.append((name, hit))
    h.monkeypatch.setattr(h.chat, "check_chat_daily_cap", cap)
    queue_card(h)
    run(h)
    assert h.caps.count(("byok_chat", True)) == 1


def test_image_finishing_exactly_at_budget_never_leaves_an_orphan(harness):
    h = harness
    clock = [0.0]
    h.monkeypatch.setattr(h.agent, "_now", lambda: clock[0])
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        agent_result.update(success=True, image_path="/uploads/budget.png", model="model", aspect_ratio="1:1")
        clock[0] = 241.0
        yield h.chat._sse({"generated_image": {"image_path": "/uploads/budget.png"}})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.append(FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])))
    events = run(h)
    assert "error" in events[-1]
    assert bool(h.saves) != bool(h.deleted)
    if h.saves:
        assert h.saves[0][1] == "/uploads/budget.png" and h.state.billable
    else:
        assert h.deleted == ["/uploads/budget.png"] and not h.state.billable


def test_unattached_owned_image_is_cleaned_even_when_partial_text_is_saved(harness):
    h = harness
    h.monkeypatch.setattr(h.agent, "agent_total_seconds", lambda: .02)
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        agent_result.update(success=True, image_path="/uploads/owned.png", model="model", aspect_ratio="1:1")
        await asyncio.Event().wait()
        yield h.chat._sse({"generated_image": {"image_path": "/uploads/owned.png"}})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.append(FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})]), "准备画。"))
    events = run(h)
    assert "error" in events[-1]
    assert h.saves == [("准备画。", None)] and h.deleted == ["/uploads/owned.png"]
    assert not h.state.billable


def test_cancel_during_successful_save_commits_the_already_persisted_card(harness):
    h = harness
    queue_card(h)
    async def scenario():
        entered, released = asyncio.Event(), asyncio.Event()
        async def save(ctx, state, image_path=None):
            entered.set()
            await released.wait()
            h.saves.append((state.full_response, image_path))
            state.response_saved = True
        h.monkeypatch.setattr(h.chat, "_save_response", save)
        async def consume():
            return [event async for event in h.agent.stream_claude_agent(h.ctx, h.state)]
        owner = asyncio.create_task(consume())
        await entered.wait()
        owner.cancel()
        released.set()
        await asyncio.gather(owner, return_exceptions=True)
        assert owner.cancelled()
    asyncio.run(scenario())
    assert h.state.response_saved and h.state.billable and len(h.saves) == 1
    assert not h.chat._BYOK_USERS


def test_missing_weather_parameters_never_write_pending(harness):
    h = harness
    h.streams.extend([FakeStream(message("tool_use", content=[call("get_weather")])),
                      FakeStream(message(text="主人想查哪个城市？"), "主人想查哪个城市？")])
    run(h)
    assert not h.executions and not h.state.billable and h.state.trace["agent_tool_errors"] == 1


@pytest.mark.parametrize("phase", ["slot", "daily_counter"])
def test_platform_admission_exceptions_before_claude_are_not_model_failures(harness, phase):
    h = harness
    def broken(*args, **kwargs):
        raise RuntimeError("platform admission failed")
    h.monkeypatch.setattr(h.chat, "_byok_slot" if phase == "slot" else "check_chat_daily_cap", broken)
    with pytest.raises(RuntimeError, match="platform admission failed"):
        run(h)
    assert not h.requests and not h.state.billable and "byok_error" not in h.state.trace
    assert not h.chat._BYOK_USERS and h.chat._BYOK_ACTIVE == 0
