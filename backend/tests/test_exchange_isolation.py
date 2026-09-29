"""Slow exchanges and URL cards cannot starve an unrelated chat."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import os
import sqlite3
from threading import Event, Lock
import time

from openai import AsyncOpenAI
import pytest

from test_safe_http_deadline import local_fetch_server  # noqa: F401


@pytest.fixture(autouse=True)
def small_default_executor(monkeypatch):
    from rate_limit import limiter

    monkeypatch.setenv("FIONA_DEFAULT_POOL_WORKERS", "4")
    monkeypatch.setattr(limiter, "enabled", False)


def _owner(client, number, *, public=False):
    headers = {"X-Dev-User": f"isolation_owner_{number}"}
    response = client.put("/agents/me", headers=headers, json={
        "display_name": f"测试分身 {number}", "bio": "并发交流", "is_public": public,
    })
    assert response.status_code == 200, response.text
    return headers


def _start(client, headers, official_id):
    response = client.post("/agent-exchanges/official", headers=headers, json={
        "official_agent_id": official_id, "topic": "一起讨论一项小计划", "max_turns": 2,
    })
    assert response.status_code == 201, response.text
    return response.json()["exchange"]["id"]


def test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive(
    client, monkeypatch, local_fetch_server,
):
    import services.exchange_service as service
    from utils.slow_pool import run_slow

    legacy = os.getenv("FIONA_T3_LEGACY_REPRO") == "1"
    started = Event()
    fetch_started = Event()
    lock = Lock()
    active = 0
    max_active = 0
    fetch_count = 0

    def block_for_five_seconds():
        time.sleep(5)

    async def hanging_provider(messages, *, max_tokens, provider="main"):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            if active >= (4 if legacy else 8):
                started.set()
        try:
            if legacy:
                # Read-only replay of the baseline's asyncio.to_thread call
                # site, deliberately confined to this opt-in test branch.
                await asyncio.to_thread(block_for_five_seconds)
            else:
                await asyncio.sleep(5)
            return {"content": "完成", "input_tokens": 1, "output_tokens": 1}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service, "generate_exchange_reply", hanging_provider)
    fetch_module = importlib.import_module("tools.fetch_card")
    original_fetch_html = fetch_module._fetch_html

    def fetch_html(url):
        nonlocal fetch_count
        with lock:
            fetch_count += 1
            if fetch_count >= 8:
                fetch_started.set()
        return original_fetch_html(url, timeout=5)

    monkeypatch.setattr(fetch_module, "_fetch_html", fetch_html)

    async def drip_fetch():
        if legacy:
            return await asyncio.to_thread(fetch_module.fetch_card, local_fetch_server + "/drip")
        return await run_slow(fetch_module.fetch_card, local_fetch_server + "/drip")

    owners = [_owner(client, number) for number in range(8)]
    assert client.portal.call(lambda: asyncio.get_running_loop()._default_executor._max_workers) == 4
    official = client.get("/agent-exchanges/official-agents", headers=owners[0]).json()["agents"][0]
    exchanges = [_start(client, headers, official["id"]) for headers in owners]
    assert started.wait(timeout=3), "official upstream calls did not overlap"
    fetch_tasks = [client.portal.start_task_soon(drip_fetch) for _ in range(8)]
    try:
        if not legacy:
            assert fetch_started.wait(timeout=2), "all eight drip fetches should enter the slow pool"
        else:
            time.sleep(0.25)
        began = time.monotonic()
        response = client.post("/chat", headers={"X-Dev-User": "other_chat_user"}, json={"message": "你好"})
        elapsed = time.monotonic() - began
        assert response.status_code == 200, response.text
        assert "data:" in response.text and "测试" in response.text
        # TestClient buffers the stream, so this is stricter than both the
        # first-event <1.5 s and completion <3 s acceptance limits.
        assert elapsed < 1.5, f"ordinary chat took {elapsed:.3f} seconds"
        assert max_active >= (4 if legacy else 8)
    finally:
        for headers, exchange_id in zip(owners, exchanges):
            client.post(f"/agent-exchanges/{exchange_id}/stop", headers=headers)
        for task in fetch_tasks:
            task.cancel()


def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
    import services.exchange_service as service

    async def start_server():
        entered, disconnected = asyncio.Event(), asyncio.Event()

        async def handler(reader, writer):
            try:
                headers = await reader.readuntil(b"\r\n\r\n")
                length = 0
                for line in headers.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1].strip())
                if length:
                    await reader.readexactly(length)
                entered.set()
                await reader.read(1)
                disconnected.set()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        return server, entered, disconnected

    async def wait_event(event):
        await asyncio.wait_for(event.wait(), timeout=5)

    server, entered, disconnected = client.portal.call(start_server)
    port = server.sockets[0].getsockname()[1]
    upstream = AsyncOpenAI(
        api_key="test-only", base_url=f"http://127.0.0.1:{port}/v1",
        timeout=15, max_retries=0,
    )
    monkeypatch.setattr(service, "get_async_main_client", lambda: upstream)
    headers = _owner(client, "cancel")
    official_id = client.get("/agent-exchanges/official-agents", headers=headers).json()["agents"][0]["id"]
    try:
        first_id = _start(client, headers, official_id)
        client.portal.call(wait_event, entered)
        began = time.monotonic()
        stopped = client.post(f"/agent-exchanges/{first_id}/stop", headers=headers)
        assert stopped.status_code == 200, stopped.text
        client.portal.call(wait_event, disconnected)
        assert time.monotonic() - began < 2
        assert stopped.json()["exchange"]["status"] == "stopped"
        # A stopped-but-still-on-wire call would retain the running slot.
        second_id = _start(client, headers, official_id)
        assert second_id != first_id
        client.post(f"/agent-exchanges/{second_id}/stop", headers=headers)
    finally:
        client.portal.call(server.close)
        client.portal.call(server.wait_closed)
        client.portal.call(upstream.close)


def test_rapid_start_stop_never_exceeds_one_inflight_call_per_owner(client, monkeypatch):
    import services.exchange_service as service

    lock = Lock()
    started = Event()
    active = 0
    peak = 0

    async def held_model(_messages, *, max_tokens, provider="main"):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service, "generate_exchange_reply", held_model)
    headers = _owner(client, "rapid")
    official_id = client.get("/agent-exchanges/official-agents", headers=headers).json()["agents"][0]["id"]
    for _ in range(4):
        started.clear()
        exchange_id = _start(client, headers, official_id)
        assert started.wait(timeout=2)
        response = client.post(f"/agent-exchanges/{exchange_id}/stop", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["exchange"]["status"] == "stopped"
    assert active == 0 and peak == 1


def test_revoking_public_agent_cancels_inflight_provider_call(client, monkeypatch):
    import database
    import services.exchange_service as service

    started, cancelled = Event(), Event()

    async def held_model(_messages, *, max_tokens, provider="main"):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(service, "generate_exchange_reply", held_model)
    first, second = _owner(client, "revoke_first", public=True), _owner(client, "revoke_second", public=True)
    second_agent = client.get("/agents/me", headers=second).json()["agent"]
    invite = client.post("/agent-exchanges", headers=first, json={
        "target_agent_id": second_agent["id"], "topic": "讨论路线", "max_turns": 2,
    })
    assert invite.status_code == 201, invite.text
    exchange_id = invite.json()["exchange"]["id"]
    accepted = client.post(f"/agent-exchanges/{exchange_id}/accept", headers=second)
    assert accepted.status_code == 200, accepted.text
    assert started.wait(timeout=2)
    hidden = client.put("/agents/me", headers=first, json={"is_public": False})
    assert hidden.status_code == 200, hidden.text
    assert cancelled.wait(timeout=2), "revocation did not cancel the upstream task"
    client.portal.call(service.wait_for_exchange, exchange_id)
    with sqlite3.connect(database.DB_PATH) as db:
        status = db.execute("SELECT status FROM agent_exchange_calls WHERE exchange_id = ?", (exchange_id,)).fetchone()
    assert status == ("discarded",)


def _assert_cancelled_call_settled(exchange_id):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        row = db.execute("""SELECT status, inflight_call_id, reserved_tokens,
            input_tokens, output_tokens, budget_used FROM agent_exchanges
            WHERE id = ?""", (exchange_id,)).fetchone()
        calls = db.execute("""SELECT status, estimated, input_tokens, output_tokens,
            input_limit, output_limit FROM agent_exchange_calls WHERE exchange_id = ?""",
            (exchange_id,)).fetchall()
    assert len(calls) == 1
    status, estimated, input_tokens, output_tokens, input_limit, output_limit = calls[0]
    assert row == ("stopped", None, 0, input_limit, output_limit, input_limit + output_limit)
    assert (status, estimated, input_tokens, output_tokens) == (
        "discarded", 1, input_limit, output_limit,
    )


def _stop_twice(client, exchange_id, first, second):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [pool.submit(client.post, f"/agent-exchanges/{exchange_id}/stop", headers=headers)
                     for headers in (first, second)]
        responses = [future.result(timeout=5) for future in responses]
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]


def test_concurrent_duplicate_stops_release_official_slot_30_times(client, monkeypatch):
    import services.exchange_service as service

    started = Event()

    async def held_model(_messages, *, max_tokens, provider="main"):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "generate_exchange_reply", held_model)
    headers = _owner(client, "twice")
    official_id = client.get("/agent-exchanges/official-agents", headers=headers).json()["agents"][0]["id"]
    for round_no in range(30):
        started.clear()
        exchange_id = _start(client, headers, official_id)
        assert started.wait(timeout=2), round_no
        _stop_twice(client, exchange_id, headers, headers)
        _assert_cancelled_call_settled(exchange_id)
        probe_id = _start(client, headers, official_id)  # Must be 201 immediately.
        assert client.post(f"/agent-exchanges/{probe_id}/stop", headers=headers).status_code == 200


def test_peer_both_participants_stop_and_release_both_slots_30_times(client, monkeypatch):
    import services.exchange_service as service

    started = Event()

    async def held_model(_messages, *, max_tokens, provider="main"):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "generate_exchange_reply", held_model)
    first = _owner(client, "peer_stop_first", public=True)
    second = _owner(client, "peer_stop_second", public=True)
    second_id = client.get("/agents/me", headers=second).json()["agent"]["id"]
    official_id = client.get("/agent-exchanges/official-agents", headers=first).json()["agents"][0]["id"]
    for round_no in range(30):
        started.clear()
        invite = client.post("/agent-exchanges", headers=first, json={
            "target_agent_id": second_id, "topic": "一起讨论路线", "max_turns": 2,
        })
        assert invite.status_code == 201, (round_no, invite.text)
        exchange_id = invite.json()["exchange"]["id"]
        accepted = client.post(f"/agent-exchanges/{exchange_id}/accept", headers=second)
        assert accepted.status_code == 200, (round_no, accepted.text)
        assert started.wait(timeout=2), round_no
        _stop_twice(client, exchange_id, first, second)
        _assert_cancelled_call_settled(exchange_id)
        for headers in (first, second):
            probe_id = _start(client, headers, official_id)
            assert client.post(f"/agent-exchanges/{probe_id}/stop", headers=headers).status_code == 200


def test_stop_before_reservation_returns_releases_slot_30_times(client, monkeypatch):
    import exchange_store

    reserved = Event()
    original_reserve = exchange_store.reserve_model_call

    async def delayed_return(*args, **kwargs):
        call_id = await original_reserve(*args, **kwargs)
        if call_id is not None:
            reserved.set()
            await asyncio.Event().wait()
        return call_id

    monkeypatch.setattr(exchange_store, "reserve_model_call", delayed_return)
    headers = _owner(client, "reserve_window")
    official_id = client.get("/agent-exchanges/official-agents", headers=headers).json()["agents"][0]["id"]
    for round_no in range(30):
        reserved.clear()
        exchange_id = _start(client, headers, official_id)
        assert reserved.wait(timeout=2), round_no
        stopped = client.post(f"/agent-exchanges/{exchange_id}/stop", headers=headers)
        assert stopped.status_code == 200, (round_no, stopped.text)
        _assert_cancelled_call_settled(exchange_id)
        probe_id = _start(client, headers, official_id)
        assert client.post(f"/agent-exchanges/{probe_id}/stop", headers=headers).status_code == 200


@pytest.mark.parametrize("always_fails", [False, True], ids=["retry-succeeds", "restart-recovers"])
def test_stop_retries_settlement_error_without_500_and_recovers_on_restart(
    client, monkeypatch, caplog, always_fails,
):
    import database
    import exchange_store
    import services.exchange_service as service

    started = Event()

    async def held_model(_messages, *, max_tokens, provider="main"):
        started.set()
        await asyncio.Event().wait()

    original_settle = exchange_store.stop_and_discard_reserved_calls
    attempts = 0

    async def injected_lock(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if always_fails or attempts < service.SETTLEMENT_MAX_ATTEMPTS:
            raise sqlite3.OperationalError("database is locked")
        return await original_settle(*args, **kwargs)

    monkeypatch.setattr(service, "generate_exchange_reply", held_model)
    monkeypatch.setattr(exchange_store, "stop_and_discard_reserved_calls", injected_lock)
    headers = _owner(client, f"settle_{always_fails}")
    official_id = client.get("/agent-exchanges/official-agents", headers=headers).json()["agents"][0]["id"]
    exchange_id = _start(client, headers, official_id)
    assert started.wait(timeout=2)

    stopped = client.post(f"/agent-exchanges/{exchange_id}/stop", headers=headers)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["exchange"]["status"] == "stopped"
    assert attempts == service.SETTLEMENT_MAX_ATTEMPTS
    assert sum("Cancelled exchange settlement failed" in message for message in caplog.messages) == (
        attempts if always_fails else attempts - 1
    )

    if not always_fails:
        _assert_cancelled_call_settled(exchange_id)
        return

    with sqlite3.connect(database.DB_PATH) as db:
        before = db.execute("""SELECT status, inflight_call_id, reserved_tokens, budget_used
            FROM agent_exchanges WHERE id = ?""", (exchange_id,)).fetchone()
        call_before = db.execute("""SELECT status, reserved_tokens FROM agent_exchange_calls
            WHERE exchange_id = ?""", (exchange_id,)).fetchone()
    assert before[0] == "stopped" and before[1] is not None and before[2] > 0
    assert call_before == ("reserved", before[2])
    assert before[3] == before[2]

    client.portal.call(exchange_store.recover_interrupted_exchanges)
    with sqlite3.connect(database.DB_PATH) as db:
        after = db.execute("""SELECT status, inflight_call_id, reserved_tokens, budget_used,
            input_tokens, output_tokens, estimated FROM agent_exchanges WHERE id = ?""",
            (exchange_id,)).fetchone()
        call_after = db.execute("""SELECT status, estimated, input_tokens, output_tokens,
            input_limit, output_limit FROM agent_exchange_calls WHERE exchange_id = ?""",
            (exchange_id,)).fetchone()
    assert after == ("stopped", None, 0, before[3], call_after[4], call_after[5], 1)
    assert call_after[:4] == ("interrupted", 1, call_after[4], call_after[5])

    client.portal.call(exchange_store.recover_interrupted_exchanges)
    with sqlite3.connect(database.DB_PATH) as db:
        repeated = db.execute("""SELECT status, inflight_call_id, reserved_tokens, budget_used,
            input_tokens, output_tokens, estimated FROM agent_exchanges WHERE id = ?""",
            (exchange_id,)).fetchone()
    assert repeated == after


def test_execute_intent_uses_slow_pool_when_default_pool_is_full(client, monkeypatch):
    """The ordinary /chat tool path must use its actual run_slow wiring."""
    import services.chat_service as chat

    legacy = os.getenv("FIONA_T3_LEGACY_TOOL_REPRO") == "1"
    if legacy:
        # Opt-in positive control: only the execute_intent call-site reverts to
        # the default executor; production source stays untouched.
        monkeypatch.setattr(chat, "run_slow", lambda fn, *args: asyncio.to_thread(fn, *args))
    loop = client.portal.call(asyncio.get_running_loop)
    release = Event()
    three_started = Event()
    tool_called = Event()
    lock = Lock()
    count = 0
    blockers = []

    def hold_default_worker():
        nonlocal count
        with lock:
            count += 1
            if count >= 3:
                three_started.set()
        release.wait(timeout=3)

    async def launch_blockers():
        return [asyncio.create_task(asyncio.to_thread(hold_default_worker)) for _ in range(4)]

    def route_to_tool(_message, _history):
        # This is running in one of four default workers. Queue four blockers,
        # wait until the other three start, then release this worker so the
        # fourth blocker gets it before execute_intent is dispatched.
        blockers.extend(asyncio.run_coroutine_threadsafe(launch_blockers(), loop).result(timeout=2))
        assert three_started.wait(timeout=2)
        return {"intent": "get_datetime", "params": {}, "missing": []}

    def execute_tool(_intent, _params):
        tool_called.set()
        return "工具调用已完成"

    monkeypatch.setattr(chat, "recognize_intent_with_fallback", route_to_tool)
    monkeypatch.setattr(chat, "execute_intent", execute_tool)
    try:
        began = time.monotonic()
        response = client.post("/chat", headers={"X-Dev-User": "tool_isolation_user"}, json={"message": "现在几点"})
        elapsed = time.monotonic() - began
        assert response.status_code == 200, response.text
        assert "工具调用已完成" in response.text
        assert tool_called.is_set()
        assert elapsed < 1.5, f"execute_intent chat took {elapsed:.3f} seconds"
    finally:
        release.set()
        if blockers:
            async def drain():
                await asyncio.gather(*blockers)
            client.portal.call(drain)
