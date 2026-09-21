"""Authorized avatar exchanges: privacy, bounded generation and revocation races."""
import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest


class ExchangeModel:
    """Fake only the provider boundary; exercise the real prompt builder and runner."""

    def __init__(self):
        self.calls = []
        self.block_at = None
        self.started = Event()
        self.release = Event()
        self.release.set()
        self.failure = None
        self.fail_at = None
        self.missing_usage = False
        self.reply_factory = None

    def block(self, call_number):
        self.block_at = call_number
        self.release.clear()

    async def generate(self, messages, *, max_tokens, provider="main"):
        from exchange_models import get_exchange_model

        config = get_exchange_model(provider)
        number = len(self.calls) + 1
        self.calls.append({
            "messages": json.loads(json.dumps(messages, ensure_ascii=False)),
            "max_tokens": max_tokens,
            "provider": provider,
        })
        if number == self.block_at:
            self.started.set()
            assert await asyncio.to_thread(self.release.wait, 10), "fake model was not released"
        if self.failure is not None and (self.fail_at is None or number == self.fail_at):
            raise self.failure
        summary = "你负责总结" in messages[0]["content"]
        return {
            "content": "模拟交流总结" if summary else self.reply_factory(number) if self.reply_factory else f"模拟交流发言 {number}",
            "input_tokens": None if self.missing_usage else 12,
            "output_tokens": None if self.missing_usage else 8,
            "provider": config.provider,
            "model": config.model,
        }


@pytest.fixture
def exchange_model(client, monkeypatch):
    import exchange_store
    import services.exchange_service as exchange_service
    from rate_limit import limiter

    # These existing scenarios exercise legacy alternating exchanges, including
    # their historical summary call. New draft/review runs have separate tests
    # that keep the production default and never inherit this legacy override.
    monkeypatch.setattr(exchange_store, "OFFICIAL_WORKFLOW_VERSION", "", raising=False)
    model = ExchangeModel()
    monkeypatch.setenv("OFFICIAL_EXCHANGE_PROVIDER", "deepseek")
    monkeypatch.setenv("OFFICIAL_EXCHANGE_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(exchange_service, "generate_exchange_reply", model.generate)
    monkeypatch.setattr(limiter, "enabled", False)
    try:
        yield model
    finally:
        model.release.set()


@pytest.fixture
def pair(client):
    participants = []
    for username, display_name in (
        ("exchange_initiator", "星河旅伴"),
        ("exchange_recipient", "苔原向导"),
    ):
        headers = {"X-Dev-User": username}
        response = client.put("/agents/me", headers=headers, json={
            "display_name": display_name,
            "bio": f"{display_name}的公开介绍",
            "is_public": True,
        })
        assert response.status_code == 200, response.text
        participants.append({"headers": headers, "agent": response.json()["agent"]})
    return participants


def _invite(client, pair, max_turns=2, **overrides):
    initiator, recipient = pair
    payload = {
        "target_agent_id": recipient["agent"]["id"],
        "topic": "一起规划一次城市漫步",
        "max_turns": max_turns,
        **overrides,
    }
    response = client.post("/agent-exchanges", headers=initiator["headers"], json=payload)
    assert response.status_code == 201, response.text
    return response.json()["exchange"]


def _detail(client, participant, exchange_id):
    response = client.get(f"/agent-exchanges/{exchange_id}", headers=participant["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def _act(client, participant, exchange_id, action):
    return client.post(f"/agent-exchanges/{exchange_id}/{action}", headers=participant["headers"])


def _wait(client, participant, exchange_id):
    import services.exchange_service as exchange_service

    client.portal.call(exchange_service.wait_for_exchange, exchange_id)
    return _detail(client, participant, exchange_id)


@pytest.mark.parametrize("private_participant", [0, 1])
def test_exchange_requires_both_public_avatars(client, pair, exchange_model, private_participant):
    client.put("/agents/me", headers=pair[private_participant]["headers"], json={"is_public": False})
    response = client.post("/agent-exchanges", headers=pair[0]["headers"], json={
        "target_agent_id": pair[1]["agent"]["id"], "topic": "一次公开交流", "max_turns": 2,
    })
    assert response.status_code == (409 if private_participant == 0 else 404), response.text
    assert exchange_model.calls == []
    assert client.get("/agent-exchanges", headers=pair[0]["headers"]).json()["exchanges"] == []


def test_exchange_cannot_invite_self_or_an_unknown_avatar(client, pair, exchange_model):
    for target_id, expected_status in ((pair[0]["agent"]["id"], 409), ("missing-agent", 404)):
        response = client.post("/agent-exchanges", headers=pair[0]["headers"], json={
            "target_agent_id": target_id, "topic": "一次公开交流", "max_turns": 2,
        })
        assert response.status_code == expected_status, response.text
    assert exchange_model.calls == []


@pytest.mark.parametrize("max_turns", [0, 1, 7, 999, -1, 2.5])
def test_exchange_rejects_out_of_range_generation_budgets(client, pair, exchange_model, max_turns):
    response = client.post("/agent-exchanges", headers=pair[0]["headers"], json={
        "target_agent_id": pair[1]["agent"]["id"], "topic": "限定次数", "max_turns": max_turns,
    })
    assert response.status_code == 422, response.text
    assert exchange_model.calls == []


def test_peer_topic_still_rejects_three_hundred_and_one_characters(client, pair, exchange_model):
    response = client.post("/agent-exchanges", headers=pair[0]["headers"], json={
        "target_agent_id": pair[1]["agent"]["id"], "topic": "文" * 301, "max_turns": 2,
    })
    assert response.status_code == 422, response.text
    assert client.get("/agent-exchanges", headers=pair[0]["headers"]).json()["exchanges"] == []
    assert exchange_model.calls == []


def test_only_recipient_can_accept_or_reject_and_strangers_cannot_access(client, pair, exchange_model):
    exchange = _invite(client, pair)
    exchange_id = exchange["id"]
    assert exchange["status"] == "pending"
    for action in ("accept", "reject"):
        response = _act(client, pair[0], exchange_id, action)
        assert response.status_code == 409, response.text

    stranger = {"headers": {"X-Dev-User": "exchange_stranger"}}
    assert client.get(f"/agent-exchanges/{exchange_id}", headers=stranger["headers"]).status_code == 404
    for action in ("accept", "reject", "stop"):
        assert _act(client, stranger, exchange_id, action).status_code == 404
    assert client.get("/agent-exchanges", headers=stranger["headers"]).json()["exchanges"] == []
    assert _detail(client, pair[0], exchange_id)["exchange"]["viewer_role"] == "initiator"
    assert _detail(client, pair[1], exchange_id)["exchange"]["viewer_role"] == "recipient"
    assert exchange_model.calls == []


def test_rejected_invitation_never_generates_or_becomes_accepted(client, pair, exchange_model):
    exchange_id = _invite(client, pair)["id"]
    response = _act(client, pair[1], exchange_id, "reject")
    assert response.status_code == 200, response.text
    assert response.json()["exchange"]["status"] == "rejected"
    assert _act(client, pair[1], exchange_id, "accept").status_code == 409
    assert _detail(client, pair[0], exchange_id)["messages"] == []
    assert exchange_model.calls == []


def test_concurrent_accepts_start_one_bounded_run(client, pair, exchange_model):
    exchange_id = _invite(client, pair)["id"]
    exchange_model.block(1)
    barrier = Barrier(2)

    def accept_together():
        barrier.wait(timeout=10)
        return _act(client, pair[1], exchange_id, "accept")

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(accept_together) for _ in range(2)]
            responses = [future.result(timeout=10) for future in futures]
        assert [response.status_code for response in responses] == [200, 200]
        assert exchange_model.started.wait(timeout=10)
        assert len(exchange_model.calls) == 1
    finally:
        exchange_model.release.set()
    detail = _wait(client, pair[0], exchange_id)
    assert detail["exchange"]["status"] == "completed"
    assert detail["exchange"]["turn_count"] == 2
    assert len(detail["messages"]) == 2
    assert len(exchange_model.calls) == 3


@pytest.mark.parametrize("stopper", [0, 1])
@pytest.mark.parametrize("blocked_call", [1, 3], ids=["reply-in-flight", "summary-in-flight"])
def test_stop_discards_inflight_generation_and_prevents_further_calls(
    client, pair, exchange_model, stopper, blocked_call,
):
    exchange_id = _invite(client, pair)["id"]
    exchange_model.block(blocked_call)
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    try:
        assert exchange_model.started.wait(timeout=10)
        response = _act(client, pair[stopper], exchange_id, "stop")
        assert response.status_code == 200, response.text
        assert response.json()["exchange"]["status"] == "stopped"
    finally:
        exchange_model.release.set()
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "stopped"
    assert len(final["messages"]) == (0 if blocked_call == 1 else 2)
    assert not final["exchange"]["summary"]
    assert len(exchange_model.calls) == blocked_call
    assert _act(client, pair[1], exchange_id, "accept").status_code == 409


@pytest.mark.parametrize("hidden_participant", [0, 1])
def test_hiding_and_republishing_does_not_revive_inflight_exchange(
    client, pair, exchange_model, hidden_participant,
):
    exchange_id = _invite(client, pair)["id"]
    exchange_model.block(1)
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    try:
        assert exchange_model.started.wait(timeout=10)
        response = client.put("/agents/me", headers=pair[hidden_participant]["headers"], json={"is_public": False})
        assert response.status_code == 200, response.text
        assert _detail(client, pair[0], exchange_id)["exchange"]["status"] == "stopped"
        client.put("/agents/me", headers=pair[hidden_participant]["headers"], json={"is_public": True})
    finally:
        exchange_model.release.set()
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "stopped"
    assert final["messages"] == []
    assert len(exchange_model.calls) == 1


@pytest.mark.parametrize("failed_call", [1, 3], ids=["reply-failure", "summary-failure"])
@pytest.mark.parametrize("billing_failure", [False, True], ids=["generic", "billing"])
def test_upstream_failure_is_sanitized_and_stops_the_exchange(
    client, pair, exchange_model, failed_call, billing_failure,
):
    exchange_id = _invite(client, pair)["id"]
    raw_message = "raw-api-key-marker secret provider request payload"
    if billing_failure:
        import httpx
        from openai import BadRequestError

        exchange_model.failure = BadRequestError(
            raw_message,
            response=httpx.Response(400, request=httpx.Request("POST", "https://provider.invalid/chat")),
            body={"code": "Arrearage", "message": raw_message},
        )
    else:
        exchange_model.failure = RuntimeError(raw_message)
    exchange_model.fail_at = failed_call
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "failed"
    assert final["exchange"]["error"]
    if billing_failure:
        assert "欠费" in final["exchange"]["error"]
        assert "管理员" in final["exchange"]["error"]
    assert "raw-api-key-marker" not in json.dumps(final)
    assert "secret provider request payload" not in json.dumps(final)
    assert len(final["messages"]) == (0 if failed_call == 1 else 2)
    assert not final["exchange"]["summary"]
    assert len(exchange_model.calls) == failed_call


@pytest.mark.parametrize("requested_turns", [3, None], ids=["odd-turn-count", "default-six-turns"])
def test_completed_exchange_alternates_speakers_and_persists_summary_and_usage(
    client, pair, exchange_model, requested_turns,
):
    payload = {"target_agent_id": pair[1]["agent"]["id"], "topic": "一次有边界的交流"}
    if requested_turns is not None:
        payload["max_turns"] = requested_turns
    response = client.post("/agent-exchanges", headers=pair[0]["headers"], json=payload)
    assert response.status_code == 201, response.text
    exchange_id = response.json()["exchange"]["id"]
    max_turns = requested_turns or 6
    assert response.json()["exchange"]["max_turns"] == max_turns
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    final = _wait(client, pair[0], exchange_id)

    exchange = final["exchange"]
    assert exchange["status"] == "completed"
    assert exchange["turn_count"] == max_turns
    assert exchange["summary"] == "模拟交流总结"
    assert exchange["error"] == ""
    assert len(final["messages"]) == max_turns
    assert [message["sequence"] for message in final["messages"]] == list(range(1, max_turns + 1))
    assert [message["agent_id"] for message in final["messages"]] == [
        pair[index % 2]["agent"]["id"] for index in range(max_turns)
    ]
    assert [message["content"] for message in final["messages"]] == [
        f"模拟交流发言 {index}" for index in range(1, max_turns + 1)
    ]
    assert [call["max_tokens"] for call in exchange_model.calls] == [256] * max_turns + [128]
    assert [call["provider"] for call in exchange_model.calls] == ["main"] * (max_turns + 1)
    usage = exchange["usage"]
    assert usage["model_calls"] == usage["max_model_calls"] == max_turns + 1
    assert usage["input_tokens"] == 12 * (max_turns + 1)
    assert usage["output_tokens"] == 8 * (max_turns + 1)
    assert usage["total_tokens"] == 20 * (max_turns + 1)
    assert usage["estimated"] is False
    assert usage["reserved_tokens"] == 0
    assert 0 < usage["budget_used"] <= usage["token_budget"] <= 80000

    # Reopening the detail and list must use persisted content, without new generation.
    assert _detail(client, pair[0], exchange_id) == final
    recipient_copy = _detail(client, pair[1], exchange_id)
    assert recipient_copy["messages"] == final["messages"]
    assert recipient_copy["exchange"]["summary"] == exchange["summary"]
    listed = client.get("/agent-exchanges", headers=pair[0]["headers"]).json()["exchanges"]
    assert any(item["id"] == exchange_id and item["status"] == "completed" for item in listed)
    assert len(exchange_model.calls) == max_turns + 1


def test_private_personality_memory_and_chat_never_enter_exchange_context(
    client, pair, exchange_model,
):
    import agent_store
    import database

    canaries = []
    for index, participant in enumerate(pair):
        username = participant["headers"]["X-Dev-User"]
        personality = f"PRIVATE_PERSONALITY_{index}_9bf2"
        memory = f"PRIVATE_MEMORY_{index}_a17d"
        private_chat = f"PRIVATE_CHAT_{index}_d4c1"
        old_profile = f"LEGACY_PROFILE_{index}_c934"
        canaries.extend((personality, memory, private_chat, old_profile))
        response = client.put("/agents/me", headers=participant["headers"], json={"personality": personality})
        assert response.status_code == 200, response.text
        asyncio.run(agent_store.update_memory(username, {"needs": [memory]}))
        asyncio.run(database.update_profile(username, {"interests": [old_profile]}))
        conversation = asyncio.run(agent_store.create_conversation(username, "私聊"))
        assert asyncio.run(database.save_message(username, "user", private_chat, conversation_id=conversation["id"]))

    exchange_id = _invite(client, pair)["id"]
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "completed"
    assert len(exchange_model.calls) == 3
    for call in exchange_model.calls:
        context = json.dumps(call["messages"], ensure_ascii=False)
        assert all(canary not in context for canary in canaries)
        assert "一起规划一次城市漫步" in context
        assert all(participant["headers"]["X-Dev-User"] not in context for participant in pair)
    initial_context = json.dumps(exchange_model.calls[0]["messages"], ensure_ascii=False)
    assert "星河旅伴" in initial_context and "苔原向导" in initial_context
    assert "AI" in initial_context
    public_result = json.dumps(final, ensure_ascii=False)
    assert all(canary not in public_result for canary in canaries)
    assert "owner_username" not in public_result
    for name in ("initiator", "recipient"):
        assert set(final["exchange"][name]) <= {
            "id", "display_name", "bio", "avatar_emoji", "is_public", "created_at",
        }


def test_initiator_can_revoke_a_pending_invitation_without_starting_models(client, pair, exchange_model):
    exchange_id = _invite(client, pair)["id"]
    response = _act(client, pair[0], exchange_id, "stop")
    assert response.status_code == 200, response.text
    assert response.json()["exchange"]["status"] == "stopped"
    assert _act(client, pair[1], exchange_id, "accept").status_code == 409
    assert _detail(client, pair[0], exchange_id)["messages"] == []
    assert exchange_model.calls == []


@pytest.mark.parametrize("reverse_second", [False, True], ids=["same-direction", "opposite-directions"])
def test_concurrent_invites_allow_one_active_exchange_per_pair(client, pair, exchange_model, reverse_second):
    barrier = Barrier(2)

    def invite_together(index):
        initiator = pair[index] if reverse_second else pair[0]
        recipient = pair[1 - index] if reverse_second else pair[1]
        barrier.wait(timeout=10)
        return client.post("/agent-exchanges", headers=initiator["headers"], json={
            "target_agent_id": recipient["agent"]["id"], "topic": "并发邀请", "max_turns": 2,
        })

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(invite_together, range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    listed = client.get("/agent-exchanges", headers=pair[0]["headers"]).json()["exchanges"]
    assert len(listed) == 1
    assert listed[0]["status"] == "pending"
    assert exchange_model.calls == []


def test_provider_usage_omission_is_estimated_without_losing_the_hard_budget(client, pair, exchange_model):
    exchange_model.missing_usage = True
    exchange_id = _invite(client, pair)["id"]
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "completed"
    usage = final["exchange"]["usage"]
    assert usage["estimated"] is True
    assert usage["model_calls"] == 3
    assert 0 < usage["budget_used"] <= usage["token_budget"] <= 80000
    assert usage["reserved_tokens"] == 0
    assert len(exchange_model.calls) == 3


@pytest.mark.parametrize("deleted_participant", [0, 1])
def test_account_deletion_removes_exchange_and_cannot_be_undone_by_a_late_reply(
    client, pair, exchange_model, deleted_participant,
):
    import database

    exchange_id = _invite(client, pair)["id"]
    exchange_model.block(1)
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    try:
        assert exchange_model.started.wait(timeout=10)
        deleted = pair[deleted_participant]
        response = client.request("DELETE", "/account", headers=deleted["headers"], json={
            "confirmation": deleted["headers"]["X-Dev-User"],
        })
        assert response.status_code == 200, response.text
    finally:
        exchange_model.release.set()

    import services.exchange_service as exchange_service
    client.portal.call(exchange_service.wait_for_exchange, exchange_id)
    survivor = pair[1 - deleted_participant]
    assert client.get(f"/agent-exchanges/{exchange_id}", headers=survivor["headers"]).status_code == 404
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM agent_exchanges WHERE id = ?", (exchange_id,)).fetchone()[0] == 0
        for table in ("agent_exchange_messages", "agent_exchange_calls"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE exchange_id = ?", (exchange_id,)).fetchone()[0] == 0
    assert len(exchange_model.calls) == 1


@pytest.mark.parametrize("stopped_before_restart", [False, True], ids=["running", "stopped-with-inflight-call"])
def test_restart_recovery_permanently_stops_and_settles_an_unfinished_run(
    client, pair, exchange_model, stopped_before_restart,
):
    import exchange_store

    exchange_id = _invite(client, pair)["id"]
    exchange_model.block(1)
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    try:
        assert exchange_model.started.wait(timeout=10)
        reserved = _detail(client, pair[0], exchange_id)["exchange"]["usage"]
        assert reserved["reserved_tokens"] > 0
        assert reserved["model_calls"] == 1
        if stopped_before_restart:
            assert _act(client, pair[0], exchange_id, "stop").status_code == 200
        # Simulate recovery before the old process's delayed result reaches its CAS.
        client.portal.call(exchange_store.recover_interrupted_exchanges)
        stopped = _detail(client, pair[0], exchange_id)
        assert stopped["exchange"]["status"] == "stopped"
        if not stopped_before_restart:
            assert "重启" in stopped["exchange"]["error"]
        settled = stopped["exchange"]["usage"]
        assert settled["reserved_tokens"] == 0
        assert settled["estimated"] is True
        assert settled["input_tokens"] > 0
        assert settled["output_tokens"] == 256
        assert settled["total_tokens"] == reserved["reserved_tokens"]
        assert settled["budget_used"] == reserved["budget_used"]
        # A second startup must not charge the uncertain request twice.
        client.portal.call(exchange_store.recover_interrupted_exchanges)
        assert _detail(client, pair[0], exchange_id)["exchange"]["usage"] == settled
    finally:
        exchange_model.release.set()
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "stopped"
    assert final["messages"] == []
    assert not final["exchange"]["summary"]
    assert final["exchange"]["usage"] == settled
    assert len(exchange_model.calls) == 1
    assert _act(client, pair[1], exchange_id, "accept").status_code == 409


def test_exhausted_token_budget_stops_before_contacting_the_model(client, pair, exchange_model):
    import database

    exchange_id = _invite(client, pair)["id"]
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE agent_exchanges SET budget_used = token_budget - 1 WHERE id = ?", (exchange_id,))
    assert _act(client, pair[1], exchange_id, "accept").status_code == 200
    final = _wait(client, pair[0], exchange_id)
    assert final["exchange"]["status"] == "stopped"
    assert "上限" in final["exchange"]["error"]
    assert final["exchange"]["usage"]["model_calls"] == 0
    assert final["exchange"]["usage"]["reserved_tokens"] == 0
    assert final["messages"] == []
    assert exchange_model.calls == []


def test_participant_cannot_run_two_different_exchanges_concurrently(client, pair, exchange_model):
    third_headers = {"X-Dev-User": "exchange_third_partner"}
    response = client.put("/agents/me", headers=third_headers, json={"is_public": True, "display_name": "第三位分身"})
    assert response.status_code == 200, response.text
    third = {"headers": third_headers, "agent": response.json()["agent"]}
    first_id = _invite(client, pair)["id"]
    second_id = _invite(client, [pair[0], third])["id"]
    exchange_model.block(1)
    assert _act(client, pair[1], first_id, "accept").status_code == 200
    try:
        assert exchange_model.started.wait(timeout=10)
        blocked = _act(client, third, second_id, "accept")
        assert blocked.status_code == 409, blocked.text
        assert _detail(client, third, second_id)["exchange"]["status"] == "pending"
        assert len(exchange_model.calls) == 1
        assert _act(client, pair[0], first_id, "stop").status_code == 200
    finally:
        exchange_model.release.set()
    _wait(client, pair[0], first_id)
    assert _act(client, third, second_id, "accept").status_code == 200
    assert _wait(client, third, second_id)["exchange"]["status"] == "completed"


def test_pending_invitation_capacity_is_released_after_revocation(client, pair, exchange_model):
    exchanges = [_invite(client, pair)]
    others = []
    for index in range(3):
        headers = {"X-Dev-User": f"capacity_partner_{index}"}
        response = client.put("/agents/me", headers=headers, json={"is_public": True})
        assert response.status_code == 200, response.text
        others.append({"headers": headers, "agent": response.json()["agent"]})
    for participant in others[:2]:
        exchanges.append(_invite(client, [pair[0], participant]))

    payload = {"target_agent_id": others[2]["agent"]["id"], "topic": "第四个邀请", "max_turns": 2}
    response = client.post("/agent-exchanges", headers=pair[0]["headers"], json=payload)
    assert response.status_code == 409, response.text
    assert len(client.get("/agent-exchanges", headers=pair[0]["headers"]).json()["exchanges"]) == 3
    assert _act(client, pair[0], exchanges[0]["id"], "stop").status_code == 200
    response = client.post("/agent-exchanges", headers=pair[0]["headers"], json=payload)
    assert response.status_code == 201, response.text
    assert exchange_model.calls == []
