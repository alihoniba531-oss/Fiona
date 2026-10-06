"""Manual, real-model crisis evaluation; scoring tests use classifier stubs.

From backend/: python scripts/eval_crisis_model.py --limit 5 --repeats 1
Full run:       python scripts/eval_crisis_model.py
"""

import argparse
import asyncio
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = BACKEND_DIR / "tests" / "data" / "crisis_eval_corpus.json"
RANK = {"none": 0, "possible": 1, "high": 2}
EXPECTATIONS = {"high", "at_least_possible", "none", "not_high"}
LEVEL_LOG = re.compile(
    r"^\[crisis-model\] level=(?:high|possible|none) ms=\d+(?:\.\d+)?$", re.MULTILINE,
)
FAILURE_LOG = re.compile(
    r"^\[crisis-model\] failed type=([A-Za-z_][A-Za-z0-9_]*) ms=\d+(?:\.\d+)?$", re.MULTILINE,
)


@dataclass(frozen=True)
class Case:
    group: str
    label: str
    text: str
    expected: str


@dataclass(frozen=True)
class Result:
    case: Case
    rule: str
    models: tuple[str | None, ...]
    combined: tuple[str, ...]


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def load_cases(path: Path) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    seen_groups = set()
    for group in data["groups"]:
        group_id, label = group["id"], group["label"]
        if not isinstance(group_id, str) or not isinstance(label, str) or group_id in seen_groups:
            raise ValueError("invalid group")
        seen_groups.add(group_id)
        for item in group["items"]:
            text, expected = item["text"], item["expected"]
            if not isinstance(text, str) or not text.strip() or expected not in EXPECTATIONS:
                raise ValueError("invalid case")
            cases.append(Case(group_id, label, text, expected))
    if not cases:
        raise ValueError("empty corpus")
    return cases


def meets_expected(level: str | None, expected: str) -> bool:
    if level not in RANK:
        return False
    if expected == "high":
        return level == "high"
    if expected == "at_least_possible":
        return level in {"high", "possible"}
    if expected == "none":
        return level == "none"
    if expected == "not_high":
        return level != "high"
    raise ValueError("unknown expectation")


def worst_level(levels: tuple[str | None, ...], expected: str) -> str | None:
    """An unavailable model result fails its standalone evaluation.

    Online evaluation instead merges that attempt with the rule fallback.
    For everyday examples, a high result is worse than an unavailable one:
    the latter falls back to rules online, whereas high adds a false alarm.
    Otherwise, an unavailable result fails before ranking usable results.
    """
    if not levels:
        raise ValueError("empty levels")
    if expected in {"none", "not_high"} and "high" in levels:
        return "high"
    if None in levels:
        return None
    if expected in {"high", "at_least_possible"}:
        return min(levels, key=RANK.__getitem__)
    return max(levels, key=RANK.__getitem__)


def shown(level: str | None) -> str:
    return "unavailable" if level is None else level


def p90(elapsed: list[float]) -> float:
    """Nearest-rank 90th percentile, including timeout attempts."""
    if not elapsed:
        raise ValueError("empty latency sample")
    return sorted(elapsed)[math.ceil(len(elapsed) * 0.9) - 1]


def corpus_fragments(cases: list[Case]) -> set[str]:
    """Six-character windows detect every longer fragment; short texts use all.

    Include JSON-escaped forms so encoding a leaked sentence cannot hide it.
    """
    fragments = set()
    for case in cases:
        windows = (
            [case.text] if len(case.text) < 6
            else [case.text[start:start + 6] for start in range(len(case.text) - 5)]
        )
        for fragment in windows:
            fragments.add(fragment)
            fragments.add(json.dumps(fragment, ensure_ascii=True)[1:-1])
            fragments.add(json.dumps(fragment, ensure_ascii=False)[1:-1])
    return fragments


def unique_daily_results(results: list[Result]) -> list[Result]:
    """Keep all attempts for a sentence while counting that sentence once."""
    grouped = {}
    for result in results:
        if result.case.expected in {"none", "not_high"}:
            grouped.setdefault(result.case.text, []).append(result)
    return [
        Result(
            members[0].case,
            members[0].rule,
            tuple(level for member in members for level in member.models),
            tuple(level for member in members for level in member.combined),
        )
        for members in grouped.values()
    ]


def daily_statistics(results: list[Result]) -> dict[str, int | float]:
    daily = unique_daily_results(results)
    rule_high = sum(result.rule == "high" for result in daily)
    merged_high = sum("high" in result.combined for result in daily)
    rule_none = sum(result.rule == "none" for result in daily)
    upgrades = sum(result.rule == "none" and "possible" in result.combined for result in daily)
    return {
        "count": len(daily),
        "rule_high": rule_high,
        "combined_high": merged_high,
        "added_high": merged_high - rule_high,
        "rule_possible": sum(result.rule == "possible" for result in daily),
        "rule_none": rule_none,
        "none_to_possible": upgrades,
        "none_to_possible_rate": upgrades / len(daily) if daily else 0,
        "none_to_possible_rule_none_rate": upgrades / rule_none if rule_none else 0,
    }


def report_groups(results: list[Result], *, combined: bool) -> None:
    print("combined" if combined else "model", flush=True)
    groups = dict.fromkeys(result.case.group for result in results)
    for group in groups:
        members = [result for result in results if result.case.group == group]
        skipped = sum(result.rule == "high" for result in members)
        if not combined:
            members = [result for result in members if result.rule != "high"]
        levels = [
            worst_level(result.combined if combined else result.models, result.case.expected)
            for result in members
        ]
        passed = sum(meets_expected(level, result.case.expected) for result, level in zip(members, levels))
        counts = Counter(shown(level) for level in levels)
        rate = f"{passed / len(members):.2%}" if members else "n/a"
        print(
            f"group={group} count={len(members)} pass={passed}/{len(members)} "
            f"rate={rate} rule_high_skipped={skipped} "
            f"high={counts['high']} possible={counts['possible']} "
            f"none={counts['none']} unavailable={counts['unavailable']}",
            flush=True,
        )
        if any(result.case.expected in {"high", "at_least_possible"} for result in members):
            at_least = sum(level in {"high", "possible"} for level in levels)
            print(f"group={group} at_least_possible={at_least}/{len(members)}", flush=True)
        for result, level in zip(members, levels):
            if not meets_expected(level, result.case.expected):
                repeats = result.combined if combined else result.models
                print(
                    f"fail expected={result.case.expected} worst={shown(level)} "
                    f"rule={result.rule} repeats={','.join(shown(item) for item in repeats)} "
                    f"text={json.dumps(result.case.text, ensure_ascii=False)}",
                    flush=True,
                )


def report_daily(results: list[Result]) -> None:
    daily = unique_daily_results(results)
    if not daily:
        return
    stats = daily_statistics(results)
    print(
        f"daily count={stats['count']} rule_high={stats['rule_high']} "
        f"combined_high={stats['combined_high']} added_high={stats['added_high']} "
        f"rule_possible={stats['rule_possible']} rule_none={stats['rule_none']} "
        f"none_to_possible={stats['none_to_possible']} "
        f"none_to_possible_rate={stats['none_to_possible_rate']:.2%} "
        f"none_to_possible_rule_none_rate={stats['none_to_possible_rule_none_rate']:.2%}",
        flush=True,
    )
    for result in daily:
        if result.rule == "possible":
            print(f"daily rule=possible text={json.dumps(result.case.text, ensure_ascii=False)}", flush=True)


async def evaluate(cases: list[Case], repeats: int) -> None:
    # Import only after the caller has checked the key; imports never expose it.
    # Existing llm imports dotenv; this manual script uses the supplied env only.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    sys.path.insert(0, str(BACKEND_DIR))
    import crisis_model
    from safety import assess_crisis, combine_crisis_levels

    results = []
    elapsed = []
    failures = 0
    failure_types = Counter()
    log_text_leaks = 0
    level_log_lines = 0
    failed_log_lines = 0
    rule_high_skipped = 0
    fragments = corpus_fragments(cases)
    transitions = Counter()
    for case in cases:
        rule = assess_crisis(case.text)
        if rule == "high":
            rule_high_skipped += 1
            results.append(Result(case, rule, (), ("high",)))
            transitions[(rule, "skipped", rule)] += 1
            continue
        models, merged = [], []
        for _ in range(repeats):
            captured_stdout, captured_stderr = io.StringIO(), io.StringIO()
            started = time.perf_counter()
            with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
                model = await crisis_model.classify(case.text)
            elapsed.append(time.perf_counter() - started)
            # Keep classification logs separate from the required case report.
            # Print only the count so a faulty classifier cannot leak raw text.
            captured_logs = (captured_stdout.getvalue(), captured_stderr.getvalue())
            log_text_leaks += any(fragment in log for log in captured_logs for fragment in fragments)
            for captured_log in captured_logs:
                level_log_lines += len(LEVEL_LOG.findall(captured_log))
                captured_failures = FAILURE_LOG.findall(captured_log)
                failed_log_lines += len(captured_failures)
                failure_types.update(captured_failures)
            failures += model is None
            combined = combine_crisis_levels(rule, model) or "none"
            models.append(model)
            merged.append(combined)
            transitions[(rule or "none", shown(model), combined)] += 1
        results.append(Result(case, rule or "none", tuple(models), tuple(merged)))

    print(
        f"sentences={len(cases)} repeats={repeats} calls={len(elapsed)} "
        f"rule_high_skipped={rule_high_skipped} failures={failures}", flush=True,
    )
    print(
        f"classifier_logs calls={len(elapsed)} level_lines={level_log_lines} "
        f"failed_lines={failed_log_lines} corpus_text_leaks={log_text_leaks}", flush=True,
    )
    assert level_log_lines + failed_log_lines == len(elapsed), "classifier log count differs from calls"
    report_groups(results, combined=False)
    report_groups(results, combined=True)
    report_daily(results)
    print("rule+model->combined", flush=True)
    for (rule, model, combined), count in sorted(transitions.items()):
        print(f"rule={rule} model={model} combined={combined} count={count}", flush=True)
    for failure_type, count in sorted(failure_types.items()):
        print(f"failure_type={failure_type} count={count}", flush=True)
    if elapsed:
        print(
            f"latency median_seconds={statistics.median(elapsed):.3f} "
            f"p90_seconds={p90(elapsed):.3f} failures={failures}/{len(elapsed)}",
            flush=True,
        )
    else:
        print("latency median_seconds=n/a p90_seconds=n/a failures=0/0", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--repeats", type=positive_int, default=3)
    parser.add_argument("--group", action="append", help="select a group ID; may be repeated")
    parser.add_argument("--limit", type=positive_int, help="maximum number of sentences after group filtering")
    args = parser.parse_args()
    if not os.getenv("DASHSCOPE_API_KEY", "").strip():
        print("DASHSCOPE_API_KEY missing", file=sys.stderr)
        return 2
    if os.getenv("FIONA_CRISIS_MODEL_ENABLED") == "0":
        print("FIONA_CRISIS_MODEL_ENABLED=0", file=sys.stderr)
        return 2
    try:
        cases = load_cases(args.corpus)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"corpus failed type={type(error).__name__}", file=sys.stderr)
        return 2
    if args.group:
        unknown = set(args.group) - {case.group for case in cases}
        if unknown:
            parser.error("unknown group")
        cases = [case for case in cases if case.group in args.group]
    if args.limit:
        cases = cases[:args.limit]
    asyncio.run(evaluate(cases, args.repeats))
    # Completion is successful even when scores miss targets; scores are printed.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
