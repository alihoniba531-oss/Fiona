#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T1: apply verify/replacements.tsv to the 76 frontend files.

Implements docs/tasks/2026-10-30-design-system/02-spec.md §T1 rules 0-6,
and the reverse check in §T1 rule 7.

Rules honoured here:
  * columns are Unicode code points (Python str indexes), not bytes;
  * app/page.tsx is read/written as bytes through str.decode("utf-8") /
    str.encode("utf-8") -- never utf-8-sig -- so its UTF-8 BOM survives;
  * every file is LF and keeps its final newline;
  * rows are grouped by file, then applied per line from the largest col to
    the smallest col;
  * before every replacement the original text at line:col is asserted to be
    exactly `old`; any mismatch aborts the whole run without writing;
  * empty `new`, `old` beginning with a space, empty `old` (insertion), and
    ordinary replacement are handled as four distinct cases.

Usage:
    python3 docs/tasks/2026-10-30-design-system/impl/apply_t1.py apply
    python3 docs/tasks/2026-10-30-design-system/impl/apply_t1.py apply --dry-run
    python3 docs/tasks/2026-10-30-design-system/impl/apply_t1.py verify
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
TASK_DIR = REPO / "docs/tasks/2026-10-30-design-system"
TSV = TASK_DIR / "verify/replacements.tsv"
FRONTEND = REPO / "frontend"
BOM = b"\xef\xbb\xbf"
HEADER = ("file", "line", "col", "old", "new", "kind", "note")
KINDS = {"size", "color", "syntax", "legacy", "contrast"}
EXPECTED_ROWS = 1158
EXPECTED_FILES = 76

# §T1 rule 3 examples, verbatim results after the whole line has been applied.
# plaza 517 is the §T1 rule 4 example and is pinned too.
SPECIAL_EXPECTED = {
    ("app/login/page.tsx", 145):
        '          <h1 className="mt-11 text-fs-76 font-light leading-none '
        'tracking-[0.01em] max-md:mt-7">Chloe</h1>',
    ("components/MessageText.tsx", 69):
        '            : "tracking-[.08em] text-[color:var(--ink2)]";',
    ("app/profile/page.tsx", 98):
        '              <h1 className={`mt-[18px] text-fs-30 font-medium '
        'tracking-[0.16em] ${embedded ? " sr-only" : ""}`}>社交画像（旧版）</h1>',
    ("app/plaza/page.tsx", 517):
        '                              <span className="ml-1 text-fs-11">（链接失效）</span>',
}


class T1Failure(Exception):
    """Abort the whole run; nothing is silently skipped or repaired."""


def fail(message: str) -> None:
    raise T1Failure(message)


def check(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


@dataclass(frozen=True)
class Row:
    tsv_line: int
    file: str
    line: int
    col: int
    old: str
    new: str
    kind: str
    note: str


def load_rows() -> list[Row]:
    raw = TSV.read_bytes()
    check(not raw.startswith(BOM), f"{TSV}: unexpected UTF-8 BOM")
    check(raw.count(b"\r") == 0, f"{TSV}: unexpected CR")
    check(raw.endswith(b"\n"), f"{TSV}: missing final newline")
    text = raw.decode("utf-8")
    records = text.split("\n")
    check(records[-1] == "", f"{TSV}: final newline handling")
    header = tuple(records[0].split("\t"))
    check(header == HEADER, f"{TSV}: unexpected header {header!r}")

    rows: list[Row] = []
    seen_cols: set[tuple[str, int, int]] = set()
    for offset, record in enumerate(records[1:-1], start=2):
        parts = record.split("\t")
        check(len(parts) == 7, f"{TSV}:{offset}: expected 7 fields, got {len(parts)}")
        file, line_s, col_s, old, new, kind, note = parts
        check(file != "", f"{TSV}:{offset}: empty file")
        rel = PurePosixPath(file)
        check(not rel.is_absolute() and ".." not in rel.parts,
              f"{TSV}:{offset}: unsafe file path {file!r}")
        check((FRONTEND / file).resolve().is_relative_to(FRONTEND.resolve()),
              f"{TSV}:{offset}: file escapes frontend/")
        check((FRONTEND / file).is_file(), f"{TSV}:{offset}: missing frontend/{file}")
        try:
            line = int(line_s)
            col = int(col_s)
        except ValueError:
            fail(f"{TSV}:{offset}: non-integer line/col {line_s!r}/{col_s!r}")
        check(line >= 1 and col >= 1, f"{TSV}:{offset}: line/col must start at 1")
        check(kind in KINDS, f"{TSV}:{offset}: unknown kind {kind!r}")
        key = (file, line, col)
        check(key not in seen_cols, f"{TSV}:{offset}: duplicate {key}")
        seen_cols.add(key)
        rows.append(Row(offset, file, line, col, old, new, kind, note))

    check(len(rows) == EXPECTED_ROWS,
          f"{TSV}: expected {EXPECTED_ROWS} rows, got {len(rows)}")
    files = {row.file for row in rows}
    check(len(files) == EXPECTED_FILES,
          f"{TSV}: expected {EXPECTED_FILES} files, got {len(files)}")
    return rows


def group_rows(rows: list[Row]) -> dict[str, dict[int, list[Row]]]:
    grouped: dict[str, dict[int, list[Row]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.file][row.line].append(row)
    for by_line in grouped.values():
        for line_rows in by_line.values():
            line_rows.sort(key=lambda row: row.col, reverse=True)
    return {file: dict(by_line) for file, by_line in grouped.items()}


def head_blob(file: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"HEAD:frontend/{file}"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    check(proc.returncode == 0,
          f"git show HEAD:frontend/{file} failed: {proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout


def decode_checked(blob: bytes, file: str, where: str) -> str:
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{where}: frontend/{file} is not valid UTF-8: {exc}")
    check("\r" not in text, f"{where}: frontend/{file} contains CR (expected LF only)")
    check(text.endswith("\n"), f"{where}: frontend/{file} lacks its final newline")
    return text


def check_worktree_matches_head(files: list[str]) -> None:
    for file in files:
        path = FRONTEND / file
        current = path.read_bytes()
        head = head_blob(file)
        check(current == head,
              f"precondition: frontend/{file} differs from HEAD before T1; "
              "table coordinates are HEAD-relative")


def apply_line(file: str, line_no: int, original: str, line_rows: list[Row]) -> tuple[str, list[str]]:
    """Apply every row of one line, largest col first (§T1 rules 1-6)."""
    line = original
    cases: list[str] = []

    for row in sorted(line_rows, key=lambda item: item.col, reverse=True):
        idx = row.col - 1
        check(0 <= idx <= len(line),
              f"{file}:{line_no}:{row.col}: col outside line (len={len(line)})")

        if row.old != "":
            actual = line[idx:idx + len(row.old)]
            check(actual == row.old,
                  f"{file}:{line_no}:{row.col}: expected {row.old!r} at line:col, "
                  f"found {actual!r}")
        else:
            # §T1 rule 5: col points at the first char after className=".
            check(idx > 0 and line[idx - 1] == '"',
                  f"{file}:{line_no}:{row.col}: insertion is not right after '\"'")
            check(idx == len(line) or line[idx] != " ",
                  f"{file}:{line_no}:{row.col}: insertion point starts with a space")

        if row.new == "" and row.old != "" and not row.old.startswith(" "):
            # §T1 rule 3: delete this class and fix the adjacent space.
            right = line[idx + len(row.old):]
            if right.startswith("${"):
                # (c) right neighbour is ${: remove only the class, keep both spaces.
                line = line[:idx] + right
                cases.append("rule3c")
            elif idx > 0 and line[idx - 1] == " ":
                # (a) left neighbour is a space, right is not ${: drop class + left space.
                line = line[:idx - 1] + line[idx + len(row.old):]
                cases.append("rule3a")
            else:
                # (b) class follows a quote: drop class + right space.
                check(right.startswith(" "),
                      f"{file}:{line_no}:{row.col}: (b) expected a space on the right")
                line = line[:idx] + line[idx + len(row.old) + 1:]
                cases.append("rule3b")
        elif row.old.startswith(" "):
            # §T1 rule 4: remove exactly the old segment, leading space included.
            check(row.new == "",
                  f"{file}:{line_no}:{row.col}: expected empty new for leading-space old")
            line = line[:idx] + line[idx + len(row.old):]
            cases.append("rule4")
        elif row.old == "":
            # §T1 rule 5: insert new at col.
            line = line[:idx] + row.new + line[idx:]
            cases.append("insert")
        else:
            # §T1 rule 6: straight replacement.
            line = line[:idx] + row.new + line[idx + len(row.old):]
            cases.append("replace")

    expected = SPECIAL_EXPECTED.get((file, line_no))
    if expected is not None:
        check(line == expected,
              f"{file}:{line_no}: result after §T1 examples mismatch\n"
              f"  expected: {expected!r}\n  actual:   {line!r}")
    return line, cases


def apply_all(rows: list[Row], dry_run: bool) -> None:
    grouped = group_rows(rows)
    files = sorted(grouped)
    check_worktree_matches_head(files)

    candidates: dict[str, tuple[bytes, bytes]] = {}
    case_counts: Counter[str] = Counter()
    changed_files = 0

    for file in files:
        source_path = FRONTEND / file
        source_bytes = source_path.read_bytes()
        source_text = decode_checked(source_bytes, file, "apply source")
        lines = source_text.split("\n")
        by_line = grouped[file]
        max_line = max(by_line)
        check(max_line <= len(lines),
              f"{file}: table references line {max_line}, file has {len(lines) - 1}")

        for line_no in sorted(by_line):
            original = lines[line_no - 1]
            new_line, cases = apply_line(file, line_no, original, by_line[line_no])
            lines[line_no - 1] = new_line
            case_counts.update(cases)

        output_text = "\n".join(lines)
        output_bytes = output_text.encode("utf-8")
        check(output_bytes.startswith(BOM) == source_bytes.startswith(BOM),
              f"{file}: BOM presence changed")
        if file == "app/page.tsx":
            check(source_bytes.startswith(BOM) and output_bytes.startswith(BOM),
                  "app/page.tsx: UTF-8 BOM must be preserved")
        check(output_bytes.count(b"\r") == 0, f"{file}: output contains CR")
        check(output_bytes.endswith(b"\n"), f"{file}: output lost final newline")
        check(output_bytes.count(b"\n") == source_bytes.count(b"\n"),
              f"{file}: newline count changed")
        if output_bytes != source_bytes:
            changed_files += 1
        candidates[file] = (source_bytes, output_bytes)

    applied_rows = sum(len(line_rows) for by_line in grouped.values()
                       for line_rows in by_line.values())
    check(applied_rows == len(rows), f"applied {applied_rows} rows, table has {len(rows)}")
    check(len(candidates) == EXPECTED_FILES, "did not build all 76 candidates")

    expected_cases = Counter({
        "replace": 1146,
        "insert": 8,
        "rule3a": 1,
        "rule3b": 1,
        "rule3c": 1,
        "rule4": 1,
    })
    check(case_counts == expected_cases,
          f"case counts mismatch: expected {dict(expected_cases)}, got {dict(case_counts)}")

    replaced_lines = sum(len(by_line) for by_line in grouped.values())
    print(f"table rows: {applied_rows}")
    print(f"files: {len(candidates)}")
    print(f"lines with replacements: {replaced_lines}")
    print(f"case counts: {dict(sorted(case_counts.items()))}")
    print(f"files whose bytes change: {changed_files}")

    for file, line_no in sorted(SPECIAL_EXPECTED):
        line = candidates[file][1].decode("utf-8").split("\n")[line_no - 1]
        print(f"special {file}:{line_no}: OK")
        print(f"  {line}")

    if dry_run:
        print("DRY RUN: no files written")
        return

    for file in files:
        source_bytes, output_bytes = candidates[file]
        path = FRONTEND / file
        path.write_bytes(output_bytes)
        written = path.read_bytes()
        check(written == output_bytes, f"{file}: on-disk bytes differ after write")
        check(len(written) == len(output_bytes) and written != source_bytes,
              f"{file}: expected a byte change after apply")

    print("APPLIED: 76 files written")
    print("PASS: every row matched line:col before replacement")


def expected_line(head_line: str, line_rows: list[Row], file: str, line_no: int) -> tuple[str, list[tuple[Row, int, str]]]:
    """Rebuild the expected line from HEAD, left to right (§T1 rule 7).

    This is deliberately a separate, ascending reconstruction rather than the
    descending in-place edit used by apply_line.
    """
    edits: list[tuple[int, int, str, Row]] = []
    for row in sorted(line_rows, key=lambda item: item.col):
        idx = row.col - 1
        if row.old != "":
            actual = head_line[idx:idx + len(row.old)]
            check(actual == row.old,
                  f"verify {file}:{line_no}:{row.col}: HEAD has {actual!r}, "
                  f"table expects {row.old!r}")
        else:
            check(idx > 0 and head_line[idx - 1] == '"',
                  f"verify {file}:{line_no}:{row.col}: insertion not after '\"'")

        if row.new == "" and row.old != "" and not row.old.startswith(" "):
            right = head_line[idx + len(row.old):]
            if right.startswith("${"):
                start, end = idx, idx + len(row.old)
            elif idx > 0 and head_line[idx - 1] == " ":
                start, end = idx - 1, idx + len(row.old)
            else:
                check(right.startswith(" "),
                      f"verify {file}:{line_no}:{row.col}: (b) expected right space")
                start, end = idx, idx + len(row.old) + 1
            edits.append((start, end, "", row))
        elif row.old.startswith(" "):
            edits.append((idx, idx + len(row.old), row.new, row))
        elif row.old == "":
            edits.append((idx, idx, row.new, row))
        else:
            edits.append((idx, idx + len(row.old), row.new, row))

    parts: list[str] = []
    positions: list[tuple[Row, int, str]] = []
    cursor = 0
    out_len = 0
    for start, end, new, row in edits:
        check(start >= cursor,
              f"verify {file}:{line_no}: overlapping edits at cols {cursor}/{start}")
        chunk = head_line[cursor:start]
        parts.append(chunk)
        out_len += len(chunk)
        positions.append((row, out_len, new))
        parts.append(new)
        out_len += len(new)
        cursor = end
    parts.append(head_line[cursor:])
    return "".join(parts), positions


def verify_all(rows: list[Row]) -> None:
    grouped = group_rows(rows)
    files = sorted(grouped)
    content_lines = 0
    final_newline_sentinels = 0
    replaced_lines = 0
    new_positions = 0
    differing_files = 0
    line_failures: list[str] = []

    for file in files:
        head_bytes = head_blob(file)
        path = FRONTEND / file
        candidate_bytes = path.read_bytes()
        head_text = decode_checked(head_bytes, file, "HEAD")
        candidate_text = decode_checked(candidate_bytes, file, "candidate")

        check(candidate_bytes.startswith(BOM) == head_bytes.startswith(BOM),
              f"verify {file}: BOM presence changed")
        if file == "app/page.tsx":
            check(head_bytes.startswith(BOM) and candidate_bytes.startswith(BOM),
                  "verify app/page.tsx: UTF-8 BOM is not preserved")
        if candidate_bytes != head_bytes:
            differing_files += 1

        head_lines = head_text.split("\n")
        candidate_lines = candidate_text.split("\n")
        check(len(head_lines) == len(candidate_lines),
              f"verify {file}: line count changed")

        expected_lines: list[str] = []
        for line_no, head_line in enumerate(head_lines, start=1):
            line_rows = grouped[file].get(line_no, [])
            if line_rows:
                want, positions = expected_line(head_line, line_rows, file, line_no)
                replaced_lines += 1
            else:
                want, positions = head_line, []

            got = candidate_lines[line_no - 1]
            if got != want:
                # Pinpoint the first mismatch for the report.
                diff_at = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b),
                               min(len(got), len(want)))
                line_failures.append(
                    f"{file}:{line_no}: expected {want!r}, got {got!r} "
                    f"(first difference at char {diff_at + 1})")
                continue

            for row, start, new in positions:
                if new == "":
                    continue
                actual = got[start:start + len(new)]
                if actual != new:
                    line_failures.append(
                        f"{file}:{line_no}:{row.col}: new {new!r} not at expected "
                        f"char {start + 1}, found {actual!r}")
                else:
                    new_positions += 1

            expected_lines.append(want)
            if line_no == len(head_lines):
                final_newline_sentinels += 1
            else:
                content_lines += 1

        if line_failures:
            break

        expected_bytes = "\n".join(expected_lines).encode("utf-8")
        check(candidate_bytes == expected_bytes,
              f"verify {file}: rebuilt bytes differ from candidate")
        check(candidate_bytes.count(b"\n") == head_bytes.count(b"\n"),
              f"verify {file}: newline count changed")
        check(candidate_bytes.endswith(b"\n"), f"verify {file}: lost final newline")

    if line_failures:
        fail("reverse check failed:\n" + "\n".join(line_failures[:20]))

    print(f"reverse check files: {len(files)}")
    print(f"reverse check content lines: {content_lines}")
    print(f"reverse check final-newline sentinels: {final_newline_sentinels}")
    print(f"reverse check lines with replacements: {replaced_lines}")
    print(f"reverse check table rows replayed: {len(rows)}")
    print(f"reverse check non-empty new placements verified: {new_positions}")
    print(f"files whose bytes differ from HEAD: {differing_files}")
    print("PASS: every candidate line equals HEAD with that line's table rows replayed")
    print("PASS: every non-empty new sits at its expected position; "
          "all other characters match HEAD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T1 replacements.tsv applier / verifier")
    parser.add_argument("action", choices=("apply", "verify"))
    parser.add_argument("--dry-run", action="store_true",
                        help="for apply: validate and print, but do not write")
    args = parser.parse_args(argv)
    try:
        rows = load_rows()
        if args.action == "apply":
            apply_all(rows, dry_run=args.dry_run)
        else:
            verify_all(rows)
    except T1Failure as exc:
        print(f"T1 FAIL: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
