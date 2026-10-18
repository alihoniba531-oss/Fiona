"""知识库检查（WO3e §6）：6 条内置规则 + model/negative 卡的数据驱动规则。

``lint_shots`` 只返回 ``warn`` / ``info``，不阻断生成；规则顺序固定，便于
试拆结果并排展示。
"""

from __future__ import annotations

from collections.abc import Mapping
import re

from . import loader
from .retrieval import SceneTags

_CAMERA_TERMS = {
    "Dolly": ("推轨", "推镜", "推近", "前推", "镜头推进", "轨道", "滑轨"),
    "Crane": ("摇臂", "升降", "吊臂"),
    "Aerial": ("航拍", "航摄", "高空俯拍"),
    "Truck": ("横移", "平移", "侧移", "轨道横移"),
    "Pedestal": ("升降", "机位升降", "底座升降"),
    "Orbit": ("环绕", "绕拍", "围绕"),
}
# Python 的 \b 把汉字也当单词字符，中文提示词里紧挨汉字的英文术语会漏报；
# 这里用 ASCII 字母的前后视断言，忽略大小写但不受中文影响。
_CAMERA_TERM_RE = {
    term: re.compile(rf"(?<![A-Za-z]){term}(?![A-Za-z])", re.IGNORECASE)
    for term in _CAMERA_TERMS
}
_LOOK_AT_CAMERA_ZH = ("朝向镜头", "看向镜头", "直视镜头", "面朝镜头")
_LOOK_AT_CAMERA_ZH_NEGATIONS = ("不", "别", "勿", "避免", "不要", "禁止")
_LOOK_AT_CAMERA_EN = re.compile(
    r"(?<![A-Za-z])(?:looks?|looking|stares?|staring|gazes?|gazing)\s+(?:at|into)\s+"
    r"(?:the\s+)?camera(?![A-Za-z])"
    r"|(?<![A-Za-z])towards?\s+(?:the\s+)?camera(?![A-Za-z])",
    re.IGNORECASE,
)
_ACTION_SEPARATORS = ("，然后", "，接着", "、并", "；")
_SENSITIVE_TRIGGERS = {"structure", "material", "face_closeup", "giant_offscreen"}
_CLOSE_SHOT_SIZES = ("中景", "近景", "特写")
# 提示词长度规则只量对应字段，不再拿多字段拼接后的总长比对。
_PROMPT_LENGTH_RULE_FIELDS = {
    "seedance-prompt-too-long": "video_prompt",
    "seedream-prompt-too-long": "first_frame_prompt",
}


def _model_cards() -> tuple[dict, ...]:
    """可被测试替换的模型卡入口；只读 cards/model/。"""
    return loader.load_cards_of_type("model")


def _negative_cards() -> tuple[dict, ...]:
    return loader.load_cards_of_type("negative")


def _text(shot: Mapping, key: str) -> str:
    value = shot.get(key)
    return value if isinstance(value, str) else ""


def _shot_text(shot: Mapping) -> str:
    return "\n".join(
        text for text in (_text(shot, key) for key in (
            "first_frame_prompt", "video_prompt", "action", "camera", "angle",
        )) if text
    )


def _shot_size(shot: Mapping) -> str:
    value = shot.get("shot_size")
    return value if isinstance(value, str) else ""


def _shot_no(shot: Mapping, index: int):
    value = shot.get("no")
    if value is None:
        value = shot.get("shot_no")
    return value if value is not None else index + 1


def _face_visible(shot: Mapping) -> bool:
    explicit = shot.get("face_visible")
    if type(explicit) is bool:
        return explicit
    text = _shot_text(shot)
    if any(word in text for word in (
        "剪影", "背影", "侧背", "背对", "遮脸", "遮住脸", "不露脸",
        "脸在暗处", "头发遮", "俯拍加头发",
    )):
        return False
    return True


def _sensitive(shot: Mapping, tags: Mapping) -> set[str]:
    shot_sensitive = shot.get("sensitive")
    values = set(shot_sensitive) if isinstance(shot_sensitive, list) else set()
    tag_sensitive = tags.get("sensitive") if isinstance(tags, Mapping) else None
    if isinstance(tag_sensitive, list):
        values.update(tag_sensitive)
    return values


def _duration(shot: Mapping) -> float | None:
    value = shot.get("duration_s")
    if type(value) is bool:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _entry(shot_no, rule_id: str, level: str, message: str) -> dict:
    return {"shot_no": shot_no, "rule_id": rule_id, "level": level, "message": message}


def _zh_looking_at_camera(text: str) -> str | None:
    """返回未被否定的中文看镜头短语；前面 0–2 字内的否定词视为不报警。"""
    for phrase in _LOOK_AT_CAMERA_ZH:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            prefix = text[max(0, index - 2):index]
            if not any(negation in prefix for negation in _LOOK_AT_CAMERA_ZH_NEGATIONS):
                return phrase
            start = index + 1
    return None


def _builtin_rules(shot: Mapping, shot_no, *, video_model: str, tags: Mapping) -> list[dict]:
    findings: list[dict] = []
    prompt_text = _shot_text(shot)
    size = _shot_size(shot)

    # 1. 英文运镜术语裸写：同一段提示词里没有对应中文白话。
    prompt_fields = [_text(shot, key) for key in (
        "first_frame_prompt", "video_prompt", "camera", "action")]
    for term, plain_words in _CAMERA_TERMS.items():
        for field_text in prompt_fields:
            if not field_text:
                continue
            if (_CAMERA_TERM_RE[term].search(field_text)
                    and not any(word in field_text for word in plain_words)):
                findings.append(_entry(
                    shot_no, "bare-camera-term", "warn",
                    f"提示词裸写英文运镜术语 {term}；请写成「术语 + 中文白话」，"
                    f"例如「推轨（镜头沿地面平稳靠近）」",
                ))
                break

    # 2. 人物看镜头 / 把视线送进镜头。
    matched = _zh_looking_at_camera(prompt_text)
    if matched is None:
        english = _LOOK_AT_CAMERA_EN.search(prompt_text)
        matched = english.group(0) if english else None
    if matched:
        findings.append(_entry(
            shot_no, "looking-at-camera", "warn",
            f"出现「{matched}」；人物视线应落在对手、关键物件或出口上，并写明不看镜头",
        ))

    # 3. 单镜动作超过 3 个（按动作分隔符近似计数）。
    action = _text(shot, "action")
    if action:
        count = 1 + sum(action.count(separator) for separator in _ACTION_SEPARATORS)
        if count > 3:
            findings.append(_entry(
                shot_no, "too-many-actions", "warn",
                f"按分隔符近似计有 {count} 个动作，超过单镜 3 个上限；请拆镜或删减",
            ))

    # 4. 敏感镜头（结构、材质、人脸、画外巨物）用了非固定机位。
    #    「非固定机位」字面上含「固定」，必须按非固定处理。
    sensitive = _sensitive(shot, tags)
    triggered = bool(shot.get("sensitive")) or bool(sensitive & _SENSITIVE_TRIGGERS)
    camera = _text(shot, "camera")
    fixed_camera = "固定" in camera and "非固定" not in camera
    if triggered and not fixed_camera:
        reason = "、".join(sorted(sensitive & _SENSITIVE_TRIGGERS)) or "本镜 sensitive 标记"
        findings.append(_entry(
            shot_no, "sensitive-nonfixed-camera", "warn",
            f"{reason} 属于敏感镜头，但机位没有写「固定」；请改为固定机位并锁定光向与轮廓",
        ))

    # 5. Seedance 写实中景/近景/特写露脸：肖像闸风险。
    realism = tags.get("realism", "photoreal")
    if (video_model == "seedance" and realism == "photoreal"
            and any(word in size for word in _CLOSE_SHOT_SIZES) and _face_visible(shot)):
        findings.append(_entry(
            shot_no, "seedance-portrait-gate", "warn",
            "Seedance 写实的中景、近景或特写露脸首帧会触发肖像闸；"
            "建议改用万相，或改成逆光剪影、约 65° 俯拍加头发遮脸、远景或背影",
        ))

    # 6. 生成时长低于 4 秒。
    duration = _duration(shot)
    if duration is not None and duration < 4:
        findings.append(_entry(
            shot_no, "short-generation", "info",
            f"生成时长 {duration:g} 秒低于 4 秒下限；请按至少 4 秒生成，再按镜长裁切",
        ))
    return findings


def _when_matches(when: Mapping, shot: Mapping, *, tags: Mapping,
                  shot_size: str, face_visible: bool, sensitive: set[str]) -> bool:
    for field, expected in when.items():
        if field == "realism":
            if tags.get("realism", "photoreal") != expected:
                return False
        elif field == "shot_size_in":
            if not any(word in shot_size for word in expected):
                return False
        elif field == "face_visible":
            if face_visible is not expected:
                return False
        elif field == "scene_type_in":
            if tags.get("scene_type") not in expected:
                return False
        elif field == "position_in":
            if tags.get("position", "body") not in expected:
                return False
        elif field == "sensitive_any":
            if not sensitive.intersection(expected):
                return False
        else:  # schema 已挡住未知条件；运行期防御性返回不命中。
            return False
    return True


def _model_rules(shot: Mapping, shot_no, *, video_model: str, tags: Mapping,
                 cards: tuple[dict, ...] | None = None) -> list[dict]:
    realism = tags.get("realism", "photoreal")
    if cards is None:
        cards = _model_cards()
    family = [card for card in cards
              if card["model"].startswith(f"{video_model}-")]
    exact = [card for card in family if card["style"] == realism]
    selected = exact or [card for card in family if card["style"] == "any"]
    if not selected:
        return []
    prompt_text = _shot_text(shot)
    size = _shot_size(shot)
    visible = _face_visible(shot)
    sensitive = _sensitive(shot, tags)
    findings: list[dict] = []
    for card in sorted(selected, key=lambda item: item["id"]):
        for rule in card["lint_rules"]:
            matched = False
            if "pattern" in rule:
                rule_text = prompt_text
                length_field = _PROMPT_LENGTH_RULE_FIELDS.get(rule["id"])
                if length_field is not None:
                    rule_text = _text(shot, length_field)
                matched = re.search(rule["pattern"], rule_text) is not None
            else:
                matched = _when_matches(rule["when"], shot, tags=tags, shot_size=size,
                                        face_visible=visible, sensitive=sensitive)
            if matched:
                findings.append(_entry(shot_no, rule["id"], rule["level"], rule["message"]))
    return findings


def _video_model_matches(values, video_model: str) -> bool:
    for value in values:
        if value == video_model or value.startswith(f"{video_model}-"):
            return True
        if f"-{video_model}-" in value or value.startswith(f"model-{video_model}-"):
            return True
    return False


def _negative_applies(card: Mapping, *, video_model: str, tags: Mapping) -> bool:
    applies = card.get("applies_to") or {}
    scene_types = applies.get("scene_type")
    if scene_types and tags.get("scene_type") not in scene_types:
        return False
    models = applies.get("model")
    if models and not _video_model_matches(models, video_model):
        return False
    return True


def _negative_rules(shot: Mapping, shot_no, *, video_model: str, tags: Mapping,
                    cards: tuple[dict, ...] | None = None) -> list[dict]:
    prompt_text = _shot_text(shot)
    if cards is None:
        cards = _negative_cards()
    findings = []
    for card in cards:
        pattern = card.get("lint_pattern")
        if not pattern or not _negative_applies(card, video_model=video_model, tags=tags):
            continue
        if re.search(pattern, prompt_text) is not None:
            findings.append(_entry(
                shot_no, card["id"], "warn",
                f"命反例「{card['title']}」：{card['why']}",
            ))
    return findings


def lint_shots(shots: list[dict], *, video_model: str, tags: SceneTags) -> list[dict]:
    """按 §6 检查分镜；只返回 warn/info，不改变 shots。"""
    if not isinstance(shots, list):
        raise ValueError("shots 必须是列表")
    if not isinstance(tags, Mapping):
        raise ValueError("tags 必须是对象")
    results: list[dict] = []
    seen: set[tuple] = set()
    # P5：一次 lint 只加载一次模型卡与反例卡，避免逐镜同步读 YAML。
    model_cards = _model_cards()
    negative_cards = _negative_cards()
    for index, shot in enumerate(shots):
        if not isinstance(shot, Mapping):
            raise ValueError("每个镜头必须是对象")
        shot_no = _shot_no(shot, index)
        findings = _builtin_rules(shot, shot_no, video_model=video_model, tags=tags)
        findings += _model_rules(shot, shot_no, video_model=video_model, tags=tags,
                                 cards=model_cards)
        findings += _negative_rules(shot, shot_no, video_model=video_model, tags=tags,
                                    cards=negative_cards)
        for finding in findings:
            key = (finding["shot_no"], finding["rule_id"])
            if key in seen:
                continue
            seen.add(key)
            results.append(finding)
    return results
