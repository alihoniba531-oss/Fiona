"""Evaluation scoring and captured-log checks, with no provider calls."""

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from scripts import eval_crisis_model as evaluation


@pytest.mark.parametrize(
    ("expected", "accepted"),
    [
        ("high", {"high"}),
        ("at_least_possible", {"possible", "high"}),
        ("none", {"none"}),
        ("not_high", {"none", "possible"}),
    ],
)
@pytest.mark.parametrize("level", [None, "none", "possible", "high", "invalid"])
def test_meets_expected(expected, accepted, level):
    assert evaluation.meets_expected(level, expected) == (level in accepted)


@pytest.mark.parametrize(
    ("levels", "expected", "worst"),
    [
        (("high", "possible", "none"), "high", "none"),
        (("high", "possible"), "at_least_possible", "possible"),
        (("high", None), "high", None),
        (("possible", None), "at_least_possible", None),
        (("none", "possible"), "none", "possible"),
        (("none", "possible"), "not_high", "possible"),
        (("none", None, "high"), "none", "high"),
        (("none", None, "high"), "not_high", "high"),
        (("possible", None), "none", None),
        (("possible", None), "not_high", None),
        ((None, None), "none", None),
    ],
)
def test_worst_level(levels, expected, worst):
    assert evaluation.worst_level(levels, expected) == worst


def test_worst_level_requires_an_attempt():
    with pytest.raises(ValueError, match="empty levels"):
        evaluation.worst_level((), "none")


@pytest.mark.parametrize(
    ("latencies", "expected"),
    [
        ([8.0], 8.0),
        ([2.0, 1.0], 2.0),
        (list(range(10, 0, -1)), 9),
        (list(range(11, 0, -1)), 10),
    ],
)
def test_p90_nearest_rank_includes_timeouts(latencies, expected):
    original = list(latencies)
    assert evaluation.p90(latencies) == expected
    assert latencies == original


def test_p90_requires_a_sample():
    with pytest.raises(ValueError, match="empty latency sample"):
        evaluation.p90([])


def _result(text, rule="none", combined=("none",), expected="none", group="daily"):
    return evaluation.Result(
        evaluation.Case(group, group, text, expected), rule, combined, combined,
    )


def test_daily_statistics_counts_unique_sentences_and_retains_all_attempts(capsys):
    results = [
        _result("重复日常一句", combined=("none", "none")),
        _result("重复日常一句", combined=("possible", "high"), group="appendix"),
        _result("其他日常一句"),
        _result("规则本已高危", rule="high", combined=("high",)),
        _result("规则本已可能", rule="possible", combined=("possible",), expected="not_high"),
        _result("规则本已可能", rule="possible", combined=("possible",), group="appendix"),
        _result("危机句不入分母", combined=("high",), expected="high"),
    ]
    assert evaluation.daily_statistics(results) == {
        "count": 4,
        "rule_high": 1,
        "combined_high": 2,
        "added_high": 1,
        "rule_possible": 1,
        "rule_none": 2,
        "none_to_possible": 1,
        "none_to_possible_rate": 0.25,
        "none_to_possible_rule_none_rate": 0.5,
    }
    evaluation.report_daily(results)
    output = capsys.readouterr().out
    assert "daily count=4" in output
    assert "none_to_possible_rate=25.00%" in output
    assert output.count("daily rule=possible text=") == 1


def test_daily_statistics_handles_no_rule_none_and_no_daily_sentences():
    assert evaluation.daily_statistics([
        _result("规则可能日常句", rule="possible", combined=("possible",)),
    ])["none_to_possible_rule_none_rate"] == 0
    empty = evaluation.daily_statistics([
        _result("只含危机语料", combined=("high",), expected="high"),
    ])
    assert empty["count"] == 0
    assert empty["none_to_possible_rate"] == 0
    assert empty["none_to_possible_rule_none_rate"] == 0


def test_real_corpus_daily_denominator_is_48_unique_sentences():
    cases = evaluation.load_cases(evaluation.DEFAULT_CORPUS)
    results = [evaluation.Result(case, "none", ("none",), ("none",)) for case in cases]
    assert len([case for case in cases if case.expected in {"none", "not_high"}]) == 49
    assert evaluation.daily_statistics(results)["count"] == 48


def _stub_evaluation(monkeypatch, classify, rules):
    # Inject the whole classifier module so these tests cannot build a client.
    monkeypatch.setitem(sys.modules, "crisis_model", SimpleNamespace(classify=classify))
    import safety

    monkeypatch.setattr(safety, "assess_crisis", lambda text: rules.get(text))


def test_evaluate_skips_rule_high_and_counts_actual_stdout_stderr_logs(monkeypatch, capsys):
    cases = [
        evaluation.Case("risk", "risk", "规则确定高危", "high"),
        evaluation.Case("daily", "daily", "需要模型复核", "none"),
    ]
    calls = []

    async def classify(text):
        calls.append(text)
        if len(calls) == 1:
            print("[crisis-model] level=none ms=12.3")
            return "none"
        print("[crisis-model] failed type=TimeoutError ms=8000.0", file=sys.stderr)
        return None

    _stub_evaluation(monkeypatch, classify, {cases[0].text: "high"})
    asyncio.run(evaluation.evaluate(cases, 2))
    captured = capsys.readouterr()
    assert calls == [cases[1].text, cases[1].text]
    assert "sentences=2 repeats=2 calls=2 rule_high_skipped=1 failures=1" in captured.out
    assert "classifier_logs calls=2 level_lines=1 failed_lines=1 corpus_text_leaks=0" in captured.out
    assert "group=risk count=0 pass=0/0 rate=n/a rule_high_skipped=1" in captured.out
    assert "group=risk count=1 pass=1/1 rate=100.00% rule_high_skipped=1" in captured.out
    assert "rule=high model=skipped combined=high count=1" in captured.out
    assert "failure_type=TimeoutError count=1" in captured.out
    assert captured.err == ""


def test_evaluate_all_rule_high_has_no_model_or_latency_samples(monkeypatch, capsys):
    case = evaluation.Case("risk", "risk", "全部规则高危", "high")

    async def classify(text):
        pytest.fail("rule-high text must never call a classifier")

    _stub_evaluation(monkeypatch, classify, {case.text: "high"})
    asyncio.run(evaluation.evaluate([case], 3))
    output = capsys.readouterr().out
    assert "calls=0 rule_high_skipped=1 failures=0" in output
    assert "level_lines=0 failed_lines=0 corpus_text_leaks=0" in output
    assert "latency median_seconds=n/a p90_seconds=n/a failures=0/0" in output


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize(
    ("text", "fragment", "escaped", "leak_count"),
    [
        ("甲乙丙丁戊己庚辛壬癸", "丙丁戊己庚辛", False, 1),
        ("甲乙丙丁戊己庚辛壬癸", "丙丁戊己庚辛壬", False, 1),
        ("甲乙丙丁戊己庚辛壬癸", "丙丁戊己庚辛", True, 1),
        ("甲乙丙丁戊己庚辛壬癸", "丙丁戊己庚", False, 0),
        ("想消失", "想消失", False, 1),
        ("想消失", "想消", False, 0),
    ],
)
def test_evaluate_detects_partial_short_and_escaped_text_leaks(
    monkeypatch, capsys, stream, text, fragment, escaped, leak_count,
):
    case = evaluation.Case("daily", "daily", text, "none")

    async def classify(submitted):
        print("[crisis-model] level=none ms=1.0")
        leaked = json.dumps(fragment) if escaped else fragment
        print(leaked, file=sys.stdout if stream == "stdout" else sys.stderr)
        return "none"

    _stub_evaluation(monkeypatch, classify, {})
    asyncio.run(evaluation.evaluate([case], 1))
    captured = capsys.readouterr()
    assert f"corpus_text_leaks={leak_count}" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("log_lines", [0, 2])
def test_evaluate_rejects_missing_or_duplicate_classifier_logs(monkeypatch, capsys, log_lines):
    case = evaluation.Case("daily", "daily", "分类日志正控句", "none")

    async def classify(text):
        for _ in range(log_lines):
            print("[crisis-model] level=none ms=1.0")
        return "none"

    _stub_evaluation(monkeypatch, classify, {})
    with pytest.raises(AssertionError, match="classifier log count differs from calls"):
        asyncio.run(evaluation.evaluate([case], 1))
    output = capsys.readouterr().out
    assert f"classifier_logs calls=1 level_lines={log_lines} failed_lines=0" in output
