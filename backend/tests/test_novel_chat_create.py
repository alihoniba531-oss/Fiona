"""聊天建书：草稿存储、Claude 工具、向导消费与清理的离线契约。

全部用例只使用临时 SQLite、模拟传输与源码副本，不访问网络，也不依赖
git 历史。规格：docs/tasks/2026-11-02-chat-create-novel/02-spec.md。
"""
import asyncio
import json
from pathlib import Path
import socket
import sqlite3
import types
from types import SimpleNamespace as NS

import pytest

from test_claude_agent_runtime import FakeStream, call, harness, message, run

# harness 夹具会替换 _save_response；需要验证刷新重建时恢复生产实现。
from services.chat_service import _save_response as _REAL_SAVE_RESPONSE


ROOT = Path(__file__).resolve().parents[2]
USER = "agent-user"
OTHER = "other"
DRAFT_ARGS = {
    "title": "归墟来信",
    "seed_idea": "一位替亡人修补家书的匠人，在无名信里读到自己的明天。",
    "min_chapters": 40,
    "max_chapters": 60,
    "chapter_words": 1800,
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """禁止真实 TCP / DNS，只放行回环地址。"""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def blocked(*args, **kwargs):
        raise AssertionError("聊天建书测试禁止真实网络连接和 DNS")

    monkeypatch.setattr(
        socket.socket, "connect",
        lambda sock, addr: blocked() if sock.family in (socket.AF_INET, socket.AF_INET6) else original_connect(sock, addr),
    )
    monkeypatch.setattr(
        socket.socket, "connect_ex",
        lambda sock, addr: blocked() if sock.family in (socket.AF_INET, socket.AF_INET6) else original_connect_ex(sock, addr),
    )
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        monkeypatch.setattr(socket, name, blocked)


@pytest.fixture
def enabled(monkeypatch):
    """小说聊天与工作室门控打开；新开关由各用例显式控制。"""
    monkeypatch.setenv("FIONA_NOVEL_CHAT", "1")
    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", f"author, {USER}, {OTHER}")
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", f"author, {USER}, {OTHER}")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")


@pytest.fixture
def create_enabled(enabled, monkeypatch):
    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "1")


@pytest.fixture
def draft_db(tmp_path, monkeypatch):
    """临时库 + 本人两个会话 + 另一个账号的会话。"""
    import agent_store
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "draft-create.db"))
    asyncio.run(database.init_db())

    async def setup():
        await database.get_or_create_user(USER)
        await database.get_or_create_user(OTHER)
        owner = (await agent_store.create_conversation(USER))["id"]
        owner_second = (await agent_store.create_conversation(USER))["id"]
        other = (await agent_store.create_conversation(OTHER))["id"]
        return owner, owner_second, other

    owner, owner_second, other = asyncio.run(setup())
    return NS(path=database.DB_PATH, owner=owner, owner_second=owner_second,
              other=other, db=database, agent_store=agent_store)


def _draft_rows():
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM novel_drafts ORDER BY created_at, id")]


def _count(table):
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _balance():
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute("SELECT strawberry_balance FROM users WHERE username = ?", (USER,)).fetchone()[0]


def _configure_turn(h, conversation):
    h.ctx.conversation_id = conversation


def _run_draft_turn(h, *arguments, final="收到了。"):
    for index, args in enumerate(arguments):
        h.streams.append(FakeStream(message("tool_use", content=[call("draft_novel", args, identity=f"draft-tool-{index}")])))
    h.streams.append(FakeStream(message(text=final), final))
    return run(h)


def _cards(events):
    return [event["card"] for event in events if isinstance(event, dict) and "card" in event]


def _assistant_rows(conversation):
    import agent_store

    result = asyncio.run(agent_store.get_conversation_messages(USER, conversation))
    return [message for message in result["messages"] if message["role"] == "assistant"]


def _load_module(name, source):
    module = types.ModuleType(name)
    module.__file__ = f"<{name}>"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _require_drafts():
    """HEAD 对照时先以 AssertionError 失败，而不是 ImportError / sqlite 错误。"""
    assert (ROOT / "backend/novel/drafts.py").is_file(), "novel/drafts.py 尚未实现"


def check_one_draft(rows):
    assert len(rows) == 1, rows


def check_foreign_draft_stored_null(stored):
    assert stored is None, stored


# ────────────────────────── 开关矩阵 ──────────────────────────


@pytest.mark.parametrize("method,crisis,base", [
    (None, None, {"list_novels", "read_novel"}),
    ("dev", None, {"list_novels", "read_novel"}),
    ("jwt", None, {"list_novels", "read_novel", "start_film"}),
    ("jwt", "possible", set()),
    ("jwt", "high", set()),
])
def test_switch_matrix_keeps_original_sets_and_object_identity(enabled, monkeypatch, method, crisis, base):
    assert "draft_novel" in (ROOT / "backend/services/claude_agent.py").read_text(encoding="utf-8")
    import services.chat_service as chat
    import services.claude_agent as agent

    ctx = chat.ChatContext("agent-user", "建书", False, None, "建书", [], 0, "persona", [], auth_method=method)
    state = chat.ChatState(trace={}, crisis_level=crisis)
    constant_names = {tool["name"] for tool in agent.CLAUDE_CLIENT_TOOLS}
    assert constant_names == {"get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image"}

    for value in ("0", None, "true"):
        if value is None:
            monkeypatch.delenv("FIONA_NOVEL_CHAT_CREATE", raising=False)
        else:
            monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", value)
        tools = agent.client_tools_for_turn(ctx, state)
        assert {tool["name"] for tool in tools} - constant_names == base
        if not base:
            assert tools is agent.CLAUDE_CLIENT_TOOLS
        else:
            assert tools is not agent.CLAUDE_CLIENT_TOOLS

    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "1")
    tools = agent.client_tools_for_turn(ctx, state)
    expected = set(base)
    if crisis is None:
        expected.add("draft_novel")
    assert {tool["name"] for tool in tools} - constant_names == expected
    if crisis is None:
        assert tools is not agent.CLAUDE_CLIENT_TOOLS
    else:
        assert tools is agent.CLAUDE_CLIENT_TOOLS


@pytest.mark.parametrize("novel_chat,user", [("0", USER), ("1", "stranger")])
def test_create_switch_still_requires_novel_chat_and_whitelist(enabled, monkeypatch, novel_chat, user):
    assert "draft_novel" in (ROOT / "backend/services/claude_agent.py").read_text(encoding="utf-8")
    import services.chat_service as chat
    import services.claude_agent as agent

    monkeypatch.setenv("FIONA_NOVEL_CHAT", novel_chat)
    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "1")
    ctx = chat.ChatContext(user, "建书", False, None, "建书", [], 0, "persona", [])
    state = chat.ChatState(trace={})
    assert agent.client_tools_for_turn(ctx, state) is agent.CLAUDE_CLIENT_TOOLS


# ────────────────────────── 参数校验 ──────────────────────────


@pytest.mark.parametrize("arguments,marker", [
    ({**DRAFT_ARGS, "title": ""}, "标题"),
    ({**DRAFT_ARGS, "title": "书" * 61}, "标题"),
    ({**DRAFT_ARGS, "seed_idea": ""}, "故事思路"),
    ({**DRAFT_ARGS, "seed_idea": "想" * 2001}, "故事思路"),
    ({**DRAFT_ARGS, "min_chapters": 0}, "章数与每章字数"),
    ({**DRAFT_ARGS, "min_chapters": True}, "章数与每章字数"),
    ({**DRAFT_ARGS, "max_chapters": "60"}, "章数与每章字数"),
    ({**DRAFT_ARGS, "chapter_words": 999}, "章数与每章字数"),
    ({**DRAFT_ARGS, "chapter_words": 4001}, "章数与每章字数"),
    ({**DRAFT_ARGS, "min_chapters": 61, "max_chapters": 60}, "最少章数"),
])
def test_invalid_arguments_are_tool_results_and_create_nothing(
    harness, create_enabled, draft_db, arguments, marker,
):
    _require_drafts()
    h = harness
    _configure_turn(h, draft_db.owner)
    events = _run_draft_turn(h, arguments)
    feedback = h.requests[1][0][-1]["content"][0]
    assert feedback["type"] == "tool_result"
    assert marker in feedback["content"]
    assert _draft_rows() == []
    assert _cards(events) == []
    assert h.state.trace["agent_tool_errors"] == 1
    assert h.state.novel_draft_id is None
    assert events[-1] == {"done": True}


def test_init_db_creates_draft_table_without_switch(tmp_path, monkeypatch):
    """T1.1 / R1：novel_drafts 不随 FIONA_NOVEL_CHAT_CREATE 变化。"""
    import database

    monkeypatch.delenv("FIONA_NOVEL_CHAT_CREATE", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "unconditional.db"))
    asyncio.run(database.init_db())
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='novel_drafts'"
        ).fetchone() is not None
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_novel_drafts_owner'"
        ).fetchone() is not None


def test_validate_draft_args_defaults_and_stripping():
    path = ROOT / "backend/novel/drafts.py"
    assert path.is_file(), "novel/drafts.py 尚未实现"
    from novel import drafts

    clean, error = asyncio.run(drafts.validate_draft_args({"title": "  归墟  ", "seed_idea": "  思路  "}))
    assert error is None
    assert clean == {
        "title": "归墟",
        "seed_idea": "思路",
        "target": {"min_chapters": 50, "max_chapters": 70, "chapter_words": 2000},
    }


# ────────────────────────── 成功路径与刷新重建 ──────────────────────────


def test_success_path_card_state_balance_and_persistence(harness, create_enabled, draft_db, monkeypatch):
    _require_drafts()
    import novel.runner as runner

    h = harness
    _configure_turn(h, draft_db.owner)
    monkeypatch.setattr(h.chat, "_save_response", _REAL_SAVE_RESPONSE)
    before_balance = _balance()
    before_tasks = dict(runner.TASKS)

    events = _run_draft_turn(h, DRAFT_ARGS)
    rows = _draft_rows()
    assert len(rows) == 1
    draft = rows[0]
    assert draft["owner_username"] == USER
    assert draft["conversation_id"] == draft_db.owner
    assert draft["title"] == "归墟来信"
    assert json.loads(draft["target_json"]) == {
        "min_chapters": 40, "max_chapters": 60, "chapter_words": 1800,
    }
    assert draft["novel_id"] is None

    cards = _cards(events)
    assert [card["subtype"] for card in cards] == ["novel_draft"]
    card = cards[0]
    assert card == {
        "type": "card",
        "subtype": "novel_draft",
        "source": "书斋",
        "points": ["草稿《归墟来信》已送到书斋", "到书斋确认智能体与预算后开始写作"],
        "draft_id": draft["id"],
        "url": f"/novels/new?draft={draft['id']}",
        "error": False,
    }
    assert h.state.novel_draft_id == draft["id"]
    assert h.state.full_response.count("［卡片：") == 1
    assert h.state.trace["agent_tools"] == ["draft_novel"]
    assert h.state.trace.get("agent_tool_errors", 0) == 0

    assistant = _assistant_rows(draft_db.owner)[-1]
    assert assistant["novel_draft_id"] == draft["id"]
    assert "［卡片：" in assistant["content"]

    # 不建书、不扣草莓：novels 行数为 0，余额不变，本轮没有 runner 任务。
    assert _count("novels") == 0
    assert _count("novel_steps") == 0
    assert _balance() == before_balance
    assert dict(runner.TASKS) == before_tasks


def test_one_draft_per_turn_then_text_reply(harness, create_enabled, draft_db):
    _require_drafts()
    h = harness
    _configure_turn(h, draft_db.owner)
    events = _run_draft_turn(h, DRAFT_ARGS, {**DRAFT_ARGS, "title": "第二本"})
    rows = _draft_rows()
    check_one_draft(rows)
    assert rows[0]["title"] == "归墟来信"
    assert h.state.novel_draft_id == rows[0]["id"]
    assert h.state.trace["agent_tool_errors"] == 0
    second = h.requests[2][0][-1]["content"][0]
    assert second["type"] == "tool_result"
    assert second["content"] == "本轮已写过一份草稿，请直接回答主人"
    assert len(_cards(events)) == 1


def test_fifty_open_drafts_are_rejected_without_creating_more(harness, create_enabled, draft_db):
    _require_drafts()
    from novel import drafts

    async def seed():
        for index in range(50):
            await drafts.create_draft(USER, draft_db.owner, f"旧草稿{index}", "旧思路", {})

    asyncio.run(seed())
    h = harness
    _configure_turn(h, draft_db.owner)
    events = _run_draft_turn(h, DRAFT_ARGS)
    assert len(_draft_rows()) == 50
    feedback = h.requests[1][0][-1]["content"][0]
    assert feedback["type"] == "tool_result"
    assert feedback["content"] == "未使用的草稿太多，请先到书斋建书或删除"
    assert _cards(events) == []
    assert h.state.novel_draft_id is None
    assert h.state.trace["agent_tool_errors"] == 0


# ────────────────────────── 消息归属与删除清理 ──────────────────────────


def test_save_message_checks_draft_owner_and_conversation(draft_db):
    _require_drafts()
    from novel import drafts

    async def create(user, conversation, title):
        return await drafts.create_draft(user, conversation, title, "思路", {})

    own = asyncio.run(create(USER, draft_db.owner, "本人"))
    own_other_conversation = asyncio.run(create(USER, draft_db.owner_second, "本人另一会话"))
    foreign = asyncio.run(create(OTHER, draft_db.other, "别人"))

    async def save():
        assert await draft_db.db.save_message(USER, "assistant", "own", conversation_id=draft_db.owner, novel_draft_id=own["id"])
        assert await draft_db.db.save_message(USER, "assistant", "own-other", conversation_id=draft_db.owner, novel_draft_id=own_other_conversation["id"])
        assert await draft_db.db.save_message(USER, "assistant", "foreign", conversation_id=draft_db.owner, novel_draft_id=foreign["id"])

    asyncio.run(save())
    with sqlite3.connect(draft_db.db.DB_PATH) as db:
        stored = dict(db.execute("SELECT content, novel_draft_id FROM messages").fetchall())
    assert stored["own"] == own["id"]
    check_foreign_draft_stored_null(stored["own-other"])
    check_foreign_draft_stored_null(stored["foreign"])


def test_get_draft_route_is_owner_only(workshop):
    _require_drafts()
    import database

    client = workshop
    draft = _seed_draft("novel_author", "可读草稿")
    owner = client.get(f"/novels/drafts/{draft['id']}", headers={"X-Dev-User": "novel_author"})
    assert owner.status_code == 200
    assert owner.json() == {
        "id": draft["id"], "title": "可读草稿", "seed_idea": "聊天里定下的故事思路",
        "target": {"min_chapters": 12, "max_chapters": 20, "chapter_words": 1500},
        "novel_id": None, "created_at": draft["created_at"],
    }
    foreign = client.get(f"/novels/drafts/{draft['id']}", headers={"X-Dev-User": "other"})
    assert foreign.status_code == 404
    missing = client.get("/novels/drafts/00000000-0000-0000-0000-000000000000", headers={"X-Dev-User": "novel_author"})
    assert missing.status_code == 404


@pytest.mark.parametrize("operation", ["account", "history"])
def test_account_and_history_cleanup_remove_only_own_drafts(draft_db, operation):
    _require_drafts()
    from novel import drafts

    own = asyncio.run(drafts.create_draft(USER, draft_db.owner, "本人", "思路", {}))
    other = asyncio.run(drafts.create_draft(OTHER, draft_db.other, "别人", "思路", {}))

    async def cleanup():
        if operation == "account":
            await draft_db.db.delete_account_data(USER)
        else:
            await draft_db.db.save_message(USER, "user", "历史", conversation_id=draft_db.owner)
            await draft_db.db.clear_message_history(USER)

    asyncio.run(cleanup())
    assert asyncio.run(drafts.get_draft(USER, own["id"])) is None
    assert asyncio.run(drafts.get_draft(OTHER, other["id"])) is not None


def test_delete_conversation_removes_only_that_conversations_drafts(draft_db):
    _require_drafts()
    from novel import drafts

    first = asyncio.run(drafts.create_draft(USER, draft_db.owner, "待删", "思路", {}))
    second = asyncio.run(drafts.create_draft(USER, draft_db.owner_second, "保留", "思路", {}))
    other = asyncio.run(drafts.create_draft(OTHER, draft_db.other, "别人", "思路", {}))

    asyncio.run(draft_db.agent_store.delete_conversation(USER, draft_db.owner))
    assert asyncio.run(drafts.get_draft(USER, first["id"])) is None
    assert asyncio.run(drafts.get_draft(USER, second["id"])) is not None
    assert asyncio.run(drafts.get_draft(OTHER, other["id"])) is not None


# ────────────────────────── HTTP 建书消费草稿 ──────────────────────────


HEADERS = {"X-Dev-User": "novel_author"}


def _payload(chapters=3):
    agents = {
        "editor": "dashscope:qwen3.8-max",
        "writer": "deepseek:deepseek-flash",
        "archivist": "dashscope:qwen3.8-max",
        "reviewer": "dashscope:qwen3.8-max",
        "twist_designer": "ark:doubao-seed-2-1-pro-260915",
    }
    return {
        "seed_idea": "一本关于失落档案的悬疑小说",
        "agents": agents,
        "panel_mode": "critique",
        "automation": "per_batch",
        "batch_size": 5,
        "target": {"min_chapters": chapters, "max_chapters": chapters, "chapter_words": 1000},
        "budget_strawberries": 100000,
    }


@pytest.fixture
def workshop(client, monkeypatch):
    import novel.runner as runner
    from novel.fake_llm import FakeLLM
    from novel.llm_router import LLMRouter
    from rate_limit import limiter

    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", "novel_author,other")
    monkeypatch.setattr(limiter, "enabled", False)
    fake = FakeLLM()
    monkeypatch.setattr(
        runner, "router_factory",
        lambda store, username, novel_id, run_token: LLMRouter(store, dry_run=True, fake=fake),
    )
    return client


def _wait_state(client, book, expected):
    import time

    data = None
    for _ in range(800):
        response = client.get(f"/novels/{book}", headers=HEADERS)
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] == expected:
            return data
        if data["status"] in ("failed", "paused") and expected not in ("failed", "paused"):
            pytest.fail(str(data))
        time.sleep(0.01)
    pytest.fail(f"timeout waiting for {expected}: {data}")


def _seed_draft(username, title="聊天草稿", target=None):
    import agent_store
    import database
    from novel import drafts

    target = target or {"min_chapters": 12, "max_chapters": 20, "chapter_words": 1500}

    async def seed():
        await database.get_or_create_user(username)
        conversation = (await agent_store.create_conversation(username))["id"]
        return await drafts.create_draft(username, conversation, title, "聊天里定下的故事思路", target)

    return asyncio.run(seed())


def test_create_with_draft_consumes_and_delete_resets(workshop):
    _require_drafts()
    from novel import drafts

    client = workshop
    draft = _seed_draft("novel_author")
    response = client.post("/novels", json={**_payload(), "draft_id": draft["id"]}, headers=HEADERS)
    assert response.status_code == 201, response.text
    book = response.json()["id"]
    assert "draft_id" not in response.json()["config"]
    _wait_state(client, book, "awaiting_setup")
    after = asyncio.run(drafts.get_draft("novel_author", draft["id"]))
    assert after["novel_id"] == book

    reused = client.post("/novels", json={**_payload(), "draft_id": draft["id"]}, headers=HEADERS)
    assert reused.status_code == 422
    assert "草稿不存在或已使用" in reused.json()["detail"]
    assert _count("novels") == 1

    foreign = _seed_draft("other")
    wrong = client.post("/novels", json={**_payload(), "draft_id": foreign["id"]}, headers=HEADERS)
    assert wrong.status_code == 422
    assert _count("novels") == 1

    deleted = client.delete(f"/novels/{book}", headers=HEADERS)
    assert deleted.status_code == 200
    restored = asyncio.run(drafts.get_draft("novel_author", draft["id"]))
    assert restored["novel_id"] is None
    assert _count("novels") == 0


def test_create_without_draft_keeps_head_config_shape(workshop):
    _require_drafts()
    from novel.service import ADVISORS, CreateNovel

    client = workshop
    body = _payload()
    response = client.post("/novels", json=body, headers=HEADERS)
    assert response.status_code == 201, response.text
    data = response.json()
    book = data["id"]
    assert "draft_id" not in data["config"]
    assert _count("novel_drafts") == 0

    expected = CreateNovel(**body).model_dump(exclude={"draft_id"})
    expected.update(experiment="P1", critique_rounds=1, enable_arc_summaries=True,
                    enable_context_compression=True)
    if expected.get("structure") == "v2":
        expected["volume_gate"] = False
    else:
        expected.pop("structure", None)
    if not set(expected["agents"]) & set(ADVISORS):
        expected["panel_mode"] = "solo"
    assert data["config"] == expected
    _wait_state(client, book, "awaiting_setup")
    assert client.delete(f"/novels/{book}", headers=HEADERS).status_code == 200


# ────────────────────────── 坏实现自检 ──────────────────────────


def test_bad_switch_copy_is_caught(enabled, monkeypatch):
    import services.chat_service as chat
    import services.claude_agent as agent

    source = (ROOT / "backend/services/claude_agent.py").read_text(encoding="utf-8")
    marker = "if novel_create_enabled(ctx.user):"
    assert marker in source, "开关判断的实现标记消失，无法做坏副本自检"
    bad = _load_module("bad_agent_switch", source.replace(marker, "if True:", 1))
    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "0")
    ctx = chat.ChatContext(USER, "建书", False, None, "建书", [], 0, "persona", [])
    state = chat.ChatState(trace={})
    constant_names = {tool["name"] for tool in agent.CLAUDE_CLIENT_TOOLS}
    base_names = {"list_novels", "read_novel"}

    def assert_off(tools, constant):
        assert {tool["name"] for tool in tools} - constant_names == base_names
        assert tools is not constant

    assert_off(agent.client_tools_for_turn(ctx, state), agent.CLAUDE_CLIENT_TOOLS)
    with pytest.raises(AssertionError):
        assert_off(bad.client_tools_for_turn(ctx, state), bad.CLAUDE_CLIENT_TOOLS)


def _run_two_drafts(module, h, conversation):
    """用给定模块跑一轮两次 draft_novel；真实实现与坏副本共用。"""
    import services.chat_service as chat

    h.ctx.conversation_id = conversation
    h.state = chat.ChatState(trace={})
    h.streams.clear()
    for index, title in enumerate(("第一份", "第二份")):
        h.streams.append(FakeStream(message("tool_use", content=[
            call("draft_novel", {**DRAFT_ARGS, "title": title}, identity=f"run-{index}"),
        ])))
    h.streams.append(FakeStream(message(text="写完了。"), "写完了。"))

    async def collect():
        return [json.loads(event[6:]) if event.startswith("data: ") else event
                async for event in module.stream_claude_agent(h.ctx, h.state)]

    asyncio.run(collect())


def _clear_drafts(path):
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM novel_drafts")
        db.commit()


def test_bad_one_per_turn_copy_is_caught(harness, create_enabled, draft_db):
    source = (ROOT / "backend/services/claude_agent.py").read_text(encoding="utf-8")
    marker = "if draft_written:"
    assert marker in source, "每轮一份计数器的实现标记消失，无法做坏副本自检"
    bad = _load_module("bad_agent_twice", source.replace(marker, "if False:", 1))
    h = harness
    bad.open_agent_stream = h.agent.open_agent_stream

    # 正样本：真实实现必须只留一份。
    _run_two_drafts(h.agent, h, draft_db.owner)
    check_one_draft(_draft_rows())
    _clear_drafts(draft_db.db.DB_PATH)

    # 坏副本：绕过每轮一份限制后，同一检查函数必须变红。
    _run_two_drafts(bad, h, draft_db.owner)
    with pytest.raises(AssertionError):
        check_one_draft(_draft_rows())


def test_bad_save_message_copy_is_caught(draft_db):
    _require_drafts()
    from novel import drafts

    source = (ROOT / "backend/database.py").read_text(encoding="utf-8")
    start_marker = "        # 书斋草稿归属同样只做附加校验"
    end_marker = "        await db.execute(\n            \"\"\"INSERT INTO messages"
    assert start_marker in source and end_marker in source, "save_message 归属校验标记消失，无法做坏副本自检"
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    bad_source = source[:start] + "        stored_novel_draft_id = novel_draft_id\n" + source[end:]
    bad = _load_module("bad_database_ownership", bad_source)
    bad.DB_PATH = draft_db.db.DB_PATH

    foreign = asyncio.run(drafts.create_draft(OTHER, draft_db.other, "别人", "思路", {}))

    # 正样本：真实 save_message 必须把别人的草稿存成 NULL。
    asyncio.run(draft_db.db.save_message(
        USER, "assistant", "real-copy", conversation_id=draft_db.owner,
        novel_draft_id=foreign["id"],
    ))
    with sqlite3.connect(draft_db.db.DB_PATH) as db:
        real_row = db.execute("SELECT novel_draft_id FROM messages WHERE content='real-copy'").fetchone()
    assert real_row is not None
    check_foreign_draft_stored_null(real_row[0])

    # 坏副本：同一检查函数必须变红。
    asyncio.run(bad.save_message(
        USER, "assistant", "bad-copy", conversation_id=draft_db.owner,
        novel_draft_id=foreign["id"],
    ))
    with sqlite3.connect(draft_db.db.DB_PATH) as db:
        bad_row = db.execute("SELECT novel_draft_id FROM messages WHERE content='bad-copy'").fetchone()
    assert bad_row is not None
    with pytest.raises(AssertionError):
        check_foreign_draft_stored_null(bad_row[0])
