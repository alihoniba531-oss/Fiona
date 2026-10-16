"""R1-A/C/D/E: offline single-call settlement and bounded repair quotes."""
import asyncio
from decimal import Decimal
import json

import pytest

from studio import brain, brain_jobs, pricing, spend, store
from test_studio_brain_orchestration import GOOD, MODELS, orchestration  # noqa: F401

USAGE = {"input_tokens": 100, "output_tokens": 50,
         "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 20}


def run(coro):
    return asyncio.run(coro)


def install(monkeypatch, replies, model="claude-sonnet-5-5"):
    calls = []

    class Adapter:
        async def call(self, task, inputs, *, images=None, repair=None):
            calls.append({"model": self.model, "repair": repair})
            result = replies[min(len(calls) - 1, len(replies) - 1)]
            if isinstance(result, Exception):
                raise result
            return result

    async def provider(*args, **kwargs):
        adapter = Adapter()
        adapter.model = model
        return adapter

    monkeypatch.setattr(brain, "get_provider", provider)
    return calls


def response(model="claude-sonnet-5-5", *, stop="end_turn", output=GOOD):
    return brain.BrainReply(json.dumps(output), USAGE, model, stop, .25)


async def execute(owner, project, provider):
    await brain_jobs.patch_project(project["id"], owner, provider)
    group = await brain_jobs.start_trial(project["id"], owner, "阿宁送还旧信。", ["read_through"], "current")
    before = group["jobs"][0]
    await brain_jobs._background(before["id"])
    return before, await brain_jobs.group(project["id"], owner, group["group_id"])


@pytest.mark.parametrize("provider", MODELS)
def test_r1_a_truncation_never_repairs_and_settles_actual_usage(orchestration, monkeypatch, provider):
    owner, project = orchestration
    stop = "max_tokens" if provider == "claude" else "length"
    calls = install(monkeypatch, [response(MODELS[provider], stop=stop)], MODELS[provider])
    before, group = run(execute(owner, project, provider))
    assert len(calls) == 1 and calls[0]["repair"] is None
    assert len(group["jobs"]) == 1
    job = group["jobs"][0]
    assert job["status"] == "invalid_output" and job["error_code"] == "max_tokens"
    assert job["error_message"] == "输出超长被截断，请缩短素材或减少勾选的任务"
    assert job["usage"] == USAGE
    assert job["cost"] == pricing.brain_actual_cost(MODELS[provider], USAGE)
    assert float(job["reserved_amount"]) == 0 and job["reserved_cny"] == 0
    assert job["cost"]["amount"] < float(before["reserved_amount"])


@pytest.mark.parametrize("provider,code", [("claude", "refusal"), ("claude", "empty_output"),
                                           ("qwen", "content_filter"), ("deepseek", "content_filter")])
def test_r1_c_complete_failed_response_settles_and_does_not_repair(orchestration, monkeypatch, provider, code):
    owner, project = orchestration
    error = brain.BrainProviderError("failed", code, "导演模型没有返回内容", usage=USAGE,
                                    model=MODELS[provider], stop_reason=code, latency_s=.2)
    calls = install(monkeypatch, [error], MODELS[provider])
    _before, group = run(execute(owner, project, provider))
    job = group["jobs"][0]
    assert len(calls) == len(group["jobs"]) == 1
    assert job["status"] == "failed" and job["error_code"] == code
    assert job["usage"] == USAGE and job["stop_reason"] == code and job["latency_s"] == .2
    assert job["cost"] == pricing.brain_actual_cost(MODELS[provider], USAGE)
    assert float(job["reserved_amount"]) == 0 and job["reserved_cny"] == 0


def test_r1_d_cache_writes_cost_one_and_a_quarter_of_base_price():
    # USD: (100 + 20*1.25)*4 + 1000*.2 + 50*20 = 1700 / million.
    assert pricing.brain_actual_cost("claude-opus-5-5", USAGE) == {"currency": "USD", "amount": .0017}
    read_only = {**USAGE, "cache_creation_input_tokens": 0}
    assert pricing.brain_actual_cost("claude-opus-5-5", read_only)["amount"] == .0016


@pytest.mark.parametrize("actual_model", ["claude-opus-5-5", "claude-fallback-unlisted"])
def test_r1_d_actual_fallback_model_prices_or_settles_exact_reserve(orchestration, monkeypatch, actual_model):
    owner, project = orchestration
    calls = install(monkeypatch, [response(actual_model)])
    before, group = run(execute(owner, project, "claude"))
    job = group["jobs"][0]
    assert len(calls) == 1 and job["status"] == "succeeded" and job["model"] == actual_model
    if actual_model == "claude-opus-5-5":
        expected = pricing.brain_actual_cost(actual_model, USAGE)["amount"]
        assert expected != pricing.brain_actual_cost("claude-sonnet-5-5", USAGE)["amount"]
        assert job["warnings"] == []
    else:
        expected = float(before["reserved_amount"])
        assert job["warnings"] == ["fallback 模型单价未配置，按预留计"]
    assert job["cost"] == {"currency": "USD", "amount": expected}
    assert float(job["reserved_amount"]) == 0
    assert run(spend.brain_month_used(owner)) == Decimal(str(expected))


def test_r1_d_unknown_fallback_first_attempt_can_repair_using_requested_model(orchestration, monkeypatch):
    owner, project = orchestration
    calls = install(monkeypatch, [response("claude-fallback-unlisted", output={}), response()])
    before, group = run(execute(owner, project, "claude"))
    assert len(calls) == 2
    assert [job["status"] for job in group["jobs"]] == ["invalid_output", "succeeded"]
    assert group["jobs"][0]["cost"]["amount"] == float(before["reserved_amount"])
    assert calls[0]["model"] == calls[1]["model"] == "claude-sonnet-5-5"
    assert "fallback 模型单价未配置，按预留计" in group["jobs"][1]["warnings"]


@pytest.mark.parametrize("model,first,repair,total", [
    ("claude-sonnet-5-5", .08267, .11339, .19606),
    ("qwen3.8-max", .099204, .136068, .235272),
])
def test_r1_e_quote_exact_token_ceiling_not_character_multiplier(monkeypatch, model, first, repair, total):
    monkeypatch.setattr(brain, "estimate_input_chars", lambda *args, **kwargs: 100)
    quote = brain_jobs._quote_item("claude" if model.startswith("claude") else "qwen", model,
                                   "read_through", {"text": "原文"})
    assert pricing.REPAIR_OVERHEAD_TOKENS == 2048
    assert quote["first_max"] == first
    assert quote["repair_max"] == repair
    assert quote["amount"] == total
    assert pricing.estimate_brain_repair(model, 100, 4096) == {
        "currency": quote["currency"], "amount": repair}


def test_r1_e_repair_reservation_matches_quoted_upper_bound(orchestration, monkeypatch):
    owner, project = orchestration
    calls = install(monkeypatch, [response(output={}), response()])
    quoted = run(brain_jobs.quote_trial(project["id"], owner, "阿宁送还旧信。", ["read_through"], "current"))
    _before, group = run(execute(owner, project, "claude"))
    assert len(calls) == 2
    # The reservation was released after settlement; estimated_max is CNY-only,
    # so observe the deterministic helper used before both inserts.
    expected = pricing.estimate_brain_repair("claude-sonnet-5-5",
        brain.estimate_input_chars("read_through", {"text": "阿宁送还旧信。"}), 4096)["amount"]
    assert quoted["items"][0]["repair_max"] == expected
    assert group["jobs"][1]["attempt"] == 2


def test_r1_d_reserve_covers_full_cache_creation_and_known_expensive_fallback():
    quote = pricing.estimate_brain("claude-sonnet-5-5", 100, 4096)
    worst = {"input_tokens": 0, "output_tokens": 4096,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 150}
    assert quote["amount"] == pricing.brain_actual_cost("claude-opus-5-5", worst)["amount"] == .08267
    haiku = pricing.estimate_brain("claude-haiku-5-5", 100, 4096)
    assert haiku["amount"] == pricing.brain_actual_cost("claude-haiku-5-5", worst)["amount"] == .00206675
