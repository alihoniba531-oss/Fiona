# -*- coding: utf-8 -*-
"""
阿里云 CosyVoice 语音合成（DashScope）。
比 NLS 标准音（xiaoyun 等）拟人度高出代际，对标豆包。

音色推荐（v2）：
  longwan_v2       — 龙婉，知性平稳女声
  longxiaobai_v2   — 龙小白，邻家温柔少女（默认，贴合Chloe）
  longxiaoxia_v2   — 龙小夏，活泼少女
  longxiaocheng_v2 — 龙小诚，沉稳男声
"""
import os
import asyncio
import threading
from queue import Queue
from typing import AsyncIterator
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat, ResultCallback


# 在 import 时把 key 注入 SDK（dotenv 由调用方/main 加载）
dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "")


DEFAULT_VOICE = "longxiaoxia_v2"  # 活泼少女，比 longxiaobai 更有起伏
DEFAULT_SPEECH_RATE = 1.15        # 略快于自然语速（CosyVoice v2 支持 0.5~2.0）


def synthesize(text: str, voice: str = DEFAULT_VOICE, speech_rate: float = DEFAULT_SPEECH_RATE) -> tuple[bytes, str]:
    """
    CosyVoice v2 合成，返回 (audio_bytes, mime_type)。
    失败时 audio_bytes 为空，mime_type 含错误信息。
    """
    text = (text or "").strip()
    if not text:
        return b"", "error:empty text"
    if len(text) > 300:
        text = text[:300]
    if not dashscope.api_key:
        return b"", "error:DASHSCOPE_API_KEY not set"

    try:
        synth = SpeechSynthesizer(
            model="cosyvoice-v2",
            voice=voice,
            format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
            speech_rate=speech_rate,
        )
        audio = synth.call(text)
        if audio:
            return audio, "audio/mpeg"
        return b"", "error:empty_audio_returned"
    except Exception as e:
        return b"", f"error:exception:{type(e).__name__}:{e}"


class _StreamCallback(ResultCallback):
    """把 SDK 的同步回调桥接到线程安全队列"""
    def __init__(self):
        self.queue: "Queue[bytes | None]" = Queue()
        self.error: str | None = None

    def on_open(self): pass
    def on_close(self): pass
    def on_event(self, message): pass

    def on_data(self, data: bytes):
        if data:
            self.queue.put(data)

    def on_complete(self):
        self.queue.put(None)

    def on_error(self, message: str):
        self.error = str(message)[:200]
        self.queue.put(None)


async def synthesize_stream(text: str, voice: str = DEFAULT_VOICE, speech_rate: float = DEFAULT_SPEECH_RATE) -> AsyncIterator[bytes]:
    """流式合成 — 边合成边 yield MP3 字节块。首音可低至 ~300ms。"""
    text = (text or "").strip()
    if not text:
        return
    if len(text) > 300:
        text = text[:300]
    if not dashscope.api_key:
        return

    cb = _StreamCallback()

    def run_synth():
        try:
            synth = SpeechSynthesizer(
                model="cosyvoice-v2",
                voice=voice,
                format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
                speech_rate=speech_rate,
                callback=cb,
            )
            synth.streaming_call(text)
            synth.streaming_complete()
        except Exception as e:
            cb.error = f"{type(e).__name__}:{e}"
            cb.queue.put(None)

    # SDK 调用同步阻塞，放后台线程；主线程 await 队列
    threading.Thread(target=run_synth, daemon=True).start()

    loop = asyncio.get_running_loop()
    while True:
        chunk = await loop.run_in_executor(None, cb.queue.get)
        if chunk is None:
            break
        yield chunk
