"""第四批「设计系统收口」Claude 门禁。

用法：
  python3 -I gate_b4.py manifest <工作树>          派单前记下本任务目录里 Claude 文件的 sha256
  python3 -I gate_b4.py check <工作树> [基线提交]   门禁；退出码 = 失败项数

check 做的事：
  1. 改动集合 ⊆ 白名单（含未跟踪文件）
  2. 02-spec.md 与 verify/** 的 sha256 与派单时一致
  3. 从基线提交 git archive 出「标准答案」：套总表 → 令牌层 28 条 → 测试字面量 29 行，
     与候选逐字节比对（76 个总表文件 + utils.ts + Seal.tsx + 10 个既有测试）
  4. backend/tests 既有文件的 numstat 与附件一致
  5. diff 新增行里没有粗体、没有「·」
  6. 参考实现：源码规则 0 命中、对比度 0 不达标、生成 CSS 0 违规
  7. 4 个新测试存在；frontend/README.md 有「设计令牌与门禁」一节
"""
import collections, csv, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = "docs/tasks/2026-10-30-design-system"
MANIFEST = os.path.join(HERE, "dispatch-manifest.json")
NEW_TESTS = ["backend/tests/test_design_system_gate.py", "backend/tests/test_design_tokens_contrast.py",
             "backend/tests/test_design_system_cn.py", "backend/tests/test_design_system_css.py"]


def sh(args, cwd=None, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败 {args}: {r.stderr[:400]}")
    return r


def claude_files(wt):
    out = {}
    for base, _dirs, names in os.walk(os.path.join(wt, TASK)):
        for n in names:
            rel = os.path.relpath(os.path.join(base, n), wt)
            if rel in (f"{TASK}/02-spec.md", f"{TASK}/04-review.md") or rel.startswith(f"{TASK}/verify/") or re.fullmatch(re.escape(TASK) + r"/05-fix-r\d+\.md", rel):
                out[rel] = hashlib.sha256(open(os.path.join(wt, rel), "rb").read()).hexdigest()
    return dict(sorted(out.items()))


def read_tsv(path):
    return list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE))


def main():
    mode, wt = sys.argv[1], os.path.abspath(sys.argv[2])
    if mode == "manifest":
        files = claude_files(wt)
        json.dump(files, open(MANIFEST, "w"), ensure_ascii=False, indent=1)
        print(f"manifest: {len(files)} 个文件 → {MANIFEST}")
        return 0
    base = sys.argv[3] if len(sys.argv) > 3 else "647a486"
    V = os.path.join(wt, TASK, "verify")
    table = read_tsv(os.path.join(V, "replacements.tsv"))
    lits = read_tsv(os.path.join(V, "test_literals.tsv"))
    table_files = sorted({"frontend/" + r["file"] for r in table})
    lit_files = sorted({"backend/tests/" + r["file"] for r in lits})
    fails = []

    def report(name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    # 1 改动集合
    st = sh(["git", "status", "--porcelain", "--untracked-files=all"], cwd=wt).stdout.splitlines()
    paths = [l[3:].split(" -> ")[-1].strip('"') for l in st if l.strip()]
    allowed = set(table_files) | {"frontend/app/globals.css", "frontend/lib/utils.ts", "frontend/components/Seal.tsx",
                                   "frontend/README.md"} | set(NEW_TESTS) | set(lit_files)
    extra = [p for p in paths if p not in allowed and not p.startswith(TASK + "/")]
    in_task = [p for p in paths if p.startswith(TASK + "/")]
    bad_task = [p for p in in_task if not (p == f"{TASK}/03-report.md" or p.startswith(f"{TASK}/impl/")
                                           or p in (f"{TASK}/02-spec.md", f"{TASK}/04-review.md") or p.startswith(f"{TASK}/verify/")
                                           or re.fullmatch(re.escape(TASK) + r"/05-fix-r\d+\.md", p))]
    report("1 改动集合 ⊆ 白名单", not extra and not bad_task, f"{len(paths)} 个路径" + (f"；白名单外 {extra[:8]} {bad_task[:8]}" if extra or bad_task else ""))

    # 2 Claude 文件未被改
    if os.path.exists(MANIFEST):
        want, got = json.load(open(MANIFEST)), claude_files(wt)
        diff = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
        report("2 02-spec.md 与 verify/** 未被改动", not diff, f"{len(want)} 个文件" + (f"；变化 {diff[:6]}" if diff else ""))
    else:
        report("2 02-spec.md 与 verify/** 未被改动", False, "缺 dispatch-manifest.json（派单前先跑 manifest）")

    # 3 标准答案逐字节比对
    tmp = tempfile.mkdtemp(prefix="b4-oracle-")
    try:
        arc = subprocess.run(["git", "archive", base, "frontend/app", "frontend/components", "frontend/lib", "backend/tests"],
                             cwd=wt, capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", tmp], input=arc, check=True)
        sh([sys.executable, "-I", os.path.join(HERE, "apply_map.py"), os.path.join(V, "replacements.tsv"), os.path.join(tmp, "frontend")])
        extra = [os.path.join(V, f) for f in sorted(os.listdir(V)) if re.fullmatch(r"r\d+_edits\.json", f)]   # 返修单的逐字改动
        for e in [e for path in [os.path.join(V, "t2_edits.json")] + extra for e in json.load(open(path, encoding="utf-8"))]:   # T2：28 条逐字改动，再加返修
            p2 = os.path.join(tmp, e["file"]); s2 = open(p2, "rb").read().decode("utf-8")
            assert s2.count(e["old"]) == e["count"], ("T2", e["n"], s2.count(e["old"]))
            open(p2, "wb").write(s2.replace(e["old"], e["new"]).encode("utf-8"))
        by = collections.defaultdict(list)
        for r in lits:
            by[r["file"]].append(r)
        for f, rs in by.items():
            p = os.path.join(tmp, "backend/tests", f)
            raw = open(p, "rb").read().decode("utf-8")
            lines = raw.split("\n")
            for r in rs:
                i = int(r["line"]) - 1
                assert lines[i].count(r["old"]) == 1, (f, r["line"], r["old"])
                lines[i] = lines[i].replace(r["old"], r["new"])
            open(p, "wb").write("\n".join(lines).encode("utf-8"))
        cmp_files = table_files + ["frontend/lib/utils.ts", "frontend/components/Seal.tsx"] + lit_files
        cmp_files = sorted(set(cmp_files))
        mism = [f for f in cmp_files if open(os.path.join(tmp, f), "rb").read() != open(os.path.join(wt, f), "rb").read()]
        report("3 与标准答案逐字节一致", not mism, f"{len(cmp_files)} 个文件" + (f"；不一致 {len(mism)}：{mism[:6]}" if mism else ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4 既有测试 numstat
    want_n = collections.Counter("backend/tests/" + r["file"] for r in lits)
    ns = sh(["git", "diff", "--numstat", base, "--", "backend/tests/"], cwd=wt).stdout.splitlines()
    got_n = {}
    for l in ns:
        a, d, p = l.split("\t")
        got_n[p] = (int(a), int(d))
    bad_n = {p: v for p, v in got_n.items() if want_n.get(p) is None or v != (want_n[p], want_n[p])}
    missing_n = [p for p in want_n if p not in got_n]
    report("4 既有测试只改附件的 29 行", not bad_n and not missing_n and sum(want_n.values()) == 29,
           f"{len(got_n)} 个文件" + (f"；不符 {bad_n} 缺 {missing_n}" if bad_n or missing_n else ""))

    # 5 粗体与中点：逐文件比较基线与候选的出现次数，只许持平或减少（改到的行里原有的 <b className="font-normal"> 和「·」不算新增）
    BOLD = re.compile(r"font-semibold|font-bold|fontWeight|<strong\b|<b[\s>]")
    grew_bold, grew_dot = [], []
    scope = set(table_files) | {"frontend/lib/utils.ts", "frontend/components/Seal.tsx", "frontend/README.md"} | set(lit_files)
    for p in paths:
        if p not in scope or not os.path.isfile(os.path.join(wt, p)):
            continue
        after = open(os.path.join(wt, p), encoding="utf-8").read()
        r = subprocess.run(["git", "show", f"{base}:{p}"], cwd=wt, capture_output=True)
        before = r.stdout.decode("utf-8") if r.returncode == 0 else ""
        if len(BOLD.findall(after)) > len(BOLD.findall(before)):
            grew_bold.append(p)
        if after.count("·") > before.count("·"):
            grew_dot.append(p)
    report("5 没有新增粗体", not grew_bold, f"{grew_bold[:4]}" if grew_bold else "")
    report("5 没有新增「·」", not grew_dot, f"{grew_dot[:4]}" if grew_dot else "")

    # 6 参考实现
    r = sh([sys.executable, "-I", os.path.join(V, "ref/gate_rules.py"), wt], check=False)
    report("6 源码规则 0 命中", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[:200])
    r = sh([sys.executable, "-I", os.path.join(V, "ref/contrast_check.py"), os.path.join(wt, "frontend/app/globals.css")], check=False)
    report("6 令牌对比度全部达标", r.returncode == 0, r.stdout.strip().splitlines()[-1][:200] if r.stdout.strip() else r.stderr[:200])
    r = sh(["node", os.path.join(V, "ref/gate_twcss.mjs"), os.path.join(wt, "frontend")], check=False)
    line = [l for l in r.stdout.splitlines() if l.startswith("scannedFiles=")]
    report("6 生成 CSS 0 违规", r.returncode == 0, line[0] if line else r.stderr[-200:])

    # 7 新测试与文档
    miss = [t for t in NEW_TESTS if not os.path.isfile(os.path.join(wt, t))]
    report("7 4 个新测试存在", not miss, f"缺 {miss}" if miss else "")
    readme = open(os.path.join(wt, "frontend/README.md"), encoding="utf-8").read()
    report("7 frontend/README.md 有「设计令牌与门禁」", "设计令牌与门禁" in readme)

    print("== FAIL", len(fails), fails)
    return len(fails)


if __name__ == "__main__":
    sys.exit(main())
