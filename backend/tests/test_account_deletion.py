# -*- coding: utf-8 -*-
import asyncio


def test_account_deletion_removes_relations_and_uploads(client, dev_headers, tmp_path, monkeypatch):
    import aiosqlite
    import database
    from utils import media

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(upload_dir))
    (upload_dir / "chat.png").write_bytes(b"chat")
    (upload_dir / "post.png").write_bytes(b"post")

    async def seed():
        await database.get_or_create_user("smoke_tester")
        await database.get_or_create_user("peer_user")
        await database.save_message("smoke_tester", "user", "private", "/uploads/chat.png")
        await database.save_post(
            "anon-owner",
            "/uploads/post.png",
            "image",
            "caption",
            ["日常"],
            "smoke_tester",
        )
        await database.save_post(
            "anon-peer",
            "/uploads/peer.png",
            "image",
            "peer caption",
            ["旅行"],
            "peer_user",
        )
        await database.like_post(2, "smoke_tester")
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """INSERT INTO matches (user_a, user_b, response_a, response_b)
                   VALUES ('smoke_tester', 'peer_user', 'accept', 'accept')"""
            )
            await db.execute(
                "INSERT INTO peer_messages (room_id, sender, content) VALUES (?, ?, ?)",
                ("peer_user__smoke_tester", "smoke_tester", "hello"),
            )
            await db.execute(
                """INSERT INTO pending_matches (username, peer_username)
                   VALUES ('peer_user', 'smoke_tester')"""
            )
            await db.execute(
                "INSERT INTO post_likes (post_id, username) VALUES (1, 'smoke_tester')"
            )
            await db.execute(
                "INSERT INTO user_tag_prefs (username, tag, score) VALUES ('smoke_tester', '日常', 1)"
            )
            await db.execute(
                """INSERT INTO user_time_tag_prefs (username, time_slot, tag, score)
                   VALUES ('smoke_tester', '周末-上午', '日常', 1)"""
            )
            await db.execute("INSERT INTO user_states (username) VALUES ('smoke_tester')")
            await db.execute(
                "INSERT INTO events (username, event_type) VALUES ('smoke_tester', 'chat')"
            )
            await db.execute(
                "INSERT INTO invite_codes (code, username) VALUES ('DELETE01', 'smoke_tester')"
            )
            await db.commit()

    asyncio.run(seed())
    response = client.request(
        "DELETE",
        "/account",
        headers=dev_headers,
        json={"confirmation": "smoke_tester"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["file_cleanup_complete"] is True
    assert not (upload_dir / "chat.png").exists()
    assert not (upload_dir / "post.png").exists()
    assert asyncio.run(database.get_pending_upload_cleanup()) == []
    assert asyncio.run(database.get_post(2))["likes"] == 0

    async def remaining_counts():
        tables_and_where = {
            "users": "username='smoke_tester'",
            "messages": "username='smoke_tester'",
            "matches": "user_a='smoke_tester' OR user_b='smoke_tester'",
            "peer_messages": "sender='smoke_tester' OR room_id='peer_user__smoke_tester'",
            "pending_matches": "username='smoke_tester' OR peer_username='smoke_tester'",
            "posts": "owner_username='smoke_tester'",
            "post_likes": "username='smoke_tester'",
            "user_tag_prefs": "username='smoke_tester'",
            "user_time_tag_prefs": "username='smoke_tester'",
            "user_states": "username='smoke_tester'",
            "events": "username='smoke_tester'",
            "invite_codes": "username='smoke_tester'",
        }
        counts = {}
        async with aiosqlite.connect(database.DB_PATH) as db:
            for table, where in tables_and_where.items():
                async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}") as cursor:
                    counts[table] = (await cursor.fetchone())[0]
        return counts

    assert all(count == 0 for count in asyncio.run(remaining_counts()).values())

    # 删除与后台任务并发时，迟到的写入不能重新制造孤立个人数据。
    assert asyncio.run(database.save_message("smoke_tester", "assistant", "late")) is False
    assert asyncio.run(database.save_match("smoke_tester", "peer_user")) is False
    assert asyncio.run(database.save_pending_match(
        "smoke_tester",
        "peer_user",
        "late",
        "late",
        "话题连接",
        [],
    )) is False


def test_account_deletion_requires_exact_username(client, dev_headers):
    import database

    asyncio.run(database.get_or_create_user("smoke_tester"))
    response = client.request(
        "DELETE",
        "/account",
        headers=dev_headers,
        json={"confirmation": "wrong"},
    )
    assert response.status_code == 400
    assert asyncio.run(database.get_session_version("smoke_tester")) is not None
