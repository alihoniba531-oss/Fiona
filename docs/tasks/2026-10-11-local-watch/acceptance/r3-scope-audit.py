"""Offline scope audit of the R3 workspace and append-only report."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
start = json.loads((evidence / "r3-start-sha256.json").read_text())
original = json.loads((evidence / "baseline-sha256.json").read_text())
generated = {"frontend/tsconfig.tsbuildinfo"}
report_path = "docs/tasks/2026-10-11-local-watch/03-report.md"
expected_changes = {
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md",
    "backend/.env.example", "watcher-mac/README.md", "backend/routers/local_watch.py",
    "frontend/lib/localWatch.ts", "frontend/components/LocalWatchSection.tsx",
    "watcher-mac/Package.swift", "watcher-mac/Sources/FionaWatcherCore/Watcher.swift",
    report_path,
}
expected_new = {
    "watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift",
    "watcher-mac/CaptureStatusTests/test_local_watch_capture_status.swift",
    "backend/tests/test_local_watch_capture_backend_r3.py",
    "backend/tests/test_local_watch_capture_frontend_r3.py",
    "backend/tests/test_local_watch_capture_docs_r3.py",
    "backend/tests/test_local_watch_swift_capture_r3.py",
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
prior_tests = sorted(path for path in start
                     if path.startswith("backend/tests/") or path.startswith("watcher-mac/Tests/"))
assert all(path not in changes for path in prior_tests)
prior_test_sources = [path for path in prior_tests if path.endswith((".py", ".swift"))]
original_tests = sorted(path for path in original if path.startswith("backend/tests/"))
assert len(original_tests) == 99
assert "backend/database.py" not in changes
git_stats = subprocess.check_output(["git", "diff", "--numstat", "--", "backend/database.py"], cwd=root, text=True).strip().split()
assert git_stats == ["249", "0", "backend/database.py"]

protected_files = {
    "backend/llm.py", "backend/intent_router.py", "backend/mode_switcher.py", "backend/crisis_model.py",
    "backend/safety.py", "backend/services/chat_service.py", "backend/services/claude_agent.py",
    "backend/routers/chat.py",
}
protected_prefixes = ("backend/byok/", "backend/tools/", "desktop/")
protected = sorted(path for path in start if path in protected_files or path.startswith(protected_prefixes))
assert all(path not in changes for path in protected)
before = (evidence / "r3-report-before.md").read_bytes()
after = (root / report_path).read_bytes()
assert after.startswith(before)
appendix = after[len(before):].decode()
assert appendix.count("\n## R3\n") == 1
assert "/Users/" not in appendix and str(root) not in appendix
assert not (root / "watcher-mac/.build").exists(), "Swift sandbox cache must be deleted"

audit = {
    "changed_existing_files": changes,
    "new_implementation_and_test_files": sorted(expected_new),
    "unexpected_changed_files": [],
    "generated_cache_excluded": sorted(generated),
    "r3_start_test_files_unchanged": len(prior_tests),
    "r3_start_python_swift_test_sources_unchanged": len(prior_test_sources),
    "original_task_test_files_unchanged": len(original_tests),
    "protected_files_unchanged": len(protected),
    "database_r3_diff": {"added": 0, "deleted": 0},
    "database_original_task_diff": {"added": 249, "deleted": 0},
    "previous_report_bytes_preserved": len(before),
    "report_append_only": True,
    "watcher_build_cache_exists_after_acceptance": False,
}
(evidence / "r3-scope-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(audit, ensure_ascii=False, indent=2))
