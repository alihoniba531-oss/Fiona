"""Round-one schema normalizations, citation observations and evidence rules."""

from copy import deepcopy

import pytest

from novel.bible import apply_archive, build_setup
from novel.schemas import (
    ValidationError, compact, validate_archive, validate_critique,
    validate_decision, validate_insertions, validate_proposals, validate_review,
    validate_setup,
)
from test_novel_schemas import archive_data, config_data, critique_data, decision_data, setup_data


def story_data():
    return build_setup(setup_data(), config_data())


def proposal_data():
    return {"proposals": [{"direction": "沿着委托追查", "advances_threads": ["T1"],
                           "conflict": "证据冲突", "ending_hook": "门外传来脚步",
                           "characters": ["C1"], "risks": "", "suggest_closing": False,
                           "closing_reason": ""}]}


def decide(data, compass, bible):
    return validate_decision(data, compass=compass, bible=bible, chapter=8,
                             mode="normal", proposal_ids=["P1"], objection_ids=[], note_ids=[])


@pytest.mark.parametrize("kind", ["setup", "new_character"])
@pytest.mark.parametrize("age", [0, 25, 120])
def test_integer_character_age_is_normalized_on_a_copy(kind, age):
    if kind == "setup":
        data = setup_data()
        data["characters"][0]["age"] = age
        before = deepcopy(data)
        result = validate_setup(data, config_data())
        characters = result["characters"]
    else:
        _, bible = story_data()
        data = archive_data()
        character = {key: value for key, value in setup_data()["characters"][0].items()
                     if key != "initial_state"}
        data["new_characters"] = [dict(character, role="supporting", age=age)]
        before = deepcopy(data)
        result = validate_archive(data, bible)
        characters = result["new_characters"]
    assert characters[0]["age"] == str(age)
    assert data == before


@pytest.mark.parametrize("age", [True, 25.5, [], {}])
def test_age_keeps_invalid_type_checks(age):
    data = setup_data()
    data["characters"][0]["age"] = age
    with pytest.raises(ValidationError):
        validate_setup(data, config_data())


@pytest.mark.parametrize("case", [
    "merge_note", "risks", "closing_reason", "conflict", "comment", "fix", "problem",
    "resolved_note", "deviation_note", "age", "personality", "motivation",
    "location", "condition", "new_appearance",
])
def test_optional_null_strings_are_normalized_without_mutating_source(case):
    compass, bible = story_data()
    if case == "merge_note":
        data = decision_data()
        target, key = data, case
        validate = lambda item: decide(item, compass, bible)
        read = lambda item: item[case]
    elif case in ("risks", "closing_reason", "conflict"):
        data = proposal_data()
        target, key = data["proposals"][0], case
        validate = lambda item: validate_proposals(item, compass, bible)
        read = lambda item: item["proposals"][0][case]
    elif case == "comment":
        data = critique_data()
        target, key = data["scores"][0], case
        validate = lambda item: validate_critique(item, ["P2"])
        read = lambda item: item["scores"][0][case]
    elif case in ("fix", "problem"):
        data = {"issues": [{"category": "continuity", "problem": "检查状态", "fix": "补足交代",
                             "evidence": "右手仍然缠着白色绷带", "blocking": True}]}
        target, key = data["issues"][0], case
        validate = lambda item: validate_review(item, "她的右手仍然缠着白色绷带。")
        read = lambda item: item["issues"][0][case]
    elif case in ("resolved_note", "deviation_note", "new_appearance"):
        data = archive_data()
        if case == "resolved_note":
            data["foreshadowing_resolved"] = [{"id": "F001", "note": None}]
            target, key = data["foreshadowing_resolved"][0], "note"
            read = lambda item: item["foreshadowing_resolved"][0]["note"]
        elif case == "deviation_note":
            target, key = data["deviation_from_beat_sheet"], "note"
            read = lambda item: item["deviation_from_beat_sheet"]["note"]
        else:
            character = {key: value for key, value in setup_data()["characters"][0].items()
                         if key != "initial_state"}
            data["new_characters"] = [dict(character, role="supporting")]
            target, key = data["new_characters"][0], "appearance"
            read = lambda item: item["new_characters"][0]["appearance"]
        validate = lambda item: validate_archive(item, bible)
    else:
        data = setup_data()
        character = data["characters"][0]
        target, key = (character["initial_state"] if case in ("location", "condition") else character), case
        validate = lambda item: validate_setup(item, config_data())
        read = lambda item: ((item["characters"][0]["initial_state"][case])
                             if case in ("location", "condition") else item["characters"][0][case])
    target[key] = None
    before = deepcopy(data)
    assert read(validate(data)) == ""
    assert data == before


@pytest.mark.parametrize("status", ["continue", "end"])
@pytest.mark.parametrize("variation", ["missing", "null"])
def test_nonclosing_missing_or_null_chapter_count_becomes_zero(status, variation):
    compass, bible = story_data()
    data = decision_data()
    data["ending_status"] = status
    data["beat_sheet"]["foreshadowing_resolve"] = ["F001"]
    if variation == "missing":
        del data["closing_chapters_left"]
    else:
        data["closing_chapters_left"] = None
    before = deepcopy(data)
    assert decide(data, compass, bible)["closing_chapters_left"] == 0
    assert data == before


@pytest.mark.parametrize("value", [None, True, "2"])
def test_closing_chapter_count_still_requires_an_integer(value):
    compass, bible = story_data()
    data = decision_data()
    data.update(ending_status="closing", closing_chapters_left=value)
    with pytest.raises(ValidationError):
        decide(data, compass, bible)


@pytest.mark.parametrize("value,added", [
    ("林知知道委托人已经离开", ["林知知道委托人已经离开"]),
    (["林知知道委托人已经离开", "林知知道银表属于证人"],
     ["林知知道委托人已经离开", "林知知道银表属于证人"]),
    ([], []),
])
def test_archive_knows_appends_individual_strings_and_preserves_inputs(value, added):
    _, bible = story_data()
    data = archive_data()
    data["character_state_changes"] = [{"id": "C1", "field": "knows", "value": value}]
    before_bible, before_data = deepcopy(bible), deepcopy(data)
    result = apply_archive(bible, data, 1, "新发现")
    assert result["dynamic"]["character_states"]["C1"]["knows"] == ["委托有假"] + added
    assert bible == before_bible
    assert data == before_data


@pytest.mark.parametrize("value", [[1], ["线索", None], {}, True])
def test_archive_knows_rejects_non_string_items(value):
    _, bible = story_data()
    data = archive_data()
    data["character_state_changes"] = [{"id": "C1", "field": "knows", "value": value}]
    with pytest.raises(ValidationError):
        validate_archive(data, bible)


def insertion_data():
    return {"insertions": [{"after_anchor": anchor, "new_sentence": "插入的矛盾句。",
                             "contradicts": "没有对应事实也只记录"}
                            for anchor in ("甲锚。", "乙锚。", "丙锚。")]}


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_insertions_still_require_exactly_three(count):
    data = insertion_data()
    data["insertions"] = (data["insertions"] * 2)[:count]
    with pytest.raises(ValidationError):
        validate_insertions(data, "甲锚。乙锚。丙锚。")


def test_insertions_require_three_distinct_anchors_even_if_each_occurs_once():
    data = insertion_data()
    data["insertions"][1]["after_anchor"] = "甲锚。"
    with pytest.raises(ValidationError, match="互不相同"):
        validate_insertions(data, "甲锚。乙锚。丙锚。")


@pytest.mark.parametrize("field", ["contradicts", "new_sentence"])
def test_empty_insertion_text_is_recorded_without_semantic_rejection(field):
    _, bible = story_data()
    data = insertion_data()
    data["insertions"][0][field] = ""
    result = validate_insertions(data, "甲锚。乙锚。丙锚。", bible)
    assert result["insertions"][0][field] == ""
    assert result["insertions"][0]["citation_check"]["matched_categories"] == []


@pytest.mark.parametrize("source,category", [
    ("world_rules", "锁定外形或设定"), ("appearance", "锁定外形或设定"),
    ("motivation", "锁定外形或设定"), ("location", "当前位置或伤病"),
    ("condition", "当前位置或伤病"), ("timeline", "时间线或伏笔"),
    ("foreshadowing", "时间线或伏笔"),
])
@pytest.mark.parametrize("length", [7, 8, 9])
def test_citation_records_eight_character_partial_matches_by_category(source, category, length):
    _, bible = story_data()
    fact = "零壹贰叁肆伍陆柒捌玖拾佰仟万亿兆"
    if source == "world_rules":
        bible["locked"][source] = [fact]
    elif source in ("appearance", "motivation"):
        bible["locked"]["characters"][0][source] = fact
    elif source in ("location", "condition"):
        bible["dynamic"]["character_states"]["C1"][source] = fact
    elif source == "timeline":
        bible["dynamic"][source] = [fact]
    else:
        bible["dynamic"][source][0]["description"] = fact
    data = insertion_data()
    data["insertions"][0]["contradicts"] = "只引用片段：" + fact[2:2 + length] + "。"
    before = deepcopy(data)
    result = validate_insertions(data, "甲锚。乙锚。丙锚。", bible)
    assert result["insertions"][0]["citation_check"] == {
        "matched_categories": [category] if length >= 8 else [], "minimum_shared_length": 8}
    assert result["insertions"][1]["citation_check"]["matched_categories"] == []
    assert data == before


@pytest.mark.parametrize("field", ["name", "age", "personality"])
def test_citation_excludes_nonfact_character_fields(field):
    _, bible = story_data()
    fact = "零壹贰叁肆伍陆柒捌玖拾佰"
    bible["locked"]["characters"][0][field] = fact
    data = insertion_data()
    data["insertions"][0]["contradicts"] = fact
    result = validate_insertions(data, "甲锚。乙锚。丙锚。", bible)
    assert result["insertions"][0]["citation_check"]["matched_categories"] == []


def test_citation_records_all_categories_without_requiring_three_category_coverage():
    _, bible = story_data()
    fact = "零壹贰叁肆伍陆柒捌玖拾佰"
    bible["locked"]["world_rules"] = [fact]
    bible["dynamic"]["timeline"] = [fact]
    data = insertion_data()
    for item in data["insertions"]:
        item["contradicts"] = fact
    result = validate_insertions(data, "甲锚。乙锚。丙锚。", bible)
    assert all(item["citation_check"]["matched_categories"] ==
               ["锁定外形或设定", "时间线或伏笔"] for item in result["insertions"])


@pytest.mark.parametrize("quotes", ["“”", "‘’", "「」", "『』", "\"\"", "''"])
@pytest.mark.parametrize("ellipsis", ["……", "…", "...", "......"])
def test_compact_normalizes_quotes_whitespace_and_ellipsis(quotes, ellipsis):
    assert compact(f" {quotes[0]}她停了一下{ellipsis}仍然推开门。{quotes[1]}\n") == "她停了一下…仍然推开门。"


@pytest.mark.parametrize("body_ellipsis,evidence_ellipsis", [("……", "..."), ("...", "…"), ("…", "……")])
def test_review_uses_identical_normalization_for_body_and_evidence(body_ellipsis, evidence_ellipsis):
    issue = {"category": "continuity", "problem": "核对事实", "fix": None, "blocking": True,
             "evidence": f"「她停了一下{evidence_ellipsis}仍然推开门」"}
    body = f'她低声说：“她停了一下{body_ellipsis}仍然推开门”。'
    before = deepcopy(issue)
    result = validate_review({"issues": [issue]}, body)
    assert len(result["issues"]) == 1
    assert result["issues"][0]["fix"] == ""
    assert result["passed"] is False
    assert issue == before


@pytest.mark.parametrize("seed", ["  用户的原文\n第二行。 ", "第1个想法：‘不要改写’……", ""])
def test_build_setup_preserves_original_seed_idea(seed):
    config = config_data()
    config["seed_idea"] = seed
    before = deepcopy(config)
    compass, _ = build_setup(setup_data(), config)
    assert compass["seed_idea"] == seed
    assert config == before


@pytest.mark.parametrize("kind", ["setup", "proposal", "critique", "decision", "review", "archive", "insertions"])
def test_every_validator_returns_an_independent_normalized_copy(kind):
    compass, bible = story_data()
    cases = {
        "setup": (setup_data, lambda item: validate_setup(item, config_data())),
        "proposal": (proposal_data, lambda item: validate_proposals(item, compass, bible)),
        "critique": (critique_data, lambda item: validate_critique(item, ["P2"])),
        "decision": (decision_data, lambda item: decide(item, compass, bible)),
        "review": (lambda: {"issues": []}, lambda item: validate_review(item, "正文")),
        "archive": (archive_data, lambda item: validate_archive(item, bible)),
        "insertions": (insertion_data, lambda item: validate_insertions(item, "甲锚。乙锚。丙锚。", bible)),
    }
    factory, validator = cases[kind]
    data = factory()
    data["unrecognized_extra"] = {"nested": ["原值"]}
    before = deepcopy(data)
    result = validator(data)
    if "unrecognized_extra" in result:
        result["unrecognized_extra"]["nested"].append("返回副本的改动")
    else:
        result["issues"].append({"test": "返回副本的改动"})
    assert data == before
