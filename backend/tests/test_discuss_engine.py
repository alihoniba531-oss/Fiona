"""讨论群引擎、存储与服务层的离线流程测试（规格 4.6，场景 4–13、16、17、21–23）。

模型用 FakeLLM，搜索替换 ``discuss.research.search_once``，后台任务通过
``discuss.runner.router_factory`` 注入；每个用例各用一个临时 SQLite 库。
"""

import asyncio
import json

import aiosqlite
import pytest
from fastapi import HTTPException

import agent_store
import database
import persona
from discuss import avatar, engine, research, roles, runner
from discuss import service
from discuss import store as discuss_store
from discuss.runner import TASKS
from novel.byok_bridge import ByokUnavailable
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from safety import CRISIS_RESOURCE_NOTE, assess_crisis


USER = "discuss_author"
REQUEST = "帮我比较三款调研工具的价格、适用场景与上手成本"


# ---------------------------------------------------------------- 数据与脚本

def plan_payload(picks=("market", "competitor"), questions=()):
    return {
        "title": "调研工具选择",
        "goal": "比较三款调研工具的价格与适用场景，给出明确建议。",
        "deliverable": {"kind": "report", "outline": ["结论", "对比", "建议"]},
        "criteria": ["列出价格", "给出明确建议", "说明适用前提"],
        "picks": [{"role": role, "focus": f"查 {role} 方向"} for role in picks],
        "questions": list(questions),
    }


def note_payload(refs=("S1", "S2")):
    return {
        "note": f"市场增长 12% [{refs[0]}]，竞品定价差异明显 [{refs[-1]}]。",
        "key_points": [
            {"text": f"市场增长 12% [{refs[0]}]", "refs": [refs[0]]},
            {"text": f"竞品定价差异明显 [{refs[-1]}]", "refs": [refs[-1]]},
        ],
        "gaps": [],
    }


def critique_payload(target="market"):
    return {
        "objections": [{
            "target": target,
            "type": "missing",
            "problem": "缺少小团队样本",
            "suggestion": "补查小团队的使用反馈",
        }],
        "counter_view": "增长数据可能只覆盖大客户。",
    }


def decide_payload(*, decision="draft", assignments=None, brief="按三节写，明确适用前提。",
                   summary="开始撰稿。", note_responses=None):
    return {
        "responses": [{"id": "O1", "action": "accept", "reason": "先写"}],
        "note_responses": note_responses if note_responses is not None else [],
        "decision": decision,
        "assignments": assignments or [],
        "brief_for_writer": brief,
        "summary": summary,
    }


def accept_payload(*, passed=True, quote=None, rework=None):
    issues = []
    if quote:
        issues.append({"quote": quote, "problem": "缺少来源"})
    return {
        "verdicts": [
            {"id": "C1", "pass": True, "evidence": "价格表齐全"},
            {"id": "C2", "pass": passed, "evidence": "结论明确" if passed else "还缺建议"},
            {"id": "C3", "pass": True, "evidence": "前提已写"},
        ],
        "citation_issues": issues,
        "rework": list(rework or []),
    }


def rework_payload(*, assignments=None, brief="按返工要求改。"):
    return {
        "assignments": assignments or [],
        "note_responses": [],
        "brief_for_writer": brief,
        "summary": "安排返工。",
    }


def draft_text(extra=""):
    return "# 调研建议\n\n" + ("本报告建议先做小范围试点，再按结果扩大投入。依据见 [S1]。" * 20) + extra


DRAFT_SENTENCE = "本报告建议先做小范围试点"


def base_script():
    return {
        "plan": plan_payload(),
        "queries": {"queries": ["问题一", "问题二"]},
        "note": note_payload(),
        "critique": critique_payload(),
        "decide": decide_payload(),
        "draft": draft_text(),
        "accept": accept_payload(),
        "rework": rework_payload(),
        "brief": {"context": "主人偏务实，预算有限。", "answers": [], "ask_owner": []},
        "view": {"comment": "对主人有用，结论可以照着做。", "must_fix": []},
    }


def patch_search(monkeypatch, handler=None):
    """Standard two-source search; ``handler`` may return a custom result or None."""
    def search_once(query, context):
        if handler is not None:
            custom = handler(query, context)
            if custom is not None:
                return custom
        index = 1 if query == "问题一" else 2
        return {
            "query": query,
            "data": {"findings": [{"fact": f"事实{index}", "refs": [1]}]},
            "sources": [{"title": f"来源{index}", "url": f"https://example.com/{index}",
                         "site_name": f"站点{index}", "index": 1}],
            "error": None,
        }
    monkeypatch.setattr(research, "search_once", search_once)


def empty_search(query, context):
    return {"query": query, "data": None, "sources": [], "error": None}


def install_fake(monkeypatch, fake):
    def factory(store, username, group_id, run_token):
        router = LLMRouter(store, fake=fake, dry_run=True)
        router.retry_delay = 0
        return router
    monkeypatch.setattr(runner, "router_factory", factory)


async def setup_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "discuss-engine.db"))
    await database.init_db()
    await database.get_or_create_user(USER)
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("UPDATE users SET strawberry_balance=1000 WHERE username=?", (USER,))
        await db.commit()


async def drain(group_id):
    task = TASKS.get(group_id)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 15)


async def create_planned(monkeypatch, tmp_path, fake, *, max_rounds=3, avatar=False,
                         members=None, identities=None, request=REQUEST,
                         search_handler=None):
    await setup_db(monkeypatch, tmp_path)
    install_fake(monkeypatch, fake)
    patch_search(monkeypatch, search_handler)
    summary = await service.create_group(USER, service.CreateGroup(
        request=request, max_rounds=max_rounds, avatar=avatar,
        members=members, identities=identities))
    group_id = summary["id"]
    await drain(group_id)
    return group_id


async def start_and_drain(group_id):
    detail = await service.detail(USER, group_id)
    await service.start(USER, group_id, service.StartGroup(
        expected_revision=detail["plan_revision"]))
    await drain(group_id)
    return await service.detail(USER, group_id)


async def create_and_run(monkeypatch, tmp_path, fake, **kwargs):
    group_id = await create_planned(monkeypatch, tmp_path, fake, **kwargs)
    detail = await start_and_drain(group_id)
    return group_id, detail


async def group_row(group_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM discuss_groups WHERE id=?", (group_id,))).fetchone()
    return dict(row)


async def step_rows(group_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(row) for row in await (await db.execute(
            "SELECT * FROM discuss_steps WHERE group_id=? ORDER BY step_key",
            (group_id,))).fetchall()]


async def message_rows(group_id):
    return await discuss_store.list_messages(USER, group_id)


def calls_for(fake, step_key):
    return [call for call in fake.calls if call.get("step_key") == step_key]


def user_payload(call):
    return FakeLLM.payload(call)


def system_of(call):
    return call["messages"][0]["content"]


# ---------------------------------------------------------------- 场景 4

def test_one_round_pass(monkeypatch, tmp_path):
    """场景 4：一轮通过：note→critique→decision→draft→verdict，done/accepted。"""
    async def scenario():
        fake = FakeLLM(base_script())
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        assert (detail["round"], detail["output_version"]) == (1, 1)
        assert detail["output"]["passed"] is True and detail["output"]["version"] == 1

        messages = await message_rows(group_id)
        assert messages[0]["kind"] == "plan" and messages[0]["sender"] == "host"
        round_one = [message["kind"] for message in messages if message["round"] == 1]
        assert round_one == ["note", "note", "critique", "decision", "draft", "verdict"]
        assert [message["sender"] for message in messages if message["kind"] == "note"] == [
            "market", "competitor"]
        assert messages[-1]["payload"]["passed"] is True

        steps = await step_rows(group_id)
        assert steps and all(step["status"] == "ok" for step in steps)
        output = await service.output(USER, group_id)
        assert output["version"] == 1 and output["passed"] is True
        assert output["verdict"]["citation_issues"] == []
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 5

def test_failed_accept_goes_to_rework_then_passes(monkeypatch, tmp_path):
    """场景 5：首轮验收不过出现 rework，第二轮通过；两版成果。"""
    async def scenario():
        script = base_script()
        script["accept"] = [
            accept_payload(quote=DRAFT_SENTENCE),
            accept_payload(),
        ]
        script["rework"] = rework_payload(assignments=[])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        assert detail["round"] == 2 and detail["output_version"] == 2

        first = await discuss_store.get_output(USER, group_id, 1)
        second = await discuss_store.get_output(USER, group_id, 2)
        assert first["passed"] == 0 and second["passed"] == 1
        assert first["verdict"]["citation_issues"][0]["quote"] == DRAFT_SENTENCE
        assert second["verdict"]["citation_issues"] == []

        kinds = [message["kind"] for message in await message_rows(group_id)]
        assert kinds.count("rework") == 1 and kinds.count("verdict") == 2
        assert kinds.count("draft") == 2
        assert kinds.index("verdict") < kinds.index("rework")
        rework = next(message for message in await message_rows(group_id)
                      if message["kind"] == "rework")
        assert rework["payload"]["brief_for_writer"]
    asyncio.run(scenario())


def test_accept_drops_non_verbatim_citation_quote(monkeypatch, tmp_path):
    """场景 5（4.6.2）：quote 不是成果逐字片段时丢弃，不阻断通过。"""
    async def scenario():
        script = base_script()
        script["accept"] = accept_payload(quote="成果里没有出现过的句子")
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        output = await discuss_store.get_output(USER, group_id, 1)
        assert output["passed"] == 1
        assert output["verdict"]["citation_issues"] == []
        verdict = next(message for message in await message_rows(group_id)
                       if message["kind"] == "verdict")
        assert verdict["payload"]["passed"] is True
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 6

def test_rounds_exhausted_then_continue_adds_a_round(monkeypatch, tmp_path):
    """场景 6：max_rounds=1 不过→awaiting_user；continue 后再跑一轮。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        fake = FakeLLM(script)
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=1)
        detail = await start_and_drain(group_id)
        assert (detail["status"], detail["stop_reason"]) == ("awaiting_user", "rounds_exhausted")
        assert detail["round"] == 1 and detail["output_version"] == 1

        continued = await service.continue_group(
            USER, group_id, service.ContinueGroup(add_rounds=1))
        assert continued["max_rounds"] == 2
        await drain(group_id)
        detail = await service.detail(USER, group_id)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        assert detail["round"] == 2 and detail["output_version"] == 2
        first = await discuss_store.get_output(USER, group_id, 1)
        second = await discuss_store.get_output(USER, group_id, 2)
        assert (first["passed"], second["passed"]) == (0, 1)

        # 总轮数超过 10 时 continue 必须 422。
        await discuss_store.update_group(
            USER, group_id, status="awaiting_user", max_rounds=9)
        with pytest.raises(HTTPException) as error:
            await service.continue_group(
                USER, group_id, service.ContinueGroup(add_rounds=2))
        assert error.value.status_code == 422
        assert int((await group_row(group_id))["max_rounds"]) == 9
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 7

def test_research_limit_is_enforced_by_payload_and_validation(monkeypatch, tmp_path):
    """场景 7：第二轮 can_research_more=false，模型仍 research 时校验失败回灌。"""
    async def scenario():
        script = base_script()
        script["decide"] = [
            decide_payload(decision="research",
                           assignments=[{"role": "competitor", "task": "补查定价"}]),
            decide_payload(decision="research",
                           assignments=[{"role": "competitor", "task": "再补查"}]),
            decide_payload(),
        ]
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=3)
        assert detail["status"] == "done" and detail["round"] == 2

        decide_calls = [call for call in fake.calls
                        if call.get("step_key", "").endswith("30-decide-host")]
        assert len(decide_calls) == 3
        assert user_payload(decide_calls[0])["can_research_more"] is True
        assert user_payload(decide_calls[1])["can_research_more"] is False
        repair = decide_calls[2]["messages"][-1]["content"]
        assert "校验错误" in repair and "can_research_more" in repair
        assert "decision" in repair

        steps = {step["step_key"]: step for step in await step_rows(group_id)}
        assert steps["r02/30-decide-host"]["attempts"] == 2
        assert steps["r02/30-decide-host"]["status"] == "ok"

        all_messages = await message_rows(group_id)
        round_one = [message["kind"] for message in all_messages if message["round"] == 1]
        assert round_one == ["note", "note", "critique", "decision"]
        first_decision = next(message for message in all_messages
                              if message["round"] == 1 and message["kind"] == "decision")
        assert first_decision["payload"]["decision"] == "research"
        round_two = [message["kind"] for message in all_messages if message["round"] == 2]
        assert round_two[:3] == ["note", "critique", "decision"]
        assert "draft" in round_two and round_two[-1] == "verdict"
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 8

def test_rework_accepts_chinese_role_name(monkeypatch, tmp_path):
    """场景 8：返工安排写中文名「竞品与对标」被归一成 competitor 并派发。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[
            {"role": "竞品与对标", "task": "补查定价与套餐"}])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert detail["status"] == "done" and detail["round"] == 2

        rework = next(message for message in await message_rows(group_id)
                      if message["kind"] == "rework")
        assert rework["payload"]["assignments"][0]["role"] == "competitor"
        assert "竞品与对标" in rework["content"]

        step_keys = {step["step_key"] for step in await step_rows(group_id)}
        assert "r02/10-queries-competitor" in step_keys
        assert "r02/10-queries-market" not in step_keys
        query_call = calls_for(fake, "r02/10-queries-competitor")[0]
        assert query_call["role"] == "competitor"
        assert user_payload(query_call)["assignment"] == "补查定价与套餐"
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 9

def test_sources_dedup_invalid_refs_http_and_export(monkeypatch, tmp_path):
    """场景 9：同网址合并编号；非法引用与网址被回灌；导出只列引用来源。"""
    urls = {
        "问题一": "https://Example.com/a/#part",
        "问题二": "https://example.com/a/",
        "问题三": "https://example.com/b",
    }

    def handler(query, context):
        if query not in urls:
            return None
        return {
            "query": query,
            "data": {"findings": [{"fact": f"{query} 的事实", "refs": [1]}]},
            "sources": [{"title": f"{query}来源", "url": urls[query],
                         "site_name": "站点", "index": 1}],
            "error": None,
        }

    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("market",))
        script["queries"] = {"queries": ["问题一", "问题二", "问题三"]}
        bad_note = note_payload()
        bad_note["note"] = "引用了没有登记的 [S9]。"
        script["note"] = [bad_note, note_payload()]
        script["draft"] = [
            draft_text("详见 https://example.com/private"),
            draft_text(),
        ]
        fake = FakeLLM(script)
        group_id = await create_planned(
            monkeypatch, tmp_path, fake, max_rounds=2,
            members=[{"role": "market"}], search_handler=handler)
        detail = await start_and_drain(group_id)
        assert detail["status"] == "done"

        sources = await service.sources(USER, group_id)
        assert [source["id"] for source in sources] == ["S1", "S2"]
        assert sources[0]["url"] == urls["问题一"]
        assert sources[1]["url"] == urls["问题三"]

        note_calls = calls_for(fake, "r01/13-note-market")
        assert len(note_calls) == 2
        assert "校验错误" in note_calls[1]["messages"][-1]["content"]
        assert "来源登记表里没有的编号" in note_calls[1]["messages"][-1]["content"]
        facts = user_payload(note_calls[0])["findings"]
        assert len(facts) == 3
        assert [fact["refs"] for fact in facts][:2] == [["S1"], ["S1"]]
        assert facts[2]["refs"] == ["S2"]

        draft_calls = calls_for(fake, "r01/40-draft-writer")
        assert len(draft_calls) == 2
        assert "不能包含网址" in draft_calls[1]["messages"][-1]["content"]
        assert [source["id"] for source in user_payload(draft_calls[0])["sources"]] == ["S1", "S2"]

        body, filename = await service.export(USER, group_id)
        assert filename == "调研工具选择.md"
        assert "## 来源" in body
        assert "- S1 " in body and urls["问题一"] in body
        assert "- S2 " not in body and urls["问题三"] not in body
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 10

def test_running_note_reaches_decide_and_is_consumed(monkeypatch, tmp_path):
    """场景 10：运行中插话进入 decide 载荷，note_responses 回应，consumed_by 落步骤键。"""
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        inner = FakeLLM({
            **base_script(),
            "decide": decide_payload(note_responses=[
                {"id": "N1", "reply": "已经让撰稿人补一段小团队样本。"}]),
        })

        async def gated(request, index):
            if request.get("task") == "critique":
                started.set()
                await release.wait()
            return await inner(request)

        fake = FakeLLM(gated)
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=2,
                                        avatar=False)
        detail = await service.detail(USER, group_id)
        await service.start(USER, group_id, service.StartGroup(
            expected_revision=detail["plan_revision"]))
        await asyncio.wait_for(started.wait(), 10)
        note = await service.add_note(
            USER, group_id, service.NoteIn(text="请补充小团队样本"))
        assert note["sender"] == "user" and note["consumed"] is False
        release.set()
        await drain(group_id)

        decide_call = calls_for(fake, "r01/30-decide-host")[0]
        assert user_payload(decide_call)["user_notes"] == [
            {"id": "N1", "text": "请补充小团队样本"}]
        messages = await message_rows(group_id)
        trigger = next(message for message in messages if message["id"] == note["id"])
        assert trigger["consumed_by"] == "r01/30-decide-host"
        decision = next(message for message in messages if message["kind"] == "decision")
        assert decision["payload"]["note_responses"] == [
            {"id": "N1", "reply": "已经让撰稿人补一段小团队样本。"}]
        assert "已经让撰稿人补一段小团队样本" in decision["content"]
        detail = await service.detail(USER, group_id)
        assert detail["pending_notes"] == 0
    asyncio.run(scenario())


def test_five_unread_notes_and_crisis_note(monkeypatch, tmp_path):
    """场景 10：未读 5 条后再插 409；明确危机插话 400 且不落库。"""
    async def scenario():
        fake = FakeLLM(base_script())
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=2)
        for index in range(5):
            await service.add_note(USER, group_id, service.NoteIn(text=f"第 {index} 条意见"))
        with pytest.raises(HTTPException) as error:
            await service.add_note(USER, group_id, service.NoteIn(text="第六条意见"))
        assert error.value.status_code == 409
        assert "还有 5 条插话没被读到" in error.value.detail
        with pytest.raises(ValueError) as store_error:
            await discuss_store.post_user_note(USER, group_id, "第六条意见", 0)
        assert str(store_error.value) == "too_many"

        before = len(await message_rows(group_id))
        crisis = "我不想活了"
        assert assess_crisis(crisis) == "high"
        with pytest.raises(HTTPException) as crisis_error:
            await service.add_note(USER, group_id, service.NoteIn(text=crisis))
        assert crisis_error.value.status_code == 400
        assert crisis_error.value.detail == CRISIS_RESOURCE_NOTE
        messages = await message_rows(group_id)
        assert len(messages) == before
        assert all(crisis not in message["content"] for message in messages)
    asyncio.run(scenario())


def test_pre_start_notes_enter_owner_notes(monkeypatch, tmp_path):
    """场景 10：开工前插话与作者回答进入第一轮 queries 的 owner_notes。"""
    async def scenario():
        fake = FakeLLM(base_script())
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=2)
        detail = await service.detail(USER, group_id)
        await service.update_plan(USER, group_id, service.UpdatePlan(
            expected_revision=detail["plan_revision"], answers="作者的补充回答"))
        await service.add_note(USER, group_id, service.NoteIn(text="开工前的补充"))
        await start_and_drain(group_id)

        query_calls = [call for call in fake.calls
                       if call.get("step_key", "").startswith("r01/10-queries-")]
        assert query_calls
        for call in query_calls:
            assert user_payload(call)["owner_notes"] == "开工前的补充\n作者的补充回答"
        detail = await service.detail(USER, group_id)
        assert detail["pending_notes"] == 0
        consumed = [message for message in detail["messages"] if message["sender"] == "user"]
        assert consumed[0]["consumed"] is True
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 11

async def prepare_avatar():
    await agent_store.update_my_agent(USER, {
        "display_name": "阿灯", "bio": "主人的谨慎顾问", "personality": "先列前提再下结论"})
    await agent_store.update_memory(USER, {
        "偏好": "喜欢对比表格", "memory_marker": "PRIVATE_MEMORY_MARKER_9"})


def test_avatar_brief_and_view_prompts(monkeypatch, tmp_path):
    """场景 11：avatar 两步存在；系统提示含私有记忆与基础规则、不含账号名。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        await prepare_avatar()
        fake = FakeLLM(base_script())
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=True)
        assert detail["status"] == "done"
        messages = await message_rows(group_id)
        kinds = [message["kind"] for message in messages]
        assert kinds.count("brief") == 1 and kinds.count("view") == 1

        for task in ("brief", "view"):
            calls = [call for call in fake.calls if call.get("task") == task]
            assert len(calls) == 1
            system = calls[0]["messages"][0]["content"]
            assert json.dumps({"偏好": "喜欢对比表格",
                               "memory_marker": "PRIVATE_MEMORY_MARKER_9"},
                              ensure_ascii=False) in system
            assert persona.BASE_SAFETY_RULES in system
            assert "阿灯" in system
            assert USER not in system
            assert "不能改变" not in system
    asyncio.run(scenario())


def test_avatar_false_has_no_avatar_steps(monkeypatch, tmp_path):
    """场景 11：avatar=false 时没有 brief/view 步骤与消息。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        await prepare_avatar()
        fake = FakeLLM(base_script())
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=False)
        assert detail["status"] == "done"
        kinds = [message["kind"] for message in await message_rows(group_id)]
        assert "brief" not in kinds and "view" not in kinds
        assert not [call for call in fake.calls if call.get("task") in ("brief", "view")]
        step_keys = {step["step_key"] for step in await step_rows(group_id)}
        assert not any("avatar" in key for key in step_keys)
    asyncio.run(scenario())


def test_avatar_failure_becomes_notice_and_flow_continues(monkeypatch, tmp_path):
    """场景 11：分身步骤普通异常→notice「分身这次没能发言」，流程照常完成。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        await prepare_avatar()
        script = base_script()
        script["brief"] = RuntimeError("avatar failed")
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=True)
        assert detail["status"] == "done" and detail["stop_reason"] == "accepted"
        messages = await message_rows(group_id)
        notices = [message for message in messages
                   if message["kind"] == "notice" and message["sender"] == "avatar"]
        assert len(notices) == 1
        assert notices[0]["content"] == "分身这次没能发言"
        assert notices[0]["step_key"] == "r00/02-brief-avatar-skip"
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 13

def test_pause_and_resume_do_not_repeat_completed_steps(monkeypatch, tmp_path):
    """场景 13：运行中暂停→paused/user、令牌空、reserved=0；继续不重跑已完成步骤。"""
    async def scenario():
        inner = FakeLLM(base_script())

        async def slow(request, index):
            await asyncio.sleep(0.02)
            return await inner(request)

        fake = FakeLLM(slow)
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=2)

        async def pause_later():
            while fake.call_count < 2:
                await asyncio.sleep(0.001)
            await service.pause(USER, group_id)

        pauser = asyncio.create_task(pause_later())
        detail = await service.detail(USER, group_id)
        await service.start(USER, group_id, service.StartGroup(
            expected_revision=detail["plan_revision"]))
        await asyncio.wait_for(pauser, 10)
        await drain(group_id)

        detail = await service.detail(USER, group_id)
        assert (detail["status"], detail["stop_reason"]) == ("paused", "user")
        row = await group_row(group_id)
        assert row["run_token"] is None and row["reserved_strawberries"] == 0

        ok_before = {step["step_key"] for step in await step_rows(group_id)
                     if step["status"] == "ok"}
        message_ids_before = {message["id"] for message in await message_rows(group_id)}
        calls_before = len(fake.calls)

        await service.resume(USER, group_id, service.ResumeGroup())
        await drain(group_id)
        detail = await service.detail(USER, group_id)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        new_calls = fake.calls[calls_before:]
        assert new_calls
        assert not [call for call in new_calls if call.get("step_key") in ok_before]
        messages = await message_rows(group_id)
        assert message_ids_before <= {message["id"] for message in messages}
        step_keys = [message["step_key"] for message in messages if message["step_key"]]
        assert len(step_keys) == len(set(step_keys))
        assert len(messages) == len({message["id"] for message in messages})
        row = await group_row(group_id)
        assert row["run_token"] is None and row["reserved_strawberries"] == 0
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 16

def test_all_roles_without_facts_pauses_search_unavailable(monkeypatch, tmp_path):
    """场景 16：第一轮所有角色无事实→paused/search_unavailable。"""
    async def scenario():
        fake = FakeLLM(base_script())
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=2,
                                        search_handler=empty_search)
        await start_and_drain(group_id)
        detail = await service.detail(USER, group_id)
        assert (detail["status"], detail["stop_reason"]) == ("paused", "search_unavailable")
        row = await group_row(group_id)
        assert row["run_token"] is None and row["reserved_strawberries"] == 0
        messages = await message_rows(group_id)
        notices = [message for message in messages if message["kind"] == "notice"]
        assert {message["sender"] for message in notices} == {"market", "competitor"}
        assert not [message for message in messages if message["kind"] == "note"]
        steps = await step_rows(group_id)
        assert not [step for step in steps if step["step_key"].startswith("r01/13-note-")]
        assert all(step["status"] == "failed" for step in steps if step["model"] == "search")
    asyncio.run(scenario())


def test_partial_roles_without_facts_post_notice_and_finish(monkeypatch, tmp_path):
    """场景 16：只有部分角色无事实时该角色 notice，其余照常，流程完成。"""
    async def scenario():
        script = base_script()
        script["r01/10-queries-competitor"] = {"queries": ["空问题"]}

        def handler(query, context):
            return empty_search(query, context) if query == "空问题" else None

        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, search_handler=handler)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        messages = await message_rows(group_id)
        notices = [message for message in messages if message["kind"] == "notice"]
        assert len(notices) == 1 and notices[0]["sender"] == "competitor"
        assert "空问题" in notices[0]["content"]
        notes = [message for message in messages if message["kind"] == "note"]
        assert [message["sender"] for message in notes] == ["market"]
        step_keys = {step["step_key"] for step in await step_rows(group_id)}
        assert notices[0]["step_key"] == "r01/14-empty-competitor"
        assert "r01/13-note-competitor" not in step_keys
        assert "r01/13-note-market" in step_keys
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 17

def test_long_brief_is_truncated_not_failed(monkeypatch, tmp_path):
    """场景 17：主持人 brief_for_writer 3000 字→步骤成功，落库与下发截到 1200。"""
    async def scenario():
        script = base_script()
        script["decide"] = [decide_payload(brief="甲" * 3000)]
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[], brief="乙" * 3000)
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        messages = await message_rows(group_id)
        decision = next(message for message in messages if message["kind"] == "decision")
        assert len(decision["payload"]["brief_for_writer"]) == 1200
        rework = next(message for message in messages if message["kind"] == "rework")
        assert len(rework["payload"]["brief_for_writer"]) == 1200

        draft_calls = [call for call in fake.calls if call.get("task") == "draft"]
        assert len(draft_calls) == 2
        assert len(user_payload(draft_calls[0])["brief"]) == 1200
        assert len(user_payload(draft_calls[1])["brief"]) == 1200
        assert all(call.get("step_key") for call in draft_calls)

        steps = {step["step_key"]: step for step in await step_rows(group_id)}
        decision_result = json.loads(steps["r01/30-decide-host"]["result_json"])
        rework_result = json.loads(steps["r01/60-rework-host"]["result_json"])
        assert len(decision_result["brief_for_writer"]) == 1200
        assert len(rework_result["brief_for_writer"]) == 1200
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 21

MEMBER_ONE = {"role": "market", "name": "行业观察", "does": "作者写的行业职责"}
MEMBER_TWO = {"name": "小探", "does": "作者写的自定义职责"}


def test_author_roster_planning_and_custom_member(monkeypatch, tmp_path):
    """场景 21：作者组队进立项载荷；picks 多/少校验回灌；custom1 调研。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        install_fake(monkeypatch, FakeLLM(base_script()))
        patch_search(monkeypatch)

        async def noop_start(*args, **kwargs):
            return None
        real_start = runner.start_group
        monkeypatch.setattr(runner, "start_group", noop_start)
        summary = await service.create_group(USER, service.CreateGroup(
            request=REQUEST, max_rounds=2, avatar=False,
            members=[MEMBER_ONE, MEMBER_TWO]))
        group_id = summary["id"]
        group = await discuss_store.get_group(USER, group_id)
        assert group["config"]["fixed_members"] == [
            {"role": "market", "name": "行业观察", "does": "作者写的行业职责"},
            {"role": "custom1", "name": "小探", "does": "作者写的自定义职责"},
        ]

        script = base_script()
        script["plan"] = plan_payload(picks=("custom1", "market"))
        fake = FakeLLM(script)
        install_fake(monkeypatch, fake)
        patch_search(monkeypatch)
        monkeypatch.setattr(runner, "start_group", real_start)
        await runner.start_group(group_id, USER)
        await drain(group_id)

        plan_calls = calls_for(fake, "r00/01-plan-host")
        assert len(plan_calls) == 1
        payload = user_payload(plan_calls[0])
        assert payload["fixed_members"] == [
            {"role": "market", "name": "行业观察", "does": "作者写的行业职责"},
            {"role": "custom1", "name": "小探", "does": "作者写的自定义职责"},
        ]
        assert payload["role_pool"] == payload["fixed_members"]

        detail = await service.detail(USER, group_id)
        assert [pick["role"] for pick in detail["plan"]["picks"]] == ["market", "custom1"]
        assert detail["plan"]["picks"][1]["name"] == "小探"
        assert detail["plan"]["picks"][1]["does"] == "作者写的自定义职责"

        detail = await start_and_drain(group_id)
        assert detail["status"] == "done"
        query_call = calls_for(fake, "r01/10-queries-custom1")[0]
        system = query_call["messages"][0]["content"]
        assert "小探" in system and "作者写的自定义职责" in system
        messages = await message_rows(group_id)
        assert any(message["sender"] == "custom1" for message in messages)
        member = next(item for item in detail["members"] if item["role"] == "custom1")
        assert (member["kind"], member["name"], member["does"]) == (
            "custom", "小探", "作者写的自定义职责")
        rendered = next(message for message in detail["messages"]
                        if message["sender"] == "custom1")
        assert rendered["sender_name"] == "小探"
    asyncio.run(scenario())


@pytest.mark.parametrize("picks", [
    ("market", "custom1", "competitor"),
    ("market",),
])
def test_roster_pick_count_mismatch_is_repaired(monkeypatch, tmp_path, picks):
    """场景 21：主持人 picks 多出或少了成员时校验失败并回灌，第二次正确后成功。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        patch_search(monkeypatch)

        async def noop_start(*args, **kwargs):
            return None
        real_start = runner.start_group
        monkeypatch.setattr(runner, "start_group", noop_start)
        summary = await service.create_group(USER, service.CreateGroup(
            request=REQUEST, max_rounds=2, avatar=False,
            members=[MEMBER_ONE, MEMBER_TWO]))
        group_id = summary["id"]

        script = base_script()
        script["plan"] = [plan_payload(picks=picks),
                          plan_payload(picks=("market", "custom1"))]
        fake = FakeLLM(script)
        install_fake(monkeypatch, fake)
        monkeypatch.setattr(runner, "start_group", real_start)
        await runner.start_group(group_id, USER)
        await drain(group_id)

        plan_calls = calls_for(fake, "r00/01-plan-host")
        assert len(plan_calls) == 2
        assert "校验错误" in plan_calls[1]["messages"][-1]["content"]
        assert "不增不减" in plan_calls[1]["messages"][-1]["content"]
        detail = await service.detail(USER, group_id)
        assert detail["status"] == "awaiting_start"
        assert [pick["role"] for pick in detail["plan"]["picks"]] == ["market", "custom1"]
    asyncio.run(scenario())


@pytest.mark.parametrize("members", [
    [],
    [{"role": "market"}] * 6,
    [{"role": "nope"}],
    [{"role": "market"}, {"role": "market"}],
    [{"name": "缺职责"}],
    [{"does": "缺名字"}],
    [{"name": "名" * 13, "does": "职责"}],
    [{"name": "名字", "does": "职" * 201}],
])
def test_invalid_author_roster_is_422(monkeypatch, tmp_path, members):
    """场景 21：members 数量、代号、重复、自定义名字/职责超限各 422。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)

        async def noop_start(*args, **kwargs):
            return None
        monkeypatch.setattr(runner, "start_group", noop_start)
        with pytest.raises(HTTPException) as error:
            await service.create_group(USER, service.CreateGroup(
                request=REQUEST, max_rounds=2, avatar=False, members=members))
        assert error.value.status_code == 422
        assert await discuss_store.list_groups(USER) == []
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 22

def test_host_identity_line_and_plan_edits(monkeypatch, tmp_path):
    """场景 22：主持人身份设定进入每步提示且 sender_name 用新名字；改方案增删成员。"""
    async def scenario():
        host_persona = "谨慎追问，先问清预算"
        writer_persona = "写法务实，先给结论"
        script = base_script()
        script["critique"] = critique_payload(target="competitor")
        script["accept"] = [accept_payload(passed=False, quote=DRAFT_SENTENCE),
                            accept_payload()]
        fake = FakeLLM(script)
        group_id = await create_planned(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=False,
            identities={"host": {"name": "老陈", "persona": host_persona},
                        "writer": {"persona": writer_persona}})
        detail = await service.detail(USER, group_id)
        plan_call = calls_for(fake, "r00/01-plan-host")[0]
        assert system_of(plan_call) == (
            roles.prompt("plan") + "\n" + roles.identity_line(host_persona)
            + roles.RULES + roles.JSON_RULE)
        plan_message = next(message for message in detail["messages"] if message["kind"] == "plan")
        assert plan_message["sender"] == "host" and plan_message["sender_name"] == "老陈"

        with pytest.raises(HTTPException) as error:
            await service.update_plan(USER, group_id, service.UpdatePlan(
                expected_revision=detail["plan_revision"],
                identities={"writer2": {"name": "非法", "persona": "x"}}))
        assert error.value.status_code == 422

        updated = await service.update_plan(USER, group_id, service.UpdatePlan(
            expected_revision=detail["plan_revision"],
            picks=[
                {"role": "competitor", "focus": "继续查竞品定价"},
                {"name": "新增成员", "does": "作者新写的研究职责", "focus": "查渠道"},
            ]))
        assert [pick["role"] for pick in updated["plan"]["picks"]] == [
            "competitor", "custom1"]
        assert updated["plan_revision"] == detail["plan_revision"] + 1

        detail = await start_and_drain(group_id)
        assert detail["status"] == "done" and detail["round"] == 2
        host_json_system = roles.RULES + roles.JSON_RULE
        decide_call = calls_for(fake, "r01/30-decide-host")[0]
        assert system_of(decide_call) == (
            roles.prompt("decide") + "\n" + roles.identity_line(host_persona)
            + host_json_system)
        rework_call = calls_for(fake, "r01/60-rework-host")[0]
        assert system_of(rework_call) == (
            roles.prompt("rework") + "\n" + roles.identity_line(host_persona)
            + host_json_system)
        draft_calls = (calls_for(fake, "r01/40-draft-writer")
                       + calls_for(fake, "r02/40-draft-writer"))
        assert len(draft_calls) == 2
        expected_draft_system = (
            roles.prompt("draft") + "\n" + roles.identity_line(writer_persona)
            + roles.RULES)
        for call in draft_calls:
            assert system_of(call) == expected_draft_system
        host_messages = [message for message in detail["messages"] if message["sender"] == "host"]
        assert host_messages and all(message["sender_name"] == "老陈" for message in host_messages)

        step_keys = {step["step_key"] for step in await step_rows(group_id)}
        assert "r01/10-queries-custom1" in step_keys
        assert "r01/13-note-custom1" in step_keys
        assert not [key for key in step_keys if "market" in key]
        custom = next(message for message in detail["messages"]
                      if message["sender"] == "custom1")
        assert custom["sender_name"] == "新增成员"
    asyncio.run(scenario())


def test_empty_persona_removes_identity_line(monkeypatch, tmp_path):
    """场景 22：把身份设定改成空字符串后，后续提示里不再出现那一行。"""
    async def scenario():
        persona_text = "谨慎追问"
        fake = FakeLLM(base_script())
        group_id = await create_planned(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=False,
            identities={"host": {"name": "老陈", "persona": persona_text}})
        plan_call = calls_for(fake, "r00/01-plan-host")[0]
        assert system_of(plan_call) == (
            roles.prompt("plan") + "\n" + roles.identity_line(persona_text)
            + roles.RULES + roles.JSON_RULE)

        detail = await service.detail(USER, group_id)
        updated = await service.update_plan(USER, group_id, service.UpdatePlan(
            expected_revision=detail["plan_revision"],
            identities={"host": {"persona": ""}}))
        assert updated["plan_revision"] == detail["plan_revision"] + 1
        group = await discuss_store.get_group(USER, group_id)
        assert group["config"]["identities"]["host"]["persona"] == ""

        detail = await start_and_drain(group_id)
        assert detail["status"] == "done"
        decide_call = calls_for(fake, "r01/30-decide-host")[0]
        assert system_of(decide_call) == (
            roles.prompt("decide") + roles.RULES + roles.JSON_RULE)
        draft_call = calls_for(fake, "r01/40-draft-writer")[0]
        assert system_of(draft_call) == roles.prompt("draft") + roles.RULES
    asyncio.run(scenario())


# ---------------------------------------------------------------- 场景 23

def test_rework_accepts_custom_member_name(monkeypatch, tmp_path):
    """场景 23：返工安排用自定义成员名字派任务，归一成 customN 并派发。"""
    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("custom1",))
        script["critique"] = critique_payload(target="custom1")
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[
            {"role": "小探", "task": "补查渠道成本"}])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2,
            members=[{"name": "小探", "does": "作者写的自定义职责"}])
        assert detail["status"] == "done" and detail["round"] == 2
        rework = next(message for message in await message_rows(group_id)
                      if message["kind"] == "rework")
        assert rework["payload"]["assignments"][0]["role"] == "custom1"
        step_keys = {step["step_key"] for step in await step_rows(group_id)}
        assert "r02/10-queries-custom1" in step_keys
        call = calls_for(fake, "r02/10-queries-custom1")[0]
        assert call["role"] == "custom1"
        assert user_payload(call)["assignment"] == "补查渠道成本"
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 P1

def test_p1_rework_merges_tasks_for_same_member(monkeypatch, tmp_path):
    """P1：返工安排给同一成员两条任务→下一轮只调研一次，任务用「；」合并。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[
            {"role": "market", "task": "补查小团队样本"},
            {"role": "market", "task": "补查定价区间"},
        ])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        assert detail["round"] == 2

        query_calls = calls_for(fake, "r02/10-queries-market")
        assert len(query_calls) == 1
        assert user_payload(query_calls[0])["assignment"] == "补查小团队样本；补查定价区间"

        steps = await step_rows(group_id)
        search_keys = [step["step_key"] for step in steps
                       if step["step_key"].startswith("r02/11-search-market-")]
        assert search_keys == ["r02/11-search-market-1", "r02/11-search-market-2"]
        query_step = next(step for step in steps if step["step_key"] == "r02/10-queries-market")
        assert len(json.loads(query_step["result_json"])["queries"]) == len(search_keys)
        note_call = calls_for(fake, "r02/13-note-market")[0]
        assert len(user_payload(note_call)["findings"]) == 2
        assert "r02/10-queries-competitor" not in {step["step_key"] for step in steps}
    asyncio.run(scenario())


def test_p1_research_decision_merges_tasks_for_same_member(monkeypatch, tmp_path):
    """P1：裁决为 research 时同一成员两条任务→下一轮只调研一次并合并任务。"""
    async def scenario():
        script = base_script()
        script["decide"] = [
            decide_payload(decision="research", assignments=[
                {"role": "market", "task": "补查小团队样本"},
                {"role": "market", "task": "补查定价区间"},
            ], summary="再查一轮。"),
            decide_payload(),
        ]
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=3)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        assert detail["round"] == 2

        query_calls = calls_for(fake, "r02/10-queries-market")
        assert len(query_calls) == 1
        assert user_payload(query_calls[0])["assignment"] == "补查小团队样本；补查定价区间"

        steps = await step_rows(group_id)
        search_keys = [step["step_key"] for step in steps
                       if step["step_key"].startswith("r02/11-search-market-")]
        assert search_keys == ["r02/11-search-market-1", "r02/11-search-market-2"]
        note_call = calls_for(fake, "r02/13-note-market")[0]
        assert len(user_payload(note_call)["findings"]) == 2
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 P2

def test_p2_replay_never_rewinds_round(monkeypatch, tmp_path):
    """P2：群已到第 2 轮时重放，update_group 收到的 round 不小于 2。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload(passed=False),
                            accept_payload()]
        fake = FakeLLM(script)
        group_id = await create_planned(monkeypatch, tmp_path, fake, max_rounds=3)
        token = "replay-token"
        await discuss_store.update_group(
            USER, group_id, status="running", round=2, run_token=token)

        store = discuss_store.DiscussStepStore(USER, group_id, token)
        await store.initialize()
        router = LLMRouter(store, fake=fake, dry_run=True)
        router.retry_delay = 0

        rounds = []
        real_update_group = store.update_group

        async def record_update_group(**fields):
            if "round" in fields:
                rounds.append(int(fields["round"]))
            return await real_update_group(**fields)

        monkeypatch.setattr(store, "update_group", record_update_group)
        await engine.run_rounds(store, router)

        assert 1 not in rounds
        assert all(value >= 2 for value in rounds)
        assert 3 in rounds
        row = await group_row(group_id)
        assert int(row["round"]) == 3
        assert (row["status"], row["stop_reason"]) == ("done", "accepted")
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 P3

def test_p3_rework_requirements_keep_300_chars(monkeypatch, tmp_path):
    """P3：250 字返工要求完整保留，400 字要求按 300 字上限截断。"""
    async def scenario():
        short = "甲" * 250
        long = "乙" * 400
        script = base_script()
        script["accept"] = [
            accept_payload(passed=False, rework=[short, long]),
            accept_payload(),
        ]
        script["rework"] = rework_payload(assignments=[])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        rework_call = calls_for(fake, "r01/60-rework-host")[0]
        values = user_payload(rework_call)["rework"]
        assert values[0] == short and len(values[0]) == 250
        assert values[1] == "乙" * 300 and len(values[1]) == 300
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 T2（E7）

def test_t2_rejected_objection_not_in_next_note(monkeypatch, tmp_path):
    """T2（E7）：主持人驳回的质疑不进入下一轮调研成员的 objections_to_address。"""
    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("market", "tech"))
        script["critique"] = {
            "objections": [
                {"target": "market", "type": "missing",
                 "problem": "市场样本不足", "suggestion": "补查小团队样本"},
                {"target": "tech", "type": "unsupported",
                 "problem": "技术证据不足", "suggestion": "补查官方文档"},
            ],
            "counter_view": "目前的证据仍有盲点。",
        }
        script["decide"] = [
            {"responses": [
                {"id": "O1", "action": "accept", "reason": "先补市场样本"},
                {"id": "O2", "action": "reject", "reason": "不影响本次结论"},
            ], "note_responses": [], "decision": "research",
                "assignments": [{"role": "market", "task": "补查小团队样本"}],
                "brief_for_writer": "", "summary": "再查一轮。"},
            {"responses": [
                {"id": "O1", "action": "accept", "reason": "已补"},
                {"id": "O2", "action": "accept", "reason": "已核"},
            ], "note_responses": [], "decision": "draft",
                "assignments": [], "brief_for_writer": "按已查资料写。",
                "summary": "开始撰稿。"},
        ]
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=3)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        note_call = calls_for(fake, "r02/13-note-market")[0]
        problems = [item["problem"] for item in user_payload(note_call)["objections_to_address"]]
        assert "市场样本不足" in problems
        assert "技术证据不足" not in problems
    asyncio.run(scenario())


def test_t2_rejected_objection_targeting_next_member_not_sent(monkeypatch, tmp_path):
    """T2（E7）：被驳回的质疑即使指向下一轮要调研的成员，也不再下发。"""
    async def scenario():
        script = base_script()
        script["critique"] = {
            "objections": [
                {"target": "market", "type": "missing",
                 "problem": "市场样本不足", "suggestion": "补查小团队样本"},
                {"target": "market", "type": "contradiction",
                 "problem": "市场口径不一致", "suggestion": "统一统计口径"},
            ],
            "counter_view": "两次口径需要对齐。",
        }
        script["decide"] = [
            {"responses": [
                {"id": "O1", "action": "accept", "reason": "先补样本"},
                {"id": "O2", "action": "reject", "reason": "口径差异不影响结论"},
            ], "note_responses": [], "decision": "research",
                "assignments": [{"role": "market", "task": "补查小团队样本"}],
                "brief_for_writer": "", "summary": "再查一轮。"},
            {"responses": [
                {"id": "O1", "action": "accept", "reason": "已补"},
                {"id": "O2", "action": "accept", "reason": "已核"},
            ], "note_responses": [], "decision": "draft",
                "assignments": [], "brief_for_writer": "按已查资料写。",
                "summary": "开始撰稿。"},
        ]
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=3)
        assert detail["status"] == "done"

        note_call = calls_for(fake, "r02/13-note-market")[0]
        problems = [item["problem"] for item in user_payload(note_call)["objections_to_address"]]
        assert problems == ["市场样本不足"]
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 T4（E11）

def test_t4_previous_draft_is_previous_version_full_text(monkeypatch, tmp_path):
    """T4（E11）：返工轮的 previous_draft 是上一版成果全文，不是 None 或摘要。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        first = await discuss_store.get_output(USER, group_id, 1)
        draft_calls = calls_for(fake, "r02/40-draft-writer")
        assert len(draft_calls) == 1
        previous = user_payload(draft_calls[0])["previous_draft"]
        assert previous == first["content"]
        assert previous is not None
        assert len(previous) > 400
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 T5（E14）

def test_t5_previous_points_reach_second_round_note(monkeypatch, tmp_path):
    """T5（E14）：第二轮笔记的 your_previous_points 含第一轮该成员的要点。"""
    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("market",))
        script["decide"] = [
            decide_payload(decision="research",
                           assignments=[{"role": "market", "task": "补查小团队样本"}]),
            decide_payload(),
        ]
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=3,
            members=[{"role": "market"}])
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")
        assert detail["round"] == 2

        first_note_calls = calls_for(fake, "r01/13-note-market")
        assert len(first_note_calls) == 1
        second_note = calls_for(fake, "r02/13-note-market")[0]
        previous = user_payload(second_note)["your_previous_points"]

        expected = script["note"]["key_points"]
        assert [{"text": item["text"], "refs": item["refs"]} for item in expected] == previous
        assert previous
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 T6（E17）

def test_t6_objections_only_target_member_and_overall(monkeypatch, tmp_path):
    """T6（E17）：笔记的 objections_to_address 只含针对本人与 overall 的质疑。"""
    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("market", "tech"))
        script["critique"] = {
            "objections": [
                {"target": "market", "type": "missing",
                 "problem": "市场样本不足", "suggestion": "补查小团队样本"},
                {"target": "tech", "type": "unsupported",
                 "problem": "技术证据不足", "suggestion": "补查官方文档"},
                {"target": "overall", "type": "bias",
                 "problem": "整体结论偏乐观", "suggestion": "补一段风险"},
            ],
            "counter_view": "结论需要更保守。",
        }
        script["decide"] = [
            {"responses": [
                {"id": "O1", "action": "accept", "reason": "补市场"},
                {"id": "O2", "action": "accept", "reason": "补技术"},
                {"id": "O3", "action": "accept", "reason": "补风险"},
            ], "note_responses": [], "decision": "research",
                "assignments": [{"role": "market", "task": "补查小团队样本"}],
                "brief_for_writer": "", "summary": "再查一轮。"},
            {"responses": [
                {"id": "O1", "action": "accept", "reason": "已补"},
                {"id": "O2", "action": "accept", "reason": "已补"},
                {"id": "O3", "action": "accept", "reason": "已补"},
            ], "note_responses": [], "decision": "draft",
                "assignments": [], "brief_for_writer": "按已查资料写。",
                "summary": "开始撰稿。"},
        ]
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=3)
        assert detail["status"] == "done"

        note_call = calls_for(fake, "r02/13-note-market")[0]
        objections = user_payload(note_call)["objections_to_address"]
        assert [item["target"] for item in objections] == ["market", "overall"]
        assert [item["problem"] for item in objections] == ["市场样本不足", "整体结论偏乐观"]
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 T7（E18）

def test_t7_sources_only_include_cited(monkeypatch, tmp_path):
    """T7（E18）：撰稿与验收只拿要点引用过的来源，登记过但没引用的不出现。"""
    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("market",))
        script["note"] = {
            "note": "只采用第一份来源的结论 [S1]。",
            "key_points": [
                {"text": "事实一 [S1]", "refs": ["S1"]},
                {"text": "事实二 [S1]", "refs": ["S1"]},
            ],
            "gaps": [],
        }
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2,
            members=[{"role": "market"}])
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        registered = await service.sources(USER, group_id)
        assert [source["id"] for source in registered] == ["S1", "S2"]

        draft_call = calls_for(fake, "r01/40-draft-writer")[0]
        assert [source["id"] for source in user_payload(draft_call)["sources"]] == ["S1"]
        accept_call = calls_for(fake, "r01/50-accept-acceptor")[0]
        assert [source["id"] for source in user_payload(accept_call)["sources"]] == ["S1"]
    asyncio.run(scenario())


# ---------------------------------------------------------------- 返修 T8（E24）

def test_t8_avatar_owner_view_reaches_accept_and_rework(monkeypatch, tmp_path):
    """T8（E24）：有分身时验收与返工载荷的 owner_view 等于分身看稿结果。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        await prepare_avatar()
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=True)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        view = script["view"]
        assert len(calls_for(fake, "r00/02-brief-avatar")) == 1
        messages = await message_rows(group_id)
        assert [message["kind"] for message in messages].count("brief") == 1
        assert [message["kind"] for message in messages].count("view") == 2

        accept_one = user_payload(calls_for(fake, "r01/50-accept-acceptor")[0])
        assert accept_one["owner_view"] == view
        rework_call = user_payload(calls_for(fake, "r01/60-rework-host")[0])
        assert rework_call["owner_view"] == view
        accept_two = user_payload(calls_for(fake, "r02/50-accept-acceptor")[0])
        assert accept_two["owner_view"] == view
    asyncio.run(scenario())


def test_t8_no_avatar_owner_view_is_null(monkeypatch, tmp_path):
    """T8（E24）：没有分身时验收与返工载荷的 owner_view 都是 null。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(passed=False), accept_payload()]
        script["rework"] = rework_payload(assignments=[])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=False)
        assert (detail["status"], detail["stop_reason"]) == ("done", "accepted")

        accept_one = user_payload(calls_for(fake, "r01/50-accept-acceptor")[0])
        assert accept_one["owner_view"] is None
        assert user_payload(calls_for(fake, "r01/60-rework-host")[0])["owner_view"] is None
        accept_two = user_payload(calls_for(fake, "r02/50-accept-acceptor")[0])
        assert accept_two["owner_view"] is None
        assert not [call for call in fake.calls if call.get("task") in ("brief", "view")]
    asyncio.run(scenario())


# ---------------------------------------------------------------- 复核返修（X 系列）

def test_x12_rework_payload_includes_verbatim_citation_issue(monkeypatch, tmp_path):
    """X12（规格 4.6.2）：逐字引用问题进入下一轮返工载荷的 rework。"""
    async def scenario():
        script = base_script()
        script["accept"] = [accept_payload(quote=DRAFT_SENTENCE), accept_payload()]
        script["rework"] = rework_payload(assignments=[])
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert (detail["status"], detail["round"]) == ("done", 2)
        assert DRAFT_SENTENCE in script["draft"]

        rework_call = calls_for(fake, "r01/60-rework-host")[0]
        assert user_payload(rework_call)["rework"] == [
            f"引用问题：「{DRAFT_SENTENCE}」缺少来源"]
    asyncio.run(scenario())


def test_x15_avatar_brief_context_reaches_draft_writer(monkeypatch, tmp_path):
    """X15（规格 4.6.2）：分身 brief 的 context 原样进入撰稿载荷 owner_context。"""
    async def scenario():
        await setup_db(monkeypatch, tmp_path)
        await prepare_avatar()
        script = base_script()
        script["brief"] = {"context": "主人偏务实，预算有限。", "answers": [], "ask_owner": []}
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(
            monkeypatch, tmp_path, fake, max_rounds=2, avatar=True)
        assert detail["status"] == "done"
        assert len(calls_for(fake, "r00/02-brief-avatar")) == 1

        draft_call = calls_for(fake, "r01/40-draft-writer")[0]
        assert user_payload(draft_call)["owner_context"] == script["brief"]["context"]
    asyncio.run(scenario())


def test_x34_collect_findings_truncates_fact_to_160():
    """X34（规格 4.8）：超过 160 字的事实截到 160 字，不依赖引擎流程。"""
    long_fact = "甲" * 200
    results = [{
        "query": "问题",
        "data": {"findings": [{"fact": long_fact, "refs": [1]}]},
        "sources": [{"title": "来源一", "url": "https://example.com/a",
                     "site_name": "站点一", "index": 1}],
        "error": None,
    }]
    facts = research.collect_findings(results, lambda source: "S1")
    assert facts == [{"fact": "甲" * 160, "refs": ["S1"]}]
    assert len(facts[0]["fact"]) == 160


def test_x35_note_payload_only_includes_member_sources(monkeypatch, tmp_path):
    """X35（规格 4.6.2）：笔记载荷只含该成员事实与历史要点引用到的来源。"""
    async def scenario():
        script = base_script()
        script["plan"] = plan_payload(picks=("market", "competitor"))
        script["r01/10-queries-market"] = {"queries": ["问题一"]}
        script["r01/10-queries-competitor"] = {"queries": ["问题二"]}
        script["r01/13-note-market"] = {
            "note": "市场结论只引用 S1 [S1]。",
            "key_points": [
                {"text": "市场增长 12% [S1]", "refs": ["S1"]},
                {"text": "市场集中度较高 [S1]", "refs": ["S1"]},
            ],
            "gaps": [],
        }
        script["r01/13-note-competitor"] = {
            "note": "竞品结论只引用 S2 [S2]。",
            "key_points": [
                {"text": "竞品定价差异明显 [S2]", "refs": ["S2"]},
                {"text": "竞品套餐分层 [S2]", "refs": ["S2"]},
            ],
            "gaps": [],
        }
        fake = FakeLLM(script)
        group_id, detail = await create_and_run(monkeypatch, tmp_path, fake, max_rounds=2)
        assert detail["status"] == "done"

        registered = await service.sources(USER, group_id)
        assert [source["id"] for source in registered] == ["S1", "S2"]

        market_note = user_payload(calls_for(fake, "r01/13-note-market")[0])
        assert market_note["sources"] == [
            {"id": "S1", "title": "来源1", "site": "站点1"}]
        assert "S2" not in [source["id"] for source in market_note["sources"]]

        competitor_note = user_payload(calls_for(fake, "r01/13-note-competitor")[0])
        assert [source["id"] for source in competitor_note["sources"]] == ["S2"]

        # 撰稿与验收看全体的要点，因此两条来源都在；笔记只看本成员的来源。
        draft_sources = user_payload(calls_for(fake, "r01/40-draft-writer")[0])["sources"]
        assert [source["id"] for source in draft_sources] == ["S1", "S2"]
        accept_sources = user_payload(calls_for(fake, "r01/50-accept-acceptor")[0])["sources"]
        assert [source["id"] for source in accept_sources] == ["S1", "S2"]
    asyncio.run(scenario())


def test_x14_gather_all_settles_siblings_before_raising():
    """X14（规格 4.12）：一个并行步骤失败时，先等其余步骤收尾再抛出。"""
    async def scenario():
        started = set()
        finished = set()

        async def sibling(name):
            started.add(name)
            try:
                # The failing sibling raises first; the gather must not return
                # until this sibling has finished its own cleanup.
                await asyncio.sleep(0.1)
            finally:
                finished.add(name)

        async def failing():
            started.add("failing")
            await asyncio.sleep(0)
            raise RuntimeError("第一个失败")

        with pytest.raises(RuntimeError, match="第一个失败"):
            await engine._gather_all([
                sibling("market"), failing(), sibling("competitor")])
        assert started == {"market", "failing", "competitor"}
        # Plain gather would raise before these finish; the protected gather
        # waits for both siblings. This is the X14 discriminator.
        assert finished == {"market", "competitor"}
    asyncio.run(scenario())


def test_x37_avatar_effective_model_prefers_byok_and_configured(monkeypatch):
    """X37（规格 4.9）：启用自带模型用 byok:self，作者指定优先，不可用回落默认。"""
    async def scenario():
        calls = []

        async def available(self):
            calls.append(self.username)
            return {"model_spec": "byok:self"}

        monkeypatch.setattr(avatar.ByokBridge, "describe", available)
        assert await avatar.effective_model(USER, None) == "byok:self"
        assert calls == [USER]

        calls.clear()
        configured = "deepseek:deepseek-flash"
        assert await avatar.effective_model(USER, configured) == configured
        assert calls == []

        async def unavailable(self):
            calls.append(self.username)
            raise ByokUnavailable("请先启用可用的自带模型")

        monkeypatch.setattr(avatar.ByokBridge, "describe", unavailable)
        assert await avatar.effective_model(USER, None) == roles.DEFAULT_AVATAR_MODEL
        assert calls == [USER]
    asyncio.run(scenario())
