# -*- coding: utf-8 -*-
"""
/chat 五条分支 + 硬词注入的黑盒回归测试。

这些测试在 Stage 2 拆 chat_service 之前先对现有 routers/chat.py 跑绿，
拆完后必须依然绿 —— 它们钉的是端点的可观察行为，不依赖内部结构，
所以是「拆服务层」这步重构的安全网。
"""
import base64
import json

import intent_router

# 1x1 透明 PNG，喂给图片分支（_save_uploaded_image 会嗅探 magic bytes）
_TINY_PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)).decode()


def _events(body: str) -> list[dict]:
    """把 SSE 文本拆成 data: JSON 事件列表。"""
    out = []
    for line in body.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _has_text(events) -> bool:
    return any(e.get("text") for e in events)


def _has_done(events) -> bool:
    return any(e.get("done") for e in events)


def test_chat_mirror_branch(client, dev_headers, monkeypatch):
    """mode=mirror → 简化 persona 流式回复，跳过意图/工具。"""
    import services.chat_service as chat
    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
    r = client.post("/chat", json={"message": "我好累"}, headers=dev_headers)
    assert r.status_code == 200
    events = _events(r.text)
    assert _has_text(events) and _has_done(events)


def test_chat_image_branch(client, dev_headers, monkeypatch):
    """带图片 → 走 qwen-vl-max 看图分支（直接用 QWEN_CLIENT）。"""
    import services.chat_service as chat
    from _fakes import FakeStream

    captured = {}

    class _FakeCompletions:
        def create(self, **k):
            captured.update(k)
            return FakeStream()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeQwen:
        chat = _FakeChat()

    monkeypatch.setattr(chat, "QWEN_CLIENT", _FakeQwen())
    r = client.post(
        "/chat",
        # 故意伪报 jpeg；后端必须按魔数规范化成 png 后再交给视觉模型。
        json={"message": "这是啥", "image_base64": f"data:image/jpeg;base64,{_TINY_PNG}"},
        headers=dev_headers,
    )
    assert r.status_code == 200
    events = _events(r.text)
    assert _has_text(events) and _has_done(events)
    image_url = captured["messages"][1]["content"][0]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_chat_rejects_invalid_image_before_visual_model(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    class _MustNotRun:
        def create(self, **kwargs):
            raise AssertionError("visual model must not receive an invalid image")

    monkeypatch.setattr(
        chat,
        "QWEN_CLIENT",
        type("Fake", (), {"chat": type("Chat", (), {"completions": _MustNotRun()})()})(),
    )
    response = client.post(
        "/chat",
        json={"message": "看看", "image_base64": "data:image/png;base64,not-valid***"},
        headers=dev_headers,
    )

    assert response.status_code == 400
    assert "base64" in response.json()["detail"]


def test_chat_rejects_message_over_limit(client, dev_headers):
    response = client.post(
        "/chat",
        json={"message": "字" * 8001},
        headers=dev_headers,
    )
    assert response.status_code == 422


def test_chat_pending_branch(client, dev_headers, monkeypatch):
    """已有 pending intent → 补全参数后执行（fill_param 真跑，execute_intent 打桩）。"""
    import services.chat_service as chat
    intent_router.set_pending(
        "smoke_tester",
        {"intent": "set_reminder", "params": {"text": "喝水"}, "missing": ["minutes"]},
    )
    monkeypatch.setattr(
        chat, "execute_intent",
        lambda intent, params: f"好，{params.get('minutes')}分钟后提醒你喝水",
    )
    try:
        r = client.post("/chat", json={"message": "30"}, headers=dev_headers)
        assert r.status_code == 200
        events = _events(r.text)
        assert any("30分钟后提醒你喝水" in (e.get("text") or "") for e in events)
        assert _has_done(events)
    finally:
        intent_router.clear_pending("smoke_tester")


def test_chat_intent_text(client, dev_headers, monkeypatch):
    """意图识别命中文本型工具 → 直接执行并回文本。"""
    import services.chat_service as chat
    monkeypatch.setattr(
        chat, "recognize_intent",
        lambda *a, **k: {"intent": "get_datetime", "params": {}, "missing": []},
    )
    monkeypatch.setattr(chat, "execute_intent", lambda i, p: "现在是下午三点")
    r = client.post("/chat", json={"message": "几点了"}, headers=dev_headers)
    assert r.status_code == 200
    events = _events(r.text)
    assert any("现在是下午三点" in (e.get("text") or "") for e in events)
    assert _has_done(events)


def test_chat_intent_card(client, dev_headers, monkeypatch):
    """意图识别命中卡片型工具 → 走专门的 card SSE 事件。"""
    import services.chat_service as chat
    monkeypatch.setattr(
        chat, "recognize_intent",
        lambda *a, **k: {"intent": "fetch_card", "params": {"query": "北京天气"}, "missing": []},
    )
    monkeypatch.setattr(
        chat, "execute_intent",
        lambda i, p: {
            "type": "card", "subtype": "weather", "source": "天气",
            "weather": {"location": "北京", "currentTemp": 20, "condition": "晴",
                        "feelsLike": 19, "forecast": []},
        },
    )
    r = client.post("/chat", json={"message": "北京天气"}, headers=dev_headers)
    assert r.status_code == 200
    events = _events(r.text)
    assert any(e.get("card") for e in events)
    assert _has_done(events)


def test_chat_hard_word_injection(client, dev_headers, monkeypatch):
    """消息含硬词（必须）→ system prompt 里被注入即时引导块。"""
    import services.chat_service as chat
    from _fakes import FakeStream
    captured = {}

    def _recorder(use_qwen, messages, **k):
        captured["messages"] = messages
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", _recorder)
    r = client.post("/chat", json={"message": "我必须做成这件事"}, headers=dev_headers)
    assert r.status_code == 200
    sys_prompt = captured["messages"][0]["content"]
    assert "硬词" in sys_prompt or "即时引导" in sys_prompt
