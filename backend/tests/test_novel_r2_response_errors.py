"""Offline regressions for actionable, content-free response ID diagnostics."""

import asyncio
from copy import deepcopy
import json
import socket

import pytest

from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.run_store import RunStore
from novel.schemas import ValidationError, validate_decision


SUMMARY = "本次下发的每条意见或留言必须恰好回应一次，不得出现其他 ID"
CONTENT = "PRIVATE_RESPONSE_CONTENT_SENTINEL"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("response ID regressions must stay offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden)


def _decision():
    return {
        "chosen_proposal_ids": [], "merge_note": "沿证据追查", "objection_responses": [],
        "user_note_responses": [], "rationale": "动机与因果衔接",
        "beat_sheet": {
            "title": "第二份委托", "chapter_goal": "找到联系人", "advances_threads": ["T1"],
            "characters": ["C1"], "scenes": [{"location": "机房", "summary": "收到消息"}],
            "beats": ["收到证据", "检验消息", "决定赴约"], "opening_hook": "陌生号码来电",
            "ending_hook": "门外有人", "foreshadowing_plant": [], "foreshadowing_resolve": [],
        },
        "ending_status": "continue", "closing_chapters_left": 0, "unresolved_major_handling": [],
    }


def _response(identifier, *, notes=False):
    result = {"note_id" if notes else "objection_id": identifier, "response": CONTENT}
    if notes:
        result["adopted"] = False
    return result


def _validate(data, *, objection_ids=(), note_ids=()):
    return validate_decision(
        data, compass={"main_threads": [{"id": "T1"}], "target": {"min_chapters": 2, "max_chapters": 3}},
        bible={"locked": {"characters": [{"id": "C1"}], "adaptation": {"max_scenes_per_chapter": 3}},
               "dynamic": {"foreshadowing": []}},
        chapter=1, mode="normal", proposal_ids=(), objection_ids=objection_ids, note_ids=note_ids, solo=True,
    )


def _errors(allowed, seen, *, notes=False):
    data = _decision()
    field = "user_note_responses" if notes else "objection_responses"
    data[field] = [_response(identifier, notes=notes) for identifier in seen]
    before = deepcopy(data)
    with pytest.raises(ValidationError) as caught:
        _validate(data, **{"note_ids" if notes else "objection_ids": allowed})
    assert data == before
    assert CONTENT not in str(caught.value)
    return caught.value.errors


@pytest.mark.parametrize("notes,prefix", [(False, "O"), (True, "N")])
@pytest.mark.parametrize("kind", ["missing", "extra", "duplicate"])
def test_response_error_names_exact_missing_extra_and_duplicate_id(notes, prefix, kind):
    if kind == "missing":
        allowed, seen, detail = [prefix + "2", prefix + "10"], [prefix + "2"], "缺少：" + prefix + "10"
    elif kind == "extra":
        allowed, seen, detail = [prefix + "2"], [prefix + "2", prefix + "10"], "多出：" + prefix + "10"
    else:
        allowed, seen, detail = [prefix + "2"], [prefix + "2", prefix + "2"], "重复：" + prefix + "2"
    path = "decision.user_note_responses" if notes else "decision.objection_responses"
    assert _errors(allowed, seen, notes=notes) == [path + "：" + SUMMARY, path + "：" + detail]


@pytest.mark.parametrize("notes,allowed,seen,details", [
    (False, ["N10", "A10", "O10", "O1", "N2", "A2", "O2"],
     ["N12", "O1", "A3", "O1", "O11", "A3", "N3"],
     ["缺少：O2、O10、A2、A10、N2、N10", "多出：O11、A3、N3、N12", "重复：O1、A3"]),
    (True, ["N10", "N1", "N2"], ["N12", "N1", "N3", "N1", "N3"],
     ["缺少：N2、N10", "多出：N3、N12", "重复：N1、N3"]),
])
def test_mixed_response_errors_keep_summary_first_and_ids_in_natural_order(notes, allowed, seen, details):
    path = "decision.user_note_responses" if notes else "decision.objection_responses"
    expected = [path + "：" + SUMMARY, *[path + "：" + detail for detail in details]]
    assert _errors(allowed, seen, notes=notes) == expected
    assert _errors(list(reversed(allowed)), list(reversed(seen)), notes=notes) == expected


@pytest.mark.parametrize("notes", [False, True])
@pytest.mark.parametrize("malicious_id", [
    CONTENT, "O3\n" + CONTENT, "O3；" + CONTENT, "O" + "9" * 200,
    {"id": CONTENT}, [CONTENT], None, True, 3,
])
def test_malformed_response_ids_are_rejected_without_echoing_content(notes, malicious_id):
    expected = "N1" if notes else "O1"
    errors = _errors([expected], [malicious_id, malicious_id], notes=notes)
    text = "；".join(errors)
    path = "decision.user_note_responses" if notes else "decision.objection_responses"
    assert errors[0] == path + "：" + SUMMARY
    assert "缺少：" + expected in text
    assert CONTENT not in text
    assert "O" + "9" * 200 not in text
    # Malformed IDs remain validation failures, but cannot turn into echoed prose.
    assert "多出：" not in text and "重复：" not in text


@pytest.mark.parametrize("identifier", ["O1", "custom_identifier", "O" + "9" * 40])
def test_diagnostic_filter_does_not_change_accepted_response_ids(identifier):
    data = _decision()
    data["objection_responses"] = [_response(identifier)]
    assert _validate(data, objection_ids=[identifier])["objection_responses"] == data["objection_responses"]


def test_actual_router_repair_receives_specific_ids_and_succeeds_on_second_attempt(tmp_path):
    broken = _decision()
    broken["objection_responses"] = [_response("O1"), _response("O1"), _response("O9")]
    broken["user_note_responses"] = [_response("N2", notes=True)]
    fixed = _decision()
    fixed["objection_responses"] = [_response(identifier) for identifier in ("O1", "O2", "A1")]
    fixed["user_note_responses"] = [_response("N1", notes=True)]
    def script(request, index):
        if index == 1:
            return broken
        repair = json.loads(request["messages"][-1]["content"])
        errors = repair["校验错误"]
        assert errors == [
            "decision.objection_responses：" + SUMMARY,
            "decision.objection_responses：缺少：O2、A1",
            "decision.objection_responses：多出：O9",
            "decision.objection_responses：重复：O1",
            "decision.user_note_responses：" + SUMMARY,
            "decision.user_note_responses：缺少：N1",
            "decision.user_note_responses：多出：N2",
        ]
        assert CONTENT not in json.dumps(errors)
        return fixed
    fake = FakeLLM(script)
    store = RunStore(tmp_path, {})
    result = asyncio.run(LLMRouter(store, fake=fake).call(
        step_key="chapter/03-finalize-editor.json", role="editor", model="fake:offline", max_tokens=1000,
        messages=[{"role": "system", "content": "逐条回应指定 ID。"},
                  {"role": "user", "content": json.dumps({"task": "finalize"})}],
        validator=lambda value: _validate(value, objection_ids=["O1", "O2", "A1"], note_ids=["N1"]),
    ))
    assert fake.call_count == 2
    assert result["objection_responses"] == fixed["objection_responses"]
    saved = store.read_step("chapter/03-finalize-editor.json")
    assert saved["status"] == "ok" and saved["attempts"] == 2
