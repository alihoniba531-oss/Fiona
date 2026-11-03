"""第五批（UI 复核收尾）机械门禁：规格 §5 第 1–7 条，由 Claude 在沙箱外跑。

用法：python3 -I gate_b5.py <工作树> <HEAD 副本> [--skip-build] [--skip-pytest]
逐条打印 PASS/FAIL 与实际值，末尾 `== FAIL n`，退出码 = n。
HEAD 副本用于「新测试在 HEAD 上必须失败」的对照：把新测试和两个门禁文件拷进去跑，跑完按 git 原样还原。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
HEAD = os.path.abspath(sys.argv[2])
SKIP_BUILD = "--skip-build" in sys.argv
SKIP_PYTEST = "--skip-pytest" in sys.argv

ALLOWED_MODIFIED = {
    "frontend/app/page.tsx", "frontend/app/history/page.tsx", "frontend/app/globals.css",
    "frontend/components/ConfirmDialog.tsx", "frontend/components/GeneratedImage.tsx", "frontend/components/SongProjectCard.tsx",
    "frontend/components/novel/NovelSettingsDialog.tsx", "frontend/components/studio/BrainTrial.tsx", "frontend/components/studio/QuoteDialog.tsx",
    "frontend/components/studio/ShotCard.tsx", "frontend/components/studio/SourceChoices.tsx",
    "backend/tests/test_design_system_gate.py", "backend/tests/test_design_system_css.py", "backend/tests/test_ui_polish_page_contracts.py",
}
NEW_TESTS = ["test_ui_closeout_cost_hint.py", "test_ui_closeout_history_keyboard.py", "test_ui_closeout_dialog_scrim.py", "test_ui_closeout_structure_guards.py"]
NEW_PREFIX = ("backend/tests/test_ui_closeout_", "docs/tasks/2026-11-02-ui-closeout/")
BASE_PASSED = 7836

ENV = {k: v for k, v in os.environ.items() if k.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}}
ENV["npm_config_cache"] = "/tmp/fiona-npm-cache"

fails = 0
N = 0


def chk(name: str, ok: bool, detail: str = "") -> None:
    global fails, N
    N += 1
    if not ok:
        fails += 1
    print(f"{'PASS' if ok else 'FAIL'} {name}  {detail}")


def run(cmd, cwd, timeout=1800):
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def git(args, cwd=WT):
    return run(["git", *args], cwd)[1]


# ---- 1. 改动集合 ----
print("== 改动集合")
status = [l for l in git(["status", "--porcelain", "--untracked-files=all"]).splitlines() if l.strip()]
paths = [l[3:].strip() for l in status]
bad = [p for p in paths if p not in ALLOWED_MODIFIED and not p.startswith(NEW_PREFIX)]
chk("改动只在白名单内", not bad, str(bad))
modified_tests = [p for p in paths if p.startswith("backend/tests/") and not p.startswith("backend/tests/test_ui_closeout_")]
chk("既有测试只动三个授权文件", set(modified_tests) <= {"backend/tests/test_design_system_gate.py", "backend/tests/test_design_system_css.py", "backend/tests/test_ui_polish_page_contracts.py"}, str(modified_tests))
new_present = [t for t in NEW_TESTS if os.path.isfile(os.path.join(WT, "backend/tests", t))]
chk("四个新测试文件都在", len(new_present) == 4, str(new_present))
other_diff = git(["diff", "HEAD", "--stat", "--", "backend/tests/", ":!backend/tests/test_design_system_gate.py", ":!backend/tests/test_design_system_css.py", ":!backend/tests/test_ui_polish_page_contracts.py", ":!backend/tests/test_ui_closeout_*"]).strip()
chk("其余既有测试零 diff", other_diff == "", other_diff[:200])
print(git(["diff", "HEAD", "--stat"]))
print("-- 门禁文件的 hunk（人工核对只落在 T4 点名位置）")
print(git(["diff", "-U0", "HEAD", "--", "backend/tests/test_design_system_gate.py", "backend/tests/test_design_system_css.py"])[:6000])


# ---- 2. 计数 ----
print("== 计数")


def count_in(rel, needle):
    with open(os.path.join(WT, rel), "rb") as fh:
        return fh.read().decode("utf-8").count(needle)


def grep_count(pattern, *dirs):
    cmd = ["grep", "-rn", "--include=*.ts", "--include=*.tsx", "--include=*.css", "--include=*.js", "--include=*.mjs", "--exclude-dir=node_modules", "--exclude-dir=.next", pattern, *dirs]
    rc, out = run(cmd, WT)
    return len([l for l in out.splitlines() if l.strip()]) if rc in (0, 1) else -1


chk("frontend 里没有 backdrop: 变体", grep_count("backdrop:", "frontend/app", "frontend/components", "frontend/lib") == 0, str(grep_count("backdrop:", "frontend/app", "frontend/components", "frontend/lib")))
rc, out = run(["grep", "-rl", "scrim-dialog", "frontend/components"], WT)
files = [l for l in out.splitlines() if l.strip()]
chk("scrim-dialog 落在 8 个组件文件", len(files) == 8, str(sorted(files)))
chk("globals.css 里 ::backdrop 规则恰 2 条", count_in("frontend/app/globals.css", "::backdrop {") == 2, str(count_in("frontend/app/globals.css", "::backdrop {")))
chk("globals.css 两条 scrim 规则", count_in("frontend/app/globals.css", ".scrim-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }") == 1 and count_in("frontend/app/globals.css", ".dark .scrim-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }") == 1)
chk("history: opacity-0 字面量恰 2", count_in("frontend/app/history/page.tsx", 'className="absolute inset-0 h-full w-full cursor-pointer opacity-0"') == 2)
chk("history: tabIndex={-1} 恰 2", count_in("frontend/app/history/page.tsx", "tabIndex={-1}") == 2)
chk("history: <label className={cn(\"chip relative 恰 2", count_in("frontend/app/history/page.tsx", '<label className={cn("chip relative') == 2)
chk("history: openDatePicker(e.currentTarget) 恰 4", count_in("frontend/app/history/page.tsx", "openDatePicker(e.currentTarget)") == 4)
chk("page: 平台模型 · 每条 10 颗草莓 恰 2", count_in("frontend/app/page.tsx", '"平台模型 · 每条 10 颗草莓"') == 2)
chk("page: 每条消息消耗 字面量恰 1", count_in("frontend/app/page.tsx", '每条消息消耗 <span className="readout font-normal">10</span> 颗草莓') == 1)
chk("page: Enter 发送 恰 1", count_in("frontend/app/page.tsx", "Enter 发送，Shift + Enter 换行") == 1)
with open(os.path.join(WT, "frontend/app/page.tsx"), "rb") as fh:
    chk("page.tsx 保留 BOM", fh.read(3) == b"\xef\xbb\xbf")
page_lines = open(os.path.join(WT, "frontend/app/page.tsx"), encoding="utf-8").read().splitlines()
row_idx = [i for i, l in enumerate(page_lines) if "border-t border-[color:var(--carve)] pt-2" in l]
chk("页脚行恰 1 行且含手机 token 与 max-md:hidden 守卫", len(row_idx) == 1 and all(t in page_lines[row_idx[0]] for t in ("max-md:mt-1", "max-md:pt-1", "max-md:text-fs-11", '!hasContent && "max-md:hidden"')), str(len(row_idx)))
chk("页脚行下一行是 Enter 提示 span", len(row_idx) == 1 and page_lines[row_idx[0] + 1].strip() == '<span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>', page_lines[row_idx[0] + 1].strip()[:80] if row_idx else "")
chk("page: readout font-normal 恰 4", count_in("frontend/app/page.tsx", 'className="readout font-normal"') == 4, str(count_in("frontend/app/page.tsx", 'className="readout font-normal"')))
pc_diff = git(["diff", "-U0", "HEAD", "--", "backend/tests/test_ui_polish_page_contracts.py"])
pc_minus = [l for l in pc_diff.splitlines() if l.startswith("-") and not l.startswith("---")]
pc_plus = [l for l in pc_diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
chk("page_contracts 只改了计数那一行", len(pc_minus) == 1 and len(pc_plus) == 1 and "== 2" in pc_minus[0] and "== 4" in pc_plus[0] and pc_minus[0][1:].replace("== 2", "== 4") == pc_plus[0][1:], f"{pc_minus} -> {pc_plus}")


# ---- 3. tsc / lint / build ----
print("== tsc / lint / build")
rc, out = run(["npx", "tsc", "--noEmit"], os.path.join(WT, "frontend"), timeout=900)
chk("tsc 退出码 0", rc == 0, out[-800:] if rc else "")
rc, out = run(["npm", "run", "lint"], os.path.join(WT, "frontend"), timeout=900)
m = re.search(r"\((\d+) errors?, (\d+) warnings?\)", out) or re.search(r"(\d+) problems? \((\d+) errors?, (\d+) warnings?\)", out)
errs = warns = None
if m:
    g = m.groups(); errs, warns = int(g[-2]), int(g[-1])
elif rc == 0:
    errs, warns = 0, 0
chk("lint 0 错误、警告 ≤ 25", rc == 0 and errs == 0 and warns is not None and warns <= 25, f"rc={rc} errors={errs} warnings={warns}")
if not SKIP_BUILD:
    rc, out = run(["npm", "run", "build"], os.path.join(WT, "frontend"), timeout=1500)
    chk("build 退出码 0", rc == 0, out[-1200:] if rc else "")
else:
    print("SKIP build")


# ---- 4. pytest ----
PY = os.path.join(WT, "backend/.venv/bin/python")
PYTEST = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
print("== pytest")
rc, out = run([PY, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q", *[f"tests/{t}" for t in NEW_TESTS]], os.path.join(WT, "backend"), timeout=600)
m = re.search(r"(\d+) tests? collected", out) or re.search(r"collected (\d+) items?", out)
new_count = int(m.group(1)) if m else -1
chk("新测试可收集", new_count > 0, f"{new_count} collected")
rc, out = run([*PYTEST, "-rf", *[f"tests/{t}" for t in NEW_TESTS], "tests/test_design_system_gate.py", "tests/test_design_system_css.py", "tests/test_empty_states_history_dates.py", "tests/test_mobile_chat_fix.py", "tests/test_ui_polish_page_contracts.py", "tests/test_component_language.py", "tests/test_empty_states_settings_privacy.py", "tests/test_empty_states_chat_openers.py"], os.path.join(WT, "backend"), timeout=900)
chk("新测试 + 相关既有测试在候选上全过", rc == 0 and " passed" in out and "skipped" not in out.splitlines()[-1], out.splitlines()[-1] if out.strip() else "")
if not SKIP_PYTEST:
    rc, out = run(PYTEST, os.path.join(WT, "backend"), timeout=1800)
    last = out.strip().splitlines()[-1] if out.strip() else ""
    mp = re.search(r"(\d+) passed", last); ms = re.search(r"(\d+) skipped", last); mf = re.search(r"(\d+) failed", last)
    passed = int(mp.group(1)) if mp else -1
    chk("全量 pytest 0 failed 0 skipped", rc == 0 and not mf and not ms, last)
    chk(f"passed = {BASE_PASSED} + {new_count}", passed == BASE_PASSED + new_count, f"passed={passed}")
else:
    print("SKIP full pytest")

# ---- 5. HEAD 对照 ----
print("== HEAD 对照")
head_tests = os.path.join(HEAD, "backend/tests")
backup = {}
for f in ("test_design_system_gate.py", "test_design_system_css.py"):
    with open(os.path.join(head_tests, f), "rb") as fh:
        backup[f] = fh.read()
try:
    for f in NEW_TESTS + ["test_design_system_gate.py", "test_design_system_css.py"]:
        shutil.copyfile(os.path.join(WT, "backend/tests", f), os.path.join(head_tests, f))
    rc, out = run([*PYTEST, "-rf", *[f"tests/{t}" for t in NEW_TESTS], "tests/test_design_system_gate.py", "tests/test_design_system_css.py"], os.path.join(HEAD, "backend"), timeout=900)
    print(out[-5000:])
    failed_ids = re.findall(r"^FAILED (tests/\S+)", out, re.M)
    def failed_in(name):
        return [i for i in failed_ids if name in i]
    chk("HEAD: cost_hint 失败", bool(failed_in("test_ui_closeout_cost_hint")), str(failed_in("test_ui_closeout_cost_hint")))
    chk("HEAD: history_keyboard 失败", bool(failed_in("test_ui_closeout_history_keyboard")), str(failed_in("test_ui_closeout_history_keyboard")))
    chk("HEAD: dialog_scrim 失败", bool(failed_in("test_ui_closeout_dialog_scrim")), str(failed_in("test_ui_closeout_dialog_scrim")))
    chk("HEAD: structure_guards 通过", not failed_in("test_ui_closeout_structure_guards"), str(failed_in("test_ui_closeout_structure_guards")))
    chk("HEAD: gate::test_token_layer 失败（T8 对不上四条旧规则）", bool(failed_in("test_design_system_gate.py::test_token_layer")), str(failed_in("test_design_system_gate")))
    chk("HEAD: gate 自检通过", not failed_in("test_selfcheck_source_rules") and not failed_in("test_selfcheck_token_layer"))
    chk("HEAD: css 测试通过", not failed_in("test_design_system_css"), str(failed_in("test_design_system_css")))
    chk("HEAD: 失败全是 AssertionError", "Error" not in re.sub(r"AssertionError", "", out) or not re.search(r"\b(ImportError|FileNotFoundError|NameError|TypeError|SyntaxError)\b", out), "")
finally:
    for f in NEW_TESTS:
        try:
            os.remove(os.path.join(head_tests, f))
        except FileNotFoundError:
            pass
    for f, data in backup.items():
        with open(os.path.join(head_tests, f), "wb") as fh:
            fh.write(data)

print(f"== FAIL {fails} / {N}")
sys.exit(fails)
