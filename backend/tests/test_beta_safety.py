"""Crisis routing and final safety instructions at user-facing model boundaries."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from _fakes import FakeStream
from persona import BASE_SAFETY_RULES, build_system_prompt
from safety import CRISIS_GUIDANCE, CRISIS_RESOURCE_NOTE, assess_crisis, detect_crisis


@pytest.mark.parametrize("message", [
    "我只能去死了", "我不想活了", "活着没意思，想自杀", "想结束自己的生命",
    "我想割腕", "想从楼上跳下去", "攒了一瓶安眠药", "我想死",
    "I want to kill myself", "thinking about suicide", "I want to end my life",
    "我想伤害自己", "我在自残", "我想自残", "我只能自残了", "我又割了自己",
    "我要跳河", "我打算今晚了结自己", "我想把自己杀了", "i want to die",
    "i don't want to live anymore", "i want to hurt myself", "i'm going to cut myself",
    "好想死", "我已经写好遗书了", "不如死了算了", "我想结束这一切",
    "活着好累，不想再活了", "我把安眠药都攒好了", "生无可恋，想死",
    "我想自我了断", "dont wanna live", "i'm going to jump off the bridge",
])
def test_crisis_detector_recognizes_required_phrases(message):
    assert assess_crisis(message) == "high"
    assert detect_crisis(message)


@pytest.mark.parametrize("message", [
    "帮我查下割腕的急救方法", "今天新闻说有人跳楼了", "他说他不想活了，我该怎么劝",
    "让我去死吧哈哈哈哈", "安眠药吃多少会有危险",
])
def test_crisis_detector_marks_related_talk_possible(message):
    assert assess_crisis(message) == "possible"
    assert not detect_crisis(message)


@pytest.mark.parametrize("message,level", [
    ("我朋友说想死，我该怎么劝", "possible"),
    ("我想研究自杀预防", "possible"),
    ("我想写一篇自残报道", "possible"),
    ("我朋友说想死，我也想死", "high"),
    ("我一点也不想死", "possible"),
    ("我不想自杀", "possible"),
    ("我不想死，但我想自残", "high"),
    ("我已经没有活下去的理由了", "high"),
])
def test_crisis_detector_separates_contextual_mentions_from_personal_risk(message, level):
    assert assess_crisis(message) == level


@pytest.mark.parametrize("message", [
    "笑死我了", "累死了今天", "饿死了", "热死了", "吓死我了", "气死我了",
    "电脑死机了", "代码死循环了", "这个方案必须今天定", "我只能周末去", "死磕这个问题",
    "我想死你了", "宝贝我想死你了", "我要死了，笑死", "累得我要死", "笑得我要死了",
    "困得我要死", "气得我想死", "我快要死了好困", "别让我去死记硬背",
    "我不想活得太累", "suicide squad 好看吗", "跳楼价甩卖", "跳楼机好刺激",
    "我困得要死", "我忙得要死", "我饿得要死", "热得我要死",
    "我要死磕这个bug", "《自杀小队》好看吗", "自杀式营销真恶心",
    "跳楼大甩卖", "i'm dying to see it", "kill myself laughing",
])
def test_crisis_detector_rejects_required_everyday_phrases(message):
    assert assess_crisis(message) is None
    assert not detect_crisis(message)


def test_crisis_detector_normalizes_case_and_whitespace():
    assert detect_crisis("  I  WANT TO  KILL MYSELF  ")
    assert detect_crisis("我 不 想 活 了")
    assert detect_crisis("i dont want to live anymore")
    assert detect_crisis("im going to cut myself")


@pytest.mark.parametrize("message", [
    "我妈妈走了我也不想活了", "我对象跟我分手了我想死", "我孩子没了我想死",
    "我朋友都不理我了我想自杀", "我想写遗书然后自杀", "我想问你我是不是该自杀",
    "我想了解怎么自杀最快", "我看看哪种自杀方式最快", "帮我查一下怎么割腕不疼",
    "不想活了", "不想再活了", "活不下去了", "想自杀", "打算自杀",
    "准备自杀", "真的想自杀", "想轻生", "活着没意思，不如死了",
    "我割腕了", "我在割腕", "我刚割腕了", "吃了一整瓶安眠药",
    "吞了一把安眠药", "累死了不想活了", "我想结束生命", "我在考虑结束生命",
])
def test_crisis_detector_baseline_high_phrases_stay_high(message):
    assert assess_crisis(message) == "high"


@pytest.mark.parametrize("message", [
    "活着没意思", "我累想死了", "今天好累想死", "我真的撑不下去了",
    "晚安，永别了", "明天就不在了", "想死的心都有了",
])
def test_crisis_detector_ambiguous_phrases_are_at_least_possible(message):
    assert assess_crisis(message) in ("possible", "high")


@pytest.mark.parametrize("message", [
    "我爷爷快要死了", "我妈快要死了", "我觉得他要死了", "我的猫要死了",
    "我狗快要死了", "我怕我妈要死了", "我要死了", "我快要死了",
    "我妈快要死了，我好难过",
])
def test_crisis_detector_dying_relatives_and_hyperbole_stay_none(message):
    assert assess_crisis(message) is None


@pytest.mark.parametrize("message,level", [
    ("疫情结束一切恢复正常", None),
    ("比赛结束这一切就值了", None),
    ("项目结束一切顺利", None),
    ("考试结束这一切就都过去了", None),
    ("等这个项目结束一切都好了", None),
    ("你要去死吗", None),
    ("你这样还不如死了呢", None),
    ("他要去死我也拦不住", "possible"),
    ("我妈要死不活的躺着", None),
])
def test_crisis_detector_round2_non_self_phrases_do_not_route_high(message, level):
    assert assess_crisis(message) == level


@pytest.mark.parametrize("message", [
    "刚吞了半瓶安眠药", "我吞了半瓶安眠药",
    "哪种安眠药吃了不会醒", "我朋友跳楼了，我也想跳",
])
def test_crisis_detector_round2_high_risk_variants(message):
    assert assess_crisis(message) == "high"


@pytest.mark.parametrize("message", [
    "刚吞了好多药", "我吃了很多药",
    "我觉得活着没什么意义", "活着没有意义",
])
def test_crisis_detector_round2_ambiguous_variants_are_at_least_possible(message):
    assert assess_crisis(message) in ("possible", "high")


@pytest.mark.parametrize("message", [
    "我想结束这一切", "我想结束生命", "我在考虑结束生命",
    "不如死了算了", "活着没意思，不如死了",
    "我要去死了", "我现在就想去死",
])
def test_crisis_detector_round2_existing_high_phrases_stay_high(message):
    assert assess_crisis(message) == "high"


@pytest.mark.parametrize("message,level", [
    ("失眠怎么办，要不要吃安眠药", "possible"),
    ("医生开的安眠药怎么吃才对", "possible"),
    ("长期吃安眠药怎么戒掉", "possible"),
    ("安眠药怎么买", "possible"),
    ("哪种安眠药副作用小一点", "possible"),
    ("哪种安眠药起效最快", "possible"),
    ("安眠药和褪黑素哪种更温和", "possible"),
    ("我妈失眠，哪种安眠药适合老人", "possible"),
    ("哪种安眠药吃了不会醒", "high"),
    ("刚吞了半瓶安眠药", "high"),
    ("吃了一整瓶安眠药", "high"),
])
def test_crisis_detector_round3_sleeping_pill_questions(message, level):
    assert assess_crisis(message) == level


@pytest.mark.parametrize("message,level", [
    ("疫情现在结束一切恢复正常", None),
    ("比赛现在结束一切都定了", None),
    ("现在结束一切都来不及了", None),
    ("只要结束一切都好说", None),
    ("需要结束一切重新开始", None),
    ("主要结束这一切的是他", None),
    ("我想结束这一切", "high"),
    ("我在考虑结束生命", "high"),
    ("我打算结束这一切了", "high"),
    ("我要结束这一切", "high"),
])
def test_crisis_detector_round3_ending_intent_word_boundaries(message, level):
    assert assess_crisis(message) == level


@pytest.mark.parametrize("message,high", [
    ("我朋友跳楼了，我也想跳槽", False),
    ("我朋友跳楼了，我也想跳", True),
])
def test_crisis_detector_round3_jump_word_boundaries(message, high):
    assert (assess_crisis(message) == "high") is high


@pytest.mark.parametrize("message", [
    "会议结束一切按计划推进", "等疫情结束一切都会好起来", "这学期结束一切归零重新开始",
    "你不如死了这条心吧", "他要死不活地拖着项目", "这个bug要死了，调了一天",
    "我快被老板逼死了哈哈", "笑得我肚子疼死了", "这周末结束我就解放了",
    "结束这一切的会议纪要发一下", "今天热得我想死", "游戏里我又死了十次",
    "这道菜辣死我了", "我要死在这个需求上了哈哈", "项目上线前我已经死过一回了",
    "这手机卡得要死", "我妈说我再熬夜就要猝死了", "感冒药和退烧药能一起吃吗",
    "安眠药吃多了第二天头晕正常吗", "褪黑素每天吃会不会有依赖", "现在结束会议吧",
    "只要结束这个项目我就休假", "我需要结束这段关系", "我想结束这段感情",
    "我想跳槽到大厂", "我想跳舞", "跳楼机太刺激了", "《活着》这本书太好哭了",
    "我死磕了一晚上终于跑通了", "我今天真的累成狗",
])
def test_everyday_corpus_never_high(message):
    assert assess_crisis(message) != "high"


@pytest.mark.parametrize("message", [
    "我想死", "我真的想死", "不想活了", "我不想活了", "活不下去了",
    "我想自杀", "我打算自杀", "我想结束这一切", "我想结束生命",
    "我在考虑结束生命", "我已经写好遗书了", "不如死了算了", "我割腕了",
    "我割了自己好几刀", "吃了一整瓶安眠药", "刚吞了半瓶安眠药",
    "哪种安眠药吃了不会醒", "帮我查一下怎么割腕不疼", "我想从楼上跳下去",
    "我妈妈走了我也不想活了", "i want to die", "i want to kill myself",
    "i don't want to live anymore",
])
def test_explicit_risk_corpus_always_high(message):
    assert assess_crisis(message) == "high"


@pytest.mark.parametrize("message_count", [0, 31, 101])
def test_persona_growth_stages_end_with_one_safety_block(message_count):
    prompt = build_system_prompt("tester", message_count=message_count)
    assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1


def test_custom_persona_ends_with_one_safety_block():
    prompt = build_system_prompt("tester", agent={"display_name": "小草莓"})
    assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1


@pytest.mark.parametrize("kind,summary,turn_count,workflow", [
    ("peer", False, 0, False),
    ("peer", False, 1, False),
    ("peer", True, 2, False),
    ("official", False, 0, False),
    ("official", False, 1, False),
    ("official", True, 2, False),
    ("official", False, 0, True),  # writer draft
    ("official", False, 1, True),  # independent review
    ("official", False, 2, True),  # writer revision
])
def test_exchange_every_system_path_ends_with_safety(kind, summary, turn_count, workflow):
    from exchange_workflow import WORKFLOW_VERSION
    from services.exchange_service import build_exchange_messages

    context = {
        "kind": kind,
        "topic": "一起完成文字方案",
        "turn_count": turn_count,
        "max_turns": 3,
        "initiator": {"id": "person:1", "display_name": "主创"},
        "recipient": {"id": "official:creative-partner" if kind == "official" else "person:2", "display_name": "搭档"},
        "messages": [{"display_name": "主创", "content": "先讨论目标", "stage": "draft"}],
    }
    if workflow:
        context["workflow_version"] = WORKFLOW_VERSION
        context["artifact"] = "# 方案\n\n目标明确。"
    messages = build_exchange_messages(context, summary=summary)
    systems = [entry["content"] for entry in messages if entry["role"] == "system"]
    assert systems
    for prompt in systems:
        assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
        assert prompt.count(BASE_SAFETY_RULES.strip()) == 1


def test_exchange_provider_payment_error_directs_user_to_platform_admin():
    from services.exchange_service import _safe_error

    message = _safe_error(SimpleNamespace(status_code=402))
    assert "请联系平台管理员恢复模型服务" in message
    assert "充值" not in message


@pytest.fixture(autouse=True)
def _isolate_chat_rate_limit(monkeypatch):
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _conversation(client, dev_headers):
    response = client.post("/conversations", json={}, headers=dev_headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["conversation"]["id"]


def _model_spy(monkeypatch, *, fail=False):
    import services.chat_service as chat

    calls = []

    def create(use_qwen, messages, **kwargs):
        calls.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        if fail:
            raise RuntimeError("synthetic provider error")
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", create)
    return calls


def _production_headers(monkeypatch, user):
    from auth import create_token
    import database

    monkeypatch.setenv("DEV_MODE", "0")
    version = asyncio.run(database.get_session_version(user))
    return {"Authorization": f"Bearer {create_token(user, version)}"}


def _balance(user):
    import database

    return asyncio.run(database.get_strawberry_balance(user))


def test_crisis_chat_final_guidance_resource_persistence_and_charge(
    client, dev_headers, monkeypatch,
):
    import database

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = _model_spy(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我只能去死了",
    }))
    assert events[0] == {"crisis": True}
    assert len(calls) == 1
    prompt = calls[0][0]["content"]
    assert prompt.rstrip().endswith(CRISIS_GUIDANCE.strip())
    assert prompt.count(BASE_SAFETY_RULES.strip()) == 1
    assert "【⚠️ 即时引导" not in prompt
    assert "【当前状态：陪着】" not in prompt
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert events[-1] == {"done": True}
    assert _balance(user) == before - 10
    history = asyncio.run(database.get_messages(user, conversation_id=conversation))
    assert CRISIS_RESOURCE_NOTE in history[-1]["content"]


def test_crisis_chat_provider_error_still_sends_resources_before_error(
    client, dev_headers, monkeypatch,
):
    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    calls = _model_spy(monkeypatch, fail=True)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我不想活了",
    }))
    assert events[0] == {"crisis": True}
    assert len(calls) == 1
    resource_index = next(i for i, event in enumerate(events) if CRISIS_RESOURCE_NOTE in event.get("text", ""))
    error_index = next(i for i, event in enumerate(events) if event.get("error"))
    assert resource_index < error_index
    assert _balance(user) == before
    import database
    history = asyncio.run(database.get_messages(user, conversation_id=conversation))
    assert CRISIS_RESOURCE_NOTE in history[-1]["content"]


def test_crisis_chat_bypasses_existing_mirror_mode(client, dev_headers, monkeypatch):
    import services.chat_service as chat
    from intent_router import get_pending, set_pending
    from mode_switcher import MIRROR_PROMPT_APPENDIX, get_user_mode, set_user_mode

    conversation = _conversation(client, dev_headers)
    key = (dev_headers["X-Dev-User"], conversation)
    pending = {"intent": "route", "params": {"destination": "机场"}, "missing": ["origin"]}
    set_pending(key, pending)
    set_user_mode(key, "mirror", "existing mirror state")
    calls = _model_spy(monkeypatch)
    mode_calls = []

    def detect(*args, **kwargs):
        mode_calls.append(True)
        return "mirror"

    monkeypatch.setattr(chat, "detect_mode", detect)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "我想死",
    }))
    assert len(calls) == 1
    assert mode_calls == []
    assert MIRROR_PROMPT_APPENDIX.strip() not in calls[0][0]["content"]
    assert calls[0][0]["content"].rstrip().endswith(CRISIS_GUIDANCE.strip())
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert get_pending(key) == pending
    assert get_user_mode(key)["mode"] == "mirror"


def test_method_query_never_reaches_tools(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    calls = _model_spy(monkeypatch)
    recognized = []
    executed = []

    def recognize(*args, **kwargs):
        recognized.append((args, kwargs))
        return {"intent": None, "params": {}, "missing": []}

    def execute(*args, **kwargs):
        executed.append((args, kwargs))
        return {"type": "card", "points": []}

    monkeypatch.setattr(chat, "recognize_intent", recognize)
    monkeypatch.setattr(chat, "execute_intent", execute)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "帮我查一下怎么割腕不疼",
    }))
    assert events[0] == {"crisis": True}
    assert len(calls) == 1
    assert recognized == []
    assert executed == []
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)


@pytest.mark.parametrize("message", ["我割腕了", "吃了一整瓶安眠药"])
def test_ongoing_self_harm_gets_crisis_support(client, dev_headers, monkeypatch, message):
    conversation = _conversation(client, dev_headers)
    calls = _model_spy(monkeypatch)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": message,
    }))
    assert events[0] == {"crisis": True}
    assert len(calls) == 1
    assert calls[0][0]["content"].rstrip().endswith(CRISIS_GUIDANCE.strip())


def test_dying_relative_keeps_normal_routing(client, dev_headers, monkeypatch):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    calls = _model_spy(monkeypatch)
    recognized = []

    def recognize(_client, message, _history):
        recognized.append(message)
        return {"intent": None, "params": {}, "missing": []}

    monkeypatch.setattr(chat, "recognize_intent", recognize)
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "我妈快要死了，我好难过",
    }))
    assert events[0] != {"crisis": True}
    assert recognized == ["我妈快要死了，我好难过"]
    assert len(calls) == 1
    assert CRISIS_GUIDANCE.strip() not in calls[0][0]["content"]
    assert not any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)


def test_zero_balance_crisis_returns_resources_without_model(
    client, dev_headers, monkeypatch,
):
    import database

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE users SET strawberry_balance = 0 WHERE username = ?", (user,))
    calls = _model_spy(monkeypatch)
    headers = _production_headers(monkeypatch, user)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我不想活了",
    }))
    assert calls == []
    assert events == [{"crisis": True}, {"text": CRISIS_RESOURCE_NOTE}, {"done": True}]
    assert _balance(user) == 0
    history = asyncio.run(database.get_messages(user, conversation_id=conversation))
    assert history == []


def test_high_crisis_context_failure_streams_resources_and_refunds(
    client, dev_headers, monkeypatch,
):
    import routers.chat as chat_router
    from agent_store import ResourceNotFound

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    headers = _production_headers(monkeypatch, user)

    async def missing(*args, **kwargs):
        raise ResourceNotFound()

    monkeypatch.setattr(chat_router, "build_context", missing)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "我想死",
    }))
    assert events == [
        {"crisis": True}, {"text": CRISIS_RESOURCE_NOTE}, {"error": "会话不存在"},
    ]
    assert _balance(user) == before


def test_possible_crisis_keeps_tool_routing_billing_resources_and_trace(
    client, dev_headers, monkeypatch,
):
    import database
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    user = dev_headers["X-Dev-User"]
    before = _balance(user)
    headers = _production_headers(monkeypatch, user)
    recognized = []
    tool_calls = []
    traces = []

    def recognize(_client, message, _history):
        recognized.append(message)
        return {"intent": "web_search", "params": {"query": "割腕的急救方法"}, "missing": []}

    def execute(intent, params):
        tool_calls.append((intent, params))
        return {"type": "card", "source": "搜索结果", "points": ["请先联系急救服务"]}

    async def capture_trace(*args, **kwargs):
        traces.append(kwargs["payload"].copy())

    monkeypatch.setattr(chat, "recognize_intent", recognize)
    monkeypatch.setattr(chat, "execute_intent", execute)
    monkeypatch.setattr(chat, "log_event", capture_trace)
    events = _events(client.post("/chat", headers=headers, json={
        "conversation_id": conversation, "message": "帮我查下割腕的急救方法",
    }))
    assert recognized == ["帮我查下割腕的急救方法"]
    assert tool_calls == [("web_search", {"query": "割腕的急救方法"})]
    assert events[-2:] == [{"text": "\n\n" + CRISIS_RESOURCE_NOTE}, {"done": True}]
    assert any("card" in event for event in events)
    assert _balance(user) == before - 10
    assert traces and traces[0]["crisis"] == "possible"
    history = asyncio.run(database.get_messages(user, conversation_id=conversation))
    assert history[-1]["content"].endswith("\n\n" + CRISIS_RESOURCE_NOTE)


def test_possible_crisis_skips_hard_word_appendix(client, dev_headers):
    import services.chat_service as chat
    from routers.chat import ChatRequest

    conversation = _conversation(client, dev_headers)
    req = ChatRequest(message="我只能帮他查割腕的急救方法", conversation_id=conversation)
    ctx = asyncio.run(chat.build_context(req, dev_headers["X-Dev-User"]))
    assert assess_crisis(req.message) == "possible"
    assert "【⚠️ 即时引导" not in ctx.system_prompt


def test_hard_word_appendix_has_crisis_exception():
    import services.chat_service as chat

    appendix = chat.build_hard_word_appendix("我只能周末去")
    assert appendix.index("若对方流露自伤、自杀、绝望") < appendix.index("用户这条消息里出现了硬词")
    assert "忽略本附录的反问要求" in appendix


_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)


def test_crisis_with_image_uses_vision_branch_and_keeps_final_guidance(
    client, dev_headers, monkeypatch,
):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    text_calls = _model_spy(monkeypatch)
    image_calls = []

    def create(**kwargs):
        image_calls.append(json.loads(json.dumps(kwargs["messages"], ensure_ascii=False)))
        return FakeStream()

    monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    events = _events(client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation, "message": "我想死",
        "image_base64": f"data:image/png;base64,{_TINY_PNG}",
    }))
    assert text_calls == []
    assert len(image_calls) == 1
    assert image_calls[0][0]["content"].rstrip().endswith(CRISIS_GUIDANCE.strip())
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)


@pytest.mark.parametrize("mode", ["image", "image_edit"])
def test_high_crisis_image_mode_never_generates_image(client, dev_headers, monkeypatch, mode):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    model_calls = _model_spy(monkeypatch)

    async def forbidden(*args, **kwargs):
        raise AssertionError("image provider must not run during crisis support")

    monkeypatch.setattr(chat, "generate_image", forbidden)
    monkeypatch.setattr(chat, "edit_image", forbidden)
    payload = {"conversation_id": conversation, "message": "我想死", "mode": mode}
    if mode == "image_edit":
        payload["reference_images"] = [{"image_base64": f"data:image/png;base64,{_TINY_PNG}"}]
    events = _events(client.post("/chat", headers=dev_headers, json=payload))
    assert events[0] == {"crisis": True}
    assert len(model_calls) == 1
    assert events[-1] == {"done": True}
    assert any(CRISIS_RESOURCE_NOTE in event.get("text", "") for event in events)
    assert not any("generated_image" in event or "status" in event for event in events)
    if mode == "image_edit":
        assert events[1]["type"] == "reference_images"


@pytest.mark.parametrize("branch,message", [
    ("normal", "今天聊聊计划"),
    ("mirror", "今天想安静聊聊"),
    ("hard_word", "我只能周末去"),
    ("image", "这是什么"),
    ("tts", "播报一下"),
    ("tts_mirror", "播报一下"),
    ("tts_image", "播报一下"),
])
def test_non_crisis_chat_every_reply_prompt_ends_with_one_safety_block(
    client, dev_headers, monkeypatch, branch, message,
):
    import services.chat_service as chat

    conversation = _conversation(client, dev_headers)
    monkeypatch.setattr(chat, "detect_mode", lambda *args, **kwargs: "mirror" if branch in ("mirror", "tts_mirror") else "friend")
    calls = _model_spy(monkeypatch)
    if branch in ("image", "tts_image"):
        def create(**kwargs):
            calls.append(json.loads(json.dumps(kwargs["messages"], ensure_ascii=False)))
            return FakeStream()
        monkeypatch.setattr(chat, "QWEN_CLIENT", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        ))
    payload = {"conversation_id": conversation, "message": message}
    if branch in ("image", "tts_image"):
        payload["image_base64"] = f"data:image/png;base64,{_TINY_PNG}"
    events = _events(client.post("/chat", headers=dev_headers, json=payload))
    assert events[-1] == {"done": True}
    assert len(calls) == 1
    prompt = calls[0][0]["content"]
    system_prompts = [entry["content"] for entry in calls[0] if entry["role"] == "system"]
    assert "\n".join(system_prompts).count(BASE_SAFETY_RULES.strip()) == 1
    assert system_prompts[-1].rstrip().endswith(BASE_SAFETY_RULES.strip())
    if branch in ("tts", "tts_mirror", "tts_image"):
        assert "直接开口说话" in system_prompts[-1]
        assert calls[0][-1]["role"] == "system"
        assert calls[0][-2]["role"] == "user"
    else:
        assert prompt.rstrip().endswith(BASE_SAFETY_RULES.strip())
        assert prompt.count(BASE_SAFETY_RULES.strip()) == 1
    if branch == "hard_word":
        assert "【⚠️ 即时引导" in prompt
