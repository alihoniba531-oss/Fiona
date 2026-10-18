# -*- coding: utf-8 -*-
"""写歌存储、消息列与三条删除路径的回归测试（全离线、临时库）。"""
import asyncio
import sqlite3
from uuid import uuid4

import pytest


def _run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def song_db(tmp_path, monkeypatch):
    """临时库 + 临时音频目录；所有用例都从这里起步。"""
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "song_data"))
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "song.db"))
    _run(database.init_db())
    return tmp_path


async def _new_conversation(username, title=None):
    import agent_store

    await _ensure_user(username)
    return (await agent_store.create_conversation(username, title=title))["id"]


async def _ensure_user(username):
    import database

    await database.get_or_create_user(username)


async def _new_project(owner, conversation_id, title="测试歌曲", brief=None, structure=None):
    import song.store as store

    return await store.create_project(
        owner_username=owner,
        conversation_id=conversation_id,
        title=title,
        brief=brief if brief is not None else {"theme": "夏天", "language": "Chinese", "duration_seconds": 60},
        structure=structure if structure is not None else [
            {"id": "s1", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
            {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
        ],
    )


async def _save_first_lyrics(project_id, owner, conversation_id):
    import song.store as store

    return await store.save_lyrics(
        project_id,
        owner_username=owner,
        conversation_id=conversation_id,
        base_revision=0,
        sections=[
            {"id": "s1", "lines": ["风吹过山岗", "云落在远方"]},
            {"id": "s2", "lines": ["我们一起唱", "唱到天亮"]},
        ],
        check={"ok": True, "errors": [], "warnings": []},
        changed_section_ids=[],
    )


def _insert_version(project_id, owner, *, audio_rel_path=None, created_at="2026-10-18 10:00:00",
                    version_id=None, status="succeeded"):
    """测试专用：直接插入版本行（jobs 自己的事务不归 store 管）。"""
    import database

    version_id = version_id or uuid4().hex
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            """INSERT INTO song_versions
                   (id, project_id, owner_username, lyrics_revision, provider, params_json,
                    status, progress, strawberries, billing_state, idempotency_key,
                    audio_rel_path, duration_s, created_day, created_at)
               VALUES (?, ?, ?, 1, 'volc', ?, ?, 100, 30, 'settled', ?, ?, 62.5, '2026-10-18', ?)""",
            (
                version_id, project_id, owner, '{"Lyrics":"[verse]\\n测试"}', status,
                version_id, audio_rel_path, created_at,
            ),
        )
    return version_id


def _table_count(table, where="1=1", parameters=()):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", parameters).fetchone()[0]


def _queue_paths():
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return [row[0] for row in db.execute("SELECT path FROM song_cleanup_queue ORDER BY path")]


def test_init_db_creates_song_tables_indexes_and_message_column(song_db):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        tables = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"song_projects", "song_lyrics", "song_versions", "song_cleanup_queue"} <= tables
        indexes = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        assert {
            "idx_song_projects_owner_conversation",
            "idx_song_versions_owner_status",
            "idx_song_versions_project",
        } <= indexes
        message_columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert "song_project_id" in message_columns
        project_columns = {
            row[1]: row for row in db.execute("PRAGMA table_info(song_projects)")
        }
        assert project_columns["lyrics_revision"][4] == "0"  # dflt_value
        assert project_columns["revision"][4] == "0"
        lyrics_pk = [
            row[1] for row in sorted(
                (row for row in db.execute("PRAGMA table_info(song_lyrics)") if row[5]),
                key=lambda row: row[5],
            )
        ]
        assert lyrics_pk == ["project_id", "revision"]
        version_uniques = {
            tuple(column[2] for column in db.execute(f"PRAGMA index_info('{index}')"))
            for index in indexes
            if index.startswith("sqlite_autoindex_song_versions")
        }
        assert ("owner_username", "idempotency_key") in version_uniques

    # 幂等：重复初始化不丢数据也不报错。
    _run(database.init_db())
    assert _table_count("song_projects") == 0


def test_init_db_upgrades_legacy_messages_with_song_project_id(song_db, tmp_path, monkeypatch):
    import database

    legacy_path = tmp_path / "legacy_song.db"
    with sqlite3.connect(legacy_path) as db:
        db.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, profile_json TEXT DEFAULT '{}')"
        )
        db.execute(
            """CREATE TABLE messages (id INTEGER PRIMARY KEY, username TEXT, role TEXT,
               content TEXT, image_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
        )
        db.execute("INSERT INTO users (username) VALUES ('legacy_song_user')")
        db.execute("INSERT INTO messages (username, role, content) VALUES ('legacy_song_user', 'user', '旧消息')")
    monkeypatch.setattr(database, "DB_PATH", str(legacy_path))
    _run(database.init_db())
    _run(database.init_db())
    with sqlite3.connect(legacy_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert "song_project_id" in columns
        assert db.execute("SELECT content, song_project_id FROM messages").fetchone() == ("旧消息", None)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"song_projects", "song_lyrics", "song_versions", "song_cleanup_queue"} <= tables


def test_project_crud_revision_and_latest_ordering(song_db):
    import song.store as store

    async def scenario():
        owner = "song_owner"
        conversation = await _new_conversation(owner, "写歌")
        other_conversation = await _new_conversation(owner, "其他")

        first = await _new_project(owner, conversation, title="第一首")
        assert first["owner_username"] == owner
        assert first["conversation_id"] == conversation
        assert first["lyrics_revision"] == 0
        assert first["revision"] == 0
        assert first["brief"]["theme"] == "夏天"
        assert [section["id"] for section in first["structure"]] == ["s1", "s2"]

        fetched = await store.get_project(first["id"], owner_username=owner, conversation_id=conversation)
        assert fetched == first
        assert await store.get_project(first["id"], owner_username=owner) == first
        assert await store.get_project(
            first["id"], owner_username=owner, conversation_id=other_conversation
        ) is None
        assert await store.get_project(first["id"], owner_username="intruder") is None

        updated = await store.update_project(
            first["id"],
            owner_username=owner,
            conversation_id=conversation,
            title="第一首·改",
            brief={"theme": "秋天", "language": "Chinese", "duration_seconds": 90},
            structure=[{"id": "s1", "type": "verse", "lines": 4, "chars": [7, 9], "rhyme": "ABAB"}],
        )
        assert updated["title"] == "第一首·改"
        assert updated["brief"]["theme"] == "秋天"
        assert updated["revision"] == 1
        assert updated["lyrics_revision"] == 0
        assert await store.update_project(
            first["id"],
            owner_username=owner,
            conversation_id=other_conversation,
            title="错误会话",
            brief={},
            structure=[],
        ) is None

        # jobs 的事务连接不一定设置了 aiosqlite.Row，fetch_* 必须兼容。
        import aiosqlite
        import database

        async with aiosqlite.connect(database.DB_PATH) as db:
            direct = await store.fetch_project(db, first["id"], owner, conversation)
            assert direct["id"] == first["id"]
            assert await store.fetch_project(db, first["id"], owner, other_conversation) is None

        second = await _new_project(owner, conversation, title="第二首")

        import aiosqlite
        import database

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE song_projects SET updated_at = '2000-01-01 00:00:00' WHERE id = ?",
                (first["id"],),
            )
            await db.execute(
                "UPDATE song_projects SET updated_at = '2000-01-01 00:00:01' WHERE id = ?",
                (second["id"],),
            )
            await db.commit()
        latest = await store.get_latest_project_for_conversation(owner, conversation)
        assert latest["id"] == second["id"]

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE song_projects SET updated_at = '2000-01-01 00:00:02' WHERE id = ?",
                (first["id"],),
            )
            await db.commit()
        latest = await store.get_latest_project_for_conversation(owner, conversation)
        assert latest["id"] == first["id"]
        assert await store.get_latest_project_for_conversation(owner, other_conversation) is None

    _run(scenario())


def test_save_lyrics_success_conflict_ownership_and_history(song_db):
    import song.store as store

    async def scenario():
        owner = "lyrics_owner"
        conversation = await _new_conversation(owner)
        other_conversation = await _new_conversation(owner)
        project = await _new_project(owner, conversation)

        saved = await _save_first_lyrics(project["id"], owner, conversation)
        assert saved["status"] == "ok"
        assert saved["project"]["lyrics_revision"] == 1
        assert saved["project"]["revision"] == 1
        assert saved["lyrics"]["revision"] == 1
        assert saved["lyrics"]["sections"][0]["lines"] == ["风吹过山岗", "云落在远方"]
        assert saved["lyrics"]["check"] == {"ok": True, "errors": [], "warnings": []}
        assert saved["lyrics"]["changed_section_ids"] == []

        import aiosqlite
        import database

        async with aiosqlite.connect(database.DB_PATH) as db:
            direct_lyrics = await store.fetch_latest_lyrics(db, project["id"])
            assert direct_lyrics["revision"] == 1
            assert direct_lyrics["sections"][0]["id"] == "s1"

        conflict = await store.save_lyrics(
            project["id"],
            owner_username=owner,
            conversation_id=conversation,
            base_revision=0,
            sections=[],
            check={},
            changed_section_ids=[],
        )
        assert conflict == {"status": "conflict"}
        assert (await store.get_lyrics(project["id"]))["revision"] == 1

        wrong_owner = await store.save_lyrics(
            project["id"],
            owner_username="intruder",
            conversation_id=conversation,
            base_revision=1,
            sections=[],
            check={},
            changed_section_ids=[],
        )
        assert wrong_owner == {"status": "not_found"}

        wrong_conversation = await store.save_lyrics(
            project["id"],
            owner_username=owner,
            conversation_id=other_conversation,
            base_revision=1,
            sections=[],
            check={},
            changed_section_ids=[],
        )
        assert wrong_conversation == {"status": "not_found"}

        missing = await store.save_lyrics(
            "0" * 32,
            owner_username=owner,
            conversation_id=conversation,
            base_revision=0,
            sections=[],
            check={},
            changed_section_ids=[],
        )
        assert missing == {"status": "not_found"}

        second = await store.save_lyrics(
            project["id"],
            owner_username=owner,
            conversation_id=conversation,
            base_revision=1,
            sections=[
                {"id": "s1", "lines": ["风吹过山岗", "云落在远方"]},
                {"id": "s2", "lines": ["我们一起唱", "唱到天亮"]},
            ],
            check={"ok": True, "errors": [], "warnings": [{"code": "line_count"}]},
            changed_section_ids=["s2"],
        )
        assert second["status"] == "ok"
        assert second["project"]["lyrics_revision"] == 2
        assert second["project"]["revision"] == 2
        assert second["lyrics"]["changed_section_ids"] == ["s2"]

        latest = await store.get_lyrics(project["id"])
        assert latest["revision"] == 2
        first_revision = await store.get_lyrics(project["id"], revision=1)
        assert first_revision["revision"] == 1
        assert first_revision["check"]["warnings"] == []
        assert await store.get_lyrics(project["id"], revision=99) is None

    _run(scenario())


def test_bad_json_falls_back_to_empty_containers(song_db):
    import aiosqlite
    import database
    import song.store as store

    async def scenario():
        owner = "json_owner"
        conversation = await _new_conversation(owner)
        project = await _new_project(owner, conversation)
        await _save_first_lyrics(project["id"], owner, conversation)
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE song_projects SET brief_json = 'not-json', structure_json = '{\"x\":1}' WHERE id = ?",
                (project["id"],),
            )
            await db.execute(
                """UPDATE song_lyrics SET sections_json = '[broken', check_json = 'null',
                       changed_section_ids = '"not-a-list"' WHERE project_id = ?""",
                (project["id"],),
            )
            await db.commit()
        fetched = await store.get_project(project["id"], owner_username=owner)
        assert fetched["brief"] == {}
        assert fetched["structure"] == []
        lyrics = await store.get_lyrics(project["id"])
        assert lyrics["sections"] == []
        assert lyrics["check"] == {}
        assert lyrics["changed_section_ids"] == []

    _run(scenario())


def test_list_versions_newest_first_and_limit(song_db):
    import song.store as store

    async def scenario():
        owner = "version_owner"
        conversation = await _new_conversation(owner)
        project = await _new_project(owner, conversation)
        inserted = []
        for index in range(12):
            version_id = _insert_version(
                project["id"],
                owner,
                version_id=f"{index:032x}",
                created_at=f"2026-10-18 10:{index:02d}:00",
            )
            inserted.append(version_id)

        latest = await store.list_versions(project["id"])
        assert len(latest) == 10
        assert [version["id"] for version in latest] == list(reversed(inserted))[:10]
        assert latest[0]["params"] == {"Lyrics": "[verse]\n测试"}
        assert latest[0]["status"] == "succeeded"
        assert latest[0]["duration_s"] == 62.5

        limited = await store.list_versions(project["id"], limit=3)
        assert [version["id"] for version in limited] == list(reversed(inserted))[:3]
        assert len(await store.list_versions(project["id"], limit=0)) == 10
        assert await store.list_versions("0" * 32) == []

    _run(scenario())


def test_save_message_binds_only_owned_project_in_same_conversation(song_db):
    import database

    async def scenario():
        owner = "message_owner"
        conversation = await _new_conversation(owner)
        other_conversation = await _new_conversation(owner)
        intruder_conversation = await _new_conversation("message_intruder")
        project = await _new_project(owner, conversation)
        foreign_project = await _new_project("message_intruder", intruder_conversation)

        assert await database.save_message(
            owner, "assistant", "合法项目", conversation_id=conversation,
            song_project_id=project["id"],
        )
        assert await database.save_message(
            owner, "assistant", "他人项目", conversation_id=conversation,
            song_project_id=foreign_project["id"],
        )
        assert await database.save_message(
            owner, "assistant", "错误会话", conversation_id=other_conversation,
            song_project_id=project["id"],
        )
        assert await database.save_message(
            owner, "assistant", "不存在的项目", conversation_id=conversation,
            song_project_id="0" * 32,
        )

        import agent_store

        page = await agent_store.get_conversation_messages(owner, conversation)
        assert [(message["content"], message["song_project_id"]) for message in page["messages"]] == [
            ("合法项目", project["id"]),
            ("他人项目", None),
            ("不存在的项目", None),
        ]
        other_page = await agent_store.get_conversation_messages(owner, other_conversation)
        assert [(message["content"], message["song_project_id"]) for message in other_page["messages"]] == [
            ("错误会话", None),
        ]

        # 写歌表查询异常时也必须保存消息，只是该列写 NULL。
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("ALTER TABLE song_projects RENAME TO song_projects_hidden")
        try:
            assert await database.save_message(
                owner, "assistant", "表缺失也要落库", conversation_id=conversation,
                song_project_id=project["id"],
            )
        finally:
            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("ALTER TABLE song_projects_hidden RENAME TO song_projects")
        page = await agent_store.get_conversation_messages(owner, conversation)
        assert page["messages"][-1]["content"] == "表缺失也要落库"
        assert page["messages"][-1]["song_project_id"] is None

    _run(scenario())


def test_delete_conversation_removes_song_rows_and_queues_audio(song_db):
    import agent_store
    import database
    import song.store as store

    async def scenario():
        owner = "conversation_owner"
        conversation = await _new_conversation(owner)
        untouched_conversation = await _new_conversation(owner)
        project = await _new_project(owner, conversation)
        await _save_first_lyrics(project["id"], owner, conversation)
        _insert_version(project["id"], owner, audio_rel_path="conversation_audio.mp3")

        untouched = await _new_project(owner, untouched_conversation, title="另一首")
        _insert_version(untouched["id"], owner, audio_rel_path="untouched.mp3")

        upload_path = "/uploads/generated_" + "a" * 32 + ".png"
        assert await database.save_message(
            owner, "user", "带图消息", upload_path, conversation,
        )
        assert await database.save_message(
            owner, "assistant", "写歌消息", conversation_id=conversation,
            song_project_id=project["id"],
        )

        result = await agent_store.delete_conversation(owner, conversation)
        assert result["status"] == "deleted"
        assert result["song_audio_paths"] == ["conversation_audio.mp3"]
        assert result["upload_paths"] == [upload_path]

        assert _table_count("song_projects", "id = ?", (project["id"],)) == 0
        assert _table_count("song_lyrics", "project_id = ?", (project["id"],)) == 0
        assert _table_count("song_versions", "project_id = ?", (project["id"],)) == 0
        assert _table_count("song_projects", "id = ?", (untouched["id"],)) == 1
        assert _table_count("song_versions", "project_id = ?", (untouched["id"],)) == 1
        assert _queue_paths() == ["conversation_audio.mp3"]
        assert await store.get_project(project["id"], owner_username=owner) is None

    _run(scenario())


def test_clear_history_removes_all_song_rows_and_keeps_upload_return(song_db):
    import database

    async def scenario():
        owner = "history_owner"
        conversation = await _new_conversation(owner)
        other_conversation = await _new_conversation(owner)
        project = await _new_project(owner, conversation)
        await _save_first_lyrics(project["id"], owner, conversation)
        _insert_version(project["id"], owner, audio_rel_path="history_audio.mp3")

        second_project = await _new_project(owner, other_conversation, title="第二首")
        _insert_version(second_project["id"], owner, audio_rel_path="history_audio_2.mp3")

        await _ensure_user("history_other")
        other_user_conversation = await _new_conversation("history_other")
        foreign_project = await _new_project("history_other", other_user_conversation)
        _insert_version(foreign_project["id"], "history_other", audio_rel_path="foreign.mp3")

        upload_path = "/uploads/generated_" + "b" * 32 + ".png"
        assert await database.save_message(owner, "user", "带图消息", upload_path, conversation)

        returned = await database.clear_message_history(owner)
        assert returned == [upload_path]
        assert _table_count("messages", "username = ?", (owner,)) == 0
        assert _table_count("song_projects", "owner_username = ?", (owner,)) == 0
        assert _table_count("song_lyrics", "project_id IN (?, ?)", (project["id"], second_project["id"])) == 0
        assert _table_count("song_versions", "owner_username = ?", (owner,)) == 0
        assert _table_count("song_projects", "owner_username = ?", ("history_other",)) == 1
        assert _table_count("song_versions", "owner_username = ?", ("history_other",)) == 1
        assert _queue_paths() == sorted(["history_audio.mp3", "history_audio_2.mp3"])
        assert "foreign.mp3" not in _queue_paths()

    _run(scenario())


def test_delete_account_removes_song_rows_and_queues_audio(song_db):
    import agent_store
    import database

    async def scenario():
        owner = "account_owner"
        conversation = await _new_conversation(owner)
        project = await _new_project(owner, conversation)
        await _save_first_lyrics(project["id"], owner, conversation)
        _insert_version(project["id"], owner, audio_rel_path="account_audio.mp3")
        upload_path = "/uploads/generated_" + "c" * 32 + ".png"
        assert await database.save_message(owner, "user", "带图消息", upload_path, conversation)

        result = await database.delete_account_data(owner)
        assert result["deleted"] is True
        assert result["song_audio_paths"] == ["account_audio.mp3"]
        assert upload_path in result["upload_paths"]
        assert _table_count("users", "username = ?", (owner,)) == 0
        assert _table_count("song_projects", "owner_username = ?", (owner,)) == 0
        assert _table_count("song_lyrics", "project_id = ?", (project["id"],)) == 0
        assert _table_count("song_versions", "owner_username = ?", (owner,)) == 0
        assert _queue_paths() == ["account_audio.mp3"]

        missing = await database.delete_account_data("never_existed")
        assert missing == {"deleted": False, "upload_paths": [], "song_audio_paths": []}

    _run(scenario())
