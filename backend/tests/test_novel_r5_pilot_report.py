"""Portable end-to-end coverage for critique mode and chapter diagnostics."""

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.fake_llm import FakeLLM
from novel.pilot import run_experiment, validate_config
from novel.report import generate_report


RULE = "每章最多安排一个关键揭示（主线谜底或核心身份的实质推进）；其余新发现只能是线索层面的。"
MERGE_KEYS = {"brief", "proposals", "reviews", "scores", "objections", "decision"}
WRITER_KEYS = {"task", "chapter", "title", "target_words", "context", "previous_draft",
               "blocking_issues", "revision", "write_attempt", "length_instruction", "length_range"}


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    monkeypatch.setattr(os, "environ", {})

    def forbidden(*args, **kwargs):
        raise AssertionError("R5 integration forbids real clients and networking")

    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)

        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            return original(sock, address)

        monkeypatch.setattr(socket.socket, method, guarded)


def config(name="A2"):
    path = Path(__file__).parents[1] / "novel/pilot_configs" / f"exp{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(value, out, *, fake=None):
    return asyncio.run(run_experiment(value, out, dry_run=True, fake=fake))


@pytest.fixture
def experiment_a2(tmp_path):
    value, fake = config(), FakeLLM()
    assert run(value, tmp_path, fake=fake) == 0
    return tmp_path, value, fake


def test_a2_five_chapters_use_plan_consultants_finalize_and_keep_solo(experiment_a2):
    out, value, fake = experiment_a2
    roles = [role for role in value["arms"]["panel"] if role != "editor"]
    expected_critique = {"mode", "brief", "plan", "critiques", "objections", "decision"}
    for chapter in range(1, 6):
        panel = out / f"arm-panel/ch{chapter:03d}"
        names = {p.name for p in panel.glob("*.json")}
        assert {"01-plan-editor.json", "03-finalize-editor.json"} <= names
        assert {f"02-critique-plan-{role}.json" for role in roles} <= names
        assert not any("proposal" in name or name.startswith("02-critique-") and "-plan-" not in name
                       for name in names)
        meeting = read(panel / "chapter_record.json")["meeting"]
        assert set(meeting) == expected_critique
        assert meeting["mode"] == "critique"
        assert [item["author"] for item in meeting["critiques"]] == roles
        assert meeting["plan"]["chosen_proposal_ids"] == []
        assert meeting["decision"]["chosen_proposal_ids"] == []
        ids = [item["id"] for item in meeting["objections"]]
        assert ({item["objection_id"] for item in meeting["decision"]["objection_responses"]}
                | {item["alternative_id"] for item in meeting["decision"]["alternative_responses"]}) == set(ids)
        assert any(key.startswith("A") for key in ids)
        solo = out / f"arm-solo/ch{chapter:03d}"
        assert (solo / "03-decision-editor.json").is_file()
        assert not (solo / "01-plan-editor.json").exists()
        assert set(read(solo / "chapter_record.json")["meeting"]) == MERGE_KEYS
    assert not any(call["task"] in {"proposal", "critique"} for call in fake.calls)
    assert read(out / "manifest.json")["status"] == "completed"
    assert set(read(out / "blind/key.json").values()) == {"solo", "panel"}
    for name in ("版本甲.md", "版本乙.md"):
        body = (out / "blind" / name).read_text(encoding="utf-8")
        assert body.count("# 第") == 5
        assert "推演模式" not in body and "主编回应" not in body


def test_a2_writer_payload_keys_are_identical_for_both_arms(experiment_a2):
    _out, _value, fake = experiment_a2
    writers = [call for call in fake.calls if call["task"] == "write"]
    assert len(writers) == 10
    for call in writers:
        payload = FakeLLM.payload(call)
        assert set(payload) == WRITER_KEYS
        assert {"plan", "critiques", "objections", "decision", "panel_mode"}.isdisjoint(payload)
        assert payload["context"]["beat_sheet"]


def test_a2_all_editor_cards_have_the_exact_one_reveal_rule(experiment_a2):
    _out, _value, fake = experiment_a2
    expected = {("solo", "decision"), ("panel", "plan"), ("panel", "finalize")}
    observed = set()
    for call in fake.calls:
        if (call["arm"], call["task"]) in expected:
            observed.add((call["arm"], call["task"]))
            assert RULE in call["messages"][0]["content"]
    assert observed == expected


@pytest.mark.parametrize("panel_mode", [None, "", "unknown", True, [], {}])
def test_invalid_panel_modes_are_rejected_without_mutating_config(panel_mode):
    value = config("A")
    value["panel_mode"] = panel_mode
    original = deepcopy(value)
    with pytest.raises(ValueError, match="panel_mode"):
        validate_config(value)
    assert value == original


@pytest.mark.parametrize("experiment", ["A", "B"])
def test_default_and_explicit_merge_preserve_step_keys_and_meeting_structure(tmp_path, experiment):
    value = config(experiment)
    explicit = deepcopy(value)
    explicit["panel_mode"] = "merge"
    first, second = tmp_path / "default", tmp_path / "explicit"
    assert run(value, first) == run(explicit, second) == 0

    def steps(out):
        return {str(p.relative_to(out)) for p in out.rglob("*.json")
                if isinstance(read(p), dict) and "step_key" in read(p)}

    assert steps(first) == steps(second)
    for record_path in first.glob("arm-*/ch*/chapter_record.json"):
        meeting = read(record_path)["meeting"]
        assert set(meeting) == MERGE_KEYS
        assert meeting == read(second / record_path.relative_to(first))["meeting"]
        folder = record_path.parent
        assert (folder / "03-decision-editor.json").is_file()
        assert not (folder / "01-plan-editor.json").exists()
        expected = {"03-decision-editor.json", "04-write-writer-r0-a0.json",
                    "05-review-reviewer-r0.json", "06-archive-archivist.json"}
        if folder.parent.name == "arm-panel":
            roles = ["plot_architect", "character_advocate", "twist_designer"]
            if experiment == "B":
                roles.append("pacing_advisor")
            expected |= {f"01-proposal-{role}.json" for role in roles}
            expected |= {f"02-critique-{role}.json" for role in roles}
        actual = {p.name for p in folder.glob("*.json") if "step_key" in read(p)}
        assert actual == expected
    assert "panel_mode" not in value


@pytest.mark.parametrize("review_kind,expected_dropped,expected_defaulted,degraded", [
    ("defaulted", 1, 2, False), ("degraded", 1, 0, True), ("empty", 0, 0, False),
])
def test_review_diagnostics_are_saved_and_reported_for_each_arm(
    tmp_path, review_kind, expected_dropped, expected_defaulted, degraded,
):
    value = config()
    value["chapters_per_arm"] = 1
    fake = FakeLLM()

    def script(request, _index):
        if request["task"] != "review":
            return None
        if review_kind == "empty":
            return {"issues": []}
        incomplete = {"category": "continuity", "problem": "缺少其他必需字段"}
        if review_kind == "degraded":
            return {"issues": [incomplete]}
        body = FakeLLM.payload(request)["body"]
        evidence = next(line for line in body.splitlines()[1:] if line.strip())[:12]
        missing = {"category": "continuity", "problem": "本地非阻断诊断",
                   "evidence": evidence, "fix": "记录即可"}
        return {"issues": [missing, {**missing, "blocking": None}, incomplete]}

    fake.script = script
    assert run(value, tmp_path, fake=fake) == 0
    for arm in ("solo", "panel"):
        record = read(tmp_path / f"arm-{arm}/ch001/chapter_record.json")
        assert record["review_dropped_issues"] == expected_dropped
        assert record["review_blocking_defaulted"] == expected_defaulted
        assert ("review_degraded" in record["flags"]) is degraded
        assert record["review_rounds"] == 1 and record["revision_rounds"] == 0
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert text.count(f"被丢弃的 issue 条数：{expected_dropped}；blocking_defaulted 条数：{expected_defaulted}") == 2


def test_critique_report_displays_plan_severity_alternative_replies_and_changes(tmp_path):
    value = config()
    value["chapters_per_arm"] = 1
    fake = FakeLLM()

    def script(request, _index):
        if request["task"] == "finalize":
            result = fake.default_response(request)
            result["beat_sheet"]["ending_hook"] = "门外出现一份此前未见的记录。"
            return result

    fake.script = script
    assert run(value, tmp_path, fake=fake) == 0
    report = (tmp_path / "report.md").read_text(encoding="utf-8").split("## arm-solo", 1)[0]
    meeting = read(tmp_path / "arm-panel/ch001/chapter_record.json")["meeting"]
    assert "推演模式：critique" in report and "初案要点：" in report
    assert meeting["plan"]["beat_sheet"]["chapter_goal"] in report
    assert "定稿相对初案的改动：" in report
    assert "| ending_hook | 是 |" in report
    for item in meeting["objections"]:
        assert item["id"] in report
        if item["id"].startswith("A"):
            assert "替代走向" in report and item["alternative"] in report
        else:
            assert item["severity"] in report and item["problem"] in report
            assert item["suggestion"] in report
    for item in meeting["decision"]["objection_responses"]:
        assert item["response"] in report
    assert "均分" not in report and "选中提案" not in report


def test_legacy_records_without_diagnostic_counts_still_generate_report(tmp_path):
    value = config("A")
    value["chapters_per_arm"] = 1
    assert run(value, tmp_path) == 0
    for path in tmp_path.glob("arm-*/ch*/chapter_record.json"):
        record = read(path)
        record.pop("review_dropped_issues")
        record.pop("review_blocking_defaulted")
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    text = generate_report(tmp_path)
    assert text.count("被丢弃的 issue 条数：0；blocking_defaulted 条数：0") == 2
