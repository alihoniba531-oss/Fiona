"""A drip response must not hold a fetch worker beyond its total deadline."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Thread
import time
from urllib.parse import urlsplit

import pytest

from utils import safe_http


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/header-drip":
            try:
                self.connection.sendall(b"HTTP/1.1 200 OK\r\nX-Drip: ")
                for _ in range(20):
                    self.connection.sendall(b"x")
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/fast")
            self.end_headers()
        elif self.path == "/fast":
            body = b"fast response"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            for _ in range(20):
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(0.5)


@pytest.fixture
def local_fetch_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def resolved(url):
        parsed = urlsplit(url)
        return safe_http.PublicUrlTarget(
            url=url, scheme="http", hostname="public.example", port=port,
            request_target=parsed.path, host_header="public.example",
            ips=("127.0.0.1",),
        )

    monkeypatch.setattr(safe_http, "resolve_public_url", resolved)
    try:
        yield "http://public.example"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_drip_response_obeys_total_wall_clock_deadline(local_fetch_server):
    started = time.monotonic()
    with pytest.raises(safe_http.PublicUrlTimeoutError, match="总时限"):
        safe_http.request_public_url("GET", local_fetch_server + "/drip", timeout=2, max_bytes=200000)
    assert time.monotonic() - started < 3


def test_fast_response_and_redirect_still_work(local_fetch_server):
    response = safe_http.request_public_url(
        "GET", local_fetch_server + "/redirect", timeout=2, follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.body == b"fast response"
    assert response.url == local_fetch_server + "/fast"


def test_drip_headers_obey_total_wall_clock_deadline(local_fetch_server):
    started = time.monotonic()
    with pytest.raises(safe_http.PublicUrlTimeoutError, match="总时限"):
        safe_http.request_public_url("GET", local_fetch_server + "/header-drip", timeout=2)
    assert time.monotonic() - started < 3


def test_slow_resolution_obeys_total_wall_clock_deadline(monkeypatch):
    def slow_resolution(_url):
        time.sleep(1)
        raise AssertionError("resolution finished after the deadline")

    monkeypatch.setattr(safe_http, "resolve_public_url", slow_resolution)
    started = time.monotonic()
    with pytest.raises(safe_http.PublicUrlTimeoutError, match="总时限"):
        safe_http.request_public_url("GET", "http://public.example/", timeout=0.2)
    assert time.monotonic() - started < 0.6


def test_four_stuck_resolutions_do_not_block_another_fetch(local_fetch_server, monkeypatch):
    resolved = safe_http.resolve_public_url
    all_started = Barrier(5)
    release = Event()

    def blocked_resolution(url):
        if "/blocked-" in url:
            all_started.wait(timeout=2)
            release.wait(timeout=5)
            raise AssertionError("abandoned resolver must not be used")
        return resolved(url)

    monkeypatch.setattr(safe_http, "resolve_public_url", blocked_resolution)
    with ThreadPoolExecutor(max_workers=4) as callers:
        blocked = [
            callers.submit(
                safe_http.request_public_url,
                "GET", f"{local_fetch_server}/blocked-{index}", timeout=0.4,
            )
            for index in range(4)
        ]
        try:
            all_started.wait(timeout=2)
            response = safe_http.request_public_url(
                "GET", local_fetch_server + "/fast", timeout=0.8,
            )
            assert response.status_code == 200
            assert response.body == b"fast response"
            for task in blocked:
                with pytest.raises(safe_http.PublicUrlTimeoutError):
                    task.result(timeout=2)
        finally:
            release.set()
