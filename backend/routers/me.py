# -*- coding: utf-8 -*-
import os

from fastapi import APIRouter, Depends, HTTPException

from auth_dep import get_current_user
from database import (delete_message, get_all_messages, get_or_create_user,
                      get_strawberry_balance)
from model_router import token_budget

router = APIRouter()


@router.get("/user/settings")
async def get_user_settings_api(user: str = Depends(get_current_user)):
    """获取当前用户性别 + 匹配偏好"""
    from database import get_user_settings
    await get_or_create_user(user)
    settings = await get_user_settings(user)
    return {"username": user, "settings": settings}


@router.post("/user/settings")
async def update_user_settings_api(body: dict, user: str = Depends(get_current_user)):
    """更新当前用户性别 + 匹配偏好"""
    from database import update_user_settings
    await get_or_create_user(user)
    gender = body.get("gender")
    match_pref = body.get("match_pref", "both")
    await update_user_settings(user, gender, match_pref)
    return {"status": "ok"}


@router.get("/profile")
async def get_user_profile(user: str = Depends(get_current_user)):
    from database import get_profile
    profile = await get_profile(user)
    return {"username": user, "profile": profile}


@router.get("/history")
async def get_history(user: str = Depends(get_current_user)):
    await get_or_create_user(user)
    messages = await get_all_messages(user)
    return {"username": user, "messages": messages}


@router.delete("/message/{message_id}")
async def delete_one_message(message_id: int, user: str = Depends(get_current_user)):
    from database import get_message_owner
    owner = await get_message_owner(message_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if owner != user:
        raise HTTPException(status_code=403, detail="无权操作")
    await delete_message(message_id)
    return {"status": "deleted"}


@router.delete("/history")
async def clear_history(user: str = Depends(get_current_user)):
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE username = ?", (user,))
        await db.commit()
    return {"status": "cleared"}


@router.get("/usage")
async def get_usage(user: str = Depends(get_current_user)):
    """返回当前用户今日 + 本月草莓用量"""
    from model_router import MAIN_DAILY_LIMIT, MAIN_MONTHLY_LIMIT
    daily   = token_budget.get_daily(user)
    monthly = token_budget.get_monthly(user)
    def pct(used, limit): return min(100, round(used / limit * 100)) if limit > 0 else 0
    return {
        "daily":   {"used": daily,   "limit": MAIN_DAILY_LIMIT,   "percent": pct(daily,   MAIN_DAILY_LIMIT)},
        "monthly": {"used": monthly, "limit": MAIN_MONTHLY_LIMIT, "percent": pct(monthly, MAIN_MONTHLY_LIMIT)},
    }




@router.get("/strawberry")
async def get_strawberry(user: str = Depends(get_current_user)):
    bal = await get_strawberry_balance(user)
    return {"username": user, "balance": bal}


# ── 用户列表（仅 DEV_MODE 开放，供本地切换身份用）─────────────
@router.get("/users")
async def list_users():
    """DEV_MODE=1 时返回所有用户列表，便于本地切身份调试；生产环境返回 404 隐藏。"""
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT username FROM users ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()
    return {"users": [r["username"] for r in rows]}
