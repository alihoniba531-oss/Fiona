#!/usr/bin/env python3
"""T2 令牌层：按 verify/t2_edits.json 逐条、按字节套用 28 条改动。

用法（仓库根或任意目录）：
    python3 docs/tasks/2026-10-30-design-system/impl/apply_t2.py [--dry-run]

规则（02-spec.md §T2）：
- 以 JSON 顺序执行；每条替换前断言 old 在当前文件内容里恰好出现 count 次；
- 按字节读写（read_bytes / decode("utf-8") / encode("utf-8")），不碰别的字符；
- 全部 28 条都通过断言后才写盘（内存两阶段），失败时不写任何文件。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
ROOT = TASK_DIR.parents[2]
EDITS_PATH = TASK_DIR / "verify" / "t2_edits.json"
ALLOWED_FILES = {
    "frontend/app/globals.css",
    "frontend/lib/utils.ts",
    "frontend/components/Seal.tsx",
}
EXPECTED_N = 28


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(msg: str) -> "NoReturn":
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_edits() -> list[dict]:
    edits = json.loads(EDITS_PATH.read_text(encoding="utf-8"))
    if not isinstance(edits, list) or len(edits) != EXPECTED_N:
        fail(f"t2_edits.json 应为 {EXPECTED_N} 条，实际 {len(edits) if isinstance(edits, list) else type(edits)}")
    for i, e in enumerate(edits, 1):
        if set(e) != {"n", "file", "count", "old", "new"}:
            fail(f"第 {i} 条字段不是 n/file/count/old/new：{sorted(e)}")
        if e["n"] != i:
            fail(f"第 {i} 条 n={e['n']}，顺序不符")
        if e["file"] not in ALLOWED_FILES:
            fail(f"第 {i} 条指向白名单外文件：{e['file']}")
        if not isinstance(e["count"], int) or e["count"] < 1:
            fail(f"第 {i} 条 count 非法：{e['count']!r}")
        if not isinstance(e["old"], str) or e["old"] == "":
            fail(f"第 {i} 条 old 为空")
        if not isinstance(e["new"], str):
            fail(f"第 {i} 条 new 不是字符串")
    files = sorted({e["file"] for e in edits})
    if files != sorted(ALLOWED_FILES):
        fail(f"条目覆盖的文件集合不符：{files}")
    return edits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只做断言与内存套用，不写盘")
    args = ap.parse_args()

    edits = load_edits()
    raw_before = {rel: (ROOT / rel).read_bytes() for rel in ALLOWED_FILES}
    text = {}
    for rel, data in raw_before.items():
        try:
            text[rel] = data.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - 防御
            fail(f"{rel} 不是合法 UTF-8：{exc}")
        if text[rel].encode("utf-8") != data:
            fail(f"{rel} UTF-8 往返后字节不一致")

    print(f"edits: {len(edits)}  files: {len(raw_before)}")
    print(f"{'n':>3}  {'file':<30} {'count':>5} {'found':>5} {'bytes':>7}  result")
    print("-" * 78)
    rows = []
    for e in edits:
        rel, old, new, want = e["file"], e["old"], e["new"], e["count"]
        cur = text[rel]
        found = cur.count(old)
        if found != want:
            fail(
                f"第 {e['n']} 条 {rel}: old 应出现 {want} 次，实际 {found} 次；未写任何文件。\n"
                f"old={old!r}"
            )
        if found == 0:  # 与上面的 found != want 重复，保留以明确“必须恰好出现”
            fail(f"第 {e['n']} 条 {rel}: old 出现 0 次")
        nxt = cur.replace(old, new)
        expected_len = len(cur) + found * (len(new) - len(old))
        if len(nxt) != expected_len:
            fail(f"第 {e['n']} 条 {rel}: 替换后长度 {len(nxt)} != 预期 {expected_len}")
        text[rel] = nxt
        delta = len(nxt.encode("utf-8")) - len(cur.encode("utf-8"))
        rows.append((e["n"], rel, want, found, delta))
        print(f"{e['n']:>3}  {rel:<30} {want:>5} {found:>5} {delta:>+7}  OK")

    raw_after = {rel: t.encode("utf-8") for rel, t in text.items()}

    # 结构自检：行尾、文件末尾换行、行数。
    def lines(data: bytes) -> int:
        return data.count(b"\n")

    print("-" * 78)
    for rel in sorted(ALLOWED_FILES):
        b, a = raw_before[rel], raw_after[rel]
        if b"\r" in a:
            fail(f"{rel}: 结果含 CR")
        if b.endswith(b"\n") != a.endswith(b"\n"):
            fail(f"{rel}: 文件末尾换行状态改变")
        print(
            f"{rel}: bytes {len(b)} -> {len(a)} ({len(a) - len(b):+d}), "
            f"lines {lines(b)} -> {lines(a)} ({lines(a) - lines(b):+d}), "
            f"sha256 {sha256(b)[:12]} -> {sha256(a)[:12]}"
        )

    if args.dry_run:
        print("DRY-RUN: all 28 assertions passed; nothing written.")
        return 0

    for rel, data in raw_after.items():
        (ROOT / rel).write_bytes(data)

    # 写盘后逐字节复读校验。
    for rel, expected in raw_after.items():
        got = (ROOT / rel).read_bytes()
        if got != expected:
            fail(f"{rel}: 写盘后复读字节与内存结果不一致")
    print(f"APPLIED: {len(edits)} edits in {len(ALLOWED_FILES)} files; post-write byte check OK.")
    print("expected sha256:")
    for rel in sorted(ALLOWED_FILES):
        print(f"  {sha256(raw_after[rel])}  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
