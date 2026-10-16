"""Seedance 2.5：提交时在内存中按输出分辨率缩小首帧。"""
from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from .base import (
    UNCERTAIN_MESSAGE, PollResult, ProviderError, Submission, VideoProvider,
    error_details, require_env, response_usage,
)


DEFAULT_MODEL = "doubao-seedance-2-5-260628"
BASE_URL = "https://ark.cn-beijing.volces.com"
RESOLUTION_BOUNDS = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}


def prepare_first_frame(path: Path, resolution: str) -> str:
    try:
        long_limit, short_limit = RESOLUTION_BOUNDS[resolution.lower()]
        with Path(path).open("rb") as handle:
            data = handle.read(20 * 1024 * 1024 + 1)
        if not data or len(data) > 20 * 1024 * 1024:
            raise ValueError("image_size")
        with Image.open(io.BytesIO(data)) as original:
            original.load()
            width, height = original.size
            factor = min(1.0, long_limit / max(width, height), short_limit / min(width, height))
            dimensions = (max(1, int(width * factor)), max(1, int(height * factor)))
            image = original.convert("RGBA" if "A" in original.getbands() or "transparency" in original.info else "RGB")
            if dimensions != original.size:
                image = image.resize(dimensions, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception:
        raise ProviderError("failed", "invalid_first_frame", "首帧校验失败，没有提交生成请求") from None


def _filtered(code: str) -> bool:
    lowered = code.lower()
    return any(value in lowered for value in (
        "sensitivecontent", "contentfilter", "contentpolicy", "copyright", "contentmoderation",
    ))


class SeedanceProvider(VideoProvider):
    @staticmethod
    def _headers() -> dict:
        return {"Authorization": "Bearer " + require_env("ARK_API_KEY"), "Content-Type": "application/json"}

    async def submit(self, params: dict, image_path: Path) -> Submission:
        headers = self._headers()
        resolution = params["resolution"].lower()
        image_uri = await asyncio.to_thread(prepare_first_frame, image_path, resolution)
        body = {
            "model": params.get("model", DEFAULT_MODEL),
            "content": [
                {"type": "text", "text": params["prompt"]},
                {"type": "image_url", "image_url": {"url": image_uri}, "role": "first_frame"},
            ],
            "duration": params["duration"], "resolution": resolution,
            "generate_audio": params.get("audio", True), "watermark": False,
        }
        data = await self._json("POST", BASE_URL + "/api/v3/contents/generations/tasks", headers, body)
        task_id = data.get("id") or data.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 512:
            raise ProviderError("uncertain", "missing_task_id", UNCERTAIN_MESSAGE)
        return Submission(task_id, response_usage(data))

    async def poll(self, task_id: str) -> PollResult:
        if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 512:
            raise ProviderError("poll_error", "invalid_task_id", "任务 ID 无效，请到控制台核对")
        data = await self._json("GET", BASE_URL + "/api/v3/contents/generations/tasks/" + quote(task_id, safe=""),
                                self._headers())
        status = data.get("status")
        usage = response_usage(data)
        if status in {"queued", "running"}:
            return PollResult("running", usage)
        if status == "succeeded":
            content = data.get("content")
            for item in content if isinstance(content, list) else [content]:
                if isinstance(item, dict):
                    for key in ("video_url", "url", "videoUrl"):
                        if isinstance(item.get(key), str) and item[key]:
                            return PollResult("succeeded", usage, item[key])
            return PollResult("succeeded", usage)
        if status in {"failed", "expired", "cancelled", "canceled"}:
            code, message = error_details(data, "upstream_failed")
            final = "filtered" if _filtered(code) else "expired" if status == "expired" else "failed"
            return PollResult(final, usage, error_code=code, error_message=message)
        raise ProviderError("poll_error", "invalid_status", "任务状态响应缺少有效状态，稍后重查")
