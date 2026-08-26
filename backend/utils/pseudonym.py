# -*- coding: utf-8 -*-
"""不可从低熵用户名反推的场景化匿名标识。"""
import hashlib
import hmac

from auth import SECRET_KEY


def anonymous_id(username: str, namespace: str, length: int = 12) -> str:
    if not username or not namespace:
        raise ValueError("username and namespace are required")
    if length < 8 or length > 64:
        raise ValueError("anonymous id length must be between 8 and 64")

    # 派生独立用途密钥；namespace 让广场作者和社群兴趣无法跨页面直接关联。
    key = hmac.new(
        SECRET_KEY.encode("utf-8"),
        b"fiona:pseudonym:v1",
        hashlib.sha256,
    ).digest()
    digest = hmac.new(
        key,
        f"{namespace}\0{username}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:length]
