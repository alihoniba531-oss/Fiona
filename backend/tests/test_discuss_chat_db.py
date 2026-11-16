# -*- coding: utf-8 -*-
"""聊天 ↔ 讨论群：两张卡片表、messages 外键与清理的数据库契约。

规格：docs/tasks/2026-11-15-agent-group-chat/02-spec.md 的 4.7、4.9。
全部用例只用临时 SQLite，不访问网络，也不依赖 git 历史。
"""
import asyncio
import re
import sqlite3
from types import SimpleNamespace as NS

import pytest


USER = "discuss-card-user"
OTHER = "discuss-card-other"
NOW = "2026-11-15T00:00:00+00:00"

TASK_COLUMNS = [
    "id", "owner_username", "conversation_id", "request", "materials",
    "max_rounds", "budget_strawberries", "group_id", "created_at", "updated_at",
]
NOTE_COLUMNS = [
    "id", "owner_username", "conversation_id", "group_id", "group_title",
    "text", "message_id", "sent_at", "created_at", "updated_at",
]

# PRAGMA table_info 的 (name, type, notnull, dflt_value, pk)，不含 cid。
# 规格 4.7.1：这两张表的列定义必须逐字段钉死；D21/D22 分别改坏
# materials 的 NOT NULL DEFAULT '' 与 group_title 的 NOT NULL。
TASK_COLUMNS_INFO = [
    ("id", "TEXT", 0, None, 1),
    ("owner_username", "TEXT", 1, None, 0),
    ("conversation_id", "TEXT", 1, None, 0),
    ("request", "TEXT", 1, None, 0),
    ("materials", "TEXT", 1, "''", 0),
    ("max_rounds", "INTEGER", 0, None, 0),
    ("budget_strawberries", "INTEGER", 0, None, 0),
    ("group_id", "TEXT", 0, "NULL", 0),
    ("created_at", "TEXT", 1, None, 0),
    ("updated_at", "TEXT", 1, None, 0),
]
NOTE_COLUMNS_INFO = [
    ("id", "TEXT", 0, None, 1),
    ("owner_username", "TEXT", 1, None, 0),
    ("conversation_id", "TEXT", 1, None, 0),
    ("group_id", "TEXT", 0, None, 0),
    ("group_title", "TEXT", 1, None, 0),
    ("text", "TEXT", 1, None, 0),
    ("message_id", "INTEGER", 0, "NULL", 0),
    ("sent_at", "TEXT", 0, "NULL", 0),
    ("created_at", "TEXT", 1, None, 0),
    ("updated_at", "TEXT", 1, None, 0),
]


@pytest.fixture
def card_db(tmp_path, monkeypatch):
    """临时库 + 本人两个会话 + 另一个账号的会话。"""
    import agent_store
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "discuss-chat-db.db"))
    asyncio.run(database.init_db())

    async def setup():
        await database.get_or_create_user(USER)
        await database.get_or_create_user(OTHER)
        owner = (await agent_store.create_conversation(USER))["id"]
        owner_second = (await agent_store.create_conversation(USER))["id"]
        other = (await agent_store.create_conversation(OTHER))["id"]
        return owner, owner_second, other

    owner, owner_second, other = asyncio.run(setup())
    return NS(path=database.DB_PATH, owner=owner, owner_second=owner_second,
              other=other, db=database, agent_store=agent_store)


def _insert_task(db_path, card_id, conversation_id, username=USER):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """INSERT INTO discuss_task_cards
               (id, owner_username, conversation_id, request, materials, max_rounds,
                budget_strawberries, group_id, created_at, updated_at)
               VALUES (?, ?, ?, '调研东南亚短剧', '', 3, 2000, NULL, ?, ?)""",
            (card_id, username, conversation_id, NOW, NOW),
        )


def _insert_note(db_path, card_id, conversation_id, username=USER):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """INSERT INTO discuss_note_cards
               (id, owner_username, conversation_id, group_id, group_title, text,
                message_id, sent_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, '东南亚短剧', '别查越南了', NULL, NULL, ?, ?)""",
            (card_id, username, conversation_id, "a" * 32, NOW, NOW),
        )


def _ids(db_path, table):
    with sqlite3.connect(db_path) as db:
        return {row[0] for row in db.execute(f"SELECT id FROM {table}")}


def _column_names(db_path, table):
    with sqlite3.connect(db_path) as db:
        return [row[1] for row in db.execute(f"PRAGMA table_info({table})")]


def _columns_info(db_path, table):
    """返回 PRAGMA table_info 的 (name, type, notnull, dflt_value, pk)。"""
    with sqlite3.connect(db_path) as db:
        return [row[1:] for row in db.execute(f"PRAGMA table_info({table})")]


def _init_fresh(monkeypatch, tmp_path, name="discuss-chat-db.db"):
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / name))
    asyncio.run(database.init_db())
    return database


# ────────────────────────── 表、索引与开关无关 ──────────────────────────


def test_init_db_creates_card_tables_columns_and_owner_indexes(monkeypatch, tmp_path):
    """规格 4.7.1：两张表按 owner_username 建索引，列与规格完全一致。"""
    monkeypatch.delenv("FIONA_DISCUSS_CHAT", raising=False)
    monkeypatch.delenv("FIONA_DISCUSS_CHAT_CARDS", raising=False)
    database = _init_fresh(monkeypatch, tmp_path)

    assert re.search(r"CREATE TABLE IF NOT EXISTS discuss_task_cards", database.DISCUSS_TASK_CARDS_DDL)
    assert re.search(r"CREATE TABLE IF NOT EXISTS discuss_note_cards", database.DISCUSS_NOTE_CARDS_DDL)
    assert "discuss_task_cards(owner_username)" in database.DISCUSS_TASK_CARDS_INDEX
    assert "discuss_note_cards(owner_username)" in database.DISCUSS_NOTE_CARDS_INDEX

    with sqlite3.connect(database.DB_PATH) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"discuss_task_cards", "discuss_note_cards"} <= tables
        assert {"idx_discuss_task_cards_owner", "idx_discuss_note_cards_owner"} <= indexes
        assert [row[2] for row in db.execute("PRAGMA index_info('idx_discuss_task_cards_owner')")] == ["owner_username"]
        assert [row[2] for row in db.execute("PRAGMA index_info('idx_discuss_note_cards_owner')")] == ["owner_username"]

    assert _column_names(database.DB_PATH, "discuss_task_cards") == TASK_COLUMNS
    assert _column_names(database.DB_PATH, "discuss_note_cards") == NOTE_COLUMNS


def test_task_card_table_column_definitions(monkeypatch, tmp_path):
    """门禁 D21：discuss_task_cards 整表逐列核对，materials 必须 TEXT NOT NULL DEFAULT ''。"""
    database = _init_fresh(monkeypatch, tmp_path, "task-columns.db")
    with sqlite3.connect(database.DB_PATH) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # 先断言目标表与目标列确实存在，再断言定义内容。
    assert "discuss_task_cards" in tables
    info = _columns_info(database.DB_PATH, "discuss_task_cards")
    assert info, "discuss_task_cards 的 PRAGMA table_info 为空"
    by_name = {row[0]: row for row in info}
    assert "materials" in by_name
    assert by_name["materials"] == ("materials", "TEXT", 1, "''", 0)
    assert info == TASK_COLUMNS_INFO


def test_note_card_table_column_definitions(monkeypatch, tmp_path):
    """门禁 D22：discuss_note_cards 整表逐列核对，group_title 必须 TEXT NOT NULL。"""
    database = _init_fresh(monkeypatch, tmp_path, "note-columns.db")
    with sqlite3.connect(database.DB_PATH) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # 先断言目标表与目标列确实存在，再断言定义内容。
    assert "discuss_note_cards" in tables
    info = _columns_info(database.DB_PATH, "discuss_note_cards")
    assert info, "discuss_note_cards 的 PRAGMA table_info 为空"
    by_name = {row[0]: row for row in info}
    assert "group_title" in by_name
    assert by_name["group_title"] == ("group_title", "TEXT", 1, None, 0)
    assert info == NOTE_COLUMNS_INFO


@pytest.mark.parametrize("switch", [None, "0", "1"])
def test_messages_card_columns_do_not_depend_on_switches(monkeypatch, tmp_path, switch):
    """规格 4.7.2：messages 两列由 init_db 无条件补上，与两个开关无关。"""
    import database

    monkeypatch.delenv("FIONA_DISCUSS_CHAT", raising=False)
    monkeypatch.delenv("FIONA_DISCUSS_CHAT_CARDS", raising=False)
    if switch is not None:
        monkeypatch.setenv("FIONA_DISCUSS_CHAT", switch)
        monkeypatch.setenv("FIONA_DISCUSS_CHAT_CARDS", switch)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / f"switch-{switch}.db"))
    asyncio.run(database.init_db())

    with sqlite3.connect(database.DB_PATH) as db:
        columns = {row[1]: row for row in db.execute("PRAGMA table_info(messages)")}
    for name in ("discuss_task_id", "discuss_note_id"):
        assert name in columns
        assert columns[name][2] == "TEXT"
        assert columns[name][3] == 0  # 可空


def test_init_db_upgrades_old_messages_with_discuss_columns(monkeypatch, tmp_path):
    """规格 4.7.2：旧库只有基础 messages 表，启动后自动有这两列。"""
    import database

    path = tmp_path / "legacy_discuss.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, profile_json TEXT DEFAULT '{}')"
        )
        db.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, "
            "role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        db.execute("INSERT INTO users (username) VALUES (?)", (USER,))
        db.execute("INSERT INTO messages (username, role, content) VALUES (?, 'user', '旧消息')", (USER,))
    monkeypatch.delenv("FIONA_DISCUSS_CHAT", raising=False)
    monkeypatch.delenv("FIONA_DISCUSS_CHAT_CARDS", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(path))
    asyncio.run(database.init_db())
    asyncio.run(database.init_db())

    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        row = db.execute("SELECT content, discuss_task_id, discuss_note_id FROM messages").fetchone()
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"discuss_task_id", "discuss_note_id"} <= columns
    assert row == ("旧消息", None, None)
    assert {"discuss_task_cards", "discuss_note_cards"} <= tables


def test_init_db_twice_keeps_five_migrations(monkeypatch, tmp_path):
    """规格 4.7：新表与补列不新增迁移版本号。"""
    database = _init_fresh(monkeypatch, tmp_path)
    asyncio.run(database.init_db())
    with sqlite3.connect(database.DB_PATH) as db:
        versions = db.execute("SELECT version FROM schema_migrations ORDER BY rowid").fetchall()
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert len(versions) == 5
    assert {"discuss_task_cards", "discuss_note_cards"} <= tables


# ────────────────────────── 消息外键 ──────────────────────────


def test_save_message_keeps_only_own_conversation_card_ids(card_db):
    """规格 4.7.3：他人的、别的会话的卡 id 存 NULL；本人本会话原样保存。"""
    own_task = "11111111-1111-4111-8111-111111111111"
    own_note = "22222222-2222-4222-8222-222222222222"
    second_task = "33333333-3333-4333-8333-333333333333"
    second_note = "44444444-4444-4444-8444-444444444444"
    foreign_task = "55555555-5555-4555-8555-555555555555"
    foreign_note = "66666666-6666-4666-8666-666666666666"
    missing_task = "77777777-7777-4777-8777-777777777777"

    _insert_task(card_db.path, own_task, card_db.owner)
    _insert_note(card_db.path, own_note, card_db.owner)
    _insert_task(card_db.path, second_task, card_db.owner_second)
    _insert_note(card_db.path, second_note, card_db.owner_second)
    _insert_task(card_db.path, foreign_task, card_db.other, username=OTHER)
    _insert_note(card_db.path, foreign_note, card_db.other, username=OTHER)

    db = card_db.db

    async def save():
        assert await db.save_message(
            USER, "assistant", "own", conversation_id=card_db.owner,
            discuss_task_id=own_task, discuss_note_id=own_note,
        )
        assert await db.save_message(
            USER, "assistant", "other-conversation", conversation_id=card_db.owner,
            discuss_task_id=second_task, discuss_note_id=second_note,
        )
        assert await db.save_message(
            USER, "assistant", "foreign", conversation_id=card_db.owner,
            discuss_task_id=foreign_task, discuss_note_id=foreign_note,
        )
        assert await db.save_message(
            USER, "assistant", "missing", conversation_id=card_db.owner,
            discuss_task_id=missing_task, discuss_note_id="88888888-8888-4888-8888-888888888888",
        )

    asyncio.run(save())
    with sqlite3.connect(card_db.path) as conn:
        stored = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT content, discuss_task_id, discuss_note_id FROM messages")
        }
    assert stored["own"] == (own_task, own_note)
    assert stored["other-conversation"] == (None, None)
    assert stored["foreign"] == (None, None)
    assert stored["missing"] == (None, None)


def test_save_message_drops_cards_owned_by_other_in_same_conversation(card_db):
    """门禁 D4/D5：别人的卡即使 conversation_id 恰好是本人会话，也必须存 NULL。

    两张附加校验都必须核对 owner_username；只看 id 与会话 id 会把别人的卡
    挂到本人消息上。同时保留本人本会话的卡原样保存的正向断言。
    """
    own_task = "11111111-aaaa-4bbb-8ccc-111111111111"
    own_note = "22222222-bbbb-4ccc-8ddd-222222222222"
    foreign_owner_task = "33333333-cccc-4ddd-8eee-333333333333"
    foreign_owner_note = "44444444-dddd-4eee-8fff-444444444444"

    _insert_task(card_db.path, own_task, card_db.owner)
    _insert_note(card_db.path, own_note, card_db.owner)
    # 别人的卡，但 conversation_id 恰好等于本人这个会话的 id。
    _insert_task(card_db.path, foreign_owner_task, card_db.owner, username=OTHER)
    _insert_note(card_db.path, foreign_owner_note, card_db.owner, username=OTHER)

    # 先断言目标行确实存在且归属关系如预期，避免插错数据造成假通过。
    with sqlite3.connect(card_db.path) as db:
        task_rows = {
            row[0]: (row[1], row[2])
            for row in db.execute("SELECT id, owner_username, conversation_id FROM discuss_task_cards")
        }
        note_rows = {
            row[0]: (row[1], row[2])
            for row in db.execute("SELECT id, owner_username, conversation_id FROM discuss_note_cards")
        }
    assert task_rows[own_task] == (USER, card_db.owner)
    assert note_rows[own_note] == (USER, card_db.owner)
    assert task_rows[foreign_owner_task] == (OTHER, card_db.owner)
    assert note_rows[foreign_owner_note] == (OTHER, card_db.owner)

    async def save():
        assert await card_db.db.save_message(
            USER, "assistant", "本人卡", conversation_id=card_db.owner,
            discuss_task_id=own_task, discuss_note_id=own_note,
        )
        assert await card_db.db.save_message(
            USER, "assistant", "他人所有同会话卡", conversation_id=card_db.owner,
            discuss_task_id=foreign_owner_task, discuss_note_id=foreign_owner_note,
        )

    asyncio.run(save())
    with sqlite3.connect(card_db.path) as conn:
        stored = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT content, discuss_task_id, discuss_note_id FROM messages")
        }
    assert stored["本人卡"] == (own_task, own_note)
    assert stored["他人所有同会话卡"] == (None, None)


def test_save_message_survives_missing_card_tables(card_db):
    """附加校验出异常也不能让消息落库失败：对应表不在时两个外键存 NULL。"""
    with sqlite3.connect(card_db.path) as db:
        db.execute("DROP TABLE discuss_task_cards")
        db.execute("DROP TABLE discuss_note_cards")

    async def save():
        return await card_db.db.save_message(
            USER, "assistant", "表不在", conversation_id=card_db.owner,
            discuss_task_id="11111111-1111-4111-8111-111111111111",
            discuss_note_id="22222222-2222-4222-8222-222222222222",
        )

    assert asyncio.run(save()) is True
    with sqlite3.connect(card_db.path) as db:
        row = db.execute(
            "SELECT discuss_task_id, discuss_note_id FROM messages WHERE content = '表不在'"
        ).fetchone()
    assert row == (None, None)


def test_get_conversation_messages_returns_discuss_ids(card_db):
    """规格 4.7.5：读消息的列清单带出两个新外键。"""
    task = "11111111-2222-4333-8444-555555555555"
    note = "66666666-7777-4888-8999-000000000000"
    _insert_task(card_db.path, task, card_db.owner)
    _insert_note(card_db.path, note, card_db.owner)

    async def scenario():
        assert await card_db.db.save_message(
            USER, "assistant", "带卡", conversation_id=card_db.owner,
            discuss_task_id=task, discuss_note_id=note,
        )
        assert await card_db.db.save_message(
            USER, "user", "普通", conversation_id=card_db.owner,
        )
        result = await card_db.agent_store.get_conversation_messages(USER, card_db.owner)
        return {message["content"]: message for message in result["messages"]}

    messages = asyncio.run(scenario())
    assert messages["带卡"]["discuss_task_id"] == task
    assert messages["带卡"]["discuss_note_id"] == note
    assert messages["普通"]["discuss_task_id"] is None
    assert messages["普通"]["discuss_note_id"] is None


# ────────────────────────── 清理 ──────────────────────────


@pytest.mark.parametrize("operation", ["account", "history"])
def test_account_and_history_cleanup_remove_only_own_cards(card_db, operation):
    """规格 4.9.1、4.9.2：删号与清空历史按 owner_username 删两张卡。"""
    _insert_task(card_db.path, "11111111-1111-4111-8111-111111111111", card_db.owner)
    _insert_task(card_db.path, "22222222-2222-4222-8222-222222222222", card_db.owner_second)
    _insert_note(card_db.path, "33333333-3333-4333-8333-333333333333", card_db.owner)
    _insert_note(card_db.path, "44444444-4444-4444-8444-444444444444", card_db.owner_second)
    _insert_task(card_db.path, "55555555-5555-4555-8555-555555555555", card_db.other, username=OTHER)
    _insert_note(card_db.path, "66666666-6666-4666-8666-666666666666", card_db.other, username=OTHER)

    async def cleanup():
        if operation == "account":
            await card_db.db.delete_account_data(USER)
        else:
            await card_db.db.save_message(USER, "user", "历史", conversation_id=card_db.owner)
            await card_db.db.clear_message_history(USER)

    asyncio.run(cleanup())
    assert _ids(card_db.path, "discuss_task_cards") == {"55555555-5555-4555-8555-555555555555"}
    assert _ids(card_db.path, "discuss_note_cards") == {"66666666-6666-4666-8666-666666666666"}


def test_delete_conversation_removes_only_that_conversations_cards(card_db):
    """规格 4.9.2：删会话按 owner_username + conversation_id 删两张卡。"""
    _insert_task(card_db.path, "11111111-1111-4111-8111-111111111111", card_db.owner)
    _insert_task(card_db.path, "22222222-2222-4222-8222-222222222222", card_db.owner_second)
    _insert_note(card_db.path, "33333333-3333-4333-8333-333333333333", card_db.owner)
    _insert_note(card_db.path, "44444444-4444-4444-8444-444444444444", card_db.owner_second)
    _insert_task(card_db.path, "55555555-5555-4555-8555-555555555555", card_db.other, username=OTHER)
    _insert_note(card_db.path, "66666666-6666-4666-8666-666666666666", card_db.other, username=OTHER)

    asyncio.run(card_db.agent_store.delete_conversation(USER, card_db.owner))
    assert _ids(card_db.path, "discuss_task_cards") == {
        "22222222-2222-4222-8222-222222222222",
        "55555555-5555-4555-8555-555555555555",
    }
    assert _ids(card_db.path, "discuss_note_cards") == {
        "44444444-4444-4444-8444-444444444444",
        "66666666-6666-4666-8666-666666666666",
    }
