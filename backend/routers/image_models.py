"""Authenticated, public-safe image model choices."""
from fastapi import APIRouter, Depends

from auth_dep import get_current_user
from tools.image_generation import get_image_models


router = APIRouter()


@router.get("/image-models")
async def image_models(user: str = Depends(get_current_user)):
    return get_image_models()
