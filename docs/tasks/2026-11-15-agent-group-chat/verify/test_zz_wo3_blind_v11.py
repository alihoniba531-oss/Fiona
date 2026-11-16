# -*- coding: utf-8 -*-
"""规格作者的 v1.1 盲测（同名优先、平台续读），按规格写，不看执行方用例。放进新代码副本的 backend/tests/ 运行。"""
import asyncio
import re
import sqlite3
import uuid

import pytest

from discuss import chat as dchat

USER = "author"


def db_exec(sql, params=()):
    import database
    with sqlite3.connect(database.DB_PATH) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute(sql, params)]
        db.commit()
    return rows


def new_group(title, *, request="调研东南亚短剧市场值不值得做", status="paused", updated="2026-11-15T10:00:00+00:00"):
    gid = uuid.uuid4().hex
    db_exec(
        """INSERT INTO discuss_groups
           (id, username, title, request, materials, status, stop_reason, round, max_rounds, plan_json,
            plan_revision, config_json, budget_strawberries, spent_strawberries, reserved_strawberries,
            output_version, run_token, created_day, created_at, updated_at)
           VALUES (?,?,?,?,'',?,'user',1,3,'{}',0,'{}',500,0,0,0,NULL,'2026-11-15',?,?)""",
        (gid, USER, title, request, status, updated, updated))
    return gid


def add_output(gid, content):
    db_exec("INSERT INTO discuss_outputs(group_id,username,version,round,step_key,content,verdict_json,passed,created_at) "
            "VALUES(?,?,1,1,'b/out',?,NULL,1,'2026-11-15T10:05:00+00:00')", (gid, USER, content))
    db_exec("UPDATE discuss_groups SET output_version=1 WHERE id=?", (gid,))


@pytest.fixture
def on(client, monkeypatch):
    for name in ("FIONA_NOVEL", "FIONA_NOVEL_USERS", "FIONA_NOVEL_CHAT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIONA_DISCUSS", "1")
    monkeypatch.setenv("FIONA_DISCUSS_USERS", USER)
    monkeypatch.setenv("FIONA_DISCUSS_CHAT", "1")
    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "0")
    return client


def test_exact_name_wins_and_brackets_are_stripped(on):
    short = new_group("东南亚AI短剧出海可行性调研", updated="2026-11-15T10:00:01+00:00")
    new_group("东南亚AI短剧出海可行性调研（待开工）", updated="2026-11-15T10:00:02+00:00")
    new_group("东南亚AI短剧出海可行性调研（已通过）", updated="2026-11-15T10:00:03+00:00")
    for query in ("东南亚AI短剧出海可行性调研", " 《东南亚AI短剧出海可行性调研》 ", "《 东南亚ai短剧出海可行性调研 》"):
        group, why = asyncio.run(dchat.resolve_group(USER, query))
        assert why is None and group["id"] == short, (query, why)
    group, why = asyncio.run(dchat.resolve_group(USER, "东南亚AI短剧"))
    assert group is None and why.startswith("要看哪个讨论群？找到这些：") and why.count("《") == 3
    group, why = asyncio.run(dchat.resolve_group(USER, "《待开工》"))
    assert why is None and group["title"].endswith("（待开工）")
    twin = new_group("东南亚AI短剧出海可行性调研", updated="2026-11-15T10:00:04+00:00")
    group, why = asyncio.run(dchat.resolve_group(USER, "东南亚AI短剧出海可行性调研"))
    assert group is None and why.startswith("要看哪个讨论群？找到这些：")
    assert why.count("《") == 2 and "待开工" not in why and "已通过" not in why and twin


def test_read_output_carries_group_id_and_two_hint_styles(on):
    gid = new_group("长成果")
    add_output(gid, "甲" * 6500)
    r = asyncio.run(dchat.read_output(USER, "长成果", 0))
    assert r["success"] and r["group_id"] == gid and r["continuation"] == 6000
    assert r["text"].endswith("</discuss_data>\n还有后文，说『继续读』接着念。")
    assert not re.search(r"\d", r["text"].rsplit("</discuss_data>", 1)[1])
    assert r["model_text"].endswith("\n还有后文，接着读请从 6000 开始。")
    bad = asyncio.run(dchat.read_output(USER, "不存在", 0))
    assert bad["success"] is False and "group_id" not in bad


def _platform(monkeypatch):
    from test_claude_agent_routing import collect, context, isolate, parse
    chat, saved, traces, refunded = isolate(monkeypatch)
    normal = []

    async def fake_normal(ctx, state):
        normal.append(ctx.message)
        state.full_response = "普通回复"
        yield chat._sse({"text": "普通回复"})
        yield chat._sse({"done": True})

    monkeypatch.setattr(chat, "stream_normal", fake_normal)

    def turn(message, recognized):
        calls = []

        def recognize(*args, **kwargs):
            calls.append(args[0])
            return recognized

        monkeypatch.setattr(chat, "recognize_intent_with_fallback", recognize)
        ctx = context(user=USER, byok_config=None, message=message, user_content=message,
                      messages=[{"role": "user", "content": message}], conversation_id="conv-1")
        events = parse(asyncio.run(collect(chat.run_chat(ctx, reserved=True, crisis=False))))
        return events, calls

    return chat, saved, normal, turn


def _body(text):
    return text.split("<discuss_data>\n", 1)[1].split("\n</discuss_data>", 1)[0]


def test_platform_continuation_round_trip(on, monkeypatch):
    from intent_router import get_discuss_read_position
    chat, saved, normal, turn = _platform(monkeypatch)
    gid = new_group("长成果")
    content = "".join(chr(0x4E00 + i % 3000) for i in range(13000))
    add_output(gid, content)
    events, calls = turn("把《长成果》的成果念给我听", {"intent": "discuss_read", "params": {"group": "长成果", "part": "output"}, "missing": []})
    assert calls and events[-1] == {"done": True}
    parts = [_body(saved[-1][0])]
    assert get_discuss_read_position(("author", "conv-1")) == {"group": gid, "part": "output", "offset": 6000}
    for phrase in ("继续读", "接着念。"):
        events, calls = turn(phrase, {"intent": None, "params": {}, "missing": []})
        assert calls == [], f"{phrase} 应走快捷续读，不该调用意图识别"
        parts.append(_body(saved[-1][0]))
    assert "".join(parts) == content
    assert "还有后文" not in saved[-1][0]
    assert get_discuss_read_position(("author", "conv-1")) is None
    events, calls = turn("接着读", {"intent": None, "params": {}, "missing": []})
    assert calls == ["接着读"] and normal == ["接着读"]


def test_continuation_not_taken_when_switch_off_or_phrase_differs_or_expired(on, monkeypatch):
    import database
    from intent_router import set_discuss_read_position
    chat, saved, normal, turn = _platform(monkeypatch)
    gid = new_group("长成果")
    add_output(gid, "乙" * 13000)
    key = ("author", "conv-1")
    set_discuss_read_position(key, {"group": gid, "part": "output", "offset": 6000})
    turn("继续读那个群", {"intent": None, "params": {}, "missing": []})
    assert normal == ["继续读那个群"]
    monkeypatch.setenv("FIONA_DISCUSS_CHAT", "0")
    turn("继续读", {"intent": None, "params": {}, "missing": []})
    assert normal == ["继续读那个群", "继续读"]
    monkeypatch.setenv("FIONA_DISCUSS_CHAT", "1")
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute("UPDATE chat_slot_state SET expires_at='2000-01-01T00:00:00+00:00' WHERE kind='discuss_read'")
    turn("继续读", {"intent": None, "params": {}, "missing": []})
    assert normal[-1] == "继续读" and len(normal) == 3


def test_newer_of_novel_and_discuss_positions_wins(on, monkeypatch):
    import database
    from intent_router import set_discuss_read_position, set_novel_read_position
    from studio import sources
    chat, saved, normal, turn = _platform(monkeypatch)
    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", USER)
    monkeypatch.setenv("FIONA_NOVEL_CHAT", "1")
    novel_calls = []

    async def read(user, title, start, end, offset):
        novel_calls.append(offset)
        return {"text": f"小说{offset}", "success": True, "book": "春山", "end_chapter": 3, "continuation": None}

    monkeypatch.setattr(sources, "read_novel", read)
    gid = new_group("长成果")
    add_output(gid, "丙" * 13000)
    key = ("author", "conv-1")

    def stamp(kind, when):
        with sqlite3.connect(database.DB_PATH) as db:
            db.execute("UPDATE chat_slot_state SET updated_at=? WHERE kind=?", (when, kind))

    set_novel_read_position(key, {"book": "春山", "chapter": "2-3", "offset": 2000})
    set_discuss_read_position(key, {"group": gid, "part": "output", "offset": 6000})
    stamp("novel_read", "2026-11-15T10:00:00+00:00")
    stamp("discuss_read", "2026-11-15T10:00:05+00:00")
    turn("继续读", {"intent": None, "params": {}, "missing": []})
    assert novel_calls == [] and "丙" in saved[-1][0]
    set_discuss_read_position(key, {"group": gid, "part": "output", "offset": 6000})
    set_novel_read_position(key, {"book": "春山", "chapter": "2-3", "offset": 2000})
    stamp("discuss_read", "2026-11-15T10:00:00+00:00")
    stamp("novel_read", "2026-11-15T10:00:05+00:00")
    turn("继续读", {"intent": None, "params": {}, "missing": []})
    assert novel_calls == [2000] and saved[-1][0] == "小说2000"


def test_claude_style_read_never_saves_a_position(on):
    import services.chat_service as chat
    from intent_router import get_discuss_read_position
    gid = new_group("长成果")
    add_output(gid, "丁" * 13000)
    r = chat.execute_intent("discuss_read", {"group": "长成果", "part": "output", "offset": 0}, username=USER)
    assert r["success"] and r["continuation"] == 6000
    assert get_discuss_read_position(("author", "conv-1")) is None and get_discuss_read_position(USER) is None
