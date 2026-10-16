import CoreGraphics
import Foundation
import Vision

public enum OCRRecognizer {
    public static func lines(in image: CGImage) throws -> [String] {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "en-US"]
        request.usesLanguageCorrection = true
        try VNImageRequestHandler(cgImage: image).perform([request])
        let observations = (request.results ?? []).sorted { $0.boundingBox.maxY > $1.boundingBox.maxY }
        // Group items on the same text row, then read that row left to right.
        // Vision's normalized coordinates start at the bottom of the image.
        var rows: [[VNRecognizedTextObservation]] = []
        for observation in observations {
            if let last = rows.last, let anchor = last.first,
               abs(anchor.boundingBox.midY - observation.boundingBox.midY) <=
                min(anchor.boundingBox.height, observation.boundingBox.height) * 0.5 {
                rows[rows.count - 1].append(observation)
            } else {
                rows.append([observation])
            }
        }
        return rows.flatMap { row in
            row.sorted { $0.boundingBox.minX < $1.boundingBox.minX }
                .compactMap { $0.topCandidates(1).first?.string }
        }
    }
}

public enum FrameFingerprint {
    public static func hash(_ image: CGImage) throws -> UInt64 {
        let size = 64
        var pixels = [UInt8](repeating: 0, count: size * size)
        let success = pixels.withUnsafeMutableBytes { bytes -> Bool in
            guard let context = CGContext(
                data: bytes.baseAddress, width: size, height: size, bitsPerComponent: 8,
                bytesPerRow: size, space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGImageAlphaInfo.none.rawValue
            ) else { return false }
            context.interpolationQuality = .low
            context.draw(image, in: CGRect(x: 0, y: 0, width: size, height: size))
            return true
        }
        guard success else { throw WatcherError.imageProcessing }
        return pixels.reduce(UInt64(14695981039346656037)) { ($0 ^ UInt64($1)) &* 1099511628211 }
    }
}
