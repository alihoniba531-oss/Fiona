"""WO3a 离线接口、事务预检、预算、恢复和独立修正账本。"""
import asyncio
from datetime import datetime, timezone
import json
import sqlite3
from types import SimpleNamespace

import pytest

import auth
import database
from studio import brain_jobs, pricing, spend, store

PYTHON = "/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def owner(client, monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "brain-author,brain-other")
    monkeypatch.setenv("DEV_MODE", "1")
    user = run(database.get_or_create_user("brain-author"))
    run(database.get_or_create_user("brain-other"))
    return {"Authorization": "Bearer " + auth.create_token("brain-author", user["session_version"])}


@pytest.fixture
def options(monkeypatch):
    import studio.brain as brain
    async def available(username):
        return [{"id": p, "label": p, "available": True,
                 "model": {"claude": "claude-sonnet-5-5", "qwen": "qwen3.8-max", "deepseek": "deepseek-v4-pro"}[p]}
                for p in brain_jobs.PROVIDERS]
    monkeypatch.setattr(brain, "provider_options", available)
    monkeypatch.setattr(brain_jobs, "_schedule", lambda jid: None)
    return available


def project(client, owner):
    response = client.post("/studio/projects", headers=owner, json={"title": "试读"})
    assert response.status_code == 201, response.text
    return response.json()


def body(**kwargs):
    return {"text": "阿宁推开旧门，手里拿着一封信。", "tasks": ["read_through"], "providers": "current", **kwargs}


def test_quote_does_not_enqueue_and_all_unavailable_is_atomic(client, owner, options, monkeypatch):
    import studio.brain as brain
    p = project(client, owner)
    endpoint = f"/studio/projects/{p['id']}/brain"
    quote = client.post(endpoint + "/quote", headers=owner, json=body())
    assert quote.status_code == 200
    assert quote.json()["totals"]["USD"] > 0
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM studio_jobs WHERE project_id=?", (p["id"],)).fetchone()[0] == 0
    async def unavailable(username):
        rows = await options(username)
        rows[0].update(available=False, reason="BYOK 未启用")
        return rows
    monkeypatch.setattr(brain, "provider_options", unavailable)
    response = client.post(endpoint + "/trial", headers=owner, json=body(providers="all"))
    assert response.status_code == 409 and "BYOK 未启用" in response.text
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM studio_jobs WHERE project_id=?", (p["id"],)).fetchone()[0] == 0


def test_switch_group_owner_and_access(client, owner, options):
    p = project(client, owner)
    assert p["brain_provider"] == "claude"
    url = f"/studio/projects/{p['id']}"
    changed = client.patch(url, headers=owner, json={"brain_provider": "qwen"})
    assert changed.status_code == 200 and changed.json()["brain_provider"] == "qwen"
    response = client.post(url + "/brain/trial", headers=owner, json=body(providers="all"))
    assert response.status_code == 200
    result = response.json()
    assert {j["provider"] for j in result["jobs"]} == set(brain_jobs.PROVIDERS)
    assert all(j["kind"] == "brain" and j["group_id"] == result["group_id"] for j in result["jobs"])
    group_url = url + "/brain/groups/" + result["group_id"]
    assert len(client.get(group_url, headers=owner).json()["jobs"]) == 3
    user = run(database.get_or_create_user("brain-other"))
    other = {"Authorization": "Bearer " + auth.create_token("brain-other", user["session_version"])}
    assert client.get(group_url, headers=other).status_code == 404
    assert client.patch(url, headers=other, json={"brain_provider": "deepseek"}).status_code == 404
    access = client.get("/studio/access", headers=owner).json()
    assert access["caps"]["brain_monthly_usd"] == 40
    assert access["caps"]["brain_month_used_usd"] > 0
    assert client.get(url + "/jobs", headers=owner).json() == []


@pytest.mark.parametrize("provider,setting", [("claude", "FIONA_STUDIO_BRAIN_MONTHLY_USD"), ("qwen", "FIONA_STUDIO_DAILY_CNY")])
def test_dev_mode_budget_blocks_before_jobs_or_requests(client, owner, options, monkeypatch, provider, setting):
    p = project(client, owner)
    client.patch(f"/studio/projects/{p['id']}", headers=owner, json={"brain_provider": provider})
    monkeypatch.setenv(setting, "0.00000001")
    response = client.post(f"/studio/projects/{p['id']}/brain/trial", headers=owner, json=body())
    assert response.status_code == 409
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM studio_jobs WHERE project_id=?", (p["id"],)).fetchone()[0] == 0


def test_prices_cache_unknown_override_and_month_boundary(monkeypatch):
    cost = pricing.brain_actual_cost("claude-opus-5-5", {"input_tokens": 100, "output_tokens": 50,
              "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 20})
    assert cost == {"currency": "USD", "amount": .00170}
    with pytest.raises(Exception, match="409"):
        pricing.brain_price("claude-unknown")
    monkeypatch.setenv("FIONA_STUDIO_PRICE_CLAUDE_UNKNOWN", '{"input":1,"output":2,"cache_read":0.1}')
    assert pricing.estimate_brain("claude-unknown", 100, 200)["amount"] == .0005875
    assert spend.shanghai_month("2026-10-31T15:59:59+00:00") == "2026-10"
    assert spend.shanghai_month("2026-10-31T16:00:00+00:00") == "2026-11"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "bad"])
def test_monthly_setting_invalid_warns_once(monkeypatch, capsys, value):
    from studio import config
    config._INVALID_SETTINGS_WARNED.discard("FIONA_STUDIO_BRAIN_MONTHLY_USD")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", value)
    assert config.get_settings().brain_monthly_usd == 40
    assert config.get_settings().brain_monthly_usd == 40
    assert capsys.readouterr().out.count("FIONA_STUDIO_BRAIN_MONTHLY_USD") == 1


def test_migration_only_adds_columns_and_preserves_old_check(tmp_path):
    async def check():
        import aiosqlite
        async with aiosqlite.connect(tmp_path / "old.db") as db:
            await db.execute("CREATE TABLE studio_projects(id TEXT PRIMARY KEY,owner TEXT)")
            await db.execute("""CREATE TABLE studio_jobs(id TEXT PRIMARY KEY,owner TEXT,project_id TEXT,
                provider TEXT CHECK(provider IN ('wan','seedance')))""")
            before = (await (await db.execute("SELECT sql FROM sqlite_master WHERE name='studio_jobs'")).fetchone())[0]
            await store.migrate_schema(db)
            await store.migrate_schema(db)
            after = (await (await db.execute("SELECT sql FROM sqlite_master WHERE name='studio_jobs'")).fetchone())[0]
            assert "CHECK(provider IN ('wan','seedance'))" in before and "CHECK(provider IN ('wan','seedance'))" in after
            columns = {r[1] for r in await (await db.execute("PRAGMA table_info(studio_jobs)")).fetchall()}
            assert {"task", "result_json", "warnings_json", "currency", "input_chars", "group_id"} <= columns
    run(check())


def _run_job(client, owner, options, monkeypatch, replies):
    import studio.brain as brain
    p = project(client, owner)
    result = client.post(f"/studio/projects/{p['id']}/brain/trial", headers=owner, json=body()).json()
    jid = result["jobs"][0]["id"]
    calls = []
    class Adapter:
        model = "claude-sonnet-5-5"
        async def call(self, task, inputs, images=None, repair=None):
            calls.append(repair)
            item = replies[min(len(calls) - 1, len(replies) - 1)]
            if isinstance(item, Exception):
                raise item
            return brain.BrainReply(text=json.dumps(item), usage={"input_tokens": 100, "output_tokens": 50,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}, model=self.model,
                stop_reason="end_turn", latency_s=.1)
    async def adapter(*args, **kwargs):
        return Adapter()
    monkeypatch.setattr(brain, "get_provider", adapter)
    run(brain_jobs._background(jid))
    return run(brain_jobs.group(p["id"], "brain-author", result["group_id"])), calls


GOOD = {"logline": "旧信归来", "synopsis": "阿宁推门。", "genre": "剧情", "tone": "克制", "theme": "归来",
        "pacing": "慢", "adaptation_risks": []}


def test_repair_two_independent_bills_and_no_third(client, owner, options, monkeypatch):
    group, calls = _run_job(client, owner, options, monkeypatch, [{}, GOOD])
    assert len(calls) == 2 and calls[0] is None and calls[1]
    assert len(group["jobs"]) == 2
    assert [job["status"] for job in group["jobs"]] == ["invalid_output", "succeeded"]
    assert group["jobs"][1]["repaired"] is True
    assert group["totals"]["USD"] == .0014
    group, calls = _run_job(client, owner, options, monkeypatch, [{}, {}])
    assert len(calls) == 2 and all(j["status"] == "invalid_output" for j in group["jobs"])


def test_uncertain_reserve_release_and_recovery_no_post(client, owner, options, monkeypatch):
    import studio.brain as brain
    group, calls = _run_job(client, owner, options, monkeypatch,
                             [brain.BrainProviderError("uncertain", "timeout", "可能已扣费")])
    job = group["jobs"][0]
    assert job["status"] == "uncertain" and float(job["reserved_amount"]) > 0
    assert client.post(f"/studio/jobs/{job['id']}/link-task", headers=owner, json={"task_id": "x"}).status_code == 409
    released = client.post(f"/studio/jobs/{job['id']}/release", headers=owner, json={"not_charged": True})
    assert released.status_code == 200 and released.json()["cost"]["amount"] == 0
    p = project(client, owner)
    trial = client.post(f"/studio/projects/{p['id']}/brain/trial", headers=owner, json=body()).json()
    jid = trial["jobs"][0]["id"]
    run(store.cas_job(jid, "queued", {"status": "running"}))
    from studio.recovery import recover_studio_jobs
    run(recover_studio_jobs())
    assert run(store.get_job(jid))["status"] == "uncertain"
    assert len(calls) == 1
