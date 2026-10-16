"""Manual evaluation stays offline until an explicit, sufficient budget."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from scripts import studio_brain_eval as evaluation
from studio import brain as real_brain, pricing
from studio.config import get_settings


@pytest.fixture
def runtime(monkeypatch):
    events = []

    class InvalidOutput(ValueError):
        def __init__(self):
            self.errors = ["schema mismatch"]

    class Provider:
        def __init__(self, provider, model):
            self.provider, self.model = provider, model

        def pin_vision_model(self, model):
            self.model = model

        async def call(self, task, inputs, *, images=None, repair=None):
            events.append({"provider": self.provider, "model": self.model, "task": task,
                           "images": images, "repair": repair})
            return SimpleNamespace(text="invalid" if task == "read_through" and repair is None else "valid",
                usage={"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0},
                model=self.model, stop_reason="end_turn", latency_s=.25, warnings=[])

    def validate(task, reply, inputs):
        if reply.text == "invalid":
            raise InvalidOutput()
        return {"result": "评测结果"}, ["软约束提示"]

    brain = SimpleNamespace(
        ClaudeProvider=lambda config: Provider("claude", config["model"]),
        QwenProvider=lambda **kwargs: Provider("qwen", kwargs.get("model", "qwen3.8-max")),
        DeepSeekProvider=lambda **kwargs: Provider("deepseek", "deepseek-v4-pro"),
        estimate_input_chars=lambda task, inputs, repair=None: len(json.dumps([task, inputs, repair], ensure_ascii=False)),
        validate_reply=validate, InvalidBrainOutput=InvalidOutput, VISION_WARNING=real_brain.VISION_WARNING)
    tasks = SimpleNamespace(get_task=lambda task: SimpleNamespace(max_tokens=64))
    monkeypatch.setattr(evaluation, "_runtime", lambda: (brain, tasks, pricing))
    for name in ("ANTHROPIC_API_KEY", "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.setenv(name, "offline-placeholder")
    return brain, events


def test_quote_without_authorization_never_builds_client_or_opens_database(runtime, monkeypatch, tmp_path, capsys):
    import aiosqlite
    import sqlite3

    def forbidden(*args, **kwargs):
        pytest.fail("quoting must not open a database or instantiate a provider")

    monkeypatch.setattr(aiosqlite, "connect", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(evaluation, "_provider", forbidden)
    output = tmp_path / "reports"
    assert evaluation.main(["--text", "离线素材", "--output-dir", str(output)]) == 2
    assert evaluation.main(["--text", "离线素材", "--yes-spend", "0", "--output-dir", str(output)]) == 2
    assert not output.exists()
    assert "USD" in capsys.readouterr().out


def test_all_keys_are_checked_before_any_provider_request(runtime, monkeypatch, tmp_path):
    _brain, events = runtime
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    assert evaluation.main(["--text", "素材", "--yes-spend", "100", "--output-dir", str(tmp_path)]) == 1
    assert events == [] and list(tmp_path.iterdir()) == []


def test_approved_eval_uses_provider_classes_and_writes_parallel_report(runtime, tmp_path):
    _brain, events = runtime
    image = tmp_path / "frame.png"
    image.write_bytes(b"offline-image-placeholder")
    output = tmp_path / "reports"
    original = "私有原文不应写入报告。"
    assert evaluation.main(["--text", original, "--image", str(image), "--yes-spend", "100",
                            "--output-dir", str(output)]) == 0
    reports = list(output.glob("*.md"))
    assert len(reports) == 1
    content = reports[0].read_text()
    assert "| 任务 | Claude | 千问 | DeepSeek |" in content
    for text in ("usage=", "费用", "耗时", "已修正：是", "软约束提示", real_brain.VISION_WARNING.format(model=get_settings().vision_model), "评测结果"):
        assert text in content
    assert original not in content
    assert len(events) == 15
    vision = [event for event in events if event["images"]]
    assert [event["provider"] for event in vision] == ["claude", "qwen", "qwen"]
    assert vision[-1]["model"] == get_settings().vision_model
    assert all(event["images"] == [image] for event in vision)


def test_second_invalid_response_has_no_third_request(runtime, tmp_path):
    brain, events = runtime

    def invalid(*args):
        raise brain.InvalidBrainOutput()

    brain.validate_reply = invalid
    args = evaluation.build_parser().parse_args(["--text", "素材", "--providers", "qwen"])
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[:1]))
    assert result[0]["status"] == "invalid_output"
    assert len(result[0]["attempts"]) == len(events) == 2
    assert result[0]["repaired"] is True


def test_uncertain_provider_error_is_not_retried(runtime, monkeypatch):
    brain, events = runtime

    class Timeout:
        async def call(self, *args, **kwargs):
            events.append("timeout")
            raise TimeoutError("source and key must never be reported")

    monkeypatch.setattr(evaluation, "_provider", lambda *args: Timeout())
    args = evaluation.build_parser().parse_args(["--text", "素材", "--providers", "qwen"])
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[:1]))
    assert result[0]["status"] == "uncertain"
    assert result[0]["error_code"] == "TimeoutError"
    assert events == ["timeout"]
    assert len(result[0]["attempts"]) == 1
    assert result[0]["attempts"][0]["cost"]["amount"] is None
    assert "可能已扣费" in result[0]["attempts"][0]["request_state"]


def test_unknown_snapshot_response_model_uses_reserved_price(runtime, monkeypatch):
    class Snapshot:
        async def call(self, *args, **kwargs):
            return SimpleNamespace(text="valid", model="qwen3.8-max-snapshot-20261016",
                usage={"input_tokens": 10, "output_tokens": 5}, stop_reason="stop", latency_s=.1, warnings=[])

    monkeypatch.setattr(evaluation, "_provider", lambda *args: Snapshot())
    args = evaluation.build_parser().parse_args(["--text", "素材", "--providers", "qwen"])
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[1:2]))
    assert result[0]["status"] == "succeeded"
    attempt = result[0]["attempts"][0]
    assert attempt["model"] == "qwen3.8-max-snapshot-20261016"
    assert attempt["cost"] == {"currency": "CNY", "amount": plan[1]["first_max"]}
    assert "fallback 模型单价未配置，按预留计" in result[0]["warnings"]


def test_real_quote_uses_task_and_pricing_interfaces_without_database(monkeypatch, tmp_path):
    import aiosqlite
    from studio import brain

    def forbidden(*args, **kwargs):
        pytest.fail("real quote must not instantiate SDKs or open database")

    monkeypatch.setattr(aiosqlite, "connect", forbidden)
    for name in ("ClaudeProvider", "QwenProvider", "DeepSeekProvider"):
        monkeypatch.setattr(brain, name, forbidden)
    assert evaluation.main(["--text", "风停了，女孩捡起桌上的钥匙。", "--output-dir", str(tmp_path / "eval")]) == 2
    assert not (tmp_path / "eval").exists()
