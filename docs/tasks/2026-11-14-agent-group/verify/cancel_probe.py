# -*- coding: utf-8 -*-
"""取消探针：真实后台任务在随机时刻被取消后，数据库写锁不得残留。

这不是常规测试，不放在 backend/tests/ 里。用法：把本文件复制到某个副本的
backend/tests/test_discuss_zz_cancel_probe.py，再从该副本的 backend/ 运行

    PROBE_ITER=300 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_zz_cancel_probe.py

每一轮：建群 → 起真实的后台任务（模型与搜索都是假的）→ 在随机时刻取消（一半的轮次
紧接着再取消一次）→ 等任务结束 → 用一条忙等待只有 0.2 秒的新连接执行 BEGIN IMMEDIATE。
拿不到写锁就记一次「残留」，并换一个新库继续。立项阶段与调研阶段各测一次。
对照：在第三轮返修之前的代码上运行应当出现残留，之后应当为 0。
"""
import asyncio
import os
import random

import aiosqlite

import database
from discuss import runner
from discuss import store as discuss_store
from test_discuss_runner import USER, _create_group, _new_group_id, world  # noqa: F401

ITERATIONS = int(os.environ.get("PROBE_ITER", "300"))
SEED = int(os.environ.get("PROBE_SEED", "20261114"))
MAX_LEAKS = 5


async def _lock_free():
    connection = await aiosqlite.connect(database.DB_PATH, timeout=0.2)
    try:
        try:
            await connection.execute("BEGIN IMMEDIATE")
        except Exception:
            return False
        await connection.rollback()
        return True
    finally:
        await connection.close()


async def _cancel_at_random(task, rng, max_delay):
    await asyncio.sleep(rng.uniform(0, max_delay))
    task.cancel()
    if rng.random() < 0.5:
        await asyncio.sleep(rng.uniform(0, 0.002))
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_random_cancellation_never_leaves_write_lock(world, monkeypatch, tmp_path):
    rng = random.Random(SEED)
    leaks, cancelled_mid_run, databases = [], 0, [0]

    async def fresh_database():
        databases[0] += 1
        monkeypatch.setattr(database, "DB_PATH", str(tmp_path / f"probe-{databases[0]}.db"))
        await database.init_db()
        await database.get_or_create_user(USER)

    async def one_phase(group_id, phase, max_delay, index):
        nonlocal cancelled_mid_run
        task = await runner.start_group(group_id, USER)
        if task is None:
            return True
        await _cancel_at_random(task, rng, max_delay)
        if task.cancelled():
            cancelled_mid_run += 1
        if await _lock_free():
            return True
        leaks.append((index, phase))
        await fresh_database()
        return False

    async def flow():
        for index in range(ITERATIONS):
            if len(leaks) >= MAX_LEAKS:
                break
            group_id = _new_group_id()
            await _create_group(group_id)
            if not await one_phase(group_id, "planning", 0.02, index):
                continue
            # 让立项跑完，再测调研阶段（写入更密）。
            await runner.cancel_group(group_id, USER)
            task = await runner.start_group(group_id, USER)
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            group = await discuss_store.get_group(USER, group_id)
            if group is None or group["status"] != "awaiting_start":
                continue
            await discuss_store.update_group(USER, group_id, status="running")
            if not await one_phase(group_id, "running", 0.08, index):
                continue
            await runner.cancel_group(group_id, USER)

    asyncio.run(flow())
    print(f"\nPROBE iterations={ITERATIONS} seed={SEED} cancelled_mid_run={cancelled_mid_run} "
          f"leaks={len(leaks)} detail={leaks}")
    # 正控：必须真的有任务在运行途中被取消，否则这个探针什么也没测到。
    assert cancelled_mid_run >= ITERATIONS // 4, cancelled_mid_run
    assert leaks == [], leaks
