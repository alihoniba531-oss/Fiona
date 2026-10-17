"""声线特效与响度处理（``studio.audio``）与音频存储的离线测试。

输入一律用 ffmpeg 合成的正弦波，不引入任何版权音频；需要 ffmpeg/ffprobe 的用例
都带 skip 守卫（规格 §11.2：没有 ffmpeg 时 skip），音频存储用例不依赖 ffmpeg。
"""
from __future__ import annotations

import array
import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from studio import audio
from studio import storage as studio_storage

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 不可用")
requires_ffprobe = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe 不可用")

TARGET_LUFS = -16.0
TP = -1.5


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_sine(path: Path, *, container: str = "wav", duration: float = 2.0,
               frequency: int = 220, sample_rate: int = 44100) -> Path:
    """用 ffmpeg 合成单声道正弦波测试输入。"""
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:duration={duration}",
            "-ac", "1", "-ar", str(sample_rate)]
    if container == "mp3":
        args += ["-c:a", "libmp3lame", "-b:a", "128k"]
    args += [str(path)]
    subprocess.run(args, check=True, capture_output=True)
    assert path.exists() and path.stat().st_size > 0
    return path


@pytest.fixture(scope="module")
def sine_wav(tmp_path_factory) -> Path:
    return _make_sine(tmp_path_factory.mktemp("sine") / "sine220.wav")


@pytest.fixture(scope="module")
def sine_mp3(tmp_path_factory) -> Path:
    return _make_sine(tmp_path_factory.mktemp("sine") / "sine220.mp3", container="mp3")


def _probe_audio(path: Path) -> dict:
    """直接用 ffprobe 读第一条音频流（不依赖 studio.storage）。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,sample_rate,channels,duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    streams = json.loads(out)["streams"]
    assert streams, "输出里没有音频流"
    return streams[0]


def _write_and_check(out_path: Path, result: audio.ProcessedAudio) -> dict:
    """落盘并校验：48000 Hz / 单声道 / s16，且波形非静音。"""
    out_path.write_bytes(result.wav)
    probe = _probe_audio(out_path)
    assert probe["codec_name"] == "pcm_s16le"
    assert int(probe["sample_rate"]) == 48000
    assert int(probe["channels"]) == 1
    with wave.open(str(out_path), "rb") as wav:
        assert wav.getframerate() == 48000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        frames = wav.getnframes()
        samples = array.array("h")
        samples.frombytes(wav.readframes(frames))
    assert frames == result.samples
    assert abs(result.duration_s - frames / 48000) < 1e-6
    assert max(abs(value) for value in samples[::7]) > 0, "输出波形为静音"
    return probe
EXPECTED_FX = {
    "robot": {
        "A": "highpass=f=140,lowpass=f=7600,equalizer=f=2600:t=q:w=1.2:g=5,aecho=0.9:0.85:9:0.12",
        "B": "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=768:overlap=0.75,highpass=f=85,lowpass=f=6800,equalizer=f=2200:t=q:w=1.0:g=7,equalizer=f=3600:t=q:w=1.2:g=4,aecho=0.85:0.8:16:0.18",
        "Bd": "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=1024:overlap=0.75,highpass=f=70,lowpass=f=6800,equalizer=f=2200:t=q:w=1.0:g=7,equalizer=f=3600:t=q:w=1.2:g=4,aecho=0.85:0.8:16:0.18",
        "C": "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=768:overlap=0.75,tremolo=f=65:d=0.35,acrusher=bits=10:mode=log:aa=1,highpass=f=240,lowpass=f=6200,equalizer=f=2800:t=q:w=1.0:g=8,flanger=delay=1.5:depth=2:speed=0.35,aecho=0.82:0.78:22:0.24",
        "D": "highpass=f=200,lowpass=f=4500,aphaser=in_gain=0.5:out_gain=0.8:delay=2.5:decay=0.35:speed=0.6,aecho=0.8:0.4:22:0.22,volume=1.1",
        "E": "highpass=f=320,lowpass=f=3400,acrusher=bits=10:mode=log:mix=0.35,aphaser=in_gain=0.5:out_gain=0.85:delay=3:decay=0.4:speed=1.2,aecho=0.7:0.5:55:0.3,volume=1.2",
    },
    "beast": {
        "A": "asplit=2[a][b];[b]asetrate=44100*0.5,aresample=44100,atempo=2.0,volume=0.75[sub];[a][sub]amix=inputs=2:weights=1 0.6:normalize=0,bass=g=6:f=110:w=0.6,acompressor=threshold=-18dB:ratio=3:attack=8:release=140,volume=1.25",
        "B": "asplit=3[a][b][c];[b]asetrate=44100*0.5,aresample=44100,atempo=2.0,volume=0.8[sub];[c]asetrate=44100*1.00695,aresample=44100,atempo=0.99310,volume=0.5[det];[a][sub][det]amix=inputs=3:weights=1 0.7 0.4:normalize=0,bass=g=7:f=105:w=0.65[mix];[mix]asplit=2[dry][wet];[wet]lowpass=f=2600,aecho=0.72:0.62:37|61|97|149:0.34|0.26|0.19|0.12,volume=0.85[rev];[dry][rev]amix=inputs=2:weights=1 0.65:normalize=0,acompressor=threshold=-19dB:ratio=3.5:attack=8:release=160,volume=1.3",
        "C": "asplit=3[a][b][c];[b]asetrate=44100*0.5,aresample=44100,atempo=2.0,volume=1.0[sub];[c]asetrate=44100*1.00695,aresample=44100,atempo=0.99310,volume=0.55[det];[a][sub][det]amix=inputs=3:weights=1 0.9 0.45:normalize=0,bass=g=8:f=100:w=0.7,lowpass=f=6000[mix];[mix]asplit=2[dry][wet];[wet]lowpass=f=1800,aecho=0.68:0.66:53|97|163|251|389:0.38|0.31|0.24|0.17|0.11,volume=1.0[rev];[dry][rev]amix=inputs=2:weights=1 0.8:normalize=0,equalizer=f=210:t=q:w=1.1:g=4,acompressor=threshold=-20dB:ratio=4:attack=10:release=200,volume=1.35",
    },
    "inner": {
        "A": "lowpass=f=6800,aecho=0.85:0.3:60:0.18,equalizer=f=300:t=q:w=1.0:g=2,volume=1.05",
    },
}


# ---------------------------------------------------------------- 滤镜常量
@requires_ffmpeg
def test_presets_ported_verbatim():
    """三套预设逐字等于源脚本展开结果（robot/inner 用 -af，beast 用 -complex）。"""
    assert audio.FX_PRESETS == EXPECTED_FX
    assert audio.FX_PRESETS["inner"]["A"] == (
        "lowpass=f=6800,aecho=0.85:0.3:60:0.18,equalizer=f=300:t=q:w=1.0:g=2,volume=1.05")
    assert audio.FX_PRESETS["robot"]["B"].index("win_size=768") > 0
    assert audio.FX_PRESETS["robot"]["Bd"].index("win_size=1024") > 0
    # 多抽头、normalize=0、weights 空格分隔必须原样保留。
    assert "aecho=0.68:0.66:53|97|163|251|389:0.38|0.31|0.24|0.17|0.11" in audio.FX_PRESETS["beast"]["C"]
    assert "amix=inputs=3:weights=1 0.9 0.45:normalize=0" in audio.FX_PRESETS["beast"]["C"]


# ---------------------------------------------------------------- parse_fx
@pytest.mark.parametrize("fx,expected", [
    ("robot:B", ("robot", "B")),
    ("robot:Bd", ("robot", "Bd")),
    ("beast:C", ("beast", "C")),
    ("inner:A", ("inner", "A")),
    ("  robot:c  ", ("robot", "C")),   # 容忍空白与大小写
    ("ROBOT:bd", ("robot", "Bd")),
    ("robot:BD", ("robot", "Bd")),      # 档位大小写不敏感
])
def test_parse_fx_valid(fx, expected):
    assert audio.parse_fx(fx) == expected


def test_parse_fx_none():
    assert audio.parse_fx(None) is None


@pytest.mark.parametrize("fx", [
    "", "robot", "robot:", ":B", "robot:Z", "pig:A", "robot:B:extra", "robot: B C",
])
def test_parse_fx_invalid(fx):
    with pytest.raises(ValueError):
        audio.parse_fx(fx)


def test_parse_fx_rejects_non_str():
    with pytest.raises(ValueError):
        audio.parse_fx(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------- 端到端
@requires_ffprobe
@pytest.mark.anyio
@pytest.mark.parametrize("fx", [
    "robot:A", "robot:B", "beast:A", "beast:B", "beast:C", "inner:A", None,
])
async def test_process_voice_three_kinds(fx, sine_wav, tmp_path):
    """三类特效各档跑通：48000 Hz 单声道 s16，实测响度在目标 ±1 LU 内。"""
    result = await audio.process_voice(
        sine_wav.read_bytes(), input_format="wav", fx=fx, target_lufs=TARGET_LUFS, true_peak=TP)
    assert result.sample_rate == 48000
    assert 1.5 <= result.duration_s <= 4.0          # 2 秒输入 + 回声尾巴
    assert result.samples == int(round(result.duration_s * 48000))
    assert abs(result.measured_lufs - TARGET_LUFS) <= 1.0
    assert result.true_peak <= TP + 1e-6            # 真峰值不得超过上限
    assert result.true_peak < 0
    _write_and_check(tmp_path / "out.wav", result)


@requires_ffprobe
@pytest.mark.anyio
async def test_process_voice_mp3_input(sine_mp3, tmp_path):
    """mp3 输入同样收敛到 48 kHz 单声道 s16 与目标响度。"""
    result = await audio.process_voice(
        sine_mp3.read_bytes(), input_format="mp3", fx="robot:D", target_lufs=TARGET_LUFS)
    assert result.sample_rate == 48000
    assert abs(result.measured_lufs - TARGET_LUFS) <= 1.0
    _write_and_check(tmp_path / "from_mp3.wav", result)


@requires_ffprobe
@pytest.mark.anyio
async def test_process_voice_respects_other_target(sine_wav, tmp_path):
    """目标响度可调：-20 LUFS 也要落在 ±1 LU 内。"""
    result = await audio.process_voice(
        sine_wav.read_bytes(), input_format="wav", fx="inner:A", target_lufs=-20.0)
    assert abs(result.measured_lufs - (-20.0)) <= 1.0
    _write_and_check(tmp_path / "target20.wav", result)


@pytest.mark.anyio
@requires_ffmpeg
async def test_process_voice_rejects_empty_payload():
    with pytest.raises(audio.AudioProcessError):
        await audio.process_voice(b"", input_format="wav", fx="robot:A", target_lufs=TARGET_LUFS)


@requires_ffmpeg
@pytest.mark.anyio
async def test_process_voice_rejects_corrupt_input():
    with pytest.raises(audio.AudioProcessError):
        await audio.process_voice(b"definitely-not-audio", input_format="wav",
                                  fx="robot:A", target_lufs=TARGET_LUFS)


@requires_ffmpeg
@pytest.mark.anyio
async def test_process_voice_rejects_video_without_audio_track(tmp_path):
    """没有音轨的文件必须明确报错，不能静默出空音频。"""
    clip = tmp_path / "silent_video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:d=1", "-an", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
    with pytest.raises(audio.AudioProcessError):
        await audio.process_voice(clip.read_bytes(), input_format="mp4",
                                  fx="beast:A", target_lufs=TARGET_LUFS)


# ---------------------------------------------------------------- 超时
class _HangingProcess:
    """只会挂住的假子进程；被 kill() 后才结束。"""

    def __init__(self):
        self.killed = False
        self.returncode = None
        self._done = False

    async def communicate(self):
        import asyncio
        while not self._done:
            await asyncio.sleep(0.01)
        return (b"", b"")

    def kill(self):
        self.killed = True
        self.returncode = -9
        self._done = True

    async def wait(self):
        self.returncode = self.returncode if self.returncode is not None else -9
        return self.returncode


@pytest.mark.anyio
@requires_ffmpeg
async def test_timeout_calls_kill(monkeypatch, sine_wav):
    """超时必须 kill() 子进程，并抛 AudioProcessError。"""
    proc = _HangingProcess()

    async def fake_spawn(args):
        return proc

    monkeypatch.setattr(audio, "_spawn", fake_spawn)
    with pytest.raises(audio.AudioProcessError) as excinfo:
        await audio.process_voice(sine_wav.read_bytes(), input_format="wav", fx="robot:A",
                                  target_lufs=TARGET_LUFS, timeout_s=0.05)
    assert proc.killed is True
    assert proc.returncode == -9
    assert "超时" in str(excinfo.value)


@pytest.mark.anyio
@requires_ffmpeg
async def test_timeout_kills_real_child_process(monkeypatch, sine_wav):
    """真实子进程被超时 kill：用 sleep 代替 ffmpeg，断言退出码为 SIGKILL。"""
    spawned = []
    real_spawn = audio._spawn

    async def slow_spawn(args):
        proc = await real_spawn(["/bin/sleep", "10"])
        spawned.append(proc)
        return proc

    monkeypatch.setattr(audio, "_spawn", slow_spawn)
    with pytest.raises(audio.AudioProcessError):
        await audio.process_voice(sine_wav.read_bytes(), input_format="wav", fx=None,
                                  target_lufs=TARGET_LUFS, timeout_s=0.2)
    assert len(spawned) == 1
    assert spawned[0].returncode == -9


# ---------------------------------------------------------------- 缺 ffmpeg
@pytest.mark.anyio
async def test_missing_ffmpeg_raises(monkeypatch):
    """没有 ffmpeg 时抛 RuntimeError("ffmpeg unavailable")（消息逐字一致）。"""
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as excinfo:
        await audio.process_voice(b"whatever", input_format="wav", fx="robot:A",
                                  target_lufs=TARGET_LUFS)
    assert str(excinfo.value) == "ffmpeg unavailable"


# ---------------------------------------------------------------- 音频存储（§8.1 storage 新函数）
@pytest.fixture
def studio_root(monkeypatch, tmp_path):
    root = tmp_path / "studio"
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(root))
    return root


def test_save_audio_atomic_path_and_digest(studio_root):
    """路径为 <pid>/audio/<sha256>.wav，内容寻址，原子写且不留 .part。"""
    data = b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(range(64))
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    result = studio_storage.save_audio("proj-1", data)
    assert result == {"rel_path": f"proj-1/audio/{digest}.wav",
                      "sha256": digest, "bytes": len(data)}
    stored = studio_storage.resolve_path(result["rel_path"])
    assert stored.read_bytes() == data
    assert stored.parent.name == "audio"
    assert not list(studio_root.rglob("*.part"))


def test_save_audio_is_content_addressed_and_overwrite_safe(studio_root):
    first = studio_storage.save_audio("proj-1", b"abcdef")
    second = studio_storage.save_audio("proj-1", b"abcdef")
    assert first["rel_path"] == second["rel_path"]          # 同内容同路径
    third = studio_storage.save_audio("proj-1", b"zbcdef")
    assert third["rel_path"] != first["rel_path"]
    assert studio_storage.resolve_path(first["rel_path"]).read_bytes() == b"abcdef"


def test_save_audio_honours_extension(studio_root):
    result = studio_storage.save_audio("proj-1", b"mp3-bytes", ext=".MP3")
    assert result["rel_path"].endswith(".mp3")
    assert studio_storage.resolve_path(result["rel_path"]).read_bytes() == b"mp3-bytes"


@pytest.mark.parametrize("project_id", ["../evil", "a/b", "a\\b", "", ".", "a b"])
def test_save_audio_rejects_bad_project_id(studio_root, project_id):
    with pytest.raises(ValueError):
        studio_storage.save_audio(project_id, b"x")


@pytest.mark.parametrize("ext", ["", "wav", ".wav/", "../wav", ".toolongext", ".w v"])
def test_save_audio_rejects_bad_extension(studio_root, ext):
    with pytest.raises(ValueError):
        studio_storage.save_audio("proj-1", b"x", ext=ext)


def test_save_audio_rejects_empty_payload(studio_root):
    with pytest.raises(ValueError):
        studio_storage.save_audio("proj-1", b"")


@requires_ffprobe
def test_probe_audio_reads_audio_stream(studio_root, sine_wav):
    """probe_audio 只返回音频流信息，且拿到真实采样率/声道。"""
    rel = studio_storage.save_audio("proj-1", sine_wav.read_bytes())
    info = studio_storage.probe_audio(studio_storage.resolve_path(rel["rel_path"]))
    assert info["sample_rate"] == 44100
    assert info["channels"] == 1
    assert 1.5 <= info["duration_s"] <= 2.5


@requires_ffprobe
def test_probe_audio_ignores_video_only_file(studio_root, tmp_path):
    """纯视频文件没有音频流：必须报错，证明只看音频流而不是容器时长。"""
    clip = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:d=1", "-an", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
    rel = studio_storage.save_audio("proj-1", clip.read_bytes(), ext=".mp4")
    with pytest.raises(studio_storage.DownloadError) as excinfo:
        studio_storage.probe_audio(studio_storage.resolve_path(rel["rel_path"]))
    assert excinfo.value.code == "invalid_output"


def test_probe_audio_reports_missing_ffprobe(studio_root, monkeypatch, tmp_path):
    """没有 ffprobe 时抛 DownloadError，而不是别的异常类型。"""
    target = tmp_path / "x.wav"
    target.write_bytes(b"RIFF")

    def no_ffprobe(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(studio_storage.subprocess, "run", no_ffprobe)
    with pytest.raises(studio_storage.DownloadError) as excinfo:
        studio_storage.probe_audio(target)
    assert excinfo.value.code == "ffprobe_unavailable"
    assert excinfo.value.retryable is True
