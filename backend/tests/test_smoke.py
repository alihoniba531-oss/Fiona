# -*- coding: utf-8 -*-
"""
4 条 happy-path 冒烟测试 —— 阶段 1 拆 router 的回归基线。

不验业务正确性，只钉住「路由能通 + 鉴权生效 + 落库读库 + 响应形状」，
让后续纯搬运式重构有个能一眼看绿/红的安全网。
"""


def test_chat_happy_path(client, dev_headers):
    """/chat：鉴权 + 落库 + 流式返回（LLM 已打桩为假流）。"""
    r = client.post("/chat", json={"message": "你好啊"}, headers=dev_headers)
    assert r.status_code == 200
    body = r.text
    # 假流吐出的文本 + done 事件都应出现在 SSE 流里
    assert "测试" in body or "回复" in body
    assert "done" in body


def test_chat_requires_auth(client):
    """无鉴权头应被中间件 401 挡下（证明鉴权确实生效）。"""
    r = client.post("/chat", json={"message": "你好"})
    assert r.status_code == 401


def test_match_happy_path(client, dev_headers):
    """/match：鉴权 + 返回 {username, matches}（匹配引擎已打桩为空）。"""
    r = client.get("/match", headers=dev_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "smoke_tester"
    assert isinstance(data["matches"], list)


def test_history_happy_path(client, dev_headers):
    """/history：先发一条 chat 落库，再读 history 应能拿回。"""
    client.post("/chat", json={"message": "记住这句话"}, headers=dev_headers)
    r = client.get("/history", headers=dev_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "smoke_tester"
    assert isinstance(data["messages"], list)
    # 刚发的用户消息应在历史里
    assert any("记住这句话" in (m.get("content") or "") for m in data["messages"])


def test_redeem_invite_happy_path(client):
    """/auth/redeem-invite：种一个码 → 兑换 → 拿到 HttpOnly 会话。"""
    import asyncio
    import database

    code = "SMOKE123"
    # 临时库已被 client 夹具的 lifespan 建好表，这里直接种码
    asyncio.run(database.create_invite(code, "invited_user", note="smoke"))
    r = client.post("/auth/redeem-invite", json={"code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "invited_user"
    assert "token" not in data
    assert "HttpOnly" in r.headers["set-cookie"]
