"""Markdown downloads are authorized, complete, read-only projections of exchanges."""
import builtins
import html
import re
import sqlite3
from pathlib import Path

import pytest

from test_agent_exchanges import exchange_model, pair, _invite, _act  # noqa: F401
from test_official_agent_exchanges import owner, official_cards, _start, _wait  # noqa: F401


def _download(client, participant, exchange_id, document="readme"):
    return client.get(f"/agent-exchanges/{exchange_id}/export", headers=participant["headers"], params={"document": document})


def _assert_fenced_exact(markdown, content):
    for match in re.finditer(r"(?m)^(`{3,})(?:text)?\n", markdown):
        fence = match.group(1)
        if markdown[match.end():].startswith(content + "\n" + fence):
            assert len(fence) > max((len(run) for run in re.findall(r"`+", content)), default=0)
            return
    pytest.fail("Original text was not preserved inside a sufficiently long code fence")


def _legacy_detail(status="completed"):
    return {
        "exchange": {
            "id": "legacy-safe-id", "kind": "official", "status": status,
            "topic": "原始主题\n```text\n嵌套围栏\n``````\n主题结尾",
            "max_turns": 2, "turn_count": 1, "created_at": "2026-09-05 10:00:00", "updated_at": "2026-09-05 10:01:00",
            "summary": "## 已讨论的方案\n\n**保留 Markdown**\n\n<script>不执行</script> & 文字",
            "error": "", "viewer_role": "initiator", "owner_username": "PRIVATE_OWNER_CANARY",
            "profile": {"secret": "PRIVATE_PROFILE_CANARY"}, "api_key": "PRIVATE_KEY_CANARY",
            "initiator": {"id": "own-agent", "display_name": "我的分身", "bio": "公开简介", "avatar_emoji": "✨", "is_public": False,
                          "owner_username": "PRIVATE_OWNER_CANARY", "personality": "PRIVATE_PERSONALITY_CANARY"},
            "recipient": {"id": "official:script-editor", "display_name": "脚本编辑", "bio": "平台官方 AI", "avatar_emoji": "🎬", "kind": "official", "is_public": True},
            "usage": {"model_calls": 2, "total_tokens": 40},
        },
        "messages": [{"id": "message-1", "sequence": 1, "agent_id": "own-agent", "display_name": "我的分身", "avatar_emoji": "✨",
                      "content": "完整回复\n```````\n嵌套代码\n```\nMESSAGE_END", "created_at": "2026-09-05 10:00:30"}],
    }


@pytest.mark.parametrize("document", ["readme", "discussion"])
def test_renderer_preserves_fenced_text_and_markdown_but_escapes_summary_html(document):
    from exchange_exports import render_exchange_markdown

    detail = _legacy_detail()
    markdown = render_exchange_markdown(detail, document)
    _assert_fenced_exact(markdown, detail["exchange"]["topic"])
    assert html.escape(detail["exchange"]["summary"], quote=False) in markdown
    assert "**保留 Markdown**" in markdown and "<script>" not in markdown
    assert "我的分身" in markdown and "脚本编辑" in markdown
    assert "官方" in markdown and "AI" in markdown
    for private in ("PRIVATE_OWNER_CANARY", "PRIVATE_PROFILE_CANARY", "PRIVATE_KEY_CANARY", "PRIVATE_PERSONALITY_CANARY"):
        assert private not in markdown
    # An old snapshot lacks model metadata: current configuration cannot be
    # retroactively presented as the model that generated that old exchange.
    for model in ("DeepSeek", "deepseek-v4-pro", "Qwen", "qwen3.8-omni-flash"):
        assert model not in markdown
    if document == "discussion":
        _assert_fenced_exact(markdown, detail["messages"][0]["content"])
    else:
        assert re.search(r"\[[^\]]+\]\(discussion-legacy-safe-id\.md\)", markdown)


@pytest.mark.parametrize("status", ["running", "stopped"])
@pytest.mark.parametrize("document", ["readme", "discussion"])
def test_incomplete_exports_are_explicit_drafts_without_an_invented_summary(status, document):
    from exchange_exports import render_exchange_markdown

    detail = _legacy_detail(status)
    detail["exchange"]["summary"] = ""
    markdown = render_exchange_markdown(detail, document)
    assert "草稿" in markdown
    assert "模拟交流总结" not in markdown and "已讨论的方案" not in markdown
    assert "停止" in markdown if status == "stopped" else ("进行" in markdown or "交流中" in markdown)
    _assert_fenced_exact(markdown, detail["exchange"]["topic"])


@pytest.mark.parametrize("malicious_id", ["../secrets", 'safe\r\nX-Injected: yes', "中文角色", "a" * 200, "\x00/\\"])
def test_export_filenames_are_bounded_ascii_without_path_or_header_injection(malicious_id):
    from exchange_exports import export_filename

    assert export_filename(malicious_id, "readme") == "README.md"
    filename = export_filename(malicious_id, "discussion")
    assert re.fullmatch(r"discussion-[A-Za-z0-9_-]{1,64}\.md", filename)


def test_completed_official_downloads_keep_ten_thousand_character_topic_and_all_99_messages_without_writes(
    client, owner, official_cards, exchange_model, monkeypatch,
):
    import database

    start = "TOPIC_START\n```text\n嵌套围栏\n``````\n"
    end = "TOPIC_PAST_300_AND_END_🎥"
    topic = start + "原" * (10000 - len(start) - len(end)) + end
    exchange_model.reply_factory = lambda number: f"MSG_{number:03d}_START\n```\n用户提供代码\n````````\nMSG_{number:03d}_END"
    created = _start(client, owner, official_cards[0], topic=topic, max_turns=99)
    exchange_id = created["exchange"]["id"]
    final = _wait(client, owner, exchange_id)
    assert final["exchange"]["status"] == "completed"
    assert len(final["messages"]) == 99 and len(exchange_model.calls) == 100

    def database_snapshot():
        with sqlite3.connect(database.DB_PATH) as db:
            return {table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                    for table in ("agent_exchanges", "agent_exchange_messages", "agent_exchange_calls")}

    before = database_snapshot()
    real_open = builtins.open

    def reject_write_open(file, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+"), "Export attempted a filesystem write"
        return real_open(file, mode, *args, **kwargs)

    def reject_path_write(*args, **kwargs):
        pytest.fail("Export attempted to create a server-side file")

    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", reject_write_open)
        guarded.setattr(Path, "write_text", reject_path_write)
        guarded.setattr(Path, "write_bytes", reject_path_write)
        readme = _download(client, owner, exchange_id)
        discussion = _download(client, owner, exchange_id, "discussion")
        default = client.get(f"/agent-exchanges/{exchange_id}/export", headers=owner["headers"])
    assert readme.status_code == discussion.status_code == default.status_code == 200
    assert default.content == readme.content
    for response, filename in ((readme, "README.md"), (discussion, f"discussion-{exchange_id}.md")):
        assert response.headers["content-type"].lower().replace(" ", "") == "text/markdown;charset=utf-8"
        assert re.fullmatch(r'attachment; filename="?' + re.escape(filename) + r'"?', response.headers["content-disposition"])
        assert "private" in response.headers["cache-control"] and "no-store" in response.headers["cache-control"]
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.content.decode("utf-8") == response.text
        _assert_fenced_exact(response.text, topic)
        assert final["exchange"]["summary"] in response.text
        assert owner["headers"]["X-Dev-User"] not in response.text
    assert re.search(r"\[[^\]]+\]\(discussion-" + re.escape(exchange_id) + r"\.md\)", readme.text)
    for message in final["messages"]:
        _assert_fenced_exact(discussion.text, message["content"])
    positions = [discussion.text.index(message["content"]) for message in final["messages"]]
    assert positions == sorted(positions)
    assert database_snapshot() == before
    assert len(exchange_model.calls) == 100


@pytest.mark.parametrize("document", ["readme", "discussion"])
def test_official_export_requires_its_owner_and_peer_export_allows_both_participants(
    client, owner, official_cards, pair, exchange_model, document,
):
    official_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    _wait(client, owner, official_id)
    assert _download(client, owner, official_id, document).status_code == 200
    stranger = {"headers": {"X-Dev-User": "export_stranger"}}
    assert _download(client, stranger, official_id, document).status_code == 404
    assert client.get(f"/agent-exchanges/{official_id}/export").status_code == 401
    peer_id = _invite(client, pair)["id"]
    assert _act(client, pair[1], peer_id, "accept").status_code == 200
    _wait(client, pair[0], peer_id)
    for participant in pair:
        response = _download(client, participant, peer_id, document)
        assert response.status_code == 200, response.text
        assert all(person["agent"]["display_name"] in response.text for person in pair)
    assert _download(client, stranger, peer_id, document).status_code == 404
    assert len(exchange_model.calls) == 6


def test_running_and_stopped_api_exports_preserve_draft_status_without_generating(
    client, owner, official_cards, exchange_model,
):
    exchange_model.block(1)
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    try:
        assert exchange_model.started.wait(timeout=10)
        for document in ("readme", "discussion"):
            response = _download(client, owner, exchange_id, document)
            assert response.status_code == 200 and "草稿" in response.text
        assert len(exchange_model.calls) == 1
        assert client.post(f"/agent-exchanges/{exchange_id}/stop", headers=owner["headers"]).status_code == 200
        for document in ("readme", "discussion"):
            response = _download(client, owner, exchange_id, document)
            assert response.status_code == 200 and "草稿" in response.text and "停止" in response.text
        assert len(exchange_model.calls) == 1
    finally:
        exchange_model.release.set()
    _wait(client, owner, exchange_id)


def test_invalid_export_document_unknown_or_deleted_exchange_cannot_be_downloaded(
    client, owner, official_cards, exchange_model,
):
    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    _wait(client, owner, exchange_id)
    for document in ("unknown", "../README.md", "readme\r\nX-Injected:yes"):
        assert _download(client, owner, exchange_id, document).status_code == 422
    for malformed_id in ("unknown-exchange", "..%2F..%2Fsecrets", "bad%0D%0AX-Injected%3Ayes"):
        assert _download(client, owner, malformed_id).status_code in (404, 422)
    assert client.request("DELETE", "/account", headers=owner["headers"], json={"confirmation": owner["headers"]["X-Dev-User"]}).status_code == 200
    assert _download(client, owner, exchange_id).status_code == 404
    assert len(exchange_model.calls) == 3


@pytest.mark.parametrize("document", ["readme", "artifact", "discussion"])
@pytest.mark.parametrize("status,artifact_status,reason,approved", [
    ("completed", "approved", "review_approved", True),
    ("completed", "needs_revision", "turn_limit", False),
    ("completed", "draft", "no_progress", False),
    ("completed", "draft", "output_limit", False),
    ("completed", "draft", "incomplete_output", False),
    ("stopped", "approved", "", False),
    ("failed", "draft", "", False),
    ("running", "draft", "", False),
])
def test_workflow_exports_include_real_artifact_and_honest_review_status(document, status, artifact_status, reason, approved):
    from exchange_exports import render_exchange_markdown

    detail = _legacy_detail(status)
    artifact = "# 完整作品\n\n| 镜号 | 画面 |\n| --- | --- |\n" + "| 1 | 开场 |\n" * 3000 + "\n<script>不执行</script>\nARTIFACT_END"
    detail["exchange"].update(workflow_version="draft_review_v1", artifact=artifact, artifact_status=artifact_status, completion_reason=reason)
    detail["messages"][0]["stage"] = "draft"
    markdown = render_exchange_markdown(detail, document)
    if document in ("readme", "artifact"):
        assert html.escape(artifact, quote=False) in markdown
        assert "ARTIFACT_END" in markdown
    else:
        assert "主创初稿" in markdown
        _assert_fenced_exact(markdown, detail["messages"][0]["content"])
    if document != "artifact":
        _assert_fenced_exact(markdown, detail["exchange"]["topic"])
    assert "AI 审稿通过 · 待用户验收" in markdown if approved else "草稿" in markdown
    if not approved:
        assert "稿件状态：AI 审稿通过" not in markdown
    assert "已用回复：1 次；上限：2 次" in markdown
    assert "不代表已生成对应文件" in markdown
    assert "<script>" not in markdown
    for private in ("PRIVATE_OWNER_CANARY", "PRIVATE_PROFILE_CANARY", "PRIVATE_KEY_CANARY", "PRIVATE_PERSONALITY_CANARY"):
        assert private not in markdown
    if reason == "output_limit":
        assert "可能不完整" in markdown
    if reason == "incomplete_output":
        assert "模型输出未正常结束" in markdown


def test_workflow_artifact_download_preserves_permissions_and_stops_claiming_unapproved_finality(
    client, owner, official_cards, exchange_model,
):
    import database
    from exchange_exports import export_filename

    exchange_id = _start(client, owner, official_cards[0])["exchange"]["id"]
    _wait(client, owner, exchange_id)
    calls_before = len(exchange_model.calls)
    artifact = "# 真正写出的稿件\n\n最终交付内容。"
    assert _download(client, owner, exchange_id, "artifact").status_code == 404
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE agent_exchanges SET workflow_version = ?, artifact = ?, artifact_status = ?, completion_reason = ? WHERE id = ?",
                   ("draft_review_v1", artifact, "needs_revision", "turn_limit", exchange_id))
    response = _download(client, owner, exchange_id, "artifact")
    assert response.status_code == 200
    assert artifact in response.text and "草稿 · 待修订" in response.text
    assert response.headers["content-type"].lower().replace(" ", "") == "text/markdown;charset=utf-8"
    assert response.headers["content-disposition"] == f'attachment; filename="artifact-{exchange_id}.md"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/agent-exchanges/{exchange_id}/export?document=artifact").status_code == 401
    stranger = {"headers": {"X-Dev-User": "export_stranger"}}
    forbidden = _download(client, stranger, exchange_id, "artifact")
    assert forbidden.status_code == 404 and "稿件" not in forbidden.text
    assert _download(client, stranger, "unknown", "artifact").content == forbidden.content
    readme = _download(client, owner, exchange_id, "readme")
    assert artifact in readme.text and f"artifact-{exchange_id}.md" in readme.text
    assert len(exchange_model.calls) == calls_before
    assert re.fullmatch(r"artifact-[A-Za-z0-9_-]{1,64}\.md", export_filename('../bad\r\nX: yes', "artifact"))
