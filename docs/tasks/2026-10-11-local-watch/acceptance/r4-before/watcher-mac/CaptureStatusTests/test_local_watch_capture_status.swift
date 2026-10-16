import Foundation
import Testing
@testable import FionaWatcherCore

struct LocalWatchCaptureStatusTests {
    private let start = Date(timeIntervalSince1970: 1_700_000_000)

    private func error(_ code: Int = -3811) -> NSError {
        NSError(domain: "SCStreamErrorDomain", code: code,
                userInfo: [NSLocalizedDescriptionKey: "SECRET_WINDOW_TITLE_OCR_TEXT"])
    }

    @Test
    func testSameErrorIsThrottledForSixtySecondsPerRule() {
        var tracker = CaptureStatusTracker()
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start) ==
                ["规则 id=1，应用=微信，截图失败：SCStreamErrorDomain/-3811"])
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(59.99)).isEmpty)
        #expect(tracker.failed(ruleID: 2, appName: "Safari", error: error(), at: start.addingTimeInterval(1)).count == 1)
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(60)).count == 1)
    }

    @Test
    func testChangingErrorsDoesNotBypassThePerErrorThrottle() {
        var tracker = CaptureStatusTracker()
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start).count == 1)
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(-3801), at: start.addingTimeInterval(1)).count == 1)
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(2)).isEmpty)
        #expect(tracker.reports().first?.error == "SCStreamErrorDomain/-3811")
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(60)).count == 1)
    }

    @Test
    func testRecoveryIsLoggedExactlyOnceWithoutResettingTheThrottle() {
        var tracker = CaptureStatusTracker()
        _ = tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(1)) == ["规则 id=1，截图已恢复"])
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(2)).isEmpty)
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(3)).isEmpty)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(4)) == ["规则 id=1，截图已恢复"])
    }

    @Test
    func testResettingRuleMatchingDoesNotBypassThePerErrorThrottle() {
        var tracker = CaptureStatusTracker()
        _ = tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start)
        tracker.remove(ruleID: 1)
        tracker.reconcile(ruleIDs: [1], at: start.addingTimeInterval(1))
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(2)).isEmpty)
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(60)).count == 1)
    }

    @Test
    func testSinceChangesOnlyWhenCaptureStateChanges() throws {
        var tracker = CaptureStatusTracker()
        _ = tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start)
        let failedSince = try #require(tracker.reports().first?.since)
        _ = tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(60))
        #expect(tracker.reports().first?.since == failedSince)
        _ = tracker.failed(ruleID: 1, appName: "微信", error: error(-3801), at: start.addingTimeInterval(61))
        #expect(tracker.reports().first?.since != failedSince)
        _ = tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(62))
        let healthySince = try #require(tracker.reports().first?.since)
        _ = tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(63))
        #expect(tracker.reports().first?.since == healthySince)
        #expect(ISO8601DateFormatter().date(from: healthySince) == start.addingTimeInterval(62))
    }

    @Test
    func testHeartbeatContainsEveryRuleAndExplicitNullWithISO8601() throws {
        var tracker = CaptureStatusTracker()
        tracker.reconcile(ruleIDs: [2, 1], at: start)
        let initial = try #require(tracker.reports().first)
        #expect(!initial.ok && initial.error == nil)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(1)).isEmpty)
        tracker.windowNotFound(ruleID: 2, at: start.addingTimeInterval(2))
        let encoded = try JSONEncoder().encode(Heartbeat(windows: [], capture_status: tracker.reports()))
        let object = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        #expect(Set(object.keys) == ["windows", "capture_status"])
        let reports = try #require(object["capture_status"] as? [[String: Any]])
        #expect(reports.count == 2)
        #expect(reports.map { $0["rule_id"] as? Int } == [1, 2])
        #expect(Set(reports[0].keys) == ["rule_id", "ok", "error", "since"])
        #expect(reports[0]["ok"] as? Bool == true)
        #expect(reports[0]["error"] is NSNull)
        #expect(reports[1]["error"] as? String == "window_not_found")
        for report in reports {
            let since = try #require(report["since"] as? String)
            #expect(ISO8601DateFormatter().date(from: since) != nil)
        }
    }

    @Test
    func testMissingWindowsRemainStableAndDeletedRulesAreRemoved() throws {
        var tracker = CaptureStatusTracker()
        tracker.reconcile(ruleIDs: [1, 2], at: start)
        tracker.windowNotFound(ruleID: 1, at: start.addingTimeInterval(1))
        let since = try #require(tracker.reports().first?.since)
        tracker.windowNotFound(ruleID: 1, at: start.addingTimeInterval(20))
        #expect(tracker.reports().first?.since == since)
        #expect(tracker.reports().first?.ok == false)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(21)) == ["规则 id=1，截图已恢复"])
        tracker.reconcile(ruleIDs: [2], at: start.addingTimeInterval(22))
        #expect(tracker.reports().map(\.rule_id) == [2])
        tracker.reconcile(ruleIDs: [1, 2], at: start.addingTimeInterval(23))
        #expect(tracker.failed(ruleID: 1, appName: "微信", error: error(), at: start.addingTimeInterval(24)).count == 1)
    }

    @Test
    func testLogsNeverIncludeNSErrorDescriptionsOrWindowText() throws {
        var tracker = CaptureStatusTracker()
        let lines = tracker.failed(ruleID: 3, appName: "Safari\n应用", error: error(), at: start)
        #expect(lines == ["规则 id=3，应用=Safari 应用，截图失败：SCStreamErrorDomain/-3811"])
        let encoded = try JSONEncoder().encode(tracker.reports())
        let json = try #require(String(data: encoded, encoding: .utf8))
        #expect(!json.contains("SECRET_WINDOW_TITLE_OCR_TEXT"))
        #expect(!lines.joined().contains("SECRET_WINDOW_TITLE_OCR_TEXT"))
        #expect(!json.contains("Safari"))
    }
}
