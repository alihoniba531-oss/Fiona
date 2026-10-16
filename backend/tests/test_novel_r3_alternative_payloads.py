"""Offline H1 payload coverage for separate objection and alternative responses."""

import asyncio
from copy import deepcopy
import json

import pytest

from novel.agent_pool import get_agent
from novel.bible import build_setup
from novel.context import build_brief
from novel.deliberation import deliberate, required_response_ids, split_response_ids
from novel.fake_llm import FakeLLM
from novel.runner import _redo


ADVISORS = ["plot_architect", "character_advocate", "twist_designer"]
NOTES = [{"id": identifier, "text": "先呈现证据，再揭示人物身份。"}
         for identifier in ("N1", "N2", "N10")]


class CaptureRouter:
    def __init__(self, fake):
        self.fake = fake
        self.requests = []

    async def call(self, **request):
        self.requests.append(deepcopy({key: value for key, value in request.items()
                                       if key != "validator"}))
        raw, _ = await self.fake(request)
        return request["validator"](json.loads(raw))


def workshop(panel_mode="critique", compressed=False):
    config = {
        "experiment": "P1", "panel_mode": panel_mode, "seed_idea": "追查原始记录。",
        "target": {"min_chapters": 8, "max_chapters": 12, "chapter_words": 300},
        "adaptation": {"max_main_characters": 3, "max_scenes_per_chapter": 3},
        "agents": {role: f"fake:{role}" for role in
                   ["editor", "writer", "archivist", *ADVISORS]},
        "enable_context_compression": compressed,
    }
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
    return config, compass, bible


@pytest.mark.parametrize("compressed", [False, True])
def test_finalize_separates_nine_objections_three_alternatives_and_notes(compressed):
    async def run():
        config, compass, bible = workshop(compressed=compressed)
        twist_done, character_done = asyncio.Event(), asyncio.Event()
        completed = []

        async def script(request, _):
            if request["task"] != "critique_plan":
                return None
            role = request["role"]
            if role == "plot_architect":
                await character_done.wait()
            elif role == "character_advocate":
                await twist_done.wait()
            completed.append(role)
            if role == "twist_designer":
                twist_done.set()
            elif role == "character_advocate":
                character_done.set()
            return {
                "objections": [{"severity": "major", "target": f"{role}节拍{n}",
                                "problem": "原件来源尚未交代。", "suggestion": "加入核对签名的动作。"}
                               for n in range(3)],
                "keep": "保留主角主动保存证据的选择。",
                "alternative": "先让证人证明副本来源，再由主角选择是否公开身份。",
            }

        router = CaptureRouter(FakeLLM(script))
        meeting = await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                                   participants=["editor", *ADVISORS], user_notes=NOTES)
        payload = FakeLLM.payload(router.requests[-1])
        objections = [f"O{n}" for n in range(1, 10)]
        alternatives = ["A1", "A2", "A3"]
        assert completed == list(reversed(ADVISORS))
        assert payload["task"] == "finalize"
        assert payload["objection_ids"] == objections
        assert payload["alternative_ids"] == alternatives
        assert payload["required_response_ids"] == [*objections, "N1", "N2", "N10"]
        assert [item["id"] for item in payload["objections"]] == [*objections, *alternatives]
        assert payload["objections"] == meeting["objections"]
        assert [item["author"] for item in meeting["objections"][:9]] == [
            role for role in ADVISORS for _ in range(3)]
        assert [item["author"] for item in meeting["objections"][9:]] == ADVISORS
        assert [item["objection_id"] for item in meeting["decision"]["objection_responses"]] == objections
        assert [item["alternative_id"] for item in meeting["decision"]["alternative_responses"]] == alternatives
        assert all(item["decision"] in ("adopt", "partial", "reject") and item["response"].strip()
                   for item in meeting["decision"]["alternative_responses"])
        assert [request["step_key"] for request in router.requests] == [
            "arm-panel/ch001/01-plan-editor.json",
            *[f"arm-panel/ch001/02-critique-plan-{role}.json" for role in ADVISORS],
            "arm-panel/ch001/03-finalize-editor.json",
        ]
        plan = FakeLLM.payload(router.requests[0])
        assert "alternative_ids" not in plan
        assert plan["required_response_ids"] == ["N1", "N2", "N10"]

    asyncio.run(run())


def test_finalize_without_alternatives_has_empty_alternative_list():
    async def run():
        config, compass, bible = workshop()
        router = CaptureRouter(FakeLLM())
        meeting = await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                                   participants=["editor", "plot_architect", "character_advocate"],
                                   user_notes=NOTES)
        payload = FakeLLM.payload(router.requests[-1])
        assert payload["objection_ids"] == ["O1", "O2"]
        assert payload["alternative_ids"] == []
        assert payload["required_response_ids"] == ["O1", "O2", "N1", "N2", "N10"]
        assert meeting["decision"]["alternative_responses"] == []

    asyncio.run(run())


def test_redo_of_legacy_mixed_meeting_emits_separate_id_lists_and_new_output():
    async def run():
        config, compass, bible = workshop()
        brief = build_brief(compass, bible, 1, user_notes=NOTES)
        mixed_ids = ["O1", "O2", "O10", "A1", "A2"]
        legacy_payload = {
            "task": "finalize", "chapter": 1, "mode": "normal", "brief": brief,
            "solo": True, "objection_ids": mixed_ids, "note_ids": ["N1", "N2", "N10"],
        }
        legacy = FakeLLM().default_response({"task": "finalize", "payload": legacy_payload})
        assert "alternative_responses" not in legacy
        assert [item["objection_id"] for item in legacy["objection_responses"]] == mixed_ids
        meeting = {
            "mode": "critique", "brief": brief, "plan": {"rationale": "先保存证据。"},
            "objections": [{"id": identifier} for identifier in mixed_ids], "decision": legacy,
            "_redo_note": "重新评估公开证人身份的代价。", "_redo_count": 1,
        }
        original = deepcopy(meeting)
        router = CaptureRouter(FakeLLM())
        result = await _redo(None, router, config, compass, bible, 1, "panel", meeting)
        payload = FakeLLM.payload(router.requests[0])
        assert payload["objection_ids"] == ["O1", "O2", "O10"]
        assert payload["alternative_ids"] == ["A1", "A2"]
        assert payload["required_response_ids"] == ["O1", "O2", "O10", "N1", "N2", "N10"]
        assert [item["alternative_id"] for item in result["decision"]["alternative_responses"]] == ["A1", "A2"]
        assert payload["objections"] == original["objections"]
        assert router.requests[0]["step_key"] == "arm-panel/ch001/03-finalize-editor-redo1.json"
        assert meeting == original

    asyncio.run(run())


@pytest.mark.parametrize("panel_mode", ["merge", "solo"])
def test_non_critique_decision_keeps_the_existing_payload_and_output_structure(panel_mode):
    async def run():
        config, compass, bible = workshop(panel_mode)
        router = CaptureRouter(FakeLLM())
        participants = ["editor", *ADVISORS] if panel_mode == "merge" else ["editor"]
        meeting = await deliberate(router, config, compass, bible, chapter=1, arm=panel_mode,
                                   participants=participants, user_notes=NOTES)
        payload = FakeLLM.payload(router.requests[-1])
        assert set(payload) == {
            "task", "chapter", "mode", "brief", "proposals", "scores", "objections",
            "proposal_ids", "objection_ids", "user_notes", "note_ids", "solo", "required_response_ids",
        }
        assert "alternative_responses" not in meeting["decision"]
        assert all(identifier.startswith(("O", "N")) for identifier in payload["required_response_ids"])

    asyncio.run(run())


def test_response_helpers_keep_assignment_order_and_exclude_alternatives_from_required_list():
    ids = ["A1", "O1", "O2", "A2", "O10"]
    assert split_response_ids(ids) == (["O1", "O2", "O10"], ["A1", "A2"])
    assert required_response_ids(ids, ["N1", "N2", "N10"]) == [
        "O1", "O2", "O10", "N1", "N2", "N10"]
    assert ids == ["A1", "O1", "O2", "A2", "O10"]


def test_finalize_card_describes_separate_fields_enumerated_decisions_and_nonempty_reasons():
    prompt = get_agent("editor", task="finalize")["system_prompt"]
    assert '"alternative_responses":[{"alternative_id":"A1","decision":"adopt|partial|reject","response":"理由"}]' in prompt
    assert "objection_responses 只回应 objection_ids 中的 O*" in prompt
    assert "alternative_responses 按 alternative_ids 的顺序逐条回应 A*" in prompt
    assert "adopt（采纳）、partial（部分采纳）或 reject（不采纳）" in prompt
    assert "response 必须给出非空理由" in prompt
    assert "user_note_responses 回应本次 N* 用户留言" in prompt
    for task in (None, "plan", "finalize"):
        assert "中 O 与 A 的顺序" not in get_agent("editor", task=task)["system_prompt"]
