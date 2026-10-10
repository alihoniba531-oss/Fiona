"""Native image tools and the bounded, non-streaming image-intent planner."""
import asyncio
from copy import deepcopy
import json
import logging
import re
import time

from llm import QWEN_CLIENT, QWEN_EXTRA_BODY


IMAGE_PLANNER_PROMPT = """你是生图意图判断器。阅读对话（最后一条是主人刚说的话），判断主人这一句是否要求「现在生成一张图片」。
要求生成图片的情形：明确让你画/生成图片/出图/生成照片；让你把之前出现的描述或提示词画出来；让你在之前的描述上修改风格或内容后再画。
不算的情形：只要提示词或文案；讨论、比较、询问生图模型、价格或用法；评价已有图片；只是提到自己画画。
如果要生成，把要画的内容整理成一段完整、具体的画面描述（可沿用之前的英文提示词原文并按要求修改），不得写入账号名、真实姓名或私人细节。
只输出 JSON：{"draw": true或false, "prompt": "画面描述或空串", "model": "seedream-5.0-flash" 或 "qwen-image-3.0" 或 null（仅当主人点名：Seedream/豆包/即梦→seedream-5.0-flash；千问/通义/Qwen→qwen-image-3.0）, "aspect_ratio": "1:1"/"16:9"/"9:16" 或 null}"""
IMAGE_PLANNER_PREFILTER_PATTERN = "画|绘|图|照片|相片|生成|出一张|来一张|风格|.风[。！!？?…～~]?$|提示词|prompt|seedream|即梦|豆包|千问|通义|qwen|draw|image|picture|photo|render|海报|壁纸|插画|头像"
IMAGE_PLANNER_PREFILTER = re.compile(IMAGE_PLANNER_PREFILTER_PATTERN, re.IGNORECASE)
IMAGE_PLANNER_TIMEOUT_SECONDS = 8.0
_logger = logging.getLogger(__name__)


def image_planner_prescreen(message: str, *, explicit: bool = False) -> bool:
    return bool(explicit or IMAGE_PLANNER_PREFILTER.search(message))


def _plan_image_once(history: list[dict], message: str) -> dict:
    recent = [row for row in history if row.get("role") in ("user", "assistant")][-5:]
    turns = [
        ("主人：" if row["role"] == "user" else "你：") + row["content"][:600]
        for row in recent
    ]
    current = message if len(message) <= 1500 else message[:1000] + "……" + message[-500:]
    turns.append("主人：" + current)
    # with_options shares the existing client's HTTP transport. Closing this
    # derived client would also close the reusable platform light-slot client.
    client = QWEN_CLIENT.with_options(timeout=IMAGE_PLANNER_TIMEOUT_SECONDS, max_retries=0)
    response = client.chat.completions.create(
        model="qwen3.8-flash",
        messages=[
            {"role": "system", "content": IMAGE_PLANNER_PROMPT},
            {"role": "user", "content": "\n".join(turns)},
        ],
        stream=False,
        response_format={"type": "json_object"},
        max_tokens=600,
        extra_body=deepcopy(QWEN_EXTRA_BODY),
    )
    result = json.loads(response.choices[0].message.content, parse_constant=_invalid_constant)
    if not isinstance(result, dict) or type(result.get("draw")) is not bool:
        raise ValueError("invalid planner decision")
    if not result["draw"]:
        return {"status": "no"}
    arguments = validate_image_tool_call({"name": "generate_image", "arguments": result})
    if arguments is None:
        raise ValueError("invalid planner prompt")
    return {"status": "draw", **arguments}


async def plan_image(history: list[dict], message: str) -> dict:
    """Return draw/no/error, retaining no sensitive text in errors or logs."""
    started = time.monotonic()
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_plan_image_once, history, message),
            timeout=IMAGE_PLANNER_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        exception_type = type(exc).__name__
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _logger.warning("image_planner exception_type=%s elapsed_ms=%s", exception_type, elapsed_ms)
        return {"status": "error", "exception_type": exception_type, "elapsed_ms": elapsed_ms}


_DESCRIPTION = """只有用户明确要求画图或生成图片时才调用 generate_image，包括「把上面的提示词画出来」「按你说的画，改成动漫风」「再画一张猫」。仅要提示词、讨论生图、评价图片、询问价格或用法时不调用，例如「帮我写一段生图提示词」「哪个生图模型好」「这张图好看吗」「生图多少钱」「怎么使用生图」。可以引用历史对话里之前出现的描述或提示词，整理成一段完整、具体的画面描述。只能生成新图，不能修改已有图片；要基于已有图片修改时，引导用户点那张图上的「以此图修改」。描述不得写入账号名、真实姓名、私有记忆里的个人细节。调用前最多说一句话，不得声称图片已经画好。只有用户点名生图模型时才填 model：点名 Seedream / 豆包 / 即梦填 seedream-5.0-flash；点名千问 / 通义 / Qwen 填 qwen-image-3.0。每轮最多调用一次，生成一张新图。"""
_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "maxLength": 1500, "description": "完整、具体的画面描述"},
        "model": {"type": "string", "enum": ["seedream-5.0-flash", "qwen-image-3.0"]},
        "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16"]},
    },
    "required": ["prompt"],
}
_INVALID_STOPS = frozenset({"refusal", "max_tokens", "length", "content_filter"})


def openai_image_tool() -> dict:
    return {"type": "function", "function": {"name": "generate_image", "description": _DESCRIPTION, "parameters": deepcopy(_SCHEMA)}}


def anthropic_image_tool() -> dict:
    return {"name": "generate_image", "description": _DESCRIPTION, "input_schema": deepcopy(_SCHEMA)}


def _value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _invalid_constant(value):
    raise ValueError("invalid JSON constant")


class OpenAIToolCallAccumulator:
    """Retain first id/name and concatenate arguments only, grouped by index."""
    def __init__(self):
        self._calls = {}

    def add(self, deltas) -> None:
        for delta in deltas or []:
            index = _value(delta, "index", 0)
            call = self._calls.setdefault(index, {"id": None, "name": None, "arguments": ""})
            fn = _value(delta, "function")
            for key, value in (("id", _value(delta, "id")), ("name", _value(fn, "name"))):
                if not call[key] and value:
                    call[key] = value
            arguments = _value(fn, "arguments")
            if isinstance(arguments, str):
                call["arguments"] += arguments

    def result(self, finish_reason) -> tuple[dict | None, bool]:
        call = next((call for call in self._calls.values() if call["name"] == "generate_image"), None)
        if call is None:
            return None, False
        if finish_reason in _INVALID_STOPS:
            return None, True
        if finish_reason != "tool_calls":
            return None, False
        try:
            arguments = json.loads(call["arguments"], parse_constant=_invalid_constant)
        except (ValueError, TypeError, RecursionError):
            return None, True
        if not isinstance(arguments, dict):
            return None, True
        return {"name": "generate_image", "arguments": arguments}, False


def extract_anthropic_image_tool_call(message) -> tuple[dict | None, bool]:
    content = list(_value(message, "content", []) or [])
    fallback = max((index for index, item in enumerate(content) if _value(item, "type") == "fallback"), default=-1)
    call = next((item for item in content[fallback + 1:] if _value(item, "type") == "tool_use" and _value(item, "name") == "generate_image"), None)
    if call is None:
        return None, False
    stop = _value(message, "stop_reason")
    if stop in _INVALID_STOPS:
        return None, True
    if stop != "tool_use":
        return None, False
    arguments = _value(call, "input")
    if not isinstance(arguments, dict):
        return None, True
    return {"name": "generate_image", "arguments": arguments}, False


def validate_image_tool_call(call) -> dict | None:
    if not isinstance(call, dict) or call.get("name") != "generate_image":
        return None
    args = call.get("arguments")
    if not isinstance(args, dict):
        return None
    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.strip()) > 1500:
        return None
    result = {"prompt": prompt.strip()}
    for name in ("model", "aspect_ratio"):
        if args.get(name) in _SCHEMA["properties"][name]["enum"]:
            result[name] = args[name]
    return result
