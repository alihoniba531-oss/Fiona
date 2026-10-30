#!/usr/bin/env python3
"""独立复核 T2：把最终文件按 JSON 逆序回滚，必须逐字节还原为套用前快照。

- 正向套用见 apply_t2.py；本脚本不复用其替换逻辑，而是反方向逐条撤销：
  * new 非空：断言 new 恰好出现 count 次，再 replace(new, old)；
  * new 为空：断言 old 已不存在（count 必须为 0）。
- 全部撤销后，三个文件必须与 `--before` 目录下的快照逐字节相同。
- 快照可用以下方式重建：utils.ts / Seal.tsx 取 `git show HEAD:`，
  globals.css 取 HEAD + A 的 T1 两处（或直接用套用前备份）。

用法：
    python3 docs/tasks/2026-10-30-design-system/impl/verify_t2.py [--before DIR]
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


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(msg: str) -> "NoReturn":
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="/tmp/fiona-t2-before")
    args = ap.parse_args()
    before_dir = Path(args.before)
    edits = json.loads(EDITS_PATH.read_text(encoding="utf-8"))

    files = sorted({e["file"] for e in edits})
    final = {rel: (ROOT / rel).read_bytes() for rel in files}
    before = {}
    for rel in files:
        src = before_dir / Path(rel).name
        if not src.exists():
            fail(f"缺少套用前快照：{src}")
        before[rel] = src.read_bytes()
    if len(before) != 3:
        fail("快照文件数不是 3")

    texts = {rel: data.decode("utf-8") for rel, data in final.items()}
    print(f"reverse check: {len(edits)} edits, {len(files)} files")
    print(f"{'n':>3}  {'file':<30} {'count':>5} {'found':>5}  reverse")
    print("-" * 72)

    # 删除项（new 为空）没有可逆的 new 串。先用套用前快照正向删掉这些段，
    # 得到“只缺删除项、其余 24 条均已撤销”时应当逐字相等的基准。
    expected = {rel: data.decode("utf-8") for rel, data in before.items()}
    for e in edits:
        if e["new"] != "":
            continue
        rel, old, want = e["file"], e["old"], e["count"]
        found_before = expected[rel].count(old)
        if found_before != want:
            fail(f"第 {e['n']} 条 {rel}: 套用前快照里 old 应出现 {want} 次，实际 {found_before} 次")
        found_final = texts[rel].count(old)
        if found_final != 0:
            fail(f"第 {e['n']} 条 {rel}: 删除项 old 仍出现 {found_final} 次")
        expected[rel] = expected[rel].replace(old, "")
        print(f"{e['n']:>3}  {rel:<30} {want:>5} {found_before:>5}  删除项：套用前 {want} 次、最终 0 次 OK")

    for e in reversed(edits):
        rel, old, new, want = e["file"], e["old"], e["new"], e["count"]
        if new == "":
            continue  # 删除项已在上面核对
        cur = texts[rel]
        found = cur.count(new)
        if found != want:
            fail(f"第 {e['n']} 条 {rel}: 反向时 new 应出现 {want} 次，实际 {found} 次")
        texts[rel] = cur.replace(new, old)
        print(f"{e['n']:>3}  {rel:<30} {want:>5} {found:>5}  撤销 OK")

    print("-" * 72)
    ok = True
    for rel in files:
        rebuilt = texts[rel].encode("utf-8")
        want_bytes = expected[rel].encode("utf-8")
        same = rebuilt == want_bytes
        ok = ok and same
        print(
            f"{rel}: reconstructed == before-minus-deletions ? {same}  "
            f"(expected {sha256(want_bytes)[:12]}, rebuilt {sha256(rebuilt)[:12]})"
        )
    if not ok:
        fail("逆序回滚结果与套用前快照（扣除 4 个删除项）不一致")
    print("PASS: reverse replay of all 28 edits byte-exactly restores the pre-T2 files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
