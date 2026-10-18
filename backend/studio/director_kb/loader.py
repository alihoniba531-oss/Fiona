"""读取并索引 ``backend/studio/director_kb/cards/`` 下的 YAML 卡片。

加载器只读仓库内这一个目录，不读环境变量、不读仓库外文件。重复 id、
文件名与 id 不符、scene_type 重复、跨卡引用不存在都会明确报错。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import yaml

from . import schema

CARDS_DIR = Path(__file__).resolve().parent / "cards"
_CARD_SUFFIXES = (".yaml", ".yml")


class CardLoadError(ValueError):
    """卡片目录内容不合法。"""


class _UniqueKeyLoader(yaml.SafeLoader):
    """拒绝 YAML 重复键；PyYAML 默认会静默保留后一个值。"""


def _construct_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise CardLoadError(f"YAML 重复键 {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


@dataclass(frozen=True)
class CardLibrary:
    """全库卡片与检索索引；所有序列按 id 排序，保证结果确定。"""

    cards: Mapping[str, dict]
    by_type: Mapping[str, tuple[str, ...]]
    by_scene_type: Mapping[str, str]

    def get(self, card_id: str) -> dict | None:
        return self.cards.get(card_id)

    def all(self) -> tuple[dict, ...]:
        return tuple(self.cards[card_id] for card_id in sorted(self.cards))

    def of_type(self, card_type: str) -> tuple[dict, ...]:
        return tuple(self.cards[card_id] for card_id in self.by_type.get(card_type, ()))

    def scene(self, scene_type: str) -> dict | None:
        card_id = self.by_scene_type.get(scene_type)
        return self.cards.get(card_id) if card_id else None

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.cards))


def _card_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir()
                  if path.is_file() and path.suffix in _CARD_SUFFIXES)


def _read_card(path: Path, card_type: str) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CardLoadError(f"{path}: 无法读取（{exc.__class__.__name__}）") from None
    try:
        card = yaml.load(text, Loader=_UniqueKeyLoader)
    except CardLoadError as exc:
        raise CardLoadError(f"{path.name}: {exc}") from None
    except yaml.YAMLError as exc:
        raise CardLoadError(f"{path.name}: YAML 解析失败（{exc.__class__.__name__}）") from None
    if not isinstance(card, dict):
        raise CardLoadError(f"{path.name}: 卡片顶层必须是对象")
    try:
        schema.validate_card(card, path=f"cards/{card_type}/{path.name}", filename=path.name)
    except schema.CardValidationError as exc:
        raise CardLoadError(str(exc)) from None
    if card["type"] != card_type:
        raise CardLoadError(
            f"cards/{card_type}/{path.name}: type 是 {card['type']}，与所在目录 {card_type} 不符"
        )
    return card


def _load_dir(card_type: str) -> list[dict]:
    if card_type not in schema.CARD_TYPES:
        raise ValueError(f"未知卡片类型：{card_type}")
    directory = CARDS_DIR / card_type
    cards = []
    seen: dict[str, Path] = {}
    for path in _card_files(directory):
        card = _read_card(path, card_type)
        if card["id"] in seen:
            raise CardLoadError(
                f"重复 id {card['id']}：{seen[card['id']].name} 与 {path.name}"
            )
        seen[card["id"]] = path
        cards.append(card)
    return sorted(cards, key=lambda item: item["id"])


def load_cards_of_type(card_type: str) -> tuple[dict, ...]:
    """只加载某一类型的卡片（lint 用，避免依赖尚未落盘的其它类型）。"""
    cards = _load_dir(card_type)
    if card_type == "grammar":
        try:
            schema.validate_references(cards)
        except schema.CardValidationError as exc:
            raise CardLoadError(str(exc)) from None
    return tuple(cards)


def build_library(cards: Iterable[Mapping]) -> CardLibrary:
    """从已解析的卡片构造索引；测试与文件加载共用同一套校验。"""
    by_id: dict[str, dict] = {}
    by_type: dict[str, list[str]] = {card_type: [] for card_type in schema.CARD_TYPES}
    by_scene_type: dict[str, str] = {}
    for card in cards:
        card = dict(card)
        try:
            schema.validate_card(card, path=f"cards/{card.get('type', '?')}/{card.get('id', '?')}")
        except schema.CardValidationError as exc:
            raise CardLoadError(str(exc)) from None
        card_id = card["id"]
        if card_id in by_id:
            raise CardLoadError(f"重复 id {card_id}")
        by_id[card_id] = card
        by_type[card["type"]].append(card_id)
        if card["type"] == "scene":
            scene_type = card["scene_type"]
            if scene_type in by_scene_type:
                raise CardLoadError(
                    f"scene_type 重复：{scene_type}（{by_scene_type[scene_type]} 与 {card_id}）"
                )
            by_scene_type[scene_type] = card_id
    try:
        schema.validate_references(by_id.values())
    except schema.CardValidationError as exc:
        raise CardLoadError(str(exc)) from None
    return CardLibrary(
        cards={card_id: by_id[card_id] for card_id in sorted(by_id)},
        by_type={card_type: tuple(sorted(ids)) for card_type, ids in by_type.items()},
        by_scene_type={scene_type: by_scene_type[scene_type]
                       for scene_type in sorted(by_scene_type)},
    )


def load_library() -> CardLibrary:
    """加载全库；只遍历仓库内的 ``cards/``。"""
    stray = [path for path in CARDS_DIR.rglob("*")
             if path.is_file() and path.suffix in _CARD_SUFFIXES
             and path.parent.name not in schema.CARD_TYPES]
    if stray:
        names = ", ".join(sorted(path.relative_to(CARDS_DIR).as_posix() for path in stray))
        raise CardLoadError(f"卡片必须放在 cards/<type>/ 下：{names}")
    cards = [card for card_type in schema.CARD_TYPES for card in _load_dir(card_type)]
    return build_library(cards)


def load_cards() -> dict[str, dict]:
    """全库 id -> 卡片（B/C 与测试的便捷入口）。"""
    return dict(load_library().cards)


def all_cards() -> tuple[dict, ...]:
    return load_library().all()


def get_card(card_id: str) -> dict | None:
    return load_library().get(card_id)


def scene_card(scene_type: str) -> dict | None:
    return load_library().scene(scene_type)


def list_cards(card_type: str | None = None, q: str | None = None) -> list[dict]:
    """列表接口用：可按类型与关键词过滤，按 id 排序。"""
    library = load_library()
    if card_type is not None:
        cards = list(library.of_type(card_type))
    else:
        cards = list(library.all())
    if q:
        needle = q.strip().lower()
        cards = [card for card in cards if needle in _search_text(card)]
    return cards


def _search_text(card: Mapping) -> str:
    return "\n".join([
        card["id"], card["title"], card["summary"],
        " ".join(card.get("tags", [])),
    ]).lower()


def missing_required_ids() -> list[str]:
    """返回 §3.6 尚未落盘的卡片 id；供报告与完整性测试使用。"""
    return schema.missing_required_ids(load_library().all())
