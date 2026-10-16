"""Offline HTTP and additive storage contracts for local watch."""
import asyncio
import hashlib
import json
import logging
import socket
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace as NS
import pytest

@pytest.fixture(scope="module", autouse=True)
def module_offline():
    def forbidden(*args, **kwargs):
        raise AssertionError("socket and DNS forbidden")
    with pytest.MonkeyPatch.context() as patch:
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
            patch.setattr(socket, name, forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        for name in ("bind", "listen", "sendto"):
            original = getattr(socket.socket, name)
            def guarded(sock, *args, _original=original, **kwargs):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    forbidden()
                return _original(sock, *args, **kwargs)
            patch.setattr(socket.socket, name, guarded)
        yield

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    from services import local_watch
    from routers import local_watch as router
    monkeypatch.setenv("FIONA_LOCAL_WATCH", "1")
    router._windows.clear()
    router._observation_rates.clear()
    local_watch._rule_locks.clear()
    import rate_limit
    rate_limit.limiter._storage.reset()
    def forbidden(*args, **kwargs):
        raise AssertionError("model must be explicitly stubbed")
    monkeypatch.setattr(local_watch, "QWEN_CLIENT", NS(with_options=forbidden))
    monkeypatch.setattr(local_watch.byok_client.anthropic, "Anthropic", forbidden)

def bearer(token):
    return {"Authorization": "Bearer " + token}

def device(client, user="smoke_tester"):
    response = client.post("/local-watch/devices", headers={"X-Dev-User": user}, json={"name": "Mac"})
    assert response.status_code == 200, response.text
    return response.json()

def rule(client, user="smoke_tester", **changes):
    body = {"name": "开会", "app_match": "WeChat", "title_match": "", "kind": "keyword", "params": {"keywords": ["开会"]}}
    body.update(changes)
    response = client.post("/local-watch/rules", headers={"X-Dev-User": user}, json=body)
    assert response.status_code == 200, response.text
    return response.json()

def observe(client, token, rule_id, lines=None):
    return client.post("/local-watch/observations", headers=bearer(token), json={"rule_id": rule_id, "new_lines": ["张三今晚开会"] if lines is None else lines, "captured_at": datetime.now(timezone.utc).isoformat()})

def rows(sql, parameters=()):
    import database
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, parameters)]

def test_devices_once_hashed_revoked_limit_and_isolation(client, dev_headers):
    first = device(client)
    token = first["token"]
    assert len(bytes.fromhex(token)) == 32
    stored = rows("SELECT * FROM watch_devices")[0]
    assert stored["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(stored)
    assert "token" not in json.dumps(client.get("/local-watch/devices", headers=dev_headers).json())
    assert client.post("/local-watch/heartbeat", headers=bearer(token), json={"windows": []}).status_code == 200
    assert rows("SELECT last_seen_at FROM watch_devices")[0]["last_seen_at"]
    device(client); device(client)
    assert client.post("/local-watch/devices", headers=dev_headers, json={"name": "fourth"}).status_code == 400
    other = device(client, "someone_else")
    assert client.delete(f"/local-watch/devices/{other['id']}", headers=dev_headers).status_code == 404
    mine = rule(client)
    rule(client, "someone_else")
    heartbeat = client.post("/local-watch/heartbeat", headers=bearer(other["token"]), json={"windows": []}).json()
    assert all(item["id"] != mine["id"] for item in heartbeat["rules"])
    assert client.post("/local-watch/heartbeat", headers=bearer("wrong"), json={"windows": []}).status_code == 401
    assert client.delete(f"/local-watch/devices/{first['id']}", headers=dev_headers).status_code == 204
    assert client.post("/local-watch/heartbeat", headers=bearer(token), json={"windows": []}).status_code == 401
    assert device(client)["token"]

def test_rules_crud_limit_and_isolation(client, dev_headers):
    first = rule(client)
    assert first["params"] == {"keywords": ["开会"]}
    assert first["interval_seconds"] == 3 and first["cooldown_seconds"] == 60
    response = client.patch(f"/local-watch/rules/{first['id']}", headers=dev_headers, json={"enabled": False, "name": "改名"})
    assert response.status_code == 200 and response.json()["enabled"] is False
    foreign = {"X-Dev-User": "someone_else"}
    assert client.patch(f"/local-watch/rules/{first['id']}", headers=foreign, json={"enabled": True}).status_code == 404
    assert client.delete(f"/local-watch/rules/{first['id']}", headers=foreign).status_code == 404
    assert client.get("/local-watch/rules", headers=foreign).json() == []
    for i in range(19): rule(client, name=str(i))
    assert len(client.get("/local-watch/rules", headers=dev_headers).json()) == 20
    assert client.post("/local-watch/rules", headers=dev_headers, json={"name": "overflow", "app_match": "x", "kind": "keyword", "params": {"keywords": ["a"]}}).status_code == 400
    assert client.delete(f"/local-watch/rules/{first['id']}", headers=dev_headers).status_code == 204
    rule(client)

@pytest.mark.parametrize("changes", [
    {"name": ""}, {"name": "a" * 31}, {"app_match": "", "title_match": ""}, {"app_match": "a" * 61}, {"title_match": "a" * 61},
    {"interval_seconds": 1}, {"interval_seconds": 61}, {"interval_seconds": True}, {"cooldown_seconds": 9}, {"cooldown_seconds": 3601},
    {"enabled": 1}, {"kind": "other"}, {"params": {"keywords": []}}, {"params": {"keywords": ["a"] * 11}}, {"params": {"keywords": [""]}},
    {"params": {"keywords": ["a" * 21]}}, {"params": {"keywords": [42]}}, {"params": {"keywords": ["a"], "extra": "x"}},
    {"kind": "number", "params": {"label": "", "op": ">", "threshold": 1}}, {"kind": "number", "params": {"label": "a" * 21, "op": ">", "threshold": 1}},
    {"kind": "number", "params": {"label": "价格", "op": "=", "threshold": 1}}, {"kind": "number", "params": {"label": "价格", "op": ">", "threshold": "1"}},
    {"kind": "number", "params": {"label": "价格", "op": ">", "threshold": True}}, {"kind": "number", "params": {"label": "价格", "op": ">", "threshold": None}},
    {"kind": "ai", "params": {"condition": "a"}}, {"kind": "ai", "params": {"condition": "a" * 201}}, {"kind": "ai", "params": {"condition": "提醒", "model": "other"}},
    {"kind": "ai", "params": {"condition": "提醒", "model": "claude"}}, {"extra": "x"},
])
def test_rule_validation(client, dev_headers, changes):
    body = {"name": "测试", "app_match": "WeChat", "kind": "keyword", "params": {"keywords": ["test"]}}
    body.update(changes)
    assert client.post("/local-watch/rules", headers=dev_headers, json=body).status_code in {400, 422}

@pytest.mark.parametrize("kind,params", [("keyword", {"keywords": ["a" * 20] * 10}), ("number", {"label": "a" * 20, "op": ">=", "threshold": -1.5}), ("ai", {"condition": "a" * 200})])
def test_valid_boundaries_patch_validation(client, dev_headers, kind, params):
    item = rule(client, name="a" * 30, app_match="a" * 60, kind=kind, params=params, interval_seconds=60, cooldown_seconds=3600)
    assert client.patch(f"/local-watch/rules/{item['id']}", headers=dev_headers, json={"kind": "number", "params": {"keywords": ["x"]}}).status_code in {400, 422}
    assert client.patch(f"/local-watch/rules/{item['id']}", headers=dev_headers, json={"app_match": ""}).status_code in {400, 422}

def test_heartbeat_fields_isolation_expiration_limit(client, dev_headers, monkeypatch):
    from routers import local_watch as router
    first = device(client)
    item = rule(client)
    rule(client, enabled=False)
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    response = client.post("/local-watch/heartbeat", headers=bearer(first["token"]), json={"windows": [{"window_id": 7, "app_name": "WeChat", "bundle_id": "com.wechat", "title": "文" * 90}]})
    assert response.status_code == 200
    assert response.json() == {"rules": [{"id": item["id"], "app_match": "WeChat", "title_match": "", "interval_seconds": 3}]}
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get("/local-watch/windows", headers=dev_headers).json() == [{"app_name": "WeChat", "bundle_id": "com.wechat", "title": "文" * 80}]
    assert client.get("/local-watch/windows", headers={"X-Dev-User": "someone_else"}).json() == []
    assert client.post("/local-watch/heartbeat", headers=bearer(first["token"]), json={"windows": [{}] * 201}).status_code in {400, 422}
    clock[0] = 400.1
    assert client.get("/local-watch/windows", headers=dev_headers).json() == []

def test_observations_ownership_size_timestamp_device_rate(client):
    first, second = device(client), device(client)
    foreign, disabled, mine = rule(client, "someone_else"), rule(client, enabled=False), rule(client)
    for identifier in (99999, foreign["id"], disabled["id"]):
        assert observe(client, first["token"], identifier).status_code == 404
    for lines in (["xx"] * 51, ["x" * 4001], [42], []):
        assert observe(client, first["token"], mine["id"], lines).status_code in {400, 422}
    bad = client.post("/local-watch/observations", headers=bearer(first["token"]), json={"rule_id": mine["id"], "new_lines": ["xx"], "captured_at": "no"})
    assert bad.status_code in {400, 422}
    from routers import local_watch as router
    router._observation_rates.clear()
    for _ in range(60): assert observe(client, first["token"], mine["id"], ["no match"]).status_code == 200
    response = observe(client, first["token"], mine["id"])
    assert response.status_code == 429 and response.headers["cache-control"] == "private, no-store"
    assert observe(client, second["token"], mine["id"], ["no match"]).status_code == 200

def test_alert_body_storage_fallback_billing_and_debug_privacy(client, monkeypatch, caplog):
    import database
    import agent_store
    from services import chat_service
    async def forbidden(*args, **kwargs): raise AssertionError("unexpected chat side effect")
    monkeypatch.setattr(chat_service, "extract_and_update", forbidden)
    monkeypatch.setattr(chat_service, "detect_matches_and_save", forbidden)
    monkeypatch.setattr(database, "reserve_strawberries", forbidden)
    first = device(client)
    target = asyncio.run(agent_store.create_conversation("smoke_tester", "提醒"))["id"]
    item = rule(client, conversation_id=target)
    before = asyncio.run(database.get_strawberry_balance("smoke_tester"))
    caplog.set_level(logging.DEBUG)
    sensitive = "开会SECRET_LOCAL_OCR_VALUE"
    response = observe(client, first["token"], item["id"], [sensitive])
    assert response.status_code == 200 and response.json()["alert"] is True
    messages = rows("SELECT id,content,conversation_id FROM messages WHERE role='assistant'")
    assert messages[-1]["content"] == f"【本机提醒 · 开会】命中『开会』：{sensitive}（规则：开会）"
    assert messages[-1]["conversation_id"] == target
    alerts = rows("SELECT * FROM watch_alerts")
    assert alerts[-1]["message_id"] == messages[-1]["id"] and alerts[-1]["conversation_id"] == target
    assert asyncio.run(database.get_strawberry_balance("smoke_tester")) == before
    assert sensitive not in caplog.text and alerts[-1]["summary"] not in caplog.text
    for event in rows("SELECT * FROM events WHERE event_type='local_watch'"):
        assert sensitive not in json.dumps(event) and alerts[-1]["summary"] not in json.dumps(event)
        assert set(json.loads(event["payload"])) <= {"rule_id", "kind", "alert", "elapsed_ms", "exception_type"}
    caplog.clear()
    fallback = rule(client, conversation_id="missing")
    assert observe(client, first["token"], fallback["id"], [sensitive]).json()["alert"] is True
    default = rows("SELECT id FROM conversations WHERE owner_username='smoke_tester' AND is_default=1")[0]["id"]
    assert rows("SELECT conversation_id FROM watch_alerts ORDER BY id DESC")[0]["conversation_id"] == default
    assert sensitive not in caplog.text

def test_alerts_after_limit_fields_isolation(client, dev_headers):
    import database
    mine, other = rule(client), rule(client, "someone_else")
    with sqlite3.connect(database.DB_PATH) as connection:
        for i in range(55): connection.execute("INSERT INTO watch_alerts(username,rule_id,summary,message_id,conversation_id) VALUES(?,?,?,?,?)", ("smoke_tester", mine["id"], str(i), i, "target"))
        connection.execute("INSERT INTO watch_alerts(username,rule_id,summary,message_id,conversation_id) VALUES(?,?,?,?,?)", ("someone_else", other["id"], "private", 1, "other"))
    alerts = client.get("/local-watch/alerts?after=2", headers=dev_headers).json()
    assert len(alerts) == 50 and alerts[0]["id"] == 3 and alerts[-1]["id"] == 52
    assert set(alerts[0]) == {"id", "rule_name", "summary", "created_at", "conversation_id", "message_id", "content"}
    assert len(client.get("/local-watch/alerts?after=52", headers=dev_headers).json()) == 3
    assert len(client.get("/local-watch/alerts", headers={"X-Dev-User": "someone_else"}).json()) == 1

def test_switch_404_all_endpoints_unauthenticated(client, monkeypatch):
    monkeypatch.setenv("FIONA_LOCAL_WATCH", "0")
    for method, suffix in [("POST", "/devices"), ("GET", "/devices"), ("DELETE", "/devices/1"), ("GET", "/rules"), ("POST", "/rules"), ("PATCH", "/rules/1"), ("DELETE", "/rules/1"), ("GET", "/windows"), ("GET", "/alerts"), ("POST", "/heartbeat"), ("POST", "/observations")]:
        response = client.request(method, "/local-watch" + suffix)
        assert response.status_code == 404 and response.headers["cache-control"] == "private, no-store"

def test_old_database_additive_startup_preserves_data(tmp_path, monkeypatch):
    import database
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as connection:
        connection.execute("CREATE TABLE preserved(id INTEGER PRIMARY KEY,value TEXT)")
        connection.execute("INSERT INTO preserved VALUES(1,'keep exactly')")
    monkeypatch.setattr(database, "DB_PATH", str(old))
    asyncio.run(database.init_db())
    with sqlite3.connect(old) as connection:
        assert connection.execute("SELECT * FROM preserved").fetchall() == [(1, "keep exactly")]
        assert {"watch_devices", "watch_rules", "watch_alerts"} <= {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def test_account_deletion_cleans_watch_tables_preserves_other(client, dev_headers):
    first, mine = device(client), rule(client)
    device(client, "someone_else"); other = rule(client, "someone_else")
    assert observe(client, first["token"], mine["id"]).json()["alert"] is True
    assert client.request("DELETE", "/account", headers=dev_headers, json={"confirmation": "smoke_tester"}).status_code == 200
    for table in ("watch_devices", "watch_rules", "watch_alerts"):
        assert rows(f"SELECT * FROM {table} WHERE username='smoke_tester'") == []
    assert len(rows("SELECT * FROM watch_devices WHERE username='someone_else'")) == 1
    assert rows("SELECT id FROM watch_rules WHERE username='someone_else'")[0]["id"] == other["id"]

@pytest.mark.parametrize("changes", [{"kind": []}, {"kind": {}}, {"kind": None}, {"kind": "number", "params": {"label": "价格", "op": [], "threshold": 1}}, {"kind": "number", "params": {"label": "价格", "op": {}, "threshold": 1}}, {"kind": "ai", "params": {"condition": "提醒", "model": []}}, {"kind": "ai", "params": {"condition": "提醒", "model": {}}}])
def test_compound_enum_values_rejected(client, dev_headers, changes):
    body = {"name": "测试", "app_match": "WeChat", "kind": "keyword", "params": {"keywords": ["test"]}}
    body.update(changes)
    assert client.post("/local-watch/rules", headers=dev_headers, json=body).status_code == 422

def test_alert_heading_uses_actual_window_app_or_rule_name(client):
    first = device(client)
    item = rule(client, app_match="term", name="完成规则", params={"keywords": ["done"]})
    assert observe(client, first["token"], item["id"], ["done one"]).json()["alert"] is True
    assert rows("SELECT content FROM messages ORDER BY id DESC")[0]["content"].startswith("【本机提醒 · 完成规则】")
    second = rule(client, app_match="term", name="完成规则2", params={"keywords": ["done"]})
    assert client.post("/local-watch/heartbeat", headers=bearer(first["token"]), json={"windows": [{"app_name": "Terminal", "bundle_id": "com.apple.Terminal", "title": "shell"}]}).status_code == 200
    assert observe(client, first["token"], second["id"], ["done two"]).json()["alert"] is True
    assert rows("SELECT content FROM messages ORDER BY id DESC")[0]["content"].startswith("【本机提醒 · Terminal】")

def test_claude_rule_enabled_byok_and_patch_disable_after_unavailable(client, dev_headers, monkeypatch):
    from routers import local_watch as router
    async def enabled(user):
        return {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "offline-key", "status": "ok"}
    monkeypatch.setattr(router.byok_store, "get_internal_config", enabled)
    item = rule(client, kind="ai", params={"condition": "出错提醒", "model": "claude"})
    async def missing(user): return None
    monkeypatch.setattr(router.byok_store, "get_internal_config", missing)
    assert client.patch(f"/local-watch/rules/{item['id']}", headers=dev_headers, json={"enabled": False}).status_code == 200
    assert client.patch(f"/local-watch/rules/{item['id']}", headers=dev_headers, json={"enabled": True}).status_code == 422

def test_old_real_user_database_restarts_additive_and_idempotent(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "old-user.db"))
    asyncio.run(database.init_db())
    asyncio.run(database.get_or_create_user("legacy_user"))
    asyncio.run(database.add_strawberry("legacy_user", 123))
    asyncio.run(database.save_message("legacy_user", "user", "旧聊天不变"))
    before_users = rows("SELECT * FROM users")
    before_messages = rows("SELECT * FROM messages")
    with sqlite3.connect(database.DB_PATH) as connection:
        for table in ("watch_devices", "watch_rules", "watch_alerts"):
            connection.execute(f"DROP TABLE {table}")
    asyncio.run(database.init_db())
    asyncio.run(database.init_db())
    assert rows("SELECT * FROM users") == before_users
    assert rows("SELECT * FROM messages") == before_messages
    for table in ("watch_devices", "watch_rules", "watch_alerts"):
        assert rows(f"SELECT * FROM {table}") == []

@pytest.mark.parametrize("method,path,body", [("DELETE", "/devices/", None), ("PATCH", "/rules/", {"enabled": True}), ("DELETE", "/rules/", None), ("GET", "/alerts?after=", None)])
def test_ids_outside_sqlite_range_rejected(client, dev_headers, method, path, body):
    response = client.request(method, "/local-watch" + path + str(2**64), headers=dev_headers, json=body)
    assert response.status_code == 422
