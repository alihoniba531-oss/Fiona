# -*- coding: utf-8 -*-
"""Generate one allowlisted-provider image and retain a verified PNG, without retries."""
import asyncio
import base64
import binascii
import io
import json
import math
import os
import re
import stat
import tempfile
import uuid
import warnings
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from PIL import Image

from utils import media


_GENERATION_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
_ARK_GENERATION_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
# Documented result buckets: qwen-image-generation-and-editing-api-reference
# and qwen-image-api in https://help.aliyun.com/zh/model-studio/ .
# Never accept arbitrary OSS buckets,
# redirects, or a user-supplied download URL. DNS may use the deployment's proxy;
# standard HTTPS certificate verification remains enabled for this fixed host.
_RESULT_HOSTS = frozenset({
    "dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com",
    "dashscope-result-sh.oss-cn-shanghai.aliyuncs.com",
    # qwen-image-api FAQ names this bucket and OSS acceleration hostname form.
    # Also observed in an authenticated Qwen Image 3.0 response; keep it exact.
    "dashscope-a717.oss-accelerate.aliyuncs.com",
})
_TIMEOUT_SECONDS = 150
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_ARK_RESPONSE_BYTES = 40 * 1024 * 1024
_MAX_IMAGE_PIXELS = 2048 * 2048
_MIN_ARK_IMAGE_PIXELS = 921600
_MAX_ARK_IMAGE_PIXELS = 4624220
_REFERENCE_IMAGE_PATH = re.compile(r"/uploads/((?:generated|reference)_[0-9a-f]{32}\.png)")
_SIZES = {
    "1:1": "1024x1024",
    "16:9": "1536x864",
    "9:16": "864x1536",
    "4:3": "1280x960",
    "3:4": "960x1280",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}


class ImageGenerationError(Exception):
    """A safe Chinese message suitable for returning directly to the user."""

    def __init__(
        self, message: str, *, provider_status: int | None = None, provider_code: str | None = None,
        category: str = "other",
    ):
        super().__init__(message)
        self.provider_status = provider_status
        self.provider_code = provider_code
        self.category = category


DEFAULT_IMAGE_MODEL = "qwen-image-3.0"


@dataclass(frozen=True)
class ImageModel:
    id: str
    label: str
    provider: str
    model_env: str
    default_model: str
    api_key_env: str

    def public_metadata(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "available": image_model_available(self.id),
        }


_IMAGE_MODELS = {
    DEFAULT_IMAGE_MODEL: ImageModel(
        DEFAULT_IMAGE_MODEL, "Qwen Image 3.0", "dashscope",
        "QWEN_IMAGE_MODEL", "qwen-image-3.0", "DASHSCOPE_API_KEY",
    ),
    "seedream-5.0-flash": ImageModel(
        "seedream-5.0-flash", "Seedream 5.0 Flash", "ark",
        "SEEDREAM_IMAGE_MODEL", "doubao-seedream-5-0-flash-260915", "ARK_API_KEY",
    ),
}


def image_model_available(model_id: str) -> bool:
    """Read the selected provider key at request time, as the picker does."""
    selected = _IMAGE_MODELS.get(model_id) if isinstance(model_id, str) else None
    return bool(selected and os.getenv(selected.api_key_env, "").strip())


def get_image_models() -> dict:
    """Expose only picker metadata; configuration is read at request time."""
    return {
        "default": DEFAULT_IMAGE_MODEL,
        "models": [model.public_metadata() for model in _IMAGE_MODELS.values()],
    }


def _image_model_configuration(model_id: str | None) -> tuple[ImageModel, str, str]:
    if model_id is None:
        model_id = DEFAULT_IMAGE_MODEL
    selected = _IMAGE_MODELS.get(model_id) if isinstance(model_id, str) else None
    if selected is None:
        raise ImageGenerationError("暂不支持这个图片模型，请重新选择。")
    api_key = os.getenv(selected.api_key_env, "").strip()
    if not api_key:
        if selected.provider == "ark":
            raise ImageGenerationError("Seedream 生图暂不可用，请改选 Qwen Image 3.0。")
        raise ImageGenerationError("图片生成服务尚未配置，请联系管理员。")
    model = os.getenv(selected.model_env, selected.default_model).strip() or selected.default_model
    return selected, model, api_key


def _ark_error(status: int, data: object) -> ImageGenerationError:
    error = data.get("error", data) if isinstance(data, dict) else {}
    raw_code = str(error.get("code", "")) if isinstance(error, dict) else ""
    safe_code = re.sub(r"[^A-Za-z0-9._-]", "", raw_code)[:80]
    code = raw_code.lower()
    category = "other"
    if any(marker in code for marker in (
        "sensitivecontentdetected", "riskdetection", "policyviolation", "privacyinformation", "deepfake",
    )):
        category = "moderation"
        message = "描述或参考图未通过内容审核，请修改后再试。"
    elif status == 429 or "ratelimit" in code or "quotaexceeded" in code:
        category = "busy"
        message = "图片生成服务繁忙，请稍后再试。"
    elif status in {401, 403, 404} or any(marker in code for marker in (
        "modelnotopen", "accountoverdue", "invalidendpointormodel",
    )):
        category = "unavailable"
        message = "Seedream 生图暂不可用，请改选 Qwen Image 3.0。"
    else:
        message = "图片生成失败，请稍后再试。"
    return ImageGenerationError(message, provider_status=status, provider_code=safe_code, category=category)


def _provider_error(status: int, data: object) -> ImageGenerationError:
    error = data.get("error", data) if isinstance(data, dict) else {}
    code = str(error.get("code", "")).lower() if isinstance(error, dict) else ""
    if status == 429 or "throttl" in code or "ratelimit" in code:
        return ImageGenerationError("图片生成服务繁忙，请稍后再试。", category="busy")
    if status in {401, 403, 404} or any(
        marker in code for marker in ("invalidapikey", "invalid_api_key", "modelnotfound", "model_not_found", "accessdenied")
    ):
        return ImageGenerationError("图片生成服务暂不可用，请联系管理员检查模型权限和配置。", category="unavailable")
    if any(marker in code for marker in ("inappropriate", "datainspection", "content_policy", "safety")):
        return ImageGenerationError("这次图片描述未通过生成服务的内容检查，请调整描述后再试。", category="moderation")
    return ImageGenerationError("图片暂时没有生成成功，请稍后再试。")


def _validated_result_url(value: object) -> str:
    try:
        if not isinstance(value, str) or len(value) > 8192:
            raise ValueError("invalid URL")
        if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
            raise ValueError("invalid URL characters")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _RESULT_HOSTS
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or not parsed.path.startswith("/")
        ):
            raise ValueError("untrusted result URL")
    except (ValueError, TypeError):
        raise ImageGenerationError("图片生成结果地址无效，请稍后再试。") from None
    return value


async def _read_bounded(response: httpx.Response, limit: int) -> bytes:
    length = response.headers.get("content-length")
    if length:
        try:
            if int(length) < 0 or int(length) > limit:
                raise ImageGenerationError("生成的图片文件过大，请换个尺寸再试。")
        except ValueError:
            raise ImageGenerationError("图片生成服务返回了无效文件。") from None
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > limit:
            raise ImageGenerationError("生成的图片文件过大，请换个尺寸再试。")
        body.extend(chunk)
    return bytes(body)


def _request_body(prompt: str, size: str, model: str, *, reference_image: str | list[str] | None = None) -> dict:
    parameters = {"size": size.replace("x", "*"), "n": 1, "prompt_extend": reference_image is None}
    if model.startswith("qwen-image-3.0"):
        parameters["enable_thinking"] = False
    references = [reference_image] if isinstance(reference_image, str) else (reference_image or [])
    content = [{"image": reference} for reference in references] + [{"text": prompt}]
    return {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }


def _result_image_url(data: dict) -> str:
    output = data.get("output")
    choices = output.get("choices") if isinstance(output, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ImageGenerationError("图片生成服务没有返回有效图片，请稍后再试。")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        raise ImageGenerationError("图片生成服务没有返回有效图片，请稍后再试。")
    images = [item["image"] for item in content if isinstance(item, dict) and "image" in item]
    if len(images) != 1:
        raise ImageGenerationError("图片生成服务没有返回有效图片，请稍后再试。")
    return _validated_result_url(images[0])


async def _fetch_generated_bytes(
    prompt: str, size: str, model: str, api_key: str, *, reference_image: str | list[str] | None = None
) -> bytes:
    timeout = httpx.Timeout(_TIMEOUT_SECONDS, connect=10, write=15, pool=10)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream(
            "POST",
            _GENERATION_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=_request_body(prompt, size, model, reference_image=reference_image),
        ) as response:
            raw = await _read_bounded(response, _MAX_RESPONSE_BYTES)
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeDecodeError, RecursionError):
                raise _provider_error(response.status_code, {}) from None
            if response.status_code != 200 or not isinstance(data, dict) or data.get("error") or data.get("code"):
                raise _provider_error(response.status_code, data)
            image_url = _result_image_url(data)

        # Authentication belongs only to the generation POST, never the image host.
        async with client.stream("GET", image_url) as response:
            if response.status_code != 200:
                raise ImageGenerationError("生成的图片暂时无法保存，请稍后再试。")
            mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if mime != "image/png":
                raise ImageGenerationError("图片生成服务返回了无效文件。")
            return await _read_bounded(response, _MAX_IMAGE_BYTES)


def _ark_size(width: int, height: int) -> str:
    """Fit the target area, accepting at most 1% ratio error before comparing area."""
    if width <= 0 or height <= 0 or not 1 / 16 <= width / height <= 16:
        raise ImageGenerationError("参考图片比例超出 Seedream 支持范围，请换一张图片。")
    maximum = min(_MAX_ARK_IMAGE_PIXELS, _MAX_IMAGE_PIXELS)
    pixels = width * height
    if _MIN_ARK_IMAGE_PIXELS <= pixels <= maximum:
        return f"{width}x{height}"
    desired_pixels = min(max(pixels, _MIN_ARK_IMAGE_PIXELS), maximum)
    scale = math.sqrt(desired_pixels / pixels)

    def nearby(value: float) -> set[int]:
        lower = math.floor(value / 8) * 8
        return {lower - 8, lower, round(value / 8) * 8, lower + 8, lower + 16}

    def candidates(widths, heights):
        options = []
        for target_width in widths:
            for target_height in heights(target_width):
                target_pixels = target_width * target_height
                if (
                    target_width > 0 and target_height > 0
                    and _MIN_ARK_IMAGE_PIXELS <= target_pixels <= maximum
                    and 1 / 16 <= target_width / target_height <= 16
                ):
                    ratio_error = abs((target_width / target_height) / (width / height) - 1)
                    size_error = abs(target_pixels - desired_pixels)
                    options.append((size_error, ratio_error, target_width, target_height))
        return options

    options = candidates(nearby(width * scale), lambda _: nearby(height * scale))
    within_ratio = [option for option in options if option[1] <= 0.01]
    if not within_ratio:
        # Rare rounding boundaries may need more distant multiples of eight.
        # Only relax the ratio tolerance if no valid candidate satisfies it.
        max_width = math.floor(math.sqrt(maximum * 16) / 8) * 8
        options = candidates(
            range(8, max_width + 1, 8),
            lambda target_width: nearby(target_width * height / width),
        )
        within_ratio = [option for option in options if option[1] <= 0.01]
    if within_ratio:
        _, _, target_width, target_height = min(within_ratio)
    elif options:
        _, _, target_width, target_height = min(options, key=lambda option: (option[1], option[0]))
    else:
        raise ImageGenerationError("参考图片比例无法适配 Seedream 图片尺寸，请换一张图片。")
    return f"{target_width}x{target_height}"


async def _fetch_ark_png(
    prompt: str, size: str, model: str, api_key: str, *, reference_images: str | list[str] | None = None
) -> bytes:
    try:
        width, height = (int(value) for value in size.split("x"))
    except (ValueError, AttributeError):
        raise ImageGenerationError("图片尺寸超出 Seedream 支持范围，请换个尺寸再试。") from None
    if width <= 0 or height <= 0 or not 1 / 16 <= width / height <= 16:
        raise ImageGenerationError("图片比例超出 Seedream 支持范围，请换个尺寸再试。")
    if not _MIN_ARK_IMAGE_PIXELS <= width * height <= min(_MAX_ARK_IMAGE_PIXELS, _MAX_IMAGE_PIXELS):
        raise ImageGenerationError("图片尺寸超出 Seedream 支持范围，请换个尺寸再试。")
    body = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "b64_json",
        "output_format": "png",
        "watermark": False,
    }
    if reference_images is not None:
        body["image"] = reference_images
    timeout = httpx.Timeout(_TIMEOUT_SECONDS, connect=10, write=15, pool=10)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream(
            "POST", _ARK_GENERATION_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        ) as response:
            data = {}
            try:
                raw = await _read_bounded(response, _MAX_ARK_RESPONSE_BYTES)
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeDecodeError, RecursionError):
                    raise _ark_error(response.status_code, {}) from None
                if response.status_code != 200 or not isinstance(data, dict) or data.get("error") or data.get("code"):
                    raise _ark_error(response.status_code, data)
                images = data.get("data")
                first_image = (
                    images[0] if isinstance(images, list) and images and isinstance(images[0], dict) else {}
                )
                encoded = first_image.get("b64_json")
                if not isinstance(encoded, str) or not encoded:
                    raise _ark_error(response.status_code, first_image)
                try:
                    png = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    raise ImageGenerationError("图片生成服务返回了无效文件。") from None
                if len(png) > _MAX_IMAGE_BYTES:
                    raise ImageGenerationError("生成的图片文件过大，请换个尺寸再试。")
                try:
                    _png_dimensions(png)
                except Exception:
                    raise ImageGenerationError("生成的图片内容损坏或尺寸过大，请稍后再试。") from None
                return png
            except ImageGenerationError as exc:
                if exc.provider_status is None:
                    metadata = _ark_error(response.status_code, data)
                    exc.provider_status = metadata.provider_status
                    exc.provider_code = metadata.provider_code
                print(f"[image] provider=ark status={exc.provider_status} code={exc.provider_code}")
                raise


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Verify a bounded PNG before decoding it; callers supply safe failure messages."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if image.format != "PNG" or width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
                raise ValueError("invalid PNG size or format")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    return width, height


def _reference_image_bytes(reference_image_path: str) -> tuple[bytes, int, int]:
    """Read only an app-managed regular PNG. Ownership is enforced by the caller."""
    match = _REFERENCE_IMAGE_PATH.fullmatch(reference_image_path) if isinstance(reference_image_path, str) else None
    if match is None:
        raise ImageGenerationError("参考图片地址无效，请重新选择图片。")
    root = os.path.realpath(media.UPLOADS_DIR)
    candidate = os.path.join(root, match.group(1))
    # Resolve the configured root, but never follow a reference-file symlink,
    # even when its destination is another file within uploads.
    if os.path.realpath(candidate) != candidate or os.path.islink(candidate):
        raise ImageGenerationError("参考图片地址无效，请重新选择图片。")
    try:
        # NOFOLLOW closes the check/open race; NONBLOCK prevents a FIFO from
        # blocking before fstat rejects anything other than a regular file.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(candidate, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ImageGenerationError("参考图片地址无效，请重新选择图片。")
            if metadata.st_size > _MAX_REFERENCE_IMAGE_BYTES:
                raise ImageGenerationError("参考图片不能超过 10MB，请换一张图片。")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                data = source.read(_MAX_REFERENCE_IMAGE_BYTES + 1)
        finally:
            os.close(descriptor)
    except OSError:
        raise ImageGenerationError("参考图片不存在或无法读取，请重新选择图片。") from None
    if len(data) > _MAX_REFERENCE_IMAGE_BYTES:
        raise ImageGenerationError("参考图片不能超过 10MB，请换一张图片。")
    try:
        width, height = _png_dimensions(data)
    except Exception:
        raise ImageGenerationError("参考图片内容损坏或尺寸过大，请重新生成图片。") from None
    return data, width, height


def _persist_png(data: bytes) -> tuple[str, int, int]:
    try:
        width, height = _png_dimensions(data)
    except Exception:
        raise ImageGenerationError("生成的图片内容损坏或尺寸过大，请稍后再试。") from None

    filename = f"generated_{uuid.uuid4().hex}.png"
    destination = os.path.join(media.UPLOADS_DIR, filename)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=media.UPLOADS_DIR, prefix=".generated_", delete=False) as file:
            temporary = file.name
            file.write(data)
        os.replace(temporary, destination)
    except OSError:
        raise ImageGenerationError("图片已经生成，但暂时无法保存，请稍后再试。") from None
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                # Keep filesystem details out of any user-facing failure.
                pass
    return f"/uploads/{filename}", width, height


async def generate_image(
    prompt: str, aspect_ratio: str = "1:1", *, model_id: str | None = DEFAULT_IMAGE_MODEL
) -> dict:
    """Create exactly one image. Cancellation propagates and cannot leave a partial file."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ImageGenerationError("请先描述你想生成的图片。")
    if len(prompt) > 12000:
        raise ImageGenerationError("图片描述太长了，请精简后再试。")
    if not isinstance(aspect_ratio, str) or aspect_ratio not in _SIZES:
        raise ImageGenerationError("暂不支持这个图片比例，请使用方形、横图或竖图比例。")
    selected, model, api_key = _image_model_configuration(model_id)
    try:
        # One total deadline includes generation, download and closing the client.
        # Do not retry: another generation can incur another charge.
        if selected.provider == "ark":
            data = await asyncio.wait_for(
                _fetch_ark_png(prompt.strip(), _SIZES[aspect_ratio], model, api_key),
                timeout=_TIMEOUT_SECONDS,
            )
        else:
            data = await asyncio.wait_for(
                _fetch_generated_bytes(prompt.strip(), _SIZES[aspect_ratio], model, api_key),
                timeout=_TIMEOUT_SECONDS,
            )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise ImageGenerationError("图片生成等待超时，请稍后再试。") from None
    except httpx.HTTPError:
        raise ImageGenerationError("图片生成服务暂时连接不上，请稍后再试。") from None
    # No await follows the atomic save: an interrupted network operation cannot
    # complete later and leave an unreferenced generated image on disk.
    image_path, width, height = _persist_png(data)
    return {"image_path": image_path, "model": model, "width": width, "height": height}


def _reference_paths(reference_image_path: str | list[str]) -> list[str]:
    """Preserve the selected order and reject invalid selections before reading files."""
    if isinstance(reference_image_path, str):
        references = [reference_image_path]
    elif isinstance(reference_image_path, list):
        references = list(reference_image_path)
    else:
        raise ImageGenerationError("参考图片地址无效，请重新选择图片。")
    if not 1 <= len(references) <= 3:
        raise ImageGenerationError("请选择 1 至 3 张参考图片。")
    if any(not isinstance(path, str) or _REFERENCE_IMAGE_PATH.fullmatch(path) is None for path in references):
        raise ImageGenerationError("参考图片地址无效，请重新选择图片。")
    if len(set(references)) != len(references):
        raise ImageGenerationError("请勿重复选择同一张参考图片。")
    return references


async def edit_image(
    prompt: str, reference_image_path: str | list[str], aspect_ratio: str | None = None,
    *, model_id: str | None = DEFAULT_IMAGE_MODEL,
) -> dict:
    """Edit 1–3 authorized local images in order, using the first image's size by default."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ImageGenerationError("请先描述你想修改的地方。")
    if len(prompt) > 12000:
        raise ImageGenerationError("图片描述太长了，请精简后再试。")
    if aspect_ratio is not None and (not isinstance(aspect_ratio, str) or aspect_ratio not in _SIZES):
        raise ImageGenerationError("暂不支持这个图片比例，请使用方形、横图或竖图比例。")
    selected, model, api_key = _image_model_configuration(model_id)
    reference_paths = _reference_paths(reference_image_path)
    references = [_reference_image_bytes(path) for path in reference_paths]
    _, width, height = references[0]
    size = _SIZES[aspect_ratio] if aspect_ratio is not None else f"{width}x{height}"
    if selected.provider == "ark" and aspect_ratio is None:
        size = _ark_size(width, height)
    data_urls = ["data:image/png;base64," + base64.b64encode(reference).decode("ascii") for reference, _, _ in references]
    # Preserve the original single-image helper argument while adding ordered lists.
    provider_references = data_urls[0] if len(data_urls) == 1 else data_urls
    try:
        if selected.provider == "ark":
            data = await asyncio.wait_for(
                _fetch_ark_png(prompt.strip(), size, model, api_key, reference_images=provider_references),
                timeout=_TIMEOUT_SECONDS,
            )
        else:
            data = await asyncio.wait_for(
                _fetch_generated_bytes(prompt.strip(), size, model, api_key, reference_image=provider_references),
                timeout=_TIMEOUT_SECONDS,
            )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise ImageGenerationError("图片编辑等待超时，请稍后再试。") from None
    except httpx.HTTPError:
        raise ImageGenerationError("图片生成服务暂时连接不上，请稍后再试。") from None
    # Keep all original images intact and publish only the fully saved new PNG.
    image_path, width, height = _persist_png(data)
    return {"image_path": image_path, "model": model, "width": width, "height": height}
