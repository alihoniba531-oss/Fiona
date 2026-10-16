"""WO3a notice migration, bounded scans and recovery after process loss."""
import asyncio
import sqlite3

import pytest

from studio import notices, spend, store
from test_studio_wo2_backend import new_job, rows, scene, studio_client  # noqa: F401


def test_first_scheduler_time_persists_and_historical_terminals_are_not_backfilled(studio_client, monkeypatch):
    import database

    async def run():
        project, asset = await scene()
        old = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "old-worker")
        await spend.settle_job(old["id"], "submitting", "failed", usage={})
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("UPDATE studio_jobs SET finished_at=?,updated_at=? WHERE id=?",
                       ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00", old["id"]))
        # Reproduce upgrading a pre-notice database, before its first scheduler start.
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("DELETE FROM studio_notice_meta WHERE key='started_at'")
        initial = await notices.initialize_notice_cutoff()
        monkeypatch.setattr(store, "utcnow", lambda: "2099-01-01T00:00:00+00:00")
        assert await notices.initialize_notice_cutoff() == initial
        await notices.retry_pending_notices()
        assert await database.list_studio_notices_with_content("owner") == []
        assert rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'") == []
        fresh = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "new-worker")
        await spend.settle_job(fresh["id"], "submitting", "failed", usage={})
        await notices.retry_pending_notices()
        assert [item["job_id"] for item in await database.list_studio_notices_with_content("owner")] == [fresh["id"]]
    asyncio.run(run())


def test_pending_message_survives_lost_process_memory_and_later_link(studio_client, monkeypatch):
    import aiosqlite
    import database
    execute = aiosqlite.Connection.execute
    failures = []

    def fail_once(db, sql, *args, **kwargs):
        if "INSERT OR IGNORE INTO studio_notices" in sql and not failures:
            failures.append(True)
            raise sqlite3.OperationalError("simulated process loss")
        return execute(db, sql, *args, **kwargs)

    monkeypatch.setattr(aiosqlite.Connection, "execute", fail_once)

    async def run():
        await notices.initialize_notice_cutoff()
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        await notices.write_job_notice(job["id"])
        before = rows("SELECT id,content FROM messages WHERE username='owner' AND role='assistant'")
        assert len(before) == 1
        assert rows("SELECT job_id FROM studio_notice_pending") == [{"job_id": job["id"]}]
        await store.link_task(job["id"], "owner", "local-task")
        notices._PENDING_NOTICES.clear()
        database._pending_studio_messages.clear()
        await notices.retry_pending_notices()
        after = rows("SELECT id,content FROM messages WHERE username='owner' AND role='assistant'")
        assert after == before
        stored = await database.list_studio_notices_with_content("owner")
        assert len(stored) == 1 and stored[0]["message_id"] == before[0]["id"]
        assert "可能已扣费" in stored[0]["content"]
        assert rows("SELECT * FROM studio_notice_pending") == []
    asyncio.run(run())


def test_archived_projects_are_excluded_by_direct_and_retry_paths(studio_client, monkeypatch):
    import database
    writes = []

    async def record(job_id):
        writes.append(job_id)

    async def run():
        await notices.initialize_notice_cutoff()
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await spend.settle_job(job["id"], "submitting", "failed", usage={})
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("UPDATE studio_projects SET archived=1 WHERE id=?", (project["id"],))
        await notices.write_job_notice(job["id"])
        assert await database.list_studio_notices_with_content("owner") == []
        monkeypatch.setattr(notices, "write_job_notice", record)
        await notices.retry_pending_notices()
        assert writes == []
    asyncio.run(run())


def test_notice_scan_can_use_terminal_time_index(studio_client):
    import database
    with sqlite3.connect(database.DB_PATH) as db:
        details = " ".join(str(row) for row in db.execute("""EXPLAIN QUERY PLAN
            SELECT j.id FROM studio_jobs AS j INDEXED BY idx_studio_jobs_notice_terminal
            WHERE j.kind='i2v'
              AND j.status IN ('downloaded','failed','rejected','filtered','expired','uncertain')
              AND COALESCE(j.finished_at,j.updated_at)>=?
            ORDER BY COALESCE(j.finished_at,j.updated_at),j.id""", ("2026-10-16T00:00:00+00:00",)))
    assert "idx_studio_jobs_notice_terminal" in details
    assert "SEARCH" in details


def test_historical_uncertain_recheck_cannot_backfill_after_timestamp_changes(studio_client):
    import database

    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "historical-worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("DELETE FROM studio_notice_meta WHERE key='started_at'")
        await notices.initialize_notice_cutoff()
        assert rows("SELECT job_id FROM studio_notice_historical") == [{"job_id": job["id"]}]
        await store.cas_job(job["id"], "uncertain", {"poll_requested": 1})
        await notices.retry_pending_notices()
        await notices.write_job_notice(job["id"])
        assert await database.list_studio_notices_with_content("owner") == []
        assert rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'") == []
        # Linking and reaching a later terminal cannot undo the deployment marker.
        await store.link_task(job["id"], "owner", "historical-linked-task")
        await spend.settle_job(job["id"], "submitted", "failed", usage={})
        await notices.write_job_notice(job["id"])
        await notices.retry_pending_notices()
        assert await database.list_studio_notices_with_content("owner") == []
        await database.delete_account_data("owner")
        assert rows("SELECT * FROM studio_notice_historical") == []
    asyncio.run(run())


@pytest.mark.parametrize("restart_stage", ["before_message", "after_notice_commit"])
def test_restart_retry_covers_both_sides_of_message_and_notice_commit(studio_client, monkeypatch, restart_stage):
    import aiosqlite
    import database
    execute, commit, save = aiosqlite.Connection.execute, aiosqlite.Connection.commit, database.save_message
    notice_connections, failures = set(), []

    def track_notice(db, sql, *args, **kwargs):
        if "INSERT OR IGNORE INTO studio_notices" in sql:
            notice_connections.add(db)
        return execute(db, sql, *args, **kwargs)

    async def interrupted_commit(db):
        await commit(db)
        if restart_stage == "after_notice_commit" and db in notice_connections and not failures:
            failures.append(True)
            raise sqlite3.OperationalError("commit completed before process interruption")

    async def interrupted_save(*args, **kwargs):
        if restart_stage == "before_message" and not failures:
            failures.append(True)
            raise sqlite3.OperationalError("process stopped before message persistence")
        return await save(*args, **kwargs)

    monkeypatch.setattr(aiosqlite.Connection, "execute", track_notice)
    monkeypatch.setattr(aiosqlite.Connection, "commit", interrupted_commit)
    monkeypatch.setattr(database, "save_message", interrupted_save)

    async def run():
        await notices.initialize_notice_cutoff()
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        await notices.write_job_notice(job["id"])
        if restart_stage == "before_message":
            assert rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'") == []
            assert len(rows("SELECT * FROM studio_notice_pending")) == 1
            await store.link_task(job["id"], "owner", "newly-linked-task")
        else:
            assert len(await database.list_studio_notices_with_content("owner")) == 1
        notices._PENDING_NOTICES.clear()
        database._pending_studio_messages.clear()
        await notices.retry_pending_notices()
        await notices.write_job_notice(job["id"])
        assert len(failures) == 1
        assert len(await database.list_studio_notices_with_content("owner")) == 1
        assert len(rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'")) == 1
        assert rows("SELECT * FROM studio_notice_pending") == []
    asyncio.run(run())
