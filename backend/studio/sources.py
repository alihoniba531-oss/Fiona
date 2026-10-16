"""作品只读适配与不可变快照。小说工坊正文永不在这里修改。"""
from __future__ import annotations

import asyncio
import errno
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile

from fastapi import HTTPException

from novel import service
from novel.runner import is_editing
from . import storage, store

logger = logging.getLogger(__name__)
MAX_CHARS = 500_000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_BYTES = 30 * 1024 * 1024
_OUTLINE_KEYS = ('title', 'chapter_goal', 'scenes', 'beats', 'opening_hook', 'ending_hook')


def novel_access(username: str) -> bool:
    allowed = {name.strip() for name in os.getenv('FIONA_NOVEL_USERS', '').split(',') if name.strip()}
    return os.getenv('FIONA_NOVEL', '0') == '1' and username in allowed


def novel_chat_enabled(username: str) -> bool:
    return os.getenv('FIONA_NOVEL_CHAT', '0') == '1' and novel_access(username)


async def _novel_call(function, *args):
    try:
        return await function(*args)
    except HTTPException as exc:
        message = '作品不存在或无权访问' if exc.status_code in (403, 404) else '作品读取失败，请稍后再试'
        raise HTTPException(404 if exc.status_code in (403, 404) else 409, message) from None


def _require_novel(username):
    if not novel_access(username):
        raise HTTPException(404, '作品不存在或无权访问')


def _eligibility(book, canonical_bible, editing=False):
    chapters = book.get('chapters') or []
    if book.get('status') != 'completed':
        return False, '作品尚未完结'
    if canonical_bible is None:
        return False, '作品缺少故事圣经'
    if not chapters:
        return False, '作品没有章节'
    if any(item.get('status') == 'stale' for item in chapters):
        return False, '作品有待复核章节，请先在小说工坊完成复核'
    if any(item.get('status') != 'done' for item in chapters):
        return False, '作品有尚未完成的章节'
    if editing:
        return False, '作品正在修改，请稍后再试'
    return True, None


def _flagged(chapters):
    return [{key: item.get(key) for key in ('chapter', 'title', 'flags')}
            for item in chapters if item.get('flags')]


async def _candidate(username, book):
    detail = await _novel_call(service.detail, username, book['id'])
    bible = await _novel_call(service.bible, username, book['id'])
    eligible, reason = _eligibility(detail, bible, is_editing(book['id']))
    async with store.connection() as db:
        projects = await store._many(db, """SELECT id,title,snapshot_no,created_at FROM studio_projects
            WHERE owner=? AND source_kind='novel' AND source_ref=? AND archived=0
            ORDER BY created_at,id""", (username, book['id']))
    return {**{key: detail.get(key) for key in ('id', 'title', 'status', 'chapters_done', 'words_done',
                                              'completed_at', 'updated_at')},
            'title': detail.get('title') or '未命名小说',
            'drama_adaptation': bool((detail.get('config') or {}).get('drama_adaptation', False)),
            'eligible': eligible, 'reason': reason, 'flagged': _flagged(detail.get('chapters') or []),
            'projects': projects}


async def _candidates(username, books):
    result = [await _candidate(username, book) for book in books]
    result.sort(key=lambda item: not item['drama_adaptation'])
    return {'enabled': True, 'books': result}


async def list_candidates(username):
    if not novel_access(username):
        return {'enabled': False, 'books': []}
    return await _candidates(username, await _novel_call(service.list_books, username))


async def find_candidates(username, query):
    if not novel_access(username):
        return {'enabled': False, 'books': []}
    books = await _novel_call(service.find_books, username, query)
    exact = [book for book in books if (book.get('title') or '').strip().casefold() == query.strip().casefold()]
    return await _candidates(username, exact if len(exact) == 1 else books)


def _bounded(chapters):
    chars = sum(len(item['body']) for item in chapters)
    if chars > MAX_CHARS:
        raise HTTPException(422, '作品超过 50 万字，暂不支持')
    return chars


async def _all_chapters(username, book):
    numbers = [item['chapter'] for item in book.get('chapters') or []]
    maximum = max(numbers + [book.get('chapters_done') or 0])
    if maximum > 300 or any(type(number) is not int or number < 1 for number in numbers):
        raise HTTPException(409, '作品章节范围无效')
    chapters = []
    for start in range(1, maximum + 1, 50):
        chapters.extend(await _novel_call(service.chapters_range, username, book['id'], start, min(start + 49, maximum)))
    return chapters, maximum


def _signature(book):
    return (book.get('updated_at'), book.get('bible_version'), book.get('status'),
            tuple((ch.get('chapter'), ch.get('status')) for ch in book.get('chapters') or []))


async def take_novel_snapshot(username, book_id):
    _require_novel(username)
    for attempt in range(2):
        book = await _novel_call(service.detail, username, book_id)
        bible = await _novel_call(service.bible, username, book_id)
        eligible, reason = _eligibility(book, bible, is_editing(book_id))
        if not eligible:
            raise HTTPException(409, reason)
        chapters, maximum = await _all_chapters(username, book)
        after = await _novel_call(service.detail, username, book_id)
        if _signature(book) != _signature(after) or is_editing(book_id):
            if attempt == 0:
                continue
            raise HTTPException(409, '作品正在修改，请稍后再试')
        return await asyncio.to_thread(_assemble_novel_snapshot, book, bible, chapters, maximum, book_id)
    raise HTTPException(409, '作品正在修改，请稍后再试')


def _assemble_novel_snapshot(book, bible, chapters, maximum, book_id):
    by_number = {item['chapter']: item for item in chapters}
    for number in range(1, maximum + 1):
        if number not in by_number or not isinstance(by_number[number].get('body'), str) or not by_number[number]['body'].strip():
            raise HTTPException(409, f'第 {number} 章正文缺失或为空')
    chapters = [by_number[number] for number in range(1, maximum + 1)]
    chars = _bounded(chapters)
    entries = []
    for index, item in enumerate(chapters, 1):
        entry = _entry(index, item['chapter'], item.get('title') or '', item['body'])
        entry.update({key: item.get(key) for key in ('status', 'flags', 'updated_at', 'edited_by_user')})
        beat_sheet = ((item.get('meeting') or {}).get('decision') or {}).get('beat_sheet') or {}
        entry['outline'] = {key: beat_sheet[key] for key in _OUTLINE_KEYS if key in beat_sheet}
        entries.append(entry)
    canonical = dict(bible)
    compass = canonical.pop('compass', book.get('compass'))
    manifest = {'version': 1, 'kind': 'novel', 'ref_id': book_id, 'title': book.get('title') or '未命名小说',
                'created_at': store.utcnow(), 'chars': chars, 'chapters': entries,
                'book': {key: book.get(key) for key in ('id', 'title', 'status', 'completed_at', 'updated_at', 'bible_version')},
                'config': _public_config({key: book['config'][key] for key in ('drama_adaptation', 'structure', 'target', 'adaptation')
                           if key in (book.get('config') or {})}), 'compass': compass, 'bible': canonical}
    return {'manifest': manifest, 'bodies': [item['body'] for item in chapters]}


def _public_config(value):
    if isinstance(value, dict):
        return {key: _public_config(item) for key, item in value.items() if not key.startswith('_')}
    if isinstance(value, list):
        return [_public_config(item) for item in value]
    return value


def _entry(index, chapter, title, body):
    return {'index': index, 'chapter': chapter, 'title': title, 'file': f'chapters/{index:04d}.md',
            'chars': len(body), 'sha256': hashlib.sha256(body.encode('utf-8')).hexdigest()}


def normalize_text(raw, filename=None):
    encoding = 'text'
    if filename and Path(filename).suffix.lower() == '.docx':
        if not isinstance(raw, bytes):
            raise HTTPException(422, 'Word 文件无效')
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(422, '上传文件不能超过 10 MB')
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > MAX_DOCUMENT_BYTES:
                    raise HTTPException(422, 'Word 正文解压后不能超过 30 MB')
                with archive.open(info) as handle:
                    document = handle.read(MAX_DOCUMENT_BYTES + 1)
                if len(document) > MAX_DOCUMENT_BYTES:
                    raise HTTPException(422, 'Word 正文解压后不能超过 30 MB')
            if b'<!DOCTYPE' in document.replace(b'\x00', b'').upper():
                raise HTTPException(422, 'Word 文件不支持 DOCTYPE')
            root = ET.fromstring(document)
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            paragraphs = []
            for paragraph in root.iter(ns + 'p'):
                paragraphs.append(''.join(element.text or '' if element.tag == ns + 't'
                                          else '\t' if element.tag == ns + 'tab' else '\n'
                                          for element in paragraph.iter()
                                          if element.tag in (ns + 't', ns + 'tab', ns + 'br')))
            text, encoding = '\n'.join(paragraphs), 'docx'
        except HTTPException:
            raise
        except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError, RuntimeError, ValueError, LookupError, NotImplementedError):
            raise HTTPException(422, 'Word 文件无效') from None
    elif isinstance(raw, bytes):
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(422, '上传文件不能超过 10 MB')
        text = None
        for codec, label in (('utf-8-sig', 'utf-8'), ('gb18030', 'gb18030')):
            try:
                text, encoding = raw.decode(codec, errors='strict'), label
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise HTTPException(422, '无法识别文件编码，请另存为 UTF-8')
    elif isinstance(raw, str):
        text = raw
    else:
        raise HTTPException(422, '作品文本无效')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t').strip()
    if not text:
        raise HTTPException(422, '作品文本不能为空')
    return text, encoding


_HEADING_PATTERNS = (
    ('第X章', re.compile(r'^[ \t]*第[0-9０-９零〇一二两三四五六七八九十百千万]+[章回卷节集幕][^\n]*', re.M)),
    ('Chapter N', re.compile(r'^[ \t]*chapter\s+[0-9ivxlcdm]+\b[^\n]*', re.M | re.I)),
    ('markdown', re.compile(r'^[ \t]*#{1,3}[ \t]+\S[^\n]*', re.M)),
)


class TextChunks(list):
    def __init__(self, chunks, split, heading_style):
        super().__init__(chunks)
        self.split, self.heading_style = split, heading_style


def split_text(text):
    for style, pattern in _HEADING_PATTERNS:
        matches = list(pattern.finditer(text))
        if len(matches) < 2:
            continue
        chunks = []
        if text[:matches[0].start()].strip():
            chunks.append({'title': '前言', 'start': 0, 'end': matches[0].start(), 'body': text[:matches[0].start()]})
        for index, match in enumerate(matches):
            start, end = match.start(), matches[index + 1].start() if index + 1 < len(matches) else len(text)
            title = re.sub(r'^#{1,3}\s+', '', match.group().strip()).strip()[:80]
            chunks.append({'title': title, 'start': start, 'end': end, 'body': text[start:end]})
        return TextChunks(chunks, 'headings', style)
    chunks, start = [], 0
    while start < len(text):
        limit = min(start + 10_000, len(text))
        end = limit
        if limit < len(text):
            blank = text.rfind('\n\n', start, limit + 1)
            line = text.rfind('\n', start, limit + 1)
            if blank > start:
                end = blank + 2
            elif line > start:
                end = line + 1
            else:
                punctuation = list(re.finditer(r'[。！？.!?]', text[start:limit]))
                if punctuation:
                    end = start + punctuation[-1].end()
        chunks.append({'title': f'第 {len(chunks) + 1} 段', 'start': start, 'end': end, 'body': text[start:end]})
        start = end
    return TextChunks(chunks, 'chunks', None)


async def take_text_snapshot(username, kind, title, text, encoding='text'):
    await asyncio.to_thread(_validate_text_source, kind, text)
    chunks = await asyncio.to_thread(split_text, text)
    return await asyncio.to_thread(_assemble_text_snapshot, kind, title, text, encoding, chunks)


def _validate_text_source(kind, text):
    if kind not in {'upload', 'paste', 'exchange'}:
        raise HTTPException(422, '作品来源无效')
    if len(text) > MAX_CHARS:
        raise HTTPException(422, '作品超过 50 万字，暂不支持')
    if not text.strip():
        raise HTTPException(422, '作品文本不能为空')


def _assemble_text_snapshot(kind, title, text, encoding, chunks):
    entries = [{**_entry(index, index, chunk['title'], chunk['body']), 'start': chunk['start'], 'end': chunk['end']}
               for index, chunk in enumerate(chunks, 1)]
    return {'manifest': {'version': 1, 'kind': kind, 'ref_id': None, 'title': title,
                         'created_at': store.utcnow(), 'chars': sum(item['chars'] for item in entries),
                         'chapters': entries, 'split': chunks.split, 'heading_style': chunks.heading_style,
                         'encoding': encoding}, 'bodies': [chunk['body'] for chunk in chunks], 'full': text}


def _exchange_eligible(exchange, username):
    # exchange_store deliberately serializes identity as viewer_role rather than raw usernames.
    mine = (exchange['initiator_username'] == username if 'initiator_username' in exchange
            else exchange.get('viewer_role') == 'initiator')
    recipient = exchange.get('recipient') or {}
    partner = exchange.get('recipient_agent_id') or recipient.get('id')
    return mine and partner == 'official:short-video-creator' and exchange.get('status') == 'completed'


async def _exchange_details(username, exchange_id):
    import exchange_store
    from agent_store import ResourceNotFound
    try:
        result = await exchange_store.exchange_details(username, exchange_id)
        exchange = result['exchange']
    except (ResourceNotFound, HTTPException):
        raise HTTPException(404, '交流不存在或没有成稿') from None
    return exchange, await asyncio.to_thread(_exchange_artifact, exchange, username)


def _exchange_artifact(exchange, username):
    artifact = exchange.get('artifact') or ''
    if not artifact.strip() and not exchange.get('workflow_version'):
        artifact = exchange.get('summary') or ''
    if not _exchange_eligible(exchange, username) or not artifact.strip():
        raise HTTPException(404, '交流不存在或没有成稿')
    return artifact


async def list_exchanges(username):
    import exchange_store
    result, offset = [], 0
    while True:
        exchanges = await exchange_store.list_exchanges(username, limit=50, offset=offset)
        for item in exchanges:
            if not _exchange_eligible(item, username):
                continue
            try:
                exchange, artifact = await _exchange_details(username, item['id'])
            except HTTPException as exc:
                if exc.status_code == 404:
                    continue
                raise
            text, _ = await asyncio.to_thread(normalize_text, artifact)
            result.append({'id': item['id'], 'title': item.get('topic') or '创意搭档成稿',
                           'completed_at': exchange.get('completed_at') or exchange.get('updated_at'),
                           'chars': len(text), 'artifact_status': item.get('artifact_status')})
        if len(exchanges) < 50:
            return result
        offset += 50


async def take_exchange_snapshot(username, exchange_id):
    exchange, artifact = await _exchange_details(username, exchange_id)
    text, encoding = await asyncio.to_thread(normalize_text, artifact)
    snapshot = await take_text_snapshot(username, 'exchange', (exchange.get('topic') or '创意搭档成稿')[:200], text, encoding)
    snapshot['manifest']['ref_id'] = exchange_id
    return snapshot


def _write_file(path, data):
    with path.open('xb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _write_snapshot(pid, no, snapshot):
    storage._component(pid)
    rel_dir = f'{pid}/source/snap-{no:04d}'
    part_rel = f'{rel_dir}.part-{uuid.uuid4().hex}'
    target, part = storage.resolve_path(rel_dir), storage.resolve_path(part_rel)
    storage.storage_root(create=True)
    part.parent.mkdir(parents=True, exist_ok=True)
    part = storage.resolve_path(part_rel)
    target = storage.resolve_path(rel_dir)
    if target.exists():
        raise HTTPException(409, '快照已更新，请重新检查')
    part.mkdir()
    renamed = False
    try:
        storage.resolve_path(f'{part_rel}/chapters').mkdir()
        for item, body in zip(snapshot['manifest']['chapters'], snapshot['bodies'], strict=True):
            _write_file(storage.resolve_path(f"{part_rel}/{item['file']}"), body.encode('utf-8'))
        if 'full' in snapshot:
            _write_file(storage.resolve_path(f'{part_rel}/full.txt'), snapshot['full'].encode('utf-8'))
        data = (json.dumps(snapshot['manifest'], ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        _write_file(storage.resolve_path(f'{part_rel}/snapshot.json'), data)
        try:
            part.rename(target)
        except OSError as exc:
            if exc.errno in (errno.EEXIST, errno.ENOTEMPTY, errno.EISDIR):
                raise HTTPException(409, '快照已更新，请重新检查') from None
            raise
        renamed = True
        _fsync_directory(target.parent)
        return rel_dir, hashlib.sha256(data).hexdigest()
    except BaseException:
        if renamed:
            _discard_directory(rel_dir)
        raise
    finally:
        if part.exists():
            shutil.rmtree(part)


def _fsync_directory(directory):
    descriptor = None
    try:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        os.fsync(descriptor)
    except OSError as exc:
        # Windows does not support opening/fsyncing directory handles this way.
        # Real disk errors, including every POSIX error, abort before DB commit.
        unsupported = (errno.EACCES, errno.EBADF, errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EISDIR)
        if os.name != 'nt' or exc.errno not in unsupported:
            raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _discard_directory(rel_dir):
    path = storage.resolve_path(rel_dir)
    if path.exists():
        shutil.rmtree(path)
    parent = path.parent
    root = storage.storage_root()
    while parent != root and parent.is_relative_to(root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


async def _finish_task(task):
    """Drain an owned worker through repeated cancellation before releasing its files."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


async def _save_snapshot(username, pid, no, snapshot, expected_no):
    rel_dir, committed = None, False
    try:
        write_task = asyncio.create_task(asyncio.to_thread(_write_snapshot, pid, no, snapshot))
        (rel_dir, digest), cancelled = await _finish_task(write_task)
        if cancelled:
            # to_thread cannot stop filesystem work. Wait for its actual result,
            # then remove this unregistered snapshot before propagating cancellation.
            raise asyncio.CancelledError
        manifest = snapshot['manifest']
        async with store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            project = await store._project(db, pid, username)
            if project['snapshot_no'] != expected_no:
                raise HTTPException(409, '快照已更新，请重新检查')
            if expected_no and await store._one(db, """SELECT id FROM studio_jobs WHERE project_id=? AND owner=?
                AND kind='brain' AND status IN ('queued','submitting','submitted','running') LIMIT 1""", (pid, username)):
                raise HTTPException(409, '导演模型任务进行中，完成后再同步')
            await db.execute('''INSERT INTO studio_snapshots(id,project_id,owner,no,kind,ref_id,title,bible_version,
                chapters,chars,manifest_sha256,rel_dir,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (str(uuid.uuid4()), pid, username, no, manifest['kind'], manifest['ref_id'], manifest['title'],
                 (manifest.get('book') or {}).get('bible_version'), len(manifest['chapters']), manifest['chars'],
                 digest, rel_dir, manifest['created_at']))
            # 第 3c 期以 snapshot_no 判断哪些集需要退回；旧快照目录始终归档保留。
            await db.execute('''UPDATE studio_projects SET source_kind=?,source_ref=?,snapshot_no=?,updated_at=?
                WHERE id=? AND owner=?''', (manifest['kind'], manifest['ref_id'], no, store.utcnow(), pid, username))
            commit_task = asyncio.create_task(db.commit())
            _, cancelled = await _finish_task(commit_task)
            committed = True
            if cancelled:
                raise asyncio.CancelledError
    except BaseException:
        if rel_dir is not None and not committed:
            await _finish_task(asyncio.create_task(asyncio.to_thread(_discard_directory, rel_dir)))
        raise


async def _rollback_empty_project(username, pid):
    async with store.connection(transaction=True) as db:
        await db.execute('DELETE FROM studio_projects WHERE id=? AND owner=? AND snapshot_no=0', (pid, username))


async def _create_with_snapshot(username, snapshot, title, aspect):
    project = await store.create_project(username, title or snapshot['manifest']['title'][:200], aspect)
    try:
        await _save_snapshot(username, project['id'], 1, snapshot, 0)
    except BaseException:
        await _finish_task(asyncio.create_task(_rollback_empty_project(username, project['id'])))
        raise
    return await store.get_project(project['id'], username)


async def create_novel_project(username, book_id, title=None, aspect='16:9'):
    return await _create_with_snapshot(username, await take_novel_snapshot(username, book_id), title, aspect)


async def create_text_project(username, kind, title, raw, filename=None, aspect='16:9'):
    if kind == 'upload' and (not filename or Path(filename).suffix.lower() not in {'.txt', '.md', '.docx'}):
        raise HTTPException(422, '上传文件只支持 txt、md 或 docx')
    text, encoding = await asyncio.to_thread(normalize_text, raw, filename if kind == 'upload' else None)
    snapshot = await take_text_snapshot(username, kind, title, text, encoding)
    return await _create_with_snapshot(username, snapshot, title, aspect)


async def create_exchange_project(username, exchange_id, title=None, aspect='16:9'):
    return await _create_with_snapshot(username, await take_exchange_snapshot(username, exchange_id), title, aspect)


async def _current_snapshot(username, pid):
    async with store.connection() as db:
        project = await store._project(db, pid, username)
        if not project.get('source_kind'):
            return project, None
        row = await store._one(db, 'SELECT * FROM studio_snapshots WHERE project_id=? AND owner=? AND no=?',
                               (pid, username, project['snapshot_no']))
    if row is None:
        logger.error('Missing snapshot row for project %s', pid)
        raise HTTPException(500, '作品快照读取失败')
    return project, row


def _read_manifest(row):
    try:
        data = storage.resolve_path(f"{row['rel_dir']}/snapshot.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != row['manifest_sha256']:
            raise ValueError('manifest hash mismatch')
        return json.loads(data)
    except (OSError, ValueError, TypeError):
        logger.exception('Invalid snapshot manifest for project %s', row['project_id'])
        raise HTTPException(500, '作品快照校验失败') from None


async def source_status(username, pid):
    project, row = await _current_snapshot(username, pid)
    if row is None:
        return {'kind': None}
    manifest = await asyncio.to_thread(_read_manifest, row)
    snapshot = {key: row[key] for key in ('id', 'no', 'created_at', 'chapters', 'chars')}
    snapshot['flagged'] = _flagged(manifest['chapters'])
    result = {'kind': row['kind'], 'title': row['title'], 'snapshot': snapshot,
              'drift': {'state': 'not_applicable'}}
    if row['kind'] != 'novel':
        return result
    try:
        _require_novel(username)
        book = await _novel_call(service.detail, username, row['ref_id'])
        bible = await _novel_call(service.bible, username, row['ref_id'])
        chapters, _ = await _all_chapters(username, book)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        result['drift'] = {'state': 'unavailable'}
        return result
    eligible, reason = _eligibility(book, bible, is_editing(book['id']))
    result['drift'] = await asyncio.to_thread(_compare_drift, row, manifest, book, chapters, eligible, reason)
    return result


def _compare_drift(row, manifest, book, chapters, eligible, reason):
    old = {item['chapter']: item for item in manifest['chapters']}
    current = {item['chapter']: item for item in chapters}
    changed = sorted(number for number in old.keys() & current.keys()
                     if old[number]['title'] != (current[number].get('title') or '')
                     or old[number]['sha256'] != hashlib.sha256((current[number].get('body') or '').encode('utf-8')).hexdigest())
    added, removed = sorted(current.keys() - old.keys()), sorted(old.keys() - current.keys())
    bible_changed = row['bible_version'] != book.get('bible_version')
    return {'state': 'changed' if changed or added or removed or bible_changed else 'unchanged',
                       'changed': changed, 'added': added, 'removed': removed, 'bible_changed': bible_changed,
                       'book_status': book['status'], 'eligible': eligible, 'reason': reason}


async def sync_source(username, pid, expected_no):
    project, row = await _current_snapshot(username, pid)
    if row is None or row['kind'] != 'novel':
        raise HTTPException(409, '只有小说工坊来源可以同步')
    if type(expected_no) is not int or expected_no != project['snapshot_no']:
        raise HTTPException(409, '快照已更新，请重新检查')
    async with store.connection() as db:
        if await store._one(db, """SELECT id FROM studio_jobs WHERE project_id=? AND owner=? AND kind='brain'
            AND status IN ('queued','submitting','submitted','running') LIMIT 1""", (pid, username)):
            raise HTTPException(409, '导演模型任务进行中，完成后再同步')
    snapshot = await take_novel_snapshot(username, row['ref_id'])
    await _save_snapshot(username, pid, expected_no + 1, snapshot, expected_no)
    return await source_status(username, pid)


async def read_snapshot(username, pid, start_index, end_index):
    _, row = await _current_snapshot(username, pid)
    if row is None:
        raise HTTPException(404, '项目没有关联作品')
    manifest = await asyncio.to_thread(_read_manifest, row)
    return await asyncio.to_thread(_read_snapshot_chunks, row, manifest, start_index, end_index)


def _read_snapshot_chunks(row, manifest, start_index, end_index):
    if type(start_index) is not int or type(end_index) is not int or not 1 <= start_index <= end_index <= len(manifest['chapters']):
        raise HTTPException(422, '快照读取范围无效')
    result = []
    for item in manifest['chapters'][start_index - 1:end_index]:
        try:
            data = storage.resolve_path(f"{row['rel_dir']}/{item['file']}").read_bytes()
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('chapter hash mismatch')
            result.append({**item, 'body': data.decode('utf-8')})
        except (OSError, ValueError, UnicodeError):
            logger.exception('Invalid snapshot chapter for project %s, index %s', row['project_id'], item['index'])
            raise HTTPException(500, '作品快照校验失败') from None
    return result


async def list_novels(username):
    from .novel_chat import list_novels as implementation
    return await implementation(username)


async def read_novel(username, book, start_chapter, end_chapter=None, offset=0):
    from .novel_chat import read_novel as implementation
    return await implementation(username, book, start_chapter, end_chapter, offset)


async def start_film(username, book, auth_method=None):
    from .novel_chat import start_film as implementation
    return await implementation(username, book, auth_method)
