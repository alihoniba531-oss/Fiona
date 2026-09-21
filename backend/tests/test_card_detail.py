"""Individual card details, with no production DB or network."""
import asyncio
import importlib
import json
import socket
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from auth_dep import get_current_user
from rate_limit import limiter
from utils import safe_http

detail = importlib.import_module("tools.card_detail")
topic = importlib.import_module("tools.topic_expand")
cards = importlib.import_module("routers.cards")


@pytest.fixture(autouse=True)
def isolate_network(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-card-detail-key")
    monkeypatch.setattr(limiter, "enabled", False)

    def unexpected_network(*args, **kwargs):
        raise AssertionError("Unexpected live network request")

    monkeypatch.setattr(topic.urllib.request, "urlopen", unexpected_network)
    monkeypatch.setattr(safe_http, "_open_pinned", unexpected_network)
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ])


@pytest.fixture
def detail_client():
    # No main import or production lifespan: this router does not need a DB.
    app = FastAPI()
    app.include_router(cards.router)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.dependency_overrides[get_current_user] = lambda: "card-tester"
    with TestClient(app) as client:
        yield client


def search_payload(data=None, sources=None):
    if data is None:
        data = {"verified": True, "summary": "1969 年首次载人登月。",
                "whats_happening": "阿波罗 11 号于 1969 年 7 月完成载人登月。",
                "key_facts": ["任务发生于 1969 年。"], "background": "历史事件。",
                "title": "模型不应覆盖所选标题",
                "sources": [{"url": "https://fabricated.example/false"}]}
    if sources is None:
        sources = [{"title": "阿波罗 11 号任务", "url": "https://example.com/apollo", "site_name": "档案"}]
    return {"output": {"choices": [{"message": {"content": json.dumps(data, ensure_ascii=False)},
                                    "finish_reason": "stop"}],
                       "search_info": {"search_results": sources}}}


def fake_search(monkeypatch, payload):
    calls = []

    def search(messages, api_key, **kwargs):
        calls.append((messages, api_key, kwargs))
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(detail, "_request_search", search)
    return calls


def alive_sources(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200, url=url)

    monkeypatch.setattr(topic, "request_public_url", request)
    return calls


def test_selection_and_historical_dates_are_preserved_with_native_sources(monkeypatch):
    calls = fake_search(monkeypatch, search_payload())
    source_calls = alive_sources(monkeypatch)
    result = detail.card_detail("  1969 年阿波罗 11 号首次载人登月  ", " 历史新闻回顾 ")
    assert "error" not in result
    assert result["title"] == "1969 年阿波罗 11 号首次载人登月"
    assert "1969" in result["whats_happening"]
    assert result["sources"] == [{"title": "阿波罗 11 号任务", "url": "https://example.com/apollo", "site_name": "档案"}]
    assert "fabricated" not in json.dumps(result)
    messages, _, options = calls[0]
    assert json.loads(messages[1]["content"]) == {"title": result["title"], "context": "历史新闻回顾"}
    assert "不预设它今天上热搜" in messages[0]["content"]
    assert "只陈述搜索结果支持的事实" in messages[0]["content"]
    assert options == {"max_tokens": 1400}
    assert source_calls == []  # Display links do not require fetching each publisher.


def test_each_selection_has_its_own_query(monkeypatch):
    calls = fake_search(monkeypatch, search_payload())
    alive_sources(monkeypatch)
    for title in ("第一条：月球任务", "第二条：火星任务"):
        assert detail.card_detail(title, "航天新闻")["title"] == title
    assert [json.loads(call[0][1]["content"])["title"] for call in calls] == [
        "第一条：月球任务", "第二条：火星任务",
    ]


@pytest.mark.parametrize("sources", [[], None, "bad", [None, {}, {"url": 123}]])
def test_missing_sources_does_not_present_unverified_model_text(monkeypatch, sources):
    payload = search_payload()
    payload["output"]["search_info"]["search_results"] = sources
    fake_search(monkeypatch, payload)
    result = detail.card_detail("所选条目")
    assert result["error"]
    assert result["summary"] == result["whats_happening"] == ""
    assert result["sources"] == result["key_facts"] == []


def test_source_links_block_private_addresses_credentials_and_local_names(monkeypatch):
    opened = []

    def open_pinned(target, ip, method, headers, timeout):
        opened.append(target.url)
        raw = SimpleNamespace(status=302, headers={"Location": "http://127.0.0.1/private"},
                              release_conn=lambda: None)
        return raw, SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(safe_http, "_open_pinned", open_pinned)
    fake_search(monkeypatch, search_payload(sources=[
        {"url": "http://127.0.0.1/private"},
        {"url": "https://user:secret@example.com/"},
        {"url": "javascript:alert(1)"},
        {"url": "http://localhost/private"},
        {"url": "http://printer.local/private"},
        {"url": "http://127.1/private"},
    ]))
    result = detail.card_detail("所选条目")
    assert result["error"]
    assert result["sources"] == []
    assert opened == []


def test_sources_are_deduplicated_and_returned_list_is_bounded(monkeypatch):
    source_calls = alive_sources(monkeypatch)
    sources = [{"url": f"https://example.com/{index}"} for index in range(100)]
    sources.insert(1, sources[0])
    fake_search(monkeypatch, search_payload(sources=sources))
    result = detail.card_detail("所选条目")
    assert len(result["sources"]) == 12
    assert source_calls == []
    assert len({source["url"] for source in result["sources"]}) == 12


@pytest.mark.parametrize("payload", [
    TimeoutError("private-api-key-and-response"),
    {"message": "private-api-key-and-response"},
    {"output": {"choices": []}},
    {"output": {"choices": [{"message": {"content": "private-api-key-and-response"}}]}},
    {"output": {"choices": [{"message": {"content": []}}]}},
    search_payload(data={"verified": False, "summary": "Unsupported claim"}),
    search_payload(data={"verified": True, "summary": ["bad type"]}),
    search_payload(data={"verified": True, "summary": "summary", "key_facts": [None]}),
])
def test_upstream_errors_and_bad_output_never_leak_raw_content(monkeypatch, payload):
    fake_search(monkeypatch, payload)
    result = detail.card_detail("所选条目")
    assert result["title"] == "所选条目"
    assert result["error"]
    assert result["sources"] == []
    assert "private-api-key-and-response" not in str(result)
    assert "Unsupported claim" not in str(result)


def test_truncated_output_is_not_a_complete_detail(monkeypatch):
    payload = search_payload()
    payload["output"]["choices"][0]["finish_reason"] = "length"
    fake_search(monkeypatch, payload)
    assert detail.card_detail("所选条目")["error"] == "详情返回不完整，请重试"


def test_missing_key_has_a_user_facing_error(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    result = detail.card_detail("所选条目")
    assert result["error"]
    assert "DASHSCOPE_API_KEY" not in str(result)


@pytest.mark.parametrize("body", [
    {}, {"title": ""}, {"title": "   "}, {"title": "字" * 1001},
    {"title": "标题", "context": "字" * 201}, {"title": 123},
    {"title": "标题", "url": "http://127.0.0.1"},
])
def test_invalid_input_never_calls_search(detail_client, monkeypatch, body):
    calls = []
    monkeypatch.setattr(cards, "card_detail", lambda *a: calls.append(a))
    assert detail_client.post("/cards/detail", json=body).status_code == 422
    assert calls == []


def test_max_lengths_and_normalized_selection(detail_client, monkeypatch):
    calls = []

    def expand(title, context):
        calls.append((title, context))
        return {"title": title, "sources": []}

    monkeypatch.setattr(cards, "card_detail", expand)
    response = detail_client.post("/cards/detail", json={"title": "字" * 1000, "context": "字" * 200})
    assert response.status_code == 200
    assert calls == [("字" * 1000, "字" * 200)]
    assert detail_client.post("/cards/detail", json={"title": "  选择  "}).json()["title"] == "选择"


def test_authentication_required(detail_client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    detail_client.app.dependency_overrides.clear()
    assert detail_client.post("/cards/detail", json={"title": "标题"}).status_code == 401


def test_twenty_calls_per_minute_limit(detail_client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    calls = []
    monkeypatch.setattr(cards, "card_detail", lambda *a: calls.append(a) or {"title": a[0]})
    try:
        for _ in range(20):
            assert detail_client.post("/cards/detail", json={"title": "标题"}).status_code == 200
        assert detail_client.post("/cards/detail", json={"title": "标题"}).status_code == 429
        assert len(calls) == 20
    finally:
        limiter.reset()


def test_route_timeout_is_bounded_and_retryable(detail_client, monkeypatch):
    async def blocked_thread(*args):
        await asyncio.sleep(1)

    monkeypatch.setattr(cards.asyncio, "to_thread", blocked_thread)
    monkeypatch.setattr(cards, "DETAIL_TIMEOUT_SECONDS", 0.001)
    response = detail_client.post("/cards/detail", json={"title": "标题"})
    assert response.status_code == 200
    assert response.json()["error"] == "详情获取超时，请重试"


def test_native_transport_forces_search_with_bounded_read_and_timeout(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            captured["size"] = size
            return b'{"output": {}}'

    def urlopen(req, *, timeout):
        captured.update(body=json.loads(req.data), timeout=timeout, url=req.full_url)
        return Response()

    monkeypatch.setattr(topic.urllib.request, "urlopen", urlopen)
    assert topic._request_search([{"role": "user", "content": "selected item"}], "test-key") == {"output": {}}
    assert captured["url"] == topic.DASHSCOPE_URL
    assert captured["timeout"] == 30
    assert captured["size"] == 1_000_001
    assert captured["body"]["parameters"]["search_options"]["forced_search"] is True
    assert captured["body"]["parameters"]["search_options"]["enable_source"] is True


def test_old_hot_expand_retains_prompt_and_response_contract(monkeypatch):
    captured = []

    def search(messages, key, **kwargs):
        captured.append((messages, kwargs))
        return search_payload(data={"summary": "热点摘要", "whats_happening": "事件详情",
                                    "why_trending": "热搜原因", "key_facts": ["事实"], "background": "背景"})

    monkeypatch.setattr(topic, "_request_search", search)
    source_calls = alive_sources(monkeypatch)
    result = topic.topic_expand("  今日话题  ")
    assert result["title"] == "今日话题"
    assert result["why_trending"] == "热搜原因"
    assert result["sources"][0]["url"] == "https://example.com/apollo"
    assert "最近 7 天内" in captured[0][0][1]["content"]
    assert captured[0][1] == {}
    assert source_calls[0][2]["timeout"] == 4
    assert source_calls[0][2]["max_redirects"] == 3

def test_citations_map_to_provider_ids_even_when_source_array_is_reordered(monkeypatch):
    payload = search_payload()
    data = json.loads(payload["output"]["choices"][0]["message"]["content"])
    data.update(summary="服贸会开幕[1][4]。", whats_happening="数智化技术集中展示[8][9]。",
                key_facts=["AI 展示覆盖多个领域[4, 9]。"])
    payload["output"]["choices"][0]["message"]["content"] = json.dumps(data)
    payload["output"]["search_info"]["search_results"] = [
        {"index": index, "title": f"真实来源 {index}", "url": f"https://example.com/{index}"}
        for index in [9, 2, 6, 1, 8, 4, 3, 5, 7]
    ]
    fake_search(monkeypatch, payload)
    result = detail.card_detail("服贸会开幕")
    assert "error" not in result
    assert [source["index"] for source in result["sources"][:4]] == [1, 4, 8, 9]
    for source in result["sources"]:
        assert source["url"] == f"https://example.com/{source['index']}"
    assert "[8][9]" in result["whats_happening"]


def test_cited_sources_beyond_the_preview_limit_take_priority(monkeypatch):
    payload = search_payload(data={"verified": True, "summary": "报道[18]。",
                                  "whats_happening": "资料[20]。", "key_facts": [], "background": ""})
    payload["output"]["search_info"]["search_results"] = [
        {"index": index, "url": f"https://example.com/{index}"} for index in range(1, 21)
    ]
    fake_search(monkeypatch, payload)
    result = detail.card_detail("标题")
    assert "error" not in result
    assert len(result["sources"]) == 12
    assert [source["index"] for source in result["sources"][:2]] == [18, 20]


@pytest.mark.parametrize("sources", [
    [{"index": 1, "url": "https://example.com/one"}],
    [{"url": "https://example.com/first"}, {"url": "https://example.com/second"}],
    [{"index": True, "url": "https://example.com/one"}],
    [{"index": 2, "url": "http://127.0.0.1/"}, {"index": 1, "url": "https://example.com/one"}],
    [{"index": 2, "url": "https://example.com/first"}, {"index": 2, "url": "https://example.com/second"}],
])
def test_missing_unsafe_or_ambiguous_citation_ids_never_return_dangling_references(monkeypatch, sources):
    payload = search_payload(
        data={"verified": True, "summary": "报道[2]", "whats_happening": "已引用[2]。",
              "key_facts": [], "background": ""},
        sources=sources,
    )
    fake_search(monkeypatch, payload)
    result = detail.card_detail("标题")
    assert result["error"]
    assert result["sources"] == []
    assert result["summary"] == ""


def test_same_url_with_distinct_native_ids_keeps_both_citation_identities(monkeypatch):
    payload = search_payload(
        data={"verified": True, "summary": "报道[1][2]", "whats_happening": "资料[2]。",
              "key_facts": [], "background": ""},
        sources=[{"index": 1, "url": "https://example.com/article"},
                 {"index": 2, "url": "https://example.com/article"}],
    )
    fake_search(monkeypatch, payload)
    result = detail.card_detail("标题")
    assert "error" not in result
    assert [source["index"] for source in result["sources"]] == [1, 2]


def test_more_citations_than_we_can_display_is_an_explicit_failure(monkeypatch):
    payload = search_payload(
        data={"verified": True, "summary": "报道" + "".join(f"[{n}]" for n in range(1, 14)),
              "whats_happening": "资料。", "key_facts": [], "background": ""},
        sources=[{"index": index, "url": f"https://example.com/{index}"} for index in range(1, 14)],
    )
    fake_search(monkeypatch, payload)
    result = detail.card_detail("标题")
    assert result["error"] == "详情引用来源不完整，请重试"
    assert result["sources"] == []
