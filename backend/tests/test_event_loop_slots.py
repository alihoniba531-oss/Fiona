"""Regression for chat slot access while a write transaction is in flight."""

import asyncio
import json
import sqlite3
from time import monotonic

import aiosqlite
import conversation_matcher
import database
import intent_router
import mode_switcher


def test_init_db_enables_wal_and_shared_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "wal.db"))
    asyncio.run(database.init_db())

    with sqlite3.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    for slot_conn in (intent_router._slot_conn, mode_switcher._slot_conn):
        with slot_conn() as db:
            assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_slot_access_does_not_block_event_loop_during_writer_transaction(tmp_path, monkeypatch):
    asyncio.run(_exercise_slot_contention(tmp_path, monkeypatch))


async def _exercise_slot_contention(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "slot-contention.db"))
    await database.init_db()
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            """INSERT INTO chat_slot_state
               (state_key, kind, owner_username, payload_json, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("alice", "mode", "alice", json.dumps({"mode": "friend"}), "2000-01-01T00:00:00+00:00"),
        )
        await db.commit()

    writer_started = asyncio.Event()
    heartbeat_delays = []

    async def heartbeat():
        next_tick = monotonic() + 0.01
        while not writer_done.done() or not slot_done.done():
            await asyncio.sleep(max(0, next_tick - monotonic()))
            heartbeat_delays.append(monotonic() - next_tick)
            next_tick = monotonic() + 0.01

    async def hold_write_lock():
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("BEGIN IMMEDIATE")
            writer_started.set()
            # The transaction retains the writer lock across multiple awaits.
            await asyncio.sleep(0.2)
            await asyncio.sleep(0.2)
            await db.commit()

    async def access_slots():
        await writer_started.wait()
        # This production coroutine used to call get_user_mode on the event loop.
        assert await conversation_matcher.detect_and_save(
            None, "alice", "hello", [], message_count=0,
        ) == 0
        await asyncio.to_thread(
            intent_router.set_pending,
            "alice",
            {"intent": "route", "params": {}, "missing": ["origin"]},
        )
        await asyncio.to_thread(intent_router.clear_pending, "alice")

    writer_done = asyncio.create_task(hold_write_lock())
    slot_done = asyncio.create_task(access_slots())
    beat_done = asyncio.create_task(heartbeat())
    results = await asyncio.gather(writer_done, slot_done, beat_done, return_exceptions=True)

    assert not any(isinstance(result, sqlite3.OperationalError) for result in results), results
    assert all(not isinstance(result, BaseException) for result in results), results
    assert heartbeat_delays
    assert max(heartbeat_delays) < 0.25
