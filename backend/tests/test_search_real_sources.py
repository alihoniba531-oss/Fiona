"""Offline regressions for native provenance and citation-free card delivery."""
import copy
import io
import json
import re
import urllib.error
import urllib.request

import pytest
import requests

from tools import native_search, travel_plan, web_search
from utils import safe_http


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(safe_http, "_open_pinned", blocked)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-native-search-key")
    yield
    # grounded_search catches exceptions, so also detect blocked requests here.
    assert not attempted, "network"


def _source(index="1", *, url=None, title="真实报道", site_name="新闻站"):
    return {"index": index, "title": title,
            "url": url or f"https://news.example.net/articles/{index}",
            "site_name": site_name, "icon": "https://news.example.net/icon.png"}


def _payload(content=None, *, results=None, finish_reason="stop"):
    if content is None:
        content = json.dumps({"success": True, "headline": "主线方案[1]",
                              "points": ["核实的事实[1]", "出行提示[1, 2]"]}, ensure_ascii=False)
    return {"output": {
        "choices": [{"finish_reason": finish_reason, "message": {"content": content}}],
        "search_info": {"search_results": [_source()] if results is None else results},
    }}


def _stub(monkeypatch, response):
    calls = []

    def request(messages, api_key, *, max_tokens):
        calls.append((messages, api_key, max_tokens))
        return response

    monkeypatch.setattr(native_search, "_request_search", request)
    return calls


@pytest.mark.parametrize("function,max_tokens", [
    (web_search.web_search, 700), (travel_plan.travel_plan, 1200),
], ids=["web-search", "travel-plan"])
def test_sources_only_use_native_results(monkeypatch, function, max_tokens):
    data = {"success": True, "headline": "主线[1]",
            "points": [f"事实 {index}[1]" for index in range(7)],
            "url": "https://invented.example.org/page",
            "sources": [{"title": "模型编写", "url": "https://invented.example.org/source"}]}
    results = [_source(str(index), title="标题" * 60) for index in range(1, 8)]
    calls = _stub(monkeypatch, _payload(json.dumps(data, ensure_ascii=False), results=results))

    card = function("查询真实资料")

    assert card["error"] is False
    assert len(card["sources"]) == 5
    assert card["url"] == card["sources"][0]["url"]
    assert {source["url"] for source in card["sources"]}.issubset({source["url"] for source in results})
    assert all(len(source["title"]) <= 80 for source in card["sources"])
    assert all(set(source) == {"title", "url", "site_name", "index"} for source in card["sources"])
    assert "invented.example.org" not in json.dumps(card)
    assert len(card["points"]) == (5 if function is web_search.web_search else 6)
    assert len(calls) == 1
    assert calls[0][1:] == ("test-native-search-key", max_tokens)
    assert "不要输出任何 URL、链接或来源列表" in calls[0][0][0]["content"]


def test_string_index_preserves_citation_priority(monkeypatch):
    response = _payload('{"success": true, "points": ["正文引用[3]"]}',
                        results=[_source(str(index)) for index in range(1, 5)])
    _stub(monkeypatch, response)

    card = web_search.web_search("引用顺序")

    assert [source["index"] for source in card["sources"]] == [3, 1, 2, 4]
    assert card["url"] == "https://news.example.net/articles/3"
    assert card["points"] == ["正文引用"]


@pytest.mark.parametrize("citation", ["[3, 1]", "[3，1]", "[3、1]"])
def test_grouped_citations_prioritize_all_indices(monkeypatch, citation):
    response = _payload(json.dumps({"success": True, "points": [f"正文{citation}"]}, ensure_ascii=False),
                        results=[_source(str(index)) for index in range(1, 5)])
    _stub(monkeypatch, response)

    result = native_search.grounded_search([], max_tokens=700)

    assert [source["index"] for source in result["sources"]] == [1, 3, 2, 4]


@pytest.mark.parametrize("invalid_url", [
    "http://127.0.0.1/x", "http://[::1]/x", "javascript:alert(1)",
    "ftp://news.example.net/x", "https://user:password@news.example.net/x",
    "https://news.example.net:8080/x", "/relative/path",
])
def test_invalid_native_source_urls_are_filtered(monkeypatch, invalid_url):
    _stub(monkeypatch, _payload(results=[_source("1", url=invalid_url), _source("2")]))

    card = web_search.web_search("过滤链接")

    assert card["error"] is False
    assert card["sources"] == [{"title": "真实报道", "url": "https://news.example.net/articles/2",
                                "site_name": "新闻站", "index": 2}]


def test_sources_are_deduplicated_by_index_and_url(monkeypatch):
    first = _source("1")
    duplicate = {**first, "title": "重复标题", "index": 1}
    another_index = {**first, "index": "2"}
    _stub(monkeypatch, _payload(results=[first, duplicate, another_index]))

    result = native_search.grounded_search([], max_tokens=700)

    assert len(result["sources"]) == 2
    assert [source["index"] for source in result["sources"]] == [1, 2]
    assert result["sources"][0]["title"] == "真实报道"


def test_conflicting_citation_indices_are_not_assigned_to_sources(monkeypatch):
    _stub(monkeypatch, _payload(results=[_source("1"), _source("1", url="https://other.example.net/x"),
                                        _source("2")]))

    result = native_search.grounded_search([], max_tokens=700)

    assert [source["index"] for source in result["sources"]] == [2]


def test_cards_playback_and_history_have_no_numeric_citations(monkeypatch):
    import services.chat_service as chat

    content = json.dumps({"success": True, "headline": "主线[3][4] [图]",
                          "points": ["事实[1, 3] ，参考[ref_4]。", "保留[注]与[图][2、4]"]},
                         ensure_ascii=False)
    _stub(monkeypatch, _payload(content, results=[_source(str(index)) for index in range(1, 5)]))

    search_card = web_search.web_search("查资料")
    travel_card = travel_plan.travel_plan("宁波到北京")
    playback = travel_plan.build_playback(travel_card)
    texts = [*search_card["points"], *travel_card["points"], playback,
             chat._summarize_card_for_history(search_card), chat._summarize_card_for_history(travel_card)]

    assert travel_card["points"][0] == "主线 [图]"
    assert search_card["points"][0] == "事实，参考。"
    assert all(not re.search(r"\[(?:\d+|ref_\d+)", text) for text in texts)
    assert "[图]" in playback and "[注]" in playback
    assert "[图]" in chat._summarize_card_for_history(search_card)


@pytest.mark.parametrize("results", [[], [_source(url="http://127.0.0.1/x")], [None, "not a source"]],
                         ids=["empty", "filtered", "non-dicts"])
def test_absent_real_sources_are_non_billable_for_search_but_allow_travel(monkeypatch, results):
    import services.chat_service as chat

    _stub(monkeypatch, _payload(results=results))

    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert search_card["points"] == ["没搜到可核实的来源，换个说法再试试"]
    assert search_card["error"] is True
    assert chat._tool_billable("web_search", search_card) is False
    assert travel_card["error"] is False
    assert travel_card["sources"] == []
    assert travel_card["url"] == ""


@pytest.mark.parametrize("function,prefix", [
    (web_search.web_search, "搜索失败:"), (travel_plan.travel_plan, "规划失败："),
], ids=["web-search", "travel-plan"])
def test_truncated_native_response_returns_error_card(monkeypatch, function, prefix):
    _stub(monkeypatch, _payload(finish_reason="length"))

    card = function("查询资料")

    assert card["error"] is True
    assert card["points"] == [prefix + "truncated"]


@pytest.mark.parametrize("response", [
    None, [], {}, {"output": []}, {"output": {}},
    {"output": {"choices": []}}, {"output": {"choices": {}}},
    {"output": {"choices": [None]}}, {"output": {"choices": [{}]}},
    {"output": {"choices": [{"message": []}]}},
    {"output": {"choices": [{"message": {}}]}},
    {"output": {"choices": [{"message": {"content": 42}}]}},
], ids=["null", "list", "no-output", "output-list", "no-choices", "empty-choices",
        "choices-dict", "choice-null", "no-message", "message-list", "no-content", "numeric-content"])
def test_bad_native_response_returns_error_cards(monkeypatch, response):
    _stub(monkeypatch, response)

    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert search_card["error"] is True
    assert search_card["points"] == ["搜索失败:bad_response"]
    assert travel_card["error"] is True
    assert travel_card["points"] == ["规划失败：bad_response"]


def test_http_error_only_exposes_exception_class(monkeypatch):
    def failed(*args, **kwargs):
        raise urllib.error.HTTPError("https://provider.example.net/private", 500,
                                     "secret upstream response body", {}, io.BytesIO(b"private body"))

    monkeypatch.setattr(native_search, "_request_search", failed)

    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert search_card["points"] == ["搜索失败:HTTPError"]
    assert travel_card["points"] == ["规划失败：HTTPError"]
    assert search_card["error"] is True and travel_card["error"] is True
    assert "secret" not in str(search_card) + str(travel_card)
    assert "private" not in str(search_card) + str(travel_card)


@pytest.mark.parametrize("key", [None, ""], ids=["unset", "empty"])
def test_missing_key_does_not_call_native_search(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("DASHSCOPE_API_KEY")
    else:
        monkeypatch.setenv("DASHSCOPE_API_KEY", key)
    calls = _stub(monkeypatch, _payload())

    result = native_search.grounded_search([], max_tokens=700)
    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert result["error"] == "missing_key"
    assert search_card["points"] == ["搜索失败:missing_key"]
    assert travel_card["points"] == ["规划失败：missing_key"]
    assert search_card["error"] is True and travel_card["error"] is True
    assert calls == []


def test_surrounding_prose_is_tolerated_and_raw_is_preserved(monkeypatch):
    content = '说明文字\n{"success": true, "points": ["具体信息[1]"]}\n后续说明'
    _stub(monkeypatch, _payload(content))

    result = native_search.grounded_search([], max_tokens=700)
    card = web_search.web_search("查询资料")

    assert result["raw"] == content
    assert result["error"] is None
    assert result["data"] == {"success": True, "points": ["具体信息[1]"]}
    assert card["points"] == ["具体信息"]
    assert card["error"] is False


def test_weather_dispatch_happens_before_native_search(monkeypatch):
    from tools import visual_search

    weather_card = {"type": "card", "subtype": "weather", "source": "宁波", "points": ["晴"]}
    weather_calls = []

    def weather(query):
        weather_calls.append(query)
        return weather_card

    monkeypatch.setattr(visual_search, "_search_weather_direct", weather)
    calls = _stub(monkeypatch, _payload())

    card = web_search.web_search("  宁波天气  ")

    assert card is weather_card
    assert weather_calls == ["宁波天气"]
    assert calls == []


def test_grounded_search_copies_provider_sources(monkeypatch):
    response = _payload(results=[_source("3"), _source(True), _source(""), _source("not-numeric")])
    original = copy.deepcopy(response)
    _stub(monkeypatch, response)

    result = native_search.grounded_search([], max_tokens=700)

    assert result["error"] is None
    assert response == original
    assert response["output"]["search_info"]["search_results"][0]["index"] == "3"


@pytest.mark.parametrize("index", [True, False, "", "bad", " 3 ", 1.5, None])
def test_invalid_indices_are_removed_before_source_validation(monkeypatch, index):
    _stub(monkeypatch, _payload(results=[_source(index, url="https://news.example.net/article")]))

    result = native_search.grounded_search([], max_tokens=700)

    assert len(result["sources"]) == 1
    assert "index" not in result["sources"][0]


@pytest.mark.parametrize("index", [3, "3", "003"])
def test_integer_and_numeric_string_indices_are_preserved(monkeypatch, index):
    _stub(monkeypatch, _payload(results=[_source(index, url="https://news.example.net/article")]))

    result = native_search.grounded_search([], max_tokens=700)

    assert result["sources"][0]["index"] == 3
    assert type(result["sources"][0]["index"]) is int


def test_grounded_search_honors_max_sources(monkeypatch):
    _stub(monkeypatch, _payload(results=[_source(str(index)) for index in range(1, 7)]))

    result = native_search.grounded_search([], max_tokens=700, max_sources=2)

    assert len(result["sources"]) == 2


@pytest.mark.parametrize("content", ["服务暂时没有结果[1]", "[]", "null", "{broken}"])
def test_non_json_or_non_dict_content_uses_non_billable_fallback(monkeypatch, content):
    import services.chat_service as chat

    _stub(monkeypatch, _payload(content))

    result = native_search.grounded_search([], max_tokens=700)
    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert result["data"] is None and result["error"] is None
    assert search_card["error"] is True and travel_card["error"] is True
    assert chat._tool_billable("web_search", search_card) is False
    assert chat._tool_billable("travel_plan", travel_card) is False
    assert "[1]" not in str(search_card["points"]) + str(travel_card["points"])


def test_non_json_fallback_cleans_each_line_before_limits(monkeypatch):
    content = "[1]\n" + "\n".join(f"• 结果 {index}[1, 2] ，保留[图]" for index in range(1, 8))
    _stub(monkeypatch, _payload(content))

    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert search_card["points"] == [f"结果 {index}，保留[图]" for index in range(1, 6)]
    assert travel_card["points"] == [f"结果 {index}，保留[图]" for index in range(1, 7)]


def test_json_parser_exception_keeps_original_fallback_semantics(monkeypatch):
    content = '{"points": [[[0]]]}'
    _stub(monkeypatch, _payload(content))

    def parse_failed(*args, **kwargs):
        raise RecursionError("JSON is too deeply nested")

    monkeypatch.setattr(native_search.json, "loads", parse_failed)

    result = native_search.grounded_search([], max_tokens=700)
    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")

    assert result["data"] is None and result["error"] is None
    assert search_card["points"] == ["没搜到"] and search_card["error"] is True
    assert travel_card["points"] == ["没规划出方案"] and travel_card["error"] is True


@pytest.mark.parametrize("headline", [None, 42, [], {"text": "主线"}, True])
def test_non_string_travel_headline_is_ignored(monkeypatch, headline):
    content = json.dumps({"success": True, "headline": headline, "points": ["实际建议[1]"]})
    _stub(monkeypatch, _payload(content))

    card = travel_plan.travel_plan("宁波到北京")

    assert card["error"] is False
    assert card["points"] == ["实际建议"]


@pytest.mark.parametrize("function,message", [
    (web_search.web_search, "没搜到"), (travel_plan.travel_plan, "没规划出方案"),
], ids=["web-search", "travel-plan"])
def test_citation_only_points_are_treated_as_empty(monkeypatch, function, message):
    _stub(monkeypatch, _payload('{"success": true, "points": ["[1]", " [ref_2] "]}'))

    card = function("查询资料")

    assert card["error"] is True
    assert card["points"] == [message]


@pytest.mark.parametrize("text,expected", [
    ("事实[1][2]", "事实"),
    ("事实[1, 2]", "事实"),
    ("事实[1，2]", "事实"),
    ("事实[1、2]", "事实"),
    ("事实[ref_3]", "事实"),
    ("  事实 [1] ，后续 [2] 。  ", "事实，后续。"),
    ("前  [1]  后", "前 后"),
    ("[图]与[注]以及[1a]", "[图]与[注]以及[1a]"),
    ("  [1] [ref_2]  ", ""),
])
def test_strip_citations(text, expected):
    assert native_search.strip_citations(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("详见 http://invented.example.org/page 了解更多", "详见 了解更多"),
    ("详见 https://invented.example.org/page?x=1#part ，保留说明", "详见，保留说明"),
    ("查询 www.invented.example.org/page 后继续", "查询 后继续"),
    ("请读[官网](https://invented.example.org/page)获取信息", "请读官网获取信息"),
    ("请读[下载](ftp://invented.example.org/file)获取信息", "请读下载获取信息"),
    ("请读[说明](javascript:alert(1))获取信息", "请读说明获取信息"),
    ("[说明](javascript:alert(call(1)))与[官网](https://invented.example.org/a_(b))", "说明与官网"),
    ("联系[作者](mailto:author@invented.example.org)", "联系作者"),
    ("详见[相关页面](/relative/path)", "详见相关页面"),
    ("  HTTPS://invented.example.org/page  WWW.invented.example.org  ", ""),
    ("  前  https://invented.example.org/page  后  ", "前 后"),
    ("3.5%", "3.5%"),
    ("v2.0", "v2.0"),
    ("A股 3.5% v2.0 [图] [注]", "A股 3.5% v2.0 [图] [注]"),
])
def test_strip_urls(text, expected):
    assert native_search.strip_urls(text) == expected


@pytest.mark.parametrize("punctuation", list("，。！？；：、）】》」』"))
def test_strip_urls_stops_before_chinese_punctuation(punctuation):
    text = f"前 https://invented.example.org/path{punctuation}后"

    assert native_search.strip_urls(text) == f"前{punctuation}后"


@pytest.mark.parametrize("function", [web_search.web_search, travel_plan.travel_plan],
                         ids=["web-search", "travel-plan"])
def test_model_urls_are_removed_from_card_points(monkeypatch, function):
    content = json.dumps({"success": True, "points": [
        "详见 https://invented.example.org/page [1]了解更多",
        "补充 http://invented.example.org/info ，继续说明",
        "参考 www.invented.example.org/page [ref_2]更多内容",
        "查看[官网](javascript:alert(1))获取建议[1]",
        "https://invented.example.org/only", "www.invented.example.org/only",
        {"url": "https://invented.example.org/dict"}, ["https://invented.example.org/list"],
        "实际建议",
    ]}, ensure_ascii=False)
    _stub(monkeypatch, _payload(content))

    card = function("查询资料")

    assert card["error"] is False
    assert card["points"] == ["详见 了解更多", "补充，继续说明", "参考 更多内容", "查看官网获取建议", "实际建议"]
    assert "invented.example.org" not in str(card)
    assert card["sources"][0]["url"] == "https://news.example.net/articles/1"


@pytest.mark.parametrize("function", [web_search.web_search, travel_plan.travel_plan],
                         ids=["web-search", "travel-plan"])
def test_only_string_and_numeric_points_are_delivered(monkeypatch, function):
    content = json.dumps({"success": True, "points": [
        {"text": "对象", "url": "https://invented.example.org/dict"},
        ["列表", "https://invented.example.org/list"], None, True, False, "", "  ",
        0, 0.0, -1, 3.5, "v2.0",
    ]}, ensure_ascii=False)
    _stub(monkeypatch, _payload(content))

    card = function("查询资料")

    assert card["error"] is False
    assert card["points"] == ["0", "0.0", "-1", "3.5", "v2.0"]
    assert "invented.example.org" not in str(card)


@pytest.mark.parametrize("function,message", [
    (web_search.web_search, "没搜到"), (travel_plan.travel_plan, "没规划出方案"),
], ids=["web-search", "travel-plan"])
def test_url_only_points_are_discarded_and_return_existing_empty_error(monkeypatch, function, message):
    content = json.dumps({"success": True, "points": ["https://invented.example.org/page[1]",
                          "http://invented.example.org/page", "www.invented.example.org/page",
                          "[](javascript:alert(1))"]})
    _stub(monkeypatch, _payload(content))

    card = function("查询资料")

    assert card["error"] is True
    assert card["points"] == [message]


@pytest.mark.parametrize("headline,expected", [
    ("主线 https://invented.example.org/page [1]后续", "主线 后续"),
    ("主线 www.invented.example.org/page ，说明", "主线，说明"),
    ("[宁波方案](https://invented.example.org/a_(b))[1]", "宁波方案"),
    ("[宁波方案](javascript:alert(call(1)))[ref_2]", "宁波方案"),
    ("https://invented.example.org/page[1]", ""),
])
def test_travel_headline_urls_are_cleaned(monkeypatch, headline, expected):
    content = json.dumps({"success": True, "headline": headline, "points": ["实际建议[1]"]},
                         ensure_ascii=False)
    _stub(monkeypatch, _payload(content))

    card = travel_plan.travel_plan("宁波到北京")

    assert card["error"] is False
    assert card["points"] == ([expected, "实际建议"] if expected else ["实际建议"])
    assert "invented.example.org" not in str(card)


def test_playback_and_history_never_include_model_urls(monkeypatch):
    import services.chat_service as chat

    content = json.dumps({"success": True, "headline": "主线 https://invented.example.org/head [1]方案",
                          "points": ["出行 http://invented.example.org/point [1]提示",
                                     "[官网](https://invented.example.org/link)信息",
                                     "参考 www.invented.example.org/info ，说明"]}, ensure_ascii=False)
    _stub(monkeypatch, _payload(content))

    search_card = web_search.web_search("查询资料")
    travel_card = travel_plan.travel_plan("宁波到北京")
    texts = [travel_plan.build_playback(travel_card), chat._summarize_card_for_history(search_card),
             chat._summarize_card_for_history(travel_card)]

    assert all("http" not in text and "www." not in text and "invented.example.org" not in text
               for text in texts)
    assert "主线 方案" in texts[0] and "官网信息" in texts[0]


@pytest.mark.parametrize("function", [web_search.web_search, travel_plan.travel_plan],
                         ids=["web-search", "travel-plan"])
def test_non_json_fallback_removes_urls_before_discarding_empty_lines(monkeypatch, function):
    import services.chat_service as chat

    content = "\n".join([
        "https://invented.example.org/only[1]", "www.invented.example.org/only",
        "• 第一 https://invented.example.org/info [1]，保留",
        "• 第二 [官网](javascript:alert(call(1)))[ref_2]说明",
        "• 第三 www.invented.example.org/info 提示",
    ])
    _stub(monkeypatch, _payload(content))

    card = function("查询资料")

    assert card["error"] is True
    assert card["points"] == ["第一，保留", "第二 官网说明", "第三 提示"]
    assert "http" not in chat._summarize_card_for_history(card)
    assert "invented.example.org" not in travel_plan.build_playback(card)
