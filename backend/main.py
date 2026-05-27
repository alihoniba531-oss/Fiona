# -*- coding: utf-8 -*-
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import json
import base64
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI

from database import (init_db, get_or_create_user, save_message, get_messages,
                      count_messages, get_all_messages, delete_message,
                      save_peer_message, get_peer_messages, get_accepted_matches,
                      get_pending_matches_for_user, mark_pending_match_seen,
                      save_otp, check_and_consume_otp, get_or_create_user_by_phone,
                      get_strawberry_balance, deduct_strawberry, add_strawberry)
from auth import make_otp, create_token
from auth_dep import get_current_user, get_optional_user, ws_authenticate
from sms import send_sms
from persona import build_system_prompt
from intent_router import recognize_intent, get_pending, set_pending, clear_pending, ask_missing, fill_param
from extractor import extract_and_update
from mode_switcher import detect_mode, apply_mode_prompt, get_user_mode
from conversation_matcher import detect_and_save as detect_matches_and_save
from matcher import find_matches
from tools.open_app import open_application
from tools.wechat_send import send_wechat_message, start_wechat_voice_call, start_wechat_video_call
from tools.web_search import web_search
from tools.system_tools import open_url, take_screenshot, get_datetime, write_clipboard
from tools.fetch_card import fetch_card as _fetch_card_impl
from tools.hot_topics import hot_topics
from tools.route import route as route_query
from tools.travel_plan import travel_plan as travel_plan_query
from nls_token import generate_nls_token
from nls_asr import asr_recognize
from tools.reminder import set_reminder
from trace import log_event, trace_span


def _summarize_card_for_history(card: dict) -> str:
    """卡片回复落库时的可读摘要 —— 防止刷新后只剩 [城市名] 占位符。"""
    subtype = card.get("subtype")
    if subtype == "weather":
        w = card.get("weather") or {}
        loc = w.get("location") or card.get("source", "")
        cur = w.get("currentTemp", "?")
        cond = w.get("condition", "")
        fl = w.get("feelsLike", "?")
        head = f"{loc}现在{cur}° {cond}，体感{fl}°。"
        fc = w.get("forecast") or []
        parts = [
            f"{f.get('day','')} {f.get('condition','')} {f.get('low','?')}~{f.get('high','?')}°"
            for f in fc[:3]
        ]
        if parts:
            head += " 接下来：" + "；".join(parts) + "。"
        return head
    # 通用网页卡 / 搜索结果：source + bullets
    src = card.get("source", "网页")
    points = card.get("points") or []
    if points:
        return f"[{src}]\n" + "\n".join(f"• {p}" for p in points)
    return f"[{src}]"


# ─── 括号旁白过滤器 ───
# DeepSeek 角色扮演时本能加 "（动作描述）"，prompt 禁令屡禁不止——只能在流式输出里硬过滤。
# 流式状态机：遇到 ( 或 （ 进入吞字状态，遇到 ) 或 ） 退出。同时丢弃过滤后开头的孤立空白。
class BracketFilter:
    def __init__(self):
        self.in_bracket = False
        self.has_emitted_non_whitespace = False

    def filter_chunk(self, text: str) -> str:
        result = []
        for ch in text:
            if self.in_bracket:
                if ch in '）)':
                    self.in_bracket = False
                continue
            if ch in '（(':
                self.in_bracket = True
                continue
            # 第一个非空白之前的空白(过滤后的空头)都丢弃
            if not self.has_emitted_non_whitespace and ch.isspace():
                continue
            if not ch.isspace():
                self.has_emitted_non_whitespace = True
            result.append(ch)
        return "".join(result)


_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_env_path, override=True)

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ── 模型路由槽配置 ──────────────────────────────────────────
DEEPSEEK_MODEL = "deepseek-chat"
QWEN_CLIENT    = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
QWEN_MODEL     = "qwen-plus"

from model_router import choose_model, token_budget


def _create_stream_with_fallback(use_qwen: bool, messages: list, **kwargs):
    """
    轻量槽走通义 qwen-plus，失败自动回退 DeepSeek。
    返回 (stream, actually_used_qwen)
    """
    if use_qwen:
        try:
            stream = QWEN_CLIENT.chat.completions.create(
                model=QWEN_MODEL,
                messages=messages,
                stream=True,
                **kwargs,
            )
            return stream, True
        except Exception:
            pass
    stream = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        stream=True,
        **kwargs,
    )
    return stream, False


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Chloe API", lifespan=lifespan)

# 图片上传目录
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局鉴权中间件 ────────────────────────────────────────────────
# 默认所有 HTTP 请求都要鉴权，白名单放过；鉴权来源按优先级：
#   1. Authorization: Bearer <jwt> 头        — apiFetch 走这条
#   2. cookie fiona_token=<jwt>              — <audio src> / <img> 不能带 header，走这条
#   3. X-Dev-User 头（仅 DEV_MODE=1）         — 本地切身份调试
# WebSocket 握手不走 HTTP middleware，各 ws 端点用 ws_authenticate 单独鉴权。
_AUTH_PUBLIC_PATHS = {"/", "/auth/send-otp", "/auth/verify-otp", "/auth/test-login"}
_AUTH_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json")

@app.middleware("http")
async def require_auth(request: Request, call_next):
    if request.method == "OPTIONS":  # CORS 预检
        return await call_next(request)
    path = request.url.path
    if path.startswith("/uploads/") and os.getenv("DEV_MODE", "0") == "1":
        return await call_next(request)
    if path in _AUTH_PUBLIC_PATHS or any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIXES):
        return await call_next(request)
    from auth import decode_token
    user = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        user = decode_token(auth_header[7:])
    if not user:
        cookie_token = request.cookies.get("fiona_token")
        if cookie_token:
            user = decode_token(cookie_token)
    # <audio src> / <img src> 不能带 header，前端把 token 塞 query 兜底
    # （和 ws_authenticate 对称）
    if not user:
        q_token = request.query_params.get("token")
        if q_token:
            user = decode_token(q_token)
    if not user and os.getenv("DEV_MODE", "0") == "1":
        from urllib.parse import unquote
        dev = request.headers.get("x-dev-user") or request.query_params.get("dev_user")
        if dev:
            user = unquote(dev).strip() or None
    if not user:
        return JSONResponse({"detail": "未鉴权或鉴权失败"}, status_code=401)
    # 把鉴权结果挂到 request.state，路由里 Depends(get_current_user) 直接读，避免重复解码。
    request.state.user = user
    return await call_next(request)

class ChatRequest(BaseModel):
    message: str
    image_base64: str | None = None


# 单张图上限 5MB，base64 解码前粗筛 base64 长度（base64 比原始大约 33%）
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
# magic bytes → 文件扩展名映射
_MIME_SNIFF = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff",      "jpg"),
    (b"GIF87a",            "gif"),
    (b"GIF89a",            "gif"),
    (b"RIFF",              "webp"),  # 还要校验偏移 8 处是 WEBP，下面会做
]

_VIDEO_SNIFF = [
    (b"\x1a\x45\xdf\xa3", "webm"),
]
_MAX_PLAZA_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_PLAZA_VIDEO_BYTES = 20 * 1024 * 1024

def _sniff_image_ext(data: bytes) -> str | None:
    """嗅探前 12 字节判图片类型。不是已知图片格式返回 None。"""
    for magic, ext in _MIME_SNIFF:
        if data.startswith(magic):
            if ext == "webp" and not (len(data) >= 12 and data[8:12] == b"WEBP"):
                continue
            return ext
    return None


def _sniff_video_ext(data: bytes) -> str | None:
    """嗅探常见短视频格式。返回保存扩展名，不信任用户上传的文件名。"""
    for magic, ext in _VIDEO_SNIFF:
        if data.startswith(magic):
            return ext
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand == b"qt  ":
            return "mov"
        return "mp4"
    return None


async def _save_plaza_upload(file: UploadFile) -> tuple[str, str]:
    """保存广场媒体，校验魔数和大小，返回 (media_path, media_type)。"""
    import uuid as _uuid

    first = await file.read(8192)
    ext = _sniff_image_ext(first[:12])
    media_type = "image"
    limit = _MAX_PLAZA_IMAGE_BYTES
    if not ext:
        ext = _sniff_video_ext(first[:16])
        media_type = "video"
        limit = _MAX_PLAZA_VIDEO_BYTES
    if not ext:
        raise HTTPException(status_code=400, detail="只支持常见图片或短视频格式")

    fname = f"plaza_{_uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOADS_DIR, fname)
    total = 0
    try:
        with open(fpath, "wb") as f:
            if first:
                total += len(first)
                if total > limit:
                    raise HTTPException(status_code=413, detail="文件太大")
                f.write(first)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="文件太大")
                f.write(chunk)
    except Exception:
        try:
            os.unlink(fpath)
        except OSError:
            pass
        raise
    if total == 0:
        try:
            os.unlink(fpath)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="文件为空")
    return f"/uploads/{fname}", media_type


def _save_uploaded_image(image_base64: str) -> str | None:
    """保存 base64 图片到 uploads 目录，返回相对 URL 路径。失败返回 None。
    校验：base64 长度上限、解码后 mime 嗅探、文件名 uuid（不可猜）。"""
    try:
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        # 粗筛：base64 串本身长度上限（解码后约小 25%）
        if len(image_base64) > _MAX_IMAGE_BYTES * 4 // 3 + 1024:
            print(f"[upload] reject: base64 too large ({len(image_base64)} chars)", flush=True)
            return None
        img_data = base64.b64decode(image_base64, validate=False)
        if len(img_data) > _MAX_IMAGE_BYTES:
            print(f"[upload] reject: decoded too large ({len(img_data)} bytes)", flush=True)
            return None
        ext = _sniff_image_ext(img_data[:12])
        if not ext:
            print(f"[upload] reject: not a known image format (head={img_data[:8].hex()})", flush=True)
            return None
        # 文件名用 uuid4 hex，不可枚举（修 #6 跨用户图泄露的最小成本方案）
        import uuid as _uuid
        fname = f"{_uuid.uuid4().hex}.{ext}"
        fpath = os.path.join(UPLOADS_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(img_data)
        return f"/uploads/{fname}"
    except Exception as e:
        print(f"[upload] save failed: {type(e).__name__}: {e}", flush=True)
        return None


def _compute_hours_since_last_user(history: list[dict]) -> float | None:
    """从 history（不含当前消息）算距上次 user 消息的小时数。无历史返回 None。
    SQLite CURRENT_TIMESTAMP 是 UTC，必须按 UTC 解析后跟 utcnow() 比较，
    否则在非 UTC 时区（如 CST +8）算出来恒定多 8 小时。"""
    for m in reversed(history):
        if m.get("role") != "user":
            continue
        ts = m.get("created_at")
        if not ts:
            continue
        try:
            if isinstance(ts, str):
                ts_str = ts.replace("T", " ").split(".")[0]
                created = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            elif isinstance(ts, datetime):
                created = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            else:
                return None
            delta = datetime.now(timezone.utc) - created
            return max(0.0, delta.total_seconds() / 3600)
        except Exception:
            return None
    return None  # 没有 user 历史（新对话）


def _compute_length_drop(history: list[dict], current_msg: str) -> bool:
    """当前消息长度 < 最近 user 消息平均 * 0.5 且至少有 5 条历史时返回 True。"""
    user_lens = [
        len(m.get("content") or "")
        for m in history
        if m.get("role") == "user" and m.get("content") and not m["content"].startswith("[")
    ]
    if len(user_lens) < 5:
        return False
    recent = user_lens[-8:]  # 最近 8 条
    avg = sum(recent) / len(recent)
    return len(current_msg) < avg * 0.5 and avg >= 6  # 避免平均本来就极短的误判


def execute_intent(intent: str, params: dict):
    """执行已识别的意图,返回结果。
    通常返回 str(文本回复);特殊意图(fetch_card)返回 dict(卡片数据)。
    上游 dispatcher 检测类型分流。"""
    if intent == "open_app":
        return open_application(params.get("app", ""))
    if intent == "send_wechat":
        return send_wechat_message(params.get("contact", ""), params.get("message", ""))
    if intent == "wechat_voice":
        return start_wechat_voice_call(params.get("contact", ""))
    if intent == "wechat_video":
        return start_wechat_video_call(params.get("contact", ""))
    if intent == "web_search":
        return web_search(params.get("query", ""))
    if intent == "hot_topics":
        return hot_topics(params.get("source", ""))
    if intent == "route":
        return route_query(params.get("origin", ""), params.get("destination", ""))
    if intent == "travel_plan":
        return travel_plan_query(params.get("query", ""))
    if intent == "set_reminder":
        return set_reminder(params.get("text", "提醒"), params.get("minutes", 5))
    if intent == "take_screenshot":
        return take_screenshot()
    if intent == "get_datetime":
        return get_datetime()
    if intent == "write_clipboard":
        return write_clipboard(params.get("content", ""))
    if intent == "fetch_card":
        return _fetch_card_impl(params.get("query", ""))  # 返回 dict
    if intent == "open_in_browser":
        # 用户明确要求"打开浏览器/用浏览器"——这种情况才打开外部浏览器
        return open_url(params.get("site", ""))
    return "不知道怎么执行这个"


@app.get("/asr/token")
async def asr_token():
    """阿里云 NLS 实时语音识别 token"""
    return generate_nls_token()


@app.get("/tts/synthesize")
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


@app.get("/tts/stream")
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


@app.websocket("/tts/ws")
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


@app.post("/asr/recognize")
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
                proc = subprocess.run(
                    [ffmpeg, "-y", "-i", inp.name, "-ar", str(req.sample_rate), "-ac", "1", "-f", "s16le", out.name],
                    capture_output=True, timeout=10,
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

    result = asr_recognize(audio_bytes, "pcm", req.sample_rate)
    print(f"[ASR] result: {result}")
    return result


@app.get("/")
async def root():
    return {"status": "ok", "name": "Chloe API"}


@app.post("/chat")
async def chat(req: ChatRequest, user: str = Depends(get_current_user)):
    has_image = bool(req.image_base64)
    if not req.message.strip() and not has_image:
        raise HTTPException(status_code=400, detail="message 和图片不能同时为空")

    await get_or_create_user(user)

    # ── 草莓余额检查（DEV 模式跳过）────────────────────────────
    DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
    if not DEV_MODE:
        balance = await get_strawberry_balance(user)
        if balance <= 0:
            async def _no_balance():
                yield f"data: {json.dumps({'error': '草莓不足，请充值后继续聊天 🍓'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(_no_balance(), media_type="text/event-stream")

    history = await get_messages(user, limit=60)
    message_count = await count_messages(user)  # 真实总数，不能用 len(history)（封顶 60 永远进不了 EMBODIED）

    # 图片处理：保存到 uploads/，拿到相对 URL
    image_path = None
    if has_image:
        image_path = _save_uploaded_image(req.image_base64)

    user_content = req.message.strip() or "[发了一张图片]"

    # 黏附心信号（用 history 算，此时 history 还不含当前消息——正确）
    hours_since_last = _compute_hours_since_last_user(history)
    length_drop = _compute_length_drop(history, user_content)

    await save_message(user, "user", user_content, image_path)

    # 加载画像（含 special_dates），传给 persona 做日期感知
    from database import get_profile
    user_profile = await get_profile(user)

    # 提取用户语气特征（镜像阶段需要）
    from avatar_state import extract_tone_profile, build_tone_description, get_stage, AvatarStage
    avatar_stage = get_stage(message_count)
    tone_description = ""
    if avatar_stage in (AvatarStage.MIRRORING, AvatarStage.EMBODIED):
        tone = extract_tone_profile(history)
        tone_description = build_tone_description(tone)

    system_prompt = build_system_prompt(
        user,
        message_count,
        hours_since_last=hours_since_last,
        length_drop=length_drop,
        profile=user_profile,
        tone_description=tone_description,
    )

    # 硬词触发：消息里含"必须/应该/离不开/以为"等词时，动态注入"本轮必须戳那个词"的强提示
    # 这是把 prompt 里被稀释的"反问硬词"规则放大到当轮最高优先级
    HARD_WORDS = ["必须", "应该", "离不开", "我以为", "一定要", "只能", "不得不", "肯定要", "非得"]
    detected_hard = [w for w in HARD_WORDS if w in req.message]
    print(f"[硬词检测] message={req.message!r}, detected={detected_hard}")
    if detected_hard:
        first_hard = detected_hard[0]
        joined_hard = "、".join(detected_hard)
        system_prompt += (
            "\n\n【⚠️ 即时引导 — 本轮的核心动作】\n"
            f"用户这条消息里出现了硬词：{joined_hard}。\n"
            "\n"
            f"硬词意味着对方头脑里有一个绷紧的判断（『{first_hard}』）。\n"
            "你本轮的核心动作不是替对方判断，也不是给建议——\n"
            "是用一个具体的反问，**邀请对方回到自身的现实**，让对方自己看清这个判断是真的成立还是头脑里绷紧的。\n"
            "\n"
            "═══ 🎯 语气原则（这条最重要）═══\n"
            "**平和，但直戳要害。**\n"
            "你的力量不在语气的强度，在问题本身的精准。\n"
            "好的反问，让对方读完停顿三秒，心里冒出：『我靠，我怎么没想过这个角度。』——\n"
            "这是**问题本身击中盲点的震惊**，不是被怼出来的不爽。\n"
            "\n"
            "❌ 错的语气（粗砺/审讯/说教，会激起防御）：\n"
            "  - 『操别给自己上发条』『你这必须哪儿来的』『别给自己加码』\n"
            "  - 任何带火气、带评判、带'你不该这样'感觉的话\n"
            "\n"
            "✅ 对的语气（平静、具体、克制——像一个看清楚事情的老朋友轻轻问一句）：\n"
            "  - 『做成这事要的本事，你都备齐了吗？』\n"
            "  - 『不做的话，最坏会怎样？』\n"
            "  - 『做成了，给你的是你真要的吗？』\n"
            "  - 『是有人压你，还是你自己想做？』\n"
            "  - 『一年后回头看，这事还有这么重？』\n"
            "（注意这些句子的共同点：没有情绪词，没有评判，但每一句都让对方往里看一层。）\n"
            "\n"
            "═══ 📍 反问的『维度池』 ═══\n"
            "根据对方的具体话语，从下面挑 1 个最贴切的切入（不要罗列、不要审讯）：\n"
            "\n"
            "─── A. 看外在现实 ───\n"
            "  ① **能力**：『做成这事要的本事，你都备齐了吗？』\n"
            "  ② **资源**：『手上的时间、人、钱，撑得起这件事吗？』\n"
            "  ③ **处境**：『是有人在催你，还是你自己想做？』\n"
            "  ④ **时机**：『非现在不可？还是这是你自己定的节点？』\n"
            "\n"
            "─── B. 看自己内在 ───\n"
            "  ⑤ **意愿**：『这是你真想做的事，还是你觉得自己该做的事？』\n"
            "  ⑥ **情绪**：『让你觉得必须的，是这件事本身，还是心里的某种害怕？』\n"
            "  ⑦ **价值**：『做成了，给你的是你真要的吗？』\n"
            "  ⑧ **身体**：『你现在的状态，撑得住这件事吗？』\n"
            "\n"
            "─── C. 看判断本身 ───\n"
            "  ⑨ **后果**：『不做的话，最坏会怎样？』\n"
            "  ⑩ **代价**：『做成它要你付出什么？这些代价你愿付吗？』\n"
            "  ⑪ **替代**：『这是唯一的路吗？还是只是你看见的那条？』\n"
            "  ⑫ **时间尺度**：『一年后回头看，这事还有这么重吗？』\n"
            "\n"
            "═══ 怎么挑维度 ═══\n"
            "  - 听对方话里最绷紧/最具体的那一点，往那个维度切。\n"
            "  - 『我必须做成这事业』→ 偏 ⑦价值 / ⑩代价 / ①能力\n"
            "  - 『我离不开他』→ 偏 ⑤意愿 / ⑥情绪 / ⑨后果\n"
            "  - 『我必须今晚做完』→ 偏 ③处境 / ④时机 / ⑧身体\n"
            "  - 『我应该接受现实』→ 偏 ⑥情绪 / ⑨后果\n"
            "  - 『我以为他会懂』→ 偏 ⑤意愿 / ⑦价值\n"
            "\n"
            "═══ 核心原则 ═══\n"
            "不替对方判断真假，是让对方自己回到具体的现实里。\n"
            "对方说『我必须做成』，你不下结论说『没必要这么硬』——\n"
            "你问『做成的代价你愿付吗 / 给你的是你真要的吗』，让事实自己回答。\n"
            "\n"
            "❌ 不要做：\n"
            "  - 给建议（'先列个计划'）\n"
            "  - 加油打气（'你能行'）\n"
            "  - 挑战推进（'那就去做'）\n"
            "  - 替对方下结论（'你不必这么硬'）\n"
            "  - 粗砺质问（'操别给自己上发条' / '你这必须哪儿来的'）\n"
            "  - 罗列多个维度（'你能力够吗资源够吗时机对吗'——这是审讯）\n"
            "  - 写括号旁白（'叹了口气' / '看你一眼'——真人发微信不描述动作神态）\n"
            "\n"
            "✅ 一句话就够，平和直击，从一个维度切进去——不展开，不长篇，问完留白让对方自己回味。\n"
        )

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_content})

    # qwen 对"播报/朗读/念出来"这类词的训练倾向太强（自动解释 TTS 机制、教对方开手机朗读），
    # 顶部 persona 禁令压不住。在 user 消息后贴一条强约束 system，离生成位置最近、attention 最大。
    import re as _re
    if _re.search(r"(播报|朗读|口播|念出来|读出来|念一[下遍]|读一[下遍]|大声[念读])", req.message or ""):
        messages.append({
            "role": "system",
            "content": (
                "对方刚才请求你**直接开口说话**——前端会把你这条回复送进 TTS 念给对方听。"
                "你只能做一件事：把上一条消息用更口语化的方式重新说一遍，或就当前话题继续聊几句。"
                "绝对禁止：解释 TTS/朗读机制；说『我没法播报』『我没有朗读功能』『我的语音是文字不是声波』；"
                "给『语音稿』让对方复制；列 iPhone/安卓/Chrome 朗读步骤；说『手把手教你』。"
                "对方听得见你说话，跟机制无关，不用解释。"
            ),
        })

    async def generate():
        full_response = ""
        # ── 使用埋点：每次 chat 一条汇总事件，沿途收集关键参数 ──
        _trace_info = {
            "mode": None,
            "intent": None,
            "model": None,
            "has_image": has_image,
            "tool": None,
            "message_count": message_count,
        }
        try:
            # ── 0. 模式判定（双模式系统 P1.5）──
            # detect_mode 内部跑同步 LLM 调用，必须扔到线程池，否则会阻塞 event loop
            # 其他在 chat 路径上的同步 LLM/IO 调用同理（recognize_intent / execute_intent）
            mode = await asyncio.to_thread(detect_mode, client, user, req.message, history)
            _trace_info["mode"] = mode
            sys_prompt_final = apply_mode_prompt(system_prompt, mode)

            # 镜子模式：跳过所有意图识别 + 工具调用，直走简化 Persona
            if mode == "mirror":
                # 只有用户明确手动切镜子（说"别给建议"之类）才清 pending；
                # 自动判定（连续短情绪 / LLM 判定发泄）可能误伤——用户也许只是在补工具参数
                _mode_state = get_user_mode(user)
                _trigger = (_mode_state.get("last_trigger") or "")
                if _trigger.startswith("manual"):
                    clear_pending(user)
                _slot = choose_model(user, user_content, "mirror")
                _trace_info["model"] = _slot
                stream, _actually_qwen = _create_stream_with_fallback(
                    _slot == "qwen",
                    [{"role": "system", "content": sys_prompt_final}] + messages,
                    max_tokens=80,
                    temperature=1.0,
                    frequency_penalty=0.6,
                    presence_penalty=0.4,
                )
                for chunk in stream:
                    text = chunk.choices[0].delta.content or ""
                    if text:
                        full_response += text
                        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                await save_message(user, "assistant", full_response)
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                if not _actually_qwen:
                    token_budget.add(user, len(full_response) // 2)
                return

            # ── 朋友模式：保留现有完整逻辑 ──
            # 有图片：用 qwen-vl-max 看图，跳过意图识别。
            if has_image:
                # base64 直接喂 VL，避免落盘再读盘
                _img_raw = req.image_base64 or ""
                _mime = "png"
                if _img_raw.startswith("data:image/"):
                    try:
                        _mime = _img_raw.split("/", 1)[1].split(";", 1)[0] or "png"
                    except Exception:
                        _mime = "png"
                _img_b64 = _img_raw.split(",", 1)[1] if "," in _img_raw else _img_raw

                vl_system = (
                    sys_prompt_final
                    + "\n\n【临时】对方刚发了张图给你。你能看到。用Chloe的语气，"
                    "**一两句话**讲图里跟当前话题相关的关键信息——"
                    "不要 OCR 逐字段念，不要说『这张图显示...』『从图中可以看出...』这种主持人腔，"
                    "就像朋友凑过来扫一眼，挑最有意思 / 最相关的一两点说出来。"
                    "如果对方文字里问了具体问题（『这是什么』『多少钱』『几点』），先回答那个。"
                )

                vl_messages = [
                    {"role": "system", "content": vl_system},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/{_mime};base64,{_img_b64}"}},
                        {"type": "text", "text": user_content},
                    ]},
                ]

                try:
                    stream = QWEN_CLIENT.chat.completions.create(
                        model="qwen-vl-max",
                        messages=vl_messages,
                        max_tokens=400,
                        temperature=0.9,
                        stream=True,
                    )
                    for chunk in stream:
                        text = chunk.choices[0].delta.content or ""
                        if text:
                            full_response += text
                            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    full_response = "图我接到了，但看的时候出了点意外，再发一次试试？"
                    yield f"data: {json.dumps({'text': full_response}, ensure_ascii=False)}\n\n"
                    print(f"[chat] qwen-vl-max error: {type(e).__name__}: {e}", flush=True)

                await save_message(user, "assistant", full_response)
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                return

            # ── 1. 检查是否有等待补全参数的 pending intent ──
            pending = get_pending(user)
            if pending:
                filled = fill_param(pending, req.message)
                if not filled["missing"]:
                    # 参数补全，执行
                    clear_pending(user)
                    _trace_info["intent"] = filled["intent"]
                    _trace_info["tool"] = filled["intent"]
                    async with trace_span(user, "tool_call", filled["intent"], payload={"via": "pending_fill"}):
                        result = await asyncio.to_thread(execute_intent, filled["intent"], filled["params"])
                    if isinstance(result, dict) and result.get("type") == "card":
                        # 卡片数据走专门 SSE 事件
                        yield f"data: {json.dumps({'card': result}, ensure_ascii=False)}\n\n"
                        if result.get("subtype") == "travel_plan":
                            from tools.travel_plan import build_playback
                            playback = build_playback(result)
                            yield f"data: {json.dumps({'text': playback}, ensure_ascii=False)}\n\n"
                            full_response = playback
                        else:
                            # 数据库存简化纯文本，历史回放友好
                            full_response = _summarize_card_for_history(result)
                    else:
                        full_response = result
                        yield f"data: {json.dumps({'text': result}, ensure_ascii=False)}\n\n"
                    await save_message(user, "assistant", full_response)
                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                    return
                else:
                    # 还缺参数，继续追问
                    set_pending(user, filled)
                    question = ask_missing(filled["missing"][0])
                    full_response = question
                    yield f"data: {json.dumps({'text': question}, ensure_ascii=False)}\n\n"
                    await save_message(user, "assistant", full_response)
                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                    return

            # ── 2. 意图识别（JSON mode，带上下文）──
            intent_result = await asyncio.to_thread(recognize_intent, client, req.message, history)
            # LLM 意图路由偶尔把"帮我看下天气"/"我查一下 XX"误判为 null——正则补一刀
            # 只兜"帮我/我 + 查/搜/找/看 + 一下/..." 和句首"查一下/搜搜..."这两种明显搜索措辞
            # ("你有没有时间"之类靠 LLM prompt 例子识别，不在 regex 里硬抠)
            if intent_result["intent"] is None:
                import re as _re
                _query = None
                for _pat in [
                    r"(?:帮我?|我)\s*(?:查|搜|找|看)(?:一下|下|看|查|搜|找|个|看看)?\s*(\S.+)",
                    r"^(?:查一下|查查|查下|搜一下|搜搜|搜下|找一下|找找|找下|看一下|看看|看下)\s*(\S.+)",
                ]:
                    _m = _re.search(_pat, req.message)
                    if not _m:
                        continue
                    cand = _m.group(1)
                    # 剥掉残余的语气补语（"一下吧"、"下" 等被正则吃剩的尾巴）
                    cand = _re.sub(r"^(?:一下|下|看|看看|个)\s*", "", cand)
                    cand = cand.strip("，。?？.! 吧啊呢哦呀")
                    if len(cand) >= 2 and not _re.match(r"^https?://", cand):
                        _query = cand
                        break
                if _query:
                    intent_result = {"intent": "web_search", "params": {"query": _query}, "missing": []}
            print(f"[意图识别] message={req.message[:60]!r}, intent={intent_result.get('intent')}, missing={intent_result.get('missing')}")
            _trace_info["intent"] = intent_result.get("intent")

            if intent_result["intent"] is not None:
                if not intent_result["missing"]:
                    # 意图明确，参数完整，直接执行
                    _trace_info["tool"] = intent_result["intent"]
                    async with trace_span(user, "tool_call", intent_result["intent"], payload={"via": "direct"}):
                        result = await asyncio.to_thread(execute_intent, intent_result["intent"], intent_result["params"])
                    if isinstance(result, dict) and result.get("type") == "card":
                        # 卡片数据走专门 SSE 事件
                        yield f"data: {json.dumps({'card': result}, ensure_ascii=False)}\n\n"
                        # 旅行规划卡：除了右侧卡片，再把要点完整口播 + 追问优化方向
                        if result.get("subtype") == "travel_plan":
                            from tools.travel_plan import build_playback
                            playback = build_playback(result)
                            yield f"data: {json.dumps({'text': playback}, ensure_ascii=False)}\n\n"
                            full_response = playback
                        else:
                            full_response = _summarize_card_for_history(result)
                    else:
                        full_response = result
                        yield f"data: {json.dumps({'text': result}, ensure_ascii=False)}\n\n"
                else:
                    # 意图明确，但缺参数，存 pending 并追问
                    set_pending(user, intent_result)
                    question = ask_missing(intent_result["missing"][0])
                    full_response = question
                    yield f"data: {json.dumps({'text': question}, ensure_ascii=False)}\n\n"
                await save_message(user, "assistant", full_response)
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                return

            # ── 3. 普通对话，走Chloe（路由决定使用哪个模型槽）──
            _slot      = choose_model(user, user_content, "normal")
            _trace_info["model"] = _slot
            _use_light = (_slot == "qwen")
            # max_tokens 统一给 700：_create_stream_with_fallback 会在 qwen 失败时
            # 自动切 deepseek，但 max_tokens 是事先传入的参数，给小了 fallback 后
            # deepseek 也被锁在小上限，对话被砍在半截。给统一上限消掉这个漏洞。
            # qwen 自己回短句时不会用满，没浪费。
            _max_tok   = 700
            _temp      = 0.9  if _use_light else 1.05
            _freq_pen  = 0.3  if _use_light else 0.4
            _pres_pen  = 0.2  if _use_light else 0.4

            stream, _actually_qwen = _create_stream_with_fallback(
                _use_light,
                [{"role": "system", "content": sys_prompt_final}] + messages,
                max_tokens=_max_tok,
                temperature=_temp,
                frequency_penalty=_freq_pen,
                presence_penalty=_pres_pen,
            )
            _finish_reason = None
            for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                fr = chunk.choices[0].finish_reason
                if fr:
                    _finish_reason = fr
            if _finish_reason == "length":
                # 撞到 max_tokens 上限 —— 用户会看到回答被砍在半句话
                print(f"[chat] truncated: user={user} model={'qwen' if _actually_qwen else 'deepseek'} "
                      f"max_tokens={_max_tok} chars={len(full_response)}", flush=True)

            await save_message(user, "assistant", full_response)
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

            # DeepSeek 实际使用时计入预算（含 Gemini 失败回退的情况）
            if not _actually_qwen:
                token_budget.add(user, len(full_response) // 2)

            # ── 4. 每 5 轮后台静默提取画像（不阻塞返回）──
            if message_count > 0 and message_count % 5 == 0:
                all_msgs = await get_messages(user, limit=60)
                asyncio.create_task(extract_and_update(client, user, all_msgs))

            # ── 5. 对话内匹配检测（后台异步，不阻塞返回）──
            # 只在朋友模式的普通对话流跑（这里已经过了 mirror 分支 + 工具分支）
            asyncio.create_task(
                detect_matches_and_save(
                    client,
                    user,
                    user_content,
                    history + [{"role": "user", "content": user_content}],
                    message_count=message_count,
                )
            )

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            _trace_info["error"] = str(e)[:200]
        finally:
            # 有实际回复才扣草莓（DEV 模式跳过）
            DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
            if full_response and not DEV_MODE:
                await deduct_strawberry(user, 10)
            # ── 写 chat 汇总事件 ──
            _trace_info["resp_chars"] = len(full_response)
            await log_event(user, "chat", payload=_trace_info,
                            success=("error" not in _trace_info))

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/match")
async def get_matches(user: str = Depends(get_current_user)):
    """为当前登录用户计算并返回匹配结果"""
    await get_or_create_user(user)
    results = await find_matches(client, user)
    return {"username": user, "matches": results}


@app.post("/match/response")
async def match_response(body: dict, user: str = Depends(get_current_user)):
    """记录当前用户对匹配的态度：accept / reject；可选附带打招呼内容。
    body: { peer: str, response: 'accept'|'reject', greeting?: str }"""
    from database import update_match_response, save_greeting
    peer = (body.get("peer") or "").strip()
    response = (body.get("response") or "").strip()
    if not peer or response not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="peer 和 response 必填")
    await update_match_response(user, peer, response)
    greeting = (body.get("greeting") or "").strip()
    if greeting and response == "accept":
        await save_greeting(user, peer, greeting)
    return {"status": "ok"}


@app.get("/match/pending")
async def get_pending_matches(user: str = Depends(get_current_user)):
    """拉对话内匹配检测命中的卡片（前端聊天页轮询/回复后调用）"""
    matches = await get_pending_matches_for_user(user, limit=5)
    return {"username": user, "pending": matches}


@app.get("/user/settings")
async def get_user_settings_api(user: str = Depends(get_current_user)):
    """获取当前用户性别 + 匹配偏好"""
    from database import get_user_settings
    await get_or_create_user(user)
    settings = await get_user_settings(user)
    return {"username": user, "settings": settings}


@app.post("/user/settings")
async def update_user_settings_api(body: dict, user: str = Depends(get_current_user)):
    """更新当前用户性别 + 匹配偏好"""
    from database import update_user_settings
    await get_or_create_user(user)
    gender = body.get("gender")
    match_pref = body.get("match_pref", "both")
    await update_user_settings(user, gender, match_pref)
    return {"status": "ok"}


@app.post("/match/pending/{match_id}/seen")
async def mark_match_seen(match_id: int, user: str = Depends(get_current_user)):
    """前端弹了卡片后标记已看，避免重复弹。校验卡片归属当前用户。"""
    from database import get_pending_match_owner
    owner = await get_pending_match_owner(match_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="匹配不存在")
    if owner != user:
        raise HTTPException(status_code=403, detail="无权操作")
    await mark_pending_match_seen(match_id)
    return {"status": "ok"}


@app.get("/profile")
async def get_user_profile(user: str = Depends(get_current_user)):
    from database import get_profile
    profile = await get_profile(user)
    return {"username": user, "profile": profile}


@app.get("/history")
async def get_history(user: str = Depends(get_current_user)):
    await get_or_create_user(user)
    messages = await get_all_messages(user)
    return {"username": user, "messages": messages}


@app.delete("/message/{message_id}")
async def delete_one_message(message_id: int, user: str = Depends(get_current_user)):
    from database import get_message_owner
    owner = await get_message_owner(message_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if owner != user:
        raise HTTPException(status_code=403, detail="无权操作")
    await delete_message(message_id)
    return {"status": "deleted"}


@app.delete("/history")
async def clear_history(user: str = Depends(get_current_user)):
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE username = ?", (user,))
        await db.commit()
    return {"status": "cleared"}


# ── WebSocket 真人聊天 ──────────────────────────────────────────

def make_room_id(user_a: str, user_b: str) -> str:
    """房间 ID = 两个用户名排序后拼接，确保 A-B 和 B-A 是同一个房间"""
    return "__".join(sorted([user_a, user_b]))


async def _require_peer_room_access(user: str, room_id: str) -> str:
    """校验当前用户能访问 room_id，并返回 peer 用户名。"""
    parts = room_id.split("__")
    if len(parts) != 2 or user not in parts:
        raise HTTPException(status_code=403, detail="不在该房间内")
    peer = parts[1] if parts[0] == user else parts[0]
    if peer == user:
        raise HTTPException(status_code=403, detail="房间无效")
    accepted_peers = await get_accepted_matches(user)
    if peer not in accepted_peers:
        raise HTTPException(status_code=403, detail="双方尚未互相接受匹配")
    if make_room_id(user, peer) != room_id:
        raise HTTPException(status_code=403, detail="房间无效")
    return peer


class ConnectionManager:
    def __init__(self):
        # room_id → {username: WebSocket}
        self.rooms: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, username: str, ws: WebSocket):
        await ws.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        self.rooms[room_id][username] = ws

    def disconnect(self, room_id: str, username: str):
        if room_id in self.rooms:
            self.rooms[room_id].pop(username, None)
            if not self.rooms[room_id]:
                del self.rooms[room_id]

    async def broadcast(self, room_id: str, message: dict, exclude: str | None = None):
        if room_id not in self.rooms:
            return
        dead = []
        for uname, ws in self.rooms[room_id].items():
            if uname == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uname)
        for uname in dead:
            self.disconnect(room_id, uname)


ws_manager = ConnectionManager()


@app.websocket("/ws/peer/{room_id}")
async def peer_chat_ws(ws: WebSocket, room_id: str):
    """WebSocket 鉴权走 query: ?token=<jwt>（或 DEV_MODE 下 ?dev_user=<name>）"""
    username = await ws_authenticate(ws)
    if not username:
        await ws.close(code=4401)
        return
    try:
        await _require_peer_room_access(username, room_id)
    except HTTPException:
        await ws.close(code=4403)
        return
    await ws_manager.connect(room_id, username, ws)
    # 连接后推送历史消息
    history = await get_peer_messages(room_id, limit=100)
    await ws.send_json({"type": "history", "messages": history})
    try:
        while True:
            data = await ws.receive_json()
            content = (data.get("content") or "").strip()
            if not content:
                continue
            await save_peer_message(room_id, username, content)
            msg = {"type": "message", "sender": username, "content": content,
                   "created_at": datetime.now().isoformat()}
            # 给自己确认
            await ws.send_json(msg)
            # 广播给房间里的其他人
            await ws_manager.broadcast(room_id, msg, exclude=username)
    except WebSocketDisconnect:
        ws_manager.disconnect(room_id, username)


@app.get("/peer/rooms")
async def get_peer_rooms(user: str = Depends(get_current_user)):
    """返回当前用户所有已接受匹配的对方用户名（可开启聊天的列表）"""
    peers = await get_accepted_matches(user)
    rooms = [{"peer": p, "room_id": make_room_id(user, p)} for p in peers]
    return {"username": user, "rooms": rooms}


@app.get("/peer/history/{room_id}")
async def peer_history(room_id: str, limit: int = 100, user: str = Depends(get_current_user)):
    await _require_peer_room_access(user, room_id)
    messages = await get_peer_messages(room_id, limit=limit)
    return {"room_id": room_id, "messages": messages}


@app.get("/usage")
async def get_usage(user: str = Depends(get_current_user)):
    """返回当前用户今日 + 本月草莓用量"""
    from model_router import DEEPSEEK_DAILY_LIMIT, DEEPSEEK_MONTHLY_LIMIT
    daily   = token_budget.get_daily(user)
    monthly = token_budget.get_monthly(user)
    def pct(used, limit): return min(100, round(used / limit * 100)) if limit > 0 else 0
    return {
        "daily":   {"used": daily,   "limit": DEEPSEEK_DAILY_LIMIT,   "percent": pct(daily,   DEEPSEEK_DAILY_LIMIT)},
        "monthly": {"used": monthly, "limit": DEEPSEEK_MONTHLY_LIMIT, "percent": pct(monthly, DEEPSEEK_MONTHLY_LIMIT)},
    }


# 预定义标签列表（前后端共用）
PLAZA_TAGS = ["日常", "风景", "美食", "创意", "情感", "搞笑", "音乐", "运动", "宠物", "穿搭", "旅行", "随拍"]


@app.get("/hot/expand")
async def hot_expand(title: str = ""):
    """把一个热搜标题展开成结构化内容卡（千问联网检索）。
    注意：此路由必须注册在 /hot/{source} 之前，否则被泛匹配吃掉。"""
    import asyncio
    from tools.topic_expand import topic_expand
    return await asyncio.to_thread(topic_expand, title)


@app.get("/hot/{source}")
async def hot_endpoint(source: str = "微博"):
    """直接给前端拉热搜（广场角落 HUD 用）。source: 微博 / 知乎 / 抖音 / B站 / 头条"""
    import asyncio
    return await asyncio.to_thread(hot_topics, source)


# ── 热搜分类关键词表 ──────────────────────────────────────────────
# 顺序敏感：按从上到下的优先级匹配（"历史"放"文化"前，因为"考古文物"应归历史不是文化）
_CAT_KEYWORDS: dict[str, list[str]] = {
    "娱乐": ["明星","演员","电影","电视","综艺","音乐","歌","剧","艺人","娱乐","演唱会",
             "舞台","歌手","主持","直播","网红","粉丝","偶像","选秀","剧情","笑","搞笑"],
    "经济": ["经济","股","市场","企业","房价","就业","贸易","工资","GDP","美元","人民币",
             "基金","投资","楼市","消费","通货","价格","出口","进口","利率","银行","上市"],
    "生活": ["美食","吃","餐","菜","厨","饮","咖啡","奶茶","早餐","晚餐","外卖","美妆","穿搭",
             "衣","鞋","健身","跑步","瑜伽","养生","睡眠","旅行","旅游","民宿","景点","宠物",
             "猫","狗","婚","恋爱","母婴","育儿","健康","看病","医生","本田","汽车","品牌"],
    "历史": ["历史","朝代","古代","唐代","宋代","明代","清代","秦","汉","三国","春秋","战国",
             "史记","史书","古人","古迹","遗址","文物","考古","出土","王朝","皇帝","战役",
             # 高频帝王名（用全名避免单字误中）
             "朱棣","朱元璋","朱高炽","朱高煦","李世民","赵匡胤","康熙","乾隆","嘉靖","雍正",
             "嬴政","刘邦","项羽","曹操","孙权","刘备","诸葛亮","武则天","唐玄宗","赵高",
             # 高频朝代/政治词
             "传位","皇位","登基","太子","太监","宦官","江山","御史","封建","科举","丝绸之路",
             "鸦片战争","辛亥","太平天国","民国","军阀"],
    "哲学": ["哲学","思想","思考","人生","意义","本质","存在","自由","信仰","禅","佛","道家",
             "儒","释","老子","庄子","孔子","苏格拉底","柏拉图","尼采","形而上","悟","觉悟",
             # 思辨/价值类常见词（知乎热榜很多）
             "为什么","如何理解","怎么看待","怎么理解","真相","对错","善恶","价值观","伦理",
             "道理","道德","内心","选择","命运","活着","死亡","幸福","痛苦","孤独"],
    "科技": ["AI","人工智能","科技","手机","互联网","芯片","航天","火箭","卫星","苹果",
             "华为","特斯拉","机器人","算法","大模型","ChatGPT","数据","云","数字","无人机",
             "Token","物理","物理学","浮力","量子","光速","引力","元素"],
    "文化": ["文化","教育","学校","大学","考试","高考","传统","非遗","节日","博物",
             "读书","文学","艺术","诗词","成语","汉字","语言","中医","国潮","习俗"],
    "时事": [],  # 兜底：未匹配到上面任何类的全归到时事
}

def _classify_topic(title: str) -> str:
    # 优先级显式声明：具体类别先匹配，"哲学"放最后做思辨兜底
    # （"哲学"的关键词里有"为什么/如何理解"这种问题前缀，太宽，
    #  必须让具体类如"科技/历史"先抢走，否则一道"为什么浮力..."会被归到哲学）
    order = ["娱乐", "经济", "生活", "历史", "科技", "文化", "哲学"]
    for cat in order:
        kws = _CAT_KEYWORDS.get(cat, [])
        if any(kw in title for kw in kws):
            return cat
    return "时事"


# ── LLM 整批分类（5 分钟缓存）──────────────────────────────────────
# 关键词字典覆盖不全（新词跟不上 / 顺序敏感把模糊词归错），
# 用 qwen-plus 整批理解一次。同批标题 5 分钟内不重复调。
import time as _time

CATEGORIES_DISPLAY = ["娱乐", "经济", "生活", "科技", "文化"]
_CLASSIFY_TTL = 300
_classify_cache: dict[int, tuple[float, dict[str, str]]] = {}

_BATCH_CLASSIFY_PROMPT = """你是热搜分类器，只输出 JSON 对象。

给你一批热搜标题（每行一个），把每条归到下面 5 类之一：
- 娱乐：明星 / 影视 / 综艺 / 音乐 / 网红 / 八卦 / 选秀
- 经济：股市 / 楼市 / 企业 / 消费 / 就业 / 价格 / 货币 / 贸易 / 财报
- 科技：AI / 芯片 / 互联网 / 航天 / 汽车工业 / 新能源 / 机器人 / 5G/6G / 量子 / 工业制造
- 文化：教育 / 高考 / 读书 / 艺术 / 传统 / 历史 / 考古 / 文物 / 宗教 / 思想
- 生活：美食 / 健康 / 宠物 / 旅行 / 穿搭 / 运动 / 婚恋 / 家庭 / 灾难 / 政策 / 民生 / 法律 / 犯罪 / 外交 / 体育赛事 / 国际新闻

规则：
- 一条标题只能归一类，挑最贴的
- 严格输出 JSON：{"标题原文": "类别", ...}
- 不解释，不 markdown，不加其他文字
- 标题列表为空时输出 {}
"""


def _classify_with_llm(titles: list[str]) -> dict[str, str]:
    """整批 LLM 分类。失败/超时 → 空 dict，调用方走关键词 fallback。"""
    if not titles:
        return {}
    key = hash(tuple(titles))
    now = _time.time()
    cached = _classify_cache.get(key)
    if cached and now - cached[0] < _CLASSIFY_TTL:
        return cached[1]
    try:
        resp = QWEN_CLIENT.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": _BATCH_CLASSIFY_PROMPT},
                {"role": "user", "content": "\n".join(titles)},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        clean = {str(k): str(v) for k, v in data.items() if str(v) in CATEGORIES_DISPLAY}
        _classify_cache[key] = (now, clean)
        return clean
    except Exception as e:
        print(f"[hot/categorized] LLM classify failed: {type(e).__name__}: {e}", flush=True)
        return {}


@app.get("/hot/categorized/all")
async def hot_categorized():
    """返回按类别分类的热搜，供广场分类卡片使用。
    源：微博 + 抖音 + 知乎 + B站 + 头条。
    多源并行拉，单源失败不影响其他。"""
    import asyncio
    results = await asyncio.gather(
        asyncio.to_thread(hot_topics, "微博"),
        asyncio.to_thread(hot_topics, "抖音"),
        asyncio.to_thread(hot_topics, "知乎"),
        asyncio.to_thread(hot_topics, "B站"),
        asyncio.to_thread(hot_topics, "头条"),
        return_exceptions=True,
    )

    all_titles: list[str] = []
    for d in results:
        if isinstance(d, Exception) or not isinstance(d, dict):
            continue
        for pt in d.get("points", []):
            # 去掉 "1. 标题 · 热度" 里的序号
            title = pt.split("·")[0].strip().lstrip("0123456789. ")
            if title:
                all_titles.append(title)

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for t in all_titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    # LLM 整批分类（带缓存）；漏归 / 失败的标题走关键词 fallback
    llm_map = await asyncio.to_thread(_classify_with_llm, unique)
    _fallback_map = {"历史": "文化", "哲学": "文化", "时事": "生活"}

    buckets: dict[str, list[str]] = {c: [] for c in CATEGORIES_DISPLAY}
    for title in unique:
        cat = llm_map.get(title)
        if cat not in CATEGORIES_DISPLAY:
            kw_cat = _classify_topic(title)
            cat = _fallback_map.get(kw_cat, kw_cat)
            if cat not in CATEGORIES_DISPLAY:
                cat = "生活"
        if len(buckets[cat]) < 5:
            buckets[cat].append(title)

    return {"categories": buckets}


@app.get("/plaza/tags")
async def plaza_tags():
    return {"tags": PLAZA_TAGS}


@app.get("/plaza/feed")
async def plaza_feed(
    tag: str = "",
    sort: str = "recommended",  # recommended | latest | hot
    limit: int = 30,
    offset: int = 0,
    user: str | None = Depends(get_optional_user),
):
    """feed：默认按用户偏好（推荐），可指定 latest / hot。匿名也能用，但无个性化"""
    from database import get_posts, get_tag_prefs, get_time_tag_prefs, get_time_slot
    posts = await get_posts(limit=200, offset=0)

    # 标签过滤
    if tag:
        posts = [p for p in posts if tag in p.get("tags", [])]

    if sort == "latest":
        posts.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    elif sort == "hot":
        posts.sort(key=lambda p: (p.get("likes", 0), p.get("created_at") or ""), reverse=True)
    else:  # recommended
        if user:
            global_prefs = await get_tag_prefs(user)
            time_prefs   = await get_time_tag_prefs(user)
            if global_prefs or time_prefs:
                def score(p):
                    tags = p.get("tags", [])
                    g = sum(global_prefs.get(t, 0) for t in tags)
                    s = sum(time_prefs.get(t, 0) * 1.5 for t in tags)
                    return g + s
                posts.sort(key=score, reverse=True)

    current_slot = get_time_slot()
    return {"posts": posts[offset: offset + limit], "time_slot": current_slot}


@app.get("/plaza/time-prefs")
async def plaza_time_prefs(user: str = Depends(get_current_user)):
    """返回当前用户各时段的标签偏好（用于可视化）"""
    from database import get_all_time_tag_prefs, get_time_slot
    prefs = await get_all_time_tag_prefs(user)
    return {"username": user, "time_slot": get_time_slot(), "prefs": prefs}


@app.get("/plaza/community-interests")
async def community_interests(user: str | None = Depends(get_optional_user)):
    """返回其他用户的兴趣标签，用于广场底部滚动展示（匿名）。
    已登录则排除自己；匿名则全量返回。"""
    import hashlib, aiosqlite
    from database import DB_PATH
    exclude = user or ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT username, tag, score FROM user_tag_prefs WHERE username != ? AND score > 0 ORDER BY score DESC LIMIT 80",
            (exclude,),
        ) as cursor:
            rows = await cursor.fetchall()
    seen: dict[str, int] = {}
    items = []
    for r in rows:
        u = r["username"]
        seen[u] = seen.get(u, 0) + 1
        if seen[u] > 3:
            continue
        anon = hashlib.md5(("fiona_plaza_" + u).encode()).hexdigest()[:6]
        items.append({"tag": f"#{r['tag']}", "user": anon})
    return {"items": items}


@app.post("/plaza/post")
async def plaza_post(
    caption: str = Form(default=""),
    tags: str = Form(default="[]"),
    file: UploadFile = File(...),
    user: str = Depends(get_current_user),
):
    import hashlib
    from database import save_post
    try:
        tag_list = json.loads(tags)
        tag_list = [t for t in tag_list if t in PLAZA_TAGS][:5]
    except Exception:
        tag_list = []
    anon_id = hashlib.md5(("fiona_plaza_" + user).encode()).hexdigest()[:8]
    media_path, media_type = await _save_plaza_upload(file)
    post_id = await save_post(anon_id, media_path, media_type, caption, tag_list)
    return {"id": post_id, "anon_id": anon_id, "media_path": media_path, "tags": tag_list}


@app.post("/plaza/like/{post_id}")
async def plaza_like(post_id: int, user: str = Depends(get_current_user)):
    from database import like_post, get_posts, update_tag_prefs
    likes = await like_post(post_id)
    # 更新用户标签喜好
    all_posts = await get_posts(limit=200)
    post = next((p for p in all_posts if p["id"] == post_id), None)
    if post and post.get("tags"):
        await update_tag_prefs(user, post["tags"])
    return {"likes": likes}


# ── 认证端点 ────────────────────────────────────────────────────

@app.post("/auth/send-otp")
async def send_otp_api(body: dict):
    phone = (body.get("phone") or "").strip()
    if not phone or len(phone) < 8:
        raise HTTPException(status_code=400, detail="手机号格式不对")
    code = make_otp()
    await save_otp(phone, code, ttl_seconds=300)
    ok = send_sms(phone, code)
    if not ok:
        raise HTTPException(status_code=500, detail="短信发送失败，请稍后重试")
    return {"status": "ok"}


@app.post("/auth/test-login")
async def test_login(body: dict | None = None):
    """开发测试入口：传 {"username": "alice"} 直接拿 JWT，不走短信验证。
    仅 DEV_MODE=1 时启用；生产环境（DEV_MODE 关掉）返回 404 把口子堵上。"""
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    body = body or {}
    username = (body.get("username") or "tester").strip() or "tester"
    await get_or_create_user(username)
    balance = await get_strawberry_balance(username)
    token = create_token(username)
    return {"token": token, "username": username, "balance": balance}


@app.post("/auth/verify-otp")
async def verify_otp_api(body: dict):
    phone = (body.get("phone") or "").strip()
    code  = (body.get("code")  or "").strip()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="参数缺失")
    ok = await check_and_consume_otp(phone, code)
    if not ok:
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    user = await get_or_create_user_by_phone(phone)
    token = create_token(user["username"])
    return {
        "token":    token,
        "username": user["username"],
        "balance":  user.get("strawberry_balance", 200),
    }


@app.get("/strawberry")
async def get_strawberry(user: str = Depends(get_current_user)):
    bal = await get_strawberry_balance(user)
    return {"username": user, "balance": bal}


# ── 用户列表（仅 DEV_MODE 开放，供本地切换身份用）─────────────
@app.get("/users")
async def list_users():
    """DEV_MODE=1 时返回所有用户列表，便于本地切身份调试；生产环境返回 404 隐藏。"""
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT username FROM users ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()
    return {"users": [r["username"] for r in rows]}
