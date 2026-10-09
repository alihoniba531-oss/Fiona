"""高德 MCP、天气卡和城市规范化的离线契约测试。"""
import json
import socket
import urllib.error
import urllib.request

import pytest
import requests

from tools import amap_mcp
from tools.weather import weather
from utils import safe_http
from utils.city_name import normalize_city


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(safe_http, "_open_pinned", blocked)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "  test-amap-key  ")
    monkeypatch.setenv("FIONA_AMAP_ENABLED", "1")
    monkeypatch.setenv("FIONA_AMAP_TIMEOUT_SECONDS", "8")
    yield
    assert not attempted, "network"


class FakeResponse:
    def __init__(self, payload, content_type="application/json;charset=utf-8"):
        self.payload = payload
        self.headers = {"Content-Type": content_type}
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size):
        self.read_sizes.append(size)
        return self.payload[:size]


def _rpc(request_id, text='{"city":"杭州市","forecasts":[]}', **result):
    return {"jsonrpc": "2.0", "id": request_id, "result": {
        "content": [{"type": "text", "text": text}], "isError": False, **result,
    }}


def _stub_response(monkeypatch, build, *, content_type="application/json;charset=utf-8"):
    calls, responses = [], []

    def fake_urlopen(request, *, timeout):
        body = json.loads(request.data)
        calls.append((request, timeout, body))
        payload = build(body["id"])
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        response = FakeResponse(payload, content_type)
        responses.append(response)
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls, responses


def test_request_contract_and_unique_ids(monkeypatch):
    monkeypatch.setenv("FIONA_AMAP_MCP_URL", "https://untrusted.example.org/")
    calls, responses = _stub_response(monkeypatch, _rpc)

    assert amap_mcp.call_tool("maps_weather", {"city": "杭州"}) == {
        "ok": True, "data": {"city": "杭州市", "forecasts": []},
    }
    assert amap_mcp.call_tool("maps_weather", {"city": "宁波"})["ok"] is True
    assert len(calls) == 2
    for request, timeout, body in calls:
        assert request.full_url == amap_mcp.AMAP_MCP_URL
        assert request.get_method() == "POST"
        headers = {key.lower(): value for key, value in request.header_items()}
        assert headers == {
            "authorization": "Bearer test-amap-key",
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        }
        assert body["jsonrpc"] == "2.0"
        assert body["method"] == "tools/call"
        assert body["params"]["name"] == "maps_weather"
        assert type(body["id"]) is int
        assert 0 < timeout <= 8
    assert calls[0][2]["params"]["arguments"] == {"city": "杭州"}
    assert calls[1][2]["params"]["arguments"] == {"city": "宁波"}
    assert calls[0][2]["id"] != calls[1][2]["id"]
    assert all(response.read_sizes == [amap_mcp.MAX_RESPONSE_BYTES + 1] for response in responses)


def test_sse_supports_comments_multiline_no_space_and_matching_id(monkeypatch):
    def payload(request_id):
        return (f': a comment\r\nevent: message\r\ndata:{json.dumps(_rpc(request_id + 1))}\r\n\r\n'
                f': another comment\r\ndata:{{"jsonrpc":"2.0", "id":{request_id},\r\n'
                'data: "result":{"content":[{"type":"text","text":"{\\"city\\":\\"杭州\\"}"}]}}\r\n\r\n'
                f'data:{json.dumps(_rpc(request_id, text="ignored later matching event"))}\r\n\r\n').encode("utf-8")

    _stub_response(monkeypatch, payload, content_type="text/event-stream;charset=utf-8")
    assert amap_mcp.call_tool("maps_weather", {"city": "杭州"}) == {"ok": True, "data": {"city": "杭州"}}


@pytest.mark.parametrize("text,data", [("plain tool result", "plain tool result"),
                                       ("null", None), ("[1,2]", [1, 2]), ("12", 12)])
def test_text_result_json_or_plain_string(monkeypatch, text, data):
    _stub_response(monkeypatch, lambda request_id: _rpc(request_id, text))
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": True, "data": data}


@pytest.mark.parametrize("build,error", [
    (lambda request_id: _rpc(request_id, "API 调用失败：USER_DAILY_QUERY_OVER_LIMIT", isError=True), "quota"),
    (lambda request_id: _rpc(request_id, "API 调用失败：ENGINE_RESPONSE_DATA_ERROR", isError=True), "tool_error"),
    (lambda request_id: {"id": request_id, "error": {"code": -32603, "message": "private error"}}, "rpc_error"),
    (lambda request_id: b"{bad json", "bad_response"),
    (lambda request_id: b"\xff", "bad_response"),
    (lambda request_id: [], "bad_response"),
    (lambda request_id: _rpc(request_id + 1), "bad_response"),
    (lambda request_id: {"id": request_id, "result": {}}, "bad_response"),
    (lambda request_id: {"id": request_id, "result": None}, "bad_response"),
    (lambda request_id: _rpc(request_id, content=[]), "bad_response"),
    (lambda request_id: _rpc(request_id, content=[{"type": "image", "data": "private"}]), "bad_response"),
    (lambda request_id: _rpc(request_id, content=[{"type": "text"}]), "bad_response"),
    (lambda request_id: _rpc(request_id, content=[{"type": "text", "text": None},
                                                {"type": "text", "text": "later text"}]), "bad_response"),
    (lambda request_id: b"x" * (amap_mcp.MAX_RESPONSE_BYTES + 1), "too_large"),
])
def test_response_failures_are_fixed_error_codes(monkeypatch, build, error):
    _stub_response(monkeypatch, build)
    assert amap_mcp.call_tool("maps_weather", {"city": "杭州"}) == {"ok": False, "error": error}


def test_sse_without_matching_id_is_bad_response(monkeypatch):
    _stub_response(monkeypatch, lambda request_id: (
        f"data:{json.dumps(_rpc(request_id + 1))}\n\ndata:broken\n\n".encode("utf-8")
    ), content_type="text/event-stream")
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": False, "error": "bad_response"}


@pytest.mark.parametrize("status,error", [(401, "auth"), (403, "auth"),
                                         (404, "not_enabled"), (500, "http")])
def test_http_errors_never_read_body(monkeypatch, status, error):
    class Unreadable:
        def read(self, *args):
            pytest.fail("HTTP error body must not be read")

        def close(self):
            return None

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(amap_mcp.AMAP_MCP_URL, status, "private supplier text", {}, Unreadable())

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": False, "error": error}


@pytest.mark.parametrize("exception,error", [
    (socket.timeout("private timeout detail"), "timeout"),
    (TimeoutError("private timeout detail"), "timeout"),
    (urllib.error.URLError(socket.timeout("private timeout detail")), "timeout"),
    (urllib.error.URLError(TimeoutError("private timeout detail")), "timeout"),
    (urllib.error.URLError("private network failure"), "exception"),
    (ValueError("private exceptional detail"), "exception"),
])
def test_network_exception_mapping(monkeypatch, exception, error):
    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": False, "error": error}


def test_read_finished_after_total_budget_is_timeout(monkeypatch):
    _stub_response(monkeypatch, _rpc)
    times = iter([10, 10.2, 18.1, 18.2])
    monkeypatch.setattr(amap_mcp.time, "perf_counter", lambda: next(times))
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": False, "error": "timeout"}


def test_exhausted_budget_does_not_open_network(monkeypatch):
    times = iter([10, 19, 19.1])
    monkeypatch.setattr(amap_mcp.time, "perf_counter", lambda: next(times))
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": False, "error": "timeout"}


@pytest.mark.parametrize("enabled,key,error", [("0", "test", "disabled"),
                                               ("1", "", "missing_key"),
                                               ("1", " \t\n", "missing_key")])
def test_local_configuration_failures_do_not_request(monkeypatch, enabled, key, error):
    monkeypatch.setenv("FIONA_AMAP_ENABLED", enabled)
    monkeypatch.setenv("DASHSCOPE_API_KEY", key)
    assert amap_mcp.call_tool("maps_weather", {}) == {"ok": False, "error": error}


@pytest.mark.parametrize("enabled", ["", "false", "broken", " 0", "0 ", "1"])
def test_only_literal_zero_disables(monkeypatch, enabled):
    monkeypatch.setenv("FIONA_AMAP_ENABLED", enabled)
    calls, _ = _stub_response(monkeypatch, _rpc)
    assert amap_mcp.call_tool("maps_weather", {})["ok"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("raw,expected", [("nan", 8), ("inf", 8), ("", 8), ("broken", 8),
                                         ("0.99", 8), ("30.01", 8), ("-2", 8),
                                         ("1", 1), ("30", 30), ("3.5", 3.5)])
def test_timeout_configuration_fallback(monkeypatch, raw, expected):
    monkeypatch.setenv("FIONA_AMAP_TIMEOUT_SECONDS", raw)
    assert amap_mcp._timeout_seconds() == expected
    calls, _ = _stub_response(monkeypatch, _rpc)
    assert amap_mcp.call_tool("maps_weather", {})["ok"] is True
    assert 0 < calls[0][1] <= expected


def test_failure_logs_omit_city_arguments_and_supplier_text(monkeypatch, capsys):
    city, supplier = "独特隐私城市标记", "独特供应商响应原文"
    _stub_response(monkeypatch, lambda request_id: _rpc(request_id, supplier, isError=True))
    assert amap_mcp.call_tool("maps_weather", {"city": city}) == {"ok": False, "error": "tool_error"}
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    assert output.startswith("[amap-mcp] failed tool=maps_weather kind=tool_error ms=")
    assert city not in output
    assert supplier not in output
    assert "arguments" not in output


def _day(**overrides):
    return {"date": "2026-10-09", "week": "7", "dayweather": "晴", "nightweather": "小雨",
            "daytemp": "26", "nighttemp": "17", "daywind": "东", "nightwind": "东北",
            "daypower": "1-3", "nightpower": "3-4", "daytemp_float": "999.0", **overrides}


def _weather_stub(monkeypatch, data):
    calls = []

    def call_tool(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "data": data}

    monkeypatch.setattr(amap_mcp, "call_tool", call_tool)
    return calls


def test_weather_real_shape_and_monday_first_date(monkeypatch):
    days = [_day(date=value) for value in ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"]]
    calls = _weather_stub(monkeypatch, {"city": "杭州市", "forecasts": days})
    card = weather("查一下杭州的天气吧")
    assert calls == [("maps_weather", {"city": "杭州"})]
    assert card == {
        "type": "card", "subtype": "weather", "source": "天气 · 杭州市", "points": [], "error": False,
        "weather": {"location": "杭州市", "forecast": [
            {"date": value, "day": day, "dayWeather": "晴", "nightWeather": "小雨",
             "high": "26", "low": "17", "dayWind": "东风 1-3级", "nightWind": "东北风 3-4级"}
            for value, day in zip(["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23"],
                                  ["周一", "周二", "周三", "周四"])
        ]},
    }


def test_weather_fields_validated_truncated_and_missing_wind_parts(monkeypatch):
    _weather_stub(monkeypatch, {"city": "城" * 30, "forecasts": [
        _day(dayweather="晴" * 30, nightweather=123, daytemp="1" * 25,
             nighttemp="not-numeric", daywind="东", daypower=None, nightwind=None, nightpower="1-3"),
        _day(date="2026-10-10", daywind=None, daypower=None, nightwind="北" * 30, nightpower="2" * 30,
             daytemp=22, nighttemp="NaN"),
    ]})
    card = weather("杭州")
    assert card["weather"]["location"] == "城" * 20
    first, second = card["weather"]["forecast"]
    assert first["dayWeather"] == "晴" * 20
    assert first["nightWeather"] == ""
    assert first["high"] == "1" * 20
    assert first["low"] == ""
    assert first["dayWind"] == "东风"
    assert first["nightWind"] == "1-3级"
    assert second["dayWind"] == ""
    assert second["high"] == second["low"] == ""
    assert all(len(value) <= 20 for item in card["weather"]["forecast"] for value in item.values())


@pytest.mark.parametrize("data", [None, "private result", [], {"city": None, "forecasts": None},
                                  {"forecasts": []}, {"forecasts": "x"},
                                  {"forecasts": [_day(date="2026-02-30"), _day(date="2026-7-20"), None, {}]}])
def test_weather_not_found_error_card_without_subtype(monkeypatch, data):
    _weather_stub(monkeypatch, data)
    assert weather("宁波吧") == {"type": "card", "source": "天气", "error": True,
                              "points": ["没找到「宁波」的天气，换个城市名试试"]}


def test_weather_non_string_location_uses_normalized_city(monkeypatch):
    _weather_stub(monkeypatch, {"city": None, "forecasts": [_day()]})
    assert weather("在杭州")["weather"]["location"] == "杭州"


def test_weather_invalid_days_are_dropped(monkeypatch):
    _weather_stub(monkeypatch, {"city": "杭州", "forecasts": [None, _day(date="bad"), _day(), {}]})
    assert [day["date"] for day in weather("杭州")["weather"]["forecast"]] == ["2026-10-09"]


@pytest.mark.parametrize("code,reason", [
    ("disabled", "天气服务暂未开启"), ("missing_key", "天气服务暂不可用"),
    ("auth", "天气服务暂不可用"), ("not_enabled", "天气服务暂不可用"),
    ("quota", "天气服务今天的查询额度用完了，晚点再试"),
    ("timeout", "天气服务响应超时，稍后再试"),
    ("http", "天气服务暂时出错了，稍后再试"),
    ("tool_error", "天气服务暂时出错了，稍后再试"),
    ("bad_response", "天气服务暂时出错了，稍后再试"),
])
def test_weather_failure_reasons_never_expose_supplier_text(monkeypatch, code, reason):
    monkeypatch.setattr(amap_mcp, "call_tool", lambda *args: {
        "ok": False, "error": code, "data": "API 调用失败：private provider response",
    })
    assert weather("杭州") == {"type": "card", "source": "天气", "points": [reason], "error": True}


def test_weather_missing_city_does_not_call_tool(monkeypatch):
    def forbidden(*args):
        pytest.fail("invalid local city must not call MCP")

    monkeypatch.setattr(amap_mcp, "call_tool", forbidden)
    assert weather("Hangzhou") == {"type": "card", "source": "天气", "error": True,
                                  "points": ["没说是哪个城市"]}


@pytest.mark.parametrize("raw,city", [
    ("宁波吧", "宁波"), ("在杭州", "杭州"), ("查一下北京的天气", "北京"),
    ("上海市", "上海市"), ("算了", "算了"), ("帮我搜一下今天的新闻", ""),
    ("Hangzhou", ""), ("割腕", "割腕"), (" \t「换成那杭州的天气吧呢！」\n", "杭州"),
    ("是就去查一下北京啊呀的", "北京"), ("查一下，一二三四五六七八九十的天气", "一二三四五六七八九十"),
    ("一二三四五六七八九十一", ""), ("杭", ""), ("杭州123", ""), ("杭 州", ""),
    ("", ""), (None, ""), (123, ""), ("城市😀", ""),
])
def test_normalize_city_pure_shape_rules(raw, city):
    assert normalize_city(raw) == city


@pytest.mark.parametrize("city", ["来宾", "什邡", "顺义", "可克达拉", "新乡", "闻喜", "会理", "那曲"])
def test_city_sentence_rejection_preserves_real_place_names(city):
    assert normalize_city(city) == city


@pytest.mark.parametrize("text", [
    "帮我查查明天的新闻", "你觉得杭州怎么样", "告诉我北京天气", "推荐个地方", "搜索上海", "我在杭州",
])
def test_city_sentence_rejection_required_examples(text):
    assert normalize_city(text) == ""


@pytest.mark.parametrize("prefix", [
    "帮我", "帮忙", "请", "给我", "我想", "我要", "我们", "我", "你",
    "能不能", "能否", "可以", "可不可以", "怎么", "为什么", "什么", "搜",
    "再", "顺便", "另外", "还有", "告诉我", "说说", "讲讲", "看看",
])
def test_city_sentence_rejection_all_literal_prefixes_after_repeated_stripping(prefix):
    assert normalize_city(f"查一下换成那{prefix}杭州的天气吧呢") == ""


@pytest.mark.parametrize("substring", ["吗", "么", "一下", "新闻", "帮我", "搜索", "告诉", "推荐", "请问"])
def test_city_sentence_rejection_all_substrings_after_repeated_stripping(substring):
    assert normalize_city(f"在那杭州{substring}地方的天气吧呢") == ""


@pytest.mark.parametrize("raw,city", [
    ("那上海呢", "上海"), ("那曲呢", "那曲"), ("那那曲的天气吧", "那曲"),
    ("查一下那曲的天气", "那曲"), ("在杭州吧呢啊呀的", "杭州"),
    ("查曲", "查曲"), ("在京", "在京"), ("是县", "是县"),
    ("就县", "就县"), ("去县", "去县"), ("宁吧", "宁吧"), ("宁呢", "宁呢"),
    ("宁啊", "宁啊"), ("宁呀", "宁呀"), ("宁的", "宁的"),
    ("天气", "天气"), ("的天气", "的天气"),
    ("那曲啊的天气", "那曲"), ("吧呢", "吧呢"),
])
def test_city_stripping_keeps_minimum_two_characters(raw, city):
    assert normalize_city(raw) == city


@pytest.mark.parametrize("upstream_city,expected", [
    ("", "杭州"), (" \t\r\n", "杭州"), ("\u3000", "杭州"),
    (None, "杭州"), (123, "杭州"), ("  杭州市 \t", "杭州市"),
    (" 城" + "市" * 30 + " ", "城" + "市" * 19),
])
def test_weather_location_strips_upstream_city_and_falls_back_when_empty(monkeypatch, upstream_city, expected):
    _weather_stub(monkeypatch, {"city": upstream_city, "forecasts": [_day()]})
    card = weather("查一下杭州的天气")
    assert card["weather"]["location"] == expected
    assert card["source"] == f"天气 · {expected}"
    assert card["error"] is False


@pytest.mark.parametrize("line_ending", ["\r\n", "\r", "\n"])
def test_sse_preserves_literal_unicode_line_separator_in_json_string(monkeypatch, line_ending):
    data = {"city": "杭州\u2028城市"}

    def payload(request_id):
        message = _rpc(request_id, json.dumps(data, ensure_ascii=False))
        serialized = json.dumps(message, ensure_ascii=False)
        assert "\u2028" in serialized
        assert "\\u2028" not in serialized
        return f"data:{serialized}{line_ending}{line_ending}".encode("utf-8")

    _stub_response(monkeypatch, payload, content_type="text/event-stream;charset=utf-8")
    assert amap_mcp.call_tool("maps_weather", {"city": "杭州"}) == {"ok": True, "data": data}
