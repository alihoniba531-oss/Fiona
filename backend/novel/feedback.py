"""聊天里的修改意见卡：参数校验与建卡。

工具只写 ``novel_feedback`` 行，作者在卡片上点按钮才会交给编辑部或重新
定稿。这里不导入 ``novel.service``，避免和 service 形成环。
"""
from __future__ import annotations

import json
from uuid import uuid4

import aiosqlite

import database

TEXT_MAX = 500
ISSUE_MAX = 200
WRITTEN_MAX = 10


def validate_feedback_args(args, book) -> tuple[dict | None, str | None]:
    """把 Claude 的工具参数收敛成修改意见卡的字段。

    返回 ``(clean, None)`` 或 ``(None, error)``。格式错误一次报全；有格式
    错误时不再检查内容是否为空或书的状态。``book`` 是 ``service.detail()``
    的返回值。
    """
    args = args if isinstance(args, dict) else {}
    title = (book.get("title") or "").strip() or "未命名小说"
    status = book.get("status")
    chapters = book.get("chapters") or []
    chapters_done = book.get("chapters_done")
    if isinstance(chapters_done, bool) or not isinstance(chapters_done, int):
        chapters_done = 0

    next_raw = args.get("next_chapters")
    next_text = next_raw.strip() if isinstance(next_raw, str) else ""
    current_raw = args.get("current_plan")
    current_text = current_raw.strip() if isinstance(current_raw, str) else ""
    written_raw = args.get("written_chapters")
    written_list = written_raw if isinstance(written_raw, list) else []

    errors: list[str] = []

    def add_error(message: str):
        if message not in errors:
            errors.append(message)

    # 第一段：格式错误，按表顺序收集，同一句只记一次。
    if next_raw is not None and not isinstance(next_raw, str):
        add_error("next_chapters 要是文字")
    if isinstance(next_raw, str) and len(next_text) > TEXT_MAX:
        add_error(f"交给编辑部的要求现在 {len(next_text)} 字，最多 {TEXT_MAX} 字，请精简后再写")
    if current_raw is not None and not isinstance(current_raw, str):
        add_error("current_plan 要是文字")
    if isinstance(current_raw, str) and len(current_text) > TEXT_MAX:
        add_error(f"重新定稿的要求现在 {len(current_text)} 字，最多 {TEXT_MAX} 字，请精简后再写")
    if written_raw is not None and not isinstance(written_raw, list):
        add_error("written_chapters 要是列表")

    done_titles: dict[int, str] = {}
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        number = chapter.get("chapter")
        if isinstance(number, bool) or not isinstance(number, int):
            continue
        if chapter.get("status") not in ("done", "stale") or number > chapters_done:
            continue
        done_titles[number] = chapter.get("title") or ""

    written: list[dict] = []
    if isinstance(written_raw, list) and len(written_raw) > WRITTEN_MAX:
        add_error(f"已写章节现在 {len(written_raw)} 条，最多 {WRITTEN_MAX} 条")
    elif isinstance(written_raw, list):
        for item in written_raw:
            if not isinstance(item, dict):
                add_error("已写章节的每一项要有 chapter（整数）和 issue（文字）")
                continue
            chapter = item.get("chapter")
            issue = item.get("issue")
            if (isinstance(chapter, bool) or not isinstance(chapter, int)
                    or not isinstance(issue, str)):
                add_error("已写章节的每一项要有 chapter（整数）和 issue（文字）")
                continue
            if chapter not in done_titles:
                add_error(f"第 {chapter} 章还没写好，不能放进已写章节")
                continue
            issue_text = issue.strip()
            if not issue_text or len(issue_text) > ISSUE_MAX:
                add_error(f"第 {chapter} 章的问题现在 {len(issue_text)} 字，要在 1–{ISSUE_MAX} 字之间")
                continue
            written.append({
                "chapter": chapter,
                "title": done_titles[chapter],
                "issue": issue_text,
            })

    if errors:
        return None, "；".join(errors)

    # 第二段：三类都为空。
    if not next_text and not current_text and not written_list:
        return None, "修改意见卡至少要写一项：以后章节的要求、这一章细纲的要求或已写章节的问题"

    awaiting_chapter = None
    if status == "awaiting_plan":
        awaiting = [
            chapter["chapter"] for chapter in chapters
            if isinstance(chapter, dict)
            and chapter.get("status") == "awaiting_plan_approval"
            and isinstance(chapter.get("chapter"), int)
            and not isinstance(chapter.get("chapter"), bool)
        ]
        if awaiting:
            awaiting_chapter = max(awaiting)

    config = book.get("config")
    automation = config.get("automation") if isinstance(config, dict) else None
    if not isinstance(automation, str):
        automation = "per_batch"

    max_chapters = book.get("max_chapters")
    if isinstance(max_chapters, bool) or not isinstance(max_chapters, int):
        max_chapters = None

    # 第三段：状态错误，全部收集。
    if next_text and status == "completed":
        add_error(f"《{title}》已经完结，编辑部不会再读留言；已写章节的问题可以放进 written_chapters")
    if next_text and status == "failed":
        add_error(f"《{title}》处于失败状态，编辑部不会再读留言；已写章节的问题可以放进 written_chapters")
    if current_text:
        if status != "awaiting_plan" or awaiting_chapter is None:
            add_error(f"《{title}》现在没有等作者确认的细纲，current_plan 只能在等确认细纲时填写")
        elif automation != "per_chapter":
            add_error(f"《{title}》现在不是逐章确认，卡片上不能重新定稿这一章细纲；这一项请在回复里请作者到书斋处理")

    if errors:
        return None, "；".join(errors)

    return {
        "title": title,
        "status": status,
        "automation": automation,
        "max_chapters": max_chapters,
        "next_chapters": next_text,
        "current_plan": current_text,
        "awaiting_chapter": awaiting_chapter,
        "plan_chapter": awaiting_chapter if current_text else None,
        "written": written,
    }, None


async def create_feedback(username, conversation_id, book, clean) -> dict:
    """插入一张修改意见卡，并在同一个连接里判断待确认章是不是最后一章。"""
    feedback_id = str(uuid4())
    written_json = json.dumps(clean["written"], ensure_ascii=False)
    awaiting_is_final = False
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        await db.execute(
            """INSERT INTO novel_feedback
               (id, owner_username, conversation_id, novel_id, book_title,
                next_chapters, current_plan, plan_chapter, written_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (feedback_id, username, conversation_id, book["id"], clean["title"],
             clean["next_chapters"], clean["current_plan"], clean["plan_chapter"],
             written_json),
        )
        await db.commit()
        awaiting_chapter = clean["awaiting_chapter"]
        if awaiting_chapter is not None:
            async with db.execute(
                "SELECT meeting_json FROM novel_chapters WHERE novel_id=? AND chapter=?",
                (book["id"], awaiting_chapter),
            ) as cursor:
                row = await cursor.fetchone()
            if row is not None:
                try:
                    meeting = json.loads(row[0] or "{}")
                except (TypeError, ValueError):
                    meeting = None
                if isinstance(meeting, dict):
                    decision = meeting.get("decision")
                    if isinstance(decision, dict) and decision.get("ending_status") == "end":
                        awaiting_is_final = True
    return {"id": feedback_id, "awaiting_is_final": awaiting_is_final}
