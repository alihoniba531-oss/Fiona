"""R1 BYOK planner routing, billing and offline acceptance-plugin contracts."""
import asyncio
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
from types import SimpleNamespace as NS

import pytest


PLANNER_CONFIGS = [
    ("dashscope", "qwen3.8-omni-flash"),
    ("dashscope", "qwen-other"),
    ("moonshot", "kimi-k2.5"),
    ("zhipu", "glm-5"),
    ("custom", "private-model"),
    ("deepseek", "deepseek-v4-pro-extra"),
    ("deepseek", "deepseek-other"),
]
NATIVE_CONFIGS = [
    ("anthropic", "claude-opus-5-5"),
    ("anthropic", "claude-sonnet-5-5"),
    ("anthropic", "claude-haiku-5-5"),
    ("deepseek", "deepseek-v4-pro"),
    ("deepseek", "deepseek-flash"),
]


async def collect(stream):
    return [json.loads(item[6:]) if item.startswith("data: ") else item async for item in stream]


class Reply:
    def __init__(self, text="普通回复", *, call=None):
        self.text = text
        self.tool_call = call
        self.tool_call_invalid = False
        self.refused = False
        self.closed = False

    def __iter__(self):
        return iter([NS(choices=[NS(delta=NS(content=self.text))])] if self.text else [])

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    monkeypatch.setenv("ARK_API_KEY", "test-ark")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope")
    def blocked(*args, **kwargs):
        raise AssertionError("R1 tests must not open network connections")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield
    import services.chat_service as chat
    chat.shutdown_byok_pool()


@pytest.fixture
def harness(monkeypatch):
    import services.chat_service as chat
    ctx = chat.ChatContext("r1-byok-user", "把上面的提示词画出来", False, None,
                           "把上面的提示词画出来", [{"role": "assistant", "content": "a cat"}],
                           2, "人设", [{"role": "user", "content": "把上面的提示词画出来"}],
                           conversation_id="r1", image_model="qwen-image-3.0")
    saved, generated, refunds, traces, daily, replies, planner_calls = [], [], [], [], [], [], []
    async def active(*args):
        return None
    async def save(*args, **kwargs):
        saved.append((args, kwargs))
        return 1
    async def image(prompt, ratio, **kwargs):
        assert chat._BYOK_ACTIVE == 0 and not chat._BYOK_USERS
        generated.append((prompt, ratio, kwargs))
        return {"image_path": "/uploads/generated_r1.png", "model": "fake-renderer"}
    async def refund(*args):
        refunds.append(args)
    async def log(*args, **kwargs):
        traces.append(kwargs["payload"].copy())
    async def noop(*args):
        return None
    def open_reply(*args, **kwargs):
        replies.append((args, kwargs))
        return Reply()
    def cap(*args, **kwargs):
        daily.append((args, kwargs))
        return None
    monkeypatch.setattr(chat, "_ensure_active_conversation", active)
    monkeypatch.setattr(chat, "save_message", save)
    monkeypatch.setattr(chat, "generate_image", image)
    monkeypatch.setattr(chat, "refund_strawberries", refund)
    monkeypatch.setattr(chat, "log_event", log)
    monkeypatch.setattr(chat, "_normal_followups", noop)
    monkeypatch.setattr(chat, "open_reply_stream", open_reply)
    monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
    monkeypatch.setattr(chat, "choose_model", lambda *args: "main")
    monkeypatch.setattr(chat, "detect_mode", lambda *args: "friend")
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *args: {"intent": None, "params": {}, "missing": []})
    monkeypatch.setattr(chat, "explicit_image_intent", lambda *args: None)
    monkeypatch.setattr(chat, "get_pending", lambda *args: None)
    monkeypatch.setattr(chat, "clear_pending", lambda *args: None)
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())
    return NS(chat=chat, ctx=ctx, saved=saved, generated=generated, refunds=refunds,
              traces=traces, daily=daily, replies=replies, planner_calls=planner_calls)


def configure(h, provider, model):
    h.ctx.byok_config = {"enabled": True, "provider": provider, "model": model, "api_key": "fake"}


def set_planner(h, monkeypatch, decision):
    async def planner(history, message):
        h.planner_calls.append((history, message))
        return decision
    monkeypatch.setattr(h.chat, "plan_image", planner, raising=False)


@pytest.mark.parametrize("provider,model", PLANNER_CONFIGS + NATIVE_CONFIGS)
def test_r1_byok_gate_and_exact_mode(harness, provider, model):
    h = harness
    configure(h, provider, model)
    assert h.chat._image_tool_enabled(h.ctx, h.chat.ChatState(trace={})) is True
    assert h.chat._image_tool_mode(h.ctx) == ("native" if (provider, model) in NATIVE_CONFIGS else "planner")


@pytest.mark.parametrize("provider,model", PLANNER_CONFIGS)
@pytest.mark.parametrize("outcome", ["draw", "generation_error"])
def test_r1_planner_draw_never_calls_user_model_or_daily_limit(harness, monkeypatch, provider, model, outcome):
    h = harness
    configure(h, provider, model)
    set_planner(h, monkeypatch, {"status": "draw", "prompt": "私密标识不应进入 trace 的猫", "model": "qwen-image-3.0", "aspect_ratio": "9:16"})
    def unexpected(*args, **kwargs):
        pytest.fail("planner draw must skip reply, intent recognition and detect_mode")
    monkeypatch.setattr(h.chat, "open_reply_stream", unexpected)
    monkeypatch.setattr(h.chat, "recognize_intent_with_fallback", unexpected)
    monkeypatch.setattr(h.chat, "detect_mode", unexpected)
    if outcome == "generation_error":
        async def fail(*args, **kwargs):
            raise h.chat.ImageGenerationError("画面审核失败", category="moderation")
        monkeypatch.setattr(h.chat, "generate_image", fail)
    events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
    assert h.planner_calls == [(h.ctx.history, h.ctx.message)]
    assert not h.daily and not h.replies
    assert not any("reply_model" in item for item in events if isinstance(item, dict))
    assert h.traces[0]["image_planner"] == "draw"
    assert h.traces[0]["image_source"] == "planner"
    assert h.traces[0]["model"] is None
    assert "私密标识" not in json.dumps(h.traces, ensure_ascii=False)
    if outcome == "draw":
        assert h.generated == [("私密标识不应进入 trace 的猫", "9:16", {})]
        assert h.refunds == []
        assert len(h.saved) == 1
        assert h.saved[0][0][2] == "图片已生成。\n\n使用的描述（Qwen Image 3.0）：私密标识不应进入 trace 的猫"
        assert events[0]["source"] == "tool"
        assert events[-1] == {"done": True}
        assert not events[-3]["text"].startswith("\n")
    else:
        assert events == [{"status": "generating_image", "message": "正在用 Qwen Image 3.0 生成图片…", "source": "tool"},
                          {"error": "这次画面描述没通过内容审核，换个说法再让我画吧。"}]
        assert not h.saved
        assert h.refunds == [(h.ctx.user, 10)]
        assert "byok_error" not in h.traces[0]


@pytest.mark.parametrize("provider,model", PLANNER_CONFIGS)
def test_r1_planner_no_calls_reply_without_tools_and_refunds_text(harness, monkeypatch, provider, model):
    h = harness
    configure(h, provider, model)
    set_planner(h, monkeypatch, {"status": "no"})
    events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
    assert len(h.planner_calls) == 1 and len(h.replies) == 1
    assert "tools" not in h.replies[0][1] and "tool_choice" not in h.replies[0][1]
    assert h.daily == [(("byok_chat", h.ctx.user), {"hit": True})]
    assert h.refunds == [(h.ctx.user, 10)] and not h.generated
    assert h.traces[0]["image_planner"] == "no"
    assert events[-1] == {"done": True} and len(h.saved) == 1


@pytest.mark.parametrize("provider,model", PLANNER_CONFIGS)
def test_r1_direct_byok_reply_cannot_enable_native_tools_for_planner_models(harness, monkeypatch, provider, model):
    h = harness
    configure(h, provider, model)
    def open_reply(*args, **kwargs):
        h.replies.append((args, kwargs))
        return Reply(call={"name": "generate_image", "arguments": {"prompt": "非原生工具不得执行"}})
    monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
    state = h.chat.ChatState(trace={}, sys_prompt_final="人设")
    events = asyncio.run(collect(h.chat._stream_byok_reply(h.ctx, state, mirror=False, image_tool=True)))
    assert "tools" not in h.replies[0][1] and "tool_choice" not in h.replies[0][1]
    assert not h.generated and not state.billable
    assert len(h.saved) == 1 and h.saved[0][0][2] == "普通回复"
    assert events[-1] == {"done": True}


@pytest.mark.parametrize("provider,model", PLANNER_CONFIGS)
def test_r1_planner_error_matches_switch_off_old_image_route(harness, monkeypatch, provider, model):
    h = harness
    configure(h, provider, model)
    h.ctx.message = h.ctx.user_content = "画一只猫"
    set_planner(h, monkeypatch, {"status": "error", "exception_type": "TimeoutError", "elapsed_ms": 8000})
    result = {"intent": "generate_image", "params": {"prompt": "旧路由猫"}, "missing": []}
    monkeypatch.setattr(h.chat, "explicit_image_intent", lambda *args: result)
    monkeypatch.setattr(h.chat, "recognize_intent_with_fallback", lambda *args: result)
    outcomes = []
    for switch in ("0", "1"):
        monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", switch)
        h.saved.clear()
        h.generated.clear()
        events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
        outcomes.append((events, list(h.saved), list(h.generated)))
    assert outcomes[0] == outcomes[1]
    assert h.planner_calls == [(h.ctx.history, h.ctx.message)]
    assert h.traces[-1]["image_planner"] == "error"
    assert not h.replies and not h.daily


@pytest.mark.parametrize("provider,model", NATIVE_CONFIGS)
def test_r1_native_still_calls_reply_tools_without_planner(harness, monkeypatch, provider, model):
    h = harness
    configure(h, provider, model)
    def unexpected(*args, **kwargs):
        pytest.fail("native mode must not call planner")
    monkeypatch.setattr(h.chat, "plan_image", unexpected, raising=False)
    def open_reply(*args, **kwargs):
        h.replies.append((args, kwargs))
        return Reply("", call={"name": "generate_image", "arguments": {"prompt": "原生猫"}})
    monkeypatch.setattr(h.chat, "open_reply_stream", open_reply)
    events = asyncio.run(collect(h.chat.run_chat(h.ctx, reserved=True, crisis=False)))
    assert h.replies[0][1]["tools"] == "generate_image"
    assert h.daily == [(("byok_chat", h.ctx.user), {"hit": True})]
    assert h.generated == [("原生猫", "1:1", {"model_id": "seedream-5.0-flash"})]
    assert events[0]["reply_model"]["source"] == "byok"
    assert not h.refunds


@pytest.mark.parametrize("provider,model", [("dashscope", "qwen3.8-flash"), ("custom", "private-model")])
@pytest.mark.parametrize("outcome", ["draw", "generation_error", "no"])
def test_r1_http_byok_planner_single_reservation_and_real_balance(client, dev_headers, monkeypatch, provider, model, outcome):
    import database
    import routers.chat as router
    import services.chat_service as chat
    from auth import create_token
    from rate_limit import limiter
    from utils import media
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())
    user = dev_headers["X-Dev-User"]
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE users SET strawberry_balance = 20 WHERE username = ?", (user,))
    headers = {"Authorization": "Bearer " + create_token(user, asyncio.run(database.get_session_version(user)))}
    monkeypatch.setenv("DEV_MODE", "0")
    config = {"enabled": True, "provider": provider, "model": model, "api_key": "fake"}
    async def internal(*args):
        return config
    async def planner(*args):
        return {"status": "no"} if outcome == "no" else {"status": "draw", "prompt": "余额测试猫"}
    monkeypatch.setattr(chat, "get_internal_config", internal)
    monkeypatch.setattr(chat, "plan_image", planner, raising=False)
    reservations, refunds, replies, daily, generated = [], [], [], [], []
    original_reserve, original_refund = router.reserve_strawberries, chat.refund_strawberries
    async def reserve(*args):
        reservations.append(args)
        return await original_reserve(*args)
    async def refund(*args):
        refunds.append(args)
        return await original_refund(*args)
    def open_reply(*args, **kwargs):
        replies.append(kwargs)
        assert "tools" not in kwargs
        return Reply()
    def cap(*args, **kwargs):
        daily.append((args, kwargs))
        return None
    async def image(prompt, ratio, **kwargs):
        assert chat._BYOK_ACTIVE == 0 and not chat._BYOK_USERS
        generated.append((prompt, ratio, kwargs))
        if outcome == "generation_error":
            raise chat.ImageGenerationError("模拟生图失败")
        path = Path(media.UPLOADS_DIR) / "generated_r1_balance.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"isolated-r1-fake-image")
        return {"image_path": "/uploads/generated_r1_balance.png", "model": "fake-renderer"}
    monkeypatch.setattr(router, "reserve_strawberries", reserve)
    monkeypatch.setattr(chat, "refund_strawberries", refund)
    monkeypatch.setattr(chat, "open_reply_stream", open_reply)
    monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
    monkeypatch.setattr(chat, "generate_image", image)
    response = client.post("/chat", headers=headers, json={"conversation_id": conversation, "message": "把上面的提示词画出来", "image_model": "qwen-image-3.0"})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert reservations == [(user, 10)]
    assert refunds == ([] if outcome == "draw" else [(user, 10)])
    assert asyncio.run(database.get_strawberry_balance(user)) == (10 if outcome == "draw" else 20)
    assert len(replies) == (1 if outcome == "no" else 0)
    assert daily == ([(("byok_chat", user), {"hit": True})] if outcome == "no" else [])
    assert sum("reply_model" in event for event in events) == (1 if outcome == "no" else 0)
    history = client.get(f"/conversations/{conversation}/messages", headers=headers).json()["messages"]
    assistants = [row for row in history if row["role"] == "assistant"]
    assert len(assistants) == (0 if outcome == "generation_error" else 1)
    if outcome == "draw":
        assert generated == [("余额测试猫", "1:1", {"model_id": "seedream-5.0-flash"})]
        assert assistants[0]["content"] == "图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：余额测试猫"


def acceptance_plugin():
    path = Path(__file__).resolve().parents[2] / "docs/tasks/2026-10-10-chat-image-tool/image_planner_stub.py"
    spec = importlib.util.spec_from_file_location("r1_image_planner_acceptance_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r1_acceptance_plugin_only_stubs_baseline_tests(monkeypatch):
    plugin = acceptance_plugin()
    import services.chat_service as chat
    async def actual(*args):
        return {"status": "draw", "prompt": "new test"}
    monkeypatch.setattr(chat, "plan_image", actual, raising=False)
    new = NS(node=NS(path=Path("backend/tests/test_byok_planner_r1.py")))
    plugin.image_planner_acceptance_stub.__wrapped__(monkeypatch, new)
    assert chat.plan_image is actual
    old = NS(node=NS(path=Path("backend/tests/test_byok_chat.py")))
    plugin.image_planner_acceptance_stub.__wrapped__(monkeypatch, old)
    assert asyncio.run(chat.plan_image([], "画猫")) == {"status": "no"}
    monkeypatch.setattr(chat, "plan_image", actual)
    assert asyncio.run(chat.plan_image([], "画猫"))["status"] == "draw"


@pytest.mark.parametrize("name", ["test_chat_image_tool.py", "test_byok_image_tool.py", "test_chat_image_tool_docs.py", "test_chat_image_tool_frontend.py", "test_image_planner.py", "test_byok_planner_r1.py"])
def test_r1_acceptance_plugin_preserves_all_task_tests(name):
    assert acceptance_plugin().is_task_test(Path("backend/tests") / name)


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_r1_acceptance_plugin_blocks_network_without_attempting_connect(monkeypatch, method):
    plugin = acceptance_plugin()
    attempted = []
    def real_network(*args):
        attempted.append(True)
        raise AssertionError("must never reach original connect")
    monkeypatch.setattr(socket.socket, method, real_network)
    plugin.offline_network_guard.__wrapped__(monkeypatch)
    dummy = NS(family=socket.AF_INET)
    with pytest.raises(RuntimeError, match="真实网络"):
        getattr(socket.socket, method)(dummy, ("203.0.113.1", 443))
    assert not attempted
