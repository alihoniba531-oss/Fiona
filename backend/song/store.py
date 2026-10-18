"""写歌数据表与项目 / 歌词 / 版本持久化。

本模块不删除任何音频文件：删除路径只把 ``audio_rel_path`` 登记到
``song_cleanup_queue``，由 ``song.media`` 在事务提交后按目录边界清理。

所有函数都在调用时读取 ``database.DB_PATH`` 与 ``database.SQLITE_BUSY_TIMEOUT``，
测试可 monkeypatch ``database.DB_PATH`` 指到临时库。``fetch_*`` 接收调用方已经
打开的 aiosqlite 连接、不 commit，供 jobs / 删除路径在各自事务里复用。
"""
import json
from uuid import uuid4

import aiosqlite

import database


SONG_TABLES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS song_projects (
        id              TEXT PRIMARY KEY,
        owner_username  TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        title           TEXT NOT NULL DEFAULT '',
        brief_json      TEXT NOT NULL DEFAULT '{}',
        structure_json  TEXT NOT NULL DEFAULT '[]',
        lyrics_revision INTEGER NOT NULL DEFAULT 0,
        revision        INTEGER NOT NULL DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_song_projects_owner_conversation
        ON song_projects(owner_username, conversation_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS song_lyrics (
        project_id          TEXT NOT NULL,
        revision            INTEGER NOT NULL,
        sections_json       TEXT NOT NULL,
        check_json          TEXT NOT NULL,
        changed_section_ids TEXT NOT NULL DEFAULT '[]',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (project_id, revision)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS song_versions (
        id               TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL,
        owner_username   TEXT NOT NULL,
        lyrics_revision  INTEGER NOT NULL,
        provider         TEXT NOT NULL,
        params_json      TEXT NOT NULL,
        status           TEXT NOT NULL,
        provider_task_id TEXT,
        progress         INTEGER NOT NULL DEFAULT 0,
        strawberries     INTEGER NOT NULL DEFAULT 0,
        billing_state    TEXT NOT NULL,
        idempotency_key  TEXT NOT NULL,
        audio_rel_path   TEXT,
        duration_s       REAL,
        captions_raw     TEXT,
        failure_code     TEXT,
        failure_message  TEXT,
        next_poll_at     REAL,
        deadline_at      REAL,
        created_day      TEXT NOT NULL,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (owner_username, idempotency_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_song_versions_owner_status
        ON song_versions(owner_username, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_song_versions_project
        ON song_versions(project_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS song_cleanup_queue (
        path       TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_object(raw) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_list(raw) -> list:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _normalize_object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_list(value) -> list:
    return value if isinstance(value, list) else []


def _project(row) -> dict:
    return {
        "id": row["id"],
        "owner_username": row["owner_username"],
        "conversation_id": row["conversation_id"],
        "title": row["title"],
        "brief": _load_object(row["brief_json"]),
        "structure": _load_list(row["structure_json"]),
        "lyrics_revision": row["lyrics_revision"],
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _lyrics(row) -> dict:
    return {
        "project_id": row["project_id"],
        "revision": row["revision"],
        "sections": _load_list(row["sections_json"]),
        "check": _load_object(row["check_json"]),
        "changed_section_ids": _load_list(row["changed_section_ids"]),
        "created_at": row["created_at"],
    }


def _version(row) -> dict:
    result = dict(row)
    result["params"] = _load_object(result.get("params_json"))
    return result


def _row_dict(row, cursor) -> dict:
    """兼容调用方连接未设置 aiosqlite.Row 的情况。"""
    if hasattr(row, "keys"):
        return dict(row)
    return dict(zip((column[0] for column in cursor.description), row))


async def _fetch_project_row(db, project_id, owner_username, conversation_id=None):
    sql = "SELECT * FROM song_projects WHERE id = ? AND owner_username = ?"
    parameters = [project_id, owner_username]
    if conversation_id is not None:
        sql += " AND conversation_id = ?"
        parameters.append(conversation_id)
    async with db.execute(sql, parameters) as cursor:
        row = await cursor.fetchone()
        return _row_dict(row, cursor) if row is not None else None


async def fetch_project(db, project_id, owner_username, conversation_id=None) -> dict | None:
    """在调用方事务内读取项目；不做 commit。"""
    row = await _fetch_project_row(db, project_id, owner_username, conversation_id)
    return _project(row) if row else None


async def fetch_latest_lyrics(db, project_id) -> dict | None:
    """在调用方事务内读取最新一稿歌词；不做 commit。"""
    async with db.execute(
        "SELECT * FROM song_lyrics WHERE project_id = ? ORDER BY revision DESC LIMIT 1",
        (project_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return _lyrics(_row_dict(row, cursor)) if row is not None else None


async def create_project(
    *,
    owner_username,
    conversation_id,
    title,
    brief,
    structure,
) -> dict:
    project_id = uuid4().hex
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            """INSERT INTO song_projects
                   (id, owner_username, conversation_id, title, brief_json, structure_json,
                    lyrics_revision, revision)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0)""",
            (
                project_id,
                owner_username,
                conversation_id,
                title or "",
                _dumps(_normalize_object(brief)),
                _dumps(_normalize_list(structure)),
            ),
        )
        project = await fetch_project(db, project_id, owner_username, conversation_id)
        await db.commit()
        return project


async def update_project(
    project_id,
    *,
    owner_username,
    conversation_id,
    title,
    brief,
    structure,
) -> dict | None:
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        if await _fetch_project_row(db, project_id, owner_username, conversation_id) is None:
            await db.rollback()
            return None
        await db.execute(
            """UPDATE song_projects
                  SET title = ?, brief_json = ?, structure_json = ?,
                      revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_username = ?""",
            (
                title or "",
                _dumps(_normalize_object(brief)),
                _dumps(_normalize_list(structure)),
                project_id,
                owner_username,
            ),
        )
        project = await fetch_project(db, project_id, owner_username, conversation_id)
        await db.commit()
        return project


async def get_project(project_id, *, owner_username, conversation_id=None) -> dict | None:
    """conversation_id=None 表示不校验会话（仍校验 owner）。"""
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN")
        row = await _fetch_project_row(db, project_id, owner_username, conversation_id)
        await db.commit()
        return _project(row) if row else None


async def get_latest_project_for_conversation(owner_username, conversation_id) -> dict | None:
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM song_projects
                WHERE owner_username = ? AND conversation_id = ?
                ORDER BY updated_at DESC, rowid DESC LIMIT 1""",
            (owner_username, conversation_id),
        ) as cursor:
            row = await cursor.fetchone()
        return _project(row) if row else None


async def save_lyrics(
    project_id,
    *,
    owner_username,
    conversation_id,
    base_revision,
    sections,
    check,
    changed_section_ids,
) -> dict:
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        project = await fetch_project(db, project_id, owner_username, conversation_id)
        if project is None:
            await db.rollback()
            return {"status": "not_found"}
        if base_revision != project["lyrics_revision"]:
            await db.rollback()
            return {"status": "conflict"}
        new_revision = project["lyrics_revision"] + 1
        await db.execute(
            """INSERT INTO song_lyrics
                   (project_id, revision, sections_json, check_json, changed_section_ids)
               VALUES (?, ?, ?, ?, ?)""",
            (
                project_id,
                new_revision,
                _dumps(_normalize_list(sections)),
                _dumps(_normalize_object(check)),
                _dumps(_normalize_list(changed_section_ids)),
            ),
        )
        await db.execute(
            """UPDATE song_projects
                  SET lyrics_revision = ?, revision = revision + 1,
                      updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_username = ?""",
            (new_revision, project_id, owner_username),
        )
        project = await fetch_project(db, project_id, owner_username, conversation_id)
        lyrics = await fetch_latest_lyrics(db, project_id)
        await db.commit()
        return {"status": "ok", "project": project, "lyrics": lyrics}


async def get_lyrics(project_id, revision=None) -> dict | None:
    """revision=None 返回最新一稿；否则返回指定稿号。"""
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        if revision is None:
            sql = "SELECT * FROM song_lyrics WHERE project_id = ? ORDER BY revision DESC LIMIT 1"
            parameters = (project_id,)
        else:
            sql = "SELECT * FROM song_lyrics WHERE project_id = ? AND revision = ? LIMIT 1"
            parameters = (project_id, revision)
        async with db.execute(sql, parameters) as cursor:
            row = await cursor.fetchone()
        return _lyrics(row) if row else None


async def list_versions(project_id, limit=10) -> list[dict]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        limit = 10
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM song_versions WHERE project_id = ?
               ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (project_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_version(row) for row in rows]


async def queue_song_cleanup(db, paths) -> list[str]:
    """把相对 ``FIONA_SONG_DIR`` 的路径登记进清理队列；不 commit。"""
    unique = list(dict.fromkeys(
        path for path in (paths or []) if isinstance(path, str) and path
    ))
    for path in unique:
        await db.execute(
            "INSERT OR IGNORE INTO song_cleanup_queue (path) VALUES (?)",
            (path,),
        )
    return unique


async def _project_ids_for_user(db, username) -> list[str]:
    async with db.execute(
        "SELECT id FROM song_projects WHERE owner_username = ?", (username,),
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def _project_ids_for_conversation(db, username, conversation_id) -> list[str]:
    async with db.execute(
        "SELECT id FROM song_projects WHERE owner_username = ? AND conversation_id = ?",
        (username, conversation_id),
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def _audio_paths_for_projects(db, project_ids) -> list[str]:
    if not project_ids:
        return []
    placeholders = ",".join("?" for _ in project_ids)
    async with db.execute(
        f"""SELECT audio_rel_path FROM song_versions
             WHERE project_id IN ({placeholders}) AND audio_rel_path IS NOT NULL
             ORDER BY rowid""",
        project_ids,
    ) as cursor:
        return [row[0] for row in await cursor.fetchall() if row[0]]


def _placeholders(values) -> str:
    return ",".join("?" for _ in values)


async def delete_user_song_data(db, username) -> list[str]:
    """在调用方事务内删除该用户的全部写歌行并登记音频；不删除文件、不 commit。"""
    project_ids = await _project_ids_for_user(db, username)
    audio_paths = await _audio_paths_for_projects(db, project_ids)
    if project_ids:
        marks = _placeholders(project_ids)
        await db.execute(
            f"""DELETE FROM song_versions
                 WHERE owner_username = ? OR project_id IN ({marks})""",
            (username, *project_ids),
        )
        await db.execute(
            f"DELETE FROM song_lyrics WHERE project_id IN ({marks})", project_ids,
        )
    else:
        await db.execute("DELETE FROM song_versions WHERE owner_username = ?", (username,))
    await db.execute("DELETE FROM song_projects WHERE owner_username = ?", (username,))
    await queue_song_cleanup(db, audio_paths)
    return audio_paths


async def delete_conversation_song_data(db, username, conversation_id) -> list[str]:
    """在调用方事务内删除该会话的写歌行并登记音频；不删除文件、不 commit。"""
    project_ids = await _project_ids_for_conversation(db, username, conversation_id)
    audio_paths = await _audio_paths_for_projects(db, project_ids)
    if project_ids:
        marks = _placeholders(project_ids)
        await db.execute(
            f"DELETE FROM song_versions WHERE project_id IN ({marks})", project_ids,
        )
        await db.execute(
            f"DELETE FROM song_lyrics WHERE project_id IN ({marks})", project_ids,
        )
    await db.execute(
        "DELETE FROM song_projects WHERE owner_username = ? AND conversation_id = ?",
        (username, conversation_id),
    )
    await queue_song_cleanup(db, audio_paths)
    return audio_paths
