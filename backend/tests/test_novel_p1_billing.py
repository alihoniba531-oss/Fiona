"""Offline billing, provider transport and storage-protocol regressions."""

import asyncio
import json
import os
import socket

import aiosqlite
import anthropic
import httpx2
import pytest

import database
from novel.billing import (DEFAULT_PRICES, InsufficientStrawberries, NovelBilling,
                           NovelBudgetExceeded, calculate_cost, estimate_cost, get_prices)
from novel.llm_router import LLMRouter, StepFailed
from novel.store_db import DbStepStore, get_db
from novel.fake_llm import FakeLLM


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    monkeypatch.delenv("FIONA_NOVEL_PRICE_JSON", raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


async def _book(monkeypatch, tmp_path, *, balance=10000, budget=10000):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "novel-billing.db"))
    await database.init_db()
    await database.get_or_create_user("billing-author")
    async with get_db() as db:
        await db.execute("UPDATE users SET strawberry_balance=? WHERE username='billing-author'", (balance,))
        await db.execute("INSERT INTO novels(id,username,seed_idea,status,config_json,budget_strawberries,run_token) "
                         "VALUES('billing-book','billing-author','故事','running','{}',?,'token')", (budget,))
        await db.commit()
    return (DbStepStore("billing-author", "billing-book", "token"),
            NovelBilling("billing-author", "billing-book", "token"))


def _call(**changes):
    values = {"step_key": "chapter/one.json", "model": "dashscope:qwen3.8-max", "role": "editor",
              "messages": [{"role": "user", "content": "x" * 1000}], "max_tokens": 1000}
    values.update(changes)
    return values


async def _snapshot():
    async with get_db() as db:
        book = await (await db.execute("SELECT spent_strawberries,reserved_strawberries FROM novels")).fetchone()
        balance = await (await db.execute("SELECT strawberry_balance FROM users WHERE username='billing-author'")).fetchone()
        steps = await (await db.execute("SELECT * FROM novel_steps ORDER BY step_key")).fetchall()
    return tuple(book), balance[0], [dict(row) for row in steps]


def test_author_prices_and_decimal_rounding():
    assert get_prices() == {"dashscope:qwen3.8-max": {"input": 1.8, "output": 5.4},
                            "deepseek:deepseek-flash": {"input": .33, "output": 1.3},
                            "ark:doubao-seed-2-1-pro-260915": {"input": .9, "output": 4.5}}
    assert calculate_cost("dashscope:qwen3.8-max", 1000, 1000) == 8
    assert calculate_cost("dashscope:qwen3.8-max", 0, 0) == 1
    assert calculate_cost("byok:self", 500000, 500000) == 0


@pytest.mark.parametrize("override", ["", "bad-json", "[]", '{"unknown":{}}',
    json.dumps({**DEFAULT_PRICES, "deepseek:deepseek-flash": {"input": -1, "output": 1}}),
    json.dumps({**DEFAULT_PRICES, "deepseek:deepseek-flash": {"input": True, "output": 1}})])
def test_invalid_price_override_falls_back_warns_once(monkeypatch, caplog, override):
    import novel.billing as billing
    monkeypatch.setattr(billing, "_warned_bad_price", False)
    monkeypatch.setenv("FIONA_NOVEL_PRICE_JSON", override)
    assert get_prices() == DEFAULT_PRICES
    assert get_prices() == DEFAULT_PRICES
    assert len(caplog.records) == 1
    if override:
        assert override not in caplog.text


def test_price_override_and_estimate_use_recent_history(monkeypatch):
    replacement = {model: {"input": 2, "output": 3} for model in DEFAULT_PRICES}
    monkeypatch.setenv("FIONA_NOVEL_PRICE_JSON", json.dumps(replacement))
    assert get_prices() == replacement
    agents = {"editor": "dashscope:qwen3.8-max", "writer": "deepseek:deepseek-flash",
              "archivist": "ark:doubao-seed-2-1-pro-260915", "twist_designer": "dashscope:qwen3.8-max"}
    estimate = estimate_cost(agents, "critique", {"min_chapters": 30, "max_chapters": 30})
    sixty = estimate_cost(agents, "critique", {"min_chapters": 60, "max_chapters": 60})
    assert estimate["per_chapter"] == sixty["per_chapter"]
    assert estimate["total"]["max"] < sixty["total"]["max"]
    history = [{"role": role, "model": model, "input_tokens": 10, "output_tokens": 10}
               for role, model in agents.items()] * 6
    from_history = estimate_cost(agents, "critique", recent_steps=history)
    assert from_history["per_chapter"]["max"] < estimate["per_chapter"]["max"]
    free = estimate_cost({role: "byok:self" for role in agents})
    assert free["chapter_range"] == free["book_range"] == [0, 0]


def test_reserve_settle_difference_and_idempotence(monkeypatch, tmp_path):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        call = _call()
        assert await billing.reserve(call) == 8
        assert (await _snapshot())[:2] == ((0, 8), 9992)
        assert await billing.settle(call, {"input_tokens": 100, "output_tokens": 100}) == 1
        assert await billing.settle(call, {"input_tokens": 100, "output_tokens": 100}) == 0
        book, balance, steps = await _snapshot()
        assert book == (1, 0) and balance == 9999
        assert steps[0]["billing_status"] == "settled"
        assert steps[0]["strawberries_charged"] == 1
        assert "messages" not in steps[0]
    asyncio.run(scenario())


def test_charge_never_exceeds_reservation_and_unknown_usage_refunds(monkeypatch, tmp_path):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        call = _call()
        assert await billing.reserve(call) == 8
        assert await billing.settle(call, {"input_tokens": 100000, "output_tokens": 100000}) == 8
        call = _call(step_key="second")
        await billing.reserve(call)
        assert await billing.settle(call, None) == 0
        book, balance, steps = await _snapshot()
        assert book == (8, 0) and balance == 9992
        assert steps[1]["billing_status"] == "refunded"
    asyncio.run(scenario())


@pytest.mark.parametrize("model,dev_mode", [("fake:local", "0"), ("byok:self", "0"),
                                           ("dashscope:qwen3.8-max", "1")])
def test_free_calls_do_not_reserve(monkeypatch, tmp_path, model, dev_mode):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        monkeypatch.setenv("DEV_MODE", dev_mode)
        assert await billing.reserve(_call(model=model)) == 0
        assert await billing.settle(_call(model=model), {"input_tokens": 1000, "output_tokens": 1000}) == 0
        assert (await _snapshot())[:2] == ((0, 0), 10000)
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["funds", "budget"])
def test_failed_precheck_never_sends_call(monkeypatch, tmp_path, kind):
    async def scenario():
        store, billing = await _book(monkeypatch, tmp_path, balance=0 if kind == "funds" else 10000,
                                     budget=1 if kind == "budget" else 10000)
        router = LLMRouter(store, billing=billing)
        async def forbidden(request):
            pytest.fail("precheck must happen before a provider call")
        monkeypatch.setattr(router, "_single_real_call", forbidden)
        with pytest.raises(InsufficientStrawberries if kind == "funds" else NovelBudgetExceeded):
            await router.call(**_call())
        assert store.reserved_tokens == 0
        assert (await _snapshot())[0] == (0, 0)
    asyncio.run(scenario())


def test_validation_retry_charges_each_attempt_and_cache_is_free(monkeypatch, tmp_path):
    async def scenario():
        store, billing = await _book(monkeypatch, tmp_path)
        router = LLMRouter(store, billing=billing)
        calls = []
        async def provider(request):
            calls.append(request["step_key"])
            return ("bad-json" if len(calls) == 1 else '{"ok":true}',
                    {"input_tokens": 100, "output_tokens": 100, "cached_tokens": 30})
        monkeypatch.setattr(router, "_single_real_call", provider)
        assert await router.call(**_call()) == {"ok": True}
        assert await router.call(**_call()) == {"ok": True}
        book, balance, steps = await _snapshot()
        assert len(calls) == 2 and book == (2, 0) and balance == 9998
        assert steps[0]["attempts"] == 2 and steps[0]["cached_tokens"] == 60
        assert steps[0]["strawberries_charged"] == 2
        assert steps[0]["billing_status"] == "settled"
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["network", "missing_usage", "cancel"])
def test_failed_or_unknown_call_refunds_everything(monkeypatch, tmp_path, failure):
    async def scenario():
        store, billing = await _book(monkeypatch, tmp_path)
        router = LLMRouter(store, billing=billing)
        router.retry_delay = 0
        async def provider(request):
            if failure == "network":
                raise ConnectionError("private provider details")
            if failure == "cancel":
                raise asyncio.CancelledError
            return '{"ok":true}', None
        monkeypatch.setattr(router, "_single_real_call", provider)
        if failure == "missing_usage":
            assert await router.call(**_call()) == {"ok": True}
        else:
            with pytest.raises(asyncio.CancelledError if failure == "cancel" else StepFailed):
                await router.call(**_call())
        book, balance, steps = await _snapshot()
        assert book == (0, 0) and balance == 10000
        assert steps[0]["billing_status"] == "refunded"
        assert store.reserved_tokens == 0
        assert "private provider details" not in json.dumps(steps)
    asyncio.run(scenario())


def test_restart_refunds_reserved_once(monkeypatch, tmp_path):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        await billing.reserve(_call())
        recovered = NovelBilling("billing-author", "billing-book")
        assert await recovered.refund_reserved() == 8
        assert await recovered.refund_reserved() == 0
        book, balance, steps = await _snapshot()
        assert book == (0, 0) and balance == 10000
        assert steps[0]["status"] == "interrupted"
    asyncio.run(scenario())


def test_anthropic_system_and_stable_user_ephemeral_cache(monkeypatch, tmp_path):
    async def scenario():
        store, _ = await _book(monkeypatch, tmp_path)
        bodies = []
        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx2.Response(200, json={"id": "msg_test", "type": "message", "role": "assistant",
                "model": "claude-haiku-5-5", "content": [{"type": "text", "text": '{"ok":true}'}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 14, "output_tokens": 6, "cache_read_input_tokens": 4}})
        client = anthropic.AsyncAnthropic(api_key="offline-placeholder", max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)))
        router = LLMRouter(store)
        router._clients["anthropic"] = client
        # Replace all environment values rather than inspecting real credentials.
        monkeypatch.setattr(os, "environ", {"ANTHROPIC_API_KEY": "offline-placeholder"})
        try:
            raw, usage, _ = await router._single_real_call(_call(model="anthropic:claude-haiku-5-5",
                output="json", messages=[{"role": "system", "content": "system"},
                    {"role": "user", "content": "stable"}, {"role": "user", "content": "changing"}]))
        finally:
            await client.close()
        assert json.loads(raw) == {"ok": True} and usage["cached_tokens"] == 4
        assert bodies[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert bodies[0]["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert bodies[0]["messages"][1]["content"] == "changing"
    asyncio.run(scenario())


def test_byok_reuses_transport_discards_client_and_never_persists_key(monkeypatch, tmp_path, capsys):
    async def scenario():
        store, billing = await _book(monkeypatch, tmp_path)
        sentinel = "BYOK_SECRET_MUST_ONLY_EXIST_IN_MEMORY"
        client = anthropic.AsyncAnthropic(api_key=sentinel, max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(
                lambda request: httpx2.Response(200, json={"id": "msg_byok", "type": "message",
                    "role": "assistant", "model": "claude-haiku-5-5",
                    "content": [{"type": "text", "text": '{"ok":true}'}], "stop_reason": "end_turn",
                    "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}}))))
        resolved = {"provider": "anthropic", "model": "claude-haiku-5-5",
                    "base_url": "https://api.anthropic.com", "api_key": sentinel}
        class Bridge:
            async def resolve(self):
                return resolved
        def construct(**kwargs):
            assert kwargs["api_key"] == sentinel
            return client
        monkeypatch.setattr(anthropic, "AsyncAnthropic", construct)
        router = LLMRouter(store, billing=billing, byok_bridge=Bridge())
        assert await router.call(**_call(model="byok:self")) == {"ok": True}
        assert client.is_closed()
        assert resolved == {} and router._clients == {}
        book, balance, steps = await _snapshot()
        assert book == (0, 0) and balance == 10000
        assert steps[0]["billing_status"] == "free"
        assert sentinel not in json.dumps(steps)
        assert sentinel not in capsys.readouterr().out
    asyncio.run(scenario())


async def _runner_book(monkeypatch, tmp_path, *, balance=100000, budget=100000,
                       chapters=3, automation="per_batch"):
    from novel import runner
    await _book(monkeypatch, tmp_path, balance=balance, budget=budget)
    monkeypatch.setenv("FIONA_DAILY_NOVEL_CHAPTERS", "1000")
    config = {"agents": {"editor": "dashscope:qwen3.8-max", "writer": "deepseek:deepseek-flash",
                          "archivist": "dashscope:qwen3.8-max"},
              "panel_mode": "solo", "automation": automation, "batch_size": 5,
              "target": {"min_chapters": chapters, "max_chapters": chapters, "chapter_words": 1000},
              "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3}}
    async with get_db() as db:
        await db.execute("UPDATE novels SET config_json=?,status='setup_running',run_token=NULL",
                         (json.dumps(config),))
        await db.commit()
    fake = FakeLLM()
    def factory(store, username, novel_id, run_token):
        router = LLMRouter(store, billing=NovelBilling(username, novel_id, run_token))
        # Keep the platform model specifications and the production billing
        # path, replacing only the final network seam with a local fake.
        router._single_real_call = fake
        router.retry_delay = 0
        return router
    monkeypatch.setattr(runner, "router_factory", factory)
    return fake


async def _run_to_gate():
    from novel import runner, service
    task = await runner.start_novel("billing-book", "billing-author")
    if task is not None:
        await task
    return await service.detail("billing-author", "billing-book")


async def _drain_runner():
    from novel import runner, service
    task = runner.TASKS.get("billing-book")
    if task is not None:
        await task
    return await service.detail("billing-author", "billing-book")


@pytest.mark.parametrize("reason", ["insufficient_strawberries", "budget_80"])
def test_runner_precheck_pause_and_resume_after_fix(monkeypatch, tmp_path, reason):
    async def scenario():
        from novel import service
        fake = await _runner_book(monkeypatch, tmp_path,
            balance=0 if reason == "insufficient_strawberries" else 100000,
            budget=1 if reason == "budget_80" else 100000)
        book = await _run_to_gate()
        assert book["status"] == "paused" and book["pause_reason"] == reason
        assert fake.call_count == 0
        if reason == "budget_80":
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as stopped:
                await service.transition("billing-author", "billing-book", "resume")
            assert stopped.value.status_code == 409
            await service.patch("billing-author", "billing-book", service.PatchNovel(budget_strawberries=100000))
        else:
            await database.add_strawberry("billing-author", 100000)
        await service.transition("billing-author", "billing-book", "resume")
        book = await _drain_runner()
        assert book["status"] == "awaiting_setup" and fake.call_count == 1
        assert book["spent_strawberries"] > 0 and book["reserved_strawberries"] == 0
    asyncio.run(scenario())


def test_runner_plan_redo_is_a_charged_real_attempt(monkeypatch, tmp_path):
    async def scenario():
        from novel import service
        fake = await _runner_book(monkeypatch, tmp_path, automation="per_chapter")
        assert (await _run_to_gate())["status"] == "awaiting_setup"
        await service.approve_setup("billing-author", "billing-book", service.SetupApproval())
        book = await _drain_runner()
        assert book["status"] == "awaiting_plan"
        before_calls, before_cost = fake.call_count, book["spent_strawberries"]
        await service.redo_plan("billing-author", "billing-book", service.Note(text="让动机更清楚"))
        book = await _drain_runner()
        assert book["status"] == "awaiting_plan" and fake.call_count == before_calls + 1
        assert book["spent_strawberries"] > before_cost
        async with get_db() as db:
            steps = await (await db.execute("SELECT billing_status,strawberries_charged FROM novel_steps "
                                            "WHERE step_key LIKE '%redo1.json'")).fetchall()
        assert len(steps) == 1 and tuple(steps[0])[0] == "settled" and steps[0][1] > 0
    asyncio.run(scenario())


def test_runner_arc_10_and_20_each_generate_once_and_charge(monkeypatch, tmp_path):
    async def scenario():
        from novel import service
        fake = await _runner_book(monkeypatch, tmp_path, chapters=20, automation="full_auto")
        assert (await _run_to_gate())["status"] == "awaiting_setup"
        await service.approve_setup("billing-author", "billing-book", service.SetupApproval())
        book = await _drain_runner()
        assert book["status"] == "awaiting_end" and book["chapters_done"] == 20
        arcs = [request for request in fake.calls if request["task"] == "arc_summary"]
        assert [request["chapter"] for request in arcs] == [10, 20]
        async with get_db() as db:
            version = await (await db.execute("SELECT bible_json FROM novel_bible_versions ORDER BY version DESC LIMIT 1")).fetchone()
            stored_bible = json.loads(version["bible_json"])
            assert [arc["end_chapter"] for arc in stored_bible["dynamic"]["arc_summaries"]] == [10, 20]
            steps = await (await db.execute("SELECT billing_status,strawberries_charged FROM novel_steps "
                                            "WHERE step_key LIKE '%arc-summary%'")).fetchall()
        assert len(steps) == 2
        assert all(row["billing_status"] == "settled" and row["strawberries_charged"] > 0 for row in steps)
        assert book["reserved_strawberries"] == 0
    asyncio.run(scenario())


def test_runner_restart_refunds_reserved_and_reuses_completed_step(monkeypatch, tmp_path):
    async def scenario():
        from novel import runner
        fake = await _runner_book(monkeypatch, tmp_path)
        book = await _run_to_gate()
        assert book["status"] == "awaiting_setup"
        completed_cost, completed_calls = book["spent_strawberries"], fake.call_count
        # A killed process may have persisted setup's successful step while its
        # publication transaction did not commit. Recreate that durable state,
        # plus a still-reserved attempt, without reading git or external files.
        async with get_db() as db:
            await db.execute("DELETE FROM novel_bible_versions WHERE novel_id='billing-book'")
            await db.execute("UPDATE novels SET status='setup_running',run_token='dead-process',"
                             "compass_json=NULL,bible_version=0 WHERE id='billing-book'")
            await db.commit()
        billing = NovelBilling("billing-author", "billing-book", "dead-process")
        reserved = await billing.reserve(_call(step_key="interrupted-attempt"))
        assert reserved == 8
        await runner.recover_interrupted_novels()
        recovered = await _drain_runner()
        assert recovered["status"] == "awaiting_setup"
        assert fake.call_count == completed_calls
        assert recovered["spent_strawberries"] == completed_cost
        assert recovered["reserved_strawberries"] == 0
        async with get_db() as db:
            step = await (await db.execute("SELECT billing_status,status FROM novel_steps "
                                           "WHERE step_key='interrupted-attempt'")).fetchone()
        assert tuple(step) == ("refunded", "interrupted")
    asyncio.run(scenario())


@pytest.mark.parametrize("percentage", [79, 80])
def test_budget_exact_79_and_80_percent_boundary(monkeypatch, tmp_path, percentage):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path, balance=100000, budget=10000)
        # 1000 output tokens at exactly 79/80 strawberries per thousand.
        prices = {model: {"input": 0, "output": percentage * 100} for model in DEFAULT_PRICES}
        monkeypatch.setenv("FIONA_NOVEL_PRICE_JSON", json.dumps(prices))
        call = _call(messages=[{"role": "user", "content": "x"}])
        assert calculate_cost(call["model"], 1, 1000) == percentage * 100
        if percentage == 80:
            with pytest.raises(NovelBudgetExceeded):
                await billing.reserve(call)
            assert (await _snapshot())[:2] == ((0, 0), 100000)
        else:
            assert await billing.reserve(call) == 7900
            assert (await _snapshot())[:2] == ((0, 7900), 92100)
            assert await billing.refund_reserved() == 7900
    asyncio.run(scenario())


def test_reserve_statement_failure_rolls_back_refill_balance_and_book(monkeypatch, tmp_path):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path, balance=7)
        monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "200")
        monkeypatch.setattr(database, "_today_shanghai", lambda: "2026-10-15")
        async with get_db() as db:
            await db.execute("UPDATE users SET strawberry_refill_date='2026-10-14'")
            await db.execute("CREATE TRIGGER fail_reservation BEFORE INSERT ON novel_steps "
                             "BEGIN SELECT RAISE(ABORT,'injected reservation failure'); END")
            await db.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await billing.reserve(_call())
        assert (await _snapshot())[:2] == ((0, 0), 7)
        async with get_db() as db:
            refill_date = await (await db.execute("SELECT strawberry_refill_date FROM users")).fetchone()
        assert refill_date[0] == "2026-10-14"
    asyncio.run(scenario())


@pytest.mark.parametrize("balance,last_refill", [(0, None), (300, "2026-10-14"), (300, "2026-10-15")])
def test_novel_reservation_reuses_existing_daily_refill_semantics(monkeypatch, tmp_path, balance, last_refill):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path, balance=balance)
        monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "200")
        monkeypatch.setattr(database, "_today_shanghai", lambda: "2026-10-15")
        await database.get_or_create_user("comparison-author")
        async with get_db() as db:
            await db.execute("UPDATE users SET strawberry_balance=?,strawberry_refill_date=?",
                             (balance, last_refill))
            await db.commit()
        expected = await database.reserve_strawberries("comparison-author", 8)
        assert await billing.reserve(_call()) == 8
        async with get_db() as db:
            rows = await (await db.execute("SELECT strawberry_balance,strawberry_refill_date "
                                           "FROM users ORDER BY username")).fetchall()
        assert tuple(rows[0]) == tuple(rows[1]) == (expected, "2026-10-15")
        await billing.refund_reserved()
    asyncio.run(scenario())


def test_cancel_after_reserve_commit_drains_then_refunds_once(monkeypatch, tmp_path):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        committed, release = asyncio.Event(), asyncio.Event()
        original_commit = aiosqlite.Connection.commit
        first = True
        async def commit(db):
            nonlocal first
            await original_commit(db)
            if first:
                first = False
                committed.set()
                await release.wait()
        monkeypatch.setattr(aiosqlite.Connection, "commit", commit)
        reservation = asyncio.create_task(billing.reserve(_call()))
        await committed.wait()
        reservation.cancel()
        await asyncio.sleep(0)
        assert not reservation.done(), "cancellation must drain the already committed transaction"
        reservation.cancel()  # Repeated pause/shutdown signals also drain safely.
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await reservation
        assert await billing.refund_reserved() == 0
        book, balance, steps = await _snapshot()
        assert book == (0, 0) and balance == 10000
        assert steps[0]["billing_status"] == "refunded"
    asyncio.run(scenario())


@pytest.mark.parametrize("window", ["before_ok", "after_ok", "after_settle"])
@pytest.mark.parametrize("bad_json_first", [False, True])
def test_cancel_between_settlement_and_step_ok_never_recharges(monkeypatch, tmp_path, window, bad_json_first):
    async def scenario():
        store, billing = await _book(monkeypatch, tmp_path)
        router = LLMRouter(store, billing=billing)
        calls, injected = [], False
        call_task = None
        async def provider(request):
            calls.append(request["step_key"])
            return ("bad-json" if bad_json_first and len(calls) == 1 else '{"ok":true}',
                    {"input_tokens": 100, "output_tokens": 100, "cached_tokens": 10})
        monkeypatch.setattr(router, "_single_real_call", provider)
        original_write = DbStepStore.write_step_on_connection
        async def write(db, username, novel_id, step_key, record):
            nonlocal injected
            if record["status"] == "ok" and window == "before_ok" and not injected:
                injected = True
                # Balance/step billing changes are made, but still uncommitted.
                row = await (await db.execute("SELECT billing_status,status FROM novel_steps")).fetchone()
                assert tuple(row) == ("settled", "interrupted")
                call_task.cancel()
            await original_write(db, username, novel_id, step_key, record)
            if record["status"] == "ok" and window == "after_ok" and not injected:
                injected = True
                call_task.cancel()
        monkeypatch.setattr(DbStepStore, "write_step_on_connection", staticmethod(write))
        original_settle = billing.settle
        async def settle(request, usage, **kwargs):
            nonlocal injected
            charged = await original_settle(request, usage, **kwargs)
            if kwargs.get("step_record") is not None and window == "after_settle" and not injected:
                injected = True
                call_task.cancel()
            return charged
        monkeypatch.setattr(billing, "settle", settle)
        call_task = asyncio.create_task(router.call(**_call()))
        with pytest.raises(asyncio.CancelledError):
            await call_task
        assert injected
        attempts = 2 if bad_json_first else 1
        book, balance, steps = await _snapshot()
        assert book == (attempts, 0) and balance == 10000 - attempts
        assert steps[0]["status"] == "ok"
        assert steps[0]["strawberries_charged"] == attempts
        resumed_store = await DbStepStore("billing-author", "billing-book", "token").initialize()
        resumed = LLMRouter(resumed_store, billing=NovelBilling("billing-author", "billing-book", "token"))
        monkeypatch.setattr(resumed, "_single_real_call", provider)
        assert await resumed.call(**_call()) == {"ok": True}
        assert len(calls) == attempts
        assert (await _snapshot())[:2] == (book, balance)
    asyncio.run(scenario())


@pytest.mark.parametrize("window", ["balance_debited", "reservation_written"])
def test_cancel_inside_reserve_transaction_preserves_conservation(monkeypatch, tmp_path, window):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        reached, release = asyncio.Event(), asyncio.Event()
        original_execute = aiosqlite.Connection.execute
        first = True
        async def execute(db, sql, parameters=None):
            nonlocal first
            cursor = await original_execute(db, sql, parameters)
            target = ("UPDATE users SET strawberry_balance=strawberry_balance-?" if window == "balance_debited"
                      else "INSERT INTO novel_steps")
            if first and sql.startswith(target):
                first = False
                reached.set()
                await release.wait()
            return cursor
        monkeypatch.setattr(aiosqlite.Connection, "execute", execute)
        reservation = asyncio.create_task(billing.reserve(_call()))
        await reached.wait()
        reservation.cancel()
        await asyncio.sleep(0)
        assert not reservation.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await reservation
        assert await billing.refund_reserved() == 0
        assert (await _snapshot())[:2] == ((0, 0), 10000)
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["settle", "refund", "refund_reserved"])
def test_settle_and_refund_commit_cancellation_drain_atomic_ledger(monkeypatch, tmp_path, operation):
    async def scenario():
        _, billing = await _book(monkeypatch, tmp_path)
        await billing.reserve(_call())
        committed, release = asyncio.Event(), asyncio.Event()
        original_commit = aiosqlite.Connection.commit
        first = True
        async def commit(db):
            nonlocal first
            await original_commit(db)
            if first:
                first = False
                committed.set()
                await release.wait()
        monkeypatch.setattr(aiosqlite.Connection, "commit", commit)
        if operation == "settle":
            pending = billing.settle(_call(), {"input_tokens": 100, "output_tokens": 100},
                                     step_record={"status": "ok", "model": _call()["model"],
                                                  "result": {"ok": True}, "raw_response": '{"ok":true}'})
        elif operation == "refund":
            pending = billing.refund(_call())
        else:
            pending = billing.refund_reserved()
        transaction = asyncio.create_task(pending)
        await committed.wait()
        transaction.cancel()
        await asyncio.sleep(0)
        assert not transaction.done()
        transaction.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await transaction
        charged = 1 if operation == "settle" else 0
        book, balance, steps = await _snapshot()
        assert book == (charged, 0) and balance == 10000 - charged
        assert steps[0]["billing_status"] == ("settled" if charged else "refunded")
        assert steps[0]["strawberries_charged"] == charged
        assert await billing.refund_reserved() == 0
        if charged:
            assert steps[0]["status"] == "ok"
    asyncio.run(scenario())


def test_step_ok_statement_failure_rolls_back_settlement_before_refund(monkeypatch, tmp_path):
    async def scenario():
        store, billing = await _book(monkeypatch, tmp_path)
        async with get_db() as db:
            await db.execute("CREATE TRIGGER fail_step_ok BEFORE UPDATE OF status ON novel_steps "
                             "WHEN NEW.status='ok' BEGIN SELECT RAISE(ABORT,'injected ok failure'); END")
            await db.commit()
        router = LLMRouter(store, billing=billing)
        async def provider(request):
            return '{"ok":true}', {"input_tokens": 100, "output_tokens": 100}
        monkeypatch.setattr(router, "_single_real_call", provider)
        with pytest.raises(aiosqlite.IntegrityError):
            await router.call(**_call())
        book, balance, steps = await _snapshot()
        assert book == (0, 0) and balance == 10000
        assert steps[0]["status"] == "interrupted"
        assert steps[0]["billing_status"] == "refunded"
        assert steps[0]["strawberries_charged"] == 0
    asyncio.run(scenario())
