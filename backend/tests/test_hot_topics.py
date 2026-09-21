"""Hot-topic failures, cache recovery, and categorization stay separate from news.

These tests use an isolated clock and fake upstream responses. They do not start
the application, initialize a database, or call an LLM/network service.
"""

import asyncio
import importlib
import inspect
import json
from types import SimpleNamespace

import pytest
import requests
from starlette.requests import Request


hot_tool = importlib.import_module("tools.hot_topics")


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


def success_response(title="2026 年科技展 · 现场观察"):
    return FakeResponse({
        "code": 200,
        "data": [{"title": title, "hot_value": 12000,
                  "link": "https://example.test/topic"}],
    })


@pytest.fixture
def clock(monkeypatch):
    tick = [1000.0]
    monkeypatch.setattr(hot_tool, "time", SimpleNamespace(monotonic=lambda: tick[0]))
    monkeypatch.setattr(hot_tool, "_cache", {})
    monkeypatch.setattr(hot_tool, "_failures", {})
    monkeypatch.setattr(hot_tool, "_api_bases", lambda: ("https://hot.example.test/v2",))
    return tick


@pytest.mark.parametrize("failure", [
    FakeResponse(status=403),
    FakeResponse({"code": 503, "message": "service unavailable"}),
    FakeResponse({"code": 200, "data": []}),
    FakeResponse({"code": 200, "data": [None, {}, {"title": "   "}]}),
    requests.Timeout("private upstream exception detail"),
])
def test_failed_fetch_is_not_a_news_item(clock, monkeypatch, failure):
    def get(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(hot_tool.requests, "get", get)
    card = hot_tool.hot_topics("微博")

    assert card["source"] == "微博热搜"
    assert card["error"] is True
    assert card["points"] == []
    assert card.get("items", []) == []
    assert card["message"]
    assert card["updated_at"] is None
    assert "private upstream exception detail" not in str(card)


def test_success_is_shared_by_source_aliases_until_cache_expires(clock, monkeypatch):
    calls = []

    def get(url, *, timeout):
        calls.append((url, timeout))
        return success_response(f"第 {len(calls)} 批科技热榜")

    monkeypatch.setattr(hot_tool.requests, "get", get)
    first = hot_tool.hot_topics("微博")
    clock[0] += 299
    cached = hot_tool.hot_topics("weibo")

    assert first == cached
    assert len(calls) == 1
    assert calls[0] == ("https://hot.example.test/v2/weibo", 8)
    assert first["stale"] is False
    assert first["updated_at"]
    assert not first.get("error")

    clock[0] += 2
    refreshed = hot_tool.hot_topics("微博热搜")
    assert len(calls) == 2
    assert refreshed["points"] != first["points"]


def test_failed_refresh_keeps_last_good_content_and_original_timestamp(clock, monkeypatch):
    monkeypatch.setattr(hot_tool.requests, "get", lambda *a, **k: success_response())
    first = hot_tool.hot_topics("微博")
    clock[0] += 301
    monkeypatch.setattr(hot_tool.requests, "get", lambda *a, **k: FakeResponse(status=403))

    stale = hot_tool.hot_topics("微博")

    assert stale["points"] == first["points"]
    assert stale["items"] == first["items"]
    assert stale["updated_at"] == first["updated_at"]
    assert stale["stale"] is True
    assert stale["message"]
    assert not stale.get("error")
    assert first["stale"] is False  # The returned cache copy is not mutated.


def test_repeated_failures_do_not_extend_age_of_last_good_content(clock, monkeypatch):
    monkeypatch.setattr(hot_tool.requests, "get", lambda *a, **k: success_response())
    first = hot_tool.hot_topics("微博")
    monkeypatch.setattr(hot_tool.requests, "get", lambda *a, **k: FakeResponse(status=503))

    clock[0] += 3500
    stale = hot_tool.hot_topics("微博")
    assert stale["stale"] is True
    assert stale["updated_at"] == first["updated_at"]

    clock[0] += 101
    expired = hot_tool.hot_topics("微博")
    assert expired["error"] is True
    assert expired["points"] == []
    assert expired["updated_at"] is None


def test_failed_request_retries_after_short_cooldown(clock, monkeypatch):
    calls = []
    healthy = [False]

    def get(*args, **kwargs):
        calls.append(args[0])
        return success_response() if healthy[0] else FakeResponse(status=403)

    monkeypatch.setattr(hot_tool.requests, "get", get)
    assert hot_tool.hot_topics("微博")["error"] is True
    healthy[0] = True
    clock[0] += 29
    assert hot_tool.hot_topics("weibo")["error"] is True
    assert len(calls) == 1

    clock[0] += 2
    recovered = hot_tool.hot_topics("微博")
    assert len(calls) == 2
    assert recovered["points"]
    assert not recovered.get("error")
    assert recovered["stale"] is False


def test_an_unavailable_primary_can_fall_back_to_second_endpoint(clock, monkeypatch):
    monkeypatch.setattr(hot_tool, "_api_bases", lambda: (
        "https://primary.example.test/v2", "https://secondary.example.test/v2",
    ))
    calls = []

    def get(url, *, timeout):
        calls.append(url)
        return FakeResponse(status=403) if "primary" in url else success_response()

    monkeypatch.setattr(hot_tool.requests, "get", get)
    card = hot_tool.hot_topics("bilibili")

    assert calls == ["https://primary.example.test/v2/bili", "https://secondary.example.test/v2/bili"]
    assert card["source"] == "B站热搜"
    assert card["points"]
    assert not card.get("error")


def test_explicit_service_override_does_not_contact_public_fallbacks(monkeypatch):
    monkeypatch.setattr(hot_tool, "_cache", {})
    monkeypatch.setattr(hot_tool, "_failures", {})
    monkeypatch.setenv("HOT_TOPICS_API_BASE", "https://internal.example.test/private-api/")
    calls = []

    def get(url, *, timeout):
        calls.append(url)
        return FakeResponse(status=403)

    monkeypatch.setattr(hot_tool.requests, "get", get)
    card = hot_tool.hot_topics("微博")

    assert card["error"] is True
    assert calls == ["https://internal.example.test/private-api/weibo"]


def categorized(monkeypatch, results, classify_fn=None):
    router = importlib.import_module("routers.hot")
    classified = []

    def fetch(source):
        result = results.get(source, {"points": []})
        if isinstance(result, Exception):
            raise result
        return result

    def classify(titles):
        classified.extend(titles)
        return classify_fn(titles) if classify_fn else {title: "科技" for title in titles}

    monkeypatch.setattr(router, "hot_topics", fetch)
    monkeypatch.setattr(router, "_classify_with_llm", classify)
    request = Request({"type": "http", "method": "GET", "path": "/hot/categorized/all",
                       "headers": [], "client": ("127.0.0.1", 1234)})
    result = asyncio.run(inspect.unwrap(router.hot_categorized)(request=request))
    return result, classified


@pytest.mark.parametrize("entertainment_rank", [9, 50])
def test_entertainment_after_chat_preview_is_still_categorized(
    clock, monkeypatch, entertainment_rank,
):
    entertainment = "电影节公布获奖名单"
    titles = [f"第 {rank} 条道路通行消息" for rank in range(1, 51)]
    titles[entertainment_rank - 1] = entertainment
    monkeypatch.setattr(hot_tool.requests, "get", lambda *a, **k: FakeResponse({
        "code": 200,
        "data": [{"title": title, "hot_value": 12000,
                  "link": f"https://example.test/topic/{rank}"}
                 for rank, title in enumerate(titles, 1)],
    }))

    card = hot_tool.hot_topics("微博")
    result, classified = categorized(
        monkeypatch, {"微博": card}, classify_fn=lambda titles: {},
    )

    assert len(card["points"]) == 8
    assert all(entertainment not in point for point in card["points"])
    assert classified == titles
    assert result["categories"]["娱乐"] == [entertainment]
    assert result["error"] is False


def test_each_source_keeps_at_most_fifty_classification_candidates(clock, monkeypatch):
    def get(url, *, timeout):
        endpoint = url.rsplit("/", 1)[-1]
        return FakeResponse({
            "code": 200,
            "data": [{"title": f"{endpoint} 第 {rank} 条话题", "hot_value": rank,
                      "link": f"https://example.test/{endpoint}/{rank}"}
                     for rank in range(1, 61)],
        })

    monkeypatch.setattr(hot_tool.requests, "get", get)
    cards = {source: hot_tool.hot_topics(source)
             for source in ["微博", "抖音", "知乎", "B站", "头条"]}

    for card in cards.values():
        assert len(card["points"]) == 8
        assert len(card["items"]) == 50
        assert card["items"][0]["title"].endswith("第 1 条话题")
        assert card["items"][-1]["title"].endswith("第 50 条话题")
        assert card["items"][-1]["url"].endswith("/50")
    _, classified = categorized(monkeypatch, cards)
    assert len(classified) == 250
    assert all("第 51 条话题" not in title for title in classified)


def test_category_feed_skips_failed_sources_and_deduplicates_titles(monkeypatch):
    result, classified = categorized(monkeypatch, {
        "微博": {"error": True, "points": ["获取失败：HTTP 403"]},
        "抖音": {"points": ["1. 同一条科技新闻 · 1.2万"]},
        "知乎": {"points": ["1. 同一条科技新闻 · 8万热度"]},
        "B站": requests.Timeout(),
        "头条": {"points": ["1. 另一条科技新闻 · 5万"]},
    })

    assert classified == ["同一条科技新闻", "另一条科技新闻"]
    assert result["categories"]["科技"] == classified
    assert all("获取失败" not in title for titles in result["categories"].values() for title in titles)


def test_legacy_points_preserve_numeric_prefixes_and_internal_middle_dots(monkeypatch):
    title = "2026 年科技展 · 张三专访"
    second = "3.14 与圆周率"
    result, classified = categorized(monkeypatch, {
        "微博": {"points": [f"1. {title} · 1.2万", f"2. {second} · 2500"]},
    })

    assert classified == [title, second]
    assert result["categories"]["科技"] == [title, second]


def test_structured_titles_take_precedence_over_display_points(monkeypatch):
    title = "2026 年科技展 · 张三专访"
    result, classified = categorized(monkeypatch, {
        "微博": {"items": [{"title": title, "url": "https://example.test/topic"}],
                 "points": ["1. 不应把显示文本当成真实标题 · 5万"]},
    })

    assert classified == [title]
    assert result["categories"]["科技"] == [title]


def test_all_sources_failed_returns_no_fabricated_topics(monkeypatch):
    failure = {"error": True, "points": ["获取失败：HTTP 403"]}
    result, classified = categorized(monkeypatch, {
        source: failure for source in ["微博", "抖音", "知乎", "B站", "头条"]
    })

    assert classified == []
    assert all(titles == [] for titles in result["categories"].values())


def mock_classifier(monkeypatch, payload):
    router = importlib.import_module("routers.hot")
    tick = [1000.0]
    calls = []
    options = []

    def create(**kwargs):
        calls.append(kwargs)
        if isinstance(payload, Exception):
            raise payload
        content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def with_options(**kwargs):
        options.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(router, "QWEN_CLIENT", SimpleNamespace(with_options=with_options))
    monkeypatch.setattr(router, "QWEN_MODEL", "test-lightweight-model")
    monkeypatch.setattr(router, "QWEN_EXTRA_BODY", {"enable_thinking": False})
    monkeypatch.setattr(router, "_time", SimpleNamespace(time=lambda: tick[0]))
    monkeypatch.setattr(router, "_classify_cache", {})
    return router, tick, calls, options


def test_numbered_classification_maps_all_250_titles_with_bounded_model_call(monkeypatch):
    categories = ["娱乐", "经济", "生活", "科技", "文化"]
    titles = [f"第 {index} 条完整标题 · 现场观察" for index in range(1, 251)]
    payload = {category: list(range(index + 1, 251, 5))
               for index, category in enumerate(categories)}
    router, _, calls, options = mock_classifier(monkeypatch, payload)

    classified = router._classify_with_llm(titles)

    assert classified == {title: categories[index % 5] for index, title in enumerate(titles)}
    assert len(calls) == 1
    assert options == [{"timeout": 8.0, "max_retries": 0}]
    call = calls[0]
    assert call["model"] == "test-lightweight-model"
    assert call["extra_body"] == {"enable_thinking": False}
    assert call["max_tokens"] == 2000
    assert call["response_format"] == {"type": "json_object"}
    numbered = call["messages"][1]["content"].splitlines()
    assert numbered == [f"{index}. {title}" for index, title in enumerate(titles, 1)]


def test_invalid_and_conflicting_classification_indices_are_not_assigned(monkeypatch):
    titles = [f"原始标题 {index}" for index in range(1, 7)]
    router, _, _, _ = mock_classifier(monkeypatch, {
        "娱乐": [True, False, "3", 3.0, 2, 0, -1, 7],
        "经济": [2, 5, 5],
        "科技": [4],
        "文化": "6",
        "生活": None,
        "未知类别": [6],
    })

    assert router._classify_with_llm(titles) == {
        "原始标题 4": "科技", "原始标题 5": "经济",
    }


def test_missing_or_conflicting_model_assignments_use_keyword_fallback(monkeypatch):
    titles = ["电影节公布获奖名单", "芯片研发获得突破", "道路恢复通行"]
    router, _, calls, _ = mock_classifier(monkeypatch, {
        "经济": [1], "科技": [1], "生活": [3],
    })

    result, classified = categorized(monkeypatch, {
        "微博": {"items": [{"title": title} for title in titles]},
    }, classify_fn=router._classify_with_llm)

    assert classified == titles
    assert result["categories"]["娱乐"] == [titles[0]]
    assert result["categories"]["科技"] == [titles[1]]
    assert result["categories"]["生活"] == [titles[2]]
    assert result["categories"]["经济"] == []
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [
    requests.Timeout("private classification failure"),
    '{"娱乐": [1',
    [1, 2],
    {},
])
def test_failed_classification_has_a_short_retry_cooldown(monkeypatch, payload):
    router, tick, calls, _ = mock_classifier(monkeypatch, payload)
    titles = ["电影节公布获奖名单"]

    assert router._classify_with_llm(titles) == {}
    tick[0] += 29
    assert router._classify_with_llm(titles) == {}
    assert len(calls) == 1

    tick[0] += 2
    assert router._classify_with_llm(titles) == {}
    assert len(calls) == 2


def test_successful_classification_is_reused_for_five_minutes(monkeypatch):
    router, tick, calls, _ = mock_classifier(monkeypatch, {"娱乐": [1]})
    titles = ["电影节公布获奖名单"]

    first = router._classify_with_llm(titles)
    tick[0] += 299
    assert router._classify_with_llm(titles) == first
    assert len(calls) == 1

    tick[0] += 2
    assert router._classify_with_llm(titles) == first
    assert len(calls) == 2


def test_classification_cache_is_bounded_and_empty_input_skips_the_model(monkeypatch):
    router, _, calls, _ = mock_classifier(monkeypatch, {"娱乐": [1]})

    assert router._classify_with_llm([]) == {}
    assert calls == []
    for index in range(40):
        router._classify_with_llm([f"第 {index} 场电影节"])

    assert len(router._classify_cache) == 32
    assert len(calls) == 40
