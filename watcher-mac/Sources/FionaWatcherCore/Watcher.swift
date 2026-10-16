import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit

@MainActor
private enum ScreenCaptureApplication {
    private static let initialized: Void = {
        _ = NSApplication.shared
        NSApplication.shared.setActivationPolicy(.prohibited)
    }()

    static func initialize() {
        _ = initialized
    }
}

public enum WatcherError: Error {
    case screenPermission
    case tokenPermissions
    case tokenUnreadable
    case invalidServer
    case unauthorized
    case httpStatus(Int)
    case invalidResponse
    case imageProcessing
    case invalidArguments

    public var guidance: String {
        switch self {
        case .screenPermission:
            return "没有屏幕录制权限。请打开 系统设置 → 隐私与安全性 → 屏幕录制，勾选运行它的终端或程序本身，然后重新启动。"
        case .tokenPermissions:
            return "令牌文件权限必须是 600。请执行 chmod 600 ~/.fiona/watcher.token（使用自定义路径时请替换路径），然后重新运行。"
        case .tokenUnreadable:
            return "无法读取有效令牌。请从 Fiona 设置页复制设备令牌，用 umask 077 写入令牌文件。"
        case .unauthorized:
            return "设备令牌已失效（HTTP 401），监控已停止。请在 Fiona 设置页生成新的设备令牌。"
        case .invalidServer:
            return "服务器地址无效，请传入 http:// 或 https:// URL。"
        case .httpStatus(let status):
            return "HTTP 状态=\(status)，监控已停止。"
        case .invalidResponse:
            return "服务器响应格式无效，监控已停止。"
        case .imageProcessing:
            return "图片无法处理。"
        case .invalidArguments:
            return "用法：fiona-watcher list-windows | ocr <png路径> | run [--server URL] [--token-file 路径]"
        }
    }
}

public struct WindowDescriptor: Codable {
    public let window_id: UInt32
    public let app_name: String
    public let bundle_id: String
    public let title: String

    init(_ window: SCWindow) {
        window_id = window.windowID
        app_name = window.owningApplication?.applicationName ?? ""
        bundle_id = window.owningApplication?.bundleIdentifier ?? ""
        title = window.title ?? ""
    }
}

public struct WatchRule: Decodable, Equatable {
    public let id: Int
    public let app_match: String?
    public let title_match: String?
    public let interval_seconds: Int

    func matches(_ window: WindowDescriptor) -> Bool {
        let app = app_match ?? ""
        let title = title_match ?? ""
        return (app.isEmpty || window.app_name.range(of: app, options: .caseInsensitive) != nil ||
                window.bundle_id.range(of: app, options: .caseInsensitive) != nil) &&
            (title.isEmpty || window.title.range(of: title, options: .caseInsensitive) != nil)
    }
}

public enum WindowInventory {
    public static func current() async throws -> [SCWindow] {
        guard CGPreflightScreenCaptureAccess() else { throw WatcherError.screenPermission }
        do {
            let content = try await SCShareableContent.current
            return content.windows.filter { window in
                window.isOnScreen && !((window.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
                    window.frame.width * window.frame.height < 200 * 200)
            }
        } catch {
            if !CGPreflightScreenCaptureAccess() { throw WatcherError.screenPermission }
            throw error
        }
    }

    public static func descriptors() async throws -> [WindowDescriptor] {
        try await current().map(WindowDescriptor.init)
    }
}

public struct RunOptions {
    public let server: URL
    public let token: String

    public init(server: String = "http://127.0.0.1:8010", tokenFile: String = "~/.fiona/watcher.token") throws {
        guard let url = URL(string: server), ["http", "https"].contains(url.scheme?.lowercased() ?? ""),
              url.host != nil else { throw WatcherError.invalidServer }
        let path = (tokenFile as NSString).expandingTildeInPath
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: path) else {
            throw WatcherError.tokenUnreadable
        }
        guard (attributes[.posixPermissions] as? NSNumber)?.intValue == 0o600 else {
            throw WatcherError.tokenPermissions
        }
        guard let data = FileManager.default.contents(atPath: path),
              let value = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty, !value.contains(where: { $0.isWhitespace }) else { throw WatcherError.tokenUnreadable }
        self.server = url
        token = value
    }
}

struct Heartbeat: Encodable {
    let windows: [WindowDescriptor]
    let capture_status: [CaptureStatus]
}
private struct HeartbeatResponse: Decodable { let rules: [WatchRule] }
private struct Observation: Encodable {
    let rule_id: Int
    let new_lines: [String]
    let captured_at: String
}

private struct RuleState {
    var rule: WatchRule
    var windowID: UInt32?
    var appName = "-"
    var nextCapture = Date.distantPast
    var history = SnapshotHistory()
    var fingerprint: UInt64?
    var lastLines: [String] = []
}

public actor WatcherRunner {
    private let options: RunOptions
    private let session: URLSession
    private var states: [Int: RuleState] = [:]
    private var windows: [SCWindow] = []
    private var inventoryFailure: Error?
    private var hasSuccessfulInventory = false
    private var captureStatus = CaptureStatusTracker()
    private var pending = ObservationQueue()

    public init(options: RunOptions) {
        self.options = options
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.httpCookieStorage = nil
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 20
        session = URLSession(configuration: configuration)
    }

    public func run() async throws {
        await ScreenCaptureApplication.initialize()
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask { try await self.heartbeatLoop() }
            group.addTask { try await self.captureLoop() }
            group.addTask { try await self.observationLoop() }
            do {
                _ = try await group.next()
                group.cancelAll()
            } catch {
                group.cancelAll()
                throw error
            }
        }
    }

    private func heartbeatLoop() async throws {
        while !Task.isCancelled {
            let nextHeartbeat = Date().addingTimeInterval(30)
            do {
                windows = try await WindowInventory.current()
                inventoryFailure = nil
                hasSuccessfulInventory = true
            } catch {
                if Task.isCancelled { throw CancellationError() }
                if !hasSuccessfulInventory && !CGPreflightScreenCaptureAccess() {
                    throw WatcherError.screenPermission
                }
                // A locked display can fail enumeration as well as screenshots.
                // Continue heartbeats with the original error instead of going silent.
                inventoryFailure = error
                windows = []
                for id in states.keys.sorted() {
                    guard let state = states[id] else { continue }
                    writeCaptureLogs(captureStatus.failed(ruleID: id, appName: state.appName,
                        error: error, at: Date()))
                }
            }
            let body = try JSONEncoder().encode(Heartbeat(
                windows: Array(windows.prefix(200)).map(WindowDescriptor.init),
                capture_status: captureStatus.reports()))
            let response = try await postWithRetry("heartbeat", body: body)
            let decoder = JSONDecoder()
            let rules: [WatchRule]
            if let wrapped = try? decoder.decode(HeartbeatResponse.self, from: response) {
                rules = wrapped.rules
            } else if let array = try? decoder.decode([WatchRule].self, from: response) {
                rules = array
            } else { throw WatcherError.invalidResponse }
            let enabled = Set(rules.map(\.id))
            for id in states.keys where !enabled.contains(id) {
                pending.remove(ruleID: id)
            }
            states = states.filter { enabled.contains($0.key) }
            for rule in rules {
                if var existing = states[rule.id] {
                    if existing.rule.app_match != rule.app_match || existing.rule.title_match != rule.title_match {
                        existing = RuleState(rule: rule)
                        captureStatus.remove(ruleID: rule.id)
                        pending.remove(ruleID: rule.id)
                    }
                    existing.rule = rule
                    states[rule.id] = existing
                } else { states[rule.id] = RuleState(rule: rule) }
            }
            captureStatus.reconcile(ruleIDs: rules.map(\.id), at: Date())
            let wait = max(0, nextHeartbeat.timeIntervalSinceNow)
            if wait > 0 { try await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000)) }
        }
    }

    private func captureLoop() async throws {
        await ScreenCaptureApplication.initialize()
        while !Task.isCancelled {
            for id in states.keys.sorted() {
                guard var state = states[id], Date() >= state.nextCapture else { continue }
                state.nextCapture = Date().addingTimeInterval(TimeInterval(max(2, min(60, state.rule.interval_seconds))))
                if let inventoryFailure {
                    writeCaptureLogs(captureStatus.failed(ruleID: id, appName: state.appName,
                        error: inventoryFailure, at: Date()))
                    states[id] = state
                    continue
                }
                guard let window = windows.first(where: { state.rule.matches(WindowDescriptor($0)) }) else {
                    captureStatus.windowNotFound(ruleID: id, at: Date())
                    states[id] = state
                    continue
                }
                state.appName = window.owningApplication?.applicationName ?? "-"
                if state.windowID != window.windowID {
                    state.windowID = window.windowID
                    state.history = SnapshotHistory()
                    state.fingerprint = nil
                    state.lastLines = []
                    pending.remove(ruleID: id)
                }
                states[id] = state
                let image: CGImage
                do {
                    let filter = SCContentFilter(desktopIndependentWindow: window)
                    let configuration = SCStreamConfiguration()
                    configuration.width = max(1, Int(window.frame.width * 2))
                    configuration.height = max(1, Int(window.frame.height * 2))
                    configuration.showsCursor = false
                    image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
                } catch {
                    if Task.isCancelled { throw CancellationError() }
                    // Discard the result if a heartbeat removed or changed this rule.
                    guard let live = states[id], live.windowID == window.windowID,
                          live.rule.app_match == state.rule.app_match,
                          live.rule.title_match == state.rule.title_match else { continue }
                    writeCaptureLogs(captureStatus.failed(ruleID: id, appName: state.appName,
                        error: error, at: Date()))
                    continue
                }
                let capturedAt = Date()
                // Heartbeat can update/delete a rule while capture or OCR awaits.
                guard let live = states[id], live.windowID == window.windowID,
                      live.rule.app_match == state.rule.app_match,
                      live.rule.title_match == state.rule.title_match else { continue }
                state = live
                writeCaptureLogs(captureStatus.succeeded(ruleID: id, at: capturedAt))
                let fingerprint = try FrameFingerprint.hash(image)
                if state.fingerprint == fingerprint {
                    _ = state.history.observe(state.lastLines)
                    states[id] = state
                    continue
                }
                let lines = try await Task.detached {
                    LineNormalizer.normalize(try OCRRecognizer.lines(in: image))
                }.value
                guard let afterOCR = states[id], afterOCR.windowID == window.windowID,
                      afterOCR.rule.app_match == state.rule.app_match,
                      afterOCR.rule.title_match == state.rule.title_match else { continue }
                state = afterOCR
                let added = ObservationLimits.lines(state.history.observe(lines))
                state.fingerprint = fingerprint
                state.lastLines = lines
                states[id] = state
                if !added.isEmpty {
                    pending.enqueue(PendingObservation(ruleID: id, lines: added, capturedAt: capturedAt,
                        appName: window.owningApplication?.applicationName ?? ""))
                }
            }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
    }

    private func observationLoop() async throws {
        while !Task.isCancelled {
            if let item = pending.takeReady(at: Date()), states[item.ruleID] != nil {
                let observation = Observation(rule_id: item.ruleID, new_lines: item.lines,
                    captured_at: ISO8601DateFormatter().string(from: item.capturedAt))
                do {
                    _ = try await postOnce("observations", body: JSONEncoder().encode(observation),
                        ruleID: item.ruleID, appName: item.appName, count: item.lines.count)
                } catch WatcherError.unauthorized {
                    throw WatcherError.unauthorized
                } catch WatcherError.httpStatus(let status) where status < 500 && status != 429 {
                    // A setting change can invalidate a cached rule. Other rules
                    // continue; the next heartbeat refreshes enabled rules.
                    if status == 403 || status == 404 {
                        states.removeValue(forKey: item.ruleID)
                        captureStatus.remove(ruleID: item.ruleID)
                        pending.remove(ruleID: item.ruleID)
                    }
                } catch {
                    if Task.isCancelled { throw CancellationError() }
                    if states[item.ruleID] != nil { pending.retry(item, at: Date()) }
                }
            }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
    }

    private func postWithRetry(_ endpoint: String, body: Data) async throws -> Data {
        var backoff = RetryBackoff()
        while !Task.isCancelled {
            do {
                return try await postOnce(endpoint, body: body)
            } catch WatcherError.unauthorized {
                throw WatcherError.unauthorized
            } catch WatcherError.httpStatus(let status) where status < 500 && status != 429 {
                throw WatcherError.httpStatus(status)
            } catch let error as WatcherError {
                if case .invalidResponse = error { throw error }
            } catch { if Task.isCancelled { throw CancellationError() } }
            try await Task.sleep(nanoseconds: backoff.next() * 1_000_000_000)
        }
        throw CancellationError()
    }

    private func postOnce(_ endpoint: String, body: Data, ruleID: Int? = nil, appName: String = "-", count: Int = 0) async throws -> Data {
        var request = URLRequest(url: options.server.appendingPathComponent("local-watch").appendingPathComponent(endpoint))
        request.httpMethod = "POST"
        request.setValue("Bearer \(options.token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = body
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw WatcherError.invalidResponse }
            log(ruleID: ruleID, appName: appName, count: count, status: String(http.statusCode))
            if http.statusCode == 401 { throw WatcherError.unauthorized }
            guard (200..<300).contains(http.statusCode) else { throw WatcherError.httpStatus(http.statusCode) }
            return data
        } catch let error as WatcherError { throw error }
        catch {
            if !Task.isCancelled {
                log(ruleID: ruleID, appName: appName, count: count, status: "network-error")
            }
            throw error
        }
    }

    private func log(ruleID: Int?, appName: String, count: Int, status: String) {
        // Do not log bodies, titles, OCR text, tokens, or returned summaries.
        let sanitizedApp = appName.components(separatedBy: .newlines).joined(separator: " ")
        let line = "规则 id=\(ruleID.map(String.init) ?? "-")，应用=\(sanitizedApp)，新增行数=\(count)，HTTP 状态=\(status)\n"
        FileHandle.standardError.write(Data(line.utf8))
    }

    private func writeCaptureLogs(_ lines: [String]) {
        for line in lines {
            FileHandle.standardError.write(Data((line + "\n").utf8))
        }
    }
}
