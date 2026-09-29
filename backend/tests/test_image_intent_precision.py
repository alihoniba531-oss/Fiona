"""The image regex proposes candidates; the model alone authorizes generation."""
import asyncio
import json

import pytest

from intent_router import INTENT_PROMPT, explicit_image_intent, image_generation_discussion


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from rate_limit import limiter
    import services.chat_service as chat

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(chat, "_IMAGE_GENERATION_USERS", set())


IMAGE_REQUESTS = [
    "画一只猫",
    "画只橘猫在窗台上晒太阳",
    "帮我画一只在月球上的猫",
    "给我画个头像，要二次元风格",
    "请画一幅水墨山水",
    "画张海报：周末市集，暖色调",
    "生成一张赛博朋克风格的城市夜景图片",
    "帮我生成一张海报，主题是读书会",
    "做一张生日贺卡的图片",
    "帮我做个头像",
    "能帮我画一只柯基吗",
    "可以给我生成一张壁纸吗",
    "画一幅竖版的星空",
    "帮我生成一张薄雾古庙图片",  # README 示例
    "画一条鱼",
    "画一座灯塔",
    "帮我生成一幅水彩画",
    "请画一张素描风格的自画像",
    "给我画一朵向日葵",
    "请画一张太空图",
]

IMAGE_DISCUSSIONS = [
    "画得真好看",
    "画的这是啥",
    "画画是我的爱好",
    "画展门票多少钱",
    "画一只猫难吗？",
    "画面感太强了，我脑子里一直是他离开的样子",
    "画风好喜欢",
    "画完了",
    "画了一下午",
    "做个头像要多少钱",
    "做一张海报一般要多久？",
    "做海报好累啊",
    "制作照片墙需要什么材料",
    "做头像好难",
    "你刚才画的不好",
    "生成图片要花多少草莓",
    "画一个圆要用什么软件",
    "做一个网站多少钱",
    "帮我画一只猫要多少钱？",
    "请画一张海报一般需要多久？",
    "画一只猫真好看",
    "画一只猫有多难",
    "画一只猫怎么画",
    "帮我生成一张猫图片的提示词",
    "画个图都这么费劲",
    "做一张海报要多少钱才合理",
    "制作一张头像的步骤有哪些",
    "画一只猫给朋友当礼物合适吗",
    "生成一张图片一般用什么模型",
    "做个头像能赚钱吗",
    "画一只狗真难啊",
    "做一张海报呗我也不知道",
    "画一只猫好不好",
    "画一张海报呢",
    "画一只猫太抽象了",
]


@pytest.mark.parametrize("message", IMAGE_REQUESTS)
def test_image_request_is_only_a_candidate(message):
    result = explicit_image_intent(message)
    assert result is not None
    assert result["intent"] == "generate_image"
    assert result["params"]["prompt"] == message
    assert result["missing"] == []


@pytest.mark.parametrize("message", IMAGE_DISCUSSIONS)
def test_image_discussion_with_null_model_never_generates(client, dev_headers, monkeypatch, message):
    import services.chat_service as chat

    classified = []
    generated = []

    def classify(_client, candidate, _history):
        classified.append(candidate)
        return {"intent": None}

    async def generate(*args):
        generated.append(args)
        raise AssertionError("a candidate alone cannot authorize image generation")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    output = _events(client.post("/chat", headers=dev_headers, json={"message": message}))
    assert classified == [message]
    assert generated == []
    assert not any("generated_image" in event for event in output)
    assert output[-1] == {"done": True}


def _events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_comment_reaches_model_intent_classifier_without_image_generation(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    classified = []
    generated = []

    def classify(*args, **kwargs):
        classified.append(args[1])
        return {"intent": None, "params": {}, "missing": []}

    async def generate(*args):
        generated.append(args)
        raise AssertionError("comment must not call image generation")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)

    output = _events(client.post("/chat", headers=dev_headers, json={"message": "画得真好看"}))
    assert classified == ["画得真好看"]
    assert generated == []
    assert not any("generated_image" in event for event in output)


def test_model_confirmed_candidate_generates_once_and_charges(client, dev_headers, monkeypatch, tmp_path):
    import services.chat_service as chat
    import database
    from auth import create_token
    from utils import media

    generated = []
    path = tmp_path / "generated_precision.png"
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))

    classified = []

    def classify(_client, message, _history):
        classified.append(message)
        return {"intent": "generate_image", "params": {
            "prompt": "橘猫在窗边晒太阳", "aspect_ratio": "16:9",
        }, "missing": []}

    async def generate(prompt, ratio):
        generated.append((prompt, ratio))
        path.write_bytes(b"test-image")
        return {"image_path": "/uploads/generated_precision.png", "model": "fake", "width": 1, "height": 1}

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)

    user = dev_headers["X-Dev-User"]
    assert client.post("/conversations", json={}, headers=dev_headers).status_code == 201
    before = asyncio.run(database.get_strawberry_balance(user))
    version = asyncio.run(database.get_session_version(user))
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}
    output = _events(client.post("/chat", headers=headers, json={"message": "画一只猫"}))
    assert classified == ["画一只猫"]
    assert generated == [("画一只猫", "16:9")]
    assert any("generated_image" in event for event in output)
    assert output[-1] == {"done": True}
    assert asyncio.run(database.get_strawberry_balance(user)) == before - 10


@pytest.mark.parametrize("classified", [
    {"intent": "generate_image", "params": {}, "missing": []},
    {"intent": "generate_image"},
])
def test_confirmed_candidate_without_model_prompt_uses_original_text(
    client, dev_headers, monkeypatch, tmp_path, classified,
):
    import services.chat_service as chat
    from utils import media

    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    path = tmp_path / "generated_original_prompt.png"
    classified_messages = []
    generated = []

    def classify(_client, message, _history):
        classified_messages.append(message)
        return classified

    async def generate(prompt, ratio):
        generated.append((prompt, ratio))
        path.write_bytes(b"test-image")
        return {"image_path": "/uploads/generated_original_prompt.png", "model": "fake", "width": 1, "height": 1}

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    output = _events(client.post("/chat", headers=dev_headers, json={"message": "画一只猫"}))
    assert classified_messages == ["画一只猫"]
    assert generated == [("画一只猫", "1:1")]
    assert any("generated_image" in event for event in output)
    assert not any("想生成什么画面" in event.get("text", "") for event in output)
    assert output[-1] == {"done": True}


def test_model_missing_prompt_overrides_populated_regex_candidate(client, dev_headers, monkeypatch):
    import database
    import services.chat_service as chat
    from auth import create_token
    from intent_router import get_pending

    message = "画一只猫"
    assert explicit_image_intent(message)["missing"] == []
    conversation = client.post("/conversations", json={}, headers=dev_headers).json()["conversation"]["id"]
    user = dev_headers["X-Dev-User"]
    before = asyncio.run(database.get_strawberry_balance(user))
    version = asyncio.run(database.get_session_version(user))
    generated = []
    classified = []

    def classify(_client, text, _history):
        classified.append(text)
        return {"intent": "generate_image", "params": {"prompt": "模型猜的猫"},
                "missing": ["prompt"]}

    async def generate(*args):
        generated.append(args)
        raise AssertionError("model says scene is missing")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}
    output = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": message,
    }))
    assert classified == [message]
    assert generated == []
    assert output[0]["text"].startswith("想生成什么画面")
    assert not any("generated_image" in event for event in output)
    assert get_pending((dev_headers["X-Dev-User"], conversation)) == {
        "intent": "generate_image", "params": {}, "missing": ["prompt"],
    }
    assert asyncio.run(database.get_strawberry_balance(user)) == before


@pytest.mark.parametrize("message,is_candidate", [
    ("你会画画吗", False),
    ("怎么生成图片", False),
    ("不要画了", False),
    ("帮我生成图片的教程", True),
])
def test_model_image_misclassification_of_discussion_never_generates(
    client, dev_headers, monkeypatch, message, is_candidate,
):
    """The discussion guard must work before either image routing path can charge."""
    import services.chat_service as chat

    assert bool(explicit_image_intent(message)) is is_candidate
    assert image_generation_discussion(message)
    classified = []
    generated = []

    def classify(_client, text, _history):
        classified.append(text)
        return {"intent": "generate_image", "params": {"prompt": "误判画面"}, "missing": []}

    async def generate(*args):
        generated.append(args)
        raise AssertionError("discussion must not generate an image")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    output = _events(client.post("/chat", headers=dev_headers, json={"message": message}))
    assert classified == [message]
    assert generated == []
    assert not any("generated_image" in event for event in output)
    assert any("测试" in event.get("text", "") for event in output)
    assert output[-1] == {"done": True}


@pytest.mark.parametrize("message,model_ratio,expected_ratio,is_candidate", [
    ("画一只在午夜灯塔边等船的黑猫，背景是潮汐与蓝色纸灯，横版16:9", "9:16", "16:9", True),
    ("午夜灯塔旁的黑猫与蓝色纸灯，请将海雾画出来", "9:16", "9:16", False),
    ("山顶风车与落日，请给我一幅正方形插画", "9:16", "1:1", False),
])
def test_natural_image_uses_complete_message_not_model_excerpt(
    client, dev_headers, monkeypatch, tmp_path, message, model_ratio, expected_ratio, is_candidate,
):
    """The classifier may truncate or rewrite a prompt; only the user text is sent."""
    import services.chat_service as chat
    from utils import media

    assert bool(explicit_image_intent(message)) is is_candidate
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    generated = []
    classified = []
    path = tmp_path / "complete_original.png"

    def classify(_client, text, _history):
        classified.append(text)
        return {"intent": "generate_image", "params": {
            "prompt": "黑猫", "aspect_ratio": model_ratio,
        }, "missing": []}

    async def generate(prompt, ratio):
        generated.append((prompt, ratio))
        path.write_bytes(b"test-image")
        return {"image_path": "/uploads/complete_original.png", "model": "fake", "width": 1, "height": 1}

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    output = _events(client.post("/chat", headers=dev_headers, json={"message": message}))
    assert classified == [message]
    assert generated == [(message, expected_ratio)]
    assert any("generated_image" in event for event in output)
    assert output[-1] == {"done": True}


@pytest.mark.parametrize("mode,expected_ratio,expected_classifications", [
    ("chat", "16:9", 1),
    ("image", "9:16", 0),
])
def test_text_ratio_precedes_chat_field_but_image_button_keeps_selection(
    client, dev_headers, monkeypatch, tmp_path, mode, expected_ratio, expected_classifications,
):
    import services.chat_service as chat
    from utils import media

    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    message = "画一只在雾中等船的黑猫，远处有灯塔，横版16:9"
    path = tmp_path / "ratio_precedence.png"
    classified = []
    generated = []

    def classify(_client, text, _history):
        classified.append(text)
        return {"intent": "generate_image", "params": {
            "prompt": "被缩短的黑猫", "aspect_ratio": "9:16",
        }, "missing": []}

    async def generate(prompt, ratio):
        generated.append((prompt, ratio))
        path.write_bytes(b"test-image")
        return {"image_path": "/uploads/ratio_precedence.png", "model": "fake", "width": 1, "height": 1}

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    output = _events(client.post("/chat", headers=dev_headers, json={
        "mode": mode, "aspect_ratio": "9:16", "message": message,
    }))
    assert classified == [message] * expected_classifications
    assert generated == [(message, expected_ratio)]
    assert any("generated_image" in event for event in output)
    assert output[-1] == {"done": True}


def test_intent_prompt_distinguishes_image_discussion_from_current_command():
    # This is a static guard; model behavior is deliberately not tested here.
    for distinction in ("价格、扣费、耗时、难度", "已生成结果的评价或抱怨", "回忆、愿望、第三人称叙述", "可以不", "哪有那么难", "不就行了"):
        assert distinction in INTENT_PROMPT
    assert '"做张封面竟然收了我八颗草莓"' in INTENT_PROMPT
    assert '"帮我生成一张日落灯塔插画"' in INTENT_PROMPT


@pytest.mark.parametrize("message", [
    "生成一张图片失败了",
    "画一只猫画成了狗",
    "画一只猫扣了我十颗草莓",
    "做一张海报咋弄",
    "给我画个头像的朋友去年走了",
    "画一只猫不难",
    "做一个头像还得花钱",
])
def test_review_corpus_candidate_with_null_model_is_ordinary_reply(
    client, dev_headers, monkeypatch, message,
):
    import services.chat_service as chat

    assert explicit_image_intent(message) is not None
    classified = []
    generated = []
    monkeypatch.setattr(chat, "recognize_intent", lambda _client, text, _history: (
        classified.append(text) or {"intent": None}
    ))
    monkeypatch.setattr(chat, "generate_image", lambda *args: generated.append(args))
    output = _events(client.post("/chat", headers=dev_headers, json={"message": message}))
    assert classified == [message]
    assert generated == []
    assert any("测试" in event.get("text", "") for event in output)
    assert output[-1] == {"done": True}


def test_null_model_candidate_bills_ordinary_reply_only(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    import database
    from auth import create_token

    user = dev_headers["X-Dev-User"]
    assert client.post("/conversations", json={}, headers=dev_headers).status_code == 201
    before = asyncio.run(database.get_strawberry_balance(user))
    version = asyncio.run(database.get_session_version(user))
    classified = []

    def classify(_client, message, _history):
        classified.append(message)
        return {"intent": None}

    async def no_image(*args):
        raise AssertionError("null intent must not generate an image")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", no_image)
    monkeypatch.setenv("DEV_MODE", "0")
    headers = {"Authorization": f"Bearer {create_token(user, version)}"}
    output = _events(client.post("/chat", headers=headers, json={"message": "生成一张图片失败了"}))
    assert classified == ["生成一张图片失败了"]
    assert not any("generated_image" in event for event in output)
    assert any("测试" in event.get("text", "") for event in output)
    assert asyncio.run(database.get_strawberry_balance(user)) == before - 10


def test_rejected_candidate_cannot_fill_old_image_prompt(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending

    conversation = client.post("/conversations", json={}, headers=dev_headers).json()["conversation"]["id"]
    key = ("smoke_tester", conversation)
    set_pending(key, {"intent": "generate_image", "params": {}, "missing": ["prompt"]})
    classified = []

    def classify(_client, message, _history):
        classified.append(message)
        return {"intent": None}

    async def no_image(*args):
        raise AssertionError("a rejected candidate cannot fill an old image prompt")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", no_image)
    output = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "生成一张图片失败了",
    }))
    assert classified == ["生成一张图片失败了"]
    assert any("测试" in event.get("text", "") for event in output)
    assert not any("generated_image" in event for event in output)
    assert get_pending(key) is not None


def test_candidate_other_model_intent_is_reused_for_tool(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    classified = []
    tools = []

    def classify(_client, message, _history):
        classified.append(message)
        return {"intent": "web_search", "params": {"query": "poster prices"}, "missing": []}

    def execute(intent, params):
        tools.append((intent, params))
        return "查到结果"

    async def no_image(*args):
        raise AssertionError("another model intent must not generate an image")

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "generate_image", no_image)
    output = _events(client.post("/chat", headers=dev_headers, json={"message": "做一张海报咋弄"}))
    assert classified == ["做一张海报咋弄"]
    assert tools == [("web_search", {"query": "poster prices"})]
    assert any(event.get("text") == "查到结果" for event in output)
    assert not any("generated_image" in event for event in output)


def test_candidate_model_failure_falls_through_without_retry_or_generation(
    client, dev_headers, monkeypatch,
):
    import services.chat_service as chat

    calls = []
    generated = []

    def classify(message, history):
        calls.append(message)
        raise RuntimeError("classifier unavailable")

    monkeypatch.setattr(chat, "recognize_intent_with_fallback", classify)
    monkeypatch.setattr(chat, "generate_image", lambda *args: generated.append(args))
    output = _events(client.post("/chat", headers=dev_headers, json={"message": "画一只猫"}))
    assert calls == ["画一只猫"]
    assert generated == []
    assert any("测试" in event.get("text", "") for event in output)
    assert output[-1] == {"done": True}


def test_confirmed_candidate_bypasses_active_mirror(client, dev_headers, monkeypatch, tmp_path):
    import services.chat_service as chat
    from mode_switcher import set_user_mode
    from utils import media

    conversation = client.post("/conversations", json={}, headers=dev_headers).json()["conversation"]["id"]
    set_user_mode(("smoke_tester", conversation), "mirror", "manual")
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    path = tmp_path / "mirror_generated.png"
    calls = []
    generated = []

    def classify(_client, message, _history):
        calls.append(message)
        return {"intent": "generate_image", "params": {}, "missing": []}

    async def generate(prompt, ratio):
        generated.append((prompt, ratio))
        path.write_bytes(b"test-image")
        return {"image_path": "/uploads/mirror_generated.png", "model": "fake", "width": 1, "height": 1}

    async def no_mirror(*args):
        raise AssertionError("confirmed image request must bypass mirror response")
        yield ""

    monkeypatch.setattr(chat, "recognize_intent", classify)
    monkeypatch.setattr(chat, "generate_image", generate)
    monkeypatch.setattr(chat, "stream_mirror", no_mirror)
    monkeypatch.setattr(chat, "detect_mode", lambda *args: (_ for _ in ()).throw(
        AssertionError("confirmed image request must bypass mode detection")
    ))
    output = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "画一只猫",
    }))
    assert calls == ["画一只猫"]
    assert generated == [("画一只猫", "1:1")]
    assert any("generated_image" in event for event in output)
    assert output[-1] == {"done": True}
