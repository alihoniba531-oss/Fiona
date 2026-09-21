"""Uploaded reference images remain private, durable and reusable across edit failures."""
import asyncio
import base64
import io
import json
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def isolated_image_slots_and_limits(monkeypatch):
    from rate_limit import limiter
    import services.chat_service as chat

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())


def image_bytes(format="PNG", size=(28, 20)):
    stream = io.BytesIO()
    Image.new("RGB", size, color="darkgreen").save(stream, format=format)
    return stream.getvalue()


def encoded_image(format="PNG", *, data_uri=False):
    encoded = base64.b64encode(image_bytes(format)).decode("ascii")
    if data_uri:
        mime = "jpeg" if format == "JPEG" else format.lower()
        return f"data:image/{mime};base64,{encoded}"
    return encoded


def events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def new_conversation(client, headers):
    response = client.post("/conversations", json={}, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["conversation"]["id"]


def history(client, headers, conversation):
    response = client.get(f"/conversations/{conversation}/messages", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["messages"]


def edit_payload(conversation, sources, message="图一人物进入图二的薄雾古庙，保持自然光", **extra):
    return {"conversation_id": conversation, "message": message, "mode": "image_edit",
            "reference_images": sources, **extra}


def selected_paths(output):
    accepted = [event for event in output if event.get("type") == "reference_images"]
    assert len(accepted) == 1, output
    assert output[0] == accepted[0], output
    return accepted[0]["reference_image_paths"]


def generated_result(output):
    results = [event["generated_image"] for event in output if "generated_image" in event]
    assert len(results) == 1, output
    assert output[-1] == {"done": True}
    assert not any("error" in event for event in output)
    return results[0]


@pytest.fixture
def edit_stub(client, monkeypatch, tmp_path):
    import database
    import main
    import services.chat_service as chat
    from utils import media

    uploads = tmp_path / "external-reference-uploads"
    uploads.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(uploads))
    static = next(route.app for route in main.app.routes if getattr(route, "name", None) == "uploads")
    monkeypatch.setattr(static, "directory", str(uploads))
    monkeypatch.setattr(static, "all_directories", [str(uploads)])
    calls, generation_calls = [], []

    def make_image(prefix="generated"):
        filename = f"{prefix}_{uuid4().hex}.png"
        (uploads / filename).write_bytes(image_bytes())
        return f"/uploads/{filename}"

    def seed(conversation, owner="smoke_tester", prefix="generated"):
        path = make_image(prefix)
        assert asyncio.run(database.save_message(
            owner, "assistant", "已有参考图", path, conversation_id=conversation,
        )) is True
        return path

    async def edit(prompt, references, aspect_ratio=None):
        selected = references.copy() if isinstance(references, list) else references
        calls.append((prompt, selected, aspect_ratio))
        return {"image_path": make_image(), "model": "qwen-external-reference-test",
                "width": 28, "height": 20}

    async def no_generation(*args, **kwargs):
        generation_calls.append((args, kwargs))
        raise AssertionError("external references must use image editing")

    monkeypatch.setattr(chat, "edit_image", edit)
    monkeypatch.setattr(chat, "generate_image", no_generation)
    return SimpleNamespace(calls=calls, generation_calls=generation_calls, edit=edit,
                           uploads=uploads, make_image=make_image, seed=seed)


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
@pytest.mark.parametrize("data_uri", [False, True])
def test_external_image_is_normalized_to_private_png_and_saved_before_result(
    client, dev_headers, edit_stub, format, data_uri,
):
    conversation = new_conversation(client, dev_headers)
    prompt = "保留人物身份，仅把天空改为青灰晨雾"
    output = events(client.post("/chat", headers=dev_headers, json=edit_payload(
        conversation, [{"image_base64": encoded_image(format, data_uri=data_uri)}], prompt,
    )))
    references = selected_paths(output)
    result = generated_result(output)

    assert len(references) == 1
    reference = references[0]
    assert re.fullmatch(r"/uploads/reference_[0-9a-f]{32}\.png", reference)
    with Image.open(edit_stub.uploads / reference.rsplit("/", 1)[-1]) as image:
        assert image.format == "PNG"
        # Normalization may enlarge tiny inputs to the provider's minimum area.
        assert image.width / image.height == pytest.approx(28 / 20, abs=0.01)
    assert edit_stub.calls == [(prompt, reference, None)]
    assert edit_stub.generation_calls == []
    assert result["reference_image_paths"] == references
    assert result["reference_image_path"] == reference
    assert result["image_path"] != reference
    rows = history(client, dev_headers, conversation)
    assert [(row["role"], row["content"], row["image_path"]) for row in rows] == [
        ("user", prompt, reference), ("assistant", "图片已修改。", result["image_path"]),
    ]
    assert rows[0]["reference_image_paths"] == references
    assert "image_base64" not in json.dumps(rows)
    assert len(list(edit_stub.uploads.iterdir())) == 2


@pytest.mark.parametrize("upload_position", [0, 1, 2])
def test_mixed_existing_and_uploaded_images_preserve_user_selection_order(
    client, dev_headers, edit_stub, upload_position,
):
    conversation = new_conversation(client, dev_headers)
    generated = edit_stub.seed(conversation)
    old_upload = edit_stub.seed(conversation, prefix="reference")
    sources = [{"image_path": old_upload}, {"image_path": generated}]
    sources.insert(upload_position, {"image_base64": encoded_image("JPEG")})
    prompt = "图一提供人物，图二提供背景，图三提供晨雾色调"
    output = events(client.post("/chat", headers=dev_headers, json=edit_payload(
        conversation, sources, prompt, aspect_ratio="16:9",
    )))
    references = selected_paths(output)

    assert len(references) == 3
    assert references[upload_position] not in {old_upload, generated}
    assert references[:upload_position] + references[upload_position + 1:] == [old_upload, generated]
    assert edit_stub.calls == [(prompt, references, "16:9")]
    assert generated_result(output)["reference_image_paths"] == references
    assert history(client, dev_headers, conversation)[-2]["reference_image_paths"] == references
    assert len(list(edit_stub.uploads.iterdir())) == 4


def test_reference_sse_is_available_before_provider_starts(client, dev_headers, edit_stub):
    import services.chat_service as chat
    from routers.chat import ChatRequest

    conversation = new_conversation(client, dev_headers)

    async def scenario():
        context = await chat.build_context(ChatRequest(**edit_payload(
            conversation, [{"image_base64": encoded_image()}],
        )), "smoke_tester")
        stream = chat.run_chat(context)
        try:
            first = await anext(stream)
            event = json.loads(first.removeprefix("data: ").strip())
            assert event["type"] == "reference_images"
            assert re.fullmatch(r"/uploads/reference_[0-9a-f]{32}\.png", event["reference_image_paths"][0])
            assert edit_stub.calls == []
        finally:
            await stream.aclose()

    asyncio.run(scenario())
    assert len(history(client, dev_headers, conversation)) == 1
    assert len(list(edit_stub.uploads.iterdir())) == 1


@pytest.mark.parametrize("bad_kind,status", [
    ("invalid_base64", 400), ("corrupt_png", 400), ("gif", 400), ("oversized", 413),
])
def test_bad_later_upload_rolls_back_every_new_file_and_saves_no_message(
    client, dev_headers, edit_stub, bad_kind, status,
):
    from utils.media import MAX_IMAGE_BYTES

    conversation = new_conversation(client, dev_headers)
    bad = {
        "invalid_base64": "not-valid-base64!",
        "corrupt_png": base64.b64encode(b"\x89PNG\r\n\x1a\ncorrupt").decode("ascii"),
        "gif": encoded_image("GIF"),
    }.get(bad_kind)
    if bad_kind == "oversized":
        raw = b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_IMAGE_BYTES + 1 - 8)
        bad = base64.b64encode(raw).decode("ascii")
    response = client.post("/chat", headers=dev_headers, json=edit_payload(
        conversation, [{"image_base64": encoded_image()}, {"image_base64": bad}],
    ))

    assert response.status_code == status, response.text
    assert history(client, dev_headers, conversation) == []
    assert list(edit_stub.uploads.iterdir()) == []
    assert edit_stub.calls == []


@pytest.mark.parametrize("ownership", ["other_account", "other_conversation", "unreferenced"])
@pytest.mark.parametrize("prefix", ["generated", "reference"])
def test_forged_old_reference_cannot_acquire_ownership_by_mixing_in_a_new_upload(
    client, dev_headers, edit_stub, ownership, prefix,
):
    conversation = new_conversation(client, dev_headers)
    source_headers = {"X-Dev-User": "external_ref_owner"} if ownership == "other_account" else dev_headers
    source_owner = source_headers["X-Dev-User"]
    other_conversation = new_conversation(client, source_headers)
    path = edit_stub.make_image(prefix) if ownership == "unreferenced" else edit_stub.seed(
        other_conversation, source_owner, prefix,
    )
    before_source = history(client, source_headers, other_conversation)
    files_before = set(edit_stub.uploads.iterdir())
    # A forged internal keyword must never let the client mark old paths as new uploads.
    payload = edit_payload(conversation, [{"image_base64": encoded_image()}, {"image_path": path}],
                           new_reference_image_paths=[path])
    response = client.post("/chat", headers=dev_headers, json=payload)

    assert response.status_code == 404, response.text
    assert history(client, dev_headers, conversation) == []
    assert history(client, source_headers, other_conversation) == before_source
    assert set(edit_stub.uploads.iterdir()) == files_before
    assert edit_stub.calls == []


@pytest.mark.parametrize("case", [
    "empty_item", "both_sources", "empty_list", "four_images", "path_traversal", "wrong_type",
    "old_single", "old_list", "chat_mode", "image_mode", "ordinary_upload",
])
def test_external_reference_shape_and_mode_errors_happen_before_file_creation(
    client, dev_headers, edit_stub, case,
):
    conversation = new_conversation(client, dev_headers)
    old = edit_stub.seed(conversation)
    source = {"image_base64": encoded_image()}
    payload = edit_payload(conversation, [source])
    if case == "empty_item":
        payload["reference_images"] = [{}]
    elif case == "both_sources":
        payload["reference_images"] = [{**source, "image_path": old}]
    elif case == "empty_list":
        payload["reference_images"] = []
    elif case == "four_images":
        payload["reference_images"] = [source] * 4
    elif case == "path_traversal":
        payload["reference_images"] = [{"image_path": "/uploads/../reference_" + "a" * 32 + ".png"}]
    elif case == "wrong_type":
        payload["reference_images"] = [{"image_base64": 21}]
    elif case == "old_single":
        payload["reference_image_path"] = old
    elif case == "old_list":
        payload["reference_image_paths"] = [old]
    elif case in {"chat_mode", "image_mode"}:
        payload["mode"] = case.removesuffix("_mode")
    elif case == "ordinary_upload":
        payload["image_base64"] = encoded_image()
    before = history(client, dev_headers, conversation)

    response = client.post("/chat", headers=dev_headers, json=payload)

    assert response.status_code in (400, 422), response.text
    assert history(client, dev_headers, conversation) == before
    assert len(list(edit_stub.uploads.iterdir())) == 1
    assert edit_stub.calls == []
    assert edit_stub.generation_calls == []


@pytest.mark.parametrize("failure", ["false", "exception"])
def test_database_save_failure_cleans_all_uploaded_references_without_partial_message(
    client, dev_headers, edit_stub, monkeypatch, failure,
):
    import services.chat_service as chat
    from fastapi import HTTPException
    from routers.chat import ChatRequest

    conversation = new_conversation(client, dev_headers)
    observed_uploads = []

    async def fail_save(*args, **kwargs):
        observed_uploads.extend(edit_stub.uploads.glob("reference_*.png"))
        if failure == "exception":
            raise RuntimeError("isolated test database failure")
        return False

    monkeypatch.setattr(chat, "save_message", fail_save)
    request = ChatRequest(**edit_payload(conversation, [
        {"image_base64": encoded_image()}, {"image_base64": encoded_image("WEBP")},
    ]))

    async def scenario():
        with pytest.raises((HTTPException, RuntimeError)):
            await chat.build_context(request, "smoke_tester")

    asyncio.run(scenario())
    assert len(observed_uploads) == 2
    assert list(edit_stub.uploads.iterdir()) == []
    assert history(client, dev_headers, conversation) == []
    assert edit_stub.calls == []


@pytest.mark.parametrize("cancel_phase", ["before_commit", "after_commit"])
def test_cancellation_waits_for_user_message_commit_and_retains_all_durable_uploads(
    client, dev_headers, edit_stub, monkeypatch, cancel_phase,
):
    import services.chat_service as chat
    from routers.chat import ChatRequest

    conversation = new_conversation(client, dev_headers)
    original_save = chat.save_message
    request = ChatRequest(**edit_payload(conversation, [
        {"image_base64": encoded_image()}, {"image_base64": encoded_image("JPEG")},
    ]))

    async def scenario():
        reached, release = asyncio.Event(), asyncio.Event()

        async def paused_save(*args, **kwargs):
            assert len(list(edit_stub.uploads.glob("reference_*.png"))) == 2
            if cancel_phase == "before_commit":
                reached.set()
                await release.wait()
            saved = await original_save(*args, **kwargs)
            if cancel_phase == "after_commit":
                reached.set()
                await release.wait()
            return saved

        monkeypatch.setattr(chat, "save_message", paused_save)
        task = asyncio.create_task(chat.build_context(request, "smoke_tester"))
        try:
            await asyncio.wait_for(reached.wait(), timeout=2)
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    rows = history(client, dev_headers, conversation)
    assert len(rows) == 1 and rows[0]["role"] == "user"
    assert len(rows[0]["reference_image_paths"]) == 2
    for path in rows[0]["reference_image_paths"]:
        assert client.get(path, headers=dev_headers).status_code == 200
    assert len(list(edit_stub.uploads.iterdir())) == 2
    assert edit_stub.calls == []


@pytest.mark.parametrize("cancel_phase", ["before_commit", "after_commit"])
def test_anyio_request_cancellation_also_finishes_reference_commit_before_cleanup(
    client, dev_headers, edit_stub, monkeypatch, cancel_phase,
):
    import anyio
    import services.chat_service as chat
    from routers.chat import ChatRequest

    conversation = new_conversation(client, dev_headers)
    original_save = chat.save_message
    request = ChatRequest(**edit_payload(conversation, [
        {"image_base64": encoded_image()}, {"image_base64": encoded_image("JPEG")},
    ]))

    async def scenario():
        reached, release = asyncio.Event(), asyncio.Event()

        async def paused_save(*args, **kwargs):
            if cancel_phase == "before_commit":
                reached.set()
                await release.wait()
            saved = await original_save(*args, **kwargs)
            if cancel_phase == "after_commit":
                reached.set()
                await release.wait()
            return saved

        monkeypatch.setattr(chat, "save_message", paused_save)
        with anyio.fail_after(3):
            async with anyio.create_task_group() as group:
                group.start_soon(chat.build_context, request, "smoke_tester")
                try:
                    await reached.wait()
                    group.cancel_scope.cancel()
                finally:
                    release.set()

    asyncio.run(scenario())
    rows = history(client, dev_headers, conversation)
    assert len(rows) == 1 and rows[0]["role"] == "user"
    assert len(rows[0]["reference_image_paths"]) == 2
    for path in rows[0]["reference_image_paths"]:
        assert client.get(path, headers=dev_headers).status_code == 200
    assert len(list(edit_stub.uploads.iterdir())) == 2
    assert edit_stub.calls == []


def test_failed_edit_keeps_accepted_paths_and_retry_reuses_them_without_reupload_or_charge(
    client, dev_headers, edit_stub, monkeypatch,
):
    import database
    import services.chat_service as chat
    from auth import create_token

    conversation = new_conversation(client, dev_headers)
    balance = asyncio.run(database.get_strawberry_balance("smoke_tester"))

    async def fail(prompt, references, aspect_ratio=None):
        edit_stub.calls.append((prompt, list(references), aspect_ratio))
        raise chat.ImageGenerationError("图片修改等待超时，请重试。")

    monkeypatch.setattr(chat, "edit_image", fail)
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token('smoke_tester')}"}
    payload = edit_payload(conversation, [
        {"image_base64": encoded_image()}, {"image_base64": encoded_image("JPEG")},
    ])
    first = events(client.post("/chat", headers=headers, json=payload))
    references = selected_paths(first)
    assert first[-1] == {"error": "图片修改等待超时，请重试。"}
    assert not any("generated_image" in event or "done" in event for event in first)
    assert asyncio.run(database.get_strawberry_balance("smoke_tester")) == balance
    rows = history(client, headers, conversation)
    assert len(rows) == 1 and rows[0]["reference_image_paths"] == references
    originals = {path: client.get(path, headers=headers).content for path in references}
    assert len(list(edit_stub.uploads.iterdir())) == 2

    monkeypatch.setattr(chat, "edit_image", edit_stub.edit)
    retry = events(client.post("/chat", headers=headers, json=edit_payload(
        conversation, [{"image_path": path} for path in references], "继续使用刚才两张参考图",
    )))
    assert selected_paths(retry) == references
    assert generated_result(retry)["reference_image_paths"] == references
    assert edit_stub.calls[-1] == ("继续使用刚才两张参考图", references, None)
    assert len(list(edit_stub.uploads.iterdir())) == 3
    for path in references:
        response = client.get(path, headers=headers)
        assert response.status_code == 200 and response.content == originals[path]


@pytest.mark.parametrize("bypass", ["0", "1"])
def test_external_and_generated_images_stay_owner_private_even_with_dev_bypass(
    client, dev_headers, edit_stub, monkeypatch, bypass,
):
    conversation = new_conversation(client, dev_headers)
    output = events(client.post("/chat", headers=dev_headers, json=edit_payload(
        conversation, [{"image_base64": encoded_image()}],
    )))
    references = selected_paths(output)
    result = generated_result(output)
    other_headers = {"X-Dev-User": "external_ref_viewer"}
    new_conversation(client, other_headers)
    client.cookies.clear()
    monkeypatch.setenv("DEV_AUTH_BYPASS", bypass)
    monkeypatch.setenv("DEV_MODE", "1")

    for path in [*references, result["image_path"]]:
        assert client.get(path).status_code == 401
        assert client.head(path).status_code == 401
        assert client.get(path, headers=other_headers).status_code == 404
        owner = client.get(path, headers=dev_headers)
        assert owner.status_code == 200
        assert owner.headers["cache-control"] == "private, no-store"
        download = client.get(path + "?download=1", headers=dev_headers)
        assert download.status_code == 200 and download.content == owner.content
        assert "attachment" in download.headers["content-disposition"]
        aliased = path.replace("/uploads/", "/uploads/unused/%2e%2e/")
        assert client.get(aliased).status_code == 401


@pytest.mark.parametrize("prefix", ["reference_", "generated_", ".reference_", ".generated_"])
def test_uncommitted_reference_and_generation_files_cannot_be_read_during_normalization(
    client, dev_headers, edit_stub, monkeypatch, prefix,
):
    suffix = ".tmp" if prefix.startswith(".") else ".png"
    filename = f"{prefix}{uuid4().hex}{suffix}"
    attachment = edit_stub.uploads / filename
    attachment.write_bytes(image_bytes())
    path = f"/uploads/{filename}"
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    client.cookies.clear()

    assert client.get(path).status_code == 401
    assert client.head(path).status_code == 401
    assert client.get(path + "?download=1").status_code == 401
    assert client.get(path, headers=dev_headers).status_code == 404
    assert attachment.exists()


@pytest.mark.parametrize("scope", ["user_message", "conversation", "history", "account"])
def test_new_uploaded_reference_cleanup_uses_all_retained_paths(
    client, dev_headers, edit_stub, scope,
):
    import database

    conversation = new_conversation(client, dev_headers)
    output = events(client.post("/chat", headers=dev_headers, json=edit_payload(
        conversation, [{"image_base64": encoded_image()}, {"image_base64": encoded_image("WEBP")}],
    )))
    references = selected_paths(output)
    result = generated_result(output)
    if scope == "user_message":
        user = history(client, dev_headers, conversation)[0]
        response = client.delete(f"/message/{user['id']}", headers=dev_headers)
    elif scope == "conversation":
        response = client.delete(f"/conversations/{conversation}", headers=dev_headers)
    elif scope == "history":
        response = client.delete("/history", headers=dev_headers)
    else:
        response = client.request("DELETE", "/account", headers=dev_headers,
                                  json={"confirmation": "smoke_tester"})

    assert response.status_code == 200, response.text
    for path in references:
        assert not (edit_stub.uploads / path.rsplit("/", 1)[-1]).exists()
    if scope == "user_message":
        assert client.get(result["image_path"], headers=dev_headers).status_code == 200
        assert len(list(edit_stub.uploads.iterdir())) == 1
    else:
        assert list(edit_stub.uploads.iterdir()) == []
    assert asyncio.run(database.get_pending_upload_cleanup()) == []
