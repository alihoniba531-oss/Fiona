# -*- coding: utf-8 -*-

import asyncio


def test_concurrent_match_and_card_creation_is_idempotent(tmp_path, monkeypatch):
    import aiosqlite
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "match-race.db"))

    async def scenario():
        await database.init_db()
        await database.get_or_create_user("race_a")
        await database.get_or_create_user("race_b")
        matches = await asyncio.gather(*(
            database.save_match("race_a", "race_b") for _ in range(8)
        ))
        cards = await asyncio.gather(*(
            database.save_pending_match(
                "race_a", "race_b", "topic", "reason", "话题连接", []
            )
            for _ in range(8)
        ))
        async with aiosqlite.connect(database.DB_PATH) as db:
            match_count = (
                await (await db.execute("SELECT COUNT(*) FROM matches")).fetchone()
            )[0]
            card_count = (
                await (await db.execute("SELECT COUNT(*) FROM pending_matches")).fetchone()
            )[0]
        return matches, cards, match_count, card_count

    matches, cards, match_count, card_count = asyncio.run(scenario())
    assert matches.count(True) == 1
    assert cards.count(True) == 1
    assert (match_count, card_count) == (1, 1)


def test_match_response_requires_an_existing_recommendation(client, dev_headers):
    import aiosqlite
    import database

    asyncio.run(database.get_or_create_user("smoke_tester"))
    asyncio.run(database.get_or_create_user("unsolicited_peer"))

    response = client.post(
        "/match/response",
        headers=dev_headers,
        json={"peer": "unsolicited_peer", "response": "accept"},
    )

    assert response.status_code == 404

    async def count_matches():
        async with aiosqlite.connect(database.DB_PATH) as db:
            return (await (await db.execute("SELECT COUNT(*) FROM matches")).fetchone())[0]

    assert asyncio.run(count_matches()) == 0


def test_match_response_limits_greeting_and_updates_real_match(client, dev_headers):
    import aiosqlite
    import database

    async def seed():
        await database.get_or_create_user("smoke_tester")
        await database.get_or_create_user("real_peer")
        assert await database.save_match("smoke_tester", "real_peer") is True

    asyncio.run(seed())
    too_long = client.post(
        "/match/response",
        headers=dev_headers,
        json={"peer": "real_peer", "response": "accept", "greeting": "x" * 501},
    )
    assert too_long.status_code == 422

    accepted = client.post(
        "/match/response",
        headers=dev_headers,
        json={"peer": "real_peer", "response": "accept", "greeting": "你好"},
    )
    assert accepted.status_code == 200

    async def read_match():
        async with aiosqlite.connect(database.DB_PATH) as db:
            return await (
                await db.execute(
                    "SELECT response_a, greeting_a FROM matches WHERE user_a = ?",
                    ("smoke_tester",),
                )
            ).fetchone()

    assert asyncio.run(read_match()) == ("accept", "你好")
