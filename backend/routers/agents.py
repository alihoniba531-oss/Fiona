"""A user's private AI identity and explicit public cards."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

import agent_store
from auth_dep import get_current_user


router = APIRouter(prefix="/agents", tags=["agents"])


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    bio: str | None = Field(default=None, max_length=300)
    personality: str | None = Field(default=None, max_length=2000)
    avatar_emoji: str | None = Field(default=None, min_length=1, max_length=16)
    is_public: bool | None = None

    @field_validator("display_name", "bio", "personality", "avatar_emoji")
    @classmethod
    def normalize_text(cls, value, info):
        if value is None:
            return None
        value = value.strip()
        if not value and info.field_name in {"display_name", "avatar_emoji"}:
            raise ValueError("不能为空")
        return value


def _not_found():
    return HTTPException(status_code=404, detail="分身不存在")


@router.get("/me")
async def my_agent(user: str = Depends(get_current_user)):
    try:
        return {"agent": await agent_store.get_my_agent(user)}
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.put("/me")
async def update_agent(body: AgentUpdate, user: str = Depends(get_current_user)):
    try:
        return {"agent": await agent_store.update_my_agent(user, body.model_dump(exclude_none=True))}
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.get("/me/memory")
async def my_memory(user: str = Depends(get_current_user)):
    try:
        snapshot = await agent_store.get_memory_snapshot(user)
        return {"profile": snapshot["profile"]}
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.delete("/me/memory")
async def delete_memory(user: str = Depends(get_current_user)):
    try:
        await agent_store.clear_memory(user)
        return {"status": "cleared"}
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.get("")
async def public_agents(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    user: str = Depends(get_current_user),
):
    return {"agents": await agent_store.list_public_agents(limit, offset)}


@router.get("/{agent_id}")
async def agent_details(agent_id: str, user: str = Depends(get_current_user)):
    try:
        return {"agent": await agent_store.get_agent_for_viewer(agent_id, user)}
    except agent_store.ResourceNotFound:
        raise _not_found()
