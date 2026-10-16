import Foundation

struct CaptureStatus: Encodable, Equatable {
    let rule_id: Int
    let ok: Bool
    let error: String?
    let since: String

    private enum CodingKeys: String, CodingKey {
        case rule_id, ok, error, since
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(rule_id, forKey: .rule_id)
        try values.encode(ok, forKey: .ok)
        if let error {
            try values.encode(error, forKey: .error)
        } else {
            try values.encodeNil(forKey: .error)
        }
        try values.encode(since, forKey: .since)
    }
}

/// Only capture metadata belongs here: never pass window titles or OCR text.
/// Explicit dates let tests simulate both errors and the 60-second boundary.
struct CaptureStatusTracker {
    private var statuses: [Int: CaptureStatus] = [:]
    private var lastFailureLogs: [Int: [String: Date]] = [:]
    private var lastRecoveryLogs: [Int: Date] = [:]

    mutating func reconcile(ruleIDs: [Int], at now: Date) {
        let enabled = Set(ruleIDs)
        statuses = statuses.filter { enabled.contains($0.key) }
        for id in enabled where statuses[id] == nil {
            update(ruleID: id, ok: false, error: nil, at: now)
        }
        // Keep recent failures even when a rule is edited or removed, so
        // switching rules or errors cannot bypass the per-error log limit.
        lastFailureLogs = lastFailureLogs.compactMapValues { errors in
            let recent = errors.filter { now.timeIntervalSince($0.value) < 60 }
            return recent.isEmpty ? nil : recent
        }
        lastRecoveryLogs = lastRecoveryLogs.filter { now.timeIntervalSince($0.value) < 60 }
    }

    mutating func remove(ruleID: Int) {
        statuses.removeValue(forKey: ruleID)
    }

    mutating func failed(ruleID: Int, appName: String, error: Error, at now: Date) -> [String] {
        let frameworkError = error as NSError
        let identity = "\(frameworkError.domain)/\(frameworkError.code)"
        update(ruleID: ruleID, ok: false, error: identity, at: now)
        if let last = lastFailureLogs[ruleID]?[identity], now.timeIntervalSince(last) < 60 {
            return []
        }
        lastFailureLogs[ruleID, default: [:]][identity] = now
        let app = appName.components(separatedBy: .newlines).joined(separator: " ")
        let safeIdentity = identity.components(separatedBy: .newlines).joined(separator: " ")
        return ["规则 id=\(ruleID)，应用=\(app)，截图失败：\(safeIdentity)"]
    }

    mutating func windowNotFound(ruleID: Int, at now: Date) {
        update(ruleID: ruleID, ok: false, error: "window_not_found", at: now)
    }

    mutating func succeeded(ruleID: Int, at now: Date) -> [String] {
        let recovered = statuses[ruleID].map { !$0.ok && $0.error != nil } ?? false
        update(ruleID: ruleID, ok: true, error: nil, at: now)
        guard recovered else { return [] }
        if let last = lastRecoveryLogs[ruleID], now.timeIntervalSince(last) < 60 {
            return []
        }
        lastRecoveryLogs[ruleID] = now
        return ["规则 id=\(ruleID)，截图已恢复"]
    }

    func reports() -> [CaptureStatus] {
        statuses.keys.sorted().compactMap { statuses[$0] }
    }

    private mutating func update(ruleID: Int, ok: Bool, error: String?, at now: Date) {
        if let previous = statuses[ruleID], previous.ok == ok && previous.error == error {
            return
        }
        statuses[ruleID] = CaptureStatus(rule_id: ruleID, ok: ok, error: error,
            since: ISO8601DateFormatter().string(from: now))
    }
}
