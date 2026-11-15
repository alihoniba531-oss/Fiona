# -*- coding: utf-8 -*-
"""aiosqlite 写事务被取消后是否残留写锁：取消点扫描探针（独立脚本，不依赖项目代码）。

对每一种事务写法，把取消依次落在事务里每一次 aiosqlite 调用上，两种落点各扫一遍：

- delivered：工作线程已把结果交回事件循环（Future 已有结果），任务还没被唤醒，
  取消在同一轮事件循环里到达。这是真实故障的窗口。
- queued：语句已入队、还没有结果时取消到达（Future 被取消，结果随后被丢弃）。

每个取消点记录三个时刻新连接能否立刻拿到写锁（忙等待 0.2 秒）：
cleanup = 任务自己的 finally 里（取消异常还在向外传播）；
after_del = 任务已结束、任务对象已丢弃、没有做垃圾回收；
after_gc = 做过一次垃圾回收之后。
同时记录这次取消之后数据是否已经提交。

用法：python mechanism_probe.py            # 打印全部结果
"""
import asyncio
import gc
import os
import sqlite3
import sys
import tempfile

import aiosqlite
import aiosqlite.core as core


class Injector:
    def __init__(self):
        self.task = None
        self.active = False
        self.mode = None
        self.k = None
        self.n = 0
        self.labels = []
        self.fired = None
        self._arm = False

    def reset(self, mode, k):
        self.task, self.active, self.mode, self.k = None, False, mode, k
        self.n, self.labels, self.fired, self._arm = 0, [], None, False


INJ = Injector()
_orig_execute = core.Connection._execute
_orig_set_result = core.set_result


def _label(fn, args):
    name = getattr(fn, "__name__", repr(fn))
    sql = ""
    if args and isinstance(args[0], str):
        sql = " " + " ".join(args[0].split())[:38]
    return f"{name}{sql}"


async def _patched_execute(self, fn, *args, **kwargs):
    mine = INJ.active and asyncio.current_task() is INJ.task
    if mine:
        INJ.n += 1
        INJ.labels.append(_label(fn, args))
        if INJ.n == INJ.k:
            INJ.fired = INJ.labels[-1]
            if INJ.mode == "delivered":
                INJ._arm = True
            else:
                INJ.active = False
                asyncio.current_task().cancel()
    return await _orig_execute(self, fn, *args, **kwargs)


def _patched_set_result(fut, result):
    _orig_set_result(fut, result)
    if INJ._arm:
        # 结果已交回、任务尚未被唤醒：取消在同一轮事件循环里到达。
        INJ._arm = False
        INJ.active = False
        INJ.task.cancel()


core.Connection._execute = _patched_execute
core.set_result = _patched_set_result


async def lock_state(path):
    conn = await aiosqlite.connect(path, timeout=0.2)
    try:
        try:
            await conn.execute("BEGIN IMMEDIATE")
        except Exception as error:
            return "LOCKED"
        await conn.rollback()
        return "free"
    finally:
        await conn.close()


async def read_value(path):
    conn = await aiosqlite.connect(path, timeout=0.2)
    try:
        rows = await conn.execute_fetchall("SELECT COALESCE(SUM(v),0), COUNT(*) FROM t")
        return tuple(rows[0])
    finally:
        await conn.close()


# ---- 事务写法 -------------------------------------------------------------

async def a_select_plain(db):
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute("SELECT v FROM t WHERE id=1")
    await cursor.fetchone()
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")
    await db.commit()


async def b_select_with(db):
    await db.execute("BEGIN IMMEDIATE")
    async with db.execute("SELECT v FROM t WHERE id=1") as cursor:
        await cursor.fetchone()
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")
    await db.commit()


async def c_select_multi_fetchone(db):
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute("SELECT v FROM t")  # 多行，只取一行，游标不关
    await cursor.fetchone()
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")
    await db.commit()


async def d_dml_only(db):
    await db.execute("BEGIN IMMEDIATE")
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")
    await db.execute("UPDATE t SET v=v+100 WHERE id=2")
    await db.commit()


async def e_implicit_dml_then_select(db):
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")  # 隐式开启写事务
    cursor = await db.execute("SELECT v FROM t WHERE id=1")
    await cursor.fetchone()
    await db.commit()


async def f_select_only(db):
    cursor = await db.execute("SELECT v FROM t WHERE id=1")
    await cursor.fetchone()


async def g_returning(db):
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute("UPDATE t SET v=v+100 WHERE id=1 RETURNING v")
    await cursor.fetchone()
    await db.commit()


async def h_execute_fetchall(db):
    await db.execute("BEGIN IMMEDIATE")
    await db.execute_fetchall("SELECT v FROM t")
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")
    await db.commit()


async def i_select_then_implicit_dml(db):
    cursor = await db.execute("SELECT v FROM t WHERE id=1")  # 此时还没有写事务
    await cursor.fetchone()
    await db.execute("UPDATE t SET v=v+100 WHERE id=1")
    await db.commit()


def with_rollback(body, catch):
    async def wrapped(db):
        try:
            await body(db)
        except catch:
            await db.rollback()
            raise
    wrapped.__name__ = f"{body.__name__}+rollback[{catch.__name__}]"
    return wrapped


async def shielded_task(path, body):
    """整个事务放进独立任务，shield 住，跑完再交还取消（项目里 _drain 的做法）。"""
    async def transaction():
        async with aiosqlite.connect(path, timeout=5) as db:
            await body(db)

    task = asyncio.create_task(transaction())
    cancelled = False
    while True:
        try:
            await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.done() and task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError


BODIES = [
    a_select_plain,
    b_select_with,
    c_select_multi_fetchone,
    d_dml_only,
    e_implicit_dml_then_select,
    f_select_only,
    g_returning,
    h_execute_fetchall,
    i_select_then_implicit_dml,
    with_rollback(a_select_plain, BaseException),
    with_rollback(a_select_plain, Exception),
    with_rollback(c_select_multi_fetchone, BaseException),
    with_rollback(g_returning, BaseException),
]


async def run_case(path, body, mode, k):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS t")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?,?)", [(1, 1), (2, 2), (3, 3)])
    conn.commit()
    conn.close()
    before = await read_value(path)
    outcome = {}
    INJ.reset(mode, k)

    async def victim():
        try:
            async with aiosqlite.connect(path, timeout=5) as db:
                INJ.active = True
                await body(db)
                INJ.active = False
        finally:
            INJ.active = False
            outcome["cleanup"] = await lock_state(path)

    task = asyncio.create_task(victim())
    INJ.task = task
    try:
        await task
        outcome["cancelled"] = False
    except asyncio.CancelledError:
        outcome["cancelled"] = True
    del task
    INJ.task = None
    outcome["after_del"] = await lock_state(path)
    gc.collect()
    outcome["after_gc"] = await lock_state(path)
    after = await read_value(path)
    outcome["committed"] = after != before
    outcome["fired"] = INJ.fired
    return outcome


async def main():
    gc.disable()
    tmp = tempfile.mkdtemp(prefix="zombie-probe-")
    path = os.path.join(tmp, "probe.db")
    print(f"python {sys.version.split()[0]} sqlite {sqlite3.sqlite_version} aiosqlite {aiosqlite.__version__}")
    bad = 0
    for body in BODIES:
        print(f"\n## {body.__name__}")
        for mode in ("delivered", "queued"):
            k = 1
            while True:
                outcome = await run_case(path, body, mode, k)
                if outcome["fired"] is None:
                    break
                flag = ""
                if "LOCKED" in (outcome["cleanup"], outcome["after_del"], outcome["after_gc"]):
                    flag = "  <== 写锁残留"
                    bad += 1
                print(f"  {mode:9s} k={k} [{outcome['fired']:<52s}] cleanup={outcome['cleanup']:<6s} "
                      f"after_del={outcome['after_del']:<6s} after_gc={outcome['after_gc']:<6s} "
                      f"cancelled={outcome['cancelled']!s:<5s} committed={outcome['committed']!s:<5s}{flag}")
                k += 1
    print(f"\nTOTAL cancel points with residual write lock: {bad}")


if __name__ == "__main__":
    asyncio.run(main())
