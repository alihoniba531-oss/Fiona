"""Offline validation of separate alternative decisions and legacy A replies."""

from copy import deepcopy

import pytest

from novel.schemas import ValidationError, validate_decision


PRIVATE = "PRIVATE_ALTERNATIVE_RESPONSE_CONTENT_SENTINEL"


def _objection(identifier):
    return {"objection_id": identifier, "response": PRIVATE}


def _alternative(identifier, decision="partial"):
    return {"alternative_id": identifier, "decision": decision, "response": PRIVATE}


def _decision():
    return {
        "chosen_proposal_ids": [], "merge_note": "保留核对记录的主线", "objection_responses": [],
        "user_note_responses": [], "rationale": "先验证证据，再决定是否公开",
        "beat_sheet": {
            "title": "旧记录", "chapter_goal": "确认保管人的身份", "advances_threads": ["T1"],
            "characters": ["C1"], "scenes": [{"location": "资料室", "summary": "核对签名和交接日期"}],
            "beats": ["收到原件", "核对交接签名", "决定追查保管人"],
            "opening_hook": "封条被换过", "ending_hook": "签名来自失踪的人",
            "foreshadowing_plant": [], "foreshadowing_resolve": [],
        },
        "ending_status": "continue", "closing_chapters_left": 0, "unresolved_major_handling": [],
    }


def _validate(data, *, objection_ids=("O1",), alternative_ids=("A1",), note_ids=()):
    return validate_decision(
        data, compass={"main_threads": [{"id": "T1"}], "target": {"min_chapters": 2, "max_chapters": 4}},
        bible={"locked": {"characters": [{"id": "C1"}], "adaptation": {"max_scenes_per_chapter": 3}},
               "dynamic": {"foreshadowing": []}},
        chapter=1, mode="normal", proposal_ids=(), objection_ids=objection_ids,
        note_ids=note_ids, solo=True, alternative_ids=alternative_ids,
    )


def _valid():
    data = _decision()
    data["objection_responses"] = [_objection("O1")]
    data["alternative_responses"] = [_alternative("A1")]
    return data


def _errors(data, **kwargs):
    before = deepcopy(data)
    with pytest.raises(ValidationError) as caught:
        _validate(data, **kwargs)
    assert data == before
    assert PRIVATE not in str(caught.value)
    return caught.value.errors


def test_smoke_shape_nine_objections_plus_three_separate_alternatives_passes():
    data = _decision()
    # Match the smoke response's shape: all O replies in the old field, then
    # the missing A1-A3 supplied as separate decisions, without rewriting O.
    data["objection_responses"] = [
        {"objection_id": f"O{index}", "response": f"第{index}条意见通过补充交接凭证和人物选择回应。"}
        for index in range(1, 10)
    ]
    original_objections = deepcopy(data["objection_responses"])
    errors = _errors(data, objection_ids=[f"O{index}" for index in range(1, 10)],
                     alternative_ids=["A1", "A2", "A3"])
    assert "decision.objection_responses：缺少：A1、A2、A3" in errors
    assert data["objection_responses"] == original_objections
    data["alternative_responses"] = [
        {"alternative_id": "A1", "decision": "adopt", "response": "采纳先核对封条的走向，让主角主动取得证据。"},
        {"alternative_id": "A2", "decision": "partial", "response": "保留保管人说谎的悬念，本章先不揭露动机。"},
        {"alternative_id": "A3", "decision": "reject", "response": "不采纳直接公开记录，现有材料尚不足以支持主角承担风险。"},
    ]
    before = deepcopy(data)
    result = _validate(data, objection_ids=[f"O{index}" for index in range(1, 10)],
                       alternative_ids=["A1", "A2", "A3"])
    assert result["objection_responses"] == original_objections == before["objection_responses"]
    assert result["alternative_responses"] == before["alternative_responses"]
    assert data == before


@pytest.mark.parametrize("legacy_argument", [False, True])
def test_legacy_a_replies_pass_without_forcing_new_output_field(legacy_argument):
    data = _decision()
    data["objection_responses"] = [_objection(key) for key in ("O1", "A1", "A2")]
    kwargs = ({"objection_ids": ["O1", "A1", "A2"], "alternative_ids": ()} if legacy_argument else
              {"objection_ids": ["O1"], "alternative_ids": ["A1", "A2"]})
    result = _validate(data, **kwargs)
    assert result["objection_responses"] == data["objection_responses"]
    assert "alternative_responses" not in result


@pytest.mark.parametrize("legacy_argument", [False, True])
@pytest.mark.parametrize("old_a_ids", [(), ("A1",), ("A1", "A2", "A3")])
def test_each_a_can_be_answered_once_in_either_field(legacy_argument, old_a_ids):
    data = _decision()
    all_a = ["A1", "A2", "A3"]
    data["objection_responses"] = [_objection(key) for key in ("O1", *old_a_ids)]
    data["alternative_responses"] = [_alternative(key) for key in all_a if key not in old_a_ids]
    kwargs = ({"objection_ids": ["O1", *all_a], "alternative_ids": ()} if legacy_argument else
              {"objection_ids": ["O1"], "alternative_ids": all_a})
    result = _validate(data, **kwargs)
    assert result["objection_responses"] == data["objection_responses"]
    assert result["alternative_responses"] == data["alternative_responses"]


def test_same_a_in_both_fields_reports_duplicate_id():
    data = _valid()
    data["objection_responses"].append(_objection("A1"))
    errors = _errors(data)
    assert errors[0] == "decision.objection_responses：本次下发的每条意见或留言必须恰好回应一次，不得出现其他 ID"
    assert "decision.objection_responses：重复：A1" in errors


@pytest.mark.parametrize("new_field", ["missing", "empty", "partial"])
def test_missing_a_diagnostics_name_exact_ids(new_field):
    data = _decision()
    data["objection_responses"] = [_objection("O1")]
    if new_field != "missing":
        data["alternative_responses"] = [] if new_field == "empty" else [_alternative("A1")]
    errors = _errors(data, alternative_ids=["A1", "A2", "A3"])
    missing = "A2、A3" if new_field == "partial" else "A1、A2、A3"
    assert "decision.objection_responses：缺少：" + missing in errors


@pytest.mark.parametrize("field", ["objection_responses", "alternative_responses"])
def test_unknown_a_is_named_in_its_actual_field(field):
    data = _valid()
    data[field].append(_objection("A9") if field == "objection_responses" else _alternative("A9"))
    assert "decision." + field + "：多出：A9" in _errors(data)


def test_repeated_a_within_new_field_reports_duplicate():
    data = _valid()
    data["alternative_responses"].append(_alternative("A1"))
    errors = _errors(data)
    assert "decision.objection_responses：重复：A1" in errors
    assert "decision.alternative_responses：重复：A1" in errors


def test_o_reply_cannot_move_to_alternative_field():
    data = _valid()
    data["objection_responses"] = []
    data["alternative_responses"].append(_alternative("O1"))
    errors = _errors(data)
    assert "decision.objection_responses：缺少：O1" in errors
    assert "decision.alternative_responses：多出：O1" in errors


def test_mixed_cross_field_errors_still_classify_missing_extra_duplicate_ids():
    data = _decision()
    data["objection_responses"] = [_objection("O1"), _objection("O1")]
    data["alternative_responses"] = [_alternative(key) for key in ("O2", "A1", "A1", "A9")]
    errors = _errors(data, objection_ids=["O1", "O2"], alternative_ids=["A1", "A2"])
    assert "decision.objection_responses：缺少：O2、A2" in errors
    assert "decision.objection_responses：重复：O1、A1" in errors
    assert "decision.alternative_responses：多出：O2、A9" in errors
    assert "decision.alternative_responses：重复：A1" in errors


@pytest.mark.parametrize("present", [False, True])
def test_no_alternatives_allows_absent_or_empty_new_field(present):
    data = _decision()
    data["objection_responses"] = [_objection("O1")]
    if present:
        data["alternative_responses"] = []
    result = _validate(data, alternative_ids=())
    assert ("alternative_responses" in result) is present
    if present:
        assert result["alternative_responses"] == []


@pytest.mark.parametrize("field_value", [None, {}, "not a list", 7, True])
def test_new_field_must_be_a_list_even_when_no_a_is_expected(field_value):
    data = _decision()
    data["objection_responses"] = [_objection("O1")]
    data["alternative_responses"] = field_value
    assert "decision.alternative_responses：必须是列表" in _errors(data, alternative_ids=())


@pytest.mark.parametrize("item", [PRIVATE, None, [], 7])
def test_alternative_item_must_be_an_object_without_echoing_it(item):
    data = _valid()
    data["alternative_responses"] = [item]
    errors = _errors(data)
    assert "decision.alternative_responses[0]：必须是对象" in errors


@pytest.mark.parametrize("missing", ["alternative_id", "decision", "response"])
def test_each_alternative_requires_all_declared_fields(missing):
    data = _valid()
    del data["alternative_responses"][0][missing]
    assert "decision.alternative_responses[0]." + missing + "：缺少字段" in _errors(data)


@pytest.mark.parametrize("decision", ["accept", "", None, True, 1, [], {"text": PRIVATE}, PRIVATE])
def test_alternative_decision_is_an_explicit_enum_without_echoing_bad_value(decision):
    data = _valid()
    data["alternative_responses"][0]["decision"] = decision
    assert "decision.alternative_responses[0].decision：必须是允许的枚举值：adopt、partial、reject" in _errors(data)


@pytest.mark.parametrize("response", ["", " \n\t", None, [], {}, False])
def test_alternative_reason_must_be_nonempty_text(response):
    data = _valid()
    data["alternative_responses"][0]["response"] = response
    errors = _errors(data)
    assert any(error.startswith("decision.alternative_responses[0].response：") for error in errors)


@pytest.mark.parametrize("identifier", [PRIVATE, "A1\n" + PRIVATE, "A" + "9" * 200, {"id": PRIVATE}, [PRIVATE], None, True, 1])
def test_bad_alternative_id_remains_private_and_does_not_satisfy_required_a(identifier):
    data = _valid()
    data["alternative_responses"][0]["alternative_id"] = identifier
    errors = _errors(data)
    assert "decision.objection_responses：缺少：A1" in errors
    assert "A" + "9" * 200 not in "；".join(errors)


@pytest.mark.parametrize("change", ["unknown_character", "unknown_thread", "invalid_ending", "missing_note"])
def test_new_alternatives_do_not_weaken_other_decision_checks(change):
    data = _valid()
    kwargs = {}
    if change == "unknown_character":
        data["beat_sheet"]["characters"] = ["C9"]
    elif change == "unknown_thread":
        data["beat_sheet"]["advances_threads"] = ["T9"]
    elif change == "invalid_ending":
        data["ending_status"] = "unknown"
    else:
        kwargs["note_ids"] = ["N1"]
    assert _errors(data, **kwargs)


@pytest.mark.parametrize("identifier", ["A9", "A10"])
def test_unrequested_a_in_both_fields_is_also_reported_duplicate(identifier):
    data = _valid()
    data["objection_responses"].append(_objection(identifier))
    data["alternative_responses"].append(_alternative(identifier))
    errors = _errors(data)
    assert "decision.objection_responses：多出：" + identifier in errors
    assert "decision.objection_responses：重复：" + identifier in errors
    assert "decision.alternative_responses：多出：" + identifier in errors


def test_n_in_alternative_field_cannot_satisfy_required_user_note():
    data = _valid()
    data["alternative_responses"].append(_alternative("N1"))
    errors = _errors(data, note_ids=["N1"])
    assert "decision.alternative_responses：多出：N1" in errors
    assert "decision.user_note_responses：缺少：N1" in errors
