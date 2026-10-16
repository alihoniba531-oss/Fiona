# 返修 R1：真机验收发现的 Swift 问题

日期：2026-10-11。作者方已在沙箱外的真机（macOS 27.0.1，只装了 Command Line Tools，没有完整的 Xcode）上完成验收。本返修单与 02-spec.md 同等效力。下面两项都必须完成，除此之外的实现保持不动。

## R1-1 `run` 一截图就崩溃（必须）

**现象**：`fiona-watcher run` 连上后端、发出心跳后，第一次截图时进程直接退出，输出：

```
Assertion failed: (did_initialize), function CGS_REQUIRE_INIT, file CGInitialization.c, line 44.
```

`list-windows` 和 `ocr` 子命令都正常。

**原因（作者方已用最小程序复现并验证）**：命令行进程没有初始化 CoreGraphics 窗口服务，一调用 `SCScreenshotManager.captureImage` 就触发断言。在截图之前执行下面两行即可修复：

```swift
import AppKit
_ = NSApplication.shared
NSApplication.shared.setActivationPolicy(.prohibited)
```

加上之后，同一窗口能截到 1324×874 的图像，不会出现 Dock 图标。

**改法**：在所有会截图的入口（`run`，以及其他会调用 `captureImage` 的地方）开头执行上述初始化，并且只执行一次。设为 `.prohibited` 后不显示 Dock 图标，也不抢焦点。

**测试**：加一条测试，断言截图入口在截图前会调用这个初始化。真实截图由作者方在真机上验证。

## R1-2 `swift test` 在只有 Command Line Tools 的机器上无法编译（必须）

**现象**：`swift test` 报错 `unable to resolve module dependency: 'XCTest'`。原因是 Command Line Tools 不带 XCTest，只带 Swift Testing（`Testing.framework`）。

**改法**：把 `watcher-mac/Tests/` 下的全部 XCTest 用例改写为 Swift Testing，即 `import Testing`、`@Test`、`#expect` / `#require`，保留原有全部断言，不得删减或放宽。

**验收**：在只有 Command Line Tools 的环境下，`swift build -c release` 和 `swift test` 都通过，包括 OCR 那条测试。沙箱里跑不了的话，在报告里写明原因，由作者方在沙箱外复跑。

## 验收

- 受保护文件零 diff；既有测试零改动。
- 本任务新增的后端测试全部通过。
- 在 03-report.md 末尾追加「R1」一节。
