"""An in-flight exchange reuses and closes its revocation read connection."""
import asyncio
import sqlite3
import time

import pytest

import database
import exchange_store
from services import exchange_service


@pytest.fixture
def running_exchange(tmp_path, monkeypatch):
    path = tmp_path / "exchange-poll.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE agent_exchanges (id TEXT, status TEXT, run_token TEXT)")
        db.execute("INSERT INTO agent_exchanges VALUES ('exchange-1', 'running', 'token-1')")
    monkeypatch.setattr(database, "DB_PATH", str(path))

    connections = []
    original_connect = exchange_store.aiosqlite.connect

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(exchange_store.aiosqlite, "connect", tracked_connect)
    return path, connections


def _assert_one_closed_connection(connections):
    assert len(connections) == 1
    assert connections[0]._connection is None


def test_three_second_provider_call_reuses_one_poll_connection(running_exchange, monkeypatch):
    _, connections = running_exchange
    checks = 0
    original_one = exchange_store._one

    async def counted_one(*args, **kwargs):
        nonlocal checks
        checks += 1
        return await original_one(*args, **kwargs)

    async def held_provider(_messages, *, max_tokens, provider):
        await asyncio.sleep(3)
        return {"content": "完成"}

    monkeypatch.setattr(exchange_store, "_one", counted_one)
    monkeypatch.setattr(exchange_service, "generate_exchange_reply", held_provider)

    result = asyncio.run(exchange_service._generate_while_authorized(
        "exchange-1", "token-1", [], max_tokens=1, provider="main",
    ))

    assert result == {"content": "完成"}
    assert checks >= 8  # The 0.25-second revocation polling still runs.
    _assert_one_closed_connection(connections)


def test_revocation_cancels_upstream_within_half_second(running_exchange, monkeypatch):
    path, connections = running_exchange
    started = asyncio.Event()
    cancelled_at = None

    async def held_provider(_messages, *, max_tokens, provider):
        nonlocal cancelled_at
        started.set()
        try:
            await asyncio.sleep(3)
        finally:
            cancelled_at = time.monotonic()

    monkeypatch.setattr(exchange_service, "generate_exchange_reply", held_provider)

    async def scenario():
        task = asyncio.create_task(exchange_service._generate_while_authorized(
            "exchange-1", "token-1", [], max_tokens=1, provider="main",
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0.3)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE agent_exchanges SET status = 'stopped' WHERE id = 'exchange-1'")
        revoked_at = time.monotonic()
        with pytest.raises(exchange_service.ExchangeRevoked):
            await asyncio.wait_for(task, timeout=0.5)
        assert cancelled_at is not None
        assert cancelled_at - revoked_at <= 0.5

    asyncio.run(scenario())
    _assert_one_closed_connection(connections)


def test_provider_exception_closes_poll_connection(running_exchange, monkeypatch):
    _, connections = running_exchange

    async def failing_provider(_messages, *, max_tokens, provider):
        raise RuntimeError("fake provider failed")

    monkeypatch.setattr(exchange_service, "generate_exchange_reply", failing_provider)
    with pytest.raises(RuntimeError, match="fake provider failed"):
        asyncio.run(exchange_service._generate_while_authorized(
            "exchange-1", "token-1", [], max_tokens=1, provider="main",
        ))
    _assert_one_closed_connection(connections)


def test_external_cancellation_closes_poll_connection(running_exchange, monkeypatch):
    _, connections = running_exchange
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def held_provider(_messages, *, max_tokens, provider):
        started.set()
        try:
            await asyncio.sleep(3)
        finally:
            cancelled.set()

    monkeypatch.setattr(exchange_service, "generate_exchange_reply", held_provider)

    async def scenario():
        task = asyncio.create_task(exchange_service._generate_while_authorized(
            "exchange-1", "token-1", [], max_tokens=1, provider="main",
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()

    asyncio.run(scenario())
    _assert_one_closed_connection(connections)
