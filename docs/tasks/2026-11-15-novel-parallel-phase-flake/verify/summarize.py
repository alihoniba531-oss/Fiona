"""Print one line per flake_probe record. All times are microseconds, measured
from the moment the first of the three parallel calls enters the router.

  issued        when each role's call entered the router
  timer_due     when each role's 1 ms router timer falls due, relative to the first
  at_model      when each role reached the fake model (absent = never reached it)
  wake_late     how late the loop woke for the first timer
  gc            collector pauses from the first call being issued until 2 ms after
                the last call reached the model: (start, length, generation)
  gc_count      the collector's counters when the test body began

Usage: python summarize.py <record.json or directory> [...]
"""
import json
import sys
from pathlib import Path


def summarize(path):
    record = json.loads(Path(path).read_text())
    nodeid = record["nodeid"]
    marker = ("-critique-plan-" if "advisor_calls" in nodeid
              else "-critique-" if nodeid.endswith("[critique]") else "-proposal-")
    events = record["events"]
    issued = [(t, step) for t, kind, step in events if kind == "router_enter" and marker in (step or "")]
    at_model = [(t, step) for t, kind, step in events if kind == "fake_enter" and marker in (step or "")]
    name = nodeid.split("::")[-1]
    if not issued:
        return f"{name}: {record['outcome']}; no router events for the failing phase"
    first = issued[0][0]
    window_end = max((t for t, _ in at_model), default=first) + 0.002
    # The three 1 ms router timers are the first three timers scheduled in the phase.
    timers = [when for t, kind, when in events if kind == "call_at" and t >= first][:3]
    us = lambda seconds: round(seconds * 1e6)
    role = lambda step: step.rsplit("-", 1)[-1].removesuffix(".json")
    pauses, begun = [], None
    for t, kind, generation in events:
        if not kind.startswith("gc_") or not first <= t <= window_end:
            continue
        if kind == "gc_start":
            begun = t
        elif begun is not None:
            pauses.append((us(begun - first), us(t - begun), generation))
            begun = None
    return json.dumps({
        "test": name[-34:],
        "outcome": record["outcome"],
        "stall": record.get("stall") or None,
        "mutation": record.get("mutation") or None,
        "gc_count": record.get("gc_count_set") or record["gc_count_before"],
        "issued": {role(step): us(t - first) for t, step in issued},
        "timer_due": [us(when - timers[0]) for when in timers],
        "at_model": {role(step): us(t - first) for t, step in at_model},
        "wake_late": us(at_model[0][0] - timers[0]) if at_model and timers else None,
        "gc": pauses,
        "threads": len(record.get("threads", [])),
        "tracked_objects": record["tracked_objects_before"],
        "load1": round(record["loadavg"][0], 1),
        "loop": [name.rsplit(".", 1)[-1] for name in record["loop_types"]],
    }, ensure_ascii=False)


for argument in sys.argv[1:]:
    target = Path(argument)
    for path in (sorted(target.glob("*.json")) if target.is_dir() else [target]):
        print(summarize(path))
