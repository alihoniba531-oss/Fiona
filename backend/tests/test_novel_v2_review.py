"""Offline P1 review convergence and opt-in v2 role-card regressions."""

import asyncio
from copy import deepcopy

import pytest

from novel.agent_pool import (AGENTS, INJECTION_GUARD, JSON_STRING_QUOTE_RULE,
                              PAYOFF_PROTECTION_RULE, get_agent)
from novel.bible import build_setup
from novel.context import v2_structure_context
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.run_store import RunStore
from novel.writing import _validate_focused_review, changed_passages, write_chapter


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("v2 review regressions must use the offline fake route")

    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden)


def workshop(experiment="P1"):
    config = {"experiment": experiment, "seed_idea": "保全原件并查清真相",
              "target": {"min_chapters": 1, "max_chapters": 3, "chapter_words": 300},
              "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3},
              "agents": {role: f"fake:{role}" for role in
                         ("editor", "writer", "reviewer", "archivist")}}
    fake = FakeLLM()
    compass, bible = build_setup(fake.default_response({"task": "setup"}), config)
    meeting = {"decision": fake.default_response({"payload": {
        "task": "decision", "chapter": 1, "compass": compass, "bible": bible}})}
    return config, compass, bible, meeting


def run_chapter(tmp_path, values, script):
    fake = FakeLLM(script)
    router = LLMRouter(RunStore(tmp_path, values[0]), fake=fake)
    router.retry_delay = 0
    result = asyncio.run(write_chapter(router, *values, chapter=1, arm="solo"))
    return result, fake


def payloads(fake, task):
    return [FakeLLM.payload(call) for call in fake.calls if call["task"] == task]


def finding(evidence, *, problem="与锁定事实冲突", blocking=True):
    return {"category": "continuity", "problem": problem, "evidence": evidence,
            "fix": "恢复锁定事实。", "blocking": blocking}


ORIGINAL = "林澈仍然站在旧控制台旁。"
UNCHANGED = "白色文件夹一直放在旧木桌上。"
REPLACED = "记录员拿着蓝色笔抄写今天的日期。"
REPLACEMENT = "记录员拿着红色笔抄写昨天的日期。"


def manuscript(payload, *, changed=False, delete=False):
    paragraphs = [f"# 第1章 {payload['title']}", ORIGINAL, UNCHANGED]
    if not delete:
        paragraphs.append(REPLACEMENT if changed else REPLACED)
    return "\n\n".join([*paragraphs, "字" * 180])


def test_changed_passages_tracks_add_replace_delete_and_unchanged():
    before = "保留的原文段落。\n\n将被修改的原文段落。\n\n将被删除的原文段落。"
    after = "保留的原文段落。\n\n修改后的当前段落。\n\n新增的当前段落。"
    assert changed_passages(before, after) == ["修改后的当前段落。", "新增的当前段落。"]
    assert changed_passages(before, before) == []
    assert changed_passages(before, "保留的原文段落。") == []
    assert changed_passages("", "新增一段。\n\n新增第二段。") == ["新增一段。", "新增第二段。"]


def test_changed_passages_truncates_to_3000_characters_and_marks_it():
    long = "新增正文" * 1000
    passages = changed_passages("旧正文", long)
    assert sum(map(len, passages)) == 3000
    assert passages[0] == long[:len(passages[0])]
    assert "截断" in passages[-1]
    assert changed_passages("", "字" * 3000) == ["字" * 3000]


def test_p1_first_review_keeps_more_than_three_blockers(tmp_path):
    values = workshop()

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload)
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL, problem=f"阻断{i}") for i in range(6)]
                    if payload["review_round"] == 0 else []}

    result, fake = run_chapter(tmp_path, values, script)
    assert len(result["reviews"][0]["issues"]) == 6
    assert all(issue["blocking"] for issue in result["reviews"][0]["issues"])
    assert len(payloads(fake, "review")[1]["previous_blocking_issues"]) == 6
    prompt = next(call["messages"][0]["content"] for call in fake.calls if call["task"] == "review")
    assert "首轮列出全部阻断问题，最多 8 条，按严重程度排序" in prompt
    assert "每轮最多 3 条阻断问题，按严重程度排序" in prompt


@pytest.mark.parametrize("structure", [None, "v1"])
def test_r2_unchanged_payload_omits_field_but_downgrades_new_findings(tmp_path, structure):
    values = workshop()
    if structure:
        values[0]["structure"] = structure

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload)
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL if payload["review_round"] == 0 else UNCHANGED)]}

    result, fake = run_chapter(tmp_path, values, script)
    reviews = payloads(fake, "review")
    assert len(reviews) == 2
    assert "changed_passages" not in reviews[0] and "changed_passages" not in reviews[1]
    assert reviews[1]["previous_blocking_issues"] == result["reviews"][0]["issues"]
    assert result["reviews"][1]["issues"][0]["blocking"] is False
    assert result["reviews"][1]["issues"][0]["outside_changes"] is True
    assert result["reviews"][1]["passed"] is True
    assert "review_unresolved" not in result["flags"]


def test_changed_payload_allows_new_blocker_only_in_changed_passage(tmp_path):
    values = workshop()

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload, changed=payload["revision"] >= 1)
        if payload["task"] == "review":
            if payload["review_round"] == 0:
                return {"issues": [finding(ORIGINAL)]}
            if payload["review_round"] == 1:
                return {"issues": [finding(ORIGINAL), finding(UNCHANGED), finding(REPLACEMENT)]}
            return {"issues": []}

    result, fake = run_chapter(tmp_path, values, script)
    reviews = payloads(fake, "review")
    assert reviews[1]["changed_passages"] == [REPLACEMENT]
    old, outside, inside = result["reviews"][1]["issues"]
    assert old["blocking"] and "outside_changes" not in old
    assert outside["blocking"] is False and outside["outside_changes"] is True
    assert inside["blocking"] and "outside_changes" not in inside
    assert reviews[2]["previous_blocking_issues"] == [old, inside]
    assert "changed_passages" not in reviews[2]


def test_previous_issue_stays_blocking_when_unchanged_and_new_issue_is_downgraded(tmp_path):
    values = workshop()

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload)
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL)] + (
                [finding(UNCHANGED)] if payload["review_round"] else [])}

    result, fake = run_chapter(tmp_path, values, script)
    assert result["review_rounds"] == 3 and "review_unresolved" in result["flags"]
    for review in result["reviews"][1:]:
        assert review["issues"][0]["blocking"] is True
        assert review["issues"][1]["outside_changes"] is True
    assert all(len(payload["previous_blocking_issues"]) == 1
               for payload in payloads(fake, "review")[1:])


def test_deletion_only_edit_omits_empty_passages_and_downgrades_new_issue(tmp_path):
    values = workshop()

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload, delete=payload["revision"] >= 1)
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL if payload["review_round"] == 0 else UNCHANGED)]}

    result, fake = run_chapter(tmp_path, values, script)
    assert payloads(fake, "write")[1]["previous_draft"] != result["body"]
    assert "changed_passages" not in payloads(fake, "review")[1]
    assert result["reviews"][1]["issues"][0]["outside_changes"] is True


def test_changed_payload_is_truncated_but_clipped_evidence_still_blocks(tmp_path):
    values = workshop()
    values[0]["target"]["chapter_words"] = 4000
    long_passage = "新增段落内容" * 600 + "末尾改动证据确实存在。"

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return (f"# 第1章 {payload['title']}\n\n{ORIGINAL}\n\n"
                    + ("旧段落内容" * 700 if payload["revision"] == 0 else long_passage))
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL if payload["review_round"] == 0
                                       else "末尾改动证据确实存在")]}

    result, fake = run_chapter(tmp_path, values, script)
    passages = payloads(fake, "review")[1]["changed_passages"]
    assert sum(map(len, passages)) == 3000 and "截断" in passages[-1]
    assert result["reviews"][1]["issues"][0]["blocking"] is True
    assert "outside_changes" not in result["reviews"][1]["issues"][0]
    assert "review_unresolved" in result["flags"]


def test_single_newline_manuscript_scopes_changes_to_individual_lines(tmp_path):
    values = workshop()

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return (f"# 第1章 {payload['title']}\n\n" + "\n".join([
                ORIGINAL, UNCHANGED, "人物核对完了保险柜里的原件。",
                REPLACEMENT if payload["revision"] else REPLACED,
                "保管员再次清点桌上的三份副本。", "她没有把钥匙交给任何人。", "字" * 180]))
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL)] if payload["review_round"] == 0 else (
                [finding(UNCHANGED), finding(REPLACEMENT)] if payload["review_round"] == 1 else [])}

    result, fake = run_chapter(tmp_path, values, script)
    assert payloads(fake, "review")[1]["changed_passages"] == [REPLACEMENT]
    outside, inside = result["reviews"][1]["issues"]
    assert outside["blocking"] is False and outside["outside_changes"] is True
    assert inside["blocking"] is True and "outside_changes" not in inside


def test_full_changed_collection_keeps_final_paragraph_error_beyond_payload_limit(tmp_path):
    values = workshop()
    values[0]["target"]["chapter_words"] = 4000
    evidence = "林澈在第十二段里死而复生地站了起来。"

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            revision = payload["revision"]
            paragraphs = [f"{'新' if revision else '旧'}稿第{i}段：" + "字" * 350
                          for i in range(1, 13)]
            if revision:
                paragraphs[-1] += evidence
            return "\n\n".join([f"# 第1章 {payload['title']}", ORIGINAL, *paragraphs])
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL if payload["review_round"] == 0 else evidence)]}

    result, fake = run_chapter(tmp_path, values, script)
    reviews = payloads(fake, "review")
    full = changed_passages(reviews[0]["body"], reviews[1]["body"], limit=None)
    assert len(full) == 12 and sum(map(len, full)) > 4000 and evidence in full[-1]
    assert sum(map(len, reviews[1]["changed_passages"])) == 3000
    assert all(evidence not in passage for passage in reviews[1]["changed_passages"])
    assert result["reviews"][1]["issues"][0]["blocking"] is True
    assert "outside_changes" not in result["reviews"][1]["issues"][0]
    assert "review_unresolved" in result["flags"]


@pytest.mark.parametrize("old,new", [
    ("林澈仍然站在旧控制台旁，手里拿着那份白色文件夹。", "仍然站在旧控制台旁"),
    ("林澈仍然站在旧控制台旁", "旧控制台旁，手里拿着那份"),
    ("林澈仍然站在旧控制台旁", "手里拿着那份白色文件夹"),
])
def test_old_blocker_with_changed_quote_span_overlap_or_same_paragraph_stays_blocking(old, new):
    body = "林澈仍然站在旧控制台旁，手里拿着那份白色文件夹。\n\n另一段原文没有改变。"
    review = _validate_focused_review({"issues": [finding(new)]}, body,
        adaptation_blocking=False, previous_issues=[finding(old)], passages=[])
    assert review["passed"] is False
    assert review["issues"][0]["blocking"] is True
    assert "outside_changes" not in review["issues"][0]


def test_quote_normalization_keeps_new_blocker_inside_changed_passage(tmp_path):
    values = workshop()
    changed = "林澈说：“原件早就不在保险柜里了，三天前就被人取走。”"
    evidence = '林澈说："原件早就不在保险柜里了，三天前就被人取走。"'

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            body = manuscript(payload)
            return body.replace(REPLACED, changed) if payload["revision"] else body
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL if payload["review_round"] == 0 else evidence)]}

    result, fake = run_chapter(tmp_path, values, script)
    assert payloads(fake, "review")[1]["changed_passages"] == [changed]
    assert result["reviews"][1]["issues"][0]["blocking"] is True
    assert "outside_changes" not in result["reviews"][1]["issues"][0]


@pytest.mark.parametrize("index,expected_blocking", [(1, True), (0, False), (2, False), (True, False)])
def test_previous_issue_index_only_reuses_a_valid_one_based_reference(index, expected_blocking):
    body = ORIGINAL + "\n\n" + UNCHANGED
    issue = dict(finding(UNCHANGED), previous_issue_index=index)
    review = _validate_focused_review({"issues": [issue]}, body,
        adaptation_blocking=False, previous_issues=[finding(ORIGINAL)], passages=[])
    assert review["issues"][0]["blocking"] is expected_blocking
    assert review["passed"] is not expected_blocking
    if expected_blocking:
        assert "outside_changes" not in review["issues"][0]
    else:
        assert review["issues"][0]["outside_changes"] is True


def test_v2_writer_and_reviewer_receive_planned_payoff_and_archive_confirms_delivery(tmp_path):
    values = workshop()
    config, compass, bible, meeting = values
    config["structure"] = "v2"
    compass["genre_contract"] = FakeLLM.genre_contract("T1")
    planned = {"type": compass["genre_contract"]["core_payoffs"][0], "beat_index": 2}
    meeting["decision"].update(genre_payoff=deepcopy(planned), milestones_advanced=["M1"])

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload)
        if payload["task"] == "review":
            return {"issues": []}
        if payload["task"] == "archive":
            archive = FakeLLM().default_response(request)
            archive["payoff_delivered"] = False
            return archive

    result, fake = run_chapter(tmp_path, values, script)
    assert payloads(fake, "write")[0]["context"]["genre_payoff"] == planned
    assert payloads(fake, "write")[0]["context"]["milestones_advanced"] == ["M1"]
    assert payloads(fake, "review")[0]["genre_payoff"] == planned
    assert payloads(fake, "archive")[0]["genre_payoff"] == planned
    assert result["archive"]["payoff_delivered"] is False
    record = result["bible"]["dynamic"]["structure_history"][-1]
    assert record["genre_payoff"] == planned and record["payoff_delivered"] is False
    compass["genre_contract"]["payoff_every_chapters"] = 2
    brief = v2_structure_context(compass, result["bible"], 2)
    assert brief["payoff_history"][-1]["genre_payoff"] is None
    assert brief["payoff_history"][-1]["payoff_delivered"] is False
    assert brief["payoff_required"] is True


def test_v2_planned_payoff_missing_from_manuscript_is_reviewed_as_missing_beat(tmp_path):
    values = workshop()
    values[0]["structure"] = "v2"
    values[1]["genre_contract"] = FakeLLM.genre_contract("T1")
    planned = {"type": values[1]["genre_contract"]["core_payoffs"][0], "beat_index": 2}
    values[3]["decision"].update(genre_payoff=planned, milestones_advanced=[])

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload)
        if payload["task"] == "review":
            return {"issues": [dict(finding(ORIGINAL, problem="整条类型爽点节拍缺失"),
                                    category="beat_sheet")]}
        if payload["task"] == "archive":
            archive = FakeLLM().default_response(request)
            archive["payoff_delivered"] = False
            return archive

    result, fake = run_chapter(tmp_path, values, script)
    assert result["review_rounds"] == 3 and "review_unresolved" in result["flags"]
    assert all(review["issues"][0]["blocking"] for review in result["reviews"])
    assert all(payload["genre_payoff"] == planned for payload in payloads(fake, "review"))


@pytest.mark.parametrize("experiment", ["A", "A2", "B", "C"])
def test_p0_review_payload_and_unrestricted_new_blockers_are_unchanged(tmp_path, experiment):
    values = workshop(experiment)

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "write":
            return manuscript(payload, changed=payload["revision"] >= 1)
        if payload["task"] == "review":
            return {"issues": [finding(ORIGINAL if payload["review_round"] == 0 else UNCHANGED)]}

    result, fake = run_chapter(tmp_path, values, script)
    reviews = payloads(fake, "review")
    assert len(reviews) == 3 and "review_unresolved" in result["flags"]
    for revision, payload in enumerate(reviews):
        expected = {"task", "chapter", "body", "beat_sheet", "bible", "review_round"}
        if revision:
            expected.add("previous_blocking_issues")
        assert set(payload) == expected
    for call in fake.calls:
        if call["task"] == "review":
            assert call["messages"][0]["content"] == get_agent("reviewer")["system_prompt"]


@pytest.mark.parametrize("role,task", [
    ("editor", "setup"), ("editor", "plan"), ("editor", "finalize"),
    ("editor", "decision"), ("writer", "write"), ("archivist", "archive"),
    ("reader_rep", "critique_plan"), ("pacing_advisor", "proposal"),
])
def test_v1_and_p0_cards_remain_exactly_unchanged(role, task):
    before = deepcopy(AGENTS)
    assert get_agent(role, task=task, structure="v1", experiment="A") == get_agent(role, task=task)
    assert get_agent(role, task=task, experiment="P1") == get_agent(role, task=task)
    assert AGENTS == before


@pytest.mark.parametrize("role", ["plot_architect", "character_advocate", "reader_rep",
                                  "twist_designer", "pacing_advisor", "adaptation_advisor"])
@pytest.mark.parametrize("task", ["proposal", "critique", "critique_plan", "volume_critique"])
def test_v2_advisors_protect_payoffs_without_mutating_v1(role, task):
    before = get_agent(role, task=task)
    card = get_agent(role, task=task, structure="v2", experiment="P1")
    assert PAYOFF_PROTECTION_RULE in card["system_prompt"]
    assert PAYOFF_PROTECTION_RULE not in before["system_prompt"]
    assert get_agent(role, task=task) == before
    assert card["system_prompt"].splitlines()[-2:] == [JSON_STRING_QUOTE_RULE, INJECTION_GUARD]
    if role == "reader_rep":
        assert "然后才看上一章留下的悬念" in card["system_prompt"]
    if role == "pacing_advisor":
        assert "thread_staleness" in card["system_prompt"] and "due_chapter" in card["system_prompt"]


@pytest.mark.parametrize("task", ["setup", "genre_contract", "volume_plan", "volume_finalize",
                                  "plan", "finalize", "decision"])
def test_v2_editor_cards_explain_new_output_contracts(task):
    prompt = get_agent("editor", task=task, structure="v2", experiment="P1")["system_prompt"]
    assert prompt.splitlines()[-2:] == [JSON_STRING_QUOTE_RULE, INJECTION_GUARD]
    if task in {"setup", "genre_contract"}:
        assert "core_thread" in prompt and "成长线" in prompt
    elif task.startswith("volume_"):
        assert "new_mystery_budget" in prompt and "payoff_plan" in prompt
    else:
        assert "milestones_advanced" in prompt and "必须同时给出替代的爽点" in prompt


def test_p1_review_prompt_preserves_old_sentences_and_limits_beat_wording():
    original = get_agent("reviewer")["system_prompt"]
    p1 = get_agent("reviewer", experiment="P1")["system_prompt"]
    frozen = "收到 previous_blocking_issues 表示复审：先逐条判断上一轮的阻断问题是否已经解决；新发现的问题只有属于上述三类中的严重情况，才可以判为阻断，否则 blocking=false。"
    assert frozen in original and frozen in p1
    assert "整条节拍或整个场景缺失" in p1
    assert "钩子措辞、节拍顺序的细节差异一律不阻断" in p1
    assert "payload 中没有 changed_passages" in p1
    assert p1.splitlines()[-2:] == [JSON_STRING_QUOTE_RULE, INJECTION_GUARD]
