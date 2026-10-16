"""Portable offline resume coverage for stale decision resolution IDs."""

import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.fake_llm import FakeLLM
from novel.pilot import run_experiment


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    monkeypatch.setattr(os, "environ", {})

    def forbidden(*args, **kwargs):
        raise AssertionError("第3轮回归禁止真实客户端和网络")

    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)

        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            return original(sock, address)

        monkeypatch.setattr(socket.socket, method, guarded)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def configuration():
    value = read(Path(__file__).parents[1] / "novel/pilot_configs/expB.json")
    value["agents"] = {role: f"fake:{role}" for role in value["agents"]}
    value["target"] = {"min_chapters": 2, "max_chapters": 2, "chapter_words": 300}
    value["user_notes"] = {}
    return value


def scripted_model(*, duplicate_final):
    fake = FakeLLM()

    def scripted(request, index):
        task, chapter = request["task"], request["chapter"]
        if task == "setup":
            result = fake.default_response(request)
            result["initial_foreshadowing"].append({
                "description": "第一章核实后即可回收的次要线索", "importance": "minor",
            })
            return result
        if task == "decision":
            result = fake.default_response(request)
            if chapter == 1:
                result["beat_sheet"]["foreshadowing_resolve"] = ["F002"]
            else:
                assert result["ending_status"] == "end"
                result["beat_sheet"]["foreshadowing_resolve"] = (
                    ["F001", "F002", "F002", "F999"] if duplicate_final
                    else ["F001", "F002", "F999"]
                )
            return result

    fake.script = scripted
    return fake


def test_failed_final_decision_resumes_with_pruned_ids_and_persisted_warnings(tmp_path):
    config = configuration()
    first = scripted_model(duplicate_final=True)
    assert asyncio.run(run_experiment(config, tmp_path, dry_run=True, fake=first)) == 4
    chapter = tmp_path / "arm-panel/ch002"
    assert read(tmp_path / "manifest.json")["status"] == "decision_invalid"
    failed = read(chapter / "03-decision-editor.json")
    assert failed["status"] == "decision_invalid" and failed["attempts"] == 2
    assert not (chapter / "chapter.md").exists()
    assert not any(call["task"] == "write" and call["chapter"] == 2 for call in first.calls)
    completed = {
        path: path.read_bytes() for path in tmp_path.rglob("*.json")
        if isinstance(read(path), dict) and read(path).get("status") == "ok"
    }

    resumed = scripted_model(duplicate_final=False)
    assert asyncio.run(run_experiment(config, tmp_path, dry_run=True, fake=resumed)) == 0
    assert Counter(call["task"] for call in resumed.calls) == {
        "decision": 1, "write": 1, "review": 1, "archive": 1,
    }
    assert all(call["chapter"] == 2 for call in resumed.calls)
    assert all(path.read_bytes() == data for path, data in completed.items())

    expected = [
        {"field": "beat_sheet.foreshadowing_resolve", "id": "F002", "reason": "已回收"},
        {"field": "beat_sheet.foreshadowing_resolve", "id": "F999", "reason": "不存在"},
    ]
    step = read(chapter / "03-decision-editor.json")
    assert step["status"] == "ok" and step["attempts"] == 1
    assert json.loads(step["raw_response"])["beat_sheet"]["foreshadowing_resolve"] == [
        "F001", "F002", "F999",
    ]
    assert step["result"]["beat_sheet"]["foreshadowing_resolve"] == ["F001"]
    assert step["result"]["warnings"] == expected
    record = read(chapter / "chapter_record.json")
    assert record["meeting"]["decision"]["warnings"] == expected
    for call in resumed.calls:
        payload = FakeLLM.payload(call)
        if call["task"] == "write":
            assert payload["context"]["beat_sheet"]["foreshadowing_resolve"] == ["F001"]
        elif call["task"] in ("review", "archive"):
            assert payload["beat_sheet"]["foreshadowing_resolve"] == ["F001"]
    assert [item["id"] for item in record["archive"]["foreshadowing_resolved"]] == ["F001"]
    bible = read(chapter / "bible_v3.json")
    assert {item["id"]: item["status"] for item in bible["dynamic"]["foreshadowing"]} == {
        "F001": "resolved", "F002": "resolved",
    }
    manifest = read(tmp_path / "manifest.json")
    assert manifest["status"] == "completed"
    assert manifest["completion"]["open_major_foreshadowing"] == []
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    second_summary = report.split("## arm-panel 第 2 章", 1)[1].split("## 完结指标", 1)[0]
    assert "beat_sheet.foreshadowing_resolve" in second_summary
    assert "F002" in second_summary and "已回收" in second_summary
    assert "F999" in second_summary and "不存在" in second_summary
