"""Offline state recovery, paid fake transport and 25-chapter v2 acceptance."""
import asyncio
from collections import Counter
import json
import threading

import pytest

import database
from novel import runner, service
from novel.billing import NovelBilling
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.store_db import get_db


AUTHOR = "v2-runner-author"


def request(*, chapters=3, automation="full_auto", batch=5, advisors=True):
    agents = {"editor": "dashscope:qwen3.8-max", "writer": "deepseek:deepseek-flash",
              "archivist": "dashscope:qwen3.8-max", "reviewer": "dashscope:qwen3.8-max"}
    if advisors:
        agents.update(pacing_advisor="dashscope:qwen3.8-max", reader_rep="dashscope:qwen3.8-max")
    return service.CreateNovel(seed_idea="现代都市玄幻修仙，普通人加入宗门，靠机缘一路变成最强。",
        agents=agents, structure="v2", panel_mode="critique" if advisors else "solo",
        automation=automation, batch_size=batch, budget_strawberries=1_000_000,
        target={"min_chapters": chapters, "max_chapters": chapters, "chapter_words": 1000})


async def prepare(monkeypatch, tmp_path, fake=None, *, charged=False):
    monkeypatch.setenv("DEV_MODE", "0" if charged else "1")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "v2-runner.db"))
    monkeypatch.setattr(runner, "check_chat_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(runner, "check_daily_cap", lambda *a, **k: None)
    await database.init_db()
    await database.get_or_create_user(AUTHOR)
    async with get_db() as db:
        await db.execute("UPDATE users SET strawberry_balance=1000000 WHERE username=?", (AUTHOR,))
        await db.commit()
    fake = fake or FakeLLM()

    def factory(store, username, novel_id, token):
        router = LLMRouter(store, fake=fake, dry_run=not charged,
                           billing=NovelBilling(username, novel_id, token))
        router.retry_delay = 0
        # Exercise production reservation and atomic settlement with a local
        # provider response, rather than making dry-run zero charges tautological.
        router._single_real_call = fake.complete
        return router

    monkeypatch.setattr(runner, "router_factory", factory)
    return fake


async def drain(novel_id):
    task = runner.TASKS.get(novel_id)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 20)


async def create(data, *, gate=False):
    book = await service.create(AUTHOR, data)
    await drain(book["id"])
    if gate:
        async with get_db() as db:
            row = await (await db.execute("SELECT config_json FROM novels WHERE id=?", (book["id"],))).fetchone()
            config = json.loads(row[0])
            config["volume_gate"] = True
            await db.execute("UPDATE novels SET config_json=? WHERE id=?", (json.dumps(config), book["id"]))
            await db.commit()
    return book["id"]


def test_25_chapter_paid_fake_acceptance(monkeypatch, tmp_path):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path, charged=True)
        novel_id = await create(request(chapters=25))
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"], book["bible_version"]) == ("awaiting_end", 25, 30)
        bible = await service.bible(AUTHOR, novel_id)
        volumes = bible["dynamic"]["volumes"]
        assert [(v["volume"], v["chapters"]) for v in volumes] == [(1, [1, 10]), (2, [11, 20]), (3, [21, 25])]
        assert all(m["status"] == "done" for v in volumes for m in v["milestones"])
        async with get_db() as db:
            chapters = [dict(row) for row in await (await db.execute(
                "SELECT chapter,meeting_json,archive_json FROM novel_chapters WHERE novel_id=? ORDER BY chapter", (novel_id,))).fetchall()]
            steps = [dict(row) for row in await (await db.execute(
                "SELECT * FROM novel_steps WHERE novel_id=? ORDER BY step_key", (novel_id,))).fetchall()]
            sources = [row[0] for row in await (await db.execute(
                "SELECT source FROM novel_bible_versions WHERE novel_id=? AND source LIKE 'volume:%' ORDER BY version", (novel_id,))).fetchall()]
            balance = (await (await db.execute("SELECT strawberry_balance FROM users WHERE username=?", (AUTHOR,))).fetchone())[0]
        decisions = [json.loads(row["meeting_json"])["decision"] for row in chapters]
        archives = [json.loads(row["archive_json"]) for row in chapters]
        payoff_chapters = [i for i, decision in enumerate(decisions, 1) if decision["genre_payoff"]]
        assert all(archive["payoff_delivered"] is True
                   for decision, archive in zip(decisions, archives) if decision["genre_payoff"])
        for start in range(23):
            assert any(decision["genre_payoff"] for decision in decisions[start:start + 3])
            assert any(archive.get("payoff_delivered") is True for archive in archives[start:start + 3])
            assert any("T1" in decision["beat_sheet"]["advances_threads"] for decision in decisions[start:start + 3])
        open_count, maximum_open = 1, 1
        for archive in archives:
            planted, resolved = len(archive["foreshadowing_planted"]), len(archive["foreshadowing_resolved"])
            assert planted <= 2
            assert open_count <= 20 or planted <= resolved
            open_count += planted - resolved
            maximum_open = max(maximum_open, open_count)
        by_volume = [sum(len(archives[i - 1]["foreshadowing_planted"]) for i in range(v["chapters"][0], v["chapters"][1] + 1))
                     for v in volumes]
        assert all(count <= volume["new_mystery_budget"] for count, volume in zip(by_volume, volumes))
        assert sources == ["volume:1", "volume:2", "volume:3"]
        finalized = [call for call in fake.calls if call["task"] == "volume_finalize"]
        assert [call["chapter"] for call in finalized] == [1, 11, 21]
        assert len({call["step_key"] for call in fake.calls}) == len(fake.calls)
        assert book["reserved_strawberries"] == 0
        # Step reservation amounts are historical audit fields. Outstanding
        # reservations are those still carrying billing_status='reserved'.
        assert all(row["billing_status"] == "settled" for row in steps)
        charged = sum(row["strawberries_charged"] for row in steps)
        assert book["spent_strawberries"] == charged == 1_000_000 - balance
        assert charged > 0
        metrics = {"chapters": 25, "volume_meetings": len(finalized), "volume_chapters": [v["chapters"] for v in volumes],
                   "calls": len(fake.calls), "payoff_chapters": payoff_chapters,
                   "payoff_types": sorted({d["genre_payoff"]["type"] for d in decisions if d["genre_payoff"]}),
                   "core_advanced": sum("T1" in d["beat_sheet"]["advances_threads"] for d in decisions),
                   "milestones_done": sum(m["status"] == "done" for v in volumes for m in v["milestones"]),
                   "volume_planted": by_volume, "maximum_open": maximum_open,
                   "final_open": open_count, "spent": charged, "step_charges": charged, "reserved": 0}
        print("NOVEL_V2_25=" + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    asyncio.run(scenario())


@pytest.mark.parametrize("automation,expected", [("full_auto", "awaiting_end"), ("per_batch", "awaiting_review"), ("per_chapter", "awaiting_plan")])
def test_volume_gate_defaults_to_automatic_approval(monkeypatch, tmp_path, automation, expected):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(automation=automation, batch=1))
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert book["status"] == expected
        assert book["config"]["_volume_gate"]["approved"] is True
        assert len((await service.bible(AUTHOR, novel_id))["dynamic"]["volumes"]) == 1
    asyncio.run(scenario())


def test_full_auto_ignores_enabled_volume_gate(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(), gate=True)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_end"
    asyncio.run(scenario())


def test_volume_recovery_reuses_completed_paid_steps(monkeypatch, tmp_path):
    async def scenario():
        entered = asyncio.Event()
        blocked = False

        async def script(call, _):
            nonlocal blocked
            if call["task"] == "volume_finalize" and not blocked:
                blocked = True
                entered.set()
                await asyncio.Event().wait()

        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script), charged=True)
        novel_id = await create(request(chapters=2))
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await asyncio.wait_for(entered.wait(), 10)
        await service.transition(AUTHOR, novel_id, "pause")
        before = await service.detail(AUTHOR, novel_id)
        assert before["reserved_strawberries"] == 0
        await service.transition(AUTHOR, novel_id, "resume")
        await drain(novel_id)
        after = await service.detail(AUTHOR, novel_id)
        assert after["status"] == "awaiting_end"
        counts = Counter(call["step_key"] for call in fake.calls)
        for name in ("01-volume-plan-editor", "02-volume-critique-pacing_advisor", "02-volume-critique-reader_rep"):
            assert counts[f"arm-panel/vol01/{name}.json"] == 1
        assert counts["arm-panel/vol01/03-volume-finalize-editor.json"] == 2
        async with get_db() as db:
            versions = (await (await db.execute("SELECT COUNT(*) FROM novel_bible_versions WHERE novel_id=? AND source='volume:1'", (novel_id,))).fetchone())[0]
            charges = (await (await db.execute("SELECT SUM(strawberries_charged) FROM novel_steps WHERE novel_id=?", (novel_id,))).fetchone())[0]
        assert versions == 1
        assert after["spent_strawberries"] == charges and after["reserved_strawberries"] == 0
    asyncio.run(scenario())


def test_volume_gate_precedes_batch_and_rearchive_preserves_next_plan(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(chapters=12, automation="per_batch", batch=10), gate=True)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_volume"
        await service.approve_volume(AUTHOR, novel_id, service.VolumeApproval())
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"]) == ("awaiting_volume", 10)
        before = (await service.bible(AUTHOR, novel_id))["dynamic"]["volumes"][1]
        chapter = await service.chapter(AUTHOR, novel_id, 10)
        await service.edit_chapter(AUTHOR, novel_id, 10, service.Manuscript(body=chapter["body"] + "\n\n她确认保留原件。"))
        await drain(novel_id)
        assert (await service.bible(AUTHOR, novel_id))["dynamic"]["volumes"][1] == before
        await service.approve_volume(AUTHOR, novel_id, service.VolumeApproval())
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"]) == ("awaiting_review", 10)
        await service.transition(AUTHOR, novel_id, "continue")
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_end"
    asyncio.run(scenario())


def test_v2_invalid_decision_is_repaired_with_concrete_budget_error(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()
        invalid_sent = False

        def script(call, _):
            nonlocal invalid_sent
            if call["task"] == "finalize" and not invalid_sent:
                invalid_sent = True
                result = baseline.default_response(call)
                result["beat_sheet"]["foreshadowing_plant"] = [{"description": "新线索", "importance": "minor"}] * 3
                return result

        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script))
        novel_id = await create(request(chapters=1))
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_end"
        calls = [call for call in fake.calls if call["task"] == "finalize"]
        assert len(calls) == 2
        errors = json.loads(calls[1]["messages"][-1]["content"])["校验错误"]
        assert any("3" in error and "2" in error for error in errors)
    asyncio.run(scenario())


def test_switching_full_auto_clears_pending_batch_after_volume_gate(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(chapters=12, automation="per_batch", batch=10), gate=True)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        await service.approve_volume(AUTHOR, novel_id, service.VolumeApproval())
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["chapters_done"] == 10
        await service.transition(AUTHOR, novel_id, "pause")
        await service.patch(AUTHOR, novel_id, service.PatchNovel(automation="full_auto"))
        await service.transition(AUTHOR, novel_id, "resume")
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"]) == ("awaiting_end", 12)
        assert book["config"]["_volume_gate"]["approved"] is True
        assert "_volume_batch_pending" not in book["config"]
    asyncio.run(scenario())


def test_upgrade_paused_final_chapter_can_extend_then_plan_new_range(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()

        def script(call, _):
            if call["task"] == "archive" and call["chapter"] == 2:
                archive = baseline.default_response(call)
                archive["locked_conflicts"] = ["原稿需作者确认锁定事实"]
                return archive

        await prepare(monkeypatch, tmp_path, FakeLLM(script))
        data = request(chapters=2, advisors=False).model_copy(update={"structure": "v1"})
        novel_id = await create(data)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"]) == ("paused", 2)
        await service.upgrade_structure(AUTHOR, novel_id)
        await service.transition(AUTHOR, novel_id, "resume")
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_end"
        await service.reject_end(AUTHOR, novel_id, service.RejectEnd(extend_chapters=2))
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"]) == ("awaiting_end", 4)
        assert (await service.volumes(AUTHOR, novel_id))[0]["chapters"] == [3, 4]
    asyncio.run(scenario())


def test_upgrade_plan_redo_and_approval_preserve_v1_thread_history(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()

        def script(call, _):
            if call["task"] == "setup":
                setup = baseline.default_response(call)
                setup["main_threads"].append({"name": "同伴成长", "description": "同伴独立完成调查。"})
                return setup
            if call["task"] == "decision" and call["chapter"] == 3:
                decision = baseline.default_response(call)
                decision["beat_sheet"]["advances_threads"] = ["T2"]
                return decision

        await prepare(monkeypatch, tmp_path, FakeLLM(script))
        data = request(chapters=6, automation="per_batch", batch=2, advisors=False).model_copy(update={"structure": "v1"})
        novel_id = await create(data)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["chapters_done"] == 2
        await service.upgrade_structure(AUTHOR, novel_id)
        await service.patch(AUTHOR, novel_id, service.PatchNovel(automation="per_chapter"))
        await service.transition(AUTHOR, novel_id, "continue")
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["chapters_done"]) == ("awaiting_plan", 2)
        await service.redo_plan(AUTHOR, novel_id, service.Note(text="同伴本章完成自己的调查"))
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_plan"
        await service.approve_plan(AUTHOR, novel_id, service.PlanApproval())
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["chapters_done"] == 3
        assert (await service.chapter(AUTHOR, novel_id, 3))["meeting"]["decision"]["beat_sheet"]["advances_threads"] == ["T2"]
    asyncio.run(scenario())


def test_runner_alone_restores_pending_volume_gate_without_repeating_steps(monkeypatch, tmp_path):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(automation="per_chapter"), gate=True)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        before = await service.detail(AUTHOR, novel_id)
        calls = len(fake.calls)
        async with get_db() as db:
            await db.execute("UPDATE novels SET status='running',run_token=NULL WHERE id=?", (novel_id,))
            await db.commit()
        # Deliberately bypass service.resume: exercise the runner's backup.
        await runner.start_novel(novel_id, AUTHOR)
        await drain(novel_id)
        after = await service.detail(AUTHOR, novel_id)
        assert (after["status"], after["chapters_done"], after["bible_version"]) == (
            "awaiting_volume", 0, before["bible_version"])
        assert len(fake.calls) == calls
    asyncio.run(scenario())


def test_upgraded_v1_latest_rearchive_matches_unupgraded_canonical_bytes(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()

        def script(call, _):
            if call["task"] == "archive" and call["chapter"] == 2:
                archive = baseline.default_response(call)
                archive["foreshadowing_planted"] = [
                    {"description": f"实际出现的旧章线索{i}", "importance": "minor"} for i in range(3)]
                return archive

        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script))
        data = request(chapters=6, automation="per_batch", batch=2, advisors=False).model_copy(update={"structure": "v1"})
        snapshots = []
        for upgrade in (False, True):
            novel_id = await create(data)
            await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
            await drain(novel_id)
            if upgrade:
                await service.upgrade_structure(AUTHOR, novel_id)
            chapter = await service.chapter(AUTHOR, novel_id, 2)
            await service.edit_chapter(AUTHOR, novel_id, 2,
                service.Manuscript(body=chapter["body"] + "\n\n她再次核对了原件。"))
            await drain(novel_id)
            book = await service.detail(AUTHOR, novel_id)
            assert (book["status"], book["pause_reason"]) == ("awaiting_review", None)
            archived = await service.chapter(AUTHOR, novel_id, 2)
            assert len(archived["archive"]["foreshadowing_planted"]) == 3
            async with get_db() as db:
                bible = (await (await db.execute("SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND version=?",
                    (novel_id, book["bible_version"])) ).fetchone())[0]
            snapshots.append((bible.encode("utf-8"), archived["archive"]))
        assert snapshots[0] == snapshots[1]
        rearchives = [c for c in fake.calls if c["step_key"].startswith("rearchive/")]
        assert len(rearchives) == 2
        assert all("genre_payoff" not in FakeLLM.payload(c) for c in rearchives)
    asyncio.run(scenario())


def test_native_v2_rearchive_still_rejects_three_planted_foreshadows(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()

        def script(call, _):
            if call["task"] == "archive" and call["step_key"].startswith("rearchive/"):
                archive = baseline.default_response(call)
                archive["foreshadowing_planted"] = [
                    {"description": f"违规新增线索{i}", "importance": "minor"} for i in range(3)]
                return archive

        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script))
        novel_id = await create(request(chapters=6, automation="per_batch", batch=2, advisors=False))
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        chapter = await service.chapter(AUTHOR, novel_id, 2)
        await service.edit_chapter(AUTHOR, novel_id, 2,
            service.Manuscript(body=chapter["body"] + "\n\n她再次核对了原件。"))
        await drain(novel_id)
        book = await service.detail(AUTHOR, novel_id)
        assert (book["status"], book["pause_reason"]) == ("paused", "step_failed")
        calls = [c for c in fake.calls if c["step_key"].startswith("rearchive/")]
        assert len(calls) == 2
        errors = json.loads(calls[-1]["messages"][-1]["content"])["校验错误"]
        assert any("3" in error and "2" in error for error in errors)
    asyncio.run(scenario())


def test_runner_payoff_window_uses_archivist_confirmation(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()

        def script(call, _):
            payload = FakeLLM.payload(call)
            if call["task"] in {"plan", "finalize"} and call["chapter"] == 2:
                decision = baseline.default_response(call)
                decision["genre_payoff"] = {"type": "确认关键证据", "beat_index": 2}
                return decision
            if call["task"] == "write" and call["chapter"] == 2:
                body = baseline.default_response(call)
                return body.replace(baseline.payoff_scene(payload["context"]["genre_payoff"]), "")
            if call["task"] == "archive" and call["chapter"] == 2:
                archive = baseline.default_response(call)
                assert archive["payoff_delivered"] is False
                return archive
            if call["task"] == "plan" and call["chapter"] == 3 and not any(
                    message["role"] == "assistant" for message in call["messages"]):
                decision = baseline.default_response(call)
                decision["genre_payoff"] = None
                return decision

        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script))
        data = request(chapters=4, automation="per_batch", batch=2)
        data.agents.pop("reviewer")
        novel_id = await create(data)
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        chapter2 = await service.chapter(AUTHOR, novel_id, 2)
        assert chapter2["meeting"]["decision"]["genre_payoff"] is not None
        assert chapter2["archive"]["payoff_delivered"] is False
        await service.transition(AUTHOR, novel_id, "continue")
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_end"
        plans = [c for c in fake.calls if c["task"] == "plan" and c["chapter"] == 3]
        assert len(plans) == 2
        brief = FakeLLM.payload(plans[0])["brief"]
        assert brief["payoff_history"][-1]["genre_payoff"] is None
        assert any("本章必须安排类型爽点" in flag for flag in brief["red_flags"])
    asyncio.run(scenario())


def test_rearchive_preserves_extended_current_volume_and_payoff_plan(monkeypatch, tmp_path):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(chapters=3, advisors=False))
        await service.approve_setup(AUTHOR, novel_id, service.SetupApproval())
        await drain(novel_id)
        start = runner.start_novel

        async def defer_start(*args, **kwargs):
            return None

        monkeypatch.setattr(runner, "start_novel", defer_start)
        await service.reject_end(AUTHOR, novel_id, service.RejectEnd(extend_chapters=2))
        extended = (await service.volumes(AUTHOR, novel_id))[0]
        assert extended["chapters"] == [1, 5]
        assert len(extended["payoff_plan"]) >= 2
        await service.patch(AUTHOR, novel_id, service.PatchNovel(automation="per_chapter"))
        monkeypatch.setattr(runner, "start_novel", start)
        chapter = await service.chapter(AUTHOR, novel_id, 3)
        await service.edit_chapter(AUTHOR, novel_id, 3,
            service.Manuscript(body=chapter["body"] + "\n\n她把原件重新锁好。"))
        await drain(novel_id)
        assert (await service.detail(AUTHOR, novel_id))["status"] == "awaiting_plan"
        volumes = await service.volumes(AUTHOR, novel_id)
        assert len(volumes) == 1
        assert volumes[0]["chapters"] == extended["chapters"]
        assert volumes[0]["payoff_plan"] == extended["payoff_plan"]
        assert [m["status"] for m in volumes[0]["milestones"]] == [m["status"] for m in extended["milestones"]]
        assert sum(call["task"] == "volume_plan" for call in fake.calls) == 1
    asyncio.run(scenario())


def test_foreground_cancel_drains_worker_owned_by_another_event_loop(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        novel_id = await create(request(advisors=False))
        entered, drained = threading.Event(), threading.Event()

        async def worker():
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                drained.set()

        def serve():
            async def run_worker():
                task = asyncio.create_task(worker())
                runner.TASKS[novel_id], runner._owners[novel_id] = task, AUTHOR
                await asyncio.gather(task, return_exceptions=True)
            asyncio.run(run_worker())

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            await runner.cancel_novel(novel_id, AUTHOR)
            assert drained.is_set()
            await asyncio.to_thread(thread.join, 5)
            assert not thread.is_alive()
        finally:
            runner.TASKS.pop(novel_id, None)
            runner._owners.pop(novel_id, None)
    asyncio.run(scenario())
