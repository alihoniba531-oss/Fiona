// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "FionaWatcher",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "fiona-watcher", targets: ["fiona-watcher"])],
    targets: [
        .target(name: "FionaWatcherCore"),
        .executableTarget(name: "fiona-watcher", dependencies: ["FionaWatcherCore"]),
        .testTarget(name: "FionaWatcherCoreTests", dependencies: ["FionaWatcherCore"]),
        .testTarget(name: "FionaWatcherCaptureStatusTests", dependencies: ["FionaWatcherCore"],
                    path: "CaptureStatusTests")
    ]
)
