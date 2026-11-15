# -*- coding: utf-8 -*-
"""讨论群 HTTP 接口与端到端流程（场景 1、2、3、4、5、6、10、13、15、18）。

全部离线：模型走 ``LLMRouter(dry_run=True, fake=FakeLLM(...))``，搜索替换
``discuss.research.search_once``，限流器关闭（除非专门测限流）。
"""
import asyncio
import json
import threading
import time

import pytest

from discuss import runner
from discuss import store as discuss_store
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from rate_limit import limiter
from safety import CRISIS_RESOURCE_NOTE, assess_crisis

USER = "discuss_author"
OTHER = "discuss_other"
HEADERS = {"X-Dev-User": USER}
OTHER_HEADERS = {"X-Dev-User": OTHER}

SUMMARY_FIELDS = {
    "id", "title", "status", "stop_reason", "round", "max_rounds",
    "budget_strawberries", "spent_strawberries", "output_version",
    "created_at", "updated_at",
}

PLAN = {
    "title": "讨论群测试方案",
    "goal": "把这件事查清楚并给出可执行建议",
    "deliverable": {"kind": "report", "outline": ["背景", "发现", "建议"]},
    "criteria": ["每个结论有来源", "覆盖两个调研方向", "给出明确建议"],
    "picks": [{"role": "market", "focus": "查市场"},
              {"role": "tech", "focus": "查技术"}],
    "questions": [],
}
QUERIES = {"queries": ["问题一"]}
NOTE = {
    "note": "市场与技术的初步结论 [S1]",
    "key_points": [{"text": "结论一 [S1]", "refs": ["S1"]},
                   {"text": "结论二 [S1]", "refs": ["S1"]}],
    "gaps": [],
}
CRITIQUE = {
    "objections": [{"target": "market", "type": "missing",
                    "problem": "缺少竞品对比", "suggestion": "补查竞品"}],
    "counter_view": "还需要更多证据",
}
DECIDE = {
    "responses": [{"id": "O1", "action": "accept", "reason": "接受"}],
    "note_responses": [],
    "decision": "draft",
    "assignments": [],
    "brief_for_writer": "按调研要点写",
    "summary": "本轮进展",
}
DECIDE_NOTE = dict(DECIDE, note_responses=[{"id": "N1", "reply": "会补充竞品对比"}])
DRAFT = "# 讨论群成果\n\n" + "这是根据调研要点写成的成果正文，结论都有来源支撑。" * 20 + "\n\n引用 [S1]。"
ACCEPT_PASS = {
    "verdicts": [{"id": "C1", "pass": True, "evidence": "有来源"},
                 {"id": "C2", "pass": True, "evidence": "覆盖两个方向"},
                 {"id": "C3", "pass": True, "evidence": "建议明确"}],
    "citation_issues": [],
    "rework": [],
}
ACCEPT_FAIL = {
    "verdicts": [{"id": "C1", "pass": False, "evidence": "缺少来源"},
                 {"id": "C2", "pass": True, "evidence": "覆盖两个方向"},
                 {"id": "C3", "pass": True, "evidence": "建议明确"}],
    "citation_issues": [],
    "rework": ["补上引用"],
}
REWORK = {"assignments": [], "note_responses": [],
          "brief_for_writer": "按意见修改", "summary": "返工"}
REWORK_NOTE = dict(REWORK, note_responses=[
    {"id": "N1", "reply": "已按你的意见补进结论"}])
BRIEF = {"context": "主人关心成本与落地", "answers": [], "ask_owner": []}
VIEW = {"comment": "对主人有用", "must_fix": []}

RESPONSES = {
    "plan": PLAN,
    "queries": QUERIES,
    "note": NOTE,
    "critique": CRITIQUE,
    "decide": DECIDE,
    "draft": DRAFT,
    "accept": ACCEPT_PASS,
    "rework": REWORK,
    "brief": BRIEF,
    "view": VIEW,
}


def search_once(query, context):
    return {
        "query": query,
        "data": {"findings": [{"fact": "一条可核实的事实", "refs": [1]}]},
        "sources": [{"title": "来源一", "url": "https://example.com/a",
                     "site_name": "站点", "index": 1}],
        "error": None,
    }


@pytest.fixture
def workshop(client, monkeypatch):
    monkeypatch.setenv("FIONA_DISCUSS", "1")
    monkeypatch.setenv("FIONA_DISCUSS_USERS", f"{USER},{OTHER}")
    monkeypatch.setattr(limiter, "enabled", False)
    fake = FakeLLM(dict(RESPONSES))
    monkeypatch.setattr(
        runner, "router_factory",
        lambda store, username, group_id, run_token: LLMRouter(
            store, dry_run=True, fake=fake))
    monkeypatch.setattr("discuss.research.search_once", search_once)
    return client, fake


def create_group(client, *, max_rounds=2, avatar=False, headers=HEADERS, **overrides):
    body = {
        "request": "帮我研究一下这个方向",
        "budget_strawberries": 500,
        "max_rounds": max_rounds,
        "avatar": avatar,
    }
    body.update(overrides)
    response = client.post("/discuss/groups", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def wait(client, group_id, state, headers=HEADERS):
    data = None
    for _ in range(600):
        response = client.get("/discuss/groups/" + group_id, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] == state:
            return data
        if data["status"] in ("failed", "paused") and state not in ("failed", "paused"):
            pytest.fail("群意外停下：" + str(data))
        time.sleep(0.01)
    pytest.fail("等待超时：" + str(data))


def start(client, group_id, revision):
    response = client.post(f"/discuss/groups/{group_id}/start",
                           json={"expected_revision": revision}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def table_counts(group_id):
    async def query():
        counts = {}
        async with discuss_store.get_db() as db:
            for table in ("discuss_groups", "discuss_messages", "discuss_sources",
                          "discuss_steps", "discuss_outputs"):
                column = "id" if table == "discuss_groups" else "group_id"
                async with db.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (group_id,)) as cursor:
                    counts[table] = (await cursor.fetchone())[0]
        return counts

    return asyncio.run(query())


def set_script(fake, script):
    fake.script = script


def last_call_payload(fake, step_key):
    """Return the JSON payload sent to the model for one step key."""
    calls = [call for call in fake.calls if call.get("step_key") == step_key]
    assert calls, "模型没有收到步骤 " + step_key
    for message in reversed(calls[-1]["messages"]):
        if message.get("role") == "user":
            return json.loads(message["content"])
    raise AssertionError("步骤 " + step_key + " 没有 user 载荷")


def blocked_script(entered, release, *, block_task, overrides=None):
    """Async FakeLLM script that holds one called task until the test releases it."""
    responses = dict(RESPONSES)
    if overrides:
        responses.update(overrides)

    async def script(request, index):
        task = request.get("task")
        if task == block_task:
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        step_key = request.get("step_key")
        if overrides and step_key in overrides:
            return overrides[step_key]
        return responses[task]

    return script


def stored_group_row(group_id, username=USER):
    """Read one group through the store, including its decoded config."""
    return asyncio.run(discuss_store.get_group(username, group_id))


def stored_group_count(username=USER):
    async def query():
        async with discuss_store.get_db() as db:
            async with db.execute(
                    "SELECT COUNT(*) FROM discuss_groups WHERE username=?",
                    (username,)) as cursor:
                return int((await cursor.fetchone())[0])

    return asyncio.run(query())


def stored_group_step_keys(group_id):
    """Return (discuss_steps keys, discuss_messages step keys) for one group."""
    async def query():
        async with discuss_store.get_db() as db:
            async with db.execute(
                    "SELECT step_key FROM discuss_steps WHERE group_id=?",
                    (group_id,)) as cursor:
                steps = [row[0] for row in await cursor.fetchall()]
            async with db.execute(
                    "SELECT step_key FROM discuss_messages WHERE group_id=? "
                    "AND step_key IS NOT NULL",
                    (group_id,)) as cursor:
                messages = [row[0] for row in await cursor.fetchall()]
        return steps, messages

    return asyncio.run(query())


def seed_other_group(status="running", group_id="other-running-group", username=USER):
    """Create a second group for the same user directly through the store."""
    async def seed():
        await discuss_store.create_group(
            username, group_id=group_id,
            request="另一个正在进行的讨论群", materials="",
            budget_strawberries=500, max_rounds=2,
            config={"avatar": False}, created_day="2026-01-01")
        if status != "planning":
            await discuss_store.update_group(username, group_id, status=status)

    asyncio.run(seed())
    return group_id


def seed_many_groups(count, username=USER):
    """Insert many rows in one transaction, bypassing the HTTP create path."""
    async def operation(db):
        for index in range(count):
            await discuss_store.create_group_on_connection(
                db, username, group_id=f"bulk-group-{index:02d}",
                request="批量讨论群用于验证列表上限", materials="",
                budget_strawberries=500, max_rounds=2,
                config={"avatar": False}, created_day="2026-01-01")

    asyncio.run(discuss_store.run_write(operation))


# ── 场景 1：准入 ───────────────────────────────────────────────

ROUTES = [
    ("GET", "/discuss/access"),
    ("GET", "/discuss/catalog"),
    ("POST", "/discuss/groups"),
    ("GET", "/discuss/groups"),
    ("GET", "/discuss/groups/missing-group"),
    ("PATCH", "/discuss/groups/missing-group/plan"),
    ("POST", "/discuss/groups/missing-group/start"),
    ("POST", "/discuss/groups/missing-group/notes"),
    ("POST", "/discuss/groups/missing-group/pause"),
    ("POST", "/discuss/groups/missing-group/resume"),
    ("POST", "/discuss/groups/missing-group/continue"),
    ("POST", "/discuss/groups/missing-group/accept"),
    ("POST", "/discuss/groups/missing-group/close"),
    ("DELETE", "/discuss/groups/missing-group"),
    ("GET", "/discuss/groups/missing-group/sources"),
    ("GET", "/discuss/groups/missing-group/output"),
    ("GET", "/discuss/groups/missing-group/export"),
]


@pytest.mark.parametrize("value", [None, "0", "true"])
def test_admission_hides_every_route_when_disabled(client, monkeypatch, value):
    """场景 1：开关未设或不是字面 1 时，全部 /discuss/* 路由都 404。"""
    if value is None:
        monkeypatch.delenv("FIONA_DISCUSS", raising=False)
    else:
        monkeypatch.setenv("FIONA_DISCUSS", value)
    monkeypatch.setenv("FIONA_DISCUSS_USERS", f"{USER},{OTHER}")
    for method, path in ROUTES:
        kwargs = {"headers": HEADERS}
        if method in ("POST", "PATCH", "DELETE"):
            kwargs["json"] = {}
        response = client.request(method, path, **kwargs)
        assert response.status_code == 404, (value, method, path, response.text)
        assert response.json() == {"detail": "Not Found"}, (method, path, response.json())


def test_admission_whitelist_and_access(workshop, monkeypatch):
    """场景 1：白名单外 403 固定文案；白名单内 /discuss/access 为 allowed。"""
    client, _ = workshop
    monkeypatch.setenv("FIONA_DISCUSS_USERS", "someone_else")
    response = client.get("/discuss/access", headers=HEADERS)
    assert response.status_code == 403
    assert response.json() == {"detail": "讨论群暂未对该账号开放"}
    monkeypatch.setenv("FIONA_DISCUSS_USERS", USER)
    response = client.get("/discuss/access", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"allowed": True}


# ── 场景 2：建群到等开工 ─────────────────────────────────────

def test_create_group_planning_then_awaiting_start(workshop):
    """场景 2：201、planning→awaiting_start、C 编号、成员顺序、plan 消息与摘要字段。"""
    client, fake = workshop
    entered, release = threading.Event(), threading.Event()
    set_script(fake, blocked_script(entered, release, block_task="plan"))
    response = client.post("/discuss/groups", json={
        "request": "帮我研究一下这个方向",
        "budget_strawberries": 600,
        "max_rounds": 2,
    }, headers=HEADERS)
    assert response.status_code == 201, response.text
    summary = response.json()
    assert summary["status"] == "planning"
    assert SUMMARY_FIELDS <= set(summary)
    assert entered.wait(5), "规划步骤没有开始"
    release.set()
    data = wait(client, summary["id"], "awaiting_start")

    assert data["title"] == PLAN["title"]
    assert [item["id"] for item in data["plan"]["criteria"]] == ["C1", "C2", "C3"]
    roles = [member["role"] for member in data["members"]]
    assert roles == ["host", "market", "tech", "critic", "writer", "acceptor", "avatar"]
    kinds = [message["kind"] for message in data["messages"]]
    assert "plan" in kinds
    for field in SUMMARY_FIELDS:
        assert field in data, field
    listed = client.get("/discuss/groups", headers=HEADERS).json()
    assert [item["id"] for item in listed] == [summary["id"]]
    assert SUMMARY_FIELDS <= set(listed[0])


# ── 场景 3：改方案 ───────────────────────────────────────────

def test_patch_plan_changes_and_guards(workshop):
    """场景 3：改标准/成员/预算生效且 plan_revision+1；版本不符与非 awaiting_start 409；非法输入 422。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")

    bad_role = {"expected_revision": 1,
                "picks": [{"role": "not-a-role", "focus": "查不存在的事"},
                          {"role": "tech", "focus": "查技术"}]}
    assert client.patch(f"/discuss/groups/{group_id}/plan",
                        json=bad_role, headers=HEADERS).status_code == 422
    short_criteria = {"expected_revision": 1, "criteria": ["只有一条", "只有两条"]}
    assert client.patch(f"/discuss/groups/{group_id}/plan",
                        json=short_criteria, headers=HEADERS).status_code == 422

    body = {
        "expected_revision": 1,
        "title": "改后的标题",
        "criteria": ["标准一", "标准二", "标准三", "标准四"],
        "picks": [{"role": "market", "focus": "改后的市场分工"},
                  {"name": "成本顾问", "does": "查成本结构", "focus": "查成本"}],
        "budget_strawberries": 800,
    }
    response = client.patch(f"/discuss/groups/{group_id}/plan",
                            json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan_revision"] == 2
    assert data["title"] == "改后的标题"
    assert data["budget_strawberries"] == 800
    assert [item["id"] for item in data["plan"]["criteria"]] == ["C1", "C2", "C3", "C4"]
    assert [item["role"] for item in data["plan"]["picks"]] == ["market", "custom1"]
    assert "成本顾问" in [member["name"] for member in data["members"]]
    assert [member["role"] for member in data["members"]] == [
        "host", "market", "custom1", "critic", "writer", "acceptor"]

    stale = dict(body, expected_revision=1)
    response = client.patch(f"/discuss/groups/{group_id}/plan",
                            json=stale, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "方案已被修改，请刷新后再改"

    start(client, group_id, 2)
    late = dict(body, expected_revision=2)
    response = client.patch(f"/discuss/groups/{group_id}/plan",
                            json=late, headers=HEADERS)
    assert response.status_code == 409


# ── 场景 15：上限 ───────────────────────────────────────────

def test_second_group_while_one_active_is_409(workshop):
    """场景 15：同一用户已有 planning/running 的群时再建 409。"""
    client, _ = workshop
    group = create_group(client)
    wait(client, group["id"], "awaiting_start")
    asyncio.run(discuss_store.update_group(USER, group["id"], status="running"))
    response = client.post("/discuss/groups", json={
        "request": "再帮我研究一个全新的方向",
        "budget_strawberries": 500,
        "max_rounds": 2,
        "avatar": False,
    }, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "你有一个讨论群正在进行，等它停下来再建新的"


def test_daily_group_cap_applies_in_dev_mode(workshop, monkeypatch):
    """场景 15：FIONA_DAILY_DISCUSS_GROUPS=1 时当天第二个群 429，DEV_MODE=1 同样生效。"""
    client, _ = workshop
    assert __import__("os").getenv("DEV_MODE") == "1"
    group = create_group(client)
    wait(client, group["id"], "awaiting_start")
    monkeypatch.setenv("FIONA_DAILY_DISCUSS_GROUPS", "1")
    response = client.post("/discuss/groups", json={
        "request": "今天再研究一个新的方向",
        "budget_strawberries": 500,
        "max_rounds": 2,
        "avatar": False,
    }, headers=HEADERS)
    assert response.status_code == 429
    assert response.json()["detail"] == "今天新建的讨论群已到上限，明天再来"


# ── 场景 4：一轮通过 ───────────────────────────────────────

def test_one_round_pass_reaches_done(workshop):
    """场景 4：note→critique→decision→draft→verdict，最终 done/accepted，一版成果通过。"""
    client, _ = workshop
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    data = wait(client, group_id, "done")

    assert data["stop_reason"] == "accepted"
    assert data["round"] == 1
    assert data["output_version"] == 1
    assert data["output"]["version"] == 1
    assert data["output"]["passed"] is True
    kinds = [message["kind"] for message in data["messages"]]
    for kind in ("note", "critique", "decision", "draft", "verdict"):
        assert kind in kinds, (kind, kinds)
    order = [kinds.index(kind) for kind in
             ("note", "critique", "decision", "draft", "verdict")]
    assert order == sorted(order)

    output = client.get(f"/discuss/groups/{group_id}/output", headers=HEADERS)
    assert output.status_code == 200
    assert output.json()["passed"] is True and output.json()["version"] == 1
    export = client.get(f"/discuss/groups/{group_id}/export", headers=HEADERS)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/markdown; charset=utf-8")
    assert "attachment" in export.headers["content-disposition"]
    assert "## 来源" in export.text and "S1" in export.text


# ── 场景 5：返工后通过 ─────────────────────────────────────

def test_rework_then_second_version_passes(workshop):
    """场景 5：第一轮不过出现 rework，第二轮第二版通过；round=2、两版成果。"""
    client, fake = workshop
    set_script(fake, {**RESPONSES, "r01/50-accept-acceptor": ACCEPT_FAIL})
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    data = wait(client, group_id, "done")

    assert data["stop_reason"] == "accepted"
    assert data["round"] == 2
    assert data["output_version"] == 2
    kinds = [message["kind"] for message in data["messages"]]
    assert kinds.count("draft") == 2
    assert kinds.count("verdict") == 2
    assert "rework" in kinds
    first = client.get(f"/discuss/groups/{group_id}/output?version=1", headers=HEADERS)
    second = client.get(f"/discuss/groups/{group_id}/output?version=2", headers=HEADERS)
    assert first.status_code == 200 and first.json()["passed"] is False
    assert second.status_code == 200 and second.json()["passed"] is True


# ── 场景 6：轮数用尽与 continue ────────────────────────────

def test_rounds_exhausted_then_continue(workshop):
    """场景 6：max_rounds=1 且验收不过进入 awaiting_user/rounds_exhausted；continue 后跑完。"""
    client, fake = workshop
    set_script(fake, {**RESPONSES, "r01/50-accept-acceptor": ACCEPT_FAIL})
    group = create_group(client, max_rounds=1)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    data = wait(client, group_id, "awaiting_user")
    assert data["stop_reason"] == "rounds_exhausted"
    assert data["output_version"] == 1
    assert data["output"]["passed"] is False

    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = wait(client, group_id, "done")
    assert data["max_rounds"] == 2
    assert data["round"] == 2
    assert data["output_version"] == 2
    assert data["output"]["passed"] is True


def test_continue_over_ten_rounds_is_422(workshop):
    """场景 6：continue 后总轮数超过 10 时 422。"""
    client, _ = workshop
    group = create_group(client, max_rounds=6)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    asyncio.run(discuss_store.update_group(
        USER, group_id, status="awaiting_user", round=9, max_rounds=9,
        stop_reason="rounds_exhausted"))
    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={"add_rounds": 3}, headers=HEADERS)
    assert response.status_code == 422


# ── 场景 10：运行中插话 ───────────────────────────────────

def test_note_during_run_is_consumed_by_decision(workshop):
    """场景 10：运行中插话后 pending_notes 变化，读取点回应并以 consumed 标记。"""
    client, fake = workshop
    entered, release = threading.Event(), threading.Event()
    set_script(fake, blocked_script(
        entered, release, block_task="critique",
        overrides={"r01/30-decide-host": DECIDE_NOTE}))
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    assert entered.wait(5), "质疑步骤没有开始"

    before = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert before["status"] == "running"
    assert before["pending_notes"] == 0
    response = client.post(f"/discuss/groups/{group_id}/notes",
                           json={"text": "重点看看竞品对比"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["pending_notes"] == 1
    release.set()
    data = wait(client, group_id, "done")
    assert data["pending_notes"] == 0

    user_notes = [message for message in data["messages"] if message["kind"] == "user"]
    assert len(user_notes) == 1
    assert user_notes[0]["content"] == "重点看看竞品对比"
    assert user_notes[0]["consumed"] is True
    decision = next(message for message in data["messages"] if message["kind"] == "decision")
    assert decision["payload"]["note_responses"] == [
        {"id": "N1", "reply": "会补充竞品对比"}]
    assert "会补充竞品对比" in decision["content"]


# ── 场景 13：暂停与继续 ───────────────────────────────────

def test_pause_then_resume_reuses_steps_and_keeps_messages_unique(workshop):
    """场景 13：暂停后 paused/user、令牌空、reserved=0；继续不重复模型步骤与消息。"""
    client, fake = workshop
    entered, release = threading.Event(), threading.Event()
    set_script(fake, blocked_script(entered, release, block_task="draft"))
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    assert entered.wait(5), "撰稿步骤没有开始"

    response = client.post(f"/discuss/groups/{group_id}/pause",
                           json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    paused = wait(client, group_id, "paused")
    assert paused["stop_reason"] == "user"
    assert paused["reserved_strawberries"] == 0

    async def token():
        group_row = await discuss_store.get_group(USER, group_id)
        return group_row["run_token"]

    assert asyncio.run(token()) is None
    ids_before = [message["id"] for message in paused["messages"]]
    calls_before = len(fake.calls)

    release.set()
    response = client.post(f"/discuss/groups/{group_id}/resume",
                           json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = wait(client, group_id, "done")

    ids_after = [message["id"] for message in data["messages"]]
    assert len(ids_after) == len(set(ids_after))
    assert set(ids_before) <= set(ids_after)
    assert [message["kind"] for message in data["messages"]].count("plan") == 1
    assert [message["kind"] for message in data["messages"]].count("note") == 2
    assert [message["kind"] for message in data["messages"]].count("draft") == 1

    step_keys = [call["step_key"] for call in fake.calls]
    assert step_keys.count("r00/01-plan-host") == 1
    assert step_keys.count("r01/10-queries-market") == 1
    assert step_keys.count("r01/13-note-market") == 1
    assert step_keys.count("r01/20-critique-critic") == 1
    assert step_keys.count("r01/30-decide-host") == 1
    assert len(fake.calls) > calls_before


# ── 场景 18：隔离与清理 ───────────────────────────────────

def test_other_user_cannot_touch_group(workshop):
    """场景 18：另一个账号读不到、也操作不了别人的群（全部 404）。"""
    client, fake = workshop
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    wait(client, group_id, "done")
    calls = len(fake.calls)
    operations = [
        ("GET", "", None),
        ("PATCH", "/plan", {"expected_revision": 1}),
        ("POST", "/start", {"expected_revision": 1}),
        ("POST", "/notes", {"text": "越权插话"}),
        ("POST", "/pause", {}),
        ("POST", "/resume", {}),
        ("POST", "/continue", {}),
        ("POST", "/accept", {}),
        ("POST", "/close", {}),
        ("DELETE", "", None),
        ("GET", "/sources", None),
        ("GET", "/output", None),
        ("GET", "/export", None),
    ]
    for method, suffix, body in operations:
        kwargs = {"headers": OTHER_HEADERS}
        if body is not None:
            kwargs["json"] = body
        response = client.request(method, f"/discuss/groups/{group_id}{suffix}", **kwargs)
        assert response.status_code == 404, (method, suffix, response.text)
    assert len(fake.calls) == calls
    assert client.get(f"/discuss/groups/{group_id}", headers=HEADERS).status_code == 200


def test_delete_group_removes_all_five_tables(workshop):
    """场景 18：删群后五张表里没有该群的行。"""
    client, _ = workshop
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    wait(client, group_id, "done")
    count_before = table_counts(group_id)
    assert count_before["discuss_groups"] == 1
    assert count_before["discuss_messages"] > 0
    assert count_before["discuss_steps"] > 0
    assert count_before["discuss_sources"] > 0
    assert count_before["discuss_outputs"] == 1

    response = client.delete(f"/discuss/groups/{group_id}", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert table_counts(group_id) == {table: 0 for table in count_before}


def test_closed_group_rejects_notes(workshop):
    """场景 18：closed 后插话 409。"""
    client, _ = workshop
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    response = client.post(f"/discuss/groups/{group_id}/close",
                           json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()["status"] == "closed"
    response = client.post(f"/discuss/groups/{group_id}/notes",
                           json={"text": "已经结束了"}, headers=HEADERS)
    assert response.status_code == 409


# ── 场景 9 补充：无引用来源的导出 ─────────────────────────

def test_export_without_sources_keeps_source_heading(workshop):
    """场景 9 补充：成果没有引用来源时导出仍保留来源标题。"""
    client, _ = workshop
    group_id = "export-no-source-01"
    content = (
        "# 无引用成果\n\n"
        "这是一段不含编号引用的 Markdown 正文，用来验证没有引用来源时导出仍保留来源标题。\n\n"
        "- 第一条建议\n"
        "- 第二条建议"
    )
    assert "[S" not in content

    async def seed():
        async with discuss_store.get_db() as db:
            await db.execute(
                "INSERT INTO discuss_groups ("
                "id, username, title, request, status, round, max_rounds, "
                "budget_strawberries, output_version, created_day, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (group_id, USER, "无引用成果", "整理一份没有引用的成果", "done",
                 1, 2, 300, 1, "2026-01-01",
                 "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
            await db.execute(
                "INSERT INTO discuss_outputs ("
                "group_id, username, version, round, step_key, content, passed, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (group_id, USER, 1, 1, "r01/40-draft-writer", content, 1,
                 "2026-01-01T00:00:00+00:00"),
            )
            await db.commit()

    asyncio.run(seed())

    response = client.get(f"/discuss/groups/{group_id}/export", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown; charset=utf-8")
    assert response.headers["content-disposition"].startswith("attachment")
    assert "## 来源" in response.text
    assert response.text == content + "\n\n## 来源\n\n"


# ── 返修 R1：完成后的 continue、无成果 accept、开工版本 ─────────

def test_done_continue_with_note_reworks_and_adds_second_version(workshop):
    """T1/E3：done 后插话再 continue，重放上一轮收尾时走 60-rework-host 并出新一版。"""
    client, fake = workshop
    set_script(fake, {**RESPONSES, "r01/60-rework-host": REWORK_NOTE})
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    first = wait(client, group_id, "done")
    assert first["stop_reason"] == "accepted"
    assert first["round"] == 1
    assert first["output_version"] == 1

    note_text = "把竞品对比补进结论，并给出价格区间"
    response = client.post(f"/discuss/groups/{group_id}/notes",
                           json={"text": note_text}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["content"] == note_text
    assert client.get(f"/discuss/groups/{group_id}",
                      headers=HEADERS).json()["pending_notes"] == 1

    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={"add_rounds": 1}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] in ("running", "done")
    data = wait(client, group_id, "done")

    assert data["output_version"] == 2
    assert data["output"]["version"] == 2
    assert data["output"]["passed"] is True
    assert data["round"] == 2
    reworks = [message for message in data["messages"] if message["kind"] == "rework"]
    assert len(reworks) == 1
    assert reworks[0]["round"] == 1
    assert reworks[0]["payload"]["note_responses"] == [
        {"id": "N1", "reply": "已按你的意见补进结论"}]
    assert "已按你的意见补进结论" in reworks[0]["content"]
    user_notes = [message for message in data["messages"] if message["kind"] == "user"]
    assert len(user_notes) == 1
    assert user_notes[0]["content"] == note_text
    assert user_notes[0]["consumed"] is True

    request_payload = last_call_payload(fake, "r01/60-rework-host")
    assert request_payload["round"] == 1
    assert request_payload["user_notes"] == [{"id": "N1", "text": note_text}]

    output = client.get(f"/discuss/groups/{group_id}/output?version=2", headers=HEADERS)
    assert output.status_code == 200, output.text
    assert output.json()["version"] == 2


def test_done_continue_without_note_is_409_then_note_allows_rework(workshop):
    """T14/S6：done 且无未读插话时 continue 返回 409 固定文案；插话后同一请求启动返工。"""
    client, fake = workshop
    set_script(fake, {**RESPONSES, "r01/60-rework-host": REWORK_NOTE})
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    start(client, group_id, 1)
    wait(client, group_id, "done")

    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={}, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "先在群里写下你的意见，再点按意见返工"
    unchanged = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert unchanged["status"] == "done"
    assert unchanged["output_version"] == 1
    assert unchanged["pending_notes"] == 0

    note_text = "结论要给出价格区间"
    response = client.post(f"/discuss/groups/{group_id}/notes",
                           json={"text": note_text}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert client.get(f"/discuss/groups/{group_id}",
                      headers=HEADERS).json()["pending_notes"] == 1

    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={}, headers=HEADERS)
    assert response.status_code in (200, 202), response.text
    assert response.json()["status"] in ("running", "done")
    data = wait(client, group_id, "done")
    assert data["output_version"] == 2
    assert any(message["kind"] == "rework" for message in data["messages"])


def test_accept_without_any_output_is_409(workshop):
    """T15/S10：群可接受但还没有成果时 accept 返回 409，不会凭空完成。"""
    client, _ = workshop
    group = create_group(client)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")

    async def force_awaiting_user():
        async with discuss_store.get_db() as db:
            await db.execute(
                "UPDATE discuss_groups SET status='awaiting_user' "
                "WHERE id=? AND username=?", (group_id, USER))
            await db.commit()

    asyncio.run(force_awaiting_user())
    before = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert before["status"] == "awaiting_user"
    assert before["output_version"] == 0

    response = client.post(f"/discuss/groups/{group_id}/accept", headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "还没有成果可以接受"
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["status"] == "awaiting_user"
    assert after["output_version"] == 0


def test_start_with_stale_revision_is_409_and_keeps_awaiting_start(workshop):
    """T16/S11：开工版本不符时 409，群仍是 awaiting_start；正确版本可以开工。"""
    client, fake = workshop
    group = create_group(client)
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")
    assert data["plan_revision"] == 1
    calls_before = len(fake.calls)

    response = client.post(f"/discuss/groups/{group_id}/start",
                           json={"expected_revision": 2}, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "方案已被修改，请刷新后再改"
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["status"] == "awaiting_start"
    assert after["plan_revision"] == 1
    assert len(fake.calls) == calls_before

    start(client, group_id, 1)
    done = wait(client, group_id, "done")
    assert done["status"] == "done"
    assert done["stop_reason"] == "accepted"


# ── R2：预算耗尽与结束前暂停 ─────────────────────────────────

def test_resume_and_continue_reject_exhausted_budget_until_added(workshop, monkeypatch):
    """T18 / S8：预算已用完时 resume 与 continue 都 409，加够预算后成功。"""
    client, _ = workshop

    group = create_group(client, avatar=False)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")

    async def no_start(*args, **kwargs):
        return None

    monkeypatch.setattr(runner, "start_group", no_start)

    async def set_state(**fields):
        await discuss_store.update_group(USER, group_id, **fields)

    asyncio.run(set_state(status="paused", stop_reason="user", round=1,
                          budget_strawberries=500, spent_strawberries=500))
    response = client.post(f"/discuss/groups/{group_id}/resume",
                           json={}, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "预算已经用完，请先调高预算"
    data = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert (data["status"], data["budget_strawberries"],
            data["spent_strawberries"]) == ("paused", 500, 500)

    response = client.post(f"/discuss/groups/{group_id}/resume",
                           json={"add_budget": 100}, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "running" and data["budget_strawberries"] == 600

    asyncio.run(set_state(status="awaiting_user", stop_reason="rounds_exhausted", round=1,
                          budget_strawberries=500, spent_strawberries=500))
    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={}, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "预算已经用完，请先调高预算"
    data = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert (data["status"], data["budget_strawberries"],
            data["spent_strawberries"]) == ("awaiting_user", 500, 500)

    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={"add_budget": 100}, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "running" and data["budget_strawberries"] == 600


def test_close_rejects_planning_or_running_until_paused(workshop):
    """T19 / S9：planning/running 时 close 409，暂停后才能结束。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")

    async def set_state(**fields):
        await discuss_store.update_group(USER, group_id, **fields)

    asyncio.run(set_state(status="planning", run_token="manual-token"))
    response = client.post(f"/discuss/groups/{group_id}/close", headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "先暂停再结束"
    data = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert data["status"] == "planning"

    asyncio.run(set_state(status="running", run_token="manual-token"))
    response = client.post(f"/discuss/groups/{group_id}/close", headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "先暂停再结束"
    data = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert data["status"] == "running"

    response = client.post(f"/discuss/groups/{group_id}/pause", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paused"
    response = client.post(f"/discuss/groups/{group_id}/close", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"


# ── 复核返修：M2 立项暂停后继续、G 身份与重名、X22/X30/X31/X32/X33/X27/X28/X39/X44 ──

def test_avatar_brief_pause_then_resume_waits_for_start(workshop):
    """M2 / X40：brief 阻塞时暂停，继续后停在 awaiting_start，没有 r01 及以后的内容。"""
    client, fake = workshop
    entered, release = threading.Event(), threading.Event()
    set_script(fake, blocked_script(entered, release, block_task="brief"))
    group = create_group(client, avatar=True)
    group_id = group["id"]
    assert entered.wait(5), "分身 brief 步骤没有开始"

    response = client.post(f"/discuss/groups/{group_id}/pause",
                           json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    paused = wait(client, group_id, "paused")
    assert paused["stop_reason"] == "user"
    assert paused["round"] == 0
    assert paused["plan_revision"] == 1
    assert paused["reserved_strawberries"] == 0
    release.set()

    response = client.post(f"/discuss/groups/{group_id}/resume",
                           json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = wait(client, group_id, "awaiting_start")

    assert data["round"] == 0
    assert data["output_version"] == 0
    assert [message["kind"] for message in data["messages"]].count("plan") == 1
    assert [message["kind"] for message in data["messages"]].count("brief") == 1
    assert all(message["round"] == 0 for message in data["messages"]), data["messages"]

    step_keys, message_step_keys = stored_group_step_keys(group_id)
    assert step_keys and all(key.startswith("r00/") for key in step_keys), step_keys
    assert all(key.startswith("r00/") for key in message_step_keys), message_step_keys

    brief_calls = [call for call in fake.calls
                   if call.get("step_key") == "r00/02-brief-avatar"]
    assert len(brief_calls) >= 2 or "r00/02-brief-avatar-skip" in message_step_keys

    start(client, group_id, data["plan_revision"])
    done = wait(client, group_id, "done")
    assert (done["status"], done["stop_reason"]) == ("done", "accepted")
    assert done["round"] == 1
    assert done["output_version"] == 1


def test_create_group_rejects_duplicate_member_names(workshop):
    """G / 规格 4.13 第 2 条：建群时 members 名字重复返回 422，且不落库。"""
    client, _ = workshop
    response = client.post("/discuss/groups", json={
        "request": "帮我研究一下这个方向",
        "budget_strawberries": 500,
        "max_rounds": 2,
        "avatar": False,
        "members": [
            {"name": "同名顾问", "does": "负责市场调研"},
            {"name": "同名顾问", "does": "负责技术调研"},
        ],
    }, headers=HEADERS)
    assert response.status_code == 422, response.text
    assert stored_group_count() == 0


def test_patch_identity_clears_name_and_persona(workshop):
    """G / v1.2 第 6 条：固定席位 name="" 恢复默认名，persona 仍可清空。"""
    client, _ = workshop
    group = create_group(client, avatar=False, identities={
        "host": {"name": "老陈", "persona": "谨慎追问"}})
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")
    host = next(member for member in data["members"] if member["role"] == "host")
    assert (host["name"], host["does"]) == ("老陈", "谨慎追问")

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": data["plan_revision"],
        "identities": {"host": {"name": ""}},
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    host = next(member for member in data["members"] if member["role"] == "host")
    assert host["name"] == "主持人"
    assert host["does"] == "谨慎追问"

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": data["plan_revision"],
        "identities": {"host": {"persona": ""}},
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    host = next(member for member in data["members"] if member["role"] == "host")
    assert host["name"] == "主持人"
    assert host["does"] == ""


def test_create_group_materials_crisis_is_400_without_row(workshop):
    """X22：materials 命中明确危机时 400 CRISIS_RESOURCE_NOTE，且不落库。"""
    client, _ = workshop
    materials = "补充材料：我最近总想自杀"
    assert assess_crisis(materials) == "high"
    response = client.post("/discuss/groups", json={
        "request": "帮我研究一下这个方向",
        "materials": materials,
        "budget_strawberries": 500,
        "max_rounds": 2,
        "avatar": False,
    }, headers=HEADERS)
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == CRISIS_RESOURCE_NOTE
    assert stored_group_count() == 0


def test_detail_after_only_returns_newer_messages(workshop):
    """X30：详情的 after 参数只返回 id 大于它的消息，轮询依赖这个语义。"""
    client, _ = workshop
    group = create_group(client, avatar=True)
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")
    ids = [message["id"] for message in data["messages"]]
    assert len(ids) >= 2 and ids == sorted(ids)

    after = ids[0]
    response = client.get(f"/discuss/groups/{group_id}",
                          params={"after": after}, headers=HEADERS)
    assert response.status_code == 200, response.text
    filtered = response.json()
    assert [message["id"] for message in filtered["messages"]] == [
        message_id for message_id in ids if message_id > after]
    assert all(message["id"] > after for message in filtered["messages"])
    assert filtered["id"] == group_id
    assert len(filtered["members"]) == len(data["members"])

    response = client.get(f"/discuss/groups/{group_id}",
                          params={"after": ids[-1]}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["messages"] == []


def test_start_rejects_when_other_group_is_running(workshop):
    """X31：同一用户已有别的 running 群时 POST start 返回 409，A 保持 awaiting_start。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")
    seed_other_group("running")

    response = client.post(f"/discuss/groups/{group_id}/start", json={
        "expected_revision": data["plan_revision"]}, headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "你有一个讨论群正在进行，等它停下来再建新的"
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["status"] == "awaiting_start"


def test_resume_rejects_when_other_group_is_running(workshop):
    """X32：同一用户已有别的 running 群时 POST resume 返回 409，A 保持 paused。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    seed_other_group("running")
    asyncio.run(discuss_store.update_group(
        USER, group_id, status="paused", stop_reason="user", round=1))

    response = client.post(f"/discuss/groups/{group_id}/resume",
                           json={}, headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "你有一个讨论群正在进行，等它停下来再建新的"
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["status"] == "paused"


def test_continue_rejects_when_other_group_is_running(workshop):
    """X33：同一用户已有别的 running 群时 POST continue 返回 409，A 保持 awaiting_user。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")
    seed_other_group("running")
    asyncio.run(discuss_store.update_group(
        USER, group_id, status="awaiting_user", stop_reason="rounds_exhausted", round=1))

    response = client.post(f"/discuss/groups/{group_id}/continue",
                           json={}, headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "你有一个讨论群正在进行，等它停下来再建新的"
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["status"] == "awaiting_user"


def test_group_list_is_capped_at_fifty(workshop):
    """X27：同一个用户有 51 个群时，GET /discuss/groups 最多返回 50 个。"""
    client, _ = workshop
    seed_many_groups(51)
    assert stored_group_count() == 51

    response = client.get("/discuss/groups", headers=HEADERS)
    assert response.status_code == 200, response.text
    listed = response.json()
    assert len(listed) == 50
    assert len({item["id"] for item in listed}) == 50


def test_patch_removing_member_clears_its_model(workshop):
    """X28：picks 删掉成员时，config.models 里该成员的设置同时清掉。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")
    revision = data["plan_revision"]

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": revision,
        "models": {
            "market": "ark:doubao-seed-2-1-pro-260915",
            "tech": "dashscope:qwen3.8-max",
        },
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    config = stored_group_row(group_id)["config"]
    assert config["models"]["market"] == "ark:doubao-seed-2-1-pro-260915"
    assert config["models"]["tech"] == "dashscope:qwen3.8-max"

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": revision + 1,
        "picks": [{"role": "tech", "focus": "继续查技术"}],
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    config = stored_group_row(group_id)["config"]
    assert "market" not in config["models"]
    assert config["models"]["tech"] == "dashscope:qwen3.8-max"
    assert [member["role"] for member in response.json()["members"]] == [
        "host", "tech", "critic", "writer", "acceptor"]


def test_patch_new_custom_member_skips_used_codes(workshop):
    """X39：新增无 role 的自定义成员时跳过已用代号，得到 custom3。"""
    client, fake = workshop
    custom_plan = dict(PLAN)
    custom_plan["picks"] = [
        {"role": "custom1", "focus": "查甲方向"},
        {"role": "custom2", "focus": "查乙方向"},
    ]
    set_script(fake, {**RESPONSES, "r00/01-plan-host": custom_plan})
    group = create_group(client, avatar=False, members=[
        {"name": "甲顾问", "does": "负责甲方向调研"},
        {"name": "乙顾问", "does": "负责乙方向调研"},
    ])
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")
    assert [pick["role"] for pick in data["plan"]["picks"]] == ["custom1", "custom2"]

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": data["plan_revision"],
        "picks": [
            {"role": "custom1", "focus": "继续查甲"},
            {"role": "custom2", "focus": "继续查乙"},
            {"name": "丙顾问", "does": "负责丙方向调研", "focus": "查丙"},
        ],
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert [pick["role"] for pick in updated["plan"]["picks"]] == [
        "custom1", "custom2", "custom3"]
    assert updated["plan"]["picks"][-1]["name"] == "丙顾问"
    assert [member["role"] for member in updated["members"]] == [
        "host", "custom1", "custom2", "custom3", "critic", "writer", "acceptor"]


def test_patch_identity_persona_over_300_is_422(workshop):
    """X44：身份设定 300 字可以保存，超过 300 字返回 422。"""
    client, _ = workshop
    group = create_group(client, avatar=False)
    group_id = group["id"]
    data = wait(client, group_id, "awaiting_start")

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": data["plan_revision"],
        "identities": {"host": {"persona": "长" * 300}},
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": data["plan_revision"],
        "identities": {"host": {"persona": "长" * 301}},
    }, headers=HEADERS)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "身份设定最多 300 字"
    after = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    assert after["plan_revision"] == data["plan_revision"]


# ── 复核第 2 轮：Y3 分身名字只取一次、Y6 带 role 的重名 ───────

def test_detail_calls_avatar_display_name_only_once(workshop, monkeypatch):
    """Y3：带分身的群取一次详情，avatar.display_name 恰好调用一次。"""
    client, _ = workshop
    group = create_group(client, avatar=True)
    group_id = group["id"]
    wait(client, group_id, "awaiting_start")

    from discuss import avatar
    calls = []
    real_display_name = avatar.display_name

    async def counted(username):
        calls.append(username)
        return await real_display_name(username)

    monkeypatch.setattr(avatar, "display_name", counted)
    response = client.get(f"/discuss/groups/{group_id}", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert len(calls) == 1


def test_create_group_rejects_duplicate_names_with_role_override(workshop):
    """Y6：带 role 的成员改名后与另一位成员重名，建群 422。"""
    client, _ = workshop
    response = client.post("/discuss/groups", json={
        "request": "帮我研究一下这个方向",
        "budget_strawberries": 500,
        "max_rounds": 2,
        "members": [
            {"role": "market", "name": "同一个名字"},
            {"role": "tech", "name": "同一个名字"},
        ],
    }, headers=HEADERS)
    assert response.status_code == 422, response.text
