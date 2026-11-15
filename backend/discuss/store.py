"""SQLite storage for the agent discussion groups.

Background writes go through :class:`DiscussStepStore.transaction`, which holds
SQLite's write lock while checking both the owner row in ``users`` and the
group's current run token. A stale worker therefore cannot recreate rows after
a delete, a pause or a restart.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import uuid

import aiosqlite

from novel.billing import NovelBilling, RunNoLongerActive
from novel.run_store import utc_now


DISCUSS_TABLES_DDL = (
    """CREATE TABLE IF NOT EXISTS discuss_groups (
        id TEXT PRIMARY KEY, username TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '', request TEXT NOT NULL, materials TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL, stop_reason TEXT, last_error TEXT,
        round INTEGER NOT NULL DEFAULT 0, max_rounds INTEGER NOT NULL,
        plan_json TEXT NOT NULL DEFAULT '{}', plan_revision INTEGER NOT NULL DEFAULT 0,
        config_json TEXT NOT NULL DEFAULT '{}',
        budget_strawberries INTEGER NOT NULL,
        spent_strawberries INTEGER NOT NULL DEFAULT 0,
        reserved_strawberries INTEGER NOT NULL DEFAULT 0,
        output_version INTEGER NOT NULL DEFAULT 0,
        run_token TEXT, created_day TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_discuss_groups_owner ON discuss_groups(username, updated_at)""",
    """CREATE TABLE IF NOT EXISTS discuss_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT NOT NULL, username TEXT NOT NULL,
        round INTEGER NOT NULL DEFAULT 0, sender TEXT NOT NULL, kind TEXT NOT NULL,
        content TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
        step_key TEXT, consumed_by TEXT, created_at TEXT NOT NULL
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_discuss_messages_step
        ON discuss_messages(group_id, step_key) WHERE step_key IS NOT NULL""",
    """CREATE INDEX IF NOT EXISTS idx_discuss_messages_group ON discuss_messages(group_id, id)""",
    """CREATE TABLE IF NOT EXISTS discuss_sources (
        group_id TEXT NOT NULL, username TEXT NOT NULL, sid INTEGER NOT NULL,
        url TEXT NOT NULL, url_key TEXT NOT NULL, title TEXT NOT NULL,
        site_name TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        PRIMARY KEY (group_id, sid), UNIQUE (group_id, url_key)
    )""",
    """CREATE TABLE IF NOT EXISTS discuss_steps (
        group_id TEXT NOT NULL, username TEXT NOT NULL, step_key TEXT NOT NULL,
        role TEXT, model TEXT, status TEXT NOT NULL, request_digest TEXT,
        raw_response TEXT, result_json TEXT, errors_json TEXT, stop_reason TEXT,
        attempts INTEGER, input_tokens INTEGER, output_tokens INTEGER,
        cached_tokens INTEGER, duration_ms INTEGER,
        strawberries_reserved INTEGER NOT NULL DEFAULT 0,
        strawberries_charged INTEGER NOT NULL DEFAULT 0,
        billing_status TEXT NOT NULL DEFAULT 'free',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (group_id, step_key)
    )""",
    """CREATE TABLE IF NOT EXISTS discuss_outputs (
        group_id TEXT NOT NULL, username TEXT NOT NULL, version INTEGER NOT NULL,
        round INTEGER NOT NULL, step_key TEXT NOT NULL, content TEXT NOT NULL,
        verdict_json TEXT, passed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        PRIMARY KEY (group_id, version), UNIQUE (group_id, step_key)
    )""",
)


_GROUP_UPDATE_FIELDS = frozenset({
    "title", "request", "materials", "status", "stop_reason", "last_error",
    "round", "max_rounds", "plan_json", "plan_revision", "config_json",
    "budget_strawberries", "spent_strawberries", "reserved_strawberries",
    "output_version", "run_token", "created_day",
})


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _decode_group(row):
    value = dict(row)
    config = _load_json(value.get("config_json"), {})
    value["config"] = config if isinstance(config, dict) else {}
    plan = _load_json(value.get("plan_json"), {})
    value["plan"] = plan if isinstance(plan, dict) and plan else None
    return value


def _decode_message(row):
    value = dict(row)
    payload = _load_json(value.get("payload_json"), {})
    value["payload"] = payload if isinstance(payload, dict) else {}
    return value


def _decode_output(row):
    value = dict(row)
    verdict = _load_json(value.get("verdict_json"), None)
    value["verdict"] = verdict
    return value


def _decode_source(row):
    value = dict(row)
    value["id"] = f"S{value['sid']}"
    return value


def url_key(url):
    return url.split("#")[0].rstrip("/").lower()


def new_group_id():
    return uuid.uuid4().hex


@asynccontextmanager
async def get_db():
    """Resolve the configured database at call time, including test isolation."""
    import database
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        yield db


connect = get_db


async def run_write(operation):
    """Run ``operation(db)`` inside one cancellation-safe write transaction.

    The whole transaction lives in its own task.  ``NovelBilling._drain``
    shields it, so a cancellation of the caller cannot interrupt a queued
    aiosqlite statement or skip rollback/commit/connection close.  The
    CancelledError is delivered only after the transaction has settled.
    """
    async def transaction():
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                result = await operation(db)
            except BaseException:
                await db.rollback()
                raise
            else:
                await db.commit()
                return result

    return await NovelBilling._drain(transaction())


async def _fetch_group(db, username, group_id):
    async with db.execute(
        "SELECT * FROM discuss_groups WHERE id=? AND username=?", (group_id, username)
    ) as cursor:
        row = await cursor.fetchone()
    return _decode_group(row) if row is not None else None


async def _fetch_message(db, username, message_id):
    async with db.execute(
        "SELECT * FROM discuss_messages WHERE id=? AND username=?", (message_id, username)
    ) as cursor:
        row = await cursor.fetchone()
    return _decode_message(row) if row is not None else None


async def _fetch_messages(db, username, group_id, *, after=0, limit=200, marker=None,
                          only_unread=False):
    sql = "SELECT * FROM discuss_messages WHERE group_id=? AND username=? AND id>?"
    params = [group_id, username, int(after)]
    if only_unread:
        sql += " AND sender='user' AND kind='user' AND consumed_by IS NULL"
    elif marker is not None:
        sql += " AND sender='user' AND kind='user' AND consumed_by=?"
        params.append(marker)
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(int(limit))
    async with db.execute(sql, params) as cursor:
        rows = await cursor.fetchall()
    return [_decode_message(row) for row in rows]


async def _count_unread(db, username, group_id):
    async with db.execute(
        "SELECT COUNT(*) FROM discuss_messages WHERE group_id=? AND username=? "
        "AND sender='user' AND kind='user' AND consumed_by IS NULL",
        (group_id, username),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0])


def _group_update(fields):
    """Build the whitelisted UPDATE assignment list for a group row."""
    fields = dict(fields)
    unknown = set(fields) - _GROUP_UPDATE_FIELDS
    if unknown:
        raise ValueError(f"不能更新讨论群字段：{sorted(unknown)[0]}")
    if "status" in fields and fields["status"] not in ("planning", "running"):
        # A group without a live run never keeps a worker token.
        fields["run_token"] = None
    now = utc_now()
    values = list(fields.values()) + [now]
    assignments = "".join(f"{name}=?, " for name in fields) + "updated_at=?"
    return assignments, values


async def create_group_on_connection(db, username, *, group_id, request, materials,
                                     budget_strawberries, max_rounds, config, created_day):
    """Insert the planning row on a caller-owned write transaction."""
    now = utc_now()
    await db.execute(
        """INSERT INTO discuss_groups
           (id, username, title, request, materials, status, round, max_rounds,
            plan_json, plan_revision, config_json, budget_strawberries,
            spent_strawberries, reserved_strawberries, output_version,
            run_token, created_day, created_at, updated_at)
           VALUES (?,?,'',?,?,'planning',0,?,'{}',0,?,?,0,0,0,NULL,?,?,?)""",
        (group_id, username, request, materials or "", max_rounds,
         _json(config or {}), budget_strawberries, created_day, now, now),
    )


async def create_group(username, *, group_id, request, materials,
                       budget_strawberries, max_rounds, config, created_day):
    async def operation(db):
        await create_group_on_connection(
            db, username, group_id=group_id, request=request, materials=materials,
            budget_strawberries=budget_strawberries, max_rounds=max_rounds,
            config=config, created_day=created_day,
        )
    await run_write(operation)


async def get_group_on_connection(db, username, group_id):
    """Read one group on a caller-owned connection."""
    return await _fetch_group(db, username, group_id)


async def get_group(username, group_id):
    async with get_db() as db:
        return await get_group_on_connection(db, username, group_id)


async def list_groups(username, limit=50):
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM discuss_groups WHERE username=? "
            "ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (username, max(0, int(limit))),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_decode_group(row) for row in rows]


async def update_group_on_connection(db, username, group_id, **fields):
    """Update a group row on a caller-owned write transaction."""
    assignments, values = _group_update(fields)
    cursor = await db.execute(
        f"UPDATE discuss_groups SET {assignments} WHERE id=? AND username=?",
        (*values, group_id, username),
    )
    return cursor.rowcount > 0


async def update_group(username, group_id, **fields):
    _group_update(fields)

    async def operation(db):
        return await update_group_on_connection(db, username, group_id, **fields)

    return await run_write(operation)


async def delete_group(username, group_id):
    async def operation(db):
        async with db.execute(
            "SELECT COALESCE(SUM(strawberries_reserved),0) AS amount FROM discuss_steps "
            "WHERE group_id=? AND username=? AND billing_status='reserved'",
            (group_id, username),
        ) as cursor:
            row = await cursor.fetchone()
        reserved = int(row["amount"] or 0)
        if reserved > 0:
            # Refund an in-flight reservation before its step row is deleted.
            # Only rows still marked reserved are counted; settled or refunded
            # rows were already accounted for and must not be refunded twice.
            await db.execute(
                "UPDATE users SET strawberry_balance=strawberry_balance+? WHERE username=?",
                (reserved, username),
            )
        for table in ("discuss_outputs", "discuss_sources", "discuss_steps", "discuss_messages"):
            await db.execute(
                f"DELETE FROM {table} WHERE group_id=? AND username=?", (group_id, username)
            )
        cursor = await db.execute(
            "DELETE FROM discuss_groups WHERE id=? AND username=?", (group_id, username)
        )
        return cursor.rowcount > 0

    return await run_write(operation)


async def count_created_today(username, day):
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM discuss_groups WHERE username=? AND created_day=?",
            (username, day),
        ) as cursor:
            row = await cursor.fetchone()
    return int(row[0])


async def has_active_group(username, exclude_group_id=None):
    sql = "SELECT 1 FROM discuss_groups WHERE username=? AND status IN ('planning','running')"
    params = [username]
    if exclude_group_id is not None:
        sql += " AND id<>?"
        params.append(exclude_group_id)
    async with get_db() as db:
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchone() is not None


async def post_user_note(username, group_id, text, round):
    async def operation(db):
        group = await _fetch_group(db, username, group_id)
        if group is None:
            return None
        if group["status"] in ("closed", "failed"):
            raise ValueError("closed")
        if await _count_unread(db, username, group_id) >= 5:
            raise ValueError("too_many")
        cursor = await db.execute(
            """INSERT INTO discuss_messages
               (group_id, username, round, sender, kind, content, payload_json,
                step_key, consumed_by, created_at)
               VALUES (?,?,?,'user','user',?,'{}',NULL,NULL,?)""",
            (group_id, username, int(round), text, utc_now()),
        )
        return await _fetch_message(db, username, cursor.lastrowid)

    return await run_write(operation)


async def list_messages(username, group_id, after=0, limit=200):
    async with get_db() as db:
        return await _fetch_messages(db, username, group_id, after=after, limit=limit)


async def unread_notes(username, group_id):
    async with get_db() as db:
        return await _fetch_messages(db, username, group_id, only_unread=True)


async def notes_for(username, group_id, marker):
    async with get_db() as db:
        return await _fetch_messages(db, username, group_id, marker=marker)


async def claim_notes(store, step_key):
    """Claim every unread note for this step inside the guarded transaction."""
    async def operation(db):
        await db.execute(
            """UPDATE discuss_messages SET consumed_by=?
               WHERE group_id=? AND username=? AND sender='user' AND kind='user'
                 AND consumed_by IS NULL""",
            (str(step_key), store.group_id, store.username),
        )
        return await _fetch_messages(db, store.username, store.group_id, marker=str(step_key))

    return await store.transaction(operation)


async def consume_notes_start(db, username, group_id):
    """Mark the pre-start notes on a caller-owned BEGIN IMMEDIATE connection."""
    await db.execute(
        """UPDATE discuss_messages SET consumed_by='start'
           WHERE group_id=? AND username=? AND sender='user' AND kind='user'
             AND consumed_by IS NULL""",
        (group_id, username),
    )


async def _register_source(db, username, group_id, url, title, site_name):
    key = url_key(url)
    async with db.execute(
        "SELECT sid FROM discuss_sources WHERE group_id=? AND username=? AND url_key=?",
        (group_id, username, key),
    ) as cursor:
        existing = await cursor.fetchone()
    if existing is not None:
        return int(existing["sid"])
    async with db.execute(
        "SELECT COALESCE(MAX(sid),0)+1 FROM discuss_sources WHERE group_id=? AND username=?",
        (group_id, username),
    ) as cursor:
        sid = int((await cursor.fetchone())[0])
    await db.execute(
        """INSERT INTO discuss_sources
           (group_id, username, sid, url, url_key, title, site_name, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (group_id, username, sid, url, key, title or "", site_name or "", utc_now()),
    )
    return sid


async def register_source(store, source):
    """Register one search source in a guarded transaction and return its sid."""
    async def operation(db):
        return await _register_source(
            db, store.username, store.group_id, source["url"],
            source.get("title") or "", source.get("site_name") or "",
        )

    return await store.transaction(operation)


async def register_sources(store, sources):
    """Register an ordered batch of sources atomically; return their sids."""
    async def operation(db):
        return [
            await _register_source(
                db, store.username, store.group_id, source["url"],
                source.get("title") or "", source.get("site_name") or "",
            )
            for source in sources
        ]

    return await store.transaction(operation)


async def list_sources(username, group_id):
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM discuss_sources WHERE group_id=? AND username=? ORDER BY sid ASC",
            (group_id, username),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_decode_source(row) for row in rows]


async def get_output(username, group_id, version=None):
    async with get_db() as db:
        if version is None:
            async with db.execute(
                "SELECT MAX(version) FROM discuss_outputs WHERE group_id=? AND username=?",
                (group_id, username),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None or row[0] is None:
                return None
            version = int(row[0])
        async with db.execute(
            "SELECT * FROM discuss_outputs WHERE group_id=? AND username=? AND version=?",
            (group_id, username, int(version)),
        ) as cursor:
            row = await cursor.fetchone()
    return _decode_output(row) if row is not None else None


async def latest_output(username, group_id):
    return await get_output(username, group_id)


async def output_summary(username, group_id):
    output = await latest_output(username, group_id)
    if output is None:
        return None
    content = output.get("content") or ""
    return {
        "version": output["version"],
        "round": output["round"],
        "passed": bool(output["passed"]),
        "verdict": output["verdict"],
        "words": len(content.strip()),
    }


class DiscussStepStore:
    """StepStore implementation for one discussion group token."""

    def __init__(self, username, group_id, run_token, *, max_total_tokens=2**63 - 1):
        self.username = username
        self.group_id = group_id
        self.run_token = run_token
        # LLMRouter only enables atomic step settlement when this is present.
        self.novel_id = group_id
        self.budget_lock = asyncio.Lock()
        self.reserved_tokens = 0
        self.max_total_tokens = max_total_tokens
        self.usage = []
        self.manifest = {"experiment": "discuss", "status": "running", "failed_step": None}

    @property
    def total_tokens(self):
        return sum(row.get("input_tokens", 0) + row.get("output_tokens", 0) for row in self.usage)

    @property
    def used_tokens(self):
        return self.total_tokens

    async def initialize(self):
        """Load persisted usage for resumed runs without recording it twice."""
        async with get_db() as db:
            async with db.execute(
                "SELECT step_key, role, model, input_tokens, output_tokens, cached_tokens, attempts "
                "FROM discuss_steps WHERE group_id=? AND username=?",
                (self.group_id, self.username),
            ) as cursor:
                self.usage = [{key: value or 0 for key, value in dict(row).items()}
                              for row in await cursor.fetchall()]
        return self

    async def is_current(self, db=None):
        if db is None:
            async with get_db() as connection:
                return await self.is_current(connection)
        async with db.execute(
            """SELECT 1 FROM discuss_groups g JOIN users u ON u.username=g.username
               WHERE g.id=? AND g.username=? AND g.run_token=?""",
            (self.group_id, self.username, self.run_token),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def transaction(self, operation):
        """Run a guarded write transaction protected from caller cancellation.

        ``operation(db)`` must only await database work.  The run-token and
        account guard is checked before the operation, and the whole transaction
        (including commit/rollback and connection close) is shielded.
        """
        async def guarded(db):
            if not await self.is_current(db):
                raise RunNoLongerActive()
            return await operation(db)

        return await run_write(guarded)

    async def read_step(self, step_key):
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM discuss_steps WHERE group_id=? AND username=? AND step_key=?",
                (self.group_id, self.username, str(step_key)),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        value = dict(row)
        return {"step_key": value["step_key"], "role": value["role"], "model": value["model"],
                "status": value["status"], "raw_response": value["raw_response"],
                "result": json.loads(value["result_json"]) if value["result_json"] else None,
                "errors": json.loads(value["errors_json"]) if value["errors_json"] else [],
                "request_digest": value["request_digest"], "attempts": value["attempts"],
                "duration_ms": value["duration_ms"], "stop_reason": value["stop_reason"],
                "usage": {key: value[key] or 0 for key in
                          ("input_tokens", "output_tokens", "cached_tokens")}}

    @staticmethod
    async def write_step_on_connection(db, username, group_id, step_key, record):
        """Write on the caller's guarded transaction, including billing settle."""
        digest = record.get("request_digest")
        if digest is None and "messages" in record:
            digest = hashlib.sha256(_json(record["messages"]).encode()).hexdigest()
        usage = record.get("usage", {})
        now = utc_now()
        await db.execute(
            """INSERT INTO discuss_steps
               (group_id, username, step_key, role, model, status, request_digest,
                raw_response, result_json, errors_json, stop_reason, attempts,
                input_tokens, output_tokens, cached_tokens, duration_ms,
                created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(group_id,step_key) DO UPDATE SET
                 role=COALESCE(excluded.role,discuss_steps.role), model=excluded.model,
                 status=excluded.status, request_digest=excluded.request_digest,
                 raw_response=excluded.raw_response, result_json=excluded.result_json,
                 errors_json=excluded.errors_json, stop_reason=excluded.stop_reason,
                 attempts=excluded.attempts, input_tokens=excluded.input_tokens,
                 output_tokens=excluded.output_tokens, cached_tokens=excluded.cached_tokens,
                 duration_ms=excluded.duration_ms, updated_at=excluded.updated_at""",
            (group_id, username, str(step_key), record.get("role"), record.get("model"),
             record.get("status", "ok"), digest, record.get("raw_response"),
             _json(record.get("result")), _json(record.get("errors", [])),
             record.get("stop_reason"), record.get("attempts", 0),
             usage.get("input_tokens", 0), usage.get("output_tokens", 0),
             usage.get("cached_tokens", 0), round(record.get("duration_ms", 0)), now, now),
        )

    async def write_step(self, step_key, record):
        # The DB stores a digest rather than the prompts, including repairs.
        async def operation(db):
            await self.write_step_on_connection(
                db, self.username, self.group_id, step_key, record
            )
            return True

        return await self.transaction(operation)

    async def append_usage(self, record):
        # Attempt usage is aggregated in the step row; the completed record
        # later replaces these counters with the same aggregate values.
        async def operation(db):
            now = utc_now()
            await db.execute(
                """INSERT INTO discuss_steps
                   (group_id,username,step_key,role,model,status,attempts,
                    input_tokens,output_tokens,cached_tokens,duration_ms,created_at,updated_at)
                   VALUES(?,?,?,?,?,'interrupted',1,?,?,?,?,?,?)
                   ON CONFLICT(group_id,step_key) DO UPDATE SET
                    attempts=COALESCE(discuss_steps.attempts,0)+1,
                    input_tokens=COALESCE(discuss_steps.input_tokens,0)+excluded.input_tokens,
                    output_tokens=COALESCE(discuss_steps.output_tokens,0)+excluded.output_tokens,
                    cached_tokens=COALESCE(discuss_steps.cached_tokens,0)+excluded.cached_tokens,
                    duration_ms=COALESCE(discuss_steps.duration_ms,0)+excluded.duration_ms,
                    updated_at=excluded.updated_at""",
                (self.group_id, self.username, str(record["step_key"]), record.get("role"),
                 record.get("model"), record.get("input_tokens", 0),
                 record.get("output_tokens", 0), record.get("cached_tokens", 0),
                 round(record.get("duration_ms", 0)), now, now),
            )

        await self.transaction(operation)
        self.usage.append(record)
        return True

    async def mark_usage(self, record, *, ok):
        record["ok"] = bool(ok)

    async def set_status(self, status, **fields):
        # Engine failure metadata belongs to the in-memory manifest; the runner
        # maps it to the persistent group state machine.
        self.manifest.update(fields, status=status, updated_at=utc_now())

    async def read_json(self, path):
        record = await self.read_step(path)
        if record is None:
            raise FileNotFoundError(path)
        return record if "raw_response" in record and record.get("role") != "artifact" else record["result"]

    async def write_json(self, path, value):
        if isinstance(value, dict) and "status" in value and "result" in value:
            return await self.write_step(path, value)
        return await self.write_step(path, {"role": "artifact", "result": value, "status": "ok"})

    async def write_text(self, path, value):
        return await self.write_json(path, value)

    async def post_message(self, round, sender, kind, content, payload=None, step_key=None):
        async def operation(db):
            cursor = await db.execute(
                """INSERT OR IGNORE INTO discuss_messages
                   (group_id, username, round, sender, kind, content, payload_json,
                    step_key, consumed_by, created_at)
                   VALUES (?,?,?,?,?,?,?,?,NULL,?)""",
                (self.group_id, self.username, int(round), sender, kind, content,
                 _json(payload or {}), None if step_key is None else str(step_key), utc_now()),
            )
            return cursor.rowcount > 0

        return await self.transaction(operation)

    async def update_group(self, **fields):
        _group_update(fields)

        async def operation(db):
            return await update_group_on_connection(
                db, self.username, self.group_id, **fields)

        return await self.transaction(operation)

    async def save_output(self, round, step_key, content):
        async def operation(db):
            async with db.execute(
                "SELECT version FROM discuss_outputs WHERE group_id=? AND username=? AND step_key=?",
                (self.group_id, self.username, str(step_key)),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing is not None:
                version = int(existing["version"])
            else:
                async with db.execute(
                    "SELECT COUNT(*) FROM discuss_outputs WHERE group_id=? AND username=?",
                    (self.group_id, self.username),
                ) as cursor:
                    count = int((await cursor.fetchone())[0])
                version = count + 1
                await db.execute(
                    """INSERT INTO discuss_outputs
                       (group_id, username, version, round, step_key, content, passed, created_at)
                       VALUES (?,?,?,?,?,?,0,?)""",
                    (self.group_id, self.username, version, int(round), str(step_key),
                     content, utc_now()),
                )
            await db.execute(
                "UPDATE discuss_groups SET output_version=MAX(output_version,?),updated_at=? "
                "WHERE id=? AND username=?",
                (version, utc_now(), self.group_id, self.username),
            )
            return version

        return await self.transaction(operation)

    async def save_verdict(self, version, verdict, passed):
        async def operation(db):
            cursor = await db.execute(
                "UPDATE discuss_outputs SET verdict_json=?,passed=? "
                "WHERE group_id=? AND username=? AND version=?",
                (_json(verdict), 1 if passed else 0, self.group_id, self.username, int(version)),
            )
            return cursor.rowcount > 0

        return await self.transaction(operation)
