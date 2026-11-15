# -*- coding: utf-8 -*-
"""写锁残留的确定性复现（不是常规测试，不放在 backend/tests/ 里）。

真实故障的机制（2026-11-14 在第二轮返修的代码上抓到现场后确认）：
后台任务在一次写事务里刚执行完一条查询、还没来得及取走游标时被取消。那个原生游标
没人关闭，却被取消异常的调用栈一直引用着。随后连接照常 close()，但写锁没有释放
（Python 3.14.6 实测；应是 sqlite3_close_v2 的行为：还有未收尾的语句时连接变成「僵尸」，
事务不回滚），直到游标被销毁。清理代码此时正拿着这个异常，于是整库写入等到超时。

用法：把本文件复制到某个副本的 backend/tests/test_discuss_zz_zombie_probe.py，再从该副本的
backend/ 运行

    .venv/bin/python -m pytest -q -s -p no:cacheprovider tests/test_discuss_zz_zombie_probe.py

本探针让任务恰好停在「令牌核对那条查询已执行、游标未取走」的位置再取消。任务体仿照
runner._run：写入放在 try 里，finally 里立刻用一条忙等待 0.2 秒的新连接执行 BEGIN IMMEDIATE
（此时取消异常还在向外传播，调用栈还活着，和真实的收尾代码处境相同）。
对照：没有取消保护的代码上必然报 database is locked；有保护的代码上必须立刻成功。
"""
import asyncio
from contextlib import asynccontextmanager

import aiosqlite
import pytest

import database
from discuss import store as discuss_store
from test_discuss_runner import USER, _create_group, _new_group_id, world  # noqa: F401


def _gate_after_token_check(monkeypatch):
    """Let the token-check query run, then hold its unconsumed cursor until released."""
    original = discuss_store.get_db
    entered, release = asyncio.Event(), asyncio.Event()
    fired = [False]

    @asynccontextmanager
    async def gated_db():
        async with original() as db:
            real_execute = db._execute

            async def execute(fn, *args, **kwargs):
                result = await real_execute(fn, *args, **kwargs)
                if (not fired[0] and args and isinstance(args[0], str)
                        and "run_token=?" in args[0]):
                    fired[0] = True
                    entered.set()
                    await release.wait()
                return result

            db._execute = execute
            yield db

    monkeypatch.setattr(discuss_store, "get_db", gated_db)
    return entered, release


async def _write_lock_state():
    connection = await aiosqlite.connect(database.DB_PATH, timeout=0.2)
    try:
        try:
            await connection.execute("BEGIN IMMEDIATE")
        except Exception as error:
            return f"locked ({type(error).__name__}: {error})"
        await connection.rollback()
        return "free"
    finally:
        await connection.close()


def test_cancel_between_query_and_cursor_keeps_no_write_lock(world, monkeypatch):
    group_id = _new_group_id()
    outcome = {}

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="probe-token")
        entered, release = _gate_after_token_check(monkeypatch)
        store = discuss_store.DiscussStepStore(USER, group_id, "probe-token")

        async def worker():
            try:
                await store.post_message(1, "host", "note", "探针消息")
            finally:
                # 与 runner._cleanup 相同的处境：取消异常正在传播时去拿写锁。
                outcome["lock_in_cleanup"] = await _write_lock_state()

        task = asyncio.create_task(worker())
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0.05)
        outcome["write_interrupted"] = "lock_in_cleanup" in outcome
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(flow())
    print(f"\nZOMBIE_PROBE write_interrupted_by_cancel={outcome['write_interrupted']} "
          f"lock_in_cleanup={outcome['lock_in_cleanup']}")
    assert outcome["lock_in_cleanup"] == "free", outcome
