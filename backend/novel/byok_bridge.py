"""Short-lived access to an enabled, supported user model configuration.

Provider requests are deliberately implemented only in ``llm_router``. This
bridge resolves credentials for that existing non-streaming provider seam.
"""

from __future__ import annotations

from byok import store as byok_store
from byok.errors import ByokUnavailableError, NeedsReentryError

from .llm_router import KNOWN_MODELS, PROVIDERS
from .run_store import ConfigurationError


SUPPORTED_PROVIDERS = frozenset({"anthropic", "dashscope", "deepseek"})


class ByokUnavailable(ConfigurationError):
    """A recoverable BYOK configuration problem with a fixed public message."""


def validate_config(config: dict | None) -> dict:
    """Validate public metadata without needing to decrypt a credential."""
    if not config or not config.get("enabled") or config.get("status", "ok") != "ok":
        raise ByokUnavailable("请先启用可用的自带模型")
    provider, model = config.get("provider"), config.get("model")
    if provider not in SUPPORTED_PROVIDERS:
        raise ByokUnavailable("小说工坊仅支持自带 Anthropic、千问或 DeepSeek")
    if model not in KNOWN_MODELS.get(provider, ()):
        raise ByokUnavailable("该模型暂不支持用于小说工坊")
    return {"provider": provider, "model": model, "model_spec": "byok:self"}


class ByokBridge:
    def __init__(self, username: str):
        self.username = username

    async def describe(self) -> dict:
        """Return public metadata, preserving the reason an unavailable model fails."""
        config = await byok_store.get_public_config(self.username)
        return validate_config(config)

    async def resolve(self) -> dict:
        """Read a key only for the duration of the caller's provider operation."""
        try:
            config = await byok_store.get_internal_config(self.username)
        except NeedsReentryError:
            raise ByokUnavailable("请重新填写自带模型 Key") from None
        except ByokUnavailableError:
            raise ByokUnavailable("服务器暂未开启自带模型，请稍后重试") from None
        try:
            public = validate_config(config)
            if not isinstance(config.get("api_key"), str) or not config["api_key"]:
                raise ByokUnavailable("请重新填写自带模型 Key")
            return {"provider": public["provider"], "model": public["model"],
                    "base_url": PROVIDERS[public["provider"]][0],
                    "api_key": config["api_key"]}
        finally:
            # Do not retain the complete store result on the bridge or router.
            config = None
