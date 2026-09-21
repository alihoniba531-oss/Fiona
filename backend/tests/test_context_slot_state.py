# -*- coding: utf-8 -*-
"""
T4 验收：聊天槽位状态（pending 追问 / mode 模式）的持久化与过期语义。

对应规格 §4.3 的六条：
  1. pending 过期即弃（含"未过期必须原样读回"的正控）
  2. 跨进程持久化（importlib.reload 模拟重启）
  3. since 必须是 datetime，且能与 naive 的 datetime.now() 相减（detect_mode 的写法）
  4. 元组键与字符串键互不串扰
  5. 按用户清空是 owner_username 等值匹配，不误删 "alice%" / "alice_bob"
  6. mode 24 小时兜底过期
外加：TTL 解析回落、往返一致、默认值不落库（不复活）、损坏 payload、免 init_db 兜底建表。
"""
import contextlib
import importlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

_COLUMNS = "state_key, kind, owner_username, payload_json, expires_at"


@pytest.fixture(autouse=True)
def slot_db(tmp_path, monkeypatch):
    """临时库隔离：绝不碰 backend/fiona.db。

    走一遍真正的 init_db()，顺带端到端验证 T4.1 的建表确实在里面。
    """
    import asyncio

    import database

    path = tmp_path / "slot.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    asyncio.run(database.init_db())
    return str(path)


def _rows(db_path, kind=None):
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        sql = f"SELECT {_COLUMNS} FROM chat_slot_state"
        if kind is None:
            return conn.execute(sql).fetchall()
        return conn.execute(f"{sql} WHERE kind = ?", (kind,)).fetchall()


def _expiry_of(db_path, kind):
    rows = _rows(db_path, kind)
    assert len(rows) == 1, rows
    return datetime.fromisoformat(rows[0][4])


def _seconds_left(db_path, kind):
    return (_expiry_of(db_path, kind) - datetime.now(timezone.utc)).total_seconds()


def _expire_rows(db_path, kind):
    """把某个 kind 的行 expires_at 改到过去（模拟时间流逝，不动 TTL 环境变量）。"""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute("UPDATE chat_slot_state SET expires_at = ? WHERE kind = ?", (past, kind))
        conn.commit()


def _rewrite_payload(db_path, kind, state_key, payload):
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "UPDATE chat_slot_state SET payload_json = ? WHERE kind = ? AND state_key = ?",
            (json.dumps(payload, ensure_ascii=False), kind, state_key),
        )
        conn.commit()


# ── T4.1 表结构 ────────────────────────────────────

def test_init_db_creates_chat_slot_state(slot_db):
    with contextlib.closing(sqlite3.connect(slot_db)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = [row[1] for row in conn.execute("PRAGMA table_info(chat_slot_state)")]
    assert "chat_slot_state" in tables
    assert columns == ["state_key", "kind", "owner_username", "payload_json", "expires_at", "updated_at"]


def test_slot_table_is_bootstrapped_without_init_db(tmp_path, monkeypatch):
    """既有测试（如 test_chat_branches.py:128）不经 init_db() 就直接调 set_pending，
    所以每次访问前都要兜底 CREATE TABLE IF NOT EXISTS。"""
    import database
    import intent_router
    import mode_switcher

    raw = tmp_path / "never_initialized.db"
    monkeypatch.setattr(database, "DB_PATH", str(raw))
    assert not raw.exists()

    intent_router.set_pending("alice", {"intent": "route", "params": {}, "missing": ["origin"]})
    assert intent_router.get_pending("alice")["intent"] == "route"
    mode_switcher.set_user_mode("alice", "mirror", "manual")
    assert mode_switcher.get_user_mode("alice")["mode"] == "mirror"

    with contextlib.closing(sqlite3.connect(str(raw))) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"chat_slot_state"}
    # 两种 kind 各自落一行，且 owner_username 都是 alice
    assert sorted(row[1] for row in _rows(str(raw))) == ["mode", "pending"]
    assert {row[2] for row in _rows(str(raw))} == {"alice"}


# ── §4.3 第 1 条：pending 过期即弃 ───────────────────

def test_pending_is_returned_while_fresh_and_dropped_once_expired(slot_db, monkeypatch):
    import intent_router

    payload = {"intent": "route", "params": {"destination": "北京西站"}, "missing": ["origin"]}
    intent_router.set_pending("alice", payload)
    # 正控：未过期时必须原样读回，否则"永远返回 None"的实现也能过这条
    assert intent_router.get_pending("alice") == payload
    assert 590 < _seconds_left(slot_db, "pending") <= 600

    # TTL=0 → 写入即过期
    monkeypatch.setenv("PENDING_TTL_SECONDS", "0")
    intent_router.set_pending("alice", payload)
    assert intent_router.get_pending("alice") is None
    assert _rows(slot_db, "pending") == []


def test_pending_row_written_earlier_is_deleted_when_read_after_expiry(slot_db):
    import intent_router

    key = ("alice", "conv1")
    intent_router.set_pending(key, {"intent": "get_datetime", "params": {}, "missing": []})
    assert intent_router.get_pending(key) is not None  # 正控

    _expire_rows(slot_db, "pending")
    assert intent_router.get_pending(key) is None
    assert _rows(slot_db, "pending") == []


def test_pending_ttl_is_read_per_call_not_frozen_at_import(slot_db, monkeypatch):
    import intent_router

    payload = {"intent": "route", "params": {}, "missing": ["origin"]}
    for ttl, low in (("60", 50), ("3600", 3500)):
        monkeypatch.setenv("PENDING_TTL_SECONDS", ttl)
        intent_router.set_pending("alice", payload)
        assert low < _seconds_left(slot_db, "pending") <= int(ttl)


@pytest.mark.parametrize("bad", ["abc", "", "  ", "12.5", "None"])
def test_pending_ttl_falls_back_to_default_when_unparsable(slot_db, monkeypatch, bad):
    import intent_router

    monkeypatch.setenv("PENDING_TTL_SECONDS", bad)
    intent_router.set_pending("alice", {"intent": "route", "params": {}, "missing": ["origin"]})
    assert intent_router.get_pending("alice") is not None  # 回落 600 秒，没当场过期
    assert 590 < _seconds_left(slot_db, "pending") <= 600


def test_pending_ttl_defaults_to_600_when_env_absent(slot_db, monkeypatch):
    import intent_router

    monkeypatch.delenv("PENDING_TTL_SECONDS", raising=False)
    intent_router.set_pending("alice", {"intent": "route", "params": {}, "missing": ["origin"]})
    assert 590 < _seconds_left(slot_db, "pending") <= 600


def test_pending_roundtrip_keeps_chinese_and_nested_structure(slot_db):
    import intent_router

    payload = {
        "intent": "travel_plan",
        "params": {
            "query": "国庆想去新疆玩 5 天",
            "预算": [1, 2.5, None, True],
            "nested": {"备注": '含"引号"与\\反斜杠', "空": {}},
        },
        "missing": ["origin", "destination"],
    }
    key = ("alice", "会话-中文-id")
    intent_router.set_pending(key, payload)
    assert intent_router.get_pending(key) == payload
    # 覆盖写入同样往返一致
    intent_router.set_pending(key, {"intent": "hot_topics", "params": {}, "missing": []})
    assert intent_router.get_pending(key) == {"intent": "hot_topics", "params": {}, "missing": []}


# ── §4.3 第 2 条：跨进程持久化 ───────────────────────

def test_pending_survives_module_reload(slot_db):
    """reload 模拟重启：模块级状态全丢，落库的槽位必须还在。

    旧实现是进程内裸 dict（intent_router._pending），reload 后必然读不到 → 这条对旧实现是红的。
    """
    import intent_router

    payload = {"intent": "route", "params": {"origin": "中关村"}, "missing": ["destination"]}
    intent_router.set_pending(("alice", "conv1"), payload)
    intent_router.set_pending("bob", {"intent": "hot_topics", "params": {}, "missing": []})
    # 进程内 dict 必须删干净，不保留缓存（多进程下缓存会不一致）
    assert not hasattr(intent_router, "_pending")

    reloaded = importlib.reload(intent_router)
    assert reloaded.get_pending(("alice", "conv1")) == payload
    assert reloaded.get_pending("bob")["intent"] == "hot_topics"


def test_mode_survives_module_reload(slot_db):
    import mode_switcher

    mode_switcher.set_user_mode(("alice", "conv1"), "mirror", "manual: '别给建议'")
    assert not hasattr(mode_switcher, "_mode_state")

    reloaded = importlib.reload(mode_switcher)
    state = reloaded.get_user_mode(("alice", "conv1"))
    assert state["mode"] == "mirror"
    assert state["last_trigger"] == "manual: '别给建议'"
    assert isinstance(state["since"], datetime)


# ── §4.3 第 3 条：since 类型与 naive 减法 ─────────────

def test_mode_since_is_naive_datetime_and_subtractable(slot_db):
    """detect_mode 里是 `datetime.now() - state["since"]`（naive 减 naive）。
    since 若变成字符串或 tz-aware，这行当场 TypeError。"""
    import mode_switcher

    key = ("alice", "conv1")
    mode_switcher.set_user_mode(key, "mirror", "manual: '你听就行'")
    state = mode_switcher.get_user_mode(key)
    assert state["mode"] == "mirror"
    assert isinstance(state["since"], datetime)
    assert state["since"].tzinfo is None

    elapsed = datetime.now() - state["since"]  # 照抄 detect_mode 的写法
    assert isinstance(elapsed, timedelta)
    assert timedelta(0) <= elapsed < timedelta(minutes=1)

    # 默认值路径同样必须是 naive datetime
    default_state = mode_switcher.get_user_mode("newcomer")
    assert default_state == {
        "mode": "friend", "since": default_state["since"], "last_trigger": None,
    }
    assert isinstance(default_state["since"], datetime) and default_state["since"].tzinfo is None
    assert datetime.now() - default_state["since"] >= timedelta(0)


def test_mirror_timeout_exit_logic_is_untouched_by_persistence(slot_db):
    """MIRROR_TIMEOUT_MINUTES=30 的既有退出判定一字不改，落库后照常工作。"""
    import mode_switcher

    key = ("alice", "conv1")
    mode_switcher.set_user_mode(key, "mirror", "manual: '别给建议'")
    # 刚切镜子：没超时 → 保持 mirror
    assert mode_switcher.detect_mode(None, key, "嗯，就是觉得有点累", []) == "mirror"

    # 把 since 拨到 31 分钟前（naive 本地时间，与 detect_mode 的减法同族）
    stale = (datetime.now() - timedelta(minutes=31)).isoformat()
    _rewrite_payload(slot_db, "mode", f"alice\x1fconv1", {
        "mode": "mirror", "since": stale, "last_trigger": "manual",
    })
    assert mode_switcher.detect_mode(None, key, "今天去了趟公园，走了很久很久", []) == "friend"
    assert mode_switcher.get_user_mode(key)["last_trigger"] == "timeout + new topic"


# ── §4.3 第 4 条：元组键与字符串键互不串扰 ────────────

def test_tuple_and_string_pending_keys_do_not_collide(slot_db):
    import intent_router

    account_level = {"intent": "route", "params": {}, "missing": ["origin"], "scope": "account"}
    conversation_level = {"intent": "generate_image", "params": {}, "missing": ["prompt"], "scope": "conv"}
    intent_router.set_pending("alice", account_level)
    intent_router.set_pending(("alice", "conv1"), conversation_level)

    assert intent_router.get_pending("alice") == account_level
    assert intent_router.get_pending(("alice", "conv1")) == conversation_level
    assert intent_router.get_pending(("alice", "conv2")) is None
    assert len(_rows(slot_db, "pending")) == 2

    # 单键清除只清自己那行
    intent_router.clear_pending("alice")
    assert intent_router.get_pending("alice") is None
    assert intent_router.get_pending(("alice", "conv1")) == conversation_level


def test_tuple_and_string_mode_keys_do_not_collide(slot_db):
    import mode_switcher

    mode_switcher.set_user_mode("alice", "mirror", "manual")
    mode_switcher.set_user_mode(("alice", "conv1"), "friend", "concrete question")
    assert mode_switcher.get_user_mode("alice")["mode"] == "mirror"
    assert mode_switcher.get_user_mode(("alice", "conv1"))["mode"] == "friend"
    assert len(_rows(slot_db, "mode")) == 2

    mode_switcher.clear_user_mode("alice")
    assert mode_switcher.get_user_mode("alice")["mode"] == "friend"  # 回落默认
    assert mode_switcher.get_user_mode(("alice", "conv1"))["last_trigger"] == "concrete question"


def test_pending_and_mode_share_the_table_without_interference(slot_db):
    import intent_router
    import mode_switcher

    intent_router.set_pending("alice", {"intent": "route", "params": {}, "missing": ["origin"]})
    mode_switcher.set_user_mode("alice", "mirror", "manual")
    assert {row[1] for row in _rows(slot_db)} == {"pending", "mode"}

    intent_router.clear_user_pending("alice")
    assert mode_switcher.get_user_mode("alice")["mode"] == "mirror"  # mode 行没被误删
    mode_switcher.clear_all_user_modes("alice")
    assert _rows(slot_db) == []


# ── §4.3 第 5 条：按用户清空是等值匹配 ────────────────

def test_clear_user_pending_uses_exact_owner_match(slot_db):
    """专防 LIKE / GLOB 前缀匹配：'alice%' 与 'alice_bob' 不能被 'alice' 的清空波及。"""
    import intent_router

    intent_router.set_pending("alice", {"intent": "route", "params": {}, "missing": ["origin"]})
    intent_router.set_pending(("alice", "conv1"), {"intent": "hot_topics", "params": {}, "missing": []})
    intent_router.set_pending(("alice", "conv2"), {"intent": "get_datetime", "params": {}, "missing": []})
    intent_router.set_pending("alice%", {"intent": "web_search", "params": {"query": "别删我"}, "missing": []})
    intent_router.set_pending("alice_bob", {"intent": "web_search", "params": {"query": "也别删我"}, "missing": []})
    intent_router.set_pending(("alice_bob", "conv9"), {"intent": "fetch_card", "params": {}, "missing": []})

    intent_router.clear_user_pending("alice")

    assert intent_router.get_pending("alice") is None
    assert intent_router.get_pending(("alice", "conv1")) is None
    assert intent_router.get_pending(("alice", "conv2")) is None
    assert intent_router.get_pending("alice%")["params"]["query"] == "别删我"
    assert intent_router.get_pending("alice_bob")["params"]["query"] == "也别删我"
    assert intent_router.get_pending(("alice_bob", "conv9"))["intent"] == "fetch_card"
    assert sorted(row[2] for row in _rows(slot_db, "pending")) == ["alice%", "alice_bob", "alice_bob"]


def test_clear_all_user_modes_uses_exact_owner_match(slot_db):
    import mode_switcher

    mode_switcher.set_user_mode("alice", "mirror", "manual")
    mode_switcher.set_user_mode(("alice", "conv1"), "mirror", "manual")
    mode_switcher.set_user_mode("alice%", "mirror", "manual")
    mode_switcher.set_user_mode("alice_bob", "mirror", "manual")
    mode_switcher.set_user_mode(("alice_bob", "conv9"), "mirror", "manual")

    mode_switcher.clear_all_user_modes("alice")

    assert mode_switcher.get_user_mode("alice")["mode"] == "friend"
    assert mode_switcher.get_user_mode(("alice", "conv1"))["mode"] == "friend"
    assert mode_switcher.get_user_mode("alice%")["mode"] == "mirror"
    assert mode_switcher.get_user_mode("alice_bob")["mode"] == "mirror"
    assert sorted(row[2] for row in _rows(slot_db, "mode")) == ["alice%", "alice_bob", "alice_bob"]


# ── §4.3 第 6 条：mode 24 小时兜底 ───────────────────

def test_mode_falls_back_to_friend_after_24h(slot_db):
    import mode_switcher

    key = ("alice", "conv1")
    mode_switcher.set_user_mode(key, "mirror", "manual")
    assert mode_switcher.get_user_mode(key)["mode"] == "mirror"  # 正控
    assert 23 * 3600 < _seconds_left(slot_db, "mode") <= 24 * 3600

    _expire_rows(slot_db, "mode")
    state = mode_switcher.get_user_mode(key)
    assert state["mode"] == "friend"
    assert state["last_trigger"] is None
    assert isinstance(state["since"], datetime)
    assert _rows(slot_db, "mode") == []  # 过期行被顺手删掉


def test_reads_do_not_persist_the_default_state(slot_db):
    """只返回默认值、绝不写库：否则"会话已删除"后的状态被读一次就复活
    （既有测试 test_agent_conversations.py 钉的就是这个不复活语义）。"""
    import intent_router
    import mode_switcher

    for _ in range(2):
        assert mode_switcher.get_user_mode("ghost")["mode"] == "friend"
        assert mode_switcher.get_user_mode(("ghost", "gone"))["mode"] == "friend"
        assert intent_router.get_pending("ghost") is None
    assert _rows(slot_db) == []

    # 过期被删掉之后再读，依然不写回默认值
    mode_switcher.set_user_mode("ghost", "mirror", "manual")
    _expire_rows(slot_db, "mode")
    assert mode_switcher.get_user_mode("ghost")["mode"] == "friend"
    assert mode_switcher.get_user_mode("ghost")["mode"] == "friend"
    assert _rows(slot_db) == []


def test_corrupt_payload_is_treated_as_absent_not_an_error(slot_db):
    import intent_router
    import mode_switcher

    intent_router.set_pending("alice", {"intent": "route", "params": {}, "missing": ["origin"]})
    mode_switcher.set_user_mode("alice", "mirror", "manual")
    with contextlib.closing(sqlite3.connect(slot_db)) as conn:
        conn.execute("UPDATE chat_slot_state SET payload_json = '{这不是 JSON'")
        conn.commit()

    assert intent_router.get_pending("alice") is None
    state = mode_switcher.get_user_mode("alice")
    assert state["mode"] == "friend" and isinstance(state["since"], datetime)

    # 结构不对（mode 取值非法）同样按不存在处理
    mode_switcher.set_user_mode("bob", "mirror", "manual")
    _rewrite_payload(slot_db, "mode", "bob", {"mode": "pirate", "since": datetime.now().isoformat()})
    assert mode_switcher.get_user_mode("bob")["mode"] == "friend"
