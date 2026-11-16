# -*- coding: utf-8 -*-
"""讨论群任务卡与意见卡的核心库（规格 4.7.1、4.8、6.6）。

``send_note_card`` 依赖另一张单子实现的 ``discuss_store.post_user_note_in_txn``，
本文件不测它；其余建卡、读卡、消费与视图形状都直接读临时库。
"""

import asyncio
import uuid

import pytest
from fastapi import HTTPException

from discuss import cards
from discuss import store as discuss_store


USER = "card_owner"
OTHER = "card_other"

TASK_CARD_DDL = """
CREATE TABLE IF NOT EXISTS discuss_task_cards (
    id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    request TEXT NOT NULL,
    materials TEXT NOT NULL DEFAULT '',
    max_rounds INTEGER,
    budget_strawberries INTEGER,
    group_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

NOTE_CARD_DDL = """
CREATE TABLE IF NOT EXISTS discuss_note_cards (
    id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    group_id TEXT,
    group_title TEXT NOT NULL,
    text TEXT NOT NULL,
    message_id INTEGER DEFAULT NULL,
    sent_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def card_db(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "discuss-cards.db"))
    run(database.init_db())

    async def create_tables(db):
        await db.execute(TASK_CARD_DDL)
        await db.execute(NOTE_CARD_DDL)

    run(discuss_store.run_write(create_tables))
    return database.DB_PATH


def seed_group(group_id="group-1", *, title="", request="帮我调研东南亚短剧市场",
               status="running", stop_reason=None, username=USER):
    async def operation(db):
        await discuss_store.create_group_on_connection(
            db, username, group_id=group_id, request=request, materials="",
            budget_strawberries=500, max_rounds=3,
            config={"avatar": False}, created_day="2026-01-01",
        )
        await discuss_store.update_group_on_connection(
            db, username, group_id, title=title, status=status,
            stop_reason=stop_reason,
        )

    run(discuss_store.run_write(operation))
    return group_id


def add_message(group_id, *, content="插话", username=USER, sender="user",
                kind="user", consumed_by=None):
    async def operation(db):
        cursor = await db.execute(
            """INSERT INTO discuss_messages
               (group_id, username, round, sender, kind, content, payload_json,
                step_key, consumed_by, created_at)
               VALUES (?,?,1,?,?,?,'{}',NULL,?,?)""",
            (group_id, username, sender, kind, content, consumed_by,
             "2026-01-01T00:00:00Z"),
        )
        return cursor.lastrowid

    return run(discuss_store.run_write(operation))


# ── 入参校验 ───────────────────────────────────────────────────


def test_validate_task_args_minimal_defaults():
    clean, error = run(cards.validate_task_args({
        "request": "  帮我调研东南亚短剧市场  ",
    }))
    assert error is None
    assert clean == {
        "request": "帮我调研东南亚短剧市场",
        "materials": "",
        "max_rounds": None,
        "budget_strawberries": None,
    }


def test_validate_task_args_accepts_full_valid_input():
    clean, error = run(cards.validate_task_args({
        "request": "x" * 10,
        "materials": "  补充材料  ",
        "max_rounds": 6,
        "budget_strawberries": 100,
    }))
    assert error is None
    assert clean == {
        "request": "x" * 10,
        "materials": "补充材料",
        "max_rounds": 6,
        "budget_strawberries": 100,
    }


def test_validate_task_args_request_minimum_is_ten_characters():
    # 9 个字必须被拒绝，规则不能宽到 9；10 个字仍是合法下限。
    clean, error = run(cards.validate_task_args({"request": "x" * 9}))
    assert clean is None
    assert error is not None
    assert "诉求需要 10–2000 字" in error
    assert "9" in error

    clean, error = run(cards.validate_task_args({"request": "x" * 10}))
    assert error is None
    assert clean is not None
    assert clean["request"] == "x" * 10


def test_validate_task_args_bounds_and_actual_lengths():
    clean, error = run(cards.validate_task_args({
        "request": "x" * 2000,
        "materials": "m" * 4000,
        "max_rounds": 1,
        "budget_strawberries": 20000,
    }))
    assert error is None

    clean, error = run(cards.validate_task_args({"request": "x" * 2001}))
    assert clean is None
    assert "诉求需要 10–2000 字" in error
    assert "2001" in error

    clean, error = run(cards.validate_task_args({
        "request": "x" * 10,
        "materials": "m" * 4001,
    }))
    assert clean is None
    assert "补充材料最多 4000 字" in error
    assert "4001" in error


def test_validate_task_args_reports_every_error_once_with_semicolon():
    clean, error = run(cards.validate_task_args({
        "request": "短",
        "materials": "m" * 4001,
        "max_rounds": True,
        "budget_strawberries": 99,
    }))
    assert clean is None
    parts = error.split("；")
    assert len(parts) == 4
    assert "诉求需要 10–2000 字" in parts[0]
    assert "补充材料最多 4000 字" in parts[1]
    assert "轮数需要在 1–6 之间" in parts[2]
    assert "预算需要在 100–20000 颗之间" in parts[3]


@pytest.mark.parametrize("value", [True, False, "3", 0, 7, 3.0])
def test_validate_task_args_rejects_non_int_or_out_of_range_rounds(value):
    clean, error = run(cards.validate_task_args({
        "request": "x" * 10, "max_rounds": value}))
    assert clean is None
    assert error == "轮数需要在 1–6 之间"


@pytest.mark.parametrize("value", [True, False, "500", 99, 20001, 500.0])
def test_validate_task_args_rejects_non_int_or_out_of_range_budget(value):
    clean, error = run(cards.validate_task_args({
        "request": "x" * 10, "budget_strawberries": value}))
    assert clean is None
    assert error == "预算需要在 100–20000 颗之间"


def test_validate_note_text_strips_and_bounds():
    assert cards.validate_note_text("  你好  ") == ("你好", None)
    assert cards.validate_note_text("x" * 500) == ("x" * 500, None)
    assert cards.validate_note_text("") == (None, "插话需要 1–500 字")
    assert cards.validate_note_text("   ") == (None, "插话需要 1–500 字")
    assert cards.validate_note_text("x" * 501) == (None, "插话需要 1–500 字")
    assert cards.validate_note_text(None) == (None, "插话需要 1–500 字")


# ── 建卡、计数、读取、消费 ─────────────────────────────────────


def test_create_count_and_get_task_cards(card_db):
    first = run(cards.create_task_card(
        USER, "conversation-1", "帮我调研东南亚短剧市场",
        materials="补充", max_rounds=4, budget_strawberries=800))
    second = run(cards.create_task_card(
        USER, "conversation-1", "帮我调研另一个市场"))
    other = run(cards.create_task_card(
        OTHER, "conversation-2", "别人的调研任务"))

    parsed = uuid.UUID(first["id"])
    assert str(parsed) == first["id"]
    assert first["request"] == "帮我调研东南亚短剧市场"
    assert first["materials"] == "补充"
    assert first["max_rounds"] == 4
    assert first["budget_strawberries"] == 800
    assert first["group_id"] is None

    assert run(cards.count_open_task_cards(USER)) == 2
    assert run(cards.count_open_task_cards(OTHER)) == 1

    assert run(cards.get_task_card(USER, first["id"]))["id"] == first["id"]
    assert run(cards.get_task_card(USER, other["id"])) is None
    assert run(cards.get_task_card(USER, "missing")) is None

    async def consume(db):
        return await cards.consume_task_card(
            db, USER, first["id"], "group-1")

    assert run(discuss_store.run_write(consume)) is True
    assert run(cards.count_open_task_cards(USER)) == 1
    assert run(cards.get_task_card(USER, first["id"]))["group_id"] == "group-1"

    # 已消费的卡不能再次消费；别人的卡也不能消费。
    assert run(discuss_store.run_write(consume)) is False

    async def consume_other(db):
        return await cards.consume_task_card(
            db, USER, other["id"], "group-x")

    assert run(discuss_store.run_write(consume_other)) is False
    assert second["id"] != first["id"]


def test_task_card_view_shape_and_group(card_db):
    seed_group("task-group", title="", request="东南亚短剧市场调研报告第二版",
               status="done", stop_reason="accepted_by_user")
    card = run(cards.create_task_card(
        USER, "conversation-1", "帮我调研东南亚短剧市场",
        materials="补充", max_rounds=2, budget_strawberries=300))

    view = run(cards.task_card_view(USER, card["id"]))
    assert set(view) == {
        "id", "request", "materials", "max_rounds",
        "budget_strawberries", "group_id", "group", "created_at",
    }
    assert view["id"] == card["id"]
    assert view["group_id"] is None
    assert view["group"] is None
    assert view["materials"] == "补充"
    assert view["max_rounds"] == 2
    assert view["budget_strawberries"] == 300

    async def consume(db):
        return await cards.consume_task_card(
            db, USER, card["id"], "task-group")

    assert run(discuss_store.run_write(consume)) is True
    view = run(cards.task_card_view(USER, card["id"]))
    assert view["group_id"] == "task-group"
    assert view["group"] == {
        "id": "task-group",
        "title": "（还没有标题）东南亚短剧市场调研报告第",
        "status": "done",
        "stop_reason": "accepted_by_user",
    }


def test_task_card_view_group_is_null_after_group_deleted(card_db):
    card = run(cards.create_task_card(
        USER, "conversation-1", "帮我调研东南亚短剧市场"))
    seed_group("gone-group", title="会消失的群")

    async def consume(db):
        return await cards.consume_task_card(
            db, USER, card["id"], "gone-group")

    run(discuss_store.run_write(consume))
    run(discuss_store.delete_group(USER, "gone-group"))
    view = run(cards.task_card_view(USER, card["id"]))
    assert view["group_id"] is None
    assert view["group"] is None


def test_task_card_view_missing_raises_404(card_db):
    with pytest.raises(HTTPException) as caught:
        run(cards.task_card_view(USER, "missing"))
    assert caught.value.status_code == 404
    assert caught.value.detail == "任务卡不存在"


# ── 意见卡视图 ─────────────────────────────────────────────────


def test_create_note_card_and_view_shape(card_db):
    seed_group("note-group", title="东南亚短剧", status="running")
    card = run(cards.create_note_card(
        USER, "conversation-1", "note-group", "东南亚短剧", "告诉他们别查越南了"))
    assert str(uuid.UUID(card["id"])) == card["id"]
    assert card["group_id"] == "note-group"
    assert card["group_title"] == "东南亚短剧"
    assert card["text"] == "告诉他们别查越南了"
    assert card["message_id"] is None

    view = run(cards.note_card_view(USER, card["id"]))
    assert set(view) == {
        "id", "group_id", "group_title", "text", "sent_at",
        "message", "group", "created_at",
    }
    assert view["id"] == card["id"]
    assert view["group_title"] == "东南亚短剧"
    assert view["sent_at"] is None
    assert view["message"] is None
    assert view["group"] == {
        "id": "note-group",
        "title": "东南亚短剧",
        "status": "running",
        "stop_reason": None,
        "pending_notes": 0,
    }


def test_note_card_view_pending_notes_and_message_state(card_db):
    seed_group("note-group", title="东南亚短剧", status="awaiting_user")
    card = run(cards.create_note_card(
        USER, "conversation-1", "note-group", "东南亚短剧", "这条意见"))
    unread_one = add_message("note-group", content="未读一")
    unread_two = add_message("note-group", content="未读二")
    add_message("note-group", content="读过的", consumed_by="r01/01")
    add_message("other-group", content="别的群", consumed_by=None)

    view = run(cards.note_card_view(USER, card["id"]))
    assert view["group"]["pending_notes"] == 2

    async def mark_sent(db):
        await db.execute(
            "UPDATE discuss_note_cards SET message_id=?, sent_at=? "
            "WHERE id=? AND owner_username=?",
            (unread_one, "2026-01-02T00:00:00Z", card["id"], USER),
        )

    run(discuss_store.run_write(mark_sent))
    view = run(cards.note_card_view(USER, card["id"]))
    assert view["message"] == {"id": unread_one, "consumed": False}
    assert view["sent_at"] == "2026-01-02T00:00:00Z"

    async def mark_read(db):
        await db.execute(
            "UPDATE discuss_messages SET consumed_by='r01/02' WHERE id=?",
            (unread_one,),
        )

    run(discuss_store.run_write(mark_read))
    view = run(cards.note_card_view(USER, card["id"]))
    assert view["message"] == {"id": unread_one, "consumed": True}

    async def delete_message(db):
        await db.execute("DELETE FROM discuss_messages WHERE id=?", (unread_one,))

    run(discuss_store.run_write(delete_message))
    view = run(cards.note_card_view(USER, card["id"]))
    assert view["message"] is None
    assert view["group"]["pending_notes"] == 1


def test_note_card_view_group_null_keeps_card_title(card_db):
    seed_group("note-group", title="旧群名", status="running")
    card = run(cards.create_note_card(
        USER, "conversation-1", "note-group", "旧群名", "这条意见"))
    run(discuss_store.delete_group(USER, "note-group"))
    view = run(cards.note_card_view(USER, card["id"]))
    assert view["group"] is None
    assert view["group_id"] is None
    assert view["group_title"] == "旧群名"


def test_note_card_view_missing_raises_404(card_db):
    with pytest.raises(HTTPException) as caught:
        run(cards.note_card_view(USER, "missing"))
    assert caught.value.status_code == 404
    assert caught.value.detail == "意见卡不存在"
