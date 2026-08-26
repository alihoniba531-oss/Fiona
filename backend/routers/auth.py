# -*- coding: utf-8 -*-
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from auth import TOKEN_EXPIRE_DAYS, create_token, make_otp
from auth_dep import get_current_user
from database import (check_and_consume_otp, get_or_create_user, get_or_create_user_by_phone,
                      get_strawberry_balance, redeem_invite, revoke_user_sessions, save_otp)
from rate_limit import limiter
from sms import send_sms

router = APIRouter()


def _login_response(user: dict, balance: int) -> JSONResponse:
    username = user["username"]
    token = create_token(username, int(user.get("session_version", 0)))
    response = JSONResponse({"username": username, "balance": balance})
    response.set_cookie(
        key="fiona_token",
        value=token,
        max_age=TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
        httponly=True,
        secure=os.getenv("DEV_MODE", "0") != "1",
        samesite="lax",
    )
    return response


# ── 认证端点 ────────────────────────────────────────────────────

@router.post("/auth/send-otp")
async def send_otp_api(body: dict):
    # OTP 这条线是死入口：send_sms 仍是 stub（只 print 不真发），且无限流、错码不删码可爆破。
    # 接真实短信服务商 + 限流 + 错误次数上限后再开放；当前仅 DEV_MODE=1 放行，生产 404 堵死。
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
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
    user = await get_or_create_user(username)
    balance = await get_strawberry_balance(username)
    return _login_response(user, balance)


@router.post("/auth/verify-otp")
async def verify_otp_api(body: dict):
    # 同上：OTP 验证是死入口，错码不删码可在 300s 窗口内爆破。
    # 接真实短信 + 限流 + 错误次数上限后再开放；当前仅 DEV_MODE=1 放行，生产 404 堵死。
    if os.getenv("DEV_MODE", "0") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    phone = (body.get("phone") or "").strip()
    code  = (body.get("code")  or "").strip()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="参数缺失")
    ok = await check_and_consume_otp(phone, code)
    if not ok:
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    user = await get_or_create_user_by_phone(phone)
    return _login_response(user, user.get("strawberry_balance", 200))


@router.post("/auth/redeem-invite")
@limiter.limit("10/minute")
async def redeem_invite_api(request: Request, body: dict):
    """内测邀请码登录：输码即进。码预绑定用户名，首次兑换建号，老号重登直接命中。
    限流 10/分钟/IP（防邀请码爆破）；request 参数供 slowapi 取限流 key。"""
    code = (body.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="请输入邀请码")
    username = await redeem_invite(code)
    if not username:
        raise HTTPException(status_code=401, detail="邀请码无效")
    user = await get_or_create_user(username)
    balance = await get_strawberry_balance(username)
    return _login_response(user, balance)


@router.post("/auth/logout")
async def logout_api(user: str = Depends(get_current_user)):
    """撤销当前账号此前签发的全部 JWT，并清除 HttpOnly 会话 Cookie。"""
    await revoke_user_sessions(user)
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("fiona_token", path="/")
    return response
