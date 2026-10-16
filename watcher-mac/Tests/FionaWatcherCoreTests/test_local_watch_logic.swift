import Testing
@testable import FionaWatcherCore

struct LocalWatchNormalizationTests {
    @Test
    func testTrimsAndCollapsesWhitespaceAndDropsNoise() {
        #expect(LineNormalizer.normalize([
            "  张三：今晚开会  ", "Download\t  complete", "A", "1234", "-1,234.50%",
            "12:30", "12:30:05", "昨天", "星期一", "周日", "！！…", "___",
            "  ", "价格 100", "今天下午开会", "@我"
        ]) == ["张三：今晚开会", "Download complete", "价格 100", "今天下午开会", "@我"])
    }

    @Test
    func testMixedNumericContentRemainsAndUnicodeWhitespaceCollapses() {
        #expect(LineNormalizer.normalize(["价格\u{3000}  -12.5%", "版本 2", "OK"]) ==
                ["价格 -12.5%", "版本 2", "OK"])
    }
}

struct LocalWatchSnapshotTests {
    @Test
    func testFirstSnapshotIsBaselineAndRecentThreeSuppressRepeatedLines() {
        var history = SnapshotHistory()
        #expect(history.observe(["甲消息", "旧行"]) == [])
        #expect(history.observe(["乙消息"]) == ["乙消息"])
        #expect(history.observe(["丙消息"]) == ["丙消息"])
        #expect(history.observe(["甲消息", "丁消息"]) == ["丁消息"])
        #expect(history.observe(["旧行"]) == ["旧行"])
    }

    @Test
    func testDuplicateLinesOnlyReportOnceAndEmptyFirstSnapshotIsBaseline() {
        var history = SnapshotHistory()
        #expect(history.observe([]) == [])
        #expect(history.observe(["新消息", "新消息", "其他消息"]) == ["新消息", "其他消息"])
        #expect(history.observe(["新消息"]) == [])
    }

    @Test
    func testObservationBoundsPreserveOrder() {
        #expect(ObservationLimits.lines(Array(repeating: "消息", count: 55)).count == 50)
        let bounded = ObservationLimits.lines([String(repeating: "甲", count: 3995), "中文中文中文"])
        #expect(bounded.map(\.count).reduce(0, +) == 4000)
        #expect(bounded.last == "中文中文中")
    }
}
