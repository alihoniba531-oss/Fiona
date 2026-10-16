"""Ark configuration validation stays local and runs before key/client access."""

from copy import deepcopy
import json
import socket
from types import SimpleNamespace

import anthropic
import openai
import pytest

from novel import llm_router, pilot
from novel.agent_pool import AGENTS, _validate_model, validate_agents
from novel.llm_router import ConfigurationError


ARK_MODELS = (
    "ark:doubao-seed-2-1-pro-260915",
    "ark:doubao-seed-2-1-pro-260628",
)


def _blocked(*args, **kwargs):
    raise AssertionError("Ark 配置校验测试禁止读取环境、联网或创建真实客户端")


class _UnreadableEnvironment(dict):
    get = __getitem__ = _blocked


@pytest.fixture(autouse=True)
def forbid_credentials_and_clients(monkeypatch):
    monkeypatch.setattr(llm_router, "os", SimpleNamespace(environ=_UnreadableEnvironment()))
    monkeypatch.setattr(openai, "AsyncOpenAI", _blocked)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _blocked)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)

        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                _blocked()
            return original(sock, address)

        monkeypatch.setattr(socket.socket, method, guarded)


def _config(experiment="B"):
    value = {
        "experiment": experiment,
        "seed_idea": "一名修复师在旧钟里发现明天才会留下的字条。",
        "target": {"min_chapters": 1, "max_chapters": 2, "chapter_words": 100},
        "adaptation": {"max_main_characters": 3, "max_scenes_per_chapter": 2},
        "critique_rounds": 1,
        "agents": {role: f"fake:{role}" for role in AGENTS},
        "user_notes": {},
    }
    if experiment == "C":
        value["reviewers_to_compare"] = ["fake:reviewer"]
    return value


@pytest.mark.parametrize("model", ARK_MODELS)
@pytest.mark.parametrize("role", list(AGENTS))
def test_each_agent_can_select_either_ark_model(role, model):
    config = _config()
    config["agents"][role] = model
    validate_agents(config)
    pilot.validate_config(config)


@pytest.mark.parametrize("model", ARK_MODELS)
def test_reviewers_to_compare_accepts_either_ark_model(model):
    config = _config("C")
    config["reviewers_to_compare"] = [model]
    validate_agents(config)
    pilot._model_spec(model)
    pilot.validate_config(config)


@pytest.mark.parametrize("validator", [_validate_model, pilot._model_spec])
def test_both_configuration_validators_reuse_ark_whitelist(validator):
    with pytest.raises(ConfigurationError, match="^火山方舟型号未在白名单内$"):
        validator("ark:unknown-model")


@pytest.mark.parametrize("validator", [_validate_model, pilot._model_spec])
@pytest.mark.parametrize("model", ["volc:xxx", "ark:", "ark:model extra", "ark:model:extra"])
def test_strict_model_syntax_reports_ark_as_an_allowed_provider(validator, model):
    with pytest.raises(ValueError, match="提供方只能为 .*ark"):
        validator(model)


@pytest.mark.parametrize("validator", [_validate_model, pilot._model_spec])
@pytest.mark.parametrize("provider", ["dashscope", "deepseek", "anthropic", "fake"])
def test_other_providers_do_not_gain_model_whitelists(validator, provider):
    validator(f"{provider}:arbitrary-unlisted-model")


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("slot", ["agent", "reviewers_to_compare"])
@pytest.mark.parametrize("model, message", [
    ("ark:unknown-model", "火山方舟型号未在白名单内"),
    ("volc:xxx", "提供方只能为 dashscope、deepseek、anthropic、ark、fake"),
])
def test_invalid_provider_or_ark_model_cli_exits_two_before_environment(
    tmp_path, monkeypatch, capsys, dry_run, slot, model, message
):
    config = _config("C" if slot == "reviewers_to_compare" else "B")
    if slot == "agent":
        config["agents"]["editor"] = model
    else:
        config[slot] = [model]
    original = deepcopy(config)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "output"
    monkeypatch.setattr(pilot, "validate_environment", _blocked)
    monkeypatch.setattr(pilot, "validate_model_settings", _blocked)
    args = ["run", "--config", str(path), "--out", str(out)]
    if dry_run:
        args.append("--dry-run")
    assert pilot.main(args) == 2
    assert message in capsys.readouterr().out
    assert not out.exists()
    assert config == original
