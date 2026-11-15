# -*- coding: utf-8 -*-
"""门禁探针：被测协程在某个取消点上吞掉了取消，取消点扫描会不会发现。

用法：在 backend/ 下运行  .venv/bin/python -B <本文件>
"""
import asyncio, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import aiosqlite
from cancel_sweep import sweep_cancel_points, write_lock_is_free

path = os.path.join(tempfile.mkdtemp(prefix="sweep-trunc-"), "t.db")
with sqlite3.connect(path) as db:
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    db.execute("INSERT INTO t VALUES (1, 10)")


async def swallowing_victim():
    async with aiosqlite.connect(path, timeout=0.2) as db:
        await db.execute("BEGIN IMMEDIATE")                       # 第 1 次调用
        try:
            await db.execute("UPDATE t SET v = v + 1 WHERE id=1")  # 第 2 次调用：取消在这里被吞掉
        except asyncio.CancelledError:
            pass
        await db.execute("UPDATE t SET v = v + 1 WHERE id=1")      # 第 3 次调用
        await db.commit()                                          # 第 4 次调用


async def check(point):
    return await write_lock_is_free(path)


async def main():
    points = await sweep_cancel_points(swallowing_victim, check=check, mode="delivered", cancel="task")
    print("SWEEP_TRUNCATION records:", [(p.k, p.label, p.cancelled) for p in points])
    print("SWEEP_TRUNCATION all_cancelled_true:", all(p.cancelled for p in points),
          "| 被测协程一共有 5 次 aiosqlite 调用（含关闭），扫到", len(points), "个")

asyncio.run(main())
