"""Offline replay of the live-run failure shape and chapter-level repairs."""

import asyncio
import json
import os
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.fake_llm import FakeLLM
from novel.pilot import run_experiment
from novel.writing import compact_length


# A portable, minimal reproduction: JSON is valid, but the quoted problem was
# cut short and evidence/fix/blocking never appeared. No external run is needed.
INCOMPLETE_REVIEW = '{"issues":[{"category":"continuity","problem":"正文年龄疑似冲突，圣经 age 为 " \t}]}'


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    def forbidden(*args, **kwargs):
        raise AssertionError("第2轮回归禁止真实客户端和网络")
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)
        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            return original(sock, address)
        monkeypatch.setattr(socket.socket, method, guarded)


def configuration(experiment="B", *, small=True):
    value = json.loads((Path(__file__).parents[1] / f"novel/pilot_configs/exp{experiment}.json").read_text())
    value["agents"] = {role: f"fake:{role}" for role in value["agents"]}
    if small:
        value["target"] = {"min_chapters": 1, "max_chapters": 1, "chapter_words": 300}
        value["user_notes"] = {}
    return value


def read(path):
    return json.loads(path.read_text())


def test_live_failure_shape_is_dropped_without_a_review_retry(tmp_path):
    fake = FakeLLM({"review": [INCOMPLETE_REVIEW]})
    assert asyncio.run(run_experiment(configuration(), tmp_path, dry_run=True, fake=fake)) == 0
    step = read(tmp_path / "arm-panel/ch001/05-review-reviewer-r0.json")
    assert step["status"] == "ok" and step["attempts"] == 1
    assert step["result"]["passed"] is True and step["result"]["issues"] == []
    assert step["result"]["dropped_issues"][0]["drop_reason"] == "字段不完整或类型错误"
    assert [message["role"] for message in step["messages"]] == ["system", "user"]
    assert sum(request["task"] == "review" for request in fake.calls) == 1
    assert sum(request["task"] == "write" for request in fake.calls) == 1
    assert read(tmp_path / "manifest.json")["status"] == "completed"


def test_revisit_uses_only_verified_previous_blockers_and_can_finish(tmp_path):
    fake = FakeLLM()
    evidence = "删除倒计时突然跳到六十秒"
    blocker = {"category": "beat_sheet", "problem": "正控：核心节拍需要补足。", "evidence": evidence,
               "fix": "补齐正控节拍。", "blocking": True}
    def scripted(request, index):
        if request["task"] == "review":
            data = FakeLLM.payload(request)
            if data["review_round"] == 0:
                assert "previous_blocking_issues" not in data
                return {"issues": [
                    {"category": "continuity", "problem": "残缺问题"}, blocker,
                    {"category": "style", "problem": "风格建议", "evidence": evidence,
                     "fix": "建议简写", "blocking": True},
                ]}
            assert data["previous_blocking_issues"] == [blocker]
            return {"issues": []}
    fake.script = scripted
    assert asyncio.run(run_experiment(configuration(), tmp_path, dry_run=True, fake=fake)) == 0
    record = read(tmp_path / "arm-panel/ch001/chapter_record.json")
    assert record["review_rounds"] == 2 and record["revision_rounds"] == 1
    assert record["flags"] == []
    assert sum(request["task"] == "write" for request in fake.calls) == 2
    for revision in (0, 1):
        step = read(tmp_path / f"arm-panel/ch001/05-review-reviewer-r{revision}.json")
        assert step["attempts"] == 1 and step["status"] == "ok"


def test_length_retry_persists_actual_count_and_concrete_integer_range(tmp_path):
    value = configuration()
    value["target"]["chapter_words"] = 25
    fake = FakeLLM()
    drafts = []
    def scripted(request, index):
        if request["task"] == "write":
            data = FakeLLM.payload(request)
            assert data["length_range"] == {"min": 15, "max": 40, "target": 25}
            if not drafts:
                body = f"# 第1章 {data['title']}\n" + "甲" * 80
            else:
                assert f"上一稿 {compact_length(drafts[0])} 字" in data["length_instruction"]
                assert "超出" in data["length_instruction"] and "15–40" in data["length_instruction"]
                body = f"# 第1章 {data['title']}\n" + "乙" * 15
            drafts.append(body)
            return body
    fake.script = scripted
    assert asyncio.run(run_experiment(value, tmp_path, dry_run=True, fake=fake)) == 0
    assert len(drafts) == 2
    final = (tmp_path / "arm-panel/ch001/chapter.md").read_text()
    assert 15 <= compact_length(final) <= 40
    assert read(tmp_path / "arm-panel/ch001/flags.json") == []
    repair = FakeLLM.payload(read(tmp_path / "arm-panel/ch001/04-write-writer-r0-a1.json"))
    assert repair["previous_draft"] == drafts[0]
    assert str(compact_length(drafts[0])) in repair["length_instruction"]


def test_experiment_c_stays_single_pass_without_previous_blockers(tmp_path):
    source, out = tmp_path / "A", tmp_path / "C"
    a = configuration("A", small=False)
    a["target"]["chapter_words"] = 300
    assert asyncio.run(run_experiment(a, source, dry_run=True)) == 0
    fake = FakeLLM()
    assert asyncio.run(run_experiment(configuration("C", small=False), out,
                                      source_run=source, dry_run=True, fake=fake)) == 0
    reviews = [FakeLLM.payload(request) for request in fake.calls if request["task"] == "review"]
    assert len(reviews) == 4
    for data in reviews:
        assert data["review_round"] == 0
        assert "previous_blocking_issues" not in data
        assert set(data) == {"task", "chapter", "body", "beat_sheet", "bible", "review_round"}
    assert all(item["caught_count"] == 3 and item["false_positives"] == 0
               for item in read(out / "comparison.json"))
