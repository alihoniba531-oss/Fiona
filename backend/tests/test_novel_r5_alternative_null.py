"""Portable regressions for optional critique alternatives."""

from copy import deepcopy

import pytest

from novel.agent_pool import AGENTS
from novel.schemas import ValidationError, validate_critique_plan


def test_null_alternative_is_optional_except_for_twist_designer():
    source = {
        "objections": [{
            "severity": "minor",
            "target": "第二个节拍",
            "problem": "线索发现缺少触发动作",
            "suggestion": "让主角先检查门锁再发现划痕",
        }],
        "keep": "保留门外脚步声带来的时间压力",
        "alternative": None,
    }
    before = deepcopy(source)
    for role, card in AGENTS.items():
        if card["category"] != "deliberation" or role in {"editor", "twist_designer"}:
            continue
        result = validate_critique_plan(source, role)
        assert result == {**before, "alternative": ""}
        assert source == before

    for alternative in (None, ""):
        twist_source = {**source, "alternative": alternative}
        twist_before = deepcopy(twist_source)
        with pytest.raises(ValidationError, match="alternative"):
            validate_critique_plan(twist_source, "twist_designer")
        assert twist_source == twist_before
