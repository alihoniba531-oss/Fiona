"""Public-API transport exercised through the real OpenAI SDK, entirely offline."""
import base64
import json
import socket
import urllib.request

import httpcore
import httpcore2
import httpx
import httpx2
import openai
import pytest
import requests

from byok import crypto, url_safety
from utils import safe_http


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("network")

    for target, name in ((urllib.request, "urlopen"), (requests, "get"), (safe_http, "_open_pinned"), (socket, "getaddrinfo"), (httpcore.SyncBackend, "connect_tcp"), (httpcore.SyncBackend, "connect_unix_socket"), (httpx.HTTPTransport, "handle_request"), (httpx.AsyncHTTPTransport, "handle_async_request"), (httpx2.HTTPTransport, "handle_request"), (httpx2.AsyncHTTPTransport, "handle_async_request")):
        monkeypatch.setattr(target, name, blocked)
    monkeypatch.setattr(httpcore2.SyncBackend, "connect_tcp", blocked)
    monkeypatch.setattr(httpcore2.SyncBackend, "connect_unix_socket", blocked)
    monkeypatch.setenv("FIONA_BYOK_SECRET", base64.urlsafe_b64encode(b"a" * 32).decode())
    for name in crypto.FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)
    yield
    assert not attempted, "network"


@pytest.mark.parametrize("raw", [
    "http://api.example.net", "https://api.example.net:8443", "https://api.example.net:0",
    "https://127.0.0.1", "https://127.1", "https://2130706433", "https://0x7f000001", "https://[::1]",
    "https://api", "https://api.localhost", "https://api.local", "https://api.internal", "https://api.lan",
    "https://api.home.arpa", "https://api.test", "https://api.invalid", "https://api.example", "https://api.onion", "https://api.alt", "https://api.arpa", "https://api.corp", "https://api.home", "https://api.intranet",
    "https://user:secret@api.example.net", "https://api.example.net\\v1", "https://api.example.net\n/v1",
    "https://api.example.net?q", "https://api.example.net#f", "https://api.example.net?", "https://api.example.net#",
    "https://api.example.net/../v1", "https://api.example.net//v1", "https://api.example.net/%2e/v1",
    "https://api.example.net/路径", "https://-api.example.net", "https://api-.example.net", "https://api..example.net",
    "https://api.0xabcdef", "https://api.123", "https://" + "a" * 64 + ".net",
    "https://" + ".".join(["a" * 63] * 4) + ".net", "https://api.example.net/" + "x" * 257,
    "https://api.example.net/" + "x" * 513, "https://api.example.net/\x7f", "https://api.example.net:", "https://api.example.net/\u0080", None,
])
def test_reject_invalid_addresses(raw):
    with pytest.raises(url_safety.UnsafeUrlError) as exc:
        url_safety.normalize_custom_base_url(raw)
    assert exc.value.args == ("须为可公网访问的 HTTPS 地址",)


@pytest.mark.parametrize("raw,expected", [
    ("HTTPS://API.Example.NET.:443/v1/", "https://api.example.net/v1"),
    ("https://例子.com/v1", "https://xn--fsqu00a.com/v1"),
    ("https://BÜCHER.de/v1", "https://xn--bcher-kva.de/v1"),
    ("https://api.example.net/", "https://api.example.net"),
])
def test_normalization(raw, expected):
    assert url_safety.normalize_custom_base_url(raw) == expected


@pytest.mark.parametrize("ip", ["198.18.0.5", "127.0.0.1", "64:ff9b::a9fe:a9fe", "224.0.0.1", "::ffff:127.0.0.1"])
def test_all_dns_answers_must_be_public(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))])
    with pytest.raises(url_safety.UnsafeUrlError):
        url_safety.validate_custom_base_url("https://api.example.net/v1")


def _response(status=200):
    if status == 302:
        return b"HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    payload = {"id": "offline", "object": "chat.completion.chunk", "created": 0, "model": "unit", "choices": [{"index": 0, "delta": {"content": "好"}, "finish_reason": None}]}
    body = ("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode()
    return b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body


class RecordingBackend(httpcore.MockBackend):
    def __init__(self, status=200):
        super().__init__([_response(status)])
        self.targets = []
        self.server_names = []

    def connect_tcp(self, host, port, **kwargs):
        self.targets.append((host, port))
        stream = super().connect_tcp(host, port, **kwargs)
        original = stream.start_tls

        def tls(ssl_context, server_hostname=None, timeout=None):
            self.server_names.append(server_hostname)
            return original(ssl_context, server_hostname, timeout)
        stream.start_tls = tls
        return stream


def _sdk(transport):
    return openai.OpenAI(api_key="sk-offline-1234", base_url="https://api.example.net/v1", timeout=1, max_retries=0, http_client=httpx.Client(transport=transport, follow_redirects=False, trust_env=False, timeout=1))


def _request(client):
    return client.chat.completions.create(model="unit", messages=[{"role": "user", "content": "test"}], stream=True, max_tokens=16)


def test_actual_sdk_connects_ip_preserves_sni_ignores_proxy_and_rechecks_dns(monkeypatch):
    answers = iter([("8.8.8.8",), ("127.0.0.1",)])
    calls = []

    def dns(host, port):
        calls.append((host, port))
        return tuple(url_safety._public_ip(ip) for ip in next(answers))
    monkeypatch.setattr(url_safety, "_resolve_public_ips", dns)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:4444")
    backend = RecordingBackend()
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=backend)
    with _sdk(transport) as client:
        stream = _request(client)
        assert "".join(chunk.choices[0].delta.content or "" for chunk in stream) == "好"
        stream.close()
        with pytest.raises(openai.APIConnectionError):
            _request(client)
    assert calls == [("api.example.net", 443), ("api.example.net", 443)]
    assert backend.targets == [("8.8.8.8", 443)]
    assert backend.server_names == ["api.example.net"]


def test_redirect_is_not_followed(monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    backend = RecordingBackend(status=302)
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=backend)
    with _sdk(transport) as client:
        with pytest.raises(openai.APIStatusError) as exc:
            _request(client)
    assert exc.value.status_code == 302
    assert backend.targets == [("8.8.8.8", 443)]


@pytest.mark.parametrize("failure", [httpcore.ConnectTimeout, httpcore.ReadTimeout])
def test_timeout_mapping_reaches_openai(monkeypatch, failure):
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))

    class TimeoutBackend(httpcore.MockBackend):
        def connect_tcp(self, *a, **k):
            raise failure()
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=TimeoutBackend([]))
    with _sdk(transport) as client:
        with pytest.raises(openai.APITimeoutError):
            _request(client)


def test_unix_socket_rejected_without_network():
    with pytest.raises(url_safety.UnsafeUrlError):
        url_safety.PinnedPublicBackend().connect_unix_socket("/tmp/service.sock")


def test_abort_records_and_shuts_down_socket_before_close(monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    events = []

    class Socket:
        def shutdown(self, how):
            events.append(("shutdown", how))

        def close(self):
            events.append(("socket_close", None))

    class SocketBackend(RecordingBackend):
        def connect_tcp(self, host, port, **kwargs):
            stream = super().connect_tcp(host, port, **kwargs)
            original = stream.get_extra_info
            stream.get_extra_info = lambda name: Socket() if name == "socket" else original(name)
            original_close = stream.close

            def close():
                events.append(("stream_close", None))
                original_close()
            stream.close = close
            return stream
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=SocketBackend())
    with _sdk(transport) as sdk:
        stream = _request(sdk)
        assert transport.backend.sockets
        transport.abort()
        interrupted = list(events)
        assert all(event[0] == "shutdown" for event in interrupted)
        stream.close()
    assert events[0] == ("shutdown", socket.SHUT_RDWR)
    assert not any(event[0] == "socket_close" for event in interrupted)
    assert any(event[0] == "stream_close" for event in events)


def test_dns_timeout_at_connection_maps_to_sdk_timeout(monkeypatch):
    class TimeoutFuture:
        def result(self, timeout):
            raise TimeoutError

        def cancel(self):
            pass
    monkeypatch.setattr(url_safety._DNS_POOL, "submit", lambda *a: TimeoutFuture())
    backend = RecordingBackend()
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=backend)
    with _sdk(transport) as sdk:
        with pytest.raises(openai.APITimeoutError):
            _request(sdk)
    assert not backend.targets


@pytest.mark.parametrize("url", ["https://例子.com/v1", "https://xn--fsqu00a.com/v1"])
def test_r1_idna_actual_sdk_stream(monkeypatch, url):
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    backend = RecordingBackend()
    transport = url_safety.PinnedTransport(url, network_backend=backend)
    with openai.OpenAI(api_key="sk-offline-1234", base_url=url, timeout=1, max_retries=0,
                       http_client=httpx.Client(transport=transport, follow_redirects=False, trust_env=False, timeout=1)) as sdk:
        stream = _request(sdk)
        assert "".join(chunk.choices[0].delta.content or "" for chunk in stream) == "好"
        stream.close()
    assert backend.targets == [("8.8.8.8", 443)]
    assert backend.server_names == ["xn--fsqu00a.com"]


@pytest.mark.parametrize("status", [200, 401])
def test_r1_custom_response_bytes_are_bounded(monkeypatch, status):
    from byok.errors import error_category, error_message
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    limit, block_size = 4 * 1024 * 1024, 64 * 1024
    sent = []

    class EndlessBackend(httpcore.MockBackend):
        def connect_tcp(self, *args, **kwargs):
            stream = super().connect_tcp(*args, **kwargs)
            header = f"HTTP/1.1 {status} Test\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n".encode()
            first = True

            def read(max_bytes, timeout=None):
                nonlocal first
                # Continually supply bytes; fail promptly if the production cap
                # is removed, without allowing a broken test to allocate forever.
                assert sum(sent) <= limit + block_size, "upstream read continued beyond the cap"
                data = header if first else b"x" * block_size
                first = False
                sent.append(len(data))
                return data
            stream.read = read
            return stream
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=EndlessBackend([]))
    with _sdk(transport) as sdk:
        try:
            stream = _request(sdk)
            list(stream)
        except Exception as exc:
            category, message = error_category(exc), error_message(exc)
        else:
            category, message = "no_error", ""
    assert sum(sent) <= limit + block_size
    assert transport.backend.aborted
    assert category == "connection"
    assert message == "你的模型调用失败：连不上该服务。本条没有改用平台模型。"


def test_r2_custom_interrupt_only_shuts_down_until_owner_close(monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    events = []

    class Sock:
        def shutdown(self, how):
            events.append("shutdown")
            assert how == socket.SHUT_RDWR

        def close(self):
            events.append("socket_close")

    class Backend(RecordingBackend):
        def connect_tcp(self, *args, **kwargs):
            stream = super().connect_tcp(*args, **kwargs)
            original_close = stream.close
            stream.get_extra_info = lambda name: Sock() if name == "socket" else None

            def close():
                events.append("stream_close")
                original_close()
            stream.close = close
            return stream

    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=Backend())
    with _sdk(transport) as sdk:
        stream = _request(sdk)
        transport.abort()
        assert transport.backend.aborted
        assert events == ["shutdown", "shutdown"]  # HTTP and TLS wrappers record the same connection.
        stream.close()
        assert "stream_close" in events
    assert "socket_close" not in events  # The NetworkStream owns the socket lifecycle.


@pytest.mark.parametrize("requested", [None, "gzip, deflate", "br", "GZIP"])
def test_r2_custom_forces_identity_request_encoding(monkeypatch, requested):
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    writes = []

    class Backend(RecordingBackend):
        def connect_tcp(self, *args, **kwargs):
            stream = super().connect_tcp(*args, **kwargs)
            stream.write = lambda buffer, timeout=None: writes.append(buffer)
            return stream

    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=Backend())
    with httpx.Client(transport=transport, trust_env=False) as sdk:
        headers = {} if requested is None else {"Accept-Encoding": requested}
        response = sdk.get("https://api.example.net/v1", headers=headers)
        assert response.status_code == 200
    header_lines = b"".join(writes).split(b"\r\n")
    assert [line.lower() for line in header_lines if line.lower().startswith(b"accept-encoding:")] == [b"accept-encoding: identity"]


@pytest.mark.parametrize("encoding", ["gzip", "GZip", "deflate", "br", "gzip, identity"])
def test_r2_custom_rejects_encoding_before_gzip_bomb_decode(monkeypatch, encoding):
    import tracemalloc
    import zlib
    from httpx import _decoders
    from byok.errors import error_category, error_message

    # Build 64 MiB worth of text without allocating that plaintext all at once.
    compressor = zlib.compressobj(wbits=31)
    block = b"x" * (1024 * 1024)
    compressed = b"".join(compressor.compress(block) for _ in range(64)) + compressor.flush()
    assert len(compressed) < 128 * 1024
    decode_calls = []

    def forbidden_decode(self, data):
        # Fail before a broken implementation can allocate 64 MiB. A successful
        # production guard must reject the response before any decoder is used.
        decode_calls.append(len(data))
        raise AssertionError("compressed BYOK body reached a decoder")

    for decoder in (_decoders.GZipDecoder, _decoders.DeflateDecoder, _decoders.BrotliDecoder):
        monkeypatch.setattr(decoder, "decode", forbidden_decode)
    monkeypatch.setattr(url_safety, "_resolve_public_ips", lambda *a: ("8.8.8.8",))
    header = b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Encoding: " + encoding.encode() + b"\r\nContent-Length: " + str(len(compressed)).encode() + b"\r\nConnection: close\r\n\r\n"
    transport = url_safety.PinnedTransport("https://api.example.net/v1", network_backend=httpcore.MockBackend([header, compressed]))
    tracemalloc.start()
    try:
        with _sdk(transport) as sdk:
            with pytest.raises(openai.APIConnectionError) as caught:
                stream = _request(sdk)
                list(stream)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert error_category(caught.value) == "connection"
    assert error_message(caught.value) == "你的模型调用失败：连不上该服务。本条没有改用平台模型。"
    assert transport.backend.aborted
    assert decode_calls == []
    assert peak < 16 * 1024 * 1024
