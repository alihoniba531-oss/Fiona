# -*- coding: utf-8 -*-
"""分身聊天的集成回归：上下文、临时状态、权限与删除竞态。"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from _fakes import FakeStream


@pytest.fixture(autouse=True)
def _isolate_chat_rate_limit(monkeypatch):
    """聊天集成用例不共享其他模块的每分钟请求配额。"""
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _events(response):
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


def _chat(client, headers, conversation_id, message):
    return client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": message},
        headers=headers,
    )


def _history(client, headers, conversation_id):
    response = client.get(f"/conversations/{conversation_id}/messages", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["messages"]


def _record_model_calls(monkeypatch):
    import services.chat_service as chat

    calls = []

    def record(use_qwen, messages, **kwargs):
        # Copy the actual model boundary payload before another turn can mutate it.
        calls.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", record)
    return calls


def test_conversations_isolate_model_context_and_persist_each_history(
    client, dev_headers, monkeypatch,
):
    calls = _record_model_calls(monkeypatch)
    first = _new_conversation(client, dev_headers, "旅行话题")
    second = _new_conversation(client, dev_headers, "阅读话题")
    first_message = "只属于旅行会话的标记：青苔车票"
    second_message = "只属于阅读会话的标记：琥珀书签"
    followup = "继续聊刚才的旅行"

    _events(_chat(client, dev_headers, first, first_message))
    _events(_chat(client, dev_headers, second, second_message))
    _events(_chat(client, dev_headers, first, followup))

    assert len(calls) == 3
    assert calls[1][1:] == [{"role": "user", "content": second_message}]
    assert calls[2][1:] == [
        {"role": "user", "content": first_message},
        {"role": "assistant", "content": "测试回复"},
        {"role": "user", "content": followup},
    ]
    assert first_message not in json.dumps(calls[1], ensure_ascii=False)
    assert second_message not in json.dumps(calls[2], ensure_ascii=False)

    first_history = _history(client, dev_headers, first)
    second_history = _history(client, dev_headers, second)
    assert [(message["role"], message["content"]) for message in first_history] == [
        ("user", first_message), ("assistant", "测试回复"),
        ("user", followup), ("assistant", "测试回复"),
    ]
    assert [(message["role"], message["content"]) for message in second_history] == [
        ("user", second_message), ("assistant", "测试回复"),
    ]


def test_chat_rejects_another_accounts_conversation_before_model_or_write(
    client, dev_headers, monkeypatch,
):
    calls = _record_model_calls(monkeypatch)
    owner_headers = {"X-Dev-User": "conversation_owner"}
    conversation_id = _new_conversation(client, owner_headers, "别人的私聊")

    response = _chat(client, dev_headers, conversation_id, "越权写入不应该发生")

    assert response.status_code == 404, response.text
    assert calls == []
    assert _history(client, owner_headers, conversation_id) == []


def test_custom_avatar_personality_keeps_platform_identity_and_safety_rules(
    client, dev_headers, monkeypatch,
):
    from persona import AGENT_IDENTITY_RULES, BASE_SAFETY_RULES

    calls = _record_model_calls(monkeypatch)
    name = "星河向导"
    personality = "喜欢用园艺比喻，表达简短直接。"
    response = client.put(
        "/agents/me",
        json={
            "display_name": name,
            "bio": "一起观察世界",
            "personality": personality,
            "avatar_emoji": "🌱",
            "is_public": False,
        },
        headers=dev_headers,
    )
    assert response.status_code == 200, response.text
    conversation_id = _new_conversation(client, dev_headers, "认识我的分身")

    _events(_chat(client, dev_headers, conversation_id, "介绍一下自己"))

    system_prompt = calls[0][0]["content"]
    assert name in system_prompt
    assert personality in system_prompt
    assert AGENT_IDENTITY_RULES.strip() in system_prompt
    assert BASE_SAFETY_RULES.strip() in system_prompt
    assert "AI 分身" in system_prompt
    assert "不是 AI、不是助手、不是模型、不是程序" not in system_prompt


def test_pending_tool_parameters_belong_to_their_conversation(
    client, dev_headers, monkeypatch,
):
    import services.chat_service as chat

    first = _new_conversation(client, dev_headers, "提醒事项")
    second = _new_conversation(client, dev_headers, "普通话题")
    executed = []

    def recognize(_client, message, history):
        if message == "稍后提醒我喝水":
            return {
                "intent": "set_reminder",
                "params": {"text": "喝水"},
                "missing": ["minutes"],
            }
        return {"intent": None, "params": {}, "missing": []}

    def execute(intent, params):
        executed.append((intent, dict(params)))
        return f"{params['minutes']}分钟后提醒喝水"

    monkeypatch.setattr(chat, "recognize_intent", recognize)
    monkeypatch.setattr(chat, "execute_intent", execute)

    _events(_chat(client, dev_headers, first, "稍后提醒我喝水"))
    _events(_chat(client, dev_headers, second, "30"))
    assert executed == []

    events = _events(_chat(client, dev_headers, first, "45"))
    assert executed == [("set_reminder", {"text": "喝水", "minutes": 45})]
    assert any("45分钟后提醒喝水" in event.get("text", "") for event in events)
    assert [message["content"] for message in _history(client, dev_headers, second)] == [
        "30", "测试回复",
    ]


def test_mirror_mode_does_not_follow_user_into_another_conversation(
    client, dev_headers, monkeypatch,
):
    import mode_switcher
    import services.chat_service as chat

    calls = _record_model_calls(monkeypatch)
    monkeypatch.setattr(chat, "detect_mode", mode_switcher.detect_mode)
    # Restore real mode switching while keeping its optional network classifier fake.
    monkeypatch.setattr(mode_switcher, "_llm_is_venting", lambda *args: False)
    first = _new_conversation(client, dev_headers, "只想倾诉")
    second = _new_conversation(client, dev_headers, "日常交流")

    _events(_chat(client, dev_headers, first, "别给建议，你听就行"))
    _events(_chat(client, dev_headers, second, "今天喝了一杯茶"))
    _events(_chat(client, dev_headers, first, "接着说刚才的事"))

    appendix = mode_switcher.MIRROR_PROMPT_APPENDIX.strip()
    assert appendix in calls[0][0]["content"]
    assert appendix not in calls[1][0]["content"]
    assert appendix in calls[2][0]["content"]


def test_deleted_conversation_is_not_recreated_by_a_late_stream_response(
    client, dev_headers, monkeypatch,
):
    import aiosqlite
    import database
    import services.chat_service as chat

    conversation_id = _new_conversation(client, dev_headers, "马上删除")
    model_started = Event()
    model_released = Event()

    def delayed_stream(use_qwen, messages, **kwargs):
        model_started.set()
        assert model_released.wait(timeout=10), "test did not release the fake model"
        return FakeStream([("迟到的模型回复", "stop")]), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", delayed_stream)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_response = executor.submit(
            _chat, client, dev_headers, conversation_id, "等待模型回复时删除会话",
        )
        try:
            assert model_started.wait(timeout=10), "chat never reached the fake model"
            response = client.delete(f"/conversations/{conversation_id}", headers=dev_headers)
            assert response.status_code in (200, 204), response.text
        finally:
            model_released.set()
        assert pending_response.result(timeout=10).status_code == 200

    assert client.get(
        f"/conversations/{conversation_id}/messages", headers=dev_headers,
    ).status_code == 404

    async def stored_message_count():
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ) as cursor:
                return (await cursor.fetchone())[0]

    assert asyncio.run(stored_message_count()) == 0
    calls = _record_model_calls(monkeypatch)
    assert _chat(client, dev_headers, conversation_id, "删除后不能继续").status_code == 404
    assert calls == []


def test_legacy_chat_keeps_default_history_separate_from_new_conversations(
    client, dev_headers, monkeypatch,
):
    calls = _record_model_calls(monkeypatch)
    legacy_message = "旧客户端第一句话"
    _events(client.post("/chat", json={"message": legacy_message}, headers=dev_headers))
    conversation_id = _new_conversation(client, dev_headers, "新客户端会话")
    _events(_chat(client, dev_headers, conversation_id, "另一个话题"))
    _events(client.post("/chat", json={"message": "旧客户端继续聊"}, headers=dev_headers))

    assert calls[1][1:] == [{"role": "user", "content": "另一个话题"}]
    assert calls[2][1:] == [
        {"role": "user", "content": legacy_message},
        {"role": "assistant", "content": "测试回复"},
        {"role": "user", "content": "旧客户端继续聊"},
    ]


def test_publishing_avatar_does_not_publish_its_chat_or_private_personality(
    client, dev_headers, monkeypatch,
):
    calls = _record_model_calls(monkeypatch)
    private_personality = "私有人格暗号：松风琥珀"
    private_message = "只在私聊里保存的内容：银杏风铃"
    response = client.put(
        "/agents/me",
        json={
            "display_name": "公开向导",
            "bio": "欢迎交流天文与植物",
            "personality": private_personality,
            "avatar_emoji": "🌿",
            "is_public": True,
        },
        headers=dev_headers,
    )
    assert response.status_code == 200, response.text
    agent_id = response.json()["agent"]["id"]
    conversation_id = _new_conversation(client, dev_headers, "我的私聊")
    _events(_chat(client, dev_headers, conversation_id, private_message))

    visitor_headers = {"X-Dev-User": "public_avatar_visitor"}
    for path in ("/agents", f"/agents/{agent_id}"):
        response = client.get(path, headers=visitor_headers)
        assert response.status_code == 200, response.text
        public_data = json.dumps(response.json(), ensure_ascii=False)
        assert "公开向导" in public_data
        assert "欢迎交流天文与植物" in public_data
        assert private_personality not in public_data
        assert private_message not in public_data
    assert client.get(
        f"/conversations/{conversation_id}/messages", headers=visitor_headers,
    ).status_code == 404

    visitor_conversation = _new_conversation(client, visitor_headers, "访客自己的私聊")
    _events(_chat(client, visitor_headers, visitor_conversation, "你好"))
    visitor_context = json.dumps(calls[-1], ensure_ascii=False)
    assert private_personality not in visitor_context
    assert private_message not in visitor_context


def test_memory_clear_wins_over_an_extractor_already_waiting_on_the_model(
    client, dev_headers, monkeypatch,
):
    import agent_store
    import extractor

    conversation_id = _new_conversation(client, dev_headers, "记忆删除竞态")
    username = dev_headers["X-Dev-User"]
    asyncio.run(agent_store.update_memory(username, {"interests": ["旧记忆：摄影"]}))
    model_started = Event()
    model_released = Event()
    captured = {}
    preference_updates = []
    followups = []

    def delayed_extraction(**kwargs):
        captured.update(kwargs)
        model_started.set()
        assert model_released.wait(timeout=10), "test did not release the extractor"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"interests": ["旧对话提取出的旅行爱好"]}, ensure_ascii=False),
        ))])

    async def record_preferences(*args, **kwargs):
        preference_updates.append((args, kwargs))

    def record_followup(coro):
        followups.append("profile-match")
        coro.close()

    monkeypatch.setattr(extractor, "update_time_tag_prefs", record_preferences)
    monkeypatch.setattr(extractor, "_track_background_task", record_followup)
    model_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=delayed_extraction),
    ))
    messages = [
        {"role": "user", "content": "我喜欢旅行"},
        {"role": "assistant", "content": "想去哪儿"},
        {"role": "user", "content": "想去山里摄影"},
        {"role": "assistant", "content": "可以聊聊山里的路线"},
    ]

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_extraction = executor.submit(
            asyncio.run,
            extractor.extract_and_update(
                model_client, username, messages, conversation_id=conversation_id,
            ),
        )
        try:
            assert model_started.wait(timeout=10), "extractor never reached the fake model"
            response = client.delete("/agents/me/memory", headers=dev_headers)
            assert response.status_code == 200, response.text
        finally:
            model_released.set()
        pending_extraction.result(timeout=10)

    assert "旧记忆：摄影" in captured["messages"][1]["content"]
    response = client.get("/agents/me/memory", headers=dev_headers)
    assert response.status_code == 200, response.text
    assert response.json()["profile"] == {}
    assert asyncio.run(agent_store.get_memory_snapshot(username))["profile"] == {}
    assert preference_updates == []
    assert followups == []


def test_deleted_conversation_cannot_execute_a_tool_after_intent_recognition(
    client, dev_headers, monkeypatch,
):
    import services.chat_service as chat

    conversation_id = _new_conversation(client, dev_headers, "删除后停止工具")
    recognition_started = Event()
    recognition_released = Event()
    executed = []

    def delayed_recognition(_client, message, history):
        recognition_started.set()
        assert recognition_released.wait(timeout=10), "test did not release recognition"
        return {"intent": "get_datetime", "params": {}, "missing": []}

    def record_tool(intent, params):
        executed.append((intent, params))
        return "不应执行的工具结果"

    monkeypatch.setattr(chat, "recognize_intent", delayed_recognition)
    monkeypatch.setattr(chat, "execute_intent", record_tool)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_response = executor.submit(
            _chat, client, dev_headers, conversation_id, "现在几点了",
        )
        try:
            assert recognition_started.wait(timeout=10), "chat did not start recognition"
            response = client.delete(f"/conversations/{conversation_id}", headers=dev_headers)
            assert response.status_code in (200, 204), response.text
        finally:
            recognition_released.set()
        assert pending_response.result(timeout=10).status_code == 200

    assert executed == []


def test_private_extraction_updates_only_avatar_memory_without_social_signals(
    client, dev_headers, monkeypatch,
):
    import agent_store
    import database
    import extractor
    import services.chat_service as chat

    conversation_id = _new_conversation(client, dev_headers, "只记给我的分身")
    username = dev_headers["X-Dev-User"]
    legacy_profile = {"interests": ["旧社交画像：陶艺"]}
    private_profile = {"values": ["私有偏好：宁静"]}
    extracted_profile = {"interests": ["私下喜欢山中摄影"], "needs": ["旅行路线"]}
    asyncio.run(database.update_profile(username, legacy_profile))
    asyncio.run(agent_store.update_memory(username, private_profile))
    preference_updates = []
    profile_matches = []
    conversation_matches = []

    async def record_preferences(*args, **kwargs):
        preference_updates.append((args, kwargs))

    def record_profile_match(coro):
        profile_matches.append("profile-match")
        coro.close()

    async def record_conversation_match(*args, **kwargs):
        conversation_matches.append((args, kwargs))

    def extract_profile(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps(extracted_profile, ensure_ascii=False),
        ))])

    monkeypatch.setattr(extractor, "update_time_tag_prefs", record_preferences)
    monkeypatch.setattr(extractor, "_track_background_task", record_profile_match)
    monkeypatch.setattr(chat, "detect_matches_and_save", record_conversation_match)
    model_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=extract_profile),
    ))
    messages = [
        {"role": "user", "content": "我喜欢安静地在山里摄影"},
        {"role": "assistant", "content": "打算什么时候去"},
        {"role": "user", "content": "周末，想规划旅行路线"},
        {"role": "assistant", "content": "聊聊你想去的山吧"},
    ]

    asyncio.run(extractor.extract_and_update(
        model_client, username, messages, conversation_id=conversation_id,
    ))

    snapshot = asyncio.run(agent_store.get_memory_snapshot(username, conversation_id))
    assert snapshot["profile"] == {**private_profile, **extracted_profile}
    assert asyncio.run(database.get_profile(username)) == legacy_profile
    calls = _record_model_calls(monkeypatch)
    _events(_chat(client, dev_headers, conversation_id, "你记住了什么"))
    system_prompt = calls[0][0]["content"]
    assert "私有偏好：宁静" in system_prompt
    assert "私下喜欢山中摄影" in system_prompt
    assert "旧社交画像：陶艺" not in system_prompt
    assert preference_updates == []
    assert profile_matches == []
    assert conversation_matches == []
