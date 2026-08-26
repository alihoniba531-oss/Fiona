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
import ipaddress
import re
import socket
import ssl
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

import urllib3


MAX_URL_LENGTH = 2048
DEFAULT_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_ALLOWED_METHODS = {"GET", "HEAD"}
_SENSITIVE_HEADERS = {"authorization", "cookie", "host", "proxy-authorization"}


class UnsafeUrlError(ValueError):
    """URL 不满足公网访问约束。"""


class ResponseTooLargeError(ValueError):
    """响应体超过调用方允许的大小。"""


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
        pool = urllib3.HTTPSConnectionPool(
            **common,
            assert_hostname=target.hostname,
            server_hostname=target.hostname,
            ssl_context=ssl.create_default_context(),
        )
    else:
        pool = urllib3.HTTPConnectionPool(**common)

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
    return response, pool


def _request_once(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None,
    timeout: float,
    max_bytes: int,
) -> PublicHttpResponse:
    target = resolve_public_url(url)
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
        raw, pool = _open_pinned(target, target.ips[0], method, outbound_headers, timeout)
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
            body = raw.read(max_bytes + 1, decode_content=True)
            if len(body) > max_bytes:
                raise ResponseTooLargeError("响应体超过大小限制")

        return PublicHttpResponse(
            status_code=int(raw.status),
            url=target.url,
            headers=response_headers,
            body=body,
        )
    finally:
        if raw is not None:
            raw.release_conn()
        if pool is not None:
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

    current_url = url
    for redirect_count in range(max_redirects + 1):
        response = _request_once(
            method,
            current_url,
            headers=headers,
            timeout=timeout,
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
