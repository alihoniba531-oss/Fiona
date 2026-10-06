# -*- coding: utf-8 -*-
import asyncio
import base64
import binascii
import io
import os
import shutil
import subprocess
import tempfile
import threading
import warnings
import weakref

import anyio
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

# 本地开发默认写仓库内；生产可通过环境变量把可变数据移出只读代码目录。
UPLOADS_DIR = os.getenv("FIONA_UPLOADS_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "uploads"
)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# 单张图上限 5MB，base64 解码前粗筛 base64 长度（base64 比原始大约 33%）
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BASE64_CHARS = 4 * ((MAX_IMAGE_BYTES + 2) // 3) + 256
# magic bytes → 文件扩展名映射
_MIME_SNIFF = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff",      "jpg"),
    (b"GIF87a",            "gif"),
    (b"GIF89a",            "gif"),
    (b"RIFF",              "webp"),  # 还要校验偏移 8 处是 WEBP，下面会做
]

_VIDEO_SNIFF = [
    (b"\x1a\x45\xdf\xa3", "webm"),
]
_IMAGE_BMFF_BRANDS = {
    b"heic", b"heix", b"hevc", b"hevx", b"heis", b"hevm",
    b"mif1", b"mif2", b"msf1", b"miaf", b"avif", b"avis",
}
_VIDEO_BMFF_BRANDS = {
    b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42",
    b"avc1", b"dash", b"M4V ", b"qt  ",
}
_MAX_PLAZA_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_PLAZA_VIDEO_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_PIL_FORMAT_BY_EXT = {"png": "PNG", "jpg": "JPEG", "gif": "GIF", "webp": "WEBP"}
_MAX_ANIMATION_FRAMES = 300
_MAX_ANIMATION_PIXELS = 200_000_000
_REENCODE_SLOTS = threading.BoundedSemaphore(2)
_PLAZA_REENCODE_SLOTS = weakref.WeakKeyDictionary()
_CHAT_REENCODE_TIMEOUT = 10


def _validate_decodable_image(source, ext: str) -> None:
    """确认魔数后的内容确实是完整、尺寸受限的图片，而不是伪造前缀。"""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                if image.format != _PIL_FORMAT_BY_EXT.get(ext) and not (
                    ext == "jpg" and image.format == "MPO"
                ):
                    raise ValueError("image format does not match signature")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
                    raise ValueError("image dimensions exceed limit")
                image.verify()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="图片内容损坏或尺寸过大") from exc


def _strip_image_metadata(source, ext: str, *, slot_timeout: float | None = None) -> bytes:
    """重建像素后编码；只携带明确允许的 ICC 和动画播放参数。"""
    if not _REENCODE_SLOTS.acquire(timeout=slot_timeout):
        raise HTTPException(status_code=503, detail="服务器繁忙，请稍后再发图片")
    frames = []
    try:
        _validate_decodable_image(source, ext)
        if hasattr(source, "seek"):
            source.seek(0)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source) as image:
                    animated = ext in {"gif", "webp"} and getattr(image, "n_frames", 1) > 1
                    frame_count = image.n_frames if animated else 1
                    if animated and (
                        frame_count > _MAX_ANIMATION_FRAMES
                        or frame_count * image.width * image.height > _MAX_ANIMATION_PIXELS
                    ):
                        raise HTTPException(status_code=400, detail="动图帧数过多，请压缩后再发")
                    icc = image.info.get("icc_profile")
                    loop = image.info.get("loop")
                    durations = []
                    gif_transparency = False
                    canvas_width, canvas_height = image.size
                    for index in range(frame_count):
                        image.seek(index)
                        if image.width * image.height > _MAX_IMAGE_PIXELS:
                            raise ValueError("image dimensions exceed limit")
                        canvas_width = max(canvas_width, image.width)
                        canvas_height = max(canvas_height, image.height)
                        if animated and frame_count * canvas_width * canvas_height > _MAX_ANIMATION_PIXELS:
                            raise HTTPException(status_code=400, detail="动图帧数过多，请压缩后再发")
                        image.load()
                        durations.append(image.info.get("duration", 0))
                        # exif_transpose copies even when no rotation is needed.
                        oriented = ImageOps.exif_transpose(image) if image.getexif().get(274, 1) in range(2, 9) else image
                        converted = None
                        try:
                            mode = oriented.mode
                            if mode == "P":
                                mode = "RGBA" if "transparency" in oriented.info else "RGB"
                            elif ext == "png" and "transparency" in oriented.info and mode in {"RGB", "L"}:
                                mode = "RGBA" if mode == "RGB" else "LA"
                            if ext == "jpg" and mode not in {"RGB", "L", "CMYK"}:
                                mode = "RGB"
                            converted = oriented.convert(mode) if mode != oriented.mode else oriented
                            if oriented is not image and converted is not oriented:
                                oriented.close()
                            rebuilt = Image.new(mode, converted.size)
                            rebuilt.paste(converted)
                            frames.append(rebuilt)
                            if ext == "gif" and mode == "RGBA" and rebuilt.getextrema()[3][0] < 255:
                                gif_transparency = True
                        finally:
                            if converted is not None and converted is not image:
                                converted.close()
                            if oriented is not image:
                                oriented.close()
                    options = {"icc_profile": icc} if icc else {}
                    if ext in {"jpg", "webp"}:
                        options["quality"] = 90
                    if animated:
                        options.update(save_all=True, append_images=frames[1:], duration=durations)
                        if loop is not None:
                            options["loop"] = loop
                        if ext == "gif" and gif_transparency:
                            # Composed transparent canvases must erase old pixels.
                            # Opaque frames retain Pillow's frame differences.
                            options["disposal"] = 2
                    output = io.BytesIO()
                    frames[0].save(output, format=_PIL_FORMAT_BY_EXT[ext], **options)
                    return output.getvalue()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="图片内容损坏或尺寸过大") from exc
    finally:
        for frame in frames:
            frame.close()
        _REENCODE_SLOTS.release()


def _strip_video_metadata(source: str, destination: str, ext: str) -> None:
    """只映射视频与首条音轨，保留压缩流及旋转矩阵，移除标签和定位轨。"""
    with _REENCODE_SLOTS:
        executable = shutil.which("ffmpeg")
        if not executable:
            raise HTTPException(status_code=503, detail="服务器暂时无法处理视频，请改发图片")
        container = {"mp4": "mp4", "mov": "mov", "webm": "webm"}[ext]
        argv = [
            executable, "-nostdin", "-y", "-i", str(source),
            "-map", "0:V:0", "-map", "0:a:0?", "-c", "copy",
            "-map_metadata", "-1", "-map_metadata:s", "-1", "-map_chapters", "-1",
            "-dn", "-sn", "-fflags", "+bitexact",
        ]
        if ext == "mp4":
            argv.extend(["-movflags", "+faststart"])
        argv.extend(["-f", container, str(destination)])
        try:
            subprocess.run(argv, check=True, capture_output=True, timeout=30)
            if not os.path.isfile(destination) or not os.path.getsize(destination):
                raise ValueError("empty video output")
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="视频处理失败，请转成 MP4 后再发") from exc


def _upload_temporary() -> str:
    descriptor, path = tempfile.mkstemp(prefix=".upload_", dir=UPLOADS_DIR)
    os.close(descriptor)
    return path


def _unlink_upload(path: str | None) -> None:
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


def _process_upload(source: str, destination: str, ext: str, media_type: str) -> None:
    if media_type == "video":
        _strip_video_metadata(source, destination, ext)
    else:
        data = _strip_image_metadata(source, ext)
        with open(destination, "wb") as output:
            output.write(data)


async def _process_upload_off_loop(source: str, destination: str, ext: str, media_type: str) -> None:
    loop = asyncio.get_running_loop()
    slots = _PLAZA_REENCODE_SLOTS.setdefault(loop, asyncio.Semaphore(2))
    await slots.acquire()
    worker = asyncio.create_task(asyncio.to_thread(_process_upload, source, destination, ext, media_type))

    def finished(task):
        slots.release()
        if not task.cancelled():
            task.exception()

    worker.add_done_callback(finished)
    try:
        await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Anyio cancellation keeps firing at every await unless shielded. A
        # second explicit asyncio cancellation falls back to deferred cleanup.
        try:
            with anyio.CancelScope(shield=True):
                await asyncio.shield(worker)
        except (asyncio.CancelledError, Exception):
            pass
        worker.add_done_callback(lambda _: (_unlink_upload(source), _unlink_upload(destination)))
        raise


def _sniff_image_ext(data: bytes) -> str | None:
    """嗅探前 12 字节判图片类型。不是已知图片格式返回 None。"""
    for magic, ext in _MIME_SNIFF:
        if data.startswith(magic):
            if ext == "webp" and not (len(data) >= 12 and data[8:12] == b"WEBP"):
                continue
            return ext
    return None


def _bmff_brands(data: bytes) -> list[bytes]:
    if len(data) < 12 or data[4:8] != b"ftyp":
        return []
    box_size = int.from_bytes(data[:4], "big")
    end = min(len(data), box_size) if box_size >= 16 else len(data)
    return [data[8:12], *(data[i:i + 4] for i in range(16, end - 3, 4))]


def _sniff_video_ext(data: bytes) -> str | None:
    """嗅探常见短视频格式。返回保存扩展名，不信任用户上传的文件名。"""
    for magic, ext in _VIDEO_SNIFF:
        if data.startswith(magic):
            return ext
    brands = _bmff_brands(data)
    if brands:
        brand = brands[0]
        if any(item in _IMAGE_BMFF_BRANDS for item in brands):
            return None
        if brand == b"qt  ":
            return "mov"
        if brand in _VIDEO_BMFF_BRANDS or brand.startswith((b"3gp", b"3g2")):
            return "mp4"
    return None


async def _save_plaza_upload(file: UploadFile) -> tuple[str, str]:
    """保存广场媒体，校验魔数和大小，返回 (media_path, media_type)。"""
    import uuid as _uuid

    first = await file.read(8192)
    ext = _sniff_image_ext(first[:12])
    media_type = "image"
    limit = _MAX_PLAZA_IMAGE_BYTES
    if not ext:
        ext = _sniff_video_ext(first)
        media_type = "video"
        limit = _MAX_PLAZA_VIDEO_BYTES
    if not ext:
        if any(brand in _IMAGE_BMFF_BRANDS for brand in _bmff_brands(first)):
            raise HTTPException(
                status_code=400,
                detail="暂不支持 HEIC/AVIF，请转成 JPG 或 PNG 后再发",
            )
        raise HTTPException(status_code=400, detail="只支持常见图片或短视频格式")

    fname = f"plaza_{_uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOADS_DIR, fname)
    total = 0
    source = None
    destination = None
    saved = False
    try:
        source = _upload_temporary()
        destination = _upload_temporary()
        with open(source, "wb") as f:
            if first:
                total += len(first)
                if total > limit:
                    raise HTTPException(status_code=413, detail="文件太大")
                f.write(first)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="文件太大")
                f.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="文件为空")
        await _process_upload_off_loop(source, destination, ext, media_type)
        os.replace(destination, fpath)
        saved = True
        return f"/uploads/{fname}", media_type
    finally:
        _unlink_upload(source)
        _unlink_upload(destination)
        if not saved:
            _unlink_upload(fpath)


def _save_uploaded_image(image_base64: str) -> tuple[str, str]:
    """校验并保存聊天图片，返回（相对路径，规范化 data URI）。

    失败时明确返回 4xx，不能静默返回 None 后继续把未校验原文交给视觉模型。
    """
    raw = image_base64
    if "," in raw:
        prefix, raw = raw.split(",", 1)
        if not prefix.lower().startswith("data:image/") or ";base64" not in prefix.lower():
            raise HTTPException(status_code=400, detail="图片 data URI 格式无效")
    if not raw or len(raw) > MAX_IMAGE_BASE64_CHARS:
        raise HTTPException(status_code=413, detail="图片不能超过 5MB")

    try:
        img_data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="图片 base64 无效") from exc
    if not img_data:
        raise HTTPException(status_code=400, detail="图片为空")
    if len(img_data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 5MB")

    ext = _sniff_image_ext(img_data[:12])
    if not ext:
        raise HTTPException(status_code=400, detail="只支持 PNG、JPEG、GIF 或 WebP 图片")
    img_data = _strip_image_metadata(io.BytesIO(img_data), ext, slot_timeout=_CHAT_REENCODE_TIMEOUT)

    import uuid as _uuid
    fname = f"{_uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOADS_DIR, fname)
    temporary = None
    saved = False
    mime = "jpeg" if ext == "jpg" else ext
    normalized = base64.b64encode(img_data).decode("ascii")
    result = (f"/uploads/{fname}", f"data:image/{mime};base64,{normalized}")
    try:
        temporary = _upload_temporary()
        with open(temporary, "wb") as f:
            f.write(img_data)
        os.replace(temporary, fpath)
        saved = True
    except OSError as exc:
        print(f"[upload] save failed type={type(exc).__name__}", flush=True)
        raise HTTPException(status_code=500, detail="图片保存失败") from exc
    finally:
        _unlink_upload(temporary)
        if not saved:
            _unlink_upload(fpath)
    return result


def delete_uploaded_files(paths: list[str]) -> tuple[list[str], list[str]]:
    """只删除 uploads 根目录下由应用记录的普通文件，拒绝路径穿越。"""
    deleted: list[str] = []
    failed: list[str] = []
    upload_root = os.path.realpath(UPLOADS_DIR)
    for stored_path in dict.fromkeys(paths):
        if not isinstance(stored_path, str) or not stored_path.startswith("/uploads/"):
            failed.append(str(stored_path))
            continue
        filename = stored_path.removeprefix("/uploads/")
        if not filename or os.path.basename(filename) != filename:
            failed.append(stored_path)
            continue
        target = os.path.realpath(os.path.join(upload_root, filename))
        if os.path.dirname(target) != upload_root:
            failed.append(stored_path)
            continue
        try:
            os.unlink(target)
            deleted.append(stored_path)
        except FileNotFoundError:
            # 数据已经不可引用且文件不存在，也视为清理完成。
            deleted.append(stored_path)
        except OSError:
            failed.append(stored_path)
    return deleted, failed
