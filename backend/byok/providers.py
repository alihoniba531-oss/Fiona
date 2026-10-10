"""Provider metadata and validation, shared by settings and reply adapters."""
from __future__ import annotations

from copy import deepcopy
import re

from .errors import ConfigurationError

CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
CLAUDE_EFFORTS = ("low", "medium", "high")
DEFAULT_EFFORT = "low"
PROVIDERS = {
    "dashscope": {"name": "通义千问（阿里云百炼）", "kind": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "extra_body": {"enable_thinking": False}, "recommended_models": ["qwen3.8-omni-flash", "qwen3.8-max", "qwen3.8-flash"]},
    "deepseek": {"name": "DeepSeek", "kind": "openai", "base_url": "https://api.deepseek.com", "extra_body": {"thinking": {"type": "disabled"}}, "recommended_models": ["deepseek-v4-pro"]},
    "moonshot": {"name": "Kimi（月之暗面）", "kind": "openai", "base_url": "https://api.moonshot.cn/v1", "recommended_models": []},
    "zhipu": {"name": "智谱 GLM", "kind": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4", "recommended_models": []},
    "anthropic": {"name": "Claude（Anthropic）", "kind": "anthropic", "base_url": "https://api.anthropic.com", "recommended_models": list(CLAUDE_MODELS), "allowed_models": list(CLAUDE_MODELS), "default_model": CLAUDE_MODELS[0]},
    "custom": {"name": "自定义 OpenAI 兼容地址", "kind": "openai", "base_url": None, "recommended_models": []},
}


def validate_provider(provider: object) -> str:
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ConfigurationError("请选择有效的厂商")
    return provider


def validate_model(provider: str, model: object) -> str:
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/@-]{1,100}", model):
        raise ConfigurationError("模型名格式不正确")
    if provider == "anthropic" and model not in CLAUDE_MODELS:
        raise ConfigurationError("请选择支持的 Claude 型号")
    return model


def validate_effort(value: object) -> str:
    if not isinstance(value, str) or value not in CLAUDE_EFFORTS:
        raise ConfigurationError("思考强度只能是低、中、高")
    return value


def public_provider_metadata() -> list[dict]:
    return [{"id": provider, "name": data["name"], "kind": data["kind"], "base_url": data["base_url"],
             "recommended_models": list(data["recommended_models"]), "allowed_models": deepcopy(data.get("allowed_models")),
             "default_model": data.get("default_model"),
             "efforts": list(CLAUDE_EFFORTS) if provider == "anthropic" else None,
             "default_effort": DEFAULT_EFFORT if provider == "anthropic" else None}
            for provider, data in PROVIDERS.items()]


def provider_label(provider: str, model: str) -> str:
    name = "Claude" if provider == "anthropic" else PROVIDERS[provider]["name"]
    return f"{name} · {model}"
