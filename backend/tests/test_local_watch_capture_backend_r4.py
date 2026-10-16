"""R4 state and real-client-IP contracts, with networking and models disabled."""
import asyncio
import socket
import sqlite3
from types import SimpleNamespace

import pytest

from test_local_watch_capture_backend_r3 import captures, device, heartbeat, rule, status


SINCE = "2026-10-11T12:00:00Z"
WAITING = {"ok": False, "neutral": True, "message": "等待首次截图"}
DISABLED = {"ok": False, "neutral": True, "message": "已停用"}
STOPPED = {"ok": False, "message": "监控程序未在运行"}


@pytest.fixture(scope="module", autouse=True)
def offline():
    def forbidden(*args, **kwargs):
        raise AssertionError("R4 tests forbid network and DNS")

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
    monkeypatch.setenv("FIONA_TRUSTED_PROXIES", "127.0.0.1,::1")
    for name in ("_windows", "_capture_states", "_recent_heartbeats", "_observation_rates", "_heartbeat_rates", "_authentication_failure_rates"):
        getattr(router, name, {}).clear()
    service._rule_locks.clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("R4 models must be stubbed")

    monkeypatch.setattr(service, "QWEN_CLIENT", SimpleNamespace(with_options=forbidden))
    monkeypatch.setattr(service.byok_client.anthropic, "Anthropic", forbidden)


def test_disabled_rule_is_neutral_before_heartbeat_and_overrides_saved_success(client, dev_headers):
    item, watched, disabled = device(client), rule(client), rule(client, enabled=False)
    assert captures(client)[disabled["id"]] == DISABLED
    assert heartbeat(client, item, [status(watched["id"])]).status_code == 200
    assert captures(client)[watched["id"]]["ok"] is True
    assert client.patch(f"/local-watch/rules/{watched['id']}", headers=dev_headers, json={"enabled": False}).status_code == 200
    assert captures(client)[watched["id"]] == DISABLED


def test_initial_state_is_neutral_and_retains_state_since_without_raw_errors(client):
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"], False, None)]).status_code == 200
    assert captures(client)[watched["id"]] == {**WAITING, "since": SINCE}


@pytest.mark.parametrize("snapshot", [None, [], [{}]])
def test_recent_heartbeat_without_valid_rule_state_is_neutral(client, snapshot):
    item, watched = device(client), rule(client)
    payload = {"windows": []}
    if snapshot is not None:
        payload["capture_status"] = snapshot
    response = client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer " + item["token"]}, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["rules"][0]["id"] == watched["id"]
    assert captures(client)[watched["id"]] == WAITING


def test_heartbeat_for_one_rule_leaves_other_enabled_rule_neutral(client):
    item, watched, pending = device(client), rule(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"])]).status_code == 200
    assert captures(client)[watched["id"]] == {"ok": True, "message": "监控中", "since": SINCE}
    assert captures(client)[pending["id"]] == WAITING


@pytest.mark.parametrize("snapshot", [[], [status(1, False, None, "9999-12-31T23:59:59Z")]])
def test_recent_heartbeat_expires_at_three_hundred_server_seconds(client, monkeypatch, snapshot):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    item, watched = device(client), rule(client)
    assert watched["id"] == 1
    assert heartbeat(client, item, snapshot).status_code == 200
    clock[0] = 399.999
    assert captures(client)[watched["id"]]["message"] == WAITING["message"]
    clock[0] = 400.0
    assert captures(client)[watched["id"]] == STOPPED


def test_only_successful_heartbeat_renews_recent_state(client, monkeypatch):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, []).status_code == 200
    clock[0] = 399.0
    assert heartbeat(client, item, None).status_code == 422
    clock[0] = 400.0
    assert captures(client)[watched["id"]] == STOPPED


def test_recent_heartbeat_is_per_user_and_per_database(client, monkeypatch, tmp_path):
    import database
    mine, mine_rule, foreign_rule = device(client), rule(client), rule(client, "other_r4")
    assert heartbeat(client, mine, []).status_code == 200
    assert captures(client)[mine_rule["id"]] == WAITING
    assert captures(client, "other_r4")[foreign_rule["id"]] == STOPPED
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "r4-other.db"))
    asyncio.run(database.init_db())
    replacement, replacement_rule = device(client), rule(client)
    assert replacement["id"] == mine["id"] and replacement_rule["id"] == mine_rule["id"]
    assert captures(client)[replacement_rule["id"]] == STOPPED
    assert heartbeat(client, replacement, []).status_code == 200
    assert captures(client)[replacement_rule["id"]] == WAITING


def test_recent_heartbeat_tracks_devices_independently_and_revocation_invalidates_only_one(client, dev_headers, monkeypatch):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    older, newer, watched = device(client), device(client), rule(client)
    assert heartbeat(client, older, []).status_code == 200
    clock[0] = 101.0
    assert heartbeat(client, newer, []).status_code == 200
    assert client.delete(f"/local-watch/devices/{newer['id']}", headers=dev_headers).status_code == 204
    assert captures(client)[watched["id"]] == WAITING
    clock[0] = 400.0
    assert captures(client)[watched["id"]] == STOPPED
    assert heartbeat(client, newer, []).status_code == 401


def test_recent_heartbeat_invalidated_by_direct_revocation_and_account_deletion(client):
    import database
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, []).status_code == 200
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE watch_devices SET revoked=1 WHERE id=?", (item["id"],))
    assert captures(client)[watched["id"]] == STOPPED
    replacement = device(client)
    assert heartbeat(client, replacement, []).status_code == 200
    asyncio.run(database.delete_account_data("smoke_tester"))
    recreated_rule = rule(client)
    assert captures(client)[recreated_rule["id"]] == STOPPED
    assert heartbeat(client, replacement, []).status_code == 401


def test_deleted_user_caches_are_discarded_even_if_device_rows_remain(client):
    import database
    from routers import local_watch as router
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"])]).status_code == 200
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("DELETE FROM users WHERE username='smoke_tester'")
    assert asyncio.run(router.rule_capture_states("smoke_tester")) == {}
    assert not any(key[:2] == (str(database.DB_PATH), "smoke_tester") for key in router._capture_states)
    assert not any(key[:2] == (str(database.DB_PATH), "smoke_tester") for key in router._recent_heartbeats)


@pytest.mark.parametrize("invalid_entry", [
    None, [], {}, {"rule_id": True, "ok": True, "error": None, "since": SINCE},
    {"rule_id": 0, "ok": True, "error": None, "since": SINCE},
    {"rule_id": 2**63, "ok": True, "error": None, "since": SINCE},
    {"rule_id": "1", "ok": True, "error": None, "since": SINCE},
    {"rule_id": 1, "ok": 1, "error": None, "since": SINCE},
    {"rule_id": 1, "ok": True, "error": "invalid-success", "since": SINCE},
    {"rule_id": 1, "ok": False, "error": 5, "since": SINCE},
    {"rule_id": 1, "ok": False, "error": "", "since": SINCE},
    {"rule_id": 1, "ok": False, "error": "x" * 201, "since": SINCE},
    {"rule_id": 1, "ok": True, "error": None, "since": None},
    {"rule_id": 1, "ok": True, "error": None, "since": ""},
    {"rule_id": 1, "ok": True, "error": None, "since": "not-date"},
    {"rule_id": 1, "ok": True, "error": None, "since": "2026-10-11"},
    {"rule_id": 1, "ok": True, "error": None, "since": "2026-10-11T12:00:00"},
    {"rule_id": 1, "ok": True, "error": None, "since": "2026-02-30T12:00:00Z"},
    {"rule_id": 1, "ok": True, "error": None, "since": SINCE, "extra": "private payload"},
])
def test_malformed_entry_is_discarded_without_losing_valid_entry_or_windows(client, invalid_entry):
    item, watched = device(client), rule(client)
    response = heartbeat(client, item, [invalid_entry, status(watched["id"])], windows=[{"app_name": "valid app", "title": "valid title"}])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert captures(client)[watched["id"]] == {"ok": True, "message": "监控中", "since": SINCE}
    assert response.json()["rules"][0]["id"] == watched["id"]
    assert client.get("/local-watch/windows", headers={"X-Dev-User": "smoke_tester"}).json()[0]["app_name"] == "valid app"


def test_duplicate_rule_status_keeps_first_valid_entry_and_other_rules_sync(client):
    item, watched, other = device(client), rule(client), rule(client)
    response = heartbeat(client, item, [status(watched["id"]), status(watched["id"], False, "window_not_found"), status(other["id"], False, None)])
    assert response.status_code == 200, response.text
    assert captures(client)[watched["id"]] == {"ok": True, "message": "监控中", "since": SINCE}
    assert captures(client)[other["id"]] == {**WAITING, "since": SINCE}


def test_foreign_and_missing_rule_entries_do_not_break_heartbeat_sync(client):
    item, watched, foreign = device(client), rule(client), rule(client, "other_r4")
    response = heartbeat(client, item, [status(foreign["id"]), status(99999), status(watched["id"])])
    assert response.status_code == 200, response.text
    assert response.json()["rules"][0]["id"] == watched["id"]
    assert captures(client, "other_r4")[foreign["id"]] == STOPPED
    assert captures(client)[watched["id"]]["ok"] is True


@pytest.mark.parametrize("bad_list", [None, {}, "bad", [{}] * 21])
def test_capture_status_container_and_limit_still_reject_atomically(client, bad_list):
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, bad_list).status_code == 422
    assert captures(client)[watched["id"]] == STOPPED


@pytest.mark.parametrize("bad_windows", [None, {}, [None], [{"extra": "unknown"}], [{"window_id": True}], [{"app_name": 42}], [{}] * 201])
def test_existing_window_validation_remains_strict(client, bad_windows):
    item, watched = device(client), rule(client)
    response = client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer " + item["token"]}, json={"windows": bad_windows, "capture_status": []})
    assert response.status_code == 422
    assert captures(client)[watched["id"]] == STOPPED


def test_discarded_entries_still_consume_heartbeat_limit_before_body_or_rules(client, monkeypatch):
    from routers import local_watch as router
    from starlette.requests import Request
    item = device(client)
    for _ in range(10):
        assert heartbeat(client, item, [{}]).status_code == 200

    async def forbidden(*args, **kwargs):
        raise AssertionError("full heartbeat bucket cannot parse JSON or query rules")

    monkeypatch.setattr(Request, "json", forbidden)
    monkeypatch.setattr(router.database, "list_watch_rules", forbidden)
    response = heartbeat(client, item, [{}])
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("header", ["X-Real-IP", "X-Forwarded-For"])
def test_trusted_proxy_counts_two_real_sources_separately(client, header):
    def fail(source):
        forwarded = source if header == "X-Real-IP" else "192.0.2.250, " + source
        return client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer forged", header: forwarded}, json={"windows": []})

    for _ in range(30):
        assert fail("198.51.100.10").status_code == 401
        assert fail("198.51.100.20").status_code == 401
    assert fail("198.51.100.10").status_code == 429
    assert fail("198.51.100.20").status_code == 429
    assert fail("198.51.100.30").status_code == 401


def test_untrusted_peer_cannot_reset_failure_count_with_forged_proxy_headers(client):
    original = client._transport.client
    try:
        client._transport.client = ("198.51.100.40", 50000)
        for index in range(30):
            response = client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer forged", "X-Real-IP": f"192.0.2.{index}", "X-Forwarded-For": f"192.0.2.{index}"}, json={"windows": []})
            assert response.status_code == 401
        assert client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer forged", "X-Real-IP": "192.0.2.99"}, json={"windows": []}).status_code == 429
    finally:
        client._transport.client = original


def test_authentication_failed_uses_existing_shared_real_ip_helper(client, monkeypatch):
    import rate_limit
    calls = []

    def real_ip(request):
        calls.append(request.headers.get("x-real-ip"))
        return "198.51.100.77"

    monkeypatch.setattr(rate_limit, "_client_ip", real_ip)
    response = client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer forged", "X-Real-IP": "198.51.100.77"}, json={"windows": []})
    assert response.status_code == 401
    assert calls == ["198.51.100.77"]
