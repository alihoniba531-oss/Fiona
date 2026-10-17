"""CosyVoice v2（DashScope）中文配音适配器。

块 B 的一次付费合成。要点：

* dashscope 只在真正合成时延迟导入，模块顶层不 import。
* ``dashscope.api_key`` 是进程级共享状态，SDK 在**构造** SpeechSynthesizer 时读取它，
  不支持按调用传 key；因此用模块级锁包住「保存旧值 → 设置 → 构造并调用 → 恢复旧值」，
  try/finally 保证恢复。锁内的调用会串行化，这是共享全局 key 的代价。
  已核实 dashscope 1.25.18 的 SpeechSynthesizer 只有这两个参数名。
* CosyVoice v2 当前 SDK 不返回逐字时间戳（WO0 探针实测 words 恒为空），所以 ``words`` 恒为 None。
* 错误分类只看结构化状态码（异常 / 响应对象上的数值属性），绝不扫异常文本：
  断连文本里的 ``:443`` 之类的数字不是 4xx（规格 §2：超时 / 断连 → uncertain）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import threading
import time
from typing import Any, Callable

from .base import UNCERTAIN_MESSAGE, safe_message
from .media_errors import MediaCallError


COSYVOICE_MODEL = "cosyvoice-v2"
COSYVOICE_ENGINE = "cosyvoice"
COSYVOICE_AUDIO_FORMAT = "WAV_48000HZ_MONO_16BIT"
COSYVOICE_CONTAINER = "wav"
COSYVOICE_SAMPLE_RATE = 48000
SYNTHESIS_TIMEOUT_S = 120.0

# 全局 api_key 的串行保护；只在 _synthesize_blocking 里使用。
_API_KEY_LOCK = threading.Lock()

# 内容审核类错误码。命中即判 failed（按 0 结算，见 media_errors 的 status 定义），
# 即使上游同时给出 4xx 状态码也以审核为准。
_MODERATION_MARKERS = (
    "sensitivecontent", "contentfilter", "contentpolicy", "contentmoderation",
    "datainspectionfailed", "data_inspection_failed", "textinspectionfailed", "copyright",
)
_MODERATION_MESSAGE = "内容审核拒绝，按 0 结算"
_REJECTED_MESSAGE = "上游拒绝，已释放预留"


@dataclass
class TtsResult:
    audio: bytes
    audio_format: str
    sample_rate: int
    chars: int
    engine: str
    voice: str
    words: list | None


class _SpeechCollector:
    """ResultCallback 的鸭子类型实现：SDK 只按方法名回调，不校验 isinstance。"""

    def __init__(self) -> None:
        self.chunks = bytearray()
        self.failure: Any = None
        self.finished = threading.Event()

    def on_open(self) -> None:
        pass

    def on_data(self, data: bytes) -> None:
        self.chunks.extend(data)

    def on_event(self, message: str) -> None:
        # sentence-begin / sentence-synthesis 事件里没有可用时间戳，忽略。
        pass

    def on_complete(self) -> None:
        self.finished.set()

    def on_close(self) -> None:
        self.finished.set()

    def on_error(self, message: Any) -> None:
        self.failure = message
        self.finished.set()


def _status_code(value: Any) -> int | None:
    """取明确的 HTTP 状态码：只认 status / status_code 这类结构化数值字段。

    结构化字段来自对象属性（异常对象）或映射键（上游响应里的 header / payload），
    两者都是明确的数值状态码；结构化字段缺失即返回 None，由 ``_classify`` 判 uncertain。

    不从 ``str(value)`` 里正则找 4xx：``Cannot connect to host x:443`` 或
    ``服务器繁忙，429ms 后重试`` 这类文本会把断连 / 未知失败误判成「上游拒绝」，
    从而错误地释放预留。
    """
    names = ("status_code", "status", "http_status", "httpStatus")
    if isinstance(value, dict):
        fields = (value.get(name) for name in names)
    else:
        fields = (getattr(value, name, None) for name in names)
    for raw in fields:
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return None


def _classify(code: str, message: str, status: int | None) -> MediaCallError:
    blob = f"{code} {message}".lower()
    if any(marker in blob for marker in _MODERATION_MARKERS):
        return MediaCallError("failed", code, safe_message(message) if message else _MODERATION_MESSAGE)
    if isinstance(status, int) and 400 <= status < 500:
        return MediaCallError("rejected", code, safe_message(message) if message else _REJECTED_MESSAGE)
    # 无状态码的未知异常、5xx、坏响应：保守判 uncertain，保留预留。
    return MediaCallError("uncertain", code, UNCERTAIN_MESSAGE)


def _failure_from_message(raw: Any) -> MediaCallError:
    """解析 SDK 的 task-failed 消息（可能是 JSON 字符串或对象）。"""
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
    code: Any = None
    message: Any = None
    status: int | None = None
    if isinstance(data, dict):
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        header = data.get("header") if isinstance(data.get("header"), dict) else {}
        for item in (header, payload, output, data):
            code = code or item.get("error_code") or item.get("errorCode") or item.get("code")
            message = message or item.get("error_message") or item.get("errorMessage") or item.get("message")
            status = status or _status_code(item)
    if message is None and isinstance(raw, str):
        message = raw
    return _classify(str(code or "upstream_error"), str(message or ""), status)


def _failure_from_exception(exc: BaseException) -> MediaCallError:
    return _classify(type(exc).__name__, str(exc), _status_code(exc))


def _close_quietly(synthesizer: Any) -> None:
    close = getattr(synthesizer, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


def _default_synthesizer_factory(**params: Any) -> Any:
    """真实 SDK 工厂：真正合成时才 import dashscope，返回可调用的 SpeechSynthesizer。"""
    import dashscope  # noqa: F401  仅为延迟导入 SDK 包
    from dashscope.audio.tts_v2 import SpeechSynthesizer

    return SpeechSynthesizer(**params)


def _synthesize_blocking(*, text: str, voice: str, rate: float, pitch: float, api_key: str,
                         factory: Callable[..., Any],
                         cancelled: threading.Event | None = None) -> bytes:
    import dashscope  # 延迟导入：只有真正合成时才加载 SDK
    from dashscope.audio.tts_v2 import AudioFormat

    collector = _SpeechCollector()
    params = {
        "model": COSYVOICE_MODEL,
        "voice": voice,
        "format": AudioFormat[COSYVOICE_AUDIO_FORMAT],
        "speech_rate": rate,
        "pitch_rate": pitch,
        "callback": collector,
    }
    synthesizer = None
    with _API_KEY_LOCK:
        # 调用方已经超时并放弃结果：拿到锁后立刻返回，不再发这一次付费请求。
        if cancelled is not None and cancelled.is_set():
            return b""
        previous = getattr(dashscope, "api_key", None)
        dashscope.api_key = api_key
        try:
            synthesizer = factory(**params)
            started = time.monotonic()
            synthesizer.call(text, timeout_millis=int(SYNTHESIS_TIMEOUT_S * 1000))
            remaining = max(0.0, SYNTHESIS_TIMEOUT_S - (time.monotonic() - started))
            if not collector.finished.wait(remaining):
                raise TimeoutError("等待 CosyVoice 完整音频超时")
            if collector.failure is not None:
                raise _failure_from_message(collector.failure)
            audio = bytes(collector.chunks)
            if not audio:
                raise MediaCallError("uncertain", "empty_audio", UNCERTAIN_MESSAGE)
            return audio
        finally:
            # 先恢复全局 key，再做可能失败的收尾。
            dashscope.api_key = previous
            _close_quietly(synthesizer)


async def synthesize_cosy(text: str, *, voice: str, rate: float, pitch: float,
                          synthesizer_factory: Callable[..., Any] | None = None) -> TtsResult:
    """合成一段中文台词（单次付费调用）。

    ``synthesizer_factory`` 契约：``factory(**params) -> 合成器实例``。params 是
    SpeechSynthesizer 的构造参数（model / voice / format / speech_rate / pitch_rate /
    callback）；实例需提供 ``call(text, timeout_millis=...)``。注入工厂时仍然会临时设置
    并恢复全局 ``dashscope.api_key``。
    """
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise MediaCallError("failed", "missing_configuration", "未设置 DASHSCOPE_API_KEY，没有提交合成请求")
    factory = synthesizer_factory or _default_synthesizer_factory
    cancelled = threading.Event()
    try:
        audio = await asyncio.wait_for(
            asyncio.to_thread(_synthesize_blocking, text=text, voice=voice, rate=rate,
                              pitch=pitch, api_key=api_key, factory=factory, cancelled=cancelled),
            timeout=SYNTHESIS_TIMEOUT_S,
        )
    except (TimeoutError, asyncio.TimeoutError):
        # 超时只取消等待，线程可能还在排队取锁；置位取消标志让它直接返回，
        # 避免「任务已按 uncertain 结束、后台却仍发出付费请求」。
        cancelled.set()
        raise MediaCallError("uncertain", "timeout", UNCERTAIN_MESSAGE) from None
    except MediaCallError:
        raise
    except Exception as exc:
        raise _failure_from_exception(exc) from None
    return TtsResult(audio=audio, audio_format=COSYVOICE_CONTAINER, sample_rate=COSYVOICE_SAMPLE_RATE,
                     chars=len(text), engine=COSYVOICE_ENGINE, voice=voice, words=None)
