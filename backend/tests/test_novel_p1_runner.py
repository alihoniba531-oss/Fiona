"""Offline state-machine acceptance tests using the public service operations."""

import asyncio
from collections import Counter
import json

import pytest

import database
from novel import runner, service
from novel.billing import NovelBilling
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.store_db import get_db


def request(*, mode="solo", automation="full_auto", chapters=3, batch=5):
    agents = {"editor": "dashscope:qwen3.8-max", "writer": "deepseek:deepseek-flash",
              "archivist": "ark:doubao-seed-2-1-pro-260915", "reviewer": "dashscope:qwen3.8-max"}
    if mode == "critique":
        agents["twist_designer"] = "dashscope:qwen3.8-max"
    return service.CreateNovel(seed_idea="旧录像里的秘密", agents=agents, panel_mode=mode,
        automation=automation, batch_size=batch, target={"min_chapters": chapters, "max_chapters": chapters,
        "chapter_words": 1000}, budget_strawberries=100000)


async def prepare(monkeypatch, tmp_path, fake=None):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "runner.db"))
    await database.init_db()
    await database.get_or_create_user("author")
    fake = fake or FakeLLM()
    def factory(store, username, novel_id, token):
        router = LLMRouter(store, fake=fake, dry_run=True, billing=NovelBilling(username, novel_id, token))
        router.retry_delay = 0
        return router
    monkeypatch.setattr(runner, "router_factory", factory)
    return fake


async def drain(novel_id):
    task = runner.TASKS.get(novel_id)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 10)


async def create_book(data, username="author"):
    book = await service.create(username, data)
    await drain(book["id"])
    return await service.detail(username, book["id"])


@pytest.mark.parametrize("mode", ["solo", "critique"])
def test_three_chapter_book_complete_and_engine_records(monkeypatch, tmp_path, mode):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path)
        book = await create_book(request(mode=mode))
        assert (book["status"], book["chapters_done"], book["bible_version"]) == ("awaiting_setup", 0, 1)
        await service.approve_setup("author", book["id"], service.SetupApproval())
        await drain(book["id"])
        book = await service.detail("author", book["id"])
        assert (book["status"], book["chapters_done"], book["bible_version"]) == ("awaiting_end", 3, 5)
        first = await service.chapter("author", book["id"], 1)
        assert first["status"] == "done"
        assert first["body"].startswith("# 第1章")
        if mode == "critique":
            meeting = first["meeting"]
            assert meeting["plan"] and meeting["critiques"] and meeting["objections"]
            assert any(item["id"].startswith("A") for item in meeting["objections"])
            assert meeting["decision"]["objection_responses"]
        completed = await service.transition("author", book["id"], "confirm")
        assert completed["status"] == "completed"
        assert completed["completed_at"]
        assert fake.call_count > 10
        assert not runner.TASKS
    asyncio.run(scenario())


def test_batch_gate_notes_and_end_extension(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        book = await create_book(request(automation="per_batch", chapters=7))
        novel_id = book["id"]
        await service.note("author", novel_id, service.Note(text="让证人保留原件"))
        await service.approve_setup("author", novel_id, service.SetupApproval())
        await drain(novel_id)
        book = await service.detail("author", novel_id)
        assert (book["status"], book["chapters_done"], book["bible_version"]) == ("awaiting_review", 5, 7)
        assert book["pending_notes"] == 0
        async with get_db() as db:
            async with db.execute("SELECT status,delivered_chapter,response_json FROM novel_notes") as cursor:
                note = await cursor.fetchone()
                assert note["status"] == "delivered" and note["delivered_chapter"] == 1
                assert json.loads(note["response_json"])["response"]
        await service.transition("author", novel_id, "continue")
        await drain(novel_id)
        assert (await service.detail("author", novel_id))["chapters_done"] == 7
        await service.reject_end("author", novel_id, service.RejectEnd(extend_chapters=2, text="再追查一条线索"))
        await drain(novel_id)
        book = await service.detail("author", novel_id)
        assert (book["status"], book["chapters_done"], book["bible_version"]) == ("awaiting_end", 9, 11)
        assert book["config"]["target"]["max_chapters"] == 9
    asyncio.run(scenario())


def test_per_chapter_redo_only_repeats_editor_then_approval(monkeypatch, tmp_path):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path)
        book = await create_book(request(mode="critique", automation="per_chapter", chapters=2))
        novel_id = book["id"]
        await service.approve_setup("author", novel_id, service.SetupApproval())
        await drain(novel_id)
        first = await service.detail("author", novel_id)
        assert first["status"] == "awaiting_plan" and first["chapters_done"] == 0
        before = len(fake.calls)
        await service.redo_plan("author", novel_id, service.Note(text="主角主动保存原件"))
        await drain(novel_id)
        assert len(fake.calls) == before + 1
        assert fake.calls[-1]["task"] == "finalize"
        assert "redo1" in fake.calls[-1]["step_key"]
        planned = await service.chapter("author", novel_id, 1)
        beat = planned["meeting"]["decision"]["beat_sheet"]
        beat["chapter_goal"] = "主动保存证据并核对来源"
        await service.approve_plan("author", novel_id, service.PlanApproval(beat_sheet=beat))
        await drain(novel_id)
        assert (await service.detail("author", novel_id))["chapters_done"] == 1
        assert (await service.detail("author", novel_id))["status"] == "awaiting_plan"
        await service.approve_plan("author", novel_id, service.PlanApproval())
        await drain(novel_id)
        assert (await service.detail("author", novel_id))["status"] == "awaiting_end"
    asyncio.run(scenario())


def test_resume_reuses_completed_steps_and_refunds_interrupted_reservation(monkeypatch, tmp_path):
    async def scenario():
        interrupted = False
        def script(call, index):
            nonlocal interrupted
            if call["task"] == "write" and not interrupted:
                interrupted = True
                return asyncio.CancelledError()
        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script))
        book = await create_book(request())
        novel_id = book["id"]
        await service.approve_setup("author", novel_id, service.SetupApproval())
        task = runner.TASKS.get(novel_id)
        if task:
            await asyncio.gather(task, return_exceptions=True)
        async with get_db() as db:
            await db.execute("UPDATE users SET strawberry_balance=strawberry_balance-17 WHERE username='author'")
            await db.execute("UPDATE novels SET reserved_strawberries=17,run_token='old-process' WHERE id=?", (novel_id,))
            await db.execute("INSERT INTO novel_steps(novel_id,username,step_key,model,status,strawberries_reserved,billing_status) "
                             "VALUES(?,'author','unfinished','dashscope:qwen3.8-max','interrupted',17,'reserved')", (novel_id,))
            await db.commit()
        await runner.recover_interrupted_novels()
        await drain(novel_id)
        book = await service.detail("author", novel_id)
        assert book["status"] == "awaiting_end" and book["reserved_strawberries"] == 0
        assert await database.get_strawberry_balance("author") == 200
        counts = Counter(call["step_key"] for call in fake.calls)
        assert counts["setup/steps/00-setup-editor.json"] == 1
        assert counts["arm-solo/ch001/03-decision-editor.json"] == 1
        assert counts["arm-solo/ch001/04-write-writer-r0-a0.json"] == 2
        actual = [(await service.chapter("author", novel_id, number))["body"] for number in range(1, 4)]
        await service.transition("author", novel_id, "confirm")
        baseline = await create_book(request())
        await service.approve_setup("author", baseline["id"], service.SetupApproval())
        await drain(baseline["id"])
        expected = [(await service.chapter("author", baseline["id"], number))["body"] for number in range(1, 4)]
        assert actual == expected
        async with get_db() as db:
            async with db.execute("SELECT billing_status,status FROM novel_steps WHERE step_key='unfinished'") as cursor:
                assert tuple(await cursor.fetchone()) == ("refunded", "interrupted")
    asyncio.run(scenario())


def test_latest_rearchive_and_earlier_edit_does_not_call_models(monkeypatch, tmp_path):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path)
        book = await create_book(request())
        novel_id = book["id"]
        await service.approve_setup("author", novel_id, service.SetupApproval())
        await drain(novel_id)
        before = fake.call_count
        version = (await service.detail("author", novel_id))["bible_version"]
        await service.edit_chapter("author", novel_id, 3, service.Manuscript(body="# 第3章 改稿\n她保留了原始录像。"))
        await drain(novel_id)
        after = await service.detail("author", novel_id)
        assert fake.call_count == before + 1
        assert (after["status"], after["bible_version"], after["chapters_done"]) == ("awaiting_end", version + 1, 3)
        async with get_db() as db:
            async with db.execute("SELECT source,bible_json FROM novel_bible_versions ORDER BY version DESC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                assert row["source"] == "rearchive:3"
                summaries = json.loads(row["bible_json"])["dynamic"]["chapter_summaries"]
                assert len(summaries) == 3
        before = fake.call_count
        result = await service.edit_chapter("author", novel_id, 1, service.Manuscript(body="更早一章的改稿"))
        assert not result["rearchiving"] and "stale" in result["message"]
        assert fake.call_count == before
        assert [item["status"] for item in (await service.detail("author", novel_id))["chapters"]] == ["done", "stale", "stale"]
    asyncio.run(scenario())


def test_global_slot_queue_and_user_delete_cancels_worker(monkeypatch, tmp_path):
    async def scenario():
        monkeypatch.setenv("FIONA_NOVEL_MAX_RUNNING", "3")
        entered = []
        release = asyncio.Event()
        async def blocking(call, index):
            if call["task"] == "setup":
                entered.append(call)
                await release.wait()
        await prepare(monkeypatch, tmp_path, FakeLLM(blocking))
        books = []
        for index in range(4):
            username = f"user{index}"
            await database.get_or_create_user(username)
            books.append((await service.create(username, request()))["id"])
        for _ in range(100):
            if len(entered) == 3:
                break
            await asyncio.sleep(.005)
        assert len(entered) == 3
        assert (await service.detail("user3", books[3]))["status"] == "setup_running"
        result = await database.delete_account_data("user0")
        assert result["deleted"]
        for _ in range(100):
            if len(entered) == 4:
                break
            await asyncio.sleep(.005)
        assert len(entered) == 4
        release.set()
        for novel_id in books:
            await drain(novel_id)
        async with get_db() as db:
            for table in ("novels", "novel_steps", "novel_chapters", "novel_bible_versions", "novel_notes"):
                async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE username='user0'") as cursor:
                    assert (await cursor.fetchone())[0] == 0
        assert not runner.TASKS
    asyncio.run(scenario())


def test_daily_cap_pauses_after_committing_accepted_chapter(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path)
        hits = []
        def cap(kind, username):
            hits.append((kind, username))
            return object()
        monkeypatch.setattr(runner, "check_daily_cap", cap)
        book = await create_book(request())
        await service.approve_setup("author", book["id"], service.SetupApproval())
        await drain(book["id"])
        book = await service.detail("author", book["id"])
        assert (book["status"], book["pause_reason"], book["chapters_done"], book["bible_version"]) == ("paused", "daily_cap", 1, 3)
        assert hits == [("novel_chapter", "author")]
    asyncio.run(scenario())


@pytest.mark.parametrize("condition", ["locked_conflict", "review_unresolved"])
def test_archive_conflict_pauses_but_unresolved_review_does_not(monkeypatch, tmp_path, condition):
    async def scenario():
        baseline = FakeLLM()
        def script(call, index):
            if condition == "locked_conflict" and call["task"] == "archive":
                archive = baseline.default_response(call)
                archive["locked_conflicts"] = ["人物外形与锁定设定冲突"]
                return archive
            if condition == "review_unresolved" and call["task"] == "review":
                body = FakeLLM.payload(call)["body"]
                evidence = next(line for line in body.splitlines() if "倒计时" in line)
                return {"issues": [{"category": "continuity", "problem": "与锁定时间线冲突",
                    "evidence": evidence, "fix": "核对时间线", "blocking": True}]}
        await prepare(monkeypatch, tmp_path, FakeLLM(script))
        book = await create_book(request(chapters=2))
        await service.approve_setup("author", book["id"], service.SetupApproval())
        await drain(book["id"])
        book = await service.detail("author", book["id"])
        first = await service.chapter("author", book["id"], 1)
        assert condition in first["flags"]
        if condition == "locked_conflict":
            assert (book["status"], book["pause_reason"], book["chapters_done"]) == ("paused", "locked_conflict", 1)
        else:
            assert (book["status"], book["chapters_done"]) == ("awaiting_end", 2)
            assert len(first["review"]) == 3
    asyncio.run(scenario())


def test_failed_restart_records_recovery_reason(monkeypatch, tmp_path):
    async def scenario():
        await prepare(monkeypatch, tmp_path, FakeLLM({"setup": ["invalid", "invalid"]}))
        config = request().model_dump()
        async with get_db() as db:
            await db.execute("INSERT INTO novels(id,username,seed_idea,status,config_json,budget_strawberries,run_token) "
                             "VALUES('restart','author','seed','setup_running',?,100000,'dead')", (json.dumps(config),))
            await db.commit()
        await runner.recover_interrupted_novels()
        await drain("restart")
        book = await service.detail("author", "restart")
        assert (book["status"], book["pause_reason"]) == ("paused", "server_restart_failed")
        assert book["chapters_done"] == 0 and book["reserved_strawberries"] == 0
    asyncio.run(scenario())


def test_rearchive_at_tenth_chapter_regenerates_arc_and_character_metadata(monkeypatch, tmp_path):
    async def scenario():
        fake = await prepare(monkeypatch, tmp_path)
        book = await create_book(request(chapters=10))
        novel_id = book["id"]
        await service.approve_setup("author", novel_id, service.SetupApproval())
        await drain(novel_id)
        before = fake.call_count
        await service.edit_chapter("author", novel_id, 10, service.Manuscript(body="# 第10章 改稿\n主角亲手交出原始录像。"))
        await drain(novel_id)
        assert fake.call_count == before + 2
        assert [call["task"] for call in fake.calls[-2:]] == ["archive", "arc_summary"]
        async with get_db() as db:
            async with db.execute("SELECT bible_json FROM novel_bible_versions ORDER BY version DESC LIMIT 1") as cursor:
                bible = json.loads((await cursor.fetchone())[0])
        assert len(bible["dynamic"]["arc_summaries"]) == 1
        assert bible["dynamic"]["arc_summaries"][0]["end_chapter"] == 10
        assert bible["dynamic"]["chapter_summaries"][-1]["characters"] == ["C1"]
        assert bible["dynamic"]["character_states"]["C1"]["last_seen_chapter"] == 10
    asyncio.run(scenario())


def test_recovery_without_workshop_schema_is_noop(monkeypatch, tmp_path):
    async def scenario():
        monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "uninitialized.db"))
        await runner.recover_interrupted_novels()
        async with get_db() as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='novels'") as cursor:
                assert await cursor.fetchone() is None
    asyncio.run(scenario())


def test_final_chapter_locked_conflict_resumes_into_end_gate_without_new_calls(monkeypatch, tmp_path):
    async def scenario():
        baseline = FakeLLM()
        def script(call, index):
            if call["task"] == "archive":
                result = baseline.default_response(call)
                result["locked_conflicts"] = ["人物外形与锁定设定冲突"]
                return result
        fake = await prepare(monkeypatch, tmp_path, FakeLLM(script))
        book = await create_book(request(chapters=1))
        novel_id = book["id"]
        await service.approve_setup("author", novel_id, service.SetupApproval())
        await drain(novel_id)
        book = await service.detail("author", novel_id)
        assert (book["status"], book["pause_reason"], book["chapters_done"]) == ("paused", "locked_conflict", 1)
        chapter = await service.chapter("author", novel_id, 1)
        assert chapter["ending_status"] == "end" and "locked_conflict" in chapter["flags"]
        calls, version = fake.call_count, book["bible_version"]
        await service.transition("author", novel_id, "resume")
        await drain(novel_id)
        book = await service.detail("author", novel_id)
        assert (book["status"], book["pause_reason"], book["chapters_done"], book["bible_version"]) == ("awaiting_end", None, 1, version)
        assert fake.call_count == calls
    asyncio.run(scenario())


def test_edit_rechecks_latest_after_worker_commits_while_cancel_drains(monkeypatch, tmp_path):
    """The next chapter's canonical archive must survive the edit/cancel race."""
    async def scenario():
        at_archive = asyncio.Event()
        finish_archive = asyncio.Event()
        async def script(call, index):
            if call['task']=='archive' and call['chapter']==2:
                at_archive.set()
                await finish_archive.wait()
        await prepare(monkeypatch,tmp_path,FakeLLM(script))
        book=await create_book(request(automation='per_batch',chapters=3,batch=1))
        novel_id=book['id']
        await service.approve_setup('author',novel_id,service.SetupApproval())
        await drain(novel_id)
        await service.transition('author',novel_id,'continue')
        await asyncio.wait_for(at_archive.wait(),5)
        assert (await service.detail('author',novel_id))['chapters_done']==1
        original_cancel=runner.cancel_novel
        committed={}
        async def finish_then_cancel(book_id,username):
            finish_archive.set()
            await drain(book_id)
            committed.update(await service.detail(username,book_id))
            await original_cancel(book_id,username)
        monkeypatch.setattr(runner,'cancel_novel',finish_then_cancel)
        result=await service.edit_chapter('author',novel_id,1,service.Manuscript(body='作者改写第一章。'))
        assert not result['rearchiving'] and 'stale' in result['message']
        after=await service.detail('author',novel_id)
        assert after['chapters_done']==2
        assert after['bible_version']==committed['bible_version']
        assert after['bible']==committed['bible']
        assert after['bible']['dynamic']['chapter_summaries'][-1]['chapter']==2
        assert (await service.chapter('author',novel_id,2))['status']=='stale'
        assert not after['config'].get('_rearchive')
        assert not runner.TASKS
    asyncio.run(scenario())


def test_edit_waits_for_claimed_worker_to_be_registered_before_cancelling(monkeypatch,tmp_path):
    from contextlib import asynccontextmanager
    async def scenario():
        await prepare(monkeypatch,tmp_path)
        book=await create_book(request(automation='per_batch',chapters=2,batch=1))
        novel_id=book['id']
        await service.approve_setup('author',novel_id,service.SetupApproval())
        await drain(novel_id)
        async with get_db() as db:
            await db.execute("UPDATE novels SET status='running',run_token=NULL WHERE id=?",(novel_id,))
            await db.commit()
        claimed=asyncio.Event(); finish_close=asyncio.Event()
        real_get_db=runner.get_db
        @asynccontextmanager
        async def db_with_delayed_close():
            async with real_get_db() as db:
                yield db
                if not claimed.is_set():
                    current=await service.row(db,'SELECT run_token FROM novels WHERE id=?',(novel_id,))
                    if current and current['run_token'] and novel_id not in runner.TASKS:
                        claimed.set()
                        await finish_close.wait()
        monkeypatch.setattr(runner,'get_db',db_with_delayed_close)
        activation=asyncio.create_task(runner.start_novel(novel_id,'author'))
        await asyncio.wait_for(claimed.wait(),5)
        observed=[]
        real_cancel=runner.cancel_novel
        async def recorded_cancel(book_id,username):
            observed.append(runner.TASKS.get(book_id))
            await real_cancel(book_id,username)
        monkeypatch.setattr(runner,'cancel_novel',recorded_cancel)
        edit=asyncio.create_task(service.edit_chapter('author',novel_id,1,service.Manuscript(body='提交令牌后暂停启动，改稿仍需等到任务登记。')))
        for _ in range(10): await asyncio.sleep(0)
        assert not runner.is_editing(novel_id) and not observed
        finish_close.set()
        original_worker=await activation
        await edit; await drain(novel_id)
        assert observed==[original_worker]
        assert original_worker.done()
        after=await service.detail('author',novel_id)
        assert (after['status'],after['chapters_done'],after['reserved_strawberries'])==('awaiting_end',2,0)
        assert not runner.TASKS
    asyncio.run(scenario())


@pytest.mark.parametrize('action,state',[('resume','paused'),('continue','awaiting_review')])
def test_edit_blocks_activation_until_worker_has_drained(monkeypatch,tmp_path,action,state):
    from fastapi import HTTPException
    async def scenario():
        await prepare(monkeypatch,tmp_path)
        book=await create_book(request(automation='per_batch',chapters=2,batch=1))
        novel_id=book['id']
        await service.approve_setup('author',novel_id,service.SetupApproval())
        await drain(novel_id)
        if state=='paused':
            await service.transition('author',novel_id,'pause')
        entered=asyncio.Event(); release=asyncio.Event()
        original_cancel=runner.cancel_novel
        async def blocking_cancel(book_id,username):
            entered.set(); await release.wait()
            await original_cancel(book_id,username)
        monkeypatch.setattr(runner,'cancel_novel',blocking_cancel)
        edit=asyncio.create_task(service.edit_chapter('author',novel_id,1,service.Manuscript(body='改稿期间不得重新拉起。')))
        await asyncio.wait_for(entered.wait(),5)
        with pytest.raises(HTTPException) as caught:
            await service.transition('author',novel_id,action)
        assert caught.value.status_code==409 and '改稿' in caught.value.detail
        assert await runner.start_novel(novel_id,'author') is None
        release.set(); await edit; await drain(novel_id)
        assert not runner.is_editing(novel_id)
        assert (await service.detail('author',novel_id))['status']==state
    asyncio.run(scenario())


@pytest.mark.parametrize('recovery',['reenable','platform'])
def test_byok_disabled_mid_run_pauses_and_reenabled_resume_reuses_steps(monkeypatch,tmp_path,recovery):
    from novel.byok_bridge import ByokBridge
    async def scenario():
        await prepare(monkeypatch,tmp_path)
        enabled=True
        disabled_once=False
        fake=FakeLLM()
        async def public(username):
            return {'provider':'dashscope','model':'qwen3.8-max','enabled':enabled,'status':'ok'}
        async def internal(username):
            return {**await public(username),'api_key':'OFFLINE-TEST-KEY'}
        monkeypatch.setattr('byok.store.get_public_config',public)
        monkeypatch.setattr('byok.store.get_internal_config',internal)
        def factory(store,username,novel_id,token):
            bridge=ByokBridge(username)
            router=LLMRouter(store,fake=fake,billing=NovelBilling(username,novel_id,token),byok_bridge=bridge)
            async def offline_call(call):
                nonlocal enabled,disabled_once
                if call['task']=='write' and not disabled_once:
                    enabled=False; disabled_once=True
                if call['model']=='byok:self':
                    resolved=await bridge.resolve()
                    resolved.clear()
                answer,_=await fake(call)
                return answer,{'input_tokens':100,'output_tokens':50,'cached_tokens':0},'stop'
            router._single_real_call=offline_call
            return router
        monkeypatch.setattr(runner,'router_factory',factory)
        data=request(chapters=2)
        data.agents={role:'byok:self' for role in data.agents}
        book=await create_book(data)
        novel_id=book['id']
        await service.approve_setup('author',novel_id,service.SetupApproval())
        await drain(novel_id)
        paused=await service.detail('author',novel_id)
        assert (paused['status'],paused['pause_reason'])==('paused','byok_unavailable')
        assert paused['last_error']=='请先启用可用的自带模型'
        assert paused['chapters_done']==0 and paused['reserved_strawberries']==0
        if recovery=='reenable':
            enabled=True
        else:
            await service.patch('author',novel_id,service.PatchNovel(agents=request().agents))
        await service.transition('author',novel_id,'resume')
        await drain(novel_id)
        done=await service.detail('author',novel_id)
        assert (done['status'],done['chapters_done'],done['last_error'])==('awaiting_end',2,None)
        counts=Counter(call['step_key'] for call in fake.calls)
        assert counts['setup/steps/00-setup-editor.json']==1
        assert counts['arm-solo/ch001/03-decision-editor.json']==1
        assert counts['arm-solo/ch001/04-write-writer-r0-a0.json']==1
        assert done['spent_strawberries']==0
    asyncio.run(scenario())
