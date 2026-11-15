"""后台任务：讨论群的启动、取消、重启恢复与关停。

结构照 ``novel/runner.py``：每个群同时只有一个带令牌的任务，令牌在
``discuss_groups`` 里声明；任务体在进程内的全站并发信号量里按群状态调用
``engine``，退出时统一退还预扣并把令牌置空。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from uuid import uuid4
from weakref import WeakKeyDictionary

from novel.billing import InsufficientStrawberries, RunNoLongerActive
from novel.byok_bridge import ByokBridge, ByokUnavailable
from novel.llm_router import LLMRouter, StepFailed
from novel.run_store import utc_now
from utils.background_tasks import create_background_task

from . import config, engine
from . import store as discuss_store
from .billing import DiscussBilling, DiscussBudgetExceeded
from .engine import WORKING
from .store import DiscussStepStore, get_db


logger = logging.getLogger(__name__)
TASKS: dict[str, asyncio.Task] = {}
_owners: dict[str, str] = {}
_semaphores = WeakKeyDictionary()


def _slots():
    """One global semaphore per event loop, read from config at call time."""
    loop = asyncio.get_running_loop()
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(config.max_running())
    return _semaphores[loop]


async def _row(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        value = await cursor.fetchone()
        return dict(value) if value else None


async def _rows(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        return [dict(value) for value in await cursor.fetchall()]


def router_factory(store, username, group_id, run_token):
    """The single injection seam for offline runner tests."""
    return LLMRouter(store, billing=DiscussBilling(username, group_id, run_token),
                     byok_bridge=ByokBridge(username))


async def start_group(group_id, username, *, recovering=False):
    """Claim a run token and schedule the group without waiting for models."""
    existing = TASKS.get(group_id)
    if existing is not None and not existing.done():
        async with get_db() as db:
            previous = await _row(
                db, "SELECT run_token FROM discuss_groups WHERE id=? AND username=?",
                (group_id, username))
        if previous is None or previous["run_token"]:
            return existing
        # The outgoing worker is still refunding and closing provider clients.
        # Drain it before a new run may reserve against the same group.
        await asyncio.gather(existing, return_exceptions=True)
        return await start_group(group_id, username, recovering=recovering)

    token = str(uuid4())

    async def claim_token(db):
        group = await _row(
            db,
            "SELECT g.* FROM discuss_groups g JOIN users u ON u.username=g.username "
            "WHERE g.id=? AND g.username=?",
            (group_id, username))
        if group is None or group["status"] not in ("planning", "running") or group["run_token"]:
            return None
        await db.execute(
            "UPDATE discuss_groups SET run_token=?,updated_at=? WHERE id=? AND username=?",
            (token, utc_now(), group_id, username))
        return token

    async def release_claim():
        """Clear the token only if it is still the one this caller claimed."""
        async def clear_token(db):
            await db.execute(
                "UPDATE discuss_groups SET run_token=NULL "
                "WHERE id=? AND username=? AND run_token=?",
                (group_id, username, token))

        try:
            await discuss_store.run_write(clear_token)
        except asyncio.CancelledError:
            # The protected transaction still settles before delivery.  The
            # caller's original cancellation below must win over a second one.
            logger.warning("group_id=%s status=claim_clear_cancelled", group_id)
        except Exception as error:
            logger.warning("group_id=%s status=claim_clear_failed type=%s",
                           group_id, type(error).__name__)

    # The token declaration must survive a cancellation of this caller: if the
    # transaction were torn down mid-statement it could leave the write lock
    # held with no worker owning it.  A cancellation delivered after the commit
    # must compensate the token before it is handed back to the caller.
    try:
        claimed = await discuss_store.run_write(claim_token)
    except asyncio.CancelledError:
        await release_claim()
        raise
    if claimed is None:
        return None

    task = create_background_task(
        _run(group_id, username, token, recovering=recovering),
        label=f"discuss:{group_id}")
    TASKS[group_id], _owners[group_id] = task, username

    def finished(completed):
        if TASKS.get(group_id) is completed:
            TASKS.pop(group_id, None)
            _owners.pop(group_id, None)

    task.add_done_callback(finished)
    return task


async def cancel_group(group_id, username):
    """Drain the worker before refunding and invalidating its token."""
    task = TASKS.get(group_id)
    if (task is not None and _owners.get(group_id) == username
            and task is not asyncio.current_task()):
        try:
            if not task.done():
                loop = task.get_loop()
                if loop.is_closed() or not loop.is_running():
                    # The worker's loop is gone or stopped (for example a
                    # previous TestClient/portal closed with an undrained task).
                    # Scheduling onto it would raise or never resolve, so detach
                    # the stale task instead of waiting for a dead loop.
                    task.cancel()
                else:
                    async def cancel_and_drain():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

                    if loop is asyncio.get_running_loop():
                        await cancel_and_drain()
                    else:
                        # Service tooling may run on a different event loop from
                        # the worker. Cancel and drain on the owning loop before
                        # touching the token or the reservations.
                        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                            cancel_and_drain(), loop))
        finally:
            # A handled entry must not be retried by the next shutdown. The
            # done callback cannot be relied on after its loop has closed.
            if TASKS.get(group_id) is task:
                TASKS.pop(group_id, None)
                _owners.pop(group_id, None)
    await DiscussBilling(username, group_id).refund_reserved()

    async def clear_token(db):
        await db.execute(
            "UPDATE discuss_groups SET run_token=NULL WHERE id=? AND username=?",
            (group_id, username))

    await discuss_store.run_write(clear_token)


async def cancel_user_tasks(username):
    async with get_db() as db:
        groups = await _rows(db, "SELECT id FROM discuss_groups WHERE username=?", (username,))
    for group in groups:
        await cancel_group(group["id"], username)


async def shutdown_discuss_tasks():
    entries = [(group_id, _owners.get(group_id)) for group_id in list(TASKS)]
    for group_id, username in entries:
        if username is not None:
            await cancel_group(group_id, username)


async def recover_interrupted_groups():
    """Resume groups whose in-process worker died with the previous process."""
    async with get_db() as db:
        # Startup tests and tooling can intentionally replace schema creation
        # with a no-op. An absent discuss schema has no work to recover.
        table = await _row(
            db, "SELECT name FROM sqlite_master WHERE type='table' AND name='discuss_groups'")
        if table is None:
            return
        groups = await _rows(
            db,
            "SELECT id,username FROM discuss_groups "
            "WHERE status IN ('planning','running') ORDER BY created_at,id",
        )
    for group in groups:
        try:
            await cancel_group(group["id"], group["username"])
            await start_group(group["id"], group["username"], recovering=True)
        except Exception:
            async def mark_restart_failed(db):
                await db.execute(
                    "UPDATE discuss_groups SET status='paused',stop_reason='server_restart_failed',"
                    "last_error=NULL,run_token=NULL,updated_at=? WHERE id=? AND username=?",
                    (utc_now(), group["id"], group["username"]))

            await discuss_store.run_write(mark_restart_failed)
            logger.warning("group_id=%s status=server_restart_failed", group["id"])


async def _pause(store, reason, last_error=None):
    """Write the final state behind the token guard; stale workers write nothing."""
    status = "failed" if reason == "error" else "paused"

    async def operation(db):
        await db.execute(
            "UPDATE discuss_groups SET status=?,stop_reason=?,last_error=?,run_token=NULL,"
            "updated_at=? WHERE id=? AND username=?",
            (status, reason, last_error, utc_now(), store.group_id, store.username))

    try:
        await store.transaction(operation)
    except RunNoLongerActive:
        # A stale worker must finish quietly, exactly like the old guarded
        # context manager that yielded None.
        return


async def _cleanup(group_id, username, token, router):
    """退还预扣、关闭客户端并清掉令牌，任何一步都不掩盖原始异常。"""
    try:
        await DiscussBilling(username, group_id).refund_reserved()
    except Exception as error:
        logger.warning("group_id=%s status=refund_failed type=%s", group_id, type(error).__name__)
    try:
        clients = getattr(router, "_clients", {}) if router is not None else {}
        for client in clients.values():
            try:
                await client.close()
            except Exception:
                pass
    except Exception:
        pass
    try:
        async def clear_token(db):
            await db.execute(
                "UPDATE discuss_groups SET run_token=NULL WHERE id=? AND username=? AND run_token=? "
                "AND EXISTS(SELECT 1 FROM users WHERE username=discuss_groups.username)",
                (group_id, username, token))

        await discuss_store.run_write(clear_token)
    except Exception as error:
        logger.warning("group_id=%s status=token_clear_failed type=%s", group_id, type(error).__name__)


async def _run(group_id, username, token, *, recovering=False):
    store = DiscussStepStore(username, group_id, token)
    router = None
    try:
        async with _slots():
            if not await store.is_current():
                return
            await store.initialize()
            router = router_factory(store, username, group_id, token)
            if inspect.isawaitable(router):
                router = await router
            async with get_db() as db:
                group = await _row(
                    db, "SELECT status FROM discuss_groups WHERE id=? AND username=?",
                    (group_id, username))
            status = group["status"] if group is not None else None
            if status == "planning":
                await engine.run_planning(store, router)
            elif status == "running":
                await engine.run_rounds(store, router)
    except asyncio.CancelledError:
        raise
    except RunNoLongerActive:
        pass
    except Exception as error:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            # A protected write may finish with a normal exception after the
            # caller was cancelled.  The author's pause (or a shutdown) owns
            # the final state; do not persist a failure stop reason first.
            raise asyncio.CancelledError() from error
        if isinstance(error, InsufficientStrawberries):
            await _pause(store, "insufficient_strawberries")
        elif isinstance(error, DiscussBudgetExceeded):
            await _pause(store, "budget")
        elif isinstance(error, ByokUnavailable):
            await _pause(store, "byok_unavailable",
                         last_error="自带模型当前不可用，请到设置里检查后再继续")
        elif isinstance(error, engine.SearchUnavailable):
            await _pause(store, "search_unavailable")
        elif isinstance(error, StepFailed):
            await _pause(store, "server_restart_failed" if recovering else "step_failed")
        else:
            # Exception text may contain prompts or a provider's response body.
            logger.warning("group_id=%s status=%s type=%s", group_id,
                           "paused" if recovering else "failed", type(error).__name__)
            await _pause(store, "server_restart_failed" if recovering else "error")
    finally:
        await _cleanup(group_id, username, token, router)
        WORKING.pop(group_id, None)
