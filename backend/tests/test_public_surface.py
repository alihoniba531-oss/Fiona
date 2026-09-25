# -*- coding: utf-8 -*-
"""匿名公网暴露面：会调用模型的热点展开必须登录，生产环境不暴露 API 文档。"""
import pytest


@pytest.fixture
def expand_calls(monkeypatch):
    import tools.topic_expand as topic_expand_module
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    calls = []

    def fake_topic_expand(title):
        calls.append(title)
        return {"title": title, "summary": "测试摘要"}

    monkeypatch.setattr(topic_expand_module, "topic_expand", fake_topic_expand)
    return calls


def _production_headers(client, dev_headers, monkeypatch):
    from auth import create_token

    # 先在 DEV_MODE 下建号，再切到生产模式并改用真实 JWT。
    assert client.get("/profile", headers=dev_headers).status_code == 200
    monkeypatch.setenv("DEV_MODE", "0")
    return {"Authorization": f"Bearer {create_token(dev_headers['X-Dev-User'])}"}


@pytest.mark.parametrize("path", ["/hot/expand?title=x", "/hot/expand/?title=x"])
def test_hot_expand_rejects_anonymous_requests_in_production(client, monkeypatch, expand_calls, path):
    monkeypatch.setenv("DEV_MODE", "0")

    response = client.get(path)

    assert response.status_code == 401
    assert expand_calls == []


def test_hot_expand_rejects_anonymous_requests_in_dev_mode(client, expand_calls):
    response = client.get("/hot/expand?title=x")

    assert response.status_code == 401
    assert expand_calls == []


def test_hot_expand_serves_logged_in_users(client, dev_headers, monkeypatch, expand_calls):
    headers = _production_headers(client, dev_headers, monkeypatch)

    response = client.get("/hot/expand?title=热点标题", headers=headers)

    assert response.status_code == 200
    assert response.json()["title"] == "热点标题"
    assert expand_calls == ["热点标题"]


def test_hot_boards_stay_public(client, monkeypatch):
    import routers.hot as hot
    from rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(hot, "hot_topics", lambda source: {"source": source, "items": []})

    response = client.get("/hot/微博")

    assert response.status_code == 200
    assert response.json() == {"source": "微博", "items": []}


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"])
def test_api_docs_are_hidden_in_production(client, dev_headers, monkeypatch, path):
    headers = _production_headers(client, dev_headers, monkeypatch)

    assert client.get(path).status_code == 404
    assert client.get(path, headers=headers).status_code == 404


def test_api_docs_remain_available_in_dev_mode(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/hot/expand" in response.json()["paths"]
