"""导演任务定义；硬约束用于本地校验，创作偏好只产生警告。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def _string(*, empty: bool = False) -> dict:
    return {"type": "string", **({} if empty else {"minLength": 1})}


def _array(items: dict, **constraints) -> dict:
    return {"type": "array", "items": items, **constraints}


def _no_warnings(output: dict, inputs: dict) -> list[str]:
    return []


def _style_warnings(output: dict, inputs: dict) -> list[str]:
    return [] if 2 <= len(output["proposals"]) <= 3 else ["风格提案建议为 2–3 个，当前结果已原样保留。"]


@dataclass(frozen=True)
class BrainTask:
    name: str
    prompt_template: str
    schema: dict
    soft_checks: Callable[[dict, dict], list[str]]
    max_tokens: int
    effort: str = "low"


READ_THROUGH_SCHEMA = _object({
    **{name: _string() for name in ("logline", "synopsis", "genre", "tone", "theme", "pacing")},
    "adaptation_risks": _array(_string()),
})
STYLE_PROPOSALS_SCHEMA = _object({
    "proposals": _array(_object({name: _string() for name in (
        "name", "visual_style", "palette", "camera", "lighting", "rationale",
    )}), minItems=1, maxItems=5),
})
BIBLE_EXTRACT_SCHEMA = _object({
    "characters": _array(_object({
        "name": _string(), "role": _string(), "description": _string(),
        "appearance_status": {"type": "string", "enum": ["from_text", "needs_author"]},
        "appearance_excerpt": _string(empty=True),
    })),
    "locations": _array(_object({"name": _string(), "description": _string()})),
    "props": _array(_object({"name": _string(), "description": _string()})),
})
FRAME_QC_SCHEMA = _object({name: _object({"passed": {"type": "boolean"}, "notes": _string()})
                           for name in ("structure", "materials", "physics", "realistic_frontal_face")})

TASKS = {
    "read_through": BrainTask("通读结论", "read_through.md", READ_THROUGH_SCHEMA, _no_warnings, 4096),
    "style_proposals": BrainTask("风格提案", "style_proposals.md", STYLE_PROPOSALS_SCHEMA, _style_warnings, 6144),
    "bible_extract": BrainTask("人物、场景、道具表", "bible_extract.md", BIBLE_EXTRACT_SCHEMA, _no_warnings, 12000),
    "frame_qc": BrainTask("看图质检", "frame_qc.md", FRAME_QC_SCHEMA, _no_warnings, 4096),
}
TEXT_TASKS = ("read_through", "style_proposals", "bible_extract")


def get_task(task: str) -> BrainTask:
    try:
        return TASKS[task]
    except (KeyError, TypeError):
        raise ValueError("不支持的导演任务") from None


def task_prompt(task: str) -> str:
    return (Path(__file__).with_name("prompts") / get_task(task).prompt_template).read_text(encoding="utf-8")


def task_hard_errors(task: str, output: dict, inputs: dict) -> list[str]:
    """依赖原文的约束不能只靠 JSON Schema 表达。"""
    errors = []
    if task == "bible_extract":
        source = inputs.get("text", "")
        for index, character in enumerate(output["characters"]):
            excerpt = character["appearance_excerpt"]
            path = f"$.characters[{index}].appearance_excerpt"
            if character["appearance_status"] == "needs_author" and excerpt:
                errors.append(path + " 原文未写外形时必须留空，不得编造")
            elif character["appearance_status"] == "from_text" and (not excerpt.strip() or excerpt not in source):
                errors.append(path + " 必须是原文中非空的逐字外形摘录")
    return errors
