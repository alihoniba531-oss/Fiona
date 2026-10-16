"""调度、恢复和结算使用独立数据库与模拟传输。"""
import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil

import httpx
from PIL import Image
import pytest

from studio import spend, storage, store
from studio.recovery import recover_studio_jobs
from studio.scheduler import StudioScheduler, run_scheduler


FIXTURES = Path(__file__).parent / "fixtures" / "studio"
RESULT_URL = "https://offline.oss-accelerate.aliyuncs.com/result.mp4"


@pytest.fixture
def studio_db(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "studio.db"))
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_WAN", "3")
    monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_SEEDANCE", "3")
    monkeypatch.setenv("FIONA_STUDIO_POLL_TIMEOUT_MIN", "30")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-wan-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "offline-workspace")
    monkeypatch.setenv("ARK_API_KEY", "offline-ark-key")

    async def initialize():
        async with store.connection(transaction=True) as db:
            await db.execute("CREATE TABLE users(username TEXT PRIMARY KEY)")
            await db.execute("INSERT INTO users(username) VALUES('author')")
            for statement in store.STUDIO_TABLES_DDL:
                await db.execute(statement)

    asyncio.run(initialize())
    return tmp_path


async def _project_asset():
    project = await store.create_project("author", "离线项目", "16:9")
    image = io.BytesIO()
    Image.new("RGB", (640, 360), "#305070").save(image, format="PNG")
    data = image.getvalue()
    asset = await store.create_asset("author", project["id"], **storage.save_image(project["id"], data, storage.inspect_image(data)))
    return project, asset


async def _job(provider="wan", *, duration=5, now=None, project_asset=None):
    project, asset = project_asset or await _project_asset()
    quote = await store.create_quote("author", project["id"], {
        "provider": provider, "prompt": "固定相机，光线缓慢移动", "first_frame_asset_id": asset["id"],
        "duration": duration,
    }, now=now)
    return (await store.confirm_quote(quote["id"], "author", now=now))[0]


def _accepted(request):
    return httpx.Response(200, json={"output": {"task_id": "offline-task", "task_status": "PENDING"}}
                          if "maas.aliyuncs.com" in request.url.host else {"id": "offline-task"})


class BrokenResponse(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"output":'
        raise httpx.ReadError("private response")


@pytest.mark.parametrize("provider", ["wan", "seedance"])
@pytest.mark.parametrize("failure", ["timeout", "reset", "interrupted", "500", "502", "no_id", "bad_json", "400", "429"])
def test_paid_attempt_never_repeats_and_reservation_follows_certainty(studio_db, provider, failure):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        if failure == "timeout":
            raise httpx.ReadTimeout("private prompt", request=request)
        if failure == "reset":
            raise ConnectionResetError("private prompt")
        if failure == "interrupted":
            return httpx.Response(400, stream=BrokenResponse())
        if failure == "no_id":
            return httpx.Response(200, json={})
        if failure == "bad_json":
            return httpx.Response(200, content=b'{')
        return httpx.Response(int(failure), json={"error": {"code": "InputImagePortraitDetected", "message": "肖像闸拒绝"}})

    async def scenario():
        job = await _job(provider)
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler))
        await scheduler.tick()
        await scheduler.tick()
        await recover_studio_jobs()
        await scheduler.tick()
        result = await store.get_job(job["id"])
        if failure in {"400", "429"}:
            assert result["status"] == "rejected"
            assert result["reserved_cny"] == 0
            assert result["error_code"] == "InputImagePortraitDetected"
            assert result["error_message"] == "肖像闸拒绝"
            assert (await spend.today())["committed_cny"] == 0
        else:
            assert result["status"] == "uncertain"
            assert result["reserved_cny"] == job["reserved_cny"]
            assert (await spend.today())["committed_cny"] == job["reserved_cny"]
            assert "可能已扣费，请勿直接重试，去控制台核对" in result["error_message"]
        assert "private prompt" not in (result["error_message"] or "")

    asyncio.run(scenario())
    assert len(calls) == 1


def test_two_schedulers_obey_separate_provider_limits(studio_db, monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO_MAX_INFLIGHT_SEEDANCE", "2")
    calls = []

    def handler(request):
        calls.append(request)
        return _accepted(request)

    async def scenario():
        shared = await _project_asset()
        for _ in range(5):
            await _job(project_asset=shared)
        for _ in range(4):
            await _job("seedance", project_asset=shared)
        first = StudioScheduler(transport=httpx.MockTransport(handler))
        second = StudioScheduler(transport=httpx.MockTransport(handler))
        await asyncio.gather(first.tick(), second.tick())
        jobs = await store.list_jobs(shared[0]["id"], "author")
        assert sum(job["status"] == "submitted" and job["provider"] == "wan" for job in jobs) == 3
        assert sum(job["status"] == "submitted" and job["provider"] == "seedance" for job in jobs) == 2
        assert sum(job["status"] == "queued" for job in jobs) == 4

    asyncio.run(scenario())
    assert len(calls) == 5 and all(request.method == "POST" for request in calls)


def test_different_quotes_of_same_parameters_both_submit(studio_db):
    calls = []

    def handler(request):
        calls.append(request)
        return _accepted(request)

    async def scenario():
        shared = await _project_asset()
        one = await _job(project_asset=shared)
        two = await _job(project_asset=shared)
        assert one["fingerprint"] != two["fingerprint"]
        await StudioScheduler(transport=httpx.MockTransport(handler)).tick()
        assert (await store.get_job(one["id"]))["status"] == "submitted"
        assert (await store.get_job(two["id"]))["status"] == "submitted"

    asyncio.run(scenario())
    assert len(calls) == 2


def test_confirmed_job_remains_submittable_after_quote_expiry(studio_db):
    calls = []

    def handler(request):
        calls.append(request)
        return _accepted(request)

    async def scenario():
        earlier = datetime.now(timezone.utc) - timedelta(minutes=16)
        job = await _job(now=earlier)
        await StudioScheduler(transport=httpx.MockTransport(handler)).tick()
        assert (await store.get_job(job["id"]))["status"] == "submitted"

    asyncio.run(scenario())
    assert len(calls) == 1


def test_recovery_retains_states_and_never_sends_network(studio_db, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("恢复不得发送网络请求")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)

    async def scenario():
        jobs = {}
        for status in ("queued", "submitting", "submitted", "running", "succeeded"):
            job = await _job()
            if status != "queued":
                await store.cas_job(job["id"], "queued", {"status": "submitting", "run_token": job["id"]})
            if status in {"submitted", "running", "succeeded"}:
                await store.cas_job(job["id"], "submitting", {"status": "submitted", "task_id": "offline-task"})
            if status in {"running", "succeeded"}:
                await store.cas_job(job["id"], "submitted", {"status": "running"})
            if status == "succeeded":
                await store.cas_job(job["id"], "running", {"status": "succeeded"})
            jobs[status] = job
        await recover_studio_jobs()
        for before, job in jobs.items():
            result = await store.get_job(job["id"])
            assert result["status"] == ("uncertain" if before == "submitting" else before)
            assert result["reserved_cny"] == job["reserved_cny"]
            if before == "submitting":
                assert "服务重启时请求可能已发出" in result["error_message"]
            if before in {"submitted", "running", "succeeded"}:
                assert result["next_poll_at"] is not None

    asyncio.run(scenario())


def test_recovery_tolerates_database_before_schema_creation(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "empty.db"))
    asyncio.run(recover_studio_jobs())


def test_poll_intervals_timeout_and_manual_recheck_are_get_only(studio_db, monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO_POLL_TIMEOUT_MIN", "3")
    clock = [datetime.now(timezone.utc)]
    calls = []

    def handler(request):
        calls.append(request.method)
        return _accepted(request) if request.method == "POST" else httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    async def scenario():
        job = await _job()
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler), now=lambda: clock[0])
        await scheduler.tick()
        base = clock[0]
        clock[0] = base + timedelta(seconds=14)
        await scheduler.tick()
        assert calls == ["POST"]
        clock[0] = base + timedelta(seconds=15)
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "running"
        assert store.parse_time(result["next_poll_at"]) == base + timedelta(seconds=30)
        clock[0] = base + timedelta(seconds=120)
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert store.parse_time(result["next_poll_at"]) == base + timedelta(seconds=150)
        clock[0] = base + timedelta(seconds=181)
        await scheduler.tick()
        assert (await store.get_job(job["id"]))["needs_recheck"] == 1
        assert calls == ["POST", "GET", "GET"]
        await store.recheck_job(job["id"], "author")
        await scheduler.tick()
        assert calls == ["POST", "GET", "GET", "GET"]
        assert (await store.get_job(job["id"]))["needs_recheck"] == 1
        await scheduler.tick()
        assert len(calls) == 4

    asyncio.run(scenario())


def test_failed_read_retries_later_without_repeating_paid_post(studio_db):
    clock = [datetime.now(timezone.utc)]
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            return _accepted(request)
        if calls.count("GET") == 1:
            raise httpx.ReadTimeout("private text", request=request)
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    async def scenario():
        job = await _job()
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler), now=lambda: clock[0])
        await scheduler.tick()
        clock[0] += timedelta(seconds=15)
        await scheduler.tick()
        assert calls == ["POST", "GET"]
        assert (await store.get_job(job["id"]))["status"] == "submitted"
        await scheduler.tick()
        assert len(calls) == 2
        clock[0] += timedelta(seconds=15)
        await scheduler.tick()
        assert (await store.get_job(job["id"]))["status"] == "running"

    asyncio.run(scenario())
    assert calls == ["POST", "GET", "GET"]


@pytest.mark.parametrize("provider,expected_cost,fps", [("wan", 1.5, 30), ("seedance", 3.38268, 24)])
def test_verified_download_asset_and_actual_usage_settlement(studio_db, monkeypatch, provider, expected_cost, fps):
    fixture_name = "wan-20261016-131032.json" if provider == "wan" else "seedance-20261016-131134.json"
    fixture = json.loads((FIXTURES / fixture_name).read_text())
    payload = fixture["response"]
    if provider == "wan":
        payload["output"]["video_url"] = RESULT_URL
    else:
        payload["content"]["video_url"] = RESULT_URL
    clock = [datetime.now(timezone.utc)]
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json=fixture["submission_response"])
        if request.url.host.endswith("aliyuncs.com") and "oss-accelerate" in request.url.host:
            assert "authorization" not in request.headers and "cookie" not in request.headers
            return httpx.Response(200, content=b"mock-video-complete")
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(storage, "probe_video", lambda path: {
        "width": 852, "height": 480, "duration_s": 5, "fps": fps, "has_audio": True,
    })

    async def scenario():
        job = await _job(provider)
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler), now=lambda: clock[0])
        await scheduler.tick()
        clock[0] += timedelta(seconds=15)
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "downloaded"
        assert result["actual_cny"] == expected_cost
        assert result["reserved_cny"] == 0
        assert (await spend.today())["committed_cny"] == expected_cost
        asset = await store.get_asset(result["result_asset_id"], "author")
        assert asset["source"] == "generated" and asset["kind"] == "video"
        assert asset["fps"] == fps and asset["duration_s"] == 5
        assert storage.resolve_asset_path(asset).read_bytes() == b"mock-video-complete"
        assert not list(storage.storage_root().rglob("*.part"))
        await scheduler.tick()
        assert (await spend.today())["committed_cny"] == expected_cost

    asyncio.run(scenario())
    assert [request.method for request in calls] == ["POST", "GET", "GET"]


async def _succeeded_job(provider="wan", *, duration=5):
    job = await _job(provider, duration=duration)
    await store.cas_job(job["id"], "queued", {"status": "submitting", "run_token": "initial-token"})
    await store.cas_job(job["id"], "submitting", {"status": "submitted", "task_id": "offline-task"})
    await store.cas_job(job["id"], "submitted", {
        "status": "succeeded", "result_url": RESULT_URL,
        "usage_json": {"duration": 5, "SR": 480} if provider == "wan" else {"completion_tokens": 48324},
    })
    return job


@pytest.mark.parametrize("provider,requested,actual,expected", [
    ("wan", 5, 4.79, "failed"), ("seedance", 5, 4.79, "failed"),
    ("wan", 5, 4.8, "downloaded"), ("seedance", 5, 4.8, "downloaded"),
    ("wan", -1, 2.0, "downloaded"), ("seedance", -1, 4.0, "downloaded"),
])
def test_download_duration_tolerance_not_frame_count(studio_db, monkeypatch, provider, requested, actual, expected):
    monkeypatch.setattr(storage, "probe_video", lambda path: {
        "width": 852, "height": 480, "duration_s": actual, "fps": 24 if provider == "seedance" else 30, "has_audio": True,
    })
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"mock-video"))

    async def scenario():
        job = await _succeeded_job(provider, duration=requested)
        await StudioScheduler(transport=transport).tick()
        result = await store.get_job(job["id"])
        assert result["status"] == expected
        if expected == "failed":
            assert result["error_code"] == "short_output"
            assert not list(storage.storage_root().rglob("*.mp4"))
            assert result["result_asset_id"] is None
        assert result["actual_cny"] == (1.5 if provider == "wan" else 3.38268)

    asyncio.run(scenario())


@pytest.mark.parametrize("http_status", [403, 404])
def test_result_expiry_settles_usage(studio_db, http_status):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(http_status)

    async def scenario():
        job = await _succeeded_job()
        await StudioScheduler(transport=httpx.MockTransport(handler)).tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "expired" and result["actual_cny"] == 1.5
        assert result["reserved_cny"] == 0

    asyncio.run(scenario())
    assert calls == ["GET"]


def test_download_retries_at_most_three_per_tick_then_later(studio_db, monkeypatch):
    clock = [datetime.now(timezone.utc)]
    calls = []
    monkeypatch.setattr(storage, "probe_video", lambda path: {
        "width": 852, "height": 480, "duration_s": 5, "fps": 30, "has_audio": True,
    })

    def handler(request):
        calls.append(request.method)
        return httpx.Response(500) if len(calls) <= 3 else httpx.Response(200, content=b"mock-video")

    async def scenario():
        job = await _succeeded_job()
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler), now=lambda: clock[0])
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "succeeded" and result["reserved_cny"] == 1.5
        assert len(calls) == 3
        await scheduler.tick()
        assert len(calls) == 3
        clock[0] += timedelta(seconds=30)
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "downloaded" and result["error_code"] is None

    asyncio.run(scenario())
    assert calls == ["GET"] * 4


@pytest.mark.parametrize("provider,status,error,expected,cost", [
    ("wan", "FAILED", "UpstreamFailure", "failed", 1.5),
    ("wan", "UNKNOWN", "UnknownTask", "failed", 1.5),
    ("seedance", "failed", "UpstreamFailure", "failed", 3.38268),
    ("seedance", "failed", "OutputVideoSensitiveContentDetected", "filtered", 0),
])
def test_terminal_poll_state_settlement(studio_db, provider, status, error, expected, cost):
    clock = [datetime.now(timezone.utc)]

    def handler(request):
        if request.method == "POST":
            return _accepted(request)
        payload = {"output": {"task_status": status, "code": error, "message": "生成失败"}, "usage": {"duration": 5, "SR": 480}}
        if provider == "seedance":
            payload = {"status": status, "error": {"code": error, "message": "生成失败"}, "usage": {"completion_tokens": 48324}}
        return httpx.Response(200, json=payload)

    async def scenario():
        job = await _job(provider)
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler), now=lambda: clock[0])
        await scheduler.tick()
        clock[0] += timedelta(seconds=15)
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == expected and result["actual_cny"] == cost
        assert result["reserved_cny"] == 0

    asyncio.run(scenario())


def test_link_and_recheck_uncertain_only_send_get(studio_db):
    calls = []

    def handler(request):
        calls.append(request.method)
        assert request.method == "GET"
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    async def scenario():
        job = await _job()
        await store.cas_job(job["id"], "queued", {"status": "submitting"})
        await store.cas_job(job["id"], "submitting", {"status": "uncertain"})
        await store.link_task(job["id"], "author", "offline-task")
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler))
        await scheduler.tick()
        assert (await store.get_job(job["id"]))["status"] == "running"
        await store.cas_job(job["id"], "running", {"status": "uncertain", "needs_recheck": 1})
        await store.recheck_job(job["id"], "author")
        await scheduler.tick()
        assert (await store.get_job(job["id"]))["status"] == "running"

    asyncio.run(scenario())
    assert calls == ["GET", "GET"]


def test_disabled_scheduler_keeps_reservation_without_requests(studio_db, monkeypatch):
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request))

    async def scenario():
        job = await _job()
        monkeypatch.setenv("FIONA_STUDIO", "0")
        await StudioScheduler(transport=transport).tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "queued" and result["reserved_cny"] == 1.5

    asyncio.run(scenario())
    assert calls == []


def test_cancellation_during_submit_keeps_uncertain_and_no_second_post(studio_db):
    calls = []

    async def scenario():
        started = asyncio.Event()

        async def handler(request):
            calls.append(request.method)
            started.set()
            await asyncio.Event().wait()

        job = await _job()
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler))
        task = asyncio.create_task(scheduler.tick())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = await store.get_job(job["id"])
        assert result["status"] == "uncertain" and result["reserved_cny"] == 1.5
        await scheduler.tick()

    asyncio.run(scenario())
    assert calls == ["POST"]


def test_scheduler_loop_survives_exception_and_cancels(monkeypatch, caplog):
    async def scenario():
        seen = asyncio.Event()

        async def fail(self, **kwargs):
            seen.set()
            raise RuntimeError("private prompt and key")

        monkeypatch.setattr(StudioScheduler, "tick", fail)
        task = asyncio.create_task(run_scheduler(transport=httpx.MockTransport(lambda request: None)))
        await seen.wait()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert "scheduler_tick_error" in caplog.text
    assert "private prompt" not in caplog.text


def test_job_guard_logs_only_error_code_id_and_exception_type(caplog):
    async def fail(job):
        raise ValueError("private prompt and key https://signed.example/result?secret=value")

    async def scenario():
        scheduler = StudioScheduler(transport=httpx.MockTransport(lambda request: None))
        await scheduler._guard(fail, {"id": "offline-job"})

    asyncio.run(scenario())
    records = [record for record in caplog.records if record.name == "studio.scheduler"]
    assert len(records) == 1
    assert records[0].getMessage() == "studio code=job_tick_error id=offline-job error=ValueError"
    assert records[0].exc_info is None
    assert "private prompt" not in caplog.text
    assert "signed.example" not in caplog.text
    assert "secret=value" not in caplog.text


@pytest.mark.parametrize("provider", ["wan", "seedance"])
@pytest.mark.parametrize("initial_status", ["submitted", "succeeded"])
def test_succeeded_without_result_url_stops_at_timeout_and_allows_manual_get(
    studio_db, monkeypatch, provider, initial_status,
):
    monkeypatch.setenv("FIONA_STUDIO_POLL_TIMEOUT_MIN", "1")
    monkeypatch.setattr(storage, "probe_video", lambda path: {
        "width": 852, "height": 480, "duration_s": 5, "fps": 24, "has_audio": True,
    })
    clock = [datetime.now(timezone.utc)]
    calls = []
    result_ready = [False]

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if request.url.host == "offline.oss-accelerate.aliyuncs.com":
            return httpx.Response(200, content=b"mock-video-complete")
        url = RESULT_URL if result_ready[0] else None
        if provider == "wan":
            payload = {"output": {"task_status": "SUCCEEDED", "video_url": url}, "usage": {"duration": 5}}
        else:
            payload = {"status": "succeeded", "content": {"video_url": url}, "usage": {"completion_tokens": 48324}}
        return httpx.Response(200, json=payload)

    async def scenario():
        if initial_status == "succeeded":
            job = await _succeeded_job(provider)
            await store.cas_job(job["id"], "succeeded", {
                "result_url": None, "submitted_at": clock[0].isoformat(), "next_poll_at": None,
            })
        else:
            job = await _job(provider)
            await store.cas_job(job["id"], "queued", {"status": "submitting"})
            await store.cas_job(job["id"], "submitting", {
                "status": "submitted", "task_id": "offline-task", "submitted_at": clock[0].isoformat(),
            })
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler), now=lambda: clock[0])
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "succeeded" and not result["result_url"]
        assert result["needs_recheck"] == 0
        assert result["reserved_cny"] == job["reserved_cny"]
        clock[0] += timedelta(seconds=60)
        await scheduler.tick()
        assert (await store.get_job(job["id"]))["needs_recheck"] == 0
        before_timeout = len(calls)
        clock[0] += timedelta(seconds=31)
        await scheduler.tick()
        stopped = await store.get_job(job["id"])
        assert stopped["status"] == "succeeded" and stopped["needs_recheck"] == 1
        assert stopped["next_poll_at"] is None and stopped["error_code"] == "poll_timeout"
        assert stopped["reserved_cny"] == job["reserved_cny"]
        assert len(calls) == before_timeout
        clock[0] += timedelta(minutes=5)
        await scheduler.tick()
        assert len(calls) == before_timeout

        await store.recheck_job(job["id"], "author")
        await scheduler.tick()
        stopped = await store.get_job(job["id"])
        assert len(calls) == before_timeout + 1
        assert stopped["needs_recheck"] == 1 and stopped["poll_requested"] == 0
        assert stopped["next_poll_at"] is None and stopped["reserved_cny"] == job["reserved_cny"]
        await scheduler.tick()
        assert len(calls) == before_timeout + 1

        result_ready[0] = True
        await store.recheck_job(job["id"], "author")
        await scheduler.tick()
        downloaded = await store.get_job(job["id"])
        assert downloaded["status"] == "downloaded" and downloaded["needs_recheck"] == 0
        assert downloaded["poll_requested"] == 0 and downloaded["reserved_cny"] == 0
        assert len(calls) == before_timeout + 3

    asyncio.run(scenario())


@pytest.mark.parametrize("filtered", [False, True])
def test_restart_succeeded_without_url_refreshes_by_get(studio_db, monkeypatch, filtered):
    calls = []
    monkeypatch.setattr(storage, "probe_video", lambda path: {
        "width": 852, "height": 480, "duration_s": 5, "fps": 24, "has_audio": True,
    })

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if request.url.host == "ark.cn-beijing.volces.com":
            if filtered:
                return httpx.Response(200, json={"status": "failed", "error": {
                    "code": "OutputVideoSensitiveContentDetected", "message": "内容校验未通过",
                }})
            return httpx.Response(200, json={"status": "succeeded", "content": {"video_url": RESULT_URL},
                                            "usage": {"completion_tokens": 48324}})
        return httpx.Response(200, content=b"mock-video-complete")

    async def scenario():
        job = await _succeeded_job("seedance")
        await store.cas_job(job["id"], "succeeded", {"result_url": None, "usage_json": {}})
        await recover_studio_jobs()
        await StudioScheduler(transport=httpx.MockTransport(handler)).tick()
        result = await store.get_job(job["id"])
        assert result["status"] == ("filtered" if filtered else "downloaded")
        assert result["actual_cny"] == (0 if filtered else 3.38268)
        assert result["reserved_cny"] == 0

    asyncio.run(scenario())
    assert len(calls) == (1 if filtered else 2)


def test_known_task_id_survives_local_result_processing_failure(studio_db, monkeypatch):
    calls = []
    real_cas = store.cas_job

    async def broken_cas(job_id, expected_status, updates, **kwargs):
        if expected_status == "submitting" and updates.get("status") == "submitted":
            raise ValueError("private result processing failure")
        return await real_cas(job_id, expected_status, updates, **kwargs)

    monkeypatch.setattr(store, "cas_job", broken_cas)

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"output": {"task_id": "known-task"}})

    async def scenario():
        job = await _job()
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler))
        await scheduler.tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "uncertain" and result["task_id"] == "known-task"
        assert result["reserved_cny"] == 1.5
        await scheduler.tick()

    asyncio.run(scenario())
    assert calls == ["POST"]


def test_missing_local_first_frame_never_posts_or_keeps_a_reservation(studio_db):
    calls = []

    async def scenario():
        job = await _job()
        asset = await store.get_asset(job["params"]["first_frame_asset_id"], "author")
        storage.resolve_asset_path(asset).unlink()
        await StudioScheduler(transport=httpx.MockTransport(lambda request: calls.append(request))).tick()
        result = await store.get_job(job["id"])
        assert result["status"] == "failed" and result["actual_cny"] == 0
        assert result["reserved_cny"] == 0 and result["error_code"] == "missing_first_frame"

    asyncio.run(scenario())
    assert calls == []


def test_production_tick_does_not_wait_for_slow_paid_post(studio_db):
    calls = []

    async def scenario():
        started = asyncio.Event()

        async def handler(request):
            calls.append(request.method)
            started.set()
            await asyncio.Event().wait()

        job = await _job()
        scheduler = StudioScheduler(transport=httpx.MockTransport(handler))
        await asyncio.wait_for(scheduler.tick(wait=False), timeout=1)
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.wait_for(scheduler.tick(wait=False), timeout=1)
        assert calls == ["POST"]
        await scheduler.close()
        result = await store.get_job(job["id"])
        assert result["status"] == "uncertain" and result["reserved_cny"] == 1.5
        assert not scheduler._tasks

    asyncio.run(scenario())


def test_stopping_scheduler_loop_cancels_all_paid_workers(studio_db):
    calls = []

    async def scenario():
        started = asyncio.Event()

        async def handler(request):
            calls.append(request.method)
            started.set()
            await asyncio.Event().wait()

        job = await _job()
        task = asyncio.create_task(run_scheduler(transport=httpx.MockTransport(handler)))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = await store.get_job(job["id"])
        assert result["status"] == "uncertain" and result["reserved_cny"] == 1.5
        assert not [pending for pending in asyncio.all_tasks() if pending.get_name().startswith("studio-")]

    asyncio.run(scenario())
    assert calls == ["POST"]


def test_late_download_after_account_cleanup_cannot_revive_files(studio_db, monkeypatch):
    real_download = storage.download_video
    monkeypatch.setattr(storage, "probe_video", lambda path: {
        "width": 852, "height": 480, "duration_s": 5, "fps": 30, "has_audio": True,
    })

    async def late_download(url, project_id, job_id, **kwargs):
        async with store.connection(transaction=True) as db:
            for table in ("studio_jobs", "studio_quotes", "studio_assets", "studio_projects"):
                await db.execute(f"DELETE FROM {table} WHERE owner='author'")
        shutil.rmtree(storage.storage_root() / project_id)
        return await real_download(url, project_id, job_id, **kwargs)

    monkeypatch.setattr(storage, "download_video", late_download)

    async def scenario():
        job = await _succeeded_job()
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"late-video"))
        await StudioScheduler(transport=transport).tick()
        assert not (storage.storage_root() / job["project_id"]).exists()
        async with store.connection() as db:
            async with db.execute("SELECT COUNT(*) FROM studio_assets") as cursor:
                assert (await cursor.fetchone())[0] == 0

    asyncio.run(scenario())
