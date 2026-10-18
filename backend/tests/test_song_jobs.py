# -*- coding: utf-8 -*-
"""写歌版本状态机、计费、退款、轮询、恢复与 lifespan 接线测试（全离线）。"""
import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from song.volc import SubmitRejected, SubmitUncertain


def _run(coroutine):
    return asyncio.run(coroutine)


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


_STRUCTURE = [
    {"id": "s1", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
    {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
]
_SECTIONS = [
    {"id": "s1", "lines": ["风吹过山岗", "云落在远方"]},
    {"id": "s2", "lines": ["我们一起唱", "唱到天亮"]},
]
_PROVIDER_TEXT = (
    "[verse]\n风吹过山岗\n云落在远方\n[chorus]\n我们一起唱\n唱到天亮"
)


def _good_check() -> dict:
    return {
        "ok": True,
        "errors": [],
        "warnings": [],
        "lines": [],
        "provider_text": _PROVIDER_TEXT,
        "provider_chars": len(_PROVIDER_TEXT),
    }


@pytest.fixture
def song_env(tmp_path, monkeypatch):
    """临时库 + 临时音频目录 + 假 AK/SK；非 DEV_MODE。"""
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "songs"))
    monkeypatch.setenv("VOLC_MUSIC_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLC_MUSIC_SECRET_KEY", "test-sk")
    monkeypatch.delenv("FIONA_SONG_AGENT", raising=False)
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("STRAWBERRY_DAILY_REFILL", raising=False)
    monkeypatch.delenv("FIONA_SONG_STRAWBERRIES", raising=False)
    monkeypatch.delenv("FIONA_DAILY_SONGS", raising=False)
    monkeypatch.delenv("FIONA_SONG_MAX_INFLIGHT", raising=False)

    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "song.db"))
    _run(database.init_db())
    return tmp_path


@pytest.fixture
def scheduled(monkeypatch):
    """拦住 create_generation / recover 调度的提交协程，避免后台竞态。"""
    import song.jobs as jobs

    calls = []

    def fake_create_task(coroutine, *, label):
        calls.append((label, coroutine))
        coroutine.close()

    monkeypatch.setattr(jobs, "create_background_task", fake_create_task)
    return calls


class FakeProvider:
    def __init__(self, *, submit_result="task-1", submit_error=None, query_results=None):
        self.submit_result = submit_result
        self.submit_error = submit_error
        self.query_results = list(query_results or [])
        self.submitted = []
        self.queried = []

    async def submit(self, params):
        self.submitted.append(params)
        if self.submit_error is not None:
            raise self.submit_error
        return self.submit_result

    async def query(self, task_id):
        self.queried.append(task_id)
        result = self.query_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _use_provider(monkeypatch, provider) -> None:
    import song.jobs as jobs

    monkeypatch.setattr(jobs, "get_provider", lambda: provider)


async def _seed_user(owner="alice", balance=100) -> None:
    import database

    await database.get_or_create_user(owner)
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            """UPDATE users SET strawberry_balance = ?, strawberry_refill_date = NULL
                WHERE username = ?""",
            (balance, owner),
        )


def _balance(owner="alice") -> int:
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute(
            "SELECT strawberry_balance FROM users WHERE username = ?", (owner,)
        ).fetchone()[0]


async def _seed_project(owner="alice", *, ok=True):
    import song.store as store

    await _seed_user(owner)
    project = await store.create_project(
        owner_username=owner,
        conversation_id="conv-1",
        title="测试歌曲",
        brief={"theme": "夏天", "language": "Chinese", "duration_seconds": 60},
        structure=_STRUCTURE,
    )
    check = _good_check()
    if not ok:
        check = dict(check)
        check["ok"] = False
        check["errors"] = [
            {"code": "line_too_long", "section_id": "s1", "line_index": 0,
             "message": "主歌第 1 行超过 30 字"}
        ]
    saved = await store.save_lyrics(
        project["id"],
        owner_username=owner,
        conversation_id="conv-1",
        base_revision=0,
        sections=_SECTIONS,
        check=check,
        changed_section_ids=[],
    )
    assert saved["status"] == "ok"
    return project, saved["lyrics"]


def _version_row(version_id):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM song_versions WHERE id = ?", (version_id,)
        ).fetchone()
    return dict(row) if row is not None else None


def _version_count():
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute("SELECT COUNT(*) FROM song_versions").fetchone()[0]


def _insert_version(
    project_id,
    *,
    owner="alice",
    status="submitted",
    billing_state="reserved",
    strawberries=30,
    task_id="task-1",
    next_poll_at=None,
    deadline_at=None,
    created_at=None,
    audio_rel_path=None,
):
    import song.jobs as jobs

    version_id = uuid4().hex
    params = json.dumps(
        {"Lyrics": _PROVIDER_TEXT, "ModelVersion": "v4.3"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    with sqlite3.connect(jobs.database.DB_PATH) as db:
        db.execute(
            """INSERT INTO song_versions
                   (id, project_id, owner_username, lyrics_revision, provider,
                    params_json, status, provider_task_id, progress, strawberries,
                    billing_state, idempotency_key, audio_rel_path, next_poll_at,
                    deadline_at, created_day, created_at)
               VALUES (?, ?, ?, 1, 'volc', ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                version_id,
                project_id,
                owner,
                params,
                status,
                task_id,
                strawberries,
                billing_state,
                "idem_" + uuid4().hex,
                audio_rel_path,
                next_poll_at,
                deadline_at,
                jobs._today_shanghai(),
                created_at or _ts(time.time()),
            ),
        )
    return version_id


def _set_version(version_id, **values) -> None:
    import database

    assignments = ", ".join(f"{key} = ?" for key in values)
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            f"UPDATE song_versions SET {assignments} WHERE id = ?",
            (*values.values(), version_id),
        )


class _Clock:
    """让轮询测试使用固定 now，同时保持 created_at 是真实 UTC 文本。"""

    def __init__(self):
        self.now = time.time()


# ------------------------------------------------------------------ 创建 / 计费
def test_create_generation_charges_once_and_freezes_params(song_env, scheduled):
    import song.jobs as jobs

    async def scenario():
        project, lyrics = await _seed_project()
        result = await jobs.create_generation(
            "alice", project["id"], 1, "idem_key_0001"
        )
        assert result["status"] == "queued"
        assert result["progress"] == 0
        assert result["lyrics_revision"] == 1
        assert set(result) == {
            "id", "project_id", "lyrics_revision", "status", "progress",
            "failure_message", "duration_s", "created_at",
        }
        row = _version_row(result["id"])
        assert row["status"] == "queued"
        assert row["billing_state"] == "reserved"
        assert row["strawberries"] == 30
        assert row["provider"] == "volc"
        assert _balance() == 70
        assert len(scheduled) == 1 and scheduled[0][0] == "song-submit"

        params = json.loads(row["params_json"])
        assert params["Lyrics"] == lyrics["check"]["provider_text"]
        assert params["ModelVersion"] == "v4.3"
        assert params["Duration"] == 60
        assert params["Lang"] == "Chinese"
        assert params["ImplicitWaterMark"]["ProduceId"] == result["id"]

        # 返回给前端/Claude 的版本不含冻结参数。
        assert "params" not in result
        assert "sk-" not in json.dumps(result)

    _run(scenario())


def test_create_generation_is_idempotent_before_lyrics_checks(song_env, scheduled):
    import song.jobs as jobs
    import song.store as store

    async def scenario():
        project, _lyrics = await _seed_project()
        first = await jobs.create_generation(
            "alice", project["id"], 1, "idem_repeat_01"
        )
        # 再存一稿：旧幂等键重放必须返回旧版本，而不是 409。
        good = _good_check()
        saved = await store.save_lyrics(
            project["id"],
            owner_username="alice",
            conversation_id="conv-1",
            base_revision=1,
            sections=_SECTIONS,
            check=good,
            changed_section_ids=[],
        )
        assert saved["status"] == "ok"
        second = await jobs.create_generation(
            "alice", project["id"], 1, "idem_repeat_01"
        )
        assert second["id"] == first["id"]
        assert _balance() == 70
        assert _version_count() == 1
        assert len(scheduled) == 1

    _run(scenario())


def test_create_generation_validation_errors(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def error_of(coroutine):
        with pytest.raises(jobs.SongError) as caught:
            await coroutine
        return caught.value

    async def scenario():
        project, _lyrics = await _seed_project()
        missing = await error_of(
            jobs.create_generation("alice", "not-a-project", 1, "idem_missing_1")
        )
        assert missing.status_code == 404

        await _seed_user("bob")
        foreign = await error_of(
            jobs.create_generation("bob", project["id"], 1, "idem_foreign_1")
        )
        assert foreign.status_code == 404

        stale = await error_of(
            jobs.create_generation("alice", project["id"], 0, "idem_stale_001")
        )
        assert stale.status_code == 409
        assert stale.detail == "歌词已更新，请刷新"
        assert _version_count() == 0

        bad_project, _ = await _seed_project("carol", ok=False)
        bad = await error_of(
            jobs.create_generation("carol", bad_project["id"], 1, "idem_bad_0001")
        )
        assert bad.status_code == 409
        assert bad.detail == "歌词有未解决的问题"

        monkeypatch.delenv("VOLC_MUSIC_SECRET_KEY")
        unconfigured = await error_of(
            jobs.create_generation("alice", project["id"], 1, "idem_nocfg_001")
        )
        assert unconfigured.status_code == 409
        assert unconfigured.detail == "写歌服务未配置"
        assert _balance("alice") == 100

    _run(scenario())


def test_create_generation_insufficient_balance(song_env, scheduled):
    import database
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=10)
        with pytest.raises(jobs.SongError) as caught:
            await jobs.create_generation(
                "alice", project["id"], 1, "idem_broke_001"
            )
        assert caught.value.status_code == 402
        assert caught.value.detail == database.strawberry_insufficient_message()
        assert _balance() == 10
        assert _version_count() == 0
        assert scheduled == []

    _run(scenario())


def test_create_generation_inflight_and_daily_limits(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=500)

        monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "1")
        ok = await jobs.create_generation(
            "alice", project["id"], 1, "idem_inflight_1"
        )
        assert ok["status"] == "queued"
        with pytest.raises(jobs.SongError) as inflight:
            await jobs.create_generation(
                "alice", project["id"], 1, "idem_inflight_2"
            )
        assert inflight.value.status_code == 429
        assert "同时在途" in inflight.value.detail
        assert _version_count() == 1

    _run(scenario())


def test_create_generation_daily_limit(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=500)

        monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "5")
        monkeypatch.setenv("FIONA_DAILY_SONGS", "1")
        await jobs.create_generation("alice", project["id"], 1, "idem_daily_0001")
        with pytest.raises(jobs.SongError) as daily:
            await jobs.create_generation(
                "alice", project["id"], 1, "idem_daily_0002"
            )
        assert daily.value.status_code == 429
        assert "今天生成歌曲的次数已用完" in daily.value.detail
        assert _version_count() == 1

    _run(scenario())


def test_dev_mode_does_not_reserve_or_refund(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def scenario():
        monkeypatch.setenv("DEV_MODE", "1")
        project, _lyrics = await _seed_project()
        result = await jobs.create_generation(
            "alice", project["id"], 1, "idem_devmode_1"
        )
        row = _version_row(result["id"])
        assert row["billing_state"] == "none"
        assert _balance() == 100
        assert await jobs.refund_version(result["id"]) is False
        assert _balance() == 100

    _run(scenario())


# ------------------------------------------------------------------ 提交
def test_submit_success_records_task_and_deadlines(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_submit_001"
        )
        provider = FakeProvider(submit_result="task-abc")
        _use_provider(monkeypatch, provider)
        await jobs.submit_version(version["id"])
        row = _version_row(version["id"])
        assert row["status"] == "submitted"
        assert row["provider_task_id"] == "task-abc"
        assert row["billing_state"] == "reserved"
        assert row["next_poll_at"] == pytest.approx(time.time() + 5, abs=5)
        assert row["deadline_at"] == pytest.approx(time.time() + 900, abs=10)
        assert len(provider.submitted) == 1
        assert provider.submitted[0]["Lyrics"] == _PROVIDER_TEXT

        # 已经 submitted 的版本不得重复付费提交。
        await jobs.submit_version(version["id"])
        assert len(provider.submitted) == 1

    _run(scenario())


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (SubmitRejected("HTTP_400"), "rejected"),
        (SubmitUncertain("transport_error"), "uncertain"),
    ],
)
def test_submit_rejected_or_uncertain_refunds_once(
    song_env, scheduled, monkeypatch, error, expected_status
):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_submit_" + expected_status
        )
        _use_provider(monkeypatch, FakeProvider(submit_error=error))
        await jobs.submit_version(version["id"])
        row = _version_row(version["id"])
        assert row["status"] == expected_status
        assert row["billing_state"] == "refunded"
        assert row["failure_code"] == str(error.code)
        assert _balance() == 100
        assert await jobs.refund_version(version["id"]) is False
        assert _balance() == 100

    _run(scenario())


def test_submit_unknown_exception_is_uncertain_and_private(
    song_env, scheduled, monkeypatch, capsys
):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_unknown_01"
        )
        _use_provider(monkeypatch, FakeProvider(submit_error=RuntimeError("secret body")))
        await jobs.submit_version(version["id"])
        row = _version_row(version["id"])
        assert row["status"] == "uncertain"
        assert row["billing_state"] == "refunded"
        assert _balance() == 100

    _run(scenario())
    captured = capsys.readouterr()
    assert "secret body" not in captured.out + captured.err
    assert "code=submit_unknown" in captured.out


# ------------------------------------------------------------------ 轮询
def test_poll_running_updates_progress_and_interval(song_env, scheduled, monkeypatch):
    import song.jobs as jobs
    import song.volc as volc

    async def scenario():
        project, _lyrics = await _seed_project()
        now = time.time()
        recent = _insert_version(
            project["id"], status="submitted", created_at=_ts(now - 10),
            next_poll_at=now - 1, deadline_at=now + 900,
        )
        provider = FakeProvider(query_results=[
            {"state": "waiting", "progress": 7, "audio_url": None,
             "duration": None, "captions_raw": None,
             "failure_code": None, "failure_msg": None},
            {"state": "running", "progress": 55, "audio_url": None,
             "duration": None, "captions_raw": None,
             "failure_code": None, "failure_msg": None},
        ])
        _use_provider(monkeypatch, provider)
        await jobs.poll_once(now)
        row = _version_row(recent)
        assert row["status"] == "running"
        assert row["progress"] == 7
        assert row["next_poll_at"] == pytest.approx(now + 5, abs=0.001)

        _set_version(recent, created_at=_ts(now - 120), next_poll_at=now - 1)
        await jobs.poll_once(now + 1)
        row = _version_row(recent)
        assert row["progress"] == 55
        assert row["next_poll_at"] == pytest.approx(now + 11, abs=0.001)
        assert provider.queried == ["task-1", "task-1"]

    _run(scenario())


def test_poll_succeeded_downloads_and_settles(song_env, scheduled, monkeypatch):
    import song.jobs as jobs
    import song.media as media

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_success_01"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-ok",
            next_poll_at=now - 1, deadline_at=now + 900,
        )
        download_calls = []

        async def fake_download(audio_url, *, version_id, title, transport=None):
            row = _version_row(version["id"])
            assert row["status"] == "downloading"
            download_calls.append((audio_url, version_id, title))
            import song.config as config

            config.song_dir().mkdir(parents=True, exist_ok=True)
            (config.song_dir() / f"{version_id}.mp3").write_bytes(b"fake-mp3")
            return {
                "audio_rel_path": f"{version_id}.mp3",
                "duration_s": 62.5,
            }

        monkeypatch.setattr(media, "download_and_store", fake_download)
        _use_provider(monkeypatch, FakeProvider(query_results=[{
            "state": "succeeded", "progress": 100,
            "audio_url": "https://v1-default.douyinvod.com/a.mp3",
            "duration": 62.5, "captions_raw": "{}",
            "failure_code": None, "failure_msg": None,
        }]))
        await jobs.poll_once(now)
        row = _version_row(version["id"])
        assert row["status"] == "succeeded"
        assert row["billing_state"] == "settled"
        assert row["audio_rel_path"] == f"{version['id']}.mp3"
        assert row["duration_s"] == 62.5
        assert row["captions_raw"] == "{}"
        assert row["progress"] == 100
        assert _balance() == 70
        assert download_calls == [(
            "https://v1-default.douyinvod.com/a.mp3",
            version["id"],
            "测试歌曲",
        )]

    _run(scenario())


def test_poll_media_error_marks_failed_and_refunds(song_env, scheduled, monkeypatch):
    import song.jobs as jobs
    import song.media as media

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_mediafail1"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-x",
            next_poll_at=now - 1, deadline_at=now + 900,
        )

        async def broken_download(*args, **kwargs):
            raise media.MediaError("invalid_audio")

        monkeypatch.setattr(media, "download_and_store", broken_download)
        _use_provider(monkeypatch, FakeProvider(query_results=[{
            "state": "succeeded", "progress": 100,
            "audio_url": "https://v1-default.douyinvod.com/a.mp3",
            "duration": 62.5, "captions_raw": "{}",
            "failure_code": None, "failure_msg": None,
        }]))
        await jobs.poll_once(now)
        row = _version_row(version["id"])
        assert row["status"] == "failed"
        assert row["failure_code"] == "invalid_audio"
        assert row["failure_message"] == jobs.GENERIC_FAILURE_MESSAGE
        assert row["billing_state"] == "refunded"
        assert _balance() == 100

    _run(scenario())


def test_poll_download_unexpected_marks_failed_and_refunds(
    song_env, scheduled, monkeypatch, capsys
):
    import song.jobs as jobs
    import song.media as media

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_downunexp"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-u",
            next_poll_at=now - 1, deadline_at=now + 900,
        )

        async def broken_download(*args, **kwargs):
            raise RuntimeError("download boom")

        monkeypatch.setattr(media, "download_and_store", broken_download)
        _use_provider(monkeypatch, FakeProvider(query_results=[{
            "state": "succeeded", "progress": 100,
            "audio_url": "https://v1-default.douyinvod.com/a.mp3",
            "duration": 62.5, "captions_raw": "{}",
            "failure_code": None, "failure_msg": None,
        }]))
        await jobs.poll_once(now)
        row = _version_row(version["id"])
        assert row["status"] == "failed"
        assert row["failure_code"] == "download_unexpected"
        assert row["failure_message"] == jobs.GENERIC_FAILURE_MESSAGE
        assert row["billing_state"] == "refunded"
        assert _balance() == 100
        assert await jobs.refund_version(version["id"]) is False
        assert _balance() == 100

    _run(scenario())
    captured = capsys.readouterr()
    assert "download boom" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("failure_code", "failure_msg", "expected"),
    [
        (300061, "InputLyricsPlagiarized", "歌词疑似与已有作品重复，请改写后再试"),
        (None, "InputLyricsPlagiarized", "歌词疑似与已有作品重复，请改写后再试"),
        (500123, "InternalError", "生成失败，请稍后再试"),
    ],
)
def test_poll_failed_messages_and_refund(
    song_env, scheduled, monkeypatch, failure_code, failure_msg, expected
):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_failed_" + str(failure_code)
        )
        now = time.time()
        _set_version(
            version["id"], status="running", provider_task_id="task-f",
            next_poll_at=now - 1, deadline_at=now + 900,
        )
        _use_provider(monkeypatch, FakeProvider(query_results=[{
            "state": "failed", "progress": 40,
            "audio_url": None, "duration": None, "captions_raw": None,
            "failure_code": failure_code, "failure_msg": failure_msg,
        }]))
        await jobs.poll_once(now)
        row = _version_row(version["id"])
        assert row["status"] == "failed"
        assert row["failure_message"] == expected
        assert row["failure_code"] == (
            str(failure_code) if failure_code is not None else None
        )
        assert row["billing_state"] == "refunded"
        assert _balance() == 100

    _run(scenario())


def test_poll_error_only_postpones(song_env, scheduled, monkeypatch):
    import song.jobs as jobs
    import song.volc as volc

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_pollerr_01"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-e",
            next_poll_at=now - 1, deadline_at=now + 900,
        )
        _use_provider(monkeypatch, FakeProvider(
            query_results=[volc.PollError("transport_error")]
        ))
        await jobs.poll_once(now)
        row = _version_row(version["id"])
        assert row["status"] == "submitted"
        assert row["next_poll_at"] == pytest.approx(now + 10, abs=0.001)
        assert row["billing_state"] == "reserved"
        assert _balance() == 70

    _run(scenario())


def test_poll_unexpected_query_error_postpones_and_continues(
    song_env, monkeypatch, capsys
):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        now = time.time()
        # A 先到期，B 后到期，保证 _due_versions 的处理顺序。
        first = _insert_version(
            project["id"], status="submitted", task_id="task-a",
            next_poll_at=now - 2, deadline_at=now + 900,
            created_at=_ts(now - 120),
        )
        second = _insert_version(
            project["id"], status="running", task_id="task-b",
            next_poll_at=now - 1, deadline_at=now + 900,
            created_at=_ts(now - 120),
        )
        provider = FakeProvider(query_results=[
            RuntimeError("boom"),
            {"state": "running", "progress": 42, "audio_url": None,
             "duration": None, "captions_raw": None,
             "failure_code": None, "failure_msg": None},
        ])
        _use_provider(monkeypatch, provider)

        await jobs.poll_once(now)

        row_a = _version_row(first)
        assert row_a["status"] == "submitted"
        assert row_a["next_poll_at"] == pytest.approx(now + 10, abs=0.001)
        row_b = _version_row(second)
        assert row_b["status"] == "running"
        assert row_b["progress"] == 42
        assert row_b["next_poll_at"] == pytest.approx(now + 10, abs=0.001)
        assert provider.queried == ["task-a", "task-b"]

    _run(scenario())
    captured = capsys.readouterr()
    assert "boom" not in captured.out + captured.err
    assert "code=poll_unexpected" in captured.out


def test_poll_expired_refunds_without_query(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_expired_01"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-d",
            next_poll_at=now - 1, deadline_at=now - 1,
        )
        provider = FakeProvider(query_results=[])
        _use_provider(monkeypatch, provider)
        await jobs.poll_once(now)
        row = _version_row(version["id"])
        assert row["status"] == "expired"
        assert row["billing_state"] == "refunded"
        assert _balance() == 100
        assert provider.queried == []

    _run(scenario())


def test_refund_is_idempotent_under_concurrency(song_env, scheduled):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_concurrent"
        )
        assert _balance() == 70
        results = await asyncio.gather(
            jobs.refund_version(version["id"]),
            jobs.refund_version(version["id"]),
        )
        assert sorted(results) == [False, True]
        assert _balance() == 100
        assert await jobs.refund_version(version["id"]) is False
        assert _balance() == 100

    _run(scenario())


# ------------------------------------------------------------------ 退款对账
def test_reconcile_refunds_terminal_reserved_once(song_env):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=0)
        statuses = ("failed", "rejected", "uncertain", "expired")
        version_ids = [
            _insert_version(
                project["id"], status=status, billing_state="reserved",
                strawberries=30,
            )
            for status in statuses
        ]

        assert await jobs.reconcile_refunds() == 4
        assert _balance() == 120
        for version_id, status in zip(version_ids, statuses):
            row = _version_row(version_id)
            assert row["status"] == status
            assert row["billing_state"] == "refunded"

        # 幂等：已退回的不再退，余额不变。
        assert await jobs.reconcile_refunds() == 0
        assert _balance() == 120

    _run(scenario())


def test_reconcile_refunds_ignores_non_terminal_and_succeeded(song_env):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=0)
        untouched = {
            "succeeded": _insert_version(
                project["id"], status="succeeded", billing_state="reserved"
            ),
            "running": _insert_version(
                project["id"], status="running", billing_state="reserved"
            ),
            "downloading": _insert_version(
                project["id"], status="downloading", billing_state="reserved"
            ),
        }
        failed = _insert_version(
            project["id"], status="failed", billing_state="reserved"
        )

        assert await jobs.reconcile_refunds() == 1
        assert _balance() == 30
        for status, version_id in untouched.items():
            row = _version_row(version_id)
            assert row["status"] == status
            assert row["billing_state"] == "reserved"
        assert _version_row(failed)["status"] == "failed"
        assert _version_row(failed)["billing_state"] == "refunded"

    _run(scenario())


def test_reconcile_refunds_skips_missing_user(song_env):
    import database
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = _insert_version(
            project["id"], status="failed", billing_state="reserved"
        )
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("DELETE FROM users WHERE username = 'alice'")

        assert await jobs.reconcile_refunds() == 0
        row = _version_row(version)
        assert row["status"] == "failed"
        assert row["billing_state"] == "reserved"

    _run(scenario())


def test_reconcile_refunds_after_rejected_refund_failure(
    song_env, scheduled, monkeypatch
):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_recon_after"
        )
        _use_provider(
            monkeypatch, FakeProvider(submit_error=SubmitRejected("HTTP_400"))
        )

        original_refund = jobs.refund_version
        calls = []

        async def flaky_refund(version_id):
            calls.append(version_id)
            if len(calls) == 1:
                raise RuntimeError("refund boom")
            return await original_refund(version_id)

        monkeypatch.setattr(jobs, "refund_version", flaky_refund)

        # 提交被拒后第一次退款抛异常：版本已是 rejected，但钱还没退。
        with pytest.raises(RuntimeError):
            await jobs.submit_version(version["id"])
        row = _version_row(version["id"])
        assert row["status"] == "rejected"
        assert row["billing_state"] == "reserved"
        assert _balance() == 70
        assert calls == [version["id"]]

        assert await jobs.reconcile_refunds() == 1
        row = _version_row(version["id"])
        assert row["status"] == "rejected"
        assert row["billing_state"] == "refunded"
        assert _balance() == 100

    _run(scenario())


# ------------------------------------------------------------------ 恢复 / 删号
def test_recover_on_startup_handles_each_status(song_env, scheduled, monkeypatch):
    import song.jobs as jobs

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=100)
        now = time.time()
        submitting = _insert_version(
            project["id"], status="submitting", next_poll_at=None
        )
        queued = _insert_version(project["id"], status="queued", next_poll_at=None)
        downloading = _insert_version(
            project["id"], status="downloading", next_poll_at=None
        )
        submitted = _insert_version(
            project["id"], status="submitted", next_poll_at=now + 5,
            deadline_at=now + 900,
        )
        running = _insert_version(
            project["id"], status="running", next_poll_at=now + 5,
            deadline_at=now + 900,
        )

        await jobs.recover_on_startup()

        assert _version_row(submitting)["status"] == "uncertain"
        assert _version_row(submitting)["billing_state"] == "refunded"
        assert _balance() == 130
        assert _version_row(queued)["status"] == "queued"
        assert _version_row(downloading)["status"] == "running"
        assert _version_row(downloading)["next_poll_at"] <= time.time()
        assert _version_row(submitted)["status"] == "submitted"
        assert _version_row(submitted)["next_poll_at"] == pytest.approx(now + 5)
        assert _version_row(running)["status"] == "running"
        assert [label for label, _ in scheduled] == ["song-submit"]

    _run(scenario())


def test_deleted_account_stops_poll_writes_and_removes_download(
    song_env, scheduled, monkeypatch
):
    import song.jobs as jobs
    import song.media as media

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_deleted_01"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-r",
            next_poll_at=now - 1, deadline_at=now + 900,
        )
        deleted = {"done": False}

        async def fake_download(audio_url, *, version_id, title, transport=None):
            # 下载期间账号被删：行还在，但 users 行没了。
            import database

            with sqlite3.connect(database.DB_PATH) as db:
                db.execute("DELETE FROM users WHERE username = 'alice'")
            deleted["done"] = True
            import song.config as config

            target = config.song_dir() / f"{version_id}.mp3"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"orphan")
            return {"audio_rel_path": f"{version_id}.mp3", "duration_s": 62.5}

        monkeypatch.setattr(media, "download_and_store", fake_download)
        _use_provider(monkeypatch, FakeProvider(query_results=[{
            "state": "succeeded", "progress": 100,
            "audio_url": "https://v1-default.douyinvod.com/a.mp3",
            "duration": 62.5, "captions_raw": "{}",
            "failure_code": None, "failure_msg": None,
        }]))
        await jobs.poll_once(now)

        assert deleted["done"] is True
        row = _version_row(version["id"])
        assert row["status"] == "downloading"
        import song.config as config

        assert not (config.song_dir() / f"{version['id']}.mp3").exists()

    _run(scenario())


def test_deleted_account_skips_download_entirely(song_env, scheduled, monkeypatch):
    import song.jobs as jobs
    import song.media as media

    async def scenario():
        project, _lyrics = await _seed_project()
        version = await jobs.create_generation(
            "alice", project["id"], 1, "idem_deleted_02"
        )
        now = time.time()
        _set_version(
            version["id"], status="submitted", provider_task_id="task-r2",
            next_poll_at=now - 1, deadline_at=now + 900,
        )
        import database

        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("DELETE FROM users WHERE username = 'alice'")

        called = []

        async def fake_download(*args, **kwargs):
            called.append(True)
            return {"audio_rel_path": "x.mp3", "duration_s": 10}

        monkeypatch.setattr(media, "download_and_store", fake_download)
        _use_provider(monkeypatch, FakeProvider(query_results=[{
            "state": "succeeded", "progress": 100,
            "audio_url": "https://v1-default.douyinvod.com/a.mp3",
            "duration": 62.5, "captions_raw": "{}",
            "failure_code": None, "failure_msg": None,
        }]))
        await jobs.poll_once(now)
        assert called == []
        assert _version_row(version["id"])["status"] == "submitted"

    _run(scenario())


# ------------------------------------------------------------------ lifespan
def test_lifespan_song_wiring_only_when_enabled(monkeypatch, tmp_path):
    import exchange_store
    import main
    import novel.runner
    import song.jobs
    import song.media
    import studio.config
    import studio.recovery
    import studio.scheduler

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "init_db", noop)
    monkeypatch.setattr(main, "_run_upload_cleanup_once", noop)
    monkeypatch.setattr(main, "shutdown_background_tasks", noop)
    monkeypatch.setattr(exchange_store, "recover_interrupted_exchanges", noop)
    monkeypatch.setattr(novel.runner, "recover_interrupted_novels", noop)
    monkeypatch.setattr(novel.runner, "shutdown_novel_tasks", noop)
    monkeypatch.setattr(studio.recovery, "recover_studio_jobs", noop)

    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(studio.scheduler, "run_scheduler", idle)
    monkeypatch.setattr(
        studio.config, "get_settings", lambda: SimpleNamespace(enabled=False)
    )

    labels = []

    def fake_task(coroutine, *, label):
        labels.append(label)
        coroutine.close()

    monkeypatch.setattr(main, "create_background_task", fake_task)

    calls = []

    async def record(name):
        calls.append(name)

    monkeypatch.setattr(song.media, "drain_cleanup_queue", lambda: record("drain"))
    monkeypatch.setattr(song.media, "cleanup_orphans", lambda: record("orphans"))
    monkeypatch.setattr(song.jobs, "recover_on_startup", lambda: record("recover"))
    monkeypatch.setattr(song.jobs, "reconcile_refunds", lambda: record("reconcile"))

    async def fake_poller():
        calls.append("poller")

    monkeypatch.setattr(song.jobs, "run_poller", fake_poller)

    async def run_once():
        async with main.lifespan(main.app):
            pass

    monkeypatch.setenv("FIONA_SONG_AGENT", "0")
    _run(run_once())
    assert calls == []
    assert "song-poller" not in labels

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    _run(run_once())
    assert calls == ["drain", "orphans", "recover", "reconcile"]
    assert labels.count("song-poller") == 1


def test_lifespan_reconcile_refunds_after_recover(song_env, monkeypatch):
    """真实 lifespan + 真实 init_db：启动后预置的 uncertain+reserved 已被退回。"""
    import exchange_store
    import main
    import novel.runner
    import song.jobs
    import studio.config
    import studio.recovery
    import studio.scheduler

    async def noop(*args, **kwargs):
        return None

    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "_run_upload_cleanup_once", noop)
    monkeypatch.setattr(main, "shutdown_background_tasks", noop)
    monkeypatch.setattr(exchange_store, "recover_interrupted_exchanges", noop)
    monkeypatch.setattr(novel.runner, "recover_interrupted_novels", noop)
    monkeypatch.setattr(novel.runner, "shutdown_novel_tasks", noop)
    monkeypatch.setattr(studio.recovery, "recover_studio_jobs", noop)
    monkeypatch.setattr(studio.scheduler, "run_scheduler", idle)
    monkeypatch.setattr(
        studio.config, "get_settings", lambda: SimpleNamespace(enabled=False)
    )
    monkeypatch.setattr(song.jobs, "run_poller", idle)

    def fake_task(coroutine, *, label):
        coroutine.close()

    monkeypatch.setattr(main, "create_background_task", fake_task)
    monkeypatch.setenv("FIONA_SONG_AGENT", "1")

    async def scenario():
        project, _lyrics = await _seed_project()
        await _seed_user("alice", balance=0)
        version = _insert_version(
            project["id"], status="uncertain", billing_state="reserved",
            strawberries=30,
        )

        async with main.lifespan(main.app):
            row = _version_row(version)
            assert row["status"] == "uncertain"
            assert row["billing_state"] == "refunded"

        row = _version_row(version)
        assert row["status"] == "uncertain"
        assert row["billing_state"] == "refunded"
        assert _balance() == 30

    _run(scenario())
