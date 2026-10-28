#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare Fiona's Pillow-dependent image paths between two Pillow versions.

The harness only uses the Python standard library and Pillow.  Fixtures are
built in memory; nothing is read from the repository or from the filesystem.
The two external paths it needs are supplied on the command line / via
environment variables:

  run      --output <json> --pixels <dir> [--uploads-dir <dir>]
           FIONA_UPLOADS_DIR must be set (or --uploads-dir supplied) before
           Fiona's utils.media is imported.

  compare  --before <json> --after <json> --before-pixels <dir>
           --after-pixels <dir> --output <json>

Typical use from the repository root (all paths are supplied by the caller;
the placeholders below are intentionally not real absolute paths):

  FIONA_UPLOADS_DIR=<uploads-dir> PYTHONPATH=backend \\
      backend/.venv/bin/python docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py \\
      run --output <after.json> --pixels <after-pixels-dir>

  python3 docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py compare \\
      --before <before.json> --after <after.json> \\
      --before-pixels <before-pixels-dir> --after-pixels <after-pixels-dir> \\
      --output <compare.json>

The JSON output deliberately contains no timestamps and no absolute paths so
that repeated runs can be diffed directly.  Pixel files are named after the
stable case id and contain raw RGBA bytes, first frame only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sys
from pathlib import Path

PNG_TEXT_CHUNKS = {"tEXt", "iTXt", "zTXt"}
XMP_SIGNATURES = (b"http://ns.adobe.com/xap/1.0/", b"<x:xmpmeta")

# A fixed, valid littleCMS sRGB profile (588 bytes, also used as the expected
# ICC payload).  Embedding it keeps the fixture byte-identical even if the two
# Pillow builds happen to ship different Profile objects.
ICC_PROFILE_B64 = (
    "AAACTGxjbXMEQAAAbW50clJHQiBYWVogB+oACgAbAAoAEwARYWNzcEFQUEwAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAPbWAAEAAAAA0y1sY21zAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAALZGVzYwAAAQgAAAA2Y3BydAAAAUAAAABMd3RwdAAAAYwAAAAUY2hhZAAAAaAAAAAs"
    "clhZWgAAAcwAAAAUYlhZWgAAAeAAAAAUZ1hZWgAAAfQAAAAUclRSQwAAAggAAAAgZ1RSQwAAAggAAAAg"
    "YlRSQwAAAggAAAAgY2hybQAAAigAAAAkbWx1YwAAAAAAAAABAAAADGVuVVMAAAAaAAAAHABzAFIARwBC"
    "ACAAYgB1AGkAbAB0AC0AaQBuAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAADAAAAAcAE4AbwAgAGMAbwBw"
    "AHkAcgBpAGcAaAB0ACwAIAB1AHMAZQAgAGYAcgBlAGUAbAB5WFlaIAAAAAAAAPbWAAEAAAAA0y1zZjMy"
    "AAAAAAABDEIAAAXe///zJQAAB5MAAP2Q///7of///aIAAAPcAADAblhZWiAAAAAAAABvoAAAOPUAAAOQ"
    "WFlaIAAAAAAAACSfAAAPhAAAtsNYWVogAAAAAAAAYpcAALeHAAAY2XBhcmEAAAAAAAMAAAACZmYAAPKn"
    "AAANWQAAE9AAAApbY2hybQAAAAAAAwAAAACj1wAAVHsAAEzNAACZmgAAJmYAAA9c"
)

XMP_PAYLOAD = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
    b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description rdf:about="" xmlns:fiona="urn:fiona:verify">'
    b"<fiona:marker>strip-me</fiona:marker>"
    b"</rdf:Description></rdf:RDF></x:xmpmeta>"
)

_STRIP_FIELDS = ("format", "size", "mode", "n_frames", "durations", "loop")


class FixtureError(RuntimeError):
    """Raised when a generated fixture does not exercise what it claims to."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def _icc_profile() -> bytes:
    return base64.b64decode(ICC_PROFILE_B64)


def _png_chunk_types(data: bytes) -> list[str] | None:
    """Return PNG chunk names without copying payloads; None for non-PNG."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    chunks: list[str] = []
    offset = 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8].decode("ascii", "replace")
        chunks.append(chunk_type)
        offset += 12 + length
        if chunk_type == "IEND":
            break
    return chunks


# ---------------------------------------------------------------------------
# Deterministic in-memory fixtures
# ---------------------------------------------------------------------------

def _pattern_rgb(size: tuple[int, int], variant: int = 0):
    """A deterministic gradient/pattern built without version-sensitive drawing.

    A 256x256 base is made from raw bytes and enlarged with NEAREST resampling,
    so both Pillow builds start from identical pixels.  ``variant`` changes the
    pixels, which keeps animated WebP frames from being merged.
    """
    from PIL import Image

    width, height = size
    base = bytearray(256 * 256 * 3)
    blue_shift = variant * 40
    for y in range(256):
        row = bytearray(256 * 3)
        for x in range(256):
            offset = x * 3
            row[offset] = x
            row[offset + 1] = y
            row[offset + 2] = (x * 7 + y * 13 + blue_shift) & 0xFF
        base[y * 768:(y + 1) * 768] = row
    image = Image.frombytes("RGB", (256, 256), bytes(base))
    if size != (256, 256):
        image = image.resize(size, Image.Resampling.NEAREST)
    data = bytearray(image.tobytes())

    # A flat colored rectangle makes JPEG/WebP encoder differences visible.
    x0, x1 = max(1, width // 8), max(2, width // 3)
    y0, y1 = max(1, height // 8), max(2, height // 2)
    fill = bytes((0xFF, 0x40, (0x20 + blue_shift) & 0xFF))
    for y in range(y0, min(y1, height)):
        start = (y * width + x0) * 3
        data[start:start + (x1 - x0) * 3] = fill * (x1 - x0)
    return Image.frombytes("RGB", size, bytes(data))


def _alpha_gradient(size: tuple[int, int]):
    """Deterministic alpha channel with a fully transparent hole."""
    from PIL import Image

    width, height = size
    alpha = bytearray(256 * 256)
    for y in range(256):
        alpha[y * 256:(y + 1) * 256] = bytes([y]) * 256
    for y in range(32, 96):
        alpha[y * 256 + 96:y * 256 + 160] = b"\x00" * 64
    image = Image.frombytes("L", (256, 256), bytes(alpha))
    if size != (256, 256):
        image = image.resize(size, Image.Resampling.NEAREST)
    return image


def _palette_image(size: tuple[int, int], shift: int = 0):
    from PIL import Image

    width, height = size
    palette: list[int] = []
    for index in range(256):
        palette.extend((
            (index * 37 + shift) & 0xFF,
            (index * 91 + shift * 3) & 0xFF,
            (index * 53 + shift * 7) & 0xFF,
        ))
    data = bytearray(width * height)
    x0, x1 = max(1, width // 10), max(2, width // 2)
    y0, y1 = max(1, height // 10), max(2, height - height // 10)
    for y in range(y0, min(y1, height)):
        data[y * width + x0:y * width + x1] = b"\x01" * (x1 - x0)
    x2, x3 = max(x1 + 1, width // 2 + 1), max(x1 + 2, width - width // 10)
    y2, y3 = max(1, height // 4), max(2, 3 * height // 4)
    for y in range(y2, min(y3, height)):
        data[y * width + x2:y * width + x3] = b"\x02" * (x3 - x2)
    image = Image.frombytes("P", (width, height), bytes(data))
    image.putpalette(palette)
    return image


def _jpeg_exif_gps_icc_xmp() -> bytes:
    from PIL import Image

    image = _pattern_rgb((1200, 800))
    exif = Image.Exif()
    exif[274] = 6  # Orientation: rotate 90 degrees clockwise on display.
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (37.0, 46.0, 30.0)
    gps[3] = "E"
    gps[4] = (122.0, 25.0, 10.0)
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=95,
        exif=exif.tobytes(),
        icc_profile=_icc_profile(),
        xmp=XMP_PAYLOAD,
    )
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        check_exif = check.getexif()
        _require(274 in check_exif and int(check_exif[274]) == 6, "JPEG fixture lost Orientation")
        _require(len(check_exif.get_ifd(0x8825)) >= 4, "JPEG fixture lost GPS tags")
        _require("icc_profile" in check.info, "JPEG fixture lost ICC profile")
    _require(XMP_SIGNATURES[0] in data, "JPEG fixture lost XMP APP1 segment")
    return data


def _mpo_two_frames() -> bytes:
    from PIL import Image

    frames = [_pattern_rgb((1000, 700)), _pattern_rgb((700, 500))]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="MPO",
        save_all=True,
        append_images=frames[1:],
        quality=90,
    )
    for frame in frames:
        frame.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(check.format == "MPO", "MPO fixture is not MPO")
        _require(int(getattr(check, "n_frames", 1)) == 2, "MPO fixture does not have 2 frames")
    return data


def _png_text_iccp_palette_transparency() -> bytes:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    image = _palette_image((600, 400))
    image.info["transparency"] = 0
    pnginfo = PngInfo()
    pnginfo.add_text("Comment", "fiona-verify-secret-text")
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="PNG",
        pnginfo=pnginfo,
        icc_profile=_icc_profile(),
        transparency=0,
    )
    image.close()
    data = buffer.getvalue()
    chunks = _png_chunk_types(data) or []
    _require("tEXt" in chunks, "PNG fixture lost tEXt chunk")
    _require("iCCP" in chunks, "PNG fixture lost iCCP chunk")
    with Image.open(io.BytesIO(data)) as check:
        _require(check.mode == "P", "PNG fixture is not palette mode")
        _require("transparency" in check.info, "PNG fixture lost palette transparency")
    return data


def _gif_three_frames() -> bytes:
    from PIL import Image

    frames = [_palette_image((240, 160), shift=index * 40) for index in range(3)]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[100, 200, 300],
        loop=0,
        transparency=0,
        disposal=2,
    )
    for frame in frames:
        frame.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(int(check.n_frames) == 3, "GIF fixture does not have 3 frames")
        durations = []
        for index in range(3):
            check.seek(index)
            check.load()
            durations.append(check.info.get("duration"))
        _require(durations == [100, 200, 300], "GIF fixture durations are wrong")
        _require(check.info.get("loop") == 0, "GIF fixture lost loop=0")
    return data


def _webp_static_exif() -> bytes:
    from PIL import Image

    image = _pattern_rgb((900, 600))
    exif = Image.Exif()
    exif[271] = "FionaVerify"
    exif[272] = "PillowCompare"
    exif[274] = 1
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=90, exif=exif.tobytes())
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(check.format == "WEBP", "WebP fixture is not WebP")
        _require(len(list(check.getexif())) >= 2, "WebP fixture lost EXIF")
    return data


def _webp_three_frames() -> bytes:
    from PIL import Image

    frames = [_pattern_rgb((320, 200), variant=index) for index in range(3)]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=[120, 180, 240],
        loop=0,
        quality=80,
    )
    for frame in frames:
        frame.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(int(getattr(check, "n_frames", 1)) == 3, "WebP fixture does not have 3 frames")
        _require(check.info.get("loop") == 0, "WebP fixture lost loop=0")
    return data


def _oversized_png() -> bytes:
    from PIL import Image

    image = Image.new("L", (8000, 6000), 128)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(check.size == (8000, 6000), "Oversized PNG fixture has wrong size")
    return data


def _gif_301_frames() -> bytes:
    from PIL import Image

    frames = []
    for index in range(301):
        image = Image.new("P", (8, 8), 0)
        image.putpalette([0] * 768)
        data = bytearray(64)
        data[(index % 8) + (index // 8 % 8) * 8] = 1
        frames.append(Image.frombytes("P", (8, 8), bytes(data)))
        frames[-1].putpalette([0] * 768)
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[20] * 301,
        loop=0,
    )
    for frame in frames:
        frame.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(int(check.n_frames) == 301, "GIF fixture does not have 301 frames")
    return data


def _reference_orientation_jpeg() -> str:
    from PIL import Image

    image = _pattern_rgb((1200, 800))
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92, exif=exif.tobytes())
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(int(check.getexif().get(274, 0)) == 6, "Reference JPEG lost Orientation")
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _reference_overlong_ratio() -> str:
    from PIL import Image

    image = _pattern_rgb((3000, 600))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(max(check.size) > 4 * min(check.size), "Reference JPEG is not overlong")
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _reference_oversized_pixels() -> str:
    from PIL import Image

    image = Image.new("L", (8000, 6000), 120)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(check.width * check.height > 40_000_000, "Reference PNG is not oversized")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _claude_large_jpeg() -> str:
    from PIL import Image

    image = _pattern_rgb((3000, 2000))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(max(check.size) > 2000, "Claude JPEG fixture is not large enough")
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _claude_transparent_png() -> str:
    from PIL import Image

    size = (2400, 1800)
    image = _pattern_rgb(size).convert("RGBA")
    alpha = _alpha_gradient(size)
    image.putalpha(alpha)
    alpha.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        _require(check.mode == "RGBA", "Claude PNG fixture is not RGBA")
        _require("A" in check.getbands(), "Claude PNG fixture has no alpha band")
        _require(max(check.size) > 2000, "Claude PNG fixture is not large enough")
        alpha_channel = check.getchannel("A")
        low, high = alpha_channel.getextrema()
        alpha_channel.close()
        _require(low == 0 and high == 255, "Claude PNG fixture alpha range is not 0..255")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# Real Fiona calls
# ---------------------------------------------------------------------------

def _build_cases(media, normalize_reference_upload, claude_image_source):
    """Return the case list in a fixed order.

    ``kind`` controls how the successful return value is turned into image
    bytes: ``bytes``, ``reference`` (bytes, width, height) or ``claude``
    (Anthropic image block dict).
    """
    return [
        {
            "id": "strip_jpeg_exif_gps_orientation_icc_xmp",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_jpeg_exif_gps_icc_xmp()), "jpg"
            ),
        },
        {
            "id": "strip_mpo_two_frames",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_mpo_two_frames()), "jpg"
            ),
        },
        {
            "id": "strip_png_text_iccp_palette_transparency",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_png_text_iccp_palette_transparency()), "png"
            ),
        },
        {
            "id": "strip_gif_3frame_transparency_durations_loop",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_gif_three_frames()), "gif"
            ),
        },
        {
            "id": "strip_webp_static_exif",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_webp_static_exif()), "webp"
            ),
        },
        {
            "id": "strip_webp_3frame_animation",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_webp_three_frames()), "webp"
            ),
        },
        {
            "id": "strip_png_oversized_8000x6000",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_oversized_png()), "png"
            ),
        },
        {
            "id": "strip_gif_301_frames",
            "function": "utils.media._strip_image_metadata",
            "kind": "bytes",
            "invoke": lambda: media._strip_image_metadata(
                io.BytesIO(_gif_301_frames()), "gif"
            ),
        },
        {
            "id": "reference_jpeg_exif_orientation",
            "function": "utils.reference_images.normalize_reference_upload",
            "kind": "reference",
            "invoke": lambda: normalize_reference_upload(_reference_orientation_jpeg()),
        },
        {
            "id": "reference_overlong_ratio",
            "function": "utils.reference_images.normalize_reference_upload",
            "kind": "reference",
            "invoke": lambda: normalize_reference_upload(_reference_overlong_ratio()),
        },
        {
            "id": "reference_oversized_pixels",
            "function": "utils.reference_images.normalize_reference_upload",
            "kind": "reference",
            "invoke": lambda: normalize_reference_upload(_reference_oversized_pixels()),
        },
        {
            "id": "claude_jpeg_3000x2000_resize",
            "function": "services.claude_agent._claude_image_source",
            "kind": "claude",
            "invoke": lambda: claude_image_source(_claude_large_jpeg()),
        },
        {
            "id": "claude_transparent_png_2400x1800_resize",
            "function": "services.claude_agent._claude_image_source",
            "kind": "claude",
            "invoke": lambda: claude_image_source(_claude_transparent_png()),
        },
    ]


def _inspect_image_bytes(data: bytes, case_id: str):
    """Return a stable description of an encoded image plus raw RGBA pixels."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        fmt = image.format
        size = [image.width, image.height]
        mode = image.mode
        n_frames = int(getattr(image, "n_frames", 1))
        loop = image.info.get("loop")
        durations = []
        info_keys: set[str] = set()
        for index in range(n_frames):
            image.seek(index)
            image.load()
            info_keys.update(str(key) for key in image.info.keys())
            durations.append(image.info.get("duration"))
        image.seek(0)
        image.load()
        info_keys.update(str(key) for key in image.info.keys())
        icc = image.info.get("icc_profile")
        icc = bytes(icc) if icc else None
        exif = image.getexif()
        exif_tags = sorted(int(tag) for tag in exif.keys())
        try:
            gps_tags = sorted(int(tag) for tag in exif.get_ifd(0x8825).keys())
        except (AttributeError, KeyError, TypeError, ValueError):
            gps_tags = []
        rgba = image.convert("RGBA")
        pixel_size = [rgba.width, rgba.height]
        pixel_bytes = rgba.tobytes()
        rgba.close()

    png_chunks = _png_chunk_types(data)
    container_text = bool(set(png_chunks or ()) & PNG_TEXT_CHUNKS)
    lowered_keys = {key.lower() for key in info_keys}
    xmp = (
        any(signature in data for signature in XMP_SIGNATURES)
        or "xmp" in lowered_keys
    )
    gps = bool(gps_tags) or 0x8825 in exif_tags
    text = container_text or bool({"text", "comment"} & lowered_keys)

    result = {
        "format": fmt,
        "size": size,
        "mode": mode,
        "n_frames": n_frames,
        "durations": durations,
        "loop": loop,
        "info_keys": sorted(info_keys),
        "exif_tag_count": len(exif_tags),
        "exif_tags": exif_tags,
        "icc": {
            "present": icc is not None,
            "sha256": hashlib.sha256(icc).hexdigest() if icc else None,
        },
        "residue": {
            "xmp": bool(xmp),
            "gps": bool(gps),
            "text": bool(text),
            "gps_tags": gps_tags,
        },
        "png_chunks": png_chunks,
        "pixel": {
            "size": pixel_size,
            "mode": "RGBA",
            "file": f"{case_id}.rgba",
            "sha256": hashlib.sha256(pixel_bytes).hexdigest(),
        },
    }
    return result, pixel_bytes


def _extract_payload(value, kind: str):
    if kind == "bytes":
        return value, {}
    if kind == "reference":
        payload, width, height = value
        return payload, {"returned_size": [int(width), int(height)]}
    if kind == "claude":
        payload = base64.b64decode(value["data"], validate=True)
        return payload, {
            "returned": {
                "type": value.get("type"),
                "media_type": value.get("media_type"),
            }
        }
    raise ValueError(f"unknown case kind: {kind}")


def _execute_case(case, pixels_dir: Path, http_exception_class, pillow_version: str):
    try:
        value = case["invoke"]()
    except FixtureError as exc:
        raise SystemExit(f"fixture invalid for {case['id']}: {exc}") from exc
    except http_exception_class as exc:
        return {
            "case": case["id"],
            "function": case["function"],
            "status": "error",
            "error": {
                "type": "HTTPException",
                "status_code": int(exc.status_code),
                "detail": str(exc.detail),
            },
        }
    except Exception as exc:  # noqa: BLE001 - the exception is the observation.
        return {
            "case": case["id"],
            "function": case["function"],
            "status": "error",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    payload, extra = _extract_payload(value, case["kind"])
    result, pixel_bytes = _inspect_image_bytes(payload, case["id"])
    result.update(extra)
    result["pillow_version"] = pillow_version
    (pixels_dir / f"{case['id']}.rgba").write_bytes(pixel_bytes)
    return {
        "case": case["id"],
        "function": case["function"],
        "status": "ok",
        "result": result,
    }


def _configure_uploads(args) -> str:
    uploads = args.uploads_dir or os.environ.get("FIONA_UPLOADS_DIR")
    if not uploads:
        raise SystemExit(
            "FIONA_UPLOADS_DIR is required (or pass --uploads-dir); "
            "it must point outside the repository"
        )
    os.environ["FIONA_UPLOADS_DIR"] = uploads
    os.makedirs(uploads, exist_ok=True)
    return uploads


def _prepare_import_environment() -> None:
    # Importing services.claude_agent constructs the DashScope client.  This
    # harness never performs network I/O; a placeholder keeps import safe when
    # the developer has no key in the environment.
    os.environ.setdefault("DASHSCOPE_API_KEY", "verify-only-placeholder")
    # Some shells export bracketed IPv6 entries in NO_PROXY; httpx rejects
    # those while building the import-time client.  No requests are made.
    for name in ("NO_PROXY", "no_proxy"):
        value = os.environ.get(name)
        if value and ("[" in value or "]" in value):
            os.environ[name] = value.replace("[", "").replace("]", "")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_run(args) -> int:
    _configure_uploads(args)
    _prepare_import_environment()

    from fastapi import HTTPException
    import PIL
    from utils import media
    from utils.reference_images import normalize_reference_upload
    from services.claude_agent import _claude_image_source

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixels_dir = Path(args.pixels)
    pixels_dir.mkdir(parents=True, exist_ok=True)

    cases = _build_cases(media, normalize_reference_upload, _claude_image_source)
    for case in cases:
        stale = pixels_dir / f"{case['id']}.rgba"
        if stale.exists():
            stale.unlink()

    pillow_version = str(PIL.__version__)
    records = []
    print(f"Pillow {pillow_version} / Python {sys.version.split()[0]}")
    for case in cases:
        record = _execute_case(case, pixels_dir, HTTPException, pillow_version)
        records.append(record)
        if record["status"] == "ok":
            result = record["result"]
            print(
                f"{case['id']}: ok format={result['format']} size={result['size']} "
                f"mode={result['mode']} frames={result['n_frames']}"
            )
        else:
            error = record["error"]
            summary = (
                f"HTTP {error['status_code']} {error['detail']}"
                if error["type"] == "HTTPException"
                else f"{error['type']}: {error['message']}"
            )
            print(f"{case['id']}: error {summary}")

    document = {
        "pillow_version": pillow_version,
        "python_version": sys.version.split()[0],
        "case_count": len(records),
        "cases": records,
    }
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(records)} cases to {output_path}")
    print(f"pixels written to {pixels_dir}")
    return 0


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _compare_pixels(case_id: str, before: dict, after: dict,
                    before_pixels: Path, after_pixels: Path):
    from PIL import Image, ImageChops, ImageStat

    problems: list[str] = []
    before_meta = before.get("pixel") or {}
    after_meta = after.get("pixel") or {}
    if not before_meta or not after_meta:
        return [f"{case_id}: pixel metadata missing"], None
    before_path = before_pixels / str(before_meta.get("file"))
    after_path = after_pixels / str(after_meta.get("file"))
    if not before_path.is_file() or not after_path.is_file():
        return [f"{case_id}: pixel file missing"], None
    before_size = tuple(int(value) for value in before_meta.get("size") or [])
    after_size = tuple(int(value) for value in after_meta.get("size") or [])
    if before_size != after_size:
        return [f"{case_id}: pixel size differs {before_size} != {after_size}"], None
    expected = before_size[0] * before_size[1] * 4
    before_raw = before_path.read_bytes()
    after_raw = after_path.read_bytes()
    if len(before_raw) != expected or len(after_raw) != expected:
        return [f"{case_id}: raw pixel byte length does not match pixel size"], None
    before_image = Image.frombytes("RGBA", before_size, before_raw)
    after_image = Image.frombytes("RGBA", after_size, after_raw)
    difference = ImageChops.difference(before_image, after_image)
    statistics = ImageStat.Stat(difference)
    raw_means = [float(value) for value in statistics.mean]
    means = [round(value, 6) for value in raw_means]
    extrema = [int(band[1]) for band in statistics.extrema]
    before_image.close()
    after_image.close()
    difference.close()
    if any(value > 1.0 for value in raw_means):
        problems.append(f"{case_id}: per-channel mean abs diff > 1.0: {means}")
    return problems, {
        "mean_abs_diff": means,
        "max_abs_diff": extrema,
        "sha_equal": before_meta.get("sha256") == after_meta.get("sha256"),
    }


def _compare_ok_case(case_id: str, before: dict, after: dict,
                     before_pixels: Path, after_pixels: Path):
    problems: list[str] = []
    notes: list[dict] = []
    for field in _STRIP_FIELDS:
        if before.get(field) != after.get(field):
            problems.append(
                f"{case_id}: {field} differs: {before.get(field)!r} != {after.get(field)!r}"
            )
    before_returned = before.get("returned")
    after_returned = after.get("returned")
    if before_returned is not None or after_returned is not None:
        before_returned = before_returned or {}
        after_returned = after_returned or {}
        for field in ("type", "media_type"):
            if before_returned.get(field) != after_returned.get(field):
                problems.append(
                    f"{case_id}: returned {field} differs: "
                    f"{before_returned.get(field)!r} != {after_returned.get(field)!r}"
                )
    if "returned_size" in before or "returned_size" in after:
        if before.get("returned_size") != after.get("returned_size"):
            problems.append(
                f"{case_id}: returned_size differs: "
                f"{before.get('returned_size')!r} != {after.get('returned_size')!r}"
            )
    if before.get("icc") != after.get("icc"):
        problems.append(
            f"{case_id}: ICC differs: {before.get('icc')!r} != {after.get('icc')!r}"
        )
    for key in ("xmp", "gps", "text"):
        before_value = (before.get("residue") or {}).get(key)
        after_value = (after.get("residue") or {}).get(key)
        if before_value or after_value:
            problems.append(
                f"{case_id}: metadata residue {key} must be absent, got "
                f"before={before_value!r} after={after_value!r}"
            )
    before_keys = set(before.get("info_keys") or [])
    after_keys = set(after.get("info_keys") or [])
    if before_keys != after_keys:
        notes.append({
            "kind": "info_keys",
            "added": sorted(after_keys - before_keys),
            "removed": sorted(before_keys - after_keys),
        })
    if before.get("exif_tag_count") != after.get("exif_tag_count"):
        notes.append({
            "kind": "exif_tag_count",
            "before": before.get("exif_tag_count"),
            "after": after.get("exif_tag_count"),
        })
    if before.get("exif_tags") != after.get("exif_tags"):
        before_tags = set(before.get("exif_tags") or [])
        after_tags = set(after.get("exif_tags") or [])
        notes.append({
            "kind": "exif_tags",
            "added": sorted(after_tags - before_tags),
            "removed": sorted(before_tags - after_tags),
        })
    if before.get("png_chunks") != after.get("png_chunks"):
        notes.append({
            "kind": "png_chunks",
            "before": before.get("png_chunks"),
            "after": after.get("png_chunks"),
        })
    pixel_problems, pixel_comparison = _compare_pixels(
        case_id, before, after, before_pixels, after_pixels
    )
    problems.extend(pixel_problems)
    return problems, notes, pixel_comparison


def cmd_compare(args) -> int:
    before_document = _load_json(args.before)
    after_document = _load_json(args.after)
    before_pixels = Path(args.before_pixels)
    after_pixels = Path(args.after_pixels)
    before_cases = {case["case"]: case for case in before_document.get("cases", [])}
    after_cases = {case["case"]: case for case in after_document.get("cases", [])}

    problems: list[str] = []
    case_results: list[dict] = []
    if set(before_cases) != set(after_cases):
        problems.append(
            "case set differs: "
            f"only-before={sorted(set(before_cases) - set(after_cases))} "
            f"only-after={sorted(set(after_cases) - set(before_cases))}"
        )

    for case_id in sorted(set(before_cases) & set(after_cases)):
        before = before_cases[case_id]
        after = after_cases[case_id]
        case_problems: list[str] = []
        notes: list[dict] = []
        pixel_comparison = None
        if before.get("status") != after.get("status"):
            case_problems.append(
                f"{case_id}: status differs: {before.get('status')} != {after.get('status')}"
            )
        elif before.get("status") == "error":
            before_error = before.get("error") or {}
            after_error = after.get("error") or {}
            if before_error.get("type") != after_error.get("type"):
                case_problems.append(
                    f"{case_id}: exception type differs: "
                    f"{before_error.get('type')!r} != {after_error.get('type')!r}"
                )
            if before_error.get("status_code") != after_error.get("status_code"):
                case_problems.append(
                    f"{case_id}: exception status differs: "
                    f"{before_error.get('status_code')!r} != {after_error.get('status_code')!r}"
                )
            before_text = before_error.get("detail", before_error.get("message"))
            after_text = after_error.get("detail", after_error.get("message"))
            if before_text != after_text:
                notes.append({
                    "kind": "exception_text",
                    "before": before_text,
                    "after": after_text,
                })
        else:
            case_problems, notes, pixel_comparison = _compare_ok_case(
                case_id, before.get("result") or {}, after.get("result") or {},
                before_pixels, after_pixels
            )
        problems.extend(case_problems)
        case_results.append({
            "case": case_id,
            "verdict": "match" if not case_problems else "mismatch",
            "problems": case_problems,
            "allowed_differences": notes,
            "pixel": pixel_comparison,
        })

    document = {
        "pillow_before": before_document.get("pillow_version"),
        "pillow_after": after_document.get("pillow_version"),
        "version_changed": before_document.get("pillow_version") != after_document.get("pillow_version"),
        "case_count": len(case_results),
        "cases": case_results,
        "problems": problems,
        "pass": not problems,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Pillow before={document['pillow_before']} after={document['pillow_after']} "
        f"cases={document['case_count']}"
    )
    for result in case_results:
        print(f"{result['case']}: {result['verdict']}")
        for note in result["allowed_differences"]:
            print(f"  allowed difference: {note}")
    if problems:
        print("RESULT: FAIL")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("RESULT: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run every case with the current interpreter")
    run_parser.add_argument("--output", required=True, help="JSON result path")
    run_parser.add_argument("--pixels", required=True, help="directory for raw RGBA files")
    run_parser.add_argument(
        "--uploads-dir",
        default=None,
        help="Fiona upload directory (defaults to $FIONA_UPLOADS_DIR)",
    )
    run_parser.set_defaults(func=cmd_run)

    compare_parser = subparsers.add_parser("compare", help="compare two run outputs")
    compare_parser.add_argument("--before", required=True, help="JSON from Pillow 12.3.0")
    compare_parser.add_argument("--after", required=True, help="JSON from Pillow 13.0.0")
    compare_parser.add_argument("--before-pixels", required=True, help="pixel dir for --before")
    compare_parser.add_argument("--after-pixels", required=True, help="pixel dir for --after")
    compare_parser.add_argument("--output", required=True, help="JSON comparison path")
    compare_parser.set_defaults(func=cmd_compare)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
