"""Main-model image tool: isolated SDK streams, persistence and routing contracts."""
import asyncio
import json
import socket
from types import SimpleNamespace as NS

import pytest


@pytest.fixture(autouse=True)
def tool_environment(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    monkeypatch.setenv("ARK_API_KEY", "fake-ark-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-qwen-key")
    def blocked_connect(*args, **kwargs):
        raise AssertionError("真实网络请求被新增测试的离线守卫禁止")
    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", blocked_connect)


def test_tool_definition_and_strict_arguments():
    from services.image_tool import anthropic_image_tool, openai_image_tool, validate_image_tool_call
    from persona import BASE_SAFETY_RULES
    tool = openai_image_tool()
    assert tool["type"] == "function"
    fn = tool["function"]
    assert fn["name"] == "generate_image"
    assert "strict" not in fn
    assert fn["parameters"]["required"] == ["prompt"]
    assert fn["parameters"]["properties"]["prompt"]["maxLength"] == 1500
    assert anthropic_image_tool() == {"name": fn["name"], "description": fn["description"], "input_schema": fn["parameters"]}
    assert BASE_SAFETY_RULES.strip() not in fn["description"]
    for phrase in ("明确", "提示词", "历史", "以此图修改", "真实姓名", "最多说一句", "千问", "Seedream"):
        assert phrase in fn["description"]
    assert validate_image_tool_call({"name": "generate_image", "arguments": {"prompt": " 猫 ", "model": "bad", "aspect_ratio": "4:3"}}) == {"prompt": "猫"}
    for prompt in ("", "  ", "猫" * 1501, None, 42):
        assert validate_image_tool_call({"name": "generate_image", "arguments": {"prompt": prompt}}) is None


def test_accumulator_repeated_ids_and_first_generate_only():
    from services.image_tool import OpenAIToolCallAccumulator
    acc = OpenAIToolCallAccumulator()
    acc.add([NS(index=0, id="same", function=NS(name="generate_image", arguments='{"prompt":"'))])
    acc.add([NS(index=0, id="same", function=NS(name=None, arguments='猫"}'))])
    acc.add([NS(index=1, id="other", function=NS(name="generate_image", arguments='{"prompt":"狗"}'))])
    call, invalid = acc.result("tool_calls")
    assert call == {"name": "generate_image", "arguments": {"prompt": "猫"}}
    assert not invalid
    assert acc.result("length") == (None, True)
    assert acc.result("stop") == (None, False)


@pytest.mark.parametrize("raw", ['{"prompt":', '[]', '{"prompt": NaN}'])
def test_accumulator_rejects_bad_json(raw):
    from services.image_tool import OpenAIToolCallAccumulator
    acc = OpenAIToolCallAccumulator()
    acc.add([NS(index=0, id="id", function=NS(name="generate_image", arguments=raw))])
    assert acc.result("tool_calls") == (None, True)


def test_anthropic_last_fallback_and_bad_stop():
    from services.image_tool import extract_anthropic_image_tool_call
    old = NS(type="tool_use", name="generate_image", input={"prompt": "旧图"})
    new = NS(type="tool_use", name="generate_image", input={"prompt": "新图"})
    assert extract_anthropic_image_tool_call(NS(stop_reason="tool_use", content=[old, NS(type="fallback"), new])) == ({"name": "generate_image", "arguments": {"prompt": "新图"}}, False)
    for stop in ("refusal", "max_tokens", "length", "content_filter"):
        assert extract_anthropic_image_tool_call(NS(stop_reason=stop, content=[new])) == (None, True)


def test_model_availability_and_error_categories(monkeypatch):
    from tools.image_generation import _ark_error, _provider_error, get_image_models, image_model_available
    assert image_model_available("seedream-5.0-flash")
    monkeypatch.delenv("ARK_API_KEY")
    assert not image_model_available("seedream-5.0-flash")
    assert next(item for item in get_image_models()["models"] if item["id"] == "seedream-5.0-flash")["available"] is False
    assert _ark_error(400, {"error": {"code": "SensitiveContentDetected"}}).category == "moderation"
    assert _ark_error(403, {}).category == "unavailable"
    assert _provider_error(400, {"error": {"code": "DataInspectionFailed"}}).category == "moderation"


async def collect(stream):
    return [json.loads(event[6:]) if event.startswith("data: ") else event async for event in stream]


@pytest.fixture
def chat_harness(monkeypatch):
    import services.chat_service as chat
    ctx = chat.ChatContext("tool-user", "按上面的提示词画", False, None, "按上面的提示词画", [], 0, "persona", [{"role": "user", "content": "按上面的提示词画"}], conversation_id="conversation", image_model="qwen-image-3.0")
    state = chat.ChatState(trace={"model": "main"}, sys_prompt_final="persona")
    saves, calls, refunds, traces = [], [], [], []
    async def active(*args):
        return None
    async def save(user, role, content, **kwargs):
        saves.append((user, role, content, kwargs))
        return 1
    async def generate(prompt, ratio, **kwargs):
        calls.append((prompt, ratio, kwargs))
        return {"image_path": "/uploads/generated_test.png", "model": "provider-model", "width": 1024, "height": 1024}
    async def refund(*args):
        refunds.append(args)
    async def log(*args, **kwargs):
        traces.append(kwargs["payload"].copy())
    async def followups(*args):
        return None
    monkeypatch.setattr(chat, "_ensure_active_conversation", active)
    monkeypatch.setattr(chat, "save_message", save)
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat, "refund_strawberries", refund)
    monkeypatch.setattr(chat, "log_event", log)
    monkeypatch.setattr(chat, "_normal_followups", followups)
    monkeypatch.setattr(chat, "choose_model", lambda *a: "main")
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())
    monkeypatch.setattr(chat, "detect_mode", lambda *a: "friend")
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *a: {"intent": None, "params": {}, "missing": []})
    monkeypatch.setattr(chat, "get_pending", lambda *a: None)
    monkeypatch.setattr(chat, "clear_pending", lambda *a: None)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **kw: (iter([block("普通回复"), block(finish="stop")]), False))
    async def planner(history, message):
        return {"status": "draw", "prompt": "猫"}
    monkeypatch.setattr(chat, "plan_image", planner, raising=False)
    return chat, ctx, state, saves, calls, refunds, traces


def test_execution_preserves_lead_and_trace(chat_harness):
    chat, ctx, state, saves, calls, *_ = chat_harness
    result = asyncio.run(collect(chat._stream_image_execution(ctx, state, "猫", source="tool", lead_text=" 好，我来画。 ")))
    assert calls == [("猫", "1:1", {"model_id": "seedream-5.0-flash"})]
    assert result == [
        {"status": "generating_image", "message": "正在用 Seedream 5.0 Flash 生成图片…", "source": "tool"},
        {"generated_image": {"image_path": "/uploads/generated_test.png", "model": "provider-model", "width": 1024, "height": 1024}},
        {"text": "\n\n图片已生成。"},
        {"text": "\n\n使用的描述（Seedream 5.0 Flash）：猫", "speak": False},
        {"done": True},
    ]
    assert len(saves) == 1 and saves[0][2] == "好，我来画。\n\n图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：猫"
    assert state.billable and state.response_saved
    assert state.trace == {"model": "main", "intent": "generate_image", "tool": "generate_image", "image_source": "tool", "image_model": "seedream-5.0-flash", "image_fallback": False}


@pytest.mark.parametrize("model,ark,ratio,prompt,expected_model,expected_ratio,fallback", [
    (None, True, "9:16", "横版猫", "seedream-5.0-flash", "9:16", False),
    ("qwen-image-3.0", True, None, "横版猫", "qwen-image-3.0", "16:9", False),
    (None, False, None, "猫", "qwen-image-3.0", "1:1", True),
])
def test_execution_model_ratio_priority(chat_harness, monkeypatch, model, ark, ratio, prompt, expected_model, expected_ratio, fallback):
    chat, ctx, state, saves, calls, *_ = chat_harness
    if not ark:
        monkeypatch.delenv("ARK_API_KEY")
    result = asyncio.run(collect(chat._stream_image_execution(ctx, state, prompt, source="tool", model_id=model, aspect_ratio=ratio)))
    assert calls == [(prompt, expected_ratio, {} if expected_model == "qwen-image-3.0" else {"model_id": expected_model})]
    assert state.trace["image_fallback"] == fallback
    if fallback:
        assert result[-2]["speak"] is False and "暂未配置" in result[-2]["text"]
        assert "Qwen Image 3.0" in saves[0][2]


@pytest.mark.parametrize("category,message", [
    ("moderation", "这次画面描述没通过内容审核，换个说法再让我画吧。"),
    ("unavailable", "Seedream 暂时用不了（可能未开通或欠费），可以说『用千问画』改用 Qwen Image 3.0。"),
    ("other", "原样错误"),
])
def test_execution_safe_error_no_save(chat_harness, monkeypatch, category, message):
    chat, ctx, state, saves, calls, *_ = chat_harness
    async def fail(*args, **kwargs):
        raise chat.ImageGenerationError("原样错误", category=category)
    monkeypatch.setattr(chat, "generate_image", fail)
    result = asyncio.run(collect(chat._stream_image_execution(ctx, state, "猫", source="tool", lead_text="我来画")))
    assert [event for event in result if "error" in event] == [{"error": message}]
    assert not saves and not state.billable
    assert not any("done" in event for event in result)


def test_execution_no_keys_and_busy(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    monkeypatch.delenv("ARK_API_KEY")
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    assert asyncio.run(collect(chat._stream_image_execution(ctx, state, "猫", source="tool"))) == [{"error": "图片生成服务尚未配置，请联系管理员。"}]
    assert not saves and not calls and not state.billable
    monkeypatch.setenv("ARK_API_KEY", "fake")
    chat._IMAGE_GENERATION_USERS.add(ctx.user)
    assert asyncio.run(collect(chat._stream_image_execution(ctx, state, "猫", source="tool"))) == [{"error": "已有图片正在生成，请等待完成后再试"}]
    assert not saves and not calls and not state.billable


def test_execution_cancel_cleans_unsaved_attachment(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    deleted = []
    monkeypatch.setattr(chat, "delete_uploaded_files", deleted.extend)
    async def scenario():
        entered = asyncio.Event()
        async def vanish(*args):
            entered.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(chat, "_ensure_active_conversation", lambda *a: asyncio.sleep(0))
        stream = chat._stream_image_execution(ctx, state, "猫", source="tool")
        await anext(stream)
        monkeypatch.setattr(chat, "_ensure_active_conversation", vanish)
        pending = asyncio.create_task(anext(stream))
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    asyncio.run(scenario())
    assert deleted == ["/uploads/generated_test.png"]
    assert ctx.user not in chat._IMAGE_GENERATION_USERS
    assert not state.billable and not saves


def block(text=None, calls=None, finish=None):
    return NS(choices=[NS(delta=NS(content=text, tool_calls=calls), finish_reason=finish)])


def tool_blocks(prompt="猫", *, lead="我来画。", finish="tool_calls", raw=None, multiple=False):
    raw = raw if raw is not None else json.dumps({"prompt": prompt}, ensure_ascii=False)
    chunks = [block(lead)] if lead else []
    chunks.extend([
        block(calls=[NS(index=0, id="same", function=NS(name="generate_image", arguments=raw[:5]))]),
        block(calls=[NS(index=0, id="same", function=NS(name=None, arguments=raw[5:]))]),
    ])
    if multiple:
        chunks.append(block(calls=[NS(index=1, id="second", function=NS(name="generate_image", arguments='{"prompt":"狗"}'))]))
    chunks.append(block(finish=finish))
    return chunks


@pytest.mark.parametrize("ratio,model", [(None, None), ("9:16", "qwen-image-3.0")])
def test_platform_planner_draw_without_reply_or_routing(chat_harness, monkeypatch, ratio, model):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    planner_requests, cleared = [], []
    async def planner(history, message):
        planner_requests.append((history, message))
        return {"status": "draw", "prompt": "猫", "aspect_ratio": ratio, "model": model}
    monkeypatch.setattr(chat, "plan_image", planner)
    monkeypatch.setattr(chat, "clear_pending", lambda *a: cleared.append(a))
    monkeypatch.setattr(chat, "get_pending", lambda *a: {"intent": "generate_image"})
    def forbidden(*args, **kwargs):
        pytest.fail("判断器生图不调用回复、模式识别或意图识别")
    monkeypatch.setattr(chat, "_create_stream_with_fallback", forbidden)
    monkeypatch.setattr(chat, "detect_mode", forbidden)
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", forbidden)
    result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert planner_requests == [(ctx.history, ctx.message)] and len(cleared) == 1
    assert calls == [("猫", ratio or "1:1", {} if model else {"model_id": "seedream-5.0-flash"})]
    assert len(saves) == 1 and not refunds
    assert saves[0][2] == "图片已生成。\n\n使用的描述（" + ("Qwen Image 3.0" if model else "Seedream 5.0 Flash") + "）：猫"
    assert result[0]["status"] == "generating_image" and result[0]["source"] == "tool"
    assert result[-3] == {"text": "图片已生成。"}
    assert result[-2]["speak"] is False and result[-1] == {"done": True}
    assert not any("reply_model" in e for e in result if isinstance(e, dict))
    assert traces[0]["image_planner"] == "draw" and traces[0]["image_source"] == "planner"
    assert "猫" not in json.dumps(traces, ensure_ascii=False)


@pytest.mark.parametrize("slot", ["main", "light"])
@pytest.mark.parametrize("fake_finish", ["tool_calls", "length", "content_filter"])
def test_platform_request_never_has_tools_and_ignores_unsolicited_calls(chat_harness, monkeypatch, slot, fake_finish):
    from persona import BASE_SAFETY_RULES
    chat, ctx, state, saves, calls, *_ = chat_harness
    monkeypatch.setattr(chat, "choose_model", lambda *a: slot)
    ctx.messages.append({"role": "system", "content": "朗读尾部\n\n" + BASE_SAFETY_RULES.strip()})
    state.sys_prompt_final = chat._final_system_prompt("persona", trailing_system=True)
    requests = []
    def opened(light, messages, **kwargs):
        requests.append((light, messages, kwargs))
        return iter(tool_blocks(finish=fake_finish)), slot == "light"
    monkeypatch.setattr(chat, "_create_stream_with_fallback", opened)
    result = asyncio.run(collect(chat.stream_normal(ctx, state)))
    assert requests[0][0] is (slot == "light")
    assert requests[0][2] == {"max_tokens": 700, "temperature": .9 if slot == "light" else 1.05,
        "frequency_penalty": .3 if slot == "light" else .4, "presence_penalty": .2 if slot == "light" else .4}
    assert not calls and saves[0][2] == "我来画。" and state.billable
    systems = [m["content"] for m in requests[0][1] if m["role"] == "system"]
    assert "\n".join(systems).count(BASE_SAFETY_RULES.strip()) == 1
    assert systems[-1].endswith(BASE_SAFETY_RULES.strip())
    assert result == [{"text": "我来画。"}, {"done": True}]


def test_stream_normal_is_restored_to_baseline():
    import inspect
    import subprocess
    import services.chat_service as chat
    baseline = subprocess.check_output(["git", "show", "7ac7b57:backend/services/chat_service.py"], text=True)
    start = baseline.index("async def stream_normal(")
    end = baseline.index("\n\nasync def _normal_followups", start)
    assert inspect.getsource(chat.stream_normal).rstrip() == baseline[start:end].rstrip()


@pytest.mark.parametrize("provider,model,mode", [
    (None, None, "planner"), ("anthropic", "claude-opus-5-5", "native"),
    ("anthropic", "claude-sonnet-5-5", "native"), ("anthropic", "claude-haiku-5-5", "native"),
    ("deepseek", "deepseek-v4-pro", "native"), ("deepseek", "deepseek-flash", "native"),
    ("deepseek", "deepseek-v4-pro-extra", "planner"), ("dashscope", "qwen3.8-flash", "planner"),
    ("moonshot", "kimi", "planner"), ("zhipu", "glm", "planner"), ("custom", "any", "planner"),
])
def test_r1_mode_selects_native_only_for_exact_providers(chat_harness, provider, model, mode):
    chat, ctx, *_ = chat_harness
    ctx.byok_config = {"enabled": True, "provider": provider, "model": model} if provider else None
    assert chat._image_tool_mode(ctx) == mode


@pytest.mark.parametrize("message,prescreen,planned", [
    ("你好", False, "no"), ("帮我写一段提示词", True, "no"),
    ("按上面那个做", True, "no"),
])
def test_r1_no_draw_routes_without_tools_or_image_candidate(chat_harness, monkeypatch, message, prescreen, planned):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    ctx.message = ctx.user_content = message
    ctx.messages = [{"role": "user", "content": message}]
    planner_requests, mode_calls, intents, requests, cleared = [], [], [], [], []
    async def planner(*args):
        planner_requests.append(args)
        return {"status": planned}
    monkeypatch.setattr(chat, "plan_image", planner)
    monkeypatch.setattr(chat, "image_planner_prescreen", lambda text, **kw: prescreen, raising=False)
    monkeypatch.setattr(chat, "get_pending", lambda *a: {"intent": "generate_image", "params": {}, "missing": ["prompt"]})
    monkeypatch.setattr(chat, "clear_pending", lambda *a: cleared.append(a))
    monkeypatch.setattr(chat, "detect_mode", lambda *a: mode_calls.append(a) or "friend")
    def recognize(*a):
        intents.append(a)
        return {"intent": "generate_image", "params": {"prompt": "wrong"}, "missing": []}
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", recognize)
    def opened(*a, **kw):
        requests.append(kw)
        return iter([block("文字回复"), block(finish="stop")]), False
    monkeypatch.setattr(chat, "_create_stream_with_fallback", opened)
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert len(planner_requests) == 1  # The pending image request also triggers the planner.
    assert len(mode_calls) == len(intents) == len(requests) == len(cleared) == 1
    assert "tools" not in requests[0] and not calls
    assert result == [{"text": "文字回复"}, {"done": True}]
    assert traces[0].get("image_planner") == planned and traces[0]["intent"] is None


@pytest.mark.parametrize("failure_type", ["TimeoutError", "JSONDecodeError", "InvalidDraw", "EmptyPrompt", "LongPrompt"])
def test_r1_planner_error_executes_legacy_route_byte_behavior(chat_harness, monkeypatch, failure_type):
    from copy import deepcopy
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    ctx.message = ctx.user_content = "画一只猫"
    ctx.messages = [{"role": "user", "content": ctx.message}]
    planner_requests, clears = [], []
    async def planner(*args):
        planner_requests.append(args)
        return {"status": "error", "exception_type": failure_type, "elapsed_ms": 8}
    monkeypatch.setattr(chat, "plan_image", planner)
    monkeypatch.setattr(chat, "clear_pending", lambda *a: clears.append(a))
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *a: {"intent": "generate_image", "params": {"prompt": "旧路由猫"}, "missing": []})
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **kw: (iter([block("旧回复"), block(finish="stop")]), False))
    outputs = []
    for enabled in ("0", "1"):
        monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", enabled)
        calls.clear()
        saves.clear()
        clears.clear()
        outputs.append((asyncio.run(collect(chat.run_chat(ctx, crisis=False))), deepcopy(calls), deepcopy(saves), deepcopy(clears)))
    assert outputs[0] == outputs[1]
    assert len(planner_requests) == 1 and traces[-1]["image_planner"] == "error"
    assert traces[-1]["image_planner_exception_type"] == failure_type
    assert traces[-1]["image_planner_elapsed_ms"] == 8
    assert "旧路由猫" not in json.dumps(traces, ensure_ascii=False)


def test_r1_planner_draw_precedes_existing_mirror_mode(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    ctx.message = ctx.user_content = "改成动漫风"
    monkeypatch.setattr(chat, "get_user_mode", lambda *a: {"mode": "mirror"})
    monkeypatch.setattr(chat, "detect_mode", lambda *a: pytest.fail("生图判断器应先于镜子模式识别"))
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert len(calls) == len(saves) == 1
    assert result[-1] == {"done": True} and traces[0]["image_source"] == "planner"


@pytest.mark.parametrize("enabled,crisis", [("0", False), ("1", "possible"), ("1", "high")])
def test_platform_disabled_request_identical_and_crisis_ignores_unsolicited_tools(chat_harness, monkeypatch, enabled, crisis):
    from safety import CRISIS_RESOURCE_NOTE
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.message = ctx.user_content = "你好" if crisis is False else "我有点想消失"
    ctx.messages = [{"role": "user", "content": ctx.message}]
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", enabled)
    kwargs = []
    def open_stream(*args, **kw):
        kwargs.append(kw)
        return iter(tool_blocks()), False
    monkeypatch.setattr(chat, "_create_stream_with_fallback", open_stream)
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=crisis)))
    assert kwargs == [{"max_tokens": 700, "temperature": 1.05, "frequency_penalty": 0.4, "presence_penalty": 0.4}]
    assert not calls
    assert sum(CRISIS_RESOURCE_NOTE in e.get("text", "") for e in result if isinstance(e, dict)) == int(crisis is not False)
    assert saves[0][2].count(CRISIS_RESOURCE_NOTE) == int(crisis is not False)


class ByokFakeStream:
    def __init__(self, text="", call=None, invalid=False):
        self.text = text
        self.tool_call = call
        self.tool_call_invalid = invalid
        self.closed = False
        self.refused = False
    def __iter__(self):
        return iter([block(self.text)] if self.text else [])
    def close(self):
        self.closed = True


@pytest.mark.parametrize("invalid,fail", [(False, False), (True, False), (False, True)])
def test_byok_tool_only_releases_slot_and_bills_image_only(chat_harness, monkeypatch, invalid, fail):
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.byok_config = {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "fake"}
    stream = ByokFakeStream(call={"name": "generate_image", "arguments": {"prompt": "猫"}}, invalid=invalid)
    request_kwargs, daily = [], []
    def open_stream(*args, **kwargs):
        request_kwargs.append(kwargs)
        return stream
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda *a, **kw: daily.append((a, kw)))
    monkeypatch.setattr(chat, "_BYOK_USERS", set())
    monkeypatch.setattr(chat, "_BYOK_ACTIVE", 0)
    original = chat.generate_image
    async def generate(*a, **kwargs):
        assert chat._BYOK_USERS == set() and chat._BYOK_ACTIVE == 0
        assert stream.closed
        if fail:
            raise chat.ImageGenerationError("工具错误")
        return await original(*a, **kwargs)
    monkeypatch.setattr(chat, "generate_image", generate)
    result = asyncio.run(collect(chat._stream_byok_reply(ctx, state, mirror=False, image_tool=True)))
    assert result[0]["reply_model"]["source"] == "byok"
    assert request_kwargs[0]["tools"] == "generate_image"
    assert daily == [(("byok_chat", ctx.user), {"hit": True})]
    assert state.billable is (not invalid and not fail)
    if invalid:
        assert not calls and len(saves) == 1 and "没能生成图片" in saves[0][2]
    elif fail:
        assert result[-1] == {"error": "工具错误"} and not saves
        assert "byok_error" not in state.trace
    else:
        assert len(calls) == 1 and len(saves) == 1
        assert sum("done" in e for e in result if isinstance(e, dict)) == 1
    chat.shutdown_byok_pool()


def test_byok_optional_parameter_off_mirror(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.byok_config = {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "fake"}
    request_kwargs = []
    def open_stream(*args, **kwargs):
        request_kwargs.append(kwargs)
        return ByokFakeStream("免费文字")
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda *a, **kw: None)
    asyncio.run(collect(chat._stream_byok_reply(ctx, state, mirror=True, image_tool=True)))
    assert "tools" not in request_kwargs[0]
    assert not calls and not state.billable
    chat.shutdown_byok_pool()


def test_r0_possible_information_pending_matches_disabled_route(chat_harness, monkeypatch):
    """R0: information/help context preserves exactly the legacy behavior."""
    from copy import deepcopy
    from safety import assess_crisis, is_informational_crisis_context
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    ctx.message = ctx.user_content = "帮我查下割腕的急救方法"
    ctx.messages = [{"role": "user", "content": ctx.message}]
    pending = {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
    cleared, requests = [], []
    assert assess_crisis(ctx.message) == "possible"
    assert is_informational_crisis_context(ctx.message)
    monkeypatch.setattr(chat, "get_pending", lambda *a: deepcopy(pending))
    monkeypatch.setattr(chat, "clear_pending", lambda *a: cleared.append(a))
    def opened(*a, **kwargs):
        requests.append(kwargs)
        return iter(tool_blocks()), False
    monkeypatch.setattr(chat, "_create_stream_with_fallback", opened)
    outcomes = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', enabled)
        cleared.clear()
        outcomes.append((asyncio.run(collect(chat.run_chat(ctx, crisis="possible"))), list(cleared)))
    assert outcomes[0] == outcomes[1]
    assert all('tools' not in kwargs for kwargs in requests)
    assert all(trace.get('image_source') != 'tool' for trace in traces)
    from safety import CRISIS_RESOURCE_NOTE
    assert sum(CRISIS_RESOURCE_NOTE in event.get('text', '') for event in outcomes[1][0] if isinstance(event, dict)) == 1


@pytest.mark.parametrize('provider,model,enabled', [
    (None, None, True), ('anthropic', 'claude-sonnet-5-5', True),
    ('dashscope', 'qwen3.8-omni-flash', True), ('dashscope', 'qwen3.8-max', True),
    ('dashscope', 'qwen3.8-flash', True), ('deepseek', 'deepseek-v4-pro', True),
    ('deepseek', 'deepseek-flash', True), ('custom', 'qwen3.8-max', True),
    ('moonshot', 'kimi', True), ('zhipu', 'glm', True),
    ('dashscope', 'qwen3.8-max-extra', True), ('deepseek', 'deepseek-chat', True),
])
def test_unique_gate_has_no_provider_allowlist(chat_harness, provider, model, enabled):
    chat, ctx, state, *_ = chat_harness
    if provider:
        ctx.byok_config = {'enabled': True, 'provider': provider, 'model': model}
    assert chat._image_tool_enabled(ctx, state) is enabled

@pytest.mark.parametrize('condition', ['off', 'image', 'has_image', 'high', 'possible', 'unreserved', 'error'])
def test_unique_gate_guards(chat_harness, monkeypatch, condition):
    chat, ctx, state, *_ = chat_harness
    if condition == 'off': monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', '0')
    elif condition == 'image': ctx.request_mode = 'image'
    elif condition == 'has_image': ctx.has_image = True
    elif condition in ('high', 'possible'): state.crisis_level = condition
    elif condition == 'unreserved': ctx.byok_unreserved = True
    elif condition == 'error': ctx.byok_error = ValueError('config')
    assert not chat._image_tool_enabled(ctx, state)


def test_gate_reads_env_each_call_and_warns_only_once(chat_harness, monkeypatch, caplog):
    chat, ctx, state, *_ = chat_harness
    monkeypatch.delenv('FIONA_CHAT_IMAGE_TOOL')
    monkeypatch.setattr(chat, '_IMAGE_TOOL_ENV_WARNED', False)
    assert chat._image_tool_enabled(ctx, state)
    monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', '0')
    assert not chat._image_tool_enabled(ctx, state)
    monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', 'invalid')
    assert chat._image_tool_enabled(ctx, state)
    assert chat._image_tool_enabled(ctx, state)
    assert len([r for r in caplog.records if 'FIONA_CHAT_IMAGE_TOOL' in r.message]) == 1

@pytest.mark.parametrize('kind', ['candidate', 'intent', 'intent_error', 'pending'])
def test_native_tool_route_uses_reply_model_only(chat_harness, monkeypatch, kind):
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    requests, cleared, modes = [], [], []
    ctx.message = ctx.user_content = '画一只猫' if kind == 'candidate' else '按上面的描述继续'
    ctx.messages = [{'role': 'user', 'content': ctx.message}]
    monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
    def detect(*a):
        modes.append(a)
        return 'mirror' if kind == 'candidate' else 'friend'
    monkeypatch.setattr(chat, 'detect_mode', detect)
    def recognize(*a):
        if kind == 'intent_error': raise RuntimeError('offline intent unavailable')
        return {'intent': 'generate_image', 'params': {'prompt': '错误的意图描述'}, 'missing': []}
    monkeypatch.setattr(chat, 'recognize_intent_with_fallback', recognize)
    monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []} if kind == 'candidate' else None)
    if kind == 'pending': monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
    def opened(config, messages, **kwargs):
        requests.append((messages, kwargs))
        return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
    monkeypatch.setattr(chat, 'open_reply_stream', opened)
    result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert len(calls) == 1 and calls[0][0] == '猫'
    assert requests[0][1]['tools'] and requests[0][0][0]['content'].strip()
    from persona import BASE_SAFETY_RULES
    assert requests[0][0][0]['content'].endswith(BASE_SAFETY_RULES.strip())
    assert sum('done' in e for e in result if isinstance(e, dict)) == 1
    if kind == 'candidate': assert not modes and cleared
    if kind == 'pending': assert cleared

    chat.shutdown_byok_pool()

@pytest.mark.parametrize('lead', ['', '我来画。'])
def test_byok_invalid_refusal_has_only_standard_notice(chat_harness, monkeypatch, lead):
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
    stream = ByokFakeStream(lead, call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=True)
    stream.refused = True
    stream.stop_reason = 'refusal'
    monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: stream)
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    result = asyncio.run(collect(chat._stream_byok_reply(ctx, state, mirror=False, image_tool=True)))
    expected = lead + ('\n\n' if lead else '') + '（这次没能生成图片，请再描述一次想画的画面。）'
    assert saves[0][2] == expected
    assert ''.join(e.get('text', '') for e in result if isinstance(e, dict)) == expected
    assert result[0]['reply_model'] and not calls and not state.billable
    chat.shutdown_byok_pool()


def test_unconfigured_tool_failure_still_has_tool_trace(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    monkeypatch.delenv('ARK_API_KEY')
    monkeypatch.delenv('DASHSCOPE_API_KEY')
    asyncio.run(collect(chat._stream_image_execution(ctx, state, '私有描述不进trace', source='tool')))
    assert state.trace['intent'] == state.trace['tool'] == 'generate_image'
    assert state.trace['image_source'] == 'tool'
    assert state.trace['model'] == 'main'
    assert '私有描述' not in json.dumps(state.trace, ensure_ascii=False)
    assert not saves and not calls and not state.billable

@pytest.mark.parametrize('provider,model', [
    ('custom', 'qwen3.8-max'), ('moonshot', 'kimi'), ('zhipu', 'glm'),
    ('dashscope', 'qwen3.8-max-extra'), ('deepseek', 'deepseek-chat'),
])
def test_disallowed_byok_route_keeps_old_request(chat_harness, monkeypatch, provider, model):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    ctx.message = ctx.user_content = '你好'
    ctx.byok_config = {'enabled': True, 'provider': provider, 'model': model, 'api_key': 'fake'}
    requests = []
    def opened(*a, **kwargs):
        requests.append(kwargs)
        return ByokFakeStream('免费文字', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
    monkeypatch.setattr(chat, 'open_reply_stream', opened)
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert len(requests) == 1 and 'tools' not in requests[0]
    assert not calls and len(refunds) == 1 and len(saves) == 1
    assert result[-1] == {'done': True} and traces[0].get('image_source') is None
    chat.shutdown_byok_pool()

@pytest.mark.parametrize('byok', [False, True])
def test_switch_off_route_keeps_requests_unchanged(chat_harness, monkeypatch, byok):
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.message = ctx.user_content = '你好'
    monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', '0')
    requests = []
    if byok:
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        def opened(*a, **kwargs):
            requests.append(kwargs)
            return ByokFakeStream('免费文字', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
        monkeypatch.setattr(chat, 'open_reply_stream', opened)
    else:
        def opened(*a, **kwargs):
            requests.append(kwargs)
            return iter(tool_blocks()), False
        monkeypatch.setattr(chat, '_create_stream_with_fallback', opened)
    asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert requests
    assert not calls and all('tools' not in request and 'tool_choice' not in request for request in requests)
    chat.shutdown_byok_pool()

@pytest.mark.parametrize('byok', [False, True])
@pytest.mark.parametrize('level,message', [('high', '我想自杀'), ('possible', '我有点想消失')])
def test_crisis_tools_ignored_resources_once_and_pending_preserved(chat_harness, monkeypatch, byok, level, message):
    from safety import CRISIS_RESOURCE_NOTE
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.message = ctx.user_content = message
    ctx.messages = [{'role': 'user', 'content': message}]
    ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
    cleared, requests = [], []
    monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
    monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    def platform(*a, **kwargs):
        requests.append(kwargs)
        return iter(tool_blocks(lead='陪你一起撑过这一刻。')), False
    def own_model(*a, **kwargs):
        requests.append(kwargs)
        return ByokFakeStream('陪你一起撑过这一刻。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
    monkeypatch.setattr(chat, '_create_stream_with_fallback', platform)
    monkeypatch.setattr(chat, 'open_reply_stream', own_model)
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=level)))
    assert not calls and not cleared and len(requests) == 1
    assert 'tools' not in requests[0] and 'tool_choice' not in requests[0]
    assert sum(CRISIS_RESOURCE_NOTE in e.get('text', '') for e in result if isinstance(e, dict)) == 1
    assert saves[0][2].count(CRISIS_RESOURCE_NOTE) == 1
    chat.shutdown_byok_pool()


def test_byok_tools_safe_system_once_including_readaloud(chat_harness, monkeypatch):
    from persona import BASE_SAFETY_RULES
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
    ctx.messages.append({'role': 'system', 'content': '朗读本次结果\n\n' + BASE_SAFETY_RULES.strip()})
    requests = []
    def opened(config, messages, **kwargs):
        requests.append(messages)
        return ByokFakeStream(call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
    monkeypatch.setattr(chat, 'open_reply_stream', opened)
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    systems = [m['content'] for m in requests[0] if m['role'] == 'system']
    assert '\n'.join(systems).count(BASE_SAFETY_RULES.strip()) == 1
    assert systems[-1].endswith(BASE_SAFETY_RULES.strip())
    assert len(calls) == len(saves) == 1 and result[0]['reply_model']
    chat.shutdown_byok_pool()


def test_image_pending_cancel_shortcut_and_weather_route(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    cleared, intents = [], []
    monkeypatch.setattr(chat, 'clear_pending', lambda *a: cleared.append(a))
    monkeypatch.setattr(chat, 'get_pending', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']})
    ctx.message = ctx.user_content = '算了'
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert result == [{'text': '好，已取消。'}, {'done': True}]
    assert len(cleared) == 1 and not calls
    ctx.message = ctx.user_content = '明天北京天气'
    monkeypatch.setattr(chat, 'get_pending', lambda *a: None)
    monkeypatch.setattr(chat, 'recognize_intent_with_fallback', lambda *a: {'intent': 'weather', 'params': {'city': '北京'}, 'missing': []})
    async def intent(*args):
        intents.append(args[2])
        yield chat._sse({'weather': True})
    monkeypatch.setattr(chat, 'stream_intent', intent)
    assert asyncio.run(collect(chat.run_chat(ctx, crisis=False))) == [{'weather': True}]
    assert intents[0]['intent'] == 'weather' and not calls


def test_mirror_non_candidate_does_not_receive_tools(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    ctx.message = ctx.user_content = '按上面那个继续'
    monkeypatch.setattr(chat, 'detect_mode', lambda *a: 'mirror')
    monkeypatch.setattr(chat, 'get_user_mode', lambda *a: {})
    kwargs = []
    def opened(*a, **kw):
        kwargs.append(kw)
        return iter(tool_blocks()), False
    monkeypatch.setattr(chat, '_create_stream_with_fallback', opened)
    asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert not calls and kwargs and 'tools' not in kwargs[0]


@pytest.mark.parametrize('byok', [False, True])
@pytest.mark.parametrize('outcome', ['success', 'invalid', 'error', 'busy', 'missing', 'deleted'])
def test_reserved_turn_settlement_and_single_image(chat_harness, monkeypatch, byok, outcome):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    if byok:
        ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
        monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
        monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}}, invalid=outcome == 'invalid'))
    else:
        monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)), False))
        if outcome == 'invalid':
            async def unavailable_planner(*args):
                return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
            monkeypatch.setattr(chat, 'plan_image', unavailable_planner)
    deleted = []
    monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
    if outcome == 'error':
        async def fail(*a, **kw): raise chat.ImageGenerationError('错误', category='moderation')
        monkeypatch.setattr(chat, 'generate_image', fail)
    elif outcome == 'busy': chat._IMAGE_GENERATION_USERS.add(ctx.user)
    elif outcome == 'missing':
        monkeypatch.delenv('ARK_API_KEY')
        monkeypatch.delenv('DASHSCOPE_API_KEY')
    elif outcome == 'deleted':
        original = chat.generate_image
        async def generate(*a, **kw):
            generated = await original(*a, **kw)
            async def vanished(*a): raise chat.ResourceNotFound()
            monkeypatch.setattr(chat, '_ensure_active_conversation', vanished)
            return generated
        monkeypatch.setattr(chat, 'generate_image', generate)
    monkeypatch.setattr(chat, 'clear_pending', lambda *a: None)
    result = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert chat.STRAWBERRY_COST_PER_REPLY == 10
    # An unavailable planner falls back to the legacy route. A delivered
    # platform text reply still settles its ordinary reservation.
    assert refunds == ([] if outcome == 'success' or (outcome == 'invalid' and not byok) else [(ctx.user, 10)])
    if outcome == 'success':
        assert len(calls) == 1
        assert sum('generated_image' in event for event in result if isinstance(event, dict)) == 1
        assert '图片已生成。' in saves[0][2] and '使用的描述' in saves[0][2]
        assert sum('done' in event for event in result if isinstance(event, dict)) == 1
        assert chat.STRAWBERRY_COST_PER_REPLY == 10 and not refunds
    else:
        assert len(calls) == int(outcome == 'deleted')
        assert sum('done' in event for event in result if isinstance(event, dict)) == int(outcome == 'invalid')
    assert sum('error' in event for event in result if isinstance(event, dict)) == (0 if outcome in ('success', 'invalid') else 1)
    assert not any('tool' in event for event in result if isinstance(event, dict))
    if outcome in ('success', 'invalid'): assert len(saves) == 1
    else: assert not saves
    if outcome == 'deleted': assert deleted == ['/uploads/generated_test.png']
    if byok and outcome == 'error': assert 'byok_error' not in traces[0]
    chat.shutdown_byok_pool()


def test_client_disconnect_cleans_attachment_refunds_and_preserves_unsaved_lead(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks()), False))
    deleted = []
    monkeypatch.setattr(chat, 'delete_uploaded_files', deleted.extend)
    async def scenario():
        entered = asyncio.Event()
        original = chat.generate_image
        async def generate(*a, **kw):
            generated = await original(*a, **kw)
            async def wait_after_generation(*a):
                entered.set()
                await asyncio.Event().wait()
            monkeypatch.setattr(chat, '_ensure_active_conversation', wait_after_generation)
            return generated
        monkeypatch.setattr(chat, 'generate_image', generate)
        stream = chat.run_chat(ctx, reserved=True, crisis=False)
        assert json.loads((await anext(stream))[6:])['source'] == 'tool'
        pending = asyncio.create_task(anext(stream))
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError): await pending
        await stream.aclose()
    asyncio.run(scenario())
    assert deleted == ['/uploads/generated_test.png'] and refunds == [(ctx.user, 10)]
    assert not saves and ctx.user not in chat._IMAGE_GENERATION_USERS


def test_tool_success_event_order_including_heartbeat(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(tool_blocks()), False))
    original = chat.generate_image
    async def slow(*a, **kw):
        await asyncio.sleep(.015)
        return await original(*a, **kw)
    monkeypatch.setattr(chat, 'generate_image', slow)
    monkeypatch.setattr(chat, '_IMAGE_HEARTBEAT_SECONDS', .003)
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert result[0]['status'] == 'generating_image'
    assert ': generating-image\n\n' in result
    kinds = [next(iter(e)) if isinstance(e, dict) else 'heartbeat' for e in result]
    assert kinds.index('heartbeat') < kinds.index('generated_image')
    assert result[-3] == {'text': '图片已生成。'}
    assert result[-2] == {'text': '\n\n使用的描述（Seedream 5.0 Flash）：猫', 'speak': False}
    assert result[-1] == {'done': True}


def test_zero_balance_byok_keeps_legacy_image_guard(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    monkeypatch.setenv('DEV_MODE', '0')
    ctx.byok_unreserved = True
    ctx.message = ctx.user_content = '画一只猫'
    ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
    monkeypatch.setattr(chat, 'explicit_image_intent', lambda *a: {'intent': 'generate_image', 'params': {}, 'missing': []})
    monkeypatch.setattr(chat, 'recognize_intent_with_fallback', lambda *a: {'intent': 'generate_image', 'params': {'prompt': '猫'}, 'missing': []})
    result = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert result == [{'error': chat.strawberry_insufficient_message()}]
    assert not calls and not saves and not refunds
    assert traces[0]['error'] == 'InsufficientStrawberries'

@pytest.mark.parametrize('byok', [False, True])
@pytest.mark.parametrize('outcome', ['image', 'invalid', 'error', 'text'])
def test_http_paid_turn_reserves_once_and_settles_real_balance(client, dev_headers, monkeypatch, byok, outcome):
    """In-process ASGI with a real isolated SQLite balance; every provider is fake."""
    import sqlite3
    from pathlib import Path
    import database
    import routers.chat as router
    import services.chat_service as chat
    from auth import create_token
    from rate_limit import limiter
    from utils import media
    monkeypatch.setattr(limiter, 'enabled', False)
    monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
    monkeypatch.setattr(chat, '_IMAGE_GENERATION_USERS', set())
    username = dev_headers['X-Dev-User']
    conversation = client.post('/conversations', headers=dev_headers, json={}).json()['conversation']['id']
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute('UPDATE users SET strawberry_balance = 20 WHERE username = ?', (username,))
    version = asyncio.run(database.get_session_version(username))
    headers = {'Authorization': 'Bearer ' + create_token(username, version)}
    monkeypatch.setenv('DEV_MODE', '0')
    config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'} if byok else None
    async def config_read(*a): return config
    monkeypatch.setattr(chat, 'get_internal_config', config_read)
    reservations, refunds, generated = [], [], []
    original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
    async def reserve(*a):
        reservations.append(a)
        return await original_reserve(*a)
    async def refund(*a):
        refunds.append(a)
        return await original_refund(*a)
    monkeypatch.setattr(router, 'reserve_strawberries', reserve)
    monkeypatch.setattr(chat, 'refund_strawberries', refund)
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    async def planner(*args):
        if outcome == 'text':
            return {'status': 'no'}
        if outcome == 'invalid':
            return {'status': 'error', 'exception_type': 'ValueError', 'elapsed_ms': 1}
        return {'status': 'draw', 'prompt': '猫'}
    monkeypatch.setattr(chat, 'plan_image', planner)
    if byok:
        call = None if outcome == 'text' else {'name': 'generate_image', 'arguments': {'prompt': '猫'}}
        monkeypatch.setattr(chat, 'open_reply_stream', lambda *a, **kw: ByokFakeStream('我来画。', call=call, invalid=outcome == 'invalid'))
    else:
        chunks = [block('普通文字'), block(finish='stop')] if outcome == 'text' else tool_blocks(raw='{"prompt":' if outcome == 'invalid' else None, multiple=True)
        monkeypatch.setattr(chat, '_create_stream_with_fallback', lambda *a, **kw: (iter(chunks), False))
    async def image(prompt, ratio, **kwargs):
        generated.append((prompt, ratio, kwargs))
        if outcome == 'error': raise chat.ImageGenerationError('工具生图失败')
        Path(media.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
        (Path(media.UPLOADS_DIR) / 'generated_billing.png').write_bytes(b'isolated-fake-image')
        return {'image_path': '/uploads/generated_billing.png', 'model': 'fake-renderer'}
    monkeypatch.setattr(chat, 'generate_image', image)
    response = client.post('/chat', headers=headers, json={'conversation_id': conversation, 'message': '按上面的提示词画', 'image_model': 'qwen-image-3.0'})
    assert response.status_code == 200
    result = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    billed = outcome == 'image' or (outcome in ('text', 'invalid') and not byok)
    assert reservations == [(username, 10)]
    assert refunds == ([] if billed else [(username, 10)])
    assert asyncio.run(database.get_strawberry_balance(username)) == (10 if billed else 20)
    history = client.get(f'/conversations/{conversation}/messages', headers=headers).json()['messages']
    assistants = [row for row in history if row['role'] == 'assistant']
    assert len(assistants) == (0 if outcome == 'error' else 1)
    if outcome == 'image':
        assert generated == [('猫', '1:1', {'model_id': 'seedream-5.0-flash'})]
        assert assistants[0]['content'] == ('我来画。\n\n' if byok else '') + '图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：猫'
    if outcome in ('invalid', 'text'): assert not generated
    if outcome == 'error':
        assert not any('done' in event for event in result)
    else:
        assert sum('done' in event for event in result) == 1
    chat.shutdown_byok_pool()

@pytest.mark.parametrize('byok', [False, True])
def test_r0_information_crisis_reaches_reply_without_tools(chat_harness, monkeypatch, byok):
    from safety import CRISIS_RESOURCE_NOTE, assess_crisis, is_informational_crisis_context
    chat, ctx, state, saves, calls, refunds, traces = chat_harness
    message = '帮我查下割腕的急救方法？'
    assert assess_crisis(message) == 'possible' and is_informational_crisis_context(message)
    ctx.message = ctx.user_content = message
    ctx.messages = [{'role': 'user', 'content': message}]
    if byok: ctx.byok_config = {'enabled': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'api_key': 'fake'}
    pending = {'intent': 'generate_image', 'params': {}, 'missing': ['prompt']}
    cleared, requests = [], []
    current_pending = [pending.copy()]
    monkeypatch.setattr(chat, 'get_pending', lambda *a: current_pending[0])
    def clear(*a):
        cleared.append(a)
        current_pending[0] = None
    monkeypatch.setattr(chat, 'clear_pending', clear)
    monkeypatch.setattr(chat, 'check_chat_daily_cap', lambda *a, **kw: None)
    def platform(*a, **kw):
        requests.append(kw)
        return iter(tool_blocks()), False
    def own(*a, **kw):
        requests.append(kw)
        return ByokFakeStream('我在。', call={'name': 'generate_image', 'arguments': {'prompt': '猫'}})
    monkeypatch.setattr(chat, '_create_stream_with_fallback', platform)
    monkeypatch.setattr(chat, 'open_reply_stream', own)
    outcomes = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('FIONA_CHAT_IMAGE_TOOL', enabled)
        cleared.clear()
        current_pending[0] = pending.copy()
        outcomes.append((asyncio.run(collect(chat.run_chat(ctx, crisis='possible'))), list(cleared)))
    assert outcomes[0] == outcomes[1] and cleared
    assert not calls and len(requests) == 2 and all('tools' not in kw for kw in requests)
    assert sum(CRISIS_RESOURCE_NOTE in event.get('text', '') for event in outcomes[1][0] if isinstance(event, dict)) == 1
    chat.shutdown_byok_pool()




def test_requested_qwen_unconfigured_falls_back_to_seedream_before_request(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    monkeypatch.delenv('DASHSCOPE_API_KEY')
    result = asyncio.run(collect(chat._stream_image_execution(ctx, state, '猫', source='tool', model_id='qwen-image-3.0')))
    assert calls == [('猫', '1:1', {'model_id': 'seedream-5.0-flash'})]
    assert state.trace['image_model'] == 'seedream-5.0-flash' and state.trace['image_fallback'] is True
    assert result[-2] == {'text': '（Qwen Image 3.0 暂未配置，这次用 Seedream 5.0 Flash 生成。）', 'speak': False}
    assert saves[0][2].endswith(result[-2]['text'])


def test_seedream_response_unavailable_does_not_retry_other_provider(chat_harness, monkeypatch):
    chat, ctx, state, saves, calls, *_ = chat_harness
    attempts = []
    async def unavailable(*a, **kw):
        attempts.append((a, kw))
        raise chat.ImageGenerationError('面板错误文案', provider_status=403, category='unavailable')
    monkeypatch.setattr(chat, 'generate_image', unavailable)
    result = asyncio.run(collect(chat._stream_image_execution(ctx, state, '猫', source='tool', lead_text='我来画。')))
    assert attempts == [(('猫', '1:1'), {'model_id': 'seedream-5.0-flash'})]
    assert result[-1] == {'error': 'Seedream 暂时用不了（可能未开通或欠费），可以说『用千问画』改用 Qwen Image 3.0。'}
    assert not saves and not state.billable and state.trace['provider_status'] == 403


@pytest.mark.parametrize("decision", ["draw", "no"])
def test_r2_image_pending_answer_calls_planner_without_current_prescreen(chat_harness, monkeypatch, decision):
    chat, ctx, state, saves, images, refunds, traces = chat_harness
    ctx.message = ctx.user_content = "一只橘猫在窗台上晒太阳"
    ctx.messages = [{"role": "user", "content": ctx.message}]
    pending = [{"intent": "generate_image", "params": {}, "missing": ["prompt"]}]
    planner_calls, clears = [], []
    monkeypatch.setattr(chat, "image_planner_prescreen", lambda *args, **kwargs: False)
    monkeypatch.setattr(chat, "explicit_image_intent", lambda *args: None)
    monkeypatch.setattr(chat, "get_pending", lambda *args: pending[0])
    def clear(*args):
        clears.append(args)
        pending[0] = None
    monkeypatch.setattr(chat, "clear_pending", clear)
    async def planner(history, message):
        planner_calls.append((history, message))
        return {"status": decision, "prompt": "窗台上的橘猫"}
    monkeypatch.setattr(chat, "plan_image", planner)
    events = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert planner_calls == [(ctx.history, ctx.message)]
    assert clears == [(ctx.state_key,)] and pending[0] is None
    assert len(images) == int(decision == "draw")
    assert len(saves) == 1 and not refunds
    assert sum("done" in event for event in events) == 1
    assert traces[-1]["image_planner"] == decision
    if decision == "draw":
        assert saves[0][2] == "图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：窗台上的橘猫"
        assert traces[-1]["image_source"] == "planner"
    else:
        assert saves[0][2] == "普通回复"


@pytest.mark.parametrize("message", ["算了", "取消吧", "不用了。", "不画了！", "不要了", "停止", "别画了"])
def test_r2_pending_cancel_does_not_call_planner(chat_harness, monkeypatch, message):
    chat, ctx, state, saves, images, refunds, traces = chat_harness
    ctx.message = ctx.user_content = message
    pending = [{"intent": "generate_image", "params": {}, "missing": ["prompt"]}]
    clears = []
    monkeypatch.setattr(chat, "get_pending", lambda *args: pending[0])
    def clear(*args):
        clears.append(args)
        pending[0] = None
    monkeypatch.setattr(chat, "clear_pending", clear)
    async def forbidden(*args):
        pytest.fail("取消已有生图请求不得调用判断器")
    monkeypatch.setattr(chat, "plan_image", forbidden)
    events = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert events == [{"text": "好，已取消。"}, {"done": True}]
    assert clears == [(ctx.state_key,)] and pending[0] is None
    assert len(saves) == 1 and saves[0][2] == "好，已取消。"
    assert not images and refunds == [(ctx.user, 10)]
    assert "image_planner" not in traces[-1]


@pytest.mark.parametrize("assistant", [
    "使用的描述（Seedream 5.0 Flash）：窗边的猫", "想生成什么画面？", "你想画什么呀？",
    "这是整理好的提示词：a cat", "Here is the PROMPT: a cat",
])
def test_r2_last_assistant_image_followup_calls_planner(chat_harness, monkeypatch, assistant):
    chat, ctx, state, saves, images, refunds, traces = chat_harness
    ctx.message = ctx.user_content = "就按这个来"
    ctx.history = [{"role": "assistant", "content": assistant}, {"role": "user", "content": "就这样"}]
    assert not chat.image_planner_prescreen(ctx.message, explicit=False)
    planner_calls = []
    async def planner(history, message):
        planner_calls.append((history, message))
        return {"status": "draw", "prompt": "一只猫"}
    monkeypatch.setattr(chat, "plan_image", planner)
    events = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert planner_calls == [(ctx.history, ctx.message)]
    assert len(images) == len(saves) == 1 and events[-1] == {"done": True}
    assert traces[-1]["image_planner"] == "draw"


@pytest.mark.parametrize("history", [
    [], [{"role": "assistant", "content": "今天过得怎么样？"}],
    [{"role": "assistant", "content": "使用的描述：一只猫"}, {"role": "assistant", "content": "今天过得怎么样？"}],
    [{"role": "user", "content": "提示词"}, {"role": "assistant", "content": "今天过得怎么样？"}],
])
def test_r2_unrelated_last_assistant_does_not_call_planner(chat_harness, monkeypatch, history):
    chat, ctx, state, saves, images, refunds, traces = chat_harness
    ctx.message = ctx.user_content = "挺好的"
    ctx.history = history
    async def forbidden(*args):
        pytest.fail("本轮与最后一条助手回复均无生图线索时不得调用判断器")
    monkeypatch.setattr(chat, "plan_image", forbidden)
    events = asyncio.run(collect(chat.run_chat(ctx, crisis=False)))
    assert events == [{"text": "普通回复"}, {"done": True}]
    assert len(saves) == 1 and not images
    assert "image_planner" not in traces[-1]


def test_r2_planner_draw_clears_search_pending_before_next_turn(chat_harness, monkeypatch):
    chat, ctx, state, saves, images, refunds, traces = chat_harness
    pending = [{"intent": "web_search", "params": {}, "missing": ["query"]}]
    clears, searches, planner_calls = [], [], []
    monkeypatch.setattr(chat, "get_pending", lambda *args: pending[0])
    def clear(*args):
        clears.append(args)
        pending[0] = None
    monkeypatch.setattr(chat, "clear_pending", clear)
    async def planner(history, message):
        planner_calls.append(message)
        return {"status": "draw", "prompt": "猫"} if len(planner_calls) == 1 else {"status": "no"}
    monkeypatch.setattr(chat, "plan_image", planner)
    async def search(ctx, state, remaining):
        searches.append(remaining)
        yield chat._sse({"done": True})
    monkeypatch.setattr(chat, "stream_pending", search)
    first = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert pending[0] is None and clears == [(ctx.state_key,)]
    assert len(images) == 1 and first[-1] == {"done": True}
    ctx.history = [{"role": "assistant", "content": saves[-1][2]}]
    ctx.message = ctx.user_content = "哇好可爱"
    ctx.messages = [{"role": "user", "content": ctx.message}]
    second = asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False)))
    assert second == [{"text": "普通回复"}, {"done": True}]
    assert planner_calls == ["按上面的提示词画", "哇好可爱"]
    assert not searches and len(images) == 1 and len(saves) == 2


@pytest.mark.parametrize("lead", ["", "我来画。"])
def test_r2_invalid_image_notice_only_separates_existing_lead(chat_harness, lead):
    chat, ctx, state, saves, images, *_ = chat_harness
    state.full_response = lead
    notice = "（这次没能生成图片，请再描述一次想画的画面。）"
    text = ("\n\n" if lead else "") + notice
    events = asyncio.run(collect(chat._stream_invalid_image_tool(ctx, state)))
    assert events == [{"text": text}, {"done": True}]
    assert saves[0][2] == lead + text and not state.billable
    assert not images


def test_r2_execution_records_planner_source_before_first_event(chat_harness):
    chat, ctx, state, saves, images, *_ = chat_harness
    async def execute():
        stream = chat._stream_image_execution(ctx, state, "猫", source="tool", image_source="planner")
        first = await anext(stream)
        assert state.trace["image_source"] == "planner"
        assert json.loads(first[6:])["source"] == "tool"
        remaining = await collect(stream)
        assert remaining[-1] == {"done": True}
    asyncio.run(execute())
    assert state.trace["image_source"] == "planner" and len(images) == len(saves) == 1


def test_r2_cancel_and_followup_patterns_are_exact_and_shared():
    import inspect
    import services.chat_service as chat
    assert chat.IMAGE_PENDING_CANCEL_PATTERN == r"^(?:算了|取消|不用了|不画了|不要了|停止|别画了)[吧了。！!\s]*$"
    assert chat.IMAGE_PLANNER_FOLLOWUP_PATTERN == "使用的描述|想生成什么画面|画|提示词|prompt"
    assert "IMAGE_PENDING_CANCEL_PATTERN" in inspect.getsource(chat._run_chat_with_image_tool)
    assert "IMAGE_PENDING_CANCEL_PATTERN" in inspect.getsource(chat.run_chat)
