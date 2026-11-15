# -*- coding: utf-8 -*-
"""真实写路径上的取消点扫描：byok.store、song.store、studio.sources。

每个参数在独立临时库里调用一次真实业务函数，用 ``cancel_sweep`` 把取消依次
落在第 k 次 aiosqlite 调用上；检查函数在任务对象仍被引用时尝试 ``BEGIN IMMEDIATE``，
确认写锁已经释放。准备数据保证写事务里至少有一条 SELECT 会返回行。
"""
import asyncio
import base64
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite
import pytest

import database
import song.store as song_store
from byok import crypto
from byok import store as byok_store
from cancel_sweep import sweep_cancel_points, write_lock_is_free
from studio import sources as studio_sources
from studio import store as studio_store


SECRET = base64.urlsafe_b64encode(b"a" * 32).decode()
USERNAME = "cancel_misc_user"
API_KEY = "sk-cancel-path-1234"
SONG_TEXT = "# 第一章 起\n风吹过山岗。\n# 第二章 承\n云落在远方。\n"
SONG_SECTIONS = [
    {"id": "s1", "lines": ["风吹过山岗", "云落在远方"]},
    {"id": "s2", "lines": ["我们一起唱", "唱到天亮"]},
]
SONG_STRUCTURE = [
    {"id": "s1", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
    {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
]


@dataclass(frozen=True)
class CancelCase:
    """一个被测函数的准备、复位和协程工厂。"""

    name: str
    setup: Callable[[dict], Awaitable[None]]
    reset: Callable[[dict], Awaitable[None]]
    build: Callable[[dict], Callable[[], Awaitable[object]]]


async def _insert_user(username: str) -> None:
    """普通 INSERT（不用 INSERT OR IGNORE），插入后断言行真的在。"""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (username, session_version) VALUES (?, 1)",
            (username,),
        )
        await db.commit()
        async with db.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ) as cursor:
            assert await cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# byok.store.save_config
# ---------------------------------------------------------------------------


async def _byok_setup(state: dict) -> None:
    await _insert_user(USERNAME)
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(byok_store.USER_MODEL_CONFIGS_DDL)
        await db.commit()
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'user_model_configs'"
        ) as cursor:
            assert await cursor.fetchone() is not None
    state["username"] = USERNAME


async def _byok_reset(state: dict) -> None:
    """清掉上一轮写入的配置与用户，重新建一个只有用户的初始状态。"""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_model_configs WHERE username = ?", (state["username"],)
        )
        await db.execute("DELETE FROM users WHERE username = ?", (state["username"],))
        await db.execute(
            "INSERT INTO users (username, session_version) VALUES (?, 1)",
            (state["username"],),
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM user_model_configs WHERE username = ?",
            (state["username"],),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0
        async with db.execute(
            "SELECT username FROM users WHERE username = ?", (state["username"],)
        ) as cursor:
            assert await cursor.fetchone() is not None


def _byok_build(state: dict) -> Callable[[], Awaitable[object]]:
    async def run():
        return await byok_store.save_config(
            state["username"],
            provider="deepseek",
            model="deepseek-v4-pro",
            api_key=API_KEY,
        )

    return run


# ---------------------------------------------------------------------------
# song.store.save_lyrics
# ---------------------------------------------------------------------------


async def _song_setup(state: dict) -> None:
    import agent_store

    await _insert_user(USERNAME)
    conversation = await agent_store.create_conversation(USERNAME, "取消点写歌")
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM conversations WHERE id = ? AND owner_username = ?",
            (conversation["id"], USERNAME),
        ) as cursor:
            assert await cursor.fetchone() is not None
    project = await song_store.create_project(
        owner_username=USERNAME,
        conversation_id=conversation["id"],
        title="取消点测试",
        brief={"theme": "取消", "language": "Chinese", "duration_seconds": 60},
        structure=SONG_STRUCTURE,
    )
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute(
            "SELECT lyrics_revision FROM song_projects WHERE id = ? AND owner_username = ?",
            (project["id"], USERNAME),
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None and row[0] == 0
    state["project_id"] = project["id"]
    state["conversation_id"] = conversation["id"]


async def _song_reset(state: dict) -> None:
    """把项目歌词 revision 复位到 0，并清掉本轮可能插入的歌词行。"""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "DELETE FROM song_lyrics WHERE project_id = ?", (state["project_id"],)
        )
        await db.execute(
            """UPDATE song_projects
                  SET lyrics_revision = 0, revision = 0
                WHERE id = ? AND owner_username = ?""",
            (state["project_id"], USERNAME),
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM song_lyrics WHERE project_id = ?",
            (state["project_id"],),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0
        async with db.execute(
            "SELECT lyrics_revision FROM song_projects WHERE id = ? AND owner_username = ?",
            (state["project_id"], USERNAME),
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None and row[0] == 0


def _song_build(state: dict) -> Callable[[], Awaitable[object]]:
    async def run():
        return await song_store.save_lyrics(
            state["project_id"],
            owner_username=USERNAME,
            conversation_id=state["conversation_id"],
            base_revision=0,
            sections=SONG_SECTIONS,
            check={"ok": True, "errors": [], "warnings": []},
            changed_section_ids=["s2"],
        )

    return run


# ---------------------------------------------------------------------------
# studio.sources._save_snapshot
# ---------------------------------------------------------------------------


async def _studio_setup(state: dict) -> None:
    await _insert_user(USERNAME)
    project = await studio_store.create_project(USERNAME, "取消点短片", "16:9")
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute(
            "SELECT snapshot_no FROM studio_projects WHERE id = ? AND owner = ?",
            (project["id"], USERNAME),
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None and row[0] == 0
    snapshot = await studio_sources.take_text_snapshot(
        USERNAME, "paste", "取消点文本", SONG_TEXT
    )
    assert snapshot["manifest"]["chapters"]
    assert len(snapshot["bodies"]) == len(snapshot["manifest"]["chapters"])
    state["project_id"] = project["id"]
    state["snapshot"] = snapshot
    state["studio_dir"] = Path(os.environ["FIONA_STUDIO_DIR"])


async def _studio_reset(state: dict) -> None:
    """清理快照行与文件目录，把项目 snapshot_no 复位到 0。"""
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "DELETE FROM studio_snapshots WHERE project_id = ? AND owner = ?",
            (state["project_id"], USERNAME),
        )
        await db.execute(
            """UPDATE studio_projects
                  SET snapshot_no = 0, source_kind = NULL, source_ref = NULL
                WHERE id = ? AND owner = ?""",
            (state["project_id"], USERNAME),
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM studio_snapshots WHERE project_id = ?",
            (state["project_id"],),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0
        async with db.execute(
            "SELECT snapshot_no FROM studio_projects WHERE id = ? AND owner = ?",
            (state["project_id"], USERNAME),
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None and row[0] == 0
    # _write_snapshot 用 "xb"/rename 写文件；下一轮开始前必须删掉上一轮目录，
    # 否则目标已存在会让它 409 提前结束，扫不到数据库取消点。
    shutil.rmtree(
        state["studio_dir"] / state["project_id"] / "source", ignore_errors=True
    )


def _studio_build(state: dict) -> Callable[[], Awaitable[object]]:
    async def run():
        return await studio_sources._save_snapshot(
            USERNAME, state["project_id"], 1, state["snapshot"], 0
        )

    return run


CASES = [
    CancelCase("byok.store.save_config", _byok_setup, _byok_reset, _byok_build),
    CancelCase("song.store.save_lyrics", _song_setup, _song_reset, _song_build),
    CancelCase("studio.sources._save_snapshot", _studio_setup, _studio_reset, _studio_build),
]


@pytest.mark.parametrize("case", CASES, ids=[item.name for item in CASES])
def test_cancelled_write_leaves_no_lock(tmp_path, monkeypatch, case):
    """每个取消点上：任务以 CancelledError 结束，且写锁已经空闲。"""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "cancel_misc.db"))
    monkeypatch.setattr(database, "SQLITE_BUSY_TIMEOUT", 0.3)
    monkeypatch.setenv("FIONA_BYOK_SECRET", SECRET)
    monkeypatch.delenv("FIONA_BYOK_SECRET_PREVIOUS", raising=False)
    for name in crypto.FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "studio"))
    state: dict = {}

    async def scenario():
        await database.init_db()
        await case.setup(state)

        async def check(point):
            return await write_lock_is_free(database.DB_PATH)

        points = await sweep_cancel_points(
            case.build(state),
            check=check,
            prepare=lambda: case.reset(state),
            mode="delivered",
            cancel="task",
        )
        assert points, f"{case.name}: 一个取消点都没扫到"
        for point in points:
            assert point.cancelled is True, (
                f"{case.name} k={point.k} [{point.label}] 任务没有以 CancelledError 结束"
            )
            assert point.check_result is True, (
                f"{case.name} k={point.k} [{point.label}] 取消后写锁仍被占用"
            )

    asyncio.run(scenario())
