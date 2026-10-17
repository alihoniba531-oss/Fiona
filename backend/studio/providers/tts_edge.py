"""edge-tts 7.3.1 英文配音适配器（免费调用）。

要点：

* edge_tts 只在真正合成时延迟导入：本机/CI 未安装 edge-tts 时，导入本模块本身不能报错。
* 输出 mp3、24kHz 单声道；``words`` 是 WordBoundary 列表，offset/duration 的单位是
  100 纳秒，除以 1e7 换成秒。
* 超时 120 秒 → uncertain；明确的 4xx/429（只认结构化状态码属性）→ rejected；
  其余 SDK 报错 → uncertain。绝不从异常文本里猜 4xx：aiohttp / edge-tts 的断连文本
  固定含 ``host:443``，扫文本会把断连误判成 rejected。
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from .base import UNCERTAIN_MESSAGE, safe_message
from .media_errors import MediaCallError
from .tts_cosy import TtsResult


EDGE_ENGINE = "edge-tts"
EDGE_AUDIO_FORMAT = "mp3"
EDGE_SAMPLE_RATE = 24000
SYNTHESIS_TIMEOUT_S = 120.0

# WordBoundary 的 offset / duration 以 100 纳秒为单位。
_TICKS_PER_SECOND = 10_000_000


def _status_code(exc: BaseException) -> int | None:
    """取明确的 HTTP 状态码：只认 status / status_code 这类结构化数值属性。

    结构化字段缺失即返回 None（由 ``_failure_from_exception`` 判 uncertain），
    ``str(exc)`` 里的 ``:443`` 之类的数字一律不作数。
    """
    for name in ("status_code", "status", "http_status"):
        raw = getattr(exc, name, None)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return None


def _failure_from_exception(exc: BaseException) -> MediaCallError:
    code = type(exc).__name__
    status = _status_code(exc)
    if isinstance(status, int) and 400 <= status < 500:
        return MediaCallError("rejected", code, safe_message(str(exc)))
    return MediaCallError("uncertain", code, UNCERTAIN_MESSAGE)


def _default_communicate_factory(**params: Any) -> Any:
    """真实 SDK 工厂：真正合成时才 import edge_tts，返回 Communicate 实例。"""
    import edge_tts

    return edge_tts.Communicate(**params)


def _word(event: dict) -> dict[str, Any]:
    return {
        "offset_s": float(event.get("offset") or 0) / _TICKS_PER_SECOND,
        "duration_s": float(event.get("duration") or 0) / _TICKS_PER_SECOND,
        "text": str(event.get("text") or ""),
    }


async def _collect(text: str, *, voice: str, rate: str, pitch: str,
                   factory: Callable[..., Any]) -> tuple[bytes, list[dict[str, Any]]]:
    communication = factory(text=text, voice=voice, rate=rate, pitch=pitch)
    audio = bytearray()
    words: list[dict[str, Any]] = []
    async for event in communication.stream():
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "audio":
            data = event.get("data")
            if data:
                audio.extend(data)
        elif kind == "WordBoundary":
            words.append(_word(event))
    if not audio:
        raise MediaCallError("uncertain", "empty_audio", UNCERTAIN_MESSAGE)
    return bytes(audio), words


async def synthesize_edge(text: str, *, voice: str, rate: str, pitch: str,
                          communicate_factory: Callable[..., Any] | None = None) -> TtsResult:
    """合成一段英文台词（免费）。

    ``communicate_factory`` 契约：``factory(text=..., voice=..., rate=..., pitch=...)``，
    返回带 ``stream()`` 异步迭代器的对象；默认用 ``edge_tts.Communicate``。
    """
    factory = communicate_factory
    if factory is None:
        try:
            import edge_tts  # noqa: F401  延迟导入：未安装也不能影响本模块的导入
        except ImportError:
            raise MediaCallError("uncertain", "edge_tts_unavailable",
                                 "未安装 edge-tts（需要 ≥7.3.1），没有发起配音") from None
        factory = _default_communicate_factory
    try:
        audio, words = await asyncio.wait_for(
            _collect(text, voice=voice, rate=rate, pitch=pitch, factory=factory),
            timeout=SYNTHESIS_TIMEOUT_S,
        )
    except (TimeoutError, asyncio.TimeoutError):
        raise MediaCallError("uncertain", "timeout", UNCERTAIN_MESSAGE) from None
    except MediaCallError:
        raise
    except Exception as exc:
        raise _failure_from_exception(exc) from None
    return TtsResult(audio=audio, audio_format=EDGE_AUDIO_FORMAT, sample_rate=EDGE_SAMPLE_RATE,
                     chars=len(text), engine=EDGE_ENGINE, voice=voice, words=words)
