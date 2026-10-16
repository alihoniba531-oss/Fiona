"""WO3c R1：导出可读性、未完成时只读、重新拆解保留已发布方案。"""
import json

import pytest

from studio import breakdown_plan as plan, store
from test_studio_breakdown_plan import project, get, op, run, sql


@pytest.mark.parametrize('role,label', [('main', '主要人物'), ('supporting', '配角'),
                                        ('major', '重要'), ('minor', '次要'), ('守门人', '守门人'), ('', '')])
def test_role_labels(role, label):
    assert plan._role_label(role) == label


@pytest.mark.parametrize('numbers,expected', [([], '未纳入'), ([3], '第 3 集'),
    ([1, 2, 3, 5, 6, 10], '第 1–3、5–6、10 集'), ([6, 1, 5, 3, 2, 1], '第 1–3、5–6 集'),
    ([1, 3, 5], '第 1、3、5 集')])
def test_episode_ranges(numbers, expected):
    assert plan._episode_ranges(numbers) == expected


def test_prose_human_readable_structures_and_markdown_escaping():
    synopsis = {'compass': {'logline': '归来', 'main_threads': [
        {'name': '旧灯', 'description': '找到灯', 'id': 'T1'}, {'title': '归路', 'summary': '渡河'}, {'name': '等候'}]},
        'arc_summaries': [{'from': 1, 'to': 2, 'summary': '离岸'},
                          {'start_chapter': 3, 'end_chapter': 4, 'summary': '登岸'},
                          {'from_chapter': 5, 'to_chapter': 6, 'summary': '归家'}, {'summary': '尾声'}],
        'themes': ['归属', '选择']}
    result = '\n'.join(plan._prose(synopsis))
    assert all(text in result for text in ('一句话梗概：归来', '主线', '旧灯 —— 找到灯', '归路 —— 渡河',
                                          '等候', '第 1–2 章：离岸', '第 3–4 章：登岸', '第 5–6 章：归家', '尾声', '主题：归属、选择'))
    assert all(text not in result for text in ('main_threads', 'arc_summaries', '"', '{', '}', '['))
    details = '\n'.join(plan._prose([{'description': '铜钥匙', 'chapter': 3, 'details': {'date': '2026-10-16', 'event': '开门'}}]))
    assert '说明：铜钥匙' in details and '章节：3' in details and '日期：2026-10-16' in details and '事件：开门' in details
    assert '\\-' not in details and '{' not in details
    assert plan._inline('|*<tag> 2026-10-16') == '\\|\\*&lt;tag&gt; 2026-10-16'


def test_export_uses_role_labels_and_compressed_episode_ranges(project):
    client, auths, pid = project
    sql('UPDATE studio_bible SET role=?,episodes_json=? WHERE id=?', ('main', '[1,2,3,5,6,10]', 'person'))
    response = client.get(f'/studio/projects/{pid}/breakdown/export', headers=auths['owner'])
    assert response.status_code == 200
    assert '主要人物' in response.text and '第 1–3、5–6、10 集' in response.text
    assert '| main |' not in response.text


def test_clearing_character_appearance_marks_missing_and_survives_refresh(project):
    client, auths, _ = project
    response = client.patch('/studio/bible/person', headers=auths['owner'], json={'appearance': '灰衣'})
    assert response.json()['appearance_source'] == 'author' and not response.json()['needs_author']
    response = client.patch('/studio/bible/person', headers=auths['owner'], json={'appearance': ''})
    assert response.status_code == 200
    assert response.json()['appearance'] == '' and response.json()['appearance_source'] == 'none'
    assert response.json()['needs_author'] == 1
    markers = json.loads(sql('SELECT import_json FROM studio_breakdowns WHERE id=?', ('bid',))[0][0])['_bible_author_edits']['person']
    assert {'appearance', 'appearance_source', 'needs_author'} <= set(markers)


@pytest.mark.parametrize('status', ['running', 'partial'])
@pytest.mark.parametrize('operation', [{'op': 'edit', 'no': 1, 'fields': {'title': '改名'}}, {'op': 'merge', 'no': 1},
    {'op': 'split', 'no': 1, 'at_unit': 2}, {'op': 'move_boundary', 'no': 1, 'delta': 1},
    {'op': 'delete', 'no': 1}, {'op': 'insert', 'unit_from': 6, 'unit_to': 8}])
def test_unfinished_breakdown_episode_operations_return_409(project, status, operation):
    sql('UPDATE studio_breakdowns SET status=? WHERE id=?', (status, 'bid'))
    response = op(project, operation)
    assert response.status_code == 409 and '完成后才能修改' in response.json()['detail']
    assert get(project)['plan_revision'] == 1
    assert sql('SELECT count(*) FROM studio_plan_revisions')[0][0] == 1


def new_active(project):
    _, _, pid = project
    sql('UPDATE studio_projects SET plan_approved_revision=plan_revision WHERE id=?', (pid,))
    sql('UPDATE studio_breakdowns SET status=? WHERE id=?', ('cancelled', 'bid'))
    sql('''INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)''', ('replacement', pid, 'owner', 2, 'deepseek', 'running', store.utcnow(), store.utcnow()))
    sql('''UPDATE studio_projects SET breakdown_id=?,episode_seconds_min=120,episode_seconds_max=360 WHERE id=?''', ('replacement', pid))


def test_rebreakdown_keeps_published_episodes_g0_and_target_defaults(project):
    client, auths, pid = project
    before = get(project)
    new_active(project)
    current = get(project)
    assert len(current['episodes']) == 2 and current['g0_approved']
    assert current['plan_revision'] == 1 and current['plan_approved_revision'] == 1
    assert current['breakdown_id'] == 'bid' and current['active_breakdown_id'] == 'replacement'
    assert current['status'] == 'done' and current['active_breakdown_status'] == 'running'
    assert current['rebreakdown_pending']
    assert current['settings'] == before['settings']
    assert current['episodes'][0]['effective_target_min'] == 180 and current['episodes'][0]['effective_target_max'] == 240
    assert current['episodes'][0]['warnings'] == before['episodes'][0]['warnings']
    assert op(project, {'op': 'delete', 'no': 1}).status_code == 409
    response = client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 1})
    assert response.status_code == 409
    exported = client.get(f'/studio/projects/{pid}/breakdown/export', headers=auths['owner'])
    assert exported.status_code == 200 and '快照第 1 版' in exported.text and '已批准' in exported.text and '门\\*开' in exported.text


def test_first_unpublished_run_never_reports_approved_zero_episode_plan(project):
    client, auths, _ = project
    empty = client.post('/studio/projects', headers=auths['owner'], json={'title': '空方案'}).json()
    sql('UPDATE studio_projects SET plan_revision=3,plan_approved_revision=3 WHERE id=?', (empty['id'],))
    result = client.get(f"/studio/projects/{empty['id']}/episodes", headers=auths['owner']).json()
    assert result['episodes'] == [] and not result['g0_approved']


def test_new_publication_replaces_old_plan_once_and_clears_g0(project):
    new_active(project)
    _, _, pid = project
    async def publish():
        async with store.connection(transaction=True) as db:
            await db.execute('''INSERT INTO studio_units(breakdown_id,seq,label,chapter,scene_index,characters_json,est_seconds)
                VALUES(?,?,?,?,?,?,?)''', ('replacement', 1, '新的第一场', 1, 1, '["新人物"]', 220))
            await db.execute('UPDATE studio_breakdowns SET status=? WHERE id=?', ('done', 'replacement'))
            await plan.publish_plan(db, 'replacement', [{'unit_from': 1, 'unit_to': 1, 'title': '新的方案', 'change': '离开', 'hook': '路口'}])
    run(publish())
    result = get(project)
    assert result['breakdown_id'] == result['active_breakdown_id'] == 'replacement'
    assert result['plan_revision'] == 2 and result['plan_approved_revision'] == 1 and not result['g0_approved']
    assert len(result['episodes']) == 1 and result['episodes'][0]['title'] == '新的方案'
    assert result['episodes'][0]['effective_target_min'] == 120 and result['episodes'][0]['effective_target_max'] == 360
    assert not result['rebreakdown_pending']
    assert sql('SELECT count(*) FROM studio_episodes WHERE breakdown_id=?', ('bid',))[0][0] == 2


def test_cancelled_replacement_restores_old_plan_editing_and_default_revision(project):
    client, auths, pid = project
    new_active(project)
    sql('UPDATE studio_breakdowns SET status=? WHERE id=?', ('cancelled', 'replacement'))
    current = get(project)
    assert current['g0_approved'] and current['status'] == 'done' and not current['rebreakdown_pending']
    assert op(project, {'op': 'edit', 'no': 1, 'fields': {'title': '旧方案继续修改'}}).status_code == 200
    assert get(project)['plan_revision'] == 2 and not get(project)['g0_approved']
    approved = client.post(f'/studio/projects/{pid}/episodes/approve', headers=auths['owner'], json={'expected_revision': 2})
    assert approved.status_code == 200 and approved.json()['g0_approved']
    # 120 was already saved as the replacement's draft default. Explicitly
    # saving it now still changes the old plan's displayed inherited 180 value.
    changed = client.patch(f'/studio/projects/{pid}', headers=auths['owner'], json={'episode_seconds_min': 120})
    assert changed.status_code == 200 and changed.json()['plan_revision'] == 3
    current = get(project)
    assert not current['g0_approved'] and current['settings']['episode_seconds_min'] == 120
    assert current['settings']['episode_seconds_max'] == 240
    assert current['active_breakdown_id'] == 'replacement' and current['breakdown_id'] == 'bid'


def test_real_rebreakdown_confirmation_keeps_approved_plan_until_new_publication(client, monkeypatch, tmp_path):
    from studio import breakdown
    from test_studio_breakdown_pipeline import OWNER, drain, fake, pipeline as fixture
    project = fixture.__wrapped__(client, monkeypatch, tmp_path)
    fake(monkeypatch)
    async def scenario():
        first_quote = await breakdown.quote(project['id'], OWNER)
        first = await breakdown.start(project['id'], OWNER, first_quote['id'])
        assert (await plan.get_episodes(project['id'], OWNER))['g0_approved'] is False
        assert (await drain(project['id']))['status'] == 'done'
        approved = await plan.approve(project['id'], OWNER, 1)
        assert approved['g0_approved'] and len(approved['episodes']) == 1
        second_quote = await breakdown.quote(project['id'], OWNER, episode_seconds_min=120, episode_seconds_max=300)
        assert (await store.get_project(project['id'], OWNER))['episode_seconds_min'] == 180
        second = await breakdown.start(project['id'], OWNER, second_quote['id'])
        assert second['id'] != first['id']
        pending = await plan.get_episodes(project['id'], OWNER)
        assert pending['rebreakdown_pending'] and pending['g0_approved'] and pending['plan_revision'] == 1
        assert pending['breakdown_id'] == first['id'] and pending['active_breakdown_id'] == second['id']
        assert pending['settings'] == {'episode_seconds_min': 180, 'episode_seconds_max': 240}
        assert pending['episodes'] == approved['episodes']
        assert (await drain(project['id']))['status'] == 'done'
        replaced = await plan.get_episodes(project['id'], OWNER)
        assert replaced['plan_revision'] == 2 and not replaced['g0_approved'] and not replaced['rebreakdown_pending']
        assert replaced['breakdown_id'] == second['id']
        assert replaced['settings'] == {'episode_seconds_min': 120, 'episode_seconds_max': 300}
    run(scenario())
