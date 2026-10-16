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
    elif task == 'novel_complete':
        expected = [item['chapter'] for item in inputs.get('chapters', [])]
        actual = [item['chapter'] for item in output['chapters']]
        if sorted(expected) != sorted(actual):
            errors.append('$.chapters 必须逐一包含全部输入章号，不得重复或越界')
    elif task == 'episode_plan':
        units = {item['seq'] for item in inputs.get('units', [])}
        previous = 0
        for index, episode in enumerate(output['episodes']):
            first, last = episode['unit_from'], episode['unit_to']
            if (first > last or first <= previous or not units or first < min(units) or last > max(units)
                    or sum(first <= seq <= last for seq in units) != last - first + 1):
                errors.append(f'$.episodes[{index}] 范围必须有序、非空、互不重叠且位于本段内')
            previous = last
    return errors

# WO3c: the four tasks share scene units; timing is a computed soft constraint.
_SCENE = _object({
    'location': _string(empty=True), 'summary': _string(),
    'characters': _array(_string()), 'est_seconds': {'type': 'integer', 'minimum': 1},
    'change': _string(empty=True), 'start_anchor': {'type': 'string', 'minLength': 8, 'maxLength': 30},
})
_ENTITY = _object({'name': _string(), 'description': _string(empty=True),
                   'first_chapter': {'type': 'integer', 'minimum': 1}, 'excerpt': _string(empty=True)})
NOVEL_COMPLETE_SCHEMA = _object({
    'chapters': _array(_object({'chapter': {'type': 'integer', 'minimum': 1},
                               'scenes': _array(_SCENE, minItems=1)}), minItems=1),
    'locations': _array(_ENTITY), 'props': _array(_ENTITY),
    'appearance_fills': _array(_object({'character': _string(), 'excerpt': _string()})),
    'new_characters': _array(_object({'name': _string(), 'role': _string(empty=True),
                                     'first_chapter': {'type': 'integer', 'minimum': 1},
                                     'excerpt': _string(empty=True)})),
})
TEXT_MAP_SCHEMA = _object({
    'summary': _string(), 'scenes': _array(_SCENE, minItems=1),
    'characters': _array(_object({'name': _string(), 'aliases': _array(_string()),
                                'role': _string(empty=True), 'excerpt': _string(empty=True)})),
    'locations': _array(_ENTITY), 'props': _array(_ENTITY),
})
SYNOPSIS_SCHEMA = _object({**{key: _string() for key in ('logline', 'synopsis', 'genre', 'tone')},
                           'themes': _array(_string())})
EPISODE_PLAN_SCHEMA = _object({'episodes': _array(_object({
    'unit_from': {'type': 'integer', 'minimum': 1}, 'unit_to': {'type': 'integer', 'minimum': 1},
    'title': _string(), 'change': _string(empty=True), 'hook': _string(empty=True),
}), minItems=1)})


def _episode_warnings(output, inputs):
    units = {item['seq']: item for item in inputs.get('units', [])}
    covered, warnings = set(), []
    for index, episode in enumerate(output['episodes'], 1):
        seqs = {seq for seq in units if episode['unit_from'] <= seq <= episode['unit_to']}
        covered.update(seqs)
        seconds = sum(units[seq].get('est_seconds') or 0 for seq in seqs if seq in units)
        if seconds < inputs.get('target_min', 180) * .85 or seconds > inputs.get('target_max', 240) * 1.15:
            warnings.append(f'第 {index} 集预估时长超出目标区间 ±15%。')
    if set(units) - covered:
        warnings.append('本段有未纳入分集的单元。')
    return warnings


TASKS.update({
    'novel_complete': BrainTask('小说补全', 'novel_complete.md', NOVEL_COMPLETE_SCHEMA, _no_warnings, 8192),
    'text_map': BrainTask('逐块通读', 'text_map.md', TEXT_MAP_SCHEMA, _no_warnings, 4096),
    'synopsis': BrainTask('故事梗概', 'synopsis.md', SYNOPSIS_SCHEMA, _no_warnings, 2048),
    'episode_plan': BrainTask('分集方案', 'episode_plan.md', EPISODE_PLAN_SCHEMA, _episode_warnings, 4096),
})
BREAKDOWN_TASKS = ('novel_complete', 'text_map', 'synopsis', 'episode_plan')
