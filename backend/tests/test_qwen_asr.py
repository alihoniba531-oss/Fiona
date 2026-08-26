# -*- coding: utf-8 -*-
"""Qwen3-ASR-Flash 的离线契约与路由回归测试。"""
import base64
import importlib
import io
import subprocess
import wave
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from pydantic import ValidationError


_MODEL = "qwen3-asr-flash"
_MAX_AUDIO_BYTES = 10 * 1024 * 1024
_WAV_DATA_URI_PREFIX_BYTES = len("data:audio/wav;base64,")
_MAX_BASE64_WAV_BYTES = ((_MAX_AUDIO_BYTES - _WAV_DATA_URI_PREFIX_BYTES) // 4) * 3


def _wav_bytes(pcm: bytes = b"\x01\x00\x02\x00", sample_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def _load_qwen_asr(monkeypatch, api_key: str | None = "unit-test-key"):
    if api_key is None:
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DASHSCOPE_API_KEY", api_key)

    import qwen_asr

    # 允许实现选择在导入时或调用时读取环境变量，同时让每个用例彼此隔离。
    return importlib.reload(qwen_asr)


def _patch_sdk(monkeypatch, fake_call):
    """无论业务模块用 dashscope.MultiModalConversation 还是直接导入类都能拦截。"""
    import dashscope

    monkeypatch.setattr(
        dashscope.MultiModalConversation,
        "call",
        staticmethod(fake_call),
    )


def _successful_response(text: str):
    """官方文档展示的 output.choices[0].message.content 列表结构。"""
    return {
        "status_code": HTTPStatus.OK,
        "output": {
            "choices": [{"message": {"content": [{"text": text}]}}],
        },
    }


def test_qwen_asr_calls_sdk_with_model_key_and_wav_data_uri(monkeypatch):
    qwen_asr = _load_qwen_asr(monkeypatch)
    captured = {}

    def fake_call(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _successful_response("测试识别")

    _patch_sdk(monkeypatch, fake_call)
    audio = _wav_bytes()

    assert qwen_asr.asr_recognize(audio, fmt="wav", sample_rate=16000) == {
        "text": "测试识别"
    }

    args = captured["args"]
    kwargs = captured["kwargs"]
    model = kwargs.get("model") or (args[0] if args else None)
    assert model == _MODEL
    assert kwargs["api_key"] == "unit-test-key"
    assert kwargs["result_format"] == "message"
    assert kwargs["asr_options"] == {"enable_itn": False}

    import dashscope

    assert dashscope.base_http_api_url == "https://dashscope.aliyuncs.com/api/v1"

    messages = kwargs["messages"]
    assert isinstance(messages, list) and messages
    user_message = next(message for message in messages if message.get("role") == "user")
    audio_item = next(item for item in user_message["content"] if "audio" in item)
    prefix, encoded = audio_item["audio"].split(",", 1)
    assert prefix == "data:audio/wav;base64"
    assert base64.b64decode(encoded) == audio


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_successful_response("列表文本"), "列表文本"),
        (
            {
                "status_code": 200,
                "output": {
                    "choices": [{"message": {"content": {"text": "字典文本"}}}],
                },
            },
            "字典文本",
        ),
        (
            {
                "status_code": 200,
                "output": {
                    "choices": [{"message": {"content": "字符串文本"}}],
                },
            },
            "字符串文本",
        ),
        (
            SimpleNamespace(
                status_code=HTTPStatus.OK,
                output=SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=[{"text": "属性对象文本"}])
                        )
                    ]
                ),
            ),
            "属性对象文本",
        ),
    ],
)
def test_qwen_asr_defensively_extracts_text(monkeypatch, response, expected):
    qwen_asr = _load_qwen_asr(monkeypatch)
    _patch_sdk(monkeypatch, lambda *args, **kwargs: response)

    assert qwen_asr.asr_recognize(_wav_bytes())["text"] == expected


@pytest.mark.parametrize(
    ("audio", "api_key", "error_fragment"),
    [
        (b"", "unit-test-key", "empty"),
        (_wav_bytes(), None, "DASHSCOPE_API_KEY"),
        (b"\x00" * (_MAX_BASE64_WAV_BYTES + 1), "unit-test-key", "base64"),
        (b"\x00" * (_MAX_AUDIO_BYTES + 1), "unit-test-key", "10"),
    ],
)
def test_qwen_asr_rejects_invalid_input_without_calling_sdk(
    monkeypatch, audio, api_key, error_fragment
):
    qwen_asr = _load_qwen_asr(monkeypatch, api_key=api_key)
    called = False

    def fake_call(*args, **kwargs):
        nonlocal called
        called = True
        return _successful_response("不应调用")

    _patch_sdk(monkeypatch, fake_call)
    result = qwen_asr.asr_recognize(audio)

    assert result["text"] == ""
    assert isinstance(result.get("error"), str) and result["error"]
    assert error_fragment.lower() in result["error"].lower()
    assert called is False


def test_qwen_asr_converts_sdk_exception_to_error_result(monkeypatch):
    qwen_asr = _load_qwen_asr(monkeypatch)

    def fake_call(*args, **kwargs):
        raise RuntimeError("offline sdk failure")

    _patch_sdk(monkeypatch, fake_call)
    result = qwen_asr.asr_recognize(_wav_bytes())

    assert result["text"] == ""
    assert "offline sdk failure" in result["error"]


def test_qwen_asr_converts_non_200_response_to_error_result(monkeypatch):
    qwen_asr = _load_qwen_asr(monkeypatch)
    response = SimpleNamespace(
        status_code=HTTPStatus.BAD_REQUEST,
        code="InvalidParameter",
        message="bad ASR request",
        output=None,
    )
    _patch_sdk(monkeypatch, lambda *args, **kwargs: response)

    result = qwen_asr.asr_recognize(_wav_bytes())

    assert result["text"] == ""
    assert "bad ASR request" in result["error"]


def test_pcm_route_wraps_raw_samples_as_wav(client, dev_headers, monkeypatch):
    import routers.voice as voice_router

    captured = {}

    def fake_asr(audio_bytes, fmt="wav", sample_rate=16000):
        captured.update(audio=audio_bytes, fmt=fmt, sample_rate=sample_rate)
        return {"text": "PCM 识别成功"}

    monkeypatch.setattr(voice_router, "asr_recognize", fake_asr)
    pcm = b"\x01\x00\x02\x00\x03\x00\x04\x00"

    response = client.post(
        "/asr/recognize",
        json={
            "audio": base64.b64encode(pcm).decode("ascii"),
            "format": "pcm",
            "sample_rate": 16000,
        },
        headers=dev_headers,
    )

    assert response.status_code == 200
    assert response.json()["text"] == "PCM 识别成功"
    assert captured["fmt"] == "wav"
    assert captured["sample_rate"] == 16000
    assert captured["audio"].startswith(b"RIFF")
    with wave.open(io.BytesIO(captured["audio"]), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.readframes(wav_file.getnframes()) == pcm


def test_pcm_route_rejects_empty_audio_without_calling_asr(
    client, dev_headers, monkeypatch
):
    import routers.voice as voice_router

    called = False

    def fake_asr(*args, **kwargs):
        nonlocal called
        called = True
        return {"text": "不应调用"}

    monkeypatch.setattr(voice_router, "asr_recognize", fake_asr)
    response = client.post(
        "/asr/recognize",
        json={"audio": "", "format": "pcm", "sample_rate": 16000},
        headers=dev_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"text": "", "error": "empty audio"}
    assert called is False


def test_asr_request_rejects_oversized_base64_before_decode():
    from routers.voice import ASR_MAX_BASE64_CHARS, AsrRequest

    with pytest.raises(ValidationError):
        AsrRequest(audio="A" * (ASR_MAX_BASE64_CHARS + 1))


def test_non_pcm_route_asks_ffmpeg_for_wav(client, dev_headers, monkeypatch):
    import shutil
    import routers.voice as voice_router

    captured = {}
    converted_wav = _wav_bytes(b"\x05\x00\x06\x00")

    def fake_run(argv, **kwargs):
        captured["ffmpeg_argv"] = list(argv)
        with open(argv[-1], "wb") as output_file:
            output_file.write(converted_wav)
        return SimpleNamespace(returncode=0, stderr=b"")

    def fake_asr(audio_bytes, fmt="wav", sample_rate=16000):
        captured.update(audio=audio_bytes, fmt=fmt, sample_rate=sample_rate)
        return {"text": "Opus 识别成功"}

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda name: "/test-bin/ffmpeg")
    monkeypatch.setattr(voice_router, "asr_recognize", fake_asr)

    response = client.post(
        "/asr/recognize",
        json={
            "audio": base64.b64encode(b"fake webm/opus payload").decode("ascii"),
            "format": "opus",
            "sample_rate": 16000,
        },
        headers=dev_headers,
    )

    assert response.status_code == 200
    assert response.json()["text"] == "Opus 识别成功"
    argv = captured["ffmpeg_argv"]
    assert argv[argv.index("-ar") + 1] == "16000"
    assert argv[argv.index("-ac") + 1] == "1"
    assert argv[argv.index("-f") + 1] == "wav"
    assert "s16le" not in argv
    assert captured["audio"] == converted_wav
    assert captured["fmt"] == "wav"
    assert captured["sample_rate"] == 16000


def test_non_16k_pcm_route_resamples_from_declared_rate(
    client, dev_headers, monkeypatch
):
    import routers.voice as voice_router

    captured = {}
    converted_wav = _wav_bytes(b"\x07\x00\x08\x00")

    def fake_run(argv, **kwargs):
        with wave.open(argv[argv.index("-i") + 1], "rb") as input_file:
            captured["input_rate"] = input_file.getframerate()
        with open(argv[-1], "wb") as output_file:
            output_file.write(converted_wav)
        return SimpleNamespace(returncode=0, stderr=b"")

    def fake_asr(audio_bytes, fmt="wav", sample_rate=16000):
        captured.update(audio=audio_bytes, fmt=fmt, sample_rate=sample_rate)
        return {"text": "重采样成功"}

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(voice_router.shutil, "which", lambda name: "/test-bin/ffmpeg")
    monkeypatch.setattr(voice_router, "asr_recognize", fake_asr)

    response = client.post(
        "/asr/recognize",
        json={
            "audio": base64.b64encode(b"\x01\x00\x02\x00").decode("ascii"),
            "format": "pcm",
            "sample_rate": 8000,
        },
        headers=dev_headers,
    )

    assert response.status_code == 200
    assert response.json()["text"] == "重采样成功"
    assert captured["input_rate"] == 8000
    assert captured["audio"] == converted_wav
    assert captured["fmt"] == "wav"
    assert captured["sample_rate"] == 16000
