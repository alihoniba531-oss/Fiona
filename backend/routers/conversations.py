"""Persistent private conversations; public cards never grant chat access."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

import agent_store
from auth_dep import get_current_user
from database import mark_upload_cleanup_done
from utils.media import delete_uploaded_files


router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=80)
    agent_id: str | None = Field(default=None, max_length=64)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value):
        return value.strip() or None if value is not None else None


def _not_found():
    return HTTPException(status_code=404, detail="会话不存在")


@router.get("")
async def conversation_list(user: str = Depends(get_current_user)):
    try:
        return {"conversations": await agent_store.list_conversations(user)}
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.post("", status_code=201)
async def new_conversation(body: ConversationCreate, user: str = Depends(get_current_user)):
    try:
        return {"conversation": await agent_store.create_conversation(user, body.title, body.agent_id)}
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.get("/{conversation_id}/messages")
async def conversation_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    user: str = Depends(get_current_user),
):
    try:
        return await agent_store.get_conversation_messages(user, conversation_id, limit)
    except agent_store.ResourceNotFound:
        raise _not_found()


@router.delete("/{conversation_id}")
async def remove_conversation(conversation_id: str, user: str = Depends(get_current_user)):
    try:
        result = await agent_store.delete_conversation(user, conversation_id)
    except agent_store.ResourceNotFound:
        raise _not_found()
    from intent_router import clear_pending
    from mode_switcher import clear_user_mode

    state_key = (user, conversation_id)
    clear_pending(state_key)
    clear_user_mode(state_key)
    deleted_files, failed_files = delete_uploaded_files(result["upload_paths"])
    await mark_upload_cleanup_done(deleted_files)
    return {"status": "deleted", "file_cleanup_complete": not failed_files}
