"""Offline documentation contract for the macOS local watcher."""
from pathlib import Path
import re
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md", "backend/.env.example",
)


@pytest.fixture(scope="module", autouse=True)
def block_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Local watch documentation tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


@pytest.mark.parametrize("filename", DOCUMENTS)
def test_documents_explain_data_flow_controls_token_privacy_and_limits(filename):
    text = (ROOT / filename).read_text()
    for phrase in (
        "本机监控", "本机 OCR", "只上报新增行", "判断", "写进聊天",
        "FIONA_LOCAL_WATCH", "FIONA_DAILY_WATCH_JUDGE", "500", "令牌",
        "只显示一次", "哈希", "600", "吊销", "不落日志", "提醒摘要",
        "阿里云千问", "Anthropic", "只支持 macOS", "窗口最小化后截不到",
        "OCR 可能有错字", "只能看到窗口当前显示的内容",
        "Fiona 页面关闭时不会实时弹出，但提醒照样落库",
    ):
        assert phrase in text, f"{filename}: missing {phrase}"
    assert not re.search(r"/Users/|/home/[^\s]+|[A-Z]:\\(?:Users|Documents)\\", text)


def test_env_declares_local_watch_defaults():
    text = (ROOT / "backend/.env.example").read_text()
    assert re.search(r"^FIONA_LOCAL_WATCH=1$", text, re.M)
    assert re.search(r"^FIONA_DAILY_WATCH_JUDGE=500$", text, re.M)
