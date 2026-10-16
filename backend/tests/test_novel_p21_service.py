"""Offline P2.1 service/API contracts, character edits, export, and reads."""

import asyncio
from copy import deepcopy
import inspect
import json
from urllib.parse import quote

from fastapi import HTTPException
import pytest

import database
from novel import runner, service
from novel.schemas import compact
from novel.store_db import get_db
from rate_limit import limiter


USER = 'p21-author'
OTHER = 'p21-other'
BOOK = 'p21-book'
HEADERS = {'X-Dev-User': USER}
APPEARANCE = '齐肩黑发束在脑后，身形清瘦，穿洗旧的深蓝长外套，左眉有一道浅疤。'


def run(coroutine):
    return asyncio.run(coroutine)


def bible_data():
    return {
        'version': 7,
        'locked': {
            'characters': [
                {'id': 'C1', 'name': '林宁', 'role': 'protagonist', 'age': '三十岁',
                 'appearance': '', 'personality': '谨慎', 'motivation': '寻找原件'},
                {'id': 'C2', 'name': '周临', 'role': 'supporting', 'age': '四十岁',
                 'appearance': APPEARANCE, 'personality': '沉默', 'motivation': '守护证人'},
            ],
            'world_rules': ['原件不可复制'], 'style_guide': {'tone': '克制'},
            'adaptation': {'max_main_characters': 6, 'max_scenes_per_chapter': 3},
        },
        'dynamic': {
            'character_states': {'C1': {'location': '档案室', 'knows': ['档案不完整']},
                                 'C2': {'location': '街口', 'knows': []}},
            'chapter_summaries': [{'chapter': n, 'title': f'旧事{n}', 'summary': '旧事摘要'}
                                  for n in range(1, 61)],
            'arc_summaries': [{'start_chapter': 1, 'end_chapter': 10, 'summary': '旧档案'}],
            'timeline': ['林宁找到纸条'], 'foreshadowing': [], 'used_beats': ['失落档案'],
        },
    }


async def seed_book(novel_id=BOOK, *, username=USER, title='旧档案 Novel', status='completed', created='2026-10-16 10:00:00'):
    config = {'target': {'max_chapters': 70}, 'agents': {}, 'drama_adaptation': False}
    compass = {'title': title, 'theme': '真相', 'main_threads': [{'id': 'T1', 'name': '找原件'}]}
    async with get_db() as db:
        await db.execute(
            'INSERT INTO novels(id,username,title,seed_idea,status,config_json,compass_json,bible_version,chapters_done,budget_strawberries,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (novel_id, username, title, '旧档案', status, service.encoded(config), service.encoded(compass), 7, 3, 100000, created),
        )
        await db.execute(
            'INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)',
            (novel_id, username, 7, service.encoded(bible_data()), 'archive'),
        )
        await db.commit()


async def seed_chapter(number, *, novel_id=BOOK, status='done', body=None):
    body = f'# 第{number}章 档案\n\n正文{number}。' if body is None else body
    async with get_db() as db:
        await db.execute(
            'INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json,edited_by_user) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (novel_id, USER, number, status, f'档案{number}', body,
             service.encoded(['人名待核对']), service.encoded({'decision': {'chapter': number}}),
             service.encoded([{'issues': [{'id': 'I1'}], 'dropped_issues': [{'id': 'I2'}]}]),
             service.encoded({'summary': '档案摘要'}), 1),
        )
        await db.commit()


async def persisted():
    async with get_db() as db:
        book = await service.row(db, 'SELECT * FROM novels WHERE id=?', (BOOK,))
        versions = await service.rows(db, 'SELECT * FROM novel_bible_versions WHERE novel_id=? ORDER BY version', (BOOK,))
        chapters = await service.rows(db, 'SELECT * FROM novel_chapters WHERE novel_id=? ORDER BY chapter', (BOOK,))
    return book, versions, chapters


@pytest.fixture
def workshop(client, monkeypatch):
    monkeypatch.setenv('FIONA_NOVEL', '1')
    monkeypatch.setenv('FIONA_NOVEL_USERS', USER+','+OTHER)
    monkeypatch.setattr(limiter, 'enabled', False)
    run(database.get_or_create_user(USER))
    run(database.get_or_create_user(OTHER))
    return client


@pytest.fixture
def book(workshop):
    run(seed_book())
    run(seed_chapter(1))
    run(seed_chapter(2, status='stale'))
    return workshop


@pytest.mark.parametrize('adaptation', [None, False, True])
def test_create_persists_drama_adaptation_with_default_false(workshop, monkeypatch, adaptation):
    async def no_background(*args):
        pass
    monkeypatch.setattr(runner, 'start_novel', no_background)
    payload = {
        'seed_idea': '旧档案里的秘密',
        'agents': {'editor': 'dashscope:qwen3.8-max', 'writer': 'deepseek:deepseek-flash',
                   'archivist': 'dashscope:qwen3.8-max'},
        'budget_strawberries': 100000,
    }
    if adaptation is not None:
        payload['drama_adaptation'] = adaptation
    response = workshop.post('/novels', json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    expected = bool(adaptation)
    novel_id = response.json()['id']
    assert response.json()['config']['drama_adaptation'] is expected
    async def config():
        async with get_db() as db:
            return json.loads((await service.row(db, 'SELECT config_json FROM novels WHERE id=?', (novel_id,)))['config_json'])
    assert run(config())['drama_adaptation'] is expected
    # This creation-only choice must not become mutable through the old PATCH.
    assert workshop.patch('/novels/'+novel_id, json={'drama_adaptation': not expected}, headers=HEADERS).status_code == 422


@pytest.mark.parametrize('status', ['awaiting_review', 'awaiting_plan', 'awaiting_end', 'paused', 'completed'])
def test_character_patch_allowed_states_versioning_and_full_bible(book, status):
    async def set_status():
        async with get_db() as db:
            await db.execute('UPDATE novels SET status=? WHERE id=?', (status, BOOK))
            await db.commit()
    run(set_status())
    before = book.get(f'/novels/{BOOK}/bible', headers=HEADERS).json()
    old_book, old_versions, old_chapters = run(persisted())
    changes = {'appearance': APPEARANCE, 'personality': '果断且审慎', 'motivation': '把原件交给证人'}
    response = book.patch(f'/novels/{BOOK}/characters/C1', json=changes, headers=HEADERS)
    assert response.status_code == 200, response.text
    expected = deepcopy(before)
    expected['version'] += 1
    expected['locked']['characters'][0].update(changes)
    assert response.json() == expected
    assert len(response.json()['dynamic']['chapter_summaries']) == 60
    assert book.get(f'/novels/{BOOK}/bible', headers=HEADERS).json() == expected
    current, versions, chapters = run(persisted())
    assert current['bible_version'] == old_book['bible_version']+1
    assert {key: value for key, value in current.items() if key not in ('bible_version', 'updated_at')} == {
        key: value for key, value in old_book.items() if key not in ('bible_version', 'updated_at')}
    assert chapters == old_chapters
    assert versions[:-1] == old_versions
    assert versions[-1]['version'] == 8 and versions[-1]['source'] == 'user_edit'
    assert json.loads(versions[-1]['bible_json']) == {key: value for key, value in expected.items() if key != 'compass'}


@pytest.mark.parametrize('changes', [
    {'appearance': APPEARANCE}, {'personality': '  坦率  '}, {'motivation': '  保护同伴  '},
])
def test_character_patch_supports_partial_updates_without_revalidating_old_appearance(book, changes):
    before = book.get(f'/novels/{BOOK}/bible', headers=HEADERS).json()
    response = book.patch(f'/novels/{BOOK}/characters/C1', json=changes, headers=HEADERS)
    assert response.status_code == 200, response.text
    expected = deepcopy(before)
    expected['version'] += 1
    expected['locked']['characters'][0].update({key: value.strip() for key, value in changes.items()})
    assert response.json() == expected


@pytest.mark.parametrize('status,message', [
    ('running', '书正在运行，请先暂停再改人物'),
    ('setup_running', '书正在运行，请先暂停再改人物'),
    ('failed', '这本书已出错，不能修改人物'),
    ('awaiting_setup', '立项阶段请在立项卡里修改'),
])
def test_character_patch_rejects_disallowed_states_without_writing(book, status, message):
    async def set_status():
        async with get_db() as db:
            await db.execute('UPDATE novels SET status=? WHERE id=?', (status, BOOK))
            await db.commit()
    run(set_status())
    before = run(persisted())
    response = book.patch(f'/novels/{BOOK}/characters/C1', json={'appearance': APPEARANCE}, headers=HEADERS)
    assert response.status_code == 409 and response.json()['detail'] == message
    assert run(persisted()) == before


@pytest.mark.parametrize('changes', [
    {}, {'appearance': ''}, {'appearance': '短发'}, {'appearance': '外 '*19},
    {'appearance': '“”'*30+'外'*19}, {'appearance': None}, {'personality': ''},
    {'personality': ' \n\t '}, {'motivation': ''}, {'motivation': None},
    {'name': '新名字'}, {'appearance': APPEARANCE, 'role': 'protagonist'},
])
def test_character_patch_rejects_invalid_fields_without_writing(book, changes):
    before = run(persisted())
    response = book.patch(f'/novels/{BOOK}/characters/C1', json=changes, headers=HEADERS)
    assert response.status_code == 422, response.text
    if 'appearance' in changes and isinstance(changes['appearance'], str) and len(compact(changes['appearance'])) < 20:
        assert response.json()['detail'] == '外形至少写 20 个字'
    assert run(persisted()) == before


def test_character_appearance_uses_compact_twenty_character_boundary(book):
    appearance = '“'+'外 \n'*20+'”'
    assert len(compact(appearance)) == 20
    response = book.patch(f'/novels/{BOOK}/characters/C1', json={'appearance': appearance}, headers=HEADERS)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('novel_id,character_id,user', [
    (BOOK, 'C999', USER), (BOOK, 'C1', OTHER), ('missing', 'C1', USER),
])
def test_character_patch_returns_404_for_missing_or_unowned_records(book, novel_id, character_id, user):
    before = run(persisted())
    response = book.patch(f'/novels/{novel_id}/characters/{character_id}',
                          json={'appearance': APPEARANCE}, headers={'X-Dev-User': user})
    assert response.status_code == 404, response.text
    assert run(persisted()) == before


def test_character_patch_obeys_chapter_edit_exclusion(book, monkeypatch):
    monkeypatch.setattr(runner, 'is_editing', lambda novel_id: novel_id == BOOK)
    before = run(persisted())
    response = book.patch(f'/novels/{BOOK}/characters/C1', json={'appearance': APPEARANCE}, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()['detail'] == '章节正在改稿，请稍后再继续'
    assert run(persisted()) == before


def test_character_patch_paused_before_setup_without_bible_returns_404(book):
    async def remove_bible():
        async with get_db() as db:
            await db.execute("UPDATE novels SET status='paused',bible_version=0 WHERE id=?", (BOOK,))
            await db.execute('DELETE FROM novel_bible_versions WHERE novel_id=?', (BOOK,))
            await db.commit()
    run(remove_bible())
    before = run(persisted())
    response = book.patch(f'/novels/{BOOK}/characters/C1', json={'appearance': APPEARANCE}, headers=HEADERS)
    assert response.status_code == 404 and response.json()['detail'] == '人物不存在'
    assert run(persisted()) == before


def test_export_marks_stale_chapters_without_skipping_or_changing_headers(book):
    run(seed_chapter(3, status='stale'))
    # A chapter without body retains the old export exclusion rule.
    async def bodyless():
        async with get_db() as db:
            await db.execute('INSERT INTO novel_chapters(novel_id,username,chapter,status) VALUES(?,?,?,?)',
                             (BOOK, USER, 4, 'writing'))
            await db.commit()
    run(bodyless())
    response = book.get(f'/novels/{BOOK}/export', headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['content-type'] == 'text/markdown; charset=utf-8'
    assert response.headers['content-disposition'] == "attachment; filename*=UTF-8''"+quote('小说-'+BOOK+'.md')
    expected = '# 旧档案 Novel\n本书有 2 章待复核：第 2、3 章。\n\n'
    expected += '# 第1章 档案\n\n正文1。\n\n'
    expected += '# 第2章 档案\n【待复核】前面章节改过稿，本章尚未按新内容复核。\n\n正文2。\n\n'
    expected += '# 第3章 档案\n【待复核】前面章节改过稿，本章尚未按新内容复核。\n\n正文3。'
    assert response.text == expected


@pytest.mark.parametrize('title,bodies', [
    ('旧档案 Novel', ['# 第1章 档案\n\n正文。', '作者改写的正文\n下一段']),
    (None, []), ('标题', ['']),
])
def test_export_without_stale_is_byte_for_byte_old_logic(workshop, title, bodies):
    run(seed_book(title=title))
    for number, body in enumerate(bodies, 1):
        run(seed_chapter(number, body=body))
    old_output = '# '+(title or '未命名小说')+'\n\n'+'\n\n'.join(bodies)
    assert run(service.export(USER, BOOK)).encode('utf-8') == old_output.encode('utf-8')


def test_export_stale_single_line_body_keeps_all_text(workshop):
    run(seed_book())
    run(seed_chapter(1, status='stale', body='# 第1章 只有标题'))
    result = run(service.export(USER, BOOK))
    assert result.endswith('# 第1章 只有标题\n【待复核】前面章节改过稿，本章尚未按新内容复核。')


def test_find_books_matches_literal_trimmed_case_insensitive_titles_and_ownership(workshop):
    async def prepare():
        await seed_book('first', title='海边 Novel', created='2026-10-16 10:00:00')
        await seed_book('second', title='NOVEL 后记', created='2026-10-16 11:00:00')
        await seed_book('literal', title='百分之%_记录', created='2026-10-16 12:00:00')
        await seed_book('untitled', title=None)
        await seed_book('foreign', username=OTHER, title='Novel 别人的书')
    run(prepare())
    listed = run(service.list_books(USER))
    found = run(service.find_books(USER, '  nOvEl \n'))
    assert found == [item for item in listed if item['id'] in ('first', 'second')]
    assert [item['id'] for item in found] == ['second', 'first']
    assert [item['id'] for item in run(service.find_books(USER, '海边'))] == ['first']
    assert [item['id'] for item in run(service.find_books(USER, '%_'))] == ['literal']
    assert run(service.find_books(USER, 'missing')) == []
    assert run(service.find_books(USER, '')) == []
    assert run(service.find_books(USER, ' \n\t ')) == []
    assert [item['id'] for item in run(service.find_books(OTHER, 'novel'))] == ['foreign']


@pytest.mark.parametrize('start,end,expected', [(1, 1, [1]), (1, 50, [1, 3]), (251, 300, [300]), (300, 300, [300]), (4, 4, [])])
def test_chapters_range_matches_single_chapter_shapes_and_skips_gaps(workshop, start, end, expected):
    run(seed_book())
    for number in (300, 3, 1):
        run(seed_chapter(number, status='stale' if number == 3 else 'done'))
    result = run(service.chapters_range(USER, BOOK, start, end))
    assert [item['chapter'] for item in result] == expected
    assert result == [run(service.chapter(USER, BOOK, number)) for number in expected]
    for item in result:
        assert item['review_summary'] == {'retained': 1, 'discarded': 1}
        assert 'username' not in item
        assert not any(key.endswith('_json') for key in item)


@pytest.mark.parametrize('start,end', [(0, 1), (1, 301), (2, 1), (1, 51), (250, 300), (-1, -1), (1.0, 1), (True, 1)])
def test_chapters_range_rejects_invalid_boundaries(workshop, start, end):
    run(seed_book())
    with pytest.raises(HTTPException) as error:
        run(service.chapters_range(USER, BOOK, start, end))
    assert error.value.status_code == 422


@pytest.mark.parametrize('username,novel_id,start,end', [(OTHER, BOOK, 1, 1), (USER, 'missing', 1, 1), (OTHER, BOOK, 0, 999)])
def test_chapters_range_checks_ownership_before_range(workshop, username, novel_id, start, end):
    run(seed_book())
    with pytest.raises(HTTPException) as error:
        run(service.chapters_range(username, novel_id, start, end))
    assert error.value.status_code == 404


@pytest.mark.parametrize('function,signature', [
    ('list_books', '(username)'), ('detail', '(username, novel_id)'),
    ('bible', '(username, novel_id)'), ('chapter', '(username, novel_id, number)'),
    ('owned', '(db, username, novel_id, states=())'),
])
def test_public_read_signatures_are_preserved(function, signature):
    assert str(inspect.signature(getattr(service, function))) == signature
