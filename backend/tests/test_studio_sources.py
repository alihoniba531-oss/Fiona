"""WO3b 作品接入：全程离线、只读的小说适配与快照回滚。"""
import asyncio
from copy import deepcopy
import errno
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import zipfile

import aiosqlite
from fastapi import HTTPException
import pytest

from studio import sources, storage, store


def run(awaitable):
    return asyncio.run(awaitable)


def headers(user):
    from auth import create_token
    from database import get_or_create_user
    account = run(get_or_create_user(user))
    return {'Authorization': f"Bearer {create_token(user, account['session_version'])}"}


@pytest.fixture
def workshop(client, tmp_path, monkeypatch):
    monkeypatch.setenv('FIONA_STUDIO', '1')
    monkeypatch.setenv('FIONA_STUDIO_OWNERS', 'owner, other')
    monkeypatch.setenv('FIONA_STUDIO_REQUIRE_JWT', '1')
    monkeypatch.setenv('FIONA_STUDIO_DIR', str(tmp_path / 'studio'))
    monkeypatch.setenv('FIONA_NOVEL', '1')
    monkeypatch.setenv('FIONA_NOVEL_USERS', ' owner, other ')
    book = {'id': 'book', 'title': '山月', 'status': 'completed', 'chapters_done': 2, 'words_done': 12,
            'completed_at': '2026-10-01', 'updated_at': '2026-10-02', 'bible_version': 3,
            'config': {'drama_adaptation': False, 'structure': 'v2', 'target': {'max_chapters': 2, '_secret': 1},
                       'adaptation': {}, '_hidden': 'NO', 'agents': 'NO'}, 'compass': {'theme': '归乡'},
            'chapters': [{'chapter': 1, 'title': '归来', 'status': 'done', 'flags': ['review_degraded']},
                         {'chapter': 2, 'title': '山月', 'status': 'done', 'flags': []}]}
    state = {'book': book, 'bible': {'version': 3, 'locked': {'characters': []}, 'compass': {'theme': '归乡'}},
             'chapters': [dict(book['chapters'][0], body='# 第1章 归来\n灯火。', updated_at='date', edited_by_user=True,
                               meeting={'brief': 'SECRET', 'proposals': 'SECRET', 'decision': {'beat_sheet': {'title': '归来', 'beats': ['进门'], 'secret': 'SECRET'}}}),
                          dict(book['chapters'][1], body='# 第2章 山月\n月升。', updated_at='date', edited_by_user=False)],
             'details': 0, 'range_calls': []}

    async def detail(user, bid):
        if bid != 'book' or user != 'owner' or state.get('deleted'):
            raise HTTPException(404, '不应外泄小说错误')
        state['details'] += 1
        return deepcopy(state['book'])

    async def bible(user, bid):
        return deepcopy(state['bible'])

    async def ranges(user, bid, start, end):
        state['range_calls'].append((start, end))
        return deepcopy([item for item in state['chapters'] if start <= item['chapter'] <= end])

    async def books(user):
        return [deepcopy(state['book'])] if user == 'owner' else []

    async def find(user, query):
        return [item for item in await books(user) if query.casefold().strip() in item['title'].casefold()]

    monkeypatch.setattr(sources.service, 'detail', detail)
    monkeypatch.setattr(sources.service, 'bible', bible)
    monkeypatch.setattr(sources.service, 'chapters_range', ranges)
    monkeypatch.setattr(sources.service, 'list_books', books)
    monkeypatch.setattr(sources.service, 'find_books', find)
    monkeypatch.setattr(sources, 'is_editing', lambda bid: False)
    return client, headers('owner'), state


def novel_project(workshop, **body):
    client, auth, _ = workshop
    response = client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book', **body})
    assert response.status_code == 201, response.text
    return response.json()


def sql(query, args=()):
    async def execute():
        import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute(query, args)
            result = await cursor.fetchall()
            await db.commit()
            return result
    return run(execute())


@pytest.mark.parametrize('enabled', ['0', '1', 'true', ''])
@pytest.mark.parametrize('allowed', ['', 'owner', ' owner, other ', 'owner-suffix'])
def test_access_exactly_matches_novel_gate(monkeypatch, enabled, allowed):
    from routers.novel import workshop_user
    monkeypatch.setenv('FIONA_NOVEL', enabled)
    monkeypatch.setenv('FIONA_NOVEL_USERS', allowed)
    try:
        accepted = run(workshop_user('owner')) == 'owner'
    except HTTPException:
        accepted = False
    assert sources.novel_access('owner') is accepted


def test_snapshot_exact_bytes_filtered_manifest_and_read(workshop):
    client, auth, state = workshop
    project = novel_project(workshop)
    assert project['title'] == '山月'
    assert project['source_kind'] == 'novel' and project['source_ref'] == 'book' and project['snapshot_no'] == 1
    root = storage.resolve_path(f"{project['id']}/source/snap-0001")
    data = (root / 'snapshot.json').read_bytes()
    manifest = json.loads(data)
    assert manifest['book']['bible_version'] == 3
    assert manifest['config'] == {'drama_adaptation': False, 'structure': 'v2', 'target': {'max_chapters': 2}, 'adaptation': {}}
    assert manifest['compass'] == {'theme': '归乡'}
    assert 'compass' not in manifest['bible']
    assert b'SECRET' not in data and b'_hidden' not in data
    assert manifest['chapters'][0]['outline'] == {'title': '归来', 'beats': ['进门']}
    for item, original in zip(manifest['chapters'], state['chapters']):
        assert (root / item['file']).read_bytes() == original['body'].encode()
        assert item['sha256'] == hashlib.sha256(original['body'].encode()).hexdigest()
    assert sql('SELECT manifest_sha256 FROM studio_snapshots')[0][0] == hashlib.sha256(data).hexdigest()
    assert run(sources.read_snapshot('owner', project['id'], 1, 2))[0]['body'] == state['chapters'][0]['body']
    status = client.get(f"/studio/projects/{project['id']}/source", headers=auth).json()
    assert status['drift']['state'] == 'unchanged'
    assert status['snapshot']['flagged'] == [{'chapter': 1, 'title': '归来', 'flags': ['review_degraded']}]
    assert client.get('/studio/projects', headers=auth).json()[0]['snapshot_no'] == 1
    assert client.get(f"/studio/projects/{project['id']}", headers=auth).json()['source_kind'] == 'novel'


@pytest.mark.parametrize('problem,reason', [('running', '尚未完结'), ('planning', '尚未完成'), ('stale', '待复核'),
                                          ('bible', '故事圣经'), ('editing', '正在修改'), ('empty', '没有章节')])
def test_eligibility_rejects_with_reason(workshop, monkeypatch, problem, reason):
    client, auth, state = workshop
    if problem == 'running':
        state['book']['status'] = 'running'
    elif problem in ('planning', 'stale'):
        state['book']['chapters'][0]['status'] = problem
    elif problem == 'bible':
        state['bible'] = None
    elif problem == 'empty':
        state['book']['chapters'] = []
    else:
        monkeypatch.setattr(sources, 'is_editing', lambda bid: True)
    candidate = client.get('/studio/sources/novels', headers=auth).json()['books'][0]
    assert not candidate['eligible'] and reason in candidate['reason']
    response = client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book'})
    assert response.status_code == 409 and reason in response.json()['detail']
    assert sql('SELECT * FROM studio_projects') == []


def test_candidate_flags_projects_and_exact_title_search(workshop, monkeypatch):
    _, _, state = workshop
    project = novel_project(workshop)
    candidates = run(sources.list_candidates('owner'))
    assert candidates['books'][0]['eligible']
    assert candidates['books'][0]['projects'][0]['id'] == project['id']
    second = deepcopy(state['book'])
    second.update(id='drama', title='山月续篇', config={'drama_adaptation': True})
    original_detail = sources.service.detail
    async def books(user):
        return [state['book'], second]
    async def detail(user, bid):
        return deepcopy(second) if bid == 'drama' else await original_detail(user, bid)
    async def find(user, query):
        return [state['book'], second]
    monkeypatch.setattr(sources.service, 'list_books', books)
    monkeypatch.setattr(sources.service, 'find_books', find)
    monkeypatch.setattr(sources.service, 'detail', detail)
    assert [item['id'] for item in run(sources.list_candidates('owner'))['books']] == ['drama', 'book']
    assert [item['id'] for item in run(sources.find_candidates('owner', ' 山月 '))['books']] == ['book']
    state['book'].update(title=None, status='setup_running')
    untitled = next(item for item in run(sources.list_candidates('owner'))['books'] if item['id'] == 'book')
    assert untitled['title'] == '未命名小说' and not untitled['eligible']


def test_consistent_snapshot_retries_once(workshop, monkeypatch):
    _, _, state = workshop
    original = sources.service.detail
    async def changing(user, bid):
        result = await original(user, bid)
        if state['details'] >= 2:
            result['updated_at'] = 'new'
        return result
    monkeypatch.setattr(sources.service, 'detail', changing)
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    assert state['details'] == 4 and len(state['range_calls']) == 2
    assert snapshot['manifest']['book']['updated_at'] == 'new'


def test_continuous_change_rejected(workshop, monkeypatch):
    _, _, state = workshop
    original = sources.service.detail
    async def changing(user, bid):
        result = await original(user, bid)
        result['updated_at'] = str(state['details'])
        return result
    monkeypatch.setattr(sources.service, 'detail', changing)
    with pytest.raises(HTTPException, match='409') as exc:
        run(sources.take_novel_snapshot('owner', 'book'))
    assert exc.value.detail == '作品正在修改，请稍后再试'
    assert len(state['range_calls']) == 2


@pytest.mark.parametrize('problem', ['missing', 'empty'])
def test_missing_or_empty_chapter_never_skipped(workshop, problem):
    _, _, state = workshop
    if problem == 'missing':
        state['chapters'].pop()
    else:
        state['chapters'][1]['body'] = ''
    with pytest.raises(HTTPException) as exc:
        run(sources.take_novel_snapshot('owner', 'book'))
    assert exc.value.status_code == 409 and '第 2 章' in exc.value.detail


def test_novel_reads_batches_of_at_most_fifty(workshop):
    _, _, state = workshop
    state['book']['chapters_done'] = 101
    state['book']['chapters'] = [{'chapter': n, 'title': str(n), 'status': 'done'} for n in range(1, 102)]
    state['chapters'] = [{**item, 'body': str(item['chapter'])} for item in state['book']['chapters']]
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    assert len(snapshot['bodies']) == 101
    assert state['range_calls'] == [(1, 50), (51, 100), (101, 101)]


def test_drift_detect_sync_archive_and_delete_source(workshop):
    _, _, state = workshop
    project = novel_project(workshop)
    before = sql('SELECT * FROM studio_snapshots')
    state['chapters'][0]['body'] += '改动'
    state['chapters'][1]['title'] = '新章名'
    state['chapters'].append({'chapter': 3, 'title': '尾声', 'status': 'done', 'body': '尾声'})
    state['book']['chapters'].append({'chapter': 3, 'title': '尾声', 'status': 'done'})
    state['book']['chapters_done'] = 3
    state['book']['bible_version'] = 4
    status = run(sources.source_status('owner', project['id']))
    assert status['drift'] == {'state': 'changed', 'changed': [1, 2], 'added': [3], 'removed': [], 'bible_changed': True,
                              'book_status': 'completed', 'eligible': True, 'reason': None}
    assert sql('SELECT * FROM studio_snapshots') == before
    status = run(sources.sync_source('owner', project['id'], 1))
    assert status['snapshot']['no'] == 2 and status['drift']['state'] == 'unchanged'
    assert storage.resolve_path(f"{project['id']}/source/snap-0001/snapshot.json").exists()
    state['chapters'].pop()
    state['book']['chapters'].pop()
    state['book']['chapters_done'] = 2
    assert run(sources.source_status('owner', project['id']))['drift']['removed'] == [3]
    with pytest.raises(HTTPException) as exc:
        run(sources.sync_source('owner', project['id'], 1))
    assert exc.value.status_code == 409
    state['deleted'] = True
    assert run(sources.source_status('owner', project['id']))['drift']['state'] == 'unavailable'
    assert len(run(sources.read_snapshot('owner', project['id'], 1, 3))) == 3


def test_sync_rejects_ineligible_and_busy_brain(workshop, monkeypatch):
    _, _, state = workshop
    project = novel_project(workshop)
    state['book']['chapters'][0]['status'] = 'stale'
    with pytest.raises(HTTPException) as exc:
        run(sources.sync_source('owner', project['id'], 1))
    assert '待复核' in exc.value.detail
    state['book']['chapters'][0]['status'] = 'done'
    original = store._one
    async def busy(db, query, args=()):
        return {'id': 'busy'} if "kind='brain'" in query else await original(db, query, args)
    monkeypatch.setattr(store, '_one', busy)
    with pytest.raises(HTTPException) as exc:
        run(sources.sync_source('owner', project['id'], 1))
    assert exc.value.detail == '导演模型任务进行中，完成后再同步'


@pytest.mark.parametrize('target', ['snapshot.json', 'chapters/0001.md'])
def test_snapshot_hash_tamper_is_logged_500(workshop, target, caplog):
    project = novel_project(workshop)
    storage.resolve_path(f"{project['id']}/source/snap-0001/{target}").write_text('篡改')
    with pytest.raises(HTTPException) as exc:
        run(sources.read_snapshot('owner', project['id'], 1, 1))
    assert exc.value.status_code == 500 and 'Invalid snapshot' in caplog.text


@pytest.mark.parametrize('failure', ['write', 'database'])
def test_snapshot_failure_rolls_back_project_and_directory(workshop, monkeypatch, failure):
    if failure == 'write':
        count = 0
        original = sources._write_file
        def failing(path, data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('disk failed')
            original(path, data)
        monkeypatch.setattr(sources, '_write_file', failing)
    else:
        sql("CREATE TRIGGER reject_snapshot BEFORE INSERT ON studio_snapshots BEGIN SELECT RAISE(ABORT,'snapshot failed'); END")
    with pytest.raises((OSError, aiosqlite.IntegrityError)):
        run(sources.create_novel_project('owner', 'book'))
    assert sql('SELECT * FROM studio_projects') == []
    assert sql('SELECT * FROM studio_snapshots') == []
    assert not list(storage.storage_root().glob('*/source/snap-*'))


def test_snapshot_path_rejects_escape(workshop, tmp_path):
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    with pytest.raises(ValueError):
        sources._write_snapshot('../outside', 1, snapshot)
    root = storage.storage_root(create=True)
    (root / 'escaped').symlink_to(tmp_path)
    with pytest.raises(HTTPException) as exc:
        sources._write_snapshot('escaped', 1, snapshot)
    assert exc.value.status_code == 404


@pytest.mark.parametrize('raw,encoding', [(b'\xef\xbb\xbfhello\r\nworld\x00\x01', 'utf-8'), ('山月\r续篇'.encode('gb18030'), 'gb18030'), (' 山月\t \n', 'text')])
def test_normalize_text_encodings_and_control_characters(raw, encoding):
    text, actual = sources.normalize_text(raw)
    assert actual == encoding and '\r' not in text and '\x00' not in text and '\x01' not in text


def docx(document):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', document)
    return result.getvalue()


def test_docx_paragraph_tab_and_break():
    raw = docx('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>山</w:t><w:tab/><w:t>月</w:t><w:br/><w:t>明</w:t></w:r></w:p><w:p><w:r><w:t>归来</w:t></w:r></w:p></w:body></w:document>')
    assert sources.normalize_text(raw, 'novel.docx') == ('山\t月\n明\n归来', 'docx')


@pytest.mark.parametrize('raw', [b'<!DOCTYPE a><a/>', '<!DOCTYPE a><a/>'.encode('utf-16'), '<!DOCTYPE a><a/>'.encode('utf-32'), b'x' * (sources.MAX_DOCUMENT_BYTES + 1)])
def test_docx_rejects_doctype_and_expansion(raw):
    with pytest.raises(HTTPException) as exc:
        sources.normalize_text(docx(raw), 'book.docx')
    assert exc.value.status_code == 422


@pytest.mark.parametrize('raw,filename,reason', [(b'\xff', None, '无法识别文件编码'), (b'', None, '不能为空'), (b'broken', 'a.docx', 'Word 文件无效'), (b'x' * (sources.MAX_UPLOAD_BYTES + 1), 'a.txt', '10 MB')])
def test_invalid_text_422(raw, filename, reason):
    with pytest.raises(HTTPException) as exc:
        sources.normalize_text(raw, filename)
    assert exc.value.status_code == 422 and reason in exc.value.detail


@pytest.mark.parametrize('text,style', [('前言\n第１章 初见\n甲\n第两回 再见\n乙', '第X章'), ('Chapter I Start\nA\nchapter 2 End\nB', 'Chapter N'), ('# 开始\n甲\n### 后来\n乙', 'markdown'), ('# 前言\n第1章 初见\nChapter 1\n第2章 结尾\nChapter 2', '第X章')])
def test_heading_styles_priority_and_offsets(text, style):
    chunks = sources.split_text(text)
    assert chunks.heading_style == style and chunks.split == 'headings'
    for item in chunks:
        assert text[item['start']:item['end']] == item['body']
    if text.startswith('前言'):
        assert chunks[0]['title'] == '前言'


@pytest.mark.parametrize('text', ['甲' * 6000 + '\n\n' + '乙' * 6000, '甲' * 9000 + '。' + '乙' * 9000, '甲' * 20001, '甲' * 8000 + '\n' + '乙' * 8000])
def test_chunk_boundaries_and_offsets(text):
    chunks = sources.split_text(text)
    assert chunks.split == 'chunks' and chunks.heading_style is None
    assert ''.join(item['body'] for item in chunks) == text
    assert all(text[item['start']:item['end']] == item['body'] for item in chunks)
    assert all(len(item['body']) <= 10_001 for item in chunks)
    assert chunks[0]['title'] == '第 1 段'


def test_text_project_full_offsets_limits_and_blank_source(workshop):
    client, auth, _ = workshop
    text = '前言\n第1章 初见\n甲\n第2章 结尾\n乙'
    response = client.post('/studio/projects/from-text', headers=auth, data={'title': '粘贴作品', 'aspect': '9:16', 'kind': 'paste', 'text': text})
    assert response.status_code == 201, response.text
    project = response.json()
    assert project['source_kind'] == 'paste' and project['aspect'] == '9:16'
    directory = storage.resolve_path(f"{project['id']}/source/snap-0001")
    full = (directory / 'full.txt').read_text()
    manifest = json.loads((directory / 'snapshot.json').read_text())
    for item in manifest['chapters']:
        assert full[item['start']:item['end']] == (directory / item['file']).read_text()
    assert run(sources.source_status('owner', project['id']))['drift'] == {'state': 'not_applicable'}
    blank = run(store.create_project('owner', '空白', '16:9'))
    assert run(sources.source_status('owner', blank['id'])) == {'kind': None}
    with pytest.raises(HTTPException):
        run(sources.sync_source('owner', project['id'], 1))
    before = sql('SELECT * FROM studio_projects')
    response = client.post('/studio/projects/from-text', headers=auth, data={'title': '超长', 'kind': 'paste', 'text': '甲' * 500001})
    assert response.status_code == 422 and response.json()['detail'] == '作品超过 50 万字，暂不支持'
    assert sql('SELECT * FROM studio_projects') == before


def test_novel_over_limit_writes_nothing(workshop):
    _, _, state = workshop
    state['chapters'][0]['body'] = '甲' * 500001
    with pytest.raises(HTTPException) as exc:
        run(sources.create_novel_project('owner', 'book'))
    assert exc.value.status_code == 422
    assert sql('SELECT * FROM studio_projects') == []
    assert not storage.storage_root().exists()


@pytest.mark.parametrize('body,files', [({'title': '上传', 'kind': 'upload'}, {'file': ('book.md', b'# 1\nhello\n# 2\nworld')}), ({'title': '上传', 'kind': 'upload'}, {'file': ('book.txt', '山月'.encode('gb18030'))})])
def test_upload_routes(workshop, body, files):
    client, auth, _ = workshop
    response = client.post('/studio/projects/from-text', headers=auth, data=body, files=files)
    assert response.status_code == 201, response.text
    assert response.json()['source_kind'] == 'upload'


@pytest.mark.parametrize('data', [{'title': '文本', 'kind': 'paste', 'text': '甲', 'unknown': 'x'}, {'title': '文本', 'kind': 'paste', 'text': '甲', 'aspect': '1:1'}, {'title': '文本', 'kind': 'other', 'text': '甲'}, {'title': ' ', 'kind': 'paste', 'text': '甲'}])
def test_text_form_extra_and_constraints(workshop, data):
    client, auth, _ = workshop
    assert client.post('/studio/projects/from-text', headers=auth, data=data).status_code == 422


@pytest.mark.parametrize('kind', ['new', 'legacy'])
def test_exchange_import_and_list_summary_only(workshop, monkeypatch, kind):
    import exchange_store
    client, auth, _ = workshop
    exchange = {'id': 'exchange', 'topic': '旅行短片', 'viewer_role': 'initiator', 'recipient': {'id': 'official:short-video-creator'},
                'status': 'completed', 'artifact': '成稿' if kind == 'new' else '', 'summary': '旧成稿',
                'updated_at': 'date', 'artifact_status': 'final', 'workflow_version': 2 if kind == 'new' else None}
    async def details(user, eid):
        return {'exchange': deepcopy(exchange)}
    async def listing(user, **kwargs):
        return [deepcopy(exchange)]
    monkeypatch.setattr(exchange_store, 'exchange_details', details)
    monkeypatch.setattr(exchange_store, 'list_exchanges', listing)
    response = client.get('/studio/sources/exchanges', headers=auth)
    assert response.status_code == 200
    assert response.json()[0]['chars'] == (2 if kind == 'new' else 3)
    assert 'artifact' not in response.json()[0] and 'summary' not in response.json()[0]
    response = client.post('/studio/projects/from-exchange', headers=auth, json={'exchange_id': 'exchange'})
    assert response.status_code == 201
    assert response.json()['source_kind'] == 'exchange' and response.json()['source_ref'] == 'exchange'


@pytest.mark.parametrize('changes', [{'viewer_role': 'recipient'}, {'recipient': {'id': 'official:script-editor'}}, {'status': 'running'}, {'artifact': '', 'summary': ''}])
def test_exchange_ownership_partner_completion_and_artifact(workshop, monkeypatch, changes):
    import exchange_store
    exchange = {'id': 'exchange', 'topic': '短片', 'viewer_role': 'initiator', 'recipient': {'id': 'official:short-video-creator'},
                'status': 'completed', 'artifact': '成稿', **changes}
    async def details(user, eid):
        return {'exchange': exchange}
    monkeypatch.setattr(exchange_store, 'exchange_details', details)
    with pytest.raises(HTTPException) as exc:
        run(sources.take_exchange_snapshot('owner', 'exchange'))
    assert exc.value.status_code == 404 and exc.value.detail == '交流不存在或没有成稿'


NEW_ENDPOINTS = [('GET', '/studio/sources/novels'), ('GET', '/studio/sources/novels/search?q=x'),
                 ('GET', '/studio/sources/exchanges'), ('POST', '/studio/projects/from-novel'),
                 ('POST', '/studio/projects/from-text'), ('POST', '/studio/projects/from-exchange'),
                 ('GET', '/studio/projects/foreign/source'), ('POST', '/studio/projects/foreign/source/sync')]


@pytest.mark.parametrize('method,path', NEW_ENDPOINTS)
def test_new_routes_hidden_for_non_authors(workshop, method, path):
    client, _, _ = workshop
    response = client.request(method, path, headers={**headers('outsider'), 'Content-Type': 'application/json'}, content=b'{')
    assert response.status_code == 404 and response.json() == {'detail': 'Not Found'}


def test_novel_disabled_and_foreign_resources(workshop, monkeypatch):
    client, auth, _ = workshop
    monkeypatch.setenv('FIONA_NOVEL', '0')
    assert client.get('/studio/sources/novels', headers=auth).json() == {'enabled': False, 'books': []}
    assert client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book'}).status_code == 404
    monkeypatch.setenv('FIONA_NOVEL', '1')
    project = novel_project(workshop)
    foreign = headers('other')
    assert client.post('/studio/projects/from-novel', headers=foreign, json={'book_id': 'book'}).json() == {'detail': '作品不存在或无权访问'}
    assert client.get(f"/studio/projects/{project['id']}/source", headers=foreign).status_code == 404
    assert client.post(f"/studio/projects/{project['id']}/source/sync", headers=foreign, json={'expected_no': 1}).status_code == 404


def test_schema_migration_adds_columns_on_existing_tables():
    async def migrate():
        async with aiosqlite.connect(':memory:') as db:
            await db.execute('CREATE TABLE studio_projects (id TEXT, owner TEXT)')
            await db.execute('CREATE TABLE studio_jobs (id TEXT, owner TEXT, project_id TEXT)')
            await store.migrate_schema(db)
            await store.migrate_schema(db)
            async with db.execute('PRAGMA table_info(studio_projects)') as cursor:
                columns = {row[1]: row for row in await cursor.fetchall()}
            assert {'source_kind', 'source_ref', 'snapshot_no'} <= columns.keys()
            assert columns['snapshot_no'][4] == '0'
    run(migrate())


def test_studio_sources_only_call_allowlisted_novel_functions():
    import ast
    directory = Path(__file__).parents[1] / 'studio'
    allowed = {'list_books', 'find_books', 'detail', 'bible', 'chapter', 'chapters_range'}
    for path in directory.rglob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('novel.'):
                assert node.module == 'novel.runner' and {alias.name for alias in node.names} <= {'is_editing'}, path
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'service':
                assert node.attr in allowed, (path, node.attr)
        assert not re.search(r'(?:FROM|INTO|UPDATE|JOIN)\s+novel(?:s|_)', path.read_text(), re.I), path


def test_account_deletion_removes_snapshot_rows_and_queues_project_directory(workshop):
    from database import delete_account_data
    project = novel_project(workshop)
    result = run(delete_account_data('owner'))
    assert result['deleted'] and f"studio:{project['id']}" in result['upload_paths']
    assert sql('SELECT * FROM studio_snapshots') == []
    assert sql('SELECT * FROM studio_projects') == []


def test_novel_errors_do_not_leak_and_boolean_sync_rejected(workshop, monkeypatch):
    client, auth, _ = workshop
    project = novel_project(workshop)
    response = client.post(f"/studio/projects/{project['id']}/source/sync", headers=auth, json={'expected_no': True})
    assert response.status_code == 422
    for expected in (0, -1):
        response = client.post(f"/studio/projects/{project['id']}/source/sync", headers=auth, json={'expected_no': expected})
        assert response.status_code == 409 and response.json() == {'detail': '快照已更新，请重新检查'}
    async def fail(*args):
        raise HTTPException(422, '小说工坊内部错误不要外泄')
    monkeypatch.setattr(sources.service, 'detail', fail)
    response = client.post('/studio/projects/from-novel', headers=auth, json={'book_id': 'book'})
    assert response.status_code == 409 and response.json() == {'detail': '作品读取失败，请稍后再试'}


def test_editing_at_end_forces_retry(workshop, monkeypatch):
    _, _, state = workshop
    phases = iter([False, True, False, False])
    monkeypatch.setattr(sources, 'is_editing', lambda bid: next(phases))
    run(sources.take_novel_snapshot('owner', 'book'))
    assert state['details'] == 4 and len(state['range_calls']) == 2


def test_snapshot_table_enforces_existing_owner_and_kind(workshop):
    project = novel_project(workshop)
    row = sql('SELECT * FROM studio_snapshots')[0]
    # Column order: id, project_id, owner, no, kind, ...
    for column, replacement in [(2, 'other'), (4, 'bad')]:
        invalid = list(row)
        invalid[0], invalid[3], invalid[column] = 'invalid', 2, replacement
        async def insert():
            import database
            async with aiosqlite.connect(database.DB_PATH) as db:
                await db.execute('PRAGMA foreign_keys=ON')
                await db.execute('INSERT INTO studio_snapshots VALUES(' + ','.join('?' for _ in invalid) + ')', invalid)
                await db.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            run(insert())
    assert len(sql('SELECT * FROM studio_snapshots')) == 1
    assert project['snapshot_no'] == 1


def test_heavy_sources_operations_use_to_thread(workshop, monkeypatch):
    original = asyncio.to_thread
    calls = []
    async def recording(function, *args, **kwargs):
        calls.append(function.__name__)
        return await original(function, *args, **kwargs)
    monkeypatch.setattr(sources.asyncio, 'to_thread', recording)
    project = run(sources.create_novel_project('owner', 'book'))
    assert {'_assemble_novel_snapshot', '_write_snapshot'} <= set(calls)
    calls.clear()
    run(sources.create_text_project('owner', 'paste', '文本', '第1章 初见\n甲\n第2章 尾声\n乙'))
    assert {'normalize_text', 'split_text', '_assemble_text_snapshot', '_write_snapshot'} <= set(calls)
    calls.clear()
    run(sources.source_status('owner', project['id']))
    run(sources.read_snapshot('owner', project['id'], 1, 2))
    assert {'_read_manifest', '_compare_drift', '_read_snapshot_chunks'} <= set(calls)
    calls.clear()
    sql("CREATE TRIGGER reject_thread_snapshot BEFORE INSERT ON studio_snapshots BEGIN SELECT RAISE(ABORT,'snapshot failed'); END")
    with pytest.raises(aiosqlite.IntegrityError):
        run(sources.create_novel_project('owner', 'book'))
    assert '_discard_directory' in calls


def test_exchange_normalization_and_artifact_selection_use_threads(workshop, monkeypatch):
    import exchange_store
    exchange = {'id': 'exchange', 'topic': '短片', 'viewer_role': 'initiator', 'recipient': {'id': 'official:short-video-creator'},
                'status': 'completed', 'artifact': '成稿', 'updated_at': 'date', 'artifact_status': 'final', 'workflow_version': 2}
    async def details(user, eid):
        return {'exchange': deepcopy(exchange)}
    async def listing(user, **kwargs):
        return [deepcopy(exchange)]
    monkeypatch.setattr(exchange_store, 'exchange_details', details)
    monkeypatch.setattr(exchange_store, 'list_exchanges', listing)
    original, calls = asyncio.to_thread, []
    async def recording(function, *args, **kwargs):
        calls.append(function.__name__)
        return await original(function, *args, **kwargs)
    monkeypatch.setattr(sources.asyncio, 'to_thread', recording)
    assert run(sources.list_exchanges('owner'))[0]['chars'] == 2
    run(sources.take_exchange_snapshot('owner', 'exchange'))
    assert calls.count('normalize_text') == 2 and calls.count('_exchange_artifact') == 2
    assert {'split_text', '_assemble_text_snapshot'} <= set(calls)


@pytest.mark.parametrize('operation', ['normalize_text', 'split_text', '_assemble_novel_snapshot', '_assemble_text_snapshot',
                                       '_write_snapshot', '_read_manifest', '_read_snapshot_chunks', '_compare_drift', '_discard_directory'])
def test_sources_workers_leave_event_loop_responsive(workshop, monkeypatch, operation):
    project = novel_project(workshop) if operation in {'_read_manifest', '_read_snapshot_chunks', '_compare_drift'} else None
    if operation == '_discard_directory':
        sql("CREATE TRIGGER reject_responsive_snapshot BEFORE INSERT ON studio_snapshots BEGIN SELECT RAISE(ABORT,'snapshot failed'); END")
    original = getattr(sources, operation)
    started, release = threading.Event(), threading.Event()
    async def scenario():
        event_loop_thread = threading.get_ident()
        def blocked(*args, **kwargs):
            assert threading.get_ident() != event_loop_thread
            started.set()
            assert release.wait(5), 'event loop did not release worker'
            return original(*args, **kwargs)
        monkeypatch.setattr(sources, operation, blocked)
        if operation in {'normalize_text', 'split_text', '_assemble_text_snapshot'}:
            action = sources.create_text_project('owner', 'paste', '文本', '甲\n\n乙')
        elif operation == '_read_snapshot_chunks':
            action = sources.read_snapshot('owner', project['id'], 1, 2)
        elif operation in {'_read_manifest', '_compare_drift'}:
            action = sources.source_status('owner', project['id'])
        else:
            action = sources.create_novel_project('owner', 'book')
        task = asyncio.create_task(action)
        try:
            assert await asyncio.to_thread(started.wait, 5)
            for _ in range(3):
                await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
            if operation == '_discard_directory':
                with pytest.raises(aiosqlite.IntegrityError):
                    await task
            else:
                await task
    run(scenario())


@pytest.mark.parametrize('point', ['before_write', 'after_rename', 'cleanup'])
def test_repeated_cancellation_drains_write_and_cleanup_workers(workshop, monkeypatch, point):
    started, release = threading.Event(), threading.Event()
    cleanup_started, cleanup_release = threading.Event(), threading.Event()
    original_write, original_discard = sources._write_snapshot, sources._discard_directory
    def delayed_write(*args):
        if point == 'before_write':
            started.set()
            assert release.wait(5)
        result = original_write(*args)
        if point != 'before_write':
            started.set()
            assert release.wait(5)
        return result
    def delayed_cleanup(*args):
        cleanup_started.set()
        if point == 'cleanup':
            assert cleanup_release.wait(5)
        return original_discard(*args)
    monkeypatch.setattr(sources, '_write_snapshot', delayed_write)
    monkeypatch.setattr(sources, '_discard_directory', delayed_cleanup)
    async def scenario():
        task = asyncio.create_task(sources.create_novel_project('owner', 'book'))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            assert await asyncio.to_thread(cleanup_started.wait, 5)
            if point == 'cleanup':
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
        finally:
            release.set()
            cleanup_release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert await store.list_projects('owner') == []
    run(scenario())
    assert sql('SELECT * FROM studio_snapshots') == []
    assert not list(storage.storage_root().glob('*/source/snap-*'))


@pytest.mark.parametrize('code', [errno.EEXIST, errno.ENOTEMPTY, errno.EISDIR])
def test_rename_competitor_returns_409_and_keeps_winner(workshop, monkeypatch, code):
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    target = storage.resolve_path('race/source/snap-0001')
    original = Path.rename
    def raced(path, destination):
        if '.part-' in path.name:
            destination.mkdir()
            (destination / 'winner.txt').write_text('winner')
            raise OSError(code, 'concurrent rename')
        return original(path, destination)
    monkeypatch.setattr(Path, 'rename', raced)
    with pytest.raises(HTTPException) as exc:
        sources._write_snapshot('race', 1, snapshot)
    assert exc.value.status_code == 409 and exc.value.detail == '快照已更新，请重新检查'
    assert (target / 'winner.txt').read_text() == 'winner'
    assert not list(target.parent.glob('*.part-*'))


def test_existing_snapshot_target_returns_409_without_part(workshop):
    snapshot = run(sources.take_novel_snapshot('owner', 'book'))
    target = storage.resolve_path('existing/source/snap-0001')
    target.mkdir(parents=True)
    (target / 'winner.txt').write_text('winner')
    with pytest.raises(HTTPException) as exc:
        sources._write_snapshot('existing', 1, snapshot)
    assert exc.value.status_code == 409
    assert (target / 'winner.txt').read_text() == 'winner'
    assert not list(target.parent.glob('*.part-*'))


def test_directory_fsync_runs_after_rename(workshop, monkeypatch):
    original, parents = sources._fsync_directory, []
    def recording(parent):
        assert (parent / 'snap-0001' / 'snapshot.json').is_file()
        parents.append(parent)
        return original(parent)
    monkeypatch.setattr(sources, '_fsync_directory', recording)
    project = novel_project(workshop)
    assert parents == [storage.resolve_path(f"{project['id']}/source")]


def test_posix_directory_fsync_failure_removes_owned_target_and_project(workshop, monkeypatch):
    def failing(parent):
        raise OSError(errno.EIO, 'directory fsync failed')
    monkeypatch.setattr(sources, '_fsync_directory', failing)
    with pytest.raises(OSError) as exc:
        run(sources.create_novel_project('owner', 'book'))
    assert exc.value.errno == errno.EIO
    assert sql('SELECT * FROM studio_snapshots') == [] and sql('SELECT * FROM studio_projects') == []
    assert not list(storage.storage_root().glob('*/source/snap-*'))


@pytest.mark.parametrize('platform,code,ignored', [('nt', errno.EACCES, True), ('nt', errno.EINVAL, True),
                                                 ('nt', errno.EIO, False), ('posix', errno.EINVAL, False),
                                                 ('posix', errno.EIO, False)])
def test_directory_fsync_ignores_only_windows_unsupported_errors(monkeypatch, platform, code, ignored):
    from types import SimpleNamespace
    def fail(*args):
        raise OSError(code, 'directory unsupported or failed')
    fake_os = SimpleNamespace(name=platform, open=fail, fsync=lambda descriptor: None, close=lambda descriptor: None,
                              O_RDONLY=0, O_DIRECTORY=0)
    monkeypatch.setattr(sources, 'os', fake_os)
    if ignored:
        sources._fsync_directory('unused')
    else:
        with pytest.raises(OSError) as exc:
            sources._fsync_directory('unused')
        assert exc.value.errno == code


@pytest.mark.parametrize('workflow,artifact,summary,eligible', [(None, '', '旧成稿', True), (0, '', '旧成稿', True),
                                                              (2, '', '阶段摘要', False), ('draft_review_v1', ' ', '阶段摘要', False),
                                                              (2, '正式成稿', '阶段摘要', True)])
def test_summary_fallback_only_for_legacy_workflows(workshop, monkeypatch, workflow, artifact, summary, eligible):
    import exchange_store
    exchange = {'id': 'exchange', 'topic': '短片', 'viewer_role': 'initiator', 'recipient': {'id': 'official:short-video-creator'},
                'status': 'completed', 'workflow_version': workflow, 'artifact': artifact, 'summary': summary}
    async def details(user, eid):
        return {'exchange': exchange}
    monkeypatch.setattr(exchange_store, 'exchange_details', details)
    if eligible:
        snapshot = run(sources.take_exchange_snapshot('owner', 'exchange'))
        assert snapshot['full'] == (artifact or summary)
    else:
        with pytest.raises(HTTPException) as exc:
            run(sources.take_exchange_snapshot('owner', 'exchange'))
        assert exc.value.status_code == 404 and exc.value.detail == '交流不存在或没有成稿'
