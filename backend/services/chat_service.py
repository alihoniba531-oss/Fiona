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
import os
import re
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException

from avatar_state import AvatarStage, build_tone_description, extract_tone_profile, get_stage
from conversation_matcher import detect_and_save as detect_matches_and_save
from database import (count_messages, deduct_strawberry, get_messages, get_or_create_user,
                      get_profile, get_strawberry_balance, save_message)
from extractor import extract_and_update
from intent_router import ask_missing, clear_pending, fill_param, get_pending, recognize_intent, set_pending
from llm import QWEN_CLIENT, _create_stream_with_fallback, client
from mode_switcher import apply_mode_prompt, detect_mode, get_user_mode
from model_router import choose_model, token_budget
from persona import build_system_prompt
from tools.fetch_card import fetch_card as _fetch_card_impl
from tools.hot_topics import hot_topics
from tools.open_app import open_application
from tools.reminder import set_reminder
from tools.route import route as route_query
from tools.system_tools import get_datetime, open_url, take_screenshot, write_clipboard
from tools.travel_plan import build_playback
from tools.travel_plan import travel_plan as travel_plan_query
from tools.web_search import web_search
from tools.wechat_send import send_wechat_message, start_wechat_video_call, start_wechat_voice_call
from trace import log_event, trace_span
from utils.media import _save_uploaded_image, delete_uploaded_files


_STREAM_END = object()
_background_tasks: set[asyncio.Task] = set()


async def _iter_sync_stream(stream):
    """逐块在线程池推进同步 OpenAI Stream，避免阻塞 asyncio 事件循环。"""
    try:
        iterator = iter(stream)
        while True:
            chunk = await asyncio.to_thread(next, iterator, _STREAM_END)
            if chunk is _STREAM_END:
                break
            yield chunk
    finally:
        try:
            close = getattr(stream, "close", None)
            if callable(close):
                await asyncio.to_thread(close)
        except Exception as e:
            # 关闭失败不能覆盖原始流异常或改变 SSE 输出。
            print(f"[chat] stream close error: {type(e).__name__}: {e}", flush=True)


def _track_background_task(coro) -> asyncio.Task:
    """保留后台任务的强引用，完成后自动移除。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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
    print(f"[硬词检测] message={message!r}, detected={detected_hard}")
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


@dataclass
class ChatState:
    """一次 chat 流式过程中的可变状态：累计回复 + 埋点 + 当前模式 prompt。"""
    trace: dict
    full_response: str = ""
    sys_prompt_final: str = ""
    response_saved: bool = False


async def build_context(req, user: str) -> ChatContext:
    """预检装配（不含余额检查 —— 那个要在 handler 早返回）。
    req 需有 .message 和 .image_base64。"""
    has_image = bool(req.image_base64)

    history = await get_messages(user, limit=60)
    message_count = await count_messages(user)  # 真实总数，不能用 len(history)（封顶 60 永远进不了 EMBODIED）

    # 图片处理：保存到 uploads/，拿到相对 URL
    image_path = None
    validated_image = None
    if has_image:
        image_path, validated_image = _save_uploaded_image(req.image_base64)

    user_content = req.message.strip() or "[发了一张图片]"

    # 黏附心信号（用 history 算，此时 history 还不含当前消息——正确）
    hours_since_last = _compute_hours_since_last_user(history)
    length_drop = _compute_length_drop(history, user_content)

    saved = await save_message(user, "user", user_content, image_path)
    if not saved:
        if image_path:
            delete_uploaded_files([image_path])
        raise HTTPException(status_code=409, detail="账号已失效")

    # 加载画像（含 special_dates），传给 persona 做日期感知
    user_profile = await get_profile(user)

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
    )
    system_prompt += build_hard_word_appendix(req.message)

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_content})

    # qwen 对"播报/朗读/念出来"这类词的训练倾向太强（自动解释 TTS 机制、教对方开手机朗读），
    # 顶部 persona 禁令压不住。在 user 消息后贴一条强约束 system，离生成位置最近、attention 最大。
    if re.search(r"(播报|朗读|口播|念出来|读出来|念一[下遍]|读一[下遍]|大声[念读])", req.message or ""):
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
    )


# ────────────────────────── 3. 五条流式分支 ──────────────────────────

async def stream_mirror(ctx: ChatContext, state: ChatState):
    """镜子模式：跳过意图识别 + 工具调用，直走简化 Persona。"""
    # 只有用户明确手动切镜子（说"别给建议"之类）才清 pending；
    # 自动判定（连续短情绪 / LLM 判定发泄）可能误伤——用户也许只是在补工具参数
    _mode_state = get_user_mode(ctx.user)
    _trigger = (_mode_state.get("last_trigger") or "")
    if _trigger.startswith("manual"):
        clear_pending(ctx.user)
    _slot = choose_model(ctx.user, ctx.user_content, "mirror")
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
        state.trace["error"] = str(e)[:200]
        print(f"[chat] mirror stream error: {type(e).__name__}: {e}", flush=True)
        yield _sse({"error": str(e)})
        return
    await save_message(ctx.user, "assistant", state.full_response)
    state.response_saved = True
    yield _sse({"done": True})
    if not _actually_qwen:
        token_budget.add(ctx.user, len(state.full_response) // 2)


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

    vl_system = (
        state.sys_prompt_final
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
            {"type": "text", "text": ctx.user_content},
        ]},
    ]

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
        state.full_response = "图我接到了，但看的时候出了点意外，再发一次试试？"
        yield _sse({"text": state.full_response})
        print(f"[chat] qwen-vl-max error: {type(e).__name__}: {e}", flush=True)

    await save_message(ctx.user, "assistant", state.full_response)
    state.response_saved = True
    yield _sse({"done": True})


async def stream_pending(ctx: ChatContext, state: ChatState, pending: dict):
    """有等待补全参数的 pending intent：补全则执行，否则继续追问。"""
    filled = fill_param(pending, ctx.message)
    if not filled["missing"]:
        # 参数补全，执行
        clear_pending(ctx.user)
        state.trace["intent"] = filled["intent"]
        state.trace["tool"] = filled["intent"]
        async with trace_span(ctx.user, "tool_call", filled["intent"], payload={"via": "pending_fill"}):
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
        await save_message(ctx.user, "assistant", state.full_response)
        state.response_saved = True
        yield _sse({"done": True})
    else:
        # 还缺参数，继续追问
        set_pending(ctx.user, filled)
        question = ask_missing(filled["missing"][0])
        state.full_response = question
        yield _sse({"text": question})
        await save_message(ctx.user, "assistant", state.full_response)
        state.response_saved = True
        yield _sse({"done": True})


def recognize_intent_with_fallback(message: str, history: list[dict]) -> dict:
    """意图识别（JSON mode）+ 正则兜底搜索措辞。同步，调用方负责 to_thread。"""
    intent_result = recognize_intent(client, message, history)
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
    print(f"[意图识别] message={message[:60]!r}, intent={intent_result.get('intent')}, missing={intent_result.get('missing')}")
    return intent_result


async def stream_intent(ctx: ChatContext, state: ChatState, intent_result: dict):
    """意图明确：参数完整直接执行，缺参数则存 pending 追问。"""
    if not intent_result["missing"]:
        # 意图明确，参数完整，直接执行
        state.trace["tool"] = intent_result["intent"]
        async with trace_span(ctx.user, "tool_call", intent_result["intent"], payload={"via": "direct"}):
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
    else:
        # 意图明确，但缺参数，存 pending 并追问
        set_pending(ctx.user, intent_result)
        question = ask_missing(intent_result["missing"][0])
        state.full_response = question
        yield _sse({"text": question})
    await save_message(ctx.user, "assistant", state.full_response)
    state.response_saved = True
    yield _sse({"done": True})


async def stream_normal(ctx: ChatContext, state: ChatState):
    """普通对话，走 Chloe（路由决定使用哪个模型槽）+ 后台画像提取/匹配检测。"""
    _slot = choose_model(ctx.user, ctx.user_content, "normal")
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
        state.trace["error"] = str(e)[:200]
        print(f"[chat] normal stream error: {type(e).__name__}: {e}", flush=True)
        yield _sse({"error": str(e)})
        return
    if _finish_reason == "length":
        # 撞到 max_tokens 上限 —— 用户会看到回答被砍在半句话
        print(f"[chat] truncated: user={ctx.user} model={'light' if _actually_qwen else 'main'} "
              f"max_tokens={_max_tok} chars={len(state.full_response)}", flush=True)

    await save_message(ctx.user, "assistant", state.full_response)
    state.response_saved = True
    yield _sse({"done": True})

    # 主力大脑实际使用时计入预算（含轻量槽失败回退的情况）
    if not _actually_qwen:
        token_budget.add(ctx.user, len(state.full_response) // 2)

    # ── 每 5 轮后台静默提取画像（不阻塞返回）──
    if ctx.message_count > 0 and ctx.message_count % 5 == 0:
        all_msgs = await get_messages(ctx.user, limit=60)
        _track_background_task(extract_and_update(client, ctx.user, all_msgs))

    # ── 对话内匹配检测（后台异步，不阻塞返回）──
    # 只在朋友模式的普通对话流跑（这里已经过了 mirror 分支 + 工具分支）
    _track_background_task(
        detect_matches_and_save(
            client,
            ctx.user,
            ctx.user_content,
            ctx.history + [{"role": "user", "content": ctx.user_content}],
            message_count=ctx.message_count,
        )
    )


# ────────────────────────── 4. 编排 ──────────────────────────

async def run_chat(ctx: ChatContext):
    """按模式/图片/pending/意图/普通的顺序派发到对应分支，统一收尾扣费 + 埋点。"""
    state = ChatState(trace={
        "mode": None,
        "intent": None,
        "model": None,
        "has_image": ctx.has_image,
        "tool": None,
        "message_count": ctx.message_count,
    })
    try:
        # ── 0. 模式判定（双模式系统 P1.5）──
        # detect_mode 内部跑同步 LLM 调用，必须扔到线程池，否则会阻塞 event loop
        mode = await asyncio.to_thread(detect_mode, client, ctx.user, ctx.message, ctx.history)
        state.trace["mode"] = mode
        state.sys_prompt_final = apply_mode_prompt(ctx.system_prompt, mode)

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
        pending = get_pending(ctx.user)
        if pending:
            async for s in stream_pending(ctx, state, pending):
                yield s
            return

        # ── 2. 意图识别（JSON mode，带上下文）──
        intent_result = await asyncio.to_thread(recognize_intent_with_fallback, ctx.message, ctx.history)
        state.trace["intent"] = intent_result.get("intent")
        if intent_result["intent"] is not None:
            async for s in stream_intent(ctx, state, intent_result):
                yield s
            return

        # ── 3. 普通对话 ──
        async for s in stream_normal(ctx, state):
            yield s

    except Exception as e:
        yield _sse({"error": str(e)})
        state.trace["error"] = str(e)[:200]
    finally:
        # 只有回复确实落库后才扣草莓（DEV 模式跳过）
        DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
        if state.full_response and state.response_saved and not DEV_MODE:
            await deduct_strawberry(ctx.user, 10)
        # ── 写 chat 汇总事件 ──
        state.trace["resp_chars"] = len(state.full_response)
        await log_event(ctx.user, "chat", payload=state.trace,
                        success=("error" not in state.trace))
