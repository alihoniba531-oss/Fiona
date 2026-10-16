import Foundation

public enum LineNormalizer {
    public static func normalize(_ lines: [String]) -> [String] {
        lines.compactMap { raw in
            let line = raw.components(separatedBy: .whitespacesAndNewlines)
                .filter { !$0.isEmpty }.joined(separator: " ")
            guard line.count >= 2 else { return nil }
            let punctuation = CharacterSet.punctuationCharacters.union(.symbols)
                .union(.whitespacesAndNewlines)
            guard !line.unicodeScalars.allSatisfy({ punctuation.contains($0) }) else { return nil }
            let number = #"^[+-]?(?:\p{N}{1,3}(?:,\p{N}{3})+|\p{N}+)(?:\.\p{N}+)?%?$"#
            guard line.range(of: number, options: .regularExpression) == nil else { return nil }
            let time = #"^(?:(?:[0-2]?\d:[0-5]\d(?::[0-5]\d)?)(?:\s?(?:AM|PM))?|今天|昨天|前天|明天|后天|刚刚|现在|(?:星期|周|礼拜)[一二三四五六日天]|(?:上午|下午|早上|晚上|中午|凌晨)(?:\s*[0-2]?\d:[0-5]\d)?|\d{4}[-/]\d{1,2}[-/]\d{1,2})$"#
            guard line.range(of: time, options: [.regularExpression, .caseInsensitive]) == nil else { return nil }
            return line
        }
    }
}

/// A baseline and at most three previous captures stay in memory only.
public struct SnapshotHistory {
    private var snapshots: [Set<String>] = []

    public init() {}

    public mutating func observe(_ lines: [String]) -> [String] {
        let baseline = snapshots.isEmpty
        let recent = snapshots.reduce(into: Set<String>()) { $0.formUnion($1) }
        var emitted = Set<String>()
        let newLines = baseline ? [] : lines.filter { !recent.contains($0) && emitted.insert($0).inserted }
        snapshots.append(Set(lines))
        if snapshots.count > 3 { snapshots.removeFirst(snapshots.count - 3) }
        return newLines
    }
}

public enum ObservationLimits {
    public static func lines(_ lines: [String]) -> [String] {
        var remaining = 4000
        var result: [String] = []
        for line in lines.prefix(50) where remaining > 0 {
            // Unicode scalar count agrees with the backend's character limit,
            // including combining marks and emoji sequences.
            let truncated = String(String.UnicodeScalarView(line.unicodeScalars.prefix(remaining)))
            guard !truncated.isEmpty else { continue }
            result.append(truncated)
            remaining -= truncated.unicodeScalars.count
        }
        return result
    }
}
