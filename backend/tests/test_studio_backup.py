"""工作室备份独立失败的离线集成测试，只操作临时库和目录。"""

import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import time

import pytest


BACKUP_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "fiona-backup.sh"
SQLITE_CLI = shutil.which("sqlite3")


@pytest.mark.skipif(SQLITE_CLI is None, reason="没有 sqlite3 命令，无法运行备份集成测试")
@pytest.mark.parametrize("studio_tar_status", [0, 1, 2, 9])
def test_studio_backup_failure_keeps_old_archive_and_publishes_main_backup(tmp_path, studio_tar_status):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE test_data (value TEXT)")
        db.execute("INSERT INTO test_data VALUES ('snapshot')")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.png").write_bytes(b"upload")
    studio = tmp_path / "studio"
    project = studio / "project"
    project.mkdir(parents=True)
    (project / "result.mp4").write_bytes(b"video")
    (project / ".hidden").write_bytes(b"private")
    (project / "download.part").write_bytes(b"incomplete")
    backups = tmp_path / "backups"
    backups.mkdir()
    old_studio = backups / "fiona-studio-old.tar.gz"
    old_db = backups / "fiona-db-old.sqlite3"
    for path in (old_studio, old_db):
        path.write_bytes(b"old backup")
        old_time = time.time() - 20 * 86400
        os.utime(path, (old_time, old_time))

    commands = tmp_path / "commands"
    commands.mkdir()
    real_tar = shutil.which("tar")
    assert real_tar is not None
    stub = commands / "tar"
    stub.write_text(
        '#!/bin/sh\n'
        'for archive_root do :; done\n'
        '"$FIONA_TEST_REAL_TAR" "$@" || exit $?\n'
        'if [ "$archive_root" = studio ]; then\n'
        '    exit "$FIONA_TEST_STUDIO_TAR_STATUS"\n'
        'fi\n',
        encoding="utf-8",
    )
    stub.chmod(0o700)
    env = os.environ.copy()
    env.update(
        FIONA_DB_PATH=str(source), FIONA_UPLOADS_DIR=str(uploads),
        FIONA_STUDIO_DIR=str(studio), FIONA_BACKUP_DIR=str(backups),
        FIONA_BACKUP_RETENTION_DAYS="14", FIONA_TEST_REAL_TAR=real_tar,
        FIONA_TEST_STUDIO_TAR_STATUS=str(studio_tar_status),
        PATH=str(commands) + os.pathsep + os.environ["PATH"],
    )
    result = subprocess.run(["sh", str(BACKUP_SCRIPT)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == (1 if studio_tar_status else 0), result.stderr
    copies = list(backups.glob("fiona-db-*.sqlite3"))
    upload_archives = list(backups.glob("fiona-uploads-*.tar.gz"))
    studio_archives = [path for path in backups.glob("fiona-studio-*.tar.gz") if path != old_studio]
    assert len(copies) == len(upload_archives) == 1
    assert len(studio_archives) == (0 if studio_tar_status else 1)
    assert not old_db.exists()
    if studio_tar_status:
        assert "工作室打包失败" in result.stderr
        assert "保留旧工作室备份" in result.stderr
        assert old_studio.read_bytes() == b"old backup"
    else:
        assert not old_studio.exists()
        with tarfile.open(studio_archives[0]) as archive:
            assert archive.extractfile("studio/project/result.mp4").read() == b"video"
            assert not any(name.endswith(".part") or "/." in name for name in archive.getnames())
    with sqlite3.connect(copies[0]) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("SELECT value FROM test_data").fetchone() == ("snapshot",)
    with tarfile.open(upload_archives[0]) as archive:
        assert archive.extractfile("uploads/sample.png").read() == b"upload"
    stamp = copies[0].stem.removeprefix("fiona-db-")
    assert upload_archives[0].name == f"fiona-uploads-{stamp}.tar.gz"
    if studio_archives:
        assert studio_archives[0].name == f"fiona-studio-{stamp}.tar.gz"
    for path in copies + upload_archives + studio_archives:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(backups.glob(".fiona-*"))
