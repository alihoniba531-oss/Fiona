"""Offline tests for encrypted, account-bound model settings."""
import asyncio
import base64
import socket
import urllib.request

import aiosqlite
import httpcore
import httpcore2
import httpx
import httpx2
import pytest
import requests

import database
from byok import crypto, store
from byok.errors import ByokUnavailableError, ConfigurationError, NeedsReentryError, UserDeletedError
from utils import safe_http

SECRET = base64.urlsafe_b64encode(b"a" * 32).decode()
NEW_SECRET = base64.urlsafe_b64encode(b"b" * 32).decode()


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    for target, name in ((urllib.request, "urlopen"), (requests, "get"), (safe_http, "_open_pinned"), (socket, "getaddrinfo"), (httpcore.SyncBackend, "connect_tcp"), (httpcore.SyncBackend, "connect_unix_socket"), (httpx.HTTPTransport, "handle_request"), (httpx.AsyncHTTPTransport, "handle_async_request"), (httpx2.HTTPTransport, "handle_request"), (httpx2.AsyncHTTPTransport, "handle_async_request")):
        monkeypatch.setattr(target, name, blocked)
    monkeypatch.setattr(httpcore2.SyncBackend, "connect_tcp", blocked)
    monkeypatch.setattr(httpcore2.SyncBackend, "connect_unix_socket", blocked)
    monkeypatch.setenv("FIONA_BYOK_SECRET", SECRET)
    monkeypatch.delenv("FIONA_BYOK_SECRET_PREVIOUS", raising=False)
    for name in crypto.FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    yield
    assert not attempted, "network"


@pytest.fixture
def config_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "byok.db"))

    async def setup():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(store.USER_MODEL_CONFIGS_DDL)
            await db.execute("INSERT INTO users(username) VALUES ('alice')")
            await db.commit()

    asyncio.run(setup())


def test_encrypt_roundtrip_and_random_nonce():
    first, identifier = crypto.encrypt_key("sk-secret-a123", "alice", "custom", "https://api.example.net/v1")
    second, _ = crypto.encrypt_key("sk-secret-a123", "alice", "custom", "https://api.example.net/v1")
    assert first[0] == 1 and len(first) == 1 + 12 + len("sk-secret-a123") + 16
    assert first != second
    assert crypto.decrypt_key(first, identifier, "alice", "custom", "https://api.example.net/v1") == "sk-secret-a123"
    assert len(identifier) == 16


@pytest.mark.parametrize("username,provider,url", [("bob", "custom", "https://api.example.net/v1"), ("alice", "deepseek", "https://api.example.net/v1"), ("alice", "custom", "https://other.example.net/v1")])
def test_aad_binding(username, provider, url):
    ciphertext, identifier = crypto.encrypt_key("sk-secret-a123", "alice", "custom", "https://api.example.net/v1")
    with pytest.raises(NeedsReentryError):
        crypto.decrypt_key(ciphertext, identifier, username, provider, url)


def test_previous_key_and_reencrypt_on_save(config_db, monkeypatch):
    async def scenario():
        await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro", api_key="sk-secret-a123")
        old = await store._read_row("alice")
        monkeypatch.setenv("FIONA_BYOK_SECRET", NEW_SECRET)
        with pytest.raises(NeedsReentryError):
            await store.get_internal_config("alice")
        monkeypatch.setenv("FIONA_BYOK_SECRET_PREVIOUS", SECRET)
        assert (await store.get_internal_config("alice"))["api_key"] == "sk-secret-a123"
        await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro")
        new = await store._read_row("alice")
        assert old["key_id"] != new["key_id"]
        monkeypatch.delenv("FIONA_BYOK_SECRET_PREVIOUS")
        assert (await store.get_internal_config("alice"))["api_key"] == "sk-secret-a123"
    asyncio.run(scenario())


@pytest.mark.parametrize("value", [None, "", "not-base64", base64.urlsafe_b64encode(b"short").decode()])
def test_secret_unavailable_without_import_failure(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("FIONA_BYOK_SECRET")
    else:
        monkeypatch.setenv("FIONA_BYOK_SECRET", value)
    assert crypto.availability() == (False, "服务器暂未开启自带模型")
    with pytest.raises(ByokUnavailableError):
        crypto.encrypt_key("key12345", "alice", "deepseek")


def test_key_id_selects_matching_key(monkeypatch):
    ciphertext, identifier = crypto.encrypt_key("key12345", "alice", "deepseek")
    monkeypatch.setenv("FIONA_BYOK_SECRET", NEW_SECRET)
    monkeypatch.setenv("FIONA_BYOK_SECRET_PREVIOUS", f"invalid,{SECRET}")
    assert crypto.decrypt_key(ciphertext, identifier, "alice", "deepseek") == "key12345"
    with pytest.raises(NeedsReentryError):
        crypto.decrypt_key(ciphertext, "0" * 16, "alice", "deepseek")


@pytest.mark.parametrize("identifier", [None, 1234, "中文", "f" * 15, "F" * 16])
def test_invalid_stored_key_id_needs_reentry(identifier):
    ciphertext, _ = crypto.encrypt_key("key12345", "alice", "deepseek")
    with pytest.raises(NeedsReentryError):
        crypto.decrypt_key(ciphertext, identifier, "alice", "deepseek")


def test_public_fields_patch_delete_and_bad_ciphertext(config_db):
    async def scenario():
        public = await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro", api_key="sk-secret-a123")
        assert set(public) == {"provider", "base_url", "model", "key_last4", "enabled", "status", "updated_at"}
        assert public["status"] == "ok" and public["key_last4"] == "a123"
        assert "sk-secret" not in repr(public)
        await store.set_enabled("alice", False)
        await store.save_config("alice", provider="deepseek", model="other-model")
        assert not (await store.get_public_config("alice"))["enabled"]
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE user_model_configs SET key_ciphertext = ?", (b"bad",))
            await db.commit()
        assert (await store.get_public_config("alice"))["status"] == "needs_reentry"
        assert (await store.get_internal_config("alice"))["api_key"] is None
        with pytest.raises(ConfigurationError, match="配置需要重新填写 Key"):
            await store.set_enabled("alice", True)
        await store.delete_config("alice")
        assert await store.get_public_config("alice") is None
    asyncio.run(scenario())


def test_enabled_config_errors_do_not_become_unconfigured(config_db, monkeypatch):
    async def scenario():
        await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro", api_key="sk-secret-a123")
        monkeypatch.delenv("FIONA_BYOK_SECRET")
        assert await store.has_enabled_config("alice")
        with pytest.raises(ByokUnavailableError) as exc:
            await store.get_internal_config("alice")
        assert exc.value.byok_provider == "deepseek"
    asyncio.run(scenario())


def test_account_delete_rebuild_and_late_save(config_db):
    async def scenario():
        await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro", api_key="sk-secret-a123")
        await database.delete_account_data("alice")
        assert await store.get_public_config("alice") is None
        with pytest.raises(UserDeletedError):
            await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro", api_key="sk-secret-a123")
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("INSERT INTO users(username) VALUES ('alice')")
            await db.commit()
        assert await store.get_public_config("alice") is None
    asyncio.run(scenario())


def test_provider_change_requires_new_key_and_test_draft_never_saves(config_db):
    async def scenario():
        await store.save_config("alice", provider="deepseek", model="deepseek-v4-pro", api_key="sk-secret-a123")
        with pytest.raises(ConfigurationError, match="更换厂商或地址需要重新填写 Key"):
            await store.prepare_config("alice", provider="anthropic", model="claude-opus-5-5")
        draft = await store.prepare_config("alice", provider="anthropic", model="claude-opus-5-5", api_key="sk-draft-b123")
        assert draft["api_key"] == "sk-draft-b123"
        assert (await store.get_public_config("alice"))["provider"] == "deepseek"
    asyncio.run(scenario())


@pytest.mark.parametrize("value", ["short", "a" * 513, "with space", "new\nline", "sk-control-\u0080", ["secret"]])
def test_bad_keys_have_fixed_message(value):
    with pytest.raises(ConfigurationError) as exc:
        store.validate_api_key(value)
    assert exc.value.args == ("Key 格式不正确",)


def test_custom_address_change_requires_new_key(config_db, monkeypatch):
    monkeypatch.setattr(store, "validate_custom_base_url", lambda url: url)

    async def scenario():
        await store.save_config("alice", provider="custom", model="unit", base_url="HTTPS://API.EXAMPLE.NET/v1/", api_key="sk-old-key1234")
        assert (await store.get_public_config("alice"))["base_url"] == "https://api.example.net/v1"
        with pytest.raises(ConfigurationError, match="更换厂商或地址需要重新填写 Key"):
            await store.save_config("alice", provider="custom", model="unit", base_url="https://other.example.net/v1")
        await store.save_config("alice", provider="custom", model="unit", base_url="https://other.example.net/v1", api_key="sk-new-key5678")
        assert (await store.get_internal_config("alice"))["api_key"] == "sk-new-key5678"
    asyncio.run(scenario())


def test_custom_dns_timeout_is_fixed_configuration_failure(config_db, monkeypatch):
    from byok import url_safety

    class TimeoutFuture:
        def result(self, timeout):
            raise TimeoutError

        def cancel(self):
            pass
    monkeypatch.setattr(url_safety._DNS_POOL, "submit", lambda *a: TimeoutFuture())

    async def scenario():
        with pytest.raises(ConfigurationError) as exc:
            await store.save_config("alice", provider="custom", model="unit", base_url="https://api.example.net/v1", api_key="sk-offline-1234")
        assert exc.value.args == ("须为可公网访问的 HTTPS 地址",)
        assert await store.get_public_config("alice") is None
    asyncio.run(scenario())
