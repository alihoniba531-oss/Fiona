"""Offline contracts for account-saved Claude effort and bounded SDK requests."""
import asyncio
import base64
import json
import socket
import sqlite3
import urllib.request

import httpcore
import httpcore2
import httpx
import httpx2
import pytest
import requests

import database
from byok import client as byok_client, crypto, providers, store
from utils import safe_http


SECRET = "sk-offline-effort-1234"
DRAFT = {"provider": "anthropic", "model": "claude-opus-5-5", "api_key": SECRET}
EFFORTS = ("low", "medium", "high")


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    for target, name in (
        (urllib.request, "urlopen"), (requests, "get"), (safe_http, "_open_pinned"),
        (socket, "getaddrinfo"),
        (httpcore.SyncBackend, "connect_tcp"), (httpcore.SyncBackend, "connect_unix_socket"),
        (httpcore2.SyncBackend, "connect_tcp"), (httpcore2.SyncBackend, "connect_unix_socket"),
        (httpx.HTTPTransport, "handle_request"), (httpx.AsyncHTTPTransport, "handle_async_request"),
        (httpx2.HTTPTransport, "handle_request"), (httpx2.AsyncHTTPTransport, "handle_async_request"),
    ):
        monkeypatch.setattr(target, name, blocked)
    monkeypatch.setenv("FIONA_BYOK_SECRET", base64.urlsafe_b64encode(b"e" * 32).decode())
    monkeypatch.delenv("FIONA_BYOK_SECRET_PREVIOUS", raising=False)
    for name in crypto.FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    from rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()
    assert not attempted, "network"


def _config(provider="anthropic", *, model="claude-opus-5-5", effort="low"):
    return {"provider": provider, "model": model, "api_key": SECRET, "enabled": True,
            "base_url": "https://api.example.net/v1" if provider == "custom" else None,
            "effort": effort}


def _claude_sse():
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_effort", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "好"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 1}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode()


def _capture_claude(monkeypatch):
    constructor = byok_client.anthropic.Anthropic
    calls, clients = [], []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=_claude_sse())

    def offline_constructor(**kwargs):
        kwargs["http_client"] = httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)
        sdk = constructor(**kwargs)
        clients.append(sdk)
        return sdk

    monkeypatch.setattr(byok_client.anthropic, "Anthropic", offline_constructor)
    return calls, clients


def _capture_openai(monkeypatch):
    constructor = byok_client.openai.OpenAI
    calls, clients = [], []

    def handler(request):
        calls.append(request.content)
        payload = {"id": "effort", "object": "chat.completion.chunk", "created": 0, "model": "unit",
                   "choices": [{"index": 0, "delta": {"content": "好"}, "finish_reason": "stop"}]}
        content = ("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode()
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=content)

    def offline_constructor(**kwargs):
        if "http_client" in kwargs:
            kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        sdk = constructor(**kwargs)
        clients.append(sdk)
        return sdk

    monkeypatch.setattr(byok_client.openai, "OpenAI", offline_constructor)
    return calls, clients


def _consume(config, *, mirror=False):
    stream = byok_client.open_reply_stream(
        config, [{"role": "system", "content": "Reply to alice"}, {"role": "user", "content": "你好"}],
        mirror=mirror, username="alice")
    assert "".join(chunk.choices[0].delta.content or "" for chunk in stream) == "好"
    return stream


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("effort,tokens", [("low", 4096), ("medium", 8192), ("high", 16384)])
def test_claude_sdk_effort_and_token_budget(monkeypatch, model, mirror, effort, tokens):
    calls, clients = _capture_claude(monkeypatch)
    stream = _consume(_config(model=model, effort=effort), mirror=mirror)
    assert calls[0]["output_config"] == {"effort": effort}
    assert calls[0]["max_tokens"] == (tokens // 2 if mirror else tokens)
    assert stream.character_limit == (600 if mirror else 4000)
    assert not {"thinking", "temperature", "top_p", "top_k"} & calls[0].keys()
    if model != "claude-haiku-5-5":
        assert calls[0]["fallbacks"] == "default"
    else:
        assert "fallbacks" not in calls[0]
    assert clients[0].is_closed()


@pytest.mark.parametrize("effort", [None, "", "invalid", 2, [], {}, "missing"])
def test_claude_sdk_invalid_or_missing_effort_is_low(monkeypatch, effort):
    calls, _ = _capture_claude(monkeypatch)
    config = _config(effort=effort)
    if effort == "missing":
        config.pop("effort")
    _consume(config)
    assert calls[0]["output_config"] == {"effort": "low"}
    assert calls[0]["max_tokens"] == 4096


@pytest.mark.parametrize("effort", EFFORTS)
def test_connection_always_uses_low_and_1024(monkeypatch, effort):
    calls, clients = _capture_claude(monkeypatch)
    byok_client.test_connection(_config(effort=effort))
    assert calls[0]["output_config"] == {"effort": "low"}
    assert calls[0]["max_tokens"] == 1024
    assert clients[0].is_closed()


@pytest.mark.parametrize("provider", ["dashscope", "deepseek", "moonshot", "zhipu", "custom"])
@pytest.mark.parametrize("mirror", [False, True])
def test_openai_body_is_byte_identical_with_high_effort(monkeypatch, provider, mirror):
    calls, clients = _capture_openai(monkeypatch)
    config = _config(provider, model="unit-model", effort="high")
    without = {key: value for key, value in config.items() if key != "effort"}
    _consume(without, mirror=mirror)
    _consume(config, mirror=mirror)
    assert calls[0] == calls[1]
    body = json.loads(calls[1])
    expected = {"model": "unit-model", "messages": [
        {"role": "system", "content": "Reply to （账号已隐藏）"}, {"role": "user", "content": "你好"}],
        "stream": True, "max_tokens": 512 if mirror else 2048}
    if provider == "dashscope":
        expected["enable_thinking"] = False
    elif provider == "deepseek":
        expected["thinking"] = {"type": "disabled"}
    assert body == expected
    assert all(sdk.is_closed() for sdk in clients)


def _capture_deadlines(monkeypatch, seconds):
    calls = []

    class Timer:
        def __init__(self, interval, callback):
            calls.append(interval)
            self.daemon = False

        def start(self):
            pass

        def cancel(self):
            pass

    monkeypatch.setattr(byok_client, "Timer", Timer)
    monkeypatch.setattr(byok_client, "total_seconds", lambda: seconds)
    return calls


@pytest.mark.parametrize("seconds", [120, 200])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("effort", EFFORTS)
def test_watchdog_receives_effort_deadline(monkeypatch, seconds, mirror, effort):
    deadlines = _capture_deadlines(monkeypatch, seconds)
    _capture_claude(monkeypatch)
    _consume(_config(effort=effort), mirror=mirror)
    assert deadlines == [min(240, seconds * 1.5) if effort == "high" else seconds]


@pytest.mark.parametrize("seconds", [120, 200])
@pytest.mark.parametrize("effort", EFFORTS)
def test_connection_watchdog_uses_unscaled_deadline(monkeypatch, seconds, effort):
    deadlines = _capture_deadlines(monkeypatch, seconds)
    _capture_claude(monkeypatch)
    byok_client.test_connection(_config(effort=effort))
    assert deadlines == [seconds]


@pytest.mark.parametrize("provider", ["dashscope", "deepseek", "moonshot", "zhipu", "custom"])
def test_openai_watchdog_uses_unscaled_deadline(monkeypatch, provider):
    deadlines = _capture_deadlines(monkeypatch, 200)
    _capture_openai(monkeypatch)
    _consume(_config(provider, model="unit-model", effort="high"))
    assert deadlines == [200]


def _request(client, headers, method, body=None):
    response = client.request(method, "/chat-model", headers=headers, json=body)
    assert response.headers["cache-control"] == "private, no-store"
    assert SECRET not in response.text
    assert "key_ciphertext" not in response.text and "key_id" not in response.text
    return response


def _save(client, headers, **changes):
    response = _request(client, headers, "PUT", {**DRAFT, **changes})
    assert response.status_code == 200, response.text
    return response.json()["config"]


def _get(client, headers):
    response = _request(client, headers, "GET")
    assert response.status_code == 200
    return response.json()["config"]


def test_old_database_migrates_existing_row_and_is_idempotent(client, dev_headers):
    _get(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    ciphertext, key_id = crypto.encrypt_key(SECRET, user, "anthropic")
    old_ddl = """
        CREATE TABLE user_model_configs (
            username TEXT PRIMARY KEY, provider TEXT NOT NULL, base_url TEXT DEFAULT NULL,
            model TEXT NOT NULL, key_ciphertext BLOB NOT NULL, key_id TEXT NOT NULL,
            key_last4 TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("DROP TABLE user_model_configs")
        db.execute(old_ddl)
        db.execute("""INSERT INTO user_model_configs
                   (username, provider, model, key_ciphertext, key_id, key_last4)
                   VALUES (?, 'anthropic', 'claude-opus-5-5', ?, ?, ?)""",
                   (user, ciphertext, key_id, SECRET[-4:]))
    asyncio.run(database.init_db())
    with sqlite3.connect(database.DB_PATH) as db:
        columns = {row[1]: row for row in db.execute("PRAGMA table_info(user_model_configs)")}
        assert "effort" in columns
        assert columns["effort"][2:5] == ("TEXT", 1, "'low'")
        assert db.execute("SELECT effort FROM user_model_configs WHERE username = ?", (user,)).fetchone() == ("low",)
    assert _get(client, dev_headers)["effort"] == "low"
    asyncio.run(database.init_db())
    assert _get(client, dev_headers)["effort"] == "low"


def test_provider_metadata(client, dev_headers):
    response = _request(client, dev_headers, "GET")
    for metadata in response.json()["providers"]:
        assert metadata["efforts"] == (list(EFFORTS) if metadata["id"] == "anthropic" else None)
        assert metadata["default_effort"] == ("low" if metadata["id"] == "anthropic" else None)
    assert providers.CLAUDE_EFFORTS == EFFORTS
    assert providers.DEFAULT_EFFORT == "low"


def test_new_configuration_defaults_low_public_and_internal(client, dev_headers):
    assert _save(client, dev_headers)["effort"] == "low"
    assert asyncio.run(store.get_internal_config(dev_headers["X-Dev-User"]))["effort"] == "low"


@pytest.mark.parametrize("value", ["xhigh", "max", "", 4, None, [], {}])
def test_validate_effort_rejects_every_non_string_option(value):
    from byok.errors import ConfigurationError
    with pytest.raises(ConfigurationError) as exc:
        providers.validate_effort(value)
    assert exc.value.args == ("思考强度只能是低、中、高",)


@pytest.mark.parametrize("effort", EFFORTS)
def test_patch_effort_is_saved_and_returned_by_get(client, dev_headers, effort):
    _save(client, dev_headers)
    response = _request(client, dev_headers, "PATCH", {"effort": effort})
    assert response.status_code == 200, response.text
    assert response.json()["config"]["effort"] == effort
    assert _get(client, dev_headers)["effort"] == effort
    internal = asyncio.run(store.get_internal_config(dev_headers["X-Dev-User"]))
    assert internal["effort"] == effort and internal["api_key"] == SECRET


@pytest.mark.parametrize("body,message", [
    ({"effort": "xhigh"}, "思考强度只能是低、中、高"),
    ({"effort": "max"}, "思考强度只能是低、中、高"),
    ({"effort": ""}, "思考强度只能是低、中、高"),
    ({"effort": 47}, "思考强度只能是低、中、高"),
    ({"effort": None}, "思考强度只能是低、中、高"),
    ({"effort": "high", "extra": "untrusted-extra-input"}, "请求格式不正确"),
    ({}, "请求格式不正确"),
])
def test_invalid_effort_patch_uses_fixed_error_and_preserves_row(client, dev_headers, body, message):
    before = _save(client, dev_headers)
    response = _request(client, dev_headers, "PATCH", body)
    assert response.status_code == 400
    assert response.json() == {"detail": message}
    assert "untrusted-extra-input" not in response.text
    assert _get(client, dev_headers) == before


@pytest.mark.parametrize("provider", ["dashscope", "deepseek", "moonshot", "zhipu", "custom"])
def test_only_anthropic_can_patch_effort(client, dev_headers, monkeypatch, provider):
    monkeypatch.setattr(store, "validate_custom_base_url", lambda url: url)
    changes = {"provider": provider, "model": "unit-model"}
    if provider == "custom":
        changes["base_url"] = "https://api.example.net/v1"
    before = _save(client, dev_headers, **changes)
    response = _request(client, dev_headers, "PATCH", {"effort": "high"})
    assert response.status_code == 400
    assert response.json() == {"detail": "只有 Claude 支持思考强度"}
    assert _get(client, dev_headers) == before


def test_needs_reentry_can_change_effort_without_decryptable_key(client, dev_headers):
    _save(client, dev_headers)
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE user_model_configs SET key_ciphertext = ?, enabled = 0", (b"corrupt",))
    response = _request(client, dev_headers, "PATCH", {"effort": "high"})
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["status"] == "needs_reentry" and config["effort"] == "high" and config["enabled"] is False
    response = _request(client, dev_headers, "PATCH", {"enabled": True, "effort": "medium"})
    assert response.status_code == 400
    assert response.json() == {"detail": "配置需要重新填写 Key"}
    assert _get(client, dev_headers) == config


def test_patch_both_options_commits_together(client, dev_headers):
    _save(client, dev_headers)
    response = _request(client, dev_headers, "PATCH", {"enabled": False, "effort": "medium"})
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["enabled"] is False and config["effort"] == "medium"
    assert _get(client, dev_headers) == config


@pytest.mark.parametrize("body", [
    {"enabled": False, "effort": "xhigh"},
    {"enabled": "untrusted-enabled-input", "effort": "high"},
    {"enabled": None, "effort": "high"},
])
def test_patch_both_options_is_atomic_when_either_invalid(client, dev_headers, body):
    before = _save(client, dev_headers)
    response = _request(client, dev_headers, "PATCH", body)
    assert response.status_code == 400
    assert "untrusted-enabled-input" not in response.text
    assert _get(client, dev_headers) == before


def test_non_anthropic_rejection_does_not_change_enabled(client, dev_headers):
    before = _save(client, dev_headers, provider="deepseek", model="deepseek-v4-pro")
    response = _request(client, dev_headers, "PATCH", {"enabled": False, "effort": "high"})
    assert response.status_code == 400
    assert response.json() == {"detail": "只有 Claude 支持思考强度"}
    assert _get(client, dev_headers) == before


@pytest.mark.parametrize("changes", [
    {"model": "claude-sonnet-5-5"}, {"api_key": "sk-offline-new-effort-key"},
    {"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "sk-offline-deepseek-key"},
])
def test_put_retains_high_when_changing_model_key_or_provider(client, dev_headers, changes):
    _save(client, dev_headers)
    response = _request(client, dev_headers, "PATCH", {"effort": "high"})
    assert response.status_code == 200, response.text
    assert _save(client, dev_headers, **changes)["effort"] == "high"
    if changes.get("provider") == "deepseek":
        assert _save(client, dev_headers)["effort"] == "high"


def test_put_forbids_effort_even_when_valid(client, dev_headers):
    before = _save(client, dev_headers)
    response = _request(client, dev_headers, "PUT", {**DRAFT, "effort": "high"})
    assert response.status_code == 400
    assert response.json() == {"detail": "请求格式不正确"}
    assert _get(client, dev_headers) == before


@pytest.mark.parametrize("effort", ["xhigh", "max", "", 17, None])
def test_invalid_stored_effort_is_low_public_and_internal(client, dev_headers, effort):
    _save(client, dev_headers)
    with sqlite3.connect(database.DB_PATH) as db:
        if effort is not None:
            db.execute("UPDATE user_model_configs SET effort = ?", (effort,))
    if effort is None:
        # NOT NULL protects normal rows; also cover malformed legacy in-memory reads.
        row = asyncio.run(store._read_row(dev_headers["X-Dev-User"]))
        row["effort"] = None
        assert store._public(row)["effort"] == "low"
    else:
        assert _get(client, dev_headers)["effort"] == "low"
        assert asyncio.run(store.get_internal_config(dev_headers["X-Dev-User"]))["effort"] == "low"


def test_delete_account_removes_entire_effort_row(client, dev_headers):
    _save(client, dev_headers)
    response = _request(client, dev_headers, "PATCH", {"effort": "high"})
    assert response.status_code == 200, response.text
    user = dev_headers["X-Dev-User"]
    assert asyncio.run(database.delete_account_data(user))["deleted"] is True
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT effort FROM user_model_configs WHERE username = ?", (user,)).fetchone() is None
