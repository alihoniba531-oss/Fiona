"""Positive metadata samples and both upload paths, with real offline remux QA."""
import asyncio
import base64
import binascii
import io
import json
from pathlib import Path
import random
import shutil
import stat
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import anyio
from fastapi import HTTPException, UploadFile
from PIL import Image, PngImagePlugin
import pytest

from utils import media


ICC = b"test-preserved-icc-profile"
PRIVATE_ARTIST = b"PRIVATE_ARTIST_69321"
PRIVATE_GPS = b"PRIVATE_GPS_69321"
PRIVATE_XMP = b"PRIVATE_XMP_69321"
PRIVATE_TEXT = b"PRIVATE_TEXT_69321"
PRIVATE_COMMENT = b"PRIVATE_COMMENT_69321"
PRIVATE_DATE = b"2099:01:02 03:04:05"
PRIVATE_IPTC = b"PRIVATE_IPTC_69321"


def _exif():
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = PRIVATE_ARTIST.decode()
    exif[306] = PRIVATE_DATE.decode()
    exif[34853] = {1: "N", 2: (12.0, 34.0, 56.0), 3: "E", 4: (123.0, 45.0, 6.0), 27: PRIVATE_GPS}
    return exif


def _sample(kind):
    output = io.BytesIO()
    first = Image.new("RGB", (8, 4), "red")
    frames = [Image.new("RGB", (8, 4), color) for color in ("blue", "green")]
    if kind == "jpg":
        first.save(output, "JPEG", exif=_exif(), xmp=PRIVATE_XMP, icc_profile=ICC)
        data = output.getvalue()
        # APP13 demonstrates that opaque IPTC-like payloads also cannot survive.
        payload = b"Photoshop 3.0\x00" + PRIVATE_IPTC
        data = data[:2] + b"\xff\xed" + (len(payload) + 2).to_bytes(2, "big") + payload + data[2:]
        markers = (PRIVATE_ARTIST, PRIVATE_GPS, PRIVATE_XMP, PRIVATE_DATE, PRIVATE_IPTC)
    elif kind == "png":
        text = PngImagePlugin.PngInfo()
        text.add_text("private", PRIVATE_TEXT.decode())
        text.add_itxt("XML:com.adobe.xmp", PRIVATE_XMP.decode())
        first.save(output, "PNG", pnginfo=text, icc_profile=ICC, exif=_exif())
        data = output.getvalue()
        markers = (PRIVATE_ARTIST, PRIVATE_GPS, PRIVATE_DATE, PRIVATE_TEXT, PRIVATE_XMP)
    elif kind == "gif":
        first.save(output, "GIF", save_all=True, append_images=frames, duration=[100, 200, 300], loop=2, comment=PRIVATE_COMMENT)
        data = output.getvalue()
        markers = (PRIVATE_COMMENT,)
    elif kind == "webp":
        first.save(output, "WEBP", save_all=True, append_images=frames, duration=[100, 200, 300], loop=2,
                   exif=_exif(), xmp=PRIVATE_XMP, icc_profile=ICC)
        data = output.getvalue()
        markers = (PRIVATE_ARTIST, PRIVATE_GPS, PRIVATE_DATE, PRIVATE_XMP)
    elif kind == "mpo":
        first.save(output, "MPO", save_all=True, append_images=frames[:1], exif=_exif(), icc_profile=ICC)
        data = output.getvalue()
        markers = (PRIVATE_ARTIST, PRIVATE_GPS, PRIVATE_DATE)
    else:
        raise AssertionError(kind)
    # Positive controls: the old HEAD wrote these bytes verbatim (and rejected MPO).
    for marker in markers:
        assert marker in data
    return data, markers


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "UPLOADS_DIR", str(tmp_path))
    return tmp_path


def _upload(data, route):
    if route == "plaza":
        path, kind = asyncio.run(media._save_plaza_upload(UploadFile(io.BytesIO(data), filename="photo")))
        assert kind == "image"
        uri = None
    else:
        path, uri = media._save_uploaded_image(base64.b64encode(data).decode())
    saved = (Path(media.UPLOADS_DIR) / Path(path).name).read_bytes()
    if uri is not None:
        assert base64.b64decode(uri.split(",", 1)[1]) == saved
    return saved, path, uri


def _frame_durations(data):
    with Image.open(io.BytesIO(data)) as image:
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            image.load()
            durations.append(image.info["duration"])
        return durations


@pytest.mark.parametrize("route", ["plaza", "chat"])
@pytest.mark.parametrize("kind", ["jpg", "png", "gif", "webp", "mpo"])
def test_images_remove_private_metadata_preserve_format_icc_and_animation(uploads, kind, route):
    source, markers = _sample(kind)
    saved, path, uri = _upload(source, route)
    for marker in markers:
        assert marker not in saved
        if uri:
            assert marker not in base64.b64decode(uri.split(",", 1)[1])
    output_ext = "jpg" if kind == "mpo" else kind
    assert path.endswith(f".{output_ext}")
    with Image.open(io.BytesIO(saved)) as image:
        assert image.format == media._PIL_FORMAT_BY_EXT[output_ext]
        assert not image.getexif()
        assert not ({"exif", "xmp", "comment"} & image.info.keys())
        if kind in {"jpg", "png", "webp", "mpo"}:
            assert image.size == (4, 8)
            assert image.info["icc_profile"] == ICC
        if kind == "mpo":
            assert getattr(image, "n_frames", 1) == 1
            red, green, blue = image.convert("RGB").getpixel((0, 0))
            assert red > 240 and green < 15 and blue < 15
        if kind in {"gif", "webp"}:
            assert image.n_frames == 3
            assert image.info["loop"] == 2
    if kind in {"gif", "webp"}:
        assert _frame_durations(saved) == _frame_durations(source)
    assert all(not path.name.startswith(".") for path in uploads.iterdir())


@pytest.mark.parametrize("route", ["plaza", "chat"])
def test_la_png_keeps_png_data_uri(uploads, route):
    output = io.BytesIO()
    Image.new("LA", (1, 1), (0, 255)).save(output, "PNG")
    saved, path, uri = _upload(output.getvalue(), route)
    assert path.endswith(".png")
    with Image.open(io.BytesIO(saved)) as image:
        assert image.mode == "LA"
    if uri:
        assert uri.startswith("data:image/png;base64,")


@pytest.mark.parametrize("route", ["plaza", "chat"])
@pytest.mark.parametrize("kind", ["GIF", "WEBP"])
def test_too_many_animation_frames_rejected(uploads, route, kind):
    output = io.BytesIO()
    frames = [Image.new("RGB", (1, 1), (index % 256, index // 256, 0)) for index in range(301)]
    frames[0].save(output, kind, save_all=True, append_images=frames[1:], duration=100, lossless=True)
    with Image.open(io.BytesIO(output.getvalue())) as image:
        assert image.n_frames == 301
    with pytest.raises(HTTPException) as error:
        _upload(output.getvalue(), route)
    assert error.value.status_code == 400
    assert error.value.detail == "动图帧数过多，请压缩后再发"
    assert list(uploads.iterdir()) == []


@pytest.mark.parametrize("route", ["plaza", "chat"])
def test_animation_total_pixel_budget_rejected(uploads, route, monkeypatch):
    data, _ = _sample("gif")
    monkeypatch.setattr(media, "_MAX_ANIMATION_PIXELS", 95)
    with pytest.raises(HTTPException, match="动图帧数过多"):
        _upload(data, route)
    assert list(uploads.iterdir()) == []


@pytest.mark.parametrize("route", ["plaza", "chat"])
def test_gif_without_loop_keeps_play_once(uploads, route):
    output = io.BytesIO()
    first = Image.new("RGB", (4, 4), "red")
    first.save(output, "GIF", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")], duration=[100, 200])
    saved, _, _ = _upload(output.getvalue(), route)
    with Image.open(io.BytesIO(saved)) as image:
        assert "loop" not in image.info
        assert image.n_frames == 2


@pytest.mark.parametrize("route", ["plaza", "chat"])
@pytest.mark.parametrize("disposal", [[2, 2, 2], [1, 2, 3], [1, 3, 1]])
def test_transparent_gif_preserves_composed_frames_with_mixed_disposal(uploads, route, disposal):
    frames = []
    for box, color in [((0, 0, 4, 4), (255, 0, 0, 255)),
                       ((4, 0, 8, 4), (0, 0, 255, 255)),
                       ((2, 4, 6, 8), (0, 128, 0, 255))]:
        frame = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        frame.paste(color, box)
        frames.append(frame)
    output = io.BytesIO()
    frames[0].save(output, "GIF", save_all=True, append_images=frames[1:],
                   duration=[100, 200, 300], loop=2, disposal=disposal, comment=PRIVATE_COMMENT)
    source = output.getvalue()

    def rgba_frames(data):
        result = []
        with Image.open(io.BytesIO(data)) as image:
            for index in range(image.n_frames):
                image.seek(index)
                image.load()
                result.append(image.convert("RGBA").tobytes())
        return result

    saved, _, _ = _upload(source, route)
    assert rgba_frames(saved) == rgba_frames(source)
    assert len(saved) <= 3 * len(source)
    assert _frame_durations(saved) == _frame_durations(source)
    assert PRIVATE_COMMENT in source and PRIVATE_COMMENT not in saved


@pytest.mark.parametrize("route", ["plaza", "chat"])
def test_opaque_gif_with_unused_transparency_preserves_frame_differences(uploads, route):
    size = (160, 160)
    rng = random.Random(69321)
    background = Image.frombytes("P", size, bytes(rng.randrange(32) for _ in range(size[0] * size[1])))
    palette = [channel for red in (0, 85, 170, 255)
               for green in (0, 85, 170, 255) for blue in (0, 255)
               for channel in (red, green, blue)]
    palette.extend([0, 0, 128])
    palette.extend([0] * (768 - len(palette)))
    background.putpalette(palette)
    frames = []
    for index in range(12):
        frame = background.copy()
        left = 8 + index * 10
        frame.paste(32, (left, 72, left + 8, 80))
        frames.append(frame)
    output = io.BytesIO()
    frames[0].save(output, "GIF", save_all=True, append_images=frames[1:],
                   duration=100, loop=2, disposal=1, transparency=255, optimize=False)
    source = output.getvalue()
    expected_frames = []
    with Image.open(io.BytesIO(source)) as image:
        # The declared index is unused: metadata alone must not disable differences.
        assert image.info["transparency"] == 255
        assert image.n_frames == 12
        for index in range(image.n_frames):
            image.seek(index)
            rgba = image.convert("RGBA")
            assert rgba.getextrema()[3] == (255, 255)
            expected_frames.append(rgba.tobytes())

    saved, _, _ = _upload(source, route)
    assert len(saved) <= 2 * len(source), (len(source), len(saved))
    with Image.open(io.BytesIO(saved)) as image:
        assert image.n_frames == len(expected_frames)
        for index, expected in enumerate(expected_frames):
            image.seek(index)
            assert image.convert("RGBA").tobytes() == expected


def _video_stub(ext):
    if ext == "webm":
        return b"\x1a\x45\xdf\xa3private-video"
    brand = b"qt  " if ext == "mov" else b"3gp4" if ext == "3gp" else b"isom"
    return b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00" + brand


@pytest.mark.parametrize("ext", ["mp4", "3gp", "mov", "webm"])
def test_video_argv_safe_stream_maps_container_timeout_and_atomic_output(uploads, monkeypatch, ext):
    calls = []
    replace = media.os.replace

    def remux(argv, **kwargs):
        assert threading.current_thread() is not threading.main_thread()
        assert kwargs == {"check": True, "capture_output": True, "timeout": 30}
        assert Path(argv[-1]).parent == uploads
        assert Path(argv[-1]).name.startswith(".")
        assert all(path.name.startswith(".") for path in uploads.iterdir())
        calls.append(argv)
        Path(argv[-1]).write_bytes(b"sanitized-video")

    def atomic(source, destination):
        assert Path(source).parent == Path(destination).parent == uploads
        assert Path(source).name.startswith(".")
        return replace(source, destination)

    monkeypatch.setattr(media.shutil, "which", lambda _: "ffmpeg-test")
    monkeypatch.setattr(media.subprocess, "run", remux)
    monkeypatch.setattr(media.os, "replace", atomic)
    path, kind = asyncio.run(media._save_plaza_upload(UploadFile(io.BytesIO(_video_stub(ext)))))
    argv = calls[0]
    for pair in (("-map", "0:V:0"), ("-map", "0:a:0?"), ("-c", "copy"),
                 ("-map_metadata", "-1"), ("-map_metadata:s", "-1"), ("-map_chapters", "-1"), ("-fflags", "+bitexact")):
        assert any(tuple(argv[index:index + 2]) == pair for index in range(len(argv) - 1))
    assert {"-nostdin", "-dn", "-sn"} <= set(argv)
    expected = "mp4" if ext == "3gp" else ext
    assert argv[-3:-1] == ["-f", expected]
    if expected == "mp4":
        assert argv[argv.index("-movflags") + 1] == "+faststart"
    assert kind == "video"
    assert path.endswith(f".{expected}")
    assert [item.name for item in uploads.iterdir()] == [Path(path).name]


@pytest.mark.parametrize("failure", ["missing", "exit", "timeout", "empty"])
def test_video_fail_closed_and_clean_all_temporaries(uploads, monkeypatch, failure):
    monkeypatch.setattr(media.shutil, "which", lambda _: None if failure == "missing" else "ffmpeg-test")

    def failed(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"" if failure == "empty" else b"half-written")
        if failure == "exit":
            raise subprocess.CalledProcessError(1, argv)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(media.subprocess, "run", failed)
    with pytest.raises(HTTPException) as error:
        asyncio.run(media._save_plaza_upload(UploadFile(io.BytesIO(_video_stub("mp4")))))
    assert error.value.status_code == (503 if failure == "missing" else 400)
    assert error.value.detail == ("服务器暂时无法处理视频，请改发图片" if failure == "missing" else "视频处理失败，请转成 MP4 后再发")
    assert list(uploads.iterdir()) == []


def test_cancelled_upload_waits_for_worker_then_removes_partial_files(uploads, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(media.shutil, "which", lambda _: "ffmpeg-test")

    def slow(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"half-written")
        started.set()
        assert release.wait(5)
        Path(argv[-1]).write_bytes(b"finished")

    monkeypatch.setattr(media.subprocess, "run", slow)

    async def scenario():
        task = asyncio.create_task(media._save_plaza_upload(UploadFile(io.BytesIO(_video_stub("mp4")))))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # Repeated cancellation cannot race the worker's cleanup.
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert list(uploads.iterdir()) == []


def test_cancelled_upload_read_removes_partially_written_input(uploads):
    data, _ = _sample("png")

    class CancelDuringRead:
        count = 0

        async def read(self, amount):
            self.count += 1
            if self.count == 1:
                return data
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(media._save_plaza_upload(CancelDuringRead()))
    assert list(uploads.iterdir()) == []


def test_plaza_image_reencoding_runs_off_event_loop(uploads, monkeypatch):
    data, _ = _sample("png")
    strip = media._strip_image_metadata

    def checked(*args):
        assert threading.current_thread() is not threading.main_thread()
        return strip(*args)

    monkeypatch.setattr(media, "_strip_image_metadata", checked)
    _upload(data, "plaza")


@pytest.mark.parametrize("route", ["plaza", "chat"])
@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
def test_image_atomic_replace_failure_removes_temporaries(uploads, monkeypatch, route, failure):
    data, _ = _sample("png")

    def fail(source, destination):
        Path(destination).write_bytes(b"half-written")
        raise failure("do not print private details")

    monkeypatch.setattr(media.os, "replace", fail)
    with pytest.raises((OSError, HTTPException, asyncio.CancelledError)):
        _upload(data, route)
    assert list(uploads.iterdir()) == []


def test_two_process_wide_reencoding_slots(uploads, monkeypatch):
    lock = threading.Lock()
    active = maximum = 0
    first_two = threading.Event()
    release = threading.Event()
    image_open = media.Image.open

    def observed(*args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                first_two.set()
        assert release.wait(5)
        result = image_open(*args, **kwargs)
        with lock:
            active -= 1
        return result

    data, _ = _sample("png")
    monkeypatch.setattr(media.Image, "open", observed)

    async def scenario():
        tasks = [asyncio.create_task(asyncio.to_thread(media._save_uploaded_image, base64.b64encode(data).decode())) for _ in range(3)]
        assert await asyncio.to_thread(first_two.wait, 5)
        release.set()
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    assert maximum == 2


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="没有 ffmpeg，无法运行离线视频集成测试")
def test_real_ffmpeg_remux_removes_tags_preserves_rotation_and_video(uploads, tmp_path):
    original = tmp_path / "original.mp4"
    rotated = tmp_path / "rotated.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-nostdin", "-y", "-f", "lavfi", "-i", "color=c=red:s=16x16:d=0.2",
                    "-c:v", "mpeg4", "-metadata", "location=+12.3456+123.4567/", "-metadata", "comment=PRIVATE_VIDEO_COMMENT",
                    "-metadata", "creation_time=2099-01-02T03:04:05Z", str(original)], check=True, capture_output=True, timeout=30)
    subprocess.run([shutil.which("ffmpeg"), "-nostdin", "-y", "-display_rotation:v:0", "90", "-i", str(original), "-c", "copy",
                    "-metadata:s:v:0", "title=PRIVATE_STREAM_TITLE", str(rotated)], check=True, capture_output=True, timeout=30)

    def probe(path):
        result = subprocess.run([shutil.which("ffprobe"), "-v", "quiet", "-show_format", "-show_streams", "-of", "json", str(path)],
                                check=True, capture_output=True, timeout=30)
        return json.loads(result.stdout)

    before = probe(rotated)
    assert "location" in before["format"]["tags"]
    assert any(side.get("rotation") == 90 for side in before["streams"][0]["side_data_list"])
    path, kind = asyncio.run(media._save_plaza_upload(UploadFile(io.BytesIO(rotated.read_bytes()))))
    after = probe(uploads / Path(path).name)
    assert kind == "video"
    assert after["streams"][0]["codec_type"] == "video"
    assert after["streams"][0]["codec_name"] == before["streams"][0]["codec_name"]
    assert any(side.get("rotation") == 90 for side in after["streams"][0]["side_data_list"])
    tags = [after["format"].get("tags", {}), *(stream.get("tags", {}) for stream in after["streams"])]
    assert not any({"location", "location-eng", "creation_time", "comment", "title"} & item.keys() for item in tags)
    assert "PRIVATE_" not in json.dumps(tags)


def test_cleanup_script_default_dry_run_scope_atomic_apply_and_failures(uploads, monkeypatch, capsys):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    data, markers = _sample("jpg")
    eligible = [uploads / "plaza_old.jpg", uploads / ("a" * 32 + ".jpg")]
    for path in eligible:
        path.write_bytes(data)
    skipped = [uploads / "generated_old.jpg", uploads / "reference_old.jpg", uploads / ".plaza_hidden.jpg", uploads / "other.jpg"]
    for path in skipped:
        path.write_bytes(data)
    assert script.main([]) == 0
    stdout = capsys.readouterr().out
    assert "文件数：2" in stdout and "类型 image/jpg：2" in stdout
    assert all(path.read_bytes() == data for path in eligible + skipped)
    broken = uploads / "plaza_broken.jpg"
    broken.write_bytes(b"\xff\xd8\xffbroken")
    assert script.main(["--apply"]) == 1
    stdout = capsys.readouterr().out
    assert "已处理：2；失败：1" in stdout
    assert "PRIVATE_" not in stdout
    assert all(marker not in path.read_bytes() for path in eligible for marker in markers)
    assert all(path.read_bytes() == data for path in skipped)
    assert broken.read_bytes() == b"\xff\xd8\xffbroken"
    assert not any(path.name.startswith(".upload_") for path in uploads.iterdir())


def test_cleanup_script_env_file_matches_admin_precedence(uploads, tmp_path, monkeypatch, capsys):
    from scripts import strip_upload_metadata as script

    configured = tmp_path / "configured"
    configured.mkdir()
    config = tmp_path / "configuration.txt"
    config.write_text(f"FIONA_UPLOADS_DIR={configured}\n")
    monkeypatch.delenv("FIONA_UPLOADS_DIR", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    assert script.main(["--env-file", str(config), "--dry-run"]) == 0
    assert media.UPLOADS_DIR == str(configured)
    assert "文件数：0" in capsys.readouterr().out
    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    assert script.configure_uploads(config) == uploads


@pytest.mark.parametrize("missing", [False, True])
def test_cleanup_script_video_reuses_remux_and_preserves_failed_original(uploads, monkeypatch, capsys, missing):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    monkeypatch.setattr(media.shutil, "which", lambda _: None if missing else "ffmpeg-test")
    original = _video_stub("3gp")
    source = uploads / "plaza_old.3gp"
    source.write_bytes(original)

    def remux(argv, **kwargs):
        assert argv[-3:-1] == ["-f", "mp4"]
        assert argv[argv.index("-map") + 1] == "0:V:0"
        Path(argv[-1]).write_bytes(b"metadata-free-mp4")

    monkeypatch.setattr(media.subprocess, "run", remux)
    assert script.main(["--apply"]) == (1 if missing else 0)
    stdout = capsys.readouterr().out
    assert "类型 video/mp4：1" in stdout
    assert ("已处理：0；失败：1" if missing else "已处理：1；失败：0") in stdout
    assert source.read_bytes() == (original if missing else b"metadata-free-mp4")
    assert list(uploads.iterdir()) == [source]


@pytest.mark.parametrize("route", ["plaza", "chat"])
def test_opaque_gif_small_motion_keeps_frame_differences_and_size(uploads, route):
    rng = random.Random(69321)
    background = Image.frombytes("P", (128, 128), bytes(rng.randrange(64) for _ in range(128 * 128)))
    background.putpalette([value for index in range(256) for value in (index, (index * 7) % 256, (index * 13) % 256)])
    frames = []
    for index in range(100):
        frame = background.copy()
        frame.paste(63, (index, 20, index + 5, 25))
        frames.append(frame)
    output = io.BytesIO()
    frames[0].save(output, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=2,
                   comment=PRIVATE_COMMENT)
    source = output.getvalue()
    saved, _, _ = _upload(source, route)
    assert len(saved) <= 2 * len(source)
    assert _frame_durations(saved) == _frame_durations(source)
    with Image.open(io.BytesIO(source)) as before, Image.open(io.BytesIO(saved)) as after:
        for index in range(100):
            before.seek(index)
            after.seek(index)
            assert before.convert("RGBA").tobytes() == after.convert("RGBA").tobytes()


@pytest.mark.parametrize("route", ["plaza", "chat"])
@pytest.mark.parametrize("mode,key,opaque", [("RGB", (1, 2, 3), (10, 20, 30)), ("L", 7, 123)])
def test_png_trns_color_key_keeps_transparency(uploads, route, mode, key, opaque):
    source = Image.new(mode, (2, 1), key)
    source.putpixel((1, 0), opaque)
    output = io.BytesIO()
    source.save(output, "PNG", transparency=key)
    saved, _, _ = _upload(output.getvalue(), route)
    with Image.open(io.BytesIO(saved)) as image:
        assert image.mode == ("RGBA" if mode == "RGB" else "LA")
        rgba = image.convert("RGBA")
        assert [rgba.getpixel((index, 0)) for index in range(2)] == ([(*key, 0), (*opaque, 255)] if mode == "RGB" else
                                                                  [(key, key, key, 0), (opaque, opaque, opaque, 255)])


@pytest.mark.parametrize("route", ["plaza", "chat"])
@pytest.mark.parametrize("kind", ["jpg", "webp"])
def test_jpeg_and_webp_explicit_quality_90(uploads, monkeypatch, route, kind):
    source, _ = _sample(kind)
    calls = []
    save = media.Image.Image.save

    def observed(image, fp, format=None, **options):
        calls.append((format, options.get("quality")))
        return save(image, fp, format=format, **options)

    monkeypatch.setattr(media.Image.Image, "save", observed)
    _upload(source, route)
    assert (media._PIL_FORMAT_BY_EXT[kind], 90) in calls


def test_plaza_queue_does_not_occupy_default_executor(uploads, monkeypatch):
    source, _ = _sample("png")
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    count = 0

    def blocked(source_path, destination, ext, media_type):
        nonlocal count
        with lock:
            count += 1
            if count == 2:
                started.set()
        assert release.wait(5)
        Path(destination).write_bytes(b"clean")

    monkeypatch.setattr(media, "_process_upload", blocked)

    async def scenario():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=3))
        tasks = [asyncio.create_task(media._save_plaza_upload(UploadFile(io.BytesIO(source)))) for _ in range(8)]
        assert await asyncio.to_thread(started.wait, 5)
        try:
            assert await asyncio.wait_for(asyncio.to_thread(lambda: "available"), 0.5) == "available"
            assert count == 2
        finally:
            release.set()
            await asyncio.gather(*tasks)

    asyncio.run(scenario())


def test_chat_reencoding_slot_timeout_is_503_and_leaves_no_files(uploads, monkeypatch):
    source, _ = _sample("png")
    monkeypatch.setattr(media, "_CHAT_REENCODE_TIMEOUT", 0.01)
    media._REENCODE_SLOTS.acquire()
    media._REENCODE_SLOTS.acquire()
    try:
        with pytest.raises(HTTPException) as error:
            _upload(source, "chat")
        assert error.value.status_code == 503
        assert error.value.detail == "服务器繁忙，请稍后再发图片"
        assert list(uploads.iterdir()) == []
    finally:
        media._REENCODE_SLOTS.release()
        media._REENCODE_SLOTS.release()


def test_anyio_cancelled_plaza_upload_waits_once_without_busy_loop(uploads, monkeypatch):
    source, _ = _sample("png")
    started = threading.Event()
    shields = []
    shield = asyncio.shield

    def observed(task):
        shields.append(task)
        return shield(task)

    def slow(source_path, destination, ext, media_type):
        started.set()
        threading.Event().wait(0.15)
        Path(destination).write_bytes(b"finished")

    monkeypatch.setattr(media, "_process_upload", slow)
    monkeypatch.setattr(media.asyncio, "shield", observed)

    async def scenario():
        async with anyio.create_task_group() as group:
            group.start_soon(media._save_plaza_upload, UploadFile(io.BytesIO(source)))
            assert await asyncio.to_thread(started.wait, 5)
            group.cancel_scope.cancel()

    anyio.run(scenario)
    assert len(shields) == 2
    assert list(uploads.iterdir()) == []


def test_chat_cancelled_during_worker_removes_final_upload(uploads, monkeypatch):
    from services import chat_service as chat

    source, _ = _sample("png")
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    save = media._save_uploaded_image

    def slow(data):
        started.set()
        assert release.wait(5)
        result = save(data)
        finished.set()
        return result

    async def resolved(*args):
        return {"conversation": {"id": "cancelled-chat"}, "agent": {}}

    async def history(*args, **kwargs):
        return []

    async def count(*args, **kwargs):
        return 0

    monkeypatch.setattr(chat, "resolve_chat_conversation", resolved)
    monkeypatch.setattr(chat, "get_messages", history)
    monkeypatch.setattr(chat, "count_messages", count)
    monkeypatch.setattr(chat, "_save_uploaded_image", slow)

    async def scenario():
        task = asyncio.create_task(chat.build_context(SimpleNamespace(image_base64=base64.b64encode(source).decode(), message=""), "user"))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        # Let the upload task completion callback run on this event loop.
        for _ in range(3):
            await asyncio.sleep(0)
        assert list(uploads.iterdir()) == []

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["jpg", "png", "gif", "webp"])
def test_cleanup_skips_clean_image_without_reencoding(uploads, monkeypatch, capsys, kind):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    source, _ = _sample(kind)
    cleaned, _, _ = _upload(source, "chat")
    path = uploads / f"plaza_clean.{kind}"
    path.write_bytes(cleaned)
    initial = path.stat().st_mtime_ns

    def unexpected(*args):
        raise AssertionError("a clean image must not be reencoded")

    monkeypatch.setattr(media, "_process_upload", unexpected)
    assert script.main(["--apply"]) == 0
    assert "已处理：0；失败：0" in capsys.readouterr().out
    assert path.read_bytes() == cleaned
    assert path.stat().st_mtime_ns == initial


def test_cleanup_preserves_original_permission_bits(uploads, monkeypatch):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    source, markers = _sample("jpg")
    path = uploads / "plaza_original.jpg"
    path.write_bytes(source)
    path.chmod(0o640)
    assert script.main(["--apply"]) == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert all(marker not in path.read_bytes() for marker in markers)


@pytest.mark.parametrize("xmp_before_loop", [True, False])
def test_cleanup_gif_xmp_application_is_not_hidden_by_loop_extension(uploads, monkeypatch, xmp_before_loop):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    output = io.BytesIO()
    first = Image.new("RGB", (4, 4), "red")
    first.save(output, "GIF", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")],
               duration=[100, 200], loop=2)
    clean = output.getvalue()
    loop = clean.index(b"!\xff\x0bNETSCAPE2.0")
    offset = loop if xmp_before_loop else loop + 19
    xmp = b"!\xff\x0bXMP DataXMP" + bytes([len(PRIVATE_XMP)]) + PRIVATE_XMP + b"\x00"
    source = clean[:offset] + xmp + clean[offset:]
    assert PRIVATE_XMP in source
    path = uploads / "plaza_old.gif"
    path.write_bytes(source)
    assert script.main(["--apply"]) == 0
    assert PRIVATE_XMP not in path.read_bytes()
    assert _frame_durations(path.read_bytes()) == [100, 200]
    with Image.open(path) as image:
        assert image.info["loop"] == 2


@pytest.mark.parametrize("kind", ["png", "webp", "jpg"])
def test_cleanup_hidden_container_metadata_is_not_mistaken_for_clean_image(uploads, monkeypatch, kind):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(output, media._PIL_FORMAT_BY_EXT[kind])
    clean = output.getvalue()
    if kind == "png":
        body = b"vpAg" + PRIVATE_GPS
        chunk = len(PRIVATE_GPS).to_bytes(4, "big") + body + (binascii.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")
        source = clean[:33] + chunk + clean[33:]
    elif kind == "webp":
        body = b"JUNK" + len(PRIVATE_GPS).to_bytes(4, "little") + PRIVATE_GPS
        body += b"\x00" * (len(PRIVATE_GPS) % 2)
        source = clean[:4] + (len(clean) - 8 + len(body)).to_bytes(4, "little") + clean[8:] + body
    else:
        body = b"\xff\xe3" + (len(PRIVATE_GPS) + 2).to_bytes(2, "big") + PRIVATE_GPS
        source = clean[:2] + body + clean[2:]
    assert PRIVATE_GPS in source
    path = uploads / f"plaza_hidden_metadata.{kind}"
    path.write_bytes(source)
    assert script.main(["--apply"]) == 0
    assert PRIVATE_GPS not in path.read_bytes()


def test_cleanup_apply_failure_cli_exit_code_is_nonzero(uploads, monkeypatch):
    from scripts import strip_upload_metadata as script

    monkeypatch.setenv("FIONA_UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    broken = uploads / "plaza_broken.jpg"
    broken.write_bytes(b"\xff\xd8\xffbroken")
    result = subprocess.run([sys.executable, script.__file__, "--apply"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert "已处理：0；失败：1" in result.stdout
    assert broken.read_bytes() == b"\xff\xd8\xffbroken"
