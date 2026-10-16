import Foundation

public struct RetryBackoff: Equatable {
    private var delay: UInt64 = 1
    public init() {}

    public mutating func next() -> UInt64 {
        defer { delay = min(delay * 2, 60) }
        return delay
    }
}

public struct PendingObservation: Equatable {
    public let ruleID: Int
    public var lines: [String]
    public let capturedAt: Date
    public let appName: String
    fileprivate var nextAttempt = Date.distantPast
    fileprivate var backoff = RetryBackoff()

    public init(ruleID: Int, lines: [String], capturedAt: Date, appName: String) {
        self.ruleID = ruleID
        self.lines = ObservationLimits.lines(lines)
        self.capturedAt = capturedAt
        self.appName = appName
    }
}

/// In-memory retry scheduling; a delayed rule never blocks another.
public struct ObservationQueue {
    private var items: [Int: [PendingObservation]] = [:]
    private var lastRule: Int?
    public init() {}

    public mutating func enqueue(_ observation: PendingObservation) {
        var queue = items[observation.ruleID] ?? []
        queue.append(observation)
        items[observation.ruleID] = queue
    }

    public mutating func takeReady(at now: Date) -> PendingObservation? {
        let keys = items.keys.sorted()
        let ordered = keys.filter { $0 > (lastRule ?? Int.min) } + keys.filter { $0 <= (lastRule ?? Int.min) }
        for id in ordered {
            guard let first = items[id]?.first, first.nextAttempt <= now else { continue }
            items[id]!.removeFirst()
            if items[id]!.isEmpty { items.removeValue(forKey: id) }
            lastRule = id
            return first
        }
        return nil
    }

    public mutating func retry(_ observation: PendingObservation, at now: Date) {
        var pending = observation
        pending.nextAttempt = now.addingTimeInterval(TimeInterval(pending.backoff.next()))
        var queue = items[pending.ruleID] ?? []
        queue.insert(pending, at: 0)
        items[pending.ruleID] = queue
    }

    public mutating func remove(ruleID: Int) { items.removeValue(forKey: ruleID) }
    public func count(for ruleID: Int) -> Int { items[ruleID]?.count ?? 0 }
}
