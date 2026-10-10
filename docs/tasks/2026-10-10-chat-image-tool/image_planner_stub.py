"""Offline R1 acceptance plugin; load with pytest -p image_planner_stub.

Only baseline test files receive the fixed planner decision. The task's new
tests retain their own real, mocked planner implementation and may override
this fixture explicitly. Importing this module does not import the app or SDK.
"""
from pathlib import Path
import socket

import pytest


_TASK_TEST_FILES = frozenset({
    "test_chat_image_tool.py",
    "test_byok_image_tool.py",
    "test_chat_image_tool_docs.py",
    "test_chat_image_tool_frontend.py",
    "test_image_planner.py",
    "test_byok_planner_r1.py",
    "test_chat_image_tool_headers.py",
})


def is_task_test(path) -> bool:
    return Path(path).name in _TASK_TEST_FILES


@pytest.fixture(autouse=True)
def image_planner_acceptance_stub(monkeypatch, request):
    if is_task_test(request.node.path):
        return
    # conftest has set placeholder credentials before this fixture runs.
    import services.chat_service as chat

    async def no_image(history, message):
        return {"status": "no"}

    monkeypatch.setattr(chat, "plan_image", no_image)


@pytest.fixture(autouse=True)
def offline_network_guard(monkeypatch):
    # MockTransport, ASGI TestClient and AF_UNIX event-loop IPC remain usable.
    # Tests that deliberately replace the network functions with fakes can
    # still do so through their own monkeypatch fixtures.
    def guarded(original):
        def connect(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise RuntimeError("R1/R2 验收禁止真实网络请求")
            return original(sock, *args, **kwargs)
        return connect

    def no_dns(*args, **kwargs):
        raise RuntimeError("R1/R2 验收禁止真实网络请求")

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
