"""Proxy headers only affect IP quotas for an explicitly trusted socket peer."""
import pytest
from starlette.requests import Request

from rate_limit import _client_ip


def _request(host, **headers):
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(key.encode(), value.encode()) for key, value in headers.items()],
        "client": (host, 12345) if host is not None else None,
    })


@pytest.mark.parametrize("headers", [
    {"x-real-ip": "198.51.100.1"},
    {"x-forwarded-for": "127.0.0.1,198.51.100.1"},
    {"x-real-ip": "198.51.100.1", "x-forwarded-for": "127.0.0.1"},
])
def test_remote_peer_ignores_forged_headers(monkeypatch, headers):
    monkeypatch.delenv("FIONA_TRUSTED_PROXIES", raising=False)
    assert _client_ip(_request("203.0.113.17", **headers)) == "203.0.113.17"


def test_trusted_loopback_prefers_real_ip_then_last_forwarded_hop(monkeypatch):
    monkeypatch.delenv("FIONA_TRUSTED_PROXIES", raising=False)
    assert _client_ip(_request("127.0.0.1", **{
        "x-real-ip": " 198.51.100.1 ",
        "x-forwarded-for": "forged,203.0.113.2",
    })) == "198.51.100.1"
    assert _client_ip(_request("::1", **{
        "x-forwarded-for": "forged, 203.0.113.2 ",
    })) == "203.0.113.2"


def test_cidr_configuration_is_read_at_call_time(monkeypatch):
    request = _request("10.8.0.2", **{"x-real-ip": "203.0.113.9"})
    monkeypatch.setenv("FIONA_TRUSTED_PROXIES", "10.8.0.0/24,2001:db8::/32")
    assert _client_ip(request) == "203.0.113.9"
    assert _client_ip(_request("2001:db8::2", **{"x-real-ip": "203.0.113.9"})) == "203.0.113.9"
    monkeypatch.setenv("FIONA_TRUSTED_PROXIES", "10.9.0.0/24")
    assert _client_ip(request) == "10.8.0.2"


def test_non_ip_peer_is_an_unchanged_untrusted_key(monkeypatch):
    monkeypatch.setenv("FIONA_TRUSTED_PROXIES", "testclient,not-a-network")
    assert _client_ip(_request("testclient", **{"x-real-ip": "127.0.0.1"})) == "testclient"


def test_ipv4_mapped_ipv6_peer_is_unwrapped_for_trust(monkeypatch):
    monkeypatch.delenv("FIONA_TRUSTED_PROXIES", raising=False)
    assert _client_ip(_request("::ffff:127.0.0.1", **{
        "x-real-ip": "203.0.113.9",
    })) == "203.0.113.9"
    assert _client_ip(_request("::ffff:203.0.113.17", **{
        "x-real-ip": "127.0.0.1",
    })) == "::ffff:203.0.113.17"


def test_missing_peer_retains_loopback_default(monkeypatch):
    monkeypatch.delenv("FIONA_TRUSTED_PROXIES", raising=False)
    assert _client_ip(_request(None)) == "127.0.0.1"


def test_ipv4_mapped_proxy_setting_matches_ipv4_peer(monkeypatch):
    monkeypatch.setenv("FIONA_TRUSTED_PROXIES", "::ffff:127.0.0.1")
    assert _client_ip(_request("127.0.0.1", **{"x-real-ip": "203.0.113.9"})) == "203.0.113.9"
