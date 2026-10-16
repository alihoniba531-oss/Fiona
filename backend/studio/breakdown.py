"""WO3c 快照拆解：确认一次、全批预留、显式依赖与确定性发布。"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import hashlib
import json
import logging
import uuid

from fastapi import HTTPException

from . import brain_jobs, pricing, sources, spend, store
from .breakdown_material import batch_plan, locate_scenes, merge_bible, normalize_name, structured_import

RETRYABLE = {'failed', 'rejected', 'invalid_output', 'released'}
ACTIVE = {'queued', 'blocked', 'running'}
logger = logging.getLogger(__name__)


async def _json(value):
    from database import WatchPrivateText
    return WatchPrivateText(await asyncio.to_thread(store._json, value))


def _decode(row):
    if row is None:
        return None
    row = store._row(row)
    for key, field, default in (('source_json', 'source', {}), ('depends_on_json', 'depends_on', []),
                                 ('settings_json', 'settings', {}), ('import_json', 'imported', {}),
                                 ('synopsis_json', 'synopsis', {})):
        if key in row:
            row[field] = json.loads(row[key]) if row[key] else default
    return row


async def decode_job_row(row):
    return await asyncio.to_thread(store._row, row)


async def _one(db, sql, params=()):
    """Decode this module's potentially large JSON rows in one worker hop."""
    async with db.execute(sql, params) as cursor:
        row = await cursor.fetchone()
    return await asyncio.to_thread(_decode, row)


async def _many(db, sql, params=()):
    async with db.execute(sql, params) as cursor:
        rows = await cursor.fetchall()
    return await asyncio.to_thread(lambda: [_decode(row) for row in rows])


async def _job(db, jid, owner=None):
    return await _one(db, 'SELECT * FROM studio_jobs WHERE id=?' + (' AND owner=?' if owner else ''),
                      (jid, owner) if owner else (jid,))


async def _breakdown(db, bid, owner):
    row = await _one(db, 'SELECT * FROM studio_breakdowns WHERE id=? AND owner=?', (bid, owner))
    if row is None:
        raise HTTPException(404, 'Not Found')
    await store._project(db, row['project_id'], owner)
    return row


async def _chunks(db, bid):
    rows = await _many(db, 'SELECT * FROM studio_chunks WHERE breakdown_id=? ORDER BY no', (bid,))
    return rows


async def _snapshot(pid, owner):
    project, row = await sources._current_snapshot(owner, pid)
    if row is None:
        raise HTTPException(409, '先关联作品才能拆解')
    manifest = await asyncio.to_thread(sources._read_manifest, row)
    entries = await sources.read_snapshot(owner, pid, 1, len(manifest['chapters']))
    return project, row, manifest, entries


def _make_quote(project, snapshot, manifest, entries, option, target):
    imported, plan = batch_plan(manifest, entries)
    if target and manifest['kind'] == 'novel':
        all_maps = [chunk['no'] for chunk in plan if chunk['task'] == 'novel_complete']
        for chunk in plan:
            if chunk['task'] == 'episode_plan':
                chunk['depends'] = list(dict.fromkeys([*chunk['depends'], *all_maps]))
    items = []
    for chunk in plan:
        inputs = chunk['inputs']
        if not inputs:
            # Future model output is unknown; reserve 400 chars per estimated unit.
            count = chunk['estimate_units'] if chunk['task'] == 'episode_plan' else len(entries)
            inputs = {'estimated_material': '字' * (count * 400), 'target_min': project.get('episode_seconds_min', 180),
                      'target_max': project.get('episode_seconds_max', 240)}
        item = brain_jobs._quote_item(option['id'], option['model'], chunk['task'], inputs)
        chunk['item'] = item
        chunk.pop('inputs', None)
        items.append(item)
    return {'kind': 'breakdown', 'snapshot_no': snapshot['no'], 'provider': option['id'],
            'settings': {'episode_seconds_min': project.get('episode_seconds_min', 180),
                         'episode_seconds_max': project.get('episode_seconds_max', 240), 'target_episodes': target},
            'plan': plan, 'items': items}


def _public_quote(row, payload):
    items = payload['items']
    totals = brain_jobs._totals(items)
    currency = items[0]['currency']
    return {'id': row['id'], 'quote_id': row['id'], 'provider': payload['provider'], 'expires_at': row['expires_at'],
            'total_min': float(sum(pricing.money(item['first_max']) for item in items)),
            'total_max': totals[currency], 'currency': currency, 'total_chunks': len(items),
            'task_counts': {task: sum(item['task'] == task for item in items)
                            for task in ('novel_complete', 'text_map', 'synopsis', 'episode_plan')},
            'items': items, 'totals': totals, 'settings': payload.get('settings')}


async def _write_quote(db, pid, owner, payload):
    qid, stamp = str(uuid.uuid4()), store.utcnow()
    expires = (store.parse_time(stamp) + timedelta(minutes=15)).isoformat()
    encoded = await _json(payload)
    totals = brain_jobs._totals(payload['items'])
    await db.execute('''INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,total_max_cny,
        params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'open',?,?)''',
        (qid, pid, owner, encoded, '0', str(pricing.money(totals['CNY'])),
         await asyncio.to_thread(lambda: hashlib.sha256(encoded.encode()).hexdigest()), stamp, expires))
    return _public_quote({'id': qid, 'expires_at': expires}, payload)


async def _option(provider, owner):
    from .brain import provider_options
    if provider not in brain_jobs.PROVIDERS:
        raise HTTPException(422, '导演模型必须为 claude、qwen 或 deepseek')
    option = next(item for item in await provider_options(owner) if item['id'] == provider)
    if not option['available']:
        raise HTTPException(409, option.get('reason', '导演模型不可用'))
    return option


async def quote(pid, owner, target_episodes=None, episode_seconds_min=None, episode_seconds_max=None):
    if target_episodes is not None and (type(target_episodes) is not int or not 1 <= target_episodes <= 300):
        raise HTTPException(422, '大约集数须为 1–300 的整数')
    project, snapshot, manifest, entries = await _snapshot(pid, owner)
    minimum = project['episode_seconds_min'] if episode_seconds_min is None else episode_seconds_min
    maximum = project['episode_seconds_max'] if episode_seconds_max is None else episode_seconds_max
    if type(minimum) is not int or type(maximum) is not int or not 60 <= minimum <= maximum <= 900:
        raise HTTPException(422, '每集目标时长须为 60–900 秒，最短不能大于最长')
    project = {**project, 'episode_seconds_min': minimum, 'episode_seconds_max': maximum}
    option = await _option(project['brain_provider'], owner)
    payload = await asyncio.to_thread(_make_quote, project, snapshot, manifest, entries, option, target_episodes)
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await spend.check_brain_budget(db, owner, brain_jobs._totals(payload['items']))
        return await _write_quote(db, pid, owner, payload)


async def _confirmed_quote(db, qid, pid, owner, kind):
    row = await _one(db, 'SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?', (qid, pid, owner))
    if row is None:
        raise HTTPException(404, 'Not Found')
    payload = row['items']
    if not isinstance(payload, dict) or payload.get('kind') != kind:
        raise HTTPException(409, '报价用途不匹配')
    if row['status'] != 'open':
        raise HTTPException(409, '报价只能确认一次')
    if store.parse_time(row['expires_at']) <= store.parse_time(store.utcnow()):
        raise HTTPException(409, '报价已过期，请重新报价')
    await spend.check_brain_budget(db, owner, brain_jobs._totals(payload['items']))
    await db.execute("UPDATE studio_quotes SET status='confirmed',confirmed_at=? WHERE id=? AND status='open'",
                     (store.utcnow(), qid))
    return payload


async def _new_chunk_job(db, bid, cid, pid, owner, item, inputs, qid):
    # Reserve the authorized correction as well as the first call from confirmation.
    reserved = {**item, 'first_max': item['amount']}
    return await brain_jobs._insert_job(db, pid, owner, reserved, inputs, bid, quote_id=qid, chunk_id=cid)


async def _insert_units(db, bid, units):
    await db.execute('DELETE FROM studio_units WHERE breakdown_id=?', (bid,))
    rows = await asyncio.to_thread(lambda: [(bid, unit['seq'], unit['label'], unit['chapter'], unit['scene_index'],
         unit.get('location', ''), unit.get('summary', ''), store._json(unit.get('characters', [])),
         unit.get('est_seconds'), unit.get('change', ''), unit.get('start'), unit.get('end')) for unit in units])
    await db.executemany('''INSERT INTO studio_units(breakdown_id,seq,label,chapter,scene_index,location,summary,
        characters_json,est_seconds,change,start,end) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', rows)


async def _locked_snapshot(pid, owner, snapshot_no, *, indices=None):
    async with store.connection() as db:
        await store._project(db, pid, owner)
        row = await _one(db, 'SELECT * FROM studio_snapshots WHERE project_id=? AND owner=? AND no=?',
                         (pid, owner, snapshot_no))
    if row is None:
        raise HTTPException(404, '作品快照不存在')
    manifest = await asyncio.to_thread(sources._read_manifest, row)
    first, last = (min(indices), max(indices)) if indices else (1, len(manifest['chapters']))
    entries = await sources.read_snapshot_at(owner, pid, snapshot_no, first, last)
    return manifest, entries


async def _cancel_unexecuted(db, breakdown, owner):
    for chunk in await _chunks(db, breakdown['id']):
        job = await _job(db, chunk['job_id'], owner)
        if chunk['status'] in {'queued', 'blocked'} and job and job['status'] == 'queued':
            await brain_jobs.transition(db, job, 'queued', {'status': 'cancelled'})
            await db.execute("UPDATE studio_chunks SET status='cancelled',updated_at=? WHERE id=?",
                             (store.utcnow(), chunk['id']))
    # 已完成的旧拆解只是被替代，事实仍是完成；只有 running/partial 这类
    # 确实有未执行批的旧拆解才写 cancelled。
    if breakdown['status'] not in {'cancelled', 'done'}:
        await db.execute("UPDATE studio_breakdowns SET status='cancelled',updated_at=? WHERE id=?",
                         (store.utcnow(), breakdown['id']))


def _retired(breakdown):
    """这次拆解已被取消，或已被新拆解替代：不再执行批次、物化、调度或发布方案。"""
    return breakdown['status'] == 'cancelled' or bool(breakdown.get('superseded_by'))


async def start(pid, owner, quote_id):
    scheduled = []
    async with store.connection(transaction=True) as db:
        project = await store._project(db, pid, owner)
        old = await _breakdown(db, project['breakdown_id'], owner) if project.get('breakdown_id') else None
        if old:
            # Inspect every paid attempt, including repair parents, before touching
            # either the quotation or the old breakdown's reservations.
            unresolved = await _one(db, "SELECT id FROM studio_jobs WHERE group_id=? AND owner=? AND status='uncertain' LIMIT 1",
                                     (old['id'], owner))
            if unresolved:
                raise HTTPException(409, '上一次拆解还有结果不确定的批次，请先核账释放后再重新拆解')
            active = await _one(db, "SELECT id FROM studio_jobs WHERE group_id=? AND owner=? AND status IN ('running','submitting') LIMIT 1",
                               (old['id'], owner))
            if active:
                raise HTTPException(409, '拆解正在进行中')
        raw_quote = await _one(db, 'SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?', (quote_id, pid, owner))
        if raw_quote is None:
            raise HTTPException(404, 'Not Found')
        preview = raw_quote['items']
        if not isinstance(preview, dict) or preview.get('kind') != 'breakdown':
            raise HTTPException(409, '报价用途不匹配')
        if project['snapshot_no'] != preview['snapshot_no']:
            raise HTTPException(409, '作品快照已更新，请重新报价')
        manifest, entries = await _locked_snapshot(pid, owner, preview['snapshot_no'])
        imported = await asyncio.to_thread(structured_import, manifest) if manifest['kind'] == 'novel' else {
            'characters': [], 'units': [], 'synopsis': {}}
        imported['_manifest'] = manifest
        if old:
            await _cancel_unexecuted(db, old, owner)
        payload = await _confirmed_quote(db, quote_id, pid, owner, 'breakdown')
        bid, stamp = str(uuid.uuid4()), store.utcnow()
        await db.execute('''INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,
            settings_json,import_json,synopsis_json,quote_id,outdated,created_at,updated_at)
            VALUES(?,?,?,?,?,'running',?,?,?,?,0,?,?)''',
            (bid, pid, owner, payload['snapshot_no'], payload['provider'], await _json(payload['settings']),
             await _json(imported), await _json(imported.get('synopsis', {})), quote_id, stamp, stamp))
        if old:
            # 不论旧拆解之前是什么状态，都记下它被哪一次新拆解替代。
            await db.execute('UPDATE studio_breakdowns SET superseded_by=?,updated_at=? WHERE id=?',
                             (bid, stamp, old['id']))
        ids = {chunk['no']: str(uuid.uuid4()) for chunk in payload['plan']}
        for chunk in payload['plan']:
            cid, blocked = ids[chunk['no']], bool(chunk['depends'])
            source = {**chunk['source'], '_item': chunk['item']}
            # Queued ledger rows reserve every batch; source material is read only
            # when that batch actually reaches execution.
            job = await _new_chunk_job(db, bid, cid, pid, owner, chunk['item'], {}, quote_id)
            await db.execute('''INSERT INTO studio_chunks(id,breakdown_id,project_id,owner,no,task,source_json,
                depends_on_json,status,job_id,provider,result_json,warnings_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,'[]',?,?)''',
                (cid, bid, pid, owner, chunk['no'], chunk['task'], await _json(source),
                 await _json([ids[no] for no in chunk['depends']]), 'blocked' if blocked else 'queued',
                 job['id'], payload['provider'], stamp, stamp))
            if not blocked:
                scheduled.append(job['id'])
        await _insert_units(db, bid, imported.get('units', []))
        initial_bible, _ = await asyncio.to_thread(merge_bible, imported, [], imported.get('units', []))
        await _insert_bible(db, {'id': bid, 'project_id': pid, 'owner': owner, 'imported': imported}, initial_bible)
        await db.execute('UPDATE studio_projects SET breakdown_id=?,episode_seconds_min=?,episode_seconds_max=?,updated_at=? WHERE id=? AND owner=?',
                         (bid, payload['settings']['episode_seconds_min'], payload['settings']['episode_seconds_max'], stamp, pid, owner))
    for jid in scheduled:
        brain_jobs._schedule(jid)
    return await get_current(pid, owner)


def _materialize(breakdown, chunks):
    imported, units, warnings = breakdown['imported'], [], {}
    manifest = imported['_manifest']
    novel = manifest['kind'] == 'novel'
    original = imported.get('units', [])
    completed_chapters = {chapter['chapter'] for chunk in chunks
                          if chunk['task'] == 'novel_complete' and chunk['status'] == 'succeeded'
                          for chapter in (chunk.get('output') or {}).get('chapters', [])}
    for chunk in chunks:
        if chunk['task'] not in {'novel_complete', 'text_map'}:
            continue
        source, result = chunk['source'], chunk.get('output') or {}
        inputs = chunk.get('inputs') or source.get('_inputs', {})
        if chunk['status'] != 'succeeded':
            if novel:
                present_chapters = {item['chapter'] for item in units}
                units.extend(dict(item) for item in original
                             if source['chapter_from'] <= item['chapter'] <= source['chapter_to']
                             and item['chapter'] not in completed_chapters
                             and item['chapter'] not in present_chapters)
            continue
        if novel:
            by_chapter = {item['chapter']: item['text'] for item in inputs['chapters']}
            scenes = [(chapter['chapter'], chapter['scenes'], by_chapter[chapter['chapter']],
                       source.get('chapter_offsets', {}).get(str(chapter['chapter']), 0))
                      for chapter in sorted(result['chapters'], key=lambda value: value['chapter'])]
        else:
            scenes = [(source['block_no'], result['scenes'], inputs['text'], source['start'])]
        for chapter, items, text, offset in scenes:
            located, notes = locate_scenes(text, items, offset)
            warnings.setdefault(chunk.get('id') or '__breakdown__', []).extend(notes)
            for index, scene in enumerate(located, 1):
                # scene_index is unique inside an original block even if it was subdivided.
                scene_index = sum(item['chapter'] == chapter for item in units) + 1
                units.append({**scene, 'chapter': chapter, 'scene_index': scene_index,
                              'label': f"第 {chapter} {'章' if novel else '块'}第 {scene_index} 场"})
    for seq, unit in enumerate(units, 1):
        unit['seq'] = seq
    material = [{**chunk, 'inputs': chunk.get('inputs') or chunk['source'].get('_inputs', {}), 'source': chunk['source']}
                for chunk in chunks if chunk['status'] == 'succeeded']
    bible, notes = merge_bible(imported, material, units, warning_by_chunk=warnings)
    return units, bible, warnings


def _dependency_input(breakdown, chunk, chunks, units):
    source, settings = chunk['source'], breakdown['settings']
    if chunk['task'] == 'synopsis':
        return {'summaries': [{'block': item['source']['block_no'], 'summary': item['output']['summary']}
                              for item in chunks if item['task'] == 'text_map' and item['status'] == 'succeeded']}
    maps = [item for item in chunks if item['no'] in source.get('map_nos', [])]
    if breakdown['imported']['_manifest']['kind'] == 'novel':
        selected = [unit for unit in units if source['chapter_from'] <= unit['chapter'] <= source['chapter_to']]
    else:
        selected = [unit for unit in units if source['block_from'] <= unit['chapter'] <= source['block_to']]
    previous = next((item['output']['episodes'][-1] for item in reversed(chunks)
                     if item['task'] == 'episode_plan' and item['no'] < chunk['no'] and item['status'] == 'succeeded'), None)
    result = {'units': [{key: unit.get(key) for key in ('seq', 'label', 'location', 'summary', 'characters', 'est_seconds', 'change')}
                        for unit in selected],
              'target_min': settings['episode_seconds_min'], 'target_max': settings['episode_seconds_max'],
              'synopsis': breakdown.get('synopsis', {}), 'previous_episode': previous,
              'foreshadowing': breakdown['imported'].get('foreshadowing', []),
              'adaptation': breakdown['imported'].get('adaptation', {})}
    if settings.get('target_episodes'):
        total = sum(unit.get('est_seconds') or 0 for unit in units)
        segment = sum(unit.get('est_seconds') or 0 for unit in selected)
        result['suggested_episodes'] = max(1, round(settings['target_episodes'] * segment / total)) if total else 1
    return result


async def _insert_bible(db, breakdown, bible):
    # Deterministic IDs preserve author edits while later batches finish.
    bid, stamp = breakdown['id'], store.utcnow()
    author_edits = breakdown['imported'].get('_bible_author_edits', {})
    desired, generated = {}, set(breakdown['imported'].get('_generated_bible_ids', []))
    for item in bible:
        identifier = str(uuid.uuid5(uuid.UUID(bid), item['kind'] + ':' + (item.get('ref_id') or item['name'])))
        desired[identifier] = item
        generated.add(identifier)
        existing = await _one(db, 'SELECT * FROM studio_bible WHERE id=?', (identifier,))
        aliases = await _json(item.get('aliases', []))
        if existing:
            edited = set(author_edits.get(identifier, []))
            updates = {} if 'first_unit' in edited else {'first_unit': item.get('first_unit')}
            if 'aliases' not in edited:
                updates['aliases_json'] = aliases
            for field in ('role', 'description'):
                if field not in edited and not existing.get(field) and item.get(field):
                    updates[field] = item[field]
            if not existing.get('excerpt') and item.get('excerpt'):
                updates['excerpt'] = item['excerpt']
            if ('appearance' not in edited and existing['appearance_source'] != 'author'
                    and not existing.get('appearance') and item.get('appearance')):
                updates.update(appearance=item['appearance'], appearance_source=item.get('appearance_source', 'excerpt'))
                if 'needs_author' not in edited:
                    updates['needs_author'] = 0
            if updates:
                await db.execute('UPDATE studio_bible SET ' + ','.join(field + '=?' for field in updates) + ' WHERE id=?',
                                 (*updates.values(), identifier))
            continue
        await db.execute('''INSERT INTO studio_bible(id,project_id,owner,breakdown_id,kind,name,aliases_json,role,
            description,appearance,appearance_source,excerpt,needs_author,first_unit,episodes_json,ref_id,
            merged_into,archived,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'[]',?,NULL,0,?)''',
            (identifier, breakdown['project_id'], breakdown['owner'], bid, item['kind'], item['name'],
             aliases, item.get('role', ''), item.get('description', ''), item.get('appearance', ''),
             item.get('appearance_source', 'none'), item.get('excerpt', ''), int(item.get('needs_author', False)),
             item.get('first_unit'), item.get('ref_id'), stamp))

    # A later completed earlier batch can change the canonical display name.
    # Retire obsolete generated IDs instead of leaving duplicate active rows.
    existing_rows = await _many(db, 'SELECT * FROM studio_bible WHERE breakdown_id=?', (bid,))
    by_id = {row['id']: row for row in existing_rows}
    merge_warnings = breakdown['imported'].setdefault('_bible_merge_warnings', [])
    for old in existing_rows:
        try:
            automatic = old['id'] in generated or uuid.UUID(old['id']).version == 5
        except ValueError:
            automatic = False
        if old['id'] in desired or not automatic or old.get('merged_into') or old.get('archived'):
            continue
        old_aliases = await asyncio.to_thread(json.loads, old.get('aliases_json') or '[]')
        old_names = {normalize_name(name) for name in [old['name'], *old_aliases]}
        for target_id, item in desired.items():
            if old['kind'] != item['kind']:
                continue
            names = {normalize_name(name) for name in [item['name'], *item.get('aliases', [])]}
            same_ref = old.get('ref_id') and old['ref_id'] == item.get('ref_id')
            if (old.get('ref_id') and item.get('ref_id') and not same_ref) or not (same_ref or old_names & names):
                continue
            target, edits = by_id[target_id], set(author_edits.get(target_id, []))
            updates = {}
            for field in author_edits.get(old['id'], []):
                if field in edits:
                    merge_warnings.append(f"{old['name']} 合并时保留项已有作者修改，原值仍保存在被合并条目中。")
                    continue
                column = {'aliases': 'aliases_json'}.get(field, field)
                if column in {'name', 'aliases_json', 'role', 'description', 'appearance', 'needs_author', 'first_unit'}:
                    updates[column] = old[column]
                    edits.add(field)
                    if field == 'appearance':
                        updates['appearance_source'] = 'author'
            if updates:
                await db.execute('UPDATE studio_bible SET ' + ','.join(field + '=?' for field in updates) + ' WHERE id=?',
                                 (*updates.values(), target_id))
                target.update(updates)
                author_edits[target_id] = sorted(edits)
            await db.execute('UPDATE studio_bible SET merged_into=?,updated_at=? WHERE id=?', (target_id, stamp, old['id']))
            break
    breakdown['imported']['_generated_bible_ids'] = sorted(generated)
    breakdown['imported']['_bible_author_edits'] = author_edits
    breakdown['imported']['_bible_merge_warnings'] = list(dict.fromkeys(merge_warnings))
    await db.execute('UPDATE studio_breakdowns SET import_json=? WHERE id=?', (await _json(breakdown['imported']), bid))


async def _stored_units(db, bid):
    rows = await _many(db, 'SELECT * FROM studio_units WHERE breakdown_id=? ORDER BY seq', (bid,))
    return await asyncio.to_thread(lambda: [{**row, 'characters': json.loads(row['characters_json'])} for row in rows])


async def _source_inputs(breakdown, chunk):
    """Read only this batch's immutable snapshot slices when they are needed."""
    source = chunk['source']
    indices = source.get('indices') if chunk['task'] == 'novel_complete' else [source.get('index') or source['block_no']]
    manifest, entries = await _locked_snapshot(breakdown['project_id'], breakdown['owner'], breakdown['snapshot_no'], indices=indices)
    def assemble():
        by_index = {entry['index']: entry for entry in entries}
        if chunk['task'] == 'text_map':
            entry = by_index[indices[0]]
            begin = source['start'] - entry.get('start', 0)
            end = source['end'] - entry.get('start', 0)
            return {'text': entry['body'][begin:end], 'block_no': source['block_no']}
        ranges = source.get('ranges') or [{'index': index, 'chapter': by_index[index]['chapter'],
                    'start': source.get('chapter_offsets', {}).get(str(by_index[index]['chapter']), 0),
                    'end': len(by_index[index]['body'])} for index in indices]
        return {'chapters': [{'chapter': item['chapter'],
                             'text': by_index[item['index']]['body'][item['start']:item['end']],
                             'scenes': (by_index[item['index']].get('outline') or {}).get('scenes', [])}
                            for item in ranges],
                'known_characters': [{'id': item.get('ref_id') or item.get('id'), 'name': item['name'],
                                      'has_appearance': bool(item.get('appearance'))}
                                     for item in breakdown['imported'].get('characters', [])]}
    return await asyncio.to_thread(assemble)


async def prepare_job(jid, owner):
    async with store.connection() as db:
        job = await _job(db, jid, owner)
        cid = job.get('params', {}).get('breakdown_chunk') if job else None
        if not cid:
            return job['params']['inputs']
        chunk = await _one(db, 'SELECT * FROM studio_chunks WHERE id=? AND job_id=? AND owner=?', (cid, jid, owner))
        if chunk is None or chunk['status'] != 'queued' or job['status'] != 'queued':
            raise HTTPException(409, '拆解批次已更新')
        breakdown = await _breakdown(db, chunk['breakdown_id'], owner)
        if _retired(breakdown):
            raise HTTPException(409, '拆解已取消')
        chunks = await _chunks(db, breakdown['id'])
        if not all(item['status'] == 'succeeded' for item in chunks if item['id'] in chunk['depends_on']):
            raise HTTPException(409, '拆解依赖尚未完成')
        units = await _stored_units(db, breakdown['id'])
    inputs = (await _source_inputs(breakdown, chunk) if chunk['task'] in {'novel_complete', 'text_map'} else
              await asyncio.to_thread(_dependency_input, breakdown, chunk, chunks, units))
    async with store.connection(transaction=True) as db:
        async with db.execute("UPDATE studio_jobs SET params_json=?,input_chars=?,updated_at=? WHERE id=? AND status='queued'",
                              (await _json({'inputs': inputs, 'breakdown_chunk': cid}),
                               await asyncio.to_thread(brain_jobs._input_chars, chunk['task'], inputs), store.utcnow(), jid)) as cursor:
            if cursor.rowcount != 1:
                raise HTTPException(409, '拆解批次已更新')
    return inputs


async def refresh_for_job(jid):
    async with store.connection() as db:
        job = await _one(db, 'SELECT group_id,owner FROM studio_jobs WHERE id=?', (jid,))
        if job is None:
            return
        bid = job.get('group_id')
        if not bid or await _one(db, 'SELECT id FROM studio_breakdowns WHERE id=?', (bid,)) is None:
            return
    await refresh(bid, job['owner'])


def _status(breakdown, chunks):
    if breakdown['status'] == 'cancelled':
        return 'cancelled'
    if breakdown.get('superseded_by'):
        # 已被新拆解替代：状态冻结，不再重新物化，也不再发布方案。
        return breakdown['status']
    if chunks and all(chunk['status'] == 'succeeded' for chunk in chunks):
        return 'done'
    if any(chunk['status'] in {'running', 'queued'} for chunk in chunks):
        return 'running'
    return 'partial' if any(chunk['status'] in RETRYABLE | {'uncertain'} for chunk in chunks) else 'running'


def _dirty(breakdown, chunks, jobs):
    by_id = {chunk['id']: chunk for chunk in chunks}
    for chunk in chunks:
        job = jobs.get(chunk['job_id'])
        if chunk['status'] not in {'blocked', 'cancelled'} and job and job['status'] != chunk['status']:
            return True
        if (not _retired(breakdown) and chunk['status'] == 'blocked'
                and all(by_id[cid]['status'] == 'succeeded' for cid in chunk['depends_on'])):
            return True
    return _status(breakdown, chunks) != breakdown['status']


async def refresh(bid, owner, *, dispatch=True):
    scheduled = []
    async with store.connection(transaction=True) as db:
        breakdown, chunks = await _breakdown(db, bid, owner), await _chunks(db, bid)
        jobs = {job['id']: job for job in await _many(db, "SELECT * FROM studio_jobs WHERE group_id=? AND owner=?", (bid, owner))}
        if not await asyncio.to_thread(_dirty, breakdown, chunks, jobs):
            return
        changed, material_changed = set(), False
        for chunk in chunks:
            if chunk['status'] in {'blocked', 'cancelled'}:
                continue
            job = jobs.get(chunk['job_id'])
            if job and chunk['status'] != job['status']:
                previous_status = chunk['status']
                material_changed |= chunk['task'] in {'novel_complete', 'text_map'} and (job['status'] == 'succeeded' or previous_status == 'succeeded')
                chunk.update(status=job['status'], output=job.get('output'))
                changed.add(chunk['id'])
                if chunk['task'] == 'synopsis' and chunk['status'] == 'succeeded' and previous_status != 'succeeded':
                    breakdown['synopsis'] = chunk['output']
        if material_changed:
            for chunk in chunks:
                if chunk['task'] in {'novel_complete', 'text_map'} and chunk['status'] == 'succeeded':
                    job = jobs.get(chunk['job_id'])
                    chunk['inputs'] = (job.get('params', {}).get('inputs') if job else None) or await _source_inputs(breakdown, chunk)
            units, bible, warning_map = await asyncio.to_thread(_materialize, breakdown, chunks)
            await _insert_units(db, bid, units)
            await _insert_bible(db, breakdown, bible)
            breakdown['imported']['_chunk_material_warnings'] = warning_map
        warning_map = breakdown['imported'].get('_chunk_material_warnings', {})
        for chunk in chunks:
            job = jobs.get(chunk['job_id'])
            notes = list(dict.fromkeys([*((job or {}).get('warnings') or []), *warning_map.get(chunk['id'], [])]))
            if chunk['id'] in changed or notes != (chunk.get('warnings') or []):
                await db.execute('UPDATE studio_chunks SET status=?,result_json=?,warnings_json=?,updated_at=? WHERE id=?',
                                 (chunk['status'], await _json(chunk.get('output')), await _json(notes), store.utcnow(), chunk['id']))
                chunk['warnings'] = notes
        by_id = {chunk['id']: chunk for chunk in chunks}
        if not _retired(breakdown):
            for chunk in chunks:
                if chunk['status'] == 'blocked' and all(by_id[cid]['status'] == 'succeeded' for cid in chunk['depends_on']):
                    await db.execute("UPDATE studio_chunks SET status='queued',updated_at=? WHERE id=? AND status='blocked'",
                                     (store.utcnow(), chunk['id']))
                    chunk['status'] = 'queued'
                    scheduled.append(chunk['job_id'])
        episodes = [episode for chunk in chunks if chunk['task'] == 'episode_plan' and chunk['status'] == 'succeeded'
                    for episode in chunk['output']['episodes']]
        status = _status(breakdown, chunks)
        encoded = await _json(episodes)
        fingerprint = await asyncio.to_thread(lambda: hashlib.sha256(encoded.encode()).hexdigest())
        imported = breakdown['imported']
        if not _retired(breakdown) and episodes and status in {'done', 'partial'} \
                and imported.get('_published_fingerprint') != fingerprint:
            from .breakdown_plan import publish_plan
            await publish_plan(db, bid, episodes, reason='generated' if status == 'done' else 'partial')
            imported['_published_fingerprint'] = fingerprint
        await db.execute('UPDATE studio_breakdowns SET status=?,import_json=?,synopsis_json=?,updated_at=? WHERE id=?',
                         (status, await _json(imported), await _json(breakdown.get('synopsis', {})), store.utcnow(), bid))
    if dispatch:
        for jid in scheduled:
            brain_jobs._schedule(jid)


async def get_current(pid, owner):
    async with store.connection() as db:
        project = await store._project(db, pid, owner)
        if not project.get('breakdown_id'):
            return None
        breakdown = await _breakdown(db, project['breakdown_id'], owner)
        chunks = await _chunks(db, breakdown['id'])
        job_rows = await _many(db, "SELECT id,status,error_code FROM studio_jobs WHERE group_id=? AND owner=?", (breakdown['id'], owner))
        for job in job_rows:
            if job['status'] == 'failed' and job.get('error_code') in {'invalid_output', 'max_tokens'}:
                job['status'] = 'invalid_output'
        dirty = await asyncio.to_thread(_dirty, breakdown, chunks, {job['id']: job for job in job_rows})
    if dirty:
        await refresh(breakdown['id'], owner)
    async with store.connection() as db:
        breakdown = await _breakdown(db, breakdown['id'], owner)
        chunks, charges, public = await _chunks(db, breakdown['id']), [], []
        all_jobs = await _many(db, "SELECT * FROM studio_jobs WHERE group_id=? AND owner=? AND kind='brain'", (breakdown['id'], owner))
        for job in all_jobs:
            charges.append({'currency': job['currency'], 'amount': job.get('actual_amount') or 0})
        for chunk in chunks:
            job = await _job(db, chunk['job_id'], owner)
            public.append({key: chunk[key] for key in ('id', 'no', 'task', 'status', 'provider', 'job_id')} | {
                'source': {key: value for key, value in chunk['source'].items() if not key.startswith('_')},
                'warnings': chunk.get('warnings') or [], 'cost': job.get('cost') if job else None,
                'totals': brain_jobs._totals([{'currency': attempt['currency'], 'amount': attempt.get('actual_amount') or 0}
                    for attempt in all_jobs if attempt.get('params', {}).get('breakdown_chunk') == chunk['id']]),
                'reserved_amount': float(job.get('reserved_amount') or 0) if job else 0})
        async with db.execute('SELECT COUNT(*) FROM studio_units WHERE breakdown_id=?', (breakdown['id'],)) as cursor:
            count = (await cursor.fetchone())[0]
    totals = brain_jobs._totals(charges)
    return {key: breakdown[key] for key in ('id', 'status', 'snapshot_no', 'provider', 'quote_id')} | {
        'outdated': bool(breakdown['outdated']), 'settings': breakdown['settings'], 'synopsis': breakdown['synopsis'],
        'chunks': public, 'units_count': count, 'unit_count': count, 'totals': totals, 'total_cost': totals,
        'retry_needed': [{'label': chunk['source']['label'], 'status': chunk['status']} for chunk in chunks
                         if chunk['status'] in RETRYABLE | {'uncertain'}],
        'blocked_segments': [chunk['source']['label'] for chunk in chunks
                             if chunk['task'] == 'episode_plan' and chunk['status'] == 'blocked'],
        'warnings': [*breakdown['imported'].get('_chunk_material_warnings', {}).get('__breakdown__', []),
                     *breakdown['imported'].get('_bible_merge_warnings', [])]}


async def retry_quote(bid, cid, owner, provider):
    async with store.connection() as db:
        breakdown = await _breakdown(db, bid, owner)
        chunk = next((item for item in await _chunks(db, bid) if item['id'] == cid), None)
        if _retired(breakdown):
            raise HTTPException(409, '拆解已取消，请重新拆解')
        if chunk is None:
            raise HTTPException(404, 'Not Found')
        job = await _job(db, chunk['job_id'], owner)
        status = job['status'] if job and chunk['status'] != 'blocked' else chunk['status']
        if status not in RETRYABLE:
            raise HTTPException(409, '此批不能重跑；结果不确定时必须先释放额度')
    option = await _option(provider, owner)
    if chunk['task'] in {'novel_complete', 'text_map'}:
        inputs = await _source_inputs(breakdown, chunk)
    else:
        async with store.connection() as db:
            chunks, units = await _chunks(db, bid), await _stored_units(db, bid)
        inputs = await asyncio.to_thread(_dependency_input, breakdown, chunk, chunks, units)
    item = await asyncio.to_thread(brain_jobs._quote_item, provider, option['model'], chunk['task'], inputs)
    payload = {'kind': 'breakdown_retry', 'breakdown_id': bid, 'chunk_id': cid, 'previous_job_id': chunk['job_id'],
               'provider': provider, 'items': [item]}
    async with store.connection(transaction=True) as db:
        await _breakdown(db, bid, owner)
        await spend.check_brain_budget(db, owner, brain_jobs._totals([item]))
        return await _write_quote(db, breakdown['project_id'], owner, payload)


async def retry(bid, cid, owner, quote_id, provider=None):
    async with store.connection(transaction=True) as db:
        breakdown = await _breakdown(db, bid, owner)
        chunk = next((item for item in await _chunks(db, bid) if item['id'] == cid), None)
        if _retired(breakdown):
            raise HTTPException(409, '拆解已取消，请重新拆解')
        if chunk is None:
            raise HTTPException(404, 'Not Found')
        payload = await _confirmed_quote(db, quote_id, breakdown['project_id'], owner, 'breakdown_retry')
        if payload['breakdown_id'] != bid or payload['chunk_id'] != cid or (provider and provider != payload['provider']):
            raise HTTPException(409, '重跑报价不匹配')
        old = await _job(db, chunk['job_id'], owner)
        if old['status'] not in RETRYABLE or payload['previous_job_id'] != old['id']:
            raise HTTPException(409, '此批已更新或不能重跑，请重新报价')
        chunk['source']['_item'] = payload['items'][0]
        await db.execute('UPDATE studio_chunks SET source_json=? WHERE id=?', (await _json(chunk['source']), cid))
        job = await _new_chunk_job(db, bid, cid, breakdown['project_id'], owner, payload['items'][0],
                                   {}, quote_id)
        await db.execute("UPDATE studio_chunks SET status='queued',job_id=?,provider=?,result_json=NULL,warnings_json='[]',updated_at=? WHERE id=?",
                         (job['id'], payload['provider'], store.utcnow(), cid))
        await db.execute("UPDATE studio_breakdowns SET status='running',updated_at=? WHERE id=?", (store.utcnow(), bid))
    brain_jobs._schedule(job['id'])
    return await get_current(breakdown['project_id'], owner)


async def cancel(bid, owner):
    async with store.connection(transaction=True) as db:
        breakdown = await _breakdown(db, bid, owner)
        await _cancel_unexecuted(db, breakdown, owner)
    return await get_current(breakdown['project_id'], owner)


async def recover():
    """Only reconcile database dependencies; never submit a provider request at startup."""
    async with store.connection() as db:
        async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_breakdowns'") as cursor:
            if await cursor.fetchone() is None:
                return
        rows = await _many(db, "SELECT id,owner FROM studio_breakdowns WHERE status IN ('running','partial')")
    for row in rows:
        try:
            await refresh(row['id'], row['owner'], dispatch=False)
        except Exception as error:
            logger.warning('studio breakdown recovery skipped id=%s error=%s', row['id'], type(error).__name__)
