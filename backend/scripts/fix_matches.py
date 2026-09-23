# -*- coding: utf-8 -*-
import asyncio, sys, json
sys.path.insert(0, '.')
import database
import aiosqlite

async def fix():
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute('DELETE FROM pending_matches')
        await db.execute(
            '''INSERT INTO pending_matches (username, peer_username, interest_topic, reason, type, tags_json, seen)
               VALUES (?, ?, ?, ?, ?, ?, 0)''',
            ('默认用户', 'test_friend', '公路骑行',
             '他骑了 6 年公路车，从杭州骑到过上海',
             '精准对接',
             json.dumps(['骑行', '公路车', '杭州'], ensure_ascii=False))
        )
        await db.commit()
        async with db.execute('SELECT id, username, peer_username, seen FROM pending_matches') as c:
            for row in await c.fetchall():
                print(row)

asyncio.run(fix())
