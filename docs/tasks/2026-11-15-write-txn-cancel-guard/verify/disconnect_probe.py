# -*- coding: utf-8 -*-
"""客户端断开时，请求处理协程会不会被取消（独立脚本，不依赖项目代码）。

按项目 main.py 的结构搭一个最小应用：一个纯 ASGI 中间件 + CORS + 三层 @app.middleware("http")，
用项目同版本的 fastapi / starlette / uvicorn 起在本机随机端口上。三种接口各发一次请求，
0.3 秒后直接关掉套接字，记录处理协程是被取消了还是照常跑完。

- /plain    普通 JSON 接口，处理中等待 1.5 秒
- /stream   流式接口（StreamingResponse），先吐一段再等待 1.5 秒
- /stream0  流式接口，第一段吐出之前就在等待（对应「还没开始输出就断开」）

用法：python disconnect_probe.py
"""
import asyncio
import socket
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

EVENTS = {}


def note(name, what):
    EVENTS.setdefault(name, []).append(what)


class PassThrough:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


app = FastAPI()
app.add_middleware(PassThrough)
app.add_middleware(CORSMiddleware, allow_origins=["*"])


@app.middleware("http")
async def layer_one(request: Request, call_next):
    return await call_next(request)


@app.middleware("http")
async def layer_two(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Probe"] = "1"
    return response


@app.middleware("http")
async def layer_three(request: Request, call_next):
    return await call_next(request)


async def work(name):
    note(name, "started")
    try:
        await asyncio.sleep(1.5)
        note(name, "finished")
    except asyncio.CancelledError:
        note(name, "CANCELLED")
        raise


@app.get("/plain")
async def plain():
    await work("plain")
    return {"ok": True}


@app.get("/stream")
async def stream():
    async def body():
        yield b"data: first\n\n"
        await work("stream")
        yield b"data: last\n\n"
    return StreamingResponse(body(), media_type="text/event-stream")


@app.get("/stream0")
async def stream0():
    async def body():
        await work("stream0")
        yield b"data: only\n\n"
    return StreamingResponse(body(), media_type="text/event-stream")


async def hit_and_drop(port, path):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode())
    await writer.drain()
    await asyncio.sleep(0.3)
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


async def main():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.05)
    for path in ("/plain", "/stream", "/stream0"):
        await hit_and_drop(port, path)
    await asyncio.sleep(2.2)
    server.should_exit = True
    await task
    import fastapi, starlette
    from importlib.metadata import version
    print(f"python {sys.version.split()[0]} fastapi {fastapi.__version__} starlette {starlette.__version__} "
          f"uvicorn {uvicorn.__version__} anyio {version('anyio')} loop={type(asyncio.get_running_loop()).__module__}")
    for name in ("plain", "stream", "stream0"):
        print(f"DISCONNECT_PROBE {name}: {' -> '.join(EVENTS.get(name, ['(never started)']))}")


if __name__ == "__main__":
    uvicorn.run  # noqa: B018 保证导入
    try:
        import uvloop
        uvloop.run(main())
    except ImportError:
        asyncio.run(main())
