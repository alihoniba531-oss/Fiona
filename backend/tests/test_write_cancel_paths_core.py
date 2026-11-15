# -*- coding: utf-8 -*-
"""真实写路径的取消点扫描：agent_store、database、trace。

每个参数先用 prepare 把数据恢复成初始状态，再让取消落在被测协程第 k 次
aiosqlite 调用「结果已交回、任务还没被唤醒」的窗口里。统一在任务对象仍被
引用时检查写锁是否空闲，并要求每个取消点都以 CancelledError 结束。

为了让「写事务里至少有一条查询返回了行」成立，prepare 会保证每个写事务里
至少一条 SELECT（或 UPDATE ... RETURNING）在初始状态下确实能查到数据。
"""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

import agent_store
import database
import trace
from cancel_sweep import sweep_cancel_points, write_lock_is_free


USER = "cancel-core-user"
PEER = "cancel-core-peer"
AGENT_ID = "cancel-core-agent"
DEFAULT_CONVERSATION = "cancel-core-default"
TARGET_CONVERSATION = "cancel-core-target"
STUDIO_PROJECT = "cancel-core-project"
STUDIO_JOB = "cancel-core-job"
STUDIO_TIME = "2026-11-15T00:00:00+00:00"


# ---------------------------------------------------------------------------
# 造数辅助：全部直接写表，不用 INSERT OR IGNORE，写完立刻查回来确认。
# ---------------------------------------------------------------------------


def _execute(sql: str, parameters: tuple = ()) -> int:
    with sqlite3.connect(database.DB_PATH) as db:
        cursor = db.execute(sql, parameters)
    return cursor.rowcount


def _row(sql: str, parameters: tuple = ()):
    with sqlite3.connect(database.DB_PATH) as db:
        row = db.execute(sql, parameters).fetchone()
    assert row is not None, f"期望查到数据行：{sql!r} parameters={parameters!r}"
    return row


def _count(table: str, condition: str, parameters: tuple = ()) -> int:
    return _row(f"SELECT COUNT(*) FROM {table} WHERE {condition}", parameters)[0]


def _ensure_agent() -> None:
    """基线分身：get_my_agent/update_my_agent/get_memory_snapshot 等共用。"""
    _execute(
        """INSERT INTO agents
               (id, owner_username, display_name, bio, personality,
                private_memory_json, memory_revision, avatar_emoji, is_public)
           VALUES (?, ?, 'Chloe', '', '', '{"seed": true}', 3, '✦', 0)
           ON CONFLICT(id) DO UPDATE SET
               owner_username = excluded.owner_username,
               display_name = excluded.display_name,
               bio = excluded.bio,
               personality = excluded.personality,
               private_memory_json = excluded.private_memory_json,
               memory_revision = excluded.memory_revision,
               avatar_emoji = excluded.avatar_emoji,
               is_public = excluded.is_public""",
        (AGENT_ID, USER),
    )
    row = _row(
        """SELECT owner_username, display_name, bio, private_memory_json,
                  memory_revision, is_public
           FROM agents WHERE id = ?""",
        (AGENT_ID,),
    )
    assert row == (USER, "Chloe", "", '{"seed": true}', 3, 0)


def _ensure_conversation(conversation_id: str, *, is_default: int, title: str) -> None:
    _execute(
        """INSERT INTO conversations
               (id, owner_username, agent_id, title, auto_title, is_default, updated_at)
           VALUES (?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(id) DO UPDATE SET
               owner_username = excluded.owner_username,
               agent_id = excluded.agent_id,
               title = excluded.title,
               auto_title = excluded.auto_title,
               is_default = excluded.is_default,
               updated_at = CURRENT_TIMESTAMP""",
        (conversation_id, USER, AGENT_ID, title, is_default),
    )
    row = _row(
        "SELECT owner_username, agent_id, is_default FROM conversations WHERE id = ?",
        (conversation_id,),
    )
    assert row == (USER, AGENT_ID, is_default)


def _ensure_default_conversation() -> None:
    _ensure_conversation(
        DEFAULT_CONVERSATION, is_default=1, title="与我的分身交流",
    )


def _ensure_studio_project() -> None:
    _execute(
        """INSERT INTO studio_projects
               (id, owner, title, aspect, created_at, updated_at, archived)
           VALUES (?, ?, '取消点测试项目', '16:9', ?, ?, 0)
           ON CONFLICT(id) DO UPDATE SET
               owner = excluded.owner,
               title = excluded.title,
               aspect = excluded.aspect,
               archived = 0""",
        (STUDIO_PROJECT, USER, STUDIO_TIME, STUDIO_TIME),
    )
    row = _row(
        "SELECT owner, archived FROM studio_projects WHERE id = ?",
        (STUDIO_PROJECT,),
    )
    assert row == (USER, 0)


def _ensure_studio_job() -> None:
    # studio_jobs 还有 (quote_id, quote_item_id) 唯一约束；先删再插，避免
    # 以 id 为冲突目标的 upsert 撞到另一条唯一约束。
    _execute("DELETE FROM studio_jobs WHERE id = ?", (STUDIO_JOB,))
    _execute(
        """INSERT INTO studio_jobs
               (id, project_id, owner, kind, provider, model, params_json,
                fingerprint, quote_id, quote_item_id, status, est_min_cny,
                est_max_cny, created_at, updated_at, confirmed_day)
           VALUES (?, ?, ?, 'i2v', 'wan', 'wan2.6-i2v', '{}',
                   'cancel-core-fingerprint', 'cancel-core-quote',
                   'cancel-core-item', 'downloaded', '0.10000000',
                   '0.20000000', ?, ?, '2026-11-15')""",
        (STUDIO_JOB, STUDIO_PROJECT, USER, STUDIO_TIME, STUDIO_TIME),
    )
    row = _row(
        "SELECT project_id, owner, status FROM studio_jobs WHERE id = ?",
        (STUDIO_JOB,),
    )
    assert row == (STUDIO_PROJECT, USER, "downloaded")


def _reset_strawberries(balance: int, refill_date=None) -> None:
    _execute(
        """UPDATE users SET strawberry_balance = ?, strawberry_refill_date = ?
           WHERE username = ?""",
        (balance, refill_date, USER),
    )
    row = _row(
        "SELECT strawberry_balance, strawberry_refill_date FROM users WHERE username = ?",
        (USER,),
    )
    assert row == (balance, refill_date)


# ---------------------------------------------------------------------------
# 每个参数一个造数/复位函数，返回 (prepare, make_coroutine)。
# prepare 在每个取消点之前运行，把数据恢复成下面这个初始状态。
# ---------------------------------------------------------------------------


def _case_get_my_agent():
    _ensure_agent()

    def make_coroutine():
        return agent_store.get_my_agent(USER)

    async def prepare():
        _ensure_agent()

    return prepare, make_coroutine


def _case_update_my_agent():
    _ensure_agent()

    def make_coroutine():
        return agent_store.update_my_agent(USER, {"bio": "取消点基线"})

    async def prepare():
        _ensure_agent()

    return prepare, make_coroutine


def _case_get_memory_snapshot():
    _ensure_agent()

    def make_coroutine():
        return agent_store.get_memory_snapshot(USER)

    async def prepare():
        _ensure_agent()

    return prepare, make_coroutine


def _case_resolve_chat_conversation():
    _ensure_agent()
    _ensure_default_conversation()

    def make_coroutine():
        return agent_store.resolve_chat_conversation(USER)

    async def prepare():
        _ensure_agent()
        _ensure_default_conversation()

    return prepare, make_coroutine


def _case_list_conversations():
    _ensure_agent()
    _ensure_default_conversation()

    def make_coroutine():
        return agent_store.list_conversations(USER)

    async def prepare():
        _ensure_agent()
        _ensure_default_conversation()

    return prepare, make_coroutine


def _case_create_conversation():
    _ensure_agent()

    def make_coroutine():
        return agent_store.create_conversation(USER, title="取消点新会话")

    async def prepare():
        _execute(
            "DELETE FROM conversations WHERE owner_username = ? AND is_default = 0",
            (USER,),
        )
        assert _count(
            "conversations", "owner_username = ? AND is_default = 0", (USER,),
        ) == 0
        _ensure_agent()

    return prepare, make_coroutine


def _create_target_conversation_with_messages() -> None:
    _execute(
        "DELETE FROM messages WHERE conversation_id = ?", (TARGET_CONVERSATION,),
    )
    _execute(
        "DELETE FROM conversations WHERE id = ?", (TARGET_CONVERSATION,),
    )
    _ensure_conversation(
        TARGET_CONVERSATION, is_default=0, title="待删除会话",
    )
    _execute(
        """INSERT INTO messages (username, role, content, conversation_id, agent_id)
           VALUES (?, 'user', ?, ?, ?)""",
        (USER, "第一条消息", TARGET_CONVERSATION, AGENT_ID),
    )
    _execute(
        """INSERT INTO messages (username, role, content, conversation_id, agent_id)
           VALUES (?, 'assistant', ?, ?, ?)""",
        (USER, "第二条消息", TARGET_CONVERSATION, AGENT_ID),
    )
    assert _count(
        "messages", "conversation_id = ? AND username = ?",
        (TARGET_CONVERSATION, USER),
    ) == 2


def _case_delete_conversation():
    _ensure_agent()
    _ensure_default_conversation()
    _create_target_conversation_with_messages()

    def make_coroutine():
        return agent_store.delete_conversation(USER, TARGET_CONVERSATION)

    async def prepare():
        _ensure_agent()
        _ensure_default_conversation()
        _create_target_conversation_with_messages()

    return prepare, make_coroutine


def _case_save_message():
    def make_coroutine():
        return database.save_message(USER, "assistant", "取消点消息")

    async def prepare():
        _execute("DELETE FROM messages WHERE username = ?", (USER,))
        _ensure_agent()
        _ensure_default_conversation()
        assert _count("messages", "username = ?", (USER,)) == 0

    return prepare, make_coroutine


def _case_reserve_strawberries():
    def make_coroutine():
        return database.reserve_strawberries(USER, 1)

    async def prepare():
        _reset_strawberries(200, None)

    return prepare, make_coroutine


def _case_refund_strawberries():
    def make_coroutine():
        return database.refund_strawberries(USER, 1)

    async def prepare():
        _reset_strawberries(100, None)

    return prepare, make_coroutine


def _case_get_strawberry_balance():
    def make_coroutine():
        return database.get_strawberry_balance(USER)

    async def prepare():
        # 余额与补草莓日期都复位，保证每日补草莓的 UPDATE 与随后的 SELECT 都执行。
        _reset_strawberries(0, None)

    return prepare, make_coroutine


def _case_save_match():
    def make_coroutine():
        return database.save_match(USER, PEER)

    async def prepare():
        _execute(
            """DELETE FROM matches
               WHERE (user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)""",
            (USER, PEER, PEER, USER),
        )
        assert _count(
            "matches",
            "((user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?))",
            (USER, PEER, PEER, USER),
        ) == 0

    return prepare, make_coroutine


def _case_save_pending_match():
    def make_coroutine():
        return database.save_pending_match(
            USER, PEER, "取消点话题", "取消点理由", "layer1", ["标签甲", "标签乙"],
        )

    async def prepare():
        _execute(
            "DELETE FROM pending_matches WHERE username = ? AND peer_username = ?",
            (USER, PEER),
        )
        assert _count(
            "pending_matches", "username = ? AND peer_username = ?", (USER, PEER),
        ) == 0

    return prepare, make_coroutine


def _case_upsert_user_state():
    def make_coroutine():
        return database.upsert_user_state(
            USER, "exploring", 3, "medium", "light_connection",
        )

    async def prepare():
        _execute("DELETE FROM user_states WHERE username = ?", (USER,))
        assert _count("user_states", "username = ?", (USER,)) == 0

    return prepare, make_coroutine


def _case_save_studio_notice():
    _ensure_agent()
    _ensure_default_conversation()
    _ensure_studio_project()
    _ensure_studio_job()

    job = {
        "id": STUDIO_JOB,
        "project_id": STUDIO_PROJECT,
        "owner": USER,
        "kind": "i2v",
        "provider": "wan",
        "status": "downloaded",
    }

    def make_coroutine():
        return database.save_studio_notice(
            USER, job, "取消点提醒摘要", "取消点提醒正文",
        )

    async def prepare():
        _ensure_agent()
        _ensure_default_conversation()
        _execute("DELETE FROM studio_notices WHERE username = ?", (USER,))
        _execute("DELETE FROM studio_notice_pending WHERE username = ?", (USER,))
        _ensure_studio_project()
        _ensure_studio_job()
        database._pending_studio_messages.pop(
            (str(database.DB_PATH), USER, STUDIO_JOB), None,
        )
        assert _count("studio_notices", "username = ?", (USER,)) == 0
        assert _count("studio_notice_pending", "username = ?", (USER,)) == 0
        assert _row(
            """SELECT j.id FROM studio_jobs j
               JOIN studio_projects p
                 ON p.id = j.project_id AND p.owner = j.owner AND p.archived = 0
               JOIN users u ON u.username = j.owner
               WHERE j.id = ? AND j.project_id = ? AND j.owner = ?""",
            (STUDIO_JOB, STUDIO_PROJECT, USER),
        )[0] == STUDIO_JOB

    return prepare, make_coroutine


def _case_update_time_tag_prefs():
    time_slot = "工作日-晚上"

    def make_coroutine():
        return database.update_time_tag_prefs(
            USER, ["取消点标签"], time_slot=time_slot,
        )

    async def prepare():
        _execute(
            "DELETE FROM user_time_tag_prefs WHERE username = ? AND time_slot = ?",
            (USER, time_slot),
        )
        assert _count(
            "user_time_tag_prefs", "username = ? AND time_slot = ?",
            (USER, time_slot),
        ) == 0

    return prepare, make_coroutine


def _case_log_event():
    def make_coroutine():
        return trace.log_event(
            USER, "cancel_core", "取消点事件", {"source": "test"},
        )

    async def prepare():
        _execute("DELETE FROM events WHERE username = ?", (USER,))
        assert _count("events", "username = ?", (USER,)) == 0

    return prepare, make_coroutine


CASES = {
    "agent_store.get_my_agent": _case_get_my_agent,
    "agent_store.update_my_agent": _case_update_my_agent,
    "agent_store.get_memory_snapshot": _case_get_memory_snapshot,
    "agent_store.resolve_chat_conversation": _case_resolve_chat_conversation,
    "agent_store.list_conversations": _case_list_conversations,
    "agent_store.create_conversation": _case_create_conversation,
    "agent_store.delete_conversation": _case_delete_conversation,
    "database.save_message": _case_save_message,
    "database.reserve_strawberries": _case_reserve_strawberries,
    "database.refund_strawberries": _case_refund_strawberries,
    "database.get_strawberry_balance": _case_get_strawberry_balance,
    "database.save_match": _case_save_match,
    "database.save_pending_match": _case_save_pending_match,
    "database.upsert_user_state": _case_upsert_user_state,
    "database.save_studio_notice": _case_save_studio_notice,
    "database.update_time_tag_prefs": _case_update_time_tag_prefs,
    "trace.log_event": _case_log_event,
}


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", list(CASES))
def test_cancelled_write_leaves_no_lock(case_id, tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "cancel-core.db"))
    monkeypatch.setattr(database, "SQLITE_BUSY_TIMEOUT", 0.3)
    # get_strawberry_balance 需要每日补草莓；其它写函数读到同一份配置也无害。
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "50")

    async def run():
        await database.init_db()
        await database.get_or_create_user(USER)
        await database.get_or_create_user(PEER)
        prepare, make_coroutine = CASES[case_id]()

        async def check(_context):
            return await write_lock_is_free(database.DB_PATH)

        points = await sweep_cancel_points(
            make_coroutine,
            check=check,
            prepare=prepare,
            mode="delivered",
            cancel="task",
        )
        assert points, f"{case_id} 至少应扫到一个取消点"
        for point in points:
            assert point.cancelled is True, (
                f"{case_id} 的取消点 k={point.k} [{point.label}] "
                "没有以 CancelledError 结束"
            )
            assert point.check_result is True, (
                f"{case_id} 的取消点 k={point.k} [{point.label}] "
                "在任务对象仍被引用时写锁没有释放"
            )

    asyncio.run(run())
