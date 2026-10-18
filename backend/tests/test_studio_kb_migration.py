"""WO3e A 块迁移：旧库跑 database.init_db() 补出知识库两表与 review_provider。

两种旧形态都用内嵌 DDL 固定（不依赖 git 历史、不读仓库外文件）：
  * d11b60d：WO3d 之前的四张基础表；
  * 4b45346：WO3d 完成时、WO3e 之前的全部 studio 表。
连续跑两次 init_db 必须正常，旧项目默认 review_provider='qwen'。
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

import database
from studio import store
from studio.director_kb import stats


OWNER = "migration-author"
NOW = "2026-10-16T00:00:00+00:00"

# d11b60d:backend/studio/store.py 的前四张表（studio_quotes 一并保留：studio_jobs 的外键引用它）。
D11B60D_DDL = (
    """CREATE TABLE IF NOT EXISTS studio_projects (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
        aspect TEXT NOT NULL CHECK(aspect IN ('16:9','9:16')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0, brain_provider TEXT NOT NULL DEFAULT 'claude',
        source_kind TEXT CHECK(source_kind IN ('novel','upload','paste','exchange')),
        source_ref TEXT, snapshot_no INTEGER NOT NULL DEFAULT 0,
        episode_seconds_min INTEGER NOT NULL DEFAULT 180, episode_seconds_max INTEGER NOT NULL DEFAULT 240,
        plan_revision INTEGER NOT NULL DEFAULT 0, plan_approved_revision INTEGER, breakdown_id TEXT,
        UNIQUE(id, owner)
    )""",
    """CREATE TABLE IF NOT EXISTS studio_assets (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('image','video','audio')),
        source TEXT NOT NULL CHECK(source IN ('upload','generated')),
        rel_path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
        width INTEGER, height INTEGER, duration_s REAL, fps REAL, has_audio INTEGER,
        meta_json TEXT NOT NULL DEFAULT '{}', archived INTEGER NOT NULL DEFAULT 0,
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
        UNIQUE(quote_id,quote_item_id),
        FOREIGN KEY(project_id,owner) REFERENCES studio_projects(id,owner),
        FOREIGN KEY(quote_id) REFERENCES studio_quotes(id),
        FOREIGN KEY(result_asset_id) REFERENCES studio_assets(id)
    )""",
)

# 4b45346:backend/studio/store.py 原样（WO3d 完成时）。studio_exemplars / studio_stats 与
# review_provider 列都不存在；studio_assets 的 item_id/version_no/role 由迁移补。
BASELINE_4B45346_DDL = (
    """CREATE TABLE IF NOT EXISTS studio_projects (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
        aspect TEXT NOT NULL CHECK(aspect IN ('16:9','9:16')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0, brain_provider TEXT NOT NULL DEFAULT 'claude',
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
    "CREATE INDEX IF NOT EXISTS idx_studio_breakdowns_project ON studio_breakdowns(owner,project_id,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_studio_chunks_breakdown ON studio_chunks(breakdown_id,no)",
    "CREATE INDEX IF NOT EXISTS idx_studio_chunks_job ON studio_chunks(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_bible_breakdown ON studio_bible(owner,breakdown_id,kind)",
    "CREATE INDEX IF NOT EXISTS idx_studio_episodes_breakdown ON studio_episodes(owner,breakdown_id,no)",
    "CREATE INDEX IF NOT EXISTS idx_studio_snapshots_owner_project ON studio_snapshots(owner,project_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_projects_owner_updated ON studio_projects(owner,updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_studio_assets_owner_project ON studio_assets(owner,project_id)",
    "CREATE INDEX IF NOT EXISTS idx_studio_assets_sha ON studio_assets(project_id,owner,sha256)",
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

EXEMPLAR_COLUMNS = {
    "id", "owner", "project_id", "source", "scene_type", "kind", "reason", "shot_json",
    "keyframe_asset_id", "video_model", "qc_json", "cost_cny", "tags_json", "created_at", "archived",
}
STATS_COLUMNS = {
    "owner", "scene_type", "episodes", "shots", "avg_shot_s", "shot_size_json",
    "camera_json", "updated_at",
}


def run(coro):
    return asyncio.run(coro)


def _connection(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _columns(db_path, table):
    connection = _connection(db_path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def _scalar(db_path, sql, params=()):
    connection = _connection(db_path)
    try:
        row = connection.execute(sql, params).fetchone()
        return tuple(row) if row is not None else None
    finally:
        connection.close()


def seed_legacy(db_path, ddl):
    connection = _connection(db_path)
    try:
        with connection:
            for statement in ddl:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO studio_projects (id,owner,title,aspect,created_at,updated_at)"
                " VALUES ('legacy-p',?,?,?,?,?)",
                (OWNER, "旧库项目", "16:9", NOW, NOW))
    finally:
        connection.close()


def upgrade(db_path, monkeypatch):
    """连续两次 init_db：第一次升级旧库，第二次证明迁移幂等。"""
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    run(database.init_db())
    run(database.init_db())


def assert_upgraded(db_path):
    assert "review_provider" in _columns(db_path, "studio_projects")
    assert _columns(db_path, "studio_exemplars") == EXEMPLAR_COLUMNS
    assert _columns(db_path, "studio_stats") == STATS_COLUMNS
    assert _scalar(db_path, "SELECT title,aspect,review_provider FROM studio_projects"
                            " WHERE id='legacy-p'") == ("旧库项目", "16:9", "qwen")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='table'"
                            " AND name='studio_exemplars'")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='table'"
                            " AND name='studio_stats'")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='index'"
                            " AND name='idx_studio_exemplars_owner_scene'")
    # 旧行保留；升级后新插入的项目也取默认 qwen（列默认值，不只是回填）。
    connection = _connection(db_path)
    try:
        with connection:
            connection.execute(
                "INSERT INTO studio_projects (id,owner,title,aspect,created_at,updated_at)"
                " VALUES ('new-p',?,?,?,?,?)",
                (OWNER, "新库项目", "9:16", NOW, NOW))
    finally:
        connection.close()
    assert _scalar(db_path, "SELECT review_provider FROM studio_projects WHERE id='new-p'") == ("qwen",)


def assert_legacy_shape(db_path):
    assert "review_provider" not in _columns(db_path, "studio_projects")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='table'"
                            " AND name='studio_exemplars'") is None
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='table'"
                            " AND name='studio_stats'") is None


def test_d11b60d_database_upgrades_and_keeps_project(tmp_path, monkeypatch):
    db_path = tmp_path / "d11b60d.db"
    seed_legacy(db_path, D11B60D_DDL)
    assert_legacy_shape(db_path)
    upgrade(db_path, monkeypatch)
    assert_upgraded(db_path)


def test_4b45346_database_upgrades_and_keeps_project(tmp_path, monkeypatch):
    db_path = tmp_path / "4b45346.db"
    seed_legacy(db_path, BASELINE_4B45346_DDL)
    assert_legacy_shape(db_path)
    upgrade(db_path, monkeypatch)
    assert_upgraded(db_path)
    # WO3d 已有的迁移列也仍然正常。
    assert {"item_id", "version_no", "role"} <= _columns(db_path, "studio_assets")
    assert "media_provider" in _columns(db_path, "studio_jobs")


def test_review_provider_roundtrip_and_validation(tmp_path, monkeypatch):
    db_path = tmp_path / "provider.db"
    seed_legacy(db_path, D11B60D_DDL)
    upgrade(db_path, monkeypatch)
    assert run(store.get_review_provider("legacy-p", OWNER)) == "qwen"
    for value in store.REVIEW_PROVIDERS:
        run(store.set_review_provider("legacy-p", OWNER, value))
        assert run(store.get_review_provider("legacy-p", OWNER)) == value
    with pytest.raises(store.HTTPException) as caught:
        run(store.set_review_provider("legacy-p", OWNER, "openai"))
    assert caught.value.status_code == 422
    with pytest.raises(store.HTTPException) as caught:
        run(store.set_review_provider("missing", OWNER, "qwen"))
    assert caught.value.status_code == 404
    with pytest.raises(store.HTTPException) as caught:
        run(store.get_review_provider("legacy-p", "other"))
    assert caught.value.status_code == 404


def test_delete_account_removes_kb_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "delete.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    run(database.init_db())
    run(database.get_or_create_user("delete-author"))
    project = run(store.create_project("delete-author", "删号知识库", "16:9"))
    run(store.create_exemplar("delete-author", scene_type="dialogue",
                              shot={"shot_size": "中景"}, source="studio"))
    run(stats.accumulate("delete-author", {
        "dialogue": [{"shot_size": "中景", "camera": "固定机位", "duration_s": 3.0}],
    }))
    result = run(database.delete_account_data("delete-author"))
    assert result["deleted"] is True
    assert f"studio:{project['id']}" in result["upload_paths"]
    connection = _connection(db_path)
    try:
        for table in ("studio_exemplars", "studio_stats", "studio_projects"):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE owner=?", ("delete-author",)
            ).fetchone()[0] == 0
    finally:
        connection.close()
