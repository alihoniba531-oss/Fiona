"""工作室声线处理：声线特效 + 两遍 loudnorm 响度标准化（ffmpeg，异步）。

滤镜字符串原样移植自本地脚本（只读源文件，不修改）：
  - /Users/yangjing/Desktop/视频生成/fx_robot.sh 第 18-23 行（``ROBOTIZE`` / ``ROBOTIZE_DEEP`` 与各档 ``af``）
  - /Users/yangjing/Desktop/视频生成/fx_beast.sh 第 29-30 行（``SUB`` / ``DET`` / ``HALL`` 与各档 ``af``）
滤镜按 44100 Hz 调校，因此先重采样到 44100 再套特效，最后回到 48000 Hz 单声道 s16。
"""
from __future__ import annotations

import asyncio
import io
import json
import math
import re
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path


# 滤镜调校采样率、输出采样率与 loudnorm 的 LRA（见规格 §10.2）。
FX_SAMPLE_RATE = 44100
OUTPUT_SAMPLE_RATE = 48000
LOUDNESS_RANGE = 11


class AudioProcessError(RuntimeError):
    """声线处理失败（解码 / 特效 / 响度 / 输出校验 / 超时）。"""


# ---------------------------------------------------------------- 滤镜常量
# 以下变量名与源脚本一致，便于逐字核对展开结果。
_ROBOTIZE = "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=768:overlap=0.75"
_ROBOTIZE_DEEP = "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=1024:overlap=0.75"
_SUB = "asetrate=44100*0.5,aresample=44100,atempo=2.0"
_DET = "asetrate=44100*1.00695,aresample=44100,atempo=0.99310"
_HALL = "aecho=0.72:0.62:37|61|97|149:0.34|0.26|0.19|0.12"
_HALL_LONG = "aecho=0.68:0.66:53|97|163|251|389:0.38|0.31|0.24|0.17|0.11"

FX_PRESETS: dict[str, dict[str, str]] = {
    "robot": {
        "A": "highpass=f=140,lowpass=f=7600,equalizer=f=2600:t=q:w=1.2:g=5,aecho=0.9:0.85:9:0.12",
        "B": f"{_ROBOTIZE},highpass=f=85,lowpass=f=6800,equalizer=f=2200:t=q:w=1.0:g=7,equalizer=f=3600:t=q:w=1.2:g=4,aecho=0.85:0.8:16:0.18",
        "Bd": f"{_ROBOTIZE_DEEP},highpass=f=70,lowpass=f=6800,equalizer=f=2200:t=q:w=1.0:g=7,equalizer=f=3600:t=q:w=1.2:g=4,aecho=0.85:0.8:16:0.18",
        "C": f"{_ROBOTIZE},tremolo=f=65:d=0.35,acrusher=bits=10:mode=log:aa=1,highpass=f=240,lowpass=f=6200,equalizer=f=2800:t=q:w=1.0:g=8,flanger=delay=1.5:depth=2:speed=0.35,aecho=0.82:0.78:22:0.24",
        "D": "highpass=f=200,lowpass=f=4500,aphaser=in_gain=0.5:out_gain=0.8:delay=2.5:decay=0.35:speed=0.6,aecho=0.8:0.4:22:0.22,volume=1.1",
        "E": "highpass=f=320,lowpass=f=3400,acrusher=bits=10:mode=log:mix=0.35,aphaser=in_gain=0.5:out_gain=0.85:delay=3:decay=0.4:speed=1.2,aecho=0.7:0.5:55:0.3,volume=1.2",
    },
    "beast": {
        "A": f"asplit=2[a][b];[b]{_SUB},volume=0.75[sub];[a][sub]amix=inputs=2:weights=1 0.6:normalize=0,bass=g=6:f=110:w=0.6,acompressor=threshold=-18dB:ratio=3:attack=8:release=140,volume=1.25",
        "B": f"asplit=3[a][b][c];[b]{_SUB},volume=0.8[sub];[c]{_DET},volume=0.5[det];[a][sub][det]amix=inputs=3:weights=1 0.7 0.4:normalize=0,bass=g=7:f=105:w=0.65[mix];[mix]asplit=2[dry][wet];[wet]lowpass=f=2600,{_HALL},volume=0.85[rev];[dry][rev]amix=inputs=2:weights=1 0.65:normalize=0,acompressor=threshold=-19dB:ratio=3.5:attack=8:release=160,volume=1.3",
        "C": f"asplit=3[a][b][c];[b]{_SUB},volume=1.0[sub];[c]{_DET},volume=0.55[det];[a][sub][det]amix=inputs=3:weights=1 0.9 0.45:normalize=0,bass=g=8:f=100:w=0.7,lowpass=f=6000[mix];[mix]asplit=2[dry][wet];[wet]lowpass=f=1800,{_HALL_LONG},volume=1.0[rev];[dry][rev]amix=inputs=2:weights=1 0.8:normalize=0,equalizer=f=210:t=q:w=1.1:g=4,acompressor=threshold=-20dB:ratio=4:attack=10:release=200,volume=1.35",
    },
    "inner": {
        "A": "lowpass=f=6800,aecho=0.85:0.3:60:0.18,equalizer=f=300:t=q:w=1.0:g=2,volume=1.05",
    },
}

# 含 asplit/amix 的多路图必须走 -filter_complex（其余用 -af）。
_COMPLEX_KINDS = frozenset({"beast"})


def parse_fx(fx: str | None) -> tuple[str, str] | None:
    """``"robot:B"`` → ``("robot", "B")``；``None`` → ``None``；非法抛 ``ValueError``。"""
    if fx is None:
        return None
    if not isinstance(fx, str):
        raise ValueError("声线特效格式非法：应为 '类别:档位'")
    kind, sep, tier = fx.strip().partition(":")
    if not sep:
        raise ValueError(f"声线特效格式非法（缺少档位）：{fx!r}")
    kind_key = kind.strip().lower()
    presets = FX_PRESETS.get(kind_key)
    if presets is None:
        raise ValueError(f"未知声线特效类别：{kind.strip()!r}")
    tier_key = tier.strip()
    for name in presets:
        if name.lower() == tier_key.lower():
            return (kind_key, name)
    raise ValueError(f"未知声线特效档位：{kind_key}:{tier_key}")


@dataclass
class ProcessedAudio:
    """处理结果；``measured_lufs`` / ``true_peak`` 为最终文件实测值。"""

    wav: bytes
    sample_rate: int
    samples: int
    duration_s: float
    measured_lufs: float
    true_peak: float


# ---------------------------------------------------------------- 内部工具
# loudnorm 第一遍/测量输出的 JSON 字段 → 第二遍的 measured_* 参数。
_MEASURE_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
_JSON_ERROR = "loudnorm 测量结果解析失败"


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def _input_suffix(input_format: str) -> str:
    """由 ``input_format`` 得到安全扩展名（``wav`` / ``audio/wav`` → ``.wav``）。"""
    fmt = re.sub(r"[^a-z0-9]", "", (input_format or "").strip().lower().rsplit("/", 1)[-1])
    return f".{fmt}" if fmt else ".bin"


async def _spawn(args: list[str]) -> asyncio.subprocess.Process:
    """起一个子进程（测试用 ``monkeypatch`` 替换此钩子即可注入假进程）。"""
    return await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _run(args: list[str], *, timeout_s: float) -> str:
    """执行一次 ffmpeg；超时 kill 进程；非 0 退出抛 ``AudioProcessError``。"""
    proc = await _spawn(args)
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # 已经退出
            pass
        await proc.wait()
        raise AudioProcessError(f"ffmpeg 超时（超过 {timeout_s} 秒）已终止") from None
    text = (err or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        tail = text.strip().splitlines()[-1] if text.strip() else "无错误输出"
        raise AudioProcessError(f"ffmpeg 处理失败（退出码 {proc.returncode}）：{tail}")
    return text


def _parse_loudnorm(stderr: str) -> dict[str, float]:
    """从 stderr 里取出 loudnorm 的 JSON 块（``input_*`` / ``target_offset``）。"""
    start = stderr.rfind("{")
    while start != -1:
        end = stderr.find("}", start)
        if end != -1:
            try:
                data = json.loads(stderr[start:end + 1])
            except (ValueError, TypeError):
                data = None
            if isinstance(data, dict) and "input_i" in data:
                try:
                    return {key: float(data[key]) for key in _MEASURE_KEYS}
                except (KeyError, TypeError, ValueError):
                    raise AudioProcessError(_JSON_ERROR) from None
        start = stderr.rfind("{", 0, start)
    raise AudioProcessError(_JSON_ERROR)


def _build_graph(kind: str, preset: str | None, loudnorm: str) -> tuple[str, bool]:
    """拼滤镜图；返回 ``(图, 是否 filter_complex)``。``fx=None`` 表示只做响度标准化。"""
    parts = [f"aresample={FX_SAMPLE_RATE}"]
    if preset:
        parts.append(preset)
    parts.append(loudnorm)
    chain = ",".join(parts)
    if kind in _COMPLEX_KINDS:
        # beast 多路图：整条链挂在 [0:a] 上，loudnorm 追加在链尾。
        return f"[0:a]{chain}", True
    return chain, False


def _wav_info(data: bytes) -> tuple[int, int, float]:
    """解析输出 WAV；返回 ``(采样率, 帧数, 时长秒)``。"""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate = wav.getframerate()
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            frames = wav.getnframes()
    except (wave.Error, EOFError, ValueError) as exc:
        raise AudioProcessError(f"输出音频解析失败：{exc}") from None
    if rate != OUTPUT_SAMPLE_RATE or channels != 1 or width != 2:
        raise AudioProcessError(
            f"输出音频格式异常：{rate} Hz / {channels} 声道 / {width * 8} 位，"
            f"预期 {OUTPUT_SAMPLE_RATE} Hz 单声道 16 位"
        )
    if frames <= 0 or not data:
        raise AudioProcessError("输出音频为空")
    return rate, frames, frames / rate


# ---------------------------------------------------------------- 主流程
async def process_voice(raw: bytes, *, input_format: str, fx: str | None, target_lufs: float,
                        true_peak: float = -1.5, timeout_s: float = 60) -> ProcessedAudio:
    """解码 → 44100 重采样 + 特效 → 两遍 loudnorm → 48000 单声道 s16 WAV。

    ``timeout_s`` 是每一次 ffmpeg 调用的上限（测量 / 合成 / 复核各一次），超时即 kill。
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg unavailable")
    if not raw:
        raise AudioProcessError("音频数据为空")
    preset = parse_fx(fx)
    if preset is None:
        kind, chain = "", None      # 无特效：只做响度标准化
    else:
        kind, tier = preset
        chain = FX_PRESETS[kind][tier]

    with tempfile.TemporaryDirectory(prefix="fiona-voice-") as tmpdir:
        work = Path(tmpdir)
        src = work / f"input{_input_suffix(input_format)}"
        src.write_bytes(raw)
        loud = f"loudnorm=I={_fmt(float(target_lufs))}:TP={_fmt(float(true_peak))}:LRA={LOUDNESS_RANGE}"

        # 第一遍：测量（print_format=json，JSON 走 stderr）。
        graph, complex_chain = _build_graph(kind, chain, f"{loud}:print_format=json")
        first = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", str(src)]
        first += (["-filter_complex", graph] if complex_chain else ["-af", graph])
        first += ["-f", "null", "-"]
        measured = _parse_loudnorm(await _run(first, timeout_s=timeout_s))
        if not math.isfinite(measured["input_i"]) or not math.isfinite(measured["target_offset"]):
            raise AudioProcessError("输入音频为静音，无法进行响度标准化")

        # 第二遍：linear=true + 第一遍实测值，重采样 48000 并输出单声道 s16。
        linear = (
            f"{loud}:linear=true:measured_I={_fmt(measured['input_i'])}"
            f":measured_TP={_fmt(measured['input_tp'])}"
            f":measured_LRA={_fmt(measured['input_lra'])}"
            f":measured_thresh={_fmt(measured['input_thresh'])}"
            f":offset={_fmt(measured['target_offset'])},aresample={OUTPUT_SAMPLE_RATE}"
        )
        graph2, complex_chain2 = _build_graph(kind, chain, linear)
        dst = work / "final.wav"
        second = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(src)]
        second += (["-filter_complex", graph2] if complex_chain2 else ["-af", graph2])
        second += ["-ac", "1", "-ar", str(OUTPUT_SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)]
        await _run(second, timeout_s=timeout_s)
        wav_bytes = dst.read_bytes()

        # 回填 measured_lufs / 实测真峰值：对最终文件再跑一遍 loudnorm 测量。
        check = ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(dst),
                 "-af", "loudnorm=print_format=json", "-f", "null", "-"]
        final_measured = _parse_loudnorm(await _run(check, timeout_s=timeout_s))

    rate, frames, duration = _wav_info(wav_bytes)
    return ProcessedAudio(
        wav=wav_bytes,
        sample_rate=rate,
        samples=frames,
        duration_s=duration,
        measured_lufs=final_measured["input_i"],
        true_peak=final_measured["input_tp"],
    )
