"""数据库并发确认、额度预留和状态 CAS；全程只使用临时 SQLite。"""

import asyncio
from datetime import datetime, timedelta, timezone
import io
import sqlite3
import threading

from fastapi import HTTPException
from PIL import Image
import pytest

from studio import spend, store


@pytest.fixture(autouse=True)
def studio_database(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "studio.sqlite"))
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    async def setup():
        async with store.connection(transaction=True) as db:
            await db.execute("CREATE TABLE users(username TEXT PRIMARY KEY)")
            await db.executemany("INSERT INTO users(username) VALUES(?)", [(name,) for name in ("author", "one", "two")])
            for statement in store.STUDIO_TABLES_DDL:
                await db.execute(statement)
    asyncio.run(setup())


async def scene(owner="author"):
    project = await store.create_project(owner, "清晨", "16:9")
    asset = await store.create_asset(owner, project["id"], kind="image", source="upload",
                                     rel_path=f"{project['id']}/frame.png", sha256="a" * 64,
                                     bytes=1000, width=854, height=480, meta={"mode": "RGB"})
    return project, asset


async def quoted(project, asset, *, now=None, **params):
    return await store.create_quote(project["owner"], project["id"], {
        "first_frame_asset_id": asset["id"], "prompt": "风吹动窗帘。", **params,
    }, now=now)


async def job_for(project, asset, *, now=None, **params):
    quote = await quoted(project, asset, now=now, **params)
    return (await store.confirm_quote(quote["id"], project["owner"], now=now))[0]


def test_confirmation_is_atomic_under_concurrency():
    async def scenario():
        project, asset = await scene()
        quote = await quoted(project, asset)
        results = await asyncio.gather(store.confirm_quote(quote["id"], "author"),
                                       store.confirm_quote(quote["id"], "author"), return_exceptions=True)
        assert sum(isinstance(result, list) for result in results) == 1
        failure = next(result for result in results if isinstance(result, HTTPException))
        assert failure.status_code == 409
        assert len(await store.list_jobs(project["id"], "author")) == 1
        assert (await spend.today())["committed_cny"] == 1.5
        with pytest.raises(HTTPException) as error:
            await store.confirm_quote(quote["id"], "author")
        assert error.value.status_code == 409
    asyncio.run(scenario())


def test_distinct_quotes_allow_identical_versions_and_persist_only_asset_id():
    async def scenario():
        project, asset = await scene()
        first = await job_for(project, asset)
        second = await job_for(project, asset)
        assert first["fingerprint"] != second["fingerprint"]
        assert first["quote_item_id"] != second["quote_item_id"]
        assert first["params"] == second["params"]
        assert first["params"]["first_frame_asset_id"] == asset["id"]
        assert "base64" not in first["params_json"]
        assert (await store.claim_next_job("wan", 3, "run-1"))["id"] == first["id"]
        assert (await store.claim_next_job("wan", 3, "run-2"))["id"] == second["id"]
    asyncio.run(scenario())


def test_quote_expiry_only_limits_confirmation():
    async def scenario():
        project, asset = await scene()
        old = datetime.now(timezone.utc) - timedelta(minutes=16)
        quote = await quoted(project, asset, now=old)
        with pytest.raises(HTTPException) as error:
            await store.confirm_quote(quote["id"], "author")
        assert error.value.status_code == 409
        pending = await job_for(project, asset, now=old)
        claimed = await store.claim_next_job("wan", 3, "late-worker")
        assert claimed["id"] == pending["id"] and claimed["status"] == "submitting"
    asyncio.run(scenario())


def test_daily_budget_is_atomic_global_and_dev_mode_cannot_bypass(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "1.5")
    async def scenario():
        one, image_one = await scene("one")
        two, image_two = await scene("two")
        first, second = await quoted(one, image_one), await quoted(two, image_two)
        results = await asyncio.gather(store.confirm_quote(first["id"], "one"),
                                       store.confirm_quote(second["id"], "two"), return_exceptions=True)
        assert sum(isinstance(result, list) for result in results) == 1
        failure = next(result for result in results if isinstance(result, HTTPException))
        assert failure.status_code == 409 and "剩余额度" in failure.detail
        assert (await spend.today("one")) == (await spend.today("two")) == {"committed_cny": 1.5, "remaining_cny": 0.0}
    asyncio.run(scenario())


def test_uncertain_keeps_reservation_and_release_is_explicit(monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "1.5")
    async def scenario():
        project, asset = await scene()
        job = await job_for(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        assert await store.cas_job(job["id"], "submitting", {"status": "uncertain"}, run_token="worker")
        assert (await spend.today())["committed_cny"] == 1.5
        for value in (False, 1, "true", None):
            with pytest.raises(HTTPException) as error:
                await store.release_job(job["id"], "author", value)
            assert error.value.status_code == 422
        released = await store.release_job(job["id"], "author", True, "控制台核实未扣费")
        assert released["status"] == "released"
        assert released["reserved_cny"] == released["actual_cny"] == 0
        assert (await spend.today())["committed_cny"] == 0
        assert not await store.cas_job(job["id"], "uncertain", {"status": "running"}, run_token="worker")
    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["rejected", "cancelled", "filtered", "failed"])
def test_zero_usage_terminal_states_release_reservation(status):
    async def scenario():
        project, asset = await scene()
        job = await job_for(project, asset)
        if status == "cancelled":
            await store.cancel_job(job["id"], "author")
        else:
            await store.claim_next_job("wan", 3, "worker")
            expected = "submitting"
            if status == "filtered":
                await store.cas_job(job["id"], expected, {"status": "submitted", "task_id": "task"})
                expected = "submitted"
            await spend.settle_job(job["id"], expected, status)
        assert (await store.get_job(job["id"]))["reserved_cny"] == 0
        assert (await spend.today())["committed_cny"] == 0
    asyncio.run(scenario())


def test_shanghai_day_uses_confirmation_time_and_real_usage():
    async def scenario():
        project, asset = await scene()
        before = datetime(2026, 10, 16, 15, 59, tzinfo=timezone.utc)
        after = before + timedelta(minutes=2)
        quote = await quoted(project, asset, now=before, provider="seedance")
        job = (await store.confirm_quote(quote["id"], "author", now=after))[0]
        assert job["confirmed_day"] == "2026-10-17"
        assert (await spend.today(now=before))["committed_cny"] == 0
        assert (await spend.today(now=after))["committed_cny"] == 4.074
        await store.claim_next_job("seedance", 3, "worker")
        await spend.settle_job(job["id"], "submitting", "failed", usage={"completion_tokens": 48324})
        assert (await spend.today(now=after))["committed_cny"] == 3.38268
    asyncio.run(scenario())


@pytest.mark.parametrize("tokens", [48324.0, "48324", "48324.0"])
def test_numeric_seedance_tokens_settle_and_release_reservation(tokens):
    async def scenario():
        project, asset = await scene()
        job = await job_for(project, asset, provider="seedance")
        await store.claim_next_job("seedance", 3, "worker")
        assert await spend.settle_job(job["id"], "submitting", "failed",
                                      usage={"completion_tokens": tokens}, run_token="worker")
        settled = await store.get_job(job["id"])
        assert settled["actual_cny"] == 3.38268
        assert settled["reserved_cny"] == 0
        assert (await spend.today())["committed_cny"] == 3.38268
    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["failed", "expired", "downloaded"])
@pytest.mark.parametrize("tokens", [-1, 1.5, "-1", "1.5", "invalid"])
def test_invalid_seedance_tokens_keep_terminal_reservation_and_budget(monkeypatch, status, tokens):
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "4.074")
    async def scenario():
        project, asset = await scene()
        job = await job_for(project, asset, provider="seedance")
        await store.claim_next_job("seedance", 3, "worker")
        assert await store.cas_job(job["id"], "submitting", {"status": "submitted", "task_id": "task"}, run_token="worker")
        if status == "downloaded":
            assert await store.cas_job(job["id"], "submitted", {"status": "succeeded",
                                       "usage_json": {"completion_tokens": tokens}}, run_token="worker")
            metadata = {"rel_path": f"{project['id']}/result.mp4", "sha256": "d" * 64,
                        "bytes": 99, "duration_s": 5, "fps": 24, "width": 854, "height": 480, "has_audio": True}
            assert await store.finish_download(job["id"], metadata, run_token="worker")
        else:
            assert await spend.settle_job(job["id"], "submitted", status,
                                          usage={"completion_tokens": tokens}, run_token="worker")
        unsettled = await store.get_job(job["id"])
        assert unsettled["status"] == status
        assert unsettled["actual_cny"] is None
        assert unsettled["reserved_cny"] == job["reserved_cny"] == 4.074
        assert (await spend.today()) == {"committed_cny": 4.074, "remaining_cny": 0.0}
        later_quote = await quoted(project, asset)
        with pytest.raises(HTTPException) as error:
            await store.confirm_quote(later_quote["id"], "author")
        assert error.value.status_code == 409
    asyncio.run(scenario())


def test_quote_cap_is_live_and_quotes_do_not_reserve(monkeypatch):
    async def scenario():
        project, asset = await scene()
        monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "1.49")
        with pytest.raises(HTTPException) as error:
            await quoted(project, asset)
        assert error.value.status_code == 422 and "1.49" in error.value.detail
        monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "1.5")
        quote = await quoted(project, asset)
        assert quote["today"] == {"committed_cny": 0.0, "remaining_cny": 300.0}
        assert (await spend.today())["committed_cny"] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("cap,provider,duration,expected", [
    ("100", "seedance", 30, "¥100.00"),
    ("1.5", "wan", 6, "¥1.50"),
    ("1.234", "wan", 5, "¥1.23"),
])
def test_quote_limit_message_has_two_decimal_places(monkeypatch, cap, provider, duration, expected):
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", cap)
    async def scenario():
        project, asset = await scene()
        with pytest.raises(HTTPException) as error:
            await quoted(project, asset, provider=provider, resolution="1080p" if provider == "seedance" else "480P",
                         duration=duration)
        assert error.value.detail == f"本次报价超过单次上限 {expected}"
    asyncio.run(scenario())


@pytest.mark.parametrize("daily,expected", [("1.5", "¥0.00"), ("2", "¥0.50"), ("2.734", "¥1.23")])
def test_remaining_budget_message_has_two_decimal_places(monkeypatch, daily, expected):
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", daily)
    async def scenario():
        project, asset = await scene()
        await job_for(project, asset)
        quote = await quoted(project, asset)
        with pytest.raises(HTTPException) as error:
            await store.confirm_quote(quote["id"], "author")
        assert error.value.detail == f"今日额度不足，剩余额度 {expected}"
    asyncio.run(scenario())


def test_every_owned_resource_is_isolated():
    async def scenario():
        project, asset = await scene()
        quote = await quoted(project, asset)
        job = (await store.confirm_quote(quote["id"], "author"))[0]
        for coroutine in (
            store.get_project(project["id"], "other"), store.get_asset(asset["id"], "other"),
            store.get_quote(quote["id"], "other"), store.get_job(job["id"], "other"),
            store.confirm_quote(quote["id"], "other"), store.list_jobs(project["id"], "other"),
            store.cancel_job(job["id"], "other"), store.recheck_job(job["id"], "other"),
            store.link_task(job["id"], "other", "task"), store.release_job(job["id"], "other", True),
        ):
            with pytest.raises(HTTPException) as error:
                await coroutine
            assert error.value.status_code == 404
        assert await store.list_projects("other") == []
    asyncio.run(scenario())


def test_claim_limits_are_atomic_and_provider_independent():
    async def scenario():
        project, asset = await scene()
        for _ in range(5):
            await job_for(project, asset)
        seedance = await job_for(project, asset, provider="seedance")
        claims = await asyncio.gather(*(store.claim_next_job("wan", 3, f"worker-{i}") for i in range(5)))
        assert sum(job is not None for job in claims) == 3
        assert (await store.claim_next_job("seedance", 1, "seedance-worker"))["id"] == seedance["id"]
        stale = next(job for job in claims if job is not None)
        assert not await store.cas_job(stale["id"], "submitting", {"status": "submitted"}, run_token="stale-token")
        with pytest.raises(ValueError):
            await store.cas_job(stale["id"], "submitting", {"status": "queued"})
    asyncio.run(scenario())


def test_link_and_recheck_only_request_read_only_work():
    async def scenario():
        project, asset = await scene()
        job = await job_for(project, asset)
        with pytest.raises(HTTPException):
            await store.recheck_job(job["id"], "author")
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        linked = await store.link_task(job["id"], "author", "upstream-task")
        assert linked["status"] == "submitted" and linked["poll_requested"] == 1
        assert await store.claim_next_job("wan", 3, "another-worker") is None
        await store.cas_job(job["id"], "submitted", {"status": "running", "needs_recheck": 1, "poll_requested": 0})
        assert await store.list_due_jobs() == []
        await store.recheck_job(job["id"], "author")
        assert [item["id"] for item in await store.list_due_jobs()] == [job["id"]]
        with pytest.raises(HTTPException):
            await store.cancel_job(job["id"], "author")
    asyncio.run(scenario())


def test_download_asset_and_settlement_are_atomic_and_stale_worker_cannot_recreate():
    async def scenario():
        project, asset = await scene()
        job = await job_for(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "submitted", "task_id": "task"})
        await store.cas_job(job["id"], "submitted", {"status": "succeeded", "usage_json": {"duration": 5, "SR": 480}})
        metadata = {"rel_path": f"{project['id']}/result.mp4", "sha256": "b" * 64, "bytes": 99,
                    "duration_s": 5, "fps": 30, "width": 854, "height": 480, "has_audio": True}
        assert not await store.finish_download(job["id"], metadata, run_token="stale-worker")
        assert await store.finish_download(job["id"], metadata, run_token="worker")
        assert not await store.finish_download(job["id"], metadata, run_token="worker")
        complete = await store.get_job(job["id"])
        assert complete["status"] == "downloaded" and complete["actual_cny"] == 1.5 and complete["reserved_cny"] == 0
        video = await store.get_asset(complete["result_asset_id"], "author")
        assert video["kind"] == "video" and video["source"] == "generated"
        async with store.connection(transaction=True) as db:
            await db.execute("DELETE FROM studio_jobs WHERE owner=?", ("author",))
            await db.execute("DELETE FROM studio_quotes WHERE owner=?", ("author",))
            await db.execute("DELETE FROM studio_assets WHERE owner=?", ("author",))
            await db.execute("DELETE FROM studio_projects WHERE owner=?", ("author",))
        assert not await store.finish_download(job["id"], metadata, run_token="worker")
        with pytest.raises(HTTPException) as error:
            await store.create_asset("author", project["id"], kind="video", source="generated", **metadata)
        assert error.value.status_code == 404
    asyncio.run(scenario())


def test_partial_unique_index_blocks_duplicate_inflight_fingerprints():
    async def scenario():
        project, asset = await scene()
        one, two = await job_for(project, asset), await job_for(project, asset)
        with pytest.raises(sqlite3.IntegrityError):
            async with store.connection(transaction=True) as db:
                await db.execute("UPDATE studio_jobs SET fingerprint=? WHERE id=?", (one["fingerprint"], two["id"]))
        await store.cancel_job(one["id"], "author")
        async with store.connection(transaction=True) as db:
            await db.execute("UPDATE studio_jobs SET fingerprint=? WHERE id=?", (one["fingerprint"], two["id"]))
    asyncio.run(scenario())


def test_concurrent_identical_uploads_share_one_asset():
    async def scenario():
        project = await store.create_project("author", "测试", "9:16")
        fields = {"kind": "image", "source": "upload", "rel_path": f"{project['id']}/same.png",
                  "sha256": "c" * 64, "bytes": 100, "width": 480, "height": 854}
        results = await asyncio.gather(*(store.create_asset("author", project["id"], **fields) for _ in range(3)))
        assert len({item["id"] for item in results}) == 1
        async with store.connection() as db:
            async with db.execute("SELECT COUNT(*) FROM studio_assets") as cursor:
                assert (await cursor.fetchone())[0] == 1
    asyncio.run(scenario())


def test_large_finite_budget_configuration_does_not_fail(monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "1e308")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "1e30")
    async def scenario():
        project, asset = await scene()
        quote = await quoted(project, asset)
        assert quote["today"]["remaining_cny"] == 1e308
        job = (await store.confirm_quote(quote["id"], "author"))[0]
        assert job["reserved_cny"] == 1.5
        assert (await spend.today())["committed_cny"] == 1.5
    asyncio.run(scenario())


def test_create_project_rechecks_account_after_deletion():
    async def scenario():
        async with store.connection(transaction=True) as db:
            await db.execute("DELETE FROM users WHERE username='author'")
        with pytest.raises(HTTPException) as error:
            await store.create_project("author", "晚到请求", "16:9")
        assert error.value.status_code == 404
        assert await store.list_projects("author") == []
    asyncio.run(scenario())


def test_upload_holds_write_lock_until_file_and_asset_are_saved(monkeypatch, tmp_path):
    from studio import storage
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "media"))
    image = io.BytesIO()
    Image.new("RGB", (640, 480)).save(image, "PNG")
    data = image.getvalue()
    metadata = storage.inspect_image(data)
    started, proceed = threading.Event(), threading.Event()
    original = storage.save_image
    def blocked_save(*args):
        started.set()
        assert proceed.wait(5)
        return original(*args)
    monkeypatch.setattr(storage, "save_image", blocked_save)

    async def scenario():
        project = await store.create_project("author", "并发上传", "16:9")
        saving = asyncio.create_task(store.save_uploaded_asset("author", project["id"], data, metadata))
        assert await asyncio.to_thread(started.wait, 5)
        attempted, acquired = asyncio.Event(), asyncio.Event()
        async def delete():
            attempted.set()
            async with store.connection(transaction=True) as db:
                acquired.set()
                await db.execute("DELETE FROM studio_assets WHERE project_id=?", (project["id"],))
                await db.execute("DELETE FROM studio_projects WHERE id=?", (project["id"],))
        deleting = asyncio.create_task(delete())
        await attempted.wait()
        assert not acquired.is_set()
        proceed.set()
        asset = await saving
        await deleting
        assert acquired.is_set()
        assert storage.resolve_asset_path(asset).is_file()
        with pytest.raises(HTTPException) as error:
            await store.save_uploaded_asset("author", project["id"], data, metadata)
        assert error.value.status_code == 404
    asyncio.run(scenario())


def test_cancelled_upload_waits_for_thread_then_removes_orphan_file(monkeypatch, tmp_path):
    from studio import storage
    root = tmp_path / "media"
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    image = io.BytesIO()
    Image.new("RGB", (640, 480)).save(image, "PNG")
    data = image.getvalue()
    metadata = storage.inspect_image(data)
    started, proceed = threading.Event(), threading.Event()
    original = storage.save_image
    def blocked_save(*args):
        started.set()
        assert proceed.wait(5)
        return original(*args)
    monkeypatch.setattr(storage, "save_image", blocked_save)

    async def scenario():
        project = await store.create_project("author", "取消上传", "16:9")
        saving = asyncio.create_task(store.save_uploaded_asset("author", project["id"], data, metadata))
        assert await asyncio.to_thread(started.wait, 5)
        saving.cancel()
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await saving
        assert not (root / project["id"]).exists()
        assert await store.find_asset_by_sha(project["id"], "author", metadata["sha256"]) is None
    asyncio.run(scenario())
