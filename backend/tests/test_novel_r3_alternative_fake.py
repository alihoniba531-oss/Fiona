"""Offline fake responses follow the split finalize contract and legacy inputs."""

from copy import deepcopy
import json

import pytest

from novel.bible import build_setup
from novel.fake_llm import FakeLLM
from novel.schemas import validate_decision


def request(task, **fields):
    config = {"seed_idea": "核对证据。",
              "target": {"min_chapters": 2, "max_chapters": 4, "chapter_words": 300},
              "adaptation": {"max_main_characters": 3, "max_scenes_per_chapter": 3}}
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
    payload = {"task": task, "chapter": 1, "mode": "normal", "solo": True,
               "brief": {"compass": compass, "locked": bible["locked"], "dynamic": bible["dynamic"]},
               "note_ids": ["N1"], "user_notes": [{"id": "N1", "text": "保留来源。"}], **fields}
    return {"role": "editor", "task": task,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}, compass, bible


@pytest.mark.parametrize("objection_ids,alternative_ids", [
    (["O1", "O2"], ["A1", "A2", "A3"]),
    ([], ["A1"]),
    (["O1"], []),
    ([], []),
])
def test_fake_finalize_uses_separate_alternative_responses(objection_ids, alternative_ids):
    # Keep mixed records just as an existing meeting does, including the case
    # where an explicitly empty objection_ids must not fall back to the A list.
    req, compass, bible = request(
        "finalize", objection_ids=objection_ids, alternative_ids=alternative_ids,
        objections=[{"id": identifier} for identifier in [*objection_ids, *alternative_ids]],
    )
    before = deepcopy(req)
    output = FakeLLM().default_response(req)
    assert req == before
    assert [item["objection_id"] for item in output["objection_responses"]] == objection_ids
    assert output["alternative_responses"] == [
        {"alternative_id": identifier, "decision": "reject",
         "response": "本章保留原来的证据核对方向，替代走向需要更多既有线索铺垫。"}
        for identifier in alternative_ids]
    assert validate_decision(
        output, compass=compass, bible=bible, chapter=1, mode="normal", solo=True,
        proposal_ids=[], objection_ids=objection_ids, alternative_ids=alternative_ids, note_ids=["N1"],
    )["alternative_responses"] == output["alternative_responses"]


def test_fake_legacy_finalize_still_responds_to_alternatives_in_objection_field():
    identifiers = ["O1", "O2", "A1", "A2"]
    req, compass, bible = request("finalize", objection_ids=identifiers)
    output = FakeLLM().default_response(req)
    assert "alternative_responses" not in output
    assert [item["objection_id"] for item in output["objection_responses"]] == identifiers
    assert output["objection_responses"][-1]["response"].startswith("不采纳：")
    assert validate_decision(
        output, compass=compass, bible=bible, chapter=1, mode="normal", solo=True,
        proposal_ids=[], objection_ids=identifiers, note_ids=["N1"],
    )["objection_responses"] == output["objection_responses"]


@pytest.mark.parametrize("task", ["decision", "plan"])
def test_fake_other_editor_tasks_keep_their_existing_response_shape(task):
    req, _, _ = request(task, objection_ids=[] if task == "plan" else ["O1"])
    output = FakeLLM().default_response(req)
    assert "alternative_responses" not in output
    assert [item["objection_id"] for item in output["objection_responses"]] == (
        [] if task == "plan" else ["O1"])
