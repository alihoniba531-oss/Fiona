"""拆解数据层独立验收；文字与人物均为测试自写。"""
from copy import deepcopy

import pytest

from studio.breakdown_material import batch_plan, locate_scenes, merge_bible, split_block, structured_import


def novel(lengths):
    entries = [{'index': n, 'chapter': n, 'chars': size, 'body': '甲' * size,
                'outline': {'scenes': [{'location': '门房', 'summary': f'第{n}章递信。'}]}}
               for n, size in enumerate(lengths, 1)]
    return {'kind': 'novel', 'chapters': entries, 'bible': {}, 'compass': {}}, entries


def unit(seq, *, chapter=1, name='阿宁', location='门房', start=0, end=100, summary='递信。'):
    return {'seq': seq, 'chapter': chapter, 'characters': [name], 'location': location,
            'summary': summary, 'start': start, 'end': end}


def test_structured_import_is_snapshot_only_and_preserves_source_facts():
    manifest, _ = novel([100, 100])
    manifest['bible'] = {'locked': {'characters': [
        {'id': 'C1', 'name': '阿宁', 'role': 'main', 'age': '二十岁', 'appearance': '短发',
         'personality': '谨慎', 'motivation': '归还借书'},
        {'id': 'C2', 'name': '阿禾', 'appearance': ''}], 'adaptation': {'max_main_characters': 3}},
        'dynamic': {'chapter_summaries': [{'chapter': 2, 'summary': '阿宁决定等到天亮。'}],
                    'arc_summaries': [{'from': 1, 'to': 2, 'summary': '借书归还。'}],
                    'foreshadowing': [{'description': '信封缺角'}], 'timeline': ['黎明递信']}}
    manifest['compass'] = {'logline': '一封旧信带来归还的决定。', 'theme': '守信', 'core_conflict': '是否等待',
                           'main_threads': [{'id': 'T1', 'description': '归还旧书'}]}
    manifest['chapters'][1]['outline'] = {}
    before = deepcopy(manifest)
    imported = structured_import(manifest)
    assert manifest == before
    assert imported['characters'][0]['ref_id'] == 'C1'
    assert imported['characters'][0]['appearance_source'] == 'workshop'
    assert '二十岁' in imported['characters'][0]['description']
    assert imported['characters'][1]['needs_author'] is True
    assert [row['seq'] for row in imported['units']] == [1, 2]
    assert imported['units'][1]['summary'] == '阿宁决定等到天亮。'
    assert imported['units'][0]['est_seconds'] is None
    assert imported['synopsis']['main_threads'] == manifest['compass']['main_threads']
    assert imported['synopsis']['arc_summaries'] == manifest['bible']['dynamic']['arc_summaries']
    assert imported['foreshadowing'] == [{'description': '信封缺角'}]
    assert imported['timeline'] == ['黎明递信']
    assert imported['adaptation'] == {'max_main_characters': 3}


@pytest.mark.parametrize('lengths', [[1] * 25, [8000] * 12, [24000, 1, 23999, 1]])
def test_novel_batches_obey_both_limits_and_ten_chapter_segments(lengths):
    manifest, entries = novel(lengths)
    _, chunks = batch_plan(manifest, entries)
    maps = [row for row in chunks if row['task'] == 'novel_complete']
    assert [chapter['chapter'] for row in maps for chapter in row['inputs']['chapters']] == list(range(1, len(lengths) + 1))
    for row in maps:
        assert len(row['inputs']['chapters']) <= 10
        assert sum(len(chapter['text']) for chapter in row['inputs']['chapters']) <= 24000
    plans = [row for row in chunks if row['task'] == 'episode_plan']
    assert len(plans) == (len(lengths) + 9) // 10
    for index, plan in enumerate(plans):
        expected = {row['no'] for row in maps if row['source']['segment'] <= index}
        assert expected <= set(plan['depends'])
        if index:
            assert plans[index - 1]['no'] in plan['depends']


def test_oversized_single_chapter_is_split_without_changing_snapshot():
    manifest, entries = novel([48001, 100])
    before = deepcopy(entries)
    _, chunks = batch_plan(manifest, entries)
    maps = [row for row in chunks if row['task'] == 'novel_complete']
    chapter_parts = [(row, chapter) for row in maps for chapter in row['inputs']['chapters'] if chapter['chapter'] == 1]
    assert ''.join(chapter['text'] for _, chapter in chapter_parts) == entries[0]['body']
    assert [row['source']['chapter_offsets']['1'] for row, _ in chapter_parts] == [0, 24000, 47971]
    assert all(len(chapter['text']) >= 30 for _, chapter in chapter_parts)
    assert all(sum(len(chapter['text']) for chapter in row['inputs']['chapters']) <= 24000 for row in maps)
    assert entries == before


def test_text_subblocks_preserve_exact_paragraph_offsets_and_dependencies():
    text = ('甲' * 5999 + '\n') * 5
    entries = [{'index': i, 'chapter': i, 'body': text if i == 1 else '乙' * 100,
                'start': 100000 * i} for i in range(1, 7)]
    _, chunks = batch_plan({'kind': 'paste', 'chapters': entries}, entries)
    maps = [row for row in chunks if row['task'] == 'text_map']
    parts = [row for row in maps if row['source']['block_no'] == 1]
    assert ''.join(row['inputs']['text'] for row in parts) == text
    assert all(len(row['inputs']['text']) <= 10000 for row in parts)
    assert all(row['inputs']['text'].endswith('\n') for row in parts)
    assert parts[0]['source']['start'] == 100000
    assert parts[-1]['source']['end'] == 100000 + len(text)
    assert all(a['source']['end'] == b['source']['start'] for a, b in zip(parts, parts[1:]))
    synopsis = next(row for row in chunks if row['task'] == 'synopsis')
    assert set(synopsis['depends']) == {row['no'] for row in maps}
    plans = [row for row in chunks if row['task'] == 'episode_plan']
    assert [(row['source']['block_from'], row['source']['block_to']) for row in plans] == [(1, 5), (6, 6)]
    assert all(synopsis['no'] in row['depends'] for row in plans)
    assert plans[0]['no'] in plans[1]['depends']


@pytest.mark.parametrize('size,parts', [(12000, 1), (12001, 2), (30001, 4)])
def test_subblock_threshold_and_unbroken_paragraph_fallback(size, parts):
    result = split_block({'body': '甲' * size, 'start': 30})
    assert len(result) == parts
    assert result[0]['start'] == 30 and result[-1]['end'] == size + 30
    assert ''.join(row['body'] for row in result) == '甲' * size
    assert all(len(row['body']) <= (12000 if parts == 1 else 10000) for row in result)


def test_anchor_positions_are_exact_monotonic_and_cover_full_block():
    text = '门外天色初明。阿宁轻轻推开木门。阿禾在窗边抬起头来。'
    scenes = [{'start_anchor': '门外天色初明。'}, {'start_anchor': '阿宁轻轻推开木门。'},
              {'start_anchor': '阿禾在窗边抬起头来。'}]
    located, warnings = locate_scenes(text, scenes, 500)
    assert warnings == []
    assert located[0]['start'] == 500 and located[-1]['end'] == 500 + len(text)
    assert located[1]['start'] == 500 + text.index('阿宁')
    assert all(a['end'] == b['start'] for a, b in zip(located, located[1:]))
    assert all(row['start'] <= row['end'] for row in located)


def test_missing_anchor_records_warning_without_guess_or_offset_regression():
    located, warnings = locate_scenes('阿宁推门。阿禾抬头。', [
        {'start_anchor': '阿宁推门。'}, {'start_anchor': '原文没有这句话。'}, {'start_anchor': '阿禾抬头。'}], 20)
    assert len(warnings) == 1
    assert located[1]['start'] == located[1]['end'] == located[0]['end'] == 25
    assert located[2]['start'] == 25
    assert located[-1]['end'] == 30


def test_normalized_aliases_merge_transitively_keep_first_excerpt_and_earliest_unit():
    chunks = [{'inputs': {'text': '阿宁身穿灰衣。阿禾扎着长辫。'}, 'output': {'characters': [
        {'name': 'Ａ 宁', 'aliases': ['Ning'], 'role': '送信人', 'excerpt': '阿宁身穿灰衣。'},
        {'name': 'ning', 'aliases': ['小宁'], 'excerpt': ''},
        {'name': '小宁', 'aliases': [], 'excerpt': '阿禾扎着长辫。'}]}}]
    result, warnings = merge_bible({}, chunks, [unit(3, name='小宁'), unit(1, name='A宁')])
    assert len(result) == 1 and warnings == []
    assert result[0]['excerpt'] == '阿宁身穿灰衣。'
    assert result[0]['first_unit'] == 1
    assert result[0]['needs_author'] is False
    assert {'Ning', '小宁'} <= set(result[0]['aliases'])


def test_workshop_ids_stay_distinct_and_workshop_appearance_has_priority():
    imported = {'characters': [
        {'name': '阿宁', 'ref_id': 'C1', 'appearance': '工坊短发', 'appearance_source': 'workshop'},
        {'name': '阿宁', 'ref_id': 'C2', 'appearance': '', 'appearance_source': 'none'}]}
    chunks = [{'inputs': {'chapters': [{'chapter': 1, 'text': '他的袖口绣着一片叶子。'}]},
               'output': {'appearance_fills': [{'character': 'C1', 'excerpt': '他的袖口绣着一片叶子。'}]}}]
    result, _ = merge_bible(imported, chunks, [unit(1, name='C1'), unit(2, name='C2')])
    assert len(result) == 2
    by_id = {row['ref_id']: row for row in result}
    assert by_id['C1']['appearance'] == '工坊短发'
    assert by_id['C1']['appearance_source'] == 'workshop'
    assert by_id['C2']['needs_author'] is True


def test_invented_or_wrong_chapter_excerpts_are_dropped_and_warned():
    chunks = [{'inputs': {'chapters': [{'chapter': 1, 'text': '阿宁来到门房。'},
                                     {'chapter': 2, 'text': '灰色袖口沾着雨水。'}]},
               'output': {'new_characters': [{'name': '阿宁', 'first_chapter': 1, 'excerpt': '灰色袖口沾着雨水。'}],
                          'locations': [{'name': '门房', 'first_chapter': 1, 'excerpt': '模型编造的砖墙。'}]}}]
    result, warnings = merge_bible({}, chunks, [unit(1)])
    assert len(warnings) == 2
    assert all(row['excerpt'] == '' for row in result)
    assert next(row for row in result if row['kind'] == 'character')['needs_author'] is True


def test_text_prop_first_appearance_uses_its_subblock_and_exact_excerpt_scene():
    chunks = [{'source': {'block_no': 1, 'start': 100, 'end': 120},
               'inputs': {'text': '阿宁坐下。桌上有一枚铜铃。'},
               'output': {'props': [{'name': '铜铃', 'excerpt': '桌上有一枚铜铃。'}]}}]
    result, warnings = merge_bible({}, chunks, [unit(1, start=0, end=100),
        unit(2, start=100, end=105), unit(3, start=105, end=120)])
    assert warnings == []
    assert result[0]['first_unit'] == 3


def test_long_chapter_materialization_keeps_absolute_offsets_and_unique_scenes():
    from studio.breakdown import _materialize
    manifest, entries = novel([48001])
    imported, planned = batch_plan(manifest, entries)
    imported['_manifest'] = manifest
    chunks = []
    for row in planned:
        if row['task'] != 'novel_complete':
            continue
        text = row['inputs']['chapters'][0]['text']
        chunks.append({**row, 'status': 'succeeded', 'source': {**row['source'], '_inputs': row['inputs']},
                       'output': {'chapters': [{'chapter': 1, 'scenes': [{'start_anchor': text[:8],
                           'location': '门房', 'summary': '递信。', 'characters': ['阿宁'], 'est_seconds': 90}]}]}})
    units, _, _ = _materialize({'imported': imported}, chunks)
    assert [(row['seq'], row['scene_index'], row['start'], row['end']) for row in units] == [
        (1, 1, 0, 24000), (2, 2, 24000, 47971), (3, 3, 47971, 48001)]
    chunks[0]['status'] = 'failed'
    partial, _, _ = _materialize({'imported': imported}, chunks)
    assert [(row['start'], row['end']) for row in partial] == [(24000, 47971), (47971, 48001)]


def test_pending_novel_keeps_all_outline_scenes_without_duplicate_fallback():
    from studio.breakdown import _materialize
    manifest, entries = novel([25000])
    entries[0]['outline']['scenes'].append({'location': '书房', 'summary': '决定归还旧书。'})
    imported, planned = batch_plan(manifest, entries)
    imported['_manifest'] = manifest
    chunks = [{**row, 'status': 'queued', 'source': {**row['source'], '_inputs': row['inputs']}}
              for row in planned]
    units, _, _ = _materialize({'imported': imported}, chunks)
    assert len(units) == 2 and [row['seq'] for row in units] == [1, 2]
