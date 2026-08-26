import aiosqlite
import os
from datetime import datetime

DB_PATH = os.getenv("FIONA_DB_PATH") or os.path.join(os.path.dirname(__file__), "fiona.db")

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
        print(f"[init_db] migrate failed type={type(e).__name__}")


async def _users_exist(db, *usernames: str) -> bool:
    unique = tuple(dict.fromkeys(name for name in usernames if name))
    if not unique:
        return False
    placeholders = ",".join("?" for _ in unique)
    async with db.execute(
        f"SELECT COUNT(*) FROM users WHERE username IN ({placeholders})",
        unique,
    ) as cursor:
        count = (await cursor.fetchone())[0]
    return count == len(unique)


async def _peer_room_is_accepted(db, room_id: str, sender: str) -> bool:
    """在当前事务中确认 sender 属于房间，且这对用户的最新决定仍是双方接受。"""
    parts = room_id.split("__")
    if len(parts) != 2 or sender not in parts or parts[0] == parts[1]:
        return False
    peer = parts[1] if parts[0] == sender else parts[0]
    if "__".join(sorted((sender, peer))) != room_id:
        return False
    if not await _users_exist(db, sender, peer):
        return False
    async with db.execute(
        """SELECT response_a, response_b FROM matches
           WHERE (user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)
           ORDER BY recommended_at DESC, id DESC LIMIT 1""",
        (sender, peer, peer, sender),
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0] == "accept" and row[1] == "accept")


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
        # JWT 会话版本：退出/删号时递增即可立即撤销此前签发的全部 token。
        await _safe_migrate(db, "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
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
        # anon_id 只用于对外展示；真实 owner 只在库内用于完整账户删除。
        await _safe_migrate(db, "ALTER TABLE posts ADD COLUMN owner_username TEXT DEFAULT NULL")
        # ── post_likes：谁赞过哪条帖子（点赞去重）──
        # (post_id, username) 唯一,同一登录用户对同一帖只能赞一次,防无限刷赞。
        await db.execute("""
            CREATE TABLE IF NOT EXISTS post_likes (
                post_id     INTEGER NOT NULL,
                username    TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (post_id, username)
            )
        """)
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
        await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_owner ON posts(owner_username)")
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
        # ── 内测邀请码 ──
        # 每个码预绑定一个用户名；兑换即登录该号，无需短信。redeemed_at 记首次使用。
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                code        TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                note        TEXT DEFAULT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                redeemed_at TIMESTAMP DEFAULT NULL
            )
        """)
        await _safe_migrate(db, "ALTER TABLE invite_codes ADD COLUMN revoked_at TIMESTAMP DEFAULT NULL")
        await _safe_migrate(db, "ALTER TABLE invite_codes ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0")
        await _safe_migrate(db, "ALTER TABLE invite_codes ADD COLUMN last_used_at TIMESTAMP DEFAULT NULL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS upload_cleanup_queue (
                path       TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 能确定归属的旧广场帖回填 owner_username；无法匹配的历史行保持 NULL，
        # 删除账户时还会再次按当前 HMAC + 旧 MD5 别名兜底查找。
        try:
            import hashlib
            from utils.pseudonym import anonymous_id
            async with db.execute("SELECT username FROM users") as cursor:
                existing_users = await cursor.fetchall()
            for (existing_username,) in existing_users:
                aliases = (
                    anonymous_id(existing_username, "plaza-author", length=12),
                    hashlib.md5(("fiona_plaza_" + existing_username).encode()).hexdigest()[:8],
                )
                await db.execute(
                    """UPDATE posts SET owner_username = ?
                       WHERE owner_username IS NULL AND anon_id IN (?, ?)""",
                    (existing_username, *aliases),
                )
        except Exception as exc:
            print(f"[init_db] post owner backfill failed type={type(exc).__name__}")
        await db.commit()

async def get_or_create_user(username: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
        return dict(row)

async def _queue_unreferenced_uploads(db, paths: list[str]) -> list[str]:
    """把当前事务删除后已无消息/帖子引用的上传路径加入持久化清理队列。"""
    unreferenced: list[str] = []
    for path in dict.fromkeys(path for path in paths if path):
        async with db.execute(
            """SELECT EXISTS(SELECT 1 FROM messages WHERE image_path = ?)
                      OR EXISTS(SELECT 1 FROM posts WHERE media_path = ?)""",
            (path, path),
        ) as cursor:
            referenced = (await cursor.fetchone())[0]
        if referenced:
            continue
        unreferenced.append(path)
        await db.execute(
            "INSERT OR IGNORE INTO upload_cleanup_queue (path) VALUES (?)",
            (path,),
        )
    return unreferenced


async def delete_message_for_user(message_id: int, username: str) -> dict:
    """原子校验消息归属、删除记录，并登记不再被引用的附件。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT username, image_path FROM messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await db.rollback()
            return {"status": "not_found", "upload_paths": []}
        if row[0] != username:
            await db.rollback()
            return {"status": "forbidden", "upload_paths": []}
        await db.execute(
            "DELETE FROM messages WHERE id = ? AND username = ?",
            (message_id, username),
        )
        upload_paths = await _queue_unreferenced_uploads(db, [row[1]])
        await db.commit()
        return {"status": "deleted", "upload_paths": upload_paths}


async def clear_message_history(username: str) -> list[str]:
    """原子清空用户消息，并登记清空后已无引用的附件。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT image_path FROM messages WHERE username = ? AND image_path IS NOT NULL",
            (username,),
        ) as cursor:
            paths = [row[0] for row in await cursor.fetchall() if row[0]]
        await db.execute("DELETE FROM messages WHERE username = ?", (username,))
        upload_paths = await _queue_unreferenced_uploads(db, paths)
        await db.commit()
        return upload_paths


async def get_pending_match_owner(match_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username FROM pending_matches WHERE id = ?", (match_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None

async def save_message(username: str, role: str, content: str, image_path: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, username):
            await db.rollback()
            return False
        await db.execute(
            "INSERT INTO messages (username, role, content, image_path) VALUES (?, ?, ?, ?)",
            (username, role, content, image_path)
        )
        await db.commit()
        return True

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

async def count_messages(username: str) -> int:
    """该用户的消息总数，用于成长阶段路由（区别于注入上下文的截断窗口）"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0

async def create_invite(code: str, username: str, note: str | None = None) -> bool:
    """登记一个邀请码→用户名。已存在则不覆盖，返回是否新建。"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO invite_codes (code, username, note) VALUES (?, ?, ?)",
            (code, username, note),
        )
        await db.commit()
    return cur.rowcount > 0

async def redeem_invite(code: str) -> str | None:
    """原子兑换一个未撤销的邀请码；记录首次/最近使用时间和使用次数。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            """UPDATE invite_codes
               SET redeemed_at = COALESCE(redeemed_at, CURRENT_TIMESTAMP),
                   last_used_at = CURRENT_TIMESTAMP,
                   use_count = use_count + 1
               WHERE code = ? AND revoked_at IS NULL
               RETURNING username""",
            (code,),
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()
        return row["username"] if row else None


async def revoke_invite(code: str) -> bool:
    """撤销邀请码并使其绑定账号的现有会话失效。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            """UPDATE invite_codes SET revoked_at = CURRENT_TIMESTAMP
               WHERE code = ? AND revoked_at IS NULL
               RETURNING username""",
            (code,),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE users SET session_version = session_version + 1 WHERE username = ?",
                (row["username"],),
            )
        await db.commit()
        return row is not None


async def rotate_invite(old_code: str, new_code: str) -> bool:
    """把邀请码原子轮换为新码，保留绑定用户名和备注。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            """SELECT username, note FROM invite_codes
               WHERE code = ? AND revoked_at IS NULL""",
            (old_code,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            await db.rollback()
            return False
        try:
            await db.execute(
                "INSERT INTO invite_codes (code, username, note) VALUES (?, ?, ?)",
                (new_code, row["username"], row["note"]),
            )
        except aiosqlite.IntegrityError:
            await db.rollback()
            return False
        await db.execute(
            "UPDATE invite_codes SET revoked_at = CURRENT_TIMESTAMP WHERE code = ?",
            (old_code,),
        )
        await db.execute(
            "UPDATE users SET session_version = session_version + 1 WHERE username = ?",
            (row["username"],),
        )
        await db.commit()
        return True

async def list_invites() -> list[dict]:
    """列出邀请码状态，供本机管理脚本使用。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT code, username, note, redeemed_at, revoked_at,
                      use_count, last_used_at
               FROM invite_codes ORDER BY created_at"""
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_session_version(username: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT session_version FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else None


async def is_session_valid(username: str, session_version: int) -> bool:
    current = await get_session_version(username)
    return current is not None and current == session_version


async def revoke_user_sessions(username: str) -> bool:
    """撤销用户此前签发的全部 JWT。"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE users SET session_version = session_version + 1 WHERE username = ?",
            (username,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_account_data(username: str) -> dict:
    """在单个事务中删除账号及所有可关联数据库记录。

    返回删除后已无数据库引用的上传路径，由路由在事务提交后清理文件。
    """
    import hashlib
    from utils.pseudonym import anonymous_id

    aliases = (
        anonymous_id(username, "plaza-author", length=12),
        hashlib.md5(("fiona_plaza_" + username).encode()).hexdigest()[:8],
    )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")

        async with db.execute(
            "SELECT phone FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            user_row = await cursor.fetchone()
        if user_row is None:
            await db.rollback()
            return {"deleted": False, "upload_paths": []}

        async with db.execute(
            "SELECT image_path FROM messages WHERE username = ? AND image_path IS NOT NULL",
            (username,),
        ) as cursor:
            upload_paths = [row[0] for row in await cursor.fetchall() if row[0]]

        async with db.execute(
            """SELECT id, media_path FROM posts
               WHERE owner_username = ? OR anon_id IN (?, ?)""",
            (username, *aliases),
        ) as cursor:
            owned_posts = await cursor.fetchall()
        post_ids = [int(row["id"]) for row in owned_posts]
        upload_paths.extend(row["media_path"] for row in owned_posts if row["media_path"])

        async with db.execute(
            "SELECT user_a, user_b FROM matches WHERE user_a = ? OR user_b = ?",
            (username, username),
        ) as cursor:
            pairs = await cursor.fetchall()
        room_ids = {"__".join(sorted((row["user_a"], row["user_b"]))) for row in pairs}

        async with db.execute(
            "SELECT DISTINCT post_id FROM post_likes WHERE username = ?",
            (username,),
        ) as cursor:
            liked_post_ids = [int(row[0]) for row in await cursor.fetchall()]

        if post_ids:
            placeholders = ",".join("?" for _ in post_ids)
            await db.execute(
                f"DELETE FROM post_likes WHERE post_id IN ({placeholders})",
                post_ids,
            )
            await db.execute(
                f"DELETE FROM posts WHERE id IN ({placeholders})",
                post_ids,
            )
        await db.execute("DELETE FROM post_likes WHERE username = ?", (username,))
        if liked_post_ids:
            placeholders = ",".join("?" for _ in liked_post_ids)
            await db.execute(
                f"""UPDATE posts
                    SET likes = (SELECT COUNT(*) FROM post_likes WHERE post_id = posts.id)
                    WHERE id IN ({placeholders})""",
                liked_post_ids,
            )

        if room_ids:
            placeholders = ",".join("?" for _ in room_ids)
            await db.execute(
                f"DELETE FROM peer_messages WHERE room_id IN ({placeholders})",
                list(room_ids),
            )
        await db.execute("DELETE FROM peer_messages WHERE sender = ?", (username,))
        await db.execute(
            "DELETE FROM pending_matches WHERE username = ? OR peer_username = ?",
            (username, username),
        )
        await db.execute(
            "DELETE FROM matches WHERE user_a = ? OR user_b = ?",
            (username, username),
        )
        await db.execute("DELETE FROM messages WHERE username = ?", (username,))
        await db.execute("DELETE FROM user_tag_prefs WHERE username = ?", (username,))
        await db.execute("DELETE FROM user_time_tag_prefs WHERE username = ?", (username,))
        await db.execute("DELETE FROM user_states WHERE username = ?", (username,))
        await db.execute("DELETE FROM events WHERE username = ?", (username,))
        await db.execute("DELETE FROM invite_codes WHERE username = ?", (username,))
        if user_row["phone"]:
            await db.execute("DELETE FROM otp_codes WHERE phone = ?", (user_row["phone"],))
        await db.execute("DELETE FROM users WHERE username = ?", (username,))

        # UUID 文件理论上不会共享；仍在事务内复核引用，避免误删异常旧数据。
        unreferenced_paths = await _queue_unreferenced_uploads(db, upload_paths)

        await db.commit()
        return {"deleted": True, "upload_paths": unreferenced_paths}


async def get_pending_upload_cleanup() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT path FROM upload_cleanup_queue ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def mark_upload_cleanup_done(paths: list[str]) -> None:
    if not paths:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "DELETE FROM upload_cleanup_queue WHERE path = ?",
            [(path,) for path in paths],
        )
        await db.commit()

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
        await db.execute("BEGIN IMMEDIATE")
        if user_a == user_b or not await _users_exist(db, user_a, user_b):
            await db.rollback()
            return False
        async with db.execute(
            """SELECT 1 FROM matches
               WHERE ((user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?))
                 AND recommended_at > datetime('now', '-30 days')
               LIMIT 1""",
            (user_a, user_b, user_b, user_a),
        ) as cursor:
            if await cursor.fetchone() is not None:
                await db.rollback()
                return False
        await db.execute(
            "INSERT INTO matches (user_a, user_b) VALUES (?, ?)", (user_a, user_b)
        )
        await db.commit()
        return True

async def update_match_response(me: str, peer: str, response: str):
    """记录 me 对 (me ↔ peer) 这对匹配的态度。response = 'accept' / 'reject'。
    根据 matches 行实际 user_a/user_b 的顺序更新对应列；不存在时拒绝，
    防止任意用户绕过推荐流程制造连接关系。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, me, peer):
            await db.rollback()
            return False
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
            await db.rollback()
            return False
        await db.commit()
        return True

async def save_peer_message(room_id: str, sender: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _peer_room_is_accepted(db, room_id, sender):
            await db.rollback()
            return False
        await db.execute(
            "INSERT INTO peer_messages (room_id, sender, content) VALUES (?, ?, ?)",
            (room_id, sender, content)
        )
        await db.commit()
        return True

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
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, username, peer_username):
            await db.rollback()
            return False
        async with db.execute(
            """SELECT 1 FROM pending_matches
               WHERE username = ? AND peer_username = ? AND match_layer = ?
                 AND created_at > datetime('now', '-2 hours')
               LIMIT 1""",
            (username, peer_username, match_layer),
        ) as cursor:
            if await cursor.fetchone() is not None:
                await db.rollback()
                return False
        await db.execute(
            """INSERT INTO pending_matches
               (username, peer_username, interest_topic, reason, type, tags_json, triggered_by_message_id, match_layer)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (username, peer_username, interest_topic, reason, match_type,
             _json.dumps(tags, ensure_ascii=False), triggered_by_message_id, match_layer)
        )
        await db.commit()
        return True


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
    matches 行不存在时拒绝，避免通过问候文本隐式创建任意关系。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, me, peer):
            await db.rollback()
            return False
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
            await db.rollback()
            return False
        await db.commit()
        return True


async def upsert_user_state(
    username: str,
    connection_mode: str,
    emotional_intensity: int,
    openness_level: str,
    interest_anchor: str,
):
    """底色探针结果持久化（一人一行 upsert）"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, username):
            await db.rollback()
            return False
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
        return True


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
        if other in seen:
            continue
        seen.add(other)
        if accepted:
            result.append(other)
    return result

async def save_post(
    anon_id: str,
    media_path: str,
    media_type: str,
    caption: str,
    tags: list,
    owner_username: str,
) -> int | None:
    """保存广场帖子，返回新帖 id"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, owner_username):
            await db.rollback()
            return None
        cursor = await db.execute(
            """INSERT INTO posts
               (anon_id, media_path, media_type, caption, tags_json, owner_username)
               VALUES (?,?,?,?,?,?)""",
            (
                anon_id,
                media_path,
                media_type,
                caption,
                _json.dumps(tags, ensure_ascii=False),
                owner_username,
            )
        )
        await db.commit()
        return cursor.lastrowid


async def get_posts(
    limit: int = 30,
    offset: int = 0,
    sort: str = "latest",
    tag: str = "",
) -> list[dict]:
    """按排序、标签和真实分页参数拉广场帖子列表。"""
    order_by = "likes DESC, created_at DESC" if sort == "hot" else "created_at DESC"
    where = ""
    params: list = []
    if tag:
        where = """WHERE EXISTS (
            SELECT 1
            FROM json_each(CASE WHEN json_valid(posts.tags_json) THEN posts.tags_json ELSE '[]' END) AS tag_item
            WHERE tag_item.value = ?
        )"""
        params.append(tag)
    params.extend((limit, offset))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""SELECT id, anon_id, media_path, media_type, caption, tags_json, likes, created_at
                FROM posts
                {where}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?""",
            params,
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


async def get_recommended_posts(
    username: str,
    time_slot: str,
    limit: int = 30,
    offset: int = 0,
    tag: str = "",
) -> list[dict]:
    """按用户全局/当前时段标签偏好在全表排序后，再做真实分页。"""
    where = ""
    params: list = [username, username, time_slot]
    if tag:
        where = """WHERE EXISTS (
            SELECT 1
            FROM json_each(CASE WHEN json_valid(posts.tags_json) THEN posts.tags_json ELSE '[]' END) AS filter_tag
            WHERE filter_tag.value = ?
        )"""
        params.append(tag)
    params.extend((limit, offset))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""SELECT id, anon_id, media_path, media_type, caption, tags_json, likes, created_at,
                       COALESCE((
                           SELECT SUM(
                               COALESCE(global_pref.score, 0)
                               + COALESCE(time_pref.score, 0) * 1.5
                           )
                           FROM json_each(
                               CASE WHEN json_valid(posts.tags_json) THEN posts.tags_json ELSE '[]' END
                           ) AS tag_item
                           LEFT JOIN user_tag_prefs AS global_pref
                             ON global_pref.username = ? AND global_pref.tag = tag_item.value
                           LEFT JOIN user_time_tag_prefs AS time_pref
                             ON time_pref.username = ? AND time_pref.time_slot = ?
                            AND time_pref.tag = tag_item.value
                       ), 0) AS preference_score
                FROM posts
                {where}
                ORDER BY preference_score DESC, created_at DESC
                LIMIT ? OFFSET ?""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d.pop("preference_score", None)
        try:
            d["tags"] = _json.loads(d.pop("tags_json") or "[]")
        except Exception:
            d["tags"] = []
        result.append(d)
    return result


async def get_post(post_id: int) -> dict | None:
    """按 id 直查一条广场帖子。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, anon_id, media_path, media_type, caption, tags_json, likes, created_at
               FROM posts WHERE id = ?""",
            (post_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    post = dict(row)
    try:
        post["tags"] = _json.loads(post.pop("tags_json") or "[]")
    except Exception:
        post["tags"] = []
    return post


async def like_post(post_id: int, username: str) -> tuple[int, bool]:
    """给帖子点赞（按登录用户去重），返回（最新 likes 数，本次是否新点赞）。
    先 INSERT OR IGNORE 进 post_likes;只有确实是新插入(rowcount>0)才给 posts.likes +1，
    所以同一用户重复点赞幂等、不再加数。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, username):
            await db.rollback()
            return 0, False
        async with db.execute(
            "SELECT 1 FROM posts WHERE id = ?", (post_id,)
        ) as cursor:
            if await cursor.fetchone() is None:
                await db.rollback()
                return 0, False
        cur = await db.execute(
            "INSERT OR IGNORE INTO post_likes (post_id, username) VALUES (?, ?)",
            (post_id, username),
        )
        inserted = cur.rowcount > 0
        if inserted:  # 本次确实是新点赞
            await db.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
        await db.commit()
        async with db.execute("SELECT likes FROM posts WHERE id = ?", (post_id,)) as c:
            row = await c.fetchone()
    return (row[0] if row else 0), inserted


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
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, username):
            await db.rollback()
            return
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
        await db.execute("BEGIN IMMEDIATE")
        if not await _users_exist(db, username):
            await db.rollback()
            return
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
        # username 与 phone 都有唯一约束；INSERT OR IGNORE 让并发首登幂等。
        await db.execute(
            "INSERT OR IGNORE INTO users (username, phone, strawberry_balance) VALUES (?, ?, 200)",
            (phone, phone),
        )
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE phone = ?", (phone,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            # 兼容旧数据：username 已占用该手机号、但 phone 尚未回填时，
            # INSERT OR IGNORE 会因 username 唯一约束被吞掉，按 username 兜底返回。
            async with db.execute("SELECT * FROM users WHERE username = ?", (phone,)) as cursor:
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
