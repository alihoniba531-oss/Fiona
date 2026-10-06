"""副本迁移演练与在线 WAL 备份，不读取真实配置或调用服务。"""

import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import time

import pytest


BACKEND = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = BACKEND.parent / "deploy" / "fiona-backup.sh"
SQLITE_CLI = shutil.which("sqlite3")
PRIVATE_TEXT = "private-message-content-should-not-be-printed"


def _environment(**updates):
    env = os.environ.copy()
    env.pop("FIONA_ENV_FILE", None)
    env.pop("FIONA_DB_PATH", None)
    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(updates)
    return env


def _run_migration(*args, env=None):
    return subprocess.run(
        [sys.executable, str(BACKEND / "migrate.py"), *map(str, args)],
        cwd=BACKEND, env=env or _environment(), capture_output=True, text=True,
        check=False,
    )


def _legacy_db(path, *, orphan=False, wal=False):
    db = sqlite3.connect(path)
    if wal:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, profile_json TEXT DEFAULT '{}')")
    db.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, username TEXT, role TEXT, "
        "content TEXT, image_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    if not orphan:
        db.execute("INSERT INTO users (username) VALUES ('legacy_owner')")
    db.execute(
        "INSERT INTO messages (username, role, content) VALUES ('legacy_owner', 'user', ?)",
        (PRIVATE_TEXT,),
    )
    db.commit()
    return db


def _sidecar_snapshot(path):
    return {item.name: item.read_bytes() for item in path.parent.glob(path.name + "*")}


def test_migration_defaults_to_copy_preserves_source_wal_and_private_rows(tmp_path):
    source = tmp_path / "legacy.db"
    db = _legacy_db(source, wal=True)
    try:
        assert Path(str(source) + "-wal").exists()
        before = _sidecar_snapshot(source)
        result = _run_migration("--db", source)
        assert result.returncode == 0, result.stderr
        assert _sidecar_snapshot(source) == before
        assert "迁移前 schema_migrations：[]" in result.stdout
        assert "20260905_official_exchange_workflow_v4" in result.stdout
        assert "迁移前 表 messages：行数=1" in result.stdout
        assert "迁移后 表 messages：行数=1" in result.stdout
        assert PRIVATE_TEXT not in result.stdout + result.stderr
        assert "conversation_id" not in [row[1] for row in db.execute("PRAGMA table_info(messages)")]
    finally:
        db.close()


def test_migration_in_place_applies_five_versions_and_preserves_message(tmp_path):
    source = tmp_path / "legacy.db"
    _legacy_db(source).close()
    result = _run_migration("--db", source, "--in-place")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"原库迁移目标：{source.resolve()}\n")
    assert result.stdout.index(str(source.resolve())) < result.stdout.index("迁移前 schema_migrations")
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5
        content, conversation = db.execute("SELECT content, conversation_id FROM messages").fetchone()
        assert content == PRIVATE_TEXT
        assert conversation


def test_migration_explicit_db_wins_over_service_config_and_process_env(tmp_path):
    selected = tmp_path / "selected.db"
    _legacy_db(selected).close()
    ignored = tmp_path / "ignored.db"
    service_config = tmp_path / "service-config.txt"
    service_config.write_text(f"FIONA_DB_PATH={ignored}\n", encoding="utf-8")
    result = _run_migration(
        "--env-file", service_config, "--db", selected, "--in-place",
        env=_environment(FIONA_DB_PATH=str(tmp_path / "process.db")),
    )
    assert result.returncode == 0, result.stderr
    assert not ignored.exists()
    with sqlite3.connect(selected) as db:
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5


def test_migration_supports_service_config(tmp_path, monkeypatch, capsys):
    import admin_env
    import database
    import migrate

    selected = tmp_path / "selected.db"
    _legacy_db(selected).close()
    config = tmp_path / "service-config.txt"
    config.write_text(f"FIONA_DB_PATH={selected}\n", encoding="utf-8")
    def configure_explicit_file(env_file, *, init_db):
        # 只在明确的测试配置读取期间启用 dotenv，数据库模块导入继续禁用它。
        with monkeypatch.context() as local:
            local.delenv("PYTHON_DOTENV_DISABLED", raising=False)
            return admin_env.configure_database(env_file, init_db=init_db)

    monkeypatch.delenv("FIONA_DB_PATH", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(selected))
    monkeypatch.setattr(migrate, "configure_database", configure_explicit_file)
    assert migrate.main(["--env-file", str(config)]) == 0
    assert "迁移后 schema_migrations" in capsys.readouterr().out


def test_migration_missing_database_returns_two_without_creation(tmp_path):
    missing = tmp_path / "missing.db"
    result = _run_migration("--db", missing)
    assert result.returncode == 2
    assert not missing.exists()
    assert "type=AdminConfigError" in result.stderr
    assert "数据库不存在" in result.stderr
    assert str(missing) not in result.stderr


def test_migration_orphan_hint_and_failure_do_not_change_original(tmp_path):
    source = tmp_path / "orphan.db"
    _legacy_db(source, orphan=True).close()
    before = _sidecar_snapshot(source)
    result = _run_migration("--db", source)
    assert result.returncode == 1
    assert "1 条没有归属用户的消息" in result.stderr
    assert "第①道迁移" in result.stderr
    assert "type=RuntimeError" in result.stderr
    assert "Avatar migration found" not in result.stderr
    assert PRIVATE_TEXT not in result.stdout + result.stderr
    assert _sidecar_snapshot(source) == before


def test_migration_invalid_database_failure_hides_exception_body(tmp_path):
    source = tmp_path / "invalid.db"
    source.write_text(PRIVATE_TEXT, encoding="utf-8")
    result = _run_migration("--db", source)
    assert result.returncode == 1
    assert "type=DatabaseError" in result.stderr
    assert PRIVATE_TEXT not in result.stdout + result.stderr
    assert "file is not a database" not in result.stderr


@pytest.mark.parametrize("missing", ["DASHSCOPE_API_KEY", "JWT_SECRET"])
def test_migration_missing_credentials_are_configuration_failures(tmp_path, missing):
    source = tmp_path / "legacy.db"
    _legacy_db(source).close()
    env = _environment(DEV_MODE="0")
    env.pop(missing, None)
    before = _sidecar_snapshot(source)
    result = _run_migration("--db", source, "--in-place", env=env)
    assert result.returncode == 2
    assert "配置不可用" in result.stderr
    assert "--env-file" in result.stderr
    assert "DASHSCOPE_API_KEY" in result.stderr and "JWT_SECRET" in result.stderr
    assert "迁移失败" not in result.stderr
    assert PRIVATE_TEXT not in result.stdout + result.stderr
    assert _sidecar_snapshot(source) == before


@pytest.mark.parametrize("sqlite_io", [False, True])
def test_migration_io_failures_have_disk_hint(tmp_path, monkeypatch, capsys, sqlite_io):
    import migrate

    source = tmp_path / "legacy.db"
    _legacy_db(source).close()
    before = _sidecar_snapshot(source)

    def copy_failure(*_args, **_kwargs):
        if sqlite_io:
            error = sqlite3.OperationalError(PRIVATE_TEXT)
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error
        raise OSError(PRIVATE_TEXT)

    monkeypatch.setattr(migrate.shutil, "copy2", copy_failure)
    assert migrate.main(["--db", str(source)]) == 1
    output = capsys.readouterr()
    assert "磁盘或 IO 错误" in output.err
    assert "迁移失败" not in output.err
    assert PRIVATE_TEXT not in output.out + output.err
    assert _sidecar_snapshot(source) == before


def test_migration_calls_init_only_without_recovery_or_upload_cleanup(tmp_path, monkeypatch):
    import database
    import exchange_store
    import migrate
    import utils.media as media

    source = tmp_path / "legacy.db"
    _legacy_db(source).close()
    calls = []

    async def init_only():
        calls.append(database.DB_PATH)

    def forbidden(*args, **kwargs):
        pytest.fail("迁移工具不得恢复交流或清理上传")

    monkeypatch.setattr(database, "DB_PATH", str(source))
    monkeypatch.setattr(database, "init_db", init_only)
    monkeypatch.setattr(exchange_store, "recover_interrupted_exchanges", forbidden)
    monkeypatch.setattr(media, "delete_uploaded_files", forbidden)
    migrate._migrate(source)
    assert calls == [str(source)]


@pytest.mark.skipif(SQLITE_CLI is None, reason="没有 sqlite3 命令，无法运行在线备份集成测试")
def test_online_backup_wal_integrity_uploads_permissions_and_retention(tmp_path):
    source = tmp_path / "live 'quoted'.db"
    db = _legacy_db(source, wal=True)
    uploads = tmp_path / "custom 'media'"
    uploads.mkdir()
    (uploads / "sample.png").write_bytes(b"upload bytes")
    (uploads / ".upload_original").write_bytes(PRIVATE_TEXT.encode())
    hidden_dir = uploads / ".upload_nested"
    hidden_dir.mkdir()
    (hidden_dir / "original.png").write_bytes(PRIVATE_TEXT.encode())
    nested_uploads = uploads / "nested"
    nested_uploads.mkdir()
    (nested_uploads / ".upload_hidden").write_bytes(PRIVATE_TEXT.encode())
    backups = tmp_path / "backup 'copies'"
    backups.mkdir()
    old_db = backups / "fiona-db-old.sqlite3"
    old_media = backups / "fiona-uploads-old.tar.gz"
    retained = backups / "fiona-db-recent.sqlite3"
    unrelated = backups / "unrelated.txt"
    nested_backups = backups / "long-term"
    nested_backups.mkdir()
    nested_db = nested_backups / "fiona-db-old.sqlite3"
    nested_media = nested_backups / "fiona-uploads-old.tar.gz"
    for path in (old_db, old_media, retained, unrelated, nested_db, nested_media):
        path.write_bytes(b"old backup")
    old_time = time.time() - 20 * 86400
    for path in (old_db, old_media, unrelated, nested_db, nested_media):
        os.utime(path, (old_time, old_time))
    owners_before = {path.name: path.stat().st_uid for path in tmp_path.glob(source.name + "*")}
    try:
        result = subprocess.run(
            ["sh", str(BACKUP_SCRIPT)], capture_output=True, text=True, check=False,
            env=_environment(
                FIONA_DB_PATH=str(source), FIONA_UPLOADS_DIR=str(uploads),
                FIONA_BACKUP_DIR=str(backups), FIONA_BACKUP_RETENTION_DAYS="14",
            ),
        )
        assert result.returncode == 0, result.stderr
        assert not old_db.exists() and not old_media.exists()
        assert retained.exists() and unrelated.exists()
        assert nested_db.exists() and nested_media.exists()
        copied = [path for path in backups.glob("fiona-db-*.sqlite3") if path != retained]
        archives = list(backups.glob("fiona-uploads-*.tar.gz"))
        assert len(copied) == len(archives) == 1
        assert copied[0].stem.removeprefix("fiona-db-") == archives[0].name.removeprefix("fiona-uploads-").removesuffix(".tar.gz")
        with sqlite3.connect(copied[0]) as backup:
            assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert backup.execute("SELECT COUNT(*) FROM messages").fetchone() == db.execute("SELECT COUNT(*) FROM messages").fetchone()
        with tarfile.open(archives[0]) as archive:
            assert archive.extractfile("uploads/sample.png").read() == b"upload bytes"
            assert not any(part.startswith(".") for name in archive.getnames() for part in name.split("/"))
        for path in (*copied, *archives):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        owners_after = {path.name: path.stat().st_uid for path in tmp_path.glob(source.name + "*")}
        assert owners_after == owners_before
        assert not list(backups.glob(".fiona-*"))
    finally:
        db.close()


@pytest.mark.skipif(SQLITE_CLI is None, reason="没有 sqlite3 命令，无法运行媒体变动备份集成测试")
@pytest.mark.parametrize("archive_created", [False, True])
def test_backup_tar_exit_one_preserves_verified_database(tmp_path, archive_created):
    source = tmp_path / "source.db"
    _legacy_db(source).close()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.png").write_bytes(b"upload bytes")
    backups = tmp_path / "backups"
    commands = tmp_path / "commands"
    commands.mkdir()
    stub = commands / "tar"
    real_tar = shutil.which("tar")
    assert real_tar is not None
    invocation = '"$FIONA_TEST_REAL_TAR" "$@"\n' if archive_created else ""
    stub.write_text("#!/bin/sh\n" + invocation + "exit 1\n", encoding="utf-8")
    stub.chmod(0o700)
    result = subprocess.run(
        ["sh", str(BACKUP_SCRIPT)], capture_output=True, text=True, check=False,
        env=_environment(
            FIONA_DB_PATH=str(source), FIONA_UPLOADS_DIR=str(uploads),
            FIONA_BACKUP_DIR=str(backups), FIONA_TEST_REAL_TAR=real_tar,
            PATH=str(commands) + os.pathsep + os.environ["PATH"],
        ),
    )
    assert result.returncode == 1
    assert "数据库快照已保存" in result.stderr
    assert "媒体备份可能不完整" in result.stderr
    assert "备份以失败状态结束" in result.stderr
    copied = list(backups.glob("fiona-db-*.sqlite3"))
    assert len(copied) == 1
    with sqlite3.connect(copied[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert backup.execute("SELECT COUNT(*) FROM messages").fetchone() == (1,)
    assert stat.S_IMODE(copied[0].stat().st_mode) == 0o600
    assert len(list(backups.glob("fiona-uploads-*.tar.gz"))) == int(archive_created)
    assert not list(backups.glob(".fiona-*"))


@pytest.mark.skipif(SQLITE_CLI is None, reason="没有 sqlite3 命令，无法运行备份失败集成测试")
@pytest.mark.parametrize("failure", ["missing", "invalid", "retention", "tar"])
def test_backup_failure_returns_nonzero_and_cleans_partial_outputs(tmp_path, failure):
    source = tmp_path / "source.db"
    _legacy_db(source).close()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    backups = tmp_path / "backups"
    if failure == "missing":
        source.unlink()
    elif failure == "invalid":
        source.write_bytes(b"invalid sqlite")
    extra = {}
    if failure == "tar":
        commands = tmp_path / "commands"
        commands.mkdir()
        stub = commands / "tar"
        stub.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        stub.chmod(0o700)
        extra["PATH"] = str(commands) + os.pathsep + os.environ["PATH"]
    result = subprocess.run(
        ["sh", str(BACKUP_SCRIPT)], capture_output=True, text=True, check=False,
        env=_environment(
            FIONA_DB_PATH=str(source), FIONA_UPLOADS_DIR=str(uploads),
            FIONA_BACKUP_DIR=str(backups),
            FIONA_BACKUP_RETENTION_DAYS="invalid" if failure == "retention" else "14",
            **extra,
        ),
    )
    assert result.returncode != 0
    assert not list(backups.glob("fiona-*"))
    assert not list(backups.glob(".fiona-*"))


def test_backup_timer_beijing_persistent_and_service_account():
    service = (BACKUP_SCRIPT.parent / "fiona-backup.service").read_text(encoding="utf-8")
    timer = (BACKUP_SCRIPT.parent / "fiona-backup.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "User=fiona" in service and "Group=fiona" in service
    assert "UMask=0077" in service
    assert "OnCalendar=*-*-* 04:00:00 Asia/Shanghai" in timer
    assert "Persistent=true" in timer
