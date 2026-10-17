# -*- coding: utf-8 -*-
"""WO3d 块 A：启动恢复与调度补发（定妆出图 / 声线试听），绝不重发付费请求。

隔离：独立 SQLite + 全部块 B / 块 C 函数 monkeypatch；恢复只改数据库状态，不发出网。
既有 i2v 与 brain 的恢复口径必须保持不变。
"""
import asyncio
import uuid

import pytest

from studio import casting_jobs, store
from studio.recovery import recover_studio_jobs
from studio.scheduler import StudioScheduler


@pytest.fixture
def studio_db(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "recovery.db"))
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")
    monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_WAN", "3")
    monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_SEEDANCE", "3")
    monkeypatch.setenv("FIONA_STUDIO_POLL_TIMEOUT_MIN", "30")

    async def initialize():
        async with store.connection(transaction=True) as db:
            await db.execute("CREATE TABLE users(username TEXT PRIMARY KEY)")
            await db.execute("INSERT INTO users(username) VALUES('author')")
            for statement in store.STUDIO_TABLES_DDL:
                await db.execute(statement)

    asyncio.run(initialize())
    return tmp_path


@pytest.fixture
def no_paid_calls(monkeypatch):
    """任何真正出网 / 合成的调用都应让测试失败；_schedule 只记录。"""
    calls = {"image": 0, "cosy": 0, "edge": 0, "scheduled": []}

    async def boom(*args, **kwargs):
        raise AssertionError("恢复不得发出付费请求")

    monkeypatch.setattr(casting_jobs, "_generate_sheet", boom)
    monkeypatch.setattr(casting_jobs, "_synthesize_cosy", boom)
    monkeypatch.setattr(casting_jobs, "_synthesize_edge", boom)
    monkeypatch.setattr(casting_jobs, "_schedule", lambda jid: calls["scheduled"].append(jid))
    return calls


def run(coro):
    return asyncio.run(coro)


async def _project(title="恢复项目"):
    return await store.create_project("author", title, "16:9")


async def _quote(db, pid, tag):
    qid, stamp = uuid.uuid4().hex, store.utcnow()
    await db.execute("""INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,
        total_max_cny,params_hash,status,created_at,expires_at,confirmed_at)
        VALUES(?,?,'author','[]','0','0',?,'confirmed',?,?,?)""", (qid, pid, tag, stamp, stamp, stamp))
    return qid


async def new_casting_job(project, *, kind="image", status="queued", media_provider="seedream",
                          reserved="0.30", run_token=None, needs_recheck=0):
    job_id = uuid.uuid4().hex
    stamp = store.utcnow()
    async with store.connection(transaction=True) as db:
        qid = await _quote(db, project["id"], f"casting-{kind}")
        fields = {
            "id": job_id, "project_id": project["id"], "owner": "author", "kind": kind,
            "provider": "wan", "media_provider": media_provider, "model": media_provider or "media",
            "params_json": store._json({"text": "台词"} if kind == "tts" else {}),
            "fingerprint": uuid.uuid4().hex, "quote_id": qid, "quote_item_id": job_id,
            "status": status, "currency": "CNY", "reserved_amount": reserved, "reserved_cny": reserved,
            "est_min_cny": reserved, "est_max_cny": reserved, "run_token": run_token,
            "needs_recheck": needs_recheck, "created_at": stamp, "updated_at": stamp,
            "confirmed_day": "2026-10-16",
        }
        await db.execute(f"INSERT INTO studio_jobs({','.join(fields)}) "
                         f"VALUES({','.join('?' for _ in fields)})", tuple(fields.values()))
    return job_id


async def new_brain_job(project, *, task="style_proposals", status="queued", run_token=None,
                       reserved="0.05"):
    job_id = uuid.uuid4().hex
    stamp = store.utcnow()
    async with store.connection(transaction=True) as db:
        qid = await _quote(db, project["id"], f"brain-{task}")
        fields = {
            "id": job_id, "project_id": project["id"], "owner": "author", "kind": "brain",
            "provider": "wan", "brain_provider": "claude", "model": "claude-sonnet-5-5", "task": task,
            "params_json": store._json({"inputs": {"text": "素材"}}), "fingerprint": uuid.uuid4().hex,
            "quote_id": qid, "quote_item_id": job_id, "status": status, "currency": "CNY",
            "reserved_amount": reserved, "reserved_cny": reserved, "est_min_cny": "0",
            "est_max_cny": reserved, "run_token": run_token, "created_at": stamp, "updated_at": stamp,
            "confirmed_day": "2026-10-16", "confirmed_month": "2026-10",
        }
        await db.execute(f"INSERT INTO studio_jobs({','.join(fields)}) "
                         f"VALUES({','.join('?' for _ in fields)})", tuple(fields.values()))
    return job_id


async def new_i2v_job(project, *, status="queued"):
    asset = await store.create_asset("author", project["id"], kind="image", source="upload",
                                     rel_path="frame.png", sha256="a" * 64, bytes=10)
    quote = await store.create_quote("author", project["id"], {
        "provider": "wan", "prompt": "固定相机", "first_frame_asset_id": asset["id"], "duration": 5})
    job = (await store.confirm_quote(quote["id"], "author"))[0]
    if status != "queued":
        assert await store.cas_job(job["id"], "queued",
                                   {"status": "submitting", "run_token": "tok-i2v"})
    return job["id"]


async def _row(job_id):
    return await store.get_job(job_id)


# ---------------------------------------------------------------------------
# 定妆 / 声线
# ---------------------------------------------------------------------------

def test_casting_inflight_becomes_uncertain_and_queued_is_redispatched(studio_db, no_paid_calls):
    async def scenario():
        project = await _project()
        image_running = await new_casting_job(project, kind="image", status="running",
                                              reserved="0.30", run_token="tok-img")
        image_submitting = await new_casting_job(project, kind="image", status="submitting",
                                                 reserved="0.30", run_token="tok-img2")
        tts_running = await new_casting_job(project, kind="tts", status="running",
                                            media_provider="cosyvoice", reserved="0.02",
                                            run_token="tok-tts")
        queued = await new_casting_job(project, kind="image", status="queued", reserved="0.30")

        await recover_studio_jobs()

        for job_id, reserved in ((image_running, "0.30"), (image_submitting, "0.30"), (tts_running, "0.02")):
            row = await _row(job_id)
            assert row["status"] == "uncertain"
            assert row["needs_recheck"] == 1
            assert row["next_poll_at"] is None
            assert row["reserved_amount"] == reserved  # 保留预留，只能手动释放
            assert row["actual_amount"] is None
            assert "服务重启时请求可能已发出" in row["error_message"]
        # queued 不动，交给调度器补发，绝不在此重发
        assert (await _row(queued))["status"] == "queued"
        assert no_paid_calls["scheduled"] == []
        assert no_paid_calls["image"] == 0 and no_paid_calls["cosy"] == 0

        scheduler = StudioScheduler()
        await scheduler.tick()
        # 只有 queued 的那条被重新派发
        assert no_paid_calls["scheduled"] == [queued]
        assert (await _row(queued))["status"] == "queued"

        # uncertain 的任务可以被作者手动释放，释放后预留清零
        assert await store.release_job(image_running, "author", True) is not None
        released = await _row(image_running)
        assert released["status"] == "released" and released["reserved_amount"] == "0"

    run(scenario())


def test_casting_uncertain_stays_uncertain_across_restart(studio_db, no_paid_calls):
    async def scenario():
        project = await _project()
        job_id = await new_casting_job(project, kind="image", status="uncertain",
                                       reserved="0.30", needs_recheck=1)
        await recover_studio_jobs()
        row = await _row(job_id)
        assert row["status"] == "uncertain" and row["reserved_amount"] == "0.30"

    run(scenario())


def test_casting_recovery_needs_no_job_table(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "empty.db"))
    run(recover_studio_jobs())


# ---------------------------------------------------------------------------
# i2v 与 brain：既有恢复口径不变
# ---------------------------------------------------------------------------

def test_i2v_submitting_recovery_unchanged(studio_db, no_paid_calls):
    async def scenario():
        project = await _project()
        job_id = await new_i2v_job(project, status="submitting")
        await recover_studio_jobs()
        row = await _row(job_id)
        assert row["status"] == "uncertain"
        assert row["needs_recheck"] == 1 and row["next_poll_at"] is None
        assert "服务重启时请求可能已发出" in row["error_message"]
        assert row["reserved_cny"] != "0"

    run(scenario())


def test_brain_submitting_recovery_unchanged(studio_db, no_paid_calls):
    async def scenario():
        project = await _project()
        style = await new_brain_job(project, task="style_proposals", status="submitting",
                                    run_token="tok-brain")
        synopsis = await new_brain_job(project, task="synopsis", status="running",
                                       run_token="tok-syn")
        quiet = await new_brain_job(project, task="style_proposals", status="succeeded",
                                    run_token="tok-ok")
        await recover_studio_jobs()
        for job_id in (style, synopsis):
            row = await _row(job_id)
            assert row["status"] == "uncertain"
            assert "服务重启时请求可能已发出" in row["error_message"]
            assert row["reserved_amount"] == "0.05"
        # succeeded 的导演任务重启不改变状态
        assert (await _row(quiet))["status"] == "succeeded"

    run(scenario())
