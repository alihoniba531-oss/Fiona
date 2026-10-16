"""Offline checks for P2's complete, account-scoped read endpoints."""
import asyncio
from datetime import datetime, timedelta
import json

import pytest

from novel.store_db import get_db


USER = 'novel_p2_author'
OTHER = 'novel_p2_other'
HEADERS = {'X-Dev-User': USER}
BOOK = 'p2-complete-book'


@pytest.fixture
def complete_book(client, monkeypatch):
    monkeypatch.setenv('FIONA_NOVEL', '1')
    monkeypatch.setenv('FIONA_NOVEL_USERS', USER + ',' + OTHER)
    compass = {
        'title': '六十章档案', 'logline': '修复师寻找六十封信的来处。',
        'theme': '记忆与选择', 'core_conflict': '真相与承诺',
        'protagonist_want': '找回信件', 'protagonist_need': '学会信任',
        'candidate_endings': ['公开真相'], 'main_threads': [{'id': 'T1', 'description': '查清信件来源'}],
    }
    bible = {
        'version': 2,
        'locked': {
            'characters': [
                {'id': f'C{n}', 'name': f'人物{n}', 'role': 'main' if n == 1 else 'supporting',
                 'appearance': f'外形{n}', 'personality': f'性格{n}', 'motivation': f'动机{n}'}
                for n in range(1, 61)
            ],
            'world_rules': ['信件记录不会自行改变'],
            'style_guide': {'tone': '克制'},
        },
        'dynamic': {
            'chapter_summaries': [{'chapter': n, 'summary': f'摘要{n}', 'characters': ['C1']} for n in range(1, 61)],
            'arc_summaries': [{'start_chapter': n, 'end_chapter': n + 9, 'summary': f'卷摘要{n}'} for n in range(1, 61, 10)],
            'foreshadowing': [
                {'id': f'F{n}', 'description': f'伏笔{n}', 'status': 'resolved' if n <= 30 else 'open',
                 'planted_chapter': n, 'resolved_chapter': n + 1 if n <= 30 else None}
                for n in range(1, 61)
            ],
            'timeline': [{'chapter': n, 'event': f'事件{n}'} for n in range(1, 61)],
            'used_beats': [f'桥段{n}' for n in range(1, 61)],
            'character_states': {
                f'C{n}': {'last_seen_chapter': n, 'knows': [f'知识{k}' for k in range(1, 61)], 'state': f'状态{n}'}
                for n in range(1, 61)
            },
        },
    }
    expected_notes = []

    async def seed():
        async with get_db() as db:
            await db.execute(
                """INSERT INTO novels(id,username,title,seed_idea,status,config_json,compass_json,
                   bible_version,chapters_done,budget_strawberries)
                   VALUES(?,?,?,'思路','completed','{}',?,2,60,100000)""",
                (BOOK, USER, compass['title'], json.dumps(compass)),
            )
            for version, content in [(1, {'version': 1, 'locked': {}, 'dynamic': {}}), (2, bible)]:
                await db.execute(
                    'INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)',
                    (BOOK, USER, version, json.dumps(content), 'p2-test'),
                )
            # Insert in reverse time order, including equal timestamps, to check
            # both chronological ordering and the deterministic id tie-breaker.
            for number in reversed(range(1, 61)):
                delivered = number != 60
                response = {'note_id': f'N{number}', 'adopted': number % 3 != 0, 'response': f'主编回应{number}'}
                created_at = (datetime(2026, 1, 1) + timedelta(hours=number // 2)).isoformat()
                cursor = await db.execute(
                    """INSERT INTO novel_notes(novel_id,username,text,status,delivered_chapter,response_json,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (BOOK, USER, f'留言{number}', 'delivered' if delivered else 'pending',
                     number if delivered else None, json.dumps(response) if delivered else None, created_at),
                )
                expected_notes.append({
                    'id': cursor.lastrowid, 'text': f'留言{number}',
                    'status': 'delivered' if delivered else 'pending',
                    'delivered_chapter': number if delivered else None, 'created_at': created_at,
                    'adopted': response['adopted'] if delivered else None,
                    'response': response['response'] if delivered else None,
                })
            await db.execute(
                "INSERT INTO novel_notes(novel_id,username,text,status) VALUES('another-book',?,'别本书的留言','pending')",
                (USER,),
            )
            await db.commit()

    asyncio.run(seed())
    return client, {**bible, 'compass': compass}, sorted(expected_notes, key=lambda item: (item['created_at'], item['id']))


def test_complete_bible_keeps_all_sixty_chapters(complete_book):
    client, expected, _ = complete_book
    response = client.get(f'/novels/{BOOK}/bible', headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json() == expected
    dynamic = response.json()['dynamic']
    for key in ('chapter_summaries', 'foreshadowing', 'timeline', 'used_beats', 'character_states'):
        assert len(dynamic[key]) == 60
    assert len(dynamic['arc_summaries']) == 6
    assert len(dynamic['character_states']['C1']['knows']) == 60
    assert len(response.json()['locked']['characters']) == 60
    # P1's bounded detail response continues to keep its existing semantics.
    detail = client.get(f'/novels/{BOOK}', headers=HEADERS)
    assert detail.status_code == 200
    assert len(detail.json()['bible']['dynamic']['chapter_summaries']) == 10


def test_complete_notes_keep_all_sixty_responses_in_time_order(complete_book):
    client, _, expected = complete_book
    response = client.get(f'/novels/{BOOK}/notes', headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert len(response.json()) == 60
    assert any(item['adopted'] is False for item in response.json())
    pending = next(item for item in response.json() if item['status'] == 'pending')
    assert pending['delivered_chapter'] is None
    assert pending['adopted'] is None and pending['response'] is None
    assert all(set(item) == {'id', 'text', 'status', 'delivered_chapter', 'created_at', 'adopted', 'response'} for item in response.json())


@pytest.mark.parametrize('endpoint', ['bible', 'notes'])
def test_complete_read_does_not_reveal_another_accounts_book(complete_book, endpoint):
    client, _, _ = complete_book
    response = client.get(f'/novels/{BOOK}/{endpoint}', headers={'X-Dev-User': OTHER})
    assert response.status_code == 404
    assert response.json()['detail'] == '小说不存在'


@pytest.mark.parametrize('endpoint', ['bible', 'notes'])
def test_complete_read_is_hidden_when_workshop_is_disabled(complete_book, monkeypatch, endpoint):
    client, _, _ = complete_book
    monkeypatch.setenv('FIONA_NOVEL', '0')
    response = client.get(f'/novels/{BOOK}/{endpoint}', headers=HEADERS)
    assert response.status_code == 404


@pytest.mark.parametrize('endpoint', ['bible', 'notes'])
def test_complete_read_requires_the_workshop_whitelist(complete_book, monkeypatch, endpoint):
    client, _, _ = complete_book
    monkeypatch.setenv('FIONA_NOVEL_USERS', OTHER)
    response = client.get(f'/novels/{BOOK}/{endpoint}', headers=HEADERS)
    assert response.status_code == 403
    assert response.json()['detail'] == '小说工坊暂未对该账号开放'


@pytest.mark.parametrize('endpoint', ['bible', 'notes'])
def test_complete_read_returns_404_for_a_missing_book(complete_book, endpoint):
    client, _, _ = complete_book
    assert client.get(f'/novels/missing/{endpoint}', headers=HEADERS).status_code == 404


def test_setup_without_a_bible_has_null_bible_and_empty_notes(complete_book):
    client, _, _ = complete_book

    async def seed():
        async with get_db() as db:
            await db.execute(
                """INSERT INTO novels(id,username,seed_idea,status,config_json,budget_strawberries)
                   VALUES('p2-setup',?,'思路','setup_running','{}',100000)""", (USER,),
            )
            await db.commit()

    asyncio.run(seed())
    response = client.get('/novels/p2-setup/bible', headers=HEADERS)
    assert response.status_code == 200 and response.json() is None
    response = client.get('/novels/p2-setup/notes', headers=HEADERS)
    assert response.status_code == 200 and response.json() == []


def test_list_and_detail_add_only_authorized_metadata_and_track_same_length_edits(complete_book):
    from novel.writing import compact_length

    client, _, _ = complete_book
    original_body = '# 第1章 第一封信\n\n旧正文。'
    edited_body = '# 第1章 第一封信\n\n新正文。'
    second_body = '# 第2章 下一封信\n\n另一封信。'
    summary_fields = {
        'id', 'title', 'status', 'pause_reason', 'bible_version', 'chapters_done', 'words_done',
        'budget_strawberries', 'spent_strawberries', 'reserved_strawberries',
        'created_at', 'updated_at', 'completed_at',
    }

    async def seed():
        async with get_db() as db:
            await db.execute('UPDATE novels SET config_json=? WHERE id=?', (
                json.dumps({'target': {'min_chapters': 60, 'max_chapters': 137, 'chapter_words': 2000}}), BOOK,
            ))
            for number, body, edited in [(1, original_body, 0), (2, second_body, 1)]:
                await db.execute(
                    """INSERT INTO novel_chapters(novel_id,username,chapter,title,status,body,flags_json,edited_by_user)
                       VALUES(?,?,?,?,'done',?,?,?)""",
                    (BOOK, USER, number, '第一封信' if number == 1 else '下一封信', body, '["deviation"]', edited),
                )
            await db.commit()
            async with db.execute('SELECT * FROM novels WHERE id=?', (BOOK,)) as cursor:
                raw_book = dict(await cursor.fetchone())
        return {key: raw_book[key] for key in summary_fields}

    original_summary = asyncio.run(seed())
    response = client.get('/novels', headers=HEADERS)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    summary = response.json()[0]
    assert set(summary) == summary_fields | {'max_chapters'}
    assert {key: summary[key] for key in summary_fields} == original_summary
    assert type(summary['max_chapters']) is int
    assert summary['max_chapters'] == 137

    response = client.get(f'/novels/{BOOK}', headers=HEADERS)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert {key: detail[key] for key in summary_fields} == original_summary
    assert type(detail['max_chapters']) is int and detail['max_chapters'] == 137
    expected_chapters = [
        {'chapter': 1, 'title': '第一封信', 'status': 'done', 'words': compact_length(original_body),
         'flags': ['deviation'], 'edited_by_user': False},
        {'chapter': 2, 'title': '下一封信', 'status': 'done', 'words': compact_length(second_body),
         'flags': ['deviation'], 'edited_by_user': True},
    ]
    assert detail['chapters'] == expected_chapters
    assert all(type(chapter['edited_by_user']) is bool for chapter in detail['chapters'])
    # The original single-chapter endpoint retains its existing integer field.
    original_chapter = client.get(f'/novels/{BOOK}/chapters/1', headers=HEADERS).json()
    assert type(original_chapter['edited_by_user']) is int and original_chapter['edited_by_user'] == 0
    assert original_chapter['body'] == original_body

    response = client.put(f'/novels/{BOOK}/chapters/1', headers=HEADERS, json={'body': edited_body})
    assert response.status_code == 200, response.text
    assert response.json() == {
        'rearchiving': False,
        'message': '后续章节已标记为 stale；不会自动重写，也不会重算圣经',
    }
    response = client.get(f'/novels/{BOOK}', headers=HEADERS)
    assert response.status_code == 200, response.text
    updated_chapters = response.json()['chapters']
    assert updated_chapters == [
        {**expected_chapters[0], 'edited_by_user': True},
        {**expected_chapters[1], 'status': 'stale'},
    ]
    assert all(type(chapter['edited_by_user']) is bool for chapter in updated_chapters)
    assert updated_chapters[0]['words'] == expected_chapters[0]['words']
    updated_chapter = client.get(f'/novels/{BOOK}/chapters/1', headers=HEADERS).json()
    assert updated_chapter['body'] == edited_body
    assert type(updated_chapter['edited_by_user']) is int and updated_chapter['edited_by_user'] == 1


def test_catalog_notice_tells_how_to_pick_claude_as_editor(complete_book):
    client, _, _ = complete_book
    catalog = client.get('/novels/catalog', headers=HEADERS)
    assert catalog.status_code == 200, catalog.text
    notice = catalog.json()['notice']
    assert '自带 Claude' in notice
    assert '设置 → 聊天模型' in notice and '启用' in notice
    assert '我的模型' in notice and '不扣草莓' in notice
    assert '经过实测' not in notice
