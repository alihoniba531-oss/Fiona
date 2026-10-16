"""WO3c 快照过期与 F4 项目建立时间排序。"""
import asyncio

from fastapi import HTTPException
import pytest

from studio import sources, store
from test_studio_sources import workshop, novel_project, sql


def run(coro):
    return asyncio.run(coro)


def seed_breakdown(pid, status='done'):
    sql('''INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)''', ('breakdown', pid, 'owner', 1, 'qwen', status, store.utcnow(), store.utcnow()))
    sql('UPDATE studio_projects SET breakdown_id=?,plan_revision=1,plan_approved_revision=1 WHERE id=?', ('breakdown', pid))


def test_snapshot_sync_marks_current_breakdown_outdated_keeps_g0(workshop):
    project = novel_project(workshop)
    seed_breakdown(project['id'])
    result = run(sources.sync_source('owner', project['id'], 1))
    assert result['snapshot']['no'] == 2
    assert sql('SELECT outdated FROM studio_breakdowns')[0][0] == 1
    assert sql('SELECT plan_revision,plan_approved_revision FROM studio_projects')[0] == (1, 1)


@pytest.mark.parametrize('chunk_status,job_status', [('blocked', 'queued'), ('queued', 'queued'), ('running', 'running')])
def test_breakdown_director_jobs_prevent_sync(workshop, monkeypatch, chunk_status, job_status):
    project = novel_project(workshop)
    pid = project['id']
    seed_breakdown(pid, 'running')
    # A blocked chunk already owns its queued job so its reservation survives dependencies.
    now = store.utcnow()
    sql('''INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,total_max_cny,
        params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
        ('quote', pid, 'owner', '[]', '0', '1', 'test', 'confirmed', now, now))
    sql('''INSERT INTO studio_jobs(id,project_id,owner,kind,provider,brain_provider,model,params_json,fingerprint,
        quote_id,quote_item_id,status,est_min_cny,est_max_cny,created_at,updated_at,confirmed_day,task)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        ('job', pid, 'owner', 'brain', 'wan', 'qwen', 'test', '{}', 'fp', 'quote', 'item', job_status,
         '0', '1', now, now, now[:10], 'novel_complete'))
    sql('''INSERT INTO studio_chunks(id,breakdown_id,project_id,owner,no,task,status,provider,job_id)
        VALUES(?,?,?,?,?,?,?,?,?)''', ('chunk', 'breakdown', pid, 'owner', 1, 'novel_complete', chunk_status, 'qwen', 'job'))
    original = sources.take_novel_snapshot
    calls = []
    async def record(*args):
        calls.append(True)
        return await original(*args)
    monkeypatch.setattr(sources, 'take_novel_snapshot', record)
    with pytest.raises(HTTPException) as exc:
        run(sources.sync_source('owner', pid, 1))
    assert exc.value.status_code == 409 and '导演模型任务进行中' in exc.value.detail
    assert calls == []
    assert sql('SELECT snapshot_no FROM studio_projects')[0][0] == 1


def test_f4_candidates_are_newest_first_with_created_at(workshop):
    first = novel_project(workshop)
    second = novel_project(workshop)
    sql('UPDATE studio_projects SET created_at=? WHERE id=?', ('2026-01-01T01:00:00+00:00', first['id']))
    sql('UPDATE studio_projects SET created_at=? WHERE id=?', ('2026-01-02T01:00:00+00:00', second['id']))
    candidates = run(sources.list_candidates('owner'))
    projects = candidates['books'][0]['projects']
    assert [row['id'] for row in projects] == [second['id'], first['id']]
    assert all(row['created_at'] for row in projects)
