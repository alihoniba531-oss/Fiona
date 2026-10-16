"""短片探针的独立基础设施；只读进程环境，绝不加载应用或 .env。"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid


ENV_NAMES = (
    "ARK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID",
    "SEED_AUDIO_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
)
MAX_MEDIA_BYTES = 300 * 1024 * 1024
MAX_JSON_BYTES = 420 * 1024 * 1024
UNCERTAIN_MESSAGE = "可能已扣费，请勿直接重试，去控制台核对"
EXIT_CODES = {"succeeded": 0, "succeeded_truncated": 0, "error": 1, "invalid_output": 1, "quoted": 2,
              "skipped": 3, "uncertain": 4, "rejected": 5, "still_running": 6, "stopped_budget": 7}
_TEXT_FIELDS = {"prompt", "text", "text_prompt", "scene_text", "label"}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:16]


def rounded_money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _redact_url(raw):
    try:
        parts = urlsplit(raw)
        def signed(key):
            return key.lower() in {
            "signature", "expires", "ossaccesskeyid", "security-token"
            } or key.lower().startswith(("x-tos-", "x-amz-"))
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if not any(signed(key) for key, _ in pairs):
            return raw
        query = [(key, "REDACTED" if signed(key) else value) for key, value in pairs]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except ValueError:
        return raw


def redact(value, secrets=(), *, preserve_text=False):
    """先处理结构，再清理嵌入消息中的密钥、签名和长内联数据。"""
    if isinstance(value, dict):
        return {redact(str(key), secrets, preserve_text=True):
                "REDACTED" if str(key).lower() in {"authorization", "x-api-key", "api-key"}
                else redact(item, secrets, preserve_text=str(key) in _TEXT_FIELDS)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets, preserve_text=preserve_text) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        return value
    if not preserve_text and len(value) > 200 and (
        value.lower().startswith("data:") or (
            not any(character.isspace() for character in value)
            and 100 * sum(1 for _ in re.finditer(r"[^A-Za-z0-9+/=_-]", value)) <= 5 * len(value)
        )
    ):
        return f"<base64 len={len(value)} sha256={hashlib.sha256(value.encode()).hexdigest()[:12]}>"
    result = re.sub(r"https?://[^\s<>\"']+", lambda match: _redact_url(match.group()), value, flags=re.IGNORECASE)
    if not preserve_text:
        def inline_data(match):
            token = match.group()
            return (f"<base64 len={len(token)} sha256={hashlib.sha256(token.encode()).hexdigest()[:12]}>"
                    if len(token) > 200 else token)
        result = re.sub(r"data:[^,\s]*,[A-Za-z0-9+/=_-]+", inline_data, result, flags=re.IGNORECASE)
    result = re.sub(r"(?i)([\"']?(?:authorization|x-api-key|api-key)[\"']?\s*[:=]\s*)"
                    r"(?:\"[^\"]*\"|'[^']*'|[^\r\n,;}]+)", r"\1REDACTED", result)
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        result = result.replace(secret, "REDACTED")
    return result


class ProbeFailure(Exception):
    """保留完整上游错误形状；只在输出边界脱敏。"""
    def __init__(self, status, message, *, code=None, http_status=None, response=None, exit_code=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.http_status = http_status
        self.response = response
        self.exit_code = EXIT_CODES.get(status, 1) if exit_code is None else exit_code


def error_details(data):
    if not isinstance(data, dict):
        return None, str(data)
    detail = data.get("error") or data.get("output") or data.get("header") or data
    if not isinstance(detail, dict):
        return None, str(detail)
    return (detail.get("code", detail.get("error_code", detail.get("type"))),
            detail.get("message", detail.get("error_message", "上游拒绝请求")))


def apply_failure(record, failure):
    record.update(status=failure.status, exit_code=failure.exit_code,
                  error={"code": failure.code, "message": str(failure), "http_status": failure.http_status})
    if failure.response is not None:
        record["error_response"] = failure.response


def _has_upstream_response(record):
    """只依据响应证据写夹具；请求体、报价和本地报错都不算上游响应。"""
    if not isinstance(record, dict):
        return False
    if any(record.get(key) is not None for key in (
        "response", "submission_response", "final_response", "error_response",
    )):
        return True
    if isinstance(record.get("error"), dict) and record["error"].get("http_status") is not None:
        return True
    # 语音接口可能只返回流式事件或音频，没有独立 JSON 响应。
    if record.get("events") or record.get("word_boundaries") or record.get("media_bytes", 0) > 0:
        return True
    return any(_has_upstream_response(item) for item in record.get("maps", [])) or _has_upstream_response(record.get("reduce"))


class Runtime:
    def __init__(self, *, backend_dir=None, environ=None, transport=None,
                 sleep=time.sleep, monotonic=time.monotonic, now=None, emit=print):
        self.backend_dir = Path(backend_dir) if backend_dir is not None else Path(__file__).resolve().parents[1]
        self.env = dict(os.environ if environ is None else environ)
        self.transport = transport
        self.sleep = sleep
        self.monotonic = monotonic
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._emit = emit
        self.last_record = None

    @property
    def secrets(self):
        # 发送时会 strip；上游回显发送值时也必须清理。
        raw = [self.env.get(name, "") for name in ENV_NAMES if name.endswith("_KEY")]
        secrets = {value for item in raw for value in (item, item.strip()) if value}
        workspace = self.env.get("DASHSCOPE_WORKSPACE_ID", "").strip()
        if len(workspace) >= 8:
            secrets.add(workspace)
        return sorted(secrets, key=len, reverse=True)

    def emit(self, text):
        self._emit(redact(str(text), self.secrets, preserve_text=True))

    def timestamp(self):
        return self.now().isoformat()

    def require_env(self, name):
        result = self.env.get(name, "").strip()
        if not result:
            raise ProbeFailure("error", f"未设置环境变量 {name}")
        return result

    def http_client(self, timeout=120):
        # 延迟导入；MockTransport 与生产路径使用相同的序列化和响应读取。
        import httpx
        return httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10),
                                                  write=min(timeout, 15), pool=min(timeout, 10)),
                            follow_redirects=False, trust_env=False, transport=self.transport)

    def paid_call(self, record, callback):
        """一次调用就是一次付费尝试；此函数没有循环或重试。"""
        record.setdefault("fingerprint", fingerprint(record.get("request", {}).get("body", record.get("request", {}))))
        started = self.monotonic()
        try:
            return callback()
        except ProbeFailure:
            raise
        except Exception as exc:
            # SDK 也可能在收到 2xx 后解析失败，此时无法断定是否已计费。
            status = getattr(exc, "status_code", None)
            response = getattr(exc, "response", None)
            if status is None and response is not None:
                status = getattr(response, "status_code", None)
            body = getattr(exc, "body", None)
            if status is not None:
                if body is None and response is not None:
                    try:
                        body = response.json()
                    except Exception:
                        body = {"message": str(exc)}
                code, message = error_details(body or {"message": str(exc)})
                uncertain = 200 <= status < 300
                if uncertain:
                    message = f"上游返回 HTTP {status}，SDK 处理响应失败：{exc}"
                raise ProbeFailure("uncertain" if uncertain else "rejected", message,
                                   code=code or type(exc).__name__, http_status=status, response=body) from None
            raise ProbeFailure("uncertain", str(exc), code=type(exc).__name__) from None
        finally:
            record["latency_s"] = round(self.monotonic() - started, 6)

    def _read_response(self, response, deadline=None):
        chunks = bytearray()
        for chunk in response.iter_bytes():
            if deadline is not None and self.monotonic() >= deadline:
                raise ProbeFailure("still_running", "轮询达到 25 分钟，保留 task_id 后可用 poll 续查")
            if len(chunks) + len(chunk) > MAX_JSON_BYTES:
                raise ValueError("响应超过大小上限，未读完")
            chunks.extend(chunk)
        return bytes(chunks)

    def _json_once(self, method, url, headers, body, timeout, paid, deadline=None):
        with self.http_client(timeout) as client:
            with client.stream(method, url, headers=headers,
                               content=json_bytes(body) if body is not None else None) as response:
                raw = self._read_response(response, deadline)
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeError):
                    data = {"message": raw.decode("utf-8", errors="replace")}
                    if 200 <= response.status_code < 300:
                        raise ProbeFailure("uncertain" if paid else "error", "响应不是有效 JSON", response=data) from None
                if not 200 <= response.status_code < 300:
                    code, message = error_details(data)
                    raise ProbeFailure("rejected", message, code=code,
                                       http_status=response.status_code, response=data)
                if not isinstance(data, dict):
                    raise ProbeFailure("uncertain" if paid else "error", "响应不是 JSON 对象", response=data)
                return data

    def post_json(self, url, body, headers, record, timeout=120):
        headers = {"Content-Type": "application/json", **headers}
        record["request"] = {"method": "POST", "url": url, "headers": headers, "body": body}
        record["request_bytes"] = len(json_bytes(body))
        result = self.paid_call(record, lambda: self._json_once("POST", url, headers, body, timeout, True))
        record["response"] = result
        return result

    def get_json(self, url, headers=None, timeout=30, deadline=None):
        import httpx
        for attempt in range(3):
            if deadline is not None and self.monotonic() >= deadline:
                raise ProbeFailure("still_running", "轮询达到 25 分钟，保留 task_id 后可用 poll 续查")
            remaining = timeout if deadline is None else min(timeout, max(.001, deadline - self.monotonic()))
            try:
                return self._json_once("GET", url, headers, None, remaining, False, deadline)
            except ProbeFailure as exc:
                if exc.http_status is not None and exc.http_status != 429 and exc.http_status < 500:
                    raise
                failure = exc
            except (httpx.TransportError, OSError, ValueError) as exc:
                failure = ProbeFailure("error", str(exc), code=type(exc).__name__)
            if attempt == 2:
                raise failure
            delay = 2 ** attempt
            if deadline is not None:
                delay = min(delay, max(0, deadline - self.monotonic()))
            self.sleep(delay)

    @property
    def media_dir(self):
        return self.backend_dir / "studio_data" / "_probe" / "media"

    def _media_target(self, suffix):
        self.media_dir.mkdir(parents=True, exist_ok=True)
        suffix = suffix if str(suffix).startswith(".") else "." + str(suffix)
        if not re.fullmatch(r"\.[a-zA-Z0-9_]+", suffix):
            raise ProbeFailure("error", "媒体扩展名无效")
        return self.media_dir / (uuid.uuid4().hex + suffix)

    def save_media(self, data, suffix, record):
        if not data or len(data) > MAX_MEDIA_BYTES:
            raise ProbeFailure("error", "媒体为空或超过 300MB")
        target = self._media_target(suffix)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.media_dir, suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        record.update(media_path=str(target), media_bytes=len(data))
        return target

    def download(self, url, suffix, record):
        import httpx
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ProbeFailure("error", "结果地址必须是没有用户凭据的 HTTP(S) URL")
        record.setdefault("result_hosts", []).append(parsed.hostname)
        target = self._media_target(suffix)
        for attempt in range(3):
            temporary = None
            try:
                # 不向结果 host 转发 API 密钥，不跟随任何 3xx。
                with self.http_client(120) as client, client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise ProbeFailure("error", "下载被拒绝或返回重定向", http_status=response.status_code)
                    declared = response.headers.get("content-length")
                    try:
                        length = None if declared is None else int(declared)
                    except ValueError:
                        raise ProbeFailure("error", "下载 Content-Length 无效") from None
                    if length is not None and not 0 < length <= MAX_MEDIA_BYTES:
                        raise ProbeFailure("error", "下载为空或超过 300MB")
                    total = 0
                    with tempfile.NamedTemporaryFile(dir=self.media_dir, suffix=".part", delete=False) as handle:
                        temporary = Path(handle.name)
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > MAX_MEDIA_BYTES:
                                raise ProbeFailure("error", "下载超过 300MB")
                            handle.write(chunk)
                    if not total or (length is not None and not response.headers.get("content-encoding") and total != length):
                        raise httpx.ReadError("下载未完整结束")
                temporary.replace(target)
                record.update(media_path=str(target), media_bytes=total)
                return target
            except ProbeFailure as exc:
                if exc.http_status != 429 and (exc.http_status is None or exc.http_status < 500):
                    raise
                failure = exc
            except (httpx.TransportError, ConnectionError, TimeoutError) as exc:
                failure = ProbeFailure("error", str(exc), code=type(exc).__name__)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise failure
            self.sleep(2 ** attempt)

    def probe_media(self, path):
        program = shutil.which("ffprobe")
        if program is None:
            return {"available": False, "error": "未安装 ffprobe，无法读取媒体参数"}
        try:
            completed = subprocess.run([
                program, "-v", "error", "-protocol_whitelist", "file,pipe", "-count_frames",
                "-show_streams", "-show_format", "-of", "json", str(Path(path).resolve()),
            ], capture_output=True, text=True, timeout=120, check=True)
            raw = json.loads(completed.stdout)
            streams = raw.get("streams", [])
            video = next((item for item in streams if item.get("codec_type") == "video"), {})
            audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
            rate = video.get("avg_frame_rate")
            if rate in (None, "0/0", "N/A"):
                rate = video.get("r_frame_rate")
            try:
                numerator, denominator = rate.split("/")
                fps = float(numerator) / float(denominator)
            except (TypeError, ValueError, AttributeError, ZeroDivisionError):
                fps = None
            return {"available": True, "width": video.get("width"), "height": video.get("height"),
                    "frame_rate": rate, "fps": fps, "nb_frames": video.get("nb_frames"),
                    "nb_read_frames": video.get("nb_read_frames"),
                    "duration": raw.get("format", {}).get("duration", video.get("duration", audio.get("duration"))),
                    "has_audio": bool(audio), "sample_rate": audio.get("sample_rate"),
                    "channels": audio.get("channels"), "bits_per_sample": audio.get("bits_per_sample"),
                    "format_name": raw.get("format", {}).get("format_name"), "raw": raw}
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return {"available": True, "error": f"ffprobe 读取失败：{type(exc).__name__}"}

    def image_data_uri(self, path):
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 30 * 1024 * 1024:
            raise ProbeFailure("error", "图片不存在、不是普通文件或超过 30MB")
        data = path.read_bytes()
        if not data:
            raise ProbeFailure("error", "图片为空")
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        if not mime.startswith("image/"):
            raise ProbeFailure("error", "不支持该图片格式")
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")

    def image_dimensions(self, path):
        with Path(path).open("rb") as handle:
            header = handle.read(24)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR" and len(header) >= 24:
            width, height = struct.unpack(">II", header[16:24])
            return {"width": width, "height": height}
        result = self.probe_media(path)
        return {"width": result.get("width"), "height": result.get("height"),
                **({"error": result["error"]} if "error" in result else {})}

    def persist(self, record):
        """每次运行写报告；只有收到上游响应才留夹具，且不覆盖旧夹具。"""
        safe = redact(record, self.secrets)
        output = self.backend_dir / "studio_data" / "_probe"
        output.mkdir(parents=True, exist_ok=True)
        safe.pop("fixture_path", None)
        if safe.get("probe") != "plan" and safe.get("status") != "quoted" and _has_upstream_response(record):
            fixtures = self.backend_dir / "tests" / "fixtures" / "studio"
            fixtures.mkdir(parents=True, exist_ok=True)
            stamp = self.now()
            name = re.sub(r"[^a-z0-9-]", "-", str(safe["probe"]).lower())
            # 同秒多次运行也不覆盖旧夹具，文件名仍保持规格格式。
            while True:
                destination = fixtures / f"{name}-{stamp:%Y%m%d-%H%M%S}.json"
                try:
                    with destination.open("x", encoding="utf-8") as handle:
                        safe["fixture_path"] = redact(str(destination), self.secrets, preserve_text=True)
                        json.dump(safe, handle, ensure_ascii=False, indent=2, allow_nan=False)
                        handle.write("\n")
                    break
                except FileExistsError:
                    stamp += timedelta(seconds=1)
        report = output / "report.jsonl"
        with report.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, ensure_ascii=False, allow_nan=False) + "\n")
        lines = ["# 短片工作室探针汇总", "", "费用为参考折算，以控制台账单为准。完整脱敏请求与响应保存在同目录 report.jsonl 和各次夹具中。", ""]
        def readable(value):
            return str(value).replace("\n", " ").replace("\r", " ").replace("`", "'")

        for raw in report.read_text(encoding="utf-8").splitlines():
            try:
                item = redact(json.loads(raw), self.secrets)
            except ValueError:
                continue
            lines.extend([f"## {item.get('timestamp', '')} · {item.get('probe', '')}", "",
                          f"标签：{readable(item.get('label', ''))}；状态：{item.get('status', '')}；退出码：{item.get('exit_code', '')}", "",
                          f"- 总耗时：{item.get('elapsed_s', '未知')} 秒"])
            estimate = item.get("quote", {})
            if estimate:
                lines.append(f"- 报价：{estimate.get('min_cny')}–{estimate.get('max_cny')} 元；{readable(estimate.get('note', ''))}")
            cost = item.get("total_cost", item.get("cost", {})).get("cny", item.get("actual_cost_cny"))
            lines.append(f"- 用量折算金额：{str(cost) + ' 元' if cost is not None else '未知（不以报价代替实际费用）'}")
            for key in ("stop_reason", "finish_reason"):
                if key in item:
                    lines.append(f"- 结束原因（{key}）：{readable(item[key])}")
            if item.get("truncation_note"):
                lines.append("- 输出状态：" + readable(item["truncation_note"]))
            if item.get("budget_note"):
                lines.append("- 花费限制：" + readable(item["budget_note"]))
            if item.get("uncertainty_note"):
                lines.append("- 计费提示：" + readable(item["uncertainty_note"]))
            if item.get("task_id"):
                lines.append(f"- 任务 ID：{readable(item['task_id'])}；轮询记录：{len(item.get('poll_history', []))} 次")
            if item.get("result_hosts"):
                lines.append("- 结果 host：" + "、".join(map(readable, item["result_hosts"])))
            if item.get("image_dimensions"):
                dimensions = item["image_dimensions"]
                lines.append(f"- 出图尺寸：{dimensions.get('width')}×{dimensions.get('height')}；参考图：{item.get('reference_image_count', 0)} 张；请求体：{item.get('request_bytes')} 字节")
            probe = item.get("ffprobe", {})
            if probe:
                lines.append(f"- 媒体：{probe.get('width')}×{probe.get('height')}；帧率 {probe.get('fps')}；"
                             f"帧数 {probe.get('nb_read_frames') or probe.get('nb_frames')}；时长 {probe.get('duration')} 秒；音轨 {probe.get('has_audio')}")
                if probe.get("error"):
                    lines.append("- 媒体检查：" + readable(probe["error"]))
            if "schema_valid" in item or "all_schema_valid" in item:
                lines.append(f"- JSON 合格：{item.get('json_valid', item.get('all_json_valid'))}；"
                             f"Schema 合格：{item.get('schema_valid', item.get('all_schema_valid'))}；"
                             f"镜头数：{item.get('shot_count', '不适用')}")
            if "chunk_count" in item:
                lines.append(f"- 原文块数：{item['chunk_count']}；失败块：{item.get('failed_chunks', [])}；"
                             f"分集数：{item.get('episode_count')}；分集秒数：{item.get('episode_seconds_distribution')}")
            if item.get("error"):
                lines.append("- 错误：" + readable(json.dumps(item["error"], ensure_ascii=False)))
            for key in ("timestamp_support", "duration_note", "actual_cost_note"):
                if item.get(key):
                    lines.append("- 说明：" + readable(item[key]))
            for note in item.get("reference_notes", []):
                lines.append("- 接口说明：" + readable(note))
            if item.get("fixture_path"):
                lines.append("- 夹具：" + readable(item["fixture_path"]))
            lines.append("")
        (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
        self.last_record = safe
        return safe
