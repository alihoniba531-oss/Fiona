# -*- coding: utf-8 -*-
import asyncio
import base64
import os

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

from auth_dep import ws_authenticate
from nls_token import generate_nls_token
from nls_asr import asr_recognize

router = APIRouter()


@router.get("/asr/token")
async def asr_token():
    """阿里云 NLS 实时语音识别 token"""
    return generate_nls_token()


@router.get("/tts/synthesize")
async def tts_synthesize(text: str, voice: str = "longxiaoxia_v2", speech_rate: float = 1.15):
    """阿里云 CosyVoice v2 语音合成：text → mp3 字节流。
    SDK 在长进程里偶发 418，在独立线程跑 + 失败重试一次。"""
    import asyncio
    from tts import synthesize
    audio, mime = await asyncio.to_thread(synthesize, text, voice, speech_rate)
    if not audio:
        audio, mime = await asyncio.to_thread(synthesize, text, voice, speech_rate)
    if not audio:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": mime}, status_code=502)
    from fastapi.responses import Response
    return Response(content=audio, media_type=mime)


@router.get("/tts/stream")
async def tts_stream(text: str, voice: str = "longxiaoxia_v2", speech_rate: float = 1.15):
    """CosyVoice 流式合成：边合成边返回 mp3 chunks（chunked transfer）。
    浏览器 <audio> 元素天然支持流式 mp3，首音 ~300ms。"""
    from tts import synthesize_stream
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        synthesize_stream(text, voice, speech_rate),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.websocket("/tts/ws")
async def tts_ws_endpoint(websocket: WebSocket):
    """持久化 TTS WebSocket：边喂文本边吐音频字节。首音 ~500ms。"""
    from tts_ws import handle_tts_ws
    user = await ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4401)
        return
    await handle_tts_ws(websocket)


class AsrRequest(BaseModel):
    audio: str  # base64 编码的 PCM 音频
    format: str = "pcm"
    sample_rate: int = 16000


@router.post("/asr/recognize")
async def asr_recognize_endpoint(req: AsrRequest):
    """一句话识别：接收 base64 音频(WebM/Opus) → ffmpeg 转 PCM → NLS"""
    try:
        audio_bytes = base64.b64decode(req.audio)
    except Exception:
        return {"text": "", "error": "invalid base64 audio"}
    print(f"[ASR] received {len(audio_bytes)} bytes, format={req.format}")

    # WebM/Opus 需要转成 PCM 16kHz mono
    if req.format != "pcm":
        import subprocess, tempfile, shutil
        inp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        inp.write(audio_bytes); inp.close()
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out.close()
        try:
            ffmpeg = shutil.which("ffmpeg") or r"D:\Program Files\软件\ffmpeg\bin\ffmpeg.exe"
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    [ffmpeg, "-y", "-i", inp.name, "-ar", str(req.sample_rate), "-ac", "1", "-f", "s16le", out.name],
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                print("[ASR] ffmpeg timeout (>10s)")
                return {"text": "", "error": "ffmpeg timeout"}
            except FileNotFoundError:
                print(f"[ASR] ffmpeg not found at: {ffmpeg}")
                return {"text": "", "error": "ffmpeg not installed"}
            with open(out.name, "rb") as f:
                audio_bytes = f.read()
            if len(audio_bytes) == 0:
                # 保留失败样本供诊断
                shutil.copy(inp.name, "/tmp/fiona-asr-bad.webm")
                print(f"[ASR][ffmpeg-stderr] {proc.stderr.decode('utf-8', errors='replace')[-800:]}")
                print(f"[ASR] bad sample saved to /tmp/fiona-asr-bad.webm")
            print(f"[ASR] converted to PCM: {len(audio_bytes)} bytes (ffmpeg rc={proc.returncode})")
        finally:
            # 不论 ffmpeg 成功/超时/异常，临时文件必删，避免 /tmp 堆积
            for _p in (inp.name, out.name):
                try: os.unlink(_p)
                except OSError: pass

    result = await asyncio.to_thread(asr_recognize, audio_bytes, "pcm", req.sample_rate)
    print(f"[ASR] result: {result}")
    return result
