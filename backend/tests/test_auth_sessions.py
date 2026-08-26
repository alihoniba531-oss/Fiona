# -*- coding: utf-8 -*-
import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect


def test_logout_revokes_captured_cookie(client):
    import database

    asyncio.run(database.create_invite("SESSION1", "session_user"))
    login = client.post("/auth/redeem-invite", json={"code": "SESSION1"})
    assert login.status_code == 200
    old_token = client.cookies.get("fiona_token")
    assert old_token
    assert client.get("/profile").status_code == 200

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    client.cookies.set("fiona_token", old_token)
    assert client.get("/profile").status_code == 401


def test_invite_can_be_revoked_and_rotated(client):
    import database

    asyncio.run(database.create_invite("OLDINV1", "rotate_user"))
    assert asyncio.run(database.rotate_invite("OLDINV1", "NEWINV1")) is True
    assert client.post("/auth/redeem-invite", json={"code": "OLDINV1"}).status_code == 401
    assert client.post("/auth/redeem-invite", json={"code": "NEWINV1"}).status_code == 200
    captured_token = client.cookies.get("fiona_token")

    assert asyncio.run(database.revoke_invite("NEWINV1")) is True
    assert client.post("/auth/redeem-invite", json={"code": "NEWINV1"}).status_code == 401
    client.cookies.set("fiona_token", captured_token)
    assert client.get("/profile").status_code == 401


def test_invite_redemption_tracks_usage(client):
    import database

    asyncio.run(database.create_invite("USAGE001", "usage_user"))
    assert client.post("/auth/redeem-invite", json={"code": "USAGE001"}).status_code == 200
    assert client.post("/auth/redeem-invite", json={"code": "USAGE001"}).status_code == 200
    invite = next(row for row in asyncio.run(database.list_invites()) if row["code"] == "USAGE001")
    assert invite["use_count"] == 2
    assert invite["last_used_at"] is not None


def test_public_optional_auth_reads_session_cookie(client, monkeypatch):
    import database

    asyncio.run(database.create_invite("COOKIE01", "cookie_user"))
    assert client.post("/auth/redeem-invite", json={"code": "COOKIE01"}).status_code == 200
    captured = {}

    async def recommended(username, time_slot, **kwargs):
        captured["username"] = username
        return []

    monkeypatch.setattr(database, "get_recommended_posts", recommended)
    response = client.get("/plaza/feed?sort=recommended")
    assert response.status_code == 200
    assert captured["username"] == "cookie_user"


def test_logout_closes_existing_peer_websocket(client):
    import aiosqlite
    import database

    async def seed():
        await database.create_invite("PEERWS01", "peer_ws_user")
        await database.get_or_create_user("peer_ws_user")
        await database.get_or_create_user("peer_ws_friend")
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """INSERT INTO matches (user_a, user_b, response_a, response_b)
                   VALUES (?, ?, 'accept', 'accept')""",
                ("peer_ws_friend", "peer_ws_user"),
            )
            await db.commit()

    asyncio.run(seed())
    assert client.post("/auth/redeem-invite", json={"code": "PEERWS01"}).status_code == 200

    with client.websocket_connect("/ws/peer/peer_ws_friend__peer_ws_user") as websocket:
        assert websocket.receive_json()["type"] == "history"
        assert client.post("/auth/logout").status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4401


def test_peer_message_write_rechecks_latest_consent(client):
    import aiosqlite
    import database

    async def scenario():
        await database.get_or_create_user("consent_a")
        await database.get_or_create_user("consent_b")
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """INSERT INTO matches (user_a, user_b, response_a, response_b)
                   VALUES ('consent_a', 'consent_b', 'accept', 'accept')"""
            )
            await db.commit()
        accepted = await database.save_peer_message(
            "consent_a__consent_b", "consent_a", "before reject"
        )
        await database.update_match_response("consent_b", "consent_a", "reject")
        rejected = await database.save_peer_message(
            "consent_a__consent_b", "consent_a", "after reject"
        )
        return accepted, rejected

    assert asyncio.run(scenario()) == (True, False)
