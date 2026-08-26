# -*- coding: utf-8 -*-
import base64
import binascii
import os

from fastapi import HTTPException, UploadFile

# 图片上传目录
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
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
_MAX_PLAZA_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_PLAZA_VIDEO_BYTES = 20 * 1024 * 1024

def _sniff_image_ext(data: bytes) -> str | None:
    """嗅探前 12 字节判图片类型。不是已知图片格式返回 None。"""
    for magic, ext in _MIME_SNIFF:
        if data.startswith(magic):
            if ext == "webp" and not (len(data) >= 12 and data[8:12] == b"WEBP"):
                continue
            return ext
    return None


def _sniff_video_ext(data: bytes) -> str | None:
    """嗅探常见短视频格式。返回保存扩展名，不信任用户上传的文件名。"""
    for magic, ext in _VIDEO_SNIFF:
        if data.startswith(magic):
            return ext
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand == b"qt  ":
            return "mov"
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
        ext = _sniff_video_ext(first[:16])
        media_type = "video"
        limit = _MAX_PLAZA_VIDEO_BYTES
    if not ext:
        raise HTTPException(status_code=400, detail="只支持常见图片或短视频格式")

    fname = f"plaza_{_uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOADS_DIR, fname)
    total = 0
    try:
        with open(fpath, "wb") as f:
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
    except Exception:
        try:
            os.unlink(fpath)
        except OSError:
            pass
        raise
    if total == 0:
        try:
            os.unlink(fpath)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="文件为空")
    return f"/uploads/{fname}", media_type


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

    import uuid as _uuid
    fname = f"{_uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOADS_DIR, fname)
    try:
        with open(fpath, "wb") as f:
            f.write(img_data)
    except OSError as exc:
        print(f"[upload] save failed: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="图片保存失败") from exc

    mime = "jpeg" if ext == "jpg" else ext
    normalized = base64.b64encode(img_data).decode("ascii")
    return f"/uploads/{fname}", f"data:image/{mime};base64,{normalized}"


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
