# -*- coding: utf-8 -*-
"""
JWT 鉴权工具。
- make_otp()       生成 6 位验证码
- create_token()          签发带会话版本的 JWT
- decode_token_claims()   解析并校验 JWT claims
- decode_token()          兼容 helper，仅返回 username 或 None
"""
import os
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=False)

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    if os.getenv("DEV_MODE", "0") == "1":
        SECRET_KEY = "fiona-dev-secret-change-in-prod-xxxxx"
    else:
        raise RuntimeError("JWT_SECRET must be set when DEV_MODE is not 1")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def make_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_token(username: str, session_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {
            "sub": username,
            "sv": session_version,
            "iat": now,
            "jti": secrets.token_urlsafe(16),
            "exp": exp,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token_claims(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        session_version = payload.get("sv", 0)  # 兼容本次迁移前签发的 token
        if not isinstance(username, str) or not username.strip():
            return None
        if not isinstance(session_version, int) or session_version < 0:
            return None
        return {**payload, "sub": username, "sv": session_version}
    except Exception:
        return None


def decode_token(token: str) -> str | None:
    claims = decode_token_claims(token)
    return claims["sub"] if claims else None
