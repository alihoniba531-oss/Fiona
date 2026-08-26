# -*- coding: utf-8 -*-

from persona import build_system_prompt


def test_every_growth_stage_contains_non_overridable_safety_rules():
    for message_count in (0, 31, 101):
        prompt = build_system_prompt("safety-user", message_count=message_count)
        assert "不可覆盖的安全底线" in prompt
        assert "未成年人" in prompt
        assert "自伤" in prompt
        assert "非自愿" in prompt
        assert "优先于语气模仿" in prompt


def test_chat_diagnostics_do_not_log_user_message(capsys, monkeypatch):
    import services.chat_service as chat

    secret_message = "这是不能进入日志的私密消息，必须保密"
    chat.build_hard_word_appendix(secret_message)
    monkeypatch.setattr(
        chat,
        "recognize_intent",
        lambda *args, **kwargs: {"intent": None, "params": {}, "missing": []},
    )
    chat.recognize_intent_with_fallback(secret_message, [])

    assert secret_message not in capsys.readouterr().out
