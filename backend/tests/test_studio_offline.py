"""工作室断网钩子的作用域及回环白名单；所有底层调用均为模拟。"""

from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

import conftest


def _install(monkeypatch, filename="test_studio_offline.py"):
    calls = []

    def original(*args, **kwargs):
        calls.append((args, kwargs))
        return "simulated"

    names = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr")
    for name in names:
        monkeypatch.setattr(socket, name, original)
    monkeypatch.setattr(socket.socket, "connect", original)
    monkeypatch.setattr(socket.socket, "connect_ex", original)
    request = SimpleNamespace(node=SimpleNamespace(path=Path(filename)))
    conftest._offline_studio_tests.__wrapped__(monkeypatch, request)
    return calls, original


@pytest.mark.parametrize("filename", ["test_byok_client.py", "test_exchange_isolation.py", "test_safe_http_deadline.py", "test_other.py"])
def test_offline_hook_leaves_non_studio_tests_untouched(monkeypatch, filename):
    calls, original = _install(monkeypatch, filename)
    assert socket.socket.connect is original
    assert socket.socket.connect_ex is original
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        assert getattr(socket, name) is original
    assert calls == []


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_offline_hook_allows_loopback_connections(monkeypatch, host, method):
    calls, _ = _install(monkeypatch)
    sock = SimpleNamespace(family=socket.AF_INET6 if host == "::1" else socket.AF_INET)
    address = (host, 12345)
    assert getattr(socket.socket, method)(sock, address) == "simulated"
    assert calls == [((sock, address), {})]


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
@pytest.mark.parametrize("method", ["getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"])
def test_offline_hook_allows_loopback_resolution(monkeypatch, host, method):
    calls, _ = _install(monkeypatch)
    assert getattr(socket, method)(host) == "simulated"
    assert calls == [((host,), {})]


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_offline_hook_blocks_external_connections_before_transport(monkeypatch, method):
    calls, _ = _install(monkeypatch)
    with pytest.raises(AssertionError, match="禁止真实网络连接"):
        getattr(socket.socket, method)(SimpleNamespace(family=socket.AF_INET), ("203.0.113.1", 443))
    assert calls == []


@pytest.mark.parametrize("method", ["getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"])
def test_offline_hook_blocks_external_resolution_before_dns(monkeypatch, method):
    calls, _ = _install(monkeypatch)
    with pytest.raises(AssertionError, match="禁止真实 DNS"):
        getattr(socket, method)("upstream.example")
    assert calls == []
