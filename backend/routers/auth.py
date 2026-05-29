# -*- coding: utf-8 -*-
import os

from fastapi import APIRouter, HTTPException

from auth import create_token, make_otp
from database import (check_and_consume_otp, get_or_create_user, get_or_create_user_by_phone,
                      get_strawberry_balance, redeem_invite, save_otp)
from sms import send_sms

router = APIRouter()


# ── 认证端点 ────────────────────────────────────────────────────

@router.post("/auth/send-otp")
async def send_otp_api(body: dict):
    phone = (body.get("phone") or "").strip()
    if not phone or len(phone) < 8:
        raise HTTPException(status_code=400, detail="手机号格式不对")
    code = make_otp()
    await save_otp(phone, code, ttl_seconds=300)
    ok = send_sms(phone, code)
    if not ok:
        raise HTTPException(status_code=500, detail="短信发送失败，请稍后重试")
    return {"status": "ok"}


@router.post("/auth/test-login")
async def test_login(body: dict | None = None):
    """开发测试入口：传 {"username": "alice"} 直接拿 JWT，不走短信验证。
    仅 DEV_MODE=1 时启用；生产环境（DEV_MODE 关掉）返回 404 把口子堵上。"""
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    body = body or {}
    username = (body.get("username") or "tester").strip() or "tester"
    await get_or_create_user(username)
    balance = await get_strawberry_balance(username)
    token = create_token(username)
    return {"token": token, "username": username, "balance": balance}


@router.post("/auth/verify-otp")
async def verify_otp_api(body: dict):
    phone = (body.get("phone") or "").strip()
    code  = (body.get("code")  or "").strip()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="参数缺失")
    ok = await check_and_consume_otp(phone, code)
    if not ok:
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    user = await get_or_create_user_by_phone(phone)
    token = create_token(user["username"])
    return {
        "token":    token,
        "username": user["username"],
        "balance":  user.get("strawberry_balance", 200),
    }


@router.post("/auth/redeem-invite")
async def redeem_invite_api(body: dict):
    """内测邀请码登录：输码即进。码预绑定用户名，首次兑换建号，老号重登直接命中。"""
    code = (body.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="请输入邀请码")
    username = await redeem_invite(code)
    if not username:
        raise HTTPException(status_code=401, detail="邀请码无效")
    await get_or_create_user(username)
    balance = await get_strawberry_balance(username)
    token = create_token(username)
    return {"token": token, "username": username, "balance": balance}
