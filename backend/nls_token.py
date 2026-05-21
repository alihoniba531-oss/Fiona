# -*- coding: utf-8 -*-
"""
阿里云 NLS（智能语音交互）Token 生成。
用于前端 WebSocket 直连 NLS 实时语音识别。
"""
import os
import hmac
import hashlib
import base64
import time
import uuid
import requests
from urllib.parse import quote, urlencode


def _percent_encode(s: str) -> str:
    """阿里云 POP API 专用百分号编码"""
    return quote(s, safe="").replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _build_canonical_query(params: dict) -> str:
    """按参数名排序，构造规范化查询字符串"""
    sorted_keys = sorted(params.keys())
    parts = []
    for k in sorted_keys:
        parts.append(f"{_percent_encode(k)}={_percent_encode(str(params[k]))}")
    return "&".join(parts)


def generate_nls_token() -> dict:
    """生成阿里云 NLS WebSocket 连接所需的 token"""
    access_key_id = os.environ.get("ALIYUN_ACCESS_KEY_ID", "")
    access_key_secret = os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "")
    appkey = os.environ.get("ALIYUN_ASR_APPKEY", "XsXKe3FI9rDRTjLI")

    if not access_key_id or not access_key_secret:
        return {"error": "missing ALIYUN_ACCESS_KEY_ID or ALIYUN_ACCESS_KEY_SECRET"}

    # 请求参数
    params = {
        "AccessKeyId": access_key_id,
        "Action": "CreateToken",
        "Version": "2019-02-28",
        "Format": "JSON",
        "RegionId": "cn-shanghai",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
    }

    # 构造规范化查询字符串 & 签名字符串
    canonical = _build_canonical_query(params)
    string_to_sign = f"GET&{_percent_encode('/')}&{_percent_encode(canonical)}"

    # HMAC-SHA1 签名
    key = access_key_secret.encode("utf-8") + b"&"
    hmac_obj = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1)
    signature = base64.b64encode(hmac_obj.digest()).decode("utf-8")

    # 拼接完整 URL
    full_url = f"https://nls-meta.cn-shanghai.aliyuncs.com/?{canonical}&Signature={_percent_encode(signature)}"

    try:
        resp = requests.get(full_url, timeout=5)
        data = resp.json()
        token_id = data.get("Token", {}).get("Id", "")
    except Exception as e:
        return {"error": f"token request failed: {e}"}

    if not token_id:
        return {"error": "empty token", "raw": str(data)[:300]}

    # WebSocket URL（前端直接用）
    ws_url = (
        f"wss://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/asr"
        f"?appkey={appkey}"
        f"&token={token_id}"
        f"&format=pcm"
        f"&sample_rate=16000"
    )

    return {
        "token": token_id,
        "ws_url": ws_url,
        "appkey": appkey,
        "expires_in": 86400,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    result = generate_nls_token()
    print("Token result:", {k: (v[:50] if k == "token" else v) for k, v in result.items()})
