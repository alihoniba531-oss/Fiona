"""火山豆包音乐客户端的离线契约测试。

所有网络交互都走 ``httpx.MockTransport``；测试不读取仓库外文件，也不访问
真实火山接口。签名用例使用 01-brief §3.1 的官方固定向量。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

import httpx
import pytest

from song.volc import (
    MAX_RESPONSE_BYTES,
    PollError,
    SubmitRejected,
    SubmitUncertain,
    VolcMusicClient,
    _canonical_request,
    build_params,
    sign_request,
)


# 官方文档公开的示例值，不是真实密钥。
VECTOR_AK = "AKEXAMPLEPLACEHOLDER"
VECTOR_SK = "WkRZeE1EQmxPVGhsWWpWak5HVmtNbUUxTXpZeU9UVXlOMlE1TmpZeVlqTQ=="
VECTOR_HOST = "billing.volcengineapi.com"
VECTOR_XDATE = "20250329T180937Z"


@pytest.fixture(autouse=True)
def _song_dir(tmp_path, monkeypatch):
    """硬性要求：任何新测试都把写歌目录指到临时目录，且不产生文件。"""
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "songs"))
    # 假凭据；客户端只用于本地 MockTransport，不会访问真实网络。
    monkeypatch.setenv("VOLC_MUSIC_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLC_MUSIC_SECRET_KEY", "test-sk")
    monkeypatch.delenv("FIONA_SONG_EXPLICIT_WATERMARK", raising=False)
    monkeypatch.delenv("FIONA_AIGC_PRODUCER", raising=False)


def _signature(headers: dict) -> str:
    return headers["Authorization"].rsplit("Signature=", 1)[1]


def _run_submit(handler, params: dict | None = None) -> str:
    client = VolcMusicClient(httpx.MockTransport(handler))
    return asyncio.run(client.submit(params if params is not None else {"Lyrics": "hello"}))


def _run_query(handler, task_id: str = "task-1") -> dict:
    client = VolcMusicClient(httpx.MockTransport(handler))
    return asyncio.run(client.query(task_id))


# ---------------------------------------------------------------------------
# 签名固定向量
# ---------------------------------------------------------------------------


def test_sign_request_matches_official_post_vector():
    query = {"Action": "ListBill", "Version": "2022-01-01"}
    body = b'{"Limit":10,"BillPeriod":"2023-08"}'
    canonical = _canonical_request("POST", query, body, host=VECTOR_HOST, xdate=VECTOR_XDATE)
    assert (
        hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        == "27383e3b56d03850f5634483527fbddcbf06cf98de1bc8a6679ef2300bff3b15"
    )

    headers = sign_request(
        "POST",
        query,
        body,
        ak=VECTOR_AK,
        sk=VECTOR_SK,
        xdate=VECTOR_XDATE,
        host=VECTOR_HOST,
        region="cn-beijing",
        service="billing",
    )
    assert headers["Host"] == VECTOR_HOST
    assert headers["X-Date"] == VECTOR_XDATE
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"] == (
        f"HMAC-SHA256 Credential={VECTOR_AK}/20250329/cn-beijing/billing/request, "
        "SignedHeaders=host;x-date, "
        "Signature=5e8480ceea12d0000a23c054151c50dd02c1a7dec835004057d19f13d53a7658"
    )


def test_sign_request_matches_official_get_vector():
    query = {"Action": "QueryBalanceAcct", "Version": "2022-01-01"}
    body = b""
    canonical = _canonical_request("GET", query, body, host=VECTOR_HOST, xdate=VECTOR_XDATE)
    assert (
        hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        == "43171c1658c64b5db55c58d54988a4598d2d09a5613136beaa5eef40eae6e2c1"
    )

    headers = sign_request(
        "GET",
        query,
        body,
        ak=VECTOR_AK,
        sk=VECTOR_SK,
        xdate=VECTOR_XDATE,
        host=VECTOR_HOST,
        region="cn-beijing",
        service="billing",
    )
    assert headers["Authorization"] == (
        f"HMAC-SHA256 Credential={VECTOR_AK}/20250329/cn-beijing/billing/request, "
        "SignedHeaders=host;x-date, "
        "Signature=1eda9e7e6b1728151a8e8791fdaf67cfbd28bd5c80d0fce2eb208746cf483105"
    )


def test_changing_body_changes_canonical_hash_and_signature():
    query = {"Action": "ListBill", "Version": "2022-01-01"}
    body = b'{"Limit":10,"BillPeriod":"2023-08"}'
    changed = b'{"Limit":11,"BillPeriod":"2023-08"}'

    canonical = _canonical_request("POST", query, body, host=VECTOR_HOST, xdate=VECTOR_XDATE)
    changed_canonical = _canonical_request(
        "POST", query, changed, host=VECTOR_HOST, xdate=VECTOR_XDATE
    )
    assert canonical != changed_canonical
    assert hashlib.sha256(canonical.encode()).hexdigest() != hashlib.sha256(
        changed_canonical.encode()
    ).hexdigest()

    def headers(payload: bytes) -> dict:
        return sign_request(
            "POST",
            query,
            payload,
            ak=VECTOR_AK,
            sk=VECTOR_SK,
            xdate=VECTOR_XDATE,
            host=VECTOR_HOST,
            region="cn-beijing",
            service="billing",
        )

    assert _signature(headers(body)) != _signature(headers(changed))


def test_canonical_query_is_sorted_and_rfc3986_encoded():
    canonical = _canonical_request(
        "GET",
        {"Version": "2022-01-01", "Action": "A B", "Z": "/"},
        b"",
        host=VECTOR_HOST,
        xdate=VECTOR_XDATE,
    )
    # Action < Version < Z，空格 %20、斜线 %2F。
    assert "\nAction=A%20B&Version=2022-01-01&Z=%2F\n" in canonical


# ---------------------------------------------------------------------------
# 提交分类
# ---------------------------------------------------------------------------


def test_submit_success_returns_task_id_and_signs_request():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Message": "success",
                "Result": {"TaskID": "2024-task-1", "PredictedWaitTime": 0},
                "ResponseMetadata": {"Error": None},
            },
        )

    task_id = _run_submit(handler, {"Lyrics": "[verse]\n你好"})

    assert task_id == "2024-task-1"
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://open.volcengineapi.com/?Action=GenSongForTime&Version=2024-08-12"
    )
    assert request.headers["Host"] == "open.volcengineapi.com"
    assert re.fullmatch(r"\d{8}T\d{6}Z", request.headers["X-Date"])
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Authorization"].startswith(
        "HMAC-SHA256 Credential="
    )
    assert "/cn-beijing/imagination/request" in request.headers["Authorization"]
    assert "SignedHeaders=host;x-date" in request.headers["Authorization"]
    # 请求体是紧凑 JSON，且不含任何密钥。
    assert json.loads(request.content) == {"Lyrics": "[verse]\n你好"}
    assert "test-sk" not in request.headers["Authorization"]


@pytest.mark.parametrize("status", [400, 401, 404, 429])
def test_submit_complete_4xx_is_rejected_without_leaking_body(status):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json={"Code": status, "Message": "do-not-leak-this-body"},
        )

    with pytest.raises(SubmitRejected) as info:
        _run_submit(handler)

    assert info.value.code == f"HTTP_{status}"
    assert str(info.value) == f"HTTP_{status}"
    assert "do-not-leak-this-body" not in str(info.value)
    assert len(calls) == 1


def test_submit_http_200_nonzero_code_is_rejected():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"Code": 1001, "Message": "bad params"})

    with pytest.raises(SubmitRejected) as info:
        _run_submit(handler)

    assert info.value.code == "code_1001"
    assert str(info.value) == "code_1001"
    assert "bad params" not in str(info.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("connect slow"),
        httpx.RemoteProtocolError("disconnected"),
        httpx.ReadError("connection reset"),
    ],
)
def test_submit_timeout_or_disconnect_is_uncertain(error):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise error

    with pytest.raises(SubmitUncertain) as info:
        _run_submit(handler)

    assert info.value.code == "transport_error"
    assert str(info.value) == "transport_error"
    assert len(calls) == 1


@pytest.mark.parametrize("status", [500, 502, 503])
def test_submit_5xx_is_uncertain(status):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, text="upstream-body")

    with pytest.raises(SubmitUncertain) as info:
        _run_submit(handler)

    assert info.value.code == f"HTTP_{status}"
    assert "upstream-body" not in str(info.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"{not-json"),
        httpx.Response(200, content=b""),
        httpx.Response(200, content=b"[]"),
    ],
)
def test_submit_bad_json_is_uncertain(response):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response

    with pytest.raises(SubmitUncertain) as info:
        _run_submit(handler)

    assert info.value.code == "invalid_json"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"Code": 0},
        {"Code": 0, "Result": {}},
        {"Code": 0, "Result": {"TaskID": ""}},
        {"Code": 0, "Result": {"TaskID": 123}},
    ],
)
def test_submit_http_200_without_task_id_is_uncertain(payload):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    with pytest.raises(SubmitUncertain) as info:
        _run_submit(handler)

    assert info.value.code == "invalid_json"
    assert len(calls) == 1


def test_submit_response_over_one_mib_is_not_retried():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))

    with pytest.raises(SubmitUncertain) as info:
        _run_submit(handler)

    assert info.value.code == "response_too_large"
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# 查询结果与错误
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "progress", "state"),
    [
        (0, 0, "waiting"),
        (1, 37, "running"),
        (2, 100, "succeeded"),
        (3, 80, "failed"),
    ],
)
def test_query_maps_four_statuses(status, progress, state):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == (
            "https://open.volcengineapi.com/?Action=QuerySong&Version=2024-08-12"
        )
        assert json.loads(request.content) == {"TaskID": "task-1"}
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Message": "success",
                "Result": {
                    "TaskID": "task-1",
                    "Status": status,
                    "Progress": progress,
                    "FailureReason": (
                        {"Code": 300061, "Msg": "InputLyricsPlagiarized"}
                        if status == 3
                        else None
                    ),
                },
            },
        )

    result = _run_query(handler)

    assert result["state"] == state
    assert result["progress"] == progress
    assert result["audio_url"] is None
    assert result["duration"] is None
    assert result["captions_raw"] is None
    if state == "failed":
        assert result["failure_code"] == 300061
        assert result["failure_msg"] == "InputLyricsPlagiarized"
    else:
        assert result["failure_code"] is None
        assert result["failure_msg"] is None


def test_query_succeeded_reads_song_detail_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Result": {
                    "TaskID": "task-1",
                    "Status": 2,
                    "Progress": 100,
                    "SongDetail": {
                        "AudioUrl": "https://v3-default.douyinvod.com/audio.mp3?token=x",
                        "Duration": 187.5,
                        "Captions": "{}",
                        "Lyrics": "[verse]\nhello",
                    },
                    "FailureReason": None,
                },
            },
        )

    result = _run_query(handler)

    assert result["state"] == "succeeded"
    assert result["progress"] == 100
    assert result["audio_url"] == "https://v3-default.douyinvod.com/audio.mp3?token=x"
    assert result["duration"] == 187.5
    assert isinstance(result["duration"], float)
    assert result["captions_raw"] == "{}"
    assert result["failure_code"] is None
    assert result["failure_msg"] is None


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ({"Captions": "{}", "Duration": 60.0}, "{}"),
        ({"Captions": '{"sentences": [{"text": "hi"}]}', "Duration": 61.0}, '{"sentences": [{"text": "hi"}]}'),
        ({"Duration": 62}, None),
        ({"Captions": "", "Duration": 63}, ""),
    ],
)
def test_query_keeps_captions_raw_unparsed(detail, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Result": {
                    "Status": 2,
                    "Progress": 100,
                    "SongDetail": detail,
                    "FailureReason": None,
                },
            },
        )

    result = _run_query(handler)

    assert result["captions_raw"] == expected
    assert isinstance(result["duration"], float)


def test_query_failed_uses_failure_reason_code_and_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Result": {
                    "Status": 3,
                    "Progress": 45,
                    "SongDetail": {},
                    "FailureReason": {"Code": "300061", "Msg": "InputLyricsPlagiarized"},
                },
            },
        )

    result = _run_query(handler)

    assert result["state"] == "failed"
    assert result["failure_code"] == "300061"
    assert result["failure_msg"] == "InputLyricsPlagiarized"


@pytest.mark.parametrize("status", [400, 404, 429, 500, 503])
def test_query_http_error_is_poll_error(status):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"Code": status, "Message": "nope"})

    with pytest.raises(PollError) as info:
        _run_query(handler)

    assert info.value.code == f"HTTP_{status}"
    assert str(info.value) == f"HTTP_{status}"
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"{bad", b"", b"[]", b"null"])
def test_query_bad_json_is_poll_error(body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with pytest.raises(PollError) as info:
        _run_query(handler)

    assert info.value.code == "invalid_json"


@pytest.mark.parametrize("status", [9, -1, "2", [2], None, True])
def test_query_unexpected_status_is_poll_error(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Code": 0, "Result": {"Status": status, "Progress": 0}}
        )

    with pytest.raises(PollError) as info:
        _run_query(handler)

    assert info.value.code == "unexpected_status"


def test_query_transport_error_is_poll_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(PollError) as info:
        _run_query(handler)

    assert info.value.code == "transport_error"


def test_query_nonzero_code_is_poll_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Code": 1001, "Message": "bad"})

    with pytest.raises(PollError) as info:
        _run_query(handler)

    assert info.value.code == "code_1001"


def test_query_response_over_one_mib_is_poll_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))

    with pytest.raises(PollError) as info:
        _run_query(handler)

    assert info.value.code == "response_too_large"


# ---------------------------------------------------------------------------
# build_params
# ---------------------------------------------------------------------------


def _project(brief: dict) -> dict:
    return {
        "id": "project-1",
        "owner_username": "owner",
        "conversation_id": "conversation-1",
        "title": "测试歌曲",
        "brief": brief,
        "structure": [],
    }


def test_build_params_required_fields(monkeypatch):
    monkeypatch.setenv("FIONA_SONG_EXPLICIT_WATERMARK", "1")
    monkeypatch.delenv("FIONA_AIGC_PRODUCER", raising=False)
    project = _project({"language": "Chinese", "duration_seconds": 180})
    check = {"provider_text": "[verse]\n你好\n[chorus]\n你好"}

    params = build_params(project, check, "version-abc")

    assert params["Lyrics"] == "[verse]\n你好\n[chorus]\n你好"
    assert params["ModelVersion"] == "v4.3"
    assert params["Duration"] == 180
    assert isinstance(params["Duration"], int)
    assert params["Lang"] == "Chinese"
    assert params["VodFormat"] == "mp3"
    assert params["SkipCopyCheck"] is False
    assert params["AigcWatermark"] is True
    assert params["ImplicitWaterMark"] == {
        "ContentProducer": "Fiona",
        "ProduceId": "version-abc",
        "Enable": True,
    }
    for optional in ("Genre", "GenreExtra", "Mood", "Gender", "Timbre", "Key", "Kmode", "Tempo", "Instrument", "Scene"):
        assert optional not in params
    # 只给人看的字段不得传给火山。
    assert "style_notes" not in params
    assert "theme" not in params


def test_build_params_optional_values_are_comma_joined(monkeypatch):
    monkeypatch.setenv("FIONA_SONG_EXPLICIT_WATERMARK", "0")
    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "测试出品")
    project = _project(
        {
            "language": "English",
            "duration_seconds": 200,
            "genre": ["Pop", "Rock", "Jazz"],
            "genre_extra": ["Chinese Style", "GuFeng Music"],
            "mood": ["Happy", "Warm/Kind"],
            "gender": "Female",
            "timbre": ["Warm", "Gentle", "Bright"],
            "key": "A#",
            "kmode": "Minor",
            "tempo": "Allegro",
            "instrument": ["Flute", "Cello", "Strings", "Drums", "Bass"],
            "scene": ["Birthday", "Wedding", "Travel"],
            "style_notes": "不要外传",
        }
    )
    check = {"provider_text": "[verse]\nhello"}

    params = build_params(project, check, "version-xyz")

    assert params["Duration"] == 200
    assert params["Lang"] == "English"
    assert params["Genre"] == "Pop,Rock,Jazz"
    assert params["GenreExtra"] == "Chinese Style,GuFeng Music"
    assert params["Mood"] == "Happy,Warm/Kind"
    assert params["Gender"] == "Female"
    assert params["Timbre"] == "Warm,Gentle,Bright"
    assert params["Key"] == "A#"
    assert params["Kmode"] == "Minor"
    assert params["Tempo"] == "Allegro"
    assert params["Instrument"] == "Flute,Cello,Strings,Drums,Bass"
    assert params["Scene"] == "Birthday,Wedding,Travel"
    assert params["AigcWatermark"] is False
    assert params["ImplicitWaterMark"]["ContentProducer"] == "测试出品"
    assert params["ImplicitWaterMark"]["ProduceId"] == "version-xyz"
    assert "不要外传" not in json.dumps(params, ensure_ascii=False)


def test_build_params_never_contains_credentials(monkeypatch):
    monkeypatch.setenv("VOLC_MUSIC_ACCESS_KEY", "AK-should-never-appear")
    monkeypatch.setenv("VOLC_MUSIC_SECRET_KEY", "SK-should-never-appear")
    project = _project({"language": "Cantonese", "duration_seconds": 90})
    check = {"provider_text": "[verse]\n你好"}

    params = build_params(project, check, "version-1")
    serialized = json.dumps(params, ensure_ascii=False)

    assert "AK-should-never-appear" not in serialized
    assert "SK-should-never-appear" not in serialized
    upper_keys = {str(key).upper() for key in params}
    assert not any("SECRET" in key or "ACCESS" in key for key in upper_keys)


def test_submit_4xx_with_non_json_body_is_still_rejected():
    """4xx 的判定只看完整状态码，不要求错误体是 JSON。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"rate limited")

    with pytest.raises(SubmitRejected) as info:
        _run_submit(handler)

    assert info.value.code == "HTTP_429"
