"""Server-only model selection for official partners; personal chat keeps its own routing."""
import os
from dataclasses import dataclass
from functools import lru_cache

from openai import AsyncOpenAI

from llm import MAIN_EXTRA_BODY, MAIN_MODEL, _float_env


@dataclass(frozen=True)
class ExchangeModel:
    provider: str
    model: str
    model_label: str
    extra_body: dict

    def public_metadata(self) -> dict:
        return {"provider": self.provider, "model": self.model, "model_label": self.model_label}


def get_exchange_model(slot: str = "main") -> ExchangeModel:
    if slot not in ("main", "official"):
        raise ValueError("Unknown exchange model slot")
    provider = os.getenv("OFFICIAL_EXCHANGE_PROVIDER", "dashscope").strip().lower() if slot == "official" else "dashscope"
    if provider not in ("dashscope", "deepseek"):
        raise ValueError("Unsupported official exchange provider")
    default = "deepseek-v4-pro" if provider == "deepseek" else MAIN_MODEL
    model = (os.getenv("OFFICIAL_EXCHANGE_MODEL", "").strip() or default) if slot == "official" else MAIN_MODEL
    label = {"deepseek-v4-pro": "DeepSeek V4 Pro", "qwen3.8-max": "Qwen3.8 Max", "qwen3.8-omni-flash": "Qwen3.8 Omni Flash"}.get(model, model)
    extra_body = {"thinking": {"type": "disabled"}} if provider == "deepseek" else dict(MAIN_EXTRA_BODY)
    return ExchangeModel(provider, model, label, extra_body)


@lru_cache(maxsize=1)
def get_async_main_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=_float_env("DASHSCOPE_TIMEOUT_SECONDS", 60.0, minimum=5.0, maximum=300.0),
        max_retries=0,
    )


@lru_cache(maxsize=1)
def get_async_deepseek_client() -> AsyncOpenAI:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise ValueError("DeepSeek API key is not configured")
    # Credentials go only to the official DeepSeek endpoint, never to a caller URL.
    return AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=45.0, max_retries=0)


def select_exchange_slot(context: dict, *, summary: bool = False) -> str:
    if context.get("kind", "peer") == "official" and (summary or context["turn_count"] % 2 == 1):
        return "official"
    return "main"
