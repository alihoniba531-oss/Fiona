"""Beta strawberry reservation, settlement, refill and tester-name regressions."""

import asyncio
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import aiosqlite
import pytest


def _events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _prepare(client, dev_headers, monkeypatch, balance=10):
    import database
    from auth import create_token
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    user = dev_headers["X-Dev-User"]
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]

    async def set_balance():
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (balance, user))
            await db.commit()

    asyncio.run(set_balance())
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    return user, conversation, {"Authorization": f"Bearer {create_token(user)}"}


def _balance(user):
    import database

    return asyncio.run(database.get_strawberry_balance(user))


def test_parallel_chat_only_one_reservation_reaches_model(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from _fakes import FakeStream

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch)
    calls = []

    def model(*args, **kwargs):
        calls.append(1)
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", model)
    payload = {"message": "普通测试消息", "conversation_id": conversation}
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: client.post("/chat", headers=headers, json=payload), range(3)))
    events = [_events(response) for response in responses]
    assert len(calls) == 1
    assert sum(any(event.get("done") for event in turn) for turn in events) == 1
    assert sum(any("草莓不足" in event.get("error", "") for event in turn) for turn in events) == 2
    assert _balance(user) == 0


def test_five_strawberries_cannot_buy_ten_strawberry_reply(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch, balance=5)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("model must not run")))
    events = _events(client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    }))
    assert events == [{"error": "草莓不足，内测期间请联系管理员补充 🍓"}]
    assert _balance(user) == 5


@pytest.mark.parametrize("intent,result,missing,billable", [
    ("web_search", {"type": "card", "source": "搜索", "points": ["失败"], "error": True}, [], False),
    ("open_app", "当前不能打开应用", [], False),
    ("route", None, ["origin"], False),
    ("unknown_intent", "不知道怎么执行这个", [], False),
    ("get_datetime", "2026年9月23日 10:00", [], True),
    ("fetch_card", {"type": "card", "source": "网页", "points": ["已读取"]}, [], True),
], ids=["tool-failure", "desktop-placeholder", "ask-missing", "unknown-intent", "datetime-success", "card-success"])
def test_tool_delivery_settlement(client, dev_headers, monkeypatch, intent, result, missing, billable):
    import services.chat_service as chat

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch)
    monkeypatch.setattr(chat, "recognize_intent", lambda *a, **k: {
        "intent": intent, "params": {}, "missing": missing,
    })
    monkeypatch.setattr(chat, "execute_intent", lambda *a, **k: result)
    events = _events(client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    }))
    assert events[-1] == {"done": True}
    assert _balance(user) == (0 if billable else 10)


def test_model_error_refunds_reservation(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(chat, "_create_stream_with_fallback", fail)
    events = _events(client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    }))
    assert events[-1].get("error")
    assert _balance(user) == 10


def test_refund_failure_keeps_sse_error_and_records_trace(
    client, dev_headers, monkeypatch, capsys,
):
    import services.chat_service as chat

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch)
    traces = []

    def fail_model(*args, **kwargs):
        raise RuntimeError("synthetic provider failure")

    async def fail_refund(*args, **kwargs):
        raise sqlite3.OperationalError("private-refund-detail")

    async def capture_trace(*args, **kwargs):
        traces.append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "_create_stream_with_fallback", fail_model)
    monkeypatch.setattr(chat, "refund_strawberries", fail_refund)
    monkeypatch.setattr(chat, "log_event", capture_trace)
    events = _events(client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    }))
    assert len(events) == 1 and events[0].get("error")
    assert traces and traces[0]["refund_failed"] is True
    output = capsys.readouterr().out
    assert "refund failed type=OperationalError" in output
    assert "private-refund-detail" not in output
    assert _balance(user) == 0


@pytest.mark.parametrize("mode", ["friend", "mirror"])
def test_post_delivery_accounting_error_does_not_follow_done_with_error(
    client, dev_headers, monkeypatch, mode,
):
    import services.chat_service as chat

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch)
    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: mode)

    def fail_accounting(*args, **kwargs):
        raise RuntimeError("synthetic accounting failure")

    monkeypatch.setattr(chat.token_budget, "add", fail_accounting)
    events = _events(client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    }))
    assert events[-1] == {"done": True}
    assert not any(event.get("error") for event in events)
    assert _balance(user) == 0


def test_context_error_refunds_before_stream(client, dev_headers, monkeypatch):
    import routers.chat as chat_router
    from agent_store import ResourceNotFound

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch)

    async def fail(*args, **kwargs):
        raise ResourceNotFound()

    monkeypatch.setattr(chat_router, "build_context", fail)
    response = client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    })
    assert response.status_code == 404
    assert _balance(user) == 10


def test_early_stream_aclose_refunds_reservation(client, dev_headers, monkeypatch):
    import database
    import services.chat_service as chat
    from routers.chat import ChatRequest

    user, conversation, _ = _prepare(client, dev_headers, monkeypatch)

    async def scenario():
        assert await database.reserve_strawberries(user, database.STRAWBERRY_COST_PER_REPLY) == 0
        ctx = await chat.build_context(ChatRequest(message="普通测试消息", conversation_id=conversation), user)
        stream = chat.run_chat(ctx, reserved=True)
        first = await anext(stream)
        assert '"text"' in first
        await stream.aclose()
        return await database.get_strawberry_balance(user)

    assert asyncio.run(scenario()) == 10


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_asgi_disconnect_after_first_chunk_refunds_reservation(
    client, dev_headers, monkeypatch, spec_version,
):
    import database
    import routers.chat as chat_router
    import services.chat_service as chat
    from routers.chat import ChatRequest
    from starlette.requests import ClientDisconnect

    user, conversation, _ = _prepare(client, dev_headers, monkeypatch)

    class BlockingModelStream:
        def __init__(self):
            self.count = 0
            self.released = threading.Event()

        def __iter__(self):
            return self

        def __next__(self):
            if self.count == 0:
                self.count += 1
                return SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="一块回复"), finish_reason=None,
                )])
            self.released.wait(timeout=20)
            raise StopIteration

        def close(self):
            self.released.set()

    model_stream = BlockingModelStream()
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **k: (model_stream, False))

    async def scenario():
        assert await database.reserve_strawberries(user, database.STRAWBERRY_COST_PER_REPLY) == 0
        ctx = await chat.build_context(ChatRequest(message="普通测试消息", conversation_id=conversation), user)
        tracker = chat.ChatRunTracker()
        response = chat_router._ReservedChatResponse(
            chat.run_chat(ctx, reserved=True, tracker=tracker),
            user, tracker, media_type="text/event-stream",
        )
        first_chunk_sent = asyncio.Event()

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                first_chunk_sent.set()
                # ASGI 2.4 reports a disconnected client through send().
                if spec_version == "2.4":
                    raise OSError("client disconnected")

        async def receive():
            await first_chunk_sent.wait()
            return {"type": "http.disconnect"}

        scope = {"type": "http", "asgi": {"spec_version": spec_version},
                 "method": "POST", "path": "/chat", "headers": []}
        try:
            await asyncio.wait_for(response(scope, receive, send), timeout=10)
        except ClientDisconnect:
            assert spec_version == "2.4"
        assert first_chunk_sent.is_set()
        assert tracker.started is True
        return await database.get_strawberry_balance(user)

    assert asyncio.run(scenario()) == 10


def test_asgi_failure_before_generator_start_refunds_reservation(
    client, dev_headers, monkeypatch,
):
    import database
    import routers.chat as chat_router
    import services.chat_service as chat
    from fastapi.responses import StreamingResponse

    user, _, _ = _prepare(client, dev_headers, monkeypatch)

    async def fail_before_stream(*args, **kwargs):
        raise RuntimeError("ASGI send failed before streaming")

    monkeypatch.setattr(StreamingResponse, "__call__", fail_before_stream)

    async def scenario():
        assert await database.reserve_strawberries(user, database.STRAWBERRY_COST_PER_REPLY) == 0
        tracker = chat.ChatRunTracker()
        stream = chat.run_chat(object(), reserved=True, tracker=tracker)
        response = chat_router._ReservedChatResponse(
            stream, user, tracker, media_type="text/event-stream",
        )
        with pytest.raises(RuntimeError, match="ASGI send failed"):
            await response({}, None, None)
        assert tracker.started is False
        return await database.get_strawberry_balance(user)

    assert asyncio.run(scenario()) == 10


def test_daily_refill_crosses_shanghai_day_once_without_lowering_balance(
    client, dev_headers, monkeypatch,
):
    import database

    user, _, _ = _prepare(client, dev_headers, monkeypatch, balance=5)
    day = ["2026-09-23"]
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "20")
    monkeypatch.setattr(database, "_today_shanghai", lambda: day[0])
    assert _balance(user) == 20

    async def set_balance(value):
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE users SET strawberry_balance = ? WHERE username = ?", (value, user))
            await db.commit()

    asyncio.run(set_balance(8))
    assert _balance(user) == 8
    day[0] = "2026-09-24"
    assert _balance(user) == 20
    asyncio.run(set_balance(35))
    day[0] = "2026-09-25"
    assert _balance(user) == 35


def test_refill_changes_balance_endpoint_and_login_response(client, dev_headers, monkeypatch):
    import database

    user, _, _ = _prepare(client, dev_headers, monkeypatch, balance=5)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "20")
    monkeypatch.setattr(database, "_today_shanghai", lambda: "2026-09-23")
    monkeypatch.setenv("DEV_MODE", "1")
    assert client.get("/strawberry", headers=dev_headers).json()["balance"] == 20
    assert client.post("/auth/test-login", json={"username": user}).json()["balance"] == 20


def test_refill_enabled_insufficient_balance_message(client, dev_headers, monkeypatch):
    import database

    user, conversation, headers = _prepare(client, dev_headers, monkeypatch, balance=5)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "8")
    monkeypatch.setattr(database, "_today_shanghai", lambda: "2026-09-23")
    events = _events(client.post("/chat", headers=headers, json={
        "message": "普通测试消息", "conversation_id": conversation,
    }))
    assert events == [{"error": "今天的草莓用完了，明天会自动补到 8 颗；急用请联系管理员补充 🍓"}]
    assert _balance(user) == 8


def test_zero_balance_crisis_reaches_model_in_dev_mode(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from _fakes import FakeStream
    from safety import CRISIS_RESOURCE_NOTE

    user, conversation, _ = _prepare(client, dev_headers, monkeypatch, balance=0)
    monkeypatch.setenv("DEV_MODE", "1")
    calls = []

    def model(*args, **kwargs):
        calls.append(1)
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", model)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "message": "我不想活了", "conversation_id": conversation,
    }))
    assert len(calls) == 1
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert events[-1] == {"done": True}
    assert _balance(user) == 0


def test_refill_and_concurrent_reservation_share_atomic_transaction(
    client, dev_headers, monkeypatch,
):
    import database

    user, _, _ = _prepare(client, dev_headers, monkeypatch, balance=0)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "20")
    monkeypatch.setattr(database, "_today_shanghai", lambda: "2026-09-23")

    async def scenario():
        return await asyncio.gather(*(
            database.reserve_strawberries(user, database.STRAWBERRY_COST_PER_REPLY)
            for _ in range(3)
        ))

    assert sorted(asyncio.run(scenario()), key=lambda value: -1 if value is None else value) == [None, 0, 10]
    assert _balance(user) == 0


def test_invalid_refill_is_disabled_without_exposing_value(client, dev_headers, monkeypatch, capsys):
    import database

    user, _, _ = _prepare(client, dev_headers, monkeypatch, balance=5)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "private-invalid-value")
    monkeypatch.setattr(database, "_INVALID_REFILL_WARNED", False)
    assert _balance(user) == 5
    output = capsys.readouterr().out
    assert "STRAWBERRY_DAILY_REFILL" in output
    assert "private-invalid-value" not in output


def test_out_of_range_refill_is_disabled(client, dev_headers, monkeypatch, capsys):
    import database

    user, _, _ = _prepare(client, dev_headers, monkeypatch, balance=5)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "9" * 5000)
    monkeypatch.setattr(database, "_INVALID_REFILL_WARNED", False)
    assert _balance(user) == 5
    assert "STRAWBERRY_DAILY_REFILL" in capsys.readouterr().out


def test_tester_invites_skip_existing_account_and_invite_names(client, dev_headers):
    import database

    async def scenario():
        await database.get_or_create_user("tester07")
        assert await database.create_invite("EXISTING", "tester09")
        created = await database.create_tester_invites(2)
        return created

    created = asyncio.run(scenario())
    assert [username for _, username in created] == ["tester10", "tester11"]
    assert len({code for code, _ in created}) == 2


@pytest.mark.parametrize("module_name,function_name,query", [
    ("tools.web_search", "web_search", "测试事实"),
    ("tools.travel_plan", "travel_plan", "宁波到北京"),
], ids=["web-search", "travel-plan"])
def test_unstructured_tool_model_reply_is_explicitly_non_billable(
    monkeypatch, module_name, function_name, query,
):
    import importlib
    import services.chat_service as chat

    module = importlib.import_module(module_name)
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="服务暂时没有结果"))])
    model = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr(module, "_get_client", lambda: model)
    card = getattr(module, function_name)(query)
    assert card["error"] is True
    assert not chat._tool_billable(function_name, card)


def test_fetch_card_summary_failure_has_structured_error(monkeypatch):
    import services.chat_service as chat
    from tools import fetch_card as module

    monkeypatch.setattr(module, "_fetch_html", lambda *a: "足够长的网页正文" * 20)
    monkeypatch.setattr(module, "_summarize_points", lambda *a: ([], False))
    card = module.fetch_card("https://example.org/article")
    assert card["error"] is True
    assert not chat._tool_billable("fetch_card", card)
