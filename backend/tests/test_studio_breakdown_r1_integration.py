"""R1 公共接缝：历史快照、局部线程边界与四位预算提示。"""
import asyncio
from decimal import Decimal
import threading

from fastapi import HTTPException
import pytest

from studio import brain_jobs, breakdown, recovery, sources, spend, storage, store
from test_studio_breakdown_pipeline import OWNER, TEXT, pipeline


def run(coro):
    return asyncio.run(coro)


def test_read_bound_snapshot_uses_its_own_revision_and_worker(pipeline, monkeypatch):
    pid = pipeline['id']
    changed = '阿青在黎明走进书房，决定留下另一封信。'
    main_thread = threading.get_ident()
    observed = []
    original_manifest, original_chunks = sources._read_manifest, sources._read_snapshot_chunks

    def manifest(*args):
        observed.append(threading.get_ident())
        return original_manifest(*args)

    def chunks(*args):
        observed.append(threading.get_ident())
        return original_chunks(*args)

    monkeypatch.setattr(sources, '_read_manifest', manifest)
    monkeypatch.setattr(sources, '_read_snapshot_chunks', chunks)

    async def scenario():
        snapshot = await sources.take_text_snapshot(OWNER, 'paste', '旧灯', changed)
        await sources._save_snapshot(OWNER, pid, 2, snapshot, 1)
        assert (await sources.read_snapshot_at(OWNER, pid, 1, 1, 1))[0]['body'] == TEXT
        assert (await sources.read_snapshot_at(OWNER, pid, 2, 1, 1))[0]['body'] == changed
        assert (await sources.read_snapshot(OWNER, pid, 1, 1))[0]['body'] == changed
        for owner, number in [('another-owner', 1), (OWNER, 3)]:
            with pytest.raises(HTTPException) as error:
                await sources.read_snapshot_at(owner, pid, number, 1, 1)
            assert error.value.status_code == 404

    run(scenario())
    assert observed and all(identifier != main_thread for identifier in observed)


def test_bound_snapshot_reader_still_verifies_body_hash(pipeline):
    pid = pipeline['id']
    path = storage.resolve_path(f'{pid}/source/snap-0001/chapters/0001.md')
    path.write_text('被改变的测试快照。', encoding='utf-8')
    with pytest.raises(HTTPException) as error:
        run(sources.read_snapshot_at(OWNER, pid, 1, 1, 1))
    assert error.value.status_code == 500


def test_ordinary_store_queries_do_not_dispatch_worker_for_each_read(pipeline, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('常规 store 查询不应全局切换到线程')

    async def scenario():
        async with store.connection() as db:
            with monkeypatch.context() as patch:
                patch.setattr(asyncio, 'to_thread', forbidden)
                row = await store._one(db, "SELECT '{\"n\":1}' AS params_json")
                rows = await store._many(db, "SELECT '{\"n\":2}' AS params_json")
            assert row['params'] == {'n': 1} and rows[0]['params'] == {'n': 2}

    run(scenario())


@pytest.mark.parametrize('setting,totals,expected', [
    ('FIONA_STUDIO_MAX_QUOTE_CNY', {'CNY': Decimal('1.23456789')}, '超过单次报价上限 ¥1.0000，超出 ¥0.2346'),
    ('FIONA_STUDIO_DAILY_CNY', {'CNY': Decimal('1.23456789')}, '今日额度不足，剩余额度 ¥1.0000，还差 ¥0.2346'),
    ('FIONA_STUDIO_BRAIN_MONTHLY_USD', {'USD': Decimal('1.23456789')}, 'Claude 本月额度不足，剩余额度 $1.0000，还差 $0.2346'),
])
def test_director_budget_messages_use_four_decimal_places(pipeline, monkeypatch, setting, totals, expected):
    monkeypatch.setenv(setting, '1')

    async def scenario():
        async with store.connection() as db:
            with pytest.raises(HTTPException) as error:
                await spend.check_brain_budget(db, OWNER, totals)
            assert error.value.status_code == 409 and error.value.detail == expected

    run(scenario())


@pytest.mark.parametrize('corrupt', ['job', 'breakdown'])
def test_corrupted_running_breakdown_cannot_block_other_recovery(pipeline, caplog, corrupt):
    secret = 'PRIVATE_BROKEN_TEST_INPUT'

    async def scenario():
        first_quote = await breakdown.quote(pipeline['id'], OWNER)
        first = await breakdown.start(pipeline['id'], OWNER, first_quote['id'])
        other = await sources.create_text_project(OWNER, 'paste', '另一封信', '阿青在门房等候同伴，一同送还旧书。')
        await brain_jobs.patch_project(other['id'], OWNER, 'qwen')
        second_quote = await breakdown.quote(other['id'], OWNER)
        second = await breakdown.start(other['id'], OWNER, second_quote['id'])
        bad_id, good_id = first['chunks'][0]['job_id'], second['chunks'][0]['job_id']
        async with store.connection(transaction=True) as db:
            await db.execute("UPDATE studio_jobs SET status='running' WHERE id=?", (bad_id,))
            if corrupt == 'job':
                await db.execute('UPDATE studio_jobs SET params_json=? WHERE id=?', ('{' + secret, bad_id))
            else:
                await db.execute('UPDATE studio_breakdowns SET import_json=? WHERE id=?', ('{' + secret, first['id']))
            await db.execute("UPDATE studio_jobs SET status='running' WHERE id=?", (good_id,))
        # Both the initial running->uncertain pass and per-breakdown refresh are isolated.
        await recovery.recover_studio_jobs()
        assert (await store.get_job(good_id))['status'] == 'uncertain'
        failed_id = bad_id if corrupt == 'job' else first['id']
        assert any(record.levelname in {'ERROR', 'WARNING'} and failed_id in record.message
                   for record in caplog.records)
        assert secret not in caplog.text

    run(scenario())


def test_quote_json_size_does_not_grow_with_source_body_length(pipeline):
    async def scenario():
        sizes = []
        for length in (200, 10000):
            text = ('自写原文大小哨兵。' * length)[:length]
            project = await sources.create_text_project(OWNER, 'paste', '报价大小', text)
            await brain_jobs.patch_project(project['id'], OWNER, 'qwen')
            quote = await breakdown.quote(project['id'], OWNER)
            async with store.connection() as db:
                async with db.execute('SELECT items_json FROM studio_quotes WHERE id=?', (quote['id'],)) as cursor:
                    payload = (await cursor.fetchone())[0]
            assert text not in payload
            sizes.append(len(payload.encode('utf-8')))
        # Both snapshots have one source block, so only numeric range/price
        # metadata can grow; the extra 9,800 source characters stay on disk.
        assert abs(sizes[1] - sizes[0]) < 512
        assert max(sizes) < 6000

    run(scenario())


def test_start_rejects_snapshot_change_without_confirming_or_reserving(pipeline):
    async def scenario():
        quote = await breakdown.quote(pipeline['id'], OWNER)
        async with store.connection(transaction=True) as db:
            await db.execute('UPDATE studio_projects SET snapshot_no=2 WHERE id=?', (pipeline['id'],))
        with pytest.raises(HTTPException) as error:
            await breakdown.start(pipeline['id'], OWNER, quote['id'])
        assert error.value.status_code == 409 and '快照已更新' in error.value.detail
        async with store.connection() as db:
            assert (await store._one(db, 'SELECT status FROM studio_quotes WHERE id=?', (quote['id'],)))['status'] == 'open'
            assert (await store._one(db, 'SELECT count(*) AS n FROM studio_jobs'))['n'] == 0
            assert (await store._one(db, 'SELECT count(*) AS n FROM studio_breakdowns'))['n'] == 0

    run(scenario())
