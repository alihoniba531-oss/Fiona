"""WO3c 分集、总表与 revision 离线验收；所有夹具文本为自写。"""
import asyncio
import json
import threading
from urllib.parse import quote

import aiosqlite
import pytest

from studio import breakdown_plan as plan, store


def run(coro):
    return asyncio.run(coro)


def sql(query, args=()):
    async def execute():
        import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute(query, args)
            rows = await cursor.fetchall()
            await db.commit()
            return rows
    return run(execute())


@pytest.fixture
def project(client, monkeypatch):
    monkeypatch.setenv('FIONA_STUDIO', '1')
    monkeypatch.setenv('FIONA_STUDIO_OWNERS', 'owner,other')
    monkeypatch.setenv('FIONA_STUDIO_REQUIRE_JWT', '1')
    from auth import create_token
    from database import get_or_create_user
    auths = {}
    for username in ('owner', 'other'):
        account = run(get_or_create_user(username))
        auths[username] = {'Authorization': f"Bearer {create_token(username, account['session_version'])}"}
    row = client.post('/studio/projects', headers=auths['owner'], json={'title': '山月|新章', 'aspect': '16:9'}).json()
    pid = row['id']
    async def seed():
        async with store.connection(transaction=True) as db:
            now = store.utcnow()
            await db.execute('''INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,
                settings_json,import_json,synopsis_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                ('bid', pid, 'owner', 1, 'qwen', 'done', '{}', store._json({'foreshadowing': ['铜钥匙'], 'timeline': ['清晨']}),
                 store._json({'logline': '阿岚\n归来', 'synopsis': '灯亮了。', 'genre': '剧情', 'tone': '平静', 'themes': ['归乡']}), now, now))
            await db.execute('UPDATE studio_projects SET breakdown_id=?,snapshot_no=1,source_kind=? WHERE id=?', ('bid', 'paste', pid))
            for seq in range(1, 9):
                await db.execute('''INSERT INTO studio_units(breakdown_id,seq,label,chapter,scene_index,location,
                    summary,characters_json,est_seconds,change,start,end) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('bid', seq, f'第 {seq} 块 第 1 场', seq, 1, '院子', '阿岚拿起铜钥匙。',
                     '["阿岚"]' if seq % 2 else '["老魏"]', seq * 20, '门打开', (seq - 1) * 20, seq * 20))
            await db.execute('''INSERT INTO studio_bible(id,project_id,owner,breakdown_id,kind,name,aliases_json,
                role,appearance,excerpt,needs_author,first_unit,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                ('person', pid, 'owner', 'bid', 'character', '阿岚', '[]', '归人', '', '', 1, 1, now))
            await plan.publish_plan(db, 'bid', [
                {'unit_from': 1, 'unit_to': 2, 'title': '门*开', 'change': '得知去向', 'hook': '谁来敲门'},
                {'unit_from': 3, 'unit_to': 5, 'title': '灯亮', 'change': '决定留下', 'hook': '纸条'}])
    run(seed())
    return client, auths, pid


def get(project):
    client, auths, pid = project
    response = client.get(f'/studio/projects/{pid}/episodes', headers=auths['owner'])
    assert response.status_code == 200, response.text
    return response.json()


def op(project, data, revision=None):
    client, auths, pid = project
    revision = get(project)['plan_revision'] if revision is None else revision
    return client.post(f'/studio/projects/{pid}/episodes/ops', headers=auths['owner'],
                       json={'expected_revision': revision, **data})


def test_calculated_plan_and_unassigned(project):
    result = get(project)
    assert result['plan_revision'] == 1 and not result['g0_approved']
    assert result['episodes'][0]['est_seconds'] == 60
    assert result['episodes'][0]['est_shots'] == round(60 / 3.5)
    assert result['episodes'][0]['characters'] == ['阿岚', '老魏']
    assert result['episodes'][0]['warnings'] and '字符 0–40' in result['episodes'][0]['source_range']
    assert (result['unassigned'][0]['unit_from'], result['unassigned'][0]['unit_to']) == (6, 8)
    assert result['total_seconds'] == 300
    assert sql('SELECT episodes_json FROM studio_bible WHERE id=?', ('person',))[0][0] == '[1,2]'


def test_all_operations_revision_invariants_and_g0(project):
    client, auths, pid = project
    approve = client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 1})
    assert approve.status_code == 200 and approve.json()['g0_approved']
    response = op(project, {'op': 'edit', 'no': 1, 'fields': {'title': '归门', 'notes': '微风', 'target_min': 60, 'target_max': 100}})
    assert response.status_code == 200, response.text
    assert response.json()['plan_revision'] == 2 and not response.json()['g0_approved']
    assert response.json()['episodes'][0]['notes'] == '微风'
    response = op(project, {'op': 'merge', 'no': 1})
    assert response.status_code == 200 and response.json()['episodes'][0]['unit_to'] == 5
    assert response.json()['episodes'][0]['title'] == '归门；灯亮'
    response = op(project, {'op': 'split', 'no': 1, 'at_unit': 3})
    assert response.status_code == 200 and response.json()['episodes'][1]['title'].endswith('（下）')
    response = op(project, {'op': 'move_boundary', 'no': 1, 'delta': 1})
    assert response.status_code == 200
    assert [(item['unit_from'], item['unit_to']) for item in response.json()['episodes']] == [(1, 3), (4, 5)]
    assert op(project, {'op': 'move_boundary', 'no': 1, 'delta': -1}).status_code == 200
    response = op(project, {'op': 'delete', 'no': 2})
    assert response.status_code == 200 and response.json()['unassigned'][0]['unit_from'] == 3
    response = op(project, {'op': 'insert', 'unit_from': 3, 'unit_to': 8, 'title': '余下的路'})
    assert response.status_code == 200 and not response.json()['unassigned']
    assert [item['no'] for item in response.json()['episodes']] == [1, 2]
    assert response.json()['plan_revision'] == 8
    revisions = sql('SELECT revision,plan_json,created_reason FROM studio_plan_revisions ORDER BY revision')
    assert [row[0] for row in revisions] == list(range(1, 9))
    assert json.loads(revisions[0][1])['episodes'][0]['title'] == '门*开'
    assert op(project, {'op': 'delete', 'no': 1}, revision=1).status_code == 409
    assert client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 1}).status_code == 409


@pytest.mark.parametrize('data', [
    {'op': 'split', 'no': 1, 'at_unit': 1}, {'op': 'split', 'no': 1, 'at_unit': 3},
    {'op': 'merge', 'no': 2}, {'op': 'move_boundary', 'no': 2, 'delta': 1},
    {'op': 'insert', 'unit_from': 2, 'unit_to': 7}, {'op': 'insert', 'unit_from': 9, 'unit_to': 10},
    {'op': 'insert', 'unit_from': 8, 'unit_to': 6}, {'op': 'edit', 'no': 1, 'fields': {}},
    {'op': 'edit', 'no': 1, 'fields': {'target_min': 300, 'target_max': 100}},
    {'op': 'edit', 'no': 1, 'fields': {'title': None}},
])
def test_invalid_operations_roll_back(project, data):
    assert op(project, data).status_code == 422
    assert get(project)['plan_revision'] == 1
    assert sql('SELECT count(*) FROM studio_plan_revisions')[0][0] == 1


def test_boundary_cannot_empty_or_cross_gaps(project):
    assert op(project, {'op': 'split', 'no': 1, 'at_unit': 2}).status_code == 200
    assert op(project, {'op': 'move_boundary', 'no': 1, 'delta': -1}).status_code == 422
    assert op(project, {'op': 'move_boundary', 'no': 1, 'delta': 1}).status_code == 422
    assert op(project, {'op': 'delete', 'no': 2}).status_code == 200
    assert op(project, {'op': 'move_boundary', 'no': 1, 'delta': 1}).status_code == 422


def test_partial_empty_and_cancelled_approval(project):
    client, auths, pid = project
    for status in ('running', 'partial', 'cancelled'):
        sql('UPDATE studio_breakdowns SET status=? WHERE id=?', (status, 'bid'))
        assert client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 1}).status_code == 409
    sql('UPDATE studio_breakdowns SET status=? WHERE id=?', ('done', 'bid'))
    assert op(project, {'op': 'delete', 'no': 2}).status_code == 200
    assert op(project, {'op': 'delete', 'no': 1}).status_code == 200
    assert client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 3}).status_code == 409


def test_bible_edit_merge_archive_and_appearances(project):
    client, auths, pid = project
    base = f'/studio/projects/{pid}/bible'
    bible = client.get(base, headers=auths['owner']).json()
    assert bible[0]['needs_author'] and bible[0]['first_appearance'] == '第 1 块 第 1 场'
    response = client.patch('/studio/bible/person', headers=auths['owner'], json={'name': '岚', 'appearance': '布衣'})
    assert response.status_code == 200, response.text
    assert response.json()['appearance_source'] == 'author' and not response.json()['needs_author']
    assert response.json()['aliases'] == ['阿岚'] and response.json()['episodes'] == [1, 2]
    response = client.post('/studio/bible', headers=auths['owner'], json={'project_id': pid, 'kind': 'character', 'name': '老魏'})
    assert response.status_code == 201 and response.json()['episodes'] == [1, 2]
    other_id = response.json()['id']
    response = client.post('/studio/bible/merge', headers=auths['owner'], json={'keep_id': 'person', 'merge_ids': [other_id]})
    assert response.status_code == 200 and '老魏' in response.json()['aliases']
    assert sql('SELECT merged_into FROM studio_bible WHERE id=?', (other_id,))[0][0] == 'person'
    assert len(client.get(base, headers=auths['owner']).json()) == 1
    response = client.post('/studio/bible', headers=auths['owner'], json={'project_id': pid, 'kind': 'location', 'name': '院子'})
    assert response.status_code == 201 and response.json()['episodes'] == [1, 2]
    location_id = response.json()['id']
    assert client.post('/studio/bible/merge', headers=auths['owner'], json={'keep_id': 'person', 'merge_ids': [location_id]}).status_code == 422
    assert client.delete(f'/studio/bible/{location_id}', headers=auths['owner']).status_code == 200
    assert sql('SELECT archived FROM studio_bible WHERE id=?', (location_id,))[0][0] == 1
    assert get(project)['plan_revision'] == 1


def test_owned_resources_and_extra_fields(project):
    client, auths, pid = project
    for path in (f'/studio/projects/{pid}/episodes', f'/studio/projects/{pid}/bible', f'/studio/projects/{pid}/breakdown/export'):
        assert client.get(path, headers=auths['other']).status_code == 404
    assert client.patch('/studio/bible/person', headers=auths['other'], json={'role': 'x'}).status_code == 404
    assert client.delete('/studio/bible/person', headers=auths['other']).status_code == 404
    assert client.post('/studio/bible/merge', headers=auths['other'], json={'keep_id': 'person', 'merge_ids': ['missing']}).status_code == 404
    assert client.post('/studio/bible', headers=auths['other'], json={'project_id': pid, 'kind': 'character', 'name': '甲'}).status_code == 404
    assert client.post(f'/studio/projects/{pid}/episodes/ops', headers=auths['other'], json={'expected_revision': 1, 'op': 'delete', 'no': 1}).status_code == 404
    assert client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['other'], json={'expected_revision': 1}).status_code == 404
    assert client.patch('/studio/bible/person', headers=auths['owner'], json={'excerpt': '不许改原文'}).status_code == 422
    assert op(project, {'op': 'edit', 'no': 1, 'fields': {'unknown': 1}}).status_code == 422


def test_markdown_export_escaping_headers_and_worker(project, monkeypatch):
    client, auths, pid = project
    synopsis = {'main_threads': [{'name': '归家', 'description': '找到灯'}],
                'arc_summaries': [{'from': 1, 'to': 2, 'summary': '离岸'}]}
    sql('UPDATE studio_breakdowns SET synopsis_json=? WHERE id=?', (store._json(synopsis), 'bid'))
    original, calls = plan._render_export, []
    def render(*args):
        calls.append(threading.current_thread() is not threading.main_thread())
        return original(*args)
    monkeypatch.setattr(plan, '_render_export', render)
    response = client.get(f'/studio/projects/{pid}/breakdown/export', headers=auths['owner'])
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/markdown')
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-disposition'] == "attachment; filename*=UTF-8''" + quote('山月|新章-拆解与分集.md', safe='')
    text = response.text
    assert '山月\\|新章' in text and '门\\*开' in text
    assert all(value in text for value in ('人物总表', '未纳入的单元', '伏笔', '铜钥匙', '| 1 | 门\\*开 |', '60 秒'))
    assert all(value in text for value in ('主线', '归家 —— 找到灯', '第 1–2 章：离岸', '模型：千问'))
    assert all(value not in text for value in ('main\\_threads', '\\[\\{', '模型：qwen', '"'))
    assert calls == [True]


def test_project_duration_and_synopsis_edits(project):
    client, auths, pid = project
    response = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': 60, 'episode_seconds_max': 120, 'brain_provider': 'deepseek'})
    assert response.status_code == 200 and response.json()['brain_provider'] == 'deepseek'
    assert client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': 300}).status_code == 422
    assert client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': True}).status_code == 422
    response = client.patch(f'/studio/projects/{pid}/breakdown/synopsis', headers=auths['owner'], json={'synopsis': {'logline': '回家了'}})
    assert response.status_code == 200 and response.json()['synopsis']['themes'] == ['归乡']
    assert get(project)['plan_revision'] == 2
    assert client.patch(f'/studio/projects/{pid}/breakdown/synopsis', headers=auths['owner'], json={'synopsis': {'themes': '归乡'}}).status_code == 422
    assert client.patch(f'/studio/projects/{pid}/breakdown/synopsis', headers=auths['owner'], json={'synopsis': {'hidden': 'x'}}).status_code == 422


def test_regeneration_preserves_revision_snapshot(project):
    _, _, pid = project
    async def republish():
        async with store.connection(transaction=True) as db:
            await plan.publish_plan(db, 'bid', [{'unit_from': 1, 'unit_to': 8, 'title': '新方案', 'change': '', 'hook': ''}], reason='regenerated')
    run(republish())
    assert get(project)['plan_revision'] == 2
    snapshots = sql('SELECT plan_json FROM studio_plan_revisions WHERE project_id=? ORDER BY revision', (pid,))
    assert len(json.loads(snapshots[0][0])['episodes']) == 2 and len(json.loads(snapshots[1][0])['episodes']) == 1


def test_account_deletion_cleans_all_new_tables(project):
    _, _, pid = project
    sql('''INSERT INTO studio_chunks(id,breakdown_id,project_id,owner,no,task,provider,status)
        VALUES(?,?,?,?,?,?,?,?)''', ('chunk', 'bid', pid, 'owner', 1, 'text_map', 'qwen', 'failed'))
    import database
    run(database.delete_account_data('owner'))
    for table in ('studio_breakdowns', 'studio_chunks', 'studio_units', 'studio_bible', 'studio_episodes', 'studio_plan_revisions'):
        assert sql(f'SELECT count(*) FROM {table}')[0][0] == 0


def test_author_field_edits_recorded_atomically_and_accumulate(project):
    client, auths, _ = project
    response = client.patch('/studio/bible/person', headers=auths['owner'], json={'role': '', 'description': ''})
    assert response.status_code == 200
    assert response.json()['role'] == '' and response.json()['description'] == ''
    assert json.loads(sql('SELECT import_json FROM studio_breakdowns')[0][0])['_bible_author_edits']['person'] == ['description', 'role']
    response = client.patch('/studio/bible/person', headers=auths['owner'], json={'name': '岚'})
    assert response.status_code == 200
    assert json.loads(sql('SELECT import_json FROM studio_breakdowns')[0][0])['_bible_author_edits']['person'] == ['aliases', 'description', 'name', 'role']
    assert get(project)['plan_revision'] == 1


def test_breakdown_refresh_preserves_author_cleared_bible_fields(client, monkeypatch, tmp_path):
    from test_studio_breakdown_pipeline import OWNER, drain, fake, pipeline as fixture
    project = fixture.__wrapped__(client, monkeypatch, tmp_path)
    from studio import breakdown
    fake(monkeypatch)
    async def scenario():
        quote = await breakdown.quote(project['id'], OWNER)
        await breakdown.start(project['id'], OWNER, quote['id'])
        await drain(project['id'])
        entries = await plan.list_bible(project['id'], OWNER)
        location = next(item for item in entries if item['kind'] == 'location')
        assert location['description'] == '住处'
        character = next(item for item in entries if item['kind'] == 'character')
        assert character['role'] == '送灯人'
        await plan.patch_bible(location['id'], OWNER, {'description': ''})
        await plan.patch_bible(character['id'], OWNER, {'role': ''})
        for _ in range(2):
            await breakdown.get_current(project['id'], OWNER)
        entries = await plan.list_bible(project['id'], OWNER)
        assert next(item for item in entries if item['id'] == location['id'])['description'] == ''
        assert next(item for item in entries if item['id'] == character['id'])['role'] == ''
    run(scenario())


def test_old_breakdown_publication_cannot_replace_new_current_or_revision(project):
    _, _, pid = project
    sql('''INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)''', ('new-bid', pid, 'owner', 2, 'deepseek', 'running', store.utcnow(), store.utcnow()))
    sql('UPDATE studio_projects SET breakdown_id=? WHERE id=?', ('new-bid', pid))
    async def late_publish():
        async with store.connection(transaction=True) as db:
            await plan.publish_plan(db, 'bid', [{'unit_from': 1, 'unit_to': 8, 'title': '旧任务迟到', 'change': '', 'hook': ''}])
    run(late_publish())
    assert sql('SELECT breakdown_id,plan_revision FROM studio_projects WHERE id=?', (pid,))[0] == ('new-bid', 1)
    assert sql('SELECT count(*) FROM studio_plan_revisions')[0][0] == 1
    assert sql('SELECT title FROM studio_episodes WHERE breakdown_id=?', ('bid',))[0][0] == '旧任务迟到'


def test_default_duration_change_revises_approved_plan_and_snapshot(project):
    client, auths, pid = project
    response = client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 1})
    assert response.status_code == 200 and response.json()['g0_approved']
    response = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': 120, 'episode_seconds_max': 300})
    assert response.status_code == 200 and response.json()['plan_revision'] == 2
    current = get(project)
    assert not current['g0_approved'] and current['plan_approved_revision'] == 1
    assert all(episode['effective_target_min'] == 120 and episode['effective_target_max'] == 300 for episode in current['episodes'])
    snapshot, reason = sql('SELECT plan_json,created_reason FROM studio_plan_revisions WHERE project_id=? AND revision=2', (pid,))[0]
    saved = json.loads(snapshot)
    assert reason == 'settings'
    assert saved['settings'] == {'episode_seconds_min': 120, 'episode_seconds_max': 300}
    assert saved['episodes'][0]['effective_target_min'] == 120 and saved['episodes'][0]['effective_target_max'] == 300
    for body in ({'episode_seconds_min': 120, 'episode_seconds_max': 300}, {'brain_provider': 'deepseek'}):
        response = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json=body)
        assert response.status_code == 200 and response.json()['plan_revision'] == 2


def test_duration_settings_without_affected_episodes_do_not_revise(project):
    client, auths, pid = project
    # Both episodes override their minimum, but continue inheriting the maximum.
    assert op(project, {'op': 'edit', 'no': 1, 'fields': {'target_min': 60}}).status_code == 200
    assert op(project, {'op': 'edit', 'no': 2, 'fields': {'target_min': 60}}).status_code == 200
    assert client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 3}).json()['g0_approved']
    response = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': 200})
    assert response.status_code == 200 and response.json()['plan_revision'] == 3
    assert get(project)['g0_approved']
    response = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_max': 300})
    assert response.status_code == 200 and response.json()['plan_revision'] == 4
    assert not get(project)['g0_approved']
    empty = client.post('/studio/projects', headers=auths['owner'], json={'title': '未拆解'}).json()
    response = client.patch(f"/studio/projects/{empty['id']}", headers=auths['owner'], json={'episode_seconds_min': 120})
    assert response.status_code == 200 and response.json()['plan_revision'] == 0


def test_default_duration_change_cannot_invert_episode_override(project):
    client, auths, pid = project
    assert op(project, {'op': 'edit', 'no': 1, 'fields': {'target_max': 200}}).status_code == 200
    response = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': 220})
    assert response.status_code == 422
    assert get(project)['plan_revision'] == 2
    assert client.get(f'/studio/projects/{pid}', headers=auths['owner']).json()['episode_seconds_min'] == 180
