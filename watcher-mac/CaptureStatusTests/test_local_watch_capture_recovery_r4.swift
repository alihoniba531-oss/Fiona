import Foundation
import Testing
@testable import FionaWatcherCore

struct LocalWatchCaptureRecoveryR4Tests {
    private let start = Date(timeIntervalSince1970: 1_700_000_000)

    private func error(_ code: Int = -3811) -> NSError {
        NSError(domain: "SCStreamErrorDomain", code: code)
    }

    @Test
    func recoveryLogsRespectTheExactSixtySecondBoundary() {
        var tracker = CaptureStatusTracker()
        _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(1)).count == 1)
        _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start.addingTimeInterval(60.99))
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(60.99)).isEmpty)
        _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start.addingTimeInterval(61))
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(61)).count == 1)
    }

    @Test
    func recoveryLogsAreIndependentForEachRule() {
        var tracker = CaptureStatusTracker()
        for id in [1, 2] {
            _ = tracker.failed(ruleID: id, appName: "Safari", error: error(), at: start)
            #expect(tracker.succeeded(ruleID: id, at: start.addingTimeInterval(Double(id))).count == 1)
        }
        for id in [1, 2] {
            _ = tracker.failed(ruleID: id, appName: "Safari", error: error(), at: start.addingTimeInterval(3))
            #expect(tracker.succeeded(ruleID: id, at: start.addingTimeInterval(4)).isEmpty)
        }
    }

    @Test
    func rapidRecoveryStillUpdatesCaptureStateAndSinceImmediately() throws {
        var tracker = CaptureStatusTracker()
        var recoveryLogs: [String] = []
        for attempt in 0..<30 {
            let failedAt = start.addingTimeInterval(Double(attempt * 2))
            let recoveredAt = failedAt.addingTimeInterval(1)
            _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: failedAt)
            recoveryLogs += tracker.succeeded(ruleID: 1, at: recoveredAt)
            let status = try #require(tracker.reports().first)
            #expect(status.ok && status.error == nil)
            #expect(ISO8601DateFormatter().date(from: status.since) == recoveredAt)
            #expect(tracker.succeeded(ruleID: 1, at: recoveredAt.addingTimeInterval(0.5)).isEmpty)
            #expect(tracker.reports().first?.since == status.since)
        }
        #expect(recoveryLogs == ["规则 id=1，截图已恢复"])
    }

    @Test
    func removingOrReconcilingRulesCannotBypassRecoveryThrottle() {
        var tracker = CaptureStatusTracker()
        tracker.windowNotFound(ruleID: 1, at: start)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(1)).count == 1)
        tracker.remove(ruleID: 1)
        tracker.reconcile(ruleIDs: [1], at: start.addingTimeInterval(2))
        _ = tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start.addingTimeInterval(3))
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(4)).isEmpty)
        tracker.reconcile(ruleIDs: [], at: start.addingTimeInterval(5))
        tracker.reconcile(ruleIDs: [1], at: start.addingTimeInterval(6))
        tracker.windowNotFound(ruleID: 1, at: start.addingTimeInterval(7))
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(8)).isEmpty)
        tracker.reconcile(ruleIDs: [1], at: start.addingTimeInterval(61))
        tracker.windowNotFound(ruleID: 1, at: start.addingTimeInterval(61))
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(61)).count == 1)
    }

    @Test
    func recoveryThrottleDoesNotResetTheFailureLogThrottle() {
        var tracker = CaptureStatusTracker()
        #expect(tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start).count == 1)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(1)).count == 1)
        #expect(tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start.addingTimeInterval(2)).isEmpty)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(3)).isEmpty)
        #expect(tracker.failed(ruleID: 1, appName: "Safari", error: error(-3801), at: start.addingTimeInterval(4)).count == 1)
        #expect(tracker.succeeded(ruleID: 1, at: start.addingTimeInterval(5)).isEmpty)
        #expect(tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start.addingTimeInterval(6)).isEmpty)
        #expect(tracker.failed(ruleID: 2, appName: "Safari", error: error(), at: start.addingTimeInterval(7)).count == 1)
        #expect(tracker.failed(ruleID: 1, appName: "Safari", error: error(), at: start.addingTimeInterval(60)).count == 1)
    }
}
