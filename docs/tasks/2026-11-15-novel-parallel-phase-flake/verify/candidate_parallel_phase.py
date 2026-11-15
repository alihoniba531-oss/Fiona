"""Reference copies used while the spec awaits confirmation. Not part of the suite.

Run from ``backend/`` with ``tests`` on ``PYTHONPATH`` and this file given by path
(see ``run_matrix.sh``). It holds:

1. The three sibling-cancellation cases in the proposed form. They are the
   repository tests with one difference: the failing role waits until all three
   requests have reached the model, instead of yielding to the event loop once.
   Every assertion is copied unchanged.
2. One evidence case that makes the situation of the flaky runs deterministic -
   a sibling that is still inside the router when the phase fails - and shows the
   implementation cancels and drains it.
"""
import asyncio
import json
import time
from pathlib import Path

import pytest

import novel
from novel.bible import build_setup
from novel.deliberation import deliberate
from novel.fake_llm import FakeLLM
from novel.llm_router import StepFailed
from test_novel_workflow import LocalRouter


def make_workshop(panel_mode=None):
    config = json.loads((Path(novel.__file__).parent / "pilot_configs/expA.json").read_text())
    if panel_mode:
        config["panel_mode"] = panel_mode
    config["target"] = {"min_chapters": 8, "max_chapters": 12, "chapter_words": 300}
    config["agents"] = {role: f"fake:{role}" for role in config["agents"]}
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
    return config, compass, bible


def run_case(workshop, phase, forbidden_task):
    started, cancelled, running = set(), set(), set()
    all_started = asyncio.Event()

    async def delayed_failure(request, _index):
        if FakeLLM.payload(request)["task"] != phase:
            return None
        role = request["role"]
        started.add(role)
        running.add(role)
        if len(started) == 3:
            all_started.set()
        try:
            if role == "plot_architect":
                await asyncio.wait_for(all_started.wait(), timeout=5)
                raise StepFailed()
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.add(role)
            raise
        finally:
            running.discard(role)

    router = LocalRouter(FakeLLM(delayed_failure))
    config, compass, bible = workshop

    async def still_running_event_loop():
        with pytest.raises(StepFailed):
            await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                             participants=config["arms"]["panel"])
        assert started == {"plot_architect", "character_advocate", "twist_designer"}
        assert cancelled == {"character_advocate", "twist_designer"}
        assert running == set() and router.active == 0
        count_after_failure = len(router.requests)
        await asyncio.sleep(0)
        assert len(router.requests) == count_after_failure
        assert all(FakeLLM.payload(request)["task"] != forbidden_task
                   for request in router.requests)

    asyncio.run(still_running_event_loop())


@pytest.mark.parametrize("phase", ["proposal", "critique"])
def test_failed_parallel_phase_cancels_and_drains_siblings_before_return(phase):
    run_case(make_workshop(), phase, "decision")


def test_all_advisor_calls_are_cancelled_and_drained_if_one_fails():
    run_case(make_workshop("critique"), "critique_plan", "finalize")


class StalledSiblingRouter(LocalRouter):
    """twist_designer issues its 1 ms router timer 5 ms late, so it is still inside
    the router (counted in ``active``, not yet at the model) when the phase fails."""

    async def call(self, **request):
        if request["role"] == "twist_designer":
            time.sleep(0.005)
        return await super().call(**request)


def test_sibling_still_inside_router_is_cancelled_and_drained():
    reached = set()

    async def fail_after_one_yield(request, _index):
        if FakeLLM.payload(request)["task"] != "proposal":
            return None
        reached.add(request["role"])
        if request["role"] == "plot_architect":
            await asyncio.sleep(0)
            raise StepFailed()
        await asyncio.sleep(10)

    router = StalledSiblingRouter(FakeLLM(fail_after_one_yield))
    config, compass, bible = make_workshop()

    async def main():
        with pytest.raises(StepFailed):
            await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                             participants=config["arms"]["panel"])
        assert "twist_designer" not in reached      # it never got to the model
        assert len(router.requests) == 3            # though its call had been issued
        assert router.active == 0                   # and it was unwound before return
        assert asyncio.all_tasks() == {asyncio.current_task()}
        await asyncio.sleep(0.02)
        assert "twist_designer" not in reached and len(router.requests) == 3

    asyncio.run(main())
