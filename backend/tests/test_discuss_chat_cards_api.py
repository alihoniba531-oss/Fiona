# -*- coding: utf-8 -*-
"""讨论群卡片接口与建群消费（规格 4.8、4.9.3、6.7、6.8、6.17）。

覆盖三条卡片路由的门控与归属、建群时消费任务卡、空串 task_id 的拒绝、
意见卡送出的幂等与拒绝文案，以及删群后两张卡片的去向。后台 runner 全部
换成 noop，不调用模型。
"""

import asyncio
import json
import uuid

import pytest
from fastapi import HTTPException

from discuss import cards, runner, service
from discuss import store as discuss_store
from rate_limit import limiter
from safety import CRISIS_RESOURCE_NOTE


USER = "discuss_cards_user"
OTHER = "discuss_cards_other"
HEADERS = {"X-Dev-User": USER}
OTHER_HEADERS = {"X-Dev-User": OTHER}

GROUP_BODY = {
    "request": "帮我研究一下东南亚短剧市场",
    "budget_strawberries": 500,
    "max_rounds": 2,
    "avatar": False,
}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def cards_ws(client, monkeypatch):
    """讨论群开关打开、白名单含两个用户，后台任务不运行。

    聊天侧两个开关明确关着：三条卡片路由不读它们。
    """
    monkeypatch.setenv("FIONA_DISCUSS", "1")
    monkeypatch.setenv("FIONA_DISCUSS_USERS", f"{USER},{OTHER}")
    monkeypatch.setenv("FIONA_DISCUSS_CHAT", "0")
    monkeypatch.setenv("FIONA_DISCUSS_CHAT_CARDS", "0")
    monkeypatch.setattr(limiter, "enabled", False)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(runner, "start_group", noop)
    monkeypatch.setattr(runner, "cancel_group", noop)
    return client


def make_task_card(request="帮我调研东南亚短剧市场", username=USER):
    return run(cards.create_task_card(username, "conversation-1", request))


def make_note_card(group_id, *, title="东南亚短剧",
                   text="告诉他们别查越南了", username=USER):
    return run(cards.create_note_card(
        username, "conversation-1", group_id, title, text))


def create_group(client, *, headers=HEADERS, **overrides):
    body = dict(GROUP_BODY)
    body.update(overrides)
    return client.post("/discuss/groups", json=body, headers=headers)


def fetch_row(sql, params=()):
    async def query():
        async with discuss_store.get_db() as db:
            async with db.execute(sql, params) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row is not None else None

    return run(query())


def fetch_scalar(sql, params=()):
    async def query():
        async with discuss_store.get_db() as db:
            async with db.execute(sql, params) as cursor:
                row = await cursor.fetchone()
        return row[0] if row is not None else None

    return run(query())


def task_card_row(card_id):
    return fetch_row("SELECT * FROM discuss_task_cards WHERE id=?", (card_id,))


def note_card_row(card_id):
    return fetch_row("SELECT * FROM discuss_note_cards WHERE id=?", (card_id,))


def own_group_count(username=USER):
    return int(fetch_scalar(
        "SELECT COUNT(*) FROM discuss_groups WHERE username=?", (username,)))


def own_note_count(group_id, username=USER):
    return int(fetch_scalar(
        "SELECT COUNT(*) FROM discuss_messages WHERE group_id=? AND username=? "
        "AND sender='user' AND kind='user'", (group_id, username)))


def set_group_status(group_id, status, username=USER):
    run(discuss_store.update_group(username, group_id, status=status))


def mark_consumed(message_id, marker="r01/02"):
    async def operation(db):
        await db.execute(
            "UPDATE discuss_messages SET consumed_by=? WHERE id=?",
            (marker, message_id),
        )

    run(discuss_store.run_write(operation))


# ── 门控与归属 ─────────────────────────────────────────────


def test_card_routes_require_switch_and_allowlist(cards_ws, monkeypatch):
    client = cards_ws
    task = make_task_card()
    created = create_group(client)
    assert created.status_code == 201, created.text
    note = make_note_card(created.json()["id"])

    assert task_card_row(task["id"]) is not None
    assert note_card_row(note["id"]) is not None

    task_path = f"/discuss/task-cards/{task['id']}"
    note_path = f"/discuss/note-cards/{note['id']}"
    send_path = f"/discuss/note-cards/{note['id']}/send"

    monkeypatch.setenv("FIONA_DISCUSS", "0")
    for method, path in (("get", task_path), ("get", note_path), ("post", send_path)):
        response = client.request(method, path, headers=HEADERS)
        assert response.status_code == 404, (method, path, response.text)

    monkeypatch.setenv("FIONA_DISCUSS", "1")
    monkeypatch.setenv("FIONA_DISCUSS_USERS", OTHER)
    for method, path in (("get", task_path), ("get", note_path), ("post", send_path)):
        response = client.request(method, path, headers=HEADERS)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["detail"] == "讨论群暂未对该账号开放"


def test_card_views_are_owner_scoped(cards_ws):
    client = cards_ws
    task = make_task_card()
    created = create_group(client)
    assert created.status_code == 201, created.text
    note = make_note_card(created.json()["id"])

    task_response = client.get(f"/discuss/task-cards/{task['id']}", headers=HEADERS)
    assert task_response.status_code == 200, task_response.text
    assert task_response.json()["request"] == "帮我调研东南亚短剧市场"
    assert task_response.json()["group_id"] is None
    assert task_response.json()["group"] is None

    other_task = client.get(f"/discuss/task-cards/{task['id']}", headers=OTHER_HEADERS)
    assert other_task.status_code == 404
    assert other_task.json()["detail"] == "任务卡不存在"

    note_response = client.get(f"/discuss/note-cards/{note['id']}", headers=HEADERS)
    assert note_response.status_code == 200, note_response.text
    assert note_response.json()["message"] is None
    assert note_response.json()["group_id"] == created.json()["id"]

    other_note = client.get(f"/discuss/note-cards/{note['id']}", headers=OTHER_HEADERS)
    assert other_note.status_code == 404
    assert other_note.json()["detail"] == "意见卡不存在"


# ── 建群消费任务卡 ─────────────────────────────────────────


def test_create_group_consumes_task_card_once(cards_ws):
    client = cards_ws
    task = make_task_card()
    first = create_group(client, task_id=task["id"])
    assert first.status_code == 201, first.text
    group_id = first.json()["id"]

    row = task_card_row(task["id"])
    assert row is not None
    assert row["group_id"] == group_id
    view = client.get(f"/discuss/task-cards/{task['id']}", headers=HEADERS).json()
    assert view["group_id"] == group_id
    assert view["group"] is not None
    assert view["group"]["id"] == group_id
    assert own_group_count() == 1

    # 让第一个群离开 planning，第二次才走到消费卡片这一步。
    set_group_status(group_id, "done")
    second = create_group(client, task_id=task["id"])
    assert second.status_code == 422, second.text
    assert second.json()["detail"] == "任务卡不存在或已使用"
    assert own_group_count() == 1
    row = task_card_row(task["id"])
    assert row is not None
    assert row["group_id"] == group_id


def test_create_group_with_unknown_task_id_rolls_back(cards_ws):
    client = cards_ws
    resp = create_group(client, task_id=str(uuid.uuid4()))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "任务卡不存在或已使用"
    assert own_group_count() == 0
    assert client.get("/discuss/groups", headers=HEADERS).json() == []


def test_create_group_with_empty_task_id_returns_422_and_leaves_no_group(cards_ws):
    client = cards_ws
    before_groups = client.get("/discuss/groups", headers=HEADERS)
    assert before_groups.status_code == 200
    assert before_groups.json() == []
    assert own_group_count() == 0
    assert int(fetch_scalar("SELECT COUNT(*) FROM discuss_task_cards")) == 0
    assert int(fetch_scalar("SELECT COUNT(*) FROM discuss_note_cards")) == 0

    response = create_group(client, task_id="")

    # 先断言目标：空串确实到了服务端，响应是 422，群数和群列表都没变，
    # 也没有顺带建出任何卡片。
    assert json.loads(response.request.content)["task_id"] == ""
    assert response.status_code == 422, response.text
    assert own_group_count() == 0
    after_groups = client.get("/discuss/groups", headers=HEADERS)
    assert after_groups.status_code == 200
    assert after_groups.json() == before_groups.json()
    assert int(fetch_scalar("SELECT COUNT(*) FROM discuss_task_cards")) == 0
    assert int(fetch_scalar("SELECT COUNT(*) FROM discuss_note_cards")) == 0

    # 再断言文案；空串不能因为“假值”被当成没带 task_id。
    assert response.json()["detail"] == "任务卡不存在或已使用"

    # 失败事务已回滚，不带 task_id 建群仍然成功。
    created = create_group(client)
    assert created.status_code == 201, created.text
    assert own_group_count() == 1


def test_create_group_without_task_id_leaves_card_open(cards_ws):
    client = cards_ws
    task = make_task_card()
    before = client.get("/discuss/groups", headers=HEADERS)
    assert before.status_code == 200
    assert before.json() == []

    created = create_group(client)
    assert created.status_code == 201, created.text
    row = task_card_row(task["id"])
    assert row is not None
    assert row["group_id"] is None
    view = client.get(f"/discuss/task-cards/{task['id']}", headers=HEADERS).json()
    assert view["group"] is None


# ── 意见卡送出 ─────────────────────────────────────────────


def test_send_note_card_twice_inserts_one_note(cards_ws):
    client = cards_ws
    created = create_group(client)
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    note = make_note_card(group_id)

    before = client.get(f"/discuss/note-cards/{note['id']}", headers=HEADERS)
    assert before.status_code == 200, before.text
    assert before.json()["message"] is None
    assert before.json()["sent_at"] is None
    assert own_note_count(group_id) == 0

    first = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert first.status_code == 200, first.text
    message = first.json()["message"]
    assert message is not None
    assert message["consumed"] is False
    assert first.json()["sent_at"] is not None
    assert own_note_count(group_id) == 1

    second = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert second.status_code == 200, second.text
    assert second.json()["message"] == message
    assert own_note_count(group_id) == 1

    mark_consumed(message["id"])
    after = client.get(f"/discuss/note-cards/{note['id']}", headers=HEADERS)
    assert after.status_code == 200, after.text
    assert after.json()["message"] == {"id": message["id"], "consumed": True}


def test_send_note_card_rejects_crisis_text_like_add_note(cards_ws):
    client = cards_ws
    created = create_group(client)
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    text = "我想自杀"
    note = make_note_card(group_id, text=text)
    row = note_card_row(note["id"])
    assert row is not None
    assert row["text"] == text
    assert row["message_id"] is None

    # 同一条危机文本走既有 add_note 也必须被拒，文案就是安全资源。
    with pytest.raises(HTTPException) as caught:
        run(service.add_note(USER, group_id, service.NoteIn(text=text)))
    assert caught.value.status_code == 400
    assert caught.value.detail == CRISIS_RESOURCE_NOTE
    assert own_note_count(group_id) == 0

    response = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert response.status_code == 400, response.text
    detail = response.json().get("detail")
    assert detail is not None
    assert detail == caught.value.detail
    assert detail == CRISIS_RESOURCE_NOTE
    assert own_note_count(group_id) == 0
    row = note_card_row(note["id"])
    assert row is not None
    assert row["message_id"] is None
    assert row["sent_at"] is None


def test_send_note_card_uses_current_group_round(cards_ws):
    client = cards_ws
    created = create_group(client)
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    note = make_note_card(group_id)
    assert note_card_row(note["id"]) is not None
    assert own_note_count(group_id) == 0

    assert run(discuss_store.update_group(USER, group_id, round=3)) is True
    assert fetch_scalar(
        "SELECT round FROM discuss_groups WHERE id=?", (group_id,)) == 3

    response = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert response.status_code == 200, response.text
    message = response.json()["message"]
    assert message is not None
    assert own_note_count(group_id) == 1

    row = fetch_row(
        "SELECT id, round, sender, kind, content FROM discuss_messages WHERE id=?",
        (message["id"],),
    )
    assert row is not None
    assert row["round"] == 3
    assert row["sender"] == "user"
    assert row["kind"] == "user"
    assert row["content"] == "告诉他们别查越南了"


def test_send_note_card_route_allows_twenty_then_rate_limits(cards_ws, monkeypatch):
    client = cards_ws
    created = create_group(client)
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    note = make_note_card(group_id)
    assert note_card_row(note["id"]) is not None
    path = f"/discuss/note-cards/{note['id']}/send"

    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    try:
        for index in range(20):
            response = client.post(path, headers=HEADERS)
            assert response.status_code == 200, (index + 1, response.text)
        limited = client.post(path, headers=HEADERS)
        assert limited.status_code == 429, limited.text
    finally:
        limiter.reset()


def test_send_note_card_rejects_ended_and_deleted_group(cards_ws):
    client = cards_ws
    created = create_group(client)
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    note = make_note_card(group_id)

    set_group_status(group_id, "closed")
    closed = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert closed.status_code == 409, closed.text
    assert closed.json()["detail"] == "讨论群已经结束"
    assert own_note_count(group_id) == 0
    row = note_card_row(note["id"])
    assert row is not None
    assert row["message_id"] is None

    set_group_status(group_id, "failed")
    failed = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert failed.status_code == 409, failed.text
    assert failed.json()["detail"] == "讨论群已经结束"
    assert own_note_count(group_id) == 0

    deleted = client.delete(f"/discuss/groups/{group_id}", headers=HEADERS)
    assert deleted.status_code == 200, deleted.text
    row = note_card_row(note["id"])
    assert row is not None
    assert row["group_id"] is None
    gone = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert gone.status_code == 409, gone.text
    assert gone.json()["detail"] == "这个讨论群已经删除"
    assert own_note_count(group_id) == 0


def test_send_note_card_rejects_five_unread_notes(cards_ws):
    client = cards_ws
    created = create_group(client)
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    for index in range(5):
        run(service.add_note(
            USER, group_id, service.NoteIn(text=f"第 {index} 条意见")))
    assert own_note_count(group_id) == 5
    note = make_note_card(group_id)

    response = client.post(f"/discuss/note-cards/{note['id']}/send", headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "还有 5 条插话没被读到，等主持人回应后再说"
    assert own_note_count(group_id) == 5
    row = note_card_row(note["id"])
    assert row is not None
    assert row["message_id"] is None


# ── 删群清理 ───────────────────────────────────────────────


def test_delete_group_releases_task_card_and_keeps_note_card(cards_ws):
    client = cards_ws
    task = make_task_card()
    created = create_group(client, task_id=task["id"])
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    task_row = task_card_row(task["id"])
    assert task_row is not None
    assert task_row["group_id"] == group_id
    note = make_note_card(group_id, title="东南亚短剧", text="告诉他们别查越南了")

    deleted = client.delete(f"/discuss/groups/{group_id}", headers=HEADERS)
    assert deleted.status_code == 200, deleted.text

    task_row = task_card_row(task["id"])
    assert task_row is not None
    assert task_row["group_id"] is None
    task_view = client.get(f"/discuss/task-cards/{task['id']}", headers=HEADERS)
    assert task_view.status_code == 200, task_view.text
    assert task_view.json()["group_id"] is None
    assert task_view.json()["group"] is None

    note_row = note_card_row(note["id"])
    assert note_row is not None
    assert note_row["group_id"] is None
    assert note_row["group_title"] == "东南亚短剧"
    assert note_row["text"] == "告诉他们别查越南了"
    note_view = client.get(f"/discuss/note-cards/{note['id']}", headers=HEADERS)
    assert note_view.status_code == 200, note_view.text
    assert note_view.json()["group_id"] is None
    assert note_view.json()["group"] is None
    assert note_view.json()["group_title"] == "东南亚短剧"

    # 任务卡回到可用状态，可以再建一个新群。
    again = create_group(client, task_id=task["id"])
    assert again.status_code == 201, again.text
    task_row = task_card_row(task["id"])
    assert task_row is not None
    assert task_row["group_id"] == again.json()["id"]
