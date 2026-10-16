"""Offline coverage for the ordered editor response checklist, without new validation rules."""

import asyncio
from copy import deepcopy
import json

import pytest

from novel.agent_pool import get_agent
from novel.bible import build_setup
from novel.context import build_brief
from novel.deliberation import deliberate, required_response_ids
from novel.fake_llm import FakeLLM
from novel.runner import _redo


RESPONSE_ORDER_RULE = (
    "`objection_responses` 必须按 `required_response_ids` 中 O 的顺序逐条回应，"
    "条数与 O 清单一致；`user_note_responses` 按其中 N 的顺序回应。"
)
ADVISORS = ["plot_architect", "character_advocate", "twist_designer", "pacing_advisor"]
NOTES = [{"id": identifier, "text": "保留现有证据来源。"}
         for identifier in ("N1", "N2", "N10")]


class RecordingRouter:
    """Record actual messages and run the original per-call validator."""

    def __init__(self, fake):
        self.fake = fake
        self.requests = []

    async def call(self, **request):
        self.requests.append(deepcopy({key: value for key, value in request.items()
                                       if key != "validator"}))
        raw, _ = await self.fake(request)
        return request["validator"](json.loads(raw))


def workshop(panel_mode):
    config = {
        "experiment": "P1", "panel_mode": panel_mode, "seed_idea": "核对旧案证据。",
        "target": {"min_chapters": 8, "max_chapters": 12, "chapter_words": 300},
        "adaptation": {"max_main_characters": 3, "max_scenes_per_chapter": 3},
        "agents": {role: f"fake:{role}" for role in
                   ["editor", "writer", "archivist", *ADVISORS]},
    }
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
    return config, compass, bible


def reverse_response_arrays(answer):
    """Order remains model guidance: an exact but reversed response set is legal."""
    for field in ("objection_responses", "alternative_responses", "user_note_responses"):
        if field in answer:
            answer[field].reverse()
    return answer


@pytest.mark.parametrize("task", [None, "plan", "finalize"])
def test_three_editor_cards_include_the_exact_response_order_instruction(task):
    assert RESPONSE_ORDER_RULE in get_agent("editor", task=task)["system_prompt"]


def test_response_checklist_groups_prefixes_without_sorting_or_mutating_assigned_ids():
    objections = ["A1", "O1", "A2", "O2", "O10"]
    notes = ["N1", "N2", "N10"]
    assert required_response_ids(objections, notes) == [
        "O1", "O2", "O10", "N1", "N2", "N10"]
    assert objections == ["A1", "O1", "A2", "O2", "O10"]
    assert notes == ["N1", "N2", "N10"]
    # The helper follows the supplied assignment sequence even for unusual IDs.
    assert required_response_ids(["O10", "O2", "O1"], ["N10", "N2"]) == [
        "O10", "O2", "O1", "N10", "N2"]


def test_finalize_checklist_follows_assignment_after_out_of_order_advisor_completion():
    async def run():
        config, compass, bible = workshop("critique")
        pacing_done, character_done = asyncio.Event(), asyncio.Event()
        completed = []

        async def script(request, _):
            if request["task"] != "critique_plan":
                return reverse_response_arrays(fake.default_response(request))
            role = request["role"]
            if role == "plot_architect":
                await character_done.wait()
            elif role == "character_advocate":
                await pacing_done.wait()
            elif role == "pacing_advisor":
                pacing_done.set()
            completed.append(role)
            if role == "character_advocate":
                character_done.set()
            answer = {
                "objections": [{"severity": "major", "target": f"{role}节拍{n}",
                                "problem": "缺少证据来源。", "suggestion": "呈现核对原件的动作。"}
                               for n in range(3)],
                "keep": "保留主角保存证据的选择。",
            }
            if role in ("twist_designer", "pacing_advisor"):
                answer["alternative"] = "让主角先识别原始签名，再决定是否公开证人身份。"
            return answer

        fake = FakeLLM(script)
        router = RecordingRouter(fake)
        meeting = await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                                   participants=["editor", *ADVISORS], user_notes=NOTES)
        assert completed == ["twist_designer", "pacing_advisor", "character_advocate", "plot_architect"]
        payload = FakeLLM.payload(router.requests[-1])
        expected = [*[f"O{n}" for n in range(1, 13)], "N1", "N2", "N10"]
        assert payload["task"] == "finalize"
        assert payload["required_response_ids"] == expected
        assert payload["objection_ids"] == expected[:-3]
        assert payload["alternative_ids"] == ["A1", "A2"]
        assert [item["author"] for item in meeting["objections"][:12]] == [
            role for role in ADVISORS for _ in range(3)]
        assert [item["author"] for item in meeting["objections"][12:]] == [
            "twist_designer", "pacing_advisor"]
        plan = FakeLLM.payload(router.requests[0])
        assert plan["task"] == "plan" and plan["required_response_ids"] == ["N1", "N2", "N10"]
        assert router.requests[-1]["step_key"] == "arm-panel/ch001/03-finalize-editor.json"
        # Reversed output remains accepted; this change does not tighten the validator.
        assert [item["objection_id"] for item in meeting["decision"]["objection_responses"]] == list(
            reversed(expected[:-3]))
        assert [item["alternative_id"] for item in meeting["decision"]["alternative_responses"]] == [
            "A2", "A1"]
        assert [item["note_id"] for item in meeting["decision"]["user_note_responses"]] == [
            "N10", "N2", "N1"]

    asyncio.run(run())


@pytest.mark.parametrize("panel_mode", ["merge", "solo"])
def test_merge_and_solo_decision_payloads_include_the_assigned_checklist(panel_mode):
    async def run():
        config, compass, bible = workshop(panel_mode)
        fake = FakeLLM(lambda request, _: reverse_response_arrays(fake.default_response(request)))
        router = RecordingRouter(fake)
        participants = ["editor", *ADVISORS] if panel_mode == "merge" else ["editor"]
        meeting = await deliberate(router, config, compass, bible, chapter=1, arm=panel_mode,
                                   participants=participants, user_notes=NOTES)
        payload = FakeLLM.payload(router.requests[-1])
        objection_ids = [f"O{n}" for n in range(1, 5)] if panel_mode == "merge" else []
        assert payload["task"] == "decision"
        assert payload["required_response_ids"] == [*objection_ids, "N1", "N2", "N10"]
        assert payload["objection_ids"] == objection_ids
        assert [item["note_id"] for item in meeting["decision"]["user_note_responses"]] == [
            "N10", "N2", "N1"]
        assert router.requests[-1]["step_key"] == f"arm-{panel_mode}/ch001/03-decision-editor.json"

    asyncio.run(run())


@pytest.mark.parametrize("panel_mode", ["critique", "merge", "solo"])
def test_redo_editor_uses_the_same_checklist_for_finalize_and_decision(panel_mode):
    async def run():
        config, compass, bible = workshop(panel_mode)
        objections = ([{"id": identifier} for identifier in ("A1", "O1", "A2", "O2", "O10")]
                      if panel_mode != "solo" else [])
        meeting = {
            "brief": build_brief(compass, bible, 1, user_notes=NOTES),
            "objections": objections, "_redo_note": "保留主角主动保存证据的选择。", "_redo_count": 2,
        }
        if panel_mode == "critique":
            meeting.update(mode="critique", plan={"rationale": "保存证据。"})
        elif panel_mode == "merge":
            meeting["proposals"] = [{"id": "P1"}]
        original = deepcopy(meeting)
        fake = FakeLLM(lambda request, _: reverse_response_arrays(fake.default_response(request)))
        router = RecordingRouter(fake)
        result = await _redo(None, router, config, compass, bible, 1, panel_mode, meeting)
        assert len(router.requests) == 1
        payload = FakeLLM.payload(router.requests[0])
        expected_objections = ["O1", "O2", "O10"] if panel_mode != "solo" else []
        assert payload["required_response_ids"] == [*expected_objections, "N1", "N2", "N10"]
        if panel_mode == "critique":
            assert payload["objection_ids"] == expected_objections
            assert payload["alternative_ids"] == ["A1", "A2"]
        else:
            assert "alternative_ids" not in payload
        task = "finalize" if panel_mode == "critique" else "decision"
        assert payload["task"] == task
        assert router.requests[0]["step_key"] == f"arm-{panel_mode}/ch001/03-{task}-editor-redo2.json"
        assert [item["note_id"] for item in result["decision"]["user_note_responses"]] == [
            "N10", "N2", "N1"]
        assert meeting == original

    asyncio.run(run())
