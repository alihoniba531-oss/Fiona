# -*- coding: utf-8 -*-
import socket

import pytest

from utils import safe_http


def _dns_answer(*ips: str):
    return [
        (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
        for ip in ips
    ]


class _FakePool:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeRaw:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self.released = False

    def read(self, amount, decode_content=True):
        return self._body[:amount]

    def release_conn(self):
        self.released = True


def test_rejects_literal_private_and_metadata_addresses():
    for url in [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
        "http://[::1]/",
    ]:
        with pytest.raises(safe_http.UnsafeUrlError):
            safe_http.resolve_public_url(url)


def test_rejects_dns_with_any_private_answer(monkeypatch):
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _dns_answer("93.184.216.34", "127.0.0.1"),
    )
    with pytest.raises(safe_http.UnsafeUrlError):
        safe_http.resolve_public_url("https://example.com/")


def test_connection_is_pinned_to_validated_ip_and_keeps_host(monkeypatch):
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _dns_answer("93.184.216.34"),
    )
    captured = {}

    def fake_open(target, ip, method, headers, timeout):
        captured.update(target=target, ip=ip, method=method, headers=headers, timeout=timeout)
        return _FakeRaw(headers={"Content-Type": "text/plain; charset=utf-8"}, body="正常".encode()), _FakePool()

    monkeypatch.setattr(safe_http, "_open_pinned", fake_open)
    response = safe_http.request_public_url("GET", "https://example.com/news?q=1")

    assert response.text == "正常"
    assert captured["ip"] == "93.184.216.34"
    assert captured["target"].hostname == "example.com"
    assert captured["headers"]["Host"] == "example.com"
    assert captured["target"].request_target == "/news?q=1"


def test_redirect_is_revalidated_before_second_connection(monkeypatch):
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _dns_answer("93.184.216.34"),
    )
    calls = []

    def fake_open(target, ip, method, headers, timeout):
        calls.append(target.url)
        return _FakeRaw(status=302, headers={"Location": "http://127.0.0.1/admin"}), _FakePool()

    monkeypatch.setattr(safe_http, "_open_pinned", fake_open)
    with pytest.raises(safe_http.UnsafeUrlError):
        safe_http.request_public_url(
            "HEAD",
            "https://example.com/start",
            follow_redirects=True,
        )
    assert calls == ["https://example.com/start"]


def test_response_body_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _dns_answer("93.184.216.34"),
    )
    monkeypatch.setattr(
        safe_http,
        "_open_pinned",
        lambda *args, **kwargs: (_FakeRaw(body=b"12345"), _FakePool()),
    )
    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.request_public_url("GET", "https://example.com/", max_bytes=4)


def test_rejects_credentials_nonstandard_ports_and_unsafe_schemes(monkeypatch):
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _dns_answer("93.184.216.34"),
    )
    for url in [
        "https://user:secret@example.com/",
        "https://example.com:8443/",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ]:
        with pytest.raises(safe_http.UnsafeUrlError):
            safe_http.resolve_public_url(url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/private", "http://127.1/private", "http://2130706433/private",
    "http://0x7f.0x0.0x0.0x1/private",
    "https://localhost/", "https://printer.local/", "http://[::1]/",
    "https://user:secret@example.com/", "https://example.com:8443/",
    "https://example.com:0/", "javascript:alert(1)", "file:///etc/passwd",
    "https://example.com\\@127.0.0.1/", "https://example.com/\nsecret",
])
def test_display_link_validation_rejects_unsafe_url_forms(url):
    with pytest.raises(safe_http.UnsafeUrlError):
        safe_http.validate_public_http_link(url)


def test_display_links_do_not_weaken_fetch_dns_checks(monkeypatch):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", lambda *a, **k: _dns_answer("198.18.0.5"))
    url = "https://example.com/news#details"
    assert safe_http.validate_public_http_link(url) == url
    with pytest.raises(safe_http.UnsafeUrlError):
        safe_http.request_public_url("HEAD", url)
