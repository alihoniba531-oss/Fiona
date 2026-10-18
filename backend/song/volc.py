"""火山引擎豆包音乐客户端（写歌 P0 只接火山）。

本模块只负责两件事：按火山 OpenAPI 的 HMAC-SHA256 规则签名，以及调用
``GenSongForTime`` / ``QuerySong`` 两个动作。密钥只在请求期间从环境变量读取，
不会写入日志、异常文案或持久化参数。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from . import config


HOST = "open.volcengineapi.com"
REGION = "cn-beijing"
SERVICE = "imagination"
API_VERSION = "2024-08-12"

SUBMIT_ACTION = "GenSongForTime"
QUERY_ACTION = "QuerySong"

# 付费响应只读这么多；超限按结果不确定处理，绝不重发 POST。
MAX_RESPONSE_BYTES = 1024 * 1024

_STATE_BY_STATUS = {
    0: "waiting",
    1: "running",
    2: "succeeded",
    3: "failed",
}


class _SubmitError(Exception):
    """提交失败的基类；只携带错误码字符串。"""

    def __init__(self, code: str):
        code = str(code)
        super().__init__(code)
        self.code = code


class SubmitRejected(_SubmitError):
    """付费 POST 得到确定的拒绝结果，可以确认没有创建任务。"""


class SubmitUncertain(_SubmitError):
    """付费 POST 结果不确定（超时、断连、5xx、坏 JSON 等），不得自动重试。"""


class PollError(Exception):
    """查询失败；调用方推迟下一次轮询。只携带错误码字符串。"""

    def __init__(self, code: str):
        code = str(code)
        super().__init__(code)
        self.code = code


class _TransportProblem(Exception):
    """内部错误：传输或读取阶段失败，由 submit / query 映射成各自异常。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _rfc3986(value: Any) -> str:
    """RFC3986 百分号编码；空格编码为 %20，斜线也编码。"""
    return quote(str(value), safe="-_.~")


def _canonical_query(query: dict[str, Any]) -> str:
    """参数按名称 ASCII 升序，逐个 RFC3986 编码后以 & 连接。"""
    pairs: list[str] = []
    for name in sorted(query):
        value = query[name]
        if isinstance(value, (list, tuple)):
            for item in value:
                pairs.append(f"{_rfc3986(name)}={_rfc3986(item)}")
        else:
            pairs.append(f"{_rfc3986(name)}={_rfc3986(value)}")
    return "&".join(pairs)


def _canonical_request(
    method: str,
    query: dict[str, Any],
    body: bytes,
    *,
    host: str,
    xdate: str,
) -> str:
    """构造火山签名规范的 CanonicalRequest（末尾不带换行）。"""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return "\n".join(
        (
            method.upper(),
            "/",
            _canonical_query(query),
            f"host:{host}",
            f"x-date:{xdate}",
            "",
            "host;x-date",
            hashlib.sha256(body).hexdigest(),
        )
    )


def _string_to_sign(
    *, xdate: str, region: str, service: str, canonical_hash: str
) -> str:
    scope = f"{xdate[:8]}/{region}/{service}/request"
    return "\n".join(("HMAC-SHA256", xdate, scope, canonical_hash))


def sign_request(
    method: str,
    query: dict,
    body: bytes,
    *,
    ak: str,
    sk: str,
    xdate: str,
    host: str,
    region: str,
    service: str,
) -> dict:
    """返回带鉴权信息的请求头；不包含任何密钥值（AK 标识符除外）。"""
    if isinstance(body, str):
        body = body.encode("utf-8")
    canonical = _canonical_request(method, query, body, host=host, xdate=xdate)
    canonical_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    string_to_sign = _string_to_sign(
        xdate=xdate,
        region=region,
        service=service,
        canonical_hash=canonical_hash,
    )

    date = xdate[:8]
    k_date = hmac.new(sk.encode("utf-8"), date.encode("ascii"), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"request", hashlib.sha256).digest()
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    scope = f"{date}/{region}/{service}/request"
    authorization = (
        f"HMAC-SHA256 Credential={ak}/{scope}, "
        "SignedHeaders=host;x-date, "
        f"Signature={signature}"
    )
    return {
        "Host": host,
        "X-Date": xdate,
        "Authorization": authorization,
        "Content-Type": "application/json",
    }


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _json_object(raw: bytes) -> dict | None:
    """解析 JSON 对象；非对象、坏 JSON 或特殊常量都视为无效。"""

    def _reject_constant(_value: str) -> None:
        raise ValueError("invalid_json_constant")

    try:
        data = json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, UnicodeError):
        return None
    return data if isinstance(data, dict) else None


def _utc_xdate() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class VolcMusicClient:
    """火山豆包音乐异步客户端。

    ``transport`` 仅供测试注入 ``httpx.MockTransport``；生产传 ``None``。
    付费 POST 每次只发一次，任何失败都不重试。
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def submit(self, params: dict) -> str:
        """提交生成任务；成功返回 TaskID。"""
        try:
            status, raw = await self._post(SUBMIT_ACTION, params, paid=True)
        except _TransportProblem as exc:
            if exc.code == "missing_credentials":
                raise SubmitRejected(exc.code) from None
            raise SubmitUncertain(exc.code) from None

        # 完整的 4xx 就是确定拒绝；不解析响应正文，避免正文影响分类。
        if 400 <= status < 500:
            raise SubmitRejected(f"HTTP_{status}")
        if not 200 <= status < 300:
            raise SubmitUncertain(f"HTTP_{status}")

        data = _json_object(raw)
        if data is None:
            raise SubmitUncertain("invalid_json")
        code = data.get("Code")
        if isinstance(code, bool) or not isinstance(code, int):
            raise SubmitUncertain("invalid_json")
        if code != 0:
            raise SubmitRejected(f"code_{code}")
        result = data.get("Result")
        task_id = result.get("TaskID") if isinstance(result, dict) else None
        if not isinstance(task_id, str) or not task_id.strip():
            raise SubmitUncertain("invalid_json")
        return task_id.strip()

    async def query(self, task_id: str) -> dict:
        """查询任务状态；调用方在 ``PollError`` 时推迟下一次轮询。"""
        try:
            status, raw = await self._post(
                QUERY_ACTION, {"TaskID": task_id}, paid=False
            )
        except _TransportProblem as exc:
            raise PollError(exc.code) from None

        if not 200 <= status < 300:
            raise PollError(f"HTTP_{status}")

        data = _json_object(raw)
        if data is None:
            raise PollError("invalid_json")
        code = data.get("Code")
        if isinstance(code, bool) or not isinstance(code, int):
            raise PollError("invalid_json")
        if code != 0:
            raise PollError(f"code_{code}")

        result = data.get("Result")
        if not isinstance(result, dict):
            raise PollError("invalid_json")
        status_value = result.get("Status")
        if isinstance(status_value, bool) or not isinstance(status_value, int):
            raise PollError("unexpected_status")
        state = _STATE_BY_STATUS.get(status_value)
        if state is None:
            raise PollError("unexpected_status")

        detail = result.get("SongDetail")
        if not isinstance(detail, dict):
            detail = {}

        audio_url = detail.get("AudioUrl")
        if not isinstance(audio_url, str) or not audio_url:
            audio_url = None

        failure_code: Any = None
        failure_msg: Any = None
        if state == "failed":
            reason = result.get("FailureReason")
            if isinstance(reason, dict):
                failure_code = reason.get("Code")
                failure_msg = reason.get("Msg")

        return {
            "state": state,
            "progress": _as_int(result.get("Progress"), 0),
            "audio_url": audio_url,
            "duration": _as_float(detail.get("Duration")),
            "captions_raw": detail.get("Captions"),
            "failure_code": failure_code,
            "failure_msg": failure_msg,
        }

    async def _post(
        self, action: str, payload: dict, *, paid: bool
    ) -> tuple[int, bytes]:
        """发一次 POST 并完整读取响应；只抛内部传输异常。"""
        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        query = {"Action": action, "Version": API_VERSION}
        ak, sk = config.volc_credentials()
        if not ak or not sk:
            raise _TransportProblem("missing_credentials")

        xdate = _utc_xdate()
        headers = sign_request(
            "POST",
            query,
            body,
            ak=ak,
            sk=sk,
            xdate=xdate,
            host=HOST,
            region=REGION,
            service=SERVICE,
        )
        url = f"https://{HOST}/?{_canonical_query(query)}"

        chunks = bytearray()
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(60 if paid else 20, connect=10),
            ) as client:
                async with client.stream(
                    "POST", url, content=body, headers=headers
                ) as response:
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise _TransportProblem("response_too_large")
                        chunks.extend(chunk)
                    declared = response.headers.get("content-length")
                    if declared is not None and not response.headers.get(
                        "content-encoding"
                    ):
                        try:
                            expected = int(declared)
                        except ValueError:
                            expected = None
                        if expected is not None and expected != len(chunks):
                            raise _TransportProblem("incomplete_response")
                    return response.status_code, bytes(chunks)
        except _TransportProblem:
            raise
        except Exception:
            # 不复制传输异常正文，避免把请求内容或凭据带进日志。
            raise _TransportProblem("transport_error") from None


__all__ = [
    "PollError",
    "SubmitRejected",
    "SubmitUncertain",
    "VolcMusicClient",
    "build_params",
    "sign_request",
]


def _join_option(values: Any, limit: int) -> str:
    if isinstance(values, str):
        items = [part.strip() for part in values.split(",") if part.strip()]
    elif isinstance(values, (list, tuple)):
        items = [str(part).strip() for part in values if str(part).strip()]
    else:
        items = []
    # 保存简报时已校验数量；这里再兜底一次，保证不发出超限参数。
    return ",".join(items[:limit])


def _add_option(params: dict, key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return
    params[key] = value


def build_params(project: dict, lyrics_check: dict, version_id: str) -> dict:
    """把项目简报与歌词自检结果冻结成火山提交参数（不含密钥）。"""
    brief = project.get("brief") or {}
    if isinstance(brief, str):
        try:
            brief = json.loads(brief)
        except (ValueError, TypeError):
            brief = {}
    if not isinstance(brief, dict):
        brief = {}

    params: dict[str, Any] = {
        "Lyrics": lyrics_check["provider_text"],
        "ModelVersion": "v4.3",
        "Duration": int(brief["duration_seconds"]),
        "Lang": brief["language"],
        "VodFormat": "mp3",
        "SkipCopyCheck": False,
        "AigcWatermark": config.song_explicit_watermark(),
        "ImplicitWaterMark": {
            "ContentProducer": config.aigc_producer(),
            "ProduceId": version_id,
            "Enable": True,
        },
    }

    # 顺序按官方文档：Genre、GenreExtra、Mood、Gender、Timbre、Key、Kmode、
    # Tempo、Instrument、Scene；冻结后的 params_json 更易核对。
    ordered_options = (
        ("Genre", "genre", 3, False),
        ("GenreExtra", "genre_extra", 2, False),
        ("Mood", "mood", 2, False),
        ("Gender", "gender", 0, True),
        ("Timbre", "timbre", 3, False),
        ("Key", "key", 0, True),
        ("Kmode", "kmode", 0, True),
        ("Tempo", "tempo", 0, True),
        ("Instrument", "instrument", 5, False),
        ("Scene", "scene", 3, False),
    )
    for param_name, brief_key, limit, scalar in ordered_options:
        if scalar:
            _add_option(params, param_name, brief.get(brief_key))
            continue
        joined = _join_option(brief.get(brief_key), limit)
        if joined:
            params[param_name] = joined
    return params
