"""BYOK Claude agent image ownership: show the image only to its owner before persistence."""
import asyncio
from io import BytesIO
from pathlib import Path
import socket

from PIL import Image
import pytest

import services.chat_service as chat
from test_claude_agent_runtime import FakeStream, call, harness, message, run


PATH = "/uploads/generated_" + "c" * 32 + ".png"


@pytest.fixture(scope="module", autouse=True)
def offline_module():
    patch = pytest.MonkeyPatch()
    def blocked(*args, **kwargs):
        raise AssertionError("BYOK pending image tests forbid TCP connections and DNS")
    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, blocked)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, blocked)
    yield
    patch.undo()


def queue_image_round(h):
    async def image(ctx, state, prompt, *, agent_result, **kwargs):
        agent_result.update(success=True, image_path=PATH, model="model", aspect_ratio="1:1")
        yield h.chat._sse({"generated_image": {"image_path": PATH, "model": "model", "width": 16, "height": 9}})
        yield h.chat._sse({"text": "图片已生成。"})
    h.monkeypatch.setattr(h.chat, "_stream_image_execution", image)
    h.streams.extend([FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "猫"})])),
                      FakeStream(message(text="完成"), "完成")])


def test_generated_image_is_viewable_from_the_event_until_persisted(harness):
    h = harness
    async def save(ctx, state, image_path=None):
        assert h.chat.is_pending_generated_image(h.ctx.user, PATH)
        assert not state.billable
        h.saves.append((state.full_response, image_path))
        state.response_saved = True
    h.monkeypatch.setattr(h.chat, "_save_response", save)
    queue_image_round(h)
    async def scenario():
        seen = False
        async for event in h.agent.stream_claude_agent(h.ctx, h.state):
            if isinstance(event, str) and "generated_image" in event:
                assert h.chat.is_pending_generated_image(h.ctx.user, PATH)
                assert h.saves == []
                seen = True
        assert seen
    asyncio.run(scenario())
    assert len(h.saves) == 1 and h.saves[0][1] == PATH
    assert not h.chat.is_pending_generated_image(h.ctx.user, PATH)
    assert h.deleted == []
    assert h.state.billable is True


def test_failed_persistence_releases_claim_and_deletes_image(harness):
    h = harness
    async def save(*args, **kwargs):
        raise RuntimeError("conversation no longer available")
    h.monkeypatch.setattr(h.chat, "_save_response", save)
    queue_image_round(h)
    with pytest.raises(RuntimeError, match="conversation no longer available"):
        run(h)
    assert not h.chat.is_pending_generated_image(h.ctx.user, PATH)
    assert h.deleted == [PATH]
    assert not h.state.billable


def test_client_disconnect_after_image_event_releases_claim(harness):
    h = harness
    queue_image_round(h)
    async def scenario():
        stream = h.agent.stream_claude_agent(h.ctx, h.state)
        while "generated_image" not in await anext(stream):
            pass
        await stream.aclose()
    asyncio.run(scenario())
    assert not h.chat.is_pending_generated_image(h.ctx.user, PATH)
    assert h.deleted == [PATH]
    assert h.saves == []
    assert not h.state.billable


def test_uploads_route_serves_pending_image_only_to_its_owner(client, dev_headers):
    from utils import media
    name = "generated_" + "d" * 32 + ".png"
    image_path = Path(media.UPLOADS_DIR) / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    Image.new("RGB", (16, 9), "blue").save(buffer, format="PNG")
    png = buffer.getvalue()
    image_path.write_bytes(png)
    try:
        assert client.get(f"/uploads/{name}", headers=dev_headers).status_code == 404
        try:
            chat.claim_pending_generated_image("smoke_tester", f"/uploads/{name}")
            response = client.get(f"/uploads/{name}", headers=dev_headers)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("image/png")
            assert "no-store" in response.headers.get("cache-control", "")
            assert response.content == png
            assert client.get(f"/uploads/{name}", headers={"X-Dev-User": "someone_else"}).status_code == 404
            other = "generated_" + "e" * 32 + ".png"
            assert client.get(f"/uploads/{other}", headers=dev_headers).status_code == 404
        finally:
            chat.release_pending_generated_image("smoke_tester", f"/uploads/{name}")
        assert client.get(f"/uploads/{name}", headers=dev_headers).status_code == 404
    finally:
        image_path.unlink(missing_ok=True)
    assert chat._PENDING_GENERATED_IMAGES == set()
