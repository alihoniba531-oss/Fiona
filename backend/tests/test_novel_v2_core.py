"""Offline structure contracts, sliding windows and immutable bible deltas."""

from copy import deepcopy

import pytest

from novel.bible import apply_archive, apply_volume_plan, build_setup
from novel.context import build_brief, v2_structure_context
from novel.schemas import (
    ValidationError, validate_archive, validate_decision, validate_genre_contract,
    validate_setup, validate_volume_plan,
)
from test_novel_schemas import archive_data, config_data, decision_data, setup_data


def genre_contract():
    return {"genre": "修仙升级", "reader_promise": "看普通人不断变强", "core_thread": "T1",
            "core_payoffs": ["修为突破", "越级取胜", "当众打脸"],
            "payoff_every_chapters": 3, "progression_ladder": ["凡人", "练气", "筑基"],
            "drift_warnings": ["连续悬疑而没有成长"]}


@pytest.fixture
def story_v2():
    config = dict(config_data(), structure="v2")
    config["target"] = {"min_chapters": 25, "max_chapters": 25, "chapter_words": 1000}
    setup = setup_data()
    setup["main_threads"].append({"name": "宗门真相", "description": "查清旧事"})
    setup["genre_contract"] = genre_contract()
    compass, bible = build_setup(setup, config)
    return config, compass, bible


def volume_plan(volume=1, start=1, end=10):
    return {"volume": volume, "chapters": [start, end], "goal": "成为正式弟子",
            "milestones": [
                {"id": "M1", "thread": "T1", "description": "首次突破", "due_chapter": start + 2},
                {"id": "M2", "thread": "T2", "description": "揭开旧事", "due_chapter": end}],
            "payoff_plan": [{"chapter_hint": number, "type": "修为突破"}
                            for number in range(start, end + 1, 3)],
            "threads_focus": ["T1", "T2"], "foreshadowing_to_resolve": ["F001"],
            "new_mystery_budget": 4}


def decide(data, story, *, chapter=3, history=()):
    config, compass, bible = story
    return validate_decision(data, compass=compass, bible=bible, chapter=chapter,
                             mode="normal", proposal_ids=["P1"], objection_ids=[],
                             note_ids=[], config=config, history=history)


def v2_decision():
    return dict(decision_data(), genre_payoff={"type": "修为突破", "beat_index": 1},
                milestones_advanced=[])


@pytest.mark.parametrize("field,value", [
    ("genre", " "), ("reader_promise", ""), ("core_thread", "T9"),
    ("core_thread", []), ("core_payoffs", ["一", "二"]),
    ("core_payoffs", ["一"] * 9), ("core_payoffs", ["一", "二", " "]),
    ("payoff_every_chapters", 0), ("payoff_every_chapters", 6),
    ("payoff_every_chapters", True), ("payoff_every_chapters", 3.0),
    ("progression_ladder", ["一", "二"]), ("progression_ladder", ["一"] * 13),
    ("drift_warnings", ["警告"] * 6), ("drift_warnings", "警告"),
])
def test_genre_contract_rejects_each_invalid_rule(story_v2, field, value):
    data = genre_contract()
    data[field] = value
    before = deepcopy(data)
    with pytest.raises(ValidationError, match=field):
        validate_genre_contract(data, story_v2[1]["main_threads"])
    assert data == before


@pytest.mark.parametrize("period", [1, 5])
def test_genre_contract_accepts_bounds_and_returns_copy(story_v2, period):
    data = genre_contract()
    data["payoff_every_chapters"] = period
    data["drift_warnings"] = []
    result = validate_genre_contract(data, story_v2[1]["main_threads"])
    result["core_payoffs"].append("机缘")
    assert len(data["core_payoffs"]) == 3


def test_setup_contract_is_v2_only_and_uses_code_owned_ids(story_v2):
    config, compass, _bible = story_v2
    source = setup_data()
    assert "genre_contract" not in validate_setup(source, config_data())
    with pytest.raises(ValidationError, match="genre_contract"):
        validate_setup(source, config)
    source["genre_contract"] = genre_contract()
    source["main_threads"][0]["id"] = "MODEL_ID"
    assert build_setup(source, config)[0]["genre_contract"] == compass["genre_contract"]
    source["genre_contract"]["core_thread"] = "MODEL_ID"
    with pytest.raises(ValidationError, match="core_thread"):
        build_setup(source, config)


def validate_plan(data, story):
    _config, compass, bible = story
    return validate_volume_plan(data, compass=compass, bible=bible,
                                volume=1, start_chapter=1, end_chapter=10)


@pytest.mark.parametrize("change", [
    "wrong_volume", "wrong_chapters", "bool_chapter", "blank_goal", "one_milestone",
    "six_milestones", "no_core", "unknown_thread", "duplicate_id", "early_due",
    "late_due", "short_payoffs", "outside_payoff", "unknown_payoff", "resolved_ref",
    "unknown_focus", "negative_budget", "large_budget", "boolean_budget",
])
def test_volume_plan_validates_all_rules(story_v2, change):
    data = volume_plan()
    if change == "wrong_volume":
        data["volume"] = 2
    elif change == "wrong_chapters":
        data["chapters"] = [2, 10]
    elif change == "bool_chapter":
        data["chapters"] = [True, 10]
    elif change == "blank_goal":
        data["goal"] = ""
    elif change == "one_milestone":
        data["milestones"] = data["milestones"][:1]
    elif change == "six_milestones":
        data["milestones"] *= 3
    elif change == "no_core":
        data["milestones"][0]["thread"] = "T2"
    elif change == "unknown_thread":
        data["milestones"][1]["thread"] = "T99"
    elif change == "duplicate_id":
        data["milestones"][1]["id"] = "M1"
    elif change in ("early_due", "late_due"):
        data["milestones"][0]["due_chapter"] = 0 if change == "early_due" else 11
    elif change == "short_payoffs":
        data["payoff_plan"].pop()
    elif change == "outside_payoff":
        data["payoff_plan"][0]["chapter_hint"] = 11
    elif change == "unknown_payoff":
        data["payoff_plan"][0]["type"] = "解谜"
    elif change == "resolved_ref":
        story_v2[2]["dynamic"]["foreshadowing"][0]["status"] = "resolved"
    elif change == "unknown_focus":
        data["threads_focus"] = ["T99"]
    else:
        data["new_mystery_budget"] = {"negative_budget": -1, "large_budget": 7, "boolean_budget": True}[change]
    with pytest.raises(ValidationError):
        validate_plan(data, story_v2)


def test_short_final_volume_uses_ceil_payoff_requirement(story_v2):
    plan = volume_plan(3, 21, 25)
    assert len(plan["payoff_plan"]) == 2
    assert validate_volume_plan(plan, compass=story_v2[1], bible=story_v2[2],
                                volume=3, start_chapter=21, end_chapter=25) == plan
    plan["payoff_plan"].pop()
    with pytest.raises(ValidationError, match="至少需要 2 条，实际 1 条"):
        validate_volume_plan(plan, compass=story_v2[1], bible=story_v2[2],
                             volume=3, start_chapter=21, end_chapter=25)


def test_volume_install_adds_version_preserves_existing_keys_and_resets_status(story_v2):
    bible = story_v2[2]
    old = deepcopy(bible)
    plan = validate_plan(volume_plan(), story_v2)
    plan["milestones"][0]["status"] = "done"
    result = apply_volume_plan(bible, plan)
    assert result["version"] == 2
    assert result["dynamic"]["volumes"][0]["milestones"][0]["status"] == "open"
    assert bible == old
    assert {key: value for key, value in result["dynamic"].items() if key != "volumes"} == old["dynamic"]
    replacement = apply_volume_plan(result, plan)
    assert replacement["version"] == 3
    assert len(replacement["dynamic"]["volumes"]) == 1


@pytest.mark.parametrize("period", [1, 2, 3, 4, 5])
def test_payoff_window_requires_payment_at_deadline(story_v2, period):
    story_v2[1]["genre_contract"]["payoff_every_chapters"] = period
    decision = v2_decision()
    decision["genre_payoff"] = None
    if period > 1:
        assert decide(decision, story_v2, chapter=period - 1)["genre_payoff"] is None
    with pytest.raises(ValidationError, match=f"每 {period} 章至少 1 个"):
        decide(decision, story_v2, chapter=period)
    assert decide(v2_decision(), story_v2, chapter=period)["genre_payoff"]
    if period > 1:
        history = [{"chapter": period - 1, "decision": v2_decision()}]
        assert decide(decision, story_v2, chapter=period, history=history)["genre_payoff"] is None


@pytest.mark.parametrize("payoff", ["突破", {}, {"type": "解谜", "beat_index": 1},
                                    {"type": "修为突破", "beat_index": 0},
                                    {"type": "修为突破", "beat_index": 4},
                                    {"type": "修为突破", "beat_index": True}])
def test_payoff_must_reference_allowed_type_and_one_based_beat(story_v2, payoff):
    decision = v2_decision()
    decision["genre_payoff"] = payoff
    with pytest.raises(ValidationError, match="genre_payoff"):
        decide(decision, story_v2)


def test_core_thread_three_chapter_window_and_noncore_is_advisory(story_v2):
    decision = v2_decision()
    decision["beat_sheet"]["advances_threads"] = ["T2"]
    assert decide(decision, story_v2, chapter=2)
    with pytest.raises(ValidationError, match="连续 2 章未推进.*每 3 章至少 1 次"):
        decide(decision, story_v2, chapter=3)
    history = [{"chapter": 1, "decision": v2_decision()}]
    assert decide(decision, story_v2, chapter=3, history=history)
    assert decide(v2_decision(), story_v2, chapter=9)


def test_due_milestones_are_required_and_unknown_ids_fail(story_v2):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    story = config, compass, bible
    with pytest.raises(ValidationError, match="M1.*第 3 章到期"):
        decide(v2_decision(), story)
    decision = v2_decision()
    decision["milestones_advanced"] = ["M1"]
    assert decide(decision, story)
    decision["milestones_advanced"] = ["M99"]
    with pytest.raises(ValidationError, match="milestones_advanced"):
        decide(decision, story)


def foreshadows(count, *, planted=0):
    return [{"id": f"F{i:03d}", "description": "旧伏笔", "importance": "minor",
             "planted_chapter": planted, "status": "open"} for i in range(1, count + 1)]


def test_per_chapter_foreshadowing_budget_has_numbers(story_v2):
    decision = v2_decision()
    plant = {"description": "新线索", "importance": "minor"}
    decision["beat_sheet"]["foreshadowing_plant"] = [plant] * 2
    assert decide(decision, story_v2)
    decision["beat_sheet"]["foreshadowing_plant"].append(plant)
    with pytest.raises(ValidationError, match="新埋 3 条.*上限 2 条"):
        decide(decision, story_v2)


def test_open_foreshadowing_budget_only_applies_above_twenty(story_v2):
    story_v2[2]["dynamic"]["foreshadowing"] = foreshadows(20)
    decision = v2_decision()
    decision["beat_sheet"]["foreshadowing_plant"] = [{"description": "新线索", "importance": "minor"}]
    assert decide(decision, story_v2)
    story_v2[2]["dynamic"]["foreshadowing"] = foreshadows(21)
    with pytest.raises(ValidationError, match="伏笔 21 条.*上限 20.*新埋 1 条.*回收 0 条"):
        decide(decision, story_v2)
    decision["beat_sheet"]["foreshadowing_resolve"] = ["F001"]
    assert decide(decision, story_v2)


def test_volume_foreshadowing_budget_counts_resolved_plants(story_v2):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    bible["dynamic"]["foreshadowing"] = foreshadows(3, planted=1)
    bible["dynamic"]["foreshadowing"][0]["status"] = "resolved"
    story = config, compass, bible
    decision = v2_decision()
    plant = {"description": "新线索", "importance": "minor"}
    decision["beat_sheet"]["foreshadowing_plant"] = [plant]
    decision["milestones_advanced"] = ["M1"]
    assert decide(decision, story)
    decision["beat_sheet"]["foreshadowing_plant"].append(plant)
    with pytest.raises(ValidationError, match="此前新埋 3 条.*本章 2 条.*合计 5 条.*卷预算 4 条"):
        decide(decision, story)


def test_v1_decision_does_not_require_v2_fields_or_apply_budgets(story_v2):
    config, compass, bible = story_v2
    decision = decision_data()
    decision["beat_sheet"]["foreshadowing_plant"] = [{"description": "线索", "importance": "minor"}] * 3
    original = deepcopy(decision)
    for legacy_config in ({}, {"structure": "v1"}):
        result = decide(decision, (legacy_config, compass, bible))
        assert "genre_payoff" not in result and "milestones_advanced" not in result
    assert decision == original


def test_brief_full_history_windows_red_flags_and_isolation(story_v2):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    bible["dynamic"]["foreshadowing"] = foreshadows(22)
    history = [{"chapter": number, "decision": dict(v2_decision(),
                beat_sheet=dict(decision_data()["beat_sheet"], advances_threads=["T2"]),
                genre_payoff=None)} for number in range(1, 13)]
    history[0]["decision"]["beat_sheet"]["advances_threads"] = ["T1"]
    history[1]["decision"]["genre_payoff"] = {"type": "修为突破", "beat_index": 1}
    brief = build_brief(compass, bible, 13, history, config=config)
    assert brief["thread_staleness"] == {"T1": 12, "T2": 1}
    assert [item["chapter"] for item in brief["payoff_history"]] == list(range(7, 13))
    assert brief["open_foreshadowing_count"] == 22 and brief["foreshadowing_limit"] == 20
    assert any("本章必须推进" in flag for flag in brief["red_flags"])
    assert any("本章必须安排类型爽点" in flag for flag in brief["red_flags"])
    assert any("未回收伏笔 22 条" in flag for flag in brief["red_flags"])
    brief["genre_contract"]["genre"] = "改变"
    assert compass["genre_contract"]["genre"] == "修仙升级"
    assert "red_flags" not in build_brief(compass, bible, 13, history)


def test_due_and_other_thread_red_flags(story_v2):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    brief = build_brief(compass, bible, 3, config=config)
    assert any("里程碑 M1 到期" in flag for flag in brief["red_flags"])
    late = build_brief(compass, bible, 6, config=config)
    assert any("主线 T2 已连续 5 章未推进" in flag for flag in late["red_flags"])


def test_archive_milestones_done_subset_and_done_missed_flow(story_v2):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    before = deepcopy(bible)
    decision = v2_decision()
    decision["milestones_advanced"] = ["M1"]
    archive = dict(archive_data(), milestones_done=["M2"], payoff_delivered=True)
    with pytest.raises(ValidationError, match="milestones_done"):
        validate_archive(archive, bible, config=config, decision=decision)
    archive["milestones_done"] = ["M1"]
    result = apply_archive(bible, archive, 10, "卷末", config=config, decision=decision)
    assert [item["status"] for item in result["dynamic"]["volumes"][0]["milestones"]] == ["done", "missed"]
    assert bible == before
    assert result["dynamic"]["chapter_summaries"] == [{"chapter": 10, "title": "卷末", "summary": archive["summary"]}]
    assert result["dynamic"]["structure_history"] == [{"chapter": 10, "genre_payoff": decision["genre_payoff"], "advances_threads": ["T1"], "payoff_delivered": True}]
    next_bible = apply_volume_plan(result, volume_plan(2, 11, 20))
    brief = build_brief(compass, next_bible, 11, config=config)
    assert brief["current_volume"]["volume"] == 2
    assert any("第 1 卷里程碑 M2 未完成" in flag for flag in brief["red_flags"])
    assert brief["thread_staleness"]["T1"] == 1


def test_archive_actual_planting_cannot_escape_decision_budget(story_v2):
    config, _compass, bible = story_v2
    decision = v2_decision()
    archive = dict(archive_data(), payoff_delivered=True)
    archive["foreshadowing_planted"] = [{"description": "计划外谜团", "importance": "minor"}]
    with pytest.raises(ValidationError, match="实际新埋 1 条.*细纲计划 0 条"):
        validate_archive(archive, bible, config=config, decision=decision)
    decision["beat_sheet"]["foreshadowing_plant"] = deepcopy(archive["foreshadowing_planted"])
    assert validate_archive(archive, bible, config=config, decision=decision)
    bible["dynamic"]["foreshadowing"] = foreshadows(21)
    decision["beat_sheet"]["foreshadowing_resolve"] = ["F001"]
    with pytest.raises(ValidationError, match="新埋 1 条.*回收 0 条"):
        validate_archive(archive, bible, config=config, decision=decision)
    archive["foreshadowing_resolved"] = [{"id": "F001", "note": "真相揭开"}]
    assert validate_archive(archive, bible, config=config, decision=decision)


def test_archived_history_survives_runner_ending_only_rows(story_v2):
    config, compass, bible = story_v2
    bible = apply_archive(bible, dict(archive_data(), payoff_delivered=True), 1, "突破", config=config, decision=v2_decision())
    view = v2_structure_context(compass, bible, 3, [{"chapter": 1, "ending_status": "continue"}])
    assert view["payoff_required"] is False
    assert view["thread_staleness"]["T1"] == 2


def test_archive_budget_enforces_actual_per_chapter_and_volume_totals(story_v2):
    config, _compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    bible["dynamic"]["chapter_summaries"] = [{"chapter": 1, "title": "旧章", "summary": "摘要"}]
    bible["dynamic"]["foreshadowing"] = foreshadows(4, planted=1)
    archive = dict(archive_data(), payoff_delivered=True)
    archive["foreshadowing_planted"] = [{"description": "新谜团", "importance": "minor"}]
    decision = v2_decision()
    decision["beat_sheet"]["foreshadowing_plant"] = deepcopy(archive["foreshadowing_planted"])
    with pytest.raises(ValidationError, match="此前新埋 4 条.*本章 1 条.*卷预算 4 条"):
        validate_archive(archive, bible, config=config, decision=decision)
    bible["dynamic"]["foreshadowing"] = []
    archive["foreshadowing_planted"] *= 3
    decision["beat_sheet"]["foreshadowing_plant"] *= 3
    with pytest.raises(ValidationError, match="本章新埋 3 条.*上限 2 条"):
        validate_archive(archive, bible, config=config, decision=decision)


@pytest.mark.parametrize("value", [None, "M1", ["M1", "M1"], ["M99"], [[]]])
def test_archive_done_values_keep_typed_errors(story_v2, value):
    config, _compass, bible = story_v2
    archive = dict(archive_data(), milestones_done=value, payoff_delivered=True)
    decision = dict(v2_decision(), milestones_advanced=["M1"])
    with pytest.raises(ValidationError, match="milestones_done"):
        validate_archive(archive, bible, config=config, decision=decision)


def test_v2_decision_requires_both_new_fields(story_v2):
    with pytest.raises(ValidationError) as caught:
        decide(decision_data(), story_v2)
    assert "decision.genre_payoff：缺少字段" in caught.value.errors
    assert any("milestones_advanced" in message for message in caught.value.errors)


def test_context_trims_archived_records_after_computing_complete_staleness(story_v2):
    config, compass, bible = story_v2
    bible["dynamic"]["structure_history"] = [
        {"chapter": number, "genre_payoff": None, "advances_threads": ["T1"] if number == 1 else ["T2"]}
        for number in range(1, 20)]
    before = deepcopy(bible)
    brief = build_brief(compass, bible, 20, config=config)
    assert brief["thread_staleness"]["T1"] == 19
    assert len(brief["dynamic"]["structure_history"]) == 10
    assert bible == before


@pytest.mark.parametrize("field,value", [("genre_payoff", []), ("milestones_advanced", {}),
                                         ("milestones_advanced", ["M1", "M1"])])
def test_new_decision_fields_keep_typed_errors(story_v2, field, value):
    data = v2_decision()
    data[field] = value
    with pytest.raises(ValidationError):
        decide(data, story_v2)


def test_legacy_chapter_archive_after_upgrade_preserves_all_canonical_facts(story_v2):
    config, _compass, bible = story_v2
    archive = archive_data()
    archive["foreshadowing_planted"] = [{"description": "旧章实际发生的伏笔", "importance": "minor"}] * 3
    bible["dynamic"]["foreshadowing"] = foreshadows(22)
    original = deepcopy(bible)
    legacy = decision_data()  # No genre_payoff key: this was written under v1.
    before_upgrade = apply_archive(bible, archive, 2, "旧章改稿", config={"structure": "v1"}, decision=legacy)
    after_upgrade = apply_archive(bible, archive, 2, "旧章改稿", config=config, decision=legacy)
    assert after_upgrade == before_upgrade
    assert len(after_upgrade["dynamic"]["foreshadowing"]) == 25
    assert "structure_history" not in after_upgrade["dynamic"]
    assert bible == original
    invalid_done = dict(archive, milestones_done=["M9"])
    with pytest.raises(ValidationError, match="milestones_done"):
        validate_archive(invalid_done, bible, config=config, decision=legacy)


def test_v2_chapter_archive_keeps_budget_checks_when_payoff_is_null(story_v2):
    config, _compass, bible = story_v2
    archive = archive_data()
    archive["foreshadowing_planted"] = [{"description": "新章谜团", "importance": "minor"}] * 3
    decision = dict(v2_decision(), genre_payoff=None)
    with pytest.raises(ValidationError, match="本章新埋 3 条.*上限 2 条"):
        apply_archive(bible, archive, 2, "v2 改稿", config=config, decision=decision)


@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", [], {}])
def test_planned_payoff_requires_strict_archive_confirmation(story_v2, value):
    config, _compass, bible = story_v2
    archive = dict(archive_data(), payoff_delivered=value)
    with pytest.raises(ValidationError, match="archive.payoff_delivered.*必须是布尔值"):
        validate_archive(archive, bible, config=config, decision=v2_decision())


def test_planned_payoff_cannot_omit_archive_confirmation(story_v2):
    config, _compass, bible = story_v2
    with pytest.raises(ValidationError, match="archive.payoff_delivered"):
        validate_archive(archive_data(), bible, config=config, decision=v2_decision())
    assert validate_archive(archive_data(), bible, config=config,
                            decision=dict(v2_decision(), genre_payoff=None))


@pytest.mark.parametrize("delivered", [True, False])
def test_payoff_archive_confirmation_is_persisted_and_controls_next_window(story_v2, delivered):
    config, compass, bible = story_v2
    archive = dict(archive_data(), payoff_delivered=delivered)
    result = apply_archive(bible, archive, 2, "计划突破", config=config, decision=v2_decision())
    record = result["dynamic"]["structure_history"][0]
    assert record["payoff_delivered"] is delivered
    assert record["genre_payoff"] == v2_decision()["genre_payoff"]
    view = v2_structure_context(compass, result, 3)
    assert view["payoff_required"] is not delivered
    assert view["payoff_history"][-1]["payoff_delivered"] is delivered
    assert view["payoff_history"][-1]["genre_payoff"] == (record["genre_payoff"] if delivered else None)
    decision = dict(v2_decision(), genre_payoff=None)
    if delivered:
        assert decide(decision, (config, compass, result), chapter=3)
    else:
        with pytest.raises(ValidationError, match="最近 2 章爽点数为 0"):
            decide(decision, (config, compass, result), chapter=3)


def test_history_archive_false_takes_priority_over_plan_and_persisted_true(story_v2):
    config, compass, bible = story_v2
    bible = apply_archive(bible, dict(archive_data(), payoff_delivered=True), 2, "计划突破",
                          config=config, decision=v2_decision())
    history = [{"chapter": 2, "decision": v2_decision(), "archive": {"payoff_delivered": False}}]
    view = v2_structure_context(compass, bible, 3, history)
    assert view["payoff_required"] is True
    assert view["payoff_history"][-1] == {"chapter": 2, "genre_payoff": None, "payoff_delivered": False}
    # An ending-only resume row cannot erase the confirmation stored in bible.
    bible["dynamic"]["structure_history"][0]["payoff_delivered"] = False
    no_archive = [{"chapter": 2, "decision": v2_decision()}]
    assert v2_structure_context(compass, bible, 3, no_archive)["payoff_required"] is True


def test_history_without_confirmation_falls_back_to_legacy_planned_payoff(story_v2):
    _config, compass, bible = story_v2
    for history in ([{"chapter": 2, "decision": v2_decision()}],
                    [{"chapter": 2, "decision": v2_decision(), "archive": {}}]):
        view = v2_structure_context(compass, bible, 3, history)
        assert view["payoff_required"] is False
        assert "payoff_delivered" not in view["payoff_history"][-1]


@pytest.mark.parametrize("period", [2, 3, 4, 5])
def test_payoff_window_excludes_exactly_one_chapter_before_window(story_v2, period):
    story_v2[1]["genre_contract"]["payoff_every_chapters"] = period
    chapter = period * 3 + 1
    decision = dict(v2_decision(), genre_payoff=None)
    just_outside = [{"chapter": chapter - period, "decision": v2_decision(),
                     "archive": {"payoff_delivered": True}}]
    with pytest.raises(ValidationError, match=f"每 {period} 章至少 1 个"):
        decide(decision, story_v2, chapter=chapter, history=just_outside)
    first_inside = [{"chapter": chapter - period + 1, "decision": v2_decision(),
                     "archive": {"payoff_delivered": True}}]
    assert decide(decision, story_v2, chapter=chapter, history=first_inside)["genre_payoff"] is None


@pytest.mark.parametrize("chapter,overdue", [(4, 1), (5, 2), (9, 6), (10, 7)])
def test_open_overdue_milestone_remains_flagged_and_mandatory(story_v2, chapter, overdue):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    story = config, compass, bible
    view = build_brief(compass, bible, chapter, config=config)
    assert any(f"里程碑 M1 已逾期 {overdue} 章" in flag for flag in view["red_flags"])
    with pytest.raises(ValidationError, match=f"M1.*已逾期 {overdue} 章"):
        decide(v2_decision(), story, chapter=chapter)
    advanced = ["M1"] + (["M2"] if chapter == 10 else [])
    assert decide(dict(v2_decision(), milestones_advanced=advanced), story, chapter=chapter)


@pytest.mark.parametrize("status", ["done", "missed"])
def test_closed_milestone_no_longer_adds_overdue_pressure(story_v2, status):
    config, compass, bible = story_v2
    bible = apply_volume_plan(bible, volume_plan())
    bible["dynamic"]["volumes"][0]["milestones"][0]["status"] = status
    view = build_brief(compass, bible, 5, config=config)
    assert not any("M1" in flag for flag in view["red_flags"])
    assert decide(v2_decision(), (config, compass, bible), chapter=5)


@pytest.mark.parametrize("open_count,budget,planted,required", [
    (20, 4, 0, False), (21, 4, 0, True), (0, 4, 4, True), (0, 4, 3, False),
    (0, 0, 0, True),
])
def test_mystery_budget_red_flag_also_restricts_ending_hook(story_v2, open_count, budget, planted, required):
    config, compass, bible = story_v2
    plan = volume_plan()
    plan["new_mystery_budget"] = budget
    bible = apply_volume_plan(bible, plan)
    bible["dynamic"]["foreshadowing"] = foreshadows(open_count)
    for item in foreshadows(planted, planted=1):
        item["id"] = "P" + item["id"]
        item["status"] = "resolved"
        bible["dynamic"]["foreshadowing"].append(item)
    brief = build_brief(compass, bible, 5, config=config)
    assert ("本章章末钩子不得引入新的未解谜团，只能使用已有线索或正面冲突" in brief["red_flags"]) is required
