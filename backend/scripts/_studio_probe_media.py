"""视频、图片和 Seed-Audio 探针；所有传输统一交给可替换的运行时。"""

from __future__ import annotations

import base64
import binascii
import math
import mimetypes
import re
import struct
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote as quote_url

from _studio_probe_common import ProbeFailure


DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-5-260628"
DEFAULT_SEEDREAM_MODEL = "doubao-seedream-5-0-flash-260915"
DEFAULT_SEED_AUDIO_MODEL = "seed-audio-1.0"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com"
SEED_AUDIO_URL = "https://openspeech.bytedance.com/api/v3/tts/create"
POLL_TIMEOUT = 25 * 60
POLL_INTERVAL = 10
WAN_PRICES = {"480P": 0.3, "720P": 0.6, "1080P": 1.2}
SEEDANCE_PRICE_PER_1K = 0.07
SEEDANCE_DISCOUNTED_PRICE_PER_1K = 0.05544
SEEDANCE_TOKENS_PER_SECOND = (21_600, 48_938)
_MAX_INLINE_MEDIA_BYTES = 300 * 1024 * 1024
_MAX_WAN_IMAGE_BYTES = 20 * 1024 * 1024


def _duration_range(value: int, minimum: int, provider: str) -> tuple[int, int]:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProbeFailure("error", f"{provider} 时长必须是整数。")
    if value == -1:
        return minimum, 30
    if not minimum <= value <= 30:
        raise ProbeFailure("error", f"{provider} 时长必须为 -1 或 {minimum}–30 秒。")
    return value, value


def quote(args: Any, rt: Any) -> dict:
    """仅做本地报价；报价阶段不读密钥、不读图片，也不进行任何传输。"""
    command = args.command
    if command == "wan":
        lower, upper = _duration_range(args.duration, 2, "万相")
        if args.resolution not in WAN_PRICES:
            raise ProbeFailure("error", "万相分辨率必须为 480P、720P 或 1080P。")
        price = WAN_PRICES[args.resolution]
        return {
            "min_cny": round(lower * price * 0.7, 6),
            "max_cny": round(upper * price, 6),
            "note": "按 video-catalog.ts 原价的七折到原价估算，prime 同价；以百炼账单为准。",
        }
    if command == "seedance":
        lower, upper = _duration_range(args.duration, 4, "Seedance")
        if args.resolution not in {"480p", "720p", "1080p"}:
            raise ProbeFailure("error", "Seedance 分辨率必须为 480p、720p 或 1080p。")
        return {
            "min_cny": round(lower * SEEDANCE_TOKENS_PER_SECOND[0] / 1000
                             * SEEDANCE_DISCOUNTED_PRICE_PER_1K, 6),
            "max_cny": round(upper * SEEDANCE_TOKENS_PER_SECOND[1] / 1000
                             * SEEDANCE_PRICE_PER_1K, 6),
            "note": "按规格的 21,600–48,938 tokens/秒估算，采用 cost.ts 的折后 "
                    "0.05544 到原价 0.07 元/千 tokens；与 config.ts 分辨率外推速率不同。"
                    "实际按 usage.completion_tokens 折算，以账单为准。",
        }
    if command == "seedream":
        return {"min_cny": 0.12, "max_cny": 0.6,
                "note": "按规格每张 0.12–0.60 元估算，本次生成一张；以账单为准。"}
    if command == "seed-audio":
        return {"min_cny": 1.0, "max_cny": 1.0,
                "note": "单价未知，以账单为准；1.00 元仅为人工确认门槛，不代表费用上限。"}
    if command == "poll":
        return {"min_cny": 0.0, "max_cny": 0.0, "note": "只读查询及下载，不提交生成请求。"}
    raise ProbeFailure("error", "未知的媒体探针。")


def _authorization(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _video_endpoint(provider: str, rt: Any) -> tuple[str, dict[str, str]]:
    if provider == "wan":
        key = rt.require_env("DASHSCOPE_API_KEY")
        workspace = rt.require_env("DASHSCOPE_WORKSPACE_ID")
        if not re.fullmatch(r"[A-Za-z0-9-]+", workspace):
            raise ProbeFailure("error", "DASHSCOPE_WORKSPACE_ID 只能包含字母、数字和连字符。")
        return f"https://{workspace}.cn-beijing.maas.aliyuncs.com", _authorization(key)
    return ARK_BASE_URL, _authorization(rt.require_env("ARK_API_KEY"))


def _error_details(data: dict) -> tuple[Any, str]:
    error = data.get("error")
    output = data.get("output")
    source = error if isinstance(error, dict) else output if isinstance(output, dict) else data
    code = source.get("code", data.get("code"))
    message = source.get("message", data.get("message"))
    if not message and isinstance(error, str):
        message = error
    return code, str(message or "上游未提供错误说明。")


def _reject_provider_error(data: dict) -> None:
    output = data.get("output")
    status = output.get("task_status") if isinstance(output, dict) else data.get("status")
    terminal_failure = str(status).lower() in {"failed", "error", "cancelled", "canceled", "expired"}
    if data.get("error") or data.get("code") not in (None, 0, "0", "") or terminal_failure:
        code, message = _error_details(data)
        raise ProbeFailure("rejected", message, code=code, response=data, exit_code=5)


def _billing_fields(data: dict) -> dict:
    """保留上游字段原名；不以本地预估值冒充上游账单。"""
    result = {}
    for key, value in data.items():
        if re.search(r"usage|bill|cost|charge", str(key), re.IGNORECASE):
            result[key] = value
    for container in ("output", "data", "result"):
        nested = data.get(container)
        if isinstance(nested, dict):
            fields = _billing_fields(nested)
            if fields:
                result[container] = fields
    return result


def _capture_response(data: dict, record: dict) -> None:
    record["response"] = data
    usage = data.get("usage")
    if usage is None and isinstance(data.get("output"), dict):
        usage = data["output"].get("usage")
    # 每次以最新响应为准，避免把运行中的临时用量误认为最终用量。
    record["usage"] = usage
    record["billing_fields"] = _billing_fields(data)


def _task_status(provider: str, data: dict) -> str:
    source = data.get("output", {}) if provider == "wan" else data
    if not isinstance(source, dict):
        return ""
    value = source.get("task_status" if provider == "wan" else "status")
    return str(value) if value is not None else ""


def _video_url(provider: str, data: dict) -> str | None:
    if provider == "wan":
        output = data.get("output")
        if isinstance(output, dict):
            for key in ("video_url", "watermark_video_url"):
                value = output.get(key)
                if isinstance(value, str) and value:
                    return value
        return None
    content = data.get("content")
    items = content if isinstance(content, list) else [content]
    for item in items:
        if isinstance(item, dict):
            for key in ("video_url", "url", "videoUrl"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    return value
    return None


def _video_dimensions(probe: dict) -> tuple[Any, Any]:
    if probe.get("width") and probe.get("height"):
        return probe["width"], probe["height"]
    for stream in probe.get("streams", []):
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            return stream.get("width"), stream.get("height")
    return None, None


def _record_actual_cost(provider: str, record: dict) -> None:
    usage = record.get("usage")
    if not isinstance(usage, dict):
        record["actual_cost_cny"] = None
        record["actual_cost_note"] = "上游未提供可折算的 usage，未以预估量代替实际用量。"
        return
    if provider == "seedance":
        tokens = usage.get("completion_tokens")
        record["completion_tokens"] = tokens
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
            record["actual_cost_cny"] = round(tokens / 1000 * SEEDANCE_PRICE_PER_1K, 8)
            record["actual_cost_note"] = "按上游 completion_tokens × 0.07 元/千 tokens 折算，最终以账单为准。"
            return
    elif provider == "wan":
        duration = usage.get("duration")
        resolution = ""
        for raw in (usage.get("SR"), record.get("resolution")):
            if isinstance(raw, float) and math.isfinite(raw) and raw.is_integer():
                raw = int(raw)
            candidate = str(raw).upper()
            candidate = candidate if candidate.endswith("P") else candidate + "P"
            if candidate in WAN_PRICES:
                resolution = candidate
                break
        if (isinstance(duration, (int, float)) and not isinstance(duration, bool)
                and math.isfinite(duration) and duration >= 0 and resolution in WAN_PRICES):
            record["actual_cost_cny"] = round(duration * WAN_PRICES[resolution], 8)
            record["actual_cost_note"] = "按上游 usage.duration 与 SR 的原价折算，最终以账单为准。"
            return
    record["actual_cost_cny"] = None
    record["actual_cost_note"] = "usage 缺少有效的计费量或分辨率，未推测实际费用。"


def _finish_video(provider: str, data: dict, rt: Any, record: dict) -> None:
    _record_actual_cost(provider, record)
    url = _video_url(provider, data)
    if url is None:
        raise ProbeFailure("error", "任务已完成，但响应没有视频地址；请保留 task_id 核对。", response=data)
    record["video_url"] = url
    path = rt.download(url, ".mp4", record)
    record["ffprobe"] = rt.probe_media(path)
    if provider == "wan":
        first = record.get("first_frame_dimensions", {})
        output_width, output_height = _video_dimensions(record["ffprobe"])
        comparison = {"input_ratio": None, "output_ratio": None, "match": None,
                      "relative_tolerance": 0.01}
        if first.get("width") and first.get("height"):
            comparison["input_ratio"] = first["width"] / first["height"]
        if output_width and output_height:
            comparison["output_ratio"] = output_width / output_height
        if comparison["input_ratio"] and comparison["output_ratio"]:
            comparison["match"] = math.isclose(comparison["input_ratio"], comparison["output_ratio"], rel_tol=0.01)
            comparison["note"] = "考虑视频像素取整，以相对误差不超过 1% 判断宽高比是否一致。"
        else:
            comparison["note"] = "缺少首帧或输出尺寸，无法比较；poll 单独运行没有原始首帧。"
        record["aspect_ratio_comparison"] = comparison
    record["status"] = "succeeded"


def _poll(provider: str, task_id: str, base: str, headers: dict, rt: Any, record: dict) -> None:
    """只读轮询；每次 GET 的有限重试由运行时处理，失败后不再循环重试。"""
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProbeFailure("error", "task_id 不能为空。")
    if provider == "wan" and not re.fullmatch(r"[A-Za-z0-9-]+", task_id):
        raise ProbeFailure("error", "万相 task_id 只能包含字母、数字和连字符。")
    path = "/api/v1/tasks/" if provider == "wan" else "/api/v3/contents/generations/tasks/"
    url = base + path + quote_url(task_id, safe="")
    record.update(provider=provider, task_id=task_id)
    history = record.setdefault("poll_history", [])
    deadline = rt.monotonic() + POLL_TIMEOUT
    while rt.monotonic() < deadline:
        remaining = deadline - rt.monotonic()
        if remaining <= 0:
            break
        try:
            data = rt.get_json(url, headers=headers, timeout=min(30, remaining), deadline=deadline)
        except ProbeFailure:
            if rt.monotonic() >= deadline:
                break
            raise
        _capture_response(data, record)
        status = _task_status(provider, data)
        history.append({"timestamp": rt.timestamp(), "status": status})
        _reject_provider_error(data)
        normalized = status.lower()
        if normalized in {"succeeded", "success", "completed", "done"}:
            _finish_video(provider, data, rt, record)
            return
        if normalized in {"failed", "error", "cancelled", "canceled", "expired"}:
            code, message = _error_details(data)
            raise ProbeFailure("rejected", f"视频任务状态为 {status}：{message}",
                               code=code, response=data, exit_code=5)
        if normalized not in {"pending", "queued", "running", "submitted", "unknown"}:
            raise ProbeFailure("error", "任务查询响应缺少有效状态，请用 task_id 核对。", response=data)
        remaining = deadline - rt.monotonic()
        if remaining > 0:
            rt.sleep(min(POLL_INTERVAL, remaining))
    raise ProbeFailure("still_running", "视频任务轮询达到 25 分钟上限，请用 poll 和 task_id 继续查询。",
                       exit_code=6)


def _prepare_wan_first_frame(path: str, rt: Any) -> tuple[str, dict[str, int]]:
    """在本地核对首帧，再用同一份字节构造请求，避免校验后重新读取文件。"""
    path = Path(path)
    try:
        if not path.is_file():
            raise ProbeFailure("error", "万相首帧不存在或不是普通文件。", exit_code=2)
        if path.stat().st_size > _MAX_WAN_IMAGE_BYTES:
            raise ProbeFailure("error", "万相首帧文件不能超过 20MB。", exit_code=2)
        with path.open("rb") as handle:
            data = handle.read(_MAX_WAN_IMAGE_BYTES + 1)
        if not data or len(data) > _MAX_WAN_IMAGE_BYTES:
            raise ProbeFailure("error", "万相首帧为空或超过 20MB。", exit_code=2)
        is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
        if is_png or path.suffix.lower() == ".png":
            if (not is_png or len(data) < 33 or data[8:12] != b"\0\0\0\r"
                    or data[12:16] != b"IHDR"):
                raise ProbeFailure("error", "万相首帧 PNG 文件头无效。", exit_code=2)
            width, height = struct.unpack(">II", data[16:24])
            if data[25] in {4, 6}:
                raise ProbeFailure("error", "万相首帧 PNG 有透明通道，请先去除透明。", exit_code=2)
            # tRNS 也能使灰度、真彩色或调色板 PNG 透明，不能只检查 IHDR。
            offset = 8
            while offset + 12 <= len(data):
                size = struct.unpack(">I", data[offset:offset + 4])[0]
                chunk_type = data[offset + 4:offset + 8]
                end = offset + size + 12
                if end > len(data):
                    raise ProbeFailure("error", "万相首帧 PNG 数据不完整。", exit_code=2)
                if chunk_type == b"tRNS":
                    raise ProbeFailure("error", "万相首帧 PNG 有透明信息，请先去除透明。", exit_code=2)
                offset = end
                if chunk_type == b"IEND":
                    break
            else:
                raise ProbeFailure("error", "万相首帧 PNG 数据不完整。", exit_code=2)
            dimensions = {"width": width, "height": height}
            mime = "image/png"
        else:
            dimensions = rt.image_dimensions(path)
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
        if not mime.startswith("image/"):
            raise ProbeFailure("error", "不支持该万相首帧图片格式。", exit_code=2)
        width, height = dimensions.get("width"), dimensions.get("height")
        if any(isinstance(side, bool) or not isinstance(side, int) or not 240 <= side <= 8000
               for side in (width, height)):
            raise ProbeFailure("error", "万相首帧宽高边长必须为 240–8000 像素。", exit_code=2)
        image = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
        return image, {"width": width, "height": height}
    except ProbeFailure as exc:
        if exc.exit_code == 2:
            raise
        raise ProbeFailure("error", f"万相首帧预检失败：{exc}", exit_code=2) from None
    except (OSError, ValueError, TypeError) as exc:
        raise ProbeFailure("error", f"万相首帧预检失败：{exc}", exit_code=2) from None


def _run_wan(args: Any, rt: Any, record: dict) -> None:
    image, dimensions = _prepare_wan_first_frame(args.image, rt)
    base, headers = _video_endpoint("wan", rt)
    record.update(provider="wan", model=args.model, prompt=args.prompt, resolution=args.resolution,
                  first_frame_dimensions=dimensions,
                  reference_notes=["首帧使用 input.media[{type:first_frame,url:data URI}]；prompt_extend 按规格显式关闭。"])
    body = {
        "model": args.model,
        "input": {"prompt": args.prompt, "media": [{"type": "first_frame", "url": image}]},
        "parameters": {"resolution": args.resolution, "ratio": args.ratio,
                       "duration": args.duration, "audio": args.audio,
                       "prompt_extend": False, "watermark": False},
    }
    headers["X-DashScope-Async"] = "enable"
    data = rt.post_json(base + "/api/v1/services/aigc/video-generation/video-synthesis",
                        body, headers, record, timeout=120)
    record["submission_response"] = data
    _capture_response(data, record)
    output = data.get("output")
    task_id = output.get("task_id") if isinstance(output, dict) else None
    if isinstance(task_id, str) and re.fullmatch(r"[A-Za-z0-9-]+", task_id):
        record["task_id"] = task_id
    if _task_status("wan", data):
        record.setdefault("poll_history", []).append({"timestamp": rt.timestamp(), "status": _task_status("wan", data)})
    _reject_provider_error(data)
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", task_id):
        raise ProbeFailure("uncertain", "提交响应缺少有效 task_id，无法确认任务是否创建。", response=data, exit_code=4)
    # 异步提交头只用于 POST，查询仍使用正常鉴权头。
    headers.pop("X-DashScope-Async")
    _poll("wan", task_id, base, headers, rt, record)


def _run_seedance(args: Any, rt: Any, record: dict) -> None:
    base, headers = _video_endpoint("seedance", rt)
    record.update(provider="seedance", model=args.model, prompt=args.prompt, resolution=args.resolution,
                  reference_notes=["create-video.ts 仍发送 ratio/camera_fixed；本探针按规格及 i2v_seedance.py 首帧实测写法省略这两项。",
                                   "报价 token 速率采用规格的 21,600–48,938，与 config.ts 按分辨率外推的数值不同。"])
    body = {
        "model": args.model,
        "content": [{"type": "text", "text": args.prompt},
                    {"type": "image_url", "image_url": {"url": rt.image_data_uri(args.image)}, "role": "first_frame"}],
        "duration": args.duration, "resolution": args.resolution,
        "generate_audio": args.generate_audio, "watermark": False,
    }
    data = rt.post_json(base + "/api/v3/contents/generations/tasks", body, headers, record, timeout=120)
    record["submission_response"] = data
    _capture_response(data, record)
    task_id = data.get("id") or data.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        record["task_id"] = task_id
    if _task_status("seedance", data):
        record.setdefault("poll_history", []).append({"timestamp": rt.timestamp(), "status": _task_status("seedance", data)})
    _reject_provider_error(data)
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProbeFailure("uncertain", "提交响应缺少有效任务 ID，无法确认任务是否创建。", response=data, exit_code=4)
    _poll("seedance", task_id, base, headers, rt, record)


def _decode_base64(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ProbeFailure("error", f"响应没有有效的 {label} base64 数据。")
    if len(value) > ((_MAX_INLINE_MEDIA_BYTES + 2) // 3) * 4:
        raise ProbeFailure("error", f"{label} 超过单文件 300MB 上限。")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ProbeFailure("error", f"响应中的 {label} base64 数据无效。") from None
    if not data or len(data) > _MAX_INLINE_MEDIA_BYTES:
        raise ProbeFailure("error", f"{label} 为空或超过单文件 300MB 上限。")
    return data


def _png_dimensions(data: bytes) -> dict[str, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ProbeFailure("error", "返回图片没有有效 PNG 文件头。")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height:
        raise ProbeFailure("error", "返回 PNG 的宽高无效。")
    return {"width": width, "height": height}


def _run_seedream(args: Any, rt: Any, record: dict) -> None:
    match = re.fullmatch(r"([1-9][0-9]*)[xX]([1-9][0-9]*)", args.size)
    if not match:
        raise ProbeFailure("error", "Seedream --size 必须为 WxH，例如 1024x1024。")
    width, height = map(int, match.groups())
    if not 1 / 16 <= width / height <= 16 or not 921_600 <= width * height <= 2048 * 2048:
        raise ProbeFailure("error", "Seedream 尺寸须符合 image_generation.py 的比例及像素范围。")
    references = list(args.ref or [])
    body = {"model": args.model, "prompt": args.prompt, "size": f"{width}x{height}",
            "response_format": "b64_json", "output_format": "png", "watermark": False}
    if references:
        images = [rt.image_data_uri(path) for path in references]
        body["image"] = images[0] if len(images) == 1 else images
    record.update(provider="seedream", model=args.model, prompt=args.prompt,
                  reference_image_count=len(references),
                  reference_notes=["默认采用 image_generation.py 中 Seedream 的 Flash 模型；config.ts 的 Seedream Pro 默认值不适用于本子命令。"])
    data = rt.post_json(ARK_BASE_URL + "/api/v3/images/generations", body,
                        _authorization(rt.require_env("ARK_API_KEY")), record, timeout=150)
    _capture_response(data, record)
    _reject_provider_error(data)
    images = data.get("data")
    first = images[0] if isinstance(images, list) and images and isinstance(images[0], dict) else {}
    _reject_provider_error(first)
    png = _decode_base64(first.get("b64_json"), "图片")
    record["image_dimensions"] = _png_dimensions(png)
    record["returned_image_count"] = len(images)
    path = rt.save_media(png, ".png", record)
    record["ffprobe"] = rt.probe_media(path)
    record["status"] = "succeeded"


def _detected_audio_format(data: bytes) -> str | None:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"OggS":
        return "ogg_opus" if b"OpusHead" in data[:128] else "ogg"
    if data[:3] == b"ID3" or len(data) >= 2 and data[0] == 255 and data[1] & 0xE0 == 0xE0:
        return "mp3"
    return None


def _run_seed_audio(args: Any, rt: Any, record: dict) -> None:
    if args.duration <= 0:
        raise ProbeFailure("error", "Seed-Audio 目标时长必须大于 0。")
    if args.format not in {"wav", "mp3", "pcm", "ogg_opus"}:
        raise ProbeFailure("error", "Seed-Audio 格式必须为 wav、mp3、pcm 或 ogg_opus。")
    record.update(provider="seed-audio", model=DEFAULT_SEED_AUDIO_MODEL, prompt=args.prompt,
                  kind=args.kind, target_duration_s=args.duration, requested_format=args.format,
                  duration_supported=False,
                  duration_note="不支持独立 duration 参数；--duration 仅记录目标时长标签，提示词原样发送。",
                  actual_cost_cny=None, actual_cost_note="单价未知，以账单为准。",
                  reference_notes=["实际字段为 text_prompt/audio_config/watermark，kind 与 duration 不发送。",
                                   "严格使用 SEED_AUDIO_API_KEY，不采用 config.ts 的 ARK 密钥回退。"])
    body = {
        "model": DEFAULT_SEED_AUDIO_MODEL,
        "text_prompt": args.prompt,
        "audio_config": {"format": args.format, "sample_rate": 48_000,
                         "speech_rate": 0, "pitch_rate": 0, "loudness_rate": 0,
                         "enable_subtitle": True},
        "watermark": {},
    }
    headers = {"X-Api-Key": rt.require_env("SEED_AUDIO_API_KEY"),
               "X-Api-Request-Id": str(uuid.uuid4()), "Content-Type": "application/json"}
    data = rt.post_json(SEED_AUDIO_URL, body, headers, record, timeout=300)
    _capture_response(data, record)
    _reject_provider_error(data)
    record["provider_duration_s"] = data.get("duration")
    record["provider_original_duration_s"] = data.get("original_duration")
    suffix = ".ogg" if args.format == "ogg_opus" else "." + args.format
    detected = None
    if isinstance(data.get("audio"), str) and data["audio"]:
        audio = _decode_base64(data["audio"], "音频")
        detected = _detected_audio_format(audio)
        path = rt.save_media(audio, suffix, record)
    elif isinstance(data.get("url"), str) and data["url"]:
        record["audio_url"] = data["url"]
        path = rt.download(data["url"], suffix, record)
    else:
        raise ProbeFailure("error", "音频生成响应没有 audio 或 url。", response=data)
    probe = rt.probe_media(path)
    record["ffprobe"] = probe
    format_section = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    record["returned_format"] = detected or probe.get("format_name") or format_section.get("format_name") or data.get("format") or "未知"
    record["duration_s"] = probe.get("duration_s", probe.get("duration", format_section.get("duration")))
    record["status"] = "succeeded"


def run(args: Any, rt: Any, record: dict) -> None:
    """由入口在报价确认后调用；每个生成分支只有一个付费 POST 调用点。"""
    handlers = {"wan": _run_wan, "seedance": _run_seedance, "seedream": _run_seedream,
                "seed-audio": _run_seed_audio}
    if args.command == "poll":
        base, headers = _video_endpoint(args.provider, rt)
        _poll(args.provider, args.task_id, base, headers, rt, record)
        return
    handler = handlers.get(args.command)
    if handler is None:
        raise ProbeFailure("error", "未知的媒体探针。")
    handler(args, rt, record)
