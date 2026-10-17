"""块 A：豆包语音 2.0 适配器的离线契约测试。

全部使用 ``httpx.MockTransport``（通过 monkeypatch ``_default_transport`` 注入）：
不联网，不读 .env，不使用真实 Key。覆盖参数映射、成功流拼接、错误分类，
并保证每次付费调用只发一个 POST、错误信息不含 Key。
"""
from __future__ import annotations

import asyncio
import base64
import json
import time

import httpx
import pytest

from studio import voices
from studio.providers import tts_doubao
from studio.providers.media_errors import MediaCallError


KEY = "test-volc-speech-key-not-real"
TEXT = "你还给的是官府。不是我。"
VOICE = "zh_female_sophie_uranus_bigtts"

DOUBAO_VOICES = [
    ("zh_female_vv_uranus_bigtts", "Vivi 2.0", "female", "语调平稳、咬字柔和、自带治愈安抚力"),
    ("zh_female_xiaohe_uranus_bigtts", "小何 2.0", "female", "声线甜美有活力"),
    ("zh_female_wenroumama_uranus_bigtts", "温柔妈妈 2.0", "female", "语调舒缓、咬字温润"),
    ("zh_female_sophie_uranus_bigtts", "魅力苏菲 2.0", "female", "高冷御姐，外冷内柔（官方标注指令遵循）"),
    ("zh_female_meilinvyou_uranus_bigtts", "魅力女友 2.0", "female", "成熟妩媚的御姐"),
    ("zh_male_wennuanahu_uranus_bigtts", "温暖阿虎 2.0", "male", "阳光温暖的少年音"),
    ("zh_male_jieshuoxiaoming_uranus_bigtts", "解说小明 2.0", "male", "明快、中气十足的解说男声"),
    ("zh_male_liufei_uranus_bigtts", "刘飞 2.0", "male", "逻辑清晰、理性稳重"),
    ("zh_male_shaonianzixin_uranus_bigtts", "少年梓辛 2.0", "male", "清爽少年感"),
    ("zh_male_taocheng_uranus_bigtts", "小天 2.0", "male", "清澈温润的男大学生"),
    ("zh_male_m191_uranus_bigtts", "云舟 2.0", "male", "磁性、成熟理性"),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def doubao_key(monkeypatch):
    monkeypatch.setenv(tts_doubao.API_KEY_ENV, KEY)
    monkeypatch.delenv(tts_doubao.RESOURCE_ENV, raising=False)
    return KEY


@pytest.fixture
def install_transport(monkeypatch):
    """把假传输装到模块级 ``_default_transport``，并记录每次请求。"""
    def install(handler):
        calls = []

        def wrapped(request):
            calls.append(request)
            return handler(request)

        monkeypatch.setattr(tts_doubao, "_default_transport",
                            lambda: httpx.MockTransport(wrapped))
        return calls

    return install


def chunk(payload: bytes) -> dict:
    return {"code": 0, "message": "", "data": base64.b64encode(payload).decode()}


def success(data=None) -> dict:
    return {"code": 20000000, "message": "success", "data": data}


def ndjson(*lines: dict) -> httpx.Response:
    body = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    return httpx.Response(200, content=body.encode("utf-8"))


async def call(**kwargs):
    params = {"voice": VOICE}
    params.update(kwargs)
    return await tts_doubao.synthesize_doubao(TEXT, **params)


def assert_single_post(calls):
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert str(calls[0].url) == tts_doubao.ENDPOINT


def assert_key_safe(message: str):
    assert KEY not in message


@pytest.mark.anyio
async def test_success_stream_collects_multiline_chunks(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(
        chunk(b"ID3"),
        chunk(b"-doubao-audio-"),
        success(),
    ))

    result = await call()

    assert_single_post(calls)
    assert result.audio == b"ID3-doubao-audio-"
    assert result.audio_format == "mp3"
    assert result.sample_rate == 24000
    assert result.engine == "doubao"
    assert result.voice == VOICE
    assert result.chars == len(TEXT)
    assert result.words == []

    request = calls[0]
    assert request.headers["X-Api-Key"] == KEY
    assert request.headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert request.headers["X-Api-Request-Id"]
    assert request.headers["Content-Type"] == "application/json"
    body = json.loads(request.content)
    assert body["user"] == {"uid": "fiona-studio"}
    assert body["req_params"]["text"] == TEXT
    assert body["req_params"]["speaker"] == VOICE
    assert body["req_params"]["audio_params"] == {
        "format": "mp3", "sample_rate": 24000, "speech_rate": 0,
    }


@pytest.mark.anyio
async def test_additions_is_json_string_with_direction_and_pitch(doubao_key, install_transport):
    direction = "  压低声音，不安里带着一点倔强，像在问自己  "
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    await call(rate=0.9, pitch=-2, direction=direction)

    assert_single_post(calls)
    body = json.loads(calls[0].content)
    additions = body["req_params"]["additions"]
    assert isinstance(additions, str)
    parsed = json.loads(additions)
    assert parsed["context_texts"] == ["压低声音，不安里带着一点倔强，像在问自己"]
    assert parsed["post_process"]["pitch"] == -2
    assert body["req_params"]["audio_params"]["speech_rate"] == -10


@pytest.mark.anyio
async def test_additions_omitted_when_no_direction_and_zero_pitch(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    await call(rate=1.0, pitch=0, direction="   ")

    assert_single_post(calls)
    body = json.loads(calls[0].content)
    assert "additions" not in body["req_params"]


@pytest.mark.anyio
async def test_zero_pitch_is_omitted_but_direction_kept(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    await call(pitch=0, direction="轻声说")

    parsed = json.loads(json.loads(calls[0].content)["req_params"]["additions"])
    assert parsed == {"context_texts": ["轻声说"]}


@pytest.mark.parametrize("rate,speech_rate", [
    (0.5, -50),
    (0.9, -10),
    (1.0, 0),
    (1.25, 25),
    (2.0, 100),
    (3.0, 100),   # 截到上限
    (0.1, -50),   # 截到下限
])
@pytest.mark.anyio
async def test_rate_conversion_and_clamp(doubao_key, install_transport, rate, speech_rate):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    await call(rate=rate)

    assert_single_post(calls)
    body = json.loads(calls[0].content)
    assert body["req_params"]["audio_params"]["speech_rate"] == speech_rate


@pytest.mark.parametrize("status,code", [
    (400, 45000000),
    (401, 45000010),
    (403, 45000030),
    (429, 45000600),
])
@pytest.mark.anyio
async def test_http_4xx_is_rejected(doubao_key, install_transport, status, code):
    calls = install_transport(lambda request: httpx.Response(
        status, json={"code": code, "message": "upstream refused"},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert exc.value.status == "rejected"
    assert exc.value.code == f"doubao_{code}"
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_http_4xx_without_json_body_is_rejected(doubao_key, install_transport):
    calls = install_transport(lambda request: httpx.Response(401, content=b"Unauthorized"))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("rejected", "doubao_http_401")
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_upstream_message_redacts_key(doubao_key, install_transport):
    calls = install_transport(lambda request: httpx.Response(
        401, json={"code": 45000010, "message": f"invalid api key: {KEY}"},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert exc.value.status == "rejected"
    assert_key_safe(exc.value.message)
    assert "[已隐藏]" in exc.value.message


@pytest.mark.anyio
async def test_http_5xx_is_uncertain(doubao_key, install_transport):
    calls = install_transport(lambda request: httpx.Response(
        500, json={"code": 55001309, "message": "internal error"},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert exc.value.status == "uncertain"
    assert exc.value.code == "doubao_55001309"
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_http_5xx_without_json_body_is_uncertain(doubao_key, install_transport):
    calls = install_transport(lambda request: httpx.Response(503, content=b"busy"))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_http_503")


@pytest.mark.anyio
async def test_body_code_45002001_is_rejected(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(
        {"code": 45002001, "message": "no readable text"},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("rejected", "doubao_45002001")
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_other_body_code_is_uncertain(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(
        {"code": 55001309, "message": "internal error"},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_55001309")


@pytest.mark.anyio
async def test_stream_without_success_code_is_uncertain(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(chunk(b"partial-audio")))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_incomplete_stream")


@pytest.mark.anyio
async def test_success_code_without_audio_is_uncertain(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(success()))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_empty_audio")


@pytest.mark.anyio
async def test_invalid_json_line_is_uncertain(doubao_key, install_transport):
    calls = install_transport(lambda request: httpx.Response(200, content=b"not-json\n"))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_invalid_response")


@pytest.mark.anyio
async def test_transport_error_is_uncertain(doubao_key, install_transport):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    calls = install_transport(handler)

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_transport_error")
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_httpx_timeout_is_uncertain(doubao_key, install_transport):
    def handler(request):
        raise httpx.ReadTimeout("read timed out")

    calls = install_transport(handler)

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_timeout")
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_total_timeout_is_uncertain(doubao_key, install_transport, monkeypatch):
    monkeypatch.setattr(tts_doubao, "SYNTHESIS_TIMEOUT_S", 0.05)

    async def handler(request):
        await asyncio.sleep(1.0)
        return ndjson(success())

    calls = install_transport(handler)

    started = time.monotonic()
    with pytest.raises(MediaCallError) as exc:
        await call()
    elapsed = time.monotonic() - started

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("uncertain", "doubao_timeout")
    assert elapsed < 0.9


@pytest.mark.anyio
async def test_missing_key_never_sends_request(monkeypatch, install_transport):
    monkeypatch.delenv(tts_doubao.API_KEY_ENV, raising=False)
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert calls == []
    assert (exc.value.status, exc.value.code) == ("rejected", "doubao_key_missing")
    assert_key_safe(exc.value.message)


@pytest.mark.anyio
async def test_direction_over_200_chars_raises_before_request(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    with pytest.raises(ValueError):
        await call(direction="字" * (tts_doubao.DIRECTION_MAX_CHARS + 1))

    assert calls == []


@pytest.mark.anyio
async def test_direction_exactly_200_chars_is_accepted(doubao_key, install_transport):
    direction = "字" * tts_doubao.DIRECTION_MAX_CHARS
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    await call(direction=direction)

    assert_single_post(calls)
    parsed = json.loads(json.loads(calls[0].content)["req_params"]["additions"])
    assert parsed["context_texts"] == [direction]


@pytest.mark.parametrize("pitch", [12.5, 13, -13, "1", True])
@pytest.mark.anyio
async def test_invalid_pitch_raises_before_request(doubao_key, install_transport, pitch):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    with pytest.raises(ValueError):
        await call(pitch=pitch)

    assert calls == []


@pytest.mark.parametrize("code", ["abc", "4.5", "45-000", "12345678901"])
@pytest.mark.anyio
async def test_invalid_upstream_code_becomes_doubao_unknown(doubao_key, install_transport, code):
    calls = install_transport(lambda request: httpx.Response(
        400, json={"code": code, "message": "bad request"},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert (exc.value.status, exc.value.code) == ("rejected", "doubao_unknown")


@pytest.mark.anyio
async def test_rejected_message_is_redacted_and_truncated_to_200(doubao_key, install_transport):
    message = f"invalid api key: {KEY} " + "错" * 500
    calls = install_transport(lambda request: httpx.Response(
        401, json={"code": 45000010, "message": message},
    ))

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert exc.value.status == "rejected"
    assert exc.value.code == "doubao_45000010"
    assert KEY not in exc.value.message
    assert "[已隐藏]" in exc.value.message
    assert len(exc.value.message) <= 200


@pytest.mark.parametrize("response", [
    lambda: httpx.Response(500, json={"code": 55001309, "message": "internal error"}),
    lambda: ndjson({"code": 55001309, "message": "internal error"}),
])
@pytest.mark.anyio
async def test_uncertain_message_is_shared_constant(doubao_key, install_transport, response):
    calls = install_transport(lambda request: response())

    with pytest.raises(MediaCallError) as exc:
        await call()

    assert_single_post(calls)
    assert exc.value.status == "uncertain"
    assert exc.value.message == tts_doubao.UNCERTAIN_MESSAGE


@pytest.mark.anyio
async def test_invalid_rate_is_a_pre_send_error(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    with pytest.raises(ValueError):
        await call(rate=float("nan"))

    assert calls == []


@pytest.mark.anyio
async def test_integral_float_pitch_is_accepted(doubao_key, install_transport):
    calls = install_transport(lambda request: ndjson(chunk(b"x"), success()))

    await call(pitch=3.0)

    assert_single_post(calls)
    parsed = json.loads(json.loads(calls[0].content)["req_params"]["additions"])
    assert parsed["post_process"]["pitch"] == 3


def test_doubao_configured(monkeypatch):
    monkeypatch.delenv(tts_doubao.API_KEY_ENV, raising=False)
    assert tts_doubao.doubao_configured() is False

    monkeypatch.setenv(tts_doubao.API_KEY_ENV, "   ")
    assert tts_doubao.doubao_configured() is False

    monkeypatch.setenv(tts_doubao.API_KEY_ENV, KEY)
    assert tts_doubao.doubao_configured() is True


def test_default_transport_is_none():
    assert tts_doubao._default_transport() is None


def test_voice_catalog_contains_doubao_entries():
    entries = voices.voices_for("doubao")
    assert len(entries) == 11
    assert [(entry["voice"], entry["label"], entry["gender"], entry["note"])
            for entry in entries] == DOUBAO_VOICES
    assert all(entry["engine"] == "doubao" and entry["lang"] == "zh"
               for entry in entries)
    assert voices.lookup_voice("doubao", VOICE)["label"] == "魅力苏菲 2.0"
    assert voices.lookup_voice("doubao", "longxiaoxia_v2") is None
