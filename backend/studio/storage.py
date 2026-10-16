"""工作室私有素材：安全路径、原子写入、下载和媒体校验。"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
import uuid
import warnings

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from studio.config import get_settings
from studio.gate import PRIVATE_HEADERS


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024
IMAGE_TYPES = {"PNG": (".png", "image/png"), "JPEG": (".jpg", "image/jpeg"),
               "WEBP": (".webp", "image/webp")}


class DownloadError(Exception):
    def __init__(self, code: str, message: str, *, expired: bool = False,
                 retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.expired = expired
        self.retryable = retryable


def storage_root(create: bool = False) -> Path:
    root = get_settings().directory.resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_path(rel_path: str) -> Path:
    """既检查相对路径，也解析符号链接后再次检查真实路径。"""
    try:
        relative = Path(rel_path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError
        root = storage_root()
        resolved = (root / relative).resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise ValueError
        return resolved
    except (ValueError, TypeError, OSError, RuntimeError):
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS) from None


def resolve_asset_path(asset: dict) -> Path:
    path = resolve_path(asset["rel_path"])
    if not path.is_file():
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)
    return path


def asset_file_response(asset: dict) -> FileResponse:
    path = resolve_asset_path(asset)
    return FileResponse(path, headers=PRIVATE_HEADERS)


def inspect_image(data: bytes) -> dict:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(422, "首帧图片不能为空，且不能超过 20MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image_type = image.format
                if image_type not in IMAGE_TYPES:
                    raise HTTPException(422, "首帧只支持 PNG、JPEG 或 WebP 图片")
                image.verify()
            # verify 不解码所有像素；再次解码，拒绝截断或损坏的数据。
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                width, height = image.size
                has_alpha = "A" in image.getbands() or "transparency" in image.info
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "图片数据无效或尺寸过大") from None
    extension, mime_type = IMAGE_TYPES[image_type]
    return {"width": width, "height": height, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "extension": extension,
            "meta": {"format": image_type, "mime_type": mime_type, "has_alpha": has_alpha}}


def validate_wan_image(asset: dict) -> None:
    path = resolve_asset_path(asset)
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_IMAGE_BYTES + 1)
    except OSError:
        raise HTTPException(422, "首帧图片读取失败") from None
    metadata = inspect_image(data)
    if metadata["meta"]["has_alpha"]:
        raise HTTPException(422, "万相首帧不能带透明通道，请先去除透明")
    if any(not 240 <= metadata[key] <= 8000 for key in ("width", "height")):
        raise HTTPException(422, "万相首帧的宽高必须在 240–8000 像素之间")


def _component(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("素材目录标识无效")
    return value


def _parent(rel_path: str) -> Path:
    storage_root(create=True)
    path = resolve_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkdir 前后都检查，防止已有目录符号链接越界。
    return resolve_path(rel_path)


def save_image(project_id: str, data: bytes, metadata: dict) -> dict:
    rel_path = f"{_component(project_id)}/images/{metadata['sha256']}{metadata['extension']}"
    target = _parent(rel_path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"kind": "image", "source": "upload", "rel_path": rel_path,
            **{key: metadata[key] for key in ("sha256", "bytes", "width", "height", "meta")}}


def discard_file(rel_path: str) -> None:
    """回滚未入库素材；只删除目标文件和已经为空的父目录。"""
    root = storage_root()
    path = resolve_path(rel_path)
    path.unlink(missing_ok=True)
    parent = path.parent
    while parent != root and parent.is_relative_to(root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _video_host(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (parts.scheme not in {"http", "https"} or not host
                or parts.username is not None or parts.password is not None):
            raise ValueError
        # 检查端口语法；白名单按主机名匹配，不受路径或 query 影响。
        _ = parts.port
    except (TypeError, ValueError):
        raise DownloadError("download_url_invalid", "视频结果地址无效") from None
    allowed = any(re.fullmatch(re.escape(pattern.lower()).replace(r"\*", ".*"), host.lower())
                  for pattern in get_settings().video_hosts)
    if not allowed:
        raise DownloadError("download_host_denied", "视频结果地址不在允许的主机名单中")
    return host


def probe_video(path: Path) -> dict:
    """ffprobe 仅允许本地文件协议，不能由媒体内容发起网络读取。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
             "-show_streams", "-show_format", "-of", "json", str(path.resolve())],
            capture_output=True, text=True, timeout=60, check=True,
        )
        raw = json.loads(result.stdout)
        streams = raw.get("streams", [])
        video = next(item for item in streams if item.get("codec_type") == "video")
        width, height = int(video["width"]), int(video["height"])
        # 音轨可能比画面长，优先以视频流时长校验。
        duration_value = video.get("duration")
        if duration_value in (None, "", "N/A"):
            duration_value = raw.get("format", {}).get("duration")
        duration = float(duration_value)
        if width <= 0 or height <= 0 or not math.isfinite(duration) or duration <= 0:
            raise ValueError
        rate = video.get("avg_frame_rate")
        if rate in (None, "", "0/0", "N/A"):
            rate = video.get("r_frame_rate")
        try:
            numerator, denominator = str(rate).split("/")
            fps = float(numerator) / float(denominator)
            if not math.isfinite(fps) or fps <= 0:
                fps = None
        except (TypeError, ValueError, ZeroDivisionError):
            fps = None
        return {"width": width, "height": height, "duration_s": duration, "fps": fps,
                "has_audio": any(item.get("codec_type") == "audio" for item in streams)}
    except FileNotFoundError:
        raise DownloadError("ffprobe_unavailable", "未安装 ffprobe，暂时无法校验视频", retryable=True) from None
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError,
            StopIteration, AttributeError):
        raise DownloadError("invalid_output", "视频文件无法通过媒体校验") from None


async def download_video(url: str, project_id: str, job_id: str, *, transport=None) -> dict:
    """每次只读下载一次；可重试错误交给调度器限制重试次数。"""
    _video_host(url)
    rel_path = (f"{_component(project_id)}/videos/"
                f"{_component(job_id)}-{uuid.uuid4().hex}.mp4")
    temporary = None
    try:
        target = _parent(rel_path)
        # 独立客户端不携带上游 API 密钥、Cookie、环境代理或自动重定向。
        async with httpx.AsyncClient(
            transport=transport, follow_redirects=False, trust_env=False,
            timeout=httpx.Timeout(120, connect=10),
        ) as client:
            async with client.stream("GET", url) as response:
                status = response.status_code
                if status in {403, 404}:
                    raise DownloadError("result_expired", "视频结果地址已过期", expired=True)
                if 300 <= status < 400:
                    raise DownloadError("download_redirect", "视频下载不接受重定向")
                if status != 200:
                    raise DownloadError("download_http_error", f"视频下载返回 HTTP {status}",
                                        retryable=status == 429 or status >= 500)
                declared = response.headers.get("content-length")
                try:
                    length = None if declared is None else int(declared)
                except ValueError:
                    raise DownloadError("download_size_invalid", "视频大小响应头无效") from None
                if length is not None and not 0 < length <= MAX_VIDEO_BYTES:
                    raise DownloadError("download_too_large", "视频不能为空，且不能超过 300MB")
                total = 0
                digest = hashlib.sha256()
                with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as handle:
                    temporary = Path(handle.name)
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            raise DownloadError("download_too_large", "视频不能超过 300MB")
                        handle.write(chunk)
                        digest.update(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                if not total or (length is not None and not response.headers.get("content-encoding")
                                 and total != length):
                    raise DownloadError("download_incomplete", "视频下载未完整结束", retryable=True)
        metadata = await asyncio.to_thread(probe_video, temporary)
        temporary.replace(target)
        return {"rel_path": rel_path, "sha256": digest.hexdigest(), "bytes": total, **metadata}
    except DownloadError:
        raise
    except httpx.HTTPError:
        raise DownloadError("download_transport", "视频下载暂时失败", retryable=True) from None
    except OSError:
        raise DownloadError("download_storage", "视频保存暂时失败", retryable=True) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
