"""Run the real pure Swift tracker offline without SwiftPM or macro dependencies."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift"


@pytest.fixture(scope="module", autouse=True)
def forbid_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


HARNESS = r'''
import Foundation

let start = Date(timeIntervalSince1970: 1_700_000_000)
func date(_ seconds: Double) -> Date { start.addingTimeInterval(seconds) }
func error(_ code: Int = -3811) -> NSError {
    NSError(domain: "SCStreamErrorDomain", code: code)
}
var tracker = CaptureStatusTracker()
var checks: [String: Bool] = [:]
switch CommandLine.arguments[1] {
case "boundary":
    _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(0))
    checks["first_recovery"] = tracker.succeeded(ruleID: 1, at: date(1)).count == 1
    _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(60.99))
    checks["59.99_seconds_is_throttled"] = tracker.succeeded(ruleID: 1, at: date(60.99)).isEmpty
    _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(61))
    checks["60_seconds_is_allowed"] = tracker.succeeded(ruleID: 1, at: date(61)).count == 1
case "per_rule":
    for id in [1, 2] {
        _ = tracker.failed(ruleID: id, appName: "Safari", error: error(), at: date(0))
        checks["first_recovery_\(id)"] = tracker.succeeded(ruleID: id, at: date(Double(id))).count == 1
        _ = tracker.failed(ruleID: id, appName: "Safari", error: error(), at: date(3))
        checks["repeated_recovery_\(id)"] = tracker.succeeded(ruleID: id, at: date(4)).isEmpty
    }
case "oscillation":
    var logCount = 0
    checks["all_transitions_update_state"] = true
    checks["healthy_since_remains_stable"] = true
    for attempt in 0..<30 {
        let failedAt = date(Double(attempt * 2))
        let recoveredAt = failedAt.addingTimeInterval(1)
        _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: failedAt)
        logCount += tracker.succeeded(ruleID: 1, at: recoveredAt).count
        let status = tracker.reports()[0]
        checks["all_transitions_update_state"] = checks["all_transitions_update_state"]! &&
            status.ok && status.error == nil && ISO8601DateFormatter().date(from: status.since) == recoveredAt
        let logs = tracker.succeeded(ruleID: 1, at: recoveredAt.addingTimeInterval(0.5))
        checks["healthy_since_remains_stable"] = checks["healthy_since_remains_stable"]! &&
            logs.isEmpty && tracker.reports()[0].since == status.since
    }
    checks["only_one_recovery_log"] = logCount == 1
case "reconcile":
    tracker.windowNotFound(ruleID: 1, at: date(0))
    checks["first_recovery"] = tracker.succeeded(ruleID: 1, at: date(1)).count == 1
    tracker.remove(ruleID: 1)
    tracker.reconcile(ruleIDs: [1], at: date(2))
    _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(3))
    checks["remove_does_not_reset_throttle"] = tracker.succeeded(ruleID: 1, at: date(4)).isEmpty
    tracker.reconcile(ruleIDs: [], at: date(5))
    tracker.reconcile(ruleIDs: [1], at: date(6))
    tracker.windowNotFound(ruleID: 1, at: date(7))
    checks["reconcile_does_not_reset_throttle"] = tracker.succeeded(ruleID: 1, at: date(8)).isEmpty
    tracker.reconcile(ruleIDs: [1], at: date(61))
    tracker.windowNotFound(ruleID: 1, at: date(61))
    checks["expiry_still_allows_recovery"] = tracker.succeeded(ruleID: 1, at: date(61)).count == 1
case "failure_throttle":
    checks["first_failure"] = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(0)).count == 1
    checks["first_recovery"] = tracker.succeeded(ruleID: 1, at: date(1)).count == 1
    checks["same_error_is_throttled"] = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(2)).isEmpty
    checks["second_recovery_is_throttled"] = tracker.succeeded(ruleID: 1, at: date(3)).isEmpty
    checks["different_error_is_independent"] = tracker.failed(ruleID: 1, appName: "Safari", error: error(-3801), at: date(4)).count == 1
    checks["third_recovery_is_throttled"] = tracker.succeeded(ruleID: 1, at: date(5)).isEmpty
    checks["switching_errors_cannot_reset_throttle"] = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(6)).isEmpty
    checks["other_rule_is_independent"] = tracker.failed(ruleID: 2, appName: "Safari", error: error(), at: date(7)).count == 1
    checks["failure_allowed_at_sixty_seconds"] = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: date(60)).count == 1
default:
    fatalError("Unknown recovery scenario")
}
let encoded = try JSONEncoder().encode(checks)
print(String(data: encoded, encoding: .utf8)!)
'''


@pytest.fixture(scope="module")
def compiled_tracker(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if compiler is None:
        pytest.skip("The installed Swift compiler is unavailable")
    directory = tmp_path_factory.mktemp("local-watch-recovery")
    source = directory / "main.swift"
    binary = directory / "recovery"
    cache = directory / "module-cache"
    source.write_text(HARNESS)
    environment = os.environ.copy()
    environment["CLANG_MODULE_CACHE_PATH"] = str(cache)
    environment["SWIFTPM_MODULECACHE_OVERRIDE"] = str(cache)
    compiled = subprocess.run(
        [compiler, "-module-cache-path", str(cache), str(STATUS), str(source), "-o", str(binary)],
        capture_output=True, text=True, env=environment, timeout=120,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return binary


@pytest.mark.parametrize("scenario", ["boundary", "per_rule", "oscillation", "reconcile", "failure_throttle"])
def test_recovery_throttle_on_the_actual_swift_tracker(compiled_tracker, scenario):
    process = subprocess.run([str(compiled_tracker), scenario], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stdout + process.stderr
    checks = json.loads(process.stdout)
    assert checks
    assert all(checks.values()), checks
