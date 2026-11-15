"""Sweep the collector's allocation counter at the start of the [critique] case
and report where the interpreter's own collection lands and whether the case fails.

No pause is injected. Each run is a fresh process; the only thing that varies is
how many allocations away the next automatic collection is when the test body
begins. With ``--generation keep`` nothing is collected beforehand, so the
collection is as long as it naturally is in that process.

Usage, from ``backend/``:

    .venv/bin/python ../docs/tasks/2026-11-15-novel-parallel-phase-flake/verify/gc_sweep.py \
        --whole-file --generation keep --start 1716 --stop 1762 --step 1 [--expect-sound]

Columns: counter at test start | outcome | "gap" when a collection began after
the first critique call's timer was scheduled and before the third one's was |
collections during the test as (start, length, generation), microseconds relative
to the first critique call being issued.

With ``--expect-sound`` the exit code is 0 only if no run failed and at least ten
runs had their collection inside the gap (otherwise the sweep proved nothing):
1 = some run failed, 2 = the gap was not exercised (move the range).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

VERIFY = Path(__file__).resolve().parent
BACKEND = VERIFY.parents[3] / "backend"
NAME = "test_failed_parallel_phase_cancels_and_drains_siblings_before_return[critique]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ballast", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, default=2000)
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--generation", default="0",
                        help="0 or 1 (collect first, short collection), or keep (move the counter only)")
    parser.add_argument("--whole-file", action="store_true",
                        help="run all of tests/test_novel_workflow.py so the target is preceded by its file-mates")
    parser.add_argument("--expect-sound", action="store_true")
    parser.add_argument("--candidate", action="store_true",
                        help="run the proposed form instead of the repository test")
    options = parser.parse_args()
    if options.candidate:
        target = f"{VERIFY / 'candidate_parallel_phase.py'}::{NAME}"
        python_path = [str(VERIFY), str(BACKEND / "tests")]
    else:
        target = "tests/test_novel_workflow.py" + ("" if options.whole_file else f"::{NAME}")
        python_path = [str(VERIFY)]
    failed = ran = in_gap = failed_in_gap = 0
    for count in range(options.start, options.stop, options.step):
        with tempfile.TemporaryDirectory(prefix="flake-probe-") as records:
            environment = dict(os.environ, FLAKE_PROBE_OUT=records,
                               FLAKE_PROBE_GC_COUNT=f"{count}:{options.generation}",
                               FLAKE_PROBE_BALLAST=str(options.ballast),
                               FLAKE_PROBE_TARGETS="siblings_before_return[critique]",
                               PYTHONPATH=os.pathsep.join(python_path))
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "-p", "flake_probe", target],
                           cwd=BACKEND, env=environment, capture_output=True, text=True)
            files = sorted(Path(records).glob("*.json"))
            if len(files) != 1:
                print(f"{count:>5} | BROKEN: expected one record, found {len(files)}")
                continue
            record = json.loads(files[0].read_text())
        events = record["events"]
        issued = [t for t, kind, step in events if kind == "router_enter" and "-critique-" in step]
        origin = issued[0] if issued else 0.0
        # The three 1 ms router timers of the critique phase: first three scheduled after it starts.
        timers = [t for t, kind, _ in events if kind == "call_at" and t >= origin][:3]
        pauses, begun, gap = [], None, False
        for t, kind, generation in events:
            if kind == "gc_start":
                begun = t
            elif kind == "gc_stop" and begun is not None:
                pauses.append((round((begun - origin) * 1e6), round((t - begun) * 1e6), generation))
                gap = gap or (len(timers) == 3 and timers[0] < begun < timers[2])
        ran += 1
        failed += record["outcome"] == "failed"
        in_gap += gap
        failed_in_gap += gap and record["outcome"] == "failed"
        print(f"{record['gc_count_set'][0]:>5} | {record['outcome']:<6} | {'gap' if gap else '   '} | {pauses}",
              flush=True)
    print(f"runs: {ran}, failed: {failed}; collection inside the gap: {in_gap}, of which failed: {failed_in_gap}; "
          f"tracked objects at test start: {record['tracked_objects_before']}")
    if options.expect_sound:
        return 1 if failed else 2 if in_gap < 10 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
