# -*- coding: utf-8 -*-
"""写歌音频：下载、转码、AIGC 隐式标识、回读校验与文件清理。

安全边界：
- 只接受 https 且主机名属于火山结果域名的 AudioUrl；
- 下载使用独立 httpx 客户端：不跟随重定向、不使用环境代理、不携带任何凭据；
- 临时文件只落在 ``FIONA_SONG_DIR``，所有路径 ``resolve()`` 后必须仍在根目录内；
- 对外只抛 ``MediaError(code)``，文案只含错误码，不含 URL、本地路径或上游正文。

除 ``MediaError`` 外，``download_and_store`` 返回
``{"audio_rel_path": "<version_id>.mp3", "duration_s": <float>}``。
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import aiosqlite
import httpx

import database
from song import config


# 单个结果文件上限：50 MB。
MAX_AUDIO_BYTES = 50 * 1024 * 1024
# 火山结果域名：v1..v50-default.douyinvod.com。
_RESULT_HOST_RE = re.compile(r"^v([1-9]|[1-4][0-9]|50)-default\.douyinvod\.com$")
# 版本 id 只用来拼文件名；拒绝路径分隔符和过长输入。
_VERSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
# 孤儿清扫只认 32 位小写 hex 的 mp3。
_ORPHAN_RE = re.compile(r"^[0-9a-f]{32}\.mp3$")
_FFMPEG_TIMEOUT_S = 120
_FFPROBE_TIMEOUT_S = 30
_PART_MAX_AGE_S = 60 * 60


class MediaError(Exception):
    """下载 / 转码 / 校验 / 存储失败；``code`` 可直接作为 failure_code。"""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# ---------------------------------------------------------------- 根目录与路径
def song_root(create: bool = False) -> Path:
    """返回写歌音频根目录（调用时读取 ``FIONA_SONG_DIR``）。"""
    root = Path(config.song_dir())
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def safe_audio_path(rel_path) -> Path | None:
    """把队列 / 数据库里的相对或绝对路径安全解析到写歌根目录内。

    返回 ``resolve()`` 后的绝对路径；空值、非路径、``..`` 逃逸、符号链接逃逸
    或根目录本身一律返回 ``None``。
    """
    if not isinstance(rel_path, (str, os.PathLike)):
        return None
    try:
        raw = os.fspath(rel_path)
    except TypeError:
        return None
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return None
    try:
        root = song_root().resolve()
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    if resolved == root:
        return None
    return resolved


# ---------------------------------------------------------------- 隐式标识
def aigc_metadata_json(version_id: str) -> str:
    """生成写入 ID3 的 AIGC JSON（键顺序固定、无空格分隔符）。"""
    payload = {
        "Label": "1",
        "ContentProducer": config.aigc_producer(),
        "ProduceID": version_id,
        "ReservedCode1": "",
        "ContentPropagator": "",
        "PropagateID": "",
        "ReservedCode2": "",
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- 子进程
async def _run(args: list[str], *, timeout_s: float) -> tuple[int, bytes, bytes]:
    """执行 ffmpeg / ffprobe；超时 kill 并只抛错误码。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise MediaError("ffmpeg_unavailable") from None
    except OSError:
        raise MediaError("transcode_failed") from None
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # 已经退出
            pass
        await proc.wait()
        raise MediaError("ffmpeg_timeout") from None
    return proc.returncode, stdout or b"", stderr or b""


def _unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------- 下载
def _validate_audio_url(audio_url) -> None:
    if not isinstance(audio_url, str):
        raise MediaError("result_host")
    try:
        parts = urlsplit(audio_url)
        # 访问 port 会把非法端口变成 ValueError，一并按非法结果地址处理。
        parts.port
    except ValueError:
        raise MediaError("result_host") from None
    host = parts.hostname
    if (
        parts.scheme.lower() != "https"
        or not host
        or not _RESULT_HOST_RE.fullmatch(host)
        or parts.username is not None
        or parts.password is not None
    ):
        raise MediaError("result_host")


async def _download_to_part(audio_url: str, root: Path, transport) -> Path:
    """流式下载到根目录内的 ``.part`` 文件并 fsync；失败时清理临时文件。"""
    part: Path | None = None
    try:
        # 独立客户端：不带上游凭据、不读环境代理、不自动跟随重定向。
        async with httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(120, connect=10),
        ) as client:
            async with client.stream("GET", audio_url) as response:
                status = response.status_code
                if 300 <= status < 400:
                    raise MediaError("download_redirect")
                if status != 200:
                    raise MediaError("download_http_error")
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        declared_bytes = int(declared)
                    except (TypeError, ValueError):
                        raise MediaError("audio_size_invalid") from None
                    if declared_bytes > MAX_AUDIO_BYTES:
                        raise MediaError("audio_too_large")
                with tempfile.NamedTemporaryFile(
                    dir=root, prefix=".song-", suffix=".part", delete=False,
                ) as handle:
                    part = Path(handle.name)
                    total = 0
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > MAX_AUDIO_BYTES:
                            raise MediaError("audio_too_large")
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                if total == 0:
                    raise MediaError("invalid_audio")
        finished = part
        part = None
        return finished
    except MediaError:
        raise
    except httpx.HTTPError:
        raise MediaError("download_transport") from None
    except OSError:
        raise MediaError("download_storage") from None
    finally:
        _unlink(part)


# ---------------------------------------------------------------- 转码与回读
async def _probe_output(path: Path, version_id: str) -> float:
    """ffprobe 回读：必须有音频流、AIGC.ProduceID 匹配、时长 > 5 秒。"""
    code, stdout, _stderr = await _run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration:format_tags:stream=codec_type",
            "-of", "json",
            str(path),
        ],
        timeout_s=_FFPROBE_TIMEOUT_S,
    )
    if code != 0:
        raise MediaError("invalid_audio")
    try:
        data = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise MediaError("invalid_audio") from None
    if not isinstance(data, dict):
        raise MediaError("invalid_audio")
    streams = data.get("streams")
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    ):
        raise MediaError("invalid_audio")
    fmt = data.get("format")
    tags = fmt.get("tags") if isinstance(fmt, dict) else None
    raw_tag = tags.get("AIGC") if isinstance(tags, dict) else None
    if not isinstance(raw_tag, str):
        raise MediaError("invalid_audio")
    try:
        aigc = json.loads(raw_tag)
    except ValueError:
        raise MediaError("invalid_audio") from None
    if not isinstance(aigc, dict) or aigc.get("ProduceID") != version_id:
        raise MediaError("invalid_audio")
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        raise MediaError("invalid_audio") from None
    if not math.isfinite(duration) or duration <= 5:
        raise MediaError("invalid_audio")
    return duration


# ---------------------------------------------------------------- 主流程
async def download_and_store(
    audio_url: str,
    *,
    version_id: str,
    title: str,
    transport=None,
) -> dict:
    """下载火山结果并一步转成带 AIGC 隐式标识的 mp3。

    返回 ``{"audio_rel_path": "<version_id>.mp3", "duration_s": float}``。
    任何失败都抛 ``MediaError``（``code`` 即 failure_code）。
    """
    _validate_audio_url(audio_url)
    if not isinstance(version_id, str) or not _VERSION_ID_RE.fullmatch(version_id):
        raise MediaError("invalid_version")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise MediaError("ffmpeg_unavailable")
    try:
        root = song_root(create=True)
        root = root.resolve()
    except (OSError, RuntimeError):
        raise MediaError("storage_error") from None

    source_part = await _download_to_part(audio_url, root, transport)
    out_part: Path | None = None
    try:
        metadata = aigc_metadata_json(version_id)
        title_text = "" if title is None else str(title)
        title_text = title_text.replace("\x00", "")
        out_part = root / f".{version_id}-{uuid.uuid4().hex}.part.mp3"
        code, _stdout, _stderr = await _run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-v", "error",
                "-y",
                "-i", str(source_part),
                "-map_metadata", "-1",
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-id3v2_version", "4",
                "-metadata", f"AIGC={metadata}",
                "-metadata", f"title={title_text}",
                "-metadata", "comment=本音频由人工智能生成",
                str(out_part),
            ],
            timeout_s=_FFMPEG_TIMEOUT_S,
        )
        if code != 0:
            raise MediaError("invalid_audio")
        duration = await _probe_output(out_part, version_id)
        target = root / f"{version_id}.mp3"
        try:
            os.replace(out_part, target)
        except OSError:
            raise MediaError("storage_error") from None
        out_part = None
        return {"audio_rel_path": f"{version_id}.mp3", "duration_s": duration}
    finally:
        _unlink(source_part)
        _unlink(out_part)


# ---------------------------------------------------------------- 清理
def _remove_queued_file(raw) -> bool:
    """删除队列里的一个文件；返回 True 表示可以出队（删掉或本来就不存在）。"""
    resolved = safe_audio_path(raw)
    if resolved is None:
        # 根外路径 / 非法路径：不删、不出队，留待人工检查。
        return False
    try:
        # 用未解析的入口路径 lstat，拒绝目录本身是符号链接的情况；
        # safe_audio_path 已保证最终目标仍在根内。
        entry = Path(os.fspath(raw))
        if not entry.is_absolute():
            entry = song_root().resolve() / entry
        info = entry.lstat()
    except FileNotFoundError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return False
    try:
        entry.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


async def drain_cleanup_queue() -> None:
    """删除 ``song_cleanup_queue`` 中位于写歌根目录内的普通文件。

    删除成功或文件已不存在则出队；根外路径、符号链接与其他错误保留待下次。
    数据库 / 表不存在时安静返回。
    """
    db_path = Path(database.DB_PATH)
    if not db_path.exists():
        return
    try:
        async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
            try:
                async with db.execute("SELECT path FROM song_cleanup_queue") as cursor:
                    rows = [row[0] for row in await cursor.fetchall()]
            except aiosqlite.Error:
                return
            for raw in rows:
                if not _remove_queued_file(raw):
                    continue
                try:
                    await db.execute("DELETE FROM song_cleanup_queue WHERE path = ?", (raw,))
                except aiosqlite.Error:
                    return
            try:
                await db.commit()
            except aiosqlite.Error:
                pass
    except (aiosqlite.Error, OSError):
        return


async def _referenced_audio_paths() -> tuple[set[Path], bool]:
    """读取 song_versions 引用的音频路径；返回 (集合, 数据库是否可用)。"""
    refs: set[Path] = set()
    db_path = Path(database.DB_PATH)
    if not db_path.exists():
        return refs, False
    try:
        async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
            async with db.execute(
                "SELECT audio_rel_path FROM song_versions "
                "WHERE audio_rel_path IS NOT NULL AND audio_rel_path <> ''"
            ) as cursor:
                rows = await cursor.fetchall()
    except (aiosqlite.Error, OSError):
        return refs, False
    for (raw,) in rows:
        resolved = safe_audio_path(raw)
        if resolved is not None:
            refs.add(resolved)
    return refs, True


async def cleanup_orphans() -> None:
    """启动清扫：删除未被数据库引用的 ``<32hex>.mp3`` 和超过 1 小时的 ``.part``。"""
    root = song_root()
    try:
        if not root.is_dir():
            return
    except OSError:
        return
    refs, db_ready = await _referenced_audio_paths()
    now = time.time()
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if ".part" in entry.name:
                info = entry.lstat()
                if (
                    stat.S_ISREG(info.st_mode)
                    and not stat.S_ISLNK(info.st_mode)
                    and now - info.st_mtime > _PART_MAX_AGE_S
                ):
                    _unlink(entry)
                continue
            if not _ORPHAN_RE.fullmatch(entry.name) or not db_ready:
                continue
            info = entry.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                continue
            try:
                resolved = entry.resolve()
            except (OSError, RuntimeError):
                continue
            if resolved in refs:
                continue
            _unlink(entry)
        except OSError:
            continue
