# -*- coding: utf-8 -*-
"""
CosyVoice 持久化 WebSocket TTS：
一个聊天轮一条 WS，文本边来边喂 SDK，音频边生成边回传。
首音延迟从 ~1.8s 降到 ~500ms。
"""
import os
import json
import asyncio
from queue import Queue
from fastapi import WebSocket, WebSocketDisconnect
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat, ResultCallback


dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "")


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
        print(f"[TTS WS] synth error: {str(message)[:200]}")
        self.queue.put(None)


async def handle_tts_ws(ws: WebSocket):
    """协议（客户端 → 服务器）:
       {"type":"text","chunk":"...","voice":"longxiaobai_v2"}   增量文本
       {"type":"complete"}                                       结束标记
       服务器 → 客户端：二进制 MP3 字节流（多帧）"""
    await ws.accept()
    cb = _Callback()
    synth: SpeechSynthesizer | None = None
    synth_completed = False
    forwarder: asyncio.Task | None = None
    loop = asyncio.get_running_loop()

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
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                continue
            kind = data.get("type")

            if kind == "text":
                chunk = (data.get("chunk") or "").strip()
                if not chunk:
                    continue
                if synth is None:
                    voice = data.get("voice", "longxiaobai_v2")
                    synth = SpeechSynthesizer(
                        model="cosyvoice-v2",
                        voice=voice,
                        format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
                        callback=cb,
                    )
                    forwarder = asyncio.create_task(forward_audio())
                # streaming_call 阻塞写 WS，放线程
                await loop.run_in_executor(None, synth.streaming_call, chunk)

            elif kind == "complete":
                if synth is not None:
                    await loop.run_in_executor(None, synth.streaming_complete)
                    synth_completed = True
                if forwarder is not None:
                    try:
                        await asyncio.wait_for(forwarder, timeout=15)
                    except asyncio.TimeoutError:
                        pass
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[TTS WS] handler error: {type(e).__name__}: {e}")
    finally:
        # cancel 不能唤醒已在线程池中执行的 queue.get；先放 sentinel，确保线程能退出。
        if synth is not None:
            cb.queue.put(None)
            if not synth_completed:
                try:
                    await loop.run_in_executor(None, synth.streaming_complete)
                    synth_completed = True
                except Exception as e:
                    print(f"[TTS WS] synth close error: {type(e).__name__}: {e}")
        if forwarder is not None and not forwarder.done():
            try:
                await asyncio.wait_for(asyncio.shield(forwarder), timeout=1.0)
            except asyncio.TimeoutError:
                forwarder.cancel()
                try:
                    await forwarder
                except asyncio.CancelledError:
                    pass
        try:
            await ws.close()
        except Exception:
            pass
