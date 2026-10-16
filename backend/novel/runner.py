"""Cancellable, resumable orchestration around the P0 novel engine."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import inspect
import json
import logging
import os
from uuid import uuid4
from weakref import WeakKeyDictionary

from rate_limit import check_chat_daily_cap, check_daily_cap
from utils.background_tasks import create_background_task

from .bible import build_setup
from .billing import (InsufficientStrawberries, NovelBilling, NovelBudgetExceeded,
                      RunNoLongerActive)
from .byok_bridge import ByokBridge, ByokUnavailable
from .context import build_review_bible
from .deliberation import deliberate, messages_for, required_response_ids, split_response_ids
from .llm_router import BudgetExhausted, LLMRouter, StepFailed
from .schemas import validate_archive, validate_decision, validate_setup
from .store_db import DbStepStore, get_db
from .writing import apply_archived_chapter, write_chapter


logger = logging.getLogger(__name__)
TASKS: dict[str, asyncio.Task] = {}
_tasks = TASKS
_owners: dict[str, str] = {}
_semaphores = WeakKeyDictionary()
_operation_locks = WeakKeyDictionary()
_editing = set()


def is_editing(novel_id):
    return novel_id in _editing


def _operation_lock(novel_id):
    locks = _operation_locks.setdefault(asyncio.get_running_loop(), {})
    return locks.setdefault(novel_id, asyncio.Lock())


@asynccontextmanager
async def editing_novel(novel_id):
    """Keep edits serial and block queued activations while the worker drains."""
    async with _operation_lock(novel_id):
        _editing.add(novel_id)
        try:
            yield
        finally:
            _editing.discard(novel_id)


def router_factory(store, username, novel_id, run_token):
    """The single injection seam for offline HTTP and recovery tests."""
    return LLMRouter(store, billing=NovelBilling(username, novel_id, run_token),
                     byok_bridge=ByokBridge(username))


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


async def _row(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        value = await cursor.fetchone()
        return dict(value) if value else None


async def _rows(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        return [dict(value) for value in await cursor.fetchall()]


def _slots():
    loop = asyncio.get_running_loop()
    try:
        limit = int(os.getenv("FIONA_NOVEL_MAX_RUNNING", "3"))
        if limit < 1:
            raise ValueError
    except ValueError:
        limit = 3
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(limit)
    return _semaphores[loop]


async def start_novel(novel_id, username, *, recovering=False):
    """Claim a token and schedule work without waiting for any model call."""
    if is_editing(novel_id):
        return None
    # Claim and registration share the edit lock. An edit cannot begin draining
    # after the claim commits but before the new worker appears in TASKS.
    async with _operation_lock(novel_id):
        return await _start_novel_locked(novel_id, username, recovering=recovering)


async def _start_novel_locked(novel_id, username, *, recovering=False):
    existing = TASKS.get(novel_id)
    if existing is not None and not existing.done():
        async with get_db() as db:
            previous = await _row(db, "SELECT run_token FROM novels WHERE id=? AND username=?",
                                  (novel_id, username))
        if previous is None or previous["run_token"]:
            return existing
        # A gate is visible before the outgoing worker has finished its refund
        # and client cleanup. Drain it before a newly approved run can reserve.
        await asyncio.gather(existing, return_exceptions=True)
        return await _start_novel_locked(novel_id, username, recovering=recovering)
    token = str(uuid4())
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        book = await _row(db, "SELECT n.* FROM novels n JOIN users u ON u.username=n.username "
                          "WHERE n.id=? AND n.username=?", (novel_id, username))
        if is_editing(novel_id) or book is None or book["status"] not in ("setup_running", "running") or book["run_token"]:
            return None
        await db.execute("UPDATE novels SET run_token=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND username=?",
                         (token, novel_id, username))
        await db.commit()
    task = create_background_task(_run(novel_id, username, token, recovering=recovering),
                                  label=f"novel:{novel_id}")
    TASKS[novel_id], _owners[novel_id] = task, username

    def finished(completed):
        if TASKS.get(novel_id) is completed:
            TASKS.pop(novel_id, None)
            _owners.pop(novel_id, None)
    task.add_done_callback(finished)
    return task


async def cancel_novel(novel_id, username):
    """Drain the worker before refunding and invalidating its token."""
    task = TASKS.get(novel_id)
    if task is not None and _owners.get(novel_id) == username and task is not asyncio.current_task():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await NovelBilling(username, novel_id).refund_reserved()
    async with get_db() as db:
        await db.execute("UPDATE novels SET run_token=NULL WHERE id=? AND username=?", (novel_id, username))
        await db.commit()


async def cancel_user_tasks(username):
    async with get_db() as db:
        books = await _rows(db, "SELECT id FROM novels WHERE username=?", (username,))
    for book in books:
        await cancel_novel(book["id"], username)


async def shutdown_novel_tasks():
    entries = [(novel_id, _owners.get(novel_id)) for novel_id in list(TASKS)]
    for novel_id, username in entries:
        if username is not None:
            await cancel_novel(novel_id, username)


async def recover_interrupted_novels():
    async with get_db() as db:
        # Startup tests and tooling can intentionally replace schema creation
        # with a no-op. An absent workshop schema has no work to recover.
        table = await _row(db, "SELECT name FROM sqlite_master WHERE type='table' AND name='novels'")
        if table is None:
            return
        books = await _rows(db, "SELECT id,username FROM novels WHERE status IN ('setup_running','running') ORDER BY created_at,id")
    for book in books:
        try:
            await cancel_novel(book["id"], book["username"])
            await start_novel(book["id"], book["username"], recovering=True)
        except Exception:
            async with get_db() as db:
                await db.execute("UPDATE novels SET status='paused',pause_reason='server_restart_failed',run_token=NULL "
                                 "WHERE id=? AND username=?", (book["id"], book["username"]))
                await db.commit()
            logger.warning("novel_id=%s status=server_restart_failed", book["id"])


async def _pause(store, reason, *, last_error=None):
    async with store.transaction() as db:
        if db is not None:
            current = await _row(db, "SELECT config_json,budget_strawberries FROM novels WHERE id=?", (store.novel_id,))
            config = json.loads(current["config_json"])
            if reason == "budget_80":
                config["_budget_at_pause"] = current["budget_strawberries"]
            if last_error is not None:
                config["_last_error"] = last_error
            await db.execute("UPDATE novels SET status='paused',pause_reason=?,config_json=?,run_token=NULL,updated_at=CURRENT_TIMESTAMP "
                             "WHERE id=? AND username=?", (reason, _encode(config), store.novel_id, store.username))


async def _run(novel_id, username, token, *, recovering=False):
    store = DbStepStore(username, novel_id, token, max_total_tokens=2**63 - 1)
    router = None
    try:
        async with _slots():
            if not await store.is_current():
                return
            await store.initialize()
            router = router_factory(store, username, novel_id, token)
            if inspect.isawaitable(router):
                router = await router
            await _advance(store, router)
    except asyncio.CancelledError:
        raise
    except RunNoLongerActive:
        pass
    except (InsufficientStrawberries, NovelBudgetExceeded) as error:
        await _pause(store, error.status)
    except ByokUnavailable as error:
        await _pause(store, "byok_unavailable", last_error=str(error))
    except StepFailed as error:
        await _pause(store, "server_restart_failed" if recovering else
                     "decision_invalid" if error.status == "decision_invalid" else "step_failed")
    except BudgetExhausted:
        await _pause(store, "budget_80")
    except Exception as error:
        # Exception text may contain prompts or a provider's response body.
        logger.warning("novel_id=%s status=failed type=%s", novel_id, type(error).__name__)
        if recovering:
            await _pause(store, "server_restart_failed")
        else:
            async with store.transaction() as db:
                if db is not None:
                    await db.execute("UPDATE novels SET status='failed',pause_reason='step_failed',run_token=NULL,updated_at=CURRENT_TIMESTAMP "
                                     "WHERE id=? AND username=?", (novel_id, username))
    finally:
        await NovelBilling(username, novel_id).refund_reserved()
        if router is not None:
            for client in getattr(router, "_clients", {}).values():
                try:
                    await client.close()
                except Exception:
                    pass
        async with get_db() as db:
            await db.execute("UPDATE novels SET run_token=NULL WHERE id=? AND username=? AND run_token=? "
                             "AND EXISTS(SELECT 1 FROM users WHERE username=novels.username)",
                             (novel_id, username, token))
            await db.commit()


async def _advance(store, router):
    while await store.is_current():
        async with get_db() as db:
            book = await _row(db, "SELECT * FROM novels WHERE id=? AND username=?", (store.novel_id, store.username))
        if book is None or book["status"] not in ("setup_running", "running"):
            return
        config = json.loads(book["config_json"])
        config.update(experiment="P1", critique_rounds=1, enable_arc_summaries=True,
                      enable_context_compression=True)
        if book["status"] == "setup_running":
            payload = {"task": "setup", "seed_idea": book["seed_idea"], "target": config["target"],
                       "adaptation": config["adaptation"]}
            card, messages = messages_for("editor", payload, task="setup",
                                          chapter_words=config["target"]["chapter_words"], split_context=True)
            setup = await router.call(step_key="setup/steps/00-setup-editor.json", role="editor",
                model=config["agents"]["editor"], messages=messages, max_tokens=card["max_tokens"],
                validator=lambda value: validate_setup(value, config), experiment="P1")
            compass, bible = build_setup(setup, config)
            await store.commit_setup(compass, bible)
            return
        compass = json.loads(book["compass_json"])
        async with get_db() as db:
            current = await _row(db, "SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND version=?",
                                 (store.novel_id, book["bible_version"]))
        bible = json.loads(current["bible_json"])
        if config.get("_rearchive"):
            if not await _rearchive(store, router, book, config, compass):
                return
            continue
        if book["chapters_done"]:
            async with get_db() as db:
                latest = await _row(db, "SELECT ending_status FROM novel_chapters WHERE novel_id=? AND chapter=?",
                                    (store.novel_id, book["chapters_done"]))
            # A final chapter can pause for an archival conflict before its end
            # gate is published. An explicit extension raises min_chapters past
            # this chapter; otherwise resuming publishes the pending end gate.
            if latest and latest["ending_status"] == "end" and book["chapters_done"] >= config["target"]["min_chapters"]:
                async with store.transaction() as db:
                    if db is not None:
                        await db.execute("UPDATE novels SET status='awaiting_end',pause_reason=NULL,run_token=NULL,"
                                         "updated_at=CURRENT_TIMESTAMP WHERE id=? AND username=?",
                                         (store.novel_id, store.username))
                return
        if check_chat_daily_cap("novel_chapter", store.username, hit=False) is not None:
            await _pause(store, "daily_cap")
            return
        chapter = book["chapters_done"] + 1
        async with get_db() as db:
            plans = await _row(db, "SELECT * FROM novel_chapters WHERE novel_id=? AND chapter=?", (store.novel_id, chapter))
            history = await _rows(db, "SELECT chapter,ending_status FROM novel_chapters WHERE novel_id=? AND chapter<? ORDER BY chapter", (store.novel_id, chapter))
            previous = await _row(db, "SELECT body FROM novel_chapters WHERE novel_id=? AND chapter=?", (store.novel_id, chapter - 1))
            notes = await _rows(db, "SELECT id,text FROM novel_notes WHERE novel_id=? AND username=? AND status='pending' ORDER BY id", (store.novel_id, store.username))
        participants = [role for role in config["agents"]
                        if role not in ("editor", "writer", "archivist", "reviewer")]
        arm = "solo" if config.get("panel_mode") == "solo" or not participants else "panel"
        if plans and plans["meeting_json"]:
            meeting = json.loads(plans["meeting_json"])
            if meeting.get("_redo_note") is not None:
                meeting = await _redo(store, router, config, compass, bible, chapter, arm, meeting)
        else:
            meeting = await deliberate(router, config, compass, bible, chapter=chapter, arm=arm,
                participants=["editor", *participants] if arm == "panel" else ["editor"],
                history=history, written_words=book["words_done"],
                user_notes=[{"id": f"N{note['id']}", "text": note["text"]} for note in notes])
        if config.get("automation", "per_batch") == "per_chapter" and (not plans or plans["status"] != "writing"):
            await store.save_plan(chapter, meeting)
            return
        product = await write_chapter(router, config, compass, bible, meeting, chapter=chapter, arm=arm,
                                      previous_text=previous["body"] if previous else "")
        if not await store.is_current():
            return
        cap = check_daily_cap("novel_chapter", store.username)
        cap_reached = cap is not None or check_chat_daily_cap("novel_chapter", store.username, hit=False) is not None
        status, reason = "running", None
        if "locked_conflict" in product["flags"]:
            status, reason = "paused", "locked_conflict"
        elif meeting["decision"]["ending_status"] == "end":
            status = "awaiting_end"
        elif cap_reached:
            status, reason = "paused", "daily_cap"
        elif config.get("automation", "per_batch") == "per_batch" and chapter % config.get("batch_size", 5) == 0:
            status = "awaiting_review"
        if not await store.commit_chapter(chapter, meeting, product, status=status, pause_reason=reason):
            return
        if status != "running":
            return


async def _redo(store, router, config, compass, bible, chapter, arm, meeting):
    """Only repeat the editor's existing finalization protocol."""
    meeting = deepcopy(meeting)
    note = meeting.pop("_redo_note")
    critique = meeting.get("mode") == "critique"
    task = "finalize" if critique else "decision"
    brief = deepcopy(meeting["brief"])
    payload = {"task": task, "chapter": chapter, "brief": brief, "mode": brief["mode"],
               "solo": not meeting.get("proposals"), "plan": meeting.get("plan"),
               "critiques": meeting.get("critiques", []), "proposals": meeting.get("proposals", []),
               "objections": meeting.get("objections", []), "author_instruction": note,
               "proposal_ids": [item["id"] for item in meeting.get("proposals", [])],
               "objection_ids": [item["id"] for item in meeting.get("objections", [])],
               "user_notes": brief.get("user_notes", []),
               "note_ids": [item["id"] for item in brief.get("user_notes", [])]}
    if critique:
        payload["objection_ids"], payload["alternative_ids"] = split_response_ids(
            payload["objection_ids"])
    payload["required_response_ids"] = required_response_ids(
        payload["objection_ids"], payload["note_ids"])
    card, messages = messages_for("editor", payload, task=task,
        chapter_words=config["target"]["chapter_words"], split_context=True)
    meeting["decision"] = await router.call(
        step_key=f"arm-{arm}/ch{chapter:03d}/03-{task}-editor-redo{meeting['_redo_count']}.json",
        role="editor", model=config["agents"]["editor"], messages=messages, max_tokens=card["max_tokens"],
        experiment="P1", arm=arm, chapter=chapter, failure_status="decision_invalid",
        validator=lambda value: validate_decision(value, compass=compass, bible=bible,
            chapter=chapter, mode=brief["mode"], proposal_ids=payload["proposal_ids"],
            objection_ids=payload["objection_ids"], note_ids=payload["note_ids"], solo=payload["solo"],
            alternative_ids=payload.get("alternative_ids", ())))
    return meeting


async def _rearchive(store, router, book, config, compass):
    chapter = config["_rearchive"]
    async with get_db() as db:
        original = await _row(db, "SELECT version FROM novel_bible_versions WHERE novel_id=? AND source=? ORDER BY version LIMIT 1",
                              (store.novel_id, f"archive:{chapter}"))
        previous = await _row(db, "SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND version<? ORDER BY version DESC LIMIT 1",
                              (store.novel_id, original["version"]))
        manuscript = await _row(db, "SELECT * FROM novel_chapters WHERE novel_id=? AND chapter=?", (store.novel_id, chapter))
    bible = json.loads(previous["bible_json"])
    meeting = json.loads(manuscript["meeting_json"])
    beat = meeting["decision"]["beat_sheet"]
    payload = {"task": "archive", "chapter": chapter, "body": manuscript["body"], "beat_sheet": beat,
               "bible": build_review_bible(compass, bible, chapter, beat["characters"])}
    card, messages = messages_for("archivist", payload, task="archive",
        chapter_words=config["target"]["chapter_words"], split_context=True)
    digest = hashlib.sha256(manuscript["body"].encode()).hexdigest()[:20]
    archive = await router.call(step_key=f"rearchive/ch{chapter:03d}/{digest}.json", role="archivist",
        model=config["agents"]["archivist"], messages=messages, max_tokens=card["max_tokens"],
        validator=lambda value: validate_archive(value, bible), experiment="P1", chapter=chapter)
    next_bible = await apply_archived_chapter(router, config, compass, bible, archive,
        chapter=chapter, title=manuscript["title"], beat_sheet=beat,
        arm="solo" if config.get("panel_mode") == "solo" else "panel",
        arc_step_key=f"rearchive/ch{chapter:03d}/{digest}-arc-summary.json")
    next_bible["version"] = book["bible_version"] + 1
    status = config.pop("_after_rearchive", "awaiting_review")
    reason = config.pop("_after_rearchive_reason", None)
    config.pop("_rearchive")
    if archive["locked_conflicts"]:
        status, reason = "paused", "locked_conflict"
    flags = [flag for flag in json.loads(manuscript["flags_json"] or "[]") if flag != "locked_conflict"]
    if archive["locked_conflicts"]:
        flags.append("locked_conflict")
    async with store.transaction() as db:
        if db is None:
            return False
        await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)",
                         (store.novel_id, store.username, next_bible["version"], _encode(next_bible), f"rearchive:{chapter}"))
        await db.execute("UPDATE novel_chapters SET archive_json=?,flags_json=?,updated_at=CURRENT_TIMESTAMP WHERE novel_id=? AND chapter=?",
                         (_encode(archive), _encode(flags), store.novel_id, chapter))
        await db.execute("UPDATE novels SET config_json=?,bible_version=?,status=?,pause_reason=?,"
                         "run_token=CASE WHEN ?='running' THEN run_token ELSE NULL END,updated_at=CURRENT_TIMESTAMP WHERE id=? AND username=?",
                         (_encode(config), next_bible["version"], status, reason, status, store.novel_id, store.username))
    return status == "running"
