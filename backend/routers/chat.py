# -*- coding: utf-8 -*-
import json
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth_dep import get_current_user
from agent_store import ResourceNotFound
from database import get_strawberry_balance
from rate_limit import limiter
from services.chat_service import build_context, run_chat
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

    # ── 草莓余额检查（DEV 模式跳过）────────────────────────────
    if os.getenv("DEV_MODE", "0") != "1":
        balance = await get_strawberry_balance(user)
        if balance <= 0:
            async def _no_balance():
                yield f"data: {json.dumps({'error': '草莓不足，请充值后继续聊天 🍓'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(_no_balance(), media_type="text/event-stream")

    # 预检装配 → 流式编排（具体逻辑见 services/chat_service.py）
    try:
        ctx = await build_context(req, user)
    except ResourceNotFound:
        detail = "参考图不存在或不属于当前对话" if req.mode == "image_edit" else "会话不存在"
        raise HTTPException(status_code=404, detail=detail) from None
    return StreamingResponse(run_chat(ctx), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
