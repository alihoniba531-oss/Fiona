"""R2 decision/privacy regression contracts; both SDKs and all networking are stubbed."""
import asyncio
import json
import logging
import socket
import sqlite3
from types import SimpleNamespace as NS

import pytest


@pytest.fixture(scope="module", autouse=True)
def module_offline():
    def forbidden(*args, **kwargs):
        raise AssertionError("R2 service tests forbid real socket/DNS requests")

    with pytest.MonkeyPatch.context() as patch:
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
            patch.setattr(socket, name, forbidden)
        for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
            original = getattr(socket.socket, name)

            def guarded(sock, *args, _original=original, **kwargs):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    forbidden()
                return _original(sock, *args, **kwargs)

            patch.setattr(socket.socket, name, guarded)
        yield


@pytest.fixture
def service(monkeypatch):
    from services import local_watch

    def forbidden(*args, **kwargs):
        raise AssertionError("Every model request must use an offline stub")

    monkeypatch.setattr(local_watch, "QWEN_CLIENT", NS(with_options=forbidden))
    monkeypatch.setattr(local_watch.byok_client.anthropic, "Anthropic", forbidden)
    monkeypatch.setattr(local_watch, "check_watch_daily_cap", lambda username: False)
    return local_watch


def model_stub(service, monkeypatch, model, decision, *, debug=False):
    """Run the real platform/BYOK adapters, including their privacy context."""
    text = json.dumps(decision, ensure_ascii=False)

    def create(**kwargs):
        if debug:
            logger = "openai._base_client" if model == "platform" else "anthropic._base_client"
            logging.getLogger(logger).debug("request=%s response=%s", kwargs, text)
        if model == "platform":
            return NS(choices=[NS(message=NS(content=text))])
        return NS(content=[NS(type="text", text=text)])

    if model == "platform":
        derived = NS(chat=NS(completions=NS(create=create)))
        monkeypatch.setattr(service, "QWEN_CLIENT", NS(with_options=lambda **kwargs: derived))
    else:
        async def config(username):
            return {
                "enabled": True, "provider": "anthropic", "status": "ok",
                "api_key": "offline-r2-key", "model": "claude-sonnet-5-5",
            }

        monkeypatch.setattr(service.byok_store, "get_internal_config", config)
        monkeypatch.setattr(
            service.byok_client.anthropic, "Anthropic",
            lambda **kwargs: NS(messages=NS(create=create), close=lambda: None),
        )


def ai_rule(model):
    return {
        "name": "R2 判断", "app_match": "Terminal", "title_match": "", "kind": "ai",
        "params": {"condition": "下载完成时提醒", "model": model},
        "interval_seconds": 3, "cooldown_seconds": 60, "enabled": True,
        "conversation_id": None,
    }


@pytest.mark.parametrize("model", ["platform", "claude"])
@pytest.mark.parametrize("summary", ["", "  \n ", "长" * 1000, None, 42, ["任意内容"], {"任意": "内容"}])
def test_false_decision_is_success_and_ignores_summary(client, service, monkeypatch, caplog, model, summary):
    import database

    caplog.set_level(logging.DEBUG)
    asyncio.run(database.get_or_create_user("r2-negative"))
    rule = asyncio.run(database.create_watch_rule("r2-negative", ai_rule(model)))
    model_stub(service, monkeypatch, model, {"alert": False, "summary": summary}, debug=True)
    failure = []
    assert asyncio.run(service.judge_ai("r2-negative", rule["params"], ["R2_PRIVATE_OCR"], failure=failure)) == {"alert": False}
    assert failure == []
    assert asyncio.run(service.process_observation("r2-negative", rule, ["R2_PRIVATE_OCR"])) == {"alert": False}
    assert not [record for record in caplog.records if record.name == service.__name__ and record.levelno >= logging.WARNING]
    assert "local_watch rule_id=" in caplog.text
    with sqlite3.connect(database.DB_PATH) as db:
        success, payload = db.execute("SELECT success,payload FROM events WHERE event_type='local_watch'").fetchone()
        assert db.execute("SELECT COUNT(*) FROM watch_alerts").fetchone()[0] == 0
    assert success == 1
    assert json.loads(payload)["alert"] is False
    assert "exception_type" not in json.loads(payload)
    assert "R2_PRIVATE_OCR" not in caplog.text + payload


def test_false_decision_does_not_require_summary(service):
    assert service._parse_decision('{"alert":false}') == {"alert": False}


@pytest.mark.parametrize("model", ["platform", "claude"])
@pytest.mark.parametrize("summary", ["", " \n ", "长" * 81, None])
def test_true_decision_invalid_summary_remains_failure(client, service, monkeypatch, caplog, model, summary):
    import database

    caplog.set_level(logging.DEBUG)
    asyncio.run(database.get_or_create_user("r2-invalid-positive"))
    rule = asyncio.run(database.create_watch_rule("r2-invalid-positive", ai_rule(model)))
    model_stub(service, monkeypatch, model, {"alert": True, "summary": summary}, debug=True)
    assert asyncio.run(service.process_observation("r2-invalid-positive", rule, ["R2_INVALID_PRIVATE_OCR"])) == {"alert": False}
    assert "local_watch exception_type=ValueError" in caplog.text
    with sqlite3.connect(database.DB_PATH) as db:
        success, payload = db.execute("SELECT success,payload FROM events WHERE event_type='local_watch'").fetchone()
    assert success == 0
    assert json.loads(payload)["exception_type"] == "ValueError"
    assert "R2_INVALID_PRIVATE_OCR" not in caplog.text + payload


@pytest.mark.parametrize("alert", [0, 1, "false", "true", None, [], {}])
def test_alert_remains_strict_boolean(service, alert):
    with pytest.raises(ValueError, match="Invalid watch decision"):
        service._parse_decision(json.dumps({"alert": alert, "summary": "ignored"}))


@pytest.mark.parametrize("sign", ["−", "－", "﹣", "‒", "–"])
@pytest.mark.parametrize("digits", ["5.2%", "５．２％"])
def test_unicode_negative_signs_and_fullwidth_numbers_preserve_sign(service, sign, digits):
    line = "涨幅 " + sign + digits
    assert service.number_decision({"label": "涨幅", "op": ">=", "threshold": 3}, [line]) is None
    assert service.number_decision({"label": "涨幅", "op": "<=", "threshold": -3}, [line]) == "涨幅 当前 -5.2%，已 <= -3"
    assert service.number_decision({"label": "涨幅", "op": "<=", "threshold": -5.2}, [line]) is not None
    assert service.number_decision({"label": "涨幅", "op": ">=", "threshold": -5.2}, [line]) is not None
    assert service.number_decision({"label": "涨幅", "op": "<", "threshold": -5.2}, [line]) is None
    assert service.number_decision({"label": "涨幅", "op": ">", "threshold": -5.2}, [line]) is None


@pytest.mark.parametrize("raw,value", [
    ("−.５％", "-0.5%"), ("＋５．２％", "5.2%"), ("１２３．４５", "123.45"),
    ("１，２３４．５０％", "1234.5%"), ("1,234.50%", "1234.5%"), ("-1,234,567.89", "-1234567.89"),
    ("1,2345", "1"), ("1,2345.67", "1"), ("1,23,456", "1"), ("1,234,56", "1"),
    ("1,234,5678", "1"), ("1234,567", "1234"), ("-1,2345", "-1"), ("123,4567", "123"),
    ("1,234, 后续", "1234"), ("1,2345 后续 9", "1"),
])
def test_thousands_groups_must_be_complete_without_swallowing_digits(service, raw, value):
    params = {"label": "价格", "op": ">=", "threshold": -2000000}
    assert service.number_decision(params, ["价格 " + raw]) == f"价格 当前 {value}，已 >= -2000000"


def assert_private_metadata_only(logs, events, secrets):
    for secret in secrets:
        assert secret not in logs + str(events), f"private watch text leaked: {secret}"


@pytest.mark.parametrize("model", ["platform", "claude"])
def test_privacy_assertion_positive_control_then_real_processing(client, service, monkeypatch, caplog, model):
    import database

    caplog.set_level(logging.DEBUG)
    secrets = ("R2_OCR_POSITIVE_CONTROL_PRIVATE", "R2_SUMMARY_POSITIVE_CONTROL_PRIVATE")
    # Use the exact assertion below before production, proving it detects a leak.
    logging.getLogger("r2.privacy_positive_control").warning("OCR=%s summary=%s", *secrets)
    with pytest.raises(AssertionError, match="private watch text leaked"):
        assert_private_metadata_only(caplog.text, [], secrets)
    caplog.clear()

    asyncio.run(database.get_or_create_user("r2-privacy"))
    rule = asyncio.run(database.create_watch_rule("r2-privacy", ai_rule(model)))
    model_stub(service, monkeypatch, model, {"alert": True, "summary": secrets[1]}, debug=True)
    assert asyncio.run(service.process_observation("r2-privacy", rule, [secrets[0]]))["alert"] is True
    with sqlite3.connect(database.DB_PATH) as db:
        events = db.execute("SELECT success,payload FROM events WHERE event_type='local_watch'").fetchall()
    assert_private_metadata_only(caplog.text, events, secrets)
    assert "local_watch rule_id=" in caplog.text
    assert len(events) == 1 and events[0][0] == 1
    payload = json.loads(events[0][1])
    assert set(payload) == {"rule_id", "kind", "alert", "elapsed_ms"}
    assert payload["kind"] == "ai" and payload["alert"] is True
