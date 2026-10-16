"""Verify R2 scope from workspace snapshots; no network or package dependencies."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
start = json.loads((evidence / "r2-start-sha256.json").read_text())
original = json.loads((evidence / "baseline-sha256.json").read_text())
report_path = "docs/tasks/2026-10-11-local-watch/03-report.md"
expected_changes = {
    "backend/database.py", "backend/routers/local_watch.py",
    "backend/services/local_watch.py", "frontend/lib/localWatch.ts",
    "frontend/components/LocalWatchSection.tsx",
    "backend/tests/test_local_watch_backend.py",
    "backend/tests/test_local_watch_frontend.py", report_path,
}
new_tests = {
    "backend/tests/test_local_watch_backend_r2.py",
    "backend/tests/test_local_watch_service_r2.py",
    "backend/tests/test_local_watch_frontend_r2.py",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def changed(snapshot):
    return sorted(path for path, value in snapshot.items()
                  if not (root / path).is_file()
                  or digest((root / path).read_bytes()) != value)


changed_existing = changed(start)
assert set(changed_existing) == expected_changes, changed_existing
assert changed(original) == ["backend/database.py"], changed(original)
original_tests = sorted(path for path in original if path.startswith("backend/tests/"))
assert len(original_tests) == 99
unchanged_tests = sorted(path for path in start if path.startswith("backend/tests/")
                         and path not in expected_changes)
assert all(path not in changed_existing for path in unchanged_tests)
assert all(path not in start and (root / path).is_file() for path in new_tests)

backend_before = (evidence / "r2-backend-contract-before.py").read_bytes()
backend_after = (root / "backend/tests/test_local_watch_backend.py").read_bytes()
assert digest(backend_before) == start["backend/tests/test_local_watch_backend.py"]
backend_diff = list(difflib.ndiff(backend_before.decode().splitlines(), backend_after.decode().splitlines()))
removed = [line[2:] for line in backend_diff if line.startswith("- ")]
added = [line[2:] for line in backend_diff if line.startswith("+ ")]
assert len(removed) == len(added) == 1
assert added[0].replace(', "content"', "") == removed[0]

frontend_after = (root / "backend/tests/test_local_watch_frontend.py").read_text()
frontend_before = frontend_after
for addition in (
    ",content:'【本机提醒 · Safari】下载完成（规则：下载）'",
    ",content:'【本机提醒 · 行情】价格上涨（规则：股价）'",
):
    assert frontend_before.count(addition) == 1
    frontend_before = frontend_before.replace(addition, "", 1)
expect_after = 'assert message["content"] == "【本机提醒 · Safari】下载完成（规则：下载）"'
expect_before = 'assert message["content"] == "【本机提醒 · 下载】下载完成（规则：下载）"'
assert frontend_before.count(expect_after) == 1
frontend_before = frontend_before.replace(expect_after, expect_before, 1)
assert digest(frontend_before.encode()) == start["backend/tests/test_local_watch_frontend.py"]
contract_diff = "".join(difflib.unified_diff(
    backend_before.decode().splitlines(keepends=True), backend_after.decode().splitlines(keepends=True),
    fromfile="before/backend/tests/test_local_watch_backend.py", tofile="after/backend/tests/test_local_watch_backend.py",
)) + "".join(difflib.unified_diff(
    frontend_before.splitlines(keepends=True), frontend_after.splitlines(keepends=True),
    fromfile="before/backend/tests/test_local_watch_frontend.py", tofile="after/backend/tests/test_local_watch_frontend.py",
))
(evidence / "r2-contract-tests.diff").write_text(contract_diff)

database_before = (evidence / "r2-database-before.py").read_text()
database_after = (root / "backend/database.py").read_text()
assert digest(database_before.encode()) == start["backend/database.py"]
matcher = difflib.SequenceMatcher(None, database_before.splitlines(), database_after.splitlines(), autojunk=False)
opcodes = matcher.get_opcodes()
assert all(tag in {"equal", "insert"} for tag, *_ in opcodes)
database_added = sum(j2 - j1 for tag, i1, i2, j1, j2 in opcodes if tag == "insert")
assert database_added == 50
database_diff = "".join(difflib.unified_diff(
    database_before.splitlines(keepends=True), database_after.splitlines(keepends=True),
    fromfile="before/backend/database.py", tofile="after/backend/database.py",
))
(evidence / "r2-database-increment.diff").write_text(database_diff)
git_stats = subprocess.check_output(["git", "diff", "--numstat", "--", "backend/database.py"], cwd=root, text=True).strip().split()
assert git_stats == ["249", "0", "backend/database.py"], git_stats

report_before = (evidence / "r2-report-before.md").read_bytes()
report_after = (root / report_path).read_bytes()
assert report_after.startswith(report_before)
appendix = report_after[len(report_before):].decode()
assert appendix.count("\n## R2\n") == 1
assert "/Users/" not in appendix and str(root) not in appendix
watcher_files = sorted(path for path in start if path.startswith("watcher-mac/"))
assert all(path not in changed_existing for path in watcher_files)

audit = {
    "changed_existing_files": changed_existing,
    "new_test_files": sorted(new_tests),
    "unexpected_changed_files": [],
    "original_test_files_unchanged": len(original_tests),
    "r2_start_non_contract_test_files_unchanged": len(unchanged_tests),
    "contract_test_changes": {
        "backend": "one response field whitelist assertion adds content; before snapshot hash verified",
        "frontend": "two fixtures add content, one expected content changes; reverse edits match before hash",
    },
    "database_r2_diff": {"added": database_added, "deleted": 0, "existing_lines_preserved": True},
    "database_original_task_diff": {"added": int(git_stats[0]), "deleted": int(git_stats[1])},
    "original_baseline_changed_files": changed(original),
    "watcher_files_unchanged": len(watcher_files),
    "previous_report_bytes_preserved": len(report_before),
    "report_append_only": True,
}
(evidence / "r2-scope-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(audit, ensure_ascii=False, indent=2))
