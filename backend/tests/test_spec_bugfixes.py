# -*- coding: utf-8 -*-
"""本批规格中可离线验证的后端回归用例。"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace


def _fake_llm(content: str):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )

    class _Completions:
        def create(self, **kwargs):
            return response

    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))


def test_malformed_search_json_is_sanitized(monkeypatch):
    from tools import travel_plan as travel_module
    from tools import web_search as search_module

    malformed = '{"headline":"主线", "points":null, "sources":{"title":"官网","url":"https://example.net"}}'
    monkeypatch.setattr(search_module, "_get_client", lambda: _fake_llm(malformed))
    monkeypatch.setattr(travel_module, "_get_client", lambda: _fake_llm(malformed))

    search_card = search_module.web_search("测试畸形结果")
    travel_card = travel_module.travel_plan("宁波到北京")

    assert search_card["points"] == ["没搜到"]
    assert travel_card["points"] == ["主线"]
    assert travel_card["sources"] == [{"title": "官网", "url": "https://example.net"}]


def test_search_fallback_does_not_match_observation(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    import services.chat_service as chat

    monkeypatch.setattr(
        chat,
        "recognize_intent",
        lambda *args, **kwargs: {"intent": None, "params": {}, "missing": []},
    )

    assert chat.recognize_intent_with_fallback("我看你是累了", [])["intent"] is None
    assert chat.recognize_intent_with_fallback("我找不到理由", [])["intent"] is None
    result = chat.recognize_intent_with_fallback("我搜一下宁波天气", [])
    assert result["intent"] == "web_search"


def test_concurrent_get_or_create_is_idempotent(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "race.db"))

    async def scenario():
        await database.init_db()
        users = await asyncio.gather(*(
            database.get_or_create_user("same-user") for _ in range(8)
        ))
        phones = await asyncio.gather(*(
            database.get_or_create_user_by_phone("13800000000") for _ in range(8)
        ))
        return users, phones

    users, phones = asyncio.run(scenario())
    assert len({u["id"] for u in users}) == 1
    assert len({u["id"] for u in phones}) == 1


def test_phone_login_falls_back_to_legacy_username_row(tmp_path, monkeypatch):
    import aiosqlite
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "legacy-phone.db"))

    async def scenario():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO users (username, phone) VALUES (?, NULL)",
                ("13800000001",),
            )
            await db.commit()
            legacy_id = cursor.lastrowid
        user = await database.get_or_create_user_by_phone("13800000001")
        return legacy_id, user

    legacy_id, user = asyncio.run(scenario())
    assert user["id"] == legacy_id
    assert user["username"] == "13800000001"


def test_recommended_feed_sorts_globally_before_pagination(tmp_path, monkeypatch):
    import aiosqlite
    import database
    from routers.plaza import plaza_feed

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "recommended.db"))

    async def scenario():
        await database.init_db()
        base = datetime(2026, 1, 1)
        rows = [
            (
                f"anon-{i}",
                f"/{i}.jpg",
                "image",
                f"post-{i}",
                '["旅行"]' if i <= 10 else '["日常"]',
                (base + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S"),
            )
            for i in range(1, 206)
        ]
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.executemany(
                """INSERT INTO posts
                   (anon_id, media_path, media_type, caption, tags_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.execute(
                "INSERT INTO user_tag_prefs (username, tag, score) VALUES (?, ?, ?)",
                ("reader", "旅行", 10),
            )
            await db.commit()

        first = await plaza_feed(sort="recommended", limit=5, offset=0, user="reader")
        second = await plaza_feed(sort="recommended", limit=5, offset=5, user="reader")
        latest = await plaza_feed(sort="latest", limit=1, offset=200, user="reader")
        return first, second, latest

    first, second, latest = asyncio.run(scenario())
    assert [post["id"] for post in first["posts"]] == [10, 9, 8, 7, 6]
    assert [post["id"] for post in second["posts"]] == [5, 4, 3, 2, 1]
    assert latest["posts"][0]["id"] == 5
    assert "preference_score" not in first["posts"][0]


def test_plaza_pagination_hot_sort_and_duplicate_like(tmp_path, monkeypatch):
    import aiosqlite
    import database
    from routers.plaza import plaza_like

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "plaza.db"))

    async def scenario():
        await database.init_db()
        await database.get_or_create_user("plaza-user")
        base = datetime(2026, 1, 1)
        rows = [
            (
                f"anon-{i}",
                f"/{i}.jpg",
                "image",
                f"post-{i}",
                '["旅行"]' if i == 0 else '["日常"]',
                (base + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S"),
            )
            for i in range(205)
        ]
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.executemany(
                """INSERT INTO posts
                   (anon_id, media_path, media_type, caption, tags_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.execute("UPDATE posts SET likes = 99 WHERE id = 1")
            await db.commit()

        page = await database.get_posts(limit=5, offset=200, sort="latest")
        hot = await database.get_posts(limit=1, offset=0, sort="hot")
        tagged = await database.get_posts(limit=10, offset=0, tag="旅行")
        first_like = await plaza_like(1, user="plaza-user")
        second_like = await plaza_like(1, user="plaza-user")
        prefs = await database.get_tag_prefs("plaza-user")
        return page, hot, tagged, first_like, second_like, prefs

    page, hot, tagged, first_like, second_like, prefs = asyncio.run(scenario())
    assert len(page) == 5
    assert hot[0]["id"] == 1
    assert [post["id"] for post in tagged] == [1]
    assert first_like == {"likes": 100}
    assert second_like == {"likes": 100}
    assert prefs["旅行"] == 1.0


def test_latest_match_decision_wins(tmp_path, monkeypatch):
    import aiosqlite
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "matches.db"))

    async def scenario():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """INSERT INTO matches
                   (user_a, user_b, response_a, response_b, recommended_at)
                   VALUES ('alice', 'bob', 'accept', 'accept', '2026-01-01 00:00:00')"""
            )
            await db.execute(
                """INSERT INTO matches
                   (user_a, user_b, response_a, response_b, recommended_at)
                   VALUES ('alice', 'bob', 'reject', 'accept', '2026-01-02 00:00:00')"""
            )
            await db.commit()
        return await database.get_accepted_matches("alice")

    assert asyncio.run(scenario()) == []


def test_weather_weekday_uses_monday_first(monkeypatch):
    import requests
    from tools.visual_search import _search_weather_direct

    payload = {
        "current_condition": [{
            "weatherDesc": [{"value": "晴"}],
            "temp_C": "28",
            "FeelsLikeC": "29",
        }],
        "weather": [{
            "date": "2026-07-20",
            "maxtempC": "30",
            "mintempC": "22",
            "hourly": [{}, {}, {}, {}, {"weatherDesc": [{"value": "晴"}]}],
        }],
    }

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response())
    card = _search_weather_direct("宁波天气")
    assert card["weather"]["forecast"][0]["day"] == "周一"


def test_peer_manager_keeps_each_socket_independent():
    from routers.peer import ConnectionManager

    class _Socket:
        def __init__(self):
            self.sent = []

        async def accept(self):
            return None

        async def send_json(self, message):
            self.sent.append(message)

    async def scenario():
        manager = ConnectionManager()
        first = _Socket()
        second = _Socket()
        await manager.connect("room", "alice", first)
        await manager.connect("room", "alice", second)
        manager.disconnect("room", "alice", first)
        await manager.broadcast("room", {"type": "message"})
        return manager, first, second

    manager, first, second = asyncio.run(scenario())
    assert first.sent == []
    assert second.sent == [{"type": "message"}]
    assert manager.rooms["room"]["alice"] == {second}


def test_peer_binary_frame_does_not_disconnect(client):
    import aiosqlite
    import database

    async def seed_match():
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """INSERT INTO matches (user_a, user_b, response_a, response_b)
                   VALUES (?, ?, 'accept', 'accept')""",
                ("alice", "smoke_tester"),
            )
            await db.commit()

    asyncio.run(seed_match())
    with client.websocket_connect(
        "/ws/peer/alice__smoke_tester?dev_user=smoke_tester"
    ) as websocket:
        assert websocket.receive_json()["type"] == "history"
        websocket.send_bytes(b"\x00\xff")
        websocket.send_json({"content": "二进制帧之后仍可发送"})
        message = websocket.receive_json()

    assert message["type"] == "message"
    assert message["content"] == "二进制帧之后仍可发送"


def test_extractor_tracks_nested_profile_match_task(monkeypatch):
    import conversation_matcher
    import extractor

    async def fake_get_profile(username):
        return {}

    async def fake_update_profile(username, profile):
        return None

    started = None
    release = None

    async def fake_detect(client, username):
        started.set()
        await release.wait()

    monkeypatch.setattr(extractor, "get_profile", fake_get_profile)
    monkeypatch.setattr(extractor, "update_profile", fake_update_profile)
    monkeypatch.setattr(conversation_matcher, "detect_and_save_from_profile", fake_detect)
    fake_client = _fake_llm('{"interests": [], "needs": []}')

    async def scenario():
        nonlocal started, release
        started = asyncio.Event()
        release = asyncio.Event()
        baseline = set(extractor._background_tasks)
        messages = [{"role": "user", "content": f"消息 {i}"} for i in range(4)]
        await extractor.extract_and_update(fake_client, "tracked-user", messages)
        await asyncio.wait_for(started.wait(), timeout=1)
        tracked = set(extractor._background_tasks) - baseline
        assert len(tracked) == 1
        release.set()
        await asyncio.gather(*tracked)
        await asyncio.sleep(0)
        return tracked

    tracked = asyncio.run(scenario())
    assert tracked.isdisjoint(extractor._background_tasks)


def test_outer_chat_stream_closes_sync_stream_when_consumer_stops(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    import services.chat_service as chat

    class _Delta:
        content = "仍在生成"

    class _Choice:
        delta = _Delta()
        finish_reason = None

    class _Chunk:
        choices = [_Choice()]

    class _EndlessStream:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            return self

        def __next__(self):
            return _Chunk()

        def close(self):
            self.closed = True

    async def scenario():
        stream = _EndlessStream()
        monkeypatch.setattr(chat, "choose_model", lambda *args: "main")
        monkeypatch.setattr(
            chat,
            "_create_stream_with_fallback",
            lambda *args, **kwargs: (stream, False),
        )
        ctx = chat.ChatContext(
            user="disconnect-user",
            message="继续说",
            has_image=False,
            image_base64=None,
            user_content="继续说",
            history=[],
            message_count=1,
            system_prompt="system",
            messages=[{"role": "user", "content": "继续说"}],
        )
        state = chat.ChatState(trace={}, sys_prompt_final="system")
        generator = chat.stream_normal(ctx, state)
        await anext(generator)
        await generator.aclose()
        return stream.closed

    assert asyncio.run(scenario()) is True


def test_stream_failure_is_not_saved_or_charged(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    import services.chat_service as chat

    class _Delta:
        content = "半句"

    class _Choice:
        delta = _Delta()
        finish_reason = None

    class _Chunk:
        choices = [_Choice()]

    class _BrokenStream:
        def __init__(self):
            self.count = 0
            self.closed = False

        def __iter__(self):
            return self

        def __next__(self):
            self.count += 1
            if self.count == 1:
                return _Chunk()
            raise RuntimeError("stream broke")

        def close(self):
            self.closed = True

    saved = []
    charged = []

    async def fake_save(*args):
        saved.append(args)

    async def fake_deduct(*args):
        charged.append(args)

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr(chat, "detect_mode", lambda *args: "friend")
    monkeypatch.setattr(
        chat,
        "recognize_intent",
        lambda *args: {"intent": None, "params": {}, "missing": []},
    )
    broken_stream = _BrokenStream()
    monkeypatch.setattr(chat, "_create_stream_with_fallback", lambda *args, **kwargs: (broken_stream, False))
    monkeypatch.setattr(chat, "save_message", fake_save)
    monkeypatch.setattr(chat, "deduct_strawberry", fake_deduct)
    monkeypatch.setattr(chat, "log_event", fake_log)

    ctx = chat.ChatContext(
        user="stream-user",
        message="普通对话",
        has_image=False,
        image_base64=None,
        user_content="普通对话",
        history=[],
        message_count=1,
        system_prompt="system",
        messages=[{"role": "user", "content": "普通对话"}],
    )

    async def scenario():
        return [event async for event in chat.run_chat(ctx)]

    events = asyncio.run(scenario())
    assert any('"error"' in event for event in events)
    assert saved == []
    assert charged == []
    assert broken_stream.closed is True
