"""Draft/review persistence, atomic migration and publication safeguards."""
import asyncio
import json
import sqlite3

import aiosqlite
import pytest

import database
import exchange_store


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def workflow(client, monkeypatch):
    monkeypatch.setattr(exchange_store, "OFFICIAL_WORKFLOW_VERSION", "draft_review_v1")
    user = "workflow-owner"
    response = client.put("/agents/me", headers={"X-Dev-User": user}, json={
        "display_name": "稿件主人", "bio": "公开创作简介", "is_public": False,
    })
    assert response.status_code == 200

    def create(max_turns=99):
        detail, token = run(exchange_store.create_official_exchange(
            user, "official:short-video-creator", "写出完整的三镜头短片剧本。", max_turns,
        ))
        return user, detail["exchange"]["id"], token

    return create


def _finish(session, index, **result):
    user, exchange_id, token = session
    call_id = run(exchange_store.reserve_model_call(exchange_id, token, index, "turn", 129_024, 8192))
    assert call_id
    success = run(exchange_store.finish_model_call(
        exchange_id, token, call_id, index,
        result={"input_tokens": 12, "output_tokens": 8, **result},
    ))
    return success, run(exchange_store.exchange_details(user, exchange_id))


def _review(verdict="approved"):
    return {
        "verdict": verdict,
        "checks": [{"category": category, "requirement": "三镜头", "status": "met", "evidence": "镜头三"}
                   for category in sorted(exchange_store.WORKFLOW_REVIEW_CATEGORIES)],
        "issues": [] if verdict == "approved" else ["缺少结尾"],
    }


def test_v4_migration_preserves_all_values_indexes_and_triggers_and_is_idempotent(tmp_path):
    path = tmp_path / "before-workflow.db"

    async def migrate(*functions):
        async with aiosqlite.connect(path) as db:
            for function in functions:
                await function(db)

    run(migrate(exchange_store.migrate_exchanges_schema,
                exchange_store.migrate_official_exchanges_schema,
                exchange_store.migrate_extended_official_exchanges_schema))
    tables = ("agent_exchanges", "agent_exchange_messages", "agent_exchange_calls")
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for kind, recipient in (("peer", "other"), ("official", None)):
            db.execute("""INSERT INTO agent_exchanges
                (id, kind, initiator_username, recipient_username, initiator_agent_id, recipient_agent_id,
                 pair_key, initiator_json, recipient_json, topic, max_turns, turn_count, status,
                 run_token, inflight_call_id, model_calls, input_tokens, output_tokens, budget_used,
                 reserved_tokens, token_budget, summary, created_at, updated_at)
                VALUES (?, ?, 'owner', ?, 'agent-owner', 'agent-target', ?, '{}', '{}', '完整旧需求',
                        2, 1, 'running', 'old-token', ?, 2, 12, 8, 1520, 1500, 80000,
                        '原来的总结', '2026-09-01', '2026-09-02')""", (kind, kind, recipient, kind, f"{kind}-call"))
            db.execute("""INSERT INTO agent_exchange_messages
                (id, exchange_id, sequence, agent_id, display_name, avatar_emoji, content)
                VALUES (?, ?, 1, 'agent-owner', '原始分身', '🌟', '完整旧消息')""", (f"{kind}-message", kind))
            db.execute("""INSERT INTO agent_exchange_calls
                (id, exchange_id, ordinal, kind, reserved_tokens, input_limit, output_limit, provider, model)
                VALUES (?, ?, 2, 'turn', 1500, 1244, 256, 'recorded-provider', 'recorded-model')""", (f"{kind}-call", kind))
        db.execute("CREATE INDEX workflow_test_topic ON agent_exchanges(topic)")
        db.execute("CREATE TABLE workflow_audit (exchange_id TEXT)")
        db.execute("""CREATE TRIGGER workflow_test_trigger AFTER UPDATE OF topic ON agent_exchanges
            BEGIN INSERT INTO workflow_audit VALUES (NEW.id); END""")
        before = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")] for table in tables}
        schema_before = list(db.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('index','trigger') ORDER BY name"))
        schema_before = [tuple(row) for row in schema_before]
    run(migrate(exchange_store.migrate_workflow_exchanges_schema, exchange_store.migrate_workflow_exchanges_schema))
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for table, old_rows in before.items():
            additions = ({"workflow_version": "", "artifact": "", "artifact_status": "", "completion_reason": ""}
                         if table == "agent_exchanges" else {"stage": "", "review_json": ""}
                         if table == "agent_exchange_messages" else {})
            assert [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")] == [
                {**row, **additions} for row in old_rows
            ]
        assert [tuple(row) for row in db.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('index','trigger') ORDER BY name")] == schema_before
        assert db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=?", (exchange_store.WORKFLOW_MIGRATION_VERSION,)).fetchone()[0] == 1
        db.execute("UPDATE agent_exchanges SET topic='更新' WHERE id='official'")
        assert [tuple(row) for row in db.execute("SELECT * FROM workflow_audit")] == [("official",)]


def test_v4_migration_rolls_back_every_column_on_failure(tmp_path):
    path = tmp_path / "rollback.db"

    async def scenario():
        async with aiosqlite.connect(path) as db:
            await exchange_store.migrate_exchanges_schema(db)
            await exchange_store.migrate_official_exchanges_schema(db)
            await exchange_store.migrate_extended_official_exchanges_schema(db)
            await db.execute("""CREATE TRIGGER reject_workflow_migration BEFORE INSERT ON schema_migrations
                WHEN NEW.version = '20260905_official_exchange_workflow_v4'
                BEGIN SELECT RAISE(ABORT, 'injected migration failure'); END""")
            await db.commit()
            with pytest.raises(sqlite3.IntegrityError, match="injected migration failure"):
                await exchange_store.migrate_workflow_exchanges_schema(db)
            async with db.execute("PRAGMA table_info(agent_exchanges)") as cursor:
                assert "artifact" not in [row[1] for row in await cursor.fetchall()]
            async with db.execute("PRAGMA table_info(agent_exchange_messages)") as cursor:
                assert "stage" not in [row[1] for row in await cursor.fetchall()]
            await db.execute("DROP TRIGGER reject_workflow_migration")
            await db.commit()
            await exchange_store.migrate_workflow_exchanges_schema(db)

    run(scenario())


def test_new_workflow_saves_full_artifact_reviews_and_approval_in_one_call(workflow):
    session = workflow()
    draft = "# 初稿\n\n" + "需要保留的完整内容。" * 1800 + "\n镜头三"
    success, detail = _finish(session, 0, stage="draft", content=draft)
    assert success and detail["exchange"]["artifact"] == draft
    assert detail["exchange"]["artifact_status"] == "draft"
    assert detail["exchange"]["workflow_version"] == "draft_review_v1"
    assert detail["exchange"]["usage"]["max_model_calls"] == 99
    context = run(exchange_store.load_running_exchange(session[1], session[2]))
    assert context["artifact"] == draft and context["messages"][0]["stage"] == "draft"
    success, detail = _finish(session, 1, stage="review", content="仍需补足结尾。", review=_review("needs_revision"))
    assert success and detail["exchange"]["artifact"] == draft
    revised = draft + "\n## 结尾\n镜头三给出完整结尾。"
    success, detail = _finish(session, 2, stage="revision", content=revised)
    assert success and detail["exchange"]["artifact"] == revised
    success, detail = _finish(session, 3, stage="review", content="逐项核对通过。", review=_review(),
                              finalize={"status": "approved", "reason": "review_approved"})
    assert success
    exchange = detail["exchange"]
    assert exchange["status"] == "completed" and exchange["artifact_status"] == "approved"
    assert exchange["completion_reason"] == "review_approved" and "待用户验收" in exchange["summary"]
    assert exchange["turn_count"] == exchange["usage"]["model_calls"] == 4
    assert exchange["usage"]["reserved_tokens"] == 0
    assert exchange["has_artifact"] is True
    records = run(exchange_store.list_exchanges(session[0]))
    assert len(records) == 1
    assert "artifact" not in records[0] and records[0]["has_artifact"] is True
    assert records[0] == {key: value for key, value in exchange.items() if key != "artifact"}
    assert [m["stage"] for m in detail["messages"]] == ["draft", "review", "revision", "review"]
    assert detail["messages"][-1]["review"] == json.loads(detail["messages"][-1]["review_json"]) == _review()
    assert run(exchange_store.reserve_model_call(session[1], session[2], 4, "turn", 100, 10)) is None
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute("SELECT run_token FROM agent_exchanges WHERE id=?", (session[1],)).fetchone() == (None,)


@pytest.mark.parametrize("invalid", [
    {"stage": "revision"},
    {"stage": "draft", "content": ""},
    {"stage": "draft", "content": "长" * (exchange_store.MAX_WORKFLOW_CONTENT_CHARS + 1)},
    {"stage": "draft", "review": {}},
    {"stage": "draft", "finalize": {"status": "approved", "reason": "review_approved"}},
    {"stage": "draft", "finalize": {"status": "needs_revision", "reason": "turn_limit"}},
    {"stage": "draft", "finalize": {"status": "needs_revision", "reason": "forged"}},
])
def test_invalid_writer_metadata_never_publishes_and_settles_usage(workflow, invalid):
    session = workflow()
    success, detail = _finish(session, 0, **{"content": "不能发布的内容", **invalid})
    assert not success
    assert detail["messages"] == [] and detail["exchange"]["artifact"] == ""
    assert detail["exchange"]["status"] == "failed"
    assert detail["exchange"]["usage"]["reserved_tokens"] == 0
    assert detail["exchange"]["usage"]["total_tokens"] == 20
    assert detail["exchange"]["has_artifact"] is False


@pytest.mark.parametrize("review", [
    {"verdict": "needs_revision", "checks": [{"status": "met"}], "issues": []},
    {"verdict": "approved", "checks": [], "issues": []},
    {"verdict": "approved", "checks": [{"status": "missing"}], "issues": []},
    {"verdict": "approved", "checks": [{"status": "met"}], "issues": ["未解决"]},
    {"verdict": "approved", "checks": [{"category": "deliverable", "status": "met"}], "issues": []},
    {"verdict": "approved", "checks": [{"category": category, "status": "met"}
                                         for category in ("deliverable", "constraints", "consistency", "usability", "unknown")], "issues": []},
])
def test_approval_requires_passing_checks_and_no_issues(workflow, review):
    session = workflow()
    assert _finish(session, 0, stage="draft", content="# 已保存初稿")[0]
    success, detail = _finish(session, 1, stage="review", content="不能发布的审稿", review=review,
                              finalize={"status": "approved", "reason": "review_approved"})
    assert not success and len(detail["messages"]) == 1
    assert detail["exchange"]["artifact"] == "# 已保存初稿"
    assert detail["exchange"]["artifact_status"] == "draft"


def test_turn_limit_keeps_artifact_as_needs_revision_without_summary_call(workflow):
    session = workflow(2)
    assert _finish(session, 0, stage="draft", content="# 未完成初稿")[0]
    success, detail = _finish(session, 1, stage="review", content="需要补足结尾。", review=_review("needs_revision"),
                              finalize={"status": "needs_revision", "reason": "turn_limit"})
    assert success and detail["exchange"]["status"] == "completed"
    assert detail["exchange"]["artifact_status"] == "needs_revision"
    assert detail["exchange"]["completion_reason"] == "turn_limit"
    assert detail["exchange"]["usage"]["max_model_calls"] == 2
    assert run(exchange_store.reserve_model_call(session[1], session[2], 2, "summary", 100, 10)) is None


def test_full_document_at_shared_character_limit_is_saved_without_truncation(workflow):
    session = workflow()
    draft = "x" * exchange_store.MAX_WORKFLOW_CONTENT_CHARS
    success, detail = _finish(session, 0, stage="draft", content=draft)
    assert success
    assert detail["exchange"]["artifact"] == draft
    assert detail["messages"][0]["content"] == draft


def test_abnormal_provider_finish_retains_draft_with_distinct_reason(workflow):
    session = workflow()
    success, detail = _finish(session, 0, stage="draft", content="# 尚未正常结束的稿件",
                              finalize={"status": "needs_revision", "reason": "incomplete_output"})
    assert success
    assert detail["exchange"]["status"] == "completed"
    assert detail["exchange"]["artifact_status"] == "needs_revision"
    assert detail["exchange"]["completion_reason"] == "incomplete_output"
    assert "模型输出未正常结束" in detail["exchange"]["summary"]


def test_stop_discards_late_approval_without_losing_draft_or_usage(workflow):
    session = workflow()
    user, exchange_id, token = session
    assert _finish(session, 0, stage="draft", content="# 要保留的稿件")[0]
    call_id = run(exchange_store.reserve_model_call(exchange_id, token, 1, "turn", 129024, 8192))
    assert call_id
    run(exchange_store.transition_exchange(user, exchange_id, "stop"))
    assert not run(exchange_store.finish_model_call(exchange_id, token, call_id, 1, result={
        "content": "迟到审稿", "stage": "review", "review": _review(),
        "finalize": {"status": "approved", "reason": "review_approved"},
        "input_tokens": 30, "output_tokens": 40,
    }))
    detail = run(exchange_store.exchange_details(user, exchange_id))
    assert detail["exchange"]["status"] == "stopped"
    assert detail["exchange"]["artifact"] == "# 要保留的稿件"
    assert detail["exchange"]["artifact_status"] == "draft" and len(detail["messages"]) == 1
    assert detail["exchange"]["usage"]["total_tokens"] == 90
    assert detail["exchange"]["usage"]["reserved_tokens"] == 0


def test_compatibility_flag_creates_legacy_session_and_preserves_extra_summary_call(workflow, monkeypatch):
    monkeypatch.setattr(exchange_store, "OFFICIAL_WORKFLOW_VERSION", "")
    session = workflow(2)
    for index in range(2):
        success, detail = _finish(session, index, content=f"旧交流 {index}")
        assert success and detail["messages"][-1]["stage"] == ""
    assert detail["exchange"]["workflow_version"] == ""
    assert detail["exchange"]["usage"]["max_model_calls"] == 3
    call_id = run(exchange_store.reserve_model_call(session[1], session[2], 2, "summary", 100, 10))
    assert call_id
    assert run(exchange_store.finish_model_call(session[1], session[2], call_id, 2, result={"content": "保留旧总结"}))
    detail = run(exchange_store.exchange_details(session[0], session[1]))
    assert detail["exchange"]["summary"] == "保留旧总结" and detail["exchange"]["artifact"] == ""
