# -*- coding: utf-8 -*-
"""Validate and normalize an uploaded reference into a private, metadata-free PNG."""
import base64
import binascii
import io
import math
import os
import tempfile
import uuid
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps

from utils import media


MAX_REFERENCE_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REFERENCE_BASE64_CHARS = 4 * ((MAX_REFERENCE_UPLOAD_BYTES + 2) // 3) + 128
_MAX_INPUT_PIXELS = 40_000_000
_MAX_OUTPUT_PIXELS = 4_000_000
_MIN_OUTPUT_PIXELS = 512 * 512
_MAX_OUTPUT_EDGE = 2048
_MAX_OUTPUT_BYTES = 10 * 1024 * 1024
_MIME_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/jpg": "JPEG", "image/webp": "WEBP"}


def _decode_upload(image_base64: str) -> tuple[bytes, str | None]:
    if not isinstance(image_base64, str) or not image_base64:
        raise HTTPException(status_code=400, detail="请选择 PNG、JPEG 或 WebP 参考图片")
    if len(image_base64) > MAX_REFERENCE_BASE64_CHARS:
        raise HTTPException(status_code=413, detail="单张参考图片不能超过 5MB")
    expected_format = None
    encoded = image_base64
    if image_base64.startswith("data:"):
        try:
            prefix, encoded = image_base64.split(",", 1)
            mime, encoding = prefix[5:].lower().split(";", 1)
            expected_format = _MIME_FORMATS[mime]
            if encoding != "base64":
                raise ValueError("unsupported encoding")
        except (KeyError, ValueError):
            raise HTTPException(status_code=400, detail="参考图片格式无效，只支持 PNG、JPEG 或 WebP") from None
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="参考图片编码无效，请重新选择图片") from None
    if not data:
        raise HTTPException(status_code=400, detail="参考图片为空")
    if len(data) > MAX_REFERENCE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="单张参考图片不能超过 5MB")
    return data, expected_format


def _normalized_size(width: int, height: int) -> tuple[int, int]:
    pixels = width * height
    if pixels < _MIN_OUTPUT_PIXELS:
        scale = math.sqrt(_MIN_OUTPUT_PIXELS / pixels)
        return math.ceil(width * scale), math.ceil(height * scale)
    scale = min(1.0, _MAX_OUTPUT_EDGE / max(width, height), math.sqrt(_MAX_OUTPUT_PIXELS / pixels))
    return max(1, math.floor(width * scale)), max(1, math.floor(height * scale))


def _encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def normalize_reference_upload(image_base64: str) -> tuple[bytes, int, int]:
    """Pure normalization: no file writes or provider calls, no original metadata."""
    data, expected_format = _decode_upload(image_base64)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in _MIME_FORMATS.values() or (expected_format and source.format != expected_format):
                    raise HTTPException(status_code=400, detail="参考图片格式不匹配，只支持 PNG、JPEG 或 WebP")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > _MAX_INPUT_PIXELS:
                    raise HTTPException(status_code=400, detail="参考图片尺寸过大，请选择不超过四千万像素的图片")
                if max(width, height) > 4 * min(width, height):
                    raise HTTPException(status_code=400, detail="参考图片过长或过窄，请裁剪到 4:1 以内的比例")
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
                converted = oriented.convert(mode)
                # A fresh image avoids carrying EXIF, PNG text, ICC, XMP or DPI
                # fields through Pillow's implicit image.info save behavior.
                normalized = Image.new(mode, converted.size)
                normalized.paste(converted)
                target_size = _normalized_size(*normalized.size)
                if normalized.size != target_size:
                    normalized = normalized.resize(target_size, Image.Resampling.LANCZOS)
                output = _encode_png(normalized)
                # Noisy JPEG/WebP may grow as PNG. Reduce proportionally until
                # the stored source meets the provider's 10MB input limit.
                while len(output) > _MAX_OUTPUT_BYTES:
                    scale = min(0.9, math.sqrt(_MAX_OUTPUT_BYTES / len(output)) * 0.95)
                    reduced = (max(1, math.floor(normalized.width * scale)), max(1, math.floor(normalized.height * scale)))
                    if reduced[0] * reduced[1] < _MIN_OUTPUT_PIXELS:
                        raise HTTPException(status_code=413, detail="参考图片转换后过大，请选择较简单的图片")
                    normalized = normalized.resize(reduced, Image.Resampling.LANCZOS)
                    output = _encode_png(normalized)
                width, height = normalized.size
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="参考图片内容损坏或尺寸过大，请重新选择图片") from None
    return output, width, height


def prepare_reference_upload(image_base64: str) -> dict:
    """Normalize and atomically save one reference; the caller retains ownership."""
    data, width, height = normalize_reference_upload(image_base64)
    filename = f"reference_{uuid.uuid4().hex}.png"
    destination = os.path.join(media.UPLOADS_DIR, filename)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=media.UPLOADS_DIR, prefix=".reference_", delete=False) as file:
            temporary = file.name
            file.write(data)
        os.replace(temporary, destination)
    except OSError:
        raise HTTPException(status_code=500, detail="参考图片暂时无法保存，请稍后再试") from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return {"image_path": f"/uploads/{filename}", "width": width, "height": height}
