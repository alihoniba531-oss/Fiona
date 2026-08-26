# -*- coding: utf-8 -*-
import asyncio


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
