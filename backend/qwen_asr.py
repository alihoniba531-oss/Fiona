# -*- coding: utf-8 -*-
"""Qwen3-ASR-Flash adapter for one-shot speech recognition."""

import base64
import os
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import dashscope


MODEL = "qwen3-asr-flash"
CHINA_BASE_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
MAX_INPUT_BYTES = 10 * 1024 * 1024

_MIME_TYPES = {
    "wav": "audio/wav",
    "wave": "audio/wav",
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "mp3": "audio/mpeg",
    "mpeg": "audio/mpeg",
    "audio/mpeg": "audio/mpeg",
}


def _field(value: Any, name: str, default: Any = None) -> Any:
    """Read a response field from either a mapping or an SDK object."""
    if isinstance(value, Mapping):
        return value.get(name, default)
    try:
        return getattr(value, name)
    except (AttributeError, KeyError, TypeError):
        return default


def _content_text(content: Any) -> str:
    """Extract text from the content shapes returned by DashScope."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, Mapping):
        text = _field(content, "text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        nested = _field(content, "content")
        return _content_text(nested) if nested is not None else ""
    if isinstance(content, (list, tuple)):
        parts = [_content_text(item) for item in content]
        return "".join(part for part in parts if part).strip()

    text = _field(content, "text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    nested = _field(content, "content")
    return _content_text(nested) if nested is not None else ""


def _choice_text(container: Any) -> str:
    choices = _field(container, "choices")
    if not isinstance(choices, (list, tuple)):
        return ""

    for choice in choices:
        message = _field(choice, "message")
        if message is not None:
            text = _content_text(_field(message, "content"))
            if text:
                return text
            text = _content_text(_field(message, "text"))
            if text:
                return text

        text = _content_text(_field(choice, "content"))
        if text:
            return text
        text = _content_text(_field(choice, "text"))
        if text:
            return text
    return ""


def _extract_text(response: Any) -> str:
    """Defensively parse both native DashScope and compatible response shapes."""
    output = _field(response, "output")
    for container in (output, response):
        if container is None:
            continue
        text = _choice_text(container)
        if text:
            return text
        text = _content_text(_field(container, "text"))
        if text:
            return text
        text = _content_text(_field(container, "content"))
        if text:
            return text
    return ""


def _response_error(response: Any) -> str | None:
    status_code = _field(response, "status_code")
    if status_code is None:
        return None
    try:
        is_success = int(status_code) == HTTPStatus.OK
    except (TypeError, ValueError):
        is_success = False
    if is_success:
        return None

    code = _field(response, "code")
    message = _field(response, "message")
    details = ": ".join(str(value) for value in (code, message) if value)
    return f"Qwen ASR request failed ({status_code})" + (f": {details}" if details else "")


def asr_recognize(audio_bytes: bytes, fmt: str = "wav", sample_rate: int = 16000) -> dict:
    """Recognize a short audio clip and return ``{"text": ...}``.

    ``sample_rate`` is kept for signature compatibility. The caller supplies a
    self-describing WAV container, so the service reads its rate from the file.
    """
    del sample_rate

    if not audio_bytes:
        return {"text": "", "error": "empty audio"}
    if len(audio_bytes) > MAX_INPUT_BYTES:
        return {
            "text": "",
            "error": f"audio exceeds Qwen ASR 10 MB limit ({len(audio_bytes)} bytes)",
        }

    normalized_format = (fmt or "").lower().lstrip(".")
    mime_type = _MIME_TYPES.get(normalized_format)
    if mime_type is None:
        return {"text": "", "error": f"unsupported audio format: {fmt}"}

    data_uri_prefix = f"data:{mime_type};base64,"
    encoded_size = 4 * ((len(audio_bytes) + 2) // 3)
    data_uri_size = len(data_uri_prefix) + encoded_size
    if data_uri_size > MAX_INPUT_BYTES:
        return {
            "text": "",
            "error": (
                "base64 audio data URI exceeds Qwen ASR 10 MB input limit "
                f"({data_uri_size} bytes encoded)"
            ),
        }

    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        return {"text": "", "error": "DASHSCOPE_API_KEY not set"}

    encoded = base64.b64encode(audio_bytes).decode("ascii")
    data_uri = data_uri_prefix + encoded
    messages = [{"role": "user", "content": [{"audio": data_uri}]}]

    try:
        # Explicitly pin the native SDK to the same China region used by
        # llm.py and tts.py. MultiModalConversation.call is synchronous.
        dashscope.base_http_api_url = CHINA_BASE_HTTP_API_URL
        response = dashscope.MultiModalConversation.call(
            model=MODEL,
            messages=messages,
            api_key=api_key,
            result_format="message",
            asr_options={"enable_itn": False},
        )
    except Exception as exc:
        return {
            "text": "",
            "error": f"Qwen ASR request failed: {type(exc).__name__}: {exc}",
        }

    try:
        error = _response_error(response)
        if error:
            return {"text": "", "error": error}
        text = _extract_text(response)
    except Exception as exc:
        return {
            "text": "",
            "error": f"Qwen ASR response parsing failed: {type(exc).__name__}: {exc}",
        }
    if not text:
        return {"text": "", "error": "Qwen ASR returned no transcription text"}
    return {"text": text}
