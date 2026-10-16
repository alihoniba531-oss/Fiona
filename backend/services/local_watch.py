"""Bounded in-memory watch decisions; only alert summaries reach persistence."""
import asyncio
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
import operator
import re
import time

import database
from byok import client as byok_client, store as byok_store
from byok.providers import PROVIDERS, validate_model
from llm import QWEN_CLIENT, QWEN_EXTRA_BODY
from rate_limit import check_watch_daily_cap
from trace import log_event

WATCH_SYSTEM_PROMPT = '你是屏幕提醒判断器。下面是用户电脑上某个程序窗口里新出现的文字（由 OCR 识别，可能有错字）。根据用户设定的提醒条件判断现在是否需要提醒用户。只依据给出的文字判断，不要猜测看不到的内容。只输出 JSON：{"alert": true或false, "summary": "需要提醒时用一句话说明发生了什么（不超过 60 字），不需要时为空串"}'
JUDGE_TIMEOUT_SECONDS = 8.0
_logger = logging.getLogger(__name__)
_rule_locks = {}
_private_request = ContextVar("local_watch_private_request", default=False)


class _PrivateRequestFilter(logging.Filter):
    """SDK request/response DEBUG logs are private during a watch model call."""
    def filter(self, record):
        return not _private_request.get() or record.name == __name__


_request_filter = _PrivateRequestFilter()


def _protect_sdk_logs():
    # Handler filtering also covers propagated child SDK loggers. ContextVar is
    # copied into asyncio.to_thread, so unrelated concurrent requests keep logs.
    handlers = set(logging.getLogger().handlers)
    for value in logging.Logger.manager.loggerDict.values():
        if isinstance(value, logging.Logger):
            handlers.update(value.handlers)
    for handler in handlers:
        if _request_filter not in handler.filters:
            handler.addFilter(_request_filter)


def keyword_decision(params: dict, lines: list[str]) -> str | None:
    for line in lines:
        lowered = line.casefold()
        for keyword in params["keywords"]:
            if keyword.casefold() in lowered:
                return f"命中『{keyword}』：{line[:80]}"
    return None


_NUMBER = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+(?!\d|,\d)|\d+)(?:\.\d+)?%?|[-+]?\.\d+%?")
_NUMBER_TRANSLATION = str.maketrans(
    "−－﹣‒–０１２３４５６７８９．％＋，",
    "-----0123456789.%+,",
)
_OPERATORS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def number_decision(params: dict, lines: list[str]) -> str | None:
    label = params["label"]
    for line in lines:
        index = line.find(label)
        if index < 0:
            continue
        match = _NUMBER.search(line[index + len(label):].translate(_NUMBER_TRANSLATION))
        if match is None:
            continue
        raw = match.group().replace(",", "")
        value = float(raw.rstrip("%"))
        if math.isfinite(value) and _OPERATORS[params["op"]](value, params["threshold"]):
            display = format(value, ".15g") + ("%" if raw.endswith("%") else "")
            return f"{label} 当前 {display}，已 {params['op']} {params['threshold']}"
    return None


def _invalid_constant(value):
    raise ValueError("Invalid JSON constant")


def _parse_decision(text):
    result = json.loads(text, parse_constant=_invalid_constant)
    if not isinstance(result, dict) or type(result.get("alert")) is not bool:
        raise ValueError("Invalid watch decision")
    if not result["alert"]:
        return {"alert": False}
    if not isinstance(result.get("summary"), str):
        raise ValueError("Invalid watch decision")
    summary = result["summary"].strip()
    if not 1 <= len(summary) <= 80:
        raise ValueError("Invalid watch summary")
    return {"alert": result["alert"], "summary": summary}


def _platform_once(user_message):
    token = _private_request.set(True)
    try:
        # with_options shares the platform transport; do not close this view.
        client = QWEN_CLIENT.with_options(timeout=JUDGE_TIMEOUT_SECONDS, max_retries=0)
        response = client.chat.completions.create(
            model="qwen3.8-flash", stream=False, max_tokens=300,
            response_format={"type": "json_object"}, extra_body=deepcopy(QWEN_EXTRA_BODY),
            messages=[{"role": "system", "content": WATCH_SYSTEM_PROMPT}, {"role": "user", "content": user_message}],
        )
        return _parse_decision(response.choices[0].message.content)
    finally:
        _private_request.reset(token)


def _claude_once(config, user_message):
    token = _private_request.set(True)
    client = None
    try:
        # Reuse BYOK's SDK and provider configuration; credentials come only from
        # its existing decryption/storage API. No agent tools or stream are used.
        client = byok_client.anthropic.Anthropic(
            api_key=config["api_key"], base_url=PROVIDERS["anthropic"]["base_url"],
            timeout=JUDGE_TIMEOUT_SECONDS, max_retries=0,
        )
        response = client.messages.create(
            model=validate_model("anthropic", config["model"]), stream=False, max_tokens=300,
            system=WATCH_SYSTEM_PROMPT, messages=[{"role": "user", "content": user_message}],
            output_config={"format": {"type": "json_schema", "schema": {
                "type": "object", "properties": {"alert": {"type": "boolean"}, "summary": {"type": "string"}},
                "required": ["alert", "summary"], "additionalProperties": False,
            }}},
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return _parse_decision(text)
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            _private_request.reset(token)


async def _judge_ai_once(username, params, lines):
    user_message = f"提醒条件：{params['condition']}\n新出现的文字：\n" + "\n".join(lines)[:2000]
    if params.get("model", "platform") == "claude":
        config = await byok_store.get_internal_config(username)
        if not config or not config.get("enabled") or config.get("provider") != "anthropic" or not config.get("api_key") or config.get("status") != "ok":
            raise ValueError("Anthropic BYOK unavailable")
        return await asyncio.to_thread(_claude_once, config, user_message)
    return await asyncio.to_thread(_platform_once, user_message)


async def judge_ai(username: str, params: dict, lines: list[str], *, failure=None) -> dict | None:
    _protect_sdk_logs()
    try:
        return await asyncio.wait_for(_judge_ai_once(username, params, lines), timeout=JUDGE_TIMEOUT_SECONDS)
    except Exception as exc:
        # Exception messages can contain OCR or SDK response bodies. Retain type
        # only, and let the outer observation record the safe metadata trace.
        if failure is not None:
            failure.append(type(exc).__name__)
        _logger.warning("local_watch exception_type=%s", type(exc).__name__)
        return None


async def process_observation(username: str, rule: dict, lines: list[str], *, app_name: str | None = None) -> dict:
    # All watch writes for an account serialize, preventing duplicate alerts and
    # making message-id resolution independent from concurrent rule decisions.
    lock = _rule_locks.setdefault(username, asyncio.Lock())
    async with lock:
        # A rule can be disabled/deleted while an observation waits for the lock.
        current = await database.get_watch_rule(username, rule["id"])
        if not current or not current["enabled"]:
            return {"alert": False}
        rule = current
        latest = await database.latest_watch_alert_time(username, rule["id"])
        if latest:
            instant = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - instant).total_seconds() < rule["cooldown_seconds"]:
                return {"alert": False}
        started = time.monotonic()
        failure = []
        summary = None
        if rule["kind"] == "keyword":
            summary = keyword_decision(rule["params"], lines)
        elif rule["kind"] == "number":
            summary = number_decision(rule["params"], lines)
        elif not check_watch_daily_cap(username):
            result = await judge_ai(username, rule["params"], lines, failure=failure)
            if result and result["alert"]:
                summary = result["summary"]
        alert = None
        if summary:
            # Models can take several seconds. A rule removed, disabled, or
            # edited in that interval must not deliver its stale decision.
            still_current = await database.get_watch_rule(username, rule["id"])
            if still_current != rule or not still_current["enabled"]:
                summary = None
        if summary:
            label = app_name or rule["name"]
            summary = summary[:200]
            content = f"【本机提醒 · {label}】{summary}（规则：{rule['name']}）"
            alert = await database.save_watch_alert(username, rule, summary, content)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        payload = {"rule_id": rule["id"], "kind": rule["kind"], "alert": bool(alert), "elapsed_ms": elapsed_ms}
        if failure:
            payload["exception_type"] = failure[0]
        await log_event(username, "local_watch", payload=payload, duration_ms=elapsed_ms, success=not failure)
        _logger.info("local_watch rule_id=%s kind=%s alert=%s elapsed_ms=%s exception_type=%s", rule["id"], rule["kind"], bool(alert), elapsed_ms, failure[0] if failure else None)
        return {"alert": bool(alert), **({"alert_id": alert["id"]} if alert else {})}
