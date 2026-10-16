"""R1 evaluation parity: complete failures settle, truncation never repairs."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts import studio_brain_eval as evaluation
from studio import brain, brain_tasks, pricing
from test_studio_brain_core import READ_RESULT
import json

USAGE = {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 100,
         "cache_creation_input_tokens": 200}


def _case(provider):
    args = evaluation.build_parser().parse_args(["--text", "旅人在渡口等船。", "--providers", provider])
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    return args, plan


def _client(monkeypatch, replies):
    calls = []

    class Provider:
        async def call(self, task, inputs, *, images=None, repair=None):
            calls.append(repair)
            reply = replies[len(calls) - 1]
            if isinstance(reply, Exception):
                raise reply
            return reply

    monkeypatch.setattr(evaluation, "_provider", lambda *args: Provider())
    return calls


@pytest.mark.parametrize("provider,stop", [("claude", "max_tokens"), ("qwen", "length"), ("deepseek", "length")])
def test_truncation_settles_one_attempt_without_repair(monkeypatch, provider, stop):
    args, plan = _case(provider)
    reply = brain.BrainReply('{"logline":', usage=USAGE, model=plan[0]["model"], stop_reason=stop, latency_s=1.25)
    calls = _client(monkeypatch, [reply])
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[:1]))[0]
    assert calls == [None]
    assert result["status"] == "invalid_output" and result["error_code"] == "max_tokens"
    assert result["error_message"] == "输出超长被截断，请缩短素材或减少勾选的任务"
    assert result["repaired"] is False
    assert result["attempts"][0]["cost"] == pricing.brain_actual_cost(reply.model, USAGE)


@pytest.mark.parametrize("provider,code,stop", [("claude", "refusal", "refusal"),
    ("claude", "empty_output", "end_turn"), ("qwen", "content_filter", "content_filter"),
    ("deepseek", "content_filter", "content_filter")])
def test_complete_failed_response_preserves_usage_and_settles(monkeypatch, provider, code, stop):
    args, plan = _case(provider)
    error = brain.BrainProviderError("failed", code, "导演模型没有返回内容",
        usage=USAGE, model=plan[0]["model"], stop_reason=stop, latency_s=1.25)
    calls = _client(monkeypatch, [error])
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[:1]))[0]
    assert calls == [None] and result["status"] == "failed"
    attempt = result["attempts"][0]
    assert attempt["usage"] == USAGE and attempt["stop_reason"] == stop and attempt["latency_s"] == 1.25
    assert attempt["cost"] == pricing.brain_actual_cost(error.model, USAGE)
    assert attempt["cost"]["amount"] < plan[0]["first_max"]


@pytest.mark.parametrize("actual", ["claude-sonnet-5-5", "claude-unpriced-fallback-r1"])
def test_fallback_uses_actual_model_price_or_this_attempt_reserve(monkeypatch, actual):
    args, plan = _case("claude")
    reply = brain.BrainReply(json.dumps(READ_RESULT), usage=USAGE, model=actual, stop_reason="end_turn")
    _client(monkeypatch, [reply])
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[:1]))[0]
    assert result["status"] == "succeeded"
    assert result["attempts"][0]["model"] == actual
    if actual == "claude-sonnet-5-5":
        assert result["attempts"][0]["cost"] == pricing.brain_actual_cost(actual, USAGE)
        assert result["warnings"] == []
    else:
        assert result["attempts"][0]["cost"] == {"currency": "USD", "amount": plan[0]["first_max"]}
        assert result["warnings"] == ["fallback 模型单价未配置，按预留计"]


def test_repair_fallback_consumes_repair_reserve_and_keeps_warning(monkeypatch):
    args, plan = _case("claude")
    first = brain.BrainReply("bad json", usage=USAGE, model=plan[0]["model"], stop_reason="end_turn")
    second = brain.BrainReply(json.dumps(READ_RESULT), usage=USAGE, model="claude-unpriced-fallback-r1", stop_reason="end_turn")
    calls = _client(monkeypatch, [first, second])
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[:1]))[0]
    assert len(calls) == 2 and calls[1] is not None
    assert result["status"] == "succeeded" and result["repaired"]
    assert result["attempts"][1]["cost"]["amount"] == plan[0]["repair_max"]
    assert plan[0]["repair_max"] > plan[0]["first_max"]
    assert "fallback 模型单价未配置，按预留计" in result["warnings"]


def test_repair_quote_has_fixed_token_overhead_and_exact_amount(monkeypatch):
    monkeypatch.delenv(pricing.brain_price_env("qwen3.8-max"), raising=False)
    monkeypatch.setattr(brain, "estimate_input_chars", lambda *args, **kwargs: 1000)
    args, plan = _case("qwen")
    first = plan[0]
    assert brain_tasks.get_task("read_through").max_tokens == 4096
    assert pricing.REPAIR_OVERHEAD_TOKENS == 2048
    assert first["first_max"] == .107304  # (1500*6 + 4096*24) / 1M
    assert first["repair_max"] == .144168  # (1500+4096+2048)*6 + 4096*24
    assert first["maximum"] == Decimal("0.251472")
