# -*- coding: utf-8 -*-
"""门禁探针：用裸 aiosqlite.connect（没有任何保护）跑「多行查询只取一行、游标不关」这种写法，
看 cancel_sweep 的 anyio 模式能不能测出残留写锁。对照：把同一个检查放进被测协程自己的
finally 里（屏蔽取消），也就是真实收尾代码所处的位置。

用法：在 backend/ 下运行  .venv/bin/python -B <本文件>
"""
import asyncio, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import aiosqlite, anyio
from cancel_sweep import sweep_cancel_points, write_lock_is_free

path = os.path.join(tempfile.mkdtemp(prefix="sweep-anyio-"), "t.db")
with sqlite3.connect(path) as db:
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    db.executemany("INSERT INTO t VALUES (?, ?)", [(1, 10), (2, 20)])

inside = []


async def body(db):
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute("SELECT id, v FROM t ORDER BY id")   # 多行，只取一行，游标不关
    await cursor.fetchone()
    await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
    await db.commit()


async def victim():
    try:
        async with aiosqlite.connect(path, timeout=0.2) as db:
            await body(db)
    finally:
        with anyio.CancelScope(shield=True):
            inside.append(await write_lock_is_free(path))


async def check(point):
    return await write_lock_is_free(path)


async def prepare():
    inside.append("|")


async def main():
    points = await sweep_cancel_points(victim, check=check, prepare=prepare, mode="delivered", cancel="anyio")
    outside = [p.check_result for p in points]
    per_point, cur = [], []
    for item in inside:
        if item == "|":
            if cur: per_point.append(cur[-1])
            cur = []
        else:
            cur.append(item)
    print("SWEEP_ANYIO 取消点:", [(p.k, p.label[:28]) for p in points])
    print("SWEEP_ANYIO 辅助模块的检查（任务结束之后）写锁空闲:", outside)
    print("SWEEP_ANYIO 被测协程自己的 finally 里（屏蔽取消）写锁空闲:", per_point[:len(points)])

asyncio.run(main())
