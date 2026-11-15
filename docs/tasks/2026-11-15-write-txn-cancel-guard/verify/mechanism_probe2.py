# -*- coding: utf-8 -*-
"""mechanism_probe.py 的补充实测（同目录运行）。

A. 取消经 anyio 的取消域投递（Starlette 流式响应在客户端断开时就是这样取消的）。
B. 被取消的任务对象还被别人拿着时，写锁挂多久（仿照「task.cancel(); await gather(task,
   return_exceptions=True); 接着去写库」的收尾写法）。
C. 修法验证：连接层统一「出任何异常先回滚再关连接」，对全部写法、全部取消点是否都不留写锁。
D. 修法验证：整个事务放进受保护任务（shield，跑完再交还取消）。

用法：python mechanism_probe2.py
"""
import asyncio
import gc
import os
import sqlite3
import tempfile
from contextlib import asynccontextmanager, suppress

import aiosqlite
import anyio

import mechanism_probe as base
from mechanism_probe import INJ, lock_state, read_value


def reset_db(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS t")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?,?)", [(1, 1), (2, 2), (3, 3)])
    conn.commit()
    conn.close()


@asynccontextmanager
async def plain_connect(path):
    async with aiosqlite.connect(path, timeout=5) as db:
        yield db


@asynccontextmanager
async def guarded_connect(path):
    """连接层回滚：任何异常离开连接作用域之前先回滚。"""
    async with aiosqlite.connect(path, timeout=5) as db:
        try:
            yield db
        except BaseException:
            with suppress(Exception):
                await db.rollback()
            raise


async def sweep(path, body, connect, mode, *, via_anyio=False, shielded=False):
    """Return list of (k, fired, cleanup, cancelled, committed)."""
    rows = []
    k = 1
    while True:
        reset_db(path)
        before = await read_value(path)
        outcome = {}
        INJ.reset(mode, k)
        scope_holder = {}

        async def transaction():
            async with connect(path) as db:
                INJ.active = True
                await body(db)
                INJ.active = False

        async def victim():
            try:
                if shielded:
                    inner = asyncio.create_task(transaction())
                    INJ.task = inner  # 计数落在事务任务里的语句上
                    cancelled = False
                    while True:
                        try:
                            await asyncio.shield(inner)
                            break
                        except asyncio.CancelledError:
                            if inner.done() and inner.cancelled():
                                raise
                            cancelled = True
                    if cancelled:
                        raise asyncio.CancelledError
                else:
                    await transaction()
            finally:
                INJ.active = False
                if via_anyio:
                    # anyio 的取消会在每次等待时重新送达；真实的收尾代码要写库就得先屏蔽，这里照做。
                    with anyio.CancelScope(shield=True):
                        outcome["cleanup"] = await lock_state(path)
                else:
                    outcome["cleanup"] = await lock_state(path)

        if via_anyio:
            async def host():
                with anyio.CancelScope() as scope:
                    scope_holder["scope"] = scope
                    INJ.task = asyncio.current_task()
                    await victim()
                outcome["cancelled"] = scope.cancelled_caught

            # 让注入器调用 scope.cancel() 而不是 task.cancel()
            class _Proxy:
                def cancel(self_inner):
                    scope_holder["scope"].cancel()
            real_task = asyncio.create_task(host())
            orig_set_result = base.core.set_result

            def patched(fut, result):
                base._orig_set_result(fut, result)
                if INJ._arm:
                    INJ._arm = False
                    INJ.active = False
                    scope_holder["scope"].cancel()
            base.core.set_result = patched
            try:
                await real_task
            finally:
                base.core.set_result = orig_set_result
        else:
            task = asyncio.create_task(victim())
            if not shielded:
                INJ.task = task
            else:
                # 受保护模式下取消的是外层任务，但窗口仍按事务任务里的语句计
                outer = task
                orig_set_result = base.core.set_result

                def patched(fut, result):
                    base._orig_set_result(fut, result)
                    if INJ._arm:
                        INJ._arm = False
                        INJ.active = False
                        outer.cancel()
                base.core.set_result = patched
            try:
                await task
                outcome["cancelled"] = False
            except asyncio.CancelledError:
                outcome["cancelled"] = True
            finally:
                if shielded:
                    base.core.set_result = orig_set_result
            del task
        INJ.task = None
        if INJ.fired is None:
            break
        after = await read_value(path)
        rows.append((k, INJ.fired, outcome.get("cleanup"), outcome.get("cancelled"), after != before))
        k += 1
        if k > 40:
            break
    return rows


def summarize(title, rows):
    locked = [r for r in rows if r[2] == "LOCKED"]
    lost = [r for r in rows if not r[3]]
    unmeasured = [r for r in rows if r[2] not in ("LOCKED", "free")]
    print(f"  {title:<58s} 取消点 {len(rows):2d}  残留写锁 {len(locked):2d}  取消未送达 {len(lost):2d}  没测到 {len(unmeasured):2d}"
          + ("   <== " + "; ".join(f"k={r[0]} {r[1]}" for r in locked) if locked else ""))
    return len(locked), len(lost)


async def part_a(path):
    print("\n## A. 取消经 anyio 取消域投递（delivered 窗口 = 结果已交回、任务未唤醒）")
    for body in base.BODIES[:9]:
        rows = await sweep(path, body, plain_connect, "delivered", via_anyio=True)
        summarize(body.__name__, rows)


async def part_b(path):
    print("\n## B. 被取消的任务对象被拿着时写锁挂多久（写法 a_select_plain，取消落在 SELECT 的 delivered 窗口）")
    reset_db(path)
    INJ.reset("delivered", 2)

    async def worker():
        async with aiosqlite.connect(path, timeout=5) as db:
            INJ.active = True
            await base.a_select_plain(db)

    task = asyncio.create_task(worker())
    INJ.task = task
    results = await asyncio.gather(task, return_exceptions=True)
    INJ.active = False
    print(f"  gather 返回: {type(results[0]).__name__}")
    del results
    print(f"  gather 之后、任务对象仍被局部变量引用: {await lock_state(path)}")
    holder = [task]
    del task
    INJ.task = None
    print(f"  任务对象只被一个列表（例如任务登记表）引用: {await lock_state(path)}")
    holder.clear()
    print(f"  任务对象已无人引用（未做垃圾回收）: {await lock_state(path)}")
    gc.collect()
    print(f"  垃圾回收之后: {await lock_state(path)}")


async def part_c(path):
    print("\n## C. 修法一：连接层统一回滚（原生取消 delivered / queued，以及 anyio 取消）")
    total = 0
    for body in base.BODIES[:9]:
        for mode in ("delivered", "queued"):
            rows = await sweep(path, body, guarded_connect, mode)
            locked, _ = summarize(f"{body.__name__} [{mode}]", rows)
            total += locked
        rows = await sweep(path, body, guarded_connect, "delivered", via_anyio=True)
        locked, _ = summarize(f"{body.__name__} [anyio]", rows)
        total += locked
    print(f"  修法一残留写锁合计: {total}")


async def part_d(path):
    print("\n## D. 修法二：整个事务放进受保护任务（外层被取消，事务照常跑完）")
    total = 0
    for body in base.BODIES[:9]:
        rows = await sweep(path, body, plain_connect, "delivered", shielded=True)
        locked, lost = summarize(body.__name__, rows)
        uncommitted = [r for r in rows if not r[4] and body.__name__ != "f_select_only"]
        if uncommitted:
            print(f"     未提交的取消点: {[r[0] for r in uncommitted]}")
        total += locked
    print(f"  修法二残留写锁合计: {total}")


async def main():
    gc.disable()
    path = os.path.join(tempfile.mkdtemp(prefix="zombie-probe2-"), "probe.db")
    await part_a(path)
    await part_b(path)
    await part_c(path)
    await part_d(path)


if __name__ == "__main__":
    asyncio.run(main())
