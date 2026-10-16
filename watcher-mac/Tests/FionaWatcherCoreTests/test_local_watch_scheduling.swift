import Foundation
import Testing
@testable import FionaWatcherCore

struct LocalWatchSchedulingTests {
    @Test
    func testRetryDoesNotBlockReadyObservationForAnotherRule() throws {
        var queue = ObservationQueue()
        let now = Date(timeIntervalSince1970: 100)
        queue.enqueue(PendingObservation(ruleID: 1, lines: ["第一条"], capturedAt: now, appName: "应用甲"))
        queue.enqueue(PendingObservation(ruleID: 2, lines: ["第二条"], capturedAt: now, appName: "应用乙"))
        let ready = queue.takeReady(at: now)
        let failed = try #require(ready)
        #expect(failed.ruleID == 1)
        queue.retry(failed, at: now)
        #expect(queue.takeReady(at: now)?.ruleID == 2)
        #expect(queue.takeReady(at: now) == nil)
        #expect(queue.takeReady(at: now.addingTimeInterval(1))?.lines == ["第一条"])
    }

    @Test
    func testPendingQueueRetainsEveryBatchAndFailedPayload() throws {
        var queue = ObservationQueue()
        let now = Date(timeIntervalSince1970: 100)
        for index in 0..<20 {
            queue.enqueue(PendingObservation(ruleID: 1, lines: ["消息 \(index)"], capturedAt: now, appName: "应用"))
        }
        #expect(queue.count(for: 1) == 20)
        let ready = queue.takeReady(at: now)
        let failed = try #require(ready)
        queue.retry(failed, at: now)
        #expect(queue.count(for: 1) == 20)
        #expect(queue.takeReady(at: now.addingTimeInterval(1))?.lines == ["消息 0"])
        for index in 1..<20 {
            #expect(queue.takeReady(at: now.addingTimeInterval(1))?.lines == ["消息 \(index)"])
        }
        queue.remove(ruleID: 1)
        #expect(queue.count(for: 1) == 0)
    }

    @Test
    func testExponentialBackoffNeverExceedsSixtySeconds() {
        var backoff = RetryBackoff()
        #expect((0..<9).map { _ in backoff.next() } == [1, 2, 4, 8, 16, 32, 60, 60, 60])
    }
}
