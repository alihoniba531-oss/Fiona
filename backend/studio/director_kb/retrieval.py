"""按场景标签从本地知识库取材料，并拼成受字数预算约束的注入文本（WO3e §5）。

结果必须确定：同样的输入与同样的库内容永远得到逐字相同的输出。
``select_materials`` 是同步函数，``owner`` 不为空时用只读 sqlite3 连接查案例库，
因此可以在异步路由里直接调用，不需要也不能调用 ``asyncio.run``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict

from fastapi import HTTPException

from . import loader, schema


class SceneTags(TypedDict):
    scene_type: str
    position: Literal["opening", "body", "ending"]
    pace: Literal["fast", "mid", "slow"]
    emotion: str
    cast_count: int
    realism: Literal["photoreal", "anime", "3d"]
    setting: Literal["interior", "exterior", "mixed"]
    sensitive: list[str]


_POSITION_CARDS = {"opening": "scene-opening-hook", "ending": "scene-cliffhanger"}
_MAX_GRAMMAR = 5
_MAX_NEGATIVES = 3
_MAX_EXEMPLARS = 3


def _tag_value(tags: Mapping, key: str, default):
    value = tags.get(key, default)
    return default if value is None else value


def _validated_tags(tags) -> dict:
    if not isinstance(tags, Mapping):
        raise HTTPException(422, "场景标签必须是对象")
    scene_type = tags.get("scene_type")
    if not isinstance(scene_type, str):
        raise HTTPException(422, "scene_type 必须是文字")
    if scene_type in schema.POSITION_SCENE_TYPES:
        raise HTTPException(422, f"{scene_type} 是位置卡类型，scene_type 必须传内容卡类型")
    if scene_type not in schema.CONTENT_SCENE_TYPES:
        raise HTTPException(422, "scene_type 不在知识库内容卡清单内")
    position = _tag_value(tags, "position", "body")
    if not isinstance(position, str) or position not in schema.SCENE_POSITIONS:
        raise HTTPException(422, "position 只能是 opening / body / ending")
    pace = _tag_value(tags, "pace", "mid")
    if not isinstance(pace, str) or pace not in ("fast", "mid", "slow"):
        raise HTTPException(422, "pace 只能是 fast / mid / slow")
    realism = _tag_value(tags, "realism", "photoreal")
    if not isinstance(realism, str) or realism not in ("photoreal", "anime", "3d"):
        raise HTTPException(422, "realism 只能是 photoreal / anime / 3d")
    setting = _tag_value(tags, "setting", "interior")
    if not isinstance(setting, str) or setting not in ("interior", "exterior", "mixed"):
        raise HTTPException(422, "setting 只能是 interior / exterior / mixed")
    cast_count = _tag_value(tags, "cast_count", 2)
    if type(cast_count) is not int or not 1 <= cast_count <= 6:
        raise HTTPException(422, "cast_count 必须是 1–6 的整数")
    emotion = _tag_value(tags, "emotion", "")
    if not isinstance(emotion, str) or len(emotion) > 20:
        raise HTTPException(422, "emotion 必须是不超过 20 字的文字")
    sensitive = _tag_value(tags, "sensitive", [])
    if (not isinstance(sensitive, list)
            or any(not isinstance(item, str) or item not in schema.SENSITIVE_TAGS
                   for item in sensitive)):
        raise HTTPException(422, "sensitive 含有未知标记")
    return {
        "scene_type": scene_type,
        "position": position,
        "pace": pace,
        "emotion": emotion,
        "cast_count": cast_count,
        "realism": realism,
        "setting": setting,
        "sensitive": list(dict.fromkeys(sensitive)),
    }


def _normalize_tag(value: str) -> str:
    """卡片 tags 一律 kebab-case；输入侧的下划线在匹配前统一成连字符。"""
    return value.replace("_", "-")


def _tag_tokens(tags: Mapping) -> set[str]:
    tokens = {
        _normalize_tag(tags["scene_type"]), _normalize_tag(tags["position"]),
        _normalize_tag(tags["pace"]), _normalize_tag(tags["realism"]),
        _normalize_tag(tags["setting"]), str(tags["cast_count"]),
    }
    tokens.update(_normalize_tag(item) for item in tags["sensitive"])
    return tokens


def _pick_model(library: loader.CardLibrary, video_model: str, realism: str) -> dict | None:
    family = [card for card in library.of_type("model")
              if card["model"].startswith(f"{video_model}-")]
    exact = sorted((card for card in family if card["style"] == realism),
                   key=lambda card: card["id"])
    if exact:
        return exact[0]
    fallback = sorted((card for card in family if card["style"] == "any"),
                      key=lambda card: card["id"])
    return fallback[0] if fallback else None


def _model_applies(card: Mapping, video_model: str) -> bool:
    applies = card.get("applies_to") or {}
    models = applies.get("model")
    if not models:
        return True
    return any(value == video_model or value.startswith(f"{video_model}-")
               or f"-{video_model}-" in value or value.startswith(f"model-{video_model}-")
               for value in models)


def _negative_applies(card: Mapping, tags: Mapping, video_model: str) -> bool:
    applies = card.get("applies_to") or {}
    scene_types = applies.get("scene_type")
    if scene_types and tags["scene_type"] not in scene_types:
        return False
    return _model_applies(card, video_model)


def _select_grammar(library: loader.CardLibrary, template: Mapping, position: Mapping | None,
                    tags: Mapping) -> list[dict]:
    # §5（R1 澄清）：按 template → position → 标签命中的优先级依次去重，
    # 截取前 5 张，再按 id 排序输出；不能先全局排序再截断。
    ordered: list[str] = []
    for card in (template, position):
        if card is not None:
            ordered.extend(card.get("related_grammar", []))
    tokens = _tag_tokens(tags)
    for card in library.of_type("grammar"):
        if tokens.intersection(_normalize_tag(tag) for tag in card["tags"]):
            ordered.append(card["id"])
    unique = list(dict.fromkeys(ordered))
    selected = [library.cards[card_id] for card_id in unique
                if card_id in library.cards][:_MAX_GRAMMAR]
    return sorted(selected, key=lambda card: card["id"])


def _select_negatives(library: loader.CardLibrary, template: Mapping, position: Mapping | None,
                      tags: Mapping, video_model: str) -> list[dict]:
    ordered: list[str] = []
    for card in (template, position):
        if card is not None:
            ordered.extend(card.get("related_negative", []))
    # applies_to 明确命中的卡优先，没有 applies_to 的通用反例随后。
    for require_filter in (True, False):
        for card in library.of_type("negative"):
            has_filter = bool(card.get("applies_to"))
            if has_filter is not require_filter:
                continue
            if require_filter and not _negative_applies(card, tags, video_model):
                continue
            ordered.append(card["id"])
    seen: set[str] = set()
    selected = []
    for card_id in ordered:
        if card_id in seen or card_id not in library.cards:
            continue
        seen.add(card_id)
        selected.append(library.cards[card_id])
        if len(selected) == _MAX_NEGATIVES:
            break
    return selected


def _pace_text(pacing: Mapping) -> str:
    labels = (("fast", "快"), ("mid", "中"), ("slow", "慢"))
    parts = []
    for key, label in labels:
        tier = pacing[key]
        low, high = tier["shots_per_min"]
        seconds_low, seconds_high = tier["shot_seconds"]
        parts.append(f"{label} {low:g}–{high:g} 镜/分、每镜 {seconds_low:g}–{seconds_high:g} 秒")
    return "；".join(parts)


def _render_scene(card: Mapping) -> str:
    lines = [f"【{card['id']}】{card['title']}：{card['summary']}"]
    if "position" in card:
        lines.append(f"位置：{card['position']}")
    lines.append("节拍：" + "；".join(card["beats"]))
    lines.append("覆盖：" + "；".join(card["coverage"]))
    lines.append("节奏：" + _pace_text(card["pacing"]))
    lines.append("运镜：" + "；".join(card["camera"]))
    lines.append("声音：" + "；".join(card["sound"]))
    lines.append("AI 风险：" + "；".join(
        f"{item['risk']} → {item['fallback']}" for item in card["ai_risks"]))
    lines.append("示例：" + card["example"])
    return "\n".join(lines)


def _render_compact(card: Mapping) -> str:
    return f"【{card['id']}】{card['title']}：{card['summary']}"


def _render_model_compact(card: Mapping) -> str:
    return f"【{card['id']}】{card['title']}：{card['summary']}"


def _render_grammar(card: Mapping) -> str:
    lines = [
        f"【{card['id']}】{card['title']}：{card['summary']}",
        "定义：" + card["definition"],
        "叙事作用：" + card["narrative_use"],
        "安全写法：" + card["safe_prompt"],
    ]
    if card.get("avoid"):
        lines.append("不要这样写：" + "；".join(card["avoid"]))
    for entry in card.get("entries", []):
        lines.append(f"{entry['name']}：{entry['safe_prompt']}")
    return "\n".join(lines)


def _render_model(card: Mapping) -> str:
    lines = [
        f"【{card['id']}】{card['title']}：{card['summary']}",
        "事实：" + "；".join(card["facts"]),
        "肖像闸：" + card["portrait_gate"],
        "版权：" + card["copyright"],
        "运镜风险：" + "；".join(card["motion_risks"]),
        "提示词写法：" + "；".join(card["prompt_syntax"]),
        f"同框上限：{card['max_characters']} 人",
    ]
    return "\n".join(lines)


def _render_negative(card: Mapping) -> str:
    return "\n".join([
        f"【{card['id']}】{card['title']}：{card['summary']}",
        "错误写法：" + card["wrong"],
        "正确写法：" + card["right"],
        "原因：" + card["why"],
        "证据：" + card["evidence"],
    ])


def _render_shot(shot) -> str:
    if isinstance(shot, Mapping):
        labels = (
            ("shot_size", "景别"), ("angle", "角度"), ("camera", "机位"),
            ("action", "动作"), ("duration_s", "时长"), ("first_frame_prompt", "首帧"),
            ("video_prompt", "视频提示词"),
        )
        parts = [f"{label}：{shot[key]}" for key, label in labels
                 if shot.get(key) not in (None, "")]
        if parts:
            return "；".join(parts)
    import json
    return json.dumps(shot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _render_exemplar(exemplar: Mapping) -> str:
    lines = [f"【好例 {exemplar['id']}】{exemplar.get('scene_type')}："
             f"{exemplar.get('reason') or '（未写原因）'}"]
    shot = exemplar.get("shot")
    if shot is not None:
        lines.append("镜头：" + _render_shot(shot))
    return "\n".join(lines)


def _compose(blocks: list[list[str]]) -> str:
    return "\n\n".join(block for section in blocks for block in section)


def select_materials(tags: SceneTags, video_model: Literal["wan", "seedance"], *,
                     owner: str | None = None, budget_chars: int = 8000) -> dict:
    """按 §5 选取模板、位置卡、语法卡、模型卡、反例与作者案例。"""
    if video_model not in ("wan", "seedance"):
        raise HTTPException(422, "video_model 只能是 wan 或 seedance")
    if type(budget_chars) is not int or budget_chars <= 0:
        raise HTTPException(422, "budget_chars 必须是正整数")
    checked = _validated_tags(tags)
    library = loader.load_library()

    template = library.scene(checked["scene_type"])
    if template is None:
        raise HTTPException(422, f"知识库缺少场景卡 scene-{checked['scene_type']}")
    position = None
    if checked["position"] != "body":
        position = library.get(_POSITION_CARDS[checked["position"]])
    model = _pick_model(library, video_model, checked["realism"])
    grammar_cards = _select_grammar(library, template, position, checked)
    negative_cards = _select_negatives(library, template, position, checked, video_model)

    exemplars: list[dict] = []
    if owner is not None:
        from ..store import good_exemplars_for_retrieval
        exemplars = good_exemplars_for_retrieval(owner, checked["scene_type"], _MAX_EXEMPLARS)

    template_blocks = [_render_scene(template)]
    position_blocks = [_render_scene(position)] if position is not None else []
    grammar_blocks = [_render_grammar(card) for card in grammar_cards]
    model_blocks = [_render_model(model)] if model is not None else []
    negative_blocks = [_render_negative(card) for card in negative_cards]
    exemplar_blocks = [_render_exemplar(item) for item in exemplars]

    # 裁剪顺序：exemplars → negatives → grammar 尾部；template/position/model 永不删。
    while True:
        text = _compose([template_blocks, position_blocks, grammar_blocks,
                         model_blocks, negative_blocks, exemplar_blocks])
        if len(text) <= budget_chars:
            break
        if exemplar_blocks:
            exemplar_blocks.pop()
        elif negative_blocks:
            negative_blocks.pop()
        elif grammar_blocks:
            grammar_blocks.pop()
        else:
            # 预算小到连三张基础卡都放不下：保留卡片本身，改用摘要行，
            # 保证注入文本仍不超过 budget_chars。
            template_blocks = [_render_compact(template)]
            position_blocks = [_render_compact(position)] if position is not None else []
            model_blocks = [_render_model_compact(model)] if model is not None else []
            text = _compose([template_blocks, position_blocks, model_blocks])
            if len(text) > budget_chars:
                text = text[:budget_chars]
            break

    card_ids: list[str] = [template["id"]]
    if position is not None:
        card_ids.append(position["id"])
    card_ids.extend(card["id"] for card in grammar_cards[:len(grammar_blocks)])
    if model is not None:
        card_ids.append(model["id"])
    card_ids.extend(card["id"] for card in negative_cards[:len(negative_blocks)])

    text = _compose([template_blocks, position_blocks, grammar_blocks,
                     model_blocks, negative_blocks, exemplar_blocks])
    if len(text) > budget_chars:
        # 只有极小预算会走到这里（摘要行仍放不下）；保证硬上限。
        text = text[:budget_chars]
    return {
        "template": template,
        "position": position,
        "grammar": grammar_cards[:len(grammar_blocks)],
        "model": model,
        "exemplars": exemplars[:len(exemplar_blocks)],
        "negatives": negative_cards[:len(negative_blocks)],
        "card_ids": list(dict.fromkeys(card_ids)),
        "text": text,
        "chars": len(text),
    }
