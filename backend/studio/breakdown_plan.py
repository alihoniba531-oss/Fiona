"""WO3c 可编辑总表、确定性分集操作、revision/G0 与安全 Markdown 导出。"""
from __future__ import annotations

import asyncio
import html
import json
import re
import unicodedata
import uuid

from fastapi import HTTPException

from . import store


_SYNOPSIS_LABELS = {'logline': '一句话梗概', 'theme': '主题', 'core_conflict': '核心冲突',
                    'main_threads': '主线', 'arc_summaries': '分段梗概', 'synopsis': '梗概',
                    'genre': '类型', 'tone': '基调', 'themes': '主题'}
_PROVIDER_LABELS = {'qwen': '千问', 'deepseek': 'DeepSeek', 'claude': 'Claude'}
_FIELD_LABELS = {**_SYNOPSIS_LABELS, 'id': '编号', 'name': '名称', 'title': '标题',
                 'description': '说明', 'summary': '摘要', 'from': '起始章节', 'to': '结束章节',
                 'start_chapter': '起始章节', 'end_chapter': '结束章节',
                 'from_chapter': '起始章节', 'to_chapter': '结束章节', 'chapter': '章节',
                 'planted_at': '铺设位置', 'planted_chapter': '铺设章节', 'planted_at_chapter': '铺设章节',
                 'resolved_at': '回收位置', 'resolved_chapter': '回收章节', 'resolved_at_chapter': '回收章节',
                 'payoff_plan': '回收计划', 'importance': '重要性', 'status': '状态', 'date': '日期',
                 'time': '时间', 'event': '事件', 'details': '详情', 'characters': '人物', 'notes': '备注'}


def _decode(row, fields):
    result = dict(row)
    for key, target in fields.items():
        result[target] = json.loads(result.get(key) or ('[]' if target in {'aliases', 'episodes', 'characters'} else '{}'))
        result.pop(key, None)
    return result


def _normal(name):
    return ''.join(unicodedata.normalize('NFKC', str(name)).split()).casefold()


async def _breakdown(db, bid, owner):
    row = await store._one(db, 'SELECT * FROM studio_breakdowns WHERE id=? AND owner=?', (bid, owner))
    if row is None:
        raise HTTPException(404, 'Not Found')
    await store._project(db, row['project_id'], owner)
    return row


async def _current(db, pid, owner):
    project = await store._project(db, pid, owner)
    breakdown = None
    if project.get('breakdown_id'):
        breakdown = await _breakdown(db, project['breakdown_id'], owner)
    return project, breakdown


async def _published(db, project, active):
    """项目指向活动拆解；revision 指向作者仍可查看的已发布方案。"""
    revision = await store._one(db, '''SELECT plan_json,created_reason FROM studio_plan_revisions
        WHERE project_id=? AND owner=? ORDER BY revision DESC LIMIT 1''', (project['id'], project['owner']))
    snapshot = await asyncio.to_thread(json.loads, revision['plan_json']) if revision else {}
    bid = snapshot.get('breakdown_id')
    published = await _breakdown(db, bid, project['owner']) if bid else None
    presentation = dict(project)
    if published and (not active or published['id'] != active['id']):
        # Starting a replacement may change project defaults and cancel the old
        # work ledger. Its accepted plan and target settings remain published.
        settings = snapshot.get('settings', {})
        for field in ('episode_seconds_min', 'episode_seconds_max'):
            if field in settings:
                presentation[field] = settings[field]
        published = dict(published)
        previous_status = snapshot.get('status')
        published['status'] = ('partial' if revision['created_reason'] == 'partial' or previous_status == 'partial'
                               else 'done')
    presentation['breakdown_id'] = published['id'] if published else None
    return presentation, published


def _activity(plan, published, active):
    plan.update(breakdown_id=published['id'] if published else None,
                active_breakdown_id=active['id'] if active else None,
                active_breakdown_status=active['status'] if active else None,
                rebreakdown_pending=bool(published and active and published['id'] != active['id']
                                        and active['status'] in {'draft', 'running', 'partial'}))
    return plan


async def _units(db, bid):
    rows = await store._many(db, 'SELECT * FROM studio_units WHERE breakdown_id=? ORDER BY seq', (bid,))
    return await asyncio.to_thread(lambda: [_decode(row, {'characters_json': 'characters'}) for row in rows])


async def _episode_rows(db, bid, owner):
    return await store._many(db, 'SELECT * FROM studio_episodes WHERE breakdown_id=? AND owner=? ORDER BY no', (bid, owner))


def _range(units, show_offsets=True):
    if not units:
        return ''
    label = units[0]['label'] if len(units) == 1 else f"{units[0]['label']} – {units[-1]['label']}"
    if show_offsets and units[0].get('start') is not None and units[-1].get('end') is not None:
        label += f"（字符 {units[0]['start']}–{units[-1]['end']}）"
    return label


def _present_episodes(project, breakdown, episodes, units):
    result, included = [], set()
    show_offsets = project.get('source_kind') != 'novel'
    default_min, default_max = project['episode_seconds_min'], project['episode_seconds_max']
    for episode in episodes:
        selected = [unit for unit in units if episode['unit_from'] <= unit['seq'] <= episode['unit_to']]
        seconds = sum(unit.get('est_seconds') or 0 for unit in selected)
        minimum, maximum = episode.get('target_min') or default_min, episode.get('target_max') or default_max
        characters = list(dict.fromkeys(name for unit in selected for name in unit['characters']))
        warnings = []
        if seconds < minimum * .85 or seconds > maximum * 1.15:
            warnings.append(f'预估时长 {seconds} 秒超出目标 {minimum}–{maximum} 秒的 ±15%')
        result.append({**episode, 'est_seconds': seconds, 'est_shots': round(seconds / 3.5),
                       'source_range': _range(selected, show_offsets), 'characters': characters, 'warnings': warnings,
                       'effective_target_min': minimum, 'effective_target_max': maximum})
        included.update(unit['seq'] for unit in selected)
    unassigned = []
    for unit in units:
        if unit['seq'] in included:
            continue
        if not unassigned or unassigned[-1]['unit_to'] + 1 != unit['seq']:
            unassigned.append({'unit_from': unit['seq'], 'unit_to': unit['seq'], 'units': [unit]})
        else:
            unassigned[-1]['unit_to'] = unit['seq']
            unassigned[-1]['units'].append(unit)
    for item in unassigned:
        item['label'] = item['source_range'] = _range(item['units'], show_offsets)
    revision, approved = project['plan_revision'], project['plan_approved_revision']
    return {'episodes': result, 'units': units, 'unassigned': unassigned, 'uncovered': unassigned,
            'plan_revision': revision, 'plan_approved_revision': approved,
            'g0_approved': bool(result and revision > 0 and approved is not None and revision == approved),
            'total_seconds': sum(item['est_seconds'] for item in result),
            'status': breakdown['status'] if breakdown else None,
            'settings': {'episode_seconds_min': default_min, 'episode_seconds_max': default_max}}


async def get_episodes(pid, owner):
    async with store.connection() as db:
        await db.execute('BEGIN')
        project, active = await _current(db, pid, owner)
        project, breakdown = await _published(db, project, active)
        episodes = await _episode_rows(db, breakdown['id'], owner) if breakdown else []
        units = await _units(db, breakdown['id']) if breakdown else []
    result = await asyncio.to_thread(_present_episodes, project, breakdown, episodes, units)
    return _activity(result, breakdown, active)


def _validate(episodes, units, project):
    valid = {unit['seq'] for unit in units}
    previous = 0
    for episode in episodes:
        start, end = episode['unit_from'], episode['unit_to']
        if type(start) is not int or type(end) is not int or not start <= end or start <= previous:
            raise HTTPException(422, '分集范围必须按顺序、互不重叠且非空')
        if any(seq not in valid for seq in range(start, end + 1)):
            raise HTTPException(422, '分集范围超出场景单元')
        minimum = episode.get('target_min') or project['episode_seconds_min']
        maximum = episode.get('target_max') or project['episode_seconds_max']
        if not 60 <= minimum <= maximum <= 900:
            raise HTTPException(422, '单集目标时长须满足 60 ≤ 最短 ≤ 最长 ≤ 900 秒')
        previous = end


def _bible_appearances(rows, episodes, units):
    changes = []
    for row in rows:
        aliases = json.loads(row['aliases_json'])
        names = {_normal(name) for name in [row['name'], *aliases]}
        appeared = []
        for episode in episodes:
            for unit in units:
                if not episode['unit_from'] <= unit['seq'] <= episode['unit_to']:
                    continue
                names_in_unit = {_normal(name) for name in unit['characters']}
                match = bool(names & names_in_unit)
                if row['kind'] == 'location':
                    match = match or _normal(unit['location']) in names
                elif row['kind'] == 'prop':
                    match = match or row['first_unit'] == unit['seq'] or any(name and name in _normal(unit['summary']) for name in names)
                if match:
                    appeared.append(episode['no'])
                    break
        changes.append((store._json(appeared), store.utcnow(), row['id']))
    return changes


async def recompute_bible_episodes(db, bid):
    """已有事务内调用；总表别名或分集边界变化时一起更新计算列。"""
    rows = await store._many(db, 'SELECT * FROM studio_bible WHERE breakdown_id=? AND archived=0 AND merged_into IS NULL', (bid,))
    episodes = await store._many(db, 'SELECT * FROM studio_episodes WHERE breakdown_id=? ORDER BY no', (bid,))
    units = await _units(db, bid)
    changes = await asyncio.to_thread(_bible_appearances, rows, episodes, units)
    await db.executemany('UPDATE studio_bible SET episodes_json=?,updated_at=? WHERE id=?', changes)


async def _revision(db, project, episodes, reason):
    revision = project['plan_revision'] + 1
    now = store.utcnow()
    breakdown = await store._one(db, 'SELECT * FROM studio_breakdowns WHERE id=?', (project['breakdown_id'],))
    units = await _units(db, project['breakdown_id'])
    def snapshot():
        value = _present_episodes({**project, 'plan_revision': revision}, breakdown, episodes, units)
        value.update(project_id=project['id'], breakdown_id=project['breakdown_id'], snapshot_no=breakdown['snapshot_no'])
        return store._json(value)
    plan_json = await asyncio.to_thread(snapshot)
    await db.execute('UPDATE studio_projects SET plan_revision=?,updated_at=? WHERE id=? AND owner=?',
                     (revision, now, project['id'], project['owner']))
    await db.execute('''INSERT INTO studio_plan_revisions(project_id,owner,revision,plan_json,created_at,created_reason)
        VALUES(?,?,?,?,?,?)''', (project['id'], project['owner'], revision, plan_json, now, reason))


async def publish_plan(db, bid, episodes, reason='generated'):
    """流水线在其写事务中发布完整/部分结果，调用方负责避免重复发布。"""
    breakdown = await store._one(db, 'SELECT * FROM studio_breakdowns WHERE id=?', (bid,))
    if breakdown is None:
        raise HTTPException(404, 'Not Found')
    project = await store._project(db, breakdown['project_id'], breakdown['owner'])
    units = await _units(db, bid)
    normalized = []
    for no, episode in enumerate(episodes, 1):
        normalized.append({'id': str(uuid.uuid4()), 'project_id': project['id'], 'owner': project['owner'],
                           'breakdown_id': bid, 'no': no, 'title': episode.get('title', f'第 {no} 集'),
                           'unit_from': episode['unit_from'], 'unit_to': episode['unit_to'],
                           'change': episode.get('change', ''), 'hook': episode.get('hook', ''),
                           'target_min': episode.get('target_min'), 'target_max': episode.get('target_max'),
                           'notes': episode.get('notes', ''), 'updated_at': store.utcnow()})
    await asyncio.to_thread(_validate, normalized, units, project)
    await db.execute('DELETE FROM studio_episodes WHERE breakdown_id=?', (bid,))
    await _write_episodes(db, normalized)
    # A previous partial run may finish after the author starts a newer run.
    # Keep its own result without taking over the selected plan or its revision.
    if project.get('breakdown_id') == bid:
        await _revision(db, project, normalized, reason)
    await recompute_bible_episodes(db, bid)


async def _write_episodes(db, episodes):
    columns = ('id', 'project_id', 'owner', 'breakdown_id', 'no', 'title', 'unit_from', 'unit_to', 'change', 'hook',
               'target_min', 'target_max', 'notes', 'updated_at')
    await db.executemany(f"INSERT INTO studio_episodes({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                         [tuple(episode[column] for column in columns) for episode in episodes])


def _combine(first, second):
    return '；'.join(value for value in (first, second) if value)


def _operate(episodes, units, project, data):
    op = data['op']
    no = data.get('no')
    index = next((i for i, episode in enumerate(episodes) if episode['no'] == no), None)
    if op != 'insert' and index is None:
        raise HTTPException(404, '分集不存在')
    episode = episodes[index] if index is not None else None
    allowed = {'title', 'change', 'hook', 'notes', 'target_min', 'target_max'}
    if op == 'edit':
        fields = data.get('fields')
        flat = {key: data[key] for key in allowed if key in data}
        if fields is not None and flat:
            raise HTTPException(422, '请只使用一种分集字段格式')
        fields = fields if fields is not None else flat
        if not fields or set(fields) - allowed:
            raise HTTPException(422, '没有可修改的分集字段')
        if any(fields.get(key) is None for key in ('title', 'change', 'hook', 'notes') if key in fields):
            raise HTTPException(422, '分集文字字段不能为 null')
        if 'title' in fields and not fields['title'].strip():
            raise HTTPException(422, '分集标题不能为空')
        episode.update(fields)
    elif op == 'merge':
        if index + 1 >= len(episodes):
            raise HTTPException(422, '没有下一集可合并')
        following = episodes.pop(index + 1)
        episode['unit_to'] = following['unit_to']
        for key in ('title', 'change', 'hook', 'notes'):
            episode[key] = _combine(episode[key], following[key])
    elif op == 'split':
        at = data.get('at_unit')
        if type(at) is not int or not episode['unit_from'] < at <= episode['unit_to']:
            raise HTTPException(422, '拆分点必须在本集第一场之后')
        new = {**episode, 'id': str(uuid.uuid4()), 'title': f"{episode['title']}（下）", 'unit_from': at}
        episode['unit_to'] = at - 1
        episodes.insert(index + 1, new)
    elif op == 'move_boundary':
        if index + 1 >= len(episodes) or data.get('delta') not in (-1, 1):
            raise HTTPException(422, '边界只能向前或向后移动一场')
        following = episodes[index + 1]
        if episode['unit_to'] + 1 != following['unit_from']:
            raise HTTPException(422, '只能移动相邻且连续两集的边界')
        boundary = episode['unit_to'] + data['delta']
        if boundary < episode['unit_from'] or boundary >= following['unit_to']:
            raise HTTPException(422, '移动边界不能让任何一集变空')
        episode['unit_to'], following['unit_from'] = boundary, boundary + 1
    elif op == 'delete':
        episodes.pop(index)
    elif op == 'insert':
        start, end = data.get('unit_from'), data.get('unit_to')
        if type(start) is not int or type(end) is not int:
            raise HTTPException(422, '请填写未纳入的单元范围')
        if any(not (end < item['unit_from'] or start > item['unit_to']) for item in episodes):
            raise HTTPException(422, '只能将未纳入的单元建成新集')
        episodes.append({'id': str(uuid.uuid4()), 'project_id': project['id'], 'owner': project['owner'],
                         'breakdown_id': project['breakdown_id'], 'no': 0, 'title': data.get('title') or '新的一集',
                         'unit_from': start, 'unit_to': end, 'change': data.get('change') or '',
                         'hook': data.get('hook') or '', 'target_min': data.get('target_min'),
                         'target_max': data.get('target_max'), 'notes': data.get('notes') or '', 'updated_at': store.utcnow()})
        episodes.sort(key=lambda item: item['unit_from'])
    else:
        raise HTTPException(422, '未知分集操作')
    for no, item in enumerate(episodes, 1):
        item['no'], item['updated_at'] = no, store.utcnow()
    _validate(episodes, units, project)
    return episodes


async def operate_episodes(pid, owner, data):
    async with store.connection(transaction=True) as db:
        project, active = await _current(db, pid, owner)
        if data['expected_revision'] != project['plan_revision']:
            raise HTTPException(409, '分集方案已更新，请刷新')
        if active and active['status'] in {'running', 'partial'}:
            raise HTTPException(409, '拆解尚未完成，完成后才能修改分集方案')
        project, breakdown = await _published(db, project, active)
        if breakdown is None:
            raise HTTPException(409, '请先完成拆解')
        episodes = await _episode_rows(db, breakdown['id'], owner)
        units = await _units(db, breakdown['id'])
        episodes = await asyncio.to_thread(_operate, episodes, units, project, data)
        await db.execute('DELETE FROM studio_episodes WHERE breakdown_id=? AND owner=?', (breakdown['id'], owner))
        await _write_episodes(db, episodes)
        await _revision(db, project, episodes, data['op'])
        await recompute_bible_episodes(db, breakdown['id'])
    return await get_episodes(pid, owner)


async def approve(pid, owner, expected_revision):
    async with store.connection(transaction=True) as db:
        project, active = await _current(db, pid, owner)
        if expected_revision != project['plan_revision']:
            raise HTTPException(409, '分集方案已更新，请刷新')
        if active and active['status'] in {'running', 'partial'}:
            raise HTTPException(409, '拆解尚未全部完成，不能批准分集方案')
        project, breakdown = await _published(db, project, active)
        if breakdown is None or breakdown['status'] != 'done':
            raise HTTPException(409, '拆解尚未全部完成，不能批准分集方案')
        if project['plan_revision'] < 1 or not await _episode_rows(db, breakdown['id'], owner):
            raise HTTPException(409, '至少需要一集才能批准')
        await db.execute('UPDATE studio_projects SET plan_approved_revision=?,updated_at=? WHERE id=? AND owner=?',
                         (project['plan_revision'], store.utcnow(), pid, owner))
    return await get_episodes(pid, owner)


async def patch_project(pid, owner, fields):
    async with store.connection(transaction=True) as db:
        project = await store._project(db, pid, owner)
        if not fields:
            raise HTTPException(422, '请填写需要修改的项目字段')
        minimum = fields.get('episode_seconds_min', project['episode_seconds_min'])
        maximum = fields.get('episode_seconds_max', project['episode_seconds_max'])
        if not 60 <= minimum <= maximum <= 900:
            raise HTTPException(422, '每集时长须满足 60 ≤ 最短 ≤ 最长 ≤ 900 秒')
        if fields.get('brain_provider'):
            if fields['brain_provider'] not in {'claude', 'qwen', 'deepseek'}:
                raise HTTPException(422, '导演模型必须为 claude、qwen 或 deepseek')
        target_project, target_bid = project, project.get('breakdown_id')
        has_duration = bool({'episode_seconds_min', 'episode_seconds_max'} & set(fields))
        if has_duration and project.get('breakdown_id'):
            active = await _breakdown(db, project['breakdown_id'], owner)
            if active['status'] == 'cancelled':
                published_project, published = await _published(db, project, active)
                if published:
                    target_project, target_bid = published_project, published['id']
        changed_defaults = {target for setting, target in (
            ('episode_seconds_min', 'target_min'), ('episode_seconds_max', 'target_max'))
            if setting in fields and fields[setting] != target_project[setting]}
        episodes = await _episode_rows(db, target_bid, owner) if target_bid and changed_defaults else []
        affects_plan = any(episode.get(target) is None for episode in episodes for target in changed_defaults)
        if affects_plan:
            units = await _units(db, target_bid)
            await asyncio.to_thread(_validate, episodes, units, {**target_project, **fields})
        assignments = ','.join(f'{key}=?' for key in fields)
        await db.execute(f'UPDATE studio_projects SET {assignments},updated_at=? WHERE id=? AND owner=?',
                         (*fields.values(), store.utcnow(), pid, owner))
        updated = await store._project(db, pid, owner)
        if affects_plan:
            effective = {**updated, 'breakdown_id': target_bid,
                         'episode_seconds_min': target_project['episode_seconds_min'],
                         'episode_seconds_max': target_project['episode_seconds_max'], **fields}
            await _revision(db, effective, episodes, 'settings')
            await recompute_bible_episodes(db, target_bid)
            updated = await store._project(db, pid, owner)
        return updated


async def patch_synopsis(pid, owner, synopsis):
    serialized = await asyncio.to_thread(store._json, synopsis)
    if len(serialized) > 100_000:
        raise HTTPException(422, '梗概不能超过 10 万字')
    async with store.connection(transaction=True) as db:
        project, breakdown = await _current(db, pid, owner)
        if breakdown is None:
            raise HTTPException(404, '项目还没有拆解')
        current = await asyncio.to_thread(json.loads, breakdown.get('synopsis_json') or '{}')
        allowed = {'logline', 'theme', 'core_conflict', 'main_threads', 'arc_summaries'} if project['source_kind'] == 'novel' else {
            'logline', 'synopsis', 'genre', 'tone', 'themes'}
        allowed.update(current)
        if set(synopsis) - allowed:
            raise HTTPException(422, '梗概包含未知字段')
        if any(key in current and type(value) is not type(current[key]) for key, value in synopsis.items()):
            raise HTTPException(422, '梗概字段类型必须保持不变')
        synopsis = {**current, **synopsis}
        serialized = await asyncio.to_thread(store._json, synopsis)
        if len(serialized) > 100_000:
            raise HTTPException(422, '梗概不能超过 10 万字')
        await db.execute('UPDATE studio_breakdowns SET synopsis_json=?,updated_at=? WHERE id=? AND owner=?',
                         (serialized, store.utcnow(), breakdown['id'], owner))
    return {'synopsis': synopsis}


async def list_bible(pid, owner, kind=None):
    async with store.connection() as db:
        await db.execute('BEGIN')
        _, breakdown = await _current(db, pid, owner)
        if not breakdown:
            return []
        rows = await store._many(db, '''SELECT b.*,u.label AS first_appearance FROM studio_bible b
            LEFT JOIN studio_units u ON u.breakdown_id=b.breakdown_id AND u.seq=b.first_unit
            WHERE b.breakdown_id=? AND b.owner=? AND b.archived=0 AND b.merged_into IS NULL
            AND (? IS NULL OR b.kind=?) ORDER BY b.kind,COALESCE(b.first_unit,2147483647),b.name,b.id''',
                                (breakdown['id'], owner, kind, kind))
    return await asyncio.to_thread(lambda: [_decode(row, {'aliases_json': 'aliases', 'episodes_json': 'episodes'}) for row in rows])


async def _bible_item(db, item_id, owner):
    item = await store._one(db, '''SELECT * FROM studio_bible
        WHERE id=? AND owner=? AND archived=0 AND merged_into IS NULL''', (item_id, owner))
    if item is None:
        raise HTTPException(404, 'Not Found')
    await store._project(db, item['project_id'], owner)
    return item


async def _record_bible_edits(db, bid, owner, item_id, edited_fields):
    breakdown = await _breakdown(db, bid, owner)
    def record():
        imported = json.loads(breakdown.get('import_json') or '{}')
        edits = imported.setdefault('_bible_author_edits', {})
        edits[item_id] = sorted(set(edits.get(item_id, [])) | set(edited_fields))
        return store._json(imported)
    await db.execute('UPDATE studio_breakdowns SET import_json=?,updated_at=? WHERE id=? AND owner=?',
                     (await asyncio.to_thread(record), store.utcnow(), bid, owner))


async def patch_bible(item_id, owner, fields):
    async with store.connection(transaction=True) as db:
        item = await _bible_item(db, item_id, owner)
        if not fields:
            raise HTTPException(422, '请填写需要修改的总表字段')
        fields = dict(fields)
        edited_fields = set(fields)
        if 'name' in fields and fields['name'] != item['name']:
            aliases = fields.get('aliases', json.loads(item['aliases_json']))
            fields['aliases'] = list(dict.fromkeys([*aliases, item['name']]))
            edited_fields.add('aliases')
        if 'appearance' in fields:
            fields.update(appearance_source='author' if fields['appearance'].strip() else 'none',
                          needs_author=int(item['kind'] == 'character' and not fields['appearance'].strip()))
            edited_fields.update(('appearance_source', 'needs_author'))
        if 'aliases' in fields:
            fields['aliases_json'] = await asyncio.to_thread(store._json, list(dict.fromkeys(fields.pop('aliases'))))
        assignments = ','.join(f'{key}=?' for key in fields)
        await db.execute(f'UPDATE studio_bible SET {assignments},updated_at=? WHERE id=? AND owner=?',
                         (*fields.values(), store.utcnow(), item_id, owner))
        await _record_bible_edits(db, item['breakdown_id'], owner, item_id, edited_fields)
        await recompute_bible_episodes(db, item['breakdown_id'])
        row = await _bible_item(db, item_id, owner)
    return _decode(row, {'aliases_json': 'aliases', 'episodes_json': 'episodes'})


async def create_bible(owner, data):
    async with store.connection(transaction=True) as db:
        project, breakdown = await _current(db, data['project_id'], owner)
        if breakdown is None:
            raise HTTPException(409, '请先完成拆解')
        item_id = str(uuid.uuid4())
        appearance = data.get('appearance', '')
        await db.execute('''INSERT INTO studio_bible(id,project_id,owner,breakdown_id,kind,name,aliases_json,role,
            description,appearance,appearance_source,needs_author,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (item_id, project['id'], owner, breakdown['id'], data['kind'], data['name'],
                          store._json(data.get('aliases', [])), data.get('role', ''), data.get('description', ''),
                          appearance, 'author' if appearance else 'none',
                          0 if appearance else int(data.get('needs_author', data['kind'] == 'character')), store.utcnow()))
        await recompute_bible_episodes(db, breakdown['id'])
        row = await _bible_item(db, item_id, owner)
    return _decode(row, {'aliases_json': 'aliases', 'episodes_json': 'episodes'})


async def archive_bible(item_id, owner):
    async with store.connection(transaction=True) as db:
        await _bible_item(db, item_id, owner)
        await db.execute('UPDATE studio_bible SET archived=1,updated_at=? WHERE id=? AND owner=?',
                         (store.utcnow(), item_id, owner))
    return {'archived': True}


async def merge_bible(owner, keep_id, merge_ids):
    if not merge_ids or keep_id in merge_ids or len(set(merge_ids)) != len(merge_ids):
        raise HTTPException(422, '请选定不同的总表条目')
    async with store.connection(transaction=True) as db:
        keep = await _bible_item(db, keep_id, owner)
        others = [await _bible_item(db, item_id, owner) for item_id in merge_ids]
        if any((item['project_id'], item['breakdown_id'], item['kind']) !=
               (keep['project_id'], keep['breakdown_id'], keep['kind']) for item in others):
            raise HTTPException(422, '只能合并同一拆解、同一类别的条目')
        aliases = json.loads(keep['aliases_json'])
        for item in others:
            aliases.extend([item['name'], *json.loads(item['aliases_json'])])
        aliases = list(dict.fromkeys(alias for alias in aliases if alias != keep['name']))
        first_units = [item['first_unit'] for item in [keep, *others] if item['first_unit'] is not None]
        appearance_item = next((item for item in [keep, *others] if item['appearance']), keep)
        excerpt = next((item['excerpt'] for item in [keep, *others] if item['excerpt']), '')
        needs_author = 0 if appearance_item['appearance'] else keep['needs_author']
        edited_fields = {'aliases', 'first_unit'}
        merged_fields = {'appearance': appearance_item['appearance'],
                         'appearance_source': appearance_item['appearance_source'], 'needs_author': needs_author}
        edited_fields.update(field for field, value in merged_fields.items() if value != keep[field])
        await db.execute('''UPDATE studio_bible SET aliases_json=?,first_unit=?,appearance=?,appearance_source=?,
            excerpt=?,needs_author=?,updated_at=? WHERE id=? AND owner=?''',
                         (store._json(aliases), min(first_units) if first_units else None, appearance_item['appearance'],
                          appearance_item['appearance_source'], excerpt,
                          needs_author, store.utcnow(), keep_id, owner))
        await db.executemany('UPDATE studio_bible SET merged_into=?,updated_at=? WHERE id=? AND owner=?',
                             [(keep_id, store.utcnow(), item['id'], owner) for item in others])
        await _record_bible_edits(db, keep['breakdown_id'], owner, keep_id, edited_fields)
        await recompute_bible_episodes(db, keep['breakdown_id'])
        row = await _bible_item(db, keep_id, owner)
    return _decode(row, {'aliases_json': 'aliases', 'episodes_json': 'episodes'})


def _inline(value):
    text = html.escape(' '.join(str(value if value is not None else '').split()), quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|])', r'\\\1', text)


def _role_label(role):
    return {'main': '主要人物', 'supporting': '配角', 'major': '重要', 'minor': '次要'}.get(role, role)


def _episode_ranges(nos):
    numbers = sorted({no for no in nos if type(no) is int and no > 0})
    if not numbers:
        return '未纳入'
    ranges, first, last = [], numbers[0], numbers[0]
    for no in numbers[1:]:
        if no == last + 1:
            last = no
            continue
        ranges.append(str(first) if first == last else f'{first}–{last}')
        first = last = no
    ranges.append(str(first) if first == last else f'{first}–{last}')
    return '第 ' + '、'.join(ranges) + ' 集'


def _table(headers, rows):
    return ['| ' + ' | '.join(_inline(value) for value in headers) + ' |',
            '| ' + ' | '.join('---' for _ in headers) + ' |',
            *['| ' + ' | '.join(_inline(value) for value in row) + ' |' for row in rows]]


def _readable(value, field=None):
    if isinstance(value, list):
        return '、'.join(_readable(item, field) for item in value)
    if isinstance(value, dict):
        if field == 'main_threads':
            name = value.get('name') or value.get('title') or ''
            description = value.get('description') or value.get('summary') or ''
            return ' —— '.join(_readable(item) for item in (name, description) if item)
        if field == 'arc_summaries':
            first = next((value[key] for key in ('from', 'start_chapter', 'from_chapter') if value.get(key) is not None), None)
            last = next((value[key] for key in ('to', 'end_chapter', 'to_chapter') if value.get(key) is not None), None)
            summary = value.get('summary') or value.get('description') or ''
            if first is not None and last is not None:
                return f'第 {_readable(first)}–{_readable(last)} 章：{_readable(summary)}'
            return _readable(summary)
        return '；'.join(f'{_FIELD_LABELS.get(key, key)}：{_readable(item, key)}'
                        for key, item in value.items() if not str(key).startswith('_'))
    return str(value if value is not None else '')


def _prose(value):
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if str(key).startswith('_'):
                continue
            if key == 'compass' and isinstance(item, dict):
                lines.extend(_prose(item))
            elif isinstance(item, list) and key != 'themes':
                lines.append(f'- {_inline(_FIELD_LABELS.get(key, key))}：')
                lines.extend(f'  - {_inline(_readable(entry, key))}' for entry in item)
            else:
                lines.append(f'- {_inline(_FIELD_LABELS.get(key, key))}：{_inline(_readable(item, key))}')
        return lines
    if isinstance(value, list):
        return [f'- {_inline(_readable(item))}' for item in value]
    return [_inline(value)]


def _render_export(project, breakdown, bible, plan):
    approved = '已批准' if plan['g0_approved'] else '待批准'
    lines = [f"# {_inline(project['title'])} · 拆解与分集", '',
             f"作品：{_inline(project['title'])}；快照第 {breakdown['snapshot_no']} 版；模型：{_inline(_PROVIDER_LABELS.get(breakdown['provider'], breakdown['provider']))}；",
             f"方案第 {plan['plan_revision']} 版 · {approved}", '', '## 梗概', '']
    lines.extend(_prose(json.loads(breakdown.get('synopsis_json') or '{}')))
    for kind, title in [('character', '人物总表'), ('location', '场景总表'), ('prop', '道具总表')]:
        lines.extend(['', f'## {title}', ''])
        lines.extend(_table(['名字（别名）', '定位', '外形或描述', '原文摘录', '首次出场', '出场的集'],
                            [[item['name'] + (f"（{'、'.join(item['aliases'])}）" if item['aliases'] else ''), _role_label(item['role']),
                              (item['appearance'] or item['description']) + ('（待作者补充）' if item['needs_author'] else ''),
                              item['excerpt'], item.get('first_appearance') or '', _episode_ranges(item['episodes'])]
                             for item in bible if item['kind'] == kind]))
    lines.extend(['', '## 分集方案', ''])
    lines.extend(_table(['集号', '标题', '原文范围', '这集发生的变化', '终点 / 钩子', '预估镜头数', '预估时长', '出场人物'],
                        [[item['no'], item['title'], item['source_range'], item['change'], item['hook'], item['est_shots'],
                          f"{item['est_seconds']} 秒", '、'.join(item['characters'])] for item in plan['episodes']]))
    lines.extend(['', '## 未纳入的单元', ''])
    lines.extend([f"- {_inline(item['source_range'])}" for item in plan['unassigned']] or ['无'])
    imported = json.loads(breakdown.get('import_json') or '{}')
    for key, title in [('foreshadowing', '伏笔'), ('timeline', '时间线')]:
        if key in imported:
            lines.extend(['', f'## {title}', '', *_prose(imported[key])])
    return '\n'.join(lines) + '\n'


async def export_markdown(pid, owner):
    async with store.connection() as db:
        await db.execute('BEGIN')
        project, active = await _current(db, pid, owner)
        project, breakdown = await _published(db, project, active)
        if breakdown is None:
            raise HTTPException(404, '项目还没有拆解')
        episodes = await _episode_rows(db, breakdown['id'], owner)
        units = await _units(db, breakdown['id'])
        rows = await store._many(db, '''SELECT b.*,u.label AS first_appearance FROM studio_bible b
            LEFT JOIN studio_units u ON u.breakdown_id=b.breakdown_id AND u.seq=b.first_unit
            WHERE b.breakdown_id=? AND b.owner=? AND b.archived=0 AND b.merged_into IS NULL ORDER BY b.kind,b.first_unit,b.name''',
                                (breakdown['id'], owner))
    def render():
        bible = [_decode(row, {'aliases_json': 'aliases', 'episodes_json': 'episodes'}) for row in rows]
        plan = _present_episodes(project, breakdown, episodes, units)
        return _render_export(project, breakdown, bible, plan)
    return project['title'], await asyncio.to_thread(render)
