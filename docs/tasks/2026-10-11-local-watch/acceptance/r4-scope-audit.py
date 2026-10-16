"""Offline R4 scope, author-edit, test, and append-only report audit."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
start = json.loads((evidence / "r4-start-sha256.json").read_text())
original = json.loads((evidence / "baseline-sha256.json").read_text())
generated = {"frontend/tsconfig.tsbuildinfo"}
report_path = "docs/tasks/2026-10-11-local-watch/03-report.md"
authorized_test_updates = {
    "backend/tests/test_local_watch_backend_r2.py",
    "backend/tests/test_local_watch_capture_backend_r3.py",
    "backend/tests/test_local_watch_capture_frontend_r3.py",
    "watcher-mac/CaptureStatusTests/test_local_watch_capture_status.swift",
}
expected_changes = authorized_test_updates | {
    "backend/routers/local_watch.py",
    "frontend/lib/localWatch.ts",
    "frontend/components/LocalWatchSection.tsx",
    "watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift",
    report_path,
}
expected_new = {
    "backend/tests/test_local_watch_capture_backend_r4.py",
    "backend/tests/test_local_watch_capture_frontend_r4.py",
    "backend/tests/test_local_watch_swift_recovery_r4.py",
    "watcher-mac/CaptureStatusTests/test_local_watch_capture_recovery_r4.swift",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def changed(snapshot):
    return sorted(path for path, value in snapshot.items()
                  if path not in generated and (not (root / path).is_file()
                  or digest((root / path).read_bytes()) != value))


changes = changed(start)
assert set(changes) == expected_changes, changes
assert changed(original) == ["backend/database.py"], changed(original)
assert all(path not in start and (root / path).is_file() for path in expected_new)
original_tests = sorted(path for path in original if path.startswith("backend/tests/"))
assert len(original_tests) == 99
prior_tests = sorted(path for path in start
                     if path.startswith(("backend/tests/", "watcher-mac/Tests/", "watcher-mac/CaptureStatusTests/")))
assert set(prior_tests).intersection(changes) == authorized_test_updates
prior_test_sources = [path for path in prior_tests if path.endswith((".py", ".swift"))]
original_swift_tests = sorted(path for path in start
                              if path.startswith("watcher-mac/Tests/") and path.endswith(".swift"))
assert len(original_swift_tests) == 3
assert not set(original_swift_tests).intersection(changes)
assert "backend/database.py" not in changes
git_stats = subprocess.check_output(
    ["git", "diff", "--numstat", "--", "backend/database.py"], cwd=root, text=True).strip().split()
assert git_stats == ["249", "0", "backend/database.py"], git_stats

protected_files = {
    "backend/llm.py", "backend/intent_router.py", "backend/mode_switcher.py", "backend/crisis_model.py",
    "backend/safety.py", "backend/services/chat_service.py", "backend/services/claude_agent.py",
    "backend/routers/chat.py",
}
protected_prefixes = ("backend/byok/", "backend/tools/", "desktop/")
protected = sorted(path for path in start if path in protected_files or path.startswith(protected_prefixes))
assert all(path not in changes for path in protected)

source = (root / "backend/routers/local_watch.py").read_text()
function = next(node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef) and node.name == "capture_message")
author_function = (evidence / "r4-author-capture-message-before.txt").read_text()
# The snapshot ends with the source line's newline; AST source segments omit it.
assert ast.get_source_segment(source, function) + "\n" == author_function
assert (root / "watcher-mac/README.md").read_bytes() == (evidence / "r4-author-watcher-readme-before.md").read_bytes()
author_domain = '(False, "com.apple.ScreenCaptureKit.SCStreamErrorDomain/-3811", CAPTURE_ERROR)'
backend_before = (evidence / "r4-before/backend/tests/test_local_watch_capture_backend_r3.py").read_text()
backend_after = (root / "backend/tests/test_local_watch_capture_backend_r3.py").read_text()
assert author_domain in backend_before and author_domain in backend_after

test_diff = []
for path in sorted(authorized_test_updates):
    before_path = evidence / "r4-before" / path
    assert digest(before_path.read_bytes()) == start[path], path
    test_diff.extend(difflib.unified_diff(
        before_path.read_text().splitlines(keepends=True),
        (root / path).read_text().splitlines(keepends=True),
        fromfile="before/" + path, tofile="after/" + path))
(evidence / "r4-tests-adjustments.diff").write_text("".join(test_diff))

before = (evidence / "r4-report-before.md").read_bytes()
after = (root / report_path).read_bytes()
assert after.startswith(before)
appendix = after[len(before):].decode()
assert appendix.count("\n## R4\n") == 1
assert "/Users/" not in appendix and str(root) not in appendix
assert not (root / "watcher-mac/.build").exists(), "Swift sandbox cache must be deleted"
swift_cleanup = json.loads((evidence / "r4-swift-cleanup-audit.json").read_text())
assert swift_cleanup["final_build_directory_absent"]
assert all(item["build_directory_removed"] for item in swift_cleanup["commands"].values())

audit = {
    "changed_existing_files": changes,
    "new_test_files": sorted(expected_new),
    "unexpected_changed_files": [],
    "generated_cache_excluded": sorted(generated),
    "original_task_test_files_unchanged": len(original_tests),
    "original_swift_test_sources_unchanged": original_swift_tests,
    "r4_start_test_files": len(prior_tests),
    "r4_start_test_files_unchanged": len(prior_tests) - len(authorized_test_updates),
    "r4_start_python_swift_test_sources": len(prior_test_sources),
    "authorized_task_test_updates": sorted(authorized_test_updates),
    "test_adjustment_diff": "r4-tests-adjustments.diff",
    "protected_files_unchanged": len(protected),
    "database_r4_diff": {"added": 0, "deleted": 0},
    "database_original_task_diff": {"added": 249, "deleted": 0},
    "author_capture_message_source_unchanged": True,
    "author_full_error_domain_test_preserved": True,
    "author_watcher_readme_bytes_unchanged": True,
    "previous_report_bytes_preserved": len(before),
    "report_append_only": True,
    "watcher_build_cache_exists_after_acceptance": False,
}
(evidence / "r4-scope-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(audit, ensure_ascii=False, indent=2))
