# -*- coding: utf-8 -*-
import json
import os
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth_dep import get_current_user
from agent_store import ResourceNotFound
from database import (STRAWBERRY_COST_PER_REPLY, get_strawberry_balance,
                      refund_strawberries, reserve_strawberries, strawberry_daily_refill)
from rate_limit import limiter
from safety import CRISIS_RESOURCE_NOTE, detect_crisis
from services.chat_service import ChatRunTracker, build_context, run_chat
from utils.media import MAX_IMAGE_BASE64_CHARS

router = APIRouter()
ReferenceImagePath = Annotated[str, Field(max_length=64, pattern=r"^/uploads/(?:generated|reference)_[0-9a-f]{32}\.png$")]


class ReferenceImageSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_path: ReferenceImagePath | None = None
    image_base64: str | None = Field(default=None, min_length=1, max_length=MAX_IMAGE_BASE64_CHARS)

    @model_validator(mode="after")
    def exactly_one_source(self):
        if (self.image_path is None) == (self.image_base64 is None):
            raise ValueError("每张参考图请选择一张已有图片或上传一张本地图片")
        return self


class ChatRequest(BaseModel):
    message: str = Field(max_length=8000)
    image_base64: str | None = Field(default=None, max_length=MAX_IMAGE_BASE64_CHARS)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    mode: Literal["chat", "image", "image_edit"] = "chat"
    aspect_ratio: Literal["1:1", "16:9", "9:16"] | None = None
    reference_image_path: str | None = Field(
        default=None, max_length=64, pattern=r"^/uploads/(?:generated|reference)_[0-9a-f]{32}\.png$",
    )
    reference_image_paths: list[ReferenceImagePath] | None = Field(default=None, min_length=1, max_length=3)
    reference_images: list[ReferenceImageSource] | None = Field(default=None, min_length=1, max_length=3)


async def _refund_before_stream(user: str) -> None:
    with anyio.CancelScope(shield=True):
        await refund_strawberries(user, STRAWBERRY_COST_PER_REPLY)


def _text_stream(*events: dict) -> StreamingResponse:
    async def stream():
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")


class _ReservedChatResponse(StreamingResponse):
    """Close the chat generator and refund if ASGI never entered it."""

    def __init__(self, stream, user: str, tracker: ChatRunTracker, **kwargs):
        super().__init__(stream, **kwargs)
        self._chat_stream = stream
        self._reservation_user = user
        self._tracker = tracker

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    await self._chat_stream.aclose()
                finally:
                    if not self._tracker.started:
                        await _refund_before_stream(self._reservation_user)


@router.post("/chat")
@limiter.limit("30/minute")
async def chat(request: Request, req: ChatRequest, user: str = Depends(get_current_user)):
    has_image = bool(req.image_base64)
    if sum(value is not None for value in (req.reference_image_path, req.reference_image_paths, req.reference_images)) > 1:
        raise HTTPException(status_code=400, detail="请使用一组参考图，不要同时提交两种引用格式")
    references = req.reference_image_paths or ([req.reference_image_path] if req.reference_image_path else [])
    if req.reference_images is not None:
        references = [source.image_path for source in req.reference_images if source.image_path is not None]
    if len(references) != len(set(references)):
        raise HTTPException(status_code=400, detail="同一张图片无需重复加入参考")
    if req.mode == "image_edit":
        if not references and not req.reference_images:
            raise HTTPException(status_code=400, detail="请先上传参考图，或在生成的图片上点击「以此图修改」")
        if has_image:
            raise HTTPException(status_code=400, detail="修改参考图时请先移除待上传的图片")
        if not req.message.strip():
            raise HTTPException(status_code=400, detail="请先输入希望修改的内容")
    elif references or req.reference_images:
        raise HTTPException(status_code=400, detail="参考图仅用于图片修改，请选择「以此图修改」")
    if req.mode == "image" and has_image:
        raise HTTPException(status_code=400, detail="生成图片时请先移除待发送的图片，再描述想生成的画面")
    if not req.message.strip() and not has_image:
        raise HTTPException(status_code=400, detail="message 和图片不能同时为空")

    crisis = detect_crisis(req.message)
    reserved = False
    dev_mode = os.getenv("DEV_MODE", "0") == "1"
    if crisis:
        # A user in crisis can reach support without spending strawberries.
        if not dev_mode and await get_strawberry_balance(user) < STRAWBERRY_COST_PER_REPLY:
            return _text_stream({"text": CRISIS_RESOURCE_NOTE}, {"done": True})
    elif not dev_mode:
        remaining = await reserve_strawberries(user, STRAWBERRY_COST_PER_REPLY)
        if remaining is None:
            refill = strawberry_daily_refill()
            message = (
                f"今天的草莓用完了，明天会自动补到 {refill} 颗；急用请联系管理员补充 🍓"
                if refill else "草莓不足，内测期间请联系管理员补充 🍓"
            )
            return _text_stream({"error": message})
        reserved = True

    # 预检装配 → 流式编排（具体逻辑见 services/chat_service.py）
    try:
        ctx = await build_context(req, user)
    except ResourceNotFound:
        if reserved:
            await _refund_before_stream(user)
        detail = "参考图不存在或不属于当前对话" if req.mode == "image_edit" else "会话不存在"
        raise HTTPException(status_code=404, detail=detail) from None
    except BaseException:
        if reserved:
            await _refund_before_stream(user)
        raise
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    if reserved:
        tracker = ChatRunTracker()
        stream = run_chat(ctx, reserved=True, crisis=crisis, tracker=tracker)
        return _ReservedChatResponse(
            stream, user, tracker, media_type="text/event-stream", headers=headers,
        )
    return StreamingResponse(
        run_chat(ctx, crisis=crisis), media_type="text/event-stream", headers=headers,
    )
