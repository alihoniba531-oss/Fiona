"""On-demand details for individual entries in Chloe's information cards."""
import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth_dep import get_current_user
from rate_limit import limiter
from tools.card_detail import card_detail, detail_error


router = APIRouter(prefix="/cards", tags=["cards"])
DETAIL_TIMEOUT_SECONDS = 45


class CardDetailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=1000)
    context: str = Field(default="", max_length=200)

    @field_validator("title", "context")
    @classmethod
    def normalize_text(cls, value, info):
        value = value.strip()
        if info.field_name == "title" and not value:
            raise ValueError("标题不能为空")
        return value


@router.post("/detail")
@limiter.limit("20/minute")
async def get_card_detail(
    request: Request, body: CardDetailRequest, user: str = Depends(get_current_user),
):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(card_detail, body.title, body.context),
            timeout=DETAIL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return detail_error(body.title, "详情获取超时，请重试")
