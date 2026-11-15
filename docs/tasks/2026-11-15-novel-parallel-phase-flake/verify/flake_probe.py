"""Timing probe for the sibling-cancellation tests. Load with ``-p flake_probe``.

Run from ``backend/`` with this directory on ``PYTHONPATH``. The plugin does
nothing outside the target tests and changes no file in the repository; every
wrapper it installs is removed when the test call ends.

Inside a target test it records monotonic timestamps for every loop timer that
is scheduled, every entry into the test's router and into the fake model, and
every garbage-collection pause, then writes one JSON record per test call.

Environment:
  FLAKE_PROBE_OUT         directory for the JSON records (required; without it
                          the plugin is inert)
  FLAKE_PROBE_TARGETS     comma-separated test-name substrings (default: the two
                          sibling-cancellation tests)
  FLAKE_PROBE_STALL       "<role>:<seconds>" - block synchronously for that long
                          at the entry of that role's router call. This is the
                          deterministic trigger: it stands in for any pause
                          (collector, scheduler, page fault) that lands between
                          two sibling calls being issued.
  FLAKE_PROBE_GC_COUNT    no pause is injected; instead the collector's
                          young-generation allocation counter is set just before
                          the test body, so the interpreter's own next collection
                          falls at a chosen point inside the test.
                          "<count>:keep" moves the counter and nothing else: the
                          young generation keeps whatever earlier tests left in
                          it, so the collection is as long as it naturally is.
                          "<count>[:<generation>]" first collects the young
                          generations and refills the counter with empty lists
                          (a short collection; used only to locate positions).
  FLAKE_PROBE_BALLAST     number of long-lived tracked objects to create when the
                          plugin loads, to give a single-test process a heap of
                          the size the full suite has when it reaches the target
  FLAKE_PROBE_MUTATION    no_cancel / no_drain / plain_gather / sequential -
                          swap novel.deliberation._gather_phase for a broken
                          variant during the target tests, to show the tests
                          still tell a correct implementation from a wrong one
  FLAKE_PROBE_EXIT_AFTER  substring of a test name; end the session once that
                          test has run (only the state at the target matters)
"""
import asyncio
import asyncio.base_events
import gc
import json
import os
import resource
import threading
import time

import pytest

TARGETS = tuple(name for name in os.environ.get(
    "FLAKE_PROBE_TARGETS",
    "test_failed_parallel_phase_cancels_and_drains_siblings_before_return,"
    "test_all_advisor_calls_are_cancelled_and_drained_if_one_fails").split(",") if name)
OUT = os.environ.get("FLAKE_PROBE_OUT")
STALL = os.environ.get("FLAKE_PROBE_STALL", "")
MUTATION = os.environ.get("FLAKE_PROBE_MUTATION", "")
EXIT_AFTER = os.environ.get("FLAKE_PROBE_EXIT_AFTER", "")
GC_COUNT = os.environ.get("FLAKE_PROBE_GC_COUNT", "")
BALLAST = int(os.environ.get("FLAKE_PROBE_BALLAST", "0") or 0)
_ballast = []
_pool = []


def pytest_configure(config):
    if OUT and GC_COUNT.endswith(":keep") and not _pool:
        # Objects to release later so the counter can be lowered without a
        # collection. One threshold's worth leaves the counter where it was.
        _pool.extend([] for _ in range(gc.get_threshold()[0] + 1))
    if OUT and BALLAST and not _ballast:
        # Small dicts that point at their neighbours, promoted to the oldest generation.
        previous = None
        for index in range(BALLAST):
            previous = {"index": index, "previous": previous if index % 50 else None}
            _ballast.append(previous)
        gc.collect()


def _move_young_count(target):
    """Move the allocation counter to ``target`` without collecting anything.

    Lists taken from or returned to the interpreter's free list are not counted,
    so the counter is first pushed past the target and then released down to it.
    That leaves the free list full every time, whatever state it started in.
    """
    padding = []
    while gc.get_count()[0] < target + 100:
        padding.append([])
    while gc.get_count()[0] > target and (padding or _pool):
        (padding or _pool).pop()
    return padding


def _set_young_count(target, generation):
    """Leave the allocation counter at ``target`` with the next automatic
    collection being of ``generation``. Returns the objects that hold it there."""
    gc.collect(1)
    if generation:
        for _ in range(gc.get_threshold()[1] + 1):
            gc.collect(0)
    padding = []
    while gc.get_count()[0] < target:
        padding.append([])
    return padding


async def _no_cancel(coroutines):
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _no_drain(coroutines):
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        raise


async def _plain_gather(coroutines):
    return await asyncio.gather(*coroutines)


async def _sequential(coroutines):
    return [await coroutine for coroutine in list(coroutines)]


MUTATIONS = {"no_cancel": _no_cancel, "no_drain": _no_drain,
             "plain_gather": _plain_gather, "sequential": _sequential}


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    if not OUT or not any(name in item.nodeid for name in TARGETS):
        return (yield)

    from novel import deliberation
    from novel.fake_llm import FakeLLM

    events = []
    now = time.monotonic
    stall_role, _, stall_seconds = STALL.partition(":")
    stall_seconds = float(stall_seconds) if stall_seconds else 0.0
    router_class = item.module.LocalRouter
    original_router_call = router_class.call
    original_fake_call = FakeLLM.__call__
    original_call_at = asyncio.base_events.BaseEventLoop.call_at
    original_gather_phase = deliberation._gather_phase
    loop_types = set()

    async def router_call(self, **request):
        events.append((now(), "router_enter", request.get("step_key")))
        if stall_seconds and request.get("role") == stall_role:
            time.sleep(stall_seconds)
        return await original_router_call(self, **request)

    async def fake_call(self, request=None, **kwargs):
        events.append((now(), "fake_enter", (request or kwargs).get("step_key")))
        loop = asyncio.get_running_loop()
        loop_types.add(f"{type(loop).__module__}.{type(loop).__name__}")
        return await original_fake_call(self, request, **kwargs)

    def call_at(self, when, callback, *args, **kwargs):
        events.append((now(), "call_at", when))
        return original_call_at(self, when, callback, *args, **kwargs)

    def on_gc(phase, info):
        events.append((now(), "gc_" + phase, info.get("generation")))

    record = {
        "nodeid": item.nodeid,
        "loadavg": os.getloadavg(),
        "gc_count_before": gc.get_count(),
        "gc_threshold": gc.get_threshold(),
        "gc_enabled": gc.isenabled(),
        "tracked_objects_before": len(gc.get_objects()),
        "threads": sorted(thread.name for thread in threading.enumerate()),
        "max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "stall": STALL,
        "mutation": MUTATION,
    }
    if MUTATION:
        deliberation._gather_phase = MUTATIONS[MUTATION]
    padding = None
    if GC_COUNT:
        count, _, generation = GC_COUNT.partition(":")
        record["gc_count_natural"] = gc.get_count()
        padding = (_move_young_count(int(count)) if generation == "keep"
                   else _set_young_count(int(count), int(generation or 0)))
        record["gc_count_set"] = gc.get_count()
    router_class.call = router_call
    FakeLLM.__call__ = fake_call
    asyncio.base_events.BaseEventLoop.call_at = call_at
    gc.callbacks.append(on_gc)
    started = now()
    outcome, error = "passed", None
    try:
        return (yield)
    except BaseException as exc:  # recorded, then re-raised unchanged
        outcome, error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        raise
    finally:
        finished = now()
        gc.callbacks.remove(on_gc)
        del padding
        deliberation._gather_phase = original_gather_phase
        asyncio.base_events.BaseEventLoop.call_at = original_call_at
        FakeLLM.__call__ = original_fake_call
        router_class.call = original_router_call
        record.update({
            "outcome": outcome, "error": error, "duration": finished - started,
            "loop_types": sorted(loop_types),
            # Seconds since the test call began; for call_at the value is the due time.
            "events": [(t - started, kind, data - started if kind == "call_at" else data)
                       for t, kind, data in events],
        })
        os.makedirs(OUT, exist_ok=True)
        name = f"{time.time_ns()}-{item.name.replace('[', '_').replace(']', '')}.json"
        with open(os.path.join(OUT, name), "w") as handle:
            json.dump(record, handle, ensure_ascii=False)


def pytest_runtest_teardown(item, nextitem):
    if EXIT_AFTER and EXIT_AFTER in item.nodeid and (
            nextitem is None or EXIT_AFTER not in nextitem.nodeid):
        item.session.shouldstop = "flake_probe: target tests have run"
