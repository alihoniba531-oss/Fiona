"""WO3d 返修 R1：d11b60d 旧库与半迁移库都必须能跑完 database.init_db()。

旧库的 studio_assets / studio_jobs / studio_projects 缺定妆列（item_id、role、version_no、
media_provider、style_json 等）。database.init_db 先跑 STUDIO_TABLES_DDL、后跑 migrate_schema，
而 CREATE TABLE IF NOT EXISTS 不改旧表，所以引用新列的索引必须等补列之后再建，
否则启动直接抛 sqlite3.OperationalError: no such column: item_id。

用例覆盖三种库：全新库、d11b60d 旧库（git 与内嵌两份旧建表语句）、半迁移库。
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

import database
from studio import store


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "d11b60d"
OWNER = "migration-author"
NOW = "2026-10-16T00:00:00+00:00"

# d11b60d:backend/studio/store.py 原样复制（studio_quotes 一并复制：旧 studio_jobs 的外键要引用它）。
LEGACY_DDL = (
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

# 只在 migrate_schema 里补的定妆列（studio_items 是全新表，旧库里整张都不存在）。
MIGRATED_COLUMNS = {
    "studio_projects": {"setup_json", "setup_confirmed_at", "style_json", "style_group_id"},
    "studio_assets": {"item_id", "version_no", "role"},
    "studio_jobs": {"media_provider", "item_id"},
}

# 半迁移库可能补了一半：定义与 migrate_schema 的 studio_assets 补列一致。
PARTIAL_ASSET_COLUMNS = {"item_id": "TEXT", "version_no": "INTEGER"}


def run(coro):
    return asyncio.run(coro)


def _connection(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _scalar(db_path, sql, params=()):
    connection = _connection(db_path)
    try:
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()


def _columns(db_path, table):
    connection = _connection(db_path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def seed_legacy(db_path, ddl):
    """按给定建表语句造库，并写入旧数据行。"""
    connection = _connection(db_path)
    try:
        with connection:
            for statement in ddl:
                connection.execute(statement)
            connection.execute("INSERT INTO studio_projects (id,owner,title,aspect,created_at,updated_at)"
                               " VALUES ('legacy-p',?,?,?,?,?)", (OWNER, "旧库项目", "16:9", NOW, NOW))
            connection.execute("INSERT INTO studio_assets (id,project_id,owner,kind,source,rel_path,sha256,bytes,"
                               "meta_json,archived,created_at) VALUES ('legacy-a','legacy-p',?,?,?,?,?,?,?,?,?)",
                               (OWNER, "image", "upload", "legacy/p.png", "legacy-sha", 12, "{}", 0, NOW))
            connection.execute("INSERT INTO studio_quotes (id,project_id,owner,items_json,total_min_cny,"
                               "total_max_cny,params_hash,status,created_at,expires_at)"
                               " VALUES ('legacy-q','legacy-p',?,?,?,?,?,?,?,?)",
                               (OWNER, "[]", "0.00000000", "0.00000000", "legacy-hash", "confirmed", NOW, NOW))
            connection.execute("INSERT INTO studio_jobs (id,project_id,owner,kind,provider,model,params_json,"
                               "fingerprint,quote_id,quote_item_id,status,est_min_cny,est_max_cny,created_at,"
                               "updated_at,confirmed_day) VALUES ('legacy-j','legacy-p',?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (OWNER, "i2v", "wan", "wan2.5", "{}", "legacy-fp", "legacy-q", "legacy-item",
                                "succeeded", "0.10000000", "0.20000000", NOW, NOW, "2026-10-16"))
    finally:
        connection.close()


def upgrade(db_path, monkeypatch):
    """连续两次 init_db：第一次升级旧库，第二次证明迁移幂等。"""
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    run(database.init_db())
    run(database.init_db())


def assert_upgraded(db_path):
    for table, expected in MIGRATED_COLUMNS.items():
        assert expected <= _columns(db_path, table), (table, sorted(_columns(db_path, table)))
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_studio_assets_item'")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='index'"
                            " AND name='idx_studio_assets_item_version'")
    # 旧数据行原样保留，新列对旧行留空。
    assert _scalar(db_path, "SELECT title,aspect FROM studio_projects WHERE id='legacy-p'") == ("旧库项目", "16:9")
    assert _scalar(db_path, "SELECT rel_path,sha256,archived,item_id,version_no,role FROM studio_assets"
                            " WHERE id='legacy-a'") == ("legacy/p.png", "legacy-sha", 0, None, None, None)
    assert _scalar(db_path, "SELECT status,provider,media_provider FROM studio_jobs WHERE id='legacy-j'") == \
        ("succeeded", "wan", None)
    assert _scalar(db_path, "SELECT COUNT(*) FROM studio_jobs")[0] == 1
    # 升级后能写入定妆出图任务（kind='image' + media_provider='seedream'）与带 item_id/version_no/role 的资产。
    connection = _connection(db_path)
    try:
        with connection:
            connection.execute("INSERT INTO studio_jobs (id,project_id,owner,kind,provider,model,params_json,"
                               "fingerprint,quote_id,quote_item_id,status,est_min_cny,est_max_cny,created_at,"
                               "updated_at,confirmed_day,media_provider,item_id) VALUES"
                               " ('new-j','legacy-p',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (OWNER, "image", "wan", "seedream-5.0", "{}", "new-fp", "legacy-q", "new-item",
                                "queued", "0.30000000", "0.60000000", NOW, NOW, "2026-10-16", "seedream", "i-cast"))
            connection.execute("INSERT INTO studio_assets (id,project_id,owner,kind,source,rel_path,sha256,bytes,"
                               "meta_json,archived,created_at,item_id,version_no,role) VALUES"
                               " ('new-a','legacy-p',?,?,?,?,?,?,?,?,?,?,?,?)",
                               (OWNER, "image", "generated", "legacy/new.png", "new-sha", 20, "{}", 0, NOW,
                                "i-cast", 1, "sheet"))
    finally:
        connection.close()
    assert _scalar(db_path, "SELECT kind,media_provider,item_id,status FROM studio_jobs WHERE id='new-j'") == \
        ("image", "seedream", "i-cast", "queued")
    assert _scalar(db_path, "SELECT item_id,version_no,role FROM studio_assets WHERE id='new-a'") == \
        ("i-cast", 1, "sheet")


def assert_legacy_shape(db_path):
    """旧库必须真的缺列，否则这条用例跑不出回归（quote_item_id 含 item_id，只能按列判断）。"""
    assert {"item_id", "version_no", "role"} & _columns(db_path, "studio_assets") == set()
    assert "media_provider" not in _columns(db_path, "studio_jobs")
    assert "style_json" not in _columns(db_path, "studio_projects")


def legacy_ddl_from_git():
    if shutil.which("git") is None:
        pytest.skip("git 不可用，跳过基于 git 的旧库用例")
    result = subprocess.run(["git", "show", f"{BASELINE}:backend/studio/store.py"], cwd=ROOT,
                            capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"取不到 {BASELINE}:backend/studio/store.py（浅克隆或缺少该提交）")
    for node in ast.parse(result.stdout).body:
        if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "STUDIO_TABLES_DDL"
                                                for target in node.targets):
            return tuple(ast.literal_eval(node.value))
    pytest.skip(f"{BASELINE} 的 store.py 里没有 STUDIO_TABLES_DDL")


def test_fresh_database_initializes_twice(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    upgrade(db_path, monkeypatch)
    for table, expected in MIGRATED_COLUMNS.items():
        assert expected <= _columns(db_path, table), table
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_items'")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_studio_assets_item'")
    assert _scalar(db_path, "SELECT 1 FROM sqlite_master WHERE type='index'"
                            " AND name='idx_studio_assets_item_version'")


def test_git_baseline_legacy_database_upgrades_and_keeps_rows(tmp_path, monkeypatch):
    ddl = legacy_ddl_from_git()
    db_path = tmp_path / "legacy-git.db"
    seed_legacy(db_path, ddl)
    assert_legacy_shape(db_path)
    upgrade(db_path, monkeypatch)
    assert_upgraded(db_path)


def test_item_version_unique_index_blocks_duplicates(tmp_path, monkeypatch):
    """(item_id,role,version_no) 部分唯一索引：非空 item_id 拒绝重复，NULL 行不参与约束。"""
    db_path = tmp_path / "unique-item-version.db"
    seed_legacy(db_path, LEGACY_DDL)
    upgrade(db_path, monkeypatch)

    def insert_asset(asset_id, item_id, version_no, rel_path, sha256):
        connection.execute("INSERT INTO studio_assets (id,project_id,owner,kind,source,rel_path,sha256,bytes,"
                           "meta_json,archived,created_at,item_id,version_no,role) VALUES"
                           " (?, 'legacy-p', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (asset_id, OWNER, "image", "generated", rel_path, sha256, 32, "{}", 0, NOW,
                            item_id, version_no, "sheet"))

    connection = _connection(db_path)
    try:
        with connection:
            insert_asset("dup-1", "dup-item", 1, "dup/v1.png", "dup-sha-1")
        # 同一 (item_id,role,version_no) 的第二行必须被唯一索引挡住。
        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                insert_asset("dup-2", "dup-item", 1, "dup/v2.png", "dup-sha-2")
        # item_id IS NULL 的行不参与部分唯一索引：重复插入都要成功。
        with connection:
            insert_asset("null-1", None, 1, "null/v1.png", "null-sha-1")
            insert_asset("null-2", None, 1, "null/v2.png", "null-sha-2")
        # 迁移后的接口写入路径：同一 item 的不同 version 都要成功。
        with connection:
            insert_asset("ok-1", "ok-item", 1, "ok/v1.png", "ok-sha-1")
            insert_asset("ok-2", "ok-item", 2, "ok/v2.png", "ok-sha-2")
    finally:
        connection.close()
    assert _scalar(db_path, "SELECT COUNT(*) FROM studio_assets WHERE item_id='dup-item'")[0] == 1
    assert _scalar(db_path, "SELECT COUNT(*) FROM studio_assets WHERE item_id IS NULL")[0] == 3
    assert _scalar(db_path, "SELECT COUNT(*) FROM studio_assets WHERE item_id='ok-item'")[0] == 2
    assert _scalar(db_path, "SELECT version_no FROM studio_assets WHERE id='ok-2'") == (2,)


def test_embedded_legacy_schema_upgrades_without_git(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-embedded.db"
    seed_legacy(db_path, LEGACY_DDL)
    assert_legacy_shape(db_path)
    upgrade(db_path, monkeypatch)
    assert_upgraded(db_path)


@pytest.mark.parametrize("already_added", [(), ("item_id",), ("item_id", "version_no")])
def test_half_migrated_database_upgrades(tmp_path, monkeypatch, already_added):
    """半迁移库：上次启动已建好 studio_items（新列一条未补或补了一半）。"""
    db_path = tmp_path / "half-migrated.db"
    seed_legacy(db_path, LEGACY_DDL)
    studio_items = next(statement for statement in store.STUDIO_TABLES_DDL
                        if statement.startswith("CREATE TABLE IF NOT EXISTS studio_items"))
    connection = _connection(db_path)
    try:
        with connection:
            connection.execute(studio_items)
            for column in already_added:
                connection.execute(f"ALTER TABLE studio_assets ADD COLUMN {column} {PARTIAL_ASSET_COLUMNS[column]}")
    finally:
        connection.close()
    upgrade(db_path, monkeypatch)
    assert_upgraded(db_path)
