# -*- coding: utf-8 -*-
"""写歌的歌词结构校验与纯代码自检。

本模块只做确定性的纯计算：不读写文件、不访问数据库、不联网。
结构蓝图（blueprint）与歌词都来自工具参数，调用前可能并不合法，
因此所有公开函数都对异常形状做防御，不抛异常。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from pypinyin import Style, lazy_pinyin

__all__ = [
    "SECTION_TYPES",
    "INSTRUMENTAL_TYPES",
    "RHYME_FORMATS",
    "SECTION_TYPE_LABELS",
    "PROVIDER_CHAR_LIMITS",
    "count_chars",
    "structure_errors",
    "summarize_structure",
    "build_provider_text",
    "check_lyrics",
]

# 与火山歌词标签一致，顺序即展示顺序。
SECTION_TYPES: tuple[str, ...] = (
    "intro",
    "verse",
    "pre-chorus",
    "chorus",
    "bridge",
    "inst",
    "outro",
    "hook",
    "build-up",
    "drop",
    "solo",
)

# 器乐段：只有标签，不能有歌词行。
INSTRUMENTAL_TYPES: frozenset[str] = frozenset({"intro", "inst", "outro", "solo"})

RHYME_FORMATS: tuple[str, ...] = ("AABB", "ABAB", "XAXA", "AAAA", "free")

SECTION_TYPE_LABELS: dict[str, str] = {
    "intro": "前奏",
    "verse": "主歌",
    "pre-chorus": "导歌",
    "chorus": "副歌",
    "bridge": "桥段",
    "inst": "间奏",
    "outro": "尾奏",
    "hook": "记忆点",
    "build-up": "铺垫",
    "drop": "高潮段",
    "solo": "独奏",
}

# 火山 Lyrics 字段的长度上限（provider_text 的字符数，含段落标签与换行）。
PROVIDER_CHAR_LIMITS: dict[str, int] = {
    "Chinese": 700,
    "Cantonese": 700,
    "English": 2000,
}

_SECTION_ID_RE = re.compile(r"^s[0-9]{1,2}$")

# 汉字（含扩展区）。判断“最后一个汉字”与计字共用。
_HAN_RE = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002ebef\U00030000-\U0003134f]"
)
_DIGIT_RE = re.compile(r"\d")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
_BRACKETS = ("[", "]", "【", "】")

# strict=True 下的实际韵母（以 pypinyin 0.55.0 为准）→ 十三辙。
_FINALS_TO_RHYME: dict[str, str] = {
    "a": "发花",
    "ia": "发花",
    "ua": "发花",
    "o": "梭波",
    "uo": "梭波",
    "e": "梭波",
    "ie": "乜斜",
    "ve": "乜斜",
    "i": "一七",
    "v": "一七",
    "er": "一七",
    "u": "姑苏",
    "ai": "怀来",
    "uai": "怀来",
    "ei": "灰堆",
    "uei": "灰堆",
    "ao": "遥条",
    "iao": "遥条",
    "ou": "油求",
    "iou": "油求",
    "an": "言前",
    "ian": "言前",
    "uan": "言前",
    "van": "言前",
    "en": "人辰",
    "in": "人辰",
    "uen": "人辰",
    "vn": "人辰",
    "ang": "江阳",
    "iang": "江阳",
    "uang": "江阳",
    "eng": "中东",
    "ing": "中东",
    "ong": "中东",
    "iong": "中东",
    "ueng": "中东",
}

_LANG_LABELS = {"Chinese": "中文", "English": "英文", "Cantonese": "粤语"}


def _issue(
    code: str,
    message: str,
    section_id: str | None = None,
    line_index: int | None = None,
) -> dict[str, Any]:
    """统一的 error / warning 形状。"""
    return {
        "code": code,
        "section_id": section_id,
        "line_index": line_index,
        "message": message,
    }


def _as_items(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_chars(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    low, high = value
    if not (_is_int(low) and _is_int(high)):
        return False
    return 1 <= low <= high <= 30


def _normalize_lang(lang: Any) -> str:
    """把外部传入的语言归一到火山的三个取值；未知值按中文处理。"""
    if isinstance(lang, str):
        value = lang.strip().casefold()
        if value == "english":
            return "English"
        if value == "cantonese":
            return "Cantonese"
    return "Chinese"


def _lang_label(lang: Any) -> str:
    return _LANG_LABELS.get(_normalize_lang(lang), "中文")


def count_chars(line: Any, lang: Any) -> int:
    """按规格计字。

    - 中文 / 粤语：每个汉字 1、每个数字 1、每段连续拉丁字母 1；标点和空白不计。
    - 英文：按空白分隔的单词数。
    """
    text = line if isinstance(line, str) else ""
    if _normalize_lang(lang) == "English":
        return len(text.split())
    return (
        len(_HAN_RE.findall(text))
        + len(_DIGIT_RE.findall(text))
        + len(_LATIN_WORD_RE.findall(text))
    )


def structure_errors(structure: Any) -> list[dict[str, Any]]:
    """校验结构蓝图（§6.2），返回逐条问题；空列表表示通过。"""
    if not isinstance(structure, (list, tuple)):
        return [_issue("structure_shape", "结构蓝图必须是从 1 到 16 段的列表")]

    sections = list(structure)
    if not sections:
        return [_issue("structure_shape", "结构蓝图至少需要 1 段")]

    errors: list[dict[str, Any]] = []
    if len(sections) > 16:
        errors.append(
            _issue(
                "structure_shape",
                f"结构蓝图最多 16 段，当前 {len(sections)} 段",
            )
        )

    seen_ids: set[str] = set()
    has_chorus = False
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            errors.append(_issue("section_shape", f"第 {index} 段必须是对象"))
            continue

        raw_id = section.get("id")
        section_id = raw_id if isinstance(raw_id, str) else None
        if not isinstance(raw_id, str) or not _SECTION_ID_RE.match(raw_id):
            errors.append(
                _issue(
                    "section_id",
                    f"第 {index} 段的 id 必须是 s1–s99 的形式",
                    section_id,
                )
            )
        elif raw_id in seen_ids:
            errors.append(_issue("section_id", f"段落 id「{raw_id}」重复", section_id))
        else:
            seen_ids.add(raw_id)

        section_type = section.get("type")
        type_ok = isinstance(section_type, str) and section_type in SECTION_TYPES
        if not type_ok:
            errors.append(
                _issue(
                    "section_type",
                    f"第 {index} 段的类型必须是 {' / '.join(SECTION_TYPES)} 之一",
                    section_id,
                )
            )
            # 类型未知时无法判断唱段还是器乐段，跳过该段的其余字段校验。
            continue

        if section_type in ("chorus", "hook"):
            has_chorus = True

        lines = section.get("lines")
        if section_type in INSTRUMENTAL_TYPES:
            if not _is_int(lines) or lines != 0:
                errors.append(
                    _issue(
                        "section_lines",
                        f"器乐段 {section_id or index} 的 lines 必须为 0",
                        section_id,
                    )
                )
        else:
            if not _is_int(lines) or not 1 <= lines <= 12:
                errors.append(
                    _issue(
                        "section_lines",
                        f"唱段 {section_id or index} 的 lines 必须在 1–12 之间",
                        section_id,
                    )
                )

        chars = section.get("chars")
        chars_omitted = section_type in INSTRUMENTAL_TYPES and chars is None
        if not chars_omitted and not _valid_chars(chars):
            errors.append(
                _issue(
                    "section_chars",
                    f"段落 {section_id or index} 的 chars 必须是 [最小字数, 最大字数]，"
                    "且 1 ≤ min ≤ max ≤ 30",
                    section_id,
                )
            )

        rhyme = section.get("rhyme")
        rhyme_omitted = section_type in INSTRUMENTAL_TYPES and rhyme is None
        if not rhyme_omitted and not (
            isinstance(rhyme, str) and rhyme in RHYME_FORMATS
        ):
            errors.append(
                _issue(
                    "section_rhyme",
                    f"段落 {section_id or index} 的押韵格式必须是 "
                    "AABB / ABAB / XAXA / AAAA / free",
                    section_id,
                )
            )

    if not has_chorus:
        errors.append(
            _issue("chorus_required", "结构蓝图至少需要一个 chorus 或 hook 段")
        )
    return errors


def summarize_structure(structure: Any) -> str:
    """生成给人看的一行结构摘要，例如「s1 主歌 4 行 7–9 字 AABB」。"""
    if not isinstance(structure, (list, tuple)):
        return ""

    parts: list[str] = []
    for section in structure:
        if not isinstance(section, dict):
            parts.append("? 未知")
            continue

        raw_id = section.get("id")
        section_id = raw_id if isinstance(raw_id, str) and raw_id else "?"
        section_type = section.get("type")
        type_name = section_type if isinstance(section_type, str) else None
        label = SECTION_TYPE_LABELS.get(type_name, type_name or "未知")

        if type_name in INSTRUMENTAL_TYPES:
            parts.append(f"{section_id} {label} 器乐")
            continue

        fragments = [f"{section_id} {label}"]
        lines = section.get("lines")
        if _is_int(lines):
            fragments.append(f"{lines} 行")
        chars = section.get("chars")
        if _valid_chars(chars):
            fragments.append(f"{chars[0]}–{chars[1]} 字")
        rhyme = section.get("rhyme")
        if isinstance(rhyme, str) and rhyme:
            fragments.append(rhyme)
        parts.append(" ".join(fragments))

    return "；".join(parts)


def build_provider_text(structure: Any, sections: Any) -> str:
    """按结构蓝图顺序拼出提交给火山的 Lyrics 文本。

    标签独占一行，段与段之间不空行；器乐段只保留标签。
    """
    if not isinstance(structure, (list, tuple)):
        return ""

    section_by_id: dict[str, dict[str, Any]] = {}
    for section in _as_items(sections):
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        if isinstance(section_id, str) and section_id not in section_by_id:
            section_by_id[section_id] = section

    chunks: list[str] = []
    for blueprint in structure:
        if not isinstance(blueprint, dict):
            continue
        section_type = blueprint.get("type")
        type_name = section_type if isinstance(section_type, str) else None
        label = type_name or ""
        chunks.append(f"[{label}]")
        if type_name in INSTRUMENTAL_TYPES:
            continue
        blueprint_id = blueprint.get("id")
        section = (
            section_by_id.get(blueprint_id) if isinstance(blueprint_id, str) else None
        )
        if not isinstance(section, dict):
            continue
        lines = _as_items(section.get("lines"))
        for line in lines:
            chunks.append(line if isinstance(line, str) else str(line))
    return "\n".join(chunks)


def _last_han_final(line: str) -> str | None:
    """取整行最后一个汉字在整句上下文中的 strict 韵母。"""
    last_index = -1
    for match in _HAN_RE.finditer(line):
        last_index = match.start()
    if last_index < 0:
        return None

    syllables = lazy_pinyin(
        line,
        style=Style.FINALS,
        strict=True,
        errors=lambda chunk: list(chunk),
    )
    if len(syllables) == len(line):
        final = syllables[last_index]
    else:
        # pypinyin 的输出一般与字符一一对应；极少数文本长度不一致时，
        # 用“到最后一个汉字为止”的前缀兜底，仍保留整句上下文。
        prefix_syllables = lazy_pinyin(
            line[: last_index + 1],
            style=Style.FINALS,
            strict=True,
            errors=lambda chunk: list(chunk),
        )
        final = prefix_syllables[-1] if prefix_syllables else ""
    if not isinstance(final, str):
        return None
    final = final.strip()
    return final or None


def _rhyme_group(line: str) -> str | None:
    final = _last_han_final(line)
    if final is None:
        return None
    return _FINALS_TO_RHYME.get(final)


def _rhyme_warnings(
    records: list[dict[str, Any]],
    groups: list[str | None],
    rhyme_format: str | None,
    section_id: str,
    label: str,
) -> list[dict[str, Any]]:
    """按蓝图格式判定本段每个参与行的 rhyme_ok，并返回押韵警告。"""
    for record in records:
        record["rhyme_ok"] = None

    if rhyme_format not in ("AABB", "ABAB", "XAXA", "AAAA"):
        # free 与缺失/非法格式都不判。
        return []

    # 只保留有汉字、能映射到十三辙的行；行号仍用歌词中的 1 起序号。
    items = [
        (record["line_index"], group, record)
        for record, group in zip(records, groups)
        if group is not None
    ]
    if not items:
        return []

    warnings: list[dict[str, Any]] = []

    def mark_pair(
        first: tuple[int, str, dict[str, Any]],
        second: tuple[int, str, dict[str, Any]],
    ) -> None:
        if first[1] == second[1]:
            first[2]["rhyme_ok"] = True
            second[2]["rhyme_ok"] = True
            return
        first[2]["rhyme_ok"] = False
        second[2]["rhyme_ok"] = False
        warnings.append(
            _issue(
                "rhyme",
                f"{label}第 {first[0]} 行与第 {second[0]} 行不同辙（{rhyme_format}）",
                section_id,
                first[0],
            )
        )
        warnings.append(
            _issue(
                "rhyme",
                f"{label}第 {second[0]} 行与第 {first[0]} 行不同辙（{rhyme_format}）",
                section_id,
                second[0],
            )
        )

    if rhyme_format == "AABB":
        # 第 1、2 行同辙，第 3、4 行同辙……奇数行数时最后一行不判。
        for start in range(0, len(items) - 1, 2):
            mark_pair(items[start], items[start + 1])

    elif rhyme_format == "ABAB":
        # 1 与 3、2 与 4、5 与 7、6 与 8……，完整对才判。
        for base in range(0, len(items), 4):
            for offset in (0, 1):
                first_index = base + offset
                second_index = first_index + 2
                if second_index < len(items):
                    mark_pair(items[first_index], items[second_index])

    elif rhyme_format == "XAXA":
        # 所有偶数行同辙；奇数行不约束，保持 null。
        even_items = items[1::2]
        if len(even_items) >= 2:
            first_group = even_items[0][1]
            if all(item[1] == first_group for item in even_items):
                for item in even_items:
                    item[2]["rhyme_ok"] = True
            else:
                for item in even_items:
                    item[2]["rhyme_ok"] = False
                    warnings.append(
                        _issue(
                            "rhyme",
                            f"{label}第 {item[0]} 行不满足 XAXA（偶数行需同辙）",
                            section_id,
                            item[0],
                        )
                    )

    else:  # AAAA
        for item in items:
            item[2]["rhyme_ok"] = True
        first_group = items[0][1]
        if any(item[1] != first_group for item in items):
            for item in items:
                item[2]["rhyme_ok"] = False
                warnings.append(
                    _issue(
                        "rhyme",
                        f"{label}第 {item[0]} 行不满足 AAAA（全段需同辙）",
                        section_id,
                        item[0],
                    )
                )

    return warnings


def _ids_text(ids: Iterable[Any]) -> str:
    values = [str(value) if value is not None else "?" for value in ids]
    if not values:
        return "（空）"
    shown = "、".join(values[:6])
    if len(values) > 6:
        shown += "…"
    return shown


def check_lyrics(
    structure: Any,
    sections: Any,
    lang: Any,
) -> dict[str, Any]:
    """对歌词做结构、字数、押韵与长度自检（§6.4 / §6.5）。

    结构蓝图本身的合法性由 :func:`structure_errors` 负责；这里只检查歌词
    与蓝图是否一致，以及逐行内容。
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    line_records: list[dict[str, Any]] = []

    structure_sections = _as_items(structure)
    lyric_sections = _as_items(sections)

    structure_ids = [
        section.get("id") if isinstance(section, dict) else None
        for section in structure_sections
    ]
    lyric_ids = [
        section.get("id") if isinstance(section, dict) else None
        for section in lyric_sections
    ]
    if structure_ids != lyric_ids:
        errors.append(
            _issue(
                "structure_mismatch",
                "歌词段落与结构蓝图不一致："
                f"蓝图 {_ids_text(structure_ids)}，歌词 {_ids_text(lyric_ids)}",
            )
        )

    section_by_id: dict[str, dict[str, Any]] = {}
    for section in lyric_sections:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        if isinstance(section_id, str) and section_id not in section_by_id:
            section_by_id[section_id] = section

    for blueprint in structure_sections:
        if not isinstance(blueprint, dict):
            continue

        section_id = blueprint.get("id")
        section_type = blueprint.get("type")
        type_name = section_type if isinstance(section_type, str) else None
        label = SECTION_TYPE_LABELS.get(type_name, type_name or "段落")
        section = section_by_id.get(section_id) if isinstance(section_id, str) else None
        raw_lines = section.get("lines") if isinstance(section, dict) else None
        lines = _as_items(raw_lines)

        if type_name in INSTRUMENTAL_TYPES:
            if lines:
                errors.append(
                    _issue(
                        "instrumental_has_lines",
                        f"{label}是器乐段，不能有歌词行",
                        section_id if isinstance(section_id, str) else None,
                    )
                )
            # 器乐段不产出逐行记录，也不参与押韵与字数统计。
            continue

        if not lines:
            errors.append(
                _issue(
                    "empty_section",
                    f"{label}没有歌词",
                    section_id if isinstance(section_id, str) else None,
                )
            )

        expected_lines = blueprint.get("lines")
        if section is not None and _is_int(expected_lines) and len(lines) != expected_lines:
            warnings.append(
                _issue(
                    "line_count",
                    f"{label}有 {len(lines)} 行，蓝图要求 {expected_lines} 行",
                    section_id if isinstance(section_id, str) else None,
                )
            )

        chars_range = blueprint.get("chars")
        has_chars_range = _valid_chars(chars_range)
        records: list[dict[str, Any]] = []
        groups: list[str | None] = []

        for line_index, line in enumerate(lines, start=1):
            text = line if isinstance(line, str) else ""
            if not text.strip():
                errors.append(
                    _issue(
                        "empty_section",
                        f"{label}第 {line_index} 行是空的",
                        section_id if isinstance(section_id, str) else None,
                        line_index,
                    )
                )

            if any(bracket in text for bracket in _BRACKETS):
                errors.append(
                    _issue(
                        "bracket_in_line",
                        f"{label}第 {line_index} 行不能包含 [ ] 【 】 标签符号",
                        section_id if isinstance(section_id, str) else None,
                        line_index,
                    )
                )

            chars = count_chars(text, lang)
            if chars > 30:
                errors.append(
                    _issue(
                        "line_too_long",
                        f"{label}第 {line_index} 行 {chars} 字，超过单行 30 字上限",
                        section_id if isinstance(section_id, str) else None,
                        line_index,
                    )
                )

            if has_chars_range:
                low, high = int(chars_range[0]), int(chars_range[1])
                if chars < low - 1 or chars > high + 1:
                    warnings.append(
                        _issue(
                            "char_count",
                            f"{label}第 {line_index} 行 {chars} 字，"
                            f"蓝图要求 {low}–{high} 字",
                            section_id if isinstance(section_id, str) else None,
                            line_index,
                        )
                    )

            group = _rhyme_group(text)
            record = {
                "section_id": section_id if isinstance(section_id, str) else None,
                "line_index": line_index,
                "chars": chars,
                "rhyme_group": group,
                "rhyme_ok": None,
            }
            line_records.append(record)
            records.append(record)
            groups.append(group)

        rhyme_format = blueprint.get("rhyme")
        if isinstance(rhyme_format, str):
            warnings.extend(
                _rhyme_warnings(
                    records,
                    groups,
                    rhyme_format,
                    section_id if isinstance(section_id, str) else "",
                    label,
                )
            )

    # 多个 chorus 段歌词不完全相同：只提醒，不阻断。
    choruses: list[tuple[str | None, list[str]]] = []
    for blueprint in structure_sections:
        if not isinstance(blueprint, dict) or blueprint.get("type") != "chorus":
            continue
        section_id = blueprint.get("id")
        section = section_by_id.get(section_id) if isinstance(section_id, str) else None
        raw_lines = section.get("lines") if isinstance(section, dict) else None
        lines = _as_items(raw_lines)
        normalized = [line if isinstance(line, str) else str(line) for line in lines]
        choruses.append(
            (section_id if isinstance(section_id, str) else None, normalized)
        )
    if len(choruses) > 1:
        base_id, base_lines = choruses[0]
        for section_id, lines in choruses[1:]:
            if lines != base_lines:
                warnings.append(
                    _issue(
                        "chorus_variant",
                        f"多个副歌段歌词不完全相同（{base_id or '第 1 个副歌'} 与 "
                        f"{section_id or '后续副歌'}）",
                        section_id,
                    )
                )

    provider_text = build_provider_text(structure_sections, lyric_sections)
    provider_chars = len(provider_text)
    normalized_lang = _normalize_lang(lang)
    limit = PROVIDER_CHAR_LIMITS.get(normalized_lang, 700)
    if provider_chars > limit:
        errors.append(
            _issue(
                "too_long",
                f"歌词共 {provider_chars} 字符，超过{_lang_label(lang)}"
                f"上限 {limit} 字符",
            )
        )
    elif provider_chars < 5:
        errors.append(
            _issue("too_long", f"歌词共 {provider_chars} 字符，至少需要 5 字符")
        )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "lines": line_records,
        "provider_text": provider_text,
        "provider_chars": provider_chars,
    }
