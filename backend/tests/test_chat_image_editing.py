"""Chat image edits retain an owned reference and publish only persisted results."""
import asyncio
import json
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


def edit_request(client, headers, conversation, reference, message="把天空改成清晨薄雾", **extra):
    return client.post("/chat", headers=headers, json={
        "conversation_id": conversation,
        "message": message,
        "mode": "image_edit",
        "reference_image_path": reference,
        **extra,
    })


@pytest.fixture
def edit_stub(client, monkeypatch, tmp_path):
    """All image bytes are local fixtures; no generation or editing provider is called."""
    import database
    import main
    import services.chat_service as chat
    from utils import media

    uploads = tmp_path / "edit-uploads"
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

    def seed(conversation, owner="smoke_tester"):
        reference = make_image()
        assert asyncio.run(database.save_message(
            owner, "assistant", "图片已生成。", reference, conversation_id=conversation,
        )) is True
        return reference

    async def edit(prompt, reference_image_path, aspect_ratio=None):
        calls.append((prompt, reference_image_path, aspect_ratio))
        return {"image_path": make_image(), "model": "qwen-image-edit-test",
                "width": 24, "height": 16}

    async def no_text_to_image(*args, **kwargs):
        generation_calls.append((args, kwargs))
        raise AssertionError("image_edit must not call text-to-image generation")

    monkeypatch.setattr(chat, "edit_image", edit)
    monkeypatch.setattr(chat, "generate_image", no_text_to_image)
    return SimpleNamespace(calls=calls, generation_calls=generation_calls,
                           uploads=uploads, seed=seed, make_image=make_image)


@pytest.mark.parametrize("ratio", [None, "1:1", "16:9", "9:16"])
def test_edit_uses_full_instruction_and_preserves_reference_in_history(
    client, dev_headers, edit_stub, monkeypatch, ratio,
):
    import services.chat_service as chat

    def unexpected_routing(*args, **kwargs):
        raise AssertionError("explicit image editing must bypass companion routing")

    monkeypatch.setattr(chat, "detect_mode", unexpected_routing)
    monkeypatch.setattr(chat, "recognize_intent", unexpected_routing)
    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)
    source_bytes = (edit_stub.uploads / reference.rsplit("/", 1)[-1]).read_bytes()
    prompt = "保持古庙轮廓、人物身份与衣服，只将天空改成青灰晨雾，加入透过树林的自然光。" * 70
    options = {} if ratio is None else {"aspect_ratio": ratio}
    output = events(edit_request(client, dev_headers, conversation, reference, prompt, **options))

    assert edit_stub.calls == [(prompt, reference, ratio)]
    generated = next(item["generated_image"] for item in output if "generated_image" in item)
    assert output == [
        {"status": "editing_image", "message": "正在按要求修改参考图，请稍候…"},
        {"generated_image": generated}, {"text": "图片已修改。"}, {"done": True},
    ]
    assert generated["reference_image_path"] == reference
    assert generated["image_path"] != reference
    rows = history(client, dev_headers, conversation)
    assert [(row["role"], row["content"], row["image_path"]) for row in rows] == [
        ("assistant", "图片已生成。", reference),
        ("user", prompt, reference),
        ("assistant", "图片已修改。", generated["image_path"]),
    ]
    assert (edit_stub.uploads / reference.rsplit("/", 1)[-1]).read_bytes() == source_bytes
    assert client.get(reference, headers=dev_headers).status_code == 200
    assert client.get(generated["image_path"], headers=dev_headers).status_code == 200


def test_repeated_edit_uses_new_selected_image_without_overwriting_previous_result(
    client, dev_headers, edit_stub,
):
    conversation = new_conversation(client, dev_headers)
    original = edit_stub.seed(conversation)
    first = events(edit_request(client, dev_headers, conversation, original, "加入晨雾"))
    first_image = next(item["generated_image"]["image_path"] for item in first if "generated_image" in item)
    second = events(edit_request(client, dev_headers, conversation, first_image, "仅把人物衣服改成墨绿"))
    second_image = next(item["generated_image"] for item in second if "generated_image" in item)

    assert edit_stub.calls == [("加入晨雾", original, None), ("仅把人物衣服改成墨绿", first_image, None)]
    assert second_image["reference_image_path"] == first_image
    assert len({original, first_image, second_image["image_path"]}) == 3
    rows = history(client, dev_headers, conversation)
    assert [row["image_path"] for row in rows] == [
        original, original, first_image, first_image, second_image["image_path"],
    ]
    for path in (original, first_image, second_image["image_path"]):
        assert client.get(path, headers=dev_headers).status_code == 200


@pytest.mark.parametrize("source_owner,target_owner,target_is_source", [
    ("other_image_owner", "smoke_tester", False),
    ("other_image_owner", "smoke_tester", True),
    ("smoke_tester", "smoke_tester", False),
])
def test_reference_must_belong_to_same_account_and_conversation_before_any_write(
    client, dev_headers, edit_stub, source_owner, target_owner, target_is_source,
):
    owner_headers = {"X-Dev-User": source_owner}
    target_headers = {"X-Dev-User": target_owner}
    source_conversation = new_conversation(client, owner_headers)
    reference = edit_stub.seed(source_conversation, source_owner)
    own_target = new_conversation(client, target_headers)
    target = source_conversation if target_is_source else own_target
    before_source = history(client, owner_headers, source_conversation)
    before_target = history(client, target_headers, own_target)

    response = edit_request(client, target_headers, target, reference)

    assert response.status_code == 404, response.text
    assert edit_stub.calls == []
    assert history(client, owner_headers, source_conversation) == before_source
    assert history(client, target_headers, own_target) == before_target
    assert client.get(reference, headers=owner_headers).status_code == 200


def test_unreferenced_file_is_not_authority_to_edit_or_read(client, dev_headers, edit_stub):
    conversation = new_conversation(client, dev_headers)
    unowned_file = edit_stub.make_image()
    missing_file = f"/uploads/generated_{uuid4().hex}.png"

    for reference in (unowned_file, missing_file):
        response = edit_request(client, dev_headers, conversation, reference)
        assert response.status_code == 404, response.text
        assert client.get(reference, headers=dev_headers).status_code == 404
    assert edit_stub.calls == []
    assert history(client, dev_headers, conversation) == []


@pytest.mark.parametrize("reference", [
    "/uploads/generated_short.png",
    "/uploads/generated_" + "g" * 32 + ".png",
    "/uploads/generated_" + "a" * 32 + ".jpg",
    "/uploads/../generated_" + "a" * 32 + ".png",
    "/uploads/%2e%2e/generated_" + "a" * 32 + ".png",
    "https://example.com/generated_" + "a" * 32 + ".png",
    "/uploads/image_" + "a" * 32 + ".png",
    "/uploads/generated_" + "a" * 32 + ".png?download=1",
])
def test_invalid_reference_path_fails_validation_without_writing_or_calling_provider(
    client, dev_headers, edit_stub, reference,
):
    conversation = new_conversation(client, dev_headers)
    response = edit_request(client, dev_headers, conversation, reference)
    assert response.status_code == 422, response.text
    assert edit_stub.calls == []
    assert history(client, dev_headers, conversation) == []


@pytest.mark.parametrize("extra", [
    {"reference_image_path": None},
    {"message": ""},
    {"message": " \n\t "},
    {"image_base64": "not-an-image"},
    {"mode": "chat"},
    {"mode": "image"},
])
def test_edit_rejects_missing_reference_blank_changes_upload_mix_and_other_modes(
    client, dev_headers, edit_stub, monkeypatch, extra,
):
    import services.chat_service as chat

    def forbidden_upload(*args, **kwargs):
        raise AssertionError("invalid editing request must fail before saving any upload")

    monkeypatch.setattr(chat, "_save_uploaded_image", forbidden_upload)
    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)
    before = history(client, dev_headers, conversation)
    payload = {"conversation_id": conversation, "message": "加入薄雾", "mode": "image_edit",
               "reference_image_path": reference, **extra}

    response = client.post("/chat", headers=dev_headers, json=payload)

    assert response.status_code == 400, response.text
    assert edit_stub.calls == []
    assert history(client, dev_headers, conversation) == before
    assert len(list(edit_stub.uploads.iterdir())) == 1


def test_original_assistant_deletion_retains_user_reference_and_owner_media_access(
    client, dev_headers, edit_stub,
):
    import database

    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)
    source_message = history(client, dev_headers, conversation)[0]
    output = events(edit_request(client, dev_headers, conversation, reference))
    generated = next(item["generated_image"]["image_path"] for item in output if "generated_image" in item)

    response = client.delete(f"/message/{source_message['id']}", headers=dev_headers)

    assert response.status_code == 200, response.text
    rows = history(client, dev_headers, conversation)
    assert [(row["role"], row["image_path"]) for row in rows] == [("user", reference), ("assistant", generated)]
    assert client.get(reference, headers=dev_headers).status_code == 200
    assert client.get(reference, headers={"X-Dev-User": "other_image_viewer"}).status_code == 404
    assert asyncio.run(database.get_pending_upload_cleanup()) == []
    # The retained user message is sufficient provenance for another deliberate edit.
    assert events(edit_request(client, dev_headers, conversation, reference, "再增加少量晨光"))[-1] == {"done": True}


def test_failed_edit_has_no_success_attachment_or_charge_and_keeps_source(
    client, dev_headers, edit_stub, monkeypatch,
):
    import database
    import services.chat_service as chat
    from auth import create_token

    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)
    source_bytes = (edit_stub.uploads / reference.rsplit("/", 1)[-1]).read_bytes()
    balance = asyncio.run(database.get_strawberry_balance("smoke_tester"))

    async def fail(prompt, source, aspect_ratio=None):
        edit_stub.calls.append((prompt, source, aspect_ratio))
        raise chat.ImageGenerationError("图片修改等待超时，请稍后再试。")

    monkeypatch.setattr(chat, "edit_image", fail)
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token('smoke_tester')}"}
    output = events(edit_request(client, headers, conversation, reference, "只修改晨雾"))

    assert output == [
        {"status": "editing_image", "message": "正在按要求修改参考图，请稍候…"},
        {"error": "图片修改等待超时，请稍后再试。"},
    ]
    assert edit_stub.calls == [("只修改晨雾", reference, None)]
    assert asyncio.run(database.get_strawberry_balance("smoke_tester")) == balance
    rows = history(client, headers, conversation)
    assert [(row["role"], row["image_path"]) for row in rows] == [("assistant", reference), ("user", reference)]
    assert (edit_stub.uploads / reference.rsplit("/", 1)[-1]).read_bytes() == source_bytes
    assert client.get(reference, headers=headers).status_code == 200
    assert len(list(edit_stub.uploads.iterdir())) == 1
    assert "smoke_tester" not in chat._IMAGE_GENERATION_USERS


@pytest.mark.parametrize("pending_intent", ["route", "generate_image"])
def test_edit_takes_priority_over_mirror_and_clears_old_pending(
    client, dev_headers, edit_stub, monkeypatch, pending_intent,
):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending

    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)
    key = ("smoke_tester", conversation)
    set_pending(key, {"intent": pending_intent, "params": {}, "missing": ["origin"]})
    mode_calls = []

    def mirror(*args, **kwargs):
        mode_calls.append(args)
        return "mirror"

    monkeypatch.setattr(chat, "detect_mode", mirror)
    output = events(edit_request(client, dev_headers, conversation, reference, "改成更安静的晨雾画面"))

    assert mode_calls == []
    assert edit_stub.calls == [("改成更安静的晨雾画面", reference, None)]
    assert next(item["generated_image"] for item in output if "generated_image" in item)["reference_image_path"] == reference
    assert get_pending(key) is None


@pytest.mark.parametrize("message", [
    "把刚才生成的图片的天空改成黄昏",
    "修改这张图片，把人物去掉",
    "帮我生成一张参考原图的图片，天空改成黄昏",
])
@pytest.mark.parametrize("pending_intent", [None, "route", "generate_image"])
def test_chat_edit_without_selection_requests_explicit_reference_and_never_guesses(
    client, dev_headers, edit_stub, monkeypatch, message, pending_intent,
):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending

    conversation = new_conversation(client, dev_headers)
    reference = edit_stub.seed(conversation)
    key = ("smoke_tester", conversation)
    if pending_intent:
        set_pending(key, {"intent": pending_intent, "params": {}, "missing": ["origin"]})
    mode_calls = []

    def mirror(*args, **kwargs):
        mode_calls.append(args)
        return "mirror"

    monkeypatch.setattr(chat, "detect_mode", mirror)
    output = events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": message,
    }))

    assert len(output) == 2 and output[-1] == {"done": True}, output
    assert "以此图修改" in output[0]["text"]
    assert edit_stub.calls == []
    assert edit_stub.generation_calls == []
    assert mode_calls == []
    assert get_pending(key) is None
    rows = history(client, dev_headers, conversation)
    assert [(row["role"], row["image_path"]) for row in rows] == [
        ("assistant", reference), ("user", None), ("assistant", None),
    ]
    assert len(list(edit_stub.uploads.iterdir())) == 1
