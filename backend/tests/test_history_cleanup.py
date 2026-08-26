# -*- coding: utf-8 -*-

import asyncio


def test_delete_message_removes_unreferenced_upload(client, dev_headers, tmp_path, monkeypatch):
    import aiosqlite
    import database
    from utils import media

    upload_dir = tmp_path / "message-uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(upload_dir))
    attachment = upload_dir / "one.png"
    attachment.write_bytes(b"private image")

    async def seed():
        await database.get_or_create_user("smoke_tester")
        await database.save_message(
            "smoke_tester", "user", "with image", "/uploads/one.png"
        )
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT id FROM messages WHERE username = ?", ("smoke_tester",)
            ) as cursor:
                return (await cursor.fetchone())[0]

    message_id = asyncio.run(seed())
    response = client.delete(f"/message/{message_id}", headers=dev_headers)

    assert response.status_code == 200
    assert not attachment.exists()
    assert asyncio.run(database.get_pending_upload_cleanup()) == []


def test_clear_history_keeps_upload_still_referenced_by_post(
    client, dev_headers, tmp_path, monkeypatch
):
    import database
    from utils import media

    upload_dir = tmp_path / "shared-uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(upload_dir))
    shared = upload_dir / "shared.png"
    private = upload_dir / "private.png"
    shared.write_bytes(b"shared")
    private.write_bytes(b"private")

    async def seed():
        await database.get_or_create_user("smoke_tester")
        await database.save_message(
            "smoke_tester", "user", "shared", "/uploads/shared.png"
        )
        await database.save_message(
            "smoke_tester", "user", "private", "/uploads/private.png"
        )
        await database.save_post(
            "anon-shared",
            "/uploads/shared.png",
            "image",
            "still referenced",
            ["日常"],
            "smoke_tester",
        )

    asyncio.run(seed())
    response = client.delete("/history", headers=dev_headers)

    assert response.status_code == 200
    assert shared.exists()
    assert not private.exists()
    assert asyncio.run(database.get_pending_upload_cleanup()) == []
