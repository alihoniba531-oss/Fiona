# -*- coding: utf-8 -*-
"""只允许访问公网 HTTP(S) 的小型客户端。

安全目标：
- 只允许 GET/HEAD 和默认 80/443 端口；
- 拒绝凭据、私网、loopback、链路本地、保留和非全局 IP；
- DNS 校验后直接连接选中的 IP，避免校验与连接之间再次解析造成 rebinding；
- HTTPS 仍用原主机名做 SNI 和证书校验；
- 每一次重定向重新解析并校验；
- 限制重定向次数和解压后的响应体大小。
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import ipaddress
import re
import socket
import ssl
from threading import Timer
import time
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

import urllib3


MAX_URL_LENGTH = 2048
DEFAULT_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_ALLOWED_METHODS = {"GET", "HEAD"}
_SENSITIVE_HEADERS = {"authorization", "cookie", "host", "proxy-authorization"}
# DNS work can remain stuck in the OS resolver after the caller's deadline.
# Leave headroom so a few such lookups cannot queue every other user's fetch.
DNS_RESOLVER_WORKERS = 32
_resolver_pool = ThreadPoolExecutor(max_workers=DNS_RESOLVER_WORKERS, thread_name_prefix="fiona-dns")


class UnsafeUrlError(ValueError):
    """URL 不满足公网访问约束。"""


class ResponseTooLargeError(ValueError):
    """响应体超过调用方允许的大小。"""


class PublicUrlTimeoutError(TimeoutError):
    """公网抓取超过整个调用的墙钟时限。"""


@dataclass(frozen=True)
class PublicUrlTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    host_header: str
    ips: tuple[str, ...]


@dataclass(frozen=True)
class PublicHttpResponse:
    status_code: int
    url: str
    headers: dict[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        return next((value for key, value in self.headers.items() if key.lower() == wanted), None)

    @property
    def text(self) -> str:
        content_type = self.header("content-type") or ""
        match = re.search(r"charset=([^;\s]+)", content_type, re.I)
        encoding = match.group(1).strip("\"'") if match else "utf-8"
        try:
            return self.body.decode(encoding, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class _DeadlineHTTPPool(urllib3.HTTPConnectionPool):
    def _new_conn(self):
        connection = super()._new_conn()
        self._fiona_active_connection = connection
        return connection


class _DeadlineHTTPSPool(urllib3.HTTPSConnectionPool):
    def _new_conn(self):
        connection = super()._new_conn()
        self._fiona_active_connection = connection
        return connection


def _abort_pool_socket(pool: Any) -> None:
    connection = getattr(pool, "_fiona_active_connection", None)
    sock = getattr(connection, "sock", None)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


def _normalize_ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    ip = ipaddress.ip_address(raw)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _resolve_public_ips(hostname: str, port: int) -> tuple[str, ...]:
    # 字面 IP 不应再交给 DNS；否则测试桩、代理解析器或异常 resolver 可能把
    # 127.0.0.1 之类的输入“解释”为另一个公网地址，绕过输入本身的语义。
    try:
        literal_ip = _normalize_ip(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if not literal_ip.is_global:
            raise UnsafeUrlError("目标是非公网 IP")
        return (str(literal_ip),)

    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeUrlError("目标主机 DNS 解析失败") from exc

    resolved: list[str] = []
    for info in infos:
        raw_ip = info[4][0]
        try:
            ip = _normalize_ip(raw_ip)
        except ValueError as exc:
            raise UnsafeUrlError("DNS 返回了无效 IP") from exc
        if not ip.is_global:
            raise UnsafeUrlError("目标主机解析到非公网 IP")
        normalized = str(ip)
        if normalized not in resolved:
            resolved.append(normalized)

    if not resolved:
        raise UnsafeUrlError("目标主机没有可用公网 IP")
    return tuple(resolved)


def validate_public_http_link(url: str) -> str:
    """Validate a displayed external link without contacting its host.

    This is not permission for a server-side fetch: DNS and redirects still need
    resolve_public_url/request_public_url. Search-result links should not require
    our server to access every publisher (proxy DNS and anti-bot rules may differ
    from the user's browser).
    """
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise UnsafeUrlError("URL 长度无效")
    if url.strip() != url or any(ord(char) < 32 for char in url) or "\\" in url:
        raise UnsafeUrlError("URL 包含无效空白或分隔符")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except (ValueError, UnicodeError) as exc:
        raise UnsafeUrlError("URL 格式无效") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not hostname:
        raise UnsafeUrlError("只允许带主机名的 HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL 不能包含用户名或密码")
    if port is not None and port != (443 if scheme == "https" else 80):
        raise UnsafeUrlError("只允许 HTTP(S) 默认端口")
    try:
        literal = _normalize_ip(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeUrlError("目标是非公网 IP")
    else:
        # Also reject browser shorthand numeric IP forms (127.1, 2130706433),
        # encoded host characters, and names reserved for local resolution.
        if ("." not in hostname or not re.fullmatch(r"[a-z0-9.-]+", hostname)
                or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", hostname.rsplit(".", 1)[-1])
                or hostname.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa"))):
            raise UnsafeUrlError("目标不是有效的外部站点")
    return urlunsplit((scheme, parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment))


def resolve_public_url(url: str) -> PublicUrlTarget:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise UnsafeUrlError("URL 长度无效")
    if url.strip() != url:
        raise UnsafeUrlError("URL 不能包含首尾空白")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL 格式无效") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeUrlError("只允许 http/https URL")
    if not parsed.hostname:
        raise UnsafeUrlError("URL 缺少主机名")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL 不能包含用户名或密码")

    default_port = 443 if scheme == "https" else 80
    port = port or default_port
    if port != default_port:
        raise UnsafeUrlError("只允许 HTTP(S) 默认端口")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeUrlError("主机名编码无效") from exc

    ips = _resolve_public_ips(hostname, port)
    path = parsed.path or "/"
    request_target = urlunsplit(("", "", path, parsed.query, ""))
    normalized_url = urlunsplit((scheme, parsed.netloc, path, parsed.query, ""))
    host_for_header = f"[{hostname}]" if ":" in hostname else hostname
    host_header = host_for_header if port == default_port else f"{host_for_header}:{port}"
    return PublicUrlTarget(
        url=normalized_url,
        scheme=scheme,
        hostname=hostname,
        port=port,
        request_target=request_target,
        host_header=host_header,
        ips=ips,
    )


def _open_pinned(
    target: PublicUrlTarget,
    ip: str,
    method: str,
    headers: Mapping[str, str],
    timeout: float,
) -> tuple[Any, Any]:
    timeout_config = urllib3.Timeout(connect=timeout, read=timeout)
    common: dict[str, Any] = {
        "host": ip,
        "port": target.port,
        "timeout": timeout_config,
        "retries": False,
        "maxsize": 1,
        "block": True,
    }
    if target.scheme == "https":
        pool = _DeadlineHTTPSPool(
            **common,
            assert_hostname=target.hostname,
            server_hostname=target.hostname,
            ssl_context=ssl.create_default_context(),
        )
    else:
        pool = _DeadlineHTTPPool(**common)

    # Socket read timeouts are idle timeouts. An absolute watchdog closes the
    # socket even if response headers (or compressed bytes) drip continuously.
    timer = Timer(timeout, _abort_pool_socket, args=(pool,))
    timer.daemon = True
    pool._fiona_deadline_timer = timer
    timer.start()
    try:
        response = pool.urlopen(
            method,
            target.request_target,
            headers=headers,
            redirect=False,
            retries=False,
            preload_content=False,
            decode_content=True,
            assert_same_host=False,
        )
    except BaseException:
        timer.cancel()
        pool.close()
        raise
    return response, pool


def _request_once(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None,
    timeout: float,
    deadline: float,
    max_bytes: int,
) -> PublicHttpResponse:
    remaining = _remaining(deadline)
    # getaddrinfo has no portable cancellation API. Keep resolver work in a
    # small separate pool so its OS timeout cannot retain a fetch worker.
    resolution = _resolver_pool.submit(resolve_public_url, url)
    try:
        target = resolution.result(timeout=remaining)
    except FutureTimeoutError as exc:
        resolution.cancel()
        raise PublicUrlTimeoutError("公网抓取超过总时限") from exc
    remaining = _remaining(deadline)
    outbound_headers = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() not in _SENSITIVE_HEADERS
    }
    outbound_headers["Host"] = target.host_header

    raw = None
    pool = None
    try:
        # 连接这里使用已校验的字面 IP；不会让连接层再次解析 hostname。
        raw, pool = _open_pinned(target, target.ips[0], method, outbound_headers, min(timeout, remaining))
        _remaining(deadline)
        response_headers = {str(key): str(value) for key, value in raw.headers.items()}
        content_length = next(
            (value for key, value in response_headers.items() if key.lower() == "content-length"),
            None,
        )
        # max_bytes=0 表示只验证状态/响应头，不读取响应体。
        if method != "HEAD" and max_bytes > 0 and content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > max_bytes:
                raise ResponseTooLargeError("响应体超过大小限制")

        body = b""
        if method != "HEAD" and max_bytes > 0:
            if not hasattr(raw, "read1"):
                # A few small test doubles implement only the old read API.
                body = raw.read(max_bytes + 1, decode_content=True)
            else:
                chunks: list[bytes] = []
                size = 0
                # read1 returns after one network read rather than waiting for
                # the requested size. A drip feed cannot reset the deadline.
                while True:
                    remaining = _remaining(deadline)
                    _set_response_read_timeout(raw, min(timeout, remaining))
                    chunk = raw.read1(min(16_384, max_bytes + 1 - size), decode_content=True)
                    _remaining(deadline)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > max_bytes:
                        raise ResponseTooLargeError("响应体超过大小限制")
                body = b"".join(chunks)
            if len(body) > max_bytes:
                raise ResponseTooLargeError("响应体超过大小限制")

        return PublicHttpResponse(
            status_code=int(raw.status),
            url=target.url,
            headers=response_headers,
            body=body,
        )
    except (urllib3.exceptions.TimeoutError, socket.timeout) as exc:
        raise PublicUrlTimeoutError("公网抓取超过总时限") from exc
    except Exception as exc:
        if time.monotonic() >= deadline:
            raise PublicUrlTimeoutError("公网抓取超过总时限") from exc
        raise
    finally:
        if raw is not None:
            close = getattr(raw, "close", None)
            if close is not None:
                close()
            raw.release_conn()
        if pool is not None:
            timer = getattr(pool, "_fiona_deadline_timer", None)
            if timer is not None:
                timer.cancel()
            pool.close()


def request_public_url(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 5,
    max_bytes: int = 1_000_000,
    follow_redirects: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> PublicHttpResponse:
    method = method.upper()
    if method not in _ALLOWED_METHODS:
        raise ValueError("safe HTTP client only supports GET/HEAD")
    if timeout <= 0 or max_bytes < 0 or max_redirects < 0:
        raise ValueError("timeout/max_bytes/max_redirects 参数无效")

    deadline = time.monotonic() + timeout
    current_url = url
    for redirect_count in range(max_redirects + 1):
        _remaining(deadline)
        response = _request_once(
            method,
            current_url,
            headers=headers,
            timeout=timeout,
            deadline=deadline,
            max_bytes=max_bytes,
        )
        if not follow_redirects or response.status_code not in _REDIRECT_STATUSES:
            return response

        location = response.header("location")
        if not location:
            return response
        if redirect_count >= max_redirects:
            raise UnsafeUrlError("重定向次数超过限制")
        current_url = urljoin(response.url, location)

    raise UnsafeUrlError("重定向次数超过限制")


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PublicUrlTimeoutError("公网抓取超过总时限")
    return remaining


def _set_response_read_timeout(response: Any, timeout: float) -> None:
    # urllib3 has no public per-chunk timeout setter. Its checked-out socket
    # remains attached to the response until release_conn().
    connection = getattr(response, "connection", None)
    sock = getattr(connection, "sock", None)
    if sock is None:
        sock = getattr(getattr(getattr(response, "_fp", None), "fp", None), "raw", None)
        sock = getattr(sock, "_sock", None)
    if sock is not None:
        sock.settimeout(timeout)
