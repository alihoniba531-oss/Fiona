"""WO3c 连载续拆：切批、报价、确认、执行、发布与视图。

全部离线：小说工坊与导演模型都用本地桩，数据库与工作室目录逐用例隔离。
用例与规格 `docs/tasks/2026-11-12-studio-serial-breakdown/02-spec.md` §4.6 第 3 条对应。
"""
import asyncio
from datetime import timedelta
import json
from types import SimpleNamespace
import uuid

from fastapi import HTTPException
import pytest

from studio import (
    brain,
    brain_jobs,
    breakdown,
    breakdown_material,
    breakdown_plan,
    casting,
    recovery,
    sources,
    spend,
    store,
)
from test_studio_sources import novel_project, sql, workshop

OWNER = 'owner'
MODELS = {'qwen': 'qwen3.8-max', 'deepseek': 'deepseek-v4-pro', 'claude': 'claude-sonnet-5-5'}
TITLES = {
    1: '归来', 2: '山月', 3: '渡口', 4: '夜航', 5: '灯影', 6: '新岸', 7: '风起', 8: '远帆',
    9: '归舟', 10: '潮声', 11: '旧约', 12: '重逢', 13: '长街', 14: '雪夜', 15: '晓雾', 16: '天明',
    17: '启程',
}


def run(coroutine):
    return asyncio.run(coroutine)


def default_body(number):
    """两场正文，起始锚点都是 8–30 字的精确子串。"""
    return (f'第{number}章 正文开始。\n'
            f'第{number}章第一场：阿禾在渡口等人。\n'
            f'第{number}章第二场：船夫撑船离岸。\n')


def changed_body(number):
    return default_body(number) + f'第{number}章第三场：雨停在渡口。\n'


def prefixed_body(number):
    """快照 2 的改动插在正文开头，仍落在旧批按快照 1 记下的 range 以内。"""
    return '改过的开头。' + changed_body(number)


def install_book(state, numbers, *, bodies=None, statuses=None, characters=None):
    """同时改 detail、chapters_range 与 chapters_done，保持签名稳定。"""
    numbers = list(numbers)
    bodies, statuses = bodies or {}, statuses or {}
    state['book']['chapters'] = [{'chapter': number, 'title': TITLES[number],
                                  'status': statuses.get(number, 'done')} for number in numbers]
    state['book']['chapters_done'] = numbers[-1] if numbers else 0
    state['chapters'] = [{'chapter': number, 'title': TITLES[number],
                          'status': statuses.get(number, 'done'),
                          'body': bodies.get(number) or default_body(number),
                          'updated_at': '2026-11-01', 'edited_by_user': False} for number in numbers]
    if characters is not None:
        state['bible'] = {'version': state['bible'].get('version', 3) + 1,
                          'locked': {'characters': characters}, 'compass': {'theme': '归乡'}}
        state['book']['bible_version'] = state['book'].get('bible_version', 3) + 1


def novel_output(inputs, script):
    chapters, characters = [], []
    for item in inputs['chapters']:
        number = item['chapter']
        text = item['text']
        scenes = []
        for anchor in (f'第{number}章第一场：阿禾在渡口等人。',
                       f'第{number}章第二场：船夫撑船离岸。'):
            if anchor not in text:
                continue
            scenes.append({'location': '渡口', 'summary': f'第 {number} 章原创摘要', 'characters': ['阿禾'],
                           'est_seconds': 100, 'change': '继续前行', 'start_anchor': anchor})
        assert scenes, f'缺少可定位的场景锚点：第 {number} 章'
        chapters.append({'chapter': number, 'scenes': scenes})
        characters.extend(script['characters'].get(number, []))
    return {'chapters': chapters, 'new_characters': characters,
            'locations': [], 'props': [], 'appearance_fills': []}


def plan_output(inputs):
    seqs = [unit['seq'] for unit in inputs['units']]
    low, high = min(seqs), max(seqs)
    if low == high:
        ranges = [(low, high)]
    else:
        middle = (low + high) // 2
        ranges = [(low, middle), (middle + 1, high)]
    return {'episodes': [{'unit_from': first, 'unit_to': last,
                          'title': f'第 {first}–{last} 场分集',
                          'change': '这一集发生的变化', 'hook': '下一集要看什么？'}
                         for first, last in ranges]}


@pytest.fixture
def serial(workshop, monkeypatch, request):
    for name, value in {'FIONA_STUDIO_DAILY_CNY': '1000', 'FIONA_STUDIO_MAX_QUOTE_CNY': '100',
                        'FIONA_STUDIO_BRAIN_MONTHLY_USD': '100'}.items():
        monkeypatch.setenv(name, value)
    options = getattr(request, 'param', None) or {}
    client, auth, state = workshop
    install_book(state, options.get('numbers', range(1, 6)), statuses=options.get('statuses'))
    project = novel_project(workshop)
    run(brain_jobs.patch_project(project['id'], OWNER, 'qwen'))
    queued, calls = [], []
    script = {'fail': None, 'characters': {}}

    async def provider_options(_owner):
        return [{'id': key, 'model': model, 'label': key, 'available': True}
                for key, model in MODELS.items()]

    class Adapter:
        model = MODELS['qwen']

        async def call(self, task, inputs, images=None, repair=None):
            calls.append({'task': task, 'inputs': inputs, 'repair': repair})
            failure = script.get('fail')
            if failure and failure(task, inputs, repair):
                raise brain.BrainProviderError('failed', 'offline_failure', '离线失败')
            if task == 'novel_complete':
                output = novel_output(inputs, script)
            elif task == 'episode_plan':
                output = plan_output(inputs)
            else:
                raise AssertionError('unexpected paid task: ' + task)
            return brain.BrainReply(json.dumps(output, ensure_ascii=False),
                                    {'input_tokens': 100, 'output_tokens': 50}, self.model, 'stop', 0.01)

    async def get_provider(provider, username, images=None, **kwargs):
        return Adapter()

    monkeypatch.setattr(brain, 'provider_options', provider_options)
    monkeypatch.setattr(brain, 'get_provider', get_provider)
    monkeypatch.setattr(brain_jobs, '_schedule', queued.append)
    return SimpleNamespace(client=client, auth=auth, state=state, queued=queued, calls=calls,
                           script=script, pid=project['id'], project=project)


def drain(serial, limit=40):
    async def go():
        rounds = 0
        while serial.queued:
            rounds += 1
            assert rounds <= limit, '依赖调度出现循环'
            await brain_jobs._background(serial.queued.pop(0))
    run(go())


def one(query, args=()):
    async def go():
        async with store.connection() as db:
            return await breakdown._one(db, query, args)
    return run(go())


def many(query, args=()):
    async def go():
        async with store.connection() as db:
            return await breakdown._many(db, query, args)
    return run(go())


def project_row(pid):
    return run(store.get_project(pid, OWNER))


def breakdown_row(bid):
    return one('SELECT * FROM studio_breakdowns WHERE id=?', (bid,))


def units_of(bid):
    return many('SELECT * FROM studio_units WHERE breakdown_id=? ORDER BY seq', (bid,))


def chunks_of(bid):
    return many('SELECT * FROM studio_chunks WHERE breakdown_id=? ORDER BY no', (bid,))


def active_bible(bid, kind='character', name=None):
    rows = many("""SELECT * FROM studio_bible WHERE breakdown_id=? AND kind=? AND archived=0
        AND merged_into IS NULL ORDER BY id""", (bid, kind))
    if name is not None:
        target = breakdown_material.normalize_name(name)
        rows = [row for row in rows if breakdown_material.normalize_name(row['name']) == target]
    return rows


def reserved_total(bid):
    return float(sql('SELECT COALESCE(SUM(CAST(reserved_amount AS REAL)),0) FROM studio_jobs WHERE group_id=?',
                     (bid,))[0][0])


def quote_count():
    return sql('SELECT COUNT(*) FROM studio_quotes')[0][0]


def counts_of(bid):
    return {'chunks': sql('SELECT COUNT(*) FROM studio_chunks WHERE breakdown_id=?', (bid,))[0][0],
            'jobs': sql('SELECT COUNT(*) FROM studio_jobs WHERE group_id=?', (bid,))[0][0],
            'reserved': reserved_total(bid)}


def first_breakdown(serial, *, target_episodes=None, durations=None, approve=False):
    minimum, maximum = durations or (None, None)
    quote = run(breakdown.quote(serial.pid, OWNER, target_episodes, minimum, maximum))
    run(breakdown.start(serial.pid, OWNER, quote['id']))
    drain(serial)
    current = run(breakdown.get_current(serial.pid, OWNER))
    assert current['status'] == 'done', current
    if approve:
        run(breakdown_plan.approve(serial.pid, OWNER, project_row(serial.pid)['plan_revision']))
    return quote


def sync_to(serial, numbers, **kwargs):
    install_book(serial.state, numbers, **kwargs)
    result = run(sources.sync_source(OWNER, serial.pid, project_row(serial.pid)['snapshot_no']))
    return result['snapshot']['no']


def start_continuation(serial):
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    current = run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    return quote, current


def insert_queued_probe(serial, suffix='probe'):
    """组内插入一条 queued job，模拟未结束批次（不关联批，也不占金额）。"""
    project = one('SELECT * FROM studio_projects WHERE id=?', (serial.pid,))
    bid = project['breakdown_id']
    quote_id = breakdown_row(bid)['quote_id']
    stamp = store.utcnow()
    sql('''INSERT INTO studio_jobs(id,project_id,owner,kind,provider,brain_provider,model,params_json,
        fingerprint,quote_id,quote_item_id,status,est_min_cny,est_max_cny,created_at,updated_at,
        confirmed_day,task,group_id,currency,reserved_amount,reserved_cny)
        VALUES(?,?,?,'brain','wan','qwen','qwen3.8-max','{}',?,?,?,'queued','0','0',?,?,?,'novel_complete',?,'CNY','0','0')''',
        ('probe-' + suffix, serial.pid, OWNER, 'fp-' + suffix, quote_id, 'item-' + suffix,
         stamp, stamp, spend.shanghai_day(stamp), bid))


def drop_queued_probe(suffix='probe'):
    sql('DELETE FROM studio_jobs WHERE id=?', ('probe-' + suffix,))


def update_imported(bid, mutate):
    async def go():
        async with store.connection(transaction=True) as db:
            row = await store._one(db, 'SELECT import_json FROM studio_breakdowns WHERE id=?', (bid,))
            imported = json.loads(row['import_json'])
            mutate(imported)
            await db.execute('UPDATE studio_breakdowns SET import_json=? WHERE id=?',
                             (store._json(imported), bid))
    run(go())


def assert_counts(bid, expected):
    assert counts_of(bid) == expected


# ---------------------------------------------------------------------------
# §4.6 第 3 条：切批（batch_plan）
# ---------------------------------------------------------------------------

def _entries(numbers):
    rows = []
    for number in numbers:
        prefix = f'第{number}章'
        body = prefix + '甲' * (100 - len(prefix))
        rows.append({'index': number, 'chapter': number, 'title': TITLES[number], 'chars': len(body),
                     'body': body, 'sha256': 'x', 'status': 'done'})
    return rows


def _manifest(entries):
    return {'kind': 'novel', 'chapters': entries, 'bible': {}, 'compass': {}, 'dynamic': {}, 'config': {}}


def _expected_map(number, entries, segment):
    first, last = entries[0]['chapter'], entries[-1]['chapter']
    return {'no': number, 'task': 'novel_complete',
            'source': {'chapter_from': first, 'chapter_to': last, 'segment': segment,
                       'label': f'第 {first}–{last} 章 · 补全',
                       'chapter_offsets': {str(item['chapter']): 0 for item in entries},
                       'indices': [item['index'] for item in entries],
                       'ranges': [{'index': item['index'], 'chapter': item['chapter'], 'start': 0,
                                   'end': item['chars']} for item in entries]},
            'inputs': {'chapters': [{'chapter': item['chapter'], 'text': item['body'], 'scenes': []}
                                    for item in entries],
                       'known_characters': []},
            'depends': [], 'estimate_units': len(entries)}


def _expected_plan(number, segment, entries, depends, map_nos, estimate):
    first, last = entries[0]['chapter'], entries[-1]['chapter']
    return {'no': number, 'task': 'episode_plan',
            'source': {'segment': segment, 'chapter_from': first, 'chapter_to': last,
                       'map_nos': list(map_nos), 'label': f'第 {first}–{last} 章 · 分集'},
            'inputs': {}, 'depends': list(depends), 'estimate_units': estimate}


def test_batch_plan_default_output_and_continuation_offsets():
    entries = _entries(range(1, 13))
    manifest = _manifest(entries)
    imported, plan = breakdown_material.batch_plan(manifest, entries)
    units = [{'seq': number, 'chapter': number, 'scene_index': 1, 'label': f'第 {number} 章第 1 场',
              'location': '', 'summary': '', 'characters': [], 'est_seconds': None, 'change': '',
              'start': 0, 'end': 100} for number in range(1, 13)]
    assert imported == {'characters': [], 'units': units,
                        'synopsis': {'logline': '', 'theme': '', 'core_conflict': '',
                                     'main_threads': '', 'arc_summaries': []},
                        'foreshadowing': [], 'timeline': [], 'adaptation': {}}
    expected = [_expected_map(1, entries[:10], 0),
                _expected_map(2, entries[10:], 1),
                _expected_plan(3, 0, entries[:10], [1], [1], 10),
                _expected_plan(4, 1, entries[10:], [1, 2, 3], [2], 2)]
    assert plan == expected
    # 默认参数与显式传入默认值逐项相等，说明新增参数没有改变旧行为。
    assert breakdown_material.batch_plan(manifest, entries, 1, 0, 0) == (imported, plan)
    # 单章批沿用改动前的标签写法（始终写「第 x–y 章」）。
    short = _entries(range(1, 12))
    _, short_plan = breakdown_material.batch_plan(_manifest(short), short)
    assert [chunk['source']['label'] for chunk in short_plan] == [
        '第 1–10 章 · 补全', '第 11–11 章 · 补全', '第 1–10 章 · 分集', '第 11–11 章 · 分集']


def test_batch_plan_continuation_slice_only_new_chapters_and_offset():
    entries = _entries(range(1, 13))
    manifest = _manifest(entries)
    base = 5
    _, plan = breakdown_material.batch_plan(manifest, entries, start_chapter=6, segment_base=1, no_base=base)
    assert [chunk['no'] for chunk in plan] == [base + 1, base + 2]
    mapping, episode = plan
    assert mapping['source']['chapter_from'] == 6 and mapping['source']['chapter_to'] == 12
    assert mapping['source']['segment'] == 1
    assert mapping['source']['label'] == '第 6–12 章 · 补全'
    assert [item['chapter'] for item in mapping['inputs']['chapters']] == list(range(6, 13))
    assert episode['source']['chapter_from'] == 6 and episode['source']['chapter_to'] == 12
    assert episode['source']['label'] == '第 6–12 章 · 分集'
    assert episode['depends'] == [base + 1] and episode['source']['map_nos'] == [base + 1]
    assert all(base + 1 <= number <= base + len(plan) for chunk in plan
               for number in chunk['depends'] + chunk['source'].get('map_nos', []))
    by_no = {chunk['no']: chunk for chunk in plan}
    for chunk in plan:
        for dependency in chunk['depends']:
            assert by_no[dependency]['no'] < chunk['no']
    # 新章跨两个段时，段号、章范围与依赖都接在旧批之后。
    longer = _entries(range(1, 17))
    _, spread = breakdown_material.batch_plan(_manifest(longer), longer, start_chapter=6,
                                              segment_base=1, no_base=2)
    assert [chunk['no'] for chunk in spread] == [3, 4, 5, 6]
    first_map, second_map, first_plan, second_plan = spread
    assert (first_map['source']['chapter_from'], first_map['source']['chapter_to'],
            first_map['source']['segment']) == (6, 15, 1)
    assert (second_map['source']['chapter_from'], second_map['source']['chapter_to'],
            second_map['source']['segment']) == (16, 16, 2)
    assert (first_plan['source']['chapter_from'], first_plan['source']['chapter_to']) == (6, 15)
    assert (second_plan['source']['chapter_from'], second_plan['source']['chapter_to']) == (16, 16)
    assert first_plan['depends'] == [3] and first_plan['source']['map_nos'] == [3]
    assert second_plan['depends'] == [3, 4, 5] and second_plan['source']['map_nos'] == [4]
    by_no = {chunk['no']: chunk for chunk in spread}
    assert by_no[6]['depends'] == [by_no[3]['no'], by_no[4]['no'], by_no[5]['no']]
    assert all(3 <= number <= 6 for chunk in spread
               for number in chunk['depends'] + chunk['source'].get('map_nos', []))


@pytest.mark.parametrize('kwargs', [{'start_chapter': 2}, {'segment_base': 1}, {'no_base': 1}])
def test_batch_plan_secondary_sources_reject_continuation_arguments(kwargs):
    manifest = {'kind': 'paste'}
    entries = [{'index': 1, 'chapter': 1, 'body': '文本', 'chars': 2, 'start': 0, 'end': 2}]
    with pytest.raises(ValueError):
        breakdown_material.batch_plan(manifest, entries, **kwargs)
    imported, plan = breakdown_material.batch_plan(manifest, entries)
    assert imported == {'characters': [], 'units': [], 'synopsis': {}}
    assert [chunk['task'] for chunk in plan] == ['text_map', 'synopsis', 'episode_plan']


# ---------------------------------------------------------------------------
# 新接口：续拆报价与确认的路由接线
# ---------------------------------------------------------------------------

def test_continue_routes_quote_then_start(serial):
    first_breakdown(serial)
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    root = f'/studio/projects/{serial.pid}/breakdown'
    quoted = serial.client.post(root + '/continue/quote', headers=serial.auth)
    assert quoted.status_code == 200, quoted.text
    body = quoted.json()
    assert (body['continue_from'], body['continue_to']) == (6, 8)
    assert body['total_chunks'] == 2
    started = serial.client.post(root + '/continue/start', headers=serial.auth,
                                 json={'quote_id': body['id']})
    assert started.status_code == 200, started.text
    assert started.json()['status'] == 'running'
    assert started.json()['snapshot_no'] == 2
    again = serial.client.post(root + '/continue/start', headers=serial.auth,
                               json={'quote_id': body['id']})
    assert again.status_code == 409
    assert again.json()['detail'] == '拆解已更新，请重新报价'


# ---------------------------------------------------------------------------
# §4.6 第 3 条：报价拒绝
# ---------------------------------------------------------------------------

def test_continue_quote_rejects_non_novel_and_missing_breakdown(serial):
    before = quote_count()
    paste = run(sources.create_text_project(OWNER, 'paste', '贴文', '第1章 初见\n甲\n第2章 尾声\n乙'))
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_quote(paste['id'], OWNER))
    assert error.value.status_code == 409
    assert error.value.detail == '只有小说工坊来源可以续拆'
    assert quote_count() == before
    # 小说来源但还没有拆解。
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_quote(serial.pid, OWNER))
    assert error.value.status_code == 409
    assert error.value.detail == '还没有拆解，请先拆解'
    assert quote_count() == before


def test_continue_quote_rejects_running_and_retired(serial):
    quote = run(breakdown.quote(serial.pid, OWNER))
    run(breakdown.start(serial.pid, OWNER, quote['id']))
    before = quote_count()
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_quote(serial.pid, OWNER))
    assert error.value.status_code == 409
    assert error.value.detail == '拆解尚未全部完成，不能续拆'
    assert quote_count() == before
    bid = one('SELECT id FROM studio_breakdowns WHERE project_id=?', (serial.pid,))['id']
    run(breakdown.cancel(bid, OWNER))
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_quote(serial.pid, OWNER))
    assert error.value.status_code == 409
    assert error.value.detail == '拆解已被替代或取消'
    assert quote_count() == before


def test_continue_quote_rejects_unfinished_batches(serial):
    first_breakdown(serial)
    before = quote_count()
    insert_queued_probe(serial, 'unfinished')
    try:
        with pytest.raises(HTTPException) as error:
            run(breakdown.continue_quote(serial.pid, OWNER))
    finally:
        drop_queued_probe('unfinished')
    assert error.value.status_code == 409
    assert error.value.detail == '拆解还有未结束的批次'
    assert quote_count() == before


def test_continue_quote_rejects_without_new_chapters(serial):
    first_breakdown(serial)
    before = quote_count()
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_quote(serial.pid, OWNER))
    assert error.value.status_code == 409
    assert error.value.detail == '没有新写好的章节可以续拆，请先在来源面板同步'
    assert quote_count() == before


# ---------------------------------------------------------------------------
# §4.6 第 3 条：报价内容
# ---------------------------------------------------------------------------

def test_continue_quote_only_new_chapters_and_ignores_target_episodes(serial):
    original = first_breakdown(serial, target_episodes=20, durations=(90, 120))
    assert original['settings']['episode_seconds_min'] == 90
    bid = project_row(serial.pid)['breakdown_id']
    old_plan_chunk = next(chunk for chunk in chunks_of(bid) if chunk['task'] == 'episode_plan')
    before_inputs = one('SELECT * FROM studio_jobs WHERE id=?', (old_plan_chunk['job_id'],))['params']['inputs']
    assert before_inputs['suggested_episodes'] == 20
    # 新章跨两个段，报价才会出现两个补全批；这样能分辨依赖是否被「大约几集」改写。
    sync_to(serial, range(1, 17), bodies={3: changed_body(3)})
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    assert quote['continue_from'] == 6 and quote['continue_to'] == 16
    assert quote['total_chunks'] == 4
    assert quote['task_counts'] == {'novel_complete': 2, 'text_map': 0, 'synopsis': 0, 'episode_plan': 2}
    # 时长沿用原拆解 settings，续拆不能改；「大约几集」不进入本轮报价。
    assert quote['settings']['episode_seconds_min'] == 90
    assert quote['settings']['episode_seconds_max'] == 120
    assert quote['settings']['target_episodes'] is None
    payload = one('SELECT * FROM studio_quotes WHERE id=?', (quote['id'],))['items']
    assert payload['kind'] == 'breakdown_continue'
    assert payload['snapshot_no'] == 2 and payload['covered_through'] == 5
    assert payload['continue_from'] == 6 and payload['continue_to'] == 16
    assert payload['settings']['target_episodes'] is None
    assert payload['settings']['episode_seconds_min'] == 90
    first_map, second_map, first_plan, second_plan = payload['plan']
    assert (first_map['source']['chapter_from'], first_map['source']['chapter_to']) == (6, 15)
    assert (second_map['source']['chapter_from'], second_map['source']['chapter_to']) == (16, 16)
    # 原拆解填过 20 集也不改写依赖：分集只等本轮补全批，不追加整本的全部补全批。
    assert first_map['no'] == 3 and first_plan['depends'] == [3]
    assert first_plan['source']['map_nos'] == [3]
    assert second_plan['depends'] == [3, 4, 5]
    assert second_plan['source']['map_nos'] == [4]
    assert all(chunk['source']['chapter_from'] >= 6 for chunk in payload['plan'])
    assert all(chunk['source']['chapter_to'] <= 16 for chunk in payload['plan'])
    after_inputs = one('SELECT * FROM studio_jobs WHERE id=?', (old_plan_chunk['job_id'],))['params']['inputs']
    assert after_inputs['suggested_episodes'] == 20
    assert original['settings']['target_episodes'] == 20


# ---------------------------------------------------------------------------
# §4.6 第 3 条：确认失败
# ---------------------------------------------------------------------------

def test_continue_start_rejects_wrong_use_and_changed_snapshot(serial):
    full_quote = first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    baseline = counts_of(bid)
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_start(serial.pid, OWNER, full_quote['id']))
    assert error.value.status_code == 409 and error.value.detail == '报价用途不匹配'
    assert_counts(bid, baseline)
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    sync_to(serial, range(1, 11), bodies={3: changed_body(3)})
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    assert error.value.status_code == 409 and error.value.detail == '作品快照已更新，请重新报价'
    assert_counts(bid, baseline)
    # 快照号相同但 covered_through 变了，也要拒绝。
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    update_imported(bid, lambda imported: imported.__setitem__('_covered_through', 6))
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    assert error.value.status_code == 409 and error.value.detail == '拆解已更新，请重新报价'
    assert_counts(bid, baseline)


def test_continue_start_confirms_once_only(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    confirmed = counts_of(bid)
    assert confirmed['chunks'] == 4 and confirmed['jobs'] == 4
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    assert error.value.status_code == 409 and error.value.detail == '拆解已更新，请重新报价'
    assert counts_of(bid) == confirmed


def test_continue_start_rejects_expired_quote(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    baseline = counts_of(bid)
    sql('UPDATE studio_quotes SET expires_at=? WHERE id=?',
        ((store.parse_time(store.utcnow()) - timedelta(minutes=1)).isoformat(), quote['id']))
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    assert error.value.status_code == 409
    assert error.value.detail == '报价已过期，请重新报价'
    assert_counts(bid, baseline)
    assert one('SELECT status FROM studio_quotes WHERE id=?', (quote['id'],))['status'] == 'open'


def test_continue_start_rejects_exhausted_budget(serial, monkeypatch):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    baseline = counts_of(bid)
    # 报价时额度充足；确认前把全工作室日额度压到不足以覆盖这笔报价。
    monkeypatch.setenv('FIONA_STUDIO_DAILY_CNY', '0.0001')
    with pytest.raises(HTTPException) as error:
        run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
    assert error.value.status_code == 409
    assert '今日额度不足' in error.value.detail
    assert_counts(bid, baseline)
    assert one('SELECT status FROM studio_quotes WHERE id=?', (quote['id'],))['status'] == 'open'


def test_continue_start_rejects_unfinished_batches(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    quote = run(breakdown.continue_quote(serial.pid, OWNER))
    insert_queued_probe(serial, 'continue')
    try:
        baseline = counts_of(bid)
        with pytest.raises(HTTPException) as error:
            run(breakdown.continue_start(serial.pid, OWNER, quote['id']))
        assert error.value.status_code == 409
        assert error.value.detail == '拆解还有未结束的批次'
        assert_counts(bid, baseline)
        assert one('SELECT status FROM studio_quotes WHERE id=?', (quote['id'],))['status'] == 'open'
    finally:
        drop_queued_probe('continue')


# ---------------------------------------------------------------------------
# §4.6 第 3 条：确认成功
# ---------------------------------------------------------------------------

def test_continue_start_appends_round_and_keeps_old_state(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    old_units = units_of(bid)
    old_bible = many('SELECT * FROM studio_bible WHERE breakdown_id=?', (bid,))
    old_chunks = chunks_of(bid)
    old_project = project_row(serial.pid)
    old_settings = breakdown_row(bid)['settings_json']
    old_manifest = breakdown_row(bid)['imported']['_manifest']
    expected_basis = {str(item['chapter']): {'snapshot_no': 1, 'sha256': item['sha256'],
                                             'title': item['title'], 'status': item['status']}
                      for item in old_manifest['chapters']}
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)},
            characters=[{'id': 'C2', 'name': '阿禾', 'role': 'main', 'appearance': ''},
                        {'id': 'C3', 'name': '渔夫', 'role': 'supporting', 'appearance': ''}])
    quote, current = start_continuation(serial)
    assert one('SELECT status FROM studio_quotes WHERE id=?', (quote['id'],))['status'] == 'confirmed'
    fresh = breakdown_row(bid)
    assert fresh['snapshot_no'] == 2 and fresh['outdated'] == 0 and fresh['status'] == 'running'
    assert current['snapshot_no'] == 2 and current['outdated'] is False and current['status'] == 'running'
    for chunk in old_chunks:
        assert one('SELECT * FROM studio_chunks WHERE id=?', (chunk['id'],))['source']['snapshot_no'] == 1
    new_chunks = [chunk for chunk in chunks_of(bid) if chunk['no'] > max(item['no'] for item in old_chunks)]
    assert [chunk['task'] for chunk in new_chunks] == ['novel_complete', 'episode_plan']
    assert [chunk['no'] for chunk in new_chunks] == [3, 4]
    assert all(chunk['source']['snapshot_no'] == 2 and chunk['source']['round'] == 1 for chunk in new_chunks)
    fresh_units = units_of(bid)
    assert len(fresh_units) == len(old_units) + 3  # 第 6–8 章各一个结构化单元
    for before, after in zip(old_units, fresh_units):
        assert (after['seq'], after['chapter'], after['scene_index'], after['label'],
                after['start'], after['end']) == (before['seq'], before['chapter'], before['scene_index'],
                                                  before['label'], before['start'], before['end'])
    imported = fresh['imported']
    basis = imported['_chapter_basis']
    assert sorted(int(key) for key in basis) == list(range(1, 9))
    for number in range(1, 6):
        # 第 3 章在快照 2 改过，拆解依据仍是快照 1 的哈希。
        assert basis[str(number)] == expected_basis[str(number)]
    for number in range(6, 9):
        chapter = next(item for item in imported['_manifest']['chapters'] if item['chapter'] == number)
        assert basis[str(number)] == {'snapshot_no': 2, 'sha256': chapter['sha256'],
                                      'title': chapter['title'], 'status': chapter['status']}
    assert imported['_covered_through'] == 8
    assert imported['_manifest']['chapters'][-1]['chapter'] == 8
    assert [item['round'] for item in imported['_continuations']] == [1]
    assert imported['_published_max_seq'] == old_units[-1]['seq']
    fresh_bible = {row['id']: row for row in many('SELECT * FROM studio_bible WHERE breakdown_id=?', (bid,))}
    for row in old_bible:
        assert row['id'] in fresh_bible
        assert fresh_bible[row['id']]['name'] == row['name']
        assert fresh_bible[row['id']]['merged_into'] == row['merged_into']
    fisher = [row for row in fresh_bible.values()
              if row['kind'] == 'character' and row['name'] == '渔夫' and not row['archived']]
    assert len(fisher) == 1 and fisher[0]['id'] not in {row['id'] for row in old_bible}
    now_project = project_row(serial.pid)
    for field in ('breakdown_id', 'plan_revision', 'plan_approved_revision', 'episode_seconds_min',
                  'episode_seconds_max'):
        assert now_project[field] == old_project[field]
    assert breakdown_row(bid)['settings_json'] == old_settings


# ---------------------------------------------------------------------------
# §4.6 第 3 条：执行 / 原文
# ---------------------------------------------------------------------------

def test_continuation_execution_reads_bound_snapshot_and_keeps_old_units(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    old_units = units_of(bid)
    old_map = next(chunk for chunk in chunks_of(bid) if chunk['task'] == 'novel_complete')
    # 快照 2 的第 3 章改了开头，改动落在旧批 range 以内：
    # 如果错读快照 2，按旧 range 切片不再等于快照 1 的原文。
    sync_to(serial, range(1, 9), bodies={3: prefixed_body(3)})
    assert serial.state['chapters'][2]['body'] == prefixed_body(3)
    start_continuation(serial)
    # 清空旧补全批的输入，强制 refresh 从该批绑定的快照 1 重读原文。
    sql('UPDATE studio_jobs SET params_json=? WHERE id=?',
        (json.dumps({'inputs': {}, 'breakdown_chunk': old_map['id']}, ensure_ascii=False), old_map['job_id']))
    chunk = one('SELECT * FROM studio_chunks WHERE id=?', (old_map['id'],))
    assert breakdown_row(bid)['snapshot_no'] == 2
    inputs = run(breakdown._source_inputs(breakdown_row(bid), chunk))
    chapter3 = next(item for item in inputs['chapters'] if item['chapter'] == 3)
    assert chapter3['text'] == default_body(3)
    assert '改过的开头。' not in chapter3['text']
    drain(serial)
    new_map_calls = [call for call in serial.calls if call['task'] == 'novel_complete'
                     and call['inputs']['chapters'][0]['chapter'] == 6]
    assert len(new_map_calls) == 1
    assert [item['chapter'] for item in new_map_calls[0]['inputs']['chapters']] == [6, 7, 8]
    assert [item['text'] for item in new_map_calls[0]['inputs']['chapters']] == [default_body(n) for n in (6, 7, 8)]
    new_map = next(chunk for chunk in chunks_of(bid)
                   if chunk['task'] == 'novel_complete' and chunk['no'] > old_map['no'])
    assert new_map['source']['snapshot_no'] == 2
    fresh_units = units_of(bid)
    assert len(fresh_units) > len(old_units)
    for before, after in zip(old_units, fresh_units):
        assert (after['start'], after['end'], after['label']) == (before['start'], before['end'], before['label'])
    assert run(breakdown.get_current(serial.pid, OWNER))['status'] == 'done'


# ---------------------------------------------------------------------------
# §4.6 第 3 条：建议集数
# ---------------------------------------------------------------------------

def test_continuation_never_suggests_episodes(serial, monkeypatch):
    first_breakdown(serial, target_episodes=20)
    bid = project_row(serial.pid)['breakdown_id']
    old_plan_chunk = next(chunk for chunk in chunks_of(bid) if chunk['task'] == 'episode_plan')
    old_inputs = one('SELECT * FROM studio_jobs WHERE id=?', (old_plan_chunk['job_id'],))['params']['inputs']
    assert old_inputs['suggested_episodes'] == 20
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    run(brain_jobs._background(serial.queued.pop(0)))  # 新补全批，解锁分集批
    plan_job = serial.queued.pop(0)
    run(breakdown.prepare_job(plan_job, OWNER))
    prepared = one('SELECT * FROM studio_jobs WHERE id=?', (plan_job,))['params']['inputs']
    assert 'suggested_episodes' not in prepared
    # 同一批失败后重跑报价，输入里同样没有建议集数。
    serial.script['fail'] = lambda task, inputs, repair: task == 'episode_plan'
    run(brain_jobs._background(plan_job))
    serial.script['fail'] = None
    seen = []
    original = breakdown._dependency_input

    def recording(*args, **kwargs):
        value = original(*args, **kwargs)
        seen.append(value)
        return value

    monkeypatch.setattr(breakdown, '_dependency_input', recording)
    new_plan_chunk = next(chunk for chunk in chunks_of(bid)
                          if chunk['task'] == 'episode_plan' and chunk['no'] > old_plan_chunk['no'])
    quote = run(breakdown.retry_quote(bid, new_plan_chunk['id'], OWNER, 'qwen'))
    assert quote['total_chunks'] == 1
    assert seen and 'suggested_episodes' not in seen[-1]
    unchanged = one('SELECT * FROM studio_jobs WHERE id=?', (old_plan_chunk['job_id'],))['params']['inputs']
    assert unchanged['suggested_episodes'] == 20


# ---------------------------------------------------------------------------
# §4.6 第 3 条：衔接
# ---------------------------------------------------------------------------

def test_continuation_chains_published_last_and_round_outputs(serial):
    first_breakdown(serial)
    project = project_row(serial.pid)
    edited = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': project['plan_revision'], 'op': 'edit', 'no': 2,
        'fields': {'title': '作者改过的末集', 'hook': '作者改过的钩子'}}))
    last = next(episode for episode in edited['episodes'] if episode['no'] == 2)
    sync_to(serial, range(1, 17), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    plan_calls = [call for call in serial.calls if call['task'] == 'episode_plan'
                  and call['inputs']['units'][0]['seq'] >= 11]
    assert len(plan_calls) == 2
    assert plan_calls[0]['inputs']['previous_episode'] == {
        'title': '作者改过的末集', 'unit_from': last['unit_from'], 'unit_to': last['unit_to'],
        'change': last['change'], 'hook': '作者改过的钩子'}
    assert plan_calls[1]['inputs']['previous_episode'] == plan_output(plan_calls[0]['inputs'])['episodes'][-1]
    assert run(breakdown.get_current(serial.pid, OWNER))['status'] == 'done'


def test_continuation_previous_episode_falls_back_to_new_last_after_delete(serial):
    first_breakdown(serial)
    project = project_row(serial.pid)
    remaining = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': project['plan_revision'], 'op': 'delete', 'no': 2}))
    last = remaining['episodes'][-1]
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    plan_calls = [call for call in serial.calls if call['task'] == 'episode_plan'
                  and call['inputs']['units'][0]['seq'] >= 11]
    assert len(plan_calls) == 1
    assert plan_calls[0]['inputs']['previous_episode'] == {
        'title': last['title'], 'unit_from': last['unit_from'], 'unit_to': last['unit_to'],
        'change': last['change'], 'hook': last['hook']}


# ---------------------------------------------------------------------------
# §4.6 第 3 条：总表沿用已有条目
# ---------------------------------------------------------------------------

def _continuity_counts(bid, name):
    merged = sql('SELECT COUNT(*) FROM studio_bible WHERE breakdown_id=? AND merged_into IS NOT NULL',
                 (bid,))[0][0]
    return active_bible(bid, 'character', name), merged


def _assert_not_orphaned(bid, bible_id):
    row = one('SELECT * FROM studio_bible WHERE id=?', (bible_id,))
    assert row is not None
    assert casting.is_orphaned(row, bid) is False


def test_continuity_recognizes_workshop_registered_character(serial):
    serial.script['characters'][1] = [{'name': '阿禾', 'role': '同伴', 'first_chapter': 1, 'excerpt': ''}]
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    rows, _ = _continuity_counts(bid, '阿禾')
    assert len(rows) == 1
    bible_id = rows[0]['id']
    assert rows[0]['ref_id'] is None
    state = run(casting.state(serial.pid, OWNER))
    item = next(entry for entry in state['items'] if entry['bible_id'] == bible_id)
    sql("UPDATE studio_items SET status='approved' WHERE id=?", (item['id'],))
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)},
            characters=[{'id': 'C2', 'name': '阿禾', 'role': 'main', 'appearance': ''}])
    start_continuation(serial)
    rows, merged = _continuity_counts(bid, '阿禾')
    assert len(rows) == 1 and rows[0]['id'] == bible_id and rows[0]['ref_id'] == 'C2'
    assert len(active_bible(bid)) == 1
    assert merged == 0
    _assert_not_orphaned(bid, bible_id)
    state = run(casting.state(serial.pid, OWNER))
    assert next(entry for entry in state['items'] if entry['bible_id'] == bible_id)['orphaned'] is False
    drain(serial)
    rows, merged = _continuity_counts(bid, '阿禾')
    assert len(rows) == 1 and rows[0]['id'] == bible_id and rows[0]['ref_id'] == 'C2'
    assert len(active_bible(bid)) == 1
    assert merged == 0
    _assert_not_orphaned(bid, bible_id)
    state = run(casting.state(serial.pid, OWNER))
    kept = next(entry for entry in state['items'] if entry['bible_id'] == bible_id)
    assert kept['orphaned'] is False and kept['status'] == 'approved'


def test_continuity_keeps_author_renamed_character(serial):
    serial.script['characters'][1] = [{'name': '阿禾', 'role': '同伴', 'first_chapter': 1, 'excerpt': ''}]
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    rows, _ = _continuity_counts(bid, '阿禾')
    bible_id = rows[0]['id']
    run(breakdown_plan.patch_bible(bible_id, OWNER, {'name': '禾生'}))
    serial.script['characters'] = {6: [{'name': '禾生', 'role': '同伴', 'first_chapter': 6, 'excerpt': ''}]}
    # 书斋圣经不登记这个人物，续拆只能靠总表的改名与旧别名认回原条目。
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    rows, merged = _continuity_counts(bid, '禾生')
    assert len(rows) == 1 and rows[0]['id'] == bible_id
    assert rows[0]['ref_id'] is None
    assert '阿禾' in json.loads(rows[0]['aliases_json'])
    assert len(active_bible(bid)) == 1
    assert merged == 0
    _assert_not_orphaned(bid, bible_id)
    drain(serial)
    rows, merged = _continuity_counts(bid, '禾生')
    assert len(rows) == 1 and rows[0]['id'] == bible_id
    assert '阿禾' in json.loads(rows[0]['aliases_json'])
    assert len(active_bible(bid)) == 1
    assert merged == 0
    _assert_not_orphaned(bid, bible_id)
    state = run(casting.state(serial.pid, OWNER))
    kept = next(entry for entry in state['items'] if entry['bible_id'] == bible_id)
    assert kept['orphaned'] is False


def test_continuity_keeps_author_created_character(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    created = run(breakdown_plan.create_bible(OWNER, {'project_id': serial.pid, 'kind': 'character',
                                                      'name': '船夫', 'aliases': ['老船夫']}))
    assert len(active_bible(bid, 'character', '船夫')) == 1
    serial.script['characters'] = {6: [{'name': '船夫', 'role': '摆渡人', 'first_chapter': 6, 'excerpt': ''}]}
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    rows, merged = _continuity_counts(bid, '船夫')
    assert len(rows) == 1 and rows[0]['id'] == created['id']
    assert '老船夫' in json.loads(rows[0]['aliases_json'])
    assert len(active_bible(bid)) == 1
    assert merged == 0
    _assert_not_orphaned(bid, created['id'])
    drain(serial)
    rows, merged = _continuity_counts(bid, '船夫')
    assert len(rows) == 1 and rows[0]['id'] == created['id']
    assert '老船夫' in json.loads(rows[0]['aliases_json'])
    assert len(active_bible(bid)) == 1
    assert merged == 0
    _assert_not_orphaned(bid, created['id'])


def test_continuity_duplicate_active_names_warn_and_insert(serial):
    # 一条是第 0 轮模型输出的自动条目（uuid5），已经定妆且批准；
    # 另一条是作者手建的 uuid4 条目。快照 2 的书斋圣经又登记同名 C2。
    serial.script['characters'][1] = [{'name': '船夫', 'role': '摆渡人', 'first_chapter': 1, 'excerpt': ''}]
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    auto_rows = active_bible(bid, 'character', '船夫')
    assert len(auto_rows) == 1
    automatic = auto_rows[0]
    assert uuid.UUID(automatic['id']).version == 5
    state = run(casting.state(serial.pid, OWNER))
    item = next(entry for entry in state['items'] if entry['bible_id'] == automatic['id'])
    sql("UPDATE studio_items SET status='approved' WHERE id=?", (item['id'],))
    first = run(breakdown_plan.create_bible(OWNER, {'project_id': serial.pid, 'kind': 'character',
                                                    'name': '船夫'}))
    serial.script['characters'] = {6: [{'name': '船夫', 'role': '摆渡人', 'first_chapter': 6, 'excerpt': ''}]}
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)},
            characters=[{'id': 'C2', 'name': '船夫', 'role': '摆渡人', 'appearance': ''}])
    start_continuation(serial)
    rows, merged = _continuity_counts(bid, '船夫')
    assert automatic['id'] in {row['id'] for row in rows}
    assert {automatic['id'], first['id']} < {row['id'] for row in rows}
    inserted = [row for row in rows if row['id'] not in {automatic['id'], first['id']}]
    assert len(inserted) == 1 and inserted[0]['ref_id'] == 'C2'
    assert len(active_bible(bid)) == 3
    assert merged == 0
    assert one('SELECT merged_into FROM studio_bible WHERE id=?', (automatic['id'],))['merged_into'] is None
    _assert_not_orphaned(bid, automatic['id'])
    state = run(casting.state(serial.pid, OWNER))
    kept = next(entry for entry in state['items'] if entry['bible_id'] == automatic['id'])
    assert kept['orphaned'] is False and kept['status'] == 'approved'
    warnings = run(breakdown.get_current(serial.pid, OWNER))['warnings']
    assert any('与总表里多个同类条目重名' in warning and '船夫' in warning for warning in warnings)
    drain(serial)
    rows, merged = _continuity_counts(bid, '船夫')
    assert {row['id'] for row in rows} == {automatic['id'], first['id'], inserted[0]['id']}
    assert len(active_bible(bid)) == 3
    assert merged == 0
    assert one('SELECT merged_into FROM studio_bible WHERE id=?', (automatic['id'],))['merged_into'] is None
    _assert_not_orphaned(bid, automatic['id'])
    state = run(casting.state(serial.pid, OWNER))
    kept = next(entry for entry in state['items'] if entry['bible_id'] == automatic['id'])
    assert kept['orphaned'] is False and kept['status'] == 'approved'
    warnings = run(breakdown.get_current(serial.pid, OWNER))['warnings']
    assert any('与总表里多个同类条目重名' in warning and '船夫' in warning for warning in warnings)


# ---------------------------------------------------------------------------
# §4.6 第 3 条：发布
# ---------------------------------------------------------------------------

def _assert_marking(view, marker):
    assert view['appended_from'] is not None
    for episode in view['episodes']:
        if episode['no'] >= view['appended_from']:
            assert episode['unit_from'] >= marker
        else:
            assert episode['unit_to'] < marker


def test_continuation_publish_keeps_edits_marks_new_and_clears_on_approve(serial):
    first_breakdown(serial)
    project = project_row(serial.pid)
    edited = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': project['plan_revision'], 'op': 'edit', 'no': 1,
        'fields': {'title': '作者定的第一集', 'notes': '作者备注：开场要慢'}}))
    old_first = edited['episodes'][0]
    before_revision = edited['plan_revision']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    view = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert view['plan_revision'] == before_revision + 1 and view['g0_approved'] is False
    assert view['continuing'] is False
    assert [episode['no'] for episode in view['episodes']] == [1, 2, 3, 4]
    assert view['episodes'][0]['title'] == '作者定的第一集'
    assert view['episodes'][0]['notes'] == '作者备注：开场要慢'
    assert (view['episodes'][0]['unit_from'], view['episodes'][0]['unit_to']) == (
        old_first['unit_from'], old_first['unit_to'])
    assert view['appended_from'] == 3
    assert [(episode['unit_from'], episode['unit_to']) for episode in view['episodes'][2:]] == [(11, 13), (14, 16)]
    _assert_marking(view, 11)
    # 发布后、批准前：删除 / 补建 / 合并 / 拆分旧集，「新增」只落在含新单元的集上。
    view = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': view['plan_revision'], 'op': 'delete', 'no': 1}))
    assert view['appended_from'] == 2
    _assert_marking(view, 11)
    view = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': view['plan_revision'], 'op': 'insert', 'unit_from': 1, 'unit_to': 5,
        'title': '补回来的旧集'}))
    assert view['appended_from'] == 3
    _assert_marking(view, 11)
    view = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': view['plan_revision'], 'op': 'merge', 'no': 1}))
    assert view['appended_from'] == 2
    _assert_marking(view, 11)
    view = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': view['plan_revision'], 'op': 'split', 'no': 1, 'at_unit': 3}))
    assert view['appended_from'] == 3
    _assert_marking(view, 11)
    approved = run(breakdown_plan.approve(serial.pid, OWNER, view['plan_revision']))
    assert approved['g0_approved'] is True and approved['appended_from'] is None


def test_continuation_appended_from_follows_moved_boundary(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    view = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert view['appended_from'] == 3
    marker = breakdown_row(bid)['imported']['_appended_from_unit']
    assert marker == 11
    # 发布后、批准前，把最后一个旧集（第 2 集）的终点向后挪一场，进入新单元。
    moved = run(breakdown_plan.operate_episodes(serial.pid, OWNER, {
        'expected_revision': view['plan_revision'], 'op': 'move_boundary', 'no': 2, 'delta': 1}))
    assert (moved['episodes'][1]['unit_to'], moved['episodes'][2]['unit_from']) == (marker, marker + 1)
    expected = next(episode['no'] for episode in moved['episodes'] if episode['unit_to'] >= marker)
    assert expected == 2
    assert moved['appended_from'] == expected


def test_continuation_partial_does_not_publish_until_retry(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    before = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert before['plan_revision'] == 1 and len(before['episodes']) == 2
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    serial.script['fail'] = (lambda task, inputs, repair:
                             task == 'novel_complete' and inputs['chapters'][0]['chapter'] == 6)
    start_continuation(serial)
    drain(serial)
    assert run(breakdown.get_current(serial.pid, OWNER))['status'] == 'partial'
    partial = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert partial['plan_revision'] == 1 and len(partial['episodes']) == 2
    assert partial['appended_from'] is None
    serial.script['fail'] = None
    failed = next(chunk for chunk in chunks_of(bid)
                  if chunk['task'] == 'novel_complete' and chunk['status'] == 'failed')
    quote = run(breakdown.retry_quote(bid, failed['id'], OWNER, 'qwen'))
    run(breakdown.retry(bid, failed['id'], OWNER, quote['id']))
    drain(serial)
    done = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert done['plan_revision'] == 2 and len(done['episodes']) == 4
    assert done['appended_from'] == 3


def test_continuation_two_segment_partial_publishes_once_after_retry(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    before = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert before['plan_revision'] == 1 and len(before['episodes']) == 2
    # 新章跨两段：6–15 一段、16 一段。只让第二段的补全批失败，
    # 第一段的分集批会成功，但整次拆解仍是 partial，不能发布。
    sync_to(serial, range(1, 17), bodies={3: changed_body(3)})
    serial.script['fail'] = (lambda task, inputs, repair:
                             task == 'novel_complete' and inputs['chapters'][0]['chapter'] == 16)
    start_continuation(serial)
    drain(serial)
    assert run(breakdown.get_current(serial.pid, OWNER))['status'] == 'partial'
    new_chunks = [chunk for chunk in chunks_of(bid) if (chunk['source'].get('round') or 0) == 1]
    assert [(chunk['task'], chunk['status']) for chunk in new_chunks] == [
        ('novel_complete', 'succeeded'), ('novel_complete', 'failed'),
        ('episode_plan', 'succeeded'), ('episode_plan', 'blocked')]
    partial = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert partial['plan_revision'] == 1 and len(partial['episodes']) == 2
    assert partial['appended_from'] is None
    assert project_row(serial.pid)['plan_revision'] == 1
    # 单批重跑成功后只发布一次：revision 加 1，两段的新集都在。
    serial.script['fail'] = None
    failed = next(chunk for chunk in chunks_of(bid)
                  if chunk['task'] == 'novel_complete' and chunk['status'] == 'failed')
    quote = run(breakdown.retry_quote(bid, failed['id'], OWNER, 'qwen'))
    run(breakdown.retry(bid, failed['id'], OWNER, quote['id']))
    drain(serial)
    done = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert done['plan_revision'] == 2 and len(done['episodes']) == 6
    assert done['appended_from'] == 3
    assert [(episode['unit_from'], episode['unit_to']) for episode in done['episodes']] == [
        (1, 5), (6, 10), (11, 20), (21, 30), (31, 31), (32, 32)]
    _assert_marking(done, 11)


def test_second_continuation_after_approval_appends_only_new_round(serial):
    first_breakdown(serial)
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    approved = run(breakdown_plan.approve(serial.pid, OWNER,
                                          project_row(serial.pid)['plan_revision']))
    assert approved['g0_approved'] is True and approved['appended_from'] is None
    first_round = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert [episode['title'] for episode in first_round['episodes']] == [
        '第 1–5 场分集', '第 6–10 场分集', '第 11–13 场分集', '第 14–16 场分集']
    sync_to(serial, range(1, 11), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    second = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert second['plan_revision'] == 3 and second['g0_approved'] is False
    assert [episode['no'] for episode in second['episodes']] == [1, 2, 3, 4, 5, 6]
    for before, after in zip(first_round['episodes'], second['episodes'][:4]):
        assert (after['title'], after['unit_from'], after['unit_to']) == (
            before['title'], before['unit_from'], before['unit_to'])
    assert second['appended_from'] == 5
    assert [(episode['unit_from'], episode['unit_to']) for episode in second['episodes'][4:]] == [(17, 18), (19, 20)]
    _assert_marking(second, 17)


def test_two_rounds_before_approval_mark_both_rounds_new(serial):
    first_breakdown(serial)
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    first_round = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert first_round['appended_from'] == 3 and first_round['g0_approved'] is False
    sync_to(serial, range(1, 11), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    second = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert second['plan_revision'] == 3 and second['g0_approved'] is False
    assert second['appended_from'] == 3
    _assert_marking(second, 11)
    assert [episode['unit_from'] for episode in second['episodes'][2:]] == [11, 14, 17, 19]


# ---------------------------------------------------------------------------
# §4.6 第 3 条：续拆进行中的视图 / casting
# ---------------------------------------------------------------------------

def test_continuing_view_hides_new_units_and_shows_new_cast(serial):
    first_breakdown(serial, approve=True)
    previous = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert previous['g0_approved'] is True
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)},
            characters=[{'id': 'C2', 'name': '阿禾', 'role': 'main', 'appearance': ''},
                        {'id': 'C3', 'name': '渔夫', 'role': 'supporting', 'appearance': ''}])
    start_continuation(serial)
    view = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert view['continuing'] is True
    assert view['g0_approved'] is True
    assert len(view['episodes']) == 2
    assert all(unit['seq'] <= 10 for unit in view['units'])
    assert view['unassigned'] == []
    _, markdown = run(breakdown_plan.export_markdown(serial.pid, OWNER))
    section = markdown.split('## 未纳入的单元', 1)[1].split('\n## ', 1)[0]
    assert '无' in section and '第 6 章' not in section
    assert '第 6 章第 1 场' not in markdown
    state = run(casting.state(serial.pid, OWNER))
    names = {entry['name'] for entry in state['items']}
    assert '渔夫' in names
    assert state['g0_approved'] is True
    assert state['g1']['approved'] is False
    fisher = next(entry for entry in state['items'] if entry['name'] == '渔夫')
    assert fisher['orphaned'] is False


# ---------------------------------------------------------------------------
# §4.6 第 3 条：续拆 partial 的 409
# ---------------------------------------------------------------------------

def test_continuation_partial_blocks_ops_approve_quote_and_sync(serial):
    first_breakdown(serial, approve=True)
    project = project_row(serial.pid)
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    serial.script['fail'] = (lambda task, inputs, repair:
                             task == 'novel_complete' and inputs['chapters'][0]['chapter'] == 6)
    start_continuation(serial)
    drain(serial)
    current = run(breakdown.get_current(serial.pid, OWNER))
    assert current['status'] == 'partial'
    plan = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert plan['g0_approved'] is True and plan['continuing'] is True
    tasks = [
        (breakdown_plan.operate_episodes(serial.pid, OWNER, {
            'expected_revision': project['plan_revision'], 'op': 'edit', 'no': 1,
            'fields': {'title': '不该成功'}}),
         '拆解尚未完成，完成后才能修改分集方案'),
        (breakdown_plan.approve(serial.pid, OWNER, project['plan_revision']),
         '拆解尚未全部完成，不能批准分集方案'),
        (breakdown.continue_quote(serial.pid, OWNER),
         '拆解尚未全部完成，不能续拆'),
        (sources.sync_source(OWNER, serial.pid, project_row(serial.pid)['snapshot_no']),
         '导演模型任务进行中，完成后再同步'),
    ]
    for coroutine, message in tasks:
        with pytest.raises(HTTPException) as error:
            run(coroutine)
        assert error.value.status_code == 409
        assert error.value.detail == message
    assert [chunk['status'] for chunk in chunks_of(current['id'])] == [
        'succeeded', 'succeeded', 'failed', 'blocked']
    assert run(breakdown_plan.get_episodes(serial.pid, OWNER))['g0_approved'] is True


def test_continuation_partial_without_active_jobs_blocks_sync(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 17), bodies={3: changed_body(3)})
    # 让本轮最后一个分集批失败：组里没有 queued/running job，但拆解仍是 partial。
    serial.script['fail'] = (lambda task, inputs, repair:
                             task == 'episode_plan'
                             and inputs['units'][0]['label'].startswith('第 16 章'))
    start_continuation(serial)
    drain(serial)
    assert run(breakdown.get_current(serial.pid, OWNER))['status'] == 'partial'
    active = many('SELECT status FROM studio_jobs WHERE group_id=?', (bid,))
    assert not any(row['status'] in {'queued', 'running'} for row in active)
    snapshot_before = project_row(serial.pid)['snapshot_no']
    install_book(serial.state, range(1, 18), bodies={3: changed_body(3)})
    with pytest.raises(HTTPException) as error:
        run(sources.sync_source(OWNER, serial.pid, snapshot_before))
    assert error.value.status_code == 409
    assert error.value.detail == '续拆进行中，完成后再同步'
    assert project_row(serial.pid)['snapshot_no'] == snapshot_before
    # 本轮完成后同步照常。
    serial.script['fail'] = None
    failed = next(chunk for chunk in chunks_of(bid)
                  if chunk['task'] == 'episode_plan' and chunk['status'] == 'failed')
    quote = run(breakdown.retry_quote(bid, failed['id'], OWNER, 'qwen'))
    run(breakdown.retry(bid, failed['id'], OWNER, quote['id']))
    drain(serial)
    assert run(breakdown.get_current(serial.pid, OWNER))['status'] == 'done'
    synced = run(sources.sync_source(OWNER, serial.pid, project_row(serial.pid)['snapshot_no']))
    assert synced['snapshot']['no'] == snapshot_before + 1


def test_rebreakdown_published_view_excludes_unpublished_continuation_units(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    # 补全批成功、分集批失败：新单元已经落库，但本轮方案没有发布。
    serial.script['fail'] = lambda task, inputs, repair: task == 'episode_plan'
    start_continuation(serial)
    drain(serial)
    current = run(breakdown.get_current(serial.pid, OWNER))
    assert current['status'] == 'partial'
    assert current['units_count'] == 16
    quote = run(breakdown.quote(serial.pid, OWNER))
    started = run(breakdown.start(serial.pid, OWNER, quote['id']))
    assert started['id'] != bid and started['status'] == 'running'
    # 已发布方案视图仍指向旧拆解；未发布的本轮新单元不能算进「未纳入」。
    view = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert view['rebreakdown_pending'] is True
    assert view['breakdown_id'] == bid
    assert len(view['episodes']) == 2
    assert view['unassigned'] == [] and view['uncovered'] == []
    assert all(unit['seq'] <= 10 for unit in view['units'])
    _, markdown = run(breakdown_plan.export_markdown(serial.pid, OWNER))
    section = markdown.split('## 未纳入的单元', 1)[1].split('\n## ', 1)[0]
    assert '无' in section
    assert '第 6 章第 1 场' not in section
    assert '第 6 章第 1 场' not in markdown


# ---------------------------------------------------------------------------
# §4.6 第 3 条：取消与整本重拆
# ---------------------------------------------------------------------------

def test_cancel_without_continuation_is_unchanged(serial):
    quote = run(breakdown.quote(serial.pid, OWNER))
    started = run(breakdown.start(serial.pid, OWNER, quote['id']))
    assert started['status'] == 'running'
    cancelled = run(breakdown.cancel(started['id'], OWNER))
    assert cancelled['status'] == 'cancelled'
    assert [chunk['status'] for chunk in cancelled['chunks']] == ['cancelled', 'cancelled']
    assert all(chunk['reserved_amount'] == 0 for chunk in cancelled['chunks'])


@pytest.mark.parametrize('provider', ['qwen', 'claude'])
def test_cancel_guard_running_and_partial_then_full_rebreakdown(serial, provider):
    run(brain_jobs.patch_project(serial.pid, OWNER, provider))
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    running = breakdown_row(bid)
    running_chunks = [(chunk['id'], chunk['status']) for chunk in chunks_of(bid)]
    with pytest.raises(HTTPException) as error:
        run(breakdown.cancel(bid, OWNER))
    assert error.value.status_code == 409
    assert error.value.detail == '续拆进行中不能取消，可以等它完成或单批重跑'
    assert breakdown_row(bid)['status'] == 'running'
    assert breakdown_row(bid)['import_json'] == running['import_json']
    assert [(chunk['id'], chunk['status']) for chunk in chunks_of(bid)] == running_chunks
    # 本轮失败后 partial 仍不能取消，也没有任何变化。
    serial.script['fail'] = (lambda task, inputs, repair:
                             task == 'novel_complete' and inputs['chapters'][0]['chapter'] == 6)
    drain(serial)
    partial = breakdown_row(bid)
    assert partial['status'] == 'partial'
    partial_chunks = [(chunk['id'], chunk['status']) for chunk in chunks_of(bid)]
    partial_reserved = reserved_total(bid)
    with pytest.raises(HTTPException):
        run(breakdown.cancel(bid, OWNER))
    assert breakdown_row(bid)['import_json'] == partial['import_json']
    assert [(chunk['id'], chunk['status']) for chunk in chunks_of(bid)] == partial_chunks
    assert reserved_total(bid) == partial_reserved
    # 整本重新拆解：取消未执行批、释放预留、旧拆解记 superseded_by。
    pending = [chunk for chunk in chunks_of(bid)
               if (chunk['source'].get('round') or 0) == 1 and chunk['status'] in {'queued', 'blocked'}]
    assert pending
    pending_jobs = [one('SELECT * FROM studio_jobs WHERE id=?', (chunk['job_id'],)) for chunk in pending]
    released = sum(float(job['reserved_amount']) for job in pending_jobs)
    before_committed = run(spend.today(OWNER))['committed_cny']
    before_month = float(run(spend.brain_month_used(OWNER)))
    quote = run(breakdown.quote(serial.pid, OWNER))
    started = run(breakdown.start(serial.pid, OWNER, quote['id']))
    assert started['id'] != bid
    for job in pending_jobs:
        latest = one('SELECT * FROM studio_jobs WHERE id=?', (job['id'],))
        assert latest['status'] == 'cancelled' and float(latest['reserved_amount']) == 0
    assert breakdown_row(bid)['superseded_by'] == started['id']
    new_reserved = sum(float(job['reserved_amount'])
                       for job in many('SELECT * FROM studio_jobs WHERE group_id=?', (started['id'],)))
    assert new_reserved > 0
    if provider == 'qwen':
        after_committed = run(spend.today(OWNER))['committed_cny']
        assert after_committed == pytest.approx(before_committed - released + new_reserved, abs=1e-6)
    else:
        after_month = float(run(spend.brain_month_used(OWNER)))
        assert after_month == pytest.approx(before_month - released + new_reserved, abs=1e-6)


def test_cancel_guard_after_recovery_to_partial(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    mapping = next(chunk for chunk in chunks_of(bid) if chunk['task'] == 'novel_complete'
                   and (chunk['source'].get('round') or 0) == 1)
    assert run(store.cas_job(mapping['job_id'], 'queued',
                             {'status': 'running', 'run_token': 'offline'}))
    run(recovery.recover_studio_jobs())
    current = run(breakdown.get_current(serial.pid, OWNER))
    assert current['status'] == 'partial'
    assert next(chunk for chunk in current['chunks'] if chunk['id'] == mapping['id'])['status'] == 'uncertain'
    before = breakdown_row(bid)['import_json']
    reserved = reserved_total(bid)
    with pytest.raises(HTTPException) as error:
        run(breakdown.cancel(bid, OWNER))
    assert error.value.status_code == 409
    assert breakdown_row(bid)['import_json'] == before
    assert reserved_total(bid) == reserved
    assert one('SELECT * FROM studio_chunks WHERE id=?', (mapping['id'],))['status'] == 'uncertain'


# ---------------------------------------------------------------------------
# §4.6 第 3 条：兼容旧拆解
# ---------------------------------------------------------------------------

def test_legacy_breakdown_without_continuation_keys_continues_once(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    legacy_keys = ('_covered_through', '_chapter_basis', '_published_chunk_ids', '_published_max_seq')
    update_imported(bid, lambda imported: [imported.pop(key, None) for key in legacy_keys])
    view = run(breakdown.get_current(serial.pid, OWNER))
    assert view['covered_through'] == 5
    assert view['stale_chapters'] == []
    assert view['continuations'] == []
    assert view['continuable'] is False
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)})
    start_continuation(serial)
    drain(serial)
    imported = breakdown_row(bid)['imported']
    assert imported['_covered_through'] == 8
    assert sorted(int(key) for key in imported['_chapter_basis']) == list(range(1, 9))
    assert all(imported['_chapter_basis'][str(number)]['snapshot_no'] == 1 for number in range(1, 6))
    assert imported['_published_max_seq'] == 16
    assert [item['round'] for item in imported['_continuations']] == [1]
    assert len(imported['_published_chunk_ids']) == 2
    plan = run(breakdown_plan.get_episodes(serial.pid, OWNER))
    assert plan['plan_revision'] == 2
    assert [episode['no'] for episode in plan['episodes']] == [1, 2, 3, 4]
    assert plan['appended_from'] == 3


# ---------------------------------------------------------------------------
# §4.8 R1：快照读不出时的降级
# ---------------------------------------------------------------------------

def test_current_view_degrades_when_manifest_unreadable(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    snapshot_no = project_row(serial.pid)['snapshot_no']
    sql('UPDATE studio_snapshots SET manifest_sha256=? WHERE project_id=? AND owner=? AND no=?',
        ('0' * 64, serial.pid, OWNER, snapshot_no))
    units_before = units_of(bid)
    view = run(breakdown.get_current(serial.pid, OWNER))
    assert view['status'] == 'done'
    assert view['continuable'] is False
    assert view['continue_from'] is None and view['continue_to'] is None
    assert view['changed_covered'] == []
    assert any('当前快照无法读取' in warning for warning in view['warnings'])
    # 未续拆过的拆解取消也不因 manifest 读不出而 500。
    cancelled = run(breakdown.cancel(bid, OWNER))
    assert cancelled['status'] == 'done'
    assert any('当前快照无法读取' in warning for warning in cancelled['warnings'])
    assert units_of(bid) == units_before


# ---------------------------------------------------------------------------
# §4.6 第 3 条：视图
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('serial', [{'numbers': list(range(1, 6)), 'statuses': {2: 'stale'}}], indirect=True)
def test_views_continuable_changed_covered_and_stale(serial):
    first_breakdown(serial)
    bid = project_row(serial.pid)['breakdown_id']
    view = run(breakdown.get_current(serial.pid, OWNER))
    assert view['covered_through'] == 5
    assert view['continuable'] is False and view['continue_from'] is None and view['continue_to'] is None
    assert view['changed_covered'] == [] and view['stale_chapters'] == [2]
    assert view['continuations'] == [] and view['continuing'] is False
    # 同步出新章、旧章改正文、待复核的章在书斋里改好。
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)}, statuses={2: 'done'})
    insert_queued_probe(serial, 'views')
    try:
        assert run(breakdown.get_current(serial.pid, OWNER))['continuable'] is False
    finally:
        drop_queued_probe('views')
    view = run(breakdown.get_current(serial.pid, OWNER))
    assert view['continuable'] is True
    assert (view['continue_from'], view['continue_to']) == (6, 8)
    assert view['changed_covered'] == [3]
    assert view['stale_chapters'] == [2]
    start_continuation(serial)
    view = run(breakdown.get_current(serial.pid, OWNER))
    assert view['continuing'] is True and view['status'] == 'running'
    assert view['continuable'] is False
    assert view['continue_from'] is None and view['continue_to'] is None
    assert view['continuations'] == [{'round': 1, 'from': 6, 'to': 8, 'snapshot_no': 2}]
    assert view['changed_covered'] == [3] and view['stale_chapters'] == [2]
    drain(serial)
    view = run(breakdown.get_current(serial.pid, OWNER))
    assert view['continuing'] is False and view['status'] == 'done'
    assert view['changed_covered'] == [3] and view['stale_chapters'] == [2]
    assert len(view['continuations']) == 1
    # 再同步一版，第 3 章没变：按拆解依据比较，仍算改过。
    sync_to(serial, range(1, 9), bodies={3: changed_body(3)}, statuses={2: 'done'})
    assert run(breakdown.get_current(serial.pid, OWNER))['changed_covered'] == [3]
    # 把第 3 章改回快照 1 的原文再同步：不再算改过。
    sync_to(serial, range(1, 9), statuses={2: 'done'})
    final = run(breakdown.get_current(serial.pid, OWNER))
    assert final['changed_covered'] == []
    assert final['stale_chapters'] == [2]
    # 退役与「不是小说来源」都不再可续拆。
    sql("UPDATE studio_breakdowns SET status='cancelled' WHERE id=?", (bid,))
    assert run(breakdown.get_current(serial.pid, OWNER))['continuable'] is False
    sql("UPDATE studio_breakdowns SET status='done' WHERE id=?", (bid,))
    sql("UPDATE studio_snapshots SET kind='paste' WHERE project_id=? AND no=?",
        (serial.pid, project_row(serial.pid)['snapshot_no']))
    assert run(breakdown.get_current(serial.pid, OWNER))['continuable'] is False


def test_views_continuable_requires_completed_breakdown(serial):
    quote = run(breakdown.quote(serial.pid, OWNER))
    started = run(breakdown.start(serial.pid, OWNER, quote['id']))
    assert started['status'] == 'running'
    assert run(breakdown.get_current(serial.pid, OWNER))['continuable'] is False
    drain(serial)
    assert run(breakdown.get_current(serial.pid, OWNER))['continuable'] is False
