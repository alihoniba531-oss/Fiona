# -*- coding: utf-8 -*-
"""
冒烟测试公共夹具。

三个核心隔离手段，保证测试不碰真库、真实上传目录和外网：
  1. 收集阶段强制设置会话临时 FIONA_DB_PATH/FIONA_UPLOADS_DIR；逐用例
     还会把 database.DB_PATH 指到自己的临时库，再触发 lifespan 跑 init_db()。
  2. 任何模块导入之前固定上传目录，避免导入期把路径绑定到 backend/uploads/。
  3. LLM/网络隔离：DEV_MODE=1 + monkeypatch main 里所有会出网的入口
     （detect_mode / recognize_intent / _create_stream_with_fallback /
      find_matches / extract_and_update / detect_matches_and_save）。
"""
import os
import tempfile
import atexit
from pathlib import Path

# Tests use isolated paths and placeholder credentials. Do not let legacy
# module-level dotenv calls inspect backend/.env during collection.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

# 收集测试模块之前固定隔离路径；部分模块在导入时就读取这些环境变量。
_test_paths = tempfile.TemporaryDirectory(prefix="fiona-pytest-")
atexit.register(_test_paths.cleanup)
_isolated_root = Path(_test_paths.name).resolve()
os.environ["FIONA_DB_PATH"] = str(_isolated_root / "test.db")
os.environ["FIONA_UPLOADS_DIR"] = str(_isolated_root / "uploads")
os.environ["FIONA_STUDIO_DIR"] = str(_isolated_root / "studio")
os.environ.setdefault("FIONA_STUDIO_OWNERS", "")
(_isolated_root / "studio").mkdir()

import pytest

from _fakes import FakeStream

# CI / 裸机保障：在收集阶段任何测试模块 import llm/auth 之前注入占位凭据。
# llm.py 在模块顶层构造 DashScope 客户端（缺 DASHSCOPE_API_KEY 直接 OpenAIError），
# auth.py 硬校验 JWT_SECRET（缺失直接 RuntimeError）；CI 不检出 .env，会当场收集崩溃。
# 用 setdefault 注入占位值；本地 .env 不覆盖已有环境变量，避免测试读入真实凭据。
# 测试本身已把出网入口全部打桩（见下方 client fixture），占位 key 不会真出网。
os.environ.setdefault("JWT_SECRET", "fiona-ci-smoke-test-secret-0123456789")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-fiona-ci-smoke-test-not-real")
os.environ.setdefault("FIONA_CRISIS_MODEL_ENABLED", "0")
os.environ.setdefault("FIONA_CHAT_IMAGE_TOOL", "0")
os.environ.setdefault("FIONA_CLAUDE_AGENT", "0")


@pytest.fixture(autouse=True)
def _offline_studio_tests(monkeypatch, request):
    """只隔离工作室测试的外网；回环和其他测试原有的网络桩保持可用。"""
    if not request.node.path.name.startswith("test_studio_"):
        return
    import socket

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_loopback(host):
        if isinstance(host, bytes):
            host = host.decode("ascii", errors="replace")
        return isinstance(host, str) and host.lower() in {"127.0.0.1", "::1", "localhost"}

    def allowed_address(address):
        return isinstance(address, tuple) and bool(address) and is_loopback(address[0])

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not allowed_address(address):
            raise AssertionError("离线测试禁止真实网络连接，请使用模拟传输")
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not allowed_address(address):
            raise AssertionError("离线测试禁止真实网络连接，请使用模拟传输")
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)

    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        original = getattr(socket, name)

        def guarded_resolution(host, *args, _original=original, **kwargs):
            if not is_loopback(host):
                raise AssertionError("离线测试禁止真实 DNS 查询，请使用模拟解析")
            return _original(host, *args, **kwargs)

        monkeypatch.setattr(socket, name, guarded_resolution)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带 DB 隔离 + 全网络打桩的 TestClient。"""
    # DEV_MODE=1：跳过草莓余额/扣费，放行 X-Dev-User 鉴权
    monkeypatch.setenv("DEV_MODE", "1")

    import database
    # 临时库，绝不碰 backend/fiona.db
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))

    import main  # noqa: F401  触发 app 装配
    import studio.scheduler

    async def _idle_studio_scheduler():
        import asyncio
        await asyncio.Event().wait()

    # 测试显式调用单次 tick，后台任务不能抢占测试刚创建的待提交任务。
    monkeypatch.setattr(studio.scheduler, "run_scheduler", _idle_studio_scheduler)
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
    with TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as c:  # 进入即触发 lifespan → init_db() 建临时库
        yield c


@pytest.fixture
def dev_headers():
    """DEV_MODE 下用 X-Dev-User 充当已登录用户。"""
    return {"X-Dev-User": "smoke_tester"}
