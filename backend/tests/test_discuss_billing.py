"""讨论群计费与搜索固定扣费的离线测试（规格 4.8、4.11、场景 12）。

模型层用 FakeLLM；需要真实计费时替换 ``LLMRouter._single_real_call``，
不构造任何厂商客户端、不出网。
"""

import asyncio
import json
import threading

import aiosqlite
import pytest

import database
from discuss import billing as discuss_billing
from discuss import research
from discuss import runner as discuss_runner
from discuss import service as discuss_service
from discuss import store as discuss_store
from discuss.billing import DiscussBilling, DiscussBudgetExceeded
from discuss.runner import cancel_group, start_group
from discuss.store import DiscussStepStore
from novel.billing import InsufficientStrawberries, RunNoLongerActive, calculate_cost
from novel.byok_bridge import ByokBridge
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter


USER = "discuss_billing_author"
QWEN = "dashscope:qwen3.8-max"


def call(**changes):
    value = {
        "step_key": "r01/30-decide-host",
        "role": "host",
        "model": QWEN,
        "messages": [{"role": "user", "content": "x" * 1000}],
        "max_tokens": 1000,
    }
    value.update(changes)
    return value


async def prepare(monkeypatch, tmp_path, *, balance=10000, budget=500, status="running",
                  models=None, avatar=False, max_rounds=2):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    monkeypatch.delenv("FIONA_DISCUSS_PRICE_JSON", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / f"discuss-billing-{status}.db"))
    await database.init_db()
    await database.get_or_create_user(USER)
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("UPDATE users SET strawberry_balance=? WHERE username=?", (balance, USER))
        await db.commit()
    group_id = f"group-{status}-{budget}"
    config = {"avatar": avatar}
    if models is not None:
        config["models"] = models
    await discuss_store.create_group(
        USER, group_id=group_id, request="比较三款调研工具", materials="",
        budget_strawberries=budget, max_rounds=max_rounds, config=config,
        created_day="2026-01-01")
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "UPDATE discuss_groups SET status=?, run_token=? WHERE id=?",
            (status, "token-1" if status == "running" else None, group_id))
        await db.commit()
    return group_id


async def snapshot(group_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        group = dict(await (await db.execute(
            "SELECT * FROM discuss_groups WHERE id=?", (group_id,))).fetchone())
        balance = (await (await db.execute(
            "SELECT strawberry_balance FROM users WHERE username=?", (USER,))).fetchone())[0]
        steps = [dict(row) for row in await (await db.execute(
            "SELECT * FROM discuss_steps WHERE group_id=? ORDER BY step_key",
            (group_id,))).fetchall()]
    return group, balance, steps


async def messages_for(group_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(row) for row in await (await db.execute(
            "SELECT * FROM discuss_messages WHERE group_id=? ORDER BY id",
            (group_id,))).fetchall()]


async def wait_for_steps(group_id, predicate, timeout=10.0):
    """Poll the database until the background worker reaches the wanted step."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        _group, _balance, steps = await snapshot(group_id)
        if predicate(steps):
            return steps
        if loop.time() >= deadline:
            raise AssertionError("等待讨论群步骤状态超时")
        await asyncio.sleep(0.01)


def test_reserve_settle_and_refund_conserve_balance(monkeypatch, tmp_path):
    """场景 12：预扣后按用量结算，余额减少量等于群 spent，退款不重复扣。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500)
        billing = DiscussBilling(USER, group_id, "token-1")
        value = call()
        reserved = await billing.reserve(value)
        assert reserved == calculate_cost(QWEN, 1000, 1000)
        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == reserved
        assert group["spent_strawberries"] == 0
        assert balance == 10000 - reserved
        assert steps[0]["billing_status"] == "reserved"
        assert steps[0]["strawberries_reserved"] == reserved

        charged = await billing.settle(
            value, {"input_tokens": 1000, "output_tokens": 500, "cached_tokens": 0})
        assert charged == calculate_cost(QWEN, 1000, 500) == 5
        group, balance, steps = await snapshot(group_id)
        assert group["spent_strawberries"] == charged
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - charged
        assert steps[0]["billing_status"] == "settled"
        assert steps[0]["strawberries_charged"] == charged

        # 已结算的步骤再退款 / 再结算都不改变账。
        assert await billing.refund(value) == 0
        assert await billing.settle(value, {"input_tokens": 1, "output_tokens": 1}) == 0
        group, balance, _ = await snapshot(group_id)
        assert (group["spent_strawberries"], group["reserved_strawberries"], balance) == (
            charged, 0, 10000 - charged)

        # 另一次调用的预扣在退款后完全恢复。
        another = call(step_key="r01/40-draft-writer", role="writer")
        reserved = await billing.reserve(another)
        assert await billing.refund(another) == 0
        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - charged
        row = next(item for item in steps if item["step_key"] == "r01/40-draft-writer")
        assert row["billing_status"] == "refunded" and row["strawberries_charged"] == 0
        assert reserved > 0
    asyncio.run(scenario())


def test_budget_rule_counts_spent_plus_reserved(monkeypatch, tmp_path):
    """场景 12：spent + reserved + 本次预扣 > 预算时拒绝。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=16)
        billing = DiscussBilling(USER, group_id, "token-1")
        first = call(step_key="one")
        second = call(step_key="two")
        amount = calculate_cost(QWEN, 1000, 1000)  # 8
        assert amount == 8
        # 8 + 0 + 8 <= 16，第二次仍可预扣。
        await billing.reserve(first)
        await billing.reserve(second)
        with pytest.raises(DiscussBudgetExceeded):
            await billing.reserve(call(step_key="three"))
        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == 16
        assert balance == 10000 - 16
        assert len([row for row in steps if row["billing_status"] == "reserved"]) == 2
    asyncio.run(scenario())


def test_budget_rejects_first_call_and_leaves_no_reservation(monkeypatch, tmp_path):
    """场景 12：预算不够时抛 DiscussBudgetExceeded，不扣余额。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=2)
        billing = DiscussBilling(USER, group_id, "token-1")
        with pytest.raises(DiscussBudgetExceeded):
            await billing.reserve(call())
        group, balance, steps = await snapshot(group_id)
        assert group["budget_strawberries"] == 2
        assert group["reserved_strawberries"] == 0
        assert group["spent_strawberries"] == 0
        assert balance == 10000 and steps == []
    asyncio.run(scenario())


def test_insufficient_strawberries_leaves_no_reservation(monkeypatch, tmp_path):
    """场景 12：余额不够时抛 InsufficientStrawberries，不扣余额。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=0, budget=500)
        billing = DiscussBilling(USER, group_id, "token-1")
        with pytest.raises(InsufficientStrawberries):
            await billing.reserve(call())
        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == 0 and steps == []
        assert balance == 0
    asyncio.run(scenario())


def test_search_charges_fixed_and_refunds_failure(monkeypatch, tmp_path):
    """场景 12：搜索每次扣固定数，成功结算，失败全额退；成功结果不重复扣。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500)
        store = DiscussStepStore(USER, group_id, "token-1")
        billing = DiscussBilling(USER, group_id, "token-1")
        calls = []
        good = {
            "query": "市场规模",
            "data": {"findings": [{"fact": "市场增长 12%", "refs": [1]}]},
            "sources": [{"title": "来源甲", "url": "https://example.com/a",
                         "site_name": "站点", "index": 1}],
            "error": None,
        }

        def search_once(query, context):
            calls.append((query, context))
            return dict(good, query=query)

        monkeypatch.setattr(research, "search_once", search_once)
        first = await research.run_search(
            store, billing, "r01/11-search-market-1", "market", "市场规模", "目标")
        assert first["sources"][0]["url"] == "https://example.com/a"
        group, balance, steps = await snapshot(group_id)
        assert group["spent_strawberries"] == 2
        assert group["reserved_strawberries"] == 0
        assert balance == 9998
        row = next(item for item in steps if item["step_key"] == "r01/11-search-market-1")
        assert (row["status"], row["billing_status"], row["strawberries_charged"],
                row["strawberries_reserved"], row["model"]) == (
            "ok", "settled", 2, 2, "search")
        assert row["input_tokens"] == 0 and row["output_tokens"] == 0

        # 已成功的步骤直接复用缓存结果，不再扣费也不再搜索。
        cached = await research.run_search(
            store, billing, "r01/11-search-market-1", "market", "市场规模", "目标")
        assert cached == first
        assert len(calls) == 1
        group, balance, _ = await snapshot(group_id)
        assert (group["spent_strawberries"], balance) == (2, 9998)

        # 没有来源的一次搜索：记为 failed，固定扣费全额退回，且不缓存。
        def failed_search(query, context):
            calls.append((query, context))
            return {"query": query, "data": None, "sources": [], "error": None}

        monkeypatch.setattr(research, "search_once", failed_search)
        failed = await research.run_search(
            store, billing, "r01/11-search-market-2", "market", "查不到", "目标")
        assert failed["error"] == "no_sources" and failed["sources"] == []
        group, balance, steps = await snapshot(group_id)
        assert group["spent_strawberries"] == 2
        assert group["reserved_strawberries"] == 0
        assert balance == 9998
        row = next(item for item in steps if item["step_key"] == "r01/11-search-market-2")
        assert (row["status"], row["billing_status"], row["strawberries_charged"]) == (
            "failed", "refunded", 0)
        assert row["errors_json"] == '["no_sources"]'
        # 失败的搜索不缓存：再跑一次仍会调用搜索。
        await research.run_search(
            store, billing, "r01/11-search-market-2", "market", "查不到", "目标")
        assert len(calls) == 3
    asyncio.run(scenario())


def test_refund_reserved_returns_all_open_reservations(monkeypatch, tmp_path):
    """场景 12/13：任务停下时退还全部预扣，reserved 归零。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500)
        billing = DiscussBilling(USER, group_id, "token-1")
        await billing.reserve(call(step_key="one"))
        await billing.reserve_fixed("search-one", "market", 2)
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == 10
        assert balance == 10000 - 10
        refunded = await billing.refund_reserved()
        assert refunded == 10
        group, balance, _ = await snapshot(group_id)
        assert (group["reserved_strawberries"], group["spent_strawberries"], balance) == (
            0, 0, 10000)
    asyncio.run(scenario())


def passing_script(*, models=None, decisions=None):
    draft = "# 成果\n\n" + "结论有依据 [S1]，建议先做小范围试点。" * 30
    script = {
        "plan": {
            "title": "调研工具选择", "goal": "比较三款调研工具并给出建议。",
            "deliverable": {"kind": "report", "outline": ["结论", "对比", "建议"]},
            "criteria": ["列出价格", "给出明确建议", "说明适用前提"],
            "picks": [{"role": "market", "focus": "查市场"},
                      {"role": "competitor", "focus": "查竞品"}],
            "questions": [],
        },
        "queries": {"queries": ["问题一", "问题二"]},
        "note": {
            "note": "市场增长 12% [S1]，竞品定价差异明显 [S2]。",
            "key_points": [{"text": "市场增长 12% [S1]", "refs": ["S1"]},
                           {"text": "竞品定价差异明显 [S2]", "refs": ["S2"]}],
            "gaps": [],
        },
        "critique": {
            "objections": [{"target": "market", "type": "missing",
                            "problem": "样本不足", "suggestion": "补查小团队"}],
            "counter_view": "增长可能只覆盖大客户。",
        },
        "decide": decisions or {
            "responses": [{"id": "O1", "action": "accept", "reason": "先写"}],
            "note_responses": [], "decision": "draft", "assignments": [],
            "brief_for_writer": "按三节写。", "summary": "开始撰稿。",
        },
        "draft": draft,
        "accept": {
            "verdicts": [{"id": "C1", "pass": True, "evidence": "有价格"},
                         {"id": "C2", "pass": True, "evidence": "有建议"},
                         {"id": "C3", "pass": True, "evidence": "有前提"}],
            "citation_issues": [], "rework": [],
        },
    }
    return script


def fake_results(monkeypatch, fake):
    async def single_real_call(_router, request):
        raw, usage = await fake(request)
        return raw, usage, None

    monkeypatch.setattr(LLMRouter, "_single_real_call", single_real_call)

    def factory(store, username, group_id, run_token):
        router = LLMRouter(
            store, billing=DiscussBilling(username, group_id, run_token),
            byok_bridge=ByokBridge(username))
        router.retry_delay = 0
        return router

    monkeypatch.setattr("discuss.runner.router_factory", factory)


def search_fake(monkeypatch):
    def search_once(query, context):
        index = 1 if query == "问题一" else 2
        return {
            "query": query,
            "data": {"findings": [{"fact": f"事实{index}", "refs": [1]}]},
            "sources": [{"title": f"来源{index}", "url": f"https://example.com/{index}",
                         "site_name": "站点", "index": 1}],
            "error": None,
        }
    monkeypatch.setattr(research, "search_once", search_once)


async def run_group(group_id):
    task = await start_group(group_id, USER)
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), 10)


async def run_paid_flow(monkeypatch, tmp_path, *, fake=None, budget=5000,
                        balance=10000, models=None, dev_mode="0"):
    group_id = await prepare(monkeypatch, tmp_path, balance=balance, budget=budget,
                             status="planning", models=models)
    monkeypatch.setenv("DEV_MODE", dev_mode)
    fake = fake or FakeLLM(passing_script())
    fake_results(monkeypatch, fake)
    search_fake(monkeypatch)
    await run_group(group_id)
    async with aiosqlite.connect(database.DB_PATH) as db:
        status = (await (await db.execute(
            "SELECT status FROM discuss_groups WHERE id=?", (group_id,))).fetchone())[0]
    if status == "awaiting_start":
        await discuss_store.update_group(USER, group_id, status="running")
        await run_group(group_id)
    return group_id, fake


# ---------------------------------------------- 复核 M4 / 残留预扣 / M2 的付费场景

async def paid_planning(monkeypatch, tmp_path, *, fake=None, avatar=False, max_rounds=2,
                        balance=10000, budget=5000):
    """付费跑完立项（真实预扣与结算），停在 awaiting_start。"""
    group_id = await prepare(monkeypatch, tmp_path, balance=balance, budget=budget,
                             status="planning", avatar=avatar, max_rounds=max_rounds)
    fake = fake or FakeLLM(passing_script())
    fake_results(monkeypatch, fake)
    search_fake(monkeypatch)
    await run_group(group_id)
    group, current, _steps = await snapshot(group_id)
    assert group["status"] == "awaiting_start"
    assert group["reserved_strawberries"] == 0
    assert group["spent_strawberries"] > 0
    assert current == balance - group["spent_strawberries"]
    return group_id, fake


def block_paid_call(monkeypatch):
    """把付费调用器换成阻塞，让预扣在数据库里停下来。"""
    entered = asyncio.Event()
    gate = asyncio.Event()

    async def blocked(_router, _request):
        entered.set()
        await gate.wait()

    monkeypatch.setattr(LLMRouter, "_single_real_call", blocked)
    return entered, gate


async def start_paid_rounds(group_id):
    await discuss_store.update_group(USER, group_id, status="running")
    task = await start_group(group_id, USER)
    assert task is not None
    return task


async def stable_paid_snapshot(group_id, timeout=5.0):
    """Wait until a blocked paid call's reservation is stable and balance matches."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    previous = None
    while loop.time() < deadline:
        group, balance, steps = await snapshot(group_id)
        reserved = group["reserved_strawberries"]
        signature = (group["spent_strawberries"], reserved, balance)
        expected = 10000 - group["spent_strawberries"] - reserved
        if reserved > 0 and balance == expected:
            if signature == previous:
                return group, balance, steps
            previous = signature
        else:
            previous = None
        await asyncio.sleep(0.01)
    raise AssertionError("付费预扣状态未稳定")


async def wait_for_group(group_id, states, timeout=10.0):
    """等到目标状态，且后台任务已经完成收尾（退款、清令牌）。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        group, balance, steps = await snapshot(group_id)
        task = discuss_runner.TASKS.get(group_id)
        if group["status"] in states and (task is None or task.done()):
            return group, balance, steps
        if group["status"] in ("failed", "paused") and group["status"] not in states:
            raise AssertionError("讨论群意外停下：" + str(group))
        if loop.time() >= deadline:
            raise AssertionError("等待讨论群状态超时：" + str(group))
        await asyncio.sleep(0.01)


async def reserve_stale_step(group_id, step_key="r00/00-stale-reservation"):
    """造一条遗留预扣：先允许旧令牌预扣，再把群放回 paused 并清令牌。"""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "UPDATE discuss_groups SET run_token='token-1' WHERE id=? AND username=?",
            (group_id, USER))
        await db.commit()
    amount = await DiscussBilling(USER, group_id, "token-1").reserve(call(step_key=step_key))
    assert amount > 0
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "UPDATE discuss_groups SET status='paused',stop_reason='user',run_token=NULL "
            "WHERE id=? AND username=?", (group_id, USER))
        await db.commit()
    return amount


async def user_balance():
    async with aiosqlite.connect(database.DB_PATH) as db:
        return (await (await db.execute(
            "SELECT strawberry_balance FROM users WHERE username=?", (USER,))).fetchone())[0]


async def table_counts(group_id):
    counts = {}
    async with aiosqlite.connect(database.DB_PATH) as db:
        for table, column in (
                ("discuss_groups", "id"), ("discuss_messages", "group_id"),
                ("discuss_sources", "group_id"), ("discuss_steps", "group_id"),
                ("discuss_outputs", "group_id")):
            cursor = await db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (group_id,))
            counts[table] = (await cursor.fetchone())[0]
    return counts


def test_end_to_end_model_and_search_billing_conserves(monkeypatch, tmp_path):
    """场景 12：每步预扣后按用量结算；spent 等于各步扣费之和，余额差等于 spent。"""
    async def scenario():
        group_id, fake = await run_paid_flow(monkeypatch, tmp_path)
        group, balance, steps = await snapshot(group_id)
        assert group["status"] == "done"
        assert group["reserved_strawberries"] == 0
        charged = sum(row["strawberries_charged"] for row in steps)
        assert group["spent_strawberries"] == charged > 0
        assert balance == 10000 - charged
        assert all(row["billing_status"] == "settled" for row in steps)
        assert all(row["strawberries_charged"] <= row["strawberries_reserved"]
                   for row in steps)
        # 预扣按 max_tokens 估算，实际用量更少时差额退回。
        assert any(row["strawberries_charged"] < row["strawberries_reserved"]
                   for row in steps)
        search_rows = [row for row in steps if row["model"] == "search"]
        assert len(search_rows) == 4
        assert all(row["strawberries_charged"] == 2 for row in search_rows)
        model_rows = [row for row in steps if row["model"] != "search"]
        assert len(model_rows) == 9
        assert all(row["strawberries_charged"] >= 1 for row in model_rows)
        assert fake.call_count == len(model_rows)
    asyncio.run(scenario())


def test_budget_pause_via_runner(monkeypatch, tmp_path):
    """场景 12：预算不够时 runner 把群置为 paused/budget，预扣归零、余额不动。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=1,
                                 status="planning")
        fake_results(monkeypatch, FakeLLM(passing_script()))
        search_fake(monkeypatch)
        await run_group(group_id)
        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == ("paused", "budget")
        assert group["reserved_strawberries"] == 0
        assert group["run_token"] is None
        assert balance == 10000
        assert steps == []
    asyncio.run(scenario())


def test_insufficient_strawberries_pause_via_runner(monkeypatch, tmp_path):
    """场景 12：余额不够时 runner 把群置为 paused/insufficient_strawberries。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=0, budget=500,
                                 status="planning")
        fake_results(monkeypatch, FakeLLM(passing_script()))
        search_fake(monkeypatch)
        await run_group(group_id)
        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == (
            "paused", "insufficient_strawberries")
        assert group["reserved_strawberries"] == 0
        assert group["run_token"] is None
        assert balance == 0 and steps == []
    asyncio.run(scenario())


def test_byok_self_steps_are_free(monkeypatch, tmp_path):
    """场景 12：byok:self 的模型步骤不扣费（搜索另计固定费）。"""
    async def scenario():
        models = {"host": "byok:self", "critic": "byok:self", "writer": "byok:self",
                  "acceptor": "byok:self", "market": "byok:self", "competitor": "byok:self"}
        monkeypatch.setenv("FIONA_DISCUSS_SEARCH_STRAWBERRIES", "0")
        group_id, _fake = await run_paid_flow(monkeypatch, tmp_path, models=models)
        group, balance, steps = await snapshot(group_id)
        assert group["status"] == "done"
        assert group["spent_strawberries"] == 0
        assert balance == 10000
        model_rows = [row for row in steps if row["model"] != "search"]
        assert model_rows and all(row["strawberries_charged"] == 0
                                  for row in model_rows)
        assert all(row["billing_status"] == "free" for row in model_rows)
    asyncio.run(scenario())


def test_dev_mode_never_charges(monkeypatch, tmp_path):
    """场景 12：DEV_MODE=1 全程不扣费。"""
    async def scenario():
        group_id, _fake = await run_paid_flow(monkeypatch, tmp_path, dev_mode="1")
        group, balance, steps = await snapshot(group_id)
        assert group["status"] == "done"
        assert group["spent_strawberries"] == 0
        assert group["reserved_strawberries"] == 0
        assert balance == 10000
        assert steps and all(row["strawberries_charged"] == 0 for row in steps)
        assert all(row["billing_status"] == "free" for row in steps)
    asyncio.run(scenario())


def test_price_override_and_invalid_fallback(monkeypatch, caplog):
    """场景 12（4.11）：价目整表覆盖；非法时回落默认并只告警一次，不回显内容。"""
    monkeypatch.setattr(discuss_billing, "_warned_bad_price", False)
    prices = {
        "dashscope:qwen3.8-max": {"input": 2.0, "output": 4.0},
        "deepseek:deepseek-flash": {"input": 1.0, "output": 2.0},
        "ark:doubao-seed-2-1-pro-260915": {"input": 3.0, "output": 6.0},
    }
    monkeypatch.setenv("FIONA_DISCUSS_PRICE_JSON", json.dumps(prices))
    assert discuss_billing.get_prices() == prices
    assert calculate_cost(QWEN, 1000, 1000,
                          prices=discuss_billing.get_prices()) == 6

    monkeypatch.setenv("FIONA_DISCUSS_PRICE_JSON", '{"bad": true, "secret": "NO_ECHO"}')
    assert discuss_billing.get_prices() == discuss_billing.DEFAULT_PRICES
    assert discuss_billing.get_prices() == discuss_billing.DEFAULT_PRICES
    assert len(caplog.records) == 1
    assert "NO_ECHO" not in caplog.text
    assert calculate_cost(QWEN, 1000, 1000,
                          prices=discuss_billing.get_prices()) == 8


# ---------------------------------------------------------------- 返修 R1：T3、T9、T12

@pytest.mark.parametrize(("error", "stop_reason"), [
    pytest.param(InsufficientStrawberries(), "insufficient_strawberries", id="insufficient"),
    pytest.param(DiscussBudgetExceeded(), "budget", id="budget"),
])
def test_avatar_brief_billing_error_pauses_group(monkeypatch, tmp_path, error, stop_reason):
    """T3/E10：分身 brief 的余额与预算异常必须上抛，群按原因暂停，不被吞成 notice。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500,
                                 status="planning", avatar=True)
        script = passing_script()
        script["brief"] = error
        fake_results(monkeypatch, FakeLLM(script))
        search_fake(monkeypatch)
        await run_group(group_id)

        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == ("paused", stop_reason)
        assert group["status"] != "awaiting_start" and group["stop_reason"] is not None
        assert group["reserved_strawberries"] == 0
        assert group["run_token"] is None
        # 立项本身照常扣费并结算，说明这次是在真实计费模式下跑出来的。
        assert group["spent_strawberries"] > 0
        assert balance == 10000 - group["spent_strawberries"]

        brief_rows = [row for row in steps if row["step_key"] == "r00/02-brief-avatar"]
        assert len(brief_rows) == 1
        assert brief_rows[0]["billing_status"] == "refunded"
        assert brief_rows[0]["strawberries_charged"] == 0
        assert not [row for row in steps
                    if row["step_key"] == "r00/02-brief-avatar" and row["status"] == "ok"]

        messages = await messages_for(group_id)
        assert any(message["kind"] == "plan" for message in messages)
        assert not [message for message in messages
                    if message["content"] == "分身这次没能发言"]
        assert not [message for message in messages
                    if (message["step_key"] or "").endswith("-skip")]
        assert not [message for message in messages if message["kind"] == "brief"]
    asyncio.run(scenario())


def test_search_fixed_fee_respects_budget_without_reserving(monkeypatch, tmp_path):
    """T9/B5：计费打开时搜索固定扣费也查预算；超限时不扣余额、不留 reserved 行。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=100)
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE discuss_groups SET spent_strawberries=99 WHERE id=? AND username=?",
                (group_id, USER))
            await db.commit()
        billing = DiscussBilling(USER, group_id, "token-1")
        with pytest.raises(DiscussBudgetExceeded):
            await billing.reserve_fixed("r01/11-search-market-1", "market", 2)

        group, balance, steps = await snapshot(group_id)
        assert group["budget_strawberries"] == 100
        assert group["spent_strawberries"] == 99
        assert group["reserved_strawberries"] == 0
        assert balance == 10000
        assert not [row for row in steps if row["model"] == "search"]
        assert not [row for row in steps if row["billing_status"] == "reserved"]
    asyncio.run(scenario())


def test_search_budget_pause_via_runner(monkeypatch, tmp_path):
    """T9/B5：搜索固定预扣超预算时，runner 落 paused/budget，全程余额不动。"""
    async def scenario():
        monkeypatch.setenv("FIONA_DISCUSS_SEARCH_STRAWBERRIES", "2")
        free_models = {role: "byok:self" for role in (
            "host", "critic", "writer", "acceptor", "market", "competitor")}
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=1,
                                 status="planning", models=free_models)
        fake_results(monkeypatch, FakeLLM(passing_script()))
        search_fake(monkeypatch)
        await run_group(group_id)  # 立项，模型步骤免费
        await discuss_store.update_group(USER, group_id, status="running")
        await run_group(group_id)  # 调研：搜索固定费 2 > 预算 1

        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == ("paused", "budget")
        assert group["reserved_strawberries"] == 0
        assert group["run_token"] is None
        assert group["spent_strawberries"] == 0
        assert balance == 10000
        assert not [row for row in steps if row["model"] == "search"]
        assert not [row for row in steps if row["billing_status"] == "reserved"]
    asyncio.run(scenario())


def test_cancel_after_model_reservation_refunds_precharge(monkeypatch, tmp_path):
    """T12/N6：paid 模式下模型调用进行到一半被取消，预扣全部退回。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500,
                                 status="planning")
        started = asyncio.Event()

        async def blocked_call(_router, _request):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(LLMRouter, "_single_real_call", blocked_call)

        def factory(store, username, gid, run_token):
            router = LLMRouter(store, billing=DiscussBilling(username, gid, run_token),
                               byok_bridge=ByokBridge(username))
            router.retry_delay = 0
            return router

        monkeypatch.setattr("discuss.runner.router_factory", factory)
        task = await start_group(group_id, USER)
        assert task is not None
        try:
            await wait_for_steps(
                group_id,
                lambda rows: any(row["step_key"] == "r00/01-plan-host"
                                 and row["billing_status"] == "reserved" for row in rows))
            assert started.is_set()
            _group, balance_before, steps_before = await snapshot(group_id)
            reservation = next(row for row in steps_before
                               if row["step_key"] == "r00/01-plan-host")
            assert reservation["strawberries_reserved"] > 0
            assert balance_before == 10000 - reservation["strawberries_reserved"]
            await cancel_group(group_id, USER)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        group, balance, steps = await snapshot(group_id)
        assert group["status"] == "planning"
        assert group["reserved_strawberries"] == 0
        assert group["spent_strawberries"] == 0
        assert group["run_token"] is None
        assert balance == 10000
        assert not [row for row in steps if row["billing_status"] == "reserved"]
        row = next(row for row in steps if row["step_key"] == "r00/01-plan-host")
        assert (row["billing_status"], row["status"], row["strawberries_charged"]) == (
            "refunded", "interrupted", 0)
    asyncio.run(scenario())


def test_cancel_after_search_reservation_refunds_all_precharges(monkeypatch, tmp_path):
    """T12/N6：搜索固定预扣在取消时只能由 runner 退还，必须清零且余额复原。

    模型调用由 ``LLMRouter._attempt`` 自己的 finally 退还，区分不出 runner 的
    ``cancel_group`` / ``_cleanup`` 漏退款；搜索预扣在 ``run_search`` 里没有
    同样的 finally，取消后只能靠 runner 的 ``refund_reserved``，因此本用例能
    杀死「取消任务时不退还预扣」的变异。
    """
    async def scenario():
        monkeypatch.setenv("FIONA_DISCUSS_SEARCH_STRAWBERRIES", "2")
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500,
                                 status="planning")
        fake_results(monkeypatch, FakeLLM(passing_script()))
        gate = threading.Event()

        def blocked_search(query, context):
            gate.wait(30)
            index = 1 if query == "问题一" else 2
            return {
                "query": query,
                "data": {"findings": [{"fact": f"事实{index}", "refs": [1]}]},
                "sources": [{"title": f"来源{index}",
                             "url": f"https://example.com/{index}",
                             "site_name": "站点", "index": 1}],
                "error": None,
            }

        monkeypatch.setattr(research, "search_once", blocked_search)
        task = None
        try:
            await run_group(group_id)  # 立项：plan 步骤先结算
            await discuss_store.update_group(USER, group_id, status="running")
            task = await start_group(group_id, USER)
            assert task is not None
            await wait_for_steps(
                group_id,
                lambda rows: len([row for row in rows
                                  if row["model"] == "search"
                                  and row["billing_status"] == "reserved"]) >= 4)
            group_before, balance_before, steps_before = await snapshot(group_id)
            reserved_keys = {row["step_key"] for row in steps_before
                             if row["billing_status"] == "reserved"}
            reserved_total = sum(row["strawberries_reserved"] for row in steps_before
                                 if row["billing_status"] == "reserved")
            assert len(reserved_keys) == 4
            assert reserved_total == group_before["reserved_strawberries"] == 8
            assert balance_before == (10000 - group_before["spent_strawberries"]
                                      - reserved_total)
            await cancel_group(group_id, USER)
        finally:
            gate.set()
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == 0
        assert group["run_token"] is None
        assert group["spent_strawberries"] == group_before["spent_strawberries"]
        assert group["status"] == "running"  # cancel 不改状态，只退预扣、清令牌
        assert balance == balance_before + reserved_total
        assert balance == 10000 - group["spent_strawberries"]
        assert not [row for row in steps if row["billing_status"] == "reserved"]
        for row in steps:
            if row["step_key"] in reserved_keys:
                assert row["billing_status"] == "refunded"
                assert row["strawberries_charged"] == 0
                assert row["strawberries_reserved"] == 2
    asyncio.run(scenario())


# ------------------------------------------------ 复核 M4：付费调用阻塞时暂停 / 删群

def test_pause_while_paid_call_blocked_refunds_reservation(monkeypatch, tmp_path):
    """M4(a)/X25：付费调用阻塞时 pause，接口返回后预扣已退、余额等于初始值减 spent。"""
    async def scenario():
        group_id, _fake = await paid_planning(monkeypatch, tmp_path)
        entered, gate = block_paid_call(monkeypatch)
        task = await start_paid_rounds(group_id)
        try:
            await asyncio.wait_for(entered.wait(), 5)
            steps = await wait_for_steps(
                group_id,
                lambda rows: any(row["billing_status"] == "reserved" for row in rows))
            assert [row for row in steps if row["billing_status"] == "reserved"]
            group_before, balance_before, _ = await stable_paid_snapshot(group_id)
            assert group_before["reserved_strawberries"] > 0
            assert group_before["spent_strawberries"] > 0
            assert balance_before == (10000 - group_before["spent_strawberries"]
                                      - group_before["reserved_strawberries"])
            spent_before = group_before["spent_strawberries"]

            result = await discuss_service.pause(USER, group_id)
            assert (result["status"], result["stop_reason"]) == ("paused", "user")
            # 暂停接口返回时后台任务必须已经取消并收尾，不能还在跑。
            assert task.done()
        finally:
            gate.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == ("paused", "user")
        assert group["run_token"] is None
        assert group["reserved_strawberries"] == 0
        assert group["spent_strawberries"] == spent_before
        assert balance == 10000 - spent_before
        assert not [row for row in steps if row["billing_status"] == "reserved"]
    asyncio.run(scenario())


def test_delete_while_paid_call_blocked_refunds_reservation(monkeypatch, tmp_path):
    """M4(b)/X26：付费调用阻塞时 delete，余额等于初始值减删群前的 spent。"""
    async def scenario():
        group_id, _fake = await paid_planning(monkeypatch, tmp_path)
        entered, gate = block_paid_call(monkeypatch)
        task = await start_paid_rounds(group_id)
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await wait_for_steps(
                group_id,
                lambda rows: any(row["billing_status"] == "reserved" for row in rows))
            group_before, balance_before, _ = await stable_paid_snapshot(group_id)
            spent_before = group_before["spent_strawberries"]
            assert group_before["reserved_strawberries"] > 0
            assert spent_before > 0
            assert balance_before == (10000 - spent_before
                                      - group_before["reserved_strawberries"])

            result = await discuss_service.delete(USER, group_id)
            assert result == {"deleted": True}
            # 删群接口返回时后台任务必须已经取消，不能留下在途预扣。
            assert task.done()
            assert group_id not in discuss_runner.TASKS
        finally:
            gate.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        assert await user_balance() == 10000 - spent_before
        counts = await table_counts(group_id)
        assert all(count == 0 for count in counts.values()), counts
    asyncio.run(scenario())


# ------------------------------------------------------ 复核 M4：付费续跑复用已结算步骤

def test_paid_continue_reuses_ok_steps_and_charges_only_new_spend(monkeypatch, tmp_path):
    """M4(c)/X1：awaiting_user 后 continue，已 ok 的付费步骤不再调用模型。"""
    async def scenario():
        script = passing_script()
        script["accept"] = {
            "verdicts": [{"id": "C1", "pass": False, "evidence": "缺少价格"},
                         {"id": "C2", "pass": True, "evidence": "有建议"},
                         {"id": "C3", "pass": True, "evidence": "有前提"}],
            "citation_issues": [], "rework": ["补上价格"],
        }
        script["rework"] = {
            "assignments": [], "note_responses": [],
            "brief_for_writer": "按验收意见补上价格", "summary": "返工",
        }
        fake = FakeLLM(script)
        group_id, _ = await paid_planning(
            monkeypatch, tmp_path, fake=fake, max_rounds=1)
        await discuss_store.update_group(USER, group_id, status="running")
        await run_group(group_id)

        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == (
            "awaiting_user", "rounds_exhausted")
        ok_keys = {row["step_key"] for row in steps
                   if row["status"] == "ok" and row["model"] != "search"}
        assert ok_keys
        assert "r01/40-draft-writer" in ok_keys
        spent_before = group["spent_strawberries"]
        assert spent_before > 0
        assert balance == 10000 - spent_before

        calls_before = len(fake.calls)
        await discuss_service.continue_group(
            USER, group_id, discuss_service.ContinueGroup(add_rounds=1))
        group_after, balance_after, steps_after = await wait_for_group(
            group_id, ("awaiting_user", "done"))

        # 续跑只重放缓存；已 ok 的步骤键不能重新出现在模型调用里。
        new_keys = {item.get("step_key") for item in fake.calls[calls_before:]}
        assert not (new_keys & ok_keys)
        assert group_after["max_rounds"] == 2
        assert group_after["round"] == 2
        assert [row for row in steps_after if row["step_key"].startswith("r02/")]
        assert group_after["spent_strawberries"] > spent_before
        # 余额减少量恰好等于群 spent，续跑没有重复扣费。
        assert balance_after == 10000 - group_after["spent_strawberries"]
        assert (10000 - balance_after) == group_after["spent_strawberries"]
    asyncio.run(scenario())


# ---------------------------------------------------------- 复核 M4：旧令牌计费守卫

def test_stale_token_cannot_reserve_or_reserve_fixed(monkeypatch, tmp_path):
    """M4(d)/X4：旧令牌的 reserve 与 reserve_fixed 都抛 RunNoLongerActive，账和步骤不变。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500,
                                 status="running")
        billing = DiscussBilling(USER, group_id, "old-token")
        before_group, before_balance, before_steps = await snapshot(group_id)
        with pytest.raises(RunNoLongerActive):
            await billing.reserve(call())
        with pytest.raises(RunNoLongerActive):
            await billing.reserve_fixed("r01/11-search-market-1", "market", 2)

        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == before_group["reserved_strawberries"] == 0
        assert group["spent_strawberries"] == before_group["spent_strawberries"] == 0
        assert balance == before_balance == 10000
        assert steps == before_steps == []
    asyncio.run(scenario())


# ---------------------------------------------------- 复核 v1.2 第 4 条：残留预扣

def test_resume_refunds_stale_reservation_before_replanning(monkeypatch, tmp_path):
    """F-resume：启动前先退残留预扣，旧步骤变 refunded，最终余额 = 初始值 - spent。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=5000,
                                 status="paused")
        stale = await reserve_stale_step(group_id)
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == stale > 0
        assert balance == 10000 - stale

        fake_results(monkeypatch, FakeLLM(passing_script()))
        search_fake(monkeypatch)

        observed = {}
        original_start = discuss_runner.start_group

        async def observed_start(gid, username, **kwargs):
            seen_group, seen_balance, seen_steps = await snapshot(gid)
            observed["reserved"] = seen_group["reserved_strawberries"]
            observed["balance"] = seen_balance
            observed["stale"] = next(
                item for item in seen_steps
                if item["step_key"] == "r00/00-stale-reservation")
            return await original_start(gid, username, **kwargs)

        monkeypatch.setattr(discuss_runner, "start_group", observed_start)
        await discuss_service.resume(USER, group_id, discuss_service.ResumeGroup())
        group, balance, steps = await wait_for_group(group_id, ("awaiting_start",))

        # 必须在启动后台任务之前退款；不能等任务跑完后的收尾再退。
        assert observed["reserved"] == 0
        assert observed["balance"] == 10000
        assert (observed["stale"]["status"], observed["stale"]["billing_status"]) == (
            "interrupted", "refunded")

        row = next(item for item in steps
                   if item["step_key"] == "r00/00-stale-reservation")
        assert (row["status"], row["billing_status"],
                row["strawberries_charged"]) == ("interrupted", "refunded", 0)
        assert group["reserved_strawberries"] == 0
        assert group["run_token"] is None
        assert group["spent_strawberries"] > 0
        assert balance == 10000 - group["spent_strawberries"]
        assert not [item for item in steps if item["step_key"].startswith("r01/")]
    asyncio.run(scenario())


def test_delete_refunds_stale_reservation_when_cancel_is_noop(monkeypatch, tmp_path):
    """F-delete：绕过 cancel_group 的退款，证明删群事务本身会退预扣并清五张表。"""
    async def scenario():
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=5000,
                                 status="paused")
        stale = await reserve_stale_step(group_id)
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == stale > 0
        assert balance == 10000 - stale

        cancelled = []

        async def no_cancel(gid, username):
            cancelled.append((gid, username))

        monkeypatch.setattr(discuss_runner, "cancel_group", no_cancel)
        result = await discuss_service.delete(USER, group_id)
        assert result == {"deleted": True}
        assert cancelled == [(group_id, USER)]
        # 预扣恢复到扣款之前；若删群事务没有退款，这里会少 stale 颗。
        assert await user_balance() == 10000
        counts = await table_counts(group_id)
        assert all(count == 0 for count in counts.values()), counts
    asyncio.run(scenario())


# ------------------------------------------- v1.2 第 1 条：付费立项 brief 失败后继续

def test_paid_resume_after_brief_insufficient_funds_waits_for_start(monkeypatch, tmp_path):
    """M2-paid/X40：方案已写入但没收工，余额不足暂停后继续必须回到 awaiting_start。"""
    async def scenario():
        brief = {"context": "主人关心成本与落地", "answers": [], "ask_owner": []}
        script = passing_script()
        script["brief"] = [InsufficientStrawberries(), brief]
        fake = FakeLLM(script)
        group_id = await prepare(monkeypatch, tmp_path, balance=10000, budget=500,
                                 status="planning", avatar=True, max_rounds=2)
        fake_results(monkeypatch, fake)
        search_fake(monkeypatch)
        await run_group(group_id)

        group, balance, steps = await snapshot(group_id)
        assert (group["status"], group["stop_reason"]) == (
            "paused", "insufficient_strawberries")
        assert group["plan_revision"] == 1
        assert group["round"] == 0
        assert json.loads(group["plan_json"])["title"] == "调研工具选择"
        assert group["reserved_strawberries"] == 0
        spent_before = group["spent_strawberries"]
        assert spent_before > 0
        assert balance == 10000 - spent_before

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE users SET strawberry_balance=strawberry_balance+1000 "
                "WHERE username=?", (USER,))
            await db.commit()

        await discuss_service.resume(USER, group_id, discuss_service.ResumeGroup())
        group, balance, steps = await wait_for_group(group_id, ("awaiting_start",))

        assert group["round"] == 0
        assert group["plan_revision"] == 1
        assert group["run_token"] is None
        assert group["reserved_strawberries"] == 0
        # 续跑只回到等开工，不能跳过作者开工去跑付费轮次。
        assert not [row for row in steps if row["step_key"].startswith("r01/")]
        messages = await messages_for(group_id)
        assert not [message for message in messages if (message["round"] or 0) >= 1]
        brief_calls = [item for item in fake.calls if item.get("task") == "brief"]
        skip_notices = [message for message in messages
                        if (message["step_key"] or "").endswith("-skip")]
        assert len(brief_calls) >= 2 or skip_notices
        assert balance == 11000 - group["spent_strawberries"]
        assert (11000 - balance) == group["spent_strawberries"]
    asyncio.run(scenario())


# ── 复核门禁补单：V7a/V7c 开工与追加轮数前的残留预扣退款 ───────

async def reserve_stale_step_for_status(group_id, status):
    """Leave one reserved step, then put the group into the wanted status."""
    amount = await reserve_stale_step(group_id)
    await discuss_store.update_group(
        USER, group_id, status=status, stop_reason=(
            "rounds_exhausted" if status == "awaiting_user" else None))
    return amount


def test_start_refunds_stale_reservation_before_launch(monkeypatch, tmp_path):
    """V7a：开工前先退残留预扣；最终余额减少量等于 spent。"""
    async def scenario():
        group_id, _fake = await paid_planning(monkeypatch, tmp_path, balance=10000)
        baseline, _, _ = await snapshot(group_id)
        spent_before = baseline["spent_strawberries"]
        stale = await reserve_stale_step_for_status(group_id, "awaiting_start")
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == stale > 0
        assert balance == 10000 - stale - group["spent_strawberries"]

        observed = {}
        original_start = discuss_runner.start_group

        async def observed_start(gid, username, **kwargs):
            seen_group, seen_balance, seen_steps = await snapshot(gid)
            observed["reserved"] = seen_group["reserved_strawberries"]
            observed["balance"] = seen_balance
            observed["stale"] = next(
                row for row in seen_steps
                if row["step_key"] == "r00/00-stale-reservation")
            return await original_start(gid, username, **kwargs)

        monkeypatch.setattr(discuss_runner, "start_group", observed_start)
        current = await discuss_store.get_group(USER, group_id)
        await discuss_service.start(
            USER, group_id, discuss_service.StartGroup(
                expected_revision=current["plan_revision"]))
        group, balance, steps = await wait_for_group(group_id, ("done", "awaiting_user"))

        assert observed["reserved"] == 0
        assert observed["balance"] == 10000 - spent_before
        assert (observed["stale"]["status"], observed["stale"]["billing_status"]) == (
            "interrupted", "refunded")
        row = next(item for item in steps
                   if item["step_key"] == "r00/00-stale-reservation")
        assert (row["status"], row["billing_status"],
                row["strawberries_charged"]) == ("interrupted", "refunded", 0)
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - group["spent_strawberries"]
    asyncio.run(scenario())


def test_continue_refunds_stale_reservation_before_launch(monkeypatch, tmp_path):
    """V7c：追加轮数前先退残留预扣；最终余额减少量等于 spent。"""
    async def scenario():
        group_id, _fake = await paid_planning(monkeypatch, tmp_path, balance=10000)
        baseline, _, _ = await snapshot(group_id)
        spent_before = baseline["spent_strawberries"]
        stale = await reserve_stale_step_for_status(group_id, "awaiting_user")
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == stale > 0
        assert balance == 10000 - stale - group["spent_strawberries"]

        observed = {}
        original_start = discuss_runner.start_group

        async def observed_start(gid, username, **kwargs):
            seen_group, seen_balance, seen_steps = await snapshot(gid)
            observed["reserved"] = seen_group["reserved_strawberries"]
            observed["balance"] = seen_balance
            observed["stale"] = next(
                row for row in seen_steps
                if row["step_key"] == "r00/00-stale-reservation")
            return await original_start(gid, username, **kwargs)

        monkeypatch.setattr(discuss_runner, "start_group", observed_start)
        await discuss_service.continue_group(
            USER, group_id, discuss_service.ContinueGroup(add_rounds=1))
        group, balance, steps = await wait_for_group(group_id, ("done", "awaiting_user"))

        assert observed["reserved"] == 0
        assert observed["balance"] == 10000 - spent_before
        assert (observed["stale"]["status"], observed["stale"]["billing_status"]) == (
            "interrupted", "refunded")
        row = next(item for item in steps
                   if item["step_key"] == "r00/00-stale-reservation")
        assert (row["status"], row["billing_status"],
                row["strawberries_charged"]) == ("interrupted", "refunded", 0)
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - group["spent_strawberries"]
    asyncio.run(scenario())


# ── 复核第 2 轮：accept/close 也退残留预扣 ───────────────────

def test_accept_refunds_stale_reservation(monkeypatch, tmp_path):
    """v1.2 第 4 条：accept 改状态后清掉残留预扣，余额回到 spent 差。"""
    async def scenario():
        group_id, _fake = await paid_planning(monkeypatch, tmp_path, balance=10000)
        base, _, _ = await snapshot(group_id)
        spent_before = base["spent_strawberries"]
        stale = await reserve_stale_step(group_id)
        await discuss_store.update_group(
            USER, group_id, status="paused", stop_reason="user", output_version=1)
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == stale > 0
        assert balance == 10000 - stale - spent_before

        result = await discuss_service.accept(USER, group_id)
        assert (result["status"], result["stop_reason"]) == ("done", "accepted_by_user")
        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - spent_before
        row = next(item for item in steps
                   if item["step_key"] == "r00/00-stale-reservation")
        assert (row["status"], row["billing_status"],
                row["strawberries_charged"]) == ("interrupted", "refunded", 0)
    asyncio.run(scenario())


def test_close_refunds_stale_reservation(monkeypatch, tmp_path):
    """v1.2 第 4 条：close 改状态后清掉残留预扣，余额回到 spent 差。"""
    async def scenario():
        group_id, _fake = await paid_planning(monkeypatch, tmp_path, balance=10000)
        base, _, _ = await snapshot(group_id)
        spent_before = base["spent_strawberries"]
        stale = await reserve_stale_step(group_id)
        group, balance, _ = await snapshot(group_id)
        assert group["reserved_strawberries"] == stale > 0
        assert balance == 10000 - stale - spent_before

        result = await discuss_service.close(USER, group_id)
        assert (result["status"], result["stop_reason"]) == ("closed", "user")
        group, balance, steps = await snapshot(group_id)
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - spent_before
        row = next(item for item in steps
                   if item["step_key"] == "r00/00-stale-reservation")
        assert (row["status"], row["billing_status"],
                row["strawberries_charged"]) == ("interrupted", "refunded", 0)
    asyncio.run(scenario())


def test_pause_during_paid_avatar_memory_error_keeps_spent(monkeypatch, tmp_path):
    """M5 付费版：view 读记忆报错时暂停仍生效，暂停后不再结算新步骤。"""
    async def scenario():
        group_id, _fake = await paid_planning(
            monkeypatch, tmp_path, avatar=True, balance=10000)
        await discuss_store.update_group(USER, group_id, status="running")

        import agent_store
        import sqlite3
        entered, release = asyncio.Event(), asyncio.Event()
        original = agent_store.get_memory_snapshot
        fired = [False]

        async def failing(username, conversation_id=None):
            if not fired[0]:
                fired[0] = True
                entered.set()
                await release.wait()
                raise sqlite3.OperationalError("simulated memory read failure")
            return await original(username, conversation_id)

        monkeypatch.setattr(agent_store, "get_memory_snapshot", failing)
        task = await start_group(group_id, USER)
        try:
            await asyncio.wait_for(entered.wait(), 5)
            group_at_block, _, _ = await snapshot(group_id)
            spent_at_block = group_at_block["spent_strawberries"]
            pause_task = asyncio.create_task(discuss_service.pause(USER, group_id))
            await asyncio.sleep(0.05)
            release.set()
            result = await pause_task
            assert (result["status"], result["stop_reason"]) == ("paused", "user")
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        group, balance, steps = await snapshot(group_id)
        assert group["status"] == "paused"
        assert group["spent_strawberries"] == spent_at_block
        assert group["reserved_strawberries"] == 0
        assert balance == 10000 - spent_at_block
    asyncio.run(scenario())
