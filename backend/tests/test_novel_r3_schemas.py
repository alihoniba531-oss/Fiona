"""R3: stale decision resolutions are normalized without weakening guards."""

from copy import deepcopy

import pytest

from novel.bible import build_setup
from novel.schemas import ValidationError, validate_decision
from test_novel_schemas import config_data, decision_data, setup_data


@pytest.fixture
def story():
    compass, bible = build_setup(setup_data(), config_data())
    bible["dynamic"]["foreshadowing"].append({
        "id": "F002", "description": "已解释的旧线索", "importance": "major",
        "status": "resolved", "planted_chapter": 1, "resolved_chapter": 6,
    })
    bible["dynamic"]["foreshadowing"].append({
        "id": "F003", "description": "仍待回收的次要线索", "importance": "minor",
        "status": "open", "planted_chapter": 2,
    })
    return compass, bible


def decision(data, story):
    compass, bible = story
    return validate_decision(data, compass=compass, bible=bible, chapter=12,
                             mode="final" if data["ending_status"] == "end" else "normal",
                             proposal_ids=["P1"], objection_ids=[], note_ids=[])


def warning(key, reason):
    return {"field": "beat_sheet.foreshadowing_resolve", "id": key, "reason": reason}


def test_prunes_resolved_and_unknown_preserves_open_and_inputs(story):
    data = decision_data()
    data["ending_status"] = "end"
    data["beat_sheet"]["foreshadowing_resolve"] = ["F002", "F001", "F999"]
    data["warnings"] = [{"field": "pretend", "id": "forged", "reason": "模型声明"}]
    original_data, original_story = deepcopy(data), deepcopy(story)

    result = decision(data, story)

    assert result["beat_sheet"]["foreshadowing_resolve"] == ["F001"]
    assert result["warnings"] == [warning("F002", "已回收"), warning("F999", "不存在")]
    assert data == original_data
    assert story == original_story


def test_valid_open_resolutions_keep_order_and_have_no_model_warnings(story):
    data = decision_data()
    data["beat_sheet"]["foreshadowing_resolve"] = ["F003", "F001"]
    data["warnings"] = "模型不能提供警告"

    result = decision(data, story)

    assert result["beat_sheet"]["foreshadowing_resolve"] == ["F003", "F001"]
    assert result["warnings"] == []


def test_end_still_rejects_open_major_after_pruning(story):
    data = decision_data()
    data["ending_status"] = "end"
    data["beat_sheet"]["foreshadowing_resolve"] = ["F002", "F999"]
    original = deepcopy(data)

    with pytest.raises(ValidationError, match="每条未回收的主要伏笔"):
        decision(data, story)

    assert data == original


def test_end_accepts_explicit_open_major_handling_after_pruning(story):
    data = decision_data()
    data["ending_status"] = "end"
    data["beat_sheet"]["foreshadowing_resolve"] = ["F002", "F999"]
    data["unresolved_major_handling"] = [
        {"id": "F001", "decision": "leave_open", "reason": "保留给读者解释"}]

    result = decision(data, story)

    assert result["beat_sheet"]["foreshadowing_resolve"] == []
    assert result["warnings"] == [warning("F002", "已回收"), warning("F999", "不存在")]
    assert result["unresolved_major_handling"] == data["unresolved_major_handling"]


@pytest.mark.parametrize("key", ["F001", "F002", "F999"])
def test_duplicate_resolution_ids_remain_errors_for_every_status(story, key):
    data = decision_data()
    data["beat_sheet"]["foreshadowing_resolve"] = [key, key]

    with pytest.raises(ValidationError, match="foreshadowing_resolve.*ID 不得重复"):
        decision(data, story)


@pytest.mark.parametrize("value", [None, {}, "F001", [None], [{}], [False], [0], [""], [" \n"]])
def test_malformed_resolution_fields_remain_typed_errors(story, value):
    data = decision_data()
    data["beat_sheet"]["foreshadowing_resolve"] = value

    with pytest.raises(ValidationError, match="foreshadowing_resolve"):
        decision(data, story)


@pytest.mark.parametrize("key", ["F002", "F999"])
def test_unresolved_major_handling_still_rejects_resolved_and_unknown(story, key):
    data = decision_data()
    data["unresolved_major_handling"] = [
        {"id": key, "decision": "leave_open", "reason": "承诺必须引用有效伏笔"}]

    with pytest.raises(ValidationError, match="必须引用尚未回收的伏笔 ID"):
        decision(data, story)


@pytest.mark.parametrize("handling", [
    [{"id": "F001", "decision": "leave_open", "reason": ""}],
    [{"id": "F001", "decision": "resolve", "reason": "不能更换承诺枚举"}],
    [{"id": "F001", "decision": "leave_open", "reason": "保留疑问"}] * 2,
])
def test_unresolved_major_handling_keeps_reason_enum_and_duplicate_guards(story, handling):
    data = decision_data()
    data["unresolved_major_handling"] = handling

    with pytest.raises(ValidationError, match="unresolved_major_handling"):
        decision(data, story)
