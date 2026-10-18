"""导演知识库卡片契约（WO3e §3）。

本模块只做纯数据校验，不读文件。字段名、取值和边界以
``docs/tasks/2026-10-18-studio-wo3e-director-kb/02-spec.md`` §3 为准；
卡片加载与索引见 :mod:`studio.director_kb.loader`。
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

CARD_TYPES = ("grammar", "scene", "model", "negative")
CARD_ID_PREFIX = {
    "grammar": "grammar-",
    "scene": "scene-",
    "model": "model-",
    "negative": "negative-",
}

# §3.1 只允许这六种授权。
LICENSES = frozenset({"own", "MIT", "MIT-0", "Apache-2.0", "CC-BY-4.0", "vendor-doc"})

# §4 的 17 类内容卡。
CONTENT_SCENE_TYPES = (
    "dialogue",
    "establishing",
    "confrontation",
    "twist",
    "fight",
    "intimacy",
    "chase",
    "phone-call",
    "reveal",
    "process-closeup",
    "monologue",
    "explainer",
    "flashback",
    "scare",
    "ensemble",
    "investigation",
    "montage",
)
# §3.3 的两张位置卡：scene_type -> position。
POSITION_SCENE_TYPES = {"opening-hook": "opening", "cliffhanger": "ending"}
SCENE_TYPES = CONTENT_SCENE_TYPES + tuple(POSITION_SCENE_TYPES)
SCENE_POSITIONS = ("opening", "body", "ending")

# §5 SceneTags.sensitive 的合法子集。
SENSITIVE_TAGS = ("face_closeup", "structure", "material", "giant_offscreen", "ip_risk")

# §3.4 写的模型名带版本点；D3 的 id 风格卡片用连字符（wan-3 / seedance-2-5 /
# seedream-5）。两种写法都只指向同一组模型，schema 接受两种，避免把已定稿卡片判错。
MODEL_NAMES = ("wan-3.0", "wan-3", "seedance-2.5", "seedance-2-5", "seedream-5.0", "seedream-5")
MODEL_STYLES = ("photoreal", "anime", "3d", "any")
LINT_LEVELS = ("warn", "info")

# §3.6 的 id 总表；loader 的完整性检查与测试共用，避免两处抄写。
REQUIRED_GRAMMAR_IDS = (
    "grammar-shot-size",
    "grammar-camera-angle",
    "grammar-camera-movement",
    "grammar-lens-focal",
    "grammar-transition",
    "grammar-axis-eyeline",
    "grammar-continuity",
    "grammar-over-shoulder",
    "grammar-shot-reverse-shot",
    "grammar-insert-closeup",
    "grammar-action-match",
    "grammar-establishing-shot",
    "grammar-backlight-silhouette",
)
REQUIRED_MODEL_IDS = (
    "model-wan-3-photoreal",
    "model-wan-3-anime",
    "model-seedance-2-5-photoreal",
    "model-seedance-2-5-anime",
    "model-seedream-5",
)
REQUIRED_NEGATIVE_IDS = (
    "negative-looking-at-camera",
    "negative-bare-camera-term",
    "negative-voiceover-mouth-moves",
    "negative-photoreal-face-seedance",
    "negative-fight-sub-four-second-generation",
    "negative-nonfixed-structure-material",
    "negative-orbit-invents-detail",
    "negative-push-tilt-reveals-face",
    "negative-move-down-material-drift",
    "negative-giant-offscreen-camera-move",
    "negative-ip-lookalike",
    "negative-grimy-realism",
    "negative-transient-look-in-sheet",
    "negative-too-many-actions",
    "negative-crowded-frame",
    "negative-no-establishing-shot",
    "negative-unwritten-detail-seedream",
    "negative-focal-without-purpose",
    "negative-axis-jump",
    "negative-prop-continuity-break",
    "negative-unverified-model-syntax",
)
REQUIRED_SCENE_IDS = tuple(f"scene-{scene_type}" for scene_type in SCENE_TYPES)
REQUIRED_CARD_IDS = (
    REQUIRED_GRAMMAR_IDS + REQUIRED_SCENE_IDS + REQUIRED_MODEL_IDS + REQUIRED_NEGATIVE_IDS
)

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# §3.1（R1）：tags 一律 kebab-case，不再接受下划线或点。
_TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LINT_RULE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_COMMON_FIELDS = {"id", "type", "title", "summary", "tags", "sources", "version"}
_TYPE_FIELDS = {
    "grammar": {"definition", "narrative_use", "safe_prompt", "avoid", "entries", "related"},
    "scene": {
        "scene_type", "signals", "beats", "coverage", "pacing", "camera", "sound",
        "ai_risks", "example", "related_grammar", "related_negative", "position",
    },
    "model": {
        "model", "style", "facts", "portrait_gate", "copyright", "motion_risks",
        "prompt_syntax", "max_characters", "lint_rules",
    },
    "negative": {"wrong", "right", "why", "evidence", "applies_to", "lint_pattern"},
}
_LINT_WHEN_FIELDS = {
    "realism",
    "shot_size_in",
    "face_visible",
    "scene_type_in",
    "position_in",
    "sensitive_any",
}


class CardValidationError(ValueError):
    """卡片不符合契约；消息带文件或字段路径。"""


def _fail(path: str, message: str):
    raise CardValidationError(f"{path}: {message}")


def _mapping(value, path: str) -> Mapping:
    if not isinstance(value, Mapping):
        _fail(path, "必须是对象")
    return value


def _keys(value: Mapping, path: str, *, required: Iterable[str], optional: Iterable[str] = ()):
    required = set(required)
    allowed = required | set(optional)
    missing = sorted(required - set(value))
    if missing:
        _fail(path, "缺少字段 " + ", ".join(missing))
    extra = sorted(set(value) - allowed)
    if extra:
        _fail(path, "未知字段 " + ", ".join(extra))


def _text(value, path: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "必须是非空字符串")
    if max_length is not None and len(value) > max_length:
        _fail(path, f"不能超过 {max_length} 字")
    return value


def _integer(value, path: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    # bool 是 int 的子类，必须显式排除。
    if type(value) is not int:
        _fail(path, "必须是整数")
    if minimum is not None and value < minimum:
        _fail(path, f"不能小于 {minimum}")
    if maximum is not None and value > maximum:
        _fail(path, f"不能大于 {maximum}")
    return value


def _number(value, path: str) -> float:
    if type(value) not in (int, float) or value != value or value in (float("inf"), float("-inf")):
        _fail(path, "必须是有限数字")
    return float(value)


def _string_list(value, path: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        _fail(path, "必须是列表")
    if nonempty and not value:
        _fail(path, "不能为空")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _fail(f"{path}[{index}]", "必须是非空字符串")
    return value


def _pair(value, path: str, *, low_field: str, high_field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        _fail(path, "必须是两个数字的列表")
    low = _number(value[0], f"{path}[0]")
    high = _number(value[1], f"{path}[1]")
    if low <= 0 or high <= 0:
        _fail(path, "取值必须大于 0")
    if low > high:
        _fail(path, f"{low_field} 不能大于 {high_field}")
    return [low, high]


def _id_list(value, path: str, prefix: str) -> list[str]:
    _string_list(value, path, nonempty=False)
    for index, card_id in enumerate(value):
        if not card_id.startswith(prefix) or not _ID_RE.fullmatch(card_id):
            _fail(f"{path}[{index}]", f"必须是 {prefix}… 形式的卡片 id")
    return value


def _compile_pattern(value, path: str):
    _text(value, path)
    try:
        return re.compile(value)
    except re.error as exc:
        _fail(path, f"正则无法编译：{exc}")


def _validate_common(card: Mapping, path: str):
    # 未知字段由各类型的 _validate_* 用完整键集合统一检查，这里只查共同字段。
    missing = sorted(_COMMON_FIELDS - set(card))
    if missing:
        _fail(path, "缺少字段 " + ", ".join(missing))
    card_id = _text(card["id"], f"{path}.id", max_length=100)
    if not _ID_RE.fullmatch(card_id):
        _fail(f"{path}.id", "必须是 kebab-case 英文 id")
    card_type = card["type"]
    if card_type not in CARD_TYPES:
        _fail(f"{path}.type", "必须是 grammar / scene / model / negative 之一")
    if not card_id.startswith(CARD_ID_PREFIX[card_type]):
        _fail(f"{path}.id", f"前缀必须是 {CARD_ID_PREFIX[card_type]}")
    _text(card["title"], f"{path}.title", max_length=120)
    _text(card["summary"], f"{path}.summary", max_length=80)
    _string_list(card["tags"], f"{path}.tags", nonempty=True)
    for index, tag in enumerate(card["tags"]):
        if not _TAG_RE.fullmatch(tag):
            _fail(f"{path}.tags[{index}]",
                  "只允许小写英文、数字和连字符（kebab-case）")
    sources = card["sources"]
    if not isinstance(sources, list) or not sources:
        _fail(f"{path}.sources", "至少需要一条来源")
    for index, source in enumerate(sources):
        source_path = f"{path}.sources[{index}]"
        _mapping(source, source_path)
        _keys(source, source_path, required={"name", "license"}, optional={"ref"})
        _text(source["name"], f"{source_path}.name")
        if source["license"] not in LICENSES:
            _fail(f"{source_path}.license", "不在允许的授权列表内")
        if "ref" in source:
            _text(source["ref"], f"{source_path}.ref")
    _integer(card["version"], f"{path}.version", minimum=1)
    return card_type


def _validate_grammar(card: Mapping, path: str):
    _keys(card, path,
          required=_COMMON_FIELDS | (_TYPE_FIELDS["grammar"] - {"entries"}),
          optional={"entries"})
    for field in ("definition", "narrative_use", "safe_prompt"):
        _text(card[field], f"{path}.{field}")
    _string_list(card["avoid"], f"{path}.avoid")
    if "entries" in card:
        if not isinstance(card["entries"], list):
            _fail(f"{path}.entries", "必须是列表")
        for index, entry in enumerate(card["entries"]):
            entry_path = f"{path}.entries[{index}]"
            _mapping(entry, entry_path)
            _keys(entry, entry_path, required={"name", "definition", "safe_prompt"})
            for field in ("name", "definition", "safe_prompt"):
                _text(entry[field], f"{entry_path}.{field}")
    _id_list(card["related"], f"{path}.related", "grammar-")


def _validate_scene(card: Mapping, path: str):
    optional = {"position"}
    _keys(card, path, required=_COMMON_FIELDS | _TYPE_FIELDS["scene"] - optional,
          optional=optional)
    scene_type = card["scene_type"]
    if scene_type not in SCENE_TYPES:
        _fail(f"{path}.scene_type", "不在 §4 场景类型清单内")
    expected_id = f"scene-{scene_type}"
    if card["id"] != expected_id:
        _fail(f"{path}.id", f"场景卡 id 必须是 {expected_id}")
    if scene_type in POSITION_SCENE_TYPES:
        if "position" not in card:
            _fail(f"{path}.position", "位置卡必须带 position")
        if card["position"] != POSITION_SCENE_TYPES[scene_type]:
            _fail(f"{path}.position",
                  f"{scene_type} 的 position 必须是 {POSITION_SCENE_TYPES[scene_type]}")
    elif "position" in card:
        _fail(f"{path}.position", "内容卡不能带 position，位置信息请用位置卡")

    _string_list(card["signals"], f"{path}.signals", nonempty=True)
    beats = card["beats"]
    _string_list(beats, f"{path}.beats", nonempty=True)
    if not 3 <= len(beats) <= 6:
        _fail(f"{path}.beats", "必须是 3–6 个节拍")
    _string_list(card["coverage"], f"{path}.coverage", nonempty=True)
    pacing = card["pacing"]
    _mapping(pacing, f"{path}.pacing")
    _keys(pacing, f"{path}.pacing", required={"fast", "mid", "slow"})
    for tier in ("fast", "mid", "slow"):
        tier_path = f"{path}.pacing.{tier}"
        _mapping(pacing[tier], tier_path)
        _keys(pacing[tier], tier_path, required={"shots_per_min", "shot_seconds"})
        _pair(pacing[tier]["shots_per_min"], f"{tier_path}.shots_per_min",
              low_field="下限", high_field="上限")
        _pair(pacing[tier]["shot_seconds"], f"{tier_path}.shot_seconds",
              low_field="下限", high_field="上限")
    _string_list(card["camera"], f"{path}.camera", nonempty=True)
    _string_list(card["sound"], f"{path}.sound", nonempty=True)
    risks = card["ai_risks"]
    if not isinstance(risks, list) or not risks:
        _fail(f"{path}.ai_risks", "至少需要一条风险与降级方案")
    for index, item in enumerate(risks):
        item_path = f"{path}.ai_risks[{index}]"
        _mapping(item, item_path)
        _keys(item, item_path, required={"risk", "fallback"})
        _text(item["risk"], f"{item_path}.risk")
        _text(item["fallback"], f"{item_path}.fallback")
    _text(card["example"], f"{path}.example", max_length=600)
    _id_list(card["related_grammar"], f"{path}.related_grammar", "grammar-")
    _id_list(card["related_negative"], f"{path}.related_negative", "negative-")


def _validate_lint_rule(rule, path: str):
    _mapping(rule, path)
    _keys(rule, path, required={"id", "level", "message"}, optional={"when", "pattern"})
    rule_id = _text(rule["id"], f"{path}.id", max_length=100)
    if not _LINT_RULE_ID_RE.fullmatch(rule_id):
        _fail(f"{path}.id", "必须是 kebab-case 英文 id")
    if rule["level"] not in LINT_LEVELS:
        _fail(f"{path}.level", "必须是 warn 或 info")
    _text(rule["message"], f"{path}.message")
    if ("when" in rule) == ("pattern" in rule):
        _fail(path, "when 与 pattern 必须二选一")
    if "pattern" in rule:
        _compile_pattern(rule["pattern"], f"{path}.pattern")
        return
    when = rule["when"]
    _mapping(when, f"{path}.when")
    if not when:
        _fail(f"{path}.when", "不能为空")
    extra = sorted(set(when) - _LINT_WHEN_FIELDS)
    if extra:
        _fail(f"{path}.when", "未知条件 " + ", ".join(extra))
    for field, value in when.items():
        field_path = f"{path}.when.{field}"
        if field == "realism":
            if value not in ("photoreal", "anime", "3d"):
                _fail(field_path, "只能是 photoreal / anime / 3d")
        elif field == "shot_size_in":
            _string_list(value, field_path, nonempty=True)
        elif field == "face_visible":
            if type(value) is not bool:
                _fail(field_path, "必须是布尔值")
        elif field == "scene_type_in":
            _string_list(value, field_path, nonempty=True)
            for index, scene_type in enumerate(value):
                if scene_type not in SCENE_TYPES:
                    _fail(f"{field_path}[{index}]", "不在场景类型清单内")
        elif field == "position_in":
            _string_list(value, field_path, nonempty=True)
            for index, position in enumerate(value):
                if position not in SCENE_POSITIONS:
                    _fail(f"{field_path}[{index}]", "只能是 opening / body / ending")
        elif field == "sensitive_any":
            _string_list(value, field_path, nonempty=True)
            for index, sensitive in enumerate(value):
                if sensitive not in SENSITIVE_TAGS:
                    _fail(f"{field_path}[{index}]", "不是合法的 sensitive 标记")


def _validate_model(card: Mapping, path: str):
    _keys(card, path, required=_COMMON_FIELDS | _TYPE_FIELDS["model"])
    if card["model"] not in MODEL_NAMES:
        _fail(f"{path}.model", "不在模型能力卡清单内")
    if card["style"] not in MODEL_STYLES:
        _fail(f"{path}.style", "只能是 photoreal / anime / 3d / any")
    facts = _string_list(card["facts"], f"{path}.facts", nonempty=True)
    for index, fact in enumerate(facts):
        # §3.4：每条事实都要注明是实测还是官方，不接受无出处断言。
        if "实测" not in fact and "官方" not in fact:
            _fail(f"{path}.facts[{index}]", "每条事实须注明「实测」或「官方」")
    for field in ("portrait_gate", "copyright"):
        _text(card[field], f"{path}.{field}")
    _string_list(card["motion_risks"], f"{path}.motion_risks")
    _string_list(card["prompt_syntax"], f"{path}.prompt_syntax")
    _integer(card["max_characters"], f"{path}.max_characters", minimum=1, maximum=6)
    if not isinstance(card["lint_rules"], list):
        _fail(f"{path}.lint_rules", "必须是列表")
    seen: set[str] = set()
    for index, rule in enumerate(card["lint_rules"]):
        rule_path = f"{path}.lint_rules[{index}]"
        _validate_lint_rule(rule, rule_path)
        if rule["id"] in seen:
            _fail(rule_path, f"规则 id 重复：{rule['id']}")
        seen.add(rule["id"])


def _validate_negative(card: Mapping, path: str):
    _keys(card, path, required=_COMMON_FIELDS | _TYPE_FIELDS["negative"] - {"applies_to", "lint_pattern"},
          optional={"applies_to", "lint_pattern"})
    for field in ("wrong", "right", "why", "evidence"):
        _text(card[field], f"{path}.{field}")
    if "applies_to" in card:
        applies_to = card["applies_to"]
        _mapping(applies_to, f"{path}.applies_to")
        _keys(applies_to, f"{path}.applies_to", required=set(), optional={"scene_type", "model"})
        if "scene_type" in applies_to:
            _string_list(applies_to["scene_type"], f"{path}.applies_to.scene_type", nonempty=True)
            for index, scene_type in enumerate(applies_to["scene_type"]):
                if scene_type not in SCENE_TYPES:
                    _fail(f"{path}.applies_to.scene_type[{index}]", "不在场景类型清单内")
        if "model" in applies_to:
            _string_list(applies_to["model"], f"{path}.applies_to.model", nonempty=True)
    if "lint_pattern" in card:
        _compile_pattern(card["lint_pattern"], f"{path}.lint_pattern")


def validate_card(card, *, path: str = "card", filename: str | None = None) -> None:
    """校验一张卡片；失败抛 :class:`CardValidationError`。

    ``filename`` 传入卡片文件名（不含目录）时会额外检查文件名与 id 一致。
    """
    _mapping(card, path)
    card_type = _validate_common(card, path)
    if filename is not None:
        if filename.endswith(".yaml"):
            stem = filename[:-5]
        elif filename.endswith(".yml"):
            stem = filename[:-4]
        else:
            _fail(path, f"卡片文件必须用 .yaml 后缀：{filename}")
        if stem != card["id"]:
            _fail(path, f"文件名 {stem} 与 id {card['id']} 不一致")
    if card_type == "grammar":
        _validate_grammar(card, path)
    elif card_type == "scene":
        _validate_scene(card, path)
    elif card_type == "model":
        _validate_model(card, path)
    else:
        _validate_negative(card, path)


def validate_references(cards: Iterable[Mapping]) -> None:
    """检查全库引用：related / related_grammar / related_negative 都必须存在且类型对。"""
    cards = list(cards)
    by_id = {card["id"]: card for card in cards}
    for card in cards:
        path = card["id"]
        if card["type"] == "grammar":
            for index, target in enumerate(card.get("related", [])):
                found = by_id.get(target)
                if found is None:
                    _fail(f"{path}.related[{index}]", f"引用不存在的卡片 {target}")
                if found["type"] != "grammar":
                    _fail(f"{path}.related[{index}]", f"{target} 不是语法卡")
        elif card["type"] == "scene":
            for field, expected_type in (("related_grammar", "grammar"),
                                         ("related_negative", "negative")):
                for index, target in enumerate(card.get(field, [])):
                    found = by_id.get(target)
                    if found is None:
                        _fail(f"{path}.{field}[{index}]", f"引用不存在的卡片 {target}")
                    if found["type"] != expected_type:
                        _fail(f"{path}.{field}[{index}]", f"{target} 不是 {expected_type} 卡")


def missing_required_ids(cards: Iterable[Mapping]) -> list[str]:
    """返回 §3.6 中尚未落盘的 id（排序后）。"""
    present = {card["id"] for card in cards}
    return sorted(set(REQUIRED_CARD_IDS) - present)


def unexpected_scene_ids(cards: Iterable[Mapping]) -> list[str]:
    """返回不在 §4 清单里的场景卡 id（排序后）。"""
    unknown = {card["id"] for card in cards
               if card.get("type") == "scene" and card.get("scene_type") not in SCENE_TYPES}
    return sorted(unknown)
