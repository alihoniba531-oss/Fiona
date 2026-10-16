"""万相 3.0：首帧保持原始尺寸，付费 POST 不做重试。"""
from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
import re
from urllib.parse import quote

from PIL import Image

from .base import (
    UNCERTAIN_MESSAGE, PollResult, ProviderError, Submission, VideoProvider,
    error_details, require_env, response_usage,
)


DEFAULT_MODEL = "wan3.0-video"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def prepare_first_frame(path: Path) -> str:
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(MAX_IMAGE_BYTES + 1)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image_size")
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("image_format")
            if "A" in image.getbands() or "transparency" in image.info:
                raise ValueError("image_alpha")
            if any(not 240 <= side <= 8000 for side in image.size):
                raise ValueError("image_dimensions")
            mime = Image.MIME[image.format]
            image.verify()
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        raise ProviderError("failed", "invalid_first_frame", "首帧校验失败，没有提交生成请求") from None


class WanProvider(VideoProvider):
    @staticmethod
    def _endpoint() -> tuple[str, dict]:
        key = require_env("DASHSCOPE_API_KEY")
        workspace = require_env("DASHSCOPE_WORKSPACE_ID")
        if not re.fullmatch(r"[A-Za-z0-9-]+", workspace):
            raise ProviderError("failed", "invalid_configuration", "DASHSCOPE_WORKSPACE_ID 无效，没有提交生成请求")
        return f"https://{workspace}.cn-beijing.maas.aliyuncs.com", {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        }

    async def submit(self, params: dict, image_path: Path) -> Submission:
        base, headers = self._endpoint()
        image_uri = await asyncio.to_thread(prepare_first_frame, image_path)
        body = {
            "model": params.get("model", DEFAULT_MODEL),
            "input": {"prompt": params["prompt"], "media": [{"type": "first_frame", "url": image_uri}]},
            "parameters": {
                "resolution": params["resolution"].upper(), "ratio": "adaptive",
                "duration": params["duration"], "audio": params.get("audio", True),
                "prompt_extend": False, "watermark": False,
            },
        }
        data = await self._json("POST", base + "/api/v1/services/aigc/video-generation/video-synthesis",
                                {**headers, "X-DashScope-Async": "enable"}, body)
        output = data.get("output")
        task_id = output.get("task_id") if isinstance(output, dict) else None
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", task_id):
            raise ProviderError("uncertain", "missing_task_id", UNCERTAIN_MESSAGE)
        return Submission(task_id, response_usage(data))

    async def poll(self, task_id: str) -> PollResult:
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", task_id):
            raise ProviderError("poll_error", "invalid_task_id", "任务 ID 无效，请到控制台核对")
        base, headers = self._endpoint()
        data = await self._json("GET", base + "/api/v1/tasks/" + quote(task_id, safe=""), headers)
        output = data.get("output")
        if not isinstance(output, dict):
            raise ProviderError("poll_error", "invalid_status", "任务状态响应缺少状态，稍后重查")
        status = output.get("task_status")
        usage = response_usage(data)
        if status in {"PENDING", "RUNNING"}:
            return PollResult("running", usage)
        if status == "SUCCEEDED":
            url = output.get("video_url") or output.get("watermark_video_url")
            return PollResult("succeeded", usage, url if isinstance(url, str) else None)
        if status in {"FAILED", "UNKNOWN"}:
            code, message = error_details(data, "upstream_failed")
            return PollResult("failed", usage, error_code=code, error_message=message)
        raise ProviderError("poll_error", "invalid_status", "任务状态响应缺少有效状态，稍后重查")
