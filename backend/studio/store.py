"""短片工作室数据库；所有状态更新使用带状态条件的 CAS。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import sqlite3
import uuid

import aiosqlite
from fastapi import HTTPException

from . import pricing
from .config import get_settings


# 金额以八位十进制文本存储，额度检查使用 Decimal，不依赖浮点 SUM。
STUDIO_TABLES_DDL = (
    """CREATE TABLE IF NOT EXISTS studio_projects (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
        aspect TEXT NOT NULL CHECK(aspect IN ('16:9','9:16')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0, brain_provider TEXT NOT NULL DEFAULT 'claude',
        review_provider TEXT NOT NULL DEFAULT 'qwen',
        source_kind TEXT CHECK(source_kind IN ('novel','upload','paste','exchange')),
        source_ref TEXT, snapshot_no INTEGER NOT NULL DEFAULT 0,
        episode_seconds_min INTEGER NOT NULL DEFAULT 180, episode_seconds_max INTEGER NOT NULL DEFAULT 240,
        plan_revision INTEGER NOT NULL DEFAULT 0, plan_approved_revision INTEGER, breakdown_id TEXT,
        setup_json TEXT, setup_confirmed_at TEXT, style_json TEXT, style_group_id TEXT,
        UNIQUE(id, owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_assets (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('image','video','audio')),
        source TEXT NOT NULL CHECK(source IN ('upload','generated')),
        rel_path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
        width INTEGER, height INTEGER, duration_s REAL, fps REAL, has_audio INTEGER,
        meta_json TEXT NOT NULL DEFAULT '{}', archived INTEGER NOT NULL DEFAULT 0,
        item_id TEXT, version_no INTEGER, role TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_quotes (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL,
        items_json TEXT NOT NULL, total_min_cny TEXT NOT NULL, total_max_cny TEXT NOT NULL,
        params_hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','confirmed')),
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL, confirmed_at TEXT,
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_jobs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'i2v', provider TEXT NOT NULL CHECK(provider IN ('wan','seedance')),
        model TEXT NOT NULL, params_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
        quote_id TEXT NOT NULL, quote_item_id TEXT NOT NULL, status TEXT NOT NULL
            CHECK(status IN ('queued','submitting','submitted','running','succeeded','downloaded',
                             'rejected','uncertain','failed','filtered','expired','cancelled','released')),
        task_id TEXT, run_token TEXT, est_min_cny TEXT NOT NULL, est_max_cny TEXT NOT NULL,
        reserved_cny TEXT NOT NULL DEFAULT '0.00000000', actual_cny TEXT,
        usage_json TEXT, result_host TEXT, result_url TEXT, result_asset_id TEXT,
        error_code TEXT, error_message TEXT, needs_recheck INTEGER NOT NULL DEFAULT 0,
        poll_requested INTEGER NOT NULL DEFAULT 0, next_poll_at TEXT,
        submitted_at TEXT, finished_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        confirmed_day TEXT NOT NULL,
        task TEXT, result_json TEXT, warnings_json TEXT, currency TEXT NOT NULL DEFAULT 'CNY',
        input_chars INTEGER, group_id TEXT, brain_provider TEXT, reserved_amount TEXT, actual_amount TEXT,
        confirmed_month TEXT, latency_s REAL, stop_reason TEXT, repaired INTEGER NOT NULL DEFAULT 0,
        attempt INTEGER NOT NULL DEFAULT 1, parent_job_id TEXT,
        media_provider TEXT, item_id TEXT,
        UNIQUE(quote_id,quote_item_id),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner),
        FOREIGN KEY(quote_id) REFERENCES studio_quotes(id),
        FOREIGN KEY(result_asset_id) REFERENCES studio_assets(id)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_items (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL, bible_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('character','location','prop')), name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','skipped')),
        spec_json TEXT NOT NULL DEFAULT '{}', approved_asset_id TEXT, voice_asset_id TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,bible_id),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
        project_id TEXT NOT NULL, job_id TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        summary TEXT NOT NULL CHECK(length(summary) <= 200),
        message_id INTEGER, conversation_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS studio_snapshots (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL,
        no INTEGER NOT NULL CHECK(no >= 1),
        kind TEXT NOT NULL CHECK(kind IN ('novel','upload','paste','exchange')),
        ref_id TEXT, title TEXT NOT NULL, bible_version INTEGER, chapters INTEGER NOT NULL,
        chars INTEGER NOT NULL, manifest_sha256 TEXT NOT NULL, rel_dir TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(project_id,no),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_breakdowns (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL, snapshot_no INTEGER NOT NULL,
        provider TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft','running','partial','done','cancelled')),
        settings_json TEXT NOT NULL DEFAULT '{}', import_json TEXT NOT NULL DEFAULT '{}', synopsis_json TEXT,
        quote_id TEXT, outdated INTEGER NOT NULL DEFAULT 0, superseded_by TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_chunks (
        id TEXT PRIMARY KEY, breakdown_id TEXT NOT NULL, project_id TEXT NOT NULL, owner TEXT NOT NULL,
        no INTEGER NOT NULL, task TEXT NOT NULL CHECK(task IN ('novel_complete','text_map','synopsis','episode_plan')),
        source_json TEXT NOT NULL DEFAULT '{}', depends_on_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL CHECK(status IN ('blocked','queued','running','succeeded','failed','uncertain',
            'rejected','invalid_output','released','cancelled')), job_id TEXT, provider TEXT NOT NULL,
        result_json TEXT, warnings_json TEXT NOT NULL DEFAULT '[]', created_at TEXT, updated_at TEXT,
        UNIQUE(breakdown_id,no), FOREIGN KEY(breakdown_id) REFERENCES studio_breakdowns(id),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_units (
        breakdown_id TEXT NOT NULL, seq INTEGER NOT NULL, label TEXT NOT NULL, chapter INTEGER NOT NULL,
        scene_index INTEGER NOT NULL, location TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
        characters_json TEXT NOT NULL DEFAULT '[]', est_seconds INTEGER, change TEXT NOT NULL DEFAULT '',
        start INTEGER, end INTEGER, PRIMARY KEY(breakdown_id,seq),
        FOREIGN KEY(breakdown_id) REFERENCES studio_breakdowns(id)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_bible (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL, breakdown_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('character','location','prop')), name TEXT NOT NULL,
        aliases_json TEXT NOT NULL DEFAULT '[]', role TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
        appearance TEXT NOT NULL DEFAULT '', appearance_source TEXT NOT NULL DEFAULT 'none'
            CHECK(appearance_source IN ('workshop','excerpt','author','none')),
        excerpt TEXT NOT NULL DEFAULT '', needs_author INTEGER NOT NULL DEFAULT 0, first_unit INTEGER,
        episodes_json TEXT NOT NULL DEFAULT '[]', ref_id TEXT, merged_into TEXT, archived INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL, FOREIGN KEY(breakdown_id) REFERENCES studio_breakdowns(id),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_episodes (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL, breakdown_id TEXT NOT NULL,
        no INTEGER NOT NULL, title TEXT NOT NULL, unit_from INTEGER NOT NULL, unit_to INTEGER NOT NULL,
        change TEXT NOT NULL DEFAULT '', hook TEXT NOT NULL DEFAULT '', target_min INTEGER, target_max INTEGER,
        notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
        FOREIGN KEY(breakdown_id) REFERENCES studio_breakdowns(id),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_plan_revisions (
        project_id TEXT NOT NULL, owner TEXT NOT NULL, revision INTEGER NOT NULL, plan_json TEXT NOT NULL,
        created_at TEXT NOT NULL, created_reason TEXT NOT NULL, PRIMARY KEY(project_id,revision),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner)
    )""",
    # WO3e 知识库：案例与按场景类型的节奏统计。不挂项目外键，删项目不删作者案例。
    """CREATE TABLE IF NOT EXISTS studio_exemplars (
        id TEXT PRIMARY KEY, owner TEXT, project_id TEXT, source TEXT,
        scene_type TEXT, kind TEXT CHECK(kind IN ('good','bad')), reason TEXT,
        shot_json TEXT, keyframe_asset_id TEXT, video_model TEXT, qc_json TEXT, cost_cny TEXT,
        tags_json TEXT, created_at TEXT, archived INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS studio_stats (
        owner TEXT, scene_type TEXT, episodes INTEGER, shots INTEGER,
        avg_shot_s REAL, shot_size_json TEXT, camera_json TEXT, updated_at TEXT,
        PRIMARY KEY(owner, scene_type)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_studio_exemplars_owner_scene ON studio_exemplars(owner,scene_type,kind,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_studio_breakdowns_project ON studio_breakdowns(owner,project_id,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_studio_chunks_breakdown ON studio_chunks(breakdown_id,no)",
    "CREATE INDEX IF NOT EXISTS idx_studio_chunks_job ON studio_chunks(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_bible_breakdown ON studio_bible(owner,breakdown_id,kind)",
    "CREATE INDEX IF NOT EXISTS idx_studio_episodes_breakdown ON studio_episodes(owner,breakdown_id,no)",
    "CREATE INDEX IF NOT EXISTS idx_studio_snapshots_owner_project ON studio_snapshots(owner,project_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_projects_owner_updated ON studio_projects(owner,updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_studio_assets_owner_project ON studio_assets(owner,project_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_assets_sha ON studio_assets(project_id,owner,sha256)",
    # idx_studio_assets_item 引用迁移才补的 item_id/role/version_no，见 _ADDED_COLUMN_INDEXES。
    "CREATE INDEX IF NOT EXISTS idx_studio_items_project ON studio_items(owner,project_id,bible_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_quotes_owner_project ON studio_quotes(owner,project_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_jobs_owner_project ON studio_jobs(owner,project_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_jobs_schedule ON studio_jobs(status,provider,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_studio_jobs_confirmed_day ON studio_jobs(confirmed_day)",
    "CREATE INDEX IF NOT EXISTS idx_studio_notices_username_id ON studio_notices(username,id)",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_studio_jobs_inflight_fingerprint
       ON studio_jobs(fingerprint)
       WHERE status IN ('queued','submitting','submitted','running','uncertain')""",
    """CREATE TABLE IF NOT EXISTS studio_notice_pending (
        job_id TEXT PRIMARY KEY, username TEXT NOT NULL, project_id TEXT NOT NULL,
        target TEXT NOT NULL, before_id INTEGER NOT NULL, content TEXT NOT NULL, summary TEXT NOT NULL
    )""",
    "CREATE TABLE IF NOT EXISTS studio_notice_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS studio_notice_historical (job_id TEXT PRIMARY KEY)",
    """CREATE INDEX IF NOT EXISTS idx_studio_jobs_notice_terminal ON studio_jobs(COALESCE(finished_at,updated_at),id)
       WHERE kind='i2v' AND status IN ('downloaded','failed','rejected','filtered','expired','uncertain')""",
)

_JSON_FIELDS = {"params_json": "params", "items_json": "items", "usage_json": "usage", "meta_json": "meta",
                "result_json": "output", "warnings_json": "warnings"}
_EXEMPLAR_JSON_FIELDS = {"shot_json": "shot", "qc_json": "qc", "tags_json": "tags"}
_STATS_JSON_FIELDS = {"shot_size_json": "shot_size", "camera_json": "camera"}
_MONEY_FIELDS = {"total_min_cny", "total_max_cny", "est_min_cny", "est_max_cny", "reserved_cny", "actual_cny"}
_JOB_UPDATE_FIELDS = {
    "status", "task_id", "run_token", "reserved_cny", "actual_cny", "usage_json", "result_host",
    "result_url", "result_asset_id", "error_code", "error_message", "needs_recheck", "poll_requested",
    "next_poll_at", "submitted_at", "finished_at", "updated_at",
}
# 定妆出图与声线的任务 kind；它们的结算口径与 i2v 不同（见 casting_jobs.transition）。
CASTING_JOB_KINDS = ("image", "tts")
# WO3e 交叉审核模型；off 表示不自动审核。
REVIEW_PROVIDERS = ("claude", "qwen", "deepseek", "off")
_TRANSITIONS = {
    "queued": {"submitting", "cancelled"},
    "submitting": {"submitted", "uncertain", "rejected", "failed"},
    "submitted": {"running", "succeeded", "uncertain", "failed", "filtered", "expired"},
    "running": {"succeeded", "uncertain", "failed", "filtered", "expired"},
    "uncertain": {"submitted", "running", "succeeded", "failed", "filtered", "expired", "released"},
    "succeeded": {"downloaded", "failed", "filtered", "expired"},
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: datetime | str) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


def _timestamp(now=None) -> str:
    return utcnow() if now is None else parse_time(now).isoformat()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _row(row) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for key, target in _JSON_FIELDS.items():
        if key in result:
            result[target] = json.loads(result[key]) if result[key] else None
    for key in _MONEY_FIELDS:
        if key in result and result[key] is not None:
            result[key] = float(pricing.money(result[key]))
    if result.get("kind") == "brain":
        result["provider"] = result["brain_provider"]
        if result.get("error_code") in {"invalid_output", "max_tokens"} and result["status"] == "failed":
            result["status"] = "invalid_output"
        result["repaired"] = bool(result.get("repaired"))
        result["warnings"] = result.get("warnings") or []
        result["cost"] = {"currency": result["currency"], "amount": (
            float(result["actual_amount"]) if result.get("actual_amount") is not None else None)}
        result["result"] = result.get("output")
    return result


# 只引用迁移补列（或迁移后才存在的表）的索引：database.init_db 先跑 STUDIO_TABLES_DDL，
# 旧库里 CREATE TABLE IF NOT EXISTS 不改旧表，索引留在 DDL 里会报 no such column。
# 这些索引必须在补列之后创建，所以由 migrate_schema 负责。
_ADDED_COLUMN_INDEXES = (
    ("studio_jobs", "CREATE INDEX IF NOT EXISTS idx_studio_brain_group ON studio_jobs(owner,project_id,group_id)"),
    ("studio_jobs", "CREATE INDEX IF NOT EXISTS idx_studio_brain_month ON studio_jobs(owner,currency,confirmed_month)"),
    ("studio_assets", "CREATE INDEX IF NOT EXISTS idx_studio_assets_item ON studio_assets(owner,item_id,role,version_no)"),
    ("studio_assets", "CREATE UNIQUE INDEX IF NOT EXISTS idx_studio_assets_item_version ON studio_assets(item_id,role,version_no) WHERE item_id IS NOT NULL"),
)


async def migrate_schema(db) -> None:
    """只补列：旧库 provider/status CHECK 保留，brain 使用新增的权威列。"""
    additions = {
        "studio_projects": {"brain_provider": "TEXT NOT NULL DEFAULT 'claude'",
                            "review_provider": "TEXT NOT NULL DEFAULT 'qwen'",
                            "source_kind": "TEXT CHECK(source_kind IN ('novel','upload','paste','exchange'))",
                            "source_ref": "TEXT", "snapshot_no": "INTEGER NOT NULL DEFAULT 0",
                            "episode_seconds_min": "INTEGER NOT NULL DEFAULT 180",
                            "episode_seconds_max": "INTEGER NOT NULL DEFAULT 240",
                            "plan_revision": "INTEGER NOT NULL DEFAULT 0", "plan_approved_revision": "INTEGER",
                            "breakdown_id": "TEXT", "setup_json": "TEXT", "setup_confirmed_at": "TEXT",
                            "style_json": "TEXT", "style_group_id": "TEXT"},
        "studio_assets": {"item_id": "TEXT", "version_no": "INTEGER", "role": "TEXT"},
        "studio_breakdowns": {"superseded_by": "TEXT"},
        "studio_jobs": {
            "task": "TEXT", "result_json": "TEXT", "warnings_json": "TEXT",
            "currency": "TEXT NOT NULL DEFAULT 'CNY'", "input_chars": "INTEGER",
            "group_id": "TEXT", "brain_provider": "TEXT", "reserved_amount": "TEXT",
            "actual_amount": "TEXT", "confirmed_month": "TEXT", "latency_s": "REAL",
            "stop_reason": "TEXT", "repaired": "INTEGER NOT NULL DEFAULT 0",
            "attempt": "INTEGER NOT NULL DEFAULT 1", "parent_job_id": "TEXT",
            "media_provider": "TEXT", "item_id": "TEXT",
        },
    }
    for table, columns in additions.items():
        # 只补已存在的表：旧库可能还没建这张表，建表由 STUDIO_TABLES_DDL 负责。
        async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)) as cursor:
            if await cursor.fetchone() is None:
                continue
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    for table, statement in _ADDED_COLUMN_INDEXES:
        async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)) as cursor:
            if await cursor.fetchone() is None:
                continue
        await db.execute(statement)


@asynccontextmanager
async def connection(*, transaction: bool = False):
    """每次取动态 DB_PATH；写事务序列化确认、预留、抢占和结算。"""
    import database
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        if transaction:
            await db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            if transaction:
                await db.commit()
        except BaseException:
            if transaction:
                await db.rollback()
            raise


connect = connection


async def _one(db, sql, params=()) -> dict | None:
    async with db.execute(sql, params) as cursor:
        return _row(await cursor.fetchone())


async def _many(db, sql, params=()) -> list[dict]:
    async with db.execute(sql, params) as cursor:
        return [_row(row) for row in await cursor.fetchall()]


def _exemplar_row(row) -> dict | None:
    """案例行：JSON 列同时给出解析后的 shot/qc/tags，便于接口直接返回。"""
    if row is None:
        return None
    result = dict(row)
    for key, target in _EXEMPLAR_JSON_FIELDS.items():
        value = result.get(key)
        result[target] = json.loads(value) if value else None
    if result.get("archived") is not None:
        result["archived"] = bool(result["archived"])
    return result


def _stats_row(row) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for key, target in _STATS_JSON_FIELDS.items():
        value = result.get(key)
        result[target] = json.loads(value) if value else {}
    return result


async def _project(db, project_id: str, owner: str) -> dict:
    project = await _one(db, "SELECT * FROM studio_projects WHERE id=? AND owner=? AND archived=0",
                         (project_id, owner))
    if project is None:
        raise HTTPException(404, "Not Found")
    return project


async def _get_job(db, job_id: str, owner: str | None = None) -> dict | None:
    sql, args = "SELECT * FROM studio_jobs WHERE id=?", [job_id]
    if owner is not None:
        sql += " AND owner=?"
        args.append(owner)
    async with db.execute(sql, args) as cursor:
        row = await cursor.fetchone()
    if row is not None and row['kind'] == 'brain' and row['task'] in {
        'novel_complete', 'text_map', 'synopsis', 'episode_plan',
    }:
        from .breakdown import decode_job_row
        return await decode_job_row(row)
    return _row(row)


async def create_project(owner: str, title: str, aspect: str) -> dict:
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise HTTPException(422, "项目标题须为 1–200 字")
    if aspect not in {"16:9", "9:16"}:
        raise HTTPException(422, "画幅必须为 16:9 或 9:16")
    project_id, now = str(uuid.uuid4()), utcnow()
    async with connection(transaction=True) as db:
        # 鉴权与数据库写入之间可能发生删号，锁内复核避免复活孤儿项目。
        if await _one(db, "SELECT username FROM users WHERE username=?", (owner,)) is None:
            raise HTTPException(404, "Not Found")
        await db.execute(
            "INSERT INTO studio_projects(id,owner,title,aspect,created_at,updated_at,brain_provider) VALUES(?,?,?,?,?,?,?)",
            (project_id, owner, title.strip(), aspect, now, now, get_settings().brain_default),
        )
        return await _project(db, project_id, owner)


async def get_project(project_id: str, owner: str) -> dict:
    async with connection() as db:
        return await _project(db, project_id, owner)


async def list_projects(owner: str) -> list[dict]:
    async with connection() as db:
        return await _many(db, "SELECT * FROM studio_projects WHERE owner=? AND archived=0 ORDER BY updated_at DESC,id",
                           (owner,))


async def get_review_provider(pid: str, owner: str) -> str:
    """项目审核模型；PATCH 之外的读取都统一返回字符串。"""
    async with connection() as db:
        row = await _one(db, "SELECT review_provider FROM studio_projects "
                             "WHERE id=? AND owner=? AND archived=0", (pid, owner))
        if row is None:
            raise HTTPException(404, "Not Found")
        return row["review_provider"] or "qwen"


async def set_review_provider(pid: str, owner: str, value: str) -> None:
    if value not in REVIEW_PROVIDERS:
        raise HTTPException(422, "审核模型只能为 claude、qwen、deepseek 或 off")
    async with connection(transaction=True) as db:
        async with db.execute(
            "UPDATE studio_projects SET review_provider=? WHERE id=? AND owner=? AND archived=0",
            (value, pid, owner),
        ) as cursor:
            if cursor.rowcount != 1:
                raise HTTPException(404, "Not Found")


def _json_column(value, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
        except ValueError:
            raise ValueError(f"{field} 必须是合法 JSON") from None
        return value
    return _json(value)


def _exemplar_fields(fields: dict) -> dict:
    unknown = set(fields) - {
        "id", "project_id", "source", "scene_type", "kind", "reason", "shot", "shot_json",
        "keyframe_asset_id", "video_model", "qc", "qc_json", "cost_cny", "tags", "tags_json",
        "created_at", "archived",
    }
    if unknown:
        raise ValueError("未知案例字段")
    fields = dict(fields)
    for alias, column in (("shot", "shot_json"), ("qc", "qc_json"), ("tags", "tags_json")):
        if alias in fields:
            fields[column] = _json_column(fields.pop(alias), alias)
    return fields


async def create_exemplar(owner: str, **fields) -> dict:
    """导入或手工写入案例；shot 必填，kind 默认 good。"""
    from .director_kb import schema as kb_schema

    fields = _exemplar_fields(fields)
    scene_type = fields.get("scene_type")
    if scene_type not in kb_schema.SCENE_TYPES:
        raise HTTPException(422, "场景类型不在知识库清单内")
    if fields.get("shot_json") is None:
        raise HTTPException(422, "案例必须带镜头数据")
    kind = fields.get("kind", "good")
    if kind not in ("good", "bad"):
        raise HTTPException(422, "案例类型只能为 good 或 bad")
    if "reason" in fields and not isinstance(fields["reason"], str):
        raise HTTPException(422, "案例原因必须是文字")
    identifier = fields.pop("id", None)
    if identifier is not None and (not isinstance(identifier, str) or not identifier.strip()):
        raise HTTPException(422, "案例 id 无效")
    row = {
        "id": identifier or str(uuid.uuid4()),
        "owner": owner,
        "project_id": fields.get("project_id"),
        "source": fields.get("source") or "studio",
        "scene_type": scene_type,
        "kind": kind,
        "reason": fields.get("reason") or "",
        "shot_json": fields["shot_json"],
        "keyframe_asset_id": fields.get("keyframe_asset_id"),
        "video_model": fields.get("video_model"),
        "qc_json": fields.get("qc_json"),
        "cost_cny": None if fields.get("cost_cny") is None else str(fields["cost_cny"]),
        "tags_json": fields.get("tags_json"),
        "created_at": fields.get("created_at") or utcnow(),
        "archived": int(bool(fields.get("archived", 0))),
    }
    async with connection(transaction=True) as db:
        try:
            await db.execute(
                """INSERT INTO studio_exemplars(id,owner,project_id,source,scene_type,kind,reason,
                   shot_json,keyframe_asset_id,video_model,qc_json,cost_cny,tags_json,created_at,archived)
                   VALUES(:id,:owner,:project_id,:source,:scene_type,:kind,:reason,:shot_json,
                   :keyframe_asset_id,:video_model,:qc_json,:cost_cny,:tags_json,:created_at,:archived)""",
                row,
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "案例 id 已存在") from None
        return _exemplar_row(await _one(db, "SELECT * FROM studio_exemplars WHERE id=?", (row["id"],)))


async def list_exemplars(owner: str, *, scene_type: str | None = None,
                         kind: str | None = None) -> list[dict]:
    if kind is not None and kind not in ("good", "bad"):
        raise HTTPException(422, "案例类型只能为 good 或 bad")
    sql = "SELECT * FROM studio_exemplars WHERE owner=? AND archived=0"
    args: list = [owner]
    if scene_type is not None:
        sql += " AND scene_type=?"
        args.append(scene_type)
    if kind is not None:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY created_at DESC,id DESC"
    async with connection() as db:
        async with db.execute(sql, args) as cursor:
            return [_exemplar_row(row) for row in await cursor.fetchall()]


async def get_exemplar(owner: str, exemplar_id: str) -> dict:
    async with connection() as db:
        exemplar = _exemplar_row(await _one(
            db, "SELECT * FROM studio_exemplars WHERE id=? AND owner=?", (exemplar_id, owner)))
        if exemplar is None:
            raise HTTPException(404, "Not Found")
        return exemplar


async def update_exemplar(owner: str, exemplar_id: str, *, kind: str | None = None,
                          reason: str | None = None, archived: bool | int | None = None) -> dict:
    """PATCH /kb/exemplars/{id} 的数据入口：只允许改 kind、reason、归档。"""
    updates: dict = {}
    if kind is not None:
        if kind not in ("good", "bad"):
            raise HTTPException(422, "案例类型只能为 good 或 bad")
        updates["kind"] = kind
    if reason is not None:
        if not isinstance(reason, str) or len(reason) > 2000:
            raise HTTPException(422, "案例原因不能超过 2000 字")
        updates["reason"] = reason
    if archived is not None:
        if type(archived) not in (bool, int):
            raise HTTPException(422, "归档标记必须是布尔值")
        updates["archived"] = int(bool(archived))
    async with connection(transaction=True) as db:
        if await _one(db, "SELECT id FROM studio_exemplars WHERE id=? AND owner=?",
                      (exemplar_id, owner)) is None:
            raise HTTPException(404, "Not Found")
        if updates:
            assignments = ",".join(f"{key}=?" for key in updates)
            await db.execute(f"UPDATE studio_exemplars SET {assignments} WHERE id=? AND owner=?",
                             (*updates.values(), exemplar_id, owner))
        return _exemplar_row(await _one(
            db, "SELECT * FROM studio_exemplars WHERE id=? AND owner=?", (exemplar_id, owner)))


def good_exemplars_for_retrieval(owner: str, scene_type: str, limit: int = 3) -> list[dict]:
    """同步读接口：select_materials 可能在异步路由里被同步调用，不能 asyncio.run。"""
    import database

    limit = max(1, min(int(limit), 50))
    connection = sqlite3.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT * FROM studio_exemplars
               WHERE owner=? AND scene_type=? AND kind='good' AND archived=0
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (owner, scene_type, limit),
        ).fetchall()
    finally:
        connection.close()
    return [_exemplar_row(row) for row in rows]


async def list_stats(owner: str) -> list[dict]:
    """节奏统计原始行；ready 判定与对外形状由 director_kb.stats 负责。"""
    async with connection() as db:
        async with db.execute(
            "SELECT * FROM studio_stats WHERE owner=? ORDER BY scene_type", (owner,)
        ) as cursor:
            return [_stats_row(row) for row in await cursor.fetchall()]



async def _create_asset(db, owner: str, project_id: str, fields: dict) -> dict:
    await _project(db, project_id, owner)
    allowed = {"id", "kind", "source", "rel_path", "sha256", "bytes", "width", "height", "duration_s",
               "fps", "has_audio", "meta_json", "meta", "created_at", "archived",
               "item_id", "version_no", "role"}
    if set(fields) - allowed:
        raise ValueError("未知素材字段")
    fields = dict(fields)
    if fields.get("source") == "upload":
        # 同一图片的并发上传共享文件及素材 ID，检查和写入必须同属写事务。
        existing = await _one(db, """SELECT * FROM studio_assets WHERE project_id=? AND owner=?
            AND sha256=? AND kind=? AND source='upload' AND archived=0 LIMIT 1""",
                              (project_id, owner, fields.get("sha256"), fields.get("kind")))
        if existing is not None:
            return existing
    fields["id"] = fields.get("id") or str(uuid.uuid4())
    fields["owner"], fields["project_id"] = owner, project_id
    fields.setdefault("created_at", utcnow())
    if "meta" in fields:
        fields["meta_json"] = _json(fields.pop("meta"))
    elif isinstance(fields.get("meta_json"), dict):
        fields["meta_json"] = _json(fields["meta_json"])
    fields.setdefault("meta_json", "{}")
    columns = ",".join(fields)
    await db.execute(f"INSERT INTO studio_assets({columns}) VALUES({','.join('?' for _ in fields)})", tuple(fields.values()))
    await db.execute("UPDATE studio_projects SET updated_at=? WHERE id=? AND owner=?",
                     (utcnow(), project_id, owner))
    return await _one(db, "SELECT * FROM studio_assets WHERE id=?", (fields["id"],))


async def create_asset(owner: str, project_id: str, **fields) -> dict:
    async with connection(transaction=True) as db:
        return await _create_asset(db, owner, project_id, fields)


async def save_uploaded_asset(owner: str, project_id: str, data: bytes, metadata: dict) -> dict:
    """验证、落盘与入库持有同一写锁，删号不能穿过验证后重建项目目录。"""
    from . import storage
    async with connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        fields = None
        committed = False
        try:
            await _project(db, project_id, owner)
            existing = await _one(db, """SELECT * FROM studio_assets WHERE project_id=? AND owner=?
                AND sha256=? AND kind='image' AND source='upload' AND archived=0 LIMIT 1""",
                                  (project_id, owner, metadata["sha256"]))
            if existing is not None:
                await db.rollback()
                return existing
            write_task = asyncio.create_task(asyncio.to_thread(storage.save_image, project_id, data, metadata))
            try:
                fields = await asyncio.shield(write_task)
            except asyncio.CancelledError:
                # 线程不能被取消；必须等写完再清理，不能提前释放删号锁。
                fields = await write_task
                raise
            asset = await _create_asset(db, owner, project_id, fields)
            commit_task = asyncio.create_task(db.commit())
            try:
                await asyncio.shield(commit_task)
            except asyncio.CancelledError:
                await commit_task
                committed = True
                raise
            committed = True
            return asset
        except BaseException:
            if not committed:
                try:
                    if fields is not None:
                        await asyncio.to_thread(storage.discard_file, fields["rel_path"])
                finally:
                    await db.rollback()
            raise


async def get_asset(asset_id: str, owner: str) -> dict:
    async with connection() as db:
        asset = await _one(db, "SELECT * FROM studio_assets WHERE id=? AND owner=? AND archived=0", (asset_id, owner))
        if asset is None:
            raise HTTPException(404, "Not Found")
        await _project(db, asset["project_id"], owner)
        return asset


async def list_assets(project_id: str, owner: str) -> list[dict]:
    async with connection() as db:
        await _project(db, project_id, owner)
        return await _many(db, """SELECT * FROM studio_assets
            WHERE project_id=? AND owner=? AND archived=0 ORDER BY created_at DESC,id""",
                           (project_id, owner))


async def find_asset_by_sha(project_id: str, owner: str, sha256: str) -> dict | None:
    async with connection() as db:
        await _project(db, project_id, owner)
        return await _one(db, "SELECT * FROM studio_assets WHERE project_id=? AND owner=? AND sha256=? AND archived=0 LIMIT 1",
                          (project_id, owner, sha256))


async def create_quote(owner: str, project_id: str, items: dict | list[dict], *, now=None) -> dict:
    from . import spend
    # 单镜接口传参数；批量内部调用传 item。所有价格仍由本地价目重算。
    supplied = [items] if isinstance(items, dict) else items
    if not supplied:
        raise HTTPException(422, "报价至少需要一个镜头")
    normalized = [pricing.quote_item(item.get("params", item)) for item in supplied]
    minimum = sum((pricing.money(item["est_min_cny"]) for item in normalized), Decimal(0))
    maximum = sum((pricing.money(item["est_max_cny"]) for item in normalized), Decimal(0))
    cap = pricing.money(get_settings().max_quote_cny)
    if maximum > cap:
        raise HTTPException(422, f"本次报价超过单次上限 ¥{cap:.2f}")
    quote_id, stamp = str(uuid.uuid4()), _timestamp(now)
    expires = (parse_time(stamp) + timedelta(minutes=15)).isoformat()
    async with connection(transaction=True) as db:
        await _project(db, project_id, owner)
        for item in normalized:
            asset = await _one(db, "SELECT * FROM studio_assets WHERE id=? AND project_id=? AND owner=? AND kind='image' AND archived=0",
                               (item["params"]["first_frame_asset_id"], project_id, owner))
            if asset is None:
                raise HTTPException(404, "Not Found")
        params_hash = hashlib.sha256(_json([item["params"] for item in normalized]).encode()).hexdigest()
        await db.execute(
            """INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,total_max_cny,
               params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'open',?,?)""",
            (quote_id, project_id, owner, _json(normalized), str(minimum), str(maximum), params_hash, stamp, expires),
        )
        quote = await _one(db, "SELECT * FROM studio_quotes WHERE id=?", (quote_id,))
        quote["today"] = await spend.today(now=stamp, db=db)
        return quote


async def get_quote(quote_id: str, owner: str) -> dict:
    async with connection() as db:
        quote = await _one(db, "SELECT * FROM studio_quotes WHERE id=? AND owner=?", (quote_id, owner))
        if quote is None:
            raise HTTPException(404, "Not Found")
        return quote


async def confirm_quote(quote_id: str, owner: str, *, now=None) -> list[dict]:
    from . import spend
    stamp = _timestamp(now)
    async with connection(transaction=True) as db:
        quote = await _one(db, "SELECT * FROM studio_quotes WHERE id=? AND owner=?", (quote_id, owner))
        if quote is None:
            raise HTTPException(404, "Not Found")
        await _project(db, quote["project_id"], owner)
        if quote["status"] != "open":
            raise HTTPException(409, "报价已经确认，不能重复确认")
        if parse_time(quote["expires_at"]) <= parse_time(stamp):
            raise HTTPException(409, "报价已过期，请重新报价")
        if not isinstance(quote["items"], list) or any("params" not in item for item in quote["items"]):
            raise HTTPException(409, "此报价须通过对应任务的确认接口开始")
        day = await spend.check_reservation(db, quote["total_max_cny"], now=stamp)
        async with db.execute(
            "UPDATE studio_quotes SET status='confirmed',confirmed_at=? WHERE id=? AND owner=? AND status='open'",
            (stamp, quote_id, owner),
        ) as cursor:
            if cursor.rowcount != 1:
                raise HTTPException(409, "报价已经确认，不能重复确认")
        jobs = []
        for item in quote["items"]:
            params = item["params"]
            asset = await _one(db, "SELECT id FROM studio_assets WHERE id=? AND owner=? AND project_id=? AND archived=0",
                               (params["first_frame_asset_id"], owner, quote["project_id"]))
            if asset is None:
                raise HTTPException(404, "Not Found")
            job_id = str(uuid.uuid4())
            item_id = item["quote_item_id"]
            fingerprint = hashlib.sha256(_json({"params": params, "quote_item_id": item_id}).encode()).hexdigest()
            try:
                await db.execute(
                    """INSERT INTO studio_jobs(id,project_id,owner,provider,model,params_json,fingerprint,
                       quote_id,quote_item_id,status,est_min_cny,est_max_cny,reserved_cny,created_at,updated_at,confirmed_day)
                       VALUES(?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?,?)""",
                    (job_id, quote["project_id"], owner, params["provider"], params["model"], _json(params), fingerprint,
                     quote_id, item_id, str(pricing.money(item["est_min_cny"])), str(pricing.money(item["est_max_cny"])),
                     str(pricing.money(item["est_max_cny"])), stamp, stamp, day),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "该报价镜头已经存在在途任务") from None
            jobs.append(await _get_job(db, job_id, owner))
        await db.execute("UPDATE studio_projects SET updated_at=? WHERE id=? AND owner=?",
                         (stamp, quote["project_id"], owner))
        return jobs


async def get_job(job_id: str, owner: str | None = None) -> dict:
    async with connection() as db:
        job = await _get_job(db, job_id, owner)
        if job is None:
            raise HTTPException(404, "Not Found")
        return job


async def list_jobs(project_id: str, owner: str) -> list[dict]:
    async with connection() as db:
        await _project(db, project_id, owner)
        return await _many(db, "SELECT * FROM studio_jobs WHERE project_id=? AND owner=? AND kind='i2v' ORDER BY created_at DESC,id",
                           (project_id, owner))


async def list_jobs_by_status(statuses) -> list[dict]:
    values = [statuses] if isinstance(statuses, str) else list(statuses)
    if not values:
        return []
    async with connection() as db:
        return await _many(db, f"SELECT * FROM studio_jobs WHERE status IN ({','.join('?' for _ in values)}) ORDER BY created_at,id", values)


async def cas_job(job_id: str, expected_status, updates: dict, run_token=None, db=None) -> bool:
    """状态条件和可选 run_token 一并检查；终态同时结算，永不退回 queued。"""
    if db is None:
        async with connection(transaction=True) as current:
            return await cas_job(job_id, expected_status, updates, run_token=run_token, db=current)
    expected = {expected_status} if isinstance(expected_status, str) else set(expected_status)
    job = await _get_job(db, job_id)
    if job and job.get("kind") == "brain":
        from .brain_jobs import transition
        return await transition(db, job, expected_status, updates, run_token=run_token)
    if job and job.get("kind") in CASTING_JOB_KINDS:
        # 定妆与声线任务有自己的结算口径，绝不走 i2v 的 params["resolution"] 计价。
        from .casting_jobs import transition
        return await transition(db, job, expected_status, updates, run_token=run_token)
    if job is None or job["status"] not in expected or (run_token is not None and job["run_token"] != run_token):
        return False
    project = await _one(db, "SELECT id FROM studio_projects WHERE id=? AND owner=? AND archived=0",
                         (job["project_id"], job["owner"]))
    if project is None:
        return False
    if set(updates) - _JOB_UPDATE_FIELDS:
        raise ValueError("未知任务更新字段")
    updates = dict(updates)
    target = updates.get("status", job["status"])
    if target != job["status"] and target not in _TRANSITIONS.get(job["status"], set()):
        raise ValueError("不允许的任务状态转换")
    from .spend import SETTLED_STATUSES, ZERO_STATUSES
    if "status" in updates and target in ZERO_STATUSES | SETTLED_STATUSES:
        usage = updates.get("usage_json", job.get("usage"))
        if isinstance(usage, str):
            usage = json.loads(usage)
        updates["actual_cny"] = (pricing.money(0) if target in ZERO_STATUSES else
                                 pricing.actual_cost(job["provider"], job["params"]["resolution"], usage))
        updates["reserved_cny"] = (pricing.money(job["reserved_cny"]) if updates["actual_cny"] is None
                                   else pricing.money(0))
        updates.setdefault("finished_at", utcnow())
        updates.setdefault("needs_recheck", 0)
        updates.setdefault("poll_requested", 0)
        updates.setdefault("next_poll_at", None)
    updates.setdefault("updated_at", utcnow())
    for key, value in list(updates.items()):
        if key in _MONEY_FIELDS and value is not None:
            updates[key] = str(pricing.money(value))
        elif key in _JSON_FIELDS and value is not None and not isinstance(value, str):
            updates[key] = _json(value)
        elif isinstance(value, datetime):
            updates[key] = _timestamp(value)
    assignments = ",".join(f"{key}=?" for key in updates)
    sql = f"UPDATE studio_jobs SET {assignments} WHERE id=? AND status=?"
    values = [*updates.values(), job_id, job["status"]]
    if run_token is not None:
        sql += " AND run_token=?"
        values.append(run_token)
    async with db.execute(sql, values) as cursor:
        return cursor.rowcount == 1


transition_job = cas_job


async def claim_next_job(provider: str, limit: int, run_token: str) -> dict | None:
    async with connection(transaction=True) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM studio_jobs WHERE kind='i2v' AND provider=? AND status IN ('submitting','submitted','running')", (provider,)
        ) as cursor:
            active = (await cursor.fetchone())[0]
        if active >= limit:
            return None
        job = await _one(db, "SELECT * FROM studio_jobs WHERE kind='i2v' AND provider=? AND status='queued' ORDER BY created_at,id LIMIT 1", (provider,))
        if job is None:
            return None
        stamp = utcnow()
        if not await cas_job(job["id"], "queued", {"status": "submitting", "run_token": run_token, "submitted_at": stamp}, db=db):
            return None
        return await _get_job(db, job["id"])


async def list_due_jobs(now=None) -> list[dict]:
    stamp = _timestamp(now)
    async with connection() as db:
        return await _many(db, """SELECT * FROM studio_jobs WHERE kind='i2v' AND task_id IS NOT NULL AND task_id!=''
            AND status IN ('submitted','running','uncertain')
            AND (poll_requested=1 OR (status IN ('submitted','running') AND needs_recheck=0))
            AND (poll_requested=1 OR next_poll_at IS NULL OR next_poll_at<=?) ORDER BY created_at,id""", (stamp,))


async def list_pending_downloads(now=None) -> list[dict]:
    async with connection() as db:
        return await _many(db, """SELECT * FROM studio_jobs WHERE kind='i2v' AND status='succeeded' AND result_asset_id IS NULL
            AND (poll_requested=1 OR (needs_recheck=0 AND (next_poll_at IS NULL OR next_poll_at<=?)))
            ORDER BY created_at,id""", (_timestamp(now),))


async def _owned_job(db, job_id: str, owner: str) -> dict:
    job = await _get_job(db, job_id, owner)
    if job is None:
        raise HTTPException(404, "Not Found")
    return job


async def cancel_job(job_id: str, owner: str) -> dict:
    async with connection(transaction=True) as db:
        job = await _owned_job(db, job_id, owner)
        if job["status"] != "queued" or not await cas_job(job_id, "queued", {"status": "cancelled"}, db=db):
            raise HTTPException(409, "只能取消排队中的任务")
        return await _get_job(db, job_id, owner)


async def recheck_job(job_id: str, owner: str) -> dict:
    async with connection(transaction=True) as db:
        job = await _owned_job(db, job_id, owner)
        allowed = bool(job["task_id"]) and (job["status"] in {"submitted", "running", "uncertain"}
                                            or (job["status"] == "succeeded" and job["needs_recheck"]))
        if not allowed or not await cas_job(job_id, job["status"], {"poll_requested": 1, "next_poll_at": utcnow()}, db=db):
            raise HTTPException(409, "该任务不能轮询，请先核对或关联上游任务 ID")
        return await _get_job(db, job_id, owner)


async def link_task(job_id: str, owner: str, task_id: str) -> dict:
    if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 512:
        raise HTTPException(422, "请提供有效的上游任务 ID")
    async with connection(transaction=True) as db:
        job = await _owned_job(db, job_id, owner)
        if job.get("kind") == "brain":
            raise HTTPException(409, "导演模型为同步调用，没有上游任务号，只能核对后释放")
        if job.get("kind") in CASTING_JOB_KINDS:
            raise HTTPException(409, "定妆与声线任务没有上游任务号，只能核对后释放")
        if job["status"] != "uncertain" or job["task_id"]:
            raise HTTPException(409, "只能为没有上游任务 ID 的不确定任务关联 ID")
        stamp = utcnow()
        if not await cas_job(job_id, "uncertain", {"status": "submitted", "task_id": task_id.strip(),
                            "needs_recheck": 0, "poll_requested": 1, "next_poll_at": stamp,
                            "error_code": None, "error_message": None}, db=db):
            raise HTTPException(409, "任务状态已变更")
        return await _get_job(db, job_id, owner)


async def release_job(job_id: str, owner: str, not_charged: bool, note: str | None = None) -> dict:
    if not_charged is not True:
        raise HTTPException(422, "请先确认此任务未扣费")
    if note is not None and (not isinstance(note, str) or len(note) > 2000):
        raise HTTPException(422, "核对说明不能超过 2000 字")
    async with connection(transaction=True) as db:
        job = await _owned_job(db, job_id, owner)
        if job["status"] != "uncertain" or not await cas_job(
            job_id, "uncertain", {"status": "released", "error_code": "not_charged",
                                 "error_message": note or "作者已确认未扣费"}, db=db,
        ):
            raise HTTPException(409, "只能释放确认未扣费的不确定任务")
        return await _get_job(db, job_id, owner)


async def finish_download(job_id: str, asset_metadata: dict, *, run_token=None) -> bool:
    """素材和结算原子提交；删号或陈旧 worker 都不能复活素材行。"""
    async with connection(transaction=True) as db:
        job = await _get_job(db, job_id)
        if job is None or job["status"] != "succeeded" or (run_token is not None and job["run_token"] != run_token):
            return False
        project = await _one(db, "SELECT id FROM studio_projects WHERE id=? AND owner=? AND archived=0",
                             (job["project_id"], job["owner"]))
        if project is None:
            return False
        metadata = {**asset_metadata, "kind": "video", "source": "generated"}
        asset = await _create_asset(db, job["owner"], job["project_id"], metadata)
        changed = await cas_job(job_id, "succeeded", {"status": "downloaded", "result_asset_id": asset["id"],
                                "error_code": None, "error_message": None},
                                run_token=run_token, db=db)
        if not changed:
            # 写锁下仍保留检查，避免未来修改意外留下孤立结果。
            raise RuntimeError("工作室下载提交状态冲突")
        return True


record_download = finish_download
