# -*- coding: utf-8 -*-
"""应用级后台任务追踪，避免异常无人读取或关机时遗留悬挂任务。"""
import asyncio
from collections.abc import Coroutine
from typing import Any


_background_tasks: set[asyncio.Task[Any]] = set()


def _task_finished(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    if error is not None:
        label = task.get_name()
        # 不输出异常正文，避免供应商错误意外携带提示词或用户内容。
        print(
            f"[background] task={label} failed type={type(error).__name__}",
            flush=True,
        )


def create_background_task(coro: Coroutine[Any, Any, Any], *, label: str) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=label)
    _background_tasks.add(task)
    task.add_done_callback(_task_finished)
    return task


async def shutdown_background_tasks() -> None:
    tasks = list(_background_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
