"""Exercise real novel reads end-to-end and compare every persisted cell."""
import asyncio
import ast
import json
from pathlib import Path
import sqlite3

import pytest

import database
from auth import create_token
from studio import sources


AUTHOR = "source-readonly-author"
OTHER = "source-readonly-other"
BOOK = "source-readonly-book"
BODY = "# 第1章 风入庭\n\n正文—原样保留。\n    空白。\n" + "长句。" * 2400


def novel_table_bytes():
    """Compare logical contents byte-for-byte, including internal JSON strings."""
    with sqlite3.connect(database.DB_PATH) as db:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND (name='novels' OR name GLOB 'novel_*') ORDER BY name"
        )]
        assert set(tables) == {"novels", "novel_bible_versions", "novel_chapters",
                               "novel_notes", "novel_steps"}
        return {name: json.dumps(db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall(),
                                 ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                for name in tables}


@pytest.fixture
def readonly_workshop(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", f"{AUTHOR},{OTHER}")
    monkeypatch.setenv("FIONA_NOVEL_CHAT", "1")
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", AUTHOR)
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "studio"))
    for username in (AUTHOR, OTHER):
        asyncio.run(database.get_or_create_user(username))
    with sqlite3.connect(database.DB_PATH) as db:
        for username, book_id in ((AUTHOR, BOOK), (OTHER, "other-book")):
            bible = {"version": 1, "locked": {"characters": []},
                     "dynamic": {"chapter_summaries": [], "foreshadowing": []}}
            db.execute("""INSERT INTO novels(id,username,title,seed_idea,status,config_json,
                          compass_json,bible_version,chapters_done,words_done,budget_strawberries,
                          completed_at) VALUES(?,?,?,'seed','completed',?,?,1,1,?,99999,?)""",
                       (book_id, username, "风入庭" if username == AUTHOR else "另一位作者的作品",
                        json.dumps({"drama_adaptation": True, "structure": "v2",
                                    "target": {"max_chapters": 1}, "_private": "never copy"}),
                        json.dumps({"title": "风入庭", "logline": "风吹入庭"}), len(BODY),
                        "2026-10-16 10:00:00"))
            db.execute("""INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source)
                          VALUES(?,?,1,?,'fixture')""", (book_id, username, json.dumps(bible)))
            db.execute("""INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,
                          flags_json,meeting_json,review_json,archive_json)
                          VALUES(?,?,1,'done','风入庭',?, ?, ?, '[]', '{}')""",
                       (book_id, username, BODY, '["review_degraded"]', json.dumps({
                           "brief": "private meeting", "decision": {"beat_sheet": {
                               "title": "风入庭", "chapter_goal": "开门", "scenes": [],
                               "beats": [], "opening_hook": "风", "ending_hook": "门"}}})))
            db.execute("""INSERT INTO novel_steps(novel_id,username,step_key,status,raw_response,
                          result_json) VALUES(?,?,'fixture-step','done',?,?)""",
                       (book_id, username, "raw response\n保持原样", '{"internal":"untouched"}'))
            db.execute("""INSERT INTO novel_notes(novel_id,username,text,status)
                          VALUES(?,?,'不应被消费的作者留言','pending')""", (book_id, username))
    user = asyncio.run(database.get_or_create_user(AUTHOR))
    headers = {"Authorization": f"Bearer {create_token(AUTHOR, user['session_version'])}"}
    return client, headers


def test_real_novel_tables_unchanged_across_snapshot_sync_and_chat(readonly_workshop, monkeypatch):
    client, headers = readonly_workshop
    before = novel_table_bytes()
    candidates = client.get("/studio/sources/novels", headers=headers)
    assert candidates.status_code == 200, candidates.text
    assert [book["id"] for book in candidates.json()["books"]] == [BOOK]
    assert novel_table_bytes() == before

    created = client.post("/studio/projects/from-novel", headers=headers,
                          json={"book_id": BOOK, "aspect": "16:9"})
    assert created.status_code == 201, created.text
    project = created.json()
    pid = project["id"]
    assert (project["source_kind"], project["snapshot_no"]) == ("novel", 1)
    assert novel_table_bytes() == before
    assert asyncio.run(sources.read_snapshot(AUTHOR, pid, 1, 1))[0]["body"] == BODY
    assert client.get(f"/studio/projects/{pid}/source", headers=headers).json()["drift"]["state"] == "unchanged"
    assert novel_table_bytes() == before
    synced = client.post(f"/studio/projects/{pid}/source/sync", headers=headers,
                         json={"expected_no": 1})
    assert synced.status_code == 200, synced.text
    assert synced.json()["snapshot"]["no"] == 2
    assert novel_table_bytes() == before

    from services import chat_service as chat
    for intent, params in (("novel_list", {}), ("novel_read", {"book": "风入庭", "chapter": "1"}),
                           ("novel_to_film", {"book": "风入庭"})):
        result = chat.execute_intent(intent, params, username=AUTHOR, auth_method="jwt")
        if intent == "novel_to_film":
            assert result["url"] == f"/studio/{pid}"
        elif intent == "novel_read":
            assert result["success"] and result["body_chars"] == 6000
            assert result["continuation"] == {"chapter": 1, "offset": 6000}
        else:
            assert "《风入庭》" in result
        assert novel_table_bytes() == before

    monkeypatch.setattr(chat, "recognize_intent", lambda *args, **kwargs: {
        "intent": "novel_read", "params": {"book": "风入庭", "chapter": "1"}, "missing": []})

    def forbid_reply_model(*args, **kwargs):
        pytest.fail("Platform novel reading must reply directly without a provider call")

    monkeypatch.setattr(chat, "_create_stream_with_fallback", forbid_reply_model)
    response = client.post("/chat", headers=headers, json={"message": "把《风入庭》第1章念给我听"})
    assert response.status_code == 200, response.text
    assert "以下是作者的小说原文" in response.text and '"done": true' in response.text
    assert novel_table_bytes() == before
    # A second source.start_film must reuse the existing project, with no model call.
    card = asyncio.run(sources.start_film(AUTHOR, "风入庭", "jwt"))
    assert card["url"] == f"/studio/{pid}"
    assert novel_table_bytes() == before


def test_real_foreign_book_and_project_are_hidden(readonly_workshop):
    client, headers = readonly_workshop
    before = novel_table_bytes()
    inaccessible = client.post("/studio/projects/from-novel", headers=headers,
                               json={"book_id": "other-book", "aspect": "16:9"})
    nonexistent = client.post("/studio/projects/from-novel", headers=headers,
                              json={"book_id": "missing-book", "aspect": "16:9"})
    assert inaccessible.status_code == nonexistent.status_code == 404
    assert inaccessible.json() == nonexistent.json() == {"detail": "作品不存在或无权访问"}
    project = asyncio.run(sources.create_novel_project(AUTHOR, BOOK))
    other_user = asyncio.run(database.get_or_create_user(OTHER))
    other_headers = {"Authorization": f"Bearer {create_token(OTHER, other_user['session_version'])}"}
    assert client.get(f"/studio/projects/{project['id']}/source", headers=other_headers).status_code == 404
    assert novel_table_bytes() == before


def test_real_drift_and_deleted_original_preserve_archived_text(readonly_workshop):
    client, headers = readonly_workshop
    project = asyncio.run(sources.create_novel_project(AUTHOR, BOOK))
    pid = project["id"]
    amended = "# 第1章 新标题\n\n作者修改过的正文。"
    # Only the test's simulated author edit writes the novel domain.
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE novel_chapters SET body=?,title='新标题' WHERE novel_id=?", (amended, BOOK))
        db.execute("UPDATE novels SET updated_at='2026-10-16 12:00:00' WHERE id=?", (BOOK,))
    after_author_edit = novel_table_bytes()
    status = client.get(f"/studio/projects/{pid}/source", headers=headers)
    assert status.status_code == 200
    assert status.json()["drift"]["changed"] == [1]
    assert novel_table_bytes() == after_author_edit
    assert asyncio.run(sources.read_snapshot(AUTHOR, pid, 1, 1))[0]["body"] == BODY
    synced = client.post(f"/studio/projects/{pid}/source/sync", headers=headers, json={"expected_no": 1})
    assert synced.status_code == 200 and synced.json()["snapshot"]["no"] == 2
    assert asyncio.run(sources.read_snapshot(AUTHOR, pid, 1, 1))[0]["body"] == amended
    from studio import storage
    assert storage.resolve_path(f"{pid}/source/snap-0001/chapters/0001.md").read_text() == BODY
    assert novel_table_bytes() == after_author_edit
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("DELETE FROM novels WHERE id=?", (BOOK,))
    after_author_delete = novel_table_bytes()
    unavailable = client.get(f"/studio/projects/{pid}/source", headers=headers)
    assert unavailable.status_code == 200 and unavailable.json()["drift"] == {"state": "unavailable"}
    assert asyncio.run(sources.read_snapshot(AUTHOR, pid, 1, 1))[0]["body"] == amended
    assert novel_table_bytes() == after_author_delete


def test_chat_novel_access_cannot_import_or_call_writer_functions():
    backend = Path(__file__).resolve().parents[1]
    paths = [backend / name for name in (
        "services/claude_agent.py", "intent_router.py", "services/chat_service.py",
        "routers/chat.py", "studio/novel_chat.py",
    )]
    allowed = {"list_books", "find_books", "detail", "bible", "chapter", "chapters_range"}
    for path in paths:
        tree = ast.parse(path.read_text())
        service_aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "novel":
                    assert all(alias.name == "service" for alias in node.names), path
                    service_aliases.update(alias.asname or alias.name for alias in node.names)
                elif node.module == "novel.service":
                    assert {alias.name for alias in node.names} <= allowed, path
                elif node.module and node.module.startswith("novel."):
                    assert node.module == "novel.runner" and {
                        alias.name for alias in node.names} <= {"is_editing"}, path
            elif isinstance(node, ast.Import):
                assert not any(alias.name == "novel" or alias.name.startswith("novel.")
                               for alias in node.names), path
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in service_aliases:
                    assert node.attr in allowed, (path, node.attr)


def test_repeated_cancellation_cannot_remove_a_committed_snapshot(readonly_workshop, monkeypatch):
    import aiosqlite
    original_commit = aiosqlite.Connection.commit

    async def scenario():
        committed = asyncio.Event()
        release_result = asyncio.Event()
        calls = 0

        async def delayed_commit(db):
            nonlocal calls
            calls += 1
            await original_commit(db)
            if calls == 2:
                # Model SQLite committing durably before the awaiter receives it.
                committed.set()
                await release_result.wait()

        monkeypatch.setattr(aiosqlite.Connection, "commit", delayed_commit)
        task = asyncio.create_task(sources.create_novel_project(AUTHOR, BOOK))
        await asyncio.wait_for(committed.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        release_result.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        from studio import store
        projects = await store.list_projects(AUTHOR)
        assert len(projects) == 1 and projects[0]["snapshot_no"] == 1
        assert (await sources.read_snapshot(AUTHOR, projects[0]["id"], 1, 1))[0]["body"] == BODY

    before = novel_table_bytes()
    asyncio.run(scenario())
    assert novel_table_bytes() == before
