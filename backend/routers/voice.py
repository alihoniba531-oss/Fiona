# -*- coding: utf-8 -*-
import asyncio
import base64
import io
import os
import shutil
import subprocess
import tempfile
import wave

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

from auth_dep import ws_authenticate
from nls_token import generate_nls_token
from qwen_asr import asr_recognize

router = APIRouter()
ASR_SAMPLE_RATE = 16000


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
        with open(out.name, "rb") as output_file:
            converted = output_file.read()

        if proc.returncode != 0 or not converted:
            try:
                shutil.copy(inp.name, "/tmp/fiona-asr-bad.webm")
            except OSError:
                pass
            stderr = proc.stderr.decode("utf-8", errors="replace")[-800:]
            print(f"[ASR][ffmpeg-stderr] {stderr}")
            print("[ASR] bad sample saved to /tmp/fiona-asr-bad.webm")
            raise RuntimeError("ffmpeg audio conversion failed")

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


@router.get("/asr/token")
async def asr_token():
    """已弃用：旧阿里云 NLS 实时语音识别 token，暂为兼容保留。"""
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
    """一句话识别：接收 base64 音频并以 WAV 调用 Qwen3-ASR-Flash。"""
    try:
        audio_bytes = base64.b64decode(req.audio)
    except Exception:
        return {"text": "", "error": "invalid base64 audio"}
    print(f"[ASR] received {len(audio_bytes)} bytes, format={req.format}")
    if not audio_bytes:
        return {"text": "", "error": "empty audio"}

    # WebM/Opus 需要转成 WAV 16kHz mono/16-bit；裸 PCM 则先补 WAV 头。
    if req.format.lower() == "pcm":
        if req.sample_rate <= 0:
            return {"text": "", "error": "invalid PCM sample rate"}
        try:
            audio_bytes = await asyncio.to_thread(_pcm_to_wav, audio_bytes, req.sample_rate)
            if req.sample_rate != ASR_SAMPLE_RATE:
                audio_bytes = await asyncio.to_thread(_ffmpeg_to_wav, audio_bytes, ".wav")
        except Exception as exc:
            return {"text": "", "error": f"PCM to WAV conversion failed: {exc}"}
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
            return {"text": "", "error": str(exc)}

    result = await asyncio.to_thread(asr_recognize, audio_bytes, "wav", ASR_SAMPLE_RATE)
    print(f"[ASR] result: {result}")
    return result
