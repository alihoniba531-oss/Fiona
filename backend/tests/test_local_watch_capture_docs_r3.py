"""Offline documentation checks for capture outages when a Mac is locked."""
from pathlib import Path
import re
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md", "backend/.env.example", "watcher-mac/README.md",
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Capture documentation tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


@pytest.mark.parametrize("filename", DOCUMENTS)
def test_capture_outage_and_lock_screen_security_guidance(filename):
    text = (ROOT / filename).read_text()
    assert "屏幕锁定或显示器休眠时 macOS 不允许截取窗口，期间无法监控" in text
    assert "系统设置 → 锁定屏幕" in text
    assert "延长自动锁定时间" in text
    assert "自行权衡安全" in text
    assert not re.search(r"/Users/|/home/[^\s]+|[A-Z]:\\(?:Users|Documents)\\", text)
