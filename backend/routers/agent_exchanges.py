"""Explicit invitations and owner controls for finite AI-to-AI exchanges."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

import exchange_store
from agent_store import ResourceNotFound
from auth_dep import get_current_user
from exchange_exports import export_filename, render_exchange_markdown
from official_agents import list_official_agents
from rate_limit import limiter
from services.exchange_service import start_exchange


router = APIRouter(prefix="/agent-exchanges", tags=["agent-exchanges"])


class ExchangeTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=300)
    max_turns: int = Field(default=6, ge=2, le=6, strict=True)

    @field_validator("topic")
    @classmethod
    def nonempty_topic(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("请填写交流主题")
        return value


class ExchangeCreate(ExchangeTopic):
    target_agent_id: str = Field(min_length=1, max_length=64)


class OfficialExchangeCreate(ExchangeTopic):
    topic: str = Field(min_length=1, max_length=exchange_store.OFFICIAL_TOPIC_MAX_LENGTH)
    official_agent_id: str = Field(min_length=1, max_length=64)
    max_turns: int = Field(default=exchange_store.OFFICIAL_MAX_TURNS, ge=2, le=exchange_store.OFFICIAL_MAX_TURNS, strict=True)


@router.get("")
async def exchange_list(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    user: str = Depends(get_current_user),
):
    return {"exchanges": await exchange_store.list_exchanges(user, limit, offset)}


@router.post("", status_code=201)
@limiter.limit("10/minute")
async def create_exchange(request: Request, body: ExchangeCreate, user: str = Depends(get_current_user)):
    try:
        return {"exchange": await exchange_store.create_exchange(user, body.target_agent_id, body.topic, body.max_turns)}
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="分身不存在") from None
    except exchange_store.ExchangeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/official-agents")
async def official_agents(user: str = Depends(get_current_user)):
    return {"agents": list_official_agents()}


@router.post("/official", status_code=201)
@limiter.limit("10/minute")
async def create_official_exchange(request: Request, body: OfficialExchangeCreate, user: str = Depends(get_current_user)):
    try:
        details, run_token = await exchange_store.create_official_exchange(
            user, body.official_agent_id, body.topic, body.max_turns,
        )
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="官方分身不存在") from None
    except exchange_store.ExchangeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    start_exchange(details["exchange"]["id"], run_token)
    return details


@router.get("/{exchange_id}")
async def exchange_detail(exchange_id: str, user: str = Depends(get_current_user)):
    try:
        return await exchange_store.exchange_details(user, exchange_id)
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="交流不存在") from None


@router.get("/{exchange_id}/export")
async def export_exchange(
    exchange_id: str,
    document: Literal["readme", "discussion", "artifact"] = Query(default="readme"),
    user: str = Depends(get_current_user),
):
    try:
        detail = await exchange_store.exchange_details(user, exchange_id)
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="交流不存在") from None
    if document == "artifact" and not str(detail["exchange"].get("artifact") or "").strip():
        raise HTTPException(status_code=404, detail="作品尚未生成")
    return Response(
        content=render_exchange_markdown(detail, document).encode("utf-8"),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(exchange_id, document)}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _transition(user, exchange_id, action):
    try:
        details, run_token = await exchange_store.transition_exchange(user, exchange_id, action)
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="交流不存在") from None
    except exchange_store.ExchangeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if run_token is not None:
        start_exchange(exchange_id, run_token)
    return details


@router.post("/{exchange_id}/accept")
@limiter.limit("10/minute")
async def accept_exchange(request: Request, exchange_id: str, user: str = Depends(get_current_user)):
    return await _transition(user, exchange_id, "accept")


@router.post("/{exchange_id}/reject")
async def reject_exchange(exchange_id: str, user: str = Depends(get_current_user)):
    return await _transition(user, exchange_id, "reject")


@router.post("/{exchange_id}/stop")
async def stop_exchange(exchange_id: str, user: str = Depends(get_current_user)):
    return await _transition(user, exchange_id, "stop")
