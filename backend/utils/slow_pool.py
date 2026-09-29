"""Bounded executor for slow tools and external information calls.

The default executor remains available for chat state and stream reads. A
cancelled HTTP request does not free its slow-call slot until the underlying
synchronous work actually exits.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import os
from threading import Lock
from weakref import WeakKeyDictionary


DEFAULT_SLOW_POOL_WORKERS = 16
_pool: ThreadPoolExecutor | None = None
_pool_lock = Lock()
_loop_slots: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()


def _worker_count() -> int:
    try:
        count = int(os.getenv("FIONA_SLOW_POOL_WORKERS", str(DEFAULT_SLOW_POOL_WORKERS)))
    except ValueError:
        count = DEFAULT_SLOW_POOL_WORKERS
    return count if 1 <= count <= 128 else DEFAULT_SLOW_POOL_WORKERS


def _get_pool() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=_worker_count(), thread_name_prefix="fiona-slow")
        return _pool


def _slots_for(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    with _pool_lock:
        slots = _loop_slots.get(loop)
        if slots is None:
            # At most one queued job per worker; additional callers await a
            # slot without occupying a thread or the executor work queue.
            slots = asyncio.Semaphore(_worker_count() * 2)
            _loop_slots[loop] = slots
        return slots


async def run_slow(func, *args, **kwargs):
    """Run synchronous external work outside asyncio's default executor."""
    loop = asyncio.get_running_loop()
    slots = _slots_for(loop)
    await slots.acquire()
    try:
        future = _get_pool().submit(partial(func, *args, **kwargs))
    except BaseException:
        slots.release()
        raise

    def release_slot(_future) -> None:
        try:
            loop.call_soon_threadsafe(slots.release)
        except RuntimeError:
            # The loop may already be closed during process shutdown.
            pass

    future.add_done_callback(release_slot)
    return await asyncio.wrap_future(future)


def shutdown_slow_pool() -> None:
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
        _loop_slots.clear()
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
