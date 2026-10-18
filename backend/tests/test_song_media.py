# -*- coding: utf-8 -*-
"""写歌媒体（``song.media``）的离线测试。

所有供应商交互走 ``httpx.MockTransport``；测试音频由本机 ffmpeg 用 lavfi
正弦波现场合成。每个用例都把 ``FIONA_SONG_DIR`` / ``database.DB_PATH`` 指到
``tmp_path``，不读写仓库内文件、不访问真实网络。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import aiosqlite
import httpx
import pytest

import database
from song import media


requires_media_tools = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="需要系统 ffmpeg/ffprobe",
)

RESULT_URL = "https://v12-default.douyinvod.com/audio/123.mp3?sign=abc"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _isolated_song_env(monkeypatch, tmp_path):
    """每个用例都隔离音频根目录与数据库，绝不在仓库内产生文件。"""
    root = tmp_path / "songs"
    monkeypatch.setenv("FIONA_SONG_DIR", str(root))
    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "Fiona")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "song.db"))
    return root


@pytest.fixture
def song_dir(_isolated_song_env):
    return _isolated_song_env


# ---------------------------------------------------------------- 测试媒体
def _ffmpeg(*args) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def wav_bytes(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("song-media-input") / "sine.wav"
    _ffmpeg(
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-ac", "1", "-ar", "44100", str(path),
    )
    return path.read_bytes()


@pytest.fixture(scope="module")
def mp4_bytes(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("song-media-input") / "sine.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=6",
        "-map", "0:a", "-map", "1:v",
        "-c:a", "aac", "-b:a", "128k", "-c:v", "mpeg4",
        "-shortest", str(path),
    )
    return path.read_bytes()


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:format_tags:stream=codec_type,codec_name",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _assert_tagged_mp3(path: Path, version_id: str, title: str) -> None:
    info = _probe(path)
    tags = info["format"]["tags"]
    assert tags["AIGC"] == media.aigc_metadata_json(version_id)
    parsed = json.loads(tags["AIGC"])
    assert parsed["ProduceID"] == version_id
    assert parsed["Label"] == "1"
    assert parsed["ContentProducer"] == "Fiona"
    assert list(parsed) == [
        "Label", "ContentProducer", "ProduceID", "ReservedCode1",
        "ContentPropagator", "PropagateID", "ReservedCode2",
    ]
    assert tags["title"] == title
    assert tags["comment"] == "本音频由人工智能生成"
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    assert audio_streams
    assert audio_streams[0]["codec_name"] == "mp3"
    assert not [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    assert float(info["format"]["duration"]) > 5


def _mock_response(data: bytes = b"", *, status: int = 200, headers: dict | None = None):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, content=data, headers=headers)

    return httpx.MockTransport(handler), requests


# ---------------------------------------------------------------- AIGC 标识
def test_aigc_metadata_json_exact_key_order(monkeypatch, song_dir):
    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "Acme")
    assert media.aigc_metadata_json("abc123") == (
        '{"Label":"1","ContentProducer":"Acme","ProduceID":"abc123",'
        '"ReservedCode1":"","ContentPropagator":"","PropagateID":"",'
        '"ReservedCode2":""}'
    )


# ---------------------------------------------------------------- 根目录与路径
def test_song_root_create_flag(song_dir):
    assert media.song_root() == song_dir.resolve()
    assert not song_dir.exists()
    created = media.song_root(create=True)
    assert created == song_dir.resolve()
    assert created.is_dir()


def test_safe_audio_path_rejects_escape_and_shadow_links(song_dir, tmp_path):
    root = media.song_root(create=True)
    inside = root / "inside.mp3"
    inside.write_bytes(b"x")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"y")

    assert media.safe_audio_path("inside.mp3") == inside.resolve()
    assert media.safe_audio_path(str(inside)) == inside.resolve()
    missing_name = f"{uuid.uuid4().hex}.mp3"
    assert media.safe_audio_path(missing_name) == (root / missing_name).resolve()

    assert media.safe_audio_path("../outside.mp3") is None
    assert media.safe_audio_path(str(outside)) is None
    assert media.safe_audio_path(str(root)) is None
    assert media.safe_audio_path("") is None
    assert media.safe_audio_path(None) is None

    escape = root / "escape.mp3"
    escape.symlink_to(outside)
    assert media.safe_audio_path("escape.mp3") is None

    duplicate = root / "duplicate.mp3"
    duplicate.symlink_to(inside)
    assert media.safe_audio_path("duplicate.mp3") == inside.resolve()


# ---------------------------------------------------------------- 完整下载 / 转码
@requires_media_tools
@pytest.mark.anyio
async def test_download_wav_transcodes_tagged_mp3(song_dir, wav_bytes):
    version_id = uuid.uuid4().hex
    transport, requests = _mock_response(wav_bytes, headers={"content-type": "audio/wav"})
    result = await media.download_and_store(
        RESULT_URL, version_id=version_id, title="测试歌曲", transport=transport,
    )
    assert result["audio_rel_path"] == f"{version_id}.mp3"
    assert isinstance(result["duration_s"], float)
    assert 5.5 <= result["duration_s"] <= 7.0
    target = song_dir / result["audio_rel_path"]
    assert target.is_file()
    _assert_tagged_mp3(target, version_id, "测试歌曲")
    assert {entry.name for entry in song_dir.iterdir()} == {target.name}
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers
    assert "x-api-key" not in request.headers


@requires_media_tools
@pytest.mark.anyio
async def test_download_mp4_input_always_outputs_mp3(song_dir, mp4_bytes):
    version_id = uuid.uuid4().hex
    transport, _requests = _mock_response(mp4_bytes, headers={"content-type": "video/mp4"})
    result = await media.download_and_store(
        RESULT_URL, version_id=version_id, title="视频容器输入", transport=transport,
    )
    assert result["audio_rel_path"] == f"{version_id}.mp3"
    target = song_dir / result["audio_rel_path"]
    assert target.suffix == ".mp3"
    _assert_tagged_mp3(target, version_id, "视频容器输入")


# ---------------------------------------------------------------- 下载失败分支
@pytest.mark.anyio
@pytest.mark.parametrize("url", [
    "http://v12-default.douyinvod.com/a.mp3",
    "https://v0-default.douyinvod.com/a.mp3",
    "https://v51-default.douyinvod.com/a.mp3",
    "https://evil.test/a.mp3",
    "https://v12-default.douyinvod.com.evil.test/a.mp3",
    "https://user:pass@v12-default.douyinvod.com/a.mp3",
    "https://v12-default.douyinvod.com:not-a-port/a.mp3",
])
async def test_result_host_rejected_before_transport(song_dir, url):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("不允许发起下载")

    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            url, version_id=uuid.uuid4().hex, title="x",
            transport=httpx.MockTransport(handler),
        )
    assert exc.value.code == "result_host"
    assert calls == []
    assert not song_dir.exists()


@requires_media_tools
@pytest.mark.anyio
async def test_redirect_rejected_without_following(song_dir):
    transport, calls = _mock_response(
        b"", status=302, headers={"location": "https://v13-default.douyinvod.com/x.mp3"},
    )
    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x", transport=transport,
        )
    assert exc.value.code == "download_redirect"
    assert len(calls) == 1
    assert not list(song_dir.iterdir())


@requires_media_tools
@pytest.mark.anyio
async def test_http_error_status_rejected(song_dir):
    transport, _calls = _mock_response(b"", status=404)
    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x", transport=transport,
        )
    assert exc.value.code == "download_http_error"
    assert not list(song_dir.iterdir())


@requires_media_tools
@pytest.mark.anyio
async def test_declared_content_length_over_limit(song_dir):
    transport, calls = _mock_response(
        b"x", headers={"content-length": str(media.MAX_AUDIO_BYTES + 1)},
    )
    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x", transport=transport,
        )
    assert exc.value.code == "audio_too_large"
    assert len(calls) == 1
    assert not list(song_dir.iterdir())


class _OversizeStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range(801):  # 801 * 64 KiB > 50 MB
            yield b"x" * 65536


@requires_media_tools
@pytest.mark.anyio
async def test_actual_content_over_limit_aborts_and_cleans(song_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_OversizeStream())

    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x",
            transport=httpx.MockTransport(handler),
        )
    assert exc.value.code == "audio_too_large"
    assert list(song_dir.iterdir()) == []


@requires_media_tools
@pytest.mark.anyio
async def test_bad_audio_input_is_invalid_audio(song_dir):
    transport, _calls = _mock_response(b"this is definitely not audio")
    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x", transport=transport,
        )
    assert exc.value.code == "invalid_audio"
    assert list(song_dir.iterdir()) == []


@pytest.mark.anyio
async def test_missing_ffmpeg_is_reported_without_download(monkeypatch, song_dir):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"x")

    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x",
            transport=httpx.MockTransport(handler),
        )
    assert exc.value.code == "ffmpeg_unavailable"
    assert calls == []
    assert not song_dir.exists()


@pytest.mark.anyio
async def test_missing_ffprobe_is_reported_without_download(monkeypatch, song_dir):
    monkeypatch.setattr(
        shutil, "which",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )
    with pytest.raises(media.MediaError) as exc:
        await media.download_and_store(
            RESULT_URL, version_id=uuid.uuid4().hex, title="x",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x")),
        )
    assert exc.value.code == "ffmpeg_unavailable"
    assert not song_dir.exists()


# ---------------------------------------------------------------- 清理队列
async def _insert_queue(paths: list[str]) -> None:
    async with aiosqlite.connect(database.DB_PATH) as db:
        for path in paths:
            await db.execute("INSERT OR IGNORE INTO song_cleanup_queue (path) VALUES (?)", (path,))
        await db.commit()


async def _remaining_queue() -> set[str]:
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute("SELECT path FROM song_cleanup_queue") as cursor:
            rows = await cursor.fetchall()
    return {row[0] for row in rows}


@pytest.mark.anyio
async def test_drain_cleanup_queue_boundaries(song_dir, tmp_path):
    await database.init_db()
    root = song_dir
    root.mkdir(parents=True)
    normal = root / "normal.mp3"
    normal.write_bytes(b"a")
    target = root / "target.mp3"
    target.write_bytes(b"t")
    link = root / "link.mp3"
    link.symlink_to(target)
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"o")

    await _insert_queue([
        "normal.mp3",
        "missing.mp3",
        str(outside),
        "../outside.mp3",
        "link.mp3",
    ])
    await media.drain_cleanup_queue()

    assert not normal.exists()
    assert target.exists()
    assert link.is_symlink()
    assert outside.exists()
    assert await _remaining_queue() == {str(outside), "../outside.mp3", "link.mp3"}


@pytest.mark.anyio
async def test_drain_cleanup_queue_without_root_dequeues_missing(song_dir):
    await database.init_db()
    assert not song_dir.exists()
    await _insert_queue(["gone.mp3"])
    await media.drain_cleanup_queue()
    assert await _remaining_queue() == set()


@pytest.mark.anyio
async def test_drain_cleanup_queue_without_database_does_not_crash(song_dir):
    await media.drain_cleanup_queue()


# ---------------------------------------------------------------- 孤儿清扫
async def _insert_version(audio_rel_path: str) -> str:
    version_id = uuid.uuid4().hex
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            """INSERT INTO song_versions
               (id, project_id, owner_username, lyrics_revision, provider, params_json,
                status, billing_state, idempotency_key, created_day, audio_rel_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                version_id, uuid.uuid4().hex, "owner", 1, "volc", "{}",
                "succeeded", "settled", uuid.uuid4().hex, "2026-10-18", audio_rel_path,
            ),
        )
        await db.commit()
    return version_id


@pytest.mark.anyio
async def test_cleanup_orphans_removes_only_unreferenced_and_old_parts(song_dir, tmp_path):
    await database.init_db()
    root = song_dir
    root.mkdir(parents=True)
    orphan = root / f"{uuid.uuid4().hex}.mp3"
    orphan.write_bytes(b"orphan")
    kept = root / f"{uuid.uuid4().hex}.mp3"
    kept.write_bytes(b"kept")
    await _insert_version(kept.name)

    old_part = root / ".song-old.part"
    old_part.write_bytes(b"old")
    old_time = time.time() - 2 * 60 * 60
    os.utime(old_part, (old_time, old_time))
    new_part = root / ".song-new.part"
    new_part.write_bytes(b"new")

    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"outside")
    link = root / f"{uuid.uuid4().hex}.mp3"
    link.symlink_to(outside)
    unrelated = root / "notes.mp3"
    unrelated.write_bytes(b"notes")

    await media.cleanup_orphans()

    assert not orphan.exists()
    assert kept.exists()
    assert outside.exists()
    assert link.is_symlink()
    assert unrelated.exists()
    assert not old_part.exists()
    assert new_part.exists()


@pytest.mark.anyio
async def test_cleanup_orphans_without_database_keeps_mp3(song_dir):
    root = song_dir
    root.mkdir(parents=True)
    orphan = root / f"{uuid.uuid4().hex}.mp3"
    orphan.write_bytes(b"orphan")
    old_part = root / ".song-old.part"
    old_part.write_bytes(b"old")
    old_time = time.time() - 2 * 60 * 60
    os.utime(old_part, (old_time, old_time))

    # 数据库不存在时不敢判断引用关系：保留 mp3，但旧 .part 仍然安全清理。
    await media.cleanup_orphans()
    assert orphan.exists()
    assert not old_part.exists()


@pytest.mark.anyio
async def test_cleanup_orphans_without_root_does_not_crash(song_dir):
    assert not song_dir.exists()
    await media.cleanup_orphans()


# ---------------------------------------------------------------- 回读标识校验
def _write_sine_mp3(path: Path, *, aigc: str | None) -> None:
    """用 lavfi 合成 6 秒 mp3；``aigc`` 为 None 时不写任何 AIGC 标签。"""
    args = [
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-ac", "1", "-ar", "44100",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-id3v2_version", "4",
    ]
    if aigc is not None:
        args.extend(["-metadata", f"AIGC={aigc}"])
    args.append(str(path))
    _ffmpeg(*args)


@requires_media_tools
@pytest.mark.anyio
async def test_probe_output_rejects_foreign_produce_id(song_dir):
    """AIGC 标签存在但 ProduceID 不是期望版本时，必须判 invalid_audio。"""
    expected_id = uuid.uuid4().hex
    path = media.song_root(create=True) / f"{uuid.uuid4().hex}.mp3"
    _write_sine_mp3(path, aigc=media.aigc_metadata_json("other-id"))

    # 先证明标签确实写进了文件且能被 ffprobe 读回，避免退化成“缺标签”用例。
    tags = _probe(path)["format"]["tags"]
    assert json.loads(tags["AIGC"])["ProduceID"] == "other-id"

    with pytest.raises(media.MediaError) as exc:
        await media._probe_output(path, expected_id)
    assert exc.value.code == "invalid_audio"


@requires_media_tools
@pytest.mark.anyio
async def test_probe_output_rejects_missing_aigc_tag(song_dir):
    path = media.song_root(create=True) / f"{uuid.uuid4().hex}.mp3"
    _write_sine_mp3(path, aigc=None)

    tags = _probe(path)["format"].get("tags") or {}
    assert "AIGC" not in tags

    with pytest.raises(media.MediaError) as exc:
        await media._probe_output(path, uuid.uuid4().hex)
    assert exc.value.code == "invalid_audio"


@requires_media_tools
@pytest.mark.anyio
async def test_probe_output_accepts_matching_produce_id(song_dir):
    version_id = uuid.uuid4().hex
    path = media.song_root(create=True) / f"{version_id}.mp3"
    _write_sine_mp3(path, aigc=media.aigc_metadata_json(version_id))

    duration = await media._probe_output(path, version_id)
    assert isinstance(duration, float)
    assert duration > 5
