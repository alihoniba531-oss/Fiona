"""WO2 只读接口与终态聊天提醒：隔离 SQLite、模拟供应商，无外网。"""
import asyncio
import io
import logging
import sqlite3

from PIL import Image
import pytest

from studio import notices, spend, storage, store
from studio.providers.base import PollResult, ProviderError
from studio.scheduler import StudioScheduler


@pytest.fixture
def studio_client(client, monkeypatch, tmp_path):
    import database
    from auth import create_token
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "owner,other")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    accounts = {}
    for username in ("owner", "other", "outsider"):
        user = asyncio.run(database.get_or_create_user(username))
        accounts[username] = {"Authorization": f"Bearer {create_token(username, user['session_version'])}"}
    return client, accounts


def rows(sql, params=()):
    import database
    with sqlite3.connect(database.DB_PATH) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(sql, params)]


async def scene(owner="owner", title="初雪"):
    project = await store.create_project(owner, title, "16:9")
    image = io.BytesIO()
    Image.new("RGB", (640, 360)).save(image, "PNG")
    data = image.getvalue()
    asset = await store.save_uploaded_asset(owner, project["id"], data, storage.inspect_image(data))
    return project, asset


async def new_job(project, asset, **params):
    quote = await store.create_quote(project["owner"], project["id"], {
        "first_frame_asset_id": asset["id"], "prompt": "风吹过窗边。", **params,
    })
    return (await store.confirm_quote(quote["id"], project["owner"]))[0]


def test_read_only_resources_are_owned_and_paths_are_private(studio_client):
    client, headers = studio_client
    project, asset = asyncio.run(scene())
    detail_url = f"/studio/projects/{project['id']}"
    assets_url = detail_url + "/assets"
    assert client.get(detail_url, headers=headers["owner"]).json() == asyncio.run(store.get_project(project["id"], "owner"))
    response = client.get(assets_url, headers=headers["owner"])
    assert response.status_code == 200
    assert response.json()[0]["id"] == asset["id"]
    assert response.json()[0]["meta"] == asset["meta"]
    assert "rel_path" not in response.json()[0]
    for url in (detail_url, assets_url):
        for actor in ("other", "outsider"):
            hidden = client.get(url, headers=headers[actor])
            assert hidden.status_code == 404 and hidden.headers["cache-control"] == "private, no-store"
        assert client.get(url).status_code == 404


@pytest.mark.parametrize("state", ["downloaded", "failed", "rejected", "filtered", "expired", "uncertain"])
def test_each_scheduler_terminal_writes_one_real_default_conversation_message(studio_client, monkeypatch, state):
    import agent_store
    import database
    _, _headers = studio_client
    other_conversation = asyncio.run(agent_store.create_conversation("owner", "别的会话"))["id"]
    balance = asyncio.run(database.get_strawberry_balance("owner"))

    class Provider:
        async def submit(self, params, image_path):
            raise ProviderError(state, "submission_error", "SECRET sk-private https://private.invalid/task-id")

        async def poll(self, task_id):
            assert task_id == "private-task-id"
            return PollResult("succeeded" if state == "downloaded" else state,
                              usage={"duration": 5, "SR": 480},
                              result_url="https://private.invalid/private-result", error_code="short_output",
                              error_message="SECRET sk-private https://private.invalid/task-id")

    async def fake_download(*args, **kwargs):
        return {"rel_path": "offline-result.mp4", "sha256": "b" * 64, "bytes": 10,
                "duration_s": 5, "width": 640, "height": 360, "fps": 24, "has_audio": 1}

    monkeypatch.setattr(storage, "download_video", fake_download)

    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        if state not in {"rejected", "uncertain"}:
            await store.claim_next_job("wan", 3, "worker")
            await store.cas_job(job["id"], "submitting", {"status": "submitted", "task_id": "private-task-id"})
        scheduler = StudioScheduler()
        monkeypatch.setattr(scheduler, "_provider", lambda job: Provider())
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == state
        await scheduler.tick()
        await notices.write_job_notice(job["id"])
        stored = await database.list_studio_notices_with_content("owner")
        assert len(stored) == 1
        notice = stored[0]
        assert notice["job_id"] == job["id"] and notice["project_id"] == project["id"]
        assert notice["project_title"] == "初雪" and len(notice["summary"]) <= 200
        context = await agent_store.resolve_chat_conversation("owner")
        assert notice["conversation_id"] == context["conversation"]["id"] != other_conversation
        message = rows("SELECT * FROM messages WHERE id=?", (notice["message_id"],))[0]
        assert message["username"] == "owner" and message["role"] == "assistant"
        assert message["content"] == notice["content"] and message["conversation_id"] == notice["conversation_id"]
        assert len(rows("SELECT * FROM messages WHERE role='assistant' AND username='owner'")) == 1
        for private in ("http", "private-task-id", "SECRET", "sk-private"):
            assert private not in notice["content"]
        if state == "downloaded":
            assert notice["content"] == "【短片工作室】《初雪》镜头已生成：万相 3.0 480P 5 秒，实付 ¥1.50。"
        elif state == "uncertain":
            assert notice["content"] == "【短片工作室】《初雪》镜头提交结果不确定，可能已扣费，请到工作室核对。"
            assert result["reserved_cny"] == job["reserved_cny"]
        elif state in {"rejected", "filtered"}:
            assert "未扣费的部分已释放。" in notice["content"]
        else:
            # 实付等于原预留，没有任何未扣费部分可释放。
            assert "未扣费的部分已释放。" not in notice["content"]
    asyncio.run(run())
    assert asyncio.run(database.get_strawberry_balance("owner")) == balance


def test_notice_failure_cannot_change_task_or_settlement_and_next_tick_retries(studio_client, monkeypatch, caplog):
    import database
    original = database.save_studio_notice
    calls = []

    async def fail_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("SECRET https://private.invalid/notice-error")
        return await original(*args, **kwargs)

    class RejectingProvider:
        async def submit(self, params, image_path):
            raise ProviderError("rejected", "submission_error", "PRIVATE")

    monkeypatch.setattr(database, "save_studio_notice", fail_once)
    caplog.set_level(logging.WARNING, logger="studio.notices")

    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        scheduler = StudioScheduler()
        monkeypatch.setattr(scheduler, "_provider", lambda job: RejectingProvider())
        await scheduler.tick()
        failed_notice_job = await store.get_job(job["id"])
        assert failed_notice_job["status"] == "rejected"
        assert failed_notice_job["reserved_cny"] == failed_notice_job["actual_cny"] == 0
        assert (await spend.today())["committed_cny"] == 0
        assert await database.list_studio_notices_with_content("owner") == []
        await scheduler.tick()
        assert await store.get_job(job["id"]) == failed_notice_job
        assert len(await database.list_studio_notices_with_content("owner")) == 1
    asyncio.run(run())
    assert len(calls) == 2 and "code=notice_write_error" in caplog.text
    assert "SECRET" not in caplog.text and "private.invalid" not in caplog.text


def test_uncertain_notice_is_not_repeated_after_later_failure_and_parallel_retries(studio_client):
    import database
    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        await asyncio.gather(*(notices.write_job_notice(job["id"]) for _ in range(3)))
        await store.link_task(job["id"], "owner", "linked-task")
        await spend.settle_job(job["id"], "submitted", "failed", usage={})
        await notices.retry_pending_notices()
        assert len(await database.list_studio_notices_with_content("owner")) == 1
        assert len(rows("SELECT * FROM messages WHERE role='assistant' AND username='owner'")) == 1
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["insert", "commit"])
def test_notice_retry_after_message_save_reuses_exact_message(studio_client, monkeypatch, fault):
    import aiosqlite
    import database
    original_execute = aiosqlite.Connection.execute
    original_commit = aiosqlite.Connection.commit
    original_save = database.save_message
    notice_connections = set()
    failures, saves = [], []

    def fail_execute(db, sql, *args, **kwargs):
        if "INSERT OR IGNORE INTO studio_notices" in sql:
            notice_connections.add(db)
            if fault == "insert" and not failures:
                failures.append(1)
                raise sqlite3.OperationalError("private insert error")
        return original_execute(db, sql, *args, **kwargs)

    async def fail_commit(db):
        if fault == "commit" and db in notice_connections and not failures:
            failures.append(1)
            raise sqlite3.OperationalError("private commit error")
        return await original_commit(db)

    async def record_save(*args, **kwargs):
        saves.append(1)
        return await original_save(*args, **kwargs)

    monkeypatch.setattr(aiosqlite.Connection, "execute", fail_execute)
    monkeypatch.setattr(aiosqlite.Connection, "commit", fail_commit)
    monkeypatch.setattr(database, "save_message", record_save)

    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await spend.settle_job(job["id"], "submitting", "failed", usage={})
        await notices.write_job_notice(job["id"])
        message = rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'")[0]
        assert await database.list_studio_notices_with_content("owner") == []
        scheduler = StudioScheduler()
        await scheduler.tick()
        stored = await database.list_studio_notices_with_content("owner")
        assert len(stored) == 1 and stored[0]["message_id"] == message["id"]
        assert len(rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'")) == 1
        assert len(failures) == len(saves) == 1
    asyncio.run(run())


def test_identical_jobs_have_distinct_exact_messages_when_notified_concurrently(studio_client):
    import database
    async def run():
        project, asset = await scene()
        jobs = [await new_job(project, asset) for _ in range(3)]
        for job in jobs:
            await store.claim_next_job("wan", 3, job["id"])
            await spend.settle_job(job["id"], "submitting", "failed", usage={})
        await asyncio.gather(*(notices.write_job_notice(job["id"]) for job in jobs))
        stored = await database.list_studio_notices_with_content("owner")
        assert len(stored) == len({notice["message_id"] for notice in stored}) == 3
        assert len({notice["content"] for notice in stored}) == 1
    asyncio.run(run())


@pytest.mark.parametrize("failure_stage", ["before_message", "after_message"])
def test_pending_first_terminal_notice_survives_link_task_before_next_tick(studio_client, monkeypatch, failure_stage):
    import aiosqlite
    import database
    original_save = database.save_studio_notice
    original_execute = aiosqlite.Connection.execute
    failures = []

    async def fail_save(*args, **kwargs):
        if failure_stage == "before_message" and not failures:
            failures.append(1)
            raise sqlite3.OperationalError("offline notice error")
        return await original_save(*args, **kwargs)

    def fail_execute(db, sql, *args, **kwargs):
        if failure_stage == "after_message" and "INSERT OR IGNORE INTO studio_notices" in sql and not failures:
            failures.append(1)
            raise sqlite3.OperationalError("offline notice error")
        return original_execute(db, sql, *args, **kwargs)

    class PollingProvider:
        async def poll(self, task_id):
            return PollResult("running")

    monkeypatch.setattr(database, "save_studio_notice", fail_save)
    monkeypatch.setattr(aiosqlite.Connection, "execute", fail_execute)

    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        await notices.write_job_notice(job["id"])
        assert await database.list_studio_notices_with_content("owner") == []
        linked = await store.link_task(job["id"], "owner", "linked-task")
        assert linked["status"] == "submitted"
        scheduler = StudioScheduler()
        monkeypatch.setattr(scheduler, "_provider", lambda job: PollingProvider())
        await scheduler.tick()
        stored = await database.list_studio_notices_with_content("owner")
        assert len(stored) == 1
        assert stored[0]["content"] == "【短片工作室】《初雪》镜头提交结果不确定，可能已扣费，请到工作室核对。"
        assert (await store.get_job(job["id"]))["status"] == "running"
        assert len(rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'")) == 1
        await spend.settle_job(job["id"], "running", "failed", usage={})
        await scheduler.tick()
        assert len(await database.list_studio_notices_with_content("owner")) == 1
    asyncio.run(run())


def test_account_delete_discards_pending_snapshot_and_saved_message_retry(studio_client, monkeypatch):
    import aiosqlite
    import database
    original_execute = aiosqlite.Connection.execute
    failures = []

    def fail_execute(db, sql, *args, **kwargs):
        if "INSERT OR IGNORE INTO studio_notices" in sql and not failures:
            failures.append(1)
            raise sqlite3.OperationalError("offline notice error")
        return original_execute(db, sql, *args, **kwargs)

    monkeypatch.setattr(aiosqlite.Connection, "execute", fail_execute)

    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        await notices.write_job_notice(job["id"])
        assert len(rows("SELECT * FROM messages WHERE username='owner' AND role='assistant'")) == 1
        assert any(key[1] == job["id"] for key in notices._PENDING_NOTICES)
        assert any(key[2] == job["id"] for key in database._pending_studio_messages)
        await database.delete_account_data("owner")
        await notices.retry_pending_notices()
        await notices.write_job_notice(job["id"])
        assert rows("SELECT * FROM studio_notices WHERE username='owner'") == []
        assert rows("SELECT * FROM messages WHERE username='owner'") == []
        assert not any(key[1] == job["id"] for key in notices._PENDING_NOTICES)
        assert not any(key[2] == job["id"] for key in database._pending_studio_messages)
    asyncio.run(run())


def test_notices_cursor_page_limit_gate_and_owner_isolation(studio_client, monkeypatch):
    import database
    client, headers = studio_client
    project, _ = asyncio.run(scene())
    with sqlite3.connect(database.DB_PATH) as db:
        for index in range(55):
            db.execute("""INSERT INTO studio_notices(username,project_id,job_id,summary,message_id,conversation_id)
                VALUES(?,?,?,?,?,?)""", ("owner", project["id"], f"job-{index}", str(index), index, "conversation"))
        db.execute("INSERT INTO studio_notices(username,project_id,job_id,summary) VALUES(?,?,?,?)",
                   ("other", "foreign-project", "foreign-job", "private"))
    response = client.get("/studio/notices?after=2", headers=headers["owner"])
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    page = response.json()
    assert len(page) == 50 and page[0]["id"] == 3 and page[-1]["id"] == 52
    assert set(page[0]) == {"id", "project_id", "project_title", "job_id", "summary", "created_at", "conversation_id", "message_id", "content"}
    assert len(client.get("/studio/notices?after=52", headers=headers["owner"]).json()) == 3
    assert len(client.get("/studio/notices", headers=headers["other"]).json()) == 1
    assert client.get("/studio/notices?after=-1", headers=headers["owner"]).status_code == 422
    for actor in (None, "outsider"):
        hidden = client.get("/studio/notices", headers=headers[actor] if actor else {})
        assert hidden.status_code == 404 and hidden.headers["cache-control"] == "private, no-store"
    monkeypatch.setenv("FIONA_STUDIO", "0")
    assert client.get("/studio/notices", headers=headers["owner"]).status_code == 404


def test_account_delete_cleans_notices_and_late_writer_cannot_restore(studio_client):
    import database
    async def run():
        project, asset = await scene()
        job = await new_job(project, asset)
        await store.claim_next_job("wan", 3, "worker")
        await spend.settle_job(job["id"], "submitting", "failed", usage={})
        await notices.write_job_notice(job["id"])
        assert len(await database.list_studio_notices_with_content("owner")) == 1
        deleted = await database.delete_account_data("owner")
        assert deleted["deleted"] is True
        assert rows("SELECT * FROM studio_notices WHERE username='owner'") == []
        assert rows("SELECT * FROM messages WHERE username='owner'") == []
        assert await database.save_studio_notice("owner", job, "late", "late") is None
        await notices.retry_pending_notices()
        assert rows("SELECT * FROM studio_notices WHERE username='owner'") == []
    asyncio.run(run())


def test_unsettled_terminal_does_not_claim_payment_or_released_budget(studio_client):
    import database
    async def run():
        project, asset = await scene()
        job = await new_job(project, asset, provider="seedance")
        await store.claim_next_job("seedance", 3, "worker")
        await spend.settle_job(job["id"], "submitting", "failed", usage={"completion_tokens": "invalid"})
        await notices.write_job_notice(job["id"])
        notice = (await database.list_studio_notices_with_content("owner"))[0]
        assert "未扣费的部分已释放" not in notice["content"]
        assert (await store.get_job(job["id"]))["reserved_cny"] == job["reserved_cny"]
    asyncio.run(run())
