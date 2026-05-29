# -*- coding: utf-8 -*-
"""
冒烟测试公共夹具。

两个核心隔离手段，保证测试既不碰真库、也不打真网络：
  1. DB 隔离：把 database.DB_PATH 指到临时文件，再触发 lifespan 跑 init_db()。
     database.py 里所有函数都在调用时读模块全局 DB_PATH，所以改这一个值就够。
  2. LLM/网络隔离：DEV_MODE=1 + monkeypatch main 里所有会出网的入口
     （detect_mode / recognize_intent / _create_stream_with_fallback /
      find_matches / extract_and_update / detect_matches_and_save）。
"""
import os
import importlib

import pytest


# ── 假流：模拟 OpenAI 流式响应，generate() 按 chunk.choices[0].delta.content 消费 ──
class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason=None):
        self.delta = _FakeDelta(content)
        self.finish_reason = finish_reason


class _FakeChunk:
    def __init__(self, content, finish_reason=None):
        self.choices = [_FakeChoice(content, finish_reason)]


class _FakeStream:
    def __iter__(self):
        yield _FakeChunk("测试")
        yield _FakeChunk("回复", finish_reason="stop")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带 DB 隔离 + 全网络打桩的 TestClient。"""
    # DEV_MODE=1：跳过草莓余额/扣费，放行 X-Dev-User 鉴权
    monkeypatch.setenv("DEV_MODE", "1")

    import database
    # 临时库，绝不碰 backend/fiona.db
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))

    import main  # noqa: F401  触发 app 装配
    # 端点已拆到 routers/，符号经 `from X import Y` 绑定在各 router 模块命名空间，
    # 所以打桩目标是 routers.chat / routers.match，不是 main。
    import routers.chat as chat
    import routers.match as match

    async def _noop_async(*a, **k):
        return None

    monkeypatch.setattr(chat, "detect_mode", lambda *a, **k: "friend")
    monkeypatch.setattr(
        chat, "recognize_intent",
        lambda *a, **k: {"intent": None, "params": {}, "missing": []},
    )
    monkeypatch.setattr(
        chat, "_create_stream_with_fallback",
        lambda use_qwen, messages, **k: (_FakeStream(), False),
    )
    monkeypatch.setattr(chat, "extract_and_update", _noop_async)
    monkeypatch.setattr(chat, "detect_matches_and_save", _noop_async)

    async def _no_matches(*a, **k):
        return []

    monkeypatch.setattr(match, "find_matches", _no_matches)

    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:  # 进入即触发 lifespan → init_db() 建临时库
        yield c


@pytest.fixture
def dev_headers():
    """DEV_MODE 下用 X-Dev-User 充当已登录用户。"""
    return {"X-Dev-User": "smoke_tester"}
