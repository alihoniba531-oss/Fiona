# -*- coding: utf-8 -*-
"""Offline checks for preparing local reference images without leaking metadata."""
import base64
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image, PngImagePlugin

from utils import media, reference_images


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    return tmp_path


def image_bytes(fmt="PNG", size=(800, 600), mode="RGB", **save_options):
    image = Image.new(mode, size, (30, 80, 140, 120) if mode == "RGBA" else (30, 80, 140))
    output = io.BytesIO()
    image.save(output, format=fmt, **save_options)
    return output.getvalue()


def encoded(data, mime=None):
    raw = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{raw}" if mime else raw


@pytest.mark.parametrize(("fmt", "mime", "mode"), [
    ("PNG", "image/png", "RGB"),
    ("PNG", None, "RGBA"),
    ("JPEG", "image/jpeg", "RGB"),
    ("JPEG", None, "RGB"),
    ("WEBP", "image/webp", "RGBA"),
])
def test_prepare_accepts_supported_data_urls_and_raw_base64(upload_dir, fmt, mime, mode):
    result = reference_images.prepare_reference_upload(encoded(image_bytes(fmt, mode=mode), mime))
    assert set(result) == {"image_path", "width", "height"}
    assert result["image_path"].startswith("/uploads/reference_")
    assert result["image_path"].endswith(".png")
    assert len(result["image_path"].split("reference_", 1)[1].removesuffix(".png")) == 32
    assert (result["width"], result["height"]) == (800, 600)
    source = upload_dir / result["image_path"].split("/")[-1]
    assert source.stat().st_size <= 10 * 1024 * 1024
    with Image.open(source) as saved:
        assert saved.format == "PNG"
        assert saved.mode == mode
        assert saved.size == (800, 600)
        assert saved.info == {}
        if mode == "RGBA":
            assert saved.getpixel((400, 300))[3] == 120
    assert list(upload_dir.iterdir()) == [source]


@pytest.mark.parametrize("size", [(5000, 3000), (3000, 5000), (2200, 2200), (1, 1), (10, 40), (40, 10), (8, 6)])
def test_normalization_bounds_size_and_preserves_aspect_ratio(upload_dir, size):
    png, width, height = reference_images.normalize_reference_upload(encoded(image_bytes(size=size)))
    assert max(width, height) <= 2048
    assert 512 * 512 <= width * height <= 4_000_000
    assert width / height == pytest.approx(size[0] / size[1], rel=0.005)
    with Image.open(io.BytesIO(png)) as result:
        assert result.size == (width, height)
    assert list(upload_dir.iterdir()) == []


def test_exif_orientation_is_applied_and_private_metadata_removed(upload_dir):
    source = Image.new("RGB", (800, 400), "red")
    source.paste("blue", (400, 0, 800, 400))
    exif = Image.Exif()
    exif[274] = 6  # Rotate 90 degrees clockwise.
    exif[315] = "private photographer"
    output = io.BytesIO()
    source.save(output, "JPEG", exif=exif, quality=95, comment=b"private comment")
    result = reference_images.prepare_reference_upload(encoded(output.getvalue(), "image/jpeg"))
    assert (result["width"], result["height"]) == (400, 800)
    saved_path = upload_dir / result["image_path"].split("/")[-1]
    assert b"private photographer" not in saved_path.read_bytes()
    with Image.open(saved_path) as saved:
        assert saved.info == {}
        assert len(saved.getexif()) == 0
        assert saved.getpixel((200, 100))[0] > 220
        assert saved.getpixel((200, 700))[2] > 220


def test_png_text_and_profile_metadata_are_not_retained(upload_dir):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Author", "private author")
    metadata.add_text("XML:com.adobe.xmp", "private xmp")
    data = image_bytes(pnginfo=metadata, icc_profile=b"private profile", dpi=(300, 300))
    png, _, _ = reference_images.normalize_reference_upload(encoded(data, "image/png"))
    with Image.open(io.BytesIO(png)) as result:
        assert result.info == {}
        assert len(result.getexif()) == 0
    assert b"private" not in png
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize("value", [None, "", "@@@", "abc\n123", "纯文本", "data:image/png,AAAA", "data:text/plain;base64,AAAA", "data:image/gif;base64,AAAA", "data:image/png;utf-8;base64,AAAA"])
def test_invalid_encoding_and_mime_leave_no_files(upload_dir, value):
    with pytest.raises(HTTPException) as error:
        reference_images.prepare_reference_upload(value)
    assert error.value.status_code == 400
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize("data", [b"private invalid image", b"\x89PNG\r\n\x1a\ntruncated"])
def test_corrupt_images_leave_no_partial_file_or_sensitive_error(upload_dir, data):
    with pytest.raises(HTTPException) as error:
        reference_images.prepare_reference_upload(encoded(data, "image/png"))
    assert error.value.status_code == 400
    assert "private" not in error.value.detail
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize(("fmt", "mime"), [("GIF", None), ("JPEG", "image/png"), ("BMP", None)])
def test_unsupported_or_mismatched_format_is_rejected(upload_dir, fmt, mime):
    with pytest.raises(HTTPException) as error:
        reference_images.prepare_reference_upload(encoded(image_bytes(fmt), mime))
    assert error.value.status_code == 400
    assert list(upload_dir.iterdir()) == []


def test_raw_bytes_over_five_mb_are_rejected_before_image_decode(upload_dir):
    too_large = b"x" * (reference_images.MAX_REFERENCE_UPLOAD_BYTES + 1)
    with pytest.raises(HTTPException) as error:
        reference_images.prepare_reference_upload(encoded(too_large))
    assert error.value.status_code == 413
    assert "5MB" in error.value.detail
    assert list(upload_dir.iterdir()) == []


def test_excessive_encoded_length_is_rejected_without_decoding(upload_dir, monkeypatch):
    def forbidden_decode(*args, **kwargs):
        pytest.fail("oversized encoded content must not be decoded")

    monkeypatch.setattr(reference_images.base64, "b64decode", forbidden_decode)
    with pytest.raises(HTTPException) as error:
        reference_images.prepare_reference_upload("x" * (reference_images.MAX_REFERENCE_BASE64_CHARS + 1))
    assert error.value.status_code == 413
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize("size", [(10, 41), (41, 10)])
def test_extreme_ratios_are_rejected_explicitly(upload_dir, size):
    with pytest.raises(HTTPException, match="4:1"):
        reference_images.prepare_reference_upload(encoded(image_bytes(size=size)))
    assert list(upload_dir.iterdir()) == []


def test_pixel_cap_and_pillow_bomb_warning_are_rejected(upload_dir, monkeypatch):
    data = encoded(image_bytes(size=(20, 20)))
    monkeypatch.setattr(reference_images, "_MAX_INPUT_PIXELS", 399)
    with pytest.raises(HTTPException, match="四千万"):
        reference_images.prepare_reference_upload(data)
    monkeypatch.setattr(reference_images, "_MAX_INPUT_PIXELS", 40_000_000)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 399)
    with pytest.raises(HTTPException, match="内容损坏或尺寸过大"):
        reference_images.prepare_reference_upload(data)
    assert list(upload_dir.iterdir()) == []


def test_output_is_reduced_again_when_png_conversion_exceeds_provider_limit(upload_dir, monkeypatch):
    original_encode = reference_images._encode_png
    seen_sizes = []

    def oversized_first(image):
        seen_sizes.append(image.size)
        if len(seen_sizes) == 1:
            return b"x" * (reference_images._MAX_OUTPUT_BYTES + 1)
        return original_encode(image)

    monkeypatch.setattr(reference_images, "_encode_png", oversized_first)
    png, width, height = reference_images.normalize_reference_upload(encoded(image_bytes(size=(1600, 1200))))
    assert len(seen_sizes) == 2
    assert width < 1600 and height < 1200
    assert width * height >= 512 * 512
    assert len(png) <= 10 * 1024 * 1024
    assert list(upload_dir.iterdir()) == []


def test_failed_atomic_save_removes_temporary_file(upload_dir, monkeypatch):
    def failed_replace(*args):
        raise OSError("private filesystem detail")

    monkeypatch.setattr(reference_images.os, "replace", failed_replace)
    with pytest.raises(HTTPException) as error:
        reference_images.prepare_reference_upload(encoded(image_bytes()))
    assert error.value.status_code == 500
    assert "private" not in error.value.detail
    assert list(upload_dir.iterdir()) == []


def test_atomic_save_does_not_follow_existing_destination_symlink(upload_dir, monkeypatch):
    marker = "f" * 32
    target = upload_dir.parent / "private-original.txt"
    target.write_bytes(b"private original")
    destination = upload_dir / f"reference_{marker}.png"
    destination.symlink_to(target)
    monkeypatch.setattr(reference_images.uuid, "uuid4", lambda: SimpleNamespace(hex=marker))
    result = reference_images.prepare_reference_upload(encoded(image_bytes()))
    assert result["image_path"] == f"/uploads/reference_{marker}.png"
    assert target.read_bytes() == b"private original"
    assert not destination.is_symlink()
    with Image.open(destination) as normalized:
        assert normalized.format == "PNG"
