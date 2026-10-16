import asyncio
import json
from functools import wraps
from types import SimpleNamespace

import pytest

from novel.fake_llm import FakeLLM
from novel.llm_router import (
    BudgetExhausted, ConfigurationError, LLMRouter, StepFailed,
    normalize_anthropic_usage, normalize_openai_usage, validate_environment,
)
from novel.run_store import RunStore
from novel.schemas import ValidationError


def run_async(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapped


def options(**overrides):
    result = dict(step_key="steps/one.json", role="editor", model="fake:offline", max_tokens=100,
                  messages=[{"role": "user", "content": json.dumps({"task": "setup"})}])
    result.update(overrides)
    return result


@run_async
async def test_novel_router_cache_avoids_calls_and_duplicate_usage(tmp_path):
    fake = FakeLLM(script={"setup": [{"value": 1}]})
    store = RunStore(tmp_path, {}, dry_run=True)
    router = LLMRouter(store, fake=fake, dry_run=True)
    assert await router.call(**options()) == {"value": 1}
    result = await router.call(**options())
    result["value"] = 99
    assert (await router.call(**options()))["value"] == 1
    assert fake.call_count == 1
    assert len(store.usage) == 1
    step = store.read_json("steps/one.json")
    assert step["status"] == "ok" and step["attempts"] == 1
    assert step["usage"]["input_tokens"] == len(options()["messages"][0]["content"])


@run_async
async def test_novel_router_repairs_json_once_and_keeps_chinese_errors(tmp_path):
    fake = FakeLLM({"setup": ["not JSON PRIVATE_RESPONSE", {"fixed": True}]})
    store = RunStore(tmp_path, {})
    result = await LLMRouter(store, fake=fake).call(**options())
    assert result == {"fixed": True}
    assert fake.call_count == 2
    repair = fake.calls[1]["messages"][-1]["content"]
    assert "校验错误" in repair and "PRIVATE_RESPONSE" not in repair
    assert store.read_json("steps/one.json")["attempts"] == 2
    assert len(store.usage) == 2 and all(row["attempts"] == 1 for row in store.usage)
    assert [row["ok"] for row in store.usage] == [False, True]


@run_async
async def test_novel_router_two_bad_responses_preserve_failed_step(tmp_path):
    store = RunStore(tmp_path, {})
    router = LLMRouter(store, fake=FakeLLM({"setup": ["bad", "still bad"]}))
    with pytest.raises(StepFailed) as failure:
        await router.call(**options(failure_status="decision_invalid"))
    assert failure.value.exit_code == 4 and failure.value.status == "decision_invalid"
    step = store.read_json("steps/one.json")
    assert step["status"] == "decision_invalid" and step["attempts"] == 2


@run_async
async def test_novel_router_schema_error_gets_one_repair(tmp_path):
    fake = FakeLLM({"setup": [{"count": -1}, {"count": 2}]})

    def validate(value):
        if value["count"] < 0:
            raise ValidationError(["count：必须为正数"])
        return {"count": value["count"], "validated": True}

    router = LLMRouter(RunStore(tmp_path, {}), fake=fake)
    assert await router.call(**options(validator=validate)) == {"count": 2, "validated": True}
    assert "必须为正数" in fake.calls[1]["messages"][-1]["content"]


@run_async
async def test_novel_router_network_timeout_retries_once(tmp_path, monkeypatch):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("novel.llm_router.asyncio.sleep", sleep)
    fake = FakeLLM({"setup": [TimeoutError("private upstream text"), {"ok": True}]})
    store = RunStore(tmp_path, {})
    assert await LLMRouter(store, fake=fake).call(**options()) == {"ok": True}
    assert sleeps == [5] and fake.call_count == 2
    assert [row["ok"] for row in store.usage] == [False, True]
    assert "private upstream text" not in (tmp_path / "steps/one.json").read_text()


@run_async
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_novel_router_http_retry_rules(tmp_path, status):
    class HTTPFailure(Exception):
        status_code = status
    router = LLMRouter(RunStore(tmp_path, {}), fake=FakeLLM({"setup": [HTTPFailure(), {"ok": True}]}))
    router.retry_delay = 0
    assert await router.call(**options()) == {"ok": True}


@run_async
async def test_novel_router_non_retryable_failure_stops_immediately(tmp_path):
    fake = FakeLLM({"setup": [RuntimeError("sentinel-do-not-record"), {"ok": True}]})
    store = RunStore(tmp_path, {})
    with pytest.raises(StepFailed):
        await LLMRouter(store, fake=fake).call(**options())
    assert fake.call_count == 1
    assert "sentinel-do-not-record" not in (tmp_path / "steps/one.json").read_text()


@run_async
async def test_novel_router_budget_prevents_call_and_can_resume(tmp_path):
    fake = FakeLLM({"setup": [{"ok": True}]})
    first = RunStore(tmp_path, {}, max_total_tokens=1)
    with pytest.raises(BudgetExhausted) as exhausted:
        await LLMRouter(first, fake=fake).call(**options())
    assert exhausted.value.exit_code == 3 and fake.call_count == 0
    assert first.usage == []
    resumed = RunStore(tmp_path, {}, max_total_tokens=10_000)
    assert await LLMRouter(resumed, fake=fake).call(**options()) == {"ok": True}


@run_async
async def test_novel_router_parallel_budget_reservations_are_atomic(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def scripted(request, index):
        entered.set()
        await release.wait()
        return {"ok": True}

    fake = FakeLLM(scripted)
    store = RunStore(tmp_path, {}, max_total_tokens=150)
    router = LLMRouter(store, fake=fake)
    first = asyncio.create_task(router.call(**options(step_key="one.json")))
    await entered.wait()
    with pytest.raises(BudgetExhausted):
        await asyncio.wait_for(router.call(**options(step_key="two.json")), 5)
    assert fake.call_count == 1
    release.set()
    await first
    assert store.reserved_tokens == 0


@run_async
async def test_novel_router_resume_after_failure_reuses_completed_steps(tmp_path):
    fake = FakeLLM(script=[{"one": 1}, RuntimeError("interruption")])
    store = RunStore(tmp_path, {})
    router = LLMRouter(store, fake=fake)
    assert await router.call(**options(step_key="one.json")) == {"one": 1}
    with pytest.raises(StepFailed):
        await router.call(**options(step_key="two.json"))
    second_fake = FakeLLM(script=[{"two": 2}])
    resumed = LLMRouter(RunStore(tmp_path, {}), fake=second_fake)
    assert await resumed.call(**options(step_key="one.json")) == {"one": 1}
    assert second_fake.call_count == 0
    assert await resumed.call(**options(step_key="two.json")) == {"two": 2}
    assert second_fake.call_count == 1


@run_async
async def test_novel_router_dry_run_never_constructs_sdk(tmp_path, monkeypatch):
    import anthropic
    import openai

    def forbidden(*args, **kwargs):
        raise AssertionError("real client constructed")

    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", forbidden)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://polluted.invalid")
    router = LLMRouter(RunStore(tmp_path, {}, dry_run=True), dry_run=True)
    result = await router.call(**options(model="anthropic:unused"))
    assert result["title"] == "未发送的自己"


@pytest.mark.parametrize("pollution", ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "OPENAI_BASE_URL"])
def test_novel_router_environment_guard_reports_names_only(pollution):
    with pytest.raises(ConfigurationError) as failure:
        validate_environment(["anthropic:test"], environ={pollution: "private-sentinel"})
    assert pollution in str(failure.value) and "unset" in str(failure.value)
    assert "private-sentinel" not in str(failure.value)


def test_novel_router_environment_only_checks_used_keys():
    validate_environment(["deepseek:test"], environ={"DEEPSEEK_API_KEY": "placeholder"})
    with pytest.raises(ConfigurationError) as failure:
        validate_environment(["anthropic:test"], environ={})
    assert str(failure.value) == "缺少环境变量：ANTHROPIC_API_KEY"


def test_novel_router_fake_and_dry_run_do_not_inspect_environment():
    class Unreadable(dict):
        def get(self, *args):
            raise AssertionError("environment inspected")
    validate_environment(["fake:test"], environ=Unreadable())
    validate_environment(["anthropic:test"], dry_run=True, environ=Unreadable())


def test_novel_router_provider_usage_normalization():
    usage = SimpleNamespace(prompt_tokens=20, completion_tokens=8,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=4))
    assert normalize_openai_usage(usage) == {"input_tokens": 20, "output_tokens": 8, "cached_tokens": 4}
    assert normalize_openai_usage({"prompt_tokens": 10, "completion_tokens": 3, "prompt_cache_hit_tokens": 2})["cached_tokens"] == 2
    assert normalize_anthropic_usage({"input_tokens": 11, "output_tokens": 7, "cache_read_input_tokens": 6}) == {
        "input_tokens": 11, "output_tokens": 7, "cached_tokens": 6}


@run_async
async def test_novel_fake_script_matching_and_callable_index():
    fake = FakeLLM({"specific.json": [{"selected": "step"}], "setup": [{"selected": "task"}]})
    first = {**options(step_key="specific.json"), "task": "setup"}
    second = {**options(step_key="other.json"), "task": "setup"}
    assert json.loads((await fake(first))[0])["selected"] == "step"
    assert json.loads((await fake(second))[0])["selected"] == "task"
    dynamic = FakeLLM(lambda request, index: {"index": index, "task": request["task"]})
    assert json.loads((await dynamic(first))[0]) == {"index": 1, "task": "setup"}
