"""结果下载和 ffprobe 的离线安全边界。"""
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from fastapi import HTTPException
import httpx
import pytest

from studio import storage


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def media_root(monkeypatch, tmp_path):
    root = tmp_path / "studio"
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    monkeypatch.setenv("FIONA_STUDIO_VIDEO_HOSTS", "*.oss-accelerate.aliyuncs.com,video.example.test")
    return root


@pytest.fixture
def fake_probe(monkeypatch):
    metadata = {"width": 480, "height": 852, "duration_s": 5.0, "fps": 30.0, "has_audio": True}
    monkeypatch.setattr(storage, "probe_video", lambda path: metadata)
    return metadata


@pytest.mark.parametrize("url", [
    "https://evil.test/movie.mp4",
    "https://video.example.test.evil.test/movie.mp4",
    "https://evil.test/?url=https://video.example.test/movie.mp4",
    "https://user:secret@video.example.test/movie.mp4",
    "file:///private/movie.mp4",
    "https://video.example.test:invalid/movie.mp4",
])
@pytest.mark.anyio
async def test_download_denies_url_before_transport(media_root, url):
    requests = []
    def handler(request):
        requests.append(request)
        raise AssertionError("不允许访问传输")
    with pytest.raises(storage.DownloadError):
        await storage.download_video(url, "project", "job", transport=httpx.MockTransport(handler))
    assert requests == []
    assert not media_root.exists()


@pytest.mark.anyio
async def test_download_atomic_complete_and_no_auth(media_root, fake_probe, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "do-not-forward-this")
    monkeypatch.setenv("ARK_API_KEY", "do-not-forward-that")
    monkeypatch.setenv("HTTPS_PROXY", "https://never-use-this-proxy.test")
    requests = []
    data = b"fake-video-payload"
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert "x-api-key" not in request.headers
        assert not list(media_root.rglob("*.mp4"))
        return httpx.Response(200, content=data)
    result = await storage.download_video("https://dashscope-test.oss-accelerate.aliyuncs.com/v.mp4",
                                          "project", "job", transport=httpx.MockTransport(handler))
    assert len(requests) == 1
    assert storage.resolve_path(result["rel_path"]).read_bytes() == data
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["bytes"] == len(data)
    assert result["duration_s"] == 5
    assert not list(media_root.rglob("*.part"))


@pytest.mark.parametrize("status,expired,retryable", [(301, False, False), (302, False, False),
    (307, False, False), (403, True, False), (404, True, False), (429, False, True), (500, False, True)])
@pytest.mark.anyio
async def test_download_status_and_no_redirect(media_root, status, expired, retryable):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://evil.test/video.mp4"})
    with pytest.raises(storage.DownloadError) as error:
        await storage.download_video("https://video.example.test/v.mp4", "project", "job",
                                      transport=httpx.MockTransport(handler))
    assert error.value.expired is expired
    assert error.value.retryable is retryable
    assert len(requests) == 1
    assert not list(media_root.rglob("*.mp4"))
    assert not list(media_root.rglob("*.part"))


@pytest.mark.parametrize("declared", [str(300 * 1024 * 1024 + 1), "-1", "0", "invalid"])
@pytest.mark.anyio
async def test_download_rejects_declared_size(media_root, declared):
    with pytest.raises(storage.DownloadError):
        await storage.download_video("https://video.example.test/v.mp4", "project", "job",
            transport=httpx.MockTransport(lambda request: httpx.Response(
                200, headers={"Content-Length": declared}, content=b"123")))
    assert not list(media_root.rglob("*.mp4"))
    assert not list(media_root.rglob("*.part"))


class BodyStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


@pytest.mark.anyio
async def test_download_enforces_stream_size_without_length(media_root, monkeypatch):
    monkeypatch.setattr(storage, "MAX_VIDEO_BYTES", 10)
    with pytest.raises(storage.DownloadError) as error:
        await storage.download_video("https://video.example.test/v.mp4", "project", "job",
            transport=httpx.MockTransport(lambda request: httpx.Response(
                200, stream=BodyStream([b"123456", b"789012"]))))
    assert error.value.code == "download_too_large"
    assert not list(media_root.rglob("*.part"))
    assert not list(media_root.rglob("*.mp4"))


@pytest.mark.anyio
async def test_download_incomplete_cleans_temporary_file(media_root):
    with pytest.raises(storage.DownloadError) as error:
        await storage.download_video("https://video.example.test/v.mp4", "project", "job",
            transport=httpx.MockTransport(lambda request: httpx.Response(
                200, stream=BodyStream([b"some data", httpx.ReadError("stream interrupted")]))))
    assert error.value.retryable
    assert not list(media_root.rglob("*.part"))
    assert not list(media_root.rglob("*.mp4"))


@pytest.mark.anyio
async def test_download_length_mismatch(media_root):
    with pytest.raises(storage.DownloadError) as error:
        await storage.download_video("https://video.example.test/v.mp4", "project", "job",
            transport=httpx.MockTransport(lambda request: httpx.Response(
                200, headers={"Content-Length": "20"}, content=b"short")))
    assert error.value.code == "download_incomplete"
    assert error.value.retryable
    assert not list(media_root.rglob("*.part"))


@pytest.mark.anyio
async def test_failed_probe_never_renames_partial(media_root, monkeypatch):
    def reject_probe(path):
        assert path.suffix == ".part"
        raise storage.DownloadError("invalid_output", "无法校验")
    monkeypatch.setattr(storage, "probe_video", reject_probe)
    with pytest.raises(storage.DownloadError):
        await storage.download_video("https://video.example.test/v.mp4", "project", "job",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"bad-video")))
    assert not list(media_root.rglob("*.part"))
    assert not list(media_root.rglob("*.mp4"))


@pytest.mark.parametrize("rel_path", ["../outside", "/private/file", "."])
def test_resolve_path_rejects_escape(media_root, rel_path):
    with pytest.raises(HTTPException) as error:
        storage.resolve_path(rel_path)
    assert error.value.status_code == 404


def test_resolve_path_rejects_symlink_escape(media_root, tmp_path):
    media_root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"private")
    (media_root / "link").symlink_to(outside)
    with pytest.raises(HTTPException):
        storage.resolve_path("link")


def test_discard_file_removes_only_its_empty_directories(media_root):
    folder = media_root / "project" / "images"
    folder.mkdir(parents=True)
    (folder / "first.png").write_bytes(b"first")
    (folder / "second.png").write_bytes(b"second")
    storage.discard_file("project/images/first.png")
    assert (folder / "second.png").read_bytes() == b"second"
    storage.discard_file("project/images/second.png")
    assert not (media_root / "project").exists()
    assert media_root.is_dir()


def test_ffprobe_video_duration_not_audio_or_frame_count(media_root, monkeypatch, tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fake-video")
    def run(args, **kwargs):
        assert args[0] == "ffprobe"
        assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
        assert args[-1] == str(path.resolve())
        return SimpleNamespace(stdout=json.dumps({"streams": [
            {"codec_type": "video", "width": 852, "height": 480, "duration": "4.9",
             "avg_frame_rate": "24/1", "nb_frames": "1"},
            {"codec_type": "audio", "duration": "15"}], "format": {"duration": "15"}}))
    monkeypatch.setattr(storage.subprocess, "run", run)
    result = storage.probe_video(path)
    assert result == {"width": 852, "height": 480, "duration_s": 4.9, "fps": 24, "has_audio": True}


def test_ffprobe_falls_back_for_unavailable_stream_metadata(media_root, monkeypatch):
    monkeypatch.setattr(storage.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({
        "streams": [{"codec_type": "video", "width": 480, "height": 852, "duration": "N/A",
                     "avg_frame_rate": "0/0", "r_frame_rate": "30/1"}],
        "format": {"duration": "5"},
    })))
    result = storage.probe_video(Path("video.mp4"))
    assert result["duration_s"] == 5
    assert result["fps"] == 30


@pytest.mark.parametrize("failure,retryable", [(FileNotFoundError(), True),
    (subprocess.CalledProcessError(1, "ffprobe"), False),
    (subprocess.TimeoutExpired("ffprobe", 60), False)])
def test_ffprobe_errors(media_root, monkeypatch, failure, retryable):
    def run(*args, **kwargs):
        raise failure
    monkeypatch.setattr(storage.subprocess, "run", run)
    with pytest.raises(storage.DownloadError) as error:
        storage.probe_video(Path("video.mp4"))
    assert error.value.retryable is retryable
