"""WO3c R1：费用清理、惰性原文、只读轮询、定位与恢复容错。"""
import asyncio
from contextlib import asynccontextmanager
import json
import threading

from fastapi import HTTPException
import pytest

from studio import brain, brain_jobs, breakdown, sources, spend, store
from studio.breakdown_material import locate_scenes
from test_studio_breakdown_pipeline import OWNER, TEXT, MODELS, pipeline, run, fake, drain, output


@pytest.mark.parametrize('finish', ['done', 'cancelled'])
def test_unchanged_get_is_zero_writes_and_preserves_timestamps(pipeline, monkeypatch, finish):
    fake(monkeypatch)
    async def scenario():
        quoted = await breakdown.quote(pipeline['id'], OWNER)
        current = await breakdown.start(pipeline['id'], OWNER, quoted['id'])
        current = await drain(pipeline['id']) if finish == 'done' else await breakdown.cancel(current['id'], OWNER)
        original = store.connection
        mutations = []
        @asynccontextmanager
        async def connection(**kwargs):
            async with original(**kwargs) as db:
                await db.set_trace_callback(lambda statement: mutations.append(statement.split()[0])
                    if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) else None)
                yield db
        monkeypatch.setattr(store, 'connection', connection)
        before = await breakdown.get_current(pipeline['id'], OWNER)
        async with original() as db:
            before_rows = await breakdown._many(db, 'SELECT id,updated_at FROM studio_breakdowns WHERE id=?', (current['id'],))
            bible_before = await breakdown._many(db, 'SELECT id,updated_at FROM studio_bible WHERE breakdown_id=?', (current['id'],))
        after = await breakdown.get_current(pipeline['id'], OWNER)
        assert before == after and mutations == []
        async with original() as db:
            assert await breakdown._many(db, 'SELECT id,updated_at FROM studio_breakdowns WHERE id=?', (current['id'],)) == before_rows
            assert await breakdown._many(db, 'SELECT id,updated_at FROM studio_bible WHERE breakdown_id=?', (current['id'],)) == bible_before
    run(scenario())


def test_quote_and_source_are_text_free_and_execution_reads_locked_snapshot(pipeline, monkeypatch):
    calls = fake(monkeypatch)
    original = sources.read_snapshot_at
    reads = []
    async def read(owner, pid, snapshot_no, first, last):
        reads.append((snapshot_no, first, last))
        assert threading.current_thread() is threading.main_thread()
        return await original(owner, pid, snapshot_no, first, last)
    monkeypatch.setattr(sources, 'read_snapshot_at', read)
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        async with store.connection() as db:
            quoted = await breakdown._one(db, 'SELECT items_json FROM studio_quotes WHERE id=?', (quote['id'],))
        assert TEXT not in quoted['items_json']
        payload = json.loads(quoted['items_json'])
        assert 'manifest' not in payload and 'imported' not in payload
        assert all('inputs' not in chunk and 'body' not in json.dumps(chunk) for chunk in payload['plan'])
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        async with store.connection() as db:
            chunks = await breakdown._chunks(db, current['id'])
            jobs = await breakdown._many(db, 'SELECT * FROM studio_jobs WHERE group_id=?', (current['id'],))
        assert all('_inputs' not in chunk['source'] and TEXT not in chunk['source_json'] for chunk in chunks)
        assert all(job['params']['inputs'] == {} for job in jobs)
        assert reads and reads[-1][0] == 1
        reads.clear()
        async with store.connection(transaction=True) as db:
            # Simulate an externally changed current pointer. The job still reads
            # the retained snapshot it was quoted against.
            await db.execute('UPDATE studio_projects SET snapshot_no=2 WHERE id=?', (pipeline['id'],))
        await brain_jobs._background(current['chunks'][0]['job_id'])
        assert calls[0]['inputs']['text'] == TEXT and reads == [(1, 1, 1)]
        async with store.connection() as db:
            chunk = (await breakdown._chunks(db, current['id']))[0]
            job = await breakdown._job(db, chunk['job_id'])
        assert '_inputs' not in chunk['source'] and TEXT not in chunk['source_json']
        assert job['params']['inputs']['text'] == TEXT
    run(scenario())


def failing_provider(monkeypatch, status):
    class Adapter:
        model = MODELS['qwen']
        async def call(self, task, inputs, **kwargs):
            raise brain.BrainProviderError(status, 'offline_failure', '离线失败',
                                          usage={'input_tokens': 50, 'output_tokens': 20} if status == 'failed' else None,
                                          model=self.model)
    async def adapter(*args, **kwargs):
        return Adapter()
    monkeypatch.setattr(brain, 'get_provider', adapter)


def test_restart_cancels_old_unexecuted_reservations_keeps_settled_cost_and_results(pipeline, monkeypatch):
    failing_provider(monkeypatch, 'failed')
    async def scenario():
        first_quote = await breakdown.quote(pipeline['id'], OWNER)
        first = await breakdown.start(pipeline['id'], OWNER, first_quote['id'])
        first = await drain(pipeline['id'])
        assert first['status'] == 'partial'
        async with store.connection() as db:
            old_before = await breakdown._many(db, 'SELECT * FROM studio_jobs WHERE group_id=?', (first['id'],))
            old_cost = sum(float(job.get('actual_amount') or 0) for job in old_before)
        second_quote = await breakdown.quote(pipeline['id'], OWNER)
        second = await breakdown.start(pipeline['id'], OWNER, second_quote['id'])
        async with store.connection() as db:
            old = await breakdown._breakdown(db, first['id'], OWNER)
            old_jobs = await breakdown._many(db, 'SELECT * FROM studio_jobs WHERE group_id=?', (first['id'],))
            old_chunks = await breakdown._chunks(db, first['id'])
        assert old['status'] == 'cancelled'
        assert old['superseded_by'] == second['id']
        assert all(job['status'] != 'queued' and float(job['reserved_amount']) == 0 for job in old_jobs)
        assert [chunk['status'] for chunk in old_chunks] == ['failed', 'cancelled', 'cancelled']
        assert (await spend.today())['committed_cny'] == pytest.approx(second_quote['total_max'] + old_cost)
        assert second['id'] != first['id']
    run(scenario())


def test_restart_uncertain_rejected_before_any_mutation_and_quote_stays_open(pipeline, monkeypatch):
    failing_provider(monkeypatch, 'uncertain')
    async def scenario():
        first_quote = await breakdown.quote(pipeline['id'], OWNER)
        first = await breakdown.start(pipeline['id'], OWNER, first_quote['id'])
        first = await drain(pipeline['id'])
        second_quote = await breakdown.quote(pipeline['id'], OWNER)
        async with store.connection() as db:
            before = await breakdown._many(db, 'SELECT id,status,reserved_amount,updated_at FROM studio_jobs WHERE group_id=?', (first['id'],))
        with pytest.raises(HTTPException) as rejected:
            await breakdown.start(pipeline['id'], OWNER, second_quote['id'])
        assert rejected.value.status_code == 409 and '核账释放' in rejected.value.detail
        async with store.connection() as db:
            quote = await breakdown._one(db, 'SELECT status FROM studio_quotes WHERE id=?', (second_quote['id'],))
            assert quote['status'] == 'open'
            assert await breakdown._many(db, 'SELECT id,status,reserved_amount,updated_at FROM studio_jobs WHERE group_id=?', (first['id'],)) == before
        assert (await store.get_project(pipeline['id'], OWNER))['breakdown_id'] == first['id']
    run(scenario())


@pytest.mark.parametrize('anchors,expected', [
    (['甲场', '乙场', '不存在'], [(0, 5), (5, 10), (10, 10)]),
    (['不存在', '乙场'], [(5, 5), (5, 10)]),
    (['不存在', '也不存在'], [(10, 10), (10, 10)]),
    (['甲场', '不存在', '乙场'], [(0, 5), (5, 5), (5, 10)]),
])
def test_missing_anchors_use_next_match_or_block_end(anchors, expected):
    scenes, warnings = locate_scenes('甲场文字。乙场文字。', [{'start_anchor': anchor} for anchor in anchors])
    assert [(scene['start'], scene['end']) for scene in scenes] == expected
    assert warnings


def test_recovery_skips_one_bad_breakdown_and_continues(pipeline, monkeypatch, caplog):
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        first = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        async with store.connection(transaction=True) as db:
            await db.execute('INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                             ('second', pipeline['id'], OWNER, 1, 'qwen', 'partial', store.utcnow(), store.utcnow()))
        calls = []
        async def refresh(bid, owner, *, dispatch):
            calls.append(bid)
            assert dispatch is False
            if len(calls) == 1:
                raise HTTPException(422, 'sensitive source text must not be logged')
        monkeypatch.setattr(breakdown, 'refresh', refresh)
        await breakdown.recover()
        assert set(calls) == {first['id'], 'second'}
        assert 'HTTPException' in caplog.text and 'sensitive source' not in caplog.text
    run(scenario())


def test_material_warnings_belong_to_the_source_batch(pipeline, monkeypatch):
    class Adapter:
        model = MODELS['qwen']
        async def call(self, task, inputs, **kwargs):
            result = output(task, inputs)
            if task == 'text_map' and inputs['block_no'] == 2:
                result['scenes'].append({**result['scenes'][0], 'start_anchor': '原文里根本不存在的句子'})
                result['characters'][0]['excerpt'] = '模型编造的外形'
            return brain.BrainReply(json.dumps(result), {'input_tokens': 50, 'output_tokens': 20}, self.model, 'stop')
    async def provider(*args, **kwargs):
        return Adapter()
    monkeypatch.setattr(brain, 'get_provider', provider)
    async def scenario():
        project = await sources.create_text_project(OWNER, 'paste', '两个院子', '第1章 灯\n' + TEXT + '\n第2章 门\n' + TEXT)
        await brain_jobs.patch_project(project['id'], OWNER, 'qwen')
        quote = await breakdown.quote(project['id'], OWNER)
        current = await breakdown.start(project['id'], OWNER, quote['id'])
        current = await drain(project['id'])
        maps = [chunk for chunk in current['chunks'] if chunk['task'] == 'text_map']
        assert len(maps) == 2 and maps[0]['warnings'] == []
        assert any('未命中' in warning for warning in maps[1]['warnings'])
        assert any('摘录' in warning for warning in maps[1]['warnings'])
        assert maps[1]['status'] == 'succeeded'
    run(scenario())


def test_restart_checks_uncertain_older_attempt_even_when_latest_is_released(pipeline, monkeypatch):
    failing_provider(monkeypatch, 'uncertain')
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        current = await drain(pipeline['id'])
        async with store.connection(transaction=True) as db:
            chunk = (await breakdown._chunks(db, current['id']))[0]
            item = chunk['source']['_item']
            job = await breakdown._new_chunk_job(db, current['id'], chunk['id'], pipeline['id'], OWNER, item, {}, quote['id'])
            await brain_jobs.transition(db, job, 'queued', {'status': 'rejected'})
            await db.execute("UPDATE studio_chunks SET job_id=?,status='rejected' WHERE id=?", (job['id'], chunk['id']))
        second_quote = await breakdown.quote(pipeline['id'], OWNER)
        with pytest.raises(HTTPException) as rejected:
            await breakdown.start(pipeline['id'], OWNER, second_quote['id'])
        assert rejected.value.status_code == 409 and '核账' in rejected.value.detail
    run(scenario())


def test_quote_draft_seconds_does_not_change_project_until_confirmed(pipeline):
    async def scenario():
        before = await store.get_project(pipeline['id'], OWNER)
        quote = await breakdown.quote(pipeline['id'], OWNER, episode_seconds_min=120, episode_seconds_max=150)
        assert quote['settings']['episode_seconds_min'] == 120
        after = await store.get_project(pipeline['id'], OWNER)
        assert after['episode_seconds_min'] == before['episode_seconds_min'] == 180
        assert after['plan_revision'] == before['plan_revision']
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        project = await store.get_project(pipeline['id'], OWNER)
        assert project['episode_seconds_min'] == current['settings']['episode_seconds_min'] == 120
        assert project['episode_seconds_max'] == 150 and project['plan_revision'] == 0
    run(scenario())
