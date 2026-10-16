"""R1 integration checks for payload parity, review context and report safety."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.context import build_review_bible
from novel.fake_llm import FakeLLM
from novel.pilot import evidence_matches, run_experiment
from novel.report import estimate_report, generate_blind


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("本测试禁止网络和真实客户端")
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)
        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            return original(sock, address)
        monkeypatch.setattr(socket.socket, method, guarded)


def configuration(experiment="A"):
    return json.loads((Path(__file__).parents[1] / f"novel/pilot_configs/exp{experiment}.json").read_text())


def read(path):
    return json.loads(path.read_text())


def payload(path):
    return FakeLLM.payload(read(path))


@pytest.fixture
def source_a(tmp_path):
    out = tmp_path / "A"
    config = configuration()
    assert asyncio.run(run_experiment(config, out, dry_run=True)) == 0
    return out, config


def test_r1_a_all_five_writer_payloads_have_identical_exact_keys(source_a):
    out, config = source_a
    expected = {"task", "chapter", "title", "target_words", "context", "previous_draft",
                "blocking_issues", "revision", "write_attempt", "length_instruction", "length_range"}
    for chapter in range(1, 6):
        drafts = [payload(out / f"arm-{arm}/ch{chapter:03d}/04-write-writer-r0-a0.json")
                  for arm in ("solo", "panel")]
        assert set(drafts[0]) == set(drafts[1]) == expected
        for draft in drafts:
            assert "decision" not in draft and "beat_sheet" not in draft
            assert draft["context"]["compass"]["seed_idea"] == config["seed_idea"]
            assert set(draft["context"]) == set(drafts[0]["context"])


def test_r1_meetings_and_execution_inputs_have_no_duplicate_outer_context(source_a):
    out, config = source_a
    meeting_base = {"task", "chapter", "mode", "brief"}
    stages = {"proposal": set(), "critique": {"proposals", "proposal_ids"},
              "decision": {"proposals", "scores", "objections", "proposal_ids", "objection_ids",
                           "user_notes", "note_ids", "solo", "required_response_ids"}}
    for path in out.glob("arm-*/ch*/*.json"):
        record = read(path)
        if "messages" not in record:
            continue
        data = FakeLLM.payload(record)
        task = data["task"]
        if task in stages:
            assert set(data) == meeting_base | stages[task]
            assert "bible" not in data and "compass" not in data and "arm" not in data
            assert data["brief"]["compass"]["seed_idea"] == config["seed_idea"]
        elif task == "review":
            assert set(data) == {"task", "chapter", "body", "beat_sheet", "bible", "review_round"}
            assert data["bible"]["compass"]["seed_idea"] == config["seed_idea"]
        elif task == "archive":
            assert set(data) == {"task", "chapter", "body", "beat_sheet", "bible"}


def test_r1_c_bad_citations_are_persisted_and_reported_without_stopping(source_a, tmp_path):
    source, _ = source_a
    fake = FakeLLM()
    def unverified_citations(request, index):
        if request["task"] == "corrupt":
            data = fake.default_response(request)
            for item in data["insertions"]:
                item["contradicts"] = "待人工核对"
            return data
    fake.script = unverified_citations
    out = tmp_path / "C"
    assert asyncio.run(run_experiment(configuration("C"), out, dry_run=True, source_run=source, fake=fake)) == 0
    insertions = read(out / "control/insertions.json")
    assert len(insertions) == 3
    assert all(item["citation_check"]["matched_categories"] == [] for item in insertions)
    report = (out / "report.md").read_text()
    assert "插入引文核对记录" in report and "未匹配（仅记录）" in report
    assert all(item["caught_count"] == 3 for item in read(out / "comparison.json"))
    for request in fake.calls:
        if request["task"] == "review":
            data = FakeLLM.payload(request)
            assert set(data) == {"task", "chapter", "body", "beat_sheet", "bible", "review_round"}
            assert data["bible"]["compass"] == read(source / "setup/compass.json")
            assert "insertions" not in data


def test_r1_review_envelope_preserves_canonical_bible_and_compass():
    bible, compass = {"locked": {"title": "设定"}, "version": 1}, {"seed_idea": "原文"}
    before = deepcopy((bible, compass))
    result = build_review_bible(compass, bible)
    assert result["compass"] == compass
    result["locked"]["title"] = "改变"
    result["compass"]["seed_idea"] = "改变"
    assert (bible, compass) == before


def test_r1_failed_step_is_visible_in_manifest_stdout_and_report(tmp_path, capsys):
    fake = FakeLLM({"setup": [RuntimeError("PRIVATE_EXCEPTION_TEXT")]})
    assert asyncio.run(run_experiment(configuration(), tmp_path, dry_run=True, fake=fake)) == 4
    step_key = "setup/steps/00-setup-editor.json"
    assert read(tmp_path / "manifest.json")["failed_step"] == step_key
    assert step_key in capsys.readouterr().out
    assert step_key in (tmp_path / "report.md").read_text()
    step = read(tmp_path / step_key)
    assert "RuntimeError" in step["errors"]
    assert "PRIVATE_EXCEPTION_TEXT" not in json.dumps(step)


def test_r1_unknown_claude_configuration_rejected_before_environment(tmp_path, monkeypatch, capsys):
    value = configuration()
    value["agents"]["editor"] = "anthropic:unknown-claude"
    def forbidden(*args, **kwargs):
        raise AssertionError("未知型号不应检查密钥")
    monkeypatch.setattr("novel.pilot.validate_environment", forbidden)
    assert asyncio.run(run_experiment(value, tmp_path)) == 2
    assert "未知的 Claude 型号，无法确定如何关闭思考" in capsys.readouterr().out
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize("extra_label", ["../escape", "../../escape", "/tmp/novel-r1-escape"])
def test_r1_blind_file_names_are_fixed_even_with_extra_key_labels(tmp_path, extra_label):
    for arm in ("solo", "panel"):
        path = tmp_path / f"arm-{arm}/ch001/chapter.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"# 第1章 {arm}\n正文")
    blind = tmp_path / "blind"
    blind.mkdir()
    (blind / "key.json").write_text(json.dumps({"版本甲": "solo", "版本乙": "panel", extra_label: "solo"}))
    generate_blind(tmp_path)
    assert {path.name for path in blind.iterdir()} == {"key.json", "版本甲.md", "版本乙.md", "阅读说明.md"}
    assert "solo" in (blind / "版本甲.md").read_text()
    assert "panel" in (blind / "版本乙.md").read_text()
    assert not (tmp_path / "escape.md").exists()


@pytest.mark.parametrize("arm", ["../outside", "../../outside", "/tmp/outside"])
def test_r1_blind_mapping_values_cannot_escape_known_arms(tmp_path, arm):
    blind = tmp_path / "blind"
    blind.mkdir()
    (blind / "key.json").write_text(json.dumps({"版本甲": arm, "版本乙": "panel"}))
    with pytest.raises(ValueError, match="盲读映射"):
        generate_blind(tmp_path)


def test_r1_estimate_caveat_and_shared_evidence_normalization(tmp_path):
    assert "Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低" in estimate_report(tmp_path)
    assert evidence_matches("她说：“关键……档案被人改过。”", "她说：「关键...档案被人改过。」")
