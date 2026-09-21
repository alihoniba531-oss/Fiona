"""Provider billing failures are actionable without leaking upstream details."""
import asyncio
import json
from types import SimpleNamespace

import httpx
from openai import BadRequestError
from openai.types.chat import ChatCompletionChunk
import pytest


_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)
_BILLING_MESSAGE = "模型服务账户欠费，暂时无法生成回复。请联系平台管理员恢复模型服务后重试。"


@pytest.mark.parametrize("branch", ["mirror", "normal", "image", "outer"])
@pytest.mark.parametrize("code,expected", [
    ("Arrearage", _BILLING_MESSAGE),
    (None, "服务暂时不可用，请稍后再试"),
], ids=["billing", "unknown"])
def test_upstream_error_is_sanitized_and_never_saved_or_charged(
    client, dev_headers, monkeypatch, branch, code, expected,
):
    import database
    import services.chat_service as chat
    from auth import create_token
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]
    user = conversation["owner_username"]
    balance_before = asyncio.run(database.get_strawberry_balance(user))
    assert balance_before > 0
    # Exercise actual balance checking and deduction, not DEV_MODE's skip path.
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token(user)}"}
    raw_detail = "Arrearage raw-secret-marker private upstream account details"
    provider_response = httpx.Response(
        400, request=httpx.Request("POST", "https://provider.invalid/chat/completions"),
    )
    failure = BadRequestError(
        raw_detail, response=provider_response,
        body={"code": code, "message": raw_detail},
    )

    def fail(*args, **kwargs):
        raise failure

    payload = {"message": "普通测试消息", "conversation_id": conversation["id"]}
    if branch == "mirror":
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
        monkeypatch.setattr(chat, "_create_stream_with_fallback", fail)
    elif branch == "normal":
        monkeypatch.setattr(chat, "_create_stream_with_fallback", fail)
    elif branch == "image":
        payload["image_base64"] = f"data:image/png;base64,{_TINY_PNG}"
        monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fail)),
        ))
    else:
        monkeypatch.setattr(chat, "detect_mode", fail)

    response = client.post("/chat", headers=headers, json=payload)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events == [{"error": expected}]
    assert "raw-secret-marker" not in response.text
    assert "private upstream account details" not in response.text
    assert asyncio.run(database.get_strawberry_balance(user)) == balance_before
    saved = asyncio.run(database.get_messages(user, conversation_id=conversation["id"]))
    assert [(message["role"], message["content"]) for message in saved] == [("user", payload["message"])]


@pytest.mark.parametrize("branch", ["mirror", "normal", "image"])
@pytest.mark.parametrize("fail_after_text", [False, True], ids=["usage-tail", "real-stream-error"])
def test_empty_choice_frames_complete_without_hiding_real_stream_errors(
    client, dev_headers, monkeypatch, branch, fail_after_text,
):
    import database
    import services.chat_service as chat
    from auth import create_token
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    conversation = client.post("/conversations", headers=dev_headers, json={}).json()["conversation"]
    user = conversation["owner_username"]
    balance_before = asyncio.run(database.get_strawberry_balance(user))
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token(user)}"}

    def frame(choices, **kwargs):
        return ChatCompletionChunk(
            id="synthetic-stream", object="chat.completion.chunk", created=0,
            model="synthetic-model", choices=choices, **kwargs,
        )

    class ProviderStream:
        close_count = 0

        def __iter__(self):
            yield frame([])  # Metadata may also precede the first content choice.
            yield frame([{"index": 0, "delta": {"role": "assistant", "content": "真实结构"}}])
            if fail_after_text:
                raise RuntimeError("private raw stream failure marker")
            yield frame([{"index": 0, "delta": {"content": "回复"}}])
            yield frame([{"index": 0, "delta": {}, "finish_reason": "stop"}])
            yield frame([], usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})

        def close(self):
            self.close_count += 1

    provider_stream = ProviderStream()
    charges = []
    original_deduct = chat.deduct_strawberry

    async def counted_deduct(username, amount):
        charges.append((username, amount))
        return await original_deduct(username, amount)

    monkeypatch.setattr(chat, "deduct_strawberry", counted_deduct)
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *a, **k: (provider_stream, False))
    payload = {"message": "普通测试消息", "conversation_id": conversation["id"]}
    if branch == "mirror":
        monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "mirror")
    elif branch == "image":
        payload["image_base64"] = f"data:image/png;base64,{_TINY_PNG}"
        monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: provider_stream)),
        ))

    response = client.post("/chat", headers=headers, json=payload)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    saved = asyncio.run(database.get_messages(user, conversation_id=conversation["id"]))
    assert provider_stream.close_count == 1
    if fail_after_text:
        assert events == [{"text": "真实结构"}, {"error": "服务暂时不可用，请稍后再试"}]
        assert "private raw stream failure marker" not in response.text
        assert [message["role"] for message in saved] == ["user"]
        assert charges == []
        assert asyncio.run(database.get_strawberry_balance(user)) == balance_before
    else:
        assert events == [{"text": "真实结构"}, {"text": "回复"}, {"done": True}]
        assert [(message["role"], message["content"]) for message in saved] == [
            ("user", payload["message"]), ("assistant", "真实结构回复"),
        ]
        assert charges == [(user, 10)]
        assert asyncio.run(database.get_strawberry_balance(user)) == balance_before - 10
