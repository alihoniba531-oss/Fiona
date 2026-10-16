"""Bounded P1 context views and arc calls, using offline model seams only."""

import asyncio
from copy import deepcopy
import json

import pytest

from novel.agent_pool import AGENTS, INJECTION_GUARD, get_agent
from novel.bible import build_setup
from novel.context import build_brief, build_review_bible, build_writer_context, trim_bible
from novel.deliberation import deliberate, messages_for
from novel.fake_llm import FakeLLM, input_characters
from novel.llm_router import LLMRouter
from novel.run_store import RunStore
from novel.safety import NOVEL_SAFETY_RULES
from novel.writing import write_chapter


def configuration():
    return {"experiment": "P1", "seed_idea": "追查一段旧录像", "panel_mode": "critique",
            "enable_context_compression": True, "enable_arc_summaries": True,
            "target": {"min_chapters": 20, "max_chapters": 60, "chapter_words": 1000},
            "adaptation": {"max_main_characters": 3, "max_scenes_per_chapter": 3},
            "agents": {role: "dashscope:qwen3.8-max" for role in
                       ("editor", "writer", "archivist", "reviewer", "twist_designer")}}


def long_bible(chapters):
    compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), configuration())
    dynamic = bible["dynamic"]
    dynamic["chapter_summaries"] = [
        {"chapter": n, "title": f"第{n}章", "summary": "核对记录，保存证据。" * 35,
         "characters": ["C1"]} for n in range(1, chapters + 1)]
    dynamic["timeline"] = [f"第{n}章：核对记录。" * 10 for n in range(1, chapters + 1)]
    dynamic["used_beats"] = [f"第{n}次核对记录" * 5 for n in range(chapters * 3)]
    dynamic["foreshadowing"] = [
        {"id": f"F{n:03d}", "status": "resolved", "importance": "minor",
         "description": "已经回收的线索。" * 10, "resolved_chapter": n}
        for n in range(chapters)] + [
        {"id": f"OPEN{n}", "status": "open", "importance": "minor",
         "description": "尚未回收的线索"} for n in range(4)]
    dynamic["arc_summaries"] = [
        {"start_chapter": n - 9, "end_chapter": n,
         "summary": "林澈选择保存记录，逐步查明旧案与自身关系。" * 2}
        for n in range(10, chapters + 1, 10)]
    return compass, bible


def serialized(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def test_sixty_chapter_context_views_stay_bounded_and_preserve_open_ledger(tmp_path):
    """Exercise real P0 planning/writing/archive calls against a growing fake story."""
    async def run():
        config = configuration()
        compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
        bible["dynamic"]["foreshadowing"].extend([
            {"id": f"F{n:03d}", "status": "open", "importance": "minor",
             "description": "持续保留的未解线索", "planted_chapter": 0}
            for n in range(2, 6)])

        def growing_story(request, _):
            if request["task"] != "archive":
                return None
            chapter = request["chapter"]
            answer = fake.default_response(request)
            answer["character_state_changes"] = [
                {"id": "C1", "field": "knows",
                 "value": [f"第{chapter:03d}章确认：保管者曾把原始记录交给另一名证人，副本来源已经得到核实。"]}]
            answer["foreshadowing_planted"] = [
                {"description": "新记录上的签名等待下一章核对", "importance": "minor"}]
            if chapter > 1:
                answer["foreshadowing_resolved"].append(
                    {"id": f"F{chapter + 4:03d}", "note": "已与原始签名核对"})
            if chapter % 4 == 0:
                answer["new_characters"] = [{
                    "name": f"记录保管人{chapter:03d}", "role": "supporting", "age": "40",
                    "appearance": "身穿旧工作服，佩戴编号胸牌，手中保存一叠原始记录。",
                    "personality": "谨慎，愿意核对事实", "motivation": "保全证人的原始记录"}]
            return answer

        fake = FakeLLM(growing_story)
        router = LLMRouter(RunStore(tmp_path, config, max_total_tokens=20_000_000))
        router._single_real_call = fake
        snapshots = {}
        previous_text = ""
        for chapter in range(1, 61):
            before = deepcopy(bible)
            meeting = await deliberate(router, config, compass, bible, chapter=chapter,
                                       arm="panel", participants=["editor", "twist_designer"])
            product = await write_chapter(router, config, compass, bible, meeting,
                                          chapter=chapter, arm="panel", previous_text=previous_text)
            assert bible == before
            if chapter in (30, 60):
                snapshots[chapter] = deepcopy(bible)
            bible, previous_text = product["bible"], product["body"]
        assert len(bible["locked"]["characters"]) == 16
        assert len(bible["dynamic"]["character_states"]["C1"]["knows"]) == 61
        assert [arc["end_chapter"] for arc in bible["dynamic"]["arc_summaries"]] == list(range(10, 61, 10))
        sizes = {}
        for chapter, source in snapshots.items():
            view = trim_bible(source, chapter)
            assert len(view["dynamic"]["chapter_summaries"]) == 10
            assert len(view["dynamic"]["timeline"]) == 10
            assert len(view["dynamic"]["used_beats"]) == min(30, chapter - 1)
            assert len(view["dynamic"]["character_states"]["C1"]["knows"]) == 30
            open_ids = {item["id"] for item in source["dynamic"]["foreshadowing"]
                        if item["status"] == "open"}
            assert len(open_ids) == 6
            assert {item["id"] for item in view["dynamic"]["foreshadowing"]
                    if item["status"] == "open"} == open_ids
            assert len([item for item in view["dynamic"]["foreshadowing"]
                        if item["status"] == "resolved"]) == 5
            sizes[chapter] = {}
            for task in ("plan", "write", "review", "archive"):
                calls = [call for call in fake.calls
                         if call["chapter"] == chapter and call["task"] == task]
                assert len(calls) == 1
                payload = FakeLLM.payload(calls[0])
                context = payload.get("brief", payload.get("context", payload.get("bible")))
                assert {item["id"] for item in context["locked"]["characters"]} == {
                    item["id"] for item in view["locked"]["characters"]}
                states = (context["dynamic"].get("character_states") or
                          {item["id"]: item["state"] for item in context["characters"]})
                assert all(len(state["knows"]) <= 30 for state in states.values())
                sizes[chapter][task] = input_characters(calls[0]["messages"])
                assert sizes[chapter][task] < 20000
        for task in sizes[30]:
            assert abs(sizes[60][task] - sizes[30][task]) / sizes[30][task] <= 0.10, sizes
        print("growing 60-chapter actual input characters:", sizes)

    asyncio.run(run())


def test_supporting_cards_and_states_use_recent_appearances_or_explicit_current_beat():
    compass, bible = long_bible(59)
    for identifier, seen in (("C2", 57), ("C3", 56), ("C4", 20), ("C5", 20)):
        bible["locked"]["characters"].append({"id": identifier, "role": "supporting"})
        bible["dynamic"]["character_states"][identifier] = {
            "last_seen_chapter": seen, "knows": [f"事实{n}" for n in range(50)]}
    bible["dynamic"]["chapter_summaries"][-1]["characters"].append("C5")
    original = deepcopy(bible)
    result = trim_bible(bible, 60, ["C4"])
    expected = {"C1", "C2", "C4", "C5"}
    assert set(result["dynamic"]["character_states"]) == expected
    assert {item["id"] for item in result["locked"]["characters"]} == expected
    for identifier in expected - {"C1"}:
        assert result["dynamic"]["character_states"][identifier]["knows"] == [
            f"事实{n}" for n in range(20, 50)]
    for view in (build_brief(compass, bible, 60, named_characters=["C4"]),
                 build_writer_context(compass, bible, {"characters": ["C4"]}, 60,
                                      compressed=True),
                 build_review_bible(compass, bible, 60, ["C4"])):
        assert {item["id"] for item in view["locked"]["characters"]} == expected
    assert bible == original


def test_plan_named_card_reaches_all_inputs_and_archive_validation_uses_full_bible(tmp_path):
    async def run():
        config = configuration()
        compass, bible = long_bible(59)
        for identifier in ("C2", "C3"):
            bible["locked"]["characters"].append({"id": identifier, "role": "supporting",
                                                    "name": "旧案证人"})
            bible["dynamic"]["character_states"][identifier] = {
                "location": "外地", "condition": "平安", "relationships": {},
                "last_seen_chapter": 20, "knows": [f"往事{n}" for n in range(60)]}
        original = deepcopy(bible)

        def story(request, _):
            answer = fake.default_response(request)
            if request["task"] in ("plan", "finalize"):
                answer["beat_sheet"]["characters"] = ["C1", "C3"]
            if request["task"] == "archive":
                answer["character_state_changes"] = [
                    {"id": "C2", "field": "condition", "value": "已确认平安"}]
            return answer

        fake = FakeLLM(story)
        router = LLMRouter(RunStore(tmp_path, config))
        router._single_real_call = fake
        meeting = await deliberate(router, config, compass, bible, chapter=60,
                                   arm="panel", participants=["editor", "twist_designer"])
        product = await write_chapter(router, config, compass, bible, meeting,
                                      chapter=60, arm="panel")
        for call in fake.calls:
            payload = FakeLLM.payload(call)
            context = payload.get("brief", payload.get("context", payload.get("bible")))
            cards = {item["id"] for item in context["locked"]["characters"]}
            assert "C2" not in cards
            assert cards == ({"C1"} if call["task"] == "plan" else {"C1", "C3"})
        archive_calls = [call for call in fake.calls if call["task"] == "archive"]
        assert len(archive_calls) == 1  # C2 must not trigger an unknown-ID retry.
        assert product["bible"]["dynamic"]["character_states"]["C2"]["condition"] == "已确认平安"
        assert len(product["bible"]["dynamic"]["character_states"]["C3"]["knows"]) == 60
        assert bible == original

    asyncio.run(run())


def test_full_length_arcs_are_retained_and_knowledge_is_bounded_in_actual_messages():
    """Retention rules take precedence over pretending every input has a fixed size.

    The representative rolling-window fixture above checks 30/60 stability. This
    separate maximum-volume-summary fixture records the unavoidable growth of
    retained arcs while protagonist knowledge is bounded only in the view.
    """
    sizes = {}
    for chapters in (29, 59):
        compass, bible = long_bible(chapters)
        for arc in bible["dynamic"]["arc_summaries"]:
            arc["summary"] = "卷" * 600
        bible["dynamic"]["character_states"]["C1"]["knows"].extend(
            f"第{n}章新确认的事实。" for n in range(1, chapters + 1))
        trimmed = build_review_bible(compass, bible, chapters + 1, ["C1"])
        assert trimmed["dynamic"]["character_states"]["C1"]["knows"] == bible["dynamic"]["character_states"]["C1"]["knows"][-30:]
        assert len(bible["dynamic"]["character_states"]["C1"]["knows"]) == chapters + 1
        assert all(len(arc["summary"]) == 600 for arc in trimmed["dynamic"]["arc_summaries"])
        assert len(trimmed["dynamic"]["arc_summaries"]) == chapters // 10
        beat = {"characters": ["C1"]}
        context = build_writer_context(compass, bible, beat, chapters + 1, compressed=True)
        assert set(context["characters"][0]) == {"id", "state"}
        assert "character_states" not in context["dynamic"]
        assert "chapter_summaries" not in context["dynamic"]
        assert "style_guide" not in context and "adaptation" not in context
        payloads = [("editor", {"task": "decision", "brief": build_brief(
                        compass, bible, chapters + 1, timeline_limit=10)}),
                    ("writer", {"task": "write", "context": context, "previous_draft": "稿" * 6400}),
                    ("reviewer", {"task": "review", "body": "稿" * 6400,
                                  "beat_sheet": beat, "bible": trimmed}),
                    ("archivist", {"task": "archive", "body": "稿" * 6400,
                                   "beat_sheet": beat, "bible": trimmed})]
        sizes[chapters + 1] = {}
        for role, payload in payloads:
            _, messages = messages_for(role, payload, split_context=True)
            assert input_characters(messages) < 22000
            assert FakeLLM.payload({"messages": messages}) == payload
            sizes[chapters + 1][role] = input_characters(messages)
    print("600-character retained arc input characters:", sizes)


def test_two_user_blocks_have_stable_prefix_and_fake_reconstructs_original_payload():
    compass, bible = long_bible(29)
    first = {"task": "decision", "brief": build_brief(compass, bible, 30), "chapter": 30}
    second = deepcopy(first)
    second["chapter"] = 31
    second["brief"]["dynamic"]["timeline"].append("变化中的本章资料")
    _, messages = messages_for("editor", first, split_context=True)
    _, later = messages_for("editor", second, split_context=True)
    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert messages[1] == later[1]
    assert messages[2] != later[2]
    assert "task" not in json.loads(messages[1]["content"])
    assert FakeLLM.payload({"messages": messages}) == first


@pytest.mark.parametrize("role", list(AGENTS))
def test_all_role_cards_place_safety_before_injection_guard(role):
    for task in (None, "setup", "plan", "finalize", "critique_plan", "arc_summary"):
        prompt = get_agent(role, task=task)["system_prompt"]
        assert NOVEL_SAFETY_RULES in prompt
        assert prompt.index(NOVEL_SAFETY_RULES) < prompt.index(INJECTION_GUARD)
        assert prompt.endswith(INJECTION_GUARD)


def test_arc_summary_every_ten_chapters_is_real_router_call_and_keeps_p0_step_shape(tmp_path):
    class Meter:
        def __init__(self):
            self.reserved, self.settled = [], []

        async def reserve(self, call):
            self.reserved.append(call["step_key"])
            return 1

        async def settle(self, call, usage):
            self.settled.append(call["step_key"])
            return 1

        async def refund(self, call):
            raise AssertionError("deterministic calls should succeed")

    async def run():
        config = configuration()
        config["panel_mode"] = "solo"
        compass, bible = build_setup(FakeLLM().default_response({"task": "setup"}), config)
        fake, meter = FakeLLM(), Meter()
        router = LLMRouter(RunStore(tmp_path, config, max_total_tokens=20_000_000), billing=meter)
        router._single_real_call = fake
        for chapter in range(1, 21):
            meeting = await deliberate(router, config, compass, bible, chapter=chapter,
                                       arm="solo", participants=["editor"])
            product = await write_chapter(router, config, compass, bible, meeting,
                                          chapter=chapter, arm="solo")
            bible = product["bible"]
        arcs = [call for call in fake.calls if call["task"] == "arc_summary"]
        assert [call["chapter"] for call in arcs] == [10, 20]
        assert all(call["step_key"] in meter.reserved and call["step_key"] in meter.settled
                   for call in arcs)
        assert [arc["end_chapter"] for arc in bible["dynamic"]["arc_summaries"]] == [10, 20]
        assert all(1 <= len(arc["summary"]) <= 600 for arc in bible["dynamic"]["arc_summaries"])
        assert all([message["role"] for message in call["messages"]] == ["system", "user", "user"]
                   for call in fake.calls)

    asyncio.run(run())
