"""Single-owner official exchanges must preserve private identity and M2 limits."""
import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from test_agent_exchanges import exchange_model  # noqa: F401 - shared provider-only fixture


@pytest.fixture
def owner(client):
    headers = {"X-Dev-User": "official_experience_owner"}
    response = client.put("/agents/me", headers=headers, json={
        "display_name": "私有星球", "bio": "用于交流的简介", "is_public": False,
    })
    assert response.status_code == 200, response.text
    return {"headers": headers, "agent": response.json()["agent"]}


@pytest.fixture
def official_cards(client, owner):
    response = client.get("/agent-exchanges/official-agents", headers=owner["headers"])
    assert response.status_code == 200, response.text
    return response.json()["agents"]


def _start(client, owner, card, *, max_turns=2, topic="一起探讨一种未来生活方式", **overrides):
    payload = {"official_agent_id": card["id"], "topic": topic, **overrides}
    if max_turns is not None:
        payload["max_turns"] = max_turns
    response = client.post("/agent-exchanges/official", headers=owner["headers"], json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _detail(client, owner, exchange_id):
    response = client.get(f"/agent-exchanges/{exchange_id}", headers=owner["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def _wait(client, owner, exchange_id):
    import services.exchange_service as exchange_service

    client.portal.call(exchange_service.wait_for_exchange, exchange_id)
    return _detail(client, owner, exchange_id)


def test_official_migration_preserves_existing_peer_rows_messages_and_reservations(tmp_path):
    import aiosqlite
    import exchange_store

    path = tmp_path / "m2-before-official.db"

    async def migrate(function):
        async with aiosqlite.connect(path) as db:
            await function(db)

    asyncio.run(migrate(exchange_store.migrate_exchanges_schema))
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        db.execute("""INSERT INTO agent_exchanges
            (id, initiator_username, recipient_username, initiator_agent_id, recipient_agent_id,
             pair_key, initiator_json, recipient_json, topic, max_turns, turn_count, status,
             run_token, inflight_call_id, model_calls, input_tokens, output_tokens,
             budget_used, reserved_tokens, token_budget)
            VALUES ('legacy-peer', 'old-a', 'old-b', 'agent-a', 'agent-b', 'old-pair', '{}', '{}',
                    '仍在进行的旧交流', 2, 1, 'running', 'old-run-token', 'call-2', 2, 12, 8, 1520, 1500, 80000)""")
        db.execute("""INSERT INTO agent_exchange_messages
            (id, exchange_id, sequence, agent_id, display_name, avatar_emoji, content)
            VALUES ('old-message', 'legacy-peer', 1, 'agent-a', '旧分身', '🌟', '旧交流内容不能丢失')""")
        db.execute("""INSERT INTO agent_exchange_calls
            (id, exchange_id, ordinal, kind, status, reserved_tokens, input_limit, output_limit, input_tokens, output_tokens)
            VALUES ('call-1', 'legacy-peer', 1, 'turn', 'succeeded', 1400, 1144, 256, 12, 8)""")
        db.execute("""INSERT INTO agent_exchange_calls
            (id, exchange_id, ordinal, kind, reserved_tokens, input_limit, output_limit)
            VALUES ('call-2', 'legacy-peer', 2, 'turn', 1500, 1244, 256)""")
        before = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
                  for table in ("agent_exchanges", "agent_exchange_messages", "agent_exchange_calls")}

    asyncio.run(migrate(exchange_store.migrate_official_exchanges_schema))
    asyncio.run(migrate(exchange_store.migrate_official_exchanges_schema))
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for table, old_rows in before.items():
            after = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
            expected = [{**row, "kind": "peer"} for row in old_rows] if table == "agent_exchanges" else old_rows
            assert after == expected
        assert dict(db.execute("SELECT version, COUNT(*) FROM schema_migrations GROUP BY version")) == {
            exchange_store.MIGRATION_VERSION: 1, exchange_store.OFFICIAL_MIGRATION_VERSION: 1,
        }
        # The active-pair protection must survive SQLite's table rebuild.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO agent_exchanges
                (id, initiator_username, recipient_username, initiator_agent_id, recipient_agent_id,
                 pair_key, initiator_json, recipient_json, topic, max_turns, token_budget)
                VALUES ('duplicate-peer', 'old-a', 'old-b', 'agent-a', 'agent-b', 'old-pair', '{}', '{}',
                        '重复邀请', 2, 80000)""")


def test_official_catalog_is_allowlisted_and_creates_no_phantom_accounts(
    client, owner, official_cards, exchange_model,
):
    import database

    assert len(official_cards) == 3
    assert len({card["id"] for card in official_cards}) == 3
    for card in official_cards:
        assert card["display_name"] and card["bio"] and card["avatar_emoji"]
        assert set(card) == {"id", "display_name", "bio", "avatar_emoji", "is_public", "kind", "suggested_topic", "provider", "model", "model_label"}
        assert card["kind"] == "official" and card["is_public"] is True
    assert client.get("/agents", headers=owner["headers"]).json()["agents"] == []
    for card in official_cards:
        assert client.get(f"/agents/{card['id']}", headers=owner["headers"]).status_code == 404
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT username FROM users").fetchall() == [(owner["headers"]["X-Dev-User"],)]
        assert db.execute("SELECT id FROM agents").fetchall() == [(owner["agent"]["id"],)]
    assert exchange_model.calls == []


@pytest.mark.parametrize("card_index,requested_turns", [(0, 3), (1, None)])
def test_private_owner_can_complete_official_exchange_without_becoming_public(
    client, owner, official_cards, exchange_model, card_index, requested_turns,
):
    import database

    before = client.get("/agents/me", headers=owner["headers"]).json()["agent"]
    created = _start(client, owner, official_cards[card_index], max_turns=requested_turns)
    turns = requested_turns or 99
    exchange = created["exchange"]
    assert exchange["kind"] == "official"
    assert exchange["status"] == "running"
    assert exchange["viewer_role"] == "initiator"
    assert exchange["initiator"]["id"] == owner["agent"]["id"]
    assert exchange["recipient"]["id"] == official_cards[card_index]["id"]
    assert created["messages"] == []
    final = _wait(client, owner, exchange["id"])
    assert final["exchange"]["status"] == "completed"
    assert final["exchange"]["max_turns"] == final["exchange"]["turn_count"] == turns
    assert [message["sequence"] for message in final["messages"]] == list(range(1, turns + 1))
    assert [message["agent_id"] for message in final["messages"]] == [
        owner["agent"]["id"] if index % 2 == 0 else official_cards[card_index]["id"]
        for index in range(turns)
    ]
    assert final["exchange"]["summary"] == "模拟交流总结"
    assert len(exchange_model.calls) == turns + 1
    assert [call["provider"] for call in exchange_model.calls] == [
        "main" if index % 2 == 0 else "official" for index in range(turns)
    ] + ["official"]
    usage = final["exchange"]["usage"]
    assert usage["model_calls"] == usage["max_model_calls"] == turns + 1
    assert usage["input_tokens"] == 12 * (turns + 1) and usage["output_tokens"] == 8 * (turns + 1)
    assert usage["total_tokens"] == usage["budget_used"] == 20 * (turns + 1)
    assert usage["reserved_tokens"] == 0 and usage["estimated"] is False
    assert usage["token_budget"] == 14_000_000
    assert client.get("/agents/me", headers=owner["headers"]).json()["agent"] == before
    assert _detail(client, owner, exchange["id"]) == final
    records = client.get("/agent-exchanges", headers=owner["headers"]).json()["exchanges"]
    # Lists carry a compact presence marker; the manuscript is available only
    # in detail/download responses so a long document is not repeated per row.
    assert records == [{key: value for key, value in final["exchange"].items() if key != "artifact"}]
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 1
    assert len(exchange_model.calls) == turns + 1


@pytest.mark.parametrize("payload", [
    {"kind": "official"}, {"kind": "peer"}, {"is_public": True},
    {"owner_username": "forged-owner"}, {"target_agent_id": "forged-target"},
    {"max_turns": 1}, {"max_turns": 100}, {"max_turns": True}, {"max_turns": 2.5},
    {"max_turns": "99"}, {"max_turns": None}, {"max_turns": 2.0},
    {"topic": " "}, {"topic": "\n\t　"}, {"topic": "x" * 10001},
])
def test_official_create_rejects_spoofed_fields_and_invalid_limits(
    client, owner, official_cards, exchange_model, payload,
):
    response = client.post("/agent-exchanges/official", headers=owner["headers"], json={
        "official_agent_id": official_cards[0]["id"], "topic": "明确的交流主题", "max_turns": 2, **payload,
    })
    assert response.status_code == 422, response.text
    assert client.get("/agent-exchanges", headers=owner["headers"]).json()["exchanges"] == []
    assert exchange_model.calls == []


def test_official_topic_over_three_hundred_characters_reaches_both_speakers_and_summary(
    client, owner, official_cards, exchange_model,
):
    end_marker = "LONG_TOPIC_FINAL_DETAIL_🎥"
    topic = "剧情背景" * 70 + end_marker
    assert 300 < len(topic) < 10000
    created = _start(client, owner, official_cards[0], topic=topic)
    assert created["exchange"]["topic"] == topic
    final = _wait(client, owner, created["exchange"]["id"])
    assert final["exchange"]["status"] == "completed"
    assert final["exchange"]["topic"] == topic
    assert [call["provider"] for call in exchange_model.calls] == ["main", "official", "official"]
    for call in exchange_model.calls:
        payload = json.loads(call["messages"][-1]["content"])
        assert payload["topic"] == topic and payload["topic"].endswith(end_marker)


def test_peer_and_official_creation_cannot_impersonate_each_others_targets(
    client, owner, official_cards, exchange_model,
):
    client.put("/agents/me", headers=owner["headers"], json={"is_public": True})
    other_headers = {"X-Dev-User": "real_peer_target"}
    real = client.put("/agents/me", headers=other_headers, json={"is_public": True}).json()["agent"]
    for target in (official_cards[0]["id"], official_cards[1]["id"]):
        response = client.post("/agent-exchanges", headers=owner["headers"], json={
            "target_agent_id": target, "topic": "不能给官方发真人邀请", "max_turns": 2,
        })
        assert response.status_code == 404, response.text
    for target in ("unknown-official-agent", real["id"]):
        response = client.post("/agent-exchanges/official", headers=owner["headers"], json={
            "official_agent_id": target, "topic": "只允许注册的官方分身", "max_turns": 2,
        })
        assert response.status_code == 404, response.text
    for extra in ({"kind": "official"}, {"is_public": True}):
        response = client.post("/agent-exchanges", headers=owner["headers"], json={
            "target_agent_id": real["id"], "topic": "不能伪装交流类型", "max_turns": 2, **extra,
        })
        assert response.status_code == 422, response.text
    assert exchange_model.calls == []


def test_official_exchange_has_no_recipient_account_to_accept_or_reject(
    client, owner, official_cards, exchange_model,
):
    exchange_model.block(1)
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        for action in ("accept", "reject"):
            response = client.post(f"/agent-exchanges/{exchange_id}/{action}", headers=owner["headers"])
            assert response.status_code == 409, response.text
        # A real account choosing the registry id as its username owns no official side.
        impostor = {"X-Dev-User": official_cards[0]["id"]}
        assert client.get(f"/agent-exchanges/{exchange_id}", headers=impostor).status_code == 404
        assert client.get("/agent-exchanges", headers=impostor).json()["exchanges"] == []
        for action in ("accept", "reject", "stop"):
            assert client.post(f"/agent-exchanges/{exchange_id}/{action}", headers=impostor).status_code == 404
    finally:
        exchange_model.release.set()
    assert _wait(client, owner, exchange_id)["exchange"]["status"] == "completed"


def test_two_users_can_run_with_the_same_official_without_sharing_records_or_quota(
    client, owner, official_cards, exchange_model,
):
    other_headers = {"X-Dev-User": "other_official_owner"}
    other = {"headers": other_headers, "agent": client.get("/agents/me", headers=other_headers).json()["agent"]}
    exchange_model.block(1)
    first_id = _start(client, owner, official_cards[0], topic="OWNER_ONE_ONLY_TOPIC")["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        second_id = _start(client, other, official_cards[0], topic="OWNER_TWO_ONLY_TOPIC")["exchange"]["id"]
        second = _wait(client, other, second_id)
        assert second["exchange"]["status"] == "completed"
        for stranger, hidden_id in ((other, first_id), (owner, second_id)):
            assert client.get(f"/agent-exchanges/{hidden_id}", headers=stranger["headers"]).status_code == 404
            assert client.post(f"/agent-exchanges/{hidden_id}/stop", headers=stranger["headers"]).status_code == 404
        assert [record["id"] for record in client.get("/agent-exchanges", headers=other_headers).json()["exchanges"]] == [second_id]
        assert _detail(client, owner, first_id)["exchange"]["status"] == "running"
    finally:
        exchange_model.release.set()
    first = _wait(client, owner, first_id)
    assert first["exchange"]["status"] == "completed"
    assert first["messages"] != second["messages"]
    assert len(exchange_model.calls) == 6
    for call in exchange_model.calls:
        context = json.dumps(call["messages"])
        assert ("OWNER_ONE_ONLY_TOPIC" in context) != ("OWNER_TWO_ONLY_TOPIC" in context)


@pytest.mark.parametrize("first_kind", ["official", "peer"])
def test_official_and_peer_share_the_real_owners_running_limit(
    client, owner, official_cards, exchange_model, first_kind,
):
    client.put("/agents/me", headers=owner["headers"], json={"is_public": True})
    peer_headers = {"X-Dev-User": "shared_limit_peer"}
    peer = client.put("/agents/me", headers=peer_headers, json={"is_public": True}).json()["agent"]
    invitation = client.post("/agent-exchanges", headers=owner["headers"], json={
        "target_agent_id": peer["id"], "topic": "真人间交流", "max_turns": 2,
    })
    assert invitation.status_code == 201, invitation.text
    peer_id = invitation.json()["exchange"]["id"]
    official_payload = {"official_agent_id": official_cards[0]["id"], "topic": "官方体验", "max_turns": 2}
    exchange_model.block(1)
    if first_kind == "official":
        first_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    else:
        first_id = peer_id
        assert client.post(f"/agent-exchanges/{peer_id}/accept", headers=peer_headers).status_code == 200
    try:
        assert exchange_model.started.wait(timeout=10)
        blocked = (client.post(f"/agent-exchanges/{peer_id}/accept", headers=peer_headers)
                   if first_kind == "official"
                   else client.post("/agent-exchanges/official", headers=owner["headers"], json=official_payload))
        assert blocked.status_code == 409, blocked.text
        assert len(exchange_model.calls) == 1
        assert client.post(f"/agent-exchanges/{first_id}/stop", headers=owner["headers"]).status_code == 200
    finally:
        exchange_model.release.set()
    _wait(client, owner, first_id)
    if first_kind == "official":
        assert client.post(f"/agent-exchanges/{peer_id}/accept", headers=peer_headers).status_code == 200
        final_id = peer_id
    else:
        final_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    assert _wait(client, owner, final_id)["exchange"]["status"] == "completed"


def test_concurrent_official_starts_for_one_owner_reserve_one_running_slot(
    client, owner, official_cards, exchange_model,
):
    barrier = Barrier(2)
    exchange_model.block(1)

    def start_together(card):
        barrier.wait(timeout=10)
        return client.post("/agent-exchanges/official", headers=owner["headers"], json={
            "official_agent_id": card["id"], "topic": "并发体验", "max_turns": 2,
        })

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(start_together, official_cards[:2]))
        assert sorted(response.status_code for response in responses) == [201, 409]
        assert exchange_model.started.wait(timeout=10)
        assert len(exchange_model.calls) == 1
    finally:
        exchange_model.release.set()
    exchange_id = next(response.json()["exchange"]["id"] for response in responses if response.status_code == 201)
    assert _wait(client, owner, exchange_id)["exchange"]["status"] == "completed"


@pytest.mark.parametrize("blocked_call", [1, 3], ids=["reply", "summary"])
def test_official_stop_discards_inflight_text_and_prevents_more_generation(
    client, owner, official_cards, exchange_model, blocked_call,
):
    exchange_model.block(blocked_call)
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        stopped = client.post(f"/agent-exchanges/{exchange_id}/stop", headers=owner["headers"])
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["exchange"]["status"] == "stopped"
    finally:
        exchange_model.release.set()
    final = _wait(client, owner, exchange_id)
    assert final["exchange"]["status"] == "stopped"
    assert len(final["messages"]) == (0 if blocked_call == 1 else 2)
    assert final["exchange"]["summary"] == ""
    assert final["exchange"]["usage"]["reserved_tokens"] == 0
    assert len(exchange_model.calls) == blocked_call


def test_hiding_own_agent_does_not_revoke_a_private_official_experience(
    client, owner, official_cards, exchange_model,
):
    client.put("/agents/me", headers=owner["headers"], json={"is_public": True})
    exchange_model.block(1)
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        response = client.put("/agents/me", headers=owner["headers"], json={"is_public": False})
        assert response.status_code == 200, response.text
        assert _detail(client, owner, exchange_id)["exchange"]["status"] == "running"
    finally:
        exchange_model.release.set()
    assert _wait(client, owner, exchange_id)["exchange"]["status"] == "completed"
    assert client.get("/agents/me", headers=owner["headers"]).json()["agent"]["is_public"] is False


def test_official_exchange_cannot_recreate_deleted_owners_or_records(
    client, owner, official_cards, exchange_model,
):
    import database
    import services.exchange_service as exchange_service

    exchange_model.block(1)
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        response = client.request("DELETE", "/account", headers=owner["headers"], json={
            "confirmation": owner["headers"]["X-Dev-User"],
        })
        assert response.status_code == 200, response.text
    finally:
        exchange_model.release.set()
    client.portal.call(exchange_service.wait_for_exchange, exchange_id)
    with sqlite3.connect(database.DB_PATH) as db:
        for table in ("users", "agents", "agent_exchanges", "agent_exchange_messages", "agent_exchange_calls"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert len(exchange_model.calls) == 1


def test_official_restart_stops_without_replay_and_settles_uncertain_usage(
    client, owner, official_cards, exchange_model,
):
    import exchange_store

    exchange_model.block(1)
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        before = _detail(client, owner, exchange_id)["exchange"]["usage"]
        client.portal.call(exchange_store.recover_interrupted_exchanges)
        stopped = _detail(client, owner, exchange_id)["exchange"]
        assert stopped["status"] == "stopped" and "重启" in stopped["error"]
        assert stopped["usage"]["estimated"] is True
        assert stopped["usage"]["reserved_tokens"] == 0
        assert stopped["usage"]["total_tokens"] == before["reserved_tokens"]
        client.portal.call(exchange_store.recover_interrupted_exchanges)
        assert _detail(client, owner, exchange_id)["exchange"]["usage"] == stopped["usage"]
    finally:
        exchange_model.release.set()
    final = _wait(client, owner, exchange_id)
    assert final["exchange"]["usage"] == stopped["usage"]
    assert final["messages"] == [] and final["exchange"]["summary"] == ""
    assert len(exchange_model.calls) == 1


def test_official_context_excludes_all_private_memory_personality_and_chat(
    client, owner, official_cards, exchange_model,
):
    import agent_store
    import database

    username = owner["headers"]["X-Dev-User"]
    canaries = ["OFFICIAL_PRIVATE_PERSONALITY", "OFFICIAL_PRIVATE_MEMORY", "OFFICIAL_PRIVATE_CHAT", "OFFICIAL_LEGACY_PROFILE"]
    response = client.put("/agents/me", headers=owner["headers"], json={"personality": canaries[0]})
    assert response.status_code == 200, response.text
    asyncio.run(agent_store.update_memory(username, {"interests": [canaries[1]]}))
    conversation = asyncio.run(agent_store.create_conversation(username, "私人会话"))
    assert asyncio.run(database.save_message(username, "user", canaries[2], conversation_id=conversation["id"]))
    asyncio.run(database.update_profile(username, {"needs": [canaries[3]]}))
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    final = _wait(client, owner, exchange_id)
    assert final["exchange"]["status"] == "completed"
    for call in exchange_model.calls:
        context = json.dumps(call["messages"], ensure_ascii=False)
        assert all(canary not in context for canary in canaries)
        assert username not in context
        assert "私有星球" in context and official_cards[0]["display_name"] in context
        assert "没有真人主人" in context
        assert "双方主人授权" not in context
    serialized = json.dumps(final)
    assert all(canary not in serialized for canary in canaries)
    assert "owner_username" not in serialized
    assert asyncio.run(agent_store.get_memory_snapshot(username))["profile"] == {"interests": [canaries[1]]}
