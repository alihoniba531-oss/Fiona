# -*- coding: utf-8 -*-
"""sqlite 连接与受保护写操作的取消安全封装。

``connect`` 的用法与 ``aiosqlite.connect`` 的 ``async with`` 形式相同。作用域
内有异常离开（包括取消）时先回滚再关闭，避免没提交的写事务继续占着写锁；
``drain`` 把操作放进独立任务，等它结束之后再交还调用方收到的取消。
"""
from __future__ import annotations

import asyncio
import contextlib

import aiosqlite


@contextlib.asynccontextmanager
async def connect(*args, **kwargs):
    """打开一个退出时先回滚、再关闭的 aiosqlite 连接。

    参数原样透传给 ``aiosqlite.connect``，交给 ``async with`` 的就是它返回的
    连接对象本身；正常退出仍由该连接自己的 ``__aexit__`` 关闭，不额外提交或
    回滚。回滚自己抛出的普通异常会被吞掉，向外传播的仍是原异常；回滚等待时
    再次被取消也不会跳过关闭，因为关闭在 ``async with`` 的退出路径上。
    """
    async with aiosqlite.connect(*args, **kwargs) as db:
        try:
            yield db
        except BaseException:
            with contextlib.suppress(Exception):
                await db.rollback()
            raise


async def drain(operation):
    """等 ``operation`` 结束后，再把调用方的取消交还。

    ``operation`` 放进独立任务并屏蔽调用方取消。调用方没被取消时结果或异常
    原样返回；调用方被取消时，等内层任务结束之后再抛 ``CancelledError``。若
    内层抛的是普通异常，把它设为该 ``CancelledError`` 的 ``__cause__``。
    """
    task = asyncio.ensure_future(operation)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.done() and task.cancelled():
                raise
            cancelled = True
        except Exception as exc:
            if cancelled:
                raise asyncio.CancelledError() from exc
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result
