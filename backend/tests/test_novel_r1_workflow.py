"""Round-one workflow regressions: scoped inputs, normalization and role direction."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.agent_pool import AGENTS, INJECTION_GUARD, get_agent
from novel.bible import build_setup
from novel.deliberation import deliberate
from novel.fake_llm import FakeLLM
from novel.pilot import run_experiment
from novel.schemas import ValidationError, compact, parse_json, validate_insertions
from novel.writing import normalize_manuscript, write_chapter


@pytest.fixture(autouse=True)
def forbid_provider_connections(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("返修测试禁止联网和真实提供方客户端")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", blocked)
    monkeypatch.setattr(openai, "AsyncOpenAI", blocked)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)

        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                blocked()
            return original(sock, address)

        monkeypatch.setattr(socket.socket, method, guarded)


class CaptureRouter:
    def __init__(self, fake=None):
        self.fake = fake or FakeLLM()
        self.requests = []

    async def call(self, **request):
        self.requests.append(deepcopy({key: value for key, value in request.items()
                                       if key != "validator"}))
        raw, _usage = await self.fake(request)
        value = raw if request.get("output") == "markdown" else parse_json(raw)
        return request["validator"](value)


def config():
    return json.loads((Path(__file__).parents[1] / "novel/pilot_configs/expA.json").read_text())


@pytest.fixture
def workshop():
    value = config()
    value["target"] = {"min_chapters": 8, "max_chapters": 12, "chapter_words": 100}
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), value)
    return value, compass, bible


def meet(workshop, router, arm="panel"):
    value, compass, bible = workshop
    return asyncio.run(deliberate(router, value, compass, bible, chapter=1, arm=arm,
                                  participants=value["arms"][arm]))


@pytest.mark.parametrize("task, extras", [
    ("proposal", set()),
    ("critique", {"proposals", "proposal_ids"}),
    ("decision", {"proposals", "scores", "objections", "proposal_ids", "objection_ids",
                  "user_notes", "note_ids", "solo", "required_response_ids"}),
])
def test_deliberation_payload_has_one_brief_and_only_phase_fields(workshop, task, extras):
    router = CaptureRouter()
    meet(workshop, router)
    selected = [FakeLLM.payload(request) for request in router.requests
                if FakeLLM.payload(request)["task"] == task]
    assert selected
    for payload in selected:
        assert set(payload) == {"task", "chapter", "mode", "brief"} | extras
        assert not {"bible", "compass", "arm"} & set(payload)
        assert payload["brief"]["locked"] == workshop[2]["locked"]
        assert payload["brief"]["compass"]["seed_idea"] == workshop[0]["seed_idea"]


def test_a_five_chapter_writer_step_keys_match_across_arms(tmp_path):
    value = config()
    fake = FakeLLM()
    assert asyncio.run(run_experiment(value, tmp_path, dry_run=True, fake=fake)) == 0
    expected = {"task", "chapter", "title", "target_words", "context", "previous_draft",
                "blocking_issues", "revision", "write_attempt", "length_instruction", "length_range"}
    for chapter in range(1, 6):
        payloads = []
        for arm in ("solo", "panel"):
            step_files = list((tmp_path / f"arm-{arm}/ch{chapter:03d}").glob("04-write-*.json"))
            assert step_files
            for filename in step_files:
                step = json.loads(filename.read_text())
                payload = FakeLLM.payload(step)
                assert set(payload) == expected
                assert "decision" not in payload and "beat_sheet" not in payload
                assert payload["context"]["beat_sheet"]
                payloads.append(payload)
        assert set(payloads[0]) == set(payloads[-1])


@pytest.mark.parametrize("task, expected", [
    ("write", {"task", "chapter", "title", "target_words", "context", "previous_draft",
               "blocking_issues", "revision", "write_attempt", "length_instruction", "length_range"}),
    ("review", {"task", "chapter", "body", "beat_sheet", "bible", "review_round"}),
    ("archive", {"task", "chapter", "body", "beat_sheet", "bible"}),
])
def test_execution_payloads_have_only_the_required_keys(workshop, task, expected):
    router = CaptureRouter()
    meeting = meet(workshop, router)
    value, compass, bible = workshop
    original = deepcopy(bible)
    asyncio.run(write_chapter(router, value, compass, bible, meeting, chapter=1, arm="panel"))
    selected = [FakeLLM.payload(request) for request in router.requests
                if FakeLLM.payload(request)["task"] == task]
    assert selected
    for payload in selected:
        assert set(payload) == expected
        if task == "review":
            assert payload["bible"]["compass"] == compass
        elif task == "archive":
            assert payload["bible"] == bible
        else:
            assert payload["context"]["compass"]["seed_idea"] == value["seed_idea"]
    assert bible == original


def test_fake_reads_custom_ids_and_open_major_facts_from_brief():
    payload = {"task": "decision", "chapter": 12, "mode": "final", "solo": True,
               "brief": {"compass": {"main_threads": [{"id": "T77"}]},
                         "locked": {"characters": [{"id": "C88"}]},
                         "dynamic": {"foreshadowing": [{"id": "F077", "importance": "major",
                                                         "status": "open"}]}}}
    result = FakeLLM().default_response({"payload": payload})
    assert result["beat_sheet"]["advances_threads"] == ["T77"]
    assert result["beat_sheet"]["characters"] == ["C88"]
    assert result["beat_sheet"]["foreshadowing_resolve"] == ["F077"]


def test_default_corrupter_state_citation_has_eight_character_fact_overlap(workshop):
    fake = FakeLLM()
    bible = workshop[2]
    body = fake.default_response({"payload": {"task": "write", "chapter": 4,
                                              "title": "核验", "target_words": 300}})
    insertions = fake.default_response({"payload": {"task": "corrupt", "chapter": 4,
                                                    "body": body, "bible": bible}})
    checked = validate_insertions(insertions, body, bible)["insertions"][1]
    assert "当前位置或伤病" in checked["citation_check"]["matched_categories"]
    citation = compact(checked["contradicts"])
    facts = [compact(state[field]) for state in bible["dynamic"]["character_states"].values()
             for field in ("location", "condition")]
    assert any(citation[start:start + 8] in fact for start in range(len(citation) - 7)
               for fact in facts)


@pytest.mark.parametrize("body, expected_tail", [
    ("```markdown\n# 第1章 旧标题\n正文\n```", "正文"),
    ("```\n# 第1章 旧标题\n正文\n```", "正文"),
    ("\n\n# 第1章 旧标题\n正文\n", "正文"),
    ("## 第 1 章：旧标题\n正文", "正文"),
    ("###第1章:旧标题\n正文", "正文"),
    ("# 第1章\n正文", "正文"),
    ("正文第一句。\n正文第二句。", "正文第一句。\n正文第二句。"),
    ("第1章 旧标题\n正文", "第1章 旧标题\n正文"),
    ("# 第2章 其他章名\n正文", "# 第2章 其他章名\n正文"),
    ("```markdown\n\n正文\n\n```", "正文"),
])
def test_manuscript_normalizes_fences_headings_and_missing_headings(body, expected_tail):
    original = body
    assert normalize_manuscript(body, 1, "细纲标题") == f"# 第1章 细纲标题\n{expected_tail}"
    assert body == original


@pytest.mark.parametrize("body", ["", " \n\t", "```markdown\n\n```", "```\n```", None])
def test_only_empty_or_non_text_manuscripts_fail_normalization(body):
    with pytest.raises(ValidationError, match="非空"):
        normalize_manuscript(body, 1, "细纲标题")


@pytest.mark.parametrize("variant", ["fence", "heading", "missing"])
def test_writer_pipeline_uses_normalization_before_validation(workshop, variant):
    def scripted(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            text = "她拨开黑色短发，银色发夹映着冷光，右手按住即将被删除的记录。" * 3
            if variant == "fence":
                return f"```markdown\n{text}\n```"
            if variant == "heading":
                return f"\n### 第 1 章：模型自行起名\n{text}"
            return text

    router = CaptureRouter(FakeLLM(scripted))
    meeting = meet(workshop, router)
    value, compass, bible = workshop
    result = asyncio.run(write_chapter(router, value, compass, bible, meeting,
                                       chapter=1, arm="panel"))
    assert result["body"].startswith(f"# 第1章 {meeting['decision']['beat_sheet']['title']}\n")
    writes = [request for request in router.requests if FakeLLM.payload(request)["task"] == "write"]
    assert len(writes) == 1
    assert "```" not in result["body"]


def test_editor_setup_and_decision_cards_are_separate_and_identical_across_arms(workshop):
    setup = get_agent("editor", task="setup")["system_prompt"]
    decision = get_agent("editor", task="decision")["system_prompt"]
    assert "不写死大纲" in setup and "task=decision" not in setup
    assert "task=decision" in decision and "setup 返回" not in decision
    for phrase in ("逻辑、人物、吸引力、与罗盘的契合度、可拍性", "used_beats", "新发现"):
        assert phrase in decision
    prompts = []
    for arm in ("solo", "panel"):
        router = CaptureRouter()
        meet(workshop, router, arm)
        prompts.append(next(request["messages"][0]["content"] for request in router.requests
                            if FakeLLM.payload(request)["task"] == "decision"))
    assert prompts == [decision, decision]


@pytest.mark.parametrize("role, phrases", [
    ("plot_architect", ("因果链", "信息差", "预计在什么时候回收")),
    ("character_advocate", ("逐个核对", "已知信息", "降智")),
    ("reader_rep", ("最想看到什么", "爽点", "阅读节奏")),
    ("twist_designer", ("最可能预期", "反向走向", "为什么仍然合理")),
    ("pacing_advisor", ("n/M", "主线完成度", "suggest_closing", "触发条件")),
    ("adaptation_advisor", ("场景数", "角色数", "可拍摄", "对白占比")),
])
def test_deliberation_role_checklists_and_proposal_specificity(role, phrases):
    prompt = get_agent(role)["system_prompt"]
    assert all(phrase in prompt for phrase in phrases)
    assert all(f"{number}. " in prompt for number in range(1, 5))
    for phrase in ("80–200", "本章新发现", "谁做了什么选择", "上一章的因果关系",
                   "章末钩子具体是什么", "对立双方", "争的是什么"):
        assert phrase in prompt
    assert prompt.endswith(INJECTION_GUARD)


def test_execution_role_prompts_cover_requested_checks():
    writer = get_agent("writer")["system_prompt"]
    for phrase in ("previous_tail", "不复述前情", "beat_sheet.scenes", "每个节拍",
                   "不在正文里解释设定", "感官细节和动作", "空泛的抒情和总结句"):
        assert phrase in writer
    review = get_agent("reviewer")["system_prompt"]
    assert "锁定的人物外形和设定 → 人物当前位置和伤病 → 时间线与伏笔 → 细纲是否完成" in review
    assert "problem 里要引用圣经原文" in review
    archive = get_agent("archivist")["system_prompt"]
    assert "第n章：" in archive and "谁知道了什么" in archive


@pytest.mark.parametrize("role, task, expected", [
    ("editor", "setup", 12000), ("editor", "decision", 6000),
    *[(role, None, 2500) for role, card in AGENTS.items()
      if card["category"] == "deliberation" and role != "editor"],
    ("reviewer", "review", 4000), ("archivist", "archive", 4000),
])
def test_round_one_token_limits_preserve_registry(role, task, expected):
    before = deepcopy(AGENTS)
    card = get_agent(role, task=task)
    assert card["max_tokens"] == expected
    card["max_tokens"] = 1
    assert AGENTS == before
