"""Persistent authorization, bounded work reservations and public-only exchanges."""
import json
from uuid import uuid4

import aiosqlite

import database
from agent_store import ResourceNotFound, _one
from official_agents import get_official_agent


MIGRATION_VERSION = "20260905_agent_exchanges_v1"
OFFICIAL_MIGRATION_VERSION = "20260905_official_agent_exchanges_v2"
EXTENDED_OFFICIAL_MIGRATION_VERSION = "20260905_official_exchange_limits_v3"
WORKFLOW_MIGRATION_VERSION = "20260905_official_exchange_workflow_v4"
DRAFT_REVIEW_WORKFLOW_VERSION = "draft_review_v1"
# Kept separate so compatibility tests can still create historical sessions.
OFFICIAL_WORKFLOW_VERSION = DRAFT_REVIEW_WORKFLOW_VERSION
MAX_WORKFLOW_CONTENT_CHARS = 48_000
WORKFLOW_REVIEW_CATEGORIES = frozenset({"deliverable", "constraints", "consistency", "usability", "claims"})
TOKEN_BUDGET = 80_000
OFFICIAL_MAX_TURNS = 99
OFFICIAL_TOPIC_MAX_LENGTH = 10_000
# Legacy: 99 replies and one summary. The new workflow uses at most 99 calls,
# each reserving 128,000 input bytes, 1,024 framing and 8,192 output tokens.
# Both remain below this allowance even when every call uses estimated usage.
OFFICIAL_TOKEN_BUDGET = 14_000_000
MAX_ACTIVE_PER_USER = 3
MAX_RUNNING_PER_USER = 1
PUBLIC_CLOSED_REASON = "参与分身已关闭公开展示，本次交流已停止。"
RESTART_REASON = "服务已重启，本次交流已停止，请重新发起。"
PARTICIPANT_STOP_REASON = "参与者已停止本次交流。"
BUDGET_REASON = "本次交流已达到调用或用量上限，已停止。"
UNAVAILABLE_REASON = "参与分身已不可用，本次交流已停止。"
INVALID_WORKFLOW_REASON = "创作流程返回了无效结果，本次交流已停止，已保存的稿件仍可查看。"


class ExchangeConflict(ValueError):
    """A valid participant requested an action unavailable in the current state."""


async def migrate_exchanges_schema(db):
    await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        if await _one(db, "SELECT version FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,)):
            await db.commit()
            return
        await db.execute("""CREATE TABLE agent_exchanges (
            id TEXT PRIMARY KEY,
            initiator_username TEXT NOT NULL,
            recipient_username TEXT NOT NULL,
            initiator_agent_id TEXT NOT NULL,
            recipient_agent_id TEXT NOT NULL,
            pair_key TEXT NOT NULL,
            initiator_json TEXT NOT NULL,
            recipient_json TEXT NOT NULL,
            topic TEXT NOT NULL,
            max_turns INTEGER NOT NULL CHECK(max_turns BETWEEN 2 AND 6),
            turn_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','running','completed','stopped','rejected','failed')),
            summary TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            run_token TEXT,
            inflight_call_id TEXT,
            model_calls INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated INTEGER NOT NULL DEFAULT 0,
            budget_used INTEGER NOT NULL DEFAULT 0,
            reserved_tokens INTEGER NOT NULL DEFAULT 0,
            token_budget INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE UNIQUE INDEX idx_exchange_active_pair
            ON agent_exchanges(pair_key) WHERE status IN ('pending','running')""")
        await db.execute("CREATE INDEX idx_exchange_initiator ON agent_exchanges(initiator_username, updated_at)")
        await db.execute("CREATE INDEX idx_exchange_recipient ON agent_exchanges(recipient_username, updated_at)")
        await db.execute("""CREATE TABLE agent_exchange_messages (
            id TEXT PRIMARY KEY,
            exchange_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            avatar_emoji TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(exchange_id, sequence)
        )""")
        await db.execute("""CREATE TABLE agent_exchange_calls (
            id TEXT PRIMARY KEY,
            exchange_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('turn','summary')),
            status TEXT NOT NULL DEFAULT 'reserved',
            reserved_tokens INTEGER NOT NULL,
            input_limit INTEGER NOT NULL,
            output_limit INTEGER NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            estimated INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            UNIQUE(exchange_id, ordinal)
        )""")
        await db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (MIGRATION_VERSION,))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def migrate_official_exchanges_schema(db):
    """Preserve V1 rows and references while making the official recipient ownerless."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        if await _one(db, "SELECT version FROM schema_migrations WHERE version = ?", (OFFICIAL_MIGRATION_VERSION,)):
            await db.commit()
            return
        # SQLite cannot remove a NOT NULL constraint with ALTER COLUMN. Rebuild
        # this table in one transaction; the message/call tables retain their IDs.
        await db.execute("""CREATE TABLE agent_exchanges_v2 (
            id TEXT PRIMARY KEY,
            initiator_username TEXT NOT NULL,
            recipient_username TEXT,
            initiator_agent_id TEXT NOT NULL,
            recipient_agent_id TEXT NOT NULL,
            pair_key TEXT NOT NULL,
            initiator_json TEXT NOT NULL,
            recipient_json TEXT NOT NULL,
            topic TEXT NOT NULL,
            max_turns INTEGER NOT NULL CHECK(max_turns BETWEEN 2 AND 6),
            turn_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','running','completed','stopped','rejected','failed')),
            summary TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            run_token TEXT,
            inflight_call_id TEXT,
            model_calls INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated INTEGER NOT NULL DEFAULT 0,
            budget_used INTEGER NOT NULL DEFAULT 0,
            reserved_tokens INTEGER NOT NULL DEFAULT 0,
            token_budget INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kind TEXT NOT NULL DEFAULT 'peer' CHECK(kind IN ('peer','official')),
            CHECK((kind = 'peer' AND recipient_username IS NOT NULL)
                OR (kind = 'official' AND recipient_username IS NULL))
        )""")
        async with db.execute("PRAGMA table_info(agent_exchanges)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        # Column names come only from SQLite's schema, quoted as identifiers.
        names = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
        await db.execute(f"INSERT INTO agent_exchanges_v2 ({names}) SELECT {names} FROM agent_exchanges")
        missing = await _one(db, f"SELECT {names} FROM agent_exchanges EXCEPT SELECT {names} FROM agent_exchanges_v2 LIMIT 1")
        counts = await _one(db, """SELECT
            (SELECT COUNT(*) FROM agent_exchanges) AS old_count,
            (SELECT COUNT(*) FROM agent_exchanges_v2) AS new_count""")
        if missing or counts["old_count"] != counts["new_count"]:
            raise RuntimeError("Official exchange migration could not preserve existing rows")
        for table in ("agent_exchange_messages", "agent_exchange_calls"):
            orphan = await _one(db, f"""SELECT child.id FROM {table} child
                LEFT JOIN agent_exchanges_v2 e ON e.id = child.exchange_id WHERE e.id IS NULL LIMIT 1""")
            if orphan:
                raise RuntimeError("Official exchange migration found an orphaned exchange record")
        await db.execute("DROP TABLE agent_exchanges")
        await db.execute("ALTER TABLE agent_exchanges_v2 RENAME TO agent_exchanges")
        await db.execute("""CREATE UNIQUE INDEX idx_exchange_active_pair
            ON agent_exchanges(pair_key) WHERE status IN ('pending','running')""")
        await db.execute("CREATE INDEX idx_exchange_initiator ON agent_exchanges(initiator_username, updated_at)")
        await db.execute("CREATE INDEX idx_exchange_recipient ON agent_exchanges(recipient_username, updated_at)")
        await db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (OFFICIAL_MIGRATION_VERSION,))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def migrate_extended_official_exchanges_schema(db):
    """Raise only official reply limits and retain call provenance without data loss."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        if await _one(db, "SELECT version FROM schema_migrations WHERE version = ?", (EXTENDED_OFFICIAL_MIGRATION_VERSION,)):
            await db.commit()
            return
        # The old CHECK cannot be changed with ALTER COLUMN. Preserve the table's
        # exact values and schema objects while replacing that constraint.
        async with db.execute("""SELECT sql FROM sqlite_master
            WHERE tbl_name = 'agent_exchanges' AND type IN ('index', 'trigger') AND sql IS NOT NULL
            ORDER BY type, name""") as cursor:
            schema_objects = [row[0] for row in await cursor.fetchall()]
        await db.execute("""CREATE TABLE agent_exchanges_v3 (
            id TEXT PRIMARY KEY,
            initiator_username TEXT NOT NULL,
            recipient_username TEXT,
            initiator_agent_id TEXT NOT NULL,
            recipient_agent_id TEXT NOT NULL,
            pair_key TEXT NOT NULL,
            initiator_json TEXT NOT NULL,
            recipient_json TEXT NOT NULL,
            topic TEXT NOT NULL,
            max_turns INTEGER NOT NULL CHECK(typeof(max_turns) = 'integer' AND max_turns BETWEEN 2 AND 99),
            turn_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','running','completed','stopped','rejected','failed')),
            summary TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            run_token TEXT,
            inflight_call_id TEXT,
            model_calls INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated INTEGER NOT NULL DEFAULT 0,
            budget_used INTEGER NOT NULL DEFAULT 0,
            reserved_tokens INTEGER NOT NULL DEFAULT 0,
            token_budget INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kind TEXT NOT NULL DEFAULT 'peer' CHECK(kind IN ('peer','official')),
            CHECK((kind = 'peer' AND recipient_username IS NOT NULL AND max_turns <= 6)
                OR (kind = 'official' AND recipient_username IS NULL))
        )""")
        async with db.execute("PRAGMA table_info(agent_exchanges)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        names = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
        await db.execute(f"INSERT INTO agent_exchanges_v3 ({names}) SELECT {names} FROM agent_exchanges")
        missing = await _one(db, f"SELECT {names} FROM agent_exchanges EXCEPT SELECT {names} FROM agent_exchanges_v3 LIMIT 1")
        counts = await _one(db, """SELECT
            (SELECT COUNT(*) FROM agent_exchanges) AS old_count,
            (SELECT COUNT(*) FROM agent_exchanges_v3) AS new_count""")
        if missing or counts["old_count"] != counts["new_count"]:
            raise RuntimeError("Extended official exchange migration could not preserve existing rows")
        for table in ("agent_exchange_messages", "agent_exchange_calls"):
            orphan = await _one(db, f"""SELECT child.id FROM {table} child
                LEFT JOIN agent_exchanges_v3 e ON e.id = child.exchange_id WHERE e.id IS NULL LIMIT 1""")
            if orphan:
                raise RuntimeError("Extended official exchange migration found an orphaned exchange record")
        await db.execute("DROP TABLE agent_exchanges")
        await db.execute("ALTER TABLE agent_exchanges_v3 RENAME TO agent_exchanges")
        for sql in schema_objects:
            await db.execute(sql)
        # Empty values explicitly mean the provider/model was not recorded for
        # historical calls; never infer it from today's runtime configuration.
        await db.execute("ALTER TABLE agent_exchange_calls ADD COLUMN provider TEXT NOT NULL DEFAULT ''")
        await db.execute("ALTER TABLE agent_exchange_calls ADD COLUMN model TEXT NOT NULL DEFAULT ''")
        await db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (EXTENDED_OFFICIAL_MIGRATION_VERSION,))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def migrate_workflow_exchanges_schema(db):
    """Add draft/review state atomically; old exchanges retain legacy behavior."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        if await _one(db, "SELECT version FROM schema_migrations WHERE version = ?", (WORKFLOW_MIGRATION_VERSION,)):
            await db.commit()
            return
        for column in ("workflow_version", "artifact", "artifact_status", "completion_reason"):
            await db.execute(f"ALTER TABLE agent_exchanges ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        for column in ("stage", "review_json"):
            await db.execute(f"ALTER TABLE agent_exchange_messages ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        await db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (WORKFLOW_MIGRATION_VERSION,))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


def _uses_workflow(row):
    return row["kind"] == "official" and row["workflow_version"] == DRAFT_REVIEW_WORKFLOW_VERSION


def _max_model_calls(row):
    return row["max_turns"] + (0 if _uses_workflow(row) else 1)


def _card(row):
    return {
        "id": row["id"], "display_name": row["display_name"], "bio": row["bio"],
        "avatar_emoji": row["avatar_emoji"], "is_public": bool(row["is_public"]),
        "created_at": row["created_at"],
    }


async def _public_identity(db, *, agent_id=None, username=None):
    condition, value = ("a.id", agent_id) if agent_id is not None else ("a.owner_username", username)
    return await _one(db, f"""SELECT a.id, a.owner_username, a.display_name, a.bio,
        a.avatar_emoji, a.is_public, a.created_at FROM agents a
        JOIN users u ON u.username = a.owner_username WHERE {condition} = ?""", (value,))


async def _participant_row(db, exchange_id, username):
    row = await _one(db, """SELECT e.* FROM agent_exchanges e
        JOIN users u ON u.username = ?
        WHERE e.id = ? AND (e.initiator_username = ? OR (e.kind = 'peer' AND e.recipient_username = ?))""",
        (username, exchange_id, username, username))
    if row is None:
        raise ResourceNotFound("Resource not found")
    return row


def _serialize(row, username, *, include_artifact=True):
    result = {key: row[key] for key in (
        "id", "kind", "topic", "max_turns", "turn_count", "status", "summary", "error", "created_at", "updated_at",
        "workflow_version", "artifact_status", "completion_reason",
    )}
    if include_artifact:
        result["artifact"] = row["artifact"]
    result.update({
        "has_artifact": bool(row["artifact"].strip()),
        "initiator": json.loads(row["initiator_json"]),
        "recipient": json.loads(row["recipient_json"]),
        "viewer_role": "initiator" if row["initiator_username"] == username else "recipient",
        "usage": {
            "model_calls": row["model_calls"], "max_model_calls": _max_model_calls(row),
            "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
            "total_tokens": row["input_tokens"] + row["output_tokens"],
            "estimated": bool(row["estimated"]), "token_budget": row["token_budget"],
            "budget_used": row["budget_used"], "reserved_tokens": row["reserved_tokens"],
        },
    })
    return result


async def _messages(db, exchange_id):
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM agent_exchange_messages WHERE exchange_id = ? ORDER BY sequence", (exchange_id,)) as cursor:
        messages = [dict(row) for row in await cursor.fetchall()]
    for message in messages:
        try:
            review = json.loads(message["review_json"]) if message["review_json"] else None
        except (ValueError, TypeError):
            review = None
        message["review"] = review if isinstance(review, dict) else None
    return messages


async def _allowed(db, row):
    if row["kind"] == "official":
        initiator = await _public_identity(db, agent_id=row["initiator_agent_id"])
        return bool(
            initiator is not None and initiator["owner_username"] == row["initiator_username"]
            and row["recipient_username"] is None and get_official_agent(row["recipient_agent_id"]) is not None
        )
    for side in ("initiator", "recipient"):
        identity = await _public_identity(db, agent_id=row[f"{side}_agent_id"])
        if identity is None or not identity["is_public"] or identity["owner_username"] != row[f"{side}_username"]:
            return False
    return True


def _unavailable_reason(row):
    return UNAVAILABLE_REASON if row["kind"] == "official" else PUBLIC_CLOSED_REASON


async def _count_participation(db, username, *, running_only=False):
    status = "status = 'running'" if running_only else "status IN ('pending','running')"
    count = await _one(db, f"""SELECT COUNT(*) AS n FROM agent_exchanges
        WHERE {status} AND (initiator_username = ? OR (kind = 'peer' AND recipient_username = ?))""",
        (username, username))
    return count["n"]


async def _stop(db, exchange_id, reason):
    await db.execute("""UPDATE agent_exchanges SET status = 'stopped', run_token = NULL,
        error = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status IN ('pending','running')""", (reason, exchange_id))


async def stop_exchanges_for_agent(db, agent_id):
    """Call inside the same transaction that hides a public agent."""
    await db.execute("""UPDATE agent_exchanges SET status = 'stopped', run_token = NULL,
        error = ?, updated_at = CURRENT_TIMESTAMP WHERE kind = 'peer' AND status IN ('pending','running')
        AND (initiator_agent_id = ? OR recipient_agent_id = ?)""",
        (PUBLIC_CLOSED_REASON, agent_id, agent_id))


async def delete_exchanges_for_user(db, username):
    """Account deletion removes both sides of these shared exchanges atomically."""
    for table in ("agent_exchange_messages", "agent_exchange_calls"):
        await db.execute(f"""DELETE FROM {table} WHERE exchange_id IN (
            SELECT id FROM agent_exchanges WHERE initiator_username = ? OR (kind = 'peer' AND recipient_username = ?)
        )""", (username, username))
    await db.execute("DELETE FROM agent_exchanges WHERE initiator_username = ? OR (kind = 'peer' AND recipient_username = ?)", (username, username))


async def recover_interrupted_exchanges():
    """Called only on process startup, never by a routine schema initialization."""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        # A request could have completed upstream before the process died. Charge
        # its full reserved allowance as estimated usage rather than replay it.
        await db.execute("""UPDATE agent_exchanges SET
            input_tokens = input_tokens + COALESCE((SELECT SUM(input_limit)
                FROM agent_exchange_calls c WHERE c.exchange_id = agent_exchanges.id AND c.status = 'reserved'), 0),
            output_tokens = output_tokens + COALESCE((SELECT SUM(output_limit)
                FROM agent_exchange_calls c WHERE c.exchange_id = agent_exchanges.id AND c.status = 'reserved'), 0),
            reserved_tokens = 0, inflight_call_id = NULL, estimated = 1,
            updated_at = CURRENT_TIMESTAMP WHERE id IN (
                SELECT exchange_id FROM agent_exchange_calls WHERE status = 'reserved'
            )""")
        await db.execute("""UPDATE agent_exchange_calls SET status = 'interrupted', estimated = 1,
            input_tokens = input_limit, output_tokens = output_limit, completed_at = CURRENT_TIMESTAMP
            WHERE status = 'reserved'""")
        await db.execute("""UPDATE agent_exchanges SET status = 'stopped', run_token = NULL,
            inflight_call_id = NULL, error = ?,
            updated_at = CURRENT_TIMESTAMP WHERE status = 'running'""", (RESTART_REASON,))
        await db.commit()


async def create_exchange(username, target_agent_id, topic, max_turns=6):
    if get_official_agent(target_agent_id) is not None:
        raise ResourceNotFound("Resource not found")
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        initiator = await _public_identity(db, username=username)
        recipient = await _public_identity(db, agent_id=target_agent_id)
        if recipient is None or not recipient["is_public"]:
            raise ResourceNotFound("Resource not found")
        if initiator is None or not initiator["is_public"]:
            raise ExchangeConflict("请先公开自己的分身，再发起交流。")
        if initiator["owner_username"] == recipient["owner_username"]:
            raise ExchangeConflict("请选择另一位用户的公开分身。")
        pair_key = "|".join(sorted((initiator["id"], recipient["id"])))
        if await _one(db, "SELECT id FROM agent_exchanges WHERE pair_key = ? AND status IN ('pending','running')", (pair_key,)):
            raise ExchangeConflict("你们已有待处理或进行中的交流。")
        for participant in (username, recipient["owner_username"]):
            if await _count_participation(db, participant) >= MAX_ACTIVE_PER_USER:
                raise ExchangeConflict("参与者的待处理交流已达上限，请稍后再试。")
        exchange_id = str(uuid4())
        await db.execute("""INSERT INTO agent_exchanges
            (id, initiator_username, recipient_username, initiator_agent_id, recipient_agent_id,
             pair_key, initiator_json, recipient_json, topic, max_turns, token_budget)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (exchange_id, username, recipient["owner_username"], initiator["id"], recipient["id"], pair_key,
             json.dumps(_card(initiator), ensure_ascii=False), json.dumps(_card(recipient), ensure_ascii=False),
             topic, max_turns, TOKEN_BUDGET))
        row = await _participant_row(db, exchange_id, username)
        await db.commit()
        return _serialize(row, username)


async def create_official_exchange(username, official_agent_id, topic, max_turns=OFFICIAL_MAX_TURNS):
    official = get_official_agent(official_agent_id)
    if official is None:
        raise ResourceNotFound("Resource not found")
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        initiator = await _public_identity(db, username=username)
        if initiator is None:
            raise ExchangeConflict("请先创建自己的分身，再开始官方体验。")
        # No public flag requirement or mutation: these basic details remain in
        # the owner's exchange, and the official role has no account identity.
        pair_key = f"official|{initiator['id']}|{official_agent_id}"
        if await _one(db, "SELECT id FROM agent_exchanges WHERE pair_key = ? AND status IN ('pending','running')", (pair_key,)):
            raise ExchangeConflict("你已有进行中的官方体验，请结束后再开始。")
        if await _count_participation(db, username) >= MAX_ACTIVE_PER_USER:
            raise ExchangeConflict("待处理交流已达上限，请结束后再开始。")
        if await _count_participation(db, username, running_only=True) >= MAX_RUNNING_PER_USER:
            raise ExchangeConflict("你已有进行中的交流，请结束后再开始。")
        exchange_id, run_token = str(uuid4()), str(uuid4())
        await db.execute("""INSERT INTO agent_exchanges
            (id, kind, initiator_username, recipient_username, initiator_agent_id, recipient_agent_id,
             pair_key, initiator_json, recipient_json, topic, max_turns, token_budget, status, run_token, workflow_version)
            VALUES (?, 'official', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)""",
            (exchange_id, username, initiator["id"], official_agent_id, pair_key,
             json.dumps(_card(initiator), ensure_ascii=False), json.dumps(official, ensure_ascii=False),
             topic, max_turns, OFFICIAL_TOKEN_BUDGET, run_token, OFFICIAL_WORKFLOW_VERSION))
        row = await _participant_row(db, exchange_id, username)
        details = {"exchange": _serialize(row, username), "messages": []}
        await db.commit()
        return details, run_token


async def list_exchanges(username, limit=50, offset=0):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""SELECT * FROM agent_exchanges
            WHERE initiator_username = ? OR (kind = 'peer' AND recipient_username = ?)
            ORDER BY updated_at DESC, created_at DESC, id LIMIT ? OFFSET ?""", (username, username, limit, offset)) as cursor:
            return [_serialize(dict(row), username, include_artifact=False) for row in await cursor.fetchall()]


async def exchange_details(username, exchange_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN")
        row = await _participant_row(db, exchange_id, username)
        return {"exchange": _serialize(row, username), "messages": await _messages(db, exchange_id)}


async def transition_exchange(username, exchange_id, action):
    """Return details and a run token only for the one transaction accepting it."""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await _participant_row(db, exchange_id, username)
        run_token = None
        if row["kind"] == "official" and action in {"accept", "reject"}:
            raise ExchangeConflict("官方体验无需接受或拒绝，你可以直接停止交流。")
        if action in {"accept", "reject"} and row["recipient_username"] != username:
            raise ExchangeConflict("只有受邀用户可以处理此邀请。")
        if action == "accept":
            if row["status"] not in {"pending", "running"}:
                raise ExchangeConflict("此邀请已结束，请重新发起。")
            if not await _allowed(db, row):
                await _stop(db, exchange_id, PUBLIC_CLOSED_REASON)
                await db.commit()
                raise ExchangeConflict(PUBLIC_CLOSED_REASON)
            if row["status"] == "pending":
                for participant in (row["initiator_username"], row["recipient_username"]):
                    if await _count_participation(db, participant, running_only=True) >= MAX_RUNNING_PER_USER:
                        raise ExchangeConflict("参与者已有进行中的交流，请结束后再接受。")
                run_token = str(uuid4())
                await db.execute("""UPDATE agent_exchanges SET status = 'running', run_token = ?,
                    updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'""", (run_token, exchange_id))
        elif action == "reject":
            if row["status"] not in {"pending", "rejected"}:
                raise ExchangeConflict("当前状态不能拒绝邀请。")
            await db.execute("UPDATE agent_exchanges SET status = 'rejected', run_token = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (exchange_id,))
        elif action == "stop":
            await _stop(db, exchange_id, PARTICIPANT_STOP_REASON)
        else:
            raise ExchangeConflict("不支持的交流操作。")
        row = await _participant_row(db, exchange_id, username)
        result = {"exchange": _serialize(row, username), "messages": await _messages(db, exchange_id)}
        await db.commit()
        return result, run_token


async def load_running_exchange(exchange_id, run_token):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await _one(db, "SELECT * FROM agent_exchanges WHERE id = ? AND status = 'running' AND run_token = ?", (exchange_id, run_token))
        if row is None:
            return None
        if not await _allowed(db, row):
            await _stop(db, exchange_id, _unavailable_reason(row))
            await db.commit()
            return None
        # Explicit boundary: no usernames, personality, memory or private conversations.
        context = {
            "id": row["id"], "kind": row["kind"], "topic": row["topic"], "max_turns": row["max_turns"],
            "turn_count": row["turn_count"], "initiator": json.loads(row["initiator_json"]),
            "recipient": json.loads(row["recipient_json"]), "messages": await _messages(db, exchange_id),
            "workflow_version": row["workflow_version"], "artifact": row["artifact"],
            "artifact_status": row["artifact_status"], "completion_reason": row["completion_reason"],
        }
        await db.commit()
        return context


async def reserve_model_call(
    exchange_id, run_token, expected_turn_count, kind, input_limit, output_limit, *, provider="", model="",
):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await _one(db, "SELECT * FROM agent_exchanges WHERE id = ? AND status = 'running' AND run_token = ?", (exchange_id, run_token))
        if row is None or row["turn_count"] != expected_turn_count or row["inflight_call_id"] is not None:
            return None
        if not await _allowed(db, row):
            await _stop(db, exchange_id, _unavailable_reason(row))
            await db.commit()
            return None
        if kind not in {"turn", "summary"} or (_uses_workflow(row) and kind != "turn"):
            return None
        if (kind == "turn" and expected_turn_count >= row["max_turns"]) or (kind == "summary" and expected_turn_count != row["max_turns"]):
            return None
        reservation = input_limit + output_limit
        if row["model_calls"] >= _max_model_calls(row) or row["budget_used"] + reservation > row["token_budget"]:
            await _stop(db, exchange_id, BUDGET_REASON)
            await db.commit()
            return None
        call_id = str(uuid4())
        await db.execute("""INSERT INTO agent_exchange_calls
            (id, exchange_id, ordinal, kind, reserved_tokens, input_limit, output_limit, provider, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (call_id, exchange_id, row["model_calls"] + 1, kind, reservation, input_limit, output_limit, provider, model))
        await db.execute("""UPDATE agent_exchanges SET inflight_call_id = ?, model_calls = model_calls + 1,
            budget_used = budget_used + ?, reserved_tokens = reserved_tokens + ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?""", (call_id, reservation, reservation, exchange_id))
        await db.commit()
        return call_id


def _workflow_metadata(row, call, expected_turn_count, result):
    """Validate runner-owned metadata again before any draft can be published.

    Provider payloads never call this API directly. The service validates reviews
    against the current artifact and constructs finalize itself; this boundary
    enforces sequencing and the minimum conditions for an approved artifact.
    """
    expected_stage = "draft" if expected_turn_count == 0 else "review" if expected_turn_count % 2 else "revision"
    stage = result.get("stage")
    content = result.get("content")
    if call["kind"] != "turn" or stage != expected_stage:
        raise ValueError("Invalid workflow stage")
    if not isinstance(content, str) or not content.strip() or len(content) > MAX_WORKFLOW_CONTENT_CHARS:
        raise ValueError("Invalid workflow content")
    review = result.get("review")
    if stage == "review":
        if not row["artifact"].strip() or not isinstance(review, dict):
            raise ValueError("Review requires the saved artifact and validated review")
        review_json = json.dumps(review, ensure_ascii=False, allow_nan=False)
    else:
        if review is not None:
            raise ValueError("Writer cannot publish review metadata")
        review_json = ""
    finalize = result.get("finalize")
    if finalize is not None:
        if not isinstance(finalize, dict) or set(finalize) != {"status", "reason"}:
            raise ValueError("Invalid finalization metadata")
        status, reason = finalize["status"], finalize["reason"]
        if status == "approved":
            checks = review.get("checks") if isinstance(review, dict) else None
            if (stage != "review" or not row["artifact"].strip() or reason != "review_approved"
                    or review.get("verdict") != "approved" or review.get("issues") != []
                    or not isinstance(checks, list) or not checks
                    or not all(isinstance(check, dict) and check.get("status") == "met"
                               and check.get("category") in WORKFLOW_REVIEW_CATEGORIES for check in checks)
                    or {check["category"] for check in checks} != WORKFLOW_REVIEW_CATEGORIES):
                raise ValueError("Approval requires a successful review of the saved artifact")
        elif status == "needs_revision":
            if reason not in {"turn_limit", "no_progress", "output_limit", "incomplete_output"}:
                raise ValueError("Invalid incomplete artifact reason")
            if reason == "turn_limit" and expected_turn_count + 1 < row["max_turns"]:
                raise ValueError("The turn limit has not been reached")
        else:
            raise ValueError("Invalid artifact status")
    elif expected_turn_count + 1 >= row["max_turns"]:
        raise ValueError("The final allowed turn must finalize the workflow")
    return stage, review_json, finalize


def _workflow_summary(finalize):
    if finalize["status"] == "approved":
        return "AI 审稿通过，正式稿件已保存，待用户验收。"
    reason = {
        "turn_limit": "已达到交流次数上限",
        "no_progress": "连续修订未取得实质进展",
        "output_limit": "本次输出未完整结束",
        "incomplete_output": "模型输出未正常结束，稿件未通过验收",
    }[finalize["reason"]]
    return f"{reason}。已保存当前稿件，仍需修订，尚未通过验收。"


async def finish_model_call(exchange_id, run_token, call_id, expected_turn_count, result=None, error=None):
    """Settle usage even after a stop; publish content only under the original authorization."""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await _one(db, "SELECT * FROM agent_exchanges WHERE id = ?", (exchange_id,))
        call = await _one(db, "SELECT * FROM agent_exchange_calls WHERE id = ? AND exchange_id = ? AND status = 'reserved'", (call_id, exchange_id))
        if row is None or call is None:
            return False
        result = result or {}
        input_tokens, output_tokens = result.get("input_tokens"), result.get("output_tokens")
        estimated = not (
            type(input_tokens) is int and input_tokens >= 0 and type(output_tokens) is int and output_tokens >= 0
        )
        if estimated:
            input_tokens, output_tokens = call["input_limit"], call["output_limit"]
        content = result.get("content", "")
        valid = (row["status"] == "running" and row["run_token"] == run_token
                 and row["inflight_call_id"] == call_id and row["turn_count"] == expected_turn_count)
        if valid and not await _allowed(db, row):
            await _stop(db, exchange_id, _unavailable_reason(row))
            valid = False
        workflow = _uses_workflow(row)
        stage, review_json, finalize = "", "", None
        if valid and not error and workflow:
            try:
                stage, review_json, finalize = _workflow_metadata(row, call, expected_turn_count, result)
            except (ValueError, TypeError, OverflowError):
                error = INVALID_WORKFLOW_REASON
        await db.execute("""UPDATE agent_exchange_calls SET status = ?, input_tokens = ?, output_tokens = ?,
            estimated = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
            ("failed" if error else "succeeded" if valid else "discarded", input_tokens, output_tokens, int(estimated), call_id))
        await db.execute("""UPDATE agent_exchanges SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?,
            estimated = MAX(estimated, ?), budget_used = budget_used - ? + ?,
            reserved_tokens = MAX(0, reserved_tokens - ?),
            inflight_call_id = CASE WHEN inflight_call_id = ? THEN NULL ELSE inflight_call_id END,
            updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (input_tokens, output_tokens, int(estimated), call["reserved_tokens"], input_tokens + output_tokens,
             call["reserved_tokens"], call_id, exchange_id))
        if valid:
            if error:
                await db.execute("""UPDATE agent_exchanges SET status = 'failed', run_token = NULL, error = ?
                    WHERE id = ?""", (error, exchange_id))
            elif row["budget_used"] - call["reserved_tokens"] + input_tokens + output_tokens > row["token_budget"]:
                await _stop(db, exchange_id, BUDGET_REASON)
                valid = False
            elif call["kind"] == "summary":
                await db.execute("UPDATE agent_exchanges SET summary = ?, status = 'completed', run_token = NULL WHERE id = ?", (content, exchange_id))
            else:
                speaker = json.loads(row["initiator_json"] if expected_turn_count % 2 == 0 else row["recipient_json"])
                await db.execute("""INSERT INTO agent_exchange_messages
                    (id, exchange_id, sequence, agent_id, display_name, avatar_emoji, content, stage, review_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid4()), exchange_id, expected_turn_count + 1, speaker["id"], speaker["display_name"], speaker["avatar_emoji"], content, stage, review_json))
                await db.execute("UPDATE agent_exchanges SET turn_count = turn_count + 1 WHERE id = ?", (exchange_id,))
                if workflow and stage in {"draft", "revision"}:
                    await db.execute("UPDATE agent_exchanges SET artifact = ?, artifact_status = 'draft' WHERE id = ?", (content, exchange_id))
                if finalize is not None:
                    await db.execute("""UPDATE agent_exchanges SET status = 'completed', run_token = NULL,
                        artifact_status = ?, completion_reason = ?, summary = ? WHERE id = ?""",
                        (finalize["status"], finalize["reason"], _workflow_summary(finalize), exchange_id))
        await db.commit()
        return valid and error is None


async def stop_running_exchange(exchange_id, run_token, reason):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("""UPDATE agent_exchanges SET status = 'stopped', run_token = NULL, error = ?,
            updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'running' AND run_token = ?""",
            (reason, exchange_id, run_token))
        await db.commit()
