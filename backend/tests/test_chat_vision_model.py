# -*- coding: utf-8 -*-
"""聊天看图模型配置的离线回归测试。"""
import json
import logging

import pytest

from _fakes import FakeStream


# 1x1 PNG，必须能通过 Pillow 的完整 CRC/结构校验。
_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)


def _events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def _capture_requests(monkeypatch):
    import services.chat_service as chat

    captured = []

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.append(kwargs)
            return FakeStream()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeQwen:
        chat = _FakeChat()

    monkeypatch.setattr(chat, "QWEN_CLIENT", _FakeQwen())
    return captured


def _post_image(client, dev_headers):
    response = client.post(
        "/chat",
        json={"message": "这是啥", "image_base64": f"data:image/png;base64,{_TINY_PNG}"},
        headers=dev_headers,
    )
    assert response.status_code == 200
    return _events(response.text)


@pytest.mark.parametrize("value", ["qwen3-vl-plus", "  qwen3-vl-plus  "])
def test_chat_vision_model_override(client, dev_headers, monkeypatch, value):
    monkeypatch.setenv("FIONA_CHAT_VISION_MODEL", value)
    captured = _capture_requests(monkeypatch)

    events = _post_image(client, dev_headers)

    assert any(event.get("text") for event in events)
    assert any(event.get("done") for event in events)
    assert captured[0]["model"] == "qwen3-vl-plus"
    assert captured[0]["extra_body"] == {"enable_thinking": False}


@pytest.mark.parametrize("value", [None, "", "   "])
def test_chat_vision_model_empty_uses_default_without_warning(
    client, dev_headers, monkeypatch, caplog, value,
):
    if value is None:
        monkeypatch.delenv("FIONA_CHAT_VISION_MODEL", raising=False)
    else:
        monkeypatch.setenv("FIONA_CHAT_VISION_MODEL", value)
    import services.chat_service as chat
    monkeypatch.setattr(chat, "_CHAT_VISION_ENV_WARNED", False)
    captured = _capture_requests(monkeypatch)

    with caplog.at_level(logging.WARNING, logger=chat.__name__):
        events = _post_image(client, dev_headers)

    assert any(event.get("done") for event in events)
    assert captured[0]["model"] == "qwen3.8-omni-flash"
    assert captured[0]["extra_body"] == {"enable_thinking": False}
    assert not any("FIONA_CHAT_VISION_MODEL" in record.message for record in caplog.records)


@pytest.mark.parametrize("value", ["bad model", "qwen\nx", "../x", "a" * 65, "中文", "qwen/x"])
def test_chat_vision_model_invalid_falls_back_and_warns_once(monkeypatch, caplog, value):
    monkeypatch.setenv("FIONA_CHAT_VISION_MODEL", value)
    import services.chat_service as chat
    monkeypatch.setattr(chat, "_CHAT_VISION_ENV_WARNED", False)

    with caplog.at_level(logging.WARNING, logger=chat.__name__):
        assert chat._chat_vision_model() == "qwen3.8-omni-flash"
        assert chat._chat_vision_model() == "qwen3.8-omni-flash"

    warnings = [record for record in caplog.records if "FIONA_CHAT_VISION_MODEL" in record.message]
    assert len(warnings) == 1
    assert warnings[0].message == "FIONA_CHAT_VISION_MODEL 非法值，按默认 qwen3.8-omni-flash 处理"
    assert value not in warnings[0].message


def test_chat_vision_model_accepts_64_char_boundary(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_VISION_MODEL", "a" * 64)
    import services.chat_service as chat

    assert chat._chat_vision_model() == "a" * 64


def test_chat_vision_model_reads_env_each_request(client, dev_headers, monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_VISION_MODEL", "qwen3-vl-plus")
    captured = _capture_requests(monkeypatch)

    first_events = _post_image(client, dev_headers)
    monkeypatch.setenv("FIONA_CHAT_VISION_MODEL", "qwen3-vl-flash")
    second_events = _post_image(client, dev_headers)

    assert any(event.get("done") for event in first_events)
    assert any(event.get("done") for event in second_events)
    assert [request["model"] for request in captured] == ["qwen3-vl-plus", "qwen3-vl-flash"]


def test_chat_vision_model_upstream_error(client, dev_headers, monkeypatch, capsys):
    monkeypatch.delenv("FIONA_CHAT_VISION_MODEL", raising=False)
    import services.chat_service as chat

    class _FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("fake vision failure")

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeQwen:
        chat = _FakeChat()

    monkeypatch.setattr(chat, "QWEN_CLIENT", _FakeQwen())

    events = _post_image(client, dev_headers)

    assert any(event.get("error") for event in events)
    output = capsys.readouterr().out
    assert "[chat] vision model=qwen3.8-omni-flash error type=RuntimeError" in output
    assert "qwen-vl-max" not in output


def test_chat_vision_model_constants(monkeypatch):
    monkeypatch.delenv("FIONA_CHAT_VISION_MODEL", raising=False)
    import llm

    assert llm.CHAT_VISION_MODEL_DEFAULT == "qwen3.8-omni-flash"
    assert llm.CHAT_VISION_MODEL_ENV == "FIONA_CHAT_VISION_MODEL"
