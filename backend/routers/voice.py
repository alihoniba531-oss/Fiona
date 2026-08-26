# -*- coding: utf-8 -*-
import asyncio
import base64
import binascii
import io
import os
import shutil
import subprocess
import tempfile
import wave

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field

from auth_dep import ws_authenticate
from qwen_asr import asr_recognize, request_timeout_seconds
from rate_limit import limiter

router = APIRouter()
ASR_SAMPLE_RATE = 16000
ASR_MAX_SOURCE_BYTES = 10 * 1024 * 1024
ASR_MAX_BASE64_CHARS = 4 * ((ASR_MAX_SOURCE_BYTES + 2) // 3) + 8
ASR_MAX_DURATION_SECONDS = 120
ASR_MAX_WAV_BYTES = 5 * 1024 * 1024


def _pcm_to_wav(audio_bytes: bytes, sample_rate: int = ASR_SAMPLE_RATE) -> bytes:
    """Wrap 16-bit mono PCM samples in a self-describing WAV container."""
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)
    return output.getvalue()


def _ffmpeg_to_wav(audio_bytes: bytes, input_suffix: str = ".webm") -> bytes:
    """Synchronously transcode audio to 16 kHz mono/16-bit WAV."""
    inp = None
    out = None
    try:
        inp = tempfile.NamedTemporaryFile(suffix=input_suffix, delete=False)
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        inp.write(audio_bytes)
        inp.close()
        out.close()

        ffmpeg = shutil.which("ffmpeg") or r"D:\Program Files\软件\ffmpeg\bin\ffmpeg.exe"
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                inp.name,
                "-t",
                str(ASR_MAX_DURATION_SECONDS),
                "-vn",
                "-ar",
                str(ASR_SAMPLE_RATE),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                out.name,
            ],
            capture_output=True,
            timeout=10,
        )
        if proc.returncode != 0:
            # 不保留失败的用户音频，也不把 ffmpeg 对不可信输入的详细输出写入日志。
            print(f"[ASR] ffmpeg conversion failed rc={proc.returncode}")
            raise RuntimeError("ffmpeg audio conversion failed")

        converted_size = os.path.getsize(out.name)
        if converted_size <= 0:
            raise RuntimeError("ffmpeg produced empty audio")
        if converted_size > ASR_MAX_WAV_BYTES:
            raise ValueError("converted audio exceeds 2 minute limit")
        with open(out.name, "rb") as output_file:
            converted = output_file.read()

        print(f"[ASR] converted to WAV: {len(converted)} bytes (ffmpeg rc={proc.returncode})")
        return converted
    finally:
        for temporary_file in (inp, out):
            if temporary_file is None:
                continue
            temporary_file.close()
            try:
                os.unlink(temporary_file.name)
            except OSError:
                pass


@router.get("/tts/synthesize")
@limiter.limit("20/minute")
async def tts_synthesize(
    request: Request,
    text: str = Query(min_length=1, max_length=2000),
    voice: str = Query(default="longxiaoxia_v2", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
    speech_rate: float = Query(default=1.15, ge=0.5, le=2.0),
):
    """阿里云 CosyVoice v2 语音合成：text → mp3 字节流。
    SDK 在长进程里偶发 418，在独立线程跑 + 失败重试一次。"""
    import asyncio
    from tts import dashscope_timeout_millis, synthesize
    timeout_seconds = dashscope_timeout_millis() / 1000 + 1
    timed_out = False
    try:
        audio, mime = await asyncio.wait_for(
            asyncio.to_thread(synthesize, text, voice, speech_rate),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        timed_out = True
        audio, mime = b"", "error:timeout"
    if not audio and not timed_out:
        try:
            audio, mime = await asyncio.wait_for(
                asyncio.to_thread(synthesize, text, voice, speech_rate),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            audio, mime = b"", "error:timeout"
    if not audio:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "TTS synthesis failed"}, status_code=502)
    from fastapi.responses import Response
    return Response(content=audio, media_type=mime)


@router.get("/tts/stream")
@limiter.limit("20/minute")
async def tts_stream(
    request: Request,
    text: str = Query(min_length=1, max_length=2000),
    voice: str = Query(default="longxiaoxia_v2", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
    speech_rate: float = Query(default=1.15, ge=0.5, le=2.0),
):
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
    await handle_tts_ws(websocket, authenticated_user=user)


class AsrRequest(BaseModel):
    audio: str = Field(max_length=ASR_MAX_BASE64_CHARS)  # base64 编码的 PCM/压缩音频
    format: str = Field(default="pcm", min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_+.-]+$")
    sample_rate: int = Field(default=16000, ge=8000, le=192000)


@router.post("/asr/recognize")
@limiter.limit("10/minute")
async def asr_recognize_endpoint(request: Request, req: AsrRequest):
    """一句话识别：接收 base64 音频并以 WAV 调用 Qwen3-ASR-Flash。"""
    try:
        audio_bytes = base64.b64decode(req.audio, validate=True)
    except (binascii.Error, ValueError):
        return {"text": "", "error": "invalid base64 audio"}
    print(f"[ASR] received {len(audio_bytes)} bytes, format={req.format}")
    if not audio_bytes:
        return {"text": "", "error": "empty audio"}
    if len(audio_bytes) > ASR_MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="audio exceeds 10MB limit")

    # WebM/Opus 需要转成 WAV 16kHz mono/16-bit；裸 PCM 则先补 WAV 头。
    if req.format.lower() == "pcm":
        max_pcm_bytes = req.sample_rate * 2 * ASR_MAX_DURATION_SECONDS
        if len(audio_bytes) > max_pcm_bytes:
            raise HTTPException(status_code=413, detail="PCM audio exceeds 2 minute limit")
        try:
            audio_bytes = await asyncio.to_thread(_pcm_to_wav, audio_bytes, req.sample_rate)
            if req.sample_rate != ASR_SAMPLE_RATE:
                audio_bytes = await asyncio.to_thread(_ffmpeg_to_wav, audio_bytes, ".wav")
        except Exception as exc:
            print(f"[ASR] PCM conversion failed type={type(exc).__name__}")
            return {"text": "", "error": "audio conversion failed"}
    else:
        try:
            audio_bytes = await asyncio.to_thread(_ffmpeg_to_wav, audio_bytes)
        except subprocess.TimeoutExpired:
            print("[ASR] ffmpeg timeout (>10s)")
            return {"text": "", "error": "ffmpeg timeout"}
        except FileNotFoundError:
            print("[ASR] ffmpeg not found")
            return {"text": "", "error": "ffmpeg not installed"}
        except Exception as exc:
            print(f"[ASR] conversion failed: {type(exc).__name__}")
            return {"text": "", "error": "audio conversion failed"}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(asr_recognize, audio_bytes, "wav", ASR_SAMPLE_RATE),
            timeout=request_timeout_seconds() + 1,
        )
    except asyncio.TimeoutError:
        return {"text": "", "error": "ASR request timed out"}
    return result
