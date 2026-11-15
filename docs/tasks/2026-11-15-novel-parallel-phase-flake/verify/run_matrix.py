"""Run the three sibling-cancellation cases under injected pauses and under broken
variants of ``_gather_phase``.

Usage, from ``backend/``:

    .venv/bin/python ../docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/run_matrix.py repo
    .venv/bin/python ../docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/run_matrix.py candidate
    ... add --record to print the table without judging it (exit code 0)

``repo`` runs the tests in the repository; ``candidate`` runs the proposed form in
``candidate_parallel_phase.py``. Without ``--record`` the script checks what a
sound form of the tests must satisfy and exits 1 otherwise:

  * no pause, or a pause of any length before any sibling call: 3 passed, every time
  * each broken ``_gather_phase``: 3 failed

Every run must execute exactly three cases; anything else is reported as BROKEN
(exit 2) rather than counted as a pass.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

VERIFY = Path(__file__).resolve().parent
BACKEND = VERIFY.parents[3] / "backend"
REPO_TESTS = [
    "tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return",
    "tests/test_novel_r5_deliberation.py::test_all_advisor_calls_are_cancelled_and_drained_if_one_fails",
]
# (label, stall, mutation, repetitions, cases expected to pass)
CONDITIONS = [
    ("no pause", "", "", 3, 3),
    ("pause 0.2 ms before twist_designer", "twist_designer:0.0002", "", 5, 3),
    ("pause 2 ms before twist_designer", "twist_designer:0.002", "", 3, 3),
    ("pause 20 ms before twist_designer", "twist_designer:0.02", "", 3, 3),
    ("pause 2 ms before character_advocate", "character_advocate:0.002", "", 3, 3),
    ("pause 20 ms before character_advocate", "character_advocate:0.02", "", 3, 3),
    ("pause 2 ms before plot_architect", "plot_architect:0.002", "", 3, 3),
    ("broken: cancels but does not wait", "", "no_drain", 1, 0),
    ("broken: plain gather", "", "plain_gather", 1, 0),
    ("broken: runs the calls one by one", "", "sequential", 1, 0),
    ("broken: waits but does not cancel", "", "no_cancel", 1, 0),
]


def run_once(which, stall, mutation, records):
    if which == "repo":
        arguments, extra_path = REPO_TESTS, []
    else:
        arguments = [str(VERIFY / "candidate_parallel_phase.py"), "-k", "not still_inside_router"]
        extra_path = [str(BACKEND / "tests")]
    environment = dict(os.environ, FLAKE_PROBE_OUT=records, FLAKE_PROBE_STALL=stall,
                       FLAKE_PROBE_MUTATION=mutation,
                       PYTHONPATH=os.pathsep.join([str(VERIFY), *extra_path]))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "flake_probe", *arguments],
        cwd=BACKEND, env=environment, capture_output=True, text=True)
    summary = [line for line in result.stdout.splitlines() if re.search(r" in [0-9.]+s", line)]
    line = summary[-1] if summary else ""
    count = lambda word: int(match.group(1)) if (match := re.search(rf"(\d+) {word}", line)) else 0
    return count("passed"), count("failed"), count("error")


def main():
    arguments = [argument for argument in sys.argv[1:] if argument != "--record"]
    record_only = "--record" in sys.argv[1:]
    which = arguments[0] if arguments else "repo"
    if which not in ("repo", "candidate"):
        raise SystemExit(__doc__)
    unmet = broken = 0
    with tempfile.TemporaryDirectory(prefix="flake-probe-") as records:
        print(f"form: {which}")
        for label, stall, mutation, repetitions, expected in CONDITIONS:
            cells = []
            for _ in range(repetitions):
                passed, failed, errors = run_once(which, stall, mutation, records)
                if passed + failed != 3 or errors:
                    broken += 1
                    cells.append(f"BROKEN({passed}p/{failed}f/{errors}e)")
                    continue
                cells.append(f"{passed} passed" if not failed else
                             f"{failed} failed" if not passed else f"{passed} passed, {failed} failed")
                unmet += passed != expected
            print(f"  {label:<40} | {' | '.join(cells)}")
    if broken:
        print(f"VERDICT: BROKEN ({broken} runs did not execute exactly three cases)")
        return 2
    if record_only:
        print("VERDICT: RECORDED")
        return 0
    print("VERDICT: SOUND" if not unmet else f"VERDICT: NOT_SOUND ({unmet} runs differ from what a sound form must do)")
    return 1 if unmet else 0


if __name__ == "__main__":
    sys.exit(main())
