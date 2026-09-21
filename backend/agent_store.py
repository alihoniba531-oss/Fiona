"""Owned AI identities and private conversations.

All writes validate ownership inside their transaction. No function here creates
a user: delayed work must not recreate an account or a deleted conversation.
"""
import json
from uuid import uuid4

import aiosqlite

import database


class ResourceNotFound(LookupError):
    """Missing and inaccessible resources intentionally share one outcome."""


MIGRATION_VERSION = "20260905_private_agents_v1"
PUBLIC_AGENT_FIELDS = (
    "id", "display_name", "bio", "avatar_emoji", "is_public", "created_at",
)


async def _one(db, sql, parameters=()):
    async with db.execute(sql, parameters) as cursor:
        row = await cursor.fetchone()
        return dict(zip((column[0] for column in cursor.description), row)) if row else None


def _agent(row):
    result = dict(row)
    result["is_public"] = bool(result["is_public"])
    result.pop("private_memory_json", None)
    result.pop("memory_revision", None)
    return result


def _conversation(row):
    result = dict(row)
    result["is_default"] = bool(result["is_default"])
    result.pop("auto_title", None)
    return result


def public_agent(agent):
    """Explicit allowlist: private personality and account names never leave it."""
    return {key: agent[key] for key in PUBLIC_AGENT_FIELDS}


async def _ensure_agent(db, username):
    if not await database._users_exist(db, username):
        raise ResourceNotFound("Resource not found")
    row = await _one(db, "SELECT * FROM agents WHERE owner_username = ?", (username,))
    if row is None:
        agent_id = str(uuid4())
        legacy = await _one(db, "SELECT profile_json FROM users WHERE username = ?", (username,))
        try:
            memory = json.loads(legacy["profile_json"] or "{}")
        except (TypeError, ValueError):
            memory = {}
        if not isinstance(memory, dict):
            memory = {}
        await db.execute(
            "INSERT INTO agents (id, owner_username, private_memory_json) VALUES (?, ?, ?)",
            (agent_id, username, json.dumps(memory, ensure_ascii=False)),
        )
        row = await _one(db, "SELECT * FROM agents WHERE id = ?", (agent_id,))
    return _agent(row)


async def _ensure_default_conversation(db, username):
    agent = await _ensure_agent(db, username)
    row = await _one(
        db, "SELECT * FROM conversations WHERE owner_username = ? AND is_default = 1",
        (username,),
    )
    if row is None:
        conversation_id = str(uuid4())
        await db.execute(
            """INSERT INTO conversations (id, owner_username, agent_id, title, is_default, auto_title)
               VALUES (?, ?, ?, '与我的分身交流', 1, 0)""",
            (conversation_id, username, agent["id"]),
        )
        row = await _one(db, "SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    return {"conversation": _conversation(row), "agent": agent}


async def _owned_conversation(db, username, conversation_id):
    row = await _one(
        db,
        """SELECT c.* FROM conversations c
           JOIN users u ON u.username = c.owner_username
           JOIN agents a ON a.id = c.agent_id AND a.owner_username = c.owner_username
           WHERE c.id = ? AND c.owner_username = ?""",
        (conversation_id, username),
    )
    if row is None:
        raise ResourceNotFound("Resource not found")
    return _conversation(row)


async def migrate_avatar_schema(db):
    """Versioned, atomic migration. Unexpected failures propagate and roll back."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        applied = await _one(
            db, "SELECT version FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,),
        )
        if applied:
            await db.commit()
            return
        await db.execute(
            """CREATE TABLE IF NOT EXISTS agents (
                   id TEXT PRIMARY KEY,
                   owner_username TEXT UNIQUE NOT NULL,
                   display_name TEXT NOT NULL DEFAULT 'Chloe',
                   bio TEXT NOT NULL DEFAULT '',
                   personality TEXT NOT NULL DEFAULT '',
                   private_memory_json TEXT NOT NULL DEFAULT '{}',
                   memory_revision INTEGER NOT NULL DEFAULT 0,
                   avatar_emoji TEXT NOT NULL DEFAULT '✦',
                   is_public INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0, 1)),
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS conversations (
                   id TEXT PRIMARY KEY,
                   owner_username TEXT NOT NULL,
                   agent_id TEXT NOT NULL,
                   title TEXT NOT NULL DEFAULT '新的交流',
                   auto_title INTEGER NOT NULL DEFAULT 1 CHECK(auto_title IN (0, 1)),
                   is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0, 1)),
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        await db.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_default
               ON conversations(owner_username) WHERE is_default = 1"""
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations(owner_username, updated_at)"
        )
        async with db.execute("PRAGMA table_info(messages)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        for column in ("conversation_id", "agent_id"):
            if column not in columns:
                await db.execute(f"ALTER TABLE messages ADD COLUMN {column} TEXT DEFAULT NULL")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id)"
        )
        async with db.execute("SELECT username FROM users") as cursor:
            usernames = [row[0] for row in await cursor.fetchall()]
        for username in usernames:
            context = await _ensure_default_conversation(db, username)
            await db.execute(
                """UPDATE messages SET conversation_id = ?, agent_id = ?
                   WHERE username = ? AND conversation_id IS NULL""",
                (context["conversation"]["id"], context["agent"]["id"], username),
            )
        # Detect orphaned legacy data rather than silently assigning it to a new account.
        orphan = await _one(db, "SELECT id FROM messages WHERE conversation_id IS NULL LIMIT 1")
        if orphan:
            raise RuntimeError("Avatar migration found messages without an existing owner")
        await db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (MIGRATION_VERSION,))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def get_my_agent(username):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        agent = await _ensure_agent(db, username)
        await db.commit()
        return agent


async def update_my_agent(username, updates):
    allowed = {"display_name", "bio", "personality", "avatar_emoji", "is_public"}
    if set(updates) - allowed:
        raise ValueError("Unsupported agent fields")
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        agent = await _ensure_agent(db, username)
        if updates:
            fields = ", ".join(f"{name} = ?" for name in updates)
            await db.execute(
                f"UPDATE agents SET {fields} WHERE id = ? AND owner_username = ?",
                (*updates.values(), agent["id"], username),
            )
        if "is_public" in updates and not updates["is_public"]:
            from exchange_store import stop_exchanges_for_agent
            await stop_exchanges_for_agent(db, agent["id"])
        row = await _one(db, "SELECT * FROM agents WHERE id = ?", (agent["id"],))
        await db.commit()
        return _agent(row)


async def get_memory_snapshot(username, conversation_id=None):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await _ensure_agent(db, username)
        if conversation_id is not None:
            await _owned_conversation(db, username, conversation_id)
        row = await _one(
            db, "SELECT private_memory_json, memory_revision FROM agents WHERE owner_username = ?", (username,),
        )
        try:
            profile = json.loads(row["private_memory_json"] or "{}")
        except (TypeError, ValueError):
            profile = {}
        await db.commit()
        return {"profile": profile if isinstance(profile, dict) else {}, "revision": row["memory_revision"]}


async def update_memory(username, profile, expected_revision=None, conversation_id=None):
    """Private memory never enters the legacy social profile used by matching."""
    async with aiosqlite.connect(database.DB_PATH) as db:
        cursor = await db.execute(
            """UPDATE agents SET private_memory_json = ?, memory_revision = memory_revision + 1
               WHERE owner_username = ? AND EXISTS (
                   SELECT 1 FROM users u WHERE u.username = agents.owner_username
               ) AND (? IS NULL OR memory_revision = ?)
               AND (? IS NULL OR EXISTS (
                   SELECT 1 FROM conversations c WHERE c.id = ?
                   AND c.owner_username = agents.owner_username AND c.agent_id = agents.id
               ))""",
            (json.dumps(profile, ensure_ascii=False), username,
             expected_revision, expected_revision, conversation_id, conversation_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def clear_memory(username):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await _ensure_agent(db, username)
        await db.execute(
            """UPDATE agents SET private_memory_json = '{}', memory_revision = memory_revision + 1
               WHERE owner_username = ?""",
            (username,),
        )
        # A deliberate erase also removes the older social profile shown by /profile.
        await db.execute("UPDATE users SET profile_json = '{}' WHERE username = ?", (username,))
        await db.commit()


async def list_public_agents(limit=30, offset=0):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT a.* FROM agents a JOIN users u ON u.username = a.owner_username
               WHERE a.is_public = 1 ORDER BY a.created_at DESC, a.id LIMIT ? OFFSET ?""",
            (limit, offset),
        ) as cursor:
            return [public_agent(_agent(row)) for row in await cursor.fetchall()]


async def get_agent_for_viewer(agent_id, username):
    async with aiosqlite.connect(database.DB_PATH) as db:
        row = await _one(
            db,
            """SELECT a.* FROM agents a JOIN users u ON u.username = a.owner_username
               WHERE a.id = ? AND (a.owner_username = ? OR a.is_public = 1)""",
            (agent_id, username),
        )
        if row is None:
            raise ResourceNotFound("Resource not found")
        agent = _agent(row)
        return agent if agent["owner_username"] == username else public_agent(agent)


async def resolve_chat_conversation(username, conversation_id=None):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if conversation_id is None:
            context = await _ensure_default_conversation(db, username)
        else:
            conversation = await _owned_conversation(db, username, conversation_id)
            agent = await _one(db, "SELECT * FROM agents WHERE id = ?", (conversation["agent_id"],))
            context = {"conversation": conversation, "agent": _agent(agent)}
        await db.commit()
        return context


async def list_conversations(username):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await _ensure_default_conversation(db, username)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id
                           AND m.username = c.owner_username) AS message_count
               FROM conversations c WHERE c.owner_username = ?
               ORDER BY c.updated_at DESC, c.created_at DESC, c.id""",
            (username,),
        ) as cursor:
            conversations = [_conversation(row) for row in await cursor.fetchall()]
        await db.commit()
        return conversations


async def create_conversation(username, title=None, agent_id=None):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        agent = await _ensure_agent(db, username)
        if agent_id is not None and agent_id != agent["id"]:
            raise ResourceNotFound("Resource not found")
        conversation_id = str(uuid4())
        await db.execute(
            """INSERT INTO conversations (id, owner_username, agent_id, title, auto_title)
               VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, username, agent["id"], title or "新的交流", int(not title)),
        )
        row = await _owned_conversation(db, username, conversation_id)
        await db.commit()
        return row


async def get_conversation_messages(username, conversation_id, limit=100):
    async with aiosqlite.connect(database.DB_PATH) as db:
        # One consistent snapshot across ownership, content and agent reads.
        await db.execute("BEGIN")
        conversation = await _owned_conversation(db, username, conversation_id)
        agent = await _one(db, "SELECT * FROM agents WHERE id = ?", (conversation["agent_id"],))
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, role, content, image_path, reference_image_paths, created_at, conversation_id, agent_id
               FROM messages WHERE username = ? AND conversation_id = ?
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (username, conversation_id, limit + 1),
        ) as cursor:
            rows = [database.message_with_image_references(row) for row in await cursor.fetchall()]
        await db.commit()
        return {
            "conversation": conversation,
            "agent": _agent(agent),
            "messages": list(reversed(rows[:limit])),
            "has_more": len(rows) > limit,
            "limit": limit,
        }


async def delete_conversation(username, conversation_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        conversation = await _owned_conversation(db, username, conversation_id)
        async with db.execute(
            "SELECT image_path, reference_image_paths FROM messages WHERE conversation_id = ? AND username = ?",
            (conversation_id, username),
        ) as cursor:
            paths = [path for row in await cursor.fetchall() for path in database.message_upload_paths(row[0], row[1])]
        await db.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND username = ?",
            (conversation_id, username),
        )
        await db.execute(
            "DELETE FROM conversations WHERE id = ? AND owner_username = ?",
            (conversation_id, username),
        )
        upload_paths = await database._queue_unreferenced_uploads(db, paths)
        await db.commit()
        return {"status": "deleted", "upload_paths": upload_paths, "is_default": conversation["is_default"]}
