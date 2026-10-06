"""Model review and its routing effects, with every provider replaced by a stub."""

import asyncio
import gc
import inspect
import json
import os
from pathlib import Path
import re
import runpy
import sqlite3
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from _fakes import FakeStream
import crisis_model
import safety


HIGH = "我想死"
POSSIBLE = "活着没意思"
ORDINARY = "帮我查下明天天气"
# The same valid one-pixel PNG used by the existing image routing tests.
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)
IMAGE = f"data:image/png;base64,{PNG}"


def _completion(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _stub_provider(monkeypatch, *, content='{"level":"none"}', failure=None):
    calls = {"clients": [], "requests": [], "cancelled": False}

    async def create(**kwargs):
        calls["requests"].append(kwargs)
        if failure == "timeout":
            try:
                await asyncio.Event().wait()
            finally:
                calls["cancelled"] = True
        if isinstance(failure, Exception):
            raise failure
        return _completion(content)

    def factory(**kwargs):
        # Never retain credentials in assertion diagnostics.
        calls["clients"].append({key: value for key, value in kwargs.items() if key != "api_key"})
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(crisis_model, "_client", None)
    monkeypatch.setattr(crisis_model, "AsyncOpenAI", factory)
    return calls


@pytest.fixture(autouse=True)
def enabled_stub_model(monkeypatch):
    from rate_limit import limiter

    monkeypatch.setenv("FIONA_CRISIS_MODEL_ENABLED", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "crisis-unit-test-placeholder")
    monkeypatch.delenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(limiter, "enabled", False)
    _stub_provider(monkeypatch)


def _stub_level(monkeypatch, level):
    calls = []

    async def classify(text):
        calls.append(text)
        return level

    monkeypatch.setattr(crisis_model, "classify", classify)
    return calls


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _conversation(client, headers):
    response = client.post("/conversations", json={}, headers=headers)
    assert response.status_code == 201
    return response.json()["conversation"]["id"]


def _balance(user):
    import database

    return asyncio.run(database.get_strawberry_balance(user))


def _production_headers(monkeypatch, user):
    import database
    from auth import create_token

    version = asyncio.run(database.get_session_version(user))
    monkeypatch.setenv("DEV_MODE", "0")
    return {"Authorization": f"Bearer {create_token(user, version)}"}


def _route_spies(monkeypatch):
    import services.chat_service as chat

    calls = {name: [] for name in ("detect", "recognize", "fill", "execute", "image", "model", "trace")}

    def detect(*args):
        calls["detect"].append(args)
        return "friend"

    def recognize(*args):
        calls["recognize"].append(args)
        return {"intent": "web_search", "params": {"query": ORDINARY}, "missing": []}

    def fill(*args):
        calls["fill"].append(args)
        return {"intent": "web_search", "params": {"query": ORDINARY}, "missing": []}

    def execute(*args):
        calls["execute"].append(args)
        return "stub tool result"

    async def image(*args):
        calls["image"].append(args)
        raise AssertionError("a high crisis must use the support route")

    def model(*args, **kwargs):
        calls["model"].append((args, kwargs))
        return FakeStream(), False

    async def trace(*args, **kwargs):
        if len(args) > 1 and args[1] == "chat":
            calls["trace"].append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "detect_mode", detect)
    monkeypatch.setattr(chat, "recognize_intent", recognize)
    monkeypatch.setattr(chat, "fill_param", fill)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "generate_image", image)
    monkeypatch.setattr(chat, "edit_image", image)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", model)
    monkeypatch.setattr(chat, "log_event", trace)
    return calls


def _assert_resource_once(events, level):
    assert sum(event.get("text", "").count(safety.CRISIS_RESOURCE_NOTE) for event in events) == 1
    assert [event for event in events if event.get("crisis") is True] == (
        [{"crisis": True}] if level == "high" else []
    )
    if level == "high":
        assert events[0] == {"crisis": True}


@pytest.mark.parametrize("rule", [None, "possible", "high"])
@pytest.mark.parametrize("model", [None, "none", "possible", "high"])
def test_combine_only_upgrades(rule, model):
    rank = {None: 0, "none": 0, "possible": 1, "high": 2}
    expected = rule if rank[rule] >= rank[model] else model
    assert safety.combine_crisis_levels(rule, model) == expected


def test_import_does_not_build_client_or_read_credentials(monkeypatch):
    import openai

    reads = []
    getenv = os.getenv

    def guarded_getenv(name, *args):
        if name == "DASHSCOPE_API_KEY":
            reads.append(name)
        return getenv(name, *args)

    def forbidden_client(**kwargs):
        raise AssertionError("client construction during module import")

    monkeypatch.setattr(os, "getenv", guarded_getenv)
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden_client)
    namespace = runpy.run_path(str(Path(crisis_model.__file__)))
    assert namespace["_client"] is None
    assert reads == []


@pytest.mark.parametrize("level", ["high", "possible", "none"])
def test_classifier_request_and_safe_success_log(monkeypatch, capsys, level):
    import llm

    private_text = "仅供单元测试的私密待判文字"
    calls = _stub_provider(monkeypatch, content=json.dumps({"level": level}))
    assert asyncio.run(crisis_model.classify(f"  {private_text}\n")) == level
    assert len(calls["clients"]) == len(calls["requests"]) == 1
    constructor = calls["clients"][0]
    assert constructor["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert constructor["max_retries"] == 0
    assert constructor["timeout"] == 2.0
    request = calls["requests"][0]
    assert request["model"] == llm.QWEN_MODEL
    assert request["extra_body"] == {"enable_thinking": False}
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0
    assert 0 < request["max_tokens"] <= 40
    assert request["messages"] == [
        {"role": "system", "content": crisis_model.SYSTEM_PROMPT},
        {"role": "user", "content": private_text},
    ]
    output = capsys.readouterr().out
    assert re.fullmatch(rf"\[crisis-model\] level={level} ms=\d+(?:\.\d+)?\n", output)
    assert private_text not in output


@pytest.mark.parametrize("setting", [None, "1", "false", "", " 0 "])
def test_only_literal_zero_disables_model(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("FIONA_CRISIS_MODEL_ENABLED", raising=False)
    else:
        monkeypatch.setenv("FIONA_CRISIS_MODEL_ENABLED", setting)
    calls = _stub_provider(monkeypatch)
    assert asyncio.run(crisis_model.classify("正常的测试内容")) == "none"
    assert len(calls["requests"]) == 1


def test_disabled_never_builds_client_and_switch_is_read_per_call(monkeypatch):
    calls = _stub_provider(monkeypatch)
    monkeypatch.setenv("FIONA_CRISIS_MODEL_ENABLED", "0")
    assert asyncio.run(crisis_model.classify("有文字")) is None
    assert calls["clients"] == calls["requests"] == []
    monkeypatch.setenv("FIONA_CRISIS_MODEL_ENABLED", "1")
    assert asyncio.run(crisis_model.classify("有文字")) == "none"
    monkeypatch.setenv("FIONA_CRISIS_MODEL_ENABLED", "0")
    assert asyncio.run(crisis_model.classify("又有文字")) is None
    assert len(calls["clients"]) == len(calls["requests"]) == 1


@pytest.mark.parametrize("setting,expected", [
    (None, 2.0), ("0.5", 0.5), ("10", 10.0), ("1.25", 1.25),
    ("0.49", 2.0), ("10.01", 2.0), ("0", 2.0), ("-1", 2.0),
    ("broken", 2.0), ("", 2.0), ("nan", 2.0), ("inf", 2.0),
])
def test_timeout_config_range_and_fallback(monkeypatch, setting, expected):
    if setting is not None:
        monkeypatch.setenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", setting)
    calls = _stub_provider(monkeypatch)
    assert asyncio.run(crisis_model.classify("测试调用配置")) == "none"
    assert calls["clients"][0]["timeout"] == expected
    assert calls["requests"][0]["timeout"] == expected


def test_timeout_is_read_per_call_and_client_is_reused(monkeypatch):
    calls = _stub_provider(monkeypatch)

    async def scenario():
        monkeypatch.setenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", "0.75")
        assert await crisis_model.classify("第一次") == "none"
        monkeypatch.setenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", "3.5")
        assert await crisis_model.classify("第二次") == "none"

    asyncio.run(scenario())
    assert len(calls["clients"]) == 1
    assert [request["timeout"] for request in calls["requests"]] == [0.75, 3.5]


@pytest.mark.parametrize("text", ["", " ", "\n\t "])
def test_empty_classifier_input_never_builds_client(monkeypatch, text):
    calls = _stub_provider(monkeypatch)
    assert asyncio.run(crisis_model.classify(text)) is None
    assert calls["clients"] == calls["requests"] == []


def test_classifier_trims_then_preserves_first_and_last_1000_characters(monkeypatch):
    calls = _stub_provider(monkeypatch)
    text = "中文🙂" * 900
    assert asyncio.run(crisis_model.classify("  \n" + text + " \t")) == "none"
    submitted = calls["requests"][0]["messages"][1]["content"]
    assert submitted == text[:1000] + "……" + text[-1000:]
    assert len(submitted) == 2002


@pytest.mark.parametrize("message,rule", [("你好，聊聊天吧", None), (POSSIBLE, "possible")])
@pytest.mark.parametrize("failure,exception_type", [
    ("timeout", "TimeoutError"), ("exception", "RuntimeError"),
    ("non_json", "JSONDecodeError"), ("unknown_level", "ValueError"),
])
def test_failed_model_keeps_rule_level_and_never_logs_text(
    client, dev_headers, monkeypatch, capsys, message, rule, failure, exception_type,
):
    assert safety.assess_crisis(message) == rule
    private_marker = "私密异常内容不能出现"
    content = private_marker if failure == "non_json" else '{"level":"unrecognized"}'
    provider_failure = RuntimeError(private_marker + message) if failure == "exception" else (
        "timeout" if failure == "timeout" else None
    )
    calls = _stub_provider(monkeypatch, content=content, failure=provider_failure)
    monkeypatch.setenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", "0.5")
    conversation = _conversation(client, dev_headers)
    routes = _route_spies(monkeypatch)
    capsys.readouterr()
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": message,
    }))
    assert routes["trace"][0]["crisis"] == rule
    assert not any(event.get("crisis") is True for event in events)
    if rule is None:
        assert not any(safety.CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    else:
        _assert_resource_once(events, "possible")
    assert events[-1] == {"done": True}
    output = capsys.readouterr().out
    logs = [line for line in output.splitlines() if line.startswith("[crisis-model]")]
    assert len(logs) == 1
    assert re.fullmatch(rf"\[crisis-model\] failed type={exception_type} ms=\d+(?:\.\d+)?", logs[0])
    assert message not in output
    assert private_marker not in output
    assert len(calls["requests"]) == 1
    if failure == "timeout":
        assert calls["cancelled"] is True


@pytest.mark.parametrize("content", ['[]', '{}', 'null', '{"level":1}'])
def test_invalid_json_structure_returns_none(monkeypatch, capsys, content):
    _stub_provider(monkeypatch, content=content)
    assert asyncio.run(crisis_model.classify("结构错误的测试输入")) is None
    assert re.fullmatch(r"\[crisis-model\] failed type=ValueError ms=\d+(?:\.\d+)?\n", capsys.readouterr().out)


def test_rule_high_skips_model(client, dev_headers, monkeypatch):
    conversation = _conversation(client, dev_headers)
    calls = _stub_level(monkeypatch, "none")
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": HIGH,
    }))
    assert calls == []
    _assert_resource_once(events, "high")


@pytest.mark.parametrize("mode", ["chat", "image", "image_edit"])
def test_rule_none_model_high_gets_complete_crisis_route(
    client, dev_headers, monkeypatch, mode,
):
    from intent_router import get_pending, set_pending

    assert safety.assess_crisis(ORDINARY) is None
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    key = (user, conversation)
    pending = {"intent": "route", "params": {}, "missing": ["origin"]}
    set_pending(key, pending)
    before = _balance(user)
    classifications = _stub_level(monkeypatch, "high")
    routes = _route_spies(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    payload = {"conversation_id": conversation, "message": ORDINARY, "mode": mode}
    if mode == "image_edit":
        payload["reference_images"] = [{"image_base64": IMAGE}]
    events = _events(client.post("/chat", headers=headers, json=payload))
    _assert_resource_once(events, "high")
    assert classifications == [ORDINARY]
    assert routes["detect"] == routes["recognize"] == routes["fill"] == routes["execute"] == routes["image"] == []
    assert len(routes["model"]) == 1
    model_args, model_kwargs = routes["model"][0]
    assert model_kwargs["max_tokens"] == 700
    system_messages = [message["content"] for message in model_args[1] if message["role"] == "system"]
    assert sum(message.count(safety.CRISIS_GUIDANCE.strip()) for message in system_messages) == 1
    assert get_pending(key) == pending
    assert routes["trace"][0]["crisis"] == "high"
    assert routes["trace"][0]["mode"] == "crisis"
    assert _balance(user) == before - 10
    assert events[-1] == {"done": True}


@pytest.mark.parametrize("pending_turn", [False, True])
def test_rule_none_model_possible_blocks_tools_and_pending_and_costs_ten(
    client, dev_headers, monkeypatch, pending_turn,
):
    from intent_router import get_pending, set_pending

    assert safety.assess_crisis(ORDINARY) is None
    assert safety.is_informational_crisis_context(ORDINARY) is False
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    key = (user, conversation)
    pending = {"intent": "route", "params": {}, "missing": ["origin"]}
    if pending_turn:
        set_pending(key, pending)
    before = _balance(user)
    classifications = _stub_level(monkeypatch, "possible")
    routes = _route_spies(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": ORDINARY,
    }))
    _assert_resource_once(events, "possible")
    assert classifications == [ORDINARY]
    assert routes["recognize"] == routes["fill"] == routes["execute"] == routes["image"] == []
    assert len(routes["model"]) == 1
    assert routes["trace"][0]["crisis"] == "possible"
    assert routes["trace"][0]["tool"] is None
    assert _balance(user) == before - 10
    if pending_turn:
        assert get_pending(key) == pending
    assert events[-1] == {"done": True}


def test_rule_possible_model_none_does_not_downgrade(client, dev_headers, monkeypatch):
    conversation = _conversation(client, dev_headers)
    classifications = _stub_level(monkeypatch, "none")
    routes = _route_spies(monkeypatch)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": POSSIBLE,
    }))
    assert classifications == [POSSIBLE]
    _assert_resource_once(events, "possible")
    assert routes["trace"][0]["crisis"] == "possible"
    assert routes["recognize"] == routes["fill"] == routes["execute"] == []


@pytest.mark.parametrize("with_image", [False, True])
def test_model_upgraded_high_read_aloud_keeps_high_crisis_prompt(
    client, dev_headers, monkeypatch, with_image,
):
    import services.chat_service as chat

    message = "帮我念出来，今天是个好天气"
    assert safety.assess_crisis(message) is None
    conversation = _conversation(client, dev_headers)
    _stub_level(monkeypatch, "high")
    routes = _route_spies(monkeypatch)
    vision_requests = []

    def vision(**kwargs):
        vision_requests.append(kwargs)
        return FakeStream()

    monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=vision)),
    ))
    payload = {"conversation_id": conversation, "message": message}
    if with_image:
        payload["image_base64"] = IMAGE
    events = _events(client.post("/chat", headers=dev_headers, json=payload))
    _assert_resource_once(events, "high")
    if with_image:
        assert len(vision_requests) == 1
        messages = vision_requests[0]["messages"]
    else:
        assert len(routes["model"]) == 1
        messages = routes["model"][0][0][1]
    system_messages = [item["content"] for item in messages if item["role"] == "system"]
    assert sum(item.count(safety.CRISIS_GUIDANCE.strip()) for item in system_messages) == 1
    assert not any("对方刚才请求你" in item for item in system_messages)
    assert routes["trace"][0]["crisis"] == "high"
    assert events[-1] == {"done": True}


def test_zero_balance_model_high_returns_free_resources_without_main_model(
    client, dev_headers, monkeypatch,
):
    import database

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE users SET strawberry_balance = 0 WHERE username = ?", (user,))
    classifications = _stub_level(monkeypatch, "high")
    routes = _route_spies(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": ORDINARY,
    }))
    _assert_resource_once(events, "high")
    assert classifications == [ORDINARY]
    assert routes["model"] == routes["detect"] == routes["recognize"] == []
    assert _balance(user) == 0
    assert asyncio.run(database.get_messages(user, conversation_id=conversation)) == []
    assert events[-1] == {"done": True}


def test_validation_error_model_possible_sends_resource_before_error(
    client, dev_headers, monkeypatch,
):
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    classifications = _stub_level(monkeypatch, "possible")
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": ORDINARY, "mode": "image_edit",
    }))
    assert classifications == [ORDINARY]
    _assert_resource_once(events, "possible")
    assert safety.CRISIS_RESOURCE_NOTE in events[0]["text"]
    assert events[-1].get("error")
    assert _balance(user) == before


@pytest.mark.parametrize("failure", ["reservation", "not_found", "context_http", "context_runtime"])
def test_precheck_error_model_possible_sends_resource_and_restores_balance(
    client, dev_headers, monkeypatch, failure,
):
    from agent_store import ResourceNotFound
    from fastapi import HTTPException
    import routers.chat as router

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    classifications = _stub_level(monkeypatch, "possible")
    routes = _route_spies(monkeypatch)

    async def fail(*args, **kwargs):
        if failure == "not_found":
            raise ResourceNotFound()
        if failure == "context_http":
            raise HTTPException(status_code=409, detail="单元测试中的失效会话")
        raise RuntimeError("stub precheck failure")

    monkeypatch.setattr(router, "reserve_strawberries" if failure == "reservation" else "build_context", fail)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": ORDINARY,
    }))
    assert classifications == [ORDINARY]
    _assert_resource_once(events, "possible")
    assert safety.CRISIS_RESOURCE_NOTE in events[0]["text"]
    assert events[-1].get("error")
    assert routes["model"] == []
    assert _balance(user) == before


def _handler_request():
    return Request({
        "type": "http", "method": "POST", "path": "/chat", "headers": [],
        "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 80),
    })


def test_reservation_and_context_overlap_model_review(monkeypatch):
    import routers.chat as router

    monkeypatch.setenv("DEV_MODE", "0")

    async def scenario():
        started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        overlapping = []

        async def classify(text):
            started.set()
            await release.wait()
            finished.set()
            return "high"

        async def reserve(*args):
            await asyncio.wait_for(started.wait(), 1)
            assert not finished.is_set()
            overlapping.append("reserve")
            return 40

        async def build(*args, **kwargs):
            await asyncio.wait_for(started.wait(), 1)
            assert not finished.is_set()
            overlapping.append("context")
            release.set()
            return SimpleNamespace()

        async def run(ctx, *, crisis, **kwargs):
            assert finished.is_set()
            assert crisis == "high"
            yield 'data: {"done": true}\n\n'

        monkeypatch.setattr(crisis_model, "classify", classify)
        monkeypatch.setattr(router, "reserve_strawberries", reserve)
        monkeypatch.setattr(router, "build_context", build)
        monkeypatch.setattr(router, "run_chat", run)
        response = await asyncio.wait_for(inspect.unwrap(router.chat)(
            _handler_request(), router.ChatRequest(message=ORDINARY), "unit_tester",
        ), 2)
        assert overlapping == ["reserve", "context"]
        assert [event async for event in response.body_iterator] == ['data: {"done": true}\n\n']

    asyncio.run(scenario())


def test_cancel_after_reservation_and_context_refunds_while_waiting_for_model(
    client, dev_headers, monkeypatch,
):
    import database
    import routers.chat as router

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    monkeypatch.setenv("DEV_MODE", "0")
    refund = router.refund_strawberries
    refunds = []

    async def observed_refund(username, amount):
        refunds.append((username, amount))
        return await refund(username, amount)

    monkeypatch.setattr(router, "refund_strawberries", observed_refund)

    async def scenario():
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        unhandled = []
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
        model_started, model_cancelled, assembled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        model_tasks = []

        async def classify(text):
            model_tasks.append(asyncio.current_task())
            model_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                model_cancelled.set()

        async def build(*args, **kwargs):
            await model_started.wait()
            assembled.set()
            return SimpleNamespace()

        monkeypatch.setattr(crisis_model, "classify", classify)
        monkeypatch.setattr(router, "build_context", build)
        try:
            task = asyncio.create_task(inspect.unwrap(router.chat)(
                _handler_request(), router.ChatRequest(message=ORDINARY, conversation_id=conversation), user,
            ))
            await asyncio.wait_for(assembled.wait(), 1)
            assert not task.done()
            assert await database.get_strawberry_balance(user) == before - 10
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert refunds == [(user, 10)]
            assert await database.get_strawberry_balance(user) == before
            assert model_cancelled.is_set()
            assert len(model_tasks) == 1
            assert model_tasks[0].cancelled()
            gc.collect()
            await asyncio.sleep(0)
            assert unhandled == []
        finally:
            loop.set_exception_handler(previous_handler)

    asyncio.run(scenario())
    assert _balance(user) == before


@pytest.mark.parametrize("exit_kind", ["fatal_precheck", "request_cancelled", "already_failed_model"])
def test_early_request_exit_cancels_or_retrieves_model_task(monkeypatch, exit_kind):
    import routers.chat as router

    class FatalPrecheck(BaseException):
        pass

    monkeypatch.setenv("DEV_MODE", "1")

    async def scenario():
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        unhandled = []
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
        started, cancelled, context_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        model_tasks = []

        async def classify(text):
            model_tasks.append(asyncio.current_task())
            started.set()
            if exit_kind == "already_failed_model":
                raise RuntimeError("stub classifier failure")
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def build(*args, **kwargs):
            await started.wait()
            context_started.set()
            if exit_kind == "request_cancelled":
                await asyncio.Event().wait()
            await asyncio.sleep(0)
            raise FatalPrecheck()

        monkeypatch.setattr(crisis_model, "classify", classify)
        monkeypatch.setattr(router, "build_context", build)
        try:
            request_task = asyncio.create_task(inspect.unwrap(router.chat)(
                _handler_request(), router.ChatRequest(message=ORDINARY), "unit_tester",
            ))
            await asyncio.wait_for(context_started.wait(), 1)
            if exit_kind == "request_cancelled":
                request_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request_task
            else:
                with pytest.raises(FatalPrecheck):
                    await request_task
            assert len(model_tasks) == 1
            model_task = model_tasks.pop()
            assert model_task.done()
            if exit_kind == "already_failed_model":
                # asyncio marks this false once the completed task's exception
                # has been retrieved; inspecting it does not retrieve the error.
                assert model_task._log_traceback is False
            else:
                assert model_task.cancelled()
                assert cancelled.is_set()
            del model_task
            gc.collect()
            await asyncio.sleep(0)
            assert unhandled == []
        finally:
            loop.set_exception_handler(previous_handler)

    asyncio.run(scenario())


@pytest.mark.parametrize("message,with_image", [("", True), (" \n\t", True), ("", False), (" \n\t", False)])
def test_image_only_and_empty_chat_do_not_call_classifier(
    client, dev_headers, monkeypatch, message, with_image,
):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    classifications = _stub_level(monkeypatch, "high")
    monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: FakeStream())),
    ))
    payload = {"conversation_id": conversation, "message": message}
    if with_image:
        payload["image_base64"] = IMAGE
    response = client.post("/chat", headers=dev_headers, json=payload)
    if with_image:
        assert _events(response)[-1] == {"done": True}
    else:
        assert response.status_code == 400
    assert classifications == []


def test_http_transport_limits_timeout_and_reuse(monkeypatch):
    transports = []
    transport = SimpleNamespace()

    def http_client(**kwargs):
        transports.append(kwargs)
        return transport

    monkeypatch.setattr(crisis_model.httpx, "AsyncClient", http_client)
    calls = _stub_provider(monkeypatch)

    async def scenario():
        monkeypatch.setenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", "0.75")
        assert await crisis_model.classify("第一条测试消息") == "none"
        monkeypatch.setenv("FIONA_CRISIS_MODEL_TIMEOUT_SECONDS", "3.5")
        assert await crisis_model.classify("第二条测试消息") == "none"

    asyncio.run(scenario())
    assert len(transports) == len(calls["clients"]) == 1
    assert calls["clients"][0]["http_client"] is transport
    assert transports[0]["timeout"] == 0.75
    limits = transports[0]["limits"]
    assert limits.max_connections == 20
    assert limits.max_keepalive_connections == 10
    assert limits.keepalive_expiry == 120
    assert [request["timeout"] for request in calls["requests"]] == [0.75, 3.5]


def test_8000_character_message_preserves_crisis_sentence_at_end(monkeypatch):
    calls = _stub_provider(monkeypatch)
    crisis_sentence = "我现在想伤害自己，今晚打算结束生命。"
    text = "今天的经历。" * 1600
    text = text[:8000 - len(crisis_sentence)] + crisis_sentence
    assert len(text) == 8000
    assert asyncio.run(crisis_model.classify(text)) == "none"
    submitted = calls["requests"][0]["messages"][1]["content"]
    assert submitted == text[:1000] + "……" + text[-1000:]
    assert len(submitted) == 2002
    assert submitted.endswith(crisis_sentence)


@pytest.mark.parametrize("length", [2000, 2001])
def test_classifier_head_tail_threshold(monkeypatch, length):
    calls = _stub_provider(monkeypatch)
    text = "始" + "中" * (length - 2) + "终"
    assert asyncio.run(crisis_model.classify(f" \n{text}\t ")) == "none"
    submitted = calls["requests"][0]["messages"][1]["content"]
    expected = text if length == 2000 else text[:1000] + "……" + text[-1000:]
    assert submitted == expected
    assert len(submitted) == (2000 if length == 2000 else 2002)


@pytest.mark.parametrize("level", ["HIGH", " high "])
def test_classifier_normalizes_level_case_and_whitespace(monkeypatch, capsys, level):
    _stub_provider(monkeypatch, content=json.dumps({"level": level}))
    assert asyncio.run(crisis_model.classify("仅供解析测试的消息")) == "high"
    assert re.fullmatch(r"\[crisis-model\] level=high ms=\d+(?:\.\d+)?\n", capsys.readouterr().out)


def test_validation_error_classifier_raises_still_sends_rule_resource_first(
    client, dev_headers, monkeypatch, capsys,
):
    assert safety.assess_crisis(POSSIBLE) == "possible"
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = []

    async def classify(text):
        calls.append(text)
        raise RuntimeError("stub classifier failure")

    monkeypatch.setattr(crisis_model, "classify", classify)
    headers = _production_headers(monkeypatch, user)
    capsys.readouterr()
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": POSSIBLE, "mode": "image_edit",
    }))
    assert calls == [POSSIBLE]
    _assert_resource_once(events, "possible")
    assert safety.CRISIS_RESOURCE_NOTE in events[0]["text"]
    assert events[-1] == {"error": "请先上传参考图，或在生成的图片上点击「以此图修改」"}
    assert _balance(user) == before
    output = capsys.readouterr().out
    logs = [line for line in output.splitlines() if line.startswith("[crisis-model]")]
    assert len(logs) == 1
    assert re.fullmatch(r"\[crisis-model\] failed type=RuntimeError ms=\d+(?:\.\d+)?", logs[0])
    assert POSSIBLE not in output
    assert "stub classifier failure" not in output


def test_classifier_cancellation_propagates_from_final_crisis(monkeypatch):
    import routers.chat as router

    async def classify(text):
        raise asyncio.CancelledError()

    monkeypatch.setattr(crisis_model, "classify", classify)

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await inspect.unwrap(router.chat)(
                _handler_request(), router.ChatRequest(message=POSSIBLE, mode="image_edit"), "unit_tester",
            )

    asyncio.run(scenario())
