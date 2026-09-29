# -*- coding: utf-8 -*-
import pytest


def _ftyp(brand: bytes) -> bytes:
    return b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00" + brand


@pytest.mark.parametrize("brand", [
    b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif", b"avis",
])
def test_image_bmff_brands_are_not_videos(brand):
    from utils.media import _sniff_video_ext

    assert _sniff_video_ext(_ftyp(brand)) is None


@pytest.mark.parametrize("brand", [
    b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42",
    b"avc1", b"dash", b"M4V ", b"3gp4", b"3g2a",
])
def test_known_video_bmff_brands_are_accepted(brand):
    from utils.media import _sniff_video_ext

    assert _sniff_video_ext(_ftyp(brand)) == "mp4"


def test_quicktime_brand_is_mov_and_unknown_brand_is_rejected():
    from utils.media import _sniff_video_ext

    assert _sniff_video_ext(_ftyp(b"qt  ")) == "mov"
    assert _sniff_video_ext(_ftyp(b"nope")) is None


def test_image_compatible_brand_overrides_video_major_brand():
    from utils.media import _sniff_video_ext

    mixed = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00avif"
    assert _sniff_video_ext(mixed) is None


@pytest.mark.parametrize("brand", [b"heic", b"avif"])
def test_plaza_rejects_image_bmff_with_conversion_hint(
    client, dev_headers, tmp_path, monkeypatch, brand,
):
    from utils import media

    upload_dir = tmp_path / "plaza-brands"
    upload_dir.mkdir()
    monkeypatch.setattr(media, "UPLOADS_DIR", str(upload_dir))
    response = client.post(
        "/plaza/post",
        headers=dev_headers,
        data={"caption": "", "tags": "[]"},
        files={"file": ("photo.heic", _ftyp(brand), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "JPG 或 PNG" in response.json()["detail"]
    assert list(upload_dir.iterdir()) == []
