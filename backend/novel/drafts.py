"""书斋草稿：聊天里定下的小说设定先存这里，由主人在向导里确认后建书。

草稿免费且不建 novels 行；只有 ``service.create`` 带 ``draft_id`` 时才会在
同一事务里把 ``novel_id`` 填上。这里不导入小说引擎，避免和 service 形成环。
"""
from __future__ import annotations

import json
from uuid import uuid4

import aiosqlite

import database

DEFAULT_TARGET = {"min_chapters": 50, "max_chapters": 70, "chapter_words": 2000}
_TARGET_RANGES = {
    "min_chapters": (1, 200),
    "max_chapters": (1, 200),
    "chapter_words": (1000, 4000),
}
_INTEGER_ERROR = "草稿的章数与每章字数须为整数且在允许范围内"


async def validate_draft_args(args) -> tuple[dict | None, str | None]:
    """把 Claude 的工具参数收敛成向导可用的草稿字段。

    返回 ``(clean, None)`` 或 ``(None, error)``。整数只接受真正的 int
    （bool、字符串、浮点都不算），缺省时使用 ``Target`` 的默认值。
    """
    args = args if isinstance(args, dict) else {}
    title = args.get("title")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60:
        return None, "草稿的标题要在 1–60 字之间"
    seed_idea = args.get("seed_idea")
    if not isinstance(seed_idea, str) or not 1 <= len(seed_idea.strip()) <= 2000:
        return None, "草稿的故事思路要在 1–2000 字之间"
    target = {}
    for key, default in DEFAULT_TARGET.items():
        value = args.get(key, default)
        low, high = _TARGET_RANGES[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            return None, _INTEGER_ERROR
        target[key] = value
    if target["min_chapters"] > target["max_chapters"]:
        return None, "草稿的最少章数不得超过最多章数"
    return {
        "title": title.strip(),
        "seed_idea": seed_idea.strip(),
        "target": target,
    }, None


async def create_draft(username: str, conversation_id: str, title: str, seed_idea: str, target: dict) -> dict:
    """插入一份草稿，返回与 :func:`get_draft` 相同形状的字典。"""
    draft_id = str(uuid4())
    target_json = json.dumps(target if isinstance(target, dict) else {}, ensure_ascii=False)
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        await db.execute(
            """INSERT INTO novel_drafts
               (id, owner_username, conversation_id, title, seed_idea, target_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (draft_id, username, conversation_id, title, seed_idea, target_json),
        )
        await db.commit()
    draft = await get_draft(username, draft_id)
    if draft is None:
        raise RuntimeError("draft insert not visible")
    return draft


async def get_draft(username: str, draft_id: str) -> dict | None:
    """只返回 owner_username 匹配的草稿；不存在或非本人返回 None。"""
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, title, seed_idea, target_json, novel_id, created_at
               FROM novel_drafts WHERE id = ? AND owner_username = ?""",
            (draft_id, username),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    try:
        parsed = json.loads(row["target_json"] or "{}")
    except (TypeError, ValueError):
        parsed = {}
    return {
        "id": row["id"],
        "title": row["title"],
        "seed_idea": row["seed_idea"],
        "target": parsed if isinstance(parsed, dict) else {},
        "novel_id": row["novel_id"],
        "created_at": row["created_at"],
    }


async def count_open_drafts(username: str) -> int:
    """该用户尚未消费的草稿数；已建书的草稿不算。"""
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM novel_drafts WHERE owner_username = ? AND novel_id IS NULL",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def consume_draft(db, username: str, draft_id: str, novel_id: str) -> bool:
    """在调用方的事务里消费草稿；已消费、非本人或不存在都返回 False。"""
    cursor = await db.execute(
        """UPDATE novel_drafts SET novel_id = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND owner_username = ? AND novel_id IS NULL""",
        (novel_id, draft_id, username),
    )
    return cursor.rowcount > 0
