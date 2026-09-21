"""Long official sessions preserve history, model limits and existing V2 data."""
import asyncio
import json
import sqlite3

import pytest

from test_agent_exchanges import exchange_model  # noqa: F401
from test_official_agent_exchanges import owner, official_cards, _start, _wait  # noqa: F401


def test_official_schema_accepts_every_integer_from_two_through_ninety_nine():
    from routers.agent_exchanges import OfficialExchangeCreate

    common = {"official_agent_id": "official:creative-partner", "topic": "测试完整允许范围"}
    assert OfficialExchangeCreate(**common).max_turns == 99
    assert [OfficialExchangeCreate(**common, max_turns=turns).max_turns for turns in range(2, 100)] == list(range(2, 100))


@pytest.mark.parametrize("turns", [2, 7, 98, 99])
def test_official_accepts_extended_integer_limits_without_changing_peer_rules(
    client, owner, official_cards, exchange_model, turns,
):
    exchange_model.block(1)
    created = _start(client, owner, official_cards[0], max_turns=turns)
    exchange_id = created["exchange"]["id"]
    try:
        assert created["exchange"]["max_turns"] == turns
        assert exchange_model.started.wait(timeout=10)
        assert client.post(f"/agent-exchanges/{exchange_id}/stop", headers=owner["headers"]).status_code == 200
    finally:
        exchange_model.release.set()
    assert _wait(client, owner, exchange_id)["exchange"]["status"] == "stopped"
    assert len(exchange_model.calls) == 1


def test_ninety_nine_replies_and_summary_retain_late_history_and_survive_estimated_budget(
    client, owner, official_cards, exchange_model,
):
    exchange_model.missing_usage = True
    exchange_model.reply_factory = lambda number: f"TURN_{number:04d}_ONLY " + "bounded-content " * 24
    end_marker = "FINAL_TOPIC_DETAIL_需保留结尾"
    topic = ("完整剧情设定" * 2000)[:10000 - len(end_marker)] + end_marker
    assert len(topic) == 10000
    created = _start(client, owner, official_cards[0], max_turns=None, topic=topic)
    assert created["exchange"]["topic"] == topic
    final = _wait(client, owner, created["exchange"]["id"])
    exchange = final["exchange"]
    assert exchange["status"] == "completed", exchange["error"]
    assert exchange["max_turns"] == exchange["turn_count"] == 99
    assert len(final["messages"]) == 99
    assert [message["sequence"] for message in final["messages"]] == list(range(1, 100))
    assert exchange["summary"] == "模拟交流总结"
    assert exchange["topic"] == topic
    assert len(exchange_model.calls) == 100
    assert [call["provider"] for call in exchange_model.calls] == [
        "main" if number % 2 == 0 else "official" for number in range(99)
    ] + ["official"]
    for number, call in enumerate(exchange_model.calls):
        payload = json.loads(call["messages"][-1]["content"])
        assert payload["topic"] == topic and payload["topic"].endswith(end_marker)
        assert len(payload["dialogue"]) == number
        if number:
            assert payload["dialogue"][-1]["content"].startswith(f"TURN_{number:04d}_ONLY ")
    usage = exchange["usage"]
    assert usage["model_calls"] == usage["max_model_calls"] == 100
    assert usage["estimated"] is True and usage["reserved_tokens"] == 0
    assert 80_000 < usage["budget_used"] <= usage["token_budget"] == 14_000_000
    reopened = client.get(f"/agent-exchanges/{exchange['id']}", headers=owner["headers"])
    assert reopened.json() == final
    assert len(exchange_model.calls) == 100


@pytest.mark.parametrize("blocked_call", [99, 100], ids=["last-reply", "summary"])
def test_stop_near_the_end_discards_late_official_results(
    client, owner, official_cards, exchange_model, blocked_call,
):
    exchange_model.block(blocked_call)
    exchange_id = _start(client, owner, official_cards[1], max_turns=99)["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=15)
        stopped = client.post(f"/agent-exchanges/{exchange_id}/stop", headers=owner["headers"])
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["exchange"]["status"] == "stopped"
    finally:
        exchange_model.release.set()
    final = _wait(client, owner, exchange_id)
    assert final["exchange"]["status"] == "stopped"
    assert final["exchange"]["turn_count"] == len(final["messages"]) == blocked_call - 1
    assert final["exchange"]["summary"] == ""
    assert final["exchange"]["usage"]["reserved_tokens"] == 0
    assert len(exchange_model.calls) == blocked_call


def test_v3_migration_preserves_peer_and_official_rows_history_calls_indexes_and_triggers(tmp_path):
    import aiosqlite
    import exchange_store

    path = tmp_path / "official-v2-upgrade.db"

    async def migrate(*functions):
        async with aiosqlite.connect(path) as db:
            for function in functions:
                await function(db)

    asyncio.run(migrate(exchange_store.migrate_exchanges_schema, exchange_store.migrate_official_exchanges_schema))
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for kind, recipient in (("peer", "peer-b"), ("official", None)):
            db.execute("""INSERT INTO agent_exchanges
                (id, kind, initiator_username, recipient_username, initiator_agent_id, recipient_agent_id,
                 pair_key, initiator_json, recipient_json, topic, max_turns, turn_count, status,
                 run_token, inflight_call_id, model_calls, input_tokens, output_tokens,
                 budget_used, reserved_tokens, token_budget, summary)
                VALUES (?, ?, 'owner-a', ?, 'agent-a', ?, ?, '{}', '{}', '旧话题', 6, 1, 'running',
                        'preserved-run-token', ?, 2, 12, 8, 1520, 1500, 80000, '保留已有摘要')""",
                       (kind, kind, recipient, f"target-{kind}", f"pair-{kind}", f"{kind}-reserved"))
            db.execute("""INSERT INTO agent_exchange_messages
                (id, exchange_id, sequence, agent_id, display_name, avatar_emoji, content)
                VALUES (?, ?, 1, 'agent-a', '旧分身', '🌟', '旧消息不能丢失')""", (f"{kind}-message", kind))
            for number, status in ((1, "succeeded"), (2, "reserved")):
                db.execute("""INSERT INTO agent_exchange_calls
                    (id, exchange_id, ordinal, kind, status, reserved_tokens, input_limit, output_limit, input_tokens, output_tokens)
                    VALUES (?, ?, ?, 'turn', ?, 1500, 1244, 256, ?, ?)""",
                           (f"{kind}-{status}", kind, number, status, 12 if number == 1 else None, 8 if number == 1 else None))
        db.execute("CREATE INDEX custom_exchange_topic ON agent_exchanges(topic)")
        db.execute("CREATE TABLE migration_audit (exchange_id TEXT)")
        db.execute("""CREATE TRIGGER custom_exchange_audit AFTER UPDATE OF topic ON agent_exchanges
            BEGIN INSERT INTO migration_audit VALUES (NEW.id); END""")
        tables = ("agent_exchanges", "agent_exchange_messages", "agent_exchange_calls")
        before = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")] for table in tables}
        schema_before = [tuple(row) for row in db.execute("SELECT type, name, sql FROM sqlite_master WHERE tbl_name='agent_exchanges' AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY name")]

    asyncio.run(migrate(exchange_store.migrate_extended_official_exchanges_schema, exchange_store.migrate_extended_official_exchanges_schema))
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for table, old_rows in before.items():
            after = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
            expected = [{**row, "provider": "", "model": ""} for row in old_rows] if table == "agent_exchange_calls" else old_rows
            assert after == expected
        assert [tuple(row) for row in db.execute("SELECT type, name, sql FROM sqlite_master WHERE tbl_name='agent_exchanges' AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY name")] == schema_before
        assert db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=?", (exchange_store.EXTENDED_OFFICIAL_MIGRATION_VERSION,)).fetchone()[0] == 1
        db.execute("UPDATE agent_exchanges SET topic='迁移后可写' WHERE id='official'")
        assert [tuple(row) for row in db.execute("SELECT * FROM migration_audit")] == [("official",)]
        # Existing six-turn sessions remain unchanged; only future official rows
        # may opt into 99. The database still rejects peer limit escalation.
        db.execute("UPDATE agent_exchanges SET max_turns=99 WHERE id='official'")
        for exchange_id, invalid_turns in (("peer", 7), ("official", 100), ("official", 2.5)):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE agent_exchanges SET max_turns=? WHERE id=?", (invalid_turns, exchange_id))
