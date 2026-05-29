# -*- coding: utf-8 -*-
import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth_dep import get_current_user
from conversation_matcher import detect_and_save as detect_matches_and_save
from database import (count_messages, deduct_strawberry, get_messages, get_or_create_user,
                      get_strawberry_balance, save_message)
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
from tools.travel_plan import travel_plan as travel_plan_query
from tools.web_search import web_search
from tools.wechat_send import send_wechat_message, start_wechat_video_call, start_wechat_voice_call
from trace import log_event, trace_span
from utils.media import _save_uploaded_image

router = APIRouter()


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


class ChatRequest(BaseModel):
    message: str
    image_base64: str | None = None




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


@router.post("/chat")
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
