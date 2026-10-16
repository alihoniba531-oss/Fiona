"""R2 evaluation uses the live vision setting without spending during quote."""
import asyncio
import json
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from scripts import studio_brain_eval as evaluation
from studio import brain, pricing
from studio.config import get_settings
from test_studio_brain_eval import runtime  # noqa: F401


def _args(tmp_path, *extra):
    image = tmp_path / "frame.png"
    image.write_bytes(b"offline-placeholder")
    return evaluation.build_parser().parse_args(["--text", "素材", "--image", str(image),
        "--output-dir", str(tmp_path / "reports"), *extra])


@pytest.mark.parametrize("override", [None, "qwen3-vl-custom-r2"])
def test_eval_plan_and_provider_read_configured_vision_model(runtime, monkeypatch, tmp_path, override):
    fake_brain, events = runtime
    if override is None:
        monkeypatch.delenv("FIONA_STUDIO_VISION_MODEL", raising=False)
    else:
        monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", override)
        monkeypatch.setenv(pricing.brain_price_env(override), json.dumps({"input": 1, "output": 10}))
    args = _args(tmp_path)
    model = get_settings().vision_model
    if override is None:
        assert model == "qwen3-vl-plus"
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    vision = [item for item in plan if item["task"] == "frame_qc"]
    assert [item["model"] for item in vision] == [args.claude_model, model, model]
    assert [item["currency"] for item in vision] == ["USD", "CNY", "CNY"]
    for provider in ("qwen", "deepseek"):
        actual = evaluation._provider(fake_brain, args, provider, "frame_qc")
        asyncio.run(actual.call("frame_qc", {"text": args.text}, images=[args.image]))
    assert [event["provider"] for event in events] == ["qwen", "qwen"]
    assert all(event["model"] == model for event in events)


def test_eval_reads_changed_vision_config_on_next_plan_and_provider(runtime, monkeypatch, tmp_path):
    fake_brain, _events = runtime
    args = _args(tmp_path, "--providers", "deepseek")
    first_model = "qwen3-vl-first-r2"
    second_model = "qwen3-vl-second-r2"
    for model in (first_model, second_model):
        monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", model)
        monkeypatch.setenv(pricing.brain_price_env(model), json.dumps({"input": 1, "output": 10}))
        plan, _totals, _cap = evaluation.build_plan(args, args.text)
        assert plan[-1]["model"] == get_settings().vision_model == model
        assert evaluation._provider(fake_brain, args, "deepseek", "frame_qc").model == model


def test_missing_vision_price_rejects_quote_before_any_provider(runtime, monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "qwen3-vl-unpriced-r2")
    monkeypatch.delenv(pricing.brain_price_env(get_settings().vision_model), raising=False)
    monkeypatch.setattr(evaluation, "_provider", lambda *args: calls.append(args))
    args = _args(tmp_path, "--providers", "deepseek")
    with pytest.raises(HTTPException) as caught:
        evaluation.build_plan(args, args.text)
    assert caught.value.status_code == 409 and "单价" in caught.value.detail
    assert "FIONA_STUDIO_PRICE_" in caught.value.detail
    assert evaluation.main(["--text", args.text, "--image", str(args.image), "--providers", "deepseek",
        "--yes-spend", "100", "--output-dir", str(args.output_dir)]) == 1
    assert calls == [] and not args.output_dir.exists()
    assert "单价" in capsys.readouterr().err


def test_missing_vision_price_defensively_prevents_provider_construction(runtime, monkeypatch, tmp_path):
    fake_brain, _events = runtime
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "qwen3-vl-unpriced-r2")
    monkeypatch.delenv(pricing.brain_price_env(get_settings().vision_model), raising=False)
    monkeypatch.setattr(fake_brain, "QwenProvider", lambda **kwargs: pytest.fail("unpriced model must not construct provider"))
    with pytest.raises(HTTPException) as caught:
        evaluation._provider(fake_brain, _args(tmp_path), "deepseek", "frame_qc")
    assert caught.value.status_code == 409


def test_configured_vision_quote_without_authorization_makes_zero_requests(runtime, monkeypatch, tmp_path):
    monkeypatch.delenv("FIONA_STUDIO_VISION_MODEL", raising=False)
    args = _args(tmp_path)
    monkeypatch.setattr(evaluation, "_provider", lambda *args: pytest.fail("quote must not construct provider"))
    assert evaluation.main(["--text", args.text, "--image", str(args.image), "--output-dir", str(args.output_dir)]) == 2
    assert not args.output_dir.exists()


def test_report_names_actual_vision_model_in_warning_and_attempt(runtime, monkeypatch, tmp_path):
    monkeypatch.delenv("FIONA_STUDIO_VISION_MODEL", raising=False)
    args = _args(tmp_path, "--providers", "deepseek")
    plan, totals, cap = evaluation.build_plan(args, args.text)
    actual = get_settings().vision_model + "-snapshot"

    class Provider:
        async def call(self, *args, **kwargs):
            return SimpleNamespace(text="valid", usage={"input_tokens": 100, "output_tokens": 50},
                model=actual, stop_reason="stop", latency_s=.2, warnings=[])

    monkeypatch.setattr(evaluation, "_provider", lambda *args: Provider())
    records = asyncio.run(evaluation.evaluate(args, args.text, plan[-1:]))
    warning = brain.VISION_WARNING.format(model=actual)
    assert warning == f"看图由千问视觉（{actual}）完成"
    assert warning in records[0]["warnings"]
    # Complete the text columns so the same report writer can render the group.
    for item in plan[:-1]:
        records.append({**item, "status": "succeeded", "repaired": False, "warnings": [], "attempts": [], "output": {}})
    report = evaluation.write_report(args, args.text, totals, cap, records).read_text()
    assert warning in report and actual in report
    assert "{model}" not in report


def test_eval_pins_quoted_vision_model_when_environment_changes(runtime, monkeypatch, tmp_path):
    _fake_brain, events = runtime
    quoted = "qwen3-vl-quoted-r2"
    changed = "qwen3-vl-changed-r2"
    for model in (quoted, changed):
        monkeypatch.setenv(pricing.brain_price_env(model), json.dumps({"input": 1, "output": 10}))
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", quoted)
    args = _args(tmp_path, "--providers", "deepseek")
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", changed)
    result = asyncio.run(evaluation.evaluate(args, args.text, plan[-1:]))[0]
    assert len(events) == 1 and events[0]["model"] == quoted
    assert result["attempts"][0]["model"] == quoted
    assert brain.VISION_WARNING.format(model=quoted) in result["warnings"]


def test_empty_vision_setting_uses_default_without_warning(runtime, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FIONA_STUDIO_VISION_MODEL", "")
    args = _args(tmp_path, "--providers", "deepseek")
    plan, _totals, _cap = evaluation.build_plan(args, args.text)
    assert plan[-1]["model"] == get_settings().vision_model == "qwen3-vl-plus"
    assert "FIONA_STUDIO_VISION_MODEL" not in capsys.readouterr().out
