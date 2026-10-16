"""R3 capture-state HTTP contracts, entirely offline with both models stubbed."""
import asyncio
import socket
import sqlite3
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module", autouse=True)
def offline():
    def forbidden(*args, **kwargs):
        raise AssertionError("R3 tests forbid network and DNS")

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
        raise AssertionError("R3 models must be stubbed")

    monkeypatch.setattr(service, "QWEN_CLIENT", SimpleNamespace(with_options=forbidden))
    monkeypatch.setattr(service.byok_client.anthropic, "Anthropic", forbidden)


SINCE = "2026-10-11T12:00:00Z"
STOPPED = {"ok": False, "message": "监控程序未在运行"}
WAITING = {"ok": False, "neutral": True, "message": "等待首次截图"}
DISABLED = {"ok": False, "neutral": True, "message": "已停用"}
CAPTURE_ERROR = "截图失败：屏幕可能已锁定或显示器已休眠，也可能缺少屏幕录制权限"
NO_WINDOW = "没有找到匹配的窗口（窗口可能已关闭或最小化）"
OTHER_ERROR = "截图失败，请查看监控程序日志"


def device(client, username="smoke_tester"):
    response = client.post("/local-watch/devices", headers={"X-Dev-User": username}, json={"name": "R3 Mac"})
    assert response.status_code == 200, response.text
    return response.json()


def rule(client, username="smoke_tester", **changes):
    payload = {"name": "R3规则", "app_match": "WeChat", "kind": "keyword", "params": {"keywords": ["开会"]}}
    payload.update(changes)
    response = client.post("/local-watch/rules", headers={"X-Dev-User": username}, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def status(identifier, ok=True, error=None, since=SINCE):
    return {"rule_id": identifier, "ok": ok, "error": error, "since": since}


def heartbeat(client, item, captures, windows=None):
    return client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer " + item["token"]}, json={
        "windows": [] if windows is None else windows, "capture_status": captures,
    })


def captures(client, username="smoke_tester"):
    response = client.get("/local-watch/rules", headers={"X-Dev-User": username})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    return {value["id"]: value["capture"] for value in response.json()}


def test_every_rule_has_capture_even_before_any_heartbeat(client):
    first, second = rule(client), rule(client, enabled=False)
    assert captures(client) == {first["id"]: STOPPED, second["id"]: DISABLED}


@pytest.mark.parametrize("ok,error,message", [
    (True, None, "监控中"),
    (False, "SCStreamErrorDomain/-3811", CAPTURE_ERROR),
    (False, "com.apple.ScreenCaptureKit.SCStreamErrorDomain/-3811", CAPTURE_ERROR),
    (False, "SCStreamErrorDomain/-3801", CAPTURE_ERROR),
    (False, "SCStreamErrorDomain/99", CAPTURE_ERROR),
    (False, "ScreenCaptureKitErrorDomain/-1", CAPTURE_ERROR),
    (False, "ScreenCaptureKit/-7", CAPTURE_ERROR),
    (False, "SCErrorDomain/-3", CAPTURE_ERROR),
    (False, "window_not_found", NO_WINDOW),
    (False, "PrivateSecretErrorDomain/-901", OTHER_ERROR),
    (False, "NSOSStatusErrorDomain/-50", OTHER_ERROR),
    (False, None, "等待首次截图"),
    (False, "do not reveal this arbitrary uploaded text", OTHER_ERROR),
])
def test_saved_capture_chinese_mapping_and_since_are_returned_without_raw_errors(client, ok, error, message):
    item, watched = device(client), rule(client)
    response = heartbeat(client, item, [status(watched["id"], ok, error)])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"rules": [{key: watched[key] for key in ("id", "app_match", "title_match", "interval_seconds")}]}
    actual = captures(client)[watched["id"]]
    expected = {"ok": ok, "message": message, "since": SINCE}
    if not ok and error is None:
        expected["neutral"] = True
    assert actual == expected
    assert "error" not in actual
    if error is not None:
        assert error not in str(actual)


@pytest.mark.parametrize("since", ["2000-01-01T00:00:00Z", "9999-12-31T23:59:59Z"])
def test_capture_ttl_is_three_hundred_server_seconds_not_device_since(client, monkeypatch, since):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"], since=since)]).status_code == 200
    clock[0] = 399.999
    assert captures(client)[watched["id"]] == {"ok": True, "message": "监控中", "since": since}
    clock[0] = 400.0
    assert captures(client)[watched["id"]] == STOPPED


def test_unchanged_state_since_is_preserved_while_heartbeat_renews_server_ttl(client, monkeypatch):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"], False, "window_not_found")]).status_code == 200
    clock[0] = 390.0
    assert heartbeat(client, item, [status(watched["id"], False, "window_not_found")]).status_code == 200
    clock[0] = 600.0
    assert captures(client)[watched["id"]] == {"ok": False, "message": NO_WINDOW, "since": SINCE}
    clock[0] = 690.0
    assert captures(client)[watched["id"]] == STOPPED


def test_old_heartbeat_without_capture_status_remains_compatible_and_clears_old_device_state(client):
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"])]).status_code == 200
    response = client.post("/local-watch/heartbeat", headers={"Authorization": "Bearer " + item["token"]}, json={"windows": []})
    assert response.status_code == 200
    assert response.json()["rules"][0]["id"] == watched["id"]
    assert captures(client)[watched["id"]] == WAITING


def test_capture_isolation_between_users_and_foreign_status_is_discarded(client):
    mine, foreign = device(client), device(client, "other_r3")
    mine_rule, foreign_rule = rule(client), rule(client, "other_r3")
    response = heartbeat(client, mine, [status(mine_rule["id"]), status(foreign_rule["id"], False, "window_not_found")])
    assert response.status_code == 200
    assert captures(client)[mine_rule["id"]]["ok"] is True
    assert captures(client, "other_r3")[foreign_rule["id"]] == STOPPED
    assert heartbeat(client, foreign, [status(foreign_rule["id"], False, "window_not_found")]).status_code == 200
    assert captures(client)[mine_rule["id"]]["ok"] is True
    assert captures(client, "other_r3")[foreign_rule["id"]]["message"] == NO_WINDOW


def test_stale_deleted_disabled_or_missing_rule_status_does_not_break_rule_sync(client, dev_headers):
    item, deleted, disabled, active = device(client), rule(client), rule(client, enabled=False), rule(client)
    assert client.delete(f"/local-watch/rules/{deleted['id']}", headers=dev_headers).status_code == 204
    response = heartbeat(client, item, [status(deleted["id"]), status(disabled["id"]), status(999999), status(active["id"])])
    assert response.status_code == 200, response.text
    assert [value["id"] for value in response.json()["rules"]] == [active["id"]]
    assert captures(client) == {disabled["id"]: DISABLED, active["id"]: {"ok": True, "message": "监控中", "since": SINCE}}


def test_per_device_snapshots_latest_active_device_wins_and_revocation_restores_older_device(client, dev_headers, monkeypatch):
    from routers import local_watch as router
    clock = [100.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    older, newer, watched = device(client), device(client), rule(client)
    assert heartbeat(client, older, [status(watched["id"])]).status_code == 200
    clock[0] = 101.0
    assert heartbeat(client, newer, [status(watched["id"], False, "SCStreamErrorDomain/-3811")]).status_code == 200
    assert captures(client)[watched["id"]]["message"] == CAPTURE_ERROR
    assert client.delete(f"/local-watch/devices/{newer['id']}", headers=dev_headers).status_code == 204
    assert captures(client)[watched["id"]]["message"] == "监控中"
    assert heartbeat(client, newer, [status(watched["id"])]).status_code == 401
    clock[0] = 400.0
    assert captures(client)[watched["id"]] == STOPPED


def test_one_device_empty_snapshot_never_clears_other_device_capture(client):
    first, second, watched = device(client), device(client), rule(client)
    assert heartbeat(client, first, [status(watched["id"])]).status_code == 200
    assert heartbeat(client, second, []).status_code == 200
    assert captures(client)[watched["id"]]["ok"] is True
    assert heartbeat(client, first, []).status_code == 200
    assert captures(client)[watched["id"]] == WAITING


def test_directly_revoked_device_and_deleted_user_cannot_retain_active_status(client, dev_headers):
    import database
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"])]).status_code == 200
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE watch_devices SET revoked=1 WHERE id=?", (item["id"],))
    assert captures(client)[watched["id"]] == STOPPED
    replacement = device(client)
    assert heartbeat(client, replacement, [status(watched["id"])]).status_code == 200
    asyncio.run(database.delete_account_data("smoke_tester"))
    recreated_rule = rule(client)
    assert captures(client)[recreated_rule["id"]] == STOPPED
    assert heartbeat(client, replacement, [status(recreated_rule["id"])]).status_code == 401


def test_capture_cache_is_scoped_to_database_even_when_user_device_and_rule_ids_match(client, monkeypatch, tmp_path):
    import database
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"])]).status_code == 200
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "r3-second.db"))
    asyncio.run(database.init_db())
    newer, newer_rule = device(client), rule(client)
    assert newer["id"] == item["id"] and newer_rule["id"] == watched["id"]
    assert captures(client)[newer_rule["id"]] == STOPPED
    assert heartbeat(client, newer, [status(newer_rule["id"], False, "window_not_found")]).status_code == 200
    assert captures(client)[newer_rule["id"]]["message"] == NO_WINDOW


@pytest.mark.parametrize("change", [
    {"rule_id": True}, {"rule_id": 0}, {"rule_id": 2**63}, {"rule_id": "1"},
    {"ok": 1}, {"ok": "true"}, {"ok": None},
    {"error": "NSOSStatusErrorDomain/-50"}, {"error": 42}, {"error": "x" * 201},
    {"since": None}, {"since": ""}, {"since": "not-date"}, {"since": "2026-10-11"},
    {"since": "2026-10-11T12:00:00"}, {"since": "2026-02-30T12:00:00Z"},
    {"extra": "private payload"},
])
def test_invalid_capture_entry_is_discarded_while_valid_heartbeat_updates_windows(client, change):
    item, watched = device(client), rule(client)
    first = heartbeat(client, item, [status(watched["id"])], windows=[{"app_name": "original", "title": "original"}])
    assert first.status_code == 200
    value = status(watched["id"])
    value.update(change)
    response = heartbeat(client, item, [value], windows=[{"app_name": "replacement"}])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert captures(client)[watched["id"]] == WAITING
    windows = client.get("/local-watch/windows", headers={"X-Dev-User": "smoke_tester"}).json()
    assert windows[0]["app_name"] == "replacement"


@pytest.mark.parametrize("missing", ["rule_id", "ok", "error", "since"])
def test_capture_entries_missing_required_fields_are_discarded(client, missing):
    item, watched = device(client), rule(client)
    value = status(watched["id"])
    del value[missing]
    assert heartbeat(client, item, [value]).status_code == 200
    assert captures(client)[watched["id"]] == WAITING


@pytest.mark.parametrize("captures_value,expected", [(None, 422), ({}, 422), ("bad", 422), ([None], 200), ([[]], 200), ([{}] * 21, 422)])
def test_capture_status_list_and_twenty_rule_limit(client, captures_value, expected):
    item = device(client)
    assert heartbeat(client, item, captures_value).status_code == expected


def test_duplicate_rule_status_is_discarded_and_all_twenty_rules_are_supported(client):
    item = device(client)
    watched = [rule(client, name=str(index)) for index in range(20)]
    assert heartbeat(client, item, [status(watched[0]["id"])] * 2).status_code == 200
    response = heartbeat(client, item, [status(value["id"]) for value in watched])
    assert response.status_code == 200, response.text
    assert len(captures(client)) == 20
    assert all(value["ok"] for value in captures(client).values())


def test_r3_heartbeat_rate_limit_precedes_capture_validation_and_rule_queries(client, monkeypatch):
    from routers import local_watch as router
    from starlette.requests import Request
    item = device(client)
    for _ in range(10):
        assert heartbeat(client, item, None).status_code == 422

    async def forbidden(*args, **kwargs):
        raise AssertionError("rate limited heartbeat cannot parse JSON or read rules")

    monkeypatch.setattr(Request, "json", forbidden)
    monkeypatch.setattr(router.database, "list_watch_rules", forbidden)
    response = heartbeat(client, item, None)
    assert response.status_code == 429
    assert response.headers["cache-control"] == "private, no-store"
    assert int(response.headers["retry-after"]) > 0


def test_capture_status_never_persists_raw_error_or_since_to_database(client):
    import database
    item, watched = device(client), rule(client)
    assert heartbeat(client, item, [status(watched["id"], False, "PrivateSecretErrorDomain/-901")]).status_code == 200
    with sqlite3.connect(database.DB_PATH) as connection:
        dump = "\n".join(connection.iterdump())
    assert "PrivateSecretErrorDomain" not in dump
    assert SINCE not in dump
    assert captures(client)[watched["id"]]["message"] == OTHER_ERROR
