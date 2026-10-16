"""快照拆解的纯数据运算；调用者在线程中执行。"""
from __future__ import annotations

import unicodedata


def normalize_name(value):
    return ''.join(unicodedata.normalize('NFKC', str(value)).split()).casefold()


def locate_scenes(text, scenes, offset=0):
    """未命中锚点取下个精确命中位置（或块末），保留已定位场景的正文。"""
    warnings, starts, cursor = [], [], 0
    for index, scene in enumerate(scenes):
        anchor = scene.get('start_anchor', '')
        found = text.find(anchor, cursor) if anchor else -1
        if found < 0:
            warnings.append(f'第 {index + 1} 场开头原文未命中，回退到后续命中锚点或块末。')
            starts.append(None)
        else:
            starts.append(found)
            cursor = found
    first_matched = bool(starts and starts[0] is not None)
    following = len(text)
    for index in range(len(starts) - 1, -1, -1):
        if starts[index] is None:
            starts[index] = following
        else:
            following = starts[index]
    if first_matched:
        starts[0] = 0
    return [{**scene, 'start': offset + starts[index],
             'end': offset + (starts[index + 1] if index + 1 < len(starts) else len(text))}
            for index, scene in enumerate(scenes)], warnings


def split_block(entry):
    text, offset = entry['body'], entry.get('start', 0)
    if len(text) <= 12000:
        return [{**entry, 'start': offset, 'end': offset + len(text)}]
    result, start = [], 0
    while start < len(text):
        end = min(start + 10000, len(text))
        if 0 < len(text) - end < 30:
            end = len(text) - 30
        if end < len(text):
            boundary = text.rfind('\n', start, end)
            if boundary > start:
                end = boundary + 1
        result.append({**entry, 'body': text[start:end], 'start': offset + start, 'end': offset + end})
        start = end
    return result


def structured_import(manifest):
    bible = manifest.get('bible') or {}
    locked, dynamic = bible.get('locked') or {}, bible.get('dynamic') or {}
    compass = manifest.get('compass') or {}
    summaries = {item['chapter']: item.get('summary', '') for item in dynamic.get('chapter_summaries', [])}
    characters, units = [], []
    for item in locked.get('characters', []):
        characters.append({**item, 'ref_id': item.get('id'), 'kind': 'character',
                           'description': item.get('description') or '；'.join(
                               f'{label}：{item[key]}' for key, label in
                               [('age', '年龄'), ('personality', '性格'), ('motivation', '动机')] if item.get(key)),
                           'appearance_source': 'workshop' if item.get('appearance') else 'none',
                           'needs_author': not bool(item.get('appearance')), 'excerpt': ''})
    for chapter in manifest['chapters']:
        scenes = (chapter.get('outline') or {}).get('scenes') or [
            {'location': '', 'summary': summaries.get(chapter['chapter'], '')}]
        for index, scene in enumerate(scenes, 1):
            units.append({'seq': len(units) + 1, 'chapter': chapter['chapter'], 'scene_index': index,
                          'label': f"第 {chapter['chapter']} 章第 {index} 场", 'location': scene.get('location', ''),
                          'summary': scene.get('summary', ''), 'characters': scene.get('characters', []),
                          'est_seconds': None, 'change': '', 'start': 0, 'end': chapter['chars']})
    synopsis = {key: compass.get(key, '') for key in ('logline', 'theme', 'core_conflict', 'main_threads')}
    synopsis['arc_summaries'] = dynamic.get('arc_summaries', [])
    return {'characters': characters, 'units': units, 'synopsis': synopsis,
            'foreshadowing': dynamic.get('foreshadowing', []), 'timeline': dynamic.get('timeline', []),
            'adaptation': locked.get('adaptation') or (manifest.get('config') or {}).get('adaptation') or {}}


def batch_plan(manifest, entries):
    novel = manifest['kind'] == 'novel'
    imported = structured_import(manifest) if novel else {'characters': [], 'units': [], 'synopsis': {}}
    chunks, maps, segments = [], [], {}
    def add(task, source, inputs, depends=(), estimate_units=0):
        row = {'no': len(chunks) + 1, 'task': task, 'source': source, 'inputs': inputs,
               'depends': list(depends), 'estimate_units': estimate_units}
        chunks.append(row)
        return row['no']
    if novel:
        groups, current, chars = [], [], 0
        fragments = []
        for entry in entries:
            start = 0
            while start < len(entry['body']):
                end = min(start + 24000, len(entry['body']))
                if 0 < len(entry['body']) - end < 30:
                    end = len(entry['body']) - 30
                if end < len(entry['body']):
                    boundary = entry['body'].rfind('\n', start, end)
                    if boundary > start:
                        end = boundary + 1
                fragments.append({**entry, 'body': entry['body'][start:end], '_chapter_offset': start})
                start = end
        for entry in fragments:
            if current and (len(current) >= 10 or chars + len(entry['body']) > 24000
                            or entry['chapter'] == current[-1]['chapter']
                            or (entry['chapter'] - 1) // 10 != (current[0]['chapter'] - 1) // 10):
                groups.append(current); current, chars = [], 0
            current.append(entry); chars += len(entry['body'])
        if current:
            groups.append(current)
        for group in groups:
            first, last = group[0]['chapter'], group[-1]['chapter']
            segment = (first - 1) // 10
            count = sum(1 for unit in imported['units'] if first <= unit['chapter'] <= last)
            offsets = {str(entry['chapter']): entry['_chapter_offset'] for entry in group}
            fragment_label = (f"（章内字符 {group[0]['_chapter_offset']}–{group[0]['_chapter_offset'] + len(group[0]['body'])}）"
                              if len(group) == 1 and (group[0]['_chapter_offset'] or len(group[0]['body']) < group[0]['chars']) else '')
            number = add('novel_complete', {'chapter_from': first, 'chapter_to': last, 'segment': segment,
                         'label': f'第 {first}–{last} 章{fragment_label} · 补全',
                         'chapter_offsets': offsets, 'indices': [entry['index'] for entry in group],
                         'ranges': [{'index': entry['index'], 'chapter': entry['chapter'],
                                     'start': entry['_chapter_offset'],
                                     'end': entry['_chapter_offset'] + len(entry['body'])} for entry in group]},
                         {'chapters': [{'chapter': entry['chapter'], 'text': entry['body'],
                                        'scenes': (entry.get('outline') or {}).get('scenes', [])} for entry in group],
                          'known_characters': [{'id': char.get('id'), 'name': char['name'],
                                               'has_appearance': bool(char.get('appearance'))}
                                              for char in imported['characters']]}, estimate_units=count)
            maps.append(number); segments.setdefault(segment, []).append(number)
    else:
        for entry in entries:
            segment = (entry['index'] - 1) // 5
            for part, block in enumerate(split_block(entry), 1):
                number = add('text_map', {'block_no': entry['index'], 'segment': segment, 'part': part,
                             'start': block['start'], 'end': block['end'],
                             'label': f"第 {entry['index']} 块 · 通读", 'index': entry['index']},
                             {'text': block['body'], 'block_no': entry['index']}, estimate_units=6)
                maps.append(number); segments.setdefault(segment, []).append(number)
        synopsis = add('synopsis', {'label': '全书梗概'}, {}, maps)
    previous = None
    for segment, dependencies in sorted(segments.items()):
        first, last = segment * (10 if novel else 5) + 1, min((segment + 1) * (10 if novel else 5), len(entries))
        # seq is global: every earlier completion must settle before this segment
        # is numbered, including batches whose scene count changed from the outline.
        deps = [number for number in maps if chunks[number - 1]['source']['segment'] <= segment]
        if not novel:
            deps.append(synopsis)
        if previous:
            deps.append(previous)
        count = sum(chunks[number - 1]['estimate_units'] for number in dependencies)
        previous = add('episode_plan', {'segment': segment, 'chapter_from' if novel else 'block_from': first,
                       'chapter_to' if novel else 'block_to': last,
                       'map_nos': dependencies, 'label': f"第 {first}–{last} {'章' if novel else '块'} · 分集"},
                       {}, deps, count)
    return imported, chunks


def merge_bible(imported, chunks, units, *, warning_by_chunk=None):
    """只接受逐字原文摘录；名字和别名形成同一确定性等价类。"""
    entries, warnings = [], []
    def warn(message, cid=None):
        warnings.append(message)
        if warning_by_chunk is not None:
            warning_by_chunk.setdefault(cid or '__breakdown__', []).append(message)
    for char in imported.get('characters', []):
        entries.append({**char, 'kind': 'character', 'first_chapter': None})
    for chunk in chunks:
        result, inputs = chunk.get('output') or {}, chunk.get('inputs') or {}
        source_info = chunk.get('source') or {}
        chapter_text = {chapter['chapter']: chapter['text'] for chapter in inputs.get('chapters', [])}
        text = inputs.get('text', '')
        for key, kind in (('characters', 'character'), ('new_characters', 'character'), ('locations', 'location'), ('props', 'prop')):
            for raw in result.get(key, []):
                item = {**raw, 'kind': kind, '_source_chunk': chunk.get('id')}
                source = chapter_text.get(item.get('first_chapter'), text)
                excerpt = item.get('excerpt', '')
                if excerpt and (len(excerpt) > 200 or excerpt not in source):
                    warn(f"{item['name']} 的摘录未在对应原文逐字命中，已丢弃。", chunk.get('id'))
                    excerpt = ''
                item['excerpt'] = excerpt
                item['appearance'] = excerpt if kind == 'character' else ''
                item['appearance_source'] = 'excerpt' if excerpt else 'none'
                item['needs_author'] = kind == 'character' and not bool(excerpt)
                chapter = source_info.get('block_no') or item.get('first_chapter')
                item['first_chapter'] = chapter
                if chapter is not None:
                    offset = ((source_info.get('start') or 0) + text.find(excerpt)
                              if text and excerpt else
                              source_info.get('chapter_offsets', {}).get(str(chapter), 0) + source.find(excerpt)
                              if excerpt else None)
                    candidates = [unit for unit in units if unit['chapter'] == chapter]
                    exact = [unit for unit in candidates if offset is not None
                             and unit.get('start') is not None and unit.get('end') is not None
                             and unit['start'] <= offset < unit['end']]
                    # When a map sub-block has no excerpt, use its first scene,
                    # rather than the first scene in the parent snapshot block.
                    if not exact and source_info.get('start') is not None:
                        exact = [unit for unit in candidates if unit.get('start') is not None
                                 and source_info['start'] <= unit['start'] < source_info.get('end', float('inf'))]
                    item['_first_unit_hint'] = min((unit['seq'] for unit in exact or candidates), default=None)
                entries.append(item)
        for fill in result.get('appearance_fills', []):
            excerpt = fill.get('excerpt', '')
            if excerpt and len(excerpt) <= 200 and any(excerpt in value for value in chapter_text.values()):
                entries.append({'name': fill['character'], 'kind': 'character', 'excerpt': excerpt,
                                'appearance': excerpt, 'appearance_source': 'excerpt', 'needs_author': False,
                                '_source_chunk': chunk.get('id')})
            elif excerpt:
                warn(f"{fill['character']} 的外形摘录未在原文逐字命中，已丢弃。", chunk.get('id'))
    merged = []
    for entry in entries:
        names = {normalize_name(value) for value in [entry['name'], entry.get('ref_id'), *entry.get('aliases', [])] if value}
        matches = [item for item in merged if item['kind'] == entry['kind'] and (
            bool(entry.get('ref_id') and entry.get('ref_id') == item.get('ref_id')) or names & item['_names'])
            and not (entry.get('ref_id') and item.get('ref_id') and entry['ref_id'] != item['ref_id'])]
        known_ids = {item['ref_id'] for item in matches if item.get('ref_id')}
        if len(known_ids) > 1:
            warn(f"{entry['name']} 对应多个小说工坊人物 ID，未自动合并这些人物，请作者核对。", entry.get('_source_chunk'))
            chosen = matches[0].get('ref_id') or next(iter(sorted(known_ids)))
            matches = [item for item in matches if not item.get('ref_id') or item['ref_id'] == chosen]
        if not matches:
            merged.append({**entry, '_names': names, 'aliases': list(entry.get('aliases', []))})
            continue
        target = matches[0]
        for extra in [*matches[1:], entry]:
            target['_names'].update(extra.get('_names', names))
            target['aliases'] = list(dict.fromkeys([*target['aliases'], *extra.get('aliases', []),
                                                    *([extra['name']] if extra['name'] != target['name'] else [])]))
            for field in ('appearance', 'excerpt', 'role', 'description', 'ref_id'):
                if not target.get(field) and extra.get(field):
                    target[field] = extra[field]
                    if field == 'appearance':
                        target['appearance_source'] = extra.get('appearance_source', 'excerpt')
            if extra.get('first_chapter') and (not target.get('first_chapter') or extra['first_chapter'] < target['first_chapter']):
                target['first_chapter'] = extra['first_chapter']
            hints = [value for value in [target.get('_first_unit_hint'), extra.get('_first_unit_hint')] if value is not None]
            target['_first_unit_hint'] = min(hints) if hints else None
            if extra in merged:
                merged.remove(extra)
    for item in merged:
        names = item.pop('_names')
        appearances = [unit['seq'] for unit in units if (
            any(normalize_name(value) in names or value == item.get('ref_id') for value in unit.get('characters', []))
            if item['kind'] == 'character' else
            (normalize_name(unit.get('location', '')) in names if item['kind'] == 'location' else
             (any(name and name in normalize_name(unit.get('summary', '')) for name in names)
              or (item.get('_first_unit_hint') is None and item.get('first_chapter') is not None
                  and item['first_chapter'] == unit['chapter']))))]
        if item.get('_first_unit_hint') is not None:
            appearances.append(item['_first_unit_hint'])
        item['first_unit'] = min(appearances) if appearances else next(
            (unit['seq'] for unit in units if unit['chapter'] == item.get('first_chapter')), None)
        item.pop('_first_unit_hint', None)
        item.pop('_source_chunk', None)
        item['needs_author'] = item['kind'] == 'character' and not bool(item.get('appearance'))
    return merged, warnings
