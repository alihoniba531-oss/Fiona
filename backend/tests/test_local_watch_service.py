"""Offline rule/AI judge contracts: SDKs always stubbed, DNS/socket blocked."""
import asyncio
import json
import logging
import socket
import sqlite3
from types import SimpleNamespace as NS
import pytest

@pytest.fixture(scope="module", autouse=True)
def module_offline():
    def forbidden(*args, **kwargs): raise AssertionError("real socket/DNS forbidden")
    with pytest.MonkeyPatch.context() as patch:
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
            patch.setattr(socket, name, forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        for name in ("bind", "listen", "sendto"):
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
    def forbidden(*args, **kwargs): raise AssertionError("model must be stubbed")
    monkeypatch.setattr(local_watch, "QWEN_CLIENT", NS(with_options=forbidden))
    monkeypatch.setattr(local_watch.byok_client.anthropic, "Anthropic", forbidden)
    return local_watch

@pytest.mark.parametrize("keywords,lines,expected", [(["Boss", "开会"], ["no", "BOSS ping"], "命中『Boss』：BOSS ping"), (["Boss", "开会"], ["今晚开会", "boss later"], "命中『开会』：今晚开会"), (["boss"], ["no match"], None), (["aa"], ["aa" + "文" * 100], "命中『aa』：" + ("aa" + "文" * 100)[:80])])
def test_keyword_first_hit_case_insensitive(service, keywords, lines, expected):
    assert service.keyword_decision({"keywords": keywords}, lines) == expected

@pytest.mark.parametrize("line,op,threshold,hit,value", [("价格 -1.5", "<", -1, True, "-1.5"), ("价格 1,234.56", ">", 1200, True, "1234.56"), ("收益 10.5%", ">=", 10.5, True, "10.5%"), ("价格 5", "<=", 5, True, "5"), ("价格 5", ">", 5, False, "5"), ("价格 -5", ">=", 0, False, "-5"), ("价格 5", "<", 5, False, "5"), ("价格 5", "<=", 4, False, "5"), ("价格暂无", ">", 1, False, ""), ("别的 999", ">", 1, False, ""), ("42 价格 .5", "<", 1, True, "0.5"), ("价格 -1,200.25 后来9", "<", -1000, True, "-1200.25")])
def test_number_formats_and_comparisons(service, line, op, threshold, hit, value):
    label = "收益" if line.startswith("收益") else "价格"
    result = service.number_decision({"label": label, "op": op, "threshold": threshold}, [line])
    assert bool(result) is hit
    if hit: assert result == f"{label} 当前 {value}，已 {op} {threshold}"

SYSTEM = '你是屏幕提醒判断器。下面是用户电脑上某个程序窗口里新出现的文字（由 OCR 识别，可能有错字）。根据用户设定的提醒条件判断现在是否需要提醒用户。只依据给出的文字判断，不要猜测看不到的内容。只输出 JSON：{"alert": true或false, "summary": "需要提醒时用一句话说明发生了什么（不超过 60 字），不需要时为空串"}'

def qwen_stub(service, monkeypatch, content, error=None, debug=False):
    calls, options, closed = [], [], []
    def create(**kwargs):
        calls.append(kwargs)
        if debug: logging.getLogger("openai._base_client").debug("Request body=%s", kwargs)
        if error: raise error
        return NS(choices=[NS(message=NS(content=content))])
    derived = NS(chat=NS(completions=NS(create=create)), close=lambda: closed.append(True))
    def with_options(**kwargs): options.append(kwargs); return derived
    monkeypatch.setattr(service, "QWEN_CLIENT", NS(with_options=with_options))
    return calls, options, closed

def test_platform_exact_parameters_and_input(service, monkeypatch):
    calls, options, closed = qwen_stub(service, monkeypatch, '{"alert":true,"summary":" 下载完成 "}')
    lines = ["a" * 1800, "b" * 1000]
    assert asyncio.run(service.judge_ai("user", {"condition": "下载完成"}, lines)) == {"alert": True, "summary": "下载完成"}
    assert options == [{"timeout": 8.0, "max_retries": 0}]
    assert calls == [{"model": "qwen3.8-flash", "stream": False, "response_format": {"type": "json_object"}, "max_tokens": 300, "extra_body": {"enable_thinking": False}, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "提醒条件：下载完成\n新出现的文字：\n" + "\n".join(lines)[:2000]}]}]
    assert closed == []

@pytest.mark.parametrize("content", ["not json", "[]", '{"alert":1,"summary":"ok"}', '{"alert":"true","summary":"ok"}', '{"alert":true,"summary":""}', '{"alert":true,"summary":"  "}', '{"alert":true,"summary":99}', json.dumps({"alert": True, "summary": "a" * 81}), '{"alert":true,"summary":"ok","x":NaN}'])
def test_invalid_ai_output_fails_closed(service, monkeypatch, content):
    qwen_stub(service, monkeypatch, content)
    assert asyncio.run(service.judge_ai("user", {"condition": "出错提醒"}, ["private"])) is None

def test_ai_exception_outer_timeout_and_debug_privacy(service, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    qwen_stub(service, monkeypatch, "", error=ValueError("SECRET_OCR_INPUT"))
    assert asyncio.run(service.judge_ai("user", {"condition": "出错提醒"}, ["SECRET_OCR_INPUT"])) is None
    assert "SECRET_OCR_INPUT" not in caplog.text
    qwen_stub(service, monkeypatch, '{"alert":true,"summary":"SECRET_ALERT_SUMMARY"}', debug=True)
    assert asyncio.run(service.judge_ai("user", {"condition": "提醒我"}, ["SECRET_OCR_INPUT"]))["summary"] == "SECRET_ALERT_SUMMARY"
    assert "SECRET_OCR_INPUT" not in caplog.text and "SECRET_ALERT_SUMMARY" not in caplog.text
    captured = []
    async def timeout(awaitable, *, timeout):
        captured.append(timeout); awaitable.close(); raise asyncio.TimeoutError("SECRET_OCR_INPUT")
    monkeypatch.setattr(service.asyncio, "wait_for", timeout)
    assert asyncio.run(service.judge_ai("user", {"condition": "出错提醒"}, ["SECRET_OCR_INPUT"])) is None
    assert captured == [8.0] and "SECRET_OCR_INPUT" not in caplog.text

@pytest.mark.parametrize("config", [None, {"enabled": False, "provider": "anthropic"}, {"enabled": True, "provider": "dashscope"}, {"enabled": True, "provider": "anthropic", "api_key": None}])
def test_claude_unavailable_never_falls_back(service, monkeypatch, config):
    async def get_config(user): return config
    monkeypatch.setattr(service.byok_store, "get_internal_config", get_config)
    assert asyncio.run(service.judge_ai("user", {"condition": "提醒我", "model": "claude"}, ["secret"])) is None

def test_claude_byok_model_nonstream_schema_no_tools(service, monkeypatch):
    calls, constructors, closed = [], [], []
    async def config(user):
        assert user == "user"
        return {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "offline-key", "status": "ok"}
    monkeypatch.setattr(service.byok_store, "get_internal_config", config)
    def create(**kwargs): calls.append(kwargs); return NS(content=[NS(type="text", text='{"alert":true,"summary":"完成了"}')])
    def client(**kwargs): constructors.append(kwargs); return NS(messages=NS(create=create), close=lambda: closed.append(True))
    monkeypatch.setattr(service.byok_client.anthropic, "Anthropic", client)
    assert asyncio.run(service.judge_ai("user", {"condition": "完成提醒", "model": "claude"}, ["Download complete"])) == {"alert": True, "summary": "完成了"}
    assert constructors[0]["api_key"] == "offline-key" and constructors[0]["timeout"] == 8.0 and constructors[0]["max_retries"] == 0
    kwargs = calls[0]
    assert kwargs["model"] == "claude-sonnet-5-5" and kwargs["max_tokens"] == 300 and kwargs["stream"] is False
    assert kwargs["system"] == SYSTEM and "tools" not in kwargs
    assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object", "properties": {"alert": {"type": "boolean"}, "summary": {"type": "string"}}, "required": ["alert", "summary"], "additionalProperties": False}}
    assert closed == [True]

def test_cooldown_and_daily_quota_even_dev_mode(client, monkeypatch, service):
    import database
    import rate_limit
    asyncio.run(database.get_or_create_user("watch_user"))
    body = {"name": "完成", "app_match": "Browser", "title_match": "", "kind": "ai", "params": {"condition": "完成提醒"}, "interval_seconds": 3, "cooldown_seconds": 60, "enabled": True, "conversation_id": None}
    item = asyncio.run(database.create_watch_rule("watch_user", body))
    calls, _, _ = qwen_stub(service, monkeypatch, '{"alert":true,"summary":"下载已完成"}')
    assert asyncio.run(service.process_observation("watch_user", item, ["done"]))["alert"] is True
    assert asyncio.run(service.process_observation("watch_user", item, ["done again"]))["alert"] is False
    assert len(calls) == 1
    with sqlite3.connect(database.DB_PATH) as connection: connection.execute("DELETE FROM watch_alerts")
    monkeypatch.setenv("FIONA_DAILY_WATCH_JUDGE", "1")
    rate_limit.limiter._storage.reset()
    qwen_stub(service, monkeypatch, '{"alert":false,"summary":"无需提醒"}')
    assert asyncio.run(service.process_observation("watch_user", item, ["one"]))["alert"] is False
    quota_calls, _, _ = qwen_stub(service, monkeypatch, '{"alert":true,"summary":"不得调用"}')
    assert asyncio.run(service.process_observation("watch_user", item, ["two"]))["alert"] is False
    assert quota_calls == []
    assert rate_limit._DAILY_SETTINGS["watch_judge"] == ("FIONA_DAILY_WATCH_JUDGE", 500)

@pytest.mark.parametrize("payload", ['{"alert":true,"summary":"bad"}', '{"alert":true,"summary":"ok"}'])
def test_claude_exception_invalid_output_and_logs(service, monkeypatch, caplog, payload):
    caplog.set_level(logging.DEBUG)
    async def config(user):
        return {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "offline-key", "status": "ok"}
    monkeypatch.setattr(service.byok_store, "get_internal_config", config)
    closed = []
    def create(**kwargs):
        logging.getLogger("anthropic._base_client").debug("private request=%s response=%s", kwargs, "SECRET_CLAUDE_SUMMARY")
        if 'bad' in payload:
            raise RuntimeError("SECRET_CLAUDE_SUMMARY")
        return NS(content=[NS(type="text", text='{"alert":1,"summary":"SECRET_CLAUDE_SUMMARY"}')])
    monkeypatch.setattr(service.byok_client.anthropic, "Anthropic", lambda **kwargs: NS(messages=NS(create=create), close=lambda: closed.append(True)))
    assert asyncio.run(service.judge_ai("user", {"condition": "完成提醒", "model": "claude"}, ["SECRET_CLAUDE_OCR"])) is None
    assert closed == [True]
    assert "SECRET_CLAUDE_OCR" not in caplog.text and "SECRET_CLAUDE_SUMMARY" not in caplog.text

def test_ai_failed_decision_trace_contains_exception_type_only(client, service, monkeypatch, caplog):
    import database
    import trace
    asyncio.run(database.get_or_create_user("watch_user"))
    body = {"name": "完成", "app_match": "Browser", "title_match": "", "kind": "ai", "params": {"condition": "完成提醒"}, "interval_seconds": 3, "cooldown_seconds": 60, "enabled": True, "conversation_id": None}
    item = asyncio.run(database.create_watch_rule("watch_user", body))
    qwen_stub(service, monkeypatch, "", error=RuntimeError("SECRET_FAILED_OCR"))
    caplog.set_level(logging.DEBUG)
    assert asyncio.run(service.process_observation("watch_user", item, ["SECRET_FAILED_OCR"])) == {"alert": False}
    with sqlite3.connect(database.DB_PATH) as connection:
        events = connection.execute("SELECT payload FROM events WHERE event_type='local_watch'").fetchall()
        assert connection.execute("SELECT COUNT(*) FROM watch_alerts").fetchone()[0] == 0
    assert events and json.loads(events[0][0])["exception_type"] == "RuntimeError"
    assert "SECRET_FAILED_OCR" not in caplog.text and "SECRET_FAILED_OCR" not in str(events)

def test_same_rule_concurrent_observations_emit_once(client, service, monkeypatch):
    import database
    asyncio.run(database.get_or_create_user("watch_user"))
    body = {"name": "完成", "app_match": "Browser", "title_match": "", "kind": "ai", "params": {"condition": "完成提醒"}, "interval_seconds": 3, "cooldown_seconds": 60, "enabled": True, "conversation_id": None}
    item = asyncio.run(database.create_watch_rule("watch_user", body))
    calls, _, _ = qwen_stub(service, monkeypatch, '{"alert":true,"summary":"下载完成"}')
    async def pair():
        return await asyncio.gather(service.process_observation("watch_user", item, ["one"]), service.process_observation("watch_user", item, ["two"]))
    results = asyncio.run(pair())
    assert sum(result["alert"] for result in results) == 1 and len(calls) == 1
    with sqlite3.connect(database.DB_PATH) as connection:
        alert = connection.execute("SELECT message_id,conversation_id FROM watch_alerts").fetchone()
        assert connection.execute("SELECT conversation_id FROM messages WHERE id=?", (alert[0],)).fetchone()[0] == alert[1]

@pytest.mark.parametrize("mutation", ["disable", "delete", "account"])
def test_ai_inflight_rule_or_account_change_discards_decision(client, service, monkeypatch, mutation):
    import database
    asyncio.run(database.get_or_create_user("watch_user"))
    body = {"name": "完成", "app_match": "Browser", "title_match": "", "kind": "ai", "params": {"condition": "完成提醒"}, "interval_seconds": 3, "cooldown_seconds": 60, "enabled": True, "conversation_id": None}
    item = asyncio.run(database.create_watch_rule("watch_user", body))
    async def pending(username, params, lines, **kwargs):
        if mutation == "disable":
            await database.update_watch_rule(username, item["id"], {**body, "enabled": False})
        elif mutation == "delete":
            await database.delete_watch_rule(username, item["id"])
        else:
            await database.delete_account_data(username)
        return {"alert": True, "summary": "旧判断不能送达"}
    monkeypatch.setattr(service, "judge_ai", pending)
    assert asyncio.run(service.process_observation("watch_user", item, ["done"])) == {"alert": False}
    with sqlite3.connect(database.DB_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM watch_alerts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM messages WHERE role='assistant'").fetchone()[0] == 0
