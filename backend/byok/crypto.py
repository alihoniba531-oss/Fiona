"""Per-user authenticated encryption; secrets are read for each operation."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import ByokUnavailableError, NeedsReentryError

FORBIDDEN_ENV = (
    "OPENAI_ORG_ID", "OPENAI_PROJECT_ID", "OPENAI_CUSTOM_HEADERS", "OPENAI_BASE_URL",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE",
    "ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE",
    "ANTHROPIC_CUSTOM_HEADERS",
)
_UNAVAILABLE_REASON = "服务器暂未开启自带模型"
_warned: set[str] = set()


def _warn_once(name: str) -> None:
    if name not in _warned:
        _warned.add(name)
        logging.getLogger(__name__).warning("BYOK configuration unavailable category=%s", name)


def _decode_secret(raw: str) -> bytes:
    try:
        secret = base64.b64decode(raw.encode("ascii"), altchars=b"-_", validate=True)
        if len(secret) != 32 or base64.urlsafe_b64encode(secret).decode() != raw:
            raise ValueError
        return secret
    except (ValueError, UnicodeError):
        raise ByokUnavailableError from None


def current_secret() -> bytes:
    try:
        return _decode_secret(os.getenv("FIONA_BYOK_SECRET", ""))
    except ByokUnavailableError:
        _warn_once("secret")
        raise


def availability() -> tuple[bool, str | None]:
    try:
        current_secret()
    except ByokUnavailableError:
        return False, _UNAVAILABLE_REASON
    if any(os.getenv(name, "") for name in FORBIDDEN_ENV):
        _warn_once("environment")
        return False, _UNAVAILABLE_REASON
    return True, None


def ensure_available() -> None:
    if not availability()[0]:
        raise ByokUnavailableError


def key_id(secret: bytes) -> str:
    return hmac.new(secret, b"fiona:byok:key-id:v1", hashlib.sha256).hexdigest()[:16]


def _aad(username: str, provider: str, base_url: str | None) -> bytes:
    return f"fiona:byok:v1|{username}|{provider}|{base_url or ''}".encode()


def encrypt_key(api_key: str, username: str, provider: str, base_url: str | None = None) -> tuple[bytes, str]:
    secret = current_secret()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(secret).encrypt(nonce, api_key.encode(), _aad(username, provider, base_url))
    return b"\x01" + nonce + encrypted, key_id(secret)


def decrypt_key(ciphertext: bytes, stored_key_id: str, username: str, provider: str, base_url: str | None = None) -> str:
    # A missing current key makes the entire feature unavailable, including rotation.
    current = current_secret()
    if not isinstance(stored_key_id, str) or not re.fullmatch(r"[0-9a-f]{16}", stored_key_id):
        raise NeedsReentryError
    keys = [current]
    for raw in os.getenv("FIONA_BYOK_SECRET_PREVIOUS", "").split(","):
        if not raw.strip():
            continue
        try:
            keys.append(_decode_secret(raw.strip()))
        except ByokUnavailableError:
            _warn_once("previous_secret")
    selected = next((secret for secret in keys if hmac.compare_digest(key_id(secret), stored_key_id)), None)
    if selected is None or not isinstance(ciphertext, bytes) or len(ciphertext) < 30 or ciphertext[0] != 1:
        raise NeedsReentryError
    try:
        return AESGCM(selected).decrypt(ciphertext[1:13], ciphertext[13:], _aad(username, provider, base_url)).decode()
    except Exception:
        raise NeedsReentryError from None
