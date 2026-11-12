"""聊天修改意见卡：卡片校验、Claude 工具、书斋接口、清理与坏副本自检。

全部用例只使用临时 SQLite、模拟传输与源码副本，不访问网络，也不依赖
git 历史。规格：docs/tasks/2026-11-12-novel-feedback/02-spec.md §4.5。
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

# harness 夹具会替换 _save_response；需要验证落库时恢复生产实现。
from services.chat_service import _save_response as _REAL_SAVE_RESPONSE


ROOT = Path(__file__).resolve().parents[2]
USER = "agent-user"
OTHER = "other"
NOVEL_USER = "novel_author"
NOVEL_OTHER = "other"
HTTP_HEADERS = {"X-Dev-User": NOVEL_USER}

CONSTANT_TOOL_NAMES = [
    "get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image",
]
NOVEL_TOOL_NAMES = ["list_novels", "read_novel"]
PROGRESS_STATUSES = ("awaiting_plan_approval", "planning", "writing")

WRITTEN_SENTENCE = (
    "已写章节的问题只给作者看，书斋不会自动修改，要作者自己去书斋改稿："
    "改最新写好的一章会重新归档（可能扣草莓）；改较早的章会让后面已写的章永久待复核、"
    "不能做成片，故事圣经与章节摘要也不会重算。"
)
FINAL_SENTENCE = "请如实告诉作者，不要说已经交给编辑部或已经改好。"
ONCE_SENTENCE = "留言只用一次，不会长期生效，交出后不能撤回。"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """禁止真实 TCP / DNS，只放行回环地址。"""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def blocked(*args, **kwargs):
        raise AssertionError("修改意见卡测试禁止真实网络连接和 DNS")

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
    monkeypatch.delenv("FIONA_NOVEL_CHAT_FEEDBACK", raising=False)


@pytest.fixture
def create_enabled(enabled, monkeypatch):
    monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", "1")


@pytest.fixture
def feedback_enabled(enabled, monkeypatch):
    monkeypatch.setenv("FIONA_NOVEL_CHAT_FEEDBACK", "1")


@pytest.fixture
def book_db(tmp_path, monkeypatch):
    """临时库 + 本人两个会话 + 另一个账号的会话。"""
    import agent_store
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "novel-feedback.db"))
    asyncio.run(database.init_db())

    async def setup():
        await database.get_or_create_user(USER)
        await database.get_or_create_user(OTHER)
        owner = (await agent_store.create_conversation(USER))["id"]
        owner_second = (await agent_store.create_conversation(USER))["id"]
        other = (await agent_store.create_conversation(OTHER))["id"]
        return owner, owner_second, other

    owner, owner_second, other = asyncio.run(setup())
    return NS(path=database.DB_PATH, owner=owner, owner_second=owner_second, other=other,
              db=database, agent_store=agent_store)


def _require_feedback():
    """HEAD 对照时先以 AssertionError 失败，而不是 ImportError / sqlite 错误。"""
    assert (ROOT / "backend/novel/feedback.py").is_file(), "novel/feedback.py 尚未实现"


def _read(relative):
    return (ROOT / "backend" / relative).read_text(encoding="utf-8")


def _load_module(name, source):
    module = types.ModuleType(name)
    module.__file__ = f"<{name}>"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _load_bad_service(source):
    module = types.ModuleType("novel._bad_service")
    module.__package__ = "novel"
    module.__file__ = "<novel._bad_service>"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _connect():
    import database

    return sqlite3.connect(database.DB_PATH)


def _rows(query, args=()):
    with _connect() as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(query, args)]


def _execute(query, args=()):
    with _connect() as db:
        db.execute(query, args)


def _insert_book(book_id, *, username=USER, title="归墟来信", status="awaiting_plan",
                 automation="per_chapter", editor="dashscope:qwen3.8-max",
                 max_chapters=10, chapters_done=0, chapters=(), created_at=None):
    """照 test_studio_sources_readonly_integration 的 INSERT 写法造真实行。"""
    config = {
        "agents": {
            "editor": editor,
            "writer": "deepseek:deepseek-flash",
            "archivist": "dashscope:qwen3.8-max",
        },
        "automation": automation,
        "target": {"min_chapters": 1, "max_chapters": max_chapters, "chapter_words": 1000},
    }
    with _connect() as db:
        db.execute(
            """INSERT INTO novels(id,username,title,seed_idea,status,config_json,
               budget_strawberries,chapters_done,created_at,updated_at)
               VALUES(?,?,?,'seed',?,?,100000,?,COALESCE(?,CURRENT_TIMESTAMP),
               COALESCE(?,CURRENT_TIMESTAMP))""",
            (book_id, username, title, status, json.dumps(config, ensure_ascii=False),
             chapters_done, created_at, created_at),
        )
        for item in chapters:
            db.execute(
                """INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,
                   flags_json,meeting_json,review_json,archive_json)
                   VALUES(?,?,?,?,?,'正文', '[]', ?, '[]', '{}')""",
                (book_id, username, item["chapter"], item["status"], item.get("title", f"第{item['chapter']}章"),
                 json.dumps(item["meeting"], ensure_ascii=False) if item.get("meeting") is not None else None),
            )
    return book_id


def _insert_feedback(*, conversation_id, username=USER, novel_id="book-1",
                     book_title="归墟来信", next_chapters="", current_plan="",
                     plan_chapter=None, written=None, note_id=None,
                     note_sent_at=None, redo_started_at=None, feedback_id=None):
    import uuid

    feedback_id = feedback_id or str(uuid.uuid4())
    with _connect() as db:
        db.execute(
            """INSERT INTO novel_feedback(id,owner_username,conversation_id,novel_id,
               book_title,next_chapters,current_plan,plan_chapter,written_json,note_id,
               note_sent_at,redo_started_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (feedback_id, username, conversation_id, novel_id, book_title, next_chapters,
             current_plan, plan_chapter, json.dumps(written or [], ensure_ascii=False),
             note_id, note_sent_at, redo_started_at),
        )
    return feedback_id


def _insert_note(novel_id, text, *, username=USER, status="pending",
                 delivered_chapter=None, response=None):
    with _connect() as db:
        cursor = db.execute(
            """INSERT INTO novel_notes(novel_id,username,text,status,delivered_chapter,response_json)
               VALUES(?,?,?,?,?,?)""",
            (novel_id, username, text, status, delivered_chapter,
             json.dumps(response, ensure_ascii=False) if response is not None else None),
        )
        return cursor.lastrowid


def _feedback_rows():
    return _rows("SELECT * FROM novel_feedback ORDER BY created_at, id")


def _feedback_count(novel_id=None):
    if novel_id is None:
        return _rows("SELECT COUNT(*) AS n FROM novel_feedback")[0]["n"]
    return _rows("SELECT COUNT(*) AS n FROM novel_feedback WHERE novel_id=?", (novel_id,))[0]["n"]


def _note_rows(novel_id):
    return _rows("SELECT * FROM novel_notes WHERE novel_id=? ORDER BY id", (novel_id,))


def _chapter_row(book_id, chapter):
    found = _rows("SELECT * FROM novel_chapters WHERE novel_id=? AND chapter=?", (book_id, chapter))
    return found[0] if found else None


def _books_snapshot(book_id):
    tables = ("novels", "novel_bible_versions", "novel_chapters", "novel_steps", "novel_notes")
    result = {}
    with _connect() as db:
        for table in tables:
            key = "id" if table == "novels" else "novel_id"
            result[table] = json.dumps(
                db.execute(f'SELECT * FROM "{table}" WHERE {key}=? ORDER BY rowid', (book_id,)).fetchall(),
                ensure_ascii=False,
            )
    return result


def _cards(events):
    return [event["card"] for event in events if isinstance(event, dict) and "card" in event]


def _run_feedback_turn(h, conversation, *arguments, final="收到了。"):
    h.ctx.conversation_id = conversation
    for index, args in enumerate(arguments):
        h.streams.append(FakeStream(message("tool_use", content=[
            call("draft_novel_feedback", args, identity=f"feedback-tool-{index}"),
        ])))
    h.streams.append(FakeStream(message(text=final), final))
    return run(h)


# ────────────────────────── 1. 开关矩阵 ──────────────────────────


SWITCH_GROUPS = [
    (None, None, {"list_novels", "read_novel"}),
    ("dev", None, {"list_novels", "read_novel"}),
    ("jwt", None, {"list_novels", "read_novel", "start_film"}),
    ("jwt", "possible", set()),
    ("jwt", "high", set()),
]


def _expected_tool_names(method, crisis, create, feedback):
    names = list(CONSTANT_TOOL_NAMES)
    if crisis is None:
        names.extend(NOVEL_TOOL_NAMES)
        if method == "jwt":
            names.append("start_film")
        if create == "1":
            names.append("draft_novel")
        if feedback == "1":
            names.append("draft_novel_feedback")
    return names


def _turn_context(method, crisis):
    import services.chat_service as chat

    ctx = chat.ChatContext(USER, "把意见交给书斋", False, None, "把意见交给书斋", [], 0,
                           "persona", [], auth_method=method)
    state = chat.ChatState(trace={}, crisis_level=crisis)
    return ctx, state


@pytest.mark.parametrize("method,crisis,base", SWITCH_GROUPS)
@pytest.mark.parametrize("create", [None, "1"])
@pytest.mark.parametrize("feedback", [None, "0", "true"])
def test_switch_matrix_off_values_match_head(enabled, monkeypatch, method, crisis, base, create, feedback):
    """回归类：FEEDBACK 未设 / 0 / true 时工具集合与 HEAD 一致。"""
    import services.claude_agent as agent

    if create is None:
        monkeypatch.delenv("FIONA_NOVEL_CHAT_CREATE", raising=False)
    else:
        monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", create)
    if feedback is None:
        monkeypatch.delenv("FIONA_NOVEL_CHAT_FEEDBACK", raising=False)
    else:
        monkeypatch.setenv("FIONA_NOVEL_CHAT_FEEDBACK", feedback)
    ctx, state = _turn_context(method, crisis)
    tools = agent.client_tools_for_turn(ctx, state)
    names = [tool["name"] for tool in tools]
    assert names == _expected_tool_names(method, crisis, create, feedback)
    assert base.issubset(names)
    if crisis is None:
        assert tools is not agent.CLAUDE_CLIENT_TOOLS
    else:
        assert tools is agent.CLAUDE_CLIENT_TOOLS


@pytest.mark.parametrize("method,crisis,base", SWITCH_GROUPS)
@pytest.mark.parametrize("create", [None, "1"])
def test_switch_matrix_feedback_on_appends_tool(feedback_enabled, monkeypatch, method, crisis, base, create):
    _require_feedback()
    import services.claude_agent as agent

    if create is None:
        monkeypatch.delenv("FIONA_NOVEL_CHAT_CREATE", raising=False)
    else:
        monkeypatch.setenv("FIONA_NOVEL_CHAT_CREATE", create)
    ctx, state = _turn_context(method, crisis)
    tools = agent.client_tools_for_turn(ctx, state)
    names = [tool["name"] for tool in tools]
    assert names == _expected_tool_names(method, crisis, create, "1")
    assert base.issubset(names)
    if crisis is None:
        assert tools is not agent.CLAUDE_CLIENT_TOOLS
    else:
        assert tools is agent.CLAUDE_CLIENT_TOOLS


@pytest.mark.parametrize("novel_chat,user", [("0", USER), ("1", "stranger")])
def test_feedback_switch_still_requires_novel_chat_and_whitelist(enabled, monkeypatch, novel_chat, user):
    _require_feedback()
    import services.chat_service as chat
    import services.claude_agent as agent

    monkeypatch.setenv("FIONA_NOVEL_CHAT", novel_chat)
    monkeypatch.setenv("FIONA_NOVEL_CHAT_FEEDBACK", "1")
    ctx = chat.ChatContext(user, "把意见交给书斋", False, None, "把意见交给书斋", [], 0, "persona", [])
    state = chat.ChatState(trace={})
    assert agent.client_tools_for_turn(ctx, state) is agent.CLAUDE_CLIENT_TOOLS


# ────────────────────────── 2. 参数校验 ──────────────────────────


def _validation_book(**overrides):
    book = {
        "id": "book-1",
        "title": "归墟来信",
        "status": "awaiting_plan",
        "chapters_done": 2,
        "config": {"automation": "per_chapter", "target": {"max_chapters": 10}},
        "max_chapters": 10,
        "chapters": [
            {"chapter": 1, "title": "第一章", "status": "done"},
            {"chapter": 2, "title": "第二章", "status": "stale"},
            {"chapter": 3, "title": "第三章", "status": "awaiting_plan_approval"},
        ],
    }
    book.update(overrides)
    return book


def _long_text(length):
    return "字" * length


@pytest.mark.parametrize("args,book_updates,expected", [
    ({"next_chapters": 5}, {},
     "next_chapters 要是文字"),
    ({"next_chapters": "  " + _long_text(501) + "  "}, {},
     "交给编辑部的要求现在 501 字，最多 500 字，请精简后再写"),
    ({"current_plan": ["不是文字"]}, {},
     "current_plan 要是文字"),
    ({"current_plan": _long_text(501)}, {},
     "重新定稿的要求现在 501 字，最多 500 字，请精简后再写"),
    ({"written_chapters": "不是列表"}, {},
     "written_chapters 要是列表"),
    ({"written_chapters": [{"chapter": index, "issue": "问题"} for index in range(1, 12)]}, {},
     "已写章节现在 11 条，最多 10 条"),
    ({"written_chapters": [5]}, {},
     "已写章节的每一项要有 chapter（整数）和 issue（文字）"),
    ({"written_chapters": [{"chapter": True, "issue": "问题"}]}, {},
     "已写章节的每一项要有 chapter（整数）和 issue（文字）"),
    ({"written_chapters": [{"chapter": 3, "issue": "问题"}]}, {},
     "第 3 章还没写好，不能放进已写章节"),
    ({"written_chapters": [{"chapter": 1, "issue": "   "}]}, {},
     "第 1 章的问题现在 0 字，要在 1–200 字之间"),
    ({"written_chapters": [{"chapter": 1, "issue": _long_text(201)}]}, {},
     "第 1 章的问题现在 201 字，要在 1–200 字之间"),
    ({"next_chapters": "   ", "current_plan": "  ", "written_chapters": []}, {},
     "修改意见卡至少要写一项：以后章节的要求、这一章细纲的要求或已写章节的问题"),
    ({"next_chapters": "下一章要收敛线索"}, {"status": "completed"},
     "《归墟来信》已经完结，编辑部不会再读留言；已写章节的问题可以放进 written_chapters"),
    ({"next_chapters": "下一章要收敛线索"}, {"status": "failed"},
     "《归墟来信》处于失败状态，编辑部不会再读留言；已写章节的问题可以放进 written_chapters"),
    ({"current_plan": "第3章要加强因果"}, {"status": "running"},
     "《归墟来信》现在没有等作者确认的细纲，current_plan 只能在等确认细纲时填写"),
    ({"current_plan": "第3章要加强因果"}, {"chapters": [
        {"chapter": 1, "title": "第一章", "status": "done"},
        {"chapter": 2, "title": "第二章", "status": "done"},
    ]},
     "《归墟来信》现在没有等作者确认的细纲，current_plan 只能在等确认细纲时填写"),
    ({"current_plan": "第3章要加强因果"}, {"config": {"automation": "per_batch"}},
     "《归墟来信》现在不是逐章确认，卡片上不能重新定稿这一章细纲；这一项请在回复里请作者到书斋处理"),
    ({"current_plan": "第3章要加强因果"}, {"config": {"target": {"max_chapters": 10}}},
     "《归墟来信》现在不是逐章确认，卡片上不能重新定稿这一章细纲；这一项请在回复里请作者到书斋处理"),
    ({"next_chapters": _long_text(501)}, {"status": "completed"},
     "交给编辑部的要求现在 501 字，最多 500 字，请精简后再写"),
], ids=[
    "next-not-text", "next-too-long", "current-not-text", "current-too-long",
    "written-not-list", "written-too-many", "written-not-dict", "written-bool-chapter",
    "chapter-not-done", "empty-issue", "long-issue", "all-empty", "completed-next",
    "failed-next", "current-not-awaiting", "current-no-pending-chapter",
    "current-per-batch", "current-automation-default", "format-before-state",
])
def test_validate_feedback_args_errors(args, book_updates, expected):
    _require_feedback()
    from novel.feedback import validate_feedback_args

    clean, error = validate_feedback_args(args, _validation_book(**book_updates))
    assert clean is None
    assert error == expected


def test_validate_feedback_args_collects_all_errors_in_order():
    _require_feedback()
    from novel.feedback import validate_feedback_args

    long_next = _long_text(501)
    long_current = "另" + _long_text(500)
    clean, error = validate_feedback_args(
        {"next_chapters": long_next, "current_plan": long_current}, _validation_book(),
    )
    assert clean is None
    assert error == (
        "交给编辑部的要求现在 501 字，最多 500 字，请精简后再写；"
        "重新定稿的要求现在 501 字，最多 500 字，请精简后再写"
    )

    # 同一句形状错误只出现一次。
    clean, error = validate_feedback_args(
        {"written_chapters": [{"chapter": "1", "issue": "问题"}, {"chapter": 1}]},
        _validation_book(),
    )
    assert clean is None
    assert error == "已写章节的每一项要有 chapter（整数）和 issue（文字）"

    # 超过 10 项时不再逐项检查。
    too_many = [{"chapter": 99, "issue": "问题"} for _ in range(11)]
    clean, error = validate_feedback_args({"written_chapters": too_many}, _validation_book())
    assert clean is None
    assert error == "已写章节现在 11 条，最多 10 条"
    assert "还没写好" not in error

    # 完结的书同时填 next_chapters 与 current_plan：两句状态错误都报。
    clean, error = validate_feedback_args(
        {"next_chapters": "下一章要收束", "current_plan": "第3章要加强因果"},
        _validation_book(status="completed"),
    )
    assert clean is None
    assert error == (
        "《归墟来信》已经完结，编辑部不会再读留言；已写章节的问题可以放进 written_chapters；"
        "《归墟来信》现在没有等作者确认的细纲，current_plan 只能在等确认细纲时填写"
    )


def test_validate_feedback_args_passes_and_returns_every_field():
    _require_feedback()
    from novel.feedback import validate_feedback_args

    book = _validation_book()
    clean, error = validate_feedback_args({
        "book": "归墟来信",
        "next_chapters": "  下一章让证人保留原件  ",
        "current_plan": "  第 3 章要加强因果  ",
        "written_chapters": [
            {"chapter": 2, "issue": "  第二章的动机不清楚  "},
            {"chapter": 1, "issue": "开头太慢"},
        ],
    }, book)
    assert error is None
    assert clean == {
        "title": "归墟来信",
        "status": "awaiting_plan",
        "automation": "per_chapter",
        "max_chapters": 10,
        "next_chapters": "下一章让证人保留原件",
        "current_plan": "第 3 章要加强因果",
        "awaiting_chapter": 3,
        "plan_chapter": 3,
        "written": [
            {"chapter": 2, "title": "第二章", "issue": "第二章的动机不清楚"},
            {"chapter": 1, "title": "第一章", "issue": "开头太慢"},
        ],
    }


def test_validate_feedback_args_defaults_and_optional_fields():
    _require_feedback()
    from novel.feedback import validate_feedback_args

    clean, error = validate_feedback_args(
        {"written_chapters": [{"chapter": 1, "issue": "问题"}]},
        _validation_book(config={}, max_chapters=None),
    )
    assert error is None
    assert clean["automation"] == "per_batch"
    assert clean["max_chapters"] is None
    assert clean["next_chapters"] == "" and clean["current_plan"] == ""
    assert clean["awaiting_chapter"] == 3 and clean["plan_chapter"] is None

    # 缺省章名按空串返回；非 dict 的 args 按空 dict 处理。
    clean, error = validate_feedback_args(
        {"written_chapters": [{"chapter": 2, "issue": "问题"}]},
        _validation_book(chapters=[{"chapter": 2, "title": None, "status": "done"}]),
    )
    assert error is None
    assert clean["written"] == [{"chapter": 2, "title": "", "issue": "问题"}]
    assert validate_feedback_args(None, _validation_book())[1] == (
        "修改意见卡至少要写一项：以后章节的要求、这一章细纲的要求或已写章节的问题"
    )


UPPER_BOUNDARY_KINDS = ("next", "current", "issue", "written")


def _upper_boundary_check(validate, kind):
    if kind == "next":
        text = _long_text(500)
        clean, error = validate({"next_chapters": " \n" + text + "\t "}, _validation_book())
        assert error is None
        assert clean["next_chapters"] == text
        assert len(clean["next_chapters"]) == 500
    elif kind == "current":
        text = "另" + _long_text(499)
        clean, error = validate({"current_plan": "\t" + text + "  "}, _validation_book())
        assert error is None
        assert clean["current_plan"] == text
        assert len(clean["current_plan"]) == 500
        assert clean["plan_chapter"] == 3
    elif kind == "issue":
        text = "问" + _long_text(199)
        clean, error = validate(
            {"written_chapters": [{"chapter": 1, "issue": "  " + text + "  "}]},
            _validation_book(),
        )
        assert error is None
        assert clean["written"] == [{"chapter": 1, "title": "第一章", "issue": text}]
        assert len(clean["written"][0]["issue"]) == 200
    else:
        chapters = [
            {"chapter": number, "title": f"第{number}章", "status": "done"}
            for number in range(1, 11)
        ]
        items = [{"chapter": number, "issue": f"问题{number}"} for number in range(1, 11)]
        clean, error = validate(
            {"written_chapters": items}, _validation_book(chapters_done=10, chapters=chapters),
        )
        assert error is None
        assert len(clean["written"]) == 10
        assert clean["written"] == [
            {"chapter": number, "title": f"第{number}章", "issue": f"问题{number}"}
            for number in range(1, 11)
        ]


@pytest.mark.parametrize("kind", UPPER_BOUNDARY_KINDS)
def test_validate_feedback_args_accepts_each_upper_boundary(kind):
    """边界正样本：恰 500 / 500 / 200 / 10 都不算超限，且返回清洗后的值。"""
    _require_feedback()
    from novel import feedback

    _upper_boundary_check(feedback.validate_feedback_args, kind)


def _check_chapter_limit(validate, detail):
    clean, error = validate(
        {"book": "归墟来信", "written_chapters": [{"chapter": 3, "issue": "问题"}]},
        detail,
    )
    assert clean is None
    assert error == "第 3 章还没写好，不能放进已写章节"


def test_validate_feedback_args_rejects_done_chapter_past_chapters_done(book_db):
    """第 3 章行是 done，但 chapters_done=2，仍不能当作已写好章节。"""
    _require_feedback()
    from novel import feedback, service

    _insert_book("book-chapter-limit", chapters_done=2, chapters=[
        {"chapter": 1, "status": "done", "title": "第一章"},
        {"chapter": 2, "status": "done", "title": "第二章"},
        {"chapter": 3, "status": "done", "title": "第三章"},
    ])
    detail = asyncio.run(service.detail(USER, "book-chapter-limit"))
    assert detail["chapters_done"] == 2
    assert next(item for item in detail["chapters"] if item["chapter"] == 3)["status"] == "done"
    _check_chapter_limit(feedback.validate_feedback_args, detail)


# ────────────────────────── 3. 成功路径 ──────────────────────────


def _success_expected(*, next_kind=None, k=None, current=False, automation="per_chapter",
                      written=False, title="归墟来信"):
    parts = [f"修改意见卡已放进聊天：《{title}》。卡片上的内容还没有生效，要等作者自己点按钮。"]
    if next_kind == "awaiting_end":
        parts.append("「以后的章节」要作者点「交给编辑部」才会交出；这本书正等作者确认完结，只有作者选择再写几章，编辑部才会看到。")
        parts.append(ONCE_SENTENCE)
    elif next_kind == "last":
        parts.append(f"「以后的章节」要作者点「交给编辑部」才会交出；第 {k} 章会是这本书的最后一章，只有作者选择再写几章，编辑部才会看到。")
        parts.append(ONCE_SENTENCE)
    elif next_kind == "plan_k":
        parts.append(f"「以后的章节」要作者点「交给编辑部」才会交出；这本书正等作者确认第 {k} 章细纲，交出后要到第 {k + 1} 章规划细纲时编辑部才会看到。")
        parts.append(ONCE_SENTENCE)
    elif next_kind == "default":
        parts.append("「以后的章节」要作者点「交给编辑部」才会交出，编辑部只在下一次为新的一章规划细纲时参考一次。")
        parts.append(ONCE_SENTENCE)
    if current:
        parts.append(f"「第 {k} 章细纲」要作者点「带着这些要求重新定稿」并在确认框里确认后才会重新定稿；编辑部看不到现在这一版细纲。")
    if k is not None and not current and automation == "per_chapter":
        parts.append(f"如果有只针对第 {k} 章的要求，请告诉作者可以在书斋里直接改第 {k} 章细纲，或者下一轮再出一张带 current_plan 的卡。")
    if written:
        parts.append(WRITTEN_SENTENCE)
    parts.append(FINAL_SENTENCE)
    return "".join(parts)


SUCCESS_CASES = [
    {
        "name": "all-three-awaiting-plan",
        "book": {"status": "awaiting_plan", "automation": "per_chapter", "chapters_done": 1,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                      "meeting": {"decision": {"ending_status": "continue"}}},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "下一章让证人保留原件",
                 "current_plan": "第 2 章要加强因果",
                 "written_chapters": [{"chapter": 1, "issue": "开头太慢"}]},
        "next_kind": "plan_k", "k": 2, "current": True, "written": True,
        "expected_plan": 2,
    },
    {
        "name": "completed-written-only",
        "book": {"status": "completed", "chapters_done": 2,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "done", "title": "第二章"},
                 ]},
        "args": {"book": "归墟来信",
                 "written_chapters": [{"chapter": 2, "issue": "结尾太急"}]},
        "next_kind": None, "k": None, "current": False, "written": True,
        "expected_plan": None,
    },
    {
        "name": "awaiting-end-next-only",
        "book": {"status": "awaiting_end", "chapters_done": 2,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "done", "title": "第二章"},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "再写几章把线索收完"},
        "next_kind": "awaiting_end", "k": None, "current": False, "written": False,
        "expected_plan": None,
    },
    {
        "name": "awaiting-plan-per-chapter-next-only",
        "book": {"status": "awaiting_plan", "automation": "per_chapter", "chapters_done": 1,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                      "meeting": {"decision": {"ending_status": "continue"}}},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "下一章要收敛线索"},
        "next_kind": "plan_k", "k": 2, "current": False, "written": False,
        "expected_plan": None,
    },
    {
        "name": "awaiting-plan-per-batch-next-only",
        "book": {"status": "awaiting_plan", "automation": "per_batch", "chapters_done": 1,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                      "meeting": {"decision": {"ending_status": "continue"}}},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "下一章要收敛线索"},
        "next_kind": "plan_k", "k": 2, "current": False, "written": False,
        "expected_plan": None, "automation": "per_batch",
    },
    {
        "name": "awaiting-review-next-only",
        "book": {"status": "awaiting_review", "chapters_done": 5,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "done", "title": "第二章"},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "下一批要收敛线索"},
        "next_kind": "default", "k": None, "current": False, "written": False,
        "expected_plan": None,
    },
    {
        "name": "awaiting-plan-last-chapter",
        "book": {"status": "awaiting_plan", "automation": "per_chapter", "chapters_done": 1,
                 "max_chapters": 10,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                      "meeting": {"decision": {"ending_status": "end"}}},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "收尾要留一点余韵"},
        "next_kind": "last", "k": 2, "current": False, "written": False,
        "expected_plan": None,
    },
    {
        "name": "awaiting-plan-last-chapter-at-max",
        "book": {"status": "awaiting_plan", "automation": "per_chapter", "chapters_done": 1,
                 "max_chapters": 2,
                 "chapters": [
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                      "meeting": {"decision": {"ending_status": "continue"}}},
                 ]},
        "args": {"book": "归墟来信", "next_chapters": "最后一章要收束线索"},
        "next_kind": "last", "k": 2, "current": False, "written": False,
        "expected_plan": None,
    },
]


@pytest.mark.parametrize("case", SUCCESS_CASES, ids=[case["name"] for case in SUCCESS_CASES])
def test_success_path_card_state_result_and_persistence(case, harness, feedback_enabled, book_db, monkeypatch):
    _require_feedback()
    import novel.runner as runner

    book_id = "book-" + case["name"]
    book_args = dict(case["book"])
    max_chapters = book_args.pop("max_chapters", 10)
    _insert_book(book_id, max_chapters=max_chapters, **book_args)
    before = _books_snapshot(book_id)
    h = harness
    monkeypatch.setattr(h.chat, "_save_response", _REAL_SAVE_RESPONSE)

    events = _run_feedback_turn(h, book_db.owner, case["args"])
    rows = _feedback_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["owner_username"] == USER
    assert row["conversation_id"] == book_db.owner
    assert row["novel_id"] == book_id
    assert row["book_title"] == "归墟来信"
    assert row["next_chapters"] == case["args"].get("next_chapters", "")
    assert row["current_plan"] == case["args"].get("current_plan", "")
    assert row["plan_chapter"] == case["expected_plan"]
    assert json.loads(row["written_json"]) == [
        {"chapter": item["chapter"],
         "title": next(ch["title"] for ch in case["book"]["chapters"] if ch["chapter"] == item["chapter"]),
         "issue": item["issue"]}
        for item in case["args"].get("written_chapters", [])
    ]
    assert row["note_id"] is None and row["redo_started_at"] is None

    cards = _cards(events)
    assert len(cards) == 1
    card = {
        "type": "card", "subtype": "novel_feedback", "source": "书斋",
        "points": ["修改意见《归墟来信》", "交给编辑部、重新定稿都要作者在卡片上点按钮"],
        "feedback_id": row["id"], "error": False,
    }
    assert cards[0] == card
    assert [event for event in events if isinstance(event, dict) and event.get("card") == card][0]["append"] is True

    expected = _success_expected(
        next_kind=case["next_kind"], k=case["k"], current=case["current"],
        automation=case.get("automation", "per_chapter"), written=case["written"],
    )
    assert h.requests[1][0][-1]["content"][0]["type"] == "tool_result"
    actual = h.requests[1][0][-1]["content"][0]["content"]
    assert actual == expected
    if case["name"] in ("awaiting-plan-last-chapter", "awaiting-plan-last-chapter-at-max"):
        assert f"第 {case['k'] + 1} 章" not in actual
    if case["name"] == "awaiting-plan-last-chapter-at-max":
        prefix = "修改意见卡已放进聊天：《归墟来信》。卡片上的内容还没有生效，要等作者自己点按钮。"
        second = (
            "「以后的章节」要作者点「交给编辑部」才会交出；"
            f"第 {case['k']} 章会是这本书的最后一章，只有作者选择再写几章，编辑部才会看到。"
        )
        assert actual.startswith(prefix)
        assert actual[len(prefix):].startswith(second)

    assert h.state.novel_feedback_id == row["id"]
    assert h.state.full_response.count("［卡片：") == 1
    assert h.state.trace["agent_tools"] == ["draft_novel_feedback"]
    assert h.state.trace.get("agent_tool_errors", 0) == 0
    assert events[-1] == {"done": True}

    assistant = [
        item for item in asyncio.run(
            book_db.agent_store.get_conversation_messages(USER, book_db.owner),
        )["messages"] if item["role"] == "assistant"
    ][-1]
    assert assistant["novel_feedback_id"] == row["id"]
    assert "［卡片：" in assistant["content"]

    assert _books_snapshot(book_id) == before
    assert book_id not in runner.TASKS


# ────────────────────────── 4. 一轮两次调用 ──────────────────────────


def test_two_feedback_calls_in_one_turn_create_only_one(harness, feedback_enabled, book_db):
    _require_feedback()
    book_id = _insert_book(
        "book-twice", status="awaiting_plan", chapters_done=1,
        chapters=[{"chapter": 1, "status": "done", "title": "第一章"},
                  {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                   "meeting": {"decision": {"ending_status": "continue"}}}],
    )
    h = harness
    events = _run_feedback_turn(
        h, book_db.owner,
        {"book": "归墟来信", "next_chapters": "第一条要求"},
        {"book": "归墟来信", "next_chapters": "第二条要求"},
    )
    assert _feedback_count(book_id) == 1
    assert len(_cards(events)) == 1
    second = h.requests[2][0][-1]["content"][0]
    assert second["type"] == "tool_result"
    assert second["content"] == "本轮已写过一张修改意见卡，请直接回答主人"
    assert h.state.trace.get("agent_tool_errors", 0) == 0


# ────────────────────────── 5. 找书失败 ──────────────────────────


@pytest.mark.parametrize("case", ["missing", "ambiguous"])
def test_resolve_failure_is_relayed_and_creates_no_card(case, harness, feedback_enabled, book_db):
    _require_feedback()
    from studio import novel_chat

    if case == "ambiguous":
        _insert_book("book-old", title="星河旧梦", created_at="2026-11-12 00:00:01")
        _insert_book("book-past", title="星河往事", created_at="2026-11-12 00:00:02")
        query = "星河"
    else:
        query = "不存在的书"
    _, expected_error = asyncio.run(novel_chat._resolve(USER, query))
    assert expected_error
    h = harness
    events = _run_feedback_turn(h, book_db.owner, {"book": query, "next_chapters": "不要写章号"})
    assert h.requests[1][0][-1]["content"][0]["content"] == expected_error
    assert _feedback_rows() == []
    assert _cards(events) == []
    assert h.state.trace["agent_tool_errors"] == 1
    assert h.state.novel_feedback_id is None


# ────────────────────────── 6. 消息归属 ──────────────────────────


def test_save_message_checks_feedback_owner_and_conversation(book_db):
    _require_feedback()

    own = _insert_feedback(conversation_id=book_db.owner)
    own_other_conversation = _insert_feedback(conversation_id=book_db.owner_second)
    foreign = _insert_feedback(username=OTHER, conversation_id=book_db.other)
    with _connect() as db:
        db.execute(
            """INSERT INTO novel_drafts(id,owner_username,conversation_id,title,seed_idea,target_json)
               VALUES('draft-1',?,?,'归墟','思路','{}')""",
            (USER, book_db.owner),
        )

    async def save():
        db = book_db.db
        assert await db.save_message(USER, "assistant", "own", conversation_id=book_db.owner,
                                     novel_feedback_id=own)
        assert await db.save_message(USER, "assistant", "own-other", conversation_id=book_db.owner,
                                     novel_feedback_id=own_other_conversation)
        assert await db.save_message(USER, "assistant", "foreign", conversation_id=book_db.owner,
                                     novel_feedback_id=foreign)
        assert await db.save_message(USER, "assistant", "both", conversation_id=book_db.owner,
                                     novel_draft_id="draft-1", novel_feedback_id=own)

    asyncio.run(save())
    with _connect() as db:
        stored = {row[0]: (row[1], row[2]) for row in db.execute(
            "SELECT content, novel_draft_id, novel_feedback_id FROM messages",
        ).fetchall()}
    assert stored["own"] == (None, own)
    assert stored["own-other"] == (None, None)
    assert stored["foreign"] == (None, None)
    assert stored["both"] == ("draft-1", own)


# ────────────────────────── 7. feedback_view ──────────────────────────


def test_feedback_view_shape_and_unsubmitted_card(book_db, monkeypatch):
    _require_feedback()
    from novel import service

    monkeypatch.setenv("DEV_MODE", "1")
    _insert_book("book-view", status="awaiting_plan", chapters_done=0,
                 chapters=[{"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    feedback_id = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-view",
        next_chapters="以后章节的要求", current_plan="这一章的要求", plan_chapter=1,
        written=[{"chapter": 1, "title": "第一章", "issue": "问题"}],
    )
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert set(view) == {
        "id", "novel_id", "book_title", "next_chapters", "current_plan",
        "plan_chapter", "written", "note", "redo_started_at", "book", "created_at",
    }
    assert view["id"] == feedback_id
    assert view["novel_id"] == "book-view"
    assert view["book_title"] == "归墟来信"
    assert view["next_chapters"] == "以后章节的要求"
    assert view["current_plan"] == "这一章的要求"
    assert view["plan_chapter"] == 1
    assert view["written"] == [{"chapter": 1, "title": "第一章", "issue": "问题"}]
    assert view["note"] is None
    assert view["redo_started_at"] is None
    assert view["created_at"]
    assert set(view["book"]) == {
        "status", "chapters_done", "max_chapters", "awaiting_chapter",
        "awaiting_is_final", "pending_notes", "automation", "redo_cost",
        "plan_row_status", "redo_pending",
    }
    assert view["book"] == {
        "status": "awaiting_plan", "chapters_done": 0, "max_chapters": 10,
        "awaiting_chapter": 1, "awaiting_is_final": False, "pending_notes": 0,
        "automation": "per_chapter", "redo_cost": "free",
        "plan_row_status": "awaiting_plan_approval", "redo_pending": False,
    }


def test_feedback_view_requires_owner(book_db):
    _require_feedback()
    from fastapi import HTTPException
    from novel import service

    _insert_book("book-owner", chapters_done=0)
    feedback_id = _insert_feedback(conversation_id=book_db.owner, novel_id="book-owner")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.feedback_view(OTHER, feedback_id))
    assert caught.value.status_code == 404
    assert caught.value.detail == "修改意见不存在"


@pytest.mark.parametrize("adopted", [True, False])
def test_feedback_view_delivered_note_parses_response(book_db, adopted):
    _require_feedback()
    from novel import service

    _insert_book("book-delivered", status="completed", chapters_done=1,
                 chapters=[{"chapter": 1, "status": "done", "title": "第一章"}])
    note_id = _insert_note("book-delivered", "留言", status="delivered", delivered_chapter=1)
    response = {"note_id": f"N{note_id}", "adopted": adopted, "response": "编辑部回应原文"}
    _execute("UPDATE novel_notes SET response_json=? WHERE id=?",
             (json.dumps(response, ensure_ascii=False), note_id))
    feedback_id = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-delivered",
        next_chapters="留言", note_id=note_id, note_sent_at="2026-11-12 10:00:00",
    )
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert set(view["note"]) == {
        "sent_at", "status", "delivered_chapter", "adopted", "response",
        "planned_chapter", "planned_adopted", "planned_response",
    }
    assert view["note"] == {
        "sent_at": "2026-11-12 10:00:00", "status": "delivered",
        "delivered_chapter": 1, "adopted": adopted, "response": "编辑部回应原文",
        "planned_chapter": None, "planned_adopted": None, "planned_response": None,
    }


def test_feedback_view_pending_note_and_deleted_book(book_db):
    _require_feedback()
    from novel import service

    _insert_book("book-pending", chapters_done=0)
    note_id = _insert_note("book-pending", "待下发留言")
    feedback_id = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-pending",
        next_chapters="待下发留言", note_id=note_id, note_sent_at="2026-11-12 10:00:00",
    )
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["note"] == {
        "sent_at": "2026-11-12 10:00:00", "status": "pending",
        "delivered_chapter": None, "adopted": None, "response": None,
        "planned_chapter": None, "planned_adopted": None, "planned_response": None,
    }

    # 书已删：book 与 note.status 都是 None。
    _insert_book("book-gone", chapters_done=0)
    gone_note = _insert_note("book-gone", "已删书的留言")
    gone_card = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-gone",
        next_chapters="留言", note_id=gone_note, note_sent_at="2026-11-12 10:00:00",
    )
    _execute("DELETE FROM novels WHERE id='book-gone'")
    _execute("DELETE FROM novel_notes WHERE novel_id='book-gone'")
    view = asyncio.run(service.feedback_view(USER, gone_card))
    assert view["book"] is None
    assert view["note"]["status"] is None
    assert view["note"]["delivered_chapter"] is None
    assert view["note"]["planned_chapter"] is None

    # written_json 损坏按 [] 处理。
    _execute("UPDATE novel_feedback SET written_json='not-json' WHERE id=?", (gone_card,))
    assert asyncio.run(service.feedback_view(USER, gone_card))["written"] == []


def test_feedback_view_pending_notes_counts_this_book_only(book_db):
    """pending_notes 只数本书待下发留言，不数已下发，也不数同用户别的书。"""
    _require_feedback()
    from novel import service

    _insert_book("book-pending-count", chapters_done=0)
    _insert_book("book-pending-other", title="另一本书", chapters_done=0)
    _insert_note("book-pending-count", "本书待一")
    _insert_note("book-pending-count", "本书待二")
    _insert_note("book-pending-count", "本书已交", status="delivered", delivered_chapter=1,
                 response={"adopted": True, "response": "已采纳"})
    _insert_note("book-pending-other", "别的书待一")
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-pending-count")

    view = asyncio.run(service.feedback_view(USER, card))
    assert view["book"]["pending_notes"] == 2


@pytest.mark.parametrize("chapter_status", PROGRESS_STATUSES)
def test_feedback_view_planned_read_from_in_progress_meeting(chapter_status, book_db):
    _require_feedback()
    from novel import service

    _insert_book("book-planned", chapters_done=0, chapters=[
        {"chapter": 2, "status": chapter_status, "title": "第二章",
         "meeting": {"brief": {"user_notes": [{"id": "N1", "text": "留言"}]},
                     "decision": {"user_note_responses": [
                         {"note_id": "N1", "adopted": False, "response": "编辑部回应原文"}]}}},
    ])
    note_id = _insert_note("book-planned", "留言")
    feedback_id = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-planned",
        next_chapters="留言", note_id=note_id, note_sent_at="2026-11-12 10:00:00",
    )
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["note"]["planned_chapter"] == 2
    assert view["note"]["planned_adopted"] is False
    assert view["note"]["planned_response"] == "编辑部回应原文"

    # meeting 损坏时三项都是 None。
    _execute("UPDATE novel_chapters SET meeting_json='not-json' WHERE novel_id='book-planned'")
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["note"]["planned_chapter"] is None
    assert view["note"]["planned_adopted"] is None
    assert view["note"]["planned_response"] is None

    # done 的章即使含这条留言也不算。
    _execute("UPDATE novel_chapters SET status='done', meeting_json=? WHERE novel_id='book-planned'",
             (json.dumps({"brief": {"user_notes": [{"id": "N1"}]},
                          "decision": {"user_note_responses": [
                              {"note_id": "N1", "adopted": True, "response": "已采纳"}]}},
                         ensure_ascii=False),))
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["note"]["planned_chapter"] is None
    assert view["note"]["planned_adopted"] is None
    assert view["note"]["planned_response"] is None

    # stale（待复核）的章即使含这条留言也不算：它不是进行中状态。
    _execute("UPDATE novel_chapters SET status='stale' WHERE novel_id='book-planned'")
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["note"]["planned_chapter"] is None
    assert view["note"]["planned_adopted"] is None
    assert view["note"]["planned_response"] is None


def test_feedback_view_http_note_read_by_next_plan(workshop):
    _require_feedback()
    import agent_store
    import novel.feedback as feedback
    from novel import service

    client, fake = workshop
    book = _create_book(client, chapters=3, automation="per_chapter")
    _approve_setup(client, book)
    wait(client, book, "awaiting_plan")

    next_text = "下一章让证人保留原件"

    async def setup_card():
        conversation = (await agent_store.create_conversation(NOVEL_USER))["id"]
        detail = await service.detail(NOVEL_USER, book)
        clean, error = feedback.validate_feedback_args(
            {"book": detail["title"], "next_chapters": next_text}, detail,
        )
        assert error is None
        return await feedback.create_feedback(NOVEL_USER, conversation, detail, clean)

    card = asyncio.run(setup_card())
    sent = client.post(f"/novels/feedback/{card['id']}/note", headers=HTTP_HEADERS)
    assert sent.status_code == 200, sent.text
    assert sent.json()["note"]["status"] == "pending"

    approved = client.post(f"/novels/{book}/plan/approve", json={}, headers=HTTP_HEADERS)
    assert approved.status_code == 200, approved.text
    data = wait(client, book, "awaiting_plan")
    assert data["chapters_done"] == 1
    view = client.get(f"/novels/feedback/{card['id']}", headers=HTTP_HEADERS)
    assert view.status_code == 200, view.text
    assert view.json()["note"]["status"] == "pending"
    assert view.json()["note"]["planned_chapter"] == 2
    assert view.json()["book"]["awaiting_chapter"] == 2


def test_feedback_view_book_flags_and_redo_cost(book_db, monkeypatch):
    _require_feedback()
    from novel import service

    _insert_book("book-cost", status="awaiting_plan", editor="byok:self", chapters_done=0,
                 chapters=[{"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
                            "meeting": {"decision": {"ending_status": "end"}}}])
    own_cost = _insert_feedback(conversation_id=book_db.owner, novel_id="book-cost", plan_chapter=1)
    monkeypatch.setenv("DEV_MODE", "1")
    assert asyncio.run(service.feedback_view(USER, own_cost))["book"]["redo_cost"] == "own_model"

    _execute("UPDATE novels SET config_json=? WHERE id='book-cost'",
             (json.dumps({"agents": {"editor": "dashscope:qwen3.8-max"},
                          "target": {"max_chapters": 20}}, ensure_ascii=False),))
    plain = _insert_feedback(conversation_id=book_db.owner, novel_id="book-cost")
    view = asyncio.run(service.feedback_view(USER, plain))
    assert view["book"]["redo_cost"] == "free"
    assert view["book"]["automation"] == "per_batch"
    assert view["book"]["max_chapters"] == 20
    assert view["book"]["awaiting_is_final"] is True

    monkeypatch.delenv("DEV_MODE", raising=False)
    assert asyncio.run(service.feedback_view(USER, plain))["book"]["redo_cost"] == "strawberries"

    # awaiting_is_final 的其他取值、meeting 损坏与不在等确认时都为 False。
    _execute("UPDATE novel_chapters SET meeting_json=? WHERE novel_id='book-cost'",
             (json.dumps({"decision": {"ending_status": "continue"}}),))
    assert asyncio.run(service.feedback_view(USER, plain))["book"]["awaiting_is_final"] is False
    _execute("UPDATE novel_chapters SET meeting_json='not-json' WHERE novel_id='book-cost'")
    assert asyncio.run(service.feedback_view(USER, plain))["book"]["awaiting_is_final"] is False
    _execute("UPDATE novels SET status='completed' WHERE id='book-cost'")
    view = asyncio.run(service.feedback_view(USER, plain))
    assert view["book"]["awaiting_chapter"] is None
    assert view["book"]["awaiting_is_final"] is False


def test_feedback_view_plan_row_status_and_redo_pending(book_db):
    _require_feedback()
    from novel import service

    _insert_book("book-redo-view", status="running", chapters_done=0,
                 chapters=[{"chapter": 2, "status": "planning", "title": "第二章",
                            "meeting": {"_redo_note": "加强因果", "_redo_count": 1}}])
    feedback_id = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-redo-view",
        current_plan="加强因果", plan_chapter=2,
        redo_started_at="2026-11-12 10:00:00",
    )
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["book"]["plan_row_status"] == "planning"
    assert view["book"]["redo_pending"] is True

    _execute("UPDATE novel_chapters SET meeting_json=? WHERE novel_id='book-redo-view'",
             (json.dumps({"_redo_count": 1}),))
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["book"]["plan_row_status"] == "planning"
    assert view["book"]["redo_pending"] is False

    _execute("UPDATE novel_chapters SET status='awaiting_plan_approval' WHERE novel_id='book-redo-view'")
    view = asyncio.run(service.feedback_view(USER, feedback_id))
    assert view["book"]["plan_row_status"] == "awaiting_plan_approval"
    assert view["book"]["redo_pending"] is False


# ────────────────────────── 8. 交给编辑部 ──────────────────────────


def _insert_http_book(book_id, *, username=NOVEL_USER, title="归墟来信", status="awaiting_plan",
                      automation="per_chapter", chapters_done=0, chapters=()):
    config = {"agents": {"editor": "dashscope:qwen3.8-max"},
              "automation": automation,
              "target": {"min_chapters": 1, "max_chapters": 10, "chapter_words": 1000}}
    with _connect() as db:
        db.execute(
            """INSERT INTO novels(id,username,title,seed_idea,status,config_json,
               budget_strawberries,chapters_done) VALUES(?,?,?,'seed',?,?,100000,?)""",
            (book_id, username, title, status, json.dumps(config, ensure_ascii=False), chapters_done),
        )
        for item in chapters:
            db.execute(
                """INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,
                   flags_json,meeting_json,review_json,archive_json)
                   VALUES(?,?,?,?,?,'正文','[]',?, '[]','{}')""",
                (book_id, username, item["chapter"], item["status"], item.get("title", f"第{item['chapter']}章"),
                 json.dumps(item["meeting"], ensure_ascii=False) if item.get("meeting") else None),
            )
    return book_id


def test_send_feedback_note_http_atomic_idempotent_and_concurrent(workshop):
    _require_feedback()
    import agent_store
    import novel.feedback as feedback
    from novel import service

    client, _ = workshop
    _insert_http_book("book-note")
    conversation = asyncio.run(agent_store.create_conversation(NOVEL_USER))["id"]
    card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                            novel_id="book-note", next_chapters="把证据留给读者")

    response = client.post(f"/novels/feedback/{card}/note", headers=HTTP_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["note"]["status"] == "pending"
    assert body["note"]["sent_at"]
    notes = _note_rows("book-note")
    assert len(notes) == 1
    assert notes[0]["text"] == "把证据留给读者"
    assert notes[0]["status"] == "pending"
    first_note_id = _rows("SELECT note_id FROM novel_feedback WHERE id=?", (card,))[0]["note_id"]
    assert first_note_id == notes[0]["id"]

    again = client.post(f"/novels/feedback/{card}/note", headers=HTTP_HEADERS)
    assert again.status_code == 200, again.text
    assert len(_note_rows("book-note")) == 1
    assert _rows("SELECT note_id FROM novel_feedback WHERE id=?", (card,))[0]["note_id"] == first_note_id

    # 并发两次也只插一条。
    _insert_http_book("book-note-concurrent")
    concurrent_card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                                       novel_id="book-note-concurrent", next_chapters="只交一次")
    async def race():
        return await asyncio.gather(
            service.send_feedback_note(NOVEL_USER, concurrent_card),
            service.send_feedback_note(NOVEL_USER, concurrent_card),
        )

    views = asyncio.run(race())
    assert len(views) == 2 and all(view["note"]["status"] == "pending" for view in views)
    assert len(_note_rows("book-note-concurrent")) == 1


@pytest.mark.parametrize("case", ["full", "completed", "failed", "deleted", "empty"])
def test_send_feedback_note_http_rejections(workshop, case):
    _require_feedback()
    import agent_store

    client, _ = workshop
    conversation = asyncio.run(agent_store.create_conversation(NOVEL_USER))["id"]
    if case == "full":
        _insert_http_book("book-note-reject")
        for index in range(5):
            _insert_note("book-note-reject", f"旧留言{index}", username=NOVEL_USER)
        card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                                novel_id="book-note-reject", next_chapters="第六条")
        expected = (409, "待处理留言最多五条")
    elif case == "completed":
        _insert_http_book("book-note-reject", status="completed")
        card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                                novel_id="book-note-reject", next_chapters="留言")
        expected = (409, "这本书已经完结，编辑部不会再读留言")
    elif case == "failed":
        _insert_http_book("book-note-reject", status="failed")
        card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                                novel_id="book-note-reject", next_chapters="留言")
        expected = (409, "这本书处于失败状态，编辑部不会再读留言")
    elif case == "deleted":
        card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                                novel_id="missing-book", next_chapters="留言")
        expected = (409, "这本书已经删除")
    else:
        _insert_http_book("book-note-reject")
        card = _insert_feedback(conversation_id=conversation, username=NOVEL_USER,
                                novel_id="book-note-reject", next_chapters="   ")
        expected = (409, "这张卡没有要交给编辑部的内容")

    response = client.post(f"/novels/feedback/{card}/note", headers=HTTP_HEADERS)
    assert response.status_code == expected[0]
    assert response.json()["detail"] == expected[1]
    row = _rows("SELECT note_id FROM novel_feedback WHERE id=?", (card,))[0]
    assert row["note_id"] is None
    if case in ("full", "completed", "failed", "deleted"):
        count = 5 if case == "full" else 0
        assert len(_note_rows("book-note-reject")) == count


def test_send_feedback_note_http_hides_foreign_card(workshop):
    _require_feedback()
    import agent_store

    client, _ = workshop
    _insert_http_book("book-note-foreign")
    other_conversation = asyncio.run(agent_store.create_conversation(NOVEL_OTHER))["id"]
    card = _insert_feedback(conversation_id=other_conversation, username=NOVEL_OTHER,
                            novel_id="book-note-foreign", next_chapters="别人的留言")
    response = client.post(f"/novels/feedback/{card}/note", headers=HTTP_HEADERS)
    assert response.status_code == 404
    assert response.json()["detail"] == "修改意见不存在"
    assert _note_rows("book-note-foreign") == []


def test_note_route_behavior_unchanged(workshop):
    """回归类：POST /novels/{id}/notes 的返回与五条上限不变。"""
    client, _ = workshop
    _insert_http_book("book-plain-note")
    for index in range(5):
        response = client.post("/novels/book-plain-note/notes", json={"text": f"留言{index}"},
                               headers=HTTP_HEADERS)
        assert response.status_code == 200
        assert response.json() == {"status": "pending"}
    overflow = client.post("/novels/book-plain-note/notes", json={"text": "第六条"}, headers=HTTP_HEADERS)
    assert overflow.status_code == 409
    assert overflow.json()["detail"] == "待处理留言最多五条"
    assert len(_note_rows("book-plain-note")) == 5


# ────────────────────────── 9. 重新定稿 ──────────────────────────


def _stub_start_novel(monkeypatch):
    import novel.runner as runner

    calls = []

    async def fake_start(novel_id, username):
        calls.append((novel_id, username))

    monkeypatch.setattr(runner, "start_novel", fake_start)
    return calls


def test_redo_feedback_plan_service_success_and_idempotent(book_db, monkeypatch):
    _require_feedback()
    from novel import service

    calls = _stub_start_novel(monkeypatch)
    _insert_book("book-redo", status="awaiting_plan", automation="per_chapter", chapters_done=0,
                 chapters=[{"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo",
                            current_plan="  第 2 章要加强因果  ", plan_chapter=2)

    view = asyncio.run(service.redo_feedback_plan(USER, card))
    assert view["redo_started_at"]
    row = _chapter_row("book-redo", 2)
    assert row["status"] == "planning"
    meeting = json.loads(row["meeting_json"])
    assert meeting["_redo_note"] == "第 2 章要加强因果"
    assert meeting["_redo_count"] == 1
    assert calls == [("book-redo", USER)]

    again = asyncio.run(service.redo_feedback_plan(USER, card))
    assert again["redo_started_at"] == view["redo_started_at"]
    assert json.loads(_chapter_row("book-redo", 2)["meeting_json"])["_redo_count"] == 1
    assert calls == [("book-redo", USER)]


def test_redo_feedback_plan_service_rejections(book_db, monkeypatch):
    _require_feedback()
    from fastapi import HTTPException
    from novel import runner, service

    calls = _stub_start_novel(monkeypatch)
    _insert_book("book-redo-mismatch", status="awaiting_plan", automation="per_chapter",
                 chapters_done=0, chapters=[
                     {"chapter": 3, "status": "awaiting_plan_approval", "title": "第三章",
                      "meeting": {"decision": {"ending_status": "continue"}}}])
    mismatch = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo-mismatch",
                                current_plan="要求", plan_chapter=2)
    _insert_book("book-redo-state", status="running", automation="per_chapter", chapters_done=0,
                 chapters=[{"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    wrong_state = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo-state",
                                   current_plan="要求", plan_chapter=1)
    _insert_book("book-redo-batch", status="awaiting_plan", automation="per_batch", chapters_done=0,
                 chapters=[{"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    per_batch = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo-batch",
                                 current_plan="要求", plan_chapter=1)
    no_plan = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo-batch",
                               current_plan="  ", plan_chapter=1)
    gone = _insert_feedback(conversation_id=book_db.owner, novel_id="missing-book",
                            current_plan="要求", plan_chapter=1)

    cases = [
        (mismatch, "第 2 章细纲已经不在等你确认了"),
        (wrong_state, "第 1 章细纲已经不在等你确认了"),
        (per_batch, "这本书现在不是逐章确认，重新定稿后会直接写正文；请到书斋里操作"),
        (no_plan, "这张卡没有重新定稿的要求"),
        (gone, "这本书已经删除"),
    ]
    for card, expected in cases:
        book_id = _rows("SELECT novel_id FROM novel_feedback WHERE id=?", (card,))[0]["novel_id"]
        before = _rows("SELECT chapter,status,meeting_json FROM novel_chapters WHERE novel_id=? ORDER BY chapter",
                       (book_id,))
        with pytest.raises(HTTPException) as caught:
            asyncio.run(service.redo_feedback_plan(USER, card))
        assert caught.value.status_code == 409
        assert caught.value.detail == expected
        assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?", (card,))[0]["redo_started_at"] is None
        assert _rows("SELECT chapter,status,meeting_json FROM novel_chapters WHERE novel_id=? ORDER BY chapter",
                     (book_id,)) == before
        assert book_id not in runner.TASKS
    assert calls == []


def test_redo_feedback_plan_rejects_card_without_plan_chapter(book_db, monkeypatch):
    """P2：current_plan 非空但 plan_chapter 为 NULL 的卡不能发起重新定稿。"""
    _require_feedback()
    from fastapi import HTTPException
    from novel import service

    calls = _stub_start_novel(monkeypatch)
    _insert_book("book-redo-no-plan-chapter", status="awaiting_plan",
                 automation="per_chapter", chapters_done=0, chapters=[
                     {"chapter": 3, "status": "awaiting_plan_approval", "title": "第三章",
                      "meeting": {"decision": {"ending_status": "continue"}}}])
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo-no-plan-chapter",
                            current_plan="第 3 章要加强因果", plan_chapter=None)
    before = _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                   "WHERE novel_id='book-redo-no-plan-chapter' ORDER BY chapter")

    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.redo_feedback_plan(USER, card))
    assert caught.value.status_code == 409
    assert caught.value.detail == "这张卡没有重新定稿的要求"
    assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?", (card,))[0]["redo_started_at"] is None
    assert _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                 "WHERE novel_id='book-redo-no-plan-chapter' ORDER BY chapter") == before
    assert calls == []

    # 书不是 awaiting_plan（running）时也先走「卡上没有记下章号」，不是章号对不上。
    _insert_book("book-redo-running-no-plan-chapter", status="running",
                 automation="per_chapter", chapters_done=0, chapters=[
                     {"chapter": 3, "status": "awaiting_plan_approval", "title": "第三章",
                      "meeting": {"decision": {"ending_status": "continue"}}}])
    running = _insert_feedback(conversation_id=book_db.owner,
                               novel_id="book-redo-running-no-plan-chapter",
                               current_plan="第 3 章要加强因果", plan_chapter=None)
    # 书已删（卡片 novel_id 为 NULL）同样先报「没有记下章号」，而不是「这本书已经删除」。
    deleted = _insert_feedback(conversation_id=book_db.owner, novel_id=None,
                               current_plan="第 3 章要加强因果", plan_chapter=None)
    running_before = _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                           "WHERE novel_id='book-redo-running-no-plan-chapter' ORDER BY chapter")
    for extra_card in (running, deleted):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(service.redo_feedback_plan(USER, extra_card))
        assert caught.value.status_code == 409
        assert caught.value.detail == "这张卡没有重新定稿的要求"
        assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?",
                     (extra_card,))[0]["redo_started_at"] is None
        assert calls == []
    assert _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                 "WHERE novel_id='book-redo-running-no-plan-chapter' ORDER BY chapter") == running_before


def test_redo_feedback_plan_service_concurrent_only_starts_once(book_db, monkeypatch):
    _require_feedback()
    from novel import service

    calls = _stub_start_novel(monkeypatch)
    _insert_book("book-redo-race", status="awaiting_plan", automation="per_chapter", chapters_done=0,
                 chapters=[{"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-redo-race",
                            current_plan="要求", plan_chapter=1)

    async def race():
        return await asyncio.gather(
            service.redo_feedback_plan(USER, card),
            service.redo_feedback_plan(USER, card),
            return_exceptions=True,
        )

    results = asyncio.run(race())
    assert all(isinstance(result, dict) for result in results), results
    row = _chapter_row("book-redo-race", 1)
    assert json.loads(row["meeting_json"])["_redo_count"] == 1
    assert calls == [("book-redo-race", USER)]


@pytest.fixture
def workshop(client, monkeypatch):
    import database
    from novel.fake_llm import FakeLLM
    from novel.llm_router import LLMRouter
    from novel import runner
    from rate_limit import limiter

    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", f"{NOVEL_USER},{NOVEL_OTHER}")
    monkeypatch.setattr(limiter, "enabled", False)
    asyncio.run(database.get_or_create_user(NOVEL_USER))
    asyncio.run(database.get_or_create_user(NOVEL_OTHER))
    fake = FakeLLM()
    monkeypatch.setattr(
        runner, "router_factory",
        lambda store, username, novel_id, run_token: LLMRouter(store, dry_run=True, fake=fake),
    )
    return client, fake


def _payload(chapters=3, automation="per_batch"):
    return {
        "seed_idea": "一本关于失落档案的悬疑小说",
        "agents": {
            "editor": "dashscope:qwen3.8-max",
            "writer": "deepseek:deepseek-flash",
            "archivist": "dashscope:qwen3.8-max",
            "reviewer": "dashscope:qwen3.8-max",
            "twist_designer": "ark:doubao-seed-2-1-pro-260915",
        },
        "panel_mode": "critique",
        "automation": automation,
        "batch_size": 5,
        "target": {"min_chapters": chapters, "max_chapters": chapters, "chapter_words": 1000},
        "budget_strawberries": 100000,
    }


def wait(client, book, state, headers=HTTP_HEADERS):
    import time

    data = None
    for _ in range(800):
        response = client.get("/novels/" + book, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] == state:
            return data
        if data["status"] in ("failed", "paused") and state not in ("failed", "paused"):
            pytest.fail(str(data))
        time.sleep(0.01)
    pytest.fail("timeout waiting for " + state + ": " + str(data))


def _create_book(client, chapters=3, automation="per_batch"):
    response = client.post("/novels", json=_payload(chapters, automation), headers=HTTP_HEADERS)
    assert response.status_code == 201, response.text
    book = response.json()["id"]
    wait(client, book, "awaiting_setup")
    return book


def _approve_setup(client, book):
    response = client.post(f"/novels/{book}/setup/approve", json={}, headers=HTTP_HEADERS)
    assert response.status_code == 200, response.text


def _http_feedback_card(book, *, current_plan="第 1 章要加强因果", plan_chapter=1,
                        next_chapters=""):
    import agent_store

    conversation = asyncio.run(agent_store.create_conversation(NOVEL_USER))["id"]
    return _insert_feedback(
        conversation_id=conversation, username=NOVEL_USER, novel_id=book,
        next_chapters=next_chapters, current_plan=current_plan,
        plan_chapter=plan_chapter,
    )


def test_redo_feedback_plan_http_runs_runner(workshop):
    _require_feedback()
    client, fake = workshop
    book = _create_book(client, chapters=3, automation="per_chapter")
    _approve_setup(client, book)
    wait(client, book, "awaiting_plan")
    card = _http_feedback_card(book, current_plan="第 1 章加强因果")
    current_plan = _rows("SELECT current_plan FROM novel_feedback WHERE id=?", (card,))[0]["current_plan"]

    before = len(fake.calls)
    chapter = client.get(f"/novels/{book}/chapters/1", headers=HTTP_HEADERS).json()
    assert "_redo_count" not in chapter["meeting"]
    n = chapter["meeting"].get("_redo_count", 0) + 1
    response = client.post(f"/novels/feedback/{card}/redo", headers=HTTP_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["redo_started_at"]
    wait(client, book, "awaiting_plan")

    assert len(fake.calls) == before + 1
    assert fake.calls[-1]["step_key"].endswith(f"-redo{n}.json")
    assert fake.calls[-1]["step_key"].endswith("-redo1.json")
    from novel.fake_llm import FakeLLM
    assert FakeLLM.payload(fake.calls[-1])["author_instruction"] == current_plan
    refreshed = client.get(f"/novels/{book}/chapters/1", headers=HTTP_HEADERS).json()
    assert refreshed["status"] == "awaiting_plan_approval"
    assert refreshed["meeting"]["_redo_count"] == n
    assert "_redo_note" not in refreshed["meeting"]


def test_redo_feedback_plan_http_background_failure_pauses(workshop):
    _require_feedback()
    from novel.llm_router import StepFailed

    client, fake = workshop
    book = _create_book(client, chapters=3, automation="per_chapter")
    _approve_setup(client, book)
    wait(client, book, "awaiting_plan")
    card = _http_feedback_card(book, current_plan="第 1 章加强因果")

    def script(request, index):
        if "-redo" in (request.get("step_key") or ""):
            return StepFailed("x", status="decision_invalid")
        return None

    fake.script = script
    response = client.post(f"/novels/feedback/{card}/redo", headers=HTTP_HEADERS)
    assert response.status_code == 200, response.text
    wait(client, book, "paused")
    view = client.get(f"/novels/feedback/{card}", headers=HTTP_HEADERS)
    assert view.status_code == 200, view.text
    data = view.json()
    assert data["redo_started_at"]
    assert data["book"]["plan_row_status"] == "planning"
    assert data["book"]["redo_pending"] is True


def test_redo_plan_route_behavior_unchanged(workshop):
    """回归类：POST /novels/{id}/plan/redo 仍按原状态机工作。"""
    client, fake = workshop
    book = _create_book(client, chapters=3, automation="per_chapter")
    _approve_setup(client, book)
    wait(client, book, "awaiting_plan")
    before = len(fake.calls)
    response = client.post(f"/novels/{book}/plan/redo", json={"text": "请加强因果"}, headers=HTTP_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "running"
    wait(client, book, "awaiting_plan")
    assert len(fake.calls) == before + 1
    meeting = client.get(f"/novels/{book}/chapters/1", headers=HTTP_HEADERS).json()["meeting"]
    assert meeting["_redo_count"] == 1
    assert "_redo_note" not in meeting

    other = _create_book(client, chapters=2)
    blocked = client.post(f"/novels/{other}/plan/redo", json={"text": "重做"}, headers=HTTP_HEADERS)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "当前状态不能执行此操作"


# ────────────────────────── 10. 清理 ──────────────────────────


def test_clear_history_and_account_delete_remove_only_own_feedback(book_db):
    _require_feedback()

    own = _insert_feedback(conversation_id=book_db.owner)
    own_second = _insert_feedback(conversation_id=book_db.owner_second)
    foreign = _insert_feedback(username=OTHER, conversation_id=book_db.other)

    asyncio.run(book_db.db.clear_message_history(USER))
    remaining = {row["id"] for row in _feedback_rows()}
    assert own not in remaining and own_second not in remaining
    assert foreign in remaining

    own_again = _insert_feedback(conversation_id=book_db.owner)
    asyncio.run(book_db.db.delete_account_data(USER))
    assert {row["id"] for row in _feedback_rows()} == {foreign}
    assert own_again not in {row["id"] for row in _feedback_rows()}


def test_delete_conversation_removes_only_that_conversations_feedback(book_db):
    _require_feedback()

    first = _insert_feedback(conversation_id=book_db.owner)
    second = _insert_feedback(conversation_id=book_db.owner_second)
    foreign = _insert_feedback(username=OTHER, conversation_id=book_db.other)

    asyncio.run(book_db.agent_store.delete_conversation(USER, book_db.owner))
    remaining = {row["id"] for row in _feedback_rows()}
    assert first not in remaining
    assert second in remaining and foreign in remaining


def test_delete_book_keeps_feedback_and_nulls_novel_id(book_db):
    _require_feedback()
    from novel import service

    _insert_book("book-delete", chapters_done=0)
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-delete",
                            next_chapters="留言")
    _insert_note("book-delete", "留言")
    asyncio.run(service.delete(USER, "book-delete"))
    row = _rows("SELECT novel_id FROM novel_feedback WHERE id=?", (card,))[0]
    assert row["novel_id"] is None
    view = asyncio.run(service.feedback_view(USER, card))
    assert view["novel_id"] is None
    assert view["book"] is None


# ────────────────────────── 11. 表与列 ──────────────────────────


def test_init_db_creates_feedback_table_without_switch(tmp_path, monkeypatch):
    _require_feedback()
    import database

    monkeypatch.delenv("FIONA_NOVEL_CHAT_FEEDBACK", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "unconditional.db"))
    asyncio.run(database.init_db())
    with sqlite3.connect(database.DB_PATH) as db:
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='novel_feedback'"
        ).fetchone() is not None
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_novel_feedback_owner'"
        ).fetchone() is not None


def test_init_db_adds_feedback_column_to_old_messages_table(tmp_path, monkeypatch):
    _require_feedback()
    import database

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, "
            "role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        )
    monkeypatch.delenv("FIONA_NOVEL_CHAT_FEEDBACK", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(path))
    asyncio.run(database.init_db())
    with sqlite3.connect(path) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(messages)")]
    assert "novel_feedback_id" in columns


# ────────────────────────── 12. 坏副本自检 ──────────────────────────


def test_bad_missing_feedback_switch_is_caught(enabled, monkeypatch):
    _require_feedback()
    import services.chat_service as chat
    import services.claude_agent as agent

    monkeypatch.setenv("FIONA_NOVEL_CHAT_FEEDBACK", "0")
    source = _read("services/claude_agent.py")
    marker = "if novel_feedback_enabled(ctx.user):"
    assert marker in source, "新开关判断的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "if True:", 1)
    assert bad_source != source
    bad = _load_module("bad_agent_feedback_switch", bad_source)
    ctx = chat.ChatContext(USER, "把意见交给书斋", False, None, "把意见交给书斋", [], 0,
                           "persona", [], auth_method="jwt")
    state = chat.ChatState(trace={})

    def check_absent(module):
        names = [tool["name"] for tool in module.client_tools_for_turn(ctx, state)]
        assert "draft_novel_feedback" not in names
        assert names[:len(CONSTANT_TOOL_NAMES)] == CONSTANT_TOOL_NAMES

    check_absent(agent)
    with pytest.raises(AssertionError):
        check_absent(bad)


def _run_two_feedback_calls(module, h, conversation, book):
    import services.chat_service as chat

    h.ctx.conversation_id = conversation
    h.state = chat.ChatState(trace={})
    h.streams.clear()
    for index in range(2):
        h.streams.append(FakeStream(message("tool_use", content=[
            call("draft_novel_feedback", {"book": "归墟来信", "next_chapters": "要求"},
                 identity=f"twice-{index}"),
        ])))
    h.streams.append(FakeStream(message(text="写完了。"), "写完了。"))

    async def collect():
        return [json.loads(event[6:]) if event.startswith("data: ") else event
                async for event in module.stream_claude_agent(h.ctx, h.state)]

    asyncio.run(collect())


def _clear_feedback():
    _execute("DELETE FROM novel_feedback")


def test_bad_one_feedback_per_turn_copy_is_caught(harness, feedback_enabled, book_db):
    _require_feedback()
    import novel.runner as runner

    _insert_book("book-bad-twice", status="awaiting_plan", automation="per_chapter", chapters_done=0,
                 chapters=[{"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    source = _read("services/claude_agent.py")
    marker = "if feedback_written:"
    assert marker in source, "每轮一张计数器的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "if False:", 1)
    assert bad_source != source
    bad = _load_module("bad_agent_feedback_twice", bad_source)
    bad.open_agent_stream = harness.agent.open_agent_stream
    h = harness

    def check(row_count):
        assert row_count == 1, row_count

    # 正样本：真实实现必须只留一张。
    _run_two_feedback_calls(h.agent, h, book_db.owner, "book-bad-twice")
    check(_feedback_count())
    _clear_feedback()

    # 坏副本：绕过每轮一张限制后，同一检查函数必须变红。
    _run_two_feedback_calls(bad, h, book_db.owner, "book-bad-twice")
    with pytest.raises(AssertionError):
        check(_feedback_count())
    assert _feedback_count() == 2
    assert "book-bad-twice" not in runner.TASKS


def test_bad_save_message_feedback_ownership_is_caught(book_db):
    _require_feedback()

    source = _read("database.py")
    start_marker = "        # 修改意见卡归属同样只做附加校验"
    end_marker = "        # 书斋草稿归属同样只做附加校验"
    assert start_marker in source and end_marker in source, "save_message 归属校验标记消失，无法做坏副本自检"
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    bad_source = source[:start] + "        stored_novel_feedback_id = novel_feedback_id\n" + source[end:]
    assert bad_source != source
    bad = _load_module("bad_database_feedback_ownership", bad_source)
    bad.DB_PATH = book_db.db.DB_PATH

    foreign = _insert_feedback(username=OTHER, conversation_id=book_db.other)

    def check(stored):
        assert stored is None, stored

    async def save(module, content):
        await module.save_message(USER, "assistant", content, conversation_id=book_db.owner,
                                  novel_feedback_id=foreign)

    asyncio.run(save(book_db.db, "real-copy"))
    row = _rows("SELECT novel_feedback_id FROM messages WHERE content='real-copy'")[0]
    check(row["novel_feedback_id"])

    asyncio.run(save(bad, "bad-copy"))
    row = _rows("SELECT novel_feedback_id FROM messages WHERE content='bad-copy'")[0]
    with pytest.raises(AssertionError):
        check(row["novel_feedback_id"])


def test_bad_send_note_without_idempotency_guard_is_caught(book_db, monkeypatch):
    _require_feedback()
    from novel import service as real

    source = _read("novel/service.py")
    marker = "        if card['note_id'] is None:"
    assert source.count(marker) == 1, "send_feedback_note 幂等判断标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "        if True:", 1)
    assert bad_source != source
    bad = _load_bad_service(bad_source)
    monkeypatch.setenv("DEV_MODE", "1")
    import agent_store

    conversation = asyncio.run(agent_store.create_conversation(USER))["id"]
    _insert_book("book-bad-note-real", chapters_done=0)
    _insert_book("book-bad-note-bad", chapters_done=0)
    real_card = _insert_feedback(conversation_id=conversation, novel_id="book-bad-note-real",
                                 next_chapters="留言")
    bad_card = _insert_feedback(conversation_id=conversation, novel_id="book-bad-note-bad",
                                next_chapters="留言")

    async def check(module, card, book):
        await module.send_feedback_note(USER, card)
        await module.send_feedback_note(USER, card)
        assert len(_note_rows(book)) == 1

    asyncio.run(check(real, real_card, "book-bad-note-real"))
    with pytest.raises(AssertionError):
        asyncio.run(check(bad, bad_card, "book-bad-note-bad"))
    assert len(_note_rows("book-bad-note-bad")) == 2


def test_bad_redo_without_expected_chapter_is_caught(book_db, monkeypatch):
    _require_feedback()
    from fastapi import HTTPException
    from novel import service as real

    _stub_start_novel(monkeypatch)
    _insert_book("book-bad-redo", status="awaiting_plan", automation="per_chapter", chapters_done=0,
                 chapters=[{"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                            "meeting": {"decision": {"ending_status": "continue"}}}])
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-bad-redo",
                            current_plan="要求", plan_chapter=1)

    source = _read("novel/service.py")
    marker = "expected_chapter=card['plan_chapter'])"
    assert marker in source, "重新定稿章号核对的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "expected_chapter=None)", 1)
    assert bad_source != source
    bad = _load_bad_service(bad_source)

    async def check(module):
        try:
            await module.redo_feedback_plan(USER, card)
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "第 1 章细纲已经不在等你确认了"
            return
        raise AssertionError("章号对不上时必须拒绝重新定稿")

    asyncio.run(check(real))
    with pytest.raises(AssertionError):
        asyncio.run(check(bad))


def test_bad_feedback_view_without_planned_chapter_is_caught(book_db):
    _require_feedback()
    from novel import service as real

    _insert_book("book-bad-planned", chapters_done=0, chapters=[
        {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
         "meeting": {"brief": {"user_notes": [{"id": "N1"}]}}},
    ])
    note_id = _insert_note("book-bad-planned", "留言")
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-bad-planned",
                            next_chapters="留言", note_id=note_id,
                            note_sent_at="2026-11-12 10:00:00")

    source = _read("novel/service.py")
    marker = "        if note is not None and note['status']=='pending' and book_row is not None:"
    assert marker in source, "已读留言计算的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "        if False:", 1)
    assert bad_source != source
    bad = _load_bad_service(bad_source)

    async def check(module):
        view = await module.feedback_view(USER, card)
        assert view["note"]["planned_chapter"] == 2

    asyncio.run(check(real))
    with pytest.raises(AssertionError):
        asyncio.run(check(bad))


def test_bad_feedback_view_final_flag_is_caught(book_db):
    _require_feedback()
    from novel import service as real

    _insert_book("book-bad-final", status="awaiting_plan", chapters_done=0, chapters=[
        {"chapter": 1, "status": "awaiting_plan_approval", "title": "第一章",
         "meeting": {"decision": {"ending_status": "end"}}},
    ])
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-bad-final")

    source = _read("novel/service.py")
    marker = "awaiting_is_final=isinstance(pending_decision,dict) and pending_decision.get('ending_status')=='end'"
    assert marker in source, "最后一章判断的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "awaiting_is_final=False", 1)
    assert bad_source != source
    bad = _load_bad_service(bad_source)

    async def check(module):
        view = await module.feedback_view(USER, card)
        assert view["book"]["awaiting_is_final"] is True

    asyncio.run(check(real))
    with pytest.raises(AssertionError):
        asyncio.run(check(bad))


def test_bad_planned_read_statuses_are_caught(book_db):
    """B1：坏副本少一个进行中状态时，对应状态组必须变红。"""
    _require_feedback()
    from novel import service as real

    _insert_book("book-bad-planned-statuses", chapters_done=0, chapters=[
        {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
         "meeting": {"brief": {"user_notes": [{"id": "N1"}]},
                     "decision": {"user_note_responses": [
                         {"note_id": "N1", "adopted": False, "response": "编辑部回应原文"}]}}},
    ])
    note_id = _insert_note("book-bad-planned-statuses", "留言")
    card = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-bad-planned-statuses",
        next_chapters="留言", note_id=note_id, note_sent_at="2026-11-12 10:00:00",
    )

    source = _read("novel/service.py")
    marker = "('awaiting_plan_approval','planning','writing')"
    assert marker in source, "已读留言的三种进行中状态消失，无法做坏副本自检"
    assert source.count(marker) == 1
    two_status_source = source.replace(marker, "('awaiting_plan_approval','planning')", 1)
    one_status_source = source.replace(marker, "('awaiting_plan_approval')", 1)
    assert two_status_source != source and one_status_source != source
    bad_two = _load_bad_service(two_status_source)
    bad_one = _load_bad_service(one_status_source)

    async def check(module, status):
        _execute("UPDATE novel_chapters SET status=?, meeting_json=? WHERE novel_id=? AND chapter=2",
                 (status, json.dumps({"brief": {"user_notes": [{"id": "N1"}]},
                                      "decision": {"user_note_responses": [
                                          {"note_id": "N1", "adopted": False,
                                           "response": "编辑部回应原文"}]}},
                                     ensure_ascii=False),
                  "book-bad-planned-statuses"))
        view = await module.feedback_view(USER, card)
        assert view["note"]["planned_chapter"] == 2
        assert view["note"]["planned_adopted"] is False
        assert view["note"]["planned_response"] == "编辑部回应原文"

    # 正样本：三种状态都能读到。
    for status in PROGRESS_STATUSES:
        asyncio.run(check(real, status))

    # 坏副本少 writing：awaiting_plan_approval、planning 仍过，writing 变红。
    for status in PROGRESS_STATUSES[:2]:
        asyncio.run(check(bad_two, status))
    with pytest.raises(AssertionError):
        asyncio.run(check(bad_two, "writing"))

    # 坏副本只留 awaiting_plan_approval：planning 与 writing 都变红。
    asyncio.run(check(bad_one, "awaiting_plan_approval"))
    for status in ("planning", "writing"):
        with pytest.raises(AssertionError):
            asyncio.run(check(bad_one, status))


def test_bad_stale_planned_read_is_caught(book_db):
    """G6：坏副本把进行中状态放宽成 status<>'done' 后，stale 一段必须变红。"""
    _require_feedback()
    from novel import service as real

    _insert_book("book-bad-stale-planned", chapters_done=0, chapters=[
        {"chapter": 2, "status": "stale", "title": "第二章",
         "meeting": {"brief": {"user_notes": [{"id": "N1"}]},
                     "decision": {"user_note_responses": [
                         {"note_id": "N1", "adopted": True, "response": "已采纳"}]}}},
    ])
    note_id = _insert_note("book-bad-stale-planned", "留言")
    card = _insert_feedback(
        conversation_id=book_db.owner, novel_id="book-bad-stale-planned",
        next_chapters="留言", note_id=note_id, note_sent_at="2026-11-12 10:00:00",
    )

    source = _read("novel/service.py")
    marker = "status IN ('awaiting_plan_approval','planning','writing')"
    assert marker in source, "已读留言的进行中状态查询消失，无法做坏副本自检"
    assert source.count(marker) == 1
    bad_source = source.replace(marker, "status<>'done'", 1)
    assert bad_source != source
    bad = _load_bad_service(bad_source)

    async def check(module):
        view = await module.feedback_view(USER, card)
        assert view["note"]["planned_chapter"] is None
        assert view["note"]["planned_adopted"] is None
        assert view["note"]["planned_response"] is None

    # 正样本：stale 不算被细纲读到。
    asyncio.run(check(real))
    # 坏副本把 stale 也算进行中，plan_chapter（以及回应）一定有值，必须变红。
    with pytest.raises(AssertionError):
        asyncio.run(check(bad))
    bad_view = asyncio.run(bad.feedback_view(USER, card))
    assert bad_view["note"]["planned_chapter"] == 2
    assert bad_view["note"]["planned_adopted"] is True
    assert bad_view["note"]["planned_response"] == "已采纳"


UPPER_BOUNDARY_BAD_REPLACEMENTS = {
    "next": ("len(next_text) > TEXT_MAX", "len(next_text) >= TEXT_MAX"),
    "current": ("len(current_text) > TEXT_MAX", "len(current_text) >= TEXT_MAX"),
    "issue": ("len(issue_text) > ISSUE_MAX", "len(issue_text) >= ISSUE_MAX"),
    "written": ("len(written_raw) > WRITTEN_MAX", "len(written_raw) >= WRITTEN_MAX"),
}


@pytest.mark.parametrize("kind", UPPER_BOUNDARY_KINDS)
def test_bad_upper_boundary_comparison_is_caught(kind):
    """B2：把 > 改成 >= 后，恰在边界上的正样本必须变红。"""
    _require_feedback()
    from novel import feedback as real

    _upper_boundary_check(real.validate_feedback_args, kind)
    source = _read("novel/feedback.py")
    marker, replacement = UPPER_BOUNDARY_BAD_REPLACEMENTS[kind]
    assert marker in source, f"{kind} 上限比较的实现标记消失，无法做坏副本自检"
    assert source.count(marker) == 1, marker
    bad_source = source.replace(marker, replacement, 1)
    assert bad_source != source
    bad = _load_module(f"bad_feedback_upper_{kind}", bad_source)
    with pytest.raises(AssertionError):
        _upper_boundary_check(bad.validate_feedback_args, kind)


def test_bad_validate_chapter_beyond_chapters_done_is_caught(book_db):
    """B4：去掉 number > chapters_done 后，done 的第 3 章会被误当成可填。"""
    _require_feedback()
    from novel import feedback as real
    from novel import service

    _insert_book("book-bad-chapter-limit", chapters_done=2, chapters=[
        {"chapter": 1, "status": "done", "title": "第一章"},
        {"chapter": 2, "status": "done", "title": "第二章"},
        {"chapter": 3, "status": "done", "title": "第三章"},
    ])
    detail = asyncio.run(service.detail(USER, "book-bad-chapter-limit"))

    _check_chapter_limit(real.validate_feedback_args, detail)
    source = _read("novel/feedback.py")
    marker = "or number > chapters_done"
    assert marker in source, "chapters_done 上限的实现标记消失，无法做坏副本自检"
    assert source.count(marker) == 1
    bad_source = source.replace(marker, "or False", 1)
    assert bad_source != source
    bad = _load_module("bad_feedback_chapter_limit", bad_source)
    with pytest.raises(AssertionError):
        _check_chapter_limit(bad.validate_feedback_args, detail)


def test_bad_feedback_view_pending_note_count_is_caught(book_db):
    """B3：写死 0、去掉 status 条件、去掉按书过滤，三种坏副本都必须变红。"""
    _require_feedback()
    from novel import service as real

    _insert_book("book-bad-count", chapters_done=0)
    _insert_book("book-bad-count-other", title="另一本书", chapters_done=0)
    _insert_note("book-bad-count", "本书待一")
    _insert_note("book-bad-count", "本书待二")
    _insert_note("book-bad-count", "本书已交", status="delivered", delivered_chapter=1,
                 response={"adopted": True, "response": "已采纳"})
    _insert_note("book-bad-count-other", "别的书待一")
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-bad-count")

    source = _read("novel/service.py")
    count_line = ("            pending_count=await row(db,\"SELECT COUNT(*) AS n FROM novel_notes "
                  "WHERE novel_id=? AND status='pending'\",(card['novel_id'],))")
    hardcoded_line = "            pending_notes=pending_count['n']"
    assert count_line in source, "pending_notes 的 COUNT 语句消失，无法做坏副本自检"
    assert source.count(count_line) == 1
    assert hardcoded_line in source
    assert source.count(hardcoded_line) == 1
    source_without_status = source.replace(
        count_line,
        ("            pending_count=await row(db,\"SELECT COUNT(*) AS n FROM novel_notes "
         "WHERE novel_id=?\",(card['novel_id'],))"),
        1,
    )
    source_without_book = source.replace(
        count_line,
        ("            pending_count=await row(db,\"SELECT COUNT(*) AS n FROM novel_notes "
         "WHERE status='pending'\",())"),
        1,
    )
    source_hardcoded = source.replace(hardcoded_line, "            pending_notes=0", 1)
    assert source_without_status != source
    assert source_without_book != source
    assert source_hardcoded != source

    async def check(module):
        view = await module.feedback_view(USER, card)
        assert view["book"]["pending_notes"] == 2

    for bad_source in (source_hardcoded, source_without_status, source_without_book):
        asyncio.run(check(real))
        with pytest.raises(AssertionError):
            asyncio.run(check(_load_bad_service(bad_source)))


def _run_feedback_module_turn(h, module, conversation, args):
    """用给定 claude_agent 模块跑一轮 draft_novel_feedback，返回回灌文本。"""
    import services.chat_service as chat

    h.ctx.conversation_id = conversation
    h.state = chat.ChatState(trace={})
    h.streams.clear()
    h.requests.clear()
    h.streams.append(FakeStream(message("tool_use", content=[
        call("draft_novel_feedback", args, identity="feedback-module-check"),
    ])))
    h.streams.append(FakeStream(message(text="好"), "好"))
    original = h.agent
    h.agent = module
    try:
        run(h)
    finally:
        h.agent = original
    return h.requests[1][0][-1]["content"][0]["content"]


def test_bad_last_chapter_at_max_branch_is_caught(harness, feedback_enabled, book_db):
    """B5：K == max_chapters 时只看 awaiting_is_final 的坏副本会走错分支。"""
    _require_feedback()
    _insert_book("book-bad-last-max", status="awaiting_plan", automation="per_chapter",
                 chapters_done=1, max_chapters=2, chapters=[
                     {"chapter": 1, "status": "done", "title": "第一章"},
                     {"chapter": 2, "status": "awaiting_plan_approval", "title": "第二章",
                      "meeting": {"decision": {"ending_status": "continue"}}},
                 ])
    args = {"book": "归墟来信", "next_chapters": "最后一章要收束线索"}
    expected = _success_expected(next_kind="last", k=2, current=False, written=False)

    source = _read("services/claude_agent.py")
    marker = "(F or (M is not None and K >= M))"
    assert marker in source, "最后一章分支的实现标记消失，无法做坏副本自检"
    assert source.count(marker) == 1
    bad_source = source.replace(marker, "F", 1)
    assert bad_source != source
    bad = _load_module("bad_agent_last_chapter_at_max", bad_source)
    bad.open_agent_stream = harness.agent.open_agent_stream

    def check(text):
        assert text == expected
        assert "第 3 章" not in text

    check(_run_feedback_module_turn(harness, harness.agent, book_db.owner, args))
    bad_text = _run_feedback_module_turn(harness, bad, book_db.owner, args)
    with pytest.raises(AssertionError):
        check(bad_text)
    assert "第 3 章" in bad_text


def test_bad_redo_without_plan_chapter_guard_is_caught(book_db, monkeypatch):
    """B6：去掉 plan_chapter 为 NULL 的判断后，坏副本会对第 3 章发起重新定稿。"""
    _require_feedback()
    from fastapi import HTTPException
    from novel import service as real

    calls = _stub_start_novel(monkeypatch)
    _insert_book("book-bad-redo-no-plan", status="awaiting_plan",
                 automation="per_chapter", chapters_done=0, chapters=[
                     {"chapter": 3, "status": "awaiting_plan_approval", "title": "第三章",
                      "meeting": {"decision": {"ending_status": "continue"}}}])
    card = _insert_feedback(conversation_id=book_db.owner, novel_id="book-bad-redo-no-plan",
                            current_plan="第 3 章要加强因果", plan_chapter=None)
    before = _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                   "WHERE novel_id='book-bad-redo-no-plan' ORDER BY chapter")

    source = _read("novel/service.py")
    marker = " or card['plan_chapter'] is None"
    assert marker in source, "没有记下章号时拒绝的实现标记消失，无法做坏副本自检"
    assert source.count(marker) == 1
    bad_source = source.replace(marker, "", 1)
    assert bad_source != source
    bad = _load_bad_service(bad_source)

    async def check(module):
        try:
            await module.redo_feedback_plan(USER, card)
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "这张卡没有重新定稿的要求"
            assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?",
                         (card,))[0]["redo_started_at"] is None
            assert _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                         "WHERE novel_id='book-bad-redo-no-plan' ORDER BY chapter") == before
            assert calls == []
            return
        raise AssertionError("没有记下 plan_chapter 的卡必须拒绝重新定稿")

    asyncio.run(check(real))
    with pytest.raises(AssertionError):
        asyncio.run(check(bad))
    assert calls == [("book-bad-redo-no-plan", USER)]
    assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?",
                 (card,))[0]["redo_started_at"] is not None
    assert json.loads(_chapter_row("book-bad-redo-no-plan", 3)["meeting_json"])["_redo_count"] == 1


def test_bad_redo_plan_chapter_check_order_is_caught(book_db, monkeypatch):
    """G7：把 plan_chapter 判断挪到 _begin_redo 前时，running 与书已删必须变红。

    坏副本仍能通过原 B6 的 awaiting_plan 场景（最后那道判断会拦住），只有新增的
    running 与 novel_id 为 NULL 两种书态会先撞上书状态 / 删书判断而报出别的 409。
    """
    _require_feedback()
    from fastapi import HTTPException
    from novel import service as real

    calls = _stub_start_novel(monkeypatch)
    _insert_book("book-bad-redo-order-awaiting", status="awaiting_plan",
                 automation="per_chapter", chapters_done=0, chapters=[
                     {"chapter": 3, "status": "awaiting_plan_approval", "title": "第三章",
                      "meeting": {"decision": {"ending_status": "continue"}}}])
    awaiting = _insert_feedback(conversation_id=book_db.owner,
                                novel_id="book-bad-redo-order-awaiting",
                                current_plan="第 3 章要加强因果", plan_chapter=None)
    _insert_book("book-bad-redo-order-running", status="running",
                 automation="per_chapter", chapters_done=0, chapters=[
                     {"chapter": 3, "status": "awaiting_plan_approval", "title": "第三章",
                      "meeting": {"decision": {"ending_status": "continue"}}}])
    running = _insert_feedback(conversation_id=book_db.owner,
                               novel_id="book-bad-redo-order-running",
                               current_plan="第 3 章要加强因果", plan_chapter=None)
    deleted = _insert_feedback(conversation_id=book_db.owner, novel_id=None,
                               current_plan="第 3 章要加强因果", plan_chapter=None)
    snapshots = {
        "book-bad-redo-order-awaiting": _rows(
            "SELECT chapter,status,meeting_json FROM novel_chapters WHERE novel_id=? ORDER BY chapter",
            ("book-bad-redo-order-awaiting",)),
        "book-bad-redo-order-running": _rows(
            "SELECT chapter,status,meeting_json FROM novel_chapters WHERE novel_id=? ORDER BY chapter",
            ("book-bad-redo-order-running",)),
    }

    source = _read("novel/service.py")
    marker = " or card['plan_chapter'] is None"
    assert marker in source, "没有记下章号时拒绝的实现标记消失，无法做坏副本自检"
    assert source.count(marker) == 1
    begin_line = ("            await _begin_redo(db,username,novel_id,Note(text=card['current_plan'])"
                  ".text,expected_chapter=card['plan_chapter'])")
    assert begin_line in source, "发起重新定稿的实现标记消失，无法做坏副本自检"
    assert source.count(begin_line) == 1
    bad_source = source.replace(marker, "", 1)
    bad_source = bad_source.replace(
        begin_line,
        "            if card['plan_chapter'] is None:\n"
        "                fail('这张卡没有重新定稿的要求')\n" + begin_line,
        1,
    )
    assert bad_source != source
    bad = _load_bad_service(bad_source)

    async def attempt(module, card):
        try:
            await module.redo_feedback_plan(USER, card)
        except HTTPException as exc:
            return exc.status_code, exc.detail
        raise AssertionError("没有记下 plan_chapter 的卡必须拒绝重新定稿")

    async def check(module, card, expected):
        status, detail = await attempt(module, card)
        assert status == 409
        assert detail == expected
        assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?",
                     (card,))[0]["redo_started_at"] is None
        assert calls == []

    # 正样本：三种书态都先报「这张卡没有重新定稿的要求」。
    for card in (awaiting, running, deleted):
        asyncio.run(check(real, card, "这张卡没有重新定稿的要求"))
    # 坏副本：原 awaiting_plan 场景仍由最后那道判断拦住；running 与书已删必须先变红。
    asyncio.run(check(bad, awaiting, "这张卡没有重新定稿的要求"))
    for card in (running, deleted):
        with pytest.raises(AssertionError):
            asyncio.run(check(bad, card, "这张卡没有重新定稿的要求"))
    assert asyncio.run(attempt(bad, running)) == (409, "第 None 章细纲已经不在等你确认了")
    assert asyncio.run(attempt(bad, deleted)) == (409, "这本书已经删除")

    assert calls == []
    for card in (awaiting, running, deleted):
        assert _rows("SELECT redo_started_at FROM novel_feedback WHERE id=?",
                     (card,))[0]["redo_started_at"] is None
    for book_id, before in snapshots.items():
        assert _rows("SELECT chapter,status,meeting_json FROM novel_chapters "
                     "WHERE novel_id=? ORDER BY chapter", (book_id,)) == before
