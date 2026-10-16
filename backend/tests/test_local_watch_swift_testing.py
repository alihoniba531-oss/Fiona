"""Offline contracts for the R1 migration from XCTest to Swift Testing."""

from pathlib import Path
import re
import socket

import pytest


ROOT = Path(__file__).resolve().parents[2]
TEST_DIRECTORY = ROOT / "watcher-mac/Tests/FionaWatcherCoreTests"
FILES_AND_METHODS = {
    "test_local_watch_logic.swift": (
        "testTrimsAndCollapsesWhitespaceAndDropsNoise",
        "testMixedNumericContentRemainsAndUnicodeWhitespaceCollapses",
        "testFirstSnapshotIsBaselineAndRecentThreeSuppressRepeatedLines",
        "testDuplicateLinesOnlyReportOnceAndEmptyFirstSnapshotIsBaseline",
        "testObservationBoundsPreserveOrder",
    ),
    "test_local_watch_scheduling.swift": (
        "testRetryDoesNotBlockReadyObservationForAnotherRule",
        "testPendingQueueRetainsEveryBatchAndFailedPayload",
        "testExponentialBackoffNeverExceedsSixtySeconds",
    ),
    "test_local_watch_ocr.swift": (
        "testRecognizesChineseAndEnglishDrawnByCoreGraphics",
    ),
}


@pytest.fixture(scope="module", autouse=True)
def block_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Swift Testing migration contracts forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in (
        "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex",
        "gethostbyaddr",
    ):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def compact(source):
    return re.sub(r"\s+", "", source)


@pytest.mark.parametrize("filename,methods", FILES_AND_METHODS.items())
def test_all_existing_cases_are_discoverable_without_xctest(filename, methods):
    source = (TEST_DIRECTORY / filename).read_text(encoding="utf-8")
    assert "import Testing" in source
    assert not re.search(r"\b(?:XCTest|XCTestCase|XCTAssert\w*|XCTUnwrap|XCTFail)\b", source)
    assert set(re.findall(r"@Test\s+func\s+(\w+)\(", source)) == set(methods)
    assert ".disabled" not in source and "XCTSkip" not in source
    assert "#if canImport" not in source
    assert not re.search(r"@Test\s*\(", source), "Migration must not disable or gate any original test"


def test_normalization_and_snapshot_assertion_strength_is_preserved():
    source = compact((TEST_DIRECTORY / "test_local_watch_logic.swift").read_text(encoding="utf-8"))
    expected = (
        'LineNormalizer.normalize(["张三：今晚开会","Download\\tcomplete","A","1234","-1,234.50%",'
        '"12:30","12:30:05","昨天","星期一","周日","！！…","___","","价格100","今天下午开会","@我"])'
        '==["张三：今晚开会","Downloadcomplete","价格100","今天下午开会","@我"]',
        'LineNormalizer.normalize(["价格\\u{3000}-12.5%","版本2","OK"])==["价格-12.5%","版本2","OK"]',
        'history.observe(["甲消息","旧行"])==[]',
        'history.observe(["乙消息"])==["乙消息"]',
        'history.observe(["丙消息"])==["丙消息"]',
        'history.observe(["甲消息","丁消息"])==["丁消息"]',
        'history.observe(["旧行"])==["旧行"]',
        'history.observe([])==[]',
        'history.observe(["新消息","新消息","其他消息"])==["新消息","其他消息"]',
        'history.observe(["新消息"])==[]',
        'ObservationLimits.lines(Array(repeating:"消息",count:55)).count==50',
        'bounded.map(\\.count).reduce(0,+)==4000',
        'bounded.last=="中文中文中"',
    )
    assert source.count("#expect(") == len(expected)
    for expression in expected:
        assert "#expect(" + expression + ")" in source
    assert 'String(repeating:"甲",count:3995),"中文中文中文"' in source


def test_retry_payload_queue_and_backoff_assertions_are_preserved():
    source = compact((TEST_DIRECTORY / "test_local_watch_scheduling.swift").read_text(encoding="utf-8"))
    expected = (
        "failed.ruleID==1",
        "queue.takeReady(at:now)?.ruleID==2",
        "queue.takeReady(at:now)==nil",
        'queue.takeReady(at:now.addingTimeInterval(1))?.lines==["第一条"]',
        "queue.count(for:1)==20",
        "queue.count(for:1)==20",
        'queue.takeReady(at:now.addingTimeInterval(1))?.lines==["消息0"]',
        'queue.takeReady(at:now.addingTimeInterval(1))?.lines==["消息\\(index)"]',
        "queue.count(for:1)==0",
        "(0..<9).map{_inbackoff.next()}==[1,2,4,8,16,32,60,60,60]",
    )
    assert source.count("#expect(") == len(expected)
    for expression in expected:
        assert "#expect(" + expression + ")" in source
    # Swift Testing evaluates a function-call receiver through an immutable
    # macro parameter. Read the mutating queue once before unwrapping its value.
    assert source.count("letready=queue.takeReady(at:now)letfailed=try#require(ready)") == 2
    assert "#require(queue.takeReady" not in source
    assert source.count("queue.takeReady(at:now)") == 4
    assert "forindexin0..<20" in source and "forindexin1..<20" in source


def test_coregraphics_ocr_fixture_and_strict_bilingual_assertions_remain():
    source = compact((TEST_DIRECTORY / "test_local_watch_ocr.swift").read_text(encoding="utf-8"))
    for required in (
        "importCoreGraphics", "try#require(CGContext(", "width:1200,height:340",
        'trydraw("张三：今晚开会",fontName:"PingFangSC-Regular",y:240,in:context)',
        'trydraw("Downloadcomplete",fontName:"Helvetica",y:85,in:context)',
        "try#require(context.makeImage())", "tryOCRRecognizer.lines(in:image)",
        '#expect(lines.contains(where:{$0.contains("张三：今晚开会")}))',
        '#expect(lines.contains(where:{$0.contains("Downloadcomplete")}))',
        'try#require(lines.firstIndex(where:{$0.contains("张三")}))',
        'try#require(lines.firstIndex(where:{$0.contains("Download")}))',
        "#expect(chineseIndex<englishIndex)", "try#require(CGFont(fontNameasCFString))",
        "try#require(font.table(for:0x636D6170))",
        "try#require(font.getGlyphAdvances(glyphs:glyphs,count:glyphs.count,advances:&advances))",
        "context.showGlyphs(glyphs,at:positions)", "ifu16(table)==12",
        "elseifu16(table)==4&&scalar<=0xFFFF",
        'try#require(false,"Systemfontlacksarequiredglyph")',
    ):
        assert required in source
    assert source.count("#expect(") == 3
    assert source.count("#require(") == 8
    assert not re.search(r"try\?|catch", source), "OCR failures must remain test failures"


def test_every_swift_test_uses_the_clt_testing_framework_without_dependencies():
    files = sorted((ROOT / "watcher-mac/Tests").rglob("*.swift"))
    assert {item.name for item in files} == set(FILES_AND_METHODS)
    for file in files:
        assert "import Testing" in file.read_text(encoding="utf-8")
    package = (ROOT / "watcher-mac/Package.swift").read_text(encoding="utf-8")
    assert ".package(" not in package
    assert '.testTarget(name: "FionaWatcherCoreTests", dependencies: ["FionaWatcherCore"])' in package
