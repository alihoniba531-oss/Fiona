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

import pytest

from _fakes import FakeStream

# CI / 裸机保障：在收集阶段任何测试模块 import llm/auth 之前注入占位凭据。
# llm.py 在模块顶层构造 DashScope 客户端（缺 DASHSCOPE_API_KEY 直接 OpenAIError），
# auth.py 硬校验 JWT_SECRET（缺失直接 RuntimeError）；CI 不检出 .env，会当场收集崩溃。
# 用 setdefault 注入占位值；本地 .env 不覆盖已有环境变量，避免测试读入真实凭据。
# 测试本身已把出网入口全部打桩（见下方 client fixture），占位 key 不会真出网。
os.environ.setdefault("JWT_SECRET", "fiona-ci-smoke-test-secret-0123456789")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-fiona-ci-smoke-test-not-real")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带 DB 隔离 + 全网络打桩的 TestClient。"""
    # DEV_MODE=1：跳过草莓余额/扣费，放行 X-Dev-User 鉴权
    monkeypatch.setenv("DEV_MODE", "1")

    import database
    # 临时库，绝不碰 backend/fiona.db
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))

    import main  # noqa: F401  触发 app 装配
    # /chat 逻辑已抽到 services.chat_service，符号经 `from X import Y` 绑定在该模块命名空间，
    # 所以 chat 相关打桩目标是 services.chat_service；find_matches 仍在 routers.match。
    import services.chat_service as chat
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
        lambda use_qwen, messages, **k: (FakeStream(), False),
    )
    monkeypatch.setattr(chat, "extract_and_update", _noop_async)
    monkeypatch.setattr(chat, "detect_matches_and_save", _noop_async)
    async def _no_image_network(*a, **k):
        raise chat.ImageGenerationError("测试环境未启用真实图片生成")
    monkeypatch.setattr(chat, "generate_image", _no_image_network)
    monkeypatch.setattr(chat, "edit_image", _no_image_network)

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
