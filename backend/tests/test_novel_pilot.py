"""Integration tests exercise only local fake responses, including real-route stubs."""

import asyncio
import copy
import json
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.pilot import evidence_matches, insert_contradictions, main, run_experiment
from novel.report import generate_report, load_prices, read_usage


@pytest.fixture(autouse=True)
def forbid_network_and_clients(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("测试禁止网络与真实客户端构造")
    monkeypatch.setattr(openai, "AsyncOpenAI", blocked)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", blocked)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)
        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                blocked()
            return original(sock, address)
        monkeypatch.setattr(socket.socket, method, guarded)


def config(experiment="B", small=False):
    value = json.loads((Path(__file__).parents[1] / f"novel/pilot_configs/exp{experiment}.json").read_text())
    if small:
        value["target"] = {"min_chapters": 1, "max_chapters": 2, "chapter_words": 100}
        value["user_notes"] = {}
        if experiment == "A":
            value["chapters_per_arm"] = 2
    return value


def run(value, out, **kwargs):
    return asyncio.run(run_experiment(value, out, dry_run=kwargs.pop("dry_run", True), **kwargs))


def read(out, relative):
    return json.loads((out / relative).read_text())


def default(request):
    return FakeLLM().default_response(request)


def test_all_three_dry_runs_do_not_construct_sdk(tmp_path, monkeypatch):
    # Poisoned client constructors and ambient endpoints must not affect fake.
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://forbidden.invalid")
    a, b, c = [tmp_path / letter for letter in "ABC"]
    fake = FakeLLM()
    assert run(config("A"), a, fake=fake) == 0
    assert sum(call["task"] == "setup" for call in fake.calls) == 1
    for arm in ("solo", "panel"):
        assert len(list((a / f"arm-{arm}").glob("ch*/chapter.md"))) == 5
        assert read(a, f"arm-{arm}/ch001/bible_before.json") == read(a, "setup/bible_v1.json")
    for name in ("版本甲.md", "版本乙.md"):
        body = (a / "blind" / name).read_text()
        assert body.count("# 第") == 5
        assert "推演会" not in body
    assert set(read(a, "blind/key.json").values()) == {"solo", "panel"}
    assert run(config("B"), b) == 0
    completion = read(b, "manifest.json")["completion"]
    assert completion["chapter"] == 9 and completion["within_target"]
    assert completion["user_note_responses"][0]["chapter"] == 4
    assert "完结章号：9" in (b / "report.md").read_text()
    assert run(config("C"), c, source_run=a) == 0
    comparisons = read(c, "comparison.json")
    assert len(comparisons) == 2
    assert all(item["caught_count"] == 3 and item["false_positives"] == 0 for item in comparisons)
    assert len(read(c, "control/insertions.json")) == 3
    for out in (a, b, c):
        assert (out / "cost.md").is_file() and (out / "report.md").is_file()
        assert "1 字符 = 1 token" in (out / "estimate.md").read_text()


@pytest.mark.parametrize("repair", [True, False])
def test_early_end_retries_and_reports_exit_code(tmp_path, repair):
    attempts = 0
    def script(request, index):
        nonlocal attempts
        if request["task"] == "decision" and request["chapter"] == 5:
            attempts += 1
            value = default(request)
            if not repair or attempts == 1:
                value["ending_status"] = "end"
                value["beat_sheet"]["foreshadowing_resolve"] = ["F001"]
            return value
    fake = FakeLLM(script)
    assert run(config(), tmp_path, fake=fake) == (0 if repair else 4)
    assert attempts == 2
    assert read(tmp_path, "manifest.json")["status"] == ("completed" if repair else "decision_invalid")
    if not repair:
        assert (tmp_path / "arm-panel/ch004/chapter.md").exists()
        assert not (tmp_path / "arm-panel/ch005/chapter.md").exists()


@pytest.mark.parametrize("repair", [True, False])
def test_final_mode_enforces_end_and_allows_one_correction(tmp_path, repair):
    def script(request, index):
        if request["task"] != "decision":
            return
        value = default(request)
        correction = sum(message["role"] == "user" for message in request["messages"]) > 1
        if repair and request["chapter"] == 12 and correction:
            return value
        value["ending_status"] = "continue"
        value["beat_sheet"]["foreshadowing_resolve"] = []
        return value
    assert run(config(), tmp_path, fake=FakeLLM(script)) == (0 if repair else 4)
    if repair:
        assert read(tmp_path, "manifest.json")["completion"]["chapter"] == 12
    else:
        assert read(tmp_path, "manifest.json")["status"] == "decision_invalid"


@pytest.mark.parametrize("reason", ["", "有意保留证人身份供读者回想。"])
def test_major_foreshadowing_requires_resolution_or_explicit_reason(tmp_path, reason):
    def script(request, index):
        if request["task"] == "decision" and request["chapter"] == 9:
            value = default(request)
            value["beat_sheet"]["foreshadowing_resolve"] = []
            value["unresolved_major_handling"] = [{"id": "F001", "decision": "leave_open", "reason": reason}] if reason else []
            return value
    assert run(config(), tmp_path, fake=FakeLLM(script)) == (0 if reason else 4)
    if reason:
        assert read(tmp_path, "manifest.json")["completion"]["open_major_foreshadowing"][0]["id"] == "F001"


@pytest.mark.parametrize("budget", [0, 1])
def test_budget_stops_before_call_then_relaxes_without_config_change(tmp_path, budget):
    value = config(small=True)
    fake = FakeLLM()
    assert run(value, tmp_path, fake=fake, max_total_tokens=budget) == 3
    assert fake.call_count == 0
    assert read(tmp_path, "manifest.json")["status"] == "budget_exhausted"
    assert run(value, tmp_path, fake=fake, max_total_tokens=3_000_000) == 0
    count, usage = fake.call_count, read_usage(tmp_path)
    assert run(value, tmp_path, fake=fake, max_total_tokens=4_000_000) == 0
    assert fake.call_count == count and read_usage(tmp_path) == usage


def test_config_hash_refuses_changed_story(tmp_path, capsys):
    value = config(small=True)
    assert run(value, tmp_path) == 0
    value["seed_idea"] += "另一种结局。"
    assert run(value, tmp_path) == 2
    assert "配置已变化，请换一个 --out" in capsys.readouterr().out


def test_interrupted_resume_preserves_completed_calls_and_final_artifacts(tmp_path, monkeypatch):
    # Freeze only the blind assignment; generation itself remains deterministic.
    monkeypatch.setattr("novel.report.random.SystemRandom", lambda: type("R", (), {"shuffle": lambda self, arms: None})())
    baseline, resumed = tmp_path / "baseline", tmp_path / "resumed"
    value = config("A", small=True)
    assert run(value, baseline) == 0
    fake = FakeLLM(lambda request, index: RuntimeError("模拟中断") if index == 17 else None)
    assert run(value, resumed, fake=fake) == 4
    completed = {read(resumed, str(path.relative_to(resumed)))["step_key"] for path in resumed.rglob("*.json") if "/ch" in str(path) and "status" in json.loads(path.read_text()) and json.loads(path.read_text())["status"] == "ok"}
    recovery = FakeLLM()
    assert run(value, resumed, fake=recovery) == 0
    assert not completed.intersection(call["step_key"] for call in recovery.calls)
    for path in baseline.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(baseline)
        if path.name in ("chapter.md", "chapter_record.json", "flags.json", "bible_before.json", "compass.json", "report.md", "版本甲.md", "版本乙.md", "key.json", "阅读说明.md") or path.name.startswith("bible_v"):
            assert path.read_bytes() == (resumed / relative).read_bytes(), str(relative)


def test_real_routes_only_local_stub_and_no_key_leaks(tmp_path, monkeypatch, capsys):
    sentinels = ["novel-sentinel-dashscope-ABC", "novel-sentinel-deepseek-DEF", "novel-sentinel-anthropic-GHI"]
    for name, sentinel in zip(("DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"), sentinels):
        monkeypatch.setenv(name, sentinel)
    for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    stub = FakeLLM()
    async def local(self, request):
        return await stub(request)
    monkeypatch.setattr(LLMRouter, "_single_real_call", local)
    assert run(config(small=True), tmp_path, dry_run=False) == 0
    assert {call["model"].split(":")[0] for call in stub.calls} == {"anthropic", "dashscope", "deepseek"}
    output = capsys.readouterr().out
    for sentinel in sentinels:
        assert sentinel not in output
        assert all(sentinel.encode() not in path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())


def test_environment_guard_cli_runs_before_clients(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://x")
    assert main(["run", "--config", "novel/pilot_configs/expA.json", "--out", str(tmp_path / "guard")]) == 2
    output = capsys.readouterr().out
    assert "unset" in output and "ANTHROPIC_BASE_URL" in output
    assert "http://x" not in output


@pytest.mark.parametrize("role", ["editor", "writer", "archivist"])
def test_required_agent_missing_exits_two(tmp_path, role):
    value = config(small=True)
    del value["agents"][role]
    assert run(value, tmp_path) == 2


@pytest.mark.parametrize("evidence,sentence,expected", [
    ("她此刻远在北方雪山医院", "插入：她此刻远在北方雪山医院，右手骨折。", True),
    ("林澈保存了新的录像证据", "她站在一座陌生的车站。", False),
    ("一二三四五六七甲", "一二三四五六七乙", False),
    ("一 二\n三四五六七八", "甲一二三四五六七八乙", True),
])
def test_c_evidence_contiguous_overlap(evidence, sentence, expected):
    assert evidence_matches(evidence, sentence) is expected


def test_insertions_use_original_offsets():
    text = "甲句。乙句。丙句。"
    items = [{"after_anchor": "甲句。", "new_sentence": "新句含乙句。"}, {"after_anchor": "乙句。", "new_sentence": "插入二。"}]
    assert insert_contradictions(text, items) == "甲句。\n新句含乙句。乙句。\n插入二。丙句。"


@pytest.mark.parametrize("bad_price", [True, -1, float("inf"), "1"])
def test_invalid_prices_rejected(bad_price):
    with pytest.raises(ValueError):
        load_prices({"fake:test": {"input_per_mtok": bad_price, "output_per_mtok": 1, "currency": "USD"}})


def test_report_regeneration_with_external_prices(tmp_path):
    assert run(config(small=True), tmp_path) == 0
    tokens_only = (tmp_path / "cost.md").read_text()
    assert "金额" not in tokens_only
    prices = {row["model"]: {"input_per_mtok": 2, "output_per_mtok": 3, "currency": "USD"} for row in read_usage(tmp_path)}
    generate_report(tmp_path, prices)
    assert "金额" in (tmp_path / "cost.md").read_text() and "USD" in (tmp_path / "cost.md").read_text()
    assert main(["report", "--out", str(tmp_path)]) == 0


def test_c_requires_valid_a_source(tmp_path):
    assert run(config("C"), tmp_path / "no-source") == 2
    assert run(config("C"), tmp_path / "missing", source_run=tmp_path / "missing-source") == 2
