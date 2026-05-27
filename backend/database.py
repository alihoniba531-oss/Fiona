import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "fiona.db")

import json as _json


async def _safe_migrate(db, sql: str):
    """跑一句"老库迁移"DDL（ALTER TABLE / CREATE INDEX 等）。
    "列已存在 / 索引已存在"是这类语句的预期错（库已迁过），静默吞；
    其他错误打 console 日志，便于发现真问题。"""
    try:
        await db.execute(sql)
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            return  # 已迁过，正常
        print(f"[init_db] migrate failed: {sql} -> {type(e).__name__}: {e}")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                profile_json TEXT DEFAULT '{}'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                image_path TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 兼容老库：如果列不存在则添加
        await _safe_migrate(db, "ALTER TABLE messages ADD COLUMN image_path TEXT DEFAULT NULL")
        # 用户性别 + 匹配偏好（老库迁移）
        await _safe_migrate(db, "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT NULL")
        await _safe_migrate(db, "ALTER TABLE users ADD COLUMN match_pref TEXT DEFAULT 'both'")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a TEXT NOT NULL,
                user_b TEXT NOT NULL,
                recommended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                response_a TEXT DEFAULT NULL,
                response_b TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS peer_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                peer_username TEXT NOT NULL,
                interest_topic TEXT,
                reason TEXT,
                type TEXT,
                tags_json TEXT,
                triggered_by_message_id INTEGER,
                match_layer TEXT DEFAULT 'layer1',
                seen INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 老库迁移：pending_matches 加 match_layer 列（区分 Layer 1 对话级 / Layer 2 画像级）
        await _safe_migrate(db, "ALTER TABLE pending_matches ADD COLUMN match_layer TEXT DEFAULT 'layer1'")
        # 老库迁移：matches 表加 greeting 列
        await _safe_migrate(db, "ALTER TABLE matches ADD COLUMN greeting_a TEXT DEFAULT NULL")
        await _safe_migrate(db, "ALTER TABLE matches ADD COLUMN greeting_b TEXT DEFAULT NULL")
        # ── plaza：匿名广场帖子 ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                anon_id     TEXT NOT NULL,
                media_path  TEXT NOT NULL,
                media_type  TEXT DEFAULT 'image',
                caption     TEXT DEFAULT '',
                tags_json   TEXT DEFAULT '[]',
                likes       INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _safe_migrate(db, "ALTER TABLE posts ADD COLUMN tags_json TEXT DEFAULT '[]'")
        # ── user_tag_prefs：用户标签喜好权重（全局） ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tag_prefs (
                username    TEXT NOT NULL,
                tag         TEXT NOT NULL,
                score       REAL DEFAULT 0,
                PRIMARY KEY (username, tag)
            )
        """)
        # ── user_time_tag_prefs：用户各时段标签权重 ──
        # time_slot: 凌晨/清晨/上午/中午/下午/晚上/深夜
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_time_tag_prefs (
                username    TEXT NOT NULL,
                time_slot   TEXT NOT NULL,
                tag         TEXT NOT NULL,
                score       REAL DEFAULT 0,
                PRIMARY KEY (username, time_slot, tag)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(username, created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_matches_ab ON matches(user_a, user_b)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_peer_room ON peer_messages(room_id, created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pending_user ON pending_matches(username, seen, created_at)")
        # ── user_states：底色探针持久化（一人一行 upsert）──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                username            TEXT PRIMARY KEY,
                connection_mode     TEXT DEFAULT 'exploring',
                emotional_intensity INTEGER DEFAULT 0,
                openness_level      TEXT DEFAULT 'medium',
                interest_anchor     TEXT DEFAULT 'light_connection',
                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for _col, _def in [
            ("connection_mode",     "TEXT DEFAULT 'exploring'"),
            ("emotional_intensity", "INTEGER DEFAULT 0"),
            ("openness_level",      "TEXT DEFAULT 'medium'"),
            ("interest_anchor",     "TEXT DEFAULT 'light_connection'"),
            ("updated_at",          "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ]:
            await _safe_migrate(db, f"ALTER TABLE user_states ADD COLUMN {_col} {_def}")
        # ── 手机号 + 草莓余额（老库迁移）──
        for _col, _def in [
            ("phone",              "TEXT DEFAULT NULL"),
            ("strawberry_balance", "INTEGER DEFAULT 200"),
        ]:
            await _safe_migrate(db, f"ALTER TABLE users ADD COLUMN {_col} {_def}")
        await _safe_migrate(db, "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL")
        # ── OTP 验证码表 ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                phone      TEXT NOT NULL,
                code       TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (phone)
            )
        """)
        # ── 使用埋点：events ──
        # 原始事件流，不预聚合。analyze.py 按维度汇总。
        # event_type: 'chat' / 'tool_call' / 'mode_switch' / 'match_card'
        # payload: JSON 字符串，存事件细节（如 intent / mode / model / match_type 等）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username    TEXT,
                event_type  TEXT NOT NULL,
                name        TEXT,
                payload     TEXT,
                duration_ms INTEGER,
                success     INTEGER DEFAULT 1
            )
        """)
        await _safe_migrate(db, "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
        await _safe_migrate(db, "CREATE INDEX IF NOT EXISTS idx_events_user_type ON events(username, event_type)")
        await db.commit()

async def get_or_create_user(username: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await db.execute("INSERT INTO users (username) VALUES (?)", (username,))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
                row = await cursor.fetchone()
        return dict(row)

async def delete_message(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        await db.commit()


async def get_message_owner(message_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username FROM messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def get_pending_match_owner(match_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username FROM pending_matches WHERE id = ?", (match_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None

async def save_message(username: str, role: str, content: str, image_path: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (username, role, content, image_path) VALUES (?, ?, ?, ?)",
            (username, role, content, image_path)
        )
        await db.commit()

async def get_messages(username: str, limit: int = 100) -> list[dict]:
    """取最近 limit 条消息，用于注入上下文"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content, image_path, created_at FROM messages WHERE username = ? ORDER BY created_at DESC LIMIT ?",
            (username, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]

async def get_profile(username: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT profile_json FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return {}
    try:
        return _json.loads(row["profile_json"] or "{}")
    except Exception:
        return {}

async def update_profile(username: str, profile: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET profile_json = ? WHERE username = ?",
            (_json.dumps(profile, ensure_ascii=False), username)
        )
        await db.commit()

async def get_all_profiles() -> list[dict]:
    """返回所有用户的 username + profile_json + gender，用于匹配"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT username, profile_json, gender FROM users") as cursor:
            rows = await cursor.fetchall()
    result = []
    for row in rows:
        try:
            profile = _json.loads(row["profile_json"] or "{}")
        except Exception:
            profile = {}
        if profile:
            result.append({
                "username": row["username"],
                "profile": profile,
                "gender": row["gender"],
            })
    return result


async def get_user_settings(username: str) -> dict:
    """获取用户性别 + 匹配偏好"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT gender, match_pref FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return {"gender": None, "match_pref": "both"}
    return {
        "gender": row["gender"],
        "match_pref": row["match_pref"] or "both",
    }


async def update_user_settings(username: str, gender, match_pref: str):
    """更新用户性别 + 匹配偏好"""
    if gender not in ("male", "female", None):
        gender = None
    if match_pref not in ("male", "female", "both"):
        match_pref = "both"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET gender = ?, match_pref = ? WHERE username = ?",
            (gender, match_pref, username)
        )
        await db.commit()

async def was_recently_matched(user_a: str, user_b: str, days: int = 30) -> bool:
    """检查两人在 days 天内是否已经推荐过"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id FROM matches
               WHERE ((user_a=? AND user_b=?) OR (user_a=? AND user_b=?))
               AND recommended_at > datetime('now', ?)""",
            (user_a, user_b, user_b, user_a, f"-{days} days")
        ) as cursor:
            row = await cursor.fetchone()
    return row is not None

async def save_match(user_a: str, user_b: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO matches (user_a, user_b) VALUES (?, ?)", (user_a, user_b)
        )
        await db.commit()

async def update_match_response(me: str, peer: str, response: str):
    """记录 me 对 (me ↔ peer) 这对匹配的态度。response = 'accept' / 'reject'。
    根据 matches 行实际 user_a/user_b 的顺序更新对应列；若行不存在则新建一条，
    把 me 当成 user_a。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_a FROM matches WHERE (user_a=? AND user_b=?) OR (user_a=? AND user_b=?) ORDER BY recommended_at DESC LIMIT 1",
            (me, peer, peer, me)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            match_id, actual_user_a = row
            col = "response_a" if actual_user_a == me else "response_b"
            await db.execute(f"UPDATE matches SET {col}=? WHERE id=?", (response, match_id))
        else:
            await db.execute(
                "INSERT INTO matches (user_a, user_b, response_a) VALUES (?, ?, ?)",
                (me, peer, response)
            )
        await db.commit()

async def save_peer_message(room_id: str, sender: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO peer_messages (room_id, sender, content) VALUES (?, ?, ?)",
            (room_id, sender, content)
        )
        await db.commit()

async def get_peer_messages(room_id: str, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, sender, content, created_at FROM peer_messages WHERE room_id=? ORDER BY created_at DESC LIMIT ?",
            (room_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]

async def save_pending_match(
    username: str,
    peer_username: str,
    interest_topic: str,
    reason: str,
    match_type: str,
    tags: list,
    triggered_by_message_id: int | None = None,
    match_layer: str = "layer1",
):
    """保存对话内匹配命中（待前端拉取并弹卡）。
    match_layer: 'layer1' = 对话级（A 触发，给 A/B 双方各推一张）；
                 'layer2' = 画像级（用户每次画像更新后批量算）。
    用于 _has_recent_layer2_match 判断 24h 冷却时区分两类，
    避免 B 端收到的 layer1 卡误判为 layer2 占位，让 B 自己的 layer2 跑不起来。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO pending_matches
               (username, peer_username, interest_topic, reason, type, tags_json, triggered_by_message_id, match_layer)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (username, peer_username, interest_topic, reason, match_type,
             _json.dumps(tags, ensure_ascii=False), triggered_by_message_id, match_layer)
        )
        await db.commit()


async def get_pending_matches_for_user(username: str, limit: int = 5) -> list[dict]:
    """拉未看过的匹配，按新到老。附带对方的招呼内容（若已接受并留招呼）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # 只拉 2 小时内的卡片，超时的视为自动过期不再展示
        async with db.execute(
            """SELECT id, peer_username, interest_topic, reason, type, tags_json, created_at
               FROM pending_matches
               WHERE username = ? AND seen = 0
               AND created_at > datetime('now', '-2 hours')
               ORDER BY created_at DESC LIMIT ?""",
            (username, limit)
        ) as cursor:
            rows = await cursor.fetchall()

    result = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = _json.loads(d.pop("tags_json") or "[]")
        except Exception:
            d["tags"] = []

        # 查对方是否已接受并留了招呼
        peer = d["peer_username"]
        d["peer_greeting"] = None
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT user_a, greeting_a, greeting_b FROM matches
                   WHERE (user_a=? AND user_b=?) OR (user_a=? AND user_b=?)
                   ORDER BY recommended_at DESC LIMIT 1""",
                (username, peer, peer, username)
            ) as cursor:
                m = await cursor.fetchone()
            if m:
                m = dict(m)
                # 对方是 user_a 还是 user_b？
                if m["user_a"] == peer:
                    d["peer_greeting"] = m["greeting_a"]  # 对方是 a，取 greeting_a
                else:
                    d["peer_greeting"] = m["greeting_b"]  # 对方是 b，取 greeting_b

        result.append(d)
    return result


async def save_greeting(me: str, peer: str, text: str):
    """保存 me 给 peer 的打招呼内容，写入最新一条 matches 行对应方向的列。
    若 matches 行不存在则新建一条（me 视为 user_a），与 update_match_response 行为一致，
    避免 race 或调用顺序异常时招呼内容静默丢失。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_a FROM matches WHERE (user_a=? AND user_b=?) OR (user_a=? AND user_b=?) ORDER BY recommended_at DESC LIMIT 1",
            (me, peer, peer, me)
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            match_id, actual_user_a = row
            col = "greeting_a" if actual_user_a == me else "greeting_b"
            await db.execute(f"UPDATE matches SET {col}=? WHERE id=?", (text, match_id))
        else:
            await db.execute(
                "INSERT INTO matches (user_a, user_b, greeting_a) VALUES (?, ?, ?)",
                (me, peer, text)
            )
        await db.commit()


async def upsert_user_state(
    username: str,
    connection_mode: str,
    emotional_intensity: int,
    openness_level: str,
    interest_anchor: str,
):
    """底色探针结果持久化（一人一行 upsert）"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_states
               (username, connection_mode, emotional_intensity, openness_level, interest_anchor, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(username) DO UPDATE SET
                 connection_mode     = excluded.connection_mode,
                 emotional_intensity = excluded.emotional_intensity,
                 openness_level      = excluded.openness_level,
                 interest_anchor     = excluded.interest_anchor,
                 updated_at          = CURRENT_TIMESTAMP""",
            (username, connection_mode, emotional_intensity, openness_level, interest_anchor)
        )
        await db.commit()


async def get_user_state(username: str) -> dict | None:
    """读取用户当前底色，不存在返回 None"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_states WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def mark_pending_match_seen(match_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_matches SET seen = 1 WHERE id = ?", (match_id,)
        )
        await db.commit()


async def get_recent_user_messages(username: str, limit: int = 5) -> list[dict]:
    """取该 user 最近 N 条 user 角色的消息（用于跨用户搜索）"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT content, created_at FROM messages
               WHERE username = ? AND role = 'user'
               ORDER BY created_at DESC LIMIT ?""",
            (username, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_accepted_matches(username: str) -> list[str]:
    """返回接受了和 username 匹配的对方用户名列表"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_a, user_b, response_a, response_b FROM matches
               WHERE (user_a=? OR user_b=?)
               ORDER BY recommended_at DESC""",
            (username, username)
        ) as cursor:
            rows = await cursor.fetchall()
    result = []
    seen = set()
    for row in rows:
        r = dict(row)
        if r["user_a"] == username:
            other = r["user_b"]
            accepted = r["response_a"] == "accept" and r["response_b"] == "accept"
        else:
            other = r["user_a"]
            accepted = r["response_a"] == "accept" and r["response_b"] == "accept"
        if accepted and other not in seen:
            result.append(other)
            seen.add(other)
    return result

async def save_post(anon_id: str, media_path: str, media_type: str, caption: str, tags: list) -> int:
    """保存广场帖子，返回新帖 id"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO posts (anon_id, media_path, media_type, caption, tags_json) VALUES (?,?,?,?,?)",
            (anon_id, media_path, media_type, caption, _json.dumps(tags, ensure_ascii=False))
        )
        await db.commit()
        return cursor.lastrowid


async def get_posts(limit: int = 30, offset: int = 0) -> list[dict]:
    """拉广场帖子列表，按时间倒序"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, anon_id, media_path, media_type, caption, tags_json, likes, created_at FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = _json.loads(d.pop("tags_json") or "[]")
        except Exception:
            d["tags"] = []
        result.append(d)
    return result


async def like_post(post_id: int) -> int:
    """给帖子点赞，返回新的 likes 数"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
        await db.commit()
        async with db.execute("SELECT likes FROM posts WHERE id = ?", (post_id,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


def get_time_slot() -> str:
    """
    返回当前时段标识，格式：{星期类型}-{时段}
    星期类型：工作日 / 周末
    时段：凌晨 / 清晨 / 上午 / 中午 / 下午 / 晚上 / 深夜
    示例：'工作日-深夜'  '周末-下午'
    """
    from datetime import datetime
    now = datetime.now()
    h = now.hour
    day_type = "周末" if now.weekday() >= 5 else "工作日"
    if 0 <= h < 5:   period = "凌晨"
    elif 5 <= h < 8:   period = "清晨"
    elif 8 <= h < 12:  period = "上午"
    elif 12 <= h < 14: period = "中午"
    elif 14 <= h < 18: period = "下午"
    elif 18 <= h < 22: period = "晚上"
    else:              period = "深夜"
    return f"{day_type}-{period}"


async def update_time_tag_prefs(username: str, tags: list, time_slot: str = "", delta: float = 1.0):
    """更新用户在指定时段的标签权重；time_slot 为空则用当前时段"""
    if not username or not tags:
        return
    slot = time_slot or get_time_slot()
    async with aiosqlite.connect(DB_PATH) as db:
        for tag in tags:
            await db.execute(
                """INSERT INTO user_time_tag_prefs (username, time_slot, tag, score) VALUES (?,?,?,?)
                   ON CONFLICT(username, time_slot, tag) DO UPDATE SET score = score + ?""",
                (username, slot, tag, delta, delta)
            )
        await db.commit()


async def get_time_tag_prefs(username: str, time_slot: str = "") -> dict[str, float]:
    """返回用户在指定时段的标签权重 {tag: score}；time_slot 为空则用当前时段"""
    if not username:
        return {}
    slot = time_slot or get_time_slot()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tag, score FROM user_time_tag_prefs WHERE username=? AND time_slot=?",
            (username, slot)
        ) as cursor:
            rows = await cursor.fetchall()
    return {r["tag"]: r["score"] for r in rows}


async def get_all_time_tag_prefs(username: str) -> dict[str, dict[str, float]]:
    """返回用户所有时段的标签权重 {time_slot: {tag: score}}（用于前端展示）"""
    if not username:
        return {}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT time_slot, tag, score FROM user_time_tag_prefs WHERE username=? ORDER BY time_slot, score DESC",
            (username,)
        ) as cursor:
            rows = await cursor.fetchall()
    result: dict = {}
    for r in rows:
        result.setdefault(r["time_slot"], {})[r["tag"]] = r["score"]
    return result


async def update_tag_prefs(username: str, tags: list, delta: float = 1.0):
    """用户点赞/互动后，更新全局标签权重 + 当前时段权重"""
    if not username or not tags:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        for tag in tags:
            await db.execute(
                """INSERT INTO user_tag_prefs (username, tag, score) VALUES (?,?,?)
                   ON CONFLICT(username, tag) DO UPDATE SET score = score + ?""",
                (username, tag, delta, delta)
            )
        await db.commit()
    # 同步更新时段权重
    await update_time_tag_prefs(username, tags, delta=delta)


async def save_otp(phone: str, code: str, ttl_seconds: int = 300):
    """保存/覆盖 OTP，ttl_seconds 内有效"""
    from datetime import timedelta
    expires = datetime.now() + timedelta(seconds=ttl_seconds)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO otp_codes (phone, code, expires_at)
               VALUES (?, ?, ?)
               ON CONFLICT(phone) DO UPDATE SET code=excluded.code, expires_at=excluded.expires_at, created_at=CURRENT_TIMESTAMP""",
            (phone, code, expires.strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()


async def check_and_consume_otp(phone: str, code: str) -> bool:
    """验证 OTP 并删除（一次性）。正确且未过期返回 True。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code, expires_at FROM otp_codes WHERE phone = ?", (phone,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        db_code, expires_at_str = row
        try:
            expires_at = datetime.strptime(expires_at_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False
        if datetime.now() > expires_at:
            await db.execute("DELETE FROM otp_codes WHERE phone = ?", (phone,))
            await db.commit()
            return False
        if db_code != code:
            return False
        await db.execute("DELETE FROM otp_codes WHERE phone = ?", (phone,))
        await db.commit()
        return True


async def get_or_create_user_by_phone(phone: str) -> dict:
    """用手机号查找或创建用户，返回用户行"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE phone = ?", (phone,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            # 新用户：username = 手机号，赠送 200 草莓
            await db.execute(
                "INSERT INTO users (username, phone, strawberry_balance) VALUES (?, ?, 200)",
                (phone, phone)
            )
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE phone = ?", (phone,)) as cursor:
                row = await cursor.fetchone()
        return dict(row)


async def get_strawberry_balance(username: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT strawberry_balance FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0


async def deduct_strawberry(username: str, amount: int = 10) -> int:
    """扣除草莓，返回扣后余额。余额不足时扣到 0 并返回 0。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET strawberry_balance = MAX(0, strawberry_balance - ?) WHERE username = ?",
            (amount, username)
        )
        await db.commit()
        async with db.execute(
            "SELECT strawberry_balance FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0


async def add_strawberry(username: str, amount: int) -> int:
    """充草莓，返回充后余额"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET strawberry_balance = strawberry_balance + ? WHERE username = ?",
            (amount, username)
        )
        await db.commit()
        async with db.execute(
            "SELECT strawberry_balance FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0


async def get_tag_prefs(username: str) -> dict[str, float]:
    """返回用户的标签权重字典 {tag: score}"""
    if not username:
        return {}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tag, score FROM user_tag_prefs WHERE username = ?", (username,)
        ) as cursor:
            rows = await cursor.fetchall()
    return {r["tag"]: r["score"] for r in rows}


async def get_all_messages(username: str) -> list[dict]:
    """取全部历史消息（用于聊天记录展示）"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, role, content, image_path, created_at FROM messages WHERE username = ? ORDER BY created_at ASC",
            (username,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]
