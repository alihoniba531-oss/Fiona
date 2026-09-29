# -*- coding: utf-8 -*-
import asyncio
import base64
import binascii
import io
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field, replace

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field

from auth_dep import get_current_user, ws_authenticate
from qwen_asr import asr_recognize, request_timeout_seconds
from rate_limit import limiter

router = APIRouter()
ASR_SAMPLE_RATE = 16000
ASR_MAX_SOURCE_BYTES = 10 * 1024 * 1024
ASR_MAX_BASE64_CHARS = 4 * ((ASR_MAX_SOURCE_BYTES + 2) // 3) + 8
ASR_MAX_DURATION_SECONDS = 120
ASR_MAX_WAV_BYTES = 5 * 1024 * 1024
TTS_TICKET_TTL_SECONDS = 60
TTS_MAX_TICKET_USES = 4
TTS_MAX_PENDING_TICKETS = 2048
TTS_MAX_CACHED_AUDIO_BYTES = 64 * 1024 * 1024
TTS_MAX_AUDIO_BYTES_PER_TICKET = 8 * 1024 * 1024


class TtsTicketRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="longxiaoxia_v2", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    speech_rate: float = Field(default=1.15, ge=0.5, le=2.0)


@dataclass
class _TtsAudioBuild:
    prewarm: bool = False
    done: threading.Event = field(default_factory=threading.Event)
    audio: bytes | None = None
    prewarm_task: asyncio.Task | None = None
    waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = field(default_factory=list)
    waiters_lock: threading.Lock = field(default_factory=threading.Lock)

    async def wait(self) -> bytes | None:
        """Wait without occupying a worker, including from a different request loop."""
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        with self.waiters_lock:
            if self.done.is_set():
                return self.audio
            self.waiters.append((loop, waiter))
        try:
            await waiter
        finally:
            with self.waiters_lock:
                if (loop, waiter) in self.waiters:
                    self.waiters.remove((loop, waiter))
        return self.audio

    def finish(self, audio: bytes | None) -> None:
        with self.waiters_lock:
            if self.done.is_set():
                return
            self.audio = audio
            self.done.set()
            waiters = self.waiters
            self.waiters = []
        for loop, waiter in waiters:
            try:
                loop.call_soon_threadsafe(_wake_tts_waiter, waiter)
            except RuntimeError:
                # A disconnected request may have closed its event loop.
                pass


def _wake_tts_waiter(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)


@dataclass(frozen=True)
class _TtsTicket:
    user: str
    text: str
    voice: str
    speech_rate: float
    expires_at: float
    uses: int = 0
    cached_audio: bytes | None = None
    audio_build: _TtsAudioBuild | None = None


_tts_tickets: dict[str, _TtsTicket] = {}
_tts_tickets_lock = threading.Lock()


def _cancel_tts_prewarm(entry: _TtsTicket) -> None:
    """Wake any playback waiter and cancel synthesis for an invalidated ticket."""
    build = entry.audio_build
    if build is None or build.prewarm_task is None:
        return
    build.finish(None)
    task = build.prewarm_task
    if not task.done():
        try:
            task.get_loop().call_soon_threadsafe(task.cancel)
        except RuntimeError:
            # The request loop has already closed; the ticket no longer owns it.
            pass


def _use_tts_ticket(ticket: str, user: str) -> _TtsTicket:
    with _tts_tickets_lock:
        entry = _tts_tickets.get(ticket)
        if entry is None:
            raise HTTPException(status_code=404, detail="朗读票据不存在或已失效")
        if time.monotonic() >= entry.expires_at:
            _tts_tickets.pop(ticket, None)
            _cancel_tts_prewarm(entry)
            raise HTTPException(status_code=404, detail="朗读票据已过期")
        if entry.user != user:
            raise HTTPException(status_code=404, detail="朗读票据不存在或已失效")
        if entry.uses >= TTS_MAX_TICKET_USES:
            raise HTTPException(status_code=404, detail="朗读票据已用完")
        _tts_tickets[ticket] = replace(entry, uses=entry.uses + 1)
        return entry


def _claim_tts_audio(ticket: str, entry: _TtsTicket) -> tuple[bytes | None, _TtsAudioBuild | None, bool]:
    """Share one synthesis across playback probes, even when they overlap."""
    with _tts_tickets_lock:
        current = _tts_tickets.get(ticket) or entry
        if current.cached_audio is not None:
            return current.cached_audio, None, False
        build = current.audio_build
        if build is not None and not build.done.is_set():
            return None, build, False
        build = _TtsAudioBuild()
        if ticket in _tts_tickets:
            _tts_tickets[ticket] = replace(current, audio_build=build)
        return None, build, True


def _complete_tts_audio(ticket: str, build: _TtsAudioBuild, audio: bytes | None) -> None:
    with _tts_tickets_lock:
        current = _tts_tickets.get(ticket)
        if current is not None and current.audio_build is build and current.expires_at > time.monotonic():
            # An oversized response is never retained by the ticket table.
            if audio and len(audio) <= min(TTS_MAX_AUDIO_BYTES_PER_TICKET, TTS_MAX_CACHED_AUDIO_BYTES):
                used = sum(len(item.cached_audio or b"") for item in _tts_tickets.values())
                for key, item in list(_tts_tickets.items()):
                    if used + len(audio) <= TTS_MAX_CACHED_AUDIO_BYTES:
                        break
                    if key == ticket or item.cached_audio is None:
                        continue
                    used -= len(item.cached_audio)
                    # Keep the ticket valid for WebKit's follow-up request.
                    # Clearing the completed build also releases its copy of
                    # the bytes, so the cache budget remains a real bound.
                    _tts_tickets[key] = replace(item, cached_audio=None, audio_build=None)
                _tts_tickets[ticket] = replace(current, cached_audio=audio, audio_build=None)
            else:
                _tts_tickets[ticket] = replace(current, audio_build=None)
        else:
            # An expired or evicted ticket cannot retain audio in the table.
            # A request admitted while valid still receives its on-demand result.
            if current is not None and current.audio_build is build and current.expires_at <= time.monotonic():
                _tts_tickets.pop(ticket, None)
            if build.prewarm:
                audio = None
        build.finish(audio)


async def _build_tts_audio(ticket: str, entry: _TtsTicket, build: _TtsAudioBuild) -> bytes | None:
    from tts import dashscope_timeout_millis, synthesize

    audio: bytes | None = None
    try:
        timeout = dashscope_timeout_millis() / 1000 + 1
        if build.prewarm:
            timeout = min(timeout, entry.expires_at - time.monotonic())
        if timeout <= 0:
            return None
        payload, _ = await asyncio.wait_for(
            asyncio.to_thread(synthesize, entry.text, entry.voice, entry.speech_rate),
            timeout=timeout,
        )
        if payload and len(payload) <= TTS_MAX_AUDIO_BYTES_PER_TICKET:
            audio = payload
    except Exception:
        pass
    finally:
        _complete_tts_audio(ticket, build, audio)
    return build.audio


async def _get_tts_audio(ticket: str, entry: _TtsTicket) -> bytes | None:
    cached, build, creator = _claim_tts_audio(ticket, entry)
    if cached is not None:
        return cached
    assert build is not None
    if not creator:
        return await build.wait()
    return await _build_tts_audio(ticket, entry, build)


def _is_webkit_user_agent(user_agent: str) -> bool:
    return "AppleWebKit" in user_agent and not any(
        engine in user_agent for engine in ("Chrome/", "Chromium/", "Edg/")
    )


_RANGE_RE = re.compile(r"^bytes=(\d{0,20})-(\d{0,20})$", re.IGNORECASE)


def _is_zero_open_range(header: str) -> bool:
    """An initial bytes=0- playback can stream without knowing the final length."""
    match = _RANGE_RE.fullmatch(header.strip())
    return bool(match and match.group(1) and int(match.group(1)) == 0 and not match.group(2))


def _parse_byte_range(header: str, total: int | None = None) -> tuple[int, int] | None:
    match = _RANGE_RE.fullmatch(header.strip())
    if match is None or not any(match.groups()):
        return None
    if total is None:
        return 0, 0  # Valid syntax; actual bounds need the synthesized length.
    if total <= 0:
        return None
    start_text, end_text = match.groups()
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            return None
        return max(0, total - suffix), total - 1
    start = int(start_text)
    end = min(int(end_text), total - 1) if end_text else total - 1
    if start >= total or end < start:
        return None
    return start, end


def _range_not_satisfiable(total: int | None = None):
    from fastapi.responses import Response

    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    if total is not None:
        headers["Content-Range"] = f"bytes */{total}"
    return Response(
        status_code=416,
        headers=headers,
    )


def _validate_ticket_query(request: Request) -> None:
    # Reject legacy text URLs, including one appended to an otherwise valid ticket.
    if any(key != "ticket" for key in request.query_params):
        raise HTTPException(status_code=400, detail="朗读请求只接受票据")


@router.post("/tts/ticket")
@limiter.limit("20/minute")
async def tts_ticket(request: Request, body: TtsTicketRequest, user: str = Depends(get_current_user)):
    """Store private text in memory and return a short-lived playback ticket."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="朗读文本不能为空")
    now = time.monotonic()
    ticket = secrets.token_urlsafe(32)
    prewarm = _is_webkit_user_agent(request.headers.get("user-agent", ""))
    build = _TtsAudioBuild(prewarm=True) if prewarm else None
    issued_entry = _TtsTicket(
        user, text, body.voice, body.speech_rate, now + TTS_TICKET_TTL_SECONDS,
        audio_build=build,
    )
    with _tts_tickets_lock:
        for key, existing in list(_tts_tickets.items()):
            if existing.expires_at <= now:
                _tts_tickets.pop(key, None)
                _cancel_tts_prewarm(existing)
        if len(_tts_tickets) >= TTS_MAX_PENDING_TICKETS:
            evicted = _tts_tickets.pop(next(iter(_tts_tickets)))
            _cancel_tts_prewarm(evicted)
        _tts_tickets[ticket] = issued_entry
        if build is not None:
            task = asyncio.create_task(_build_tts_audio(ticket, issued_entry, build))
            build.prewarm_task = task
            task.add_done_callback(lambda completed: setattr(build, "prewarm_task", None))
    return {"ticket": ticket, "expires_in": TTS_TICKET_TTL_SECONDS}


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
async def tts_synthesize(
    request: Request,
    ticket: str = Query(min_length=1, max_length=128),
    user: str = Depends(get_current_user),
):
    """阿里云 CosyVoice v2 语音合成：短期票据 → mp3 字节。"""
    _validate_ticket_query(request)
    entry = _use_tts_ticket(ticket, user)
    audio = await _get_tts_audio(ticket, entry)
    if not audio:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "TTS synthesis failed"}, status_code=502)
    from fastapi.responses import Response
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/tts/stream")
async def tts_stream(
    request: Request,
    ticket: str = Query(min_length=1, max_length=128),
    user: str = Depends(get_current_user),
):
    """Closed ranges need a finite MP3 length; first zero-open playback streams."""
    from tts import synthesize_stream
    from fastapi.responses import Response, StreamingResponse
    _validate_ticket_query(request)
    range_header = request.headers.get("range")
    if range_header is not None and _parse_byte_range(range_header) is None:
        return _range_not_satisfiable()
    entry = _use_tts_ticket(ticket, user)
    with _tts_tickets_lock:
        cached = _tts_tickets.get(ticket)
        has_cached_or_pending_audio = cached is not None and (cached.cached_audio is not None or cached.audio_build is not None)
    if range_header is not None and (has_cached_or_pending_audio or not _is_zero_open_range(range_header)):
        audio = await _get_tts_audio(ticket, entry)
        if not audio:
            return Response(status_code=502)
        byte_range = _parse_byte_range(range_header, len(audio))
        if byte_range is None:
            return _range_not_satisfiable(len(audio))
        start, end = byte_range
        return Response(
            content=audio[start:end + 1],
            status_code=206,
            media_type="audio/mpeg",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{len(audio)}",
                "Content-Length": str(end - start + 1),
                "Cache-Control": "private, no-store",
            },
        )

    async def stream_and_cache():
        cached, build, creator = _claim_tts_audio(ticket, entry)
        if cached is not None:
            yield cached
            return
        assert build is not None
        if not creator:
            audio = await build.wait()
            if audio:
                yield audio
            return
        chunks: list[bytes] = []
        size = 0
        complete = False
        try:
            async for chunk in synthesize_stream(entry.text, entry.voice, entry.speech_rate):
                if size <= TTS_MAX_AUDIO_BYTES_PER_TICKET:
                    size += len(chunk)
                    if size <= TTS_MAX_AUDIO_BYTES_PER_TICKET:
                        chunks.append(chunk)
                yield chunk
            complete = True
        finally:
            _complete_tts_audio(ticket, build, b"".join(chunks) if complete and size <= TTS_MAX_AUDIO_BYTES_PER_TICKET else None)

    return StreamingResponse(
        stream_and_cache(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, no-store"},
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
