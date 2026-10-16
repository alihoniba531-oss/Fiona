"""Offline behavior tests for role cards and the fixed chapter protocol."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from novel.agent_pool import AGENTS, INJECTION_GUARD, get_agent, validate_agents
from novel.bible import build_setup
from novel.deliberation import deliberate
from novel.fake_llm import FakeLLM
from novel.llm_router import StepFailed
from novel.schemas import ValidationError, parse_json
from novel.writing import compact_length, validate_manuscript, write_chapter


class LocalRouter:
    """Keep workflow tests independent from persistence and provider transports."""

    def __init__(self, fake=None):
        self.fake = fake or FakeLLM()
        self.requests = []
        self.active = 0
        self.max_active = 0

    async def call(self, **request):
        self.requests.append(deepcopy({key: value for key, value in request.items() if key != "validator"}))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.001)
            raw, _ = await self.fake(request)
            data = raw if request.get("output") == "markdown" else parse_json(raw)
            return request["validator"](data)
        finally:
            self.active -= 1


@pytest.fixture
def workshop():
    config = json.loads((Path(__file__).parents[1] / "novel/pilot_configs/expA.json").read_text())
    config["target"] = {"min_chapters": 8, "max_chapters": 12, "chapter_words": 300}
    config["agents"] = {role: f"fake:{role}" for role in config["agents"]}
    setup = FakeLLM().default_response({"task": "setup"})
    compass, bible = build_setup(setup, config)
    return config, compass, bible


def meeting_for(workshop, router=None, participants=None, chapter=1, user_notes=()):
    config, compass, bible = workshop
    return asyncio.run(deliberate(router or LocalRouter(), config, compass, bible,
                                  chapter=chapter, arm="panel", user_notes=user_notes,
                                  participants=participants or config["arms"]["panel"]))


@pytest.mark.parametrize("role", list(AGENTS))
def test_every_role_has_complete_guarded_card(role):
    card = get_agent(role)
    assert set(card) == {"id", "name", "category", "required", "system_prompt", "max_tokens", "output"}
    assert card["system_prompt"].endswith(INJECTION_GUARD)
    assert card["id"] == role and card["max_tokens"] > 0


def test_role_token_limits_do_not_mutate_registry():
    assert get_agent("editor", task="setup")["max_tokens"] == 12000
    assert get_agent("editor", task="decision")["max_tokens"] == 6000
    assert get_agent("writer", chapter_words=100)["max_tokens"] == 4000
    assert get_agent("writer", chapter_words=2500)["max_tokens"] == 6250
    assert get_agent("writer", chapter_words=2001)["max_tokens"] == 5003
    card = get_agent("writer")
    card["system_prompt"] = "changed"
    assert get_agent("writer")["system_prompt"].endswith(INJECTION_GUARD)


@pytest.mark.parametrize("role", ["editor", "writer", "archivist"])
def test_missing_required_role_rejected(workshop, role):
    config = deepcopy(workshop[0])
    del config["agents"][role]
    with pytest.raises(ValueError, match="缺少必选智能体"):
        validate_agents(config)


@pytest.mark.parametrize("model", ["bad:model", "deepseek:", "anthropic:model extra", "model"])
def test_invalid_provider_model_rejected(workshop, model):
    config = deepcopy(workshop[0])
    config["agents"]["editor"] = model
    with pytest.raises(ValueError, match="模型规格"):
        validate_agents(config)


@pytest.mark.parametrize("roles", [["editor", ["plot_architect"]], ["editor", 7], ["editor", None], "editor"])
def test_malformed_arm_roles_are_chinese_validation_errors(workshop, roles):
    config = deepcopy(workshop[0])
    config["arms"]["panel"] = roles
    with pytest.raises(ValueError, match="智能体列表不合法"):
        validate_agents(config)


@pytest.mark.parametrize("reviewers", [None, "fake:reviewer", {"model": "fake:reviewer"}, 4])
def test_malformed_reviewer_collection_is_validation_error(workshop, reviewers):
    config = deepcopy(workshop[0])
    config["reviewers_to_compare"] = reviewers
    with pytest.raises(ValueError, match="reviewers_to_compare 必须"):
        validate_agents(config)


@pytest.mark.parametrize("agents", [None, [], "editor", 7])
def test_malformed_agents_collection_is_validation_error(workshop, agents):
    config = deepcopy(workshop[0])
    config["agents"] = agents
    with pytest.raises(ValueError, match="agents 必须"):
        validate_agents(config)


def test_non_object_configuration_is_validation_error():
    with pytest.raises(ValueError, match="配置必须为 JSON 对象"):
        validate_agents(None)


@pytest.mark.parametrize("filename", ["expA.json", "expB.json", "expC.json"])
def test_default_config_valid(filename):
    config = json.loads((Path(__file__).parents[1] / "novel/pilot_configs" / filename).read_text())
    validate_agents(config)
    assert config["seed_idea"].startswith("一个专门替人删除网络痕迹")
    assert config["adaptation"] == {"max_main_characters": 6, "max_scenes_per_chapter": 3}


def test_all_proposals_precede_critiques_and_ids_are_in_configuration_order(workshop):
    router = LocalRouter()
    meeting = meeting_for(workshop, router)
    tasks = [FakeLLM.payload(request)["task"] for request in router.requests]
    assert tasks == ["proposal"] * 3 + ["critique"] * 3 + ["decision"]
    assert [proposal["id"] for proposal in meeting["proposals"]] == ["P1", "P2", "P3"]
    assert [proposal["author"] for proposal in meeting["proposals"]] == ["plot_architect", "character_advocate", "twist_designer"]
    assert [proposal["author_name"] for proposal in meeting["proposals"]] == ["情节架构师", "人物代言人", "反转设计师"]
    assert [objection["id"] for objection in meeting["objections"]] == ["O1", "O2", "O3"]
    assert meeting["scores"]["P1"]["total_mean"] == 4.2
    assert meeting["scores"]["P1"]["review_count"] == 2
    editorial_payload = FakeLLM.payload(router.requests[-1])
    assert all(item["author_name"] for item in editorial_payload["proposals"])


def test_peer_receives_only_other_authors_proposals(workshop):
    router = LocalRouter()
    meeting_for(workshop, router)
    for request in router.requests:
        payload = FakeLLM.payload(request)
        if payload["task"] == "critique":
            assert len(payload["proposals"]) == 2
            assert all(item["author"] != request["role"] for item in payload["proposals"])


def test_single_proposer_safely_skips_empty_peer_review(workshop):
    router = LocalRouter()
    meeting = meeting_for(workshop, router, participants=["plot_architect", "editor"])
    assert [FakeLLM.payload(request)["task"] for request in router.requests] == ["proposal", "decision"]
    assert meeting["scores"]["P1"]["total_mean"] is None
    assert meeting["objections"] == []
    assert meeting["decision"]["chosen_proposal_ids"] == ["P1"]


def test_solo_skips_proposals_and_reviews(workshop):
    router = LocalRouter()
    meeting = meeting_for(workshop, router, participants=["editor"])
    assert len(router.requests) == 1
    assert meeting["proposals"] == [] and meeting["scores"] == {}
    assert meeting["decision"]["chosen_proposal_ids"] == []


def test_concurrency_is_limited_to_three(workshop):
    config, compass, bible = workshop
    roles = [role for role, card in AGENTS.items() if card["category"] == "deliberation" and role != "editor"]
    config["agents"].update({role: f"fake:{role}" for role in roles})
    router = LocalRouter()
    asyncio.run(deliberate(router, config, compass, bible, chapter=1, arm="panel", participants=roles + ["editor"]))
    assert router.max_active == 3


@pytest.mark.parametrize("phase", ["proposal", "critique"])
def test_failed_parallel_phase_cancels_and_drains_siblings_before_return(workshop, phase):
    started, cancelled, running = set(), set(), set()

    async def delayed_failure(request, _index):
        if FakeLLM.payload(request)["task"] != phase:
            return None
        role = request["role"]
        started.add(role)
        running.add(role)
        try:
            if role == "plot_architect":
                # Let all three requests start, then fail without waiting for
                # the siblings' deliberately slow local model responses.
                await asyncio.sleep(0)
                raise StepFailed()
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.add(role)
            raise
        finally:
            running.discard(role)

    router = LocalRouter(FakeLLM(delayed_failure))
    config, compass, bible = workshop

    async def still_running_event_loop():
        with pytest.raises(StepFailed):
            await deliberate(router, config, compass, bible, chapter=1, arm="panel",
                             participants=config["arms"]["panel"])
        # These checks happen before asyncio.run closes the event loop, so
        # loop shutdown cannot accidentally supply the required cancellation.
        assert started == {"plot_architect", "character_advocate", "twist_designer"}
        assert cancelled == {"character_advocate", "twist_designer"}
        assert running == set() and router.active == 0
        count_after_failure = len(router.requests)
        await asyncio.sleep(0)
        assert len(router.requests) == count_after_failure
        assert all(FakeLLM.payload(request)["task"] != "decision" for request in router.requests)

    asyncio.run(still_running_event_loop())


def test_user_note_ids_preserved_and_responded(workshop):
    notes = [{"id": "N1", "text": "让读者先发现委托人的身份。"}]
    meeting = meeting_for(workshop, user_notes=notes)
    assert meeting["brief"]["user_notes"] == notes
    assert meeting["decision"]["user_note_responses"][0]["note_id"] == "N1"


def test_normal_draft_is_reviewed_and_archived(workshop):
    router = LocalRouter()
    meeting = meeting_for(workshop, router)
    config, compass, bible = workshop
    original = deepcopy(bible)
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=1, arm="panel"))
    assert result["body"].startswith("# 第1章 ")
    assert result["flags"] == [] and result["review_rounds"] == 1
    assert result["revision_rounds"] == 0 and result["bible"]["version"] == 2
    assert bible == original


def test_writer_receives_scoped_complete_context_without_full_bible(workshop):
    router = LocalRouter()
    meeting = meeting_for(workshop, router, chapter=2)
    config, compass, bible = workshop
    previous = "上一章末尾。" * 400
    asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=2, arm="panel", previous_text=previous))
    payload = next(FakeLLM.payload(request) for request in router.requests
                   if FakeLLM.payload(request)["task"] == "write")
    assert "bible" not in payload
    context = payload["context"]
    assert context["compass"] == compass
    assert context["style_guide"] == bible["locked"]["style_guide"]
    assert context["adaptation"] == bible["locked"]["adaptation"]
    assert context["characters"][0]["state"] == bible["dynamic"]["character_states"]["C1"]
    assert context["chapter_summaries"] == []
    assert context["previous_tail"] == previous[-1500:]
    assert context["beat_sheet"] == meeting["decision"]["beat_sheet"]
    assert context["open_major_foreshadowing"] == bible["dynamic"]["foreshadowing"]


def test_absent_reviewer_skips_review(workshop):
    config, compass, bible = workshop
    config["agents"].pop("reviewer")
    router = LocalRouter()
    meeting = meeting_for(workshop, router)
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=1, arm="panel"))
    assert result["review_rounds"] == 0
    assert not any(FakeLLM.payload(request)["task"] == "review" for request in router.requests)


def test_length_rewrite_once_then_accept_and_flag(workshop):
    fake = FakeLLM()

    def short_writer(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return f"# 第{payload['chapter']}章 {payload['title']}\n\n她拔掉电源。"

    fake.script = short_writer
    router = LocalRouter(fake)
    meeting = meeting_for(workshop, router)
    config, compass, bible = workshop
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=1, arm="panel"))
    assert result["flags"] == ["length_out_of_range"]
    assert sum(FakeLLM.payload(request)["task"] == "write" for request in router.requests) == 2


def test_blocking_review_revises_twice_and_then_archives(workshop):
    def blocking_review(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "review":
            return {"issues": [{"category": "continuity", "problem": "正控问题", "evidence": "删除倒计时突然跳到六十秒", "fix": "修正倒计时", "blocking": True}]}

    router = LocalRouter(FakeLLM(blocking_review))
    meeting = meeting_for(workshop, router)
    config, compass, bible = workshop
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=1, arm="panel"))
    assert result["flags"] == ["review_unresolved"]
    assert result["review_rounds"] == 3 and result["revision_rounds"] == 2
    writes = [FakeLLM.payload(request) for request in router.requests if FakeLLM.payload(request)["task"] == "write"]
    assert len(writes) == 3
    assert writes[1]["previous_draft"] and writes[1]["blocking_issues"]
    assert result["bible"]["version"] == 2


def test_length_flag_describes_final_draft_after_review_revision(workshop):
    def short_then_repaired(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write" and payload["revision"] == 0:
            return f"# 第{payload['chapter']}章 {payload['title']}\n\n她拔掉电源并关上控制台。"
        if payload["task"] == "review" and payload["review_round"] == 0:
            return {"issues": [{"category": "beat_sheet", "problem": "缺少细纲核验动作", "evidence": "她拔掉电源并关上控制台", "fix": "补全核验动作", "blocking": True}]}

    router = LocalRouter(FakeLLM(short_then_repaired))
    meeting = meeting_for(workshop, router)
    config, compass, bible = workshop
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=1, arm="panel"))
    assert result["flags"] == []
    assert result["revision_rounds"] == 1
    assert 0.6 * config["target"]["chapter_words"] <= compact_length(result["body"])


def test_archival_conflict_and_deviation_are_recorded_without_stopping(workshop):
    fake = FakeLLM()

    def flagged_archive(request, _index):
        if FakeLLM.payload(request)["task"] == "archive":
            archive = fake.default_response(request)
            archive["locked_conflicts"] = ["正文偏离锁定事实"]
            archive["deviation_from_beat_sheet"] = {"deviated": True, "note": "加入一次对质"}
            return archive

    fake.script = flagged_archive
    router = LocalRouter(fake)
    meeting = meeting_for(workshop, router)
    config, compass, bible = workshop
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting, chapter=1, arm="panel"))
    assert result["flags"] == ["locked_conflict", "deviation"]
    assert result["bible"]["version"] == 2


@pytest.mark.parametrize("body", ["", "第1章 标题\n正文", "# 第2章 标题\n正文", "\n# 第1章 标题\n正文"])
def test_invalid_manuscript_heading_is_validation_error(body):
    with pytest.raises(ValidationError):
        validate_manuscript(body, 1, "标题")


def test_manuscript_heading_and_unicode_whitespace_length():
    body = "# 第1章 标题\n正文\t段落\u3000末尾"
    assert validate_manuscript(body, 1, "标题") == body
    assert compact_length(" 甲\n乙\t丙\u3000丁 ") == 4
