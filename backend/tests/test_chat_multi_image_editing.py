"""Multi-reference edits authorize, retain and clean up every selected image."""
import asyncio
import json
import sqlite3
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


def edit_request(client, headers, conversation, references, message="融合图一的人物和图二的古庙背景", **extra):
    return client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message, "mode": "image_edit",
        "reference_image_paths": references, **extra,
    })


def generated_result(output):
    generated = [event["generated_image"] for event in output if "generated_image" in event]
    assert len(generated) == 1, output
    assert output[-1] == {"done": True}, output
    assert not any("error" in event for event in output), output
    return generated[0]


def remove_messages(client, headers, messages):
    for message in messages:
        response = client.delete(f"/message/{message['id']}", headers=headers)
        assert response.status_code == 200, response.text


@pytest.fixture
def edit_stub(client, monkeypatch, tmp_path):
    import database
    import main
    import services.chat_service as chat
    from utils import media

    uploads = tmp_path / "multi-edit-uploads"
    uploads.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(uploads))
    static = next(route.app for route in main.app.routes if getattr(route, "name", None) == "uploads")
    monkeypatch.setattr(static, "directory", str(uploads))
    monkeypatch.setattr(static, "all_directories", [str(uploads)])
    calls = []
    generation_calls = []

    def make_image():
        filename = f"generated_{uuid4().hex}.png"
        Image.new("RGB", (24, 16), color="darkgreen").save(uploads / filename)
        return f"/uploads/{filename}"

    def seed(conversation, owner="smoke_tester", count=1):
        references = []
        for _ in range(count):
            reference = make_image()
            assert asyncio.run(database.save_message(
                owner, "assistant", "图片已生成。", reference, conversation_id=conversation,
            )) is True
            references.append(reference)
        return references

    async def edit(prompt, references, aspect_ratio=None):
        calls.append((prompt, list(references) if isinstance(references, list) else references, aspect_ratio))
        return {"image_path": make_image(), "model": "qwen-multi-image-edit-test",
                "width": 24, "height": 16}

    async def no_generation(*args, **kwargs):
        generation_calls.append((args, kwargs))
        raise AssertionError("reference editing must not invoke text-to-image generation")

    monkeypatch.setattr(chat, "edit_image", edit)
    monkeypatch.setattr(chat, "generate_image", no_generation)
    return SimpleNamespace(calls=calls, generation_calls=generation_calls,
                           uploads=uploads, seed=seed, make_image=make_image)


@pytest.mark.parametrize("count", [2, 3])
@pytest.mark.parametrize("ratio", [None, "16:9"])
def test_multiple_references_preserve_selected_order_and_publish_one_saved_result(
    client, dev_headers, edit_stub, count, ratio,
):
    import database

    conversation = new_conversation(client, dev_headers)
    # Select in the reverse of creation order: image numbering is user-defined.
    references = list(reversed(edit_stub.seed(conversation, count=count)))
    source_bytes = {path: client.get(path, headers=dev_headers).content for path in references}
    prompt = "图一人物进入图二古庙场景，保持人物身份；有图三时只借用图三的青灰晨雾色调。" * 60
    options = {} if ratio is None else {"aspect_ratio": ratio}
    output = events(edit_request(client, dev_headers, conversation, references, prompt, **options))
    generated = generated_result(output)

    assert edit_stub.calls == [(prompt, references, ratio)]
    assert edit_stub.generation_calls == []
    assert output[0]["status"] == "editing_image"
    assert generated["reference_image_path"] == references[0]
    assert generated["reference_image_paths"] == references
    assert generated["image_path"] not in references
    assert [event["text"] for event in output if "text" in event] == ["图片已修改。"]
    rows = history(client, dev_headers, conversation)
    assert len(rows) == count + 2
    assert (rows[-2]["role"], rows[-2]["content"], rows[-2]["image_path"]) == ("user", prompt, references[0])
    assert rows[-2]["reference_image_paths"] == references
    assert (rows[-1]["role"], rows[-1]["content"], rows[-1]["image_path"]) == (
        "assistant", "图片已修改。", generated["image_path"],
    )
    with sqlite3.connect(database.DB_PATH) as db:
        raw = db.execute("SELECT reference_image_paths FROM messages WHERE id = ?", (rows[-2]["id"],)).fetchone()[0]
    assert json.loads(raw) == references
    all_history = client.get("/history", headers=dev_headers)
    assert all_history.status_code == 200
    assert next(row for row in all_history.json()["messages"] if row["id"] == rows[-2]["id"])["reference_image_paths"] == references
    assert len(list(edit_stub.uploads.iterdir())) == count + 1
    for path in references:
        response = client.get(path, headers=dev_headers)
        assert response.status_code == 200
        assert response.content == source_bytes[path]


@pytest.mark.parametrize("source_kind", ["other_account", "other_conversation", "unreferenced_file", "missing_file"])
@pytest.mark.parametrize("bad_position", [0, 1, 2])
def test_one_unauthorized_reference_rejects_entire_request_without_partial_write(
    client, dev_headers, edit_stub, source_kind, bad_position,
):
    conversation = new_conversation(client, dev_headers)
    valid = edit_stub.seed(conversation, count=2)
    other_headers = {"X-Dev-User": "multi_image_other"}
    other_owner = "multi_image_other" if source_kind == "other_account" else "smoke_tester"
    source_headers = other_headers if source_kind == "other_account" else dev_headers
    other_conversation = new_conversation(client, source_headers)
    if source_kind in {"other_account", "other_conversation"}:
        invalid = edit_stub.seed(other_conversation, other_owner)[0]
    elif source_kind == "unreferenced_file":
        invalid = edit_stub.make_image()
    else:
        invalid = f"/uploads/generated_{uuid4().hex}.png"
    references = valid.copy()
    references.insert(bad_position, invalid)
    before_target = history(client, dev_headers, conversation)
    before_source = history(client, source_headers, other_conversation)

    response = edit_request(client, dev_headers, conversation, references)

    assert response.status_code == 404, response.text
    assert edit_stub.calls == []
    assert edit_stub.generation_calls == []
    assert history(client, dev_headers, conversation) == before_target
    assert history(client, source_headers, other_conversation) == before_source
    for path in valid:
        assert client.get(path, headers=dev_headers).status_code == 200


@pytest.mark.parametrize("case,status", [
    ("empty", 422), ("too_many", 422), ("not_array", 422), ("object", 422),
    ("invalid_path", 422), ("invalid_type", 422), ("null_item", 422),
    ("duplicate", 400), ("both_fields", 400), ("chat_mode", 400), ("image_mode", 400),
    ("mixed_upload", 400),
])
def test_invalid_multi_reference_options_fail_before_write_upload_or_provider(
    client, dev_headers, edit_stub, monkeypatch, case, status,
):
    import services.chat_service as chat

    def no_upload(*args, **kwargs):
        raise AssertionError("invalid edit must not save uploaded bytes")

    monkeypatch.setattr(chat, "_save_uploaded_image", no_upload)
    conversation = new_conversation(client, dev_headers)
    references = edit_stub.seed(conversation, count=3)
    payload = {"conversation_id": conversation, "message": "融合参考图", "mode": "image_edit",
               "reference_image_paths": references[:2]}
    if case == "empty":
        payload["reference_image_paths"] = []
    elif case == "too_many":
        payload["reference_image_paths"] = references + [f"/uploads/generated_{uuid4().hex}.png"]
    elif case == "not_array":
        payload["reference_image_paths"] = references[0]
    elif case == "object":
        payload["reference_image_paths"] = {"first": references[0]}
    elif case == "invalid_path":
        payload["reference_image_paths"] = [references[0], "/uploads/../generated_" + "a" * 32 + ".png"]
    elif case == "invalid_type":
        payload["reference_image_paths"] = [references[0], 17]
    elif case == "null_item":
        payload["reference_image_paths"] = [references[0], None]
    elif case == "duplicate":
        payload["reference_image_paths"] = [references[0], references[0]]
    elif case == "both_fields":
        payload["reference_image_path"] = references[0]
    elif case in {"chat_mode", "image_mode"}:
        payload["mode"] = case.removesuffix("_mode")
    elif case == "mixed_upload":
        payload["image_base64"] = "not-an-image"
    before = history(client, dev_headers, conversation)

    response = client.post("/chat", headers=dev_headers, json=payload)

    assert response.status_code == status, response.text
    assert history(client, dev_headers, conversation) == before
    assert edit_stub.calls == []
    assert edit_stub.generation_calls == []
    assert len(list(edit_stub.uploads.iterdir())) == 3


@pytest.mark.parametrize("field", ["reference_image_path", "reference_image_paths"])
def test_single_reference_keeps_legacy_provider_argument_and_history_compatibility(
    client, dev_headers, edit_stub, field,
):
    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)[0]
    prompt = "只把天空改成清晨"
    payload = {"conversation_id": conversation, "message": prompt, "mode": "image_edit",
               field: reference if field == "reference_image_path" else [reference]}
    generated = generated_result(events(client.post("/chat", headers=dev_headers, json=payload)))

    assert edit_stub.calls == [(prompt, reference, None)]
    assert generated["reference_image_path"] == reference
    assert generated["reference_image_paths"] == [reference]
    rows = history(client, dev_headers, conversation)
    assert rows[-2]["image_path"] == reference
    assert rows[-2]["reference_image_paths"] == [reference]


@pytest.mark.parametrize("count", [2, 3])
def test_deleted_originals_remain_readable_and_editable_via_retained_user_array(
    client, dev_headers, edit_stub, count,
):
    import database

    conversation = new_conversation(client, dev_headers)
    references = edit_stub.seed(conversation, count=count)
    originals = history(client, dev_headers, conversation)
    result = generated_result(events(edit_request(client, dev_headers, conversation, references)))
    other_headers = {"X-Dev-User": "multi_image_viewer"}
    new_conversation(client, other_headers)

    for original in originals:
        remove_messages(client, dev_headers, [original])
        for reference in references:
            assert client.get(reference, headers=dev_headers).status_code == 200
            assert client.head(reference, headers=dev_headers).status_code == 200
            assert client.get(reference + "?download=1", headers=dev_headers).status_code == 200
            assert client.get(reference, headers=other_headers).status_code == 404
    assert asyncio.run(database.get_pending_upload_cleanup()) == []
    remaining = history(client, dev_headers, conversation)
    assert len(remaining) == 2
    assert remaining[0]["reference_image_paths"] == references
    # Reverse again, proving authorization checks JSON-only references 2 and 3.
    next_references = list(reversed(references))
    edited_again = generated_result(events(edit_request(client, dev_headers, conversation, next_references, "再把晨雾调淡")))
    assert edit_stub.calls[-1] == ("再把晨雾调淡", next_references, None)
    assert edited_again["reference_image_paths"] == next_references
    assert edited_again["image_path"] != result["image_path"]


def test_deleting_only_remaining_user_reference_cleans_every_source_but_keeps_result(
    client, dev_headers, edit_stub,
):
    import database

    conversation = new_conversation(client, dev_headers)
    references = edit_stub.seed(conversation, count=3)
    originals = history(client, dev_headers, conversation)
    result = generated_result(events(edit_request(client, dev_headers, conversation, references)))
    remove_messages(client, dev_headers, originals)
    user = next(row for row in history(client, dev_headers, conversation) if row["role"] == "user")

    remove_messages(client, dev_headers, [user])

    for reference in references:
        assert not (edit_stub.uploads / reference.rsplit("/", 1)[-1]).exists()
        assert client.get(reference, headers=dev_headers).status_code == 404
    assert client.get(result["image_path"], headers=dev_headers).status_code == 200
    assert len(list(edit_stub.uploads.iterdir())) == 1
    assert [row["image_path"] for row in history(client, dev_headers, conversation)] == [result["image_path"]]
    assert asyncio.run(database.get_pending_upload_cleanup()) == []


@pytest.mark.parametrize("scope", ["conversation", "history", "account"])
def test_bulk_deletion_cleans_json_only_references_without_touching_other_owner(
    client, dev_headers, edit_stub, scope,
):
    import database

    conversation = new_conversation(client, dev_headers)
    references = edit_stub.seed(conversation, count=3)
    originals = history(client, dev_headers, conversation)
    result = generated_result(events(edit_request(client, dev_headers, conversation, references)))
    remove_messages(client, dev_headers, originals)
    other_headers = {"X-Dev-User": "multi_image_other_owner"}
    other_conversation = new_conversation(client, other_headers)
    other_image = edit_stub.seed(other_conversation, "multi_image_other_owner")[0]
    other_history = history(client, other_headers, other_conversation)

    if scope == "conversation":
        response = client.delete(f"/conversations/{conversation}", headers=dev_headers)
    elif scope == "history":
        response = client.delete("/history", headers=dev_headers)
    else:
        response = client.request("DELETE", "/account", headers=dev_headers,
                                  json={"confirmation": "smoke_tester"})

    assert response.status_code == 200, response.text
    for path in [*references, result["image_path"]]:
        assert not (edit_stub.uploads / path.rsplit("/", 1)[-1]).exists()
    assert len(list(edit_stub.uploads.iterdir())) == 1
    assert client.get(other_image, headers=other_headers).status_code == 200
    assert history(client, other_headers, other_conversation) == other_history
    assert asyncio.run(database.get_pending_upload_cleanup()) == []
    if scope == "conversation":
        assert client.get(f"/conversations/{conversation}/messages", headers=dev_headers).status_code == 404
    elif scope == "history":
        assert history(client, dev_headers, conversation) == []
    else:
        assert asyncio.run(database.get_session_version("smoke_tester")) is None


def test_failed_multi_edit_does_not_charge_or_publish_success_and_keeps_all_sources(
    client, dev_headers, edit_stub, monkeypatch,
):
    import database
    import services.chat_service as chat
    from auth import create_token

    conversation = new_conversation(client, dev_headers)
    references = edit_stub.seed(conversation, count=3)
    balance = asyncio.run(database.get_strawberry_balance("smoke_tester"))
    original_bytes = {path: client.get(path, headers=dev_headers).content for path in references}

    async def fail(prompt, selected, aspect_ratio=None):
        edit_stub.calls.append((prompt, list(selected), aspect_ratio))
        raise chat.ImageGenerationError("图片修改失败，请稍后重试。")

    monkeypatch.setattr(chat, "edit_image", fail)
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token('smoke_tester')}"}
    output = events(edit_request(client, headers, conversation, references, "融合三张参考图"))

    assert edit_stub.calls == [("融合三张参考图", references, None)]
    assert output[0]["status"] == "editing_image"
    assert output[-1] == {"error": "图片修改失败，请稍后重试。"}
    assert not any("generated_image" in event or "done" in event or "text" in event for event in output)
    assert asyncio.run(database.get_strawberry_balance("smoke_tester")) == balance
    rows = history(client, headers, conversation)
    assert [row["role"] for row in rows] == ["assistant", "assistant", "assistant", "user"]
    assert rows[-1]["reference_image_paths"] == references
    for path in references:
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.content == original_bytes[path]
    assert len(list(edit_stub.uploads.iterdir())) == 3
    assert "smoke_tester" not in chat._IMAGE_GENERATION_USERS


def test_multi_reference_schema_migration_preserves_legacy_single_images_and_is_idempotent(
    tmp_path, monkeypatch,
):
    import agent_store
    import database

    legacy_path = tmp_path / "legacy-multi-reference.db"
    legacy_image = "/uploads/generated_" + "a" * 32 + ".png"
    with sqlite3.connect(legacy_path) as db:
        db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, profile_json TEXT DEFAULT '{}')")
        db.execute("""CREATE TABLE messages (id INTEGER PRIMARY KEY, username TEXT, role TEXT,
                   content TEXT, image_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("INSERT INTO users (id, username) VALUES (7, 'old_image_owner')")
        db.executemany("""INSERT INTO messages (id, username, role, content, image_path, created_at)
                        VALUES (?, 'old_image_owner', ?, ?, ?, '2026-09-01 08:00:00')""", [
            (11, "assistant", "旧的生成图", legacy_image),
            (12, "user", "旧的上传图", "/uploads/legacy-upload.png"),
            (13, "user", "旧的纯文字", None),
        ])
        before = db.execute("SELECT id, username, role, content, image_path, created_at FROM messages ORDER BY id").fetchall()
    monkeypatch.setattr(database, "DB_PATH", str(legacy_path))

    asyncio.run(database.init_db())
    first_context = asyncio.run(agent_store.resolve_chat_conversation("old_image_owner"))
    with sqlite3.connect(legacy_path) as db:
        assert "reference_image_paths" in {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert db.execute("SELECT id, username, role, content, image_path, created_at FROM messages ORDER BY id").fetchall() == before
        first_rows = db.execute("SELECT * FROM messages ORDER BY id").fetchall()
    asyncio.run(database.init_db())
    with sqlite3.connect(legacy_path) as db:
        assert db.execute("SELECT * FROM messages ORDER BY id").fetchall() == first_rows
    assert asyncio.run(agent_store.resolve_chat_conversation("old_image_owner")) == first_context
    migrated = asyncio.run(agent_store.get_conversation_messages(
        "old_image_owner", first_context["conversation"]["id"],
    ))["messages"]
    assert [row["image_path"] for row in migrated] == [legacy_image, "/uploads/legacy-upload.png", None]
    assert all(isinstance(row["reference_image_paths"], list) for row in migrated)
