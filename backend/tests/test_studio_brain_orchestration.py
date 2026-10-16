"""独立复核导演编排：队列、实际结算、未知费用和上海月界。"""
import asyncio
from decimal import Decimal
import json
import logging

import pytest

import database
from studio import brain, brain_jobs, pricing, spend, store


GOOD = {"logline": "信归旧主", "synopsis": "阿宁把旧信送还。", "genre": "剧情", "tone": "克制",
        "theme": "归还", "pacing": "先等待后归还", "adaptation_risks": []}
MODELS = {"claude": "claude-sonnet-5-5", "qwen": "qwen3.8-max", "deepseek": "deepseek-v4-pro"}
USAGE = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def orchestration(client, monkeypatch):
    owner = "orchestration-author"
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", owner)
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    run(database.get_or_create_user(owner))
    project = run(store.create_project(owner, "独立编排复核", "16:9"))

    async def available(username):
        return [{"id": provider, "label": provider, "available": True, "model": model}
                for provider, model in MODELS.items()]

    monkeypatch.setattr(brain, "provider_options", available)
    # 测试自己控制派发时点，生产调度器不会抢先推进队列。
    monkeypatch.setattr(brain_jobs, "_schedule", lambda jid: None)
    return owner, project


def reply(provider="claude", output=GOOD, usage=None):
    return brain.BrainReply(text=json.dumps(output), usage=USAGE if usage is None else usage,
                            model=MODELS[provider], stop_reason="stop", latency_s=.25)


@pytest.mark.parametrize("provider", MODELS)
def test_provider_lane_runs_three_and_leaves_remaining_jobs_queued(orchestration, monkeypatch, provider):
    owner, project = orchestration

    async def scenario():
        await brain_jobs.patch_project(project["id"], owner, provider)
        jobs = []
        for index in range(6):
            group = await brain_jobs.start_trial(project["id"], owner, f"第{index}封旧信", ["read_through"], "current")
            jobs.extend(group["jobs"])
        release, first_three = asyncio.Event(), asyncio.Event()
        active, peak, total = 0, 0, 0

        class Adapter:
            model = MODELS[provider]

            async def call(self, task, inputs, images=None, repair=None):
                nonlocal active, peak, total
                active += 1
                total += 1
                peak = max(peak, active)
                if active == 3:
                    first_three.set()
                try:
                    await release.wait()
                    return reply(provider)
                finally:
                    active -= 1

        async def adapter(*args, **kwargs):
            return Adapter()

        monkeypatch.setattr(brain, "get_provider", adapter)
        tasks = [asyncio.create_task(brain_jobs._background(job["id"])) for job in jobs]
        try:
            await asyncio.wait_for(first_three.wait(), timeout=3)
            statuses = [(await store.get_job(job["id"]))["status"] for job in jobs]
            assert statuses.count("running") == 3 and statuses.count("queued") == 3
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
            assert total == 6 and peak == 3
            assert all([(await store.get_job(job["id"]))["status"] == "succeeded" for job in jobs])
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    run(scenario())


def test_unknown_first_usage_remains_unknown_after_successful_separately_billed_repair(orchestration, monkeypatch):
    owner, _project = orchestration
    calls = []

    class Adapter:
        model = MODELS["claude"]

        async def call(self, task, inputs, images=None, repair=None):
            calls.append(repair)
            return reply(output={}, usage={}) if len(calls) == 1 else reply()

    async def adapter(*args, **kwargs):
        return Adapter()

    monkeypatch.setattr(brain, "get_provider", adapter)
    result = run(brain.run_brain("read_through", {"text": "阿宁归还旧信。"}, provider="claude", username=owner))
    assert result.repaired and result.cost["amount"] is None
    assert len(calls) == 2 and calls[0] is None and calls[1]

    async def rows():
        async with store.connection() as db:
            return await store._many(db, "SELECT * FROM studio_jobs WHERE owner=? ORDER BY created_at,id", (owner,))

    jobs = run(rows())
    assert len(jobs) == 2
    assert jobs[0]["status"] == "invalid_output" and jobs[0]["actual_amount"] is None
    assert float(jobs[0]["reserved_amount"]) > 0
    assert jobs[1]["status"] == "succeeded" and jobs[1]["actual_amount"] is not None


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
@pytest.mark.parametrize("uncertain", [False, True])
def test_cny_calls_settle_actual_usage_or_keep_uncertain_reserve_without_other_provider(orchestration, monkeypatch, provider, uncertain):
    owner, project = orchestration
    calls, providers = [], []

    class Adapter:
        model = MODELS[provider]

        async def call(self, task, inputs, images=None, repair=None):
            calls.append(repair)
            if uncertain:
                raise brain.BrainProviderError("uncertain", "transport_error", "可能已扣费")
            return reply(provider)

    async def adapter(selected, *args, **kwargs):
        providers.append(selected)
        return Adapter()

    monkeypatch.setattr(brain, "get_provider", adapter)

    async def scenario():
        await brain_jobs.patch_project(project["id"], owner, provider)
        group = await brain_jobs.start_trial(project["id"], owner, "阿宁归还旧信。", ["read_through"], "current")
        jid = group["jobs"][0]["id"]
        before = await spend.today()
        await brain_jobs._background(jid)
        return await store.get_job(jid), before, await spend.today()

    job, before, after = run(scenario())
    assert len(calls) == 1 and providers == [provider]
    assert job["currency"] == "CNY"
    if uncertain:
        assert job["status"] == "uncertain" and job["actual_amount"] is None
        assert float(job["reserved_amount"]) > 0 and float(job["reserved_cny"]) > 0
        assert after["committed_cny"] == before["committed_cny"]
    else:
        expected = pricing.brain_actual_cost(MODELS[provider], USAGE)["amount"]
        assert job["status"] == "succeeded" and job["cost"]["amount"] == expected
        assert float(job["reserved_amount"]) == 0 and job["reserved_cny"] == 0
        assert after["committed_cny"] == expected


def test_single_path_image_uses_one_image_reserve_and_deepseek_maps_to_qwen_model(orchestration, monkeypatch, tmp_path):
    from studio.config import get_settings
    vision_model = get_settings().vision_model
    vision_warning = brain.VISION_WARNING.format(model=vision_model)
    owner, _project = orchestration
    path = tmp_path / "frame.png"
    from PIL import Image
    Image.new("RGB", (30, 30)).save(path)
    inputs = {"text": "检查结构和材质。"}
    item = brain_jobs._quote_item("deepseek", vision_model, "frame_qc", inputs, images=path)
    listed = brain_jobs._quote_item("deepseek", vision_model, "frame_qc", inputs, images=[path])
    assert item["first_max"] == listed["first_max"]
    assert item["currency"] == "CNY"
    seen = []
    output = {key: {"passed": True, "notes": "可见结构正常。"}
              for key in ("structure", "materials", "physics", "realistic_frontal_face")}

    class Adapter:
        model = vision_model

        async def call(self, task, inputs, images=None, repair=None):
            seen.append(images)
            return brain.BrainReply(json.dumps(output), USAGE, self.model, "stop", .1, [vision_warning])

    async def adapter(provider, username, images=None):
        assert provider == "deepseek"
        return Adapter()

    monkeypatch.setattr(brain, "get_provider", adapter)
    result = run(brain.run_brain("frame_qc", inputs, provider="deepseek", username=owner, images=path))
    assert len(seen) == 1 and result.model == vision_model and result.cost["currency"] == "CNY"
    assert result.warnings.count(vision_warning) == 1


def test_month_occupancy_uses_shanghai_confirmation_month_and_counts_reserved_uncertain_succeeded(orchestration):
    owner, project = orchestration

    async def scenario():
        jobs = []
        for index in range(6):
            group = await brain_jobs.start_trial(project["id"], owner, f"旧信{index}", ["read_through"], "current")
            jobs.extend(group["jobs"])
        states = [
            ("queued", "1", None, "2026-10"),
            ("uncertain", "2", None, "2026-10"),
            ("succeeded", "0", "3", "2026-10"),
            ("rejected", "9", "9", "2026-10"),
            ("running", "4", None, "2026-11"),
            ("released", "9", "9", "2026-11"),
        ]
        async with store.connection(transaction=True) as db:
            for job, (status, reserved, actual, month) in zip(jobs, states):
                await db.execute("UPDATE studio_jobs SET status=?,reserved_amount=?,actual_amount=?,confirmed_month=? WHERE id=?",
                                 (status, reserved, actual, month, job["id"]))
        return (await spend.brain_month_used(owner, now="2026-10-31T15:59:59+00:00"),
                await spend.brain_month_used(owner, now="2026-10-31T16:00:00+00:00"),
                await spend.brain_month_used("someone-else", now="2026-10-31T15:59:59+00:00"))

    october, november, other = run(scenario())
    assert october == Decimal("6") and november == Decimal("4") and other == 0


def test_sqlite_debug_logs_never_include_material_or_model_output(orchestration, monkeypatch, caplog):
    owner, _project = orchestration
    source = "STUDIO_PRIVATE_SOURCE_415c1 原文。"
    output = {**GOOD, "logline": "STUDIO_PRIVATE_OUTPUT_90d2e 梗概。"}

    class Adapter:
        model = MODELS["claude"]

        async def call(self, task, inputs, images=None, repair=None):
            return reply(output=output)

    async def adapter(*args, **kwargs):
        return Adapter()

    monkeypatch.setattr(brain, "get_provider", adapter)
    with caplog.at_level(logging.DEBUG, logger="aiosqlite"):
        result = run(brain.run_brain("read_through", {"text": source}, provider="claude", username=owner))
    assert result.output["logline"] == output["logline"]
    assert "STUDIO_PRIVATE_SOURCE_415c1" not in caplog.text
    assert "STUDIO_PRIVATE_OUTPUT_90d2e" not in caplog.text
