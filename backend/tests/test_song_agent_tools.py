# -*- coding: utf-8 -*-
"""写歌工具与 Claude 智能体接入的离线回归测试。

全部用例使用临时数据库与临时 FIONA_SONG_DIR；供应商流用
``test_claude_agent_runtime`` 的 FakeStream，不访问真实网络。
"""
import asyncio
import json
import re
import socket
import sqlite3
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from test_claude_agent_runtime import FakeStream, call, harness, message, run

# 在 harness 夹具替换之前保留生产实现，用来验证 ChatState 的 song_project_id
# 确实由 _save_response 传给了 save_message。
from services.chat_service import _save_response as _REAL_SAVE_RESPONSE


@pytest.fixture(autouse=True)
def song_dir(tmp_path, monkeypatch):
    """每个用例都指定临时音频目录，仓库里不产生任何文件。"""
    path = tmp_path / "song_data"
    monkeypatch.setenv("FIONA_SONG_DIR", str(path))
    return path


@pytest.fixture(autouse=True)
def song_switch_off(monkeypatch):
    """默认关闭写歌；需要正控的用例在自己的用例体里显式打开。"""
    monkeypatch.delenv("FIONA_SONG_AGENT", raising=False)


@pytest.fixture(autouse=True)
def idle_song_poller(monkeypatch):
    """即使某个用例打开开关，也不会真的启动无限轮询器。"""
    try:
        from song import jobs as song_jobs
    except Exception:
        return

    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(song_jobs, "run_poller", idle)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """禁止真实 TCP / DNS，只放行回环地址。"""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def is_loopback(host):
        if isinstance(host, bytes):
            host = host.decode("ascii", errors="replace")
        return isinstance(host, str) and host.lower() in {"127.0.0.1", "::1", "localhost"}

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not (
            isinstance(address, tuple) and address and is_loopback(address[0])
        ):
            raise AssertionError("写歌智能体测试禁止真实网络连接")
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not (
            isinstance(address, tuple) and address and is_loopback(address[0])
        ):
            raise AssertionError("写歌智能体测试禁止真实网络连接")
        return original_connect_ex(sock, address)

    def guarded_resolution(host, *args, **kwargs):
        if not is_loopback(host):
            raise AssertionError("写歌智能体测试禁止真实 DNS 查询")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_resolution)


@pytest.fixture
def song_db(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "song.db"))
    asyncio.run(database.init_db())
    return tmp_path / "song.db"


BRIEF = {
    "theme": "写给朋友的生日歌",
    "occasion": "生日",
    "recipient": "小夏",
    "language": "Chinese",
    "duration_seconds": 120,
    "gender": "Female",
    "genre": ["Pop", "Folk"],
    "genre_extra": ["Chinese Pop"],
    "mood": ["Happy"],
    "timbre": ["Warm"],
    "key": "C",
    "kmode": "Major",
    "tempo": "Moderato",
    "instrument": ["Guitar"],
    "scene": ["Birthday"],
    "style_notes": "轻快一些",
}

STRUCTURE = [
    {"id": "s1", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
    {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
]

SECTIONS = [
    {"id": "s1", "type": "verse", "lines": ["风吹过山岗", "云落在远方"]},
    {"id": "s2", "type": "chorus", "lines": ["我们一起唱", "唱到天亮"]},
]


def _brief(**overrides):
    value = json.loads(json.dumps(BRIEF))
    value.update(overrides)
    return value


async def _new_conversation(username="owner"):
    import agent_store
    import database

    await database.get_or_create_user(username)
    conversation = await agent_store.create_conversation(username)
    return conversation["id"]


async def _seed_project(username, conversation_id, *, title="夏日信", with_lyrics=True):
    from song import lyrics_check, store

    project = await store.create_project(
        owner_username=username,
        conversation_id=conversation_id,
        title=title,
        brief=_brief(),
        structure=STRUCTURE,
    )
    if with_lyrics:
        check = lyrics_check.check_lyrics(STRUCTURE, SECTIONS, "Chinese")
        await store.save_lyrics(
            project["id"],
            owner_username=username,
            conversation_id=conversation_id,
            base_revision=0,
            sections=SECTIONS,
            check=check,
            changed_section_ids=[],
        )
    return project["id"]


def _save_brief_args(*, project_id=None, **overrides):
    args = {
        "title": "夏日信",
        "brief": _brief(),
        "structure": json.loads(json.dumps(STRUCTURE)),
    }
    args.update(overrides)
    if project_id is not None:
        args["project_id"] = project_id
    return args


def _run_tool(name, args, *, user="owner", conversation_id, context=None):
    from song import tools

    context = {} if context is None else context
    text = asyncio.run(
        tools.execute(
            name,
            args,
            ctx=NS(user=user),
            conversation_id=conversation_id,
            context=context,
        )
    )
    return text, context


def _project_count():
    import database

    with sqlite3.connect(database.DB_PATH) as db:
        return db.execute("SELECT COUNT(*) FROM song_projects").fetchone()[0]


# ────────────────────────── 工具单测 ──────────────────────────


def test_song_tool_schemas_use_volc_options():
    from song import lyrics_check, tools, volc_options

    assert tools.SONG_TOOL_NAMES == {
        "song_save_brief", "song_save_lyrics", "song_revise_section", "song_get_status",
    }
    by_name = {tool["name"]: tool for tool in tools.SONG_TOOLS}
    brief = by_name["song_save_brief"]["input_schema"]["properties"]["brief"]["properties"]
    assert brief["genre"]["items"]["enum"] == list(volc_options.GENRE_VALUES)
    assert brief["mood"]["items"]["enum"] == list(volc_options.MOOD_VALUES)
    assert brief["timbre"]["items"]["enum"] == list(volc_options.TIMBRE_VALUES)
    assert brief["language"]["enum"] == list(volc_options.LANG_VALUES)
    assert brief["key"]["enum"] == list(volc_options.KEY_VALUES)
    assert brief["kmode"]["enum"] == list(volc_options.KMODE_VALUES)
    assert brief["tempo"]["enum"] == list(volc_options.TEMPO_VALUES)
    assert brief["instrument"]["items"]["enum"] == list(volc_options.INSTRUMENT_VALUES)
    assert brief["scene"]["items"]["enum"] == list(volc_options.SCENE_VALUES)
    structure = by_name["song_save_brief"]["input_schema"]["properties"]["structure"]["items"]
    assert structure["properties"]["type"]["enum"] == list(lyrics_check.SECTION_TYPES)


def test_save_brief_creates_then_updates_project(song_db):
    from song import store

    conversation_id = asyncio.run(_new_conversation())
    context = {}
    text, context = _run_tool(
        "song_save_brief", _save_brief_args(), conversation_id=conversation_id, context=context,
    )
    project_id = context["project_id"]
    assert "已创建写歌项目" in text
    assert project_id in text
    assert "s1 主歌 2 行 5–9 字 AABB" in text
    assert "owner" not in text and conversation_id not in text
    project = asyncio.run(
        store.get_project(project_id, owner_username="owner", conversation_id=conversation_id)
    )
    assert project["title"] == "夏日信"
    assert project["brief"]["genre"] == ["Pop", "Folk"]
    assert project["brief"]["duration_seconds"] == 120
    assert project["lyrics_revision"] == 0

    updated = _save_brief_args(
        project_id=project_id,
        title="夏日信（新版）",
        brief=_brief(theme="改成写给自己", mood=["Calm/Relaxing"]),
        structure=json.loads(json.dumps(STRUCTURE)),
    )
    context = {}
    text, context = _run_tool(
        "song_save_brief", updated, conversation_id=conversation_id, context=context,
    )
    assert "已更新写歌项目" in text
    assert context["project_id"] == project_id
    project = asyncio.run(
        store.get_project(project_id, owner_username="owner", conversation_id=conversation_id)
    )
    assert project["title"] == "夏日信（新版）"
    assert project["brief"]["theme"] == "改成写给自己"
    assert project["brief"]["mood"] == ["Calm/Relaxing"]
    assert project["lyrics_revision"] == 0


def test_save_brief_rechecks_existing_lyrics_on_structure_change(song_db):
    from song import store

    conversation_id = asyncio.run(_new_conversation())
    project_id = asyncio.run(_seed_project("owner", conversation_id))
    before = asyncio.run(store.get_lyrics(project_id, 1))
    assert before["revision"] == 1
    assert before["check"]["ok"] is True

    # 删掉 s1，只保留 chorus；结构本身合法，但旧歌词多出 s1。
    structure = [
        {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "AABB"},
    ]
    text, context = _run_tool(
        "song_save_brief",
        _save_brief_args(project_id=project_id, structure=structure),
        conversation_id=conversation_id,
        context={},
    )
    assert "已按新结构重检第 2 稿" in text
    assert context["project_id"] == project_id

    latest = asyncio.run(store.get_lyrics(project_id))
    assert latest["revision"] == 2
    assert latest["check"]["ok"] is False
    assert "structure_mismatch" in [item["code"] for item in latest["check"]["errors"]]

    # 第 1 稿保持原样，没有被重检覆盖。
    first = asyncio.run(store.get_lyrics(project_id, 1))
    assert first == before

    project = asyncio.run(
        store.get_project(project_id, owner_username="owner", conversation_id=conversation_id)
    )
    assert project["lyrics_revision"] == 2


def test_save_brief_language_change_rechecks_lyrics(song_db):
    from song import lyrics_check, store

    conversation_id = asyncio.run(_new_conversation())
    structure = [
        {"id": "s1", "type": "verse", "lines": 12, "chars": [1, 30], "rhyme": "free"},
        {"id": "s2", "type": "chorus", "lines": 12, "chars": [1, 30], "rhyme": "free"},
    ]
    # 每行 30 个拉丁字母是一个英文单词：英文规则不超长，中文规则会超总长。
    long_lines = ["a" * 30 for _ in range(12)]
    sections = [
        {"id": "s1", "lines": list(long_lines)},
        {"id": "s2", "lines": list(long_lines)},
    ]
    project = asyncio.run(
        store.create_project(
            owner_username="owner",
            conversation_id=conversation_id,
            title="Summer Letter",
            brief=_brief(language="English"),
            structure=structure,
        )
    )
    base_check = lyrics_check.check_lyrics(structure, sections, "English")
    assert base_check["ok"] is True
    assert base_check["provider_chars"] < 2000
    saved = asyncio.run(
        store.save_lyrics(
            project["id"],
            owner_username="owner",
            conversation_id=conversation_id,
            base_revision=0,
            sections=sections,
            check=base_check,
            changed_section_ids=[],
        )
    )
    assert saved["status"] == "ok"

    text, context = _run_tool(
        "song_save_brief",
        {
            "project_id": project["id"],
            "title": "Summer Letter",
            "brief": _brief(language="Chinese"),
            "structure": json.loads(json.dumps(structure)),
        },
        conversation_id=conversation_id,
        context={},
    )
    assert "已按新结构重检第 2 稿" in text
    assert context["project_id"] == project["id"]

    latest = asyncio.run(store.get_lyrics(project["id"]))
    assert latest["revision"] == 2
    assert latest["check"]["ok"] is False
    assert "too_long" in [item["code"] for item in latest["check"]["errors"]]
    assert latest["check"]["provider_chars"] > 700


def test_save_brief_rejects_invalid_enum_without_creating_project(song_db):
    conversation_id = asyncio.run(_new_conversation())
    context = {}
    text, context = _run_tool(
        "song_save_brief",
        _save_brief_args(brief=_brief(genre=["NotAGenre"])),
        conversation_id=conversation_id,
        context=context,
    )
    assert "没有保存" in text and "曲风" in text
    assert context == {}
    assert _project_count() == 0


def test_save_brief_rejects_structure_without_chorus(song_db):
    conversation_id = asyncio.run(_new_conversation())
    context = {}
    text, context = _run_tool(
        "song_save_brief",
        _save_brief_args(structure=[{"id": "s1", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "AABB"}]),
        conversation_id=conversation_id,
        context=context,
    )
    assert "没有保存" in text
    assert "chorus" in text
    assert context == {}
    assert _project_count() == 0


def test_save_lyrics_success_and_base_conflict(song_db):
    from song import store

    conversation_id = asyncio.run(_new_conversation())
    _, context = _run_tool(
        "song_save_brief", _save_brief_args(), conversation_id=conversation_id, context={},
    )
    project_id = context["project_id"]

    context = {}
    text, context = _run_tool(
        "song_save_lyrics",
        {
            "project_id": project_id,
            "base_revision": 0,
            "sections": [{"id": "s1", "lines": SECTIONS[0]["lines"]}, {"id": "s2", "lines": SECTIONS[1]["lines"]}],
        },
        conversation_id=conversation_id,
        context=context,
    )
    assert "第 1 稿" in text and "自检：通过" in text
    assert context["project_id"] == project_id
    lyrics = asyncio.run(store.get_lyrics(project_id))
    assert lyrics["revision"] == 1
    assert [section["type"] for section in lyrics["sections"]] == ["verse", "chorus"]
    assert lyrics["check"]["ok"] is True
    assert lyrics["check"]["errors"] == []

    conflict_context = {}
    text, conflict_context = _run_tool(
        "song_save_lyrics",
        {
            "project_id": project_id,
            "base_revision": 0,
            "sections": [{"id": "s1", "lines": ["另一个版本"]}, {"id": "s2", "lines": ["另一个副歌"]}],
        },
        conversation_id=conversation_id,
        context=conflict_context,
    )
    assert text == "歌词已被更新，请先调用 song_get_status"
    assert conflict_context == {}
    assert asyncio.run(store.get_lyrics(project_id))["revision"] == 1


def test_revise_section_only_changes_one_section(song_db):
    from song import store

    conversation_id = asyncio.run(_new_conversation())
    project_id = asyncio.run(_seed_project("owner", conversation_id))
    before = asyncio.run(store.get_lyrics(project_id))

    context = {}
    text, context = _run_tool(
        "song_revise_section",
        {
            "project_id": project_id,
            "base_revision": 1,
            "section_id": "s1",
            "lines": ["风轻轻吹过山岗", "云慢慢落向远方"],
            "reason": "主语再柔和一点",
        },
        conversation_id=conversation_id,
        context=context,
    )
    assert "第 2 稿" in text and "只修改了 主歌 s1" in text
    assert "【修改前】" in text and "【修改后】" in text
    assert context["project_id"] == project_id

    after = asyncio.run(store.get_lyrics(project_id))
    assert after["revision"] == 2
    assert after["changed_section_ids"] == ["s1"]
    after_by_id = {section["id"]: section for section in after["sections"]}
    before_by_id = {section["id"]: section for section in before["sections"]}
    assert after_by_id["s2"] == before_by_id["s2"]
    assert after_by_id["s1"]["lines"] == ["风轻轻吹过山岗", "云慢慢落向远方"]
    assert after["check"]["ok"] is True

    # 不存在的段落
    text, context = _run_tool(
        "song_revise_section",
        {
            "project_id": project_id,
            "base_revision": 2,
            "section_id": "s9",
            "lines": ["没有这个段落"],
        },
        conversation_id=conversation_id,
        context={},
    )
    assert "结构蓝图里没有段落" in text
    assert asyncio.run(store.get_lyrics(project_id))["revision"] == 2

    # 旧稿号冲突
    text, context = _run_tool(
        "song_revise_section",
        {
            "project_id": project_id,
            "base_revision": 1,
            "section_id": "s1",
            "lines": ["过期修改"],
        },
        conversation_id=conversation_id,
        context={},
    )
    assert text == "歌词已被更新，请先调用 song_get_status"
    assert asyncio.run(store.get_lyrics(project_id))["revision"] == 2


@pytest.mark.parametrize("target", ["s2", "s4"])
def test_revise_section_preserves_every_other_section(song_db, target):
    from song import lyrics_check, store

    conversation_id = asyncio.run(_new_conversation())
    structure = [
        {"id": "s1", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "free"},
        {"id": "s2", "type": "chorus", "lines": 2, "chars": [5, 9], "rhyme": "free"},
        {"id": "s3", "type": "inst", "lines": 0},
        {"id": "s4", "type": "verse", "lines": 2, "chars": [5, 9], "rhyme": "free"},
    ]
    sections = [
        {"id": "s1", "type": "verse", "lines": ["第一段第一句", "第一段第二句"]},
        {"id": "s2", "type": "chorus", "lines": ["副歌第一句", "副歌第二句"]},
        {"id": "s3", "type": "inst", "lines": []},
        {"id": "s4", "type": "verse", "lines": ["最后一段一", "最后一段二"]},
    ]
    project = asyncio.run(
        store.create_project(
            owner_username="owner",
            conversation_id=conversation_id,
            title="四段测试",
            brief=_brief(),
            structure=structure,
        )
    )
    base_check = lyrics_check.check_lyrics(structure, sections, "Chinese")
    assert base_check["ok"] is True
    saved = asyncio.run(
        store.save_lyrics(
            project["id"],
            owner_username="owner",
            conversation_id=conversation_id,
            base_revision=0,
            sections=sections,
            check=base_check,
            changed_section_ids=[],
        )
    )
    assert saved["status"] == "ok"
    project_id = project["id"]
    before = asyncio.run(store.get_lyrics(project_id, 1))
    assert before["revision"] == 1

    new_lines = {
        "s2": ["换过的副歌一", "换过的副歌二"],
        "s4": ["换过的结尾一", "换过的结尾二"],
    }[target]
    text, context = _run_tool(
        "song_revise_section",
        {
            "project_id": project_id,
            "base_revision": 1,
            "section_id": target,
            "lines": new_lines,
            "reason": "只换这一段",
        },
        conversation_id=conversation_id,
        context={},
    )
    assert "第 2 稿" in text
    assert context["project_id"] == project_id

    after = asyncio.run(store.get_lyrics(project_id, 2))
    assert after["revision"] == 2
    assert after["changed_section_ids"] == [target]
    before_by_id = {section["id"]: section for section in before["sections"]}
    after_by_id = {section["id"]: section for section in after["sections"]}
    assert set(after_by_id) == {"s1", "s2", "s3", "s4"}
    assert after_by_id[target]["lines"] == new_lines
    assert after_by_id[target]["type"] == before_by_id[target]["type"]

    # 除目标段外的每一段都必须逐项保留；器乐段也必须仍是空列表。
    for section_id in ("s1", "s2", "s3", "s4"):
        if section_id == target:
            continue
        assert after_by_id[section_id]["lines"] == before_by_id[section_id]["lines"]
    assert after_by_id["s3"]["lines"] == []

    # 基础稿本身不能被改写。
    reread = asyncio.run(store.get_lyrics(project_id, 1))
    assert reread["sections"] == before["sections"]


def _insert_version(project_id, owner, *, status, created_at, audio_rel_path="deadbeef.mp3"):
    import database

    version_id = uuid4().hex
    with sqlite3.connect(database.DB_PATH) as db:
        db.execute(
            """INSERT INTO song_versions
                   (id, project_id, owner_username, lyrics_revision, provider, params_json,
                    status, progress, strawberries, billing_state, idempotency_key,
                    audio_rel_path, duration_s, created_day, created_at)
               VALUES (?, ?, ?, 1, 'volc', '{"Lyrics":"SECRET_PARAMS"}', ?, 100, 30,
                       'settled', ?, ?, 180.5, '2026-10-18', ?)""",
            (version_id, project_id, owner, status, uuid4().hex, audio_rel_path, created_at),
        )
    return version_id


def test_get_status_lists_recent_versions_without_audio_or_params(song_db):
    conversation_id = asyncio.run(_new_conversation())
    project_id = asyncio.run(_seed_project("owner", conversation_id, title="测试歌"))
    _insert_version(project_id, "owner", status="succeeded", created_at="2026-10-18 10:01:00")
    _insert_version(project_id, "owner", status="failed", created_at="2026-10-18 10:02:00")
    _insert_version(project_id, "owner", status="queued", created_at="2026-10-18 10:03:00")
    _insert_version(project_id, "owner", status="rejected", created_at="2026-10-18 10:04:00")

    context = {}
    text, context = _run_tool(
        "song_get_status", {"project_id": project_id}, conversation_id=conversation_id, context=context,
    )
    assert context["project_id"] == project_id
    assert "标题：《测试歌》" in text
    assert "最新稿号：第 1 稿" in text
    assert "风吹过山岗" in text
    assert "owner" not in text and conversation_id not in text
    assert "最近版本：" in text
    assert "rejected" in text and "queued" in text and "failed" in text
    # 最多 3 个版本，最早的成功版本不出现。
    assert "succeeded" not in text
    assert "deadbeef.mp3" not in text
    assert "SECRET_PARAMS" not in text and "Lyrics" not in text


def test_projects_are_scoped_to_owner_and_conversation(song_db):
    from song import store

    conversation_id = asyncio.run(_new_conversation())
    project_id = asyncio.run(_seed_project("owner", conversation_id))

    other_conversation = asyncio.run(_new_conversation("other"))
    for user, conversation in (("intruder", conversation_id), ("owner", other_conversation)):
        context = {}
        text, context = _run_tool(
            "song_get_status", {"project_id": project_id}, user=user,
            conversation_id=conversation, context=context,
        )
        assert text == "找不到这个写歌项目"
        assert context == {}

        context = {}
        text, context = _run_tool(
            "song_revise_section",
            {
                "project_id": project_id,
                "base_revision": 1,
                "section_id": "s1",
                "lines": ["不应该被写入"],
            },
            user=user,
            conversation_id=conversation,
            context=context,
        )
        assert text == "找不到这个写歌项目"
        assert context == {}

        context = {}
        text, context = _run_tool(
            "song_save_brief",
            _save_brief_args(project_id=project_id, title="越权改名"),
            user=user,
            conversation_id=conversation,
            context=context,
        )
        assert text == "找不到这个写歌项目"
        assert context == {}

    project = asyncio.run(
        store.get_project(project_id, owner_username="owner", conversation_id=conversation_id)
    )
    assert project["title"] == "夏日信"
    assert asyncio.run(store.get_lyrics(project_id))["revision"] == 1


# ────────────────────────── Claude 智能体接入 ──────────────────────────


def test_switch_off_has_zero_impact_on_claude_turn(harness, monkeypatch):
    import services.chat_service as chat
    import services.claude_agent as agent

    monkeypatch.setenv("FIONA_CLAUDE_AGENT", "0")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")
    monkeypatch.delenv("FIONA_SONG_AGENT", raising=False)

    h = harness
    assert agent.client_tools_for_turn(h.ctx, h.state) is agent.CLAUDE_CLIENT_TOOLS
    h.streams.append(FakeStream(message(text="普通回复"), "普通回复"))
    events = run(h)

    request, kwargs = h.requests[0]
    assert kwargs["tools"] is agent.CLAUDE_CLIENT_TOOLS
    assert {tool["name"] for tool in kwargs["tools"]} == {
        "get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image",
    }
    system = request[0]["content"]
    assert "【写歌模式】" not in system
    blocks = request[-1]["content"]
    assert [block["type"] for block in blocks] == ["text", "text"]
    assert blocks[0]["text"].startswith("（当前北京时间：")
    assert blocks[1]["text"] == h.ctx.user_content
    assert not any(isinstance(event, dict) and event.get("card", {}).get("subtype") == "song_project" for event in events)
    assert h.state.song_project_id is None
    assert events[-1] == {"done": True}


def test_song_tools_are_not_offered_on_crisis_turns(monkeypatch):
    import services.chat_service as chat
    import services.claude_agent as agent

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")
    monkeypatch.setenv("FIONA_NOVEL_CHAT", "0")
    ctx = chat.ChatContext(
        "agent-user", "帮我写首歌", False, None, "帮我写首歌", [], 0, "persona", [],
        conversation_id="conversation",
    )
    for state in (
        chat.ChatState(trace={}, crisis=True),
        chat.ChatState(trace={}, crisis_level="possible"),
    ):
        assert agent.client_tools_for_turn(ctx, state) is agent.CLAUDE_CLIENT_TOOLS


def test_switch_off_songs_routes_404_and_no_song_poller(client, dev_headers):
    from utils import background_tasks

    task_names = {task.get_name() for task in background_tasks._background_tasks}
    assert "song-poller" not in task_names
    response = client.get("/songs/projects/not-a-project", headers=dev_headers)
    assert response.status_code == 404


def test_switch_on_changes_tools_prompt_and_user_message(song_db, harness, monkeypatch):
    import services.claude_agent as agent
    from persona import BASE_SAFETY_RULES
    from song.tools import SONG_MODE_PROMPT

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")

    h = harness
    conversation_id = asyncio.run(_new_conversation("agent-user"))
    h.ctx.conversation_id = conversation_id
    project_id = asyncio.run(_seed_project("agent-user", conversation_id, title="夏日信"))

    tools = agent.client_tools_for_turn(h.ctx, h.state)
    assert tools is not agent.CLAUDE_CLIENT_TOOLS
    assert {tool["name"] for tool in tools} == {
        "get_weather", "plan_travel", "plan_route", "get_hot_topics", "generate_image",
        "song_save_brief", "song_save_lyrics", "song_revise_section", "song_get_status",
    }

    h.streams.append(FakeStream(message(text="收到"), "收到"))
    events = run(h)

    request, kwargs = h.requests[0]
    assert {tool["name"] for tool in kwargs["tools"]} == {tool["name"] for tool in tools}
    system = request[0]["content"]
    safety = BASE_SAFETY_RULES.strip()
    assert system.rstrip().endswith(safety)
    assert system.count(safety) == 1
    assert system.count(SONG_MODE_PROMPT) == 1
    assert system.index(SONG_MODE_PROMPT) < system.rindex(safety)

    blocks = request[-1]["content"]
    assert [block["type"] for block in blocks] == ["text", "text", "text"]
    song_block = blocks[1]["text"]
    assert "本会话的写歌项目" in song_block
    assert "《夏日信》" in song_block
    assert f"id={project_id}" in song_block
    assert "最新第 1 稿" in song_block
    assert "自检 0 个问题 / 0 条提醒" in song_block
    assert "song_get_status" in song_block
    assert len(song_block) <= 300
    assert blocks[2]["text"] == h.ctx.user_content
    assert h.state.song_project_id is None
    assert events[-1] == {"done": True}


def _collect_system_texts(request):
    """收集一次模型请求里的全部 system 文本（顶层 system + 消息里的 system）。"""
    assert request and request[0]["role"] == "system"
    texts = [request[0]["content"]]
    texts.extend(entry["content"] for entry in request[1:] if entry["role"] == "system")
    return texts


def _assert_song_prompt_before_safety(system_texts):
    """写歌提示必须在安全规则之前；安全规则恰好一次，且在最后一条 system 末尾。"""
    from persona import BASE_SAFETY_RULES
    from song.tools import SONG_MODE_PROMPT

    assert system_texts
    safety = BASE_SAFETY_RULES.strip()
    joined = "\n\n".join(system_texts)
    assert joined.count(SONG_MODE_PROMPT) == 1
    assert joined.count(safety) == 1
    assert system_texts[-1].rstrip().endswith(safety)
    assert joined.index(SONG_MODE_PROMPT) < joined.index(safety)


def test_song_mode_prompt_stays_before_trailing_safety_rules(song_db, harness, monkeypatch):
    from persona import BASE_SAFETY_RULES
    from song.tools import SONG_MODE_PROMPT

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")

    h = harness
    # 真实 persona 提示末尾已经带一次基础安全规则，_final_system_prompt 会去掉后重放。
    h.ctx.system_prompt = "人设提示\n\n" + BASE_SAFETY_RULES.strip()
    assert h.ctx.messages[-1]["role"] == "user"

    h.streams.append(FakeStream(message(text="收到"), "收到"))
    events = run(h)

    system_texts = _collect_system_texts(h.requests[0][0])
    assert len(system_texts) == 1
    _assert_song_prompt_before_safety(system_texts)
    assert system_texts[0].count("【写歌模式】") == 1
    assert events[-1] == {"done": True}


def test_song_mode_prompt_stays_before_trailing_system_safety(song_db, harness, monkeypatch):
    import services.chat_service as chat
    from persona import BASE_SAFETY_RULES
    from song.tools import SONG_MODE_PROMPT

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")

    h = harness
    safety = BASE_SAFETY_RULES.strip()
    h.ctx.system_prompt = "人设提示\n\n" + safety
    trailing = "尾随规则\n\n" + safety
    h.ctx.messages = [
        {"role": "user", "content": "帮我写首歌"},
        {"role": "system", "content": trailing},
    ]
    assert chat._has_trailing_system(h.ctx) is True

    h.streams.append(FakeStream(message(text="收到"), "收到"))
    run(h)

    system_texts = _collect_system_texts(h.requests[0][0])
    assert len(system_texts) == 2
    assert system_texts[-1] == trailing
    _assert_song_prompt_before_safety(system_texts)
    assert system_texts[0].count(SONG_MODE_PROMPT) == 1


def test_layout_check_rejects_song_prompt_appended_after_safety(song_db, harness, monkeypatch):
    import services.chat_service as chat
    from persona import BASE_SAFETY_RULES
    from song.tools import SONG_MODE_PROMPT

    safety = BASE_SAFETY_RULES.strip()
    # 旧实现的错误拼法：先得到以安全规则结尾的最终提示，再把写歌提示追到后面。
    wrong = chat._final_system_prompt("人设提示\n\n" + safety) + "\n\n" + SONG_MODE_PROMPT
    with pytest.raises(AssertionError):
        _assert_song_prompt_before_safety([wrong])

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")
    h = harness
    h.ctx.system_prompt = "人设提示\n\n" + safety
    h.streams.append(FakeStream(message(text="收到"), "收到"))
    run(h)

    _assert_song_prompt_before_safety(_collect_system_texts(h.requests[0][0]))


def test_full_fake_stream_dispatches_song_tools_and_delivers_one_card(song_db, harness, monkeypatch):
    import database
    from song import store

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")

    h = harness
    conversation_id = asyncio.run(_new_conversation("agent-user"))
    h.ctx.conversation_id = conversation_id

    saves = []

    async def save(ctx_, state_, image_path=None):
        saves.append((state_.full_response, state_.song_project_id))
        await _REAL_SAVE_RESPONSE(ctx_, state_, image_path=image_path)

    h.monkeypatch.setattr(h.chat, "_save_response", save)

    brief_args = _save_brief_args()
    lyrics_args = {
        "base_revision": 0,
        "sections": [
            {"id": "s1", "lines": SECTIONS[0]["lines"]},
            {"id": "s2", "lines": SECTIONS[1]["lines"]},
        ],
    }
    lyrics_stream = FakeStream(
        message("tool_use", content=[call("song_save_lyrics", lyrics_args, "song-2")]),
        "歌词写好了。",
    )
    h.streams.extend([
        FakeStream(message("tool_use", content=[call("song_save_brief", brief_args, "song-1")]), "我先保存简报。"),
        lyrics_stream,
        FakeStream(message(text="都准备好了，请确认。"), "都准备好了，请确认。"),
    ])

    # 模拟模型把 song_save_brief 返回的项目 id 填进下一次工具调用。
    base_open = h.agent.open_agent_stream

    def open_stream(config, messages, **kwargs):
        if h.streams and h.streams[0] is lyrics_stream:
            tool_result = messages[-1]["content"][0]["content"]
            match = re.search(r"id=([0-9a-f]{32})", tool_result)
            assert match, tool_result
            lyrics_args["project_id"] = match.group(1)
        return base_open(config, messages, **kwargs)

    h.monkeypatch.setattr(h.agent, "open_agent_stream", open_stream)
    events = run(h)

    with sqlite3.connect(database.DB_PATH) as db:
        project_id = db.execute("SELECT id FROM song_projects").fetchone()[0]

    cards = [
        event["card"] for event in events
        if isinstance(event, dict) and isinstance(event.get("card"), dict)
        and event["card"].get("subtype") == "song_project"
    ]
    assert len(cards) == 1
    card = cards[0]
    assert card["project_id"] == project_id
    assert card["source"] == "写歌"
    assert card["points"] == ["《夏日信》第 1 稿"]
    assert card["error"] is False
    assert {"card": card, "append": True} in events
    assert h.state.song_project_id == project_id
    assert saves and saves[0][1] == project_id
    assert "［卡片：" in saves[0][0] and "《夏日信》第 1 稿" in saves[0][0]
    assert h.state.billable is False
    assert h.state.trace["agent_tools"] == ["song_save_brief", "song_save_lyrics"]
    assert h.state.trace["agent_tool_errors"] == 0

    lyrics = asyncio.run(store.get_lyrics(project_id))
    assert lyrics["revision"] == 1
    project = asyncio.run(
        store.get_project(project_id, owner_username="agent-user", conversation_id=conversation_id)
    )
    assert project["title"] == "夏日信"

    with sqlite3.connect(database.DB_PATH) as db:
        row = db.execute(
            "SELECT song_project_id FROM messages WHERE username = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
            ("agent-user",),
        ).fetchone()
    assert row is not None and row[0] == project_id


def test_mirror_turn_does_not_add_song_mode_prompt(song_db, harness, monkeypatch):
    """R2：镜子轮不拼写歌提示，system 与写歌关闭时逐字节相同。"""
    from song.tools import SONG_MODE_PROMPT

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")

    h = harness
    conversation_id = asyncio.run(_new_conversation("agent-user"))
    h.ctx.conversation_id = conversation_id
    asyncio.run(_seed_project("agent-user", conversation_id, title="镜子测试"))

    h.monkeypatch.setattr(h.chat, "detect_mode", lambda *args: "mirror")
    systems = []

    async def mirror(ctx, state):
        systems.append(state.sys_prompt_final)
        yield h.chat._sse({"text": "mirror"})
        yield h.chat._sse({"done": True})

    h.monkeypatch.setattr(h.chat, "stream_mirror", mirror)
    assert run(h) == [{"text": "mirror"}, {"done": True}]
    song_on_system = systems[-1]
    assert "【写歌模式】" not in song_on_system
    assert SONG_MODE_PROMPT not in song_on_system
    assert not h.requests

    # 同一 harness、同一输入，只把开关关掉：system 文本必须逐字节相同。
    monkeypatch.setenv("FIONA_SONG_AGENT", "0")
    assert run(h) == [{"text": "mirror"}, {"done": True}]
    assert systems[-1] == song_on_system
    assert not h.requests


def test_friend_turn_with_song_on_contains_mode_prompt_once(song_db, harness, monkeypatch):
    """正控：同样的写歌开关下，friend 轮确实带上写歌提示恰好一次。"""
    from song.tools import SONG_MODE_PROMPT

    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "agent-user")

    h = harness
    h.monkeypatch.setattr(h.chat, "detect_mode", lambda *args: "friend")
    h.streams.append(FakeStream(message(text="收到"), "收到"))
    events = run(h)

    system_texts = _collect_system_texts(h.requests[0][0])
    assert "【写歌模式】" in system_texts[0]
    assert sum(text.count(SONG_MODE_PROMPT) for text in system_texts) == 1
    assert events[-1] == {"done": True}

