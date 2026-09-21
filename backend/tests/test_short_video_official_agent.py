"""The short-video role uses trusted, role-specific instructions and existing model routing."""
import json
import sqlite3

import pytest

from test_agent_exchanges import exchange_model  # noqa: F401
from test_official_agent_exchanges import owner, official_cards, _start, _wait  # noqa: F401


SHORT_VIDEO_ID = "official:short-video-creator"


def test_short_video_role_is_available_without_exposing_internal_instructions(
    client, owner, exchange_model,
):
    from official_agents import get_official_exchange_instruction

    # Fetch after the fake model fixture configures the official provider.
    response = client.get("/agent-exchanges/official-agents", headers=owner["headers"])
    assert response.status_code == 200, response.text
    official_cards = response.json()["agents"]
    card = next(card for card in official_cards if card["id"] == SHORT_VIDEO_ID)
    assert card["display_name"] == "短视频创意搭档"
    assert card["kind"] == "official"
    assert card["provider"] == "deepseek" and card["model"] == "deepseek-v4-pro"
    assert card["suggested_topic"]
    assert set(card) == {"id", "display_name", "bio", "avatar_emoji", "is_public", "kind",
                         "suggested_topic", "provider", "model", "model_label"}
    public_values = [value for public_card in official_cards for value in public_card.values() if isinstance(value, str)]
    for summary in (False, True):
        instruction = get_official_exchange_instruction(SHORT_VIDEO_ID, summary=summary)
        assert instruction
        assert all(instruction not in value for value in public_values)
    assert client.get("/agents", headers=owner["headers"]).json()["agents"] == []
    assert exchange_model.calls == []


def test_short_video_default_99_uses_main_for_owner_and_official_for_partner_and_summary(
    client, owner, official_cards, exchange_model,
):
    import database
    from exchange_models import get_exchange_model
    from official_agents import get_official_exchange_instruction

    card = next(card for card in official_cards if card["id"] == SHORT_VIDEO_ID)
    created = _start(client, owner, card, max_turns=None, topic="创作一条上班迟到却意外救场的短视频")
    assert created["exchange"]["max_turns"] == 99
    final = _wait(client, owner, created["exchange"]["id"])
    assert final["exchange"]["status"] == "completed"
    assert final["exchange"]["turn_count"] == len(final["messages"]) == 99
    assert final["exchange"]["summary"] == "模拟交流总结"
    assert final["exchange"]["recipient"]["id"] == SHORT_VIDEO_ID
    assert client.get("/agents/me", headers=owner["headers"]).json()["agent"]["is_public"] is False
    assert [call["provider"] for call in exchange_model.calls] == [
        "main" if number % 2 == 0 else "official" for number in range(99)
    ] + ["official"]
    reply_instruction = get_official_exchange_instruction(SHORT_VIDEO_ID)
    summary_instruction = get_official_exchange_instruction(SHORT_VIDEO_ID, summary=True)
    for call in exchange_model.calls[:-1]:
        assert reply_instruction in call["messages"][0]["content"]
    assert summary_instruction in exchange_model.calls[-1]["messages"][0]["content"]
    with sqlite3.connect(database.DB_PATH) as db:
        ledger = db.execute("SELECT provider, model FROM agent_exchange_calls WHERE exchange_id=? ORDER BY ordinal",
                            (created["exchange"]["id"],)).fetchall()
    assert ledger == [
        (get_exchange_model(slot).provider, get_exchange_model(slot).model)
        for slot in ["main" if number % 2 == 0 else "official" for number in range(99)] + ["official"]
    ]


@pytest.mark.parametrize("summary", [False, True], ids=["reply", "summary"])
def test_short_video_role_instructions_cover_a_shootable_timed_script(summary):
    from official_agents import get_official_exchange_instruction

    instruction = get_official_exchange_instruction(SHORT_VIDEO_ID, summary=summary)
    normalized = instruction.replace(" ", "")
    for concept in ("30", "60", "钩子", "反转", "分镜", "台词", "音效", "时长"):
        assert concept in normalized
    if summary:
        assert "剧本" in normalized and "画面" in normalized
        assert "总" in normalized or "合计" in normalized


@pytest.mark.parametrize("kind,recipient_id", [
    ("official", SHORT_VIDEO_ID),
    ("official", "official:creative-partner"),
    ("official", "official:script-editor"),
    ("official", "unknown-role"),
    ("peer", SHORT_VIDEO_ID),
    ("peer", "some-real-user-agent"),
])
@pytest.mark.parametrize("summary", [False, True], ids=["reply", "summary"])
def test_trusted_short_video_instructions_are_scoped_to_the_official_recipient_id(
    kind, recipient_id, summary,
):
    from official_agents import get_official_exchange_instruction
    from services.exchange_service import build_exchange_messages

    # Matching names or an initiator using the registry ID must not activate a
    # trusted role. Only kind=official plus the exact recipient registry ID does.
    context = {
        "kind": kind, "topic": "整理一个短视频方案", "turn_count": 1, "max_turns": 2,
        "initiator": {"id": SHORT_VIDEO_ID, "display_name": "我的分身"},
        "recipient": {"id": recipient_id, "display_name": "短视频创意搭档", "bio": "用户填写的资料"},
        "messages": [{"display_name": "我的分身", "content": "先决定故事方向"}],
    }
    messages = build_exchange_messages(context, summary=summary)
    instruction = get_official_exchange_instruction(SHORT_VIDEO_ID, summary=summary)
    assert instruction
    assert (instruction in messages[0]["content"]) is (kind == "official" and recipient_id == SHORT_VIDEO_ID)
    assert instruction not in messages[-1]["content"]
    assert json.loads(messages[-1]["content"])["dialogue"][0]["content"] == "先决定故事方向"
