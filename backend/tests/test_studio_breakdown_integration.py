"""WO3c 新接口的作者门禁与跨模块集成。所有素材为自写。"""
import asyncio
import json

import pytest

import auth
import database
from studio import brain, brain_jobs, sources, store


NEW_ROUTES = [
    ("PATCH", "/studio/projects/missing", {"episode_seconds_min": 180, "episode_seconds_max": 240}),
    ("POST", "/studio/projects/missing/breakdown/quote", {}),
    ("POST", "/studio/projects/missing/breakdown/start", {"quote_id": "missing"}),
    ("GET", "/studio/projects/missing/breakdown", None),
    ("PATCH", "/studio/projects/missing/breakdown/synopsis", {"synopsis": {"logline": "归还旧书"}}),
    ("POST", "/studio/breakdowns/missing/chunks/missing/retry/quote", {"provider": "qwen"}),
    ("POST", "/studio/breakdowns/missing/chunks/missing/retry", {"quote_id": "missing", "provider": "qwen"}),
    ("POST", "/studio/breakdowns/missing/cancel", {}),
    ("GET", "/studio/projects/missing/bible", None),
    ("PATCH", "/studio/bible/missing", {"name": "阿宁"}),
    ("POST", "/studio/bible/merge", {"keep_id": "missing", "merge_ids": ["other"]}),
    ("POST", "/studio/bible", {"project_id": "missing", "kind": "character", "name": "阿宁"}),
    ("DELETE", "/studio/bible/missing", None),
    ("GET", "/studio/projects/missing/episodes", None),
    ("POST", "/studio/projects/missing/episodes/ops", {
        "expected_revision": 1, "op": "edit", "no": 1, "fields": {"title": "归还旧书"}}),
    ("POST", "/studio/projects/missing/episodes/approve", {"expected_revision": 1}),
    ("GET", "/studio/projects/missing/breakdown/export", None),
]


@pytest.mark.parametrize("method,path,body", NEW_ROUTES)
def test_all_new_endpoints_are_hidden_from_non_authors(client, monkeypatch, method, path, body):
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "wo3c-author")
    account = asyncio.run(database.get_or_create_user("wo3c-outsider"))
    headers = {"Authorization": "Bearer " + auth.create_token("wo3c-outsider", account["session_version"])}
    response = client.request(method, path, headers=headers, **({"json": body} if body is not None else {}))
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not Found"


TEXT = '阿宁穿着灰色外衣走进门房。\n她把一枚铜铃放到桌上。\n阿禾推门进来，决定一同归还旧书。'
SYNOPSIS = {'logline': '一枚铜铃让两人决定归还旧书。', 'synopsis': '两人在门房会合。',
            'genre': '剧情', 'tone': '平静', 'themes': ['守信']}
SCENES = [
    {'location': '门房', 'summary': '阿宁留下铜铃等候。', 'characters': ['阿宁'], 'est_seconds': 90,
     'change': '她决定等待。', 'start_anchor': '阿宁穿着灰色外衣走进门房。'},
    {'location': '门房', 'summary': '阿禾答应归还旧书。', 'characters': ['阿宁', '阿禾'], 'est_seconds': 100,
     'change': '两人结伴出发。', 'start_anchor': '阿禾推门进来，决定一同归还旧书。'},
]


@pytest.fixture
def assembled(client, monkeypatch):
    owner = 'wo3c-integration-author'
    monkeypatch.setenv('FIONA_STUDIO_OWNERS', owner)
    account = asyncio.run(database.get_or_create_user(owner))
    headers = {'Authorization': 'Bearer ' + auth.create_token(owner, account['session_version'])}
    queued, calls = [], []

    async def options(_owner):
        return [{'id': 'qwen', 'available': True, 'label': '千问', 'model': 'qwen3.8-max'}]

    class Adapter:
        model = 'qwen3.8-max'

        async def call(self, task, inputs, images=None, repair=None):
            calls.append((task, inputs, repair))
            assert repair is None
            if task == 'text_map':
                output = {'summary': '阿宁和阿禾在门房商量归还旧书。', 'scenes': SCENES,
                          'characters': [{'name': '阿宁', 'aliases': ['小宁'], 'role': '送信人',
                                          'excerpt': '阿宁穿着灰色外衣'},
                                         {'name': '阿禾', 'aliases': [], 'role': '同伴', 'excerpt': ''}],
                          'locations': [{'name': '门房', 'description': '两人会合处', 'first_chapter': 1,
                                         'excerpt': '阿宁穿着灰色外衣走进门房。'}],
                          'props': [{'name': '铜铃', 'description': '约定信物', 'first_chapter': 1,
                                     'excerpt': '她把一枚铜铃放到桌上。'}]}
            elif task == 'novel_complete':
                output = {'chapters': [{'chapter': 1, 'scenes': SCENES}],
                          'appearance_fills': [{'character': '阿宁', 'excerpt': '阿宁穿着灰色外衣'}],
                          'new_characters': [{'name': '阿禾', 'role': '同伴', 'first_chapter': 1, 'excerpt': ''}],
                          'locations': [], 'props': []}
            elif task == 'synopsis':
                assert inputs['summaries']
                output = SYNOPSIS
            elif task == 'episode_plan':
                assert [unit['seq'] for unit in inputs['units']] == [1, 2]
                output = {'episodes': [{'unit_from': 1, 'unit_to': 2, 'title': '旧书归途',
                                        'change': '两人决定共同归还旧书。', 'hook': '失主是否仍在等待？'}]}
            else:
                pytest.fail('Unexpected paid task: ' + task)
            return brain.BrainReply(json.dumps(output, ensure_ascii=False),
                                    {'input_tokens': 100, 'output_tokens': 50}, self.model, 'stop', .01)

    async def get_provider(provider, username, **kwargs):
        assert provider == 'qwen' and username == owner
        return Adapter()

    monkeypatch.setattr(brain, 'provider_options', options)
    monkeypatch.setattr(brain, 'get_provider', get_provider)
    monkeypatch.setattr(brain_jobs, '_schedule', queued.append)
    return headers, queued, calls


def execute_all(queued):
    async def drain():
        attempts = 0
        while queued:
            attempts += 1
            assert attempts <= 8, '依赖调度不得循环或重发'
            await brain_jobs._background(queued.pop(0))
    asyncio.run(drain())


@pytest.mark.parametrize('kind', ['paste', 'novel'])
def test_full_snapshot_pipeline_to_g0_edit_export_and_author_preservation(client, assembled, monkeypatch, kind):
    headers, queued, calls = assembled
    if kind == 'paste':
        response = client.post('/studio/projects/from-text', headers=headers,
                               data={'title': '旧书与铜铃', 'kind': 'paste', 'text': TEXT})
    else:
        snapshot = sources._assemble_novel_snapshot(
            {'id': 'book', 'title': '旧书与铜铃', 'config': {}},
            {'locked': {'characters': [{'id': 'C1', 'name': '阿宁', 'appearance': '', 'role': 'main'}]},
             'compass': {'logline': '旧书归还。', 'theme': '守信'}, 'dynamic': {}},
            [{'chapter': 1, 'title': '门房', 'body': TEXT}], 1, 'book')

        async def take_snapshot(*_args):
            return snapshot
        monkeypatch.setattr(sources, 'take_novel_snapshot', take_snapshot)
        response = client.post('/studio/projects/from-novel', headers=headers, json={'book_id': 'book'})
    assert response.status_code == 201, response.text
    pid = response.json()['id']
    root = f'/studio/projects/{pid}'
    assert client.patch(root, headers=headers, json={'brain_provider': 'qwen'}).status_code == 200
    quote = client.post(root + '/breakdown/quote', headers=headers, json={'target_episodes': 1})
    assert quote.status_code == 200, quote.text
    assert not calls
    started = client.post(root + '/breakdown/start', headers=headers, json={'quote_id': quote.json()['id']})
    assert started.status_code == 200, started.text
    assert client.post(root + '/breakdown/start', headers=headers,
                       json={'quote_id': quote.json()['id']}).status_code == 409
    if kind == 'novel':
        imported = client.get(root + '/bible', headers=headers).json()
        assert next(row for row in imported if row['name'] == '阿宁')['needs_author']
    execute_all(queued)
    current = client.get(root + '/breakdown', headers=headers)
    assert current.status_code == 200 and current.json()['status'] == 'done', current.text
    assert len(calls) == (3 if kind == 'paste' else 2)
    assert len(client.get('/studio/projects', headers=headers).json()) == 1
    bible = client.get(root + '/bible', headers=headers).json()
    ning = next(row for row in bible if row['name'] == '阿宁')
    assert ning['appearance'] == '阿宁穿着灰色外衣' and ning['excerpt'] == ning['appearance']
    assert not ning['needs_author'] and ning['episodes'] == [1]
    assert next(row for row in bible if row['name'] == '阿禾')['needs_author']
    plan = client.get(root + '/episodes', headers=headers).json()
    assert plan['plan_revision'] >= 1 and not plan['g0_approved']
    episode = plan['episodes'][0]
    assert (episode['est_seconds'], episode['est_shots'], episode['characters']) == (190, round(190 / 3.5), ['阿宁', '阿禾'])
    assert plan['units'][0]['start'] == 0 and plan['units'][-1]['end'] == len(TEXT)
    revision = plan['plan_revision']
    approved = client.post(root + '/episodes/approve', headers=headers, json={'expected_revision': revision})
    assert approved.status_code == 200 and approved.json()['g0_approved']
    changed = client.post(root + '/episodes/ops', headers=headers,
                          json={'expected_revision': revision, 'op': 'edit', 'no': 1,
                                'fields': {'title': '旧书 | 归途 *'}})
    assert changed.status_code == 200, changed.text
    assert changed.json()['plan_revision'] == revision + 1 and not changed.json()['g0_approved']
    assert client.post(root + '/episodes/ops', headers=headers,
                        json={'expected_revision': revision, 'op': 'delete', 'no': 1}).status_code == 409
    assert client.patch(root + '/breakdown/synopsis', headers=headers,
                         json={'synopsis': {'logline': '作者亲自修改的梗概'}}).status_code == 200
    assert client.patch(f"/studio/bible/{ning['id']}", headers=headers,
                         json={'appearance': '作者确认的蓝色衣服'}).status_code == 200
    # A normal polling refresh must preserve all three independent author edits.
    polled = client.get(root + '/breakdown', headers=headers).json()
    assert polled['synopsis']['logline'] == '作者亲自修改的梗概'
    assert client.get(root + '/episodes', headers=headers).json()['episodes'][0]['title'] == '旧书 | 归途 *'
    assert next(row for row in client.get(root + '/bible', headers=headers).json() if row['id'] == ning['id'])['appearance'] == '作者确认的蓝色衣服'
    exported = client.get(root + '/breakdown/export', headers=headers)
    assert exported.status_code == 200 and r'旧书 \| 归途 \*' in exported.text
    assert '作者亲自修改的梗概' in exported.text
    assert exported.headers['Cache-Control'] == 'private, no-store'
    assert exported.headers['X-Content-Type-Options'] == 'nosniff'
    assert "filename*=UTF-8''" in exported.headers['Content-Disposition']
