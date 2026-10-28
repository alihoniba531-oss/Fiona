#!/usr/bin/env python3
"""Route smoke test for the Fiona frontend.

Starts a stub backend (Python's http.server serving a file named ``health``
whose body is exactly ``fiona-stub-ok``) and a production ``next start``
server, then requests a fixed list of routes without following redirects and
records the status code, ``Location`` and the three security headers that
``next.config.ts`` installs.  The result is written as deterministic JSON so
two runs against the same build can be compared byte for byte.

Standard library only.  No local absolute paths are baked in: the frontend
directory and output path are command line arguments, and the ports and
timeouts come from command line arguments too.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

NO_COOKIE_PATHS = [
    "/",
    "/login",
    "/history",
    "/settings",
    "/agents/abc",
    "/novels/abc",
    "/studio/abc",
]

COOKIE_PATHS = [
    "/",
    "/login",
    "/history",
    "/agents/abc",
    "/novels/abc",
    "/studio/abc",
    "/novels?embed=1",
]

RECORDED_HEADERS = [
    "Content-Security-Policy",
    "X-Frame-Options",
    "Permissions-Policy",
]

HEALTH_PATH = "/api/health"
HEALTH_BODY = "fiona-stub-ok"
COOKIE_HEADER = "fiona_token=x"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test Fiona frontend routes against a stub backend."
    )
    parser.add_argument(
        "--frontend-dir",
        default=os.environ.get("FIONA_FRONTEND_DIR"),
        help="Path to the frontend directory (env: FIONA_FRONTEND_DIR).",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("FIONA_ROUTE_SMOKE_OUTPUT"),
        help="Path of the JSON result file (env: FIONA_ROUTE_SMOKE_OUTPUT).",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=int(os.environ.get("FIONA_FRONTEND_PORT", "3091")),
        help="Port for next start (default: 3091).",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=int(os.environ.get("FIONA_BACKEND_PORT", "8091")),
        help="Port for the stub backend (default: 8091).",
    )
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=float(os.environ.get("FIONA_ROUTE_SMOKE_START_TIMEOUT", "120")),
        help="Seconds to wait for each server to become ready (default: 120).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=float(os.environ.get("FIONA_ROUTE_SMOKE_REQUEST_TIMEOUT", "30")),
        help="Socket timeout for a single request in seconds (default: 30).",
    )
    args = parser.parse_args(argv)
    if not args.frontend_dir:
        parser.error("--frontend-dir is required (or set FIONA_FRONTEND_DIR)")
    if not args.output:
        parser.error("--output is required (or set FIONA_ROUTE_SMOKE_OUTPUT)")
    return args


def http_get(
    port: int, path: str, cookie: str | None, timeout: float
) -> tuple[int, str | None, dict[str, str | None], bytes]:
    """GET without following redirects.

    Returns status, Location, the recorded security headers and the body.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        headers = {"Cookie": cookie} if cookie else {}
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        body = response.read()
        recorded = {name: response.getheader(name) for name in RECORDED_HEADERS}
        return response.status, response.getheader("Location"), recorded, body
    finally:
        conn.close()


def wait_for_http(
    port: int, path: str, timeout: float, child: subprocess.Popen[bytes]
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return False
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                conn.request("GET", path)
                conn.getresponse().read()
                return True
            finally:
                conn.close()
        except (ConnectionError, OSError):
            time.sleep(0.2)
    return False


def log_tail(log_path: str, limit: int = 4000) -> str:
    try:
        with open(log_path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        return f"<could not read log: {exc}>"
    if len(data) > limit:
        data = data[-limit:]
    return data.decode("utf-8", "replace")


def stop_process(proc: subprocess.Popen[bytes] | None) -> None:
    """Stop only the process group we started ourselves."""
    if proc is None or proc.poll() is not None:
        return
    try:
        # start_new_session=True made this pid the leader of its own group.
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def write_result(output: str, payload: dict[str, Any]) -> None:
    output_dir = os.path.dirname(os.path.abspath(output))
    os.makedirs(output_dir, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with open(output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def record_case(
    result: dict[str, Any],
    port: int,
    path: str,
    cookie: str | None,
    request_timeout: float,
) -> None:
    status, location, headers, body = http_get(port, path, cookie, request_timeout)
    case: dict[str, Any] = {
        "path": path,
        "cookie": cookie is not None,
        "status": status,
        "location": location,
        "headers": headers,
    }
    if path == HEALTH_PATH:
        case["body"] = body.decode("utf-8", "replace")
    result["cases"].append(case)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    frontend_dir = os.path.abspath(args.frontend_dir)
    if not os.path.isdir(frontend_dir):
        print(f"frontend dir not found: {frontend_dir}", file=sys.stderr)
        return 2

    npx = shutil.which("npx")
    if npx is None:
        print("npx not found on PATH", file=sys.stderr)
        return 2

    result: dict[str, Any] = {"cases": [], "errors": []}

    tmpdir = tempfile.mkdtemp(prefix="fiona-route-smoke-")
    stub_dir = os.path.join(tmpdir, "stub")
    os.makedirs(stub_dir, exist_ok=True)
    # Exactly these bytes, no trailing newline, no file extension.
    with open(os.path.join(stub_dir, "health"), "wb") as handle:
        handle.write(HEALTH_BODY.encode("ascii"))

    backend_log = os.path.join(tmpdir, "backend.log")
    frontend_log = os.path.join(tmpdir, "frontend.log")
    backend: subprocess.Popen[bytes] | None = None
    frontend: subprocess.Popen[bytes] | None = None
    backend_log_handle = None
    frontend_log_handle = None

    try:
        backend_log_handle = open(backend_log, "wb")
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(args.backend_port),
                "--bind",
                "127.0.0.1",
            ],
            cwd=stub_dir,
            stdin=subprocess.DEVNULL,
            stdout=backend_log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if not wait_for_http(
            args.backend_port, "/health", min(args.start_timeout, 15), backend
        ):
            result["errors"].append(
                "stub backend did not become ready: " + log_tail(backend_log)
            )

        env = os.environ.copy()
        env["FIONA_BACKEND_ORIGIN"] = f"http://127.0.0.1:{args.backend_port}"
        env.pop("NODE_ENV", None)
        env.pop("FIONA_ALLOWED_DEV_ORIGINS", None)
        env.pop("NEXT_PUBLIC_API_BASE", None)
        frontend_log_handle = open(frontend_log, "wb")
        frontend = subprocess.Popen(
            [
                npx,
                "--no-install",
                "next",
                "start",
                "-p",
                str(args.frontend_port),
                "-H",
                "127.0.0.1",
            ],
            cwd=frontend_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=frontend_log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if not wait_for_http(
            args.frontend_port, "/login", args.start_timeout, frontend
        ):
            result["errors"].append(
                "frontend did not become ready: " + log_tail(frontend_log)
            )
        else:
            for path in NO_COOKIE_PATHS:
                record_case(result, args.frontend_port, path, None, args.request_timeout)
            for path in COOKIE_PATHS:
                record_case(
                    result,
                    args.frontend_port,
                    path,
                    COOKIE_HEADER,
                    args.request_timeout,
                )
            record_case(
                result, args.frontend_port, HEALTH_PATH, None, args.request_timeout
            )
    finally:
        stop_process(frontend)
        stop_process(backend)
        if frontend_log_handle is not None:
            frontend_log_handle.close()
        if backend_log_handle is not None:
            backend_log_handle.close()
        write_result(args.output, result)

    if result["errors"]:
        print("route smoke completed with errors:", file=sys.stderr)
        for error in result["errors"]:
            print(error, file=sys.stderr)
        print(f"logs kept in {tmpdir}", file=sys.stderr)
        return 1
    print(f"wrote {len(result['cases'])} cases to {args.output}")
    print(f"logs kept in {tmpdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
