# -*- coding: utf-8 -*-
"""DEV shortcuts require the actual ASGI socket peer to be loopback."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_dev_http_shortcuts_reject_remote_peer_even_with_proxy_headers(client):
    import main

    headers = {"X-Dev-User": "loopback_owner", "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"}
    assert client.post("/auth/test-login", json={"username": "loopback_owner"}).status_code == 200
    assert client.get("/profile", headers=headers).status_code == 200
    assert client.get("/users").status_code == 200
    assert client.post("/auth/send-otp", json={"phone": ""}).status_code == 400
    assert client.post("/auth/verify-otp", json={"phone": "", "code": ""}).status_code == 400

    remote = TestClient(main.app, client=("203.0.113.17", 45678))
    try:
        assert remote.get("/profile", headers=headers).status_code == 401
        assert remote.get("/profile", params={"dev_user": "loopback_owner"}).status_code == 401
        assert remote.get("/users").status_code in (401, 404)
        assert remote.post("/auth/test-login", json={"username": "loopback_owner"}).status_code == 404
        assert remote.post("/auth/send-otp", json={"phone": ""}).status_code == 404
        assert remote.post("/auth/verify-otp", json={"phone": "", "code": ""}).status_code == 404
        assert remote.get("/docs").status_code == 404
        assert remote.get("/uploads/nonexistent.jpg").status_code == 401
    finally:
        remote.close()


def test_dev_websocket_user_query_rejects_remote_peer(client):
    import main

    local = TestClient(main.app, client=("127.0.0.1", 45678))
    remote = TestClient(main.app, client=("203.0.113.17", 45678))
    try:
        with pytest.raises(WebSocketDisconnect) as local_error:
            with local.websocket_connect("/ws/peer/alice__bob?dev_user=alice"):
                pass
        assert local_error.value.code == 4403  # identity accepted; room access denied

        with pytest.raises(WebSocketDisconnect) as remote_error:
            with remote.websocket_connect("/ws/peer/alice__bob?dev_user=alice"):
                pass
        assert remote_error.value.code == 4401  # DEV identity itself denied
    finally:
        local.close()
        remote.close()


def test_production_authentication_still_accepts_valid_cookie_from_remote(client, monkeypatch):
    import main

    response = client.post("/auth/test-login", json={"username": "remote_real_session"})
    assert response.status_code == 200
    token = client.cookies.get("fiona_token")
    assert token
    monkeypatch.setenv("DEV_MODE", "0")
    remote = TestClient(main.app, client=("203.0.113.17", 45678))
    local = TestClient(main.app, client=("127.0.0.1", 45678))
    try:
        remote.cookies.set("fiona_token", token)
        assert remote.get("/profile").status_code == 200
        assert local.get("/profile", headers={"X-Dev-User": "remote_real_session"}).status_code == 401
        assert local.post("/auth/test-login", json={"username": "nope"}).status_code == 404
    finally:
        remote.close()
        local.close()
