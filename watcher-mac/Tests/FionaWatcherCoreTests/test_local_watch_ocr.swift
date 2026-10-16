import CoreGraphics
import Foundation
import Testing
@testable import FionaWatcherCore

struct LocalWatchOCRTests {
    @Test
    func testRecognizesChineseAndEnglishDrawnByCoreGraphics() throws {
        let context = try #require(CGContext(
            data: nil, width: 1200, height: 340, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ))
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 1200, height: 340))
        context.setFillColor(CGColor(gray: 0, alpha: 1))
        try draw("张三：今晚开会", fontName: "PingFangSC-Regular", y: 240, in: context)
        try draw("Download complete", fontName: "Helvetica", y: 85, in: context)
        let image = try #require(context.makeImage())
        let lines = try OCRRecognizer.lines(in: image)
        #expect(lines.contains(where: { $0.contains("张三：今晚开会") }))
        #expect(lines.contains(where: { $0.contains("Download complete") }))
        let chineseIndex = try #require(lines.firstIndex(where: { $0.contains("张三") }))
        let englishIndex = try #require(lines.firstIndex(where: { $0.contains("Download") }))
        #expect(chineseIndex < englishIndex)
    }

    // CoreGraphics does not shape text. This test maps Unicode scalars through the
    // system font's cmap table, then draws the resulting glyphs with CoreGraphics.
    private func draw(_ text: String, fontName: String, y: CGFloat, in context: CGContext) throws {
        let font = try #require(CGFont(fontName as CFString))
        let cmap = try #require(font.table(for: 0x636D6170)) as Data
        let glyphs = try text.unicodeScalars.map { try glyph(for: $0.value, cmap: cmap) }
        var advances = [Int32](repeating: 0, count: glyphs.count)
        try #require(font.getGlyphAdvances(glyphs: glyphs, count: glyphs.count, advances: &advances))
        let size: CGFloat = 62
        var x: CGFloat = 45
        let positions = advances.map { advance -> CGPoint in
            defer { x += CGFloat(advance) * size / CGFloat(font.unitsPerEm) }
            return CGPoint(x: x, y: y)
        }
        context.setFont(font)
        context.setFontSize(size)
        context.textMatrix = .identity
        context.showGlyphs(glyphs, at: positions)
    }

    private func glyph(for scalar: UInt32, cmap: Data) throws -> CGGlyph {
        func u16(_ offset: Int) -> UInt16 {
            UInt16(cmap[offset]) << 8 | UInt16(cmap[offset + 1])
        }
        func u32(_ offset: Int) -> UInt32 {
            UInt32(u16(offset)) << 16 | UInt32(u16(offset + 2))
        }
        for record in 0..<Int(u16(2)) {
            let table = Int(u32(4 + record * 8 + 4))
            if u16(table) == 12 {
                for group in 0..<Int(u32(table + 12)) {
                    let offset = table + 16 + group * 12
                    let start = u32(offset), end = u32(offset + 4)
                    if scalar >= start && scalar <= end {
                        return CGGlyph(u32(offset + 8) + scalar - start)
                    }
                }
            } else if u16(table) == 4 && scalar <= 0xFFFF {
                let count = Int(u16(table + 6)) / 2
                let ends = table + 14, starts = ends + count * 2 + 2
                let deltas = starts + count * 2, ranges = deltas + count * 2
                for segment in 0..<count where scalar >= u16(starts + segment * 2) && scalar <= u16(ends + segment * 2) {
                    let delta = u16(deltas + segment * 2)
                    let range = Int(u16(ranges + segment * 2))
                    if range == 0 { return CGGlyph((UInt16(scalar) &+ delta)) }
                    let offset = ranges + segment * 2 + range + 2 * Int(scalar - UInt32(u16(starts + segment * 2)))
                    let value = u16(offset)
                    return value == 0 ? 0 : value &+ delta
                }
            }
        }
        try #require(false, "System font lacks a required glyph")
        return 0
    }
}
