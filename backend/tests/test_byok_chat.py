"""Offline BYOK routing, billing, crisis and admission regressions."""
import asyncio
import base64
import json
import socket
import sqlite3
import threading
import urllib.request
from types import SimpleNamespace

import httpcore
import httpx
import openai
import pytest
import requests

from _fakes import FakeStream
from byok.errors import ByokUnavailableError, NeedsReentryError, error_message
from safety import CRISIS_RESOURCE_NOTE


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    from utils import safe_http
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(safe_http, "_open_pinned", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", blocked)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_unix_socket", blocked)
    from byok.crypto import FORBIDDEN_ENV
    for name in FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIONA_BYOK_SECRET", base64.urlsafe_b64encode(b"b" * 32).decode())
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    from rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()
    assert not attempted, "network"


class Reply(FakeStream):
    def __init__(self, chunks=None, *, refused=False, thread_names=None):
        super().__init__(chunks)
        self.refused = refused
        self.stop_reason = "refusal" if refused else "end_turn"
        self.closed = False
        self.thread_names = thread_names

    def __iter__(self):
        if self.thread_names is not None:
            self.thread_names.append(threading.current_thread().name)
        yield from super().__iter__()

    def close(self):
        if self.thread_names is not None:
            self.thread_names.append(threading.current_thread().name)
        self.closed = True


def events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def setup(client, headers, monkeypatch, *, balance=10, enabled=True):
    import database
    from auth import create_token
    from byok.store import save_config, set_enabled
    user = headers["X-Dev-User"]
    conversation = client.post("/conversations", headers=headers, json={}).json()["conversation"]["id"]
    asyncio.run(save_config(user, provider="anthropic", model="claude-opus-5-5", api_key="sk-private-test-key"))
    if not enabled:
        asyncio.run(set_enabled(user, False))
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (balance, user))
    version = asyncio.run(database.get_session_version(user))
    monkeypatch.setenv("DEV_MODE", "0")
    return user, conversation, {"Authorization": f"Bearer {create_token(user, version)}"}


def balance(user):
    import database
    return asyncio.run(database.get_strawberry_balance(user))


def stub_reply(monkeypatch, *, chunks=None, refused=False, failure=None):
    import services.chat_service as chat
    calls, platform, names, replies = [], [], [], []

    def open_stream(*args, **kwargs):
        calls.append(kwargs)
        names.append(threading.current_thread().name)
        if failure is not None:
            raise failure
        reply = Reply(chunks, refused=refused, thread_names=names)
        replies.append(reply)
        return reply

    def platform_stream(*args, **kwargs):
        platform.append(1)
        return FakeStream(), False

    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", platform_stream)
    return calls, platform, names, replies


@pytest.mark.parametrize("mode", ["friend", "mirror"])
@pytest.mark.parametrize("amount", [0, 5, 10])
def test_reply_uses_dedicated_pool_and_refunds(client, dev_headers, monkeypatch, mode, amount):
    import services.chat_service as chat
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
    calls, platform, names, replies = stub_reply(monkeypatch)
    accounting = []
    monkeypatch.setattr(chat.token_budget, "add", lambda *a: accounting.append(1))
    result = events(client.post("/chat", headers=headers, json={"message": "今天挺轻松", "conversation_id": conversation}))
    assert len(calls) == 1 and calls[0]["mirror"] is (mode == "mirror")
    assert platform == [] and accounting == []
    assert result[0] == {"reply_model": {"source": "byok", "label": "Claude · claude-opus-5-5"}}
    assert result[1:] == [{"text": "测试"}, {"text": "回复"}, {"done": True}]
    assert balance(user) == amount
    assert replies[0].closed and all(name.startswith("fiona-byok") for name in names)


@pytest.mark.parametrize("branch", ["weather", "pending", "image", "vision"])
@pytest.mark.parametrize("amount", [0, 5])
def test_unreserved_blocks_paid_branches_and_preserves_pending(client, dev_headers, monkeypatch, branch, amount):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending
    from database import strawberry_insufficient_message
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
    key = (user, conversation)
    pending = {"intent": "weather", "params": {}, "missing": ["city"]}
    if branch == "pending":
        set_pending(key, pending)
    elif branch == "image":
        pending = {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
        set_pending(key, pending)
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
        "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
    })
    invoked = []
    monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: invoked.append("tool"))
    async def generate(*a, **k):
        invoked.append("image")
        raise AssertionError("paid image")
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: invoked.append("vision"))
    caps = []
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda *a, **k: caps.append((a, k)))
    payload = {"message": "北京" if branch == "pending" else "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
    if branch == "vision":
        payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    result = events(client.post("/chat", headers=headers, json=payload))
    assert result == [{"error": strawberry_insufficient_message()}]
    assert invoked == [] and caps == [] and balance(user) == amount
    if branch in {"pending", "image"}:
        assert get_pending(key) == pending


@pytest.mark.parametrize("mode", ["image", "image_edit"])
def test_zero_balance_explicit_image_modes_keep_precheck(client, dev_headers, monkeypatch, mode):
    import services.chat_service as chat
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=0)
    payload = {"message": "画一只猫", "mode": mode, "conversation_id": conversation}
    if mode == "image_edit":
        payload["reference_image_path"] = "/uploads/reference_" + "a" * 32 + ".png"
    calls, platform, *_ = stub_reply(monkeypatch)
    result = events(client.post("/chat", headers=headers, json=payload))
    assert result == [{"error": "草莓不足，内测期间请联系管理员补充 🍓"}]
    assert not calls and not platform and balance(user) == 0


@pytest.mark.parametrize("branch", ["weather", "image", "vision"])
def test_paid_branches_still_cost_ten(client, dev_headers, monkeypatch, branch):
    import services.chat_service as chat
    from pathlib import Path
    from utils import media
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    calls, platform, *_ = stub_reply(monkeypatch)
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
        "intent": "generate_image" if branch == "image" else "weather", "params": {"city": "北京"}, "missing": [],
    })
    monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: {"type": "card", "subtype": "weather", "points": ["晴"]})
    async def generate(*a, **k):
        path = "/uploads/generated_" + "f" * 32 + ".png"
        Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
        return {"image_path": path, "model": "platform-image"}
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat.QWEN_CLIENT.chat.completions, "create", lambda *a, **k: FakeStream())
    payload = {"message": "画一只猫" if branch == "image" else "北京天气", "conversation_id": conversation}
    if branch == "vision":
        payload["image_base64"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    result = events(client.post("/chat", headers=headers, json=payload))
    assert result[-1] == {"done": True}
    assert not calls and not platform and balance(user) == 0


@pytest.mark.parametrize("amount", [0, 10])
def test_high_crisis_keeps_platform_or_free_resources(client, dev_headers, monkeypatch, amount):
    import database
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
    calls, platform, *_ = stub_reply(monkeypatch)
    result = events(client.post("/chat", headers=headers, json={"message": "我想死", "conversation_id": conversation}))
    assert not calls
    if amount:
        assert platform == [1] and balance(user) == 0
    else:
        assert not platform
        assert result == [{"crisis": True}, {"text": CRISIS_RESOURCE_NOTE}, {"done": True}]
        assert asyncio.run(database.count_messages(user, conversation_id=conversation)) == 0


@pytest.mark.parametrize("failure", [None, RuntimeError("private-upstream-body")])
def test_possible_crisis_resource_once_before_error(client, dev_headers, monkeypatch, failure):
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
    result = events(client.post("/chat", headers=headers, json={"message": "活着没意思", "conversation_id": conversation}))
    assert calls and not platform and balance(user) == 10
    resource = [i for i, event in enumerate(result) if CRISIS_RESOURCE_NOTE in event.get("text", "")]
    assert len(resource) == 1
    if failure:
        assert resource[0] < next(i for i, event in enumerate(result) if "error" in event)
    else:
        assert result[-1] == {"done": True}


class ProviderFailure(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__("sk-private-test-key https://private.example.net claude-opus-5-5")


@pytest.mark.parametrize("failure", [ProviderFailure(401), ProviderFailure(404), ProviderFailure(429), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
def test_error_mapping_no_fallback_refund_or_secret(client, dev_headers, monkeypatch, capsys, failure):
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    calls, platform, *_ = stub_reply(monkeypatch, failure=failure)
    response = client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation})
    assert events(response) == [{"error": error_message(failure)}]
    assert calls and not platform and balance(user) == 10
    output = response.text + capsys.readouterr().out
    assert "sk-private-test-key" not in output and "private.example.net" not in output and "claude-opus-5-5" not in output


@pytest.mark.parametrize("refused,partial", [(False, False), (True, False), (True, True)])
def test_empty_and_refusal_semantics(client, dev_headers, monkeypatch, refused, partial):
    import database
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    stub_reply(monkeypatch, chunks=[("部分", None)] if partial else [], refused=refused)
    result = events(client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation}))
    messages = asyncio.run(database.get_messages(user, conversation_id=conversation))
    if partial:
        assert result[-2:] == [{"text": "（Claude 中止了这条回复）"}, {"done": True}]
        assert messages[-1]["content"] == "部分（Claude 中止了这条回复）"
    else:
        assert len(result) == 1 and "error" in result[0]
        assert all(message["role"] == "user" for message in messages)
    assert balance(user) == 10


def test_daily_cap_and_dev_mode_bypass(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from rate_limit import limiter
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    monkeypatch.setenv("FIONA_DAILY_BYOK_CHATS", "1")
    monkeypatch.setattr(limiter, "enabled", True)
    calls, *_ = stub_reply(monkeypatch)
    payload = {"message": "正常聊天", "conversation_id": conversation}
    assert events(client.post("/chat", headers=headers, json=payload))[-1] == {"done": True}
    denied = events(client.post("/chat", headers=headers, json=payload))
    assert denied == [{"error": "今天用自带模型聊天的次数已用完，明天再试，或在输入框下方改用平台"}]
    assert len(calls) == 1 and balance(user) == 10
    monkeypatch.setenv("DEV_MODE", "1")
    assert events(client.post("/chat", headers=dev_headers, json=payload))[-1] == {"done": True}
    assert len(calls) == 2


@pytest.mark.parametrize("changed", ["delete", "disable", "reentry"])
def test_unreserved_rechecks_config_before_reply(client, dev_headers, monkeypatch, changed):
    import services.chat_service as chat
    import database
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=0)
    calls, platform, *_ = stub_reply(monkeypatch)
    def detect(*args, **kwargs):
        with sqlite3.connect(database.DB_PATH) as db:
            if changed == "delete":
                db.execute("DELETE FROM user_model_configs WHERE username = ?", (user,))
            elif changed == "disable":
                db.execute("UPDATE user_model_configs SET enabled = 0 WHERE username = ?", (user,))
            else:
                db.execute("UPDATE user_model_configs SET key_ciphertext = ? WHERE username = ?", (b"corrupt", user))
        return "friend"
    monkeypatch.setattr(chat, "detect_mode", detect)
    assert events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation})) == [{"error": "草莓不足，内测期间请联系管理员补充 🍓"}]
    assert not calls and not platform


def test_disabled_config_keeps_exact_platform_events(client, dev_headers, monkeypatch):
    user, conversation, headers = setup(client, dev_headers, monkeypatch, enabled=False)
    calls, platform, *_ = stub_reply(monkeypatch)
    result = events(client.post("/chat", headers=headers, json={"message": "普通聊天", "conversation_id": conversation}))
    assert result == [{"text": "测试"}, {"text": "回复"}, {"done": True}]
    assert not calls and platform == [1] and balance(user) == 0


def test_route_unreserved_flag_does_not_access_context_fields(client, dev_headers, monkeypatch):
    import routers.chat as route
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=0)
    captured = []
    async def context(*args, **kwargs):
        captured.append(kwargs)
        return SimpleNamespace()
    async def run(*args, **kwargs):
        captured.append(kwargs)
        yield 'data: {"done": true}\n\n'
    monkeypatch.setattr(route, "build_context", context)
    monkeypatch.setattr(route, "run_chat", run)
    assert events(client.post("/chat", headers=headers, json={"message": "普通聊天", "conversation_id": conversation})) == [{"done": True}]
    assert all(item["byok_unreserved"] is True for item in captured)


@pytest.mark.parametrize("same_user", [True, False])
def test_admission_has_no_queued_streams(monkeypatch, same_user):
    import services.chat_service as chat
    from rate_limit import limiter
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("FIONA_BYOK_MAX_STREAMS", "1" if not same_user else "8")
    monkeypatch.setattr(limiter, "enabled", False)
    async def noop(*a, **k):
        return None
    async def saved(ctx, state):
        state.response_saved = True
    monkeypatch.setattr(chat, "_save_response", saved)
    monkeypatch.setattr(chat, "_normal_followups", noop)
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Blocking(Reply):
        def __iter__(self):
            entered.set()
            assert release.wait(5)
            yield from super().__iter__()
    def open_stream(*a, **k):
        calls.append(k)
        return Blocking()
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    config = {"provider": "anthropic", "model": "claude-opus-5-5", "enabled": True, "api_key": "test-key"}
    def context(user):
        return chat.ChatContext(user, "聊聊", False, None, "聊聊", [], 0, "system", [], byok_config=config)
    async def collect(user):
        return [json.loads(event[6:]) async for event in chat.stream_normal(context(user), chat.ChatState(trace={}))]
    async def scenario():
        first = asyncio.create_task(collect("first"))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            second, third = await asyncio.gather(collect("first" if same_user else "second"), collect("first" if same_user else "third"))
        finally:
            release.set()
        successful = await first
        return successful, second, third
    successful, second, third = asyncio.run(scenario())
    expected = "你的模型正在回复上一条消息，请稍候" if same_user else "自带模型通道繁忙，请稍后再试"
    assert second == third == [{"error": expected}]
    assert successful[-1] == {"done": True} and len(calls) == 1
    assert not chat._BYOK_USERS and chat._BYOK_ACTIVE == 0
    chat.shutdown_byok_pool()


def test_enabled_byok_does_not_take_over_avatar_exchange(client, dev_headers, monkeypatch):
    import services.exchange_service as exchanges
    import services.chat_service as chat
    from byok.store import save_config
    from rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    participants = []
    for username in ("byok_exchange_one", "byok_exchange_two"):
        headers = {"X-Dev-User": username}
        response = client.put("/agents/me", headers=headers, json={"display_name": username, "bio": "公开介绍", "is_public": True})
        assert response.status_code == 200
        participants.append((headers, response.json()["agent"]["id"]))
        asyncio.run(save_config(username, provider="anthropic", model="claude-opus-5-5", api_key="sk-exchange-private-key"))
    byok_calls, platform_calls = [], []
    def byok(*args, **kwargs):
        byok_calls.append(1)
        raise AssertionError("exchange must remain on platform")
    async def model(*args, **kwargs):
        platform_calls.append(kwargs)
        return {"content": "平台交流回复", "input_tokens": 12, "output_tokens": 8, "provider": "main", "model": "qwen-platform"}
    monkeypatch.setattr(chat, "open_reply_stream", byok)
    monkeypatch.setattr(exchanges, "generate_exchange_reply", model)
    invitation = client.post("/agent-exchanges", headers=participants[0][0], json={"target_agent_id": participants[1][1], "topic": "公开交流", "max_turns": 2})
    assert invitation.status_code == 201, invitation.text
    exchange_id = invitation.json()["exchange"]["id"]
    assert client.post(f"/agent-exchanges/{exchange_id}/accept", headers=participants[1][0]).status_code == 200
    client.portal.call(exchanges.wait_for_exchange, exchange_id)
    final = client.get(f"/agent-exchanges/{exchange_id}", headers=participants[0][0])
    assert final.json()["exchange"]["status"] == "completed", final.text
    assert platform_calls and not byok_calls


@pytest.mark.parametrize("broken", ["ciphertext", "secret", "read"])
def test_configuration_failure_is_not_absent_or_platform(client, dev_headers, monkeypatch, broken):
    import database
    import services.chat_service as chat
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    calls, platform, *_ = stub_reply(monkeypatch)
    traces = []
    async def capture(*a, **k):
        traces.append(k["payload"].copy())
    monkeypatch.setattr(chat, "log_event", capture)
    if broken == "ciphertext":
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("UPDATE user_model_configs SET key_ciphertext = ?", (b"corrupt",))
        expected = error_message(NeedsReentryError())
    elif broken == "secret":
        monkeypatch.delenv("FIONA_BYOK_SECRET")
        expected = error_message(ByokUnavailableError())
    else:
        async def read(*a, **k):
            raise sqlite3.OperationalError("private DB detail")
        monkeypatch.setattr(chat, "get_internal_config", read)
        expected = error_message(sqlite3.OperationalError())
    result = events(client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation}))
    assert result == [{"error": expected}]
    assert not calls and not platform and balance(user) == 10
    assert traces[-1]["model"] == "byok" and traces[-1]["byok_provider"] == "anthropic"
    assert traces[-1]["error"] in {"NeedsReentryError", "ByokUnavailableError", "OperationalError"}


def test_disconnected_byok_stream_closes_and_releases_slot(monkeypatch):
    import services.chat_service as chat
    from rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "friend")
    monkeypatch.setattr(chat, "get_pending", lambda *a, **k: None)
    monkeypatch.setattr(chat, "recognize_intent_with_fallback", lambda *a, **k: {"intent": None})
    traces = []
    async def log(*a, **k):
        traces.append(k)
    monkeypatch.setattr(chat, "log_event", log)
    replies = []
    def open_stream(*a, **k):
        reply = Reply()
        replies.append(reply)
        return reply
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    config = {"provider": "anthropic", "model": "claude-opus-5-5", "enabled": True, "api_key": "test-key"}
    ctx = chat.ChatContext("disconnect_user", "聊天", False, None, "聊天", [], 0, "system", [], byok_config=config)
    async def scenario():
        stream = chat.run_chat(ctx, crisis=False)
        first = await anext(stream)
        assert "reply_model" in first
        assert ctx.user in chat._BYOK_USERS
        await stream.aclose()
    asyncio.run(scenario())
    assert replies[0].closed and not chat._BYOK_USERS and chat._BYOK_ACTIVE == 0 and traces


@pytest.mark.parametrize("amount", [0, 10])
@pytest.mark.parametrize("case", [
    "image_topic", "image_cancel", "image_fill", "weather_cancel", "weather_fill",
    "weather_chat", "image_new_tool", "image_thanks", "image_discussion",
    "image_question", "manual_mirror", "missing_edit_reference",
])
def test_r1_pending_api_free_actions_and_paid_guards(client, dev_headers, monkeypatch, amount, case):
    import database
    import services.chat_service as chat
    from intent_router import get_pending, set_pending
    from pathlib import Path
    from utils import media
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
    key = (user, conversation)
    calls, platform, *_ = stub_reply(monkeypatch)
    caps, generated, tools = [], [], []

    def classify(_client, message, history):
        if message == "帮我画张图":
            return {"intent": "generate_image", "params": {}, "missing": ["prompt"]}
        if message == "查一下北京明天天气":
            return {"intent": "weather", "params": {"city": "北京"}, "missing": []}
        return {"intent": None, "params": {}, "missing": []}

    def cap(kind, username, *, hit):
        caps.append((kind, hit))
        return None

    def execute(intent, params):
        tools.append((intent, dict(params)))
        return {"type": "card", "subtype": "weather", "points": ["天气晴"]}

    async def image(*a, **k):
        generated.append(1)
        path = "/uploads/generated_" + "e" * 32 + ".png"
        Path(media.UPLOADS_DIR, path.rsplit("/", 1)[1]).write_bytes(b"image")
        return {"image_path": path, "model": "platform-image"}

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "check_chat_daily_cap", cap)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "generate_image", image)
    weather_pending = case.startswith("weather_") or case == "manual_mirror"
    pending = {"intent": "weather" if weather_pending else "generate_image", "params": {}, "missing": ["city" if weather_pending else "prompt"]}
    if case == "image_new_tool":
        # Manufacture the pending through the real paid route, then lower balance.
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("UPDATE users SET strawberry_balance = 10 WHERE username = ?", (user,))
        seed = events(client.post("/chat", headers=headers, json={"message": "帮我画张图", "conversation_id": conversation}))
        assert seed[-1] == {"done": True} and get_pending(key) == pending
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (amount, user))
        caps.clear()
    else:
        set_pending(key, pending)
    messages = {
        "image_topic": "换个话题", "image_cancel": "算了", "image_fill": "一只橘猫",
        "weather_cancel": "算了", "weather_fill": "上海", "weather_chat": "我今天心情不好",
        "image_new_tool": "查一下北京明天天气", "image_thanks": "谢谢",
        "image_discussion": "生图多少钱", "image_question": "你觉得呢？",
        "manual_mirror": "聊聊今天", "missing_edit_reference": "把刚才的图片天空改成黄昏",
    }
    if case == "manual_mirror":
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
        monkeypatch.setattr(chat, "get_user_mode", lambda *a, **k: {"last_trigger": "manual_request"})
    result = events(client.post("/chat", headers=headers, json={"message": messages[case], "conversation_id": conversation}))
    paid = case in {"image_fill", "weather_fill", "image_new_tool"}
    if paid and amount == 0:
        assert result == [{"error": database.strawberry_insufficient_message()}]
        assert not generated and not tools and not calls and not platform
        assert all(kind != "weather" or hit is False for kind, hit in caps)
        assert get_pending(key) == pending
        assert balance(user) == amount
    else:
        assert get_pending(key) is None
        assert result[-1] == {"done": True}
        if case in {"image_cancel", "weather_cancel"}:
            assert result == [{"text": "好，已取消。"}, {"done": True}]
            assert not calls
        elif case == "missing_edit_reference":
            assert "请先点击" in result[0]["text"] and not calls
        elif paid:
            assert bool(generated) is (case == "image_fill")
            assert bool(tools) is (case != "image_fill")
            assert not calls
            if tools:
                assert ("weather", True) in caps
        else:
            assert len(calls) == 1 and "reply_model" in result[0]
        assert balance(user) == (0 if paid else amount)


@pytest.mark.parametrize("kind", ["weather", "generate_image"])
def test_r1_pending_missing_parameter_remains_free(client, dev_headers, monkeypatch, kind):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=0)
    key = (user, conversation)
    pending = {"intent": kind, "params": {}, "missing": ["city", "other"] if kind == "weather" else ["prompt", "other"]}
    set_pending(key, pending)
    caps = []
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
    result = events(client.post("/chat", headers=headers, json={"message": "上海" if kind == "weather" else "一只橘猫", "conversation_id": conversation}))
    assert result[-1] == {"done": True} and "text" in result[0]
    saved_pending = get_pending(key)
    assert saved_pending["missing"] == ["other"]
    assert saved_pending["params"]["city" if kind == "weather" else "prompt"] == ("上海" if kind == "weather" else "一只橘猫")
    assert caps == ([("weather", False)] if kind == "weather" else []) and balance(user) == 0


@pytest.mark.parametrize("mode", ["friend", "mirror"])
def test_r1_reply_persistence_failure_uses_platform_error(client, dev_headers, monkeypatch, capsys, mode):
    import services.chat_service as chat
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    calls, platform, *_ = stub_reply(monkeypatch)
    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
    original = chat.save_message
    async def fail_assistant(username, role, *a, **k):
        if role == "assistant":
            return False
        return await original(username, role, *a, **k)
    monkeypatch.setattr(chat, "save_message", fail_assistant)
    result = events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation}))
    assert result[-1] == {"error": "服务暂时不可用，请稍后再试"}
    assert calls and not platform and balance(user) == 10
    assert "[byok] reply failed" not in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["opening", "reading"])
@pytest.mark.parametrize("worker_error", [False, True])
def test_r1_cancel_interrupts_before_waiting_for_worker(monkeypatch, phase, worker_error):
    import services.chat_service as chat
    from rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("DEV_MODE", "0")
    entered, release = threading.Event(), threading.Event()
    controls, replies, saved, delivered = [], [], [], []
    async def save(*a, **k):
        saved.append(1)
    monkeypatch.setattr(chat, "_save_response", save)

    class Control:
        def __init__(self):
            self.aborted = False
            controls.append(self)
        def abort(self):
            self.aborted = True
            release.set()

    class Hanging(Reply):
        def __iter__(self):
            if phase == "reading":
                entered.set()
                assert release.wait(5)
                if worker_error:
                    raise httpx.ReadError("interrupted read")
            yield from super().__iter__()

    def open_stream(*a, control=None, **k):
        reply = Hanging()
        replies.append(reply)
        if phase == "opening":
            entered.set()
            assert release.wait(5)
            if worker_error:
                reply.close()
                raise httpx.RemoteProtocolError("interrupted handshake")
        return reply

    monkeypatch.setattr(chat, "ReplyStreamControl", Control, raising=False)
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    config = {"provider": "anthropic", "model": "claude-opus-5-5", "enabled": True, "api_key": "test-key"}
    ctx = chat.ChatContext("cancel_user", "聊天", False, None, "聊天", [], 0, "system", [], byok_config=config)
    async def scenario():
        async def consume():
            async for event in chat.stream_normal(ctx, chat.ChatState(trace={})):
                delivered.append(json.loads(event[6:]))
        task = asyncio.create_task(consume())
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            await asyncio.wait({task}, timeout=0.3)
            timely = task.done()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
        assert timely, "cancel must abort the blocking worker before waiting"
        assert task.cancelled(), "interrupted worker exceptions must preserve cancellation"
        assert controls and controls[0].aborted
    asyncio.run(scenario())
    assert replies[0].closed and not chat._BYOK_USERS and chat._BYOK_ACTIVE == 0
    assert not saved and not any("error" in event for event in delivered)


@pytest.mark.parametrize("possible", [False, True])
def test_r1_generated_image_direct_unreserved_guard(monkeypatch, possible):
    import services.chat_service as chat
    from database import strawberry_insufficient_message
    monkeypatch.setenv("DEV_MODE", "0")
    invoked = []
    async def active(*a, **k):
        invoked.append("active")
    async def image(*a, **k):
        invoked.append("image")
        return {"image_path": "/uploads/generated_" + "d" * 32 + ".png", "model": "platform-image"}
    async def save(ctx, state, **kwargs):
        state.response_saved = True
    monkeypatch.setattr(chat, "_ensure_active_conversation", active)
    monkeypatch.setattr(chat, "generate_image", image)
    monkeypatch.setattr(chat, "_save_response", save)
    ctx = chat.ChatContext("direct_guard", "画猫", False, None, "画猫", [], 0, "system", [], byok_unreserved=True)
    state = chat.ChatState(trace={}, crisis_level="possible" if possible else None)
    async def scenario():
        return [json.loads(event[6:]) async for event in chat.stream_generated_image(ctx, state, "画猫")]
    result = asyncio.run(scenario())
    expected = [{"text": "\n\n" + CRISIS_RESOURCE_NOTE}] if possible else []
    assert result == expected + [{"error": strawberry_insufficient_message()}]
    assert invoked == [] and not state.billable and not chat._IMAGE_GENERATION_USERS


@pytest.mark.parametrize("amount", [0, 5])
def test_r1_route_config_read_failure_stops_before_context_or_user_message(client, dev_headers, monkeypatch, amount):
    import database
    import routers.chat as route
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=amount)
    calls, platform, *_ = stub_reply(monkeypatch)
    built = []
    original = route.build_context
    async def read(*a, **k):
        raise sqlite3.OperationalError("private-read-error")
    async def context(*a, **k):
        built.append(1)
        return await original(*a, **k)
    monkeypatch.setattr(route, "has_enabled_config", read)
    monkeypatch.setattr(route, "build_context", context)
    before = asyncio.run(database.count_messages(user, conversation_id=conversation))
    result = events(client.post("/chat", headers=headers, json={"message": "正常聊天", "conversation_id": conversation}))
    assert result == [{"error": database.strawberry_insufficient_message()}]
    assert not built and not calls and not platform
    assert asyncio.run(database.count_messages(user, conversation_id=conversation)) == before
    assert balance(user) == amount


@pytest.mark.parametrize("mode", ["friend", "mirror"])
def test_r1_deleted_conversation_during_reply_is_platform_failure(client, dev_headers, monkeypatch, capsys, mode):
    import database
    import services.chat_service as chat
    from agent_store import delete_conversation
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    calls, platform, *_ = stub_reply(monkeypatch)
    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)
    class DeletedReply(Reply):
        def __iter__(self):
            for chunk in super().__iter__():
                yield chunk
                # The first chunk has reached the consumer before deletion.
                if not calls:
                    raise AssertionError("BYOK stream did not open")
                asyncio.run(delete_conversation(user, conversation))
                break
    def open_stream(*a, **k):
        calls.append(1)
        return DeletedReply()
    monkeypatch.setattr(chat, "open_reply_stream", open_stream)
    result = events(client.post("/chat", headers=headers, json={"message": "聊天", "conversation_id": conversation}))
    assert result[:2] == [{"reply_model": {"source": "byok", "label": "Claude · claude-opus-5-5"}}, {"text": "测试"}]
    assert result[-1] == {"error": "服务暂时不可用，请稍后再试"}
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM conversations WHERE id = ?", (conversation,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation,)).fetchone()[0] == 0
    assert not platform and balance(user) == 10
    assert "[byok] reply failed" not in capsys.readouterr().out


@pytest.mark.parametrize("configured", [False, True])
def test_r1_platform_weather_pending_keeps_legacy_city_handling(client, dev_headers, monkeypatch, configured):
    import services.chat_service as chat
    from byok.store import delete_config
    from intent_router import get_pending, set_pending
    user, conversation, headers = setup(client, dev_headers, monkeypatch, enabled=False)
    if not configured:
        asyncio.run(delete_config(user))
    key = (user, conversation)
    set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
    calls, platform, *_ = stub_reply(monkeypatch)
    tools, caps = [], []
    card = {"type": "card", "subtype": "weather", "points": ["旧平台天气结果"]}
    def execute(intent, params):
        tools.append((intent, dict(params)))
        return card
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
    result = events(client.post("/chat", headers=headers, json={"message": "今天心情不好", "conversation_id": conversation}))
    assert result == [{"card": card}, {"done": True}]
    assert tools == [("weather", {"city": "今天心情不好"})]
    assert caps == [("weather", True)]
    assert not calls and not platform and get_pending(key) is None and balance(user) == 0


def test_r2_paid_weather_pending_routing_matches_platform(client, dev_headers, monkeypatch):
    """BYOK must not reinterpret a pending city's valid text as conversation."""
    import database
    import services.chat_service as chat
    from byok.store import delete_config
    from intent_router import get_pending, set_pending
    snapshots = []
    for enabled in (False, True):
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch)
        if not enabled:
            asyncio.run(delete_config(user))
        key = (user, conversation)
        set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
        calls, platform, *_ = stub_reply(monkeypatch)
        tools, caps = [], []
        card = {"type": "card", "subtype": "weather", "points": ["天气结果"]}
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return card
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
        result = events(client.post("/chat", headers=headers, json={"message": "开心", "conversation_id": conversation}))
        snapshots.append((result, tools, caps, balance(user), bool(calls), bool(platform), get_pending(key)))
        assert asyncio.run(database.get_messages(user, conversation_id=conversation))[-1]["role"] == "assistant"
    assert snapshots[0] == snapshots[1]
    assert snapshots[1] == ([{"card": card}, {"done": True}], [("weather", {"city": "开心"})], [("weather", True)], 0, False, False, None)


def _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, *, byok=True):
    """Use /chat at balance 10 to create the pending before changing credit."""
    import services.chat_service as chat
    from byok.store import delete_config
    from intent_router import get_pending
    monkeypatch.setenv("DEV_MODE", "1")
    user, conversation, headers = setup(client, dev_headers, monkeypatch)
    if not byok:
        asyncio.run(delete_config(user))
    message = "怎么去机场" if intent == "route" else "帮我搜点信息"
    pending = {"intent": intent, "params": {"destination": "机场"} if intent == "route" else {}, "missing": ["origin" if intent == "route" else "query"]}
    def classify(_client, text, history):
        return {"intent": pending["intent"], "params": dict(pending["params"]), "missing": list(pending["missing"])} if text == message else {"intent": None, "params": {}, "missing": []}
    monkeypatch.setattr(chat, "recognize_intent", classify)
    seed = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
    assert seed[-1] == {"done": True} and get_pending((user, conversation)) == pending
    assert balance(user) == 10
    return user, conversation, headers, pending


@pytest.mark.parametrize("intent,message", [("route", "算了"), ("route", "换个话题"), ("route", "从家出发"), ("web_search", "算了")])
def test_r2_zero_balance_other_pending_free_exits(client, dev_headers, monkeypatch, intent, message):
    import database
    import services.chat_service as chat
    from intent_router import get_pending
    user, conversation, headers, pending = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent)
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE users SET strawberry_balance = 0 WHERE username = ?", (user,))
    calls, platform, _, replies = stub_reply(monkeypatch)
    tools = []
    monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: tools.append((a, k)))
    result = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
    if message == "算了":
        assert result == [{"text": "好，已取消。"}, {"done": True}]
        assert get_pending((user, conversation)) is None and not calls
        saved = asyncio.run(database.get_messages(user, conversation_id=conversation))
        assert saved[-1]["role"] == "assistant" and saved[-1]["content"] == "好，已取消。"
    elif message == "换个话题":
        assert result == [{"reply_model": {"source": "byok", "label": "Claude · claude-opus-5-5"}}, {"text": "测试"}, {"text": "回复"}, {"done": True}]
        assert get_pending((user, conversation)) is None and len(calls) == 1 and replies[0].closed
    else:
        assert result == [{"error": database.strawberry_insufficient_message()}]
        assert get_pending((user, conversation)) == pending and not calls
    assert not tools and not platform and balance(user) == 0


@pytest.mark.parametrize("intent", ["route", "web_search"])
@pytest.mark.parametrize("message", ["算了", "换个话题", "从家出发"])
def test_r2_paid_other_pending_matches_platform(client, dev_headers, monkeypatch, intent, message):
    import services.chat_service as chat
    from intent_router import get_pending
    snapshots = []
    card = {"type": "card", "subtype": intent, "points": ["付费工具结果"]}
    for byok in (False, True):
        user, conversation, headers, _ = _r2_seed_other_pending(client, dev_headers, monkeypatch, intent, byok=byok)
        calls, platform, *_ = stub_reply(monkeypatch)
        tools = []
        def execute(kind, params):
            tools.append((kind, dict(params)))
            return card
        monkeypatch.setattr(chat, "execute_intent", execute)
        result = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
        snapshots.append((result, tools, balance(user), bool(calls), bool(platform), get_pending((user, conversation))))
    assert snapshots[0] == snapshots[1]
    expected_params = {"destination": "机场", "origin": message} if intent == "route" else {"query": message}
    assert snapshots[1] == ([{"card": card}, {"done": True}], [(intent, expected_params)], 0, False, False, None)


def test_r2_cancelled_worker_exception_is_retrieved_without_shield_log(monkeypatch, caplog):
    import services.chat_service as chat
    from concurrent.futures import ThreadPoolExecutor
    entered, released = threading.Event(), threading.Event()
    owner_threads = []
    class Control:
        def abort(self):
            released.set()
    def worker():
        owner_threads.append(threading.get_ident())
        entered.set()
        assert released.wait(3)
        raise httpx.ReadError("interrupted worker")
    async def scenario():
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="fiona-byok-r2") as pool:
            task = asyncio.create_task(chat._byok_call(pool, worker, control=Control()))
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert task.cancelled()
    try:
        asyncio.run(scenario())
    finally:
        released.set()
    assert len(owner_threads) == 1
    assert "exception in shielded future" not in caplog.text


def test_r2_cancelled_open_closes_returned_stream_on_worker_after_return(monkeypatch):
    import services.chat_service as chat
    from concurrent.futures import ThreadPoolExecutor
    entered, released = threading.Event(), threading.Event()
    lifecycle = []
    class Stream:
        def close(self):
            lifecycle.append(("close", threading.get_ident()))
    class Control:
        def abort(self):
            lifecycle.append(("abort", threading.get_ident()))
            released.set()
    def worker():
        lifecycle.append(("open", threading.get_ident()))
        entered.set()
        assert released.wait(3)
        lifecycle.append(("returned", threading.get_ident()))
        return Stream()
    async def scenario():
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="fiona-byok-r2") as pool:
            task = asyncio.create_task(chat._byok_call(pool, worker, control=Control()))
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            assert task.cancelled()
    try:
        asyncio.run(scenario())
    finally:
        released.set()
    assert [name for name, _ in lifecycle] == ["open", "abort", "returned", "close"]
    assert lifecycle[0][1] == lifecycle[2][1] == lifecycle[3][1]
    assert lifecycle[1][1] != lifecycle[3][1]


@pytest.mark.parametrize("message", ["先聊一会儿", "聊点别的", "换个话题", "先不查了"])
def test_r3_zero_balance_weather_pending_topic_exit(client, dev_headers, monkeypatch, message):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending
    user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=0)
    key = (user, conversation)
    set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
    monkeypatch.setattr(chat, "detect_mode", lambda *args, **kwargs: "friend")
    monkeypatch.setattr(chat, "recognize_intent", lambda *args, **kwargs: {"intent": None, "params": {}, "missing": []})
    calls, platform, *_ = stub_reply(monkeypatch)
    tools = []
    monkeypatch.setattr(chat, "execute_intent", lambda *args, **kwargs: tools.append(args))
    result = events(client.post("/chat", headers=headers, json={"message": message, "conversation_id": conversation}))
    assert get_pending(key) is None
    assert len(calls) == 1 and not platform and not tools
    assert result[0] == {"reply_model": {"source": "byok", "label": "Claude · claude-opus-5-5"}}
    assert result[-1] == {"done": True} and balance(user) == 0


def test_r3_paid_weather_topic_exit_matches_unconfigured_platform(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from byok.store import delete_config
    from intent_router import get_pending, set_pending
    snapshots = []
    for enabled in (False, True):
        monkeypatch.setenv("DEV_MODE", "1")
        user, conversation, headers = setup(client, dev_headers, monkeypatch, balance=10)
        if not enabled:
            asyncio.run(delete_config(user))
        key = (user, conversation)
        set_pending(key, {"intent": "weather", "params": {}, "missing": ["city"]})
        calls, platform, *_ = stub_reply(monkeypatch)
        tools, caps = [], []
        card = {"type": "card", "subtype": "weather", "points": ["天气结果"]}
        def execute(intent, params):
            tools.append((intent, dict(params)))
            return card
        monkeypatch.setattr(chat, "execute_intent", execute)
        monkeypatch.setattr(chat, "check_chat_daily_cap", lambda kind, user, *, hit: caps.append((kind, hit)))
        result = events(client.post("/chat", headers=headers, json={"message": "换个话题", "conversation_id": conversation}))
        snapshots.append((result, tools, caps, balance(user), bool(calls), bool(platform), get_pending(key)))
    assert snapshots[0] == snapshots[1]
    assert snapshots[1] == ([{"card": card}, {"done": True}], [("weather", {"city": "换个话题"})], [("weather", True)], 0, False, False, None)
