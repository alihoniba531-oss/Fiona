# -*- coding: utf-8 -*-
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth_dep import get_current_user
from database import get_strawberry_balance
from rate_limit import limiter
from services.chat_service import build_context, run_chat
from utils.media import MAX_IMAGE_BASE64_CHARS

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(max_length=8000)
    image_base64: str | None = Field(default=None, max_length=MAX_IMAGE_BASE64_CHARS)


@router.post("/chat")
@limiter.limit("30/minute")
async def chat(request: Request, req: ChatRequest, user: str = Depends(get_current_user)):
    has_image = bool(req.image_base64)
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
    ctx = await build_context(req, user)
    return StreamingResponse(run_chat(ctx), media_type="text/event-stream")
