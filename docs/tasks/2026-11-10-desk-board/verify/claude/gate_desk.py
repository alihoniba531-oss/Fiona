"""案头第一期 · 机械门禁（Claude 在执行者沙箱外运行）。

用法：python3 -I gate_desk.py <工作树> <规格哈希文件> [--skip-build] [--skip-full]
逐项打印 PASS / FAIL，最后一行 `== FAIL n / m`。每一项都先确认它真的扫到了东西。
"""
import re
import subprocess
import sys
from pathlib import Path

WT = Path(sys.argv[1]).resolve()
HASHES = Path(sys.argv[2]).resolve()
SKIP_BUILD = "--skip-build" in sys.argv
SKIP_FULL = "--skip-full" in sys.argv
TASK = "docs/tasks/2026-11-10-desk-board"
BASE = "9adf34cd104a6e46f2a0c22c7bda2be4c7ef5aaa"
BASELINE_PASSED = 7911
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}  {str(detail)[:400]}")


def run(cmd, cwd=WT, timeout=1800):
    if not Path(cwd).is_dir():
        return 127, f"目录不存在：{cwd}"
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def git(*args):
    return run(["git", "-c", "core.quotepath=off", *args])


# ---- G1 规格快照没被动过 ----
code, out = run(["shasum", "-a", "256", "-c", str(HASHES)], cwd=WT / TASK)
lines = [l for l in out.splitlines() if l.strip()]
chk("G1 规格、返修单、复核报告与参考稿哈希未变（19 个文件）", code == 0 and len(lines) == 19 and all(l.endswith(": OK") for l in lines), out[-300:])

# ---- G2 改动集合 ⊆ 白名单 ----
code, out = git("status", "--porcelain", "--untracked-files=all")
paths = [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]
pre = {f"{TASK}/{n}" for n in ("01-brief.md", "02-spec.md", "03-dispatch.md", "04-fix-r1.md", "05-review.md", "06-fix-r2.md", "07-fix-r3.md", "08-review-r2.md", "09-fix-r4.md", "10-review-r3.md", "11-fix-r5.md", "12-review-r4.md")}
allowed = [
    re.compile(r"^frontend/lib/desk\.ts$"), re.compile(r"^frontend/components/desk/[A-Za-z0-9_]+\.tsx$"),
    re.compile(r"^frontend/app/page\.tsx$"), re.compile(r"^frontend/app/globals\.css$"),
    re.compile(r"^backend/tests/test_desk_[a-z0-9_]+\.py$"),
    re.compile(r"^backend/tests/test_ui_closeout_dialog_scrim\.py$"),  # v1.1 授权：仅 13→14 一处
    re.compile(r"^(CLAUDE|README|PLAN)\.md$"), re.compile(r"^docs/ARCHITECTURE\.md$"),
    re.compile(rf"^{re.escape(TASK)}/impl/.+$"),
]
# design/ 是参考稿，verify/ 是验收方自己的脚本与结果，都不算实施方的改动
mine = [p for p in paths if p not in pre and not p.startswith((f"{TASK}/design/", f"{TASK}/verify/"))]
outside = [p for p in mine if not any(rx.match(p) for rx in allowed)]
chk("G2 git status 扫到了改动（非空）", len(mine) >= 8, len(mine))
chk("G2 改动全部在白名单内", not outside, outside)
print("   改动清单：", mine)

# ---- G3 后端非测试零改动、既有测试零改动、依赖文件零改动 ----
code, out = git("diff", "--name-only", BASE, "--", "backend")
chk("G3 backend/ 下只有授权的那一个既有测试被改", code == 0 and out.split() == ["backend/tests/test_ui_closeout_dialog_scrim.py"], out)
code, out = git("diff", "-U0", BASE, "--", "backend/tests/test_ui_closeout_dialog_scrim.py")
t_removed = [l for l in out.splitlines() if l.startswith("-") and not l.startswith("---")]
t_added = [l for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]
chk("G3 该测试只改一行：expected_count 13→14", t_removed == ["-def assert_dialogs_have_scrim(sources, *, expected_count=13):"] and t_added == ["+def assert_dialogs_have_scrim(sources, *, expected_count=14):"], (t_removed, t_added))
new_tests = sorted(p for p in mine if p.startswith("backend/tests/test_desk_"))
chk("G3 新测试文件 4 个（含容器竞态用例）", len(new_tests) >= 4 and "backend/tests/test_desk_dock_races_frontend.py" in new_tests, new_tests)
code, out = git("diff", "--name-only", BASE, "--", "frontend/package.json", "frontend/package-lock.json", "backend/requirements.txt", "backend/requirements-dev.txt")
chk("G3 依赖文件未改", code == 0 and not out.strip(), out)
code, out = git("diff", "--name-only", BASE, "--", "frontend")
changed_fe = set(out.split())
chk("G3 frontend 已跟踪文件只改了 page.tsx（可含 globals.css）", changed_fe <= {"frontend/app/page.tsx", "frontend/app/globals.css"} and "frontend/app/page.tsx" in changed_fe, sorted(changed_fe))

# ---- G4 page.tsx：BOM、锁定字面量、接线计数、删行审计 ----
raw = (WT / "frontend/app/page.tsx").read_bytes()
src = raw.decode("utf-8")
chk("G4 page.tsx 仍以 BOM 开头", raw[:3] == b"\xef\xbb\xbf")
LOCKED = ['const openNovelAt = (path: string) => {', 'onOpenNovel={openNovelAt}',
          'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")', 'src={novelFrameSrc}',
          'studioAllowed ? <iframe', 'key={username}', 'src="/studio?embed=1"']
for lit in LOCKED:
    chk(f"G4 字面量仍在：{lit[:40]}", lit in src)
chk('G4 aria-controls="desk-panel" 恰一次', src.count('aria-controls="desk-panel"') == 1, src.count('aria-controls="desk-panel"'))
chk("G4 <DeskDock 恰一次", src.count("<DeskDock") == 1, src.count("<DeskDock"))
i_desk, i_read = src.find('aria-controls="desk-panel"'), src.find('aria-label="朗读"')
chk("G4 案头开关在朗读按钮之前", 0 < i_desk < i_read, (i_desk, i_read))
i_mount, i_panel, i_agent = src.find("<DeskDock"), src.find("data-chat-panel"), src.find('id="agent-drawer"')
chk("G4 DeskDock 挂在聊天面板之后、抽屉之前", 0 < i_panel < i_mount < i_agent, (i_panel, i_mount, i_agent))
code, out = git("diff", "-U0", BASE, "--", "frontend/app/page.tsx")
removed = [l for l in out.splitlines() if l.startswith("-") and not l.startswith("---")]
added = [l for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]
chk("G4 page.tsx 有新增行", len(added) >= 10, len(added))
chk("G4 流式卡片处改用 deskAutoOpens(window.innerWidth)", src.count("deskAutoOpens(window.innerWidth)") == 1 and 'deskMode(window.innerWidth) !== "sheet"' not in src, src.count("deskAutoOpens(window.innerWidth)"))
chk("G4 page.tsx 删除的行不超过 3 行（应只有 import 行被替换）", len(removed) <= 3, removed)
print("   page.tsx 新增", len(added), "行；被替换的行：", removed)

# ---- G5 globals.css：要么不动，要么只加 .desk- 规则 ----
code, out = git("diff", "-U0", BASE, "--", "frontend/app/globals.css")
g_removed = [l for l in out.splitlines() if l.startswith("-") and not l.startswith("---")]
g_added = [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]
css_ok = not g_removed and "::backdrop" not in "\n".join(g_added) and not re.search(r"^\s*--[\w-]+\s*:", "\n".join(g_added), re.M)
chk("G5 globals.css 无删除、无新 ::backdrop、无新变量", css_ok, (g_removed[:3], g_added[:3]))

# ---- G6 新文件齐全 + 我自己的禁用写法扫描 ----
desk_dir = WT / "frontend/components/desk"
need = ["DeskDock.tsx", "DeskFrame.tsx", "DeskIdeaView.tsx", "DeskChaptersView.tsx", "DeskEpisodesView.tsx", "DeskDialogs.tsx"]
have = sorted(p.name for p in desk_dir.glob("*.tsx")) if desk_dir.is_dir() else []
chk("G6 六个组件文件齐全", all(n in have for n in need), have)
scan = [desk_dir / n for n in have] + [WT / "frontend/lib/desk.ts"]
texts = {str(p.relative_to(WT)): p.read_text(encoding="utf-8") for p in scan if p.is_file()}
chk("G6 扫描面非空且含 lib/desk.ts", len(texts) >= 7 and "frontend/lib/desk.ts" in texts, len(texts))
BANNED = {
    "加粗类": r"font-(?:medium|semibold|bold|extrabold|black)\b", "字重": r"fontWeight|font-weight",
    "十六进制色": r"#[0-9A-Fa-f]{3,8}\b", "rgb()": r"\brgba?\(", "印色/ink3/dim": r"var\(--(?:stamp|ink3|dim)\)",
    "iframe": r"<iframe", "fetch": r"\bfetch\(", "卡片堆叠": r"ceramic-card", "任意字号": r"text-\[\d",
}
for label, rx in BANNED.items():
    hits = [(name, m.group(0)) for name, text in texts.items() for m in re.finditer(rx, text)]
    chk(f"G6 新代码不含 {label}", not hits, hits[:5])
probe = {"x.tsx": 'className="font-medium text-[13px]" style={{color:"#A8322A"}} <iframe fetch( rgba(0,0,0,.1) var(--stamp) ceramic-card fontWeight'}
caught = sum(1 for rx in BANNED.values() if any(re.search(rx, t) for t in probe.values()))
chk("G6 自检：扫描器能抓到全部 9 类违规样本", caught == len(BANNED), caught)
dialogs_src = texts.get("frontend/components/desk/DeskDialogs.tsx", "")
chk("G6 DeskDialogs.tsx 里 JSX <dialog 恰一次", dialogs_src.count("<dialog") == 1, dialogs_src.count("<dialog"))
evade = [(n, m.group(0)) for n, t in texts.items() for m in re.finditer(r"""createElement\(\s*["']dialog["']""", t)]
chk("G6 没有用 createElement 躲开对话框扫描", not evade and bool(dialogs_src), evade)
chk("G6 自检：能抓到 createElement(\"dialog\")", bool(re.search(r"""createElement\(\s*["']dialog["']""", 'React.createElement("dialog", {})')))
desk_ts = texts.get("frontend/lib/desk.ts", "")
chk("G6 lib/desk.ts 导出三个新函数", all(f"export function {n}(" in desk_ts for n in ("deskAutoOpens", "isRevisionConflict", "deskStageByKey")))
frame_src = texts.get("frontend/components/desk/DeskFrame.tsx", "")
ep_src = texts.get("frontend/components/desk/DeskEpisodesView.tsx", "")
chk("G6 分集对话框的 busy 不再含锁定状态", bool(ep_src) and "busy={busy || " not in ep_src, ep_src.count("busy={busy || "))
chk("G6 DeskFrame 改用 deskStageByKey、不再用 useRovingTabs、标签带 data-stage", "deskStageByKey(" in frame_src and "useRovingTabs" not in frame_src and frame_src.count("data-stage=") >= 2, (frame_src.count("deskStageByKey("), frame_src.count("useRovingTabs"), frame_src.count("data-stage=")))
import hashlib
r2_hash = (HASHES.parent / "out/page-tsx-r2.sha256").read_text().strip()
chk("G4 page.tsx 与 R2 结束时逐字节相同（R3 没碰它）", hashlib.sha256(raw).hexdigest() == r2_hash, hashlib.sha256(raw).hexdigest()[:16])
code_rt, out_rt = git("diff", "--name-only", BASE, "--", "frontend/lib/useRovingTabs.ts", "frontend/lib/useAccountIdentity.ts")
# R5：除容器竞态测试与任务目录外，所有改动文件与 R4 结束时逐字节相同
r4_lines = [l.split("  ", 1) for l in (HASHES.parent / "out/r4-files.sha256").read_text(encoding="utf-8").splitlines() if l.strip()]
r5_diff = [rel for digest, rel in r4_lines if rel != "backend/tests/test_desk_dock_races_frontend.py" and (not (WT / rel).is_file() or hashlib.sha256((WT / rel).read_bytes()).hexdigest() != digest)]
chk("G3 R5 只动了容器竞态测试：其余 16 个改动文件与 R4 逐字节相同", len(r4_lines) == 17 and not r5_diff, r5_diff or len(r4_lines))
races_digest = dict((rel, digest) for digest, rel in r4_lines).get("backend/tests/test_desk_dock_races_frontend.py")
races_now = (WT / "backend/tests/test_desk_dock_races_frontend.py").read_text(encoding="utf-8")
chk("G3 R5 容器竞态测试确实改了：locked 初值为 false、输出并断言 beforeActive", hashlib.sha256(races_now.encode("utf-8")).hexdigest() != races_digest and "let locked = false;" in races_now and "let locked = LOCK;" not in races_now and races_now.count('["beforeActive"] == "done"') == 2 and "beforeActive" in races_now.split("def test_non_conflict_409_keeps_reason_and_refreshes_locked_plan")[0], races_now.count("beforeActive"))
chk("G3 useRovingTabs.ts 与 useAccountIdentity.ts 未改", code_rt == 0 and not out_rt.strip(), out_rt)
dock_src = texts.get("frontend/components/desk/DeskDock.tsx", "")
bare = [l.strip()[:90] for l in dock_src.splitlines() if "window.localStorage" in l and "try" not in l]
print("   DeskDock 里出现 window.localStorage 的行（人工确认都在 try 或安全封装里）：", bare[:8])
chk("G6 lib/desk.ts 不 import react", not re.search(r"""from\s+["']react["']""", desk_ts) and len(desk_ts) > 500, len(desk_ts))
for view in ("DeskFrame.tsx", "DeskIdeaView.tsx", "DeskChaptersView.tsx", "DeskEpisodesView.tsx"):
    t = texts.get(f"frontend/components/desk/{view}", "")
    bad = re.findall(r"useAccountRequest|localStorage|listNovels\(|getNovel\(|getStudioEpisodes\(", t)
    chk(f"G6 视图 {view} 是纯展示（不取数）", t and not bad, bad)

# ---- G7 类型、lint、构建 ----
code, out = run(["npx", "tsc", "--noEmit"], cwd=WT / "frontend")
chk("G7 tsc --noEmit 退出 0", code == 0, out[-300:])
code, out = run(["npm", "run", "lint"], cwd=WT / "frontend")
m = re.search(r"\((\d+) errors?, (\d+) warnings?\)", out)
chk("G7 lint 0 errors 且 warnings ≤ 25", code == 0 and m and int(m.group(1)) == 0 and int(m.group(2)) <= 25, m.group(0) if m else out[-300:])
if SKIP_BUILD:
    print("SKIP G7 build（--skip-build）")
else:
    code, out = run(["npm", "run", "build"], cwd=WT / "frontend", timeout=1800)
    chk("G7 npm run build 退出 0", code == 0, out[-300:])

# ---- G8 新测试 ----
py = str(WT / "backend/.venv/bin/python")
if new_tests:
    code, out = run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rsf", *[str(WT / t) for t in new_tests]], cwd=WT / "backend")
else:
    code, out = 1, "没有新测试文件，不运行（否则 pytest 会去跑全量，造成假通过）"
tail = out.strip().splitlines()[-1] if out.strip() else ""
m = re.search(r"(\d+) passed", tail)
new_count = int(m.group(1)) if m else 0
chk("G8 新测试全部通过、0 失败、0 跳过（R5 不新增用例，仍是 100 条）", code == 0 and new_count == 100 and "failed" not in tail and "skipped" not in tail, tail)

# ---- G9 全量 ----
if SKIP_FULL:
    print("SKIP G9 全量 pytest（--skip-full）")
else:
    code, out = run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=WT / "backend", timeout=3600)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    m = re.search(r"(\d+) passed", tail)
    total = int(m.group(1)) if m else 0
    chk(f"G9 全量 = {BASELINE_PASSED} + {new_count}，0 失败、0 跳过", code == 0 and total == BASELINE_PASSED + new_count and "failed" not in tail and "skipped" not in tail, tail)

print(f"== FAIL {results.count(False)} / {len(results)}")
