# -*- coding: utf-8 -*-
"""
CosyVoice 持久化 WebSocket TTS：
一个聊天轮一条 WS，文本边来边喂 SDK，音频边生成边回传。
首音延迟从 ~1.8s 降到 ~500ms。
"""
import os
import json
import asyncio
import re
from queue import Queue
from fastapi import WebSocket, WebSocketDisconnect
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat, ResultCallback
from tts import dashscope_timeout_millis


dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "")

TTS_WS_MAX_TEXT_CHARS = 2000
TTS_WS_MAX_MESSAGE_CHARS = 4096
TTS_WS_IDLE_TIMEOUT_SECONDS = 30
TTS_WS_MAX_SESSION_SECONDS = 120
_VOICE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class _Callback(ResultCallback):
    """把 SDK 的同步回调架到线程安全队列"""
    def __init__(self):
        self.queue: "Queue[bytes | None]" = Queue()

    def on_open(self): pass
    def on_close(self): pass
    def on_event(self, message): pass

    def on_data(self, data: bytes):
        if data:
            self.queue.put(data)

    def on_complete(self):
        self.queue.put(None)

    def on_error(self, message: str):
        print("[TTS WS] synth error")
        self.queue.put(None)


async def handle_tts_ws(ws: WebSocket, authenticated_user: str | None = None):
    """协议（客户端 → 服务器）:
       {"type":"text","chunk":"...","voice":"longxiaobai_v2"}   增量文本
       {"type":"complete"}                                       结束标记
       服务器 → 客户端：二进制 MP3 字节流（多帧）"""
    await ws.accept()
    cb = _Callback()
    synth: SpeechSynthesizer | None = None
    synth_completed = False
    websocket_closed = False
    forwarder: asyncio.Task | None = None
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    total_text_chars = 0
    sdk_timeout_seconds = dashscope_timeout_millis() / 1000

    async def reject(code: int):
        nonlocal websocket_closed
        await ws.close(code=code)
        websocket_closed = True

    async def forward_audio():
        """从 SDK 回调队列拿音频字节，推给前端 WS"""
        while True:
            chunk = await loop.run_in_executor(None, cb.queue.get)
            if chunk is None:
                break
            try:
                await ws.send_bytes(chunk)
            except Exception:
                break

    try:
        while True:
            session_remaining = TTS_WS_MAX_SESSION_SECONDS - (loop.time() - started_at)
            if session_remaining <= 0:
                await reject(1008)
                break
            try:
                msg = await asyncio.wait_for(
                    ws.receive_text(),
                    timeout=min(TTS_WS_IDLE_TIMEOUT_SECONDS, session_remaining),
                )
            except asyncio.TimeoutError:
                await reject(1008)
                break
            if authenticated_user is not None:
                from auth_dep import ws_authenticate
                if await ws_authenticate(ws) != authenticated_user:
                    await reject(4401)
                    break
            if len(msg) > TTS_WS_MAX_MESSAGE_CHARS:
                await reject(1009)
                break
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            kind = data.get("type")

            if kind == "text":
                raw_chunk = data.get("chunk")
                if not isinstance(raw_chunk, str):
                    await reject(1008)
                    break
                chunk = raw_chunk.strip()
                if not chunk:
                    continue
                total_text_chars += len(chunk)
                if total_text_chars > TTS_WS_MAX_TEXT_CHARS:
                    await reject(1009)
                    break
                if synth is None:
                    voice = data.get("voice", "longxiaoxia_v2")  # 与 tts.py / voice.py 默认音色一致
                    if not isinstance(voice, str) or not _VOICE_PATTERN.fullmatch(voice):
                        await reject(1008)
                        break
                    synth = SpeechSynthesizer(
                        model="cosyvoice-v2",
                        voice=voice,
                        format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
                        callback=cb,
                    )
                    forwarder = asyncio.create_task(forward_audio())
                # streaming_call 阻塞写 WS，放线程
                await asyncio.wait_for(
                    loop.run_in_executor(None, synth.streaming_call, chunk),
                    timeout=sdk_timeout_seconds,
                )

            elif kind == "complete":
                if synth is not None:
                    # 标记已发起完成，超时时不要在 finally 并发调用第二次。
                    synth_completed = True
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            synth.streaming_complete,
                            dashscope_timeout_millis(),
                        ),
                        timeout=sdk_timeout_seconds + 1,
                    )
                if forwarder is not None:
                    try:
                        await asyncio.wait_for(forwarder, timeout=15)
                    except asyncio.TimeoutError:
                        pass
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[TTS WS] handler error type={type(e).__name__}")
    finally:
        # cancel 不能唤醒已在线程池中执行的 queue.get；先放 sentinel，确保线程能退出。
        if synth is not None:
            cb.queue.put(None)
            if not synth_completed:
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            synth.streaming_complete,
                            dashscope_timeout_millis(),
                        ),
                        timeout=sdk_timeout_seconds + 1,
                    )
                    synth_completed = True
                except Exception as e:
                    print(f"[TTS WS] synth close error type={type(e).__name__}")
        if forwarder is not None and not forwarder.done():
            try:
                await asyncio.wait_for(asyncio.shield(forwarder), timeout=1.0)
            except asyncio.TimeoutError:
                forwarder.cancel()
                try:
                    await forwarder
                except asyncio.CancelledError:
                    pass
        if not websocket_closed:
            try:
                await ws.close()
            except Exception:
                pass
