"""连载小说来源：资格、快照范围、签名、漂移、来源状态、候选与做成片。"""
import asyncio
import json

from fastapi import HTTPException
import pytest

from studio import novel_chat, sources, storage
from test_studio_sources import workshop, novel_project, sql


def run(awaitable):
    return asyncio.run(awaitable)


def manifest(project, no=1):
    return json.loads(storage.resolve_path(
        f"{project['id']}/source/snap-{no:04d}/snapshot.json").read_text())


def add_chapter(state, number, status='planning', title='下一章', body=None):
    state['book']['chapters'].append({'chapter': number, 'title': title, 'status': status})
    state['chapters'].append({'chapter': number, 'title': title, 'status': status, 'body': body})


def candidate():
    return run(sources.list_candidates('owner'))['books'][0]


@pytest.mark.parametrize('status', ['running', 'awaiting_plan', 'paused', 'failed', 'setup_running'])
def test_serial_book_status_stays_eligible(workshop, status):
    _, _, state = workshop
    state['book']['status'] = status
    book = candidate()
    assert book['eligible'] is True and book['reason'] is None
    project = novel_project(workshop)
    assert project['source_kind'] == 'novel' and project['snapshot_no'] == 1
    assert sql('SELECT COUNT(*) FROM studio_projects')[0][0] == 1


def test_stale_chapter_imports_with_status_and_is_flagged(workshop):
    _, _, state = workshop
    state['book']['chapters'][0]['status'] = 'stale'
    state['chapters'][0]['status'] = 'stale'
    book = candidate()
    assert book['eligible'] is True and book['stale'] == [1]
    project = novel_project(workshop)
    assert manifest(project)['chapters'][0]['status'] == 'stale'
    status = run(sources.source_status('owner', project['id']))
    assert status['snapshot']['stale'] == [1]


@pytest.mark.parametrize('problem,reason', [
    ('bible', '作品缺少故事圣经'),
    ('empty', '作品还没有写好的章节'),
    ('editing', '作品正在修改，请稍后再试'),
])
def test_three_rejection_reasons(workshop, monkeypatch, problem, reason):
    client, auth, state = workshop
    if problem == 'bible':
        state['bible'] = None
    elif problem == 'empty':
        state['book'].update(chapters_done=0, chapters=[])
    else:
        monkeypatch.setattr(sources, 'is_editing', lambda bid: True)
    book = candidate()
    assert book['eligible'] is False and book['reason'] == reason
    response = client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book'})
    assert response.status_code == 409 and response.json()['detail'] == reason
    assert sql('SELECT * FROM studio_projects') == []


def test_rearchive_window_blocks_candidate_create_sync_and_drift(workshop):
    client, auth, state = workshop
    project = novel_project(workshop)
    state['book']['config']['_rearchive'] = 2
    book = candidate()
    assert book['eligible'] is False and book['reason'] == '作品正在修改，请稍后再试'
    response = client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book'})
    assert response.status_code == 409
    assert response.json()['detail'] == '作品正在修改，请稍后再试'
    with pytest.raises(HTTPException) as exc:
        run(sources.sync_source('owner', project['id'], 1))
    assert exc.value.status_code == 409 and exc.value.detail == '作品正在修改，请稍后再试'
    status = run(sources.source_status('owner', project['id']))
    assert status['drift']['eligible'] is False
    assert status['drift']['reason'] == '作品正在修改，请稍后再试'


@pytest.mark.parametrize('maximum', [301, True])
def test_invalid_chapter_range_rejects_before_reading(workshop, maximum):
    client, auth, state = workshop
    state['book']['chapters_done'] = maximum
    response = client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book'})
    assert response.status_code == 409 and response.json()['detail'] == '作品章节范围无效'
    assert sql('SELECT * FROM studio_projects') == []
    assert state['range_calls'] == []


def test_snapshot_ignores_in_progress_row_after_chapters_done(workshop):
    _, _, state = workshop
    add_chapter(state, 3, status='planning', body=None)
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    assert [item['chapter'] for item in snapshot['manifest']['chapters']] == [1, 2]
    assert len(snapshot['bodies']) == 2
    assert state['range_calls'] == [(1, 2)]


def test_signature_ignores_updated_at(workshop, monkeypatch):
    _, _, state = workshop
    original = sources.service.detail

    async def changing(user, bid):
        result = await original(user, bid)
        if state['details'] >= 2:
            result['updated_at'] = 'billed'
        return result

    monkeypatch.setattr(sources.service, 'detail', changing)
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    assert state['details'] == 2 and len(state['range_calls']) == 1
    assert snapshot['manifest']['chapters'][0]['status'] == 'done'


def test_signature_retries_on_bible_version_change(workshop, monkeypatch):
    _, _, state = workshop
    original = sources.service.detail

    async def changing(user, bid):
        result = await original(user, bid)
        if state['details'] >= 2:
            result['bible_version'] = state['book']['bible_version'] + 1
        return result

    monkeypatch.setattr(sources.service, 'detail', changing)
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    assert state['details'] == 4 and len(state['range_calls']) == 2
    assert snapshot['manifest']['book']['bible_version'] == 4


def test_signature_retries_when_covered_chapter_becomes_stale(workshop, monkeypatch):
    _, _, state = workshop
    original = sources.service.detail

    async def changing(user, bid):
        result = await original(user, bid)
        if state['details'] >= 2:
            result['chapters'][0]['status'] = 'stale'
        return result

    monkeypatch.setattr(sources.service, 'detail', changing)
    run(sources.take_novel_snapshot('owner', 'book'))
    assert state['details'] == 4 and len(state['range_calls']) == 2


def test_signature_retries_then_rejects_rearchive_on_second_detail(workshop, monkeypatch):
    _, _, state = workshop
    original = sources.service.detail

    async def changing(user, bid):
        result = await original(user, bid)
        if state['details'] >= 2:
            result['config']['_rearchive'] = 1
        return result

    monkeypatch.setattr(sources.service, 'detail', changing)
    with pytest.raises(HTTPException) as exc:
        run(sources.take_novel_snapshot('owner', 'book'))
    assert exc.value.status_code == 409 and exc.value.detail == '作品正在修改，请稍后再试'
    assert state['details'] == 3 and len(state['range_calls']) == 1


def test_signature_ignores_row_after_chapters_done(workshop, monkeypatch):
    _, _, state = workshop
    add_chapter(state, 3, status='planning', body=None)
    original = sources.service.detail

    async def changing(user, bid):
        result = await original(user, bid)
        if state['details'] >= 2:
            result['chapters'][-1].update(status='writing', title='改过的下一章')
        return result

    monkeypatch.setattr(sources.service, 'detail', changing)
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    assert state['details'] == 2 and state['range_calls'] == [(1, 2)]
    assert [item['chapter'] for item in snapshot['manifest']['chapters']] == [1, 2]


def test_drift_ignores_in_progress_stale_and_serial_sync(workshop):
    _, _, state = workshop
    project = novel_project(workshop)
    add_chapter(state, 3, status='planning', body=None)
    drift = run(sources.source_status('owner', project['id']))['drift']
    assert drift['added'] == [] and drift['stale'] == [] and drift['chapters_done'] == 2
    state['book']['chapters'][0]['status'] = 'stale'
    state['chapters'][0]['status'] = 'stale'
    drift = run(sources.source_status('owner', project['id']))['drift']
    assert drift['stale'] == [1] and drift['chapters_done'] == 2 and drift['state'] == 'unchanged'
    state['book']['status'] = 'running'
    state['book']['chapters'][-1].update(status='done', title='新章')
    state['chapters'][-1].update(status='done', body='新章正文')
    state['book']['chapters_done'] = 3
    status = run(sources.sync_source('owner', project['id'], 1))
    assert status['snapshot']['no'] == 2
    assert status['drift']['state'] == 'unchanged'
    assert status['drift']['chapters_done'] == 3
    assert status['drift']['stale'] == [1]
    assert status['snapshot']['stale'] == [1]


def test_source_status_snapshot_stale_is_empty_before_any_stale_chapter(workshop):
    _, _, state = workshop
    project = novel_project(workshop)
    assert run(sources.source_status('owner', project['id']))['snapshot']['stale'] == []
    state['book']['chapters'][1]['status'] = 'stale'
    state['chapters'][1]['status'] = 'stale'
    status = run(sources.sync_source('owner', project['id'], 1))
    assert status['snapshot']['no'] == 2
    assert status['snapshot']['stale'] == [2]
    assert status['drift']['stale'] == [2]


def test_candidate_stale_and_snapshot_chapters(workshop):
    _, _, state = workshop
    state['book']['chapters'][0]['status'] = 'stale'
    state['chapters'][0]['status'] = 'stale'
    project = novel_project(workshop)
    book = candidate()
    assert book['stale'] == [1]
    assert book['projects'][0]['id'] == project['id']
    assert book['projects'][0]['snapshot_chapters'] == 2


def test_start_film_reuse_shows_snapshot_and_sync_hint(workshop, monkeypatch):
    _, _, state = workshop
    project = novel_project(workshop)

    async def no_creation(*args, **kwargs):
        pytest.fail('Must reuse an existing project without creating another one')

    monkeypatch.setattr(sources, 'create_novel_project', no_creation)
    state['book']['chapters_done'] = 3
    add_chapter(state, 3, status='done', body='第三层正文')
    card = run(novel_chat.start_film('owner', '山月', 'jwt'))
    assert card['url'] == '/studio/' + project['id']
    assert card['points'] == [
        '《山月》',
        '快照第 1 版 · 2 章',
        '作品已写到第 3 章；到工作室来源面板同步后可以续拆',
        '已有项目，打开即可继续',
    ]


def test_start_film_reuse_without_new_chapters_has_no_sync_hint(workshop, monkeypatch):
    project = novel_project(workshop)

    async def no_creation(*args, **kwargs):
        pytest.fail('Must reuse an existing project without creating another one')

    monkeypatch.setattr(sources, 'create_novel_project', no_creation)
    card = run(novel_chat.start_film('owner', '山月', 'jwt'))
    assert card['url'] == '/studio/' + project['id']
    assert card['points'] == ['《山月》', '快照第 1 版 · 2 章', '已有项目，打开即可继续']
