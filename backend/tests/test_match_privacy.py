# -*- coding: utf-8 -*-
import asyncio
import json

from utils.match_privacy import minimized_match_profile


def test_minimized_profile_drops_sensitive_fields():
    result = minimized_match_profile({
        "interests": ["骑行"],
        "skills": ["摄影"],
        "struggles": ["SECRET_STRUGGLE"],
        "needs": ["SECRET_NEED"],
        "special_dates": ["01-01 SECRET_DATE"],
        "occupation": "SECRET_JOB",
        "city": "上海",
    })
    serialized = json.dumps(result, ensure_ascii=False)
    assert result == {"interests": ["骑行"], "skills": ["摄影"], "city": "上海"}
    assert "SECRET" not in serialized


def test_conversation_candidates_never_read_raw_peer_messages(monkeypatch):
    import conversation_matcher as matcher

    async def get_profiles():
        return [{
            "username": "bob",
            "gender": "male",
            "profile": {"interests": ["骑行"], "struggles": ["RAW_PRIVATE_MESSAGE"]},
        }]

    async def get_settings(username):
        return {
            "alice": {"gender": "female", "match_pref": "male"},
            "bob": {"gender": "male", "match_pref": "female"},
        }[username]

    async def not_recent(*args, **kwargs):
        return False

    monkeypatch.setattr(matcher, "get_all_profiles", get_profiles)
    monkeypatch.setattr(matcher, "get_user_settings", get_settings)
    monkeypatch.setattr(matcher, "was_recently_matched", not_recent)
    candidates = asyncio.run(matcher.find_cross_user_candidates("alice", ["骑行"]))
    assert len(candidates) == 1
    assert "RAW_PRIVATE_MESSAGE" not in json.dumps(candidates, ensure_ascii=False)


def test_match_evaluator_sanitizes_defensively_before_llm():
    import conversation_matcher as matcher

    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            content = json.dumps({
                "role_compatible": True,
                "should_recommend": True,
                "type": "话题连接",
                "reason": "都喜欢骑行",
                "tags": ["骑行"],
            }, ensure_ascii=False)
            return type("Response", (), {
                "choices": [type("Choice", (), {
                    "message": type("Message", (), {"content": content})(),
                })()],
            })()

    client = type("Client", (), {
        "chat": type("Chat", (), {"completions": _Completions()})(),
    })()
    candidate = {
        "peer_username": "bob",
        "peer_profile": {"interests": ["骑行"], "struggles": ["RAW_PRIVATE_MESSAGE"]},
        "hit_topics": ["骑行"],
    }
    result = asyncio.run(matcher.evaluate_match(client, "alice", "骑行", candidate))
    prompt = captured["messages"][1]["content"]
    assert result is not None
    assert "RAW_PRIVATE_MESSAGE" not in prompt
