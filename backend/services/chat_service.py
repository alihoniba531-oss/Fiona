# -*- coding: utf-8 -*-
"""
/chat 的服务层 —— 从 routers/chat.py 抽出，行为零改动。

分三层：
  1. 纯 helper：execute_intent / _summarize_card_for_history / _compute_* /
     build_hard_word_appendix —— 无副作用，可独立单测。
  2. build_context：预检（拉历史、存图、算信号、存 user 消息、拼 system prompt + messages），
     返回 ChatContext。余额检查留在 handler（它要早返回 StreamingResponse）。
  3. 五条流式分支（async generator）+ run_chat 编排：
     mirror / image / pending / intent / normal，各自 yield SSE 字符串、
     写入共享 ChatState（full_response + 埋点 trace）。
"""
import asyncio
import json
import re
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timezone

import anyio
from fastapi import HTTPException

from avatar_state import AvatarStage, build_tone_description, extract_tone_profile, get_stage
from agent_store import ResourceNotFound, get_memory_snapshot, resolve_chat_conversation
from conversation_matcher import detect_and_save as detect_matches_and_save
from database import (STRAWBERRY_COST_PER_REPLY, count_messages, get_messages,
                      refund_strawberries, save_message, set_message_image_summary)
from extractor import extract_and_update
from intent_router import ask_missing, clear_pending, explicit_image_intent, fill_param, get_pending, image_aspect_ratio, image_edit_requires_reference, image_generation_discussion, recognize_intent, set_pending
from llm import QWEN_CLIENT, _create_stream_with_fallback, client
from mode_switcher import apply_mode_prompt, detect_mode, get_user_mode
from model_router import choose_model, token_budget
from persona import BASE_SAFETY_RULES, build_system_prompt
from safety import CRISIS_GUIDANCE, CRISIS_RESOURCE_NOTE, detect_crisis
from tools.fetch_card import fetch_card as _fetch_card_impl
from tools.hot_topics import hot_topics
from tools.image_generation import ImageGenerationError, edit_image, generate_image
from tools.open_app import open_application
from tools.reminder import set_reminder
from tools.route import route as route_query
from tools.system_tools import get_datetime, open_url, take_screenshot, write_clipboard
from tools.travel_plan import build_playback
from tools.travel_plan import travel_plan as travel_plan_query
from tools.web_search import web_search
from tools.wechat_send import send_wechat_message, start_wechat_video_call, start_wechat_voice_call
from trace import log_event, trace_span
from utils.background_tasks import create_background_task
from utils.media import _save_uploaded_image, delete_uploaded_files
from utils.reference_images import prepare_reference_upload


_STREAM_END = object()
_UPSTREAM_ERROR_MESSAGE = "服务暂时不可用，请稍后再试"
_MODEL_ARREARAGE_MESSAGE = "模型服务账户欠费，暂时无法生成回复。请联系平台管理员恢复模型服务后重试。"
_IMAGE_GENERATION_USERS: set[str] = set()
_IMAGE_HEARTBEAT_SECONDS = 10
# 视觉分支拼进 VL 请求的历史条数上限（T2a）。
_VL_HISTORY_TURNS = 10
_BILLABLE_TOOLS = frozenset({
    "web_search", "hot_topics", "route", "travel_plan", "fetch_card", "get_datetime",
})


def _without_safety(prompt: str) -> str:
    return prompt.replace(BASE_SAFETY_RULES.strip(), "").strip()


def _final_system_prompt(
    prompt: str, *, crisis: bool = False, trailing_system: bool = False,
) -> str:
    """Put the safety rules on the final system message sent to the model."""
    prompt = _without_safety(prompt).replace(CRISIS_GUIDANCE.strip(), "").strip()
    if trailing_system:
        return prompt
    return prompt + "\n\n" + BASE_SAFETY_RULES.strip() + (
        "\n\n" + CRISIS_GUIDANCE.strip() if crisis else ""
    )


def _has_trailing_system(ctx: "ChatContext") -> bool:
    return bool(ctx.messages and ctx.messages[-1]["role"] == "system")


def _tool_billable(intent: str, result) -> bool:
    if intent not in _BILLABLE_TOOLS:
        return False
    if isinstance(result, dict):
        return result.get("type") == "card" and not result.get("error", False) and not result.get("stale", False)
    return intent == "get_datetime" and isinstance(result, str) and bool(result.strip())


def _crisis_resource_event(state: "ChatState") -> str:
    state.crisis_resource_sent = True
    text = "\n\n" + CRISIS_RESOURCE_NOTE
    state.full_response += text
    return _sse({"text": text})


def _upstream_error_message(error: Exception) -> str:
    """Expose only known provider codes, never raw error bodies or credentials."""
    if getattr(error, "code", None) == "Arrearage":
        return _MODEL_ARREARAGE_MESSAGE
    return _UPSTREAM_ERROR_MESSAGE


async def _iter_sync_stream(stream):
    """逐块在线程池推进同步 OpenAI Stream，避免阻塞 asyncio 事件循环。"""
    try:
        iterator = iter(stream)
        while True:
            chunk = await asyncio.to_thread(next, iterator, _STREAM_END)
            if chunk is _STREAM_END:
                break
            # OpenAI-compatible providers may send metadata/usage-only frames
            # before or after text. They have no choice to render.
            if chunk.choices == []:
                continue
            yield chunk
    finally:
        try:
            close = getattr(stream, "close", None)
            if callable(close):
                await asyncio.to_thread(close)
        except Exception as e:
            # 关闭失败不能覆盖原始流异常或改变 SSE 输出。
            print(f"[chat] stream close error type={type(e).__name__}", flush=True)


def _track_background_task(coro) -> asyncio.Task:
    """兼容现有调用点，实际由应用级追踪器统一管理。"""
    return create_background_task(coro, label="chat-postprocess")


def _sse(obj: dict) -> str:
    """统一 SSE 行格式（与原内联 f-string 输出逐字节一致）。"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ────────────────────────── 1. 纯 helper ──────────────────────────

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


# 硬词触发：消息里含"必须/应该/离不开/以为"等词时，动态注入"本轮必须戳那个词"的强提示
# 这是把 prompt 里被稀释的"反问硬词"规则放大到当轮最高优先级
HARD_WORDS = ["必须", "应该", "离不开", "我以为", "一定要", "只能", "不得不", "肯定要", "非得"]


def build_hard_word_appendix(message: str) -> str:
    """检测硬词并返回要追加到 system prompt 的即时引导块；无硬词返回空串。"""
    detected_hard = [w for w in HARD_WORDS if w in message]
    print(f"[硬词检测] chars={len(message)}, detected_count={len(detected_hard)}")
    if not detected_hard:
        return ""
    first_hard = detected_hard[0]
    joined_hard = "、".join(detected_hard)
    return (
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


# ────────────────────────── 2. 上下文装配 ──────────────────────────

@dataclass
class ChatContext:
    user: str
    message: str
    has_image: bool
    image_base64: str | None
    user_content: str
    history: list[dict]
    message_count: int
    system_prompt: str
    messages: list[dict]
    conversation_id: str | None = None
    agent: dict = field(default_factory=dict)
    memory_revision: int | None = None
    request_mode: str = "chat"
    aspect_ratio: str | None = None
    reference_image_path: str | None = None
    reference_image_paths: list[str] = field(default_factory=list)
    reference_sources_submitted: bool = False
    uploaded_image_path: str | None = None

    @property
    def state_key(self) -> str | tuple[str, str]:
        # 默认会话也按不可复用的 ID 隔离，删除后重建不会继承旧状态。
        if self.conversation_id is None:
            return self.user
        return (self.user, self.conversation_id)


@dataclass
class ChatState:
    """一次 chat 流式过程中的可变状态：累计回复 + 埋点 + 当前模式 prompt。"""
    trace: dict
    full_response: str = ""
    sys_prompt_final: str = ""
    response_saved: bool = False
    billable: bool = False
    crisis: bool = False
    crisis_resource_sent: bool = False


@dataclass
class ChatRunTracker:
    """Lets the ASGI response refund if streaming never starts."""
    started: bool = False


def _prepare_edit_references(sources) -> tuple[list[str], list[str]]:
    """Normalize local inputs in order; leave no partial batch on failure."""
    references: list[str] = []
    fresh: list[str] = []
    try:
        for source in sources:
            item = source.model_dump() if hasattr(source, "model_dump") else source
            if item.get("image_base64") is not None:
                upload = prepare_reference_upload(item["image_base64"])
                fresh.append(upload["image_path"])
                references.append(upload["image_path"])
            else:
                references.append(item["image_path"])
        return references, fresh
    except BaseException:
        delete_uploaded_files(fresh)
        raise


async def _persist_edit_references(req, user: str, conversation_id: str, user_content: str) -> list[str]:
    """Commit source ownership before generation, cleaning only unsaved uploads.

    The caller shields this whole operation so cancellation cannot orphan a
    file still being normalized by a worker or delete a committed attachment.
    """
    fresh: list[str] = []
    saved = False
    try:
        sources = getattr(req, "reference_images", None)
        if sources is not None:
            references, fresh = await asyncio.to_thread(_prepare_edit_references, sources)
        else:
            first = getattr(req, "reference_image_path", None)
            references = getattr(req, "reference_image_paths", None) or ([first] if first else [])
        options = {"new_reference_image_paths": fresh} if fresh else {}
        saved = await save_message(
            user, "user", user_content, references[0] if references else None,
            conversation_id=conversation_id, require_image_reference=True,
            reference_image_paths=references, **options,
        )
        if not saved:
            raise HTTPException(status_code=409, detail="账号或会话已失效")
        return references
    finally:
        if not saved:
            delete_uploaded_files(fresh)


async def build_context(req, user: str) -> ChatContext:
    """预检装配（不含余额检查 —— 那个要在 handler 早返回）。
    req 需有 .message 和 .image_base64，可带 .conversation_id。"""
    has_image = bool(req.image_base64)

    resolved = await resolve_chat_conversation(user, getattr(req, "conversation_id", None))
    conversation = resolved["conversation"]
    agent = resolved["agent"]
    conversation_id = conversation["id"]
    history = await get_messages(user, limit=60, conversation_id=conversation_id)
    message_count = await count_messages(user, conversation_id=conversation_id)

    # 图片处理：保存到 uploads/，拿到相对 URL
    image_path = None
    validated_image = None
    reference_image_path = getattr(req, "reference_image_path", None)
    reference_image_paths = getattr(req, "reference_image_paths", None) or ([reference_image_path] if reference_image_path else [])
    reference_image_path = reference_image_paths[0] if reference_image_paths else None
    if has_image:
        image_path, validated_image = _save_uploaded_image(req.image_base64)

    user_content = req.message.strip() or "[发了一张图片]"

    # 黏附心信号（用 history 算，此时 history 还不含当前消息——正确）
    hours_since_last = _compute_hours_since_last_user(history)
    length_drop = _compute_length_drop(history, user_content)

    if getattr(req, "mode", "chat") == "image_edit":
        persist_task = asyncio.create_task(_persist_edit_references(req, user, conversation_id, user_content))
        with anyio.CancelScope(shield=True):
            try:
                reference_image_paths = await asyncio.shield(persist_task)
            except asyncio.CancelledError:
                await persist_task
                raise
        reference_image_path = reference_image_paths[0]
        saved = True
    else:
        saved = await save_message(user, "user", user_content, image_path, conversation_id=conversation_id)
    if not saved:
        if image_path:
            delete_uploaded_files([image_path])
        raise HTTPException(status_code=409, detail="账号或会话已失效")

    # 加载画像（含 special_dates），传给 persona 做日期感知
    memory = await get_memory_snapshot(user, conversation_id)
    user_profile = memory["profile"]

    # 提取用户语气特征（镜像阶段需要）
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
        agent=agent,
    )
    crisis = detect_crisis(req.message)
    if not crisis:
        system_prompt += build_hard_word_appendix(req.message)

    # 图片摘要只注入给模型的这份副本；history 保持原始行（信号计算/画像提取/意图识别都在读它），
    # 数据库里的 content 与前端气泡一律不变。全角括号与半角占位符 [发了一张图片] 区分。
    messages = []
    for m in history:
        summary = m.get("image_summary")
        content = f"{m['content']}［图中：{summary}］" if summary else m["content"]
        messages.append({"role": m["role"], "content": content})
    messages.append({"role": "user", "content": user_content})

    # qwen 对"播报/朗读/念出来"这类词的训练倾向太强（自动解释 TTS 机制、教对方开手机朗读），
    # 顶部 persona 禁令压不住。在 user 消息后贴一条强约束 system，离生成位置最近、attention 最大。
    if not crisis and re.search(r"(播报|朗读|口播|念出来|读出来|念一[下遍]|读一[下遍]|大声[念读])", req.message or ""):
        messages.append({
            "role": "system",
            "content": (
                "对方刚才请求你**直接开口说话**——前端会把你这条回复送进 TTS 念给对方听。"
                "你只能做一件事：把上一条消息用更口语化的方式重新说一遍，或就当前话题继续聊几句。"
                "绝对禁止：解释 TTS/朗读机制；说『我没法播报』『我没有朗读功能』『我的语音是文字不是声波』；"
                "给『语音稿』让对方复制；列 iPhone/安卓/Chrome 朗读步骤；说『手把手教你』。"
                "对方听得见你说话，跟机制无关，不用解释。"
                "\n\n" + BASE_SAFETY_RULES.strip()
            ),
        })

    return ChatContext(
        user=user,
        message=req.message,
        has_image=has_image,
        image_base64=validated_image,
        user_content=user_content,
        history=history,
        message_count=message_count,
        system_prompt=system_prompt,
        messages=messages,
        conversation_id=conversation_id,
        agent=agent,
        memory_revision=memory["revision"],
        request_mode=getattr(req, "mode", "chat"),
        aspect_ratio=getattr(req, "aspect_ratio", None),
        reference_image_path=reference_image_path,
        reference_image_paths=list(reference_image_paths),
        reference_sources_submitted=getattr(req, "reference_images", None) is not None,
        uploaded_image_path=image_path if has_image else None,
    )


async def _save_response(ctx: ChatContext, state: ChatState, image_path: str | None = None) -> None:
    """所有分支固定写入请求开始时的会话，删除后不重建也不扣费。"""
    state.response_saved = bool(await save_message(
        ctx.user, "assistant", state.full_response, image_path=image_path, conversation_id=ctx.conversation_id,
    ))
    if not state.response_saved:
        raise RuntimeError("conversation no longer available")


async def _ensure_active_conversation(ctx: ChatContext) -> None:
    if ctx.conversation_id is not None:
        # 验证固定 ID，绝不把已删除的会话重新解析成默认会话。
        await resolve_chat_conversation(ctx.user, ctx.conversation_id)


# ────────────────────────── 3. 五条流式分支 ──────────────────────────

async def stream_generated_image(ctx: ChatContext, state: ChatState, prompt: str):
    """生成图先保存到固定会话，再交给页面；中断和删除均不留下孤立附件。"""
    await _ensure_active_conversation(ctx)
    editing = ctx.request_mode == "image_edit"
    tool = "edit_image" if editing else "generate_image"
    state.trace.update({"intent": tool, "tool": tool})
    if ctx.user in _IMAGE_GENERATION_USERS:
        state.trace["error"] = "ImageGenerationBusy"
        yield _sse({"error": "已有图片正在生成，请等待完成后再试"})
        return
    _IMAGE_GENERATION_USERS.add(ctx.user)
    task = None
    image_path = None
    try:
        if editing:
            references = ctx.reference_image_paths or ([ctx.reference_image_path] if ctx.reference_image_path else [])
            if not references:
                raise ImageGenerationError("请先在生成的图片上点击「以此图修改」")
            yield _sse({"status": "editing_image", "message": "正在按要求修改参考图，请稍候…"})
            # 引用在预检时校验并保存，按图1/图2/图3的原顺序发送，不夹带其他上下文。
            task = asyncio.create_task(edit_image(prompt, references[0] if len(references) == 1 else references, ctx.aspect_ratio))
        else:
            yield _sse({"status": "generating_image", "message": "正在生成图片，请稍候…"})
            # 只发送本次画面描述，不夹带人设、私有记忆或其他会话内容。
            task = asyncio.create_task(generate_image(prompt, ctx.aspect_ratio or image_aspect_ratio(prompt)))
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=_IMAGE_HEARTBEAT_SECONDS)
            if not done:
                yield ": generating-image\n\n"
        generated = task.result()
        image_path = generated["image_path"]
        await _ensure_active_conversation(ctx)
        state.trace["model"] = generated["model"]
        state.full_response = "图片已修改。" if editing else "图片已生成。"
        # 若客户端恰好在落库期间离开，先确认事务结果，避免误删已持久化的图。
        save_task = asyncio.create_task(_save_response(ctx, state, image_path=image_path))
        with anyio.CancelScope(shield=True):
            try:
                await asyncio.shield(save_task)
            except asyncio.CancelledError:
                await save_task
                raise
        state.billable = True
        if editing:
            generated = {**generated, "reference_image_path": references[0], "reference_image_paths": references}
        yield _sse({"generated_image": generated})
        yield _sse({"text": state.full_response})
        yield _sse({"done": True})
    except ImageGenerationError as exc:
        state.trace["error"] = "ImageGenerationError"
        yield _sse({"error": str(exc)})
    finally:
        with anyio.CancelScope(shield=True):
            if task is not None:
                if not task.done():
                    task.cancel()
                try:
                    generated = await task
                    image_path = image_path or generated.get("image_path")
                except (asyncio.CancelledError, Exception):
                    pass
            if image_path and not state.response_saved:
                delete_uploaded_files([image_path])
            _IMAGE_GENERATION_USERS.discard(ctx.user)

async def stream_mirror(ctx: ChatContext, state: ChatState):
    """镜子模式：跳过意图识别 + 工具调用，直走简化 Persona。"""
    # 只有用户明确手动切镜子（说"别给建议"之类）才清 pending；
    # 自动判定（连续短情绪 / LLM 判定发泄）可能误伤——用户也许只是在补工具参数
    _mode_state = get_user_mode(ctx.state_key)
    _trigger = (_mode_state.get("last_trigger") or "")
    if _trigger.startswith("manual"):
        clear_pending(ctx.state_key)
    _slot = choose_model(ctx.user, ctx.user_content, "mirror", len(ctx.history))
    state.trace["model"] = _slot
    try:
        stream, _actually_qwen = await asyncio.to_thread(
            _create_stream_with_fallback,
            _slot == "light",
            [{"role": "system", "content": state.sys_prompt_final}] + ctx.messages,
            max_tokens=80,
            temperature=1.0,
            frequency_penalty=0.6,
            presence_penalty=0.4,
        )
        async with aclosing(_iter_sync_stream(stream)) as chunks:
            async for chunk in chunks:
                text = chunk.choices[0].delta.content or ""
                if text:
                    state.full_response += text
                    yield _sse({"text": text})
    except Exception as e:
        state.trace["error"] = type(e).__name__
        print(f"[chat] mirror stream error type={type(e).__name__}", flush=True)
        yield _sse({"error": _upstream_error_message(e)})
        return
    if state.full_response.strip():
        await _save_response(ctx, state)
        state.billable = True
    yield _sse({"done": True})
    try:
        if not _actually_qwen:
            token_budget.add(ctx.user, len(state.full_response) // 2)
    except Exception as e:
        print(f"[chat] post-delivery accounting failed type={type(e).__name__}", flush=True)


async def stream_image(ctx: ChatContext, state: ChatState):
    """有图片：用 qwen-vl-max 看图，跳过意图识别。"""
    # base64 直接喂 VL，避免落盘再读盘
    _img_raw = ctx.image_base64 or ""
    _mime = "png"
    if _img_raw.startswith("data:image/"):
        try:
            _mime = _img_raw.split("/", 1)[1].split(";", 1)[0] or "png"
        except Exception:
            _mime = "png"
    _img_b64 = _img_raw.split(",", 1)[1] if "," in _img_raw else _img_raw

    vl_system = _final_system_prompt((
        _without_safety(state.sys_prompt_final).replace(CRISIS_GUIDANCE.strip(), "").strip()
        + "\n\n【临时】对方刚发了张图给你。你能看到。按当前分身的表达风格，"
        "**一两句话**讲图里跟当前话题相关的关键信息——"
        "不要 OCR 逐字段念，不要说『这张图显示...』『从图中可以看出...』这种主持人腔，"
        "就像朋友凑过来扫一眼，挑最有意思 / 最相关的一两点说出来。"
        "如果对方文字里问了具体问题（『这是什么』『多少钱』『几点』），先回答那个。"
    ), crisis=state.crisis, trailing_system=_has_trailing_system(ctx))

    # 三段：system + 最近若干条纯文本历史 + 当前多模态 user（本轮只发这一张图）。
    vl_messages = [{"role": "system", "content": vl_system}]
    vl_messages.extend(
        {"role": m["role"], "content": m["content"]}
        for m in ctx.history[-_VL_HISTORY_TURNS:]
        if m.get("content")
    )
    vl_messages.append({"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/{_mime};base64,{_img_b64}"}},
        {"type": "text", "text": ctx.user_content},
    ]})
    if _has_trailing_system(ctx):
        vl_messages.append(ctx.messages[-1])

    try:
        stream = await asyncio.to_thread(
            QWEN_CLIENT.chat.completions.create,
            model="qwen-vl-max",
            messages=vl_messages,
            max_tokens=400,
            temperature=0.9,
            stream=True,
        )
        async with aclosing(_iter_sync_stream(stream)) as chunks:
            async for chunk in chunks:
                text = chunk.choices[0].delta.content or ""
                if text:
                    state.full_response += text
                    yield _sse({"text": text})
    except Exception as e:
        state.trace["error"] = type(e).__name__
        print(f"[chat] qwen-vl-max error type={type(e).__name__}", flush=True)
        if state.crisis:
            yield _crisis_resource_event(state)
        yield _sse({"error": _upstream_error_message(e)})
        return

    image_summary = state.full_response
    if state.crisis:
        yield _crisis_resource_event(state)
    if state.full_response.strip():
        await _save_response(ctx, state)
        if not state.crisis and image_summary.strip():
            state.billable = True
    # 摘要直接复用 VL 本轮已生成的回复，不再额外调用任何模型；写失败绝不能影响已返回的 SSE。
    try:
        await set_message_image_summary(
            ctx.user, ctx.conversation_id, ctx.uploaded_image_path, image_summary,
        )
    except Exception as e:
        print(f"[chat] image summary write failed type={type(e).__name__}", flush=True)
    yield _sse({"done": True})


async def stream_pending(ctx: ChatContext, state: ChatState, pending: dict):
    """有等待补全参数的 pending intent：补全则执行，否则继续追问。"""
    await _ensure_active_conversation(ctx)
    if pending.get("intent") == "generate_image" and re.match(
        r"^(?:算了|取消|不用了|不画了|不要了|停止|别画了)[吧了。！!\s]*$", ctx.message.strip(),
    ):
        clear_pending(ctx.state_key)
        state.full_response = "好，已取消。"
        await _save_response(ctx, state)
        yield _sse({"text": state.full_response})
        yield _sse({"done": True})
        return
    filled = fill_param(pending, ctx.message)
    if not filled["missing"]:
        # 参数补全，执行
        clear_pending(ctx.state_key)
        if filled["intent"] == "generate_image":
            async for event in stream_generated_image(ctx, state, ctx.message.strip()):
                yield event
            return
        state.trace["intent"] = filled["intent"]
        state.trace["tool"] = filled["intent"]
        async with trace_span(ctx.user, "tool_call", filled["intent"], payload={"via": "pending_fill"}):
            await _ensure_active_conversation(ctx)
            result = await asyncio.to_thread(execute_intent, filled["intent"], filled["params"])
        if isinstance(result, dict) and result.get("type") == "card":
            # 卡片数据走专门 SSE 事件
            yield _sse({"card": result})
            if result.get("subtype") == "travel_plan":
                playback = build_playback(result)
                yield _sse({"text": playback})
                state.full_response = playback
            else:
                # 数据库存简化纯文本，历史回放友好
                state.full_response = _summarize_card_for_history(result)
        else:
            state.full_response = result
            yield _sse({"text": result})
        await _save_response(ctx, state)
        state.billable = _tool_billable(filled["intent"], result)
        yield _sse({"done": True})
    else:
        # 还缺参数，继续追问
        set_pending(ctx.state_key, filled)
        question = ask_missing(filled["missing"][0])
        state.full_response = question
        yield _sse({"text": question})
        await _save_response(ctx, state)
        yield _sse({"done": True})


def recognize_intent_with_fallback(message: str, history: list[dict]) -> dict:
    """意图识别（JSON mode）+ 正则兜底搜索措辞。同步，调用方负责 to_thread。"""
    intent_result = recognize_intent(client, message, history)
    if intent_result.get("intent") == "generate_image" and image_generation_discussion(message):
        intent_result = {"intent": None}
    # LLM 意图路由偶尔把"我查一下 XX"误判为 null——正则补一刀。
    # 只兜明确的"查/搜"措辞；裸"看/找"容易把观察、情绪表达误判成联网搜索。
    # ("你有没有时间"之类靠 LLM prompt 例子识别，不在 regex 里硬抠)
    if intent_result["intent"] is None:
        _query = None
        for _pat in [
            r"(?:帮我?|我)\s*(?:查|搜)(?:一下|下|查|搜|个)?\s*(\S.+)",
            r"^(?:查一下|查查|查下|搜一下|搜搜|搜下)\s*(\S.+)",
        ]:
            _m = re.search(_pat, message)
            if not _m:
                continue
            cand = _m.group(1)
            # 剥掉残余的语气补语（"一下吧"、"下" 等被正则吃剩的尾巴）
            cand = re.sub(r"^(?:一下|下|看|看看|个)\s*", "", cand)
            cand = cand.strip("，。?？.! 吧啊呢哦呀")
            if len(cand) >= 2 and not re.match(r"^https?://", cand):
                _query = cand
                break
        if _query:
            intent_result = {"intent": "web_search", "params": {"query": _query}, "missing": []}
    print(
        f"[意图识别] chars={len(message)}, intent={intent_result.get('intent')}, "
        f"missing={intent_result.get('missing')}"
    )
    return intent_result


async def stream_intent(ctx: ChatContext, state: ChatState, intent_result: dict):
    """意图明确：参数完整直接执行，缺参数则存 pending 追问。"""
    await _ensure_active_conversation(ctx)
    if intent_result["intent"] == "generate_image":
        if intent_result.get("missing"):
            set_pending(ctx.state_key, {"intent": "generate_image", "params": {}, "missing": ["prompt"]})
            state.full_response = ask_missing("prompt")
            await _save_response(ctx, state)
            yield _sse({"text": state.full_response})
            yield _sse({"done": True})
        else:
            # 分类器的短 JSON 不能替换或截断用户完整的画面要求。
            clear_pending(ctx.state_key)
            async for event in stream_generated_image(ctx, state, ctx.message.strip()):
                yield event
        return
    if not intent_result["missing"]:
        # 意图明确，参数完整，直接执行
        state.trace["tool"] = intent_result["intent"]
        async with trace_span(ctx.user, "tool_call", intent_result["intent"], payload={"via": "direct"}):
            await _ensure_active_conversation(ctx)
            result = await asyncio.to_thread(execute_intent, intent_result["intent"], intent_result["params"])
        if isinstance(result, dict) and result.get("type") == "card":
            # 卡片数据走专门 SSE 事件
            yield _sse({"card": result})
            # 旅行规划卡：除了右侧卡片，再把要点完整口播 + 追问优化方向
            if result.get("subtype") == "travel_plan":
                playback = build_playback(result)
                yield _sse({"text": playback})
                state.full_response = playback
            else:
                state.full_response = _summarize_card_for_history(result)
        else:
            state.full_response = result
            yield _sse({"text": result})
        tool_billable = _tool_billable(intent_result["intent"], result)
    else:
        # 意图明确，但缺参数，存 pending 并追问
        set_pending(ctx.state_key, intent_result)
        question = ask_missing(intent_result["missing"][0])
        state.full_response = question
        yield _sse({"text": question})
        tool_billable = False
    await _save_response(ctx, state)
    state.billable = tool_billable
    yield _sse({"done": True})


async def stream_normal(ctx: ChatContext, state: ChatState):
    """普通对话，走 Chloe（路由决定使用哪个模型槽）+ 后台画像提取/匹配检测。"""
    _slot = choose_model(ctx.user, ctx.user_content, "normal", len(ctx.history))
    state.trace["model"] = _slot
    _use_light = (_slot == "light")
    # max_tokens 统一给 700：_create_stream_with_fallback 会在轻量槽失败时
    # 自动切主力大脑，但 max_tokens 是事先传入的参数，给小了 fallback 后
    # 主脑也被锁在小上限，对话被砍在半截。给统一上限消掉这个漏洞。
    # 轻量槽自己回短句时不会用满，没浪费。
    _max_tok = 700
    _temp = 0.9 if _use_light else 1.05
    _freq_pen = 0.3 if _use_light else 0.4
    _pres_pen = 0.2 if _use_light else 0.4

    _finish_reason = None
    try:
        stream, _actually_qwen = await asyncio.to_thread(
            _create_stream_with_fallback,
            _use_light,
            [{"role": "system", "content": state.sys_prompt_final}] + ctx.messages,
            max_tokens=_max_tok,
            temperature=_temp,
            frequency_penalty=_freq_pen,
            presence_penalty=_pres_pen,
        )
        async with aclosing(_iter_sync_stream(stream)) as chunks:
            async for chunk in chunks:
                text = chunk.choices[0].delta.content or ""
                if text:
                    state.full_response += text
                    yield _sse({"text": text})
                fr = chunk.choices[0].finish_reason
                if fr:
                    _finish_reason = fr
    except Exception as e:
        state.trace["error"] = type(e).__name__
        print(f"[chat] normal stream error type={type(e).__name__}", flush=True)
        if state.crisis:
            yield _crisis_resource_event(state)
        yield _sse({"error": _upstream_error_message(e)})
        return
    if _finish_reason == "length":
        # 撞到 max_tokens 上限 —— 用户会看到回答被砍在半句话
        print(f"[chat] truncated: model={'light' if _actually_qwen else 'main'} "
              f"max_tokens={_max_tok} chars={len(state.full_response)}", flush=True)

    model_response = state.full_response
    if state.crisis:
        yield _crisis_resource_event(state)
    if state.full_response.strip():
        await _save_response(ctx, state)
        if not state.crisis and model_response.strip():
            state.billable = True
    yield _sse({"done": True})

    try:
        # These follow-up tasks cannot change the already delivered answer.
        if not _actually_qwen:
            token_budget.add(ctx.user, len(state.full_response) // 2)
        if ctx.message_count > 0 and ctx.message_count % 5 == 0:
            all_msgs = await get_messages(ctx.user, limit=60, conversation_id=ctx.conversation_id)
            _track_background_task(extract_and_update(
                client, ctx.user, all_msgs, conversation_id=ctx.conversation_id,
                expected_revision=ctx.memory_revision,
            ))
        if ctx.conversation_id is None:
            _track_background_task(
                detect_matches_and_save(
                    client,
                    ctx.user,
                    ctx.user_content,
                    ctx.history + [{"role": "user", "content": ctx.user_content}],
                    message_count=ctx.message_count,
                )
            )
    except Exception as e:
        print(f"[chat] post-delivery follow-up failed type={type(e).__name__}", flush=True)


# ────────────────────────── 4. 编排 ──────────────────────────

async def run_chat(
    ctx: ChatContext, *, reserved: bool = False, crisis: bool | None = None,
    tracker: ChatRunTracker | None = None,
):
    """Dispatch one chat turn and settle a reservation against actual delivery."""
    crisis = detect_crisis(ctx.message) if crisis is None else crisis
    state = ChatState(trace={
        "mode": None,
        "intent": None,
        "model": None,
        "has_image": ctx.has_image,
        "tool": None,
        "message_count": ctx.message_count,
        "conversation_id": ctx.conversation_id,
        "agent_id": ctx.agent.get("id"),
        "crisis": crisis,
    })
    state.crisis = crisis
    try:
        if tracker is not None:
            tracker.started = True
        if crisis:
            # Keep existing pending parameters and mode untouched. A crisis turn
            # always reaches a support reply before ordinary chat routing.
            await _ensure_active_conversation(ctx)
            state.trace["mode"] = "crisis"
            state.sys_prompt_final = _final_system_prompt(ctx.system_prompt, crisis=True)
            if ctx.has_image:
                async for event in stream_image(ctx, state):
                    yield event
            else:
                async for event in stream_normal(ctx, state):
                    yield event
            return
        if ctx.request_mode == "image_edit" and ctx.reference_sources_submitted:
            # Acknowledge the durable paths even if the provider is busy or
            # fails, so retries can reuse uploads instead of resending bytes.
            yield _sse({"type": "reference_images", "reference_image_paths": ctx.reference_image_paths})
        # 用户明确请求生成图片时，优先执行；避免被情绪陪聊或旧 pending 参数吞掉。
        image_intent = explicit_image_intent(ctx.message) if not ctx.has_image else None
        if ctx.request_mode in {"image", "image_edit"}:
            clear_pending(ctx.state_key)
            state.trace["mode"] = ctx.request_mode
            async for event in stream_generated_image(ctx, state, ctx.message.strip()):
                yield event
            return
        if not ctx.has_image and image_edit_requires_reference(ctx.message):
            clear_pending(ctx.state_key)
            state.trace["mode"] = "image_edit_selection"
            state.full_response = "请先点击要修改的图片上的「以此图修改」，再输入修改要求。我会参考你选中的那张图生成新版本，并保留原图。"
            await _save_response(ctx, state)
            yield _sse({"text": state.full_response})
            yield _sse({"done": True})
            return
        if image_intent:
            state.trace["mode"] = "image"
            async for event in stream_intent(ctx, state, image_intent):
                yield event
            return
        image_pending = get_pending(ctx.state_key)
        if not ctx.has_image and image_pending and image_pending.get("intent") == "generate_image":
            if re.match(r"^(?:算了|取消|不用了|不画了|不要了|停止|别画了)[吧了。！!\s]*$", ctx.message.strip()):
                async for event in stream_pending(ctx, state, image_pending):
                    yield event
                return
            # 新的工具请求优先于旧的画面追问，例如“先查一下天气”。
            replacement = await asyncio.to_thread(recognize_intent_with_fallback, ctx.message, ctx.history)
            if replacement.get("intent") and replacement["intent"] != "generate_image":
                clear_pending(ctx.state_key)
                async for event in stream_intent(ctx, state, replacement):
                    yield event
                return
            if (image_generation_discussion(ctx.message)
                or ctx.message.strip("。！! ") in {"谢谢", "好的", "好", "嗯"}
                or re.match(r"^(?:先聊|聊点|换个话题|先不|算了|取消)", ctx.message.strip())
                or (not replacement.get("intent") and re.search(r"如何|怎么样|为什么|多少钱|几点|几号|[吗么？?]", ctx.message))):
                clear_pending(ctx.state_key)
            else:
                async for event in stream_pending(ctx, state, image_pending):
                    yield event
                return
        # ── 0. 模式判定（双模式系统 P1.5）──
        # detect_mode 内部跑同步 LLM 调用，必须扔到线程池，否则会阻塞 event loop
        mode = await asyncio.to_thread(detect_mode, client, ctx.state_key, ctx.message, ctx.history)
        await _ensure_active_conversation(ctx)
        state.trace["mode"] = mode
        state.sys_prompt_final = _final_system_prompt(
            apply_mode_prompt(_without_safety(ctx.system_prompt), mode),
            trailing_system=_has_trailing_system(ctx),
        )

        if mode == "mirror":
            async for s in stream_mirror(ctx, state):
                yield s
            return

        # ── 朋友模式：保留现有完整逻辑 ──
        if ctx.has_image:
            async for s in stream_image(ctx, state):
                yield s
            return

        # ── 1. 检查是否有等待补全参数的 pending intent ──
        pending = get_pending(ctx.state_key)
        if pending:
            async for s in stream_pending(ctx, state, pending):
                yield s
            return

        # ── 2. 意图识别（JSON mode，带上下文）──
        intent_result = await asyncio.to_thread(recognize_intent_with_fallback, ctx.message, ctx.history)
        await _ensure_active_conversation(ctx)
        state.trace["intent"] = intent_result.get("intent")
        if intent_result["intent"] is not None:
            async for s in stream_intent(ctx, state, intent_result):
                yield s
            return

        # ── 3. 普通对话 ──
        async for s in stream_normal(ctx, state):
            yield s

    except ResourceNotFound:
        if not crisis:
            clear_pending(ctx.state_key)
            from mode_switcher import clear_user_mode
            clear_user_mode(ctx.state_key)
        if crisis and not state.crisis_resource_sent:
            yield _crisis_resource_event(state)
        yield _sse({"error": "会话已删除或不可用"})
        state.trace["error"] = "ResourceNotFound"
    except Exception as e:
        if crisis and not state.crisis_resource_sent:
            yield _crisis_resource_event(state)
        yield _sse({"error": _upstream_error_message(e)})
        state.trace["error"] = type(e).__name__
    finally:
        with anyio.CancelScope(shield=True):
            if reserved and not state.billable:
                try:
                    await refund_strawberries(ctx.user, STRAWBERRY_COST_PER_REPLY)
                except Exception as e:
                    state.trace["refund_failed"] = True
                    print(f"[chat] refund failed type={type(e).__name__}", flush=True)
            # ── 写 chat 汇总事件 ──
            state.trace["resp_chars"] = len(state.full_response)
            try:
                await log_event(ctx.user, "chat", payload=state.trace,
                                success=("error" not in state.trace))
            except Exception as e:
                print(f"[chat] trace write failed type={type(e).__name__}", flush=True)
