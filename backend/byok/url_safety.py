"""HTTPS validation and DNS-pinned transport built only on public HTTP APIs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
import ipaddress
import re
import socket
import unicodedata
from threading import Lock
from urllib.parse import urlsplit

import httpcore
import httpx

_DNS_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="fiona-byok-dns")
_DNS_TIMEOUT = 5.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_FORBIDDEN_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".test", ".invalid", ".example", ".onion", ".alt", ".arpa", ".corp", ".home", ".intranet")


class UnsafeUrlError(ValueError):
    def __init__(self):
        super().__init__("须为可公网访问的 HTTPS 地址")


def normalize_custom_base_url(raw) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 512 or any(c.isspace() or unicodedata.category(c) == "Cc" or c == "\\" for c in raw):
        raise UnsafeUrlError
    try:
        parts = urlsplit(raw)
        port = parts.port
        host = (parts.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except (ValueError, UnicodeError):
        raise UnsafeUrlError from None
    if parts.scheme.lower() != "https" or not host or parts.username is not None or parts.password is not None or port not in {None, 443}:
        raise UnsafeUrlError
    # Only hostname text can be Unicode. All other URL components stay ASCII.
    if not parts.scheme.isascii() or not parts.path.isascii() or not parts.netloc.lower().replace(parts.hostname or "", "").isascii():
        raise UnsafeUrlError
    if parts.netloc.endswith(":"):
        raise UnsafeUrlError
    if "?" in raw or "#" in raw or ":" in host or len(host) > 253 or "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
        raise UnsafeUrlError
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeUrlError
    labels = host.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels) or labels[-1].isdigit() or labels[-1].startswith("0x") or host.endswith(_FORBIDDEN_SUFFIXES):
        raise UnsafeUrlError
    path = parts.path
    if len(path) > 256 or (path and not path.startswith("/")) or not re.fullmatch(r"[A-Za-z0-9._~/-]*", path) or ".." in path or "//" in path:
        raise UnsafeUrlError
    normalized = f"https://{host}{path.rstrip('/')}"
    if len(normalized) > 512:
        raise UnsafeUrlError
    return normalized


def _public_ip(raw: str) -> str:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        raise UnsafeUrlError from None
    normalized = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip
    if not normalized.is_global or normalized.is_multicast:
        raise UnsafeUrlError
    if isinstance(ip, ipaddress.IPv6Address) and ip in _NAT64:
        embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if not embedded.is_global or embedded.is_multicast:
            raise UnsafeUrlError
    return str(ip)


def _resolve_public_ips(hostname: str, port: int) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        raise UnsafeUrlError from None
    result = tuple(dict.fromkeys(_public_ip(info[4][0]) for info in infos))
    if not result:
        raise UnsafeUrlError
    return result


def resolve_public_ips(hostname: str, port: int = 443, *, timeout: float | None = None) -> tuple[str, ...]:
    # All answers must be checked, even when the first answer is safe.
    future = _DNS_POOL.submit(_resolve_public_ips, hostname, port)
    try:
        return future.result(timeout=min(_DNS_TIMEOUT, timeout) if timeout is not None else _DNS_TIMEOUT)
    except FutureTimeoutError:
        future.cancel()
        raise httpcore.ConnectTimeout() from None


def validate_custom_base_url(raw) -> str:
    normalized = normalize_custom_base_url(raw)
    try:
        resolve_public_ips(urlsplit(normalized).hostname or "")
    except httpcore.ConnectTimeout:
        raise UnsafeUrlError from None
    return normalized


class _TrackedStream(httpcore.NetworkStream):
    def __init__(self, stream: httpcore.NetworkStream, backend: PinnedPublicBackend, byte_counter: list[int] | None = None):
        self.stream = stream
        self.backend = backend
        self.byte_counter = byte_counter if byte_counter is not None else [0]
        backend.record_stream(self)

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        data = self.stream.read(max_bytes, timeout)
        self.byte_counter[0] += len(data)
        if self.byte_counter[0] > MAX_RESPONSE_BYTES:
            self.backend.abort()
            raise httpcore.ReadError("BYOK response limit exceeded")
        return data

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.stream.write(buffer, timeout)

    def close(self) -> None:
        self.stream.close()

    def start_tls(self, ssl_context, server_hostname: str | None = None, timeout: float | None = None):
        wrapped = self.stream.start_tls(ssl_context, server_hostname=server_hostname, timeout=timeout)
        return _TrackedStream(wrapped, self.backend, self.byte_counter)

    def get_extra_info(self, info: str):
        return self.stream.get_extra_info(info)


class PinnedPublicBackend(httpcore.NetworkBackend):
    def __init__(self, network_backend: httpcore.NetworkBackend | None = None):
        self.network_backend = network_backend if network_backend is not None else httpcore.SyncBackend()
        self.streams: list[_TrackedStream] = []
        self.sockets: list = []
        self.lock = Lock()
        self.aborted = False

    def record_stream(self, stream: _TrackedStream) -> None:
        sock = stream.get_extra_info("socket")
        with self.lock:
            self.streams.append(stream)
            if sock is not None:
                self.sockets.append(sock)
            aborted = self.aborted
        if aborted:
            self.abort()

    def connect_tcp(self, host: str, port: int, timeout: float | None = None, local_address: str | None = None, socket_options=None):
        if port != 443:
            raise UnsafeUrlError
        normalize_custom_base_url(f"https://{host}")
        if self.aborted:
            raise httpcore.ConnectTimeout()
        ips = resolve_public_ips(host, port, timeout=timeout)
        # Pass the validated IP, with no second DNS lookup of the original host.
        stream = self.network_backend.connect_tcp(ips[0], port, timeout=timeout, local_address=local_address, socket_options=socket_options)
        return _TrackedStream(stream, self)

    def connect_unix_socket(self, *args, **kwargs):
        raise UnsafeUrlError

    def sleep(self, seconds: float) -> None:
        self.network_backend.sleep(seconds)

    def abort(self) -> None:
        with self.lock:
            self.aborted = True
            sockets = list(self.sockets)
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


_EXCEPTION_PAIRS = (
    (httpcore.ConnectTimeout, httpx.ConnectTimeout), (httpcore.ReadTimeout, httpx.ReadTimeout),
    (httpcore.WriteTimeout, httpx.WriteTimeout), (httpcore.PoolTimeout, httpx.PoolTimeout),
    (httpcore.ConnectError, httpx.ConnectError), (httpcore.ReadError, httpx.ReadError),
    (httpcore.WriteError, httpx.WriteError), (httpcore.RemoteProtocolError, httpx.RemoteProtocolError),
    (httpcore.LocalProtocolError, httpx.LocalProtocolError), (httpcore.UnsupportedProtocol, httpx.UnsupportedProtocol),
    (httpcore.TimeoutException, httpx.TimeoutException), (httpcore.NetworkError, httpx.NetworkError),
    (httpcore.ProtocolError, httpx.ProtocolError), (UnsafeUrlError, httpx.ConnectError),
)


@contextmanager
def _map_errors():
    try:
        yield
    except Exception as exc:
        for source, target in _EXCEPTION_PAIRS:
            if isinstance(exc, source):
                raise target("BYOK transport failed") from None
        raise


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    def __iter__(self):
        with _map_errors():
            yield from self.stream

    def close(self) -> None:
        with _map_errors():
            self.stream.close()


class PinnedTransport(httpx.BaseTransport):
    def __init__(self, base_url: str, *, network_backend: httpcore.NetworkBackend | None = None):
        self.base_url = normalize_custom_base_url(base_url)
        self.hostname = urlsplit(self.base_url).hostname
        self.backend = PinnedPublicBackend(network_backend)
        self.connection_pool = httpcore.ConnectionPool(network_backend=self.backend, http1=True, http2=False, retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.raw_host.decode("ascii").lower() != self.hostname.lower() or request.url.port not in {None, 443}:
            raise httpx.ConnectError("BYOK transport failed")
        request.headers["Accept-Encoding"] = "identity"
        core_request = httpcore.Request(method=request.method, url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path), headers=request.headers.raw, content=request.stream, extensions=request.extensions)
        with _map_errors():
            response = self.connection_pool.handle_request(core_request)
            encoding = httpx.Headers(response.headers).get("Content-Encoding", "").strip().lower()
            if encoding and encoding != "identity":
                self.backend.abort()
                raise httpcore.ReadError("BYOK encoded response rejected")
        return httpx.Response(response.status, headers=response.headers, stream=_ResponseStream(response.stream), extensions=response.extensions)

    def abort(self) -> None:
        self.backend.abort()

    def close(self) -> None:
        self.connection_pool.close()
