"""Identity migration, authorization, deletion and memory revision regressions."""
import asyncio
import sqlite3

import pytest


def _run(coroutine):
    return asyncio.run(coroutine)


def _legacy_db(path, orphan=False):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, profile_json TEXT DEFAULT '{}')")
        db.execute(
            """CREATE TABLE messages (id INTEGER PRIMARY KEY, username TEXT, role TEXT,
               content TEXT, image_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
        )
        if not orphan:
            db.execute("INSERT INTO users (username, profile_json) VALUES ('old_user', ?)", ('{"city":"private city"}',))
        db.execute("INSERT INTO messages (username, role, content, image_path) VALUES ('old_user','user','legacy text','/uploads/legacy.png')")


def test_legacy_migration_backfills_once_and_keeps_private_data(tmp_path, monkeypatch):
    import agent_store
    import database
    import exchange_store

    path = tmp_path / "legacy.db"
    _legacy_db(path)
    monkeypatch.setattr(database, "DB_PATH", str(path))
    _run(database.init_db())
    first = _run(agent_store.resolve_chat_conversation("old_user"))
    _run(database.init_db())
    second = _run(agent_store.resolve_chat_conversation("old_user"))
    assert first == second
    assert second["agent"]["is_public"] is False
    assert second["agent"]["bio"] == ""
    assert second["agent"]["personality"] == ""
    assert "private_memory_json" not in second["agent"]
    assert _run(agent_store.get_memory_snapshot("old_user"))["profile"] == {"city": "private city"}
    assert _run(database.get_profile("old_user")) == {"city": "private city"}
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT content, image_path, conversation_id, agent_id FROM messages").fetchone()
        assert row == ("legacy text", "/uploads/legacy.png", first["conversation"]["id"], first["agent"]["id"])
        assert db.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
        versions = dict(db.execute("SELECT version, COUNT(*) FROM schema_migrations GROUP BY version"))
        assert versions == {
            agent_store.MIGRATION_VERSION: 1,
            exchange_store.MIGRATION_VERSION: 1,
            exchange_store.OFFICIAL_MIGRATION_VERSION: 1,
            exchange_store.EXTENDED_OFFICIAL_MIGRATION_VERSION: 1,
            exchange_store.WORKFLOW_MIGRATION_VERSION: 1,
        }


def test_migration_failure_rolls_back_and_can_retry(tmp_path, monkeypatch):
    import database

    path = tmp_path / "orphan.db"
    _legacy_db(path, orphan=True)
    monkeypatch.setattr(database, "DB_PATH", str(path))
    with pytest.raises(RuntimeError, match="without an existing owner"):
        _run(database.init_db())
    with sqlite3.connect(path) as db:
        assert "conversation_id" not in {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert db.execute("SELECT content FROM messages").fetchone() == ("legacy text",)
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='agents'").fetchall()
        db.execute("INSERT INTO users (username) VALUES ('old_user')")
    _run(database.init_db())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT conversation_id FROM messages").fetchone()[0]


def test_one_agent_and_default_conversation_under_concurrent_creation(client):
    import agent_store
    import database

    async def race():
        await database.get_or_create_user("parallel_user")
        return await asyncio.gather(*[
            agent_store.resolve_chat_conversation("parallel_user") for _ in range(8)
        ])

    contexts = _run(race())
    assert len({ctx["agent"]["id"] for ctx in contexts}) == 1
    assert len({ctx["conversation"]["id"] for ctx in contexts}) == 1
    with pytest.raises(agent_store.ResourceNotFound):
        _run(agent_store.resolve_chat_conversation("never_existed"))
    assert _run(database.get_session_version("never_existed")) is None


def test_public_agent_cards_are_opt_in_and_allowlisted(client, dev_headers):
    own = client.get("/agents/me", headers=dev_headers).json()["agent"]
    other = {"X-Dev-User": "viewer"}
    assert client.get("/agents", headers=other).json() == {"agents": []}
    assert client.get(f"/agents/{own['id']}", headers=other).status_code == 404
    saved = client.put("/agents/me", headers=dev_headers, json={
        "display_name": " 小星 ", "bio": "公开介绍", "personality": "private personality",
        "avatar_emoji": "🌌", "is_public": True,
    }).json()["agent"]
    assert saved["id"] == own["id"]
    assert saved["display_name"] == "小星"
    assert saved["owner_username"] == "smoke_tester"
    public = client.get(f"/agents/{own['id']}", headers=other).json()["agent"]
    assert set(public) == {"id", "display_name", "bio", "avatar_emoji", "is_public", "created_at"}
    assert client.get("/agents", headers=other).json()["agents"] == [public]
    assert client.get(f"/agents/{own['id']}", headers=dev_headers).json()["agent"]["personality"] == "private personality"
    assert client.post("/conversations", headers=other, json={"agent_id": own["id"]}).status_code == 404
    client.put("/agents/me", headers=dev_headers, json={"is_public": False})
    assert client.get(f"/agents/{own['id']}", headers=other).status_code == 404


@pytest.mark.parametrize("payload", [
    {"display_name": " "}, {"display_name": "x" * 41}, {"bio": "x" * 301},
    {"personality": "x" * 2001}, {"avatar_emoji": "x" * 17},
    {"owner_username": "someone_else"}, {"id": "someone_else"},
])
def test_agent_update_rejects_invalid_fields(client, dev_headers, payload):
    assert client.put("/agents/me", headers=dev_headers, json=payload).status_code == 422


def test_conversation_history_limit_ownership_and_legacy_compatibility(client, dev_headers):
    import database

    first = client.get("/conversations", headers=dev_headers).json()["conversations"][0]
    response = client.post("/conversations", headers=dev_headers, json={"title": "研究"})
    assert response.status_code == 201
    second = response.json()["conversation"]

    async def seed():
        await database.save_message("smoke_tester", "user", "legacy default")
        for index in range(5):
            assert await database.save_message("smoke_tester", "user", f"topic-{index}", conversation_id=second["id"])

    _run(seed())
    page = client.get(f"/conversations/{second['id']}/messages?limit=2", headers=dev_headers).json()
    assert page["has_more"] is True and page["limit"] == 2
    assert [message["content"] for message in page["messages"]] == ["topic-3", "topic-4"]
    assert _run(database.count_messages("smoke_tester")) == 6
    assert _run(database.count_messages("smoke_tester", conversation_id=first["id"])) == 1
    assert len(_run(database.get_messages("smoke_tester"))) == 6
    other = {"X-Dev-User": "other_user"}
    assert client.get(f"/conversations/{second['id']}/messages", headers=other).status_code == 404
    assert client.delete(f"/conversations/{second['id']}", headers=other).status_code == 404
    assert all(row["id"] != second["id"] for row in client.get("/conversations", headers=other).json()["conversations"])


def test_conversation_deletion_preserves_shared_uploads_and_rejects_late_writes(client, dev_headers, tmp_path, monkeypatch):
    import agent_store
    import database
    from utils import media

    upload_dir = tmp_path / "shared_uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(upload_dir))
    shared = upload_dir / "shared.png"
    shared.write_bytes(b"not opened by test")
    first = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    second = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    _run(database.save_message("smoke_tester", "user", "one", "/uploads/shared.png", first))
    _run(database.save_message("smoke_tester", "user", "two", "/uploads/shared.png", second))
    assert client.delete(f"/conversations/{first}", headers=dev_headers).status_code == 200
    assert shared.exists()
    assert _run(database.save_message("smoke_tester", "assistant", "late", conversation_id=first)) is False
    with pytest.raises(agent_store.ResourceNotFound):
        _run(database.get_messages("smoke_tester", conversation_id=first))
    assert client.delete(f"/conversations/{second}", headers=dev_headers).json()["file_cleanup_complete"] is True
    assert not shared.exists()
    assert _run(database.get_pending_upload_cleanup()) == []


def test_deleting_default_clears_mode_and_pending_without_resurrecting_id(client, dev_headers):
    import database
    from intent_router import get_pending, set_pending
    from mode_switcher import get_user_mode, set_user_mode

    old = client.get("/conversations", headers=dev_headers).json()["conversations"][0]["id"]
    state_key = ("smoke_tester", old)
    set_pending(state_key, {"intent": "route", "params": {}, "missing": ["origin"]})
    set_user_mode(state_key, "mirror", "manual")
    assert client.delete(f"/conversations/{old}", headers=dev_headers).status_code == 200
    assert get_pending(state_key) is None
    assert get_user_mode(state_key)["mode"] == "friend"
    fresh = client.get("/conversations", headers=dev_headers).json()["conversations"][0]["id"]
    assert fresh != old
    assert _run(database.save_message("smoke_tester", "assistant", "late", conversation_id=old)) is False


def test_auto_titles_keep_explicit_titles_and_name_image_conversations(client, dev_headers):
    import database

    automatic = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    explicit = client.post("/conversations", headers=dev_headers, json={"title": "新的交流"}).json()["conversation"]["id"]
    image = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    _run(database.save_message("smoke_tester", "user", "旅行规划\n后续内容", conversation_id=automatic))
    _run(database.save_message("smoke_tester", "user", "后续消息不改标题", conversation_id=automatic))
    _run(database.save_message("smoke_tester", "user", "自定义标题不改", conversation_id=explicit))
    _run(database.save_message("smoke_tester", "user", "[发了一张图片]", "/uploads/test.png", image))
    titles = {row["id"]: row["title"] for row in client.get("/conversations", headers=dev_headers).json()["conversations"]}
    assert titles[automatic] == "旅行规划"
    assert titles[explicit] == "新的交流"
    assert titles[image] == "图片交流"


def test_memory_revision_blocks_cleared_or_deleted_conversation_results(client, dev_headers):
    import agent_store
    import database

    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]["id"]
    _run(database.update_profile("smoke_tester", {"city": "legacy social profile"}))
    _run(agent_store.update_memory("smoke_tester", {"interests": ["private memory"]}, conversation_id=conversation))
    assert client.get("/agents/me/memory", headers=dev_headers).json() == {"profile": {"interests": ["private memory"]}}
    old = _run(agent_store.get_memory_snapshot("smoke_tester", conversation))
    assert client.delete("/agents/me/memory", headers=dev_headers).json() == {"status": "cleared"}
    assert not _run(agent_store.update_memory("smoke_tester", {"interests": ["stale"]}, old["revision"], conversation))
    assert client.get("/profile", headers=dev_headers).json()["profile"] == {}
    current = _run(agent_store.get_memory_snapshot("smoke_tester", conversation))
    assert current["revision"] > old["revision"]
    assert _run(agent_store.update_memory("smoke_tester", {"city": "new"}, current["revision"], conversation))
    latest = _run(agent_store.get_memory_snapshot("smoke_tester", conversation))
    client.delete(f"/conversations/{conversation}", headers=dev_headers)
    assert not _run(agent_store.update_memory("smoke_tester", {"city": "late"}, latest["revision"], conversation))
    assert _run(agent_store.get_memory_snapshot("smoke_tester"))["profile"] == {"city": "new"}
    assert _run(database.get_profile("smoke_tester")) == {}


def test_private_memory_never_updates_matcher_social_profile(client, dev_headers):
    import agent_store
    import database

    _run(database.get_or_create_user("smoke_tester"))
    _run(database.update_profile("smoke_tester", {"interests": ["old public interest"]}))
    client.get("/agents/me", headers=dev_headers)
    assert _run(agent_store.get_memory_snapshot("smoke_tester"))["profile"] == {"interests": ["old public interest"]}
    assert _run(agent_store.update_memory("smoke_tester", {"interests": ["private new secret"]}))
    assert _run(database.get_all_profiles())[0]["profile"] == {"interests": ["old public interest"]}
    # Later edits to the legacy social profile cannot overwrite an established private memory.
    _run(database.update_profile("smoke_tester", {"interests": ["changed social profile"]}))
    assert _run(agent_store.get_memory_snapshot("smoke_tester"))["profile"] == {"interests": ["private new secret"]}


def test_account_deletion_removes_identity_and_rejects_background_memory(client, dev_headers):
    import agent_store
    import database

    agent = client.get("/agents/me", headers=dev_headers).json()["agent"]
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]
    assert client.request("DELETE", "/account", headers=dev_headers, json={"confirmation": "smoke_tester"}).status_code == 200
    assert not _run(database.save_message("smoke_tester", "assistant", "late", conversation_id=conversation["id"]))
    assert not _run(database.update_profile("smoke_tester", {"city": "late"}))
    assert not _run(agent_store.update_memory("smoke_tester", {"city": "late"}))
    with pytest.raises(agent_store.ResourceNotFound):
        _run(agent_store.get_my_agent("smoke_tester"))
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT id FROM agents WHERE id = ?", (agent["id"],)).fetchone() is None
        assert db.execute("SELECT id FROM conversations WHERE id = ?", (conversation["id"],)).fetchone() is None
