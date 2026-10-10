"""Transactional configuration storage. Table creation belongs to database.init_db."""
from __future__ import annotations

import asyncio
import unicodedata
import aiosqlite
import database

from .crypto import decrypt_key, encrypt_key, ensure_available
from .errors import ConfigurationError, ConfigNotFoundError, NeedsReentryError, ByokUnavailableError, UserDeletedError
from .providers import PROVIDERS, validate_model, validate_provider
from .url_safety import normalize_custom_base_url, validate_custom_base_url, UnsafeUrlError

USER_MODEL_CONFIGS_DDL = """
    CREATE TABLE IF NOT EXISTS user_model_configs (
        username TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        base_url TEXT DEFAULT NULL,
        model TEXT NOT NULL,
        key_ciphertext BLOB NOT NULL,
        key_id TEXT NOT NULL,
        key_last4 TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""
_PUBLIC_FIELDS = ("provider", "base_url", "model", "key_last4", "enabled", "updated_at")


async def _read_row(username: str) -> dict | None:
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_model_configs WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


def _public(row: dict) -> dict:
    result = {field: row[field] for field in _PUBLIC_FIELDS}
    result["enabled"] = bool(result["enabled"])
    try:
        decrypt_key(row["key_ciphertext"], row["key_id"], row["username"], row["provider"], row["base_url"])
        result["status"] = "ok"
    except (NeedsReentryError, ByokUnavailableError):
        result["status"] = "needs_reentry"
    return result


async def get_public_config(username: str) -> dict | None:
    row = await _read_row(username)
    return _public(row) if row else None


async def get_internal_config(username: str) -> dict | None:
    row = await _read_row(username)
    if row is None:
        return None
    result = _public(row)
    result["api_key"] = None
    if result["enabled"]:
        try:
            ensure_available()
            result["api_key"] = decrypt_key(row["key_ciphertext"], row["key_id"], username, row["provider"], row["base_url"])
        except (ByokUnavailableError, NeedsReentryError) as exc:
            # Expose only a preset id to let chat attribute failed BYOK traces.
            if row["provider"] in PROVIDERS:
                exc.byok_provider = row["provider"]
            raise
    return result


async def has_enabled_config(username: str) -> bool:
    row = await _read_row(username)
    return bool(row and row["enabled"])


def validate_api_key(api_key: object) -> str:
    if not isinstance(api_key, str) or not 8 <= len(api_key) <= 512 or any(c.isspace() or unicodedata.category(c) == "Cc" for c in api_key):
        raise ConfigurationError("Key 格式不正确")
    return api_key


async def prepare_config(username: str, *, provider=None, model=None, base_url=None, api_key=None) -> dict:
    """Validate a draft without saving; reuse a stored key only for the same AAD."""
    ensure_available()
    old = await _read_row(username)
    if provider is None:
        if old is None:
            raise ConfigNotFoundError
        provider = old["provider"]
    provider = validate_provider(provider)
    if model is None:
        if old and old["provider"] == provider:
            model = old["model"]
        else:
            model = PROVIDERS[provider].get("default_model")
    model = validate_model(provider, model)
    if provider == "custom":
        if base_url is None and old and old["provider"] == provider:
            base_url = old["base_url"]
        try:
            base_url = normalize_custom_base_url(base_url)
            await asyncio.to_thread(validate_custom_base_url, base_url)
        except UnsafeUrlError:
            raise ConfigurationError("须为可公网访问的 HTTPS 地址") from None
    else:
        base_url = None
    if api_key is not None:
        api_key = validate_api_key(api_key)
    elif old is None:
        raise ConfigurationError("请填写 Key")
    elif (old["provider"], old["base_url"]) != (provider, base_url):
        raise ConfigurationError("更换厂商或地址需要重新填写 Key")
    else:
        api_key = decrypt_key(old["key_ciphertext"], old["key_id"], username, provider, base_url)
    return {"provider": provider, "model": model, "base_url": base_url, "api_key": api_key,
            "key_last4": api_key[-4:], "enabled": bool(old["enabled"]) if old else True, "status": "ok"}


async def save_config(username: str, *, provider, model, base_url=None, api_key=None) -> dict:
    config = await prepare_config(username, provider=provider, model=model, base_url=base_url, api_key=api_key)
    ciphertext, identifier = encrypt_key(config["api_key"], username, config["provider"], config["base_url"])
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await database._users_exist(db, username):
            raise UserDeletedError
        # Keep the existing enabled value, including switches during draft validation.
        await db.execute("""
            INSERT INTO user_model_configs (username, provider, base_url, model, key_ciphertext, key_id, key_last4, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(username) DO UPDATE SET provider=excluded.provider, base_url=excluded.base_url,
                model=excluded.model, key_ciphertext=excluded.key_ciphertext, key_id=excluded.key_id,
                key_last4=excluded.key_last4, updated_at=CURRENT_TIMESTAMP
        """, (username, config["provider"], config["base_url"], config["model"], ciphertext, identifier, config["key_last4"]))
        await db.commit()
    result = await get_public_config(username)
    if result is None:
        raise UserDeletedError
    return result


async def set_enabled(username: str, enabled: bool) -> dict:
    if not isinstance(enabled, bool):
        raise ConfigurationError("启用状态格式不正确")
    if enabled:
        ensure_available()
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        await db.execute("BEGIN IMMEDIATE")
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_model_configs WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ConfigNotFoundError
        if enabled and _public(dict(row))["status"] != "ok":
            raise ConfigurationError("配置需要重新填写 Key")
        await db.execute("UPDATE user_model_configs SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?", (int(enabled), username))
        await db.commit()
    result = await get_public_config(username)
    if result is None:
        raise ConfigNotFoundError
    return result


async def delete_config(username: str) -> None:
    async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
        await db.execute("DELETE FROM user_model_configs WHERE username = ?", (username,))
        await db.commit()
