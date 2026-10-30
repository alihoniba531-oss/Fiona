"""把 replacements.tsv 套到一份 frontend 目录上：同一行按列从大到小替换，原写法不在位置上就报错退出。"""
import csv, sys, pathlib, collections
tsv, fe = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = list(csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE))
by = collections.defaultdict(list)
for r in rows: by[r["file"]].append(r)
n = 0
for f, rs in by.items():
    p = fe / f; lines = p.read_text(encoding="utf-8").split("\n")
    for r in sorted(rs, key=lambda r: (int(r["line"]), -int(r["col"]))):
        i, c, old, new = int(r["line"]) - 1, int(r["col"]) - 1, r["old"], r["new"]
        s = lines[i]
        if s[c:c + len(old)] != old: sys.exit(f"MISMATCH {f}:{r['line']}:{r['col']} want {old!r} got {s[c:c+len(old)+8]!r}")
        if new == "" and old and not old.startswith(" "):
            # 删除整个类名：吃掉左侧一个空格；若右侧紧跟 ${ 则保留左侧空格、吃右侧空格
            if c > 0 and s[c - 1] == " " and not s[c + len(old):].startswith("${"):
                s = s[:c - 1] + s[c + len(old):]
            elif s[c + len(old):c + len(old) + 1] == " ":
                s = s[:c] + s[c + len(old) + 1:]
            else:
                s = s[:c] + s[c + len(old):]
        else:
            s = s[:c] + new + s[c + len(old):]
        lines[i] = s; n += 1
    p.write_text("\n".join(lines), encoding="utf-8")
print("applied", n, "in", len(by), "files")
