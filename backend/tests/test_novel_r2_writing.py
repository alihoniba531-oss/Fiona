"""Offline regressions for concrete lengths and focused review revisions."""

import asyncio
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.bible import build_setup
from novel.fake_llm import FakeLLM
from novel.schemas import parse_json
import novel.writing as writing


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("R2 写作测试禁止网络及真实提供方")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    for name in ("connect", "connect_ex"):
        original = getattr(socket.socket, name)

        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            return original(sock, address)

        monkeypatch.setattr(socket.socket, name, guarded)


class CaptureRouter:
    def __init__(self, script=None):
        self.fake = FakeLLM(script)
        self.requests = []

    async def call(self, **request):
        self.requests.append(deepcopy({key: value for key, value in request.items()
                                       if key != "validator"}))
        raw, _usage = await self.fake(request)
        data = raw if request["output"] == "markdown" else parse_json(raw)
        return request["validator"](data)

    def payloads(self, task):
        return [FakeLLM.payload(request) for request in self.requests
                if FakeLLM.payload(request)["task"] == task]


@pytest.fixture
def workshop():
    value = json.loads((Path(__file__).parents[1] / "novel/pilot_configs/expA.json").read_text())
    value["target"]["chapter_words"] = 300
    value["agents"] = {role: f"fake:{role}" for role in value["agents"]}
    fake = FakeLLM()
    compass, bible = build_setup(fake.default_response({"task": "setup"}), value)
    meeting = {"decision": fake.default_response({"payload": {
        "task": "decision", "chapter": 1,
        "brief": {"compass": compass, **bible}}})}
    return value, compass, bible, meeting


def run_chapter(workshop, router):
    config, compass, bible, meeting = workshop
    return asyncio.run(writing.write_chapter(
        router, config, compass, bible, meeting, chapter=1, arm="panel"))


def draft_with_length(payload, length):
    opening = f"# 第{payload['chapter']}章 {payload['title']}\n\n人物站在门前核对记录。\n"
    assert writing.compact_length(opening) <= length
    return opening + "字" * (length - writing.compact_length(opening))


@pytest.mark.parametrize("words", [
    1, 2, 3, 4, 5, 6, 7, 99, 100, 101, 1499, 1500, 1501,
    2 ** 53 - 1, 2 ** 53, 2 ** 53 + 1,
])
def test_each_writer_payload_has_exact_integer_length_range(workshop, words):
    workshop[0]["target"]["chapter_words"] = words

    def script(request, _index):
        if FakeLLM.payload(request)["task"] == "write":
            return "人物站在门前核对记录。"

    router = CaptureRouter(script)
    result = run_chapter(workshop, router)
    expected = {"min": math.ceil(Fraction(3 * words, 5)),
                "max": math.floor(Fraction(8 * words, 5)), "target": words}
    assert router.payloads("write")
    for payload in router.payloads("write"):
        assert payload["length_range"] == expected
        assert all(type(number) is int for number in payload["length_range"].values())
    assert len(router.payloads("archive")) == 1
    assert result["bible"]["version"] == 2


@pytest.mark.parametrize("words", [101, 102, 103, 104, 105, 1500])
@pytest.mark.parametrize("position", ["min", "max", "below", "above"])
def test_inclusive_integer_boundaries_control_rewrite_and_final_flag(workshop, words, position):
    workshop[0]["target"]["chapter_words"] = words
    lower, upper = math.ceil(Fraction(3 * words, 5)), math.floor(Fraction(8 * words, 5))
    first_length = {"min": lower, "max": upper,
                    "below": lower - 1, "above": upper + 1}[position]

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return draft_with_length(payload, first_length if payload["write_attempt"] == 0 else words)

    router = CaptureRouter(script)
    result = run_chapter(workshop, router)
    writes = router.payloads("write")
    needs_rewrite = position in ("below", "above")
    assert len(writes) == (2 if needs_rewrite else 1)
    assert writes[0]["length_instruction"] == ""
    assert result["flags"] == []
    if needs_rewrite:
        direction = "不足" if position == "below" else "超出"
        assert f"上一稿 {first_length} 字，{direction}范围 {lower}–{upper}" in writes[1]["length_instruction"]
        assert first_length == writing.compact_length(writes[1]["previous_draft"])
        assert writes[1]["length_range"] == writes[0]["length_range"]
        assert writing.compact_length(result["body"]) == words
    else:
        assert writing.compact_length(result["body"]) == first_length
    assert len(router.payloads("archive")) == 1


@pytest.mark.parametrize("position", ["below", "above"])
def test_second_out_of_range_draft_is_flagged_and_still_archived(workshop, position):
    words = workshop[0]["target"]["chapter_words"]
    length = (3 * words + 4) // 5 - 1 if position == "below" else 8 * words // 5 + 1

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return draft_with_length(payload, length)

    router = CaptureRouter(script)
    result = run_chapter(workshop, router)
    assert len(router.payloads("write")) == 2
    assert result["flags"] == ["length_out_of_range"]
    assert len(router.payloads("review")) == len(router.payloads("archive")) == 1
    assert result["bible"]["version"] == 2


def issue(problem, *, blocking=True, category="continuity", evidence="人物站在门前核对记录"):
    return {"category": category, "problem": problem, "evidence": evidence,
            "fix": "按锁定事实修正人物位置。", "blocking": blocking,
            "details": {"sources": [problem]}}


def test_review_revisions_receive_only_previous_retained_blocking_issues(workshop, monkeypatch):
    captured = []
    original_messages_for = writing.messages_for

    def capture(role, payload, **kwargs):
        captured.append((role, payload))
        return original_messages_for(role, payload, **kwargs)

    monkeypatch.setattr(writing, "messages_for", capture)

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return draft_with_length(payload, payload["target_words"])
        if payload["task"] == "review":
            number = payload["review_round"]
            return {"issues": [
                issue(f"阻断-{number}"), issue("建议", blocking=False),
                issue("措辞", category="style"),
                issue("证据不在正文", evidence="这句话根本没有写在正文里"),
            ]}

    router = CaptureRouter(script)
    result = run_chapter(workshop, router)
    reviews, writes = router.payloads("review"), router.payloads("write")
    assert [payload["review_round"] for payload in reviews] == [0, 1, 2]
    assert "previous_blocking_issues" not in reviews[0]
    for number in (1, 2):
        expected = [item for item in result["reviews"][number - 1]["issues"] if item["blocking"]]
        assert reviews[number]["previous_blocking_issues"] == expected
        assert [item["problem"] for item in expected] == [f"阻断-{number - 1}"]
    assert result["flags"] == ["review_unresolved"]
    assert result["review_rounds"] == 3 and result["revision_rounds"] == 2
    assert len(writes) == 3 and all(payload["write_attempt"] == 0 for payload in writes)
    assert all(payload["length_instruction"] == "" for payload in writes)
    assert all(payload["length_range"] == {"min": 180, "max": 480, "target": 300}
               for payload in writes)
    assert len(router.payloads("archive")) == 1 and result["bible"]["version"] == 2

    # Capture objects before JSON serialization so this checks the explicit
    # copy between the writer's retained list and the next review's list.
    reviewer_one = next(payload for role, payload in captured
                        if role == "reviewer" and payload["review_round"] == 1)
    writer_one = next(payload for role, payload in captured
                     if role == "writer" and payload["revision"] == 1)
    assert reviewer_one["previous_blocking_issues"] is not writer_one["blocking_issues"]
    reviewer_one["previous_blocking_issues"][0]["details"]["sources"].append("mutated")
    assert writer_one["blocking_issues"][0]["details"]["sources"] == ["阻断-0"]
    assert result["reviews"][0]["issues"][0]["details"]["sources"] == ["阻断-0"]


def test_resolved_review_stops_revisions_and_archives(workshop):
    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return draft_with_length(payload, payload["target_words"])
        if payload["task"] == "review":
            return {"issues": [issue("首轮位置矛盾")] if payload["review_round"] == 0 else []}

    router = CaptureRouter(script)
    result = run_chapter(workshop, router)
    assert len(router.payloads("write")) == len(router.payloads("review")) == 2
    assert result["revision_rounds"] == 1 and result["flags"] == []
    assert router.payloads("review")[1]["previous_blocking_issues"] == result["reviews"][0]["issues"]
    assert len(router.payloads("archive")) == 1 and result["bible"]["version"] == 2


def test_nonblocking_or_unverifiable_issues_do_not_start_a_revision(workshop):
    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return draft_with_length(payload, payload["target_words"])
        if payload["task"] == "review":
            return {"issues": [issue("仅建议", blocking=False),
                               issue("证据缺失", evidence="没有出现在正文的引文")]}

    router = CaptureRouter(script)
    result = run_chapter(workshop, router)
    assert len(router.payloads("write")) == len(router.payloads("review")) == 1
    assert "previous_blocking_issues" not in router.payloads("review")[0]
    assert result["revision_rounds"] == 0 and result["flags"] == []
    assert len(router.payloads("archive")) == 1 and result["bible"]["version"] == 2
