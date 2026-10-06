"""Local readiness checks, startup exit status, and resilient upload cleanup."""
import asyncio
import os
import sqlite3
import time

import pytest


def test_health_is_public_and_does_not_clear_cookie(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    client.cookies.set("fiona_token", "expired-or-invalid-cookie")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "set-cookie" not in response.headers
    assert client.cookies.get("fiona_token") == "expired-or-invalid-cookie"


def test_health_missing_database_does_not_create_it(client, monkeypatch, tmp_path):
    import database

    missing = tmp_path / "missing ?# database.db"
    monkeypatch.setattr(database, "DB_PATH", str(missing))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["database"]}
    assert not missing.exists()
    assert str(tmp_path) not in response.text
    assert "missing" not in response.text


def test_health_detects_missing_schema_version(client):
    import database
    import exchange_store

    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("DELETE FROM schema_migrations WHERE version = ?", (exchange_store.WORKFLOW_MIGRATION_VERSION,))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["schema"]}
    assert database.DB_PATH not in response.text
    assert exchange_store.WORKFLOW_MIGRATION_VERSION not in response.text


def test_health_detects_missing_users_table(client, monkeypatch, tmp_path):
    import agent_store
    import database
    import exchange_store

    path = tmp_path / "schema-only.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE schema_migrations(version TEXT)")
        db.executemany("INSERT INTO schema_migrations VALUES (?)", [(version,) for version in (
            agent_store.MIGRATION_VERSION, exchange_store.MIGRATION_VERSION,
            exchange_store.OFFICIAL_MIGRATION_VERSION, exchange_store.EXTENDED_OFFICIAL_MIGRATION_VERSION,
            exchange_store.WORKFLOW_MIGRATION_VERSION,
        )])
    monkeypatch.setattr(database, "DB_PATH", str(path))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["schema"]}


def test_health_detects_unwritable_uploads_without_writing(client, monkeypatch):
    import main

    monkeypatch.setattr(main.os, "access", lambda path, _mode: path != main.media.UPLOADS_DIR)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["uploads"]}
    assert main.media.UPLOADS_DIR not in response.text


def test_health_detects_unwritable_database_without_opening_it(client, monkeypatch):
    import main

    monkeypatch.setattr(main.os, "access", lambda path, _mode: path != main.database.DB_PATH)
    monkeypatch.setattr(main.aiosqlite, "connect", lambda *_args, **_kwargs: pytest.fail("只读库不应打开"))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["database"]}
    assert main.database.DB_PATH not in response.text


def test_health_head_is_public_and_retains_invalid_cookie(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    client.cookies.set("fiona_token", "invalid-cookie")
    response = client.head("/health")
    assert response.status_code == 200
    assert response.content == b""
    assert "set-cookie" not in response.headers
    assert client.cookies.get("fiona_token") == "invalid-cookie"


def test_health_total_timeout_cancels_entire_check(client, monkeypatch):
    import main

    cancelled = []
    timeouts = []
    original_wait_for = main.asyncio.wait_for

    async def blocked_check():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    async def shortened_wait_for(coroutine, *, timeout):
        timeouts.append(timeout)
        return await original_wait_for(coroutine, timeout=0.02)

    monkeypatch.setattr(main, "_check_health", blocked_check)
    monkeypatch.setattr(main.asyncio, "wait_for", shortened_wait_for)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["database"]}
    assert cancelled == [True]
    assert len(timeouts) == 1 and 0 < timeouts[0] <= 3


def test_startup_cleans_only_expired_upload_temporaries(monkeypatch, tmp_path):
    import exchange_store
    import main

    old = tmp_path / ".upload_old"
    fresh = tmp_path / ".upload_fresh"
    final = tmp_path / "plaza_preserved.png"
    other_hidden = tmp_path / ".reference_preserved"
    for path in (old, fresh, final, other_hidden):
        path.write_bytes(b"sample")
    old_time = time.time() - 3601
    for path in (old, final, other_hidden):
        os.utime(path, (old_time, old_time))
    nested = tmp_path / ".upload_directory"
    nested.mkdir()
    nested_file = nested / ".upload_nested"
    nested_file.write_bytes(b"sample")
    os.utime(nested_file, (old_time, old_time))
    linked = tmp_path / ".upload_symlink"
    linked.symlink_to(final)

    async def noop():
        pass

    monkeypatch.setattr(main.media, "UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "init_db", noop)
    monkeypatch.setattr(exchange_store, "recover_interrupted_exchanges", noop)
    monkeypatch.setattr(main, "_run_upload_cleanup_once", noop)
    monkeypatch.setattr(main, "create_background_task", lambda coroutine, **_kwargs: coroutine.close())
    monkeypatch.setattr(main, "shutdown_background_tasks", noop)
    monkeypatch.setattr(main, "shutdown_slow_pool", lambda: None)

    async def startup():
        async with main.lifespan(main.app):
            assert not old.exists()
            assert all(path.exists() for path in (fresh, final, other_hidden, nested_file, linked))

    asyncio.run(startup())


@pytest.mark.parametrize("dev_mode,auth_method", [
    ("0", "bearer"), ("0", "cookie"),
    ("1", "bearer"), ("1", "cookie"),
    ("1", "dev_header"), ("1", "dev_query"),
])
@pytest.mark.parametrize("filename", [".upload_original", ".generated_result.png", ".reference_input.png", "%2Eupload_encoded"])
def test_hidden_uploads_require_authentication_before_404(
    client, monkeypatch, tmp_path, dev_mode, auth_method, filename,
):
    from urllib.parse import unquote
    import auth
    import database
    import main

    uploads = tmp_path / "hidden-uploads"
    uploads.mkdir()
    attachment = uploads / unquote(filename)
    attachment.write_bytes(b"private-upload")
    monkeypatch.setattr(main.media, "UPLOADS_DIR", str(uploads))
    static = next(route.app for route in main.app.routes if getattr(route, "name", None) == "uploads")
    monkeypatch.setattr(static, "directory", str(uploads))
    monkeypatch.setattr(static, "all_directories", [str(uploads)])

    monkeypatch.setenv("DEV_MODE", dev_mode)
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    username = "hidden_upload_viewer"
    user = asyncio.run(database.get_or_create_user(username))
    token = auth.create_token(username, user["session_version"])
    for method, query in (("GET", ""), ("HEAD", ""), ("GET", "?download=1")):
        path = "/uploads/" + filename + query
        # An absent or invalid session keeps the original 401/Cookie behavior,
        # including loopback requests that can otherwise bypass DEV uploads auth.
        for cookie in (None, "invalid-cookie"):
            client.cookies.clear()
            if cookie:
                client.cookies.set("fiona_token", cookie, domain="127.0.0.1", path="/")
            response = client.request(method, path)
            assert response.status_code == 401
            assert 'fiona_token=""' in response.headers["set-cookie"]
            assert "Max-Age=0" in response.headers["set-cookie"]
            assert "Path=/" in response.headers["set-cookie"]
            assert client.cookies.get("fiona_token") is None

        headers = {}
        client.cookies.set("fiona_token", "invalid-cookie", domain="127.0.0.1", path="/")
        if auth_method == "bearer":
            headers["Authorization"] = "Bearer " + token
        elif auth_method == "cookie":
            client.cookies.set("fiona_token", token, domain="127.0.0.1", path="/")
        elif auth_method == "dev_header":
            headers["X-Dev-User"] = username
        else:
            path += ("&" if query else "?") + "dev_user=" + username
        response = client.request(method, path, headers=headers)
        assert response.status_code == 404
        assert "set-cookie" not in response.headers
        assert client.cookies.get("fiona_token") == (token if auth_method == "cookie" else "invalid-cookie")
        assert attachment.exists()


def test_health_reads_upload_directory_at_request_time(client, monkeypatch, tmp_path):
    from utils import media

    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path / "missing-uploads"))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["uploads"]}
    assert str(tmp_path) not in response.text


def test_health_opens_database_with_rw_uri_and_bounded_timeout(client, monkeypatch):
    import main

    original_connect = main.aiosqlite.connect
    calls = []

    def connect(path, **kwargs):
        calls.append((path, kwargs))
        return original_connect(path, **kwargs)

    monkeypatch.setattr(main.aiosqlite, "connect", connect)
    assert client.get("/health").status_code == 200
    assert len(calls) == 1
    path, kwargs = calls[0]
    assert path.startswith("file:") and path.endswith("?mode=rw")
    assert kwargs["uri"] is True
    assert 0 < kwargs["timeout"] <= 1


@pytest.mark.parametrize("started, exit_code", [(False, 3), (True, None)])
def test_run_exits_nonzero_only_if_server_never_started(monkeypatch, started, exit_code):
    import run

    configs = []

    class Server:
        def __init__(self, config):
            configs.append(config)
            self.started = started

        async def serve(self):
            pass

    monkeypatch.setattr(run.uvicorn, "Server", Server)
    if exit_code is not None:
        with pytest.raises(SystemExit) as error:
            asyncio.run(run.main())
        assert error.value.code == exit_code
    else:
        asyncio.run(run.main())
    assert configs[0].host == "127.0.0.1"
    assert configs[0].port == 8000


def test_upload_cleanup_continues_after_error_and_propagates_cancellation(monkeypatch, capsys):
    import main

    calls = []

    async def sleep(_interval):
        pass

    async def cleanup():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("private-exception-detail")
        if len(calls) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(main, "_run_upload_cleanup_once", cleanup)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._run_upload_cleanup_periodically())
    assert len(calls) == 3
    output = capsys.readouterr().out
    assert "[cleanup]" in output and "failed type=RuntimeError" in output
    assert "private-exception-detail" not in output
