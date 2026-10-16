"""Offline Runner wiring contracts; state behavior is tested with Swift Testing."""

from pathlib import Path
import socket

import pytest


ROOT = Path(__file__).resolve().parents[2]
WATCHER = ROOT / "watcher-mac/Sources/FionaWatcherCore/Watcher.swift"
STATUS = ROOT / "watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift"


@pytest.fixture(scope="module", autouse=True)
def forbid_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Capture status contracts forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def body(source, declaration):
    opening = source.index("{", source.index(declaration))
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[opening + 1:end - 1]


def test_each_actual_heartbeat_serializes_the_status_tracker():
    source = WATCHER.read_text()
    heartbeat = body(source, "private func heartbeatLoop()")
    assert "capture_status: captureStatus.reports()" in heartbeat
    assert "captureStatus.reconcile(ruleIDs: rules.map(\\.id)" in heartbeat
    assert "captureStatus.remove(ruleID: rule.id)" in heartbeat


def test_actual_screenshot_failure_and_success_update_status_before_hash_skip():
    source = WATCHER.read_text()
    capture = body(source, "private func captureLoop()")
    screenshot = capture.index("SCScreenshotManager.captureImage(")
    failed = capture.index("captureStatus.failed(", screenshot)
    recovered = capture.index("captureStatus.succeeded(", failed)
    assert failed < recovered < capture.index("FrameFingerprint.hash(image)")
    assert "writeCaptureLogs(" in capture
    assert "throw WatcherError.screenPermission" not in capture
    assert "localizedDescription" not in capture and "userInfo" not in capture


def test_inventory_failure_keeps_heartbeats_and_is_not_replaced_by_window_missing():
    source = WATCHER.read_text()
    heartbeat = body(source, "private func heartbeatLoop()")
    capture = body(source, "private func captureLoop()")
    assert "inventoryFailure = error" in heartbeat
    assert "windows = []" in heartbeat
    assert "captureStatus.failed(" in heartbeat
    assert "if !hasSuccessfulInventory && !CGPreflightScreenCaptureAccess()" in heartbeat
    assert "throw WatcherError.screenPermission" in heartbeat
    assert capture.index("if let inventoryFailure") < capture.index("captureStatus.windowNotFound(")
    assert "captureStatus.failed(" in body(capture, "if let inventoryFailure")


def test_new_unit_tests_use_clt_and_are_outside_the_immutable_old_test_inventory():
    tests = ROOT / "watcher-mac/CaptureStatusTests/test_local_watch_capture_status.swift"
    source = tests.read_text()
    assert "import Testing" in source and "import XCTest" not in source
    assert source.count("@Test") >= 7
    assert "NSError(domain:" in source and "addingTimeInterval(60)" in source
    package = (ROOT / "watcher-mac/Package.swift").read_text()
    assert 'name: "FionaWatcherCaptureStatusTests"' in package
    assert 'path: "CaptureStatusTests"' in package
    assert ".package(" not in package


def test_capture_log_sink_is_private_to_metadata_and_raw_error_identity():
    assert STATUS.exists()
    status = STATUS.read_text()
    assert "localizedDescription" not in status and "userInfo" not in status
    assert ".domain" in status and ".code" in status
    assert "window.title" not in status and "lastLines" not in status
    sink = body(WATCHER.read_text(), "private func writeCaptureLogs(")
    assert "FileHandle.standardError.write" in sink
