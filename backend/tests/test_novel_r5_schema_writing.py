"""Portable critique-plan validation, review recovery and title regressions."""

import asyncio
from copy import deepcopy

import pytest

from novel.bible import build_setup
from novel.fake_llm import FakeLLM
from novel.schemas import ValidationError, parse_json, validate_critique_plan, validate_review
from novel.writing import normalize_manuscript, write_chapter
from test_novel_schemas import config_data, decision_data, setup_data


BODY = "删除倒计时突然跳到六十秒，她按住仍在闪烁的屏幕。"


def critique_plan():
    return {"objections": [{"severity": "major", "target": "第二个节拍",
                            "problem": "人物缺乏打开封存记录的动机",
                            "suggestion": "先让她从旧照片发现母亲的签名"}],
            "keep": "保留门外脚步声造成的时间压力"}


@pytest.mark.parametrize("role", ["plot_architect", "character_advocate",
                                  "reader_advocate", "pacing_editor"])
@pytest.mark.parametrize("alternative", [None, "", "另一个替代走向"])
def test_non_twist_critique_allows_omitted_or_empty_alternative(role, alternative):
    data = critique_plan()
    if alternative is not None:
        data["alternative"] = alternative
    before = deepcopy(data)
    result = validate_critique_plan(data, role)
    assert result == before
    result["objections"][0]["problem"] = "改动副本"
    assert data == before


@pytest.mark.parametrize("alternative", [None, "", " \n ", [], 12])
def test_twist_critique_requires_nonempty_text_alternative(alternative):
    data = critique_plan()
    if alternative is not None:
        data["alternative"] = alternative
    with pytest.raises(ValidationError, match="alternative"):
        validate_critique_plan(data, "twist_designer")


@pytest.mark.parametrize("alternative", ["改从母亲的视角追查", "替" * 240])
def test_alternative_length_is_guidance_only(alternative):
    data = dict(critique_plan(), alternative=alternative)
    assert validate_critique_plan(data, "twist_designer")["alternative"] == alternative


@pytest.mark.parametrize("count", [1, 2, 3])
def test_critique_plan_accepts_one_to_three_actionable_objections(count):
    data = critique_plan()
    data["objections"] *= count
    data["objections"][-1]["severity"] = "minor"
    assert len(validate_critique_plan(data, "plot_architect")["objections"]) == count


@pytest.mark.parametrize("field,value", [
    ("severity", "critical"), ("severity", True),
    ("target", ""), ("target", None), ("target", []),
    ("problem", " \n"), ("problem", None), ("problem", False),
    ("suggestion", ""), ("suggestion", None), ("suggestion", {}),
])
def test_critique_objection_rejects_empty_or_invalid_fields(field, value):
    data = critique_plan()
    data["objections"][0][field] = value
    with pytest.raises(ValidationError):
        validate_critique_plan(data, "plot_architect")


@pytest.mark.parametrize("field", ["severity", "target", "problem", "suggestion"])
def test_critique_objection_requires_all_four_fields(field):
    data = critique_plan()
    del data["objections"][0][field]
    with pytest.raises(ValidationError, match=field):
        validate_critique_plan(data, "plot_architect")


@pytest.mark.parametrize("value", [[], [critique_plan()["objections"][0]] * 4,
                                  None, {}, "意见", [None]])
def test_critique_plan_objection_envelope_and_bounds(value):
    with pytest.raises(ValidationError):
        validate_critique_plan(dict(critique_plan(), objections=value), "plot_architect")


@pytest.mark.parametrize("value", ["", " \n", None, [], False])
def test_critique_plan_requires_nonempty_keep(value):
    with pytest.raises(ValidationError, match="keep"):
        validate_critique_plan(dict(critique_plan(), keep=value), "plot_architect")


def review_issue(**changes):
    return {"category": "continuity", "problem": "倒计时变化缺少原因",
            "evidence": "删除倒计时突然跳到六十秒", "fix": "补上触发倒计时的动作",
            "blocking": True, **changes}


@pytest.mark.parametrize("variant", ["missing", "null"])
def test_review_defaults_only_missing_or_null_blocking_to_nonblocking(variant):
    item = review_issue()
    if variant == "missing":
        del item["blocking"]
    else:
        item["blocking"] = None
    source = {"issues": [item]}
    before = deepcopy(source)
    result = validate_review(source, BODY)
    assert result == {"issues": [dict(item, blocking=False, blocking_defaulted=True)],
                      "dropped_issues": [], "passed": True}
    assert source == before


@pytest.mark.parametrize("field", ["category", "problem", "evidence", "fix"])
@pytest.mark.parametrize("blocking", [None, False])
def test_missing_other_review_fields_still_drops_issue(field, blocking):
    item = review_issue(blocking=blocking)
    del item[field]
    before = deepcopy(item)
    result = validate_review({"issues": [item]}, BODY)
    assert result == {"issues": [], "dropped_issues": [dict(item, drop_reason="字段不完整或类型错误")],
                      "passed": True}
    assert item == before


@pytest.mark.parametrize("blocking", ["false", "", 0, 1, [], {}])
def test_invalid_nonnull_blocking_is_not_defaulted(blocking):
    item = review_issue(blocking=blocking)
    result = validate_review({"issues": [item]}, BODY)
    assert result["issues"] == []
    assert result["dropped_issues"] == [dict(item, drop_reason="字段不完整或类型错误")]


def test_defaulted_review_still_requires_real_body_evidence():
    item = review_issue(evidence="根本不存在于正文的引文", blocking=None)
    result = validate_review({"issues": [item]}, BODY)
    assert result["issues"] == []
    assert result["dropped_issues"][0]["drop_reason"] == "证据少于 6 字或不是正文的逐字摘录"


def test_blocking_defaulted_marker_is_owned_by_validator():
    item = review_issue(blocking_defaulted=True)
    result = validate_review({"issues": [item]}, BODY)
    assert result["issues"] == [review_issue()]
    assert result["passed"] is False
    assert item["blocking_defaulted"] is True


class LocalRouter:
    def __init__(self, script):
        self.fake = FakeLLM(script)

    async def call(self, **request):
        raw, _usage = await self.fake(request)
        value = raw if request["output"] == "markdown" else parse_json(raw)
        return request["validator"](value)


def chapter_with_reviews(issues_for_round):
    config = config_data()
    config["target"]["chapter_words"] = 300
    config["experiment"] = "A"
    config["agents"] = {role: f"fake:{role}" for role in ("writer", "reviewer", "archivist")}
    compass, bible = build_setup(setup_data(), config)

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "review":
            return {"issues": issues_for_round(payload["review_round"])}

    router = LocalRouter(script)
    result = asyncio.run(write_chapter(router, config, compass, bible,
                                      {"decision": decision_data()}, chapter=1, arm="solo"))
    return result, router.fake


@pytest.mark.parametrize("items", [
    [{"category": "continuity", "problem": "残缺"}],
    [review_issue(evidence="这句话完全未写进正文")],
    [None, {"category": "continuity"}],
])
def test_all_review_issues_dropped_marks_chapter_degraded(items):
    result, fake = chapter_with_reviews(lambda _round: items)
    assert result["flags"] == ["review_degraded"]
    assert result["reviews"][0]["issues"] == []
    assert len(result["reviews"][0]["dropped_issues"]) == len(items)
    assert result["revision_rounds"] == 0
    assert sum(request["task"] == "archive" for request in fake.calls) == 1


@pytest.mark.parametrize("items", [[], [review_issue(blocking=None)],
                                  [review_issue(blocking=False), None]])
def test_empty_or_partly_retained_review_does_not_mark_degraded(items):
    result, _fake = chapter_with_reviews(lambda _round: items)
    assert result["flags"] == []
    assert result["revision_rounds"] == 0


def test_later_review_round_can_mark_chapter_degraded():
    result, _fake = chapter_with_reviews(
        lambda round_: [review_issue()] if round_ == 0 else [{"category": "continuity"}])
    assert result["review_rounds"] == 2
    assert result["revision_rounds"] == 1
    assert result["flags"] == ["review_degraded"]


@pytest.mark.parametrize("number,chapter", [("二", 2), ("十二", 12), ("二十", 20),
                                          ("二十一", 21), ("五十", 50), ("七十", 70),
                                          ("一百零二", 102), ("一〇二", 102), ("12", 12)])
def test_chinese_and_arabic_chapter_heading_is_canonical(number, chapter):
    body = f"# 第{number}章 同源的跳板\n\n正文一。\n正文二。"
    assert normalize_manuscript(body, chapter, "同源的跳板") == (
        f"# 第{chapter}章 同源的跳板\n\n正文一。\n正文二。")


@pytest.mark.parametrize("separator", ["\n", "\n\n", "\n  \n\t\n"])
def test_adjacent_duplicate_title_removes_only_that_one_line(separator):
    body = "# 第2章 X" + separator + "# 第二章 X\n  正文保持空格。\n# 第二章 X\n尾声。"
    expected = "# 第2章 X" + separator + "  正文保持空格。\n# 第二章 X\n尾声。"
    assert normalize_manuscript(body, 2, "X") == expected


@pytest.mark.parametrize("first", ["# 第二章 X", "## 第 2 章：X", "# 第2章 X"])
def test_wrong_chapter_heading_is_preserved_after_inserting_correct_heading(first):
    body = first + "\n\n正文保持。"
    assert normalize_manuscript(body, 3, "X") == "# 第3章 X\n" + body


@pytest.mark.parametrize("tail", ["# 第二章 其他标题\n正文。", "# 第三章 X\n正文。",
                                  "正文先出现。\n# 第二章 X", "第2章 X\n正文。"])
def test_nonduplicate_or_nonadjacent_heading_is_preserved(tail):
    body = "# 第2章 X\n\n" + tail
    assert normalize_manuscript(body, 2, "X") == body
