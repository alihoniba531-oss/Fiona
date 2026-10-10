"""Offline R1 planner contracts: request shape, bounded input and safe outcomes."""
import asyncio
import hashlib
import json
import logging
import re
import socket
import threading
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from services import image_tool


EXPECTED_PROMPT = """你是生图意图判断器。阅读对话（最后一条是主人刚说的话），判断主人这一句是否要求「现在生成一张图片」。
要求生成图片的情形：明确让你画/生成图片/出图/生成照片；让你把之前出现的描述或提示词画出来；让你在之前的描述上修改风格或内容后再画。
不算的情形：只要提示词或文案；讨论、比较、询问生图模型、价格或用法；评价已有图片；只是提到自己画画。
如果要生成，把要画的内容整理成一段完整、具体的画面描述（可沿用之前的英文提示词原文并按要求修改），不得写入账号名、真实姓名或私人细节。
只输出 JSON：{"draw": true或false, "prompt": "画面描述或空串", "model": "seedream-5.0-flash" 或 "qwen-image-3.0" 或 null（仅当主人点名：Seedream/豆包/即梦→seedream-5.0-flash；千问/通义/Qwen→qwen-image-3.0）, "aspect_ratio": "1:1"/"16:9"/"9:16" 或 null}"""
EXPECTED_PREFILTER = "画|绘|图|照片|相片|生成|出一张|来一张|风格|.风[。！!？?…～~]?$|提示词|prompt|seedream|即梦|豆包|千问|通义|qwen|draw|image|picture|photo|render|海报|壁纸|插画|头像"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-planner-key")
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("real network request")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def install_client(monkeypatch, content, *, error=None, request=None):
    options, calls, closed = [], [], []

    def create(**kwargs):
        calls.append(kwargs)
        if request is not None:
            return request(**kwargs)
        if error is not None:
            raise error
        return NS(choices=[NS(message=NS(content=content))])

    derived = NS(chat=NS(completions=NS(create=create)), close=lambda: closed.append(True))

    def with_options(**kwargs):
        options.append(kwargs)
        return derived

    monkeypatch.setattr(image_tool, "QWEN_CLIENT", NS(with_options=with_options), raising=False)
    return options, calls, closed


def run_plan(history=(), message="画一只猫"):
    return asyncio.run(image_tool.plan_image(list(history), message))


def test_planner_constants_are_r1_verbatim():
    assert image_tool.IMAGE_PLANNER_PROMPT == EXPECTED_PROMPT
    assert image_tool.IMAGE_PLANNER_PREFILTER_PATTERN == EXPECTED_PREFILTER
    assert image_tool.IMAGE_PLANNER_PREFILTER.pattern == EXPECTED_PREFILTER
    assert image_tool.IMAGE_PLANNER_PREFILTER.flags & re.IGNORECASE


@pytest.mark.parametrize("message", ["画一只猫", "生成", "来一张", "改成动漫风。", "变成油画风！", "换成新风", "PROMPT", "Seedream", "QWEN", "Render a cat", "image", "头像"])
def test_prefilter_recall(message):
    assert image_tool.image_planner_prescreen(message)


@pytest.mark.parametrize("message", ["你好", "明天北京天气", "今天想休息", "动漫模式讨论"])
def test_prefilter_miss_and_explicit_override(message):
    assert not image_tool.image_planner_prescreen(message)
    assert image_tool.image_planner_prescreen(message, explicit=True)


def test_planner_uses_existing_light_client_json_no_retry_and_never_closes_shared_transport(monkeypatch):
    options, calls, closed = install_client(monkeypatch, '{"draw":true,"prompt":"  一只猫  ","model":"qwen-image-3.0","aspect_ratio":"16:9"}')
    assert run_plan() == {"status": "draw", "prompt": "一只猫", "model": "qwen-image-3.0", "aspect_ratio": "16:9"}
    assert options == [{"timeout": 8.0, "max_retries": 0}]
    assert len(calls) == 1
    assert calls[0] == {
        "model": "qwen3.8-flash", "stream": False, "max_tokens": 600,
        "response_format": {"type": "json_object"}, "extra_body": {"enable_thinking": False},
        "messages": [{"role": "system", "content": EXPECTED_PROMPT}, {"role": "user", "content": "主人：画一只猫"}],
    }
    assert closed == []


def test_input_is_last_six_chronological_messages_history_600_current_preserved(monkeypatch):
    _, calls, _ = install_client(monkeypatch, '{"draw":false,"prompt":""}')
    history = [{"role": "user" if index % 2 == 0 else "assistant", "content": str(index) + "文" * 800} for index in range(9)]
    history[-1]["content"] = "图片已生成。\n\n使用的描述（Seedream 5.0 Flash）：A cozy cat"
    original = deepcopy(history)
    current = "画" * 900
    assert run_plan(history, current) == {"status": "no"}
    text = calls[0]["messages"][1]["content"]
    expected = [("主人：" if row["role"] == "user" else "你：") + row["content"][:600] for row in history[-5:]]
    assert text == "\n".join(expected + ["主人：" + current])
    assert "使用的描述（Seedream 5.0 Flash）：A cozy cat" in text
    assert history == original


@pytest.mark.parametrize("length", [600, 601, 1499, 1500])
def test_current_message_at_most_1500_is_preserved_in_full(monkeypatch, length):
    _, calls, _ = install_client(monkeypatch, '{"draw":false}')
    current = "a" * (length - len("用 Seedream 画出来")) + "用 Seedream 画出来"
    assert len(current) == length
    assert run_plan(message=current) == {"status": "no"}
    assert calls[0]["messages"][1]["content"] == "主人：" + current


@pytest.mark.parametrize("length", [1501, 2400])
def test_long_current_message_retains_first_1000_and_last_500(monkeypatch, length):
    _, calls, _ = install_client(monkeypatch, '{"draw":false}')
    current = "FIRST_PRIVATE_PROMPT_R2" + "a" * (length - len("FIRST_PRIVATE_PROMPT_R2") - len("用 Seedream 画出来")) + "用 Seedream 画出来"
    assert len(current) == length
    assert run_plan(message=current) == {"status": "no"}
    assert calls[0]["messages"][1]["content"] == "主人：" + current[:1000] + "……" + current[-500:]


def test_input_excludes_system_history_and_always_ends_with_current_user(monkeypatch):
    _, calls, _ = install_client(monkeypatch, '{"draw":false}')
    assert run_plan([{"role": "system", "content": "人设不可发送"}, {"role": "assistant", "content": "上文提示词"}], "现在画") == {"status": "no"}
    assert calls[0]["messages"][1]["content"] == "你：上文提示词\n主人：现在画"


@pytest.mark.parametrize("model,ratio", [("seedream-5.0-flash", "1:1"), ("qwen-image-3.0", "9:16")])
def test_valid_optional_arguments_adopted(monkeypatch, model, ratio):
    install_client(monkeypatch, json.dumps({"draw": True, "prompt": "英文 prompt", "model": model, "aspect_ratio": ratio}))
    assert run_plan() == {"status": "draw", "prompt": "英文 prompt", "model": model, "aspect_ratio": ratio}


@pytest.mark.parametrize("model,ratio", [("unknown", "3:2"), (None, None), (["qwen-image-3.0"], {"ratio": "1:1"}), (False, 1)])
def test_invalid_optional_arguments_ignored(monkeypatch, model, ratio):
    install_client(monkeypatch, json.dumps({"draw": True, "prompt": "猫", "model": model, "aspect_ratio": ratio}))
    assert run_plan() == {"status": "draw", "prompt": "猫"}


@pytest.mark.parametrize("value", [{"draw": False}, {"draw": False, "prompt": ""}, {"draw": False, "prompt": "文" * 1501}])
def test_false_decision_does_not_require_prompt(monkeypatch, value):
    install_client(monkeypatch, json.dumps(value))
    assert run_plan() == {"status": "no"}


@pytest.mark.parametrize("content", ["not JSON", "[]", "null", "3", '{"draw":1,"prompt":"猫"}', '{"draw":"true","prompt":"猫"}', '{"draw":null}', '{}', '{"draw":true,"prompt":""}', '{"draw":true,"prompt":"  "}', json.dumps({"draw": True, "prompt": "文" * 1501}), '{"draw":true,"prompt":null}', '{"draw":true,"prompt":12}', '{"draw":true,"prompt":"猫","model":NaN}'])
def test_invalid_planner_result_is_unavailable_without_content_leak(monkeypatch, caplog, content):
    private_marker = "PRIVATE_PLANNER_CASE_R2_" + hashlib.sha256(content.encode()).hexdigest()
    options, calls, _ = install_client(monkeypatch, content)
    with caplog.at_level(logging.WARNING):
        result = run_plan(message=private_marker)
    assert set(result) == {"status", "exception_type", "elapsed_ms"}
    assert result["status"] == "error"
    assert result["exception_type"] in {"ValueError", "JSONDecodeError"}
    assert isinstance(result["elapsed_ms"], int) and result["elapsed_ms"] >= 0
    assert private_marker not in caplog.text
    planner_logs = [record for record in caplog.records if record.name == image_tool.__name__]
    assert len(planner_logs) == 1
    assert planner_logs[0].msg == "image_planner exception_type=%s elapsed_ms=%s"
    assert planner_logs[0].args == (result["exception_type"], result["elapsed_ms"])
    assert "猫" not in caplog.text
    assert len(options) == len(calls) == 1


@pytest.mark.parametrize("error", [TimeoutError("主人私密原话画猫"), RuntimeError("服务端敏感描述猫")])
def test_exception_or_provider_timeout_is_unavailable_one_call_no_leak(monkeypatch, caplog, error):
    options, calls, _ = install_client(monkeypatch, None, error=error)
    with caplog.at_level(logging.WARNING):
        result = run_plan(message="主人私密原话")
    assert result["status"] == "error" and result["exception_type"] == type(error).__name__
    assert "主人私密原话" not in caplog.text and str(error) not in caplog.text
    assert "elapsed_ms=" in caplog.text
    assert len(options) == len(calls) == 1


def test_planner_request_runs_in_thread_without_blocking_event_loop(monkeypatch):
    main_thread = threading.get_ident()
    worker_threads = []
    entered, release = threading.Event(), threading.Event()

    def request(**kwargs):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        return NS(choices=[NS(message=NS(content='{"draw":false}'))])

    install_client(monkeypatch, None, request=request)

    async def scenario():
        task = asyncio.create_task(image_tool.plan_image([], "画猫"))
        try:
            for _ in range(1000):
                await asyncio.sleep(0)
                if entered.is_set():
                    break
            assert entered.is_set() and not task.done()
        finally:
            release.set()
        assert await task == {"status": "no"}

    asyncio.run(scenario())
    assert worker_threads and worker_threads[0] != main_thread


def test_single_total_deadline_returns_before_blocked_worker_without_retry(monkeypatch):
    release = threading.Event()

    def request(**kwargs):
        release.wait(2)
        return NS(choices=[NS(message=NS(content='{"draw":true,"prompt":"猫"}'))])

    options, calls, _ = install_client(monkeypatch, None, request=request)
    monkeypatch.setattr(image_tool, "IMAGE_PLANNER_TIMEOUT_SECONDS", 0.01, raising=False)

    async def scenario():
        try:
            result = await image_tool.plan_image([], "画猫")
            assert result["status"] == "error" and result["exception_type"] == "TimeoutError"
            assert result["elapsed_ms"] < 1000
            assert not release.is_set()
        finally:
            release.set()

    asyncio.run(scenario())
    assert len(options) == len(calls) == 1


def test_task_cancellation_propagates_instead_of_routing_as_planner_error(monkeypatch):
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "to_thread", cancelled)
    with pytest.raises(asyncio.CancelledError):
        run_plan()
