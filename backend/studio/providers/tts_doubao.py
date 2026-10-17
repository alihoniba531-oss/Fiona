"""豆包语音 2.0（火山引擎单向流式 HTTP）中文配音适配器。

块 B 的单次付费合成。要点：

* 只发一次 POST，不重试；不联网的测试通过 ``_default_transport()`` 注入
  ``httpx.MockTransport``。
* ``additions`` 必须是 JSON 序列化后的字符串。表演指示写进 ``context_texts``，
  音高写进 ``post_process.pitch``（为 0 时省略），两者都没有时整个字段不传。
* 错误分类只看结构化状态码（HTTP 状态码和响应体里的 ``code``），绝不扫错误文本：
  4xx / 45 开头的 8 位 code → rejected，其余（5xx、传输错误、超时、流未正常结束、
  成功码但无音频）→ uncertain。
* 错误信息里不出现 ``VOLC_SPEECH_API_KEY``。
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import uuid
from typing import Any

import httpx

from .base import UNCERTAIN_MESSAGE, safe_message
from .media_errors import MediaCallError
from .tts_cosy import TtsResult


DOUBAO_ENGINE = "doubao"
API_KEY_ENV = "VOLC_SPEECH_API_KEY"
RESOURCE_ENV = "VOLC_SPEECH_RESOURCE_ID"
DOUBAO_AUDIO_FORMAT = "mp3"
DOUBAO_SAMPLE_RATE = 24000
DIRECTION_MAX_CHARS = 200
SYNTHESIS_TIMEOUT_S = 120.0

DEFAULT_RESOURCE_ID = "seed-tts-2.0"
ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
_SUCCESS_CODE = "20000000"
_REJECTED_MESSAGE = "上游拒绝，已释放预留"
_UPSTREAM_CODE_RE = re.compile(r"\d{1,10}")
_MAX_MESSAGE_CHARS = 200


def _default_transport() -> httpx.AsyncBaseTransport | None:
    """真实调用走 httpx 默认传输；测试 monkeypatch 本函数注入 MockTransport。"""
    return None


def doubao_configured() -> bool:
    """Key 存在且非空。"""
    return bool(os.getenv(API_KEY_ENV, "").strip())


def _redact(value: Any) -> str:
    """上游说明可以保留，但 Key 不能进入任何错误文本，且最多 200 字。"""
    result = safe_message(value)
    key = os.getenv(API_KEY_ENV, "").strip()
    if key:
        result = result.replace(key, "[已隐藏]")
    return result[:_MAX_MESSAGE_CHARS]


def _error_code(raw_code: Any) -> str:
    """上游 code 只接受 1–10 位纯数字，其余一律落 doubao_unknown。"""
    text = "" if raw_code is None else str(raw_code).strip()
    if _UPSTREAM_CODE_RE.fullmatch(text):
        return f"doubao_{text}"
    return "doubao_unknown"


def _resource_id() -> str:
    return os.getenv(RESOURCE_ENV, "").strip() or DEFAULT_RESOURCE_ID


def _speech_rate(rate: float) -> int:
    """0.5–2.0 倍速换算成 [-50, 100]，超出范围截断。"""
    value = round((float(rate) - 1) * 100)
    return max(-50, min(100, value))


def _pitch_value(pitch: int | float) -> int:
    if isinstance(pitch, bool):
        raise ValueError("pitch 必须是 -12 到 12 的整数")
    if isinstance(pitch, int):
        value = pitch
    elif isinstance(pitch, float) and pitch.is_integer():
        value = int(pitch)
    else:
        raise ValueError("pitch 必须是 -12 到 12 的整数")
    if not -12 <= value <= 12:
        raise ValueError("pitch 必须是 -12 到 12 的整数")
    return value


def _request_body(text: str, *, voice: str, rate: float, pitch: int, direction: str) -> dict:
    additions: dict[str, Any] = {}
    if direction:
        additions["context_texts"] = [direction]
    if pitch:
        additions["post_process"] = {"pitch": pitch}
    req_params: dict[str, Any] = {
        "text": text,
        "speaker": voice,
        "audio_params": {
            "format": DOUBAO_AUDIO_FORMAT,
            "sample_rate": DOUBAO_SAMPLE_RATE,
            "speech_rate": _speech_rate(rate),
        },
    }
    if additions:
        # 官方要求：additions 是 JSON 字符串，不能直接传对象。
        req_params["additions"] = json.dumps(additions, ensure_ascii=False)
    return {"user": {"uid": "fiona-studio"}, "req_params": req_params}


def _decode_audio(value: Any) -> bytes:
    if value is None or value == "":
        return b""
    if not isinstance(value, str):
        raise MediaCallError("uncertain", "doubao_invalid_audio", UNCERTAIN_MESSAGE)
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise MediaCallError("uncertain", "doubao_invalid_audio", UNCERTAIN_MESSAGE) from None


def _code_error(code: str, message: Any) -> MediaCallError:
    """响应体里 45 开头的 8 位 code 是明确的拒绝，其余都是 uncertain。"""
    normalized = code.strip()
    if normalized.isdigit() and len(normalized) == 8 and normalized.startswith("45"):
        return MediaCallError("rejected", _error_code(normalized),
                              _redact(message) if message else _REJECTED_MESSAGE)
    return MediaCallError("uncertain", _error_code(normalized), UNCERTAIN_MESSAGE)


def _http_error(status: int, raw: bytes) -> MediaCallError:
    code = ""
    message: Any = ""
    text = raw.decode("utf-8", errors="replace").strip()
    data: Any = None
    if text:
        try:
            data = json.loads(text)
        except ValueError:
            data = None
    if isinstance(data, dict):
        raw_code = data.get("code")
        if raw_code is not None:
            code = str(raw_code).strip()
        message = data.get("message") or data.get("msg") or ""
    elif text:
        message = text
    error_code = _error_code(code) if code else f"doubao_http_{status}"
    if 400 <= status < 500:
        return MediaCallError("rejected", error_code,
                              _redact(message) if message else _REJECTED_MESSAGE)
    return MediaCallError("uncertain", error_code, UNCERTAIN_MESSAGE)


def _parse_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        raise MediaCallError("uncertain", "doubao_invalid_response", UNCERTAIN_MESSAGE) from None
    if not isinstance(data, dict):
        raise MediaCallError("uncertain", "doubao_invalid_response", UNCERTAIN_MESSAGE)
    return data


async def _collect(*, body: dict, api_key: str,
                   transport: httpx.AsyncBaseTransport | None) -> bytes:
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": _resource_id(),
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(SYNTHESIS_TIMEOUT_S),
        follow_redirects=False,
    ) as client:
        async with client.stream("POST", ENDPOINT, headers=headers, json=body) as response:
            if not 200 <= response.status_code < 300:
                raw = await response.aread()
                raise _http_error(response.status_code, raw)

            audio = bytearray()
            finished = False
            async for line in response.aiter_lines():
                payload = _parse_line(line)
                if payload is None:
                    continue
                code = payload.get("code")
                code = "" if code is None else str(code).strip()
                message = payload.get("message") or payload.get("msg") or ""
                if code and code != "0":
                    if code == _SUCCESS_CODE:
                        finished = True
                        audio.extend(_decode_audio(payload.get("data")))
                        break
                    raise _code_error(code, message)
                audio.extend(_decode_audio(payload.get("data")))

    if not finished:
        raise MediaCallError("uncertain", "doubao_incomplete_stream", UNCERTAIN_MESSAGE)
    if not audio:
        raise MediaCallError("uncertain", "doubao_empty_audio", UNCERTAIN_MESSAGE)
    return bytes(audio)


async def synthesize_doubao(text: str, *, voice: str, rate: float = 1.0, pitch: int = 0,
                            direction: str = "", transport=None) -> TtsResult:
    """合成一段中文台词（单次付费调用）。"""
    direction_text = (direction or "").strip()
    if len(direction_text) > DIRECTION_MAX_CHARS:
        raise ValueError(f"表演指示最多 {DIRECTION_MAX_CHARS} 字")
    pitch_value = _pitch_value(pitch)
    # 请求体在发 POST 之前构造：参数 / 序列化错误属于发送前失败，不能被归为 uncertain。
    body = _request_body(text, voice=voice, rate=rate, pitch=pitch_value, direction=direction_text)

    api_key = os.getenv(API_KEY_ENV, "").strip()
    if not api_key:
        raise MediaCallError("rejected", "doubao_key_missing",
                             "未配置 VOLC_SPEECH_API_KEY，没有提交合成请求")

    injected = transport if transport is not None else _default_transport()
    try:
        audio = await asyncio.wait_for(
            _collect(body=body, api_key=api_key, transport=injected),
            timeout=SYNTHESIS_TIMEOUT_S,
        )
    except MediaCallError:
        raise
    except (TimeoutError, asyncio.TimeoutError):
        raise MediaCallError("uncertain", "doubao_timeout", UNCERTAIN_MESSAGE) from None
    except httpx.TimeoutException:
        raise MediaCallError("uncertain", "doubao_timeout", UNCERTAIN_MESSAGE) from None
    except httpx.TransportError:
        raise MediaCallError("uncertain", "doubao_transport_error", UNCERTAIN_MESSAGE) from None
    except Exception:
        raise MediaCallError("uncertain", "doubao_error", UNCERTAIN_MESSAGE) from None

    return TtsResult(audio=audio, audio_format=DOUBAO_AUDIO_FORMAT,
                     sample_rate=DOUBAO_SAMPLE_RATE, chars=len(text),
                     engine=DOUBAO_ENGINE, voice=voice, words=[])
