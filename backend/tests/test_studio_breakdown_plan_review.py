"""WO3c 独立复核：跨批 canonical 合并与作者修改的集成回归。"""
from studio import breakdown, breakdown_plan, store
from test_studio_breakdown_pipeline import OWNER, pipeline, run


def entity(name, aliases=(), **fields):
    return {'kind': 'character', 'name': name, 'aliases': list(aliases), 'role': '初始定位',
            'description': '原先描述', 'appearance': '', 'appearance_source': 'none',
            'excerpt': '', 'needs_author': True, 'first_unit': None, **fields}


async def insert(bid, entities):
    async with store.connection(transaction=True) as db:
        current = await breakdown._breakdown(db, bid, OWNER)
        await breakdown._insert_bible(db, current, entities)


async def stored(bid):
    async with store.connection() as db:
        return await store._many(db, 'SELECT * FROM studio_bible WHERE breakdown_id=? ORDER BY name', (bid,))


def test_later_earlier_batch_absorbs_previous_generated_canonical(pipeline):
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        bid = current['id']
        # Batch 2 finishes before batch 1, so its temporary canonical ID exists first.
        await insert(bid, [entity('乙')])
        old = (await stored(bid))[0]
        # Once batch 1 also completes, deterministic merge chooses its earlier name.
        await insert(bid, [entity('甲', ['乙'])])
        rows = await stored(bid)
        active = [row for row in rows if not row['archived'] and row['merged_into'] is None]
        assert len(active) == 1
        assert active[0]['name'] == '甲'
        old_after = next(row for row in rows if row['id'] == old['id'])
        if old_after['id'] != active[0]['id']:
            assert old_after['merged_into'] == active[0]['id']
        # Nothing is physically deleted, including the old canonical row.
        assert old['id'] in {row['id'] for row in rows}
    run(scenario())


def test_cross_batch_canonical_merge_preserves_author_changes(pipeline):
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        bid = current['id']
        await insert(bid, [entity('乙')])
        old = (await stored(bid))[0]
        await breakdown_plan.patch_bible(old['id'], OWNER, {'role': '作者定位', 'description': ''})
        await insert(bid, [entity('甲', ['乙'], role='模型新定位', description='模型新描述')])
        rows = await stored(bid)
        active = [row for row in rows if not row['archived'] and row['merged_into'] is None]
        assert len(active) == 1
        assert active[0]['role'] == '作者定位'
        assert active[0]['description'] == ''
        # A later read/refresh must continue respecting the migrated edit markers.
        await insert(bid, [entity('甲', ['乙'], role='另一模型定位', description='另一模型描述')])
        rows = await stored(bid)
        active = [row for row in rows if not row['archived'] and row['merged_into'] is None]
        assert len(active) == 1 and active[0]['role'] == '作者定位' and active[0]['description'] == ''
    run(scenario())


def test_cancelling_running_batch_settles_first_call_without_new_paid_repair(pipeline, monkeypatch):
    import asyncio
    import json
    from studio import brain, brain_jobs
    from test_studio_breakdown_pipeline import MODELS, output
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        class Adapter:
            model = MODELS['qwen']
            async def call(self, task, inputs, images=None, repair=None):
                calls.append(repair)
                if repair is None:
                    entered.set()
                    await release.wait()
                    result = {}  # Original call is paid but fails schema validation.
                else:
                    result = output(task, inputs)
                return brain.BrainReply(json.dumps(result), {'input_tokens': 50, 'output_tokens': 20}, self.model, 'stop', .01)
        async def provider(*args, **kwargs):
            return Adapter()
        monkeypatch.setattr(brain, 'get_provider', provider)
        quote = await breakdown.quote(pipeline['id'], OWNER)
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        batch = current['chunks'][0]
        task = asyncio.create_task(brain_jobs._background(batch['job_id']))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            cancelled = await breakdown.cancel(current['id'], OWNER)
            assert cancelled['status'] == 'cancelled'
            release.set()
            await asyncio.wait_for(task, 5)
            assert calls == [None]
            async with store.connection() as db:
                attempts = await store._many(db, 'SELECT * FROM studio_jobs WHERE group_id=? AND task=?',
                                              (current['id'], 'text_map'))
            assert len(attempts) == 1
            assert attempts[0]['status'] == 'invalid_output'
            assert attempts[0]['actual_amount'] is not None and float(attempts[0]['reserved_amount']) == 0
            assert (await breakdown.get_current(pipeline['id'], OWNER))['status'] == 'cancelled'
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    run(scenario())


def test_manual_bible_merge_survives_later_generated_refresh(pipeline):
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        current = await breakdown.start(pipeline['id'], OWNER, quote['id'])
        bid = current['id']
        generated = [entity('甲', first_unit=2), entity('乙', first_unit=1)]
        await insert(bid, generated)
        rows = {row['name']: row for row in await stored(bid)}
        merged = await breakdown_plan.merge_bible(OWNER, rows['甲']['id'], [rows['乙']['id']])
        assert '乙' in merged['aliases'] and merged['first_unit'] == 1
        await insert(bid, generated)
        visible = await breakdown_plan.list_bible(pipeline['id'], OWNER)
        assert len(visible) == 1
        assert '乙' in visible[0]['aliases'] and visible[0]['first_unit'] == 1
    run(scenario())
