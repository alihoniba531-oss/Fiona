"""Default DeepSeek model and SDK request regressions, entirely offline."""

import asyncio
import json
import os
from pathlib import Path
import socket

import httpx
import openai
import pytest

from novel.llm_router import LLMRouter, MODEL_ALLOWLISTS, parse_model, validate_model_settings
from novel.run_store import RunStore


CONFIG_DIRECTORY = Path(__file__).resolve().parents[1] / "novel" / "pilot_configs"
FLASH = "deepseek:deepseek-flash"


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    # Replace the entire mapping instead of reading or copying host credentials.
    monkeypatch.setattr(os, "environ", {"DEEPSEEK_API_KEY": "offline-deepseek-placeholder"})

    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.mark.parametrize("experiment", ["A", "B", "C"])
def test_default_configs_use_deepseek_flash(experiment):
    raw = (CONFIG_DIRECTORY / f"exp{experiment}.json").read_text(encoding="utf-8")
    config = json.loads(raw)
    assert "deepseek-v4-pro" not in raw
    assert config["agents"]["writer"] == FLASH
    assert config["agents"]["character_advocate"] == FLASH


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro", "custom-deepseek-model"])
def test_deepseek_models_remain_selectable_without_allowlist(model):
    assert "deepseek" not in MODEL_ALLOWLISTS
    assert parse_model(f"deepseek:{model}") == ("deepseek", model)
    assert validate_model_settings([f"deepseek:{model}"], announce=False) is None


@pytest.mark.parametrize("output", ["json", "markdown"])
def test_deepseek_flash_sdk_disables_thinking_and_sets_json_format_only_for_json(
    tmp_path, monkeypatch, output,
):
    requests, clients, parameters = [], [], []
    text = '{"ok":true}' if output == "json" else "# 第1章\n纯离线正文。"

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "chatcmpl-deepseek-offline", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26,
                      "prompt_cache_hit_tokens": 4},
        })

    original = openai.AsyncOpenAI

    def factory(**kwargs):
        parameters.append(dict(kwargs))
        client = original(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    messages = [{"role": "system", "content": "只输出 JSON。" if output == "json" else "撰写正文。"},
                {"role": "user", "content": "离线测试"}]

    async def request_once():
        try:
            return await LLMRouter(RunStore(tmp_path, {}))._single_real_call({
                "model": FLASH, "messages": messages, "max_tokens": 256, "output": output,
            })
        finally:
            for client in clients:
                await client.close()

    raw, usage, finish = asyncio.run(request_once())
    assert parameters == [{
        "base_url": "https://api.deepseek.com", "api_key": "offline-deepseek-placeholder",
        "timeout": 300, "max_retries": 0,
    }]
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.deepseek.com/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer offline-deepseek-placeholder"
    body = json.loads(requests[0].content)
    assert body["model"] == "deepseek-flash"
    assert body["messages"] == messages
    assert body["max_tokens"] == 256
    assert body["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in body
    if output == "json":
        assert body["response_format"] == {"type": "json_object"}
    else:
        assert "response_format" not in body
    assert raw == text
    assert finish == "stop"
    assert usage == {"input_tokens": 17, "output_tokens": 9, "cached_tokens": 4}
