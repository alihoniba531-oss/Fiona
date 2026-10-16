"""Offline schema regressions: each invalid model field stays a typed error."""

from copy import deepcopy
import json

import pytest

from novel.bible import build_setup
from novel.schemas import (
    ValidationError, parse_json, validate_archive, validate_critique,
    validate_decision, validate_insertions, validate_proposals, validate_review,
    validate_setup,
)


def setup_data():
    return {
        "title": "失落的影像", "logline": "技术员追查一段未来的影像", "theme": "记忆与责任",
        "core_conflict": "删除证据还是揭开真相",
        "protagonist": {"name": "林知", "want": "完成委托", "need": "承担责任"},
        "candidate_endings": [{"summary": "公开证据"}, {"summary": "留下关键证人"}],
        "main_threads": [{"name": "委托真相", "description": "追查委托人的身份"}],
        "characters": [{"name": "林知", "role": "main", "age": "二十五岁",
                        "appearance": "身高一米六八，黑色齐肩短发，左眉一道浅疤，常穿灰色风衣并佩戴银色手表。",
                        "personality": "谨慎", "motivation": "追查真相",
                        "initial_state": {"location": "机房", "condition": "右手受伤", "knows": ["委托有假"]}}],
        "world_rules": ["删除无法逆转"],
        "style_guide": {"pov": "第三人称", "tense": "过去时", "voice": "短句悬疑",
                        "banned_phrases": ["命运齿轮", "一抹", "不禁", "宛如", "悄然"]},
        "initial_foreshadowing": [{"description": "银表停在三点", "importance": "major"}],
    }


def config_data():
    return {"target": {"min_chapters": 8, "max_chapters": 12, "chapter_words": 1500},
            "adaptation": {"max_main_characters": 1, "max_scenes_per_chapter": 3}}


def decision_data():
    return {
        "chosen_proposal_ids": ["P1"], "merge_note": "沿证据追查", "objection_responses": [],
        "user_note_responses": [], "rationale": "动机与因果能够衔接",
        "beat_sheet": {"title": "第二份委托", "chapter_goal": "找到联系人", "advances_threads": ["T1"],
                       "characters": ["C1"], "scenes": [{"location": "机房", "summary": "收到消息"}],
                       "beats": ["收到证据", "检验消息", "决定赴约"], "opening_hook": "陌生号码来电",
                       "ending_hook": "门外有人", "foreshadowing_plant": [], "foreshadowing_resolve": []},
        "ending_status": "continue", "closing_chapters_left": 0, "unresolved_major_handling": [],
    }


def archive_data():
    return {"summary": "林知发现了第二份委托，决定追查联系人。", "character_state_changes": [],
            "timeline_add": [], "foreshadowing_planted": [], "foreshadowing_resolved": [],
            "used_beats_add": [], "new_characters": [],
            "deviation_from_beat_sheet": {"deviated": False, "note": ""}, "locked_conflicts": []}


@pytest.fixture
def story():
    return build_setup(setup_data(), config_data())


@pytest.mark.parametrize("wrapper", [lambda text: text, lambda text: "```json\n" + text + "\n```",
                                     lambda text: "下面是结果：\n" + text + "\n以上。"])
def test_json_extracts_fences_and_surrounding_text(wrapper):
    assert parse_json(wrapper(json.dumps({"内容": "合法"}, ensure_ascii=False))) == {"内容": "合法"}


@pytest.mark.parametrize("response", ["坏 JSON", "{坏}", '{"a":NaN}', '{"a":1,"a":2}',
                                      '[{"a":1}]', '```json\n[{"a":1}]\n```', None])
def test_json_errors_do_not_echo_response(response):
    with pytest.raises(ValidationError) as caught:
        parse_json(response)
    assert caught.value.errors
    assert "坏" not in str(caught.value)


@pytest.mark.parametrize("field,value", [
    ("title", False), ("candidate_endings", [{"summary": "一个结局"}]),
    ("main_threads", []), ("characters", []), ("world_rules", [3]),
    ("initial_foreshadowing", [{"description": "线索", "importance": "unknown"}]),
    ("protagonist", {"name": "主角", "want": [], "need": "责任"}),
])
def test_setup_invalid_fields(field, value):
    data = setup_data()
    data[field] = value
    with pytest.raises(ValidationError):
        validate_setup(data, config_data())


@pytest.mark.parametrize("change", ["appearance", "banned", "main_limit", "total_limit"])
def test_setup_bounds(change):
    data = setup_data()
    if change == "appearance":
        data["characters"][0]["appearance"] = "太短"
    elif change == "banned":
        data["style_guide"]["banned_phrases"] = ["一抹"]
    elif change == "main_limit":
        data["characters"] *= 2
    else:
        data["characters"] = [dict(deepcopy(data["characters"][0]), role="supporting") for _ in range(13)]
    with pytest.raises(ValidationError):
        validate_setup(data, config_data())


@pytest.mark.parametrize("field,value", [("advances_threads", []), ("advances_threads", ["T9"]),
                                        ("characters", ["C9"]), ("suggest_closing", 1),
                                        ("closing_reason", "")])
def test_proposal_references_and_closing_reason(story, field, value):
    compass, bible = story
    item = {"direction": "追查委托人", "advances_threads": ["T1"], "conflict": "收到威胁",
            "ending_hook": "门被推开", "characters": ["C1"], "risks": "过早暴露", "suggest_closing": True,
            "closing_reason": "主要线索已齐"}
    item[field] = value
    with pytest.raises(ValidationError):
        validate_proposals({"proposals": [item]}, compass, bible)


def critique_data():
    return {"scores": [{"proposal_id": "P2", "logic": 4, "character": 3, "appeal": 5,
                        "compass_fit": 4, "filmability": 3, "comment": "因果合理"}],
            "strongest_objection": {"proposal_id": "P2", "objection": "证据需要验证"}}


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "low", "high", "boolean", "objection", "object_id"])
def test_critique_exactly_once_and_scores(change):
    data = critique_data()
    if change == "missing":
        data["scores"] = []
    elif change == "duplicate":
        data["scores"] *= 2
    elif change == "unknown":
        data["scores"][0]["proposal_id"] = "P1"
    elif change == "objection":
        data["strongest_objection"]["proposal_id"] = "P1"
    elif change == "object_id":
        data["strongest_objection"]["proposal_id"] = []
    else:
        data["scores"][0]["appeal"] = {"low": 0, "high": 6, "boolean": True}[change]
    with pytest.raises(ValidationError):
        validate_critique(data, ["P2"])


def _decision(data, story, **kwargs):
    compass, bible = story
    args = dict(compass=compass, bible=bible, chapter=8, mode="normal", proposal_ids=["P1"],
                objection_ids=[], note_ids=[])
    args.update(kwargs)
    return validate_decision(data, **args)


@pytest.mark.parametrize("change", ["early_end", "final_continue", "missing_major", "unknown_resolution",
                                    "closing_zero", "closing_too_far", "boolean_left", "too_few_beats",
                                    "too_many_scenes", "unknown_character", "chosen", "solo_chosen"])
def test_decision_end_guards_and_fields(story, change):
    data = decision_data()
    kwargs = {}
    if change == "early_end":
        data["ending_status"] = "end"
        data["beat_sheet"]["foreshadowing_resolve"] = ["F001"]
        kwargs["chapter"] = 5
    elif change == "final_continue":
        kwargs.update(chapter=12, mode="final")
    elif change == "missing_major":
        data["ending_status"] = "end"
    elif change == "unknown_resolution":
        data["beat_sheet"]["foreshadowing_resolve"] = ["F999"]
    elif change.startswith("closing_"):
        data["ending_status"] = "closing"
        data["closing_chapters_left"] = 0 if change == "closing_zero" else 5
    elif change == "boolean_left":
        data["closing_chapters_left"] = True
    elif change == "too_few_beats":
        data["beat_sheet"]["beats"] = ["发现证据"]
    elif change == "too_many_scenes":
        data["beat_sheet"]["scenes"] *= 4
    elif change == "unknown_character":
        data["beat_sheet"]["characters"] = ["C9"]
    elif change == "chosen":
        data["chosen_proposal_ids"] = []
    elif change == "solo_chosen":
        kwargs["solo"] = True
    if change == "unknown_resolution":
        result = _decision(data, story, **kwargs)
        assert result["beat_sheet"]["foreshadowing_resolve"] == []
        assert result["warnings"] == [{
            "field": "beat_sheet.foreshadowing_resolve", "id": "F999", "reason": "不存在",
        }]
        return
    with pytest.raises(ValidationError):
        _decision(data, story, **kwargs)


@pytest.mark.parametrize("resolution", ["resolve", "leave_open"])
def test_end_accepts_resolved_or_reasoned_major(story, resolution):
    data = decision_data()
    data["ending_status"] = "end"
    if resolution == "resolve":
        data["beat_sheet"]["foreshadowing_resolve"] = ["F001"]
    else:
        data["unresolved_major_handling"] = [{"id": "F001", "decision": "leave_open", "reason": "留给读者理解"}]
    assert _decision(data, story)["ending_status"] == "end"


@pytest.mark.parametrize("kind", ["objection", "note"])
def test_missing_objection_or_user_note_response_rejected(story, kind):
    kwargs = {"objection_ids" if kind == "objection" else "note_ids": ["O1" if kind == "objection" else "N1"]}
    with pytest.raises(ValidationError):
        _decision(decision_data(), story, **kwargs)


def test_solo_decision_and_responses_are_valid(story):
    data = decision_data()
    data["chosen_proposal_ids"] = []
    data["objection_responses"] = [{"objection_id": "O1", "response": "补足证据"}]
    data["user_note_responses"] = [{"note_id": "N1", "adopted": False, "response": "下一章安排"}]
    assert _decision(data, story, solo=True, objection_ids=["O1"], note_ids=["N1"])["chosen_proposal_ids"] == []


@pytest.mark.parametrize("category", ["style", "adaptation", "continuity"])
def test_review_code_computes_blocking_and_conclusion(category):
    body = "她走进机房。\n她的右手仍然缠着绷带。"
    issue = {"category": category, "problem": "状态冲突", "evidence": "她的右手 仍然缠着绷带。", "fix": "补足解释", "blocking": True}
    output = validate_review({"issues": [issue], "passed": True, "conclusion": "通过"}, body)
    assert output["passed"] is (category != "continuity")
    assert output["issues"][0]["blocking"] is (category == "continuity")
    assert issue["blocking"] is True


@pytest.mark.parametrize("evidence", ["正文从来没有说过这一句话。", "她走进", " \n\t"])
def test_review_drops_nonexistent_and_short_evidence(evidence):
    issue = {"category": "character", "problem": "问题", "evidence": evidence, "fix": "修正", "blocking": True}
    output = validate_review({"issues": [issue], "passed": False}, "她走进机房。")
    assert output["passed"] is True
    assert output["issues"] == []
    assert len(output["dropped_issues"]) == 1


@pytest.mark.parametrize("change", ["missing_id", "resolved_twice", "unknown_character", "bad_relationship",
                                    "new_main", "three_new", "summary_long", "summary_empty", "wrong_type"])
def test_archive_references_and_new_characters(story, change):
    _, bible = story
    data = archive_data()
    new = {k: v for k, v in setup_data()["characters"][0].items() if k != "initial_state"}
    new["role"] = "supporting"
    if change == "missing_id":
        data["foreshadowing_resolved"] = [{"id": "F999", "note": "已解释"}]
    elif change == "resolved_twice":
        bible["dynamic"]["foreshadowing"][0]["status"] = "resolved"
        data["foreshadowing_resolved"] = [{"id": "F001", "note": "再次解释"}]
    elif change in ("unknown_character", "bad_relationship"):
        data["character_state_changes"] = [{"id": "C999" if change == "unknown_character" else "C1",
                                             "field": "relationships", "value": {"C999": "同伴"}}]
    elif change == "new_main":
        data["new_characters"] = [dict(new, role="main")]
    elif change == "three_new":
        data["new_characters"] = [new] * 3
    elif change == "summary_long":
        data["summary"] = "字" * 401
    elif change == "summary_empty":
        data["summary"] = " \n"
    else:
        data["deviation_from_beat_sheet"]["deviated"] = 1
    with pytest.raises(ValidationError):
        validate_archive(data, bible)


@pytest.mark.parametrize("body", ["缺少所有锚点", "甲锚。甲锚。乙锚。丙锚。"])
def test_insertions_require_unique_anchor(body):
    data = {"insertions": [{"after_anchor": anchor, "new_sentence": "矛盾句", "contradicts": "圣经原文"}
                           for anchor in ("甲锚。", "乙锚。", "丙锚。") ]}
    with pytest.raises(ValidationError):
        validate_insertions(data, body)


def test_insertions_reject_overlapping_anchor_occurrences():
    data = {"insertions": [{"after_anchor": anchor, "new_sentence": "矛盾句", "contradicts": "圣经原文"}
                           for anchor in ("哈哈哈", "乙锚。", "丙锚。") ]}
    with pytest.raises(ValidationError):
        validate_insertions(data, "哈哈哈哈乙锚。丙锚。")


@pytest.mark.parametrize("citations,valid", [
    (["圣经写明：删除无法逆转", "圣经写明：右手受伤", "圣经写明：银表停在三点"], True),
    (["与银表停在三点冲突", "与删除无法逆转冲突", "与机房冲突"], True),
    (["与删除无法逆转冲突", "与删除无法逆转冲突", "与删除无法逆转冲突"], False),
    (["引用不存在的圣经事实", "与右手受伤冲突", "与银表停在三点冲突"], False),
])
def test_insertions_quote_real_bible_facts_and_cover_three_categories(story, citations, valid):
    _, bible = story
    data = {"insertions": [{"after_anchor": anchor, "new_sentence": "她忽然发现原来的证据不成立。", "contradicts": citation}
                           for anchor, citation in zip(("甲锚。", "乙锚。", "丙锚。"), citations)]}
    body = "甲锚。乙锚。丙锚。"
    result = validate_insertions(data, body, bible)
    assert [item["contradicts"] for item in result["insertions"]] == citations
    # These original facts are shorter than eight characters: even the
    # originally "valid" quotations are recorded without rejecting the step.
    assert [item["citation_check"] for item in result["insertions"]] == [
        {"matched_categories": [], "minimum_shared_length": 8}] * 3


@pytest.mark.parametrize("field,value", [("after_anchor", []), ("new_sentence", {}), ("contradicts", False)])
def test_insertions_malformed_fields_raise_typed_error(story, field, value):
    _, bible = story
    data = {"insertions": [{"after_anchor": "甲锚。", "new_sentence": "新句。", "contradicts": "删除无法逆转"},
                            {"after_anchor": "乙锚。", "new_sentence": "新句。", "contradicts": "右手受伤"},
                            {"after_anchor": "丙锚。", "new_sentence": "新句。", "contradicts": "银表停在三点"}]}
    data["insertions"][0][field] = value
    with pytest.raises(ValidationError):
        validate_insertions(data, "甲锚。乙锚。丙锚。", bible)


@pytest.mark.parametrize("validator,kwargs", [(validate_setup, {"config": config_data()}),
                                              (validate_critique, {"proposal_ids": ["P1"]}),
                                              (validate_review, {"body": "正文"})])
def test_invalid_root_raises_validation_error(validator, kwargs):
    with pytest.raises(ValidationError):
        validator([], **kwargs)
