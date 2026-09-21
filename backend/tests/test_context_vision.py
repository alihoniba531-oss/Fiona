# -*- coding: utf-8 -*-
"""T2 验收：视觉分支拼历史（T2a）+ 图片摘要落库/注入/前端不受影响（T2b）。

对应规格 docs/tasks/2026-09-10-聊天上下文优化-P0P1/02-spec.md §4.2 的 5 条覆盖：
  1. T2a 长度（含"空历史 → 2 条"正控）
  2. T2a 隔离（历史不得混进多模态结构）
  3. T2b 写入（image_summary 非空且 ≤ 120 字符）
  4. T2b 注入（含"ctx.history 未被污染"正控）
  5. T2b 前端不受影响（/conversations/{id}/messages 的 content 原样）
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from _fakes import FakeStream

# 1x1 PNG，样本必须能通过 Pillow 的完整 CRC/结构校验。
# 常量复制自 tests/test_chat_branches.py —— 既有测试文件不得修改，故此处各持一份。
_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)

# VL 本轮的回复文本，同时被复用为图片摘要（不得为此额外调用模型）。
_SUMMARY = "图里是一只橘猫趴在窗台上晒太阳"
_USER_TEXT = "这是啥"
# 全角括号，与既有的半角占位符 [发了一张图片] 区分开，便于精确 grep。
_IMAGE_MARK = "［图中："
_SEEDED = [f"历史第{i}条" for i in range(12)]


@pytest.fixture(autouse=True)
def _isolate_chat_rate_limit(monkeypatch):
    """视觉用例要连发多次 /chat，不与其他模块共享每分钟配额。"""
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _events(response):
    """把 SSE 文本拆成事件列表，顺带断言这一轮没有报错、正常收尾。"""
    assert response.status_code == 200, response.text
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert not any(event.get("error") for event in events), events
    assert any(event.get("done") for event in events), events
    return events


def _new_conversation(client, headers, title):
    response = client.post("/conversations", json={"title": title}, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["conversation"]["id"]


def _install_fake_vl(monkeypatch, summary=_SUMMARY):
    """打桩视觉模型：逐次记录送进 VL 的 messages，并回一段固定文本当回复/摘要。"""
    import services.chat_service as chat

    calls = []

    class _FakeCompletions:
        def create(self, **kwargs):
            # 逐条浅拷贝，锁住本轮实际出网的 payload，后续轮次改不到它。
            calls.append([dict(message) for message in kwargs["messages"]])
            return FakeStream(chunks=[(summary, "stop")])

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeQwen:
        chat = _FakeChat()

    monkeypatch.setattr(chat, "QWEN_CLIENT", _FakeQwen())
    return calls


def _post_image(client, headers, conversation_id, message=_USER_TEXT):
    return client.post(
        "/chat",
        json={
            "message": message,
            "image_base64": f"data:image/png;base64,{_TINY_PNG}",
            "conversation_id": conversation_id,
        },
        headers=headers,
    )


def _seed_history(user, conversation_id, contents):
    """直接落库灌历史；内容必须都非空，否则会被"跳过空 content"规则吃掉。"""
    import database

    async def _write():
        for content in contents:
            assert await database.save_message(
                user, "user", content, conversation_id=conversation_id,
            )

    asyncio.run(_write())


def _image_rows(user, conversation_id):
    """库里带图的那条 user 消息（get_messages 的返回含 image_summary 键）。"""
    import database

    rows = asyncio.run(database.get_messages(user, conversation_id=conversation_id))
    return [row for row in rows if row.get("image_path")]


def test_visual_branch_attaches_last_ten_history_turns(client, dev_headers, monkeypatch):
    """§4.2-1 + §4.2-2：拼最近 10 条历史，且历史必须是纯文本。"""
    calls = _install_fake_vl(monkeypatch)
    user = dev_headers["X-Dev-User"]

    # 正控：历史为空时退化回原来的两条。若两种情况长度相同，说明历史根本没拼进去。
    empty_conversation = _new_conversation(client, dev_headers, "空历史")
    _events(_post_image(client, dev_headers, empty_conversation))
    assert len(calls[0]) == 2
    assert calls[0][0]["role"] == "system"
    assert calls[0][-1]["role"] == "user"
    assert isinstance(calls[0][-1]["content"], list)

    # 12 条历史 → 1 (system) + 10 (history) + 1 (当前多模态 user) = 12
    conversation = _new_conversation(client, dev_headers, "带历史")
    _seed_history(user, conversation, _SEEDED)
    _events(_post_image(client, dev_headers, conversation))

    sent = calls[1]
    assert len(sent) == 1 + 10 + 1 == 12
    assert sent[0]["role"] == "system"
    history_turns = sent[1:-1]
    # 第 2 条（下标 1）= 历史倒数第 10 条
    assert history_turns[0]["content"] == _SEEDED[-10]
    assert [turn["content"] for turn in history_turns] == _SEEDED[-10:]
    assert {turn["role"] for turn in history_turns} == {"user"}
    # 最后一条仍是本轮的多模态 user（图片 + 当前文字）
    assert sent[-1]["role"] == "user"
    assert isinstance(sent[-1]["content"], list)
    assert sent[-1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert sent[-1]["content"][1]["text"] == _USER_TEXT
    # §4.2-2 隔离：10 条历史里没有任何一条混进多模态结构
    assert not any(isinstance(turn["content"], list) for turn in history_turns)


def test_visual_reply_is_persisted_as_image_summary(client, dev_headers, monkeypatch):
    """§4.2-3：走完视觉分支后，该 user 消息行的 image_summary 非空且 ≤ 120 字符。"""
    _install_fake_vl(monkeypatch)
    user = dev_headers["X-Dev-User"]
    conversation = _new_conversation(client, dev_headers, "摘要落库")

    _events(_post_image(client, dev_headers, conversation))

    rows = _image_rows(user, conversation)
    assert len(rows) == 1
    summary = rows[0]["image_summary"]
    assert summary and summary.strip()
    assert summary == _SUMMARY
    assert len(summary) <= 120


def test_image_summary_is_truncated_to_120_chars(client, dev_headers, monkeypatch):
    """§4.2-3 的上界不是空断言：超长 VL 回复入库时被截到 120。"""
    long_summary = "橘猫趴在窗台上" * 60
    assert len(long_summary) > 120
    _install_fake_vl(monkeypatch, summary=long_summary)
    user = dev_headers["X-Dev-User"]
    conversation = _new_conversation(client, dev_headers, "摘要截断")

    _events(_post_image(client, dev_headers, conversation))

    rows = _image_rows(user, conversation)
    assert len(rows) == 1
    assert rows[0]["image_summary"] == long_summary[:120]
    assert len(rows[0]["image_summary"]) == 120


def test_image_summary_is_injected_into_model_messages_only(client, dev_headers, monkeypatch):
    """§4.2-4：摘要注入 build_context 产出的 messages，且 ctx.history 保持原始行。"""
    import services.chat_service as chat

    _install_fake_vl(monkeypatch)
    user = dev_headers["X-Dev-User"]
    conversation = _new_conversation(client, dev_headers, "摘要注入")
    _seed_history(user, conversation, _SEEDED)
    _events(_post_image(client, dev_headers, conversation))
    # 前提：摘要确实已落库，否则下面的注入断言是空跑。
    assert _image_rows(user, conversation)[0]["image_summary"] == _SUMMARY

    # 下一轮：build_context 里其它字段都走 getattr 默认值，SimpleNamespace 缺属性不会炸。
    request = SimpleNamespace(message="再看看", image_base64=None, conversation_id=conversation)
    ctx = asyncio.run(chat.build_context(request, user))

    injected = [m for m in ctx.messages if _IMAGE_MARK in (m.get("content") or "")]
    assert len(injected) == 1
    assert injected[0]["role"] == "user"
    assert injected[0]["content"] == f"{_USER_TEXT}{_IMAGE_MARK}{_SUMMARY}］"
    # 正控：原始历史一条都没被改写（信号计算/画像提取/意图识别都在读它）
    assert not any(_IMAGE_MARK in (m.get("content") or "") for m in ctx.history)
    original = [m for m in ctx.history if m.get("image_path")]
    assert len(original) == 1
    assert original[0]["content"] == _USER_TEXT
    assert original[0]["image_summary"] == _SUMMARY
    # 历史顺序未被注入打乱：12 条种子 + 图片那条 = 13
    assert [m["content"] for m in ctx.history[:12]] == _SEEDED


def test_frontend_message_payload_keeps_original_content(client, dev_headers, monkeypatch):
    """§4.2-5：/conversations/{id}/messages 返回给前端的 content 不含注入标记。"""
    _install_fake_vl(monkeypatch)
    user = dev_headers["X-Dev-User"]
    conversation = _new_conversation(client, dev_headers, "前端不受影响")
    _events(_post_image(client, dev_headers, conversation))

    # 正控：库里那条确实已经有摘要了，接口仍然不能把它拼进气泡文案。
    stored = _image_rows(user, conversation)
    assert len(stored) == 1
    assert stored[0]["image_summary"] == _SUMMARY

    response = client.get(f"/conversations/{conversation}/messages", headers=dev_headers)
    assert response.status_code == 200, response.text
    messages = response.json()["messages"]
    image_messages = [m for m in messages if m.get("image_path")]
    assert len(image_messages) == 1
    assert image_messages[0]["content"] == _USER_TEXT
    assert _IMAGE_MARK not in image_messages[0]["content"]
    assert _SUMMARY not in image_messages[0]["content"]
    # 用户气泡与助手回复的可见顺序/内容不变
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", _USER_TEXT), ("assistant", _SUMMARY),
    ]
