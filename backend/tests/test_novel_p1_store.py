"""Offline database contract and stale-worker protection tests."""

import asyncio
import json

import aiosqlite
import pytest

import database
from novel.store_db import DbStepStore, get_db


async def _book(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "novel.db"))
    await database.init_db()
    await database.get_or_create_user("author")
    async with get_db() as db:
        await db.execute(
            """INSERT INTO novels(id,username,seed_idea,status,config_json,budget_strawberries,run_token)
               VALUES('book','author','seed','running','{}',10000,'token')"""
        )
        await db.commit()
    return DbStepStore("author", "book", "token")


def test_tables_have_owner_and_novel_indexes_without_new_migrations(monkeypatch, tmp_path):
    async def scenario():
        await _book(monkeypatch, tmp_path)
        async with get_db() as db:
            for table in ("novels", "novel_bible_versions", "novel_chapters", "novel_steps", "novel_notes"):
                async with db.execute(f"PRAGMA table_info({table})") as cursor:
                    columns = {row["name"]: row for row in await cursor.fetchall()}
                assert columns["username"]["notnull"] == 1
                async with db.execute(f"PRAGMA index_list({table})") as cursor:
                    indexes = await cursor.fetchall()
                assert indexes
            async with db.execute("SELECT version FROM schema_migrations") as cursor:
                versions = [row[0] for row in await cursor.fetchall()]
            assert not any("novel" in str(version).lower() for version in versions)
    asyncio.run(scenario())


def test_steps_digest_prompts_preserve_billing_and_resume_usage(monkeypatch, tmp_path):
    async def scenario():
        store = await _book(monkeypatch, tmp_path)
        usage = {"step_key": "step", "role": "editor", "model": "fake:local",
                 "input_tokens": 20, "output_tokens": 5, "cached_tokens": 3}
        await store.append_usage(usage)
        async with get_db() as db:
            await db.execute("UPDATE novel_steps SET strawberries_charged=7,billing_status='settled'")
            await db.commit()
        assert await store.write_step("step", {"status": "ok", "role": "editor", "model": "fake:local",
            "messages": [{"role": "user", "content": "PROMPT_SENTINEL"}], "result": {"valid": True},
            "usage": usage, "attempts": 1})
        saved = await store.read_step("step")
        assert saved["result"] == {"valid": True}
        assert len(saved["request_digest"]) == 64
        async with get_db() as db:
            async with db.execute("SELECT * FROM novel_steps") as cursor:
                row = dict(await cursor.fetchone())
        assert "PROMPT_SENTINEL" not in json.dumps(row)
        assert row["strawberries_charged"] == 7
        assert row["billing_status"] == "settled"
        resumed = await DbStepStore("author", "book", "token").initialize()
        assert resumed.total_tokens == 25
        assert resumed.used_tokens == 25
    asyncio.run(scenario())


@pytest.mark.parametrize("invalidate", ["token", "user", "novel"])
def test_obsolete_workers_cannot_write_any_artifacts(monkeypatch, tmp_path, invalidate):
    async def scenario():
        store = await _book(monkeypatch, tmp_path)
        async with get_db() as db:
            if invalidate == "token":
                await db.execute("UPDATE novels SET run_token='successor'")
            elif invalidate == "user":
                await db.execute("DELETE FROM users WHERE username='author'")
            else:
                await db.execute("DELETE FROM novels WHERE id='book'")
            await db.commit()
        assert not await store.write_step("stale", {"status": "ok", "result": {}})
        assert not await store.append_usage({"step_key": "stale", "input_tokens": 2})
        assert not await store.commit_setup({"title": "title"}, {"version": 1})
        async with get_db() as db:
            async with db.execute("SELECT COUNT(*) FROM novel_steps") as cursor:
                assert (await cursor.fetchone())[0] == 0
            async with db.execute("SELECT COUNT(*) FROM novel_bible_versions") as cursor:
                assert (await cursor.fetchone())[0] == 0
    asyncio.run(scenario())


def test_chapter_commit_is_atomic_and_cannot_double_count(monkeypatch, tmp_path):
    async def scenario():
        store = await _book(monkeypatch, tmp_path)
        meeting = {"decision": {"beat_sheet": {"title": "title"}, "ending_status": "continue",
                                "user_note_responses": [{"note_id": "N1", "response": "received", "adopted": True}]}}
        product = {"body": "# 第1章 title\n正文", "bible": {"version": 1}, "flags": [], "archive": {}}
        async with get_db() as db:
            await db.execute("INSERT INTO novel_notes(novel_id,username,text,status) VALUES('book','author','note','pending')")
            await db.commit()
        assert await store.commit_chapter(1, meeting, product)
        assert not await store.commit_chapter(1, meeting, product)
        async with get_db() as db:
            async with db.execute("SELECT chapters_done,bible_version FROM novels") as cursor:
                assert tuple(await cursor.fetchone()) == (1, 1)
            async with db.execute("SELECT status,delivered_chapter FROM novel_notes") as cursor:
                assert tuple(await cursor.fetchone()) == ("delivered", 1)
            async with db.execute("SELECT COUNT(*) FROM novel_bible_versions") as cursor:
                assert (await cursor.fetchone())[0] == 1
        broken = {**product, "bible": {"version": 2}}
        # An injected statement failure rolls back the chapter and the counters.
        async with get_db() as db:
            await db.execute("CREATE TRIGGER fail_bible BEFORE INSERT ON novel_bible_versions BEGIN SELECT RAISE(ABORT,'forced'); END")
            await db.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await store.commit_chapter(2, meeting, broken)
        async with get_db() as db:
            async with db.execute("SELECT chapters_done FROM novels") as cursor:
                assert (await cursor.fetchone())[0] == 1
            async with db.execute("SELECT COUNT(*) FROM novel_chapters WHERE chapter=2") as cursor:
                assert (await cursor.fetchone())[0] == 0
    asyncio.run(scenario())
