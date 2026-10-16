"""工作室准入；拒绝时隐藏功能是否存在。"""
from fastapi import HTTPException, Request, Response

from studio.config import get_settings


PRIVATE_HEADERS = {"Cache-Control": "private, no-store"}


def allow_studio(user: str | None, auth_method: str | None) -> bool:
    settings = get_settings()
    return bool(
        settings.enabled
        and user in settings.owners
        and (auth_method == "jwt" or (auth_method == "dev" and not settings.require_jwt))
    )


async def studio_user(request: Request, response: Response) -> str:
    # 身份和鉴权通道只接受主中间件验证的结果，不从请求参数推测。
    user = getattr(request.state, "user", None)
    method = getattr(request.state, "auth_method", None)
    if not allow_studio(user, method):
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)
    response.headers.update(PRIVATE_HEADERS)
    return user
