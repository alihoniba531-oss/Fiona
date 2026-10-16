import CoreGraphics
import FionaWatcherCore
import Foundation

@main
struct FionaWatcherMain {
    static func main() async {
        do {
            let arguments = Array(CommandLine.arguments.dropFirst())
            guard let command = arguments.first else { throw WatcherError.invalidArguments }
            switch command {
            case "list-windows":
                guard arguments.count == 1 else { throw WatcherError.invalidArguments }
                try outputJSON(await WindowInventory.descriptors())
            case "ocr":
                guard arguments.count == 2 else { throw WatcherError.invalidArguments }
                let path = (arguments[1] as NSString).expandingTildeInPath
                guard let provider = CGDataProvider(filename: path),
                      let image = CGImage(pngDataProviderSource: provider, decode: nil,
                                          shouldInterpolate: false, intent: .defaultIntent) else {
                    throw WatcherError.imageProcessing
                }
                try outputJSON(["lines": OCRRecognizer.lines(in: image)])
            case "run":
                var server = "http://127.0.0.1:8010"
                var tokenFile = "~/.fiona/watcher.token"
                var index = 1
                while index < arguments.count {
                    guard index + 1 < arguments.count else { throw WatcherError.invalidArguments }
                    switch arguments[index] {
                    case "--server": server = arguments[index + 1]
                    case "--token-file": tokenFile = arguments[index + 1]
                    default: throw WatcherError.invalidArguments
                    }
                    index += 2
                }
                try await WatcherRunner(options: RunOptions(server: server, tokenFile: tokenFile)).run()
            default:
                throw WatcherError.invalidArguments
            }
        } catch let error as WatcherError {
            FileHandle.standardError.write(Data((error.guidance + "\n").utf8))
            exit(1)
        } catch is CancellationError {
            exit(0)
        } catch {
            // Framework errors can embed recognized text: never dump them.
            FileHandle.standardError.write(Data("监控遇到错误，已停止。请检查屏幕录制授权和运行参数。\n".utf8))
            exit(1)
        }
    }

    private static func outputJSON<T: Encodable>(_ value: T) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        FileHandle.standardOutput.write(try encoder.encode(value))
        FileHandle.standardOutput.write(Data("\n".utf8))
    }
}
