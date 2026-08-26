# -*- coding: utf-8 -*-
"""ASGI 请求体总量限制，覆盖 Content-Length 和 chunked 请求。"""
from __future__ import annotations

from starlette.responses import JSONResponse


MAX_REQUEST_BODY_BYTES = 25 * 1024 * 1024


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = MAX_REQUEST_BODY_BYTES):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > self.max_bytes:
                await self._reject(scope, receive, send)
                return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope, receive, send):
        max_mb = self.max_bytes // (1024 * 1024)
        limit_label = f"{max_mb}MB" if max_mb else f"{self.max_bytes} bytes"
        response = JSONResponse(
            {"detail": f"请求体不能超过 {limit_label}"},
            status_code=413,
        )
        await response(scope, receive, send)
