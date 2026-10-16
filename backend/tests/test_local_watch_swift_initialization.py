"""Offline source contracts for the command-line screenshot initialization."""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WATCHER = ROOT / "watcher-mac/Sources/FionaWatcherCore/Watcher.swift"
SOURCES = ROOT / "watcher-mac/Sources"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Local watch initialization tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def braced_body(source, declaration):
    """Return the balanced body of a Swift declaration in these source files."""
    start = source.index(declaration)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[opening + 1:end - 1]


def test_application_initialization_is_main_actor_isolated_and_once_only():
    source = WATCHER.read_text(encoding="utf-8")
    assert "import AppKit" in source
    assert re.search(r"@MainActor\s+private enum ScreenCaptureApplication", source)
    application = braced_body(source, "private enum ScreenCaptureApplication")
    # A static let is initialized lazily once, including concurrent callers.
    assert re.search(r"private static let initialized:\s*Void\s*=\s*\{", application)
    initialization = braced_body(application, "private static let initialized")
    assert [line.strip() for line in initialization.strip().splitlines()] == [
        "_ = NSApplication.shared",
        "NSApplication.shared.setActivationPolicy(.prohibited)",
    ]
    assert braced_body(application, "static func initialize()").strip() == "_ = initialized"
    assert source.count("NSApplication.shared.setActivationPolicy(.prohibited)") == 1


def test_run_initializes_before_starting_any_watch_tasks():
    source = WATCHER.read_text(encoding="utf-8")
    body = braced_body(source, "public func run() async throws")
    assert body.strip().startswith("await ScreenCaptureApplication.initialize()")
    assert body.index("await ScreenCaptureApplication.initialize()") < body.index("withThrowingTaskGroup")


def test_every_capture_entry_initializes_before_screenshot():
    capture_entries = []
    for path in SOURCES.rglob("*.swift"):
        source = path.read_text(encoding="utf-8")
        for declaration in re.finditer(r"(?:public |private |static )*func\s+\w+\([^\n]*\)[^\n{]*\{", source):
            body = braced_body(source, declaration.group())
            if "SCScreenshotManager.captureImage(" not in body:
                continue
            capture_entries.append((path.name, declaration.group()))
            assert body.strip().startswith("await ScreenCaptureApplication.initialize()"), path.name
            assert body.index("await ScreenCaptureApplication.initialize()") < body.index("SCScreenshotManager.captureImage(")
    assert capture_entries, "The regression test must inspect an actual screenshot entry"
