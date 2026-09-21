"""Image chat persists real attachments, respects ownership and never fabricates success."""
import asyncio
import json
import pytest


@pytest.fixture(autouse=True)
def isolated_limits(monkeypatch):
    from rate_limit import limiter
    import services.chat_service as chat
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def image_stub(monkeypatch, tmp_path):
    import services.chat_service as chat
    from utils import media
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    calls = []
    path = tmp_path / "generated_test.png"

    async def generate(prompt, ratio):
        calls.append((prompt, ratio))
        path.write_bytes(b"owned-test-attachment")
        return {"image_path": "/uploads/generated_test.png", "model": "qwen-image-3.0", "width": 1024, "height": 1024}

    monkeypatch.setattr(chat, "generate_image", generate)
    return calls, path


def new_conversation(client, headers):
    return client.post("/conversations", json={}, headers=headers).json()["conversation"]["id"]


def test_explicit_mode_uses_full_prompt_and_saves_image_in_fixed_conversation(client, dev_headers, image_stub, monkeypatch):
    import services.chat_service as chat
    monkeypatch.setattr(chat, "detect_mode", lambda *a: (_ for _ in ()).throw(AssertionError("must bypass companion routing")))
    conversation = new_conversation(client, dev_headers)
    prompt = "薄雾中的古庙，青灰与墨绿。" * 50
    output = events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": prompt, "mode": "image", "aspect_ratio": "9:16",
    }))
    assert image_stub[0] == [(prompt, "9:16")]
    assert output[0]["status"] == "generating_image"
    assert output[-1] == {"done": True}
    generated = next(event["generated_image"] for event in output if "generated_image" in event)
    history = client.get(f"/conversations/{conversation}/messages", headers=dev_headers).json()["messages"]
    assert [(item["role"], item["content"]) for item in history] == [("user", prompt), ("assistant", "图片已生成。")]
    assert history[-1]["image_path"] == generated["image_path"]
    assert image_stub[1].exists()


@pytest.mark.parametrize("prompt,ratio", [
    ("帮我生成一张青灰薄雾古庙图片，横版16:9", "16:9"),
    ("画一只趴在窗台的猫", "1:1"),
    ("请帮我做一张咖啡店海报，竖版", "9:16"),
])
def test_natural_request_precedes_mirror_and_old_pending(client, dev_headers, image_stub, monkeypatch, prompt, ratio):
    import services.chat_service as chat
    from intent_router import set_pending, get_pending
    conversation = new_conversation(client, dev_headers)
    key = ("smoke_tester", conversation)
    set_pending(key, {"intent": "route", "params": {}, "missing": ["origin"]})
    monkeypatch.setattr(chat, "detect_mode", lambda *a: "mirror")
    output = events(client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": prompt}))
    assert image_stub[0] == [(prompt, ratio)]
    assert any("generated_image" in item for item in output)
    assert get_pending(key) is None


@pytest.mark.parametrize("message", [
    "能生成图片吗", "你能生成图片吗？", "帮我写一个生成图片的提示词", "生成图片有哪些模型？",
    "不要画了", "我昨天画了一张猫的图片", "你刚才生成的图片不好看", "怎么生成图片",
])
def test_image_discussion_does_not_trigger_generation(client, dev_headers, image_stub, message):
    output = events(client.post("/chat", headers=dev_headers, json={"message": message}))
    assert image_stub[0] == []
    assert not any("generated_image" in item for item in output)


def test_image_prompt_question_then_description_generates_only_description(client, dev_headers, image_stub):
    conversation = new_conversation(client, dev_headers)
    first = events(client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": "帮我生成图片"}))
    assert image_stub[0] == []
    assert "想生成什么画面" in first[0]["text"]
    events(client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": "青灰薄雾中的悬崖古庙"}))
    assert image_stub[0] == [("青灰薄雾中的悬崖古庙", "1:1")]


@pytest.mark.parametrize("reply", ["取消", "不要画了", "不用生成了", "取消，先聊别的", "你能生成图片吗", "今天天气如何", "先聊别的", "谢谢"])
def test_pending_image_request_can_be_cancelled_or_left(client, dev_headers, image_stub, reply):
    from intent_router import get_pending
    conversation = new_conversation(client, dev_headers)
    events(client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": "帮我生成图片"}))
    events(client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": reply}))
    assert image_stub[0] == []
    assert get_pending(("smoke_tester", conversation)) is None


def test_generation_error_has_no_success_attachment_or_charge(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    import database
    from auth import create_token
    conversation = new_conversation(client, dev_headers)
    balance = asyncio.run(database.get_strawberry_balance("smoke_tester"))
    monkeypatch.setenv("DEV_MODE", "0")
    async def fail(*args):
        raise chat.ImageGenerationError("图片生成等待超时，请稍后再试。")
    monkeypatch.setattr(chat, "generate_image", fail)
    headers = {"Authorization": f"Bearer {create_token('smoke_tester')}"}
    output = events(client.post("/chat", headers=headers, json={"conversation_id": conversation, "message": "古庙", "mode": "image"}))
    assert output == [{"status": "generating_image", "message": "正在生成图片，请稍候…"}, {"error": "图片生成等待超时，请稍后再试。"}]
    assert asyncio.run(database.get_strawberry_balance("smoke_tester")) == balance
    history = client.get(f"/conversations/{conversation}/messages", headers=headers).json()["messages"]
    assert [item["role"] for item in history] == ["user"]


def test_other_owner_conversation_rejected_before_generation(client, dev_headers, image_stub):
    other = {"X-Dev-User": "image_owner"}
    conversation = new_conversation(client, other)
    response = client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": "古庙", "mode": "image"})
    assert response.status_code == 404
    assert image_stub[0] == []


def test_deleted_conversation_during_generation_removes_unsaved_image(client, dev_headers, image_stub, monkeypatch):
    import services.chat_service as chat
    import agent_store
    conversation = new_conversation(client, dev_headers)
    original = chat.generate_image
    async def generate(*args):
        result = await original(*args)
        await agent_store.delete_conversation("smoke_tester", conversation)
        return result
    monkeypatch.setattr(chat, "generate_image", generate)
    output = events(client.post("/chat", headers=dev_headers, json={"conversation_id": conversation, "message": "古庙", "mode": "image"}))
    assert output[-1] == {"error": "会话已删除或不可用"}
    assert not any("generated_image" in item for item in output)
    assert not image_stub[1].exists()


def test_cancellation_cancels_provider_and_releases_user_slot(monkeypatch):
    import services.chat_service as chat
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def generate(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setattr(chat, "generate_image", generate)
        ctx = chat.ChatContext("cancel-test", "古庙", False, None, "古庙", [], 0, "", [])
        state = chat.ChatState(trace={})
        stream = chat.stream_generated_image(ctx, state, ctx.message)
        assert "generating_image" in await anext(stream)
        pending = asyncio.create_task(anext(stream))
        await started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert cancelled.is_set()
        assert ctx.user not in chat._IMAGE_GENERATION_USERS
        assert not state.response_saved
    asyncio.run(scenario())


def test_anyio_disconnect_finishes_commit_before_deciding_file_cleanup(monkeypatch):
    import anyio
    import services.chat_service as chat
    async def scenario():
        started = asyncio.Event()
        deleted = []
        async def generate(*args):
            return {"image_path": "/uploads/generated_commit.png", "model": "test", "width": 1, "height": 1}
        async def save(ctx, state, image_path=None):
            started.set()
            await asyncio.sleep(0.02)
            state.response_saved = True
        monkeypatch.setattr(chat, "generate_image", generate)
        monkeypatch.setattr(chat, "_save_response", save)
        monkeypatch.setattr(chat, "delete_uploaded_files", lambda paths: deleted.extend(paths))
        ctx = chat.ChatContext("commit-test", "古庙", False, None, "古庙", [], 0, "", [])
        state = chat.ChatState(trace={})
        async def consume():
            async for _ in chat.stream_generated_image(ctx, state, ctx.message):
                pass
        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await started.wait()
            group.cancel_scope.cancel()
        assert state.response_saved
        assert deleted == []
        assert ctx.user not in chat._IMAGE_GENERATION_USERS
    asyncio.run(scenario())


@pytest.mark.parametrize("extra", [{"aspect_ratio": "4:3"}, {"mode": "unknown"}])
def test_invalid_generation_options_fail_validation(client, dev_headers, image_stub, extra):
    response = client.post("/chat", headers=dev_headers, json={"message": "古庙", "mode": "image", **extra})
    assert response.status_code == 422
    assert image_stub[0] == []


def test_generation_mode_rejects_attached_image_before_upload_or_provider(client, dev_headers, image_stub):
    response = client.post("/chat", headers=dev_headers, json={"message": "古庙", "mode": "image", "image_base64": "not-an-image"})
    assert response.status_code == 400
    assert "移除" in response.json()["detail"]
    assert image_stub[0] == []
