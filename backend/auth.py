# -*- coding: utf-8 -*-
"""
JWT 鉴权工具。
- make_otp()       生成 6 位验证码
- create_token()   签发 JWT
- decode_token()   解析 JWT，返回 username 或 None
"""
import os
import secrets
import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = os.getenv("JWT_SECRET", "fiona-dev-secret-change-in-prod-xxxxx")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def make_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_token(username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None
