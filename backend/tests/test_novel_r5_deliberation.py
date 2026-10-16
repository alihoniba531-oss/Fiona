"""Portable offline coverage for editor-plan / advisor-critique meetings."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from novel.agent_pool import AGENTS
from novel.bible import build_setup
from novel.deliberation import deliberate
from novel.fake_llm import FakeLLM
from novel.llm_router import StepFailed
from novel.schemas import ValidationError
from test_novel_workflow import LocalRouter


@pytest.fixture
def workshop():
    config = json.loads((Path(__file__).parents[1] / "novel/pilot_configs/expA.json").read_text())
    config["panel_mode"] = "critique"
    config["target"] = {"min_chapters": 8, "max_chapters": 12, "chapter_words": 300}
    config["agents"] = {role: f"fake:{role}" for role in config["agents"]}
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
    return config, compass, bible


def run_meeting(workshop, router=None, *, arm="panel", participants=None, notes=()):
    config, compass, bible = workshop
    return asyncio.run(deliberate(router or LocalRouter(), config, compass, bible,
                                  chapter=1, arm=arm, user_notes=notes,
                                  participants=participants or config["arms"]["panel"]))


def tasks(router):
    return [FakeLLM.payload(request)["task"] for request in router.requests]


def test_critique_runs_plan_then_parallel_advisors_then_finalize(workshop):
    router = LocalRouter()
    notes = [{"id": "N1", "text": "先呈现读者能判断的证据。"}]
    meeting = run_meeting(workshop, router, notes=notes)
    assert tasks(router) == ["plan", "critique_plan", "critique_plan", "critique_plan", "finalize"]
    assert [request["step_key"] for request in router.requests] == [
        "arm-panel/ch001/01-plan-editor.json",
        "arm-panel/ch001/02-critique-plan-plot_architect.json",
        "arm-panel/ch001/02-critique-plan-character_advocate.json",
        "arm-panel/ch001/02-critique-plan-twist_designer.json",
        "arm-panel/ch001/03-finalize-editor.json",
    ]
    assert router.max_active == 3
    assert set(meeting) == {"mode", "brief", "plan", "critiques", "objections", "decision"}
    assert meeting["mode"] == "critique"
    assert meeting["plan"]["chosen_proposal_ids"] == []
    assert meeting["plan"]["objection_responses"] == []
    assert meeting["plan"]["user_note_responses"][0]["note_id"] == "N1"
    assert meeting["decision"]["chosen_proposal_ids"] == []
    assert meeting["decision"]["user_note_responses"][0]["note_id"] == "N1"
    assert [item["objection_id"] for item in meeting["decision"]["objection_responses"]] == [
        item["id"] for item in meeting["objections"] if item["id"].startswith("O")]
    assert [item["alternative_id"] for item in meeting["decision"]["alternative_responses"]] == [
        item["id"] for item in meeting["objections"] if item["id"].startswith("A")]
    for request in router.requests[1:4]:
        payload = FakeLLM.payload(request)
        assert payload["brief"] == meeting["brief"]
        assert payload["plan"] == {key: meeting["plan"][key]
                                   for key in ("beat_sheet", "rationale", "ending_status")}
        assert "scores" not in payload and "proposals" not in payload
    final_payload = FakeLLM.payload(router.requests[-1])
    assert final_payload["critiques"] == meeting["critiques"]
    assert final_payload["plan"] == meeting["plan"]
    assert final_payload["objections"] == meeting["objections"]
    assert final_payload["solo"] is True and final_payload["proposal_ids"] == []
    assert all(item["author_name"] == AGENTS[item["author"]]["name"]
               for item in meeting["critiques"] + meeting["objections"])


def test_ids_follow_configuration_order_even_when_advisors_finish_in_reverse(workshop):
    completion = []
    roles = ["plot_architect", "character_advocate", "twist_designer"]

    async def reverse_advisors(request, _index):
        if FakeLLM.payload(request)["task"] != "critique_plan":
            return None
        role = request["role"]
        await asyncio.sleep({"plot_architect": .03, "character_advocate": .02,
                             "twist_designer": .001}[role])
        completion.append(role)
        count = 2 if role == "plot_architect" else 1
        result = {"objections": [
            {"severity": "major" if i == 0 else "minor", "target": f"{role}节拍{i}",
             "problem": "因果依据未呈现。", "suggestion": "增加核对记录的动作。"}
            for i in range(count)], "keep": "保留人物的主动选择。"}
        if role in ("character_advocate", "twist_designer"):
            result["alternative"] = f"{role}提出另一种有证据支持的走向。"
        return result

    router = LocalRouter(FakeLLM(reverse_advisors))
    meeting = run_meeting(workshop, router)
    assert completion == list(reversed(roles))
    assert [item["author"] for item in meeting["critiques"]] == roles
    assert [item["id"] for item in meeting["objections"]] == ["O1", "O2", "O3", "O4", "A1", "A2"]
    assert [item["author"] for item in meeting["objections"]] == [
        "plot_architect", "plot_architect", "character_advocate", "twist_designer",
        "character_advocate", "twist_designer"]
    assert meeting["objections"][1]["severity"] == "minor"


def test_whitespace_only_optional_alternative_does_not_get_an_a_id(workshop):
    def whitespace_alternative(request, _index):
        if (FakeLLM.payload(request)["task"] == "critique_plan"
                and request["role"] != "twist_designer"):
            response = FakeLLM().default_response(request)
            response["alternative"] = " \n\t "
            return response
        return None

    meeting = run_meeting(workshop, LocalRouter(FakeLLM(whitespace_alternative)))
    alternatives = [item for item in meeting["objections"] if item["id"].startswith("A")]
    assert len(alternatives) == 1
    assert alternatives[0]["id"] == "A1"
    assert alternatives[0]["author"] == "twist_designer"
    assert [item["objection_id"] for item in meeting["decision"]["objection_responses"]] == [
        item["id"] for item in meeting["objections"] if item["id"].startswith("O")]
    assert [item["alternative_id"] for item in meeting["decision"]["alternative_responses"]] == [
        item["id"] for item in meeting["objections"] if item["id"].startswith("A")]


@pytest.mark.parametrize("prefix", ["O", "A"])
@pytest.mark.parametrize("fault", ["missing", "duplicate"])
def test_finalize_requires_exactly_one_response_to_every_objection_and_alternative(workshop, prefix, fault):
    def broken_finalize(request, _index):
        if FakeLLM.payload(request)["task"] != "finalize":
            return None
        response = FakeLLM().default_response(request)
        responses = response["alternative_responses" if prefix == "A" else "objection_responses"]
        id_field = "alternative_id" if prefix == "A" else "objection_id"
        selected = next(item for item in responses if item[id_field].startswith(prefix))
        if fault == "missing":
            responses.remove(selected)
        else:
            responses.append(deepcopy(selected))
        return response

    with pytest.raises(ValidationError, match="恰好回应一次"):
        run_meeting(workshop, LocalRouter(FakeLLM(broken_finalize)))


@pytest.mark.parametrize("fault", ["chosen_proposal", "objection_response", "missing_user_note"])
def test_plan_uses_solo_validation_before_any_advisor_runs(workshop, fault):
    def broken_plan(request, _index):
        if FakeLLM.payload(request)["task"] != "plan":
            return None
        response = FakeLLM().default_response(request)
        if fault == "chosen_proposal":
            response["chosen_proposal_ids"] = ["P1"]
        elif fault == "objection_response":
            response["objection_responses"] = [{"objection_id": "O1", "response": "修改。"}]
        else:
            response["user_note_responses"] = []
        return response

    router = LocalRouter(FakeLLM(broken_plan))
    with pytest.raises(ValidationError):
        run_meeting(workshop, router, notes=[{"id": "N1", "text": "保留悬念。"}])
    assert tasks(router) == ["plan"]


def test_experiment_b_uses_critique_protocol(workshop):
    workshop[0]["experiment"] = "B"
    router = LocalRouter()
    meeting = run_meeting(workshop, router)
    assert tasks(router)[0] == "plan" and tasks(router)[-1] == "finalize"
    assert meeting["mode"] == "critique" and "scores" not in meeting


@pytest.mark.parametrize("experiment", ["A", "B"])
def test_solo_ignores_critique_panel_mode(workshop, experiment):
    workshop[0]["experiment"] = experiment
    router = LocalRouter()
    meeting = run_meeting(workshop, router, arm="solo", participants=["editor"])
    assert tasks(router) == ["decision"]
    assert router.requests[0]["step_key"] == "arm-solo/ch001/03-decision-editor.json"
    assert set(meeting) == {"brief", "proposals", "reviews", "scores", "objections", "decision"}
    assert meeting["proposals"] == [] and meeting["reviews"] == [] and meeting["scores"] == {}


@pytest.mark.parametrize("experiment", ["A", "B"])
def test_absent_panel_mode_and_explicit_merge_have_identical_protocol(workshop, experiment):
    config = workshop[0]
    config["experiment"] = experiment
    del config["panel_mode"]
    default_router = LocalRouter()
    default = run_meeting(workshop, default_router)
    config["panel_mode"] = "merge"
    merge_router = LocalRouter()
    explicit = run_meeting(workshop, merge_router)
    assert default == explicit
    assert default_router.requests == merge_router.requests
    assert tasks(default_router) == ["proposal"] * 3 + ["critique"] * 3 + ["decision"]
    assert set(default) == {"brief", "proposals", "reviews", "scores", "objections", "decision"}


def test_all_advisor_calls_are_cancelled_and_drained_if_one_fails(workshop):
    started, cancelled, running = set(), set(), set()

    async def broken_advisor(request, _index):
        if FakeLLM.payload(request)["task"] != "critique_plan":
            return None
        role = request["role"]
        started.add(role)
        running.add(role)
        try:
            if role == "plot_architect":
                await asyncio.sleep(0)
                raise StepFailed()
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.add(role)
            raise
        finally:
            running.discard(role)

    router = LocalRouter(FakeLLM(broken_advisor))
    config, compass, bible = workshop

    async def run_before_loop_shutdown():
        with pytest.raises(StepFailed):
            await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                             participants=config["arms"]["panel"])
        assert started == {"plot_architect", "character_advocate", "twist_designer"}
        assert cancelled == {"character_advocate", "twist_designer"}
        assert running == set() and router.active == 0
        assert "finalize" not in tasks(router)

    asyncio.run(run_before_loop_shutdown())


def test_advisor_concurrency_is_limited_to_three(workshop):
    config, compass, bible = workshop
    roles = [role for role, card in AGENTS.items()
             if card["category"] == "deliberation" and role != "editor"]
    config["agents"].update({role: f"fake:{role}" for role in roles})
    router = LocalRouter()
    asyncio.run(deliberate(router, config, compass, bible, chapter=1, arm="panel",
                          participants=roles + ["editor"]))
    assert router.max_active == 3


@pytest.mark.parametrize("panel_mode", [None, "", "other"])
def test_direct_deliberation_rejects_invalid_panel_mode(workshop, panel_mode):
    workshop[0]["panel_mode"] = panel_mode
    router = LocalRouter()
    with pytest.raises(ValueError, match="panel_mode"):
        run_meeting(workshop, router)
    assert router.requests == []
