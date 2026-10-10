"""Offline public-schema, validation, settings and connection-test contracts."""
import asyncio
import base64
import socket
import sqlite3
import urllib.request

import httpcore
import httpx
import openai
import pytest
import requests

from byok.errors import ByokUnavailableError, NeedsReentryError, error_message


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []
    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")
    from utils import safe_http
    from rate_limit import limiter
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(safe_http, "_open_pinned", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", blocked)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_unix_socket", blocked)
    from byok.crypto import FORBIDDEN_ENV
    for name in FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIONA_BYOK_SECRET", base64.urlsafe_b64encode(b"b" * 32).decode())
    limiter.reset()
    yield
    limiter.reset()
    assert not attempted, "network"


SECRET = "sk-private-settings-key"
DRAFT = {"provider": "anthropic", "model": "claude-opus-5-5", "api_key": SECRET}


def request(client, headers, method, *, body=None, path="/chat-model"):
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code != 401
    assert response.headers["cache-control"] == "private, no-store"
    assert SECRET not in response.text
    assert "key_ciphertext" not in response.text and "key_id" not in response.text
    return response


def saved(client, headers):
    response = request(client, headers, "PUT", body=DRAFT)
    assert response.status_code == 200, response.text
    return response.json()["config"]


def test_get_public_metadata_and_no_key(client, dev_headers):
    first = request(client, dev_headers, "GET")
    assert first.json()["available"] is True and first.json()["config"] is None
    providers = first.json()["providers"]
    assert {p["id"] for p in providers} == {"dashscope", "deepseek", "moonshot", "zhipu", "anthropic", "custom"}
    expected = {"provider", "model", "base_url", "key_last4", "enabled", "status", "updated_at"}
    config = saved(client, dev_headers)
    assert set(config) == expected and config["enabled"] is True and config["status"] == "ok"
    assert config["key_last4"] == SECRET[-4:]
    assert request(client, dev_headers, "GET").json()["config"] == config


@pytest.mark.parametrize("body", [
    {**DRAFT, "api_key": "tiny"}, {**DRAFT, "api_key": "x" * 513},
    {**DRAFT, "api_key": SECRET + "\n"}, {**DRAFT, "api_key": SECRET + " "},
    {**DRAFT, "api_key": {"secret": SECRET}}, {**DRAFT, "api_key": [SECRET]},
    {**DRAFT, "api_key": 12345}, {**DRAFT, "provider": "unknown"},
    {**DRAFT, "model": "claude-unsupported"}, {**DRAFT, "model": "has space"},
    {**DRAFT, "model": "x" * 101}, {"provider": "anthropic", "model": "claude-opus-5-5"},
    {**DRAFT, "extra": SECRET}, [], None,
    {"provider": "custom", "model": "custom-model", "base_url": "http://127.0.0.1", "api_key": SECRET},
], ids=["short-key", "long-key", "newline-key", "space-key", "object-key", "list-key", "numeric-key", "provider", "claude-model", "model-format", "long-model", "first-key-required", "extra", "array", "null", "custom-url"])
def test_invalid_put_is_fixed_400_without_echo(client, dev_headers, body):
    response = request(client, dev_headers, "PUT", body=body)
    assert response.status_code == 400, response.text
    assert set(response.json()) == {"detail"}
    assert request(client, dev_headers, "GET").json()["config"] is None


def test_model_edit_retains_key_and_switch_state(client, dev_headers):
    saved(client, dev_headers)
    disabled = request(client, dev_headers, "PATCH", body={"enabled": False})
    assert disabled.json()["config"]["enabled"] is False
    response = request(client, dev_headers, "PUT", body={"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": None, "base_url": None})
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["key_last4"] == SECRET[-4:] and config["enabled"] is False
    assert request(client, dev_headers, "PATCH", body={"enabled": True}).json()["config"]["enabled"] is True
    assert request(client, dev_headers, "DELETE").status_code == 204
    assert request(client, dev_headers, "GET").json()["config"] is None
    assert request(client, dev_headers, "PATCH", body={"enabled": True}).status_code == 404


@pytest.mark.parametrize("body", [{"enabled": None}, {"enabled": "yes"}, {"enabled": 1}, {}, {"enabled": True, "extra": 1}])
def test_invalid_patch_fixed_400(client, dev_headers, body):
    saved(client, dev_headers)
    assert request(client, dev_headers, "PATCH", body=body).status_code == 400


def test_provider_change_requires_new_key(client, dev_headers):
    saved(client, dev_headers)
    response = request(client, dev_headers, "PUT", body={"provider": "deepseek", "model": "deepseek-v4-pro"})
    assert response.status_code == 400
    assert response.json()["detail"] == "更换厂商或地址需要重新填写 Key"
    assert request(client, dev_headers, "GET").json()["config"]["provider"] == "anthropic"


def test_needs_reentry_cannot_be_enabled(client, dev_headers):
    import database
    saved(client, dev_headers)
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE user_model_configs SET key_ciphertext = ?, enabled = 0", (b"corrupt",))
    config = request(client, dev_headers, "GET").json()["config"]
    assert config["status"] == "needs_reentry"
    response = request(client, dev_headers, "PATCH", body={"enabled": True})
    assert response.status_code == 400 and response.json()["detail"] == "配置需要重新填写 Key"
    assert request(client, dev_headers, "DELETE").status_code == 204


@pytest.mark.parametrize("unavailable", ["missing", "invalid", "anthropic_override"])
def test_unavailable_get_and_save(client, dev_headers, monkeypatch, unavailable):
    if unavailable == "missing":
        monkeypatch.delenv("FIONA_BYOK_SECRET")
    elif unavailable == "invalid":
        monkeypatch.setenv("FIONA_BYOK_SECRET", "not-a-key")
    else:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://private.example.net")
    payload = request(client, dev_headers, "GET").json()
    assert payload["available"] is False and payload["unavailable_reason"] == "服务器暂未开启自带模型"
    assert request(client, dev_headers, "PUT", body=DRAFT).status_code == 503


class ProviderFailure(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__(SECRET + " https://private.example.net claude-opus-5-5")


@pytest.mark.parametrize("failure", [None, ProviderFailure(401), ProviderFailure(403), ProviderFailure(404), ProviderFailure(402), ProviderFailure(429), ProviderFailure(400), TimeoutError(), openai.APIConnectionError(request=httpx.Request("POST", "https://private.example.net")), NeedsReentryError(), ByokUnavailableError()])
def test_connection_classification_and_never_saves(client, dev_headers, monkeypatch, failure):
    import routers.chat_model as route
    calls = []
    async def connection(config):
        calls.append(config)
        if failure:
            raise failure
    monkeypatch.setattr(route, "run_byok_connection_test", connection)
    response = request(client, dev_headers, "POST", path="/chat-model/test", body=DRAFT)
    assert response.status_code == 200
    assert response.json() == ({"ok": False, "message": error_message(failure)} if failure else {"ok": True, "message": "连接成功"})
    assert calls[0]["api_key"] == SECRET
    assert request(client, dev_headers, "GET").json()["config"] is None


def test_connection_reuses_stored_key_and_draft_never_changes_it(client, dev_headers, monkeypatch):
    import routers.chat_model as route
    saved(client, dev_headers)
    calls = []
    async def connection(config):
        calls.append(config.copy())
    monkeypatch.setattr(route, "run_byok_connection_test", connection)
    before = request(client, dev_headers, "GET").json()["config"]
    assert request(client, dev_headers, "POST", path="/chat-model/test", body={}).json()["ok"] is True
    assert calls[-1]["api_key"] == SECRET
    assert request(client, dev_headers, "POST", path="/chat-model/test", body={"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "sk-draft-new-key"}).json()["ok"] is True
    assert calls[-1]["provider"] == "deepseek"
    assert request(client, dev_headers, "GET").json()["config"] == before
    failed = request(client, dev_headers, "POST", path="/chat-model/test", body={"provider": "deepseek", "model": "deepseek-v4-pro"})
    assert failed.status_code == 200 and failed.json() == {"ok": False, "message": "更换厂商或地址需要重新填写 Key"}


def test_test_daily_cap_does_not_call_or_save(client, dev_headers, monkeypatch):
    import database
    import routers.chat_model as route
    from auth import create_token
    from rate_limit import limiter
    client.get("/chat-model", headers=dev_headers)
    user = dev_headers["X-Dev-User"]
    version = asyncio.run(database.get_session_version(user))
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("FIONA_DAILY_BYOK_TESTS", "1")
    monkeypatch.setattr(limiter, "enabled", True)
    calls = []
    async def connection(config):
        calls.append(1)
    monkeypatch.setattr(route, "run_byok_connection_test", connection)
    assert request(client, headers, "POST", path="/chat-model/test", body=DRAFT).json()["ok"] is True
    second = request(client, headers, "POST", path="/chat-model/test", body=DRAFT)
    assert second.status_code == 200 and second.json() == {"ok": False, "message": "今天测试自带模型连接的次数已用完，明天再试"}
    assert calls == [1] and request(client, headers, "GET").json()["config"] is None


@pytest.mark.parametrize("path", ["/chat-model", "/chat-model/", "/chat-model/test", "/chat-model/test/"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer expired-invalid"}])
def test_new_interfaces_require_login_without_401(client, monkeypatch, path, headers):
    monkeypatch.setenv("DEV_MODE", "0")
    response = request(client, headers, "GET" if path.rstrip("/") == "/chat-model" else "POST", path=path, body={})
    assert response.status_code == 403 and response.json() == {"detail": "未鉴权或鉴权失败"}


def test_malformed_json_never_echoes_key(client, dev_headers):
    response = client.put("/chat-model", headers={**dev_headers, "Content-Type": "application/json"}, content='{"api_key":"' + SECRET)
    assert response.status_code == 400 and SECRET not in response.text
    response = client.post("/chat-model/test", headers={**dev_headers, "Content-Type": "application/json"}, content='{"api_key":"' + SECRET)
    assert response.status_code == 200 and response.json()["ok"] is False and SECRET not in response.text


def test_connection_minute_cap_returns_200_without_eleventh_call(client, dev_headers, monkeypatch):
    import routers.chat_model as route
    from rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", True)
    calls = []
    async def connection(config):
        calls.append(1)
    monkeypatch.setattr(route, "run_byok_connection_test", connection)
    for _ in range(10):
        assert request(client, dev_headers, "POST", path="/chat-model/test", body=DRAFT).json()["ok"] is True
    exceeded = request(client, dev_headers, "POST", path="/chat-model/test", body=DRAFT)
    assert exceeded.status_code == 200
    assert exceeded.json() == {"ok": False, "message": "操作太频繁，请稍后再试"}
    assert len(calls) == 10


def test_r2_connection_minute_cap_uses_platform_message(client, dev_headers, monkeypatch):
    import routers.chat_model as route
    from rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", True)
    calls = []
    async def connection(config):
        calls.append(1)
    monkeypatch.setattr(route, "run_byok_connection_test", connection)
    for _ in range(10):
        assert request(client, dev_headers, "POST", path="/chat-model/test/", body=DRAFT).json()["ok"] is True
    exceeded = request(client, dev_headers, "POST", path="/chat-model/test/", body=DRAFT)
    assert exceeded.status_code == 200
    assert exceeded.json() == {"ok": False, "message": "操作太频繁，请稍后再试"}
    assert len(calls) == 10
