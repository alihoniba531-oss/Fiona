"""Deleted account names cannot revive an earlier login session."""

import asyncio

import pytest


async def _stored_session_version(username):
    import aiosqlite
    import database

    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute(
            "SELECT session_version, typeof(session_version) FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            return await cursor.fetchone()


def test_deleted_tester_name_is_retired_and_old_token_stays_invalid(client):
    import database
    from auth_dep import authenticate_token

    first = asyncio.run(database.create_tester_invites(2))
    assert [username for _, username in first] == ["tester01", "tester02"]

    login = client.post("/auth/redeem-invite", json={"code": first[1][0]})
    assert login.status_code == 200
    old_token = client.cookies.get("fiona_token")
    assert old_token
    assert asyncio.run(authenticate_token(old_token)) == "tester02"

    assert asyncio.run(database.delete_account_data("tester02"))["deleted"]
    assert asyncio.run(authenticate_token(old_token)) is None

    later = asyncio.run(database.create_tester_invites(1))
    assert [username for _, username in later] == ["tester03"]

    async def retired_name():
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT retired_at FROM retired_usernames WHERE username = ?",
                ("tester02",),
            ) as cursor:
                return await cursor.fetchone()

    assert asyncio.run(retired_name())[0] is not None

    recreated = asyncio.run(database.get_or_create_user("tester02"))
    assert recreated["session_version"] > 0
    assert asyncio.run(authenticate_token(old_token)) is None
    client.cookies.set("fiona_token", old_token)
    assert client.get("/profile").status_code == 401


def test_new_users_start_with_distinct_positive_session_versions(client, monkeypatch):
    import database

    numbers = iter((123, 456, 789))
    monkeypatch.setattr(database.secrets, "randbelow", lambda upper: next(numbers))

    first = asyncio.run(database.get_or_create_user("version_first"))
    second = asyncio.run(database.get_or_create_user("version_second"))
    phone = asyncio.run(database.get_or_create_user_by_phone("13800000042"))

    assert first["session_version"] == 124
    assert second["session_version"] == 457
    assert phone["session_version"] == 790
    assert len({first["session_version"], second["session_version"], phone["session_version"]}) == 3


def test_existing_zero_version_session_remains_valid(client):
    import aiosqlite
    import database
    from auth import create_token
    from auth_dep import authenticate_token

    async def seed_legacy_account():
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("INSERT INTO users (username) VALUES (?)", ("legacy_zero",))
            await db.commit()

    asyncio.run(seed_legacy_account())
    token = create_token("legacy_zero", 0)
    assert asyncio.run(authenticate_token(token)) == "legacy_zero"
    existing = asyncio.run(database.get_or_create_user("legacy_zero"))
    assert existing["session_version"] == 0
    assert asyncio.run(authenticate_token(token)) == "legacy_zero"


@pytest.mark.parametrize("by_phone", [False, True], ids=["username", "phone"])
@pytest.mark.parametrize("random_value", [0, 2**31 - 2], ids=["lower_bound", "upper_bound"])
def test_new_session_version_bounds_allow_integer_revocation(
    client, monkeypatch, by_phone, random_value
):
    import database
    from auth import create_token
    from auth_dep import authenticate_token

    def fixed_random(upper):
        assert upper == 2**31 - 1
        return random_value

    monkeypatch.setattr(database.secrets, "randbelow", fixed_random)
    username = "13800000123" if by_phone else "bounded_version_user"
    user = asyncio.run(
        database.get_or_create_user_by_phone(username)
        if by_phone else database.get_or_create_user(username)
    )
    initial_version = random_value + 1
    assert user["session_version"] == initial_version
    assert isinstance(user["session_version"], int)

    old_token = create_token(username, initial_version)
    assert asyncio.run(authenticate_token(old_token)) == username
    assert asyncio.run(database.revoke_user_sessions(username)) is True
    current_version = asyncio.run(database.get_session_version(username))
    assert current_version == initial_version + 1
    assert isinstance(current_version, int)
    assert asyncio.run(_stored_session_version(username)) == (initial_version + 1, "integer")
    assert asyncio.run(authenticate_token(old_token)) is None


def test_max_initial_version_survives_invite_rotation_and_revocation(client, monkeypatch):
    import database
    from auth import create_token
    from auth_dep import authenticate_token

    def max_random(upper):
        assert upper == 2**31 - 1
        return upper - 1

    monkeypatch.setattr(database.secrets, "randbelow", max_random)
    username = "max_version_invite_user"
    initial_version = asyncio.run(database.get_or_create_user(username))["session_version"]
    assert initial_version == 2**31 - 1
    assert asyncio.run(database.create_invite("MAXSVOLD", username)) is True

    before_rotate = create_token(username, initial_version)
    assert asyncio.run(database.rotate_invite("MAXSVOLD", "MAXSVNEW")) is True
    rotated_version = asyncio.run(database.get_session_version(username))
    assert rotated_version == initial_version + 1
    assert asyncio.run(authenticate_token(before_rotate)) is None

    before_revoke = create_token(username, rotated_version)
    assert asyncio.run(database.revoke_invite("MAXSVNEW")) is True
    revoked_version = asyncio.run(database.get_session_version(username))
    assert revoked_version == rotated_version + 1
    assert isinstance(revoked_version, int)
    assert asyncio.run(_stored_session_version(username)) == (initial_version + 2, "integer")
    assert asyncio.run(authenticate_token(before_revoke)) is None
