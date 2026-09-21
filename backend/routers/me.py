# -*- coding: utf-8 -*-
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth_dep import get_current_user
from database import get_all_messages, get_strawberry_balance
from model_router import token_budget

router = APIRouter()


class DeleteAccountRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)


@router.get("/user/settings")
async def get_user_settings_api(user: str = Depends(get_current_user)):
    """获取当前用户性别 + 匹配偏好"""
    from database import get_user_settings
    settings = await get_user_settings(user)
    return {"username": user, "settings": settings}


@router.post("/user/settings")
async def update_user_settings_api(body: dict, user: str = Depends(get_current_user)):
    """更新当前用户性别 + 匹配偏好"""
    from database import update_user_settings
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
    messages = await get_all_messages(user)
    return {"username": user, "messages": messages}


@router.delete("/message/{message_id}")
async def delete_one_message(message_id: int, user: str = Depends(get_current_user)):
    from database import delete_message_for_user, mark_upload_cleanup_done
    from utils.media import delete_uploaded_files

    result = await delete_message_for_user(message_id, user)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="消息不存在")
    if result["status"] == "forbidden":
        raise HTTPException(status_code=403, detail="无权操作")
    deleted_files, _ = delete_uploaded_files(result["upload_paths"])
    await mark_upload_cleanup_done(deleted_files)
    return {"status": "deleted"}


@router.delete("/history")
async def clear_history(user: str = Depends(get_current_user)):
    from database import clear_message_history, mark_upload_cleanup_done
    from utils.media import delete_uploaded_files

    upload_paths = await clear_message_history(user)
    deleted_files, _ = delete_uploaded_files(upload_paths)
    await mark_upload_cleanup_done(deleted_files)
    return {"status": "cleared"}


@router.delete("/account")
async def delete_account(
    body: DeleteAccountRequest,
    user: str = Depends(get_current_user),
):
    """删除当前账号的数据库记录、广场内容和不再被引用的上传文件。"""
    if body.confirmation != user:
        raise HTTPException(status_code=400, detail="请输入当前用户名确认删除")

    from database import delete_account_data, mark_upload_cleanup_done
    from intent_router import clear_user_pending
    from mode_switcher import clear_all_user_modes
    from routers.peer import ws_manager
    from utils.media import delete_uploaded_files

    result = await delete_account_data(user)
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="账号不存在")

    clear_user_pending(user)
    clear_all_user_modes(user)
    await ws_manager.disconnect_user(user)
    deleted_files, failed_files = delete_uploaded_files(result["upload_paths"])
    await mark_upload_cleanup_done(deleted_files)

    response = JSONResponse({
        "status": "deleted",
        "deleted_files": len(deleted_files),
        "file_cleanup_complete": not failed_files,
    })
    response.delete_cookie("fiona_token", path="/")
    return response


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
