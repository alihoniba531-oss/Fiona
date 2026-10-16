"""Task-specific editor token limits must not alter the shared role registry."""

from copy import deepcopy

from novel.agent_pool import AGENTS, get_agent


def test_only_finalize_uses_8000_tokens_without_mutating_registry():
    registry_before = deepcopy(AGENTS)

    finalize = get_agent("editor", task="finalize")
    assert finalize["max_tokens"] == 8000
    assert get_agent("editor", task="plan")["max_tokens"] == 6000
    assert get_agent("editor", task="decision")["max_tokens"] == 6000
    assert get_agent("editor")["max_tokens"] == 6000

    finalize["max_tokens"] = 1
    assert get_agent("editor", task="finalize")["max_tokens"] == 8000
    assert AGENTS == registry_before
