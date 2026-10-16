"""SQLite storage adapter for the existing novel engine.

Each background write checks both the account and the current run token while
holding SQLite's write lock. An old or cancelled worker therefore cannot
recreate rows after an account or a book is deleted.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json

import aiosqlite

from .run_store import utc_now


NOVEL_TABLES_DDL = (
    """CREATE TABLE IF NOT EXISTS novels (
        id TEXT PRIMARY KEY, username TEXT NOT NULL, title TEXT,
        seed_idea TEXT NOT NULL, status TEXT NOT NULL, pause_reason TEXT,
        config_json TEXT NOT NULL, compass_json TEXT,
        bible_version INTEGER NOT NULL DEFAULT 0,
        chapters_done INTEGER NOT NULL DEFAULT 0,
        words_done INTEGER NOT NULL DEFAULT 0,
        budget_strawberries INTEGER NOT NULL,
        spent_strawberries INTEGER NOT NULL DEFAULT 0,
        reserved_strawberries INTEGER NOT NULL DEFAULT 0,
        run_token TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS novel_bible_versions (
        novel_id TEXT NOT NULL, username TEXT NOT NULL, version INTEGER NOT NULL,
        bible_json TEXT NOT NULL, source TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(novel_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS novel_chapters (
        novel_id TEXT NOT NULL, username TEXT NOT NULL, chapter INTEGER NOT NULL,
        status TEXT NOT NULL, title TEXT, body TEXT, flags_json TEXT,
        meeting_json TEXT, review_json TEXT, archive_json TEXT, ending_status TEXT,
        edited_by_user INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(novel_id, chapter)
    )""",
    """CREATE TABLE IF NOT EXISTS novel_steps (
        novel_id TEXT NOT NULL, username TEXT NOT NULL, step_key TEXT NOT NULL,
        role TEXT, model TEXT, status TEXT NOT NULL, request_digest TEXT,
        raw_response TEXT, result_json TEXT, errors_json TEXT, stop_reason TEXT,
        attempts INTEGER, input_tokens INTEGER, output_tokens INTEGER,
        cached_tokens INTEGER, duration_ms INTEGER,
        strawberries_reserved INTEGER NOT NULL DEFAULT 0,
        strawberries_charged INTEGER NOT NULL DEFAULT 0,
        billing_status TEXT NOT NULL DEFAULT 'free',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(novel_id, step_key)
    )""",
    """CREATE TABLE IF NOT EXISTS novel_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, novel_id TEXT NOT NULL,
        username TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL,
        delivered_chapter INTEGER, response_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_novels_novel_id ON novels(id)",
    "CREATE INDEX IF NOT EXISTS idx_novels_username_status ON novels(username, status)",
    "CREATE INDEX IF NOT EXISTS idx_novel_bible_novel_id ON novel_bible_versions(novel_id)",
    "CREATE INDEX IF NOT EXISTS idx_novel_chapters_novel_id ON novel_chapters(novel_id)",
    "CREATE INDEX IF NOT EXISTS idx_novel_steps_novel_id ON novel_steps(novel_id)",
    "CREATE INDEX IF NOT EXISTS idx_novel_notes_novel_id ON novel_notes(novel_id)",
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@asynccontextmanager
async def get_db():
    """Resolve the configured database at call time, including test isolation."""
    import database
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        yield db


connect = get_db


class DbStepStore:
    def __init__(self, username, novel_id, run_token, *, max_total_tokens=3_000_000):
        self.username, self.novel_id, self.run_token = username, novel_id, run_token
        self.budget_lock = asyncio.Lock()
        self.reserved_tokens = 0
        self.max_total_tokens = max_total_tokens
        self.usage = []
        self.manifest = {"experiment": "P1", "status": "running", "failed_step": None}

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
                "FROM novel_steps WHERE novel_id=? AND username=?",
                (self.novel_id, self.username),
            ) as cursor:
                self.usage = [{key: value or 0 for key, value in dict(row).items()}
                              for row in await cursor.fetchall()]
        return self

    async def is_current(self, db=None):
        if db is None:
            async with get_db() as connection:
                return await self.is_current(connection)
        async with db.execute(
            """SELECT 1 FROM novels n JOIN users u ON u.username=n.username
               WHERE n.id=? AND n.username=? AND n.run_token=?""",
            (self.novel_id, self.username, self.run_token),
        ) as cursor:
            return await cursor.fetchone() is not None

    @asynccontextmanager
    async def transaction(self):
        """Yield a guarded write transaction, or None for an obsolete worker."""
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            if not await self.is_current(db):
                await db.rollback()
                yield None
                return
            try:
                yield db
            except BaseException:
                await db.rollback()
                raise
            else:
                await db.commit()

    async def read_step(self, step_key):
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM novel_steps WHERE novel_id=? AND username=? AND step_key=?",
                (self.novel_id, self.username, str(step_key)),
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
                "usage": {key: value[key] or 0 for key in ("input_tokens", "output_tokens", "cached_tokens")}}

    @staticmethod
    async def write_step_on_connection(db, username, novel_id, step_key, record):
        """Write on the caller's guarded transaction, including billing settle."""
        digest = record.get("request_digest")
        if digest is None and "messages" in record:
            digest = hashlib.sha256(_json(record["messages"]).encode()).hexdigest()
        usage = record.get("usage", {})
        await db.execute(
            """INSERT INTO novel_steps
               (novel_id, username, step_key, role, model, status, request_digest,
                raw_response, result_json, errors_json, stop_reason, attempts,
                input_tokens, output_tokens, cached_tokens, duration_ms)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(novel_id,step_key) DO UPDATE SET
                 role=COALESCE(excluded.role,novel_steps.role), model=excluded.model, status=excluded.status,
                 request_digest=excluded.request_digest, raw_response=excluded.raw_response,
                 result_json=excluded.result_json, errors_json=excluded.errors_json,
                 stop_reason=excluded.stop_reason, attempts=excluded.attempts,
                 input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                 cached_tokens=excluded.cached_tokens, duration_ms=excluded.duration_ms,
                 updated_at=CURRENT_TIMESTAMP""",
            (novel_id, username, str(step_key), record.get("role"), record.get("model"),
             record.get("status", "ok"), digest, record.get("raw_response"),
             _json(record.get("result")), _json(record.get("errors", [])), record.get("stop_reason"),
             record.get("attempts", 0), usage.get("input_tokens", 0), usage.get("output_tokens", 0),
             usage.get("cached_tokens", 0), round(record.get("duration_ms", 0))),
        )

    async def write_step(self, step_key, record):
        # The DB stores a digest rather than the prompts, including repairs.
        async with self.transaction() as db:
            if db is None:
                return False
            await self.write_step_on_connection(db, self.username, self.novel_id, step_key, record)
        return True

    async def append_usage(self, record):
        # Attempt usage is aggregated in the schema's step row. The completed
        # record later replaces these counters with the same aggregate values.
        async with self.transaction() as db:
            if db is None:
                return False
            await db.execute(
                """INSERT INTO novel_steps
                   (novel_id,username,step_key,role,model,status,attempts,
                    input_tokens,output_tokens,cached_tokens,duration_ms)
                   VALUES(?,?,?,?,?,'interrupted',1,?,?,?,?)
                   ON CONFLICT(novel_id,step_key) DO UPDATE SET
                    attempts=COALESCE(novel_steps.attempts,0)+1,
                    input_tokens=COALESCE(novel_steps.input_tokens,0)+excluded.input_tokens,
                    output_tokens=COALESCE(novel_steps.output_tokens,0)+excluded.output_tokens,
                    cached_tokens=COALESCE(novel_steps.cached_tokens,0)+excluded.cached_tokens,
                    duration_ms=COALESCE(novel_steps.duration_ms,0)+excluded.duration_ms,
                    updated_at=CURRENT_TIMESTAMP""",
                (self.novel_id, self.username, str(record["step_key"]), record.get("role"),
                 record.get("model"), record.get("input_tokens", 0), record.get("output_tokens", 0),
                 record.get("cached_tokens", 0), round(record.get("duration_ms", 0))),
            )
        self.usage.append(record)
        return True

    async def mark_usage(self, record, *, ok):
        record["ok"] = bool(ok)

    async def set_status(self, status, **fields):
        # Engine failure metadata belongs to the in-memory run manifest; the
        # runner maps it to its own, more specific persistent state machine.
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

    async def commit_setup(self, compass, bible):
        async with self.transaction() as db:
            if db is None:
                return False
            await db.execute(
                "INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)",
                (self.novel_id, self.username, bible["version"], _json(bible), "setup"),
            )
            await db.execute(
                """UPDATE novels SET title=?, compass_json=?, bible_version=?,
                   status='awaiting_setup',pause_reason=NULL,run_token=NULL,
                   updated_at=CURRENT_TIMESTAMP WHERE id=? AND username=?""",
                (compass["title"], _json(compass), bible["version"], self.novel_id, self.username),
            )
        return True

    async def save_plan(self, chapter, meeting):
        async with self.transaction() as db:
            if db is None:
                return False
            await db.execute(
                """INSERT INTO novel_chapters(novel_id,username,chapter,status,title,meeting_json)
                   VALUES(?,?,?,'awaiting_plan_approval',?,?)
                   ON CONFLICT(novel_id,chapter) DO UPDATE SET status=excluded.status,
                    title=excluded.title,meeting_json=excluded.meeting_json,updated_at=CURRENT_TIMESTAMP""",
                (self.novel_id, self.username, chapter,
                 meeting["decision"]["beat_sheet"]["title"], _json(meeting)),
            )
            await db.execute("UPDATE novels SET status='awaiting_plan',run_token=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                             (self.novel_id,))
        return True

    async def commit_chapter(self, chapter, meeting, product, *, status="running", pause_reason=None):
        """Atomically publish the accepted chapter, next bible and counters."""
        from .writing import compact_length
        bible = deepcopy(product["bible"])
        decision = meeting["decision"]
        async with self.transaction() as db:
            if db is None:
                return False
            async with db.execute("SELECT bible_version,chapters_done FROM novels WHERE id=?", (self.novel_id,)) as cursor:
                current = await cursor.fetchone()
            if chapter != current["chapters_done"] + 1:
                return False
            bible["version"] = current["bible_version"] + 1
            await db.execute(
                """INSERT INTO novel_chapters
                   (novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json,ending_status)
                   VALUES(?,?,?,'done',?,?,?,?,?,?,?)
                   ON CONFLICT(novel_id,chapter) DO UPDATE SET status='done',title=excluded.title,
                    body=excluded.body,flags_json=excluded.flags_json,meeting_json=excluded.meeting_json,
                    review_json=excluded.review_json,archive_json=excluded.archive_json,
                    ending_status=excluded.ending_status,updated_at=CURRENT_TIMESTAMP""",
                (self.novel_id, self.username, chapter, decision["beat_sheet"]["title"], product["body"],
                 _json(product.get("flags", [])), _json(meeting), _json(product.get("reviews", [])),
                 _json(product.get("archive", {})), decision["ending_status"]),
            )
            await db.execute(
                "INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)",
                (self.novel_id, self.username, bible["version"], _json(bible), f"archive:{chapter}"),
            )
            await db.execute(
                """UPDATE novels SET bible_version=?,chapters_done=?,words_done=words_done+?,
                   status=?,pause_reason=?,run_token=CASE WHEN ?='running' THEN run_token ELSE NULL END,
                   updated_at=CURRENT_TIMESTAMP WHERE id=? AND username=?""",
                (bible["version"], chapter, compact_length(product["body"]), status, pause_reason,
                 status, self.novel_id, self.username),
            )
            responses = decision.get("user_note_responses", [])
            for response in responses:
                note_id = response.get("note_id", response.get("id"))
                if isinstance(note_id, str) and note_id.startswith("N"):
                    note_id = note_id[1:]
                await db.execute(
                    """UPDATE novel_notes SET status='delivered',delivered_chapter=?,response_json=?
                       WHERE id=? AND novel_id=? AND username=? AND status='pending'""",
                    (chapter, _json(response), note_id, self.novel_id, self.username),
                )
        return True
