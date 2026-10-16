"""Review reports with unverifiable schema content cannot block a chapter."""

from copy import deepcopy

import pytest

from novel.schemas import ValidationError, parse_json, validate_review


BODY = "她的右手仍然缠着白色绷带。她独自站在机房门前。"
STRUCTURE_REASON = "字段不完整或类型错误"
EVIDENCE_REASON = "证据少于 6 字或不是正文的逐字摘录"


def issue(**changes):
    return {"category": "continuity", "problem": "右手状态与上一章冲突",
            "evidence": "她的右手仍然缠着白色绷带", "fix": "补足治疗经过",
            "blocking": True, **changes}


@pytest.mark.parametrize("field", ["category", "problem", "evidence", "fix", "blocking"])
def test_review_missing_issue_field_is_dropped_without_mutating_source(field):
    report = issue()
    del report[field]
    data = {"issues": [report], "passed": False}
    before = deepcopy(data)
    result = validate_review(data, BODY)
    if field == "blocking":
        assert result == {"issues": [dict(report, blocking=False, blocking_defaulted=True)],
                          "dropped_issues": [], "passed": True}
    else:
        assert result == {"issues": [], "dropped_issues": [dict(report, drop_reason=STRUCTURE_REASON)],
                          "passed": True}
    assert data == before


@pytest.mark.parametrize("field,value", [
    (field, value)
    for field in ("category", "problem", "evidence", "fix", "blocking")
    for value in ([], {}, 0, 1.5, True)
    if not (field == "blocking" and value is True)
] + [("category", None), ("evidence", None), ("blocking", None),
     ("blocking", "true"), ("blocking", "false"), ("blocking", "")])
def test_review_wrong_issue_field_type_is_dropped(field, value):
    report = issue(**{field: value})
    before = deepcopy(report)
    result = validate_review({"issues": [report]}, BODY)
    if field == "blocking" and value is None:
        assert result["issues"] == [dict(report, blocking=False, blocking_defaulted=True)]
        assert result["dropped_issues"] == []
    else:
        assert result["issues"] == []
        assert result["dropped_issues"] == [dict(report, drop_reason=STRUCTURE_REASON)]
    assert result["passed"] is True
    assert report == before


@pytest.mark.parametrize("category", ["", "unknown", "Continuity", "plot", "continuity "])
def test_review_invalid_issue_category_is_dropped(category):
    report = issue(category=category)
    result = validate_review({"issues": [report]}, BODY)
    assert result["passed"] is True
    assert result["issues"] == []
    assert result["dropped_issues"] == [dict(report, drop_reason=STRUCTURE_REASON)]


@pytest.mark.parametrize("report", [None, False, True, 0, 1.5, "问题", [], ["问题"]])
def test_review_nonobject_issue_has_explicit_diagnostic_wrapper(report):
    data = {"issues": [report]}
    before = deepcopy(data)
    result = validate_review(data, BODY)
    assert result == {"issues": [], "dropped_issues": [
        {"issue": report, "drop_reason": STRUCTURE_REASON}], "passed": True}
    assert data == before


@pytest.mark.parametrize("data", [
    None, False, 1, "review", [], [{"issues": []}], {},
    {"issues": None}, {"issues": {}}, {"issues": "[]"},
    {"issues": False}, {"issues": 1},
])
def test_review_invalid_top_structure_still_fails(data):
    before = deepcopy(data)
    with pytest.raises(ValidationError):
        validate_review(data, BODY)
    assert data == before


def test_review_real_run_shaped_incomplete_issue_parses_and_passes():
    # A minimal local fixture for the recorded early closing double quote:
    # JSON itself is valid, but the issue ends before evidence/fix/blocking.
    raw = '{"issues":[{"category":"continuity","problem":"圣经 age 锁定为 "    }]}'
    parsed = parse_json(raw)
    before = deepcopy(parsed)
    result = validate_review(parsed, BODY)
    assert result["issues"] == []
    assert result["passed"] is True
    assert result["dropped_issues"] == [dict(parsed["issues"][0], drop_reason=STRUCTURE_REASON)]
    assert parsed == before


@pytest.mark.parametrize("blocking", [True, False])
def test_review_mixed_issues_compute_passed_from_retained_items(blocking):
    kept = issue(blocking=blocking)
    incomplete = {"category": "continuity", "problem": "缺失证据"}
    data = {"issues": [incomplete, kept, None], "passed": blocking}
    before = deepcopy(data)
    result = validate_review(data, BODY)
    assert result["issues"] == [kept]
    assert result["passed"] is (not blocking)
    assert result["dropped_issues"] == [dict(incomplete, drop_reason=STRUCTURE_REASON),
                                        {"issue": None, "drop_reason": STRUCTURE_REASON}]
    assert data == before


@pytest.mark.parametrize("evidence", ["她的右手", "这句长长的证据完全没有出现在正文中"])
def test_review_valid_but_unverifiable_issue_keeps_original_drop_reason(evidence):
    report = issue(evidence=evidence)
    result = validate_review({"issues": [report]}, BODY)
    assert result["passed"] is True
    assert result["dropped_issues"] == [dict(report, drop_reason=EVIDENCE_REASON)]


@pytest.mark.parametrize("category", ["style", "adaptation"])
def test_review_style_and_adaptation_are_never_blocking_with_malformed_neighbor(category):
    report = issue(category=category)
    result = validate_review({"issues": [{"category": "continuity"}, report]}, BODY)
    assert result["passed"] is True
    assert result["issues"] == [dict(report, blocking=False)]
    assert result["dropped_issues"][0]["drop_reason"] == STRUCTURE_REASON
    assert report["blocking"] is True


@pytest.mark.parametrize("field", ["problem", "fix"])
def test_review_existing_optional_null_normalization_remains_valid(field):
    report = issue(**{field: None})
    result = validate_review({"issues": [report]}, BODY)
    assert result["issues"] == [dict(report, **{field: ""})]
    assert result["dropped_issues"] == []
    assert result["passed"] is False
    assert report[field] is None


def test_review_dropped_diagnostics_preserve_raw_fields_and_are_independent_copies():
    report = issue(problem=None, evidence=123, metadata={"nested": ["原值"]})
    data = {"issues": [report, ["原项"]]}
    before = deepcopy(data)
    result = validate_review(data, BODY)
    assert result["dropped_issues"][0] == dict(report, drop_reason=STRUCTURE_REASON)
    assert result["dropped_issues"][0]["problem"] is None
    result["dropped_issues"][0]["metadata"]["nested"].append("改动")
    result["dropped_issues"][1]["issue"].append("改动")
    assert data == before
