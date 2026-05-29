# -*- coding: utf-8 -*-
import base64
import os

from fastapi import HTTPException, UploadFile

# 图片上传目录
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# 单张图上限 5MB，base64 解码前粗筛 base64 长度（base64 比原始大约 33%）
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
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


def _save_uploaded_image(image_base64: str) -> str | None:
    """保存 base64 图片到 uploads 目录，返回相对 URL 路径。失败返回 None。
    校验：base64 长度上限、解码后 mime 嗅探、文件名 uuid（不可猜）。"""
    try:
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        # 粗筛：base64 串本身长度上限（解码后约小 25%）
        if len(image_base64) > _MAX_IMAGE_BYTES * 4 // 3 + 1024:
            print(f"[upload] reject: base64 too large ({len(image_base64)} chars)", flush=True)
            return None
        img_data = base64.b64decode(image_base64, validate=False)
        if len(img_data) > _MAX_IMAGE_BYTES:
            print(f"[upload] reject: decoded too large ({len(img_data)} bytes)", flush=True)
            return None
        ext = _sniff_image_ext(img_data[:12])
        if not ext:
            print(f"[upload] reject: not a known image format (head={img_data[:8].hex()})", flush=True)
            return None
        # 文件名用 uuid4 hex，不可枚举（修 #6 跨用户图泄露的最小成本方案）
        import uuid as _uuid
        fname = f"{_uuid.uuid4().hex}.{ext}"
        fpath = os.path.join(UPLOADS_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(img_data)
        return f"/uploads/{fname}"
    except Exception as e:
        print(f"[upload] save failed: {type(e).__name__}: {e}", flush=True)
        return None
