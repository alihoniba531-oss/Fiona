# -*- coding: utf-8 -*-
"""真实写路径上的取消点：取消后的收尾写库，以及取消不留写锁。

所有扫描都用 ``mode="delivered", cancel="task"``。检查函数在任务对象仍被
``cancel_sweep`` 引用时运行：三条业务用例在其中执行真实的收尾写库，参数化
用例在其中探测写锁。
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import aiosqlite
import pytest

import agent_store
import database
import exchange_store
import novel.runner as novel_runner
from novel.store_db import DbStepStore

from cancel_sweep import sweep_cancel_points, write_lock_is_free


USERNAME = "cancel_author"
OTHER_USERNAME = "cancel_reader"
NOVEL_ID = "cancel-novel-1"
RUN_TOKEN = "cancel-run-token-1"
EXCHANGE_ID = "cancel-exchange-1"
EXCHANGE_TOKEN = "cancel-exchange-token-1"
CALL_ID = "cancel-call-1"
AGENT_ID = "cancel-agent-author"
OTHER_AGENT_ID = "cancel-agent-reader"
DEFAULT_CONVERSATION_ID = "cancel-conversation-default"
NAMED_CONVERSATION_ID = "cancel-conversation-named"
START_BALANCE = 100
STEP_KEY = "usage/step-1"

EXCHANGE_CASES = (
    "exchange_store.load_running_exchange",
    "exchange_store.reserve_model_call",
    "exchange_store.finish_model_call",
    "exchange_store.stop_and_discard_reserved_calls",
)
NOVEL_CASES = (
    "novel.DbStepStore.append_usage",
    "novel.DbStepStore.write_step",
    "novel.DbStepStore.commit_setup",
    "novel.DbStepStore.save_plan",
    "novel.DbStepStore.commit_chapter",
    "novel.runner._pause",
)
LOCK_CASES = EXCHANGE_CASES + NOVEL_CASES


@pytest.fixture(autouse=True)
def _cancel_test_database(tmp_path, monkeypatch):
    """每个用例独立临时库；残留写锁 0.3 秒就报错，不用干等 5 秒。"""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "cancel-paths.db"))
    monkeypatch.setattr(database, "SQLITE_BUSY_TIMEOUT", 0.3)
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "0")
    asyncio.run(database.init_db())


@asynccontextmanager
async def _db():
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def _fetchall(sql, params=()):
    async with _db() as db:
        async with db.execute(sql, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def _fetchone(sql, params=()):
    rows = await _fetchall(sql, params)
    return rows[0] if rows else None


async def _ensure_user(username):
    await database.get_or_create_user(username)
    row = await _fetchone(
        "SELECT username, strawberry_balance FROM users WHERE username = ?",
        (username,),
    )
    assert row is not None, f"用户 {username} 没有真实插入"
    assert row["username"] == username
    return row


# ---------------------------------------------------------------------------
# novel 数据
# ---------------------------------------------------------------------------


def _novel_config():
    return {"target": {"min_chapters": 10, "max_chapters": 60},
            "experiment": "P1"}


async def _reset_novel():
    """把书恢复成 running + 本 run_token，并清空所有子表。"""
    async with _db() as db:
        await db.execute("DELETE FROM novel_steps WHERE novel_id = ?", (NOVEL_ID,))
        await db.execute("DELETE FROM novel_chapters WHERE novel_id = ?", (NOVEL_ID,))
        await db.execute("DELETE FROM novel_bible_versions WHERE novel_id = ?", (NOVEL_ID,))
        await db.execute("DELETE FROM novels WHERE id = ?", (NOVEL_ID,))
        await db.execute(
            """INSERT INTO novels
               (id, username, title, seed_idea, status, pause_reason, config_json,
                bible_version, chapters_done, words_done, budget_strawberries, run_token)
               VALUES (?, ?, ?, ?, 'running', NULL, ?, 0, 0, 0, 10000, ?)""",
            (NOVEL_ID, USERNAME, "取消点测试书", "seed idea",
             json.dumps(_novel_config(), ensure_ascii=False), RUN_TOKEN),
        )
        await db.commit()
    row = await _fetchone(
        "SELECT username, status, run_token FROM novels WHERE id = ?", (NOVEL_ID,)
    )
    assert row == {"username": USERNAME, "status": "running", "run_token": RUN_TOKEN}


def _novel_meeting():
    return {
        "decision": {
            "beat_sheet": {"title": "第一章 启程"},
            "ending_status": "continue",
            "user_note_responses": [],
        },
    }


def _novel_product():
    return {
        "body": "# 第一章 启程\n\n这是正文。",
        "bible": {"characters": []},
        "flags": [],
        "reviews": [],
        "archive": {},
    }


def _usage_record():
    return {
        "step_key": STEP_KEY,
        "role": "editor",
        "model": "fake:local",
        "input_tokens": 3,
        "output_tokens": 2,
        "cached_tokens": 1,
        "duration_ms": 10,
    }


def _step_record():
    return {
        "role": "editor",
        "model": "fake:local",
        "status": "ok",
        "result": {"valid": True},
        "usage": {"input_tokens": 3, "output_tokens": 2, "cached_tokens": 1},
        "attempts": 1,
        "duration_ms": 10,
    }


async def _novel_run_token():
    row = await _fetchone("SELECT run_token FROM novels WHERE id = ?", (NOVEL_ID,))
    assert row is not None, "书在收尾写库后消失了"
    return row["run_token"]


# ---------------------------------------------------------------------------
# exchange 数据
# ---------------------------------------------------------------------------


def _card(agent_id, display_name):
    return {"id": agent_id, "display_name": display_name, "bio": "",
            "avatar_emoji": "✦", "is_public": 1,
            "created_at": "2026-01-01 00:00:00"}


async def _seed_exchange_participants():
    async with _db() as db:
        for agent_id, owner, display_name in (
            (AGENT_ID, USERNAME, "星河"),
            (OTHER_AGENT_ID, OTHER_USERNAME, "苔原"),
        ):
            await db.execute("DELETE FROM agents WHERE owner_username = ?", (owner,))
            await db.execute(
                """INSERT INTO agents
                   (id, owner_username, display_name, bio, avatar_emoji, is_public)
                   VALUES (?, ?, ?, '', '✦', 1)""",
                (agent_id, owner, display_name),
            )
        await db.commit()
    rows = await _fetchall(
        "SELECT id, owner_username, is_public FROM agents WHERE owner_username IN (?, ?)",
        (USERNAME, OTHER_USERNAME),
    )
    assert {row["owner_username"] for row in rows} == {USERNAME, OTHER_USERNAME}
    assert all(row["is_public"] == 1 for row in rows)


async def _seed_exchange(*, reserved):
    """恢复一场 running 的交流；reserved 时再放一条 reserved 调用。"""
    async with _db() as db:
        await db.execute(
            "DELETE FROM agent_exchange_calls WHERE exchange_id = ?", (EXCHANGE_ID,)
        )
        await db.execute(
            "DELETE FROM agent_exchange_messages WHERE exchange_id = ?", (EXCHANGE_ID,)
        )
        await db.execute("DELETE FROM agent_exchanges WHERE id = ?", (EXCHANGE_ID,))
        await db.execute(
            """INSERT INTO agent_exchanges
               (id, kind, initiator_username, recipient_username,
                initiator_agent_id, recipient_agent_id, pair_key,
                initiator_json, recipient_json, topic, max_turns, token_budget,
                status, run_token, turn_count, inflight_call_id, model_calls,
                budget_used, reserved_tokens)
               VALUES (?, 'peer', ?, ?, ?, ?, ?, ?, ?, ?, 6, 80000, 'running', ?,
                       0, ?, ?, ?, ?)""",
            (EXCHANGE_ID, USERNAME, OTHER_USERNAME, AGENT_ID, OTHER_AGENT_ID,
             "cancel-pair-key",
             json.dumps(_card(AGENT_ID, "星河"), ensure_ascii=False),
             json.dumps(_card(OTHER_AGENT_ID, "苔原"), ensure_ascii=False),
             "取消点测试", EXCHANGE_TOKEN,
             CALL_ID if reserved else None,
             1 if reserved else 0,
             150 if reserved else 0,
             150 if reserved else 0),
        )
        if reserved:
            await db.execute(
                """INSERT INTO agent_exchange_calls
                   (id, exchange_id, ordinal, kind, status, reserved_tokens,
                    input_limit, output_limit)
                   VALUES (?, ?, 1, 'turn', 'reserved', 150, 100, 50)""",
                (CALL_ID, EXCHANGE_ID),
            )
        await db.commit()
    exchange = await _fetchone(
        "SELECT initiator_username, status, run_token "
        "FROM agent_exchanges WHERE id = ?",
        (EXCHANGE_ID,),
    )
    assert exchange == {"initiator_username": USERNAME, "status": "running",
                        "run_token": EXCHANGE_TOKEN}
    calls = await _fetchall(
        "SELECT id, status FROM agent_exchange_calls WHERE exchange_id = ?",
        (EXCHANGE_ID,),
    )
    if reserved:
        assert calls == [{"id": CALL_ID, "status": "reserved"}]
    else:
        assert calls == []


async def _reserved_call_count():
    row = await _fetchone(
        "SELECT COUNT(*) AS n FROM agent_exchange_calls "
        "WHERE exchange_id = ? AND status = 'reserved'",
        (EXCHANGE_ID,),
    )
    assert row is not None
    return row["n"]


# ---------------------------------------------------------------------------
# chat 数据
# ---------------------------------------------------------------------------


async def _reset_chat_state(state):
    """state: default-missing / default-exists / named。"""
    async with _db() as db:
        await db.execute(
            "DELETE FROM conversations WHERE owner_username = ?", (USERNAME,)
        )
        await db.execute("DELETE FROM agents WHERE owner_username = ?", (USERNAME,))
        await db.execute(
            "UPDATE users SET strawberry_balance = ? WHERE username = ?",
            (START_BALANCE, USERNAME),
        )
        if state != "default-missing":
            await db.execute(
                """INSERT INTO agents
                   (id, owner_username, display_name, bio, avatar_emoji, is_public)
                   VALUES (?, ?, 'Chloe', '', '✦', 0)""",
                (AGENT_ID, USERNAME),
            )
            if state == "default-exists":
                await db.execute(
                    """INSERT INTO conversations
                       (id, owner_username, agent_id, title, is_default, auto_title)
                       VALUES (?, ?, ?, '与我的分身交流', 1, 0)""",
                    (DEFAULT_CONVERSATION_ID, USERNAME, AGENT_ID),
                )
            elif state == "named":
                await db.execute(
                    """INSERT INTO conversations
                       (id, owner_username, agent_id, title, is_default, auto_title)
                       VALUES (?, ?, ?, '指定会话', 0, 0)""",
                    (NAMED_CONVERSATION_ID, USERNAME, AGENT_ID),
                )
        await db.commit()
    balance = await _fetchone(
        "SELECT strawberry_balance FROM users WHERE username = ?", (USERNAME,)
    )
    assert balance == {"strawberry_balance": START_BALANCE}
    conversations = await _fetchall(
        "SELECT id, is_default FROM conversations WHERE owner_username = ?",
        (USERNAME,),
    )
    expected = {
        "default-missing": [],
        "default-exists": [{"id": DEFAULT_CONVERSATION_ID, "is_default": 1}],
        "named": [{"id": NAMED_CONVERSATION_ID, "is_default": 0}],
    }[state]
    assert conversations == expected
    agents = await _fetchall(
        "SELECT id FROM agents WHERE owner_username = ?", (USERNAME,)
    )
    assert agents == ([] if state == "default-missing" else [{"id": AGENT_ID}])


async def _chat_balance():
    row = await _fetchone(
        "SELECT strawberry_balance FROM users WHERE username = ?", (USERNAME,)
    )
    assert row is not None, "用户在收尾写库后消失了"
    return row["strawberry_balance"]


# ---------------------------------------------------------------------------
# 检查函数
# ---------------------------------------------------------------------------


async def _check_lock_free(_point):
    return await write_lock_is_free(database.DB_PATH)


async def _run_follow_up(awaitable):
    """执行收尾写库；任何异常或超时都记下来交给断言，不让它打断扫描。"""
    try:
        await asyncio.wait_for(awaitable, timeout=2)
    except Exception as error:  # 包括 TimeoutError 和 OperationalError
        return f"{type(error).__name__}: {error}"
    return None


async def _check_novel_follow_up(_point):
    error = await _run_follow_up(novel_runner.cancel_novel(NOVEL_ID, USERNAME))
    if error is not None:
        return {"error": error, "value": None}
    return {"error": None, "value": await _novel_run_token()}


async def _check_exchange_follow_up(_point):
    error = await _run_follow_up(
        exchange_store.stop_and_discard_reserved_calls(
            EXCHANGE_ID, EXCHANGE_TOKEN, "取消点测试收尾"
        )
    )
    if error is not None:
        return {"error": error, "value": None}
    return {"error": None, "value": await _reserved_call_count()}


async def _check_chat_follow_up(_point):
    before = await _chat_balance()
    error = await _run_follow_up(database.refund_strawberries(USERNAME, 1))
    if error is not None:
        return {"error": error, "value": None}
    return {"error": None, "value": await _chat_balance() - before}


def _follow_up_failures(function_name, points, *, expected):
    """把一条扫描里的不合格取消点转成文字，交给用例最后一起断言。"""
    assert points, "扫描必须至少覆盖一个取消点（sweep 会抛 NoCancelPointsFound）"
    failures = []
    for point in points:
        prefix = (
            f"{function_name} 的取消点 k={point.k}，调用标签 {point.label}"
        )
        if point.cancelled is not True:
            failures.append(f"{prefix}：没有以取消结束")
        if point.check_completed is not True:
            failures.append(f"{prefix}：检查函数没有跑完")
        result = point.check_result
        if (
            not isinstance(result, dict)
            or "error" not in result
            or "value" not in result
        ):
            failures.append(
                f"{prefix}：检查结果不是 {{'error', 'value'}}：{result!r}"
            )
            continue
        if result["error"] is not None:
            failures.append(f"{prefix}：收尾写库失败：{result['error']}")
        elif result["value"] != expected:
            failures.append(
                f"{prefix}：收尾后的值 {result['value']!r}，期望 {expected!r}"
            )
    return failures


_UNSET = object()


def _assert_points(points, *, expect_check=_UNSET):
    assert points, "扫描必须至少覆盖一个取消点（sweep 会抛 NoCancelPointsFound）"
    for point in points:
        assert point.cancelled is True, (
            f"k={point.k} label={point.label} 没有以取消结束"
        )
        assert point.check_completed is True, (
            f"k={point.k} label={point.label} 的检查函数没有跑完"
        )
        if expect_check is not _UNSET:
            assert point.check_result == expect_check, (
                f"k={point.k} label={point.label} 检查结果={point.check_result!r}"
            )


# ---------------------------------------------------------------------------
# 三条取消后真实收尾写库
# ---------------------------------------------------------------------------


async def _novel_follow_up_scenario():
    await _ensure_user(USERNAME)
    novel_runner.TASKS.pop(NOVEL_ID, None)
    novel_runner._owners.pop(NOVEL_ID, None)

    def append_usage():
        store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
        return store.append_usage(_usage_record())

    def write_step():
        store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
        return store.write_step(STEP_KEY, _step_record())

    def pause():
        store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
        return novel_runner._pause(store, "budget_80")

    failures = []
    for function_name, make_coroutine in (
        ("DbStepStore.append_usage", append_usage),
        ("DbStepStore.write_step", write_step),
        ("novel.runner._pause", pause),
    ):
        points = await sweep_cancel_points(
            make_coroutine,
            check=_check_novel_follow_up,
            prepare=_reset_novel,
            mode="delivered",
            cancel="task",
        )
        failures.extend(
            _follow_up_failures(function_name, points, expected=None)
        )
    assert not failures, (
        "novel 取消后的收尾写库有不合格取消点：\n" + "\n".join(failures)
    )


async def _exchange_follow_up_scenario():
    await _ensure_user(USERNAME)
    await _ensure_user(OTHER_USERNAME)
    await _seed_exchange_participants()

    async def prepare():
        await _seed_exchange(reserved=False)

    def load_running():
        return exchange_store.load_running_exchange(EXCHANGE_ID, EXCHANGE_TOKEN)

    def reserve():
        return exchange_store.reserve_model_call(
            EXCHANGE_ID, EXCHANGE_TOKEN, 0, "turn", 100, 50
        )

    async def prepare_with_call():
        await _seed_exchange(reserved=True)

    def finish():
        return exchange_store.finish_model_call(
            EXCHANGE_ID, EXCHANGE_TOKEN, CALL_ID, 0,
            result={"content": "你好", "input_tokens": 10, "output_tokens": 5},
        )

    failures = []
    for function_name, make_coroutine, prepare in (
        ("exchange_store.load_running_exchange", load_running, prepare),
        ("exchange_store.reserve_model_call", reserve, prepare),
        ("exchange_store.finish_model_call", finish, prepare_with_call),
    ):
        points = await sweep_cancel_points(
            make_coroutine,
            check=_check_exchange_follow_up,
            prepare=prepare,
            mode="delivered",
            cancel="task",
        )
        failures.extend(
            _follow_up_failures(function_name, points, expected=0)
        )
    assert not failures, (
        "exchange 取消后的收尾写库有不合格取消点：\n" + "\n".join(failures)
    )


async def _chat_follow_up_scenario():
    await _ensure_user(USERNAME)

    failures = []
    for state in ("default-missing", "default-exists", "named"):
        async def prepare(_state=state):
            await _reset_chat_state(_state)

        async def make(_state=state):
            if _state == "named":
                return await agent_store.resolve_chat_conversation(
                    USERNAME, NAMED_CONVERSATION_ID
                )
            return await agent_store.resolve_chat_conversation(USERNAME)

        points = await sweep_cancel_points(
            make,
            check=_check_chat_follow_up,
            prepare=prepare,
            mode="delivered",
            cancel="task",
        )
        failures.extend(
            _follow_up_failures(
                f"agent_store.resolve_chat_conversation(state={state})",
                points,
                expected=1,
            )
        )
    assert not failures, (
        "chat 取消后的收尾退款有不合格取消点：\n" + "\n".join(failures)
    )


def test_novel_cancel_then_cancel_novel_succeeds():
    asyncio.run(_novel_follow_up_scenario())


def test_exchange_cancel_then_settlement_succeeds():
    asyncio.run(_exchange_follow_up_scenario())


def test_chat_conversation_check_cancel_then_refund_succeeds():
    asyncio.run(_chat_follow_up_scenario())


# ---------------------------------------------------------------------------
# 参数化：取消点上的写锁必须空闲
# ---------------------------------------------------------------------------


def _exchange_case_coroutine(case_id):
    name = case_id.split(".", 1)[1]
    if name == "load_running_exchange":
        def make():
            return exchange_store.load_running_exchange(EXCHANGE_ID, EXCHANGE_TOKEN)
    elif name == "reserve_model_call":
        def make():
            return exchange_store.reserve_model_call(
                EXCHANGE_ID, EXCHANGE_TOKEN, 0, "turn", 100, 50
            )
    elif name == "finish_model_call":
        def make():
            return exchange_store.finish_model_call(
                EXCHANGE_ID, EXCHANGE_TOKEN, CALL_ID, 0,
                result={"content": "你好", "input_tokens": 10, "output_tokens": 5},
            )
    elif name == "stop_and_discard_reserved_calls":
        def make():
            return exchange_store.stop_and_discard_reserved_calls(
                EXCHANGE_ID, EXCHANGE_TOKEN, "取消点测试收尾"
            )
    else:  # pragma: no cover - 参数表由本文件固定
        raise AssertionError(f"未知 exchange 用例 {case_id}")
    return make


def _novel_case_coroutine(case_id):
    name = case_id.split(".", 1)[1]
    if name == "DbStepStore.append_usage":
        def make():
            store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
            return store.append_usage(_usage_record())
    elif name == "DbStepStore.write_step":
        def make():
            store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
            return store.write_step(STEP_KEY, _step_record())
    elif name == "DbStepStore.commit_setup":
        def make():
            store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
            return store.commit_setup(
                {"title": "取消点测试书", "seed_idea": "seed idea"},
                {"version": 1, "characters": []},
            )
    elif name == "DbStepStore.save_plan":
        def make():
            store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
            return store.save_plan(1, _novel_meeting())
    elif name == "DbStepStore.commit_chapter":
        def make():
            store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
            return store.commit_chapter(1, _novel_meeting(), _novel_product())
    elif name == "runner._pause":
        def make():
            store = DbStepStore(USERNAME, NOVEL_ID, RUN_TOKEN)
            return novel_runner._pause(store, "budget_80")
    else:  # pragma: no cover - 参数表由本文件固定
        raise AssertionError(f"未知 novel 用例 {case_id}")
    return make


async def _lock_scenario(case_id):
    if case_id in EXCHANGE_CASES:
        await _ensure_user(USERNAME)
        await _ensure_user(OTHER_USERNAME)
        await _seed_exchange_participants()
        reserved = case_id in {
            "exchange_store.finish_model_call",
            "exchange_store.stop_and_discard_reserved_calls",
        }

        async def prepare():
            await _seed_exchange(reserved=reserved)
    else:
        await _ensure_user(USERNAME)

        async def prepare():
            await _reset_novel()

    make_coroutine = (
        _exchange_case_coroutine(case_id)
        if case_id in EXCHANGE_CASES
        else _novel_case_coroutine(case_id)
    )
    points = await sweep_cancel_points(
        make_coroutine,
        check=_check_lock_free,
        prepare=prepare,
        mode="delivered",
        cancel="task",
    )
    _assert_points(points, expect_check=True)


@pytest.mark.parametrize("case_id", LOCK_CASES, ids=LOCK_CASES)
def test_cancelled_write_leaves_no_lock(case_id):
    asyncio.run(_lock_scenario(case_id))
