"""工作室的调用时配置、启动接线、删号清理与离线备份。"""
import asyncio
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import threading
import time
from unittest.mock import AsyncMock

from PIL import Image
import pytest


@pytest.mark.parametrize("name,default", [
    ("FIONA_STUDIO_DAILY_CNY", 300),
    ("FIONA_STUDIO_MAX_QUOTE_CNY", 100),
    ("FIONA_STUDIO_POLL_TIMEOUT_MIN", 30),
])
@pytest.mark.parametrize("raw", ["", "zero", "0", "-1", "nan", "inf", "1e999"])
def test_invalid_positive_config_falls_back_once(monkeypatch, capsys, name, default, raw):
    from studio import config

    monkeypatch.setattr(config, "_INVALID_SETTINGS_WARNED", set())
    monkeypatch.setenv(name, raw)
    attribute = name.removeprefix("FIONA_STUDIO_").lower()
    assert getattr(config.get_settings(), attribute) == default
    assert getattr(config.get_settings(), attribute) == default
    assert capsys.readouterr().out.count(name) == 1
    monkeypatch.setenv(name, "12.5")
    assert getattr(config.get_settings(), attribute) == 12.5


def test_config_flags_exact_owners_hosts_and_directory(monkeypatch, tmp_path):
    from studio import config

    monkeypatch.setenv("FIONA_STUDIO", "false")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", " 0")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", " author , other,author,, ")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("FIONA_STUDIO_VIDEO_HOSTS", " *.example.com,CDN.EXAMPLE.ORG ")
    settings = config.get_settings()
    assert settings.enabled and settings.require_jwt
    assert settings.owners == {"author", "other"}
    assert settings.directory == tmp_path.resolve()
    assert settings.video_hosts == ("*.example.com", "cdn.example.org")
    monkeypatch.setenv("FIONA_STUDIO", "0")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "0")
    assert not config.get_settings().enabled and not config.get_settings().require_jwt


@pytest.mark.parametrize("raw", ["0", "11", "nan", "1.2", "-1", ""])
def test_provider_inflight_config_range(monkeypatch, raw):
    from studio.config import get_settings

    for provider in ("WAN", "SEEDANCE"):
        monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_" + provider, raw)
        assert get_settings().inflight_limit(provider.lower()) == 3
        monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_" + provider, "10")
        assert get_settings().inflight_limit(provider.lower()) == 10


def test_health_checks_studio_only_while_enabled(client, monkeypatch, tmp_path):
    import main

    root = tmp_path / "health-studio"
    root.mkdir()
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    original = main.os.access
    monkeypatch.setattr(main.os, "access", lambda path, mode: False if Path(path) == root else original(path, mode))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["studio_storage"]}
    assert str(root) not in response.text
    monkeypatch.setenv("FIONA_STUDIO", "0")
    assert client.get("/health").status_code == 200


def test_health_missing_studio_does_not_create_it(client, monkeypatch, tmp_path):
    root = tmp_path / "missing-studio"
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    assert client.get("/health").json()["failed"] == ["studio_storage"]
    assert not root.exists()


def _author(client, monkeypatch):
    import auth
    import database

    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "studio-delete")
    user = asyncio.run(database.get_or_create_user("studio-delete"))
    return {"Authorization": "Bearer " + auth.create_token("studio-delete", user["session_version"])}


def test_account_deletion_queues_studio_directory_and_removes_all_rows(client, monkeypatch, tmp_path):
    import database
    import main

    root = tmp_path / "studio-deletion"
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    headers = _author(client, monkeypatch)
    project = client.post("/studio/projects", headers=headers, json={"title": "删除测试", "aspect": "16:9"}).json()
    data = io.BytesIO()
    Image.new("RGB", (640, 480)).save(data, "PNG")
    asset = client.post(f"/studio/projects/{project['id']}/assets", headers=headers,
                        files={"file": ("frame.png", data.getvalue(), "image/png")}).json()
    response = client.post(f"/studio/projects/{project['id']}/clips/quote", headers=headers,
                           json={"first_frame_asset_id": asset["id"], "prompt": "镜头缓缓推进"})
    assert response.status_code == 200, response.text
    assert client.post(f"/studio/quotes/{response.json()['id']}/confirm", headers=headers).status_code == 200
    result = asyncio.run(database.delete_account_data("studio-delete"))
    project_dir = root / project["id"]
    queued = "studio:" + project["id"]
    assert queued in result["upload_paths"]
    assert str(project_dir) not in result["upload_paths"]
    assert queued in asyncio.run(database.get_pending_upload_cleanup())
    with sqlite3.connect(database.DB_PATH) as db:
        for table in ("studio_projects", "studio_assets", "studio_quotes", "studio_jobs"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE owner=?", ("studio-delete",)).fetchone()[0] == 0
    assert project_dir.is_dir()
    asyncio.run(main._run_upload_cleanup_once())
    assert not project_dir.exists()
    assert queued not in asyncio.run(database.get_pending_upload_cleanup())


def test_cleanup_refuses_outside_root_symlink_and_files(monkeypatch, tmp_path):
    from utils.media import delete_uploaded_files

    root = tmp_path / "studio"
    root.mkdir()
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "preserve").write_text("keep")
    linked = root / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    regular = root / "file"
    regular.write_text("keep")
    invalid = [str(root), str(outside), str(linked), str(regular), str(root / ".." / "outside")]
    deleted, failed = delete_uploaded_files(invalid)
    assert deleted == [] and failed == invalid
    assert (outside / "preserve").exists() and regular.exists()
    missing = str(root / "missing-project")
    assert delete_uploaded_files([missing]) == ([missing], [])


def test_cleanup_accepts_studio_directory_sharing_legacy_url_prefix(monkeypatch, tmp_path):
    from utils.media import delete_uploaded_files

    root = tmp_path / "studio"
    project = root / "project"
    project.mkdir(parents=True)
    (project / "video.mp4").write_bytes(b"video")
    monkeypatch.setenv("FIONA_STUDIO_DIR", "/uploads/studio")
    original_resolve = Path.resolve

    # 模拟配置根位于 /uploads/studio，真实文件仍只写会话临时目录。
    def mapped_resolve(path, *args, **kwargs):
        if str(path) == "/uploads/studio":
            return original_resolve(root, *args, **kwargs)
        if str(path).startswith("/uploads/studio/"):
            return original_resolve(root / path.relative_to("/uploads/studio"), *args, **kwargs)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", mapped_resolve)
    queued = "studio:project"
    assert delete_uploaded_files([queued]) == ([queued], [])
    assert not project.exists() and root.exists()


@pytest.mark.parametrize("tagged", [False, True])
def test_cleanup_keeps_permission_failure_in_queue(monkeypatch, tmp_path, tagged):
    from utils.media import delete_uploaded_files

    root = tmp_path / "studio"
    project = root / "project"
    project.mkdir(parents=True)
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    original_stat = Path.stat

    def denied_stat(path, *args, **kwargs):
        if path == project:
            raise PermissionError("blocked")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied_stat)
    queued = "studio:project" if tagged else str(project)
    assert delete_uploaded_files([queued]) == ([], [queued])


@pytest.mark.parametrize("tagged", [False, True])
def test_cleanup_deletes_only_project_directory_within_root(monkeypatch, tmp_path, tagged):
    from utils.media import delete_uploaded_files

    root = tmp_path / "studio"
    project = root / "project"
    (project / "nested").mkdir(parents=True)
    (project / "nested" / "result.mp4").write_bytes(b"video")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    queued = "studio:project" if tagged else str(project)
    assert delete_uploaded_files([queued, queued]) == ([queued], [])
    assert root.is_dir() and not project.exists()


def test_cleanup_tagged_project_uses_current_configured_root(monkeypatch, tmp_path):
    from utils.media import delete_uploaded_files

    old_root = tmp_path / "old-studio"
    new_root = tmp_path / "new-studio"
    for root in (old_root, new_root):
        (root / "project").mkdir(parents=True)
        (root / "project" / "result.mp4").write_bytes(b"video")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(old_root))
    queued = "studio:project"
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(new_root))
    assert delete_uploaded_files([queued]) == ([queued], [])
    assert (old_root / "project" / "result.mp4").is_file()
    assert new_root.is_dir() and not (new_root / "project").exists()


def test_cleanup_tagged_project_refuses_traversal_symlinks_and_files(monkeypatch, tmp_path):
    from utils.media import delete_uploaded_files

    root = tmp_path / "studio"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "preserve").write_bytes(b"keep")
    (root / "safe").mkdir()
    (root / "file").write_bytes(b"keep")
    (root / "linked-outside").symlink_to(outside, target_is_directory=True)
    (root / "linked-inside").symlink_to(root / "safe", target_is_directory=True)
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    invalid = ["studio:", "studio:.", "studio:..", "studio:../outside",
               "studio:" + str(outside), "studio:safe/nested", "studio:safe\\nested",
               "studio:linked-outside", "studio:linked-inside", "studio:file", "relative-project"]
    assert delete_uploaded_files(invalid) == ([], invalid)
    assert (outside / "preserve").is_file() and (root / "file").is_file()
    assert (root / "safe").is_dir()
    assert delete_uploaded_files(["studio:missing"]) == (["studio:missing"], [])


def test_cleanup_legacy_upload_url_remains_file_only(monkeypatch, tmp_path):
    from utils import media

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "x.png").write_bytes(b"image")
    project = uploads / "studio" / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(media, "UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(uploads / "studio"))
    invalid = "/uploads/studio/project"
    assert media.delete_uploaded_files(["/uploads/x.png", invalid]) == (["/uploads/x.png"], [invalid])
    assert not (uploads / "x.png").exists() and project.is_dir()


@pytest.mark.parametrize("action", ["account", "history", "message"])
def test_user_cleanup_runs_in_worker_without_blocking_event_loop(monkeypatch, action):
    import database
    from routers import me
    from routers.peer import ws_manager
    import intent_router
    import mode_switcher
    from utils import media

    paths = ["/uploads/deleted.png", "studio:retry"]
    started = threading.Event()
    release = threading.Event()
    worker_threads = []
    loop_thread = threading.get_ident()

    def slow_cleanup(queued):
        assert queued == paths
        worker_threads.append(threading.get_ident())
        started.set()
        assert release.wait(2), "清理阻塞了事件循环"
        return paths[:1], paths[1:]

    monkeypatch.setattr(media, "delete_uploaded_files", slow_cleanup)
    marked = AsyncMock()
    monkeypatch.setattr(database, "mark_upload_cleanup_done", marked)
    monkeypatch.setattr(database, "delete_account_data", AsyncMock(return_value={"deleted": True, "upload_paths": paths}))
    monkeypatch.setattr(database, "clear_message_history", AsyncMock(return_value=paths))
    monkeypatch.setattr(database, "delete_message_for_user", AsyncMock(return_value={"status": "deleted", "upload_paths": paths}))
    monkeypatch.setattr(intent_router, "clear_user_pending", lambda _user: None)
    monkeypatch.setattr(mode_switcher, "clear_all_user_modes", lambda _user: None)
    monkeypatch.setattr(ws_manager, "disconnect_user", AsyncMock())

    async def exercise():
        if action == "account":
            operation = me.delete_account(me.DeleteAccountRequest(confirmation="owner"), "owner")
        elif action == "history":
            operation = me.clear_history("owner")
        else:
            operation = me.delete_one_message(1, "owner")
        task = asyncio.create_task(operation)
        try:
            async with asyncio.timeout(1):
                while not started.is_set():
                    await asyncio.sleep(0.001)
            assert not task.done()
            assert len(worker_threads) == 1 and worker_threads[0] != loop_thread
        finally:
            release.set()
        response = await task
        if action == "account":
            assert json.loads(response.body) == {"status": "deleted", "deleted_files": 1,
                                                 "file_cleanup_complete": False}
        else:
            assert response == {"status": "cleared" if action == "history" else "deleted"}
        marked.assert_awaited_once_with(paths[:1])

    asyncio.run(exercise())


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="未安装 sqlite3 命令")
@pytest.mark.parametrize("with_studio", [True, False])
def test_backup_optional_studio_archive_exclusions_permissions_retention(tmp_path, with_studio):
    source = tmp_path / "db.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE marker (id INTEGER)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "image.png").write_bytes(b"image")
    (uploads / "unfinished.part").write_bytes(b"partial")
    studio = tmp_path / "studio with space"
    if with_studio:
        project = studio / "project"
        project.mkdir(parents=True)
        (project / "result.mp4").write_bytes(b"video")
        (project / "video.part").write_bytes(b"partial")
        (project / ".hidden").write_bytes(b"private")
        (project / ".pending").mkdir()
        (project / ".pending" / "secret").write_bytes(b"private")
    backups = tmp_path / "backups"
    backups.mkdir()
    stale = backups / "fiona-studio-old.tar.gz"
    stale.write_bytes(b"old")
    os.utime(stale, (time.time() - 20 * 86400,) * 2)
    env = {**os.environ, "FIONA_DB_PATH": str(source), "FIONA_UPLOADS_DIR": str(uploads),
           "FIONA_STUDIO_DIR": str(studio), "FIONA_BACKUP_DIR": str(backups)}
    script = Path(__file__).resolve().parents[2] / "deploy" / "fiona-backup.sh"
    result = subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    archives = list(backups.glob("fiona-studio-*.tar.gz"))
    assert len(archives) == int(with_studio)
    assert not stale.exists()
    if with_studio:
        assert stat.S_IMODE(archives[0].stat().st_mode) == 0o600
        with tarfile.open(archives[0]) as archive:
            files = [member.name for member in archive.getmembers() if member.isfile()]
            assert files == ["studio/project/result.mp4"]
        stamp = archives[0].name.removeprefix("fiona-studio-").removesuffix(".tar.gz")
        assert (backups / f"fiona-db-{stamp}.sqlite3").exists()
        assert (backups / f"fiona-uploads-{stamp}.tar.gz").exists()
    with tarfile.open(next(backups.glob("fiona-uploads-*.tar.gz"))) as archive:
        assert [member.name for member in archive.getmembers() if member.isfile()] == ["uploads/image.png"]
