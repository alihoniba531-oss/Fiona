# -*- coding: utf-8 -*-
"""
阿里云 NLS 一句话识别（HTTP REST）。
前端录音 → 后端上传 PCM → NLS 识别 → 返回文本。
比 WebSocket 实时方案更稳定。
"""
import os
import time
import uuid
import hmac
import hashlib
import base64
import requests
from urllib.parse import quote


def _percent_encode(s: str) -> str:
    return quote(s, safe="").replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def asr_recognize(audio_bytes: bytes, audio_format: str = "pcm", sample_rate: int = 16000) -> dict:
    """
    调用阿里云 NLS 一句话识别。返回 {"text": "...", "error": "..."}
    """
    ak_id = os.environ.get("ALIYUN_ACCESS_KEY_ID", "")
    ak_secret = os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "")
    appkey = os.environ.get("ALIYUN_ASR_APPKEY", "XsXKe3FI9rDRTjLI")

    if not audio_bytes:
        return {"text": "", "error": "empty audio"}

    # Pop API 签名（同 nls_token.py 逻辑，但 Action=SpeechRecognizer）
    params = {
        "AccessKeyId": ak_id,
        "Action": "SpeechRecognizer",
        "Version": "2019-02-28",
        "Format": "JSON",
        "RegionId": "cn-shanghai",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
    }
    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(str(params[k]))}"
        for k in sorted(params.keys())
    )
    string_to_sign = f"GET&{_percent_encode('/')}&{_percent_encode(canonical)}"
    key = ak_secret.encode("utf-8") + b"&"
    sig = base64.b64encode(hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()).decode("utf-8")

    # NLS 一句话识别 HTTP 地址
    url = (
        f"https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/asr"
        f"?appkey={appkey}"
        f"&format={audio_format}"
        f"&sample_rate={sample_rate}"
        f"&enable_punctuation=true"
        f"&enable_interim_result=false"
    )

    headers = {
        "X-NLS-Token": _get_nls_token(ak_id, ak_secret),
        "Content-Type": "application/octet-stream",
    }

    try:
        resp = requests.post(url, data=audio_bytes, headers=headers, timeout=10)
        data = resp.json()
        if data.get("status") == 20000000:
            return {"text": data.get("result", ""), "error": None}
        return {"text": "", "error": data.get("message", str(data)[:200])}
    except Exception as e:
        return {"text": "", "error": str(e)}


def _get_nls_token(ak_id: str, ak_secret: str) -> str:
    """获取 NLS token（与 nls_token.py 相同签名逻辑）"""
    params = {
        "AccessKeyId": ak_id,
        "Action": "CreateToken",
        "Version": "2019-02-28",
        "Format": "JSON",
        "RegionId": "cn-shanghai",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
    }
    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(str(params[k]))}"
        for k in sorted(params.keys())
    )
    string_to_sign = f"GET&{_percent_encode('/')}&{_percent_encode(canonical)}"
    key = ak_secret.encode("utf-8") + b"&"
    sig = base64.b64encode(hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()).decode("utf-8")
    url = f"https://nls-meta.cn-shanghai.aliyuncs.com/?{canonical}&Signature={_percent_encode(sig)}"
    try:
        resp = requests.get(url, timeout=5)
        return (resp.json().get("Token", {}) or {}).get("Id", "")
    except Exception:
        return ""


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    r = asr_recognize(b"\x00" * 1600, "pcm", 16000)
    print("Result:", r)
