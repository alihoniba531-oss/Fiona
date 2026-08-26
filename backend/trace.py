# -*- coding: utf-8 -*-
"""
使用埋点。把事件原始写进 events 表，不预聚合。
设计原则：永远不让 trace 失败影响主流程。
"""
import json
import time
import aiosqlite
from contextlib import asynccontextmanager
from database import DB_PATH


async def log_event(
    username: str | None,
    event_type: str,
    name: str | None = None,
    payload: dict | None = None,
    duration_ms: int | None = None,
    success: bool = True,
) -> None:
    """写一条事件。失败只打日志，不抛。"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if username is not None:
                await db.execute("BEGIN IMMEDIATE")
                async with db.execute(
                    "SELECT 1 FROM users WHERE username = ?",
                    (username,),
                ) as cursor:
                    if await cursor.fetchone() is None:
                        await db.rollback()
                        return
            await db.execute(
                "INSERT INTO events (username, event_type, name, payload, duration_ms, success) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    username,
                    event_type,
                    name,
                    json.dumps(payload, ensure_ascii=False) if payload else None,
                    duration_ms,
                    1 if success else 0,
                ),
            )
            await db.commit()
    except Exception as e:
        print(f"[trace] log_event failed: {type(e).__name__}: {e}", flush=True)


@asynccontextmanager
async def trace_span(
    username: str | None,
    event_type: str,
    name: str | None = None,
    payload: dict | None = None,
):
    """耗时测量 + 异常自动标 success=False。

    用法：
        async with trace_span(user, "tool_call", "web_search", {"query": q}):
            result = await web_search(q)
    """
    start = time.time()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        duration_ms = int((time.time() - start) * 1000)
        await log_event(username, event_type, name, payload, duration_ms, ok)
