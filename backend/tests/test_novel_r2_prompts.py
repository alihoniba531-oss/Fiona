"""Round-two output, review, and concrete-length prompt regressions."""

import asyncio
from copy import deepcopy
import json

import pytest

from novel import agent_pool
from novel.agent_pool import AGENTS, INJECTION_GUARD, get_agent
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.prompt_rules import JSON_STRING_QUOTE_RULE
from novel.run_store import RunStore


DELIBERATION_ROLES = [
    "plot_architect", "character_advocate", "reader_rep", "twist_designer",
    "pacing_advisor", "adaptation_advisor",
]
JSON_ROLE_TASKS = [
    ("editor", "setup"), ("editor", "decision"),
    *[(role, task) for role in DELIBERATION_ROLES for task in ("proposal", "critique")],
    ("reviewer", "review"), ("archivist", "archive"), ("corrupter", "corrupt"),
]


@pytest.fixture(autouse=True)
def reject_real_provider_calls(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("these regressions must use only the offline fake provider")

    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden)


def test_quote_rule_is_the_requested_shared_instruction():
    assert JSON_STRING_QUOTE_RULE == (
        'JSON 字符串值内部不得出现英文双引号 "；需要引用原文、人物台词或圣经内容时，'
        '一律使用中文直角引号「」。'
    )


@pytest.mark.parametrize("schema", [
    "SETUP_SCHEMA", "PROPOSAL_SCHEMA", "DECISION_SCHEMA", "REVIEW_SCHEMA",
    "ARCHIVE_SCHEMA", "CORRUPTER_SCHEMA",
])
def test_json_schema_ends_with_shared_quote_rule(schema):
    assert getattr(agent_pool, schema).splitlines()[-1] == JSON_STRING_QUOTE_RULE


@pytest.mark.parametrize("role,task", JSON_ROLE_TASKS)
def test_every_json_task_has_quote_rule_before_final_injection_guard(role, task):
    card = get_agent(role, task=task)
    assert card["output"] == "json"
    assert card["system_prompt"].splitlines()[-2:] == [JSON_STRING_QUOTE_RULE, INJECTION_GUARD]
    assert card["system_prompt"].count(JSON_STRING_QUOTE_RULE) == 1


@pytest.mark.parametrize("words,minimum,maximum", [
    (1, 1, 1), (4, 3, 6), (100, 60, 160), (1500, 900, 2400),
    (1501, 901, 2401), (2000, 1200, 3200), (2001, 1201, 3201),
    (2500, 1500, 4000),
])
def test_writer_gets_concrete_integer_range_without_json_rule(words, minimum, maximum):
    before = deepcopy(AGENTS)
    card = get_agent("writer", chapter_words=words)
    assert (
        f"正文（不计空白）目标 {words} 字，必须在 {minimum}–{maximum} 字之间；"
        "宁可略短，不要超过上限。"
    ) in card["system_prompt"]
    assert "{target}" not in card["system_prompt"]
    assert "{min}" not in card["system_prompt"] and "{max}" not in card["system_prompt"]
    assert "target_words 的0.6–1.6倍" not in card["system_prompt"]
    assert JSON_STRING_QUOTE_RULE not in card["system_prompt"]
    assert card["system_prompt"].splitlines()[-1] == INJECTION_GUARD
    assert card["output"] == "markdown"
    assert AGENTS == before


@pytest.mark.parametrize("rule", [
    "只有以下三类问题可以判为阻断（blocking=true）",
    "读者会明显察觉的前后矛盾",
    "人物在两处同时出现",
    "已经死去的人又出现",
    "与锁定设定直接冲突",
    "外形或身份被写成另一个样子",
    "foreshadowing_plant、foreshadowing_resolve 所要求的伏笔",
    "漏掉细纲的核心节拍",
    "同义表述、数字的中文写法与阿拉伯数字写法、措辞的详略差异，都不算矛盾",
    "只有正文明确写出某人知道了他不可能知道的事，才算矛盾",
    "不能把 knows 当作排除其他合理知识来源的完整清单",
    "拿不准时一律 blocking=false",
    "每轮最多 3 条阻断问题，按严重程度排序",
    "收到 previous_blocking_issues 表示复审",
    "先逐条判断上一轮的阻断问题是否已经解决",
    "新发现的问题只有属于上述三类中的严重情况，才可以判为阻断，否则 blocking=false",
    "style 和 adaptation 一律 blocking=false",
])
def test_review_prompt_contains_narrow_blocking_and_rereview_rules(rule):
    assert rule in get_agent("reviewer")["system_prompt"]


@pytest.mark.parametrize("task", ["setup", "proposal", "critique", "decision", "review", "archive", "corrupt"])
@pytest.mark.parametrize("failure", ["parse", "schema", "truncation"])
def test_json_repair_replays_output_and_reuses_quote_instruction(tmp_path, task, failure):
    raw = '{"problem":"正文说"二十四岁"}' if failure == "parse" else '{"ok":false}'
    first = (raw, {}, "max_tokens") if failure == "truncation" else raw
    fake = FakeLLM({task: [first, {"ok": True}]})
    store = RunStore(tmp_path, {})
    router = LLMRouter(store, fake=fake)

    def validate(result):
        if result.get("ok") is not True:
            raise ValueError("missing required result")
        return result

    result = asyncio.run(router.call(
        step_key="steps/repair.json", role="editor", model="fake:offline",
        messages=[{"role": "system", "content": "Return a JSON object."},
                  {"role": "user", "content": json.dumps({"task": task})}],
        max_tokens=1000, validator=validate, output="json",
    ))
    assert result == {"ok": True}
    assert len(fake.calls) == 2
    retry_messages = fake.calls[1]["messages"]
    assert [message["role"] for message in retry_messages] == ["system", "user", "assistant", "user"]
    assert retry_messages[-2]["content"] == raw
    repair = json.loads(retry_messages[-1]["content"])
    assert repair["修正要求"].splitlines()[-1] == JSON_STRING_QUOTE_RULE
    assert repair["修正要求"].count(JSON_STRING_QUOTE_RULE) == 1
    assert store.read_json("steps/repair.json")["status"] == "ok"


@pytest.mark.parametrize("failure", ["schema", "truncation"])
def test_markdown_repair_keeps_quoted_prose_free_of_json_restriction(tmp_path, failure):
    raw = '# 第1章 灯下\n她说："证据在这里。"'
    first = (raw, {}, "max_tokens") if failure == "truncation" else raw
    accepted = raw + "\n所有人停住了脚步。"
    fake = FakeLLM({"write": [first, accepted]})

    def validate(result):
        if result != accepted:
            raise ValueError("draft too short")
        return result

    result = asyncio.run(LLMRouter(RunStore(tmp_path, {}), fake=fake).call(
        step_key="steps/write.json", role="writer", model="fake:offline",
        messages=[{"role": "system", "content": get_agent("writer")["system_prompt"]},
                  {"role": "user", "content": json.dumps({"task": "write"})}],
        max_tokens=1000, validator=validate, output="markdown",
    ))
    assert result == accepted
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"][-2]["content"] == raw
    repair = json.loads(fake.calls[1]["messages"][-1]["content"])
    assert JSON_STRING_QUOTE_RULE not in repair["修正要求"]
    assert JSON_STRING_QUOTE_RULE not in fake.calls[1]["messages"][0]["content"]
