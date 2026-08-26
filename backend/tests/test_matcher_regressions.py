# -*- coding: utf-8 -*-
import asyncio
import json


def test_layer2_creates_cards_for_both_users(monkeypatch):
    import conversation_matcher as matcher

    async def fake_profile(username):
        return {
            "interests": ["骑行"],
            "values": ["自由"],
            "needs": ["伙伴"],
        }

    async def no_recent(*args, **kwargs):
        return False

    async def candidates(*args, **kwargs):
        return [{
            "peer_username": "bob",
            "peer_profile": {"interests": ["骑行"]},
            "score": 4,
            "match_reasons": ["共同兴趣"],
        }]

    async def evaluate(*args, **kwargs):
        return {"type": "话题连接", "reason": "都在认真骑车", "tags": ["骑行"]}

    pending_calls = []
    match_calls = []

    async def save_pending(**kwargs):
        pending_calls.append(kwargs)

    async def save_pair(user_a, user_b):
        match_calls.append((user_a, user_b))

    monkeypatch.setattr(matcher, "get_profile", fake_profile)
    monkeypatch.setattr(matcher, "_has_recent_layer2_match", no_recent)
    monkeypatch.setattr(matcher, "find_profile_candidates", candidates)
    monkeypatch.setattr(matcher, "evaluate_profile_match", evaluate)
    monkeypatch.setattr(matcher, "save_pending_match", save_pending)
    monkeypatch.setattr(matcher, "save_match", save_pair)

    saved = asyncio.run(matcher.detect_and_save_from_profile(object(), "alice"))

    assert saved == 1
    assert [(call["username"], call["peer_username"]) for call in pending_calls] == [
        ("alice", "bob"),
        ("bob", "alice"),
    ]
    assert all(call["match_layer"] == "layer2" for call in pending_calls)
    assert pending_calls[1]["reason"] == "Chloe觉得你们可能聊得来"
    assert match_calls == [("alice", "bob")]


def test_candidate_requires_both_users_preferences(monkeypatch):
    import conversation_matcher as matcher

    profiles = [{
        "username": "bob",
        "profile": {"interests": ["骑行"]},
        "gender": "male",
    }]
    settings = {
        "alice": {"gender": "female", "match_pref": "male"},
        # Bob 只接受男性，因此不能推荐给女性 Alice。
        "bob": {"gender": "male", "match_pref": "male"},
    }

    async def get_settings(username):
        return settings[username].copy()

    async def get_profiles():
        return profiles

    async def not_recent(*args, **kwargs):
        return False

    monkeypatch.setattr(matcher, "get_user_settings", get_settings)
    monkeypatch.setattr(matcher, "get_all_profiles", get_profiles)
    monkeypatch.setattr(matcher, "was_recently_matched", not_recent)

    regular = asyncio.run(matcher.find_cross_user_candidates("alice", ["骑行"]))
    profile = asyncio.run(
        matcher.find_profile_candidates(
            "alice",
            {"interests": ["骑行"], "values": ["自由"], "needs": ["伙伴"]},
        )
    )
    seeking = asyncio.run(
        matcher.find_seeking_candidates(
            "alice",
            "female",
            {"seeking_gender": "male", "seeking_traits": ["骑行"]},
        )
    )

    assert regular == []
    assert profile == []
    assert seeking == []


def test_candidate_is_allowed_when_preferences_are_mutual(monkeypatch):
    import conversation_matcher as matcher

    async def get_settings(username):
        return {
            "alice": {"gender": "female", "match_pref": "male"},
            "bob": {"gender": "male", "match_pref": "female"},
        }[username].copy()

    monkeypatch.setattr(matcher, "get_user_settings", get_settings)
    assert asyncio.run(
        matcher._mutually_compatible(
            {"gender": "female", "match_pref": "male"},
            "bob",
            "male",
        )
    )


def test_manual_matcher_sanitizes_model_users_and_schema(monkeypatch):
    import matcher

    async def get_profile(username):
        return {"interests": ["骑行"]}

    async def get_profiles():
        return [
            {"username": "alice", "profile": {"interests": ["骑行"]}, "gender": "female"},
            {"username": "bob", "profile": {"interests": ["骑行"]}, "gender": "male"},
            {"username": "charlie", "profile": {"interests": ["露营"]}, "gender": "male"},
        ]

    async def get_settings(username):
        return {
            "alice": {"gender": "female", "match_pref": "male"},
            "bob": {"gender": "male", "match_pref": "female"},
            "charlie": {"gender": "male", "match_pref": "female"},
        }[username]

    async def not_recent(*args, **kwargs):
        return False

    saved = []

    async def save(user_a, user_b):
        saved.append((user_a, user_b))

    payload = [
        {"username": "mallory", "reason": "模型幻觉", "type": "话题连接", "tags": []},
        {"username": "bob", "reason": "  都喜欢骑行  ", "type": "话题连接", "tags": ["骑行", 3, "骑行", "周末"]},
        {"username": "bob", "reason": "重复", "type": "话题连接", "tags": []},
        {"username": "charlie", "reason": "类型非法", "type": "随便匹配", "tags": []},
    ]

    class _Completions:
        def create(self, **kwargs):
            return type("Response", (), {
                "choices": [type("Choice", (), {
                    "message": type("Message", (), {"content": json.dumps(payload, ensure_ascii=False)})(),
                })()],
            })()

    client = type("Client", (), {
        "chat": type("Chat", (), {"completions": _Completions()})(),
    })()

    monkeypatch.setattr(matcher, "get_profile", get_profile)
    monkeypatch.setattr(matcher, "get_all_profiles", get_profiles)
    monkeypatch.setattr(matcher, "get_user_settings", get_settings)
    monkeypatch.setattr(matcher, "was_recently_matched", not_recent)
    monkeypatch.setattr(matcher, "save_match", save)

    results = asyncio.run(matcher.find_matches(client, "alice"))

    assert results == [{
        "username": "bob",
        "reason": "都喜欢骑行",
        "type": "话题连接",
        "tags": ["骑行", "周末"],
    }]
    assert saved == [("alice", "bob")]


def test_manual_matcher_filters_non_mutual_preferences_before_llm(monkeypatch):
    import matcher

    async def get_profile(username):
        return {"interests": ["骑行"]}

    async def get_profiles():
        return [{"username": "bob", "profile": {"interests": ["骑行"]}, "gender": "male"}]

    async def get_settings(username):
        return {
            "alice": {"gender": "female", "match_pref": "male"},
            "bob": {"gender": "male", "match_pref": "male"},
        }[username]

    async def not_recent(*args, **kwargs):
        return False

    class _MustNotRun:
        def create(self, **kwargs):
            raise AssertionError("LLM must not run without mutually compatible candidates")

    client = type("Client", (), {
        "chat": type("Chat", (), {"completions": _MustNotRun()})(),
    })()

    monkeypatch.setattr(matcher, "get_profile", get_profile)
    monkeypatch.setattr(matcher, "get_all_profiles", get_profiles)
    monkeypatch.setattr(matcher, "get_user_settings", get_settings)
    monkeypatch.setattr(matcher, "was_recently_matched", not_recent)

    assert asyncio.run(matcher.find_matches(client, "alice")) == []
