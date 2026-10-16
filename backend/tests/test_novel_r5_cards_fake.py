"""Critique role cards, deterministic responses and the portable A2 config."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from novel.agent_pool import (
    AGENTS, INJECTION_GUARD, PROPOSAL_SCHEMA, REVELATION_RULE, get_agent,
    validate_agents,
)
from novel.bible import build_setup
from novel.fake_llm import FakeLLM
from novel.prompt_rules import JSON_STRING_QUOTE_RULE
from novel.schemas import validate_decision
from test_novel_schemas import config_data, setup_data


ADVISORS = [role for role, card in AGENTS.items()
            if card["category"] == "deliberation" and role != "editor"]
CONFIG_DIRECTORY = Path(__file__).resolve().parents[1] / "novel" / "pilot_configs"


@pytest.mark.parametrize("task", ["decision", "plan", "finalize"])
def test_each_editor_creation_task_contains_exact_revelation_rule(task):
    exact = "每章最多安排一个关键揭示（主线谜底或核心身份的实质推进）；其余新发现只能是线索层面的。"
    prompt = get_agent("editor", task=task)["system_prompt"]
    assert REVELATION_RULE == exact
    assert prompt.count(exact) == 1
    assert f"task={task}" in prompt
    assert "逻辑、人物、吸引力、与罗盘的契合度、可拍性" in prompt
    assert "不重复 used_beats" in prompt
    assert "每章必须有一个读者能说得出来的新发现" in prompt


@pytest.mark.parametrize("task", ["plan", "finalize"])
def test_new_editor_cards_use_solo_shape_and_isolated_registry(task):
    before = deepcopy(AGENTS)
    card = get_agent("editor", task=task)
    prompt = card["system_prompt"]
    assert '"chosen_proposal_ids":[]' in prompt
    assert "综合评分" not in prompt
    assert "可以合并多个提案" not in prompt
    assert "推演会模式必须至少选择" not in prompt
    assert prompt.splitlines()[-2:] == [JSON_STRING_QUOTE_RULE, INJECTION_GUARD]
    if task == "finalize":
        assert card["max_tokens"] == 8000
    else:
        assert card["max_tokens"] == get_agent("editor")["max_tokens"]
    card["system_prompt"] = "调用方改动"
    assert AGENTS == before


def test_plan_and_finalize_have_distinct_creative_responsibilities():
    plan = get_agent("editor", task="plan")["system_prompt"]
    finalize = get_agent("editor", task="finalize")["system_prompt"]
    assert '"objection_responses":[]' in plan
    assert "本次 N* 用户留言各恰好回应一次" in plan
    assert "这一章最好的写法，而不是让每条意见都满意" in finalize
    assert "不要为了照顾意见而把多个方向拼在一起" in finalize
    assert "对每条 major 意见，要么改，要么说明不改的理由" in finalize
    assert "如果它明显更好，可以整体换成它" in finalize
    assert "「采纳 / 部分采纳 / 不采纳」以及理由" in finalize
    assert "O* 反对意见、A* 替代走向" in finalize


@pytest.mark.parametrize("role", ADVISORS)
def test_critique_card_preserves_each_role_perspective_and_shared_contract(role):
    original = get_agent(role)
    prompt = get_agent(role, task="critique_plan")["system_prompt"]
    perspective = original["system_prompt"].split(PROPOSAL_SCHEMA, 1)[0]
    assert prompt.startswith(perspective)
    assert "task=critique_plan" in prompt
    assert "task=proposal" not in prompt
    assert "task=critique 时" not in prompt
    for field in ("objections", "severity", "target", "problem", "suggestion", "keep", "alternative"):
        assert f'"{field}"' in prompt
    assert "1–3 条" in prompt
    assert "不挑措辞" in prompt
    assert "可执行的改法" in prompt
    assert "80–200 字" in prompt
    assert "不打分，不计算均分" in prompt
    assert prompt.splitlines()[-2:] == [JSON_STRING_QUOTE_RULE, INJECTION_GUARD]
    assert prompt.count(JSON_STRING_QUOTE_RULE) == 1


def _request(task, role="editor", **fields):
    compass, bible = build_setup(setup_data(), config_data())
    payload = {"task": task, "chapter": 12, "mode": "final", "solo": True,
               "brief": {"compass": compass, "locked": bible["locked"],
                         "dynamic": bible["dynamic"]},
               "note_ids": ["N1"], "user_notes": [{"id": "N1", "text": "保留线索"}],
               **fields}
    request = {"role": role, "task": task, "chapter": 12,
               "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    return request, compass, bible


@pytest.mark.parametrize("task", ["plan", "finalize"])
def test_fake_new_editor_tasks_satisfy_final_solo_decision_schema(task):
    objection_ids = [] if task == "plan" else ["O1", "O2", "A1"]
    request, compass, bible = _request(task, objection_ids=objection_ids)
    result = FakeLLM().default_response(request)
    normalized = validate_decision(
        result, compass=compass, bible=bible, chapter=12, mode="final",
        proposal_ids=[], objection_ids=objection_ids, note_ids=["N1"], solo=True,
    )
    assert normalized["chosen_proposal_ids"] == []
    assert normalized["ending_status"] == "end"
    assert normalized["beat_sheet"]["foreshadowing_resolve"] == ["F001"]
    assert [item["objection_id"] for item in normalized["objection_responses"]] == objection_ids
    assert [item["note_id"] for item in normalized["user_note_responses"]] == ["N1"]
    if task == "finalize":
        alternative_reply = normalized["objection_responses"][-1]["response"]
        assert alternative_reply.startswith("不采纳：")
        assert "需要更多既有线索铺垫" in alternative_reply


@pytest.mark.parametrize("role", ADVISORS)
def test_fake_critique_plan_produces_actionable_objections_and_twist_alternative(role):
    request, _, _ = _request("critique_plan", role=role)
    result = FakeLLM().default_response(request)
    assert 1 <= len(result["objections"]) <= 3
    assert result["keep"]
    for issue in result["objections"]:
        assert issue["severity"] in {"major", "minor"}
        assert all(issue[field] for field in ("target", "problem", "suggestion"))
    if role == "twist_designer":
        assert 80 <= len(result["alternative"]) <= 200
    else:
        assert not result.get("alternative")


def test_default_decision_fake_still_selects_a_proposal_and_responds_as_before():
    request, _, _ = _request("decision", solo=False, proposals=[{"id": "P1"}],
                             objection_ids=["O1"])
    result = FakeLLM().default_response(request)
    assert result["chosen_proposal_ids"] == ["P1"]
    assert result["objection_responses"] == [
        {"objection_id": "O1", "response": "安排保管记录解释证据来源。"},
    ]


def test_exp_a2_config_has_exact_requested_story_models_and_arms():
    config = json.loads((CONFIG_DIRECTORY / "expA2.json").read_text(encoding="utf-8"))
    original = json.loads((CONFIG_DIRECTORY / "expA.json").read_text(encoding="utf-8"))
    assert config["experiment"] == "A"
    assert config["panel_mode"] == "critique"
    assert config["arms"] == original["arms"]
    assert config["chapters_per_arm"] == 5
    assert config["user_notes"] == {}
    assert config["target"] == {"min_chapters": 50, "max_chapters": 70, "chapter_words": 2000}
    assert config["adaptation"] == original["adaptation"]
    assert config["agents"] == {
        "editor": "anthropic:claude-sonnet-5-5", "plot_architect": "dashscope:qwen3.8-max",
        "character_advocate": "ark:doubao-seed-2-1-pro-260915",
        "twist_designer": "anthropic:claude-haiku-5-5", "writer": "deepseek:deepseek-flash",
        "reviewer": "dashscope:qwen3.8-max", "archivist": "dashscope:qwen3.8-max",
    }
    assert config["seed_idea"] == (
        "一个在殡仪馆做遗容化妆的年轻女人，某天推进来的遗体，是一张和她一模一样的脸——可她从小被告知自己是独生女。"
        "随后她发现，死者身上的旧伤疤，和她母亲多年来闭口不提的那场火灾，对得上。"
        "基调：家庭悬疑加情感，克制细腻，每章揭开一层家族秘密。"
    )
    validate_agents(config)
