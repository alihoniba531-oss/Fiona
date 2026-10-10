"""Bounded Claude BYOK orchestration, isolated from the legacy chat paths."""
from __future__ import annotations

import asyncio
import base64
from contextlib import aclosing
from copy import deepcopy
from functools import partial
from io import BytesIO
import json
import math
import os
import time
from urllib.parse import urlsplit

import anyio
from anthropic._utils._json import openapi_model_dump
from PIL import Image

from byok.client import ReplyStreamControl, open_agent_stream
from byok.errors import ByokTimeoutError, EmptyReplyError, RefusalError, error_category, error_message
from byok.providers import provider_label
from services.image_tool import anthropic_image_tool, validate_image_tool_call
from utils.beijing_time import beijing_now
from utils.city_name import normalize_city
from utils.safe_http import UnsafeUrlError, validate_public_http_link


_now = time.monotonic
_SLOT_WAIT_SECONDS = 10.0
_TOOL_HEARTBEAT_SECONDS = 10.0
_CLIENT_INTENTS = {"get_weather": "weather", "plan_travel": "travel_plan", "plan_route": "route", "get_hot_topics": "hot_topics"}
_TOOL_LIMIT_RESULT = "本轮工具调用次数已用完，请直接回答主人"
_CITY_PRIVACY_RESULT = "主人没有说过这个城市，请先问主人想查哪个城市"
_IMAGE_LIMIT_RESULT = "本轮已生成过一张图，请直接回答；如需更多请让主人再说一次"
_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
_CLAUDE_IMAGE_MAX_BYTES = 3_500_000
_CLAUDE_IMAGE_MAX_SIDE = 2000
_CITY_ADMIN_SUFFIXES = ("特别行政区", "自治州", "市", "省", "区", "县", "州", "盟")


def _tool(name, description, properties, required):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": required}}


CLAUDE_CLIENT_TOOLS = [
    _tool("get_weather", "查询主人亲口说过的城市的天气，没说过城市时先问主人。", {"city": {"type": "string"}}, ["city"]),
    _tool("plan_travel", "按完整旅行需求规划旅行。", {"query": {"type": "string", "description": "旅行需求的完整描述"}}, ["query"]),
    _tool("plan_route", "查询两地之间的路线。", {"origin": {"type": "string"}, "destination": {"type": "string"}}, ["origin", "destination"]),
    _tool("get_hot_topics", "查询指定来源的热榜。", {"source": {"type": "string", "enum": ["微博", "知乎", "抖音", "B站", "头条"]}}, ["source"]),
    anthropic_image_tool(),
]


def agent_total_seconds() -> float:
    try:
        value = float(os.getenv("FIONA_CLAUDE_AGENT_TOTAL_SECONDS", "240"))
    except (TypeError, ValueError):
        return 240.0
    return value if math.isfinite(value) and 60 <= value <= 290 else 240.0


def _value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _block_dict(block):
    if isinstance(block, dict):
        return deepcopy(block)
    if hasattr(block, "model_dump"):
        # Match SDK prepare_request_data's BaseModel branch. Explicit nulls
        # remain present, while unset and API-excluded fields stay excluded.
        return openapi_model_dump(block)
    return deepcopy(vars(block))


def _assistant_content(final, *, trim_fallback=True):
    content = list(_value(final, "content", []) or [])
    fallback = max((index for index, block in enumerate(content) if _value(block, "type") == "fallback"), default=-1) if trim_fallback else -1
    return [_block_dict(block) for block in content[fallback + 1:]]


def _claude_image_source(data_uri):
    """Prepare only the outbound copy; Pillow work runs outside the event loop."""
    _, encoded = data_uri.split(",", 1)
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(BytesIO(raw)) as source:
        source.load()
        mime = Image.MIME[source.format]
        if len(raw) <= _CLAUDE_IMAGE_MAX_BYTES and max(source.size) <= _CLAUDE_IMAGE_MAX_SIDE:
            return {"type": "base64", "media_type": mime, "data": encoded}
        transparent_png = source.format == "PNG" and ("A" in source.getbands() or "transparency" in source.info)
        image = source.convert("RGBA" if transparent_png else "RGB")
    image.thumbnail((_CLAUDE_IMAGE_MAX_SIDE, _CLAUDE_IMAGE_MAX_SIDE), Image.Resampling.LANCZOS)
    encoding = "PNG" if transparent_png else "JPEG"
    while True:
        output = BytesIO()
        image.save(output, format=encoding, **({"quality": 85} if encoding == "JPEG" else {}))
        raw = output.getvalue()
        if len(raw) <= _CLAUDE_IMAGE_MAX_BYTES:
            break
        width, height = image.size
        image = image.resize((max(1, int(width * .85)), max(1, int(height * .85))), Image.Resampling.LANCZOS)
    return {"type": "base64", "media_type": "image/" + encoding.lower(), "data": base64.b64encode(raw).decode("ascii")}


async def _agent_messages(ctx, state):
    messages = deepcopy(ctx.messages)
    current = max((index for index, item in enumerate(messages) if item["role"] == "user"), default=-1)
    now = beijing_now()
    weekday = "一二三四五六日"[now.weekday()]
    blocks = [{"type": "text", "text": f"（当前北京时间：{now.year}年{now.month}月{now.day}日 周{weekday} {now:%H:%M}）"}]
    if ctx.has_image:
        image = await asyncio.to_thread(_claude_image_source, ctx.image_base64)
        blocks.append({"type": "image", "source": image})
    blocks.append({"type": "text", "text": ctx.user_content or "[发了一张图片]"})
    if current >= 0:
        messages[current] = {"role": "user", "content": blocks}
    else:
        messages.append({"role": "user", "content": blocks})
    return [{"role": "system", "content": state.sys_prompt_final}] + messages


def _city_is_allowed(ctx, city):
    # Only raw user turns participate. Memories and generated image summaries
    # never supply permission, even if included in the model's prompt.
    if not isinstance(city, str) or len(city.strip()) < 2:
        return ""
    candidates = []
    for spelling in (city.strip(), normalize_city(city)):
        if len(spelling) >= 2 and spelling not in candidates:
            candidates.append(spelling)
        for suffix in _CITY_ADMIN_SUFFIXES:
            if spelling.endswith(suffix):
                shortened = spelling[:-len(suffix)]
                if len(shortened) >= 2 and shortened not in candidates:
                    candidates.append(shortened)
                break
    recent = [row.get("content", "") for row in ctx.history if row.get("role") == "user"][-3:]
    for raw in [ctx.user_content, *recent]:
        if not isinstance(raw, str):
            continue
        for text in (raw, normalize_city(raw)):
            for spelling in candidates:
                if spelling in text:
                    matched = normalize_city(spelling)
                    if matched:
                        return matched
    return ""


def _tool_result_text(name, card):
    if not isinstance(card, dict):
        return card if isinstance(card, str) else "工具暂时没有返回可用结果"
    if card.get("error"):
        return str(card.get("message") or card.get("reason") or "\n".join(str(point) for point in (card.get("points") or [])) or "工具暂时不可用")
    if name == "get_weather":
        weather = card.get("weather") or {}
        lines = [str(weather.get("location") or card.get("source") or "天气")]
        for forecast in (weather.get("forecast") or [])[:5]:
            if not isinstance(forecast, dict):
                continue
            conditions = "/".join(str(forecast[key]) for key in ("dayWeather", "nightWeather", "condition") if forecast.get(key))
            temperatures = "~".join(str(forecast[key]) for key in ("low", "high") if forecast.get(key) is not None)
            wind = " ".join(str(forecast[key]) for key in ("dayWind", "nightWind", "wind", "dayWindPower", "nightWindPower") if forecast.get(key))
            lines.append(" ".join(value for value in (str(forecast.get("date") or forecast.get("day") or ""), conditions,
                                                     temperatures + "℃" if temperatures else "", wind) if value))
        if len(lines) == 1 and weather.get("currentTemp") is not None:
            lines.append(f"{weather.get('condition', '')} {weather['currentTemp']}℃ {weather.get('wind', '')}".strip())
        return "\n".join(lines)
    if name == "get_hot_topics":
        items = card.get("items") or []
        titles = [str(item.get("title", "")) for item in items[:10] if isinstance(item, dict) and item.get("title")]
        return "\n".join(titles or [str(point) for point in (card.get("points") or [])[:10]]) or "暂时没有热榜条目"
    parts = [str(card.get("source") or ""), *[str(point) for point in (card.get("points") or [])[:15]]]
    if name == "plan_travel":
        parts.extend(str(source.get("title", "")) for source in (card.get("sources") or []) if isinstance(source, dict))
    return "\n".join(part for part in parts if part) or "工具已返回结果"


def _collect_sources(content, sources):
    seen = {source["url"] for source in sources}
    for block in content:
        kind = _value(block, "type")
        if kind == "web_search_tool_result":
            results = _value(block, "content", [])
            if not isinstance(results, list):
                continue
        elif kind == "web_fetch_tool_result":
            fetched = _value(block, "content")
            # Anthropic 1.12.1 BetaWebFetchToolResultBlock wraps a
            # BetaWebFetchBlock (type=web_fetch_result), whose document has title.
            if _value(fetched, "type") != "web_fetch_result":
                continue
            results = [{"url": _value(fetched, "url"), "title": _value(_value(fetched, "content"), "title", "")}]
        else:
            continue
        for result in results:
            try:
                url = validate_public_http_link(_value(result, "url"))
            except (UnsafeUrlError, TypeError, ValueError):
                continue
            if url in seen or len(sources) >= 5:
                continue
            title = _value(result, "title", "")
            sources.append({"title": title[:80] if isinstance(title, str) else "", "url": url,
                            "site_name": urlsplit(url).hostname or ""})
            seen.add(url)


def _add_usage(trace, final):
    usage = _value(final, "usage")
    for name in _USAGE_FIELDS:
        value = _value(usage, name)
        if isinstance(value, int):
            trace["agent_usage"][name] = trace["agent_usage"].get(name, 0) + value
    server = _value(usage, "server_tool_use")
    for name in ("web_search_requests", "web_fetch_requests"):
        value = _value(server, name, 0)
        trace[name] += value if isinstance(value, int) else 0


class _AgentBudgetError(ByokTimeoutError):
    pass


async def _wait_task(task, deadline, heartbeat, interval):
    try:
        while not task.done():
            remaining = deadline - _now()
            if remaining <= 0:
                raise _AgentBudgetError()
            done, _ = await asyncio.wait({task}, timeout=min(interval, remaining))
            if not done:
                if _now() >= deadline:
                    raise _AgentBudgetError()
                yield heartbeat
    finally:
        if not task.done():
            task.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(task, return_exceptions=True)


async def stream_claude_agent(ctx, state):
    """Route a Claude turn and stream every step through one platform lifecycle."""
    from services import chat_service as chat

    deadline = _now() + agent_total_seconds()
    user_locked = False

    def release_user_lock():
        nonlocal user_locked
        if user_locked:
            with chat._BYOK_POOL_LOCK:
                chat._BYOK_USERS.discard(ctx.user)
            user_locked = False

    try:
        with chat._BYOK_POOL_LOCK:
            if ctx.user in chat._BYOK_USERS:
                raise chat._ByokBusyError("你的模型正在回复上一条消息，请稍候")
            chat._BYOK_USERS.add(ctx.user)
            user_locked = True
        async with aclosing(_stream_claude_agent(ctx, state, deadline, release_user_lock)) as reply:
            async for event in reply:
                yield event
    except Exception as exc:
        if state.trace.get("mode") == "mirror" or not isinstance(exc, (_AgentBudgetError, chat._ByokBusyError)):
            # Mirror delegates its whole legacy lifecycle, including platform
            # persistence errors. Deleted conversations likewise retain the
            # run_chat resource handler and its state cleanup.
            raise
        # Known admission/budget failures retain their fixed public messages;
        # platform preparation and persistence errors belong to run_chat.
        state.trace.update(model="byok", byok_provider="anthropic", agent=True,
                           agent_stop="budget" if isinstance(exc, _AgentBudgetError) else "busy" if isinstance(exc, chat._ByokBusyError) else "error",
                           error="ByokLimitExceeded" if isinstance(exc, chat._ByokBusyError) else type(exc).__name__)
        for name, value in (("agent_rounds", 0), ("agent_tools", []), ("agent_usage", {}),
                            ("web_search_requests", 0), ("web_fetch_requests", 0), ("agent_tool_errors", 0)):
            state.trace.setdefault(name, value)
        if not isinstance(exc, chat._ByokBusyError):
            state.trace["byok_error"] = error_category(exc)
        yield chat._sse({"error": exc.message if isinstance(exc, chat._ByokBusyError) else error_message(exc)})
    finally:
        release_user_lock()


async def _stream_claude_agent(ctx, state, deadline, release_user_lock):
    from services import chat_service as chat

    task = asyncio.create_task(asyncio.to_thread(chat.get_pending, ctx.state_key))
    async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
        async for event in waiting:
            yield event
    pending = task.result()
    if pending:
        task = asyncio.create_task(asyncio.to_thread(chat.clear_pending, ctx.state_key))
        async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
            async for event in waiting:
                yield event
        task.result()
    if ctx.has_image:
        mode = "friend"
    else:
        task = asyncio.create_task(asyncio.to_thread(chat.detect_mode, chat.client, ctx.state_key, ctx.message, ctx.history))
        async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
            async for event in waiting:
                yield event
        mode = task.result()
    task = asyncio.create_task(chat._ensure_active_conversation(ctx))
    async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
        async for event in waiting:
            yield event
    task.result()
    if _now() >= deadline:
        raise _AgentBudgetError()
    state.trace["mode"] = mode
    state.sys_prompt_final = chat._final_system_prompt(chat.apply_mode_prompt(chat._without_safety(ctx.system_prompt), mode),
                                                     trailing_system=chat._has_trailing_system(ctx))
    if mode == "mirror":
        # The legacy mirror stream acquires the same user lock itself.
        release_user_lock()
        async with aclosing(chat.stream_mirror(ctx, state)) as mirror:
            async for event in mirror:
                yield event
        return

    state.trace.update(model="byok", byok_provider="anthropic", agent=True, agent_rounds=0, agent_tools=[],
                       agent_stop="end_turn", web_search_requests=0, web_fetch_requests=0, agent_usage={}, agent_tool_errors=0)
    task = asyncio.create_task(_agent_messages(ctx, state))
    async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
        async for event in waiting:
            yield event
    messages = task.result()
    labelled = False
    delivered = False
    sources = []
    sources_sent = False
    image_path = None
    persisted_image_path = None
    owned_image_result = None
    image_success = False
    claude_text = ""
    visible_chars = 0
    tools_executed = pauses = 0
    last_answer = False
    daily_counted = False
    billable_pending = False
    persistence_failed = False
    platform_failure = False

    def label():
        return chat._sse({"reply_model": {"source": "byok", "label": provider_label("anthropic", ctx.byok_config["model"])}})

    async def save_delivered():
        nonlocal persistence_failed, persisted_image_path
        if delivered and not state.response_saved:
            saved_image_path = image_path
            save_task = asyncio.create_task(chat._save_response(ctx, state, image_path=saved_image_path))
            try:
                with anyio.CancelScope(shield=True):
                    try:
                        await asyncio.shield(save_task)
                    except asyncio.CancelledError:
                        await save_task
                        raise
                    finally:
                        if state.response_saved:
                            persisted_image_path = saved_image_path
                            state.billable = state.billable or billable_pending
            except Exception:
                persistence_failed = True
                raise
            if ctx.has_image and claude_text.strip():
                try:
                    await chat.set_message_image_summary(ctx.user, ctx.conversation_id, ctx.uploaded_image_path, claude_text[:120])
                except Exception as exc:
                    print(f"[byok] image summary write failed type={type(exc).__name__}", flush=True)

    try:
        while True:
            if _now() >= deadline:
                raise _AgentBudgetError()
            slot_deadline = min(deadline, _now() + _SLOT_WAIT_SECONDS)
            while True:
                try:
                    slot = chat._byok_slot()
                    pool = slot.__enter__()
                    break
                except chat._ByokBusyError:
                    if _now() >= deadline:
                        raise _AgentBudgetError()
                    if _now() >= slot_deadline:
                        raise chat._ByokBusyError("自带模型通道繁忙，请稍后再试")
                    await asyncio.sleep(min(.1, max(0, slot_deadline - _now())))
                except Exception:
                    platform_failure = True
                    raise
            stream = None
            control = ReplyStreamControl()
            exhausted = False
            try:
                if not daily_counted:
                    try:
                        cap = chat.check_chat_daily_cap("byok_chat", ctx.user, hit=True)
                    except Exception:
                        platform_failure = True
                        raise
                    daily_counted = True
                    if cap:
                        raise chat._ByokBusyError(cap)
                state.trace["agent_rounds"] += 1
                task = asyncio.create_task(chat._byok_call(pool, partial(open_agent_stream, ctx.byok_config, messages,
                                            username=ctx.user, tools=CLAUDE_CLIENT_TOOLS, deadline_seconds=deadline - _now(), control=control), control=control))
                try:
                    async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
                        async for event in waiting:
                            yield event
                    stream = task.result()
                finally:
                    if stream is None and task.done() and not task.cancelled() and task.exception() is None:
                        control.abort()
                        with anyio.CancelScope(shield=True):
                            await chat._byok_call(pool, task.result().close)
                iterator = iter(stream)
                request_text_started = False
                while True:
                    if _now() >= deadline:
                        raise _AgentBudgetError()
                    task = asyncio.create_task(chat._byok_call(pool, next, iterator, chat._STREAM_END, control=control))
                    async with aclosing(_wait_task(task, deadline, ": thinking\n\n", chat._BYOK_HEARTBEAT_SECONDS)) as waiting:
                        async for event in waiting:
                            yield event
                    chunk = task.result()
                    if chunk is chat._STREAM_END:
                        exhausted = True
                        break
                    if not chunk.choices:
                        continue
                    raw_text = chunk.choices[0].delta.content or ""
                    if raw_text and not request_text_started:
                        request_text_started = True
                        if delivered and state.full_response:
                            separator = "\n\n"[:max(0, 8000 - visible_chars)]
                            state.full_response += separator
                            # Cards render below the text, so only already visible
                            # text needs a visible gap before this request's text.
                            if visible_chars > 0 and separator:
                                claude_text += separator
                                visible_chars += len(separator)
                                yield chat._sse({"text": separator})
                    text = raw_text[:max(0, 8000 - visible_chars)]
                    if text:
                        if not labelled:
                            yield label()
                            labelled = True
                        state.full_response += text
                        claude_text += text
                        visible_chars += len(text)
                        delivered = True
                        yield chat._sse({"text": text})
                    if visible_chars >= 8000:
                        break
                final = getattr(stream, "final_message", None)
                _add_usage(state.trace, final)
                content = _assistant_content(final)
                _collect_sources(_value(final, "content", []) or [], sources)
                stop = _value(final, "stop_reason", getattr(stream, "stop_reason", None)) or "end_turn"
                refused = bool(getattr(stream, "refused", False) or stop == "refusal")
            finally:
                if stream is not None:
                    if not exhausted and not control.aborted:
                        control.abort()
                    with anyio.CancelScope(shield=True):
                        try:
                            await chat._byok_call(pool, stream.close, control=control)
                        except Exception as exc:
                            print(f"[byok] close failed type={type(exc).__name__}", flush=True)
                slot.__exit__(None, None, None)
            state.trace["agent_stop"] = stop
            if visible_chars >= 8000:
                state.trace["agent_stop"] = "text_limit"
                break
            if last_answer and stop in {"tool_use", "pause_turn"}:
                if stop == "tool_use":
                    state.trace["agent_stop"] = "tool_limit"
                break
            if stop == "pause_turn":
                if pauses >= 2:
                    state.trace["agent_stop"] = "pause_limit"
                    break
                pauses += 1
                messages.append({"role": "assistant", "content": _assistant_content(final, trim_fallback=False)})
                continue
            if stop != "tool_use":
                if refused:
                    if not claude_text.strip():
                        raise RefusalError()
                    text = "（Claude 中止了这条回复）"[:max(0, 8000 - visible_chars)]
                    state.full_response += text
                    visible_chars += len(text)
                    if text:
                        yield chat._sse({"text": text})
                break
            tool = next((item for item in content if item.get("type") == "tool_use" and item.get("name") in {*_CLIENT_INTENTS, "generate_image"}), None)
            if tool is None:
                break
            name = tool["name"]
            if not labelled:
                yield label()
                labelled = True
            if tools_executed >= 4:
                result_text = _TOOL_LIMIT_RESULT
                last_answer = True
            else:
                tools_executed += 1
                state.trace["agent_tools"].append(name)
                args = tool.get("input")
                args = args if isinstance(args, dict) else {}
                if name == "generate_image":
                    validated = validate_image_tool_call({"name": name, "arguments": args})
                    if image_success:
                        result_text = _IMAGE_LIMIT_RESULT
                    elif validated is None:
                        result_text = "这次没能生成图片，请再描述一次想画的画面。"
                        state.trace["agent_tool_errors"] += 1
                        yield chat._sse({"status": "image_failed", "source": "tool"})
                    else:
                        result = {}
                        owned_image_result = result
                        image_prefix = state.full_response
                        image_text = ""
                        previous_error = state.trace.get("error")
                        execution = chat._stream_image_execution(ctx, state, validated["prompt"], source="tool", lead_text="",
                                            model_id=validated.get("model"), aspect_ratio=validated.get("aspect_ratio"), agent_result=result)
                        try:
                            async with aclosing(execution):
                                while True:
                                    task = asyncio.create_task(anext(execution, chat._STREAM_END))
                                    async with aclosing(_wait_task(task, deadline, ": generating-image\n\n", chat._IMAGE_HEARTBEAT_SECONDS)) as waiting:
                                        async for event in waiting:
                                            yield event
                                    event = task.result()
                                    if event is chat._STREAM_END:
                                        break
                                    if event.startswith("data: "):
                                        payload = json.loads(event[6:])
                                        if payload.get("error"):
                                            result["error"] = payload["error"]
                                            continue
                                        if "generated_image" in payload:
                                            image_success = True
                                            image_path = payload["generated_image"]["image_path"]
                                            delivered = True
                                            billable_pending = True
                                            # The adapter prepares all text before this event.
                                            # Retain only text actually delivered within the cap.
                                            state.full_response = image_prefix
                                        if "text" in payload:
                                            text = payload["text"][:max(0, 8000 - visible_chars)]
                                            visible_chars += len(text)
                                            image_text += text
                                            state.full_response = image_prefix + image_text
                                            if not text:
                                                continue
                                            event = chat._sse({**payload, "text": text})
                                    yield event
                        except (_AgentBudgetError, chat.ResourceNotFound):
                            raise
                        except Exception:
                            result["error"] = "图片生成失败，请稍后再试"
                        finally:
                            if previous_error is None:
                                state.trace.pop("error", None)
                            else:
                                state.trace["error"] = previous_error
                        image_success = image_success or bool(result.get("success"))
                        if image_success:
                            image_path = result.get("image_path", image_path)
                            billable_pending = True
                            delivered = True
                            result_text = f"图片已生成并展示给主人（模型：{result.get('model', '')}，比例：{result.get('aspect_ratio', '')}）"
                        else:
                            result_text = result.get("error") or "图片生成失败，请稍后再试"
                            state.trace["agent_tool_errors"] += 1
                            yield chat._sse({"status": "image_failed", "source": "tool"})
                else:
                    required = next(item["input_schema"]["required"] for item in CLAUDE_CLIENT_TOOLS if item["name"] == name)
                    params = {key: args.get(key) for key in required}
                    valid = all(isinstance(value, str) and value.strip() for value in params.values())
                    if name == "get_weather":
                        city = _city_is_allowed(ctx, params.get("city"))
                        valid = valid and bool(city)
                        params = {"city": city}
                        if not city:
                            valid = False
                            result_text = _CITY_PRIVACY_RESULT
                        else:
                            result_text = "工具参数不完整，请先向主人询问"
                    else:
                        result_text = "工具参数不完整，请先向主人询问"
                    if name == "get_hot_topics" and params.get("source") not in ("微博", "知乎", "抖音", "B站", "头条"):
                        valid = False
                    if not valid:
                        state.trace["agent_tool_errors"] += 1
                    if valid:
                        cap = chat.check_chat_daily_cap("weather", ctx.user, hit=True) if name == "get_weather" else None
                        if cap:
                            result_text = cap
                            state.trace["agent_tool_errors"] += 1
                        else:
                            task = asyncio.create_task(chat.run_slow(chat.execute_intent, _CLIENT_INTENTS[name], params))
                            try:
                                async with aclosing(_wait_task(task, deadline, ": tool\n\n", _TOOL_HEARTBEAT_SECONDS)) as waiting:
                                    async for event in waiting:
                                        yield event
                                card = task.result()
                            except _AgentBudgetError:
                                raise
                            except chat.ResourceNotFound:
                                raise
                            except Exception:
                                card = {"type": "card", "source": name, "points": [], "error": True, "message": "工具暂时不可用，请稍后再试"}
                            result_text = _tool_result_text(name, card)
                            if isinstance(card, dict) and card.get("error"):
                                state.trace["agent_tool_errors"] += 1
                            if isinstance(card, dict) and card.get("type") == "card":
                                billable_pending = billable_pending or chat._tool_billable(_CLIENT_INTENTS[name], card)
                                state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"
                                delivered = True
                                yield chat._sse({"card": card, "append": True})
            if visible_chars >= 8000:
                state.trace["agent_stop"] = "text_limit"
                break
            messages.extend([{"role": "assistant", "content": content},
                             {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool.get("id"), "content": result_text}]}])
        if sources:
            if not labelled:
                yield label()
                labelled = True
            card = {"type": "card", "subtype": "web_sources", "source": "联网搜索", "points": [], "sources": sources, "error": False}
            state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"
            delivered = sources_sent = True
            yield chat._sse({"card": card, "append": True})
        if not delivered:
            raise EmptyReplyError()
        await save_delivered()
        yield chat._sse({"done": True})
        if state.response_saved and "error" not in state.trace:
            await chat._normal_followups(ctx, state, True)
    except Exception as exc:
        if persistence_failed or isinstance(exc, chat.ResourceNotFound):
            raise
        if platform_failure:
            await save_delivered()
            raise
        if isinstance(exc, _AgentBudgetError):
            state.trace["agent_stop"] = "budget"
        elif isinstance(exc, chat._ByokBusyError):
            state.trace["agent_stop"] = "busy"
        else:
            if state.trace["agent_stop"] not in {"refusal", "max_tokens"}:
                state.trace["agent_stop"] = "error"
        state.trace["error"] = "ByokLimitExceeded" if isinstance(exc, chat._ByokBusyError) else type(exc).__name__
        if not isinstance(exc, chat._ByokBusyError):
            state.trace["byok_error"] = error_category(exc)
            print(f"[byok] reply failed category={error_category(exc)}", flush=True)
        if delivered and sources and not sources_sent:
            if not labelled:
                yield label()
            card = {"type": "card", "subtype": "web_sources", "source": "联网搜索", "points": [], "sources": sources, "error": False}
            state.full_response += "［卡片：" + chat._summarize_card_for_history(card) + "］"
            delivered = True
            yield chat._sse({"card": card, "append": True})
        await save_delivered()
        yield chat._sse({"error": exc.message if isinstance(exc, chat._ByokBusyError) else error_message(exc)})
    finally:
        # An image can finish while the caller is suspended at a heartbeat.
        # The adapter has transferred ownership even before its event is read.
        image_path = image_path or (owned_image_result or {}).get("image_path")
        if image_path and image_path != persisted_image_path:
            chat.delete_uploaded_files([image_path])
