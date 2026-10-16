"""R2 HTTP/storage regressions, with sockets, DNS and model clients disabled."""
import asyncio
import hashlib
import socket
import sqlite3
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module", autouse=True)
def offline():
    def forbidden(*args, **kwargs):
        raise AssertionError("R2 tests forbid network and DNS")

    with pytest.MonkeyPatch.context() as patch:
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
            patch.setattr(socket, name, forbidden)
        for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
            original = getattr(socket.socket, name)

            def guarded(sock, *args, _original=original, **kwargs):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    forbidden()
                return _original(sock, *args, **kwargs)

            patch.setattr(socket.socket, name, guarded)
        yield


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    from routers import local_watch as router
    from services import local_watch as service

    monkeypatch.setenv("FIONA_LOCAL_WATCH", "1")
    for name in ("_windows", "_capture_states", "_recent_heartbeats", "_observation_rates", "_heartbeat_rates", "_authentication_failure_rates"):
        getattr(router, name, {}).clear()
    service._rule_locks.clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("R2 models must be stubbed")

    monkeypatch.setattr(service, "QWEN_CLIENT", SimpleNamespace(with_options=forbidden))
    monkeypatch.setattr(service.byok_client.anthropic, "Anthropic", forbidden)


def device(client, username="smoke_tester"):
    result = client.post("/local-watch/devices", headers={"X-Dev-User": username}, json={"name": "R2 Mac"})
    assert result.status_code == 200, result.text
    return result.json()


def rule(client, username="smoke_tester", **changes):
    payload = {"name": "老板提醒", "app_match": "WeChat", "kind": "keyword", "params": {"keywords": ["开会"]}}
    payload.update(changes)
    result = client.post("/local-watch/rules", headers={"X-Dev-User": username}, json=payload)
    assert result.status_code == 200, result.text
    return result.json()


def bearer(token):
    return {"Authorization": "Bearer " + token}


def heartbeat(client, token, **changes):
    payload = {"windows": []}
    payload.update(changes)
    return client.post("/local-watch/heartbeat", headers=bearer(token), json=payload)


def observe(client, token, identifier):
    return client.post("/local-watch/observations", headers=bearer(token), json={
        "rule_id": identifier, "new_lines": ["张三今晚开会"], "captured_at": "2026-10-11T12:00:00Z",
    })


def sql_rows(statement, parameters=()):
    import database
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(statement, parameters)]


def record_execute(monkeypatch):
    import aiosqlite
    statements = []
    commits = []
    original_execute = aiosqlite.Connection.execute
    original_commit = aiosqlite.Connection.commit

    def execute(connection, sql, *args, **kwargs):
        statements.append(sql.strip().upper())
        return original_execute(connection, sql, *args, **kwargs)

    async def commit(connection):
        commits.append(True)
        return await original_commit(connection)

    monkeypatch.setattr(aiosqlite.Connection, "execute", execute)
    monkeypatch.setattr(aiosqlite.Connection, "commit", commit)
    return statements, commits


@pytest.mark.parametrize("path", ["heartbeat", "observations"])
def test_forged_bearer_authentication_never_takes_write_lock_or_updates(client, monkeypatch, path):
    statements, commits = record_execute(monkeypatch)
    result = client.post("/local-watch/" + path, headers=bearer("invented-token"), content="{broken")
    assert result.status_code == 401
    assert any(sql.startswith("SELECT") for sql in statements)
    assert not any(sql.startswith(("BEGIN", "UPDATE", "INSERT", "DELETE")) for sql in statements)
    assert commits == []
    assert result.headers["cache-control"] == "private, no-store"


def test_forged_bearer_can_be_rejected_while_other_connection_holds_write_lock(client):
    import database
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("BEGIN IMMEDIATE")
        result = heartbeat(client, "invented-while-write-locked")
        assert result.status_code == 401
        connection.rollback()


def test_valid_device_last_seen_updated_once_then_read_only_within_sixty_seconds(client, monkeypatch):
    item = device(client)
    statements, commits = record_execute(monkeypatch)
    for _ in range(5):
        assert heartbeat(client, item["token"]).status_code == 200
    assert sum(sql.startswith("UPDATE WATCH_DEVICES") for sql in statements) == 1
    assert len(commits) == 1
    assert not any(sql.startswith("BEGIN IMMEDIATE") for sql in statements)
    assert sql_rows("SELECT last_seen_at FROM watch_devices WHERE id=?", (item["id"],))[0]["last_seen_at"]


def test_last_seen_uses_database_clock_and_refreshes_only_when_sixty_seconds_elapsed(client, monkeypatch):
    import database
    item = device(client)
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE watch_devices SET last_seen_at=datetime('now','-30 seconds') WHERE id=?", (item["id"],))
    statements, commits = record_execute(monkeypatch)
    assert heartbeat(client, item["token"]).status_code == 200
    assert not any(sql.startswith("UPDATE WATCH_DEVICES") for sql in statements)
    assert commits == []
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE watch_devices SET last_seen_at=datetime('now','-61 seconds') WHERE id=?", (item["id"],))
    assert heartbeat(client, item["token"]).status_code == 200
    assert sum(sql.startswith("UPDATE WATCH_DEVICES") for sql in statements) == 1
    assert len(commits) == 1


def test_concurrent_authentication_does_not_refresh_database_value_more_than_once(client):
    import database
    item = device(client)
    token_hash = hashlib.sha256(item["token"].encode()).hexdigest()
    events = []
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("CREATE TABLE r2_touch_events(id INTEGER)")
        connection.execute("CREATE TRIGGER r2_touch AFTER UPDATE OF last_seen_at ON watch_devices BEGIN INSERT INTO r2_touch_events VALUES(NEW.id); END")

    async def authenticate_all():
        return await asyncio.gather(*(database.authenticate_watch_device_throttled(token_hash) for _ in range(12)))

    events = asyncio.run(authenticate_all())
    assert all(value == {"id": item["id"], "username": "smoke_tester"} for value in events)
    assert sql_rows("SELECT COUNT(*) AS count FROM r2_touch_events")[0]["count"] == 1


def test_throttled_authentication_rejects_revoked_device_and_deleted_owner_without_writes(client, monkeypatch):
    import database
    first, second = device(client), device(client, "someone_else")
    assert heartbeat(client, first["token"]).status_code == 200
    assert heartbeat(client, second["token"]).status_code == 200
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE watch_devices SET revoked=1 WHERE id=?", (first["id"],))
        connection.execute("DELETE FROM users WHERE username='someone_else'")
    statements, commits = record_execute(monkeypatch)
    assert heartbeat(client, first["token"]).status_code == 401
    assert heartbeat(client, second["token"]).status_code == 401
    assert not any(sql.startswith(("BEGIN", "UPDATE")) for sql in statements)
    assert commits == []


@pytest.mark.parametrize("path", ["heartbeat", "observations"])
def test_all_authentication_failures_count_by_real_client_ip_before_body_or_rule_validation(client, monkeypatch, path):
    from routers import local_watch as router
    from starlette.requests import Request
    # A non-trusted peer cannot evade its real-IP counter by forging XFF.
    monkeypatch.setattr(client._transport, "client", ("198.51.100.40", 50000))
    failures = [{}, {"Authorization": "Basic invalid"}, bearer(""), bearer("invented"), bearer("x" * 300)]
    for index in range(30):
        headers = {**failures[index % len(failures)], "X-Forwarded-For": f"192.0.2.{index}"}
        result = client.post("/local-watch/" + path, headers=headers, content="{invalid JSON")
        assert result.status_code == 401, (index, result.text)

    async def forbidden(*args, **kwargs):
        raise AssertionError("rate limited requests cannot parse body or query rules")

    monkeypatch.setattr(Request, "json", forbidden)
    monkeypatch.setattr(router.database, "get_watch_rule", forbidden)
    monkeypatch.setattr(router.database, "list_watch_rules", forbidden)
    result = client.post("/local-watch/" + path, headers=bearer("invented"), content="{invalid")
    assert result.status_code == 429
    assert 1 <= int(result.headers["retry-after"]) <= 61
    assert result.headers["cache-control"] == "private, no-store"


def test_authentication_failure_window_resets_after_sixty_seconds(client, monkeypatch):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    for _ in range(30):
        assert heartbeat(client, "invented").status_code == 401
    assert heartbeat(client, "invented").status_code == 429
    clock[0] = 160.0
    assert heartbeat(client, "invented").status_code == 401


def test_authentication_failure_limit_is_independent_per_client_ip(client):
    for _ in range(30):
        assert heartbeat(client, "invented").status_code == 401
    assert heartbeat(client, "invented").status_code == 429
    original = client._transport.client
    try:
        client._transport.client = ("198.51.100.40", 50000)
        assert heartbeat(client, "invented").status_code == 401
    finally:
        client._transport.client = original


@pytest.mark.parametrize("invalid_payload,status", [("not JSON", 422), ("{}", 422), ('{"rule_id":999,"new_lines":["xx"],"captured_at":"2026-10-11T12:00:00Z"}', 404)])
def test_invalid_observations_count_before_validation_and_lookup(client, monkeypatch, invalid_payload, status):
    from routers import local_watch as router
    from starlette.requests import Request
    item = device(client)
    for _ in range(60):
        result = client.post("/local-watch/observations", headers=bearer(item["token"]), content=invalid_payload)
        assert result.status_code == status

    async def forbidden(*args, **kwargs):
        raise AssertionError("full observation bucket must short circuit parsing and rule lookup")

    monkeypatch.setattr(Request, "json", forbidden)
    monkeypatch.setattr(router.database, "get_watch_rule", forbidden)
    result = client.post("/local-watch/observations", headers=bearer(item["token"]), content=invalid_payload)
    assert result.status_code == 429
    assert result.headers["cache-control"] == "private, no-store"
    assert int(result.headers["retry-after"]) > 0


def test_observation_rate_limit_is_per_device_and_resets_after_sixty_seconds(client, monkeypatch):
    from routers import local_watch as router
    first, second = device(client), device(client)
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    for _ in range(60):
        assert observe(client, first["token"], 999).status_code == 404
    assert observe(client, first["token"], 999).status_code == 429
    assert observe(client, second["token"], 999).status_code == 404
    clock[0] = 160.0
    assert observe(client, first["token"], 999).status_code == 404


@pytest.mark.parametrize("payload,status", [('not JSON', 422), ('{"windows":[]}', 200)])
def test_heartbeat_maximum_ten_per_device_before_parsing_and_rule_queries(client, monkeypatch, payload, status):
    from routers import local_watch as router
    from starlette.requests import Request
    first, second = device(client), device(client)
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    for _ in range(10):
        result = client.post("/local-watch/heartbeat", headers=bearer(first["token"]), content=payload)
        assert result.status_code == status

    async def forbidden(*args, **kwargs):
        raise AssertionError("full heartbeat bucket must short circuit parsing and rule lookup")

    with monkeypatch.context() as patch:
        patch.setattr(Request, "json", forbidden)
        patch.setattr(router.database, "list_watch_rules", forbidden)
        result = client.post("/local-watch/heartbeat", headers=bearer(first["token"]), content=payload)
        assert result.status_code == 429
        assert result.headers["cache-control"] == "private, no-store"
        assert int(result.headers["retry-after"]) > 0
    assert heartbeat(client, second["token"]).status_code == 200
    clock[0] = 160.0
    assert heartbeat(client, first["token"]).status_code == 200


def test_database_scope_does_not_reuse_rate_buckets_between_different_databases(client, monkeypatch, tmp_path):
    import database
    item = device(client)
    for _ in range(10):
        assert heartbeat(client, item["token"]).status_code == 200
    assert heartbeat(client, item["token"]).status_code == 429
    for _ in range(30):
        assert heartbeat(client, "invalid").status_code == 401
    assert heartbeat(client, "invalid").status_code == 429
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "second.db"))
    asyncio.run(database.init_db())
    newer = device(client)
    assert newer["id"] == item["id"]
    assert heartbeat(client, newer["token"]).status_code == 200
    assert heartbeat(client, "invalid").status_code == 401


def test_alert_content_is_exact_stored_message_after_application_label_rule_rename_and_delete(client, dev_headers):
    item = device(client)
    watched = rule(client)
    assert heartbeat(client, item["token"], windows=[{"app_name": "微信 WeChat", "bundle_id": "com.wechat", "title": "会议"}]).status_code == 200
    assert observe(client, item["token"], watched["id"]).json()["alert"] is True
    message = sql_rows("SELECT id,content,conversation_id FROM messages WHERE role='assistant'")[0]
    assert message["content"].startswith("【本机提醒 · 微信 WeChat】")
    assert client.patch(f"/local-watch/rules/{watched['id']}", headers=dev_headers, json={"name": "新规则名"}).status_code == 200
    renamed = client.get("/local-watch/alerts", headers=dev_headers).json()[0]
    assert renamed["content"] == message["content"]
    assert renamed["rule_name"] == "新规则名"
    assert client.delete(f"/local-watch/rules/{watched['id']}", headers=dev_headers).status_code == 204
    deleted = client.get("/local-watch/alerts", headers=dev_headers).json()[0]
    assert deleted["content"] == message["content"]
    assert deleted["rule_name"] == "已删除规则"
    assert deleted["message_id"] == message["id"] and deleted["conversation_id"] == message["conversation_id"]


@pytest.mark.parametrize("changed_field", ["username", "conversation_id", "role", "missing"])
def test_alert_content_join_never_discloses_another_owner_conversation_or_non_assistant_message(client, dev_headers, changed_field):
    import database
    item = device(client)
    watched = rule(client)
    assert observe(client, item["token"], watched["id"]).json()["alert"] is True
    alert = sql_rows("SELECT * FROM watch_alerts")[0]
    with sqlite3.connect(database.DB_PATH) as connection:
        if changed_field == "missing":
            connection.execute("DELETE FROM messages WHERE id=?", (alert["message_id"],))
        else:
            value = {"username": "someone_else", "conversation_id": "wrong-target", "role": "user"}[changed_field]
            connection.execute(f"UPDATE messages SET {changed_field}=? WHERE id=?", (value, alert["message_id"]))
    response = client.get("/local-watch/alerts", headers=dev_headers)
    assert response.status_code == 200
    assert response.json()[0]["content"] == ""
    assert len(response.json()) == 1


def test_three_watch_indexes_are_added_to_existing_database_idempotently_without_changing_data(client):
    import database
    watched = rule(client)
    device(client)
    before = sql_rows("SELECT * FROM watch_rules")
    with sqlite3.connect(database.DB_PATH) as connection:
        expected = {("username",), ("username", "id"), ("rule_id", "id")}
        actual = set()
        for table in ("watch_rules", "watch_alerts"):
            for row in connection.execute(f"PRAGMA index_list({table})"):
                actual.add(tuple(value[2] for value in connection.execute(f'PRAGMA index_info("{row[1]}")')))
        assert expected <= actual
        for table in ("watch_rules", "watch_alerts"):
            for row in connection.execute(f"PRAGMA index_list({table})").fetchall():
                connection.execute(f'DROP INDEX "{row[1]}"')
    asyncio.run(database.init_db())
    asyncio.run(database.init_db())
    assert sql_rows("SELECT * FROM watch_rules") == before
    assert sql_rows("SELECT id FROM watch_rules")[0]["id"] == watched["id"]
    with sqlite3.connect(database.DB_PATH) as connection:
        actual = set()
        for table in ("watch_rules", "watch_alerts"):
            for row in connection.execute(f"PRAGMA index_list({table})"):
                actual.add(tuple(value[2] for value in connection.execute(f'PRAGMA index_info("{row[1]}")')))
        assert expected <= actual
