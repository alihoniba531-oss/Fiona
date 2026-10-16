"""Ark integration stays offline and never consults the process's real keys."""

import asyncio
import json
import os
from pathlib import Path
import socket

import anthropic
import openai
import pytest

from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.pilot import run_experiment
from novel.report import cost_report, load_prices, read_usage


ARK_MODEL = "ark:doubao-seed-2-1-pro-260915"


class UnreadableEnvironment(dict):
    """Fail provider reads; asyncio may inspect its own synthetic debug flag."""

    def _forbidden(self, *args, **kwargs):
        raise AssertionError("离线运行不得读取环境变量")

    def get(self, key, default=None):
        if key == "PYTHONASYNCIODEBUG":
            return default
        return self._forbidden()

    __getitem__ = __contains__ = __iter__ = _forbidden
    items = keys = values = _forbidden


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    # Replacing the whole mapping avoids reading or preserving ambient secrets.
    monkeypatch.setattr(os, "environ", {})
    client_constructions = []

    def blocked_client(*args, **kwargs):
        client_constructions.append(True)
        raise AssertionError("Ark 集成测试禁止真实 SDK 客户端构造")

    monkeypatch.setattr(openai, "AsyncOpenAI", blocked_client)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", blocked_client)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)

        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise AssertionError("Ark 集成测试禁止网络")
            return original(sock, address)

        monkeypatch.setattr(socket.socket, method, guarded)
    return client_constructions


def _default_config(experiment):
    path = Path(__file__).parents[1] / "novel" / "pilot_configs" / f"exp{experiment}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _small_ark_config(role="plot_architect"):
    config = _default_config("B")
    config["target"] = {"min_chapters": 1, "max_chapters": 1, "chapter_words": 200}
    config["user_notes"] = {}
    config["agents"] = {name: f"fake:{name}" for name in config["agents"]}
    config["agents"][role] = ARK_MODEL
    return config


def _run(config, out, **kwargs):
    return asyncio.run(run_experiment(config, out, **kwargs))


def _table_cells(text):
    return [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.startswith("|")]


def test_ark_internal_config_full_a_dry_run_and_accounting(tmp_path, monkeypatch, offline_only):
    # This test-only variant lives in memory; all three default files stay intact.
    config = _default_config("A")
    config["agents"]["plot_architect"] = ARK_MODEL
    monkeypatch.setattr(os, "environ", UnreadableEnvironment())

    async def forbidden_real_call(self, request):
        raise AssertionError("dry-run 不得进入真实调用分支")

    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden_real_call)
    fake = FakeLLM()
    assert _run(config, tmp_path, dry_run=True, fake=fake) == 0
    assert offline_only == []
    assert json.loads((tmp_path / "manifest.json").read_text())["status"] == "completed"
    for arm in ("solo", "panel"):
        assert len(list((tmp_path / f"arm-{arm}").glob("ch*/chapter.md"))) == 5
    usage = read_usage(tmp_path)
    ark_usage = [row for row in usage if row["model"] == ARK_MODEL]
    assert ark_usage
    assert {row["role"] for row in ark_usage} == {"plot_architect"}
    assert {row["provider"] for row in usage} == {"fake"}
    assert len(ark_usage) == sum(call["model"] == ARK_MODEL for call in fake.calls)
    assert sum(row["input_tokens"] + row["output_tokens"] for row in ark_usage) > 0

    estimate = (tmp_path / "estimate.md").read_text(encoding="utf-8")
    estimate_row = next(row for row in _table_cells(estimate) if row[:2] == ["A", "plot_architect"])
    assert estimate_row[2:] == [
        str(sum(row["attempts"] for row in ark_usage)),
        str(sum(row["input_chars"] for row in ark_usage)),
        str(sum(row["max_tokens"] * row["attempts"] for row in ark_usage)),
    ]
    cost = (tmp_path / "cost.md").read_text(encoding="utf-8")
    cost_row = next(row for row in _table_cells(cost) if row[:3] == ["A", "plot_architect", ARK_MODEL])
    assert cost_row[3:6] == [
        str(sum(row["attempts"] for row in ark_usage)),
        str(sum(row["input_tokens"] for row in ark_usage)),
        str(sum(row["output_tokens"] for row in ark_usage)),
    ]
    assert load_prices(None) == {}
    assert "金额" not in cost and "CNY" not in cost
    # A supplied price is honored; there is no implicit Ark price.
    supplied_prices = {ARK_MODEL: {"input_per_mtok": 17, "output_per_mtok": 29, "currency": "CNY"}}
    priced = cost_report(tmp_path, supplied_prices)
    expected_amount = sum(row["input_tokens"] * 17 + row["output_tokens"] * 29 for row in ark_usage) / 1_000_000
    priced_row = next(row for row in _table_cells(priced) if row[:3] == ["A", "plot_architect", ARK_MODEL])
    assert priced_row[-1] == f"CNY {expected_amount:.6f}"


def test_ark_key_sentinel_never_reaches_stdout_or_output_tree(tmp_path, monkeypatch, capsys, offline_only):
    sentinel = "novel-ark-only-local-test-secret-5297"
    monkeypatch.setattr(os, "environ", {"ARK_API_KEY": sentinel})
    local_fake = FakeLLM()

    async def local_real_call(self, request):
        assert request["model"] == ARK_MODEL
        raw, usage = await local_fake(request)
        return raw, {**usage, "cached_tokens": 7}, "stop"

    monkeypatch.setattr(LLMRouter, "_single_real_call", local_real_call)
    assert _run(_small_ark_config(), tmp_path, dry_run=False) == 0
    assert offline_only == []
    assert local_fake.call_count > 0
    assert {call["model"] for call in local_fake.calls} == {ARK_MODEL}
    assert (tmp_path / "arm-panel/ch001/chapter.md").is_file()
    usage = read_usage(tmp_path)
    ark_usage = [row for row in usage if row["model"] == ARK_MODEL]
    assert len(ark_usage) == local_fake.call_count
    assert all(row["provider"] == "ark" and row["cached_tokens"] == 7 for row in ark_usage)
    assert {row["provider"] for row in usage} == {"ark", "fake"}
    captured = capsys.readouterr()
    assert sentinel not in captured.out and sentinel not in captured.err
    for path in tmp_path.rglob("*"):
        assert sentinel not in str(path)
        if path.is_file():
            assert sentinel.encode() not in path.read_bytes()


@pytest.mark.parametrize("budget", [0, 1])
@pytest.mark.parametrize("dry_run", [True, False])
def test_ark_budget_blocks_all_calls_before_generation(tmp_path, monkeypatch, offline_only, budget, dry_run):
    monkeypatch.setattr(os, "environ", UnreadableEnvironment() if dry_run else {"ARK_API_KEY": "local-budget-key"})

    async def forbidden_real_call(self, request):
        raise AssertionError("预算耗尽不得执行调用")

    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden_real_call)
    fake = FakeLLM()
    assert _run(_small_ark_config("editor"), tmp_path, dry_run=dry_run,
                fake=fake, max_total_tokens=budget) == 3
    assert fake.call_count == 0
    assert offline_only == []
    assert read_usage(tmp_path) == []
    assert json.loads((tmp_path / "manifest.json").read_text())["status"] == "budget_exhausted"


def test_missing_ark_key_reports_only_variable_name_before_creating_run(tmp_path, capsys, offline_only):
    out = tmp_path / "missing"
    assert _run(_small_ark_config(), out, dry_run=False) == 2
    captured = capsys.readouterr()
    assert captured.out == "配置或环境错误：缺少环境变量：ARK_API_KEY\n"
    assert captured.err == ""
    assert not out.exists()
    assert offline_only == []


def test_ark_environment_pollution_rejected_without_values(tmp_path, monkeypatch, capsys, offline_only):
    sentinel = "novel-ark-pollution-secret-5297"
    endpoint = "https://offline-forbidden.invalid/private-sentinel"
    monkeypatch.setattr(os, "environ", {"ARK_API_KEY": sentinel, "OPENAI_BASE_URL": endpoint})
    out = tmp_path / "polluted"
    assert _run(_small_ark_config(), out, dry_run=False) == 2
    captured = capsys.readouterr()
    assert "OPENAI_BASE_URL" in captured.out and "unset" in captured.out
    assert sentinel not in captured.out and endpoint not in captured.out
    assert captured.err == ""
    assert not out.exists()
    assert offline_only == []
