# -*- coding: utf-8 -*-
"""写歌 HTTP 路由测试：404、快照、生成计费、音频 Range 与下载头。"""
import asyncio
import json
import sqlite3
import time
from urllib.parse import quote
from uuid import uuid4

import pytest


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


def _run(coroutine):
    return asyncio.run(coroutine)


def _check(ok=True):
    return {
        "ok": ok,
        "errors": [] if ok else [
            {"code": "line_too_long", "section_id": "s1", "line_index": 0,
             "message": "主歌第 1 行超过 30 字"}
        ],
        "warnings": [],
        "lines": [],
        "provider_text": _PROVIDER_TEXT,
        "provider_chars": len(_PROVIDER_TEXT),
    }


class FakeProvider:
    def __init__(self):
        self.submitted = []
        self.queried = []

    async def submit(self, params):
        self.submitted.append(params)
        return "task-1"

    async def query(self, task_id):
        self.queried.append(task_id)
        raise AssertionError("本测试不应真正轮询")


@pytest.fixture
def song_scheduled(monkeypatch):
    import song.jobs as jobs

    calls = []

    def fake_task(coroutine, *, label):
        calls.append((label, coroutine))
        coroutine.close()

    monkeypatch.setattr(jobs, "create_background_task", fake_task)
    return calls


@pytest.fixture
def song_client(tmp_path, monkeypatch, song_scheduled):
    """打开写歌开关并用 idle 轮询器；在进入 lifespan 之前完成打桩。"""
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "smoke_tester")
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "songs"))
    monkeypatch.setenv("VOLC_MUSIC_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLC_MUSIC_SECRET_KEY", "test-sk")
    monkeypatch.delenv("FIONA_SONG_STRAWBERRIES", raising=False)
    monkeypatch.delenv("FIONA_DAILY_SONGS", raising=False)
    monkeypatch.delenv("FIONA_SONG_MAX_INFLIGHT", raising=False)
    monkeypatch.delenv("STRAWBERRY_DAILY_REFILL", raising=False)

    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "routes.db"))

    import main
    import song.jobs as jobs
    import studio.scheduler

    async def idle_poller():
        await asyncio.Event().wait()

    async def idle_studio_scheduler():
        await asyncio.Event().wait()

    monkeypatch.setattr(jobs, "run_poller", idle_poller)
    monkeypatch.setattr(studio.scheduler, "run_scheduler", idle_studio_scheduler)
    provider = FakeProvider()
    monkeypatch.setattr(jobs, "get_provider", lambda: provider)

    from rate_limit import limiter

    limiter.reset()

    from fastapi.testclient import TestClient

    with TestClient(
        main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        _login(client)
        client.song_scheduled = song_scheduled
        client.song_provider = provider
        yield client


def _login(client, owner="smoke_tester"):
    """DEV_MODE=0 下用真实 Cookie JWT 登录，保证生成走扣费分支。"""
    import auth
    import database

    user = _run(database.get_or_create_user(owner))
    client.cookies.set(
        "fiona_token", auth.create_token(owner, int(user["session_version"]))
    )


def _seed_user(balance=100, owner="smoke_tester"):
    import database

    _run(database.get_or_create_user(owner))
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            """UPDATE users SET strawberry_balance = ?, strawberry_refill_date = NULL
                WHERE username = ?""",
            (balance, owner),
        )


def _balance(owner="smoke_tester"):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute(
            "SELECT strawberry_balance FROM users WHERE username = ?", (owner,)
        ).fetchone()[0]


def _seed_project(owner="smoke_tester", *, ok=True, title="测试歌曲"):
    import song.store as store

    async def scenario():
        await _ensure_user(owner)
        project = await store.create_project(
            owner_username=owner,
            conversation_id="conv-1",
            title=title,
            brief={"theme": "夏天", "language": "Chinese", "duration_seconds": 60},
            structure=_STRUCTURE,
        )
        if ok is not None:
            saved = await store.save_lyrics(
                project["id"],
                owner_username=owner,
                conversation_id="conv-1",
                base_revision=0,
                sections=_SECTIONS,
                check=_check(ok),
                changed_section_ids=[],
            )
            assert saved["status"] == "ok"
        return project

    return _run(scenario())


async def _ensure_user(owner):
    import database

    await database.get_or_create_user(owner)


def _insert_version(
    project_id,
    *,
    owner="smoke_tester",
    status="succeeded",
    progress=100,
    audio_rel_path=None,
    failure_message=None,
    duration_s=62.5,
    billing_state="settled",
):
    import database
    import song.jobs as jobs

    version_id = uuid4().hex
    params = json.dumps(
        {"Lyrics": _PROVIDER_TEXT}, ensure_ascii=False, separators=(",", ":")
    )
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            """INSERT INTO song_versions
                   (id, project_id, owner_username, lyrics_revision, provider,
                    params_json, status, progress, strawberries, billing_state,
                    idempotency_key, audio_rel_path, duration_s, failure_message,
                    created_day)
               VALUES (?, ?, ?, 1, 'volc', ?, ?, ?, 30, ?, ?, ?, ?, ?, ?)""",
            (
                version_id,
                project_id,
                owner,
                params,
                status,
                progress,
                billing_state,
                "idem_" + uuid4().hex,
                audio_rel_path,
                duration_s,
                failure_message,
                jobs._today_shanghai(),
            ),
        )
    return version_id


def _version_count():
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute("SELECT COUNT(*) FROM song_versions").fetchone()[0]


def _version_row(version_id):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM song_versions WHERE id = ?", (version_id,)
        ).fetchone()
    return dict(row) if row else None


# ------------------------------------------------------------------ 开关 / 白名单
def test_song_routes_404_for_disabled_switch_and_foreign_user(
    song_client, dev_headers, monkeypatch
):
    project = _seed_project()
    ok = song_client.get(f"/songs/projects/{project['id']}", headers=dev_headers)
    assert ok.status_code == 200
    assert ok.headers["cache-control"] == "private, no-store"

    monkeypatch.delenv("FIONA_SONG_AGENT")
    disabled = song_client.get(
        f"/songs/projects/{project['id']}", headers=dev_headers
    )
    assert disabled.status_code == 404
    assert disabled.headers["cache-control"] == "private, no-store"

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "someone_else")
    foreign = song_client.get(
        f"/songs/projects/{project['id']}", headers=dev_headers
    )
    assert foreign.status_code == 404
    assert foreign.headers["cache-control"] == "private, no-store"

    generate = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "abcdefgh"},
    )
    assert generate.status_code == 404
    assert generate.headers["cache-control"] == "private, no-store"


# ------------------------------------------------------------------ 快照
def test_project_snapshot_shape_and_version_order(song_client, dev_headers):
    _seed_user(100)
    project = _seed_project()
    older = _insert_version(project["id"], status="failed", failure_message="生成失败，请稍后再试", audio_rel_path=None)
    newer = _insert_version(project["id"], status="succeeded", audio_rel_path="newer.mp3")

    response = song_client.get(f"/songs/projects/{project['id']}", headers=dev_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()

    assert data["id"] == project["id"]
    assert data["title"] == "测试歌曲"
    assert data["brief"]["language"] == "Chinese"
    assert data["structure"] == _STRUCTURE
    assert data["lyrics_revision"] == 1
    assert data["lyrics"]["revision"] == 1
    assert data["lyrics"]["check"]["ok"] is True
    assert data["lyrics"]["changed_section_ids"] == []
    assert [section["type"] for section in data["lyrics"]["sections"]] == [
        "verse", "chorus"
    ]
    assert [section["lines"] for section in data["lyrics"]["sections"]] == [
        ["风吹过山岗", "云落在远方"], ["我们一起唱", "唱到天亮"]
    ]
    assert [version["id"] for version in data["versions"]] == [newer, older]
    assert set(data["versions"][0]) == {
        "id", "lyrics_revision", "status", "progress",
        "failure_message", "duration_s", "created_at",
    }
    assert data["price_strawberries"] == 30
    assert data["configured"] is True
    assert data["can_generate"] is True
    assert data["generate_blocked_reason"] is None


def test_snapshot_no_lyrics_and_unresolved_reasons(song_client, dev_headers):
    _seed_user(100)
    empty = _seed_project(ok=None)
    response = song_client.get(f"/songs/projects/{empty['id']}", headers=dev_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["lyrics"] is None
    assert data["can_generate"] is False
    assert data["generate_blocked_reason"] == "还没有歌词"

    broken = _seed_project(ok=False)
    data = song_client.get(
        f"/songs/projects/{broken['id']}", headers=dev_headers
    ).json()
    assert data["lyrics"]["check"]["ok"] is False
    assert data["can_generate"] is False
    assert data["generate_blocked_reason"] == "歌词有未解决的问题"


def test_brief_update_rechecks_lyrics_and_blocks_generation(song_client, dev_headers):
    from types import SimpleNamespace as NS

    from song import tools

    _seed_user(100)
    project = _seed_project()

    # 删掉 s1，只留 chorus；旧歌词多出 s1，重检应给 structure_mismatch。
    structure = [
        {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
    ]
    text = _run(
        tools.execute(
            "song_save_brief",
            {
                "project_id": project["id"],
                "title": "测试歌曲",
                "brief": {"theme": "夏天", "language": "Chinese", "duration_seconds": 60},
                "structure": structure,
            },
            ctx=NS(user="smoke_tester"),
            conversation_id="conv-1",
            context={},
        )
    )
    assert "已按新结构重检第 2 稿" in text

    snapshot = song_client.get(
        f"/songs/projects/{project['id']}", headers=dev_headers
    )
    assert snapshot.status_code == 200
    data = snapshot.json()
    assert data["lyrics_revision"] == 2
    assert data["lyrics"]["check"]["ok"] is False
    assert data["can_generate"] is False
    assert data["generate_blocked_reason"] == "歌词有未解决的问题"

    generate = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 2, "idempotency_key": "idemrecheck01"},
    )
    assert generate.status_code == 409
    assert generate.json()["detail"] == "歌词有未解决的问题"
    assert _version_count() == 0


def test_snapshot_unconfigured_and_limit_reasons(
    song_client, dev_headers, monkeypatch
):
    _seed_user(100)
    project = _seed_project()

    monkeypatch.delenv("VOLC_MUSIC_ACCESS_KEY")
    data = song_client.get(
        f"/songs/projects/{project['id']}", headers=dev_headers
    ).json()
    assert data["configured"] is False
    assert data["can_generate"] is False
    assert data["generate_blocked_reason"] == "写歌服务未配置"

    monkeypatch.setenv("VOLC_MUSIC_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "1")
    queued = _insert_version(
        project["id"], status="queued", progress=0, billing_state="reserved",
        audio_rel_path=None,
    )
    data = song_client.get(
        f"/songs/projects/{project['id']}", headers=dev_headers
    ).json()
    assert data["generate_blocked_reason"] == "同时在途的歌曲太多"
    assert data["can_generate"] is False

    # 把在途版本改成终态，再用每日上限触发第二个原因。
    _mark_terminal(queued, "failed")
    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "5")
    monkeypatch.setenv("FIONA_DAILY_SONGS", "1")
    data = song_client.get(
        f"/songs/projects/{project['id']}", headers=dev_headers
    ).json()
    assert data["generate_blocked_reason"] == "今天生成歌曲的次数已用完"


def _mark_terminal(version_id, status):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            "UPDATE song_versions SET status = ? WHERE id = ?", (status, version_id)
        )


# ------------------------------------------------------------------ 生成
def test_generate_202_charges_and_reuses_idempotency_key(song_client, dev_headers):
    _seed_user(100)
    project = _seed_project()
    body = {"lyrics_revision": 1, "idempotency_key": "idemroute_0001"}

    first = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers, json=body,
    )
    assert first.status_code == 202
    assert first.headers["cache-control"] == "private, no-store"
    payload = first.json()
    assert payload["status"] == "queued"
    assert payload["progress"] == 0
    row = _version_row(payload["id"])
    assert row["billing_state"] == "reserved"
    assert row["strawberries"] == 30
    assert _balance() == 70
    assert [label for label, _ in song_client.song_scheduled] == ["song-submit"]

    second = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers, json=body,
    )
    assert second.status_code == 202
    assert second.json()["id"] == payload["id"]
    assert _balance() == 70
    assert _version_count() == 1
    assert len(song_client.song_scheduled) == 1


def test_generate_402_insufficient_balance(song_client, dev_headers):
    import database

    _seed_user(0)
    project = _seed_project()
    response = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "idembroke_0001"},
    )
    assert response.status_code == 402
    assert response.json()["detail"] == database.strawberry_insufficient_message()
    assert response.headers["cache-control"] == "private, no-store"
    assert _version_count() == 0


def test_generate_404_for_foreign_or_missing_project(song_client, dev_headers):
    _seed_user(100)
    foreign = _seed_project(owner="somebody_else")

    for project_id in (foreign["id"], "does-not-exist"):
        response = song_client.post(
            f"/songs/projects/{project_id}/generate",
            headers=dev_headers,
            json={"lyrics_revision": 1, "idempotency_key": "idemforeign_01"},
        )
        assert response.status_code == 404
        assert response.headers["cache-control"] == "private, no-store"

    snapshot = song_client.get(
        f"/songs/projects/{foreign['id']}", headers=dev_headers
    )
    assert snapshot.status_code == 404
    assert snapshot.headers["cache-control"] == "private, no-store"
    assert _version_count() == 0


def test_generate_409_for_stale_or_unresolved_lyrics(song_client, dev_headers):
    _seed_user(100)
    project = _seed_project()

    stale = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 0, "idempotency_key": "idemstale_0001"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "歌词已更新，请刷新"

    broken = _seed_project(ok=False)
    unresolved = song_client.post(
        f"/songs/projects/{broken['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "idembroken_001"},
    )
    assert unresolved.status_code == 409
    assert unresolved.json()["detail"] == "歌词有未解决的问题"
    assert _version_count() == 0


def test_generate_429_for_inflight_limit(song_client, dev_headers, monkeypatch):
    _seed_user(500)
    project = _seed_project()

    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "1")
    first = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "ideminflight01"},
    )
    assert first.status_code == 202
    inflight = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "ideminflight02"},
    )
    assert inflight.status_code == 429
    assert "同时在途" in inflight.json()["detail"]
    assert _version_count() == 1


def test_generate_429_for_daily_limit(song_client, dev_headers, monkeypatch):
    _seed_user(500)
    project = _seed_project()

    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "5")
    monkeypatch.setenv("FIONA_DAILY_SONGS", "1")
    first = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "idemdaily_0001"},
    )
    assert first.status_code == 202
    daily = song_client.post(
        f"/songs/projects/{project['id']}/generate",
        headers=dev_headers,
        json={"lyrics_revision": 1, "idempotency_key": "idemdaily_0002"},
    )
    assert daily.status_code == 429
    assert "今天生成歌曲的次数已用完" in daily.json()["detail"]


# ------------------------------------------------------------------ 音频
def _write_audio(version_id, content=b"0123456789"):
    from song import config

    root = config.song_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{version_id}.mp3"
    path.write_bytes(content)
    return path


def test_audio_supports_range_and_download_header(song_client, dev_headers):
    _seed_user(100)
    project = _seed_project(title="测试歌曲")
    version_id = _insert_version(project["id"], audio_rel_path="audio-test.mp3")
    _write_audio("audio-test")

    full = song_client.get(
        f"/songs/versions/{version_id}/audio", headers=dev_headers
    )
    assert full.status_code == 200
    assert full.headers["content-type"] == "audio/mpeg"
    assert full.headers["cache-control"] == "private, no-store"
    assert full.content == b"0123456789"

    ranged = song_client.get(
        f"/songs/versions/{version_id}/audio",
        headers={**dev_headers, "Range": "bytes=0-1"},
    )
    assert ranged.status_code == 206
    assert ranged.content == b"01"
    assert ranged.headers["content-range"] == "bytes 0-1/10"

    download = song_client.get(
        f"/songs/versions/{version_id}/audio?download=1", headers=dev_headers
    )
    assert download.status_code == 200
    assert download.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''" + quote("测试歌曲", safe="") + ".mp3"
    )

    empty_title = _seed_project(title="")
    empty_id = _insert_version(empty_title["id"], audio_rel_path="empty.mp3")
    _write_audio("empty")
    empty_download = song_client.get(
        f"/songs/versions/{empty_id}/audio?download=1", headers=dev_headers
    )
    assert empty_download.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''song.mp3"
    )


def test_audio_404_for_non_succeeded_missing_foreign_and_escape(
    song_client, dev_headers, tmp_path
):
    _seed_user(100)
    project = _seed_project()

    queued = _insert_version(
        project["id"], status="queued", progress=0, audio_rel_path=None,
        duration_s=None,
    )
    assert song_client.get(
        f"/songs/versions/{queued}/audio", headers=dev_headers
    ).status_code == 404

    missing = _insert_version(project["id"], audio_rel_path="missing.mp3")
    assert song_client.get(
        f"/songs/versions/{missing}/audio", headers=dev_headers
    ).status_code == 404

    foreign = _seed_project(owner="other_person")
    foreign_version = _insert_version(
        foreign["id"], owner="other_person", audio_rel_path="foreign.mp3"
    )
    _write_audio("foreign")
    assert song_client.get(
        f"/songs/versions/{foreign_version}/audio", headers=dev_headers
    ).status_code == 404

    escape = _insert_version(project["id"], audio_rel_path="../outside.mp3")
    (tmp_path / "outside.mp3").write_bytes(b"secret")
    response = song_client.get(
        f"/songs/versions/{escape}/audio", headers=dev_headers
    )
    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"

    from song import config

    root = config.song_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "link-target.mp3"
    target.write_bytes(b"secret")
    (root / "link.mp3").symlink_to(target)
    linked = _insert_version(project["id"], audio_rel_path="link.mp3")
    assert song_client.get(
        f"/songs/versions/{linked}/audio", headers=dev_headers
    ).status_code == 404
