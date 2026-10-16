"""Main-app boundary checks, with no listening server or outbound network."""
import asyncio
import socket
import sqlite3

import pytest


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def block(original):
        def guarded(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise AssertionError("Local watch integration tests forbid internet sockets")
            return original(sock, *args, **kwargs)
        return guarded

    def no_dns(*args, **kwargs):
        raise AssertionError("Local watch integration tests forbid DNS")

    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        patch.setattr(socket.socket, name, block(getattr(socket.socket, name)))
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, no_dns)
    yield
    patch.undo()


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/local-watch/devices", None),
    ("POST", "/local-watch/devices", {"name": "Mac"}),
    ("DELETE", "/local-watch/devices/1", None),
    ("GET", "/local-watch/rules", None),
    ("POST", "/local-watch/rules", {}),
    ("PATCH", "/local-watch/rules/1", {}),
    ("DELETE", "/local-watch/rules/1", None),
    ("GET", "/local-watch/windows", None),
    ("GET", "/local-watch/alerts?after=0", None),
    ("POST", "/local-watch/heartbeat", {"windows": []}),
    ("POST", "/local-watch/observations", {}),
    ("OPTIONS", "/local-watch/heartbeat", None),
])
def test_disabled_main_app_returns_private_404_before_auth(client, monkeypatch, method, path, body):
    monkeypatch.setenv("FIONA_LOCAL_WATCH", "0")
    response = client.request(method, path, json=body)
    assert response.status_code == 404
    assert response.headers.get("cache-control") == "private, no-store"


@pytest.mark.parametrize("path,body", [
    ("/local-watch/heartbeat", {"windows": []}),
    ("/local-watch/observations", {"rule_id": 1, "new_lines": [], "captured_at": "2026-10-11T12:00:00Z"}),
])
def test_device_authentication_cannot_borrow_cookie_or_dev_identity(client, monkeypatch, path, body):
    monkeypatch.setenv("FIONA_LOCAL_WATCH", "1")
    response = client.post(path, json=body, headers={"X-Dev-User": "smoke_tester"})
    assert response.status_code == 401
    assert response.headers.get("cache-control") == "private, no-store"


def login_cookie(client, monkeypatch):
    import database
    asyncio.run(database.create_invite("LOCALWATCHCOOKIE", "local_watch_cookie"))
    assert client.post("/auth/redeem-invite", json={"code": "LOCALWATCHCOOKIE"}).status_code == 200
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("FIONA_LOCAL_WATCH", "1")


def test_cookie_user_device_bearer_and_deleted_conversation_fallback(client, monkeypatch):
    import agent_store
    import database
    login_cookie(client, monkeypatch)
    device = client.post("/local-watch/devices", json={"name": "Cookie Mac"})
    assert device.status_code in (200, 201), device.text
    bearer = {"Authorization": "Bearer " + device.json()["token"]}
    conversation = asyncio.run(agent_store.create_conversation("local_watch_cookie", "临时会话"))
    conversation_id = conversation["id"]
    rule = client.post("/local-watch/rules", json={
        "name": "完成提醒", "app_match": "Terminal", "title_match": "",
        "kind": "keyword", "params": {"keywords": ["Download"]},
        "conversation_id": conversation_id,
    })
    assert rule.status_code in (200, 201), rule.text
    assert asyncio.run(agent_store.delete_conversation("local_watch_cookie", conversation_id)) is not None
    client.cookies.clear()
    heartbeat = client.post("/local-watch/heartbeat", headers=bearer, json={"windows": [
        {"window_id": 1, "app_name": "Terminal", "bundle_id": "com.apple.Terminal", "title": "Jobs"},
    ]})
    assert heartbeat.status_code == 200
    assert "params" not in heartbeat.text
    observed = client.post("/local-watch/observations", headers=bearer, json={
        "rule_id": rule.json()["id"], "new_lines": ["Download complete"],
        "captured_at": "2026-10-11T12:00:00Z",
    })
    assert observed.status_code == 200, observed.text
    assert observed.json()["alert"] is True
    with sqlite3.connect(database.DB_PATH) as db:
        alert = db.execute("SELECT message_id, conversation_id, summary FROM watch_alerts").fetchone()
        message = db.execute("SELECT content, conversation_id FROM messages WHERE id=?", (alert[0],)).fetchone()
        assert message[1] == alert[1] != conversation_id
        assert message[0] == f"【本机提醒 · Terminal】{alert[2]}（规则：完成提醒）"
        assert db.execute("SELECT is_default FROM conversations WHERE id=?", (alert[1],)).fetchone()[0] == 1
    revoked = client.delete("/local-watch/devices/" + str(device.json()["id"]), headers=bearer)
    assert revoked.status_code == 401  # device tokens have no user-settings authority
    assert revoked.headers.get("cache-control") == "private, no-store"
