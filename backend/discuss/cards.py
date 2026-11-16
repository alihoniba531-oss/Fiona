"""讨论群任务卡与意见卡的存储与视图。

卡片只存在本地数据库：任务卡不建群，意见卡不直接插话。数据库访问统一走
``discuss_store``；``send_note_card`` 在一个写事务里完成插话与卡片状态更新。
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from novel.run_store import utc_now

from . import store as discuss_store


TASK_OPEN_LIMIT = 50

TASK_NOT_FOUND = "任务卡不存在"
NOTE_NOT_FOUND = "意见卡不存在"
NOTE_TOO_MANY = "还有 5 条插话没被读到，等主持人回应后再说"
GROUP_DELETED = "这个讨论群已经删除"
GROUP_CLOSED = "讨论群已经结束"


async def validate_task_args(args: dict) -> tuple[dict | None, str | None]:
    """校验任务卡入参；格式错误一次报全，用「；」连接。"""
    args = args if isinstance(args, dict) else {}
    errors: list[str] = []

    raw_request = args.get("request")
    request = raw_request.strip() if isinstance(raw_request, str) else ""
    if not 10 <= len(request) <= 2000:
        errors.append(f"诉求需要 10–2000 字，现在是 {len(request)} 字")

    raw_materials = args.get("materials")
    if raw_materials is None:
        materials = ""
    elif isinstance(raw_materials, str):
        materials = raw_materials.strip()
        if len(materials) > 4000:
            errors.append(f"补充材料最多 4000 字，现在是 {len(materials)} 字")
    else:
        materials = ""
        errors.append("补充材料需要是文字")

    max_rounds = args.get("max_rounds")
    if max_rounds is not None and (
        type(max_rounds) is not int or not 1 <= max_rounds <= 6
    ):
        errors.append("轮数需要在 1–6 之间")

    budget = args.get("budget_strawberries")
    if budget is not None and (
        type(budget) is not int or not 100 <= budget <= 20000
    ):
        errors.append("预算需要在 100–20000 颗之间")

    if errors:
        return None, "；".join(errors)
    return {
        "request": request,
        "materials": materials,
        "max_rounds": max_rounds,
        "budget_strawberries": budget,
    }, None


def validate_note_text(text: object) -> tuple[str | None, str | None]:
    """意见卡正文去空白后 1–500 字。"""
    clean = text.strip() if isinstance(text, str) else ""
    if not 1 <= len(clean) <= 500:
        return None, "插话需要 1–500 字"
    return clean, None


async def _fetch_task(db, username: str, card_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM discuss_task_cards WHERE id=? AND owner_username=?",
        (card_id, username),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def _fetch_note(db, username: str, card_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM discuss_note_cards WHERE id=? AND owner_username=?",
        (card_id, username),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def create_task_card(
    username: str,
    conversation_id: str,
    request: str,
    materials: str = "",
    max_rounds: int | None = None,
    budget_strawberries: int | None = None,
) -> dict:
    card_id = str(uuid4())
    now = utc_now()

    async def operation(db):
        await db.execute(
            """INSERT INTO discuss_task_cards
               (id, owner_username, conversation_id, request, materials,
                max_rounds, budget_strawberries, group_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,NULL,?,?)""",
            (card_id, username, conversation_id, request, materials or "",
             max_rounds, budget_strawberries, now, now),
        )
        return await _fetch_task(db, username, card_id)

    return await discuss_store.run_write(operation)


async def count_open_task_cards(username: str) -> int:
    async with discuss_store.get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM discuss_task_cards "
            "WHERE owner_username=? AND group_id IS NULL",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
    return int(row[0] if row is not None else 0)


async def get_task_card(username: str, card_id: str) -> dict | None:
    async with discuss_store.get_db() as db:
        return await _fetch_task(db, username, card_id)


async def task_card_view(username: str, card_id: str) -> dict:
    card = await get_task_card(username, card_id)
    if card is None:
        raise HTTPException(404, TASK_NOT_FOUND)
    group = None
    group_id = card.get("group_id")
    if group_id:
        raw = await discuss_store.get_group(username, group_id)
        if raw is not None:
            from .chat import display_title

            group = {
                "id": raw["id"],
                "title": display_title(raw),
                "status": raw.get("status"),
                "stop_reason": raw.get("stop_reason"),
            }
    return {
        "id": card["id"],
        "request": card["request"],
        "materials": card["materials"],
        "max_rounds": card.get("max_rounds"),
        "budget_strawberries": card.get("budget_strawberries"),
        "group_id": group_id,
        "group": group,
        "created_at": card["created_at"],
    }


def _message_view(row) -> dict | None:
    if row is None:
        return None
    return {"id": int(row["id"]), "consumed": bool(row["consumed_by"])}


async def _note_message(username: str, message_id) -> dict | None:
    async with discuss_store.get_db() as db:
        async with db.execute(
            "SELECT id, consumed_by FROM discuss_messages WHERE id=? AND username=?",
            (message_id, username),
        ) as cursor:
            row = await cursor.fetchone()
    return _message_view(row)


async def note_card_view(username: str, card_id: str) -> dict:
    card = await get_note_card(username, card_id)
    if card is None:
        raise HTTPException(404, NOTE_NOT_FOUND)
    message = None
    if card.get("message_id") is not None:
        message = await _note_message(username, card["message_id"])
    group = None
    group_id = card.get("group_id")
    if group_id:
        raw = await discuss_store.get_group(username, group_id)
        if raw is not None:
            from .chat import display_title

            pending_notes = len(await discuss_store.unread_notes(username, group_id))
            group = {
                "id": raw["id"],
                "title": display_title(raw),
                "status": raw.get("status"),
                "stop_reason": raw.get("stop_reason"),
                "pending_notes": pending_notes,
            }
    return {
        "id": card["id"],
        "group_id": group_id,
        "group_title": card["group_title"],
        "text": card["text"],
        "sent_at": card.get("sent_at"),
        "message": message,
        "group": group,
        "created_at": card["created_at"],
    }


async def consume_task_card(
    db, username: str, card_id: str, group_id: str
) -> bool:
    """在调用方的写事务里消费一张未使用的任务卡。"""
    cursor = await db.execute(
        "UPDATE discuss_task_cards SET group_id=?, updated_at=? "
        "WHERE id=? AND owner_username=? AND group_id IS NULL",
        (group_id, utc_now(), card_id, username),
    )
    return cursor.rowcount > 0


async def create_note_card(
    username: str,
    conversation_id: str,
    group_id: str,
    group_title: str,
    text: str,
) -> dict:
    card_id = str(uuid4())
    now = utc_now()

    async def operation(db):
        await db.execute(
            """INSERT INTO discuss_note_cards
               (id, owner_username, conversation_id, group_id, group_title,
                text, message_id, sent_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,NULL,NULL,?,?)""",
            (card_id, username, conversation_id, group_id, group_title,
             text, now, now),
        )
        return await _fetch_note(db, username, card_id)

    return await discuss_store.run_write(operation)


async def get_note_card(username: str, card_id: str) -> dict | None:
    async with discuss_store.get_db() as db:
        return await _fetch_note(db, username, card_id)


async def _count_unread(db, username: str, group_id: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM discuss_messages WHERE group_id=? AND username=? "
        "AND sender='user' AND kind='user' AND consumed_by IS NULL",
        (group_id, username),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0] if row is not None else 0)


def _posted_message_id(result) -> int | None:
    if isinstance(result, dict):
        value = result.get("id")
    elif type(result) is int:
        value = result
    else:
        value = None
    return int(value) if type(value) is int else None


async def send_note_card(username: str, card_id: str) -> dict:
    """把一张意见卡作为插话送进群；重复点击不重复插话。"""

    async def operation(db):
        card = await _fetch_note(db, username, card_id)
        if card is None:
            raise HTTPException(404, NOTE_NOT_FOUND)
        if card.get("message_id") is not None:
            return
        group_id = card.get("group_id")
        if not group_id:
            raise HTTPException(409, GROUP_DELETED)
        group = await discuss_store.get_group_on_connection(db, username, group_id)
        if group is None:
            raise HTTPException(409, GROUP_DELETED)
        if group.get("status") in ("closed", "failed"):
            raise HTTPException(409, GROUP_CLOSED)
        # 惰性导入，避免 service -> cards -> service 的循环导入。
        from discuss import service

        service._check_crisis(card["text"])
        if await _count_unread(db, username, group_id) >= 5:
            raise HTTPException(409, NOTE_TOO_MANY)
        async with db.execute(
            "SELECT COALESCE(MAX(id),0) FROM discuss_messages "
            "WHERE group_id=? AND username=?",
            (group_id, username),
        ) as cursor:
            before_id = int((await cursor.fetchone())[0])
        try:
            posted = await discuss_store.post_user_note_in_txn(
                db, username, group_id, card["text"], int(group.get("round") or 0)
            )
        except ValueError as error:
            if str(error) == "too_many":
                raise HTTPException(409, NOTE_TOO_MANY) from error
            if str(error) == "closed":
                raise HTTPException(409, GROUP_CLOSED) from error
            raise
        message_id = _posted_message_id(posted)
        if message_id is None:
            async with db.execute(
                "SELECT MAX(id) FROM discuss_messages WHERE group_id=? AND username=?",
                (group_id, username),
            ) as cursor:
                row = await cursor.fetchone()
            if row is not None and row[0] is not None and int(row[0]) > before_id:
                message_id = int(row[0])
        if message_id is None:
            raise HTTPException(409, GROUP_DELETED)
        now = utc_now()
        cursor = await db.execute(
            "UPDATE discuss_note_cards SET message_id=?, sent_at=?, updated_at=? "
            "WHERE id=? AND owner_username=? AND message_id IS NULL",
            (message_id, now, now, card_id, username),
        )
        if cursor.rowcount <= 0:
            raise HTTPException(409, NOTE_NOT_FOUND)

    await discuss_store.run_write(operation)
    return await note_card_view(username, card_id)
