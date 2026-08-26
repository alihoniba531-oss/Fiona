# -*- coding: utf-8 -*-

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth_dep import get_current_user
from database import get_pending_matches_for_user, mark_pending_match_seen
from llm import client
from matcher import find_matches

router = APIRouter()


class MatchResponseRequest(BaseModel):
    peer: str = Field(min_length=1, max_length=100)
    response: Literal["accept", "reject"]
    greeting: str = Field(default="", max_length=500)

    @field_validator("peer", "greeting")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


@router.get("/match")
async def get_matches(user: str = Depends(get_current_user)):
    """为当前登录用户计算并返回匹配结果"""
    results = await find_matches(client, user)
    return {"username": user, "matches": results}


@router.post("/match/response")
async def match_response(body: MatchResponseRequest, user: str = Depends(get_current_user)):
    """记录当前用户对匹配的态度：accept / reject；可选附带打招呼内容。
    body: { peer: str, response: 'accept'|'reject', greeting?: str }"""
    from database import update_match_response, save_greeting
    if not body.peer or body.peer == user:
        raise HTTPException(status_code=400, detail="peer 无效")
    updated = await update_match_response(user, body.peer, body.response)
    if not updated:
        raise HTTPException(status_code=404, detail="没有可响应的匹配")
    if body.greeting and body.response == "accept":
        await save_greeting(user, body.peer, body.greeting)
    return {"status": "ok"}


@router.get("/match/pending")
async def get_pending_matches(user: str = Depends(get_current_user)):
    """拉对话内匹配检测命中的卡片（前端聊天页轮询/回复后调用）"""
    matches = await get_pending_matches_for_user(user, limit=5)
    return {"username": user, "pending": matches}


@router.post("/match/pending/{match_id}/seen")
async def mark_match_seen(match_id: int, user: str = Depends(get_current_user)):
    """前端弹了卡片后标记已看，避免重复弹。校验卡片归属当前用户。"""
    from database import get_pending_match_owner
    owner = await get_pending_match_owner(match_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="匹配不存在")
    if owner != user:
        raise HTTPException(status_code=403, detail="无权操作")
    await mark_pending_match_seen(match_id)
    return {"status": "ok"}
