"""Pure state transitions, stable identifiers, and context boundaries."""

from copy import deepcopy

import pytest

from novel.bible import apply_archive, build_setup
from novel.context import CLOSING_INSTRUCTION, build_brief, build_writer_context, chapter_mode, chapter_stage
from test_novel_schemas import archive_data, config_data, decision_data, setup_data


@pytest.mark.parametrize("chapter,maximum,history,expected", [
    (1, 12, [], "normal"), (10, 12, [], "normal"), (11, 12, [], "closing"), (12, 12, [], "final"),
    (85, 100, [], "closing"), (84, 100, [], "normal"), (100, 100, [], "final"),
    (2, 12, [{"ending_status": "closing"}], "closing"),
    (3, 12, [{"ending_status": "closing"}, {"ending_status": "continue"}], "closing"),
    (12, 12, [{"ending_status": "closing"}], "final"),
])
def test_mode_table(chapter, maximum, history, expected):
    assert chapter_mode(chapter, maximum, history) == expected


@pytest.mark.parametrize("chapter,mode,expected", [
    (1, "normal", "开端"), (2, "normal", "开端"), (3, "normal", "发展"),
    (6, "normal", "发展"), (7, "normal", "高潮"), (10, "normal", "高潮"),
    (1, "closing", "收束"), (10, "final", "收束"),
])
def test_stage_table(chapter, mode, expected):
    assert chapter_stage(chapter, 10, mode) == expected


@pytest.mark.parametrize("chapter,maximum", [(0, 12), (13, 12), (True, 12), (1, 0), (1, False)])
def test_invalid_chapter_is_rejected(chapter, maximum):
    with pytest.raises(ValueError):
        chapter_mode(chapter, maximum)


def test_setup_assigns_ids_and_creates_isolated_locked_and_dynamic_state():
    source, config = setup_data(), config_data()
    source["characters"][0]["id"] = "MODEL_ID"
    source["initial_foreshadowing"][0]["id"] = "MODEL_ID"
    compass, bible = build_setup(source, config)
    assert compass["main_threads"][0]["id"] == "T1"
    assert bible["locked"]["characters"][0]["id"] == "C1"
    assert "initial_state" not in bible["locked"]["characters"][0]
    assert bible["dynamic"]["character_states"]["C1"]["relationships"] == {}
    assert bible["dynamic"]["foreshadowing"][0] == {
        "id": "F001", "description": "银表停在三点", "importance": "major", "planted_chapter": 0, "status": "open"}
    assert bible["version"] == 1
    bible["locked"]["world_rules"].append("新规则")
    compass["target"]["chapter_words"] = 1
    assert source["world_rules"] == ["删除无法逆转"]
    assert config["target"]["chapter_words"] == 1500


def test_archive_allocates_ids_increments_version_and_keeps_original():
    _, bible = build_setup(setup_data(), config_data())
    before = deepcopy(bible)
    delta = archive_data()
    delta["character_state_changes"] = [
        {"id": "C1", "field": "location", "value": "档案室"},
        {"id": "C1", "field": "condition", "value": "伤势好转"},
        {"id": "C1", "field": "knows", "value": "委托来自旧同事"},
        {"id": "C1", "field": "relationships", "value": {"C1": "自我怀疑"}},
    ]
    delta["foreshadowing_planted"] = [{"id": "F999", "description": "门后有脚步声", "importance": "minor"}]
    delta["foreshadowing_resolved"] = [{"id": "F001", "note": "银表记录了事故时间"}]
    delta["new_characters"] = [{"id": "C999", "name": "周临", "role": "supporting", "age": "三十岁",
                                "appearance": "深色外套", "personality": "沉默", "motivation": "寻找证据"}]
    delta["timeline_add"] = ["第1章进入档案室"]
    delta["used_beats_add"] = ["深夜查档"]
    result = apply_archive(bible, delta, 1, "档案室")
    assert bible == before
    assert result["version"] == 2
    assert result["dynamic"]["foreshadowing"][1]["id"] == "F002"
    assert result["dynamic"]["foreshadowing"][1]["planted_chapter"] == 1
    assert result["dynamic"]["foreshadowing"][0]["status"] == "resolved"
    assert result["dynamic"]["foreshadowing"][0]["resolved_chapter"] == 1
    assert result["locked"]["characters"][-1]["id"] == "C2"
    assert result["dynamic"]["character_states"]["C2"] == {"location": "", "condition": "", "knows": [], "relationships": {}}
    state = result["dynamic"]["character_states"]["C1"]
    assert state["knows"] == ["委托有假", "委托来自旧同事"]
    assert state["relationships"] == {"C1": "自我怀疑"}
    assert result["dynamic"]["chapter_summaries"] == [{"chapter": 1, "title": "档案室", "summary": delta["summary"]}]
    assert result["dynamic"]["timeline"] == delta["timeline_add"]
    assert result["dynamic"]["used_beats"] == delta["used_beats_add"]
    assert apply_archive(result, archive_data(), 2, "下一个发现")["version"] == 3


def test_identifiers_use_maximum_instead_of_reusing_gaps():
    _, bible = build_setup(setup_data(), config_data())
    bible["dynamic"]["foreshadowing"][0]["id"] = "F010"
    bible["locked"]["characters"][0]["id"] = "C8"
    bible["dynamic"]["character_states"]["C8"] = bible["dynamic"]["character_states"].pop("C1")
    delta = archive_data()
    delta["foreshadowing_planted"] = [{"description": "新线索", "importance": "major"}]
    delta["new_characters"] = [{"name": "证人", "role": "supporting", "age": "二十岁", "appearance": "短发",
                                "personality": "谨慎", "motivation": "求生"}]
    result = apply_archive(bible, delta, 1, "新证据")
    assert result["dynamic"]["foreshadowing"][-1]["id"] == "F011"
    assert result["locked"]["characters"][-1]["id"] == "C9"


def test_brief_contains_complete_ledger_and_only_last_five_timeline_entries():
    compass, bible = build_setup(setup_data(), config_data())
    bible["dynamic"]["timeline"] = [str(i) for i in range(9)]
    bible["dynamic"]["chapter_summaries"] = [{"chapter": 1, "title": "初见", "summary": "发现线索"}]
    notes = [{"id": "N1", "text": "尽早揭开身份"}]
    brief = build_brief(compass, bible, 11, written_words=10000, user_notes=notes)
    assert brief["dynamic"]["timeline"] == [str(i) for i in range(4, 9)]
    assert brief["dynamic"]["foreshadowing"] == bible["dynamic"]["foreshadowing"]
    assert brief["progress"]["written_chapters"] == 10
    assert brief["progress"]["written_words"] == 10000
    assert brief["mode"] == "closing"
    assert brief["stage"] == "收束"
    assert brief["closing_instruction"] == CLOSING_INSTRUCTION
    assert brief["user_notes"] == notes
    brief["locked"]["characters"][0]["name"] = "改变"
    brief["user_notes"][0]["text"] = "改变"
    assert bible["locked"]["characters"][0]["name"] == "林知"
    assert notes[0]["text"] == "尽早揭开身份"


def test_writer_context_selects_cast_and_open_major_foreshadowing():
    compass, bible = build_setup(setup_data(), config_data())
    bible["locked"]["characters"].append(dict(deepcopy(bible["locked"]["characters"][0]), id="C2", name="旁人"))
    bible["dynamic"]["character_states"]["C2"] = deepcopy(bible["dynamic"]["character_states"]["C1"])
    bible["dynamic"]["foreshadowing"].extend([
        {"id": "F002", "description": "已解开的谜", "importance": "major", "planted_chapter": 0, "status": "resolved"},
        {"id": "F003", "description": "小线索", "importance": "minor", "planted_chapter": 0, "status": "open"},
    ])
    beat = decision_data()["beat_sheet"]
    context = build_writer_context(compass, bible, beat, 2, "前" * 2000 + "后" * 1500)
    assert [item["id"] for item in context["characters"]] == ["C1"]
    assert context["characters"][0]["state"] == bible["dynamic"]["character_states"]["C1"]
    assert context["previous_tail"] == "后" * 1500
    assert [item["id"] for item in context["open_major_foreshadowing"]] == ["F001"]
    assert build_writer_context(compass, bible, beat, 1, "必须忽略")["previous_tail"] == ""
    context["characters"][0]["state"]["knows"].clear()
    assert bible["dynamic"]["character_states"]["C1"]["knows"] == ["委托有假"]
